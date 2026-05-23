# D039 — marching-squares smooth-boundary STL (Wave JJ)

**Status**: Accepted
**Wave**: JJ (v6)
**Supersedes**: none (adds a smooth path beside D023's voxel `write_stl`)
**Superseded by**: none

## Context

v5 Wave DD (D023) shipped `write_stl`: it turns each solid density cell into an
axis-aligned box. The boundary is therefore staircased and its enclosed-area
error vs the true shape is O(h) (one cell-width per boundary step). D023's
limitation note flagged marching-cubes-style iso-contour extraction as the
smoother v5+ option. In 2D this is **marching squares** (no 3D introduced — the
contour is still extruded to a 2.5D prism). v6 adds it.

## Decision

Add to `core/stl_export.py`, beside the untouched voxel `write_stl`:

- `marching_squares_contours(field, x_coords, y_coords, level=0.5)` — extracts
  iso-contour loops from a scalar grid by the 16-case marching-squares table
  with **linear edge interpolation**. Saddle cases (5, 10) are resolved by the
  cell-centre value (asymptotic decider). Segments are stitched into closed
  loops by exact endpoint matching (a crossing shared by two cells interpolates
  identically, so keys match bit-for-bit).
- `polygon_area(loop)` — shoelace absolute area.
- `write_stl_marching_squares(mesh, densities, out_path, ...)` — samples the
  density field at cell centres, extracts the `rho_threshold` contour, and
  extrudes each loop to a prism: linearly-interpolated side walls + centroid-fan
  top/bottom caps. Returns `n_triangles`, `n_loops`, `cross_section_area`.

## Verification (quantitative)

- **Second-order convergence** (`test_disk_area_second_order_convergence`): on a
  smooth disk level set the area error quarters as h halves
  (measured 1.08e-3 → 2.46e-4 → 6.4e-5 → 1.6e-5 for n = 33/65/129/257, ratio
  ≈0.25 = O(h²)); fine-grid relative error < 0.5%. This is the anchor.
- **Beats voxel** (`test_marching_squares_beats_voxel`): at n=65 the
  marching-squares area error is < the voxel (staircase) area error — measured
  ratio MS/voxel ≈ 0.2 across resolutions.
- **Closed contour** (`test_contours_are_closed`): the disk yields exactly one
  non-degenerate loop, closed (first point ≈ last point).
- **Shoelace exactness** (`test_polygon_area_unit_square_exact`): a 2×3
  rectangle loop → 6.0 to ≤1e-12.
- **Valid STL** (`test_write_stl_marching_squares_valid_ascii`): a disk-shaped
  density region writes a parseable ASCII STL; facet count = reported
  `n_triangles` = 4 × Σ(loop segments); cross-section area > 0.
- Contract errors (grid too small, coord mismatch, density mismatch). 7 tests,
  all green. Adjacent `test_stl_export` + `test_geometry_export` (27) unchanged.

## Honest scope notes

- Cell-centre sampling loses a half-cell border: a solid touching the domain
  edge produces an open contour there (handled gracefully — the loop simply
  isn't closed). Interior shapes are unaffected; the convergence anchor uses an
  interior disk.
- Caps are centroid-fan triangulated, watertight for star-convex loops; a loop
  with a re-entrant boundary relative to its centroid could self-overlap in the
  cap. Side walls are always correct. Robust general-polygon triangulation
  (ear-clipping) is a future option.
- Holes (nested loops) are emitted as separate loops; the writer does not yet
  punch a hole through the caps (it fan-fills each loop independently).
- The optimised density field is near-binary, so the contour midpoints sit
  between cells; the O(h²) benefit is fully realised on smooth fields (level
  sets, filtered densities).

## Reopening criteria

- A workflow needing watertight STL for non-star-convex or holed sections →
  add ear-clipping triangulation + even-odd hole handling.
- Full-boundary capture at the domain edge → sample on nodes with ghost padding.

## Red lines

numpy-only, 2.5D extrusion (no 3D solver), single-line stderr — all held.
`write_stl` voxel path and all its callers untouched.
