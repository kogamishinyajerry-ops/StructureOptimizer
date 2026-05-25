# D102 — discrete angle-set selection (beyond ordering) (Wave EEEEEE, v14)

**Status**: Accepted
**Wave**: EEEEEE (v14)
**Supersedes**: none (extends D095 optimize_stacking_sequence)
**Superseded by**: none

## Context

D095 (v13 Wave FFFFF) optimised the stacking **sequence** — the *ordering* of a fixed
ply inventory — and recorded as a reopening criterion:

> *"angle-value selection beyond ordering."*

Ordering answers "given these plies, how do I stack them?"; **selection** answers the
prior question "which angles do I even use?". A composite designer picks plies from a
discrete manufacturable set (e.g. `{0, ±45, 90}`), with repetition, to build an `n`-ply
laminate. This wave adds that selection step and composes it with the D095 ordering
optimiser.

## Decision

- **`orthotropic_simp.select_ply_angles(d0, candidate_angles, n_plies, thickness=1.0,
  objective="max_bending", symmetric=False)`** → `StackingSequenceResult`. Selects a
  size-`n_plies` multiset (drawn with repetition from the discrete `candidate_angles`,
  **radians**), then hands it to `optimize_stacking_sequence` (D095) for the final
  arrangement.

  - **`max_bending`** — each position's `D_11` contribution `c_k·Q̄_11(θ_k)` has
    `c_k > 0`, so each is independently maximised by `θ* = argmax_{θ∈C} Q̄_11(θ)`. The
    **provably-global** selection is `n` copies of `θ*`, with
    `D_11 = (h³/12)·Q̄_11(θ*)` in closed form — no search.
  - **`min_coupling`** — brute-force over the size-`n` multisets of `C` (small `n`/`|C|`),
    each arranged by the inner `optimize_stacking_sequence`; the floor `‖B‖ = 0` is
    reached by a balanced multiset arranged symmetrically.

- **v14 integration铁律**: `select_ply_angles` **reuses** `optimize_stacking_sequence`
  (D095) verbatim for the arrangement, so a single-candidate selection reproduces the
  D095 result **bit-exactly** — composition does not alter the ordering optimiser.

## Verification (quantitative anchors)

`tests/test_angle_selection.py` (6 passed; adjacent regression on `test_stacking_sequence`
+ `test_balanced_laminate` + `test_orthotropic_simultaneous`, 18 pass):

1. **closed form**: `max_bending` from `{0,π/4,π/2}` (n=4) selects all-`θ*` (=0) and
   `D_11 == (h³/12)·max Q̄_11` to rel 1e-9.
2. **provably global**: exhaustive over all `|C|^n` (=3³) assignments confirms no
   assignment beats the closed-form `D_11` (rel 1e-9).
3. **selection ≻ ordering**: `select_ply_angles` (all-stiffest) gives strictly larger
   `D_11` than `optimize_stacking_sequence` *ordering* a fixed mixed inventory
   `[0,45,90,45]°`.
4. **‖B‖=0 floor**: `min_coupling` from `{±π/4}` (n=4) reaches `objective_value < 1e-7`
   and `‖B‖ < 1e-7` (balanced multiset, symmetric ordering).
5. **integration bit-exact**: single-candidate `[0.3]` selection reproduces
   `optimize_stacking_sequence([0.3]*4)` **bit-exactly** (`np.array_equal` on sequence /
   A / B / D and `==` on objective) — D095 reused, not altered.
6. **guards**: empty candidates / nonpositive plies / unknown objective / too-large
   `min_coupling` (n=7) raise single-string `SolverError`.

## Honest scope notes

- **Selection, not concurrent thickness or layer-count optimisation.** `n_plies` and
  per-ply `thickness` are fixed inputs; only the angle *values* are chosen. Choosing the
  number of plies or per-ply thicknesses is out of scope.
- **`max_bending` global optimum is degenerate (all one angle).** That is the honest,
  correct answer to "maximise `D_11` with free per-ply angle choice" — there is no
  ply-count or coupling constraint forcing diversity. A realistic design would add a
  balanced/symmetric or `D_16` constraint (see reopening); without one, all-stiffest is
  genuinely optimal, and the test confirms it exhaustively rather than dressing it up.
- **`min_coupling` is brute-force, capped** at `n_plies ≤ 6` and `|C| ≤ 6`
  (`combinations_with_replacement × permutations` inside D095). Adequate for the small
  laminates of 2.5-D design; not a large-scale combinatorial solver.
- **With `symmetric=True`, `min_coupling` is moot** — symmetry already forces `B = 0`,
  so every multiset ties at `‖B‖ = 0`; the meaningful symmetric objective is
  `max_bending`. (Documented in the docstring.)
- **Angles in radians** (the `rotate_plane_stress` convention); callers passing degrees
  get physically-wrong stiffnesses.
- **Not wired into the elastic MMA loop** — this is a standalone laminate-design
  primitive, not a constraint inside `simultaneous_elastic_orientation_mma`.

## Reopening criteria

- **Constrained selection**: maximise `D_11` *subject to* balanced (D101) /
  symmetric / `D_16` limits, so the optimum is no longer the degenerate all-one-angle.
- **Concurrent ply-count / thickness selection** (variable `n`, variable `t_k`).
- **Branch-and-bound or LP relaxation** to lift the small-`n` brute-force cap for
  larger discrete catalogues.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
