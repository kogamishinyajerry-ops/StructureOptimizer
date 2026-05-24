# D048 — ear-clipping general-polygon STL + holes (Wave SS)

**Status**: Accepted
**Wave**: SS (v7)
**Supersedes**: none (replaces the centroid-fan cap for general sections)
**Superseded by**: none

## Context

v6 Wave JJ (D039) extruded marching-squares contours with **centroid-fan** caps.
A centroid fan is only valid for **star-convex** loops (the centroid must see
every edge) and cannot represent **holes**. D039's reopening criterion named the
upgrade: ear-clipping triangulation + hole handling (even-odd). v7 Wave SS
delivers it.

## Decision

`core/stl_export.py`:

- `ear_clipping_triangulate(loop)` → `(pts, triangles)`: classic O(n²) ear
  clipping for a simple polygon (concave / non-star-convex OK). Forces CCW
  orientation; a vertex is an ear when its triangle is a left turn and contains
  no other vertex strictly (`_point_strictly_in_tri`, barycentric). A simple
  polygon yields exactly n−2 triangles.
- `triangulate_with_holes(outer, holes)` → `(pts, triangles)`: each hole (forced
  CW, opposite the outer ring) is bridged into the outer polygon via a
  **mutually-visible vertex pair** (`_bridge_visible`, brute-force proper-segment
  test) forming a zero-width slit, then the single merged simple polygon is
  ear-clipped. The bridge is tested against the merged polygon **and every
  not-yet-merged hole** (the bug that an early version missed). Holes processed
  by descending rightmost-x (Eberly's ordering).
- `write_stl_polygon(outer, out_path, holes, z_thickness, …)`: extrudes a general
  (concave, holed) polygon — ear-clipped caps (±z) + side walls for the outer
  ring and every hole ring. Returns `n_triangles`, `cross_section_area`,
  `is_watertight`, `out_path`.
- `stl_is_watertight(triangle_blocks)`: edge-manifold check — every undirected
  edge (vertices rounded to 9 dp) shared by exactly two facets.

## Verification (quantitative)

- **Concave area conservation** (`test_ear_clipping_conserves_area_concave`): an
  L-shape triangulates to area 7.0 to abs 1e-12, with exactly n−2 triangles.
- **Star (non-star-convex)** (`test_ear_clipping_conserves_area_star`): a 5-point
  star conserves area to 1e-12 — the centroid fan cannot.
- **Centroid fan is wrong** (`test_centroid_fan_is_wrong_on_concave_polygon`): the
  old fan gives 11.0 on the L-shape (true 7.0, off by 4.0), while ear clipping
  gives 7.0 to 1e-12 — quantifies *why* the upgrade is needed.
- **Holes even-odd** (`test_holes_even_odd_area_conservation`,
  `test_two_holes_area_conservation`): square−square-hole = 84.0; rectangle with
  two holes = 72−8−4 = 60.0, both to abs 1e-12.
- **Watertight extrusion** (`test_extruded_concave_prism_is_watertight`,
  `test_extruded_holed_prism_is_watertight_and_area_exact`): the star and
  holed-square prisms are edge-manifold (every edge shared by exactly two
  facets) with exact cross-section area.
- **Contracts** (`test_contracts`): <3 vertices / nonpositive thickness →
  `SolverError`. 8 tests, all green. Adjacent `test_marching_squares` +
  `test_stl_export` + `test_geometry_export` (34) unchanged.

## Honest scope notes

- Ear clipping is **O(n²)** — fine for the boundary loops a topology section
  produces (tens–hundreds of vertices), not for million-vertex meshes. A
  monotone-polygon or Delaunay sweep would be O(n log n); deferred (no accuracy
  gain, only speed).
- The hole bridge uses **brute-force visibility** (O(n²·m) proper-segment tests)
  rather than Eberly's ray-cast heuristic. It is slower but far easier to verify
  correct; area conservation is the gate and it passes. Degenerate inputs
  (self-touching rings, holes sharing a vertex with the outer ring) are not
  handled and would need a robustness pass.
- `write_stl_marching_squares` (D039) is **unchanged** — it still uses the
  centroid fan, which is correct for the convex iso-contour loops it typically
  produces. `write_stl_polygon` is the new path for arbitrary sections; wiring
  marching-squares loops (with nested-loop hole detection) through ear clipping
  is a follow-up, not this wave.

## Reopening criteria

- Auto-detect nested marching-squares loops (point-in-polygon parity) and route
  outer+holes through `triangulate_with_holes` from `write_stl_marching_squares`.
- O(n log n) triangulation (monotone decomposition) if section vertex counts grow.
- Robustness for degenerate/self-touching rings (snap-rounding + validation).

## Red lines

numpy-only, ASCII STL, single-line stderr (`SolverError`). `write_stl`,
`write_stl_marching_squares`, `marching_squares_contours`, `polygon_area` are
unchanged; the new code is additive.
