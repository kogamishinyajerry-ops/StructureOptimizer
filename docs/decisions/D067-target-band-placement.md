# D067 — target-band placement: minimax around a target frequency (Wave LLL, v10)

**Status**: Accepted
**Wave**: LLL (v10)
**Supersedes**: none (extends D059)
**Superseded by**: none

## Context

D059 delivered band-gap maximisation (`maximize_band_gap`): it pushes two
adjacent *eigenvalues* apart. Its recorded reopening criterion was
**target-band placement** — minimising the worst-case forced response over a
target frequency band, i.e. a band-suppression / vibration-isolation objective,
rather than only separating eigenvalues. v10 Wave LLL implements it.

The per-frequency machinery already existed: `dynamic_compliance_sensitivity`
gives the squared dynamic compliance `J(ω) = |fᵀû|²` and its self-adjoint
sensitivity `dJ/dρ`. What was missing was the **minimax aggregation** over a
band and its sensitivity.

## Decision

- **`freq_response.target_band_peak_sensitivity(config, mesh, densities,
  band_omegas, alpha=0, beta=0, p=12, mass_type)`** — samples `J(ω_k)` at each
  `ω_k` in the band and aggregates into the smooth p-norm peak
  `J_PN = (Σ_k J_k^p)^(1/p)` → `max_k J_k` as `p → ∞` (minimax around the band's
  target). The sensitivity chains the per-frequency self-adjoint sensitivity:

      dJ_PN/dρ = Σ_k (J_k / J_PN)^(p−1) · dJ_k/dρ.

  Returns `(peak_pnorm, dpeak_drho, per_freq_J)`.

- **`freq_response.target_band_placement(config, mesh, band_omegas, alpha=0,
  beta=1e-4, n_steps=20, move=0.1, p=12, filter_radius=None, mass_type)`** — a
  volume-preserving, move-limited projected-gradient **descent** on the in-band
  peak, reusing the Sigmund density filter and the same volume-rescale step as
  `maximize_band_gap` (this one descends instead of ascends). Returns
  `TargetBandResult` (densities + peak history + band + initial/final peak +
  converged).

- **`tests/test_target_band_placement.py`** — four quantitative anchors (below).

## Verification (quantitative anchors)

`tests/test_target_band_placement.py` (all pass; adjacent regression on
test_band_gap_to / test_damped_freq_response / test_dynamic_band_to /
test_dynamic_compliance_to / test_freq_response / test_modal):

1. **in-band peak sensitivity vs central-FD**: `dJ_PN/dρ` matches central finite
   differences to relative error ≤ 1e-4 on the 5 highest-|sensitivity| elements
   (measured ≈ 1e-7); the p-norm peak over-estimates the true max but stays
   close (ratio ≈ 1.03 at p = 12).
2. **worst-case in-band response drops**: after optimisation
   `max_k J(ω_k)` < 0.5·initial (probe: 4.33e5 → 6.75e4, an 84 % drop on a band
   straddling the first natural frequency).
3. **volume-preserving**: design volume fraction held at its initial value to
   ≤ 1e-6.
4. **contract + determinism**: histories aligned, band echoed, two runs
   identical.

## Honest scope notes

- The objective is the **smoothed minimax** (p-norm of in-band `J(ω_k)`), not the
  exact `max`; finite `p` (= 12 default) over-estimates the true peak by a few
  percent. Raising `p` sharpens the approximation but steepens the gradient.
- The band is a **fixed user-supplied frequency sample** (`band_omegas`); the
  driver does not adaptively refine the sampling around the moving resonance, so
  a coarse band can miss a peak that drifts between samples during the descent.
- The optimiser is the **same first-order projected-gradient + volume-rescale**
  heuristic as `maximize_band_gap`, **not** MMA — combining target-band placement
  with the multi-constraint MMA of D066 (peak-as-constraint) is a future
  extension.
- Damping is Rayleigh (`alpha`, `beta`); with `beta = 0` and a frequency exactly
  at an undamped resonance the response is singular — the default `beta = 1e-4`
  keeps the in-band solve well-posed.
- Builds on `dynamic_compliance_sensitivity`'s dense modal assembly (smoke-mesh
  scale); large meshes inherit that path's cost.

## Reopening criteria

- **Adaptive band sampling** that tracks the moving resonance during the descent.
- **Peak-as-constraint** inside the D066 multi-constraint MMA (minimise volume or
  compliance s.t. in-band peak ≤ limit) instead of pure peak descent.
- **Repeated / clustered eigenvalues** in the band (the per-frequency `J` is
  smooth, but the underlying modes can cross — robust handling is unaddressed).

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
