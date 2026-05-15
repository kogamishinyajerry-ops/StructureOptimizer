"""v0.8 linear-solver adapter interface.

This is the **single boundary** where a FEM linear solve (K · u = f) crosses
into the rest of the codebase. Anything that consumes ``solve_linear_elastic``
goes through a ``LinearSolver`` instance, so swapping the underlying
linear-algebra implementation requires no changes outside this directory.

Current built-in backends:
- ``NumpyDenseSolver``: ``np.linalg.solve``. Fast for small N, O(N^3) cost,
  O(N^2) memory. Default backend.
- ``NumpyCGSolver``: pure-NumPy Conjugate Gradient iterative solver for SPD
  systems. Lower memory; more iterations but cheaper per-iteration on large N.
  Useful for benchmarks where N > a few thousand DOFs.

Extension hooks (not implemented; documented for future spike):
- scipy.sparse.linalg.spsolve / cg / minres backend (requires adding scipy
  as a dependency — see docs/architecture.md §4 invariants before doing so).
- CalculiX / Code_Aster file-based adapter (write input deck, shell out,
  parse output). Out of scope for v0.x.

Contract:
- Implementations receive a square symmetric positive-definite matrix
  ``A`` and a right-hand-side vector ``b``, both restricted to the free
  DOFs (boundary conditions already eliminated by the caller).
- Implementations return the solution vector ``u`` such that ``A @ u ≈ b``.
- Singular / non-convergent solves raise ``SolverError`` (defined in
  ``structure_optimizer.core.fem2d``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class LinearSolver(ABC):
    """Abstract base for linear solvers operating on free-DOF reduced systems."""

    name: str = "abstract"

    @abstractmethod
    def solve(self, matrix: np.ndarray, rhs: np.ndarray) -> np.ndarray:
        """Solve ``matrix @ u = rhs`` for ``u``.

        Args:
            matrix: SPD square stiffness submatrix (free DOFs only).
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


_REGISTRY: dict[str, type[LinearSolver]] = {
    NumpyDenseSolver.name: NumpyDenseSolver,
    NumpyCGSolver.name: NumpyCGSolver,
}


def available_backends() -> list[str]:
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
        raise ValueError(
            f"Unknown linear solver backend '{backend}'. Available: {available_backends()}"
        )
    return impl()


# Legacy export so older imports (`Solver`) keep working transparently.
Solver: Any = LinearSolver
