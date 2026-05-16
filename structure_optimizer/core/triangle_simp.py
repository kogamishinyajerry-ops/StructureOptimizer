"""Wave M: SIMP topology optimization on triangle meshes.

Fills the D005 留白 from v1.9: ``triangle.py`` had CST stiffness + linear
elastic solve but no SIMP main loop. This module mirrors
``core/simp.py`` (quad path) on unstructured triangle meshes via:

- per-element stiffness reused across iterations (geometry doesn't change)
- centroid-distance density filter (``core/triangle_filter.py``)
- optimality-criteria bisection identical in form to the quad path
- design / frozen-solid / void masks from ``TriangleMesh``

The simpler-than-quad pieces: no manufacturing projections (overhang etc.
are inherently grid-aligned; D005 explicitly defers them); no stress
adjoint yet (the Wave-L adjoint is quad-only by construction — see
deferred section in D008).
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
class TriangleIterationMetric:
    """Per-iteration record for triangle SIMP."""

    iteration: int
    compliance: float
    volume_fraction: float
    change: float
    max_displacement: float


@dataclass(frozen=True)
class TriangleOptimizationResult:
    """Result of ``run_simp_triangle``."""

    densities: np.ndarray
    metrics: list[TriangleIterationMetric]
    baseline_compliance: float
    final_compliance: float
    final_displacements: np.ndarray
    stop_reason: str

    def _repr_html_(self) -> str:
        """Jupyter / VS Code Notebook rich display."""
        from structure_optimizer.core.repr_html import triangle_optimization_result_repr_html

        return triangle_optimization_result_repr_html(self)


def run_simp_triangle(
    mesh: TriangleMesh,
    *,
    young_modulus: float,
    poisson_ratio: float,
    fixed_dofs: np.ndarray,
    force: np.ndarray,
    volume_fraction: float = 0.4,
    penalty: float = 3.0,
    filter_radius: float = 1.5,
    min_density: float = 1e-3,
    max_iterations: int = 50,
    min_iterations: int = 5,
    change_tolerance: float = 0.01,
    thickness: float = 1.0,
    solver_backend: str = "dense",
) -> TriangleOptimizationResult:
    """SIMP main loop on a triangle mesh.

    Mirrors ``core/simp.run_simp`` (quad path) with these adaptations:

    - Element stiffnesses precomputed once (CST geometry is static).
    - Density filter uses ``centroid_density_filter`` (no grid neighbors).
    - Bisection OC identical in form.

    Args:
        mesh: triangle mesh (must have design_mask populated; defaults to
              all-design via ``TriangleMesh.__post_init__``).
        young_modulus, poisson_ratio: material.
        fixed_dofs: 1d int array of constrained DOFs.
        force: ndof-length force vector.
        volume_fraction, penalty, filter_radius, min_density,
        max_iterations, min_iterations, change_tolerance, thickness,
        solver_backend: SIMP knobs (defaults match quad path conventions).

    Returns:
        ``TriangleOptimizationResult`` with densities + per-iter metrics
        + baseline (all-solid) and final compliance.

    Raises:
        SolverError: if all DOFs fixed.
        ValueError: if mesh / arrays inconsistent.
    """
    n_elem = mesh.n_elements
    densities = np.full(n_elem, volume_fraction, dtype=float)
    densities = _apply_masks(densities, mesh, min_density)

    # Precompute per-element stiffness + area (geometry fixed)
    element_kes: list[np.ndarray] = []
    element_areas: list[float] = []
    for eid in range(n_elem):
        coords = mesh.nodes[mesh.elements[eid]]
        ke, area = triangle_stiffness(young_modulus, poisson_ratio, coords, thickness)
        element_kes.append(ke)
        element_areas.append(area)

    # Baseline: all-solid (after masks)
    baseline = np.ones(n_elem, dtype=float)
    baseline = _apply_masks(baseline, mesh, min_density)
    baseline_result = _solve(mesh, element_kes, baseline, penalty, min_density, fixed_dofs, force, solver_backend)

    assert mesh.design_mask is not None  # populated by __post_init__
    design_mask: np.ndarray = mesh.design_mask
    areas = np.array(element_areas)
    total_design_area = float(areas[design_mask].sum())

    metrics: list[TriangleIterationMetric] = []
    stop_reason = "max_iterations"
    final_result: dict[str, Any] = baseline_result

    for iteration in range(1, max_iterations + 1):
        previous = densities.copy()
        result = _solve(mesh, element_kes, densities, penalty, min_density, fixed_dofs, force, solver_backend)
        compliance_sens = (
            -penalty * (densities ** (penalty - 1.0)) * (1.0 - min_density) * result["element_strain_energy"]
        )
        compliance_sens[~design_mask] = 0.0
        filtered = centroid_density_filter(mesh, densities, compliance_sens, filter_radius, min_density)
        densities = _oc_update(
            densities, filtered, mesh, areas, design_mask, total_design_area, volume_fraction, min_density
        )
        densities = _apply_masks(densities, mesh, min_density)

        change = float(np.max(np.abs(densities - previous)))
        active_vol = float(np.sum(densities[design_mask] * areas[design_mask]) / total_design_area)
        disp_pairs = result["displacements"].reshape((-1, 2))
        max_disp = float(np.max(np.linalg.norm(disp_pairs, axis=1)))
        metrics.append(
            TriangleIterationMetric(
                iteration=iteration,
                compliance=float(result["compliance"]),
                volume_fraction=active_vol,
                change=change,
                max_displacement=max_disp,
            )
        )
        final_result = result
        if iteration >= min_iterations and change <= change_tolerance:
            stop_reason = "change_tolerance"
            break

    final_result = _solve(mesh, element_kes, densities, penalty, min_density, fixed_dofs, force, solver_backend)
    return TriangleOptimizationResult(
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
    penalty: float,
    min_density: float,
    fixed_dofs: np.ndarray,
    force: np.ndarray,
    solver_backend: str,
) -> dict[str, Any]:
    linear_solver = get_linear_solver(solver_backend)
    density_scale = min_density + (densities**penalty) * (1.0 - min_density)
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


def _oc_update(
    densities: np.ndarray,
    sensitivities: np.ndarray,
    mesh: TriangleMesh,
    areas: np.ndarray,
    design_mask: np.ndarray,
    total_design_area: float,
    volume_fraction: float,
    min_density: float,
) -> np.ndarray:
    """Area-weighted bisection OC update for triangle meshes.

    Mirrors the quad path but weights the volume constraint by element area
    (triangles are unequal-area). Identical in spirit to Bendsøe-Sigmund
    bisection.
    """
    move = 0.2
    l1 = 0.0
    l2 = 1e9
    dv = np.ones_like(densities)
    updated = densities.copy()
    target_area = volume_fraction * total_design_area

    for _ in range(80):
        midpoint = 0.5 * (l1 + l2)
        ratio = np.maximum(1e-12, -sensitivities / (dv * midpoint))
        candidate = densities.copy()
        candidate[design_mask] = np.maximum(
            min_density,
            np.maximum(
                densities[design_mask] - move,
                np.minimum(
                    1.0,
                    np.minimum(
                        densities[design_mask] + move,
                        densities[design_mask] * np.sqrt(ratio[design_mask]),
                    ),
                ),
            ),
        )
        active_area = float(np.sum(candidate[design_mask] * areas[design_mask]))
        if active_area > target_area:
            l1 = midpoint
        else:
            l2 = midpoint
            updated = candidate
        if (l2 - l1) / max(1.0, l1 + l2) < 1e-4:
            break
    return np.clip(updated, min_density, 1.0)


def split_quad_to_triangles(
    nelx: int,
    nely: int,
    width: float = 1.0,
    height: float = 1.0,
) -> TriangleMesh:
    """Build a triangle mesh by splitting each quad of a structured grid
    into 2 triangles (lower-left + upper-right). Used in Wave M tests
    to verify quad-vs-triangle SIMP equivalence on the same domain."""
    n_nodes_x = nelx + 1
    n_nodes_y = nely + 1
    nodes = np.array(
        [(width * i / nelx, height * j / nely) for j in range(n_nodes_y) for i in range(n_nodes_x)],
        dtype=float,
    )
    triangles = []
    for j in range(nely):
        for i in range(nelx):
            n1 = j * n_nodes_x + i
            n2 = n1 + 1
            n4 = n1 + n_nodes_x
            n3 = n4 + 1
            # Lower-left triangle (n1, n2, n4) and upper-right (n2, n3, n4) — CCW
            triangles.append((n1, n2, n4))
            triangles.append((n2, n3, n4))
    return TriangleMesh(nodes=nodes, elements=np.array(triangles, dtype=int))
