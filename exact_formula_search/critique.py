from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

import sympy as sp

from .code_generation import validate_generated_source
from .models import Candidate, CritiqueIssue, CritiqueResult, Frontier, GeneratedCodeResult, ProblemKind, ProblemSpec, VerificationResult
from .symbolic_tools import (
    evaluate_group_word_by_postfix,
    exact_nonzero,
    exact_parse_expression,
    exact_zero,
    expression_domain_obligations,
    finite_field_element_from_text,
    finite_field_element_text,
    irreducible_modulus_polynomial,
    is_exact_algebraic_value,
    polynomial_coefficient_dictionary,
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


_FINITE_FIELD_SCAN_LIMIT = 20000


def _packed_pack(vector: Sequence[int], prime: int) -> int:
    value = 0
    scale = 1
    for entry in vector:
        value += (int(entry) % prime) * scale
        scale *= prime
    return value


def _packed_digits(value: int, prime: int, count: int) -> tuple[int, ...]:
    digits: list[int] = []
    current = int(value)
    for _ in range(count):
        digits.append(current % prime)
        current //= prime
    return tuple(digits)


def _packed_add(left: int, right: int, prime: int, degree: int) -> int:
    left_digits = _packed_digits(left, prime, degree)
    right_digits = _packed_digits(right, prime, degree)
    return _packed_pack(tuple((a + b) % prime for a, b in zip(left_digits, right_digits)), prime)


def _packed_negate(value: int, prime: int, degree: int) -> int:
    return _packed_pack(tuple((-entry) % prime for entry in _packed_digits(value, prime, degree)), prime)


def _packed_multiply(left: int, right: int, prime: int, degree: int, modulus: Sequence[int]) -> int:
    if degree <= 1:
        return (int(left) * int(right)) % prime
    digits = [0] * (2 * degree)
    left_digits = _packed_digits(left, prime, degree)
    right_digits = _packed_digits(right, prime, degree)
    for index, a in enumerate(left_digits):
        if not a:
            continue
        for offset, b in enumerate(right_digits):
            if b:
                digits[index + offset] = (digits[index + offset] + a * b) % prime
    for power in range(len(digits) - 1, degree - 1, -1):
        top = digits[power]
        if not top:
            continue
        digits[power] = 0
        shift = power - degree
        for index in range(degree):
            digits[shift + index] = (digits[shift + index] - top * modulus[index]) % prime
    return _packed_pack(tuple(digits[:degree]), prime)


def _packed_power(value: int, exponent: int, prime: int, degree: int, modulus: Sequence[int]) -> int:
    result = 1
    base = int(value) % (prime ** degree) if degree > 1 else int(value) % prime
    count = max(0, int(exponent))
    while count:
        if count & 1:
            result = _packed_multiply(result, base, prime, degree, modulus)
        base = _packed_multiply(base, base, prime, degree, modulus)
        count >>= 1
    return result


def _packed_polynomial_evaluation(coefficients: Mapping[tuple[int, int], int], point: Sequence[int], prime: int, degree: int, modulus: Sequence[int]) -> int:
    total = 0
    for monomial, coefficient in coefficients.items():
        reduced = int(coefficient) % prime
        if not reduced:
            continue
        term = reduced
        if monomial[0]:
            term = _packed_multiply(term, _packed_power(point[0], monomial[0], prime, degree, modulus), prime, degree, modulus)
        if monomial[1]:
            term = _packed_multiply(term, _packed_power(point[1], monomial[1], prime, degree, modulus), prime, degree, modulus)
        total = _packed_add(total, term, prime, degree)
    return total


def _independent_finite_field_recheck(specification: ProblemSpec, candidate: Candidate) -> bool:
    artifacts = dict(candidate.exact_derivation_artifacts)
    try:
        prime = int(artifacts.get("field_characteristic"))
        degree = int(artifacts.get("field_extension_degree"))
    except (TypeError, ValueError):
        return False
    if prime < 2 or degree < 1 or prime ** degree > _FINITE_FIELD_SCAN_LIMIT:
        return False
    modulus = irreducible_modulus_polynomial(prime, degree)
    if artifacts.get("field_modulus") is not None and tuple(int(item) for item in artifacts.get("field_modulus")) != tuple(modulus):
        return False
    formulas = candidate.formulas
    try:
        first = exact_parse_expression(str(formulas["F1"]), ("x", "y"))
        second = exact_parse_expression(str(formulas["F2"]), ("x", "y"))
    except Exception:
        return False
    x_symbol, y_symbol = sp.symbols("x y")
    try:
        first_coefficients = {monomial: int(value) for monomial, value in polynomial_coefficient_dictionary(first, (x_symbol, y_symbol)).items()}
        second_coefficients = {monomial: int(value) for monomial, value in polynomial_coefficient_dictionary(second, (x_symbol, y_symbol)).items()}
    except Exception:
        return False
    determinant_terms: dict[tuple[int, int], int] = {}
    partials: list[dict[tuple[int, int], int]] = []
    for coefficients in (first_coefficients, second_coefficients):
        for axis in (0, 1):
            partial: dict[tuple[int, int], int] = {}
            for monomial, value in coefficients.items():
                if monomial[axis]:
                    key = (monomial[0] - 1, monomial[1]) if axis == 0 else (monomial[0], monomial[1] - 1)
                    partial[key] = partial.get(key, 0) + monomial[axis] * value
            partials.append(partial)
    first_x, first_y, second_x, second_y = partials
    for left, left_value in first_x.items():
        for right, right_value in second_y.items():
            key = (left[0] + right[0], left[1] + right[1])
            determinant_terms[key] = determinant_terms.get(key, 0) + left_value * right_value
    for left, left_value in first_y.items():
        for right, right_value in second_x.items():
            key = (left[0] + right[0], left[1] + right[1])
            determinant_terms[key] = determinant_terms.get(key, 0) - left_value * right_value
    jacobian = {key: value for key, value in determinant_terms.items() if value}
    point_count = prime ** degree
    if point_count * point_count > _FINITE_FIELD_SCAN_LIMIT:
        return False
    points = [(left_index, right_index) for left_index in range(point_count) for right_index in range(point_count)]
    determinant_values: set[int] = set()
    images: dict[tuple[int, int], tuple[int, int]] = {}
    duplicate_pairs: int = 0
    for point in points:
        determinant_value = _packed_polynomial_evaluation(jacobian, point, prime, degree, modulus)
        determinant_values.add(determinant_value)
        image = (
            _packed_polynomial_evaluation(first_coefficients, point, prime, degree, modulus),
            _packed_polynomial_evaluation(second_coefficients, point, prime, degree, modulus),
        )
        if image in images:
            duplicate_pairs += 1
        else:
            images[image] = point
    if len(determinant_values) != 1:
        return False
    constant = next(iter(determinant_values))
    if constant == 0:
        return False
    if duplicate_pairs == 0:
        return False
    point_text = candidate.points.get("P")
    other_text = candidate.points.get("Q")
    if point_text is None or other_text is None or len(point_text) != 2 or len(other_text) != 2:
        return False
    try:
        point = (
            _packed_pack(finite_field_element_from_text(point_text[0], prime, degree), prime),
            _packed_pack(finite_field_element_from_text(point_text[1], prime, degree), prime),
        )
        other = (
            _packed_pack(finite_field_element_from_text(other_text[0], prime, degree), prime),
            _packed_pack(finite_field_element_from_text(other_text[1], prime, degree), prime),
        )
    except Exception:
        return False
    if point == other:
        return False
    point_image = (
        _packed_polynomial_evaluation(first_coefficients, point, prime, degree, modulus),
        _packed_polynomial_evaluation(second_coefficients, point, prime, degree, modulus),
    )
    other_image = (
        _packed_polynomial_evaluation(first_coefficients, other, prime, degree, modulus),
        _packed_polynomial_evaluation(second_coefficients, other, prime, degree, modulus),
    )
    if point_image != other_image:
        return False
    recorded_point_image = artifacts.get("image_at_point")
    recorded_other_image = artifacts.get("image_at_other")
    if recorded_point_image is None or recorded_other_image is None:
        return False
    point_image_text = [
        finite_field_element_text(_packed_digits(point_image[0], prime, degree), prime),
        finite_field_element_text(_packed_digits(point_image[1], prime, degree), prime),
    ]
    other_image_text = [
        finite_field_element_text(_packed_digits(other_image[0], prime, degree), prime),
        finite_field_element_text(_packed_digits(other_image[1], prime, degree), prime),
    ]
    if point_image_text != [str(item) for item in recorded_point_image]:
        return False
    return other_image_text == [str(item) for item in recorded_other_image]


def _independent_recheck(specification: ProblemSpec, candidate: Candidate) -> bool:
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        return _independent_planar_recheck(specification, candidate)
    if specification.kind == ProblemKind.FINITE_FIELD_JACOBIAN_REFUTATION:
        return _independent_finite_field_recheck(specification, candidate)
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
    elif specification.kind == ProblemKind.FINITE_FIELD_JACOBIAN_REFUTATION:
        if specification.finite_field_target is None:
            issues.append(_issue("target_missing", "finite field target data is absent", "repair formalization"))
        if artifacts.get("field_modulus_is_canonical") is not True:
            issues.append(_issue("field_modulus_gap", "the field modulus is not the canonical irreducible polynomial", "recompute the irreducible modulus for the declared field"))
        if artifacts.get("determinant_nonzero") is not True or artifacts.get("nonconstant_coefficients_vanish_mod_characteristic") is not True:
            issues.append(_issue("determinant_obligation_gap", "constant determinant obligations are incomplete in the declared characteristic", "repair the determinant constraint route"))
        if artifacts.get("independent_determinant_check") is not True:
            issues.append(_issue("single_determinant_path", "determinant was not certified by independent paths", "add the coefficient-dictionary determinant check"))
        if artifacts.get("independent_collision_check") is not True:
            issues.append(_issue("single_collision_path", "collision was not certified by independent paths", "add a second finite field evaluation route"))
        if artifacts.get("distinct_points") is not True:
            issues.append(_issue("distinctness_gap", "point distinctness was not proved exactly", "change the collision witness"))
        if artifacts.get("collision_differences_zero") is not True:
            issues.append(_issue("collision_obligation_gap", "collision obligations are incomplete", "repair the collision equations"))
        if artifacts.get("not_injective_on_finite_field") is not True:
            issues.append(_issue("injectivity_gap", "non-injectivity over the finite field was not certified", "repair the point scan"))
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
