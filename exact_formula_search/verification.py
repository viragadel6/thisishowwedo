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
    finite_field_add,
    finite_field_element_from_text,
    finite_field_element_text,
    finite_field_elements,
    finite_field_is_zero,
    finite_field_multiply,
    finite_field_negate,
    finite_field_power,
    finite_field_reduce,
    irreducible_modulus_polynomial,
    is_exact_algebraic_value,
    polynomial_coefficient_dictionary,
)


def verify_candidate(specification: ProblemSpec, candidate: Candidate) -> VerificationResult:
    try:
        if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
            return _verify_planar(specification, candidate)
        if specification.kind == ProblemKind.FINITE_FIELD_JACOBIAN_REFUTATION:
            return _verify_finite_field_jacobian(specification, candidate)
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


def _coefficient_dictionary_determinant(
    first_coefficients: Mapping[tuple[int, int], Any],
    second_coefficients: Mapping[tuple[int, int], Any],
) -> dict[tuple[int, int], int]:
    first_x: dict[tuple[int, int], int] = {}
    first_y: dict[tuple[int, int], int] = {}
    second_x: dict[tuple[int, int], int] = {}
    second_y: dict[tuple[int, int], int] = {}
    for monomial, coefficient in first_coefficients.items():
        value = int(coefficient)
        if monomial[0]:
            key = (monomial[0] - 1, monomial[1])
            first_x[key] = first_x.get(key, 0) + monomial[0] * value
        if monomial[1]:
            key = (monomial[0], monomial[1] - 1)
            first_y[key] = first_y.get(key, 0) + monomial[1] * value
    for monomial, coefficient in second_coefficients.items():
        value = int(coefficient)
        if monomial[0]:
            key = (monomial[0] - 1, monomial[1])
            second_x[key] = second_x.get(key, 0) + monomial[0] * value
        if monomial[1]:
            key = (monomial[0], monomial[1] - 1)
            second_y[key] = second_y.get(key, 0) + monomial[1] * value
    difference: dict[tuple[int, int], int] = {}
    for left, left_value in first_x.items():
        for right, right_value in second_y.items():
            key = (left[0] + right[0], left[1] + right[1])
            difference[key] = difference.get(key, 0) + left_value * right_value
    for left, left_value in first_y.items():
        for right, right_value in second_x.items():
            key = (left[0] + right[0], left[1] + right[1])
            difference[key] = difference.get(key, 0) - left_value * right_value
    return {key: value for key, value in difference.items() if value}


def _polynomial_mod_characteristic_constants(coefficients: Mapping[tuple[int, int], int], prime: int) -> tuple[int, bool]:
    constant = 0
    nonconstant_vanish = True
    for monomial, coefficient in coefficients.items():
        reduced = int(coefficient) % int(prime)
        if monomial == (0, 0):
            constant = reduced
        elif reduced:
            nonconstant_vanish = False
    return constant, nonconstant_vanish


def _monomial_field_evaluation(coefficients: Mapping[tuple[int, int], int], point: Sequence[Sequence[int]], prime: int, modulus: Sequence[int]) -> tuple[int, ...]:
    x_value = tuple(int(item) for item in point[0])
    y_value = tuple(int(item) for item in point[1])
    total = finite_field_reduce((0,), prime, modulus)
    for monomial, coefficient in coefficients.items():
        reduced = int(coefficient) % int(prime)
        if not reduced:
            continue
        term = finite_field_reduce((reduced,), prime, modulus)
        if monomial[0]:
            term = finite_field_multiply(term, finite_field_power(x_value, monomial[0], prime, modulus), prime, modulus)
        if monomial[1]:
            term = finite_field_multiply(term, finite_field_power(y_value, monomial[1], prime, modulus), prime, modulus)
        total = finite_field_add(total, term, prime)
    return finite_field_reduce(total, prime, modulus)


def _horner_field_evaluation(coefficients: Mapping[tuple[int, int], int], point: Sequence[Sequence[int]], prime: int, modulus: Sequence[int]) -> tuple[int, ...]:
    x_value = finite_field_reduce(tuple(int(item) for item in point[0]), prime, modulus)
    y_value = finite_field_reduce(tuple(int(item) for item in point[1]), prime, modulus)
    maximum_x = max((monomial[0] for monomial in coefficients), default=0)
    maximum_y = max((monomial[1] for monomial in coefficients), default=0)
    outer = finite_field_reduce((0,), prime, modulus)
    for y_degree in range(maximum_y, -1, -1):
        inner = finite_field_reduce((0,), prime, modulus)
        for x_degree in range(maximum_x, -1, -1):
            coefficient = int(coefficients.get((x_degree, y_degree), 0)) % int(prime)
            inner = finite_field_multiply(inner, x_value, prime, modulus)
            if coefficient:
                inner = finite_field_add(inner, finite_field_reduce((coefficient,), prime, modulus), prime)
        outer = finite_field_multiply(outer, y_value, prime, modulus)
        outer = finite_field_add(outer, inner, prime)
    return finite_field_reduce(outer, prime, modulus)


