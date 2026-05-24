# D056 — marching-squares nested loops → ear-clipping caps with holes (Wave AAA)

**Status**: Accepted
**Wave**: AAA (v8)
**Supersedes**: none (extends D048's marching-squares smooth STL + D049's ear-clipping)
**Superseded by**: none

## Context

D048 added marching-squares smooth boundaries but capped each contour with a
**centroid fan** — correct only for star-convex loops and with **no hole
support**. D049 added ear-clipping for concave single loops. D048's reopening
criterion named **auto-detect nested MS loops → ear-clipping caps**: a density
field with an interior void (e.g. an annulus) yields an outer contour *and* an
inner contour, and the cap must carve the inner one out. Wave AAA delivers the
even-odd nesting classifier + a holed-cap STL writer.

## Decision

`core/stl_export.py`:

- `classify_loops_even_odd(loops)` → `[(outer, [holes]), ...]`. Sorts loops by
  descending area, then assigns each loop a containment **depth** by ray-casting
  its first vertex against every larger loop (`_point_in_loop`). Even depth = a
  solid outer; odd depth = a hole of its immediate even-depth parent. A
  triply-nested set therefore becomes *outer-with-hole* + *solid island* (2
  groups), which is the physically correct even-odd rule.
- `_clean_ring(loop, tol=1e-9)` removes consecutive duplicate **and collinear**
  vertices, applied once per ring so the cap boundary and the side walls share
  exactly the same vertex set.
- `write_stl_smooth_holes(mesh, densities, out_path, rho_threshold=0.5,
  z_thickness=1.0, ...)` → marching-squares contours → `classify_loops_even_odd`
  → `triangulate_with_holes` cap (bridged ear-clipping, D049) → outer + hole
  side walls. Returns `n_triangles`, `cross_section_area` (outer − holes),
  `n_groups`, `is_watertight`, `out_path`.
- `ear_clipping_triangulate` was revised to also clip **collinear** vertices
  (pass 2 drops a vertex whose cross product is ≤1e-9 without emitting a
  degenerate triangle), so the many near-collinear vertices of a marching-squares
  circle no longer stall the strictly-convex ear search.

## Verification (quantitative)

- **Nesting** (`test_even_odd_nesting_detection`): a square-in-square → 1 group /
  1 hole; two disjoint squares → 2 groups / 0 holes; a triply-nested set →
  outer-with-hole + solid island (2 groups, hole counts {0, 1}). Exact integer
  checks.
- **Area conservation, rectangular hole** (`test_rectangular_hole_is_watertight_and_area_exact`):
  the cap area equals (outer-ring area − hole-ring area) computed independently
  from the marching-squares loops, to 1e-9; the prism is **watertight**.
- **Area conservation, annulus** (`test_annulus_area_conservation`): a
  many-vertex curved hole still conserves area exactly (1e-9) and classifies as
  1 group. 4 tests, all green. Adjacent `test_polygon_stl` + `test_marching_squares`
  + `test_stl_export` (22) unchanged.

## Honest scope notes

- **Watertight is asserted only for clean-cornered (rectangular) holes.** The
  hole is opened with a **zero-width bridge slit** (D049): for a high-vertex
  *curved* hole (an annulus) the slit leaves one boundary traversal un-cancelled,
  so the resulting prism is **not edge-manifold**. This is *not* an AAA
  regression — the pre-existing `write_stl_polygon` (D049) is non-watertight on
  the same annulus rings too; the D049 square-hole test happens to land on the
  well-behaved geometry. Area conservation is exact regardless, because the
  triangulation tiles the holed region correctly; only 3D edge-manifoldness is
  affected.
- The cap is a *physical-units* cross-section, not a normalised one; areas are in
  mesh length units squared.
- This is still 2.5D (prism extrusion); not a general 3D mesh.

## Reopening criteria

- **Slit-free hole triangulation** (constrained Delaunay or a monotone-polygon
  decomposition) so curved-hole prisms are robustly watertight without the bridge
  slit — the well-defined next step for full watertight guarantees.
- Per-group `z_thickness` from a thickness field (variable-height prisms).
- Smoothing the marching-squares staircase (Laplacian / Chaikin) before capping
  to reduce facet count on curved boundaries.

## Red lines

numpy-only, 2D/2.5D, single-line stderr (`SolverError`:
`density_count_mismatch`, `stl_export_nonpositive_thickness`). The existing
`write_stl_marching_squares` / `write_stl_polygon` paths are unchanged; the
nesting + holed-cap code is additive.
