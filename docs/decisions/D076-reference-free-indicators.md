# D076 — reference-(front)-free quality indicators: R2 + auto-ref hypervolume (Wave UUU, v11)

**Status**: Accepted
**Wave**: UUU (v11)
**Supersedes**: none (extends D068)
**Superseded by**: none

## Context

D068 added **IGD⁺** (`igd_plus`) as a weakly-Pareto-compliant multi-objective
quality indicator. Its honest limitation, recorded as a reopening criterion:

> *"reference-free quality indicators (hypervolume-only / R2)."*

IGD⁺ needs a **reference Pareto front** — the true front, or a dense
approximation. In a real optimisation that is exactly what you do **not** have
(if you had it you would not be optimising). So IGD⁺ is a benchmarking tool, not
an in-the-loop quality measure. Two standard indicators avoid the reference
front entirely: the **R2 indicator** (Tchebycheff) needs only a weight set and a
utopia point, and **hypervolume** needs only a reference point. v11 Wave UUU
delivers both in reference-front-free form.

## Decision

- **`multi_objective_to.r2_indicator(front, weights=None, ideal=None,
  n_divisions=10) → float`** — the R2 indicator for minimisation:

      R2(A) = (1/|W|) · Σ_{λ∈W}  min_{a∈A}  max_j λ_j · (a_j − z*_j)

  the mean over scalarisations of the best achievable weighted Tchebycheff
  utility (**lower is better**). `weights` defaults to Das-Dennis simplex
  directions (`das_dennis_reference_points`, reused from the NSGA-III machinery);
  `ideal` (utopia `z*`) defaults to the front's component-wise minimum. Needs
  **no reference front**.

- **`multi_objective_to.reference_free_hypervolume(front, margin=0.1) → float`** —
  dominated hypervolume with the reference point **auto-derived** from the front
  (`ref = max + margin·(max − min)`), delegating to the exact `hypervolume_2d` /
  `hypervolume_nd`. **Higher is better.** Needs no externally supplied reference
  point.

- **`tests/test_reference_free_indicators.py`** — five quantitative anchors.

## Verification (quantitative anchors)

`tests/test_reference_free_indicators.py` (5 passed; adjacent regression on
test_generalised_nsga / test_multi_objective_to / test_multi_load_case_to /
test_nsga3 / test_pareto_nsga / test_pareto / test_seeded_nsga below):

1. **R2 closed form**: front `{(1,1)}`, weights `{(1,0),(0,1),(0.5,0.5)}`, utopia
   `(0,0)` → R2 = mean(1, 1, 0.5) = 5/6, matched to 1e-12.
2. **R2 weakly Pareto-compliant**: `{(1,1)}` (dominating) scores strictly below
   `{(2,2)}`; adding the dominated `(2,2)` to `{(1,1)}` leaves R2 unchanged (the
   inner `min` ignores it).
3. **reference-free indicators rank identically to IGD⁺**: on four nested-better
   fronts (`base·{1.0, 0.8, 0.6, 0.4}`), R2 (lower=better), reference-free
   hypervolume (higher=better) and IGD⁺ (lower=better) all induce the order
   `[3,2,1,0]`, and each is strictly monotone along the improving sequence — so a
   practitioner *without* a true front (no IGD⁺) gets the same verdict.
4. **reference-free hypervolume auto-ref + monotone**: HV strictly increases when
   a non-dominated point is added, and equals the exact `hypervolume_2d` computed
   with the manually reconstructed auto-reference (1e-12).
5. **error handling**: empty front, weight/ideal dimension mismatch, non-positive
   margin all raise `SolverError`.

## Honest scope notes

- **R2 comparisons require a shared `ideal` and `weights`.** R2 is translation-
  and weight-dependent; comparing two fronts with each one's own default ideal
  (its own min) is meaningless. The tests therefore pass a **shared** `ideal` and
  fixed `weights` when ranking. The default (front's own min) is only an intrinsic
  single-front convenience — documented in the docstring.
- **R2 measures convergence + spread only through the chosen scalarisations.** A
  coarse Das-Dennis weight set can miss a gap between weight directions; it is not
  a substitute for a diversity indicator. `n_divisions` controls the resolution.
- **The ranking-agreement anchor is an empirical equivalence on well-formed
  nested fronts, not a theorem.** R2, hypervolume and IGD⁺ are all weakly
  Pareto-compliant, so they agree when one front *dominates* another; for
  incomparable fronts (crossing trade-offs) they can and do disagree — that is
  expected and not tested as agreement.
- **`reference_free_hypervolume`'s margin is a convention.** A different margin
  changes the absolute HV (not the ranking among fronts sharing a margin). For
  *cross-front* comparison a shared explicit reference point (the existing
  `hypervolume_2d/_nd`) is still preferable; the auto-ref wrapper is for the
  single-front, no-reference-supplied case.
- Hypervolume itself is exact (D068's `hypervolume_2d`/`_nd`); UUU only adds the
  reference-derivation convenience, no new HV algorithm.

## Reopening criteria

- **R2 with an explicit augmented Tchebycheff** (small linear term) to break ties
  on weakly-dominated points and improve sensitivity.
- **A dedicated diversity / spread indicator** (e.g. spacing, or the
  Riesz-energy of the front) to complement R2's convergence emphasis.
- **Adaptive weight sets** for R2 (e.g. weights placed by the front's own gaps)
  so the indicator resolves where the front is sparse.
- **Hypervolume contribution / k-EMOA selection** using these reference-free
  measures inside the optimiser loop, not just as post-hoc diagnostics.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
