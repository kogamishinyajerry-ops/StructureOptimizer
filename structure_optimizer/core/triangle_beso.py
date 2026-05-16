"""Wave T: BESO topology optimization on triangle meshes.

Closes D013 留白 from v3.0 (BESO-on-triangle defer). Mirrors the
structured-quad BESO (``core/beso.py``) on unstructured triangle meshes
with one key adaptation: **area-weighted ranking**.

For structured quads, all elements have identical area, so ranking by raw
sensitivity is equivalent to ranking by sensitivity per unit area. On a
triangle mesh, element areas vary — keeping the top-N elements by raw
sensitivity does not satisfy the area-volume constraint. We instead:

1. Rank elements by sensitivity per unit area.
2. Walk down the ranked list, accumulating area, until target area is
   reached.
3. Promote those elements to solid; demote the rest to ``min_density``.

References:
- Huang & Xie (2010), *Evolutionary Topology Optimization of Continuum
  Structures*, Wiley §3.4 (unstructured meshes).
- Querin, Steven, Xie (2000), "Evolutionary structural optimisation
  using an additive algorithm", *Finite Elem. Anal. Des.* 34.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from structure_optimizer.adapters.solver_base import get_linear_solver
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.triangle import TriangleMesh, triangle_stiffness
from structure_optimizer.core.triangle_filter import centroid_density_filter


@dataclass(frozen=True)
class TriangleBesoIterationMetric:
    """Per-iteration record for triangle BESO."""

    iteration: int
    compliance: float
    volume_fraction: float
    change: float
    target_volume: float


@dataclass(frozen=True)
class TriangleBesoResult:
    """Result of ``run_beso_triangle``."""

    densities: np.ndarray
    metrics: list[TriangleBesoIterationMetric]
    baseline_compliance: float
    final_compliance: float
    final_displacements: np.ndarray
    stop_reason: str


def run_beso_triangle(
    mesh: TriangleMesh,
    *,
    young_modulus: float,
    poisson_ratio: float,
    fixed_dofs: np.ndarray,
    force: np.ndarray,
    volume_fraction: float = 0.4,
    er: float = 0.02,
    filter_radius: float = 1.5,
    min_density: float = 1e-3,
    max_iterations: int = 50,
    min_iterations: int = 5,
    change_tolerance: float = 0.01,
    thickness: float = 1.0,
    solver_backend: str = "dense",
) -> TriangleBesoResult:
    """BESO main loop on a triangle mesh.

    Algorithm (mirrors quad BESO with area weighting):
      1. Initialize all design elements solid (density 1).
      2. FEA → element strain energy sensitivities.
      3. Apply centroid-distance filter to smooth.
      4. Current target area = max(target_vol, current * (1 - er)) of
         design area.
      5. Rank design elements by (sensitivity / area); walk down the
         list accumulating area; threshold = sensitivity-per-area at
         which accumulated area = target.
      6. Promote above-threshold to 1, demote rest to min_density.
      7. Convergence: target reached AND change ≤ tolerance after
         min_iterations.

    Args mirror ``run_simp_triangle`` (Wave M).

    Returns:
        ``TriangleBesoResult``.

    Raises:
        SolverError: if all DOFs fixed.
        ValueError: if inputs inconsistent.
    """
    n_elem = mesh.n_elements
    densities = np.ones(n_elem, dtype=float)
    densities = _apply_masks(densities, mesh, min_density)

    # Precompute per-element stiffness + area (geometry fixed)
    element_kes: list[np.ndarray] = []
    element_areas: list[float] = []
    for eid in range(n_elem):
        coords = mesh.nodes[mesh.elements[eid]]
        ke, area = triangle_stiffness(young_modulus, poisson_ratio, coords, thickness)
        element_kes.append(ke)
        element_areas.append(area)
    areas = np.array(element_areas)

    assert mesh.design_mask is not None
    design_mask: np.ndarray = mesh.design_mask
    total_design_area = float(areas[design_mask].sum())

    # Baseline (all-solid)
    baseline = np.ones(n_elem, dtype=float)
    baseline = _apply_masks(baseline, mesh, min_density)
    baseline_result = _solve(mesh, element_kes, baseline, min_density, fixed_dofs, force, solver_backend)

    target_area_frac = volume_fraction
    current_area_frac = 1.0
    metrics: list[TriangleBesoIterationMetric] = []
    stop_reason = "max_iterations"
    final_result: dict[str, Any] = baseline_result

    for iteration in range(1, max_iterations + 1):
        previous = densities.copy()
        result = _solve(mesh, element_kes, densities, min_density, fixed_dofs, force, solver_backend)
        sensitivities = result["element_strain_energy"].copy()
        sensitivities[~design_mask] = 0.0
        sensitivities = centroid_density_filter(mesh, densities, sensitivities, filter_radius, min_density)

        current_area_frac = max(target_area_frac, current_area_frac * (1.0 - er))
        target_area = current_area_frac * total_design_area

        # Sensitivity-per-area ranking
        sens_per_area = sensitivities / np.maximum(areas, 1e-30)
        # Among design elements only
        idx_design = np.where(design_mask)[0]
        order = np.argsort(-sens_per_area[idx_design])  # descending
        ordered_idx = idx_design[order]
        cumulative_area = np.cumsum(areas[ordered_idx])
        # Find smallest k such that cumulative_area[k] >= target_area
        k = int(np.searchsorted(cumulative_area, target_area, side="left"))
        k = max(1, min(k + 1, ordered_idx.size))  # at least one solid
        keep_set = set(ordered_idx[:k].tolist())

        new_densities = densities.copy()
        for eid in idx_design:
            new_densities[eid] = 1.0 if int(eid) in keep_set else min_density
        new_densities = _apply_masks(new_densities, mesh, min_density)

        change = float(np.max(np.abs(new_densities - previous)))
        densities = new_densities

        active_vol = float(np.sum(densities[design_mask] * areas[design_mask]) / total_design_area)
        metrics.append(
            TriangleBesoIterationMetric(
                iteration=iteration,
                compliance=float(result["compliance"]),
                volume_fraction=active_vol,
                change=change,
                target_volume=current_area_frac,
            )
        )
        final_result = result

        target_reached = abs(current_area_frac - target_area_frac) < 1e-6
        if iteration >= min_iterations and target_reached and change <= change_tolerance:
            stop_reason = "change_tolerance"
            break

    final_result = _solve(mesh, element_kes, densities, min_density, fixed_dofs, force, solver_backend)
    return TriangleBesoResult(
        densities=densities,
        metrics=metrics,
        baseline_compliance=float(baseline_result["compliance"]),
        final_compliance=float(final_result["compliance"]),
        final_displacements=final_result["displacements"],
        stop_reason=stop_reason,
    )


def _apply_masks(densities: np.ndarray, mesh: TriangleMesh, min_density: float) -> np.ndarray:
    out = densities.copy()
    assert mesh.frozen_solid_mask is not None and mesh.void_mask is not None
    out[mesh.frozen_solid_mask] = 1.0
    out[mesh.void_mask] = min_density
    return out


def _solve(
    mesh: TriangleMesh,
    element_kes: list[np.ndarray],
    densities: np.ndarray,
    min_density: float,
    fixed_dofs: np.ndarray,
    force: np.ndarray,
    solver_backend: str,
) -> dict[str, Any]:
    """Assemble + solve K u = f for BESO (linear density scaling, not SIMP penalty).

    BESO uses binary densities so the SIMP penalty exponent does not apply;
    we scale stiffness linearly with density (which is min_density or 1).
    """
    linear_solver = get_linear_solver(solver_backend)
    density_scale = min_density + densities * (1.0 - min_density)
    if linear_solver.prefers_sparse:
        import scipy.sparse as sp

        n_elem = mesh.n_elements
        edofs_all = np.array([mesh.element_dofs(eid) for eid in range(n_elem)])
        rows = np.repeat(edofs_all, 6, axis=1).flatten()
        cols = np.tile(edofs_all, (1, 6)).flatten()
        vals_list = [(density_scale[eid] * element_kes[eid]).flatten() for eid in range(n_elem)]
        vals = np.concatenate(vals_list)
        stiffness: Any = sp.coo_matrix((vals, (rows, cols)), shape=(mesh.ndof, mesh.ndof)).tocsr()
    else:
        stiffness = np.zeros((mesh.ndof, mesh.ndof), dtype=float)
        for eid in range(mesh.n_elements):
            edofs = mesh.element_dofs(eid)
            stiffness[np.ix_(edofs, edofs)] += density_scale[eid] * element_kes[eid]

    ndof = mesh.ndof
    fixed = np.asarray(fixed_dofs, dtype=int)
    free = np.setdiff1d(np.arange(ndof), fixed)
    if free.size == 0:
        raise SolverError("all degrees of freedom are fixed")

    displacements = np.zeros(ndof, dtype=float)
    kff = stiffness.tocsr()[free, :][:, free] if linear_solver.prefers_sparse else stiffness[np.ix_(free, free)]
    ff = force[free]
    displacements[free] = linear_solver.solve(kff, ff)

    element_energy = np.zeros(mesh.n_elements, dtype=float)
    for eid in range(mesh.n_elements):
        edofs = mesh.element_dofs(eid)
        ue = displacements[edofs]
        element_energy[eid] = float(ue @ (element_kes[eid] @ ue))

    return {
        "displacements": displacements,
        "compliance": float(force @ displacements),
        "element_strain_energy": element_energy,
    }
