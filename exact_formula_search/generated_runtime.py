from __future__ import annotations

import itertools
import math
import time
from typing import Any, Iterable, Iterator, Mapping, Sequence

import sympy as sp

from .symbolic_tools import (
    check_denominator_nonzero_obligations,
    check_obligations_at,
    derivative_matrix_determinant,
    differential_determinant_from_expressions,
    exact_nonzero,
    exact_parse_expression,
    exact_zero,
    evaluate_group_word,
    evaluate_group_word_by_postfix,
    expression_domain_obligations,
    finite_field_add,
    finite_field_element_text,
    finite_field_elements,
    finite_field_multiply,
    finite_field_power,
    finite_field_reduce,
    is_exact_algebraic_value,
    irreducible_modulus_polynomial,
    normalize_expression,
    polynomial_coefficient_dictionary,
)

_DEFAULT_MAX_CANDIDATES = 4
_DEFAULT_MAX_INSTANCES = 256
_DEFAULT_MAX_POINT_PAIRS = 48
_DEFAULT_MAX_COMPOSITIONS = 2048
_DEFAULT_MAX_ENUMERATIONS = 20000
_DEFAULT_MAX_SOLVES = 12
_DEFAULT_DEADLINE_SECONDS = 8.0
_SEARCH_DEADLINE: list[float | None] = [None]


def _set_search_deadline(seconds: float) -> None:
    _SEARCH_DEADLINE[0] = time.monotonic() + max(0.05, float(seconds))


def _search_time_exceeded() -> bool:
    deadline = _SEARCH_DEADLINE[0]
    if deadline is None:
        return False
    return time.monotonic() >= deadline


def coefficient_enumeration(bound: int, count: int, domain: str = "rational", limit: int = 0) -> Iterator[tuple[Any, ...]]:
    values = exact_algebraic_candidate_construction(bound) if domain == "algebraic" else exact_rational_grid(bound)
    produced = 0
    for item in itertools.product(values, repeat=max(0, count)):
        yield item
        produced += 1
        if limit and produced >= limit:
            return


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
            if first + second > degree:
                continue
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


def _route_resultant(equations: Sequence[Any], symbols: Sequence[sp.Symbol]) -> list[dict[sp.Symbol, sp.Expr]]:
    ordered = list(symbols)
    if not ordered:
        return []
    if len(ordered) == 1:
        try:
            roots = sp.solve([sp.expand(item) for item in equations], ordered[0], dict=True)
        except Exception:
            return []
        return [dict(item) for item in roots if isinstance(item, Mapping)]
    eliminator = ordered[0]
    rest = ordered[1:]
    try:
        current = sp.expand(equations[0])
        for equation in equations[1:]:
            current = sp.expand(sp.resultant(current, sp.expand(equation), eliminator))
    except Exception:
        return []
    sub_solutions = _route_resultant([current], rest)
    solutions: list[dict[sp.Symbol, sp.Expr]] = []
    for sub in sub_solutions:
        remaining = [sp.expand(equation.subs(sub)) for equation in equations]
        try:
            roots = sp.solve(remaining, eliminator, dict=True)
        except Exception:
            continue
        for root in roots:
            if not isinstance(root, Mapping):
                continue
            merged = dict(sub)
            merged.update(dict(root))
            solutions.append(merged)
    return solutions


def _route_sequential(equations: Sequence[Any], symbols: Sequence[sp.Symbol]) -> list[dict[sp.Symbol, sp.Expr]]:
    ordered = list(symbols)
    current = list(equations)
    solved: dict[sp.Symbol, sp.Expr] = {}
    for position, symbol in enumerate(ordered):
        target = None
        for equation in current:
            if symbol in equation.free_symbols:
                target = equation
                break
        if target is None:
            continue
        try:
            values = sp.solve(target, symbol, dict=True)
        except Exception:
            return []
        if not values:
            return []
        branch = values[0]
        for key, value in branch.items():
            solved[sp.sympify(key)] = sp.sympify(value)
        current = [sp.expand(item.subs(branch)) for item in current]
        current = [item for item in current if item != 0]
        if not current:
            break
    for equation in equations:
        substituted = sp.sympify(equation).subs(solved)
        if substituted.free_symbols or substituted != 0:
            return []
    return [dict(solved)]


def _route_groebner(equations: Sequence[Any], symbols: Sequence[sp.Symbol], term_order: str) -> list[dict[sp.Symbol, sp.Expr]]:
    if len(symbols) > 6:
        raise ValueError("groebner_route_symbol_limit")
    try:
        basis = sp.groebner(list(equations), *symbols, order=term_order)
    except Exception:
        return []
    try:
        solved = sp.solve(list(basis.polys), list(symbols), dict=True)
    except Exception:
        return []
    result: list[dict[sp.Symbol, sp.Expr]] = []
    for item in solved:
        if isinstance(item, Mapping):
            result.append({sp.sympify(key): sp.sympify(value) for key, value in item.items()})
    return result


def solve_exact(equations: Sequence[Any], symbols: Sequence[sp.Symbol], route: str = "solve", term_order: str = "lex") -> tuple[list[dict[sp.Symbol, sp.Expr]], tuple[str, ...]]:
    cleaned = [sp.expand(sp.sympify(equation)) for equation in equations if not exact_zero(equation)]
    notes: list[str] = []
    if not cleaned:
        return [{}], ("trivial_system",)
    if not symbols:
        return [], ("no_unknowns",)
    ordered = list(symbols)
    attempts: list[tuple[str, Any]] = []
    selected = str(route)
    if selected == "groebner":
        attempts.append(("groebner", lambda: _route_groebner(cleaned, ordered, term_order)))
        attempts.append(("solve", lambda: _solve_plain(cleaned, ordered)))
    elif selected == "resultant":
        attempts.append(("resultant", lambda: _route_resultant(cleaned, ordered)))
        attempts.append(("solve", lambda: _solve_plain(cleaned, ordered)))
    elif selected == "sequential":
        attempts.append(("sequential", lambda: _route_sequential(cleaned, ordered)))
        attempts.append(("solve", lambda: _solve_plain(cleaned, ordered)))
    else:
        attempts.append(("solve", lambda: _solve_plain(cleaned, ordered)))
    for name, attempt in attempts:
        try:
            solutions = attempt()
        except Exception as exception:
            notes.append("route_" + name + "_exception:" + type(exception).__name__)
            continue
        normalized: list[dict[sp.Symbol, sp.Expr]] = []
        for item in solutions:
            if isinstance(item, Mapping):
                normalized.append({sp.sympify(key): sp.sympify(value) for key, value in item.items()})
        if normalized:
            return normalized, tuple(notes)
        notes.append("route_" + name + "_empty")
    return [], tuple(notes)


def _solve_plain(equations: Sequence[Any], symbols: Sequence[sp.Symbol]) -> list[dict[sp.Symbol, sp.Expr]]:
    try:
        solved = sp.solve(list(equations), list(symbols), dict=True, rational=True)
    except Exception:
        solved = sp.solve(list(equations), list(symbols), dict=True)
    result: list[dict[sp.Symbol, sp.Expr]] = []
    for item in solved:
        if isinstance(item, Mapping):
            result.append({sp.sympify(key): sp.sympify(value) for key, value in item.items()})
    return result


def solve_exact_helper(equations: Sequence[Any], symbols: Sequence[sp.Symbol], route: str = "solve", term_order: str = "lex") -> list[dict[sp.Symbol, sp.Expr]]:
    solutions, _ = solve_exact(equations, symbols, route, term_order)
    return solutions


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
    if isinstance(value, int) and not isinstance(value, bool):
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


