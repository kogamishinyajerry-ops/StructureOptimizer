"""v0.6 manufacturing constraints applied during SIMP optimization.

This module is the *pre-hoc* counterpart of ``manufacturability.py``:

- ``manufacturability.py`` runs after optimization and reports warnings.
- ``manufacturing.py`` runs *inside* the SIMP loop, projecting the density
  field to satisfy manufacturing constraints every iteration.

Projection semantics (current scope):

- **symmetry**: density is averaged with its mirror across an axis (``x`` = mirror
  across a vertical line, ``y`` = mirror across a horizontal line). The line
  position is normalized to [0, 1] of the corresponding mesh extent and defaults
  to 0.5.
- **extrusion**: density is averaged along a chosen axis, producing a field that
  is uniform along that axis. Useful for parts manufactured by extrusion or
  2.5D pull along the axis.
- **min_member_size**: not a projection; surfaced as a verification check that
  validates ``filter_radius`` (in cell units) is large enough to enforce the
  declared minimum feature length under the standard SIMP filter heuristic
  ``min_member_length ≈ 2 * filter_radius * cell_size``.

Frozen-solid / void masks are applied **after** projection, so design-space
constraints always win over manufacturing projection. If frozen / void regions
themselves break the declared symmetry/extrusion, the manufacturing-compliance
checks at the end will mark a residual; that is reported, not silenced.

Overhang projection (additive-manufacturing build direction support) is
deliberately out of scope for v0.6; tracked for v0.6.1+.
"""

from __future__ import annotations

import numpy as np

from structure_optimizer.core.config import (
    BenchmarkConfig,
    ExtrusionConstraintConfig,
    SymmetryConstraintConfig,
)
from structure_optimizer.core.mesh import StructuredMesh

SYMMETRY_TOLERANCE = 1e-3
EXTRUSION_TOLERANCE = 1e-3


def apply_manufacturing_projections(config: BenchmarkConfig, mesh: StructuredMesh, densities: np.ndarray) -> np.ndarray:
    """Apply every active manufacturing projection in deterministic order.

    Order: symmetry → extrusion. The order matters when both are declared:
    symmetry first establishes axial symmetry, then extrusion forces axial
    uniformity. If both are declared along the same axis the result is
    equivalent to extrusion alone.

    Returns a new array; input is not mutated.
    """
    constraints = config.manufacturing_constraints
    result = np.asarray(densities, dtype=float).copy()
    if constraints.symmetry is not None:
        result = apply_symmetry_projection(mesh, result, constraints.symmetry)
    if constraints.extrusion is not None:
        result = apply_extrusion_projection(mesh, result, constraints.extrusion)
    return result


def apply_symmetry_projection(
    mesh: StructuredMesh, densities: np.ndarray, symmetry: SymmetryConstraintConfig
) -> np.ndarray:
    """Mirror-average densities across the symmetry line.

    For ``axis='x'`` the line is vertical at ``x = position * width``; for
    ``axis='y'`` the line is horizontal at ``y = position * height``.

    Each element at grid index ``(ex, ey)`` is mapped to its mirror
    ``(ex_m, ey_m)``. The output density at both indices is the arithmetic mean
    of the two.

    Cells whose mirror falls outside the mesh (because the symmetry line is not
    at the midpoint) are left untouched — projection only acts where a paired
    cell exists.
    """
    grid = densities.reshape(mesh.nely, mesh.nelx).copy()
    nelx, nely = mesh.nelx, mesh.nely
    if symmetry.axis == "x":
        mirror_axis_x = symmetry.position * nelx - 0.5  # element-center coordinate of the line
        for ex in range(nelx):
            mirror_ex = round(2 * mirror_axis_x - ex)
            if 0 <= mirror_ex < nelx and mirror_ex != ex:
                averaged = 0.5 * (grid[:, ex] + grid[:, mirror_ex])
                grid[:, ex] = averaged
                grid[:, mirror_ex] = averaged
    else:  # axis == 'y'
        mirror_axis_y = symmetry.position * nely - 0.5
        for ey in range(nely):
            mirror_ey = round(2 * mirror_axis_y - ey)
            if 0 <= mirror_ey < nely and mirror_ey != ey:
                averaged = 0.5 * (grid[ey, :] + grid[mirror_ey, :])
                grid[ey, :] = averaged
                grid[mirror_ey, :] = averaged
    return grid.reshape(-1)


def apply_extrusion_projection(
    mesh: StructuredMesh, densities: np.ndarray, extrusion: ExtrusionConstraintConfig
) -> np.ndarray:
    """Average densities along the extrusion axis so the field is axis-uniform.

    For ``axis='x'`` every row collapses to its row-mean → field varies only with
    y. For ``axis='y'`` every column collapses to its column-mean → field varies
    only with x.
    """
    grid = densities.reshape(mesh.nely, mesh.nelx).copy()
    if extrusion.axis == "x":
        row_means = grid.mean(axis=1, keepdims=True)
        grid = np.broadcast_to(row_means, grid.shape).copy()
    else:  # axis == 'y'
        col_means = grid.mean(axis=0, keepdims=True)
        grid = np.broadcast_to(col_means, grid.shape).copy()
    return grid.reshape(-1)


