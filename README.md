# exact-formula-search

Exact symbolic search for counterexamples to algebraic, finite-group and planar
determinant identities.

The package turns a natural language statement into a formal target, enumerates
frontiers of candidate search approaches, generates and executes a search
program for each frontier in an isolated subprocess, verifies every reported
candidate with independent exact recomputations, critiques the result, and
repairs the search frontier when something is rejected.

Everything is done with SymPy exact arithmetic: rational numbers, algebraic
numbers, symbolic simplification, Groebner bases, resultants and polynomial
coefficient dictionaries. No floating point certification is accepted anywhere
in the pipeline.

## Installation

```
pip install .
```

Python 3.11 or newer and `sympy>=1.12` are required.

## Command line

```
exact-formula-search "find a counterexample for x^2 + 1 = x^2"
```

```
x = 0
```

Without arguments the request is read from standard input:

```
echo "In every finite group, x^2 = e" | python -m exact_formula_search
```

Exit codes: `0` a counterexample was found and printed, `2` the request could not
be formalized, `3` the search produced no printable result, `1` an unexpected
internal failure.

## Library

```python
from exact_formula_search import run, SearchBudget

print(run("refute the identity alpha + x = x", SearchBudget(max_seconds=30)))
```

```
alpha = -1
x = -1
```

## Request kinds

| Kind | Recognised from | Result |
| --- | --- | --- |
| algebraic identity counterassignment | any statement containing a parsable equality | an assignment of exact values to the variables |
| finite group identity countermodel | group wording with a group word on both sides | an operation table, an identity element and an assignment |
| planar constant determinant collision | refutation wording together with a Jacobian request, a two dimensional dimension marker and an explicit characteristic zero request (`over the rationals`, `over q`, `characteristic zero`) | two polynomial components and two distinct exact points; the characteristic zero case is open, so this lane reports exhaustion |
| finite field Jacobian refutation | refutation wording together with a Jacobian request and a two dimensional dimension marker, without a characteristic zero request | a finite field GF(p^k) of positive characteristic, two polynomial components, the constant nonzero determinant modulo p and two distinct points with a common image |

## Pipeline

1. `formalization` normalises the text, extracts variables, constraints and
   declared bounds, and parses the mathematical sides into SymPy expressions.
2. `frontiers` builds the initial set of search approaches and mutates them
   later, always keeping a stable signature so that nothing is repeated.
3. `code_generation` renders a small, structurally validated program that calls
   `generated_runtime.run_generated_search` with the frontier and the problem.
4. `execution` runs that program in a forked subprocess with restricted imports
   and resource limits, then rebuilds candidates and checks their provenance.
5. `verification` re-derives the certificate through independent paths:
   determinant by differentiation and by coefficient dictionaries, collisions by
   direct evaluation and by coefficient evaluation, finite field collisions by
   monomial and Horner evaluation over GF(p^k), group words by two evaluators,
   domain exclusions and denominator obligations.
6. `critique` rejects anything that was certified by a single path, that
   contains decimal text, or whose provenance does not match.
7. `repair` maps every rejection reason onto a concrete frontier mutation.
8. `output_format` prints the counterexample.

## Web interface

```
python -m exact_formula_search.web --host 0.0.0.0 --port 8000
```

The same server is installed as the `exact-formula-search-web` console script.
It serves a single page browser client from the same origin as the JSON API and
streams every search step as server-sent events.

### HTTP API

| Method | Path | Body | Result |
| --- | --- | --- | --- |
| `GET` | `/api/health` | - | version, asset fingerprint, uptime |
| `GET` | `/api/presets` | - | prepared statements, budgets and the expected terminal outcome |
| `POST` | `/api/formalize` | `{"query": "...", "budget": {...}}` | the formalized target without running a search |
| `POST` | `/api/search/stream` | `{"query": "...", "budget": {...}}` | `text/event-stream` of search events |

The budget object accepts `time_seconds`, `max_frontier_visits`,
`max_verified_candidates`, `max_mutation_rounds`, `execution_timeout_seconds`,
`max_candidates_per_frontier`, `max_instances_per_solve`, `max_point_pairs` and
`max_group_order`. Every field is range checked; out of range values are
rejected with `400` and a `budget_field_out_of_range:<field>` error code.

### Event stream