def _limits(frontier: Mapping[str, Any], problem: Mapping[str, Any]) -> dict[str, int]:
    declared = dict(problem.get("search_limits") or {})
    extra = dict(frontier.get("extra_parameters") or {})
    def pick(name: str, default: int) -> int:
        for source in (extra, declared):
            if name in source:
                try:
                    return max(0, int(source[name]))
                except (TypeError, ValueError):
                    continue
        return default
    return {
        "max_candidates": pick("max_candidates", _DEFAULT_MAX_CANDIDATES),
        "max_instances": pick("max_instances", _DEFAULT_MAX_INSTANCES),
        "max_point_pairs": pick("max_point_pairs", _DEFAULT_MAX_POINT_PAIRS),
        "max_compositions": pick("max_compositions", _DEFAULT_MAX_COMPOSITIONS),
        "max_enumerations": pick("max_enumerations", _DEFAULT_MAX_ENUMERATIONS),
        "max_solves": pick("max_solves", _DEFAULT_MAX_SOLVES),
        "deadline_seconds": pick("deadline_seconds", _DEFAULT_DEADLINE_SECONDS),
    }


def _frontier_supports(frontier: Mapping[str, Any]) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]:
    raw = frontier.get("support_sets") or ()
    supports: list[tuple[tuple[int, int], ...]] = []
    for support in raw:
        supports.append(tuple((int(first), int(second)) for first, second in support))
    degree = max(0, int(frontier.get("degree_extent", 1)))
    supports = [tuple(item for item in support if item[0] >= 0 and item[1] >= 0 and item[0] + item[1] <= degree) for support in supports]
    if len(supports) >= 2:
        return supports[0], supports[1]
    support = monomial_support_construction(degree)
    return support, support


