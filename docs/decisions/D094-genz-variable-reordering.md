# D094 — Genz variable reordering (Genz–Bretz priority ordering) (Wave EEEEE, v13)

**Status**: Accepted
**Wave**: EEEEE (v13)
**Supersedes**: none (extends D078 Genz-MC + D086 Korobov lattice)
**Superseded by**: none

## Context

D086 (v12 Wave FFFF, Korobov lattice Genz) recorded a reopening item:

> *"Variable reordering by integration-range width: order the integration axes so the
> most-constrained variable is handled first; this is the standard Genz–Bretz
> prioritisation that reduces the separation-of-variables estimator's variance, and it
> applies to both the MC (D078) and the lattice (D086) estimator."*

The Genz separation-of-variables estimator runs a sequence of 1-D conditional
integrals. Its variance depends heavily on the *order* of the axes: integrating the
high-probability-mass (loosely bounded) axes early leaves the tightly-bounded,
high-variance axes for last and inflates the spread of the per-sample product. Genz &
Bretz's prioritisation reorders so the **most-constrained axis goes first**.

## Decision

- **`reliability._genz_reorder_cholesky(b, R)`** — the Genz–Bretz **ordered Cholesky**.
  At each column `j` it picks, among the not-yet-placed variables, the one with the
  smallest expected truncated probability `Φ((b_i − Σ_{k<j} L_ik y_k)/√(R_ii − Σ
  L_ik²))`, swaps it into position `j` (in `b`, `R` rows+cols, `L` rows, and the
  permutation), completes the Cholesky column, and sets `y_j` to the **mean of the
  standard normal truncated to (−∞, up_j]** (`= −φ(up_j)/Φ(up_j)`). Returns
  `(b_ordered, L_ordered, perm)`. Raises `SolverError` for a non-SPD `R`.

- **`reliability.genz_mvn_cdf_reordered(upper, correlation, n_samples=20000, seed=0)`**
  — same estimand as `genz_mvn_cdf` (D078) but applies the reordering first, then runs
  the shared `_genz_product_estimate` kernel (the same kernel the D086 lattice uses).

- **`tests/test_genz_reordering.py`** — six anchors.

## Verification (quantitative anchors)

`tests/test_genz_reordering.py` (6 passed; adjacent regression on
`test_genz_mvn_system` + `test_korobov_genz_lattice` + `test_system_reliability`, 17
pass):

1. **converges to exact reference**: on a 6-D equicorrelation (ρ=0.5) problem the
   high-N reordered estimate matches the exact 1-factor 1-D-quadrature reference
   ∫φ(t)ΠΦ((b−√ρt)/√(1−ρ))dt to abs 2e-3.
2. **reordering is a relabelling**: reordered and unordered high-N estimates agree to
   abs 3e-3 — reordering changes convergence, not the answer.
3. **cuts fixed-sample error several-fold (headline)**: on a deliberately badly-ordered
   problem (large bounds first), at fixed N=400 the mean |error| over 60 seeds is
   < ½ the unordered estimator's (measured ratio ≈ 0.11, i.e. ≈ 9× reduction).
4. **priority order**: for equicorrelation the order sorts bounds ascending
   (smallest-mass axis first); `perm` equals the ascending-bound argsort.
5. **full correlation matrix**: on a random full (non-equicorrelation) SPD R, reordered
   and unordered high-N agree to abs 4e-3.
6. **edge cases / guards**: m=1 closed form Φ(b/√R); determinism (same seed ⟹
   identical); shape and non-SPD guards raise single-string `SolverError`.

## Honest scope notes

- **The expected-limit heuristic uses the truncated-normal mean, not the true
  posterior.** `y_j = −φ(up)/Φ(up)` is the *expectation* of the next conditional
  variable, which is the standard Genz–Bretz approximation for the priority score. It
  is a heuristic ordering, not a provably variance-minimal one; on a problem already in
  good order it neither helps nor hurts (the swap leaves it in place).
- **Reordering does not change the estimand** — same value in the limit, so it is not a
  new accuracy result, only a variance reduction. Anchor 3 quantifies the variance win;
  it is not a bias correction.
- **Added as a separate `genz_mvn_cdf_reordered`, not flipped on by default.** D078's
  `genz_mvn_cdf` and `system_reliability_series_exact`, and D086's lattice, are left
  unchanged (no regression). Wiring reordering into the lattice/series estimators is a
  reopening item.
- **The reordered Cholesky recomputes scores in an O(m²) inner loop.** For the moderate
  m (≤ ~10 limit states) of 2.5-D series-system reliability this is negligible; it is
  not optimised for very large m (out of regime).
- **Equicorrelation reference only is "exact".** The full-matrix correctness anchor
  cross-checks against the unordered MC estimator (same unbiased estimand), not an
  independent closed form — there is no closed form for a general full-R MVN CDF (that
  is the whole reason Genz-MC exists).

## Reopening criteria

- **Wire reordering into `genz_mvn_cdf_lattice` and `system_reliability_series_exact`**
  so the production reliability path benefits from the variance reduction.
- **Combine reordering with the Korobov lattice (D086)** — reordering + randomised QMC
  is the strongest published Genz variant.
- **A variance-based priority score** (minimise the conditional variance contribution)
  instead of the expected-limit heuristic, for problems where the mean-based ordering
  is suboptimal.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
