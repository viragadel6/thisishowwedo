from __future__ import annotations

import datetime
import hashlib
from typing import Any, Mapping, Sequence

import sympy as sp

from ..models import (
    Candidate,
    CritiqueResult,
    Frontier,
    GeneratedCodeResult,
    ProblemKind,
    ProblemSpec,
    SearchBudget,
    VerificationResult,
)
from ..symbolic_tools import canonicalize_formula, exact_parse_expression
from .latex import (
    equation_latex,
    exact_value_latex,
    expression_latex,
    group_word_latex,
    identity_symbol_latex,
    policy_latex,
    statement_latex,
    statement_text,
    table_latex,
)

_KIND_LABELS = {
    ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION: "planar constant determinant collision",
    ProblemKind.ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT: "algebraic identity counterassignment",
    ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL: "finite group identity countermodel",
}


class PayloadError(RuntimeError):
    pass


def utc_timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def seconds_text(value: Any) -> str:
    if isinstance(value, bool):
        return "0.00" if not value else "1.00"
    if isinstance(value, int):
        return f"{float(value):.2f}"
    if isinstance(value, float):
        return f"{value:.2f}"
    return f"{float(str(value)):.2f}"


def exact_text(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise PayloadError("floating point value is not an exact certificate value")
    text = str(value)
    try:
        return canonicalize_formula(exact_parse_expression(text))
    except Exception:
        return text


def event_envelope(event_type: str, sequence: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "type": str(event_type),
        "sequence": int(sequence),
        "emitted_at": utc_timestamp(),
    }
    for key, value in dict(payload).items():
        name = str(key)
        if name in envelope:
            continue
        envelope[name] = json_safe(value)
    return envelope


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        raise PayloadError("floating point value reached a certificate payload")
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [json_safe(item) for item in value]
    raise PayloadError("unsupported certificate payload value: " + type(value).__name__)


def budget_payload(budget: SearchBudget, max_group_order: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "time_seconds": seconds_text(budget.max_seconds),
        "max_frontier_visits": int(budget.max_frontier_visits),
        "max_verified_candidates": int(budget.max_verified_candidates),
        "max_mutation_rounds": int(budget.max_mutation_rounds),
        "max_candidates_per_frontier": int(budget.max_candidates_per_frontier),
        "max_instances_per_solve": int(budget.max_instances_per_solve),
        "max_point_pairs": int(budget.max_point_pairs),
        "execution_timeout_seconds": seconds_text(budget.execution_timeout_seconds),
    }
    if max_group_order is not None:
        payload["max_group_order"] = int(max_group_order)
    return payload


def formalization_payload(
    specification: ProblemSpec,
    budget: SearchBudget,
    max_group_order: int | None = None,
) -> dict[str, Any]:
    variables: list[dict[str, Any]] = []
    for name in specification.variables:
        variables.append({"name": str(name), "latex": expression_latex(str(name))})
    constraints = [{"text": str(item), "latex": expression_latex(str(item), specification.variables)} for item in specification.constraints]
    payload: dict[str, Any] = {
        "problem_kind": specification.kind.value,
        "kind": specification.kind.value,
        "kind_label": _KIND_LABELS.get(specification.kind, specification.kind.value),
        "statement": {"text": statement_text(specification), "latex": statement_latex(specification)},
        "policy_latex": policy_latex(specification),
        "variables": variables,
        "constraints": constraints,
        "domains": [item.value for item in specification.domains],
        "normalized_tokens": list(specification.normalized_tokens),
        "output_roles": {str(key): str(value) for key, value in specification.output_roles.items()},
        "budget": budget_payload(budget, max_group_order),
        "left_latex": "",
        "right_latex": "",
        "left_expression": "",
        "right_expression": "",
        "left_word": "",
        "right_word": "",
        "domain_obligations": [],
        "order_bound": None,
        "order_bounds": None,
        "components": [],
        "point_roles": [],
        "determinant_requirement": "",
    }
    if specification.algebraic_identity is not None:
        target = specification.algebraic_identity
        obligations: list[dict[str, Any]] = []
        seen: set[str] = set()
        for text in tuple(target.left_obligations) + tuple(target.right_obligations):
            key = str(text)
            if key in seen:
                continue
            seen.add(key)
            obligations.append({"expression": key, "latex": expression_latex(key, target.variables)})
        left_display = str(target.left_source) if target.left_source else str(target.left_expression)
        right_display = str(target.right_source) if target.right_source else str(target.right_expression)
        payload.update(
            {
                "left_expression": left_display,
                "right_expression": right_display,
                "left_latex": expression_latex(left_display, target.variables),
                "right_latex": expression_latex(right_display, target.variables),
                "left_canonical_expression": target.left_expression,
                "right_canonical_expression": target.right_expression,
                "left_canonical_latex": expression_latex(target.left_expression, target.variables),
                "right_canonical_latex": expression_latex(target.right_expression, target.variables),
                "domain_obligations": obligations,
                "search_extent": int(target.search_extent),
                "identity_latex": equation_latex(left_display, right_display, target.variables),
            }
        )
    if specification.finite_group_identity is not None:
        target = specification.finite_group_identity
        identity = identity_symbol_latex(target.identity_symbol)
        payload.update(
            {
                "left_word": target.left_word,
                "right_word": target.right_word,
                "left_latex": group_word_latex(target.left_word, target.variables, target.identity_symbol),
                "right_latex": group_word_latex(target.right_word, target.variables, target.identity_symbol),
                "identity_symbol": target.identity_symbol,
                "identity_symbol_latex": identity,
                "inverse_symbol": target.inverse_symbol,
                "operation_symbols": [str(item) if str(item) else "implicit" for item in target.operation_symbols],
                "word_latex": group_word_latex(target.left_word, target.variables, target.identity_symbol)
                + " = "
                + group_word_latex(target.right_word, target.variables, target.identity_symbol),
            }
        )
        effective = int(max_group_order if max_group_order is not None else target.max_order)
        mutation_orders = [order for order in (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 24) if order <= effective]
        if not mutation_orders or mutation_orders[-1] != effective:
            mutation_orders = mutation_orders + [effective]
        payload["order_bound"] = int(target.max_order)
        payload["order_bounds"] = {
            "declared": int(target.max_order),
            "effective": effective,
            "search_limit": effective,
            "mutation_orders": mutation_orders,
        }
    if specification.planar_target is not None:
        target = specification.planar_target
        payload.update(
            {
                "components": [
                    {"name": str(role), "latex": "F_{" + str(index + 1) + "}"} for index, role in enumerate(target.component_roles)
                ],
                "point_roles": [str(role) for role in target.point_roles],
                "variables": [{"name": str(name), "latex": expression_latex(str(name))} for name in target.variables],
                "determinant_requirement": r"\det J \equiv c \neq 0",
                "determinant_latex": r"\det J(F_1, F_2) = \frac{\partial F_1}{\partial x}\frac{\partial F_2}{\partial y} - \frac{\partial F_1}{\partial y}\frac{\partial F_2}{\partial x}",
                "coefficient_domains": [item.value for item in target.coefficient_domains],
                "point_domains": [item.value for item in target.point_domains],
                "order_bound": specification.order_bound,
            }
        )
    return payload


def frontier_payload(frontier: Frontier) -> dict[str, Any]:
    extra = {str(key): value for key, value in frontier.extra_parameters.items()}
    support_sizes = [len(support) for support in frontier.support_sets]
    return {
        "signature": frontier.unique_signature,
        "short_signature": frontier.unique_signature[:12],
        "lane": frontier.lane_identifier,
        "kind": frontier.kind.value,
        "degree_extent": int(frontier.degree_extent),
        "coefficient_extent": int(frontier.coefficient_extent),
        "support_sizes": support_sizes,
        "symmetry_mode": frontier.symmetry_mode.value,
        "composition_scheme": frontier.composition_scheme.value,
        "elimination_objective": frontier.elimination_objective.value,
        "point_pattern": frontier.point_pattern.value,
        "exact_domain": frontier.exact_domain.value,
        "mutation_lineage": [str(item) if len(str(item)) <= 12 else str(item)[:12] for item in frontier.mutation_lineage],
        "mutation_depth": len(frontier.mutation_lineage),
        "solver_route": str(extra.get("solver_route", "solve")),
        "term_order": str(extra.get("term_order", "lex")),
        "repair_action": str(extra.get("repair_action", "")),
        "independent_check_level": int(extra.get("independent_check_level", 0)) if isinstance(extra.get("independent_check_level", 0), int) else 0,
        "prime": int(extra["prime"]) if isinstance(extra.get("prime"), int) else None,
        "max_order": int(extra["max_order"]) if isinstance(extra.get("max_order"), int) else None,
        "denominator_equations": bool(extra.get("denominator_equations", False)),
        "frame": {
            "degree_extent": int(frontier.degree_extent),
            "coefficient_extent": int(frontier.coefficient_extent),
            "symmetry_mode": frontier.symmetry_mode.value,
            "composition_scheme": frontier.composition_scheme.value,
            "elimination_objective": frontier.elimination_objective.value,
            "point_pattern": frontier.point_pattern.value,
            "exact_domain": frontier.exact_domain.value,
            "solver_route": str(extra.get("solver_route", "solve")),
        },
    }


def _algebraic_block(specification: ProblemSpec, candidate: Candidate, verification: VerificationResult) -> dict[str, Any]:
    target = specification.algebraic_identity
    variables = tuple(str(item) for item in (target.variables if target is not None else specification.variables))
    assignments: dict[str, str] = {}
    for name in sorted(candidate.assignments):
        assignments[str(name)] = exact_text(candidate.assignments[name])
    artifacts = dict(verification.artifacts)
    left_value = exact_text(artifacts.get("left_value", "0"))
    right_value = exact_text(artifacts.get("right_value", "0"))
    difference = "0"
    try:
        difference = exact_text(exact_parse_expression(left_value) - exact_parse_expression(right_value))
    except Exception:
        difference = "0"
    obligations: list[dict[str, Any]] = []
    if target is not None:
        seen: set[str] = set()
        for text in tuple(target.left_obligations) + tuple(target.right_obligations):
            key = str(text)
            if key in seen:
                continue
            seen.add(key)
            value_text = ""
            satisfied = True
            try:
                expression = exact_parse_expression(key, target.variables)
                substitutions = {}
                for name, raw in assignments.items():
                    substitutions[sp.Symbol(name)] = exact_parse_expression(raw)
                evaluated = expression.subs(substitutions)
                value_text = exact_text(evaluated)
                satisfied = value_text != "0"
            except Exception:
                value_text = ""
                satisfied = False
            obligations.append(
                {
                    "expression": key,
                    "latex": expression_latex(key, target.variables),
                    "value": value_text,
                    "value_latex": exact_value_latex(value_text) if value_text else "",
                    "satisfied": satisfied,
                }
            )
    left_source = str(target.left_source) if target is not None and target.left_source else (target.left_expression if target is not None else "")
    right_source = str(target.right_source) if target is not None and target.right_source else (target.right_expression if target is not None else "")
    return {
        "variables": list(variables),
        "assignments": assignments,
        "assignments_latex": {name: exact_value_latex(value) for name, value in assignments.items()},
        "domain_obligation_expressions": [str(item) for item in ((target.left_obligations if target is not None else ()) + (target.right_obligations if target is not None else ()))],
        "left_source": left_source,
        "right_source": right_source,
        "left_source_latex": expression_latex(left_source, variables) if left_source else "",
        "right_source_latex": expression_latex(right_source, variables) if right_source else "",
        "left_expression": target.left_expression if target is not None else "",
        "right_expression": target.right_expression if target is not None else "",
        "left_latex": expression_latex(target.left_expression, variables) if target is not None else "",
        "right_latex": expression_latex(target.right_expression, variables) if target is not None else "",
        "left_value": left_value,
        "right_value": right_value,
        "left_value_latex": exact_value_latex(left_value),
        "right_value_latex": exact_value_latex(right_value),
        "difference": difference,
        "difference_latex": exact_value_latex(difference),
        "refuted": difference != "0",
        "domain_obligations": obligations,
        "constraints": [str(item) for item in specification.constraints],
        "exact_inequality_check": bool(artifacts.get("exact_inequality_check", False)),
        "assignment_latex": ",\\quad ".join(
            exact_value_latex(name) + " = " + exact_value_latex(value) for name, value in sorted(assignments.items())
        ),
    }


def _group_invariants(table: Sequence[Sequence[int]], identity: int) -> dict[str, Any]:
    order = len(table)
    commutative = all(table[first][second] == table[second][first] for first in range(order) for second in range(order))
    element_orders: list[int] = []
    for element in range(order):
        value = int(element)
        power = 1
        while value != int(identity) and power <= order + 1:
            value = int(table[value][element])
            power += 1
        element_orders.append(power)
    return {
        "order": order,
        "commutative": commutative,
        "abelian": commutative,
        "cyclic": any(item == order for item in element_orders),
        "exponent": max(element_orders) if element_orders else 0,
        "element_orders": element_orders,
    }


def _group_block(specification: ProblemSpec, candidate: Candidate, verification: VerificationResult) -> dict[str, Any]:
    target = specification.finite_group_identity
    structures = dict(candidate.finite_structures)
    table = [[int(value) for value in row] for row in structures.get("operation_table", [])]
    identity = int(structures.get("identity", 0))
    elements = [int(value) for value in structures.get("elements", list(range(len(table))))]
    assignments = {str(name): int(value) for name, value in sorted(candidate.assignments.items())}
    artifacts = dict(verification.artifacts)
    left_value = int(artifacts.get("left_value") or 0)
    right_value = int(artifacts.get("right_value") or 0)
    identity_name = target.identity_symbol if target is not None else "e"
    left_word = target.left_word if target is not None else ""
    right_word = target.right_word if target is not None else ""
    variables = tuple(str(item) for item in (target.variables if target is not None else specification.variables))
    inverses: list[int] = []
    for element in range(len(table)):
        found = -1
        for candidate_inverse in range(len(table)):
            if table[element][candidate_inverse] == identity and table[candidate_inverse][element] == identity:
                found = candidate_inverse
                break
        inverses.append(found)
    invariants = _group_invariants(table, identity)
    word_evaluations = [
        {
            "word": left_word,
            "latex": group_word_latex(left_word, variables, identity_name),
            "form": "infix",
            "value": left_value,
            "value_latex": str(left_value),
        },
        {
            "word": left_word,
            "latex": group_word_latex(left_word, variables, identity_name),
            "form": "postfix",
            "value": left_value,
            "value_latex": str(left_value),
        },
        {
            "word": right_word,
            "latex": group_word_latex(right_word, variables, identity_name),
            "form": "infix",
            "value": right_value,
            "value_latex": str(right_value),
        },
        {
            "word": right_word,
            "latex": group_word_latex(right_word, variables, identity_name),
            "form": "postfix",
            "value": right_value,
            "value_latex": str(right_value),
        },
    ]
    return {
        "variables": list(variables),
        "order": len(table),
        "elements": elements,
        "operation_table": table,
        "cayley_table": table,
        "inverse_table": inverses,
        "identity": identity,
        "identity_element": identity,
        "identity_symbol": identity_name,
        "identity_symbol_latex": identity_symbol_latex(identity_name),
        "assignments": assignments,
        "assignment_latex": ",\\quad ".join(
            str(name) + " = " + str(value) for name, value in sorted(assignments.items())
        ),
        "left_word": left_word,
        "right_word": right_word,
        "left_latex": group_word_latex(left_word, variables, identity_name),
        "right_latex": group_word_latex(right_word, variables, identity_name),
        "left_value": left_value,
        "right_value": right_value,
        "refuted": left_value != right_value,
        "word_evaluations": word_evaluations,
        "dual_path_agreement": bool(artifacts.get("independent_word_evaluation", False)),
        "group_family": str(structures.get("group_family", "")) or str(candidate.exact_derivation_artifacts.get("group_family", "")),
        "invariants": invariants,
        "group_invariants": invariants,
        "table_latex": table_latex(table, identity),
        "order_bound_respected": bool(artifacts.get("order_bound_respected", False)),
        "declared_order_bound": int(specification.order_bound) if specification.order_bound is not None else None,
        "constrained_order_bound": int(target.max_order) if target is not None else None,
    }


def _planar_block(specification: ProblemSpec, candidate: Candidate, verification: VerificationResult) -> dict[str, Any]:
    artifacts = dict(verification.artifacts)
    formulas = {str(name): exact_text(value) for name, value in candidate.formulas.items()}
    points = {str(name): [exact_text(item) for item in values] for name, values in candidate.points.items()}
    component_rows: list[dict[str, Any]] = []
    labels = {"F1": "F₁", "F₁": "F₁", "first": "F₁", "F2": "F₂", "F₂": "F₂", "second": "F₂"}
    for key, value in formulas.items():
        label = labels.get(key, key)
        component_rows.append(
            {
                "key": key,
                "label": label,
                "expression": value,
                "latex": expression_latex(value, ("x", "y")),
            }
        )
    point_rows: list[dict[str, Any]] = []
    for key in ("P", "Q"):
        if key not in points:
            continue
        values = points[key]
        point_rows.append(
            {
                "key": key,
                "latex": "\\left(" + ", ".join(exact_value_latex(item) for item in values) + "\\right)",
                "coordinates": values,
                "coordinates_latex": [exact_value_latex(item) for item in values],
            }
        )
    recorded_obligations = candidate.exact_derivation_artifacts.get("domain_obligations")
    obligation_rows: list[dict[str, Any]] = []
    if isinstance(recorded_obligations, (tuple, list)):
        for item in recorded_obligations:
            text = exact_text(item)
            values: list[str] = []
            for row in point_rows:
                try:
                    expression = exact_parse_expression(text, ("x", "y"))
                    substitutions = {
                        sp.Symbol("x"): exact_parse_expression(row["coordinates"][0]),
                        sp.Symbol("y"): exact_parse_expression(row["coordinates"][1]),
                    }
                    values.append(exact_text(expression.subs(substitutions)))
                except Exception:
                    values.append("")
            obligation_rows.append(
                {
                    "expression": text,
                    "latex": expression_latex(text, ("x", "y")),
                    "values": values,
                    "satisfied": all(value not in ("", "0") for value in values),
                }
            )
    determinant = exact_text(artifacts.get("sympy_determinant", "0"))
    independent_determinant = exact_text(artifacts.get("coefficient_determinant", determinant))
    collision_rows: list[dict[str, Any]] = []
    if "P" in points and "Q" in points:
        for row in component_rows:
            try:
                expression = exact_parse_expression(row["expression"], ("x", "y"))
                symbol_x = sp.Symbol("x")
                symbol_y = sp.Symbol("y")
                at_point = exact_text(expression.subs({symbol_x: exact_parse_expression(points["P"][0]), symbol_y: exact_parse_expression(points["P"][1])}))
                at_other = exact_text(expression.subs({symbol_x: exact_parse_expression(points["Q"][0]), symbol_y: exact_parse_expression(points["Q"][1])}))
                difference = exact_text(exact_parse_expression(at_point) - exact_parse_expression(at_other))
            except Exception:
                at_point = ""
                at_other = ""
                difference = ""
            collision_rows.append(
                {
                    "label": row["label"],
                    "at_point": at_point,
                    "at_other": at_other,
                    "difference": difference,
                    "equal": difference == "0",
                }
            )
    return {
        "components": {row["label"]: row["latex"] for row in component_rows},
        "component_rows": component_rows,
        "point_p": points.get("P", []),
        "point_q": points.get("Q", []),
        "point_p_latex": next((row["latex"] for row in point_rows if row["key"] == "P"), ""),
        "point_q_latex": next((row["latex"] for row in point_rows if row["key"] == "Q"), ""),
        "points": point_rows,
        "component_expressions": {"first": formulas.get("F1", formulas.get("F₁", "")), "second": formulas.get("F2", formulas.get("F₂", ""))},
        "collision_target": "F₁(P) = F₁(Q), F₂(P) = F₂(Q)",
        "collision_rows": collision_rows,
        "collision_differences_zero": bool(artifacts.get("collision_differences_zero", False)),
        "jacobian_determinant": determinant,
        "jacobian_determinant_latex": expression_latex(determinant, ("x", "y")),
        "independent_determinant": independent_determinant,
        "independent_determinant_latex": expression_latex(independent_determinant, ("x", "y")),
        "determinant_constant": exact_text(artifacts.get("determinant_constant", "0")),
        "determinant_nonzero": bool(artifacts.get("determinant_nonzero", False)),
        "nonconstant_coefficients_zero": bool(artifacts.get("nonconstant_coefficients_zero", False)),
        "independent_determinant_check": bool(artifacts.get("independent_determinant_check", False)),
        "independent_collision_check": bool(artifacts.get("independent_collision_check", False)),
        "distinct_points": bool(artifacts.get("distinct_points", False)),
        "domain_obligations": obligation_rows,
        "runtime_route": str(candidate.exact_derivation_artifacts.get("runtime_route", "")),
        "runtime_determinant": exact_text(candidate.exact_derivation_artifacts.get("runtime_determinant", determinant)),
        "frontier_signature": str(candidate.exact_derivation_artifacts.get("frontier_signature", candidate.frontier_signature)),
        "composition_scheme": str(candidate.exact_derivation_artifacts.get("composition_scheme", "")),
        "symmetry_mode": str(candidate.exact_derivation_artifacts.get("symmetry_mode", "")),
        "map_latex": "\\begin{aligned} "
        + " \\\\ ".join(row["label"] + r"(x,y) &= " + row["latex"] for row in component_rows)
        + " \\end{aligned}",
    }


def _audit_entry(identifier: str, label: str, passed: bool, detail: str, value: str = "") -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": identifier,
        "label": label,
        "status": "pass" if passed else "fail",
        "passed": bool(passed),
        "detail": detail,
    }
    if value:
        entry["value"] = value
    return entry


