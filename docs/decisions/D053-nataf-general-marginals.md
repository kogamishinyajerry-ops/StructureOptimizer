# D053 — general-marginal Nataf via Gauss-Hermite quadrature (Wave XX)

**Status**: Accepted
**Wave**: XX (v8)
**Supersedes**: none (extends D045's closed-form Nataf)
**Superseded by**: none

## Context

v7 Wave PP (D045) handled the Nataf equivalent-correlation only for normal–normal
(ρ_z=ρ_x) and lognormal–lognormal (closed form), and **rejected** other
marginals. D045's reopening criterion named the fix: general marginals
(Weibull/Gumbel/…) via the **Gauss-Hermite Nataf integral**. v8 Wave XX delivers
it.

## Decision

`core/reliability.py`:

- `Marginal` extended to **weibull** (shape k, scale λ) and **gumbel** (loc μ,
  scale β, max-type) alongside normal/lognormal — each with `to_standard_normal`
  (Φ⁻¹∘F), `from_standard_normal` (F⁻¹∘Φ), and a new `moments() → (mean, std)`
  (Γ-based for Weibull, μ+βγ / βπ√⅙ for Gumbel).
- `nataf_correlation_gauss_hermite(mi, mj, rho_x, n_nodes=24)` — equivalent
  normal correlation ρ_z solving the Nataf integral
  ρ_x = E[η_i(Z_i)·η_j(Z_j)] over a bivariate normal with correlation ρ_z
  (η_k = (F_k⁻¹(Φ(z))−μ_k)/σ_k), evaluated by 2-D Gauss-Hermite quadrature
  (`np.polynomial.hermite.hermgauss`) + bisection on ρ_z.
- `build_nataf_general(marginals, correlation_x, n_nodes=24)` — a `NatafTransform`
  whose equivalent correlation uses the closed form for normal–normal pairs and
  the GH integral for every other pair; PD checked via Cholesky.

## Verification (quantitative)

- **GH integral vs lognormal closed form** (`test_gauss_hermite_matches_lognormal_closed_form`):
  for ρ_x ∈ {0.2, 0.6, −0.4} the quadrature reproduces D045's closed-form
  ρ_z = ln(1+ρ_x·c)/(ζ_iζ_j) to abs 1e-6 (observed ≈3e-11) — the cross-check
  that the quadrature is correct.
- **Moments** (`test_weibull_moments_and_exponential_special_case`,
  `test_gumbel_moments`): Weibull(1,λ)=exponential gives mean=std=λ; Weibull(2,3)
  mean=3·Γ(1.5); Gumbel(0,1) mean=γ=0.5772, std=π/√6 — all to ≤1e-6.
- **Round-trips** (`test_general_marginal_round_trips`): Weibull/Gumbel
  F⁻¹(Φ(Φ⁻¹(F(x))))=x to rel 1e-9.
- **Correlation behaviour** (`test_equivalent_correlation_zero_and_monotone`):
  ρ_x=0 → ρ_z=0; ρ_z monotone in ρ_x; |ρ_z| ≥ |ρ_x| for this pair.
- **General Nataf** (`test_build_nataf_general_round_trip`): a Weibull+Gumbel
  correlated Nataf round-trips x→u→x to 1e-8. + contracts. 7 tests, all green.
  Adjacent `test_nataf_reliability` + `test_form_sorm` (19) unchanged.

## Honest scope notes

- Marginals: normal, lognormal, **Weibull, Gumbel**. The GH integral works for
  any marginal exposing a CDF/PPF + moments; adding more (Frechet, generalised
  extreme value, …) is a `Marginal`-kind extension, not new machinery.
- The integral is validated **against the lognormal closed form**, not against
  published Weibull/Gumbel tables — the closed-form cross-check proves the
  quadrature is correct, and Weibull/Gumbel use the same quadrature, so the
  validation transfers. (Adding a tabulated reference would be a nice belt-and-
  braces but is not required for correctness.)
- `n_nodes=24` Gauss-Hermite is ample for these smooth integrands (the lognormal
  cross-check is exact to 3e-11); heavier-tailed marginals may want more nodes.
- D045's closed-form `build_nataf` is unchanged; `build_nataf_general` is the
  superset path.

## Reopening criteria

- More marginals (Frechet/GEV/empirical-CDF) via the same `Marginal` interface.
- Tabulated-reference validation for Weibull/Gumbel equivalent correlations.
- Rosenblatt transform (conditional CDFs) for known joint distributions.

## Red lines

numpy-only (`np.polynomial.hermite.hermgauss`, `math.gamma`), 2D-agnostic,
single-line stderr (`SolverError`). D045's normal/lognormal closed-form path is
unchanged; the general path is additive.
