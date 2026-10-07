from __future__ import annotations

import concurrent.futures
import json
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from typing import Any, Iterator, Mapping

from ..code_generation import generate_search_code
from ..critique import critique_candidate
from ..execution import execute_generated_code
from ..formalization import formalize_request
from ..frontiers import initial_frontiers, mutate_frontier
from ..models import (
    FiniteGroupIdentityTarget,
    FormalizationError,
    Frontier,
    ProblemKind,
    ProblemSpec,
    SearchBudget,
    VerificationResult,
)
from ..output_format import format_candidate
from ..repair import build_repair_request, repair_frontiers
from ..symbolic_tools import exact_parse_expression, exact_zero
from ..verification import verify_candidate
from .exports import ExportError, exhaustion_latex, latex_summary, sympy_identity_proof_script, sympy_reproduction_script, symbolic_proof_latex
from .payloads import (
    PayloadError,
    artifact_safe,
    budget_payload,
    certificate_payload,
    event_envelope,
    exhaustion_payload,
    formalization_payload,
    frontier_payload,
    seconds_text,
    sha256_text,
    symbolic_proof_payload,
)


class InvalidRequestError(ValueError):
    pass


_FLOAT_FIELDS = frozenset({"time_seconds", "execution_timeout_seconds"})
_FIELD_LIMITS: dict[str, tuple[float, float]] = {
    "time_seconds": (0.05, 600.0),
    "max_frontier_visits": (1, 20000),
    "max_verified_candidates": (1, 20000),
    "max_mutation_rounds": (1, 20000),
    "execution_timeout_seconds": (0.25, 300.0),
    "max_candidates_per_frontier": (1, 64),
    "max_instances_per_solve": (1, 1000000),
    "max_point_pairs": (1, 1000000),
    "max_group_order": (1, 64),
}
_BUDGET_FIELD_MAP = {
    "time_seconds": "max_seconds",
    "max_frontier_visits": "max_frontier_visits",
    "max_verified_candidates": "max_verified_candidates",
    "max_mutation_rounds": "max_mutation_rounds",
    "execution_timeout_seconds": "execution_timeout_seconds",
    "max_candidates_per_frontier": "max_candidates_per_frontier",
    "max_instances_per_solve": "max_instances_per_solve",
    "max_point_pairs": "max_point_pairs",
}
_REPAIR_PER_BATCH = 5
_FORMALIZATION_TIMEOUT_SECONDS = 20.0
_FORMALIZATION_WORKERS = 4


