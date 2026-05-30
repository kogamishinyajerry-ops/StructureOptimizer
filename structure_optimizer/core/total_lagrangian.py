"""Wave EE (v6): full Total-Lagrangian Green-strain Newton-Raphson.

This is the **rigorous** geometric-nonlinear solver that v5's
``core/nonlinear_fem.py`` deferred (D027 "Reopening criteria"). Where the v5
version approximated the St. Venant-Kirchhoff (SVK) response through a
matrix-level ``K + ½ K_g`` correction, this module integrates the genuine
Total-Lagrangian element (Bonet & Wood, *Nonlinear Continuum Mechanics for
Finite Element Analysis*, Ch. 9):

    deformation gradient   F = I + ∂u/∂X
    Green-Lagrange strain  E = ½ (Fᵀ F − I)
    2nd Piola-Kirchhoff    S = D : E            (SVK material)
    internal force         f_int = ∫ B_L(u)ᵀ S dV
    tangent stiffness      K_T   = ∫ (B_Lᵀ D B_L  +  Gᵀ Σ G) dV
                                      └ material ┘   └ geometric ┘

solved by Newton-Raphson with incremental load stepping. Plane stress,
unit thickness, 2×2 Gauss quadrature on the isoparametric Q4 element.

Why this matters (the correctness gain over the v5 approximation):
- **Frame indifference / objectivity**: a finite rigid-body rotation of the
  whole mesh produces *exactly zero* Green strain (and zero internal force).
  The v5 ``K + ½K_g`` form does not satisfy this; the full TL does. This is
  the flagship regression test (``test_total_lagrangian.py``).
- At small strain it reduces to linear elasticity (same SIMP density scaling),
  so the v1-v5 linear path is recovered as the small-load limit.

SIMP density coupling: the element constitutive matrix is scaled by the same
``ρ^p``-interpolation used everywhere else (``min_density + ρ^p (1-min_density)``),
keeping topology-optimization compatibility.

Permanent red lines respected: numpy-only, 2D, dense, single-line SolverError.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import StructuredMesh

# 2×2 Gauss points / weights on [-1,1]².
_GP = 1.0 / np.sqrt(3.0)
_GAUSS = [(-_GP, -_GP), (_GP, -_GP), (_GP, _GP), (-_GP, _GP)]
_GAUSS_W = [1.0, 1.0, 1.0, 1.0]

# Natural-coordinate node ordering matching mesh connectivity
# n1=(ex,ey), n2=(ex+1,ey), n3=(ex+1,ey+1), n4=(ex,ey+1):
_NODE_XI = np.array([-1.0, 1.0, 1.0, -1.0])
_NODE_ETA = np.array([-1.0, -1.0, 1.0, 1.0])


@dataclass
class TotalLagrangianResult:
    """Output of a full Total-Lagrangian solve.

    Attributes:
        displacements:     converged nodal displacements (n_dof,)
        load_steps:        load fractions applied (ascending)
        max_displacements: per-load-step max |u| (load-displacement curve)
        n_newton_iters:    total Newton iterations across all load steps
        converged:         whether the final step met tolerance
        strain_energy:     total strain energy ∫ ½ S:E dV at the final state
    """

    displacements: np.ndarray
    load_steps: np.ndarray
    max_displacements: np.ndarray
    n_newton_iters: int
    converged: bool
    strain_energy: float


def _shape_grad_natural(xi: float, eta: float) -> np.ndarray:
    """∂N/∂(ξ,η) for the 4 Q4 nodes. Returns (4, 2)."""
    dn_dxi = 0.25 * _NODE_XI * (1.0 + _NODE_ETA * eta)
    dn_deta = 0.25 * _NODE_ETA * (1.0 + _NODE_XI * xi)
    return np.column_stack([dn_dxi, dn_deta])


def _plane_stress_D(young: float, nu: float) -> np.ndarray:
    """SVK plane-stress constitutive matrix (Voigt: [E11, E22, 2E12])."""
    return young / (1.0 - nu**2) * np.array([[1.0, nu, 0.0], [nu, 1.0, 0.0], [0.0, 0.0, 0.5 * (1.0 - nu)]])


def _density_scale(config: BenchmarkConfig, mesh: StructuredMesh, densities: np.ndarray) -> np.ndarray:
    opt = config.optimization
    active = np.where(mesh.void_mask, opt.min_density, densities)
    return opt.min_density + (active**opt.penalty) * (1.0 - opt.min_density)


def _build_load_vector(config: BenchmarkConfig, mesh: StructuredMesh) -> np.ndarray:
    f = np.zeros(mesh.ndof)
    for load in config.loads:
        nodes = mesh.selector_nodes(load["selector"])
        if not nodes:
            continue
        fx = float(load.get("fx", 0.0)) / len(nodes)
        fy = float(load.get("fy", 0.0)) / len(nodes)
        for node in nodes:
            f[2 * node] += fx
            f[2 * node + 1] += fy
    return f


def _element_internal_force_and_tangent(
    coords: np.ndarray, u_e: np.ndarray, D: np.ndarray
) -> tuple[np.ndarray, np.ndarray, float]:
    """Full-TL element internal force (8,), tangent (8,8), strain energy (scalar).

    Args:
        coords: (4, 2) reference nodal coordinates X.
        u_e:    (8,) element displacement [u1x,u1y,...,u4x,u4y].
        D:      (3, 3) density-scaled plane-stress constitutive matrix.
    """
    u_nodes = u_e.reshape(4, 2)
    f_int = np.zeros(8)
    k_t = np.zeros((8, 8))
    energy = 0.0

    for (xi, eta), w in zip(_GAUSS, _GAUSS_W, strict=True):
        dn_nat = _shape_grad_natural(xi, eta)  # (4,2) ∂N/∂(ξ,η)
        jac = dn_nat.T @ coords  # (2,2) ∂X/∂(ξ,η)
        detj = np.linalg.det(jac)
        if detj <= 0:
            raise SolverError("total_lagrangian_nonpositive_jacobian")
        dn_dx = dn_nat @ np.linalg.inv(jac).T  # (4,2) ∂N/∂X
        dvol = detj * w

        # Deformation gradient F = I + ∂u/∂X = I + Σ_a u_a ⊗ ∂N_a/∂X
        grad_u = u_nodes.T @ dn_dx  # (2,2): grad_u[i,J] = ∂u_i/∂X_J
        F = np.eye(2) + grad_u

        # Green-Lagrange strain E = ½(FᵀF − I), Voigt [E11, E22, 2E12]
        E_t = 0.5 * (F.T @ F - np.eye(2))
        E_v = np.array([E_t[0, 0], E_t[1, 1], 2.0 * E_t[0, 1]])

        # 2nd PK stress S = D : E, Voigt [S11, S22, S12]
        S_v = D @ E_v
        S_t = np.array([[S_v[0], S_v[2]], [S_v[2], S_v[1]]])

        # Nonlinear strain-displacement B_L (3 × 8): δE_v = B_L δu
        B_L = np.zeros((3, 8))
        for a in range(4):
            dNx, dNy = dn_dx[a]
            cx, cy = 2 * a, 2 * a + 1
            # δE11 = F1J ∂Na/∂X ; row uses F[:,0]
            B_L[0, cx] = F[0, 0] * dNx
            B_L[0, cy] = F[1, 0] * dNx
            B_L[1, cx] = F[0, 1] * dNy
            B_L[1, cy] = F[1, 1] * dNy
            B_L[2, cx] = F[0, 0] * dNy + F[0, 1] * dNx
            B_L[2, cy] = F[1, 0] * dNy + F[1, 1] * dNx

        f_int += B_L.T @ S_v * dvol
        # Material tangent
        k_t += B_L.T @ D @ B_L * dvol
        # Geometric (initial-stress) tangent: Σ_ab (∂Na/∂X · S · ∂Nb/∂X) I₂
        for a in range(4):
            for b in range(4):
                kg = dn_dx[a] @ S_t @ dn_dx[b]
                k_t[2 * a, 2 * b] += kg * dvol
                k_t[2 * a + 1, 2 * b + 1] += kg * dvol

        energy += 0.5 * float(S_v @ E_v) * dvol

    return f_int, k_t, energy


def _assemble(
    config: BenchmarkConfig, mesh: StructuredMesh, densities: np.ndarray, u: np.ndarray, D0: np.ndarray
) -> tuple[np.ndarray, np.ndarray, float]:
    """Assemble global internal force, tangent, and total strain energy."""
    k_scale = _density_scale(config, mesh, densities)
    n_dof = mesh.ndof
    f_int = np.zeros(n_dof)
    k_t = np.zeros((n_dof, n_dof))
    energy = 0.0
    for e, nodes in enumerate(mesh.elements):
        coords = mesh.nodes[nodes]  # (4,2)
        dofs = np.empty(8, dtype=int)
        dofs[0::2] = 2 * nodes
        dofs[1::2] = 2 * nodes + 1
        u_e = u[dofs]
        D_e = k_scale[e] * D0
        fe, ke, en = _element_internal_force_and_tangent(coords, u_e, D_e)
        f_int[dofs] += fe
        k_t[np.ix_(dofs, dofs)] += ke
        energy += en
    return f_int, k_t, energy


def solve_total_lagrangian(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    n_load_steps: int = 5,
    max_inner_iter: int = 30,
    tol: float = 1e-8,
) -> TotalLagrangianResult:
    """Full Total-Lagrangian Newton-Raphson with incremental load stepping.

    Args:
        config:        BenchmarkConfig (loads + BCs + material + SIMP penalty)
        mesh:          structured-quad mesh
        densities:     per-element densities
        n_load_steps:  number of incremental load steps
        max_inner_iter: max Newton iterations per load step
        tol:           residual-norm tolerance (relative to applied load)
    """
    densities = np.asarray(densities, dtype=float).reshape(-1)
    if densities.shape[0] != mesh.elements.shape[0]:
        raise SolverError("density_count_mismatch")
    if n_load_steps < 1:
        raise SolverError("total_lagrangian_n_load_steps_must_be_positive")

    D0 = _plane_stress_D(config.material.young_modulus, config.material.poisson_ratio)
    f_total = _build_load_vector(config, mesh)
    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(mesh.ndof), fixed)
    if free.size == 0:
        raise SolverError("total_lagrangian_all_dofs_fixed")

    u = np.zeros(mesh.ndof)
    if np.linalg.norm(f_total[free]) == 0:
        return TotalLagrangianResult(
            displacements=u,
            load_steps=np.array([1.0]),
            max_displacements=np.array([0.0]),
            n_newton_iters=0,
            converged=True,
            strain_energy=0.0,
        )

    load_fractions = np.linspace(0.0, 1.0, n_load_steps + 1)[1:]
    max_disps = np.zeros(n_load_steps)
    total_newton = 0
    final_converged = False
    energy = 0.0

    for step_idx, frac in enumerate(load_fractions):
        f_step = f_total * frac
        f_norm = float(np.linalg.norm(f_step[free]))
        step_converged = False
        for _ in range(max_inner_iter):
            f_int, k_t, energy = _assemble(config, mesh, densities, u, D0)
            R = f_step - f_int
            r_norm = float(np.linalg.norm(R[free]))
            total_newton += 1
            if f_norm > 0 and r_norm / f_norm < tol:
                step_converged = True
                break
            try:
                delta = np.linalg.solve(k_t[np.ix_(free, free)], R[free])
            except np.linalg.LinAlgError as exc:
                raise SolverError("total_lagrangian_tangent_singular") from exc
            u[free] += delta
        final_converged = step_converged
        max_disps[step_idx] = float(np.max(np.abs(u)))

    return TotalLagrangianResult(
        displacements=u,
        load_steps=load_fractions,
        max_displacements=max_disps,
        n_newton_iters=total_newton,
        converged=final_converged,
        strain_energy=float(energy),
    )


def green_strain_field(mesh: StructuredMesh, u: np.ndarray) -> np.ndarray:
    """Per-element centroid Green-Lagrange strain (Voigt [E11,E22,2E12]).

    Used by the objectivity/patch tests: a finite rigid-body rotation must
    yield ~zero Green strain everywhere.
    """
    out = np.zeros((mesh.elements.shape[0], 3))
    dn_nat = _shape_grad_natural(0.0, 0.0)  # element centroid
    for e, nodes in enumerate(mesh.elements):
        coords = mesh.nodes[nodes]
        jac = dn_nat.T @ coords
        dn_dx = dn_nat @ np.linalg.inv(jac).T
        dofs = np.empty(8, dtype=int)
        dofs[0::2] = 2 * nodes
        dofs[1::2] = 2 * nodes + 1
        u_nodes = u[dofs].reshape(4, 2)
        F = np.eye(2) + u_nodes.T @ dn_dx
        E_t = 0.5 * (F.T @ F - np.eye(2))
        out[e] = [E_t[0, 0], E_t[1, 1], 2.0 * E_t[0, 1]]
    return out
