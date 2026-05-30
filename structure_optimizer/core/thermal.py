"""Wave Y: 2D heat-conduction FEM solver (v5 multi-physics layer).

Solves the steady-state heat equation

    -∇·(k(ρ) · ∇T) = q       in Ω
              T   = T₀        on Γ_D (Dirichlet)
       -k · ∂T/∂n = -q̂        on Γ_N (Neumann / heat flux)

on the same structured-quad mesh as the linear-elastic FEM (`fem2d.py`),
sharing the geometric topology + element ordering. The element conductivity
matrix is the bilinear-quad ``∇N · ∇N`` integral on a unit reference square:

    Ke_thermal = (k · t / 6) · [[ 4, -1, -2, -1],
                                [-1,  4, -1, -2],
                                [-2, -1,  4, -1],
                                [-1, -2, -1,  4]]

(see Cook 1989 §10.2 or Bathe FEA textbook). For rectangular (non-square)
elements this would need an anisotropic scaling — like the elastic
``element_stiffness`` we currently assume unit-sized elements, with mesh
size effects absorbed into the (k, t, q) calibration constants. Honest
caveat in D025.

The thermal field is scalar so DOF count per node = 1 (vs 2 for elasticity).

SIMP density scaling on the element matrix follows the same penalty law:
    K_e_eff = (ρ_min + ρ_e^p · (1 - ρ_min)) · Ke
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import StructuredMesh


@dataclass
class ThermalResult:
    """Output of a SIMP-scaled thermal solve.

    Attributes:
        temperatures: nodal temperature array (n_nodes,)
        thermal_compliance: scalar ``T^T · K · T`` (the SIMP objective)
        max_temperature: ``max(temperatures)``
        element_thermal_energy: per-element ``T_e^T · Ke · T_e`` (for SIMP sens)
        n_nodes_fixed: count of Dirichlet-fixed DOFs (sanity)
    """

    temperatures: np.ndarray
    thermal_compliance: float
    max_temperature: float
    element_thermal_energy: np.ndarray
    n_nodes_fixed: int


def element_thermal_conductivity(conductivity: float, thickness: float = 1.0) -> np.ndarray:
    """4-node bilinear quad element conductivity matrix (unit-size element).

    Args:
        conductivity: material thermal conductivity ``k`` (W/m·K)
        thickness:    out-of-plane plate thickness (m)
    Returns:
        4x4 symmetric positive-semi-definite matrix.
    """
    return (conductivity * thickness / 6.0) * np.array(
        [
            [4.0, -1.0, -2.0, -1.0],
            [-1.0, 4.0, -1.0, -2.0],
            [-2.0, -1.0, 4.0, -1.0],
            [-1.0, -2.0, -1.0, 4.0],
        ],
        dtype=float,
    )


# --- Wave GG (v6, D036): anisotropic / orthotropic tensor conductivity -----

# 2×2 Gauss on natural [-1,1]²; Q4 node order matches mesh connectivity.
_GP = 1.0 / np.sqrt(3.0)
_GAUSS_PTS = [(-_GP, -_GP), (_GP, -_GP), (_GP, _GP), (-_GP, _GP)]
_NODE_XI = np.array([-1.0, 1.0, 1.0, -1.0])
_NODE_ETA = np.array([-1.0, -1.0, 1.0, 1.0])
# Unit-square physical element (side 1), node order n1..n4 = (0,0),(1,0),(1,1),(0,1).
_UNIT_SQUARE = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])


def conductivity_tensor(kxx: float, kyy: float, kxy: float = 0.0) -> np.ndarray:
    """Build a symmetric 2×2 conductivity tensor [[kxx, kxy], [kxy, kyy]]."""
    return np.array([[kxx, kxy], [kxy, kyy]], dtype=float)


def rotate_conductivity_tensor(k: np.ndarray, theta: float) -> np.ndarray:
    """Rotate a conductivity tensor by angle θ (rad): k' = R k Rᵀ."""
    c, s = np.cos(theta), np.sin(theta)
    R = np.array([[c, -s], [s, c]])
    return R @ np.asarray(k, dtype=float) @ R.T


