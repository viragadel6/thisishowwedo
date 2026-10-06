from __future__ import annotations

from collections.abc import Mapping as _MappingABC
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class FormalizationError(ValueError):
    pass


class FrozenMapping(_MappingABC):
    __slots__ = ("_entries",)

    def __init__(self, source: Any = ()) -> None:
        if isinstance(source, FrozenMapping):
            entries = source._entries
        elif isinstance(source, _MappingABC):
            entries = tuple((key, source[key]) for key in source.keys())
        else:
            entries = tuple((key, value) for key, value in source)
        object.__setattr__(self, "_entries", tuple(entries))

    def __getitem__(self, key: Any) -> Any:
        for entry_key, entry_value in self._entries:
            if entry_key == key:
                return entry_value
        raise KeyError(key)

    def __iter__(self):
        return iter(key for key, _ in self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __hash__(self) -> int:
        try:
            return hash(self._entries)
        except TypeError:
            return hash(tuple(key for key, _ in self._entries))

    def __repr__(self) -> str:
        return "FrozenMapping(" + repr(dict(self._entries)) + ")"


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", tuple(self.variables))
        object.__setattr__(self, "component_roles", tuple(self.component_roles))
        object.__setattr__(self, "point_roles", tuple(self.point_roles))
        object.__setattr__(self, "coefficient_domains", tuple(self.coefficient_domains))
        object.__setattr__(self, "point_domains", tuple(self.point_domains))


@dataclass(frozen=True)
class AlgebraicIdentityTarget:
    variables: tuple[str, ...]
    left_expression: str
    right_expression: str
    domain: ExactDomain = ExactDomain.ALGEBRAIC
    search_extent: int = 2
    left_source: str = ""
    right_source: str = ""
    left_obligations: tuple[str, ...] = ()
    right_obligations: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", tuple(self.variables))
        object.__setattr__(self, "left_obligations", tuple(self.left_obligations))
        object.__setattr__(self, "right_obligations", tuple(self.right_obligations))
        object.__setattr__(self, "constraints", tuple(self.constraints))
        object.__setattr__(self, "search_extent", int(self.search_extent))


@dataclass(frozen=True)
class FiniteGroupIdentityTarget:
    variables: tuple[str, ...]
    left_word: str
    right_word: str
    identity_symbol: str = "e"
    inverse_symbol: str = "^-1"
    operation_symbols: tuple[str, ...] = ("*", "·", "")
    max_order: int = 6
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", tuple(self.variables))
        object.__setattr__(self, "operation_symbols", tuple(self.operation_symbols))
        object.__setattr__(self, "constraints", tuple(self.constraints))
        object.__setattr__(self, "max_order", int(self.max_order))


@dataclass(frozen=True)
class ProblemSpec:
    kind: ProblemKind
    raw_text: str
    normalized_tokens: tuple[str, ...]
    variables: tuple[str, ...] = field(default_factory=tuple)
    mappings: Mapping[str, str] = field(default_factory=FrozenMapping)
    predicates: tuple[str, ...] = field(default_factory=tuple)
    domains: tuple[ExactDomain, ...] = field(default_factory=tuple)
    output_roles: Mapping[str, str] = field(default_factory=FrozenMapping)
    constraints: tuple[str, ...] = field(default_factory=tuple)
    order_bound: int | None = None
    planar_target: PlanarMapTarget | None = None
    algebraic_identity: AlgebraicIdentityTarget | None = None
    finite_group_identity: FiniteGroupIdentityTarget | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "normalized_tokens", tuple(self.normalized_tokens))
        object.__setattr__(self, "variables", tuple(self.variables))
        object.__setattr__(self, "predicates", tuple(self.predicates))
        object.__setattr__(self, "domains", tuple(self.domains))
        object.__setattr__(self, "constraints", tuple(self.constraints))
        object.__setattr__(self, "mappings", FrozenMapping(self.mappings))
        object.__setattr__(self, "output_roles", FrozenMapping(self.output_roles))


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
    extra_parameters: Mapping[str, Any] = field(default_factory=FrozenMapping)

    def __post_init__(self) -> None:
        supports = tuple(tuple((int(first), int(second)) for first, second in support) for support in self.support_sets)
        object.__setattr__(self, "support_sets", supports)
        object.__setattr__(self, "degree_extent", int(self.degree_extent))
        object.__setattr__(self, "coefficient_extent", int(self.coefficient_extent))
        object.__setattr__(self, "mutation_lineage", tuple(str(item) for item in self.mutation_lineage))
        object.__setattr__(self, "extra_parameters", FrozenMapping(self.extra_parameters))


