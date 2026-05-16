"""Wave S: SIMP driver using MMA + Augmented Lagrangian for stress constraints.

Composes the building blocks introduced in Wave S into an end-to-end
topology optimizer that delivers what v3.x couldn't:

- σ_PN ≤ σ_lim **strictly** (within ``feas_tol``), not "encouraged"
- MMA as the inner update — convergence with multiple inequality
  constraints (volume + stress) instead of OC's volume-only bisection

Returns an ``OptimizationResult`` compatible with the existing v1-v3 path
so downstream tools (verification, reporting, _repr_html_) work unchanged.
"""

from __future__ import annotations

import numpy as np

from structure_optimizer.adapters.solver_base import get_linear_solver
from structure_optimizer.core.adjoint import adjoint_stress_sensitivity
from structure_optimizer.core.augmented_lagrangian import (
    AugLagState,
    augmented_objective,
    update_multipliers,
)
from structure_optimizer.core.config import BenchmarkConfig, effective_load_cases
from structure_optimizer.core.fem2d import (
    build_sparse_assembly_template,
    element_stiffness,
)
from structure_optimizer.core.filtering import density_filter
from structure_optimizer.core.manufacturing import apply_manufacturing_projections
from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.core.mma import MMAState, mma_step
from structure_optimizer.core.objectives import solve_and_aggregate
from structure_optimizer.core.simp import (
    IterationMetric,
    OptimizationResult,
    _apply_density_masks,
)


def _filter_then_clip(
    mesh: StructuredMesh,
    densities: np.ndarray,
    sensitivities: np.ndarray,
    radius: float,
    min_density: float,
) -> np.ndarray:
    return density_filter(mesh, densities, sensitivities, radius, min_density)


