from __future__ import annotations

from typing import Any, Mapping, Sequence

import sympy as sp

from .models import Candidate, ProblemKind, ProblemSpec, VerificationResult
from .symbolic_tools import (
    check_denominator_nonzero_obligations,
    check_obligations_at,
    coefficient_domain_valid,
    compare_algebraic_coordinates,
    derivative_matrix_determinant,
    differential_determinant_from_expressions,
    evaluate_coefficient_dictionary,
    evaluate_group_word,
    evaluate_group_word_by_postfix,
    evaluate_polynomial,
    exact_nonzero,
    exact_parse_expression,
    exact_zero,
    expression_domain_obligations,
    is_exact_algebraic_value,
    polynomial_coefficient_dictionary,
)


def verify_candidate(specification: ProblemSpec, candidate: Candidate) -> VerificationResult:
    try:
        if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
            return _verify_planar(specification, candidate)
        if specification.kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
            return _verify_finite_group(specification, candidate)
        return _verify_algebraic_identity(specification, candidate)
    except Exception as exception:
        return VerificationResult(
            False,
            candidate,
            (type(exception).__name__,),
            {"exception": repr(exception)[:500], "no_numeric_certification": False, "denominator_status": False},
        )


def _formula(candidate: Candidate, names: Sequence[str]) -> str:
    for name in names:
        if name in candidate.formulas:
            return str(candidate.formulas[name])
    raise ValueError("missing_formula")


def _point(candidate: Candidate, name: str) -> tuple[str, str]:
    value = candidate.points.get(name)
    if value is None or len(value) != 2:
        raise ValueError("missing_point")
    return str(value[0]), str(value[1])


def _formula_obligations(candidate: Candidate, text: str) -> tuple[sp.Expr, ...]:
    collected: list[sp.Expr] = []
    try:
        for obligation in expression_domain_obligations(text, ("x", "y")):
            collected.append(obligation)
    except Exception:
        pass
    recorded = candidate.exact_derivation_artifacts.get("domain_obligations") if isinstance(candidate.exact_derivation_artifacts, Mapping) else None
    if recorded is not None:
        for item in recorded:
            try:
                collected.append(exact_parse_expression(str(item), ("x", "y")))
            except Exception:
                continue
    return tuple(collected)