def _bounded_number(name: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exception:
        raise InvalidRequestError("invalid_budget_field:" + name) from exception
    if number != number or number in (float("inf"), float("-inf")):
        raise InvalidRequestError("invalid_budget_field:" + name)
    low, high = _FIELD_LIMITS[name]
    if number < low or number > high:
        raise InvalidRequestError("budget_field_out_of_range:" + name)
    return number


def _bounded_integer(name: str, value: Any) -> int:
    number = _bounded_number(name, value)
    if float(number) != float(int(number)):
        raise InvalidRequestError("budget_field_not_integer:" + name)
    return int(number)


def resolve_budget(payload: Mapping[str, Any] | None) -> SearchBudget:
    defaults = SearchBudget()
    if payload is None:
        return defaults
    if not isinstance(payload, Mapping):
        raise InvalidRequestError("budget_payload_not_an_object")
    values: dict[str, Any] = {}
    for request_field, budget_field in _BUDGET_FIELD_MAP.items():
        if request_field not in payload or payload[request_field] is None:
            continue
        if request_field in _FLOAT_FIELDS:
            values[budget_field] = _bounded_number(request_field, payload[request_field])
        else:
            values[budget_field] = _bounded_integer(request_field, payload[request_field])
    return replace(defaults, **values)


def requested_group_order(payload: Mapping[str, Any] | None) -> int | None:
    if not isinstance(payload, Mapping) or payload.get("max_group_order") is None:
        return None
    return _bounded_integer("max_group_order", payload["max_group_order"])


def apply_group_order_limit(specification: ProblemSpec, requested: int | None) -> ProblemSpec:
    target = specification.finite_group_identity
    if target is None or requested is None:
        return specification
    if specification.order_bound is not None:
        effective = int(specification.order_bound)
    else:
        effective = int(requested)
    effective = max(1, min(effective, 64))
    if effective == int(target.max_order):
        return specification
    updated = FiniteGroupIdentityTarget(
        variables=target.variables,
        left_word=target.left_word,
        right_word=target.right_word,
        identity_symbol=target.identity_symbol,
        inverse_symbol=target.inverse_symbol,
        operation_symbols=target.operation_symbols,
        max_order=effective,
        constraints=target.constraints,
    )
    return replace(specification, finite_group_identity=updated, order_bound=effective)


def _statistics(counters: Mapping[str, Any], started: float) -> dict[str, Any]:
    lanes = counters.get("lanes")
    lane_rows: list[dict[str, Any]] = []
    if isinstance(lanes, Mapping):
        for name in sorted(lanes):
            record = dict(lanes[name])
            lane_rows.append(
                {
                    "lane": str(name),
                    "visits": int(record.get("visits", 0)),
                    "candidates": int(record.get("candidates", 0)),
                    "repairs": int(record.get("repairs", 0)),
                }
            )
    return {
        "frontiers_examined": int(counters.get("frontiers_examined", 0)),
        "candidates_verified": int(counters.get("candidates_verified", 0)),
        "mutation_rounds": int(counters.get("mutation_rounds", 0)),
        "queued_frontiers": int(counters.get("queued_frontiers", 0)),
        "repairs": int(counters.get("repairs", 0)),
        "executions": int(counters.get("executions", 0)),
        "lane_count": len(lane_rows),
        "lanes": lane_rows,
        "repair_reasons": [str(item) for item in counters.get("repair_reasons", ())],
        "elapsed_seconds": seconds_text(max(0.0, time.monotonic() - started)),
    }



def symbolic_identity_proof_text(specification: ProblemSpec) -> str | None:
    if specification.kind != ProblemKind.ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT:
        return None
    target = specification.algebraic_identity
    if target is None:
        return None
    try:
        left = exact_parse_expression(target.left_expression, target.variables)
        right = exact_parse_expression(target.right_expression, target.variables)
    except Exception:
        return None
    try:
        holds = exact_zero(left - right)
    except Exception:
        holds = False
    if not holds:
        try:
            left_source = exact_parse_expression(str(target.left_source or target.left_expression), target.variables)
            right_source = exact_parse_expression(str(target.right_source or target.right_expression), target.variables)
            holds = exact_zero(left_source - right_source)
        except Exception:
            holds = False
    if not holds:
        return None
    left_text = str(target.left_source) if target.left_source else str(target.left_expression)
    right_text = str(target.right_source) if target.right_source else str(target.right_expression)
    return "\n".join(
        (
            "no counterassignment exists",
            "kind: " + specification.kind.value,
            "left: " + left_text,
            "right: " + right_text,
            "left_canonical: " + str(target.left_expression),
            "right_canonical: " + str(target.right_expression),
            "reason: identity_holds_symbolically",
        )
    )


def exhaustion_text(specification: ProblemSpec, statistics: Mapping[str, Any], reason: str) -> str:
    lines = [
        "no counterexample found within the search budget",
        "kind: " + specification.kind.value,
        "frontiers_examined: " + str(statistics.get("frontiers_examined", 0)),
        "candidates_verified: " + str(statistics.get("candidates_verified", 0)),
        "mutation_rounds: " + str(statistics.get("mutation_rounds", 0)),
        "reason: " + str(reason),
    ]
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        lines.append("note: the two dimensional case of the Jacobian conjecture remains open")
    if specification.kind == ProblemKind.FINITE_FIELD_JACOBIAN_REFUTATION:
        lines.append("note: the finite field ladder was visited without a certified collision; a missing collision is not a proof of the statement")
        lines.append("note: the general two dimensional Jacobian conjecture in characteristic zero remains open")
    return "\n".join(lines)


def attach_exports(payload: dict[str, Any]) -> dict[str, Any]:
    kind = str(payload.get("kind", ""))
    sympy_script = ""
    try:
        if kind == "counterexample":
            latex_document = latex_summary(payload)
            sympy_script = sympy_reproduction_script(payload)
        elif kind == "symbolic_proof":
            latex_document = symbolic_proof_latex(payload)
            sympy_script = sympy_identity_proof_script(payload)
        elif kind == "exhaustion":
            latex_document = exhaustion_latex(payload)
        else:
            raise ExportError("unsupported_certificate_kind:" + kind)
    except ExportError:
        raise
    except Exception as exception:
        raise PayloadError("export_failed:" + type(exception).__name__) from exception
    query_slug = "".join(character if character.isalnum() else "-" for character in str(payload.get("query", ""))).strip("-")[:48]
    payload["exports"] = {
        "latex": latex_document,
        "sympy": sympy_script,
        "json": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False),
        "base_filename": ("exact-formula-search-" + (query_slug or "certificate")),
        "kind": kind,
    }
    return payload


