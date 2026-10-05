from __future__ import annotations

import itertools
import math
from typing import Any, Mapping, Sequence

import sympy as sp

from .symbolic_tools import (
    check_denominator_nonzero_obligations,
    exact_nonzero,
    exact_parse_expression,
    exact_zero,
    normalize_expression,
)


def coefficient_enumeration(bound: int, count: int, domain: str = "rational"):
    values = exact_algebraic_candidate_construction(bound) if domain == "algebraic" else exact_rational_grid(bound)
    for item in itertools.product(values, repeat=max(0, count)):
        yield item


def monomial_support_construction(
    degree_extent: int,
    weighted_degree: int | None = None,
    weights: tuple[int, int] = (1, 1),
    include_constant: bool = True,
) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    degree = max(0, int(degree_extent))
    for first in range(degree + 1):
        for second in range(degree + 1):
            if not include_constant and first == 0 and second == 0:
                continue
            if first + second <= degree:
                if weighted_degree is None or weights[0] * first + weights[1] * second <= weighted_degree:
                    result.append((first, second))
    return tuple(sorted(set(result), key=lambda item: (item[0] + item[1], item[0], item[1])))


def exact_rational_grid(bound: int) -> tuple[sp.Expr, ...]:
    extent = max(0, int(bound))
    values = {sp.Integer(0)}
    denominator_extent = max(1, extent)
    for denominator in range(1, denominator_extent + 1):
        for numerator in range(-extent, extent + 1):
            values.add(sp.Rational(numerator, denominator))
    return tuple(sorted(values, key=sp.default_sort_key))


def exact_algebraic_candidate_construction(bound: int) -> tuple[sp.Expr, ...]:
    extent = max(1, int(bound))
    values = set(exact_rational_grid(extent))
    for radicand in range(2, min(6, extent + 4)):
        root = sp.sqrt(sp.Integer(radicand))
        values.add(root)
        values.add(-root)
        values.add(root - 1)
        values.add(1 - root)
    values.add(sp.I)
    values.add(-sp.I)
    return tuple(sorted(values, key=sp.default_sort_key))


def polynomial_system_equation_construction(expressions: Sequence[Any]) -> tuple[sp.Expr, ...]:
    return tuple(sp.expand(sp.sympify(expression)) for expression in expressions)


def determinant_constraint_construction(first: Any, second: Any, variables: Sequence[sp.Symbol]) -> tuple[sp.Expr, ...]:
    x_symbol, y_symbol = variables
    determinant = sp.expand(sp.diff(first, x_symbol) * sp.diff(second, y_symbol) - sp.diff(first, y_symbol) * sp.diff(second, x_symbol))
    polynomial = sp.Poly(determinant, x_symbol, y_symbol, extension=True)
    equations: list[sp.Expr] = []
    for monomial, coefficient in polynomial.terms():
        if monomial != (0, 0):
            equations.append(sp.expand(coefficient))
    return tuple(equations)


def collision_constraint_construction(first: Any, second: Any, point: Sequence[Any], other: Sequence[Any], variables: Sequence[sp.Symbol]) -> tuple[sp.Expr, ...]:
    x_symbol, y_symbol = variables
    substitutions_left = {x_symbol: point[0], y_symbol: point[1]}
    substitutions_right = {x_symbol: other[0], y_symbol: other[1]}
    return (
        sp.expand(first.subs(substitutions_left) - first.subs(substitutions_right)),
        sp.expand(second.subs(substitutions_left) - second.subs(substitutions_right)),
    )


