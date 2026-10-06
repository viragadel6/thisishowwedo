from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

import sympy as sp

from ..symbolic_tools import (
    evaluate_group_word_by_postfix,
    tokenize_group_word,
)


class ExportError(ValueError):
    pass


_POWER_PATTERN = re.compile(r"\s*(-?[0-9]+)")


def _symbol_table(names: Sequence[str]) -> dict[str, sp.Symbol]:
    table: dict[str, sp.Symbol] = {}
    for name in names:
        text = str(name)
        if not text.isidentifier():
            raise ExportError("invalid_symbol_name:" + text)
        table[text] = sp.Symbol(text)
    return table


def _exact_sympify(text: Any, symbols: Mapping[str, sp.Symbol]) -> sp.Expr:
    try:
        value = sp.sympify(str(text), locals=dict(symbols))
    except Exception as exception:
        raise ExportError("unparsable_expression:" + type(exception).__name__) from exception
    if not isinstance(value, sp.Expr):
        raise ExportError("non_expression_value")
    if value.has(sp.Float):
        raise ExportError("floating_point_expression_rejected")
    return value


def _python_literal(value: Any) -> str:
    return repr(value)


def _literal_lines(name: str, value: Any) -> list[str]:
    rendered = _python_literal(value)
    if "\n" in rendered:
        raise ExportError("multiline_literal_rejected")
    return [name + " = " + rendered]


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


def _postfix_program(tokens: Sequence[tuple[str, Any]]) -> list[list[Any]]:
    output: list[list[Any]] = []
    operators: list[tuple[str, Any]] = []
    for token in _insert_implicit_operations(tokens):
        kind = token[0]
        if kind in ("var", "identity", "inv", "power"):
            output.append([kind, token[1]])
        elif kind == "star":
            while operators and operators[-1][0] != "lparen":
                pending = operators.pop()
                output.append([pending[0], pending[1]])
            operators.append(token)
        elif kind == "lparen":
            operators.append(token)
        elif kind == "rparen":
            while operators and operators[-1][0] != "lparen":
                pending = operators.pop()
                output.append([pending[0], pending[1]])
            if not operators:
                raise ExportError("unbalanced_group_parentheses")
            operators.pop()
        else:
            raise ExportError("unexpected_group_token:" + str(kind))
    while operators:
        pending = operators.pop()
        if pending[0] == "lparen":
            raise ExportError("unbalanced_group_parentheses")
        output.append([pending[0], pending[1]])
    return output


def _inverse_element(table: Sequence[Sequence[int]], identity: int, value: int) -> int:
    for candidate in range(len(table)):
        if table[value][candidate] == identity and table[candidate][value] == identity:
            return candidate
    raise ExportError("missing_inverse")


def _element_power(table: Sequence[Sequence[int]], identity: int, value: int, exponent: int) -> int:
    if exponent < 0:
        value = _inverse_element(table, identity, value)
        exponent = -exponent
    result = identity
    factor = value
    while exponent:
        if exponent & 1:
            result = table[result][factor]
        factor = table[factor][factor]
        exponent >>= 1
    return result


def _evaluate_program(
    program: Sequence[Sequence[Any]],
    assignment: Mapping[str, int],
    table: Sequence[Sequence[int]],
    identity: int,
) -> int:
    stack: list[int] = []
    for instruction in program:
        kind = str(instruction[0])
        payload = instruction[1]
        if kind == "var":
            if str(payload) not in assignment:
                raise ExportError("missing_group_assignment:" + str(payload))
            stack.append(int(assignment[str(payload)]))
        elif kind == "identity":
            stack.append(int(identity))
        elif kind == "star":
            if len(stack) < 2:
                raise ExportError("malformed_group_word")
            right = stack.pop()
            left = stack.pop()
            stack.append(int(table[left][right]))
        elif kind == "inv":
            if not stack:
                raise ExportError("malformed_group_word")
            stack.append(_inverse_element(table, identity, stack.pop()))
        elif kind == "power":
            if not stack:
                raise ExportError("malformed_group_word")
            stack.append(_element_power(table, identity, stack.pop(), int(payload)))
        else:
            raise ExportError("unexpected_group_token:" + kind)
    if len(stack) != 1:
        raise ExportError("malformed_group_word")
    return stack[0]


