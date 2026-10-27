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
| planar constant determinant collision | refutation wording together with a Jacobian request and a two dimensional dimension marker | two polynomial components and two distinct exact points |

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
   direct evaluation and by coefficient evaluation, group words by two
   evaluators, domain exclusions and denominator obligations.
6. `critique` rejects anything that was certified by a single path, that
   contains decimal text, or whose provenance does not match.
7. `repair` maps every rejection reason onto a concrete frontier mutation.
8. `output_format` prints the counterexample.

## Testing

```
python -m pytest
```

## Planar Jacobian search (added later)

`scripts/jc_planar_search.py` is an independent, self contained exact search for a
counterexample to the *two dimensional* Jacobian conjecture, plus a written report:

* `scripts/jc_planar_search.py` — lanes F0–F9, exact SymPy only,
* `reports/planar_search_transcript.txt` — full run (about 14 minutes),
* `reports/jacobian_2d_report.md` — what is proved, what is only scanned,
* `reports/self_critique.md` — the critique of the first version and the fixes,
* `tests/test_planar_search.py` — fast regression tests.

No counterexample is produced; the lanes that are complete (degree <= 2, triangular,
cubic-linear, cubic homogeneous, one linear form in every degree) all prove
invertibility with explicit polynomial inverses.  Run it with

```
python scripts/jc_planar_search.py
python scripts/jc_planar_search.py F1,F4      # selected lanes
```
