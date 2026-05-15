"""Tests for v0.6 manufacturing constraints (symmetry / extrusion / min_member_size).

Strategy:
- Build minimal in-memory configs (avoid touching benchmark JSON files).
- For symmetry & extrusion: run a few SIMP iterations and assert the produced
  density field obeys the projection within a tight numerical tolerance.
- For min_member_size: assert verification reports ``warning`` when the
  configured ``filter_radius`` is too small to enforce the declared length.
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

from structure_optimizer.core.config import (
    BenchmarkConfig,
    ConfigError,
    parse_config,
    validate_config,
)
from structure_optimizer.core.manufacturing import (
    apply_extrusion_projection,
    apply_symmetry_projection,
    evaluate_manufacturing_compliance,
    extrusion_residual,
    symmetry_residual,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.simp import run_simp


def _base_raw_config() -> dict:
    """A small MBB-beam-like config suitable for fast SIMP smoke runs."""
    return {
        "name": "constraint_test",
        "dimension": "2d",
        "units": "mm_N_MPa",
        "thickness": 1.0,
        "mesh": {"type": "structured_quad", "nelx": 12, "nely": 8, "width": 12.0, "height": 8.0},
        "material": {"young_modulus": 1000.0, "poisson_ratio": 0.3, "density": 1.0},
        "boundary_conditions": [{"selector": "left_edge", "components": ["ux", "uy"]}],
        "loads": [{"selector": "right_mid", "fx": 0.0, "fy": -1.0}],
        "optimization": {
            "objective": "min_compliance",
            "volume_fraction": 0.4,
            "penalty": 3.0,
            "filter_radius": 1.5,
            "max_iterations": 5,
            "min_iterations": 5,
            "change_tolerance": 0.01,
            "min_density": 0.001,
        },
    }


def _make_config(manufacturing_constraints: dict | None = None) -> BenchmarkConfig:
    raw = _base_raw_config()
    if manufacturing_constraints is not None:
        raw["manufacturing_constraints"] = manufacturing_constraints
    config = parse_config(raw)
    validate_config(config)
    return config


def test_symmetry_projection_makes_field_mirror_invariant():
    config = _make_config({"symmetry": {"axis": "y", "position": 0.5}})
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    residual = symmetry_residual(mesh, result.densities, config.manufacturing_constraints.symmetry)
    assert residual < 1e-9, f"symmetric SIMP run produced residual {residual}"


def test_extrusion_projection_makes_field_axis_uniform_along_x():
    config = _make_config({"extrusion": {"axis": "x"}})
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    grid = result.densities.reshape(mesh.nely, mesh.nelx)
    # axis='x' → each row collapses to row mean → all cells in a row equal
    for row in range(mesh.nely):
        spread = float(np.max(grid[row, :]) - np.min(grid[row, :]))
        assert spread < 1e-9, f"row {row} not uniform after extrusion-x projection, spread={spread}"


def test_extrusion_projection_makes_field_axis_uniform_along_y():
    config = _make_config({"extrusion": {"axis": "y"}})
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    grid = result.densities.reshape(mesh.nely, mesh.nelx)
    # axis='y' → each column uniform
    for col in range(mesh.nelx):
        spread = float(np.max(grid[:, col]) - np.min(grid[:, col]))
        assert spread < 1e-9, f"col {col} not uniform after extrusion-y projection, spread={spread}"


def test_apply_symmetry_projection_unit_case():
    config = _make_config({"symmetry": {"axis": "y", "position": 0.5}})
    mesh = create_structured_mesh(config)
    # synthetic asymmetric pattern
    grid = np.zeros((mesh.nely, mesh.nelx))
    grid[2, 3] = 1.0
    projected = apply_symmetry_projection(
        mesh, grid.reshape(-1), config.manufacturing_constraints.symmetry
    ).reshape(mesh.nely, mesh.nelx)
    # mirror about y at position 0.5: mirror of row 2 (out of 8) is row 5
    assert projected[2, 3] == pytest.approx(0.5)
    assert projected[5, 3] == pytest.approx(0.5)


def test_apply_extrusion_projection_unit_case():
    config = _make_config({"extrusion": {"axis": "y"}})
    mesh = create_structured_mesh(config)
    grid = np.arange(mesh.nely * mesh.nelx, dtype=float).reshape(mesh.nely, mesh.nelx)
    projected = apply_extrusion_projection(
        mesh, grid.reshape(-1), config.manufacturing_constraints.extrusion
    ).reshape(mesh.nely, mesh.nelx)
    # extrusion along y: each column uniform = mean of that column
    expected_means = grid.mean(axis=0)
    for col in range(mesh.nelx):
        assert np.allclose(projected[:, col], expected_means[col])


def test_min_member_size_compliance_passes_when_filter_large_enough():
    raw = _base_raw_config()
    raw["optimization"]["filter_radius"] = 3.0  # 2 * 3.0 * cell_size(=1.0) = 6 >= target 5
    raw["manufacturing_constraints"] = {"min_member_size": 5.0}
    config = parse_config(raw)
    validate_config(config)
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    report = evaluate_manufacturing_compliance(config, mesh, densities)
    assert report["min_member_size_compliance"]["status"] == "passed"


def test_min_member_size_compliance_warns_when_filter_too_small():
    raw = _base_raw_config()
    raw["optimization"]["filter_radius"] = 1.0  # 2 * 1.0 * 1.0 = 2 < target 5
    raw["manufacturing_constraints"] = {"min_member_size": 5.0}
    config = parse_config(raw)
    validate_config(config)
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    report = evaluate_manufacturing_compliance(config, mesh, densities)
    payload = report["min_member_size_compliance"]
    assert payload["status"] == "warning"
    assert payload["enforced_length"] < payload["min_member_size"]


def test_min_member_size_compliance_missing_when_not_declared():
    config = _make_config()
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    report = evaluate_manufacturing_compliance(config, mesh, densities)
    assert report["min_member_size_compliance"]["status"] == "missing"


def test_extrusion_residual_zero_for_uniform_field():
    config = _make_config({"extrusion": {"axis": "y"}})
    mesh = create_structured_mesh(config)
    uniform_columns = np.tile(np.arange(mesh.nelx, dtype=float), (mesh.nely, 1)).reshape(-1)
    assert (
        extrusion_residual(mesh, uniform_columns, config.manufacturing_constraints.extrusion)
        < 1e-12
    )


def test_validate_rejects_bad_symmetry_axis():
    raw = _base_raw_config()
    raw["manufacturing_constraints"] = {"symmetry": {"axis": "z", "position": 0.5}}
    with pytest.raises(ConfigError, match="symmetry.axis"):
        validate_config(parse_config(raw))


def test_validate_rejects_bad_extrusion_axis():
    raw = _base_raw_config()
    raw["manufacturing_constraints"] = {"extrusion": {"axis": "z"}}
    with pytest.raises(ConfigError, match="extrusion.axis"):
        validate_config(parse_config(raw))


def test_validate_rejects_nonpositive_min_member_size():
    raw = _base_raw_config()
    raw["manufacturing_constraints"] = {"min_member_size": 0.0}
    with pytest.raises(ConfigError, match="min_member_size"):
        validate_config(parse_config(raw))


def test_validate_rejects_symmetry_position_out_of_range():
    raw = _base_raw_config()
    raw["manufacturing_constraints"] = {"symmetry": {"axis": "x", "position": 1.5}}
    with pytest.raises(ConfigError, match="symmetry.position"):
        validate_config(parse_config(raw))


def test_combined_symmetry_and_extrusion_along_orthogonal_axes():
    """Symmetry about y at mid + extrusion along x → field uniform per row AND mirror-symmetric."""
    config = _make_config(
        {"symmetry": {"axis": "y", "position": 0.5}, "extrusion": {"axis": "x"}}
    )
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    grid = result.densities.reshape(mesh.nely, mesh.nelx)
    # extrusion along x: every row uniform
    for row in range(mesh.nely):
        assert float(np.max(grid[row, :]) - np.min(grid[row, :])) < 1e-9
    # symmetry across y at midpoint: row k ≈ row nely-1-k
    for row in range(mesh.nely // 2):
        mirror = mesh.nely - 1 - row
        assert np.max(np.abs(grid[row, :] - grid[mirror, :])) < 1e-9
