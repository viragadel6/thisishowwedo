from __future__ import annotations

import itertools
from typing import Iterable, Mapping, Sequence

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
            if first + second > bound:
                continue
            if weights[0] * first + weights[1] * second <= bound:
                result.append((first, second))
    return tuple(sorted(set(result), key=lambda item: (item[0] + item[1], item[0], item[1])))


def sparse_support(degree: int) -> tuple[tuple[int, int], ...]:
    extent = max(0, int(degree))
    base = {(0, 0), (1, 0), (0, 1)}
    for power in range(2, extent + 1):
        base.add((power, 0))
        base.add((0, power))
        base.add((power - 1, 1))
        base.add((1, power - 1))
    return tuple(sorted(base, key=lambda item: (item[0] + item[1], item[0], item[1])))


def homogeneous_layer_support(degree: int) -> tuple[tuple[int, int], ...]:
    value = max(1, degree)
    return tuple((first, value - first) for first in range(value, -1, -1))


def _clamp_support(support: Sequence[tuple[int, int]], degree_extent: int) -> tuple[tuple[int, int], ...]:
    bound = max(0, int(degree_extent))
    kept = []
    for monomial in support:
        first, second = int(monomial[0]), int(monomial[1])
        if first < 0 or second < 0:
            continue
        if first + second > bound:
            continue
        kept.append((first, second))
    return tuple(sorted(set(kept), key=lambda item: (item[0] + item[1], item[0], item[1])))


