from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig, ConfigError
from structure_optimizer.core.design_space import build_design_space_masks


@dataclass(frozen=True)
class StructuredMesh:
    """Structured quadrilateral mesh + design / frozen-solid / void masks."""

    nelx: int
    nely: int
    width: float
    height: float
    nodes: np.ndarray
    elements: np.ndarray
    design_mask: np.ndarray
    frozen_solid_mask: np.ndarray
    void_mask: np.ndarray
    region_masks: dict[str, np.ndarray]

    @property
    def ndof(self) -> int:
        """Total degrees of freedom (2 per node)."""
        return self.nodes.shape[0] * 2

    @property
    def element_area(self) -> float:
        """Area of a single element in mesh units."""
        return (self.width / self.nelx) * (self.height / self.nely)

    def node_id(self, i: int, j: int) -> int:
        """Flat node id for grid coords (i, j)."""
        return j * (self.nelx + 1) + i

    def element_index(self, ex: int, ey: int) -> int:
        """Flat element id for element-grid coords (ex, ey)."""
        return ey * self.nelx + ex

    def element_grid_index(self, element_id: int) -> tuple[int, int]:
        """Inverse of ``element_index`` — return (ex, ey)."""
        return element_id % self.nelx, element_id // self.nelx

    def element_dofs(self, element_id: int) -> np.ndarray:
        """Return the 8 DOF indices (ux/uy pairs for 4 nodes) of an element."""
        nodes = self.elements[element_id]
        dofs: list[int] = []
        for node in nodes:
            dofs.extend([2 * int(node), 2 * int(node) + 1])
        return np.array(dofs, dtype=int)

    def selector_nodes(self, selector: str) -> list[int]:
        """Map a string selector (e.g. ``"left_edge"``) to the nodes it covers."""
        mid_x = self.nelx // 2
        mid_y = self.nely // 2
        selectors = {
            "left_edge": [self.node_id(0, j) for j in range(self.nely + 1)],
            "right_edge": [self.node_id(self.nelx, j) for j in range(self.nely + 1)],
            "top_edge": [self.node_id(i, self.nely) for i in range(self.nelx + 1)],
            "bottom_edge": [self.node_id(i, 0) for i in range(self.nelx + 1)],
            "right_mid": [self.node_id(self.nelx, mid_y)],
            "left_mid": [self.node_id(0, mid_y)],
            "top_mid": [self.node_id(mid_x, self.nely)],
            "bottom_mid": [self.node_id(mid_x, 0)],
            "bottom_left": [self.node_id(0, 0)],
            "bottom_right": [self.node_id(self.nelx, 0)],
            "top_left": [self.node_id(0, self.nely)],
            "top_right": [self.node_id(self.nelx, self.nely)],
        }
        if selector not in selectors:
            raise ConfigError(f"unknown mesh selector '{selector}'")
        return selectors[selector]

    def fixed_dofs(self, boundary_conditions: list[dict]) -> np.ndarray:
        """Collect the set of DOFs constrained by all boundary-condition records."""
        dofs: set[int] = set()
        for bc in boundary_conditions:
            for node in self.selector_nodes(bc["selector"]):
                components = set(bc["components"])
                if "ux" in components:
                    dofs.add(2 * node)
                if "uy" in components:
                    dofs.add(2 * node + 1)
        return np.array(sorted(dofs), dtype=int)

    def force_vector(self, loads: list[dict]) -> np.ndarray:
        """Build the global force vector from a list of point-load records (distributed across selector nodes)."""
        force = np.zeros(self.ndof, dtype=float)
        for load in loads:
            fx = float(load.get("fx", 0.0))
            fy = float(load.get("fy", 0.0))
            nodes = self.selector_nodes(load["selector"])
            for node in nodes:
                force[2 * node] += fx / len(nodes)
                force[2 * node + 1] += fy / len(nodes)
        return force


def create_structured_mesh(config: BenchmarkConfig) -> StructuredMesh:
    """Build a structured-quadrilateral mesh + design / frozen / void masks from a ``BenchmarkConfig``."""
    nelx = config.mesh.nelx
    nely = config.mesh.nely
    width = float(config.mesh.width if config.mesh.width is not None else nelx)
    height = float(config.mesh.height if config.mesh.height is not None else nely)

    nodes = []
    for j in range(nely + 1):
        y = height * j / nely
        for i in range(nelx + 1):
            x = width * i / nelx
            nodes.append((x, y))

    elements = []
    for ey in range(nely):
        for ex in range(nelx):
            n1 = ey * (nelx + 1) + ex
            n2 = n1 + 1
            n4 = n1 + (nelx + 1)
            n3 = n4 + 1
            elements.append((n1, n2, n3, n4))

    empty = np.zeros(nelx * nely, dtype=bool)
    provisional = StructuredMesh(
        nelx=nelx,
        nely=nely,
        width=width,
        height=height,
        nodes=np.array(nodes, dtype=float),
        elements=np.array(elements, dtype=int),
        design_mask=~empty,
        frozen_solid_mask=empty.copy(),
        void_mask=empty.copy(),
        region_masks={},
    )
    masks = build_design_space_masks(config, provisional)
    return StructuredMesh(
        nelx=nelx,
        nely=nely,
        width=width,
        height=height,
        nodes=provisional.nodes,
        elements=provisional.elements,
        design_mask=masks.design_mask,
        frozen_solid_mask=masks.frozen_solid_mask,
        void_mask=masks.void_mask,
        region_masks=masks.region_masks,
    )
