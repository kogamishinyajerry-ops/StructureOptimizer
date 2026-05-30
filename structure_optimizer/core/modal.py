"""Wave Z: 2D modal analysis (generalized eigenvalue problem) — v5 multi-physics.

Solves K(ρ) φ = ω² M(ρ) φ on the same plane-stress quad mesh as the
linear-elastic FEM, where:

- K  is the elastic stiffness matrix (`fem2d.element_stiffness`)
- M  is the consistent or lumped mass matrix (this module)
- φ  is a mode shape (displacement)
- ω² is the squared natural angular frequency (rad/s)²

For the eigensolver this module uses a pure-NumPy generalized-eigenvalue
path:

    Cholesky factor M = L Lᵀ → solve L⁻¹ K L⁻ᵀ y = ω² y → φ = L⁻ᵀ y

`np.linalg.eigh` handles the symmetric inner eigenproblem. This is dense
and O(N³) but works on numpy-only hosts (scipy not required).

Mass matrix:
- ``mass_type="consistent"`` — standard bilinear-quad consistent mass
  (Hughes 1987 §7.3). Each element contributes
      Me = ρ · t · A / 36 · [[4, 2, 1, 2] ⊗ I₂, …]    (8×8)
- ``mass_type="lumped"`` — row-sum lumping → diagonal.

SIMP scaling: mass scales linearly with density (no penalty exponent),
following Diaz & Kikuchi 1992 and the bulk of the modal-TO literature.
This avoids the spurious low-density eigenmodes that come from penalising
mass with p > 1.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import SolverError, element_stiffness
from structure_optimizer.core.mesh import StructuredMesh


@dataclass
class ModalResult:
    """Output of a generalised-eigenvalue solve.

    Attributes:
        omega_squared: array of smallest ``n_modes`` eigenvalues ω² (rad/s)²
        eigenvectors:  matrix of mode shapes (ndof_free × n_modes)
        free_dofs:     index array of the free DOFs (companion to eigenvectors)
        n_dof:         total mesh DOF count
    """

    omega_squared: np.ndarray
    eigenvectors: np.ndarray
    free_dofs: np.ndarray
    n_dof: int

    @property
    def frequencies_hz(self) -> np.ndarray:
        """Convert ω² → Hz (ω/2π) under the assumption units are rad/s."""
        omega = np.sqrt(np.clip(self.omega_squared, 0.0, None))
        return omega / (2.0 * np.pi)


def element_mass_matrix(density: float, thickness: float = 1.0, mass_type: str = "consistent") -> np.ndarray:
    """4-node bilinear-quad mass matrix for unit-sized element (8×8 plane-stress).

    Args:
        density:    material mass density (kg/m³)
        thickness:  out-of-plane thickness (m)
        mass_type:  ``"consistent"`` (full) or ``"lumped"`` (diagonal row-sum)
    """
    if mass_type not in ("consistent", "lumped"):
        raise SolverError(f"unknown_mass_type: {mass_type!r}")

    # Consistent 4-node bilinear pattern (Hughes 1987 §7.3 table 7.3.2)
    pattern = (
        1.0
        / 36.0
        * np.array(
            [
                [4.0, 2.0, 1.0, 2.0],
                [2.0, 4.0, 2.0, 1.0],
                [1.0, 2.0, 4.0, 2.0],
                [2.0, 1.0, 2.0, 4.0],
            ],
            dtype=float,
        )
    )
    # 8×8 mass matrix: block-diag Kronecker with 2D identity (ux & uy share pattern)
    me = density * thickness * np.kron(pattern, np.eye(2))
    if mass_type == "lumped":
        # Row-sum lumping
        diag = me.sum(axis=1)
        me = np.diag(diag)
    return me


def _assemble_mass_dense(
    mesh: StructuredMesh,
    density_scale: np.ndarray,
    me_base: np.ndarray,
) -> np.ndarray:
    """Assemble dense global mass matrix scaled by per-element densities."""
    n_dof = mesh.ndof
    M = np.zeros((n_dof, n_dof), dtype=float)
    for elem_id in range(mesh.elements.shape[0]):
        dofs = mesh.element_dofs(elem_id)
        scale = float(density_scale[elem_id])
        for i in range(8):
            for j in range(8):
                M[dofs[i], dofs[j]] += scale * me_base[i, j]
    return M


def _assemble_stiffness_dense_modal(
    mesh: StructuredMesh,
    density_scale: np.ndarray,
    ke: np.ndarray,
) -> np.ndarray:
    """Re-implementation of `_assemble_stiffness_dense` for modal use (avoid
    circular import with fem2d's helper which is private)."""
    n_dof = mesh.ndof
    K = np.zeros((n_dof, n_dof), dtype=float)
    for elem_id in range(mesh.elements.shape[0]):
        dofs = mesh.element_dofs(elem_id)
        scale = float(density_scale[elem_id])
        for i in range(8):
            for j in range(8):
                K[dofs[i], dofs[j]] += scale * ke[i, j]
    return K


def _generalized_eigh_symmetric(K: np.ndarray, M: np.ndarray, n_modes: int) -> tuple[np.ndarray, np.ndarray]:
    """Pure-NumPy solution to K φ = λ M φ for the n_modes smallest λ.

    Uses Cholesky transform: with M = L Lᵀ, K φ = λ M φ ↔
    (L⁻¹ K L⁻ᵀ)(Lᵀ φ) = λ (Lᵀ φ). The inner symmetric eigenproblem is
    handed to ``np.linalg.eigh`` which returns ascending eigenvalues.
    """
    try:
        L = np.linalg.cholesky(M)
    except np.linalg.LinAlgError as exc:
        raise SolverError("mass_matrix_not_positive_definite") from exc
    # A_sym = L⁻¹ K L⁻ᵀ
    Linv_K = np.linalg.solve(L, K)
    A_sym = np.linalg.solve(L, Linv_K.T).T  # equivalent to (L⁻¹ K) L⁻ᵀ
    A_sym = 0.5 * (A_sym + A_sym.T)  # symmetrise numerical noise
    eigvals, y = np.linalg.eigh(A_sym)
    # Smallest n_modes
    omega2 = eigvals[:n_modes]
    y_n = y[:, :n_modes]
    # Back-transform φ = L⁻ᵀ y
    phi = np.linalg.solve(L.T, y_n)
    return omega2, phi


def solve_modal(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    n_modes: int = 3,
    mass_type: str = "consistent",
) -> ModalResult:
    """Compute the n_modes smallest natural frequencies of the SIMP-scaled
    structure.

    Args:
        config:     BenchmarkConfig (supplies material + boundary conditions)
        mesh:       structured-quad mesh
        densities:  per-element densities (n_elements,)
        n_modes:    how many smallest eigenvalues to return (default 3)
        mass_type:  "consistent" or "lumped"
    """
    opt = config.optimization
    densities = np.asarray(densities, dtype=float).reshape(-1)
    if densities.shape[0] != mesh.elements.shape[0]:
        raise SolverError("density_count_mismatch")
    if n_modes < 1:
        raise SolverError("n_modes_must_be_positive")

    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
    me = element_mass_matrix(config.material.density, config.thickness, mass_type)

    active = np.where(mesh.void_mask, opt.min_density, densities)
    k_scale = opt.min_density + (active**opt.penalty) * (1.0 - opt.min_density)
    # Linear mass scaling (Diaz & Kikuchi 1992) — no SIMP penalty on mass
    m_scale = opt.min_density + active * (1.0 - opt.min_density)

    K = _assemble_stiffness_dense_modal(mesh, k_scale, ke)
    M = _assemble_mass_dense(mesh, m_scale, me)

    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(mesh.ndof), fixed)
    if free.size == 0:
        raise SolverError("modal_all_dofs_fixed")
    if n_modes > free.size:
        raise SolverError(f"modal_n_modes_exceeds_free_dofs: {n_modes} > {free.size}")

    K_ff = K[np.ix_(free, free)]
    M_ff = M[np.ix_(free, free)]

    omega2, phi = _generalized_eigh_symmetric(K_ff, M_ff, n_modes)

    return ModalResult(
        omega_squared=omega2,
        eigenvectors=phi,
        free_dofs=free,
        n_dof=mesh.ndof,
    )
