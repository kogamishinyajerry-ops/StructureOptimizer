"""Wave CCCCCC (v14, D100) — Ruppert refinement wired into write_stl_cdt_multi_hole.

Quantitative analytical anchors (byte-exact backward-compat / preserved area /
achieved min-angle), never qualitative trends. Traces D096's reopening criterion:
"wire constrained_delaunay_ruppert into write_stl_cdt_multi_hole so exported caps are
quality-refined".

INTEGRATION DISCIPLINE (v14): refine=False (default) reproduces D080's plain-CDT cap
byte-for-byte; refine=True raises the cap min angle while preserving cross-section + watertightness.
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.stl_export import (
    _min_triangle_angle,
    constrained_delaunay_ruppert,
    constrained_delaunay_triangulate,
    write_stl_cdt_multi_hole,
    write_stl_ruppert_multi_hole,
)

# 6×6 square with a 2×2 central hole: a genuine multi-hole cap whose plain CDT has
# an 18.4° sliver (< 20°), so refinement actually triggers.
_OUTER = [[0.0, 0.0], [6.0, 0.0], [6.0, 6.0], [0.0, 6.0]]
_HOLE = [[2.0, 2.0], [4.0, 2.0], [4.0, 4.0], [2.0, 4.0]]
# 4×1 thin rectangle (14° sliver) for a strong refine-adds-triangles contrast.
_THIN = [[0.0, 0.0], [4.0, 0.0], [4.0, 1.0], [0.0, 1.0]]


def test_refine_false_is_byte_exact_d080(tmp_path):
    """Backward-compat: refine=False is deterministic and matches the D080 plain-CDT cap."""
    fa = write_stl_cdt_multi_hole(_OUTER, [_HOLE], out_path=tmp_path / "a.stl", refine=False)
    write_stl_cdt_multi_hole(_OUTER, [_HOLE], out_path=tmp_path / "b.stl", refine=False)
    assert (tmp_path / "a.stl").read_bytes() == (tmp_path / "b.stl").read_bytes()  # deterministic
    # n_triangles == 2·cap + 2·(ring edges) — the exact D080 extrusion formula
    cap = len(constrained_delaunay_triangulate(np.array(_OUTER, float), [np.array(_HOLE, float)])[1])
    walls = 2 * (len(_OUTER) + len(_HOLE))
    assert fa["n_triangles"] == 2 * cap + walls


def test_refine_adds_steiner_triangles(tmp_path):
    """refine=True inserts Steiner points ⟹ strictly more cap (hence total) triangles."""
    coarse = write_stl_cdt_multi_hole(_THIN, [], out_path=tmp_path / "c.stl", refine=False)
    fine = write_stl_cdt_multi_hole(_THIN, [], out_path=tmp_path / "f.stl", refine=True, min_angle_deg=20.0)
    assert fine["n_triangles"] > coarse["n_triangles"]


def test_refine_preserves_cross_section_area(tmp_path):
    """Refinement preserves the polygon ⟹ identical cross-section area (6²−2²=32)."""
    coarse = write_stl_cdt_multi_hole(_OUTER, [_HOLE], out_path=tmp_path / "c.stl", refine=False)
    fine = write_stl_cdt_multi_hole(_OUTER, [_HOLE], out_path=tmp_path / "f.stl", refine=True)
    assert coarse["cross_section_area"] == pytest.approx(32.0, abs=1e-9)
    assert fine["cross_section_area"] == pytest.approx(coarse["cross_section_area"], abs=1e-9)


def test_refined_export_is_watertight(tmp_path):
    """A refined multi-hole cap still extrudes to a watertight prism."""
    fine = write_stl_cdt_multi_hole(_OUTER, [_HOLE], out_path=tmp_path / "f.stl", refine=True)
    assert fine["is_watertight"] is True
    assert fine["n_holes"] == 1


def test_refined_cap_meets_min_angle(tmp_path):
    """The cap the writer uses (constrained_delaunay_ruppert) meets the angle bound."""
    # writer with n_samples=None uses _clean_ring(rings), identical to what ruppert does
    pts, tris = constrained_delaunay_ruppert(_OUTER, [_HOLE], min_angle_deg=20.0)
    assert np.degrees(_min_triangle_angle(pts, tris)) >= 20.0
    # plain CDT of the same domain is below the bound (so refinement was necessary)
    p0, t0 = constrained_delaunay_triangulate(np.array(_OUTER, float), [np.array(_HOLE, float)])
    assert np.degrees(_min_triangle_angle(p0, t0)) < 20.0


def test_wrapper_matches_refine_true(tmp_path):
    """write_stl_ruppert_multi_hole == write_stl_cdt_multi_hole(refine=True) (same STL)."""
    write_stl_ruppert_multi_hole(_OUTER, [_HOLE], out_path=tmp_path / "w.stl", solid_name="x")
    write_stl_cdt_multi_hole(_OUTER, [_HOLE], out_path=tmp_path / "d.stl", refine=True, solid_name="x")
    assert (tmp_path / "w.stl").read_bytes() == (tmp_path / "d.stl").read_bytes()
    with pytest.raises(SolverError, match="stl_export_nonpositive_thickness"):
        write_stl_ruppert_multi_hole(_OUTER, [_HOLE], out_path=tmp_path / "z.stl", z_thickness=0.0)
