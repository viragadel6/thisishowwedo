from __future__ import annotations

import pytest

from exact_formula_search import run
from exact_formula_search.code_generation import generate_search_code, validate_generated_source
from exact_formula_search.execution import execute_generated_code
from exact_formula_search.formalization import describe_formalization, formalize_request
from exact_formula_search.frontiers import initial_frontiers, mutate_frontier
from exact_formula_search.models import FormalizationError, ProblemKind, SearchBudget
from exact_formula_search.orchestrator import run as orchestrator_run
from exact_formula_search.repair import build_repair_request, repair_frontiers
from exact_formula_search.verification import verify_candidate

FAST = SearchBudget(max_seconds=20.0, execution_timeout_seconds=15.0)


@pytest.mark.parametrize(
    "request_text,expected_kind",
    [
        ("find a counterexample for x^2 + 1 = x^2", ProblemKind.ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT),
        ("In every finite group, x^2 = e", ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL),
        ("refute the two dimensional Jacobian conjecture", ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION),
    ],
)
def test_formalization_kinds(request_text: str, expected_kind: ProblemKind) -> None:
    assert formalize_request(request_text).kind == expected_kind


@pytest.mark.parametrize(
    "request_text",
    [
        "",
        "=",
        "x =",
        "no equality here at all",
    ],
)
def test_malformed_requests_raise(request_text: str) -> None:
    with pytest.raises(FormalizationError):
        formalize_request(request_text)


@pytest.mark.parametrize(
    "request_text,expected_lines",
    [
        ("find a counterexample for x^2 + 1 = x^2", "x = 0"),
        ("refute the identity x + 1 = x", "x = 0"),
        ("is x/(x-1) = 1 false?", "x = 0"),
        ("refute the identity alpha + x = x", "alpha = -1"),
    ],
)
def test_algebraic_counterassignments(request_text: str, expected_lines: str) -> None:
    report = orchestrator_run(request_text, FAST)
    assert expected_lines in report


def test_symbolically_true_identity_has_no_counterassignment() -> None:
    report = orchestrator_run("prove that sin(x)^2 + cos(x)^2 = 1 for every real x", FAST)
    assert "no counterassignment exists" in report
    assert "identity_holds_symbolically" in report


def test_group_countermodel_is_a_group_table() -> None:
    report = orchestrator_run("In every finite group, x^2 = e", FAST)
    assert "* = [" in report
    assert "x = 1" in report


def test_group_order_bound_is_respected() -> None:
    specification = formalize_request("find a countermodel for x^2 = e in every group of order at most 4")
    for frontier in initial_frontiers(specification):
        assert frontier.extra_parameters["group_order"] <= 4


def test_planar_request_reports_open_status() -> None:
    report = orchestrator_run("refute the two dimensional Jacobian conjecture", FAST)
    assert "no counterexample found within the search budget" in report
    assert "remains open" in report


def test_constraints_are_enforced() -> None:
    report = orchestrator_run("for all positive integers n, n^2 + 1 = n", FAST)
    assert "n = 1" in report
    report = orchestrator_run("for all nonnegative integers n, n + 1 = n", FAST)
    assert "n = 0" in report


def test_quoted_sides_are_formalized() -> None:
    specification = formalize_request('refute the identity "x + 1 = x"')
    payload = describe_formalization(specification)
    assert payload["left"] == "x + 1"
    assert payload["right"] == "x"


def test_domain_obligations_are_recorded() -> None:
    specification = formalize_request("refute the identity 1/(x-1) + 1/(x+1) = 1")
    target = specification.algebraic_identity
    assert target is not None
    assert "x - 1" in target.left_obligations
    assert "x + 1" in target.left_obligations


def test_generated_source_is_structurally_valid() -> None:
    specification = formalize_request("find a counterexample for x^2 + 1 = x^2")
    frontier = initial_frontiers(specification)[0]
    generated = generate_search_code(specification, frontier, FAST)
    assert validate_generated_source(generated.source, generated.entry_function) == ()
    assert generated.generation_issues == ()


def test_hostile_generated_source_is_rejected() -> None:
    assert validate_generated_source("import os\n", "search") != ()
    assert validate_generated_source("from exact_formula_search.generated_runtime import run_generated_search\nprint(run_generated_search)\n", "search") != ()
    assert validate_generated_source("def search(:\n    pass\n", "search") == ("unparsable_generated_source",)


def test_executed_frontier_reports_verified_candidate() -> None:
    specification = formalize_request("find a counterexample for x^2 + 1 = x^2")
    frontier = initial_frontiers(specification)[0]
    generated = generate_search_code(specification, frontier, FAST)
    result = execute_generated_code(generated, specification, frontier, FAST)
    assert result.candidates
    assert result.failure_reasons == ()
    for candidate in result.candidates:
        assert verify_candidate(specification, candidate).passed


def test_provenance_mismatch_is_rejected() -> None:
    specification = formalize_request("find a counterexample for x^2 + 1 = x^2")
    frontier = initial_frontiers(specification)[0]
    other = initial_frontiers(specification)[-1]
    generated = generate_search_code(specification, frontier, FAST)
    result = execute_generated_code(generated, specification, other, FAST)
    assert result.candidates == ()
    assert "provenance_frontier_signature_mismatch" in result.failure_reasons


def test_mutations_respect_problem_kind() -> None:
    specification = formalize_request("In every finite group, x^2 = e")
    base = initial_frontiers(specification)[0]
    for frontier in mutate_frontier(base, set(), 6, "test", specification.kind):
        assert frontier.exact_domain.value == "finite_table"
        assert frontier.kind.value == "finite_structure"
    specification = formalize_request("find a counterexample for x^2 + 1 = x^2")
    base = initial_frontiers(specification)[0]
    for frontier in mutate_frontier(base, set(), 6, "test", specification.kind):
        assert frontier.exact_domain.value in ("rational", "algebraic")


def test_repair_actions_map_to_mutations() -> None:
    specification = formalize_request("find a counterexample for x^2 + 1 = x^2")
    base = initial_frontiers(specification)[0]
    request = build_repair_request("no_candidate_returned", base)
    produced = repair_frontiers(specification, request, set(), 4, FAST)
    assert produced
    for frontier in produced:
        assert frontier.extra_parameters["repair_action"]


def test_frontier_records_are_immutable_and_hashable() -> None:
    specification = formalize_request("refute the two dimensional Jacobian conjecture")
    frontier = initial_frontiers(specification)[0]
    assert hash(frontier) is not None
    assert hash(frontier.unique_signature) is not None
    with pytest.raises(Exception):
        frontier.degree_extent = 9


def test_module_entry_point_matches_library() -> None:
    assert callable(run)
    assert run("find a counterexample for x^2 + 1 = x^2", FAST) == "x = 0"
