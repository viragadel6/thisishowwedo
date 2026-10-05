from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ProblemKind(str, Enum):
    PLANAR_CONSTANT_DETERMINANT_COLLISION = "planar_constant_determinant_collision"
    ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT = "algebraic_identity_counterassignment"
    FINITE_GROUP_IDENTITY_COUNTERMODEL = "finite_group_identity_countermodel"


class ExactDomain(str, Enum):
    RATIONAL = "rational"
    ALGEBRAIC = "algebraic"
    MODULAR_PRESCREEN = "modular_prescreen"
    FINITE_TABLE = "finite_table"


class FrontierKind(str, Enum):
    FULL_POLYNOMIAL = "full_polynomial"
    SPARSE_POLYNOMIAL = "sparse_polynomial"
    COLLISION_INTERPOLATION = "collision_interpolation"
    DETERMINANT_FIRST = "determinant_first"
    HOMOGENEOUS_LAYER = "homogeneous_layer"
    SYMMETRY_ACTION = "symmetry_action"
    COMPOSITION_PERTURBATION = "composition_perturbation"
    SUPPORT_MUTATION = "support_mutation"
    FINITE_FIELD_PRESCREEN = "finite_field_prescreen"
    ALGEBRAIC_POINT_COLLISION = "algebraic_point_collision"
    ELIMINATION_ORDER = "elimination_order"
    ALGEBRAIC_ASSIGNMENT = "algebraic_assignment"
    FINITE_STRUCTURE = "finite_structure"


class SymmetryMode(str, Enum):
    NONE = "none"
    SWAP = "swap"
    ANTISYMMETRY = "antisymmetry"
    SIGN = "sign"


class CompositionScheme(str, Enum):
    DIRECT = "direct"
    IDENTITY_PERTURBATION = "identity_perturbation"
    TRIANGULAR_COMPOSITION = "triangular_composition"
    AFFINE_COMPOSITION = "affine_composition"
    LAYERED = "layered"


class EliminationObjective(str, Enum):
    COEFFICIENTS_FIRST = "coefficients_first"
    DETERMINANT_FIRST = "determinant_first"
    COLLISION_FIRST = "collision_first"
    MIXED = "mixed"
    RESULTANT = "resultant"
    GROEBNER = "groebner"


class PointPattern(str, Enum):
    RATIONAL_GRID = "rational_grid"
    AXIS_PAIR = "axis_pair"
    DIAGONAL_PAIR = "diagonal_pair"
    SWAPPED_PAIR = "swapped_pair"
    ALGEBRAIC_GRID = "algebraic_grid"
    FINITE_FIELD = "finite_field"
    ORIGIN_PAIR = "origin_pair"


@dataclass(frozen=True)
class PlanarMapTarget:
    variables: tuple[str, str] = ("x", "y")
    component_roles: tuple[str, str] = ("F1", "F2")
    point_roles: tuple[str, str] = ("P", "Q")
    coefficient_domains: tuple[ExactDomain, ...] = (ExactDomain.RATIONAL, ExactDomain.ALGEBRAIC)
    point_domains: tuple[ExactDomain, ...] = (ExactDomain.RATIONAL, ExactDomain.ALGEBRAIC)
    determinant_must_be_nonzero_constant: bool = True


@dataclass(frozen=True)
class AlgebraicIdentityTarget:
    variables: tuple[str, ...]
    left_expression: str
    right_expression: str
    domain: ExactDomain = ExactDomain.ALGEBRAIC
    search_extent: int = 2


@dataclass(frozen=True)
class FiniteGroupIdentityTarget:
    variables: tuple[str, ...]
    left_word: str
    right_word: str
    identity_symbol: str = "e"
    inverse_symbol: str = "^-1"
    operation_symbols: tuple[str, ...] = ("*", "·", "")
    max_order: int = 6


@dataclass(frozen=True)
class ProblemSpec:
    kind: ProblemKind
    raw_text: str
    normalized_tokens: tuple[str, ...]
    variables: tuple[str, ...] = field(default_factory=tuple)
    mappings: Mapping[str, str] = field(default_factory=dict)
    predicates: tuple[str, ...] = field(default_factory=tuple)
    domains: tuple[ExactDomain, ...] = field(default_factory=tuple)
    output_roles: Mapping[str, str] = field(default_factory=dict)
    planar_target: PlanarMapTarget | None = None
    algebraic_identity: AlgebraicIdentityTarget | None = None
    finite_group_identity: FiniteGroupIdentityTarget | None = None


@dataclass(frozen=True)
class Frontier:
    kind: FrontierKind
    degree_extent: int
    coefficient_extent: int
    support_sets: tuple[tuple[tuple[int, int], ...], ...]
    symmetry_mode: SymmetryMode
    composition_scheme: CompositionScheme
    elimination_objective: EliminationObjective
    point_pattern: PointPattern
    exact_domain: ExactDomain
    lane_identifier: str
    mutation_lineage: tuple[str, ...]
    unique_signature: str
    extra_parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratedCodeResult:
    frontier_signature: str
    source: str
    entry_function: str
    source_fingerprint: str
    generation_issues: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Candidate:
    problem_kind: ProblemKind
    formulas: Mapping[str, str] = field(default_factory=dict)
    points: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    assignments: Mapping[str, Any] = field(default_factory=dict)
    finite_structures: Mapping[str, Any] = field(default_factory=dict)
    exact_derivation_artifacts: Mapping[str, Any] = field(default_factory=dict)
    source_fingerprint: str = ""
    frontier_signature: str = ""


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    candidate: Candidate | None
    issues: tuple[str, ...] = field(default_factory=tuple)
    artifacts: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CritiqueIssue:
    code: str
    description: str
    severity: str
    resolved: bool = False
    repair_hint: str = ""


@dataclass(frozen=True)
class CritiqueResult:
    passed: bool
    issues: tuple[CritiqueIssue, ...] = field(default_factory=tuple)
    artifacts: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RepairRequest:
    reason: str
    source_frontier: Frontier | None = None
    verification_result: VerificationResult | None = None
    critique_result: CritiqueResult | None = None
    execution_result: Any | None = None
    exception_text: str = ""


@dataclass(frozen=True)
class FrontierResult:
    frontier: Frontier
    generated_result: GeneratedCodeResult | None
    candidates: tuple[Candidate, ...] = field(default_factory=tuple)
    failure_reasons: tuple[str, ...] = field(default_factory=tuple)
    exception_text: str = ""
    internal_artifacts: Mapping[str, Any] = field(default_factory=dict)
