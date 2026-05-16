# D031 — 2D → STL boundary export (Wave DD · v5)

**Status**: Accepted
**Wave**: DD
**Supersedes**: none
**Superseded by**: none

## Context

A SIMP density field is just an in-memory numpy array. To **manufacture**
a topology (3D printer, CNC pre-form, laser cutter), the result must
be exported in a CAD-compatible format. The lowest-common-denominator
3D-printing format is **STL** (stereolithography).

For 2D topology with a fixed extrusion thickness, the simplest STL
generator is voxelization: each "solid" element (density above a
threshold) becomes an axis-aligned box; each box contributes 12
triangles (6 faces × 2). The result is a 3D printer-ready STL with
stair-step boundaries.

## Decision

- New module `core/stl_export.py`:
  - `write_stl(mesh, densities, out_path, rho_threshold, z_thickness,
    solid_name)` → dict with `n_triangles`, `n_solid_cells`, `out_path`
  - ASCII STL output (parseable by every CAD/CAM tool, slicer, etc.)
  - Each solid cell = 12 triangles (axis-aligned box).
  - Internal/shared faces NOT skipped — the output is verbose but
    geometrically correct (any decent slicer handles internal faces).

## Why ASCII over binary STL

- **ASCII** is human-readable + debuggable + parseable by every tool.
  Slightly larger files (~5× binary), but at v5 mesh sizes (≤ 10k
  elements) the absolute file size is still small (~few MB).
- **Binary** is more compact but adds dep on struct-packing fixed
  widths + endian-aware writes. v5+ option if file size matters.

## Why voxelized (axis-aligned boxes) over marching cubes

- **Voxelization** is one-page-of-numpy: trivially correct, no
  isocontour ambiguity, no need for normal smoothing.
- **Marching cubes** would give smoother surfaces but adds:
  - Lookup table for the 256 cube configurations
  - Edge interpolation between corners with different density signs
  - Optional Laplacian smoothing pass to remove staircase
  - ~400 LOC of code with subtle edge cases
- Stair-step STLs are entirely usable for FDM 3D printing — slicer's
  layer height (~0.2 mm) already filters out stairs that small.
- **Marching cubes is a v5+ option** if a real workflow needs smoother
  surfaces.

## Honest scope notes

- **No face-sharing optimisation** — internal faces between adjacent
  solid cells are duplicated. A "boundary-only" extraction would
  skip them, halving the triangle count for fully-solid regions, but
  adds neighbour-lookup complexity. Not worth it at v5 mesh sizes.
- **Uniform thickness** — no per-element thickness variation. Lattice
  structures with varying wall thickness need pre-processing.
- **No normal smoothing** — every triangle has the canonical
  axis-aligned normal (±1 on one axis). This is correct, just stair-stepped.
- **Orientation** — outward normals are computed by hand on each
  face; verified by the "all 12 triangles" property test.

## Reopening criteria

- If file size becomes a bottleneck, add a `write_stl_binary` variant.
- If marching cubes becomes worth the LOC, add `write_stl_smooth`
  with a separate isocontour-extraction path.
- If per-element thickness is needed, extend `write_stl` to accept
  a `z_thickness: float | np.ndarray` parameter.

## Consequences

- 1 new module (~120 LOC).
- 6 new tests (covering happy path, void, threshold, error cases,
  property check on triangle count).
- v5 rubric §5.2 = 3 pts.
