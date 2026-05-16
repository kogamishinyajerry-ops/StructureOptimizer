from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from structure_optimizer.adapters.solver_base import get_linear_solver
from structure_optimizer.core.config import BenchmarkConfig, effective_load_cases
from structure_optimizer.core.fem2d import (
    FEMResult,
    build_sparse_assembly_template,
    element_stiffness,
)
from structure_optimizer.core.filtering import density_filter
from structure_optimizer.core.manufacturing import apply_manufacturing_projections
from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.core.objectives import solve_and_aggregate


@dataclass(frozen=True)
class IterationMetric:
    """Per-iteration SIMP record: compliance, volume fraction, density change, max disp, mass."""

    iteration: int
    compliance: float
    volume_fraction: float
    change: float
    max_displacement: float
    mass: float


@dataclass(frozen=True)
class OptimizationResult:
    """Result of a SIMP optimization run: final density + per-iter metrics + baseline/final FEA."""

    densities: np.ndarray
    metrics: list[IterationMetric]
    baseline: FEMResult
    final_analysis: FEMResult
    stop_reason: str
    density_history: list[np.ndarray]
    load_case_names: list[str]
    mesh_shape: tuple[int, int] = (0, 0)
    """(nelx, nely) of the mesh that produced this result.

    Wave Q only — used by ``_repr_png_`` to reshape ``densities``. Defaults
    to (0, 0) for backwards compatibility with any caller that constructs
    ``OptimizationResult`` directly without passing a mesh; PNG output is
    suppressed in that case but the table-form ``_repr_html_`` still works.
    """

    def _repr_html_(self) -> str:
        """Jupyter / VS Code Notebook rich display."""
        from structure_optimizer.core.repr_html import optimization_result_repr_html

        return optimization_result_repr_html(self)

    def _repr_png_(self) -> bytes | None:
        """Inline PNG of the final density field. Returns None if mesh_shape is unknown."""
        nelx, nely = self.mesh_shape
        if nelx <= 0 or nely <= 0:
            return None
        from structure_optimizer.core.repr_html import _grayscale_png_bytes

        grid = np.asarray(self.densities, dtype=float).reshape((nely, nelx))
        pixels = np.clip((1.0 - grid) * 255.0, 0, 255).astype(np.uint8)
        scale = max(1, 320 // max(nelx, nely))
        if scale > 1:
            pixels = np.repeat(np.repeat(pixels, scale, axis=0), scale, axis=1)
        return _grayscale_png_bytes(pixels)


def run_simp(config: BenchmarkConfig, mesh: StructuredMesh) -> OptimizationResult:
    """Run the SIMP main loop: density init → FEA → sensitivity → filter → OC update → manufacturing projection → repeat.

    Stops when ``change <= change_tolerance`` (after ``min_iterations``) or
    ``max_iterations`` is reached. Returns ``OptimizationResult`` with the final
    density field, full iteration history, and pre/post-optimization FEA results.
    """
    opt = config.optimization
    load_cases = effective_load_cases(config)
    densities = np.full(mesh.elements.shape[0], opt.volume_fraction, dtype=float)
    densities = _apply_density_masks(config, mesh, densities)
    baseline_densities = np.ones(mesh.elements.shape[0], dtype=float)
    baseline_densities = _apply_density_masks(config, mesh, baseline_densities)
    aggregator = opt.case_aggregator

    # Wave N: build sparse-assembly template once for the whole loop when the
    # solver prefers sparse. Skipped for dense backends (template is cheap to
    # rebuild but adds no value when assembly is dense).
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
    stop_reason = "max_iterations"
    final_analysis = baseline
    design_count = max(1, int(np.count_nonzero(mesh.design_mask)))

    use_stress_adjoint = config.stress_constraint.enabled and opt.stress_penalty > 0
    for iteration in range(1, opt.max_iterations + 1):
        previous = densities.copy()
        analysis = solve_and_aggregate(config, mesh, densities, load_cases, aggregator, sparse_template=sparse_template)
        sensitivities = -opt.penalty * (densities ** (opt.penalty - 1.0)) * analysis.element_strain_energy
        sensitivities[~mesh.design_mask] = 0.0
        if use_stress_adjoint:
            from structure_optimizer.core.adjoint import adjoint_stress_sensitivity

            sigma_pn, stress_sens, _ = adjoint_stress_sensitivity(config, mesh, densities, analysis.displacements)
            violation_ratio = max(0.0, sigma_pn / config.stress_constraint.limit - 1.0)
            if violation_ratio > 0.0:
                # Normalize stress sensitivity to same magnitude scale as compliance
                # sensitivity (Le et al. 2010 recipe). Otherwise large-magnitude
                # stress gradients overwhelm OC's bisection range.
                comp_scale = float(np.mean(np.abs(sensitivities[mesh.design_mask])))
                stress_scale = float(np.mean(np.abs(stress_sens[mesh.design_mask])))
                if stress_scale > 0:
                    stress_sens_scaled = stress_sens * (comp_scale / stress_scale)
                    sensitivities = sensitivities + opt.stress_penalty * violation_ratio * stress_sens_scaled
                    sensitivities[~mesh.design_mask] = 0.0
        sensitivities = density_filter(mesh, densities, sensitivities, opt.filter_radius, opt.min_density)
        densities = _optimality_criteria_update(config, mesh, densities, sensitivities)
        densities = apply_manufacturing_projections(config, mesh, densities)
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

    final_analysis = solve_and_aggregate(
        config, mesh, densities, load_cases, aggregator, sparse_template=sparse_template
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


def _apply_density_masks(config: BenchmarkConfig, mesh: StructuredMesh, densities: np.ndarray) -> np.ndarray:
    masked = np.asarray(densities, dtype=float).copy()
    masked[mesh.frozen_solid_mask] = 1.0
    masked[mesh.void_mask] = config.optimization.min_density
    return masked


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
