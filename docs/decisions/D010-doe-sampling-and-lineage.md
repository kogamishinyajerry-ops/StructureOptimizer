# D010 — DOE sampling (LHS + Sobol) + design lineage tracking

- **Status**: accepted
- **Date**: 2026-05-16
- **Wave**: O (v2.4.0)

## Context

The v3.x rubric §5 dedicates 6 points to "user面 / 流程":

- §5.1 (3 pts): DOE study runner with ≥ 2 sampling methods (LHS + Sobol)
- §5.2 (3 pts): design lineage tracking (run dirs carry `parent_id`,
  studies carry a lineage tree)

The v1.x/v2.x study runner only supports the Cartesian-product grid:
`{vol: [0.3, 0.5], radius: [1, 2]}` → 4 candidates. For
parameter-space exploration in higher dimensions, grid blows up
combinatorially (5 dims × 5 values = 3125 candidates). DOE sampling
gives **good coverage at sub-grid cost**.

Design lineage was missing entirely — a run was a leaf with no
genealogy. For "iterative refinement" workflows (rank candidates → pick
top one → derive new study around it) you need to track who-came-from-whom.

## Decision

### 1. Sampling module (§5.1)

`structure_optimizer/core/sampling.py`:
- `lhs_samples(n, n_dims, rng)` — pure NumPy Latin Hypercube. Each dim
  partitioned into n equiprobable bins; one uniform draw per bin; bins
  permuted per dim so the joint distribution covers the unit hypercube.
- `sobol_samples(n, n_dims, rng)` — wraps `scipy.stats.qmc.Sobol` (raises
  `RuntimeError` if scipy unavailable). We deliberately do NOT roll our
  own Sobol — direction vectors + carryover bookkeeping is non-trivial,
  scipy's vetted impl wins.
- `map_samples_to_grid(samples, parameters)` — converts unit-cube samples
  into concrete parameter overrides by indexing into the per-dim value
  list.

### 2. StudyConfig extension

Three new optional fields on `StudyConfig`:
- `sampling: str = "grid"` — one of `{grid, lhs, sobol}`
- `n_samples: int | None = None` — required when `sampling != "grid"`
- `seed: int | None = None` — for reproducibility of LHS / Sobol

`to_dict` omits the new fields when `sampling == "grid"` (default), so
v1.x / v2.x study JSON files load unchanged.

`load_study_config` validates: `sampling` must be in the allowed set;
`n_samples` is required for non-grid samplings; `n_samples ≥ 1`. The
existing `max_candidates` cap applies in both modes.

### 3. Lineage module (§5.2)

`structure_optimizer/core/lineage.py`:
- `LineageRecord(run_id, parent_id, study_id, generation)` — frozen
  dataclass. Defaults: `parent_id=None` (root), `study_id=None`,
  `generation=0`.
- `write_lineage(run_dir, record)` → `run_dir/lineage.json`
- `read_lineage(run_dir)` → `LineageRecord | None` (None when absent;
  back-compat for v1.x / v2.x runs that pre-date Wave O)
- `build_lineage_tree(study_dir)` — walks `candidate_*/lineage.json`
  files and produces `{nodes: [...], edges: [...]}` JSON
- `write_lineage_tree(study_dir, tree)` → `study_dir/lineage_tree.json`

### 4. Workflow integration

`workflow.run_config(...)` gains three optional kwargs:
`parent_id=None`, `study_id=None`, `generation=0`. When called, writes
`lineage.json` into the run dir alongside `summary.json` /
`metrics.csv` / `density.npy`. Defaults preserve v1/v2 behavior (root
run with no study).

`study.run_study(...)` passes `study_id=study_dir.name, generation=0`
to every candidate (both serial and parallel paths) and writes
`lineage_tree.json` after candidates complete. For the LHS / Sobol
paths the tree is a forest of root nodes (no `parent_id` set); for
"derive-from-best" workflows users can manually call `run_config` with
`parent_id=<previous_run_dir.name>` to build multi-generation trees.

### Why no auto-refinement loop in v2.4

Refinement workflows ("derive 5 candidates within ±10% of the best
LHS sample") are valuable but require a separate optimization-policy
abstraction (genetic algorithm? Bayesian opt? Latin square refinement?).
Each is a research direction in itself. v2.4 ships the **mechanism**
(parent_id tracking) without prescribing a **policy**. Future waves can
add a `derive_study(prev_study_dir, top_k=3, perturbation=0.1)` helper
once we know which policies users actually want.

## Honest limitations

- **`n_samples` cap by `max_candidates`**: same default 64 as v1.x.
  Bigger studies need explicit override. This is intentional safety —
  a study that explodes to 10,000 candidates by accident is annoying.
- **No design-of-experiments analysis** beyond the existing Pareto rank
  + ranked CSV. ANOVA / sensitivity indices / response-surface fitting
  are out of scope for v3.x.
- **Sobol depends on scipy.stats.qmc** — adds a soft requirement on
  scipy ≥ 1.7 (when scipy is in the optional dep group). We keep the
  graceful fallback: `RuntimeError` with install hint, not a crash on
  import.
- **`map_samples_to_grid` discretizes continuous parameters** to the
  user-provided list. For truly continuous LHS exploration users would
  pass `parameters: {vol: [0.3, 0.31, 0.32, ..., 0.7]}` (41 values) —
  this is fine and works, just visually verbose. A native
  `parameters: {vol: {"min": 0.3, "max": 0.7}}` schema is a candidate
  for later if real users hit the rough edge.

## Files added / changed

- `structure_optimizer/core/lineage.py` (NEW)
- `structure_optimizer/core/sampling.py` (NEW)
- `structure_optimizer/core/study.py` — `StudyConfig` extended; sampling
  branch in `run_study`; lineage tree at end
- `structure_optimizer/core/workflow.py` — `run_config(parent_id,
  study_id, generation)` writes `lineage.json`
- `tests/test_doe_and_lineage.py` (NEW, 24 tests)

## Coverage

- `lineage.py` 100%
- `sampling.py` 88.4% (untested branch is the scipy-missing path —
  exercised manually but skipped in CI when scipy is installed)
- `study.py` 89.1% (study HTML generation paths still untested)

## References

- McKay, M.D., Beckman, R.J., & Conover, W.J. (1979). "A comparison of
  three methods for selecting values of input variables in the analysis
  of output from a computer code." *Technometrics* 21(2), 239–245 —
  original LHS paper.
- Sobol', I.M. (1967). "On the distribution of points in a cube and the
  approximate evaluation of integrals." *USSR Computational Mathematics
  and Mathematical Physics* 7(4), 86–112.
- scipy docs, `scipy.stats.qmc.Sobol` — implementation we wrap.
