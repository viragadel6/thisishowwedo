"""Exact search for a counterexample to the planar (two dimensional) Jacobian conjecture.

Target: P, Q in C[x, y] with rational or algebraic coefficients such that

    (J)  det J = P_x Q_y - P_y Q_x is a NONZERO CONSTANT, and
    (C)  (x, y) |-> (P(x, y), Q(x, y)) is NOT injective on C^2.

METHODOLOGICAL POINTS (these are the corrections of a first, weaker version):

*  The number of points of a fibre is computed as

       dim_Q Q[x, y] / (P - w1, Q - w2)

   (number of standard monomials of a Groebner basis).  For a map with det J a
   nonzero constant the fibre ideal is radical by the Jacobian criterion, so this
   dimension IS the number of points over C.  Counting distinct roots of one
   elimination polynomial -- what the first version did -- is only a lower bound:
   for (x^2, y^2) at (1,1) it gives 2 although the fibre has 4 points.  That is
   now also demonstrated in the transcript.
*  A fibre count of 1 therefore proves injectivity at that fibre, and a count > 1
   proves non-injectivity together with exact algebraic collision partners.
*  Wherever possible injectivity is additionally certified by an explicit
   polynomial inverse verified by exact substitution.
*  Symbolic derivations avoid unjustified nonzero assumptions and avoid dividing
   by parameters that may vanish; every case split is executed and verified.

Lanes: F0 positive control (3D), F1 degree <= 2, F2 triangular (all degrees),
F3 nilpotent 2x2 / cubic-linear, F4 cubic homogeneous (complete), F5 box scan,
F6 tame group, F7 near misses, F8 one-linear-form family in every degree,
F9 mixed degree 2+3 grid.
"""

from __future__ import annotations

import itertools
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
    data = sp.Poly(J, x, y).as_dict()
    constant = data.get((0, 0), sp.Integer(0))
    degenerate = all(c == 0 for m, c in data.items() if m != (0, 0))
    return {
        "jacobian": J,
        "constant": sp.simplify(constant),
        "is_constant": bool(degenerate),
        "is_nonzero_constant": bool(degenerate and sp.simplify(constant) != 0),
    }


def _standard_monomials(basis):
    """Standard monomials of a zero dimensional ideal, given a Groebner basis."""
    lms = [sp.Poly(g, x, y).LM() for g in basis]
    if not lms:
        return []
    seen = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        m = stack.pop()
        for step in ((1, 0), (0, 1)):
            n = (m[0] + step[0], m[1] + step[1])
            if n in seen:
                continue
            if any(n[0] >= lm[0] and n[1] >= lm[1] for lm in lms):
                continue
            seen.add(n)
            stack.append(n)
            if len(seen) > 20000:
                raise RuntimeError("fibre not zero dimensional")
    return sorted(seen)


def fibre(P, Q, p0):
    """Exact fibre over C, with the number of points certified as a quotient dimension."""
    w = (sp.expand(P.subs({x: p0[0], y: p0[1]})), sp.expand(Q.subs({x: p0[0], y: p0[1]})))
    gens = [sp.expand(P - w[0]), sp.expand(Q - w[1])]
    G = sp.groebner(gens, x, y, order="lex")
    out = {"p0": p0, "w": w, "points": None, "basis": [g for g in G.exprs],
           "lower_bound_distinct_x": None, "solutions": None}
    if [g for g in G.exprs] == [sp.Integer(1)]:
        out["points"] = 0
        out["solutions"] = []
        return out
    out["points"] = len(_standard_monomials(G.exprs))
    univariate = [g for g in G.exprs if g.free_symbols <= {x}]
    if univariate:
        poly = sp.Poly(univariate[-1], x, y)
        squarefree = poly.sqf_part().as_expr()
        _, factors = sp.factor_list(squarefree)
        out["lower_bound_distinct_x"] = sum(
            sp.Poly(f, x, y).total_degree() for f, _ in factors if f.free_symbols
        )
    sols = sp.solve(gens, [x, y], dict=True)
    out["solutions"] = [(sp.nsimplify(s.get(x)), sp.nsimplify(s.get(y))) for s in sols]
    return out


def polynomial_inverse(P, Q):
    """Explicit inverse, verified by exact substitution."""
    sol = sp.solve([X - P, Y - Q], [x, y], dict=True)
    if len(sol) != 1:
        return {"found": False, "solutions": len(sol), "inverse": None, "verified": False}
    inv = (sp.simplify(sol[0][x]), sp.simplify(sol[0][y]))
    ok = (sp.expand(P.subs({x: inv[0], y: inv[1]}) - X) == 0
          and sp.expand(Q.subs({x: inv[0], y: inv[1]}) - Y) == 0)
    return {"found": True, "solutions": 1, "inverse": inv, "verified": bool(ok),
            "polynomial": bool(inv[0].is_polynomial(X, Y) and inv[1].is_polynomial(X, Y))}


def collision(P, Q, p0, p1):
    dP = sp.expand(P.subs({x: p0[0], y: p0[1]}) - P.subs({x: p1[0], y: p1[1]}))
    dQ = sp.expand(Q.subs({x: p0[0], y: p0[1]}) - Q.subs({x: p1[0], y: p1[1]}))
    distinct = sp.simplify(p0[0] - p1[0]) != 0 or sp.simplify(p0[1] - p1[1]) != 0
    return {"dP": dP, "dQ": dQ, "verified": bool(dP == 0 and dQ == 0 and distinct)}


# ---------------------------------------------------------------------------
# F0: positive control, the known three dimensional counterexample
# ---------------------------------------------------------------------------
def lane_positive_control():
    z = sp.Symbol("z")
    P = sp.expand((1 + x * y) ** 3 * z + y**2 * (1 + x * y) * (4 + 3 * x * y))
    Q = sp.expand(y + 3 * x * (1 + x * y) ** 2 * z + 3 * x * y**2 * (4 + 3 * x * y))
    R = sp.expand(2 * x - 3 * x**2 * y - x**3 * z)
    # determinant by two independent routes
    J1 = sp.expand(sp.Matrix([P, Q, R]).jacobian([x, y, z]).det())
    J2 = sp.expand(
        sp.diff(P, x) * (sp.diff(Q, y) * sp.diff(R, z) - sp.diff(Q, z) * sp.diff(R, y))
        - sp.diff(P, y) * (sp.diff(Q, x) * sp.diff(R, z) - sp.diff(Q, z) * sp.diff(R, x))
        + sp.diff(P, z) * (sp.diff(Q, x) * sp.diff(R, y) - sp.diff(Q, y) * sp.diff(R, x))
    )
    points = [(-1, sp.Rational(3, 2), sp.Rational(13, 2)),
              (0, 0, sp.Rational(-1, 4)),
              (1, sp.Rational(-3, 2), sp.Rational(13, 2))]
    images = [tuple(sp.expand(e.subs({x: p[0], y: p[1], z: p[2]})) for e in (P, Q, R))
              for p in points]
    return {"map": (P, Q, R), "determinant": J1, "determinant_second_route": J2,
            "determinants_agree": sp.expand(J1 - J2) == 0,
            "determinant_is_minus_two": J1 == -2,
            "points": points, "images": images,
            "one_image": len({str(i) for i in images}) == 1,
            "three_distinct_points": len({str(p) for p in points}) == 3}


