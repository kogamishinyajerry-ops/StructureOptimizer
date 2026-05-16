"""Wave W: matrix-free Conjugate Gradient solver for large topology problems.

Instead of assembling the global stiffness matrix K (O(ndof²) memory for
dense, O(non-zeros) for sparse), this module computes ``K · v`` on-the-fly
per element via the SIMP-penalized element stiffness multiplication.
For 1000×1000 meshes (2M DOFs) the assembled sparse K is still hundreds
of MB; matrix-free uses **only the density vector** plus per-element
geometry — typically 1-2 orders of magnitude less memory.

Trade-off:
- Memory: O(n_elem × 1) for densities + O(ndof) for vectors = linear.
- Time per ``K · v`` apply: O(n_elem × 64) for the 8×8 quad ke
  (small constant matrix per element). Vs sparse-CSR matvec which is
  O(non-zeros) ≈ O(n_elem × 64) as well — so per-iteration cost is
  comparable; the win is exclusively memory.
- Useful when:
  * mesh is large (≥ 500k DOF)
  * available RAM is limited
  * the assembled sparse matrix would not fit

Uses Jacobi (diagonal) preconditioning. The diagonal of K is cheap:
sum over each element's contribution to its own DOFs, with SIMP
penalty applied.

Reference: Bendsøe & Sigmund (2003) §1.6 on iterative solvers;
Andreassen et al. (2011) "Efficient topology optimization in MATLAB"
discusses the assembly bottleneck this addresses.
"""

from __future__ import annotations

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import SolverError, element_stiffness
from structure_optimizer.core.mesh import StructuredMesh


def matrix_free_apply(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    ke: np.ndarray,
    v: np.ndarray,
) -> np.ndarray:
    """Compute ``K · v`` without assembling K.

    Args:
        config: benchmark config (for SIMP penalty + min_density).
        mesh: structured-quad mesh.
        densities: per-element density (length n_elem).
        ke: reference 8×8 element stiffness (output of
            ``core.fem2d.element_stiffness``).
        v: input vector of length ndof.

    Returns:
        ``K · v`` as a length-ndof array.
    """
    opt = config.optimization
    n_elem = mesh.elements.shape[0]
    result = np.zeros_like(v)
    active = np.where(mesh.void_mask, opt.min_density, densities)
    scale = opt.min_density + (active**opt.penalty) * (1.0 - opt.min_density)
    for eid in range(n_elem):
        edofs = mesh.element_dofs(eid)
        ve = v[edofs]
        local = scale[eid] * (ke @ ve)
        result[edofs] += local
    return result


def matrix_free_diagonal(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    ke: np.ndarray,
) -> np.ndarray:
    """Compute diag(K) without assembling K — needed for Jacobi preconditioning."""
    opt = config.optimization
    n_elem = mesh.elements.shape[0]
    diag = np.zeros(mesh.ndof, dtype=float)
    active = np.where(mesh.void_mask, opt.min_density, densities)
    scale = opt.min_density + (active**opt.penalty) * (1.0 - opt.min_density)
    ke_diag = np.diag(ke)
    for eid in range(n_elem):
        edofs = mesh.element_dofs(eid)
        diag[edofs] += scale[eid] * ke_diag
    return diag


def matrix_free_cg(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    rhs: np.ndarray,
    tolerance: float = 1e-8,
    max_iterations: int = 10000,
) -> np.ndarray:
    """Solve ``K(ρ) · u = rhs`` on free DOFs via matrix-free CG.

    Algorithm: standard PCG with Jacobi preconditioner; ``K · v``
    computed per-iteration via ``matrix_free_apply``.

    Args:
        config, mesh, densities: define K (SIMP-penalized).
        rhs: force vector on free DOFs (length = n_free).
        tolerance: ``||r|| ≤ tolerance × ||rhs||`` stops CG.
        max_iterations: cap.

    Returns:
        Solution vector restricted to free DOFs (caller must zero-pad
        to ndof for downstream use). Mirrors ``NumpyCGSolver`` semantics.

    Raises:
        SolverError: if CG fails to converge or breaks down.
    """
    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)

    # Build full-ndof matvec/diag then restrict to free DOFs
    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(mesh.ndof), fixed)
    if free.size == 0:
        raise SolverError("all degrees of freedom are fixed")

    diag = matrix_free_diagonal(config, mesh, densities, ke)
    diag_free = diag[free]
    if np.any(diag_free <= 0):
        raise SolverError("singular_matrix")
    M_inv = 1.0 / diag_free

    def apply_free(v_free: np.ndarray) -> np.ndarray:
        """K · v restricted to free DOFs (zero-pad input, apply, restrict)."""
        v_full = np.zeros(mesh.ndof, dtype=float)
        v_full[free] = v_free
        out_full = matrix_free_apply(config, mesh, densities, ke, v_full)
        return out_full[free]

    n_free = free.size
    u = np.zeros(n_free, dtype=float)
    r = rhs - apply_free(u)
    z = M_inv * r
    p = z.copy()
    rz_old = float(r @ z)

    rhs_norm = float(np.linalg.norm(rhs))
    if rhs_norm == 0.0:
        return u
    target = tolerance * rhs_norm

    for _ in range(max_iterations):
        ap = apply_free(p)
        pap = float(p @ ap)
        if pap <= 0:
            raise SolverError("singular_matrix")
        alpha = rz_old / pap
        u = u + alpha * p
        r = r - alpha * ap
        if float(np.linalg.norm(r)) <= target:
            return u
        z = M_inv * r
        rz_new = float(r @ z)
        beta = rz_new / rz_old
        p = z + beta * p
        rz_old = rz_new

    raise SolverError("matrix_free_cg_did_not_converge")


def estimate_memory_usage_mb(mesh: StructuredMesh) -> dict[str, float]:
    """Estimate matrix-free vs assembled memory cost for the given mesh.

    Returns ``{"densities_mb", "sparse_csr_mb", "dense_mb", "savings_ratio"}``.
    Each entry is in MiB; ``savings_ratio = sparse_csr / densities`` so a
    value > 10 means matrix-free saves ≥10× memory.

    Used by tests to assert the §2.3 rubric ("memory < 2× density × 64
    bytes" target on the per-iteration storage).
    """
    n_elem = mesh.elements.shape[0]
    ndof = mesh.ndof
    # Each ρ_e is 8 bytes (float64). Total density storage:
    density_bytes = n_elem * 8
    # Sparse K (CSR): ~64 entries per row × ndof × (8 + 4) bytes (val + col idx)
    sparse_bytes = ndof * 64 * 12
    dense_bytes = ndof * ndof * 8
    return {
        "densities_mb": density_bytes / (1024**2),
        "sparse_csr_mb": sparse_bytes / (1024**2),
        "dense_mb": dense_bytes / (1024**2),
        "savings_ratio": float(sparse_bytes / max(density_bytes, 1)),
    }
