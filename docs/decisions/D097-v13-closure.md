# D097 — v13 closure: robust drivers & validated geometry (Wave HHHHH, v13)

**Status**: Accepted
**Wave**: HHHHH (v13)
**Supersedes**: none
**Superseded by**: none

## Context

v13 (**robust drivers & validated geometry**) ran seven capability waves, each tracing
a recorded reopening criterion from a v12 ADR (D082-D088) — not number-chasing:

| Wave | ADR | reopening traced | delivered |
|------|-----|------------------|-----------|
| AAAAA | D090 | D082 "buckling-*constrained* MMA (λ_crit ≥ λ_safety)" | buckling-constrained MMA (λ binds 14.3→21.2 at +6.7% compliance) |
| BBBBB | D091 | D083 "bandwidth-adaptive window (half-power)" | half-power bandwidth-adaptive window (peak-binding-different-design honestly deferred) |
| CCCCC | D092 | D084 "extent/spread indicator + range-adaptive ρ" | extent (Δ) indicator + scale-invariant range-adaptive R2 |
| DDDDD | D093 | D085 "non-Clayton d-dim copula" | d-dim exchangeable Gumbel (ψ^{(k)}=ψ·g_k closed-form conditional CDF) |
| EEEEE | D094 | D086 "Genz variable reordering" | Genz–Bretz priority ordering (≈9× error reduction at fixed N) |
| FFFFF | D095 | D087 "laminate stacking-sequence optimisation" | stacking-sequence optimisation (rearrangement global max + symmetric B=0 + min-coupling) |
| GGGGG | D096 | D088 "Ruppert refinement (Steiner)" | Ruppert Steiner insertion (14°→≥20°, watertight) |

This ADR records the closure: demos, fingerprints, property tests, docs, CI, and the
authoritative rubric scorecard.

## Decision

- **`scripts/v13_demos.py`** — seven real, deterministic HTML demos
  (`buckling_constrained_demo`, `bandwidth_adaptive_demo`, `extent_demo` /
  `range_adaptive_demo`, `gumbel_d_demo`, `genz_reorder_demo`, `stacking_demo`,
  `ruppert_demo`).
- **Fingerprints 60 → 65**: `extent_range_adaptive_front`,
  `gumbel_d_copula_conditional`, `genz_reordered_equicorr`,
  `stacking_sequence_max_bending`, `ruppert_rect_4x1` — each with a tolerant tier and a
  bit-exact SHA tier (verified under `REQUIRE_BIT_EXACT_FINGERPRINT=1`), wired into the
  `_rerun` dispatcher and the present-set guard.
- **Property tests 54 → 57**: `tests/test_property_v13.py` (d-Gumbel d=2 degeneration;
  range-adaptive scale-invariance + extent linearity; stacking rearrangement
  global-optimum domination).
- **Docs**: `docs/architecture.md` §23 (robust drivers & validated geometry +
  honest-limits); `docs/tutorial.md` §23.1–23.7; `docs/blueprint-v13.md` all eight waves
  ticked; `docs/quality-rubric-v13.md`.
- **CI**: `.github/workflows/test.yml` v13 strict step (after v12), enforcing the D033
  pytest-green gate and the v4–v12 regression checks.
- **Authoritative scorecard**: `python scripts/test_agent.py --rubric v13 --strict`
  writes `tests/v13_scorecard.json`.

## Verification (authoritative rubric)

Authoritative `python scripts/test_agent.py --rubric v13 --strict`:

- **v13 rubric total = 100/100** (six sections; §1 robust drivers 24, §2 robust
  reliability 16, §3 validated geometry 15, §4 quality gates 20, §5 demos 10, §6 docs
  15).
- **v4–v12 regression = False** (each prior milestone re-scored at 100/100 with full
  coverage).
- **D033 pytest gate green** — full suite passes, 0 failed / 0 errors.
- §4 thresholds met: test count ≥ 1140 (actual ≈ 1174); property tests ≥ 56 (actual
  57); fingerprint DB ≥ 65 (actual 65); core coverage ≥ 95%.

(The scorecard JSON `tests/v13_scorecard.json` records the exact per-section figures.)

## Honest scope notes

- **v13 is a *robustness / validity* milestone, not a new-physics one.** Every wave
  hardened or constrained an existing v12 capability (buckling → constrained; fixed band
  → adaptive; fixed ρ → scale-invariant; Clayton → Gumbel; unordered → reordered Genz;
  evaluate-laminate → optimise-stacking; flip-refine → Steiner-refine). No new physical
  model was added.
- **One reopening was honestly deferred, not faked (D091).** The D083 "peak-binding
  produces a different design" claim could not be demonstrated on the smoke mesh (the
  objective and the peak constraint are aligned there); rather than fabricate a binding
  conflict, BBBBB delivered the demonstrable bandwidth-adaptive window and recorded the
  deferral with probe evidence.
- **Several v13 primitives are not yet wired into the production drivers.** d-Gumbel
  (D093) and Genz reordering (D094) are not yet inside `system_reliability_series`;
  stacking (D095) optimises order not angle values; Ruppert (D096) is not yet inside
  `write_stl_cdt_multi_hole`. These are explicit reopening items, carried forward.
- **The rubric's §4.2 coverage / §4.4 mutation gates are coarse.** Coverage ≥ 95% and a
  recorded mutation kill-rate are necessary, not sufficient — they do not prove the
  *analytical anchors* are tight; that is the job of the per-wave quantitative tests.

## Reopening criteria

- **Wire d-Gumbel + Genz reordering into `system_reliability_series`** so the production
  reliability path uses upper-tail dependence and the variance-reduced estimator.
- **Wire Ruppert into `write_stl_cdt_multi_hole`** so exported caps are quality-refined.
- **Balanced laminate constraint + angle-value selection** (beyond ordering) for D095.
- **Small-input-angle handling for Ruppert** (concentric-shell splitting) so acute
  corners refine without the `max_steiner` backstop.
- A **v14 milestone** would consolidate these integrations rather than add new isolated
  primitives.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
