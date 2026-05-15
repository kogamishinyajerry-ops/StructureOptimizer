"""Targeted coverage for ``core/design_space.py``.

The original ``tests/test_design_space.py`` covers SIMP-loop integration. This
file complements it by exercising selector parsing edge cases and error paths
that are otherwise hard to reach.

Properties pinned here:

- Box selectors accept both ``x``/``y`` list form and ``x_min``/``x_max`` form.
- Box selectors accept ``normalized`` and ``absolute`` coordinate modes.
- Circle selectors accept both coordinate modes; require explicit ``center`` list.
- String selectors cover all the named regions (left/right/top/bottom edge bands,
  mid pads).
- Empty / out-of-bounds / inverted-range selectors raise ``ConfigError``.
- Duplicate region names raise ``ConfigError``.
- design_space with frozen ∪ void = all elements (no design left) raises.
- Legacy ``mesh.void_regions`` path (``rect`` only) raises on other types.
"""

from __future__ import annotations

import pytest
from structure_optimizer.core.config import ConfigError, parse_config, validate_config
from structure_optimizer.core.design_space import (
    build_design_space_masks,
    element_mask_for_selector,
)
from structure_optimizer.core.mesh import create_structured_mesh


def _config(**overrides):
    base = {
        "name": "design_space_cov",
        "dimension": "2d",
        "units": "mm_N_MPa",
        "thickness": 1.0,
        "mesh": {"type": "structured_quad", "nelx": 10, "nely": 6, "width": 10.0, "height": 6.0},
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
    base.update(overrides)
    config = parse_config(base)
    validate_config(config)
    return config


# --- string selectors -------------------------------------------------


def test_string_selectors_recognize_all_named_regions():
    """Each documented string selector should produce a non-empty mask."""
    config = _config()
    mesh = create_structured_mesh(config)
    selectors = [
        "all",
        "left_edge_band",
        "left_support_band",
        "right_edge_band",
        "right_load_band",
        "top_edge_band",
        "bottom_edge_band",
        "right_mid_pad",
        "left_mid_pad",
    ]
    for selector in selectors:
        mask = element_mask_for_selector(mesh, selector)
        assert mask.any(), f"selector {selector!r} produced empty mask"


def test_string_selector_rejects_unknown_name():
    config = _config()
    mesh = create_structured_mesh(config)
    with pytest.raises(ConfigError, match="unknown or empty element selector"):
        element_mask_for_selector(mesh, "not_a_real_selector")


def test_selector_rejects_non_string_non_dict():
    config = _config()
    mesh = create_structured_mesh(config)
    with pytest.raises(ConfigError, match="must be a string or object"):
        element_mask_for_selector(mesh, 12345)  # type: ignore[arg-type]


def test_selector_rejects_unknown_dict_type():
    config = _config()
    mesh = create_structured_mesh(config)
    with pytest.raises(ConfigError, match="unknown element selector type"):
        element_mask_for_selector(mesh, {"type": "octagon"})


# --- box selectors ----------------------------------------------------


def test_box_selector_with_x_y_list_form_normalized_default():
    """Box selector with ``x: [...]`` defaults to normalized coords."""
    config = _config()
    mesh = create_structured_mesh(config)
    mask = element_mask_for_selector(mesh, {"type": "box", "x": [0.0, 0.5], "y": [0.0, 1.0]})
    grid = mask.reshape(mesh.nely, mesh.nelx)
    # left half should be selected
    assert grid[:, : mesh.nelx // 2].all()
    assert not grid[:, mesh.nelx // 2 + 1 :].any()


def test_box_selector_with_min_max_form_defaults_absolute():
    """``x_min/x_max`` form defaults to absolute coords."""
    config = _config()
    mesh = create_structured_mesh(config)
    mask = element_mask_for_selector(mesh, {"type": "box", "x_min": 0.0, "x_max": 5.0, "y_min": 0.0, "y_max": 6.0})
    grid = mask.reshape(mesh.nely, mesh.nelx)
    assert grid[:, :5].all()


def test_box_selector_rect_alias():
    config = _config()
    mesh = create_structured_mesh(config)
    mask_box = element_mask_for_selector(mesh, {"type": "box", "x": [0.0, 0.5], "y": [0.0, 0.5]})
    mask_rect = element_mask_for_selector(mesh, {"type": "rect", "x": [0.0, 0.5], "y": [0.0, 0.5]})
    assert (mask_box == mask_rect).all()


def test_box_selector_element_box_alias():
    config = _config()
    mesh = create_structured_mesh(config)
    mask = element_mask_for_selector(mesh, {"type": "element_box", "x": [0.0, 0.5], "y": [0.0, 1.0]})
    assert mask.any()


def test_box_selector_explicit_absolute_coords():
    config = _config()
    mesh = create_structured_mesh(config)
    mask = element_mask_for_selector(
        mesh,
        {
            "type": "box",
            "coordinates": "absolute",
            "x": [0.0, 3.0],
            "y": [0.0, 6.0],
        },
    )
    assert mask.any()


def test_box_selector_rejects_bad_axis_range_shape():
    config = _config()
    mesh = create_structured_mesh(config)
    with pytest.raises(ConfigError, match="range must contain two values"):
        element_mask_for_selector(mesh, {"type": "box", "x": [0.0], "y": [0.0, 1.0]})


def test_box_selector_rejects_inverted_range():
    config = _config()
    mesh = create_structured_mesh(config)
    with pytest.raises(ConfigError, match="range minimum exceeds maximum"):
        element_mask_for_selector(mesh, {"type": "box", "x": [0.7, 0.3], "y": [0.0, 1.0]})


def test_box_selector_rejects_bad_coordinates_mode():
    config = _config()
    mesh = create_structured_mesh(config)
    with pytest.raises(ConfigError, match="must be normalized or absolute"):
        element_mask_for_selector(
            mesh,
            {"type": "box", "coordinates": "pixels", "x": [0.0, 1.0], "y": [0.0, 1.0]},
        )


# --- circle selectors --------------------------------------------------


def test_circle_selector_normalized_default():
    config = _config()
    mesh = create_structured_mesh(config)
    mask = element_mask_for_selector(mesh, {"type": "circle", "center": [0.5, 0.5], "radius": 0.2})
    assert mask.any()


def test_circle_selector_absolute_coords():
    config = _config()
    mesh = create_structured_mesh(config)
    mask = element_mask_for_selector(
        mesh,
        {
            "type": "circle",
            "coordinates": "absolute",
            "center": [5.0, 3.0],
            "radius": 2.0,
        },
    )
    assert mask.any()


def test_circle_selector_requires_center_pair():
    config = _config()
    mesh = create_structured_mesh(config)
    with pytest.raises(ConfigError, match="center"):
        element_mask_for_selector(mesh, {"type": "circle", "center": [0.5], "radius": 0.2})


def test_circle_selector_rejects_missing_center():
    config = _config()
    mesh = create_structured_mesh(config)
    with pytest.raises(ConfigError, match="center"):
        element_mask_for_selector(mesh, {"type": "circle", "radius": 0.2})


def test_circle_selector_rejects_bad_coordinates_mode():
    config = _config()
    mesh = create_structured_mesh(config)
    with pytest.raises(ConfigError, match="coordinates must be normalized or absolute"):
        element_mask_for_selector(
            mesh,
            {"type": "circle", "coordinates": "polar", "center": [0.5, 0.5], "radius": 0.2},
        )


# --- design-space integration -----------------------------------------


def test_build_masks_with_empty_region_raises():
    """A region selector that matches no elements is a config error."""
    raw_overrides = {
        "design_space": {
            "frozen_solid": [
                {
                    "name": "out_of_bounds",
                    "selector": {"type": "box", "x": [2.0, 3.0], "y": [0.0, 1.0]},
                }
            ],
            "void": [],
        }
    }
    with pytest.raises(ConfigError, match="selects no elements"):
        config = _config(**raw_overrides)
        mesh = create_structured_mesh(config)
        build_design_space_masks(config, mesh)


def test_build_masks_with_duplicate_region_names_raises():
    raw_overrides = {
        "design_space": {
            "frozen_solid": [
                {"name": "dup", "selector": {"type": "box", "x": [0.0, 0.2], "y": [0.0, 1.0]}},
            ],
            "void": [
                {"name": "dup", "selector": {"type": "box", "x": [0.8, 1.0], "y": [0.0, 1.0]}},
            ],
        }
    }
    with pytest.raises(ConfigError, match="duplicate design_space region name"):
        config = _config(**raw_overrides)
        mesh = create_structured_mesh(config)
        build_design_space_masks(config, mesh)


def test_build_masks_with_full_coverage_leaves_no_design_raises():
    """If frozen ∪ void = entire mesh, no elements remain free → ConfigError."""
    raw_overrides = {
        "design_space": {
            "frozen_solid": [
                {"name": "everything", "selector": "all"},
            ],
            "void": [],
        }
    }
    with pytest.raises(ConfigError, match="no design elements"):
        config = _config(**raw_overrides)
        mesh = create_structured_mesh(config)
        build_design_space_masks(config, mesh)


def test_build_masks_with_disjoint_frozen_and_void_succeeds():
    raw_overrides = {
        "design_space": {
            "frozen_solid": [
                {"name": "left", "selector": {"type": "box", "x": [0.0, 0.1], "y": [0.0, 1.0]}},
            ],
            "void": [
                {"name": "right", "selector": {"type": "box", "x": [0.9, 1.0], "y": [0.0, 1.0]}},
            ],
        }
    }
    config = _config(**raw_overrides)
    mesh = create_structured_mesh(config)
    masks = build_design_space_masks(config, mesh)
    assert masks.frozen_solid_mask.any()
    assert masks.void_mask.any()
    assert masks.design_mask.any()
    # disjoint property
    assert not (masks.frozen_solid_mask & masks.void_mask).any()


# --- legacy mesh.void_regions ----------------------------------------


def test_legacy_mesh_void_regions_rect_type_works():
    raw_overrides = {
        "mesh": {
            "type": "structured_quad",
            "nelx": 10,
            "nely": 6,
            "width": 10.0,
            "height": 6.0,
            "void_regions": [{"type": "rect", "x_min": 8.0, "x_max": 10.0, "y_min": 0.0, "y_max": 6.0}],
        },
    }
    config = _config(**raw_overrides)
    mesh = create_structured_mesh(config)
    masks = build_design_space_masks(config, mesh)
    assert masks.void_mask.any()


def test_legacy_mesh_void_regions_non_rect_type_raises():
    raw_overrides = {
        "mesh": {
            "type": "structured_quad",
            "nelx": 10,
            "nely": 6,
            "width": 10.0,
            "height": 6.0,
            "void_regions": [{"type": "circle", "center": [0.5, 0.5], "radius": 0.1}],
        },
    }
    config = _config(**raw_overrides)
    # create_structured_mesh internally calls build_design_space_masks → error path
    with pytest.raises(ConfigError, match="only rect void regions"):
        create_structured_mesh(config)