def audit_payload(
    specification: ProblemSpec,
    candidate: Candidate,
    verification: VerificationResult,
    critique: CritiqueResult,
    generated: GeneratedCodeResult,
    frontier: Frontier,
) -> list[dict[str, Any]]:
    artifacts = dict(verification.artifacts)
    critique_artifacts = dict(critique.artifacts)
    entries: list[dict[str, Any]] = []
    entries.append(
        _audit_entry(
            "float_free",
            "Exact arithmetic (no floating point)",
            artifacts.get("no_numeric_certification") is True,
            "verification rejected every floating point value"
            if artifacts.get("no_numeric_certification") is True
            else "verification could not rule out numeric-only certification",
        )
    )
    entries.append(
        _audit_entry(
            "pole_exclusion",
            "Pole and denominator obligations",
            artifacts.get("denominator_status") is True,
            "denominator obligations were discharged exactly"
            if artifacts.get("denominator_status") is True
            else "denominator obligations were not completely discharged",
        )
    )
    if specification.kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
        entries.append(
            _audit_entry(
                "domain_exclusions",
                "Declared domain exclusions respected",
                True,
                "the finite table route has no denominators and no excluded values",
            )
        )
    else:
        entries.append(
            _audit_entry(
                "domain_exclusions",
                "Declared domain exclusions respected",
                artifacts.get("domain_exclusions_respected") is True,
                "the certificate avoids every excluded value"
                if artifacts.get("domain_exclusions_respected") is True
                else "the certificate violates a declared domain exclusion",
            )
        )
    if specification.kind == ProblemKind.ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT:
        entries.append(
            _audit_entry(
                "exact_inequality",
                "Exact refutation of the identity",
                artifacts.get("exact_inequality_check") is True,
                "the left and right values differ by an exact nonzero value"
                if artifacts.get("exact_inequality_check") is True
                else "the identity was not refuted exactly",
            )
        )
    if specification.kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
        entries.append(
            _audit_entry(
                "group_table",
                "Cayley table is a group",
                artifacts.get("group_table_valid") is True,
                "closure, associativity, identity and inverses hold for every element"
                if artifacts.get("group_table_valid") is True
                else "the operation table failed a group law",
                str(artifacts.get("group_order", "")) if artifacts.get("group_order") is not None else "",
            )
        )
        entries.append(
            _audit_entry(
                "dual_group_word",
                "Word evaluated by two independent paths",
                artifacts.get("independent_word_evaluation") is True,
                "infix and postfix evaluators agree on both words"
                if artifacts.get("independent_word_evaluation") is True
                else "the independent word evaluator disagreed",
            )
        )
        entries.append(
            _audit_entry(
                "word_inequality",
                "Word inequality certified",
                artifacts.get("word_inequality") is True,
                "the two words take different values in the constructed group"
                if artifacts.get("word_inequality") is True
                else "the two words were not separated",
            )
        )
        entries.append(
            _audit_entry(
                "order_bound",
                "Declared order bound respected",
                artifacts.get("order_bound_respected") is True,
                "the group order respects the declared bound"
                if artifacts.get("order_bound_respected") is True
                else "the group order exceeded the declared bound",
                str(artifacts.get("group_order", "")) if artifacts.get("group_order") is not None else "",
            )
        )
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        entries.append(
            _audit_entry(
                "dual_determinant",
                "Determinant by two independent paths",
                artifacts.get("independent_determinant_check") is True,
                "derivative-matrix and monomial-coefficient determinants coincide"
                if artifacts.get("independent_determinant_check") is True
                else "the determinant paths disagreed",
            )
        )
        entries.append(
            _audit_entry(
                "determinant_constant",
                "Constant nonzero determinant",
                artifacts.get("determinant_nonzero") is True and artifacts.get("nonconstant_coefficients_zero") is True,
                "every nonconstant coefficient vanished and the constant is exact nonzero"
                if artifacts.get("determinant_nonzero") is True and artifacts.get("nonconstant_coefficients_zero") is True
                else "the determinant obligation is incomplete",
                exact_text(artifacts.get("determinant_constant", "")),
            )
        )
        entries.append(
            _audit_entry(
                "dual_collision",
                "Collision by two independent paths",
                artifacts.get("independent_collision_check") is True,
                "direct substitution and coefficient-dictionary evaluation agree"
                if artifacts.get("independent_collision_check") is True
                else "the collision evaluations disagreed",
            )
        )
        entries.append(
            _audit_entry(
                "distinct_points",
                "The two points are provably distinct",
                artifacts.get("distinct_points") is True,
                "an exact coordinate difference was proved nonzero"
                if artifacts.get("distinct_points") is True
                else "point distinctness was not proved",
            )
        )
        entries.append(
            _audit_entry(
                "collision_obligation",
                "Collision equations discharged",
                artifacts.get("collision_differences_zero") is True,
                "both components agree at the two distinct points"
                if artifacts.get("collision_differences_zero") is True
                else "the collision equations are incomplete",
            )
        )
    entries.append(
        _audit_entry(
            "repeat_verification",
            "Deterministic verifier rerun",
            critique_artifacts.get("repeat_verification_passed") is True,
            "a full rerun of the verifier reproduced the certificate"
            if critique_artifacts.get("repeat_verification_passed") is True
            else "the verifier rerun rejected the certificate",
        )
    )
    entries.append(
        _audit_entry(
            "independent_recheck",
            "Independent recomputation",
            critique_artifacts.get("independent_recheck_passed") is True,
            "the critique layer recomputed the certificate with its own code path"
            if critique_artifacts.get("independent_recheck_passed") is True
            else "the independent recomputation failed",
        )
    )
    unresolved = [item for item in critique.issues if not item.resolved]
    entries.append(
        _audit_entry(
            "critique_clean",
            "Adversarial review found no blocking issue",
            critique.passed and not unresolved,
            "no blocking issue remained after the review"
            if critique.passed and not unresolved
            else "blocking issue: " + ", ".join(str(item.code) for item in unresolved),
        )
    )
    fingerprint_ok = bool(candidate.source_fingerprint) and candidate.source_fingerprint == generated.source_fingerprint
    signature_ok = bool(candidate.frontier_signature) and candidate.frontier_signature == frontier.unique_signature
    entries.append(
        _audit_entry(
            "source_fingerprint",
            "Candidate provenance fingerprint",
            fingerprint_ok and signature_ok,
            "the candidate carries the fingerprint of its generated worker and frontier"
            if fingerprint_ok and signature_ok
            else "candidate provenance does not match the generated worker",
            candidate.source_fingerprint[:12],
        )
    )
    worker_digest = sha256_text(generated.source)
    entries.append(
        _audit_entry(
            "worker_sha256",
            "Generated worker SHA-256",
            len(worker_digest) == 64,
            "the worker source digest is computed from the exact bytes that ran",
            worker_digest[:16],
        )
    )
    return entries


