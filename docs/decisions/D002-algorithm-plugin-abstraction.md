# D002 — Algorithm plug-in abstraction (Wave G / v1.7)

**Status**: Accepted (v1.7.0, 2026-05-16)

## Context

v1.x had a hardcoded call to `run_simp(config, mesh)` in `core/workflow.run_config`.
Wave G adds a second topology-optimization algorithm (BESO). We need an
abstraction that lets users choose at config / CLI time, without scattering
`if algorithm == "simp" / elif algorithm == "beso"` throughout the codebase.

## Decision

Follow the same pattern already proven in `adapters/solver_base.py`:

- `TopologyAlgorithm` ABC with one method: `run(config, mesh) → OptimizationResult`.
- Two built-in implementations: `SimpAlgorithm`, `BesoAlgorithm`.
- Module-level `_REGISTRY: dict[str, type[TopologyAlgorithm]]`.
- Factory `get_algorithm(name) → TopologyAlgorithm` with case-insensitive
  name dispatch + `None`/empty → default `"simp"`.
- Configuration: `OptimizationConfig.algorithm: str = "simp"` (backward compat).
- CLI override: `structure-optimizer run --algorithm {simp,beso}`.

## Alternatives considered

1. **Strategy injection** (pass algorithm object directly into `run_config`).
   Rejected: complicates config-file-only workflows; users would still need
   a string-to-class lookup.
2. **`if/elif` dispatch in `workflow.py`**. Rejected: brittle to grow; no
   plug-in story for downstream packages adding their own algorithms.
3. **Entry points via setuptools**. Rejected: overkill for v2.x; reconsider
   if external algorithm contributions arrive.

## Consequences

- New algorithms (level-set, MMA, phase-field) plug in by writing one class
  + one `_REGISTRY` line — no other code changes.
- Algorithm changes are reflected in `summary.json` via the `OptimizationResult`
  schema; demo/report/study consume that uniformly.
- BESO and SIMP share 80% of their utilities (density_filter, manufacturing
  projections, objectives.solve_and_aggregate) — abstraction at the entry
  point, not the internals.

## Reopening criteria

- An algorithm needs a fundamentally different `OptimizationResult` schema
  (e.g. level-set returning a φ field instead of densities) → consider a
  result-type variant.
- Performance: if the indirect dispatch shows up in profiles, drop to
  module-level function dispatch.
