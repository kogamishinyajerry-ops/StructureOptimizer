# D037 — NSGA-III for ≥3 objectives (Wave HH)

**Status**: Accepted
**Wave**: HH (v6)
**Supersedes**: none (extends D023's NSGA-II; reopens its "≥3 objectives" note)
**Superseded by**: none

## Context

v5 Wave DD (D023) shipped `nsga_ii`, a bi-objective NSGA-II using crowding
distance for diversity preservation. Its honest scope note flagged that for
**three or more objectives** crowding distance degenerates — almost every point
becomes "boundary" and loses discriminating power, so the front collapses or
clusters. The reference-point method of NSGA-III (Deb & Jain 2014) is the
standard fix and was named as the v5+ upgrade. v6 turns it on.

## Decision

Add `nsga3` to `core/pareto_nsga.py`, reusing NSGA-II's non-dominated sort, SBX
crossover, and polynomial mutation; **only the survival selection differs**:

- `das_dennis_reference_points(n_obj, n_divisions)` → structured directions on
  the unit simplex. Every integer composition of `n_divisions` into `n_obj`
  parts, normalized; count = `C(n_divisions + n_obj − 1, n_obj − 1)` exactly.
- `_normalize_objectives(objs)` → translate by the ideal point, scale by the
  per-objective range (a robust simplification of the Deb-Jain hyperplane
  normalization; see honest note).
- `_associate(normalized, ref_dirs)` → each point to its nearest reference line
  by perpendicular distance.
- `_niching_select(...)` → fills the splitting front F_l by repeatedly choosing
  the least-crowded reference niche; empty niche → take the closest point, else
  random among that niche's members.
- `nsga3(eval_fn, n_vars, bounds_lower, bounds_upper, n_obj=3, n_divisions=12,
  population_size=None, ...)` — population defaults to `#ref_points` rounded up
  to a multiple of 4. `n_obj < 2` → single-line `SolverError`.

`nsga_ii` is untouched; bi-objective callers and fingerprints are unaffected.

## Verification (quantitative)

- **Das-Dennis counts** (`test_das_dennis_count_three_objective`,
  `test_das_dennis_count_small_and_four_objective`): reference-point counts
  equal the exact combinatorials `C(14,2)=91`, `C(6,2)=15`, `C(6,3)=20`; every
  row is non-negative and sums to 1 (on the simplex). This is the analytical
  anchor.
- **DTLZ2 sphere convergence** (`test_nsga3_dtlz2_converges_to_unit_sphere`):
  DTLZ2's true 3-objective Pareto front is the unit-sphere octant `Σf_i²=1`.
  The evolved front lands on that sphere (mean `Σf²` well below the random-init
  radius) with a non-trivial front size.
- **Front is non-dominated** (`test_nsga3_front_is_nondominated`): re-sorting
  the returned front yields a single front (no dominated points leak through).
- **Diversity** (`test_nsga3_three_objective_diversity`): per-objective spread
  stays wide (front does not collapse — the exact failure NSGA-II has at m≥3).
- **Contract** (`test_nsga3_rejects_single_objective`): `n_obj<2` →
  `SolverError`. 7 tests, all green. Adjacent `test_pareto_nsga` +
  `test_pareto` (19) unchanged.

## Honest scope notes

- `_normalize_objectives` uses ideal-point translation + range scaling, **not**
  the full Deb-Jain hyperplane-intercept normalization (which solves for m
  extreme points and the achievement-scalarizing intercepts). For well-formed,
  bounded fronts the association geometry is preserved; pathological degenerate
  fronts (near-coincident extremes) are out of scope.
- Niching tie-breaks among equally-empty niches are uniform-random (seeded), not
  the original "smallest index" — reproducible but not bit-identical to a
  reference NSGA-III implementation.
- Like NSGA-II, this post-processes/optimizes **cheap proxy** objective vectors
  (material assignment, sizing), not whole density fields per genome.

## Reopening criteria

- A study needing the rigorous Deb-Jain normalization on degenerate fronts →
  add the hyperplane-intercept solve.
- Constrained many-objective problems → add the feasibility-first tournament.

## Red lines

numpy-only, 2D-proxy, dense, single-line stderr — all held. (The 3 pre-existing
Wave-DD lint nits in this file — RUF059 line 51, B007 line 143, B905 line 408 —
are left untouched; not part of this wave.)