def solve_exact_helper(equations: Sequence[Any], symbols: Sequence[sp.Symbol], route: str = "solve", term_order: str = "lex") -> list[dict[sp.Symbol, sp.Expr]]:
    cleaned = [sp.expand(sp.sympify(equation)) for equation in equations if not exact_zero(equation)]
    if not cleaned:
        return [{}]
    try:
        if route == "groebner" and symbols:
            basis = sp.groebner(cleaned, *symbols, order=term_order)
            solved = sp.solve(list(basis.polys), list(symbols), dict=True)
        else:
            solved = sp.solve(cleaned, list(symbols), dict=True, rational=True)
    except Exception:
        try:
            solved = sp.solve(cleaned, list(symbols), dict=True)
        except Exception:
            solved = []
    result: list[dict[sp.Symbol, sp.Expr]] = []
    for item in solved:
        if isinstance(item, Mapping):
            result.append({sp.sympify(key): sp.sympify(value) for key, value in item.items()})
    return result


def groebner_helper(equations: Sequence[Any], symbols: Sequence[sp.Symbol], order: str = "lex") -> Any:
    try:
        return sp.groebner([sp.sympify(item) for item in equations], *symbols, order=order)
    except Exception:
        return None


def resultant_helper(first: Any, second: Any, variable: sp.Symbol) -> sp.Expr | None:
    try:
        return sp.resultant(sp.sympify(first), sp.sympify(second), variable)
    except Exception:
        return None


def modular_prescreen_helpers(expression: Any, prime: int, variables: Sequence[sp.Symbol]) -> dict[tuple[int, int], int]:
    polynomial = sp.Poly(sp.expand(expression), *variables, modulus=int(prime))
    result: dict[tuple[int, int], int] = {}
    for monomial, coefficient in polynomial.terms():
        result[tuple(int(item) for item in monomial)] = int(coefficient) % int(prime)
    return result


def exact_lifting_helpers(value: int, prime: int) -> sp.Integer:
    residue = int(value) % int(prime)
    if residue > prime // 2:
        residue -= int(prime)
    return sp.Integer(residue)


def serialize_candidate(
    formulas: Mapping[str, Any] | None = None,
    points: Mapping[str, Sequence[Any]] | None = None,
    assignments: Mapping[str, Any] | None = None,
    finite_structures: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "formulas": {str(key): _expression_text(value) for key, value in dict(formulas or {}).items()},
        "points": {str(key): tuple(_expression_text(item) for item in value) for key, value in dict(points or {}).items()},
        "assignments": {str(key): _assignment_text(value) for key, value in dict(assignments or {}).items()},
        "finite_structures": dict(finite_structures or {}),
        "exact_derivation_artifacts": dict(artifacts or {}),
    }


def candidate_serialization_helpers(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return serialize_candidate(*args, **kwargs)


def _assignment_text(value: Any) -> Any:
    if isinstance(value, int):
        return value
    try:
        return _expression_text(value)
    except Exception:
        return value


def _expression_text(value: Any) -> str:
    expression = normalize_expression(value)
    try:
        return sp.sstr(expression, order="lex")
    except Exception:
        return str(expression)


def _frontier_supports(frontier: Mapping[str, Any]) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]:
    raw = frontier.get("support_sets") or ()
    supports: list[tuple[tuple[int, int], ...]] = []
    for support in raw:
        supports.append(tuple((int(first), int(second)) for first, second in support))
    if len(supports) >= 2:
        return supports[0], supports[1]
    support = monomial_support_construction(int(frontier.get("degree_extent", 1)))
    return support, support


