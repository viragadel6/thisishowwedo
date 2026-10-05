from __future__ import annotations

import contextlib
import io
from typing import Any, Mapping

from .models import Candidate, Frontier, FrontierResult, GeneratedCodeResult, ProblemSpec


def _candidate_from_mapping(
    item: Mapping[str, Any],
    specification: ProblemSpec,
    generated: GeneratedCodeResult,
    frontier: Frontier,
) -> Candidate:
    raw_points = dict(item.get("points") or {})
    points = {str(key): tuple(str(coordinate) for coordinate in value) for key, value in raw_points.items()}
    return Candidate(
        problem_kind=specification.kind,
        formulas={str(key): str(value) for key, value in dict(item.get("formulas") or {}).items()},
        points=points,
        assignments=dict(item.get("assignments") or {}),
        finite_structures=dict(item.get("finite_structures") or {}),
        exact_derivation_artifacts=dict(item.get("exact_derivation_artifacts") or {}),
        source_fingerprint=generated.source_fingerprint,
        frontier_signature=frontier.unique_signature,
    )


def execute_generated_code(generated: GeneratedCodeResult, specification: ProblemSpec, frontier: Frontier) -> FrontierResult:
    namespace: dict[str, Any] = {}
    output_buffer = io.StringIO()
    error_buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(error_buffer):
            compiled = compile(generated.source, f"<generated:{generated.source_fingerprint}>", "exec")
            exec(compiled, namespace, namespace)
            function = namespace.get(generated.entry_function)
            if not callable(function):
                return FrontierResult(frontier=frontier, generated_result=generated, failure_reasons=("missing_search_function",))
            raw_result = function()
    except Exception as exception:
        return FrontierResult(
            frontier=frontier,
            generated_result=generated,
            candidates=(),
            failure_reasons=("generated_execution_exception",),
            exception_text=repr(exception)[:500],
        )
    failures: list[str] = []
    candidates: list[Candidate] = []
    artifacts: dict[str, Any] = {}
    if not isinstance(raw_result, Mapping):
        return FrontierResult(frontier=frontier, generated_result=generated, failure_reasons=("invalid_generated_result",))
    for failure in raw_result.get("failures") or ():
        failures.append(str(failure))
    artifacts.update(dict(raw_result.get("artifacts") or {}))
    for raw_candidate in raw_result.get("candidates") or ():
        if isinstance(raw_candidate, Mapping):
            try:
                candidates.append(_candidate_from_mapping(raw_candidate, specification, generated, frontier))
            except Exception as exception:
                failures.append(type(exception).__name__)
        else:
            failures.append("invalid_candidate_shape")
    if not candidates and not failures:
        failures.append("empty_result")
    return FrontierResult(
        frontier=frontier,
        generated_result=generated,
        candidates=tuple(candidates),
        failure_reasons=tuple(failures),
        internal_artifacts=artifacts,
    )
