# D065 — v9 closure: second-order drivers (constrained optimisers & coupled fields) (Wave JJJ)

**Status**: Accepted
**Wave**: JJJ (v9)
**Supersedes**: none (closes the v9 milestone)
**Superseded by**: none

## Context

Waves CCC–III delivered the seven v9 upgrades, each tracing a v8 (or earlier) ADR
reopening criterion: MMA-driven TL nonlinear TO (D058), eigenfrequency band-gap
objective (D059), ≥3-objective multi-load NSGA-III (D060), Rosenblatt transform
(D061), coupled density+orientation thermal TO (D062), system-reliability-based TO
(D063), slit-free watertight holed prism (D064). Wave JJJ closes the milestone:
real demos, architecture/tutorial docs, v9 fingerprints, CI wiring, and the
`--rubric v9` scorecard at ≥99/100 with no v4–v8 regression and the D033
pytest-green gate.

## Decision

- **`scripts/v9_demos.py`** — seven demos, each running a *real* v9 computation:
  `mma_tl_demo` (MMA/OC ratio 0.946), `band_gap_demo` (gap 2.2e10→4.8e10),
  `three_objective_demo` (seeded HV 1.93e9 vs random 1.51e9), `rosenblatt_demo`
  (β 3.379 == closed form), `system_rbto_demo` (vf 0.413, β_sys 2.058),
  `coupled_orientation_demo` (coupled 2.59e5 vs density-only 8.0e5),
  `slit_free_demo` (annulus watertight, area 560).
- **`scripts/generate_v9_fingerprints.py`** + 5 fixtures (DB 40→45): `mma_nonlinear`,
  `band_gap`, `rosenblatt`, `coupled_thermal`, `slit_free` — all deterministic
  (no RNG-sensitive front shapes), with matching `_rerun` recipes in
  `test_multiphysics_fingerprints.py` (two-tier: tolerant always + strict SHA under
  `REQUIRE_BIT_EXACT_FINGERPRINT=1`) and added to the fixture-set guard.
- **Docs**: architecture §19 (second-order-driver principle + §18.2-resolved table
  + honest §19.2 limits), tutorial §19.1–§19.7 (7 sections), blueprint-v9 all 8
  waves ticked.
- **Rubric/CI**: v9 step added to `.github/workflows/test.yml` (`--rubric v9
  --strict`, gated to the canonical ubuntu/3.12/with-extras cell after v8).

## Verification (the v9 completion gate)

`python scripts/test_agent.py --rubric v9 --strict` reports (`tests/v9_scorecard.json`):

- v9 rubric total ≥ 99/100 (§1 24 · §2 16 · §3 15 · §4 20 · §5 10 · §6 15).
- v8 regression = False (v8 = 100); v7 = v6 = v5 = v4 = 100 — all no-regression.
- **pytest gate green** (D033): full suite 0 failed / 0 errors.
- core coverage ≥ 95%; fingerprint DB 45 (≥45); property tests ≥ 44; mutation
  kill rate ≥ 75%.

## Honest scope notes

- v9 raises the **driver order** (MMA, coupled fields, system reliability, robust
  geometry) but each wave keeps a documented honest boundary: MMA ≈ OC on
  compliance-only (D058); band-gap assumes simple eigenvalues + projected-gradient
  ascent (D059); multi-objective is still gradient-free (D060); Rosenblatt is
  MVN-only (D061); coupling is block-coordinate not simultaneous MMA (D062);
  system modes treated as independent (D063); slit-free is watertight for
  edge-connected regions only, with a staircase boundary (D064).
- The §5 demo rubric checks grep `**/*.py` and self-match `test_agent.py`'s own
  check source; the demos are built genuinely regardless so the artifacts run.
- v9 reuses v8 drivers + helpers via additive APIs and local imports; v4–v8 call
  paths and rubrics are unchanged (no-regression verified).

## Reopening criteria

- Per-wave reopening criteria in D058–D064 (multi-constraint MMA-TL, target-band
  placement, many-objective HV, non-Gaussian Rosenblatt copulas, simultaneous
  (ρ,θ) MMA, correlated system modes, constrained-Delaunay smooth+watertight holes).
- A v10 milestone would target the next reopening tier; no v10 is scoped yet.

## Red lines

All permanent red lines hold across v9: numpy-only mandatory runtime
(scipy/pyamg/meshio optional), 2D/2.5D only, local `pytest -q` (no network),
single-line stderr + `SolverError` status strings, no CAD/GUI/cloud/full-3D/
commercial solvers/LLM, self-deprecation over self-promotion.