def _verify_planar(specification: ProblemSpec, candidate: Candidate) -> VerificationResult:
    issues: list[str] = []
    x_symbol, y_symbol = sp.symbols("x y")
    first_text = _formula(candidate, ("F1", "F₁", "first"))
    second_text = _formula(candidate, ("F2", "F₂", "second"))
    first = exact_parse_expression(first_text, ("x", "y"))
    second = exact_parse_expression(second_text, ("x", "y"))
    point_text = _point(candidate, "P")
    other_text = _point(candidate, "Q")
    point = tuple(exact_parse_expression(item) for item in point_text)
    other = tuple(exact_parse_expression(item) for item in other_text)
    if len(point) != 2 or len(other) != 2:
        return VerificationResult(False, candidate, ("point_dimension_mismatch",))
    if first.has(sp.Float) or second.has(sp.Float) or any(item.has(sp.Float) for item in point + other):
        issues.append("floating_number_present")
    if not check_denominator_nonzero_obligations((first, second) + point + other):
        issues.append("denominator_obligation_failed")
    for coordinate in point + other:
        if not is_exact_algebraic_value(coordinate):
            issues.append("invalid_point_domain")
    obligations = _formula_obligations(candidate, first_text) + _formula_obligations(candidate, second_text)
    for label, values in (("P", point), ("Q", other)):
        if not check_obligations_at(obligations, {x_symbol: values[0], y_symbol: values[1]}):
            issues.append("domain_exclusion_violated_at_" + label)
    try:
        first_coefficients = polynomial_coefficient_dictionary(first, (x_symbol, y_symbol))
        second_coefficients = polynomial_coefficient_dictionary(second, (x_symbol, y_symbol))
    except Exception as exception:
        issues.append("non_polynomial_component:" + type(exception).__name__)
        first_coefficients = {}
        second_coefficients = {}
    for coefficient in tuple(first_coefficients.values()) + tuple(second_coefficients.values()):
        if not coefficient_domain_valid(coefficient):
            issues.append("invalid_coefficient_domain")
    determinant_sympy = derivative_matrix_determinant(first, second, (x_symbol, y_symbol))
    try:
        determinant_independent = differential_determinant_from_expressions(first, second, (x_symbol, y_symbol))
    except Exception as exception:
        issues.append("independent_determinant_unavailable:" + type(exception).__name__)
        determinant_independent = determinant_sympy
    if not exact_zero(determinant_sympy - determinant_independent):
        issues.append("determinant_paths_disagree")
    determinant_coefficients = polynomial_coefficient_dictionary(determinant_sympy, (x_symbol, y_symbol))
    constant = determinant_coefficients.get((0, 0), sp.Integer(0))
    for monomial, coefficient in determinant_coefficients.items():
        if monomial != (0, 0) and not exact_zero(coefficient):
            issues.append("nonconstant_determinant_coefficient")
    if not exact_nonzero(constant):
        issues.append("zero_or_undecided_constant_determinant")
    first_at_point = evaluate_polynomial(first, {x_symbol: point[0], y_symbol: point[1]})
    first_at_other = evaluate_polynomial(first, {x_symbol: other[0], y_symbol: other[1]})
    second_at_point = evaluate_polynomial(second, {x_symbol: point[0], y_symbol: point[1]})
    second_at_other = evaluate_polynomial(second, {x_symbol: other[0], y_symbol: other[1]})
    first_independent_point = evaluate_coefficient_dictionary(first_coefficients, point)
    first_independent_other = evaluate_coefficient_dictionary(first_coefficients, other)
    second_independent_point = evaluate_coefficient_dictionary(second_coefficients, point)
    second_independent_other = evaluate_coefficient_dictionary(second_coefficients, other)
    if not exact_zero(first_at_point - first_independent_point):
        issues.append("first_component_point_evaluation_paths_disagree")
    if not exact_zero(first_at_other - first_independent_other):
        issues.append("first_component_other_evaluation_paths_disagree")
    if not exact_zero(second_at_point - second_independent_point):
        issues.append("second_component_point_evaluation_paths_disagree")
    if not exact_zero(second_at_other - second_independent_other):
        issues.append("second_component_other_evaluation_paths_disagree")
    if not exact_zero(first_at_point - first_at_other):
        issues.append("first_component_collision_failed")
    if not exact_zero(second_at_point - second_at_other):
        issues.append("second_component_collision_failed")
    _, distinct = compare_algebraic_coordinates(point, other)
    if not distinct:
        issues.append("points_not_proved_distinct")
    if not check_denominator_nonzero_obligations((first_at_point, first_at_other, second_at_point, second_at_other)):
        issues.append("evaluation_denominator_obligation_failed")
    artifacts = {
        "sympy_determinant": str(determinant_sympy),
        "coefficient_determinant": str(determinant_independent),
        "determinant_constant": str(constant),
        "nonconstant_coefficients_zero": "nonconstant_determinant_coefficient" not in issues,
        "determinant_nonzero": "zero_or_undecided_constant_determinant" not in issues,
        "collision_differences_zero": "first_component_collision_failed" not in issues and "second_component_collision_failed" not in issues,
        "distinct_points": distinct,
        "denominator_status": "denominator_obligation_failed" not in issues and "evaluation_denominator_obligation_failed" not in issues,
        "domain_exclusions_respected": not any(item.startswith("domain_exclusion_violated") for item in issues),
        "no_numeric_certification": "floating_number_present" not in issues,
        "independent_determinant_check": "determinant_paths_disagree" not in issues,
        "independent_collision_check": all("evaluation_paths_disagree" not in issue for issue in issues),
        "formal_variables": specification.variables,
    }
    return VerificationResult(not issues, candidate, tuple(issues), artifacts)


def _verify_algebraic_identity(specification: ProblemSpec, candidate: Candidate) -> VerificationResult:
    target = specification.algebraic_identity
    if target is None:
        return VerificationResult(False, candidate, ("missing_algebraic_target",))
    issues: list[str] = []
    variables = tuple(target.variables)
    left = exact_parse_expression(target.left_expression, variables)
    right = exact_parse_expression(target.right_expression, variables)
    substitutions: dict[sp.Symbol, sp.Expr] = {}
    for variable in variables:
        if variable not in candidate.assignments:
            issues.append("missing_assignment")
            continue
        value = exact_parse_expression(str(candidate.assignments[variable]))
        if not is_exact_algebraic_value(value):
            issues.append("invalid_assignment_domain")
        substitutions[sp.Symbol(variable)] = value
    left_value = left.subs(substitutions)
    right_value = right.subs(substitutions)
    if left.has(sp.Float) or right.has(sp.Float) or any(value.has(sp.Float) for value in substitutions.values()):
        issues.append("floating_number_present")
    if not check_denominator_nonzero_obligations(tuple(substitutions.values()) + (left_value, right_value)):
        issues.append("denominator_obligation_failed")
    obligations: list[sp.Expr] = []
    for source in (target.left_obligations, target.right_obligations):
        for text in source:
            try:
                obligations.append(exact_parse_expression(str(text), variables))
            except Exception:
                issues.append("unparsable_domain_obligation")
    if obligations and not check_obligations_at(obligations, substitutions):
        issues.append("domain_exclusion_violated")
    if not exact_nonzero(left_value - right_value):
        issues.append("identity_not_refuted")
    artifacts = {
        "left_value": str(left_value),
        "right_value": str(right_value),
        "exact_inequality_check": "identity_not_refuted" not in issues,
        "denominator_status": "denominator_obligation_failed" not in issues,
        "domain_exclusions_respected": "domain_exclusion_violated" not in issues,
        "no_numeric_certification": "floating_number_present" not in issues,
    }
    return VerificationResult(not issues, candidate, tuple(issues), artifacts)


