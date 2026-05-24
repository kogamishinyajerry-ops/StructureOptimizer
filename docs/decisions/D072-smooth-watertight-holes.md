# D072 — smooth AND watertight holed (annulus) triangulation (Wave QQQ, v10)

**Status**: Accepted
**Wave**: QQQ (v10)
**Supersedes**: none (resolves the D056/D064 smooth-vs-watertight tension for rings)
**Superseded by**: none

## Context

Two earlier geometry waves each won one property and lost the other:

- **AAA (D056)** `write_stl_smooth_holes` — *smooth* marching-squares contours,
  but the keyhole **bridge-slit cap is non-watertight** on curved holes
  (re-confirmed here: 339 cap boundary edges vs 336 ring edges, one vertex
  dropped by collinear clipping → non-manifold).
- **III (D064)** `write_stl_slit_free_holes` — *watertight* prism, but a
  **staircase** (cell-resolution) boundary.

D064's recorded reopening criterion was *constrained-Delaunay smooth + watertight
holes*. v10 Wave QQQ resolves the smooth-AND-watertight tension for the **ring
(annulus)** case the rubric targets, without a full CDT.

## Decision

- **`stl_export.write_stl_smooth_watertight_holes(field, x_coords, y_coords,
  out_path, level=0.5, n_samples=128, z_thickness=1.0, solid_name)`** — extracts
  smooth marching-squares contours, groups by even-odd nesting, and for each
  **single-hole (annulus)** region builds an **annulus ribbon prism**:
  1. resample the outer and hole contours to `n_samples` points each by arc
     length (`_resample_closed_ring`);
  2. make both CCW and **angularly align** the hole's start vertex to the
     outer's (roll by nearest angle about the centroid);
  3. connect `i↔i` into a **quad strip** for the top (+z) and bottom (−z) caps;
  4. add side walls along both contours.

  The quad-strip topology is **edge-manifold by construction** — every rung is
  shared by two cap triangles, every contour edge by one cap + one wall triangle
  — *independent of geometry*, so the prism is watertight while the contour stays
  smooth. Cross-section area ≈ outer − hole.

- **`tests/test_smooth_watertight_holes.py`** — five quantitative anchors (below).

## Verification (quantitative anchors)

`tests/test_smooth_watertight_holes.py` (all pass; adjacent regression on the STL
suite):

1. **annulus watertight**: a smooth ring's prism has `is_watertight = True` (vs
   AAA's `False` on the same field), `n_annuli = 1`.
2. **exact triangle count**: `n_triangles = 8·n_samples` per annulus (4 cap + 4
   wall triangles per sample step).
3. **area ≈ smooth contour**: `cross_section_area` vs (smooth outer − smooth
   hole) to ≤ 5e-3 relative (probe: ring 0.00 %, ellipse 0.06 %).
4. **all-2 edge histogram**: parsing the written STL, every undirected edge is
   shared by exactly two facets (`{2: …}` only).
5. **non-circular annulus**: an elliptical annulus is also watertight.
6. **input guards**: zero thickness / `n_samples < 8` / a solid disk with no hole
   raise `SolverError`.

## Honest scope notes

- **Annulus only**: exactly **one hole per region** (the ring case). A region
  with no holes or ≥2 holes raises `SolverError`. The general
  smooth-watertight polygon-with-many-holes still needs a constrained-Delaunay
  triangulation (the original D064 criterion) — *not* delivered here; QQQ delivers
  the ring specialisation.
- The ribbon **resamples** the contours, so the boundary is a smooth polyline at
  `n_samples` resolution — slightly different from the raw MS contour (hence area
  is "≈", not exact). Larger `n_samples` → closer.
- Watertightness is **topological** (edge-manifold); the `i↔i` connection assumes
  both contours are roughly concentric / star-shaped about the outer centroid
  (true for MS annuli). For a wildly non-convex or strongly offset hole the rungs
  could self-intersect *geometrically* while staying edge-manifold — a quality
  (not watertightness) issue.
- Resampling both loops to the **same** `n_samples` is what makes the quad strip
  close; it is not an adaptive/error-driven sampling.
- Caps are a **2.5-D extrusion** (flat top/bottom at constant z), as in all prior
  STL waves — not a true 3-D surface.

## Reopening criteria

- **Constrained-Delaunay** triangulation for general smooth + watertight
  polygons-with-many-holes (the full D064 criterion).
- **Adaptive resampling** (curvature-driven `n_samples`) and **ray-cast angular
  resampling** to guarantee non-self-intersecting rungs for strongly non-convex
  annuli.
- **Multiple holes per region** via a proper polygon-with-holes mesher rather
  than the single-annulus ribbon.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
