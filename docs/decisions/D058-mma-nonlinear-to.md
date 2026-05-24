# D058 — MMA-driven Total-Lagrangian nonlinear TO (Wave CCC)

**Status**: Accepted
**Wave**: CCC (v9)
**Supersedes**: none (extends D050's OC-driven TL nonlinear TO)
**Superseded by**: none

## Context

D050 (Wave UU) closed the geometric-nonlinear TO loop with an **optimality-criteria
(OC)** update: a single move-limited heuristic that handles exactly one constraint
(volume) and assumes a monotone, separable objective. D050's reopening criterion
named **"MMA driving the TL adjoint (handles additional constraints, faster
convergence)."** Wave CCC delivers that: the same D044 Total-Lagrangian adjoint
sensitivity, driven by the Method of Moving Asymptotes (`core/mma.py`, already in
the codebase since v4) with the volume constraint written as an explicit inequality.

## Decision

`core/nonlinear_simp.py`:

- `mma_nonlinear_to(config, mesh, n_load_steps=4, max_iter=30, change_tol=1e-3)`
  → `NonlinearTOResult` (reused). Each iteration:
  1. solve the forward TL + adjoint for `dC/dρ`
     (`tl_adjoint_compliance_sensitivity`, D044);
  2. density-filter the sensitivity (Sigmund, `core.filtering.density_filter`);
  3. one `mma_step` on the design-cell sub-vector with the single inequality
     `g(x) = mean(x) − vf ≤ 0`, Jacobian `∂g/∂x_e = 1/n`;
  4. re-apply void/solid masks.
  Stops on `max|Δx| < change_tol` or `max_iter`.
- MMA operates on the design-cell sub-vector; void/solid cells are held by the
  masks. The MMA Lagrange multipliers are available from `mma_step` (KKT
  diagnostics) but not surfaced in the result. Uses a local import of
  `core.mma` to keep the module's top-level import block unchanged.

## Verification (quantitative)

- **Descent + feasibility** (`test_mma_nonlinear_to_descends_and_is_feasible`):
  the full-TL end-compliance drops below half its initial value (observed
  2066 → 553, a 3.7× reduction) and the final volume satisfies the inequality
  (`≤ vf + 0.02`; observed 0.4497 ≤ 0.45).
- **Competitive with OC** (`test_mma_nonlinear_to_competitive_with_oc`): at the
  same final volume, MMA's compliance is within 5% of OC's — observed ratio
  **0.946** (MMA *below* OC by 5.4%). This is the honest D050 claim: MMA matches
  or beats OC on the compliance-only objective; its real payoff is *additional*
  constraints (the reopening item).
- **Determinism** (`test_mma_nonlinear_to_deterministic`): no RNG → bit-identical
  densities + compliance history across runs.
- **Volume-tail property** (`test_property_mma_nonlinear_volume_non_increasing_tail`):
  over the back half of the iterations the volume stays at/under the constraint
  (the moving asymptotes settle the design onto the feasible boundary). 4 tests,
  all green. Adjacent `test_nonlinear_simp` + `test_nonlinear_to_oc` +
  `test_nonlinear_to_adjoint` + `test_total_lagrangian` (19) unchanged.

## Honest scope notes

- On this **compliance-only** problem MMA is competitive with OC (≈0.95× here),
  not categorically superior; the headline advantage of MMA — multiple/general
  inequality constraints (stress, buckling, displacement) — is *not* exercised
  here, it is the reopening item. The test asserts "within 5%", not "strictly
  better", to stay robust and honest.
- The volume constraint is the only constraint wired; `mma_step`'s multi-
  constraint capability (`m > 1`) is unused.
- Convergence on the smoke mesh hits `max_iter` (`converged=False`) but the design
  is stable (the volume-tail property); a tighter `change_tol`/larger `max_iter`
  is a cost/quality trade, not a correctness issue.
- Still the same single-load-step-count TL adjoint as D044/D050; no continuation
  scheduling (a separate D050 reopening item).

## Reopening criteria

- **Multi-constraint MMA-TL**: add a stress or buckling inequality alongside
  volume (the real reason to prefer MMA over OC).
- Load/continuation scheduling (ramp the load over MMA iterations) for robustness
  on highly nonlinear problems.
- KKT-residual convergence test (use the returned multipliers) instead of the
  `max|Δx|` heuristic.

## Red lines

numpy-only (`core.mma` is numpy-only), 2D/2.5D, single-line stderr via the
existing `SolverError` paths in the TL solver. The OC loop (`nonlinear_to_oc`) and
all D044/D050 paths are unchanged; `mma_nonlinear_to` is purely additive.
