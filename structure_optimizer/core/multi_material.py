"""Wave BB: multi-material SIMP (v5 multi-physics layer).

Generalises classical SIMP from a single material to **M materials**.
Each material has its own (E, density) pair; each element has an
M-dim density vector ρ_e = (ρ_{1,e}, ..., ρ_{M,e}) describing the
volume fraction of each material at that element. The effective
Young's modulus per element is the SIMP-weighted sum

    E_eff(e) = E_min + Σᵢ ρ_{i,e}^p · (Eᵢ - E_min)

(Bendsøe-Sigmund style; each material has its own penalty exponent in
fancier implementations, but v5 uses a single shared penalty p).

Volume constraints are **per-material**: ``mean(ρ_i) ≤ V_i_target`` for
each material i. The optimality-criteria update is applied per-material
independently.

This is the "Sigmund-Tortorelli" form of multi-material SIMP — simpler
than the "ordered SIMP" (Pareto et al. 2012) which uses a single density
variable mapped through a smoothed Heaviside ladder. The Sigmund form
costs M × the memory but is much cleaner to implement and validate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import (
    SolverError,
    _assemble_stiffness_dense,
    element_stiffness,
)
from structure_optimizer.core.filtering import density_filter
from structure_optimizer.core.mesh import StructuredMesh


@dataclass
class MaterialProperty:
    """A single solid material's mechanical properties.

    Attributes:
        name:           identifier for reporting / fingerprints
        young_modulus:  Young's modulus E (MPa or compatible)
        poisson_ratio:  Poisson ratio (used per-material if different)
        density:        mass density (kg/m³ or compatible)
    """

    name: str
    young_modulus: float
    poisson_ratio: float
    density: float


@dataclass
class MultiMaterialResult:
    """Output of a multi-material FEM solve at fixed densities.

    Attributes:
        displacements:        global displacement vector
        compliance:           f · u total
        effective_modulus:    per-element effective E (n_elements,)
        material_volumes:     per-material volume fraction (M,)
        element_energy_per_material: (M, n_elements) strain energy for
            each material × element (used for SIMP sensitivity)
    """

    displacements: np.ndarray
    compliance: float
    effective_modulus: np.ndarray
    material_volumes: np.ndarray
    element_energy_per_material: np.ndarray


def effective_modulus_per_element(
    densities_per_material: np.ndarray,
    materials: list[MaterialProperty],
    penalty: float,
    e_min: float,
) -> np.ndarray:
    """E_eff(e) = E_min + Σᵢ ρ_{i,e}^p · (Eᵢ - E_min)

    Args:
        densities_per_material: shape (M, n_elements) — per-material per-element
        materials: list of M MaterialProperty (matches first dim)
        penalty:   SIMP exponent p (shared across materials)
        e_min:     floor Young modulus (avoid singularity at ρ=0)
    """
    densities_per_material = np.asarray(densities_per_material, dtype=float)
    M, n_elem = densities_per_material.shape
    if len(materials) != M:
        raise SolverError(f"multi_material_count_mismatch: {M} vs {len(materials)}")
    E_eff = np.full(n_elem, e_min, dtype=float)
    for i, mat in enumerate(materials):
        rho_i = densities_per_material[i]
        E_eff += np.power(np.clip(rho_i, 0.0, 1.0), penalty) * (mat.young_modulus - e_min)
    return E_eff


def solve_multi_material(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities_per_material: np.ndarray,
    materials: list[MaterialProperty],
    e_min: float = 1.0,
) -> MultiMaterialResult:
    """Solve linear-elastic FEM with per-element effective stiffness from M materials.

    Uses the first material's Poisson ratio for the Ke template (Poisson
    ratio differences are usually 2nd-order and ignored at this scope).
    """
    densities_per_material = np.asarray(densities_per_material, dtype=float)
    M, n_elem = densities_per_material.shape
    if len(materials) != M:
        raise SolverError("multi_material_count_mismatch")
    if n_elem != mesh.elements.shape[0]:
        raise SolverError("density_count_mismatch")

    opt = config.optimization
    p = opt.penalty
    nu = materials[0].poisson_ratio
    # Reference Ke at unit E (we'll scale by per-element E_eff)
    ke_unit = element_stiffness(1.0, nu)
    E_eff = effective_modulus_per_element(densities_per_material, materials, p, e_min)

    # The assembly path expects a density_scale vector that multiplies ke.
    # We craft it as ``E_eff / E_ref`` where E_ref = 1 (since ke_unit is at E=1).
    density_scale = E_eff
    K = _assemble_stiffness_dense(mesh, density_scale, ke_unit)

    # Build load vector
    n_dof = mesh.ndof
    f = np.zeros(n_dof)
    for load in config.loads:
        nodes = mesh.selector_nodes(load["selector"])
        if not nodes:
            continue
        fx = float(load.get("fx", 0.0)) / len(nodes)
        fy = float(load.get("fy", 0.0)) / len(nodes)
        for node in nodes:
            f[2 * node] += fx
            f[2 * node + 1] += fy

    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(n_dof), fixed)
    if free.size == 0:
        raise SolverError("multi_material_all_dofs_fixed")

    K_ff = K[np.ix_(free, free)]
    try:
        u_free = np.linalg.solve(K_ff, f[free])
    except np.linalg.LinAlgError as exc:
        raise SolverError("multi_material_singular_matrix") from exc

    u = np.zeros(n_dof)
    u[free] = u_free
    compliance = float(f @ u)
    material_volumes = densities_per_material.mean(axis=1)

    # Per-element per-material energy (for SIMP sensitivity)
    elem_energy = np.zeros((M, n_elem))
    for eid in range(n_elem):
        edofs = mesh.element_dofs(eid)
        ue = u[edofs]
        base = float(ue @ ke_unit @ ue)
        for i, mat in enumerate(materials):
            elem_energy[i, eid] = base * (mat.young_modulus - e_min)

    return MultiMaterialResult(
        displacements=u,
        compliance=compliance,
        effective_modulus=E_eff,
        material_volumes=material_volumes,
        element_energy_per_material=elem_energy,
    )


def _oc_update_per_material(
    densities_row: np.ndarray,
    sens_row: np.ndarray,
    target_volume: float,
    min_density: float,
    move: float = 0.2,
) -> np.ndarray:
    """Bisection-OC update for one material's density field."""
    l1, l2 = 0.0, 1e9
    updated = densities_row.copy()
    for _ in range(80):
        mid = 0.5 * (l1 + l2)
        ratio = np.maximum(1e-12, -sens_row / mid)
        candidate = np.maximum(
            min_density,
            np.maximum(
                densities_row - move,
                np.minimum(1.0, np.minimum(densities_row + move, densities_row * np.sqrt(ratio))),
            ),
        )
        if candidate.mean() > target_volume:
            l1 = mid
        else:
            l2 = mid
            updated = candidate
        if (l2 - l1) / max(1.0, l1 + l2) < 1e-4:
            break
    return np.clip(updated, min_density, 1.0)