def _parameterized_map(frontier: Mapping[str, Any], x_symbol: sp.Symbol, y_symbol: sp.Symbol) -> tuple[sp.Expr, sp.Expr, tuple[sp.Symbol, ...]]:
    first_support, second_support = _frontier_supports(frontier)
    symmetry = str(frontier.get("symmetry_mode", "none"))
    scheme = str(frontier.get("composition_scheme", "direct"))
    base_first = x_symbol if scheme in ("identity_perturbation", "triangular_composition", "affine_composition", "layered") else sp.Integer(0)
    base_second = y_symbol if scheme in ("identity_perturbation", "triangular_composition", "affine_composition", "layered") else sp.Integer(0)
    if symmetry in ("swap", "antisymmetry", "sign"):
        support = tuple(sorted(set(first_support) | {(b, a) for a, b in first_support}, key=lambda item: (item[0] + item[1], item[0], item[1])))
        symbols = tuple(sp.Symbol(f"c_{index}") for index, _ in enumerate(support))
        first_extra = sum(symbol * x_symbol ** first * y_symbol ** second for symbol, (first, second) in zip(symbols, support))
        if symmetry == "swap":
            second_extra = sum(symbol * x_symbol ** second * y_symbol ** first for symbol, (first, second) in zip(symbols, support))
        elif symmetry == "antisymmetry":
            second_extra = -sum(symbol * x_symbol ** second * y_symbol ** first for symbol, (first, second) in zip(symbols, support))
        else:
            second_extra = sum(symbol * (-x_symbol) ** first * (-y_symbol) ** second for symbol, (first, second) in zip(symbols, support))
        return sp.expand(base_first + first_extra), sp.expand(base_second + second_extra), symbols
    first_symbols = tuple(sp.Symbol(f"a_{index}") for index, _ in enumerate(first_support))
    second_symbols = tuple(sp.Symbol(f"b_{index}") for index, _ in enumerate(second_support))
    first_extra = sum(symbol * x_symbol ** first * y_symbol ** second for symbol, (first, second) in zip(first_symbols, first_support))
    second_extra = sum(symbol * x_symbol ** first * y_symbol ** second for symbol, (first, second) in zip(second_symbols, second_support))
    return sp.expand(base_first + first_extra), sp.expand(base_second + second_extra), first_symbols + second_symbols


def _allowed_values(frontier: Mapping[str, Any]) -> tuple[sp.Expr, ...]:
    bound = int(frontier.get("coefficient_extent", 1))
    domain = str(frontier.get("exact_domain", "rational"))
    if domain == "algebraic":
        return exact_algebraic_candidate_construction(bound)
    return exact_rational_grid(bound)


def _value_in_grid(value: Any, grid: Sequence[Any]) -> bool:
    expression = normalize_expression(value)
    return any(exact_zero(expression - item) for item in grid)


def _instantiate_solutions(
    symbols: Sequence[sp.Symbol],
    solutions: Sequence[Mapping[sp.Symbol, Any]],
    grid: Sequence[Any],
) -> list[dict[sp.Symbol, sp.Expr]]:
    symbol_set = set(symbols)
    instances: list[dict[sp.Symbol, sp.Expr]] = []
    for solution in solutions:
        free_parameters: set[sp.Symbol] = set()
        normalized_solution = {sp.sympify(key): sp.sympify(value) for key, value in solution.items()}
        for symbol in symbols:
            expression = normalized_solution.get(symbol, symbol)
            free_parameters.update(item for item in expression.free_symbols if item not in set())
            if symbol not in normalized_solution:
                free_parameters.add(symbol)
        free_parameters = {item for item in free_parameters if item not in {sp.Symbol("x"), sp.Symbol("y")}}
        ordered = tuple(sorted(free_parameters, key=lambda item: str(item)))
        for values in itertools.product(grid, repeat=len(ordered)):
            substitutions = dict(zip(ordered, values))
            instance: dict[sp.Symbol, sp.Expr] = {}
            accepted = True
            for symbol in symbols:
                expression = normalized_solution.get(symbol, symbol)
                value = normalize_expression(expression.subs(substitutions))
                if value.free_symbols:
                    accepted = False
                    break
                if not _value_in_grid(value, grid):
                    accepted = False
                    break
                instance[symbol] = value
            if accepted and set(instance) == symbol_set:
                instances.append(instance)
    return instances


def _point_values(frontier: Mapping[str, Any]) -> tuple[sp.Expr, ...]:
    extra = dict(frontier.get("extra_parameters") or {})
    bound = int(extra.get("point_bound", max(1, int(frontier.get("coefficient_extent", 1)))))
    if str(frontier.get("point_pattern", "")) == "algebraic_grid" or str(frontier.get("exact_domain", "")) == "algebraic":
        return exact_algebraic_candidate_construction(bound)
    return exact_rational_grid(bound)


