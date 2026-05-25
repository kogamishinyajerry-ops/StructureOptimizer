# D083 — in-loop adaptive band re-gridding: tracking a moving resonance (Wave BBBB, v12)

**Status**: Accepted
**Wave**: BBBB (v12)
**Supersedes**: none (extends D075, completes its deferral)
**Superseded by**: none

## Context

D075 (v11 Wave TTT) added `adaptive_band_sample` (bisection-toward-peak frequency
sampling) and `peak_constrained_mma` (minimise compliance s.t. an in-band
forced-response peak ≤ limit *and* volume ≤ vf). But `peak_constrained_mma` pins
the constraint to a **fixed** `band_omegas` chosen *up front*. D075's recorded
reopening criterion:

> *"in-loop adaptive re-gridding so the peak constraint tracks the moving
> resonance instead of a band fixed up front."*

The natural frequencies move as material redistributes. A probe on the smoke
cantilever measured the fundamental drifting **+99 %** (36 867 → 73 545 rad/s)
over a compliance-min optimisation. A band frozen at the *initial* resonance
slides completely off-resonance: on the final design it reports **6.3 %** of the
true (dense-sweep) peak — a 94 % under-report. The p-norm constraint then policing
the wrong frequencies is the defect D075 flagged. v12 Wave BBBB closes it.

## Decision

- **`freq_response.adaptive_peak_constrained_mma(config, mesh, peak_limit,
  omega_lo, omega_hi, alpha=0, beta=2e-6, vf=None, max_iter=40, change_tol=1e-3,
  p=12, mass_type="consistent", n_init=7, n_refine=14, band_rel_width=0.05,
  n_band=5)`** — minimise SIMP static compliance subject to the **D066/D075
  two-constraint pair**

      g₁(x) = J_peak(x) / J_lim − 1 ≤ 0      (in-band forced-response peak)
      g₂(x) = mean(x) − vf ≤ 0               (volume)

  but with the constraint band **re-gridded every iteration**: each step re-runs
  `adaptive_band_sample` over the full `[omega_lo, omega_hi]` to re-locate the
  moving resonance `ω_peak`, then rebuilds the band as
  `ω_peak · linspace(1−band_rel_width, 1+band_rel_width, n_band)` (clipped to the
  search range). The peak constraint therefore tracks the resonance throughout.
  The compliance gradient is the standard `dc/dρ_e = −dscale_e·uₑᵀkₑuₑ`; the peak
  gradient is the smooth p-norm `target_band_peak_sensitivity` on the *current*
  band. Both are density-filtered. Returns `AdaptivePeakConstrainedTOResult` whose
  **`peak_omega_history`** records the tracked resonance each iteration — the
  evidence the re-gridder is doing non-trivial work.

- The light default **`beta = 2e-6`** is deliberate: it keeps the resonance sharp
  enough to be *worth* tracking (a heavily-damped, monotone response has no peak to
  chase, and fixed/adaptive bands coincide) while remaining damped enough for a
  finite, stable solve (cf. Wave TTT's undamped J→∞ singularity).

- **`tests/test_inloop_adaptive_band.py`** — six quantitative anchors.

## Verification (quantitative anchors)

`tests/test_inloop_adaptive_band.py` (6 passed; adjacent regression on
test_adaptive_band_peak + test_freq_response = 14 passed):

1. **resonance drift ≥ 20 %**: the tracked `ω_peak` moves +99 % over the
   optimisation, so re-gridding tracks a genuinely moving target (a fixed band
   would be stale).
2. **in-loop tracking beats a stale fixed band on constraint fidelity** (the
   decisive D075-reopening contrast, anchored to an independent 800-point dense
   sweep): at the final design the adaptively-tracked band reports the true peak
   to **4.0 %** error, whereas a band frozen at the initial resonance errs by
   **93.7 %** — and the stale error is > 3× the tracked error.
3. **feasible against the dense sweep**: the final design's true (dense-sweep)
   peak ≤ 1.05 × limit, and volume ≤ vf + 0.02 — feasibility is checked against
   the independent sweep, not merely the in-loop sampled band.
4. **determinism**: two runs give identical densities and `peak_omega_history`.
5. **honest-scope degeneracy**: with heavy damping (`beta=1e-2`) the forced
   response is monotone in ω, so the re-gridder pins to the band's lower edge —
   in-loop has nothing a fixed band would miss (bounds the method's claimed value).
6. **input guards**: nonpositive limit / inverted range / `n_band<1` raise
   `SolverError`.

## Honest scope notes

- **On this stiffness-aligned smoke problem the in-loop and fixed-band *designs*
  nearly coincide; what differs is the constraint *measurement*.** Minimising
  static compliance stiffens the structure, which *lowers* the forced-response
  peak (8.2e6 final vs 7.0e8 initial) — so the peak constraint and the compliance
  objective pull the same way and the constraint is not strongly binding at the
  optimum. Both a fixed band and the in-loop band therefore reach a feasible
  min-compliance design. The demonstrated value of re-gridding here is **keeping
  the constraint faithful as the resonance drifts +99 %** (4 % vs 94 % error), not
  producing a divergent design. On a problem where the peak constraint genuinely
  *conflicts* with the primary objective (see Reopening criteria) that fidelity is
  what would keep the design feasible — but that conflicting formulation is not
  demonstrated here, and I do not claim it.
- **Min-volume-s.t.-peak is *not* used and does not work.** A single-objective
  min-volume drive collapses to near-void by detuning (Wave TTT's documented
  failure; re-confirmed by probe: true peak explodes 40–120× the limit as material
  vanishes and the resonance escapes the band entirely). Volume is held as its own
  constraint with compliance as the objective, exactly as D066/D075 established.
- **The re-grid is a full `adaptive_band_sample` every iteration** (`n_init +
  n_refine` ≈ 21 forced-response solves/step on top of the static solve and the
  p-norm adjoint). That is the honest cost of tracking; no attempt is made to warm-
  start the sampler from the previous iteration's grid.
- **Single lowest resonance, no mode-tracking.** The re-gridder follows the global
  band maximum each step; if two resonances cross within the band it tracks
  whichever is taller, with no continuation/identity tracking. Fine for the smoke
  cantilever's well-separated fundamental; a multi-resonance band is a reopening
  item.
- **`band_rel_width` is a fixed fractional window**, not adapted to the resonance
  sharpness (half-power bandwidth). A very sharp peak could in principle fall
  between the `n_band` samples; the p-norm over the window mitigates this but does
  not eliminate it.

## Reopening criteria

- **A genuinely peak-*binding* formulation** where the constraint conflicts with
  the objective — e.g. minimise dynamic compliance at a fixed operating frequency
  `ω_op` (which pushes a resonance toward a neighbouring in-band frequency) subject
  to the tracked-band peak ≤ limit — to demonstrate in-loop re-gridding changing
  the *design*, not just the measurement.
- **Bandwidth-adaptive window**: set `band_rel_width` from the local half-power
  bandwidth so the constraint window scales with the resonance sharpness.
- **Multi-resonance / mode-tracking band** (track the k tallest in-band peaks with
  a KS/p-norm aggregate) for designs whose resonances cross.
- **Warm-started sampler** reusing the previous iteration's grid to cut the
  per-step solve count.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
