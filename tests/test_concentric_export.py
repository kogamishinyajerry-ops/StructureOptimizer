"""Wave BBBBBBB (v15, D107) — concentric shells wired into write_stl_cdt_multi_hole.

Closes D100/D103's reopening ("expose concentric_shells through
write_stl_cdt_multi_hole"). Quantitative anchors proving the wired option **truly binds**
(v15 discipline): (a) feasible — an acute-cornered cross-section refines to a watertight
cap end-to-end; (b) necessary — plain midpoint refine on the same input fails; (c) opt-in
defaults reproduce D100 (refine) and D080 (plain) byte-for-byte.
"""

from pathlib import Path

import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.stl_export import (
    write_stl_cdt_multi_hole,
    write_stl_concentric_export,
)

# 30×10 body with a sharp (~4.8°) leftward spike — acute input corner.
_SPIKE = [[0.0, 0.0], [30.0, 0.0], [30.0, 10.0], [0.0, 10.0], [-120.0, 5.0]]
_SQUARE = [[0.0, 0.0], [6.0, 0.0], [6.0, 6.0], [0.0, 6.0]]
_HOLE = [[[2.0, 2.0], [4.0, 2.0], [4.0, 4.0], [2.0, 4.0]]]


def test_concentric_export_acute_cross_section_watertight(tmp_path):
    """(a) feasible: an acute-cornered cross-section refines to a watertight STL cap."""
    r = write_stl_concentric_export(_SPIKE, out_path=tmp_path / "c.stl")
    assert r["is_watertight"] is True
    assert r["cross_section_area"] == pytest.approx(900.0, abs=1e-6)  # 300 body + 600 spike
    assert r["n_triangles"] > 0


def test_plain_refine_fails_on_acute_export(tmp_path):
    """(b) necessary: refine WITHOUT concentric shells cannot make the acute cap
    watertight — the option changes the outcome (it binds)."""
    with pytest.raises(SolverError, match="ruppert_not_watertight"):
        write_stl_cdt_multi_hole(
            _SPIKE, out_path=tmp_path / "p.stl", refine=True, concentric_shells=False, min_angle_deg=20.0
        )


def test_concentric_default_false_byte_exact_reproduces_d100(tmp_path):
    """(c) integration铁律: concentric_shells=False + refine=True reproduces D100 byte-for-byte."""
    p1, p2 = tmp_path / "d100.stl", tmp_path / "v15.stl"
    write_stl_cdt_multi_hole(_SQUARE, _HOLE, out_path=p1, refine=True, min_angle_deg=20.0)
    write_stl_cdt_multi_hole(_SQUARE, _HOLE, out_path=p2, refine=True, min_angle_deg=20.0, concentric_shells=False)
    assert Path(p1).read_bytes() == Path(p2).read_bytes()


def test_refine_false_byte_exact_reproduces_d080(tmp_path):
    """The new param does not perturb the plain (refine=False) D080 path byte-for-byte."""
    p1, p2 = tmp_path / "a.stl", tmp_path / "b.stl"
    r1 = write_stl_cdt_multi_hole(_SQUARE, _HOLE, out_path=p1)  # plain default
    r2 = write_stl_cdt_multi_hole(_SQUARE, _HOLE, out_path=p2, refine=False, concentric_shells=False)
    assert Path(p1).read_bytes() == Path(p2).read_bytes()
    assert r1["n_triangles"] == r2["n_triangles"]


def test_concentric_requires_refine_guard(tmp_path):
    """concentric_shells=True without refine=True raises (the option only applies to refinement)."""
    with pytest.raises(SolverError, match="stl_export_concentric_requires_refine"):
        write_stl_cdt_multi_hole(_SQUARE, out_path=tmp_path / "g.stl", refine=False, concentric_shells=True)


def test_concentric_export_wrapper_equivalent(tmp_path):
    """write_stl_concentric_export == write_stl_cdt_multi_hole(refine=True, concentric_shells=True)."""
    p1, p2 = tmp_path / "w.stl", tmp_path / "e.stl"
    write_stl_concentric_export(_SPIKE, out_path=p1, solid_name="x")
    write_stl_cdt_multi_hole(
        _SPIKE, out_path=p2, refine=True, concentric_shells=True, min_angle_deg=20.0, solid_name="x"
    )
    assert Path(p1).read_bytes() == Path(p2).read_bytes()