def _group_program(word: str, variables: Sequence[str], assignment: Mapping[str, int], table: Sequence[Sequence[int]], identity: int) -> list[list[Any]]:
    tokens = tokenize_group_word(word, [str(item) for item in variables])
    program = _postfix_program(tokens)
    reproduced = _evaluate_program(program, assignment, table, identity)
    engine_value = evaluate_group_word_by_postfix(word, dict(assignment), table, identity)
    if int(reproduced) != int(engine_value):
        raise ExportError("group_reproduction_mismatch")
    return program


def _group_word_latex(word: str) -> str:
    text = " ".join(str(word).split())
    pieces: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character.isspace():
            index += 1
            continue
        if character in ("*", "\u00b7", "\u22c5", "\u2218"):
            pieces.append(" \\cdot ")
            index += 1
            continue
        if character == "'":
            pieces.append("^{-1}")
            index += 1
            continue
        if character in ("^",) or text.startswith("**", index):
            step = 2 if text.startswith("**", index) else 1
            following = text[index + step :]
            power_match = _POWER_PATTERN.match(following)
            if power_match is None:
                raise ExportError("unparsable_group_power")
            pieces.append("^{" + power_match.group(1) + "}")
            index += step + power_match.end()
            continue
        if character == "(":
            pieces.append("\\left(")
            index += 1
            continue
        if character == ")":
            pieces.append("\\right)")
            index += 1
            continue
        pieces.append(character)
        index += 1
    return "".join(pieces)


def _latex_expression(text: Any, symbols: Mapping[str, sp.Symbol]) -> str:
    return sp.latex(_exact_sympify(text, symbols))


def _algebraic_script(certificate: Mapping[str, Any]) -> list[str]:
    algebraic = dict(certificate.get("algebraic") or {})
    names = [str(name) for name in algebraic.get("variables", ())]
    assignments = {str(key): str(value) for key, value in dict(algebraic.get("assignments") or {}).items()}
    missing = [name for name in names if name not in assignments]
    if missing:
        raise ExportError("missing_assignment:" + ",".join(sorted(missing)))
    lines: list[str] = []
    lines.append("import sympy as sp")
    lines.append("")
    lines.extend(_literal_lines("symbol_names", tuple(names)))
    lines.append("symbols = {name: sp.Symbol(name) for name in symbol_names}")
    lines.extend(_literal_lines("assignment_text", {name: assignments[name] for name in names}))
    lines.append("assignment = {symbols[name]: sp.sympify(text) for name, text in assignment_text.items()}")
    lines.extend(_literal_lines("left_expression_text", str(algebraic.get("left_expression", ""))))
    lines.extend(_literal_lines("right_expression_text", str(algebraic.get("right_expression", ""))))
    lines.append("left_expression = sp.sympify(left_expression_text, locals=symbols)")
    lines.append("right_expression = sp.sympify(right_expression_text, locals=symbols)")
    obligation_texts = [str(dict(item).get("expression", "")) for item in algebraic.get("domain_obligations") or ()]
    lines.extend(_literal_lines("obligation_texts", tuple(obligation_texts)))
    lines.append("obligations = [sp.sympify(text, locals=symbols) for text in obligation_texts]")
    lines.append("")
    lines.append("def exact(value):")
    lines.append("    if value.has(sp.Float):")
    lines.append("        raise ValueError(\"floating point value rejected\")")
    lines.append("    return sp.simplify(value)")
    lines.append("")
    lines.append("left_value = exact(left_expression.subs(assignment))")
    lines.append("right_value = exact(right_expression.subs(assignment))")
    lines.append("difference = exact(left_value - right_value)")
    lines.append("if difference == 0:")
    lines.append("    raise AssertionError(\"the exported assignment does not refute the identity\")")
    lines.append("for obligation in obligations:")
    lines.append("    if exact(obligation.subs(assignment)) == 0:")
    lines.append("        raise AssertionError(\"the exported assignment violates a domain obligation\")")
    lines.append("print(\"left value:\", sp.sstr(left_value))")
    lines.append("print(\"right value:\", sp.sstr(right_value))")
    lines.append("print(\"difference:\", sp.sstr(difference))")
    lines.append("print(\"reproduction verified with exact arithmetic\")")
    return lines


