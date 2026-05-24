# D043 — per-element anisotropic thermal field + anisotropic thermal TO (Wave NN)

**Status**: Accepted
**Wave**: NN (v7)
**Supersedes**: none (extends D036's global tensor to a per-element field)
**Superseded by**: none

## Context

v6 Wave GG (D036) added a **global** conductivity tensor (one tensor per solve).
Its reopening criteria named two upgrades: a **per-element orientation field**
(e.g. per-element fibre angle) and the **anisotropic thermal TO sensitivity**.
v7 Wave NN delivers both.

## Decision

`core/thermal.py`:

- `orientation_field_to_tensors(kxx, kyy, angles, kxy=0)` → `(n_elem, 2, 2)`
  field, element e = R(θ_e)·k·R(θ_e)ᵀ of the base orthotropic tensor.
- `_assemble_thermal_dense_field(mesh, density_scale, ke_field)` — assembles with
  a per-element `(n_elem, 4, 4)` element-matrix array.
- `solve_thermal(..., conductivity_tensor_field=None)` — when supplied a
  `(n_elem, 2, 2)` field, builds per-element element matrices, assembles via the
  field assembler, and computes `element_thermal_energy` with each element's own
  tensor. The scalar and global-tensor paths are unchanged.

`core/thermal_simp.py`:

- `anisotropic_thermal_sensitivity(config, mesh, densities, conductivity_tensor
  | conductivity_tensor_field, ...)` → `dC/dρ_e = -p·ρ_e^(p-1)·(1-ρ_min)·(Tₑᵀ
  ke_e Tₑ)`. The thermal problem is self-adjoint, so this is identical in form to
  the scalar `run_thermal_simp` sensitivity — the only change is that
  `element_thermal_energy` now carries the anisotropic (tensor / field)
  conductivity.

## Verification (quantitative)

- **Reduction** (`test_uniform_field_reduces_to_global_tensor`): a field whose
  elements all carry the same tensor matches the global-tensor solve to ≤1e-12
  (temperatures + compliance) — so it inherits D036's patch test and
  rotation-invariance guarantees.
- **Field does something** (`test_varying_orientation_changes_solution`): a
  linearly-varying orientation field yields a temperature field measurably
  different from the uniform field.
- **Helper** (`test_orientation_field_to_tensors_matches_rotate`): each element
  tensor equals `rotate_conductivity_tensor(base, θ_e)`; θ=0 → base.
- **Sensitivity vs central-FD** (`test_anisotropic_sensitivity_matches_central_fd`):
  the anisotropic SIMP sensitivity matches central differences of the thermal
  compliance to rel 1e-4 across sampled design elements — the quantitative
  anchor for §2.2.
- **Contract**: wrong field shape → `SolverError`. 5 tests, all green. Adjacent
  `test_anisotropic_thermal` + `test_thermal` + `test_thermal_simp` (31)
  unchanged.

## Honest scope notes

- The patch test is *not re-claimed* for spatially-varying conductivity (a
  linear temperature field is the exact source-free solution only for uniform
  conductivity, since ∇·(k∇T) = ∇k·∇T ≠ 0 when k varies). The reduction anchor
  routes the patch-test guarantee through the field path for the uniform case;
  varying fields are validated by the reduction + sensitivity + physical-change
  anchors, not by a linear-field exactness claim.
- Sensitivity is delivered for a global tensor (and accepts a field); a full
  per-element-field thermal-TO driver that also optimises the orientation field
  is a further step (orientation as a design variable).

## Reopening criteria

- Optimising the orientation field itself (fibre-steering TO) → add orientation
  sensitivities + an orientation update.
- Per-element scalar conductivity fields (functionally-graded) → trivial via the
  same field assembler with isotropic per-element tensors.

## Red lines

numpy-only, 2D, single-line stderr — all held. Scalar + global-tensor thermal
paths and `run_thermal_simp` unchanged. (Two pre-existing lint nits — thermal.py
`zip` B905 and thermal_simp.py import-sort — are left untouched, not part of this
wave.)
