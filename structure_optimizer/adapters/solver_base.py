"""v0.8 linear-solver adapter interface (v1.8: scipy sparse backends added).

This is the **single boundary** where a FEM linear solve (K · u = f) crosses
into the rest of the codebase. Anything that consumes ``solve_linear_elastic``
goes through a ``LinearSolver`` instance, so swapping the underlying
linear-algebra implementation requires no changes outside this directory.

Current built-in backends:
- ``NumpyDenseSolver`` (``"dense"``): ``np.linalg.solve``. Fast for small N,
  O(N^3) cost, O(N^2) memory. Default backend.
- ``NumpyCGSolver`` (``"cg"``): pure-NumPy Conjugate Gradient iterative
  solver for SPD systems. Lower memory; more iterations but cheaper
  per-iteration on large N.
- ``ScipySparseSolver`` (``"sparse"``, **optional**): scipy.sparse.linalg.spsolve.
  Direct sparse factorization. Real memory savings on large meshes.
  Requires ``pip install structure-optimizer[sparse]``.
- ``ScipySparseCGSolver`` (``"sparse_cg"``, **optional**): scipy.sparse.linalg.cg
  with sparse matrices. Lowest memory; iterative.

Sparse backends opt into a different assembly path: the matrix is built
directly as ``scipy.sparse.csr_matrix`` rather than dense, which scales
linearly in DOFs instead of quadratically.

Extension hooks (not implemented):
- CalculiX / Code_Aster file-based adapter (write input deck, shell out,
  parse output). Out of scope for v2.x.
- AMG preconditioner (pyamg) — investigate when CG iteration count
  becomes the bottleneck.

Contract:
- Implementations receive a square symmetric positive-definite matrix
  ``A`` (numpy ndarray for ``prefers_sparse=False``, scipy.sparse.csr_matrix
  for ``prefers_sparse=True``) and an RHS vector ``b`` (both already
  restricted to free DOFs).
- Implementations return ``u`` such that ``A @ u ≈ b``.
- Singular / non-convergent solves raise ``SolverError`` (in ``core.fem2d``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class LinearSolver(ABC):
    """Abstract base for linear solvers operating on free-DOF reduced systems.

    ``prefers_sparse`` (class attribute) signals to the FEM assembly code
    whether the solver expects a dense numpy ndarray or a sparse
    scipy.sparse matrix. Override in subclasses; default is dense (False)
    to preserve v1.7-and-earlier behavior for unknown backends.
    """

    name: str = "abstract"
    prefers_sparse: bool = False

    @abstractmethod
    def solve(self, matrix: Any, rhs: np.ndarray) -> np.ndarray:
        """Solve ``matrix @ u = rhs`` for ``u``.

        Args:
            matrix: SPD square stiffness submatrix (free DOFs only). Type
                depends on ``self.prefers_sparse``.
            rhs:    force vector restricted to free DOFs.
        Returns:
            displacement vector for free DOFs.
        """


class NumpyDenseSolver(LinearSolver):
    """``np.linalg.solve`` — LAPACK ``gesv`` direct factorization.

    Fastest path for ``ndof_free`` up to a few thousand. The default backend.
    """

    name = "dense"

    def solve(self, matrix: np.ndarray, rhs: np.ndarray) -> np.ndarray:
        from structure_optimizer.core.fem2d import SolverError  # avoid import cycle

        try:
            return np.linalg.solve(matrix, rhs)
        except np.linalg.LinAlgError as exc:
            raise SolverError("singular_matrix") from exc


class NumpyCGSolver(LinearSolver):
    """Pure-NumPy preconditioned Conjugate Gradient.

    Uses Jacobi (diagonal) preconditioning. Tolerance and max iterations are
    fixed; if real workflows need them tunable, v0.9 should extend the config
    schema.

    Iteration count is bounded by ``max_iterations`` to avoid runaway runs on
    ill-conditioned matrices; failure to converge raises ``SolverError``.
    """

    name = "cg"
    tolerance: float = 1e-10
    max_iterations: int = 5000

    def solve(self, matrix: np.ndarray, rhs: np.ndarray) -> np.ndarray:
        from structure_optimizer.core.fem2d import SolverError  # avoid import cycle

        diag = np.diag(matrix)
        if np.any(diag <= 0):
            raise SolverError("singular_matrix")
        preconditioner = 1.0 / diag

        u = np.zeros_like(rhs)
        r = rhs - matrix @ u
        z = preconditioner * r
        p = z.copy()
        rz_old = float(r @ z)

        rhs_norm = float(np.linalg.norm(rhs))
        if rhs_norm == 0.0:
            return u
        target = self.tolerance * rhs_norm

        for _ in range(self.max_iterations):
            ap = matrix @ p
            pap = float(p @ ap)
            if pap <= 0:
                raise SolverError("singular_matrix")
            alpha = rz_old / pap
            u = u + alpha * p
            r = r - alpha * ap
            if float(np.linalg.norm(r)) <= target:
                return u
            z = preconditioner * r
            rz_new = float(r @ z)
            beta = rz_new / rz_old
            p = z + beta * p
            rz_old = rz_new

        raise SolverError("cg_did_not_converge")


try:
    import scipy.sparse
    import scipy.sparse.linalg  # noqa: F401

    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False


class ScipySparseSolver(LinearSolver):
    """``scipy.sparse.linalg.spsolve`` — direct sparse factorization (SuperLU).

    Memory-efficient for large meshes (O(non-zeros) instead of O(N^2)).
    Available only when ``scipy`` is installed (``pip install
    structure-optimizer[sparse]``).
    """

    name = "sparse"
    prefers_sparse = True

    def solve(self, matrix: Any, rhs: np.ndarray) -> np.ndarray:
        import warnings

        from scipy.sparse import SparseEfficiencyWarning
        from scipy.sparse.linalg import MatrixRankWarning, spsolve

        from structure_optimizer.core.fem2d import SolverError

        # spsolve returns NaN-filled vector for singular matrices (doesn't raise);
        # promote MatrixRankWarning to an error so we can catch it consistently.
        with warnings.catch_warnings():
            warnings.simplefilter("error", category=MatrixRankWarning)
            warnings.simplefilter("ignore", category=SparseEfficiencyWarning)
            try:
                solution = np.asarray(spsolve(matrix.tocsr(), rhs))
            except (MatrixRankWarning, RuntimeError) as exc:
                raise SolverError("singular_matrix") from exc
        if not np.all(np.isfinite(solution)):
            raise SolverError("singular_matrix")
        return solution


class ScipySparseCGSolver(LinearSolver):
    """``scipy.sparse.linalg.cg`` with sparse matrices — iterative SPD solver.

    Lowest memory; uses Jacobi (diagonal) preconditioning implicitly via
    scipy's default. Convergence failure raises ``SolverError``.
    """

    name = "sparse_cg"
    prefers_sparse = True
    tolerance: float = 1e-10
    max_iterations: int = 5000

    def solve(self, matrix: Any, rhs: np.ndarray) -> np.ndarray:
        from scipy.sparse.linalg import cg

        from structure_optimizer.core.fem2d import SolverError

        matrix_csr = matrix.tocsr()
        # scipy renamed ``tol`` → ``rtol`` in 1.12; support both.
        try:
            x, info = cg(matrix_csr, rhs, rtol=self.tolerance, maxiter=self.max_iterations)
        except TypeError:
            x, info = cg(matrix_csr, rhs, tol=self.tolerance, maxiter=self.max_iterations)
        if info > 0:
            raise SolverError("cg_did_not_converge")
        if info < 0:
            raise SolverError("singular_matrix")
        return np.asarray(x)


_REGISTRY: dict[str, type[LinearSolver]] = {
    NumpyDenseSolver.name: NumpyDenseSolver,
    NumpyCGSolver.name: NumpyCGSolver,
}
if _SCIPY_AVAILABLE:
    _REGISTRY[ScipySparseSolver.name] = ScipySparseSolver
    _REGISTRY[ScipySparseCGSolver.name] = ScipySparseCGSolver


def available_backends() -> list[str]:
    """Return alphabetised list of registered linear-solver backend names."""
    return sorted(_REGISTRY)


def get_linear_solver(backend: str | None) -> LinearSolver:
    """Factory: return a ``LinearSolver`` instance for a backend name.

    ``backend`` of ``None`` or empty string defaults to ``"dense"``.
    Unknown backends raise ``ValueError`` listing valid options — config
    validation should catch this before we reach the solver factory, but
    this is the last-line guard.
    """
    key = (backend or "dense").lower()
    impl = _REGISTRY.get(key)
    if impl is None:
        raise ValueError(f"Unknown linear solver backend '{backend}'. Available: {available_backends()}")
    return impl()


# Legacy export so older imports (`Solver`) keep working transparently.
Solver: Any = LinearSolver
