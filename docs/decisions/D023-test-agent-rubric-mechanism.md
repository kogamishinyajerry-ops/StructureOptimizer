# D023 — Dedicated test agent as v4 rubric mechanism (Wave X · 2025-Q4)

**Status**: Accepted
**Wave**: X
**Supersedes**: none (new)
**Superseded by**: none

## Context

v1-v3 rubrics were applied **manually**: at phase boundaries, a human read
the rubric markdown, ran `pytest -q`, counted things, eyeballed CLI output,
and wrote down a score in the changelog. This worked when the rubric was
short (v1 = 8 items) and the codebase was small.

By v4 the rubric grew to 23 items across 6 sections, and several items
(coverage, mutation kill rate, test count, fingerprint count, property-test
count, CLI red-line preservation) require running tooling and parsing
output. Manual scoring would be slow + error-prone — and worse, it would
*tempt the author to be generous* with PARTIAL → PASS in marginal cases.

The user's explicit charter ("绝对诚实客观") demands a mechanism that does
not let the author bias the score.

## Decision

Build `scripts/test_agent.py` as a **mechanical, source-controlled**
verifier of the v4 rubric.

Architecture:

```
scripts/test_agent.py
├── check_1_1_..._6_4()  — one function per rubric item
│   each returns (earned_pts, status, evidence_string)
├── _grep_count, _pytest_collect_count, _pytest_coverage  — primitives
├── _RUBRIC = [(section, code, title, max_pts, fn), ...]  — table-driven
└── main()  — runs all checks, prints scorecard, writes JSON
```

Output:
- Human: tabular console (PASS / PARTIAL / FAIL + evidence)
- Machine: `tests/v4_scorecard.json` (re-readable by CI / dashboards)

Each check function is ~5-15 lines. They use only file reads, grep,
and `pytest --collect-only / --cov`. **No human judgment inside.**

Acceptance gate: `total_earned ≥ 99` to ship v4.0.0.

## Why mechanical-only

- **No PARTIAL bias**: if a check function says FAIL, it's FAIL — author
  cannot argue "but the spirit of the requirement is met".
- **CI-runnable**: the agent runs in `.github/workflows/test.yml` so every
  PR sees the rubric delta. No manual rubric review needed for releases.
- **Auditable diff**: a check function change is a code change, requiring
  review. Bumping a threshold from 95 % to 90 % is visible in `git log`.

## What the test_agent does NOT do

- It does NOT generate tests. Coverage gaps must be filled by a human
  writing new tests (Wave X added 3 new test files for this reason).
- It does NOT modify source. It is a pure read-only auditor.
- It does NOT enforce the v1/v2/v3 rubrics beyond a "regression=False"
  gate — those rubrics' detail is delegated to the corresponding rubric
  markdown + per-version test files.
- It does NOT judge subjective quality (code style, comment density,
  naming). Those are out of scope; the rubric is intentionally objective.

## Honest disclosure

- **The test_agent is the rubric** — if the test_agent has a bug, the
  rubric has a bug. Wave X already caught two such bugs:
  1. §3.3 read `kill_rate` key but `run_mutation_test.py` writes
     `aggregate_kill_rate` (fix landed in W).
  2. §3.5 counted `def test_` lines but the rubric semantics is
     "number of test cases" (parametrize expands one def into N).
     Fix: switch to `--collect-only`.
- These fixes are *not* score inflation — they are correctness fixes
  for the agent. The post-fix score (82 → 99) reflects what was always
  true about the codebase; the pre-fix score (76) was *under-reporting*.
  Honest scoring works both ways.
- The agent is host-dependent: §4.3 adapters coverage depends on whether
  scipy / pyamg are installed. Code paths gated by optional deps are
  marked `# pragma: no cover` per standard Python convention; the agent
  measures only the non-pragma'd code.

## Reopening criteria

- If a v4 rubric item is rejected as "too easy to game" or "missed a real
  quality gap" during external review, revise the corresponding check
  function and document the rationale in this ADR's addendum section.
- If a v5 rubric is introduced, the v4 test_agent stays in place as a
  regression check; v5 gets its own agent (no shared state).
- If CI runtime exceeds 10 minutes purely from test_agent overhead,
  cache intermediate results (pytest collection JSON, coverage XML).

## Consequences

- One new ~470 LOC Python script.
- One new JSON artifact (`tests/v4_scorecard.json`) committed at each
  Wave boundary as a reproducible scoring trail.
- The author cannot ship v4.0.0 with `total_earned < 99` unless they
  modify the rubric (visible in git) or the test_agent (visible in git).
