"""Wave Y: thermal-compliance SIMP driver (v5 multi-physics).

Minimises thermal compliance ``T^T · K(ρ) · T`` subject to a volume-fraction
constraint, where K is the conductivity matrix from `core.thermal`. The
sensitivity is symmetric to elastic compliance:

    dC/dρ_e = -p · ρ_e^(p-1) · (1 - ρ_min) · T_e^T · Ke · T_e

Classic optimality-criteria update + Bendsøe density filter are reused
verbatim from `core.simp` / `core.filtering`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.filtering import density_filter
from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.core.simp import _apply_density_masks, _optimality_criteria_update
from structure_optimizer.core.thermal import ThermalResult, solve_thermal


@dataclass
class ThermalIterationMetric:
    iteration: int
    thermal_compliance: float
    max_temperature: float
    volume_fraction: float
    max_density_change: float


@dataclass
class ThermalOptimizationResult:
    densities: np.ndarray
    final_result: ThermalResult
    metrics: list[ThermalIterationMetric]
    converged: bool
    mesh_shape: tuple[int, int]


def _deep_merge(dst: dict, src: dict) -> dict:
    for k, v in src.items():
        if k in dst and isinstance(dst[k], dict) and isinstance(v, dict):
            dst[k] = _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def load_thermal_benchmark(
    name: str, preset: str | None = None
) -> tuple[BenchmarkConfig, float, list[dict[str, Any]], list[dict[str, Any]]]:
    """Load a benchmark + extract its ``thermal`` block (conductivity, sources, BCs).

    The ``thermal`` block lives in the raw JSON and is *not* parsed by
    ``parse_config`` (preserving v1-v4 schema). This helper reads the raw
    JSON, applies the preset, and returns the typed config plus the
    thermal-specific extras.

    Returns:
        (config, conductivity, heat_sources, thermal_bcs)
    """
    from structure_optimizer.benchmarks.registry import config_path
    from structure_optimizer.core.config import parse_config, validate_config

    raw = json.loads(Path(config_path(name)).read_text())
    presets = raw.pop("presets", {})
    if preset:
        if preset not in presets:
            raise ValueError(f"Unknown preset '{preset}' for benchmark '{name}'")
        raw = _deep_merge(raw, presets[preset])
    thermal_block = raw.pop("thermal", {})
    if not thermal_block:
        raise ValueError(f"benchmark '{name}' has no 'thermal' block")
    config = parse_config(raw, source_path=str(config_path(name)))
    validate_config(config)
    return (
        config,
        float(thermal_block.get("conductivity", 1.0)),
        list(thermal_block.get("heat_sources", [])),
        list(thermal_block.get("thermal_bcs", [])),
    )


def _default_initial_density(config: BenchmarkConfig, mesh: StructuredMesh) -> np.ndarray:
    """Mirror of `simp._default_initial_density` for thermal optimisation."""
    rho0 = np.full(mesh.elements.shape[0], config.optimization.volume_fraction)
    return _apply_density_masks(config, mesh, rho0)


def run_thermal_simp(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    conductivity: float,
    heat_sources: list[dict],
    thermal_bcs: list[dict],
) -> ThermalOptimizationResult:
    """SIMP min-thermal-compliance driver.

    Args:
        config:        BenchmarkConfig (uses optimization.* + thickness)
        mesh:          structured quad mesh
        conductivity:  scalar material thermal conductivity
        heat_sources:  list of ``{"selector", "q"}`` records
        thermal_bcs:   list of ``{"selector", "temperature"}`` records

    Returns:
        ThermalOptimizationResult with density history + iteration metrics
    """
    opt = config.optimization
    densities = _default_initial_density(config, mesh)
    metrics: list[ThermalIterationMetric] = []
    converged = False
    prev = densities.copy()

    for it in range(opt.max_iterations):
        result = solve_thermal(
            config,
            mesh,
            densities,
            conductivity=conductivity,
            heat_sources=heat_sources,
            thermal_bcs=thermal_bcs,
        )

        active_density = np.where(mesh.void_mask, opt.min_density, densities)
        p = opt.penalty
        # SIMP sensitivity: dC/dρ_e = -p · ρ_e^(p-1) · (1 - ρ_min) · elem_energy
        sens = -p * np.power(active_density, p - 1.0) * (1.0 - opt.min_density) * result.element_thermal_energy

        # Bendsøe density filter (sensitivity-based) — share with elastic path
        sens = density_filter(mesh, densities, sens, opt.filter_radius, opt.min_density)

        new = _optimality_criteria_update(config, mesh, densities, sens)
        new = _apply_density_masks(config, mesh, new)

        change = float(np.max(np.abs(new - prev)))
        vol = float(np.mean(new))
        metrics.append(
            ThermalIterationMetric(
                iteration=it,
                thermal_compliance=result.thermal_compliance,
                max_temperature=result.max_temperature,
                volume_fraction=vol,
                max_density_change=change,
            )
        )

        prev = densities.copy()
        densities = new

        if it >= opt.min_iterations and change < opt.change_tolerance:
            converged = True
            break

    final = solve_thermal(
        config,
        mesh,
        densities,
        conductivity=conductivity,
        heat_sources=heat_sources,
        thermal_bcs=thermal_bcs,
    )

    return ThermalOptimizationResult(
        densities=densities,
        final_result=final,
        metrics=metrics,
        converged=converged,
        mesh_shape=(mesh.nelx, mesh.nely),
    )


def anisotropic_thermal_sensitivity(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    conductivity_tensor: np.ndarray | None = None,
    heat_sources: list[dict[str, Any]] | None = None,
    thermal_bcs: list[dict[str, Any]] | None = None,
    conductivity_tensor_field: np.ndarray | None = None,
) -> np.ndarray:
    """Anisotropic thermal SIMP compliance sensitivity dC/dρ_e (Wave NN, D043).

    The thermal problem K(ρ)·T = q is self-adjoint, so for thermal compliance
    C = qᵀT = TᵀK T the sensitivity is

        dC/dρ_e = -p · ρ_e^(p-1) · (1 - ρ_min) · (Tₑᵀ ke_e Tₑ),

    identical in form to the scalar case (``run_thermal_simp``) — the only change
    is that ``ke_e`` (and hence ``element_thermal_energy``) carries the
    anisotropic tensor / per-element field. Pass either a global
    ``conductivity_tensor`` or a per-element ``conductivity_tensor_field``.
    """
    densities = np.asarray(densities, dtype=float).reshape(-1)
    result = solve_thermal(
        config, mesh, densities, conductivity=1.0,
        heat_sources=heat_sources, thermal_bcs=thermal_bcs,
        conductivity_tensor=conductivity_tensor,
        conductivity_tensor_field=conductivity_tensor_field,
    )
    opt = config.optimization
    active = np.where(mesh.void_mask, opt.min_density, densities)
    p = opt.penalty
    return -p * np.power(active, p - 1.0) * (1.0 - opt.min_density) * result.element_thermal_energy
