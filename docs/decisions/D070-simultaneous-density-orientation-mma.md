# D070 — simultaneous (ρ,θ) MMA coupled thermal TO (Wave OOO, v10)

**Status**: Accepted
**Wave**: OOO (v10)
**Supersedes**: none (extends D062)
**Superseded by**: none

## Context

D062 (`coupled_density_orientation_to`) optimised density *and* fibre orientation
together, but by **block-coordinate alternating minimisation**: a density OC step
at fixed θ, then orientation steepest-descent at fixed ρ, cycling. Alternation is
monotone but stalls at coordinate-wise stationary points that are not jointly
optimal. D062's recorded reopening criterion was **simultaneous (ρ,θ) MMA**. v10
Wave OOO implements it.

## Decision

- **`thermal_simp.simultaneous_density_orientation_mma(config, mesh, kxx, kyy,
  kxy=0, max_iter=40, theta_bound=π/2, init_angles=None, heat_sources, thermal_bcs,
  change_tol=1e-3)`** — MMA over the **stacked** design vector
  `x = [ρ_design ; θ_design]`. The objective is thermal compliance; its gradient
  stacks the two self-adjoint sensitivities:
  - `dC/dρ` — D043 `anisotropic_thermal_sensitivity`, density-filtered;
  - `dC/dθ` — D054 `orientation_sensitivity`.
  The single constraint is the volume inequality `g = mean(ρ) − vf ≤ 0`, acting on
  the ρ block only (`dfdx[0, :n_design] = 1/n`, `0` on the θ block). Angles are
  box-bounded to `[−θ_bound, θ_bound]` (the conductivity tensor `R(θ)k₀R(θ)ᵀ` has
  period π, so `π/2` spans all directions). Returns `SimultaneousCoupledResult`
  (densities + angles + compliance/volume histories + converged).

- **`tests/test_simultaneous_coupled_mma.py`** — four quantitative anchors
  (below).

## Verification (quantitative anchors)

`tests/test_simultaneous_coupled_mma.py` (all pass; adjacent regression on
test_coupled_thermal_to / test_thermal_simp / fibre-steering):

1. **combined sensitivity vs central-FD**: the stacked `[dC/dρ ; dC/dθ]` matches
   central finite differences to relative error ≤ 1e-4 on the top-|sensitivity|
   elements of **both** blocks (measured ≈ 1e-8), confirming the merge is correct
   at a non-uniform (ρ,θ) point.
2. **simultaneous ≤ alternating**: on the `heat_sink` smoke benchmark (kxx=5,
   kyy=1) simultaneous MMA reaches C = 2.0949e5 vs alternating (GGG) 2.5905e5 — a
   19 % improvement; the test asserts `≤ alternating·1.001`.
3. **feasible volume**: `mean(ρ) ≤ vf + 0.02` at convergence.
4. **contract + determinism**: histories aligned, two runs identical, angles stay
   inside the box bound.

## Honest scope notes

- The objective is **thermal** compliance (self-adjoint), as in D062 — the
  simultaneous MMA is *not* applied to the elastic coupled problem here.
- "≤ alternating" is **empirical on this benchmark**, not a theorem: MMA is a
  local optimiser, and a pathological start could in principle land higher than
  alternation. The 1.001 tolerance in the test acknowledges this; the observed
  19 % gain is the typical (not guaranteed) payoff of joint stepping.
- Orientation is **unfiltered** (only ρ is density-filtered), matching D054/D062;
  a fibre-continuity / steering-rate constraint on θ is not imposed, so the angle
  field can be locally rough.
- Angles are box-bounded at `±π/2`; the MMA does not exploit the π-periodicity to
  wrap, so a true optimum near the boundary is represented at the boundary, not
  wrapped.
- Single volume constraint only; combining with the D066 stress constraint (a
  multi-constraint *coupled* MMA) is a further extension.

## Reopening criteria

- **Elastic** simultaneous (ρ,θ) MMA (orthotropic stiffness orientation), not just
  thermal.
- **Fibre-continuity constraint** on θ (steering-rate / curvature bound) for
  manufacturable tow paths.
- **Multi-constraint coupled MMA** (volume + stress + orientation) unifying D066
  and D070.
- **Periodic-θ handling** (wrap at ±π/2) so boundary optima are not artefacts.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
