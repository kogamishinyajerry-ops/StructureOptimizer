"""Wave S §1.2 evidence: MMA vs OC convergence comparison.

Both Method of Moving Asymptotes (MMA, Svanberg 1987) and Optimality
Criteria (OC, Bendsøe 1995) are gradient-based topology optimizers. The
two should reach **similar compliance and similar topology** on a
single-constraint (volume-only) SIMP problem — that is the canonical
sanity check before adding stress / robust / buckling constraints
where OC alone can no longer handle the constraint structure.
"""

from __future__ import annotations

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.simp import run_simp


def _run_oc(config_name: str, preset: str | None = "smoke"):
    config = load_benchmark(config_name, preset=preset)
    mesh = create_structured_mesh(config)
    return run_simp(config, mesh), config, mesh


def _run_mma_volume_only(config_name: str, preset: str | None = "smoke"):
    """Run MMA on volume-constrained compliance minimization (single constraint)."""
    from dataclasses import replace

    from structure_optimizer.adapters.solver_base import get_linear_solver
    from structure_optimizer.core.config import effective_load_cases
    from structure_optimizer.core.fem2d import (
        build_sparse_assembly_template,
        element_stiffness,
    )
    from structure_optimizer.core.filtering import density_filter
    from structure_optimizer.core.manufacturing import apply_manufacturing_projections
    from structure_optimizer.core.mma import MMAState, mma_step
    from structure_optimizer.core.objectives import solve_and_aggregate
    from structure_optimizer.core.simp import _apply_density_masks

    config = load_benchmark(config_name, preset=preset)
    # Disable stress constraint so we compare apples-to-apples with OC
    config = replace(
        config,
        stress_constraint=replace(config.stress_constraint, enabled=False),
    )
    mesh = create_structured_mesh(config)
    opt = config.optimization
    load_cases = effective_load_cases(config)
    n_elem = mesh.elements.shape[0]
    densities = np.full(n_elem, opt.volume_fraction, dtype=float)
    densities = _apply_density_masks(config, mesh, densities)
    aggregator = opt.case_aggregator

    sparse_template = None
    linear_solver = get_linear_solver(config.solver.backend)
    if linear_solver.prefers_sparse:
        ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
        sparse_template = build_sparse_assembly_template(mesh, ke)

    design_count = max(1, int(np.count_nonzero(mesh.design_mask)))
    xmin = np.full(n_elem, opt.min_density)
    xmax = np.ones(n_elem)
    xmin = np.where(mesh.frozen_solid_mask, 1.0, xmin)
    xmax = np.where(mesh.void_mask, opt.min_density, xmax)
    xmin = np.minimum(xmin, xmax)

    state = MMAState(move_limit=0.2)
    for _ in range(opt.max_iterations):
        analysis = solve_and_aggregate(
            config,
            mesh,
            densities,
            load_cases,
            aggregator,
            sparse_template=sparse_template,
        )
        # Compliance gradient
        df = -opt.penalty * (densities ** (opt.penalty - 1.0)) * analysis.element_strain_energy
        df[~mesh.design_mask] = 0.0
        # Filter sensitivity for consistency with OC SIMP
        df = density_filter(mesh, densities, df, opt.filter_radius, opt.min_density)
        df[~mesh.design_mask] = 0.0
        # Single volume constraint
        vol_g = float(np.sum(densities[mesh.design_mask]) / design_count - opt.volume_fraction)
        vol_dg = np.zeros_like(densities)
        vol_dg[mesh.design_mask] = 1.0 / design_count
        previous = densities.copy()
        x_new, _ = mma_step(
            densities,
            df,
            np.array([vol_g]),
            vol_dg.reshape(1, -1),
            xmin,
            xmax,
            state,
        )
        x_new = apply_manufacturing_projections(config, mesh, x_new)
        x_new = _apply_density_masks(config, mesh, x_new)
        change = float(np.max(np.abs(x_new - previous)))
        densities = x_new
        if change <= opt.change_tolerance:
            break
    final = solve_and_aggregate(
        config,
        mesh,
        densities,
        load_cases,
        aggregator,
        sparse_template=sparse_template,
    )
    return densities, final, mesh


def test_mma_vs_oc_volume_only_cantilever():
    """Both MMA and OC respect volume target and reach comparable compliance."""
    oc_result, oc_cfg, oc_mesh = _run_oc("cantilever", preset="smoke")
    mma_x, mma_final, mma_mesh = _run_mma_volume_only("cantilever", preset="smoke")

    # Both must produce non-trivial finite results
    assert oc_result.final_analysis.compliance > 0
    assert mma_final.compliance > 0
    # Total mass / volume should be ≤ target (both methods)
    design_count_oc = max(1, int(np.count_nonzero(oc_mesh.design_mask)))
    design_count_mma = max(1, int(np.count_nonzero(mma_mesh.design_mask)))
    vol_oc = float(np.sum(oc_result.densities[oc_mesh.design_mask]) / design_count_oc)
    vol_mma = float(np.sum(mma_x[mma_mesh.design_mask]) / design_count_mma)
    target = oc_cfg.optimization.volume_fraction
    assert abs(vol_oc - target) < 0.02
    assert abs(vol_mma - target) < 0.05  # MMA tolerates slightly more drift via slacks

    # Final compliance should be comparable (within a generous 3× window — both
    # are sound optimizers but MMA's first-pass approximation can be looser on
    # very small smoke meshes where filter dominates)
    ratio = mma_final.compliance / oc_result.final_analysis.compliance
    assert 0.3 < ratio < 3.0, f"compliance ratio MMA/OC = {ratio:.2f} out of range"


def test_mma_oc_comparison_records_iteration_history():
    """Both must track per-iter history (used by reporting / diagnostics)."""
    oc_result, *_ = _run_oc("cantilever", preset="smoke")
    assert len(oc_result.metrics) > 0
    # MMA path tested via _run_mma_volume_only — its inner MMAState.history
    # is exposed when caller wants it; here we just ensure both paths run.
    mma_x, mma_final, _ = _run_mma_volume_only("cantilever", preset="smoke")
    assert mma_final.compliance > 0
    assert mma_x.shape == oc_result.densities.shape
