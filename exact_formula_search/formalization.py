from __future__ import annotations

import re
import unicodedata
from typing import Any

from .models import (
    AlgebraicIdentityTarget,
    ExactDomain,
    FiniteGroupIdentityTarget,
    FormalizationError,
    PlanarMapTarget,
    ProblemKind,
    ProblemSpec,
)
from .symbolic_tools import (
    canonicalize_formula,
    exact_parse_expression,
    expression_domain_obligations,
    normalize_math_text,
    tokenize_group_word,
)

_PROSE_WORDS = frozenset(
    """
    is are was were be been being am
    the a an and or nor but so yet for
    all any some each every both few more most other such only own same than too very
    there here when where why how what which who whom whose that this these those
    if then else thus hence therefore however moreover furthermore nevertheless otherwise
    because since although though unless until whether either neither while during before after above below
    do does did done can could should would shall will may might must have has had having
    of in on at to from by with without about into over under between among up down out off again
    find refute disprove prove show demonstrate establish verify check test determine search seek
    given suppose assume consider let us please help need want using use used via per
    true false valid invalid correct wrong right
    identity equation equality expression statement claim conjecture hypothesis theorem lemma proposition
    counterexample countermodel counterassignment counterexamples example instance instances
    value values variable variables constant constants coefficient coefficients domain range set sets
    group groups ring rings field fields integer integers rational rationals real reals complex number numbers
    positive negative nonnegative nonzero zero dimension dimensional plane planar map mapping function functions
    determinant jacobian jacobi matrix polynomial polynomials degree order element elements table operation
    inverse law laws hold holds satisfied satisfies exists exist
    question problem task exercise next previous first second third last etc
    in on under above below following respect terms sense case cases fact point view
    szamit szamitani
    a az egy es vagy nem igen de ha akkor hogy hogyan mi ki melyik hol mikor mennyi
    minden mind barmely valamilyen letezik nincs van legyen keres keress talalj mutasd mutassa
    bizonyit bizonyitand bizonyitasa igaz hamis
    azonossag egyenlet egyenloseg kifejezes allitas felteves tetel sejtes sejtest
    ellenpelda pelda ertek valtozo allando halmaz
    csoport csoportban csoportok gyuru gyuruk test testben mezo mezok
    egesz egeszek szam szamok racionalis racionalisak algebrai algebraiak
    pozitiv negativ nemnegativ nemnulla nulla ketto harom negy ot hat het nyolc kilenc
    dimenzio dimenzios ketdimenzios ketdimenzionalis sik sikbeli lekepezes fuggveny
    determinans matrix polinom fok rend elem eleme muvelet inverz torveny teljesul
    keresd keressuk adj adja epits vizsgald feltetelezzuk legyenek
    illetve tovabba mivel mert habar ugyanakkor ezert tehat vagyis azaz
    amelyik aki ami stb reszletesen foleg feladat kerdes valasz
    """.split()
)

_GROUP_MARKERS = frozenset({"group", "groups", "csoport", "csoportban", "csoportok", "gruppe", "grupo", "groupe"})
_STRONG_GROUP_MARKERS = frozenset({"group", "groups", "csoport", "csoportban", "csoportok", "gruppe", "grupo", "groupe"})
_NON_GROUP_MARKERS = frozenset(
    {
        "ring",
        "rings",
        "gyuru",
        "gyuruk",
        "field",
        "fields",
        "mezo",
        "mezok",
        "ideal",
        "ideals",
        "module",
        "modules",
        "vector",
        "space",
        "spaces",
        "lattice",
        "semigroup",
        "monoid",
        "quasigroup",
        "loop",
        "algebra",
        "category",
    }
)
_IDENTITY_MARKERS = frozenset({"identity", "azonossag", "unit", "neutral", "egyseg", "egység", "inverse", "inverz", "e", "1"})
_POSITIVE_MARKERS = ("positive", "pozitiv", "strictly positive")
_NONNEGATIVE_MARKERS = ("nonnegative", "non negative", "nemnegativ", "nem negativ", "not negative")
_NEGATIVE_MARKERS = ("negative", "negativ", "strictly negative")
_NONPOSITIVE_MARKERS = ("nonpositive", "non positive", "nempozitiv", "nem pozitiv", "not positive")
_INTEGER_MARKERS = ("integer", "integers", "integral", "egesz", "whole number", "natural number", "termeszetes")
_RATIONAL_MARKERS = ("rational", "racionalis")
_ALGEBRAIC_MARKERS = ("algebraic", "algebrai")
_NONZERO_MARKERS = ("nonzero", "non zero", "not zero", "nem nulla", "nemnulla", "not equal to zero")
_ORDER_PATTERNS = (
    r"order\s*(?:of\s*)?(?:at\s*most\s*|up\s*to\s*|no\s*more\s*than\s*)?(\d+)",
    r"max(?:imum)?\s*order\s*(?:of\s*)?(\d+)",
    r"at\s*most\s*(\d+)\s*(?:elements|group)",
    r"(\d+)\s*or\s*fewer\s*(?:elements|group)",
    r"legfeljebb\s*(\d+)",
    r"\|\s*g\s*\|\s*<=\s*(\d+)",
    r"order\s*<=\s*(\d+)",
    r"orders?\s*up\s*to\s*(\d+)",
)
_EXTENT_PATTERNS = (
    r"(?:up\s*to|at\s*most|bound(?:ed)?\s*(?:by|of)?|extent\s*(?:of)?|legfeljebb)\s*(\d+)",
    r"\|\s*[a-z]\s*\|\s*<=\s*(\d+)",
)


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(character for character in decomposed if unicodedata.category(character) != "Mn")


