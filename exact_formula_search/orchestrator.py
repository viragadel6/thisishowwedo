from __future__ import annotations

import math
import operator
import time
from collections import deque
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from .code_generation import generate_search_code
from .critique import critique_candidate
from .execution import execute_generated_code
from .formalization import formalize_request
from .frontiers import initial_frontiers, mutate_frontier
from .models import Frontier, ProblemKind, SearchBudget, VerificationResult
from .output_format import format_candidate
from .repair import build_repair_request, repair_frontiers
from .symbolic_tools import exact_parse_expression, exact_zero
from .verification import verify_candidate

_FRONTIER_BATCH_SIZE = 5
_EXCEPTION_TEXT_LIMIT = 500
_Result = TypeVar("_Result")


class _SearchBudgetExhausted(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(name + " must be a nonnegative integer")
    try:
        result = operator.index(value)
    except TypeError as exception:
        raise TypeError(
            name + " must be a nonnegative integer"
        ) from exception
    if result < 0:
        raise ValueError(name + " must be a nonnegative integer")
    return result


def _nonnegative_seconds(value: Any) -> float:
    message = "max_seconds must be a finite, nonnegative real number"
    if isinstance(value, (bool, str, bytes, bytearray)):
        raise TypeError(message)
    try:
        result = float(value)
    except TypeError as exception:
        raise TypeError(message) from exception
    except (ValueError, OverflowError) as exception:
        raise ValueError(message) from exception
    if not math.isfinite(result) or result < 0:
        raise ValueError(message)
    return result


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise _SearchBudgetExhausted("search_budget_exhausted")


def _exception_text(exception: Exception) -> str:
    try:
        return repr(exception)[:_EXCEPTION_TEXT_LIMIT]
    except Exception:
        return type(exception).__name__[:_EXCEPTION_TEXT_LIMIT]


def _generation_issue_text(
    issues: Any,
    deadline: float | None = None,
) -> str | None:
    _check_deadline(deadline)
    if issues is None:
        return None
    if isinstance(issues, str):
        return issues[:_EXCEPTION_TEXT_LIMIT] if issues else None

    parts: list[str] = []
    remaining = _EXCEPTION_TEXT_LIMIT
    found_issue = False

    for issue in issues:
        _check_deadline(deadline)
        issue_text = issue if isinstance(issue, str) else str(issue)
        if found_issue:
            parts.append(";")
            remaining -= 1
        found_issue = True
        fragment = issue_text[:remaining]
        parts.append(fragment)
        remaining -= len(fragment)
        if remaining <= 0:
            break

    _check_deadline(deadline)
    return "".join(parts) if found_issue else None


def _symbolic_proof_report(
    specification: Any,
    deadline: float | None = None,
) -> str:
    _check_deadline(deadline)
    if specification.kind != ProblemKind.ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT:
        return ""

    target = specification.algebraic_identity
    if target is None:
        return ""

    try:
        left_expression = target.left_expression
        right_expression = target.right_expression
        variables = target.variables

        _check_deadline(deadline)
        left = exact_parse_expression(left_expression, variables)
        _check_deadline(deadline)
        right = exact_parse_expression(right_expression, variables)
        _check_deadline(deadline)
        difference = left - right
        _check_deadline(deadline)
        identity_holds = exact_zero(difference)
        _check_deadline(deadline)

        if not identity_holds:
            return ""

        report = "\n".join(
            (
                "no counterassignment exists",
                "kind: " + specification.kind.value,
                "left: " + str(left_expression),
                "right: " + str(right_expression),
                "reason: identity_holds_symbolically",
            )
        )
        _check_deadline(deadline)
        return report
    except _SearchBudgetExhausted:
        raise
    except Exception:
        _check_deadline(deadline)
        return ""


def _exhausted_report(
    specification: Any,
    statistics: dict[str, int],
    reason: str,
    *,
    last_recovery_error: str = "",
) -> str:
    lines = [
        "no counterexample found within the search budget",
        "kind: " + specification.kind.value,
        "frontiers_examined: " + str(statistics.get("frontiers_examined", 0)),
        "candidates_verified: " + str(statistics.get("candidates_verified", 0)),
        "mutation_rounds: " + str(statistics.get("mutation_rounds", 0)),
        "reason: " + reason,
    ]
    if last_recovery_error:
        lines.append("last_recovery_error: " + last_recovery_error)
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        lines.append(
            "note: the two dimensional case of the Jacobian conjecture remains open"
        )
    return "\n".join(lines)


def run(raw_text: str, budget: SearchBudget | None = None) -> str:
    if not isinstance(raw_text, str):
        raise TypeError("raw_text must be a string")

    started_at = time.monotonic()
    limits = budget if budget is not None else SearchBudget()

    max_seconds = _nonnegative_seconds(limits.max_seconds)
    max_frontier_visits = _nonnegative_integer(
        limits.max_frontier_visits,
        "max_frontier_visits",
    )
    max_verified_candidates = _nonnegative_integer(
        limits.max_verified_candidates,
        "max_verified_candidates",
    )
    max_mutation_rounds = _nonnegative_integer(
        limits.max_mutation_rounds,
        "max_mutation_rounds",
    )
    max_candidates_per_frontier = _nonnegative_integer(
        limits.max_candidates_per_frontier,
        "max_candidates_per_frontier",
    )

    deadline = started_at + max_seconds
    specification = formalize_request(raw_text)

    active: deque[Frontier] = deque()
    known_signatures: set[str] = set()
    last_frontier: Frontier | None = None
    last_recovery_error = ""

    statistics = {
        "frontiers_examined": 0,
        "candidates_verified": 0,
        "mutation_rounds": 0,
    }
    counter_limits = {
        "candidates_verified": (
            max_verified_candidates,
            "candidate_budget_exhausted",
        ),
        "mutation_rounds": (
            max_mutation_rounds,
            "mutation_budget_exhausted",
        ),
    }

    def exhausted(reason: str) -> str:
        return _exhausted_report(
            specification,
            statistics,
            reason,
            last_recovery_error=last_recovery_error,
        )

    def checked_call(
        function: Callable[..., _Result],
        *args: Any,
        counter: str | None = None,
        **kwargs: Any,
    ) -> _Result:
        _check_deadline(deadline)
        if counter is not None:
            limit, reason = counter_limits[counter]
            if statistics[counter] >= limit:
                raise _SearchBudgetExhausted(reason)
            statistics[counter] += 1
        try:
            result = function(*args, **kwargs)
        except _SearchBudgetExhausted:
            raise
        except Exception:
            _check_deadline(deadline)
            raise
        _check_deadline(deadline)
        return result

    def check_new_frontier_budget() -> None:
        _check_deadline(deadline)
        if statistics["frontiers_examined"] >= max_frontier_visits:
            raise _SearchBudgetExhausted("search_budget_exhausted")
        if (
            statistics["candidates_verified"] >= max_verified_candidates
            or max_candidates_per_frontier == 0
        ):
            raise _SearchBudgetExhausted("candidate_budget_exhausted")

    def expansion_available() -> bool:
        _check_deadline(deadline)
        return (
            max_candidates_per_frontier > 0
            and statistics["candidates_verified"] < max_verified_candidates
            and statistics["mutation_rounds"] < max_mutation_rounds
            and statistics["frontiers_examined"] < max_frontier_visits
        )

    def add_frontiers(frontiers: Iterable[Frontier]) -> None:
        _check_deadline(deadline)
        iterator = iter(frontiers)

        while (
            statistics["frontiers_examined"] < max_frontier_visits
            and len(active) < max(max_frontier_visits, _FRONTIER_BATCH_SIZE)
        ):
            _check_deadline(deadline)
            try:
                frontier = next(iterator)
            except StopIteration:
                break
            _check_deadline(deadline)

            signature = frontier.unique_signature
            if not isinstance(signature, str):
                raise TypeError("Frontier.unique_signature must be a string")
            if signature not in known_signatures:
                known_signatures.add(signature)
                active.append(frontier)

        _check_deadline(deadline)

    def request_repair(
        stage: str,
        frontier: Frontier,
        **details: Any,
    ) -> None:
        nonlocal last_recovery_error

        if not expansion_available():
            return

        try:
            request = checked_call(
                build_repair_request,
                stage,
                frontier,
                **details,
            )
            if not expansion_available():
                return

            repaired = checked_call(
                repair_frontiers,
                specification,
                request,
                known_signatures.copy(),
                _FRONTIER_BATCH_SIZE,
                limits,
            )
            add_frontiers(repaired)
        except _SearchBudgetExhausted:
            raise
        except Exception as exception:
            last_recovery_error = (
                "repair_exception at "
                + stage
                + ": "
                + _exception_text(exception)
            )

    def attempt_mutation(
        frontier: Frontier | None,
        reason: str,
    ) -> bool | None:
        nonlocal last_recovery_error

        if not expansion_available():
            return None

        try:
            mutated = checked_call(
                mutate_frontier,
                frontier,
                known_signatures.copy(),
                _FRONTIER_BATCH_SIZE,
                reason,
                specification.kind,
                counter="mutation_rounds",
            )
            add_frontiers(mutated)
            return True
        except _SearchBudgetExhausted:
            raise
        except Exception as exception:
            last_recovery_error = (
                "frontier_mutation_exception at "
                + reason
                + ": "
                + _exception_text(exception)
            )
            return False

    try:
        proof = checked_call(
            _symbolic_proof_report,
            specification,
            deadline,
        )
        if proof:
            return proof

        check_new_frontier_budget()

        try:
            add_frontiers(
                checked_call(initial_frontiers, specification)
            )
        except _SearchBudgetExhausted:
            raise
        except Exception as exception:
            last_recovery_error = (
                "initial_frontiers_exception: "
                + _exception_text(exception)
            )

        while True:
            check_new_frontier_budget()

            if not active:
                mutation_completed = attempt_mutation(
                    last_frontier,
                    "active_queue_empty",
                )
                root_mutation_completed = None

                if not active:
                    root_mutation_completed = attempt_mutation(
                        None,
                        "active_queue_empty_root",
                    )

                check_new_frontier_budget()

                if not active:
                    if statistics["mutation_rounds"] >= max_mutation_rounds:
                        raise _SearchBudgetExhausted(
                            "mutation_budget_exhausted"
                        )
                    if (
                        mutation_completed is False
                        or root_mutation_completed is False
                    ):
                        return exhausted("frontier_mutation_exception")
                    return exhausted("frontier_space_exhausted")

            frontier = active.popleft()
            last_frontier = frontier
            statistics["frontiers_examined"] += 1

            try:
                generated = checked_call(
                    generate_search_code,
                    specification,
                    frontier,
                    limits,
                )
                generation_error_text = _generation_issue_text(
                    generated.generation_issues,
                    deadline,
                )
            except _SearchBudgetExhausted:
                raise
            except Exception as exception:
                request_repair(
                    "code_generation_exception",
                    frontier,
                    exception_text=_exception_text(exception),
                )
                continue

            if generation_error_text is not None:
                request_repair(
                    "code_generation_exception",
                    frontier,
                    exception_text=generation_error_text,
                )
                continue

            execution_result = None
            try:
                execution_result = checked_call(
                    execute_generated_code,
                    generated,
                    specification,
                    frontier,
                    limits,
                )
                candidate_iterator = iter(execution_result.candidates)
                execution_exception_text = execution_result.exception_text
            except _SearchBudgetExhausted:
                raise
            except Exception as exception:
                request_repair(
                    "execution_or_empty_frontier",
                    frontier,
                    execution_result=execution_result,
                    exception_text=_exception_text(exception),
                )
                continue

            _check_deadline(deadline)
            candidates_seen = 0
            iterator_failed = False

            for _ in range(max_candidates_per_frontier):
                _check_deadline(deadline)
                if (
                    statistics["candidates_verified"]
                    >= max_verified_candidates
                ):
                    raise _SearchBudgetExhausted(
                        "candidate_budget_exhausted"
                    )

                try:
                    candidate = checked_call(next, candidate_iterator)
                except StopIteration:
                    break
                except _SearchBudgetExhausted:
                    raise
                except Exception as exception:
                    iterator_failed = True
                    request_repair(
                        "execution_or_empty_frontier",
                        frontier,
                        execution_result=execution_result,
                        exception_text=_exception_text(exception),
                    )
                    break

                candidates_seen += 1

                try:
                    verification = checked_call(
                        verify_candidate,
                        specification,
                        candidate,
                        counter="candidates_verified",
                    )
                    verification_passed = bool(verification.passed)
                except _SearchBudgetExhausted:
                    raise
                except Exception as exception:
                    verification = VerificationResult(
                        False,
                        candidate,
                        (type(exception).__name__,),
                        {"exception": _exception_text(exception)},
                    )
                    verification_passed = False

                _check_deadline(deadline)

                if not verification_passed:
                    request_repair(
                        "verification_rejection",
                        frontier,
                        verification_result=verification,
                        execution_result=execution_result,
                    )
                    continue

                try:
                    critique = checked_call(
                        critique_candidate,
                        specification,
                        candidate,
                        verification,
                        generated,
                        frontier,
                    )
                    critique_passed = bool(critique.passed)
                except _SearchBudgetExhausted:
                    raise
                except Exception as exception:
                    request_repair(
                        "critique_exception",
                        frontier,
                        verification_result=verification,
                        execution_result=execution_result,
                        exception_text=_exception_text(exception),
                    )
                    continue

                _check_deadline(deadline)

                if not critique_passed:
                    request_repair(
                        "critique_rejection",
                        frontier,
                        verification_result=verification,
                        critique_result=critique,
                        execution_result=execution_result,
                    )
                    continue

                try:
                    output = checked_call(
                        format_candidate,
                        specification,
                        candidate,
                    )
                    if not isinstance(output, str):
                        raise TypeError(
                            "format_candidate must return a string"
                        )
                    if not output.strip():
                        raise ValueError(
                            "format_candidate returned empty or "
                            "whitespace-only output"
                        )
                except _SearchBudgetExhausted:
                    raise
                except Exception as exception:
                    request_repair(
                        "format_exception",
                        frontier,
                        verification_result=verification,
                        critique_result=critique,
                        execution_result=execution_result,
                        exception_text=_exception_text(exception),
                    )
                    continue

                _check_deadline(deadline)
                return output

            if candidates_seen == 0 and not iterator_failed:
                request_repair(
                    "no_candidate_returned",
                    frontier,
                    execution_result=execution_result,
                    exception_text=execution_exception_text,
                )

    except _SearchBudgetExhausted as exception:
        return exhausted(exception.reason)