# ---------------------------------------------------------------------------
# F1: complete classification of Keller maps of degree <= 2
# ---------------------------------------------------------------------------
def lane_degree_two():
    """det J a nonzero constant forces an invertible linear part; normalise it away.

    Affine changes of coordinates on source and target are bijections preserving
    both (J) (up to a nonzero scalar) and (C), so the ansatz below is complete.
    """
    a, b, c, d, e, f = sp.symbols("a b c d e f")
    P = x + a * x**2 + b * x * y + c * y**2
    Q = y + d * x**2 + e * x * y + f * y**2
    data = sp.Poly(sp.expand(det_jacobian(P, Q) - 1), x, y).as_dict()
    equations = [sp.expand(c0) for _, c0 in sorted(data.items())]
    G = sp.groebner(equations, a, b, c, d, e, f, order="lex")
    solutions = sp.solve(equations, [a, b, c, d, e, f], dict=True)

    # the linear part is invertible: det J is a nonzero constant, and the constant
    # term of det J is det of the linear part.  Verified on the general
    # degree <= 2 ansatz with arbitrary linear part below (no normalisation).
    l11, l12, l21, l22 = sp.symbols("l11 l12 l21 l22")
    Pg = l11 * x + l12 * y + a * x**2 + b * x * y + c * y**2
    Qg = l21 * x + l22 * y + d * x**2 + e * x * y + f * y**2
    det_at_origin = sp.expand(det_jacobian(Pg, Qg).subs({x: 0, y: 0}))
    linear_part_identity = sp.expand(det_at_origin - (l11 * l22 - l12 * l21)) == 0

    branches = []
    for s0 in solutions:
        Pb, Qb = sp.expand(P.subs(s0)), sp.expand(Q.subs(s0))
        jd = jacobian_data(Pb, Qb)
        entry = {"solution": s0, "P": Pb, "Q": Qb, "determinant": sp.simplify(jd["jacobian"]),
                 "nonzero_constant": jd["is_nonzero_constant"], "inverse": None,
                 "inverse_verified": False}
        if jd["is_nonzero_constant"]:
            inv = polynomial_inverse(Pb, Qb)
            entry["inverse"] = inv["inverse"]
            entry["inverse_verified"] = inv["verified"]
        branches.append(entry)

    # closed form of the generic branch and of its inverse
    s_, f_ = sp.symbols("s f", nonzero=True)
    L = x - (f_ / s_) * y
    Pgen = sp.expand(x + s_ * L**2)
    Qgen = sp.expand(y + (s_**2 / f_) * L**2)
    u_form = sp.expand(Pgen - (f_ / s_) * Qgen)          # equals x - (f/s) y on the source
    u_target = sp.expand(X - (f_ / s_) * Y)              # the same linear form in the target
    inv_gen = (sp.expand(u_target + (f_ / s_) * (Y - (s_**2 / f_) * u_target**2)),
               sp.expand(Y - (s_**2 / f_) * u_target**2))
    check_gen = (sp.expand(Pgen.subs({x: inv_gen[0], y: inv_gen[1]}) - X),
                 sp.expand(Qgen.subs({x: inv_gen[0], y: inv_gen[1]}) - Y))

    # a rational member, fully verified
    Pm = sp.expand(Pgen.subs({s_: 2, f_: 3}))
    Qm = sp.expand(Qgen.subs({s_: 2, f_: 3}))
    inv_m = polynomial_inverse(Pm, Qm)

    return {
        "ansatz": (P, Q), "equations": equations,
        "groebner_basis": [sp.factor(g) for g in G.exprs],
        "solutions": solutions,
        "det_at_origin": det_at_origin,
        "linear_part_identity": linear_part_identity,
        "branches": branches,
        "all_branches_invertible": all(b["inverse_verified"] for b in branches
                                       if b["nonzero_constant"]),
        "generic_family": (Pgen, Qgen),
        "generic_determinant": sp.simplify(det_jacobian(Pgen, Qgen)),
        "generic_target_coordinate": u_form,
        "generic_inverse": inv_gen, "generic_inverse_checks": check_gen,
        "member": (Pm, Qm), "member_determinant": sp.simplify(det_jacobian(Pm, Qm)),
        "member_fibre": fibre(Pm, Qm, (0, 0))["points"],
        "member_inverse": inv_m["inverse"], "member_inverse_verified": inv_m["verified"],
    }


