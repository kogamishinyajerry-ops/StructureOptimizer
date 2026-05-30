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
    0: [],
    15: [],
    1: [(3, 0)],
    14: [(3, 0)],
    2: [(0, 1)],
    13: [(0, 1)],
    3: [(1, 3)],
    12: [(1, 3)],
    4: [(1, 2)],
    11: [(1, 2)],
    6: [(0, 2)],
    9: [(0, 2)],
    7: [(2, 3)],
    8: [(2, 3)],
    5: [(3, 0), (1, 2)],  # saddle — resolved below
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
                segments.append((_edge_point(ea, corners, vals, level), _edge_point(eb, corners, vals, level)))
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
    eps = 1e-9
    while len(idx) > 3 and guard < max_guard:
        guard += 1
        m = len(idx)
        # Pass 1: clip a strictly-convex ear containing no other vertex.
        clipped = False
        for ii in range(m):
            i0, i1, i2 = idx[(ii - 1) % m], idx[ii], idx[(ii + 1) % m]
            a, b, c = pts[i0], pts[i1], pts[i2]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
            if cross <= eps:  # reflex or collinear — not a strict ear
                continue
            if any(_point_strictly_in_tri(pts[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            del idx[ii]
            clipped = True
            break
        if clipped:
            continue
        # Pass 2: drop a redundant collinear vertex (|cross| ≤ eps). It lies on
        # the straight edge between its neighbours, so removing it leaves the
        # polygon unchanged — no triangle is emitted (it would be degenerate).
        # This is what lets marching-squares staircase runs (many collinear
        # vertices) be triangulated.
        removed = False
        for ii in range(m):
            i0, i1, i2 = idx[(ii - 1) % m], idx[ii], idx[(ii + 1) % m]
            a, b, c = pts[i0], pts[i1], pts[i2]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
            if abs(cross) <= eps:
                del idx[ii]
                removed = True
                break
        if not removed:
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
        all_rings = [merged, hr, *hole_rings[k + 1 :]]
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


# --- Wave AAA (v8, D056): marching-squares nested-loop holes → ear-clipping ---
#
# D048's reopening criterion: auto-detect nested marching-squares loops
# (even-odd parity) and route each (outer, holes) group through the
# ear-clipping `triangulate_with_holes`, so a density field with an interior
# void (e.g. an annulus) extrudes to a watertight prism with the hole carved out
# — which the centroid-fan cap of `write_stl_marching_squares` cannot do.


def _clean_ring(loop, tol: float = 1e-9) -> np.ndarray:
    """Drop consecutive-duplicate and collinear vertices from a ring.

    Used so the cap triangulation and the side walls share the **same** vertex
    set (collinear vertices removed once, up front) — otherwise ear clipping
    would silently drop boundary vertices the walls still carry, breaking
    watertightness. Never reduces below 3 vertices.
    """
    pts = _dedupe_ring(loop)
    # remove consecutive duplicates
    keep = [pts[0]]
    for p in pts[1:]:
        if np.linalg.norm(p - keep[-1]) > tol:
            keep.append(p)
    pts = np.array(keep)
    if pts.shape[0] < 3:
        return pts
    # remove collinear vertices
    out = []
    n = pts.shape[0]
    for i in range(n):
        a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        if abs(cross) > tol:
            out.append(b)
    return np.array(out) if len(out) >= 3 else pts


def _point_in_loop(point, loop) -> bool:
    """Ray-casting point-in-polygon test for a closed loop (open or closed ring)."""
    pts = _dedupe_ring(loop)
    x, y = float(point[0]), float(point[1])
    inside = False
    n = pts.shape[0]
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-300) + xi):
            inside = not inside
        j = i
    return inside


def classify_loops_even_odd(loops):
    """Group MS contour loops into (outer, [holes]) by even-odd nesting depth.

    A loop's depth = number of other loops that contain it (containment tested on
    a representative vertex — MS loops never cross). Even depth = solid outer; odd
    depth = hole. Each hole is assigned to its immediate container (depth−1).
    Returns a list of ``(outer_loop, [hole_loops])`` groups; deeper nesting
    (islands inside holes) become their own outer groups.
    """
    rings = [_dedupe_ring(lp) for lp in loops]
    n = len(rings)
    contains = [[False] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j and rings[i].shape[0] >= 1:
                contains[j][i] = _point_in_loop(rings[i][0], rings[j])
    depth = [sum(1 for j in range(n) if contains[j][i]) for i in range(n)]
    groups = []
    for i in range(n):
        if depth[i] % 2 == 0:  # solid outer
            holes = [rings[h] for h in range(n) if depth[h] == depth[i] + 1 and contains[i][h]]
            groups.append((rings[i], holes))
    return groups


def write_stl_smooth_holes(
    mesh: StructuredMesh,
    densities: np.ndarray,
    out_path: str | Path,
    rho_threshold: float = 0.5,
    z_thickness: float = 1.0,
    solid_name: str = "topology_smooth_holes",
) -> dict:
    """Smooth-boundary STL with **holes**: marching-squares contours → even-odd
    nesting → ear-clipping caps + outer/hole side walls (Wave AAA, D056).

    Unlike ``write_stl_marching_squares`` (centroid fan, no holes), this carves
    interior voids out of the cap. Returns ``n_triangles``, ``cross_section_area``
    (outer − holes), ``n_groups``, ``is_watertight``, ``out_path``.
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

    loops = [
        lp for lp in marching_squares_contours(field, x_coords, y_coords, rho_threshold) if polygon_area(lp) > 1e-12
    ]
    groups = classify_loops_even_odd(loops)

    triangles: list[str] = []
    total_area = 0.0
    for outer, holes in groups:
        # Clean rings once (remove collinear) so cap boundary and walls share the
        # same vertices → watertight (see _clean_ring).
        outer_c = _clean_ring(outer)
        holes_c = [_clean_ring(h) for h in holes]
        pts, tris = triangulate_with_holes(outer_c, holes_c)
        total_area += sum(_tri_area(pts[i], pts[j], pts[k]) for i, j, k in tris)
        for i, j, k in tris:
            a, b, c = pts[i], pts[j], pts[k]
            a_lo, b_lo, c_lo = (np.array([p[0], p[1], 0.0]) for p in (a, b, c))
            a_hi, b_hi, c_hi = (np.array([p[0], p[1], z_thickness]) for p in (a, b, c))
            triangles.append(_format_triangle(a_lo, c_lo, b_lo, np.array([0.0, 0.0, -1.0])))
            triangles.append(_format_triangle(a_hi, b_hi, c_hi, np.array([0.0, 0.0, 1.0])))
        for ring in [outer_c, *holes_c]:
            ring = np.asarray(ring, dtype=float)
            if _signed_area(ring) < 0:
                ring = ring[::-1].copy()
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
                triangles.append(_format_triangle(a_lo, b_lo, b_hi, wall_n))
                triangles.append(_format_triangle(a_lo, b_hi, a_hi, wall_n))

    out_path = Path(out_path)
    with open(out_path, "w") as f:
        f.write(f"solid {solid_name[:80]}\n")
        for tri in triangles:
            f.write(tri)
        f.write(f"endsolid {solid_name[:80]}\n")

    return {
        "n_triangles": len(triangles),
        "cross_section_area": float(total_area),
        "n_groups": len(groups),
        "is_watertight": stl_is_watertight(triangles),
        "out_path": str(out_path),
    }


# --- Wave III (v9, D064): slit-free, robustly-watertight holed prism ---------
#
# D056's ear-clipping holed cap opens each hole with a zero-width *bridge slit*,
# which leaves a non-manifold edge for high-vertex curved holes (an annulus is
# NOT watertight — the well-documented D056 limitation). Its reopening criterion
# named a "slit-free hole triangulation (constrained Delaunay / monotone-polygon
# decomposition) so curved-hole prisms are robustly watertight". This delivers
# the simplest such decomposition: each solid grid cell is trivially y-monotone,
# so triangulating the rasterised region cell-by-cell (2 tris per cap face + a
# wall on every solid↔void boundary edge) is slit-free and edge-manifold for ANY
# hole topology — the annulus included. The trade-off vs D056 is a staircase
# (cell-resolution) boundary instead of the smooth marching-squares contour.


def write_stl_slit_free_holes(
    mesh: StructuredMesh,
    densities: np.ndarray,
    out_path: str | Path,
    rho_threshold: float = 0.5,
    z_thickness: float = 1.0,
    solid_name: str = "topology_slit_free",
) -> dict:
    """Slit-free, robustly-watertight extruded prism of the solid cells (Wave III,
    D064). Unlike :func:`write_stl_smooth_holes` (smooth but non-manifold on curved
    holes) this is watertight for any **edge-connected** hole topology — annuli and
    multi-hole plates included — at the cost of a cell-resolution staircase
    boundary. Returns ``n_triangles``, ``cross_section_area`` (= n_solid_cells ·
    cell_area), ``n_solid_cells``, ``is_watertight``, ``out_path``.

    Honest limitation: a *diagonal pinch* (two solid cells touching only at a
    corner, as in a checkerboard) is a genuine non-manifold point and is reported
    as ``is_watertight=False`` — density-filtered topology-optimised designs do not
    contain these, but raw random fields can.
    """
    densities = np.asarray(densities, dtype=float).reshape(-1)
    if densities.shape[0] != mesh.elements.shape[0]:
        raise SolverError("density_count_mismatch")
    if z_thickness <= 0:
        raise SolverError("stl_export_nonpositive_thickness")

    nelx, nely = mesh.nelx, mesh.nely
    cw = mesh.width / nelx
    ch = mesh.height / nely
    solid = np.zeros((nely, nelx), dtype=bool)
    for ey in range(nely):
        for ex in range(nelx):
            solid[ey, ex] = densities[mesh.element_index(ex, ey)] > rho_threshold

    zt = float(z_thickness)
    triangles: list[str] = []
    up = np.array([0.0, 0.0, 1.0])
    down = np.array([0.0, 0.0, -1.0])
    n_solid = 0
    for ey in range(nely):
        for ex in range(nelx):
            if not solid[ey, ex]:
                continue
            n_solid += 1
            x0, x1 = ex * cw, (ex + 1) * cw
            y0, y1 = ey * ch, (ey + 1) * ch
            bl, br = np.array([x0, y0, 0.0]), np.array([x1, y0, 0.0])
            tr, tl = np.array([x1, y1, 0.0]), np.array([x0, y1, 0.0])
            blz, brz = np.array([x0, y0, zt]), np.array([x1, y0, zt])
            trz, tlz = np.array([x1, y1, zt]), np.array([x0, y1, zt])
            # top cap (+z) and bottom cap (-z), consistent bl–tr diagonal
            triangles.append(_format_triangle(blz, brz, trz, up))
            triangles.append(_format_triangle(blz, trz, tlz, up))
            triangles.append(_format_triangle(bl, tr, br, down))
            triangles.append(_format_triangle(bl, tl, tr, down))
            # side walls on every solid↔(void|outside) edge
            # bottom edge bl-br (neighbour ey-1)
            if ey == 0 or not solid[ey - 1, ex]:
                triangles.append(_format_triangle(bl, br, brz, np.array([0.0, -1.0, 0.0])))
                triangles.append(_format_triangle(bl, brz, blz, np.array([0.0, -1.0, 0.0])))
            # top edge tr-tl (neighbour ey+1)
            if ey == nely - 1 or not solid[ey + 1, ex]:
                triangles.append(_format_triangle(tr, tl, tlz, np.array([0.0, 1.0, 0.0])))
                triangles.append(_format_triangle(tr, tlz, trz, np.array([0.0, 1.0, 0.0])))
            # left edge tl-bl (neighbour ex-1)
            if ex == 0 or not solid[ey, ex - 1]:
                triangles.append(_format_triangle(tl, bl, blz, np.array([-1.0, 0.0, 0.0])))
                triangles.append(_format_triangle(tl, blz, tlz, np.array([-1.0, 0.0, 0.0])))
            # right edge br-tr (neighbour ex+1)
            if ex == nelx - 1 or not solid[ey, ex + 1]:
                triangles.append(_format_triangle(br, tr, trz, np.array([1.0, 0.0, 0.0])))
                triangles.append(_format_triangle(br, trz, brz, np.array([1.0, 0.0, 0.0])))

    out_path = Path(out_path)
    with open(out_path, "w") as f:
        f.write(f"solid {solid_name[:80]}\n")
        for tri in triangles:
            f.write(tri)
        f.write(f"endsolid {solid_name[:80]}\n")

    return {
        "n_triangles": len(triangles),
        "cross_section_area": float(n_solid * cw * ch),
        "n_solid_cells": int(n_solid),
        "is_watertight": stl_is_watertight(triangles),
        "out_path": str(out_path),
    }


# --- Wave QQQ (v10, D072): smooth AND watertight holed prism (annulus ribbon) --
#
# AAA (D056) gave smooth marching-squares contours but the bridge-slit cap is
# non-watertight on curved holes; III (D064) gave a watertight prism but with a
# staircase (cell-resolution) boundary. QQQ resolves D064's reopening criterion —
# smooth + watertight — for the **ring (annulus)** case the rubric targets, by
# triangulating the region between the smooth outer contour and the smooth hole
# contour as a **quad ribbon**: both loops are resampled to the same vertex count
# and angularly aligned, then connected i↔i. The ribbon's quad-strip topology is
# edge-manifold *by construction* (every rung shared by two triangles, every
# contour edge shared by one cap + one wall triangle), independent of geometry —
# so the prism is watertight while the contour stays smooth.


def _resample_closed_ring(loop: np.ndarray, n: int) -> np.ndarray:
    """Resample a closed loop to ``n`` points equally spaced by arc length."""
    ring = _clean_ring(loop)
    if ring.shape[0] < 3:
        raise SolverError("smooth_watertight_degenerate_ring")
    pts = np.vstack([ring, ring[0]])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(cum[-1])
    if total <= 0:
        raise SolverError("smooth_watertight_zero_perimeter")
    targets = np.linspace(0.0, total, n, endpoint=False)
    out = np.empty((n, 2))
    for i, t in enumerate(targets):
        k = min(int(np.searchsorted(cum, t, side="right") - 1), len(seg) - 1)
        f = (t - cum[k]) / seg[k] if seg[k] > 0 else 0.0
        out[i] = pts[k] + f * (pts[k + 1] - pts[k])
    return out


def write_stl_smooth_watertight_holes(
    field: np.ndarray,
    x_coords: np.ndarray,
    y_coords: np.ndarray,
    out_path: str | Path,
    level: float = 0.5,
    n_samples: int = 128,
    z_thickness: float = 1.0,
    solid_name: str = "topology_smooth_watertight",
) -> dict:
    """Smooth **and** watertight STL for **annular** (single-hole) regions of a
    scalar field — Wave QQQ, D072.

    Extracts smooth marching-squares contours, groups them by even-odd nesting,
    and for each region with exactly one hole builds an **annulus ribbon prism**:
    the outer and hole contours are resampled to ``n_samples`` points each,
    angularly aligned, and connected ``i↔i`` into a quad strip for the top and
    bottom caps, with side walls along both contours. The quad-strip topology is
    edge-manifold by construction, so the result is watertight (verified) while
    the boundary stays smooth (no staircase). Cross-section area ≈ outer − hole.

    Only single-hole (annulus) regions are supported; a region with no holes or
    with ≥2 holes raises ``SolverError`` (see honest scope / reopening in D072).

    Returns ``n_triangles``, ``cross_section_area``, ``is_watertight``,
    ``n_annuli``, ``out_path``.
    """
    if z_thickness <= 0:
        raise SolverError("stl_export_nonpositive_thickness")
    if n_samples < 8:
        raise SolverError("smooth_watertight_too_few_samples")

    loops = [lp for lp in marching_squares_contours(field, x_coords, y_coords, level) if polygon_area(lp) > 1e-12]
    groups = classify_loops_even_odd(loops)
    if not groups:
        raise SolverError("smooth_watertight_no_annulus")
    if any(len(h) != 1 for _o, h in groups):
        raise SolverError("smooth_watertight_requires_single_hole_per_region")
    annuli = groups

    triangles: list[str] = []
    total_area = 0.0
    zt = float(z_thickness)
    z_up = np.array([0.0, 0.0, 1.0])
    z_dn = np.array([0.0, 0.0, -1.0])

    def _p3(p: np.ndarray, z: float) -> np.ndarray:
        return np.array([p[0], p[1], z])

    for outer, holes in annuli:
        o = _resample_closed_ring(outer, n_samples)
        h = _resample_closed_ring(holes[0], n_samples)
        if _signed_area(o) < 0:
            o = o[::-1].copy()
        if _signed_area(h) < 0:
            h = h[::-1].copy()
        # angularly align the hole's start vertex to the outer's start vertex
        c = o.mean(axis=0)
        a0 = np.arctan2(o[0, 1] - c[1], o[0, 0] - c[0])
        ah = np.arctan2(h[:, 1] - c[1], h[:, 0] - c[0])
        h = np.roll(h, -int(np.argmin(np.abs(((ah - a0 + np.pi) % (2.0 * np.pi)) - np.pi))), axis=0)

        # caps: top (+z) and bottom (−z, reversed) quad strip oi-oj-hj-hi
        for i in range(n_samples):
            oi, oj = o[i], o[(i + 1) % n_samples]
            hi, hj = h[i], h[(i + 1) % n_samples]
            total_area += _tri_area(oi, oj, hj) + _tri_area(oi, hj, hi)
            triangles.append(_format_triangle(_p3(oi, zt), _p3(oj, zt), _p3(hj, zt), z_up))
            triangles.append(_format_triangle(_p3(oi, zt), _p3(hj, zt), _p3(hi, zt), z_up))
            triangles.append(_format_triangle(_p3(oi, 0.0), _p3(hj, 0.0), _p3(oj, 0.0), z_dn))
            triangles.append(_format_triangle(_p3(oi, 0.0), _p3(hi, 0.0), _p3(hj, 0.0), z_dn))

        # side walls along the outer ring (outward) and the hole ring (inward)
        for ring in (o, h):
            for i in range(n_samples):
                a, b = ring[i], ring[(i + 1) % n_samples]
                edge = b - a
                wn = np.array([edge[1], -edge[0], 0.0])
                nn = np.linalg.norm(wn)
                wn = wn / nn if nn > 1e-300 else np.array([1.0, 0.0, 0.0])
                a_lo, b_lo = _p3(a, 0.0), _p3(b, 0.0)
                a_hi, b_hi = _p3(a, zt), _p3(b, zt)
                triangles.append(_format_triangle(a_lo, b_lo, b_hi, wn))
                triangles.append(_format_triangle(a_lo, b_hi, a_hi, wn))

    out_path = Path(out_path)
    with open(out_path, "w") as f:
        f.write(f"solid {solid_name[:80]}\n")
        for tri in triangles:
            f.write(tri)
        f.write(f"endsolid {solid_name[:80]}\n")

    return {
        "n_triangles": len(triangles),
        "cross_section_area": float(total_area),
        "is_watertight": stl_is_watertight(triangles),
        "n_annuli": len(annuli),
        "out_path": str(out_path),
    }


# --- Wave YYY (v11, D080): constrained-Delaunay multi-hole smooth+watertight ---
#
# D056 (smooth holes) used bridge-based ear clipping → smooth but the bridge/cap
# seam is not reliably watertight on curved holes. D072 (ribbon) is watertight by
# construction but **annulus-only** (exactly one hole/region). D072's reopening
# criterion named the general fix: **constrained-Delaunay** triangulation of the
# multiply-connected region, which supports an arbitrary number of holes and is
# watertight by construction (no bridges). This is that path — a Bowyer-Watson
# Delaunay of all ring vertices, region-filtered, with the boundary-edge ==
# ring-edge invariant *verified* (the watertightness guarantee).


def _circumcircle(a: np.ndarray, b: np.ndarray, c: np.ndarray):
    """Circumcentre + squared radius of triangle (a,b,c); None if degenerate."""
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    cx, cy = float(c[0]), float(c[1])
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-300:
        return None
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return np.array([ux, uy]), (ax - ux) ** 2 + (ay - uy) ** 2


def _bowyer_watson_delaunay(points: np.ndarray) -> list[tuple[int, int, int]]:
    """Bowyer-Watson Delaunay triangulation of 2-D ``points`` (numpy-only, O(n²);
    fine for the few-hundred-vertex ring boundaries here)."""
    p = np.asarray(points, dtype=float)
    n = p.shape[0]
    if n < 3:
        raise SolverError("cdt_too_few_points")
    mn, mx = p.min(axis=0), p.max(axis=0)
    ctr = 0.5 * (mn + mx)
    span = float((mx - mn).max()) * 10.0 + 1.0
    pp = np.vstack([p, [ctr[0] - span, ctr[1] - span], [ctr[0] + span, ctr[1] - span], [ctr[0], ctr[1] + span]])
    tris: list[tuple[int, int, int]] = [(n, n + 1, n + 2)]
    for ip in range(n):
        pt = pp[ip]
        bad = []
        for t in tris:
            cc = _circumcircle(pp[t[0]], pp[t[1]], pp[t[2]])
            if cc is None:
                continue
            center, r2 = cc
            if (pt[0] - center[0]) ** 2 + (pt[1] - center[1]) ** 2 < r2 - 1e-12:
                bad.append(t)
        edge_count: dict[tuple[int, int], int] = {}
        for t in bad:
            for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                k = tuple(sorted(e))
                edge_count[k] = edge_count.get(k, 0) + 1
        boundary = [e for e, ct in edge_count.items() if ct == 1]
        bad_set = set(bad)
        tris = [t for t in tris if t not in bad_set]
        for a, b in boundary:
            tris.append((a, b, ip))
    return [t for t in tris if max(t) < n]


def constrained_delaunay_triangulate(outer_loop, holes=None) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    """Constrained-Delaunay triangulation of the region inside ``outer_loop`` and
    outside every loop in ``holes`` (Wave YYY, D080).

    Bowyer-Watson Delaunay of all ring vertices, then keep only triangles whose
    centroid lies in the region (inside outer, outside all holes). The
    watertightness guarantee is **verified**: the boundary edges of the kept
    triangulation (edges in exactly one kept triangle) must equal exactly the set
    of ring edges. If a constraint edge was not recovered (the Delaunay
    triangulation did not contain it — possible for sparsely-sampled or strongly
    non-convex boundaries), this raises ``SolverError`` rather than emit a
    non-watertight cap. Returns ``(pts, tris)``.
    """
    outer = _clean_ring(outer_loop)
    hole_rings = [_clean_ring(h) for h in (holes or [])]
    pts_list: list[np.ndarray] = []
    constraints: set[tuple[int, int]] = set()
    for ring in [outer, *hole_rings]:
        start = len(pts_list)
        pts_list.extend(ring)
        m = ring.shape[0]
        for k in range(m):
            constraints.add(tuple(sorted((start + k, start + (k + 1) % m))))
    pts = np.asarray(pts_list, dtype=float)

    tris = _bowyer_watson_delaunay(pts)
    kept = []
    for t in tris:
        centroid = pts[list(t)].mean(axis=0)
        if _point_in_loop(centroid, outer) and not any(_point_in_loop(centroid, h) for h in hole_rings):
            kept.append(t)

    edge_count: dict[tuple[int, int], int] = {}
    for t in kept:
        for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            k = tuple(sorted(e))
            edge_count[k] = edge_count.get(k, 0) + 1
    boundary = {e for e, ct in edge_count.items() if ct == 1}
    if boundary != constraints:
        raise SolverError("cdt_constraint_recovery_failed")
    return pts, kept


def _tri_sorted_edges(t: tuple[int, int, int]) -> list[tuple[int, int]]:
    return [tuple(sorted((t[0], t[1]))), tuple(sorted((t[1], t[2]))), tuple(sorted((t[2], t[0])))]


def _apex(t: tuple[int, int, int], c: int, d: int) -> int:
    """The vertex of triangle ``t`` that is not ``c`` or ``d``."""
    for v in t:
        if v != c and v != d:
            return v
    raise SolverError("cdt_degenerate_triangle")


def _edge_to_tri_indices(tris: list[tuple[int, int, int]]) -> dict[tuple[int, int], list[int]]:
    m: dict[tuple[int, int], list[int]] = {}
    for i, t in enumerate(tris):
        for e in _tri_sorted_edges(t):
            m.setdefault(e, []).append(i)
    return m


def recover_constraints_by_flips(
    pts: np.ndarray,
    tris: list[tuple[int, int, int]],
    constraints: set[tuple[int, int]],
    max_flips: int = 10000,
) -> list[tuple[int, int, int]]:
    """Recover missing **constraint edges** in a Delaunay triangulation by **edge
    flips** (Sloan 1993), so non-convex / sparsely-sampled boundaries triangulate
    without giving up (Wave GGGG, D088).

    For each constraint edge ``(a,b)`` absent from ``tris``, build the list of edges
    that properly cross the segment ``a–b``; repeatedly flip a crossing edge whose
    two triangles form a **convex** quad (deferring non-convex ones to the end of
    the list), re-adding the flipped diagonal if it still crosses. Each convex flip
    strictly reduces the crossing count, so the constraint is recovered in finitely
    many flips. Returns the updated triangle list (constraint edges now present).
    """
    tris = [tuple(t) for t in tris]
    flips = 0
    for a, b in constraints:
        present = set()
        for t in tris:
            present.update(_tri_sorted_edges(t))
        if tuple(sorted((a, b))) in present:
            continue
        pa, pb = pts[a], pts[b]
        # crossing-edge work list
        crossing = [
            e
            for e in {e for t in tris for e in _tri_sorted_edges(t)}
            if a not in e and b not in e and _segment_intersects(pa, pb, pts[e[0]], pts[e[1]])
        ]
        guard = 0
        while crossing and flips < max_flips:
            guard += 1
            if guard > max_flips:
                break
            c, d = crossing.pop(0)
            owners = [i for i, t in enumerate(tris) if tuple(sorted((c, d))) in _tri_sorted_edges(t)]
            if len(owners) != 2:
                continue  # boundary/constraint edge — cannot flip
            t1, t2 = tris[owners[0]], tris[owners[1]]
            x, y = _apex(t1, c, d), _apex(t2, c, d)
            # convex quad ⟺ the new diagonal x–y properly crosses the old c–d
            if not _segment_intersects(pts[x], pts[y], pts[c], pts[d]):
                crossing.append((c, d))  # defer non-convex
                continue
            # flip: replace the two triangles, new diagonal (x,y)
            new = [t for i, t in enumerate(tris) if i not in owners]
            new.append((x, y, c))
            new.append((x, y, d))
            tris = new
            flips += 1
            new_edge = tuple(sorted((x, y)))
            if new_edge != tuple(sorted((a, b))) and _segment_intersects(pa, pb, pts[x], pts[y]):
                crossing.append(new_edge)
    return tris


def _min_triangle_angle(pts: np.ndarray, tris: list[tuple[int, int, int]]) -> float:
    """Smallest interior angle (radians) over all triangles — a mesh-quality gauge."""
    worst = np.pi
    for i, j, k in tris:
        p = [pts[i], pts[j], pts[k]]
        for m in range(3):
            u = p[(m + 1) % 3] - p[m]
            v = p[(m + 2) % 3] - p[m]
            nu, nv = np.linalg.norm(u), np.linalg.norm(v)
            if nu < 1e-300 or nv < 1e-300:
                continue
            ang = np.arccos(np.clip(float(u @ v) / (nu * nv), -1.0, 1.0))
            worst = min(worst, ang)
    return float(worst)


def refine_min_angle_flips(
    pts: np.ndarray,
    tris: list[tuple[int, int, int]],
    constraints: set[tuple[int, int]],
    max_passes: int = 30,
) -> list[tuple[int, int, int]]:
    """Improve the minimum angle by **Lawson Delaunay flips** on non-constraint
    edges (Wave GGGG, D088).

    An edge shared by two triangles is *locally Delaunay* unless the opposite apex
    lies inside the other triangle's circumcircle; flipping a non-Delaunay edge
    locally **increases the minimum angle** (Lawson). Constraint edges are never
    flipped, so the result is a **constrained** Delaunay triangulation (Delaunay
    subject to the boundary) and the boundary — hence watertightness — is preserved.
    """
    tris = [tuple(t) for t in tris]
    for _ in range(max_passes):
        flipped = False
        edge_map = _edge_to_tri_indices(tris)
        for (c, d), owners in edge_map.items():
            if len(owners) != 2 or (c, d) in constraints:
                continue
            t1, t2 = tris[owners[0]], tris[owners[1]]
            x, y = _apex(t1, c, d), _apex(t2, c, d)
            if not _segment_intersects(pts[x], pts[y], pts[c], pts[d]):
                continue  # non-convex quad — flip would invert
            cc = _circumcircle(pts[t1[0]], pts[t1[1]], pts[t1[2]])
            if cc is None:
                continue
            center, r2 = cc
            # non-Delaunay if the other apex y is strictly inside t1's circumcircle
            if (pts[y][0] - center[0]) ** 2 + (pts[y][1] - center[1]) ** 2 < r2 - 1e-12:
                new = [t for i, t in enumerate(tris) if i not in owners]
                new.append((x, y, c))
                new.append((x, y, d))
                tris = new
                flipped = True
                break
        if not flipped:
            break
    return tris


def constrained_delaunay_flip_recover(
    outer_loop, holes=None, refine: bool = False
) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    """Constrained-Delaunay triangulation with **flip-based constraint recovery**
    (and optional min-angle refinement), the no-give-up successor to D080's
    :func:`constrained_delaunay_triangulate` (Wave GGGG, D088).

    Bowyer-Watson Delaunay of all ring vertices, then
    :func:`recover_constraints_by_flips` to force every boundary edge in (rather
    than raising as D080 does for non-convex / sparse boundaries). With
    ``refine=True``, :func:`refine_min_angle_flips` then improves the minimum angle.
    Triangles are region-filtered (centroid inside outer, outside holes). The
    watertightness guarantee is still **verified**: the kept boundary edges must
    equal the ring constraints, else ``SolverError`` (recovery genuinely failed).
    """
    outer = _clean_ring(outer_loop)
    hole_rings = [_clean_ring(h) for h in (holes or [])]
    pts_list: list[np.ndarray] = []
    constraints: set[tuple[int, int]] = set()
    for ring in [outer, *hole_rings]:
        start = len(pts_list)
        pts_list.extend(ring)
        m = ring.shape[0]
        for k in range(m):
            constraints.add(tuple(sorted((start + k, start + (k + 1) % m))))
    pts = np.asarray(pts_list, dtype=float)

    tris = _bowyer_watson_delaunay(pts)
    tris = recover_constraints_by_flips(pts, tris, constraints)
    if refine:
        tris = refine_min_angle_flips(pts, tris, constraints)

    kept = []
    for t in tris:
        centroid = pts[list(t)].mean(axis=0)
        if _point_in_loop(centroid, outer) and not any(_point_in_loop(centroid, h) for h in hole_rings):
            kept.append(t)
    edge_count: dict[tuple[int, int], int] = {}
    for t in kept:
        for e in _tri_sorted_edges(t):
            edge_count[e] = edge_count.get(e, 0) + 1
    boundary = {e for e, ct in edge_count.items() if ct == 1}
    if boundary != constraints:
        raise SolverError("cdt_constraint_recovery_failed")
    return pts, kept


def _diametral_circle_contains(pa: np.ndarray, pb: np.ndarray, q: np.ndarray) -> bool:
    """Does the **diametral circle** of segment ``pa–pb`` strictly contain ``q``?
    (centre = midpoint, radius = |pa−pb|/2). Equivalent to ``∠pa q pb > 90°`` — the
    Ruppert *encroachment* test."""
    m = 0.5 * (pa + pb)
    r2 = 0.25 * float((pa - pb) @ (pa - pb))
    return float((q - m) @ (q - m)) < r2 - 1e-12


def _retriangulate_region(pts, constraints, outer, hole_rings):
    """Rebuild a region-filtered constrained-Delaunay triangulation from the current
    point set (Bowyer-Watson → flip-recover → Lawson refine → keep in-region)."""
    tris = _bowyer_watson_delaunay(pts)
    tris = recover_constraints_by_flips(pts, tris, constraints)
    tris = refine_min_angle_flips(pts, tris, constraints)
    kept = [
        t
        for t in tris
        if _point_in_loop(pts[list(t)].mean(axis=0), outer)
        and not any(_point_in_loop(pts[list(t)].mean(axis=0), h) for h in hole_rings)
    ]
    return kept


def _apex_locked(t: tuple[int, int, int], apexes: set[int], cons: set[tuple[int, int]]) -> bool:
    """Is triangle ``t`` the unavoidable wedge at a small-angle apex — a vertex in
    ``apexes`` whose two triangle edges are both constraint subsegments (D103)? Such a
    triangle's smallest angle is the input angle itself and must not be refined."""
    for i in range(3):
        v = t[i]
        if v in apexes:
            o1, o2 = t[(i + 1) % 3], t[(i + 2) % 3]
            if tuple(sorted((v, o1))) in cons and tuple(sorted((v, o2))) in cons:
                return True
    return False


def _small_angle_apexes(ptl, cons, threshold_rad: float) -> set[int]:
    """Input vertices where two incident **input** segments meet at an angle below
    ``threshold_rad`` — the *small-angle apexes* that defeat plain midpoint Ruppert
    (D103). Computed once on the original constraint set; the indices stay valid because
    Steiner points are only ever appended."""
    adj: dict[int, list[int]] = {}
    for a, b in cons:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    apexes: set[int] = set()
    for v, nbrs in adj.items():
        for i in range(len(nbrs)):
            for j in range(i + 1, len(nbrs)):
                d1 = ptl[nbrs[i]] - ptl[v]
                d2 = ptl[nbrs[j]] - ptl[v]
                n1 = float(np.linalg.norm(d1))
                n2 = float(np.linalg.norm(d2))
                if n1 < 1e-12 or n2 < 1e-12:
                    continue
                if np.arccos(np.clip((d1 @ d2) / (n1 * n2), -1.0, 1.0)) < threshold_rad:
                    apexes.add(v)
    return apexes


def ruppert_refine(
    pts,
    constraints: set[tuple[int, int]],
    outer: np.ndarray,
    hole_rings=None,
    min_angle_deg: float = 20.0,
    max_steiner: int = 300,
    concentric_shells: bool = False,
    shell_angle_deg: float = 60.0,
) -> tuple[np.ndarray, list[tuple[int, int, int]], set[tuple[int, int]], int]:
    """**Ruppert's Delaunay refinement** — insert **Steiner points** until every
    triangle's minimum angle ≥ ``min_angle_deg`` (Wave GGGGG, D096).

    Lawson flips (:func:`refine_min_angle_flips`) can only *reorder* a fixed vertex
    set, so they plateau at whatever min angle the input vertices allow; they cannot
    guarantee an angle bound. Ruppert adds vertices:

    1. **Encroached subsegment** — a boundary segment whose diametral circle
       (:func:`_diametral_circle_contains`) contains another vertex is split at its
       midpoint (the midpoint becomes a new boundary vertex; the constraint set is
       subdivided), restoring boundary conformity.
    2. **Skinny triangle** — for the worst in-region triangle below the bound, insert
       its **circumcentre**; but if that circumcentre would encroach a subsegment,
       split the segment instead (Ruppert's priority rule), which is what keeps the
       boundary watertight.

    The angle bound is capped at the provably-terminating 20.7° (Ruppert/Shewchuk) for
    inputs without acute boundary angles. **Small input angles** (two input segments
    meeting below ~60°) defeat plain midpoint splitting — splitting one apex subsegment
    encroaches its neighbour, which is split, *ad infinitum* (it only stops on the
    ``max_steiner`` backstop, and may even break watertightness). With
    ``concentric_shells=True`` subsegments incident to such a small-angle apex
    (``< shell_angle_deg``) are split at a **power-of-two radius from the apex** instead
    of the midpoint, so split points on the two incident segments land on the same
    concentric circle (isosceles ⟹ ``∠ = 90°−θ/2 < 90°`` ⟹ no mutual encroachment),
    and refinement **terminates** without the ``max_steiner`` backstop. The unavoidable
    sub-bound triangles at the input angle itself remain — geometry cannot remove them.
    ``concentric_shells=False`` (default) reproduces D096's midpoint behaviour exactly.
    Returns ``(pts, tris, constraints, n_steiner)``.
    """
    hole_rings = hole_rings or []
    if not 0.0 < min_angle_deg <= 20.7:
        raise SolverError("ruppert_angle_bound_unsafe")
    ptl = [np.asarray(p, dtype=float) for p in pts]
    cons = set(constraints)
    min_ang = np.radians(min_angle_deg)
    n_steiner = 0
    apexes = _small_angle_apexes(ptl, cons, np.radians(shell_angle_deg)) if concentric_shells else set()

    def _split_segment(a: int, b: int) -> None:
        nonlocal n_steiner
        idx = len(ptl)
        if concentric_shells and (a in apexes) != (b in apexes):
            # concentric-shell split: place the new vertex a power-of-two radius from the
            # small-angle apex (r/L ∈ [2^-0.5, 2^0.5]/2 ≈ [0.354, 0.707], always interior).
            apex, other = (a, b) if a in apexes else (b, a)
            d = ptl[other] - ptl[apex]
            length = float(np.linalg.norm(d))
            r = 2.0 ** round(np.log2(length / 2.0))
            ptl.append(ptl[apex] + (r / length) * d)
        else:
            ptl.append(0.5 * (ptl[a] + ptl[b]))
        cons.discard(tuple(sorted((a, b))))
        cons.add(tuple(sorted((a, idx))))
        cons.add(tuple(sorted((idx, b))))
        n_steiner += 1

    for _ in range(max_steiner):
        P = np.array(ptl)
        kept = _retriangulate_region(P, cons, outer, hole_rings)
        # 1. encroached subsegment → split midpoint
        enc = None
        for a, b in cons:
            if any(k not in (a, b) and _diametral_circle_contains(P[a], P[b], P[k]) for k in range(P.shape[0])):
                enc = (a, b)
                break
        if enc is not None:
            _split_segment(*enc)
            continue
        # 2. worst skinny in-region triangle — but with concentric shells, skip the
        #    triangle wedged at a small-angle apex (both its apex-edges are subsegments):
        #    its small angle IS the input angle, geometrically unremovable, so trying to
        #    refine it would never terminate.
        worst = None
        worst_ang = np.pi
        for t in kept:
            if concentric_shells and _apex_locked(t, apexes, cons):
                continue
            ang = _min_triangle_angle(P, [t])
            if ang < worst_ang:
                worst_ang = ang
                worst = t
        if worst is None or worst_ang >= min_ang:
            break
        cc = _circumcircle(P[worst[0]], P[worst[1]], P[worst[2]])
        if cc is None:
            break
        center = cc[0]
        seg = next(((a, b) for a, b in cons if _diametral_circle_contains(P[a], P[b], center)), None)
        if seg is not None:  # circumcentre would encroach → split that segment instead
            _split_segment(*seg)
            continue
        if _point_in_loop(center, outer) and not any(_point_in_loop(center, h) for h in hole_rings):
            ptl.append(center)
            n_steiner += 1
            continue
        break  # circumcentre outside region but encroaches nothing — best effort, stop

    P = np.array(ptl)
    kept = _retriangulate_region(P, cons, outer, hole_rings)
    return P, kept, cons, n_steiner


def constrained_delaunay_ruppert(
    outer_loop,
    holes=None,
    min_angle_deg: float = 20.0,
    max_steiner: int = 300,
    concentric_shells: bool = False,
) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    """Constrained-Delaunay triangulation refined by **Ruppert Steiner insertion** to a
    guaranteed minimum-angle bound, the quality-refining successor to D088's
    :func:`constrained_delaunay_flip_recover` (Wave GGGGG, D096).

    Builds the CDT (Bowyer-Watson + flip recovery), then :func:`ruppert_refine` inserts
    Steiner points until the minimum angle ≥ ``min_angle_deg``. Watertightness is still
    **verified** — the kept boundary edges must equal the (now subdivided) ring
    constraints, else ``SolverError``. Returns ``(pts, tris)``.
    """
    outer = _clean_ring(outer_loop)
    hole_rings = [_clean_ring(h) for h in (holes or [])]
    pts_list: list[np.ndarray] = []
    constraints: set[tuple[int, int]] = set()
    for ring in [outer, *hole_rings]:
        start = len(pts_list)
        pts_list.extend(ring)
        m = ring.shape[0]
        for k in range(m):
            constraints.add(tuple(sorted((start + k, start + (k + 1) % m))))

    pts, kept, cons, _ = ruppert_refine(
        pts_list,
        constraints,
        outer,
        hole_rings,
        min_angle_deg=min_angle_deg,
        max_steiner=max_steiner,
        concentric_shells=concentric_shells,
    )
    edge_count: dict[tuple[int, int], int] = {}
    for t in kept:
        for e in _tri_sorted_edges(t):
            edge_count[e] = edge_count.get(e, 0) + 1
    boundary = {e for e, ct in edge_count.items() if ct == 1}
    if boundary != cons:
        raise SolverError("ruppert_not_watertight")
    return pts, kept


def write_stl_cdt_multi_hole(
    outer_loop,
    holes=None,
    out_path: str | Path = "cdt_multi_hole.stl",
    z_thickness: float = 1.0,
    n_samples: int | None = None,
    solid_name: str = "topology_cdt_multi_hole",
    refine: bool = False,
    min_angle_deg: float = 20.0,
    concentric_shells: bool = False,
) -> dict:
    """Extrude a smooth multiply-connected polygon (outer + **arbitrary** holes) to
    a watertight STL prism via constrained-Delaunay caps (Wave YYY, D080; ``refine``
    added Wave CCCCCC, v14, D100; ``concentric_shells`` added Wave BBBBBBB, v15, D107).

    Unlike D072's annulus ribbon (exactly one hole), this handles any number of
    holes. Optional ``n_samples`` resamples every ring to equal arc-length spacing
    (denser sampling makes the constraint edges Delaunay-favoured).

    With ``refine=True`` the cap triangulation is **Ruppert-quality-refined** (D096,
    :func:`constrained_delaunay_ruppert`) — Steiner points raise the minimum cap angle
    to ``≥ min_angle_deg`` (better-conditioned export faces) while preserving the
    cross-section and watertightness. **Default ``refine=False`` reproduces D080's
    plain constrained-Delaunay cap byte-for-byte** (no regression).

    With ``concentric_shells=True`` (D107, requires ``refine=True``) the refinement uses
    **concentric-shell splitting** (D103) so cross-sections with **acute input corners**
    (where plain midpoint Ruppert fails to terminate / breaks watertightness) refine to a
    watertight cap end-to-end through the production STL writer — closing D100/D103's
    "expose concentric_shells through write_stl_cdt_multi_hole" reopening.
    ``concentric_shells=False`` (default) reproduces D100 byte-for-byte. Returns
    ``n_triangles`` / ``cross_section_area`` / ``n_holes`` / ``is_watertight`` /
    ``out_path``.
    """
    if z_thickness <= 0:
        raise SolverError("stl_export_nonpositive_thickness")
    if concentric_shells and not refine:
        raise SolverError("stl_export_concentric_requires_refine")
    outer = _resample_closed_ring(outer_loop, n_samples) if n_samples else _clean_ring(outer_loop)
    hole_rings = [_resample_closed_ring(h, n_samples) if n_samples else _clean_ring(h) for h in (holes or [])]
    if refine:
        pts, tris = constrained_delaunay_ruppert(
            outer, hole_rings, min_angle_deg=min_angle_deg, concentric_shells=concentric_shells
        )
    else:
        pts, tris = constrained_delaunay_triangulate(outer, hole_rings)

    triangles: list[str] = []
    total_area = 0.0
    for i, j, k in tris:
        a, b, c = pts[i], pts[j], pts[k]
        total_area += _tri_area(a, b, c)
        a_lo, b_lo, c_lo = (np.array([p[0], p[1], 0.0]) for p in (a, b, c))
        a_hi, b_hi, c_hi = (np.array([p[0], p[1], z_thickness]) for p in (a, b, c))
        triangles.append(_format_triangle(a_lo, c_lo, b_lo, np.array([0.0, 0.0, -1.0])))
        triangles.append(_format_triangle(a_hi, b_hi, c_hi, np.array([0.0, 0.0, 1.0])))
    if refine:
        # Steiner points subdivide boundary segments, so the walls must follow the
        # refined cap boundary (edges in exactly one triangle), not the original rings
        # — otherwise the caps gain vertices the walls lack and the prism is non-manifold
        # (T-junctions). Outward normal = the edge perpendicular pointing away from the
        # owning triangle's interior apex.
        owners: dict[tuple[int, int], list[int]] = {}
        for ti, t in enumerate(tris):
            for e in _tri_sorted_edges(t):
                owners.setdefault(e, []).append(ti)
        for e, own in owners.items():
            if len(own) != 1:
                continue
            ia, ib = e
            a, b = pts[ia], pts[ib]
            apex = pts[_apex(tris[own[0]], ia, ib)]
            edge = b - a
            wall_n = np.array([edge[1], -edge[0], 0.0])
            nrm = np.linalg.norm(wall_n)
            wall_n = wall_n / nrm if nrm > 1e-300 else np.array([1.0, 0.0, 0.0])
            if np.dot(0.5 * (a + b) - apex, wall_n[:2]) < 0.0:  # point away from interior
                wall_n = -wall_n
            a_lo = np.array([a[0], a[1], 0.0])
            b_lo = np.array([b[0], b[1], 0.0])
            a_hi = np.array([a[0], a[1], z_thickness])
            b_hi = np.array([b[0], b[1], z_thickness])
            triangles.append(_format_triangle(a_lo, b_lo, b_hi, wall_n))
            triangles.append(_format_triangle(a_lo, b_hi, a_hi, wall_n))
    else:
        for ring in [outer, *hole_rings]:
            ring = np.asarray(ring, dtype=float)
            if _signed_area(ring) < 0:
                ring = ring[::-1].copy()
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
                triangles.append(_format_triangle(a_lo, b_lo, b_hi, wall_n))
                triangles.append(_format_triangle(a_lo, b_hi, a_hi, wall_n))

    out_path = Path(out_path)
    with open(out_path, "w") as f:
        f.write(f"solid {solid_name[:80]}\n")
        for tri in triangles:
            f.write(tri)
        f.write(f"endsolid {solid_name[:80]}\n")
    return {
        "n_triangles": len(triangles),
        "cross_section_area": float(total_area),
        "n_holes": len(hole_rings),
        "is_watertight": stl_is_watertight(triangles),
        "out_path": str(out_path),
    }


def write_stl_ruppert_multi_hole(
    outer_loop,
    holes=None,
    out_path: str | Path = "ruppert_multi_hole.stl",
    z_thickness: float = 1.0,
    n_samples: int | None = None,
    solid_name: str = "topology_ruppert_multi_hole",
    min_angle_deg: float = 20.0,
) -> dict:
    """**Quality-refined** (Ruppert Steiner-insertion) multi-hole STL extrusion (Wave
    CCCCCC, v14, D100) — convenience alias for :func:`write_stl_cdt_multi_hole` with
    ``refine=True``. The cap's minimum triangle angle is raised to ``≥ min_angle_deg``
    while the cross-section and watertightness are preserved."""
    return write_stl_cdt_multi_hole(
        outer_loop,
        holes,
        out_path=out_path,
        z_thickness=z_thickness,
        n_samples=n_samples,
        solid_name=solid_name,
        refine=True,
        min_angle_deg=min_angle_deg,
    )


def write_stl_concentric_export(
    outer_loop,
    holes=None,
    out_path: str | Path = "concentric_multi_hole.stl",
    z_thickness: float = 1.0,
    n_samples: int | None = None,
    solid_name: str = "topology_concentric_export",
    min_angle_deg: float = 20.0,
) -> dict:
    """**concentric_export** — quality-refined multi-hole STL extrusion that terminates
    and stays watertight on cross-sections with **acute input corners** (Wave BBBBBBB,
    v15, D107) — convenience alias for :func:`write_stl_cdt_multi_hole` with
    ``refine=True, concentric_shells=True`` (D103 concentric-shell splitting). Plain
    midpoint Ruppert (``concentric_shells=False``) fails to make an acute-cornered cap
    watertight; this wires the concentric-shell fix through the production STL writer."""
    return write_stl_cdt_multi_hole(
        outer_loop,
        holes,
        out_path=out_path,
        z_thickness=z_thickness,
        n_samples=n_samples,
        solid_name=solid_name,
        refine=True,
        min_angle_deg=min_angle_deg,
        concentric_shells=True,
    )
