"""Wave L: adjoint-method sensitivity for stress-constrained SIMP (v2.1).

This module fills the D003 留白 (deferred from v1.6): integrating stress
constraint into the SIMP optimization loop's gradient, not just the
verification check.

Math:
- Compute σ_PN(ρ, u) = (Σ_e σ_vm,e(u_e)^p)^(1/p) (masked by density_threshold)
- Compute ∂σ_PN/∂u (per-DOF gradient by chain rule)
- Solve adjoint system K λ = -∂σ_PN/∂u (one extra linear solve per SIMP iter)
- Sensitivity: dσ_PN/dρ_e = -p ρ_e^(p-1) (1-ρ_min) λ_e^T K_e^0 u_e
  (analogous to compliance sensitivity but with λ instead of u in the
  bilinear form)

The OC update combines:
- compliance sensitivity ∂c/∂ρ_e (always present)
- stress sensitivity ∂σ_PN/∂ρ_e (multiplied by penalty when σ_PN > σ_lim)

Reference:
- Bendsøe & Sigmund 2003, §3.5
- Le, Norato, Bruns, Ha & Tortorelli (2010), "Stress-based topology
  optimization for continua", *Structural and Multidisciplinary
  Optimization*.
"""

from __future__ import annotations

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import element_stiffness
from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.core.stress import aggregate_stress, element_von_mises_stresses


def _strain_displacement_matrix(mesh: StructuredMesh) -> np.ndarray:
    """Build the constant-strain-quad (CSQ) ``B`` matrix once (3×8) for all
    elements, since the mesh is uniform structured quad.

    Reverse-engineered from ``_approx_element_stress``:
    ε_xx = (∂u_x/∂x), ε_yy = (∂u_y/∂y), γ_xy = (∂u_x/∂y + ∂u_y/∂x)
    on a unit-size quad's center.
    """
    hx = mesh.width / mesh.nelx
    hy = mesh.height / mesh.nely
    a, b = 1.0 / (2.0 * hx), 1.0 / (2.0 * hy)
    return np.array(
        [
            [-a, 0, a, 0, a, 0, -a, 0],
            [0, -b, 0, -b, 0, b, 0, b],
            [-b, -a, -b, a, b, a, b, -a],
        ],
        dtype=float,
    )


def _constitutive_matrix(young_modulus: float, poisson_ratio: float) -> np.ndarray:
    """Plane-stress D matrix (3×3)."""
    nu = poisson_ratio
    factor = young_modulus / (1.0 - nu**2)
    return factor * np.array(
        [
            [1.0, nu, 0.0],
            [nu, 1.0, 0.0],
            [0.0, 0.0, (1.0 - nu) / 2.0],
        ]
    )