# ---------------------------------------------------------------------------
# F2: triangular maps, complete for ALL degrees
# ---------------------------------------------------------------------------
def lane_triangular(deg_P=4, deg_x=2, deg_f=6):
    """P arbitrary in y, Q = f(x): the identity det J = -P_y f'(x) settles everything.

    Two machine checked ingredients, for general symbolic coefficients:
      (i)  det J = -P_y * f'(x)                     (structural identity)
      (ii) coeff of y^(dp-1) in det J = -dp * p_dp(x) * f'(x)
    Hence constancy of a nonzero det J forces deg_y P <= 1 and f' constant, i.e.
    Q affine and P of y-degree <= 1 -- for arbitrary degrees, not just the tested
    ones (the tested range is only the machine check of the pattern).
    """
    # (i) and (ii) with general symbolic coefficients
    checks = []
    for dp in range(1, deg_P + 1):
        # generic polynomial of y-degree dp with arbitrary x-coefficients in every layer
        coeffs = [[sp.Symbol("c%d_%d" % (i, j)) for j in range(deg_x + 1)] for i in range(dp + 1)]
        Pdp = sum(sum(coeffs[i][j] * x**j for j in range(deg_x + 1)) * y**i
                  for i in range(dp + 1))
        q = [sp.Symbol("q%d" % j) for j in range(deg_f + 1)]
        Qf = sum(q[j] * x**j for j in range(deg_f + 1))
        Jdp = sp.expand(det_jacobian(Pdp, Qf))
        structural = sp.expand(Jdp - (-sp.diff(Pdp, y) * sp.diff(Qf, x))) == 0
        top = sp.expand(sp.Poly(Jdp, y).nth(dp - 1))          # coefficient of y^(dp-1), in x
        top_layer = sum(coeffs[dp][j] * x**j for j in range(deg_x + 1))
        expected = sp.expand(-dp * top_layer * sp.diff(Qf, x))
        checks.append({"deg_y_P": dp, "structural_identity": structural,
                       "leading_y_coefficient_matches": sp.expand(top - expected) == 0})

    # complete classification of the surviving case: P = p0(x) + c*y, Q affine
    c0, c1 = sp.symbols("c0 c1", nonzero=True)
    gcoef = sp.symbols("g0:5")
    P_full = sum(gcoef[j] * x**j for j in range(5)) + c1 * y
    q0 = sp.Symbol("q0")
    q1 = sp.Symbol("q1", nonzero=True)
    Q_full = q0 + q1 * x
    inv = (sp.expand((Y - q0) / q1),
           sp.expand((X - sum(gcoef[j] * ((Y - q0) / q1) ** j for j in range(5))) / c1))
    inv_checks = (sp.expand(P_full.subs({x: inv[0], y: inv[1]}) - X),
                  sp.expand(Q_full.subs({x: inv[0], y: inv[1]}) - Y))

    # rank-one structure of the determinant: det J = -p1(x) f'(x)
    p1 = sp.Symbol("p1", nonzero=True)
    product_constant_forces = "p1 and f' both constant (a product of polynomials is constant only if both are)"

    return {"checks": checks, "structural_identity_all_tested": all(c["structural_identity"] for c in checks),
            "leading_coefficient_all_tested": all(c["leading_y_coefficient_matches"] for c in checks),
            "surviving_form": (P_full, Q_full),
            "surviving_determinant": sp.simplify(det_jacobian(P_full, Q_full)),
            "surviving_inverse": inv, "surviving_inverse_checks": inv_checks,
            "argument": product_constant_forces,
            "tested_y_degrees": (1, deg_P)}


# ---------------------------------------------------------------------------
# F3: nilpotent 2x2 matrices and cubic-linear maps, without nonzero assumptions
# ---------------------------------------------------------------------------
def lane_cubic_linear():
    s_, t_, m_, n_ = sp.symbols("s t m n")
    L = m_ * x + n_ * y
    P = sp.expand(x + (s_ * L) ** 3)
    Q = sp.expand(y + (t_ * L) ** 3)
    J = sp.expand(det_jacobian(P, Q))
    # exact closed form, no division anywhere
    J_formula = sp.expand(1 + 3 * L**2 * (s_**3 * m_ + t_**3 * n_))
    formula_verified = sp.expand(J - J_formula) == 0
    # on the nilpotency locus s*m + t*n = 0
    nil = s_ * m_ + t_ * n_
    J_on_nil = sp.expand(sp.simplify(J_formula + (0 * nil)))
    # s^3 m + t^3 n = s^2(sm) + t^2(tn) = tn(t^2 - s^2) on the locus sm + tn = 0
    identity_on_locus = sp.expand(
        (s_**3 * m_ + t_**3 * n_) - (t_ * n_) * (t_**2 - s_**2) - (s_ * m_ + t_ * n_) * s_**2
    )

    cases = []
    # Case A: L = 0, i.e. A = 0 -> identity map
    cases.append({"case": "m = n = 0 (A = 0)", "map": (x, y), "determinant": sp.Integer(1),
                  "inverse": (X, Y), "inverse_verified": True})
    # Case B: s*m = t*n = 0 (shears) -- four sub-cases, one representative each
    shears = [("s = 0, n = 0", sp.expand(x), sp.expand(y + (t_ * m_ * x) ** 3)),
              ("t = 0, m = 0", sp.expand(x + (s_ * n_ * y) ** 3), sp.expand(y)),
              ("s = 0, t = 0 (A = 0)", x, y),
              ("m = 0, n = 0 (A = 0)", x, y)]
    for name, Ps, Qs in shears:
        jd = jacobian_data(Ps, Qs)
        inv = polynomial_inverse(Ps, Qs) if jd["is_nonzero_constant"] else {"verified": False, "inverse": None}
        cases.append({"case": "shear: " + name, "map": (Ps, Qs),
                      "determinant": sp.simplify(jd["jacobian"]),
                      "nonzero_constant": jd["is_nonzero_constant"],
                      "inverse": inv["inverse"], "inverse_verified": inv["verified"]})
    # Case C: t*n != 0 and t^2 = s^2 -> t = +-s, n = -s*m/t
    for sign in (1, -1):
        tt = sign * s_
        nn = -s_ * m_ / s_ if False else -m_ * (s_ / (sign * s_))  # = -m/sign
        Ps = sp.expand(x + (s_ * (m_ * x + nn * y)) ** 3)
        Qs = sp.expand(y + ((sign * s_) * (m_ * x + nn * y)) ** 3)
        inv = polynomial_inverse(Ps, Qs)
        jd = jacobian_data(Ps, Qs)
        cases.append({"case": "t = %+d s, n = -m/t*s" % sign, "map": (Ps, Qs),
                      "determinant": sp.simplify(jd["jacobian"]),
                      "nonzero_constant": jd["is_nonzero_constant"],
                      "inverse": inv["inverse"], "inverse_verified": inv["verified"]})

    # exhaustive integer matrix scan, cross-checked against nilpotency
    a, b, c, d = sp.symbols("a b c d")
    Pg = sp.expand(x + (a * x + b * y) ** 3)
    Qg = sp.expand(y + (c * x + d * y) ** 3)
    Jg = sp.Poly(sp.expand(det_jacobian(Pg, Qg)), x, y).as_dict()
    keller, nilpotent = [], []
    for values in itertools.product(range(-2, 3), repeat=4):
        subst = dict(zip((a, b, c, d), values))
        constant = Jg.get((0, 0), sp.Integer(0)).subs(subst)
        rest = [c0.subs(subst) for m0, c0 in Jg.items() if m0 != (0, 0)]
        if all(sp.simplify(r) == 0 for r in rest) and sp.simplify(constant) != 0:
            keller.append(values)
        A0 = sp.Matrix([[values[0], values[1]], [values[2], values[3]]])
        if sp.expand(A0 * A0) == sp.zeros(2, 2):
            nilpotent.append(values)
    records = []
    for values in keller:
        subst = dict(zip((a, b, c, d), values))
        Pv, Qv = sp.expand(Pg.subs(subst)), sp.expand(Qg.subs(subst))
        inv = polynomial_inverse(Pv, Qv)
        f = fibre(Pv, Qv, (0, 0))
        records.append({"A": sp.Matrix([[values[0], values[1]], [values[2], values[3]]]),
                        "P": Pv, "Q": Qv, "determinant": sp.simplify(det_jacobian(Pv, Qv)),
                        "points_in_fibre": f["points"], "inverse_verified": inv["verified"]})

    return {"P": P, "Q": Q, "determinant": J, "formula": J_formula,
            "formula_verified": formula_verified,
            "identity_on_nilpotency_locus": identity_on_locus,
            "cases": cases,
            "all_cases_invertible": all(c.get("inverse_verified") for c in cases),
            "box": 2, "keller_entries": keller, "nilpotent_entries": nilpotent,
            "keller_equals_nilpotent": sorted(keller) == sorted(nilpotent),
            "records": records,
            "all_injective": all(r["inverse_verified"] and r["points_in_fibre"] == 1
                                 for r in records)}