def _verify_finite_field_jacobian(specification: ProblemSpec, candidate: Candidate) -> VerificationResult:
    issues: list[str] = []
    artifacts = dict(candidate.exact_derivation_artifacts)
    first_text = _formula(candidate, ("F1", "F₁", "first"))
    second_text = _formula(candidate, ("F2", "F₂", "second"))
    point_text = _point(candidate, "P")
    other_text = _point(candidate, "Q")
    try:
        prime = int(artifacts.get("field_characteristic"))
        degree = int(artifacts.get("field_extension_degree"))
    except (TypeError, ValueError):
        return VerificationResult(False, candidate, ("missing_finite_field_declaration",))
    if prime < 2 or degree < 1:
        return VerificationResult(False, candidate, ("invalid_finite_field_declaration",))
    try:
        modulus = irreducible_modulus_polynomial(prime, degree)
    except Exception as exception:
        return VerificationResult(False, candidate, ("irreducible_modulus_unavailable:" + type(exception).__name__,))
    recorded_modulus = artifacts.get("field_modulus")
    modulus_matches = recorded_modulus is not None and tuple(int(item) for item in recorded_modulus) == tuple(modulus)
    if not modulus_matches:
        issues.append("recorded_modulus_is_not_the_canonical_irreducible_polynomial")
    elements = finite_field_elements(prime, degree)
    field_order = prime ** degree
    if int(artifacts.get("field_order", 0) or 0) != field_order:
        issues.append("field_order_mismatch")
    first = exact_parse_expression(first_text, ("x", "y"))
    second = exact_parse_expression(second_text, ("x", "y"))
    if first.has(sp.Float) or second.has(sp.Float):
        issues.append("floating_number_present")
    x_symbol, y_symbol = sp.symbols("x y")
    try:
        first_coefficients = polynomial_coefficient_dictionary(first, (x_symbol, y_symbol))
        second_coefficients = polynomial_coefficient_dictionary(second, (x_symbol, y_symbol))
    except Exception as exception:
        return VerificationResult(False, candidate, ("non_polynomial_component:" + type(exception).__name__,))
    for coefficient in tuple(first_coefficients.values()) + tuple(second_coefficients.values()):
        if not getattr(coefficient, "is_Integer", False):
            issues.append("non_integer_coefficient_in_positive_characteristic")
    determinant_sympy = sp.expand(
        sp.diff(first, x_symbol) * sp.diff(second, y_symbol) - sp.diff(first, y_symbol) * sp.diff(second, x_symbol)
    )
    determinant_coefficients = polynomial_coefficient_dictionary(determinant_sympy, (x_symbol, y_symbol))
    constant, nonconstant_vanish = _polynomial_mod_characteristic_constants(
        {monomial: int(value) for monomial, value in determinant_coefficients.items()}, prime
    )
    if not nonconstant_vanish:
        issues.append("nonconstant_determinant_coefficient_survives_modulo_characteristic")
    if constant % prime == 0:
        issues.append("zero_or_undecided_constant_determinant_modulo_characteristic")
    independent_determinant = _coefficient_dictionary_determinant(first_coefficients, second_coefficients)
    independent_reduced = {
        monomial: int(value) % prime for monomial, value in independent_determinant.items() if int(value) % prime
    }
    recorded_reduced = {
        monomial: int(value) % prime
        for monomial, value in determinant_coefficients.items()
        if int(value) % prime
    }
    if independent_reduced != recorded_reduced:
        issues.append("determinant_paths_disagree")
    try:
        point = finite_field_element_from_text(point_text[0], prime, degree)
        point_second = finite_field_element_from_text(point_text[1], prime, degree)
        other = finite_field_element_from_text(other_text[0], prime, degree)
        other_second = finite_field_element_from_text(other_text[1], prime, degree)
    except Exception as exception:
        return VerificationResult(False, candidate, ("unparsable_finite_field_point:" + type(exception).__name__,))
    point_pair = (point, point_second)
    other_pair = (other, other_second)
    for value in point_pair + other_pair:
        try:
            round_trip = finite_field_element_from_text(finite_field_element_text(value, prime), prime, degree)
        except Exception:
            round_trip = None
        if round_trip != tuple(value):
            issues.append("field_element_text_round_trip_failed")
            break
    distinct = any(not finite_field_is_zero(finite_field_add(left, finite_field_negate(right, prime), prime), prime) for left, right in zip(point_pair, other_pair))
    if not distinct:
        issues.append("points_not_proved_distinct")
    first_reduced = {monomial: int(value) % prime for monomial, value in first_coefficients.items()}
    second_reduced = {monomial: int(value) % prime for monomial, value in second_coefficients.items()}
    evaluations = {
        "first_point_monomial": _monomial_field_evaluation(first_reduced, point_pair, prime, modulus),
        "first_point_horner": _horner_field_evaluation(first_reduced, point_pair, prime, modulus),
        "first_other_monomial": _monomial_field_evaluation(first_reduced, other_pair, prime, modulus),
        "first_other_horner": _horner_field_evaluation(first_reduced, other_pair, prime, modulus),
        "second_point_monomial": _monomial_field_evaluation(second_reduced, point_pair, prime, modulus),
        "second_point_horner": _horner_field_evaluation(second_reduced, point_pair, prime, modulus),
        "second_other_monomial": _monomial_field_evaluation(second_reduced, other_pair, prime, modulus),
        "second_other_horner": _horner_field_evaluation(second_reduced, other_pair, prime, modulus),
    }
    if evaluations["first_point_monomial"] != evaluations["first_point_horner"] or evaluations["second_point_monomial"] != evaluations["second_point_horner"]:
        issues.append("first_component_point_evaluation_paths_disagree")
    if evaluations["first_other_monomial"] != evaluations["first_other_horner"] or evaluations["second_other_monomial"] != evaluations["second_other_horner"]:
        issues.append("component_other_evaluation_paths_disagree")
    if evaluations["first_point_monomial"] != evaluations["first_other_monomial"]:
        issues.append("first_component_collision_failed")
    if evaluations["second_point_monomial"] != evaluations["second_other_monomial"]:
        issues.append("second_component_collision_failed")
    prime_field_collision = all(
        all(int(entry) % prime == 0 for entry in value[1:]) for value in point_pair + other_pair
    )
    recorded_image = artifacts.get("image_at_point")
    recorded_other_image = artifacts.get("image_at_other")
    if recorded_image is None or recorded_other_image is None:
        issues.append("missing_recorded_image")
    else:
        if [finite_field_element_text(evaluations["first_point_monomial"], prime), finite_field_element_text(evaluations["second_point_monomial"], prime)] != [str(item) for item in recorded_image]:
            issues.append("recorded_image_at_point_mismatch")
        if [finite_field_element_text(evaluations["first_other_monomial"], prime), finite_field_element_text(evaluations["second_other_monomial"], prime)] != [str(item) for item in recorded_other_image]:
            issues.append("recorded_image_at_other_mismatch")
    result_artifacts = {
        "field_characteristic": prime,
        "field_extension_degree": degree,
        "field_order": field_order,
        "field_modulus": [int(item) for item in modulus],
        "field_modulus_is_canonical": modulus_matches,
        "field_size_matches_element_table": len(elements) == field_order,
        "sympy_determinant": str(determinant_sympy),
        "constant_determinant_mod_characteristic": int(constant),
        "determinant_nonzero": constant % prime != 0,
        "nonconstant_coefficients_vanish_mod_characteristic": nonconstant_vanish,
        "independent_determinant_check": independent_reduced == recorded_reduced,
        "independent_determinant_polynomial": sp.sstr(
            sum(
                sp.Integer(coefficient) * x_symbol ** monomial[0] * y_symbol ** monomial[1]
                for monomial, coefficient in independent_reduced.items()
            )
            or sp.Integer(0)
        ),
        "collision_differences_zero": "first_component_collision_failed" not in issues and "second_component_collision_failed" not in issues,
        "independent_collision_check": all("evaluation_paths_disagree" not in issue for issue in issues),
        "distinct_points": distinct,
        "not_injective_on_finite_field": distinct and "first_component_collision_failed" not in issues and "second_component_collision_failed" not in issues,
        "prime_field_collision": prime_field_collision,
        "collision_lifts_to_algebraic_closure": prime_field_collision and all(getattr(coefficient, "is_Integer", False) for coefficient in tuple(first_coefficients.values()) + tuple(second_coefficients.values())),
        "denominator_status": True,
        "domain_exclusions_respected": True,
        "no_numeric_certification": "floating_number_present" not in issues,
        "refutation_scope": "polynomial maps over the finite field GF(" + str(prime) + ("" if degree == 1 else "^" + str(degree)) + ")",
        "characteristic_zero_status": "open",
        "image_at_point": [finite_field_element_text(evaluations["first_point_monomial"], prime), finite_field_element_text(evaluations["second_point_monomial"], prime)],
        "image_at_other": [finite_field_element_text(evaluations["first_other_monomial"], prime), finite_field_element_text(evaluations["second_other_monomial"], prime)],
        "formal_variables": specification.variables,
    }
    return VerificationResult(not issues, candidate, tuple(issues), result_artifacts)


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
