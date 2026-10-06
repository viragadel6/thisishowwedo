from __future__ import annotations

from typing import Any

PRESETS: tuple[dict[str, Any], ...] = (
    {
        "identifier": "algebraic_pole_refutation",
        "label": "Identity with pole exclusions",
        "query": "refute the identity x/(x-1) = 1",
        "problem_kind": "algebraic_identity_counterassignment",
        "description": "an exact counterassignment that avoids the pole of the left hand side",
        "expected": "counterexample",
        "budget": {"time_seconds": 20, "max_frontier_visits": 60, "execution_timeout_seconds": 8},
    },
    {
        "identifier": "algebraic_polynomial_refutation",
        "label": "Polynomial identity refutation",
        "query": "find a counterexample for x^2 + 1 = x^2",
        "problem_kind": "algebraic_identity_counterassignment",
        "description": "a polynomial identity that fails over the rationals",
        "expected": "counterexample",
        "budget": {"time_seconds": 20, "max_frontier_visits": 60, "execution_timeout_seconds": 8},
    },
    {
        "identifier": "constrained_integer_assignment",
        "label": "Constrained integer assignment",
        "query": "for all nonnegative integers n, n + 1 = n",
        "problem_kind": "algebraic_identity_counterassignment",
        "description": "the candidate assignment must respect the declared integer and sign constraints",
        "expected": "counterexample",
        "budget": {"time_seconds": 20, "max_frontier_visits": 60, "execution_timeout_seconds": 8},
    },
    {
        "identifier": "symbolic_identity_proof",
        "label": "Symbolically true identity",
        "query": "prove that sin(x)^2 + cos(x)^2 = 1 for every real x",
        "problem_kind": "algebraic_identity_counterassignment",
        "description": "the engine proves the identity symbolically and reports no counterassignment",
        "expected": "symbolic_proof",
        "budget": {"time_seconds": 20, "max_frontier_visits": 60, "execution_timeout_seconds": 8},
    },
    {
        "identifier": "finite_group_square",
        "label": "Finite group countermodel",
        "query": "In every finite group, x^2 = e",
        "problem_kind": "finite_group_identity_countermodel",
        "description": "a complete operation table that violates the claimed law",
        "expected": "counterexample",
        "budget": {"time_seconds": 20, "max_frontier_visits": 120, "execution_timeout_seconds": 12, "max_group_order": 6},
    },
    {
        "identifier": "finite_group_commuting",
        "label": "Nonabelian group countermodel",
        "query": "In every finite group of order at most 8, x*y = y*x",
        "problem_kind": "finite_group_identity_countermodel",
        "description": "a nonabelian group within the declared order bound",
        "expected": "counterexample",
        "budget": {"time_seconds": 25, "max_frontier_visits": 160, "execution_timeout_seconds": 15, "max_group_order": 8},
    },
    {
        "identifier": "planar_jacobian_collision",
        "label": "Planar Jacobian determinant collision",
        "query": "refute the two dimensional Jacobian conjecture",
        "problem_kind": "planar_constant_determinant_collision",
        "description": "searches for a polynomial map with constant nonzero determinant that collides",
        "expected": "exhaustion",
        "budget": {"time_seconds": 25, "max_frontier_visits": 24, "execution_timeout_seconds": 10},
    },
)
