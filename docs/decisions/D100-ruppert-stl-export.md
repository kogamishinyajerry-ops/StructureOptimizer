# D100 — Ruppert refinement wired into write_stl_cdt_multi_hole (Wave CCCCCC, v14)

**Status**: Accepted
**Wave**: CCCCCC (v14)
**Supersedes**: none (extends D096 Ruppert + D080 multi-hole STL)
**Superseded by**: none

## Context

D096 (v13 Wave GGGGG) added `constrained_delaunay_ruppert` (Steiner-insertion quality
refinement) but recorded:

> *"Wire `constrained_delaunay_ruppert` into `write_stl_cdt_multi_hole` so exported caps
> are quality-refined, not just constraint-recovered."*

D080's `write_stl_cdt_multi_hole` extrudes a multiply-connected polygon to a watertight
prism using the **plain** constrained-Delaunay cap, which can contain slivers (e.g. an
18.4° angle on a 6×6-with-2×2-hole cap). v14 wires in the Ruppert refinement.

## Decision

- **`stl_export.write_stl_cdt_multi_hole(..., refine=False, min_angle_deg=20.0)`** —
  `refine=True` routes the cap through `constrained_delaunay_ruppert` (D096) instead of
  `constrained_delaunay_triangulate` (D080), raising the cap's minimum angle to
  `≥ min_angle_deg`. **Default `refine=False` reproduces D080 byte-for-byte.**

- **`stl_export.write_stl_ruppert_multi_hole(...)`** — convenience alias for
  `refine=True`.

- **The walls now follow the refined boundary when `refine=True`** (see the defect
  below).

- **`tests/test_ruppert_stl_export.py`** — six anchors.

## Integration defect found and fixed (the v14 discipline working)

The first cut of `refine=True` produced a **non-watertight** STL. Ruppert's
encroachment rule splits boundary segments (Steiner points land *on* the rings), so the
refined **cap** has boundary vertices the **walls** lacked — the wall loop still iterated
the *original* un-subdivided rings, leaving T-junctions where a wall edge spanned two
cap edges. The backward-compat/watertight anchor caught it immediately.

**Fix**: for `refine=True`, generate the walls from the **refined triangulation's
boundary edges** (edges in exactly one triangle), with the outward normal taken as the
edge perpendicular pointing away from the owning triangle's interior apex. `refine=False`
keeps the original ring-based wall loop unchanged (byte-exact). This is exactly the
class of bug the v14 "integration铁律" (modify-production-fn ⟹ backward-compat +
watertight anchors) exists to surface.

## Verification (quantitative anchors)

`tests/test_ruppert_stl_export.py` (6 passed; adjacent regression on
`test_cdt_multi_hole` + `test_ruppert_refinement` + `test_polygon_stl` +
`test_slit_free_stl`, 31 pass):

1. **backward-compat byte-exact (integration铁律)**: `refine=False` is deterministic
   (two runs byte-identical) and `n_triangles == 2·cap + 2·(ring edges)` — the exact
   D080 extrusion formula.
2. **refine adds Steiner triangles**: on the 4×1 sliver, `refine=True` n_triangles >
   `refine=False`.
3. **area preserved**: `cross_section_area` for refine=True == refine=False == 32.0
   (6²−2²) to abs 1e-9.
4. **refined export is watertight**: `is_watertight is True` (the fix); `n_holes == 1`.
5. **min-angle achieved + refinement necessary**: the cap the writer uses
   (`constrained_delaunay_ruppert`) has min angle ≥ 20°, while the plain CDT of the same
   domain is < 20° (so refinement genuinely did work).
6. **wrapper byte-identical**: `write_stl_ruppert_multi_hole` == `...(refine=True)`;
   nonpositive thickness guard raises.

## Honest scope notes

- **Wall normals are geometric, not provably consistently outward across all
  topologies.** The apex-away heuristic gives the correct outward normal for the simple
  convex-outer + convex-hole caps tested; a pathologically non-convex boundary edge
  whose owning-triangle apex sits on the "wrong" side could flip one normal. Watertight
  (edge-manifold) is verified regardless; the *normal orientation* is the softer claim.
- **`refine=True` changes `n_triangles`** (more Steiner points + boundary-edge walls) —
  callers depending on the exact triangle count must not assume the refined count equals
  the coarse one. The return-dict *keys* are unchanged.
- **Ruppert's own limits carry over** (D096): bound capped at 20.7°; acute input
  corners rely on the `max_steiner` backstop (concentric-shell handling is wave FFFFFF).
- **2.5-D extrusion only** — the cap is refined in-plane, then extruded; this is not a
  3-D surface remesh.

## Reopening criteria

- **Robust outward-normal orientation** (ray-cast / winding test) instead of the
  apex-away heuristic, for arbitrary non-convex boundaries.
- **`refine=True` + `n_samples` resampling interplay** — currently refine ignores the
  resampled-then-refined ordering nuances; combining adaptive resampling with Ruppert
  could be tuned.
- **Wire refinement into the other STL writers** (`write_stl_slit_free_holes`,
  `write_stl_smooth_watertight_holes`) for consistency.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
