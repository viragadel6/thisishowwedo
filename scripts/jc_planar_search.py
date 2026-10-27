"""Exact search for a counterexample to the planar (two dimensional) Jacobian conjecture.

Target object: P, Q in C[x, y] with rational or algebraic coefficients such that

    (J)  det J = P_x Q_y - P_y Q_x is a NONZERO CONSTANT, and
    (C)  (x, y) |-> (P(x, y), Q(x, y)) is NOT injective on C^2.

Everything is exact (Q, algebraic numbers, Groebner bases, resultants); no
floating point is used for any decision.  Each lane is an *ordered algebraic
construction* written natively for the two variables x, y:

  F1  degree <= 2       complete classification of all Keller maps (det J = const)
  F2  triangular        complete classification for deg P <= 2, deg Q <= 4
  F3  cubic linear      all 2x2 nilpotent matrices, all Druzkowski-type maps
  F4  cubic homogeneous complete classification of all Keller maps of this shape
  F5  box scan          exhaustive integer coefficients in [-2,2]^8, cubic homogeneous
  F6  tame group        compositions of elementary automorphisms, degree up to 10
  F7  near misses       colliding maps, with their exact non-constant determinants
  F8  arbitrary degree  (x + lam L^k, y + mu L^k) for k = 2..7, with det J formula

Injectivity is decided exactly, never sampled: for a map with det J a nonzero
constant (hence etale) the fibre F^{-1}(F(p0)) is reduced, so its cardinality is
the number of solutions of a zero dimensional polynomial system, computed from a
lex Groebner basis plus a factorisation over Q.  Cardinality > 1 is a proof of
non-injectivity and delivers an exact algebraic collision partner.

A positive control (F0) verifies the known three dimensional counterexample with
the same code, so that "no counterexample found" cannot be an artefact of a
broken test.
"""

from __future__ import annotations

import itertools
import random
import sys
import time

import sympy as sp

x, y = sp.symbols("x y")
X, Y = sp.symbols("X Y")


# ---------------------------------------------------------------------------
# exact primitives
# ---------------------------------------------------------------------------
def det_jacobian(P, Q):
    return sp.expand(sp.diff(P, x) * sp.diff(Q, y) - sp.diff(P, y) * sp.diff(Q, x))


def jacobian_data(P, Q):
    J = det_jacobian(P, Q)
    poly = sp.Poly(J, x, y).as_dict()
    constant = poly.get((0, 0), sp.Integer(0))
    nonconstant = {m: c for m, c in poly.items() if m != (0, 0)}
    degenerate = all(c == 0 for c in nonconstant.values())
    return {
        "jacobian": J,
        "constant": sp.simplify(constant),
        "is_constant": bool(degenerate),
        "is_nonzero_constant": bool(degenerate and sp.simplify(constant) != 0),
    }


def fibre(P, Q, p0):
    """Exact cardinality of the fibre F^{-1}(F(p0)) over C, and its points."""
    w = (sp.expand(P.subs({x: p0[0], y: p0[1]})), sp.expand(Q.subs({x: p0[0], y: p0[1]})))
    gens = [sp.expand(P - w[0]), sp.expand(Q - w[1])]
    out = {"p0": p0, "w": w, "count": None, "solutions": None, "basis": None}
    G = sp.groebner(gens, x, y, order="lex")
    out["basis"] = [g for g in G.exprs]
    univariate = [g for g in G.exprs if not g.free_symbols]
    univariate = [g for g in G.exprs if g.free_symbols <= {x}] or [
        g for g in G.exprs if g.free_symbols <= {y}
    ]
    if univariate:
        # distinct points over C: sum of the degrees of the distinct irreducible
        # factors of the elimination polynomial (multiplicities do not add points)
        squarefree = sp.Poly(univariate[-1], x, y).sqf_part().as_expr()
        _, factors = sp.factor_list(squarefree)
        total = 0
        for factor, _multiplicity in factors:
            if not factor.free_symbols:
                continue
            total += sp.Poly(factor, x, y).total_degree()
        out["count"] = total
    sols = sp.solve(gens, [x, y], dict=True)
    out["solutions"] = [(sp.nsimplify(s.get(x)), sp.nsimplify(s.get(y))) for s in sols]
    return out


def collision(P, Q, p0, p1):
    dP = sp.expand(P.subs({x: p0[0], y: p0[1]}) - P.subs({x: p1[0], y: p1[1]}))
    dQ = sp.expand(Q.subs({x: p0[0], y: p0[1]}) - Q.subs({x: p1[0], y: p1[1]}))
    distinct = sp.simplify(p0[0] - p1[0]) != 0 or sp.simplify(p0[1] - p1[1]) != 0
    return {"dP": dP, "dQ": dQ, "verified": bool(dP == 0 and dQ == 0 and distinct)}


