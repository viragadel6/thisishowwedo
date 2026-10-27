"""Fast regression tests for the exact planar Jacobian search.

These pin down the facts that the written report relies on, in a few seconds:

*  the fibre cardinality used for injectivity is the quotient dimension, and it
   differs from the naive count of distinct x-roots (the mistake of version 1);
*  the degree two family, the cubic homogeneous family and the one-linear-form
   family all have det J a nonzero constant AND a verified polynomial inverse;
*  the near-miss maps really collide and really have a non-constant determinant.
"""

from __future__ import annotations

import sympy as sp

from scripts.jc_planar_search import (
    collision,
    det_jacobian,
    fibre,
    lane_arbitrary_degree,
    lane_cubic_homogeneous,
    lane_cubic_linear,
    lane_degree_two,
    lane_near_misses,
)

x, y = sp.symbols("x y")


def test_fibre_count_is_quotient_dimension_not_distinct_roots():
    # (x^2, y^2) at (1,1) has four points over C but only two distinct x values
    P, Q = x**2, y**2
    f = fibre(P, Q, (1, 1))
    assert f["points"] == 4
    assert f["lower_bound_distinct_x"] == 2


def test_degree_two_family_is_injective():
    r = lane_degree_two()
    assert sp.simplify(r["generic_determinant"]) == 1
    assert r["generic_inverse_checks"] == (0, 0)
    assert sp.simplify(r["member_determinant"]) == 1
    assert r["member_fibre"] == 1
    assert r["member_inverse_verified"]
    assert r["all_branches_invertible"]


def test_cubic_homogeneous_family_is_injective():
    r = lane_cubic_homogeneous()
    assert sp.simplify(r["closed_form_determinant_with_condition"]) == 1
    assert r["closed_form_inverse_checks"] == (0, 0)
    assert sp.simplify(r["member_determinant"]) == 1
    assert r["member_inverse_verified"]
    assert r["linear_relations_in_basis"]


def test_cubic_linear_formula_and_cases():
    r = lane_cubic_linear()
    assert r["formula_verified"]
    assert r["identity_on_nilpotency_locus"] == 0
    assert r["all_cases_invertible"]
    assert r["keller_equals_nilpotent"]


def test_one_linear_form_every_degree_is_bijective():
    r = lane_arbitrary_degree(max_degree=8)
    assert r["all_verified"]


def test_near_misses_collide_with_nonconstant_determinant():
    r = lane_near_misses()
    for record in r["records"]:
        assert record["collision"] is not None
        assert collision(record["P"], record["Q"],
                         (1, 0), record["collision"][0])["verified"]
        J = det_jacobian(record["P"], record["Q"])
        assert sp.Poly(J, x, y).total_degree() >= 1
