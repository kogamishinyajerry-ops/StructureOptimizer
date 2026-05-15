"""Wave J: geometry export (boundary segments + SVG + DXF + STL) tests.

Pins these properties:

- ``extract_boundary_segments`` finds the right segments for known density patterns.
- A single solid element produces exactly 4 boundary segments.
- A fully solid mesh produces only the outer perimeter (4 sides × n cells).
- A fully void mesh produces 0 segments.
- SVG file is well-formed XML with the expected number of ``<line>`` elements.
- DXF file is parseable: SECTION/ENTITIES/EOF structure + LINE entity count.
- STL file is parseable ASCII STL: ``solid`` / ``facet`` / ``vertex`` /
  ``endsolid`` keywords + facet count = 12 × n_solid_cells (worst case
  fully-isolated cells; fewer when cells share interior faces).
- CLI ``export`` subcommand works end-to-end for all three formats.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.cli import main
from structure_optimizer.core.config import parse_config, validate_config
from structure_optimizer.core.geometry_export import (
    BoundarySegment,
    extract_boundary_segments,
    write_dxf,
    write_stl_extrusion,
    write_svg,
)
from structure_optimizer.core.mesh import create_structured_mesh


def _small_mesh():
    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    config = parse_config(raw)
    validate_config(config)
    return config, create_structured_mesh(config)


# --- boundary extraction ----------------------------------------------


def test_extract_boundary_all_void_returns_no_segments():
    _, mesh = _small_mesh()
    densities = np.zeros(mesh.elements.shape[0])
    segments = extract_boundary_segments(mesh, densities, threshold=0.5)
    assert segments == []


def test_extract_boundary_all_solid_returns_perimeter_only():
    """All-solid → only outer perimeter, no interior segments."""
    _, mesh = _small_mesh()
    densities = np.ones(mesh.elements.shape[0])
    segments = extract_boundary_segments(mesh, densities, threshold=0.5)
    # Perimeter = 2 × (nelx + nely) cells × 1 segment each
    expected = 2 * (mesh.nelx + mesh.nely)
    assert len(segments) == expected


def test_extract_boundary_single_solid_cell_has_4_segments():
    """A single isolated solid cell in a void sea → exactly 4 boundary edges."""
    _, mesh = _small_mesh()
    densities = np.zeros(mesh.elements.shape[0])
    # Pick a non-edge cell
    cell_x, cell_y = mesh.nelx // 2, mesh.nely // 2
    densities[mesh.element_index(cell_x, cell_y)] = 1.0
    segments = extract_boundary_segments(mesh, densities, threshold=0.5)
    assert len(segments) == 4


def test_extract_boundary_threshold_respected():
    """Density at 0.3 with threshold=0.5 → all void."""
    _, mesh = _small_mesh()
    densities = np.full(mesh.elements.shape[0], 0.3)
    assert extract_boundary_segments(mesh, densities, threshold=0.5) == []
    # Density at 0.3 with threshold=0.2 → all solid
    perimeter_segments = extract_boundary_segments(mesh, densities, threshold=0.2)
    assert len(perimeter_segments) == 2 * (mesh.nelx + mesh.nely)


def test_extract_boundary_segments_are_axis_aligned():
    """Every segment must be either purely horizontal (y1==y2) or purely vertical (x1==x2)."""
    _, mesh = _small_mesh()
    densities = np.full(mesh.elements.shape[0], 1.0)
    densities[mesh.element_index(0, 0)] = 0.0  # punch a hole
    segments = extract_boundary_segments(mesh, densities, threshold=0.5)
    for seg in segments:
        is_horizontal = seg.y1 == seg.y2
        is_vertical = seg.x1 == seg.x2
        assert is_horizontal or is_vertical


def test_boundary_segment_is_frozen_dataclass():
    from dataclasses import FrozenInstanceError

    seg = BoundarySegment(0.0, 0.0, 1.0, 0.0)
    with pytest.raises(FrozenInstanceError):
        seg.x1 = 99.0  # type: ignore[misc]


# --- SVG export -------------------------------------------------------


def test_svg_file_parses_as_xml(tmp_path):
    _, mesh = _small_mesh()
    densities = np.ones(mesh.elements.shape[0])
    out = write_svg(tmp_path / "out.svg", mesh, densities)
    assert out.exists()
    tree = ET.parse(out)
    root = tree.getroot()
    assert root.tag.endswith("svg")
    # Width / height attribs match mesh
    assert float(root.get("width") or 0) == mesh.width
    assert float(root.get("height") or 0) == mesh.height


def test_svg_line_count_matches_segments(tmp_path):
    _, mesh = _small_mesh()
    densities = np.ones(mesh.elements.shape[0])
    out = write_svg(tmp_path / "all_solid.svg", mesh, densities)
    content = out.read_text()
    n_lines = content.count("<line")
    assert n_lines == 2 * (mesh.nelx + mesh.nely)


def test_svg_empty_density_field_still_writes(tmp_path):
    _, mesh = _small_mesh()
    densities = np.zeros(mesh.elements.shape[0])
    out = write_svg(tmp_path / "empty.svg", mesh, densities)
    assert out.exists()
    content = out.read_text()
    assert "<svg" in content
    assert "</svg>" in content
    assert "<line" not in content


# --- DXF export -------------------------------------------------------


def test_dxf_file_has_section_entities_eof(tmp_path):
    _, mesh = _small_mesh()
    densities = np.ones(mesh.elements.shape[0])
    out = write_dxf(tmp_path / "out.dxf", mesh, densities)
    content = out.read_text()
    assert "SECTION" in content
    assert "ENTITIES" in content
    assert "ENDSEC" in content
    assert content.strip().endswith("EOF")


def test_dxf_line_entity_count_matches_segments(tmp_path):
    _, mesh = _small_mesh()
    densities = np.ones(mesh.elements.shape[0])
    out = write_dxf(tmp_path / "out.dxf", mesh, densities)
    content = out.read_text()
    # Count "LINE" entity declarations (preceded by "0\nLINE\n")
    line_count = len(re.findall(r"^0\nLINE", content, flags=re.MULTILINE))
    assert line_count == 2 * (mesh.nelx + mesh.nely)


def test_dxf_coordinates_within_mesh_bounds(tmp_path):
    _, mesh = _small_mesh()
    densities = np.ones(mesh.elements.shape[0])
    out = write_dxf(tmp_path / "out.dxf", mesh, densities)
    content = out.read_text()
    # Pull x coords from "10\n<x>" pairs
    x_vals = [float(m) for m in re.findall(r"^10\n([\d.\-]+)", content, flags=re.MULTILINE)]
    assert all(0.0 - 1e-9 <= x <= mesh.width + 1e-9 for x in x_vals)


# --- STL export -------------------------------------------------------


def test_stl_file_has_solid_endsolid_keywords(tmp_path):
    _, mesh = _small_mesh()
    densities = np.ones(mesh.elements.shape[0])
    out = write_stl_extrusion(tmp_path / "out.stl", mesh, densities, extrusion_depth=2.0)
    content = out.read_text()
    assert content.startswith("solid structure_optimizer_density")
    assert content.strip().endswith("endsolid structure_optimizer_density")


def test_stl_facet_count_for_single_solid_cell(tmp_path):
    """One isolated solid cell → 12 facets (2 each for 6 faces)."""
    _, mesh = _small_mesh()
    densities = np.zeros(mesh.elements.shape[0])
    densities[mesh.element_index(mesh.nelx // 2, mesh.nely // 2)] = 1.0
    out = write_stl_extrusion(tmp_path / "out.stl", mesh, densities)
    content = out.read_text()
    n_facets = content.count("facet normal")
    assert n_facets == 12


def test_stl_extrusion_depth_appears_in_vertices(tmp_path):
    _, mesh = _small_mesh()
    densities = np.zeros(mesh.elements.shape[0])
    densities[mesh.element_index(0, 0)] = 1.0
    out = write_stl_extrusion(tmp_path / "out.stl", mesh, densities, extrusion_depth=3.0)
    content = out.read_text()
    # Should contain at least one vertex with z = 3.0
    assert "3.000000" in content


def test_stl_void_field_writes_empty_solid(tmp_path):
    _, mesh = _small_mesh()
    densities = np.zeros(mesh.elements.shape[0])
    out = write_stl_extrusion(tmp_path / "empty.stl", mesh, densities)
    content = out.read_text()
    assert "solid" in content
    assert "endsolid" in content
    assert content.count("facet normal") == 0


# --- CLI export subcommand --------------------------------------------


def _generate_run(tmp_path: Path) -> Path:
    """Run a smoke optimization to generate a real run directory."""
    import os

    os.chdir(tmp_path)
    from structure_optimizer.core.workflow import run_benchmark

    return run_benchmark("mbb_beam", preset="smoke")


def test_cli_export_svg_e2e(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_dir = _generate_run(tmp_path)
    exit_code = main(["export", "--run", str(run_dir), "--format", "svg"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert (run_dir / "geometry.svg").exists()
    assert "geometry.svg" in captured.out


def test_cli_export_dxf_e2e(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_dir = _generate_run(tmp_path)
    exit_code = main(["export", "--run", str(run_dir), "--format", "dxf"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert (run_dir / "geometry.dxf").exists()
    assert "geometry.dxf" in captured.out


def test_cli_export_stl_e2e(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_dir = _generate_run(tmp_path)
    exit_code = main(["export", "--run", str(run_dir), "--format", "stl", "--extrusion-depth", "5.0"])
    assert exit_code == 0
    assert (run_dir / "geometry.stl").exists()
    content = (run_dir / "geometry.stl").read_text()
    assert "5.000000" in content


def test_cli_export_threshold_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_dir = _generate_run(tmp_path)
    # Very high threshold → mostly void → fewer segments
    exit_code = main(["export", "--run", str(run_dir), "--format", "svg", "--threshold", "0.95"])
    assert exit_code == 0


def test_cli_export_rejects_unknown_format(tmp_path):
    with pytest.raises(SystemExit):
        main(["export", "--run", str(tmp_path), "--format", "step"])
