# D022 — In-house mutation testing (Wave W/X · 2025-Q4)

**Status**: Accepted
**Wave**: W (introduced) / X (formalised)
**Supersedes**: none (new)
**Superseded by**: none

## Context

v4 rubric §3.3 demands ≥ 70 % mutation kill rate as a *quantitative test-suite
quality floor*. Branch coverage measures "what code is executed"; mutation
testing measures "what code changes are *caught*". The two diverge — many
codebases hit 95 % coverage with mutation kill rates under 30 % because most
tests are happy-path asserts, not edge-detection guards.

External tools considered:

- **`mutmut`** (Python) — easy install, but on numpy-heavy code (`tests/`
  takes 2-5 min per run) a full mutmut sweep would take hours. The
  parallelism is limited to threading; subprocess workers are not stable
  across Python 3.10/3.13.
- **`cosmic-ray`** — better infra but heavier (depends on celery,
  redis-friendly). Overkill for our 3-module hot-path.
- **PIT** (Java) — wrong language.

## Decision

Build a small, well-scoped in-house mutation harness:

- `scripts/run_mutation_test.py` with 4 mutators (Coles 2007 minimal set):
  - `>` → `>=` (boundary)
  - `+` → `-` (arithmetic)
  - `*` → `+` (arithmetic)
  - `True` → `False` (boolean negation)
- Applied to 3 hot-path modules: `augmented_lagrangian.py`, `robust.py`,
  `matrix_free_cg.py`. Other modules covered by happy-path tests are
  out of scope (we don't expect novel coverage gain from mutating them).
- Each mutation: write mutated source → run a fixed pytest subset →
  restore. Outcome = `killed` (any test failed) / `survived` (all passed).
- Cap occurrences per mutator (default 3) to keep total runtime bounded
  (~5-10 minutes locally).
- Aggregate kill rate written to `tests/mutation_report.json`; v4 rubric
  §3.3 reads `aggregate_kill_rate ≥ 0.70`.

## Why this scope

- **Three modules, not the whole codebase**: mutation testing is most
  valuable on code with subtle numerical edge cases (constraint thresholds,
  CG convergence checks). Mutating `verification.py` or `mesh.py` would
  generate mostly trivially-killed mutations on already-tested asserts.
- **4 mutators, not 12**: the classical Coles minimum captures ~80 % of
  the value; more mutators inflate runtime without proportional signal.
- **Bounded per-mutator occurrences**: prevents pathological runtime when
  a source file has 200+ `*` operators.

## Honest disclosure

- **Not a substitute for branch coverage** — both are tracked separately
  (§3.3 mutation + §4.2/§4.3 line coverage).
- **Survivor analysis is manual**: surviving mutations are written to
  `mutation_report.json::per_module[].details[].outcome == "survived"` for
  human triage. The test suite is **not** auto-regenerated to kill them.
- **70 % is the floor, not the ceiling**: industry "good" mutation kill
  rates are 80-90 % on numerical code; we set 70 % so the bar is achievable
  without overfitting tests to the mutator set.
- **No equivalent-mutant detection**: a survivor might be a semantically
  equivalent mutation (e.g. `>` vs `>=` on a strictly-strict comparison
  that's never on the boundary in practice). We accept this as noise —
  acceptable at the 70 % floor.

## Reopening criteria

- If aggregate kill rate drops below 65 % at the next phase boundary, do
  a survivor sweep + add targeted tests.
- If the in-house harness grows above 30 minutes runtime, revisit `mutmut`
  + parallel workers.
- If a P0 bug ships that *would have been killed by a mutation already in
  the survivor list*, that's a hard signal to escalate the mutator set.

## Consequences

- One more script + one more JSON artifact in `tests/`.
- Adds ~5-10 min to a full v4 verification cycle (not on critical pytest
  path — runs as a separate CI step / manual quality gate).
- Documents the test-suite's *non-coverage* quality, which complements
  coverage % nicely in rubric reports.
