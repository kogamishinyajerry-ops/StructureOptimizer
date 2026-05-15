# D006 — Geometry export: axis-aligned cell-edge boundary, not full marching squares (Wave J / v2.0)

**Status**: Accepted (v2.0.0, 2026-05-16)

## Context

Wave J adds boundary extraction + SVG / DXF / STL export. The textbook
algorithm is **marching squares**: operate on corner values (densities
interpolated to mesh nodes), produce smooth contour polylines that crop
through individual cells. This gives anti-aliased boundary geometry.

But our SIMP/BESO design is **cell-centered**: density is one number per
element. The honest discrete boundary is the union of cell edges between
solid and void elements — axis-aligned, blocky, exactly matching the
discrete design representation.

## Decision

Implement **cell-edge marching squares simplification**:

- Threshold each cell: solid (density ≥ threshold) or void.
- A boundary segment exists between adjacent solid/void cells and at the
  domain boundary if the boundary cell is solid.
- Output: list of axis-aligned `BoundarySegment(x1, y1, x2, y2)` records.
- No chaining into loops, no interpolation, no smoothing.

This is **not** a 2D marching-squares contour; it's the discrete boundary
of a binary indicator function on a regular grid. Both interpretations
are valid; ours matches the cell-centered design representation.

## Alternatives considered

1. **Corner-value marching squares with smoothing**. Rejected: would
   misrepresent the discrete design as a smooth shape; users seeing the
   smoothed boundary might assume the underlying SIMP design has that
   resolution, which it doesn't.
2. **Output polylines / closed loops** instead of raw segments. Deferred:
   downstream tools (CAD, SVG editors) accept raw line lists fine;
   loop-chaining adds complexity without clear value.
3. **STL based on a true 3D mesh** (extrude + cap with smoothed contours).
   Rejected: scope creep — same misrepresentation issue + needs proper
   3D mesh quality control.

## Consequences

- Exported geometry has staircased boundaries. This is **correct** for a
  cell-centered topology design — not a defect.
- Downstream users who want smoothed geometry can post-process the SVG/DXF
  (most CAD tools have "smooth polyline" or "fillet edges" operations).
- The export is exact and deterministic: same density.npy → same SVG byte
  string. Useful for reproducibility tests.
- 2.5D STL is simple "extrude each solid cell into a brick" — the user can
  3D-print or visualize the design without an external CAD step.

## Reopening criteria

- A user demonstrates a real workflow where the smoothed/chained output
  produces better downstream results.
- A user reports a SIMP design where the discrete cell boundary
  misrepresents the intended geometry by more than half a cell width.
- Marching squares becomes mandatory for a future feature (e.g. STEP export,
  which would need curve fitting).