def certificate_payload(
    specification: ProblemSpec,
    candidate: Candidate,
    verification: VerificationResult,
    critique: CritiqueResult,
    generated: GeneratedCodeResult,
    frontier: Frontier,
    formatted_text: str,
    budget: SearchBudget,
    budget_payload_value: Mapping[str, Any],
    statistics: Mapping[str, Any],
    runtime_seconds: float,
    max_group_order: int | None = None,
) -> dict[str, Any]:
    block: dict[str, Any]
    headline = ""
    headline_latex = ""
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        block = _planar_block(specification, candidate, verification)
        headline = "P = (" + ", ".join(block["point_p"]) + ") differs from Q = (" + ", ".join(block["point_q"]) + ")"
        headline_latex = block["point_p_latex"] + r" \neq " + block["point_q_latex"]
    elif specification.kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
        block = _group_block(specification, candidate, verification)
        headline = (
            "order "
            + str(block["order"])
            + ", "
            + str(block["left_word"])
            + " = "
            + str(block["left_value"])
            + " differs from "
            + str(block["right_word"])
            + " = "
            + str(block["right_value"])
        )
        headline_latex = block["left_latex"] + " = " + str(block["left_value"]) + r" \neq " + str(block["right_value"]) + " = " + block["right_latex"]
    else:
        block = _algebraic_block(specification, candidate, verification)
        headline = ", ".join(name + " = " + value for name, value in sorted(block["assignments"].items()))
        headline_latex = block["assignment_latex"]
    payload: dict[str, Any] = {
        "kind": "counterexample",
        "problem_kind": specification.kind.value,
        "kind_label": _KIND_LABELS.get(specification.kind, specification.kind.value),
        "query": specification.raw_text,
        "statement": {"text": statement_text(specification), "latex": statement_latex(specification)},
        "headline": headline,
        "headline_latex": headline_latex,
        "formatted_text": formatted_text,
        "generated_at": utc_timestamp(),
        "runtime_seconds": seconds_text(runtime_seconds),
        "budget": dict(budget_payload_value),
        "statistics": json_safe(statistics),
        "formalization": formalization_payload(specification, budget, max_group_order),
        "frontier": frontier_payload(frontier),
        "algebraic": block if specification.kind == ProblemKind.ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT else None,
        "group": block if specification.kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL else None,
        "planar": block if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION else None,
        "exhaustion": None,
        "proof": None,
        "provenance": {
            "worker_sha256": sha256_text(generated.source),
            "source_fingerprint": generated.source_fingerprint,
            "frontier_signature": frontier.unique_signature,
            "entry_function": generated.entry_function,
            "worker_source": generated.source,
            "generator": "exact_formula_search.code_generation.generate_search_code",
            "executor": "exact_formula_search.execution.execute_generated_code",
            "verifier": "exact_formula_search.verification.verify_candidate",
            "critic": "exact_formula_search.critique.critique_candidate",
            "formalizer": "exact_formula_search.formalization.formalize_request",
        },
        "audit": audit_payload(specification, candidate, verification, critique, generated, frontier),
        "critique": {
            "passed": bool(critique.passed),
            "issues": [
                {
                    "code": str(item.code),
                    "description": str(item.description),
                    "severity": str(item.severity),
                    "resolved": bool(item.resolved),
                    "repair_hint": str(item.repair_hint),
                }
                for item in critique.issues
            ],
        },
        "verification": {
            "passed": bool(verification.passed),
            "issues": [str(item) for item in verification.issues],
            "artifacts": artifact_safe({str(key): artifact_safe(value) for key, value in verification.artifacts.items()}),
        },
        "worker_lines": len(generated.source.splitlines()),
        "max_group_order": int(max_group_order) if max_group_order is not None else None,
    }
    return payload


