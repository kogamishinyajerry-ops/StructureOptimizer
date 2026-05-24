# D062 — coupled density + orientation thermal TO (alternating minimisation) (Wave GGG)

**Status**: Accepted
**Wave**: GGG (v9)
**Supersedes**: none (couples D043 density TO + D054 orientation TO)
**Superseded by**: none

## Context

D043 (Wave NN) gave the anisotropic-thermal density sensitivity (optimise ρ at
fixed orientation); D054 (Wave YY) gave fibre steering (optimise the orientation
field θ at fixed ρ). D054's reopening criterion named the coupling: **"coupled
density + orientation TO (alternating minimisation)"**. Wave GGG delivers it.

## Decision

`core/thermal_simp.py`:

- `coupled_density_orientation_to(config, mesh, kxx, kyy, kxy=0, n_outer=8,
  n_orient_steps=8, orient_step=0.3, ...)` → `CoupledThermalResult(densities,
  angles, compliance_history, converged)`. Each outer cycle:
  1. **density step** at the current θ field — `anisotropic_thermal_sensitivity`
     (D043) → Sigmund `density_filter` → volume-constrained `_optimality_criteria_update`
     → `_apply_density_masks`;
  2. **orientation step** at the updated ρ — up to `n_orient_steps` normalised
     steepest-descent steps using `orientation_sensitivity` (D054).
  Records thermal compliance after each full cycle; stops on `max|Δρ| < change_tol`
  or `n_outer`. The thermal problem is self-adjoint, so each sub-step is a descent
  on the same objective → the alternation is monotone.

## Verification (quantitative)

- **Beats each single field** (`test_coupled_beats_each_single_field`): the coupled
  final thermal compliance is ≤ density-only (`n_orient_steps=0`) and ≤
  orientation-only (`fibre_steering_thermal_to` at uniform density). Observed
  259,050 vs 801,643 (density-only, 3.1×) vs 4,473,543 (orientation-only, 17×).
  Headline coupling payoff.
- **Monotone descent** (`test_coupled_monotone_descent`): the per-cycle compliance
  history is non-increasing (observed 2.88e6 → 2.59e5).
- **Isotropic degeneracy** (`test_isotropic_reduces_to_density_only`): with
  `kxx==kyy` the orientation sensitivity is identically zero, so the coupled run
  equals the density-only run **exactly** (Δ = 0.0) and the angles stay 0.
- **Determinism** (`test_coupled_deterministic`): no RNG → bit-identical densities,
  angles, history. 4 tests, all green. Adjacent `test_thermal_simp` +
  `test_fibre_steering_thermal` + `test_thermal` (26) unchanged.

## Honest scope notes

- **Alternating (block-coordinate) minimisation**, not a fully-coupled
  simultaneous (ρ,θ) optimiser: it converges to a block-coordinate stationary
  point, which need not be the global joint optimum. It is guaranteed monotone and
  ≥ either single field, which is the claim made.
- The density step is OC (single move limit), the orientation step is normalised
  steepest descent — neither is MMA; a simultaneous (ρ,θ) MMA is the reopening item.
- Orientation has no manufacturability/continuity constraint (angles are
  per-element and free); angle-field filtering for manufacturable fibre paths is a
  separate D054 reopening item.
- Thermal only (the same self-adjoint structure); the elastic fibre-steering
  coupling is future work.

## Reopening criteria

- Simultaneous (ρ, θ) MMA (one design vector, two constraint blocks) instead of
  alternating block-coordinate descent.
- Angle-field filtering / continuation for manufacturable fibre paths.
- Anisotropic **elastic** coupled density + orientation TO (same derivation with
  the elastic tensor).

## Red lines

numpy-only, 2D/2.5D, single-line stderr (reuses the `SolverError` paths in
`solve_thermal` / `anisotropic_thermal_sensitivity` / the OC update). D043
density sensitivity and D054 fibre steering are unchanged; the coupled driver is
additive (local import of `orientation_field_to_tensors`, top-level imports
untouched).
