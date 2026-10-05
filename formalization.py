from __future__ import annotations

import re
import unicodedata
from typing import Any

from .models import (
    AlgebraicIdentityTarget,
    ExactDomain,
    FiniteGroupIdentityTarget,
    PlanarMapTarget,
    ProblemKind,
    ProblemSpec,
)
from .symbolic_tools import canonicalize_formula, exact_parse_expression


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(character for character in decomposed if unicodedata.category(character) != "Mn")


def _normalized_tokens(raw_text: str) -> tuple[str, ...]:
    folded = _strip_accents(unicodedata.normalize("NFKC", raw_text)).lower()
    folded = folded.replace("-", " ").replace("_", " ")
    base_tokens = re.findall(r"[a-z0-9]+", folded)
    tokens: list[str] = []
    for token in base_tokens:
        tokens.append(token)
        if token.startswith("2d") and token != "2d":
            tokens.append("2d")
            remainder = token[2:]
            if remainder:
                tokens.append(remainder)
        if token.startswith("2") and len(token) > 1 and token[1:].startswith("d"):
            tokens.append("2d")
    return tuple(tokens)


def _edit_distance_at_most_one(left: str, right: str) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) <= 1
    if len(left) > len(right):
        left, right = right, left
    index_left = 0
    index_right = 0
    difference = 0
    while index_left < len(left) and index_right < len(right):
        if left[index_left] == right[index_right]:
            index_left += 1
            index_right += 1
        else:
            difference += 1
            index_right += 1
            if difference > 1:
                return False
    return True


def _has_close_token(tokens: tuple[str, ...], forms: tuple[str, ...]) -> bool:
    for token in tokens:
        for form in forms:
            if token.startswith(form) or _edit_distance_at_most_one(token, form):
                return True
    return False


def _recognizes_planar_refutation(tokens: tuple[str, ...]) -> bool:
    joined = " ".join(tokens)
    has_refutation = _has_close_token(tokens, ("cafol", "cafold", "refute", "disprove")) or "cafold meg" in joined
    has_named_request = _has_close_token(tokens, ("jacobi", "jakobi"))
    has_assertion_word = _has_close_token(tokens, ("sejtes", "sejtest", "sejtestet", "conjecture"))
    has_dimension = "2d" in tokens or ("2" in tokens and "d" in tokens) or "ketdimenzios" in tokens or "twodimensional" in tokens
    return bool(has_refutation and has_named_request and has_assertion_word and has_dimension)


def _split_equality(raw_text: str) -> tuple[str, str] | None:
    value = raw_text.replace("==", "=").replace("≡", "=").replace("＝", "=")
    for index, character in enumerate(value):
        if character == "=":
            previous = value[index - 1] if index else ""
            if previous not in ("!", "<", ">"):
                return value[:index], value[index + 1 :]
    return None


def _suspicion_score(segment: str) -> int:
    allowed = {"sqrt", "root", "Rational", "Integer", "I"}
    identifiers = re.findall(r"[A-Za-z_]\w*", segment)
    return sum(1 for item in identifiers if len(item) > 1 and item not in allowed)


def _parse_segment(segment: str) -> Any:
    return exact_parse_expression(segment.strip())


def _choose_math_segment(text: str, side: str) -> str | None:
    fragments: list[str] = []
    for chunk in re.split(r"[:,;]", text):
        words = chunk.strip().split()
        if side == "left":
            for index in range(len(words)):
                fragments.append(" ".join(words[index:]))
        else:
            for index in range(1, len(words) + 1):
                fragments.append(" ".join(words[:index]))
        stripped = chunk.strip()
        if stripped:
            fragments.append(stripped)
    best: tuple[int, int, str] | None = None
    for fragment in fragments:
        if not fragment.strip():
            continue
        try:
            _parse_segment(fragment)
        except Exception:
            continue
        operator_count = sum(1 for character in fragment if character in "+-*/^()0123456789")
        score = (_suspicion_score(fragment), -operator_count - len(fragment), fragment)
        if best is None or score < best:
            best = score
    return None if best is None else best[2]