def _support_variant(variant: int, degree: int) -> tuple[tuple[int, int], ...]:
    if variant == 0:
        return total_degree_support(degree)
    if variant == 1:
        return sparse_support(degree)
    if variant == 2:
        return weighted_support(degree, (1, 2))
    if variant == 3:
        return homogeneous_layer_support(degree)
    return tuple(sorted(set(sparse_support(degree)) | set(weighted_support(degree, (2, 1))), key=lambda item: (item[0] + item[1], item[0], item[1])))


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
    clamped = tuple(_clamp_support(support, degree_extent) for support in support_sets)
    payload = _approach_payload(
        kind,
        degree_extent,
        coefficient_extent,
        clamped,
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
        support_sets=clamped,
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


def _split_supports(
    first_support: tuple[tuple[int, int], ...],
    second_support: tuple[tuple[int, int], ...],
) -> tuple[tuple[tuple[int, int], ...], ...]:
    return (first_support, second_support)


def _initial_planar_frontiers() -> tuple[Frontier, ...]:
    items: list[Frontier] = []
    items.append(make_frontier(FrontierKind.FULL_POLYNOMIAL, 1, 1, _paired_support(total_degree_support(1)), SymmetryMode.NONE, CompositionScheme.DIRECT, EliminationObjective.COEFFICIENTS_FIRST, PointPattern.RATIONAL_GRID, ExactDomain.RATIONAL, "lane_full"))
    items.append(make_frontier(FrontierKind.SPARSE_POLYNOMIAL, 2, 1, _paired_support(sparse_support(2)), SymmetryMode.NONE, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.MIXED, PointPattern.AXIS_PAIR, ExactDomain.RATIONAL, "lane_sparse"))
    items.append(make_frontier(FrontierKind.COLLISION_INTERPOLATION, 2, 1, _paired_support(weighted_support(3, (1, 2))), SymmetryMode.NONE, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.COLLISION_FIRST, PointPattern.DIAGONAL_PAIR, ExactDomain.RATIONAL, "lane_collision"))
    items.append(make_frontier(FrontierKind.DETERMINANT_FIRST, 2, 1, _paired_support(total_degree_support(2, False)), SymmetryMode.NONE, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.DETERMINANT_FIRST, PointPattern.ORIGIN_PAIR, ExactDomain.RATIONAL, "lane_determinant"))
    items.append(make_frontier(FrontierKind.HOMOGENEOUS_LAYER, 3, 1, _paired_support(homogeneous_layer_support(3)), SymmetryMode.NONE, CompositionScheme.LAYERED, EliminationObjective.DETERMINANT_FIRST, PointPattern.AXIS_PAIR, ExactDomain.RATIONAL, "lane_layer"))
    items.append(make_frontier(FrontierKind.SYMMETRY_ACTION, 2, 1, _split_supports(total_degree_support(2, False), sparse_support(2)), SymmetryMode.SWAP, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.MIXED, PointPattern.SWAPPED_PAIR, ExactDomain.RATIONAL, "lane_symmetry"))
    items.append(make_frontier(FrontierKind.COMPOSITION_PERTURBATION, 3, 1, _paired_support(sparse_support(3)), SymmetryMode.NONE, CompositionScheme.TRIANGULAR_COMPOSITION, EliminationObjective.MIXED, PointPattern.RATIONAL_GRID, ExactDomain.RATIONAL, "lane_composition"))
    items.append(make_frontier(FrontierKind.SUPPORT_MUTATION, 3, 1, _paired_support(weighted_support(3, (2, 1))), SymmetryMode.SIGN, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.MIXED, PointPattern.DIAGONAL_PAIR, ExactDomain.RATIONAL, "lane_support"))
    items.append(make_frontier(FrontierKind.FINITE_FIELD_PRESCREEN, 2, 1, _paired_support(sparse_support(2)), SymmetryMode.NONE, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.MIXED, PointPattern.FINITE_FIELD, ExactDomain.MODULAR_PRESCREEN, "lane_modular", extra_parameters={"prime": 2}))
    items.append(make_frontier(FrontierKind.ALGEBRAIC_POINT_COLLISION, 2, 1, _paired_support(sparse_support(2)), SymmetryMode.NONE, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.COLLISION_FIRST, PointPattern.ALGEBRAIC_GRID, ExactDomain.ALGEBRAIC, "lane_algebraic_point"))
    items.append(make_frontier(FrontierKind.ELIMINATION_ORDER, 2, 1, _paired_support(sparse_support(2)), SymmetryMode.NONE, CompositionScheme.IDENTITY_PERTURBATION, EliminationObjective.GROEBNER, PointPattern.RATIONAL_GRID, ExactDomain.RATIONAL, "lane_elimination", extra_parameters={"term_order": "lex"}))
    return tuple(items)


def _initial_algebraic_frontiers(specification: ProblemSpec) -> tuple[Frontier, ...]:
    extent = 2
    if specification.algebraic_identity is not None:
        extent = max(2, int(specification.algebraic_identity.search_extent))
    return (
        make_frontier(FrontierKind.ALGEBRAIC_ASSIGNMENT, 0, 0, (), SymmetryMode.NONE, CompositionScheme.DIRECT, EliminationObjective.COEFFICIENTS_FIRST, PointPattern.RATIONAL_GRID, ExactDomain.RATIONAL, "lane_assignment_0"),
        make_frontier(FrontierKind.ALGEBRAIC_ASSIGNMENT, 1, 1, (), SymmetryMode.NONE, CompositionScheme.DIRECT, EliminationObjective.COEFFICIENTS_FIRST, PointPattern.RATIONAL_GRID, ExactDomain.RATIONAL, "lane_assignment_1"),
        make_frontier(FrontierKind.ALGEBRAIC_ASSIGNMENT, extent, extent, (), SymmetryMode.NONE, CompositionScheme.DIRECT, EliminationObjective.MIXED, PointPattern.ALGEBRAIC_GRID, ExactDomain.ALGEBRAIC, "lane_assignment_2"),
    )


def _initial_group_frontiers(specification: ProblemSpec) -> tuple[Frontier, ...]:
    max_order = 6
    if specification.finite_group_identity is not None:
        max_order = max(1, int(specification.finite_group_identity.max_order))
    elif specification.order_bound is not None:
        max_order = max(1, int(specification.order_bound))
    orders = [order for order in (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 24) if order <= max_order]
    if not orders:
        orders = [max_order]
    if orders[-1] != max_order and max_order <= 64:
        orders.append(max_order)
    selected = sorted(set(orders))[-6:]
    items: list[Frontier] = []
    for order in selected:
        items.append(
            make_frontier(
                FrontierKind.FINITE_STRUCTURE,
                order,
                order,
                (),
                SymmetryMode.NONE,
                CompositionScheme.DIRECT,
                EliminationObjective.COEFFICIENTS_FIRST,
                PointPattern.RATIONAL_GRID,
                ExactDomain.FINITE_TABLE,
                "lane_table_" + str(order),
                extra_parameters={"max_order": order, "group_order": order},
            )
        )
    return tuple(items)


def initial_frontiers(specification: ProblemSpec) -> tuple[Frontier, ...]:
    if specification.kind == ProblemKind.PLANAR_CONSTANT_DETERMINANT_COLLISION:
        return _initial_planar_frontiers()
    if specification.kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
        return _initial_group_frontiers(specification)
    return _initial_algebraic_frontiers(specification)


def _allowed_domains(kind: ProblemKind | None) -> tuple[ExactDomain, ...]:
    if kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
        return (ExactDomain.FINITE_TABLE,)
    if kind == ProblemKind.ALGEBRAIC_IDENTITY_COUNTERASSIGNMENT:
        return (ExactDomain.RATIONAL, ExactDomain.ALGEBRAIC)
    return (ExactDomain.RATIONAL, ExactDomain.ALGEBRAIC, ExactDomain.MODULAR_PRESCREEN)


_DEFAULT_MUTATION_ACTIONS = (
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
_SOLVER_ROUTES = ("solve", "groebner", "resultant", "sequential")
_TERM_ORDERS = ("lex", "grlex", "grevlex")


def mutate_frontier(
    base: Frontier | None,
    known_signatures: Iterable[str],
    count: int = 5,
    reason: str = "",
    kind: ProblemKind | None = None,
    actions: Sequence[str] = (),
) -> tuple[Frontier, ...]:
    known = set(known_signatures)
    produced: list[Frontier] = []
    produced_signatures: set[str] = set()
    action_list = tuple(actions) if actions else _DEFAULT_MUTATION_ACTIONS
    kind_cycle = tuple(FrontierKind)
    symmetry_cycle = tuple(SymmetryMode)
    composition_cycle = tuple(CompositionScheme)
    elimination_cycle = tuple(EliminationObjective)
    point_cycle = tuple(PointPattern)
    allowed_domains = _allowed_domains(kind)
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
        action = action_list[(index - 1) % len(action_list)]
        variant = index % 5
        degree = max(1, seed_degree + (1 if action == "expand_degree_extent" else 0) + index // 6)
        coefficient = max(1, seed_coefficient + (1 if action == "expand_coefficient_extent" else 0) + index // 23)
        support = _support_variant(variant, degree)
        kind_next = kind_cycle[(kind_cycle.index(seed_kind) + index) % len(kind_cycle)]
        symmetry = symmetry_cycle[(symmetry_cycle.index(seed_symmetry) + index) % len(symmetry_cycle)]
        composition = composition_cycle[(composition_cycle.index(seed_composition) + index) % len(composition_cycle)]
        elimination = elimination_cycle[(elimination_cycle.index(seed_elimination) + index) % len(elimination_cycle)]
        pattern = point_cycle[(point_cycle.index(seed_pattern) + index) % len(point_cycle)]
        if kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
            kind_next = FrontierKind.FINITE_STRUCTURE
            symmetry = SymmetryMode.NONE
            composition = CompositionScheme.DIRECT
            pattern = PointPattern.RATIONAL_GRID
            elimination = elimination_cycle[(elimination_cycle.index(seed_elimination) + index) % len(elimination_cycle)]
        domain_index = (allowed_domains.index(seed_domain) + index) % len(allowed_domains) if seed_domain in allowed_domains else 0
        domain = allowed_domains[domain_index]
        if action == "strengthen_exact_domain_conversion" and ExactDomain.RATIONAL in allowed_domains:
            domain = ExactDomain.RATIONAL
        if domain == ExactDomain.MODULAR_PRESCREEN:
            pattern = PointPattern.FINITE_FIELD
        extra = {
            "repair_action": action,
            "solver_route": _SOLVER_ROUTES[index % len(_SOLVER_ROUTES)],
            "term_order": _TERM_ORDERS[index % len(_TERM_ORDERS)],
            "point_bound": max(1, coefficient),
            "denominator_guard": "strict",
            "independent_check_level": 2 + index % 3,
        }
        if action == "add_denominator_equations":
            extra["denominator_equations"] = True
        if action == "add_independent_exact_checks":
            extra["independent_check_level"] = 3 + index % 3
        if domain == ExactDomain.MODULAR_PRESCREEN:
            extra["prime"] = (2, 3, 5, 7)[index % 4]
        if kind == ProblemKind.FINITE_GROUP_IDENTITY_COUNTERMODEL:
            extra["max_order"] = max(1, degree)
            extra["group_order"] = max(1, degree)
        frontier = make_frontier(
            kind_next,
            degree,
            coefficient,
            _paired_support(support),
            symmetry,
            composition,
            elimination,
            pattern,
            domain,
            "lane_mutation_" + str(index),
            tuple(str(item) for item in lineage),
            extra,
        )
        if frontier.unique_signature not in known and frontier.unique_signature not in produced_signatures:
            produced.append(frontier)
            produced_signatures.add(frontier.unique_signature)
            if len(produced) >= count:
                return tuple(produced)
    return tuple(produced)