@dataclass(frozen=True)
class GeneratedCodeResult:
    frontier_signature: str
    source: str
    entry_function: str
    source_fingerprint: str
    generation_issues: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "generation_issues", tuple(self.generation_issues))


@dataclass(frozen=True)
class Candidate:
    problem_kind: ProblemKind
    formulas: Mapping[str, str] = field(default_factory=FrozenMapping)
    points: Mapping[str, tuple[str, ...]] = field(default_factory=FrozenMapping)
    assignments: Mapping[str, Any] = field(default_factory=FrozenMapping)
    finite_structures: Mapping[str, Any] = field(default_factory=FrozenMapping)
    exact_derivation_artifacts: Mapping[str, Any] = field(default_factory=FrozenMapping)
    source_fingerprint: str = ""
    frontier_signature: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "formulas", FrozenMapping(self.formulas))
        points = FrozenMapping(
            (str(key), tuple(str(item) for item in value)) for key, value in dict(self.points).items()
        )
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "assignments", FrozenMapping(self.assignments))
        object.__setattr__(self, "finite_structures", FrozenMapping(self.finite_structures))
        object.__setattr__(self, "exact_derivation_artifacts", FrozenMapping(self.exact_derivation_artifacts))


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    candidate: Candidate | None
    issues: tuple[str, ...] = field(default_factory=tuple)
    artifacts: Mapping[str, Any] = field(default_factory=FrozenMapping)

    def __post_init__(self) -> None:
        object.__setattr__(self, "issues", tuple(self.issues))
        object.__setattr__(self, "artifacts", FrozenMapping(self.artifacts))


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
    artifacts: Mapping[str, Any] = field(default_factory=FrozenMapping)

    def __post_init__(self) -> None:
        object.__setattr__(self, "issues", tuple(self.issues))
        object.__setattr__(self, "artifacts", FrozenMapping(self.artifacts))


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
    internal_artifacts: Mapping[str, Any] = field(default_factory=FrozenMapping)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "failure_reasons", tuple(self.failure_reasons))
        object.__setattr__(self, "internal_artifacts", FrozenMapping(self.internal_artifacts))


@dataclass(frozen=True)
class SearchBudget:
    max_frontier_visits: int = 240
    max_verified_candidates: int = 120
    max_mutation_rounds: int = 60
    max_seconds: float = 60.0
    max_candidates_per_frontier: int = 4
    max_instances_per_solve: int = 4096
    max_point_pairs: int = 512
    execution_timeout_seconds: float = 25.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_frontier_visits", int(self.max_frontier_visits))
        object.__setattr__(self, "max_verified_candidates", int(self.max_verified_candidates))
        object.__setattr__(self, "max_mutation_rounds", int(self.max_mutation_rounds))
        object.__setattr__(self, "max_seconds", float(self.max_seconds))
        object.__setattr__(self, "max_candidates_per_frontier", int(self.max_candidates_per_frontier))
        object.__setattr__(self, "max_instances_per_solve", int(self.max_instances_per_solve))
        object.__setattr__(self, "max_point_pairs", int(self.max_point_pairs))
        object.__setattr__(self, "execution_timeout_seconds", float(self.execution_timeout_seconds))
