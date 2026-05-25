# D086 — Korobov-lattice Genz MVN CDF with reported standard error (Wave EEEE, v12)

**Status**: Accepted
**Wave**: EEEE (v12)
**Supersedes**: none (extends D078)
**Superseded by**: none

## Context

D078 (v11 Wave WWW) added `genz_mvn_cdf` — the Genz separation-of-variables
estimator of the multivariate-normal CDF `Φ_m(b; R)` — sampled with **pseudo-random**
points (plain Monte-Carlo). Its recorded reopening criterion:

> *"randomised-lattice (Korobov) Genz with error bounds."*

Plain MC has two honest weaknesses: error decays only `O(N^{-1/2})`, and the
routine returns a point estimate with **no usable error estimate**. The Genz
integrand is a product of smooth normal CDFs — exactly the smooth, low-effective-
dimension integrand that lattice rules integrate far better than MC. v12 Wave EEEE
adds a randomly-shifted Korobov lattice rule and a genuine reported standard error.

## Decision

- **`reliability.genz_mvn_cdf_lattice(upper, correlation, n_points=1021,
  n_shifts=12, a=76, seed=0) → GenzLatticeResult`** — a rank-1 **Korobov** lattice
  with generating vector `z = (1, a, …, a^{m-2}) mod N` produces points
  `w_k = frac(k·z/N + Δ)`, evaluated under `n_shifts` **independent random shifts**
  `Δ`. Each shift gives one Genz estimate; the **mean** is the value and the
  **spread across shifts** (`std(ddof=1)/√n_shifts`) is the reported standard
  error. `GenzLatticeResult` carries `value`, `std_error`, `n_points`, `n_shifts`.

- **`reliability.system_reliability_series_lattice(betas, correlation=None, …) →
  (P_f, std_error)`** — the series-system `P_f = 1 − Φ_m(β; R)` with the lattice SE
  propagated through the linear `1 − ·` (parallels `system_reliability_series_exact`).

- A private `_genz_product_estimate(b, chol, w)` kernel holds the separation-of-
  variables product (shared by the lattice driver); `_korobov_generating_vector`
  builds `z`. **`genz_mvn_cdf` (D078) is left untouched** (no regression).

- **`tests/test_korobov_genz_lattice.py`** — six anchors against a high-accuracy
  reference.

## Verification (quantitative anchors)

`tests/test_korobov_genz_lattice.py` (6 passed; adjacent regression on
test_system_reliability + test_genz_mvn_system = 11 passed). The reference for
correlated cases is the **equicorrelation 1-D Gauss-Hermite reduction**
`Φ_m = ∫ ∏_i Φ((b_i+√ρ·t)/√(1−ρ)) φ(t) dt` (exact to quadrature, numpy-only):

1. **independent case exact**: `R=I` ⟹ the integrand is constant ⟹ the estimate
   equals `∏Φ(b_i)` to ≤ 1e-9.
2. **matches the equicorrelation reference within SE**: 4-D, ρ=0.5 — `|value −
   exact| ≤ 4·SE` and `SE < 1e-3`.
3. **beats plain MC at equal budget**: over 20 seeds the lattice RMS error is
   < ⅓ of the pseudo-random Genz MC RMS at the same sample count (measured ≈ 25×
   better at N=1021 in the design probe).
4. **SE is a genuine error estimate**: `|value − exact| ≤ 3·SE` in ≥ 27/30 seeds,
   and SE shrinks as `n_points` grows (251 → 2039).
5. **system wrapper reports SE**: `P_f = 1 − Φ_m(β; R)` cross-checked against the
   exact safe probability within `4·SE`.
6. **determinism** (seeded) and **guards**: `n_shifts < 2` / `n_points < 2` /
   non-SPD `R` raise `SolverError`.

## Honest scope notes

- **The default `(a=76, N=1021)` is one decent small Korobov rule, not a
  certified-optimal generating vector.** Lattice quality depends on `(a, N)`; a poor
  multiplier degrades the gain (the probe saw the advantage drop from ~25× to ~11×
  for `a=306`). I expose `a`/`n_points` and ship a known-good default, but make **no
  claim of optimality** and there is no component-by-component (CBC) construction.
- **The "standard error" is a randomisation estimate, not a deterministic bound.**
  It is the Monte-Carlo standard error *of the random-shift average* — empirically
  it brackets the true error (~3·SE), but it is **not** a guaranteed worst-case
  bound (a true QMC bound needs the integrand's variation / the lattice's worst-case
  error, not computed here). "Error bounds" from the criterion is delivered as a
  *reported standard error*, and I name it as such.
- **Same `O(N·m)` per-shift cost and same dimension-ordering as D078.** The Genz
  estimator's accuracy is sensitive to variable ordering (largest-integration-range
  first is the classic reordering); neither D078 nor this wave reorders. A badly-
  ordered `R` will still converge but slower — for both methods equally.
- **Effective only while the integrand stays smooth/low-effective-dimension.** For
  very high `m` or near-singular `R` the lattice advantage over MC narrows; the SE
  remains valid (it self-reports the larger spread) but the speed-up is not claimed
  to persist.

## Reopening criteria

- **CBC-constructed / tabulated good generating vectors** (or a higher-order /
  interlaced lattice) for certified lattice quality across dimensions.
- **A deterministic QMC error bound** (variation × discrepancy) to replace the
  randomisation SE where a guaranteed bound is required.
- **Genz variable reordering** (sort by integration-range width) shared by both the
  MC and lattice estimators for faster convergence.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional — the Gauss-Hermite reference uses `numpy.polynomial`), 2D/2.5D only,
local `pytest -q` (no network), single-line stderr + `SolverError` status strings,
no CAD/GUI/cloud/full-3D/commercial solvers/LLM, self-deprecation over
self-promotion.