def _planar_script(certificate: Mapping[str, Any]) -> list[str]:
    planar = dict(certificate.get("planar") or {})
    components = dict(planar.get("component_expressions") or {})
    if "first" not in components or "second" not in components:
        raise ExportError("missing_planar_component")
    first_text = str(components["first"])
    second_text = str(components["second"])
    point_p = list(planar.get("point_p") or [])
    point_q = list(planar.get("point_q") or [])
    for point in (point_p, point_q):
        if len(point) != 2:
            raise ExportError("missing_planar_point_coordinate")
    point_p = {"first": point_p[0], "second": point_p[1]}
    point_q = {"first": point_q[0], "second": point_q[1]}
    lines: list[str] = []
    lines.append("import sympy as sp")
    lines.append("")
    lines.append("x, y = sp.symbols(\"x y\")")
    lines.append("symbols = {\"x\": x, \"y\": y}")
    lines.extend(_literal_lines("first_expression_text", first_text))
    lines.extend(_literal_lines("second_expression_text", second_text))
    lines.append("first_expression = sp.sympify(first_expression_text, locals=symbols)")
    lines.append("second_expression = sp.sympify(second_expression_text, locals=symbols)")
    lines.extend(_literal_lines("point_p_text", (str(point_p["first"]), str(point_p["second"]))))
    lines.extend(_literal_lines("point_q_text", (str(point_q["first"]), str(point_q["second"]))))
    lines.append("point_p = tuple(sp.sympify(text) for text in point_p_text)")
    lines.append("point_q = tuple(sp.sympify(text) for text in point_q_text)")
    lines.extend(
        _literal_lines(
            "obligation_texts",
            tuple(str(dict(item).get("expression", "")) for item in planar.get("domain_obligations") or ()),
        )
    )
    lines.append("obligations = [sp.sympify(text, locals=symbols) for text in obligation_texts]")
    lines.append("")
    lines.append("def exact(value):")
    lines.append("    if value.has(sp.Float):")
    lines.append("        raise ValueError(\"floating point value rejected\")")
    lines.append("    return sp.expand(value)")
    lines.append("")
    lines.append("matrix = sp.Matrix([[sp.diff(first_expression, x), sp.diff(first_expression, y)], [sp.diff(second_expression, x), sp.diff(second_expression, y)]])")
    lines.append("determinant = exact(matrix.det())")
    lines.append("polynomial = sp.Poly(determinant, x, y)")
    lines.append("constant = sp.Integer(0)")
    lines.append("for monomial, coefficient in polynomial.terms():")
    lines.append("    if monomial == (0, 0):")
    lines.append("        constant = exact(coefficient)")
    lines.append("    elif exact(coefficient) != 0:")
    lines.append("        raise AssertionError(\"the determinant is not a constant\")")
    lines.append("if constant == 0:")
    lines.append("    raise AssertionError(\"the determinant constant is zero\")")
    lines.append("left_substitution = {x: point_p[0], y: point_p[1]}")
    lines.append("right_substitution = {x: point_q[0], y: point_q[1]}")
    lines.append("if exact(first_expression.subs(left_substitution) - first_expression.subs(right_substitution)) != 0:")
    lines.append("    raise AssertionError(\"the first component does not collide\")")
    lines.append("if exact(second_expression.subs(left_substitution) - second_expression.subs(right_substitution)) != 0:")
    lines.append("    raise AssertionError(\"the second component does not collide\")")
    lines.append("if exact(point_p[0] - point_q[0]) == 0 and exact(point_p[1] - point_q[1]) == 0:")
    lines.append("    raise AssertionError(\"the collision points are not distinct\")")
    lines.append("for obligation in obligations:")
    lines.append("    for substitution in (left_substitution, right_substitution):")
    lines.append("        if exact(obligation.subs(substitution)) == 0:")
    lines.append("            raise AssertionError(\"a collision point violates a domain obligation\")")
    lines.append("print(\"determinant:\", sp.sstr(determinant))")
    lines.append("print(\"point P:\", tuple(sp.sstr(item) for item in point_p))")
    lines.append("print(\"point Q:\", tuple(sp.sstr(item) for item in point_q))")
    lines.append("print(\"reproduction verified with exact arithmetic\")")
    return lines


