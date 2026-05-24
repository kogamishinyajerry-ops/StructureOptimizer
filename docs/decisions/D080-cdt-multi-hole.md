# D080 — constrained-Delaunay multi-hole smooth + watertight STL (Wave YYY, v11)

**Status**: Accepted
**Wave**: YYY (v11)
**Supersedes**: none (extends D056 / D072)
**Superseded by**: none

## Context

Two earlier geometry waves each won one property and lost the other:

- **D056** (`write_stl_smooth_holes`): marching-squares **smooth** contours →
  even-odd nesting → bridge-based ear-clipping caps. Smooth, multi-hole, but the
  bridge/cap seam is **not reliably watertight** on curved holes.
- **D072** (`write_stl_smooth_watertight_holes`): the annulus **ribbon** —
  watertight by construction, but **annulus-only** (exactly one hole / region;
  raises for 0 or ≥ 2).

D072's recorded reopening criterion:

> *"constrained-Delaunay multi-hole smooth+watertight."*

A constrained-Delaunay triangulation (CDT) of the multiply-connected region needs
**no bridges**, so it triangulates an outer boundary with an **arbitrary number**
of holes and is watertight by construction. v11 Wave YYY delivers it.

## Decision

- **`stl_export._bowyer_watson_delaunay(points)`** — a from-scratch numpy-only
  Bowyer-Watson Delaunay triangulation (super-triangle, incremental insertion,
  cavity re-triangulation), O(n²) — fine for the few-hundred-vertex ring
  boundaries.

- **`stl_export.constrained_delaunay_triangulate(outer_loop, holes=None) →
  (pts, tris)`** — Delaunay of all ring vertices, then keep only triangles whose
  centroid lies in the region (inside outer, outside every hole). **Verifies the
  watertightness invariant**: the boundary edges of the kept triangulation (edges
  in exactly one triangle) must equal exactly the ring-edge set; otherwise it
  raises `SolverError("cdt_constraint_recovery_failed")` rather than emit a
  non-watertight cap.

- **`stl_export.write_stl_cdt_multi_hole(outer_loop, holes=None, out_path=...,
  z_thickness=1.0, n_samples=None, …)`** — extrudes the CDT cap (top + bottom) +
  side walls along every ring edge into a watertight prism, for an **arbitrary
  number of holes**. Returns `n_triangles` / `cross_section_area` / `n_holes` /
  `is_watertight` / `out_path`.

- **`tests/test_cdt_multi_hole.py`** — five quantitative anchors.

## Verification (quantitative anchors)

`tests/test_cdt_multi_hole.py` (5 passed; adjacent regression on
test_smooth_watertight_holes / the smooth/MS STL suite = 34 passed):

1. **genuine multi-hole watertight**: a circle outer with **2** and **3** circular
   holes both produce `is_watertight=True`, and an independent edge-histogram on
   the written 3-hole STL confirms every undirected edge is shared by exactly two
   facets (D072 ribbon = single hole only).
2. **cross-section area ≈ outer − Σ holes**: circle (r=1) − two r=0.18 holes
   matches `π − 2·π·0.18²` to ≤ 1 % (polygon-vs-circle discretisation).
3. **CDT boundary = ring edges**: the kept triangulation's boundary edge count
   equals exactly `n_outer + Σ n_hole` ring edges (the watertightness guarantee).
4. **robustness**: 0-hole (solid disc, area ≈ π) and an **elliptical** outer with
   two holes are both watertight.
5. **error handling**: non-positive thickness and a degenerate (< 3-point) ring
   raise `SolverError`.

## Honest scope notes

- **No constraint-edge recovery via flips.** This is a *Delaunay + region-filter*
  CDT that relies on all ring edges already being Delaunay edges of the vertex
  set. For **densely-sampled smooth** boundaries (the design-relevant case — MS
  contours resampled to many short edges) they are, and the routine verifies it.
  For **sparsely-sampled or strongly non-convex** boundaries a constraint edge may
  be missing; the routine then **raises** (`cdt_constraint_recovery_failed`)
  rather than emit a bad mesh. True constraint recovery by edge-flipping (so it
  never needs to raise) is a reopening item. The honesty here is that it **fails
  loudly**, never silently non-watertight.
- **O(n²) Bowyer-Watson**, no spatial acceleration — adequate for ring boundaries
  (hundreds of points), not for dense interior point clouds.
- **Watertight is topological (edge-manifold), the same standard as D072/D056**:
  every undirected edge shared by exactly two facets. It does **not** guarantee
  geometric non-self-intersection for pathological (e.g. holes overlapping the
  outer) inputs — the region filter assumes well-formed, non-overlapping rings.
- **Caps are 2.5D extrusions** (flat top/bottom at `z=0`/`z_thickness`), not a
  true 3-D surface — consistent with the 2.5D red line.
- **No interior Steiner points / quality refinement**: triangles can be sliver-
  thin where the boundary sampling is uneven; the triangulation is Delaunay of the
  boundary vertices only. Quality CDT (Ruppert/Chew refinement) is a reopening
  item.
- **The area is the polygon area** of the sampled rings (`Σ tri areas`), so it
  approaches the true smooth area only as sampling densifies — the "≈" in the
  area anchor is real (≤ 1 % at the tested sampling).

## Reopening criteria

- **Constraint-edge recovery by edge-flipping** so non-convex / sparsely-sampled
  boundaries triangulate without raising.
- **Quality refinement (Ruppert / Chew)** with interior Steiner points to bound
  the minimum angle and kill slivers.
- **A field-based entry point** (`write_stl_cdt_from_field`) wiring marching-
  squares + even-odd `classify_loops_even_odd` directly into the CDT writer, so a
  raw density field with multiple voids exports in one call (currently the caller
  supplies the rings).
- **Spatial acceleration** (bin / k-d structure) to lift the O(n²) Bowyer-Watson
  for large vertex counts.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