@dataclass
class MultiMaterialOptimizationResult:
    densities_per_material: np.ndarray  # (M, n_elements)
    final_result: MultiMaterialResult
    metrics: list[dict]
    converged: bool
    mesh_shape: tuple[int, int]
    material_names: list[str]


def run_multi_material_simp(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    materials: list[MaterialProperty],
    volume_fractions: list[float],
    e_min: float = 1.0,
) -> MultiMaterialOptimizationResult:
    """SIMP main loop for M-material compliance minimisation.

    Args:
        materials:         list of M MaterialProperty
        volume_fractions:  list of M target volume fractions (one per material).
            The sum should be ≤ 1 to make physical sense; the optimiser
            does not enforce the cross-material constraint.
    """
    opt = config.optimization
    M = len(materials)
    if len(volume_fractions) != M:
        raise SolverError("multi_material_volume_fractions_length_mismatch")
    n_elem = mesh.elements.shape[0]
    # Initialise each material at its target fraction uniformly
    densities = np.zeros((M, n_elem))
    for i, vf in enumerate(volume_fractions):
        densities[i] = float(vf)

    metrics: list[dict] = []
    converged = False
    prev = densities.copy()

    for it in range(opt.max_iterations):
        result = solve_multi_material(config, mesh, densities, materials, e_min=e_min)
        p = opt.penalty
        # Per-material sensitivity: dC/dρ_{i,e} = -p ρ^(p-1) * elem_energy_per_material[i, e]
        sens = -p * np.power(np.clip(densities, opt.min_density, 1.0), p - 1.0) * result.element_energy_per_material
        # Filter each material's sensitivity independently
        for i in range(M):
            sens[i] = density_filter(mesh, densities[i], sens[i], opt.filter_radius, opt.min_density)

        new = np.zeros_like(densities)
        for i in range(M):
            new[i] = _oc_update_per_material(densities[i], sens[i], volume_fractions[i], opt.min_density)

        change = float(np.max(np.abs(new - prev)))
        metrics.append(
            {
                "iteration": it,
                "compliance": result.compliance,
                "material_volumes": result.material_volumes.tolist(),
                "max_density_change": change,
            }
        )
        prev = densities.copy()
        densities = new

        if it >= opt.min_iterations and change < opt.change_tolerance:
            converged = True
            break

    final = solve_multi_material(config, mesh, densities, materials, e_min=e_min)
    return MultiMaterialOptimizationResult(
        densities_per_material=densities,
        final_result=final,
        metrics=metrics,
        converged=converged,
        mesh_shape=(mesh.nelx, mesh.nely),
        material_names=[m.name for m in materials],
    )
