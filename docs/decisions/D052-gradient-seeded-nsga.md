# D052 — gradient-seeded NSGA-III density-field TO (Wave WW)

**Status**: Accepted
**Wave**: WW (v8)
**Supersedes**: none (extends D046's random-init NSGA-III)
**Superseded by**: none

## Context

v7 Wave QQ (D046) ran NSGA-III directly on density fields from a **random**
initial population, and was honestly shown not to beat gradient SIMP. D046's
reopening criterion named the fix: a **gradient-seeded initial population**
(warm-start from `run_simp` at several volume fractions) for a sharper front at
the same budget. v8 Wave WW delivers it.

## Decision

`core/multi_objective_to.py`:

- `multi_objective_to(..., seed_genomes=None)` — additive optional parameter:
  each provided design-element genome replaces a random member of the initial
  population (shape-checked → `SolverError`). Default `None` ⇒ identical to D046
  (QQ tests unaffected).
- `gradient_seeded_multi_objective_to(config, mesh,
  seed_volume_fractions=(0.2, 0.35, 0.5, 0.65, 0.8), **kwargs)` — runs `run_simp`
  at each volume fraction and injects those gradient-optimal density fields as
  `seed_genomes`, then runs the NSGA-III driver.

## Verification (quantitative)

- **Seeded beats random at the same budget** (`test_seeded_beats_random_at_same_budget`):
  at 10 generations × population 12, the seeded run's final hypervolume strictly
  exceeds the random run's (observed 171 637 vs 118 594, +45%), and the seeded
  front reaches far lower compliance (observed min 223 vs 2094, < 0.5×) — the
  gradient-SIMP-quality low-compliance endpoint the random search cannot find.
- **Monotone hypervolume** (`test_seeded_hypervolume_monotone`): the
  cumulative-archive hypervolume is non-decreasing (inherited D046 invariant).
- **Reproducible** (`test_seeded_reproducible`) + **seed-shape contract**
  (`test_seed_genome_shape_contract`). 4 tests, all green. Adjacent
  `test_multi_objective_to` (6) unchanged.

## Honest scope notes

- The seeds are **gradient-SIMP optima** at fixed volume fractions, so the
  warm-start essentially hands NSGA-III a near-Pareto set on the low-compliance
  side; the genetic search then fills/diversifies. The dramatic min-compliance
  gap (≈9×) reflects that gradient SIMP is simply much better at single-objective
  compliance than gradient-free search — the honest reading is "seed with
  gradients, diversify with NSGA", not "NSGA found these".
- Still bi-objective (compliance, volume) on the smoke mesh; ≥3 objectives and a
  hypervolume-vs-budget sweep across generation counts are reopening items.
- `gradient_seeded_multi_objective_to` costs `len(seed_volume_fractions)` extra
  `run_simp` calls up front (cheap on the smoke mesh; scales with mesh size).

## Reopening criteria

- Hypervolume-vs-budget study (seeded vs random across generation counts) to
  quantify the speed-up.
- ≥3 objectives (multi-load-case) with seeded warm-start.
- Seeding from non-SIMP references (e.g. BESO or a previous milestone's design).

## Red lines

numpy-only, 2D, single-line stderr (`SolverError`). The D046 random-init path is
unchanged (default `seed_genomes=None`); `run_simp` is consumed read-only.