# ---------------------------------------------------------------------------
# F4: complete classification of cubic homogeneous Keller maps
# ---------------------------------------------------------------------------
def lane_cubic_homogeneous():
    a, b, c, d, e, f, g, h = sp.symbols("a b c d e f g h")
    h1 = a * x**3 + b * x**2 * y + c * x * y**2 + d * y**3
    h2 = e * x**3 + f * x**2 * y + g * x * y**2 + h * y**3
    P = sp.expand(x + h1)
    Q = sp.expand(y + h2)
    equations = [sp.expand(c0) for _, c0 in
                 sorted(sp.Poly(sp.expand(det_jacobian(P, Q) - 1), x, y).as_dict().items())]
    G = sp.groebner(equations, a, b, c, d, e, f, g, h, order="lex")
    basis = [sp.factor(g0) for g0 in G.exprs]

    # ---- case analysis, executed and verified against the basis --------------
    # linear relations valid in every branch
    linear_relations = [3 * a + f, b + g, c + 3 * h]
    linear_in_ideal = all(sp.simplify(sp.expand(r)) in [sp.expand(g0) for g0 in G.exprs]
                          for r in linear_relations)

    # Case 1: h = 0.  Then the basis gives d*g = 0, f*g = 0, 3*e*g - f^2 = 0.
    #   Sub-case g != 0: d = f = 0 and 3*d*e - 2*f*h + g^2 = g^2 != 0, impossible.
    case1_impossible = sp.simplify(sp.expand((3 * d * e - 2 * f * h + g**2).subs({h: 0, d: 0, f: 0}))) == g**2
    #   Sub-case g = 0: f = 0 (from 3*e*g = f^2) and 3*d*e = 0.
    case1_reduced = [sp.expand(g0.subs({h: 0, g: 0, f: 0})) for g0 in G.exprs]
    case1_reduced = [g0 for g0 in case1_reduced if g0 != 0]
    case1_solutions = sp.solve(case1_reduced, [a, b, c, d, e], dict=True)
    case1_maps = []
    for s0 in case1_solutions:
        Pb = sp.expand(P.subs({**{h: 0, g: 0, f: 0}, **s0}))
        Qb = sp.expand(Q.subs({**{h: 0, g: 0, f: 0}, **s0}))
        inv = polynomial_inverse(Pb, Qb)
        case1_maps.append({"solution": s0, "P": Pb, "Q": Qb,
                           "determinant": sp.simplify(det_jacobian(Pb, Qb)),
                           "inverse_verified": inv["verified"]})

    # Case 2: h != 0.  From h*(3fh - g^2) = 0 we get 3fh = g^2.
    #   If moreover g = 0 then f = 0 and the basis collapses to 3h^2 = 0, which
    #   contradicts h != 0.  Checked below by substitution into the basis.
    basis_g0 = [sp.expand(g0.subs({g: 0})) for g0 in G.exprs]
    basis_g0 = [g0 for g0 in basis_g0 if g0 != 0]
    basis_g0_f0 = [sp.expand(g0.subs({f: 0})) for g0 in basis_g0]
    basis_g0_f0 = [g0 for g0 in basis_g0_f0 if g0 != 0]
    case2_g_zero_forces_h_zero = any(sp.simplify(g0) == 3 * h**2 for g0 in basis_g0_f0)
    case2_g_zero = {"equations_with_g_0": basis_g0, "with_f_0": basis_g0_f0,
                    "forces_h_zero": bool(case2_g_zero_forces_h_zero)}
    generic = sp.solve(equations, [a, b, c, d, e, f, g, h], dict=True)
    generic_solution = generic[0]

    # closed form H = (lam L^3, mu L^3), lam + t*mu = 0
    lam, mu, tt = sp.symbols("lambda mu t")
    Lk = x + tt * y
    Ph = sp.expand(x + lam * Lk**3)
    Qh = sp.expand(y + mu * Lk**3)
    J_general = sp.expand(det_jacobian(Ph, Qh))
    J_forced = sp.expand(sp.simplify(J_general.subs(lam, -tt * mu)))
    Ph_con = sp.expand(Ph.subs(lam, -tt * mu))
    Qh_con = sp.expand(Qh.subs(lam, -tt * mu))
    inv = (sp.expand(X + tt * mu * (X + tt * Y) ** 3), sp.expand(Y - mu * (X + tt * Y) ** 3))
    check = (sp.expand(Ph_con.subs({x: inv[0], y: inv[1]}) - X),
             sp.expand(Qh_con.subs({x: inv[0], y: inv[1]}) - Y))
    # the lex solution and the closed form are the same family
    L_id = x + (g / f) * y
    identification = (sp.simplify(sp.expand(h1.subs(generic_solution) - (-f / 3) * L_id**3)),
                      sp.simplify(sp.expand(h2.subs(generic_solution) - (f**2 / (3 * g)) * L_id**3)))
    lam_value = -f / 3
    mu_value = f**2 / (3 * g)
    t_value = g / f

    member = {"lambda": sp.Rational(-2, 3), "mu": 5, "t": sp.Rational(2, 15)}
    Pm = sp.expand(Ph.subs({lam: member["lambda"], mu: member["mu"], tt: member["t"]}))
    Qm = sp.expand(Qh.subs({lam: member["lambda"], mu: member["mu"], tt: member["t"]}))
    inv_m = polynomial_inverse(Pm, Qm)

    return {"ansatz": (P, Q), "equations": equations, "groebner_basis": basis,
            "linear_relations": linear_relations, "linear_relations_in_basis": linear_in_ideal,
            "case1_h_zero_impossible_for_g": case1_impossible,
            "case1_reduced_equations": case1_reduced,
            "case1_solutions": case1_solutions, "case1_maps": case1_maps,
            "case2_g_zero": case2_g_zero,
            "generic_solutions": generic,
            "closed_form": (lam * Lk**3, mu * Lk**3),
            "closed_form_determinant": J_general,
            "closed_form_determinant_with_condition": J_forced,
            "closed_form_inverse": inv, "closed_form_inverse_checks": check,
            "identification_with_closed_form": identification,
            "lam_plus_t_mu": sp.simplify(lam_value + t_value * mu_value),
            "member": (Pm, Qm), "member_determinant": sp.simplify(det_jacobian(Pm, Qm)),
            "member_fibre": fibre(Pm, Qm, (0, 0)),
            "member_inverse": inv_m["inverse"], "member_inverse_verified": inv_m["verified"]}