def _group_script(certificate: Mapping[str, Any]) -> list[str]:
    group = dict(certificate.get("group") or {})
    table = [[int(entry) for entry in row] for row in (group.get("operation_table") or [])]
    if not table:
        raise ExportError("missing_operation_table")
    identity = int(group.get("identity", 0))
    names = [str(name) for name in group.get("variables", ())]
    assignments = {str(key): int(value) for key, value in dict(group.get("assignments") or {}).items()}
    missing = [name for name in names if name not in assignments]
    if missing:
        raise ExportError("missing_group_assignment:" + ",".join(sorted(missing)))
    left_word = str(group.get("left_word", ""))
    right_word = str(group.get("right_word", ""))
    left_program = _group_program(left_word, names, assignments, table, identity)
    right_program = _group_program(right_word, names, assignments, table, identity)
    lines: list[str] = []
    lines.append("import sympy as sp")
    lines.append("")
    lines.extend(_literal_lines("operation_table", table))
    lines.append("identity = " + str(identity))
    lines.extend(_literal_lines("assignment", {name: assignments[name] for name in names}))
    lines.extend(_literal_lines("left_program", left_program))
    lines.extend(_literal_lines("right_program", right_program))
    lines.append("left_word = " + _python_literal(left_word))
    lines.append("right_word = " + _python_literal(right_word))
    lines.append("")
    lines.append("def inverse_element(value):")
    lines.append("    for candidate in range(len(operation_table)):")
    lines.append("        if operation_table[value][candidate] == identity and operation_table[candidate][value] == identity:")
    lines.append("            return candidate")
    lines.append("    raise ValueError(\"missing inverse\")")
    lines.append("")
    lines.append("def element_power(value, exponent):")
    lines.append("    if exponent < 0:")
    lines.append("        value = inverse_element(value)")
    lines.append("        exponent = -exponent")
    lines.append("    result = identity")
    lines.append("    factor = value")
    lines.append("    while exponent:")
    lines.append("        if exponent & 1:")
    lines.append("            result = operation_table[result][factor]")
    lines.append("        factor = operation_table[factor][factor]")
    lines.append("        exponent >>= 1")
    lines.append("    return result")
    lines.append("")
    lines.append("def evaluate(program):")
    lines.append("    stack = []")
    lines.append("    for kind, payload in program:")
    lines.append("        if kind == \"var\":")
    lines.append("            stack.append(assignment[payload])")
    lines.append("        elif kind == \"identity\":")
    lines.append("            stack.append(identity)")
    lines.append("        elif kind == \"star\":")
    lines.append("            right = stack.pop()")
    lines.append("            left = stack.pop()")
    lines.append("            stack.append(operation_table[left][right])")
    lines.append("        elif kind == \"inv\":")
    lines.append("            stack.append(inverse_element(stack.pop()))")
    lines.append("        elif kind == \"power\":")
    lines.append("            stack.append(element_power(stack.pop(), payload))")
    lines.append("        else:")
    lines.append("            raise ValueError(\"unknown instruction\" + str(kind))")
    lines.append("    if len(stack) != 1:")
    lines.append("        raise ValueError(\"malformed word program\")")
    lines.append("    return stack[0]")
    lines.append("")
    lines.append("def validate_group_table():")
    lines.append("    order = len(operation_table)")
    lines.append("    for row in operation_table:")
    lines.append("        if len(row) != order:")
    lines.append("            raise AssertionError(\"the operation table is not square\")")
    lines.append("        for entry in row:")
    lines.append("            if entry < 0 or entry >= order:")
    lines.append("                raise AssertionError(\"the operation table is not closed\")")
    lines.append("    for left in range(order):")
    lines.append("        for middle in range(order):")
    lines.append("            for right in range(order):")
    lines.append("                if operation_table[operation_table[left][middle]][right] != operation_table[left][operation_table[middle][right]]:")
    lines.append("                    raise AssertionError(\"associativity fails\")")
    lines.append("    for element in range(order):")
    lines.append("        if operation_table[identity][element] != element or operation_table[element][identity] != element:")
    lines.append("            raise AssertionError(\"the identity law fails\")")
    lines.append("        inverse_element(element)")
    lines.append("")
    lines.append("validate_group_table()")
    lines.append("left_value = evaluate(left_program)")
    lines.append("right_value = evaluate(right_program)")
    lines.append("if left_value == right_value:")
    lines.append("    raise AssertionError(\"the exported model does not refute the identity\")")
    lines.append("print(\"left word\", left_word, \"=\", left_value)")
    lines.append("print(\"right word\", right_word, \"=\", right_value)")
    lines.append("print(\"group order:\", len(operation_table))")
    lines.append("print(\"reproduction verified with exact arithmetic\")")
    return lines


