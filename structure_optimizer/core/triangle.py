"""Wave I: CST (Constant Strain Triangle) element for 2D linear elasticity.

CST is the simplest 2D linear element: 3 nodes, linear shape functions, one
Gauss point. Stiffness is 6×6 (3 nodes × 2 DOFs). Reference: Bathe (1996)
§5.3 or any introductory FEM text.

This module + ``adapters/mesh_source.MeshioReader`` together provide read
support for arbitrary triangle meshes (e.g. produced by Gmsh) and a linear
elastic solve on them. Full SIMP topology optimization on triangle meshes
is intentionally **not** in v1.9 scope — that would require a separate
adjoint-method-aware SIMP path (current SIMP assumes structured quad).

Public functions:
- ``triangle_stiffness(E, ν, node_coords, thickness)`` — 6×6 element matrix
- ``solve_tri_linear_elastic(mesh, material, loads, ...)`` — full assemble+solve
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from structure_optimizer.core.fem2d import SolverError


def triangle_stiffness(
    young_modulus: float,
    poisson_ratio: float,
    node_coords: np.ndarray,
    thickness: float = 1.0,
) -> tuple[np.ndarray, float]:
    """Compute 6×6 plane-stress CST stiffness matrix + element area.

    Args:
        young_modulus: Young's modulus E.
        poisson_ratio: Poisson's ratio ν.
        node_coords: (3, 2) array of (x, y) per node (ccw orientation).
        thickness: out-of-plane thickness (default 1).

    Returns:
        (ke, area) where ``ke`` is 6×6 SPD and ``area`` is the signed-positive
        triangle area.

    Raises:
        ValueError: if the triangle is degenerate (zero area).
    """
    coords = np.asarray(node_coords, dtype=float)
    if coords.shape != (3, 2):
        raise ValueError(f"node_coords must be (3, 2), got {coords.shape}")
    x = coords[:, 0]
    y = coords[:, 1]
    twice_area = x[0] * (y[1] - y[2]) + x[1] * (y[2] - y[0]) + x[2] * (y[0] - y[1])
    if abs(twice_area) < 1e-12:
        raise ValueError("degenerate triangle (zero area)")
    area = 0.5 * abs(twice_area)

    b = np.array([y[1] - y[2], y[2] - y[0], y[0] - y[1]])
    c = np.array([x[2] - x[1], x[0] - x[2], x[1] - x[0]])

    bmat = np.zeros((3, 6))
    for i in range(3):
        bmat[0, 2 * i] = b[i]
        bmat[1, 2 * i + 1] = c[i]
        bmat[2, 2 * i] = c[i]
        bmat[2, 2 * i + 1] = b[i]
    bmat = bmat / twice_area

    nu = poisson_ratio
    factor = young_modulus / (1.0 - nu**2)
    dmat = factor * np.array(
        [
            [1.0, nu, 0.0],
            [nu, 1.0, 0.0],
            [0.0, 0.0, (1.0 - nu) / 2.0],
        ]
    )

    ke = thickness * area * (bmat.T @ dmat @ bmat)
    return ke, area


@dataclass(frozen=True)
class TriangleMesh:
    """Unstructured 2D triangle mesh container.

    Required: ``nodes`` (n_nodes, 2) + ``elements`` (n_elem, 3).
    Optional design-space masks (default: all-design, none frozen, none void)
    are populated in ``__post_init__`` so existing v1.9 callers
    (``TriangleMesh(nodes=..., elements=...)``) keep working unchanged while
    Wave M's SIMP-on-triangle path can pin elements as solid/void.
    """

    nodes: np.ndarray
    elements: np.ndarray
    design_mask: np.ndarray | None = None
    frozen_solid_mask: np.ndarray | None = None
    void_mask: np.ndarray | None = None

    def __post_init__(self) -> None:
        n_elem = int(self.elements.shape[0])
        if self.design_mask is None:
            object.__setattr__(self, "design_mask", np.ones(n_elem, dtype=bool))
        if self.frozen_solid_mask is None:
            object.__setattr__(self, "frozen_solid_mask", np.zeros(n_elem, dtype=bool))
        if self.void_mask is None:
            object.__setattr__(self, "void_mask", np.zeros(n_elem, dtype=bool))

    @property
    def n_nodes(self) -> int:
        return int(self.nodes.shape[0])

    @property
    def n_elements(self) -> int:
        return int(self.elements.shape[0])

    @property
    def ndof(self) -> int:
        return 2 * self.n_nodes

    def element_dofs(self, element_id: int) -> np.ndarray:
        """Return the 6 DOF indices for one triangle."""
        node_ids = self.elements[element_id]
        dofs: list[int] = []
        for n in node_ids:
            dofs.extend([2 * int(n), 2 * int(n) + 1])
        return np.array(dofs, dtype=int)

    def element_area(self, element_id: int) -> float:
        """Signed-positive area of one triangle."""
        coords = self.nodes[self.elements[element_id]]
        x = coords[:, 0]
        y = coords[:, 1]
        return float(abs(x[0] * (y[1] - y[2]) + x[1] * (y[2] - y[0]) + x[2] * (y[0] - y[1])) * 0.5)

    def element_centroid(self, element_id: int) -> np.ndarray:
        """Centroid (x, y) of one triangle."""
        return self.nodes[self.elements[element_id]].mean(axis=0)

    @property
    def element_centroids(self) -> np.ndarray:
        """(n_elem, 2) array of triangle centroids."""
        return self.nodes[self.elements].mean(axis=1)

    def select_nodes_in_box(
        self,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        tolerance: float = 1e-9,
    ) -> np.ndarray:
        """Return node ids whose coordinates fall in [x_min, x_max] × [y_min, y_max]."""
        x = self.nodes[:, 0]
        y = self.nodes[:, 1]
        mask = (x >= x_min - tolerance) & (x <= x_max + tolerance) & (y >= y_min - tolerance) & (y <= y_max + tolerance)
        return np.where(mask)[0]


def solve_tri_linear_elastic(
    mesh: TriangleMesh,
    young_modulus: float,
    poisson_ratio: float,
    fixed_dofs: np.ndarray,
    force: np.ndarray,
    thickness: float = 1.0,
    densities: np.ndarray | None = None,
    solver_backend: str = "dense",
) -> dict[str, Any]:
    """Assemble + solve K u = f on a triangle mesh.

    Args:
        mesh: TriangleMesh
        young_modulus, poisson_ratio: material
        fixed_dofs: 1d int array of constrained DOF indices
        force: ndof-length force vector
        thickness: out-of-plane thickness
        densities: optional per-element density (length = n_elem).
            Currently treated as a linear scale (no SIMP penalty). If None,
            all elements at density 1.
        solver_backend: "dense" / "cg" / "sparse" / "sparse_cg"

    Returns:
        dict with keys: ``displacements`` (ndof,), ``compliance`` (float),
        ``max_displacement`` (float), ``element_strain_energy`` (n_elem,).

    Raises:
        SolverError: if all DOFs are fixed or solver fails.
    """
    n_elem = mesh.n_elements
    if densities is None:
        densities = np.ones(n_elem, dtype=float)
    densities = np.asarray(densities, dtype=float)
    if densities.shape != (n_elem,):
        raise ValueError(f"densities length {densities.shape} != n_elements {n_elem}")

    from structure_optimizer.adapters.solver_base import get_linear_solver

    linear_solver = get_linear_solver(solver_backend)

    # Per-element stiffness + area (precompute)
    element_kes = []
    element_areas = []
    for eid in range(n_elem):
        coords = mesh.nodes[mesh.elements[eid]]
        ke, area = triangle_stiffness(young_modulus, poisson_ratio, coords, thickness)
        element_kes.append(ke)
        element_areas.append(area)

    if linear_solver.prefers_sparse:
        stiffness = _assemble_tri_sparse(mesh, element_kes, densities)
    else:
        stiffness = _assemble_tri_dense(mesh, element_kes, densities)

    ndof = mesh.ndof
    fixed = np.asarray(fixed_dofs, dtype=int)
    free = np.setdiff1d(np.arange(ndof), fixed)
    if free.size == 0:
        raise SolverError("all degrees of freedom are fixed")

    displacements = np.zeros(ndof, dtype=float)
    kff = stiffness.tocsr()[free, :][:, free] if linear_solver.prefers_sparse else stiffness[np.ix_(free, free)]
    ff = force[free]
    displacements[free] = linear_solver.solve(kff, ff)

    element_energy = np.zeros(n_elem, dtype=float)
    for eid in range(n_elem):
        edofs = mesh.element_dofs(eid)
        ue = displacements[edofs]
        element_energy[eid] = float(ue @ (element_kes[eid] @ ue))

    compliance = float(force @ displacements)
    disp_pairs = displacements.reshape((-1, 2))
    max_displacement = float(np.max(np.linalg.norm(disp_pairs, axis=1)))

    return {
        "displacements": displacements,
        "compliance": compliance,
        "max_displacement": max_displacement,
        "element_strain_energy": element_energy,
        "element_areas": np.array(element_areas),
    }


def _assemble_tri_dense(mesh: TriangleMesh, element_kes: list[np.ndarray], densities: np.ndarray) -> np.ndarray:
    stiffness = np.zeros((mesh.ndof, mesh.ndof), dtype=float)
    for eid, ke in enumerate(element_kes):
        edofs = mesh.element_dofs(eid)
        stiffness[np.ix_(edofs, edofs)] += densities[eid] * ke
    return stiffness


def _assemble_tri_sparse(mesh: TriangleMesh, element_kes: list[np.ndarray], densities: np.ndarray) -> Any:
    import scipy.sparse as sp

    n_elem = mesh.n_elements
    edofs_all = np.array([mesh.element_dofs(eid) for eid in range(n_elem)])  # (n_elem, 6)
    rows = np.repeat(edofs_all, 6, axis=1).flatten()
    cols = np.tile(edofs_all, (1, 6)).flatten()
    vals_list = [(densities[eid] * element_kes[eid]).flatten() for eid in range(n_elem)]
    vals = np.concatenate(vals_list)
    return sp.coo_matrix((vals, (rows, cols)), shape=(mesh.ndof, mesh.ndof)).tocsr()