def _folded_text(raw_text: str) -> str:
    folded = _strip_accents(unicodedata.normalize("NFKC", raw_text)).lower()
    return folded.replace("≤", "<=").replace("≥", ">=")


def _normalized_tokens(raw_text: str) -> tuple[str, ...]:
    folded = _folded_text(raw_text)
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


def _has_planar_dimension(tokens: tuple[str, ...]) -> bool:
    if "2d" in tokens:
        return True
    if "twodimensional" in tokens or "twodim" in tokens:
        return True
    dimension_forms = ("dimensional", "dimenzios", "dimenzio", "dimenzionalis", "dimension", "dimensions", "dims", "variable", "variables", "coord", "coords")
    if "two" in tokens and any(form in tokens for form in dimension_forms):
        return True
    if "2" in tokens and any(form in tokens for form in dimension_forms):
        return True
    if "ket" in tokens and any(form in tokens for form in ("dimenzios", "dimenzio", "dimenzionalis", "dimension")):
        return True
    if "ketdimenzios" in tokens or "ketdimenzionalis" in tokens:
        return True
    if "planar" in tokens or "sikbeli" in tokens:
        return True
    return False


def _recognizes_planar_refutation(tokens: tuple[str, ...]) -> bool:
    joined = " ".join(tokens)
    has_refutation = _has_close_token(tokens, ("cafol", "cafold", "refute", "disprove")) or "cafold meg" in joined
    has_named_request = _has_close_token(tokens, ("jacobi", "jakobi"))
    has_assertion_word = _has_close_token(tokens, ("sejtes", "sejtest", "sejtestet", "conjecture"))
    has_dimension = _has_planar_dimension(tokens)
    return bool(has_refutation and has_named_request and has_assertion_word and has_dimension)


def _split_equality(raw_text: str) -> tuple[str, str] | None:
    value = normalize_math_text(str(raw_text))
    value = value.replace("==", "=").replace("≡", "=").replace("＝", "=")
    for index, character in enumerate(value):
        if character == "=":
            previous = value[index - 1] if index else ""
            if previous not in ("!", "<", ">"):
                return value[:index], value[index + 1 :]
    return None


def _is_prose_token(token: str) -> bool:
    cleaned = token.strip().strip(".,;:!?()[]{}\"'").lower()
    if not cleaned:
        return True
    if len(cleaned) == 1:
        return False
    folded = _strip_accents(cleaned)
    return folded in _PROSE_WORDS or cleaned in _PROSE_WORDS


def _trim_prose_edges(text: str) -> str:
    tokens = text.split()
    while tokens and _is_prose_token(tokens[0]):
        tokens.pop(0)
    while tokens and _is_prose_token(tokens[-1]):
        tokens.pop()
    return " ".join(tokens)


_MATH_CHARACTERS = frozenset("0123456789+-*/^()_.,")


def _segment_score(fragment: str) -> tuple[int, int, int]:
    operators = sum(1 for character in fragment if character in _MATH_CHARACTERS)
    identifiers = re.findall(r"[A-Za-z_]\w*", fragment)
    variables = sum(1 for item in identifiers if len(item) > 1 and not _is_prose_token(item))
    prose = sum(1 for token in fragment.split() if _is_prose_token(token))
    return (prose, -operators - variables, -len(fragment))


_QUOTE_CHARACTERS = "\"\u201c\u201d\u2018\u2019'`\u00ab\u00bb\u2039\u203a"