def _ordered(support: Iterable[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    return tuple(sorted(set((int(a), int(b)) for a, b in support), key=lambda item: (item[0] + item[1], item[0], item[1])))


def _parameterized_map(frontier: Mapping[str, Any], x_symbol: sp.Symbol, y_symbol: sp.Symbol) -> tuple[sp.Expr, sp.Expr, tuple[sp.Symbol, ...]]:
    first_support, second_support = _frontier_supports(frontier)
    symmetry = str(frontier.get("symmetry_mode", "none"))
    scheme = str(frontier.get("composition_scheme", "direct"))
    first_keys = _ordered(first_support)
    second_keys = _ordered(second_support)
    if scheme == "triangular_composition":
        first_keys = _ordered(item for item in first_keys if item[0] == 0)
        second_keys = _ordered(item for item in second_keys if item[1] == 0)
        if not first_keys:
            first_keys = ((0, 2),)
        if not second_keys:
            second_keys = ((2, 0),)
    if symmetry in ("swap", "antisymmetry", "sign"):
        first_coefficient_keys = _ordered(first_keys)
        second_coefficient_keys = _ordered(second_keys)
        shared_keys = _ordered(set(first_coefficient_keys) | {(item[1], item[0]) for item in second_coefficient_keys})
        symbols = tuple(sp.Symbol("c_" + str(index)) for index, _ in enumerate(shared_keys))
        coefficient = {key: symbol for key, symbol in zip(shared_keys, symbols)}
        fresh = [symbol for symbol in symbols if symbol not in coefficient.values()]
        first_terms = [coefficient[key] * x_symbol ** key[0] * y_symbol ** key[1] for key in first_coefficient_keys]
        second_terms = []
        for key in second_coefficient_keys:
            transposed = (key[1], key[0])
            if transposed in coefficient:
                factor = coefficient[transposed]
            else:
                factor = fresh.pop(0) if fresh else sp.Integer(0)
            if symmetry == "antisymmetry":
                second_terms.append(-factor * x_symbol ** key[0] * y_symbol ** key[1])
            elif symmetry == "sign":
                parity = -1 if (key[0] + key[1]) % 2 else 1
                second_terms.append(factor * parity * x_symbol ** key[0] * y_symbol ** key[1])
            else:
                second_terms.append(factor * x_symbol ** key[0] * y_symbol ** key[1])
        first_extra = sum(first_terms) if first_terms else sp.Integer(0)
        second_extra = sum(second_terms) if second_terms else sp.Integer(0)
        first, second = _scheme_base(scheme, x_symbol, y_symbol, first_extra, second_extra)
        used = tuple(symbol for symbol in symbols if symbol in first.free_symbols or symbol in second.free_symbols)
        return sp.expand(first), sp.expand(second), used
    first_symbols = tuple(sp.Symbol("a_" + str(index)) for index, _ in enumerate(first_keys))
    second_symbols = tuple(sp.Symbol("b_" + str(index)) for index, _ in enumerate(second_keys))
    first_extra = sum(symbol * x_symbol ** key[0] * y_symbol ** key[1] for symbol, key in zip(first_symbols, first_keys)) if first_keys else sp.Integer(0)
    second_extra = sum(symbol * x_symbol ** key[0] * y_symbol ** key[1] for symbol, key in zip(second_symbols, second_keys)) if second_keys else sp.Integer(0)
    first, second = _scheme_base(scheme, x_symbol, y_symbol, first_extra, second_extra)
    used = tuple(symbol for symbol in first_symbols + second_symbols if symbol in first.free_symbols or symbol in second.free_symbols)
    return sp.expand(first), sp.expand(second), used


def _scheme_base(scheme: str, x_symbol: sp.Symbol, y_symbol: sp.Symbol, first_extra: sp.Expr, second_extra: sp.Expr) -> tuple[sp.Expr, sp.Expr]:
    if scheme == "identity_perturbation":
        return x_symbol + first_extra, y_symbol + second_extra
    if scheme == "triangular_composition":
        return x_symbol + first_extra, y_symbol + second_extra
    if scheme == "affine_composition":
        matrix = (sp.Symbol("m11"), sp.Symbol("m12"), sp.Symbol("m21"), sp.Symbol("m22"))
        first = matrix[0] * x_symbol + matrix[1] * y_symbol + first_extra
        second = matrix[2] * x_symbol + matrix[3] * y_symbol + second_extra
        return first, second
    if scheme == "layered":
        return x_symbol * (1 + first_extra), y_symbol * (1 + second_extra)
    return first_extra, second_extra


def _allowed_values(frontier: Mapping[str, Any]) -> tuple[sp.Expr, ...]:
    bound = int(frontier.get("coefficient_extent", 1))
    domain = str(frontier.get("exact_domain", "rational"))
    if domain == "algebraic":
        return exact_algebraic_candidate_construction(bound)
    return exact_rational_grid(bound)


def _instantiate_solutions(
    symbols: Sequence[sp.Symbol],
    solutions: Sequence[Mapping[sp.Symbol, Any]],
    grid: Sequence[Any],
    limit: int = _DEFAULT_MAX_INSTANCES,
) -> tuple[list[dict[sp.Symbol, sp.Expr]], bool]:
    ordered_symbols = tuple(symbols)
    instances: list[dict[sp.Symbol, sp.Expr]] = []
    attempts = 0
    for solution in solutions:
        normalized_solution = {sp.sympify(key): sp.sympify(value) for key, value in solution.items()}
        fixed: dict[sp.Symbol, sp.Expr] = {}
        dependent: list[sp.Symbol] = []
        usable = True
        for symbol in ordered_symbols:
            expression = normalized_solution.get(symbol, symbol)
            if expression.free_symbols:
                dependent.append(symbol)
                continue
            value = normalize_expression(expression)
            if value.free_symbols or not is_exact_algebraic_value(value):
                usable = False
                break
            fixed[symbol] = value
        if not usable:
            continue
        parameters: set[sp.Symbol] = set()
        for symbol in dependent:
            parameters.update(normalized_solution.get(symbol, symbol).free_symbols)
        parameters = {item for item in parameters if item not in {sp.Symbol("x"), sp.Symbol("y")}}
        ordered_parameters = tuple(sorted(parameters, key=lambda item: str(item)))
        for values in itertools.product(grid, repeat=len(ordered_parameters)):
            attempts += 1
            if attempts > max(1, int(limit)):
                return instances, True
            if attempts % 32 == 0 and _search_time_exceeded():
                return instances, True
            substitutions = dict(zip(ordered_parameters, values))
            instance = dict(fixed)
            accepted = True
            for symbol in dependent:
                expression = normalized_solution.get(symbol, symbol)
                value = normalize_expression(expression.subs(substitutions))
                if value.free_symbols or not is_exact_algebraic_value(value):
                    accepted = False
                    break
                instance[symbol] = value
            if accepted and set(instance) == set(ordered_symbols):
                instances.append(instance)
    return instances, False


def _point_values(frontier: Mapping[str, Any]) -> tuple[sp.Expr, ...]:
    extra = dict(frontier.get("extra_parameters") or {})
    bound = int(extra.get("point_bound", max(1, int(frontier.get("coefficient_extent", 1)))))
    if str(frontier.get("point_pattern", "")) == "algebraic_grid" or str(frontier.get("exact_domain", "")) == "algebraic":
        return exact_algebraic_candidate_construction(bound)
    return exact_rational_grid(bound)


def _point_pairs(frontier: Mapping[str, Any], limit: int = _DEFAULT_MAX_POINT_PAIRS) -> Iterator[tuple[tuple[sp.Expr, sp.Expr], tuple[sp.Expr, sp.Expr]]]:
    pattern = str(frontier.get("point_pattern", "rational_grid"))
    values = _point_values(frontier)
    zero = sp.Integer(0)
    produced = 0
    if pattern == "axis_pair":
        for value in values:
            if not exact_nonzero(value):
                continue
            yield (zero, zero), (value, zero)
            produced += 1
            if produced >= limit:
                return
            yield (zero, zero), (zero, value)
            produced += 1
            if produced >= limit:
                return
    elif pattern == "origin_pair":
        for first in values:
            for second in values:
                if not (exact_nonzero(first) or exact_nonzero(second)):
                    continue
                yield (zero, zero), (first, second)
                produced += 1
                if produced >= limit:
                    return
    elif pattern == "diagonal_pair":
        for first in values:
            if not exact_nonzero(first):
                continue
            for second in values:
                if exact_nonzero(first - second):
                    yield (first, first), (second, second)
                    produced += 1
                    if produced >= limit:
                        return
    elif pattern == "swapped_pair":
        for first in values:
            for second in values:
                if exact_nonzero(first - second):
                    yield (first, second), (second, first)
                    produced += 1
                    if produced >= limit:
                        return
    elif pattern == "finite_field":
        prime = int(dict(frontier.get("extra_parameters") or {}).get("prime", 2))
        residues = tuple(range(max(2, prime)))
        for point in itertools.product(residues, repeat=2):
            for other in itertools.product(residues, repeat=2):
                if point == other:
                    continue
                yield tuple(exact_lifting_helpers(item, prime) for item in point), tuple(exact_lifting_helpers(item, prime) for item in other)
                produced += 1
                if produced >= limit:
                    return
    else:
        points = tuple((first, second) for first in values for second in values)
        for point in points:
            for other in points:
                if not (exact_nonzero(point[0] - other[0]) or exact_nonzero(point[1] - other[1])):
                    continue
                yield point, other
                produced += 1
                if produced >= limit:
                    return


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
    extra = dict(frontier.get("extra_parameters") or {})
    if not _det_constant_nonzero(first, second, (x_symbol, y_symbol)):
        return None
    if not _collision_exact(first, second, point, other, (x_symbol, y_symbol)):
        return None
    if not (exact_nonzero(point[0] - other[0]) or exact_nonzero(point[1] - other[1])):
        return None
    determinant = sp.expand(sp.diff(first, x_symbol) * sp.diff(second, y_symbol) - sp.diff(first, y_symbol) * sp.diff(second, x_symbol))
    try:
        independent_determinant = derivative_matrix_determinant(first, second, (x_symbol, y_symbol))
    except Exception:
        independent_determinant = determinant
    if not exact_zero(determinant - independent_determinant):
        return None
    if int(extra.get("independent_check_level", 0)) >= 3:
        try:
            coefficient_determinant = differential_determinant_from_expressions(first, second, (x_symbol, y_symbol))
        except Exception:
            return None
        if not exact_zero(determinant - coefficient_determinant):
            return None
    obligations: list[sp.Expr] = []
    obligation_texts: list[str] = []
    for formula in (first, second):
        for obligation in expression_domain_obligations(_expression_text(formula), ("x", "y")):
            obligations.append(obligation)
            obligation_text = _expression_text(obligation)
            if obligation_text not in obligation_texts:
                obligation_texts.append(obligation_text)
    if str(extra.get("denominator_guard", "")) == "strict" and obligations:
        for values in (point, other):
            if not check_obligations_at(obligations, {x_symbol: values[0], y_symbol: values[1]}):
                return None
    return serialize_candidate(
        formulas={"F1": first, "F2": second},
        points={"P": point, "Q": other},
        artifacts={
            "runtime_route": str(frontier.get("kind", "")),
            "runtime_determinant": _expression_text(determinant),
            "frontier_signature": str(frontier.get("unique_signature", "")),
            "domain_obligations": tuple(obligation_texts),
            "composition_scheme": str(frontier.get("composition_scheme", "")),
            "symmetry_mode": str(frontier.get("symmetry_mode", "")),
            "independent_determinant_check": exact_zero(determinant - independent_determinant),
        },
    )


def _search_planar_enumeration(frontier: Mapping[str, Any], limits: Mapping[str, int]) -> dict[str, Any]:
    x_symbol, y_symbol = sp.symbols("x y")
    first, second, symbols = _parameterized_map(frontier, x_symbol, y_symbol)
    grid = _allowed_values(frontier)
    pairs = _point_pairs(frontier, int(limits.get("max_point_pairs", _DEFAULT_MAX_POINT_PAIRS)))
    candidates: list[dict[str, Any]] = []
    maximum = int(limits.get("max_candidates", _DEFAULT_MAX_CANDIDATES))
    enumeration_limit = int(limits.get("max_enumerations", _DEFAULT_MAX_ENUMERATIONS))
    attempted = 0
    truncated = False
    for values in itertools.product(grid, repeat=len(symbols)):
        attempted += 1
        if attempted > enumeration_limit:
            truncated = True
            break
        if attempted % 128 == 0 and _search_time_exceeded():
            truncated = True
            break
        substitutions = dict(zip(symbols, values))
        current_first = sp.expand(first.subs(substitutions))
        current_second = sp.expand(second.subs(substitutions))
        if not _det_constant_nonzero(current_first, current_second, (x_symbol, y_symbol)):
            continue
        for point, other in pairs:
            candidate = _check_and_serialize(current_first, current_second, point, other, frontier)
            if candidate is not None:
                candidates.append(candidate)
                if len(candidates) >= maximum:
                    return {"candidates": candidates, "failures": (), "artifacts": {"route": "coefficient_enumeration", "enumerations_attempted": attempted, "truncated": True}}
    failures = () if candidates else ("no_candidate_in_frontier",)
    return {"candidates": candidates, "failures": failures, "artifacts": {"route": "coefficient_enumeration", "enumerations_attempted": attempted, "truncated": truncated}}


def _search_planar_equation(frontier: Mapping[str, Any], limits: Mapping[str, int]) -> dict[str, Any]:
    x_symbol, y_symbol = sp.symbols("x y")
    first, second, symbols = _parameterized_map(frontier, x_symbol, y_symbol)
    grid = _allowed_values(frontier)
    pairs = list(_point_pairs(frontier, int(limits.get("max_point_pairs", _DEFAULT_MAX_POINT_PAIRS))))
    determinant_equations = determinant_constraint_construction(first, second, (x_symbol, y_symbol))
    extra = dict(frontier.get("extra_parameters") or {})
    route = str(extra.get("solver_route", "solve"))
    term_order = str(extra.get("term_order", "lex"))
    objective = str(frontier.get("elimination_objective", "mixed"))
    candidates: list[dict[str, Any]] = []
    notes: list[str] = []
    maximum = int(limits.get("max_candidates", _DEFAULT_MAX_CANDIDATES))
    instance_limit = int(limits.get("max_instances", _DEFAULT_MAX_INSTANCES))
    solve_limit = max(1, int(limits.get("max_solves", _DEFAULT_MAX_SOLVES)))
    solves_used = 0
    if objective == "coefficients_first":
        return _search_planar_enumeration(frontier, limits)

    def finish(result_notes: list[str], truncated: bool) -> dict[str, Any]:
        if candidates:
            return {"candidates": candidates, "failures": (), "artifacts": {"route": "equation_solving", "objective": objective, "notes": tuple(result_notes), "solves_used": solves_used, "truncated": truncated}}
        return {"candidates": (), "failures": ("no_candidate_in_frontier",), "artifacts": {"route": "equation_solving", "objective": objective, "notes": tuple(result_notes), "solves_used": solves_used, "truncated": truncated}}

    if objective == "determinant_first":
        if solves_used >= solve_limit:
            return finish(["solve_budget_exhausted"], True)
        solves_used += 1
        solutions, route_notes = solve_exact(determinant_equations, symbols, route, term_order)
        notes.extend(route_notes)
        instances, truncated = _instantiate_solutions(symbols, solutions, grid, instance_limit)
        if truncated:
            notes.append("instance_grid_truncated")
        for instance in instances:
            current_first = sp.expand(first.subs(instance))
            current_second = sp.expand(second.subs(instance))
            if not _det_constant_nonzero(current_first, current_second, (x_symbol, y_symbol)):
                continue
            for point, other in pairs:
                candidate = _check_and_serialize(current_first, current_second, point, other, frontier)
                if candidate is not None:
                    candidates.append(candidate)
                    if len(candidates) >= maximum:
                        return finish(notes, True)
        return finish(notes, truncated)

    for point, other in pairs:
        if solves_used >= solve_limit:
            notes.append("solve_budget_exhausted")
            return finish(notes, True)
        if _search_time_exceeded():
            notes.append("search_deadline_reached")
            return finish(notes, True)
        solves_used += 1
        collision_equations = collision_constraint_construction(first, second, point, other, (x_symbol, y_symbol))
        if objective == "collision_first":
            equations = collision_equations
        else:
            equations = determinant_equations + collision_equations
        solutions, route_notes = solve_exact(equations, symbols, route, term_order)
        notes.extend(route_notes)
        instances, truncated = _instantiate_solutions(symbols, solutions, grid, instance_limit)
        if truncated:
            notes.append("instance_grid_truncated")
        for instance in instances:
            current_first = sp.expand(first.subs(instance))
            current_second = sp.expand(second.subs(instance))
            candidate = _check_and_serialize(current_first, current_second, point, other, frontier)
            if candidate is not None:
                candidates.append(candidate)
                if len(candidates) >= maximum:
                    return finish(notes, True)
    return finish(notes, False)


_COMPOSITION_BLOCKS = ("shear_x", "shear_y", "fold_x", "fold_y", "swap", "scale")


def _apply_composition_block(name: str, current_first: sp.Expr, current_second: sp.Expr, first_value: Any, second_value: Any) -> tuple[sp.Expr, sp.Expr]:
    if name == "shear_x":
        return sp.expand(current_first + first_value * current_second ** 2), current_second
    if name == "shear_y":
        return current_first, sp.expand(current_second + second_value * current_first ** 2)
    if name == "fold_x":
        return sp.expand(current_first ** 2 + first_value * current_second), current_second
    if name == "fold_y":
        return current_first, sp.expand(current_second ** 2 + second_value * current_first)
    if name == "swap":
        return current_second, current_first
    return sp.expand(first_value * current_first), sp.expand(second_value * current_second)


def _search_planar_composition(frontier: Mapping[str, Any], limits: Mapping[str, int]) -> dict[str, Any]:
    x_symbol, y_symbol = sp.symbols("x y")
    grid = _allowed_values(frontier)
    pairs = list(_point_pairs(frontier, int(limits.get("max_point_pairs", _DEFAULT_MAX_POINT_PAIRS))))
    candidates: list[dict[str, Any]] = []
    maximum = int(limits.get("max_candidates", _DEFAULT_MAX_CANDIDATES))
    composition_limit = int(limits.get("max_compositions", _DEFAULT_MAX_COMPOSITIONS))
    length_extent = max(1, min(3, int(frontier.get("degree_extent", 1))))
    attempted = 0
    truncated = False
    for length in range(1, length_extent + 1):
        for values in itertools.product(grid, repeat=2 * length):
            attempted += 1
            if attempted > composition_limit:
                truncated = True
                break
            if attempted % 128 == 0 and _search_time_exceeded():
                truncated = True
                break
            iterator = iter(values)
            current_first = x_symbol
            current_second = y_symbol
            for step in range(length):
                first_value = next(iterator)
                second_value = next(iterator)
                block = _COMPOSITION_BLOCKS[(step + length) % len(_COMPOSITION_BLOCKS)]
                current_first, current_second = _apply_composition_block(block, current_first, current_second, first_value, second_value)
            for point, other in pairs:
                candidate = _check_and_serialize(current_first, current_second, point, other, frontier)
                if candidate is not None:
                    candidates.append(candidate)
                    if len(candidates) >= maximum:
                        return {"candidates": candidates, "failures": (), "artifacts": {"route": "composition", "compositions_attempted": attempted, "truncated": truncated}}
        if truncated:
            break
    failures = () if candidates else ("no_candidate_in_frontier",)
    return {"candidates": candidates, "failures": failures, "artifacts": {"route": "composition", "compositions_attempted": attempted, "truncated": truncated}}


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


def _search_planar_modular(frontier: Mapping[str, Any], limits: Mapping[str, int]) -> dict[str, Any]:
    x_symbol, y_symbol = sp.symbols("x y")
    prime = int(dict(frontier.get("extra_parameters") or {}).get("prime", 2))
    first, second, symbols = _parameterized_map(frontier, x_symbol, y_symbol)
    candidates: list[dict[str, Any]] = []
    maximum = int(limits.get("max_candidates", _DEFAULT_MAX_CANDIDATES))
    enumeration_limit = int(limits.get("max_enumerations", _DEFAULT_MAX_ENUMERATIONS))
    residues = tuple(range(prime))
    determinant = sp.expand(sp.diff(first, x_symbol) * sp.diff(second, y_symbol) - sp.diff(first, y_symbol) * sp.diff(second, x_symbol))
    try:
        determinant_terms = [(monomial, sp.expand(coefficient)) for monomial, coefficient in sp.Poly(determinant, x_symbol, y_symbol, extension=True).terms()]
    except Exception:
        determinant_terms = [((0, 0), determinant)]
    prescreen_hits = 0
    rejected_lifts = 0
    passing: list[dict[sp.Symbol, int]] = []
    attempted = 0
    truncated = False
    for values in itertools.product(residues, repeat=len(symbols)):
        attempted += 1
        if attempted > enumeration_limit:
            truncated = True
            break
        if attempted % 256 == 0 and _search_time_exceeded():
            truncated = True
            break
        substitutions = dict(zip(symbols, values))
        constant = 0
        constant_determinant = True
        for monomial, coefficient in determinant_terms:
            value = int(coefficient.subs(substitutions)) % prime
            if monomial == (0, 0):
                constant = value
            elif value:
                constant_determinant = False
                break
        if not constant_determinant or constant % prime == 0:
            continue
        passing.append(substitutions)
    finite_points = tuple((a, b) for a in residues for b in residues)
    pair_limit = int(limits.get("max_point_pairs", _DEFAULT_MAX_POINT_PAIRS))
    point_pairs: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for point in finite_points:
        for other in finite_points:
            if point == other:
                continue
            point_pairs.append((point, other))
            if len(point_pairs) >= pair_limit:
                break
        if len(point_pairs) >= pair_limit:
            break
    grid = _allowed_values(frontier)
    for substitutions in passing:
        if _search_time_exceeded():
            truncated = True
            break
        current_first = sp.expand(first.subs(substitutions))
        current_second = sp.expand(second.subs(substitutions))
        for point, other in point_pairs:
            if _eval_mod(current_first, point[0], point[1], prime, (x_symbol, y_symbol)) != _eval_mod(current_first, other[0], other[1], prime, (x_symbol, y_symbol)):
                continue
            if _eval_mod(current_second, point[0], point[1], prime, (x_symbol, y_symbol)) != _eval_mod(current_second, other[0], other[1], prime, (x_symbol, y_symbol)):
                continue
            prescreen_hits += 1
            lifted = {symbol: exact_lifting_helpers(value, prime) for symbol, value in substitutions.items()}
            lifted_first = sp.expand(first.subs(lifted))
            lifted_second = sp.expand(second.subs(lifted))
            lifted_point = tuple(exact_lifting_helpers(value, prime) for value in point)
            lifted_other = tuple(exact_lifting_helpers(value, prime) for value in other)
            candidate = _check_and_serialize(lifted_first, lifted_second, lifted_point, lifted_other, frontier)
            if candidate is not None:
                candidates.append(candidate)
                if len(candidates) >= maximum:
                    return {"candidates": candidates, "failures": (), "artifacts": {"route": "modular_prescreen", "prime": prime, "prescreen_hits": prescreen_hits, "rejected_lifts": rejected_lifts, "enumerations_attempted": attempted, "truncated": truncated}}
                continue
            rejected_lifts += 1
            collision_equations = collision_constraint_construction(first, second, lifted_point, lifted_other, (x_symbol, y_symbol))
            determinant_equations = determinant_constraint_construction(first, second, (x_symbol, y_symbol))
            solutions, _ = solve_exact(determinant_equations + collision_equations, symbols, "solve", "lex")
            instances, _ = _instantiate_solutions(symbols, solutions, grid, int(limits.get("max_instances", _DEFAULT_MAX_INSTANCES)))
            for instance in instances:
                exact_first = sp.expand(first.subs(instance))
                exact_second = sp.expand(second.subs(instance))
                exact_candidate = _check_and_serialize(exact_first, exact_second, lifted_point, lifted_other, frontier)
                if exact_candidate is not None:
                    candidates.append(exact_candidate)
                    if len(candidates) >= maximum:
                        return {"candidates": candidates, "failures": (), "artifacts": {"route": "modular_prescreen", "prime": prime, "prescreen_hits": prescreen_hits, "rejected_lifts": rejected_lifts, "enumerations_attempted": attempted, "truncated": truncated}}
    failures = () if candidates else ("no_candidate_in_frontier",)
    return {"candidates": candidates, "failures": failures, "artifacts": {"route": "modular_prescreen", "prime": prime, "prescreen_hits": prescreen_hits, "rejected_lifts": rejected_lifts, "enumerations_attempted": attempted, "truncated": truncated}}


_FINITE_FIELD_FAMILIES = ("frobenius_pair", "frobenius_shear", "frobenius_y_shear", "frobenius_mixed_shear")


def _finite_field_map_expressions(family: str, prime: int, coefficients: Sequence[int], x_symbol: sp.Symbol, y_symbol: sp.Symbol) -> tuple[sp.Expr, sp.Expr] | None:
    a = int(coefficients[0]) % int(prime) if len(coefficients) > 0 else 0
    b = int(coefficients[1]) % int(prime) if len(coefficients) > 1 else 0
    power = int(prime)
    if family == "frobenius_pair":
        return sp.expand(x_symbol + a * y_symbol ** power), sp.expand(y_symbol + b * x_symbol ** power)
    if family == "frobenius_shear":
        return sp.expand(x_symbol + a * x_symbol ** power), y_symbol
    if family == "frobenius_y_shear":
        return x_symbol, sp.expand(y_symbol + b * y_symbol ** power)
    if family == "frobenius_mixed_shear":
        return sp.expand(x_symbol + a * x_symbol ** power * y_symbol ** (power - 1)), y_symbol
    return None


def _finite_field_determinant_constant(first: sp.Expr, second: sp.Expr, prime: int, variables: Sequence[sp.Symbol]) -> tuple[int, bool] | None:
    x_symbol, y_symbol = variables
    determinant = sp.expand(sp.diff(first, x_symbol) * sp.diff(second, y_symbol) - sp.diff(first, y_symbol) * sp.diff(second, x_symbol))
    try:
        coefficients = polynomial_coefficient_dictionary(determinant, (x_symbol, y_symbol))
    except Exception:
        return None
    constant = 0
    for monomial, coefficient in coefficients.items():
        reduced = int(coefficient) % int(prime)
        if monomial == (0, 0):
            constant = reduced
        elif reduced:
            return (constant, False)
    return (constant, constant % int(prime) != 0)


def _finite_field_reduce_polynomial(coefficients: Mapping[tuple[int, int], int], prime: int) -> dict[tuple[int, int], int]:
    return {key: int(value) % int(prime) for key, value in coefficients.items() if int(value) % int(prime)}


def _finite_field_direct_evaluation(coefficients: Mapping[tuple[int, int], int], point: Sequence[int], prime: int, modulus: Sequence[int]) -> tuple[int, ...]:
    total = finite_field_reduce((0,), prime, modulus)
    for monomial, coefficient in coefficients.items():
        value = finite_field_reduce((int(coefficient) % int(prime),), prime, modulus)
        if any(value):
            term = finite_field_multiply(value, finite_field_power(point[0], monomial[0], prime, modulus), prime, modulus) if monomial[0] else value
            if monomial[1]:
                term = finite_field_multiply(term, finite_field_power(point[1], monomial[1], prime, modulus), prime, modulus)
            total = finite_field_add(total, term, prime)
    return finite_field_reduce(total, prime, modulus)


def _finite_field_horner_evaluation(coefficients: Mapping[tuple[int, int], int], point: Sequence[int], prime: int, modulus: Sequence[int]) -> tuple[int, ...]:
    x_value = finite_field_reduce(tuple(point[0]), prime, modulus)
    y_value = finite_field_reduce(tuple(point[1]), prime, modulus)
    maximum_y = max((monomial[1] for monomial in coefficients), default=0)
    maximum_x = max((monomial[0] for monomial in coefficients), default=0)
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


def _search_finite_field_jacobian(frontier: Mapping[str, Any], limits: Mapping[str, int]) -> dict[str, Any]:
    x_symbol, y_symbol = sp.symbols("x y")
    extra = dict(frontier.get("extra_parameters") or {})
    prime = int(extra.get("prime", 2))
    degree = int(extra.get("extension_degree", 1))
    families = tuple(str(item) for item in (extra.get("map_families") or _FINITE_FIELD_FAMILIES))
    if not families:
        families = _FINITE_FIELD_FAMILIES
    family_index = max(0, int(extra.get("family_index", 0)))
    coefficient_offset = max(0, int(extra.get("coefficient_offset", 0)))
    maximum_maps = max(1, int(extra.get("max_maps", 64)))
    point_budget = max(4, int(extra.get("max_points", limits.get("max_enumerations", _DEFAULT_MAX_ENUMERATIONS))))
    modulus = irreducible_modulus_polynomial(prime, degree)
    elements = finite_field_elements(prime, degree)
    field_order = prime ** degree
    artifacts: dict[str, Any] = {
        "route": "finite_field_jacobian_lattice",
        "field_characteristic": prime,
        "field_extension_degree": degree,
        "field_order": field_order,
        "field_modulus": list(modulus),
        "map_families": list(families),
        "family_index": family_index,
        "coefficient_offset": coefficient_offset,
        "maps_examined": 0,
        "coefficient_vectors_examined": 0,
        "points_examined": 0,
        "point_budget": point_budget,
        "map_attempts_truncated": False,
        "point_scan_truncated": False,
    }
    coefficient_vectors: list[tuple[int, int]] = []
    for value in range(max(1, prime * prime)):
        first_coefficient = value % prime
        second_coefficient = (value // prime) % prime
        coefficient_vectors.append((first_coefficient, second_coefficient))
    if coefficient_vectors:
        rotated = coefficient_vectors[coefficient_offset % len(coefficient_vectors):] + coefficient_vectors[: coefficient_offset % len(coefficient_vectors)]
    else:
        rotated = []
    ordered_families = families[family_index % len(families):] + families[: family_index % len(families)]
    attempts = 0
    for family in ordered_families:
        for coefficients in rotated:
            attempts += 1
            if attempts > maximum_maps:
                artifacts["map_attempts_truncated"] = True
                break
            expressions = _finite_field_map_expressions(family, prime, coefficients, x_symbol, y_symbol)
            if expressions is None:
                continue
            first, second = expressions
            determinant = _finite_field_determinant_constant(first, second, prime, (x_symbol, y_symbol))
            if determinant is None:
                continue
            artifacts["maps_examined"] = int(artifacts["maps_examined"]) + 1
            artifacts["coefficient_vectors_examined"] = int(artifacts["coefficient_vectors_examined"]) + 1
            constant, constant_determinant = determinant
            if not constant_determinant:
                continue
            first_coefficients = _finite_field_reduce_polynomial(polynomial_coefficient_dictionary(first, (x_symbol, y_symbol)), prime)
            second_coefficients = _finite_field_reduce_polynomial(polynomial_coefficient_dictionary(second, (x_symbol, y_symbol)), prime)
            images: dict[tuple[tuple[int, ...], tuple[int, ...]], tuple[tuple[int, ...], tuple[int, ...]]] = {}
            collision: tuple[tuple[tuple[int, ...], tuple[int, ...]], tuple[tuple[int, ...], tuple[int, ...]]] | None = None
            scanned = 0
            for point in itertools.product(elements, repeat=2):
                if scanned >= point_budget:
                    artifacts["point_scan_truncated"] = True
                    break
                if _search_time_exceeded():
                    artifacts["point_scan_truncated"] = True
                    break
                scanned += 1
                image = (
                    _finite_field_horner_evaluation(first_coefficients, point, prime, modulus),
                    _finite_field_horner_evaluation(second_coefficients, point, prime, modulus),
                )
                previous = images.get(image)
                if previous is not None and previous != point:
                    collision = (previous, point)
                    break
                images.setdefault(image, point)
            artifacts["points_examined"] = int(artifacts["points_examined"]) + scanned
            if collision is None:
                continue
            point, other = collision
            direct_first_point = _finite_field_direct_evaluation(first_coefficients, point, prime, modulus)
            direct_second_point = _finite_field_direct_evaluation(second_coefficients, point, prime, modulus)
            direct_first_other = _finite_field_direct_evaluation(first_coefficients, other, prime, modulus)
            direct_second_other = _finite_field_direct_evaluation(second_coefficients, other, prime, modulus)
            independent_first_point = _finite_field_horner_evaluation(first_coefficients, point, prime, modulus)
            independent_second_point = _finite_field_horner_evaluation(second_coefficients, point, prime, modulus)
            independent_first_other = _finite_field_horner_evaluation(first_coefficients, other, prime, modulus)
            independent_second_other = _finite_field_horner_evaluation(second_coefficients, other, prime, modulus)
            if direct_first_point != independent_first_point or direct_second_point != independent_second_point:
                continue
            if direct_first_other != independent_first_other or direct_second_other != independent_second_other:
                continue
            if direct_first_point != direct_first_other or direct_second_point != direct_second_other:
                continue
            candidate = serialize_candidate(
                formulas={"F1": first, "F2": second},
                points={
                    "P": tuple(finite_field_element_text(element_value, prime) for element_value in point),
                    "Q": tuple(finite_field_element_text(element_value, prime) for element_value in other),
                },
                artifacts={
                    "runtime_route": str(frontier.get("kind", "")),
                    "frontier_signature": str(frontier.get("unique_signature", "")),
                    "map_family": family,
                    "map_coefficients": [int(item) for item in coefficients],
                    "field_characteristic": prime,
                    "field_extension_degree": degree,
                    "field_order": field_order,
                    "field_modulus": list(modulus),
                    "determinant_constant_mod_characteristic": int(constant),
                    "points_examined": int(artifacts["points_examined"]),
                    "maps_examined": int(artifacts["maps_examined"]),
                    "map_attempts_truncated": bool(artifacts["map_attempts_truncated"]),
                    "point_scan_truncated": bool(artifacts["point_scan_truncated"]),
                    "image_at_point": [
                        finite_field_element_text(direct_first_point, prime),
                        finite_field_element_text(direct_second_point, prime),
                    ],
                    "image_at_other": [
                        finite_field_element_text(direct_first_other, prime),
                        finite_field_element_text(direct_second_other, prime),
                    ],
                    "runtime_determinant": _expression_text(sp.expand(sp.diff(first, x_symbol) * sp.diff(second, y_symbol) - sp.diff(first, y_symbol) * sp.diff(second, x_symbol))),
                },
            )
            artifacts["candidate_family"] = family
            artifacts["candidate_coefficients"] = [int(item) for item in coefficients]
            artifacts["candidate_point"] = list(point)
            artifacts["candidate_other"] = list(other)
            artifacts["candidate_constant"] = int(constant)
            return {"candidates": [candidate], "failures": (), "artifacts": artifacts}
        if attempts > maximum_maps:
            break
    return {"candidates": (), "failures": ("no_finite_field_collision_in_frontier",), "artifacts": artifacts}


def _search_finite_field_jacobian_frontier(frontier: Mapping[str, Any], problem: Mapping[str, Any]) -> dict[str, Any]:
    return _search_finite_field_jacobian(frontier, _limits(frontier, problem))


def search_planar_frontier(frontier: Mapping[str, Any], problem: Mapping[str, Any] | None = None) -> dict[str, Any]:
    limits = _limits(frontier, problem or {})
    kind = str(frontier.get("kind", ""))
    scheme = str(frontier.get("composition_scheme", ""))
    if kind == "finite_field_prescreen" or str(frontier.get("exact_domain", "")) == "modular_prescreen":
        return _search_planar_modular(frontier, limits)
    if kind == "composition_perturbation" or scheme == "triangular_composition":
        return _search_planar_composition(frontier, limits)
    return _search_planar_equation(frontier, limits)


def _filtered_values(values: Sequence[Any], constraints: Sequence[str]) -> tuple[Any, ...]:
    filtered = list(values)
    if "integer" in constraints:
        filtered = [item for item in filtered if getattr(item, "is_integer", False) is True]
    if "rational" in constraints:
        filtered = [item for item in filtered if getattr(item, "is_rational", False) is True]
    if "positive" in constraints:
        filtered = [item for item in filtered if getattr(item, "is_positive", False) is True]
    if "negative" in constraints:
        filtered = [item for item in filtered if getattr(item, "is_negative", False) is True]
    if "nonzero" in constraints:
        filtered = [item for item in filtered if not exact_zero(item)]
    if "nonnegative" in constraints:
        filtered = [item for item in filtered if getattr(item, "is_nonnegative", False) is True]
    if "nonpositive" in constraints:
        filtered = [item for item in filtered if getattr(item, "is_nonpositive", False) is True]
    return tuple(filtered)


def search_algebraic_assignment(frontier: Mapping[str, Any], problem: Mapping[str, Any]) -> dict[str, Any]:
    target = dict(problem.get("algebraic_identity") or {})
    variables = tuple(str(item) for item in target.get("variables", ()))
    left_text = str(target.get("left_expression", "0"))
    right_text = str(target.get("right_expression", "0"))
    constraints = tuple(str(item) for item in target.get("constraints", ()))
    left_expression = exact_parse_expression(left_text, variables)
    right_expression = exact_parse_expression(right_text, variables)
    symbol_map = {name: sp.Symbol(name) for name in variables}
    difference = sp.expand(left_expression - right_expression)
    if not variables:
        if exact_zero(difference):
            return {"candidates": (), "failures": ("identity_holds_symbolically",), "artifacts": {"route": "assignment_grid", "proved": True}}
        if not check_denominator_nonzero_obligations((left_expression, right_expression)):
            return {"candidates": (), "failures": ("denominator_obligation_failed",), "artifacts": {"route": "assignment_grid"}}
        return {"candidates": [serialize_candidate(artifacts={"left_value": _expression_text(left_expression), "right_value": _expression_text(right_expression)})], "failures": (), "artifacts": {"route": "assignment_grid"}}
    if exact_zero(difference):
        return {"candidates": (), "failures": ("identity_holds_symbolically",), "artifacts": {"route": "assignment_grid", "proved": True}}
    raw_values = exact_algebraic_candidate_construction(int(frontier.get("coefficient_extent", 1))) if str(frontier.get("exact_domain", "")) == "algebraic" else exact_rational_grid(int(frontier.get("coefficient_extent", 1)))
    values = _filtered_values(raw_values, constraints)
    obligations: list[Any] = []
    for text in tuple(str(item) for item in target.get("left_obligations", ())) + tuple(str(item) for item in target.get("right_obligations", ())):
        try:
            obligations.append(exact_parse_expression(text, variables))
        except Exception:
            continue
    candidates: list[dict[str, Any]] = []
    limits = _limits(frontier, problem)
    maximum = max(1, int(limits.get("max_candidates", 1)))
    for assignment_values in itertools.product(values, repeat=len(variables)):
        if _search_time_exceeded():
            break
        substitutions = {symbol_map[name]: value for name, value in zip(variables, assignment_values)}
        if obligations:
            failed = False
            for obligation in obligations:
                try:
                    evaluated = normalize_expression(obligation.subs(substitutions))
                except Exception:
                    failed = True
                    break
                if not exact_nonzero(evaluated):
                    failed = True
                    break
            if failed:
                continue
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
            if len(candidates) >= maximum:
                break
    failures = () if candidates else ("no_counterassignment_in_frontier",)
    return {"candidates": candidates, "failures": failures, "artifacts": {"route": "assignment_grid", "grid_size": len(values), "constraints": constraints, "bounded_grid": True, "exhaustive": False}}


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


def alternating_group_table(degree: int) -> tuple[tuple[int, ...], ...]:
    permutations = [item for item in _permutations(degree) if _permutation_sign(item) == 0]
    index = {permutation: position for position, permutation in enumerate(permutations)}
    table: list[tuple[int, ...]] = []
    for left in permutations:
        row: list[int] = []
        for right in permutations:
            composed = tuple(left[right[item]] for item in range(degree))
            row.append(index[composed])
        table.append(tuple(row))
    return tuple(table)


def _permutation_sign(permutation: tuple[int, ...]) -> int:
    sign = 0
    for index in range(len(permutation)):
        for other in range(index + 1, len(permutation)):
            if permutation[index] > permutation[other]:
                sign += 1
    return sign % 2


def direct_product_group_table(left_table: Sequence[Sequence[int]], right_table: Sequence[Sequence[int]]) -> tuple[tuple[int, ...], ...]:
    return _direct_product_tables((left_table, right_table))


def _direct_product_tables(tables: Sequence[Sequence[Sequence[int]]]) -> tuple[tuple[int, ...], ...]:
    usable = [tuple(tuple(int(item) for item in row) for row in table) for table in tables if len(table)]
    if not usable:
        return cyclic_group_table(1)
    if len(usable) == 1:
        return usable[0]
    orders = [len(table) for table in usable]
    elements = tuple(itertools.product(*[range(order) for order in orders]))
    index = {element: position for position, element in enumerate(elements)}
    rows: list[tuple[int, ...]] = []
    for left in elements:
        row: list[int] = []
        for right in elements:
            composed = tuple(usable[position][left[position]][right[position]] for position in range(len(usable)))
            row.append(index[composed])
        rows.append(tuple(row))
    return tuple(rows)


def dihedral_group_table(degree: int) -> tuple[tuple[int, ...], ...]:
    size = max(1, int(degree))
    elements = tuple((rotation, reflection) for rotation in range(size) for reflection in range(2))
    index = {element: position for position, element in enumerate(elements)}
    rows: list[tuple[int, ...]] = []
    for left in elements:
        row: list[int] = []
        for right in elements:
            rotation = (left[0] + (right[0] if left[1] == 0 else -right[0])) % size
            reflection = (left[1] + right[1]) % 2
            row.append(index[(rotation, reflection)])
        rows.append(tuple(row))
    return tuple(rows)


def dicyclic_group_table(degree: int) -> tuple[tuple[int, ...], ...]:
    size = max(2, int(degree))
    modulus = 2 * size
    elements = tuple((rotation, reflection) for rotation in range(modulus) for reflection in range(2))
    index = {element: position for position, element in enumerate(elements)}
    rows: list[tuple[int, ...]] = []
    for left in elements:
        row: list[int] = []
        for right in elements:
            factor = right[0] if left[1] == 0 else -right[0]
            rotation = (left[0] + factor + (size if left[1] == 1 and right[1] == 1 else 0)) % modulus
            reflection = (left[1] + right[1]) % 2
            row.append(index[(rotation, reflection)])
        rows.append(tuple(row))
    return tuple(rows)


def semidirect_product_group_table(modulus: int, extension: int, action: int) -> tuple[tuple[int, ...], ...]:
    left_order = max(1, int(modulus))
    right_order = max(1, int(extension))
    multiplier = int(action) % left_order
    elements = tuple((first, second) for first in range(left_order) for second in range(right_order))
    index = {element: position for position, element in enumerate(elements)}
    rows: list[tuple[int, ...]] = []
    for left in elements:
        row: list[int] = []
        for right in elements:
            factor = pow(multiplier, left[1], left_order)
            first = (left[0] + factor * right[0]) % left_order
            second = (left[1] + right[1]) % right_order
            row.append(index[(first, second)])
        rows.append(tuple(row))
    return tuple(rows)


def _integer_partitions(value: int) -> tuple[tuple[int, ...], ...]:
    if value <= 0:
        return ((),)
    results: list[tuple[int, ...]] = []

    def build(remaining: int, maximum: int, current: tuple[int, ...]) -> None:
        if remaining == 0:
            results.append(current)
            return
        for part in range(min(remaining, maximum), 0, -1):
            build(remaining - part, part, current + (part,))

    build(value, value, ())
    return tuple(results)


def _prime_factorization(value: int) -> tuple[tuple[int, int], ...]:
    order = max(1, int(value))
    factors: list[tuple[int, int]] = []
    divisor = 2
    while divisor * divisor <= order:
        if order % divisor == 0:
            exponent = 0
            while order % divisor == 0:
                order //= divisor
                exponent += 1
            factors.append((divisor, exponent))
        divisor += 1 if divisor == 2 else 2
    if order > 1:
        factors.append((order, 1))
    return tuple(factors)


def _abelian_group_tables(order: int) -> tuple[tuple[tuple[int, ...], ...], ...]:
    factors = _prime_factorization(order)
    if not factors:
        return (cyclic_group_table(1),)
    choices: list[tuple[tuple[int, ...], ...]] = []
    for prime, exponent in factors:
        variants: list[tuple[int, ...]] = []
        for partition in _integer_partitions(exponent):
            variants.append(tuple(prime ** part for part in partition))
        choices.append(tuple(variants))
    tables: list[tuple[tuple[int, ...], ...]] = []
    for combination in itertools.product(*choices):
        cyclic_orders: list[int] = []
        for variant in combination:
            cyclic_orders.extend(variant)
        tables.append(_direct_product_tables(tuple(cyclic_group_table(size) for size in cyclic_orders)))
    return tuple(tables)


def _element_orders(table: Sequence[Sequence[int]]) -> tuple[int, ...]:
    identity = 0
    orders: list[int] = []
    for element in range(len(table)):
        current = element
        count = 1
        while current != identity and count <= len(table) + 1:
            current = table[current][element]
            count += 1
        orders.append(count)
    return tuple(sorted(orders))


def _group_invariants(table: Sequence[Sequence[int]]) -> tuple[Any, ...]:
    order = len(table)
    abelian = all(table[left][right] == table[right][left] for left in range(order) for right in range(order))
    return (order, _element_orders(table), abelian)


def finite_group_table_construction_helpers(max_order: int) -> Iterator[tuple[str, tuple[tuple[int, ...], ...], int]]:
    extent = max(1, int(max_order))
    seen: set[tuple[Any, ...]] = set()

    def offer(name: str, table: Sequence[Sequence[int]]) -> bool:
        if not table or len(table) > extent:
            return False
        signature = _group_invariants(table)
        if signature in seen:
            return False
        seen.add(signature)
        return True

    for order in range(1, extent + 1):
        for table in _abelian_group_tables(order):
            if offer("abelian_" + str(order), table):
                yield ("abelian_" + str(order), table, 0)
    for degree in range(3, extent // 2 + 1):
        table = dihedral_group_table(degree)
        if offer("dihedral_" + str(degree), table):
            yield ("dihedral_" + str(degree), table, 0)
    for degree in range(2, extent // 4 + 1):
        table = dicyclic_group_table(degree)
        if offer("dicyclic_" + str(degree), table):
            yield ("dicyclic_" + str(degree), table, 0)
    for modulus in range(2, extent + 1):
        for extension in range(2, extent + 1):
            if modulus * extension > extent:
                continue
            for action in range(modulus):
                if math.gcd(action, modulus) != 1:
                    continue
                if pow(action, extension, modulus) != 1:
                    continue
                table = semidirect_product_group_table(modulus, extension, action)
                if offer("semidirect_" + str(modulus) + "_" + str(extension) + "_" + str(action), table):
                    yield ("semidirect_" + str(modulus) + "_" + str(extension) + "_" + str(action), table, 0)
    for degree in range(3, 8):
        order = math.factorial(degree)
        if order <= extent:
            table = symmetric_group_table(degree)
            if offer("symmetric_" + str(degree), table):
                yield ("symmetric_" + str(degree), table, 0)
        if degree >= 4 and order // 2 <= extent:
            table = alternating_group_table(degree)
            if offer("alternating_" + str(degree), table):
                yield ("alternating_" + str(degree), table, 0)


def finite_group_table_construction_helpers_serialized(max_order: int) -> tuple[dict[str, Any], ...]:
    result = []
    for name, table, identity in finite_group_table_construction_helpers(max_order):
        result.append({"name": name, "table": [list(row) for row in table], "identity": identity})
    return tuple(result)


def search_finite_group_identity(frontier: Mapping[str, Any], problem: Mapping[str, Any]) -> dict[str, Any]:
    target = dict(problem.get("finite_group_identity") or {})
    variables = tuple(str(item) for item in target.get("variables", ()))
    left_word = str(target.get("left_word", ""))
    right_word = str(target.get("right_word", ""))
    target_max_order = max(1, int(target.get("max_order", 6)))
    frontier_order = max(1, int(frontier.get("degree_extent", target_max_order)))
    extra = dict(frontier.get("extra_parameters") or {})
    if "max_order" in extra:
        frontier_order = min(frontier_order, max(1, int(extra["max_order"])))
    max_order = max(1, min(target_max_order, frontier_order))
    candidates: list[dict[str, Any]] = []
    assignments_examined = 0
    families_examined = 0
    for name, table, identity in finite_group_table_construction_helpers(max_order):
        if _search_time_exceeded():
            return {"candidates": (), "failures": ("no_countermodel_in_frontier",), "artifacts": {"route": "finite_group_tables", "families_examined": families_examined, "assignments_examined": assignments_examined, "max_order": max_order, "truncated": True}}
        families_examined += 1
        order = len(table)
        for values in itertools.product(range(order), repeat=len(variables)):
            assignments_examined += 1
            assignment = {variable: value for variable, value in zip(variables, values)}
            try:
                left_value = evaluate_group_word(left_word, assignment, table, identity)
                right_value = evaluate_group_word(right_word, assignment, table, identity)
                independent_left = evaluate_group_word_by_postfix(left_word, assignment, table, identity)
                independent_right = evaluate_group_word_by_postfix(right_word, assignment, table, identity)
            except Exception:
                continue
            if left_value != right_value and independent_left == left_value and independent_right == right_value:
                candidates.append(
                    serialize_candidate(
                        assignments=assignment,
                        finite_structures={"operation_table": [list(row) for row in table], "identity": identity, "elements": list(range(order))},
                        artifacts={
                            "group_family": name,
                            "left_value": left_value,
                            "right_value": right_value,
                            "order": order,
                            "order_bound_respected": order <= target_max_order,
                            "independent_word_evaluation": True,
                        },
                    )
                )
                return {"candidates": candidates, "failures": (), "artifacts": {"route": "finite_group_tables", "families_examined": families_examined, "assignments_examined": assignments_examined, "max_order": max_order}}
    return {"candidates": (), "failures": ("no_countermodel_in_frontier",), "artifacts": {"route": "finite_group_tables", "families_examined": families_examined, "assignments_examined": assignments_examined, "max_order": max_order}}


def run_generated_search(frontier: Mapping[str, Any], problem: Mapping[str, Any], source_fingerprint: str = "") -> dict[str, Any]:
    try:
        _set_search_deadline(_limits(frontier, problem).get("deadline_seconds", _DEFAULT_DEADLINE_SECONDS))
        problem_kind = str(problem.get("kind", ""))
        frontier_signature = str(frontier.get("unique_signature", ""))
        provenance = {
            "problem_kind": problem_kind,
            "frontier_signature": frontier_signature,
            "source_fingerprint": str(source_fingerprint),
        }
        if problem_kind == "planar_constant_determinant_collision":
            result = search_planar_frontier(frontier, problem)
        elif problem_kind == "finite_field_jacobian_refutation":
            result = _search_finite_field_jacobian_frontier(frontier, problem)
        elif problem_kind == "finite_group_identity_countermodel":
            result = search_finite_group_identity(frontier, problem)
        else:
            result = search_algebraic_assignment(frontier, problem)
        artifacts = dict(result.get("artifacts") or {})
        artifacts["provenance"] = provenance
        return {
            "candidates": result.get("candidates") or (),
            "failures": result.get("failures") or (),
            "artifacts": artifacts,
            "provenance": provenance,
        }
    except Exception as exception:
        _SEARCH_DEADLINE[0] = None
        return {
            "candidates": (),
            "failures": (type(exception).__name__,),
            "artifacts": {"exception": repr(exception)[:500], "provenance": {"problem_kind": str(problem.get("kind", "")), "frontier_signature": str(frontier.get("unique_signature", "")), "source_fingerprint": str(source_fingerprint)}},
            "provenance": {"problem_kind": str(problem.get("kind", "")), "frontier_signature": str(frontier.get("unique_signature", "")), "source_fingerprint": str(source_fingerprint)},
        }
    finally:
        _SEARCH_DEADLINE[0] = None
