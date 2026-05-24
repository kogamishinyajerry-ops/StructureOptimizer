# D079 — elastic orthotropic simultaneous (ρ,θ) MMA + fibre continuity (Wave XXX, v11)

**Status**: Accepted
**Wave**: XXX (v11)
**Supersedes**: none (extends D070)
**Superseded by**: none

## Context

D070 (`thermal_simp.simultaneous_density_orientation_mma`) drove density and
fibre orientation **together** in a single MMA step — but for **thermal**
conductivity (a rotated 2×2 conductivity tensor). Its recorded reopening
criterion:

> *"elastic simultaneous (ρ,θ) MMA; fibre-continuity."*

The elastic analogue is harder: it needs an **orthotropic lamina stiffness**
(3×3 plane-stress `D₀`) rotated by a per-element fibre angle, integrated into a
Q4 element stiffness — none of which existed (the elastic FEM only had the
isotropic closed-form `fem2d.element_stiffness`). And D070 let θ vary freely
between neighbours, which is unmanufacturable for a fibre layup; a
**fibre-continuity** constraint was the missing piece. v11 Wave XXX adds the new
`orthotropic_simp.py` module with both.

## Decision

- **`orthotropic_plane_stress_matrix(e1, e2, nu12, g12)`** — the orthotropic
  plane-stress `D₀` (material axes, Voigt/engineering shear).

- **`rotate_plane_stress(d0, theta)`** + **`drotate_plane_stress_dtheta(d0, theta)`**
  — rotation to global axes via the **4th-order tensor** transform
  `C' = QQQQ:C` (and its analytic θ-derivative through `dQ/dθ`), which makes the
  engineering-shear bookkeeping exact (no error-prone Q̄ Reuter matrix).

- **`orthotropic_element_stiffness(d)`** — the 8×8 Q4 stiffness `∫ Bᵀ D B` by 2×2
  Gauss on the unit square, with the B-matrix node order matched to `mesh`
  connectivity. **With an isotropic D it reproduces `fem2d.element_stiffness` to
  ≤ 1e-9** (the kernel's self-check).

- **`orthotropic_compliance_sensitivities(config, mesh, densities, angles, d0)`**
  — compliance + the two self-adjoint sensitivities
  `dC/dρ_e = −dscale_e·uₑᵀke(θ_e)uₑ` and
  `dC/dθ_e = −scale_e·uₑᵀ(dke/dθ)(θ_e)uₑ` with `dke/dθ = ∫ Bᵀ(dD/dθ)B`.

- **`simultaneous_elastic_orientation_mma(config, mesh, d0, vf=None,
  fibre_continuity_limit=None, …)`** — minimise compliance over stacked `[ρ; θ]`
  with the volume inequality and, when `fibre_continuity_limit` is set, a second
  inequality `g₂ = mean_{(e,f) adj}(θ_e−θ_f)²/lim − 1 ≤ 0` (gradient = the design-
  graph Laplacian of θ). θ box-bounded to `[−π/2, π/2]`.

- **`tests/test_orthotropic_simultaneous.py`** — six quantitative anchors.

## Verification (quantitative anchors)

`tests/test_orthotropic_simultaneous.py` (6 passed; adjacent regression on
test_simultaneous_coupled_mma / test_coupled_thermal_to / test_thermal_simp /
test_nonlinear_fem = 31 passed):

1. **isotropic ke reproduces the closed form** to ≤ 1e-9 (2.9e-11 measured) —
   validates B, node ordering, Gauss quadrature.
2. **rotation correctness**: isotropic D rotation-invariant (1e-12); `D(90°)`
   swaps E₁↔E₂; `D(0)=D₀`; `dD/dθ` vs central FD ≤ 1e-6.
3. **both compliance sensitivities vs central FD** ≤ 1e-4 on the top-|sensitivity|
   elements (measured: `dC/dρ` ≈ 9e-7, the novel `dC/dθ` ≈ 1e-5).
4. **simultaneous (ρ,θ) MMA**: compliance driven below half the start (1.20e3 →
   2.62e2), volume feasible (0.450), and deterministic (two runs identical).
5. **fibre-continuity constraint binds**: with `lim = 0.3·`(the free run's adjacent-
   angle variation), the unconstrained variation (0.461) exceeds `lim` while the
   constrained run lands on it (0.138 ≤ lim·1.05), at comparable compliance
   (≤ 1.5× the free value — here actually lower).
6. **error handling**: non-positive modulus, invalid Poisson raise `SolverError`.

## Honest scope notes

- **The continuity metric is the mean adjacent squared angle difference, not a
  manufacturability guarantee.** It penalises raw `θ_e − θ_f` jumps on the design
  grid; it does **not** account for the π-periodicity of fibre direction (a jump
  from `+89°` to `−89°` is physically 2° but scores as a large difference), nor
  does it enforce a steerable continuous fibre path. A period-aware metric
  (`sin²(θ_e−θ_f)` or vector-field smoothing) is a reopening item.
- **Single lamina, in-plane only.** `D₀` is one orthotropic ply; no stacking
  sequence, no laminate `[A,B,D]` coupling, no out-of-plane — consistent with the
  2.5D red line.
- **Dense assembly, per-element ke rebuilt each iteration.** Every element's
  `ke(θ_e)` and `dke/dθ(θ_e)` are recomputed each MMA iteration (the angles
  change), and the global solve is dense — fine for smoke meshes, O(n_elem) ke
  builds per iter. No sparse template (the ke pattern is constant but the values
  change every element every iter, so the D066-style template saves less here).
- **`dC/dθ` ignores cross-coupling through neighbours' angles** only in the sense
  that each element's stiffness depends on its *own* θ; that is exact for this
  element-wise rotation (validated by FD). The continuity constraint is what
  couples angles, and its gradient is exact (graph Laplacian).
- **MMA is non-convex here**; the continuity-constrained run reaching *lower*
  compliance than the free run in the probe is a local-optimum artefact, not a
  claim that continuity improves compliance. The anchor only asserts
  "comparable" (≤ 1.5×).
- θ-bound `π/2` spans all fibre directions (period-π stiffness), but the optimiser
  can still settle in orientation local minima; no global orientation search.

## Reopening criteria

- **Period-aware fibre continuity** (`sin²(Δθ)` or unit-director vector smoothing)
  so `+89°`/`−89°` neighbours are not falsely penalised, plus a steerable
  continuous-path constraint for true manufacturability.
- **Laminate / multi-ply** stiffness (stacking sequence, `[A,B,D]`), still 2.5D.
- **Sparse / cached assembly** for the orthotropic path on larger meshes (only the
  changed-angle elements need a ke rebuild between iterations).
- **Orientation continuation / multi-start** to mitigate the non-convex
  orientation local minima.
- **Stress or buckling constraints** on the orthotropic body (combine with D074).

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
