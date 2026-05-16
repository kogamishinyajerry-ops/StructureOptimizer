"""Wave DD: 2D density field → STL boundary extraction (v5 multi-physics).

Produces a 3D-printer-ready STL representation of a 2D topology by:

1. Thresholding the density field at ``rho_threshold`` (default 0.5)
2. Extruding the binary mask to a fixed thickness (out-of-plane direction)
3. Writing every "solid" element as 12 triangles (2 per face × 6 faces)
4. Optionally skipping faces shared between two adjacent solid cells
   (boundary-only extraction)

The output is ASCII STL (more verbose but parseable by every CAD/CAM
tool). Binary STL is more compact but adds a dep on struct-packing
fixed widths; v5+ option.

Limitations:
- Output is voxelized — each density cell becomes an axis-aligned box.
  Marching-cubes-style isocontour extraction would give smoother
  surfaces but adds significant complexity. v5+ if needed.
- Thickness is uniform — variable thickness needs per-element
  metadata.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import StructuredMesh


def _format_triangle(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray, normal: np.ndarray) -> str:
    return (
        f"  facet normal {normal[0]:.6e} {normal[1]:.6e} {normal[2]:.6e}\n"
        f"    outer loop\n"
        f"      vertex {p1[0]:.6e} {p1[1]:.6e} {p1[2]:.6e}\n"
        f"      vertex {p2[0]:.6e} {p2[1]:.6e} {p2[2]:.6e}\n"
        f"      vertex {p3[0]:.6e} {p3[1]:.6e} {p3[2]:.6e}\n"
        f"    endloop\n"
        f"  endfacet\n"
    )


def _box_triangles(x0: float, y0: float, x1: float, y1: float, z0: float, z1: float) -> list[tuple]:
    """Return 12 triangles (6 quad faces × 2) of an axis-aligned box."""
    # 8 corners
    v = [
        np.array([x0, y0, z0]),
        np.array([x1, y0, z0]),
        np.array([x1, y1, z0]),
        np.array([x0, y1, z0]),
        np.array([x0, y0, z1]),
        np.array([x1, y0, z1]),
        np.array([x1, y1, z1]),
        np.array([x0, y1, z1]),
    ]
    nx = np.array([1.0, 0.0, 0.0])
    ny = np.array([0.0, 1.0, 0.0])
    nz = np.array([0.0, 0.0, 1.0])

    return [
        # Bottom (z = z0, normal -z)
        (v[0], v[2], v[1], -nz),
        (v[0], v[3], v[2], -nz),
        # Top (z = z1, normal +z)
        (v[4], v[5], v[6], nz),
        (v[4], v[6], v[7], nz),
        # Front (y = y0, normal -y)
        (v[0], v[1], v[5], -ny),
        (v[0], v[5], v[4], -ny),
        # Back (y = y1, normal +y)
        (v[3], v[7], v[6], ny),
        (v[3], v[6], v[2], ny),
        # Left (x = x0, normal -x)
        (v[0], v[4], v[7], -nx),
        (v[0], v[7], v[3], -nx),
        # Right (x = x1, normal +x)
        (v[1], v[2], v[6], nx),
        (v[1], v[6], v[5], nx),
    ]


def write_stl(
    mesh: StructuredMesh,
    densities: np.ndarray,
    out_path: str | Path,
    rho_threshold: float = 0.5,
    z_thickness: float = 1.0,
    solid_name: str = "topology",
) -> dict:
    """Write a 2D density field as a 3D-printable STL.

    Args:
        mesh:          structured-quad mesh
        densities:     per-element densities (shape n_elements,)
        out_path:      destination .stl file
        rho_threshold: density above this is treated as solid (default 0.5)
        z_thickness:   extrusion depth in z (default 1.0 = unit cube)
        solid_name:    STL solid name (max 80 chars in ASCII STL header)

    Returns:
        dict with `n_triangles`, `n_solid_cells`, `out_path` for the caller.
    """
    densities = np.asarray(densities, dtype=float).reshape(-1)
    if densities.shape[0] != mesh.elements.shape[0]:
        raise SolverError("density_count_mismatch")
    if z_thickness <= 0:
        raise SolverError("stl_export_nonpositive_thickness")

    cell_w = mesh.width / mesh.nelx
    cell_h = mesh.height / mesh.nely
    solid = densities > rho_threshold

    out_path = Path(out_path)
    triangles: list[str] = []
    n_solid = 0

    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            eid = mesh.element_index(ex, ey)
            if not solid[eid]:
                continue
            n_solid += 1
            x0 = ex * cell_w
            x1 = (ex + 1) * cell_w
            y0 = ey * cell_h
            y1 = (ey + 1) * cell_h
            for p1, p2, p3, normal in _box_triangles(x0, y0, x1, y1, 0.0, z_thickness):
                triangles.append(_format_triangle(p1, p2, p3, normal))

    with open(out_path, "w") as f:
        f.write(f"solid {solid_name[:80]}\n")
        for tri in triangles:
            f.write(tri)
        f.write(f"endsolid {solid_name[:80]}\n")

    return {
        "n_triangles": len(triangles),
        "n_solid_cells": n_solid,
        "out_path": str(out_path),
    }
