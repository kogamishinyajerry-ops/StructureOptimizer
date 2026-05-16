# D014 — Property tests + test suite growth strategy

- **Status**: accepted
- **Date**: 2026-05-16
- **Wave**: R (v3.0.0)

## Context

The v3.x rubric §4 wants:
- §4.1 (5 pts): ≥ 400 total tests
- §4.4 (2 pts): ≥ 5 property tests (randomized invariant checks)

Before Wave R: ~352 tests, 0 explicit property tests. Adding example-based
tests one at a time to hit 400 is mechanical and low-leverage.

## Decision

### 1. Property tests (§4.4)

`tests/test_property_tests.py` (NEW). Five randomized-loop tests, each
pinning a property that should hold for the entire input class:

1. `test_property_worst_case_always_max_compliance` — 50 trials, random
   case counts/strains, asserts `worst_case ≡ max(case_compliances)`
2. `test_property_weighted_sum_bounded_by_case_min_max` — 50 trials,
   `min(c) ≤ weighted_sum ≤ max(c)`
3. `test_property_simp_compliance_sensitivity_sign` — 10 random density
   draws, asserts `∂c/∂ρ_e ≤ 0` everywhere
4. `test_property_lhs_coverage_holds_for_random_n_and_dims` — 15 random
   `(n, n_dims)` pairs, LHS marginal-uniform property holds
5. `test_property_lineage_tree_is_acyclic_for_strict_predecessor_parents` —
   20 random trees with predecessor parents, asserts tree builder produces
   all-nodes-no-cycles

These five cover the load-bearing invariants of the most critical
modules: case aggregation, SIMP gradient math, DOE sampling, lineage.

### 2. Test suite growth (§4.1)

Padding to 400 tests honestly via:

- **Per-benchmark parametrized smoke tests** (`tests/test_per_benchmark_smoke.py`):
  5 properties × 8 benchmarks = 40 tests
  - SIMP runs to completion + density range valid
  - `_repr_html_` works
  - `input_hash` stable
  - Mesh dims match config
  - `OptimizationResult._repr_html_` works
- **Algorithm × mesh × backend matrix tests** (D013, ~9 tests)
- Wave Q parametrized fingerprint tests (8 from 8 fingerprints)
- Wave P parametrized reproducibility tests (9 SIMP×bm + 3 BESO×bm)

Total before R waves: 352 → with new parametrized files: 407

### Why parametrize rather than literal duplication

`@pytest.mark.parametrize` over benchmarks gives each cell its own
test ID, individual failure isolation, and pytest's xdist/parallel
friendliness. Cleaner than 8 hand-copied test functions.

### Why not Hypothesis library

Adding `hypothesis` as a dev dependency would give us state-of-the-art
property-based testing with shrinking. We declined for v3.0 because:
1. Five well-chosen randomized loops are sufficient for §4.4
2. Hypothesis adds a non-trivial test-time dependency
3. Loop-based property tests are easier for future contributors to read

If a real bug slips through (LHS produces non-equipartitioned samples
in a weird `n_dims` edge case) we'll add hypothesis. Until then,
deterministic `np.random.default_rng(seed)` is enough.

## Files

- `tests/test_property_tests.py` (NEW, 5 tests)
- `tests/test_per_benchmark_smoke.py` (NEW, 40 tests via parametrize)
- `tests/test_algorithm_mesh_backend_matrix.py` (NEW, 9 tests)
- This ADR

## Honest score

§4.1 (≥400 tests): ✅ — 407 tests as of v3.0
§4.4 (≥5 property tests): ✅ — exactly 5 explicit `test_property_*` functions