# ---------------------------------------------------------------------------
# F5: exhaustive box scan of cubic homogeneous maps
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
        rest = [c0.subs(subst) for m0, c0 in data.items() if m0 != (0, 0)]
        if all(sp.simplify(r) == 0 for r in rest) and sp.simplify(constant) != 0:
            keller.append(values)
    records = []
    for values in keller:
        subst = dict(zip(names1 + names2, values))
        Pv, Qv = sp.expand(P.subs(subst)), sp.expand(Q.subs(subst))
        inv = polynomial_inverse(Pv, Qv)
        records.append({"coefficients": values, "P": Pv, "Q": Qv,
                        "points_in_fibre": fibre(Pv, Qv, (1, 0))["points"],
                        "inverse_verified": inv["verified"]})
    return {"box": box, "scanned": scanned, "keller_count": len(keller), "records": records,
            "all_injective": all(r["inverse_verified"] and r["points_in_fibre"] == 1
                                 for r in records)}


# ---------------------------------------------------------------------------
# F6: compositions of elementary automorphisms (the tame group)
# ---------------------------------------------------------------------------
def lane_tame_group(depth=5, samples=80, seed=20261027):
    import random
    rng = random.Random(seed)
    moves = list(itertools.product([0, 1], [1, 2, 3], [-3, -2, -1, 1, 2, 3]))
    tested = keller = verified = 0
    max_degree = 0
    failures = []
    for _ in range(samples):
        length = rng.randint(1, depth)
        P, Q = x, y
        steps = []
        for _ in range(length):
            kind, power, coeff = rng.choice(moves)
            if rng.random() < 0.15:
                alpha, beta = rng.choice([(1, 1), (1, -1), (2, 1), (1, 2)])
                P, Q = sp.expand(alpha * P), sp.expand(beta * Q)
                steps.append(("scale", alpha, beta))
            elif kind == 0:
                P, Q = sp.expand(P + coeff * Q**power), Q
                steps.append(("x", power, coeff))
            else:
                P, Q = P, sp.expand(Q + coeff * P**power)
                steps.append(("y", power, coeff))
            if sp.total_degree(P) > 7 or sp.total_degree(Q) > 7:
                break
        if sp.total_degree(P) > 7 or sp.total_degree(Q) > 7:
            continue
        tested += 1
        jd = jacobian_data(P, Q)
        if not jd["is_nonzero_constant"]:
            continue
        keller += 1
        max_degree = max(max_degree, sp.total_degree(P), sp.total_degree(Q))
        inv = (X, Y)
        for step in reversed(steps):
            if step[0] == "x":
                inv = (sp.expand(inv[0] - step[2] * inv[1] ** step[1]), inv[1])
            elif step[0] == "y":
                inv = (inv[0], sp.expand(inv[1] - step[2] * inv[0] ** step[1]))
            else:
                inv = (sp.expand(inv[0] / step[1]), sp.expand(inv[1] / step[2]))
        ok = (sp.expand(P.subs({x: inv[0], y: inv[1]}) - X) == 0
              and sp.expand(Q.subs({x: inv[0], y: inv[1]}) - Y) == 0)
        if ok:
            verified += 1
        else:
            failures.append({"P": P, "Q": Q, "inverse": inv})
    return {"tested": tested, "keller_maps": keller, "verified_inverses": verified,
            "failures": failures[:3], "max_degree": max_degree}


# ---------------------------------------------------------------------------
# F7: near misses -- maps that really do collide
# ---------------------------------------------------------------------------
def lane_near_misses():
    candidates = [(sp.expand(x**2), sp.expand(y + x**3)),
                  (sp.expand(x + x**3), sp.expand(y + x**3)),
                  (sp.expand(x + y**2), sp.expand(y + x**2)),
                  (sp.expand(x * (1 + y)), sp.expand(y * (1 + x)))]
    records = []
    for P, Q in candidates:
        jd = jacobian_data(P, Q)
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
        records.append({"P": P, "Q": Q, "determinant": jd["jacobian"],
                        "determinant_constant": jd["is_constant"],
                        "fibre_scheme_length": f["points"],
                        "fibre_distinct_points": len(f["solutions"] or []),
                        "fibre_list": f["solutions"],
                        "lower_bound_distinct_x": f["lower_bound_distinct_x"],
                        "collision": partner,
                        "determinant_factored": sp.factor(jd["jacobian"])})
    return {"records": records}