def sympy_reproduction_script(certificate: Mapping[str, Any]) -> str:
    problem_kind = str(certificate.get("problem_kind", ""))
    if problem_kind == "algebraic_identity_counterassignment":
        lines = _algebraic_script(certificate)
    elif problem_kind == "planar_constant_determinant_collision":
        lines = _planar_script(certificate)
    elif problem_kind == "finite_group_identity_countermodel":
        lines = _group_script(certificate)
    else:
        raise ExportError("unsupported_problem_kind:" + problem_kind)
    return "\n".join(lines) + "\n"


def _algebraic_latex(certificate: Mapping[str, Any]) -> list[str]:
    algebraic = dict(certificate.get("algebraic") or {})
    names = [str(name) for name in algebraic.get("variables", ())]
    symbols = _symbol_table(names)
    assignments = {str(key): str(value) for key, value in dict(algebraic.get("assignments") or {}).items()}
    lines: list[str] = []
    lines.append("\\begin{equation}")
    lines.append("  " + _latex_expression(algebraic.get("left_expression", "0"), symbols) + " = " + _latex_expression(algebraic.get("right_expression", "0"), symbols))
    lines.append("\\end{equation}")
    lines.append("")
    lines.append("\\paragraph{Exact counterassignment}")
    lines.append("\\[")
    lines.append("  " + ",\\qquad ".join(name + " = " + _latex_expression(assignments[name], symbols) for name in names if name in assignments))
    lines.append("\\]")
    lines.append("")
    lines.append("\\paragraph{Exact substitution}")
    lines.append("\\[")
    lines.append("  L(x_0) = " + _latex_expression(algebraic.get("left_value", "0"), symbols) + ",\\qquad R(x_0) = " + _latex_expression(algebraic.get("right_value", "0"), symbols) + ",\\qquad L - R = " + _latex_expression(algebraic.get("difference", "0"), symbols) + " \\neq 0")
    lines.append("\\]")
    obligations = list(algebraic.get("domain_obligations") or [])
    if obligations:
        lines.append("")
        lines.append("\\paragraph{Domain obligations}")
        lines.append("\\[")
        entries = []
        for item in obligations:
            entry = dict(item)
            entries.append(_latex_expression(entry.get("expression", "0"), symbols) + " = " + _latex_expression(entry.get("value", "0"), symbols) + " \\neq 0")
        lines.append("  " + ",\\qquad ".join(entries))
        lines.append("\\]")
    return lines