def _inverse_element(table: Sequence[Sequence[int]], identity: int, value: int) -> int | None:
    for candidate in range(len(table)):
        if table[value][candidate] == identity and table[candidate][value] == identity:
            return candidate
    return None


def _is_strict_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _verify_group_table(table: Sequence[Sequence[int]], identity: int) -> tuple[str, ...]:
    issues: list[str] = []
    order = len(table)
    if order == 0:
        return ("empty_table",)
    if not _is_strict_integer(identity):
        return ("non_integer_identity",)
    if identity < 0 or identity >= order:
        issues.append("invalid_identity")
    for row in table:
        if len(row) != order:
            issues.append("non_square_table")
    if issues:
        return tuple(dict.fromkeys(issues))
    for row in table:
        for value in row:
            if not _is_strict_integer(value) or value < 0 or value >= order:
                issues.append("closure_failed")
    if "closure_failed" in issues:
        return tuple(dict.fromkeys(issues))
    for a in range(order):
        for b in range(order):
            for c in range(order):
                if table[table[a][b]][c] != table[a][table[b][c]]:
                    issues.append("associativity_failed")
                    return tuple(dict.fromkeys(issues))
    for element in range(order):
        if table[identity][element] != element or table[element][identity] != element:
            issues.append("identity_law_failed")
        if _inverse_element(table, identity, element) is None:
            issues.append("inverse_law_failed")
    return tuple(dict.fromkeys(issues))


def _verify_finite_group(specification: ProblemSpec, candidate: Candidate) -> VerificationResult:
    target = specification.finite_group_identity
    if target is None:
        return VerificationResult(False, candidate, ("missing_group_target",))
    structures = dict(candidate.finite_structures)
    raw_table = structures.get("operation_table")
    raw_identity = structures.get("identity", 0)
    if raw_table is None:
        return VerificationResult(False, candidate, ("missing_operation_table",))
    if not _is_strict_integer(raw_identity):
        return VerificationResult(False, candidate, ("non_integer_identity",), {"group_table_valid": False, "word_inequality": False, "denominator_status": True, "no_numeric_certification": True})
    identity = int(raw_identity)
    rows: list[tuple[int, ...]] = []
    malformed = False
    for row in raw_table:
        if isinstance(row, (str, bytes)) or not hasattr(row, "__iter__"):
            malformed = True
            break
        entries = tuple(row)
        for entry in entries:
            if not _is_strict_integer(entry):
                malformed = True
                break
        if malformed:
            break
        rows.append(entries)
    if malformed:
        return VerificationResult(False, candidate, ("non_integer_table_entry",), {"group_table_valid": False, "word_inequality": False, "denominator_status": True, "no_numeric_certification": True})
    table = tuple(rows)
    issues = list(_verify_group_table(table, identity))
    order = len(table)
    if order > int(target.max_order):
        issues.append("group_order_exceeds_bound")
    assignment: dict[str, int] = {}
    for variable in target.variables:
        if variable not in candidate.assignments:
            issues.append("missing_assignment")
            continue
        value = candidate.assignments[variable]
        if not _is_strict_integer(value):
            issues.append("non_integer_assignment")
            continue
        if int(value) < 0 or int(value) >= order:
            issues.append("assignment_out_of_range")
            continue
        assignment[variable] = int(value)
    left_value = None
    right_value = None
    word_issues: list[str] = []
    if not any(item in issues for item in ("missing_assignment", "non_integer_assignment", "assignment_out_of_range", "empty_table", "non_square_table", "closure_failed", "non_integer_table_entry", "non_integer_identity")):
        try:
            left_value = evaluate_group_word(target.left_word, assignment, table, identity)
            right_value = evaluate_group_word(target.right_word, assignment, table, identity)
            independent_left = evaluate_group_word_by_postfix(target.left_word, assignment, table, identity)
            independent_right = evaluate_group_word_by_postfix(target.right_word, assignment, table, identity)
            if independent_left != left_value or independent_right != right_value:
                word_issues.append("word_evaluation_paths_disagree")
            if left_value == right_value:
                word_issues.append("word_identity_not_refuted")
        except Exception as exception:
            word_issues.append(type(exception).__name__)
            left_value = None
            right_value = None
    issues.extend(word_issues)
    table_issue_codes = (
        "empty_table",
        "non_integer_identity",
        "invalid_identity",
        "non_square_table",
        "closure_failed",
        "associativity_failed",
        "identity_law_failed",
        "inverse_law_failed",
        "non_integer_table_entry",
        "group_order_exceeds_bound",
    )
    artifacts = {
        "left_value": left_value,
        "right_value": right_value,
        "group_table_valid": not any(item in issues for item in table_issue_codes),
        "word_inequality": left_value is not None and right_value is not None and "word_identity_not_refuted" not in issues,
        "independent_word_evaluation": "word_evaluation_paths_disagree" not in issues,
        "denominator_status": True,
        "no_numeric_certification": True,
        "order_bound_respected": "group_order_exceeds_bound" not in issues,
        "group_order": order,
    }
    return VerificationResult(not issues, candidate, tuple(issues), artifacts)
