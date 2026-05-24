# D060 — ≥3-objective multi-load-case NSGA-III + seeded warm-start (Wave EEE)

**Status**: Accepted
**Wave**: EEE (v9)
**Supersedes**: none (extends D046's 2-objective density-field NSGA-III + D052's seeding)
**Superseded by**: none

## Context

D046 (Wave QQ) delivered density-field NSGA-III for the 2-objective (compliance,
volume) trade-off; D052 (Wave WW) added gradient-SIMP warm-starting. D052's
reopening criterion named **"≥3 objectives (multi-load-case) with seeded
warm-start"**. Wave EEE delivers it: an exact n-D hypervolume + a 3-objective
driver minimising compliance under two conflicting load cases plus volume.

## Decision

`core/multi_objective_to.py`:

- `hypervolume_nd(points, reference)` — exact dominated hypervolume of an
  n-objective minimisation set via **Hypervolume by Slicing Objectives (HSO)**:
  slice along the last objective, recurse on the (n−1)-D projection of the points
  reaching each slab, base case `hypervolume_2d` at n=2 (and `ref₀−min` at n=1).
- `multi_load_case_to(config, mesh, load_cases=None, ...)` — NSGA-III over density
  fields with `n_obj = len(load_cases) + 1` objectives: compliance under each load
  case + volume. Default `load_cases` = the original loads plus a horizontal
  variant (fx/fy swapped), which genuinely conflict. Reuses the same NSGA-III
  machinery as `multi_objective_to` (Das-Dennis directions, non-dominated sort,
  niching, offspring) and the cumulative `hypervolume_nd` archive; supports
  `seed_genomes` warm-start. Each load case is a `dataclasses.replace(config,
  loads=lc)`.

## Verification (quantitative)

- **HSO hypervolume exact** (`test_property_hypervolume_nd_matches_2d_and_known_boxes`):
  matches `hypervolume_2d` over 40 random 2-D fronts (1e-12); a single 3-D box =
  1.0; two overlapping boxes = 0.375 (inclusion-exclusion); a dominated point
  contributes nothing. (Property test.)
- **Das-Dennis 3-objective count** (`test_das_dennis_three_objective_exact_count`):
  the reference-point count is exactly `C(d+2, 2)` for d ∈ {4,6,8} → {15,28,45}.
- **3-objective front + monotone HV** (`test_three_objective_front_and_monotone_hypervolume`):
  the front has 3 objective columns; the cumulative-archive hypervolume is
  non-decreasing.
- **Genuine conflict** (`test_load_cases_genuinely_conflict`): the LC1-optimal
  design and the LC2-optimal design are distinct, and the LC1-optimal design is
  worse under LC2 (observed C₂ 184.9 vs 100.3) — a real Pareto trade-off.
- **Seeded warm-start** (`test_seeded_warm_start_improves_front`): gradient-SIMP
  seeds lift the final hypervolume above a random start (observed 1.93e9 vs 1.51e9)
  and sharpen the LC1 endpoint > 2× (observed min-C₁ 267 vs 2243). 6 tests, all
  green. Adjacent `test_multi_objective_to` + `test_pareto_nsga` + `test_seeded_nsga`
  (16) unchanged.

## Honest scope notes

- Still a **gradient-free** evolutionary search: it produces a verifiable
  FEM-evaluated Pareto front, it does not beat gradient SIMP per single objective
  (the warm-start *injects* the gradient endpoint rather than the GA discovering
  it). This is the same honest stance as D046.
- The default second load case is a simple fx/fy swap; arbitrary load cases are
  accepted via `load_cases`. Objectives are compliance-per-case + volume; other
  objectives (stress, frequency) are not wired.
- HSO is `O(k^{n-1})` in the front size k — fine for the small fronts here, not
  intended for many-objective (n ≫ 4) large-front problems.
- `multi_load_case_to` deliberately duplicates the NSGA-III loop of
  `multi_objective_to` rather than refactoring the working 2-objective function
  (surgical, no-regression); the shared *helpers* (`pareto_nsga`) are reused.

## Reopening criteria

- A single generalised `nsga3_density_to(eval_fn, n_obj, ...)` that both the
  2-objective and multi-load drivers call (refactor once both are battle-tested).
- More objectives: add stress / fundamental-frequency objectives alongside
  multi-load compliance.
- A reference-point-based HV indicator (IGD+) for many-objective fronts where HSO
  becomes expensive.

## Red lines

numpy-only, 2D/2.5D, single-line stderr (`SolverError`:
`mo_to_n_generations_must_be_positive`, `mo_to_population_too_small`,
`mo_to_seed_genome_shape_mismatch`, `mlc_to_no_load_cases`). The 2-objective
`multi_objective_to` / `gradient_seeded_multi_objective_to` and all D046/D052
paths are unchanged; the n-D HV + multi-load driver are additive.