def _planar_latex(certificate: Mapping[str, Any]) -> list[str]:
    planar = dict(certificate.get("planar") or {})
    symbols = _symbol_table(("x", "y"))
    components = dict(planar.get("component_expressions") or {})
    raw_point_p = list(planar.get("point_p") or [])
    raw_point_q = list(planar.get("point_q") or [])
    point_p = {"first": raw_point_p[0], "second": raw_point_p[1]} if len(raw_point_p) == 2 else {"first": "0", "second": "0"}
    point_q = {"first": raw_point_q[0], "second": raw_point_q[1]} if len(raw_point_q) == 2 else {"first": "0", "second": "0"}
    lines: list[str] = []
    lines.append("\\begin{equation}")
    lines.append("  F(x,y) = \\left(" + _latex_expression(components.get("first", "0"), symbols) + ",\\;" + _latex_expression(components.get("second", "0"), symbols) + "\\right)")
    lines.append("\\end{equation}")
    lines.append("")
    lines.append("\\paragraph{Constant nonzero determinant}")
    lines.append("\\[")
    lines.append("  \\det J_F(x,y) = " + _latex_expression(planar.get("jacobian_determinant", "0"), symbols) + " \\neq 0")
    lines.append("\\]")
    lines.append("")
    lines.append("\\paragraph{Exact collision}")
    lines.append("\\[")
    lines.append(
        "  P = \\left("
        + _latex_expression(point_p.get("first", "0"), symbols)
        + ",\\;"
        + _latex_expression(point_p.get("second", "0"), symbols)
        + "\\right),\\qquad Q = \\left("
        + _latex_expression(point_q.get("first", "0"), symbols)
        + ",\\;"
        + _latex_expression(point_q.get("second", "0"), symbols)
        + "\\right)"
    )
    lines.append("\\]")
    lines.append("\\[")
    lines.append("  F(P) = F(Q),\\qquad P \\neq Q")
    lines.append("\\]")
    return lines


def _group_latex(certificate: Mapping[str, Any]) -> list[str]:
    group = dict(certificate.get("group") or {})
    table = [[int(entry) for entry in row] for row in (group.get("operation_table") or [])]
    identity = int(group.get("identity", 0))
    elements = [str(item) for item in group.get("elements", ())]
    assignments = {str(key): int(value) for key, value in dict(group.get("assignments") or {}).items()}
    lines: list[str] = []
    lines.append("\\begin{equation}")
    lines.append("  " + _group_word_latex(str(group.get("left_word", ""))) + " = " + _group_word_latex(str(group.get("right_word", ""))) + "\\quad\\text{in every finite group is false}")
    lines.append("\\end{equation}")
    lines.append("")
    lines.append("\\paragraph{Exact countermodel}")
    lines.append("\\[")
    lines.append("  |G| = " + str(len(table)) + ",\\qquad e = " + str(identity) + ",\\qquad " + ",\\qquad ".join(name + " = " + str(assignments[name]) for name in sorted(assignments)))
    lines.append("\\]")
    lines.append("\\[")
    lines.append("  " + _group_word_latex(str(group.get("left_word", ""))) + " = " + str(group.get("left_value")) + " \\neq " + str(group.get("right_value")) + " = " + _group_word_latex(str(group.get("right_word", ""))))
    lines.append("\\]")
    if table:
        lines.append("")
        lines.append("\\paragraph{Operation table}")
        lines.append("\\[")
        lines.append("\\begin{array}{c|" + "c" * len(table) + "}")
        header = " & ".join([""] + [_latex_group_element(index, elements) for index in range(len(table))])
        lines.append(header + " \\\\ \\hline")
        for row_index, row in enumerate(table):
            cells = " & ".join(_latex_group_element(entry, elements) for entry in row)
            lines.append(_latex_group_element(row_index, elements) + " & " + cells + " \\\\")
        lines.append("\\end{array}")
        lines.append("\\]")
    return lines


def _latex_group_element(index: int, elements: Sequence[str]) -> str:
    if index < len(elements):
        return _latex_escape(elements[index])
    return str(index)


def _latex_escape(text: str) -> str:
    mapping = {
        "\\": "\\textbackslash{}",
        "{": "\\{",
        "}": "\\}",
        "$": "\\$",
        "&": "\\&",
        "#": "\\#",
        "_": "\\_",
        "%": "\\%",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
    }
    return "".join(mapping.get(character, character) for character in str(text))


