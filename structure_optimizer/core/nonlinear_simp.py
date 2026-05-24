"""Wave AA: SIMP driver for geometric-nonlinear compliance (v5 multi-physics).

Minimises **nonlinear** compliance ``f_ext · u_nonlinear`` where
``u_nonlinear`` comes from `core.nonlinear_fem.solve_geometric_nonlinear`,
subject to the standard volume-fraction constraint.

The sensitivity uses the linear-FEM approximation (`-p · ρ^(p-1) · (1 -
ρ_min) · u^T Ke u`) on the **nonlinear** displacement field. This is a
known and accepted simplification (Buhl et al. 2000) — full nonlinear
adjoint sensitivities would require a path-tracking adjoint solve which
is out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import element_stiffness
from structure_optimizer.core.filtering import density_filter
from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.core.nonlinear_fem import (
    NonlinearResult,
    _build_load_vector,
    solve_geometric_nonlinear,
)
from structure_optimizer.core.simp import _apply_density_masks, _optimality_criteria_update


@dataclass
class NonlinearIterationMetric:
    iteration: int
    nonlinear_compliance: float
    max_displacement: float
    volume_fraction: float
    max_density_change: float
    newton_iters: int


@dataclass
class NonlinearOptimizationResult:
    densities: np.ndarray
    final_result: NonlinearResult
    metrics: list[NonlinearIterationMetric]
    converged: bool
    mesh_shape: tuple[int, int]


def _default_initial_density(config: BenchmarkConfig, mesh: StructuredMesh) -> np.ndarray:
    rho0 = np.full(mesh.elements.shape[0], config.optimization.volume_fraction)
    return _apply_density_masks(config, mesh, rho0)


def run_nonlinear_simp(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    n_load_steps: int = 3,
) -> NonlinearOptimizationResult:
    """SIMP min-nonlinear-compliance driver.

    Args:
        config:         BenchmarkConfig (uses optimization.* + loads + BCs)
        mesh:           structured-quad mesh
        n_load_steps:   incremental load steps per nonlinear FEM solve
    """
    opt = config.optimization
    densities = _default_initial_density(config, mesh)
    metrics: list[NonlinearIterationMetric] = []
    converged_simp = False
    prev = densities.copy()
    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
    f_ext = _build_load_vector(config, mesh)

    for it in range(opt.max_iterations):
        result = solve_geometric_nonlinear(config, mesh, densities, n_load_steps=n_load_steps)
        u = result.displacements
        # SIMP compliance: c = f_ext · u (nonlinear)
        c = float(f_ext @ u)
        # Per-element strain energy (linear approx of sensitivity)
        elem_energy = np.zeros(mesh.elements.shape[0])
        for eid in range(mesh.elements.shape[0]):
            edofs = mesh.element_dofs(eid)
            ue = u[edofs]
            elem_energy[eid] = float(ue @ ke @ ue)

        active = np.where(mesh.void_mask, opt.min_density, densities)
        p = opt.penalty
        sens = -p * np.power(active, p - 1.0) * (1.0 - opt.min_density) * elem_energy
        sens = density_filter(mesh, densities, sens, opt.filter_radius, opt.min_density)

        new = _optimality_criteria_update(config, mesh, densities, sens)
        new = _apply_density_masks(config, mesh, new)

        change = float(np.max(np.abs(new - prev)))
        vol = float(np.mean(new))
        metrics.append(
            NonlinearIterationMetric(
                iteration=it,
                nonlinear_compliance=c,
                max_displacement=float(np.max(np.abs(u))),
                volume_fraction=vol,
                max_density_change=change,
                newton_iters=result.n_newton_iters,
            )
        )
        prev = densities.copy()
        densities = new

        if it >= opt.min_iterations and change < opt.change_tolerance:
            converged_simp = True
            break

    final = solve_geometric_nonlinear(config, mesh, densities, n_load_steps=n_load_steps)
    return NonlinearOptimizationResult(
        densities=densities,
        final_result=final,
        metrics=metrics,
        converged=converged_simp,
        mesh_shape=(mesh.nelx, mesh.nely),
    )


@dataclass
class TLAdjointResult:
    """End-compliance + adjoint sensitivity of a converged full-TL state (Wave OO)."""

    compliance: float
    sensitivity: np.ndarray
    converged: bool


def tl_adjoint_compliance_sensitivity(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    n_load_steps: int = 5,
) -> TLAdjointResult:
    """End-compliance C = fᵀu of the converged **full Total-Lagrangian** state
    (D034) plus its adjoint sensitivity dC/dρ_e (Wave OO, D044).

    At convergence the internal force equals the full external load,
    f_int(u, ρ) = f_total, so the adjoint λ solves K_T λ = f_total and

        dC/dρ_e = -(dk_scale_e/dρ_e / k_scale_e) · (λ_eᵀ f_int,e),

    because each element's TL internal force is linear in its SIMP modulus scale
    (f_int,e = k_scale_e · g_e(u)). In the linear limit K_T → K, f_int = K u,
    λ → u and this reduces to the self-adjoint −u_eᵀ(dK_e/dρ)u_e.
    """
    from structure_optimizer.core.total_lagrangian import (
        _build_load_vector,
        _density_scale,
        _element_internal_force_and_tangent,
        _plane_stress_D,
        solve_total_lagrangian,
    )

    densities = np.asarray(densities, dtype=float).reshape(-1)
    res = solve_total_lagrangian(config, mesh, densities, n_load_steps=n_load_steps)
    u = res.displacements

    D0 = _plane_stress_D(config.material.young_modulus, config.material.poisson_ratio)
    k_scale = _density_scale(config, mesh, densities)
    f_total = _build_load_vector(config, mesh)
    n_dof = mesh.ndof

    K_T = np.zeros((n_dof, n_dof))
    f_int_elems: list[np.ndarray] = []
    dofs_elems: list[np.ndarray] = []
    for e, nodes in enumerate(mesh.elements):
        coords = mesh.nodes[nodes]
        dofs = np.empty(8, dtype=int)
        dofs[0::2] = 2 * nodes
        dofs[1::2] = 2 * nodes + 1
        fe, ke, _ = _element_internal_force_and_tangent(coords, u[dofs], k_scale[e] * D0)
        K_T[np.ix_(dofs, dofs)] += ke
        f_int_elems.append(fe)
        dofs_elems.append(dofs)

    compliance = float(f_total @ u)

    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(n_dof), fixed)
    lam = np.zeros(n_dof)
    lam[free] = np.linalg.solve(K_T[np.ix_(free, free)], f_total[free])

    opt = config.optimization
    p, mn = opt.penalty, opt.min_density
    active = np.where(mesh.void_mask, mn, densities)
    sens = np.zeros(mesh.elements.shape[0])
    for e in range(mesh.elements.shape[0]):
        if mesh.void_mask[e]:
            continue
        dks = p * active[e] ** (p - 1.0) * (1.0 - mn)
        sens[e] = -(dks / k_scale[e]) * float(lam[dofs_elems[e]] @ f_int_elems[e])

    return TLAdjointResult(compliance=compliance, sensitivity=sens, converged=res.converged)


# --- Wave UU (v8, D050): geometric-nonlinear TO full OC loop ----------------
#
# D044 delivered the TL adjoint sensitivity but stopped short of a driver ("a TL
# in-the-loop optimiser ... is deferred"). Wave UU closes that loop: an
# optimality-criteria SIMP loop whose sensitivity is the full-TL adjoint
# dC/dρ_e (not the v5 linear-on-nonlinear approximation of run_nonlinear_simp),
# so the optimiser sees genuine large-deformation stiffness at every iteration.


@dataclass
class NonlinearTOResult:
    """Output of the full-TL adjoint OC loop (Wave UU)."""

    densities: np.ndarray
    compliance_history: list[float]
    volume_history: list[float]
    converged: bool
    mesh_shape: tuple[int, int]


def nonlinear_to_oc(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    n_load_steps: int = 4,
    max_iter: int = 25,
    change_tol: float = 1e-2,
) -> NonlinearTOResult:
    """Optimality-criteria topology optimisation of the **full Total-Lagrangian**
    end-compliance, driven by the D044 TL adjoint sensitivity (Wave UU, D050).

    Each iteration: solve the forward TL + adjoint for dC/dρ
    (``tl_adjoint_compliance_sensitivity``), density-filter the sensitivity, OC
    update under the volume constraint, re-apply masks. Stops on
    ``max|Δρ| < change_tol`` or ``max_iter``. Reuses the same OC update and
    density filter as the linear SIMP loop — only the sensitivity is the
    large-deformation one.
    """
    opt = config.optimization
    rho = _default_initial_density(config, mesh)
    compliance_history: list[float] = []
    volume_history: list[float] = []
    converged = False
    design = mesh.design_mask
    n_design = max(1, int(np.count_nonzero(design)))

    for _ in range(max_iter):
        out = tl_adjoint_compliance_sensitivity(config, mesh, rho, n_load_steps=n_load_steps)
        compliance_history.append(out.compliance)
        volume_history.append(float(np.sum(rho[design]) / n_design))
        sens = density_filter(mesh, rho, out.sensitivity, opt.filter_radius, opt.min_density)
        sens[~design] = 0.0
        previous = rho.copy()
        rho = _optimality_criteria_update(config, mesh, rho, sens)
        rho = _apply_density_masks(config, mesh, rho)
        if float(np.max(np.abs(rho - previous))) < change_tol:
            converged = True
            break

    final = tl_adjoint_compliance_sensitivity(config, mesh, rho, n_load_steps=n_load_steps)
    compliance_history.append(final.compliance)
    volume_history.append(float(np.sum(rho[design]) / n_design))
    return NonlinearTOResult(
        densities=rho,
        compliance_history=compliance_history,
        volume_history=volume_history,
        converged=converged,
        mesh_shape=(mesh.nelx, mesh.nely),
    )


def mma_nonlinear_to(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    n_load_steps: int = 4,
    max_iter: int = 30,
    change_tol: float = 1e-3,
) -> NonlinearTOResult:
    """MMA-driven topology optimisation of the **full Total-Lagrangian**
    end-compliance (Wave CCC, D058).

    D050's reopening criterion: replace the single-move-limit OC update of
    :func:`nonlinear_to_oc` with a proper constrained optimiser (MMA, the Method
    of Moving Asymptotes). The objective + sensitivity are the same D044 TL
    adjoint; the volume constraint is written as the explicit inequality
    ``g(x) = mean(x) − vf ≤ 0`` and handled by :func:`core.mma.mma_step` (which
    returns KKT multipliers). MMA's payoff over OC is *additional* constraints
    (stress, buckling, …) — on this compliance-only problem it is competitive
    with OC, which is the honest claim verified by the test.

    Operates on the design-cell sub-vector; void/solid cells are held by the
    masks. Stops on ``max|Δx| < change_tol`` or ``max_iter``.
    """
    from structure_optimizer.core.mma import MMAState, mma_step

    opt = config.optimization
    design = mesh.design_mask
    n_design = max(1, int(np.count_nonzero(design)))
    vf = float(opt.volume_fraction)

    rho = _default_initial_density(config, mesh)
    x = rho[design].astype(float).copy()
    xmin = np.full(n_design, opt.min_density)
    xmax = np.ones(n_design)
    dfdx = np.full((1, n_design), 1.0 / n_design)  # ∂g/∂x_e = 1/n (mean volume)
    state = MMAState()

    compliance_history: list[float] = []
    volume_history: list[float] = []
    converged = False

    for _ in range(max_iter):
        rho[design] = x
        rho = _apply_density_masks(config, mesh, rho)
        out = tl_adjoint_compliance_sensitivity(config, mesh, rho, n_load_steps=n_load_steps)
        compliance_history.append(out.compliance)
        volume_history.append(float(np.sum(rho[design]) / n_design))
        sens = density_filter(mesh, rho, out.sensitivity, opt.filter_radius, opt.min_density)
        df0dx = sens[design]
        fval = np.array([float(np.mean(x) - vf)])
        x_new, _lmbda = mma_step(x, df0dx, fval, dfdx, xmin, xmax, state)
        change = float(np.max(np.abs(x_new - x)))
        x = x_new
        if change < change_tol:
            converged = True
            break

    rho[design] = x
    rho = _apply_density_masks(config, mesh, rho)
    final = tl_adjoint_compliance_sensitivity(config, mesh, rho, n_load_steps=n_load_steps)
    compliance_history.append(final.compliance)
    volume_history.append(float(np.sum(rho[design]) / n_design))
    return NonlinearTOResult(
        densities=rho,
        compliance_history=compliance_history,
        volume_history=volume_history,
        converged=converged,
        mesh_shape=(mesh.nelx, mesh.nely),
    )
