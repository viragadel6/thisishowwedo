from __future__ import annotations

import ast
from dataclasses import asdict
from enum import Enum
from typing import Any, Mapping

from .models import GeneratedCodeResult, ProblemSpec, Frontier, SearchBudget
from .symbolic_tools import stable_signature

_ALLOWED_IMPORT_MODULE = "exact_formula_search.generated_runtime"
_ALLOWED_IMPORT_NAMES = frozenset({"run_generated_search"})
_ALLOWED_ENTRY_ARGUMENT_NAMES = frozenset({"FRONTIER", "PROBLEM", "SOURCE_FINGERPRINT"})
_ALLOWED_NODE_TYPES = (
    ast.Module,
    ast.ImportFrom,
    ast.alias,
    ast.Assign,
    ast.Name,
    ast.Constant,
    ast.Load,
    ast.Store,
    ast.FunctionDef,
    ast.arguments,
    ast.Return,
    ast.Call,
    ast.Dict,
    ast.List,
    ast.Tuple,
)


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


def _problem_payload(specification: ProblemSpec, limits: SearchBudget | None = None) -> dict[str, Any]:
    budget = limits if limits is not None else SearchBudget()
    return {
        "kind": specification.kind.value,
        "raw_text": specification.raw_text,
        "normalized_tokens": specification.normalized_tokens,
        "variables": specification.variables,
        "mappings": dict(specification.mappings),
        "predicates": specification.predicates,
        "domains": tuple(domain.value for domain in specification.domains),
        "output_roles": dict(specification.output_roles),
        "constraints": specification.constraints,
        "order_bound": specification.order_bound,
        "search_limits": {
            "max_candidates": budget.max_candidates_per_frontier,
            "max_instances": budget.max_instances_per_solve,
            "max_point_pairs": budget.max_point_pairs,
        },
        "planar_target": _plain(specification.planar_target) if specification.planar_target is not None else None,
        "algebraic_identity": _plain(specification.algebraic_identity) if specification.algebraic_identity is not None else None,
        "finite_group_identity": _plain(specification.finite_group_identity) if specification.finite_group_identity is not None else None,
    }


def _source_template(frontier_payload: Mapping[str, Any], problem_payload: Mapping[str, Any], fingerprint: str) -> str:
    return "\n".join(
        (
            "from exact_formula_search.generated_runtime import run_generated_search",
            "FRONTIER = " + repr(dict(frontier_payload)),
            "PROBLEM = " + repr(dict(problem_payload)),
            "SOURCE_FINGERPRINT = " + repr(fingerprint),
            "def search():",
            "    return run_generated_search(FRONTIER, PROBLEM, SOURCE_FINGERPRINT)",
            "",
        )
    )


def _validate_node_types(node: ast.AST) -> tuple[str, ...]:
    issues: list[str] = []
    for child in ast.walk(node):
        if not isinstance(child, _ALLOWED_NODE_TYPES):
            issues.append("disallowed_syntax_node:" + type(child).__name__)
            return tuple(issues)
    return ()


def validate_generated_source(source: str, entry_function: str = "search") -> tuple[str, ...]:
    issues: list[str] = []
    try:
        tree = ast.parse(str(source))
    except SyntaxError:
        return ("unparsable_generated_source",)
    except Exception:
        return ("unparsable_generated_source",)
    issues.extend(_validate_node_types(tree))
    assigned: set[str] = set()
    imported: set[str] = set()
    entry = None
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.level != 0 or node.module != _ALLOWED_IMPORT_MODULE:
                issues.append("disallowed_import_module")
            for alias in node.names:
                if alias.name not in _ALLOWED_IMPORT_NAMES:
                    issues.append("disallowed_import_name")
                else:
                    imported.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned.add(target.id)
                else:
                    issues.append("disallowed_assignment_target")
        elif isinstance(node, ast.FunctionDef):
            if node.name == entry_function:
                entry = node
        else:
            issues.append("disallowed_statement:" + type(node).__name__)
    if entry is None:
        issues.append("missing_entry_function")
        return tuple(dict.fromkeys(issues))
    if entry.args.args or entry.args.vararg or entry.args.kwarg or entry.args.kwonlyargs or entry.args.defaults:
        issues.append("entry_function_parameters_present")
    if len(entry.body) != 1 or not isinstance(entry.body[0], ast.Return):
        issues.append("entry_function_body_not_single_return")
        return tuple(dict.fromkeys(issues))
    call = entry.body[0].value
    if not isinstance(call, ast.Call):
        issues.append("entry_function_return_not_call")
        return tuple(dict.fromkeys(issues))
    if not isinstance(call.func, ast.Name) or call.func.id not in imported:
        issues.append("entry_function_calls_unimported_symbol")
    if call.keywords:
        issues.append("entry_function_keyword_arguments")
    if len(call.args) != 3:
        issues.append("entry_function_argument_count")
    for argument in call.args:
        if not isinstance(argument, ast.Name) or argument.id not in _ALLOWED_ENTRY_ARGUMENT_NAMES:
            issues.append("disallowed_entry_argument")
        elif argument.id not in assigned and argument.id != "SOURCE_FINGERPRINT":
            issues.append("unassigned_entry_argument")
    return tuple(dict.fromkeys(issues))


def generate_search_code(specification: ProblemSpec, frontier: Frontier, limits: SearchBudget | None = None) -> GeneratedCodeResult:
    frontier_payload = _frontier_payload(frontier)
    problem_payload = _problem_payload(specification, limits)
    fingerprint = stable_signature({"frontier": dict(frontier_payload), "problem": dict(problem_payload), "entry_function": "search"})
    source = _source_template(frontier_payload, problem_payload, fingerprint)
    validation_issues = validate_generated_source(source, "search")
    return GeneratedCodeResult(
        frontier_signature=frontier.unique_signature,
        source=source,
        entry_function="search",
        source_fingerprint=fingerprint,
        generation_issues=validation_issues,
    )
