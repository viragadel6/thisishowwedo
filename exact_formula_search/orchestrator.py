from __future__ import annotations

import time
from collections import deque

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


def _symbolic_proof_report(specification) -> str:
    if specification.kind != ProblemKind.ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT:
        return ""
    target = specification.algebraic_identity
    if target is None:
        return ""
    try:
        left = exact_parse_expression(target.left_expression, target.variables)
        right = exact_parse_expression(target.right_expression, target.variables)
    except Exception:
        return ""
    if exact_zero(left - right):
        return "\n".join(
            (
                "no counterassignment exists",
                "kind: " + specification.kind.value,
                "left: " + str(target.left_expression),
                "right: " + str(target.right_expression),
                "reason: identity_holds_symbolically",
            )
        )
    return ""


def _exhausted_report(specification, statistics: dict[str, int], reason: str) -> str:
    lines = [
        "no counterexample found within the search budget",
        "kind: " + specification.kind.value,
        "frontiers_examined: " + str(statistics.get("frontiers_examined", 0)),
        "candidates_verified: " + str(statistics.get("candidates_verified", 0)),
        "mutation_rounds: " + str(statistics.get("mutation_rounds", 0)),
        "reason: " + reason,
    ]
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        lines.append("note: the two dimensional case of the Jacobian conjecture remains open")
    return "\n".join(lines)


def run(raw_text: str, budget: SearchBudget | None = None) -> str:
    limits = budget if budget is not None else SearchBudget()
    specification = formalize_request(raw_text)
    proof = _symbolic_proof_report(specification)
    if proof:
        return proof
    active: deque[Frontier] = deque()
    known_signatures: set[str] = set()
    last_frontier: Frontier | None = None
    statistics = {"frontiers_examined": 0, "candidates_verified": 0, "mutation_rounds": 0}
    deadline = time.monotonic() + max(0.001, limits.max_seconds)

    def add_frontiers(frontiers: tuple[Frontier, ...]) -> None:
        for frontier in frontiers:
            if frontier.unique_signature not in known_signatures:
                known_signatures.add(frontier.unique_signature)
                active.append(frontier)

    def budget_exhausted() -> bool:
        return (
            statistics["frontiers_examined"] >= limits.max_frontier_visits
            or statistics["candidates_verified"] >= limits.max_verified_candidates
            or statistics["mutation_rounds"] >= limits.max_mutation_rounds
            or time.monotonic() >= deadline
        )

    add_frontiers(initial_frontiers(specification))
    while True:
        if budget_exhausted():
            return _exhausted_report(specification, statistics, "search_budget_exhausted")
        if not active:
            statistics["mutation_rounds"] += 1
            add_frontiers(mutate_frontier(last_frontier, known_signatures, 5, "active_queue_empty", specification.kind))
            if not active:
                add_frontiers(mutate_frontier(None, known_signatures, 5, "active_queue_empty_root", specification.kind))
            if not active:
                return _exhausted_report(specification, statistics, "frontier_space_exhausted")
        frontier = active.popleft()
        last_frontier = frontier
        statistics["frontiers_examined"] += 1
        try:
            generated = generate_search_code(specification, frontier, limits)
        except Exception as exception:
            request = build_repair_request("code_generation_exception", frontier, exception_text=repr(exception)[:500])
            add_frontiers(repair_frontiers(specification, request, known_signatures, 5, limits))
            continue
        if generated.generation_issues:
            request = build_repair_request("code_generation_exception", frontier, exception_text=";".join(generated.generation_issues))
            add_frontiers(repair_frontiers(specification, request, known_signatures, 5, limits))
            continue
        try:
            execution_result = execute_generated_code(generated, specification, frontier, limits)
        except Exception as exception:
            request = build_repair_request("execution_or_empty_frontier", frontier, exception_text=repr(exception)[:500])
            add_frontiers(repair_frontiers(specification, request, known_signatures, 5, limits))
            continue
        if not execution_result.candidates:
            request = build_repair_request(
                "no_candidate_returned",
                frontier,
                execution_result=execution_result,
                exception_text=execution_result.exception_text,
            )
            add_frontiers(repair_frontiers(specification, request, known_signatures, 5, limits))
            continue
        for candidate in execution_result.candidates[: max(1, limits.max_candidates_per_frontier)]:
            statistics["candidates_verified"] += 1
            if statistics["candidates_verified"] > limits.max_verified_candidates:
                return _exhausted_report(specification, statistics, "candidate_budget_exhausted")
            try:
                verification = verify_candidate(specification, candidate)
            except Exception as exception:
                verification = VerificationResult(False, candidate, (type(exception).__name__,), {"exception": repr(exception)[:500]})
            if not verification.passed:
                request = build_repair_request("verification_rejection", frontier, verification_result=verification, execution_result=execution_result)
                add_frontiers(repair_frontiers(specification, request, known_signatures, 5, limits))
                continue
            try:
                critique = critique_candidate(specification, candidate, verification, generated, frontier)
            except Exception as exception:
                request = build_repair_request("critique_exception", frontier, verification_result=verification, exception_text=repr(exception)[:500])
                add_frontiers(repair_frontiers(specification, request, known_signatures, 5, limits))
                continue
            if not critique.passed:
                request = build_repair_request("critique_rejection", frontier, verification_result=verification, critique_result=critique, execution_result=execution_result)
                add_frontiers(repair_frontiers(specification, request, known_signatures, 5, limits))
                continue
            try:
                output = format_candidate(specification, candidate)
            except Exception as exception:
                request = build_repair_request("format_exception", frontier, verification_result=verification, critique_result=critique, exception_text=repr(exception)[:500])
                add_frontiers(repair_frontiers(specification, request, known_signatures, 5, limits))
                continue
            if output:
                return output
