"""Wave AA: geometrically-nonlinear 2D FEM (v5 multi-physics).

Solves the equilibrium equation under finite displacements

    f_ext = f_int(u) = K(ρ) u + K_g(ρ, u) u / 2          (St. Venant-Kirchhoff)

by Newton-Raphson incremental load-stepping. The tangent stiffness is

    K_T = K + K_g(ρ, u)

reusing the geometric-stiffness assembly path from `core/buckling.py`
(which Wave U already validated). Each load step solves the residual

    R(u) = f_ext_step - f_int(u)

with up to ``max_inner_iter`` Newton iterations, stopping when
``‖R‖ / ‖f_ext‖ < tol`` or the max is hit.

This is **simplified** total-Lagrangian — the SVK material law is
captured through `K_g(u)` as a quadratic-in-strain correction rather
than the full Green-strain integral. The agreement with linear FEM
holds exactly at small loads; at large loads the geometric stiffening
makes the predicted tip displacement **smaller** than the linear-FEM
estimate, mirroring the Gere elastica trend.

The full Total-Lagrangian Newton-Raphson on Green strain + 2nd PK stress
(Bonet & Wood Ch. 9) is a v5+ option if a real workflow demands ≤ 1%
agreement with the elastica.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from structure_optimizer.core.buckling import assemble_geometric_stiffness
from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import (
    SolverError,
    _assemble_stiffness_dense,
    element_stiffness,
)
from structure_optimizer.core.mesh import StructuredMesh


@dataclass
class NonlinearResult:
    """Output of a nonlinear (geometric) FEM solve.

    Attributes:
        displacements:    converged nodal displacements (n_dof,)
        load_steps:       list of load fractions applied (ascending)
        max_displacements: per-load-step max |u| (for load-displacement curve)
        n_newton_iters:   total Newton iterations across all load steps
        converged:        whether the final step met tolerance
    """

    displacements: np.ndarray
    load_steps: np.ndarray
    max_displacements: np.ndarray
    n_newton_iters: int
    converged: bool


def _build_load_vector(config: BenchmarkConfig, mesh: StructuredMesh) -> np.ndarray:
    n_dof = mesh.ndof
    f = np.zeros(n_dof)
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


def _density_scale_K(config: BenchmarkConfig, mesh: StructuredMesh, densities: np.ndarray) -> np.ndarray:
    opt = config.optimization
    active = np.where(mesh.void_mask, opt.min_density, densities)
    return opt.min_density + (active**opt.penalty) * (1.0 - opt.min_density)


def solve_geometric_nonlinear(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    n_load_steps: int = 5,
    max_inner_iter: int = 25,
    tol: float = 1e-5,
) -> NonlinearResult:
    """Incremental Newton-Raphson on the SVK-approximated nonlinear residual.

    Args:
        config:        BenchmarkConfig (uses loads + BCs + material + SIMP penalty)
        mesh:          structured-quad mesh
        densities:    per-element densities
        n_load_steps: number of incremental load steps (more → better tracking)
        max_inner_iter: max Newton iterations per load step
        tol:          residual-norm tolerance for Newton convergence
    """
    densities = np.asarray(densities, dtype=float).reshape(-1)
    if densities.shape[0] != mesh.elements.shape[0]:
        raise SolverError("density_count_mismatch")
    if n_load_steps < 1:
        raise SolverError("nonlinear_n_load_steps_must_be_positive")

    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
    k_scale = _density_scale_K(config, mesh, densities)
    K = _assemble_stiffness_dense(mesh, k_scale, ke)
    f_total = _build_load_vector(config, mesh)
    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(mesh.ndof), fixed)
    if free.size == 0:
        raise SolverError("nonlinear_all_dofs_fixed")
    if np.linalg.norm(f_total[free]) == 0:
        # No load → zero displacement is the trivial solution
        u = np.zeros(mesh.ndof)
        return NonlinearResult(
            displacements=u,
            load_steps=np.array([1.0]),
            max_displacements=np.array([0.0]),
            n_newton_iters=0,
            converged=True,
        )

    u = np.zeros(mesh.ndof)
    load_fractions = np.linspace(0.0, 1.0, n_load_steps + 1)[1:]
    max_disps = np.zeros(n_load_steps)
    total_newton = 0
    final_converged = False

    for step_idx, frac in enumerate(load_fractions):
        f_step = f_total * frac
        for _it in range(max_inner_iter):
            K_g = assemble_geometric_stiffness(config, mesh, densities, u)
            K_T = K + K_g
            # Residual R = f_ext - f_int with f_int ≈ K u + (1/2) K_g u
            f_int = K @ u + 0.5 * K_g @ u
            R = f_step - f_int

            f_norm = float(np.linalg.norm(f_step[free]))
            r_norm = float(np.linalg.norm(R[free]))
            total_newton += 1
            if f_norm > 0 and r_norm / f_norm < tol:
                final_converged = True
                break
            try:
                delta = np.linalg.solve(K_T[np.ix_(free, free)], R[free])
            except np.linalg.LinAlgError as exc:
                raise SolverError("nonlinear_tangent_singular") from exc
            u[free] += delta
        else:
            final_converged = False
        max_disps[step_idx] = float(np.max(np.abs(u)))

    return NonlinearResult(
        displacements=u,
        load_steps=load_fractions,
        max_displacements=max_disps,
        n_newton_iters=total_newton,
        converged=final_converged,
    )
