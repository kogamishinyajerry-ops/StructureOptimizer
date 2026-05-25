# D088 — flip-based CDT constraint recovery + min-angle refinement (Wave GGGG, v12)

**Status**: Accepted
**Wave**: GGGG (v12)
**Supersedes**: none (extends D080)
**Superseded by**: none

## Context

D080 (v11 Wave YYY) added `constrained_delaunay_triangulate`: Bowyer-Watson
Delaunay + region filter, then **verify** every boundary edge survived — and
**raise** `cdt_constraint_recovery_failed` if the unconstrained Delaunay had
crossed a boundary edge (common for non-convex / sparsely-sampled rings). Its
recorded reopening criterion:

> *"flip-based CDT constraint recovery + quality refinement."*

Giving up on a missing constraint is the honest-but-limited D080 behaviour. v12
Wave GGGG **recovers** the missing edges by flips (the standard Sloan algorithm) so
those boundaries triangulate watertightly, and optionally refines mesh quality.

## Decision

- **`stl_export.recover_constraints_by_flips(pts, tris, constraints)`** — for each
  absent constraint edge `(a,b)`, build the list of edges that *properly cross* the
  segment `a–b` and repeatedly flip a crossing edge whose two triangles form a
  **convex** quad (deferring non-convex ones, re-adding a flipped diagonal that
  still crosses). Each convex flip strictly reduces the crossing count → finite
  recovery (Sloan 1993).

- **`stl_export.refine_min_angle_flips(pts, tris, constraints)`** — **Lawson**
  Delaunay flips on **non-constraint** edges only: flip an edge whose opposite apex
  lies inside the neighbour's circumcircle (non-Delaunay), which locally **increases
  the minimum angle**. Constraint edges are never flipped, so the boundary — and
  watertightness — is preserved (a *constrained* Delaunay triangulation).

- **`stl_export.constrained_delaunay_flip_recover(outer_loop, holes=None,
  refine=False)`** — the no-give-up successor to D080: Bowyer-Watson → recover →
  (optional) refine → region-filter → **still verifies** boundary edges == ring
  constraints (raises only if recovery genuinely failed). `_min_triangle_angle` is
  a quality gauge. **D080's `constrained_delaunay_triangulate` is left untouched.**

- **`tests/test_cdt_flip_recovery.py`** — six anchors.

## Verification (quantitative anchors)

`tests/test_cdt_flip_recovery.py` (6 passed; adjacent regression on
test_cdt_multi_hole = 5 passed):

1. **D080 fails, recovery succeeds**: on an 11-vertex star that D080 rejects with
   `cdt_constraint_recovery_failed`, the flip recovery returns `n−2` triangles
   forming a **2-manifold cap** (every edge in 1 or 2 triangles ⟹ watertight prism).
2. **exact tiling + full recovery**: the recovered triangle areas sum to the
   polygon area (≤ 1e-6 — no gaps/overlaps) and **every** boundary constraint edge
   is present.
3. **min-angle refinement strictly improves and preserves**: on a known 10-vertex
   case the worst angle rises 18.75° → 19.38°, area is preserved, and the cap stays
   2-manifold.
4. **refinement never lowers** the min angle on the star (Lawson monotonicity).
5. **convex degeneration**: with no recovery needed, the recovery path yields the
   **same triangle set** as D080.
6. **recovery with a hole** stays watertight and tiles the annular area exactly.

## Honest scope notes

- **`O(n²)`-ish recovery on a triangle list, no half-edge structure.** Each flip
  re-scans the triangle list for the two owners of an edge; fine for the
  few-hundred-vertex rings here, not for large meshes. The `max_flips` guard caps
  pathological loops.
- **Refinement is Lawson flips only — it does *not* insert points (no Ruppert).**
  It maximises the minimum angle *among triangulations of the fixed vertex set*; it
  **cannot** remove a skinny triangle that is forced by the boundary sampling (a
  sliver between two close boundary vertices survives). A genuine angle *bound*
  (e.g. ≥ 20°) needs Steiner-point insertion, which is **not** done — so I claim
  "improves / never lowers the min angle", **not** "guarantees a min-angle bound".
- **Convex-quad flips only.** A crossing edge whose quad is non-convex is deferred;
  recovery relies on Sloan's guarantee that a flippable convex quad always exists
  among the crossing edges. If a degenerate (collinear) configuration leaves none,
  recovery makes no progress and the final boundary-vs-constraints check **still
  raises** — recovery is best-effort, and the watertightness *guarantee* is never
  weakened (it fails loudly rather than emit a leaky cap).
- **Opt-in, default-preserving.** A new function; D080's behaviour (raise on
  non-convex) is unchanged for existing callers.

## Reopening criteria

- **Half-edge / DCEL connectivity** for `O(1)` neighbour lookup and `O(n log n)`
  recovery on larger meshes.
- **Ruppert refinement** (circumcentre Steiner insertion) for a *guaranteed*
  minimum-angle bound, not just a monotone improvement.
- **Recovery for the truly-degenerate collinear case** (perturbation / symbolic
  tie-breaking) so it never falls through to the raise.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