def run_simp_mma_auglag(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    feas_tol: float = 0.01,
    max_outer: int = 12,
    inner_per_outer: int = 8,
    rho0: float = 1.0,
) -> OptimizationResult:
    """Stress-constrained SIMP via MMA + Augmented Lagrangian.

    Requires ``config.stress_constraint.enabled`` (the whole point of this
    driver). Volume target is enforced by MMA as one inequality constraint;
    stress is enforced by AL.

    Args:
        config: benchmark configuration with ``stress_constraint`` enabled.
        mesh: structured-quad mesh.
        feas_tol: σ_PN / σ_lim - 1 ≤ feas_tol stops outer loop (default 1%).
        max_outer: cap on AL outer iterations.
        inner_per_outer: MMA inner iterations between each AL multiplier
            update.
        rho0: initial AL penalty.

    Returns:
        ``OptimizationResult`` (compatible with v1-v3 path). ``stop_reason``
        will be one of ``converged`` / ``max_outer`` / ``change_tolerance``.
    """
    sc = config.stress_constraint
    if not sc.enabled:
        raise ValueError("run_simp_mma_auglag requires config.stress_constraint.enabled")

    opt = config.optimization
    load_cases = effective_load_cases(config)
    n_elem = mesh.elements.shape[0]
    densities = np.full(n_elem, opt.volume_fraction, dtype=float)
    densities = _apply_density_masks(config, mesh, densities)
    baseline_densities = np.ones(n_elem, dtype=float)
    baseline_densities = _apply_density_masks(config, mesh, baseline_densities)
    aggregator = opt.case_aggregator

    sparse_template = None
    linear_solver = get_linear_solver(config.solver.backend)
    if linear_solver.prefers_sparse:
        ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
        sparse_template = build_sparse_assembly_template(mesh, ke)

    baseline = solve_and_aggregate(
        config, mesh, baseline_densities, load_cases, aggregator, sparse_template=sparse_template
    )

    metrics: list[IterationMetric] = []
    density_history: list[np.ndarray] = [densities.copy()]
    design_count = max(1, int(np.count_nonzero(mesh.design_mask)))

    mma_state = MMAState(move_limit=0.15)
    al_state = AugLagState.init(m=1, rho0=rho0)

    xmin = np.full(n_elem, opt.min_density)
    xmax = np.ones(n_elem)
    # Freeze solid → 1, void → min_density
    xmin = np.where(mesh.frozen_solid_mask, 1.0, xmin)
    xmax = np.where(mesh.void_mask, opt.min_density, xmax)
    xmin = np.minimum(xmin, xmax)

    final_analysis = baseline
    stop_reason = "max_outer"
    total_inner = 0

    for _outer in range(max_outer):
        previous_x = densities.copy()
        # Inner MMA loop on the *current* AL objective
        for _inner in range(inner_per_outer):
            previous = densities.copy()
            analysis = solve_and_aggregate(
                config,
                mesh,
                densities,
                load_cases,
                aggregator,
                sparse_template=sparse_template,
            )
            # Compliance sensitivity (SIMP standard form)
            df_compliance = -opt.penalty * (densities ** (opt.penalty - 1.0)) * analysis.element_strain_energy
            df_compliance[~mesh.design_mask] = 0.0
            f_compliance = float(analysis.compliance)

            # Stress: σ_PN and gradient via adjoint
            sigma_pn, stress_sens, _ = adjoint_stress_sensitivity(
                config,
                mesh,
                densities,
                analysis.displacements,
            )
            # Constraint g(x) = σ_PN / limit - 1 ≤ 0
            g_val = sigma_pn / sc.limit - 1.0
            dg = stress_sens / sc.limit  # shape (n,)
            g_arr = np.array([g_val])
            dg_arr = dg.reshape(1, -1)

            # Augmented Lagrangian objective + grad
            _L_A, dL_A = augmented_objective(f_compliance, df_compliance, g_arr, dg_arr, al_state)

            # Apply density filter to sensitivities (Bendsøe filter consistency)
            dL_A = _filter_then_clip(mesh, densities, dL_A, opt.filter_radius, opt.min_density)
            dL_A[~mesh.design_mask] = 0.0

            # Volume constraint for MMA: Σ ρ / N - V* ≤ 0
            vol_g = float(np.sum(densities[mesh.design_mask]) / design_count - opt.volume_fraction)
            vol_dg = np.zeros_like(densities)
            vol_dg[mesh.design_mask] = 1.0 / design_count

            x_new, _lmbda = mma_step(
                densities,
                dL_A,
                np.array([vol_g]),
                vol_dg.reshape(1, -1),
                xmin,
                xmax,
                mma_state,
            )
            x_new = apply_manufacturing_projections(config, mesh, x_new)
            x_new = _apply_density_masks(config, mesh, x_new)
            change_inner = float(np.max(np.abs(x_new - previous)))
            densities = x_new
            total_inner += 1
            density_history.append(densities.copy())

            active_volume = float(np.sum(densities[mesh.design_mask]) / design_count)
            metrics.append(
                IterationMetric(
                    iteration=total_inner,
                    compliance=analysis.compliance,
                    volume_fraction=active_volume,
                    change=change_inner,
                    max_displacement=analysis.max_displacement,
                    mass=analysis.mass,
                )
            )
            final_analysis = analysis
            if change_inner <= opt.change_tolerance and total_inner > opt.min_iterations:
                break

        # AL outer update
        analysis = solve_and_aggregate(
            config,
            mesh,
            densities,
            load_cases,
            aggregator,
            sparse_template=sparse_template,
        )
        sigma_pn, _stress_sens, _ = adjoint_stress_sensitivity(
            config,
            mesh,
            densities,
            analysis.displacements,
        )
        g_val = sigma_pn / sc.limit - 1.0
        update_multipliers(np.array([g_val]), al_state)

        outer_change = float(np.max(np.abs(densities - previous_x)))
        if max(0.0, g_val) <= feas_tol and outer_change <= opt.change_tolerance:
            stop_reason = "converged"
            break

    final_analysis = solve_and_aggregate(
        config,
        mesh,
        densities,
        load_cases,
        aggregator,
        sparse_template=sparse_template,
    )
    return OptimizationResult(
        densities=densities,
        metrics=metrics,
        baseline=baseline,
        final_analysis=final_analysis,
        stop_reason=stop_reason,
        density_history=density_history,
        load_case_names=[load_case.name for load_case in load_cases],
        mesh_shape=(mesh.nelx, mesh.nely),
    )
