"""Wave X: targeted ``config.py`` validation-branch coverage.

Every ``raise ConfigError`` in ``_parse_*`` / ``validate_config`` /
``_validate_*`` helpers should be reachable by exactly one negative test.
These tests round out §4.2 by hitting validation branches the happy-path
benchmark loaders never trigger.
"""

from __future__ import annotations

import copy

import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.config import (
    ConfigError,
    parse_config,
    validate_config,
)


def _base_raw() -> dict:
    """Return a mutable copy of the cantilever-smoke raw dict."""
    return copy.deepcopy(load_benchmark("cantilever", preset="smoke").to_dict())


# ---------------------------------------------------------------------------
# Mesh / geometry validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "patch,match",
    [
        ({"dimension": "3d"}, "dimension must be"),
        ({"mesh": {"type": "voronoi", "nelx": 4, "nely": 4}}, "structured_quad"),
        ({"mesh": {"type": "structured_quad", "nelx": 0, "nely": 4}}, "nelx and nely must be positive"),
        ({"mesh": {"type": "structured_quad", "nelx": 4, "nely": -1}}, "nelx and nely must be positive"),
        (
            {"mesh": {"type": "structured_quad", "nelx": 4, "nely": 4, "width": 0}},
            "mesh width must be positive",
        ),
        (
            {"mesh": {"type": "structured_quad", "nelx": 4, "nely": 4, "height": -1}},
            "mesh height must be positive",
        ),
        ({"thickness": 0}, "thickness must be positive"),
        ({"thickness": -1}, "thickness must be positive"),
    ],
)
def test_mesh_and_geometry_validation_errors(patch, match):
    raw = _base_raw()
    raw.update(patch)
    with pytest.raises(ConfigError, match=match):
        validate_config(parse_config(raw))


# ---------------------------------------------------------------------------
# Material validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,bad_value,match",
    [
        ("young_modulus", 0, "young_modulus must be positive"),
        ("young_modulus", -1, "young_modulus must be positive"),
        ("poisson_ratio", 0.99, "poisson_ratio must be in"),
        ("poisson_ratio", -1.5, "poisson_ratio must be in"),
        ("density", 0, "density must be positive"),
        ("density", -1, "density must be positive"),
    ],
)
def test_material_validation_errors(field, bad_value, match):
    raw = _base_raw()
    raw["material"][field] = bad_value
    with pytest.raises(ConfigError, match=match):
        validate_config(parse_config(raw))


# ---------------------------------------------------------------------------
# Boundary conditions / loads
# ---------------------------------------------------------------------------


def test_missing_boundary_conditions_rejected():
    raw = _base_raw()
    raw["boundary_conditions"] = []
    with pytest.raises(ConfigError, match="at least one boundary condition"):
        validate_config(parse_config(raw))


def test_missing_loads_rejected():
    raw = _base_raw()
    raw["loads"] = []
    raw["load_cases"] = []
    with pytest.raises(ConfigError, match="at least one load"):
        validate_config(parse_config(raw))


def test_boundary_condition_with_empty_components_rejected():
    raw = _base_raw()
    raw["boundary_conditions"] = [{"selector": "left_edge", "components": []}]
    with pytest.raises(ConfigError, match="components must be a non-empty subset"):
        validate_config(parse_config(raw))


def test_boundary_condition_with_bad_component_rejected():
    raw = _base_raw()
    raw["boundary_conditions"] = [{"selector": "left_edge", "components": ["uz"]}]
    with pytest.raises(ConfigError, match="components must be a non-empty subset"):
        validate_config(parse_config(raw))


def test_boundary_condition_without_selector_rejected():
    raw = _base_raw()
    raw["boundary_conditions"] = [{"components": ["ux"]}]
    with pytest.raises(ConfigError, match="non-empty selector"):
        validate_config(parse_config(raw))


def test_load_with_zero_force_rejected():
    raw = _base_raw()
    raw["loads"] = [{"selector": "right_mid", "fx": 0.0, "fy": 0.0}]
    with pytest.raises(ConfigError, match="nonzero fx or fy"):
        validate_config(parse_config(raw))


# ---------------------------------------------------------------------------
# Optimization validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,bad_value,match",
    [
        ("objective", "max_displacement", "only min_compliance"),
        ("volume_fraction", 0, "volume_fraction must be in"),
        ("volume_fraction", 1.5, "volume_fraction must be in"),
        ("penalty", 0, "penalty must be positive"),
        ("penalty", -1, "penalty must be positive"),
        ("filter_radius", 0, "filter_radius must be positive"),
        ("filter_radius", -1, "filter_radius must be positive"),
        ("max_iterations", 0, "max_iterations must be positive"),
        ("change_tolerance", 0, "change_tolerance must be positive"),
        ("min_density", 0, "min_density must be in"),
        ("min_density", 1, "min_density must be in"),
    ],
)
def test_optimization_validation_errors(field, bad_value, match):
    raw = _base_raw()
    raw["optimization"][field] = bad_value
    with pytest.raises(ConfigError, match=match):
        validate_config(parse_config(raw))


