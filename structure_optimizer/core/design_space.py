from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig, ConfigError


@dataclass(frozen=True)
class DesignSpaceMasks:
    design_mask: np.ndarray
    frozen_solid_mask: np.ndarray
    void_mask: np.ndarray
    region_masks: dict[str, np.ndarray]


def build_design_space_masks(config: BenchmarkConfig, mesh) -> DesignSpaceMasks:
    element_count = mesh.nelx * mesh.nely
    frozen = np.zeros(element_count, dtype=bool)
    void = np.zeros(element_count, dtype=bool)
    regions: dict[str, np.ndarray] = {}

    for index, region in enumerate(config.mesh.void_regions):
        mask = element_mask_for_selector(mesh, _legacy_void_selector(region))
        _add_region_mask(regions, f"mesh_void_{index}", mask)
        void |= mask

    for region in config.design_space.frozen_solid:
        mask = element_mask_for_selector(mesh, region["selector"])
        _require_non_empty(region["name"], mask)
        _add_region_mask(regions, region["name"], mask)
        frozen |= mask

    for region in config.design_space.void:
        mask = element_mask_for_selector(mesh, region["selector"])
        _require_non_empty(region["name"], mask)
        _add_region_mask(regions, region["name"], mask)
        void |= mask

    if np.any(frozen & void):
        raise ConfigError("design_space frozen_solid and void regions overlap")

    design = ~(frozen | void)
    if not np.any(design):
        raise ConfigError("design_space leaves no design elements")
    return DesignSpaceMasks(design_mask=design, frozen_solid_mask=frozen, void_mask=void, region_masks=regions)


def element_mask_for_selector(mesh, selector: str | dict[str, Any]) -> np.ndarray:
    if isinstance(selector, str):
        return _string_selector_mask(mesh, selector)
    if not isinstance(selector, dict):
        raise ConfigError("element selector must be a string or object")
    selector_type = selector.get("type")
    if selector_type in {"box", "rect", "element_box"}:
        return _box_selector_mask(mesh, selector)
    if selector_type == "circle":
        return _circle_selector_mask(mesh, selector)
    raise ConfigError(f"unknown element selector type '{selector_type}'")


def _string_selector_mask(mesh, selector: str) -> np.ndarray:
    mask = np.zeros(mesh.nelx * mesh.nely, dtype=bool)
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            element_id = mesh.element_index(ex, ey)
            if selector == "all":
                mask[element_id] = True
            elif selector in {"left_edge_band", "left_support_band"} and ex == 0:
                mask[element_id] = True
            elif selector in {"right_edge_band", "right_load_band"} and ex == mesh.nelx - 1:
                mask[element_id] = True
            elif selector == "top_edge_band" and ey == mesh.nely - 1:
                mask[element_id] = True
            elif selector == "bottom_edge_band" and ey == 0:
                mask[element_id] = True
            elif selector == "right_mid_pad" and ex == mesh.nelx - 1 and abs((ey + 0.5) / mesh.nely - 0.5) <= 0.12:
                mask[element_id] = True
            elif selector == "left_mid_pad" and ex == 0 and abs((ey + 0.5) / mesh.nely - 0.5) <= 0.12:
                mask[element_id] = True
    if not np.any(mask):
        raise ConfigError(f"unknown or empty element selector '{selector}'")
    return mask


def _box_selector_mask(mesh, selector: dict[str, Any]) -> np.ndarray:
    x_min, x_max = _axis_bounds(selector, "x", mesh.width)
    y_min, y_max = _axis_bounds(selector, "y", mesh.height)
    mask = np.zeros(mesh.nelx * mesh.nely, dtype=bool)
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            center_x = mesh.width * (ex + 0.5) / mesh.nelx
            center_y = mesh.height * (ey + 0.5) / mesh.nely
            if x_min <= center_x <= x_max and y_min <= center_y <= y_max:
                mask[mesh.element_index(ex, ey)] = True
    return mask


def _circle_selector_mask(mesh, selector: dict[str, Any]) -> np.ndarray:
    coordinates = selector.get("coordinates", "normalized")
    center = selector.get("center")
    if not isinstance(center, list | tuple) or len(center) != 2:
        raise ConfigError("circle selector requires center [x, y]")
    radius = float(selector["radius"])
    if coordinates == "normalized":
        cx = float(center[0]) * mesh.width
        cy = float(center[1]) * mesh.height
        r = radius * max(mesh.width, mesh.height)
    elif coordinates == "absolute":
        cx = float(center[0])
        cy = float(center[1])
        r = radius
    else:
        raise ConfigError("selector coordinates must be normalized or absolute")

    mask = np.zeros(mesh.nelx * mesh.nely, dtype=bool)
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            center_x = mesh.width * (ex + 0.5) / mesh.nelx
            center_y = mesh.height * (ey + 0.5) / mesh.nely
            if (center_x - cx) ** 2 + (center_y - cy) ** 2 <= r**2:
                mask[mesh.element_index(ex, ey)] = True
    return mask


def _axis_bounds(selector: dict[str, Any], axis: str, size: float) -> tuple[float, float]:
    coordinates = selector.get("coordinates")
    if axis in selector:
        values = selector[axis]
        if not isinstance(values, list | tuple) or len(values) != 2:
            raise ConfigError(f"{axis} selector range must contain two values")
        low, high = float(values[0]), float(values[1])
        coordinates = coordinates or "normalized"
    else:
        low = float(selector[f"{axis}_min"])
        high = float(selector[f"{axis}_max"])
        coordinates = coordinates or "absolute"
    if coordinates == "normalized":
        low *= size
        high *= size
    elif coordinates != "absolute":
        raise ConfigError("selector coordinates must be normalized or absolute")
    if low > high:
        raise ConfigError(f"{axis} selector range minimum exceeds maximum")
    return low, high


def _legacy_void_selector(region: dict[str, Any]) -> dict[str, Any]:
    if region.get("type") != "rect":
        raise ConfigError("only rect void regions are supported")
    return {
        "type": "rect",
        "coordinates": "absolute",
        "x_min": region["x_min"],
        "x_max": region["x_max"],
        "y_min": region["y_min"],
        "y_max": region["y_max"],
    }


def _add_region_mask(regions: dict[str, np.ndarray], name: str, mask: np.ndarray) -> None:
    if name in regions:
        raise ConfigError(f"duplicate design_space region name '{name}'")
    regions[name] = mask.copy()


def _require_non_empty(name: str, mask: np.ndarray) -> None:
    if not np.any(mask):
        raise ConfigError(f"design_space region '{name}' selects no elements")
