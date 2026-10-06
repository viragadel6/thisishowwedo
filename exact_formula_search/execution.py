from __future__ import annotations

import contextlib
import io
import multiprocessing
from typing import Any, Mapping

from .code_generation import validate_generated_source
from .models import Candidate, Frontier, FrontierResult, GeneratedCodeResult, ProblemSpec, SearchBudget

_ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "exact_formula_search",
        "exact_formula_search.generated_runtime",
        "exact_formula_search.symbolic_tools",
        "exact_formula_search.models",
    }
)
_ADDRESS_SPACE_LIMIT = 2 * 1024 * 1024 * 1024
_CPU_LIMIT_SECONDS = 60


def _restricted_import(name: str, globals: Any = None, locals: Any = None, fromlist: Any = (), level: int = 0) -> Any:
    if level != 0 or str(name) not in _ALLOWED_IMPORT_ROOTS:
        raise ImportError("import_not_allowed:" + str(name))
    return __import__(name, globals, locals, fromlist, level)


def _apply_resource_limits() -> None:
    try:
        import resource
    except Exception:
        return
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        target = _ADDRESS_SPACE_LIMIT
        if hard != resource.RLIM_INFINITY:
            target = min(hard, target)
        new_soft = target if soft == resource.RLIM_INFINITY else min(soft, target)
        if new_soft > 0:
            resource.setrlimit(resource.RLIMIT_AS, (new_soft, target))
    except Exception:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (_CPU_LIMIT_SECONDS, _CPU_LIMIT_SECONDS))
    except Exception:
        pass


def _worker(source: str, entry_function: str, fingerprint: str, connection: Any) -> None:
    try:
        _apply_resource_limits()
        namespace: dict[str, Any] = {"__builtins__": {"__import__": _restricted_import}}
        output_buffer = io.StringIO()
        error_buffer = io.StringIO()
        with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(error_buffer):
            compiled = compile(source, "<generated:" + str(fingerprint) + ">", "exec")
            exec(compiled, namespace, namespace)
            function = namespace.get(entry_function)
            if not callable(function):
                connection.send({"status": "missing_search_function", "payload": None})
                return
            payload = function()
        connection.send({"status": "ok", "payload": payload, "stdout": output_buffer.getvalue()[:2000], "stderr": error_buffer.getvalue()[:2000]})
    except BaseException as exception:
        try:
            connection.send({"status": "exception", "exception": repr(exception)[:500], "payload": None})
        except Exception:
            pass
    finally:
        try:
            connection.close()
        except Exception:
            pass


def _run_isolated(source: str, entry_function: str, fingerprint: str, timeout: float) -> dict[str, Any]:
    try:
        context = multiprocessing.get_context("fork")
    except ValueError:
        context = multiprocessing.get_context()
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(source, entry_function, fingerprint, sender), daemon=True)
    try:
        process.start()
    except Exception as exception:
        try:
            sender.close()
            receiver.close()
        except Exception:
            pass
        return {"status": "process_start_failed", "exception": repr(exception)[:500]}
    received: dict[str, Any] | None = None
    try:
        if receiver.poll(max(1.0, float(timeout))):
            try:
                received = receiver.recv()
            except Exception as exception:
                received = {"status": "no_result", "exception": repr(exception)[:500]}
    except Exception as exception:
        received = {"status": "no_result", "exception": repr(exception)[:500]}
    if process.is_alive():
        process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join(5)
        if received is None:
            received = {"status": "timeout", "exception": "execution_timeout"}
    else:
        process.join(5)
    if received is None:
        if process.exitcode not in (0, None):
            received = {"status": "crashed", "exception": "worker_exit_code:" + str(process.exitcode)}
        else:
            received = {"status": "no_result", "exception": "worker_returned_nothing"}
    try:
        sender.close()
    except Exception:
        pass
    try:
        receiver.close()
    except Exception:
        pass
    return received