def latex_summary(certificate: Mapping[str, Any]) -> str:
    problem_kind = str(certificate.get("problem_kind", ""))
    if problem_kind == "algebraic_identity_counterassignment":
        body = _algebraic_latex(certificate)
    elif problem_kind == "planar_constant_determinant_collision":
        body = _planar_latex(certificate)
    elif problem_kind == "finite_group_identity_countermodel":
        body = _group_latex(certificate)
    else:
        raise ExportError("unsupported_problem_kind:" + problem_kind)
    return _certificate_document(certificate, body)


def sympy_identity_proof_script(certificate: Mapping[str, Any]) -> str:
    proof = dict(certificate.get("proof") or {})
    names = [str(name) for name in proof.get("variables", ())]
    lines: list[str] = []
    lines.append("import sympy as sp")
    lines.append("")
    lines.extend(_literal_lines("symbol_names", tuple(names)))
    lines.append("symbols = {name: sp.Symbol(name) for name in symbol_names}")
    lines.extend(_literal_lines("left_expression_text", str(proof.get("left_expression", "0"))))
    lines.extend(_literal_lines("right_expression_text", str(proof.get("right_expression", "0"))))
    lines.append("left_expression = sp.sympify(left_expression_text, locals=symbols)")
    lines.append("right_expression = sp.sympify(right_expression_text, locals=symbols)")
    lines.append("")
    lines.append("def exact(value):")
    lines.append("    if value.has(sp.Float):")
    lines.append("        raise ValueError(\"floating point value rejected\")")
    lines.append("    return sp.simplify(value)")
    lines.append("")
    lines.append("difference = exact(left_expression - right_expression)")
    lines.append("if difference != 0:")
    lines.append("    raise AssertionError(\"the exported identity is not an exact identity\")")
    lines.append("print(\"exact difference:\", sp.sstr(difference))")
    lines.append("print(\"identity verified symbolically with exact arithmetic\")")
    return "\n".join(lines) + "\n"


def exhaustion_latex(certificate: Mapping[str, Any]) -> str:
    exhaustion = dict(certificate.get("exhaustion") or {})
    budget = dict(certificate.get("budget") or {})
    body: list[str] = []
    body.append("\\begin{equation}")
    body.append("  " + _latex_escape(str(exhaustion.get("headline", "no counterexample found within the search budget"))))
    body.append("\\end{equation}")
    body.append("")
    body.append("\\paragraph{Exhaustion reason}")
    body.append("\\texttt{" + _latex_escape(str(exhaustion.get("exhaustion_reason", ""))) + "}")
    body.append("")
    body.append("\\paragraph{Search statistics}")
    body.append("\\begin{itemize}")
    body.append("  \\item frontiers examined: " + str(exhaustion.get("frontiers_examined", 0)))
    body.append("  \\item candidates verified: " + str(exhaustion.get("candidates_verified", 0)))
    body.append("  \\item mutation rounds: " + str(exhaustion.get("mutation_rounds", 0)))
    body.append("  \\item repair rounds: " + str(exhaustion.get("repairs", 0)))
    body.append("\\end{itemize}")
    body.append("")
    body.append("\\paragraph{Budget}")
    body.append("\\begin{itemize}")
    body.append("  \\item wall clock: " + _latex_escape(str(budget.get("time_seconds", ""))) + " s")
    body.append("  \\item frontier visits: " + str(budget.get("max_frontier_visits", 0)))
    body.append("  \\item verified candidates: " + str(budget.get("max_verified_candidates", 0)))
    body.append("  \\item mutation rounds: " + str(budget.get("max_mutation_rounds", 0)))
    body.append("  \\item worker timeout: " + _latex_escape(str(budget.get("execution_timeout_seconds", ""))) + " s")
    body.append("\\end{itemize}")
    lanes = [dict(item) for item in exhaustion.get("lanes") or []]
    if lanes:
        body.append("")
        body.append("\\paragraph{Lanes explored}")
        body.append("\\[")
        body.append("\\begin{array}{lrr}")
        body.append("\\text{lane} & \\text{visits} & \\text{candidates} \\\\ \\hline")
        for item in lanes:
            body.append(
                _latex_escape(str(item.get("lane", "")))
                + " & "
                + str(item.get("visits", 0))
                + " & "
                + str(item.get("candidates", 0))
                + " \\\\"
            )
        body.append("\\end{array}")
        body.append("\\]")
    if exhaustion.get("note"):
        body.append("")
        body.append("\\paragraph{Note}")
        body.append(_latex_escape(str(exhaustion.get("note"))))
    return _certificate_document(certificate, body)