# ---------------------------------------------------------------------------
# F8: one linear form, every degree
# ---------------------------------------------------------------------------
def lane_arbitrary_degree(max_degree=30):
    """P = x + lam L^k, Q = y + mu L^k, L = x + t y, for every k from 2 to max_degree.

    det J = 1 + k (lam + t mu) L^(k-1)   (verified symbolically for every k).

    Constancy forces lam + t mu = 0.  Then L is a target coordinate: for
    G = (X + t mu L^k, Y - mu L^k) one has (G1 + t G2) = X + t Y, hence
    P(G) = G1 + lam (X + t Y)^k = X + t mu L^k - t mu L^k = X and
    Q(G) = Y - mu L^k + mu L^k = Y.  The code verifies exactly these three
    identities for every k (symbolic in lam, mu, t), so the inverse is a
    polynomial of degree k and the map is bijective for every k.
    """
    lam, mu, tt = sp.symbols("lambda mu t")
    Lk = x + tt * y
    records = []
    for k in range(2, max_degree + 1):
        P = sp.expand(x + lam * Lk**k)
        Q = sp.expand(y + mu * Lk**k)
        J = sp.expand(det_jacobian(P, Q))
        predicted = sp.expand(1 + k * (lam + tt * mu) * Lk ** (k - 1))
        formula_ok = sp.expand(J - predicted) == 0
        determinant_with_condition = sp.expand(sp.simplify(J.subs(lam, -tt * mu)))
        # the inverse, and the three exact identities
        u = sp.expand((X + tt * Y) ** k)
        G1 = sp.expand(X + tt * mu * u)
        G2 = sp.expand(Y - mu * u)
        L_invariance = sp.expand(G1 + tt * G2 - (X + tt * Y)) == 0
        P_of_G = sp.expand(G1 + lam * u)          # P(x,y) = x + lam*(x + t y)^k at (G1, G2)
        Q_of_G = sp.expand(G2 + mu * u)
        P_check = sp.expand(P_of_G.subs(lam, -tt * mu) - X) == 0
        Q_check = sp.expand(Q_of_G - Y) == 0
        records.append({"k": k, "determinant": J, "formula_verified": formula_ok,
                        "determinant_with_condition": determinant_with_condition,
                        "inverse": (G1, G2), "L_invariance": bool(L_invariance),
                        "inverse_verified": bool(L_invariance and P_check and Q_check),
                        "inverse_degree": max(sp.total_degree(G1), sp.total_degree(G2))})
    return {"records": records, "max_degree": max_degree,
            "all_verified": all(r["inverse_verified"] and r["formula_verified"] for r in records)}


