# D041 — v6 closure (Wave LL)

**Status**: Accepted
**Wave**: LL (v6)
**Supersedes**: none (closes the v6 milestone opened by the v6 charter)
**Superseded by**: none

## Context

Waves EE–KK (D034–D040) upgraded the seven intentionally-simplified v5
formulations to production-grade, each with a quantitative analytical anchor.
Wave LL is the closure wave: deliver the user-facing demos, documentation, CI
wiring, and reproducibility fixtures the v6 rubric requires, and confirm the
rubric scores ≥99/100 with no v4/v5 regression and a green pytest gate (D033).

## Decision

Closure deliverables (no new core formulation; only demos, docs, fixtures):

- **§5 demos** — `scripts/v6_demos.py`: `convergence_study` (marching-squares vs
  voxel area, O(h²) vs O(h), HTML log-log), `render_bode` (damped FR magnitude +
  phase over a sweep), `render_nsga3_html` (3-objective Pareto projection),
  `smooth_vs_voxel_demo` (writes both STLs). Self-contained inline-SVG HTML in
  the D012 spirit; kept in `scripts/` so they do not enter the core-coverage
  denominator. Artifacts write to `build/v6_demos/` (gitignored).
- **§6.3 architecture** — `docs/architecture.md` §16 "production-grade
  formulations": a table mapping each lifted v5 §15 limitation → v6 upgrade →
  module → ADR → quantitative anchor, plus the production-grade principles and
  honest v6-scope limitations.
- **§4.7 CI** — a v6 test-agent step added to `.github/workflows/test.yml`.
- **§4.5 fingerprints** — 5 new deterministic v6 fingerprints
  (`tl_cantilever__smoke`, `damped_fr_cantilever__smoke`,
  `anisotropic_thermal_heat_sink__smoke`, `form_linear_limit_state`,
  `marching_squares_disk`) bringing the DB to 30. A first-ever generator
  (`scripts/generate_v6_fingerprints.py`) plus matching `_rerun` recipes in
  `tests/test_multiphysics_fingerprints.py` (the v5 set never had a generator).
  Both the tolerant (1e-9) and strict (`REQUIRE_BIT_EXACT_FINGERPRINT=1`) tiers
  pass; the v6 fingerprints carry `rubric_version` so the SIMP validator skips
  them.

## Verification

- `python scripts/test_agent.py --rubric v6` → total ≥99/100, v4 = 100 (no
  regression), v5 = 100 (no regression), pytest gate green (D033, 0 failed / 0
  errors). The committed `tests/v6_scorecard.json` records the run.
- Full suite green; 30 fingerprints; ≥7 v6 ADRs (D034–D041); blueprint-v6 all 8
  waves ticked; tutorial §16.1–§16.7; architecture §16.

## Honest scope notes

- The §5 demos are illustrative; quantitative correctness is asserted by the
  test suite, not by the HTML/STL artifacts.
- The CI v6 step is wired but its first green run happens on the next push (the
  workflow has not been exercised by an actual CI run at authoring time).
- v6 lifts the seven §15 limitations it targeted; the remaining permanent red
  lines (2D/2.5D, numpy-only, no LLM, no commercial solvers) are unchanged by
  design.

## Reopening criteria

- A future milestone (v7) → new charter + blueprint-v7; do not extend v6.

## Red lines

All permanent red lines held: numpy-only runtime, 2D/2.5D, local-runnable,
single-line stderr, no LLM, self-deprecation over self-promotion.
