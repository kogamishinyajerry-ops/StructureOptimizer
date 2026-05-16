"""Wave Z: frequency-domain harmonic-response analysis — v5 multi-physics.

Solves the steady-state harmonic problem

    (K - ω² M) û = f̂

for the complex displacement amplitude û at a single excitation frequency
ω, given the SIMP-scaled stiffness K(ρ), mass M(ρ), and load amplitude f̂.

This is the frequency-domain analogue of `fem2d.solve_linear_elastic`. The
key engineering use is **anti-resonance design**: keep |û(ω)| small at a
target frequency by topology-optimising K - ω² M to be well-conditioned.

Damping is intentionally omitted (zero structural damping); adding
Rayleigh damping (C = αM + βK) would extend this to a complex system

    (K - ω² M + iω C) û = f̂

which is a v5+ extension if real workflows demand it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import SolverError, element_stiffness
from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.core.modal import (
    _assemble_mass_dense,
    _assemble_stiffness_dense_modal,
    element_mass_matrix,
)


@dataclass
class FrequencyResponseResult:
    """Output of a single-frequency harmonic-response solve.

    Attributes:
        omega:           excitation angular frequency (rad/s)
        displacements:   real-valued displacement amplitudes (n_dof,)
        max_displacement: max absolute amplitude (objective for anti-resonance)
        response_norm:   ‖u‖₂  (alternative scalar response measure)
    """

    omega: float
    displacements: np.ndarray
    max_displacement: float
    response_norm: float


def solve_frequency_response(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    omega: float,
    mass_type: str = "consistent",
) -> FrequencyResponseResult:
    """Solve (K - ω² M) u = f at a single excitation frequency.

    Uses the same `config.loads` / `config.boundary_conditions` as
    `solve_linear_elastic`; the load is interpreted as a force amplitude
    at angular frequency ω.

    Args:
        config:     BenchmarkConfig
        mesh:       structured-quad mesh
        densities:  per-element densities
        omega:      excitation angular frequency (rad/s)
        mass_type:  "consistent" or "lumped"
    """
    if omega < 0:
        raise SolverError("frequency_response_negative_omega")

    opt = config.optimization
    densities = np.asarray(densities, dtype=float).reshape(-1)
    if densities.shape[0] != mesh.elements.shape[0]:
        raise SolverError("density_count_mismatch")

    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
    me = element_mass_matrix(config.material.density, config.thickness, mass_type)

    active = np.where(mesh.void_mask, opt.min_density, densities)
    k_scale = opt.min_density + (active**opt.penalty) * (1.0 - opt.min_density)
    m_scale = opt.min_density + active * (1.0 - opt.min_density)

    K = _assemble_stiffness_dense_modal(mesh, k_scale, ke)
    M = _assemble_mass_dense(mesh, m_scale, me)

    # Assemble load vector at the configured load locations
    n_dof = mesh.ndof
    f = np.zeros(n_dof)
    for load in config.loads:
        nodes = mesh.selector_nodes(load["selector"])
        if not nodes:
            continue
        fx = float(load.get("fx", 0.0))
        fy = float(load.get("fy", 0.0))
        for node in nodes:
            f[2 * node] += fx / len(nodes)
            f[2 * node + 1] += fy / len(nodes)

    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(n_dof), fixed)
    if free.size == 0:
        raise SolverError("frequency_response_all_dofs_fixed")

    # Dynamic stiffness D = K - ω² M (real-valued, no damping)
    D = K - (omega**2) * M
    D_ff = D[np.ix_(free, free)]
    f_f = f[free]

    try:
        u_free = np.linalg.solve(D_ff, f_f)
    except np.linalg.LinAlgError as exc:
        # Singular at exact resonance — expected near eigenvalues
        raise SolverError("frequency_response_resonance_singular") from exc

    u = np.zeros(n_dof)
    u[free] = u_free

    return FrequencyResponseResult(
        omega=float(omega),
        displacements=u,
        max_displacement=float(np.max(np.abs(u))),
        response_norm=float(np.linalg.norm(u)),
    )


def frequency_sweep(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    omega_values: np.ndarray,
    mass_type: str = "consistent",
) -> dict[str, np.ndarray]:
    """Sweep across a list of frequencies, returning max-disp / response-norm
    as arrays. Skips frequencies where the dynamic stiffness is singular
    (i.e. at exact resonance)."""
    omega_arr = np.asarray(omega_values, dtype=float)
    max_disp = np.zeros_like(omega_arr)
    resp_norm = np.zeros_like(omega_arr)
    valid = np.ones_like(omega_arr, dtype=bool)
    for i, w in enumerate(omega_arr):
        try:
            r = solve_frequency_response(config, mesh, densities, float(w), mass_type=mass_type)
            max_disp[i] = r.max_displacement
            resp_norm[i] = r.response_norm
        except SolverError:
            valid[i] = False
            max_disp[i] = np.inf
            resp_norm[i] = np.inf
    return {
        "omega": omega_arr,
        "max_displacement": max_disp,
        "response_norm": resp_norm,
        "valid": valid,
    }