def _point_pairs(frontier: Mapping[str, Any]) -> tuple[tuple[tuple[sp.Expr, sp.Expr], tuple[sp.Expr, sp.Expr]], ...]:
    pattern = str(frontier.get("point_pattern", "rational_grid"))
    values = _point_values(frontier)
    zero = sp.Integer(0)
    pairs: list[tuple[tuple[sp.Expr, sp.Expr], tuple[sp.Expr, sp.Expr]]] = []
    if pattern == "axis_pair":
        for value in values:
            if exact_nonzero(value):
                pairs.append(((zero, zero), (value, zero)))
                pairs.append(((zero, zero), (zero, value)))
    elif pattern == "origin_pair":
        for first in values:
            for second in values:
                if exact_nonzero(first) or exact_nonzero(second):
                    pairs.append(((zero, zero), (first, second)))
    elif pattern in ("diagonal_pair", "swapped_pair"):
        for first in values:
            for second in values:
                if exact_nonzero(first - second):
                    pairs.append(((first, second), (second, first)))
    else:
        points = tuple((first, second) for first in values for second in values)
        for point in points:
            for other in points:
                if exact_nonzero(point[0] - other[0]) or exact_nonzero(point[1] - other[1]):
                    pairs.append((point, other))
    return tuple(pairs)


def _det_constant_nonzero(first: sp.Expr, second: sp.Expr, variables: Sequence[sp.Symbol]) -> bool:
    x_symbol, y_symbol = variables
    if not first.free_symbols.issubset({x_symbol, y_symbol}) or not second.free_symbols.issubset({x_symbol, y_symbol}):
        return False
    determinant = sp.expand(sp.diff(first, x_symbol) * sp.diff(second, y_symbol) - sp.diff(first, y_symbol) * sp.diff(second, x_symbol))
    try:
        polynomial = sp.Poly(determinant, x_symbol, y_symbol, extension=True)
    except Exception:
        return False
    constant = sp.Integer(0)
    for monomial, coefficient in polynomial.terms():
        coefficient = normalize_expression(coefficient)
        if monomial == (0, 0):
            constant = coefficient
        elif not exact_zero(coefficient):
            return False
    return exact_nonzero(constant)


def _collision_exact(first: sp.Expr, second: sp.Expr, point: Sequence[Any], other: Sequence[Any], variables: Sequence[sp.Symbol]) -> bool:
    x_symbol, y_symbol = variables
    left = {x_symbol: point[0], y_symbol: point[1]}
    right = {x_symbol: other[0], y_symbol: other[1]}
    return exact_zero(first.subs(left) - first.subs(right)) and exact_zero(second.subs(left) - second.subs(right))


def _check_and_serialize(first: sp.Expr, second: sp.Expr, point: Sequence[Any], other: Sequence[Any], frontier: Mapping[str, Any]) -> dict[str, Any] | None:
    x_symbol, y_symbol = sp.symbols("x y")
    if not _det_constant_nonzero(first, second, (x_symbol, y_symbol)):
        return None
    if not _collision_exact(first, second, point, other, (x_symbol, y_symbol)):
        return None
    if not (exact_nonzero(point[0] - other[0]) or exact_nonzero(point[1] - other[1])):
        return None
    determinant = sp.expand(sp.diff(first, x_symbol) * sp.diff(second, y_symbol) - sp.diff(first, y_symbol) * sp.diff(second, x_symbol))
    return serialize_candidate(
        formulas={"F1": first, "F2": second},
        points={"P": point, "Q": other},
        artifacts={
            "runtime_route": str(frontier.get("kind", "")),
            "runtime_determinant": _expression_text(determinant),
            "frontier_signature": str(frontier.get("unique_signature", "")),
        },
    )


