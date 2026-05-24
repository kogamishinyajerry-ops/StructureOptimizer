# D069 — Archimedean-copula Rosenblatt: Clayton / Frank (Wave NNN, v10)

**Status**: Accepted
**Wave**: NNN (v10)
**Supersedes**: none (extends D061)
**Superseded by**: none

## Context

D061's `RosenblattTransform` is **MVN-only**: its dependence structure is fully
described by a covariance, so it cannot represent **tail dependence** (e.g. two
loads that spike together far more often than a Gaussian copula predicts).
D061's recorded reopening criterion was *non-Gaussian Rosenblatt
(Clayton/Frank copulas)*. v10 Wave NNN implements bivariate Archimedean copulas.

## Decision

- **`reliability.ArchimedeanCopula(family, theta)`** (+ `clayton_copula`,
  `frank_copula` constructors) — a bivariate copula with:
  - `cdf(u1,u2)` — Clayton `(u₁^−θ+u₂^−θ−1)^(−1/θ)`, Frank via `log1p`/`expm1`;
  - `conditional_cdf(u1,u2) = ∂C/∂u₁` — the Rosenblatt conditional CDF;
  - `conditional_ppf(u1,w)` — its closed-form inverse in `u₂`
    (Clayton `[u₁^−θ(w^(−θ/(θ+1))−1)+1]^(−1/θ)`; Frank via `log1p`);
  - `kendall_tau()` — closed form: Clayton `θ/(θ+2)`, Frank `1−4/θ(1−D₁(θ))`
    with `D₁` the Debye function evaluated by **numpy Simpson** (`_debye1`, no
    scipy).
  Guards: Clayton `θ>0`, Frank `θ≠0`, unknown family.

- **`reliability.CopulaRosenblattTransform(marginals, copula)`** (+
  `build_copula_rosenblatt`) — Rosenblatt transform of two arbitrary marginals
  coupled by an Archimedean copula. `x_to_u`: `u_i=F_i(x_i)`, `w₂=C_{2|1}(u₂|u₁)`,
  `z=Φ⁻¹(w)`; `u_to_x` is the sequential inverse. Reuses `Marginal`'s
  standard-normal maps for `F`/`F⁻¹` (`_marginal_cdf`/`_marginal_ppf`) and mirrors
  `RosenblattTransform`'s `wrap_limit_state` so `form_hlrf` runs unchanged.

- **`tests/test_copula_rosenblatt.py`** — seven quantitative anchors (below).

## Verification (quantitative anchors)

`tests/test_copula_rosenblatt.py` (all pass; adjacent regression on
test_form_sorm / test_nataf_general_marginals / test_nataf_reliability /
test_rbto / test_rosenblatt / test_system_rbto / test_system_reliability):

1. **conditional CDF round-trip**: `conditional_ppf(u₁, conditional_cdf(u₁,u₂))
   = u₂` to ≤ 1e-9 (Clayton ≈ 1.4e-10, Frank ≈ 2.8e-15).
2. **full transform round-trip**: `u → x → u` recovers `z` to ≤ 1e-7 (normal +
   lognormal marginals, both families).
3. **θ → 0 → independence**: `C_{2|1}(u₂|u₁) → u₂` and `C(u₁,u₂) → u₁·u₂` with
   error bounded by `2θ`.
4. **Clayton Kendall τ closed form**: `θ/(θ+2)` exact; matches empirical Kendall
   τ of 1500 conditional-method samples to < 0.03.
5. **Frank Kendall τ closed form**: `1−4/θ(1−D₁(θ))` matches empirical to < 0.03.
6. **input guards**: Clayton θ≤0 / Frank θ=0 / unknown family / ≠2 marginals
   raise `SolverError`.
7. **drives FORM**: the transform plugs into `form_hlrf` via `wrap_limit_state`
   and returns a finite β with `0 < p_failure < 1`.

## Honest scope notes

- **Bivariate only** (`n_vars = 2`). A general d-dimensional Archimedean
  Rosenblatt needs the (d−1)-fold conditional via the generator's derivatives;
  this wave does the 2-D case where the conditionals are closed form.
- Only **Clayton and Frank** families. Gumbel (upper-tail) has no closed-form
  conditional inverse (needs a 1-D root solve) and is left out; other families
  (Joe, AMH) likewise.
- Frank's Kendall τ uses the **Debye function** approximated by a fixed
  2000-point Simpson rule — accurate but not analytic; very small |θ| relies on
  the explicit `t/(eᵗ−1) → 1` limit at `t = 0`.
- The copula couples exactly **two** marginals; mixing copula-dependent pairs
  with extra independent variables (block structure) is not wired here.
- Like D061 this assumes the joint is *known* (marginals + copula + θ given); it
  does not *fit* a copula to data.

## Reopening criteria

- **d-dimensional Archimedean Rosenblatt** (nested/hierarchical generators or the
  full conditional chain).
- **Gumbel / other families** (upper-tail dependence) with a robust 1-D inverse
  for the conditional CDF.
- **Copula parameter estimation** (method-of-moments via Kendall τ, or MLE) to
  drive the transform from data rather than a supplied θ.
- **Copula-RBTO**: feed `CopulaRosenblattTransform` into the RBTO driver so a
  reliability-constrained design accounts for tail-dependent loads.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (the Debye integral
is numpy Simpson — no scipy), 2D/2.5D only, local `pytest -q` (no network),
single-line stderr + `SolverError` status strings, no CAD/GUI/cloud/full-3D/
commercial solvers/LLM, self-deprecation over self-promotion.
