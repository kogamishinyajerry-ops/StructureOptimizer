# D089 — v12 closure: design-grade & adaptive milestone (Wave HHHH)

**Status**: Accepted
**Wave**: HHHH (v12)
**Supersedes**: none
**Superseded by**: none

## Context

v12 ("design-grade & adaptive") set out to close, one wave at a time, the limits
v11 had *honestly deferred* — each wave traceable to a recorded ADR reopening
criterion, not number-chasing. Waves AAAA–GGGG delivered the seven capability
upgrades (D082–D088). Wave HHHH is the closure: demos, fingerprints, property
tests, architecture doc, CI wiring, and the authoritative rubric gate.

## Decision

The v12 milestone is closed when `python scripts/test_agent.py --rubric v12
--strict` reports total ≥ 99/100, every prior rubric (v4–v11) at 100 (no
regression), and the D033 pytest-green gate holds. Wave HHHH delivers:

- **`scripts/v12_demos.py`** — nine real, deterministic demos covering all seven
  waves (`design_grade_demo`, `inloop_band_demo`, `augmented_r2_demo`,
  `spacing_demo`, `nested_copula_demo`, `lattice_genz_demo`, `laminate_demo`,
  `periodic_fibre_demo`, `cdt_refine_demo`).
- **`scripts/generate_v12_fingerprints.py`** + **5 new fingerprints** (55 → 60):
  design-grade buckling, nested Clayton CDF, Korobov-lattice Genz, laminate [A,B,D],
  flip-recovery CDT — each with a re-run recipe in
  `tests/test_multiphysics_fingerprints.py` and a guard-set entry.
- **`tests/test_property_v12.py`** — 3 property tests (51 → 54): nested-Clayton
  degeneration, period-aware gradient vs FD, Korobov value bounded + accurate.
- **`docs/architecture.md` §22** — v12 design principles + honest-limits roll-up.
- **`.github/workflows/test.yml`** — a `--rubric v12 --strict` CI step after v11.
- **`docs/tutorial.md` §22.8** — v12 closure summary; **`docs/quality-rubric-v12.md`**
  and `CHECKS_V12` already scored the rubric.

## Verification (quantitative anchors)

- **rubric**: `--rubric v12 --strict` → **100/100** (see `tests/v12_scorecard.json`).
- **no regression**: v4/v5/v6/v7/v8/v9/v10/v11 each re-scored 100/100 in-process.
- **pytest gate**: full suite green (D033), 0 failed / 0 errors.
- **counts**: ≥ 1095 tests collected, ≥ 53 property tests (54), ≥ 60 fingerprints
  (60), core coverage ≥ 95%.
- **§5 demos / §6 docs**: all four demo checks and all five doc checks PASS.

## Honest scope notes

- **v12 closes v11's deferrals; it does not claim production-completeness.** Each of
  D082–D088 ships with its own "Honest scope notes" + "Reopening criteria" — the
  buckling driver is ascent (not a constraint) with no mode-tracking; the in-loop
  band shows constraint-fidelity not a divergent design on the aligned smoke
  problem; spacing is a gameable distribution-only metric; the nested copula has no
  Rosenblatt transform/sampler; Korobov reports a randomisation SE, not a
  deterministic QMC bound; the laminate is a standalone calculator; CDT refinement
  is Lawson-only (no min-angle guarantee). The milestone advances capability **inside**
  the permanent red lines, recording every remaining limit rather than papering
  over it.
- **The rubric is a self-authored gate, not an external benchmark.** A 100/100 means
  the implementation matches the contracts *I wrote*; it is a regression harness and
  honesty ledger, not third-party validation. The fingerprints are
  same-environment reproducibility checks (tolerant cross-platform), not physical
  validation.
- **5 fingerprints cover 5 of 7 waves** (the fast, non-MMA-loop drivers); the in-loop
  band and augmented-R2 waves are covered by their unit tests, not a fingerprint, to
  keep the CI fingerprint pass cheap.

## Reopening criteria

- The union of D082–D088 reopening criteria (mode-tracking buckling, peak-binding
  in-loop formulation, range-adaptive ρ + extent metric, nested Rosenblatt/sampler,
  CBC lattice + deterministic bound, laminate stacking-sequence optimisation,
  Ruppert refinement) — the natural v13 backlog.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