`search_started`, `formalization`, `frontier_queued`, `frontier_visit`,
`code_generated`, `execution_completed`, `verification_completed`,
`critique_completed`, `repair_triggered` describe progress. Exactly one terminal
event closes a search:

| Terminal event | Meaning |
| --- | --- |
| `search_completed` | an exact certificate was verified and critiqued |
| `symbolic_proof` | the exact difference of the two sides vanishes identically, so no counterassignment exists |
| `search_exhausted` | the declared budget was consumed, with statistics, lane coverage and the exhaustion reason |
| `search_cancelled` | the client closed the connection |
| `error` | the engine failed; the message carries the exception summary |

Every certificate event carries `audit` rows (float-free arithmetic, pole and
domain exclusions, dual-path determinant, dual-path group words, repeat
verification, independent recomputation, critique cleanliness, provenance
fingerprint, worker SHA-256) and an `exports` bundle: a standalone LaTeX
document, a standalone SymPy reproduction script, the full JSON certificate and
a suggested file name. The browser client recomputes the SHA-256 digest of the
received worker source and shows the result next to the server value.

Certificate payloads never contain floating point numbers: elapsed times are
serialised as exact decimal strings and every algebraic value is canonical,
exact text.

### Example certificates

`docs/example-refutation.json` and `docs/example-refutation.tex` are the
verbatim exports of a live run of the statement
`cáfold meg az x/(x-1) = 1 azonosságot`: the engine returned the exact
counterassignment `x = 0`, whose left value is `0` and right value is `1`, with
every audit row passing and the pole `x - 1` respected.

`docs/example-jacobi-refutation.json` and `docs/example-jacobi-refutation.tex`
are the verbatim exports of a live run of the statement
`cáfold meg a 2D Jacobi-sejtést`. The engine formalizes this as
`finite_field_jacobian_refutation`, walks the finite field ladder GF(2), GF(4),
GF(8), ... and returns a certified refutation over GF(2):

* the map is `F(x, y) = (x + y^2, x^2 + y)`,
* its Jacobian determinant reduces to the nonzero constant `1` modulo the
  characteristic, certified by a derivative-matrix path and by an independent
  coefficient-dictionary path,
* the distinct points `P = (0, 1)` and `Q = (1, 0)` both map to `(1, 1)`, so the
  map is not injective over GF(2) and therefore is not a polynomial
  automorphism.

The certificate states its own scope: it refutes the Jacobian statement over the
finite field GF(2) in positive characteristic. The general two dimensional
Jacobi conjecture in characteristic zero is open and remains untouched by this
witness; the characteristic zero lane (`refute the two dimensional Jacobian
conjecture over the rationals`) still reports an honest exhaustion. Exhaustion
never claims falsity.

### Browser client

The client in `exact_formula_search/web/static/` is compiled ahead of time from
the JSX sources in `exact_formula_search/web/jsx/` and is committed. It renders
KaTeX, streams the event log, draws the exact certificates (assignment tables,
Cayley tables, Jacobian components with collision rows) and offers LaTeX, SymPy
and JSON export.

On load the interface immediately runs the Jacobi refutation preset
`cáfold meg a 2D Jacobi-sejtést`, so the first thing the page shows is a found
counterexample - the certified finite field refutation above - with its exact
certificate, verification audit and exports. Its result card displays the field,
the irreducible modulus, the map, the constant determinant modulo the
characteristic, both collision witnesses and a scope notice stating that the
characteristic zero case stays open. Every other preset, including the plain
algebraic ones (`cáfold meg az x/(x-1) = 1 azonosságot`), runs from the same
composer. The result header states the outcome explicitly:
`refutation found · cáfolat megvan` for a certificate, `no refutation within
budget · nincs cáfolat` for an honest exhaustion report, and `no counterexample
exists · nincs cáfolat` when the exact difference already vanishes. React, ReactDOM and KaTeX are vendored under
`static/vendor/` (see the licence table in `static/vendor/README.md`); there is
no network dependency at runtime.

Rebuilding the client after editing a `.jsx` file:

```
npx --yes @babel/standalone --version
node exact_formula_search/web/jsx/build.mjs
```

`build.mjs` transforms every `.jsx` source with the Babel React preset and
writes the result to `static/js/`. Icons and splash images are generated by
`python tools/build_brand_assets.py`.

## Testing

```
python -m pytest
```
