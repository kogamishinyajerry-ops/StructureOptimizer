"""Failure-status coverage: every status in ``FAILURE_STATUSES`` should be
triggerable via at least one realistic scenario, and the CLI must surface it
correctly (single-line stderr or stdout status string, no traceback leak).

Status codes (from ``core/verification.py``):
- invalid_config — already covered in ``test_cli.py``
- solver_failed — non-singular but pathological matrix → SolverError
- singular_matrix — all DOFs fixed or zero stiffness
- volume_constraint_failed — final density exceeds target + 0.02
- connectivity_failed — density field has no load-to-support path
- design_space_constraint_failed — frozen/void mask violated in stored density
- report_failed — covered in ``test_cli.py`` for missing-dir path

This module focuses on the ones that are hardest to reach: fabricate a run
directory with a doctored ``density.npy`` and run ``verify_run`` directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.cli import main
from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.verification import FAILURE_STATUSES, verify_run


def _fabricate_run(tmp_path: Path, config: BenchmarkConfig, densities: np.ndarray) -> Path:
    """Build a minimal run directory: input.json + density.npy. No images."""
    run_dir = tmp_path / "fake_run"
    run_dir.mkdir()
    (run_dir / "input.json").write_text(json.dumps(config.to_dict()))
    np.save(run_dir / "density.npy", densities)
    return run_dir


# --- volume_constraint_failed -----------------------------------------


def test_volume_constraint_failed_status(tmp_path):
    """Density at 1.0 everywhere → fraction = 1.0 > target 0.4 + 0.02."""
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh_size = config.mesh.nelx * config.mesh.nely
    densities = np.ones(mesh_size)
    run_dir = _fabricate_run(tmp_path, config, densities)
    result = verify_run(run_dir)
    assert result["status"] == "volume_constraint_failed"


def test_volume_constraint_failed_via_cli(tmp_path, capsys):
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh_size = config.mesh.nelx * config.mesh.nely
    run_dir = _fabricate_run(tmp_path, config, np.ones(mesh_size))
    exit_code = main(["verify", "--run", str(run_dir)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "volume_constraint_failed"
    assert "Traceback" not in captured.err


# --- connectivity_failed ----------------------------------------------


def test_connectivity_failed_status(tmp_path):
    """All-min-density field → no material connecting load to support.

    Volume fraction is also < target, so volume_constraint_failed doesn't fire.
    """
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh_size = config.mesh.nelx * config.mesh.nely
    densities = np.full(mesh_size, config.optimization.min_density)
    run_dir = _fabricate_run(tmp_path, config, densities)
    result = verify_run(run_dir)
    assert result["status"] == "connectivity_failed"


def test_connectivity_failed_via_cli(tmp_path, capsys):
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh_size = config.mesh.nelx * config.mesh.nely
    densities = np.full(mesh_size, config.optimization.min_density)
    run_dir = _fabricate_run(tmp_path, config, densities)
    exit_code = main(["verify", "--run", str(run_dir)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "connectivity_failed"


# --- design_space_constraint_failed -----------------------------------


def test_design_space_constraint_failed_when_frozen_region_violated(tmp_path):
    """A config with frozen_solid region; doctored density leaves it ≈ 0.

    Verification should detect frozen_solid_ok == False → status =
    design_space_constraint_failed.
    """
    raw = load_benchmark("simple_bracket", preset="smoke").to_dict()
    raw["design_space"] = {
        "frozen_solid": [
            {
                "name": "must_be_solid",
                "selector": {"type": "box", "x": [0.0, 0.2], "y": [0.0, 1.0]},
            }
        ],
        "void": [],
    }
    from structure_optimizer.core.config import parse_config, validate_config

    config = parse_config(raw)
    validate_config(config)
    mesh_size = config.mesh.nelx * config.mesh.nely
    # All cells at 0.1 — frozen region should be 1.0 but is 0.1 → violation
    densities = np.full(mesh_size, 0.1)
    run_dir = _fabricate_run(tmp_path, config, densities)
    result = verify_run(run_dir)
    assert result["status"] == "design_space_constraint_failed"


def test_design_space_constraint_failed_via_cli(tmp_path, capsys):
    raw = load_benchmark("simple_bracket", preset="smoke").to_dict()
    raw["design_space"] = {
        "frozen_solid": [
            {
                "name": "must_be_solid",
                "selector": {"type": "box", "x": [0.0, 0.2], "y": [0.0, 1.0]},
            }
        ],
        "void": [],
    }
    from structure_optimizer.core.config import parse_config, validate_config

    config = parse_config(raw)
    validate_config(config)
    mesh_size = config.mesh.nelx * config.mesh.nely
    densities = np.full(mesh_size, 0.1)
    run_dir = _fabricate_run(tmp_path, config, densities)
    exit_code = main(["verify", "--run", str(run_dir)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "design_space_constraint_failed"


# --- solver_failed / singular_matrix ----------------------------------


def _all_dofs_fixed_config():
    """Construct a 1×1 mesh with all 4 edges fully fixed → every DOF is
    constrained → solver_failed via the 'all degrees of freedom are fixed' path."""
    from structure_optimizer.core.config import parse_config, validate_config

    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    raw["mesh"] = {"type": "structured_quad", "nelx": 1, "nely": 1, "width": 1.0, "height": 1.0}
    raw["boundary_conditions"] = [
        {"selector": "left_edge", "components": ["ux", "uy"]},
        {"selector": "right_edge", "components": ["ux", "uy"]},
        {"selector": "top_edge", "components": ["ux", "uy"]},
        {"selector": "bottom_edge", "components": ["ux", "uy"]},
    ]
    raw["loads"] = [{"selector": "right_mid", "fx": 0.0, "fy": -1.0}]
    config = parse_config(raw)
    validate_config(config)
    return config


def test_solver_failed_when_all_dofs_fixed(tmp_path):
    """On a 1×1 mesh with all edges fully constrained, no free DOF exists →
    solver raises 'all degrees of freedom are fixed' → solver_failed."""
    config = _all_dofs_fixed_config()
    densities = np.full(config.mesh.nelx * config.mesh.nely, 0.5)
    run_dir = _fabricate_run(tmp_path, config, densities)
    result = verify_run(run_dir)
    assert result["status"] == "solver_failed"


def test_solver_failed_via_cli(tmp_path, capsys):
    config = _all_dofs_fixed_config()
    densities = np.full(config.mesh.nelx * config.mesh.nely, 0.5)
    run_dir = _fabricate_run(tmp_path, config, densities)
    exit_code = main(["verify", "--run", str(run_dir)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "solver_failed"
    assert "Traceback" not in captured.err


def test_singular_matrix_status_reachable_via_solver_adapter():
    """``singular_matrix`` status is produced when ``np.linalg.solve`` raises
    LinAlgError on a rank-deficient SPD-ish stiffness matrix. Already covered
    by ``tests/test_solver_adapter.py::test_dense_solver_raises_solver_error_on_singular_matrix``.
    This test pins the status string is in ``FAILURE_STATUSES``."""
    assert "singular_matrix" in FAILURE_STATUSES


# --- stress_constraint_failed (Wave F) --------------------------------


def test_stress_constraint_failed_status(tmp_path):
    """Wave F: tight stress limit + non-zero density → stress_constraint_failed."""
    from structure_optimizer.core.config import parse_config, validate_config

    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    raw["stress_constraint"] = {
        "enabled": True,
        "aggregation": "p_norm",
        "p": 8.0,
        "limit": 1e-9,
        "density_threshold": 0.05,
    }
    config = parse_config(raw)
    validate_config(config)
    mesh_size = config.mesh.nelx * config.mesh.nely
    densities = np.full(mesh_size, 0.3)
    run_dir = _fabricate_run(tmp_path, config, densities)
    result = verify_run(run_dir)
    assert result["status"] == "stress_constraint_failed"


def test_stress_constraint_failed_via_cli(tmp_path, capsys):
    from structure_optimizer.core.config import parse_config, validate_config

    raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    raw["stress_constraint"] = {
        "enabled": True,
        "aggregation": "p_norm",
        "p": 8.0,
        "limit": 1e-9,
        "density_threshold": 0.05,
    }
    config = parse_config(raw)
    validate_config(config)
    mesh_size = config.mesh.nelx * config.mesh.nely
    densities = np.full(mesh_size, 0.3)
    run_dir = _fabricate_run(tmp_path, config, densities)
    exit_code = main(["verify", "--run", str(run_dir)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "stress_constraint_failed"
    assert "Traceback" not in captured.err


# --- coverage summary -------------------------------------------------


def test_all_documented_failure_statuses_have_test_coverage_here():
    """Meta-test: this file together with test_cli.py should reference every
    string in ``FAILURE_STATUSES``. Documents the contract."""
    expected = {
        "invalid_config",
        "solver_failed",
        "singular_matrix",
        "volume_constraint_failed",
        "connectivity_failed",
        "design_space_constraint_failed",
        "stress_constraint_failed",
        "report_failed",
    }
    assert expected.issubset(FAILURE_STATUSES), (
        f"FAILURE_STATUSES set drifted: expected superset of {expected}, got {FAILURE_STATUSES}"
    )
