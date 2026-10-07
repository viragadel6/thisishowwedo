from __future__ import annotations

import pytest

import json
import subprocess
import sys

from exact_formula_search import run
from exact_formula_search.code_generation import generate_search_code, validate_generated_source
from exact_formula_search.critique import critique_candidate
from exact_formula_search.execution import execute_generated_code
from exact_formula_search.formalization import describe_formalization, formalize_request
from exact_formula_search.frontiers import initial_frontiers, mutate_frontier
from exact_formula_search.models import Candidate, ExactDomain, FormalizationError, ProblemKind, SearchBudget
from exact_formula_search.orchestrator import run as orchestrator_run
from exact_formula_search.repair import build_repair_request, repair_frontiers
from exact_formula_search.symbolic_tools import (
    finite_field_add,
    finite_field_element_text,
    finite_field_elements,
    finite_field_inverse,
    finite_field_is_zero,
    finite_field_multiply,
    finite_field_reduce,
    irreducible_modulus_polynomial,
)
from exact_formula_search.verification import verify_candidate
from exact_formula_search.web.exports import sympy_reproduction_script
from exact_formula_search.web.presets import PRESETS

FAST = SearchBudget(max_seconds=20.0, execution_timeout_seconds=15.0)


@pytest.mark.parametrize(
    "request_text,expected_kind",
    [
        ("find a counterexample for x^2 + 1 = x^2", ProblemKind.ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT),
        ("In every finite group, x^2 = e", ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL),
        ("refute the two dimensional Jacobian conjecture", ProblemKind.FINITE_FIELD_JACOBIAN_REFUTATION),
        ("cáfold meg a 2D Jacobi-sejtést", ProblemKind.FINITE_FIELD_JACOBIAN_REFUTATION),
        (
            "refute the two dimensional Jacobian conjecture over the rationals",
            ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION,
        ),
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


def test_planar_request_in_characteristic_zero_reports_open_status() -> None:
    report = orchestrator_run("refute the two dimensional Jacobian conjecture over the rationals", FAST)
    assert "no counterexample found within the search budget" in report
    assert "remains open" in report


def test_finite_field_helper_arithmetic_is_exact() -> None:
    modulus = irreducible_modulus_polynomial(2, 2)
    generator = (0, 1)
    assert finite_field_element_text(finite_field_multiply(generator, generator, 2, modulus), 2) == "a + 1"
    assert finite_field_is_zero(finite_field_add(finite_field_multiply(generator, generator, 2, modulus), (1, 1), 2), 2)
    assert finite_field_element_text(finite_field_inverse(generator, 2, modulus), 2) == "a + 1"
    nine = irreducible_modulus_polynomial(3, 2)
    identity = finite_field_reduce((1,), 3, nine)
    for element in finite_field_elements(3, 2):
        if finite_field_is_zero(element, 3):
            continue
        assert finite_field_multiply(element, finite_field_inverse(element, 3, nine), 3, nine) == identity
    assert irreducible_modulus_polynomial(11, 2) == (1, 0)
    assert irreducible_modulus_polynomial(2, 8) == (1, 1, 0, 1, 1, 0, 0, 0)


def test_finite_field_jacobian_lanes_use_the_extension_domain() -> None:
    specification = formalize_request("cáfold meg a 2D Jacobi-sejtést")
    frontiers = initial_frontiers(specification)
    assert frontiers
    ladder = [(frontier.extra_parameters["prime"], frontier.extra_parameters["extension_degree"]) for frontier in frontiers]
    assert ladder[0] == (2, 1)
    assert len(set(ladder)) == len(ladder)
    for frontier in frontiers:
        assert frontier.exact_domain == ExactDomain.FINITE_FIELD_EXTENSION
        assert frontier.kind.value == "finite_field_jacobian_lattice"
    for frontier in mutate_frontier(frontiers[0], set(), 6, "test", specification.kind):
        assert frontier.exact_domain == ExactDomain.FINITE_FIELD_EXTENSION
        assert frontier.extra_parameters["extension_degree"] >= 1


def _finite_field_execution():
    specification = formalize_request("cáfold meg a 2D Jacobi-sejtést")
    frontier = initial_frontiers(specification)[0]
    generated = generate_search_code(specification, frontier, FAST)
    result = execute_generated_code(generated, specification, frontier, FAST)
    assert result.candidates
    return specification, frontier, generated, result.candidates[0]


def test_finite_field_jacobian_refutation_is_certified() -> None:
    specification, frontier, generated, candidate = _finite_field_execution()
    verification = verify_candidate(specification, candidate)
    assert verification.passed, verification.issues
    assert verification.artifacts["field_characteristic"] == 2
    assert verification.artifacts["field_order"] == 2
    assert verification.artifacts["determinant_nonzero"] is True
    assert verification.artifacts["nonconstant_coefficients_vanish_mod_characteristic"] is True
    assert verification.artifacts["independent_determinant_check"] is True
    assert verification.artifacts["collision_differences_zero"] is True
    assert verification.artifacts["independent_collision_check"] is True
    assert verification.artifacts["distinct_points"] is True
    assert verification.artifacts["not_injective_on_finite_field"] is True
    assert verification.artifacts["characteristic_zero_status"] == "open"
    critique = critique_candidate(specification, candidate, verification, generated, frontier)
    assert critique.passed, [issue.code for issue in critique.issues]
    assert critique.artifacts["independent_recheck_passed"] is True


def test_finite_field_jacobian_refutation_reaches_the_entry_points() -> None:
    report = orchestrator_run("cáfold meg a 2D Jacobi-sejtést", FAST)
    assert "field: GF(2)" in report
    assert "det J = 1 (mod 2)" in report
    assert "F(P) = (1, 1) = F(Q)" in report
    assert "characteristic 0 remains open" in report
    assert run("cáfold meg a 2D Jacobi-sejtést", FAST) == report


def test_finite_field_verifier_rejects_broken_witnesses() -> None:
    specification, frontier, generated, candidate = _finite_field_execution()
    identical_points = Candidate(
        problem_kind=candidate.problem_kind,
        formulas=dict(candidate.formulas),
        points={"P": candidate.points["P"], "Q": candidate.points["P"]},
        exact_derivation_artifacts=dict(candidate.exact_derivation_artifacts),
        source_fingerprint=candidate.source_fingerprint,
        frontier_signature=candidate.frontier_signature,
    )
    assert not verify_candidate(specification, identical_points).passed
    changed_modulus = Candidate(
        problem_kind=candidate.problem_kind,
        formulas=dict(candidate.formulas),
        points=dict(candidate.points),
        exact_derivation_artifacts={**dict(candidate.exact_derivation_artifacts), "field_modulus": [0]},
        source_fingerprint=candidate.source_fingerprint,
        frontier_signature=candidate.frontier_signature,
    )
    assert not verify_candidate(specification, changed_modulus).passed
    broken_map = Candidate(
        problem_kind=candidate.problem_kind,
        formulas={"F1": candidate.formulas["F1"], "F2": str(candidate.formulas["F2"]) + " + 1"},
        points=dict(candidate.points),
        exact_derivation_artifacts=dict(candidate.exact_derivation_artifacts),
        source_fingerprint=candidate.source_fingerprint,
        frontier_signature=candidate.frontier_signature,
    )
    assert not verify_candidate(specification, broken_map).passed
    tampered_image = Candidate(
        problem_kind=candidate.problem_kind,
        formulas=dict(candidate.formulas),
        points=dict(candidate.points),
        exact_derivation_artifacts={**dict(candidate.exact_derivation_artifacts), "image_at_point": ["0", "0"]},
        source_fingerprint=candidate.source_fingerprint,
        frontier_signature=candidate.frontier_signature,
    )
    verification = verify_candidate(specification, tampered_image)
    assert not verification.passed
    critique = critique_candidate(specification, tampered_image, verification, generated, frontier)
    assert not critique.passed
    assert critique.artifacts["independent_recheck_passed"] is False


def test_exported_reproduction_script_verifies_the_refutation(tmp_path) -> None:
    certificate = {
        "kind": "counterexample",
        "problem_kind": "finite_field_jacobian_refutation",
        "query": "cáfold meg a 2D Jacobi-sejtést",
        "finite_field": {
            "field_label": "GF(3^2)",
            "field_characteristic": 3,
            "field_extension_degree": 2,
            "field_modulus": list(irreducible_modulus_polynomial(3, 2)),
            "point_p": ["0", "1"],
            "point_q": ["1", "0"],
            "component_rows": [{"expression": "x + y**3"}, {"expression": "x**3 + y"}],
            "jacobian_determinant": "1 - 9*x**2*y**2",
            "determinant_constant_mod_characteristic": 1,
        },
    }
    script = tmp_path / "reproduce.py"
    script.write_text(sympy_reproduction_script(certificate), encoding="utf-8")
    completed = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert "finite field Jacobian refutation verified with exact arithmetic" in completed.stdout
    tampered = json.loads(json.dumps(certificate))
    tampered["finite_field"]["point_q"] = list(tampered["finite_field"]["point_p"])
    broken = tmp_path / "tampered.py"
    broken.write_text(sympy_reproduction_script(tampered), encoding="utf-8")
    rejected = subprocess.run([sys.executable, str(broken)], capture_output=True, text=True)
    assert rejected.returncode != 0
    assert "not distinct" in rejected.stderr


def test_presets_match_their_declared_problem_kinds() -> None:
    for preset in PRESETS:
        specification = formalize_request(str(preset["query"]))
        assert specification.kind.value == str(preset["problem_kind"])


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