def element_thermal_conductivity_tensor(k_matrix: np.ndarray, thickness: float = 1.0) -> np.ndarray:
    """4-node bilinear quad element conductivity matrix for an anisotropic
    conductivity tensor, via 2×2 Gauss quadrature on a unit-size element:

        Ke = ∫ Bᵀ k B t dA ,   B = [∂N/∂x; ∂N/∂y]  (2×4)

    For an isotropic tensor ``k·I`` this reduces (to machine precision) to the
    analytical scalar :func:`element_thermal_conductivity`.
    """
    k_matrix = np.asarray(k_matrix, dtype=float)
    if k_matrix.shape != (2, 2):
        raise SolverError("conductivity_tensor_must_be_2x2")
    if not np.allclose(k_matrix, k_matrix.T):
        raise SolverError("conductivity_tensor_must_be_symmetric")
    eigvals = np.linalg.eigvalsh(k_matrix)
    if (eigvals <= 0).any():
        raise SolverError("conductivity_tensor_must_be_positive_definite")

    ke = np.zeros((4, 4))
    for xi, eta in _GAUSS_PTS:
        dn_dxi = 0.25 * _NODE_XI * (1.0 + _NODE_ETA * eta)
        dn_deta = 0.25 * _NODE_ETA * (1.0 + _NODE_XI * xi)
        dn_nat = np.column_stack([dn_dxi, dn_deta])      # (4,2)
        jac = dn_nat.T @ _UNIT_SQUARE                    # (2,2)
        detj = np.linalg.det(jac)
        dn_dx = dn_nat @ np.linalg.inv(jac).T            # (4,2) ∂N/∂x,∂N/∂y
        # Ke += (∂N/∂x)·k·(∂N/∂x)ᵀ · detJ · t   (weight = 1 for 2×2 Gauss)
        ke += dn_dx @ k_matrix @ dn_dx.T * detj * thickness
    return ke


def _assemble_thermal_dense(
    mesh: StructuredMesh,
    density_scale: np.ndarray,
    ke: np.ndarray,
) -> np.ndarray:
    """Assemble the global conductivity matrix densely (n_nodes × n_nodes)."""
    n_nodes = mesh.nodes.shape[0]
    K = np.zeros((n_nodes, n_nodes), dtype=float)
    for elem_id, elem in enumerate(mesh.elements):
        scale = float(density_scale[elem_id])
        # Vectorised 4×4 scatter
        for i_local in range(4):
            ni = elem[i_local]
            for j_local in range(4):
                K[ni, elem[j_local]] += scale * ke[i_local, j_local]
    return K


def _assemble_thermal_dense_field(
    mesh: StructuredMesh,
    density_scale: np.ndarray,
    ke_field: np.ndarray,
) -> np.ndarray:
    """Assemble with a per-element conductivity element matrix (Wave NN, D043).

    ``ke_field`` has shape (n_elements, 4, 4) — one element matrix per element,
    so each element may carry its own (orientation-rotated) anisotropic tensor.
    """
    n_nodes = mesh.nodes.shape[0]
    K = np.zeros((n_nodes, n_nodes), dtype=float)
    for elem_id, elem in enumerate(mesh.elements):
        scale = float(density_scale[elem_id])
        ke = ke_field[elem_id]
        for i_local in range(4):
            ni = elem[i_local]
            for j_local in range(4):
                K[ni, elem[j_local]] += scale * ke[i_local, j_local]
    return K


def orientation_field_to_tensors(kxx: float, kyy: float, angles, kxy: float = 0.0) -> np.ndarray:
    """Build a per-element conductivity-tensor field from a base orthotropic tensor
    rotated by a per-element orientation (fibre-angle) field.

    Args:
        kxx, kyy, kxy: principal-axis base tensor [[kxx,kxy],[kxy,kyy]].
        angles:        per-element rotation angles (rad), shape (n_elements,).

    Returns:
        (n_elements, 2, 2) tensor field; element e uses R(θ_e)·k·R(θ_e)ᵀ.
    """
    base = conductivity_tensor(kxx, kyy, kxy)
    angles = np.asarray(angles, dtype=float).reshape(-1)
    return np.stack([rotate_conductivity_tensor(base, float(a)) for a in angles])


def thermal_node_selector(mesh: StructuredMesh, selector: str) -> list[int]:
    """Map a string selector to node IDs (mirrors mesh.selector_nodes)."""
    nodes = mesh.selector_nodes(selector)
    return list(nodes)


