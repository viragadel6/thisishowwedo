from __future__ import annotations

import itertools
from typing import Iterable, Mapping

from .models import (
    CompositionScheme,
    EliminationObjective,
    ExactDomain,
    Frontier,
    FrontierKind,
    PointPattern,
    ProblemKind,
    ProblemSpec,
    SymmetryMode,
)
from .symbolic_tools import stable_signature


def total_degree_support(degree: int, include_constant: bool = True) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    start = 0 if include_constant else 1
    for total in range(start, max(0, degree) + 1):
        for first in range(total, -1, -1):
            result.append((first, total - first))
    return tuple(result)


def weighted_support(degree: int, weights: tuple[int, int] = (1, 2), include_constant: bool = True) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    bound = max(0, degree)
    for first in range(bound + 1):
        for second in range(bound + 1):
            if not include_constant and first == 0 and second == 0:
                continue
            if weights[0] * first + weights[1] * second <= bound:
                result.append((first, second))
    return tuple(sorted(set(result), key=lambda item: (item[0] + item[1], item[0], item[1])))


def sparse_support(degree: int) -> tuple[tuple[int, int], ...]:
    base = {(0, 0), (1, 0), (0, 1)}
    for power in range(2, max(2, degree) + 1):
        base.add((power, 0))
        base.add((0, power))
        if power <= degree:
            base.add((power - 1, 1))
    return tuple(sorted(base, key=lambda item: (item[0] + item[1], item[0], item[1])))


def homogeneous_layer_support(degree: int) -> tuple[tuple[int, int], ...]:
    value = max(1, degree)
    return tuple((first, value - first) for first in range(value, -1, -1))


def _approach_payload(
    kind: FrontierKind,
    degree_extent: int,
    coefficient_extent: int,
    support_sets: tuple[tuple[tuple[int, int], ...], ...],
    symmetry_mode: SymmetryMode,
    composition_scheme: CompositionScheme,
    elimination_objective: EliminationObjective,
    point_pattern: PointPattern,
    exact_domain: ExactDomain,
    extra_parameters: Mapping[str, object],
) -> dict[str, object]:
    return {
        "kind": kind.value,
        "degree_extent": int(degree_extent),
        "coefficient_extent": int(coefficient_extent),
        "support_sets": support_sets,
        "symmetry_mode": symmetry_mode.value,
        "composition_scheme": composition_scheme.value,
        "elimination_objective": elimination_objective.value,
        "point_pattern": point_pattern.value,
        "exact_domain": exact_domain.value,
        "extra_parameters": dict(sorted(extra_parameters.items())),
    }


def make_frontier(
    kind: FrontierKind,
    degree_extent: int,
    coefficient_extent: int,
    support_sets: tuple[tuple[tuple[int, int], ...], ...],
    symmetry_mode: SymmetryMode,
    composition_scheme: CompositionScheme,
    elimination_objective: EliminationObjective,
    point_pattern: PointPattern,
    exact_domain: ExactDomain,
    lane_identifier: str,
    mutation_lineage: tuple[str, ...] = (),
    extra_parameters: Mapping[str, object] | None = None,
) -> Frontier:
    extra = dict(extra_parameters or {})
    payload = _approach_payload(
        kind,
        degree_extent,
        coefficient_extent,
        support_sets,
        symmetry_mode,
        composition_scheme,
        elimination_objective,
        point_pattern,
        exact_domain,
        extra,
    )
    signature = stable_signature(payload)
    return Frontier(
        kind=kind,
        degree_extent=int(degree_extent),
        coefficient_extent=int(coefficient_extent),
        support_sets=support_sets,
        symmetry_mode=symmetry_mode,
        composition_scheme=composition_scheme,
        elimination_objective=elimination_objective,
        point_pattern=point_pattern,
        exact_domain=exact_domain,
        lane_identifier=lane_identifier,
        mutation_lineage=mutation_lineage,
        unique_signature=signature,
        extra_parameters=extra,
    )


def _paired_support(support: tuple[tuple[int, int], ...]) -> tuple[tuple[tuple[int, int], ...], ...]:
    return (support, support)


