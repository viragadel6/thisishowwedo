from __future__ import annotations

from collections import deque

from .code_generation import generate_search_code
from .critique import critique_candidate
from .execution import execute_generated_code
from .formalization import formalize_request
from .frontiers import initial_frontiers, mutate_frontier
from .models import Frontier, VerificationResult
from .output_format import format_candidate
from .repair import build_repair_request, repair_frontiers
from .verification import verify_candidate


def run(raw_text: str) -> str:
    specification = formalize_request(raw_text)
    active: deque[Frontier] = deque()
    known_signatures: set[str] = set()
    last_frontier: Frontier | None = None

    def add_frontiers(frontiers: tuple[Frontier, ...]) -> None:
        for frontier in frontiers:
            if frontier.unique_signature not in known_signatures:
                known_signatures.add(frontier.unique_signature)
                active.append(frontier)

    add_frontiers(initial_frontiers(specification))
    while True:
        if not active:
            add_frontiers(mutate_frontier(last_frontier, known_signatures, 5, "active_queue_empty"))
            if not active:
                add_frontiers(mutate_frontier(None, known_signatures, 5, "active_queue_empty_root"))
        frontier = active.popleft()
        last_frontier = frontier
        try:
            generated = generate_search_code(specification, frontier)
        except Exception as exception:
            request = build_repair_request("code_generation_exception", frontier, exception_text=repr(exception)[:500])
            add_frontiers(repair_frontiers(specification, request, known_signatures, 5))
            continue
        execution_result = execute_generated_code(generated, specification, frontier)
        if execution_result.failure_reasons:
            request = build_repair_request("execution_or_empty_frontier", frontier, execution_result=execution_result, exception_text=execution_result.exception_text)
            add_frontiers(repair_frontiers(specification, request, known_signatures, 5))
        if not execution_result.candidates:
            request = build_repair_request("no_candidate_returned", frontier, execution_result=execution_result)
            add_frontiers(repair_frontiers(specification, request, known_signatures, 5))
            continue
        for candidate in execution_result.candidates:
            try:
                verification = verify_candidate(specification, candidate)
            except Exception as exception:
                verification = VerificationResult(False, candidate, (type(exception).__name__,), {"exception": repr(exception)[:500]})
            if not verification.passed:
                request = build_repair_request("verification_rejection", frontier, verification_result=verification, execution_result=execution_result)
                add_frontiers(repair_frontiers(specification, request, known_signatures, 5))
                continue
            try:
                critique = critique_candidate(specification, candidate, verification, generated, frontier)
            except Exception as exception:
                request = build_repair_request("critique_exception", frontier, verification_result=verification, exception_text=repr(exception)[:500])
                add_frontiers(repair_frontiers(specification, request, known_signatures, 5))
                continue
            if not critique.passed:
                request = build_repair_request("critique_rejection", frontier, verification_result=verification, critique_result=critique, execution_result=execution_result)
                add_frontiers(repair_frontiers(specification, request, known_signatures, 5))
                continue
            try:
                output = format_candidate(specification, candidate)
            except Exception as exception:
                request = build_repair_request("format_exception", frontier, verification_result=verification, critique_result=critique, exception_text=repr(exception)[:500])
                add_frontiers(repair_frontiers(specification, request, known_signatures, 5))
                continue
            if output:
                return output