def solve_thermal(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    conductivity: float,
    heat_sources: list[dict[str, Any]] | None = None,
    thermal_bcs: list[dict[str, Any]] | None = None,
    conductivity_tensor: np.ndarray | None = None,
    conductivity_tensor_field: np.ndarray | None = None,
) -> ThermalResult:
    """Solve K(ρ) · T = q for nodal temperatures + thermal compliance.

    Args:
        config:         supplies thickness + SIMP penalty + min_density
        mesh:           structured quad mesh
        densities:      per-element densities (n_elements,)
        conductivity:   material thermal conductivity (constant scalar; v5
                        does not yet support per-element anisotropic k)
        heat_sources:   list of ``{"selector": str, "q": float}`` records;
                        ``q`` is total heat input distributed equally across
                        the selector's nodes (W if thickness in m)
        thermal_bcs:    list of ``{"selector": str, "temperature": float}``
                        records; nodes are fixed at the given temperature
                        (Dirichlet)

    Returns:
        ThermalResult with temperatures + thermal compliance + per-elem energy
    """
    opt = config.optimization
    densities = np.asarray(densities, dtype=float).reshape(-1)
    if densities.shape[0] != mesh.elements.shape[0]:
        raise SolverError("density_count_mismatch")

    ke_field = None
    if conductivity_tensor_field is not None:
        # Per-element anisotropic field (Wave NN, D043).
        field = np.asarray(conductivity_tensor_field, dtype=float)
        if field.shape != (mesh.elements.shape[0], 2, 2):
            raise SolverError("conductivity_tensor_field_shape")
        ke_field = np.stack(
            [element_thermal_conductivity_tensor(field[e], config.thickness) for e in range(field.shape[0])]
        )
        ke = None
    elif conductivity_tensor is not None:
        # Global anisotropic / orthotropic tensor (Wave GG, D036).
        ke = element_thermal_conductivity_tensor(conductivity_tensor, config.thickness)
    else:
        if conductivity <= 0:
            raise SolverError("nonpositive_conductivity")
        ke = element_thermal_conductivity(conductivity, config.thickness)
    active = np.where(mesh.void_mask, opt.min_density, densities)
    density_scale = opt.min_density + (active**opt.penalty) * (1.0 - opt.min_density)
    if ke_field is not None:
        K = _assemble_thermal_dense_field(mesh, density_scale, ke_field)
    else:
        K = _assemble_thermal_dense(mesh, density_scale, ke)

    n_nodes = mesh.nodes.shape[0]
    q = np.zeros(n_nodes)
    if heat_sources:
        for src in heat_sources:
            nodes = thermal_node_selector(mesh, src["selector"])
            if not nodes:
                continue
            q_per_node = float(src.get("q", 0.0)) / len(nodes)
            for n in nodes:
                q[n] += q_per_node

    fixed_nodes: list[int] = []
    fixed_temps: list[float] = []
    if thermal_bcs:
        for bc in thermal_bcs:
            nodes = thermal_node_selector(mesh, bc["selector"])
            temp = float(bc.get("temperature", 0.0))
            for n in nodes:
                fixed_nodes.append(n)
                fixed_temps.append(temp)

    # De-dup fixed nodes (last value wins, matching elastic BC semantics)
    fixed_dict: dict[int, float] = {}
    for n, t in zip(fixed_nodes, fixed_temps, strict=True):
        fixed_dict[int(n)] = float(t)

    if not fixed_dict:
        raise SolverError("thermal_no_dirichlet_bc")

    fixed_arr = np.array(sorted(fixed_dict.keys()), dtype=int)
    fixed_vals = np.array([fixed_dict[i] for i in fixed_arr], dtype=float)
    free = np.setdiff1d(np.arange(n_nodes), fixed_arr)

    if free.size == 0:
        raise SolverError("thermal_all_dofs_fixed")

    # Substitute Dirichlet: K_ff T_f = q_f - K_fd T_d
    K_ff = K[np.ix_(free, free)]
    K_fd = K[np.ix_(free, fixed_arr)]
    q_f = q[free] - K_fd @ fixed_vals

    try:
        T_free = np.linalg.solve(K_ff, q_f)
    except np.linalg.LinAlgError as exc:
        raise SolverError("thermal_singular_matrix") from exc

    T = np.zeros(n_nodes)
    T[free] = T_free
    T[fixed_arr] = fixed_vals

    thermal_compliance = float(T @ K @ T)
    max_T = float(np.max(np.abs(T)))

    elem_energy = np.zeros(mesh.elements.shape[0])
    for i, elem in enumerate(mesh.elements):
        Te = T[elem]
        ke_i = ke_field[i] if ke_field is not None else ke
        elem_energy[i] = float(Te @ ke_i @ Te)

    return ThermalResult(
        temperatures=T,
        thermal_compliance=thermal_compliance,
        max_temperature=max_T,
        element_thermal_energy=elem_energy,
        n_nodes_fixed=int(fixed_arr.size),
    )
