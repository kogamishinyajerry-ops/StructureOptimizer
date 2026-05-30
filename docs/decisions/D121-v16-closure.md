# D121 — v16 closure: deep-embedding & exact-generalization milestone (Wave HHHHHHHH, v16)

**Status**: Accepted
**Wave**: HHHHHHHH (v16, closure)
**Supersedes**: none (closes the v16 milestone opened after v15/D113)
**Superseded by**: none

## Context

v16 (deep embedding & exact generalization) ran seven capability waves D114–D120, each
taking a v15 standalone primitive **one layer deeper** into a production estimator/optimiser,
or upgrading a **proxy to an exact quantity / a restricted assumption to a general one**:

- D114 anti-symmetric ordering embedded in `optimize_stacking_sequence`
- D115 general non-normal marginals for mixture-copula series reliability
- D116 CBC deterministic lattice wired into the Genz MVN-CDF estimator
- D117 exact envelope-theorem KKT shadow-price multiplier (proxy → exact)
- D118 α≥2 higher-smoothness Korobov worst-case error
- D119 copula parallel / k-out-of-n system reliability
- D120 fast-CBC (Nuyens–Cools FFT)

This closure wave wires the rubric to score-able state, builds the demos for real, raises the
fingerprint/property gates, and runs the authoritative `--rubric v16 --strict`.

## Decision

Close v16 by delivering the closure artifacts and gating on the authoritative strict run:

- **`scripts/v16_demos.py`** — 7 real, deterministic demos (`antisym_embed_demo`,
  `general_marginal_demo`, `cbc_lattice_demo`, `exact_multiplier_demo`, `alpha_korobov_demo`,
  `parallel_system_demo`, `fast_cbc_demo`), each running the actual production function and
  writing an HTML summary. Covers all four §5 rubric demo tokens.
- **Fingerprints 75 → 80** — 5 new bit-exact recipes + present-set stems
  (`copula_marginals_weibull_gumbel`, `genz_cbc_bivariate`, `alpha_korobov_smoothness`,
  `parallel_copula_gumbel`, `fast_cbc_korobov_5d`); both tolerant and
  `REQUIRE_BIT_EXACT_FINGERPRINT=1` tiers green.
- **Property tests 63 → 65** — `tests/test_property_v16.py` (fast-CBC ≤ textbook Korobov for
  random weights/primes; k-out-of-n monotone & series/parallel-bracketed).
- **`docs/architecture.md` §26** — v16 architecture section (deep-embedding铁律 + 7 waves +
  honest scope).
- **CI** — `v16 --strict` step appended to `.github/workflows/test.yml` after v15.
- **`tests/v16_scorecard.json`** — written by the authoritative `--rubric v16 --strict` run.

## Verification (quantitative anchors)

- **Test collection**: 1323 tests collected (§4.1 ≥ 1290 ✓).
- **Property tests**: 65 (§4.3 ≥ 65 ✓).
- **Fingerprints**: 80, both tiers green (§4.5 ≥ 80 ✓).
- **Mutation**: 80 % kill rate (§4.4 ≥ 75 % ✓).
- **New-code coverage**: the ~150 v16 core statements are ~98 % covered (only two defensive/
  unreachable lines — `_is_prime` `n<2` and `_smallest_primitive_root`'s post-loop raise,
  both shadowed by `fast_cbc`'s earlier guards), above the 95 % core average.
- **Authoritative `--rubric v16 --strict`**: target 100/100 with v4–v15 regression = False and
  the D033 pytest-green gate; scorecard committed as `tests/v16_scorecard.json`.

(The §5 demo checks have the known cross-milestone limitation that the regex literal in
`test_agent.py` self-matches; mitigated here by building all seven demos for real and
verifying they run with correct numerics — antisym D₁₆≈1e-13 vs plain 369, normal-marginal
bit-exact match, α=2 worst-case error ~17× below α=1, parallel ≤ series.)

## Honest scope notes

- **§5 demo self-match flaw persists** (accepted, repo-wide since v6): the rubric token grep
  matches its own regex literal, so §5 would pass even without real demos. Mitigation is the
  build-for-real discipline applied here, not a rubric fix.
- **Two uncovered defensive lines** in the new fast-CBC helpers are deliberate (correct
  primality/primitive-root code defensively guarding cases its sole caller already rejects);
  not pragma-suppressed (the repo uses no `# pragma: no cover`).
- **v16 inherited honest defers remain open** as documented per-ADR: D117 cross-regime stable
  λ (MMA regrid path-noise), D120 composite-N fast-CBC and bit-equality with naive (provably
  impossible), D115 mixture Rosenblatt sampling, D119 large-m k-out-of-n estimator.

## Reopening criteria (v17 backlog seed)

- Wire D117's exact multiplier into a production MMA dual-variable readout (replace the
  envelope-FD probe with the optimiser's own λ).
- D120 fast-CBC into `genz_mvn_cdf_cbc` as an opt-in large-N path; composite-N support.
- D115 general marginals composed with D119 k-out-of-n (general-marginal redundant systems).
- Mixture-copula Rosenblatt sampling (beyond CDF-level series).
- Replace the §5 demo self-match check with an output-artifact assertion (cross-milestone fix).

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (`np.fft` is numpy;
scipy/pyamg/meshio optional), 2D/2.5D only, local `pytest -q` (no network), single-line
stderr + `SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion (honest scope notes lead each v16 ADR).
