from __future__ import annotations

from .models import Candidate, ProblemKind, ProblemSpec
from .symbolic_tools import canonicalize_formula, exact_parse_expression


def _finite_field_modulus_text(modulus: tuple[int, ...], prime: int) -> str:
    if not modulus:
        return "none: GF(" + str(prime) + ") is the prime field"
    degree = len(modulus)
    terms: list[str] = []
    for power in range(degree, -1, -1):
        coefficient = 1 if power == degree else int(modulus[power])
        if coefficient % prime == 0:
            continue
        if power == 0:
            terms.append(str(coefficient % prime))
        elif power == 1:
            terms.append("a" if coefficient % prime == 1 else str(coefficient % prime) + "*a")
        else:
            terms.append("a^" + str(power) if coefficient % prime == 1 else str(coefficient % prime) + "*a^" + str(power))
    return " + ".join(terms)


def format_candidate(specification: ProblemSpec, candidate: Candidate) -> str:
    if specification.kind == ProblemKind.FINITE_FIELD_JACOBIAN_REFUTATION:
        artifacts = dict(candidate.exact_derivation_artifacts)
        prime = int(artifacts.get("field_characteristic", 2))
        degree = int(artifacts.get("field_extension_degree", 1))
        field_label = "GF(" + str(prime) + ("" if degree == 1 else "^" + str(degree)) + ")"
        first = canonicalize_formula(exact_parse_expression(str(candidate.formulas["F1"]), ("x", "y")))
        second = canonicalize_formula(exact_parse_expression(str(candidate.formulas["F2"]), ("x", "y")))
        point = candidate.points["P"]
        other = candidate.points["Q"]
        if len(point) != 2 or len(other) != 2:
            raise ValueError("point_dimension_mismatch")
        modulus = tuple(int(item) for item in artifacts.get("field_modulus", ()))
        modulus_text = _finite_field_modulus_text(modulus, prime)
        image = artifacts.get("image_at_point", ())
        return "\n".join(
            (
                "field: " + field_label + " with " + str(prime ** degree) + " elements",
                "modulus: " + modulus_text,
                f"F₁(x,y) = {first}",
                f"F₂(x,y) = {second}",
                f"P = ({point[0]}, {point[1]})",
                f"Q = ({other[0]}, {other[1]})",
                "F(P) = (" + ", ".join(str(item) for item in image) + ") = F(Q)",
                "det J = " + str(int(artifacts.get("determinant_constant_mod_characteristic", 1))) + " (mod " + str(prime) + ")",
                "scope: polynomial maps over the finite field " + field_label + " in positive characteristic",
                "limitation: the general two dimensional Jacobian conjecture in characteristic 0 remains open and is not refuted by this witness",
            )
        )
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        first = canonicalize_formula(exact_parse_expression(str(candidate.formulas["F1"]), ("x", "y")))
        second = canonicalize_formula(exact_parse_expression(str(candidate.formulas["F2"]), ("x", "y")))
        point = candidate.points["P"]
        other = candidate.points["Q"]
        if len(point) != 2 or len(other) != 2:
            raise ValueError("point_dimension_mismatch")
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
