# D098 — d-Gumbel copula wired into system_reliability_series (Wave AAAAAA, v14)

**Status**: Accepted
**Wave**: AAAAAA (v14)
**Supersedes**: none (extends D093 d-Gumbel + D078 Genz-exact series)
**Superseded by**: none

## Context

D093 (v13 Wave DDDDD) added the d-dim exchangeable **Gumbel** copula but recorded:

> *"Not yet wired into `system_reliability_series` — substituting it for the
> Gaussian/Clayton dependence in the series-system estimator is a separate integration
> step (reopening)."*

D078's `system_reliability_series_exact` models the mode dependence with a **Gaussian**
correlation matrix `R`. But correlated structural failure modes typically cluster in the
**upper tail** (joint extremes) — exactly the regime a Gumbel copula captures and a
Gaussian one understates. v14 (integration milestone) wires the d-Gumbel into the
production series-system estimator.

## Decision

- **`reliability.system_reliability_series_copula(betas, copula)`** — a series system is
  safe iff **all** modes are safe, so modelling the joint *safety* with a copula `C` on
  the per-mode safe-probabilities `u_k = Φ(β_k)`:

      P(all safe) = C(u_1, …, u_m),   P_f = 1 − C(Φ(β_1), …, Φ(β_m)).

  `copula` is any d-variate copula with `.dim` and `.cdf(u)` —
  `ExchangeableGumbelCopula` (upper-tail, θ≥1) or `ExchangeableClaytonCopula`
  (lower-tail). Raises `SolverError` on dim mismatch / empty modes.

- **`tests/test_series_copula_reliability.py`** — six anchors.

## Verification (quantitative anchors)

`tests/test_series_copula_reliability.py` (6 passed; adjacent regression on
`test_system_reliability` + `test_genz_mvn_system` + `test_d_gumbel_copula`, 17 pass):

1. **backward-compat bit-exact (integration铁律)**: Gumbel θ=1 reproduces the
   independent series `1 − Π Φ(β_k)` to abs 1e-14.
2. **matches the prior Gaussian path**: Gumbel θ=1 also equals D078's
   `system_reliability_series_exact(R=I)` (abs 2e-4; Genz is MC).
3. **positive dependence lowers P_f monotonically**: P_f strictly decreasing over
   θ ∈ {1, 1.5, 3, 10}, and any θ>1 is below the independent value.
4. **comonotone limit**: as θ→∞ (θ=50) P_f → max_k Φ(−β_k) to abs 1e-3 (the series
   fails when the weakest mode does); P_f ≥ that floor for finite θ.
5. **family-agnostic independence**: a Clayton copula at θ=1e-4 recovers the
   independent P_f to abs 1e-5.
6. **guards**: copula-dim mismatch / empty modes raise single-string `SolverError`.

## Honest scope notes

- **Exchangeable single-θ dependence only.** The copula is exchangeable (one θ for all
  pairs); heterogeneous pairwise dependence would need a nested or vine copula (D085's
  nested Clayton is two-level; a nested *Gumbel* is a reopening item). The Gaussian
  `system_reliability_series_exact` (D078) keeps the full-matrix `R` capability that
  this exchangeable-copula path does not have.
- **Series only.** Parallel / general system topologies are not handled by this copula
  path (the safe-event = all-safe logic is series-specific). Parallel-system copulas are
  a reopening item.
- **No FORM-correlation → copula-θ calibration.** The caller supplies the copula (hence
  θ) directly; mapping FORM MPP-direction correlations `α_iᵀα_j` onto a Gumbel θ (e.g.
  via a Kendall-τ match) is not provided — θ is an explicit modelling choice, honestly
  not inferred from the limit-state geometry.
- **Reuses D093's exact CDF** (no new approximation): P_f is exact given the copula;
  the only error is whatever the copula's own `.cdf` carries (Gumbel/Clayton CDFs here
  are closed-form exact).

## Reopening criteria

- **FORM-correlation → copula-θ calibration** (Kendall-τ or tail-dependence match) so a
  user with FORM `α` directions gets a principled Gumbel θ.
- **Nested / heterogeneous-dependence series systems** (per-cluster θ, mirroring D085's
  nested Clayton) for mixed upper-tail structure.
- **Parallel / general-topology copula reliability** (the all-safe logic is series-only).

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