def _candidate_from_mapping(
    item: Mapping[str, Any],
    specification: ProblemSpec,
    generated: GeneratedCodeResult,
    frontier: Frontier,
    provenance: Mapping[str, Any] | None = None,
) -> tuple[Candidate | None, tuple[str, ...]]:
    issues: list[str] = []
    if provenance is not None:
        if str(provenance.get("problem_kind", "")) != specification.kind.value:
            issues.append("provenance_problem_kind_mismatch")
        if str(provenance.get("frontier_signature", "")) != frontier.unique_signature:
            issues.append("provenance_frontier_signature_mismatch")
        if str(provenance.get("source_fingerprint", "")) != generated.source_fingerprint:
            issues.append("provenance_source_fingerprint_mismatch")
    if issues:
        return None, tuple(issues)
    raw_points = dict(item.get("points") or {})
    points = {str(key): tuple(str(coordinate) for coordinate in value) for key, value in raw_points.items()}
    candidate = Candidate(
        problem_kind=specification.kind,
        formulas={str(key): str(value) for key, value in dict(item.get("formulas") or {}).items()},
        points=points,
        assignments=dict(item.get("assignments") or {}),
        finite_structures=dict(item.get("finite_structures") or {}),
        exact_derivation_artifacts=dict(item.get("exact_derivation_artifacts") or {}),
        source_fingerprint=generated.source_fingerprint,
        frontier_signature=frontier.unique_signature,
    )
    return candidate, ()


def execute_generated_code(
    generated: GeneratedCodeResult,
    specification: ProblemSpec,
    frontier: Frontier,
    limits: SearchBudget | None = None,
) -> FrontierResult:
    budget = limits if limits is not None else SearchBudget()
    validation_issues = validate_generated_source(generated.source, generated.entry_function)
    validation_issues = tuple(dict.fromkeys(tuple(generated.generation_issues) + tuple(validation_issues)))
    if validation_issues:
        return FrontierResult(
            frontier=frontier,
            generated_result=generated,
            candidates=(),
            failure_reasons=tuple(validation_issues),
            exception_text="",
            internal_artifacts={"validation": True},
        )
    outcome = _run_isolated(generated.source, generated.entry_function, generated.source_fingerprint, budget.execution_timeout_seconds)
    status = str(outcome.get("status", "no_result"))
    if status != "ok":
        return FrontierResult(
            frontier=frontier,
            generated_result=generated,
            candidates=(),
            failure_reasons=("generated_execution_" + status,),
            exception_text=str(outcome.get("exception", ""))[:500],
            internal_artifacts={"execution_status": status},
        )
    raw_result = outcome.get("payload")
    if not isinstance(raw_result, Mapping):
        return FrontierResult(frontier=frontier, generated_result=generated, failure_reasons=("invalid_generated_result",), internal_artifacts={"execution_status": status})
    failures: list[str] = []
    candidates: list[Candidate] = []
    artifacts: dict[str, Any] = {}
    for failure in raw_result.get("failures") or ():
        failures.append(str(failure))
    for key, value in dict(raw_result.get("artifacts") or {}).items():
        artifacts[str(key)] = value
    provenance = raw_result.get("provenance")
    for raw_candidate in raw_result.get("candidates") or ():
        if isinstance(raw_candidate, Mapping):
            try:
                candidate, issues = _candidate_from_mapping(raw_candidate, specification, generated, frontier, provenance if isinstance(provenance, Mapping) else None)
            except Exception as exception:
                failures.append(type(exception).__name__)
                continue
            if candidate is None:
                failures.extend(issues)
                continue
            candidates.append(candidate)
        else:
            failures.append("invalid_candidate_shape")
    if not candidates and not failures:
        failures.append("empty_result")
    return FrontierResult(
        frontier=frontier,
        generated_result=generated,
        candidates=tuple(candidates),
        failure_reasons=tuple(dict.fromkeys(failures)),
        internal_artifacts=artifacts,
    )
