"""Wave Z: frequency-domain harmonic-response analysis — v5 multi-physics.

Solves the steady-state harmonic problem

    (K - ω² M) û = f̂

for the complex displacement amplitude û at a single excitation frequency
ω, given the SIMP-scaled stiffness K(ρ), mass M(ρ), and load amplitude f̂.

This is the frequency-domain analogue of `fem2d.solve_linear_elastic`. The
key engineering use is **anti-resonance design**: keep |û(ω)| small at a
target frequency by topology-optimising K - ω² M to be well-conditioned.

The undamped solve below omits structural damping. Wave FF (v6, D035) adds
the Rayleigh-damped complex system

    (K - ω² M + iω C) û = f̂ ,   C = α M + β K

via ``solve_damped_frequency_response`` — see the bottom of this module. The
damped response is finite at resonance (the undamped one is singular there),
and its modal damping ratio ζ_i = ½(α/ω_i + β ω_i) is verified through the
half-power bandwidth Δω ≈ 2 ζ ω_n (``half_power_bandwidth``).
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


# --- Wave FF (v6, D035): Rayleigh-damped complex frequency response --------


@dataclass
class DampedFrequencyResponseResult:
    """Output of a single-frequency Rayleigh-damped harmonic solve.

    Attributes:
        omega:           excitation angular frequency (rad/s)
        displacements:   complex displacement amplitudes û (n_dof,)
        magnitude:       |û| per DOF (real, ≥ 0)
        phase:           arg(û) per DOF (rad)
        max_magnitude:   max |û| (anti-resonance objective)
        response_norm:   ‖û‖₂ (complex 2-norm)
        alpha:           mass-proportional Rayleigh coefficient
        beta:            stiffness-proportional Rayleigh coefficient
    """

    omega: float
    displacements: np.ndarray
    magnitude: np.ndarray
    phase: np.ndarray
    max_magnitude: float
    response_norm: float
    alpha: float
    beta: float


def rayleigh_modal_damping_ratio(alpha: float, beta: float, omega_n: float) -> float:
    """Modal damping ratio ζ = ½(α/ω + β ω) for Rayleigh damping C = αM + βK."""
    if omega_n <= 0:
        raise SolverError("rayleigh_damping_nonpositive_omega")
    return 0.5 * (alpha / omega_n + beta * omega_n)


def solve_damped_frequency_response(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    omega: float,
    alpha: float = 0.0,
    beta: float = 0.0,
    mass_type: str = "consistent",
) -> DampedFrequencyResponseResult:
    """Solve the complex dynamic system (K - ω²M + iωC) û = f̂, C = αM + βK.

    With ``alpha == beta == 0`` this reduces to the undamped real system and
    its magnitude matches :func:`solve_frequency_response`. With damping the
    response stays finite at resonance.

    Args:
        config:     BenchmarkConfig
        mesh:       structured-quad mesh
        densities:  per-element densities
        omega:      excitation angular frequency (rad/s)
        alpha:      mass-proportional Rayleigh coefficient (≥ 0)
        beta:       stiffness-proportional Rayleigh coefficient (≥ 0)
        mass_type:  "consistent" or "lumped"
    """
    if omega < 0:
        raise SolverError("frequency_response_negative_omega")
    if alpha < 0 or beta < 0:
        raise SolverError("rayleigh_damping_negative_coefficient")

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
    C = alpha * M + beta * K  # Rayleigh damping

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

    # Complex dynamic stiffness D = K - ω²M + iωC
    D = (K - (omega**2) * M).astype(complex)
    D = D + 1j * omega * C
    D_ff = D[np.ix_(free, free)]
    f_f = f[free].astype(complex)

    try:
        u_free = np.linalg.solve(D_ff, f_f)
    except np.linalg.LinAlgError as exc:
        raise SolverError("frequency_response_singular") from exc

    u = np.zeros(n_dof, dtype=complex)
    u[free] = u_free
    magnitude = np.abs(u)
    return DampedFrequencyResponseResult(
        omega=float(omega),
        displacements=u,
        magnitude=magnitude,
        phase=np.angle(u),
        max_magnitude=float(np.max(magnitude)),
        response_norm=float(np.linalg.norm(u)),
        alpha=float(alpha),
        beta=float(beta),
    )


def half_power_bandwidth(omega_arr: np.ndarray, magnitude: np.ndarray) -> dict[str, float]:
    """Half-power (−3 dB) bandwidth of a resonance peak in a magnitude sweep.

    Finds the peak, then the frequencies on either side where the magnitude
    drops to peak/√2. Returns peak frequency, the two half-power frequencies,
    bandwidth Δω, and the implied damping ratio ζ ≈ Δω / (2 ω_peak).

    Requires the sweep to bracket the peak on both sides at the half-power
    level; raises ``SolverError`` otherwise.
    """
    omega_arr = np.asarray(omega_arr, dtype=float)
    magnitude = np.asarray(magnitude, dtype=float)
    if omega_arr.shape != magnitude.shape or omega_arr.size < 3:
        raise SolverError("half_power_bandwidth_bad_sweep")

    peak_i = int(np.argmax(magnitude))
    peak_val = magnitude[peak_i]
    target = peak_val / np.sqrt(2.0)
    omega_peak = omega_arr[peak_i]

    def _cross(lo_idx: int, hi_idx: int, step: int) -> float:
        # Walk from peak outward (step ±1) to first index below target, then
        # linearly interpolate the crossing frequency.
        i = peak_i
        while 0 <= i + step <= magnitude.size - 1:
            j = i + step
            if magnitude[j] <= target:
                # interpolate between i (above) and j (below)
                m_i, m_j = magnitude[i], magnitude[j]
                w_i, w_j = omega_arr[i], omega_arr[j]
                if m_i == m_j:
                    return float(w_j)
                t = (m_i - target) / (m_i - m_j)
                return float(w_i + t * (w_j - w_i))
            i = j
        raise SolverError("half_power_bandwidth_not_bracketed")

    w_low = _cross(0, peak_i, -1)
    w_high = _cross(peak_i, magnitude.size - 1, +1)
    bandwidth = w_high - w_low
    return {
        "omega_peak": float(omega_peak),
        "omega_low": w_low,
        "omega_high": w_high,
        "bandwidth": float(bandwidth),
        "damping_ratio": float(bandwidth / (2.0 * omega_peak)) if omega_peak > 0 else float("nan"),
    }


# --- Wave RR (v7, D047): damped frequency-response TO (dynamic compliance) ---
#
# D035's reopening criterion named the driver: turn the damped harmonic forward
# solve into a topology-optimisation objective. The natural objective is the
# squared dynamic compliance J(ρ) = |c|², c = fᵀû, of the complex system
# D(ω)û = f, D = K − ω²M + iωC, C = αM + βK. Because K, M, C (hence D) are
# symmetric (not Hermitian) and the "output" load equals the input load, the
# adjoint is self-adjoint: dc/dρ_e = −û_eᵀ (dD_e/dρ_e) û_e, and
# dJ/dρ_e = 2·Re(c̄ · dc/dρ_e).


def _build_harmonic_load(config: BenchmarkConfig, mesh: StructuredMesh) -> np.ndarray:
    """Real load amplitude vector f̂ (same convention as the damped solver)."""
    f = np.zeros(mesh.ndof)
    for load in config.loads:
        nodes = mesh.selector_nodes(load["selector"])
        if not nodes:
            continue
        fx = float(load.get("fx", 0.0))
        fy = float(load.get("fy", 0.0))
        for node in nodes:
            f[2 * node] += fx / len(nodes)
            f[2 * node + 1] += fy / len(nodes)
    return f


@dataclass
class DynamicComplianceResult:
    """Squared dynamic compliance + its self-adjoint sensitivity (Wave RR).

    Attributes:
        omega, alpha, beta:  excitation frequency + Rayleigh coefficients
        dynamic_compliance:  complex c = fᵀû
        objective:           J = |c|² (real, the minimisation objective)
        sensitivity:         dJ/dρ_e (real, per element)
        converged:           whether the complex solve succeeded
    """

    omega: float
    alpha: float
    beta: float
    dynamic_compliance: complex
    objective: float
    sensitivity: np.ndarray
    converged: bool


def dynamic_compliance_sensitivity(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    omega: float,
    alpha: float = 0.0,
    beta: float = 0.0,
    mass_type: str = "consistent",
) -> DynamicComplianceResult:
    """Squared dynamic compliance J = |fᵀû|² and its analytic sensitivity dJ/dρ.

    Self-adjoint (symmetric complex D, output load = input load):
        dc/dρ_e = −û_eᵀ (dD_e/dρ_e) û_e,
        dD_e/dρ_e = (dk_scale/dρ_e)(1 + iωβ)·ke + (dm_scale/dρ_e)(−ω² + iωα)·me,
        dJ/dρ_e = 2·Re(c̄ · dc/dρ_e).
    """
    if omega < 0:
        raise SolverError("frequency_response_negative_omega")
    if alpha < 0 or beta < 0:
        raise SolverError("rayleigh_damping_negative_coefficient")
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
    C = alpha * M + beta * K

    n_dof = mesh.ndof
    f = _build_harmonic_load(config, mesh)
    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(n_dof), fixed)
    if free.size == 0:
        raise SolverError("frequency_response_all_dofs_fixed")

    D = (K - (omega**2) * M).astype(complex) + 1j * omega * C
    try:
        u_free = np.linalg.solve(D[np.ix_(free, free)], f[free].astype(complex))
    except np.linalg.LinAlgError as exc:
        raise SolverError("frequency_response_singular") from exc
    u = np.zeros(n_dof, dtype=complex)
    u[free] = u_free

    c = complex(f @ u)
    objective = float((c * np.conjugate(c)).real)

    # Per-element scale derivatives (design elements only).
    dk = opt.penalty * np.power(active, opt.penalty - 1.0) * (1.0 - opt.min_density)
    dm = np.full_like(active, 1.0 - opt.min_density)
    coef_k = 1.0 + 1j * omega * beta
    coef_m = -(omega**2) + 1j * omega * alpha

    sens = np.zeros(mesh.elements.shape[0])
    c_bar = np.conjugate(c)
    for e, nodes in enumerate(mesh.elements):
        if mesh.void_mask[e]:
            continue
        dofs = np.empty(8, dtype=int)
        dofs[0::2] = 2 * nodes
        dofs[1::2] = 2 * nodes + 1
        ue = u[dofs]
        dDe = (dk[e] * coef_k) * ke + (dm[e] * coef_m) * me
        dc = -complex(ue @ (dDe @ ue))
        sens[e] = 2.0 * float((c_bar * dc).real)

    return DynamicComplianceResult(
        omega=float(omega),
        alpha=float(alpha),
        beta=float(beta),
        dynamic_compliance=c,
        objective=objective,
        sensitivity=sens,
        converged=True,
    )


@dataclass
class DynamicTOResult:
    """Output of the resonance-avoidance descent (Wave RR)."""

    densities: np.ndarray
    objective_history: list[float]
    omega: float


def minimize_dynamic_compliance(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    omega: float,
    alpha: float = 0.0,
    beta: float = 0.0,
    n_steps: int = 20,
    move: float = 0.1,
    mass_type: str = "consistent",
) -> DynamicTOResult:
    """Volume-preserving projected-gradient descent on the squared dynamic
    compliance J = |fᵀû|² at a fixed excitation frequency ω (resonance avoidance).

    Starts from the uniform design at ``volume_fraction``; each step takes a
    normalised steepest-descent move (clipped to ``±move``), clips to
    [min_density, 1], and rescales the design elements to preserve the target
    volume. Records J each step. This is a compact driver, not a full MMA loop —
    the verifiable claim is that the analytic sensitivity drives J down.
    """
    opt = config.optimization
    design = mesh.design_mask
    target_vol = float(opt.volume_fraction)
    rho = np.where(mesh.void_mask, opt.min_density, target_vol)

    history: list[float] = []
    for _ in range(n_steps + 1):
        res = dynamic_compliance_sensitivity(config, mesh, rho, omega, alpha, beta, mass_type)
        history.append(res.objective)
        if len(history) > n_steps:
            break
        g = res.sensitivity
        gmax = float(np.max(np.abs(g[design]))) if np.any(design) else 0.0
        if gmax <= 0.0:
            break
        step = np.clip(-(g / gmax) * move, -move, move)
        rho = rho.copy()
        rho[design] = np.clip(rho[design] + step[design], opt.min_density, 1.0)
        # Rescale design densities to preserve the target volume fraction.
        cur = float(np.mean(rho[design]))
        if cur > 0:
            rho[design] = np.clip(rho[design] * (target_vol / cur), opt.min_density, 1.0)
    return DynamicTOResult(densities=rho, objective_history=history, omega=float(omega))
