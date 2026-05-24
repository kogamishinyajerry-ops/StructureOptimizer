# D071 — correlated system-mode driven RBTO (Wave PPP, v10)

**Status**: Accepted
**Wave**: PPP (v10)
**Supersedes**: none (extends D063)
**Superseded by**: none

## Context

D063 (`system_rbto_simp`) bisected the volume fraction for the lightest design
meeting a **series-system** reliability target, but treated the failure modes as
**statistically independent** (`P_f = 1 − ∏(1 − P_i)`). Real failure modes share
load uncertainty and therefore correlate. D063's recorded reopening criterion was
*correlated system modes via `system_reliability_series(ρ)`*. v10 Wave PPP
implements it.

## Decision

- **`rbto._correlated_system_beta(d_nominal, d_allows, load_covs, rho_modes)`** —
  builds the equicorrelation matrix `R = (1−ρ)I + ρ·11ᵀ` from a scalar inter-mode
  correlation and computes the series-system index through
  `reliability.system_reliability_series`, whose Ditlevsen second-order bounds use
  the **bivariate normal CDF Φ₂** (`bivariate_normal_cdf`). The point estimate is
  the bound midpoint. At `ρ = 0` the bounds collapse to the exact independent
  value, so this reduces to D063's `_system_beta`.

- **`rbto.correlated_system_rbto_simp(config, mesh, d_allows, beta_target,
  rho_modes=0.0, load_covs=None, vf_low, vf_high, vf_tol, max_iter)`** — the same
  volume-fraction bisection as `system_rbto_simp`, but driven by
  `_correlated_system_beta`. Returns the existing `SystemRBTOResult`. Guards add
  `rho_modes ∈ [0,1)`.

- **`tests/test_correlated_system_rbto.py`** — five quantitative anchors (below).

## Verification (quantitative anchors)

`tests/test_correlated_system_rbto.py` (all pass; adjacent regression on
test_system_rbto / test_rbto / test_system_reliability = 20 passed):

1. **β helper degenerates at ρ=0**: `_correlated_system_beta(…, 0.0)` equals
   `_system_beta(…)` to < 1e-9 (β and P_f), because the Ditlevsen bounds collapse
   to `1 − ∏(1 − P_i)` exactly.
2. **direction correct**: at a fixed nominal displacement, β_system increases
   monotonically with `rho_modes` (0.0→0.9 gives 2.4764→2.4985 on the probe) —
   positive correlation reduces the union failure probability.
3. **full RBTO degenerates at ρ=0**: `correlated_system_rbto_simp(…, ρ=0)` ==
   `system_rbto_simp(…)` (feasibility, volume, β_system, densities) to < 1e-9.
4. **correlation → lighter/equal feasible volume**: at the same β_target the
   ρ=0.8 design's volume ≤ the ρ=0 design's (tighter reliability), and a feasible
   design satisfies `β_system ≥ β_target`.
5. **input guards**: `rho_modes` ≥ 1, < 0, and empty modes raise `SolverError`.

## Honest scope notes

- The correlation is a **single scalar `rho_modes`** (equicorrelation across all
  mode pairs), not a full per-pair matrix — adequate for the common "shared load"
  case but not general. A full `correlation` matrix argument is a small extension.
- The system P_f is the **midpoint of the Ditlevsen second-order bounds**, not an
  exact multivariate integral. For 2 modes the bounds collapse to the exact value
  (so 2-mode results are exact); for ≥3 modes the midpoint carries the bound gap.
- The correlation ρ is a **modelling input**, not derived from FORM MPP direction
  cosines `αᵢᵀαⱼ` — the displacement limit states here are scalar (a single
  random load scale per mode), so there are no MPP vectors to dot. Tying ρ to
  actual shared random variables is future work.
- Restricted to `rho_modes ∈ [0,1)`: negative (competing) correlation and the
  ρ→1 fully-dependent limit are excluded (the latter is numerically singular).
- Parallels `system_rbto_simp`'s bisection (the codebase's own
  `rbto_simp`/`system_rbto_simp` convention) rather than refactoring it — HHH is
  untouched, zero regression risk.

## Reopening criteria

- **Full correlation matrix** (per-pair ρ_ij) and **FORM-derived correlation**
  from shared random variables (αᵢᵀαⱼ) instead of a scalar modelling input.
- **Exact multivariate system P_f** (e.g. Genz) for ≥3 modes rather than the
  Ditlevsen midpoint.
- **Parallel / general system** topologies (cut-sets, k-out-of-n) beyond the
  series union.
- **Copula-correlated modes** feeding the D069 `CopulaRosenblattTransform` for
  tail-dependent joint mode failure.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (Φ₂ is numpy
Gauss-Legendre), 2D/2.5D only, local `pytest -q` (no network), single-line stderr
+ `SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