def _search_planar_enumeration(frontier: Mapping[str, Any]) -> dict[str, Any]:
    x_symbol, y_symbol = sp.symbols("x y")
    first, second, symbols = _parameterized_map(frontier, x_symbol, y_symbol)
    grid = _allowed_values(frontier)
    pairs = _point_pairs(frontier)
    candidates: list[dict[str, Any]] = []
    for values in itertools.product(grid, repeat=len(symbols)):
        substitutions = dict(zip(symbols, values))
        current_first = sp.expand(first.subs(substitutions))
        current_second = sp.expand(second.subs(substitutions))
        if not _det_constant_nonzero(current_first, current_second, (x_symbol, y_symbol)):
            continue
        for point, other in pairs:
            candidate = _check_and_serialize(current_first, current_second, point, other, frontier)
            if candidate is not None:
                candidates.append(candidate)
    failures = () if candidates else ("no_candidate_in_frontier",)
    return {"candidates": candidates, "failures": failures, "artifacts": {"route": "coefficient_enumeration"}}


def _search_planar_equation(frontier: Mapping[str, Any]) -> dict[str, Any]:
    x_symbol, y_symbol = sp.symbols("x y")
    first, second, symbols = _parameterized_map(frontier, x_symbol, y_symbol)
    grid = _allowed_values(frontier)
    pairs = _point_pairs(frontier)
    determinant_equations = determinant_constraint_construction(first, second, (x_symbol, y_symbol))
    route = str(dict(frontier.get("extra_parameters") or {}).get("solver_route", "solve"))
    term_order = str(dict(frontier.get("extra_parameters") or {}).get("term_order", "lex"))
    objective = str(frontier.get("elimination_objective", "mixed"))
    candidates: list[dict[str, Any]] = []
    if objective == "coefficients_first":
        return _search_planar_enumeration(frontier)
    if objective == "determinant_first":
        solutions = solve_exact_helper(determinant_equations, symbols, route, term_order)
        instances = _instantiate_solutions(symbols, solutions, grid)
        for instance in instances:
            current_first = sp.expand(first.subs(instance))
            current_second = sp.expand(second.subs(instance))
            if not _det_constant_nonzero(current_first, current_second, (x_symbol, y_symbol)):
                continue
            for point, other in pairs:
                candidate = _check_and_serialize(current_first, current_second, point, other, frontier)
                if candidate is not None:
                    candidates.append(candidate)
    elif objective == "collision_first":
        for point, other in pairs:
            collision_equations = collision_constraint_construction(first, second, point, other, (x_symbol, y_symbol))
            solutions = solve_exact_helper(collision_equations, symbols, route, term_order)
            instances = _instantiate_solutions(symbols, solutions, grid)
            for instance in instances:
                current_first = sp.expand(first.subs(instance))
                current_second = sp.expand(second.subs(instance))
                candidate = _check_and_serialize(current_first, current_second, point, other, frontier)
                if candidate is not None:
                    candidates.append(candidate)
    else:
        for point, other in pairs:
            collision_equations = collision_constraint_construction(first, second, point, other, (x_symbol, y_symbol))
            equations = determinant_equations + collision_equations
            solutions = solve_exact_helper(equations, symbols, route, term_order)
            instances = _instantiate_solutions(symbols, solutions, grid)
            for instance in instances:
                current_first = sp.expand(first.subs(instance))
                current_second = sp.expand(second.subs(instance))
                candidate = _check_and_serialize(current_first, current_second, point, other, frontier)
                if candidate is not None:
                    candidates.append(candidate)
    failures = () if candidates else ("no_candidate_in_frontier",)
    return {"candidates": candidates, "failures": failures, "artifacts": {"route": "equation_solving", "objective": objective}}


