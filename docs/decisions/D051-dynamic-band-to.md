# D051 — filtered multi-ω dynamic-compliance TO loop (Wave VV)

**Status**: Accepted
**Wave**: VV (v8)
**Supersedes**: none (closes D047's deferred filtered/band driver)
**Superseded by**: none

## Context

v7 Wave RR (D047) delivered the single-ω dynamic-compliance sensitivity and a
compact unfiltered descent. Its reopening criteria named two upgrades: a
**band-averaged (multi-ω)** objective and a **filtered MMA/OC loop**. v8 Wave VV
delivers both.

## Decision

`core/freq_response.py`:

- `dynamic_compliance_to(config, mesh, omegas, alpha, beta, n_steps, move,
  filter_radius=None, …) → DynamicBandTOResult`. Objective J(ρ) = mean_ω
  |fᵀû(ω)|² over the band `omegas`; the per-ω self-adjoint sensitivities (D047)
  are averaged, **Sigmund-density-filtered** (`density_filter`, default radius =
  `config.optimization.filter_radius`), then a volume-preserving normalised
  projected-gradient step (clipped to ±move) is taken.
- `_checkerboard_metric(mesh, rho)` — mean squared deviation of each interior
  cell from its 4-neighbour mean (a checkerboard maximises it, a smooth field →0).

**Why projected-gradient, not OC**: the dynamic-compliance sensitivity changes
sign near resonance, where OC's positive-Lagrange-multiplier bisection
(`x·√(−s/λ)`) is not valid. Projected gradient + volume rescale is robust to
either sign — the honest choice for a dynamic objective.

## Verification (quantitative)

- **Band descent + band peak** (`test_band_dynamic_compliance_descends_and_cuts_band_peak`):
  over a 30–70 rad/s band (5 frequencies) the band-averaged J is monotone
  non-increasing and ends < 0.5·J₀ (observed 0.166·J₀); the peak magnitude over
  the **whole band** drops (observed 2.60 → 1.06) — band resonance avoidance, the
  multi-ω value-add over RR's single-ω; volume preserved at 0.45 to rel 1e-6.
- **Filter suppresses checkerboard** (`test_density_filter_suppresses_checkerboard`):
  a synthetic checkerboard field (0.2/0.8) filters to a far smoother one — the
  checkerboard metric drops by >10× (observed 0.36 → 5e-4). This is a direct,
  loop-independent property of the Sigmund filter.
- **Contract** (`test_dynamic_to_rejects_empty_band`): empty band → `SolverError`.
  3 tests, all green. Adjacent `test_dynamic_compliance_to` +
  `test_damped_freq_response` + `test_freq_response` (20) unchanged.

## Honest scope notes

- The checkerboard anchor is verified as a **filter property** (smoothing a
  checkerboard), not as a before/after on the final design — the gentle
  projected-gradient loop on this smooth benchmark does not itself produce
  checkerboarding, so a final-design comparison would have nothing to reduce.
  The honest claim is "the filter the loop applies suppresses checkerboarding",
  proven directly.
- Projected gradient with volume rescale, **not** MMA/OC (sign-robustness, see
  above). A proper dynamic-MMA with move limits + an OC variant restricted to the
  sub-resonance regime where the sensitivity stays one-signed are reopening items.
- Band objective is the **uniform mean** over a discrete ω list; a
  frequency-weighted or worst-ω (minimax) band objective is a further step.

## Reopening criteria

- Frequency-weighted / minimax band objective.
- Dynamic MMA with move limits; OC variant on the one-signed sub-resonance band.
- Eigenfrequency-gap (band-stop) objective built on the modal solver.

## Red lines

numpy-only (`density_filter` reused), 2D, single-line stderr (`SolverError`).
`dynamic_compliance_sensitivity`, `solve_damped_frequency_response`,
`minimize_dynamic_compliance` (RR) are unchanged; the new driver only consumes
them.
