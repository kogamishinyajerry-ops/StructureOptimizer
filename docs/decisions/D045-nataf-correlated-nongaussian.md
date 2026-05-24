# D045 — Nataf transform: correlated / non-Gaussian uncertainty (Wave PP)

**Status**: Accepted
**Wave**: PP (v7)
**Supersedes**: none (extends D038's independent-Gaussian FORM)
**Superseded by**: none

## Context

v6 Wave II (D038) delivered FORM/SORM, but under the standard assumption that
the physical variables are **independent Gaussians** (`standardize_gaussian`
just subtracts the mean and divides by std, componentwise). D038's reopening
criterion named the next step explicitly: *Nataf / Rosenblatt transform* for
**correlated** and **non-Gaussian** variables. v7 Wave PP delivers the Nataf
model so the existing HL-RF machinery applies unchanged to those problems.

## Decision

`core/reliability.py` gains:

- `_standard_normal_ppf(p)` — inverse standard-normal CDF Φ⁻¹ (Acklam rational
  approximation + one Halley refinement against the erf-based Φ, ~1e-12). The
  marginal transform's backbone; numpy/stdlib only.
- `Marginal(kind, param_a, param_b)` — `normal(μ, σ)` or `lognormal(λ, ζ)` (λ, ζ
  = mean/std of the underlying normal `ln X`). Provides `to_standard_normal(x) =
  Φ⁻¹(F(x))` and `from_standard_normal(z) = F⁻¹(Φ(z))`.
- `build_nataf(marginals, correlation_x=None)` → `NatafTransform`. Computes the
  **equivalent normal correlation** Rᵤ from the physical Rₓ via closed forms
  (`_equivalent_normal_correlation`): normal–normal ρ_z = ρ_x; lognormal–lognormal
  ρ_z = ln(1 + ρ_x·c)/(ζ_iζ_j) with c = √((e^{ζ_i²}−1)(e^{ζ_j²}−1)). Then
  Rᵤ = L·Lᵀ (Cholesky).
- `NatafTransform.x_to_u / u_to_x / wrap_limit_state` — the X↔U maps and a helper
  that wraps a physical-space limit state `g(x)` into a U-space `g(u)` for
  `form_hlrf`.
- `correlated_gaussian_reliability(mean, std, correlation, g, **form_kwargs)` —
  convenience driver: build the Gaussian-marginal Nataf and run FORM.

## Verification (quantitative)

- **Φ⁻¹ inverts Φ** (`test_ppf_inverts_cdf`, `test_ppf_known_quantiles`): round-trip
  to 1e-10 across [−4, 4]; Φ⁻¹(0.975) = 1.95996398 to 1e-9.
- **Correlated-Gaussian closed form** (`test_correlated_gaussian_linear_limit_state_matches_closed_form`):
  for g(x) = a₀ − aᵀx with X ~ N(μ, Σ), FORM through the Nataf reproduces
  β = (a₀ − aᵀμ)/√(aᵀΣa) to rel 1e-6 on a 3-var problem with a non-trivial
  correlation matrix — the headline anchor for §4.
- **Correlation matters** (`test_correlation_changes_beta_vs_independent`): positive
  correlation of like-signed loads inflates the variance of their sum → strictly
  lower β than the independent case.
- **Lognormal equivalent correlation** (`test_lognormal_equivalent_correlation_closed_form`):
  Rᵤ[0,1] matches the lognormal closed form to 1e-12, and the correlated x→u→x
  round-trips to 1e-10.
- **Lognormal marginal** (`test_lognormal_marginal_round_trip`): F⁻¹(Φ(Φ⁻¹(F(x))))
  = x to rel 1e-12.
- **Reduction** (`test_identity_correlation_reduces_to_standardize`): an
  identity-correlation Gaussian Nataf gives exactly `standardize_gaussian` —
  inherits D038's guarantees in the independent case.
- **Contracts** (`test_nataf_contracts`): shape mismatch / non-symmetric /
  non-PD / mixed-marginal-with-correlation → `SolverError`. 8 tests, all green.
  Adjacent `test_form_sorm` (10) unchanged.

## Honest scope notes

- Marginals supported: **normal** and **lognormal**. These are the two with
  exact closed-form equivalent-correlation corrections, so every correlated case
  is verified analytically rather than by a numerical Nataf integral. Other
  marginals (Weibull, Gumbel, …) would need the general Nataf double integral
  (Gauss–Hermite quadrature) — deferred, since adding them without a closed-form
  reference would weaken the verification.
- **Mixed** normal/lognormal pairs with non-zero correlation are *rejected*
  (`nataf_mixed_marginal_correlation_unsupported`) rather than silently using an
  approximation — there is no closed form here and a wrong ρ_z would be a hidden
  inaccuracy. Independent mixed marginals (off-diagonal 0) are fine.
- This is the **transform**, not a reliability-based TO driver over non-Gaussian
  variables; combined with D042 (RBTO) that is a further step.

## Reopening criteria

- General marginals (Weibull/Gumbel/empirical) → Nataf integral via Gauss–Hermite
  quadrature for ρ_z, validated against published tables.
- Rosenblatt transform (conditional-CDF chaining) for cases where the full joint
  CDF is known rather than marginals + correlation.
- Correlated RBTO: feed `correlated_gaussian_reliability` into the D042 volume
  bisection.

## Red lines

numpy-only (`np.linalg.cholesky`, `np.linalg.solve`, `math.erf`), 2D-agnostic
(reliability is dimension-free), single-line stderr via `SolverError`. The v5/v6
independent-Gaussian FORM/SORM path is unchanged; the Nataf code is additive.
