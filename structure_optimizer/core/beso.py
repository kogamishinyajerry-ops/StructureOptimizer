"""Bidirectional Evolutionary Structural Optimization (Wave G / v1.7.0).

Hard-kill ESO/BESO style: each iteration ranks elements by sensitivity
(per-element strain energy, optionally filtered) and produces a discrete
0/1 design by promoting the top-ranked elements to solid and demoting the
rest to ``min_density``. The current "target volume" walks from 1.0 down to
``volume_fraction`` at rate ``er`` per iteration ("evolutionary ratio").

References:
- Huang & Xie (2010), *Evolutionary Topology Optimization of Continuum
  Structures*, Wiley.
- Yang, Xie & Steven (1999), "Topology optimization for frequencies using
  an evolutionary method", *IJNME*.

Differences vs SIMP:
- Density is essentially binary (``min_density`` ∪ ``1.0``); no gray
  intermediate values during the run.
- No optimality-criteria bisection; the threshold is found by sorting.
- ``element_strain_energy`` is the sensitivity directly (no ``ρ^(p-1)``
  scaling): BESO doesn't use the SIMP penalty term in the same way.

Shared with SIMP:
- design_mask / frozen_solid / void semantics
- density_filter for sensitivities
- manufacturing projections (symmetry / extrusion / min_member_size)
- multi-case aggregation through ``objectives.solve_and_aggregate``
"""

from __future__ import annotations

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig, effective_load_cases
from structure_optimizer.core.filtering import density_filter
from structure_optimizer.core.manufacturing import apply_manufacturing_projections
from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.core.objectives import solve_and_aggregate
from structure_optimizer.core.simp import IterationMetric, OptimizationResult


def run_beso(config: BenchmarkConfig, mesh: StructuredMesh) -> OptimizationResult:
    """Run BESO until target volume reached + densities stable.

    Algorithm:
      1. Initialize all design elements solid (density 1).
      2. FEA → element sensitivities (strain energy).
      3. Apply density filter to smooth sensitivities.
      4. Compute current target volume = max(target, prev * (1 - er)).
      5. Rank sensitivities; promote top-N to solid, demote rest to min_density.
      6. Apply masks (frozen / void) + manufacturing projections.
      7. Convergence: target reached AND change ≤ tolerance after min_iterations.
    """
    opt = config.optimization
    load_cases = effective_load_cases(config)
    aggregator = opt.case_aggregator
    er = opt.beso_er

    densities = np.ones(mesh.elements.shape[0], dtype=float)
    densities = _apply_density_masks(config, mesh, densities)
    baseline_densities = np.ones(mesh.elements.shape[0], dtype=float)
    baseline_densities = _apply_density_masks(config, mesh, baseline_densities)
    baseline = solve_and_aggregate(config, mesh, baseline_densities, load_cases, aggregator)

    target_vol = opt.volume_fraction
    design_count = max(1, int(np.count_nonzero(mesh.design_mask)))
    current_target = 1.0

    metrics: list[IterationMetric] = []
    density_history: list[np.ndarray] = [densities.copy()]
    stop_reason = "max_iterations"
    final_analysis = baseline

    for iteration in range(1, opt.max_iterations + 1):
        previous = densities.copy()
        analysis = solve_and_aggregate(config, mesh, densities, load_cases, aggregator)
        sensitivities = analysis.element_strain_energy.copy()
        sensitivities[~mesh.design_mask] = 0.0
        sensitivities = density_filter(mesh, densities, sensitivities, opt.filter_radius, opt.min_density)

        current_target = max(target_vol, current_target * (1.0 - er))
        n_solid = round(current_target * design_count)
        n_solid = max(1, min(design_count, n_solid))

        active = mesh.design_mask
        sens_active = sensitivities[active]
        sorted_sens = np.sort(sens_active)[::-1]
        threshold = float(sorted_sens[min(n_solid - 1, len(sorted_sens) - 1)])

        new_densities = densities.copy()
        candidate = np.where(sensitivities[active] >= threshold, 1.0, opt.min_density)
        new_densities[active] = candidate
        new_densities = apply_manufacturing_projections(config, mesh, new_densities)
        new_densities = _apply_density_masks(config, mesh, new_densities)

        change = float(np.max(np.abs(new_densities - previous)))
        densities = new_densities
        density_history.append(densities.copy())

        active_volume = float(np.sum(densities[mesh.design_mask]) / design_count)
        metrics.append(
            IterationMetric(
                iteration=iteration,
                compliance=analysis.compliance,
                volume_fraction=active_volume,
                change=change,
                max_displacement=analysis.max_displacement,
                mass=analysis.mass,
            )
        )
        final_analysis = analysis

        target_reached = abs(current_target - target_vol) < 1e-6
        if iteration >= opt.min_iterations and target_reached and change <= opt.change_tolerance:
            stop_reason = "change_tolerance"
            break

    final_analysis = solve_and_aggregate(config, mesh, densities, load_cases, aggregator)
    return OptimizationResult(
        densities=densities,
        metrics=metrics,
        baseline=baseline,
        final_analysis=final_analysis,
        stop_reason=stop_reason,
        density_history=density_history,
        load_case_names=[lc.name for lc in load_cases],
    )


def _apply_density_masks(config: BenchmarkConfig, mesh: StructuredMesh, densities: np.ndarray) -> np.ndarray:
    masked = np.asarray(densities, dtype=float).copy()
    masked[mesh.frozen_solid_mask] = 1.0
    masked[mesh.void_mask] = config.optimization.min_density
    return masked
