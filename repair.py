from __future__ import annotations

from .frontiers import initial_frontiers, mutate_frontier
from .models import CritiqueResult, Frontier, ProblemSpec, RepairRequest, VerificationResult


def build_repair_request(
    reason: str,
    source_frontier: Frontier | None = None,
    verification_result: VerificationResult | None = None,
    critique_result: CritiqueResult | None = None,
    execution_result: object | None = None,
    exception_text: str = "",
) -> RepairRequest:
    return RepairRequest(
        reason=reason,
        source_frontier=source_frontier,
        verification_result=verification_result,
        critique_result=critique_result,
        execution_result=execution_result,
        exception_text=exception_text,
    )


def repair_frontiers(
    specification: ProblemSpec,
    request: RepairRequest,
    known_signatures: set[str],
    minimum: int = 5,
) -> tuple[Frontier, ...]:
    base = request.source_frontier
    produced: list[Frontier] = []
    produced.extend(mutate_frontier(base, known_signatures, max(minimum, 5), request.reason))
    if len(produced) >= minimum:
        return tuple(produced[: max(minimum, 5)])
    for frontier in initial_frontiers(specification):
        if frontier.unique_signature not in known_signatures:
            produced.append(frontier)
            if len(produced) >= minimum:
                return tuple(produced)
        extra = mutate_frontier(frontier, known_signatures | {item.unique_signature for item in produced}, minimum, request.reason)
        produced.extend(extra)
        if len(produced) >= minimum:
            return tuple(produced[:minimum])
    produced.extend(mutate_frontier(None, known_signatures | {item.unique_signature for item in produced}, minimum, request.reason))
    return tuple(produced[: max(minimum, 5)])