def _search_planar_composition(frontier: Mapping[str, Any]) -> dict[str, Any]:
    x_symbol, y_symbol = sp.symbols("x y")
    grid = _allowed_values(frontier)
    pairs = _point_pairs(frontier)
    candidates: list[dict[str, Any]] = []
    length_extent = max(1, int(frontier.get("degree_extent", 1)))
    for length in range(1, length_extent + 1):
        for values in itertools.product(grid, repeat=2 * length):
            current_x = x_symbol
            current_y = y_symbol
            iterator = iter(values)
            for step in range(length):
                first_value = next(iterator)
                second_value = next(iterator)
                current_x = sp.expand(current_x + first_value * current_y ** (step + 2))
                current_y = sp.expand(current_y + second_value * current_x ** (step + 2))
            for point, other in pairs:
                candidate = _check_and_serialize(current_x, current_y, point, other, frontier)
                if candidate is not None:
                    candidates.append(candidate)
    failures = () if candidates else ("no_candidate_in_frontier",)
    return {"candidates": candidates, "failures": failures, "artifacts": {"route": "composition"}}


def _constant_nonzero_mod(expression: Any, prime: int, variables: Sequence[sp.Symbol]) -> bool:
    coefficients = modular_prescreen_helpers(expression, prime, variables)
    constant = 0
    for monomial, coefficient in coefficients.items():
        if monomial == (0, 0):
            constant = coefficient % prime
        elif coefficient % prime != 0:
            return False
    return constant % prime != 0


def _eval_mod(expression: Any, x_value: int, y_value: int, prime: int, variables: Sequence[sp.Symbol]) -> int:
    x_symbol, y_symbol = variables
    value = sp.sympify(expression).subs({x_symbol: x_value, y_symbol: y_value})
    return int(value) % int(prime)


def _search_planar_modular(frontier: Mapping[str, Any]) -> dict[str, Any]:
    x_symbol, y_symbol = sp.symbols("x y")
    prime = int(dict(frontier.get("extra_parameters") or {}).get("prime", 2))
    first, second, symbols = _parameterized_map(frontier, x_symbol, y_symbol)
    candidates: list[dict[str, Any]] = []
    residues = tuple(range(prime))
    finite_points = tuple((a, b) for a in residues for b in residues)
    determinant = sp.expand(sp.diff(first, x_symbol) * sp.diff(second, y_symbol) - sp.diff(first, y_symbol) * sp.diff(second, x_symbol))
    for values in itertools.product(residues, repeat=len(symbols)):
        substitutions = dict(zip(symbols, values))
        current_first = sp.expand(first.subs(substitutions))
        current_second = sp.expand(second.subs(substitutions))
        current_determinant = determinant.subs(substitutions)
        if not _constant_nonzero_mod(current_determinant, prime, (x_symbol, y_symbol)):
            continue
        for point in finite_points:
            for other in finite_points:
                if point == other:
                    continue
                if _eval_mod(current_first, point[0], point[1], prime, (x_symbol, y_symbol)) == _eval_mod(current_first, other[0], other[1], prime, (x_symbol, y_symbol)) and _eval_mod(current_second, point[0], point[1], prime, (x_symbol, y_symbol)) == _eval_mod(current_second, other[0], other[1], prime, (x_symbol, y_symbol)):
                    lifted = {symbol: exact_lifting_helpers(value, prime) for symbol, value in substitutions.items()}
                    lifted_first = sp.expand(first.subs(lifted))
                    lifted_second = sp.expand(second.subs(lifted))
                    lifted_point = tuple(exact_lifting_helpers(value, prime) for value in point)
                    lifted_other = tuple(exact_lifting_helpers(value, prime) for value in other)
                    candidate = _check_and_serialize(lifted_first, lifted_second, lifted_point, lifted_other, frontier)
                    if candidate is not None:
                        candidates.append(candidate)
    failures = () if candidates else ("no_candidate_in_frontier",)
    return {"candidates": candidates, "failures": failures, "artifacts": {"route": "modular_prescreen", "prime": prime}}


