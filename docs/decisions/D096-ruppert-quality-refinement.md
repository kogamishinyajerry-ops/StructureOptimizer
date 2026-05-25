# D096 — Ruppert Delaunay refinement (Steiner insertion, min-angle bound) (Wave GGGGG, v13)

**Status**: Accepted
**Wave**: GGGGG (v13)
**Supersedes**: none (extends D088 flip-based CDT)
**Superseded by**: none

## Context

D088 (v12 Wave GGGG) added flip-based constraint recovery + Lawson min-angle flips and
recorded a reopening item:

> *"Lawson flips can only reorder a fixed vertex set, so they cannot guarantee a minimum
> angle. A Ruppert quality refinement that inserts Steiner points at circumcentres (and
> splits encroached subsegments) would give a provable minimum-angle lower bound while
> staying watertight."*

A high-aspect-ratio polygon sampled only at its corners triangulates to a slim
triangle (a 4×1 rectangle ⟹ ~14° min angle). No reordering of those four vertices can
do better — the angle is a property of the *vertex set*, not the connectivity. Lawson
flips plateau; only adding vertices helps.

## Decision

- **`stl_export._diametral_circle_contains(pa, pb, q)`** — the Ruppert **encroachment**
  test: is `q` strictly inside the diametral circle of segment `pa–pb` (⟺ ∠pa q pb >
  90°).

- **`stl_export.ruppert_refine(pts, constraints, outer, hole_rings=None,
  min_angle_deg=20.0, max_steiner=300)`** — Ruppert's algorithm: (1) split any
  **encroached subsegment** at its midpoint (subdividing the constraint set); else (2)
  for the worst in-region triangle below the bound, insert its **circumcentre** — unless
  that circumcentre would encroach a subsegment, in which case split the segment
  instead (Ruppert's priority rule, the key to watertightness). The bound is capped at
  the provably-terminating **20.7°**. Returns `(pts, tris, constraints, n_steiner)`.

- **`stl_export.constrained_delaunay_ruppert(outer_loop, holes=None,
  min_angle_deg=20.0, max_steiner=300)`** — public CDT-with-refinement entry mirroring
  D088's `constrained_delaunay_flip_recover`; **verifies** the kept boundary edges equal
  the subdivided ring constraints (else `SolverError`).

- **`tests/test_ruppert_refinement.py`** — six anchors.

## Verification (quantitative anchors)

`tests/test_ruppert_refinement.py` (6 passed; adjacent regression on
`test_cdt_flip_recovery` + `test_cdt_multi_hole` + `test_polygon_stl`, 26 pass):

1. **Lawson plateaus, Ruppert clears the bound (headline)**: on the 4×1 rectangle the
   Lawson-only refinement stays < 15° (≈ 14.04°); Ruppert reaches ≥ 20° (measured
   26.57°).
2. **Steiner points added, corners preserved**: `n_steiner > 0`, the point count grows
   by exactly `n_steiner`, and the four input corners are unchanged (prefix).
3. **watertight after refinement**: every boundary vertex has degree 2 (closed loop);
   the public entry already raises unless boundary == subdivided constraints.
4. **bound achieved for several thresholds**: for bound ∈ {10, 15, 20}° the resulting
   min angle ≥ the bound.
5. **longer sliver needs more Steiner points**: the 6×1 rectangle (~9.5° corner) needs
   strictly more Steiner points than 4×1 and still reaches ≥ 20°.
6. **angle-bound guard**: a bound > 20.7° (or ≤ 0) raises `ruppert_angle_bound_unsafe`.

## Honest scope notes

- **The bound is capped at 20.7°, not arbitrary.** Ruppert/Shewchuk only guarantee
  termination up to ~20.7° (≈ √2/2 radius-edge ratio) for inputs **without acute
  boundary angles**; the guard refuses higher bounds rather than risk a non-terminating
  loop. This is the honest, theory-backed limit — I do not claim a 30° guarantee.
- **No small-input-angle handling.** If the input polygon itself has an acute corner
  (< the bound), Ruppert can loop forever splitting near that corner; the `max_steiner`
  budget is the only backstop and the watertight check would then likely still pass at a
  worse min angle. The rectangles tested have 90° corners. Concentric-shell / acute-notch
  inputs are a reopening item (they need Shewchuk's "corner lopping" / concentric-shell
  splitting).
- **Re-triangulates globally per insertion (O(n²) Bowyer-Watson each step).** Correct
  and simple for the few-hundred-vertex smoke caps here; not the incremental
  cavity-retriangulation a production mesher would use. `max_steiner` bounds the cost.
- **Quality = min-angle only.** No area/size grading, no boundary-curvature-driven
  sizing function. A target *element size* field is a separate refinement objective, not
  delivered.
- **2-D caps only.** This refines the planar triangulation used for STL end-caps; it is
  not a 3-D tetrahedral mesher (out of the 2.5-D regime by red line).

## Reopening criteria

- **Small-input-angle handling** (concentric-shell segment splitting / corner lopping)
  so acute-cornered polygons refine without the `max_steiner` backstop.
- **Size-graded refinement**: a sizing function (uniform target area, or
  curvature-driven) on top of the min-angle bound.
- **Incremental cavity retriangulation** instead of global Bowyer-Watson per insertion,
  for larger caps.
- **Wire `constrained_delaunay_ruppert` into `write_stl_cdt_multi_hole`** so exported
  caps are quality-refined, not just constraint-recovered.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
