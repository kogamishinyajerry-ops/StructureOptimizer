# D004 — scipy as optional dependency (Wave H / v1.8)

**Status**: Accepted (v1.8.0, 2026-05-16)

## Context

Wave H adds two sparse solver backends (`sparse`, `sparse_cg`) using
`scipy.sparse.linalg`. The project red line 7.2 from v1.x is "runtime
mandatory deps stay NumPy-only". scipy is a 50+ MB install — including it
unconditionally would break the red line and inflate the install footprint
for users who don't need sparse solvers.

## Decision

scipy is an **optional dependency**:

- `[project.optional-dependencies].sparse = ["scipy>=1.11"]` in pyproject.toml.
- Install via `pip install structure-optimizer[sparse]`.
- `adapters/solver_base.py` probes for scipy at import time:
  ```python
  try:
      import scipy.sparse, scipy.sparse.linalg
      _SCIPY_AVAILABLE = True
  except ImportError:
      _SCIPY_AVAILABLE = False
  ```
- `ScipySparseSolver` and `ScipySparseCGSolver` are defined unconditionally;
  registry entries are added only when scipy is available.
- `available_backends()` returns only the backends usable in the current
  environment — users get clear errors at config-validation time, not at
  runtime.

## Alternatives considered

1. **Add scipy to mandatory deps**. Rejected: breaks red line 7.2;
   inflates install size 30×.
2. **Lazy-import inside `solve()` method**. Rejected: equivalent runtime
   behavior but loses the registry-level guard, so config validation
   wouldn't catch "you asked for sparse but scipy isn't installed".
3. **Vendor a minimal sparse solver**. Rejected: rewriting LAPACK + ARPACK
   in pure NumPy is a separate project.

## Consequences

- Default `pip install structure-optimizer` is still NumPy-only, 2-3 MB.
- Users on large meshes do `pip install structure-optimizer[sparse]` and
  flip a config flag.
- The same pattern applies to `[mesh] = ["meshio>=5.0"]` (Wave I) —
  established a clear precedent.
- CI must run two test matrices: vanilla (NumPy only) + with-extras
  (all optionals). See `.github/workflows/test.yml`.

## Reopening criteria

- scipy becomes a transitive dependency of something we already depend on
  (unlikely while NumPy is the only mandatory dep).
- A user demonstrates a use case where the sparse backend should be the
  default — e.g. "out of 100 real users, 95 are on meshes too large for
  dense to be tractable".
