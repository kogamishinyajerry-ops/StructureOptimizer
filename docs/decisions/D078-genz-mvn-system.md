# D078 — exact multivariate system P_f via the Genz MVN-CDF (Wave WWW, v11)

**Status**: Accepted
**Wave**: WWW (v11)
**Supersedes**: none (extends D055 / D071)
**Superseded by**: none

## Context

D055 (and D071's correlated-system RBTO) computed series-system failure
probability via **Ditlevsen second-order bounds** — a *bracket*
`[P_lower, P_upper]` built from pairwise `bivariate_normal_cdf` (Φ₂). D055's
recorded reopening criterion:

> *"full correlation matrix; exact multivariate system P_f (Genz)."*

Ditlevsen bounds use only pairwise joint failure probabilities, so they cannot
return a single exact value and the bracket can be wide when modes are strongly
correlated. The exact series P_f needs the full **m-variate** normal CDF
`Φ_m(b; R)` with the complete correlation matrix `R`. **Genz's (1992)
separation-of-variables Monte Carlo** estimates `Φ_m` for an arbitrary SPD `R`,
numpy-only. v11 Wave WWW delivers it.

## Decision

- **`reliability.genz_mvn_cdf(upper, correlation, n_samples=20000, seed=0) →
  float`** — the multivariate-normal CDF `Φ_m(b; R) = P(Z ≤ b)`, `Z ~ N(0,R)`,
  via Genz. Cholesky-factor `R = L Lᵀ` (lower `L`); with lower bounds `−∞` the
  truncated integral separates so the estimator averages a product over uniform
  samples `w ∈ [0,1]^{m−1}`:

      e₁ = Φ(b₁/L₁₁);  y_{i-1} = Φ⁻¹(w_{i-1}·e_{i-1});
      e_i = Φ((b_i − Σ_{j<i} L_ij y_j)/L_ii);   Φ_m ≈ mean(Π_i e_i).

  Vectorised over samples (`np.vectorize` of the module's existing scalar Φ / Φ⁻¹
  for numerical consistency). Raises `SolverError` for non-SPD `R` or shape
  mismatch.

- **`reliability.system_reliability_series_exact(betas, correlation=None,
  n_samples=20000, seed=0) → float`** — the **exact** (Genz-MC) series-system
  failure probability `P_f = 1 − Φ_m(β; R)` (safe event = all modes safe), a
  single value that lies inside D055's Ditlevsen bracket.

- **`tests/test_genz_mvn_system.py`** — five quantitative anchors.

## Verification (quantitative anchors)

`tests/test_genz_mvn_system.py` (5 passed; adjacent regression on
test_system_reliability / test_reliability / test_correlated_system_rbto /
test_rbto = 39 passed):

1. **Genz reduces to the exact bivariate Φ₂**: at m = 2 the Genz estimator
   (40000 samples) matches the exact Gauss-Legendre `bivariate_normal_cdf` to
   ≤ 1e-3 across three (b₁,b₂,ρ) cases (measured ≈ 4e-5–2e-4).
2. **Genz exact for independent R = I**: `Φ_m(b; I) = Π Φ(b_i)` to ≤ 1e-12 (the
   off-diagonal-free Cholesky makes every sample's product the exact answer).
3. **m = 1 collapses to univariate Φ** to 1e-12.
4. **exact series P_f within the Ditlevsen bounds**: with a full rank-deficient-
   then-nudged 4×4 `R` (random FORM α directions), `system_reliability_series_exact`
   = 4.13e-2 sits inside the bracket `[4.09e-2, 4.15e-2]` (1 % MC slack), and the
   bracket is non-trivial (lower < upper).
5. **determinism** (same seed → identical) + **non-SPD / shape** raise
   `SolverError`.

## Honest scope notes

- **Genz is a Monte-Carlo estimate, not a closed form.** It converges to the
  exact `Φ_m` as `n_samples → ∞`; at the default 20000 samples the standard error
  is ≈ 1e-3–1e-4 for the tested dimensions. "Exact" means *unbiased and
  convergent* (vs Ditlevsen's structurally-approximate bracket), **not**
  bit-exact. The result is seeded for determinism; changing `seed` or
  `n_samples` perturbs it at the MC-error level.
- **Plain Monte Carlo, not a randomised lattice / quasi-MC rule.** Genz's
  published method uses a scrambled Korobov lattice for ~order-of-magnitude
  faster convergence; this implementation uses plain pseudo-random samples for
  simplicity. Higher accuracy ⇒ more samples (cost is linear). A lattice upgrade
  is a reopening item.
- **Accuracy degrades with dimension and strong correlation.** The product
  estimator's variance grows as `m` rises and as `R` approaches singularity; the
  tests cover m ≤ 4 with a nudged-SPD `R`. Very high `m` or near-perfectly-
  correlated modes need many more samples.
- **`R` must be SPD.** A rank-deficient correlation (e.g. raw `ααᵀ` with fewer
  FORM dimensions than modes) makes the Cholesky fail; the test nudges
  `0.98·R + 0.02·I`. Surfacing a built-in ridge / nearest-SPD projection is a
  reopening item, deliberately not done here (it would hide ill-conditioning).
- The series-system formula assumes **FORM-linearised** limit states (Gaussian
  safety margins with `R_ij = α_iᵀα_j`), inheriting D055's linearisation; the
  Genz step adds no extra approximation beyond the MC error.

## Reopening criteria

- **Randomised lattice / quasi-MC (scrambled Korobov)** for the Genz integral, to
  reach a target accuracy with far fewer samples + a reported error estimate.
- **Reported standard error** alongside the point estimate (sample variance of
  `Π e_i`), so callers can size `n_samples` to a tolerance.
- **Parallel-system and general cut-set/min-path P_f** via the same MVN-CDF
  (intersection / inclusion-exclusion), beyond the series case.
- **Nearest-SPD / ridge projection** option for rank-deficient `R`, with an
  explicit warning rather than a silent fix.
- **Variable ordering** (descending β) to reduce the Genz estimator variance, as
  the bounds already do for tightness.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
