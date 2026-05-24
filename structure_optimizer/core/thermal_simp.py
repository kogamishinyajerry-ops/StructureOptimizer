"""Wave Y: thermal-compliance SIMP driver (v5 multi-physics).

Minimises thermal compliance ``T^T · K(ρ) · T`` subject to a volume-fraction
constraint, where K is the conductivity matrix from `core.thermal`. The
sensitivity is symmetric to elastic compliance:

    dC/dρ_e = -p · ρ_e^(p-1) · (1 - ρ_min) · T_e^T · Ke · T_e

Classic optimality-criteria update + Bendsøe density filter are reused
verbatim from `core.simp` / `core.filtering`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.filtering import density_filter
from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.core.simp import _apply_density_masks, _optimality_criteria_update
from structure_optimizer.core.thermal import ThermalResult, solve_thermal


@dataclass
class ThermalIterationMetric:
    iteration: int
    thermal_compliance: float
    max_temperature: float
    volume_fraction: float
    max_density_change: float


@dataclass
class ThermalOptimizationResult:
    densities: np.ndarray
    final_result: ThermalResult
    metrics: list[ThermalIterationMetric]
    converged: bool
    mesh_shape: tuple[int, int]


def _deep_merge(dst: dict, src: dict) -> dict:
    for k, v in src.items():
        if k in dst and isinstance(dst[k], dict) and isinstance(v, dict):
            dst[k] = _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def load_thermal_benchmark(
    name: str, preset: str | None = None
) -> tuple[BenchmarkConfig, float, list[dict[str, Any]], list[dict[str, Any]]]:
    """Load a benchmark + extract its ``thermal`` block (conductivity, sources, BCs).

    The ``thermal`` block lives in the raw JSON and is *not* parsed by
    ``parse_config`` (preserving v1-v4 schema). This helper reads the raw
    JSON, applies the preset, and returns the typed config plus the
    thermal-specific extras.

    Returns:
        (config, conductivity, heat_sources, thermal_bcs)
    """
    from structure_optimizer.benchmarks.registry import config_path
    from structure_optimizer.core.config import parse_config, validate_config

    raw = json.loads(Path(config_path(name)).read_text())
    presets = raw.pop("presets", {})
    if preset:
        if preset not in presets:
            raise ValueError(f"Unknown preset '{preset}' for benchmark '{name}'")
        raw = _deep_merge(raw, presets[preset])
    thermal_block = raw.pop("thermal", {})
    if not thermal_block:
        raise ValueError(f"benchmark '{name}' has no 'thermal' block")
    config = parse_config(raw, source_path=str(config_path(name)))
    validate_config(config)
    return (
        config,
        float(thermal_block.get("conductivity", 1.0)),
        list(thermal_block.get("heat_sources", [])),
        list(thermal_block.get("thermal_bcs", [])),
    )


def _default_initial_density(config: BenchmarkConfig, mesh: StructuredMesh) -> np.ndarray:
    """Mirror of `simp._default_initial_density` for thermal optimisation."""
    rho0 = np.full(mesh.elements.shape[0], config.optimization.volume_fraction)
    return _apply_density_masks(config, mesh, rho0)


def run_thermal_simp(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    conductivity: float,
    heat_sources: list[dict],
    thermal_bcs: list[dict],
) -> ThermalOptimizationResult:
    """SIMP min-thermal-compliance driver.

    Args:
        config:        BenchmarkConfig (uses optimization.* + thickness)
        mesh:          structured quad mesh
        conductivity:  scalar material thermal conductivity
        heat_sources:  list of ``{"selector", "q"}`` records
        thermal_bcs:   list of ``{"selector", "temperature"}`` records

    Returns:
        ThermalOptimizationResult with density history + iteration metrics
    """
    opt = config.optimization
    densities = _default_initial_density(config, mesh)
    metrics: list[ThermalIterationMetric] = []
    converged = False
    prev = densities.copy()

    for it in range(opt.max_iterations):
        result = solve_thermal(
            config,
            mesh,
            densities,
            conductivity=conductivity,
            heat_sources=heat_sources,
            thermal_bcs=thermal_bcs,
        )

        active_density = np.where(mesh.void_mask, opt.min_density, densities)
        p = opt.penalty
        # SIMP sensitivity: dC/dρ_e = -p · ρ_e^(p-1) · (1 - ρ_min) · elem_energy
        sens = -p * np.power(active_density, p - 1.0) * (1.0 - opt.min_density) * result.element_thermal_energy

        # Bendsøe density filter (sensitivity-based) — share with elastic path
        sens = density_filter(mesh, densities, sens, opt.filter_radius, opt.min_density)

        new = _optimality_criteria_update(config, mesh, densities, sens)
        new = _apply_density_masks(config, mesh, new)

        change = float(np.max(np.abs(new - prev)))
        vol = float(np.mean(new))
        metrics.append(
            ThermalIterationMetric(
                iteration=it,
                thermal_compliance=result.thermal_compliance,
                max_temperature=result.max_temperature,
                volume_fraction=vol,
                max_density_change=change,
            )
        )

        prev = densities.copy()
        densities = new

        if it >= opt.min_iterations and change < opt.change_tolerance:
            converged = True
            break

    final = solve_thermal(
        config,
        mesh,
        densities,
        conductivity=conductivity,
        heat_sources=heat_sources,
        thermal_bcs=thermal_bcs,
    )

    return ThermalOptimizationResult(
        densities=densities,
        final_result=final,
        metrics=metrics,
        converged=converged,
        mesh_shape=(mesh.nelx, mesh.nely),
    )


def anisotropic_thermal_sensitivity(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    conductivity_tensor: np.ndarray | None = None,
    heat_sources: list[dict[str, Any]] | None = None,
    thermal_bcs: list[dict[str, Any]] | None = None,
    conductivity_tensor_field: np.ndarray | None = None,
) -> np.ndarray:
    """Anisotropic thermal SIMP compliance sensitivity dC/dρ_e (Wave NN, D043).

    The thermal problem K(ρ)·T = q is self-adjoint, so for thermal compliance
    C = qᵀT = TᵀK T the sensitivity is

        dC/dρ_e = -p · ρ_e^(p-1) · (1 - ρ_min) · (Tₑᵀ ke_e Tₑ),

    identical in form to the scalar case (``run_thermal_simp``) — the only change
    is that ``ke_e`` (and hence ``element_thermal_energy``) carries the
    anisotropic tensor / per-element field. Pass either a global
    ``conductivity_tensor`` or a per-element ``conductivity_tensor_field``.
    """
    densities = np.asarray(densities, dtype=float).reshape(-1)
    result = solve_thermal(
        config, mesh, densities, conductivity=1.0,
        heat_sources=heat_sources, thermal_bcs=thermal_bcs,
        conductivity_tensor=conductivity_tensor,
        conductivity_tensor_field=conductivity_tensor_field,
    )
    opt = config.optimization
    active = np.where(mesh.void_mask, opt.min_density, densities)
    p = opt.penalty
    return -p * np.power(active, p - 1.0) * (1.0 - opt.min_density) * result.element_thermal_energy


# --- Wave YY (v8, D054): fibre-steering thermal TO (orientation as design var) -
#
# D043 delivered the per-element anisotropic field + the density sensitivity, but
# the orientation field itself was fixed. Its reopening criterion named the
# upgrade: optimise the orientation field (fibre steering). The thermal problem
# is self-adjoint, so for compliance C = TᵀK(θ)T the orientation sensitivity is
#     dC/dθ_e = -scale_e · Tₑᵀ (∂ke_e/∂θ_e) Tₑ,
# where ke_e is linear in the conductivity tensor k(θ) = R(θ)k₀R(θ)ᵀ, so
# ∂ke_e/∂θ_e is the same element quadrature applied to dk/dθ.


def _thermal_elem_from_tensor(k2x2: np.ndarray, thickness: float) -> np.ndarray:
    """Element conductivity matrix ∫ Bᵀ k B for an arbitrary (possibly indefinite)
    2×2 tensor — same quadrature as ``element_thermal_conductivity_tensor`` but
    without the positive-definite check, so it accepts derivative tensors dk/dθ."""
    from structure_optimizer.core.thermal import (
        _GAUSS_PTS,
        _NODE_ETA,
        _NODE_XI,
        _UNIT_SQUARE,
    )

    ke = np.zeros((4, 4))
    for xi, eta in _GAUSS_PTS:
        dn_dxi = 0.25 * _NODE_XI * (1.0 + _NODE_ETA * eta)
        dn_deta = 0.25 * _NODE_ETA * (1.0 + _NODE_XI * xi)
        dn_nat = np.column_stack([dn_dxi, dn_deta])
        jac = dn_nat.T @ _UNIT_SQUARE
        detj = np.linalg.det(jac)
        dn_dx = dn_nat @ np.linalg.inv(jac).T
        ke += dn_dx @ k2x2 @ dn_dx.T * detj * thickness
    return ke


def _dk_dtheta(kxx: float, kyy: float, kxy: float, theta: float) -> np.ndarray:
    """d/dθ of R(θ)·k₀·R(θ)ᵀ where R is the 2-D rotation by θ."""
    k0 = np.array([[kxx, kxy], [kxy, kyy]], dtype=float)
    c, s = np.cos(theta), np.sin(theta)
    rot = np.array([[c, -s], [s, c]])
    drot = np.array([[-s, -c], [c, -s]])
    return drot @ k0 @ rot.T + rot @ k0 @ drot.T


@dataclass
class FibreSteeringResult:
    """Output of fibre-steering thermal TO (Wave YY)."""

    angles: np.ndarray
    compliance_history: list[float]
    kxx: float
    kyy: float


def orientation_sensitivity(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    angles: np.ndarray,
    kxx: float,
    kyy: float,
    kxy: float = 0.0,
    heat_sources: list[dict[str, Any]] | None = None,
    thermal_bcs: list[dict[str, Any]] | None = None,
) -> np.ndarray:
    """Thermal-compliance sensitivity w.r.t. each element's fibre angle θ_e
    (Wave YY, D054): dC/dθ_e = -scale_e · Tₑᵀ (∂ke_e/∂θ_e) Tₑ."""
    from structure_optimizer.core.thermal import orientation_field_to_tensors

    densities = np.asarray(densities, dtype=float).reshape(-1)
    angles = np.asarray(angles, dtype=float).reshape(-1)
    field = orientation_field_to_tensors(kxx, kyy, angles, kxy)
    result = solve_thermal(
        config, mesh, densities, conductivity=1.0,
        heat_sources=heat_sources, thermal_bcs=thermal_bcs,
        conductivity_tensor_field=field,
    )
    temps = result.temperatures
    opt = config.optimization
    active = np.where(mesh.void_mask, opt.min_density, densities)
    scale = opt.min_density + (active**opt.penalty) * (1.0 - opt.min_density)
    dC = np.zeros(mesh.elements.shape[0])
    for e, nodes in enumerate(mesh.elements):
        te = temps[nodes]
        dke = _thermal_elem_from_tensor(_dk_dtheta(kxx, kyy, kxy, float(angles[e])), config.thickness)
        dC[e] = -scale[e] * float(te @ dke @ te)
    return dC


def fibre_steering_thermal_to(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    kxx: float,
    kyy: float,
    kxy: float = 0.0,
    n_steps: int = 25,
    step: float = 0.3,
    init_angles: np.ndarray | None = None,
    heat_sources: list[dict[str, Any]] | None = None,
    thermal_bcs: list[dict[str, Any]] | None = None,
) -> FibreSteeringResult:
    """Steepest-descent optimisation of the per-element fibre angle to minimise
    thermal compliance (Wave YY, D054), at fixed densities. Angles are periodic
    (no box constraint). Records compliance each step.
    """
    from structure_optimizer.core.thermal import orientation_field_to_tensors

    densities = np.asarray(densities, dtype=float).reshape(-1)
    n_elem = mesh.elements.shape[0]
    angles = np.zeros(n_elem) if init_angles is None else np.asarray(init_angles, dtype=float).reshape(-1).copy()
    history: list[float] = []
    for _ in range(n_steps + 1):
        field = orientation_field_to_tensors(kxx, kyy, angles, kxy)
        r = solve_thermal(config, mesh, densities, conductivity=1.0,
                          heat_sources=heat_sources, thermal_bcs=thermal_bcs,
                          conductivity_tensor_field=field)
        history.append(float(r.thermal_compliance))
        if len(history) > n_steps:
            break
        g = orientation_sensitivity(config, mesh, densities, angles, kxx, kyy, kxy, heat_sources, thermal_bcs)
        gmax = float(np.max(np.abs(g)))
        if gmax <= 0.0:
            break
        angles = angles - step * (g / gmax)
    return FibreSteeringResult(angles=angles, compliance_history=history, kxx=float(kxx), kyy=float(kyy))


# --- Wave GGG (v9, D062): coupled density + orientation thermal TO -----------
#
# D054 (fibre steering) optimised the orientation field θ at *fixed* density;
# run_thermal_simp / anisotropic_thermal_sensitivity optimise density at fixed θ.
# D054's reopening criterion named the coupling: optimise BOTH by alternating
# minimisation — a density OC step (fixed θ) then an orientation steepest-descent
# step (fixed ρ), cycling until convergence. Each sub-step lowers the (self-
# adjoint) thermal compliance, so the alternation is monotone and reaches a design
# at least as good as optimising either field alone.


@dataclass
class CoupledThermalResult:
    """Output of coupled density + orientation thermal TO (Wave GGG)."""

    densities: np.ndarray
    angles: np.ndarray
    compliance_history: list[float]
    converged: bool


def coupled_density_orientation_to(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    kxx: float,
    kyy: float,
    kxy: float = 0.0,
    n_outer: int = 8,
    n_orient_steps: int = 8,
    orient_step: float = 0.3,
    init_angles: np.ndarray | None = None,
    heat_sources: list[dict[str, Any]] | None = None,
    thermal_bcs: list[dict[str, Any]] | None = None,
    change_tol: float = 1e-3,
) -> CoupledThermalResult:
    """Coupled density + fibre-orientation thermal TO by alternating minimisation
    (Wave GGG, D062).

    Each outer cycle: (1) a density OC step (D043 anisotropic sensitivity, Sigmund
    filter, volume-constrained OC) at the current orientation field; (2) up to
    ``n_orient_steps`` orientation steepest-descent steps (D054) at the updated
    density. Records the thermal compliance after each full cycle; stops on
    ``max|Δρ| < change_tol`` or ``n_outer``. With ``n_orient_steps=0`` it reduces
    to a pure (anisotropic) density TO; with an isotropic base tensor (kxx==kyy)
    the orientation step is a no-op (dC/dθ ≡ 0)."""
    from structure_optimizer.core.thermal import orientation_field_to_tensors

    opt = config.optimization
    n_elem = mesh.elements.shape[0]
    rho = _default_initial_density(config, mesh)
    angles = np.zeros(n_elem) if init_angles is None else np.asarray(init_angles, dtype=float).reshape(-1).copy()
    history: list[float] = []
    converged = False

    for _ in range(n_outer):
        # (1) density step at fixed orientation
        field = orientation_field_to_tensors(kxx, kyy, angles, kxy)
        sens = anisotropic_thermal_sensitivity(
            config, mesh, rho, conductivity_tensor_field=field,
            heat_sources=heat_sources, thermal_bcs=thermal_bcs,
        )
        sens = density_filter(mesh, rho, sens, opt.filter_radius, opt.min_density)
        prev_rho = rho.copy()
        rho = _optimality_criteria_update(config, mesh, rho, sens)
        rho = _apply_density_masks(config, mesh, rho)

        # (2) orientation steepest descent at fixed density
        for _s in range(n_orient_steps):
            g = orientation_sensitivity(config, mesh, rho, angles, kxx, kyy, kxy, heat_sources, thermal_bcs)
            gmax = float(np.max(np.abs(g)))
            if gmax <= 0.0:
                break
            angles = angles - orient_step * (g / gmax)

        field = orientation_field_to_tensors(kxx, kyy, angles, kxy)
        c = solve_thermal(
            config, mesh, rho, conductivity=1.0,
            heat_sources=heat_sources, thermal_bcs=thermal_bcs,
            conductivity_tensor_field=field,
        ).thermal_compliance
        history.append(float(c))
        if float(np.max(np.abs(rho - prev_rho))) < change_tol:
            converged = True
            break

    return CoupledThermalResult(densities=rho, angles=angles, compliance_history=history, converged=converged)


@dataclass
class SimultaneousCoupledResult:
    """Output of simultaneous (ρ,θ) MMA coupled thermal TO (Wave OOO, D070)."""

    densities: np.ndarray
    angles: np.ndarray
    compliance_history: list[float]
    volume_history: list[float]
    converged: bool


def simultaneous_density_orientation_mma(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    kxx: float,
    kyy: float,
    kxy: float = 0.0,
    max_iter: int = 40,
    theta_bound: float = np.pi / 2.0,
    init_angles: np.ndarray | None = None,
    heat_sources: list[dict[str, Any]] | None = None,
    thermal_bcs: list[dict[str, Any]] | None = None,
    change_tol: float = 1e-3,
) -> SimultaneousCoupledResult:
    """Coupled density + fibre-orientation thermal TO by **simultaneous** MMA over
    the stacked design ``[ρ_design ; θ_design]`` (Wave OOO, D070).

    D062's reopening criterion: replace the block-coordinate *alternating*
    minimisation of :func:`coupled_density_orientation_to` (density OC step, then
    orientation steepest descent) with a single MMA step that moves ρ and θ
    **together**. The combined objective gradient stacks the two self-adjoint
    sensitivities — ``dC/dρ`` (D043 :func:`anisotropic_thermal_sensitivity`,
    density-filtered) and ``dC/dθ`` (D054 :func:`orientation_sensitivity`) — and the
    only constraint, the volume inequality ``g = mean(ρ) − vf ≤ 0``, acts on the ρ
    block (``∂g/∂θ ≡ 0``). Angles are box-bounded to ``[−θ_bound, θ_bound]`` (the
    conductivity tensor has period π, so ``π/2`` spans all directions).

    Joint stepping escapes the coordinate-wise stalls of alternation, so the final
    compliance is **at least as low** as the block-coordinate result on the same
    problem (verified by test). Stops on ``max|Δx| < change_tol`` or ``max_iter``.
    """
    from structure_optimizer.core.mma import MMAState, mma_step
    from structure_optimizer.core.thermal import orientation_field_to_tensors

    opt = config.optimization
    design = mesh.design_mask
    n_design = max(1, int(np.count_nonzero(design)))
    n_elem = mesh.elements.shape[0]
    vf = float(opt.volume_fraction)

    rho = _default_initial_density(config, mesh)
    angles = np.zeros(n_elem) if init_angles is None else np.asarray(init_angles, dtype=float).reshape(-1).copy()

    x = np.concatenate([rho[design], angles[design]])
    xmin = np.concatenate([np.full(n_design, opt.min_density), np.full(n_design, -theta_bound)])
    xmax = np.concatenate([np.ones(n_design), np.full(n_design, theta_bound)])
    dfdx = np.zeros((1, 2 * n_design))
    dfdx[0, :n_design] = 1.0 / n_design  # ∂(mean ρ)/∂ρ_e; ∂/∂θ ≡ 0
    state = MMAState()

    def _compliance(rho_v: np.ndarray, ang_v: np.ndarray) -> float:
        field = orientation_field_to_tensors(kxx, kyy, ang_v, kxy)
        return float(
            solve_thermal(
                config, mesh, rho_v, conductivity=1.0,
                heat_sources=heat_sources, thermal_bcs=thermal_bcs,
                conductivity_tensor_field=field,
            ).thermal_compliance
        )

    compliance_history: list[float] = []
    volume_history: list[float] = []
    converged = False
    for _ in range(max_iter):
        rho[design] = x[:n_design]
        rho = _apply_density_masks(config, mesh, rho)
        angles[design] = x[n_design:]
        field = orientation_field_to_tensors(kxx, kyy, angles, kxy)
        d_rho = anisotropic_thermal_sensitivity(
            config, mesh, rho, conductivity_tensor_field=field,
            heat_sources=heat_sources, thermal_bcs=thermal_bcs,
        )
        d_rho = density_filter(mesh, rho, d_rho, opt.filter_radius, opt.min_density)
        d_theta = orientation_sensitivity(config, mesh, rho, angles, kxx, kyy, kxy, heat_sources, thermal_bcs)

        compliance_history.append(_compliance(rho, angles))
        volume_history.append(float(np.sum(rho[design]) / n_design))

        df0dx = np.concatenate([d_rho[design], d_theta[design]])
        fval = np.array([float(np.mean(x[:n_design]) - vf)])
        x_new, _lmbda = mma_step(x, df0dx, fval, dfdx, xmin, xmax, state)
        change = float(np.max(np.abs(x_new - x)))
        x = x_new
        if change < change_tol:
            converged = True
            break

    rho[design] = x[:n_design]
    rho = _apply_density_masks(config, mesh, rho)
    angles[design] = x[n_design:]
    compliance_history.append(_compliance(rho, angles))
    volume_history.append(float(np.sum(rho[design]) / n_design))
    return SimultaneousCoupledResult(
        densities=rho,
        angles=angles,
        compliance_history=compliance_history,
        volume_history=volume_history,
        converged=converged,
    )
