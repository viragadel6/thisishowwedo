from __future__ import annotations

from typing import Iterable

from .frontiers import initial_frontiers, mutate_frontier
from .models import CritiqueResult, Frontier, ProblemKind, ProblemSpec, RepairRequest, SearchBudget, VerificationResult

_ISSUE_ACTIONS = {
    "denominator_obligation_failed": "add_denominator_equations",
    "evaluation_denominator_obligation_failed": "add_denominator_equations",
    "domain_exclusion_violated": "add_denominator_equations",
    "domain_exclusion_violated_at_P": "add_denominator_equations",
    "domain_exclusion_violated_at_Q": "add_denominator_equations",
    "unparsable_domain_obligation": "add_denominator_equations",
    "identity_not_refuted": "expand_coefficient_extent",
    "invalid_assignment_domain": "strengthen_exact_domain_conversion",
    "missing_assignment": "expand_coefficient_extent",
    "nonconstant_determinant_coefficient": "change_support_sets",
    "zero_or_undecided_constant_determinant": "expand_coefficient_extent",
    "points_not_proved_distinct": "change_collision_point_pattern",
    "invalid_point_domain": "change_collision_point_pattern",
    "first_component_collision_failed": "change_collision_point_pattern",
    "second_component_collision_failed": "change_collision_point_pattern",
    "determinant_paths_disagree": "add_independent_exact_checks",
    "first_component_point_evaluation_paths_disagree": "add_independent_exact_checks",
    "second_component_point_evaluation_paths_disagree": "add_independent_exact_checks",
    "invalid_coefficient_domain": "strengthen_exact_domain_conversion",
    "non_polynomial_component": "change_support_sets",
    "word_identity_not_refuted": "expand_group_order",
    "no_countermodel_in_frontier": "expand_group_order",
    "group_order_exceeds_bound": "change_support_sets",
    "associativity_failed": "change_support_sets",
    "closure_failed": "change_support_sets",
    "non_square_table": "change_support_sets",
    "empty_table": "expand_group_order",
    "missing_operation_table": "expand_group_order",
    "missing_group_target": "expand_group_order",
    "missing_algebraic_target": "change_elimination_order",
    "no_candidate_in_frontier": "expand_degree_extent",
    "no_counterassignment_in_frontier": "expand_coefficient_extent",
    "empty_result": "expand_degree_extent",
    "invalid_generated_result": "add_independent_exact_checks",
    "generated_execution_exception": "switch_solver_route",
    "generated_execution_timeout": "switch_solver_route",
    "generated_execution_crashed": "switch_solver_route",
    "code_generation_exception": "add_independent_exact_checks",
    "provenance_problem_kind_mismatch": "add_independent_exact_checks",
    "provenance_frontier_signature_mismatch": "add_independent_exact_checks",
    "provenance_source_fingerprint_mismatch": "add_independent_exact_checks",
}

_CRITIQUE_ACTIONS = {
    "verification_failed": "add_independent_exact_checks",
    "problem_kind_mismatch": "change_elimination_order",
    "frontier_provenance_mismatch": "add_independent_exact_checks",
    "source_fingerprint_mismatch": "add_independent_exact_checks",
    "generation_issue_present": "add_independent_exact_checks",
    "generated_source_structure_invalid": "add_independent_exact_checks",
    "decimal_text_present": "strengthen_exact_domain_conversion",
    "numeric_certification_gap": "strengthen_exact_domain_conversion",
    "denominator_gap": "add_denominator_equations",
    "repeat_verification_failed": "add_independent_exact_checks",
    "independent_recheck_failed": "add_independent_exact_checks",
    "target_missing": "change_elimination_order",
    "single_determinant_path": "add_independent_exact_checks",
    "single_collision_path": "add_independent_exact_checks",
    "distinctness_gap": "change_collision_point_pattern",
    "domain_exclusion_gap": "add_denominator_equations",
    "determinant_obligation_gap": "change_support_sets",
    "collision_obligation_gap": "change_collision_point_pattern",
    "identity_inequality_gap": "expand_coefficient_extent",
    "group_table_gap": "change_support_sets",
    "word_inequality_gap": "expand_group_order",
    "group_order_bound_gap": "change_support_sets",
    "single_word_evaluation_path": "add_independent_exact_checks",
}

_REASON_ACTIONS = {
    "code_generation_exception": "add_independent_exact_checks",
    "execution_or_empty_frontier": "switch_solver_route",
    "no_candidate_returned": "expand_degree_extent",
    "verification_rejection": "add_denominator_equations",
    "critique_exception": "add_independent_exact_checks",
    "critique_rejection": "add_independent_exact_checks",
    "format_exception": "add_independent_exact_checks",
    "active_queue_empty": "expand_degree_extent",
    "active_queue_empty_root": "change_elimination_order",
}


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


def _execution_failure_reasons(execution_result: object | None) -> tuple[str, ...]:
    if execution_result is None:
        return ()
    reasons = getattr(execution_result, "failure_reasons", None)
    if reasons is None:
        return ()
    return tuple(str(item) for item in reasons)


def _actions_for_request(request: RepairRequest) -> tuple[str, ...]:
    actions: list[str] = []

    def add(action: str) -> None:
        if action and action not in actions:
            actions.append(action)

    if request.verification_result is not None:
        for issue in request.verification_result.issues:
            add(_ISSUE_ACTIONS.get(str(issue).split(":")[0]))
    if request.critique_result is not None:
        for issue in request.critique_result.issues:
            add(_CRITIQUE_ACTIONS.get(str(getattr(issue, "code", ""))))
    for failure in _execution_failure_reasons(request.execution_result):
        add(_ISSUE_ACTIONS.get(str(failure).split(":")[0]))
    add(_REASON_ACTIONS.get(str(request.reason)))
    if request.exception_text:
        add("add_independent_exact_checks")
    if not actions:
        add("change_elimination_order")
    return tuple(actions)


def repair_frontiers(
    specification: ProblemSpec,
    request: RepairRequest,
    known_signatures: set[str] | Iterable[str],
    minimum: int = 5,
    limits: SearchBudget | None = None,
) -> tuple[Frontier, ...]:
    target = max(1, int(minimum))
    base = request.source_frontier
    actions = _actions_for_request(request)
    kind: ProblemKind = specification.kind
    seen = set(known_signatures)
    produced: list[Frontier] = []

    def absorb(frontiers: Iterable[Frontier]) -> None:
        for frontier in frontiers:
            if frontier.unique_signature in seen:
                continue
            seen.add(frontier.unique_signature)
            produced.append(frontier)

    if base is not None:
        absorb(mutate_frontier(base, seen, target, request.reason, kind, actions))
    if len(produced) < target:
        starting = initial_frontiers(specification)
        for frontier in starting:
            if len(produced) >= target:
                break
            if frontier.unique_signature in seen:
                continue
            seen.add(frontier.unique_signature)
            produced.append(frontier)
        for frontier in starting:
            if len(produced) >= target:
                break
            absorb(mutate_frontier(frontier, seen, target - len(produced), request.reason, kind, actions))
    if len(produced) < target:
        absorb(mutate_frontier(None, seen, target - len(produced), request.reason, kind, actions))
    return tuple(produced)
