from __future__ import annotations

from typing import Any, Mapping, Sequence

import sympy as sp

from .models import Candidate, ProblemKind, ProblemSpec, VerificationResult
from .symbolic_tools import (
    check_denominator_nonzero_obligations,
    coefficient_domain_valid,
    compare_algebraic_coordinates,
    differential_determinant_from_expressions,
    derivative_matrix_determinant,
    evaluate_coefficient_dictionary,
    evaluate_polynomial,
    exact_nonzero,
    exact_parse_expression,
    exact_zero,
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
        return VerificationResult(False, candidate, (type(exception).__name__,), {"exception": repr(exception)[:500]})


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


def _verify_planar(specification: ProblemSpec, candidate: Candidate) -> VerificationResult:
    issues: list[str] = []
    x_symbol, y_symbol = sp.symbols("x y")
    first = exact_parse_expression(_formula(candidate, ("F1", "F₁", "first")), ("x", "y"))
    second = exact_parse_expression(_formula(candidate, ("F2", "F₂", "second")), ("x", "y"))
    point_text = _point(candidate, "P")
    other_text = _point(candidate, "Q")
    point = tuple(exact_parse_expression(item) for item in point_text)
    other = tuple(exact_parse_expression(item) for item in other_text)
    if first.has(sp.Float) or second.has(sp.Float) or any(item.has(sp.Float) for item in point + other):
        issues.append("floating_number_present")
    if not check_denominator_nonzero_obligations((first, second) + point + other):
        issues.append("denominator_obligation_failed")
    for coordinate in point + other:
        if not is_exact_algebraic_value(coordinate):
            issues.append("invalid_point_domain")
    first_coefficients = polynomial_coefficient_dictionary(first, (x_symbol, y_symbol))
    second_coefficients = polynomial_coefficient_dictionary(second, (x_symbol, y_symbol))
    for coefficient in tuple(first_coefficients.values()) + tuple(second_coefficients.values()):
        if not coefficient_domain_valid(coefficient):
            issues.append("invalid_coefficient_domain")
    determinant_sympy = derivative_matrix_determinant(first, second, (x_symbol, y_symbol))
    determinant_independent = differential_determinant_from_expressions(first, second, (x_symbol, y_symbol))
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
    if not exact_nonzero(left_value - right_value):
        issues.append("identity_not_refuted")
    artifacts = {
        "left_value": str(left_value),
        "right_value": str(right_value),
        "exact_inequality_check": "identity_not_refuted" not in issues,
        "denominator_status": "denominator_obligation_failed" not in issues,
        "no_numeric_certification": "floating_number_present" not in issues,
    }
    return VerificationResult(not issues, candidate, tuple(issues), artifacts)


def _inverse_element(table: Sequence[Sequence[int]], identity: int, value: int) -> int | None:
    for candidate in range(len(table)):
        if table[value][candidate] == identity and table[candidate][value] == identity:
            return candidate
    return None


def _tokenize_word(word: str, variables: Sequence[str]) -> tuple[str, ...]:
    text = word.replace("⁻¹", "^-1").replace("−1", "-1")
    tokens: list[str] = []
    index = 0
    variable_set = {item.lower() for item in variables}
    while index < len(text):
        if text.startswith("^-1", index):
            tokens.append("INV")
            index += 3
        elif text[index] in ("'", "’"):
            tokens.append("INV")
            index += 1
        elif text[index] in ("*", "·", "(", ")"):
            tokens.append(text[index])
            index += 1
        elif text[index].isspace():
            index += 1
        elif text[index].isalnum() or text[index] == "_":
            end = index + 1
            while end < len(text) and (text[end].isalnum() or text[end] == "_"):
                end += 1
            run = text[index:end]
            lower = run.lower()
            if lower in ("e", "id", "identity", "1"):
                tokens.append("e")
            elif lower in variable_set:
                tokens.append(lower)
            else:
                for character in run:
                    if character.lower() in variable_set:
                        tokens.append(character.lower())
            index = end
        else:
            index += 1
    return tuple(tokens)


def _evaluate_word(word: str, assignment: Mapping[str, int], table: Sequence[Sequence[int]], identity: int) -> int:
    tokens = _tokenize_word(word, tuple(assignment))
    index = 0

    def parse_product() -> int:
        nonlocal index
        result = identity
        while index < len(tokens) and tokens[index] != ")":
            if tokens[index] in ("*", "·"):
                index += 1
                continue
            value = parse_factor()
            result = table[result][value]
        return result

    def parse_factor() -> int:
        nonlocal index
        if index >= len(tokens):
            return identity
        token = tokens[index]
        if token == "(":
            index += 1
            value = parse_product()
            if index < len(tokens) and tokens[index] == ")":
                index += 1
        elif token == "e":
            index += 1
            value = identity
        elif token in assignment:
            index += 1
            value = int(assignment[token])
        else:
            raise ValueError("unknown_group_token")
        while index < len(tokens) and tokens[index] == "INV":
            inverse = _inverse_element(table, identity, value)
            if inverse is None:
                raise ValueError("missing_inverse")
            value = inverse
            index += 1
        return value

    return parse_product()


def _verify_group_table(table: Sequence[Sequence[int]], identity: int) -> tuple[str, ...]:
    issues: list[str] = []
    order = len(table)
    if order == 0:
        return ("empty_table",)
    if identity < 0 or identity >= order:
        issues.append("invalid_identity")
    for row in table:
        if len(row) != order:
            issues.append("non_square_table")
    if issues:
        return tuple(issues)
    for left in range(order):
        for right in range(order):
            value = table[left][right]
            if not isinstance(value, int) or value < 0 or value >= order:
                issues.append("closure_failed")
    for a in range(order):
        for b in range(order):
            for c in range(order):
                if table[table[a][b]][c] != table[a][table[b][c]]:
                    issues.append("associativity_failed")
                    return tuple(issues)
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
    identity = int(structures.get("identity", 0))
    if raw_table is None:
        return VerificationResult(False, candidate, ("missing_operation_table",))
    table = tuple(tuple(int(item) for item in row) for row in raw_table)
    issues = list(_verify_group_table(table, identity))
    assignment: dict[str, int] = {}
    for variable in target.variables:
        if variable not in candidate.assignments:
            issues.append("missing_assignment")
        else:
            value = int(candidate.assignments[variable])
            if value < 0 or value >= len(table):
                issues.append("assignment_out_of_range")
            assignment[variable] = value
    try:
        left_value = _evaluate_word(target.left_word, assignment, table, identity)
        right_value = _evaluate_word(target.right_word, assignment, table, identity)
        if left_value == right_value:
            issues.append("word_identity_not_refuted")
    except Exception as exception:
        issues.append(type(exception).__name__)
        left_value = None
        right_value = None
    artifacts = {
        "left_value": left_value,
        "right_value": right_value,
        "group_table_valid": not any(item in issues for item in ("closure_failed", "associativity_failed", "identity_law_failed", "inverse_law_failed")),
        "word_inequality": "word_identity_not_refuted" not in issues,
        "denominator_status": True,
        "no_numeric_certification": True,
    }
    return VerificationResult(not issues, candidate, tuple(issues), artifacts)
