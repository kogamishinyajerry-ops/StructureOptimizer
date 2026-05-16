"""Wave Q: Jupyter rich display + interactive review HTML tests.

Pins:

- ``OptimizationResult._repr_html_`` returns valid HTML containing key fields
- ``OptimizationResult._repr_png_`` returns PNG-magic-prefixed bytes when
  ``mesh_shape`` is populated; ``None`` otherwise (graceful)
- ``BenchmarkConfig._repr_html_`` returns HTML with benchmark name + mesh dims
- ``FEMResult._repr_html_`` returns HTML with compliance + mass
- ``TriangleOptimizationResult._repr_html_`` works
- demo.html contains the interactive script + toggle inputs + panzoom stage
- The PNG encoder helper ``_grayscale_png_bytes`` produces decodable PNGs
  (verified by checking magic + IHDR / IEND chunks)
"""

from __future__ import annotations

import struct

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.demo import generate_demo_html
from structure_optimizer.core.fem2d import FEMResult, solve_linear_elastic
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.repr_html import _grayscale_png_bytes, density_field_repr_png
from structure_optimizer.core.simp import OptimizationResult, run_simp
from structure_optimizer.core.triangle_simp import (
    TriangleOptimizationResult,
    run_simp_triangle,
    split_quad_to_triangles,
)
from structure_optimizer.core.workflow import run_benchmark

# --- _grayscale_png_bytes encoder -------------------------------------


def test_grayscale_png_bytes_has_valid_magic_and_chunks():
    pixels = np.zeros((4, 6), dtype=np.uint8)
    pixels[1:3, 2:4] = 200  # a small grey square
    png = _grayscale_png_bytes(pixels)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    # IHDR chunk follows the 8-byte signature, with length 13
    assert png[8:12] == b"\x00\x00\x00\x0d"
    assert png[12:16] == b"IHDR"
    # IEND must end with CRC of "IEND" alone
    assert png.endswith(b"IEND" + struct.pack(">I", 0xAE426082))
    # IHDR width/height
    width = int.from_bytes(png[16:20], "big")
    height = int.from_bytes(png[20:24], "big")
    assert (width, height) == (6, 4)


def test_grayscale_png_bytes_rejects_non_2d():
    with pytest.raises(ValueError, match="2-D"):
        _grayscale_png_bytes(np.zeros((2, 2, 2), dtype=np.uint8))


def test_density_field_repr_png_round_trip():
    """For a real benchmark mesh + densities, we get a PNG with the right
    pixel dimensions after upscaling."""
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    png = density_field_repr_png(densities, mesh, max_dim=320)
    # IHDR width/height
    width = int.from_bytes(png[16:20], "big")
    height = int.from_bytes(png[20:24], "big")
    # mesh is 30×10 → upscale factor floor(320/30)=10 → 300×100
    assert width == 30 * 10
    assert height == 10 * 10


# --- OptimizationResult rich repr -------------------------------------


def test_optimization_result_repr_html_contains_key_fields():
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    html = result._repr_html_()
    assert "OptimizationResult" in html
    assert "Iterations" in html
    assert "Compliance" in html
    assert "Volume fraction" in html
    # mesh_shape was set by run_simp
    assert result.mesh_shape == (mesh.nelx, mesh.nely)


def test_optimization_result_repr_png_returns_png_when_shape_known():
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    png = result._repr_png_()
    assert png is not None
    assert png.startswith(b"\x89PNG")


def test_optimization_result_repr_png_returns_none_for_default_mesh_shape():
    """If a downstream caller constructs OptimizationResult without passing
    a mesh_shape, _repr_png_ gracefully returns None instead of raising."""
    # Build a stub OptimizationResult with mesh_shape=(0,0) (the default)
    n_elem = 10
    densities = np.full(n_elem, 0.5)
    fake_fem = FEMResult(
        displacements=np.zeros(20),
        compliance=1.0,
        max_displacement=0.1,
        max_stress=2.0,
        mass=0.5,
        element_strain_energy=np.full(n_elem, 0.05),
    )
    result = OptimizationResult(
        densities=densities,
        metrics=[],
        baseline=fake_fem,
        final_analysis=fake_fem,
        stop_reason="max_iterations",
        density_history=[densities.copy()],
        load_case_names=["primary"],
    )
    assert result.mesh_shape == (0, 0)
    assert result._repr_png_() is None


# --- BenchmarkConfig rich repr ----------------------------------------


def test_benchmark_config_repr_html_contains_name_and_mesh():
    config = load_benchmark("cantilever", preset="smoke")
    html = config._repr_html_()
    assert "BenchmarkConfig" in html
    assert "cantilever" in html
    # mesh dim should appear (24×10 in smoke)
    assert "24" in html and "10" in html


# --- FEMResult rich repr ----------------------------------------------


def test_fem_result_repr_html_contains_compliance_and_mass():
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    result = solve_linear_elastic(config, mesh, densities)
    html = result._repr_html_()
    assert "FEMResult" in html
    assert "Compliance" in html
    assert "Mass" in html
    assert "DOFs" in html


# --- TriangleOptimizationResult rich repr ----------------------------


def test_triangle_optimization_result_repr_html():
    mesh = split_quad_to_triangles(8, 4, width=8.0, height=4.0)
    n_nodes_x = 9
    left_nodes = [j * n_nodes_x for j in range(5)]
    fixed_dofs = np.array(sorted({2 * n for n in left_nodes} | {2 * n + 1 for n in left_nodes}))
    force = np.zeros(mesh.ndof)
    force[2 * (2 * n_nodes_x + 8) + 1] = -100.0
    result = run_simp_triangle(
        mesh,
        young_modulus=210000.0,
        poisson_ratio=0.3,
        fixed_dofs=fixed_dofs,
        force=force,
        volume_fraction=0.4,
        max_iterations=5,
        min_iterations=5,
    )
    assert isinstance(result, TriangleOptimizationResult)
    html = result._repr_html_()
    assert "TriangleOptimizationResult" in html
    assert "Compliance" in html


# --- demo.html interactive enhancements -------------------------------


def test_demo_html_contains_interactive_script_and_panzoom():
    run_dir = run_benchmark("mbb_beam", preset="smoke")
    demo_path = generate_demo_html(run_dir)
    html = demo_path.read_text()
    # Wave Q toggles
    assert 'data-toggle="baseline"' in html
    assert 'data-toggle="loadcase"' in html
    assert 'data-toggle="density"' in html
    # Wave Q panzoom stage + buttons
    assert "data-panzoom" in html
    assert 'data-zoom="in"' in html
    assert 'data-zoom="out"' in html
    assert 'data-zoom="reset"' in html
    # Inline script bound the events
    assert "wheel" in html  # zoom-on-scroll
    assert "pointerdown" in html  # drag-pan