def _initial_planar_frontiers() -> tuple[Frontier, ...]:
    items: list[Frontier] = []
    items.append(make_frontier(FrontierKind.FULL_POLYNOMIAL, 1, 1, _paired_support(total_degree_support(1)), SymmetryMode.NONE, CompositionScheme.DIRECT, EliminationObjective.COEFFICIENTS_FIRST, PointPattern.RATIONAL_GRID, ExactDomain.RATIONAL, "lane_full"))
    items.append(make_frontier(FrontierKind.SPARSE_POLYNOMIAL, 2, 1, _paired_support(sparse_support(2)), SymmetryMode.NONE, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.MIXED, PointPattern.AXIS_PAIR, ExactDomain.RATIONAL, "lane_sparse"))
    items.append(make_frontier(FrontierKind.COLLISION_INTERPOLATION, 2, 1, _paired_support(weighted_support(3, (1, 2))), SymmetryMode.NONE, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.COLLISION_FIRST, PointPattern.DIAGONAL_PAIR, ExactDomain.RATIONAL, "lane_collision"))
    items.append(make_frontier(FrontierKind.DETERMINANT_FIRST, 2, 1, _paired_support(total_degree_support(2, False)), SymmetryMode.NONE, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.DETERMINANT_FIRST, PointPattern.ORIGIN_PAIR, ExactDomain.RATIONAL, "lane_determinant"))
    items.append(make_frontier(FrontierKind.HOMOGENEOUS_LAYER, 3, 1, _paired_support(homogeneous_layer_support(3)), SymmetryMode.NONE, CompositionScheme.LAYERED, EliminationObjective.DETERMINANT_FIRST, PointPattern.AXIS_PAIR, ExactDomain.RATIONAL, "lane_layer"))
    items.append(make_frontier(FrontierKind.SYMMETRY_ACTION, 2, 1, _paired_support(total_degree_support(2, False)), SymmetryMode.SWAP, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.MIXED, PointPattern.SWAPPED_PAIR, ExactDomain.RATIONAL, "lane_symmetry"))
    items.append(make_frontier(FrontierKind.COMPOSITION_PERTURBATION, 3, 1, _paired_support(sparse_support(3)), SymmetryMode.NONE, CompositionScheme.TRIANGULAR_COMPOSITION, EliminationObjective.MIXED, PointPattern.RATIONAL_GRID, ExactDomain.RATIONAL, "lane_composition"))
    items.append(make_frontier(FrontierKind.SUPPORT_MUTATION, 3, 1, _paired_support(weighted_support(4, (2, 1))), SymmetryMode.SIGN, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.MIXED, PointPattern.DIAGONAL_PAIR, ExactDomain.RATIONAL, "lane_support"))
    items.append(make_frontier(FrontierKind.FINITE_FIELD_PRESCREEN, 2, 1, _paired_support(sparse_support(2)), SymmetryMode.NONE, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.MIXED, PointPattern.FINITE_FIELD, ExactDomain.MODULAR_PRESCREEN, "lane_modular", extra_parameters={"prime": 2}))
    items.append(make_frontier(FrontierKind.ALGEBRAIC_POINT_COLLISION, 2, 1, _paired_support(sparse_support(2)), SymmetryMode.NONE, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.COLLISION_FIRST, PointPattern.ALGEBRAIC_GRID, ExactDomain.ALGEBRAIC, "lane_algebraic_point"))
    items.append(make_frontier(FrontierKind.ELIMINATION_ORDER, 2, 1, _paired_support(sparse_support(2)), SymmetryMode.NONE, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.GROEBNER, PointPattern.RATIONAL_GRID, ExactDomain.RATIONAL, "lane_elimination", extra_parameters={"term_order": "lex"}))
    return tuple(items)


def _initial_algebraic_frontiers() -> tuple[Frontier, ...]:
    return (
        make_frontier(FrontierKind.ALGEBRAIC_ASSIGNMENT, 0, 0, (), SymmetryMode.NONE, CompositionScheme.DIRECT, EliminationObjective.COEFFICIENTS_FIRST, PointPattern.RATIONAL_GRID, ExactDomain.RATIONAL, "lane_assignment_0"),
        make_frontier(FrontierKind.ALGEBRAIC_ASSIGNMENT, 1, 1, (), SymmetryMode.NONE, CompositionScheme.DIRECT, EliminationObjective.COEFFICIENTS_FIRST, PointPattern.RATIONAL_GRID, ExactDomain.RATIONAL, "lane_assignment_1"),
        make_frontier(FrontierKind.ALGEBRAIC_ASSIGNMENT, 2, 2, (), SymmetryMode.NONE, CompositionScheme.DIRECT, EliminationObjective.MIXED, PointPattern.ALGEBRAIC_GRID, ExactDomain.ALGEBRAIC, "lane_assignment_2"),
    )


def _initial_group_frontiers() -> tuple[Frontier, ...]:
    return (
        make_frontier(FrontierKind.FINITE_STRUCTURE, 1, 1, (), SymmetryMode.NONE, CompositionScheme.DIRECT, EliminationObjective.COEFFICIENTS_FIRST, PointPattern.RATIONAL_GRID, ExactDomain.FINITE_TABLE, "lane_table_1"),
        make_frontier(FrontierKind.FINITE_STRUCTURE, 2, 2, (), SymmetryMode.NONE, CompositionScheme.DIRECT, EliminationObjective.COEFFICIENTS_FIRST, PointPattern.RATIONAL_GRID, ExactDomain.FINITE_TABLE, "lane_table_2"),
        make_frontier(FrontierKind.FINITE_STRUCTURE, 3, 3, (), SymmetryMode.NONE, CompositionScheme.DIRECT, EliminationObjective.MIXED, PointPattern.RATIONAL_GRID, ExactDomain.FINITE_TABLE, "lane_table_3"),
        make_frontier(FrontierKind.FINITE_STRUCTURE, 6, 6, (), SymmetryMode.NONE, CompositionScheme.DIRECT, EliminationObjective.MIXED, PointPattern.RATIONAL_GRID, ExactDomain.FINITE_TABLE, "lane_table_6"),
    )


