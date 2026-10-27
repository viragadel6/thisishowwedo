from __future__ import annotations

import math
import operator
import time
from collections import deque
from collections.abc import Iterable
from typing import Any

from .code_generation import generate_search_code
from .critique import critique_candidate
from .execution import execute_generated_code
from .formalization import formalize_request
from .frontiers import initial_frontiers, mutate_frontier
from .models import Frontier, ProblemKind, SearchBudget, VerificationResult
from .output_format import format_candidate
from .repair import build_repair_request, repair_frontiers
from .symbolic_tools import exact_parse_expression, exact_zero
from .verification import verify_candidate

FRONTIER_BATCH_SIZE = 5
MAX_DIAGNOSTIC_TEXT_LENGTH = 500
MINIMUM_SEARCH_SECONDS = 0.001


def _bounded_text(text: Any) -> str:
    if text is None:
        return ""
    return str(text)[:MAX_DIAGNOSTIC_TEXT_LENGTH]


def _exception_text(exception: BaseException) -> str:
    try:
        return _bounded_text(repr(exception))
    except Exception:
        return _bounded_text(type(exception).__name__)


def _symbolic_proof_report(specification: Any) -> str:
    if getattr(specification, "kind", None) != ProblemKind.ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT:
        return ""
    target = getattr(specification, "algebraic_identity", None)
    if target is None:
        return ""
    try:
        left = exact_parse_expression(target.left_expression, target.variables)
        right = exact_parse_expression(target.right_expression, target.variables)
        identity_holds = exact_zero(left - right)
    except Exception:
        return ""
    if identity_holds:
        kind_str = specification.kind.value if hasattr(specification.kind, "value") else str(specification.kind)
        return "\n".join(
            (
                "no counterassignment exists",
                "kind: " + str(kind_str),
                "left: " + str(target.left_expression),
                "right: " + str(target.right_expression),
                "reason: identity_holds_symbolically",
            )
        )
    return ""


def _exhausted_report(specification: Any, statistics: dict[str, int], reason: str) -> str:
    kind_val = specification.kind.value if hasattr(specification.kind, "value") else str(specification.kind)
    lines = [
        "no counterexample found within the search budget",
        "kind: " + str(kind_val),
        "frontiers_examined: " + str(statistics.get("frontiers_examined", 0)),
        "candidates_verified: " + str(statistics.get("candidates_verified", 0)),
        "mutation_rounds: " + str(statistics.get("mutation_rounds", 0)),
        "reason: " + str(reason),
    ]
    if getattr(specification, "kind", None) == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        lines.append("note: the two dimensional case of the Jacobian conjecture remains open")
    return "\n".join(lines)


def _extract_candidates(raw_candidates: Any, limit: int) -> list[Any]:
    if raw_candidates is None or limit <= 0:
        return []
    if isinstance(raw_candidates, (str, bytes)):
        return [raw_candidates]
    if isinstance(raw_candidates, dict):
        iterator = iter(raw_candidates.values())
    else:
        try:
            iterator = iter(raw_candidates)
        except TypeError:
            return [raw_candidates]
    result: list[Any] = []
    while len(result) < limit:
        try:
            result.append(next(iterator))
        except StopIteration:
            break
    return result


