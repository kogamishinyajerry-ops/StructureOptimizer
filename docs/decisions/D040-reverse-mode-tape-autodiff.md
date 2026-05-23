# D040 — reverse-mode (tape) autodiff (Wave KK)

**Status**: Accepted
**Wave**: KK (v6)
**Supersedes**: none (adds reverse mode beside D023's forward-mode `Var`)
**Superseded by**: none

## Context

v5 Wave DD (D023) shipped `core/autodiff.py`. Despite the module title claiming
"reverse-mode", the delivered `Var` class is actually **forward-mode**: it
carries the derivative w.r.t. a single seed, and its own docstring conceded
"Reverse-mode is out of scope (would need a tape)." For a scalar objective of n
design variables — exactly the SIMP sensitivity case — forward mode costs n
evaluations while reverse mode costs one backward pass. v6 delivers the real
reverse mode and corrects the docstring.

## Decision

Add to `core/autodiff.py`, beside the untouched `Var`:

- `RVar` — a reverse-mode variable recording an implicit tape. Each node stores
  its value plus a tuple of `(parent, local_partial)` edges. Same operator set
  as `Var` (+, -, *, /, **, neg), so expressions cross-check between modes.
- `RVar.backward()` — seeds the scalar output's adjoint to 1 and propagates it
  to every reachable input via an **iterative** post-order traversal (no
  Python-recursion-depth limit). A reused node accumulates adjoint from all of
  its consumers (correct chain rule across shared subexpressions).
- `reverse_grad(f, x)` — `f(list[RVar]) → RVar`; returns the full ∂f/∂xᵢ vector
  from one backward pass. Non-scalar output → single-line `SolverError`.

The module + `Var` docstrings are corrected to describe forward vs reverse mode
accurately. (The module's pre-existing quoted-annotation / tuple-`__slots__` /
`typing.Callable` style — flagged by ruff UP037/RUF023/UP035 already in v5 — is
matched by `RVar` for consistency and left as-is; not part of this wave.)

## Verification (quantitative)

- **Reverse == analytical == central-FD** (`test_reverse_matches_analytical_and_fd`):
  a mixed +/-/*//** function with a reused input; reverse grad matches the
  analytic gradient to ≤1e-9 and central-FD to ≤1e-6.
- **Reverse == forward** (`test_reverse_matches_forward_var_single_input`):
  reverse grad of x³+2x²−5x equals the forward-mode `Var.grad` and the analytic
  3x²+4x−5 to rel 1e-12. The cross-mode anchor the blueprint asks for.
- **All partials, one pass** (`test_reverse_rosenbrock_all_partials_one_pass`):
  Rosenbrock — both partials returned from a single backward, matching analytic
  (1e-9) and FD (1e-6).
- **Shared-subexpression accumulation** (`test_reverse_dag_reuse_accumulates`):
  y=a·b feeding y²+y; ∂/∂a=(2ab+1)b, ∂/∂b=(2ab+1)a — matched to FD. This is the
  reverse-mode-specific correctness property (per-seed approaches drop it).
- **Deep chain** (`test_reverse_deep_chain_no_recursion_limit`): 20 000 chained
  ops differentiate to 1.0 — a recursive backward would overflow Python's stack;
  the iterative traversal does not.
- **Direct example** + **contract** (non-scalar output → SolverError). 7 tests,
  all green. Adjacent forward-mode `test_autodiff` (14) unchanged.

## Honest scope notes

- Operator set is +, -, *, /, **, neg (matches `Var`). No exp/log/trig/numpy-array
  ops — this is a sensitivity-verification tool, not a JAX/PyTorch competitor.
- Scalar nodes only; vectorised/array-valued reverse mode is out of scope.
- `**` supports a constant float exponent only (not `RVar ** RVar`).
- Not yet wired to differentiate the SIMP compliance objective end-to-end (the
  hand-derived adjoint sensitivities remain the production path; `reverse_grad`
  is for independently verifying them on reduced expressions).

## Reopening criteria

- A workflow differentiating a closed-form objective with many variables →
  extend `RVar` with the needed elementary functions.
- Array-level reverse mode → a tensor tape (larger effort; reconsider a real AD
  dependency at that point).

## Red lines

numpy + stdlib only, single-line stderr — held. `Var` and its callers untouched.
