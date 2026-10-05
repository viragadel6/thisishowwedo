from __future__ import annotations

from dataclasses import asdict
from enum import Enum
from typing import Any, Mapping

from .models import GeneratedCodeResult, ProblemSpec, Frontier
from .symbolic_tools import stable_signature


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return _plain(asdict(value))
    return value


def _frontier_payload(frontier: Frontier) -> dict[str, Any]:
    return {
        "kind": frontier.kind.value,
        "degree_extent": frontier.degree_extent,
        "coefficient_extent": frontier.coefficient_extent,
        "support_sets": frontier.support_sets,
        "symmetry_mode": frontier.symmetry_mode.value,
        "composition_scheme": frontier.composition_scheme.value,
        "elimination_objective": frontier.elimination_objective.value,
        "point_pattern": frontier.point_pattern.value,
        "exact_domain": frontier.exact_domain.value,
        "lane_identifier": frontier.lane_identifier,
        "mutation_lineage": frontier.mutation_lineage,
        "unique_signature": frontier.unique_signature,
        "extra_parameters": dict(frontier.extra_parameters),
    }


def _problem_payload(specification: ProblemSpec) -> dict[str, Any]:
    return {
        "kind": specification.kind.value,
        "raw_text": specification.raw_text,
        "normalized_tokens": specification.normalized_tokens,
        "variables": specification.variables,
        "mappings": dict(specification.mappings),
        "predicates": specification.predicates,
        "domains": tuple(domain.value for domain in specification.domains),
        "output_roles": dict(specification.output_roles),
        "planar_target": _plain(specification.planar_target) if specification.planar_target is not None else None,
        "algebraic_identity": _plain(specification.algebraic_identity) if specification.algebraic_identity is not None else None,
        "finite_group_identity": _plain(specification.finite_group_identity) if specification.finite_group_identity is not None else None,
    }


def generate_search_code(specification: ProblemSpec, frontier: Frontier) -> GeneratedCodeResult:
    frontier_payload = _frontier_payload(frontier)
    problem_payload = _problem_payload(specification)
    source = "\n".join(
        (
            "from exact_formula_search.generated_runtime import run_generated_search",
            f"FRONTIER = {repr(frontier_payload)}",
            f"PROBLEM = {repr(problem_payload)}",
            "def search():",
            "    return run_generated_search(FRONTIER, PROBLEM)",
            "",
        )
    )
    fingerprint = stable_signature(source)
    return GeneratedCodeResult(
        frontier_signature=frontier.unique_signature,
        source=source,
        entry_function="search",
        source_fingerprint=fingerprint,
        generation_issues=(),
    )
