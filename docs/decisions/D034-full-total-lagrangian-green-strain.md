# D034 — full Total-Lagrangian Green-strain Newton (Wave EE)

**Status**: Accepted
**Wave**: EE (v6)
**Supersedes**: none (deepens D027's simplified TL; reopens its "Reopening criteria")
**Superseded by**: none

## Context

v5 Wave AA (D027) shipped a **simplified** geometric-nonlinear solver
(`core/nonlinear_fem.py`): it approximates the St. Venant-Kirchhoff (SVK)
response with a matrix-level `K + ½K_g` correction reusing the buckling
geometric-stiffness path. D027's own "Honest scope notes" + "Reopening
criteria" flagged the full Total-Lagrangian Newton on Green strain + 2nd
Piola-Kirchhoff stress (Bonet & Wood Ch. 9) as the v5+ upgrade for workflows
needing rigorous large-rotation behaviour. v6's charter is exactly that:
turn v5's intentional simplifications into production-grade formulations.

The simplified form has a concrete, demonstrable defect: under a **finite
rigid-body rotation** it does not produce zero strain (it is not frame
indifferent). That is the canonical correctness gap a full Green-strain TL
closes.

## Decision

Add `core/total_lagrangian.py` implementing the genuine Total-Lagrangian Q4
element with 2×2 Gauss quadrature on the isoparametric element:

- deformation gradient `F = I + ∂u/∂X` from actual reference node coordinates,
- Green-Lagrange strain `E = ½(FᵀF − I)`,
- 2nd PK stress `S = D:E` (SVK), with SIMP density scaling `D_e = ρ_e-scale · D₀`
  (same `ρ^p` interpolation used everywhere — topology-optimization compatible),
- internal force `∫ B_L(u)ᵀ S dV` and consistent tangent
  `∫ (B_Lᵀ D B_L + Gᵀ Σ G) dV` (material + geometric),
- Newton-Raphson with incremental load stepping; single-line `SolverError`.

`solve_total_lagrangian(config, mesh, densities, n_load_steps, …)` returns
displacements, per-step max displacement, Newton-iteration count, converged
flag, and total strain energy. `green_strain_field(mesh, u)` exposes the
per-element centroid Green strain for the verification tests.

## Verification (quantitative, against analytical results)

- **Objectivity** (`test_finite_rotation_zero_green_strain`): a 30° rigid
  rotation `u = (R−I)X` gives `F = R`, so `E = ½(RᵀR−I) = 0` to ≤ 1e-10. This
  is the property the simplified v5 form fails — the headline correctness gain.
- **Constant-strain patch** (`test_uniform_stretch_…`): uniform stretch λ gives
  `E11 = ½(λ²−1)` exactly (atol 1e-12).
- **Linear limit**: at 1e-4 load, TL displacement matches `solve_linear_elastic`
  within 1e-3 relative.
- **Geometric stiffening**: at the working load TL tip displacement does not
  exceed the linear estimate (elastica sub-linear trend).
- Strain energy ≥ 0 (SVK), finite displacements; contract errors raise.

8 tests, all green. Full suite stays green (new module imported only by its test).

## Honest scope notes

- SVK material only (large rotation, *moderate* strain). Neo-Hookean / other
  hyperelastic laws are a later option if a workflow needs large *strain*.
- Dense assembly + dense Newton solve — same scale ceiling as the rest of the
  dense path; sparse/AMG TL is a future option.
- Not yet wired into a SIMP optimization loop (nonlinear-compliance TO with the
  full TL adjoint is deferred); this wave delivers the verified forward solver.

## Reopening criteria

- A workflow needing large-strain (not just large-rotation) → add a
  Neo-Hookean / Mooney-Rivlin constitutive option.
- Nonlinear-compliance topology optimization → add the TL adjoint sensitivity
  and a `run_total_lagrangian_simp` driver.

## Red lines

numpy-only, 2D, dense, single-line stderr — all held.