def symbolic_proof_latex(certificate: Mapping[str, Any]) -> str:
    proof = dict(certificate.get("proof") or {})
    body: list[str] = []
    body.append("\\begin{equation}")
    left_rendered = str(proof.get("left_latex") or "")
    right_rendered = str(proof.get("right_latex") or "")
    if not left_rendered or not right_rendered:
        symbols = _symbol_table([str(name) for name in proof.get("variables", ())])
        left_rendered = _latex_expression(proof.get("left_expression", "0"), symbols)
        right_rendered = _latex_expression(proof.get("right_expression", "0"), symbols)
    body.append("  " + left_rendered + " = " + right_rendered)
    body.append("\\end{equation}")
    body.append("")
    body.append("\\paragraph{Exact simplification}")
    body.append("\\[")
    body.append("  L - R = " + str(proof.get("difference_latex") or "0") + " = 0")
    body.append("\\]")
    steps = [dict(item) for item in proof.get("steps") or []]
    if steps:
        body.append("")
        body.append("\\paragraph{Exact steps}")
        body.append("\\begin{enumerate}")
        for step in steps:
            body.append("  \\item " + _latex_escape(str(step.get("label", ""))) + ":" )
            body.append("\\[")
            body.append("  " + str(step.get("latex", "")))
            body.append("\\]")
            body.append("  " + _latex_escape(str(step.get("detail", ""))))
        body.append("\\end{enumerate}")
    return _certificate_document(certificate, body)


def _certificate_document(certificate: Mapping[str, Any], body: Sequence[str]) -> str:
    source = dict(certificate.get("source") or {})
    lines: list[str] = []
    lines.append("\\documentclass{article}")
    lines.append("\\usepackage{amsmath,amssymb}")
    lines.append("\\begin{document}")
    lines.append("\\section*{Exact formula search certificate}")
    lines.append("")
    lines.extend(body)
    lines.append("")
    lines.append("\\paragraph{Request}")
    lines.append("\\texttt{" + _latex_escape(str(certificate.get("query", ""))) + "}")
    lines.append("")
    lines.append("\\paragraph{Verification}")
    lines.append("\\begin{itemize}")
    for entry in certificate.get("audit") or []:
        item = dict(entry)
        status = str(item.get("status", "pending"))
        mark = "\\checkmark" if status == "pass" else ("$\\times$" if status == "fail" else "--")
        lines.append("  \\item " + mark + " " + _latex_escape(str(item.get("label", ""))) + ": " + _latex_escape(str(item.get("detail", ""))))
    lines.append("\\end{itemize}")
    lines.append("")
    provenance = dict(certificate.get("provenance") or {})
    worker_digest = str(provenance.get("worker_sha256", ""))
    fingerprint = str(provenance.get("source_fingerprint", provenance.get("fingerprint", source.get("fingerprint", ""))))
    lines.append("\\paragraph{Provenance}")
    if worker_digest or fingerprint:
        lines.append("\\texttt{worker sha256: " + _latex_escape(worker_digest) + "}")
        lines.append("")
        lines.append("\\texttt{source fingerprint: " + _latex_escape(fingerprint) + "}")
    else:
        lines.append("\\emph{no generated worker was certified in this run}")
    lines.append("")
    lines.append("\\end{document}")
    return "\n".join(lines) + "\n"
