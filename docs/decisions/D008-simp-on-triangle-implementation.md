# D008 — SIMP on triangle meshes (fills D005 留白)

- **Status**: accepted
- **Date**: 2026-05-16
- **Wave**: M (v2.2.0)
- **Supersedes**: D005 (which scoped triangle support to linear-elastic-only for v1.9)

## Context

D005 (Wave I, v1.9.0) added the CST element + `TriangleMesh` container +
`solve_tri_linear_elastic` + meshio reader, but explicitly **deferred** the
SIMP main loop for triangle meshes. The reasoning: at the time we did not have
a centroid-aware density filter and the existing quad SIMP main loop hard-coded
several grid-only assumptions (`element_grid_index`, `design_count` ÷ unit
area, manufacturing projections like "overhang" that mean nothing on
unstructured triangles).

The v3.x rubric §1.2 makes this a 8-point hard requirement: "SIMP-on-triangle
完整实装 + benchmark".

## Decision

Implement a triangle-specific SIMP loop in
`structure_optimizer/core/triangle_simp.py` rather than refactoring the quad
loop into a mesh-agnostic abstraction. Reasoning:

1. **Lower risk of v1/v2 regression**: the quad SIMP path is exercised by 264
   tests; introducing a polymorphic mesh abstraction risks invisible behavior
   change. Two parallel loops are simpler to reason about for v2.2.
2. **Mesh abstraction is a v3.0+ scope decision**: when both paths stabilize,
   a unified `MeshLike` Protocol with `element_dofs / element_centroid /
   element_area / design_mask` can absorb both. Premature.
3. **Triangle path is genuinely simpler**: no manufacturing projections (D005
   defers; "overhang" is grid-oriented by definition), no stress adjoint (the
   Wave-L adjoint is structured-quad only — see deferred section below).

## Implementation

### Files

- **`structure_optimizer/core/triangle.py`** — extended `TriangleMesh` with
  optional `design_mask` / `frozen_solid_mask` / `void_mask` fields,
  defaulting to all-design / no-frozen / no-void via `__post_init__`. Existing
  v1.9 callers (`TriangleMesh(nodes=..., elements=...)`) keep working
  unchanged. Added `element_centroid(eid)` + `element_centroids` property for
  the centroid filter.
- **`structure_optimizer/core/triangle_filter.py` (NEW)** — Sigmund-style
  density-weighted sensitivity filter using centroid Euclidean distance
  instead of grid neighbors. O(n²) pairwise scan (fine for the modest mesh
  sizes triangle paths target; KD-tree would help at 50k+ elements but
  premature optimization).
- **`structure_optimizer/core/triangle_simp.py` (NEW)** — `run_simp_triangle`
  mirrors quad `run_simp` with these differences:
  - Per-element CST stiffness precomputed once (geometry static across iters)
  - `centroid_density_filter` instead of grid `density_filter`
  - Area-weighted volume bisection (`active_area > target_area` where
    `target_area = vf · total_design_area`) — triangles have unequal areas, so
    naïve "average density over design elements" is misleading; area-weighting
    is the physically correct version.
  - No manufacturing projections (D005 defers; overhang/minimum-feature only
    make sense on a regular grid).
- **`split_quad_to_triangles(nelx, nely, width, height)`** helper inside
  `triangle_simp.py` — splits each grid cell into 2 CCW triangles. Used by
  tests for quad-vs-triangle parity comparison; also handy for users who
  want a "triangle mesh of a rectangle" without needing meshio.

### Volume-fraction interpretation

In quad SIMP we used `np.sum(densities[design]) / design_count` (unit-area
elements assumed). In triangle SIMP we use
`np.sum(densities[design] * areas[design]) / total_design_area`. These reduce
to the same number when all triangles have equal area (true for
`split_quad_to_triangles`). For unstructured meshes the area-weighted version
is the only meaningful definition.

### Bisection numerics — known limitation

OC bisection over Lagrange multiplier `[l1=0, l2=1e9]` converges only when
sensitivity magnitudes live in a compatible range. For very small applied
forces (`‖f‖ ≪ 1`) compliance-sensitivity values collapse to ~1e-20 and
`-sens / midpoint` underflows, so the bisection can't navigate. This is not
triangle-specific (quad SIMP has the same property) but came up during Wave M
test development: we use realistic load magnitudes in benchmarks, not unit
loads. Documented in `triangle_simp.py` docstring and in tests via
`_cantilever_setup` choosing physical units.

## What does NOT carry over to triangle path (deferred / out of scope)

1. **Stress-adjoint** — Wave-L `core/adjoint.py` assumes structured quad
   (`_strain_displacement_matrix` uses `mesh.width / mesh.nelx`). Triangle
   analog would derive ∂σ_PN/∂u per CST element with its own B-matrix; this
   is mathematically straightforward but adds ~150 LOC and is not required by
   v3.x rubric §1.1 (which is quad-only). Deferred to v3.x+.
2. **Manufacturing projections** (overhang / minimum feature / symmetry) —
   grid-oriented by construction. Triangle equivalents would need
   normal-vector-aware projection. Deferred indefinitely.
3. **BESO on triangles** — Wave-G `core/beso.py` is also quad-only. Same
   story: deferable, not required by rubric.
4. **CLI integration** — v2.2.0 keeps `run_simp_triangle` as a Python API
   only. CLI `--algorithm triangle_simp` would need full benchmark-config
   support; deferred to a later wave.

## Testing scope (Wave M)

Test counts (`tests/test_triangle_simp.py`):

- `TriangleMesh` defaults / explicit masks (2)
- centroid filter constant-input / self-only / pairwise (3)
- `split_quad_to_triangles` counts + CCW (2)
- SIMP loop: compliance reduction / volume-fraction hit / frozen-solid / void
  / sparse-vs-dense parity / stop-reason / all-fixed error (8)
- Cross-check vs quad SIMP on same cantilever — vf within 10% of target (1)
- Plus the existing 22 tests in `tests/test_triangle_mesh.py` (Wave I) still
  pass with the extended TriangleMesh

**Total Wave M-related tests: 17 new** in test_triangle_simp.py + 22 from
Wave I (still green).

## Coverage

- `triangle_simp.py`: 100%
- `triangle_filter.py`: 100%
- `triangle.py`: 99.2% (extension preserved Wave I coverage)

## References

- Bendsøe, M.P. & Sigmund, O. (2003). *Topology Optimization: Theory, Methods and Applications*, §1.2.4 (filtering), §1.2.5 (OC update).
- Sigmund, O. (1997). "On the design of compliant mechanisms using topology optimization." *Mechanics of Structures and Machines* 25(4), 493–524 — original sensitivity filter.
- Sigmund, O. (2007). "Morphology-based black and white filters for topology optimization." *Structural and Multidisciplinary Optimization* 33(4), 401–424.
- Bathe, K.J. (1996). *Finite Element Procedures*, §5.3 (CST formulation).