def test_min_iterations_above_max_rejected():
    raw = _base_raw()
    raw["optimization"]["min_iterations"] = 99
    raw["optimization"]["max_iterations"] = 5
    with pytest.raises(ConfigError, match="min_iterations must be in"):
        validate_config(parse_config(raw))


def test_unknown_case_aggregator_rejected():
    raw = _base_raw()
    raw["optimization"]["case_aggregator"] = "median_squared"
    with pytest.raises(ConfigError, match="case_aggregator must be one of"):
        validate_config(parse_config(raw))


def test_unknown_algorithm_rejected():
    raw = _base_raw()
    raw["optimization"]["algorithm"] = "level_set"
    with pytest.raises(ConfigError, match="algorithm must be one of"):
        validate_config(parse_config(raw))


def test_bad_beso_er_rejected():
    raw = _base_raw()
    raw["optimization"]["beso_er"] = 1.5
    with pytest.raises(ConfigError, match="beso_er must be in"):
        validate_config(parse_config(raw))


def test_negative_stress_penalty_rejected():
    raw = _base_raw()
    raw["optimization"]["stress_penalty"] = -1.0
    with pytest.raises(ConfigError, match="stress_penalty must be"):
        validate_config(parse_config(raw))


# ---------------------------------------------------------------------------
# Load cases
# ---------------------------------------------------------------------------


def test_load_case_with_empty_name_rejected():
    raw = _base_raw()
    raw["load_cases"] = [{"name": "", "weight": 1.0, "loads": [{"selector": "right_mid", "fx": 1.0}]}]
    with pytest.raises(ConfigError, match="load case name"):
        validate_config(parse_config(raw))


def test_load_case_with_nonpositive_weight_rejected():
    raw = _base_raw()
    raw["load_cases"] = [{"name": "primary", "weight": 0.0, "loads": [{"selector": "right_mid", "fx": 1.0}]}]
    with pytest.raises(ConfigError, match="load case weight"):
        validate_config(parse_config(raw))


def test_load_case_without_loads_rejected():
    raw = _base_raw()
    raw["load_cases"] = [{"name": "primary", "weight": 1.0, "loads": []}]
    with pytest.raises(ConfigError, match="load case must define"):
        validate_config(parse_config(raw))


def test_load_case_load_with_zero_force_rejected():
    raw = _base_raw()
    raw["load_cases"] = [{"name": "primary", "weight": 1.0, "loads": [{"selector": "right_mid", "fx": 0.0, "fy": 0.0}]}]
    with pytest.raises(ConfigError, match="load case load must define nonzero"):
        validate_config(parse_config(raw))


# ---------------------------------------------------------------------------
# Manufacturing constraints
# ---------------------------------------------------------------------------


def test_symmetry_with_bad_axis_rejected():
    raw = _base_raw()
    raw["manufacturing_constraints"] = {"symmetry": {"axis": "z", "position": 0.5}}
    with pytest.raises(ConfigError, match=r"symmetry\.axis must be"):
        validate_config(parse_config(raw))


def test_symmetry_with_out_of_range_position_rejected():
    raw = _base_raw()
    raw["manufacturing_constraints"] = {"symmetry": {"axis": "x", "position": 1.5}}
    with pytest.raises(ConfigError, match=r"symmetry\.position must be in"):
        validate_config(parse_config(raw))


def test_extrusion_with_bad_axis_rejected():
    raw = _base_raw()
    raw["manufacturing_constraints"] = {"extrusion": {"axis": "z"}}
    with pytest.raises(ConfigError, match=r"extrusion\.axis must be"):
        validate_config(parse_config(raw))


def test_nonpositive_min_member_size_rejected():
    raw = _base_raw()
    raw["manufacturing_constraints"] = {"min_member_size": 0.0}
    with pytest.raises(ConfigError, match="min_member_size must be positive"):
        validate_config(parse_config(raw))


def test_manufacturing_constraints_non_object_rejected():
    raw = _base_raw()
    raw["manufacturing_constraints"] = "yes please"
    with pytest.raises(ConfigError, match="manufacturing_constraints must be an object"):
        parse_config(raw)


def test_symmetry_non_object_rejected():
    raw = _base_raw()
    raw["manufacturing_constraints"] = {"symmetry": "x"}
    with pytest.raises(ConfigError, match="symmetry must be an object"):
        parse_config(raw)


