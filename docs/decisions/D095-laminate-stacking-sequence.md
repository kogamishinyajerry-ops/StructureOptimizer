# D095 — laminate stacking-sequence optimisation (Wave FFFFF, v13)

**Status**: Accepted
**Wave**: FFFFF (v13)
**Supersedes**: none (extends D087 laminate_abd)
**Superseded by**: none

## Context

D087 (v12 Wave GGGG) added `laminate_abd` (classical-lamination-theory [A, B, D]) and
recorded a reopening item:

> *"Connect `laminate_abd` to a stacking-sequence optimisation — choose the discrete
> ply angles / their order to minimise extension–bending coupling B or maximise bending
> stiffness D, with symmetric / balanced constraints."*

`laminate_abd` only *evaluates* a stack; it does not choose the order. This wave adds
the optimisation over the **arrangement** of a fixed ply inventory.

## Decision

- **`orthotropic_simp._stacking_position_weights(n, thickness)`** — the bending
  position weights ``c_k = (z_k³ − z_{k-1}³)/3`` (the per-ply multiplier on ``Q̄_11`` in
  ``D_11``), largest at the surfaces.

- **`orthotropic_simp.optimize_stacking_sequence(d0, ply_angles, thickness=1.0,
  objective="max_bending", symmetric=False)`** → `StackingSequenceResult`:
  - **`max_bending`** — since ``D_11 = Σ_k c_k·Q̄_11(θ_k)`` with **position-only**
    weights ``c_k``, the global maximiser is the **rearrangement inequality**: put the
    stiffest plies at the highest-``c`` (outer-surface) positions. **Closed form,
    provably global, no search.**
  - **`min_coupling`** — minimise ``‖B‖_F`` by exhaustive search over distinct
    permutations (exact; guarded to ``n ≤ 8``).
  - **`symmetric=True`** — `ply_angles` is the bottom half-stack; the full laminate is
    ``half + reversed(half)`` ⟹ ``B = 0`` exactly (the classical mid-plane decoupling),
    half ordered for maximum ``D_11``.

- **`tests/test_stacking_sequence.py`** — six anchors.

## Verification (quantitative anchors)

`tests/test_stacking_sequence.py` (6 passed; adjacent regression on
`test_orthotropic_simultaneous` + `test_periodic_fibre_laminate` +
`test_fibre_steering_thermal`, 16 pass):

1. **max_bending = brute-force global optimum**: the rearrangement ordering's ``D_11``
   equals the maximum over *all* permutations of a 6-ply inventory to rel 1e-9.
2. **stiffest plies at surfaces**: for a 0°/90° inventory the optimum places 0° at both
   surfaces and 90° at the mid-plane.
3. **symmetric ⟹ B = 0 exactly**: a mirror-symmetric stack has ``‖B‖ < 1e-9``; the
   built sequence is exactly `half + reversed(half)`.
4. **min_coupling = brute-force min and reaches 0**: matches the ‖B‖-minimal permutation
   (abs 1e-12) and reaches ``‖B‖ < 1e-9`` for [0,0,90,90] (which has a symmetric
   arrangement).
5. **min_coupling beats a bad ordering**: the optimised coupling is < 1e-6× the strongly
   coupled [0,0,90,90]-as-given stacking (which is > 1e3).
6. **guards**: empty / nonpositive thickness / unknown objective / > 8 plies for the
   brute-force path raise single-string `SolverError`.

## Honest scope notes

- **Optimises the *ordering* of a fixed inventory, not the angle *values*.** The ply
  angles are given; the wave chooses their arrangement. Continuous or discrete-set angle
  *selection* (which angles to use at all) is a larger MMA/genetic problem, not done
  here.
- **`max_bending` maximises `D_11` only** — a single bending component along the global
  x-axis. A multi-component / off-axis bending objective (e.g. maximise the smallest
  eigenvalue of D, or D in a given direction) is not the rearrangement form and would
  need a search; reopening item.
- **`min_coupling` is brute-force, O(n!).** Guarded to ``n ≤ 8`` (40 320 perms ×
  trivial ABD ≈ sub-second). Larger stacks need a heuristic (genetic / simulated
  annealing) — out of the small-laminate 2.5-D regime, not pursued.
- **No balanced ( +θ/−θ pairing ) constraint yet.** `symmetric=True` enforces the
  B = 0 decoupling; a *balanced* constraint (zeroing the A₁₆/A₂₆ shear-extension
  coupling) is a separate constraint, named as a reopening item.
- **Uniform ply thickness.** All plies share one `thickness`; per-ply thickness is
  supported by the underlying `laminate_abd` but the optimiser assumes uniform.

## Reopening criteria

- **Balanced-laminate constraint** (+θ/−θ pairs ⟹ A₁₆ = A₂₆ = 0) alongside the
  symmetric B = 0 constraint.
- **Multi-component / directional bending objective** (e.g. maximise the minimum
  eigenvalue of D, or D in an arbitrary in-plane direction) via a search rather than the
  single-component rearrangement.
- **Angle-set *selection*** (choose which discrete angles to include, not just order a
  fixed inventory) via discrete MMA or a metaheuristic for ``n > 8``.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
