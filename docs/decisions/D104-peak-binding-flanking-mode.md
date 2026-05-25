# D104 — peak-binding flanking-mode: anti-resonance valley placement (Wave GGGGGG, v14)

**Status**: Accepted
**Wave**: GGGGGG (v14)
**Supersedes**: none (closes D091's twice-deferred peak-binding criterion, extends D083/D075)
**Superseded by**: none

## Context

D083 (v12) named, and D091 (v13) **deferred for the second time**, a peak-*binding*
formulation:

> *"minimising J(ω_op) genuinely raises a flanking in-band resonance (anti-resonance
> pole–zero interlacing), so the constraint binds and in-loop re-gridding changes the
> design."*

D091's probe minimised the response near the fundamental ω₁ and found stiffening
*lowered* the whole transfer function — the objective and the peak constraint were
**aligned**, so neither binding nor an in-loop-vs-fixed design difference could be shown.
It deferred honestly rather than fake it.

**The missing ingredient (this wave): placing ω_op in the anti-resonance valley *between*
two modes.** A fresh probe (`minimize_dynamic_compliance`, ω_op = ½(ω₁+ω₂)) shows
minimising J(ω_op) there **raises** the flanking band peak around ω₂ by **+55 % (24×10)**
and **+16 % (48×20)** — the pole–zero coupling D091 sought. D091 simply looked in the
wrong place.

## Decision

- **`freq_response.peak_binding_mma(config, mesh, omega_op, flanking_lo, flanking_hi,
  peak_limit, ..., regrid=True)`** → `PeakBindingTOResult`. Minimises the **dynamic**
  compliance `J(ω_op) = |fᵀû(ω_op)|²` at a fixed operating frequency in the
  anti-resonance valley, subject to an in-loop re-gridded **flanking-resonance** peak
  constraint over `[flanking_lo, flanking_hi]` + volume, via the proven D066/D075 MMA
  pair:

      g₁(x) = J_flank(x)/J_lim − 1 ≤ 0   (flanking in-band peak, p-norm)
      g₂(x) = mean(x) − vf ≤ 0           (volume)

  The objective sensitivity comes from `dynamic_compliance_sensitivity` (scaled by its
  initial value for MMA conditioning). With `regrid=True` the flanking band is re-located
  each iteration by `adaptive_band_sample` (tracking the moving flanking resonance);
  `regrid=False` freezes it at the initial flanking location.

## Verification (quantitative anchors)

`tests/test_peak_binding.py` (6 passed; adjacent regression on `test_inloop_adaptive_band`
+ `test_bandwidth_adaptive_band` + `test_dynamic_compliance_to` + `test_adaptive_band_peak`):

1. **the coupling D091 could not show**: unconstrained `peak_binding_mma` lowers J(ω_op)
   yet **raises** the dense-sweep flanking peak above the initial (`> init·1.05`; probe
   6.16e4 → 7.73e4).
2. **constraint changes the design**: the constrained design's flanking peak is `< 0.7×`
   the unconstrained one (probe 1.73e4 vs 7.73e4 — 4.5×) and the density field differs.
3. **in-loop re-gridding changes the design**: `regrid=True` vs `False` densities differ
   by `> 5 %` (probe 27 %), and the tracked flanking resonance moves `> 2 %` over the run
   (probe 155 k → 147 k).
4. **feasible vs dense sweep**: the regrid design's true flanking peak ≤ `peak_limit·1.15`.
5. **determinism**: identical inputs ⟹ bit-identical densities.
6. **guards**: `ω_op ≤ 0` / inverted flanking range / nonpositive limit raise
   single-string `SolverError`.

## Honest scope notes

- **The flanking constraint is NOT strictly KKT-binding, and J is NOT sacrificed.** This
  is the key honesty point and the reason D104 does *not* over-claim D091's full wording.
  Probes at limits 0.3 / 0.5 / 0.8 × initial show the constraint never sits *active* at
  the limit and the constrained runs actually reach a **lower** J(ω_op) than the
  unconstrained run (≈1.7e3 vs 6.6e3). The constrained problem finds a basin low in
  **both** objective and flanking peak; the flanking constraint acts as a
  **trajectory / basin selector** that steers the optimiser away from the
  flanking-raising path the bare objective takes — not as a hard Pareto trade-off where
  reducing the flank costs J.
- **So what *is* delivered vs D091**: (a) the *coupling* — min J(ω_op) raises the flanking
  resonance — is now demonstrated (D091's actual blocker); (b) constraining it *changes
  the design*; (c) in-loop re-gridding *changes the design*. What remains genuinely open
  is a regime with a **strictly active** flanking constraint and a measurable J sacrifice.
- **Modest tracked drift (~5 %).** The flanking resonance moves less than the
  fundamental did in D075 (~100 %); the re-gridding-vs-stale *design* difference (27 %) is
  the stronger evidence that tracking matters here.
- **Smoke 24×10 mesh in the test** (fast); the conflict was confirmed on 48×20 too (+16 %)
  via the standalone probe. The effect is *not* a fine-mesh artefact — it appears on the
  smoke mesh, strongest there.
- **Rayleigh damping, light β=2e-6** (sharp, trackable, finite — cf. Wave TTT undamped
  singularity). Single flanking mode; multi-flanking-mode bands are out of scope.

## Reopening criteria

- **Strictly active flanking constraint with J sacrifice** — a mesh/limit/ω_op regime (or
  a reduced design freedom) where suppressing the flank provably costs objective, so the
  KKT multiplier is positive and the constraint sits at the limit.
- **Multi-flanking-mode** bands (one tracked window per flanking resonance).
- **Wire the dynamic-objective + flanking-constraint** into the unified MMA driver family
  rather than a standalone function.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