@dataclass(frozen=True)
class SearchPlan:
    query: str
    specification: ProblemSpec
    budget: SearchBudget
    group_order_limit: int | None
    proof_text: str | None


class SearchService:
    def __init__(self, concurrency: int = 4, formalization_timeout: float = _FORMALIZATION_TIMEOUT_SECONDS) -> None:
        self._formalization_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=_FORMALIZATION_WORKERS,
            thread_name_prefix="exact-formula-formalizer",
        )
        self._formalization_slots = threading.BoundedSemaphore(_FORMALIZATION_WORKERS)
        self._formalization_timeout = max(1.0, float(formalization_timeout))
        if int(concurrency) < 1:
            raise ValueError("invalid_search_concurrency")
        self._search_slots = threading.BoundedSemaphore(int(concurrency))

    def acquire_search_slot(self) -> bool:
        return bool(self._search_slots.acquire(blocking=False))

    def release_search_slot(self) -> None:
        try:
            self._search_slots.release()
        except ValueError:
            pass

    def _guarded_formalize(self, query: str) -> ProblemSpec:
        if not self._formalization_slots.acquire(blocking=False):
            raise InvalidRequestError("formalization_queue_full")
        try:
            future = self._formalization_pool.submit(formalize_request, query)
            try:
                return future.result(timeout=self._formalization_timeout)
            except concurrent.futures.TimeoutError as exception:
                raise InvalidRequestError("formalization_timeout") from exception
        finally:
            self._formalization_slots.release()

    def prepare(self, raw_text: str, budget_values: Mapping[str, Any] | None = None, with_proof: bool = True) -> SearchPlan:
        query = "" if raw_text is None else str(raw_text)
        if not query.strip():
            raise InvalidRequestError("empty_query")
        if len(query) > 20000:
            raise InvalidRequestError("query_too_long")
        budget = resolve_budget(budget_values)
        group_limit = requested_group_order(budget_values)
        try:
            specification = self._guarded_formalize(query)
        except FormalizationError as exception:
            raise InvalidRequestError("formalization_failed:" + str(exception)) from exception
        specification = apply_group_order_limit(specification, group_limit)
        proof_text = symbolic_identity_proof_text(specification) if with_proof else None
        return SearchPlan(
            query=query,
            specification=specification,
            budget=budget,
            group_order_limit=group_limit,
            proof_text=proof_text,
        )

    def formalize(self, raw_text: str, budget_values: Mapping[str, Any] | None = None) -> dict[str, Any]:
        plan = self.prepare(raw_text, budget_values, with_proof=False)
        payload = formalization_payload(plan.specification, plan.budget, plan.group_order_limit)
        payload["budget"] = budget_payload(plan.budget, plan.group_order_limit)
        payload["group_order_limit"] = plan.group_order_limit
        payload["symbolic_proof_available"] = bool(symbolic_identity_proof_text(plan.specification))
        payload["accepted"] = True
        return payload

    def stream(self, plan: SearchPlan, cancel: Any = None) -> Iterator[dict[str, Any]]:
        started = time.monotonic()
        sequence = 0

        def emit(event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
            nonlocal sequence
            sequence += 1
            return event_envelope(event_type, sequence, payload)

        counters: dict[str, Any] = {
            "frontiers_examined": 0,
            "candidates_verified": 0,
            "mutation_rounds": 0,
            "queued_frontiers": 0,
            "repairs": 0,
            "executions": 0,
            "lanes": {},
            "repair_reasons": [],
        }
        specification = plan.specification
        budget = plan.budget
        deadline = started + max(0.001, float(budget.max_seconds))

        yield emit(
            "search_started",
            {
                "query": plan.query,
                "problem_kind": specification.kind.value,
                "budget": budget_payload(budget, plan.group_order_limit),
                "group_order_limit": plan.group_order_limit,
                "statistics": _statistics(counters, started),
            },
        )
        yield emit("formalization", formalization_payload(specification, budget, plan.group_order_limit))
        if plan.proof_text is not None:
            proof = symbolic_proof_payload(
                specification,
                plan.proof_text,
                budget,
                budget_payload(budget, plan.group_order_limit),
                time.monotonic() - started,
                plan.group_order_limit,
            )
            attach_exports(proof)
            yield emit("symbolic_proof", proof)
            return

        active: deque[Frontier] = deque()
        known_signatures: set[str] = set()
        last_frontier: Frontier | None = None

        def queue_frontiers(frontiers: tuple[Frontier, ...]) -> list[dict[str, Any]]:
            queued: list[dict[str, Any]] = []
            for frontier in frontiers:
                if frontier.unique_signature in known_signatures:
                    continue
                known_signatures.add(frontier.unique_signature)
                active.append(frontier)
                counters["queued_frontiers"] += 1
                queued.append(frontier_payload(frontier))
            return queued

        def repair_events(reason: str, frontier: Frontier | None, **kwargs: Any) -> list[dict[str, Any]]:
            request = build_repair_request(reason, frontier, **kwargs)
            mutated = repair_frontiers(specification, request, known_signatures, _REPAIR_PER_BATCH, budget)
            queued = queue_frontiers(mutated)
            counters["repairs"] += 1
            reasons = counters["repair_reasons"]
            if isinstance(reasons, list) and str(reason) not in reasons:
                reasons.append(str(reason))
            lanes = counters["lanes"]
            if frontier is not None and isinstance(lanes, dict):
                record = lanes.setdefault(frontier.lane_identifier, {"visits": 0, "candidates": 0, "repairs": 0})
                record["repairs"] = int(record.get("repairs", 0)) + 1
            payloads = [frontier_payload(item) for item in mutated]
            actions = sorted({str(item["repair_action"]) for item in payloads if str(item["repair_action"])})
            return [
                emit(
                    "repair_triggered",
                    {
                        "reason": reason,
                        "repair_actions": actions,
                        "exception_text": str(kwargs.get("exception_text", ""))[:500],
                        "new_frontier_signatures": [item["signature"] for item in queued],
                        "queued_frontiers": queued,
                        "statistics": _statistics(counters, started),
                    },
                )
            ]

        def exhausted(reason: str) -> dict[str, Any]:
            statistics = _statistics(counters, started)
            payload = exhaustion_payload(
                specification,
                statistics,
                reason,
                exhaustion_text(specification, statistics, reason),
                budget,
                budget_payload(budget, plan.group_order_limit),
                time.monotonic() - started,
                statistics["lanes"],
                statistics["repair_reasons"],
                plan.group_order_limit,
            )
            attach_exports(payload)
            return emit("search_exhausted", payload)

        def budget_exhausted() -> bool:
            return (
                counters["frontiers_examined"] >= budget.max_frontier_visits
                or counters["candidates_verified"] >= budget.max_verified_candidates
                or counters["mutation_rounds"] >= budget.max_mutation_rounds
                or time.monotonic() >= deadline
            )

        for payload in queue_frontiers(initial_frontiers(specification)):
            yield emit("frontier_queued", {**payload, "statistics": _statistics(counters, started)})

        while True:
            if cancel is not None and cancel.is_set():
                yield emit("search_cancelled", {"reason": "client_cancelled", "statistics": _statistics(counters, started)})
                return
            if budget_exhausted():
                yield exhausted("search_budget_exhausted")
                return
            if not active:
                counters["mutation_rounds"] += 1
                counters["repairs"] += 1
                if last_frontier is not None and isinstance(counters["lanes"], dict):
                    record = counters["lanes"].setdefault(last_frontier.lane_identifier, {"visits": 0, "candidates": 0, "repairs": 0})
                    record["repairs"] = int(record.get("repairs", 0)) + 1
                queued = queue_frontiers(
                    mutate_frontier(last_frontier, known_signatures, _REPAIR_PER_BATCH, "active_queue_empty", specification.kind)
                )
                if not queued:
                    queued = queue_frontiers(
                        mutate_frontier(None, known_signatures, _REPAIR_PER_BATCH, "active_queue_empty_root", specification.kind)
                    )
                if not queued:
                    yield exhausted("frontier_space_exhausted")
                    return
                yield emit(
                    "repair_triggered",
                    {
                        "reason": "active_queue_empty",
                        "repair_actions": ["expand_frontier_space"],
                        "new_frontier_signatures": [item["signature"] for item in queued],
                        "queued_frontiers": queued,
                        "statistics": _statistics(counters, started),
                    },
                )
                continue
            frontier = active.popleft()
            last_frontier = frontier
            counters["frontiers_examined"] += 1
            lanes = counters["lanes"]
            if isinstance(lanes, dict):
                record = lanes.setdefault(frontier.lane_identifier, {"visits": 0, "candidates": 0, "repairs": 0})
                record["visits"] = int(record.get("visits", 0)) + 1
            yield emit(
                "frontier_visit",
                {
                    **frontier_payload(frontier),
                    "frontier_signature": frontier.unique_signature,
                    "statistics": _statistics(counters, started),
                },
            )
            try:
                generated = generate_search_code(specification, frontier, budget)
            except Exception as exception:
                for event in repair_events("code_generation_exception", frontier, exception_text=repr(exception)[:500]):
                    yield event
                continue
            if generated.generation_issues:
                for event in repair_events(
                    "code_generation_exception", frontier, exception_text=";".join(generated.generation_issues)
                ):
                    yield event
                continue
            yield emit(
                "code_generated",
                {
                    "frontier_signature": frontier.unique_signature,
                    "source_fingerprint": generated.source_fingerprint,
                    "worker_sha256": sha256_text(generated.source),
                    "source_sha256": sha256_text(generated.source),
                    "entry_function": generated.entry_function,
                    "worker_code": generated.source,
                    "line_count": generated.source.count("\n") + 1,
                    "statistics": _statistics(counters, started),
                },
            )
            remaining = deadline - time.monotonic()
            execution_budget = replace(
                budget,
                execution_timeout_seconds=min(float(budget.execution_timeout_seconds), max(0.25, remaining)),
            )
            execution_started = time.monotonic()
            counters["executions"] += 1
            try:
                execution_result = execute_generated_code(generated, specification, frontier, execution_budget)
            except Exception as exception:
                for event in repair_events("execution_or_empty_frontier", frontier, exception_text=repr(exception)[:500]):
                    yield event
                continue
            yield emit(
                "execution_completed",
                {
                    "frontier_signature": frontier.unique_signature,
                    "status": "ok" if execution_result.candidates else "no_candidate",
                    "candidate_count": len(execution_result.candidates),
                    "failure_reasons": [str(item) for item in execution_result.failure_reasons],
                    "exception_text": str(execution_result.exception_text)[:500],
                    "route": str(execution_result.internal_artifacts.get("route", "")),
                    "worker_artifacts": artifact_safe(dict(execution_result.internal_artifacts)),
                    "execution_seconds": seconds_text(max(0.0, time.monotonic() - execution_started)),
                    "statistics": _statistics(counters, started),
                },
            )
            if not execution_result.candidates:
                for event in repair_events(
                    "no_candidate_returned",
                    frontier,
                    execution_result=execution_result,
                    exception_text=execution_result.exception_text,
                ):
                    yield event
                continue
            for candidate in execution_result.candidates[: max(1, budget.max_candidates_per_frontier)]:
                counters["candidates_verified"] += 1
                if counters["candidates_verified"] > budget.max_verified_candidates:
                    yield exhausted("candidate_budget_exhausted")
                    return
                try:
                    verification = verify_candidate(specification, candidate)
                except Exception as exception:
                    verification = VerificationResult(
                        False,
                        candidate,
                        (type(exception).__name__,),
                        {
                            "exception": repr(exception)[:500],
                            "no_numeric_certification": False,
                            "denominator_status": False,
                        },
                    )
                yield emit(
                    "verification_completed",
                    {
                        "frontier_signature": frontier.unique_signature,
                        "passed": bool(verification.passed),
                        "issue_codes": [str(item) for item in verification.issues],
                        "artifacts": artifact_safe(dict(verification.artifacts)),
                        "statistics": _statistics(counters, started),
                    },
                )
                if not verification.passed:
                    for event in repair_events(
                        "verification_rejection",
                        frontier,
                        verification_result=verification,
                        execution_result=execution_result,
                    ):
                        yield event
                    continue
                try:
                    critique = critique_candidate(specification, candidate, verification, generated, frontier)
                except Exception as exception:
                    for event in repair_events(
                        "critique_exception",
                        frontier,
                        verification_result=verification,
                        exception_text=repr(exception)[:500],
                    ):
                        yield event
                    continue
                yield emit(
                    "critique_completed",
                    {
                        "frontier_signature": frontier.unique_signature,
                        "passed": bool(critique.passed),
                        "issue_codes": [str(item.code) for item in critique.issues],
                        "repair_hints": [str(item.repair_hint) for item in critique.issues if str(item.repair_hint)],
                        "artifacts": artifact_safe(dict(critique.artifacts)),
                        "statistics": _statistics(counters, started),
                    },
                )
                if not critique.passed:
                    lanes = counters["lanes"]
                    if isinstance(lanes, dict):
                        record = lanes.setdefault(frontier.lane_identifier, {"visits": 0, "candidates": 0, "repairs": 0})
                        record["repairs"] = int(record.get("repairs", 0)) + 1
                    for event in repair_events(
                        "critique_rejection",
                        frontier,
                        verification_result=verification,
                        critique_result=critique,
                        execution_result=execution_result,
                    ):
                        yield event
                    continue
                try:
                    formatted_text = format_candidate(specification, candidate)
                    if not formatted_text:
                        raise PayloadError("empty_formatted_candidate")
                    certificate = certificate_payload(
                        specification=specification,
                        candidate=candidate,
                        verification=verification,
                        critique=critique,
                        generated=generated,
                        frontier=frontier,
                        formatted_text=formatted_text,
                        budget=budget,
                        budget_payload_value=budget_payload(budget, plan.group_order_limit),
                        statistics=_statistics(counters, started),
                        runtime_seconds=time.monotonic() - started,
                        max_group_order=plan.group_order_limit,
                    )
                    attach_exports(certificate)
                except Exception as exception:
                    for event in repair_events(
                        "format_exception",
                        frontier,
                        verification_result=verification,
                        critique_result=critique,
                        exception_text=repr(exception)[:500],
                    ):
                        yield event
                    continue
                lanes = counters["lanes"]
                if isinstance(lanes, dict):
                    record = lanes.setdefault(frontier.lane_identifier, {"visits": 0, "candidates": 0, "repairs": 0})
                    record["candidates"] = int(record.get("candidates", 0)) + 1
                yield emit("search_completed", certificate)
                return