def _parse_algebraic_target(raw_text: str) -> AlgebraicIdentityTarget:
    split = _split_equality(raw_text)
    if split is None:
        return AlgebraicIdentityTarget(variables=(), left_expression="0", right_expression="0")
    left_raw, right_raw = split
    left_segment = _choose_math_segment(left_raw, "left") or left_raw.strip()
    right_segment = _choose_math_segment(right_raw, "right") or right_raw.strip()
    try:
        left_expression = exact_parse_expression(left_segment)
        right_expression = exact_parse_expression(right_segment)
    except Exception:
        return AlgebraicIdentityTarget(variables=(), left_expression="0", right_expression="0")
    variables = tuple(sorted(str(symbol) for symbol in left_expression.free_symbols | right_expression.free_symbols))
    return AlgebraicIdentityTarget(
        variables=variables,
        left_expression=canonicalize_formula(left_expression),
        right_expression=canonicalize_formula(right_expression),
        domain=ExactDomain.ALGEBRAIC,
        search_extent=2,
    )


def _looks_like_group_request(tokens: tuple[str, ...], raw_text: str) -> bool:
    group_words = {"group", "groups", "csoport", "csoportban", "finite", "veges", "véges"}
    has_group_word = any(token in group_words for token in tokens)
    has_equality = _split_equality(raw_text) is not None
    has_inverse = "^-1" in raw_text or "⁻¹" in raw_text or "'" in raw_text or "inverse" in tokens or "inverz" in tokens
    has_operation = "*" in raw_text or "·" in raw_text
    return bool(has_group_word and has_equality and (has_inverse or has_operation or "identity" in tokens or "azonossag" in tokens))


def _trim_group_side(text: str, side: str) -> str:
    if side == "left":
        pieces = re.split(r":|\bto\b|\blaw\b|\bidentity\b|\bazonossag\b", text, flags=re.IGNORECASE)
        return pieces[-1].strip()
    pieces = re.split(r"[.;,\n]", text)
    return pieces[0].strip()


def _parse_group_target(raw_text: str) -> FiniteGroupIdentityTarget:
    split = _split_equality(raw_text)
    if split is None:
        return FiniteGroupIdentityTarget(variables=("x",), left_word="x", right_word="x")
    left_raw, right_raw = split
    left_word = _trim_group_side(left_raw, "left") or left_raw.strip()
    right_word = _trim_group_side(right_raw, "right") or right_raw.strip()
    reserved = {"e", "id", "identity", "one", "inv"}
    letters = []
    for token in re.findall(r"[A-Za-z]", left_word + " " + right_word):
        lower = token.lower()
        if lower not in reserved and lower not in letters:
            letters.append(lower)
    variables = tuple(letters) if letters else ("x",)
    return FiniteGroupIdentityTarget(variables=variables, left_word=left_word, right_word=right_word, max_order=6)


def formalize_request(raw_text: str) -> ProblemSpec:
    raw = "" if raw_text is None else str(raw_text)
    tokens = _normalized_tokens(raw)
    if _recognizes_planar_refutation(tokens):
        target = PlanarMapTarget()
        return ProblemSpec(
            kind=ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION,
            raw_text=raw,
            normalized_tokens=tokens,
            variables=("x", "y"),
            mappings={"first_component": "F1", "second_component": "F2", "first_point": "P", "second_point": "Q"},
            predicates=("constant_derivative_determinant_nonzero", "collision_at_distinct_exact_points"),
            domains=(ExactDomain.RATIONAL, ExactDomain.ALGEBRAIC),
            output_roles={"first_component": "F₁", "second_component": "F₂", "first_point": "P", "second_point": "Q"},
            planar_target=target,
        )
    if _looks_like_group_request(tokens, raw):
        target = _parse_group_target(raw)
        return ProblemSpec(
            kind=ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL,
            raw_text=raw,
            normalized_tokens=tokens,
            variables=target.variables,
            mappings={"operation": "*", "identity": target.identity_symbol},
            predicates=("finite_group_table", "word_inequality"),
            domains=(ExactDomain.FINITE_TABLE,),
            output_roles={"table": "*", "identity": target.identity_symbol},
            finite_group_identity=target,
        )
    target = _parse_algebraic_target(raw)
    return ProblemSpec(
        kind=ProblemKind.ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT,
        raw_text=raw,
        normalized_tokens=tokens,
        variables=target.variables,
        mappings={"left": target.left_expression, "right": target.right_expression},
        predicates=("assignment_inequality",),
        domains=(ExactDomain.ALGEBRAIC,),
        output_roles={variable: variable for variable in target.variables},
        algebraic_identity=target,
    )