def run(raw_text: str, budget: SearchBudget | None = None) -> str:
    if not isinstance(raw_text, str):
        raise TypeError("raw_text must be a string")
    limits = budget if budget is not None else SearchBudget()
    max_seconds = max(MINIMUM_SEARCH_SECONDS, float(limits.max_seconds))
    deadline = time.monotonic() + max_seconds
    specification = formalize_request(raw_text)
    proof = _symbolic_proof_report(specification)
    if proof:
        return proof

    active: deque[Frontier] = deque()
    known_signatures: set[str] = set()
    last_frontier: Frontier | None = None
    statistics: dict[str, int] = {
        "frontiers_examined": 0,
        "candidates_verified": 0,
        "mutation_rounds": 0,
    }

    def candidate_exhaustion_reason() -> str:
        if limits.max_candidates_per_frontier == 0 or statistics["candidates_verified"] >= limits.max_verified_candidates:
            return "candidate_budget_exhausted"
        if time.monotonic() >= deadline:
            return "search_budget_exhausted"
        return ""

    def frontier_exhaustion_reason() -> str:
        if statistics["frontiers_examined"] >= limits.max_frontier_visits:
            return "search_budget_exhausted"
        return candidate_exhaustion_reason()

    def add_frontiers(frontiers: Iterable[Frontier] | None) -> None:
        if frontiers is None:
            return
        try:
            iterator = iter(frontiers)
        except TypeError:
            return
        for frontier in iterator:
            if frontier is None:
                continue
            signature = getattr(frontier, "unique_signature", None)
            if signature is not None and signature not in known_signatures:
                known_signatures.add(signature)
                active.append(frontier)

    def enqueue_repairs(request: Any) -> None:
        if request is None:
            return
        try:
            repaired = repair_frontiers(
                specification,
                request,
                known_signatures,
                FRONTIER_BATCH_SIZE,
                limits,
            )
            add_frontiers(repaired)
        except Exception:
            pass

    try:
        add_frontiers(initial_frontiers(specification))
    except Exception:
        pass

    while True:
        stop_reason = frontier_exhaustion_reason()
        if stop_reason:
            return _exhausted_report(specification, statistics, stop_reason)

        if not active:
            if statistics["mutation_rounds"] >= limits.max_mutation_rounds:
                return _exhausted_report(specification, statistics, "mutation_budget_exhausted")
            statistics["mutation_rounds"] += 1
            if last_frontier is not None:
                try:
                    mutated = mutate_frontier(
                        last_frontier,
                        known_signatures,
                        FRONTIER_BATCH_SIZE,
                        "active_queue_empty",
                        specification.kind,
                    )
                    add_frontiers(mutated)
                except Exception:
                    pass
            if not active:
                try:
                    mutated_root = mutate_frontier(
                        None,
                        known_signatures,
                        FRONTIER_BATCH_SIZE,
                        "active_queue_empty_root",
                        specification.kind,
                    )
                    add_frontiers(mutated_root)
                except Exception:
                    pass
            if not active:
                if time.monotonic() >= deadline:
                    return _exhausted_report(specification, statistics, "search_budget_exhausted")
                return _exhausted_report(specification, statistics, "frontier_space_exhausted")

        frontier = active.popleft()
        last_frontier = frontier
        statistics["frontiers_examined"] += 1

        try:
            generated = generate_search_code(specification, frontier, limits)
        except Exception as exception:
            try:
                request = build_repair_request(
                    "code_generation_exception",
                    frontier,
                    exception_text=_exception_text(exception),
                )
                enqueue_repairs(request)
            except Exception:
                pass
            continue

        generation_issues_text = ""
        if getattr(generated, "generation_issues", None):
            try:
                generation_issues_text = ";".join(str(issue) for issue in generated.generation_issues)
            except Exception:
                generation_issues_text = str(generated.generation_issues)

        if generation_issues_text:
            try:
                request = build_repair_request(
                    "code_generation_exception",
                    frontier,
                    exception_text=_bounded_text(generation_issues_text),
                )
                enqueue_repairs(request)
            except Exception:
                pass
            continue

        execution_result = None
        try:
            execution_result = execute_generated_code(generated, specification, frontier, limits)
        except Exception as exception:
            try:
                request = build_repair_request(
                    "execution_or_empty_frontier",
                    frontier,
                    exception_text=_exception_text(exception),
                )
                enqueue_repairs(request)
            except Exception:
                pass
            continue

        remaining_candidates = limits.max_verified_candidates - statistics["candidates_verified"]
        if remaining_candidates <= 0:
            return _exhausted_report(specification, statistics, "candidate_budget_exhausted")

        candidate_limit = min(limits.max_candidates_per_frontier, remaining_candidates)
        raw_candidates = getattr(execution_result, "candidates", None)
        candidates = _extract_candidates(raw_candidates, candidate_limit)

        if not candidates:
            try:
                exec_exc = getattr(execution_result, "exception_text", None)
                request = build_repair_request(
                    "no_candidate_returned",
                    frontier,
                    execution_result=execution_result,
                    exception_text=_bounded_text(exec_exc) if exec_exc else "",
                )
                enqueue_repairs(request)
            except Exception:
                pass
            continue

        for candidate in candidates:
            stop_reason = candidate_exhaustion_reason()
            if stop_reason:
                return _exhausted_report(specification, statistics, stop_reason)

            statistics["candidates_verified"] += 1

            try:
                verification = verify_candidate(specification, candidate)
            except Exception as exception:
                verification = VerificationResult(
                    False,
                    candidate,
                    (type(exception).__name__,),
                    {"exception": _exception_text(exception)},
                )

            if not getattr(verification, "passed", False):
                try:
                    request = build_repair_request(
                        "verification_rejection",
                        frontier,
                        verification_result=verification,
                        execution_result=execution_result,
                    )
                    enqueue_repairs(request)
                except Exception:
                    pass
                continue

            try:
                critique = critique_candidate(specification, candidate, verification, generated, frontier)
            except Exception as exception:
                try:
                    request = build_repair_request(
                        "critique_exception",
                        frontier,
                        verification_result=verification,
                        exception_text=_exception_text(exception),
                    )
                    enqueue_repairs(request)
                except Exception:
                    pass
                continue

            if not getattr(critique, "passed", False):
                try:
                    request = build_repair_request(
                        "critique_rejection",
                        frontier,
                        verification_result=verification,
                        critique_result=critique,
                        execution_result=execution_result,
                    )
                    enqueue_repairs(request)
                except Exception:
                    pass
                continue

            try:
                output = format_candidate(specification, candidate)
            except Exception as exception:
                try:
                    request = build_repair_request(
                        "format_exception",
                        frontier,
                        verification_result=verification,
                        critique_result=critique,
                        exception_text=_exception_text(exception),
                    )
                    enqueue_repairs(request)
                except Exception:
                    pass
                continue

            if output and isinstance(output, str) and output.strip():
                return output

            try:
                request = build_repair_request(
                    "format_exception",
                    frontier,
                    verification_result=verification,
                    critique_result=critique,
                    exception_text="format_candidate_returned_empty_output",
                )
                enqueue_repairs(request)
            except Exception:
                pass