def test_extrusion_non_object_rejected():
    raw = _base_raw()
    raw["manufacturing_constraints"] = {"extrusion": ["x"]}
    with pytest.raises(ConfigError, match="extrusion must be an object"):
        parse_config(raw)


# ---------------------------------------------------------------------------
# Solver config
# ---------------------------------------------------------------------------


def test_solver_config_non_object_rejected():
    raw = _base_raw()
    raw["solver"] = "dense"
    with pytest.raises(ConfigError, match="solver must be an object"):
        parse_config(raw)


# ---------------------------------------------------------------------------
# Stress constraint
# ---------------------------------------------------------------------------


def test_stress_constraint_non_object_rejected():
    raw = _base_raw()
    raw["stress_constraint"] = True
    with pytest.raises(ConfigError, match="stress_constraint must be an object"):
        parse_config(raw)


def test_stress_constraint_with_bad_aggregation_rejected():
    raw = _base_raw()
    raw["stress_constraint"] = {
        "enabled": True,
        "aggregation": "geomean",
        "p": 8.0,
        "limit": 100.0,
        "density_threshold": 0.5,
    }
    with pytest.raises(ConfigError, match="aggregation must be"):
        validate_config(parse_config(raw))


def test_stress_constraint_with_nonpositive_p_rejected():
    raw = _base_raw()
    raw["stress_constraint"] = {
        "enabled": True,
        "aggregation": "p_norm",
        "p": 0.0,
        "limit": 100.0,
        "density_threshold": 0.5,
    }
    with pytest.raises(ConfigError, match=r"\.p must be positive"):
        validate_config(parse_config(raw))


def test_stress_constraint_with_nonpositive_limit_rejected():
    raw = _base_raw()
    raw["stress_constraint"] = {
        "enabled": True,
        "aggregation": "p_norm",
        "p": 8.0,
        "limit": 0.0,
        "density_threshold": 0.5,
    }
    with pytest.raises(ConfigError, match="limit must be positive"):
        validate_config(parse_config(raw))


def test_stress_constraint_density_threshold_out_of_range_rejected():
    raw = _base_raw()
    raw["stress_constraint"] = {
        "enabled": True,
        "aggregation": "p_norm",
        "p": 8.0,
        "limit": 100.0,
        "density_threshold": 1.5,
    }
    with pytest.raises(ConfigError, match="density_threshold must be in"):
        validate_config(parse_config(raw))


def test_disabled_stress_constraint_is_a_noop():
    """Disabled stress constraint must skip all the inner validations."""
    raw = _base_raw()
    raw["stress_constraint"] = {
        "enabled": False,
        "aggregation": "bogus",  # would fail if enabled
        "p": -1,
        "limit": -1,
        "density_threshold": 99,
    }
    # Should NOT raise
    validate_config(parse_config(raw))


# ---------------------------------------------------------------------------
# Design space
# ---------------------------------------------------------------------------


def test_design_space_frozen_solid_must_be_list():
    raw = _base_raw()
    raw["design_space"] = {"frozen_solid": "everything", "void": []}
    with pytest.raises(ConfigError, match="frozen_solid must be a list"):
        validate_config(parse_config(raw))


def test_design_space_region_must_be_object():
    raw = _base_raw()
    raw["design_space"] = {"frozen_solid": ["string region"], "void": []}
    with pytest.raises(ConfigError, match="regions must be objects"):
        validate_config(parse_config(raw))


def test_design_space_region_requires_name():
    raw = _base_raw()
    raw["design_space"] = {"frozen_solid": [{"selector": "left_edge"}], "void": []}
    with pytest.raises(ConfigError, match="requires a name"):
        validate_config(parse_config(raw))


def test_design_space_region_requires_selector():
    raw = _base_raw()
    raw["design_space"] = {"frozen_solid": [{"name": "fixed"}], "void": []}
    with pytest.raises(ConfigError, match="requires a selector"):
        validate_config(parse_config(raw))


# ---------------------------------------------------------------------------
# Top-level config error wrapping
# ---------------------------------------------------------------------------


def test_missing_required_field_raises_config_error():
    """``parse_config`` wraps KeyError → ConfigError."""
    bad = {"name": "x"}  # missing dimension/mesh/material/etc.
    with pytest.raises(ConfigError, match="Missing required"):
        parse_config(bad)


def test_wrong_type_raises_config_error():
    """``parse_config`` wraps TypeError → ConfigError."""
    raw = _base_raw()
    raw["mesh"] = "not a dict"
    with pytest.raises(ConfigError):
        parse_config(raw)