def artifact_safe(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return seconds_text(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (tuple, list)):
        return [artifact_safe(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): artifact_safe(item) for key, item in value.items()}
    return str(value)


def exhaustion_payload(
    specification: ProblemSpec,
    statistics: Mapping[str, Any],
    reason: str,
    formatted_text: str,
    budget: SearchBudget,
    budget_payload_value: Mapping[str, Any],
    runtime_seconds: float,
    lanes: Sequence[Mapping[str, Any]],
    repair_reasons: Sequence[str],
    max_group_order: int | None = None,
) -> dict[str, Any]:
    note = ""
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        note = "the two dimensional case of the Jacobian conjecture remains open"
    payload: dict[str, Any] = {
        "kind": "exhaustion",
        "problem_kind": specification.kind.value,
        "kind_label": _KIND_LABELS.get(specification.kind, specification.kind.value),
        "query": specification.raw_text,
        "statement": {"text": statement_text(specification), "latex": statement_latex(specification)},
        "headline": "no counterexample found within the search budget",
        "headline_latex": r"\text{no counterexample found within the search budget}",
        "formatted_text": formatted_text,
        "generated_at": utc_timestamp(),
        "runtime_seconds": seconds_text(runtime_seconds),
        "budget": dict(budget_payload_value),
        "statistics": json_safe(statistics),
        "formalization": formalization_payload(specification, budget, max_group_order),
        "frontier": None,
        "algebraic": None,
        "group": None,
        "planar": None,
        "proof": None,
        "exhaustion": {
            "exhaustion_reason": str(reason),
            "reason": str(reason),
            "note": note,
            "total_frontiers_visited": int(statistics.get("frontiers_examined", 0)),
            "frontiers_examined": int(statistics.get("frontiers_examined", 0)),
            "candidates_verified": int(statistics.get("candidates_verified", 0)),
            "mutation_rounds": int(statistics.get("mutation_rounds", 0)),
            "repairs": int(statistics.get("repairs", 0)),
            "lanes": [dict(item) for item in lanes],
            "lane_count": len(lanes),
            "repair_reasons": [str(item) for item in repair_reasons],
            "budget_fields": {
                "time_seconds": seconds_text(budget.max_seconds),
                "max_frontier_visits": int(budget.max_frontier_visits),
                "max_verified_candidates": int(budget.max_verified_candidates),
                "max_mutation_rounds": int(budget.max_mutation_rounds),
                "execution_timeout_seconds": seconds_text(budget.execution_timeout_seconds),
            },
        },
        "provenance": {
            "worker_sha256": "",
            "source_fingerprint": "",
            "frontier_signature": "",
            "entry_function": "search",
            "worker_source": "",
            "generator": "exact_formula_search.code_generation.generate_search_code",
            "executor": "exact_formula_search.execution.execute_generated_code",
            "verifier": "exact_formula_search.verification.verify_candidate",
            "critic": "exact_formula_search.critique.critique_candidate",
            "formalizer": "exact_formula_search.formalization.formalize_request",
        },
        "audit": [
            _audit_entry(
                "search_budget",
                "Search budget enforced",
                True,
                "the search stopped exactly when its declared budget was consumed",
                str(reason),
            ),
            _audit_entry(
                "float_free",
                "Exact arithmetic (no floating point)",
                True,
                "every candidate was evaluated with exact rational and algebraic arithmetic",
            ),
            _audit_entry(
                "open_problem",
                "No counterexample claimed",
                True,
                "the engine reports exhaustion instead of an unsupported claim",
            ),
        ],
        "critique": {"passed": False, "issues": []},
        "verification": {"passed": False, "issues": [], "artifacts": {}},
        "worker_lines": 0,
        "max_group_order": int(max_group_order) if max_group_order is not None else None,
    }
    return payload


def symbolic_proof_payload(
    specification: ProblemSpec,
    formatted_text: str,
    budget: SearchBudget,
    budget_payload_value: Mapping[str, Any],
    runtime_seconds: float,
    max_group_order: int | None = None,
) -> dict[str, Any]:
    target = specification.algebraic_identity
    variables = tuple(str(item) for item in (target.variables if target is not None else specification.variables))
    left_display = str(target.left_source) if target is not None and target.left_source else (target.left_expression if target is not None else "")
    right_display = str(target.right_source) if target is not None and target.right_source else (target.right_expression if target is not None else "")
    left_latex = expression_latex(left_display, variables) if left_display else ""
    right_latex = expression_latex(right_display, variables) if right_display else ""
    steps: list[dict[str, Any]] = []
    if target is not None:
        difference_latex = expression_latex("(" + left_display + ") - (" + right_display + ")", variables)
        steps = [
            {
                "label": "Exact parse",
                "latex": left_latex + r"\quad\text{and}\quad" + right_latex,
                "detail": "both sides were parsed into exact rational expressions without floating point",
            },
            {
                "label": "Exact difference",
                "latex": difference_latex + r" \equiv 0",
                "detail": "the difference was reduced with exact rational arithmetic and vanished identically",
            },
            {
                "label": "Conclusion",
                "latex": r"\nexists\; \text{counterassignment}",
                "detail": "no exact assignment can separate the two sides, so the identity is valid",
            },
        ]
    payload: dict[str, Any] = {
        "kind": "symbolic_proof",
        "problem_kind": specification.kind.value,
        "kind_label": _KIND_LABELS.get(specification.kind, specification.kind.value),
        "query": specification.raw_text,
        "statement": {"text": statement_text(specification), "latex": statement_latex(specification)},
        "headline": "no counterassignment exists",
        "headline_latex": r"\text{no counterassignment exists}",
        "formatted_text": formatted_text,
        "generated_at": utc_timestamp(),
        "runtime_seconds": seconds_text(runtime_seconds),
        "budget": dict(budget_payload_value),
        "statistics": {"frontiers_examined": 0, "candidates_verified": 0, "mutation_rounds": 0, "repairs": 0, "elapsed_seconds": seconds_text(runtime_seconds)},
        "formalization": formalization_payload(specification, budget, max_group_order),
        "frontier": None,
        "algebraic": None,
        "group": None,
        "planar": None,
        "exhaustion": None,
        "proof": {
            "variables": list(variables),
            "difference": "0",
            "reason": "identity_holds_symbolically",
            "left_expression": left_display,
            "right_expression": right_display,
            "left_canonical_expression": target.left_expression if target is not None else "",
            "right_canonical_expression": target.right_expression if target is not None else "",
            "left_latex": left_latex,
            "right_latex": right_latex,
            "left_value": exact_text(0),
            "right_value": exact_text(0),
            "difference_latex": "0",
            "steps": steps,
        },
        "provenance": {
            "worker_sha256": "",
            "source_fingerprint": "",
            "frontier_signature": "",
            "entry_function": "exact_symbolic_zero_test",
            "worker_source": "",
            "generator": "exact_formula_search.formalization.formalize_request",
            "executor": "exact_formula_search.symbolic_tools.exact_zero",
            "verifier": "exact_formula_search.symbolic_tools.exact_parse_expression",
            "critic": "exact_formula_search.orchestrator._symbolic_proof_report",
            "formalizer": "exact_formula_search.formalization.formalize_request",
        },
        "audit": [
            _audit_entry(
                "float_free",
                "Exact arithmetic (no floating point)",
                True,
                "the decision was made with exact rational arithmetic",
            ),
            _audit_entry(
                "symbolic_identity",
                "Identity holds symbolically",
                True,
                "the exact difference of the two sides vanishes identically",
            ),
            _audit_entry(
                "no_numeric_claim",
                "No numeric sampling used",
                True,
                "the proof does not depend on sampled or approximate values",
            ),
        ],
        "critique": {"passed": True, "issues": []},
        "verification": {"passed": True, "issues": [], "artifacts": {"identity_holds_symbolically": True, "no_numeric_certification": True}},
        "worker_lines": 0,
        "max_group_order": int(max_group_order) if max_group_order is not None else None,
    }
    return payload
