# D116 — CBC deterministic vector wired into the Genz MVN CDF estimator (Wave CCCCCCCC, v16)

**Status**: Accepted
**Wave**: CCCCCCCC (v16)
**Supersedes**: none (closes D112's reopening; complements D086 `genz_mvn_cdf_lattice`)
**Superseded by**: none

## Context

D112 (v15) built the deterministic CBC machinery (`korobov_worst_case_error`,
`cbc_korobov_generating_vector`) as a **standalone certificate** and recorded as a reopening:

> *"Wire the CBC `z` into `genz_mvn_cdf_lattice` as an optional deterministic generating
> vector (replacing the single-`a` Korobov vector), reporting `e(z)` alongside the estimate."*

D086's `genz_mvn_cdf_lattice` uses a textbook Korobov vector `(1,a,…)` under **random
shifts** and reports a *statistical* `std_error`. D116 wires D112's deterministic CBC vector
into the Genz estimator.

## Decision

- **`genz_mvn_cdf_cbc(upper, correlation, n_points=1021, weights=None)`** — estimates
  `Φ_m(b; R)` with a **single unshifted** rank-1 lattice whose generating vector is built
  **CBC** (`cbc_korobov_generating_vector`, greedily minimising the worst-case error). The
  estimate is **seed-free / byte-exact reproducible** (no RNG), and the rule's
  **deterministic worst-case error certificate** `e(z)` (`korobov_worst_case_error`) is
  reported instead of a randomisation `std_error`.
- **`GenzCBCResult`** = `value` + `worst_case_error` + `n_points` + `generating_vector`.
- `weights` default to `γ_j = 1/(j+1)²` (standard decaying product weights of the α=1
  weighted-Korobov space the CBC vector targets).
- **Pure addition**: D086 `genz_mvn_cdf_lattice` and D078 `genz_mvn_cdf` are **unchanged**
  (no regression by construction).

## Verification (quantitative anchors)

`tests/test_genz_cbc.py` (6 passed; adjacent regression on `test_genz_mvn_system` +
`test_deterministic_qmc`, 11 pass):

1. **deterministic / seed-free**: two calls give a bit-identical `value` and generating
   vector (no RNG) — unlike D086's lattice which needs a seed.
2. **m=1 exact**: returns `Φ(b/√R)` exactly, with zero worst-case error.
3. **converges to Gauss–Hermite reference**: refining `N` drives the estimate to an
   independent one-factor GH equicorrelated reference (abs error < 5e-4 by `N≈2039`, and
   shrinking with `N`).
4. **uses the CBC vector + reports certificate**: the generating vector equals
   `cbc_korobov_generating_vector(m−1, N, γ)`; `worst_case_error` equals
   `korobov_worst_case_error(z, N, γ)` and is **≤** the textbook Korobov vector's.
5. **certificate decays with N**: `e(z)` decreases monotonically (127→2039).
6. **guards**: non-SPD `R` and `n_points < 2` raise `SolverError`.

## Honest scope notes

- **`e(z)` certifies the lattice *rule* worst-case quality** over the unit ball of the
  weighted-Korobov space — it is **not** a tight a-posteriori error bound on *this* Genz
  integrand (whose space-norm is not computed). The practical guarantee on the estimate is
  **convergence** (anchor 3) + **determinism** (anchor 1); the certificate is the rule's
  certified quality, reported honestly as such.
- **Single unshifted lattice** (no randomisation) ⟹ no statistical error estimate; that is
  the deliberate trade for determinism. For a statistical `std_error`, D086's randomly-shifted
  `genz_mvn_cdf_lattice` remains the tool (kept unchanged).
- **Plain (un-reordered) Cholesky**, matching D086's lattice setup (not D094's reordering);
  combining CBC with Genz–Bretz reordering is a reopening.
- **Default weights `1/(j+1)²`** are a tuning choice for the CBC target, not part of the
  estimand (any `z` yields a valid lattice rule converging to the same integral).

## Reopening criteria

- **CBC + Genz–Bretz variable reordering** (`_genz_reorder_cholesky`) combined.
- **Integrand-norm bound** to turn `e(z)` into a tight a-posteriori error bound on the CDF.
- **Wire `genz_mvn_cdf_cbc` into `system_reliability_series_lattice`** as a deterministic
  reliability path.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio optional),
2D/2.5D only, local `pytest -q` (no network), single-line stderr + `SolverError` status
strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM, self-deprecation over
self-promotion.
