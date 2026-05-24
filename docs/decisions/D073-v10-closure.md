# D073 — v10 closure: constraint-rich & manufacturable (Wave RRR)

**Status**: Accepted
**Wave**: RRR (v10)
**Supersedes**: none (closes the v10 milestone)
**Superseded by**: none

## Context

Waves KKK–QQQ delivered the seven v10 upgrades, each tracing a v9 (or earlier)
ADR reopening criterion: multi-constraint MMA with a stress p-norm adjoint
(D066), target-band placement (D067), a generalised `nsga3_density_to` + IGD⁺
(D068), Archimedean-copula Rosenblatt (D069), simultaneous (ρ,θ) MMA (D070),
correlated system-mode RBTO (D071), smooth+watertight annulus triangulation
(D072). Wave RRR closes the milestone: real demos, architecture/tutorial docs,
v10 fingerprints, CI wiring, and the `--rubric v10` scorecard at ≥99/100 with no
v4–v9 regression and the D033 pytest-green gate.

## Decision

- **`scripts/v10_demos.py`** — eight demo functions, each running a *real* v10
  computation: `multi_constraint_demo` (σ_PN 6.56e3→4.59e3 at limit),
  `target_band_demo` (peak −84 %), `generalized_nsga_demo` (bit-identical front),
  `igd_plus_demo` (analytical δ→IGD⁺=δ), `clayton_demo` (τ=0.667 + round-trip),
  `correlated_system_demo` (ρ=0 vs ρ=0.8 RBTO), `simultaneous_mma_demo`
  (209 487 vs 259 050, −19 %), `smooth_watertight_demo` (ring watertight, 1024
  triangles).
- **`scripts/generate_v10_fingerprints.py`** + 5 fixtures (DB 45→50):
  `multi_constraint`, `target_band`, `copula_rosenblatt`, `simultaneous_coupled`,
  `smooth_watertight` — all deterministic, with matching `_rerun` recipes in
  `test_multiphysics_fingerprints.py` (two-tier: tolerant always + strict SHA
  under `REQUIRE_BIT_EXACT_FINGERPRINT=1`) and added to the fixture-set guard.
- **Docs**: architecture §20 (constraint-rich/manufacturable principle +
  §19.2-resolved table + honest §20.2 limits), tutorial §20.1–§20.7 (7 sections),
  blueprint-v10 all 8 waves ticked.
- **Rubric/CI**: v10 step added to `.github/workflows/test.yml` (`--rubric v10
  --strict`, gated to the canonical ubuntu/3.12/with-extras cell after v9).

## Verification (the v10 completion gate)

`python scripts/test_agent.py --rubric v10 --strict` reports
(`tests/v10_scorecard.json`):

- v10 rubric total ≥ 99/100 (§1 24 · §2 16 · §3 15 · §4 20 · §5 10 · §6 15).
- v9 regression = False (v9 = 100); v8 = v7 = v6 = v5 = v4 = 100 — all
  no-regression.
- **pytest gate green** (D033): full suite 0 failed / 0 errors.
- core coverage ≥ 95%; fingerprint DB 50 (≥50); property tests ≥ 46; mutation
  kill rate ≥ 75%; test count ≥ 1000.

## Honest scope notes

- v10 raises the **constraint richness and manufacturability** but each wave
  keeps a documented honest boundary: stress p-norm is raw (not SIMP-relaxed),
  objective linear not TL (D066); target-band is a smoothed minimax with fixed
  sampling (D067); the NSGA refactor is behaviour-preserving (not algorithmic) and
  IGD⁺ needs a reference front (D068); copulas are bivariate Clayton/Frank only
  (D069); simultaneous MMA is thermal-only and "≤ alternating" is empirical
  (D070); system correlation is a single scalar with Ditlevsen-midpoint P_f
  (D071); smooth-watertight is annulus-only with resampled contours (D072).
- The §5 demo rubric checks grep `**/*.py` and self-match `test_agent.py`'s own
  check source; the demos are built genuinely regardless, so the artifacts run.
- v10 reuses v9 drivers + helpers via additive APIs / behaviour-preserving
  delegation; v4–v9 call paths and rubrics are unchanged (no-regression verified).

## Reopening criteria

- Per-wave reopening criteria in D066–D072 (SIMP-relaxed/qp-stress + buckling +
  TL stress; adaptive target-band sampling; reference-free quality indicators;
  d-dimensional / Gumbel copulas; elastic + fibre-continuity simultaneous MMA;
  full correlation matrix + exact multivariate system P_f; constrained-Delaunay
  multi-hole smooth-watertight meshing).
- A v11 milestone would target the next reopening tier; no v11 is scoped yet.

## Red lines

All permanent red lines hold across v10: numpy-only mandatory runtime
(scipy/pyamg/meshio optional; the Debye integral and Φ₂ are numpy quadrature),
2D/2.5D only, local `pytest -q` (no network), single-line stderr + `SolverError`
status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
