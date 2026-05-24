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
- ``write_stl`` output is voxelized — each density cell becomes an axis-aligned
  box (boundary area error O(h)). Wave JJ adds ``write_stl_marching_squares``,
  a marching-squares iso-contour extruder with linearly-interpolated smooth
  boundaries (area error O(h²)); see D039.
- Thickness is uniform — variable thickness needs per-element
  metadata.
"""

from __future__ import annotations

from collections import defaultdict
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


# ---------------------------------------------------------------------------
# Wave JJ (v6): marching-squares smooth-boundary STL.
#
# The voxel ``write_stl`` above turns every solid cell into an axis-aligned box,
# so the boundary is staircased — its area error vs the true shape is O(h)
# (proportional to cell size). Marching squares extracts the iso-contour of the
# density field with *linear edge interpolation*, cutting the corners; for a
# smooth field its enclosed-area error drops to O(h²). The closed contour loops
# are then extruded to a prism (smooth side walls + fan-triangulated caps).
#
# Edge indexing within a cell (corners CCW from bottom-left):
#   c0=(x_i, y_j)  c1=(x_{i+1}, y_j)  c2=(x_{i+1}, y_{j+1})  c3=(x_i, y_{j+1})
#   e0 = c0-c1 (bottom)  e1 = c1-c2 (right)  e2 = c2-c3 (top)  e3 = c3-c0 (left)
# ---------------------------------------------------------------------------

# Undirected edge-pairs the contour crosses, per 4-bit corner-inside case.
# Saddle cases 5 and 10 are resolved at run time by the cell-centre value.
_MS_CASES: dict[int, list[tuple[int, int]]] = {
    0: [], 15: [],
    1: [(3, 0)], 14: [(3, 0)],
    2: [(0, 1)], 13: [(0, 1)],
    3: [(1, 3)], 12: [(1, 3)],
    4: [(1, 2)], 11: [(1, 2)],
    6: [(0, 2)], 9: [(0, 2)],
    7: [(2, 3)], 8: [(2, 3)],
    5: [(3, 0), (1, 2)],   # saddle — resolved below
    10: [(0, 1), (2, 3)],  # saddle — resolved below
}


def _edge_point(edge: int, corners: list, vals: list, level: float) -> np.ndarray:
    """Linearly-interpolated crossing point on one cell edge at ``level``."""
    a, b = ((0, 1), (1, 2), (2, 3), (3, 0))[edge]
    va, vb = vals[a], vals[b]
    denom = vb - va
    t = 0.5 if abs(denom) < 1e-300 else (level - va) / denom
    return corners[a] + t * (corners[b] - corners[a])


def _key(p: np.ndarray) -> tuple[float, float]:
    """Quantized endpoint key so a crossing shared by two cells matches exactly."""
    return (round(float(p[0]), 12), round(float(p[1]), 12))


def _stitch_loops(segments: list[tuple[np.ndarray, np.ndarray]]) -> list[list[np.ndarray]]:
    """Stitch unordered segments into closed loops by endpoint matching."""
    used = [False] * len(segments)
    endpoint: dict[tuple, list[int]] = defaultdict(list)
    for idx, (p, q) in enumerate(segments):
        endpoint[_key(p)].append(idx)
        endpoint[_key(q)].append(idx)

    loops: list[list[np.ndarray]] = []
    for start_idx in range(len(segments)):
        if used[start_idx]:
            continue
        used[start_idx] = True
        p, q = segments[start_idx]
        loop = [p, q]
        start_key, cur_key = _key(p), _key(q)
        while cur_key != start_key:
            nxt = next((c for c in endpoint[cur_key] if not used[c]), None)
            if nxt is None:
                break  # open contour (solid touches the sampling boundary)
            used[nxt] = True
            a, b = segments[nxt]
            nextpt = b if _key(a) == cur_key else a
            loop.append(nextpt)
            cur_key = _key(nextpt)
        loops.append(loop)
    return loops


def marching_squares_contours(
    field: np.ndarray,
    x_coords: np.ndarray,
    y_coords: np.ndarray,
    level: float = 0.5,
) -> list[list[np.ndarray]]:
    """Extract iso-contour loops at ``level`` from a scalar grid.

    Args:
        field:    shape (ny, nx) — scalar samples; ``field[j, i]`` at
                  (x_coords[i], y_coords[j]).
        x_coords: shape (nx,) ascending sample x positions.
        y_coords: shape (ny,) ascending sample y positions.
        level:    iso-value (inside = field > level).

    Returns:
        list of loops; each loop is a list of (x, y) points. Interior loops are
        closed (first point ≈ last point) with linearly-interpolated vertices.
    """
    field = np.asarray(field, dtype=float)
    ny, nx = field.shape
    if nx < 2 or ny < 2:
        raise SolverError("marching_squares_grid_too_small")
    if x_coords.shape[0] != nx or y_coords.shape[0] != ny:
        raise SolverError("marching_squares_coord_mismatch")

    segments: list[tuple[np.ndarray, np.ndarray]] = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            corners = [
                np.array([x_coords[i], y_coords[j]]),
                np.array([x_coords[i + 1], y_coords[j]]),
                np.array([x_coords[i + 1], y_coords[j + 1]]),
                np.array([x_coords[i], y_coords[j + 1]]),
            ]
            vals = [field[j, i], field[j, i + 1], field[j + 1, i + 1], field[j + 1, i]]
            case = sum((1 << k) for k, v in enumerate(vals) if v > level)
            pairs = _MS_CASES[case]
            if case in (5, 10):
                center_inside = (sum(vals) / 4.0) > level
                if case == 5:
                    pairs = [(0, 1), (2, 3)] if center_inside else [(3, 0), (1, 2)]
                else:
                    pairs = [(3, 0), (1, 2)] if center_inside else [(0, 1), (2, 3)]
            for ea, eb in pairs:
                segments.append(
                    (_edge_point(ea, corners, vals, level), _edge_point(eb, corners, vals, level))
                )
    return _stitch_loops(segments)


def polygon_area(loop: list[np.ndarray]) -> float:
    """Absolute area enclosed by a polygon loop (shoelace)."""
    pts = np.asarray(loop, dtype=float)
    if pts.shape[0] >= 2 and np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    if pts.shape[0] < 3:
        return 0.0
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def write_stl_marching_squares(
    mesh: StructuredMesh,
    densities: np.ndarray,
    out_path: str | Path,
    rho_threshold: float = 0.5,
    z_thickness: float = 1.0,
    solid_name: str = "topology_smooth",
) -> dict:
    """Write a 2D density field as a smooth-boundary extruded STL.

    Samples the density field at cell centres, extracts the ``rho_threshold``
    iso-contour by marching squares, and extrudes each closed loop to a prism
    (linearly-interpolated side walls + centroid-fan top/bottom caps).

    Returns a dict with ``n_triangles``, ``n_loops``, ``cross_section_area``,
    ``out_path``.
    """
    densities = np.asarray(densities, dtype=float).reshape(-1)
    if densities.shape[0] != mesh.elements.shape[0]:
        raise SolverError("density_count_mismatch")
    if z_thickness <= 0:
        raise SolverError("stl_export_nonpositive_thickness")

    cell_w = mesh.width / mesh.nelx
    cell_h = mesh.height / mesh.nely
    field = np.zeros((mesh.nely, mesh.nelx))
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            field[ey, ex] = densities[mesh.element_index(ex, ey)]
    x_coords = (np.arange(mesh.nelx) + 0.5) * cell_w
    y_coords = (np.arange(mesh.nely) + 0.5) * cell_h

    loops = marching_squares_contours(field, x_coords, y_coords, rho_threshold)
    loops = [lp for lp in loops if polygon_area(lp) > 1e-12]

    triangles: list[str] = []
    total_area = 0.0
    for lp in loops:
        pts = np.asarray(lp, dtype=float)
        if pts.shape[0] >= 2 and np.allclose(pts[0], pts[-1]):
            pts = pts[:-1]
        if pts.shape[0] < 3:
            continue
        total_area += polygon_area(lp)
        centroid = pts.mean(axis=0)
        c_lo = np.array([centroid[0], centroid[1], 0.0])
        c_hi = np.array([centroid[0], centroid[1], z_thickness])
        n_pts = pts.shape[0]
        for k in range(n_pts):
            a = pts[k]
            b = pts[(k + 1) % n_pts]
            a_lo = np.array([a[0], a[1], 0.0])
            b_lo = np.array([b[0], b[1], 0.0])
            a_hi = np.array([a[0], a[1], z_thickness])
            b_hi = np.array([b[0], b[1], z_thickness])
            # Side wall (two triangles); normal from the edge direction × z.
            edge = b - a
            wall_n = np.array([edge[1], -edge[0], 0.0])
            nrm = np.linalg.norm(wall_n)
            wall_n = wall_n / nrm if nrm > 1e-300 else np.array([1.0, 0.0, 0.0])
            triangles.append(_format_triangle(a_lo, b_lo, b_hi, wall_n))
            triangles.append(_format_triangle(a_lo, b_hi, a_hi, wall_n))
            # Bottom cap fan (normal -z) and top cap fan (normal +z).
            triangles.append(_format_triangle(c_lo, b_lo, a_lo, np.array([0.0, 0.0, -1.0])))
            triangles.append(_format_triangle(c_hi, a_hi, b_hi, np.array([0.0, 0.0, 1.0])))

    out_path = Path(out_path)
    with open(out_path, "w") as f:
        f.write(f"solid {solid_name[:80]}\n")
        for tri in triangles:
            f.write(tri)
        f.write(f"endsolid {solid_name[:80]}\n")

    return {
        "n_triangles": len(triangles),
        "n_loops": len(loops),
        "cross_section_area": float(total_area),
        "out_path": str(out_path),
    }


# --- Wave SS (v7, D048): ear-clipping general-polygon triangulation + holes ---
#
# D039's reopening criterion named the upgrade: the marching-squares caps use a
# centroid fan, which is only valid for star-convex loops and cannot represent
# holes. Ear clipping triangulates an arbitrary simple polygon (concave,
# non-star-convex), and a visibility bridge merges holes (even-odd nesting) into
# a single simple polygon before clipping. The verifiable invariant is exact
# area conservation: Σ triangle areas == polygon area − Σ hole areas.


def _signed_area(pts: np.ndarray) -> float:
    """Signed shoelace area of an open vertex ring (CCW > 0)."""
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _tri_area(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return 0.5 * abs(float((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])))


def _point_strictly_in_tri(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> bool:
    """True if p is strictly inside triangle abc (barycentric, small tolerance)."""
    d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(d) < 1e-300:
        return False
    s = ((b[1] - c[1]) * (p[0] - c[0]) + (c[0] - b[0]) * (p[1] - c[1])) / d
    t = ((c[1] - a[1]) * (p[0] - c[0]) + (a[0] - c[0]) * (p[1] - c[1])) / d
    eps = 1e-12
    return s > eps and t > eps and (s + t) < 1.0 - eps


def _dedupe_ring(loop) -> np.ndarray:
    """Drop a repeated closing vertex; return (n, 2) open ring."""
    pts = np.asarray(loop, dtype=float)
    if pts.shape[0] >= 2 and np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    return pts


def ear_clipping_triangulate(loop) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    """Triangulate a simple polygon (concave OK) by ear clipping.

    Returns ``(pts, triangles)`` where ``pts`` is the (n, 2) CCW vertex ring and
    ``triangles`` is a list of index triples into ``pts``. The triangulation
    conserves area exactly (Σ triangle areas == |polygon area|).
    """
    pts = _dedupe_ring(loop)
    n = pts.shape[0]
    if n < 3:
        raise SolverError("ear_clipping_degenerate_polygon")
    if _signed_area(pts) < 0:  # force CCW
        pts = pts[::-1].copy()
    idx = list(range(pts.shape[0]))
    tris: list[tuple[int, int, int]] = []
    guard = 0
    max_guard = pts.shape[0] ** 2 + 1
    while len(idx) > 3 and guard < max_guard:
        guard += 1
        m = len(idx)
        clipped = False
        for ii in range(m):
            i0, i1, i2 = idx[(ii - 1) % m], idx[ii], idx[(ii + 1) % m]
            a, b, c = pts[i0], pts[i1], pts[i2]
            # convex (CCW left turn) ?
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
            if cross <= 1e-12:
                continue
            if any(
                _point_strictly_in_tri(pts[j], a, b, c)
                for j in idx
                if j not in (i0, i1, i2)
            ):
                continue
            tris.append((i0, i1, i2))
            del idx[ii]
            clipped = True
            break
        if not clipped:
            raise SolverError("ear_clipping_no_ear_found")
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return pts, tris


def _segment_intersects(p1, p2, q1, q2) -> bool:
    """Proper segment intersection test (shared endpoints do not count)."""
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(v) < 1e-12:
            return 0
        return 1 if v > 0 else -1

    if np.allclose(p1, q1) or np.allclose(p1, q2) or np.allclose(p2, q1) or np.allclose(p2, q2):
        return False
    o1, o2 = orient(p1, p2, q1), orient(p1, p2, q2)
    o3, o4 = orient(q1, q2, p1), orient(q1, q2, p2)
    return o1 != o2 and o3 != o4


def _bridge_visible(outer: np.ndarray, hole: np.ndarray, all_rings: list[np.ndarray]):
    """Find a bridge (outer index, hole index) whose segment crosses no edge."""
    for oi in range(outer.shape[0]):
        for hi in range(hole.shape[0]):
            a, b = outer[oi], hole[hi]
            blocked = False
            for ring in all_rings:
                rn = ring.shape[0]
                for k in range(rn):
                    if _segment_intersects(a, b, ring[k], ring[(k + 1) % rn]):
                        blocked = True
                        break
                if blocked:
                    break
            if not blocked:
                return oi, hi
    raise SolverError("polygon_hole_no_visible_bridge")


def triangulate_with_holes(outer_loop, holes=None) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    """Triangulate a polygon with optional holes (even-odd nesting).

    Each hole is bridged into the outer polygon (a mutually-visible vertex pair,
    zero-width slit) to form one simple polygon, then ear-clipped. Conserves
    area exactly: Σ triangle areas == outer area − Σ hole areas.
    """
    outer = _dedupe_ring(outer_loop)
    if _signed_area(outer) < 0:
        outer = outer[::-1].copy()
    holes = holes or []
    hole_rings = []
    for h in holes:
        hr = _dedupe_ring(h)
        if _signed_area(hr) > 0:  # holes traversed opposite to outer
            hr = hr[::-1].copy()
        hole_rings.append(hr)
    # Process holes by descending rightmost-x (Eberly's ordering).
    hole_rings.sort(key=lambda r: -float(r[:, 0].max()))

    merged = outer.copy()
    for k, hr in enumerate(hole_rings):
        # The bridge must cross neither the current merged polygon nor any hole
        # not yet merged in.
        all_rings = [merged, hr, *hole_rings[k + 1:]]
        oi, hi = _bridge_visible(merged, hr, all_rings)
        # Insert the slit: merged[..oi], hole[hi..wrap..hi], merged[oi..].
        hole_seq = np.vstack([np.roll(hr, -hi, axis=0), hr[hi][None, :]])
        merged = np.vstack([merged[: oi + 1], hole_seq, merged[oi:][:]])
    return ear_clipping_triangulate(merged)


def write_stl_polygon(
    outer_loop,
    out_path: str | Path,
    holes=None,
    z_thickness: float = 1.0,
    solid_name: str = "polygon_extruded",
) -> dict:
    """Extrude a general (concave, holed) polygon to a watertight STL prism.

    Caps are ear-clipped (valid for non-star-convex sections + holes); side walls
    are built for the outer ring and every hole ring. Returns a dict with
    ``n_triangles``, ``cross_section_area``, ``is_watertight``, ``out_path``.
    """
    if z_thickness <= 0:
        raise SolverError("stl_export_nonpositive_thickness")
    pts, tris = triangulate_with_holes(outer_loop, holes)
    cross_section_area = sum(_tri_area(pts[i], pts[j], pts[k]) for i, j, k in tris)

    triangles: list[str] = []

    def emit(a3, b3, c3, n):
        triangles.append(_format_triangle(a3, b3, c3, n))

    # Caps: bottom (−z, reversed winding) and top (+z).
    for i, j, k in tris:
        a, b, c = pts[i], pts[j], pts[k]
        a_lo, b_lo, c_lo = (np.array([p[0], p[1], 0.0]) for p in (a, b, c))
        a_hi, b_hi, c_hi = (np.array([p[0], p[1], z_thickness]) for p in (a, b, c))
        emit(a_lo, c_lo, b_lo, np.array([0.0, 0.0, -1.0]))
        emit(a_hi, b_hi, c_hi, np.array([0.0, 0.0, 1.0]))

    # Side walls for outer ring + each hole ring (orientation from the ring).
    outer = _dedupe_ring(outer_loop)
    if _signed_area(outer) < 0:
        outer = outer[::-1].copy()
    rings = [outer]
    for h in holes or []:
        hr = _dedupe_ring(h)
        if _signed_area(hr) > 0:
            hr = hr[::-1].copy()
        rings.append(hr)
    for ring in rings:
        rn = ring.shape[0]
        for kk in range(rn):
            a, b = ring[kk], ring[(kk + 1) % rn]
            a_lo = np.array([a[0], a[1], 0.0])
            b_lo = np.array([b[0], b[1], 0.0])
            a_hi = np.array([a[0], a[1], z_thickness])
            b_hi = np.array([b[0], b[1], z_thickness])
            edge = b - a
            wall_n = np.array([edge[1], -edge[0], 0.0])
            nrm = np.linalg.norm(wall_n)
            wall_n = wall_n / nrm if nrm > 1e-300 else np.array([1.0, 0.0, 0.0])
            emit(a_lo, b_lo, b_hi, wall_n)
            emit(a_lo, b_hi, a_hi, wall_n)

    out_path = Path(out_path)
    with open(out_path, "w") as f:
        f.write(f"solid {solid_name[:80]}\n")
        for tri in triangles:
            f.write(tri)
        f.write(f"endsolid {solid_name[:80]}\n")

    return {
        "n_triangles": len(triangles),
        "cross_section_area": float(cross_section_area),
        "is_watertight": stl_is_watertight(triangles),
        "out_path": str(out_path),
    }


def stl_is_watertight(triangle_blocks: list[str]) -> bool:
    """True if every undirected edge of the facet set is shared by exactly two facets."""
    edges: dict[tuple, int] = defaultdict(int)
    for block in triangle_blocks:
        verts = []
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("vertex"):
                parts = line.split()
                verts.append((round(float(parts[1]), 9), round(float(parts[2]), 9), round(float(parts[3]), 9)))
        if len(verts) != 3:
            return False
        for a, b in ((verts[0], verts[1]), (verts[1], verts[2]), (verts[2], verts[0])):
            edges[tuple(sorted((a, b)))] += 1
    return all(count == 2 for count in edges.values())