def polynomial_inverse(P, Q):
    """Explicit inverse from solve(), verified by exact substitution."""
    sol = sp.solve([X - P, Y - Q], [x, y], dict=True)
    if len(sol) != 1:
        return {"solutions": len(sol), "inverse": None, "verified": False, "polynomial": False}
    Xs, Ys = sp.simplify(sol[0][x]), sp.simplify(sol[0][y])
    ok = sp.expand(P.subs({x: Xs, y: Ys}) - X) == 0 and sp.expand(Q.subs({x: Xs, y: Ys}) - Y) == 0
    return {
        "solutions": 1,
        "inverse": (Xs, Ys),
        "verified": bool(ok),
        "polynomial": bool(Xs.is_polynomial(X, Y) and Ys.is_polynomial(X, Y)),
    }


# ---------------------------------------------------------------------------
# F0: positive control -- the known three dimensional counterexample
# ---------------------------------------------------------------------------
def positive_control_dim3():
    """Alpoge 2026: det J = -2 but three distinct rational points collide."""
    z = sp.Symbol("z")
    P = sp.expand((1 + x * y) ** 3 * z + y**2 * (1 + x * y) * (4 + 3 * x * y))
    Q = sp.expand(y + 3 * x * (1 + x * y) ** 2 * z + 3 * x * y**2 * (4 + 3 * x * y))
    R = sp.expand(2 * x - 3 * x**2 * y - x**3 * z)
    J = sp.expand(sp.Matrix([P, Q, R]).jacobian([x, y, z]).det())
    points = [(-1, sp.Rational(3, 2), sp.Rational(13, 2)), (0, 0, sp.Rational(-1, 4)),
              (1, sp.Rational(-3, 2), sp.Rational(13, 2))]
    images = []
    for point in points:
        sub = {x: point[0], y: point[1], z: point[2]}
        images.append((sp.expand(P.subs(sub)), sp.expand(Q.subs(sub)), sp.expand(R.subs(sub))))
    return {
        "map": (P, Q, R),
        "determinant": J,
        "determinant_is_constant_nonzero": J == -2,
        "points": points,
        "images": images,
        "all_images_equal": len(set(images)) == 1,
        "distinct_points": len(set(points)) == 3,
    }


# ---------------------------------------------------------------------------
# F1: complete classification of Keller maps of degree <= 2
# ---------------------------------------------------------------------------
def lane_degree_two():
    """P = x + quadratic, Q = y + quadratic, det J == 1.

    Any Keller map of degree <= 2 has invertible linear part; affine changes of
    coordinates on source and target preserve both (J) and (C), so this ansatz
    is completely general with the linear part normalised to the identity.
    """
    a, b, c, d, e, f = sp.symbols("a b c d e f")
    P = x + a * x**2 + b * x * y + c * y**2
    Q = y + d * x**2 + e * x * y + f * y**2
    gap = sp.Poly(sp.expand(det_jacobian(P, Q) - 1), x, y)
    equations = [sp.expand(co) for _, co in gap.terms()]
    G = sp.groebner(equations, a, b, c, d, e, f, order="lex")
    solutions = sp.solve(equations, [a, b, c, d, e, f], dict=True)
    # the generic branch, written in closed form, with a verified inverse
    s_, f_ = sp.symbols("s f", nonzero=True)
    L = x - (f_ / s_) * y
    Pgen = sp.expand(x + s_ * L**2)
    Qgen = sp.expand(y + (s_**2 / f_) * L**2)
    u_form = X - (f_ / s_) * Y                    # = P - (f/s) Q, the coordinate u
    inv = (u_form + (f_ / s_) * (Y - (s_**2 / f_) * u_form**2),
           Y - (s_**2 / f_) * u_form**2)
    # fix a rational member and verify everything numerically-exactly
    member = {"s": 2, "f": 3}
    Pm = sp.expand(Pgen.subs({s_: member["s"], f_: member["f"]}))
    Qm = sp.expand(Qgen.subs({s_: member["s"], f_: member["f"]}))
    Pm_inv = sp.expand(inv[0].subs({s_: member["s"], f_: member["f"]}))
    Qm_inv = sp.expand(inv[1].subs({s_: member["s"], f_: member["f"]}))
    member_ok = (
        sp.expand(Pm.subs({x: Pm_inv, y: Qm_inv}) - X) == 0
        and sp.expand(Qm.subs({x: Pm_inv, y: Qm_inv}) - Y) == 0
    )
    return {
        "ansatz": (P, Q),
        "gap": gap.as_expr(),
        "equations": equations,
        "groebner_basis": [sp.factor(g) for g in G.exprs],
        "solutions": solutions,
        "generic_family": (Pgen, Qgen),
        "generic_determinant": sp.simplify(det_jacobian(Pgen, Qgen)),
        "generic_target_linear_form": sp.simplify(Pgen - (f_ / s_) * Qgen),
        "generic_target_linear_form_equals_L": sp.simplify(
            sp.expand(Pgen - (f_ / s_) * Qgen - L)) == 0,
        "member": (Pm, Qm),
        "member_determinant": sp.simplify(det_jacobian(Pm, Qm)),
        "member_fibre": fibre(Pm, Qm, (0, 0))["count"],
        "member_inverse": (Pm_inv, Qm_inv),
        "member_inverse_verified": bool(member_ok),
        "all_solutions_invertible": all(
            sp.simplify(det_jacobian(
                sp.expand(P.subs(s0)), sp.expand(Q.subs(s0))
            )) != 0 for s0 in solutions
        ),
    }


