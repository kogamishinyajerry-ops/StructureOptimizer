from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.mesh import StructuredMesh


class SolverError(RuntimeError):
    """Raised when the FEM solve cannot complete."""


# Defined here (not in adapters/) so SolverError can be raised by adapters
# without an import cycle. Adapters import SolverError inside their methods.


@dataclass(frozen=True)
class FEMResult:
    """Linear-elastic FEM result: displacements + scalar metrics + per-element strain energy."""

    displacements: np.ndarray
    compliance: float
    max_displacement: float
    max_stress: float
    mass: float
    element_strain_energy: np.ndarray


def element_stiffness(young_modulus: float, poisson_ratio: float) -> np.ndarray:
    """Build the 8×8 plane-stress quad-element stiffness matrix for unit-sized elements."""
    nu = poisson_ratio
    k = np.array(
        [
            0.5 - nu / 6.0,
            0.125 + nu / 8.0,
            -0.25 - nu / 12.0,
            -0.125 + 3.0 * nu / 8.0,
            -0.25 + nu / 12.0,
            -0.125 - nu / 8.0,
            nu / 6.0,
            0.125 - 3.0 * nu / 8.0,
        ],
        dtype=float,
    )
    ke = np.array(
        [
            [k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7]],
            [k[1], k[0], k[7], k[6], k[5], k[4], k[3], k[2]],
            [k[2], k[7], k[0], k[5], k[6], k[3], k[4], k[1]],
            [k[3], k[6], k[5], k[0], k[7], k[2], k[1], k[4]],
            [k[4], k[5], k[6], k[7], k[0], k[1], k[2], k[3]],
            [k[5], k[4], k[3], k[2], k[1], k[0], k[7], k[6]],
            [k[6], k[3], k[4], k[1], k[2], k[7], k[0], k[5]],
            [k[7], k[2], k[1], k[4], k[3], k[6], k[5], k[0]],
        ],
        dtype=float,
    )
    return young_modulus / (1.0 - nu**2) * ke


def solve_linear_elastic(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    loads: list[dict] | None = None,
) -> FEMResult:
    """Assemble the SIMP-scaled stiffness matrix and solve for nodal displacements.

    Uses ``config.solver.backend`` (``dense`` or ``cg``) to perform the actual
    linear solve. Returns displacements + compliance + max displacement + max
    von Mises stress (approx, per-element) + mass + per-element strain energy
    (the SIMP sensitivity driver).
    """
    opt = config.optimization
    densities = np.asarray(densities, dtype=float).reshape(-1)
    if densities.shape[0] != mesh.elements.shape[0]:
        raise SolverError("density vector length does not match element count")

    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
    stiffness = np.zeros((mesh.ndof, mesh.ndof), dtype=float)
    active_density = np.where(mesh.void_mask, opt.min_density, densities)
    density_scale = opt.min_density + (active_density**opt.penalty) * (1.0 - opt.min_density)

    for element_id, scale in enumerate(density_scale):
        edofs = mesh.element_dofs(element_id)
        stiffness[np.ix_(edofs, edofs)] += scale * ke

    force = mesh.force_vector(loads if loads is not None else config.loads)
    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(mesh.ndof), fixed)
    if free.size == 0:
        raise SolverError("all degrees of freedom are fixed")

    from structure_optimizer.adapters.solver_base import get_linear_solver

    displacements = np.zeros(mesh.ndof, dtype=float)
    kff = stiffness[np.ix_(free, free)]
    ff = force[free]
    linear_solver = get_linear_solver(config.solver.backend)
    displacements[free] = linear_solver.solve(kff, ff)

    element_energy = np.zeros(mesh.elements.shape[0], dtype=float)
    stress = np.zeros(mesh.elements.shape[0], dtype=float)
    for element_id in range(mesh.elements.shape[0]):
        edofs = mesh.element_dofs(element_id)
        ue = displacements[edofs]
        ce = float(ue @ (ke @ ue))
        element_energy[element_id] = ce
        stress[element_id] = _approx_element_stress(mesh, element_id, ue, config)

    compliance = float(force @ displacements)
    disp_pairs = displacements.reshape((-1, 2))
    max_displacement = float(np.max(np.linalg.norm(disp_pairs, axis=1)))
    mass = compute_mass(config, mesh, active_density)
    max_stress = float(np.max(np.abs(stress)))
    return FEMResult(
        displacements=displacements,
        compliance=compliance,
        max_displacement=max_displacement,
        max_stress=max_stress,
        mass=mass,
        element_strain_energy=element_energy,
    )


def compute_mass(config: BenchmarkConfig, mesh: StructuredMesh, densities: np.ndarray) -> float:
    """Integrate density × element area × thickness × material density. Void elements contribute zero."""
    active = np.where(mesh.void_mask, 0.0, densities)
    return float(np.sum(active) * mesh.element_area * config.thickness * config.material.density)


def _approx_element_stress(
    mesh: StructuredMesh,
    element_id: int,
    ue: np.ndarray,
    config: BenchmarkConfig,
) -> float:
    _ex, _ey = mesh.element_grid_index(element_id)
    hx = mesh.width / mesh.nelx
    hy = mesh.height / mesh.nely
    ux = ue[[0, 2, 4, 6]]
    uy = ue[[1, 3, 5, 7]]
    left_ux = 0.5 * (ux[0] + ux[3])
    right_ux = 0.5 * (ux[1] + ux[2])
    bottom_uy = 0.5 * (uy[0] + uy[1])
    top_uy = 0.5 * (uy[2] + uy[3])
    exx = (right_ux - left_ux) / hx
    eyy = (top_uy - bottom_uy) / hy
    gamma_xy = ((0.5 * (uy[1] + uy[2]) - 0.5 * (uy[0] + uy[3])) / hx) + (
        (0.5 * (ux[2] + ux[3]) - 0.5 * (ux[0] + ux[1])) / hy
    )
    e = config.material.young_modulus
    nu = config.material.poisson_ratio
    c = e / (1.0 - nu**2)
    sx = c * (exx + nu * eyy)
    sy = c * (nu * exx + eyy)
    txy = e / (2.0 * (1.0 + nu)) * gamma_xy
    return float(np.sqrt(sx**2 - sx * sy + sy**2 + 3.0 * txy**2))
