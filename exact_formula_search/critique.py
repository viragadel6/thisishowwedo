from __future__ import annotations

import re
from typing import Any

import sympy as sp

from .code_generation import validate_generated_source
from .models import Candidate, CritiqueIssue, CritiqueResult, Frontier, GeneratedCodeResult, ProblemKind, ProblemSpec, VerificationResult
from .symbolic_tools import (
    evaluate_group_word_by_postfix,
    exact_nonzero,
    exact_parse_expression,
    exact_zero,
    expression_domain_obligations,
    is_exact_algebraic_value,
)
from .verification import verify_candidate


def _issue(code: str, description: str, repair_hint: str) -> CritiqueIssue:
    return CritiqueIssue(code=code, description=description, severity="blocking", resolved=False, repair_hint=repair_hint)


def _contains_decimal_text(value: Any) -> bool:
    if isinstance(value, str):
        return re.search(r"(?<![A-Za-z_])\d+\.\d+", value) is not None
    if isinstance(value, dict):
        return any(_contains_decimal_text(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return any(_contains_decimal_text(item) for item in value)
    return False


def _independent_algebraic_recheck(specification: ProblemSpec, candidate: Candidate) -> bool:
    target = specification.algebraic_identity
    if target is None:
        return False
    if not candidate.assignments:
        return False
    substitutions: dict[sp.Symbol, sp.Expr] = {}
    for variable in target.variables:
        if variable not in candidate.assignments:
            return False
        value = exact_parse_expression(str(candidate.assignments[variable]))
        if not is_exact_algebraic_value(value):
            return False
        substitutions[sp.Symbol(variable)] = value
    left_text = target.left_source or target.left_expression
    right_text = target.right_source or target.right_expression
    try:
        left = exact_parse_expression(left_text, target.variables)
        right = exact_parse_expression(right_text, target.variables)
    except Exception:
        return False
    difference = sp.expand(left.subs(substitutions) - right.subs(substitutions))
    if difference.free_symbols:
        return False
    if difference.has(sp.Float):
        return False
    if difference == 0:
        return False
    if getattr(difference, "is_zero", None) is True:
        return False
    numerator, denominator = sp.together(difference).as_numer_denom()
    if exact_zero(numerator) or exact_zero(denominator):
        return False
    if not exact_nonzero(numerator):
        return False
    for source in (target.left_obligations, target.right_obligations):
        for text in source:
            try:
                for obligation in expression_domain_obligations(str(text), target.variables):
                    if not exact_nonzero(obligation.subs(substitutions)):
                        return False
            except Exception:
                return False
    return True


def _independent_planar_recheck(specification: ProblemSpec, candidate: Candidate) -> bool:
    if not candidate.formulas or not candidate.points:
        return False
    try:
        first = exact_parse_expression(str(candidate.formulas.get("F1", candidate.formulas.get("F₁", ""))), ("x", "y"))
        second = exact_parse_expression(str(candidate.formulas.get("F2", candidate.formulas.get("F₂", ""))), ("x", "y"))
        point_values = candidate.points.get("P")
        other_values = candidate.points.get("Q")
        if point_values is None or other_values is None or len(point_values) != 2 or len(other_values) != 2:
            return False
        point = tuple(exact_parse_expression(str(item)) for item in point_values)
        other = tuple(exact_parse_expression(str(item)) for item in other_values)
    except Exception:
        return False
    x_symbol, y_symbol = sp.symbols("x y")
    matrix = sp.Matrix(
        [
            [sp.diff(first, x_symbol), sp.diff(first, y_symbol)],
            [sp.diff(second, x_symbol), sp.diff(second, y_symbol)],
        ]
    )
    determinant = sp.expand(matrix.det())
    try:
        polynomial = sp.Poly(determinant, x_symbol, y_symbol, extension=True)
    except Exception:
        return False
    constant = sp.Integer(0)
    for monomial, coefficient in polynomial.terms():
        if monomial == (0, 0):
            constant = coefficient
        elif not exact_zero(coefficient):
            return False
    if not exact_nonzero(constant):
        return False
    left_substitutions = {x_symbol: point[0], y_symbol: point[1]}
    right_substitutions = {x_symbol: other[0], y_symbol: other[1]}
    if sp.expand(first.subs(left_substitutions) - first.subs(right_substitutions)) != 0:
        return False
    if sp.expand(second.subs(left_substitutions) - second.subs(right_substitutions)) != 0:
        return False
    if sp.expand(point[0] - other[0]) == 0 and sp.expand(point[1] - other[1]) == 0:
        return False
    if not exact_nonzero(point[0] - other[0]) and not exact_nonzero(point[1] - other[1]):
        return False
    for formula in (first, second):
        for obligation in expression_domain_obligations(sp.sstr(formula), ("x", "y")):
            for substitutions in (left_substitutions, right_substitutions):
                if not exact_nonzero(obligation.subs(substitutions)):
                    return False
    return True


def _independent_group_recheck(specification: ProblemSpec, candidate: Candidate) -> bool:
    target = specification.finite_group_identity
    if target is None:
        return False
    structures = dict(candidate.finite_structures)
    table = structures.get("operation_table")
    identity = structures.get("identity", 0)
    if table is None or not isinstance(identity, int) or isinstance(identity, bool):
        return False
    assignment: dict[str, int] = {}
    for variable in target.variables:
        value = candidate.assignments.get(variable)
        if not isinstance(value, int) or isinstance(value, bool):
            return False
        assignment[variable] = value
    rows = tuple(tuple(row) for row in table)
    try:
        left = evaluate_group_word_by_postfix(target.left_word, assignment, rows, identity)
        right = evaluate_group_word_by_postfix(target.right_word, assignment, rows, identity)
    except Exception:
        return False
    return left != right


def _independent_recheck(specification: ProblemSpec, candidate: Candidate) -> bool:
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        return _independent_planar_recheck(specification, candidate)
    if specification.kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
        return _independent_group_recheck(specification, candidate)
    return _independent_algebraic_recheck(specification, candidate)


def critique_candidate(
    specification: ProblemSpec,
    candidate: Candidate,
    verification: VerificationResult,
    generated: GeneratedCodeResult | None = None,
    frontier: Frontier | None = None,
) -> CritiqueResult:
    issues: list[CritiqueIssue] = []
    if not verification.passed:
        issues.append(_issue("verification_failed", "verification did not certify the candidate", "rerun with strengthened exact checks"))
    if candidate.problem_kind != specification.kind:
        issues.append(_issue("problem_kind_mismatch", "candidate kind does not match formalized target", "discard candidate and regenerate for the current target"))
    if frontier is not None and candidate.frontier_signature != frontier.unique_signature:
        issues.append(_issue("frontier_provenance_mismatch", "candidate frontier signature does not match current frontier", "rerun generated source from the current frontier"))
    if generated is not None:
        if candidate.source_fingerprint != generated.source_fingerprint:
            issues.append(_issue("source_fingerprint_mismatch", "candidate source fingerprint does not match generated source", "discard candidate and re-execute generated source"))
        if generated.generation_issues:
            issues.append(_issue("generation_issue_present", "code generation reported internal issues", "repair code generation parameters"))
        structural_issues = validate_generated_source(generated.source, generated.entry_function)
        if structural_issues:
            issues.append(_issue("generated_source_structure_invalid", "generated source failed structural validation", "regenerate source from the fixed template"))
    if (
        _contains_decimal_text(candidate.formulas)
        or _contains_decimal_text(candidate.points)
        or _contains_decimal_text(candidate.assignments)
        or _contains_decimal_text(candidate.finite_structures)
    ):
        issues.append(_issue("decimal_text_present", "candidate contains decimal text", "regenerate with exact rational or algebraic values"))
    artifacts = dict(verification.artifacts)
    if artifacts.get("no_numeric_certification") is not True:
        issues.append(_issue("numeric_certification_gap", "verification did not rule out numeric-only certification", "strengthen exact-domain verification"))
    if artifacts.get("denominator_status") is not True:
        issues.append(_issue("denominator_gap", "denominator obligations were not completely discharged", "add denominator nonzero obligations"))
    repeat = verify_candidate(specification, candidate)
    if not repeat.passed:
        issues.append(_issue("repeat_verification_failed", "deterministic rerun of verifier rejected candidate", "discard candidate and mutate frontier"))
    independent = _independent_recheck(specification, candidate)
    if not independent:
        issues.append(_issue("independent_recheck_failed", "independent recomputation of the certificate failed", "discard candidate and mutate frontier"))
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        if specification.planar_target is None:
            issues.append(_issue("target_missing", "planar target data is absent", "repair formalization"))
        if artifacts.get("independent_determinant_check") is not True:
            issues.append(_issue("single_determinant_path", "determinant was not certified by independent paths", "add monomial-coefficient determinant check"))
        if artifacts.get("independent_collision_check") is not True:
            issues.append(_issue("single_collision_path", "collision was not certified by independent paths", "add coefficient-dictionary evaluation check"))
        if artifacts.get("distinct_points") is not True:
            issues.append(_issue("distinctness_gap", "point distinctness was not proved exactly", "change point pattern or exact comparison"))
        if artifacts.get("domain_exclusions_respected") is not True:
            issues.append(_issue("domain_exclusion_gap", "point does not respect the domain exclusions of the components", "change point pattern or component domain"))
        if artifacts.get("determinant_nonzero") is not True or artifacts.get("nonconstant_coefficients_zero") is not True:
            issues.append(_issue("determinant_obligation_gap", "constant determinant obligations are incomplete", "repair determinant constraint route"))
        if artifacts.get("collision_differences_zero") is not True:
            issues.append(_issue("collision_obligation_gap", "collision obligations are incomplete", "repair collision equations"))
    elif specification.kind == ProblemKind.ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT:
        if artifacts.get("exact_inequality_check") is not True:
            issues.append(_issue("identity_inequality_gap", "identity inequality was not proved exactly", "change assignment search domain"))
        if artifacts.get("domain_exclusions_respected") is not True:
            issues.append(_issue("domain_exclusion_gap", "assignment hits an excluded pole of the original expression", "exclude assignments that zero a denominator"))
    elif specification.kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
        if artifacts.get("group_table_valid") is not True:
            issues.append(_issue("group_table_gap", "finite table was not certified as a group", "repair finite structure search"))
        if artifacts.get("word_inequality") is not True:
            issues.append(_issue("word_inequality_gap", "word inequality was not certified", "mutate group assignments or table family"))
        if artifacts.get("order_bound_respected") is not True:
            issues.append(_issue("group_order_bound_gap", "group order exceeds the requested bound", "respect the declared group order bound"))
        if artifacts.get("independent_word_evaluation") is not True:
            issues.append(_issue("single_word_evaluation_path", "group word was not evaluated by independent paths", "add a second group word evaluator"))
    unresolved = tuple(item for item in issues if not item.resolved)
    return CritiqueResult(
        passed=not unresolved,
        issues=tuple(issues),
        artifacts={"repeat_verification_passed": repeat.passed, "independent_recheck_passed": independent},
    )
