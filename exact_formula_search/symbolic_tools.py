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
_RADICAL_DEGREES = {"√": 2, "∛": 3, "∜": 4}
_IDENTITY_NAMES = frozenset({"e", "id", "identity", "one", "unit"})
_FUNCTION_TABLE: dict[str, Any] = {
    "sqrt": sp.sqrt,
    "cbrt": lambda value: sp.real_root(value, 3),
    "root": sp.root,
    "real_root": sp.real_root,
    "Rational": sp.Rational,
    "Integer": sp.Integer,
    "Float": sp.Float,
    "exp": sp.exp,
    "log": sp.log,
    "ln": sp.log,
    "log10": lambda value: sp.log(value, 10),
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "cot": sp.cot,
    "sec": sp.sec,
    "csc": sp.csc,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "acot": sp.acot,
    "asec": sp.asec,
    "acsc": sp.acsc,
    "arcsin": sp.asin,
    "arccos": sp.acos,
    "arctan": sp.atan,
    "sinh": sp.sinh,
    "cosh": sp.cosh,
    "tanh": sp.tanh,
    "coth": sp.coth,
    "asinh": sp.asinh,
    "acosh": sp.acosh,
    "atanh": sp.atanh,
    "Abs": sp.Abs,
    "abs": sp.Abs,
    "sign": sp.sign,
    "floor": sp.floor,
    "ceiling": sp.ceiling,
    "ceil": sp.ceiling,
    "trunc": sp.trunc,
    "frac": sp.frac,
    "factorial": sp.factorial,
    "gamma": sp.gamma,
    "erf": sp.erf,
    "zeta": sp.zeta,
    "binomial": sp.binomial,
    "conjugate": sp.conjugate,
    "re": sp.re,
    "im": sp.im,
    "arg": sp.arg,
    "min": sp.Min,
    "max": sp.Max,
    "gcd": sp.gcd,
    "lcm": sp.lcm,
}
_CONSTANT_TABLE: dict[str, Any] = {
    "pi": sp.pi,
    "Pi": sp.pi,
    "PI": sp.pi,
    "τ": sp.pi,
    "tau": 2 * sp.pi,
    "e": sp.E,
    "E": sp.E,
    "I": sp.I,
    "oo": sp.oo,
    "inf": sp.oo,
    "infinity": sp.oo,
    "zoo": sp.zoo,
    "nan": sp.nan,
    "EulerGamma": sp.EulerGamma,
    "GoldenRatio": sp.GoldenRatio,
    "Catalan": sp.Catalan,
    "TribonacciConstant": sp.TribonacciConstant,
}
_TOKEN_PATTERN = re.compile(
    r"(?P<number>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)"
    r"|(?P<name>[A-Za-z_][A-Za-z_0-9]*)"
    r"|(?P<power>\*\*)"
    r"|(?P<op>[+\-*/^(),!])"
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


def _radical_operand(text: str, index: int) -> tuple[str, int]:
    length = len(text)
    while index < length and text[index].isspace():
        index += 1
    if index >= length:
        raise ValueError("missing_radical_operand")
    if text[index] == "(":
        depth = 0
        start = index
        while index < length:
            if text[index] == "(":
                depth += 1
            elif text[index] == ")":
                depth -= 1
                if depth == 0:
                    index += 1
                    break
            index += 1
        if depth != 0:
            raise ValueError("unbalanced_parentheses")
        return text[start:index], index
    match = re.match(r"[0-9]*\.?[0-9]+|[A-Za-z_][A-Za-z_0-9]*", text[index:])
    if match is None:
        raise ValueError("missing_radical_operand")
    end = index + match.end()
    operand = match.group(0)
    exponent = re.match(r"(?:\*\*|\^)\s*\(?\s*[0-9]+\s*\)?", text[end:])
    if exponent is not None:
        digits = re.sub(r"[^0-9]", "", exponent.group(0))
        operand = operand + "**" + digits
        end = end + exponent.end()
    return operand, end


def _convert_radicals(text: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character in _RADICAL_DEGREES:
            degree = _RADICAL_DEGREES[character]
            operand, index = _radical_operand(text, index + 1)
            if degree == 2:
                output.append("sqrt(" + operand + ")")
            else:
                output.append("root(" + operand + ", " + str(degree) + ")")
        else:
            output.append(character)
            index += 1
    return "".join(output)


def normalize_math_text(text: str) -> str:
    replacements = {
        "−": "-",
        "–": "-",
        "—": "-",
        "﹣": "-",
        "×": "*",
        "⋅": "*",
        "·": "*",
        "÷": "/",
        "＝": "=",
        "≡": "=",
        "≈": "=",
        "≠": "!=",
        "≤": "<=",
        "≥": ">=",
        "𝐱": "x",
        "𝑥": "x",
        "𝑦": "y",
        "𝑋": "X",
        "𝑌": "Y",
    }
    value = str(text)
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = _convert_radicals(value)
    return _replace_superscript_runs(value)


def create_symbols(names: Sequence[str]) -> tuple[sp.Symbol, ...]:
    return tuple(sp.Symbol(str(name)) for name in names)


def _exact_number(text: str) -> sp.Expr:
    if "e" in text or "E" in text:
        mantissa_text, exponent_text = re.split("[eE]", text, maxsplit=1)
        mantissa = sp.Rational(mantissa_text) if "." in mantissa_text else sp.Integer(int(mantissa_text))
        return mantissa * sp.Integer(10) ** int(exponent_text)
    if "." in text:
        return sp.Rational(text)
    return sp.Integer(int(text))


class _Token:
    __slots__ = ("kind", "text", "position")

    def __init__(self, kind: str, text: str, position: int) -> None:
        self.kind = kind
        self.text = text
        self.position = position


def _tokenize_expression(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    position = 0
    length = len(text)
    while position < length:
        character = text[position]
        if character.isspace():
            position += 1
            continue
        match = _TOKEN_PATTERN.match(text, position)
        if match is None:
            raise ValueError("unexpected_character:" + repr(character))
        kind = match.lastgroup
        if kind is None:
            raise ValueError("unexpected_character:" + repr(character))
        tokens.append(_Token(kind, match.group(0), position))
        position = match.end()
    return tokens


class _ExpressionParser:
    def __init__(self, text: str, variables: Sequence[Any] = ()) -> None:
        self.text = str(text)
        self.tokens = _tokenize_expression(self.text)
        self.index = 0
        self.declared: dict[str, sp.Symbol] = {}
        for variable in variables:
            if isinstance(variable, sp.Symbol):
                self.declared[str(variable)] = variable
            else:
                name = str(variable)
                self.declared[name] = sp.Symbol(name)
        self.denominators: list[sp.Expr] = []

    def parse(self) -> sp.Expr:
        if not self.tokens:
            raise ValueError("empty_expression")
        value = self._parse_sum()
        if self.index != len(self.tokens):
            raise ValueError("trailing_tokens:" + self.tokens[self.index].text)
        return sp.sympify(value)

    def _peek(self) -> _Token | None:
        if self.index < len(self.tokens):
            return self.tokens[self.index]
        return None

    def _starts_factor(self, token: _Token | None) -> bool:
        if token is None:
            return False
        if token.kind in ("number", "name"):
            return True
        return token.kind == "op" and token.text == "("

    def _parse_sum(self) -> sp.Expr:
        value = self._parse_product()
        while True:
            token = self._peek()
            if token is None or token.kind != "op" or token.text not in ("+", "-"):
                break
            self.index += 1
            operand = self._parse_product()
            value = value + operand if token.text == "+" else value - operand
        return value

    def _parse_product(self) -> sp.Expr:
        value = self._parse_unary()
        while True:
            token = self._peek()
            if token is None:
                break
            if token.kind == "op" and token.text in ("*", "/"):
                self.index += 1
                operand = self._parse_unary()
                if token.text == "*":
                    value = value * operand
                else:
                    self.denominators.append(operand)
                    value = value / operand
                continue
            if token.kind == "op" and token.text in ("+", "-", ")", ",", "!"):
                break
            if self._starts_factor(token):
                value = value * self._parse_unary()
                continue
            break
        return value

    def _parse_unary(self) -> sp.Expr:
        token = self._peek()
        if token is not None and token.kind == "op" and token.text in ("+", "-"):
            self.index += 1
            operand = self._parse_unary()
            return operand if token.text == "+" else -operand
        return self._parse_power()

    def _parse_power(self) -> sp.Expr:
        base = self._parse_atom()
        while True:
            token = self._peek()
            if token is not None and (token.kind == "power" or (token.kind == "op" and token.text == "^")):
                self.index += 1
                exponent = self._parse_unary()
                base = base ** exponent
                continue
            if token is not None and token.kind == "op" and token.text == "!":
                self.index += 1
                base = sp.factorial(base)
                continue
            break
        return base

    def _parse_atom(self) -> sp.Expr:
        token = self._peek()
        if token is None:
            raise ValueError("unexpected_end_of_expression")
        if token.kind == "number":
            self.index += 1
            return _exact_number(token.text)
        if token.kind == "name":
            return self._parse_name(token)
        if token.kind == "op" and token.text == "(":
            self.index += 1
            value = self._parse_sum()
            closing = self._peek()
            if closing is None or closing.kind != "op" or closing.text != ")":
                raise ValueError("unbalanced_parentheses")
            self.index += 1
            return value
        raise ValueError("unexpected_token:" + token.text)

    def _parse_call_arguments(self) -> tuple[sp.Expr, ...]:
        opening = self._peek()
        if opening is None or opening.kind != "op" or opening.text != "(":
            raise ValueError("missing_argument_list")
        self.index += 1
        arguments: list[sp.Expr] = []
        token = self._peek()
        if token is not None and token.kind == "op" and token.text == ")":
            self.index += 1
            return tuple(arguments)
        while True:
            arguments.append(self._parse_sum())
            token = self._peek()
            if token is None:
                raise ValueError("unbalanced_parentheses")
            if token.kind == "op" and token.text == ",":
                self.index += 1
                continue
            if token.kind == "op" and token.text == ")":
                self.index += 1
                break
            raise ValueError("unexpected_token_in_argument_list:" + token.text)
        return tuple(arguments)

    def _parse_name(self, token: _Token) -> sp.Expr:
        name = token.text
        self.index += 1
        following = self._peek()
        if name in self.declared:
            symbol = self.declared[name]
            if following is not None and following.kind == "op" and following.text == "(":
                arguments = self._parse_call_arguments()
                product = symbol
                for argument in arguments:
                    product = product * argument
                return product
            return symbol
        function = _FUNCTION_TABLE.get(name)
        if function is not None:
            if following is not None and following.kind == "op" and following.text == "(":
                return function(*self._parse_call_arguments())
            if self._starts_factor(following):
                return function(self._parse_unary())
            return sp.Symbol(name)
        constant = _CONSTANT_TABLE.get(name)
        if constant is not None:
            if following is not None and following.kind == "op" and following.text == "(":
                arguments = self._parse_call_arguments()
                product = constant
                for argument in arguments:
                    product = product * argument
                return product
            return constant
        if following is not None and following.kind == "op" and following.text == "(":
            arguments = self._parse_call_arguments()
            product = sp.Symbol(name)
            for argument in arguments:
                product = product * argument
            return product
        return sp.Symbol(name)


def exact_parse_expression(text: str, variables: Sequence[Any] = ()) -> sp.Expr:
    parser = _ExpressionParser(normalize_math_text(str(text)), variables)
    return parser.parse()


def expression_domain_obligations(text: str, variables: Sequence[Any] = ()) -> tuple[sp.Expr, ...]:
    parser = _ExpressionParser(normalize_math_text(str(text)), variables)
    parser.parse()
    collected: list[sp.Expr] = []
    for denominator in parser.denominators:
        normalized = sp.sympify(denominator)
        if not any(sp.simplify(normalized - item) == 0 for item in collected):
            collected.append(normalized)
    return tuple(collected)


def normalize_expression(expression: Any) -> sp.Expr:
    value = sp.sympify(expression)
    try:
        value = sp.cancel(sp.together(value))
    except Exception:
        try:
            value = sp.simplify(value)
        except Exception:
            value = sp.sympify(value)
    try:
        value = sp.expand(value)
    except Exception:
        try:
            value = sp.simplify(value)
        except Exception:
            value = sp.sympify(value)
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


def is_finite_exact_value(value: Any) -> bool:
    try:
        expression = sp.sympify(value)
    except Exception:
        return False
    if expression in (sp.oo, -sp.oo, sp.zoo, sp.nan):
        return False
    try:
        if expression.has(sp.oo, -sp.oo, sp.zoo, sp.nan):
            return False
    except Exception:
        return False
    finite = getattr(expression, "is_finite", None)
    if finite is False:
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
    if not is_finite_exact_value(value):
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
    if not is_finite_exact_value(expression):
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
    if not is_finite_exact_value(expression):
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
    return check_obligations_at(denominator_nonzero_obligations(expressions), {})


def check_obligations_at(obligations: Sequence[Any], substitutions: Mapping[sp.Symbol, Any]) -> bool:
    table = dict(substitutions)
    for obligation in obligations:
        try:
            value = normalize_expression(sp.sympify(obligation).subs(table))
        except Exception:
            return False
        if not is_finite_exact_value(value):
            return False
        if not exact_nonzero(value):
            return False
    return True


def polynomial_coefficient_dictionary(expression: Any, variables: Sequence[sp.Symbol]) -> dict[tuple[int, ...], sp.Expr]:
    symbols = tuple(variables)
    if not symbols:
        raise ValueError("missing_variables")
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
    symbols = tuple(variables)
    total = sp.Integer(0)
    for monomial, coefficient in coefficients.items():
        if len(monomial) != len(symbols):
            raise ValueError("monomial_dimension_mismatch")
        term = sp.sympify(coefficient)
        for variable, exponent in zip(symbols, monomial):
            term *= variable ** int(exponent)
        total += term
    return normalize_expression(total)


def derivative_from_monomial_coefficients(
    coefficients: Mapping[tuple[int, ...], Any],
    variable_index: int,
) -> dict[tuple[int, ...], sp.Expr]:
    result: dict[tuple[int, ...], sp.Expr] = {}
    for monomial, coefficient in coefficients.items():
        if variable_index < 0 or variable_index >= len(monomial):
            raise ValueError("variable_index_out_of_range")
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
            if len(left_monomial) != len(right_monomial):
                raise ValueError("monomial_dimension_mismatch")
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
    symbols = tuple(variables)
    if len(symbols) != 2:
        raise ValueError("planar_variables_required")
    x_symbol, y_symbol = symbols
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
    symbols = tuple(variables)
    if len(symbols) != 2:
        raise ValueError("planar_variables_required")
    first_coefficients = polynomial_coefficient_dictionary(first, symbols)
    second_coefficients = polynomial_coefficient_dictionary(second, symbols)
    determinant_coefficients = differential_determinant_from_coefficients(first_coefficients, second_coefficients)
    return coefficient_dictionary_to_expression(determinant_coefficients, symbols)


def evaluate_polynomial(expression: Any, substitutions: Mapping[sp.Symbol, Any]) -> sp.Expr:
    return normalize_expression(sp.sympify(expression).subs(dict(substitutions)))


def evaluate_coefficient_dictionary(
    coefficients: Mapping[tuple[int, ...], Any],
    point: Sequence[Any],
) -> sp.Expr:
    total = sp.Integer(0)
    for monomial, coefficient in coefficients.items():
        if len(monomial) != len(point):
            raise ValueError("point_dimension_mismatch")
        term = sp.sympify(coefficient)
        for coordinate, exponent in zip(point, monomial):
            term *= sp.sympify(coordinate) ** int(exponent)
        total += term
    return normalize_expression(total)


def compare_algebraic_coordinates(left: Sequence[Any], right: Sequence[Any]) -> tuple[bool, bool]:
    if len(left) != len(right):
        raise ValueError("coordinate_dimension_mismatch")
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


def tokenize_group_word(word: str, variables: Sequence[str] = ()) -> tuple[tuple[str, Any], ...]:
    text = str(word)
    text = text.replace("⁻¹", "^-1").replace("’", "'").replace("−", "-").replace("–", "-")
    text = re.sub(r"\*\*\s*-\s*1", "^-1", text)
    lookup: dict[str, str] = {}
    for variable in variables:
        lookup[str(variable).lower()] = str(variable)
    tokens: list[tuple[str, Any]] = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character.isspace():
            index += 1
            continue
        if character in ("*", "·", "⋅", "∘"):
            tokens.append(("star", None))
            index += 1
            continue
        if character == "(":
            tokens.append(("lparen", None))
            index += 1
            continue
        if character == ")":
            tokens.append(("rparen", None))
            index += 1
            continue
        if character == "'":
            tokens.append(("inv", None))
            index += 1
            continue
        power_match = re.match(r"(?:\*\*|\^)\s*(-?[0-9]+)", text[index:])
        if power_match is not None:
            tokens.append(("power", int(power_match.group(1))))
            index += power_match.end()
            continue
        identifier_match = re.match(r"[A-Za-z_][A-Za-z_0-9]*", text[index:])
        if identifier_match is not None:
            run = identifier_match.group(0)
            lower = run.lower()
            if lower in _IDENTITY_NAMES:
                tokens.append(("identity", None))
            elif lower in lookup:
                tokens.append(("var", lookup[lower]))
            else:
                raise ValueError("unknown_group_name:" + run)
            index += identifier_match.end()
            continue
        digit_match = re.match(r"[0-9]+", text[index:])
        if digit_match is not None:
            value = int(digit_match.group(0))
            if value == 1:
                tokens.append(("identity", None))
            else:
                raise ValueError("unexpected_group_number:" + digit_match.group(0))
            index += digit_match.end()
            continue
        raise ValueError("unexpected_group_character:" + repr(character))
    return tuple(tokens)


def group_word_power(value: int, exponent: int, table: Sequence[Sequence[int]], identity: int) -> int:
    if exponent < 0:
        value = _group_inverse_element(table, identity, value)
        exponent = -exponent
    result = identity
    factor = value
    while exponent:
        if exponent & 1:
            result = table[result][factor]
        factor = table[factor][factor]
        exponent >>= 1
    return result


def _group_inverse_element(table: Sequence[Sequence[int]], identity: int, value: int) -> int:
    for candidate in range(len(table)):
        if table[value][candidate] == identity and table[candidate][value] == identity:
            return candidate
    raise ValueError("missing_inverse")


class _GroupWordReader:
    def __init__(self, tokens: Sequence[tuple[str, Any]], assignment: Mapping[str, Any], table: Sequence[Sequence[int]], identity: int) -> None:
        self.tokens = tuple(tokens)
        self.assignment = assignment
        self.table = table
        self.identity = identity
        self.index = 0

    def _peek(self) -> tuple[str, Any] | None:
        if self.index < len(self.tokens):
            return self.tokens[self.index]
        return None

    def _element(self, name: str) -> int:
        if name not in self.assignment:
            raise ValueError("missing_group_assignment:" + str(name))
        value = self.assignment[name]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("non_integer_group_assignment:" + str(name))
        if value < 0 or value >= len(self.table):
            raise ValueError("assignment_out_of_range:" + str(name))
        return int(value)

    def parse(self) -> int:
        if not self.tokens:
            raise ValueError("empty_group_word")
        value = self._parse_product()
        if self.index != len(self.tokens):
            raise ValueError("trailing_group_tokens")
        return value

    def _parse_product(self) -> int:
        result = self.identity
        while True:
            token = self._peek()
            if token is None or token[0] == "rparen":
                break
            if token[0] == "star":
                self.index += 1
                continue
            result = self.table[result][self._parse_factor()]
        return result

    def _parse_factor(self) -> int:
        token = self._peek()
        if token is None:
            raise ValueError("unexpected_end_of_group_word")
        kind, payload = token
        if kind == "lparen":
            self.index += 1
            value = self._parse_product()
            closing = self._peek()
            if closing is None or closing[0] != "rparen":
                raise ValueError("unbalanced_group_parentheses")
            self.index += 1
        elif kind == "identity":
            self.index += 1
            value = self.identity
        elif kind == "var":
            self.index += 1
            value = self._element(str(payload))
        else:
            raise ValueError("unexpected_group_token:" + str(kind))
        while True:
            token = self._peek()
            if token is None:
                break
            kind, payload = token
            if kind == "inv":
                self.index += 1
                value = _group_inverse_element(self.table, self.identity, value)
                continue
            if kind == "power":
                self.index += 1
                value = group_word_power(value, int(payload), self.table, self.identity)
                continue
            break
        return value


def evaluate_group_word(word: str, assignment: Mapping[str, Any], table: Sequence[Sequence[int]], identity: int = 0) -> int:
    tokens = tokenize_group_word(word, tuple(str(item) for item in assignment))
    reader = _GroupWordReader(tokens, assignment, table, identity)
    return reader.parse()


def _insert_implicit_operations(tokens: Sequence[tuple[str, Any]]) -> list[tuple[str, Any]]:
    result: list[tuple[str, Any]] = []
    previous_complete = False
    for token in tokens:
        kind = token[0]
        if kind in ("var", "identity", "lparen") and previous_complete:
            result.append(("star", None))
        result.append(token)
        previous_complete = kind in ("var", "identity", "rparen", "inv", "power")
    return result


def _group_word_postfix(tokens: Sequence[tuple[str, Any]]) -> list[tuple[str, Any]]:
    output: list[tuple[str, Any]] = []
    operators: list[tuple[str, Any]] = []
    for token in _insert_implicit_operations(tokens):
        kind = token[0]
        if kind in ("var", "identity"):
            output.append(token)
        elif kind in ("inv", "power"):
            output.append(token)
        elif kind == "star":
            while operators and operators[-1][0] != "lparen":
                output.append(operators.pop())
            operators.append(token)
        elif kind == "lparen":
            operators.append(token)
        elif kind == "rparen":
            while operators and operators[-1][0] != "lparen":
                output.append(operators.pop())
            if not operators:
                raise ValueError("unbalanced_group_parentheses")
            operators.pop()
    while operators:
        operator = operators.pop()
        if operator[0] == "lparen":
            raise ValueError("unbalanced_group_parentheses")
        output.append(operator)
    return output


def evaluate_group_word_by_postfix(word: str, assignment: Mapping[str, Any], table: Sequence[Sequence[int]], identity: int = 0) -> int:
    tokens = tokenize_group_word(word, tuple(str(item) for item in assignment))
    if not tokens:
        raise ValueError("empty_group_word")
    postfix = _group_word_postfix(tokens)
    stack: list[int] = []
    for kind, payload in postfix:
        if kind == "var":
            if str(payload) not in assignment:
                raise ValueError("missing_group_assignment:" + str(payload))
            value = assignment[str(payload)]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("non_integer_group_assignment:" + str(payload))
            stack.append(int(value))
        elif kind == "identity":
            stack.append(identity)
        elif kind == "star":
            if len(stack) < 2:
                raise ValueError("malformed_group_word")
            right = stack.pop()
            left = stack.pop()
            stack.append(table[left][right])
        elif kind == "inv":
            if not stack:
                raise ValueError("malformed_group_word")
            stack.append(_group_inverse_element(table, identity, stack.pop()))
        elif kind == "power":
            if not stack:
                raise ValueError("malformed_group_word")
            stack.append(group_word_power(stack.pop(), int(payload), table, identity))
        else:
            raise ValueError("unexpected_group_token:" + str(kind))
    if len(stack) != 1:
        raise ValueError("malformed_group_word")
    return stack[0]


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


def is_prime_number(value: Any) -> bool:
    number = int(value)
    if number < 2:
        return False
    if number < 4:
        return True
    if number % 2 == 0:
        return False
    divisor = 3
    while divisor * divisor <= number:
        if number % divisor == 0:
            return False
        divisor += 2
    return True


def prime_divisors(value: int) -> tuple[int, ...]:
    number = max(1, int(value))
    divisors: list[int] = []
    candidate = 2
    while candidate * candidate <= number:
        if number % candidate == 0:
            divisors.append(candidate)
            while number % candidate == 0:
                number //= candidate
        candidate += 1
    if number > 1:
        divisors.append(number)
    return tuple(divisors)


def _poly_trim(coefficients: Sequence[int], prime: int) -> tuple[int, ...]:
    values = [int(entry) % prime for entry in coefficients]
    while values and values[-1] == 0:
        values.pop()
    return tuple(values)


def _poly_add(left: Sequence[int], right: Sequence[int], prime: int) -> tuple[int, ...]:
    size = max(len(left), len(right))
    result = [0] * size
    for index in range(size):
        a = left[index] if index < len(left) else 0
        b = right[index] if index < len(right) else 0
        result[index] = (a + b) % prime
    return _poly_trim(result, prime)


def _poly_subtract(left: Sequence[int], right: Sequence[int], prime: int) -> tuple[int, ...]:
    size = max(len(left), len(right))
    result = [0] * size
    for index in range(size):
        a = left[index] if index < len(left) else 0
        b = right[index] if index < len(right) else 0
        result[index] = (a - b) % prime
    return _poly_trim(result, prime)


def _poly_multiply(left: Sequence[int], right: Sequence[int], prime: int) -> tuple[int, ...]:
    if not left or not right:
        return ()
    result = [0] * (len(left) + len(right) - 1)
    for i, a in enumerate(left):
        if a == 0:
            continue
        for j, b in enumerate(right):
            if b == 0:
                continue
            result[i + j] = (result[i + j] + a * b) % prime
    return _poly_trim(result, prime)


def _poly_divmod(numerator: Sequence[int], denominator: Sequence[int], prime: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    top = _poly_trim(numerator, prime)
    bottom = _poly_trim(denominator, prime)
    if not bottom:
        raise ValueError("division_by_zero_polynomial")
    inverse_lead = pow(bottom[-1], prime - 2, prime)
    quotient = [0] * max(0, len(top) - len(bottom) + 1)
    remainder = list(top)
    while len(remainder) >= len(bottom) and remainder:
        shift = len(remainder) - len(bottom)
        factor = (remainder[-1] * inverse_lead) % prime
        quotient[shift] = factor
        for index in range(len(bottom)):
            remainder[shift + index] = (remainder[shift + index] - factor * bottom[index]) % prime
        remainder = list(_poly_trim(remainder, prime))
    return _poly_trim(quotient, prime), _poly_trim(remainder, prime)


def _poly_monic(coefficients: Sequence[int], prime: int) -> tuple[int, ...]:
    values = _poly_trim(coefficients, prime)
    if not values:
        return ()
    inverse_lead = pow(values[-1], prime - 2, prime)
    return tuple((entry * inverse_lead) % prime for entry in values)


def _poly_gcd(left: Sequence[int], right: Sequence[int], prime: int) -> tuple[int, ...]:
    a = _poly_trim(left, prime)
    b = _poly_trim(right, prime)
    while b:
        _, remainder = _poly_divmod(a, b, prime)
        a, b = b, remainder
    return _poly_monic(a, prime)


def _poly_powmod(base: Sequence[int], exponent: int, modulus: Sequence[int], prime: int) -> tuple[int, ...]:
    reduced = _poly_divmod(base, modulus, prime)[1]
    result: tuple[int, ...] = (1 % prime,)
    power = reduced
    value = max(0, int(exponent))
    while value:
        if value & 1:
            result = _poly_divmod(_poly_multiply(result, power, prime), modulus, prime)[1]
        power = _poly_divmod(_poly_multiply(power, power, prime), modulus, prime)[1]
        value >>= 1
    return result


def irreducible_modulus_polynomial(prime: Any, degree: Any) -> tuple[int, ...]:
    p = int(prime)
    k = int(degree)
    if not is_prime_number(p):
        raise ValueError("characteristic_not_prime")
    if k < 1:
        raise ValueError("invalid_extension_degree")
    x_polynomial = (0, 1)
    if k == 1:
        return ()
    factors = prime_divisors(k)
    for candidate in range(p ** k):
        lower = [((candidate // (p ** index)) % p) for index in range(k)]
        monic = tuple(lower + [1])
        frobenius = _poly_powmod(x_polynomial, p ** k, monic, p)
        if _poly_subtract(frobenius, x_polynomial, p) != ():
            continue
        coprime = True
        for divisor in factors:
            difference = _poly_subtract(_poly_powmod(x_polynomial, p ** (k // divisor), monic, p), x_polynomial, p)
            if _poly_gcd(monic, difference, p) != (1 % p,):
                coprime = False
                break
        if coprime:
            return tuple(lower)
    raise ValueError("irreducible_polynomial_not_found")


def finite_field_elements(prime: Any, degree: Any) -> tuple[tuple[int, ...], ...]:
    p = int(prime)
    k = int(degree)
    if not is_prime_number(p) or k < 1:
        raise ValueError("invalid_finite_field")
    elements: list[tuple[int, ...]] = []
    for index in range(p ** k):
        vector = tuple((index // (p ** position)) % p for position in range(k))
        elements.append(vector)
    return tuple(elements)


def finite_field_reduce(vector: Sequence[int], prime: Any, modulus: Sequence[int]) -> tuple[int, ...]:
    p = int(prime)
    degree = len(modulus)
    if degree == 0:
        return ((int(vector[0]) % p,) if vector else (0,))
    values = [int(entry) % p for entry in vector]
    while len(values) > degree:
        top = values.pop()
        if top == 0:
            continue
        shift = len(values) - degree
        for index in range(degree):
            values[shift + index] = (values[shift + index] - top * modulus[index]) % p
    while len(values) < degree:
        values.append(0)
    return tuple(entry % p for entry in values)


def finite_field_size(prime: Any, degree: Any) -> int:
    p = int(prime)
    k = int(degree)
    if not is_prime_number(p) or k < 1:
        raise ValueError("invalid_finite_field")
    return p ** k


def finite_field_add(left: Sequence[int], right: Sequence[int], prime: Any) -> tuple[int, ...]:
    p = int(prime)
    size = max(len(left), len(right), 1)
    return tuple(((left[index] if index < len(left) else 0) + (right[index] if index < len(right) else 0)) % p for index in range(size))


def finite_field_negate(value: Sequence[int], prime: Any) -> tuple[int, ...]:
    p = int(prime)
    return tuple((-int(entry)) % p for entry in value)


def finite_field_multiply(left: Sequence[int], right: Sequence[int], prime: Any, modulus: Sequence[int]) -> tuple[int, ...]:
    p = int(prime)
    if not left or not right:
        return finite_field_reduce((0,), p, modulus)
    if not modulus:
        return (((int(left[0]) if left else 0) * (int(right[0]) if right else 0)) % p,)
    product: list[int] = [0] * (len(left) + len(right) - 1)
    for i, a in enumerate(left):
        for j, b in enumerate(right):
            product[i + j] = (product[i + j] + int(a) * int(b)) % p
    return finite_field_reduce(product, p, modulus)


def finite_field_power(value: Sequence[int], exponent: int, prime: Any, modulus: Sequence[int]) -> tuple[int, ...]:
    p = int(prime)
    count = max(0, int(exponent))
    if not modulus:
        scalar = int(value[0]) % p if value else 0
        return (pow(scalar, count, p),)
    base = finite_field_reduce(tuple(int(entry) % p for entry in value), p, modulus)
    result = finite_field_reduce((1,), p, modulus)
    power = base
    while count:
        if count & 1:
            result = finite_field_multiply(result, power, p, modulus)
        power = finite_field_multiply(power, power, p, modulus)
        count >>= 1
    return result


def finite_field_inverse(value: Sequence[int], prime: Any, modulus: Sequence[int]) -> tuple[int, ...]:
    p = int(prime)
    degree = max(1, len(modulus))
    order = p ** degree
    if not any(int(entry) % p for entry in value):
        raise ValueError("zero_element_has_no_inverse")
    return finite_field_power(value, order - 2, p, modulus)


def finite_field_from_int(value: Any, prime: Any, degree: Any) -> tuple[int, ...]:
    p = int(prime)
    k = int(degree)
    first = int(value) % p
    return tuple([first] + [0] * (k - 1))


def finite_field_is_zero(value: Sequence[int], prime: Any) -> bool:
    p = int(prime)
    return all(int(entry) % p == 0 for entry in value)


def finite_field_element_text(value: Sequence[int], prime: Any, generator: str = "a") -> str:
    p = int(prime)
    terms: list[str] = []
    for degree in range(len(value) - 1, -1, -1):
        coefficient = int(value[degree]) % p
        if coefficient == 0:
            continue
        if degree == 0:
            terms.append(str(coefficient))
        elif degree == 1:
            terms.append(generator if coefficient == 1 else str(coefficient) + "*" + generator)
        else:
            power = generator + "^" + str(degree)
            terms.append(power if coefficient == 1 else str(coefficient) + "*" + power)
    return " + ".join(terms) if terms else "0"


def finite_field_element_from_text(text: Any, prime: Any, degree: Any, generator: str = "a") -> tuple[int, ...]:
    p = int(prime)
    k = int(degree)
    raw = str(text).replace(" ", "").replace("**", "^").replace("*", "*")
    if not raw:
        raise ValueError("empty_field_element")
    if raw in ("0", "-0"):
        return tuple([0] * k)
    values = [0] * k
    for term in raw.replace("-", "+-").split("+"):
        if not term or term == "-":
            continue
        sign = 1
        body = term
        if body.startswith("-"):
            sign = -1
            body = body[1:]
        if not body:
            continue
        if generator not in body:
            values[0] = (values[0] + sign * int(body)) % p
            continue
        coefficient_text, _, power_text = body.partition(generator)
        coefficient_text = coefficient_text.rstrip("*")
        coefficient = int(coefficient_text) if coefficient_text else 1
        if power_text.startswith("^"):
            exponent = int(power_text[1:])
        elif power_text == "":
            exponent = 1
        else:
            raise ValueError("invalid_field_element:" + str(text))
        if exponent >= k:
            raise ValueError("field_element_degree_exceeds_extension")
        values[exponent] = (values[exponent] + sign * coefficient) % p
    return tuple(entry % p for entry in values)


def finite_field_vector_from_text(text: Any, prime: Any, degree: Any, generator: str = "a") -> tuple[int, ...]:
    return finite_field_element_from_text(text, prime, degree, generator)
