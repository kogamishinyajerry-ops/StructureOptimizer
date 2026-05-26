# D115 — mixture-copula system reliability with general non-normal marginals (Wave BBBBBBBB, v16)

**Status**: Accepted
**Wave**: BBBBBBBB (v16)
**Supersedes**: none (closes D111's reopening; generalises D098/D111 `system_reliability_series_copula`)
**Superseded by**: none

## Context

D098 (d-Gumbel series copula) and D111 (multi-family mixture) fixed each mode's
safe-probability to the **standard-normal** tail `u_k = Φ(β_k)`. D111 recorded as a
reopening criterion:

> *"General non-normal marginals through the mixture (full Rosenblatt with per-mode
> arbitrary marginal distributions)."*

Real limit-state margins are frequently non-normal — Weibull material strength, Gumbel
extreme load, lognormal. D115 generalises the per-mode safe-probability to any
:class:`Marginal` while keeping the copula dependence model intact.

## Decision

- **`system_reliability_series_copula_marginals(margins, points, copula)`** — each mode `k`
  carries a `Marginal` (normal/lognormal/weibull/gumbel) and an evaluation point `x_k`; the
  safe-probability is the **marginal CDF** `u_k = F_k(x_k) = Φ(Marginal.to_standard_normal(x_k))`
  (reusing the engine's existing Nataf marginal map), and `P_f = 1 − C(u_1,…,u_m)`.
- The dependence `C` is any d-variate copula with `.dim`/`.cdf` (Gumbel / Clayton / a
  `MixtureCopula` from D111).

**Why it reduces exactly**: `Marginal("normal",0,1).to_standard_normal(β) = β` (no
round-trip), so `u_k = Φ(β_k)` and the function is **bit-identical** to
`system_reliability_series_copula` on normal marginals.

## Verification (quantitative anchors)

`tests/test_copula_marginals.py` (6 passed; adjacent regression on
`test_series_copula_reliability` + `test_multi_family_copula` + `test_nataf_reliability`,
21 pass):

1. **byte-exact reduction**: all-`N(0,1)` marginals + `points=β` reproduce
   `system_reliability_series_copula` with **exact equality**.
2. **general-marginal correctness**: with the independence copula (Gumbel θ=1) the series
   `P_f` equals `1 − ∏ F_k(x_k)` for the true Weibull/Gumbel CDFs (abs 1e-10).
3. **non-normal changes P_f**: a Weibull-strength mode gives a different `P_f` than a
   normal mode at the same physical point (>1e-3) — the marginal tail matters.
4. **copula still binds with general marginals**: upper-tail Gumbel θ>1 lowers `P_f` vs the
   independence copula at the same (Weibull, Gumbel, lognormal) marginals.
5. **monotonicity**: raising every evaluation point (more margin) raises each `u_k` and
   strictly lowers `P_f`.
6. **guards**: point/marginal count mismatch, copula-dim mismatch, no-modes raise
   `SolverError`.

## Honest scope notes

- **Marginals enter only through the per-mode safe-probability `u_k`**; the copula models
  the *dependence* on the uniform scale. This is the standard copula-marginal separation
  (Sklar), **not** a full joint-physical Rosenblatt with a Nataf-transformed correlation
  matrix — the dependence is specified directly as the copula, not derived from a physical
  `R_x`. Wiring a Nataf-equivalent copula from a physical correlation is a reopening.
- **`u_k` via the Φ∘Φ⁻¹ round-trip** through `to_standard_normal` (reuses existing code).
  For non-normal marginals this incurs ≤~1e-12 round-trip error vs the closed-form CDF
  (validated in anchor 2); for normal marginals there is no round-trip (bit-exact).
- **CDF-level, series system** only (the D111 scope) — mixture Rosenblatt *sampling* and
  parallel/general system events remain separate reopenings (D111 / addressed by D119).
- Only the four engine marginals (normal/lognormal/weibull/gumbel) are supported.

## Reopening criteria

- **Nataf-derived copula** from a physical correlation matrix `R_x` (couple D045/D053's
  equivalent-normal correlation with the copula path).
- **Mixture Rosenblatt sampling** with general marginals (importance sampling).
- **Per-mode points as random** (full convolution) rather than fixed evaluation points.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio optional),
2D/2.5D only, local `pytest -q` (no network), single-line stderr + `SolverError` status
strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM, self-deprecation over
self-promotion.
