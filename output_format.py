from __future__ import annotations

from .models import Candidate, ProblemKind, ProblemSpec
from .symbolic_tools import canonicalize_formula, exact_parse_expression


def format_candidate(specification: ProblemSpec, candidate: Candidate) -> str:
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        first = canonicalize_formula(exact_parse_expression(str(candidate.formulas["F1"]), ("x", "y")))
        second = canonicalize_formula(exact_parse_expression(str(candidate.formulas["F2"]), ("x", "y")))
        point = candidate.points["P"]
        other = candidate.points["Q"]
        point_first = canonicalize_formula(exact_parse_expression(str(point[0])))
        point_second = canonicalize_formula(exact_parse_expression(str(point[1])))
        other_first = canonicalize_formula(exact_parse_expression(str(other[0])))
        other_second = canonicalize_formula(exact_parse_expression(str(other[1])))
        return "\n".join(
            (
                f"F₁(x,y) = {first}",
                f"F₂(x,y) = {second}",
                f"P = ({point_first}, {point_second})",
                f"Q = ({other_first}, {other_second})",
            )
        )
    if specification.kind == ProblemKind.ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT:
        if not candidate.assignments:
            return "()"
        return "\n".join(f"{key} = {canonicalize_formula(exact_parse_expression(str(candidate.assignments[key])))}" for key in sorted(candidate.assignments))
    table = candidate.finite_structures.get("operation_table", [])
    identity = candidate.finite_structures.get("identity", 0)
    lines = [f"* = {table}", f"e = {identity}"]
    for key in sorted(candidate.assignments):
        lines.append(f"{key} = {candidate.assignments[key]}")
    return "\n".join(lines)
