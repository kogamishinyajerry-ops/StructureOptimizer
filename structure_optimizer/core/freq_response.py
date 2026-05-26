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


# ---------------------------------------------------------------------------
# Wave TTT (v11, D075): adaptive in-band sampling + peak-as-MMA-constraint.
#
# D067's reopening criterion named "adaptive band sampling; peak-as-constraint".
# target_band_placement (D067) samples a *fixed* ω-grid and runs projected-
# gradient descent with the peak as the *objective*. Both are limited: a sharp
# resonance falling between fixed grid points is missed (the optimiser then
# "suppresses" a peak it never saw), and peak-as-objective cannot express
# "least material such that resonance stays bounded". TTT cashes in both.
# ---------------------------------------------------------------------------


def _dynamic_compliance_objective(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    omega: float,
    alpha: float = 0.0,
    beta: float = 0.0,
    mass_type: str = "consistent",
) -> float:
    """Forward-only squared dynamic compliance ``J = |fᵀû|²`` at ``omega``.

    Same complex dynamic-stiffness solve as :func:`dynamic_compliance_sensitivity`
    but **without** the per-element adjoint loop — used by the adaptive sampler,
    which needs only the objective at many frequencies.
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
    f = _build_harmonic_load(config, mesh)
    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(mesh.ndof), fixed)
    if free.size == 0:
        raise SolverError("frequency_response_all_dofs_fixed")
    D = (K - (omega**2) * M).astype(complex) + 1j * omega * C
    try:
        u_free = np.linalg.solve(D[np.ix_(free, free)], f[free].astype(complex))
    except np.linalg.LinAlgError as exc:
        raise SolverError("frequency_response_singular") from exc
    c = complex(f[free] @ u_free)
    return float((c * np.conjugate(c)).real)


@dataclass
class AdaptiveBandResult:
    """Output of :func:`adaptive_band_sample` (Wave TTT, D075)."""

    omegas: np.ndarray  # sorted sample frequencies (n_init + n_refine,)
    values: np.ndarray  # J(ω) at each sample
    peak_value: float
    peak_omega: float
    n_evals: int


def adaptive_band_sample(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    omega_lo: float,
    omega_hi: float,
    n_init: int = 5,
    n_refine: int = 10,
    alpha: float = 0.0,
    beta: float = 0.0,
    mass_type: str = "consistent",
) -> AdaptiveBandResult:
    """Adaptively sample the forced-response magnitude over ``[omega_lo, omega_hi]``
    to capture a sharp in-band resonance peak (Wave TTT, D075).

    Starts from ``n_init`` uniform samples, then performs ``n_refine`` bisection
    steps: each step bisects the sub-interval **adjacent to the current peak
    sample** whose endpoints have the larger summed response, inserting the
    midpoint. This concentrates evaluations around the resonance, so the returned
    ``peak_value`` converges to the true band maximum with far fewer solves than a
    uniform grid of equal resolution.

    Returns an :class:`AdaptiveBandResult` (sorted ``omegas`` / ``values`` +
    ``peak_value`` / ``peak_omega`` + total ``n_evals``).
    """
    if not (omega_hi > omega_lo):
        raise SolverError("adaptive_band_invalid_range")
    if n_init < 2:
        raise SolverError("adaptive_band_too_few_initial")
    omegas = list(np.linspace(float(omega_lo), float(omega_hi), n_init))
    values = [
        _dynamic_compliance_objective(config, mesh, densities, w, alpha, beta, mass_type) for w in omegas
    ]
    for _ in range(max(0, n_refine)):
        i_peak = int(np.argmax(values))
        candidates: list[tuple[int, int]] = []
        if i_peak > 0:
            candidates.append((i_peak - 1, i_peak))
        if i_peak < len(omegas) - 1:
            candidates.append((i_peak, i_peak + 1))
        a, b = max(candidates, key=lambda t: values[t[0]] + values[t[1]])
        w_mid = 0.5 * (omegas[a] + omegas[b])
        j_mid = _dynamic_compliance_objective(config, mesh, densities, w_mid, alpha, beta, mass_type)
        omegas.insert(b, w_mid)
        values.insert(b, j_mid)
    omegas_arr = np.asarray(omegas, dtype=float)
    values_arr = np.asarray(values, dtype=float)
    ipk = int(np.argmax(values_arr))
    return AdaptiveBandResult(
        omegas=omegas_arr,
        values=values_arr,
        peak_value=float(values_arr[ipk]),
        peak_omega=float(omegas_arr[ipk]),
        n_evals=len(omegas_arr),
    )


@dataclass
class PeakConstrainedTOResult:
    """Output of :func:`peak_constrained_mma` (Wave TTT, D075)."""

    densities: np.ndarray
    compliance_history: list[float]
    volume_history: list[float]
    peak_history: list[float]
    peak_limit: float
    band_omegas: np.ndarray
    converged: bool


def peak_constrained_mma(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    peak_limit: float,
    band_omegas: np.ndarray,
    alpha: float = 0.0,
    beta: float = 1e-4,
    vf: float | None = None,
    max_iter: int = 40,
    change_tol: float = 1e-3,
    p: float = 12.0,
    mass_type: str = "consistent",
) -> PeakConstrainedTOResult:
    """Minimise static compliance subject to an in-band **peak-as-constraint** on
    the forced response *and* a volume fraction, via MMA (Wave TTT, D075).

    D067 drove the peak as the *objective* (volume-preserving descent). Its
    reopening criterion named making the peak a genuine **constraint** so it can
    sit alongside a primary objective. This driver does exactly that, reusing the
    proven D066 two-constraint MMA structure with the dynamic peak swapped in for
    the stress. The two inequalities for :func:`core.mma.mma_step` are

        ``g₁(x) = J_peak(x) / J_lim − 1 ≤ 0``   (in-band forced-response peak)
        ``g₂(x) = mean(x) − vf ≤ 0``            (volume)

    minimising the standard SIMP static compliance (gradient
    ``dc/dρ_e = −dscale_e·(uₑᵀ kₑ uₑ)``). The peak-constraint gradient is the
    smooth p-norm band-peak sensitivity (:func:`target_band_peak_sensitivity`).
    Holding volume as its own constraint keeps the design from collapsing to
    minimum density (which a min-volume objective with a single-frequency peak
    constraint does, by detuning). Both gradients are density-filtered.
    """
    from structure_optimizer.core.fem2d import solve_linear_elastic
    from structure_optimizer.core.mma import MMAState, mma_step

    if not (peak_limit > 0.0):
        raise SolverError("peak_constrained_nonpositive_limit")
    opt = config.optimization
    design = mesh.design_mask
    n_design = max(1, int(np.count_nonzero(design)))
    band = np.atleast_1d(np.asarray(band_omegas, dtype=float))
    vf_target = float(opt.volume_fraction) if vf is None else float(vf)
    rho = np.where(mesh.void_mask, opt.min_density, vf_target)

    x = rho[design].astype(float).copy()
    xmin = np.full(n_design, opt.min_density)
    xmax = np.ones(n_design)
    state = MMAState()

    compliance_history: list[float] = []
    volume_history: list[float] = []
    peak_history: list[float] = []
    converged = False
    for _ in range(max_iter):
        rho[design] = x
        res = solve_linear_elastic(config, mesh, rho)
        active = np.where(mesh.void_mask, opt.min_density, rho)
        dscale = opt.penalty * np.where(mesh.void_mask, 0.0, active ** (opt.penalty - 1.0)) * (1.0 - opt.min_density)
        dc = -dscale * res.element_strain_energy
        sens_c = density_filter(mesh, rho, dc, opt.filter_radius, opt.min_density)
        peak, dpeak, _ = target_band_peak_sensitivity(config, mesh, rho, band, alpha, beta, p, mass_type)
        sens_p = density_filter(mesh, rho, dpeak, opt.filter_radius, opt.min_density)

        compliance_history.append(res.compliance)
        volume_history.append(float(np.mean(x)))
        peak_history.append(peak)

        df0dx = sens_c[design]
        fval = np.array([peak / peak_limit - 1.0, float(np.mean(x) - vf_target)])
        dfdx = np.vstack([sens_p[design] / peak_limit, np.full(n_design, 1.0 / n_design)])
        x_new, _lmbda = mma_step(x, df0dx, fval, dfdx, xmin, xmax, state)
        change = float(np.max(np.abs(x_new - x)))
        x = x_new
        if change < change_tol:
            converged = True
            break

    rho[design] = x
    res = solve_linear_elastic(config, mesh, rho)
    peak_f, _, _ = target_band_peak_sensitivity(config, mesh, rho, band, alpha, beta, p, mass_type)
    compliance_history.append(res.compliance)
    volume_history.append(float(np.mean(x)))
    peak_history.append(peak_f)
    return PeakConstrainedTOResult(
        densities=rho,
        compliance_history=compliance_history,
        volume_history=volume_history,
        peak_history=peak_history,
        peak_limit=float(peak_limit),
        band_omegas=band,
        converged=converged,
    )


@dataclass
class AdaptivePeakConstrainedTOResult:
    """Output of :func:`adaptive_peak_constrained_mma` (Wave BBBB, D083)."""

    densities: np.ndarray
    compliance_history: list[float]
    volume_history: list[float]
    peak_history: list[float]  # in-loop tracked-band peak each iteration
    peak_omega_history: list[float]  # tracked resonance location each iteration
    band_history: list[np.ndarray]  # the re-gridded band used each iteration
    peak_limit: float
    omega_range: tuple[float, float]
    converged: bool


def half_power_relative_bandwidth(omega: float, alpha: float = 0.0, beta: float = 2e-6) -> float:
    """Half-power **fractional** bandwidth ``Δω/ω_n = 2ζ(ω_n) = α/ω_n + β·ω_n`` of a
    Rayleigh-damped (``C = αM + βK``) resonance at ``ω`` (Wave BBBBB, D091).

    From ``ζ(ω_n) = ½(α/ω_n + β·ω_n)`` (see :func:`rayleigh_modal_damping_ratio`) and
    the half-power relation ``Δω ≈ 2ζ·ω_n``. A sharp (lightly-damped) resonance has a
    small fractional bandwidth; a broad one a large bandwidth. Used to size the
    in-loop constraint band to the *current* resonance's sharpness instead of a fixed
    fraction. Raises ``SolverError`` for ``ω ≤ 0`` or negative damping.
    """
    if omega <= 0.0:
        raise SolverError("half_power_nonpositive_omega")
    if alpha < 0.0 or beta < 0.0:
        raise SolverError("rayleigh_damping_negative_coefficient")
    return float(alpha / omega + beta * omega)


def adaptive_peak_constrained_mma(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    peak_limit: float,
    omega_lo: float,
    omega_hi: float,
    alpha: float = 0.0,
    beta: float = 2e-6,
    vf: float | None = None,
    max_iter: int = 40,
    change_tol: float = 1e-3,
    p: float = 12.0,
    mass_type: str = "consistent",
    n_init: int = 7,
    n_refine: int = 14,
    band_rel_width: float = 0.05,
    n_band: int = 5,
    bandwidth_adaptive: bool = False,
) -> AdaptivePeakConstrainedTOResult:
    """Minimise static compliance subject to an **in-loop adaptively re-gridded**
    forced-response peak constraint over ``[omega_lo, omega_hi]`` and a volume
    fraction, via MMA (Wave BBBB, D083).

    D075's :func:`peak_constrained_mma` pins the constraint band to a **fixed**
    ``band_omegas`` chosen up front. But the natural frequencies move as material
    redistributes — on the smoke cantilever the fundamental drifts ≈ +100 % over an
    optimisation — so a band fixed at the *initial* resonance slides off-resonance
    and the p-norm constraint stops measuring the true peak (it under-reports by
    ~90 %). D075's recorded reopening criterion named **in-loop adaptive
    re-gridding** to fix exactly this.

    Each iteration this driver re-runs :func:`adaptive_band_sample` over the full
    search range to **re-locate the moving resonance**, then rebuilds the
    constraint band as ``ω_peak · [1−w, 1+w]`` (``n_band`` points, ``w =
    band_rel_width``, clipped to the search range). The peak constraint therefore
    tracks the resonance throughout, keeping its measurement faithful to the true
    band maximum. The two inequalities for :func:`core.mma.mma_step` are the proven
    D066/D075 pair

        ``g₁(x) = J_peak(x) / J_lim − 1 ≤ 0``   (in-band forced-response peak)
        ``g₂(x) = mean(x) − vf ≤ 0``            (volume)

    minimising the SIMP static compliance (``dc/dρ_e = −dscale_e·uₑᵀkₑuₑ``). The
    light default ``beta = 2e-6`` keeps the resonance **sharp enough to be worth
    tracking** (a heavily-damped response has no peak to chase, and the fixed and
    adaptive bands coincide); it is still damped enough for a finite, stable solve
    (cf. Wave TTT's undamped singularity). Both gradients are density-filtered.

    With ``bandwidth_adaptive=True`` (Wave BBBBB, D091) the window half-width is set
    each iteration from the resonance's **half-power fractional bandwidth**
    (:func:`half_power_relative_bandwidth`, ``= α/ω_peak + β·ω_peak``) instead of the
    fixed ``band_rel_width`` — robust across resonance sharpness, where a single
    fixed fraction is accurate only near one damping level.

    Returns an :class:`AdaptivePeakConstrainedTOResult` whose ``peak_omega_history``
    records the tracked resonance each iteration — the evidence that re-gridding is
    doing non-trivial work.
    """
    from structure_optimizer.core.fem2d import solve_linear_elastic
    from structure_optimizer.core.mma import MMAState, mma_step

    if not (peak_limit > 0.0):
        raise SolverError("peak_constrained_nonpositive_limit")
    if not (omega_hi > omega_lo):
        raise SolverError("adaptive_band_invalid_range")
    if n_band < 1:
        raise SolverError("adaptive_peak_band_too_few")
    opt = config.optimization
    design = mesh.design_mask
    n_design = max(1, int(np.count_nonzero(design)))
    vf_target = float(opt.volume_fraction) if vf is None else float(vf)
    rho = np.where(mesh.void_mask, opt.min_density, vf_target)

    x = rho[design].astype(float).copy()
    xmin = np.full(n_design, opt.min_density)
    xmax = np.ones(n_design)
    state = MMAState()

    compliance_history: list[float] = []
    volume_history: list[float] = []
    peak_history: list[float] = []
    peak_omega_history: list[float] = []
    band_history: list[np.ndarray] = []
    converged = False

    def _regrid(r: np.ndarray) -> tuple[float, np.ndarray]:
        ab = adaptive_band_sample(
            config, mesh, r, omega_lo, omega_hi, n_init, n_refine, alpha, beta, mass_type
        )
        # Wave BBBBB (D091): size the window to the resonance's half-power bandwidth
        # when bandwidth_adaptive, instead of a fixed fractional width — a sharp
        # resonance gets a narrow band, a broad one a wide band.
        width = (
            half_power_relative_bandwidth(ab.peak_omega, alpha, beta)
            if bandwidth_adaptive
            else band_rel_width
        )
        spread = np.linspace(1.0 - width, 1.0 + width, n_band)
        band = np.clip(ab.peak_omega * spread, omega_lo, omega_hi)
        return ab.peak_omega, band

    for _ in range(max_iter):
        rho[design] = x
        res = solve_linear_elastic(config, mesh, rho)
        active = np.where(mesh.void_mask, opt.min_density, rho)
        dscale = opt.penalty * np.where(mesh.void_mask, 0.0, active ** (opt.penalty - 1.0)) * (1.0 - opt.min_density)
        dc = -dscale * res.element_strain_energy
        sens_c = density_filter(mesh, rho, dc, opt.filter_radius, opt.min_density)

        peak_omega, band = _regrid(rho)
        peak, dpeak, _ = target_band_peak_sensitivity(config, mesh, rho, band, alpha, beta, p, mass_type)
        sens_p = density_filter(mesh, rho, dpeak, opt.filter_radius, opt.min_density)

        compliance_history.append(res.compliance)
        volume_history.append(float(np.mean(x)))
        peak_history.append(peak)
        peak_omega_history.append(peak_omega)
        band_history.append(band)

        df0dx = sens_c[design]
        fval = np.array([peak / peak_limit - 1.0, float(np.mean(x) - vf_target)])
        dfdx = np.vstack([sens_p[design] / peak_limit, np.full(n_design, 1.0 / n_design)])
        x_new, _lmbda = mma_step(x, df0dx, fval, dfdx, xmin, xmax, state)
        change = float(np.max(np.abs(x_new - x)))
        x = x_new
        if change < change_tol:
            converged = True
            break

    rho[design] = x
    res = solve_linear_elastic(config, mesh, rho)
    peak_omega_f, band_f = _regrid(rho)
    peak_f, _, _ = target_band_peak_sensitivity(config, mesh, rho, band_f, alpha, beta, p, mass_type)
    compliance_history.append(res.compliance)
    volume_history.append(float(np.mean(x)))
    peak_history.append(peak_f)
    peak_omega_history.append(peak_omega_f)
    band_history.append(band_f)
    return AdaptivePeakConstrainedTOResult(
        densities=rho,
        compliance_history=compliance_history,
        volume_history=volume_history,
        peak_history=peak_history,
        peak_omega_history=peak_omega_history,
        band_history=band_history,
        peak_limit=float(peak_limit),
        omega_range=(float(omega_lo), float(omega_hi)),
        converged=converged,
    )


@dataclass
class PeakBindingTOResult:
    """Output of :func:`peak_binding_mma` (Wave GGGGGG, v14, D104)."""

    densities: np.ndarray
    dyn_compliance_history: list[float]  # J(ω_op) each iteration (the objective)
    flanking_peak_history: list[float]  # in-loop flanking-band peak each iteration
    flanking_omega_history: list[float]  # tracked flanking resonance each iteration
    band_history: list[np.ndarray]  # the re-gridded flanking band each iteration
    omega_op: float
    peak_limit: float
    flanking_range: tuple[float, float]
    converged: bool


def peak_binding_mma(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    omega_op: float,
    flanking_lo: float,
    flanking_hi: float,
    peak_limit: float,
    alpha: float = 0.0,
    beta: float = 2e-6,
    vf: float | None = None,
    max_iter: int = 40,
    change_tol: float = 1e-3,
    p: float = 12.0,
    mass_type: str = "consistent",
    n_init: int = 7,
    n_refine: int = 14,
    band_rel_width: float = 0.05,
    n_band: int = 5,
    regrid: bool = True,
) -> PeakBindingTOResult:
    """Minimise **dynamic** compliance ``J(ω_op) = |fᵀû(ω_op)|²`` at a fixed operating
    frequency in an *anti-resonance valley*, subject to an in-loop re-gridded **flanking
    resonance** peak constraint over ``[flanking_lo, flanking_hi]`` plus a volume
    fraction, via MMA (Wave GGGGGG, v14, D104). **Closes D091's twice-deferred
    peak-*binding* criterion.**

    D091 placed ``ω_op`` near the fundamental ``ω₁`` and found minimising the response
    there *lowered* the whole transfer function — objective and constraint **aligned**,
    so the constraint never bound and "in-loop changes the design" could not be shown.
    The missing ingredient is **placing ω_op in the valley between two modes**: deepening
    the anti-resonance at ``ω_op`` (pole–zero interlacing) then *raises* the neighbouring
    (flanking) resonance, so the flanking-peak constraint genuinely **conflicts** with the
    objective. A probe confirms minimising ``J(ω_op)`` raises the flanking band peak by
    ~16–55 % (fine/coarse mesh) instead of lowering it.

    The two MMA inequalities (the proven D066/D075 pair) are

        ``g₁(x) = J_flank(x) / J_lim − 1 ≤ 0``   (flanking in-band peak, p-norm)
        ``g₂(x) = mean(x) − vf ≤ 0``             (volume)

    minimising the **dynamic** objective ``J(ω_op)`` (sensitivity from
    :func:`dynamic_compliance_sensitivity`, scaled by its initial value for MMA
    conditioning). With ``regrid=True`` the flanking band is re-located each iteration by
    :func:`adaptive_band_sample` over ``[flanking_lo, flanking_hi]`` (tracking the moving
    flanking resonance); ``regrid=False`` freezes it at the **initial** flanking location
    (stale), so the two settings yield different designs — the evidence that in-loop
    re-gridding changes the design, not just the measurement. All gradients are
    density-filtered. Returns a :class:`PeakBindingTOResult`.
    """
    from structure_optimizer.core.fem2d import solve_linear_elastic  # noqa: F401 (parity w/ siblings)
    from structure_optimizer.core.mma import MMAState, mma_step

    if not (omega_op > 0.0):
        raise SolverError("peak_binding_nonpositive_omega")
    if not (peak_limit > 0.0):
        raise SolverError("peak_constrained_nonpositive_limit")
    if not (flanking_hi > flanking_lo):
        raise SolverError("adaptive_band_invalid_range")
    if n_band < 1:
        raise SolverError("adaptive_peak_band_too_few")
    opt = config.optimization
    design = mesh.design_mask
    n_design = max(1, int(np.count_nonzero(design)))
    vf_target = float(opt.volume_fraction) if vf is None else float(vf)
    rho = np.where(mesh.void_mask, opt.min_density, vf_target)

    x = rho[design].astype(float).copy()
    xmin = np.full(n_design, opt.min_density)
    xmax = np.ones(n_design)
    state = MMAState()

    def _flanking_band(r: np.ndarray) -> tuple[float, np.ndarray]:
        ab = adaptive_band_sample(
            config, mesh, r, flanking_lo, flanking_hi, n_init, n_refine, alpha, beta, mass_type
        )
        spread = np.linspace(1.0 - band_rel_width, 1.0 + band_rel_width, n_band)
        return ab.peak_omega, np.clip(ab.peak_omega * spread, flanking_lo, flanking_hi)

    # Stale band (regrid=False): frozen at the INITIAL flanking resonance.
    _, frozen_band = _flanking_band(rho)
    # Objective scale for MMA conditioning (constant ⟹ same optimum).
    j_scale = max(dynamic_compliance_sensitivity(config, mesh, rho, omega_op, alpha, beta, mass_type).objective, 1e-30)

    dyn_history: list[float] = []
    flanking_peak_history: list[float] = []
    flanking_omega_history: list[float] = []
    band_history: list[np.ndarray] = []
    converged = False

    for _ in range(max_iter):
        rho[design] = x
        rj = dynamic_compliance_sensitivity(config, mesh, rho, omega_op, alpha, beta, mass_type)
        sens_j = density_filter(mesh, rho, rj.sensitivity, opt.filter_radius, opt.min_density)

        if regrid:
            flank_omega, band = _flanking_band(rho)
        else:
            flank_omega, band = float(0.5 * (frozen_band[0] + frozen_band[-1])), frozen_band
        peak, dpeak, _ = target_band_peak_sensitivity(config, mesh, rho, band, alpha, beta, p, mass_type)
        sens_p = density_filter(mesh, rho, dpeak, opt.filter_radius, opt.min_density)

        dyn_history.append(rj.objective)
        flanking_peak_history.append(peak)
        flanking_omega_history.append(flank_omega)
        band_history.append(band)

        df0dx = sens_j[design] / j_scale
        fval = np.array([peak / peak_limit - 1.0, float(np.mean(x) - vf_target)])
        dfdx = np.vstack([sens_p[design] / peak_limit, np.full(n_design, 1.0 / n_design)])
        x_new, _lmbda = mma_step(x, df0dx, fval, dfdx, xmin, xmax, state)
        change = float(np.max(np.abs(x_new - x)))
        x = x_new
        if change < change_tol:
            converged = True
            break

    rho[design] = x
    rj_f = dynamic_compliance_sensitivity(config, mesh, rho, omega_op, alpha, beta, mass_type)
    if regrid:
        flank_omega_f, band_f = _flanking_band(rho)
    else:
        flank_omega_f, band_f = float(0.5 * (frozen_band[0] + frozen_band[-1])), frozen_band
    peak_f, _, _ = target_band_peak_sensitivity(config, mesh, rho, band_f, alpha, beta, p, mass_type)
    dyn_history.append(rj_f.objective)
    flanking_peak_history.append(peak_f)
    flanking_omega_history.append(flank_omega_f)
    band_history.append(band_f)
    return PeakBindingTOResult(
        densities=rho,
        dyn_compliance_history=dyn_history,
        flanking_peak_history=flanking_peak_history,
        flanking_omega_history=flanking_omega_history,
        band_history=band_history,
        omega_op=float(omega_op),
        peak_limit=float(peak_limit),
        flanking_range=(float(flanking_lo), float(flanking_hi)),
        converged=converged,
    )


@dataclass
class PeakBindingKKTStatus:
    """KKT active-set status of a :func:`peak_binding_mma` result (Wave DDDDDDD, v15, D109)."""

    active: bool  # constraint active (true flank ≈ limit, |g₁| ≤ tol)
    flank_peak: float  # dense-sweep true flanking peak of the design
    peak_limit: float
    constraint_value: float  # g₁ = flank_peak / peak_limit − 1 (≈0 when active)
    j_objective: float  # J(ω_op) at the design
    active_multiplier: float | None  # J/J_reference − 1 (>0 ⟺ objective sacrificed) if a reference is given


def kkt_binding_status(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    result: PeakBindingTOResult,
    alpha: float = 0.0,
    beta: float = 2e-6,
    mass_type: str = "consistent",
    n_dense: int = 120,
    tol: float = 0.1,
    j_reference: float | None = None,
) -> PeakBindingKKTStatus:
    """Diagnose whether the flanking-peak constraint is **strictly KKT-binding** in a
    :func:`peak_binding_mma` result (Wave DDDDDDD, v15, D109) — **closes D104's deferral**.

    Recomputes the design's true flanking peak by a dense sweep over the flanking range,
    forms the constraint value ``g₁ = flank/limit − 1`` and flags the constraint
    **active** when ``|g₁| ≤ tol`` (the flank sits at the limit). D104 found the
    constraint *inactive* (a "basin selector": at loose limits the J-optimum basin already
    has a low flank, so the flank stays well below the limit and J is not sacrificed). A
    **tight enough limit** (empirically ≲ 0.1·initial flank) drives the flank below that
    basin's natural level, so ``g₁ → 0`` (active) **and** ``J(ω_op)`` is forced up — a
    strictly binding constraint with a positive KKT multiplier (a genuine objective
    trade-off, not just a design change).

    With ``j_reference`` (the unconstrained min ``J(ω_op)``) the ``active_multiplier``
    field reports the relative objective sacrifice ``J/J_ref − 1`` — strictly positive iff
    the constraint genuinely costs the objective (the KKT multiplier is > 0).
    """
    lo, hi = result.flanking_range
    rho = result.densities
    flank = max(
        _dynamic_compliance_objective(config, mesh, rho, float(w), alpha, beta, mass_type)
        for w in np.linspace(lo, hi, n_dense)
    )
    g1 = flank / result.peak_limit - 1.0
    j_obj = result.dyn_compliance_history[-1] if result.dyn_compliance_history else float("nan")
    mult = (j_obj / j_reference - 1.0) if (j_reference is not None and j_reference > 0.0) else None
    return PeakBindingKKTStatus(
        active=bool(abs(g1) <= tol),
        flank_peak=float(flank),
        peak_limit=float(result.peak_limit),
        constraint_value=float(g1),
        j_objective=float(j_obj),
        active_multiplier=(float(mult) if mult is not None else None),
    )
