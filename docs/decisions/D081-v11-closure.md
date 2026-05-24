# D081 — v11 closure: exact & robust (Wave ZZZ, v11)

**Status**: Accepted
**Wave**: ZZZ (v11)
**Supersedes**: none (closes v11)
**Superseded by**: none

## Context

v11 ("exact & robust") set out to lift the v10 drivers from their honestly-recorded
approximations — unhandled stress singularity, fixed-grid band sampling,
reference-front-dependent indicators, bivariate-only copulas, Ditlevsen-bound
system reliability, thermal-only simultaneous (ρ,θ), and annulus-only watertight
holes — to exact / robust / general forms. Seven driver waves (SSS–YYY, D074–D080)
delivered the capabilities; this closure wave (ZZZ) wires the test-infrastructure,
demo, fingerprint and documentation rubric items and runs the gate.

## Decision

Closure deliverables (rubric §4–§6):

- **§4.5 fingerprints (50 → 55)**: `scripts/generate_v11_fingerprints.py` writes 5
  deterministic v11 fingerprints (qp-relaxed stress, adaptive band, reference-free
  R2+HV, d-dim Clayton Rosenblatt, Genz series P_f), with matching `_rerun`
  recipes and guard stems in `tests/test_multiphysics_fingerprints.py`.
- **§4.3 property tests (47 → 50)**: `tests/test_property_v11.py` adds three
  randomised invariants (R2 monotone under front contraction; d-dim Clayton
  round-trip; qp-relaxation never amplifies stress).
- **§4.7 CI**: `.github/workflows/test.yml` gains a `--rubric v11 --strict` step.
- **§5 demos**: `scripts/v11_demos.py` runs real computations for all seven waves
  (`qp_stress_demo` / `adaptive_band_demo` / `r2_demo` / `reference_free_demo` /
  `gumbel_demo` / `genz_demo` / `elastic_mma_demo` / `cdt_demo`).
- **§6 docs**: `docs/blueprint-v11.md` 8 ticks, `docs/tutorial.md` §21.1–§21.7,
  `docs/architecture.md` §21 (+ §21.2 honest-limits), ADRs D074–D081.

## Verification (quantitative anchors)

`python scripts/test_agent.py --rubric v11 --strict` reports **v11 = 100/100**,
**v4–v10 no regression** (each 100), **pytest gate green** (D033, 1071 passed / 0
failed / 0 errors / 4 skipped), permanent red lines held. Suite: **1075 tests**
collected; **core coverage 95.6 %** (≥ 95; new `orthotropic_simp.py` at 96.3 %);
**55 fingerprints**; **50 property tests**; mutation kill rate 80 %. See
`tests/v11_scorecard.json` (total_earned 100 / total_max 100).

Per-wave anchors (each validated in its own ADR + test):

| Wave | ADR | Headline anchor |
|---|---|---|
| SSS | D074 | qp-relaxed stress sensitivity vs central-FD ≤ 1e-4; relaxation kills singularity (σ̃=ρ^q·σ); **buckling-driving deferred** (probe λ 20.1→8.1) |
| TTT | D075 | adaptive-25 recovers dense-400 peak to 0.015 % vs uniform-7 −41 %; peak-constraint binds |
| UUU | D076 | R2 closed form 5/6; R2/refHV/IGD⁺ rank nested fronts identically |
| VVV | D077 | Gumbel conditional vs ∂C/∂u₁ ≤ 1e-6; d-dim Clayton conditional = mixed-partial ratio ≤ 1e-5 |
| WWW | D078 | Genz→Φ₂ ≤ 1e-3, Genz(I) exact; exact series P_f inside Ditlevsen bounds |
| XXX | D079 | iso ke reproduces closed form ≤ 1e-9; dC/dρ, dC/dθ vs FD ≤ 1e-4; fibre-continuity binds |
| YYY | D080 | 2- and 3-hole prisms watertight; area ≈ outer − Σ holes ≤ 1 % |

## Honest scope notes

- **v11 raised the floor, it did not make everything exact.** Genz is a converging
  MC estimate (not closed form); R2 ranking-agreement is empirical on nested
  fronts (not a theorem); the d-dim copula is exchangeable-Clayton only; the CDT
  has no flip-based constraint recovery (it fails loudly instead); the fibre-
  continuity metric is not period-aware. Each wave's ADR carries the specifics.
- **Buckling-constrained driving (D074) is the one promised-then-deferred item.**
  The blueprint SSS row originally paired stress relaxation with a buckling
  constraint; the existing `buckling_sensitivity` is analysis-grade (ignores
  ∂u/∂ρ, no void-mode relaxation) and a probe showed it *lowers* λ_crit under
  ascent (20.1 → 8.1). Rather than ship a non-working driver, SSS was re-scoped to
  qp-stress only and buckling-driving moved to a D074 reopening criterion with the
  probe evidence as its entry condition. This is the wave that most exercised the
  "自我贬低优先于自我吹嘘" red line.
- **The §5 demo rubric self-matches `test_agent.py`'s own check source** (greps
  `**/*.py`), as noted since D066; `scripts/v11_demos.py` nonetheless contains
  real, runnable demos so the credit is earned, not gamed.
- **Coverage includes the new `orthotropic_simp.py`** (the only wholly new module);
  the gate run confirms core coverage stayed ≥ 95 %.

## Reopening criteria

The aggregate of D074–D080 reopening criteria defines a potential v12 ("design-
grade & adaptive"): design-grade buckling sensitivity (∂u/∂ρ + void-mode
relaxation) to unlock buckling-driven TO; in-loop adaptive band re-gridding;
augmented-Tchebycheff R2 + diversity indicators; nested/hierarchical &
non-Clayton d-dim copulas; randomised-lattice (Korobov) Genz with error bounds;
period-aware fibre continuity + laminates; flip-based CDT constraint recovery +
quality refinement.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
