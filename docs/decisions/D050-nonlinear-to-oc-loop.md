# D050 — geometric-nonlinear TO full OC loop (Wave UU)

**Status**: Accepted
**Wave**: UU (v8)
**Supersedes**: none (closes D044's deferred driver)
**Superseded by**: none

## Context

v7 Wave OO (D044) delivered the full-Total-Lagrangian adjoint sensitivity
`tl_adjoint_compliance_sensitivity` but explicitly stopped short of a driver
("a TL-in-the-loop optimiser ... is deferred ... materially slower"). D044's
reopening criterion named it: *an OC/MMA loop driving the TL adjoint with a
documented large-deformation-vs-linear topology difference*. v8 Wave UU closes
that loop.

## Decision

`core/nonlinear_simp.py` gains `nonlinear_to_oc(config, mesh, n_load_steps=4,
max_iter=25, change_tol=1e-2) → NonlinearTOResult(densities, compliance_history,
volume_history, converged, mesh_shape)`.

Each iteration: solve the forward TL + adjoint for dC/dρ
(`tl_adjoint_compliance_sensitivity`), density-filter the sensitivity
(`density_filter`), OC update under the volume constraint
(`_optimality_criteria_update`), re-apply masks (`_apply_density_masks`). The
**only** difference from the linear SIMP loop is the sensitivity: it is the
genuine large-deformation adjoint, not the v5 linear-on-nonlinear approximation
of `run_nonlinear_simp`. Stops on `max|Δρ| < change_tol` or `max_iter`.

## Verification (quantitative)

- **Loop + beats-linear** (`test_nonlinear_oc_loop_and_beats_linear_under_large_deformation`):
  on the smoke cantilever (15 iters, 4 load steps) the TL end-compliance drops
  2066 → 584 (< 0.5·C₀), the history is near-monotone (≤1.05× step-over-step),
  and the volume holds at the 0.45 target. The TL-aware optimum has **lower TL
  compliance than the linear-SIMP optimum evaluated under the same TL solve**
  (584 ≤ 635, an 8% margin) — large deformation genuinely matters — and the two
  density fields differ (L2/√n ≈ 0.066 > 5e-3).
- **Single step well-formed** (`test_nonlinear_oc_single_step_is_well_formed`):
  one OC step records initial+final compliance, holds the target volume, and
  keeps densities in [min, 1]. 2 tests, all green. Adjacent
  `test_nonlinear_to_adjoint` + `test_nonlinear_simp` + `test_total_lagrangian`
  (17) unchanged.

## Honest scope notes

- **OC, not MMA**; single objective (TL end-compliance) under a volume
  constraint. MMA and multi-constraint are a further step.
- The **magnitude** of the large-deformation-vs-linear topology difference scales
  with load: at the smoke load the L2 gap is modest (≈0.066) and the compliance
  margin ≈8%; under a heavier load (≈5×) the loop reaches a ≈15% margin with a
  clearly divergent layout (≈0.30). The test asserts the *direction* (TL-aware ≤
  linear under TL) plus a non-trivial difference, not a fixed large gap — the gap
  is load-dependent and over-claiming it would be dishonest.
- The "beats linear" inequality requires the TL loop to be **converged enough**;
  a truncated loop (few iterations under a heavy load) can sit above the
  fully-converged linear design measured under TL. The test uses 15 iterations so
  the inequality holds with margin; the ADR notes this so future tuning does not
  truncate it into a flake.
- TL forward+adjoint per iteration makes this materially slower than linear SIMP
  (≈17 s for 15 smoke iterations); production runs want a coarse-to-fine or
  reduced-load continuation schedule.

## Reopening criteria

- MMA driving the TL adjoint (handles additional constraints, faster convergence).
- Load/continuation scheduling (ramp the load over OC iterations) for robustness
  at large deformation.
- A combined nonlinear + stress or nonlinear + buckling constrained driver.

## Red lines

numpy-only (reuses the existing OC update + density filter), 2D, single-line
stderr. `run_nonlinear_simp` (v5 path) and `tl_adjoint_compliance_sensitivity`
(D044) are unchanged; the new driver only consumes them.