def stress_pn_and_gradient_w_r_t_u(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    displacements: np.ndarray,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Compute σ_PN and ∂σ_PN/∂u (length = mesh.ndof) at current displacement.

    Returns:
        (sigma_pn, dpn_du, element_von_mises) — the aggregated p-norm
        stress, its derivative w.r.t. the displacement vector, and the
        per-element von Mises stress field (also useful for diagnostics).
    """
    sc = config.stress_constraint
    if not sc.enabled:
        raise ValueError("stress_constraint must be enabled to compute adjoint sensitivity")

    stresses = element_von_mises_stresses(config, mesh, displacements)
    mask = densities >= sc.density_threshold
    sigma_pn = aggregate_stress(stresses, sc.aggregation, sc.p, mask)

    if sigma_pn <= 0.0:
        return sigma_pn, np.zeros(mesh.ndof, dtype=float), stresses

    bmat = _strain_displacement_matrix(mesh)
    dmat = _constitutive_matrix(config.material.young_modulus, config.material.poisson_ratio)
    db = dmat @ bmat  # 3×8 — strain → stress operator
    p = sc.p

    dpn_du = np.zeros(mesh.ndof, dtype=float)
    n_elem = mesh.elements.shape[0]
    # Avoid division by zero by skipping elements with σ_vm < tiny epsilon
    eps = 1e-30

    for eid in range(n_elem):
        if not mask[eid]:
            continue
        sigma_vm = stresses[eid]
        if sigma_vm < eps:
            continue
        edofs = mesh.element_dofs(eid)
        ue = displacements[edofs]
        # σ = D B u_e: per-component
        sx = float(db[0] @ ue)
        sy = float(db[1] @ ue)
        sxy = float(db[2] @ ue)
        # ∂σ_vm/∂u_e via chain rule
        # σ_vm² = σ_x² - σ_x σ_y + σ_y² + 3 σ_xy²
        # ∂(σ_vm²)/∂σ_x = 2σ_x - σ_y; ∂/∂σ_y = -σ_x + 2σ_y; ∂/∂σ_xy = 6 σ_xy
        dvm2_dsigma = np.array([2.0 * sx - sy, -sx + 2.0 * sy, 6.0 * sxy])
        # ∂σ_vm/∂u_e = (1/(2σ_vm)) * dvm2_dsigma · D B
        dvm_due = (dvm2_dsigma @ db) / (2.0 * sigma_vm)
        # ∂σ_PN/∂σ_vm,e contribution
        if sc.aggregation == "p_norm":
            # ∂σ_PN/∂σ_vm,e = σ_vm,e^(p-1) * σ_PN^(1-p)
            dpn_dvm = (sigma_vm ** (p - 1.0)) * (sigma_pn ** (1.0 - p))
        else:  # KS
            # ∂σ_KS/∂σ_vm,e = exp(p (σ_vm - max σ)) / Σ exp(...)
            #               (effectively softmax weight)
            # numerically stable: use shifted form
            smax = float(stresses[mask].max())
            shifted = np.exp(p * (stresses[mask] - smax))
            denom = float(shifted.sum())
            local_shift = np.exp(p * (sigma_vm - smax))
            dpn_dvm = float(local_shift / max(denom, eps))
        dpn_due = dpn_dvm * dvm_due  # 8-vector
        dpn_du[edofs] += dpn_due

    return sigma_pn, dpn_du, stresses


def adjoint_stress_sensitivity(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    displacements: np.ndarray,
    stiffness: object = None,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Compute σ_PN and dσ_PN/dρ via the adjoint method.

    Performs one extra linear solve: ``K λ = -∂σ_PN/∂u``. Returns:
        (sigma_pn, sensitivity, element_von_mises)

    ``sensitivity`` is the per-element gradient ``dσ_PN/dρ_e``; positive
    values mean σ_PN increases if ρ_e increases (so SIMP should push ρ
    down there to reduce stress).

    Args:
        config, mesh, densities, displacements: standard SIMP arguments.
        stiffness: optional precomputed dense stiffness matrix (used when
            the caller already has it; avoids reassembly).
    """
    from structure_optimizer.adapters.solver_base import get_linear_solver
    from structure_optimizer.core.fem2d import (
        SolverError,
        _assemble_stiffness_dense,
        _assemble_stiffness_sparse,
    )

    opt = config.optimization
    sc = config.stress_constraint
    if not sc.enabled:
        raise ValueError("stress_constraint must be enabled")

    sigma_pn, dpn_du, stresses = stress_pn_and_gradient_w_r_t_u(config, mesh, densities, displacements)

    if sigma_pn <= 0.0:
        return sigma_pn, np.zeros(mesh.elements.shape[0], dtype=float), stresses

    # Solve adjoint system K λ = -dpn_du on free DOFs (BCs identical to forward)
    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(mesh.ndof), fixed)
    if free.size == 0:
        raise SolverError("all degrees of freedom are fixed (cannot solve adjoint)")

    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
    active_density = np.where(mesh.void_mask, opt.min_density, densities)
    density_scale = opt.min_density + (active_density**opt.penalty) * (1.0 - opt.min_density)

    linear_solver = get_linear_solver(config.solver.backend)
    if stiffness is None:
        stiffness = (
            _assemble_stiffness_sparse(mesh, density_scale, ke)
            if linear_solver.prefers_sparse
            else _assemble_stiffness_dense(mesh, density_scale, ke)
        )

    lam = np.zeros(mesh.ndof, dtype=float)
    kff = stiffness.tocsr()[free, :][:, free] if linear_solver.prefers_sparse else stiffness[np.ix_(free, free)]  # type: ignore[attr-defined,index]
    # K λ = (∂σ_PN/∂u)^T  (no sign flip — sign goes into the final formula)
    rhs = dpn_du[free]
    lam[free] = linear_solver.solve(kff, rhs)

    # Per-element sensitivity: dσ_PN/dρ_e = -p ρ_e^(p-1) (1-ρ_min) λ_e^T K_e^0 u_e
    n_elem = mesh.elements.shape[0]
    sensitivity = np.zeros(n_elem, dtype=float)
    p_simp = opt.penalty
    rho_min = opt.min_density
    for eid in range(n_elem):
        edofs = mesh.element_dofs(eid)
        ue = displacements[edofs]
        le = lam[edofs]
        rho = active_density[eid]
        if rho < 1e-12:
            continue
        ke_local = ke
        bilinear = float(le @ (ke_local @ ue))
        sensitivity[eid] = -p_simp * (rho ** (p_simp - 1.0)) * (1.0 - rho_min) * bilinear

    # Frozen / void elements have zero gradient w.r.t. their density (they're not free)
    sensitivity[~mesh.design_mask] = 0.0

    return sigma_pn, sensitivity, stresses
