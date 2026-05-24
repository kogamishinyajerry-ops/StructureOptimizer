# D061 — Rosenblatt transform for a known joint distribution (Wave FFF)

**Status**: Accepted
**Wave**: FFF (v9)
**Supersedes**: none (complements D045/D053 Nataf)
**Superseded by**: none

## Context

D045 (Nataf, closed form) and D053 (Nataf, Gauss-Hermite) map correlated/non-Gaussian
marginals to independent standard normals using *marginals + a correlation matrix*
(an assumed Gaussian copula). When the **full joint** distribution is known, the
exact transform is **Rosenblatt's**: the chain of conditional CDFs. D053's reopening
criterion named **"Rosenblatt transform (conditional CDFs) for known joint
distributions"**. Wave FFF delivers it for the multivariate-normal joint — the
canonical known-joint case, and the one with an exact analytical cross-check.

## Decision

`core/reliability.py`:

- `RosenblattTransform(mean, cov)` with `x_to_u`, `u_to_x`, `wrap_limit_state`
  (mirroring `NatafTransform`). It applies the chain
  `u_k = Φ⁻¹(F_{k|1..k-1}(x_k | x_1..x_{k-1}))`. For a multivariate normal the
  conditionals are Gaussian, so `Φ⁻¹∘F_{k|..}` collapses to the standardised
  conditional `u_k = (x_k − μ_{k|..})/σ_{k|..}`, with the conditional mean/variance
  computed by the Schur-complement formulas `μ_{k|..} = μ_k + Σ_{k,:k}Σ_{:k,:k}⁻¹
  (x_{:k}−μ_{:k})`, `σ²_{k|..} = Σ_{kk} − Σ_{k,:k}Σ_{:k,:k}⁻¹Σ_{:k,k}`.
- `build_rosenblatt_normal(mean, cov)` — SPD validation via Cholesky.

## Verification (quantitative)

- **Equals Cholesky whitening** (`test_property_rosenblatt_equals_cholesky_whitening`):
  over 30 random SPD covariances, the conditional-CDF map equals `L⁻¹(x−μ)` to
  1e-10 — two independent derivations (sequential Schur conditionals vs Cholesky
  forward substitution) agree at machine precision. Headline + property test.
- **Round-trip** (`test_rosenblatt_round_trip`): `x→u→x` and `u→x→u` are the
  identity to 1e-10.
- **Exact decorrelation** (`test_rosenblatt_decorrelates_exactly`): `Cov(U) =
  L⁻¹ Σ L⁻ᵀ = I` to 1e-10.
- **Agrees with Nataf** (`test_rosenblatt_matches_nataf_for_unit_variance_gaussians`):
  for unit-variance Gaussian marginals (so Σ = R), Rosenblatt and Nataf give the
  same U to 1e-10.
- **FORM β** (`test_rosenblatt_form_beta_matches_closed_form`): FORM through the
  Rosenblatt-wrapped linear limit state equals the closed form
  `(a₀−aᵀμ)/√(aᵀΣa)` and the Nataf-based `correlated_gaussian_reliability` (rel
  1e-6). 6 tests, all green. Adjacent `test_nataf_reliability` +
  `test_nataf_general_marginals` + `test_form_sorm` + `test_system_reliability`
  (32) unchanged.

## Honest scope notes

- Implemented for the **multivariate-normal** joint only. For a Gaussian copula
  with non-Gaussian marginals the Rosenblatt map factorises as
  copula-Rosenblatt-on-Z then `x_i = F_i⁻¹(Φ(z_i))` — which for a Gaussian copula
  coincides with Nataf, so it adds nothing there; genuinely-non-Gaussian joints
  (e.g. a Clayton/Frank copula, or a known multivariate density) are the
  reopening item.
- The transform is **ordering-dependent** (Rosenblatt always is): different
  variable orderings give different U-space limit states (and slightly different
  FORM iterates), though the same β for a linear state. The natural input ordering
  is used.
- No tail/conditioning safeguards beyond the SPD check; near-singular Σ stresses
  the conditional-variance `> 0` guard (`rosenblatt_nonpositive_conditional_variance`).

## Reopening criteria

- Non-Gaussian known joints: Rosenblatt for a Gaussian copula with arbitrary
  marginals, then for Archimedean copulas (Clayton/Frank/Gumbel) with closed-form
  conditional CDFs.
- Ordering heuristics (most-to-least informative) for better FORM conditioning.
- SORM on the Rosenblatt-wrapped state (the curvature is already available from
  `sorm_breitung`).

## Red lines

numpy-only (`np.linalg.solve`/`cholesky`), distribution-space (no mesh), single-line
stderr (`SolverError`: `rosenblatt_cov_shape_mismatch`,
`rosenblatt_cov_not_symmetric`, `rosenblatt_cov_not_positive_definite`,
`rosenblatt_nonpositive_conditional_variance`). All Nataf/FORM/SORM paths are
unchanged; the Rosenblatt code is additive.
