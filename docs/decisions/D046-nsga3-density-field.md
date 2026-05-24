# D046 — NSGA-III directly on the density field (Wave QQ)

**Status**: Accepted
**Wave**: QQ (v7)
**Supersedes**: none (lifts D037/D023's proxy restriction)
**Superseded by**: none

## Context

v5 Wave DD (`pareto_nsga`) ran NSGA on **proxy** problems (material assignment,
sizing) or as a **post-processor** of pre-computed single-objective solutions.
Its own docstring flags the reason: *"This is not a from-scratch SIMP-via-NSGA —
that would be prohibitively expensive (each genome = whole density field)."*
D037 + D023's reopening criterion named the upgrade: a genetic multi-objective
driver whose decision vector **is** the density field. v7 Wave QQ delivers it for
the (compliance, volume) trade-off.

## Decision

`core/multi_objective_to.py`:

- `hypervolume_2d(points, reference)` — exact dominated area of a 2-objective
  minimisation set: filter to points inside the reference, keep the
  non-dominated staircase (sorted by f1 ascending), sum
  `Σ (ref₀ − f1_i)·(prev_f2 − f2_i)` with `prev_f2` starting at `ref₁`.
- `_nondominated(objs)` — non-dominated mask of a minimisation objective set.
- `multi_objective_to(config, mesh, n_generations, population_size, n_divisions,
  …)` → `MultiObjectiveTOResult(front_objectives, front_densities, hv_history,
  reference_point, n_front)`. Each genome is the design-element density in [0,1]
  (void floor applied before the FEM solve); objectives are
  `(compliance = solve_linear_elastic(...).compliance, volume = mean(genome))`.
  The NSGA-III survival loop **reuses** `pareto_nsga`'s building blocks
  (`_non_dominated_sort`, `_generate_offspring`, `_niching_select`,
  `das_dennis_reference_points`) so `pareto_nsga` is untouched (no drive-by).
- A **fixed** hypervolume reference `(c_worst·1.05, 1.05)` (worst stiffness =
  all-min-density compliance, full volume) and a **cumulative non-dominated
  archive** are maintained so the recorded hypervolume is monotone by
  construction.

## Verification (quantitative)

- **Exact hypervolume** (`test_hypervolume_2d_exact`): single rectangle = 4.0;
  two-point union `[1,3]×[2,3] ∪ [2,3]×[1,3]` = 2+2−1 = 3.0 (inclusion–exclusion);
  a dominated point leaves it unchanged; points outside the reference contribute
  0 — all hand-computed.
- **Monotone archive hypervolume** (`test_archive_hypervolume_is_monotone`): the
  per-generation archive hypervolume is non-decreasing (≥ −1e-9) and strictly
  improves end-to-end — the §5 anchor. This is an algorithmic invariant of the
  cumulative archive + fixed reference, independent of optimiser quality.
- **Genuine trade-off** (`test_front_is_a_genuine_tradeoff`): the evolved front
  has ≥2 points and volume falls monotonically as compliance rises (the defining
  property of a non-dominated bi-objective front).
- **Honest endpoint** (`test_gradientfree_front_does_not_dominate_simp`): no
  evolved point dominates the gradient-SIMP point (same penalised-compliance and
  volume definitions) — the driver does not beat gradients, and the test asserts
  that explicitly rather than claiming superiority.
- **Reproducible** (`test_reproducible_with_seed`) + **contracts**
  (`test_contracts`: n_generations / population). 6 tests, all green. Adjacent
  `test_pareto_nsga` (6) + `test_nsga3` + `test_pareto` (20) unchanged.

## Honest scope notes

- This is a **gradient-free** search and is *not* competitive with gradient SIMP
  on a single objective — the test suite verifies it never dominates the SIMP
  point rather than pretending otherwise. Its contribution is a verifiable
  Pareto front of real FEM-evaluated density fields plus a monotone-hypervolume
  convergence signal, which gradient SIMP (single-objective) does not produce.
- Bi-objective (compliance, volume) on the smoke mesh. Three objectives (e.g.
  two load cases + volume) work through the same `das_dennis_reference_points`
  niching but cost ∝ population × generations × FEM solves; left to a driver
  config rather than baked in.
- On a 240-element field with a modest population/generation budget the front is
  coarse — this is a *capability* (real density-field NSGA-III, the thing v5
  deferred), not a production optimiser. A seeded/hybrid initial population
  (gradient SIMP at several volume fractions) would sharpen it (reopening).

## Reopening criteria

- Gradient-seeded initial population (warm-start from `run_simp` at several volume
  fractions) for a sharper front, with a hypervolume-vs-budget study.
- ≥3 objectives (multi-load-case compliance + volume) with a documented
  reference-point coverage check.
- Reference-point-adaptive niching for non-convex fronts.

## Red lines

numpy-only, 2D, single-line stderr (`SolverError`). `pareto_nsga`,
`solve_linear_elastic` and `run_simp` are unchanged; the new driver only consumes
them.
