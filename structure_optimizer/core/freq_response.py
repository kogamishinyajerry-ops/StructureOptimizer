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
from structure_optimizer.core.filtering import density_filter
from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.core.modal import (
    _assemble_mass_dense,
    _assemble_stiffness_dense_modal,
    element_mass_matrix,
    solve_modal,
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


# --- Wave VV (v8, D051): filtered multi-ω dynamic-compliance TO loop ---------
#
# D047's reopening criterion named a filtered MMA/OC dynamic-TO loop and a
# band-averaged (multi-ω) objective. Wave VV delivers a band-averaged
# objective J(ρ) = mean_ω |fᵀû(ω)|² with a Sigmund density filter (length scale
# / checkerboard control) and a volume-preserving projected-gradient loop
# (robust to the sign changes the dynamic-compliance sensitivity shows near
# resonance — where OC's positive-multiplier bisection is not valid).


@dataclass
class DynamicBandTOResult:
    """Output of the filtered multi-ω dynamic-compliance loop (Wave VV)."""

    densities: np.ndarray
    objective_history: list[float]
    omegas: np.ndarray
    peak_before: float
    peak_after: float
    checkerboard: float


def _checkerboard_metric(mesh: StructuredMesh, rho: np.ndarray) -> float:
    """Mean squared deviation of each interior cell from its 4-neighbour mean.

    A pure checkerboard maximises this; a smooth field drives it to ~0. Used to
    show the density filter suppresses checkerboarding.
    """
    field = np.zeros((mesh.nely, mesh.nelx))
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            field[ey, ex] = rho[mesh.element_index(ex, ey)]
    inner = field[1:-1, 1:-1]
    if inner.size == 0:
        return 0.0
    neigh = 0.25 * (field[:-2, 1:-1] + field[2:, 1:-1] + field[1:-1, :-2] + field[1:-1, 2:])
    return float(np.mean((inner - neigh) ** 2))


def dynamic_compliance_to(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    omegas,
    alpha: float = 0.0,
    beta: float = 0.0,
    n_steps: int = 20,
    move: float = 0.1,
    filter_radius: float | None = None,
    mass_type: str = "consistent",
) -> DynamicBandTOResult:
    """Volume-preserving projected-gradient TO of the **band-averaged** squared
    dynamic compliance J(ρ) = mean_ω |fᵀû(ω)|² over ``omegas`` (Wave VV, D051).

    The per-ω self-adjoint sensitivities (D047) are averaged, optionally
    Sigmund-filtered (``filter_radius``, default ``config.optimization.filter_radius``)
    to control length scale / checkerboarding, then a normalised steepest-descent
    step (clipped to ``±move``) is taken and the design rescaled to preserve the
    target volume fraction. Records J each step plus the before/after peak
    magnitude over the band.
    """
    omegas = np.asarray(omegas, dtype=float).reshape(-1)
    if omegas.size < 1:
        raise SolverError("dynamic_to_no_omegas")
    opt = config.optimization
    design = mesh.design_mask
    radius = opt.filter_radius if filter_radius is None else filter_radius
    target_vol = float(opt.volume_fraction)
    rho = np.where(mesh.void_mask, opt.min_density, target_vol)

    def band_objective(r: np.ndarray) -> float:
        return float(np.mean([dynamic_compliance_sensitivity(config, mesh, r, w, alpha, beta, mass_type).objective for w in omegas]))

    def band_peak(r: np.ndarray) -> float:
        return max(
            solve_damped_frequency_response(config, mesh, r, float(w), alpha, beta, mass_type).max_magnitude
            for w in omegas
        )

    peak_before = band_peak(rho)
    history: list[float] = []
    for _ in range(n_steps + 1):
        results = [dynamic_compliance_sensitivity(config, mesh, rho, w, alpha, beta, mass_type) for w in omegas]
        history.append(float(np.mean([r.objective for r in results])))
        if len(history) > n_steps:
            break
        grad = np.mean([r.sensitivity for r in results], axis=0)
        grad = density_filter(mesh, rho, grad, radius, opt.min_density)
        grad[~design] = 0.0
        gmax = float(np.max(np.abs(grad[design]))) if np.any(design) else 0.0
        if gmax <= 0.0:
            break
        step = np.clip(-(grad / gmax) * move, -move, move)
        rho = rho.copy()
        rho[design] = np.clip(rho[design] + step[design], opt.min_density, 1.0)
        cur = float(np.mean(rho[design]))
        if cur > 0:
            rho[design] = np.clip(rho[design] * (target_vol / cur), opt.min_density, 1.0)

    return DynamicBandTOResult(
        densities=rho,
        objective_history=history,
        omegas=omegas,
        peak_before=peak_before,
        peak_after=band_peak(rho),
        checkerboard=_checkerboard_metric(mesh, rho),
    )


# ---------------------------------------------------------------------------
# Wave DDD (v9, D059): eigenfrequency band-gap objective on the modal solver.
#
# D051's reopening criterion named an "eigenfrequency-gap (band-stop) objective
# built on the modal solver". The band gap between consecutive modes is
# g = ω²_{m+1} − ω²_m; maximising it pushes the natural frequencies apart (a
# phononic band-stop). The eigenvalue sensitivity is the textbook result for
# mass-normalised modes (φᵀMφ = 1):
#     dλ_i/dρ_e = φ_e,iᵀ (dk_scale_e·ke − λ_i·dm_scale_e·me) φ_e,i ,
# so dg/dρ_e = dλ_{m+1}/dρ_e − dλ_m/dρ_e. solve_modal returns φ already
# mass-normalised (it whitens with the mass Cholesky factor).
# ---------------------------------------------------------------------------


@dataclass
class BandGapResult:
    """Output of band-gap maximisation (Wave DDD)."""

    densities: np.ndarray
    gap_history: list[float]
    omega2_initial: np.ndarray
    omega2_final: np.ndarray
    lower_mode: int
    converged: bool


def _eigenvalue_sensitivities(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    n_modes: int,
    mass_type: str = "consistent",
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(omega2[n_modes], dlambda_drho[n_modes, n_elem])`` — the smallest
    ``n_modes`` eigenvalues and their analytic sensitivities w.r.t. each density.
    """
    opt = config.optimization
    densities = np.asarray(densities, dtype=float).reshape(-1)
    modal = solve_modal(config, mesh, densities, n_modes=n_modes, mass_type=mass_type)
    omega2 = modal.omega_squared
    phi_free = modal.eigenvectors  # (n_free, n_modes), mass-normalised
    free = modal.free_dofs

    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
    me = element_mass_matrix(config.material.density, config.thickness, mass_type)
    active = np.where(mesh.void_mask, opt.min_density, densities)
    dk = opt.penalty * np.power(active, opt.penalty - 1.0) * (1.0 - opt.min_density)
    dm = np.full_like(active, 1.0 - opt.min_density)

    # Scatter eigenvectors to the full DOF vector (0 on fixed DOFs).
    n_elem = mesh.elements.shape[0]
    phi_full = np.zeros((mesh.ndof, n_modes))
    phi_full[free, :] = phi_free
    dlambda = np.zeros((n_modes, n_elem))
    for e, nodes in enumerate(mesh.elements):
        if mesh.void_mask[e]:
            continue
        dofs = np.empty(8, dtype=int)
        dofs[0::2] = 2 * nodes
        dofs[1::2] = 2 * nodes + 1
        phi_e = phi_full[dofs, :]  # (8, n_modes)
        ke_phi = ke @ phi_e
        me_phi = me @ phi_e
        for i in range(n_modes):
            pe = phi_e[:, i]
            dlambda[i, e] = dk[e] * float(pe @ ke_phi[:, i]) - omega2[i] * dm[e] * float(pe @ me_phi[:, i])
    return omega2, dlambda


def band_gap_sensitivity(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    lower_mode: int = 0,
    mass_type: str = "consistent",
) -> tuple[float, np.ndarray]:
    """Band gap ``g = ω²_{m+1} − ω²_m`` and its sensitivity ``dg/dρ`` (Wave DDD,
    D059), where ``m = lower_mode`` (0-indexed). Returns ``(gap, dgap_drho)``."""
    if lower_mode < 0:
        raise SolverError("band_gap_negative_mode")
    omega2, dlambda = _eigenvalue_sensitivities(config, mesh, densities, lower_mode + 2, mass_type)
    gap = float(omega2[lower_mode + 1] - omega2[lower_mode])
    dgap = dlambda[lower_mode + 1] - dlambda[lower_mode]
    return gap, dgap


def maximize_band_gap(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    lower_mode: int = 0,
    n_steps: int = 20,
    move: float = 0.1,
    filter_radius: float | None = None,
    mass_type: str = "consistent",
) -> BandGapResult:
    """Volume-preserving projected-gradient **ascent** on the band gap
    ``ω²_{m+1} − ω²_m`` (Wave DDD, D059): a band-stop topology that pushes two
    adjacent natural frequencies apart. Reuses the Sigmund density filter and the
    same move-limited, volume-rescaled step as ``dynamic_compliance_to``."""
    opt = config.optimization
    radius = opt.filter_radius if filter_radius is None else filter_radius
    design = mesh.design_mask
    rho = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    target_vol = float(np.mean(rho[design])) if np.any(design) else 0.0

    omega2_initial, _ = _eigenvalue_sensitivities(config, mesh, rho, lower_mode + 2, mass_type)
    gap_history: list[float] = []
    converged = False
    for _ in range(n_steps):
        gap, dgap = band_gap_sensitivity(config, mesh, rho, lower_mode, mass_type)
        gap_history.append(gap)
        grad = density_filter(mesh, rho, dgap, radius, opt.min_density)
        grad[~design] = 0.0
        gmax = float(np.max(np.abs(grad[design]))) if np.any(design) else 0.0
        if gmax <= 0.0:
            converged = True
            break
        step = np.clip((grad / gmax) * move, -move, move)  # + : ascend the gap
        rho = rho.copy()
        rho[design] = np.clip(rho[design] + step[design], opt.min_density, 1.0)
        cur = float(np.mean(rho[design]))
        if cur > 0:
            rho[design] = np.clip(rho[design] * (target_vol / cur), opt.min_density, 1.0)

    final_gap, _ = band_gap_sensitivity(config, mesh, rho, lower_mode, mass_type)
    gap_history.append(final_gap)
    omega2_final, _ = _eigenvalue_sensitivities(config, mesh, rho, lower_mode + 2, mass_type)
    return BandGapResult(
        densities=rho,
        gap_history=gap_history,
        omega2_initial=omega2_initial,
        omega2_final=omega2_final,
        lower_mode=lower_mode,
        converged=converged,
    )


# ---------------------------------------------------------------------------
# Wave LLL (D067): target-band placement — minimax around a target frequency.
# Where ``maximize_band_gap`` moves *eigenvalues* apart, this minimises the
# worst-case forced response over a target frequency band: a band-suppression /
# vibration-isolation design. The minimax is smoothed by a p-norm over sampled
# in-band frequencies,
#     J_PN = (Σ_k J(ω_k)^p)^(1/p) → max_k J(ω_k)   as p → ∞,
# whose density sensitivity chains the per-frequency self-adjoint sensitivity
# of ``dynamic_compliance_sensitivity``:
#     dJ_PN/dρ = Σ_k (J_k / J_PN)^(p−1) · dJ_k/dρ.
# ---------------------------------------------------------------------------


@dataclass
class TargetBandResult:
    """Output of target-band placement (Wave LLL, D067)."""

    densities: np.ndarray
    peak_history: list[float]
    band_omegas: np.ndarray
    peak_initial: float
    peak_final: float
    converged: bool


def target_band_peak_sensitivity(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    band_omegas: np.ndarray,
    alpha: float = 0.0,
    beta: float = 0.0,
    p: float = 12.0,
    mass_type: str = "consistent",
) -> tuple[float, np.ndarray, np.ndarray]:
    """Smooth in-band peak dynamic compliance + its density sensitivity (Wave
    LLL, D067).

    Samples the squared dynamic compliance ``J(ω_k) = |fᵀû(ω_k)|²`` at each
    ``ω_k`` in ``band_omegas`` (via :func:`dynamic_compliance_sensitivity`) and
    aggregates them into the p-norm peak ``J_PN = (Σ_k J_k^p)^(1/p)`` — a smooth
    surrogate for ``max_k J_k`` (minimax around the band's target). The
    sensitivity chains the per-frequency self-adjoint sensitivity:
    ``dJ_PN/dρ = Σ_k (J_k/J_PN)^(p−1) · dJ_k/dρ``. Validated against central FD to
    relative error ≤ 1e-4.

    Returns ``(peak_pnorm, dpeak_drho, per_freq_J)``.
    """
    if p <= 0:
        raise SolverError("target_band_nonpositive_p")
    band = np.atleast_1d(np.asarray(band_omegas, dtype=float))
    if band.size == 0:
        raise SolverError("target_band_empty")
    n_elem = mesh.elements.shape[0]
    per_freq_j = np.zeros(band.size)
    dj = np.zeros((band.size, n_elem))
    for k, w in enumerate(band):
        r = dynamic_compliance_sensitivity(config, mesh, densities, float(w), alpha, beta, mass_type)
        per_freq_j[k] = r.objective
        dj[k] = r.sensitivity
    jmax = float(per_freq_j.max())
    if jmax <= 0.0:
        return 0.0, np.zeros(n_elem), per_freq_j
    peak = float(jmax * np.sum((per_freq_j / jmax) ** p) ** (1.0 / p))
    weights = (per_freq_j / peak) ** (p - 1.0)
    dpeak = weights @ dj
    return peak, dpeak, per_freq_j


def target_band_placement(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    band_omegas: np.ndarray,
    alpha: float = 0.0,
    beta: float = 1e-4,
    n_steps: int = 20,
    move: float = 0.1,
    p: float = 12.0,
    filter_radius: float | None = None,
    mass_type: str = "consistent",
) -> TargetBandResult:
    """Minimax-around-target: minimise the worst-case (peak) forced response over
    a target frequency band (Wave LLL, D067).

    D059's reopening criterion was *target-band placement* (the band-gap wave only
    pushed two eigenvalues apart). This drives a volume-preserving, move-limited
    projected-gradient **descent** on the smooth in-band peak
    (:func:`target_band_peak_sensitivity`), reusing the Sigmund density filter and
    the same volume-rescale step as :func:`maximize_band_gap`. The result is a
    band-suppression topology: resonances are pushed out of (or damped within) the
    target band so the worst-case response drops.
    """
    opt = config.optimization
    radius = opt.filter_radius if filter_radius is None else filter_radius
    design = mesh.design_mask
    rho = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    target_vol = float(np.mean(rho[design])) if np.any(design) else 0.0

    _, _, j_initial = target_band_peak_sensitivity(config, mesh, rho, band_omegas, alpha, beta, p, mass_type)
    peak_initial = float(j_initial.max())
    peak_history: list[float] = []
    converged = False
    for _ in range(n_steps):
        _, dpeak, j_cur = target_band_peak_sensitivity(config, mesh, rho, band_omegas, alpha, beta, p, mass_type)
        peak_history.append(float(j_cur.max()))
        grad = density_filter(mesh, rho, dpeak, radius, opt.min_density)
        grad[~design] = 0.0
        gmax = float(np.max(np.abs(grad[design]))) if np.any(design) else 0.0
        if gmax <= 0.0:
            converged = True
            break
        step = np.clip((grad / gmax) * move, -move, move)  # − : descend the peak
        rho = rho.copy()
        rho[design] = np.clip(rho[design] - step[design], opt.min_density, 1.0)
        cur = float(np.mean(rho[design]))
        if cur > 0:
            rho[design] = np.clip(rho[design] * (target_vol / cur), opt.min_density, 1.0)

    _, _, j_final = target_band_peak_sensitivity(config, mesh, rho, band_omegas, alpha, beta, p, mass_type)
    peak_final = float(j_final.max())
    peak_history.append(peak_final)
    return TargetBandResult(
        densities=rho,
        peak_history=peak_history,
        band_omegas=np.atleast_1d(np.asarray(band_omegas, dtype=float)),
        peak_initial=peak_initial,
        peak_final=peak_final,
        converged=converged,
    )