def initial_frontiers(specification: ProblemSpec) -> tuple[Frontier, ...]:
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        return _initial_planar_frontiers()
    if specification.kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
        return _initial_group_frontiers()
    return _initial_algebraic_frontiers()


def mutate_frontier(
    base: Frontier | None,
    known_signatures: Iterable[str],
    count: int = 5,
    reason: str = "",
) -> tuple[Frontier, ...]:
    known = set(known_signatures)
    produced: list[Frontier] = []
    produced_signatures: set[str] = set()
    kind_cycle = tuple(FrontierKind)
    symmetry_cycle = tuple(SymmetryMode)
    composition_cycle = tuple(CompositionScheme)
    elimination_cycle = tuple(EliminationObjective)
    point_cycle = tuple(PointPattern)
    domain_cycle = (ExactDomain.RATIONAL, ExactDomain.ALGEBRAIC, ExactDomain.MODULAR_PRESCREEN)
    actions = (
        "strengthen_exact_domain_conversion",
        "add_denominator_equations",
        "change_elimination_order",
        "change_term_order",
        "change_support_sets",
        "change_symmetry_constraints",
        "expand_degree_extent",
        "expand_coefficient_extent",
        "change_collision_point_pattern",
        "switch_solver_route",
        "add_independent_exact_checks",
    )
    seed_kind = base.kind if base is not None else FrontierKind.SUPPORT_MUTATION
    seed_degree = base.degree_extent if base is not None else 1
    seed_coefficient = base.coefficient_extent if base is not None else 1
    seed_symmetry = base.symmetry_mode if base is not None else SymmetryMode.NONE
    seed_composition = base.composition_scheme if base is not None else CompositionScheme.IDENTITY_PERTURBATION
    seed_elimination = base.elimination_objective if base is not None else EliminationObjective.MIXED
    seed_pattern = base.point_pattern if base is not None else PointPattern.RATIONAL_GRID
    seed_domain = base.exact_domain if base is not None else ExactDomain.RATIONAL
    lineage = ((base.unique_signature if base is not None else "root"), reason)
    for index in itertools.count(1):
        variant = index % 11
        degree = max(1, seed_degree + (index // 5) + (1 if variant in (6, 4, 10) else 0))
        coefficient = max(1, seed_coefficient + (1 if variant in (7, 10) else 0) + index // 17)
        if variant == 0:
            support = total_degree_support(degree)
        elif variant == 1:
            support = sparse_support(degree)
        elif variant == 2:
            support = weighted_support(degree + 1, (1 + index % 3, 1 + (index + 1) % 3))
        elif variant == 3:
            support = homogeneous_layer_support(degree)
        else:
            support = tuple(sorted(set(sparse_support(degree)) | set(weighted_support(degree + 1, (2, 1)))))
        kind = kind_cycle[(kind_cycle.index(seed_kind) + index) % len(kind_cycle)]
        symmetry = symmetry_cycle[(symmetry_cycle.index(seed_symmetry) + index) % len(symmetry_cycle)]
        composition = composition_cycle[(composition_cycle.index(seed_composition) + index) % len(composition_cycle)]
        elimination = elimination_cycle[(elimination_cycle.index(seed_elimination) + index) % len(elimination_cycle)]
        pattern = point_cycle[(point_cycle.index(seed_pattern) + index) % len(point_cycle)]
        domain = domain_cycle[(domain_cycle.index(seed_domain) + index) % len(domain_cycle)] if seed_domain in domain_cycle else ExactDomain.RATIONAL
        extra = {
            "repair_action": actions[index % len(actions)],
            "solver_route": ("solve", "groebner", "resultant", "sequential")[index % 4],
            "term_order": ("lex", "grlex", "grevlex")[index % 3],
            "point_bound": max(1, coefficient),
            "denominator_guard": "strict",
            "independent_check_level": 2 + index % 3,
        }
        if domain == ExactDomain.MODULAR_PRESCREEN:
            extra["prime"] = (2, 3, 5, 7)[index % 4]
            pattern = PointPattern.FINITE_FIELD
        frontier = make_frontier(
            kind,
            degree,
            coefficient,
            _paired_support(support),
            symmetry,
            composition,
            elimination,
            pattern,
            domain,
            f"lane_mutation_{index}",
            tuple(str(item) for item in lineage),
            extra,
        )
        if frontier.unique_signature not in known and frontier.unique_signature not in produced_signatures:
            produced.append(frontier)
            produced_signatures.add(frontier.unique_signature)
            if len(produced) >= count:
                return tuple(produced)
    return tuple(produced)
