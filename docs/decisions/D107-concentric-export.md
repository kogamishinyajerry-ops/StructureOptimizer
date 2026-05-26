# D107 — concentric shells wired into write_stl_cdt_multi_hole (Wave BBBBBBB, v15)

**Status**: Accepted
**Wave**: BBBBBBB (v15)
**Supersedes**: none (closes D100/D103 reopening, extends D100 STL writer)
**Superseded by**: none

## Context

D103 (v14) added concentric-shell splitting to `ruppert_refine` /
`constrained_delaunay_ruppert` so acute-input-angle triangulations terminate and stay
watertight, but recorded as a reopening criterion:

> *"Expose `concentric_shells` through `write_stl_cdt_multi_hole` so acute-cornered
> cross-sections can be exported refined end-to-end."*

D100's `write_stl_cdt_multi_hole(refine=True)` called `constrained_delaunay_ruppert` with
`concentric_shells=False`, so an acute-cornered cross-section could not be exported
refined — the writer would raise `ruppert_not_watertight`. D107 wires the option through.

## Decision

- **`write_stl_cdt_multi_hole(..., concentric_shells: bool = False)`** — passed through to
  `constrained_delaunay_ruppert` on the `refine=True` path. With
  `refine=True, concentric_shells=True`, acute-cornered cross-sections refine to a
  watertight cap end-to-end (D103 concentric-shell splitting + apex-lock). A guard raises
  `stl_export_concentric_requires_refine` if `concentric_shells=True` without `refine`.

- **`write_stl_concentric_export(...)`** — convenience wrapper for
  `write_stl_cdt_multi_hole(refine=True, concentric_shells=True)`; the named
  `concentric_export` production entry point.

- The D100 wall-follows-refined-boundary logic is unchanged and still correct — concentric
  shells only relocate Steiner points; the refined triangulation's boundary edges are
  still what the walls follow.

## Verification (quantitative anchors)

`tests/test_concentric_export.py` (6 passed; adjacent regression on `test_ruppert_stl_export`
+ `test_concentric_shell` + `test_ruppert_refinement`, 18 pass). The wired option **truly
binds** (v15 discipline):

1. **feasible**: `write_stl_concentric_export` on a ~4.8° spike cross-section ⟹
   `is_watertight=True`, `cross_section_area=900.0` (300 body + 600 spike, abs 1e-6).
2. **necessary**: `refine=True, concentric_shells=False` on the same acute input raises
   `ruppert_not_watertight` — the option changes the outcome (D100 alone fails here).
3. **byte-exact D100 (integration铁律)**: `concentric_shells=False, refine=True`
   reproduces the D100 cap **byte-for-byte** (`Path.read_bytes()` equality) on a
   non-acute square-with-hole.
4. **byte-exact D080**: the new param does not perturb the plain `refine=False` path
   byte-for-byte.
5. **guard**: `concentric_shells=True` without `refine` raises
   `stl_export_concentric_requires_refine`.
6. **wrapper equivalence**: `write_stl_concentric_export` is byte-identical to the
   explicit `write_stl_cdt_multi_hole(refine=True, concentric_shells=True)`.

## Honest scope notes

- **Inherits D103's honest limits.** The input acute angle itself is never removed (the
  apex wedge stays at the input angle); concentric shells are a heuristic toward
  isosceles termination, not a formal proof for arbitrary multi-apex inputs (the
  `max_steiner` backstop remains). Multi-apex is Wave GGGGGG (D112).
- **Wall normals use the D100 apex-away heuristic** (a pathological non-convex boundary
  could flip one normal, but edge-manifold watertightness is still guaranteed and
  verified by `stl_is_watertight`).
- **2.5-D extrusion**, not 3-D remeshing.
- **No new geometry algorithm** — this is pure wiring of D103 into the D100 writer; the
  value is end-to-end acute-corner export, not a new method.

## Reopening criteria

- **Multi-apex cross-sections** where two acute corners' shells interfere (Wave GGGGGG /
  D112 or a follow-up).
- **`n_samples` resampling interaction** with concentric shells on curved acute features.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
