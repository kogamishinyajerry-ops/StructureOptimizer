# D033 — pytest-green no-regression gate in test_agent

**Status**: Accepted
**Wave**: post-v5.0.0 maintenance
**Supersedes**: none (extends D023 test-agent mechanism)
**Superseded by**: none

## Context

`scripts/test_agent.py` scores the rubric from **static probes** — file
existence, `grep` counts, `pytest --collect-only` counts, and coverage
percentages. None of those probes *runs* the test suite to completion and
checks the result. D023 documented this as a deliberate "mechanical, not
judgemental" design, and D024/D032 flagged the residual weakness ("the
agent that writes the rubric also implements it").

That weakness became concrete: five v5 multi-physics fingerprint files
(`heat_sink`, `vibrating_beam`, `nonlinear_cantilever`, `stochastic_uq`,
`stochastic_worst_case`) were committed in Waves Y / CC / DD as fixtures
but never validated. `tests/test_fingerprints.py` globbed them in and
raised `KeyError: 'input_hash'` at runtime, so `pytest -q` was
**5 failed, 793 passed** — while `test_agent.py --rubric v5` reported a
clean **100/100, release ready**. The rubric items
(`check_3_1_fingerprint_count`, `check_v5_3_4_stochastic_fingerprints`,
`check_v5_4_5_fingerprints_25`) only *counted the JSON files*; the
`--collect-only` reproducibility probe never executed them. A green rubric
and a red suite coexisted with no signal.

(The five fingerprints are now validated by
`tests/test_multiphysics_fingerprints.py` — they reproduce bit-exact, so
the failures were a glob/schema bug, not numerical drift. See that file's
docstring.)

## Decision

Add a **pytest-green no-regression gate** to `test_agent.py`, modelled on
the existing v1-v4 regression gates (hard fail, *not* part of the 100
points):

- `check_pytest_green()` runs `pytest -q` (full suite) and records
  `passed / failed / errors / skipped / returncode / green`.
- The gate is **green** iff return code == 0 and there are zero failures
  and zero errors. Skips are allowed (the slow perf tests are
  `--run-slow`-gated).
- `run_all()` runs the gate by default; `print_summary()` prints it and
  folds `regression` into the "release ready" verdict; `--strict` exits
  non-zero if the gate is red. The result is persisted to the scorecard
  JSON under `pytest_check`.
- The gate is **skipped for `--section` (partial) scoring** and via
  `--no-pytest-gate` — a partial score should not gate on the whole suite,
  and iterative scoring needs a fast path.

Consequence: a 100/100 rubric can no longer be reported as "release ready"
while `pytest` is red. The two signals (rubric score, suite green) are now
both required and reported separately.

## What this does NOT do (honest scope notes)

- It does **not** make the rubric items themselves run their tests; they
  remain static probes (that is D023's design, unchanged). The gate is an
  orthogonal backstop, not a rewrite of the scoring model.
- It does **not** assert a specific pass count — only "no failures/errors".
  Test-count thresholds remain rubric items (§4.1).
- It roughly doubles `test_agent` wall-time on a full run (the suite runs
  once for the gate, plus the existing coverage runs). Acceptable for a
  release gate; `--no-pytest-gate` / `--section` provide the fast path.

## Reopening criteria

- If the full-suite run makes the release gate impractically slow, gate on
  a curated fast subset (smoke + fingerprints) and run the full suite only
  in CI.
- If a future rubric promotes "every rubric item executes its test" (true
  dynamic scoring), this orthogonal gate can be retired in favour of that.

## Verification

`pytest -q` → 799 passed, 4 skipped, 0 failed.
`python scripts/test_agent.py --rubric v5` → 100/100, pytest gate green,
"release ready". Forcing a red suite flips the verdict to
"release blocked (D033 gate)".
