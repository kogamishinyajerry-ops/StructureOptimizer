# D105 — v14 closure: integration & production-wiring milestone (Wave HHHHHH, v14)

**Status**: Accepted
**Wave**: HHHHHH (v14, closure)
**Supersedes**: none (closes the v14 milestone D098–D104)
**Superseded by**: none

## Context

v14 (integration & production-wiring) ran seven capability waves AAAAAA–GGGGGG
(D098–D104), each wiring a v13 isolated primitive into a production function — under the
v14 **integration铁律**: every wave that modifies a production function carries a
backward-compatibility *byte-exact* anchor proving the opt-in default reproduces prior
behaviour. This wave is the closure: demos, docs, fingerprint/property quota, CI
promotion, and the authoritative scorecard.

## Decision

- **`scripts/v14_demos.py`** — seven deterministic HTML demos (`series_copula_demo`,
  `series_reorder_demo`, `ruppert_export_demo`, `concentric_shell_demo`,
  `balanced_laminate_demo`, `angle_select_demo`, `peak_binding_demo`), one per wave,
  running the actual production-wired drivers (rubric §5.1–5.4).
- **5 new fingerprints** (65 → **70**, rubric §4.5): `series_copula_gumbel`,
  `series_exact_reordered_equicorr`, `balanced_laminate_sym`,
  `angle_selection_max_bending`, `concentric_shell_spike` — each with a `_rerun` recipe
  in `test_multiphysics_fingerprints.py`, tolerant + bit-exact tiers, added to the
  present-set guard.
- **3 new property tests** (57 → **60**, rubric §4.3) in `tests/test_property_v14.py`:
  balanced-laminate zeros A₁₆/A₂₆ for arbitrary angle sets; angle-selection dominates
  every random multiset; the Gumbel series copula at θ=1 reduces to the independent
  series P_f.
- **`docs/architecture.md` §24** — the v14 integration narrative + the integration铁律 +
  honest-limits list (rubric §6.3).
- **CI** (`.github/workflows/test.yml`): the v14 step is promoted from
  `continue-on-error` (non-strict) to **`--rubric v14 --strict`** (rubric §4.7).
- **`tests/v14_scorecard.json`** — the authoritative `--rubric v14 --strict` scorecard.

## Verification (quantitative anchors)

Authoritative `python scripts/test_agent.py --rubric v14 --strict`:

- **v14 rubric total = 100 / 100** (§1.1/1.2/2.1/2.2/3.1/3.2/3.3 capability waves +
  §4 counts/coverage/mutation/gate/CI + §5 demos + §6 docs/ADRs).
- **v4–v13 regression = False** (each prior milestone re-scored 100/100 in-process).
- **pytest gate green** (D033): 0 failed / 0 errors.
- Counts at closure: ≥1185 tests collected, core coverage ≥95 %, 60 property tests, 70
  fingerprints, mutation kill rate 80 %, 8 v14 ADRs (D098–D105).

(Full numbers recorded in `tests/v14_scorecard.json`.)

## Honest scope notes

- **v14 wired primitives into production; it did not add new physics.** The milestone's
  value is integration + robustness, not new capability classes — by design.
- **Two honest carrydowns remain open** and are documented in their ADRs, not papered
  over: D101 balanced-laminate is construction+verification (not yet an
  `optimize_stacking_sequence` constraint); D104 peak-binding demonstrated the *coupling*
  + *design change* but **not** a strictly KKT-binding constraint with J sacrifice.
- **D100/D103 left their refine path un-wired into the STL writer's `refine=True`** (the
  writer still calls the un-shelled Ruppert byte-exact); concentric shells are reachable
  via `constrained_delaunay_ruppert(concentric_shells=True)` but not through
  `write_stl_cdt_multi_hole` yet.
- **The `--rubric v14 --strict` run is slow** (~6 h+ — it re-runs the full v4–v13
  coverage regression chain plus the v14 test set). The per-wave checks were verified
  incrementally; the authoritative run is the final gate.

## Reopening criteria (v15 candidates)

- Wire **balanced (D101)** into `optimize_stacking_sequence`; wire **concentric shells
  (D103)** into `write_stl_cdt_multi_hole(refine=True)`.
- A **strictly KKT-binding peak-binding** regime (D104) with a positive multiplier and a
  measurable J sacrifice.
- **Constrained discrete angle selection** (D102 + balanced/D₁₆ constraints) so the
  max_bending optimum is non-degenerate.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
