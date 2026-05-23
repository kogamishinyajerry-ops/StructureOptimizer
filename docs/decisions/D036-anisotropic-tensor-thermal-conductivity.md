# D036 — anisotropic / orthotropic tensor thermal conductivity (Wave GG)

**Status**: Accepted
**Wave**: GG (v6)
**Supersedes**: none (deepens D025's scalar conductivity; reopens its "Reopening criteria")
**Superseded by**: none

## Context

v5 Wave Y (D025) shipped a 2D heat-conduction solver with a single **scalar**
conductivity `k`, using the analytical unit-square element matrix. D025's
"Reopening criteria" flagged anisotropic / orthotropic conductivity (fibre
composites, additively-manufactured layers, rolled metals) as the v5+ upgrade.
v6 turns it on.

## Decision

Add tensor-conductivity support to `core/thermal.py`, backward compatible:

- `conductivity_tensor(kxx, kyy, kxy)` → symmetric 2×2 tensor.
- `rotate_conductivity_tensor(k, θ) = R k Rᵀ` for principal-axis rotation.
- `element_thermal_conductivity_tensor(k, t)` integrates `∫ Bᵀ k B t dA`
  (B = [∂N/∂x; ∂N/∂y]) by 2×2 Gauss on the unit element; validates the tensor
  is symmetric positive-definite (single-line `SolverError`).
- `solve_thermal(..., conductivity_tensor=None)` — when supplied, uses the
  tensor element matrix; otherwise the scalar path is unchanged (existing
  callers, `run_thermal_simp`, fingerprints all unaffected).

## Verification (quantitative)

- **Isotropic reduction** (`test_isotropic_tensor_matches_scalar_analytical`):
  `k·I` tensor matrix equals the analytical scalar matrix to ≤ 1e-12.
- **Patch test** (`test_orthotropic_patch_test_linear_field`): a linear
  temperature field `T = a·x + b·y` gives *zero interior residual* for a fully
  orthotropic + off-diagonal tensor (the classic FEM patch test, ≤ 1e-9). This
  is the quantitative correctness anchor.
- **Rotation invariance** (`test_conductivity_tensor_rotation_invariance_isotropic`):
  an isotropic tensor is unchanged by rotation, so its element matrix is too.
- **90° swap**, **isotropic solve == scalar solve**, directional-conduction
  physical sanity, SPD/symmetry contract errors. 8 tests, all green.
  Adjacent `test_thermal` + `test_thermal_simp` (23) unchanged.

## Honest scope notes

- Tensor is **global** (one k per solve), not per-element spatially varying
  fields — sufficient for orthotropic-material studies; per-element tensor
  fields are a later option.
- Not yet wired into a thermal-SIMP objective with anisotropic sensitivities
  (the forward solver is delivered; anisotropic thermal TO is a future driver).
- Unit-element convention inherited from D025 (mesh-size effects in calibration).

## Reopening criteria

- A workflow needing spatially-varying orientation (e.g. per-element fibre
  angle) → accept a per-element tensor array.
- Anisotropic thermal topology optimization → add the tensor SIMP sensitivity.

## Red lines

numpy-only, 2D, dense, single-line stderr — all held. (A pre-existing B905
`zip` lint nit elsewhere in the file is left untouched — not part of this wave.)