def symmetry_residual(mesh: StructuredMesh, densities: np.ndarray, symmetry: SymmetryConstraintConfig) -> float:
    """Max absolute deviation from perfect mirror symmetry across the axis.

    Returns 0.0 if no paired cells exist (degenerate, position outside).
    """
    grid = densities.reshape(mesh.nely, mesh.nelx)
    nelx, nely = mesh.nelx, mesh.nely
    max_residual = 0.0
    if symmetry.axis == "x":
        mirror_axis_x = symmetry.position * nelx - 0.5
        for ex in range(nelx):
            mirror_ex = round(2 * mirror_axis_x - ex)
            if 0 <= mirror_ex < nelx and mirror_ex != ex:
                diff = float(np.max(np.abs(grid[:, ex] - grid[:, mirror_ex])))
                if diff > max_residual:
                    max_residual = diff
    else:
        mirror_axis_y = symmetry.position * nely - 0.5
        for ey in range(nely):
            mirror_ey = round(2 * mirror_axis_y - ey)
            if 0 <= mirror_ey < nely and mirror_ey != ey:
                diff = float(np.max(np.abs(grid[ey, :] - grid[mirror_ey, :])))
                if diff > max_residual:
                    max_residual = diff
    return max_residual


def extrusion_residual(mesh: StructuredMesh, densities: np.ndarray, extrusion: ExtrusionConstraintConfig) -> float:
    """Max absolute deviation from perfect axis-uniformity."""
    grid = densities.reshape(mesh.nely, mesh.nelx)
    if extrusion.axis == "x":
        row_means = grid.mean(axis=1, keepdims=True)
        return float(np.max(np.abs(grid - row_means)))
    col_means = grid.mean(axis=0, keepdims=True)
    return float(np.max(np.abs(grid - col_means)))


def min_member_size_compliance(config: BenchmarkConfig, mesh: StructuredMesh) -> dict[str, float | bool | str]:
    """Check whether the configured ``filter_radius`` is large enough to enforce
    the declared ``min_member_size`` under the standard SIMP filter heuristic
    ``min_member_length ≈ 2 * filter_radius * cell_size``.

    Returns ``{"status": "passed"/"warning"/"missing", ...}`` payload suitable
    for embedding in ``verification.json`` constraints.
    """
    constraints = config.manufacturing_constraints
    if constraints.min_member_size is None:
        return {"status": "missing", "rule": "min_member_size_not_declared"}

    cell_size = max(mesh.width / mesh.nelx, mesh.height / mesh.nely)
    enforced_length = 2.0 * config.optimization.filter_radius * cell_size
    target = float(constraints.min_member_size)
    status = "passed" if enforced_length >= target else "warning"
    return {
        "status": status,
        "rule": "filter_radius_vs_min_member_size",
        "min_member_size": target,
        "enforced_length": enforced_length,
        "cell_size": cell_size,
        "filter_radius_cells": config.optimization.filter_radius,
    }


def evaluate_manufacturing_compliance(
    config: BenchmarkConfig, mesh: StructuredMesh, densities: np.ndarray
) -> dict[str, dict[str, float | bool | str]]:
    """Build a status report for all declared manufacturing constraints.

    Returns a dict keyed by constraint name. Each entry has at least ``status``
    ∈ ``{"passed", "warning", "missing"}``.
    """
    constraints = config.manufacturing_constraints
    report: dict[str, dict[str, float | bool | str]] = {}

    if constraints.symmetry is not None:
        residual = symmetry_residual(mesh, densities, constraints.symmetry)
        report["symmetry_compliance"] = {
            "status": "passed" if residual <= SYMMETRY_TOLERANCE else "warning",
            "rule": "max_mirror_residual",
            "axis": constraints.symmetry.axis,
            "position": constraints.symmetry.position,
            "residual": residual,
            "tolerance": SYMMETRY_TOLERANCE,
        }
    else:
        report["symmetry_compliance"] = {"status": "missing", "rule": "symmetry_not_declared"}

    if constraints.extrusion is not None:
        residual = extrusion_residual(mesh, densities, constraints.extrusion)
        report["extrusion_compliance"] = {
            "status": "passed" if residual <= EXTRUSION_TOLERANCE else "warning",
            "rule": "max_axis_uniformity_residual",
            "axis": constraints.extrusion.axis,
            "residual": residual,
            "tolerance": EXTRUSION_TOLERANCE,
        }
    else:
        report["extrusion_compliance"] = {"status": "missing", "rule": "extrusion_not_declared"}

    report["min_member_size_compliance"] = min_member_size_compliance(config, mesh)
    return report
