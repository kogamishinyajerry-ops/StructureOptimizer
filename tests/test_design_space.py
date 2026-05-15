import copy

import numpy as np
import pytest

from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.config import ConfigError, parse_config, validate_config
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.simp import run_simp


def _design_space_config():
    raw = load_benchmark("simple_bracket", preset="smoke").to_dict()
    raw["optimization"]["max_iterations"] = 4
    raw["optimization"]["min_iterations"] = 4
    raw["design_space"] = {
        "frozen_solid": [
            {"name": "support_band", "selector": {"type": "box", "x": [0.0, 0.12], "y": [0.0, 1.0]}},
            {"name": "load_pad", "selector": {"type": "box", "x": [0.90, 1.0], "y": [0.40, 0.60]}},
        ],
        "void": [
            {"name": "bottom_clearance", "selector": {"type": "box", "x": [0.42, 0.58], "y": [0.0, 0.20]}}
        ],
    }
    return raw


def test_region_selectors_create_design_frozen_and_void_masks():
    config = parse_config(_design_space_config())
    validate_config(config)

    mesh = create_structured_mesh(config)

    assert np.count_nonzero(mesh.frozen_solid_mask) > 0
    assert np.count_nonzero(mesh.void_mask) > 0
    assert np.count_nonzero(mesh.design_mask) > 0
    assert not np.any(mesh.design_mask & mesh.frozen_solid_mask)
    assert not np.any(mesh.design_mask & mesh.void_mask)


def test_simp_enforces_frozen_solid_and_void_density_masks():
    config = parse_config(_design_space_config())
    validate_config(config)
    mesh = create_structured_mesh(config)

    result = run_simp(config, mesh)

    assert np.all(result.densities[mesh.frozen_solid_mask] == 1.0)
    assert np.all(result.densities[mesh.void_mask] == config.optimization.min_density)


def test_overlapping_frozen_and_void_regions_are_rejected():
    raw = _design_space_config()
    raw["design_space"]["void"] = [
        {"name": "overlapping_void", "selector": copy.deepcopy(raw["design_space"]["frozen_solid"][0]["selector"])}
    ]
    config = parse_config(raw)
    validate_config(config)

    with pytest.raises(ConfigError, match="overlap"):
        create_structured_mesh(config)


def test_multi_load_weighted_compliance_smoke():
    raw = _design_space_config()
    raw["load_cases"] = [
        {"name": "downward_tip", "weight": 0.75, "loads": [{"selector": "right_mid", "fx": 0.0, "fy": -300.0}]},
        {"name": "side_tip", "weight": 0.25, "loads": [{"selector": "top_mid", "fx": 120.0, "fy": 0.0}]},
    ]
    config = parse_config(raw)
    validate_config(config)
    mesh = create_structured_mesh(config)

    result = run_simp(config, mesh)

    assert result.load_case_names == ["downward_tip", "side_tip"]
    assert result.metrics[-1].compliance > 0
    assert result.final_analysis.compliance > 0
