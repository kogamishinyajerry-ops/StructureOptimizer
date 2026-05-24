# D044 — geometric-nonlinear TO via full-TL adjoint sensitivity (Wave OO)

**Status**: Accepted
**Wave**: OO (v7)
**Supersedes**: none (consumes D034's full-TL forward solver as a TO driver)
**Superseded by**: none

## Context

v6 Wave EE (D034) replaced the v5 simplified geometric-nonlinear FEM with a
**full Total-Lagrangian** Green-strain Newton solver (`core/total_lagrangian.py`),
verified by objectivity (1e-10) and a constant-strain patch test. Its reopening
criteria named the next step explicitly: *drive topology optimisation with the
full TL forward solver* — i.e. a TL **adjoint** sensitivity, not the v5
`nonlinear_simp` path which still calls the simplified nonlinear FEM.

## Decision

`core/nonlinear_simp.py` gains `tl_adjoint_compliance_sensitivity(config, mesh,
densities, n_load_steps=5) → TLAdjointResult(compliance, sensitivity, converged)`.

It uses a **local import** of the v6 full-TL internals (`solve_total_lagrangian`,
`_element_internal_force_and_tangent`, `_density_scale`, `_plane_stress_D`,
`_build_load_vector`) so the existing v5 `run_nonlinear_simp` driver and its
top-of-file import block are untouched (no drive-by; the pre-existing I001
import-sort nit in this file is left as-is).

Derivation of the adjoint, for end-compliance `C = fᵀu`:

- The TL residual is `R(u, ρ) = f_int(u, ρ) − f_total = 0` at convergence.
- `dC/dρ = fᵀ (du/dρ)`, and differentiating the residual gives
  `K_T (du/dρ) = −∂f_int/∂ρ`, with `K_T = ∂f_int/∂u` the consistent tangent.
- Adjoint `λ` solves `K_T λ = f_total` (K_T symmetric), so
  `dC/dρ_e = −λᵀ (∂f_int/∂ρ_e)`.
- Each element's TL internal force is **linear in its SIMP modulus scale**
  (`f_int,e = k_scale_e · g_e(u)`), so `∂f_int,e/∂ρ_e = (dk_scale_e/dρ_e /
  k_scale_e) · f_int,e`, giving

      dC/dρ_e = −(dk_scale_e/dρ_e / k_scale_e) · (λ_eᵀ f_int,e),

  with `dk_scale_e/dρ_e = p·ρ_e^(p−1)·(1−ρ_min)`.

In the linear limit `K_T → K`, `f_int = K u`, `λ → u`, and this reduces to the
classic self-adjoint `−u_eᵀ (dK_e/dρ) u_e`.

Implementation: solve the forward TL once, reassemble `K_T` and per-element
`f_int,e` at the converged `u`, solve the adjoint on free DOFs, then accumulate
the per-element sensitivity (void elements skipped).

## Verification (quantitative)

- **Adjoint vs central-FD** (`test_tl_adjoint_sensitivity_matches_central_fd`):
  on a perturbed cantilever the analytic sensitivity matches central differences
  of the converged TL compliance to rel 2e-4 on the 5 most-sensitive design
  elements (FD step 1e-6) — the blueprint's headline anchor for §3.
- **Sign** (`test_tl_adjoint_sensitivity_sign_is_negative_where_loaded`): adding
  material lowers compliance, so `dC/dρ_e ≤ 0` over design elements and strictly
  `< 0` at the most-strained ones.
- **Nonlinearity is real** (`test_geometric_nonlinearity_changes_compliance`):
  the TL end-compliance differs measurably from the linear-elastic compliance of
  the same design — the driver consumes the genuine large-deformation solve, not
  a relabelled linear one.
- **Contract** (`test_tl_adjoint_rejects_density_mismatch`): wrong density count
  → `SolverError("density_count_mismatch")`. 4 tests, all green. Adjacent
  `test_total_lagrangian` (8) + `test_nonlinear_simp` (5) unchanged.

## Honest scope notes

- This delivers the **sensitivity** (the hard, verifiable piece), not a full
  OC/MMA loop wrapped around the TL solve. A driver is a thin add-on: feed
  `tl_adjoint_compliance_sensitivity` into the existing `_optimality_criteria_update`.
  It is deferred because the verifiable contribution is the adjoint correctness,
  and a TL-in-the-loop optimiser is materially slower (Newton per design
  iteration) without adding a new analytical anchor.
- The FD tolerance is rel 2e-4 (not 1e-5): the central-FD reference is itself
  limited by the Newton convergence tolerance of two independent nonlinear solves
  and float64 cancellation at step 1e-6. 2e-4 is the honest achievable bound on
  this smoke mesh; tightening it would require a tighter Newton tol on both the
  analytic and FD solves, which trades runtime for a cosmetic number.
- End-compliance `C = fᵀu` (work of the final external load through the final
  displacement) is the objective; strain-energy or path-integral objectives would
  need their own adjoint and are out of scope here.

## Reopening criteria

- A TL-in-the-loop optimiser (OC/MMA driving `tl_adjoint_compliance_sensitivity`)
  with a documented large-deformation-vs-linear topology difference.
- Path-dependent objectives (e.g. total strain energy over the load path) → a
  per-load-step adjoint accumulation.
- Follower/displacement-dependent loads → `∂f_total/∂u ≠ 0` adds a term to `K_T`.

## Red lines

numpy-only (`np.linalg.solve` on the free-DOF tangent), 2D, single-line stderr —
all held. The v5 `run_nonlinear_simp` path and the top-of-file imports are
unchanged; the new code is reached only through the new function via a local
import.
