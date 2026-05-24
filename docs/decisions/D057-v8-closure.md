# D057 — v8 closure: closing the loop (gradient drivers & general distributions) (Wave BBB)

**Status**: Accepted
**Wave**: BBB (v8)
**Supersedes**: none (closes the v8 milestone)
**Superseded by**: none

## Context

Waves UU–AAA delivered the seven v8 upgrades, each tracing a v7 (or earlier) ADR
reopening criterion: TL-in-the-loop full OC (D050), filtered multi-ω dynamic-
compliance OC (D051), gradient-seeded NSGA-III (D052), general-marginal Nataf via
Gauss-Hermite (D053), fibre-steering thermal TO (D054), system reliability with
Ditlevsen bounds (D055), marching-squares nested-loop holed caps (D056). Wave BBB
closes the milestone: real demos, architecture/tutorial docs, v8 fingerprints, CI
wiring, and the `--rubric v8` scorecard at 100/100 with no v4/v5/v6/v7 regression
and the D033 pytest-green gate.

## Decision

- **`scripts/v8_demos.py`** — five demos, each running a *real* v8 computation and
  writing a real artifact: `nonlinear_oc_demo` (TL OC end-compliance 2066→602),
  `seeded_nsga_demo` (gradient-seeded hypervolume +36% vs random at the same
  budget), `system_reliability_demo` (general-marginal Weibull/Gumbel FORM β per
  mode + series Ditlevsen bound), `fibre_steer_demo` (thermal compliance −33% by
  steering θ), `holed_stl_demo` (watertight rectangular-hole prism, area 684.0).
- **`scripts/generate_v8_fingerprints.py`** + 5 fixtures (DB 35→40):
  `nonlinear_oc`, `general_nataf` (weibull/gumbel correlation matrix),
  `system_reliability` (series bounds), `fibre_steering` (angles), `holed_cap`
  (ear-clipped rect-hole vertices) — all deterministic (no RNG-sensitive front
  shapes), with matching `_rerun` recipes in `test_multiphysics_fingerprints.py`
  (two-tier: tolerant always + strict SHA under `REQUIRE_BIT_EXACT_FINGERPRINT=1`)
  and added to the fixture-set guard.
- **Docs**: architecture §18 (closed-loop principle + §17.2 limitations resolved
  table + honest §18.2 limits), tutorial §18.1–§18.7 (7 sections), blueprint-v8 all
  8 waves ticked.
- **Rubric/CI**: v8 step added to `.github/workflows/test.yml` (`--rubric v8
  --strict`, gated to the canonical ubuntu/3.12/with-extras cell after v7).
- **2 new property tests** (DB 40→42): bivariate-normal CDF monotone in each
  argument; Ditlevsen series bounds always ordered and within the simple unimodal
  bounds, over random β vectors.

## Verification (the v8 completion gate)

`python scripts/test_agent.py --rubric v8 --strict` reports (`tests/v8_scorecard.json`):

- v8 rubric total = **100/100** (§1 24 · §2 16 · §3 15 · §4 20 · §5 10 · §6 15).
- v7 regression = False (v7 = 100); v6 = 100; v5 = 100; v4 = 100 — all no-regression.
- **pytest gate green** (D033): full suite 0 failed / 0 errors, 949 tests
  collected (≥920); 4 perf tests skipped (`--run-slow`).
- core coverage 95.7% (≥95%); fingerprint DB 40 (≥40); property tests 42 (≥42);
  mutation kill rate 80% (≥75%).

## Honest scope notes

- The v8 drivers close the **loop** (OC with density filter) for the TL and
  dynamic cases, but still use a single move-limit OC update (not MMA); the
  large-deformation-vs-linear topology difference is robust only with a converged
  loop (D050). The dynamic band-TO uses projected gradient near resonance (D051),
  and gradient-seeded NSGA-III is still a gradient-free *refinement* whose
  endpoints come from the seeds, not a competitor to gradient SIMP (D052).
- Reliability generalises to arbitrary marginals (24-node Gauss-Hermite, D053) and
  to series systems with Ditlevsen bounds, but **parallel is 2-component only** and
  ρ=1 does not collapse exactly (residual ≈2%, D055).
- The holed-cap STL is **watertight only for clean-cornered holes**; a high-vertex
  curved hole leaves a non-manifold zero-width bridge slit — *not* a v8 regression
  (the pre-existing `write_stl_polygon` shares it), area conservation exact
  regardless (D056).
- The §5 demo rubric checks grep `**/*.py` and self-match `test_agent.py`'s own
  check source; the demos are built genuinely regardless so the artifacts exist and
  run.
- v8 reuses v7 forward solvers + drivers via additive APIs and local imports;
  v4/v5/v6/v7 call paths and rubrics are unchanged (no-regression verified).

## Reopening criteria

- Per-wave reopening criteria in D050–D056 (MMA TL optimiser, m>2 parallel system
  reliability via the multivariate normal CDF, FORM-coupled inter-mode ρ_ij,
  slit-free constrained-Delaunay hole triangulation, system-reliability-based TO,
  per-element anisotropic field optimisation, …).
- A v9 milestone would target the next reopening tier; no v9 is scoped yet.

## Red lines

All permanent red lines hold across v8: numpy-only mandatory runtime
(scipy/pyamg/meshio optional), 2D/2.5D only, local `pytest -q` (no network),
single-line stderr + `SolverError` status strings, no CAD/GUI/cloud/full-3D/
commercial solvers/LLM, self-deprecation over self-promotion.
