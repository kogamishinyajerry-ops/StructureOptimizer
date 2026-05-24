# D068 — generalised nsga3_density_to + IGD⁺ indicator (Wave MMM, v10)

**Status**: Accepted
**Wave**: MMM (v10)
**Supersedes**: none (refactors D052/D060 drivers; behaviour-preserving)
**Superseded by**: none

## Context

After D060 the codebase had **two near-identical NSGA-III loops** over density
fields: `multi_objective_to` (compliance + volume → 2 objectives) and
`multi_load_case_to` (per-load-case compliances + volume → ≥3 objectives). They
differed only in the objective evaluator, the reference-point construction, the
objective count, and which exact hypervolume routine they called. D060's
recorded reopening criterion named exactly this: **one generalised
`nsga3_density_to`** plus a **many-objective IGD⁺** quality indicator.

## Decision

- **`multi_objective_to.nsga3_density_to(config, mesh, load_cases, …)`** — the
  single generalised driver. Minimises `(C_1, …, C_L, volume)` for
  `L = len(load_cases)` load cases (`n_obj = L+1`). The per-generation
  cumulative-archive hypervolume dispatches to `hypervolume_2d` when
  `n_obj == 2` and `hypervolume_nd` otherwise, so the two original code paths are
  reproduced exactly. All RNG consumption (uniform init → per-generation
  offspring → niching) is unchanged.

- **Refactor (behaviour-preserving)**: `multi_objective_to` now delegates with
  `load_cases=[list(config.loads)]`; `multi_load_case_to` resolves its default
  load cases (original + fx/fy-swapped) then delegates. Both public signatures
  and docstrings are unchanged. The three duplicate ~45-line loops collapse to
  one.

- **`multi_objective_to.igd_plus(front, reference_front)`** — Inverted
  Generational Distance plus for minimisation:
  `d⁺(z,a) = sqrt(Σ_i max(a_i − z_i, 0)²)`, `IGD⁺ = mean_z min_a d⁺(z,a)`.
  Weakly Pareto-compliant (a front dominating the reference scores 0), unlike
  plain IGD.

- **`tests/test_generalised_nsga.py`** — six quantitative anchors (below).

## Verification (quantitative anchors)

`tests/test_generalised_nsga.py` (all pass; adjacent regression on
test_multi_load_case_to / test_multi_objective_to / test_nsga3 / test_pareto_nsga
/ test_pareto / test_seeded_nsga):

1. **2-obj delegation bit-identical**: `multi_objective_to` == direct
   `nsga3_density_to(load_cases=[config.loads])` — front objectives, densities,
   and hypervolume history equal element-for-element (`np.array_equal`). Also
   verified against a captured pre-refactor golden baseline (hv[-1] 118455.6190).
2. **3-obj delegation bit-identical**: `multi_load_case_to` == direct
   `nsga3_density_to(default load cases)` — likewise exact (hv[-1] 1.5067600610e9).
3. **generality beyond 2/3-obj**: 3 load cases → 4 objectives runs and returns a
   4-component reference + front.
4. **IGD⁺ closed form**: hand-computed 3-point example = 1/3 exactly;
   `IGD⁺(Z,Z)=0`; a weakly dominating front = 0.
5. **IGD⁺ on analytical front**: a front pushed radially outward by δ from the
   unit quarter-circle Pareto front has `IGD⁺ = δ` to < 1e-3, monotone in δ.
6. **input guards**: empty front / dimension mismatch raise `SolverError`.

## Honest scope notes

- The refactor is a **behaviour-preserving DRY collapse**, proven by bit-identity
  against captured baselines — not an algorithmic improvement. NSGA-III itself is
  unchanged (still gradient-free, still the D052/D060 niching + Das-Dennis
  directions).
- `igd_plus` requires the caller to supply a **reference Pareto front**. For real
  TO problems no analytical front exists, so IGD⁺ is validated here against
  *synthetic analytical* fronts (quarter-circle); using it on a TO run requires a
  surrogate reference (e.g. the best-known merged archive), which is a metric
  *relative* to that surrogate, not absolute convergence.
- The `n_obj == 2` → `hypervolume_2d` dispatch is retained purely for
  bit-identity with the old `multi_objective_to`; `hypervolume_nd` would give the
  same area but not necessarily the same floating-point bits.
- `multi_load_case_to` called with an explicit single load case (`L=1`) now also
  routes through the `n_obj==2` path → `hypervolume_2d`; the default (`L=2`,
  `n_obj=3`) path is unaffected.

## Reopening criteria

- **Reference-free quality indicators** (hypervolume-only, or R2) so convergence
  can be tracked on TO problems without an analytical front.
- **IGD⁺-driven termination / adaptive reference directions** rather than fixed
  Das-Dennis points.
- **Gradient-assisted many-objective search** (the front is still found by a
  gradient-free GA; combining with per-objective adjoints is unaddressed).

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
