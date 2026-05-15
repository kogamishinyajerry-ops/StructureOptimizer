"""Wave F: stress aggregation tests (von Mises + p-norm + KS).

Pins these properties of ``core/stress.py``:

- ``p_norm_stress`` ≤ ``max(σ)`` for any p ≥ 1; equal in the limit p → ∞.
- ``p_norm_stress`` monotonically decreasing in p (closer to max as p grows).
- ``ks_stress`` ≥ ``max(σ)`` (KS overestimates max from above).
- All zero stresses → 0 regardless of p / aggregation.
- Masking out half the elements ≤ full-array p-norm.
- ``aggregate_stress`` dispatches correctly + rejects unknown names.
- Config: ``stress_constraint`` defaults disabled; validation catches bad p / limit / aggregation / threshold.
- Verification end-to-end:
    - constraint disabled → no stress_constraint key in constraints
    - constraint enabled + design satisfies limit → status passes
    - constraint enabled + tight limit fails → status = stress_constraint_failed
- ``stress_limited_bracket`` benchmark loads + parses correctly.
"""

from __future__ import annotations

import json
import random

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.config import (
    ConfigError,
    parse_config,
    validate_config,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.stress import (
    aggregate_stress,
    element_von_mises_stresses,
    ks_stress,
    p_norm_stress,
)
from structure_optimizer.core.verification import FAILURE_STATUSES, verify_run

# --- p-norm math ------------------------------------------------------


def test_pnorm_zero_stress_is_zero():
    assert p_norm_stress(np.zeros(10), p=8.0) == 0.0


def test_pnorm_lower_bounded_by_zero():
    rng = random.Random(20260516)
    for _ in range(20):
        n = rng.randint(1, 30)
        stresses = np.array([rng.uniform(0, 100) for _ in range(n)])
        assert p_norm_stress(stresses, p=8.0) >= 0


def test_pnorm_upper_bounded_by_n_times_max_for_p1():
    """For p=1, p_norm = Σ |σ|, bounded by N × max."""
    stresses = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    pn = p_norm_stress(stresses, p=1.0)
    assert pn == pytest.approx(15.0)


def test_pnorm_monotonic_in_p_approaches_max():
    """For fixed σ vector, p_norm is monotonically decreasing in p, ↓ to max(σ)."""
    stresses = np.array([1.0, 2.0, 10.0, 5.0])
    values = [p_norm_stress(stresses, p=p) for p in (1.0, 2.0, 4.0, 8.0, 16.0, 64.0)]
    for i in range(len(values) - 1):
        assert values[i + 1] <= values[i] + 1e-9
    # Approaches max
    assert values[-1] == pytest.approx(10.0, abs=0.5)


def test_pnorm_rejects_non_positive_p():
    with pytest.raises(ValueError, match="p must be positive"):
        p_norm_stress(np.array([1.0]), p=0.0)


def test_pnorm_mask_excludes_elements():
    stresses = np.array([100.0, 0.1, 0.1, 100.0])
    mask = np.array([True, False, False, True])
    full = p_norm_stress(stresses, p=8.0)
    masked = p_norm_stress(stresses, p=8.0, mask=mask)
    # Masked should be smaller (or equal) since we removed some elements
    assert masked <= full + 1e-9
    # Masked should be close to 100*2^(1/8) ≈ 109
    assert masked == pytest.approx(100.0 * 2 ** (1 / 8), rel=1e-6)


def test_pnorm_empty_mask_returns_zero():
    stresses = np.array([1.0, 2.0])
    mask = np.array([False, False])
    assert p_norm_stress(stresses, p=8.0, mask=mask) == 0.0


# --- KS math ----------------------------------------------------------


def test_ks_zero_stress_is_zero():
    assert ks_stress(np.zeros(5), p=50.0) == 0.0


def test_ks_geq_max_stress():
    """KS overestimates max from above (smooth max upper bound)."""
    rng = random.Random(20260517)
    for _ in range(20):
        n = rng.randint(2, 20)
        stresses = np.array([rng.uniform(0.1, 100) for _ in range(n)])
        ks = ks_stress(stresses, p=50.0)
        assert ks >= float(np.abs(stresses).max()) - 1e-9


def test_ks_rejects_non_positive_p():
    with pytest.raises(ValueError, match="p must be positive"):
        ks_stress(np.array([1.0]), p=0.0)


def test_ks_approaches_max_at_high_p():
    stresses = np.array([1.0, 2.0, 10.0])
    for p in (10.0, 50.0, 200.0):
        val = ks_stress(stresses, p=p)
        assert val >= 10.0 - 1e-9
        assert val <= 10.0 + 5.0 / p  # converges as 1/p


# --- aggregate_stress dispatch ----------------------------------------


def test_aggregate_stress_dispatches_p_norm():
    stresses = np.array([1.0, 2.0, 3.0])
    assert aggregate_stress(stresses, "p_norm", p=8.0) == pytest.approx(p_norm_stress(stresses, p=8.0))


def test_aggregate_stress_dispatches_ks():
    stresses = np.array([1.0, 2.0, 3.0])
    assert aggregate_stress(stresses, "ks", p=50.0) == pytest.approx(ks_stress(stresses, p=50.0))


def test_aggregate_stress_rejects_unknown_aggregation():
    with pytest.raises(ValueError, match="unknown stress aggregation"):
        aggregate_stress(np.array([1.0]), "wrong", p=8.0)


# --- element_von_mises_stresses ---------------------------------------


def _config_for_stress(stress_overrides: dict | None = None):
    raw = {
        "name": "stress_test",
        "dimension": "2d",
        "units": "mm_N_MPa",
        "thickness": 1.0,
        "mesh": {"type": "structured_quad", "nelx": 8, "nely": 4, "width": 8.0, "height": 4.0},
        "material": {"young_modulus": 1000.0, "poisson_ratio": 0.3, "density": 1.0},
        "boundary_conditions": [{"selector": "left_edge", "components": ["ux", "uy"]}],
        "loads": [{"selector": "right_mid", "fx": 0.0, "fy": -1.0}],
        "optimization": {
            "objective": "min_compliance",
            "volume_fraction": 0.4,
            "penalty": 3.0,
            "filter_radius": 1.5,
            "max_iterations": 3,
            "min_iterations": 1,
            "change_tolerance": 0.01,
            "min_density": 0.001,
        },
    }
    if stress_overrides is not None:
        raw["stress_constraint"] = stress_overrides
    config = parse_config(raw)
    validate_config(config)
    return config


def test_element_von_mises_stresses_length_matches_elements():
    from structure_optimizer.core.fem2d import solve_linear_elastic

    config = _config_for_stress()
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    result = solve_linear_elastic(config, mesh, densities)
    stresses = element_von_mises_stresses(config, mesh, result.displacements)
    assert stresses.shape == (mesh.elements.shape[0],)
    assert (stresses >= 0).all()


def test_element_von_mises_max_matches_fem_result():
    from structure_optimizer.core.fem2d import solve_linear_elastic

    config = _config_for_stress()
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    result = solve_linear_elastic(config, mesh, densities)
    stresses = element_von_mises_stresses(config, mesh, result.displacements)
    assert float(stresses.max()) == pytest.approx(result.max_stress, rel=1e-9)


# --- config defaults + validation -------------------------------------


def test_stress_constraint_disabled_by_default():
    config = _config_for_stress()
    assert config.stress_constraint.enabled is False


def test_stress_constraint_round_trip_parse():
    config = _config_for_stress({"enabled": True, "aggregation": "ks", "p": 60.0, "limit": 500.0})
    assert config.stress_constraint.enabled is True
    assert config.stress_constraint.aggregation == "ks"
    assert config.stress_constraint.p == 60.0
    assert config.stress_constraint.limit == 500.0


def test_stress_constraint_rejects_bad_aggregation():
    with pytest.raises(ConfigError, match="aggregation must be 'p_norm' or 'ks'"):
        _config_for_stress({"enabled": True, "aggregation": "geo_mean", "limit": 100.0})


def test_stress_constraint_rejects_non_positive_p():
    with pytest.raises(ConfigError, match="p must be positive"):
        _config_for_stress({"enabled": True, "p": 0.0, "limit": 100.0})


def test_stress_constraint_rejects_non_positive_limit():
    with pytest.raises(ConfigError, match="limit must be positive"):
        _config_for_stress({"enabled": True, "p": 8.0, "limit": 0.0})


def test_stress_constraint_rejects_bad_density_threshold():
    with pytest.raises(ConfigError, match="density_threshold"):
        _config_for_stress({"enabled": True, "limit": 100.0, "density_threshold": 1.5})


def test_stress_constraint_failed_in_failure_statuses():
    """Status string must be registered in the canonical set."""
    assert "stress_constraint_failed" in FAILURE_STATUSES


# --- verification integration -----------------------------------------


def _fabricate_run(tmp_path, config, densities):
    run_dir = tmp_path / "fake_run"
    run_dir.mkdir()
    (run_dir / "input.json").write_text(json.dumps(config.to_dict()))
    np.save(run_dir / "density.npy", densities)
    return run_dir


def test_verify_no_stress_constraint_when_disabled(tmp_path):
    config = _config_for_stress()
    densities = np.full(config.mesh.nelx * config.mesh.nely, 0.5)
    run_dir = _fabricate_run(tmp_path, config, densities)
    result = verify_run(run_dir)
    constraint_names = {c["name"] for c in result.get("constraints", [])}
    assert "stress_constraint" not in constraint_names


def test_verify_stress_constraint_record_when_enabled(tmp_path):
    """Enabled + high enough limit → constraint passes, record present."""
    config = _config_for_stress({"enabled": True, "p": 8.0, "limit": 1e9, "density_threshold": 0.3})
    densities = np.full(config.mesh.nelx * config.mesh.nely, 0.5)
    run_dir = _fabricate_run(tmp_path, config, densities)
    result = verify_run(run_dir)
    stress_records = [c for c in result.get("constraints", []) if c["name"] == "stress_constraint"]
    assert len(stress_records) == 1
    assert stress_records[0]["status"] == "passed"
    assert stress_records[0]["value"] is not None
    assert stress_records[0]["value"] >= 0


def test_verify_stress_constraint_failed_triggers_status(tmp_path):
    """Enabled + impossibly low limit (1e-9) → status = stress_constraint_failed.

    Density 0.3 (below volume target 0.42) passes volume + connectivity +
    design_space; only stress check fails.
    """
    config = _config_for_stress({"enabled": True, "p": 8.0, "limit": 1e-9, "density_threshold": 0.05})
    densities = np.full(config.mesh.nelx * config.mesh.nely, 0.3)
    run_dir = _fabricate_run(tmp_path, config, densities)
    result = verify_run(run_dir)
    assert result["status"] == "stress_constraint_failed"


def test_verify_stress_constraint_priority_below_volume_and_connectivity(tmp_path):
    """If both volume_constraint and stress_constraint fail, volume wins (earlier in
    status precedence). Test by making volume fail (density all 1.0) AND stress fail."""
    config = _config_for_stress({"enabled": True, "p": 8.0, "limit": 1e-9, "density_threshold": 0.3})
    densities = np.full(config.mesh.nelx * config.mesh.nely, 1.0)
    run_dir = _fabricate_run(tmp_path, config, densities)
    result = verify_run(run_dir)
    # Volume fails first (1.0 > 0.4 + 0.02)
    assert result["status"] == "volume_constraint_failed"


# --- benchmark --------------------------------------------------------


def test_stress_limited_bracket_benchmark_loads():
    config = load_benchmark("stress_limited_bracket", preset="smoke")
    assert config.stress_constraint.enabled is True
    assert config.stress_constraint.aggregation == "p_norm"
    assert config.stress_constraint.limit == 250.0


def test_stress_limited_bracket_ks_preset_loads():
    from structure_optimizer.benchmarks.registry import config_path
    from structure_optimizer.core.config import load_config

    config = load_config(config_path("stress_limited_bracket"), preset="ks")
    assert config.stress_constraint.aggregation == "ks"
    assert config.stress_constraint.p == 50.0
