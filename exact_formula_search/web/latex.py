from __future__ import annotations

from typing import Any, Sequence

import sympy as sp

from ..models import ProblemKind, ProblemSpec
from ..symbolic_tools import exact_parse_expression, tokenize_group_word

_LATEX_ESCAPES = (
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
)

_OPERAND_TOKENS = ("var", "identity", "rparen", "power", "inv")
_OPENING_TOKENS = ("var", "identity", "lparen")


def escape_latex(text: Any) -> str:
    result = str(text)
    for source, target in _LATEX_ESCAPES:
        result = result.replace(source, target)
    return result


def expression_latex(text: Any, variables: Sequence[str] = ()) -> str:
    raw = str(text)
    try:
        expression = exact_parse_expression(raw, tuple(str(item) for item in variables))
    except Exception:
        return r"\text{" + escape_latex(raw) + "}"
    try:
        rendered = sp.latex(expression)
    except Exception:
        return r"\text{" + escape_latex(raw) + "}"
    return rendered or r"\text{" + escape_latex(raw) + "}"


def exact_value_latex(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    return expression_latex(str(value))


def identity_symbol_latex(symbol: Any) -> str:
    raw = str(symbol) if symbol not in (None, "") else "e"
    if raw in ("e", "E"):
        return "e"
    if len(raw) == 1 and raw.isalpha():
        return raw
    return r"\text{" + escape_latex(raw) + "}"


def group_word_latex(word: Any, variables: Sequence[str] = (), identity_symbol: str = "e") -> str:
    raw = str(word)
    identity = identity_symbol_latex(identity_symbol)
    try:
        tokens = tokenize_group_word(raw, tuple(str(item) for item in variables))
    except Exception:
        return r"\text{" + escape_latex(raw) + "}"
    parts: list[str] = []
    previous = ""
    for kind, value in tokens:
        if kind in _OPENING_TOKENS and previous in _OPERAND_TOKENS:
            parts.append(r"\cdot")
        if kind == "star":
            parts.append(r"\cdot")
        elif kind == "var":
            parts.append(sp.latex(sp.Symbol(str(value))))
        elif kind == "identity":
            parts.append(identity)
        elif kind == "lparen":
            parts.append("\\left(")
        elif kind == "rparen":
            parts.append("\\right)")
        elif kind == "power":
            exponent = int(value)
            if exponent == 1:
                continue
            parts.append("^{" + str(exponent) + "}")
        elif kind == "inv":
            parts.append("^{-1}")
        previous = kind
    rendered = " ".join(parts).replace("\\left( ", "\\left(").replace(" \\right)", "\\right)")
    return rendered or r"\text{" + escape_latex(raw) + "}"


def equation_latex(left: Any, right: Any, variables: Sequence[str] = ()) -> str:
    return expression_latex(left, variables) + " = " + expression_latex(right, variables)


def _source_text(source: Any, canonical: Any) -> str:
    text = str(source) if source not in (None, "") else str(canonical)
    return text if text else "0"


def statement_text(specification: ProblemSpec) -> str:
    if specification.kind == ProblemKind.FINITE_FIELD_JACOBIAN_REFUTATION:
        return "every polynomial map of the plane over a finite field with constant nonzero Jacobian determinant is injective"
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        return "every polynomial map of the plane with constant nonzero Jacobian determinant is injective"
    if specification.kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
        target = specification.finite_group_identity
        bound = specification.order_bound
        if target is None:
            return "finite group identity countermodel"
        prefix = "in every finite group"
        if bound is not None:
            prefix = prefix + " of order at most " + str(int(bound))
        return prefix + ": " + str(target.left_word) + " = " + str(target.right_word)
    target = specification.algebraic_identity
    if target is None:
        return "algebraic identity counterassignment"
    return _source_text(target.left_source, target.left_expression) + " = " + _source_text(target.right_source, target.right_expression)


def statement_latex(specification: ProblemSpec) -> str:
    if specification.kind == ProblemKind.FINITE_FIELD_JACOBIAN_REFUTATION:
        return (
            r"\det J(F_1, F_2) \equiv c \neq 0 \;\text{in } \mathbb{F}_{p^k} \;\Longrightarrow\; "
            r"\forall P, Q \;:\; F_1(P) = F_1(Q),\ F_2(P) = F_2(Q) \;\Longrightarrow\; P = Q"
        )
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        return (
            r"\det J(F_1, F_2) \equiv c \neq 0 \;\Longrightarrow\; "
            r"\forall P, Q \;:\; F_1(P) = F_1(Q),\ F_2(P) = F_2(Q) \;\Longrightarrow\; P = Q"
        )
    if specification.kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
        target = specification.finite_group_identity
        if target is None:
            return r"\text{finite group identity countermodel}"
        identity = identity_symbol_latex(target.identity_symbol)
        left = group_word_latex(target.left_word, target.variables, identity)
        right = group_word_latex(target.right_word, target.variables, identity)
        bound = specification.order_bound
        if bound is None:
            return left + r" = " + right + r"\quad \text{in every finite group}"
        return left + r" = " + right + r"\quad \text{in every finite group of order at most } " + str(int(bound))
    target = specification.algebraic_identity
    if target is None:
        return r"\text{algebraic identity counterassignment}"
    return equation_latex(
        _source_text(target.left_source, target.left_expression),
        _source_text(target.right_source, target.right_expression),
        target.variables,
    )


def policy_latex(specification: ProblemSpec) -> str:
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        return r"\text{find } P \neq Q \text{ with } F_1(P) = F_1(Q),\; F_2(P) = F_2(Q),\quad \det J(F_1,F_2) \equiv c \neq 0"
    if specification.kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
        return r"\text{find a finite group and elements that refute the identity}"
    return r"\text{find an exact assignment that refutes the identity}"


def table_latex(table: Sequence[Sequence[Any]], identity: Any = None) -> str:
    rows: list[str] = []
    order = len(table)
    header = ["", *[str(index) for index in range(order)]]
    rows.append(r"\begin{array}{c|" + "c" * order + "}")
    rows.append(" & ".join(header) + r" \\ \hline")
    for index, row in enumerate(table):
        rows.append(str(index) + " & " + " & ".join(str(int(value)) for value in row) + r" \\")
    rows.append(r"\end{array}")
    return "\n".join(rows)
