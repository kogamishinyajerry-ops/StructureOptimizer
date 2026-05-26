# D108 — constrained discrete angle selection (constrained_select) (Wave CCCCCCC, v15)

**Status**: Accepted
**Wave**: CCCCCCC (v15)
**Supersedes**: none (closes D102's reopening, extends D102 selection)
**Superseded by**: none

## Context

D102 (v14) added `select_ply_angles` but recorded a degeneracy as a reopening criterion:

> *"Constrained selection: maximise D_11 subject to balanced/symmetric/D₁₆ limits, so the
> optimum is no longer the degenerate all-one-angle."*

D102's `max_bending` optimum is `n` copies of the single stiffest angle — degenerate and
(off the 0/π2 axes) unbalanced (`A₁₆ ≠ 0`). D108 adds a balanced constraint so the
optimum is non-degenerate and `A₁₆ = A₂₆ = 0`.

## Decision

- **`select_ply_angles(..., balanced: bool = False)`**. When `True`, dispatches to
  **`_constrained_select_balanced`**: the candidate set is augmented with negatives
  (`±candidates`), the size-`n` multiset search is **filtered to balanced multisets**
  (`is_balanced_laminate`, equal +θ/−θ counts), and the best per objective is arranged by
  `optimize_stacking_sequence`. `balanced=False` (default) reproduces D102 exactly.

- **The honest twist — balance costs no D_11.** `Q̄₁₁` is **even** in θ, so the
  max-`D_11` balanced pick (±θ* of the stiffest magnitude) attains the *same* `D_11` as
  the unconstrained all-θ*. The constraint therefore de-degenerates the design and zeros
  `A₁₆/A₂₆` at **no bending-stiffness cost** — while the all-one-angle solution is
  excluded because it is not balanced (off the 0/π2 axes).

## Verification (quantitative anchors)

`tests/test_constrained_select.py` (6 passed; adjacent regression on `test_angle_selection`
+ `test_balanced_stacking` + `test_stacking_sequence`, 18 pass). The constraint **truly
binds** (v15 discipline):

1. **feasible + non-degenerate**: `balanced=True` from `{30°,60°}` (n=4) ⟹ `A₁₆=A₂₆=0`
   and ≥2 distinct angles (±30°).
2. **removes the degenerate optimum**: `balanced=False` is the all-one-angle (1 distinct,
   `|A₁₆|>1e3`); `balanced=True` is ≥2 distinct with `A₁₆=0`.
3. **no D_11 cost**: `balanced=True` `D_11` equals `balanced=False` `D_11` to rel 1e-9
   (the even-Q̄₁₁ twist).
4. **byte-exact default (integration铁律)**: `balanced=False` reproduces D102
   (`np.array_equal` sequence/D, `==` objective).
5. **min_coupling floor**: balanced `min_coupling` still reaches `‖B‖<1e-7`.
6. **guards**: no balanced multiset of odd size from off-axis candidates
   (`select_no_balanced_multiset`); too-large brute force (`select_min_coupling_too_large`).

## Honest scope notes

- **Balance is free for D_11 (even Q̄₁₁), so the constraint removes *degeneracy*, not
  objective value.** This is the honest, correct result — there is no D_11 *trade-off*
  here (unlike a genuine Pareto constraint). The value delivered is "non-degenerate +
  extension-shear-decoupled at no bending cost," not "constrained optimum sacrifices the
  objective." If the candidate set's stiffest angle is self-balanced (0/π2 ∈ candidates),
  the all-one-angle solution *is* balanced and the constraint does not bite — the demo
  deliberately uses off-axis candidates.
- **Brute-force over balanced multisets**, capped at `n ≤ 6`, `|candidates| ≤ 6`
  (augmented to `±`). Adequate for 2.5-D laminate catalogues; not a large combinatorial
  solver.
- **A₁₆/A₂₆ only** — not D₁₆/D₂₆ (Wave EEEEEE, D110).
- **Angles in radians**; uniform thickness; not wired into the elastic MMA loop.

## Reopening criteria

- **A genuine objective trade-off**: a constraint that *does* cost the objective (e.g.
  min-coupling-and-max-bending jointly, or a D₁₆ limit that conflicts with D_11).
- **Symmetric+balanced selection** and **per-ply thickness** selection.
- **Branch-and-bound** to lift the brute-force cap.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
