# D054 — fibre-steering thermal TO: orientation as a design variable (Wave YY)

**Status**: Accepted
**Wave**: YY (v8)
**Supersedes**: none (closes D043's deferred orientation-field optimisation)
**Superseded by**: none

## Context

v7 Wave NN (D043) added the per-element anisotropic thermal field and the density
sensitivity, but the **orientation field was fixed**. Its reopening criterion
named the upgrade: optimise the orientation field itself (fibre-steering TO). v8
Wave YY delivers the orientation sensitivity + a steering driver.

## Decision

`core/thermal_simp.py`:

- `_thermal_elem_from_tensor(k2x2, thickness)` — the `∫ Bᵀ k B` element
  quadrature **without** the positive-definite check (so it accepts the
  indefinite derivative tensor dk/dθ); identical quadrature to
  `element_thermal_conductivity_tensor`.
- `_dk_dtheta(kxx, kyy, kxy, θ)` — d/dθ of R(θ)·k₀·R(θ)ᵀ =
  R'(θ)k₀R(θ)ᵀ + R(θ)k₀R'(θ)ᵀ.
- `orientation_sensitivity(config, mesh, densities, angles, kxx, kyy, …)` →
  dC/dθ_e. The thermal problem is self-adjoint, so for C = TᵀK(θ)T and a
  θ-independent load, dC/dθ_e = −scale_e · Tₑᵀ(∂ke_e/∂θ_e)Tₑ, where ke_e is
  linear in k(θ) so ∂ke_e/∂θ_e = `_thermal_elem_from_tensor(dk/dθ)`.
- `fibre_steering_thermal_to(config, mesh, densities, kxx, kyy, …)` →
  `FibreSteeringResult(angles, compliance_history, …)`: steepest descent on the
  per-element fibre angle (periodic, no box constraint) at fixed densities.

## Verification (quantitative)

- **Sensitivity vs central-FD** (`test_orientation_sensitivity_matches_central_fd`):
  on a random orientation field the analytic dC/dθ matches central differences to
  rel 1e-5 on the 6 most-sensitive elements (observed ≈1e-9) — the §3.1 anchor.
- **Isotropic ⇒ zero** (`test_isotropic_base_has_zero_orientation_sensitivity`):
  kxx==kyy makes k(θ) rotation-invariant, so dC/dθ ≡ 0 (observed max|·| < 1e-6) —
  an exact analytical check that the rotation derivative is correct.
- **Steering lowers compliance** (`test_fibre_steering_lowers_thermal_compliance`):
  steepest descent on the angles monotonically lowers thermal compliance and ends
  < 0.9·C₀ (observed ≈0.67·C₀, a 33% cut) versus the fixed axis-aligned start.
  3 tests, all green. Adjacent `test_anisotropic_thermal_field` +
  `test_thermal_simp` + `test_thermal` (28) unchanged.

## Honest scope notes

- Steering optimises the **orientation field only** (angles), at fixed densities.
  A coupled density + orientation TO (alternating or simultaneous) is a further
  step.
- Steepest descent with a normalised step, **not** a manifold-aware or
  trust-region update; angles are treated as unconstrained periodic variables.
  Good enough to demonstrate the sensitivity drives compliance down; a production
  fibre-steering optimiser would add filtering/continuation on the angle field.
- The self-adjoint identity uses the full element temperatures (prescribed-BC
  nodes included), matching the D043 density-sensitivity convention.

## Reopening criteria

- Coupled density + orientation TO (alternating minimisation or a combined
  update).
- Angle-field filtering / continuation for manufacturable fibre paths.
- Anisotropic **elastic** fibre steering (the same derivation with the elastic
  D(θ) tensor).

## Red lines

numpy-only, 2D, single-line stderr. `element_thermal_conductivity_tensor` and the
D043 density sensitivity are unchanged; the derivative quadrature is a separate
unchecked helper so the validated forward builder is untouched.
