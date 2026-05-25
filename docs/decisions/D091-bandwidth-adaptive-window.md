# D091 — half-power bandwidth-adaptive in-loop window; peak-binding deferred (Wave BBBBB, v13)

**Status**: Accepted
**Wave**: BBBBB (v13)
**Supersedes**: none (extends D083)
**Superseded by**: none

## Context

D083 (v12 Wave BBBB) added in-loop adaptive band re-gridding but recorded two
reopening items:

> *(a) "A genuinely peak-*binding* formulation where the constraint conflicts with
> the objective — e.g. minimise dynamic compliance at a fixed operating frequency
> ω_op — to demonstrate in-loop re-gridding changing the **design**, not just the
> measurement."*
> *(b) "Bandwidth-adaptive window: set band_rel_width from the local half-power
> bandwidth so the constraint window scales with the resonance sharpness."*

This wave **delivers (b)** and **honestly defers (a)** with probe evidence.

## Decision

- **`freq_response.half_power_relative_bandwidth(omega, alpha=0.0, beta=2e-6)`** —
  the closed-form half-power *fractional* bandwidth `Δω/ω_n = 2ζ(ω_n) = α/ω_n +
  β·ω_n` of a Rayleigh-damped (`C = αM + βK`) resonance.

- **`freq_response.adaptive_peak_constrained_mma(..., bandwidth_adaptive=False)`** —
  a new opt-in flag. When `True`, each iteration sizes the in-loop constraint
  window half-width from the half-power bandwidth at the *tracked* resonance
  (`α/ω_peak + β·ω_peak`) instead of the fixed `band_rel_width`. **Default `False`
  reproduces D083 exactly** (no regression).

- **`tests/test_bandwidth_adaptive_band.py`** — four anchors.

## Verification (quantitative anchors)

`tests/test_bandwidth_adaptive_band.py` (4 passed; adjacent regression on
test_inloop_adaptive_band = the D083 set, all pass):

1. **half-power closed form**: `half_power_relative_bandwidth` equals `α/ω + β·ω`
   and `= 2·ζ` (the modal damping ratio relation) to ≤ 1e-15.
2. **robust across sharpness** (the headline, vs an independent 1200-point dense
   sweep): over `β ∈ {5e-7, 2e-6, 8e-6}` (ζ ≈ 0.009 → 0.148) the adaptive band's
   worst-case error is < ½ the fixed-5%-band's worst case; at the **sharpest**
   resonance the adaptive band errs ~11 % vs the fixed band's ~62 % (a fixed
   fraction straddles a sharp peak with off-peak samples).
3. **driver feasible**: `bandwidth_adaptive=True` runs stably, the final design's
   true (dense-sweep) peak ≤ limit, and the recorded band's width matches the
   half-power formula (and is *not* the fixed 0.05 default).
4. **determinism + guards** (`ω ≤ 0`, negative damping raise `SolverError`).

## Honest scope notes

- **The peak-*binding* "different design" claim (D083 item a) is DEFERRED, with
  probe evidence.** Two probes on the smoke cantilever:
  - Minimising dynamic compliance at ω_op (for ω_op ∈ {0.85, 1.0, 1.15, 1.4}·ω₁)
    s.t. a peak constraint left **both** in-loop and fixed-band designs *feasible*
    (true-peak ratios ≈ 0.01–0.05 of the limit) — the constraint never binds.
  - Unconstrained min J(ω_op) **lowered** the in-band true peak in every case
    (e.g. 7.0e8 → 6.1e6) rather than raising it: on this small mesh stiffening to
    reduce the response at one frequency reduces the whole transfer function, so the
    objective and the peak constraint are *aligned*, not in conflict.
  The in-loop and fixed designs did differ (≈ 46 % by ‖Δρ‖), but since both are
  feasible that difference does not demonstrate the intended "in-loop succeeds where
  fixed fails." Manufacturing a binding conflict would need the anti-resonance
  flanking-mode mechanism on a finer mesh; I do **not** fake it here. Reopened.
- **`bandwidth_adaptive` is opt-in; default preserves D083.** I did not flip the
  default, because the fixed `band_rel_width=0.05` is a fine choice near ζ ≈ 0.025
  and existing D083 tests assume it.
- **The half-power width assumes the Rayleigh model is the true damping.** The
  fractional bandwidth is exact for `C = αM + βK`; for non-proportional damping the
  formula is an approximation (not used here — the whole module is Rayleigh).
- **At a sharp resonance the adaptive band's ~11 % residual error** comes from the
  `n_band = 5`-point p-norm sampling of a very narrow window plus the bisection
  `ω_peak` error; it is far below the fixed band's 62 % but not zero. Denser
  `n_band` would tighten it (not pursued — the robustness *contrast* is the point).

## Reopening criteria

- **Peak-binding "different design"** on a finer mesh where minimising J(ω_op)
  genuinely raises a flanking in-band resonance (anti-resonance pole–zero
  interlacing), so the constraint binds and in-loop re-gridding changes the design.
- **Multi-resonance adaptive windows** (one half-power window per tracked peak) for
  bands containing several modes.
- **Non-proportional damping**: a measured half-power bandwidth (from the actual
  swept magnitude via `half_power_bandwidth`) instead of the Rayleigh closed form.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