def _choose_math_segment(text: str, side: str) -> str | None:
    cleaned = str(text)
    for character in _QUOTE_CHARACTERS:
        cleaned = cleaned.replace(character, " ")
    words = cleaned.split()
    if not words:
        return None
    candidates: list[str] = []
    for start in range(len(words)):
        for end in range(start + 1, len(words) + 1):
            fragment = " ".join(words[start:end])
            candidates.append(fragment)
    best: tuple[tuple[int, int, int], str] | None = None
    for fragment in candidates:
        stripped = fragment.strip()
        if not stripped:
            continue
        if not any(character in _MATH_CHARACTERS for character in stripped) and len(stripped.split()) > 1:
            continue
        try:
            exact_parse_expression(stripped)
        except Exception:
            continue
        score = _segment_score(stripped)
        if best is None or score < best[0]:
            best = (score, stripped)
    return None if best is None else best[1]


def _contains_marker(folded: str, markers: tuple[str, ...]) -> bool:
    return any(marker in folded for marker in markers)


def _first_integer_match(folded: str, patterns: tuple[str, ...]) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, folded)
        if match is not None:
            try:
                return int(match.group(1))
            except (TypeError, ValueError):
                continue
    return None


def _declared_constraints(raw_text: str) -> tuple[str, ...]:
    folded = _folded_text(raw_text)
    constraints: list[str] = []
    nonnegative = _contains_marker(folded, _NONNEGATIVE_MARKERS)
    nonpositive = _contains_marker(folded, _NONPOSITIVE_MARKERS)
    if nonnegative:
        constraints.append("nonnegative")
    elif not nonpositive and _contains_marker(folded, _POSITIVE_MARKERS):
        constraints.append("positive")
    if nonpositive:
        constraints.append("nonpositive")
    elif not nonnegative and _contains_marker(folded, _NEGATIVE_MARKERS):
        constraints.append("negative")
    if _contains_marker(folded, _INTEGER_MARKERS):
        constraints.append("integer")
    if _contains_marker(folded, _RATIONAL_MARKERS):
        constraints.append("rational")
    if _contains_marker(folded, _ALGEBRAIC_MARKERS):
        constraints.append("algebraic")
    if _contains_marker(folded, _NONZERO_MARKERS):
        constraints.append("nonzero")
    return tuple(constraints)


def _declared_order_bound(raw_text: str) -> int | None:
    folded = _folded_text(raw_text)
    value = _first_integer_match(folded, _ORDER_PATTERNS)
    if value is None or value < 1:
        return None
    return min(int(value), 64)


def _declared_extent(raw_text: str) -> int:
    folded = _folded_text(raw_text)
    value = _first_integer_match(folded, _EXTENT_PATTERNS)
    if value is None or value < 1:
        return 2
    return max(2, min(int(value), 8))


def _declared_domain(raw_text: str, constraints: tuple[str, ...]) -> ExactDomain:
    folded = _folded_text(raw_text)
    if _contains_marker(folded, _RATIONAL_MARKERS) or "rational" in constraints:
        return ExactDomain.RATIONAL
    if _contains_marker(folded, _ALGEBRAIC_MARKERS) or "algebraic" in constraints:
        return ExactDomain.ALGEBRAIC
    return ExactDomain.ALGEBRAIC


def _parse_algebraic_target(raw_text: str) -> AlgebraicIdentityTarget:
    split = _split_equality(raw_text)
    if split is None:
        raise FormalizationError("request contains no equality to formalize")
    left_raw, right_raw = split
    left_segment = _choose_math_segment(left_raw, "left")
    right_segment = _choose_math_segment(right_raw, "right")
    if left_segment is None or right_segment is None:
        raise FormalizationError("no parsable mathematical expression on both sides of the equality")
    try:
        left_expression = exact_parse_expression(left_segment)
        right_expression = exact_parse_expression(right_segment)
    except Exception as exception:
        raise FormalizationError("unparsable mathematical expression: " + type(exception).__name__) from exception
    try:
        left_obligations = expression_domain_obligations(left_segment)
        right_obligations = expression_domain_obligations(right_segment)
    except Exception:
        left_obligations = ()
        right_obligations = ()
    variables = tuple(sorted(str(symbol) for symbol in left_expression.free_symbols | right_expression.free_symbols))
    constraints = _declared_constraints(raw_text)
    domain = _declared_domain(raw_text, constraints)
    if "rational" in constraints:
        domain = ExactDomain.RATIONAL
    return AlgebraicIdentityTarget(
        variables=variables,
        left_expression=canonicalize_formula(left_expression),
        right_expression=canonicalize_formula(right_expression),
        domain=domain,
        search_extent=_declared_extent(raw_text),
        left_source=left_segment,
        right_source=right_segment,
        left_obligations=tuple(canonicalize_formula(item) for item in left_obligations),
        right_obligations=tuple(canonicalize_formula(item) for item in right_obligations),
        constraints=constraints,
    )