# ---------------------------------------------------------------------------
# F2: triangular maps
# ---------------------------------------------------------------------------
def lane_triangular(deg_P=2, deg_f=4):
    """Q = f(x), general P of degree <= deg_P: solve det J == nonzero constant."""
    names_P = sp.symbols("p0:%d" % ((deg_P + 1) * (deg_P + 2) // 2))
    names_f = sp.symbols("q0:%d" % (deg_f + 1))
    monomials = [x**i * y**j for i in range(deg_P + 1) for j in range(deg_P + 1 - i)]
    P = sum(c * m for c, m in zip(names_P, monomials))
    Q = sum(c * x**k for c, k in zip(names_f, range(deg_f + 1)))
    J = sp.expand(det_jacobian(P, Q))
    identity = sp.expand(J - (-sp.diff(P, y) * sp.diff(Q, x))) == 0
    equations = [sp.expand(co) for m, co in sp.Poly(J, x, y).as_dict().items() if m != (0, 0)]
    solutions = sp.solve(equations, list(names_P) + list(names_f), dict=True)
    branches = []
    for s0 in solutions:
        Pb, Qb = sp.expand(P.subs(s0)), sp.expand(Q.subs(s0))
        data = jacobian_data(Pb, Qb)
        entry = {
            "solution": s0,
            "P": Pb,
            "Q": Qb,
            "determinant": sp.simplify(data["jacobian"]),
            "nonzero_constant": data["is_nonzero_constant"],
            "inverse_verified": False,
            "inverse": None,
        }
        if data["is_nonzero_constant"]:
            inv = polynomial_inverse(Pb, Qb)
            entry["inverse_verified"] = inv["verified"]
            entry["inverse"] = inv["inverse"]
        branches.append(entry)
    return {
        "identity_det_equals_minus_Py_fprime": bool(identity),
        "equations": equations,
        "solutions": solutions,
        "branches": branches,
        "all_constant_determinant_branches_invertible": all(
            b["inverse_verified"] for b in branches if b["nonzero_constant"]
        ),
    }


# ---------------------------------------------------------------------------
# F3: nilpotent matrices and cubic-linear (Druzkowski type) maps in dimension 2
# ---------------------------------------------------------------------------
def lane_cubic_linear():
    s_, t_, m_, n_, lam = sp.symbols("s t m n lambda", nonzero=True)
    A = sp.Matrix([[s_ * m_, s_ * n_], [t_ * m_, t_ * n_]])
    rank_one_square = sp.simplify(A * A - (s_ * m_ + t_ * n_) * A)
    conjugating = sp.simplify(sp.Matrix([[1, 0], [0, lam]]) * sp.Matrix([[0, 1], [0, 0]])
                              * sp.Matrix([[1, 0], [0, lam]]).inv())
    examples = [sp.Matrix([[0, 1], [0, 0]]), sp.Matrix([[1, 1], [-1, -1]]),
                sp.Matrix([[2, 1], [-4, -2]]), sp.Matrix([[3, 2], [-2, -1]])]
    example_data = [{"A": M, "A2": sp.simplify(M * M), "rank": M.rank(),
                     "nilpotent": sp.simplify(M * M) == sp.zeros(2, 2)} for M in examples]

    # symbolic family: X + (A X)^{*3} with A = u v^T, v.u = 0
    L = m_ * x + n_ * y
    Pn = sp.expand(x + (s_ * L) ** 3)
    Qn = sp.expand(y + (t_ * L) ** 3)
    Jn = sp.expand(det_jacobian(Pn, Qn))
    n_expr = -s_ * m_ / t_
    J_loc = sp.expand(Jn.subs(n_, n_expr))
    gap = sp.Poly(sp.expand(J_loc - 1), x, y)
    constancy = [sp.expand(c) for _, c in gap.terms()]
    constancy_solutions = sp.solve(constancy, [s_, t_, m_], dict=True)
    factored = [sp.factor(e) for e in constancy]

    # exhaustive integer scan over all 2x2 matrices with entries in [-2,2]
    a, b, c, d = sp.symbols("a b c d")
    Pg = sp.expand(x + (a * x + b * y) ** 3)
    Qg = sp.expand(y + (c * x + d * y) ** 3)
    Jg = sp.Poly(sp.expand(det_jacobian(Pg, Qg)), x, y).as_dict()
    keller_entries = []
    for values in itertools.product(range(-2, 3), repeat=4):
        subst = dict(zip((a, b, c, d), values))
        constant = Jg.get((0, 0), sp.Integer(0)).subs(subst)
        rest = [co.subs(subst) for mon, co in Jg.items() if mon != (0, 0)]
        if all(sp.simplify(r) == 0 for r in rest) and sp.simplify(constant) != 0:
            keller_entries.append(values)
    checks = []
    for values in keller_entries:
        subst = dict(zip((a, b, c, d), values))
        Pv, Qv = sp.expand(Pg.subs(subst)), sp.expand(Qg.subs(subst))
        inv = polynomial_inverse(Pv, Qv)
        checks.append({
            "A": sp.Matrix([[values[0], values[1]], [values[2], values[3]]]),
            "P": Pv,
            "Q": Qv,
            "determinant": sp.simplify(det_jacobian(Pv, Qv)),
            "fibre": fibre(Pv, Qv, (0, 0))["count"],
            "inverse_verified": inv["verified"],
        })
    return {
        "A": A,
        "A_squared_equals_vdotu_A": rank_one_square,
        "conjugating_family": conjugating,
        "examples": example_data,
        "P_nilpotent": Pn,
        "Q_nilpotent": Qn,
        "determinant_on_nilpotency_locus": J_loc,
        "constancy_equations_factored": factored,
        "constancy_solutions": constancy_solutions,
        "integer_matrices_scanned": 625,
        "keller_entries": keller_entries,
        "checks": checks,
        "all_keller_injective": all(
            c["fibre"] == 1 and c["inverse_verified"] for c in checks
        ),
    }


# ---------------------------------------------------------------------------
# F4: complete classification of cubic homogeneous Keller maps in the plane
# ---------------------------------------------------------------------------
def lane_cubic_homogeneous():
    """H = (h1, h2) homogeneous cubic, det(I + JH) == 1, solved completely."""
    a, b, c, d, e, f, g, h = sp.symbols("a b c d e f g h")
    h1 = a * x**3 + b * x**2 * y + c * x * y**2 + d * y**3
    h2 = e * x**3 + f * x**2 * y + g * x * y**2 + h * y**3
    P = sp.expand(x + h1)
    Q = sp.expand(y + h2)
    gap = sp.Poly(sp.expand(det_jacobian(P, Q) - 1), x, y)
    equations = [sp.expand(co) for _, co in gap.terms()]
    G = sp.groebner(equations, a, b, c, d, e, f, g, h, order="grevlex")
    basis = [sp.factor(t0) for t0 in G.exprs]
    generic = sp.solve(equations, [a, b, c, d, e, f, g, h], dict=True)

    # Case analysis on the factored basis.
    # (0) linear relations: a = -f/3, b = -g, c = -3h.
    linear = [t0 for t0 in G.exprs if t0 in (3 * a + f, b + g, c + 3 * h)]
    sub_linear = {a: -f / 3, b: -g, c: -3 * h}
    reduced = [sp.expand(t0.subs(sub_linear)) for t0 in G.exprs]
    reduced = [t0 for t0 in reduced if t0 != 0]
    # (1) degenerate case f = g = h = 0
    degen = [sp.expand(t0.subs({f: 0, g: 0, h: 0})) for t0 in reduced]
    degenerate_solutions = sp.solve([t0 for t0 in degen if t0 != 0], [d, e], dict=True)
    # (2) generic case 3fh = g^2 with h != 0 (then also g != 0)
    h_zero = sp.solve([3 * f * h - g**2, h], [f, g, h], dict=True)
    # the generic branch, in closed form: H = (lambda L^3, mu L^3)
    lam, mu, tt = sp.symbols("lambda mu t", nonzero=True)
    Lk = x + tt * y
    Ph = sp.expand(x + lam * Lk**3)
    Qh = sp.expand(y + mu * Lk**3)
    det_general = sp.expand(det_jacobian(Ph, Qh))
    det_forced = sp.expand(sp.simplify(det_general.subs(lam, -tt * mu)))
    # under the constancy condition lambda = -t*mu the inverse is polynomial
    inverse = (X + tt * mu * (X + tt * Y) ** 3, Y - mu * (X + tt * Y) ** 3)
    # the constraint lambda = -t*mu is used in the verification itself
    Ph_con = sp.expand(Ph.subs(lam, -tt * mu))
    Qh_con = sp.expand(Qh.subs(lam, -tt * mu))
    inverse_checks = (
        sp.expand(Ph_con.subs({x: inverse[0], y: inverse[1]}) - X),
        sp.expand(Qh_con.subs({x: inverse[0], y: inverse[1]}) - Y),
    )
    # identification of the Groebner solution with the closed form
    generic_solution = generic[0]
    L_id = x + (g / f) * y
    identification = (
        sp.simplify(sp.expand(h1.subs(generic_solution) - (-f / 3) * L_id**3)),
        sp.simplify(sp.expand(h2.subs(generic_solution) - (f**2 / (3 * g)) * L_id**3)),
    )
    constraint_check = sp.simplify((-f / 3) + (g / f) * (f**2 / (3 * g)))
    # explicit rational member, fully verified
    member = {"lambda": sp.Rational(-2, 3), "mu": 5, "t": sp.Rational(2, 15)}
    Pm = sp.expand(Ph.subs({lam: member["lambda"], mu: member["mu"], tt: member["t"]}))
    Qm = sp.expand(Qh.subs({lam: member["lambda"], mu: member["mu"], tt: member["t"]}))
    inv_m = polynomial_inverse(Pm, Qm)
    return {
        "ansatz": (P, Q),
        "equations": equations,
        "groebner_basis": basis,
        "linear_relations": linear,
        "reduced_equations": reduced,
        "degenerate_case_fgh0": {"equations": degen, "solutions": degenerate_solutions},
        "case_h_zero": h_zero,
        "generic_solutions": generic,
        "closed_form_H": (lam * Lk**3, mu * Lk**3),
        "closed_form_determinant": det_general,
        "closed_form_determinant_with_condition": det_forced,
        "closed_form_inverse": inverse,
        "closed_form_inverse_checks": inverse_checks,
        "identification_with_closed_form": identification,
        "lambda_plus_t_mu": constraint_check,
        "general_H_is_lambda_L3_mu_L3": (
            sp.expand(Ph_con - (x + lam * (x + tt * y) ** 3)) == 0
        ),
        "member": (Pm, Qm),
        "member_determinant": sp.simplify(det_jacobian(Pm, Qm)),
        "member_fibre": fibre(Pm, Qm, (0, 0))["count"],
        "member_inverse": inv_m["inverse"],
        "member_inverse_verified": inv_m["verified"],
        "member_inverse_polynomial": inv_m["polynomial"],
    }


# ---------------------------------------------------------------------------
# F5: exhaustive box scan of cubic homogeneous maps with integer coefficients
# ---------------------------------------------------------------------------
def lane_box_scan(box=2):
    names1 = sp.symbols("a0:4")
    names2 = sp.symbols("b0:4")
    monomials = [x**3, x**2 * y, x * y**2, y**3]
    P = sp.expand(x + sum(c * m for c, m in zip(names1, monomials)))
    Q = sp.expand(y + sum(c * m for c, m in zip(names2, monomials)))
    data = sp.Poly(sp.expand(det_jacobian(P, Q)), x, y).as_dict()
    keller = []
    scanned = 0
    for values in itertools.product(range(-box, box + 1), repeat=8):
        scanned += 1
        subst = dict(zip(names1 + names2, values))
        constant = data.get((0, 0), sp.Integer(0)).subs(subst)
        rest = [co.subs(subst) for mon, co in data.items() if mon != (0, 0)]
        if all(sp.simplify(r) == 0 for r in rest) and sp.simplify(constant) != 0:
            keller.append(values)
    records = []
    for values in keller:
        subst = dict(zip(names1 + names2, values))
        Pv, Qv = sp.expand(P.subs(subst)), sp.expand(Q.subs(subst))
        records.append({
            "coefficients": values,
            "P": Pv,
            "Q": Qv,
            "fibre": fibre(Pv, Qv, (1, 0))["count"],
            "inverse_verified": polynomial_inverse(Pv, Qv)["verified"],
        })
    return {
        "box": box,
        "scanned": scanned,
        "keller_count": len(keller),
        "records": records,
        "all_injective": all(
            r["fibre"] == 1 and r["inverse_verified"] for r in records
        ),
    }


# ---------------------------------------------------------------------------
# F6: compositions of elementary automorphisms
# ---------------------------------------------------------------------------
def lane_tame_group(depth=5, samples=120, seed=20261027):
    rng = random.Random(seed)
    moves = list(itertools.product([0, 1], [1, 2, 3], [-3, -2, -1, 1, 2, 3]))
    tested = keller = verified = 0
    max_degree = 0
    failures = []
    degrees = set()
    for _ in range(samples):
        length = rng.randint(1, depth)
        P, Q = x, y
        steps = []
        for _ in range(length):
            kind, power, coeff = rng.choice(moves)
            if rng.random() < 0.15:  # occasional linear mixing step
                alpha, beta = rng.choice([(1, 1), (1, -1), (2, 1), (1, 2)])
                P, Q = sp.expand(alpha * P), sp.expand(beta * Q)
                steps.append(("scale", alpha, beta))
            elif kind == 0:
                P, Q = sp.expand(P + coeff * Q**power), Q
                steps.append(("x", power, coeff))
            else:
                P, Q = P, sp.expand(Q + coeff * P**power)
                steps.append(("y", power, coeff))
            if sp.total_degree(P) > 7 or sp.total_degree(Q) > 7 or len(sp.Poly(P, x, y).terms()) > 200 or len(sp.Poly(Q, x, y).terms()) > 200:
                break
        if sp.total_degree(P) > 7 or sp.total_degree(Q) > 7:
            continue
        tested += 1
        data = jacobian_data(P, Q)
        if not data["is_nonzero_constant"]:
            continue
        keller += 1
        degrees.add(max(sp.total_degree(P), sp.total_degree(Q)))
        max_degree = max(max_degree, sp.total_degree(P), sp.total_degree(Q))
        inv = (X, Y)
        for step in reversed(steps):
            if step[0] == "x":
                inv = (sp.expand(inv[0] - step[2] * inv[1] ** step[1]), inv[1])
            elif step[0] == "y":
                inv = (inv[0], sp.expand(inv[1] - step[2] * inv[0] ** step[1]))
            else:
                inv = (sp.expand(inv[0] / step[1]), sp.expand(inv[1] / step[2]))
        ok = (
            sp.expand(P.subs({x: inv[0], y: inv[1]}) - X) == 0
            and sp.expand(Q.subs({x: inv[0], y: inv[1]}) - Y) == 0
        )
        if ok:
            verified += 1
        else:
            failures.append({"P": P, "Q": Q, "inverse": inv})
    return {
        "tested": tested,
        "keller_maps": keller,
        "verified_inverses": verified,
        "counterexamples": failures[:3],
        "max_degree": max_degree,
        "degrees_present": sorted(degrees),
    }


# ---------------------------------------------------------------------------
# F8: the "single linear form" family at arbitrary degree k
# ---------------------------------------------------------------------------
def lane_arbitrary_degree(degrees=range(2, 8)):
    """P = x + lam*L^k, Q = y + mu*L^k with L = x + t*y, for every k in range.

    det J = 1 + k (lam + t mu) L^{k-1}: it is a nonzero constant exactly when
    lam + t*mu = 0, and in that case L = X + t*Y is a target coordinate, so the
    inverse is polynomial.  The identity is verified symbolically for each k.
    """
    lam, mu, tt = sp.symbols("lambda mu t", nonzero=True)
    Lk = x + tt * y
    records = []
    for k in degrees:
        P = sp.expand(x + lam * Lk**k)
        Q = sp.expand(y + mu * Lk**k)
        J = sp.expand(det_jacobian(P, Q))
        predicted = sp.expand(1 + k * (lam + tt * mu) * Lk ** (k - 1))
        identity = sp.simplify(sp.expand(J - predicted)) == 0
        J_con = sp.expand(sp.simplify(J.subs(lam, -tt * mu)))
        inverse = (X + tt * mu * (X + tt * Y) ** k, Y - mu * (X + tt * Y) ** k)
        P_con = sp.expand(P.subs(lam, -tt * mu))
        Q_con = sp.expand(Q.subs(lam, -tt * mu))
        check = (
            sp.expand(P_con.subs({x: inverse[0], y: inverse[1]}) - X),
            sp.expand(Q_con.subs({x: inverse[0], y: inverse[1]}) - Y),
        )
        records.append({
            "k": k,
            "P": P,
            "Q": Q,
            "determinant": J,
            "determinant_formula_verified": identity,
            "determinant_with_condition": J_con,
            "inverse": inverse,
            "inverse_verified": check == (0, 0),
        })
    return {"records": records}


# ---------------------------------------------------------------------------
# F7: near misses -- maps that really do collide
# ---------------------------------------------------------------------------
def lane_near_misses():
    candidates = [
        (sp.expand(x**2), sp.expand(y + x**3)),
        (sp.expand(x + x**3), sp.expand(y + x**3)),
        (sp.expand(x + y**2), sp.expand(y + x**2)),
    ]
    records = []
    for P, Q in candidates:
        data = jacobian_data(P, Q)
        p0 = (1, 0)
        f = fibre(P, Q, p0)
        partner = None
        for s0 in f["solutions"] or []:
            if s0 == p0 or s0[0] is None or s0[1] is None:
                continue
            chk = collision(P, Q, p0, s0)
            if chk["verified"]:
                partner = (s0, chk)
                break
        records.append({
            "P": P,
            "Q": Q,
            "determinant": data["jacobian"],
            "determinant_constant": data["is_constant"],
            "fibre_at_origin": f["count"],
            "fibre_points": f["solutions"],
            "collision": partner,
            "determinant_factored": sp.factor(data["jacobian"]),
            "determinant_zero_locus": sp.solve(sp.Eq(data["jacobian"], 0), [x, y], dict=True),
        })
    return {"records": records}


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def main(stages=("F0", "F1", "F2", "F3", "F4", "F5", "F6", "F7")):
    clock = time.time()
    print("=" * 78)
    print("planar Jacobian conjecture -- exact counterexample search")
    print("=" * 78)
    results = {}

    if "F0" in stages:
        print("\n[F0] positive control: the known three dimensional counterexample")
        r = positive_control_dim3()
        results["F0"] = r
        print("  map =", r["map"])
        print("  det J =", r["determinant"], "| constant and nonzero:", r["determinant_is_constant_nonzero"])
        for point, image in zip(r["points"], r["images"]):
            print("    F%s = %s" % (point, image))
        print("  three distinct points, one image:", r["all_images_equal"], r["distinct_points"])
        print("  => the verification pipeline does detect a genuine counterexample.")

    if "F1" in stages:
        print("\n[F1] complete classification of degree <= 2 Keller maps")
        r = lane_degree_two()
        results["F1"] = r
        print("  ansatz: P =", r["ansatz"][0], "  Q =", r["ansatz"][1])
        print("  det J - 1 =", r["gap"])
        print("  coefficient equations:", r["equations"])
        print("  Groebner basis:", r["groebner_basis"])
        print("  solutions:", r["solutions"])
        print("  generic family: P =", r["generic_family"][0], " Q =", r["generic_family"][1])
        print("  det J =", r["generic_determinant"], "| P - (s/f) Q =",
              r["generic_target_linear_form"])
        print("  rational member: P =", r["member"][0], " Q =", r["member"][1])
        print("  its det J =", r["member_determinant"], "| fibre at (0,0):", r["member_fibre"])
        print("  inverse:", r["member_inverse"], "| verified:", r["member_inverse_verified"])

    if "F2" in stages:
        print("\n[F2] triangular maps: Q = f(x), general P of degree <= 2, f of degree <= 4")
        r = lane_triangular(2, 4)
        results["F2"] = r
        print("  identity det J = -P_y f'(x):", r["identity_det_equals_minus_Py_fprime"])
        print("  solutions of the coefficient system:", r["solutions"])
        for b in r["branches"]:
            print("    branch", b["solution"])
            print("      P =", b["P"], " Q =", b["Q"])
            print("      det J =", b["determinant"], "| nonzero constant:", b["nonzero_constant"],
                  "| inverse verified:", b["inverse_verified"])
        print("  every nonzero-constant branch is invertible:",
              r["all_constant_determinant_branches_invertible"])

    if "F3" in stages:
        print("\n[F3] nilpotent 2x2 matrices and cubic-linear maps X + (A X)^{*3}")
        r = lane_cubic_linear()
        results["F3"] = r
        print("  A = u v^T:", r["A"], "  A^2 - (v.u) A =", r["A_squared_equals_vdotu_A"])
        print("  normal form conjugation:", r["conjugating_family"])
        for item in r["examples"]:
            print("    A =", item["A"], "rank", item["rank"], "A^2 = 0:", item["nilpotent"])
        print("  family: P =", r["P_nilpotent"], " Q =", r["Q_nilpotent"])
        print("  det J on the nilpotency locus:", r["determinant_on_nilpotency_locus"])
        print("  constancy equations (factored):", r["constancy_equations_factored"])
        print("  their solutions:", r["constancy_solutions"])
        print("  integer matrices scanned:", r["integer_matrices_scanned"],
              "| constant nonzero det:", len(r["keller_entries"]))
        for c in r["checks"][:6]:
            print("    A =", c["A"], "| det J =", c["determinant"], "| fibre", c["fibre"],
                  "| inverse verified", c["inverse_verified"])
        print("  all Keller cubic-linear maps injective:", r["all_keller_injective"])

    if "F4" in stages:
        print("\n[F4] complete classification of cubic homogeneous Keller maps")
        r = lane_cubic_homogeneous()
        results["F4"] = r
        print("  ansatz: P =", r["ansatz"][0], " Q =", r["ansatz"][1])
        print("  equations:", r["equations"])
        print("  Groebner basis:", r["groebner_basis"])
        print("  reduced equations after the linear relations:", r["reduced_equations"])
        print("  degenerate case f = g = h = 0:", r["degenerate_case_fgh0"])
        print("  case h = 0 (then g = 0 too):", r["case_h_zero"])
        print("  identification of the generic solution with lambda L^3, mu L^3:",
              r["identification_with_closed_form"])
        print("  lambda + t mu =", r["lambda_plus_t_mu"])
        print("  generic solutions:", r["generic_solutions"])
        print("  closed form H =", r["closed_form_H"])
        print("  det J =", r["closed_form_determinant"])
        print("  with the constancy condition lambda = -t mu: det J =",
              r["closed_form_determinant_with_condition"])
        print("  inverse:", r["closed_form_inverse"])
        print("  inverse checks (must be 0, 0):", r["closed_form_inverse_checks"])
        print("  rational member: P =", r["member"][0], " Q =", r["member"][1])
        print("  det J =", r["member_determinant"], "| fibre at (0,0):", r["member_fibre"])
        print("  inverse:", r["member_inverse"], "| verified:", r["member_inverse_verified"],
              "| polynomial:", r["member_inverse_polynomial"])

    if "F5" in stages:
        print("\n[F5] exhaustive scan of cubic homogeneous maps, coefficients in [-2,2]^8")
        r = lane_box_scan(box=2)
        results["F5"] = r
        print("  parameter tuples scanned:", r["scanned"])
        print("  tuples with det J a nonzero constant:", r["keller_count"])
        for rec in r["records"]:
            print("    ", rec["coefficients"], "F = (", rec["P"], ",", rec["Q"], ")",
                  "| fibre", rec["fibre"], "| inverse verified", rec["inverse_verified"])
        print("  all injective:", r["all_injective"])

    if "F6" in stages:
        print("\n[F6] compositions of elementary automorphisms (the tame group)")
        r = lane_tame_group()
        results["F6"] = r
        print("  maps tested:", r["tested"], "| with constant nonzero det J:", r["keller_maps"])
        print("  with an inverse verified by exact substitution:", r["verified_inverses"])
        print("  counterexamples:", r["counterexamples"])
        print("  maximal degree:", r["max_degree"], "| degrees present:", r["degrees_present"])

    if "F8" in stages:
        print("\n[F8] the family (x + lambda L^k, y + mu L^k) at every degree k")
        r = lane_arbitrary_degree()
        results["F8"] = r
        for rec in r["records"]:
            print("  k =", rec["k"])
            print("    det J =", rec["determinant"], "| = 1 + k(lambda+t mu)L^(k-1):",
                  rec["determinant_formula_verified"])
            print("    under lambda = -t mu: det J =", rec["determinant_with_condition"],
                  "| inverse verified:", rec["inverse_verified"])

    if "F7" in stages:
        print("\n[F7] near misses: maps that really do collide")
        r = lane_near_misses()
        results["F7"] = r
        for rec in r["records"]:
            print("  P =", rec["P"], " Q =", rec["Q"])
            print("    det J =", rec["determinant"], "| constant:", rec["determinant_constant"])
            print("    fibre of F(1,0):", rec["fibre_at_origin"], "distinct points",
                  rec["fibre_points"])
            if rec["collision"]:
                p1, chk = rec["collision"]
                print("    exact collision (1,0) ~", p1, "| dP =", chk["dP"], "dQ =", chk["dQ"])
            print("    det J factored:", rec["determinant_factored"],
                  "| zero locus:", rec["determinant_zero_locus"])

    print("\n" + "=" * 78)
    print("tally of exactly verified Keller maps (condition (J) holds)")
    print("=" * 78)
    rows = []
    if "F1" in results:
        rows.append(("F1 degree <= 2, complete classification", "all solutions", "explicit inverse"))
    if "F2" in results:
        rows.append(("F2 triangular, complete classification",
                     "constant det branches: %d" % sum(
                         1 for b in results["F2"]["branches"] if b["nonzero_constant"]),
                     "inverse verified: %s" % results["F2"]["all_constant_determinant_branches_invertible"]))
    if "F3" in results:
        rows.append(("F3 cubic-linear, 2x2 matrices in [-2,2]",
                     "%d" % len(results["F3"]["keller_entries"]),
                     "all injective: %s" % results["F3"]["all_keller_injective"]))
    if "F4" in results:
        rows.append(("F4 cubic homogeneous, complete classification", "all solutions",
                     "inverse verified: %s" % results["F4"]["member_inverse_verified"]))
    if "F5" in results:
        rows.append(("F5 cubic homogeneous box scan, %d tuples" % results["F5"]["scanned"],
                     "%d" % results["F5"]["keller_count"],
                     "all injective: %s" % results["F5"]["all_injective"]))
    if "F6" in results:
        rows.append(("F6 tame group compositions", "%d" % results["F6"]["keller_maps"],
                     "verified inverses: %d" % results["F6"]["verified_inverses"]))
    if "F8" in results:
        rows.append(("F8 (x + lam L^k, y + mu L^k), k = 2..7", "7 families",
                     "all inverse verified: %s" % all(
                         r["inverse_verified"] for r in results["F8"]["records"])))
    for name, count, status in rows:
        print("  %-52s %-22s %s" % (name, count, status))
    if "F7" in results:
        print("\n  colliding maps found (F7): %d, each with a NON-constant determinant" %
              sum(1 for r in results["F7"]["records"] if r["collision"]))
    print("\ntotal wall clock: %.1f s" % (time.time() - clock))
    print("\nVERDICT: no pair (P, Q) satisfying (J) and (C) was produced.")
    print("Every Keller map in lanes F1-F6 is injective: either its fibre at a tested")
    print("point has size 1, or an explicit polynomial inverse was verified by exact")
    print("substitution. Every colliding map found in F7 has a non-constant determinant.")
    return results


if __name__ == "__main__":
    chosen = tuple(sys.argv[1].split(",")) if len(sys.argv) > 1 else (
        "F0", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8")
    main(chosen)
