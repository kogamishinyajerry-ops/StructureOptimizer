# D030 — NSGA-II Pareto front + autodiff (Wave DD · v5)

**Status**: Accepted
**Wave**: DD
**Supersedes**: none
**Superseded by**: none

## Context

v1-v4 minimised a single scalar objective (compliance, with stress or
buckling as constraints). For genuine engineering trade-offs —
compliance vs mass, stress vs volume — we need a **Pareto front**:
a set of non-dominated objective tuples that engineers can choose
from based on application priorities.

The textbook algorithm for multi-objective topology optimisation is
**NSGA-II** (Deb et al. 2002): genetic algorithm with non-dominated
sorting + crowding-distance selection. It's a heuristic — convergence
to the *true* Pareto front isn't guaranteed in finite time — but it
reliably produces non-dominated front samples that are good enough
for practical decision support.

Adjacent to Pareto fronts: **autodiff for gradient verification**.
SIMP sensitivity expressions are easy to derive incorrectly, and the
current test suite catches mismatches via finite-difference checks
scattered across modules. A consolidated `core/autodiff.py` with
`gradient_check` and a `Var` forward-mode class gives a single,
well-tested verification entrypoint.

## Decision

Two new modules in one ADR:

### `core/pareto_nsga.py`
- `nsga_ii(eval_fn, n_vars, bounds, population_size, n_generations,
  rng_seed)` → `ParetoFront`
- SBX crossover + polynomial mutation (Deb 1995)
- Non-dominated sort + crowding distance (Deb 2002)
- `render_pareto(front, html_path)` → self-contained HTML+SVG
  visualisation (no external dep — same philosophy as v3's
  interactive demo, D012)

### `core/autodiff.py`
- `gradient_check(f, x, h)` — central finite-difference gradient
- `Var` — minimal forward-mode AD class with +, -, *, /, **, neg,
  and rtruediv (supports `c / x`)
- `grad_check_against_analytical(f, df, x, h, rtol)` — convenience
  wrapper for unit tests

Both are designed for **verification**, not for performance — they
intentionally don't try to compete with JAX / PyTorch / autograd.

## Why NSGA-II over MOEA/D / SPEA2

- **NSGA-II is the canonical multi-objective GA** — most engineering
  literature uses it; results are directly comparable.
- **SPEA2** uses external archive + density estimation; more complex
  implementation for marginal Pareto-front quality gain at 2 objectives.
- **MOEA/D** decomposes into scalarised sub-problems; better at high
  dimensions but worse at maintaining diversity at 2 objectives.
- **NSGA-III** is preferred for ≥3 objectives but the reference-point
  selection adds complexity. v5+ option if a real workflow needs it.

## Why pure-numpy AD instead of JAX/autograd

- **JAX** would be the right choice for production AD, but it's a
  large dep (~100 MB) — incompatible with the numpy-only red line.
- **autograd** is older + numpy-native but unmaintained; reverse-mode
  + numpy interop is finicky.
- **The use case** is sensitivity verification, not performance.
  Central FD + `Var` forward-mode fit on one screen + ~150 LOC.

## Honest scope notes

### NSGA-II
- **Bi-objective only** — extending to ≥3 needs reference-point
  variants (NSGA-III).
- **No constraint handling** — caller's `eval_fn` must return finite
  objectives. Constraint violations as soft penalties is the standard
  workaround.
- **Heuristic convergence** — the test asserts non-dominance and
  finite objectives, NOT analytical-front match (NSGA-II at small
  pop/gen doesn't reach the true ZDT1 front).
- **SBX crossover assumes continuous variables** — discrete encoding
  needs a different operator.

### Autodiff
- **Forward-mode only** — reverse-mode (the AD style most useful for
  ML / large gradients) would need a tape implementation. Out of scope.
- **Scalar `Var`** — no vector `Var` class (would need numpy-broadcast
  semantics for *, +, etc.).
- **No control flow** — no `if`, `while`, `for` over `Var` instances.

## Reopening criteria

- If ≥3 objectives become routine, implement NSGA-III with reference
  points.
- If integrated multi-objective SIMP (NSGA-II driving density updates
  rather than post-processing) is needed, build it in
  `core/multi_objective_simp.py`.
- If reverse-mode AD becomes necessary for performance, switch to
  optional JAX dep (`pip install structure-optimizer[autodiff]`).

## Consequences

- 2 new modules (~330 LOC total).
- 17 new tests (6 NSGA-II + 11 autodiff).
- v5 rubric §3.5 + §5.1 + §5.3 = 7 pts.
