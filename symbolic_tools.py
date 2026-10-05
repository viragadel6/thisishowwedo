from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

import sympy as sp
from sympy.parsing.sympy_parser import (
    auto_symbol,
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

_SUPERSCRIPT_DIGITS = {
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
    "⁻": "-",
    "⁺": "+",
}
_PARSE_TRANSFORMATIONS = tuple(item for item in standard_transformations if item is not auto_symbol) + (
    implicit_multiplication_application,
    convert_xor,
)


def _replace_superscript_runs(text: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character in _SUPERSCRIPT_DIGITS:
            collected: list[str] = []
            while index < len(text) and text[index] in _SUPERSCRIPT_DIGITS:
                collected.append(_SUPERSCRIPT_DIGITS[text[index]])
                index += 1
            output.append("**" + "".join(collected))
        else:
            output.append(character)
            index += 1
    return "".join(output)


def normalize_math_text(text: str) -> str:
    replacements = {
        "−": "-",
        "–": "-",
        "—": "-",
        "×": "*",
        "·": "*",
        "÷": "/",
        "√": "sqrt",
    }
    value = str(text)
    for source, target in replacements.items():
        value = value.replace(source, target)
    return _replace_superscript_runs(value)


def create_symbols(names: Sequence[str]) -> tuple[sp.Symbol, ...]:
    return tuple(sp.Symbol(str(name)) for name in names)


def exact_parse_expression(text: str, variables: Sequence[str] | Sequence[sp.Symbol] = ()) -> sp.Expr:
    normalized = normalize_math_text(str(text))
    local_dict: dict[str, Any] = {
        "sqrt": sp.sqrt,
        "root": sp.root,
        "Rational": sp.Rational,
        "Integer": sp.Integer,
        "I": sp.I,
    }
    for variable in variables:
        symbol = variable if isinstance(variable, sp.Symbol) else sp.Symbol(str(variable))
        local_dict[str(symbol)] = symbol
    for name in re.findall(r"[A-Za-z_]\w*", normalized):
        if name not in local_dict:
            local_dict[name] = sp.Symbol(name)
    global_dict = {"__builtins__": {}, "Integer": sp.Integer, "Rational": sp.Rational}
    return sp.sympify(
        parse_expr(
            normalized,
            local_dict=local_dict,
            global_dict=global_dict,
            transformations=_PARSE_TRANSFORMATIONS,
            evaluate=True,
        )
    )


def normalize_expression(expression: Any) -> sp.Expr:
    value = sp.sympify(expression)
    try:
        value = sp.cancel(sp.together(value))
    except Exception:
        value = sp.simplify(value)
    try:
        value = sp.expand(value)
    except Exception:
        value = sp.simplify(value)
    try:
        value = sp.simplify(value)
    except Exception:
        value = sp.sympify(value)
    return sp.sympify(value)


def contains_float(expression: Any) -> bool:
    try:
        return bool(sp.sympify(expression).atoms(sp.Float))
    except Exception:
        return True


def number_atoms_are_exact(expression: Any) -> bool:
    try:
        value = sp.sympify(expression)
    except Exception:
        return False
    if contains_float(value):
        return False
    for atom in value.atoms(sp.NumberSymbol):
        if atom.is_algebraic is not True:
            return False
    return True


def exact_zero(expression: Any) -> bool:
    try:
        value = normalize_expression(expression)
    except Exception:
        return False
    if value == 0:
        return True
    status = getattr(value, "is_zero", None)
    if status is True:
        return True
    if getattr(value, "is_number", False) is True:
        try:
            simplified = sp.simplify(value)
            return bool(simplified == 0)
        except Exception:
            return False
    return False


def exact_nonzero(expression: Any) -> bool:
    try:
        value = normalize_expression(expression)
    except Exception:
        return False
    if exact_zero(value):
        return False
    status = getattr(value, "is_zero", None)
    if status is False and not value.free_symbols:
        return True
    if getattr(value, "is_number", False) is True:
        if getattr(value, "is_rational", False) is True:
            return True
        if getattr(value, "is_algebraic", None) is True:
            try:
                variable = sp.Symbol("_t")
                polynomial = sp.Poly(sp.minpoly(value, variable), variable)
                return not exact_zero(polynomial.eval(0))
            except Exception:
                return False
    return False


def is_exact_algebraic_value(value: Any) -> bool:
    try:
        expression = normalize_expression(value)
    except Exception:
        return False
    if expression in (sp.oo, -sp.oo, sp.zoo, sp.nan):
        return False
    if expression.free_symbols:
        return False
    if contains_float(expression):
        return False
    if not number_atoms_are_exact(expression):
        return False
    if getattr(expression, "is_number", False) is not True:
        return False
    if getattr(expression, "is_algebraic", None) is True:
        return True
    if getattr(expression, "is_rational", False) is True:
        return True
    return False


def coefficient_domain_valid(value: Any) -> bool:
    try:
        expression = normalize_expression(value)
    except Exception:
        return False
    if expression.free_symbols:
        return False
    if contains_float(expression):
        return False
    if not number_atoms_are_exact(expression):
        return False
    if getattr(expression, "is_algebraic", None) is True:
        return True
    if getattr(expression, "is_rational", False) is True:
        return True
    return False


def denominator_nonzero_obligations(expressions: Sequence[Any]) -> tuple[sp.Expr, ...]:
    obligations: list[sp.Expr] = []
    for expression in expressions:
        value = sp.sympify(expression)
        try:
            denominator = sp.together(value).as_numer_denom()[1]
        except Exception:
            denominator = sp.nan
        obligations.append(sp.sympify(denominator))
    return tuple(obligations)


def check_denominator_nonzero_obligations(expressions: Sequence[Any]) -> bool:
    for denominator in denominator_nonzero_obligations(expressions):
        if contains_float(denominator):
            return False
        if denominator.free_symbols:
            return False
        if not exact_nonzero(denominator):
            return False
    return True


def polynomial_coefficient_dictionary(expression: Any, variables: Sequence[sp.Symbol]) -> dict[tuple[int, ...], sp.Expr]:
    symbols = tuple(variables)
    value = sp.cancel(sp.together(sp.sympify(expression)))
    if contains_float(value):
        raise ValueError("inexact_number")
    numerator, denominator = value.as_numer_denom()
    if any(symbol in denominator.free_symbols for symbol in symbols):
        raise ValueError("variable_denominator")
    if not exact_nonzero(denominator):
        raise ValueError("zero_denominator")
    polynomial_expression = sp.expand(numerator / denominator)
    if not polynomial_expression.free_symbols.issubset(set(symbols)):
        raise ValueError("foreign_symbol")
    polynomial = sp.Poly(polynomial_expression, *symbols, extension=True)
    result: dict[tuple[int, ...], sp.Expr] = {}
    for monomial, coefficient in polynomial.terms():
        coefficient = normalize_expression(coefficient)
        if not exact_zero(coefficient):
            if not coefficient_domain_valid(coefficient):
                raise ValueError("invalid_coefficient_domain")
            result[tuple(int(item) for item in monomial)] = coefficient
    return result


def coefficient_dictionary_to_expression(coefficients: Mapping[tuple[int, ...], Any], variables: Sequence[sp.Symbol]) -> sp.Expr:
    total = sp.Integer(0)
    for monomial, coefficient in coefficients.items():
        term = sp.sympify(coefficient)
        for variable, exponent in zip(variables, monomial):
            term *= variable ** int(exponent)
        total += term
    return normalize_expression(total)


def derivative_from_monomial_coefficients(
    coefficients: Mapping[tuple[int, ...], Any],
    variable_index: int,
) -> dict[tuple[int, ...], sp.Expr]:
    result: dict[tuple[int, ...], sp.Expr] = {}
    for monomial, coefficient in coefficients.items():
        exponent = int(monomial[variable_index])
        if exponent:
            new_monomial = list(monomial)
            new_monomial[variable_index] = exponent - 1
            key = tuple(new_monomial)
            result[key] = normalize_expression(result.get(key, sp.Integer(0)) + sp.sympify(coefficient) * exponent)
    return {key: value for key, value in result.items() if not exact_zero(value)}


def multiply_coefficient_dictionaries(
    left: Mapping[tuple[int, ...], Any],
    right: Mapping[tuple[int, ...], Any],
) -> dict[tuple[int, ...], sp.Expr]:
    result: dict[tuple[int, ...], sp.Expr] = {}
    for left_monomial, left_coefficient in left.items():
        for right_monomial, right_coefficient in right.items():
            key = tuple(int(a) + int(b) for a, b in zip(left_monomial, right_monomial))
            result[key] = normalize_expression(
                result.get(key, sp.Integer(0)) + sp.sympify(left_coefficient) * sp.sympify(right_coefficient)
            )
    return {key: value for key, value in result.items() if not exact_zero(value)}


def subtract_coefficient_dictionaries(
    left: Mapping[tuple[int, ...], Any],
    right: Mapping[tuple[int, ...], Any],
) -> dict[tuple[int, ...], sp.Expr]:
    result: dict[tuple[int, ...], sp.Expr] = {}
    for key, value in left.items():
        result[key] = normalize_expression(result.get(key, sp.Integer(0)) + sp.sympify(value))
    for key, value in right.items():
        result[key] = normalize_expression(result.get(key, sp.Integer(0)) - sp.sympify(value))
    return {key: value for key, value in result.items() if not exact_zero(value)}


def derivative_matrix_determinant(first: Any, second: Any, variables: Sequence[sp.Symbol]) -> sp.Expr:
    x_symbol, y_symbol = variables
    return normalize_expression(
        sp.diff(first, x_symbol) * sp.diff(second, y_symbol)
        - sp.diff(first, y_symbol) * sp.diff(second, x_symbol)
    )


def differential_determinant_from_coefficients(
    first_coefficients: Mapping[tuple[int, int], Any],
    second_coefficients: Mapping[tuple[int, int], Any],
) -> dict[tuple[int, int], sp.Expr]:
    first_x = derivative_from_monomial_coefficients(first_coefficients, 0)
    first_y = derivative_from_monomial_coefficients(first_coefficients, 1)
    second_x = derivative_from_monomial_coefficients(second_coefficients, 0)
    second_y = derivative_from_monomial_coefficients(second_coefficients, 1)
    positive = multiply_coefficient_dictionaries(first_x, second_y)
    negative = multiply_coefficient_dictionaries(first_y, second_x)
    return subtract_coefficient_dictionaries(positive, negative)


def differential_determinant_from_expressions(first: Any, second: Any, variables: Sequence[sp.Symbol]) -> sp.Expr:
    first_coefficients = polynomial_coefficient_dictionary(first, variables)
    second_coefficients = polynomial_coefficient_dictionary(second, variables)
    determinant_coefficients = differential_determinant_from_coefficients(first_coefficients, second_coefficients)
    return coefficient_dictionary_to_expression(determinant_coefficients, variables)


def evaluate_polynomial(expression: Any, substitutions: Mapping[sp.Symbol, Any]) -> sp.Expr:
    return normalize_expression(sp.sympify(expression).subs(dict(substitutions)))


def evaluate_coefficient_dictionary(
    coefficients: Mapping[tuple[int, ...], Any],
    point: Sequence[Any],
) -> sp.Expr:
    total = sp.Integer(0)
    for monomial, coefficient in coefficients.items():
        term = sp.sympify(coefficient)
        for coordinate, exponent in zip(point, monomial):
            term *= sp.sympify(coordinate) ** int(exponent)
        total += term
    return normalize_expression(total)


def compare_algebraic_coordinates(left: Sequence[Any], right: Sequence[Any]) -> tuple[bool, bool]:
    equal = True
    distinct = False
    for left_coordinate, right_coordinate in zip(left, right):
        difference = normalize_expression(sp.sympify(left_coordinate) - sp.sympify(right_coordinate))
        if not exact_zero(difference):
            equal = False
        if exact_nonzero(difference):
            distinct = True
    return equal, distinct


def canonicalize_formula(expression: Any) -> str:
    value = normalize_expression(expression)
    try:
        return sp.sstr(value, order="lex")
    except Exception:
        return str(value)


def _stable_data(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _stable_data(asdict(value))
    if isinstance(value, sp.Basic):
        return canonicalize_formula(value)
    if isinstance(value, Mapping):
        return {str(key): _stable_data(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (tuple, list)):
        return [_stable_data(item) for item in value]
    if isinstance(value, set):
        return sorted(_stable_data(item) for item in value)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        return repr(value)
    return repr(value)


def stable_signature(value: Any) -> str:
    payload = json.dumps(_stable_data(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
