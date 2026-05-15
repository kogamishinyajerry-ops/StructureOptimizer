from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig, LoadCaseConfig, effective_load_cases
from structure_optimizer.core.fem2d import FEMResult, solve_linear_elastic
from structure_optimizer.core.filtering import density_filter
from structure_optimizer.core.mesh import StructuredMesh


@dataclass(frozen=True)
class IterationMetric:
    iteration: int
    compliance: float
    volume_fraction: float
    change: float
    max_displacement: float
    mass: float


@dataclass(frozen=True)
class OptimizationResult:
    densities: np.ndarray
    metrics: list[IterationMetric]
    baseline: FEMResult
    final_analysis: FEMResult
    stop_reason: str
    density_history: list[np.ndarray]
    load_case_names: list[str]


def run_simp(config: BenchmarkConfig, mesh: StructuredMesh) -> OptimizationResult:
    opt = config.optimization
    load_cases = effective_load_cases(config)
    densities = np.full(mesh.elements.shape[0], opt.volume_fraction, dtype=float)
    densities = _apply_density_masks(config, mesh, densities)
    baseline_densities = np.ones(mesh.elements.shape[0], dtype=float)
    baseline_densities = _apply_density_masks(config, mesh, baseline_densities)
    baseline = _solve_weighted_load_cases(config, mesh, baseline_densities, load_cases)

    metrics: list[IterationMetric] = []
    density_history: list[np.ndarray] = [densities.copy()]
    stop_reason = "max_iterations"
    final_analysis = baseline
    design_count = max(1, int(np.count_nonzero(mesh.design_mask)))

    for iteration in range(1, opt.max_iterations + 1):
        previous = densities.copy()
        analysis = _solve_weighted_load_cases(config, mesh, densities, load_cases)
        sensitivities = -opt.penalty * (densities ** (opt.penalty - 1.0)) * analysis.element_strain_energy
        sensitivities[~mesh.design_mask] = 0.0
        sensitivities = density_filter(mesh, densities, sensitivities, opt.filter_radius, opt.min_density)
        densities = _optimality_criteria_update(config, mesh, densities, sensitivities)
        densities = _apply_density_masks(config, mesh, densities)
        density_history.append(densities.copy())
        change = float(np.max(np.abs(densities - previous)))
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
        if iteration >= opt.min_iterations and change <= opt.change_tolerance:
            stop_reason = "change_tolerance"
            break

    final_analysis = _solve_weighted_load_cases(config, mesh, densities, load_cases)
    return OptimizationResult(
        densities=densities,
        metrics=metrics,
        baseline=baseline,
        final_analysis=final_analysis,
        stop_reason=stop_reason,
        density_history=density_history,
        load_case_names=[load_case.name for load_case in load_cases],
    )


def _apply_density_masks(config: BenchmarkConfig, mesh: StructuredMesh, densities: np.ndarray) -> np.ndarray:
    masked = np.asarray(densities, dtype=float).copy()
    masked[mesh.frozen_solid_mask] = 1.0
    masked[mesh.void_mask] = config.optimization.min_density
    return masked


def _solve_weighted_load_cases(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    load_cases: list[LoadCaseConfig],
) -> FEMResult:
    weighted_energy = np.zeros(mesh.elements.shape[0], dtype=float)
    weighted_compliance = 0.0
    max_displacement = 0.0
    max_stress = 0.0
    first_result: FEMResult | None = None
    total_weight = sum(load_case.weight for load_case in load_cases)

    for load_case in load_cases:
        result = solve_linear_elastic(config, mesh, densities, loads=load_case.loads)
        weight = load_case.weight / total_weight
        weighted_energy += weight * result.element_strain_energy
        weighted_compliance += weight * result.compliance
        max_displacement = max(max_displacement, result.max_displacement)
        max_stress = max(max_stress, result.max_stress)
        if first_result is None:
            first_result = result

    assert first_result is not None
    return FEMResult(
        displacements=first_result.displacements,
        compliance=float(weighted_compliance),
        max_displacement=float(max_displacement),
        max_stress=float(max_stress),
        mass=first_result.mass,
        element_strain_energy=weighted_energy,
    )


def _optimality_criteria_update(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    sensitivities: np.ndarray,
) -> np.ndarray:
    opt = config.optimization
    move = 0.2
    l1 = 0.0
    l2 = 1e9
    active = mesh.design_mask
    design_count = max(1, int(np.count_nonzero(active)))
    updated = densities.copy()
    dv = np.ones_like(densities)

    # Bisection enforces the volume target on active design elements.
    for _ in range(80):
        midpoint = 0.5 * (l1 + l2)
        candidate = densities.copy()
        ratio = np.maximum(1e-12, -sensitivities / (dv * midpoint))
        candidate[active] = np.maximum(
            opt.min_density,
            np.maximum(
                densities[active] - move,
                np.minimum(1.0, np.minimum(densities[active] + move, densities[active] * np.sqrt(ratio[active]))),
            ),
        )
        if np.sum(candidate[active]) / design_count > opt.volume_fraction:
            l1 = midpoint
        else:
            l2 = midpoint
            updated = candidate
        if (l2 - l1) / max(1.0, l1 + l2) < 1e-4:
            break
    return np.clip(updated, opt.min_density, 1.0)
