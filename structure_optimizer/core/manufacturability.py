from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.mesh import StructuredMesh


@dataclass(frozen=True)
class ComponentStats:
    count: int
    largest_size: int
    island_count: int
    small_component_count: int


def analyze_manufacturability(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
) -> dict[str, Any]:
    threshold = max(0.05, config.optimization.min_density)
    solid = (densities >= threshold) & mesh.design_mask
    components = _solid_components(mesh, solid)
    largest = max((len(component) for component in components), default=0)
    small_limit = max(3, int(0.01 * max(1, int(np.count_nonzero(mesh.design_mask)))))
    small_components = [component for component in components if len(component) < small_limit]
    thin_elements = _thin_member_elements(mesh, solid)
    gray_fraction = _gray_density_fraction(mesh, densities)

    component_stats = ComponentStats(
        count=len(components),
        largest_size=largest,
        island_count=max(0, len(components) - 1),
        small_component_count=len(small_components),
    )
    isolated_ok = component_stats.island_count == 0 and component_stats.small_component_count == 0
    thin_warning = len(thin_elements) > 0
    gray_warning = gray_fraction > 0.20

    return {
        "status": "warning" if (not isolated_ok or thin_warning or gray_warning) else "passed",
        "checks": {
            "isolated_islands": {
                "status": "passed" if isolated_ok else "warning",
                "component_count": component_stats.count,
                "largest_component_elements": component_stats.largest_size,
                "island_count": component_stats.island_count,
                "small_component_count": component_stats.small_component_count,
                "minimum_region_elements": small_limit,
            },
            "thin_member_warning": {
                "status": "warning" if thin_warning else "passed",
                "thin_element_count": len(thin_elements),
                "rule": "solid elements with one or fewer solid orthogonal neighbors are flagged as thin-member candidates",
            },
            "local_density_warning": {
                "status": "warning" if gray_warning else "passed",
                "gray_density_fraction": gray_fraction,
                "rule": "active elements with density between 0.15 and 0.85 indicate unresolved local density regions",
            },
        },
        "limitations": "These v0.2 checks are coarse manufacturability warnings for 2D/2.5D benchmark models, not production manufacturing approval.",
    }


def _solid_components(mesh: StructuredMesh, solid: np.ndarray) -> list[set[int]]:
    visited: set[int] = set()
    components: list[set[int]] = []
    for element_id, is_solid in enumerate(solid):
        if not is_solid or element_id in visited:
            continue
        component: set[int] = set()
        queue = [element_id]
        visited.add(element_id)
        while queue:
            current = queue.pop(0)
            component.add(current)
            cx, cy = mesh.element_grid_index(current)
            for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                if 0 <= nx < mesh.nelx and 0 <= ny < mesh.nely:
                    neighbor = mesh.element_index(nx, ny)
                    if solid[neighbor] and neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
        components.append(component)
    components.sort(key=len, reverse=True)
    return components


def _thin_member_elements(mesh: StructuredMesh, solid: np.ndarray) -> list[int]:
    thin: list[int] = []
    for element_id, is_solid in enumerate(solid):
        if not is_solid:
            continue
        ex, ey = mesh.element_grid_index(element_id)
        neighbors = 0
        for nx, ny in ((ex - 1, ey), (ex + 1, ey), (ex, ey - 1), (ex, ey + 1)):
            if 0 <= nx < mesh.nelx and 0 <= ny < mesh.nely and solid[mesh.element_index(nx, ny)]:
                neighbors += 1
        if neighbors <= 1:
            thin.append(element_id)
    return thin


def _gray_density_fraction(mesh: StructuredMesh, densities: np.ndarray) -> float:
    active = densities[mesh.design_mask]
    if active.size == 0:
        return 0.0
    gray = (active > 0.15) & (active < 0.85)
    return float(np.count_nonzero(gray) / active.size)
