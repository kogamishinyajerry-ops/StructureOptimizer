# D055 — system reliability: series systems + Ditlevsen bounds (Wave ZZ)

**Status**: Accepted
**Wave**: ZZ (v8)
**Supersedes**: none (extends D038's single-limit-state FORM)
**Superseded by**: none

## Context

D038 (FORM/SORM) and D042 (RBTO) handle a **single** limit state. Real structures
fail through one of several modes (series system) or only when several fail
together (parallel). D042's reopening criterion named **system reliability**. v8
Wave ZZ delivers series-system Ditlevsen bounds + the bivariate-normal CDF they
require.

## Decision

`core/reliability.py`:

- `bivariate_normal_cdf(a, b, rho, n_nodes=64)` — Φ₂(a,b;ρ) via the exact
  identity Φ₂ = Φ(a)Φ(b) + ∫₀^ρ φ₂(a,b;r) dr, integrated by Gauss-Legendre
  (`np.polynomial.legendre.leggauss`); numpy-only.
- `system_reliability_series(betas, correlation=None, n_nodes=64)` → dict with
  the simple unimodal bounds (max P_i ≤ P_f ≤ Σ P_i) and the tighter **Ditlevsen**
  second-order bounds, using pairwise joint failures
  P(F_i∩F_j) = Φ₂(−β_i,−β_j; ρ_ij). Components are ordered by descending P_i (the
  ordering that gives Ditlevsen's tightest bounds); the result is clipped to the
  simple bounds.
- `system_reliability_parallel(beta_i, beta_j, rho, n_nodes=64)` — 2-component
  parallel failure P(F_i∩F_j) = Φ₂(−β_i,−β_j;ρ).

## Verification (quantitative)

- **Bivariate CDF** (`test_bivariate_normal_cdf_special_cases`): ρ=0 → Φ(a)Φ(b)
  (1e-12); Φ₂(0,0;ρ) = ¼ + arcsin(ρ)/2π closed form (1e-7); ρ→1 → min(Φ(a),Φ(b))
  (1e-4) — all exact analytical checks.
- **Single mode** (`test_single_mode_series_equals_phi`): a 1-mode series system
  equals Φ(−β) exactly (bounds collapse).
- **Independent series within bounds** (`test_independent_series_within_ditlevsen_bounds`):
  the independent series failure 1−∏(1−P_i) lies within the Ditlevsen bounds,
  and the Ditlevsen bounds are within (tighter than) the simple unimodal bounds.
- **Correlation lowers series failure** (`test_positive_correlation_lowers_series_failure`):
  positive inter-mode correlation (ρ=0.8) gives a series failure strictly below
  the independent case — overlapping failure modes.
- **Parallel** (`test_parallel_independent_is_product`): independent → P_i·P_j
  (1e-10); ρ→1 → min (1e-4). + contracts. 6 tests, all green. Adjacent
  `test_form_sorm` + `test_nataf_reliability` + `test_nataf_general_marginals`
  (26) unchanged.

## Honest scope notes

- The bivariate CDF clamps |ρ| to 0.999999, so a *perfectly* correlated series
  system does **not** collapse to exactly Φ(−β) (residual ≈2% at ρ=1, β=2): the
  near-singular φ₂ integrand at ρ=1 is the limit of the quadrature. The exact
  ρ→1 behaviour (→ min) is verified to 1e-4, and the meaningful claim
  (correlation lowers series failure) is exact in direction; perfect-correlation
  collapse is not claimed.
- **Series** Ditlevsen bounds for any m; **parallel** only for the 2-component
  case (m>2 parallel needs the multivariate normal CDF — a trivariate-plus
  integral is the reopening item).
- Inter-mode correlations ρ_ij = α_iᵀα_j come from the FORM MPP directions; this
  module takes them as a given matrix rather than recomputing FORM per mode
  (the caller pairs `form_hlrf` results with this).

## Reopening criteria

- m>2 parallel / general system events (cut sets) via the multivariate normal CDF.
- Coupling to FORM: a helper that runs `form_hlrf` per mode and assembles ρ_ij
  from the MPP unit vectors.
- System-reliability-based TO (drive a topology to a target system β).

## Red lines

numpy-only (`np.polynomial.legendre.leggauss`, `math.erf`), 2D-agnostic,
single-line stderr (`SolverError`). FORM/SORM/Nataf paths are unchanged; the
system-reliability code is additive.
