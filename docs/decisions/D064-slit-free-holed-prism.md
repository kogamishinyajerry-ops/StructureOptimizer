# D064 — slit-free, robustly-watertight holed prism (Wave III)

**Status**: Accepted
**Wave**: III (v9)
**Supersedes**: none (complements D056's smooth bridge-slit cap)
**Superseded by**: none

## Context

D056 (Wave AAA) carved holes into a smooth marching-squares cap with a **zero-width
bridge slit**, which leaves a non-manifold edge for high-vertex *curved* holes — an
annulus extrudes to a **non-watertight** prism (the documented D056 limitation).
D056's reopening criterion named the fix: a **"slit-free hole triangulation
(constrained Delaunay / monotone-polygon decomposition) so curved-hole prisms are
robustly watertight"**. Wave III delivers the simplest such decomposition.

## Decision

`core/stl_export.py`:

- `write_stl_slit_free_holes(mesh, densities, out_path, rho_threshold=0.5,
  z_thickness=1.0, ...)` → dict with `n_triangles`, `cross_section_area`
  (= n_solid_cells·cell_area), `n_solid_cells`, `is_watertight`, `out_path`.
  Each solid grid cell (`density > threshold`) is a trivially y-monotone quad; the
  rasterised region is triangulated cell-by-cell: a 2-triangle top cap (+z) and
  bottom cap (−z) per solid cell with a **consistent bl–tr diagonal** (so shared
  cell–cell edges are interior, count 2), plus a wall quad on every **solid↔void
  (or domain-boundary)** edge. No bridge, no slit — the shell is edge-manifold for
  any edge-connected hole topology.

## Verification (quantitative)

- **Annulus watertight where AAA is not** (`test_annulus_is_watertight_where_aaa_is_not`):
  on the same ring density field, `write_stl_slit_free_holes` →
  `is_watertight=True` while `write_stl_smooth_holes` (D056) → `False`. The
  headline — the curved hole AAA's bridge slit fails on is now robustly watertight.
- **Exact area** (`test_area_equals_solid_cell_count`): `cross_section_area =
  n_solid_cells · cell_area` to 1e-12 (observed annulus 560 cells → 560.0,
  ≈ π(15²−7²)=553).
- **Robust across curved-hole topologies** (`test_property_watertight_over_curved_hole_topologies`):
  four annuli of varying radii + a two-round-hole plate are all watertight with
  exact area (property test).
- **Determinism** (`test_deterministic`) + **contracts** (`test_contracts`:
  `density_count_mismatch`, `stl_export_nonpositive_thickness`). 5 tests, all
  green. Adjacent `test_ms_nesting_stl` + `test_polygon_stl` + `test_marching_squares`
  + `test_stl_export` (26) unchanged.

## Honest scope notes

- **Watertight for edge-connected regions only.** A *diagonal pinch* (two solid
  cells touching only at a corner, as in a checkerboard) is a genuine non-manifold
  point and is honestly reported `is_watertight=False`. Density-filtered
  topology-optimised designs (the real use case) have no such pinches; raw random
  ±threshold fields can — so the property test covers curved-hole topologies, not
  arbitrary noise, and the function docstring states the limitation.
- **Staircase boundary.** This is the *complement* to D056: D056 gives a smooth
  boundary that is fragile on curved holes; D064 gives a cell-resolution (blocky)
  boundary that is robustly watertight. Neither is "smooth AND robustly watertight"
  — that needs a constrained-Delaunay/monotone triangulation of the *MS contour*
  (the remaining reopening item).
- It is the simplest monotone decomposition (per-cell quad), not a CDT of the
  smooth contour; the area is the rasterised cell-count area, not the smooth
  contour area.

## Reopening criteria

- A constrained-Delaunay (or sweep-line monotone) triangulation of the **smooth
  marching-squares contour with holes** — smooth boundary AND robust watertightness
  in one mesh.
- Diagonal-pinch resolution (split the pinch vertex / insert a sliver) so even
  checkerboard fields are watertight.
- Per-cell adaptive height (variable-thickness prism from a thickness field).

## Red lines

numpy-only, 2D/2.5D, single-line stderr (`SolverError`: `density_count_mismatch`,
`stl_export_nonpositive_thickness`). The D056 `write_stl_smooth_holes` and the
marching-squares / polygon writers are unchanged; the slit-free writer is additive.