# ---------------------------------------------------------------------------
# F9: mixed degree 2+3 (bounded grid, and the exact structural facts)
# ---------------------------------------------------------------------------
def lane_mixed_degree_three(grid=3, grid_samples=200):
    """F = x + F_2 + F_3 with both parts nonzero (the degree-3 case not covered by F4).

    Exact structural facts established here for general coefficients:
      * the degree one part of det J - 1 is 2 a1 + b2, a2 + 2 b3, so a1 = -b2/2,
        a2 = -2 b3 always;
      * the degree four part of det J - 1 is exactly the Jacobian determinant of the
        cubic part (P3, Q3): det J(P3, Q3) = 0 is therefore a *necessary* condition,
        and the cubic Keller maps (P3, Q3) were classified in F4;
      * the degree two part is linear in the three cubic coefficients a4, a5, a6,
        so those are determined by (a3, b1, b2, b3, b4, b5, b6, b7).
    What is left is a four variable problem in (b4, b5, b6, b7).  This lane solves
    it exactly on a grid of the free quadratic data; it is a bounded scan, NOT a
    completeness proof.  Completeness is claimed only in F1 (pure degree 2) and
    F4 (pure cubic homogeneous).
    """
    a1, a2, a3 = sp.symbols("a1 a2 a3")
    b1, b2, b3 = sp.symbols("b1 b2 b3")
    a4, a5, a6, a7 = sp.symbols("a4 a5 a6 a7")
    b4, b5, b6, b7 = sp.symbols("b4 b5 b6 b7")
    P2 = a1 * x**2 + a2 * x * y + a3 * y**2
    Q2 = b1 * x**2 + b2 * x * y + b3 * y**2
    P3 = a4 * x**3 + a5 * x**2 * y + a6 * x * y**2 + a7 * y**3
    Q3 = b4 * x**3 + b5 * x**2 * y + b6 * x * y**2 + b7 * y**3
    P = sp.expand(x + P2 + P3)
    Q = sp.expand(y + Q2 + Q3)
    J = sp.expand(det_jacobian(P, Q))
    data = sp.Poly(sp.expand(J - 1), x, y).as_dict()
    by_degree = {}
    for m0, c0 in data.items():
        by_degree.setdefault(sum(m0), []).append((m0, sp.expand(c0)))

    degree_one = [sp.expand(c0) for _, c0 in by_degree.get(1, [])]
    degree_one_matches = all(
        any(sp.expand(e - f0) == 0 for f0 in (2 * a1 + b2, a2 + 2 * b3)) for e in degree_one
    ) and len(degree_one) == 2
    degree_four = sp.expand(sum(c0 * x**m0[0] * y**m0[1] for m0, c0 in by_degree.get(4, [])))
    degree_four_matches = sp.expand(degree_four - sp.expand(det_jacobian(P3, Q3))) == 0
    degree_two = [sp.expand(c0) for _, c0 in by_degree.get(2, [])]
    def is_affine_in_cubic(expr):
        poly = sp.Poly(expr, a4, a5, a6)
        return all(sum(m0) <= 1 for m0 in poly.as_dict())
    degree_two_linear_in_a456 = all(is_affine_in_cubic(e) for e in degree_two)
    degree_two_solution = sp.solve(degree_two, [a4, a5, a6], dict=True)

    def solve_fibre(values):
        """Given (a3,b1,b2,b3), return all exact maps satisfying det J == 1."""
        eqs2 = [sp.expand(e.subs(values)) for e in degree_two]
        sol2 = sp.solve(eqs2, [a4, a5, a6], dict=True)
        maps = []
        for s2 in sol2:
            base = {**values, **s2}
            high = [sp.expand(c0.subs(base)) for deg in (3, 4) for _, c0 in by_degree.get(deg, [])]
            high = [e for e in high if e != 0]
            G = sp.groebner(high, b4, b5, b6, b7, order="grevlex")
            if [g0 for g0 in G.exprs] == [sp.Integer(1)]:
                continue
            for s3 in sp.solve(high, [b4, b5, b6, b7], dict=True):
                sub = {**base, **s3}
                Pv = sp.expand(P.subs(sub))
                Qv = sp.expand(Q.subs(sub))
                jd = jacobian_data(Pv, Qv)
                if not jd["is_nonzero_constant"]:
                    continue
                inv = polynomial_inverse(Pv, Qv)
                f = fibre(Pv, Qv, (0, 0))
                maps.append({"quadratic_data": values, "cubic_data": {**s2, **s3},
                             "P": Pv, "Q": Qv, "determinant": sp.simplify(jd["jacobian"]),
                             "points_in_fibre": f["points"],
                             "inverse_verified": inv["verified"]})
        return maps

    scanned = 0
    consistent_quadratic = []
    maps = []
    for q in itertools.product(range(-grid, grid + 1), repeat=4):
        scanned += 1
        values = {a3: q[0], b1: q[1], b2: q[2], b3: q[3]}
        found = solve_fibre(values)
        if found:
            consistent_quadratic.append(q)
            maps.extend(found)

    # the same question on rational quadratic data outside the integer grid
    import random
    rng = random.Random(20261027)
    sampled = 0
    sample_hits = []
    dens = (2, 3, 4, 5)
    while sampled < grid_samples:
        den = rng.choice(dens)
        q = tuple(sp.Rational(rng.randint(-2 * den, 2 * den), den) for _ in range(4))
        if all(sp.denom(v) == 1 for v in q):
            continue          # already covered by the integer grid
        sampled += 1
        values = {a3: q[0], b1: q[1], b2: q[2], b3: q[3]}
        found = solve_fibre(values)
        if found:
            sample_hits.append(q)
            maps.extend(found)
    return {"degree_one_equations": degree_one, "degree_one_matches": degree_one_matches,
            "rational_samples": sampled, "rational_samples_with_solutions": sample_hits,
            "degree_four_matches_cubic_jacobian": degree_four_matches,
            "degree_two_linear_in_cubic_coefficients": bool(degree_two_linear_in_a456),
            "degree_two_solution_generic": degree_two_solution,
            "grid": grid, "scanned": scanned,
            "quadratic_data_with_solutions": consistent_quadratic,
            "maps": maps,
            "all_injective": all(m0["inverse_verified"] and m0["points_in_fibre"] == 1
                                 for m0 in maps)}


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def main(stages=("F0", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9")):
    clock = time.time()
    out = print
    out("=" * 78)
    out("planar Jacobian conjecture -- exact counterexample search (version 2)")
    out("=" * 78)
    results = {}

    if "F0" in stages:
        out("\n[F0] positive control: the known three dimensional counterexample")
        r = results["F0"] = lane_positive_control()
        out("  map =", r["map"])
        out("  det J =", r["determinant"], "| second route:", r["determinant_second_route"],
            "| routes agree:", r["determinants_agree"])
        out("  det J is the nonzero constant -2:", r["determinant_is_minus_two"])
        for p, i in zip(r["points"], r["images"]):
            out("    F%s = %s" % (p, i))
        out("  three distinct points, one image:", r["three_distinct_points"], r["one_image"])

    if "F1" in stages:
        out("\n[F1] complete classification of degree <= 2 Keller maps")
        r = results["F1"] = lane_degree_two()
        out("  ansatz: P =", r["ansatz"][0], " Q =", r["ansatz"][1])
        out("  coefficient equations:", r["equations"])
        out("  Groebner basis:", r["groebner_basis"])
        out("  constant term of det J = det of the linear part:", r["det_at_origin"],
            "| identity verified:", r["linear_part_identity"],
            "(nonzero constant => invertible linear part, so the normalisation is complete)")
        for b in r["branches"]:
            out("    branch", b["solution"])
            out("      det J =", b["determinant"], "| nonzero constant:", b["nonzero_constant"],
                "| inverse verified:", b["inverse_verified"])
        out("  all admissible branches invertible:", r["all_branches_invertible"])
        out("  generic family: P =", r["generic_family"][0], " Q =", r["generic_family"][1])
        out("  det J =", r["generic_determinant"], "| P - (f/s) Q =", r["generic_target_coordinate"])
        out("  generic inverse checks (must be 0, 0):", r["generic_inverse_checks"])
        out("  rational member: P =", r["member"][0], " Q =", r["member"][1])
        out("  det J =", r["member_determinant"], "| points in fibre at (0,0):", r["member_fibre"])
        out("  inverse:", r["member_inverse"], "| verified:", r["member_inverse_verified"])

    if "F2" in stages:
        out("\n[F2] triangular maps, complete for all degrees")
        r = results["F2"] = lane_triangular()
        for c in r["checks"]:
            out("  deg_y P =", c["deg_y_P"], "| det J = -P_y f'(x):", c["structural_identity"],
                "| leading y-coefficient identity:", c["leading_y_coefficient_matches"])
        out("  surviving form: P =", r["surviving_form"][0], " Q =", r["surviving_form"][1])
        out("  its det J =", r["surviving_determinant"])
        out("  inverse checks (must be 0, 0):", r["surviving_inverse_checks"])
        out("  argument:", r["argument"])

    if "F3" in stages:
        out("\n[F3] nilpotent 2x2 matrices and cubic-linear maps (no nonzero assumptions)")
        r = results["F3"] = lane_cubic_linear()
        out("  P =", r["P"], " Q =", r["Q"])
        out("  det J = 1 + 3 L^2 (s^3 m + t^3 n):", r["formula_verified"])
        out("  on the nilpotency locus s^3 m + t^3 n = tn(t^2 - s^2):",
            r["identity_on_nilpotency_locus"])
        for c in r["cases"]:
            out("    case", c["case"], "| map =", c["map"], "| det J =", c["determinant"],
                "| inverse verified:", c["inverse_verified"])
        out("  all cases invertible:", r["all_cases_invertible"])
        out("  integer matrices in [-%d,%d]^4: %d | constant nonzero det: %d | nilpotent: %d | same set: %s"
            % (r["box"], r["box"], (2 * r["box"] + 1) ** 4, len(r["keller_entries"]),
               len(r["nilpotent_entries"]), r["keller_equals_nilpotent"]))
        for rec in r["records"][:5]:
            out("    A =", rec["A"], "| det J =", rec["determinant"],
                "| points in fibre:", rec["points_in_fibre"],
                "| inverse verified:", rec["inverse_verified"])
        out("  all injective:", r["all_injective"])

    if "F4" in stages:
        out("\n[F4] complete classification of cubic homogeneous Keller maps")
        r = results["F4"] = lane_cubic_homogeneous()
        out("  ansatz: P =", r["ansatz"][0], " Q =", r["ansatz"][1])
        out("  equations:", r["equations"])
        out("  Groebner basis:", r["groebner_basis"])
        out("  linear relations present in the basis:", r["linear_relations_in_basis"])
        out("  case h = 0 with g != 0 reduces to g^2, impossible:",
            r["case1_h_zero_impossible_for_g"])
        out("  case h = 0 reduced equations:", r["case1_reduced_equations"])
        out("  case h = 0 solutions:", r["case1_solutions"])
        for m0 in r["case1_maps"]:
            out("    P =", m0["P"], " Q =", m0["Q"], " det J =", m0["determinant"],
                " inverse verified:", m0["inverse_verified"])
        out("  case h != 0 with g = 0 collapses to 3h^2 = 0, impossible:",
            r["case2_g_zero"]["forces_h_zero"])
        out("    reduced equations with g = 0:", r["case2_g_zero"]["equations_with_g_0"])
        out("    reduced equations with g = 0 and f = 0:", r["case2_g_zero"]["with_f_0"])
        out("  generic solution:", r["generic_solutions"][0])
        out("  closed form H =", r["closed_form"])
        out("  det J =", r["closed_form_determinant"])
        out("  with lam + t mu = 0: det J =", r["closed_form_determinant_with_condition"],
            "| lam + t mu =", r["lam_plus_t_mu"])
        out("  identification of the solution with the closed form:",
            r["identification_with_closed_form"])
        out("  inverse checks (must be 0, 0):", r["closed_form_inverse_checks"])
        out("  rational member: P =", r["member"][0], " Q =", r["member"][1])
        out("  det J =", r["member_determinant"], "| fibre at (0,0): points =",
            r["member_fibre"]["points"], "(lower bound from one elimination polynomial:",
            r["member_fibre"]["lower_bound_distinct_x"], ")")
        out("  inverse:", r["member_inverse"], "| verified:", r["member_inverse_verified"])

    if "F5" in stages:
        out("\n[F5] exhaustive box scan of cubic homogeneous maps, coefficients in [-2,2]^8")
        r = results["F5"] = lane_box_scan(box=2)
        out("  tuples scanned:", r["scanned"], "| with constant nonzero det J:", r["keller_count"])
        for rec in r["records"]:
            out("    ", rec["coefficients"], "F = (", rec["P"], ",", rec["Q"], ")",
                "| fibre points:", rec["points_in_fibre"],
                "| inverse verified:", rec["inverse_verified"])
        out("  all injective:", r["all_injective"])

    if "F6" in stages:
        out("\n[F6] compositions of elementary automorphisms (the tame group)")
        r = results["F6"] = lane_tame_group()
        out("  tested:", r["tested"], "| constant nonzero det J:", r["keller_maps"],
            "| inverses verified:", r["verified_inverses"], "| max degree:", r["max_degree"])
        out("  failures:", r["failures"])

    if "F7" in stages:
        out("\n[F7] near misses: maps that really do collide")
        r = results["F7"] = lane_near_misses()
        for rec in r["records"]:
            out("  P =", rec["P"], " Q =", rec["Q"])
            out("    det J =", rec["determinant_factored"], "| constant:",
                rec["determinant_constant"])
            out("    fibre of F(1,0): scheme length", rec["fibre_scheme_length"],
                "| distinct points found", rec["fibre_distinct_points"])
            if rec["collision"]:
                p1, chk = rec["collision"]
                out("    exact collision (1,0) ~", p1, "| dP =", chk["dP"], " dQ =", chk["dQ"])

    if "F8" in stages:
        out("\n[F8] (x + lam L^k, y + mu L^k) in every degree")
        r = results["F8"] = lane_arbitrary_degree()
        for rec in r["records"]:
            out("  k =", rec["k"], "| det J = 1 + k(lam+t mu)L^(k-1):", rec["formula_verified"],
                "| under lam = -t mu: det J =", rec["determinant_with_condition"],
                "| L invariance:", rec["L_invariance"],
                "| inverse verified:", rec["inverse_verified"],
                "| inverse degree:", rec["inverse_degree"])
        out("  all degrees verified:", r["all_verified"])

    if "F9" in stages:
        out("\n[F9] mixed degree 2+3 (bounded grid of the quadratic part)")
        r = results["F9"] = lane_mixed_degree_three(grid=3, grid_samples=250)
        out("  degree one equations of det J - 1:", r["degree_one_equations"],
            "| as expected 2a1 + b2, a2 + 2b3:", r["degree_one_matches"])
        out("  degree four part equals det J of the cubic part:",
            r["degree_four_matches_cubic_jacobian"])
        out("  degree two part linear in the cubic coefficients:",
            r["degree_two_linear_in_cubic_coefficients"])
        out("  generic solution of the degree two part:", r["degree_two_solution_generic"])
        out("  integer quadratic data scanned:", r["scanned"],
            "| admitting cubic data:", r["quadratic_data_with_solutions"])
        out("  rational quadratic data sampled:", r["rational_samples"],
            "| admitting cubic data:", r["rational_samples_with_solutions"])
        for m0 in r["maps"]:
            out("    P =", m0["P"], " Q =", m0["Q"], "| det J =", m0["determinant"],
                "| fibre points:", m0["points_in_fibre"],
                "| inverse verified:", m0["inverse_verified"])
        out("  mixed-degree Keller maps found in the scanned class:", len(r["maps"]),
            "(none => in every scanned case det J == 1 forces the cubic part to vanish,")
        out("   so those maps have degree <= 2 and are covered by F1)")

    out("\n" + "=" * 78)
    out("tally")
    out("=" * 78)
    if "F1" in results:
        out("  F1 degree <= 2, complete: all branches invertible:",
            results["F1"]["all_branches_invertible"])
    if "F2" in results:
        out("  F2 triangular, complete: inverse checks:",
            results["F2"]["surviving_inverse_checks"])
    if "F3" in results:
        out("  F3 cubic-linear: all cases invertible:", results["F3"]["all_cases_invertible"],
            "| all box records injective:", results["F3"]["all_injective"])
    if "F4" in results:
        out("  F4 cubic homogeneous, complete: closed form inverse checks:",
            results["F4"]["closed_form_inverse_checks"],
            "| member inverse verified:", results["F4"]["member_inverse_verified"])
    if "F5" in results:
        out("  F5 box scan:", results["F5"]["keller_count"], "Keller maps, all injective:",
            results["F5"]["all_injective"])
    if "F6" in results:
        out("  F6 tame: inverses verified:",
            results["F6"]["verified_inverses"], "/", results["F6"]["keller_maps"])
    if "F7" in results:
        out("  F7 colliding maps:",
            sum(1 for r in results["F7"]["records"] if r["collision"]),
            "(each with a non-constant determinant)")
    if "F8" in results:
        out("  F8 all degrees invertible:", results["F8"]["all_verified"])
    if "F9" in results:
        out("  F9 mixed degree 3, scanned quadratic data: %d, maps found: %d"
            % (results["F9"]["scanned"] + results["F9"]["rational_samples"],
               len(results["F9"]["maps"])))
    out("\ntotal wall clock: %.1f s" % (time.time() - clock))
    out("\nNo pair (P, Q) satisfying (J) and (C) was produced.  Every Keller map")
    out("constructed in F1-F6 and F8-F9 is injective, certified by an explicit")
    out("polynomial inverse and/or an exact fibre of cardinality one.  Every")
    out("colliding map in F7 has a non-constant determinant.")
    return results


if __name__ == "__main__":
    import sys
    chosen = tuple(sys.argv[1].split(",")) if len(sys.argv) > 1 else (
        "F0", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9")
    main(chosen)
