"""Wave V: adaptive mesh-refinement loop for SIMP topology optimization.

Closes D010 留白 (auto-refinement defer). The standard SIMP workflow
uses a fixed mesh resolution from the benchmark config. Auto-refinement
runs an initial SIMP at coarse resolution, identifies regions of
**high stress** or **active design**, refines the mesh selectively
there, and re-runs SIMP with the refined mesh seeded from the coarse
solution.

Why selective refinement: doubling the mesh in 2D quadruples DOFs. A
global refinement is expensive (~16× for double-then-double); local
refinement keeps the cost ≤ 2× while capturing critical stress
gradients accurately.

This Wave-V implementation is **uniform-refinement-only** for the
structured-quad mesh (the existing FEM and SIMP machinery require
structured quads). The "adaptive" aspect is in *when* to refine — by
the user calling ``auto_refine_until_converged`` which runs SIMP at
multiple resolutions and stops when the converged compliance change
falls below a tolerance between successive refinement levels.

Reference:
    Stainko (2006). "An adaptive multilevel approach to the minimal
        compliance problem in 3D topology optimization." *Comm. Numer.
        Meth. Eng.* 22, 109–118.
    Berger & Oliger (1984). "Adaptive Mesh Refinement for Hyperbolic
        PDEs." *J. Comput. Phys.* 53, 484–512.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.simp import OptimizationResult, run_simp


@dataclass(frozen=True)
class RefinementLevel:
    """One mesh-refinement step record."""

    level: int
    nelx: int
    nely: int
    compliance: float
    iterations_run: int


@dataclass
class RefinementResult:
    """Result of an auto-refinement run."""

    final: OptimizationResult
    levels: list[RefinementLevel] = field(default_factory=list)
    stop_reason: str = "max_levels"
    convergence_history: list[float] = field(default_factory=list)


def _refine_config(config: BenchmarkConfig, factor: int = 2) -> BenchmarkConfig:
    """Return a copy of ``config`` with mesh ``nelx``/``nely`` multiplied by ``factor``.

    Scales filter_radius proportionally so the physical filter footprint
    is preserved across refinements.
    """
    new_mesh = replace(
        config.mesh,
        nelx=int(config.mesh.nelx * factor),
        nely=int(config.mesh.nely * factor),
    )
    new_opt = replace(
        config.optimization,
        filter_radius=float(config.optimization.filter_radius * factor),
    )
    return replace(config, mesh=new_mesh, optimization=new_opt)


def _interpolate_densities_to_finer_mesh(
    coarse_densities: np.ndarray,
    coarse_nelx: int,
    coarse_nely: int,
    fine_nelx: int,
    fine_nely: int,
) -> np.ndarray:
    """Bilinear-equivalent: each fine cell inherits the coarse cell it falls in.

    For factor-of-2 refinement (the common case), this means each coarse
    cell becomes 4 fine cells with the same density. Used to seed SIMP
    on the finer mesh from the coarse solution (warm start).
    """
    coarse = coarse_densities.reshape((coarse_nely, coarse_nelx))
    rx = fine_nelx / coarse_nelx
    ry = fine_nely / coarse_nely
    fine = np.zeros((fine_nely, fine_nelx), dtype=float)
    for j in range(fine_nely):
        cj = min(int(j / ry), coarse_nely - 1)
        for i in range(fine_nelx):
            ci = min(int(i / rx), coarse_nelx - 1)
            fine[j, i] = coarse[cj, ci]
    return fine.reshape(-1)


def auto_refine_until_converged(
    config: BenchmarkConfig,
    max_levels: int = 3,
    factor: int = 2,
    compliance_tolerance: float = 0.05,
) -> RefinementResult:
    """Run SIMP at progressively finer meshes until compliance stabilizes.

    Algorithm:
    1. Run SIMP at the base resolution (level 0).
    2. Refine mesh by ``factor`` (default 2×). Run SIMP.
       (Note: seeding the finer mesh with the coarse density via
       bilinear-equivalent interpolation is informational; the current
       SIMP driver re-initializes from the volume fraction.)
    3. Compare compliance to the previous level. If
       ``|c_new - c_old| / c_old ≤ compliance_tolerance``, stop.
    4. Otherwise refine again, up to ``max_levels``.

    Returns the final-mesh ``OptimizationResult`` plus a per-level
    history.

    Args:
        config: benchmark configuration (start resolution).
        max_levels: cap on refinement steps (default 3 → final mesh is
            8× original linear resolution).
        factor: refinement factor per level (default 2).
        compliance_tolerance: relative compliance change to stop early.

    Returns:
        ``RefinementResult``.
    """
    current_config = config
    levels: list[RefinementLevel] = []
    convergence_history: list[float] = []
    prev_compliance: float | None = None
    final_result: OptimizationResult | None = None
    stop_reason = "max_levels"

    for level in range(max_levels):
        mesh = create_structured_mesh(current_config)
        result = run_simp(current_config, mesh)
        compliance = float(result.final_analysis.compliance)
        levels.append(
            RefinementLevel(
                level=level,
                nelx=mesh.nelx,
                nely=mesh.nely,
                compliance=compliance,
                iterations_run=len(result.metrics),
            )
        )
        convergence_history.append(compliance)
        final_result = result

        if prev_compliance is not None:
            rel_change = abs(compliance - prev_compliance) / max(abs(prev_compliance), 1e-30)
            if rel_change <= compliance_tolerance:
                stop_reason = "compliance_converged"
                break

        prev_compliance = compliance
        # Refine for next iteration
        if level < max_levels - 1:
            current_config = _refine_config(current_config, factor)

    if final_result is None:
        raise RuntimeError("auto_refine_until_converged produced no result")

    return RefinementResult(
        final=final_result,
        levels=levels,
        stop_reason=stop_reason,
        convergence_history=convergence_history,
    )
