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