def search_planar_frontier(frontier: Mapping[str, Any]) -> dict[str, Any]:
    kind = str(frontier.get("kind", ""))
    scheme = str(frontier.get("composition_scheme", ""))
    if kind == "finite_field_prescreen" or str(frontier.get("exact_domain", "")) == "modular_prescreen":
        return _search_planar_modular(frontier)
    if kind == "composition_perturbation" or scheme == "triangular_composition":
        return _search_planar_composition(frontier)
    return _search_planar_equation(frontier)


def search_algebraic_assignment(frontier: Mapping[str, Any], problem: Mapping[str, Any]) -> dict[str, Any]:
    target = dict(problem.get("algebraic_identity") or {})
    variables = tuple(str(item) for item in target.get("variables", ()))
    left_text = str(target.get("left_expression", "0"))
    right_text = str(target.get("right_expression", "0"))
    left_expression = exact_parse_expression(left_text, variables)
    right_expression = exact_parse_expression(right_text, variables)
    values = exact_algebraic_candidate_construction(int(frontier.get("coefficient_extent", 1))) if str(frontier.get("exact_domain", "")) == "algebraic" else exact_rational_grid(int(frontier.get("coefficient_extent", 1)))
    candidates: list[dict[str, Any]] = []
    symbol_map = {name: sp.Symbol(name) for name in variables}
    for assignment_values in itertools.product(values, repeat=len(variables)):
        substitutions = {symbol_map[name]: value for name, value in zip(variables, assignment_values)}
        assigned_left = normalize_expression(left_expression.subs(substitutions))
        assigned_right = normalize_expression(right_expression.subs(substitutions))
        if not check_denominator_nonzero_obligations(tuple(substitutions.values()) + (assigned_left, assigned_right)):
            continue
        if exact_nonzero(assigned_left - assigned_right):
            candidates.append(
                serialize_candidate(
                    assignments={name: value for name, value in zip(variables, assignment_values)},
                    artifacts={"left_value": _expression_text(assigned_left), "right_value": _expression_text(assigned_right)},
                )
            )
            break
    failures = () if candidates else ("no_counterassignment_in_frontier",)
    return {"candidates": candidates, "failures": failures, "artifacts": {"route": "assignment_grid"}}


def cyclic_group_table(size: int) -> tuple[tuple[int, ...], ...]:
    order = max(1, int(size))
    return tuple(tuple((left + right) % order for right in range(order)) for left in range(order))


def _permutations(degree: int) -> tuple[tuple[int, ...], ...]:
    return tuple(itertools.permutations(range(degree)))


def symmetric_group_table(degree: int) -> tuple[tuple[int, ...], ...]:
    permutations = _permutations(degree)
    index = {permutation: position for position, permutation in enumerate(permutations)}
    table: list[tuple[int, ...]] = []
    for left in permutations:
        row: list[int] = []
        for right in permutations:
            composed = tuple(left[right[item]] for item in range(degree))
            row.append(index[composed])
        table.append(tuple(row))
    return tuple(table)


def direct_product_group_table(left_table: Sequence[Sequence[int]], right_table: Sequence[Sequence[int]]) -> tuple[tuple[int, ...], ...]:
    left_order = len(left_table)
    right_order = len(right_table)
    elements = tuple((a, b) for a in range(left_order) for b in range(right_order))
    index = {element: position for position, element in enumerate(elements)}
    rows: list[tuple[int, ...]] = []
    for left in elements:
        row: list[int] = []
        for right in elements:
            row.append(index[(left_table[left[0]][right[0]], right_table[left[1]][right[1]])])
        rows.append(tuple(row))
    return tuple(rows)


def finite_group_table_construction_helpers(max_order: int):
    extent = max(1, int(max_order))
    for size in range(1, extent + 1):
        yield ("cyclic", cyclic_group_table(size), 0)
    for degree in range(2, 5):
        order = math.factorial(degree)
        if order <= extent:
            yield (f"symmetric_{degree}", symmetric_group_table(degree), 0)
    for left_size in range(2, extent + 1):
        for right_size in range(2, extent + 1):
            if left_size * right_size <= extent:
                yield (f"product_{left_size}_{right_size}", direct_product_group_table(cyclic_group_table(left_size), cyclic_group_table(right_size)), 0)