def _looks_like_group_request(tokens: tuple[str, ...], raw_text: str) -> bool:
    has_group_word = any(token in _GROUP_MARKERS for token in tokens)
    if not has_group_word:
        return False
    if any(token in _NON_GROUP_MARKERS for token in tokens) and not any(token in _STRONG_GROUP_MARKERS for token in tokens):
        return False
    has_equality = _split_equality(raw_text) is not None
    if not has_equality:
        return False
    has_inverse = "^-1" in raw_text or "⁻¹" in raw_text or "'" in raw_text or "inverse" in tokens or "inverz" in tokens
    has_operation = "*" in raw_text or "·" in raw_text or "⋅" in raw_text
    has_identity_marker = any(token in _IDENTITY_MARKERS for token in tokens)
    return bool(has_inverse or has_operation or has_identity_marker)


_GROUP_WORD_ALPHABET = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_*^-()' ")
_GROUP_PUNCTUATION = ".,;:!?()[]{}\"'"


def _is_group_math_token(token: str) -> bool:
    cleaned = token.strip().strip(_GROUP_PUNCTUATION)
    if not cleaned:
        return False
    if cleaned.isdigit() and cleaned != "1":
        return False
    for character in cleaned:
        if character not in _GROUP_WORD_ALPHABET:
            return False
    return not _is_prose_token(cleaned)


def _group_word_runs(text: str) -> list[str]:
    runs: list[str] = []
    current: list[str] = []
    for token in text.split():
        if _is_group_math_token(token):
            current.append(token)
        else:
            if current:
                runs.append(" ".join(current))
                current = []
    if current:
        runs.append(" ".join(current))
    return runs


def _trim_group_side(text: str, side: str) -> str:
    runs = _group_word_runs(text)
    if not runs:
        return ""
    if side == "left":
        return runs[-1]
    return runs[0]


def _group_variables(left_word: str, right_word: str) -> tuple[str, ...]:
    variables: list[str] = []
    for word in (left_word, right_word):
        for run in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", word):
            lowered = run.lower()
            if lowered in ("e", "id", "identity", "one", "unit", "inv"):
                continue
            if len(run) > 1 and _is_prose_token(run):
                continue
            if run not in variables:
                variables.append(run)
    return tuple(variables)


def _group_target_or_none(raw_text: str) -> FiniteGroupIdentityTarget | None:
    split = _split_equality(raw_text)
    if split is None:
        return None
    left_raw, right_raw = split
    left_word = _trim_group_side(left_raw, "left") or left_raw.strip()
    right_word = _trim_group_side(right_raw, "right") or right_raw.strip()
    if not left_word or not right_word:
        return None
    variables = _group_variables(left_word, right_word)
    if not variables:
        return None
    try:
        for word in (left_word, right_word):
            tokenize_group_word(word, variables)
    except Exception:
        return None
    order_bound = _declared_order_bound(raw_text)
    max_order = order_bound if order_bound is not None else 6
    return FiniteGroupIdentityTarget(
        variables=variables,
        left_word=left_word,
        right_word=right_word,
        max_order=max_order,
        constraints=_declared_constraints(raw_text),
    )


def _parse_group_target(raw_text: str) -> FiniteGroupIdentityTarget:
    target = _group_target_or_none(raw_text)
    if target is None:
        raise FormalizationError("group identity words could not be parsed as group words")
    return target


def formalize_request(raw_text: str) -> ProblemSpec:
    raw = "" if raw_text is None else str(raw_text)
    tokens = _normalized_tokens(raw)
    constraints = _declared_constraints(raw)
    order_bound = _declared_order_bound(raw)
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
            constraints=constraints,
            planar_target=target,
        )
    if _looks_like_group_request(tokens, raw):
        target = _group_target_or_none(raw)
        if target is not None:
            return ProblemSpec(
                kind=ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL,
                raw_text=raw,
                normalized_tokens=tokens,
                variables=target.variables,
                mappings={"operation": "*", "identity": target.identity_symbol},
                predicates=("finite_group_table", "word_inequality"),
                domains=(ExactDomain.FINITE_TABLE,),
                output_roles={"table": "*", "identity": target.identity_symbol},
                constraints=target.constraints,
                order_bound=order_bound if order_bound is not None else target.max_order,
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
        domains=(target.domain,),
        output_roles={variable: variable for variable in target.variables},
        constraints=target.constraints,
        algebraic_identity=target,
    )


def describe_formalization(specification: ProblemSpec) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": specification.kind.value,
        "variables": list(specification.variables),
        "constraints": list(specification.constraints),
    }
    if specification.algebraic_identity is not None:
        payload["left"] = specification.algebraic_identity.left_expression
        payload["right"] = specification.algebraic_identity.right_expression
    if specification.finite_group_identity is not None:
        payload["left_word"] = specification.finite_group_identity.left_word
        payload["right_word"] = specification.finite_group_identity.right_word
        payload["max_order"] = specification.finite_group_identity.max_order
    return payload
