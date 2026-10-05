from __future__ import annotations

import re
from typing import Any

from .models import Candidate, CritiqueIssue, CritiqueResult, Frontier, GeneratedCodeResult, ProblemKind, ProblemSpec, VerificationResult
from .verification import verify_candidate


def _issue(code: str, description: str, repair_hint: str) -> CritiqueIssue:
    return CritiqueIssue(code=code, description=description, severity="blocking", resolved=False, repair_hint=repair_hint)


def _contains_decimal_text(value: Any) -> bool:
    if isinstance(value, str):
        return re.search(r"(?<![A-Za-z_])\d+\.\d+", value) is not None
    if isinstance(value, dict):
        return any(_contains_decimal_text(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return any(_contains_decimal_text(item) for item in value)
    return False


def critique_candidate(
    specification: ProblemSpec,
    candidate: Candidate,
    verification: VerificationResult,
    generated: GeneratedCodeResult | None = None,
    frontier: Frontier | None = None,
) -> CritiqueResult:
    issues: list[CritiqueIssue] = []
    if not verification.passed:
        issues.append(_issue("verification_failed", "verification did not certify the candidate", "rerun with strengthened exact checks"))
    if candidate.problem_kind != specification.kind:
        issues.append(_issue("problem_kind_mismatch", "candidate kind does not match formalized target", "discard candidate and regenerate for the current target"))
    if frontier is not None and candidate.frontier_signature != frontier.unique_signature:
        issues.append(_issue("frontier_provenance_mismatch", "candidate frontier signature does not match current frontier", "rerun generated source from the current frontier"))
    if generated is not None:
        if candidate.source_fingerprint != generated.source_fingerprint:
            issues.append(_issue("source_fingerprint_mismatch", "candidate source fingerprint does not match generated source", "discard candidate and re-execute generated source"))
        if generated.generation_issues:
            issues.append(_issue("generation_issue_present", "code generation reported internal issues", "repair code generation parameters"))
        if "TODO" in generated.source or "NotImplementedError" in generated.source or '"""' in generated.source or "'''" in generated.source:
            issues.append(_issue("generated_source_marker", "generated source contains a forbidden marker", "regenerate source without forbidden markers"))
    if _contains_decimal_text(candidate.formulas) or _contains_decimal_text(candidate.points) or _contains_decimal_text(candidate.assignments):
        issues.append(_issue("decimal_text_present", "candidate contains decimal text", "regenerate with exact rational or algebraic values"))
    artifacts = dict(verification.artifacts)
    if artifacts.get("no_numeric_certification") is not True:
        issues.append(_issue("numeric_certification_gap", "verification did not rule out numeric-only certification", "strengthen exact-domain verification"))
    if artifacts.get("denominator_status") is not True:
        issues.append(_issue("denominator_gap", "denominator obligations were not completely discharged", "add denominator nonzero obligations"))
    repeat = verify_candidate(specification, candidate)
    if not repeat.passed:
        issues.append(_issue("repeat_verification_failed", "independent rerun of verifier rejected candidate", "discard candidate and mutate frontier"))
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        if specification.planar_target is None:
            issues.append(_issue("target_missing", "planar target data is absent", "repair formalization"))
        if artifacts.get("independent_determinant_check") is not True:
            issues.append(_issue("single_determinant_path", "determinant was not certified by independent paths", "add monomial-coefficient determinant check"))
        if artifacts.get("independent_collision_check") is not True:
            issues.append(_issue("single_collision_path", "collision was not certified by independent paths", "add coefficient-dictionary evaluation check"))
        if artifacts.get("distinct_points") is not True:
            issues.append(_issue("distinctness_gap", "point distinctness was not proved exactly", "change point pattern or exact comparison"))
        if artifacts.get("determinant_nonzero") is not True or artifacts.get("nonconstant_coefficients_zero") is not True:
            issues.append(_issue("determinant_obligation_gap", "constant determinant obligations are incomplete", "repair determinant constraint route"))
        if artifacts.get("collision_differences_zero") is not True:
            issues.append(_issue("collision_obligation_gap", "collision obligations are incomplete", "repair collision equations"))
    elif specification.kind == ProblemKind.ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT:
        if artifacts.get("exact_inequality_check") is not True:
            issues.append(_issue("identity_inequality_gap", "identity inequality was not proved exactly", "change assignment search domain"))
    elif specification.kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
        if artifacts.get("group_table_valid") is not True:
            issues.append(_issue("group_table_gap", "finite table was not certified as a group", "repair finite structure search"))
        if artifacts.get("word_inequality") is not True:
            issues.append(_issue("word_inequality_gap", "word inequality was not certified", "mutate group assignments or table family"))
    unresolved = tuple(item for item in issues if not item.resolved)
    return CritiqueResult(passed=not unresolved, issues=tuple(issues), artifacts={"repeat_verification_passed": repeat.passed})
