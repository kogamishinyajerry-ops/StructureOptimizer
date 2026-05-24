"""Wave QQQ (v10, D072): smooth AND watertight holed (annulus) triangulation.

Quantitative anchors (exact / analytical, not qualitative trend):
- a **ring (annulus) with a smooth contour is watertight** — every undirected
  edge of the prism is shared by exactly two facets (the AAA bridge-slit cap was
  non-watertight; the III prism was watertight but staircase);
- the **cross-section area ≈ smooth outer − smooth hole** (the ribbon conserves
  the annulus area to a small tolerance);
- the topology is a clean quad ribbon: with ``n_samples`` per contour the prism
  has **exactly ``8·n_samples`` triangles per annulus** (4 cap + 4 wall triangles
  per sample step), and the edge-multiplicity histogram is all-2.

D064's reopening criterion: constrained smooth + watertight holes (here the ring
case, by an angularly-aligned ribbon rather than a constrained-Delaunay mesh).
"""

from __future__ import annotations

import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.stl_export import (
    marching_squares_contours,
    polygon_area,
    write_stl_smooth_watertight_holes,
)


def _grid(fn, n=64):
    xs = np.linspace(0.0, 1.0, n)
    ys = np.linspace(0.0, 1.0, n)
    gx, gy = np.meshgrid(xs, ys, indexing="xy")  # field[j,i] at (xs[i], ys[j])
    return fn(gx, gy).astype(float), xs, ys


def _ring(cx, cy, r_in, r_out):
    def fn(x, y):
        r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        return (r >= r_in) & (r <= r_out)
    return fn


def _expected_annulus_area(field, xs, ys, level=0.5):
    loops = [lp for lp in marching_squares_contours(field, xs, ys, level) if polygon_area(lp) > 1e-12]
    # the two largest loops are the outer + hole of the single annulus
    areas = sorted((polygon_area(lp) for lp in loops), reverse=True)
    return areas[0] - areas[1]


def test_annulus_is_watertight():
    field, xs, ys = _grid(_ring(0.5, 0.5, 0.25, 0.45))
    tmp = Path(tempfile.mktemp(suffix=".stl"))
    try:
        info = write_stl_smooth_watertight_holes(field, xs, ys, tmp, n_samples=96)
        assert info["is_watertight"] is True
        assert info["n_annuli"] == 1
        assert info["n_triangles"] == 8 * 96  # 4 cap + 4 wall per sample step
    finally:
        tmp.unlink(missing_ok=True)


def test_annulus_area_matches_smooth_contour():
    field, xs, ys = _grid(_ring(0.5, 0.5, 0.25, 0.45))
    expected = _expected_annulus_area(field, xs, ys)
    tmp = Path(tempfile.mktemp(suffix=".stl"))
    try:
        info = write_stl_smooth_watertight_holes(field, xs, ys, tmp, n_samples=160)
        rel = abs(info["cross_section_area"] - expected) / expected
        assert rel <= 5e-3, f"area {info['cross_section_area']:.5f} vs smooth {expected:.5f} (rel {rel:.2%})"
    finally:
        tmp.unlink(missing_ok=True)


def test_every_edge_shared_by_exactly_two_facets():
    # parse the written STL and confirm the all-2 edge histogram directly
    field, xs, ys = _grid(_ring(0.5, 0.5, 0.22, 0.42))
    tmp = Path(tempfile.mktemp(suffix=".stl"))
    try:
        write_stl_smooth_watertight_holes(field, xs, ys, tmp, n_samples=64)
        text = tmp.read_text()
        edges: dict[tuple, int] = defaultdict(int)
        for block in text.split("facet normal")[1:]:
            verts = []
            for line in block.splitlines():
                s = line.strip()
                if s.startswith("vertex"):
                    p = s.split()
                    verts.append((round(float(p[1]), 9), round(float(p[2]), 9), round(float(p[3]), 9)))
            assert len(verts) == 3
            for a, b in ((verts[0], verts[1]), (verts[1], verts[2]), (verts[2], verts[0])):
                edges[tuple(sorted((a, b)))] += 1
        hist = defaultdict(int)
        for cnt in edges.values():
            hist[cnt] += 1
        assert set(hist) == {2}, f"non-manifold edge multiplicities present: {dict(hist)}"
    finally:
        tmp.unlink(missing_ok=True)


def test_non_circular_annulus_still_watertight():
    # an elliptical annulus (non-circular smooth contour) must also be watertight
    def fn(x, y):
        ro = (x - 0.5) ** 2 / 0.20 + (y - 0.5) ** 2 / 0.12
        ri = (x - 0.5) ** 2 / 0.08 + (y - 0.5) ** 2 / 0.05
        return (ro <= 1.0) & (ri >= 1.0)

    field, xs, ys = _grid(fn)
    tmp = Path(tempfile.mktemp(suffix=".stl"))
    try:
        info = write_stl_smooth_watertight_holes(field, xs, ys, tmp, n_samples=128)
        assert info["is_watertight"] is True
    finally:
        tmp.unlink(missing_ok=True)


def test_smooth_watertight_input_guards():
    field, xs, ys = _grid(_ring(0.5, 0.5, 0.25, 0.45))
    tmp = Path(tempfile.mktemp(suffix=".stl"))
    try:
        with pytest.raises(SolverError):
            write_stl_smooth_watertight_holes(field, xs, ys, tmp, z_thickness=0.0)
        with pytest.raises(SolverError):
            write_stl_smooth_watertight_holes(field, xs, ys, tmp, n_samples=4)
        # a solid disk (no hole) is not an annulus → guard fires
        solid, sx, sy = _grid(lambda x, y: (x - 0.5) ** 2 + (y - 0.5) ** 2 <= 0.16)
        with pytest.raises(SolverError):
            write_stl_smooth_watertight_holes(solid, sx, sy, tmp, n_samples=64)
    finally:
        tmp.unlink(missing_ok=True)
