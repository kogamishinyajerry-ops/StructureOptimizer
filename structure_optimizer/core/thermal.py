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
    if conductivity <= 0:
        raise SolverError("nonpositive_conductivity")

    ke = element_thermal_conductivity(conductivity, config.thickness)
    active = np.where(mesh.void_mask, opt.min_density, densities)
    density_scale = opt.min_density + (active**opt.penalty) * (1.0 - opt.min_density)
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
    for n, t in zip(fixed_nodes, fixed_temps):
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
        elem_energy[i] = float(Te @ ke @ Te)

    return ThermalResult(
        temperatures=T,
        thermal_compliance=thermal_compliance,
        max_temperature=max_T,
        element_thermal_energy=elem_energy,
        n_nodes_fixed=int(fixed_arr.size),
    )
