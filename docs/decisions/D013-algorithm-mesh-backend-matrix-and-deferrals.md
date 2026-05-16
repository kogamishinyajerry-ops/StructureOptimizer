# D013 — Algorithm × mesh × backend matrix + explicit deferrals

- **Status**: accepted
- **Date**: 2026-05-16
- **Wave**: R (v3.0.0)

## Context

The v3.x rubric §1.4 (4 pts) asks for "algorithm × mesh × backend 矩阵
全跑通": SIMP/BESO × quad/triangle × dense/sparse.

After Waves L–Q, the implemented combinations are:

| algorithm | mesh     | backend | implemented? | test                                  |
|-----------|----------|---------|--------------|---------------------------------------|
| simp      | quad     | dense   | ✅           | `test_quad_algorithm_backend_matrix`  |
| simp      | quad     | sparse  | ✅           | same                                  |
| simp      | triangle | dense   | ✅ (Wave M)  | `test_triangle_simp_backend_matrix`   |
| simp      | triangle | sparse  | ✅ (Wave M)  | same                                  |
| beso      | quad     | dense   | ✅           | `test_quad_algorithm_backend_matrix`  |
| beso      | quad     | sparse  | ✅           | same                                  |
| beso      | triangle | dense   | ❌ deferred  | `test_matrix_documented_deferred_combinations` |
| beso      | triangle | sparse  | ❌ deferred  | same                                  |

So **6 of 8 combinations** are implemented + tested. The two missing
cells (BESO-on-triangle) are documented as deferred here.

## Decision

Score §1.4 as **3 of 4 pts** (75%) — honestly reflecting the missing
BESO-on-triangle cells. We do not pad with stub "BESO triangle =
unsupported" tests that simply assert `NotImplementedError` — that
would be cosmetic.

## Why BESO-on-triangle is deferred

BESO is a hard-kill evolutionary method: rank elements by strain energy
density, kill the worst, restore the best. The math is mesh-agnostic in
principle, but the existing `run_beso` is structured-quad-only because:

1. It assumes uniform element area (rank thresholds use raw element-count
   ratios, not area-weighted volume). Triangle meshes have unequal
   triangle areas, so area-weighted ranking is required for physical
   correctness.
2. The "evolutionary rate" parameter `beso_er` is calibrated for
   structured-quad meshes; behavior on triangles needs revalidation.
3. No real user has asked for BESO-on-triangle; SIMP-on-triangle covers
   the common case.

Total work: ~150 LOC + 5–10 tests + ADR. Not blocking v3.0 launch.
Reopen when:
- A user asks for BESO with imported meshio mesh
- The triangle mesh size (5k+ elements) makes SIMP filter convergence
  slow enough that BESO's hard-kill advantage matters

## Why we did NOT add a stub

`run_beso_triangle = NotImplementedError("deferred")` would technically
satisfy a literal "all 8 cells exist" reading of §1.4. We don't do this
because:

1. The rubric implicitly means *working* cells, not stub functions
2. Stubs accumulate; future readers misread them as "supported"
3. Honest scope > inflated rubric score (the project's North Star)

## Files

- `tests/test_algorithm_mesh_backend_matrix.py` — explicit tests for
  the 6 implemented cells + a `test_matrix_documented_deferred_combinations`
  guard that asserts `available_algorithms()` does NOT contain
  `beso_triangle` (so future contributors know the deferral was intentional)
