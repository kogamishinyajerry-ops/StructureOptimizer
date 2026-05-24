# D063 — system-reliability-based TO (target system β) (Wave HHH)

**Status**: Accepted
**Wave**: HHH (v9)
**Supersedes**: none (couples D042 RBTO + D055 system reliability)
**Superseded by**: none

## Context

D042 (Wave MM) drives the volume fraction to a target reliability index β for a
**single** displacement limit state. D055 (Wave ZZ) added series-system reliability
(Ditlevsen bounds + bivariate-normal CDF). D055's reopening criterion named the
coupling: **"system-reliability-based TO (drive a topology to a target system β)"**.
Wave HHH delivers it.

## Decision

`core/rbto.py`:

- `system_rbto_simp(config, mesh, d_allows, beta_target, load_covs=None, ...)` →
  `SystemRBTOResult`. Each failure mode `i` is a displacement limit state with
  allowable `d_allows[i]` and an **independent** load factor `s_i ~ N(1,
  load_covs[i])`. For a candidate volume fraction the min-compliance design's
  nominal displacement `d_nom` gives per-mode `β_i = (d_allow_i − d_nom)/(cov_i·
  d_nom)` (the D042 closed form via `displacement_reliability`); the series-system
  failure is `P_f,sys = 1 − ∏(1 − P_f,i)` and `β_sys = Φ⁻¹(1 − P_f,sys)`. More
  material lowers `d_nom`, raising every `β_i` and `β_sys`, so the same volume
  bisection as D042 finds the lightest design with `β_sys ≥ beta_target`.
- `_system_beta(d_nominal, d_allows, load_covs)` helper returns
  `(β_sys, P_f,sys, per_mode_βs)`.

## Verification (quantitative)

- **Meets target + harder than single mode** (`test_system_rbto_meets_target_and_harder_than_single_mode`):
  the bisection reaches `β_sys ≥ target` (observed vf 0.413, β_sys 2.06 ≥ 2.0) and
  `β_sys < min(β_i)` (observed 2.06 < 2.09) — an independent 2-mode series system
  is harder than either mode alone.
- **Reduces to D042** (`test_single_mode_reduces_to_rbto`): a single mode gives the
  same volume fraction and β as `rbto_simp` (exact, 1e-9).
- **Volume monotone in target** (`test_volume_monotone_in_target_beta`): the
  selected vf is non-decreasing in `beta_target` (observed 0.403 at β=1.5 ≤ 0.434
  at β=3.0).
- **Consistent with D055** (`test_system_pf_within_ditlevsen_bounds`): the exact
  independent series failure probability lies within the D055 `system_reliability_series`
  Ditlevsen bounds. 5 tests, all green. Adjacent `test_rbto` +
  `test_system_reliability` (15) unchanged.

## Honest scope notes

- **Modes are treated as independent** (series failure `1 − ∏(1 − P_i)`). Real
  modes driven by a shared load are correlated; using `system_reliability_series`
  with an inter-mode correlation matrix as the driver metric is the natural
  extension (the bounds are already consistent — see the D055 anchor). Independence
  is the conservative-but-clean choice here.
- The reliability knob is still the **volume fraction** of a min-compliance design
  (the same as D042) — the topology is not itself reliability-shaped per mode; a
  per-mode load-case-weighted topology is a deeper coupling (cf. D060 multi-load).
- Each mode is the linear displacement limit state of D042; nonlinear or
  stress-based system modes are future work.
- The bisection assumes monotonicity of `β_sys` in vf (true for these
  displacement modes); a non-monotone metric would need a different search.

## Reopening criteria

- Correlated system modes: drive on `system_reliability_series(betas, ρ_ij)`
  (Ditlevsen) rather than the independent product, with `ρ_ij` from shared loads.
- Per-mode topology shaping (multi-load-case reliability) rather than a single
  min-compliance design scaled by volume.
- Nonlinear / stress / buckling system limit states.

## Red lines

numpy-only, 2D/2.5D, single-line stderr (`SolverError`: `system_rbto_no_modes`,
`system_rbto_cov_shape_mismatch`, plus the reused `rbto_*` codes). `rbto_simp` and
the D055 system-reliability functions are unchanged; `system_rbto_simp` is additive.