def _inverse_element(table: Sequence[Sequence[int]], identity: int, value: int) -> int:
    for candidate in range(len(table)):
        if table[value][candidate] == identity and table[candidate][value] == identity:
            return candidate
    raise ValueError("missing_inverse")


def _group_tokens(word: str, variables: Sequence[str]) -> tuple[str, ...]:
    text = word.replace("⁻¹", "^-1").replace("−1", "-1")
    tokens: list[str] = []
    index = 0
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
            elif run in variables or lower in variables:
                tokens.append(lower)
            else:
                for character in run:
                    lower_character = character.lower()
                    if lower_character in variables:
                        tokens.append(lower_character)
            index = end
        else:
            index += 1
    return tuple(tokens)


def evaluate_group_word(word: str, assignment: Mapping[str, int], table: Sequence[Sequence[int]], identity: int = 0) -> int:
    variables = tuple(str(item).lower() for item in assignment)
    tokens = _group_tokens(word, variables)
    index = 0

    def parse_product() -> int:
        nonlocal index
        result = identity
        while index < len(tokens) and tokens[index] != ")":
            if tokens[index] in ("*", "·"):
                index += 1
                continue
            factor_value = parse_factor()
            result = table[result][factor_value]
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
            value = _inverse_element(table, identity, value)
            index += 1
        return value

    return parse_product()


def finite_group_table_construction_helpers_serialized(max_order: int) -> tuple[dict[str, Any], ...]:
    result = []
    for name, table, identity in finite_group_table_construction_helpers(max_order):
        result.append({"name": name, "table": [list(row) for row in table], "identity": identity})
    return tuple(result)


def search_finite_group_identity(frontier: Mapping[str, Any], problem: Mapping[str, Any]) -> dict[str, Any]:
    target = dict(problem.get("finite_group_identity") or {})
    variables = tuple(str(item).lower() for item in target.get("variables", ()))
    left_word = str(target.get("left_word", ""))
    right_word = str(target.get("right_word", ""))
    max_order = max(1, int(frontier.get("degree_extent", target.get("max_order", 6))))
    candidates: list[dict[str, Any]] = []
    for name, table, identity in finite_group_table_construction_helpers(max_order):
        order = len(table)
        for values in itertools.product(range(order), repeat=len(variables)):
            assignment = {variable: value for variable, value in zip(variables, values)}
            try:
                left_value = evaluate_group_word(left_word, assignment, table, identity)
                right_value = evaluate_group_word(right_word, assignment, table, identity)
            except Exception:
                continue
            if left_value != right_value:
                candidates.append(
                    serialize_candidate(
                        assignments=assignment,
                        finite_structures={"operation_table": [list(row) for row in table], "identity": identity, "elements": list(range(order))},
                        artifacts={"group_family": name, "left_value": left_value, "right_value": right_value},
                    )
                )
                return {"candidates": candidates, "failures": (), "artifacts": {"route": "finite_group_tables"}}
    return {"candidates": (), "failures": ("no_countermodel_in_frontier",), "artifacts": {"route": "finite_group_tables"}}


def run_generated_search(frontier: Mapping[str, Any], problem: Mapping[str, Any]) -> dict[str, Any]:
    try:
        problem_kind = str(problem.get("kind", ""))
        if problem_kind == "planar_constant_determinant_collision":
            return search_planar_frontier(frontier)
        if problem_kind == "finite_group_identity_countermodel":
            return search_finite_group_identity(frontier, problem)
        return search_algebraic_assignment(frontier, problem)
    except Exception as exception:
        return {"candidates": (), "failures": (type(exception).__name__,), "artifacts": {"exception": repr(exception)[:500]}}
