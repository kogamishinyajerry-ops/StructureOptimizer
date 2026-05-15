"""Wave J: boundary extraction + 2D geometry export (SVG/DXF) + 2.5D STL.

Takes a SIMP/BESO density field and produces vector geometry suitable for
downstream CAD/CAE/manufacturing tools. This is **not** CAD — we output
geometric descriptions; the consumer decides whether to feature-recognize.

Three formats:
- **SVG**: width × height of mesh, one path per closed boundary loop.
- **DXF R12 (ASCII)**: LINE entities, the minimal portable CAD vector subset.
- **STL (ASCII)**: 2.5D extrusion of the density field as triangle prisms.

Boundary extraction algorithm (marching squares simplification):
- Each element is classified solid (density ≥ threshold) or void.
- An edge between a solid and a void element is on the boundary.
- Boundary edges are chained into polylines / loops where possible.

This is intentionally simpler than full marching squares: we operate on
the element grid (not corner-value grid), producing axis-aligned segments.
That's a fine downstream descriptor for orthogonal designs from
structured topology optimization.

References:
- Marching squares: Lorensen & Cline 1987 (cube), 2D specialization.
- ezdxf for production DXF; we use a hand-rolled R12 ASCII subset.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from structure_optimizer.core.mesh import StructuredMesh


@dataclass(frozen=True)
class BoundarySegment:
    """A single axis-aligned line segment on the density-field boundary.

    Coordinates are in mesh-native units (model length).
    """

    x1: float
    y1: float
    x2: float
    y2: float


def extract_boundary_segments(
    mesh: StructuredMesh,
    densities: np.ndarray,
    threshold: float = 0.5,
) -> list[BoundarySegment]:
    """Find every cell-edge that separates a solid cell from a void cell.

    The mesh is treated as a regular grid of nelx × nely cells. An element
    is "solid" iff density ≥ threshold. A boundary segment is emitted
    between any solid–void neighbor pair or between any solid cell and the
    outside-of-domain. Output is a flat list (no chaining into loops).
    """
    solid = (np.asarray(densities, dtype=float).reshape(mesh.nely, mesh.nelx) >= threshold).astype(bool)
    hx = mesh.width / mesh.nelx
    hy = mesh.height / mesh.nely
    segments: list[BoundarySegment] = []

    for j in range(mesh.nely):
        for i in range(mesh.nelx):
            if not solid[j, i]:
                continue
            x0 = i * hx
            x1 = (i + 1) * hx
            y0 = j * hy
            y1 = (j + 1) * hy
            # left
            if i == 0 or not solid[j, i - 1]:
                segments.append(BoundarySegment(x0, y0, x0, y1))
            # right
            if i == mesh.nelx - 1 or not solid[j, i + 1]:
                segments.append(BoundarySegment(x1, y0, x1, y1))
            # bottom
            if j == 0 or not solid[j - 1, i]:
                segments.append(BoundarySegment(x0, y0, x1, y0))
            # top
            if j == mesh.nely - 1 or not solid[j + 1, i]:
                segments.append(BoundarySegment(x0, y1, x1, y1))
    return segments


def write_svg(
    path: Path | str,
    mesh: StructuredMesh,
    densities: np.ndarray,
    threshold: float = 0.5,
    stroke_width: float = 0.5,
) -> Path:
    """Write boundary segments to an SVG file. Returns the path."""
    path = Path(path)
    segments = extract_boundary_segments(mesh, densities, threshold)
    lines = [
        "<?xml version='1.0' encoding='utf-8'?>",
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{mesh.width}" height="{mesh.height}" '
        f'viewBox="0 0 {mesh.width} {mesh.height}">',
        '<g fill="none" stroke="black" stroke-width="' + str(stroke_width) + '">',
    ]
    for seg in segments:
        # Flip y so SVG (top-down) matches our (bottom-up) mesh convention
        y1 = mesh.height - seg.y1
        y2 = mesh.height - seg.y2
        lines.append(f'<line x1="{seg.x1:.6f}" y1="{y1:.6f}" x2="{seg.x2:.6f}" y2="{y2:.6f}"/>')
    lines.append("</g></svg>")
    path.write_text("\n".join(lines))
    return path


def write_dxf(
    path: Path | str,
    mesh: StructuredMesh,
    densities: np.ndarray,
    threshold: float = 0.5,
) -> Path:
    """Write boundary segments as a DXF R12 ASCII file (LINE entities).

    Minimal-subset DXF: HEADER + ENTITIES (LINE) + EOF. Sufficient for
    most CAD imports (AutoCAD, FreeCAD, LibreCAD).
    """
    path = Path(path)
    segments = extract_boundary_segments(mesh, densities, threshold)
    lines: list[str] = []
    # DXF entities header
    lines.extend(["0", "SECTION", "2", "ENTITIES"])
    for seg in segments:
        lines.extend(
            [
                "0",
                "LINE",
                "8",
                "0",  # layer "0"
                "10",
                f"{seg.x1:.6f}",
                "20",
                f"{seg.y1:.6f}",
                "30",
                "0.0",
                "11",
                f"{seg.x2:.6f}",
                "21",
                f"{seg.y2:.6f}",
                "31",
                "0.0",
            ]
        )
    lines.extend(["0", "ENDSEC", "0", "EOF"])
    path.write_text("\n".join(lines) + "\n")
    return path


def write_stl_extrusion(
    path: Path | str,
    mesh: StructuredMesh,
    densities: np.ndarray,
    extrusion_depth: float = 1.0,
    threshold: float = 0.5,
) -> Path:
    """Write 2.5D extrusion: each solid element becomes a hexahedral prism,
    decomposed into 12 triangles, in ASCII STL format. Returns the path.

    Only "top", "bottom", and outward-facing side faces are emitted (closed
    surface). This is the simplest "give me geometry I can 3D-print"
    output for a 2D topology design.
    """
    path = Path(path)
    solid = (np.asarray(densities, dtype=float).reshape(mesh.nely, mesh.nelx) >= threshold).astype(bool)
    hx = mesh.width / mesh.nelx
    hy = mesh.height / mesh.nely
    z0 = 0.0
    z1 = float(extrusion_depth)

    lines: list[str] = ["solid structure_optimizer_density"]

    def add_triangle(
        p1: tuple[float, float, float], p2: tuple[float, float, float], p3: tuple[float, float, float]
    ) -> None:
        # Compute normal
        v1 = np.array(p2) - np.array(p1)
        v2 = np.array(p3) - np.array(p1)
        n = np.cross(v1, v2)
        norm = float(np.linalg.norm(n))
        if norm > 0:
            n = n / norm
        lines.append(f"facet normal {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}")
        lines.append("  outer loop")
        for v in (p1, p2, p3):
            lines.append(f"    vertex {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
        lines.append("  endloop")
        lines.append("endfacet")

    for j in range(mesh.nely):
        for i in range(mesh.nelx):
            if not solid[j, i]:
                continue
            x0 = i * hx
            x1 = (i + 1) * hx
            y0 = j * hy
            y1 = (j + 1) * hy
            # Bottom face (z = 0), normal -z; 2 triangles
            add_triangle((x0, y0, z0), (x1, y1, z0), (x1, y0, z0))
            add_triangle((x0, y0, z0), (x0, y1, z0), (x1, y1, z0))
            # Top face (z = depth), normal +z
            add_triangle((x0, y0, z1), (x1, y0, z1), (x1, y1, z1))
            add_triangle((x0, y0, z1), (x1, y1, z1), (x0, y1, z1))
            # Left face if void to left
            if i == 0 or not solid[j, i - 1]:
                add_triangle((x0, y0, z0), (x0, y0, z1), (x0, y1, z1))
                add_triangle((x0, y0, z0), (x0, y1, z1), (x0, y1, z0))
            if i == mesh.nelx - 1 or not solid[j, i + 1]:
                add_triangle((x1, y0, z0), (x1, y1, z0), (x1, y1, z1))
                add_triangle((x1, y0, z0), (x1, y1, z1), (x1, y0, z1))
            if j == 0 or not solid[j - 1, i]:
                add_triangle((x0, y0, z0), (x1, y0, z0), (x1, y0, z1))
                add_triangle((x0, y0, z0), (x1, y0, z1), (x0, y0, z1))
            if j == mesh.nely - 1 or not solid[j + 1, i]:
                add_triangle((x0, y1, z0), (x0, y1, z1), (x1, y1, z1))
                add_triangle((x0, y1, z0), (x1, y1, z1), (x1, y1, z0))

    lines.append("endsolid structure_optimizer_density")
    path.write_text("\n".join(lines) + "\n")
    return path
