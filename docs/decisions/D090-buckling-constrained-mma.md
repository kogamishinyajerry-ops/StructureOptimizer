# D090 — buckling-constrained MMA: λ_crit ≥ λ_safety (Wave AAAAA, v13)

**Status**: Accepted
**Wave**: AAAAA (v13)
**Supersedes**: none (extends D082)
**Superseded by**: none

## Context

D082 (v12 Wave AAAA) derived the **design-grade** buckling sensitivity (the ∂u/∂ρ
adjoint) and used it as an *ascent* objective in `maximize_buckling_load`. Its
recorded reopening criterion:

> *"Buckling-*constrained* MMA (λ_crit ≥ λ_safety as a third inequality with
> compliance + volume), the production use case."*

Maximising λ_crit at fixed volume is rarely the real goal; the real goal is a
**stiff** structure that is also **safe against buckling** — minimise compliance
subject to `λ_crit ≥ λ_safety`. v13 Wave AAAAA delivers that.

## Decision

- **`buckling.buckling_constrained_mma(config, mesh, lambda_safety, vf=None,
  max_iter=40, change_tol=1e-3, filter_radius=None, init_densities=None)`** —
  minimise SIMP static compliance subject to the proven D066 two-constraint pair

      g₁(x) = 1 − λ_crit(x) / λ_safety ≤ 0      (buckling: λ_crit ≥ λ_safety)
      g₂(x) = mean(x) − vf ≤ 0                   (volume)

  via `mma_step`. The compliance gradient is `dc/dρ_e = −dscale_e·uₑᵀkₑuₑ`; the
  buckling-constraint gradient is the **design-grade** `−dλ/dρ / λ_safety`
  (`design_grade_buckling_sensitivity` — the analysis-grade gradient points the
  wrong way, D082). All gradients density-filtered. Returns
  `BucklingConstrainedTOResult` (densities + compliance/λ/volume histories +
  λ_safety + converged).

- **`tests/test_buckling_constrained.py`** — five anchors, with the buckling-free
  baseline being the *same driver* with an inactive constraint (consistent
  reference).

## Verification (quantitative anchors)

`tests/test_buckling_constrained.py` (5 passed; adjacent regression on
test_design_grade_buckling + test_buckling = 11 passed):

1. **binds + conflicts**: with `λ_safety = 1.5 × λ_free` (λ_free = the buckling-free
   compliance optimum's λ_crit), the constrained design reaches `λ_crit ≥ 0.95 ×
   λ_safety` and `λ_crit > 1.3 × λ_free`, **at a strictly higher compliance** than
   the free optimum (probe: λ_crit 14.3 → 21.2 vs λ_safety 21.5, compliance +6.7 %).
2. **volume feasible**: `mean(ρ) ≤ vf + 0.02`.
3. **slack degeneration**: `λ_safety = 0.5 × λ_free` (inactive) reproduces the
   buckling-free compliance/λ to within 2 %/5 %.
4. **determinism**.
5. **guard**: `λ_safety ≤ 0` raises `SolverError`.

## Honest scope notes

- **Single lowest mode, no mode-tracking — inherited from D082.** The constraint
  follows the lowest `λ` each step. Buckling-constrained TO is prone to **mode
  switching** (the active mode changes identity) and **repeated eigenvalues** (the
  sensitivity is non-smooth at multiplicity); this driver does neither k-lowest
  aggregation nor sub-gradient handling. On the smoke cantilever the lowest mode is
  well separated, so it is stable here — not a claim about fine meshes.
- **Near-binding, not exactly binding.** At 40 iterations the constraint settles at
  ~99 % of λ_safety (the test allows ≥ 95 %); MMA asymptotes to the active
  constraint rather than hitting it exactly. More iterations tighten it; I do **not**
  claim an exactly-active constraint.
- **The free baseline is this driver with an inactive constraint**, not an
  independent compliance minimiser — chosen deliberately so the "compliance cost"
  comparison is apples-to-apples (same MMA, same filter, same mesh). It is therefore
  a *relative* statement (constrained > unconstrained on the same machine), not an
  absolute optimality claim.
- **`g_penalty` void-mode relaxation (D082) is left at its default** here; for fine
  meshes where spurious localized modes bite, the constraint would need the
  continuation schedule D082 reopened.

## Reopening criteria

- **Mode-tracking + k-lowest aggregation** (KS/p-norm over the smallest modes) for
  robustness through mode switches and multiplicities in the *constrained* setting.
- **Continuation on λ_safety / `g_penalty`** for fine meshes.
- **Combined stress + buckling constraints** (this driver + the D074 qp-stress
  constraint together) for a genuinely multi-constraint manufacturable optimum.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
