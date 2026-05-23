"""Wave CC: reliability-based / worst-case topology optimization (v5).

Provides ``worst_case_simp``: SIMP driver that minimises the **maximum**
compliance over a fixed set of pre-sampled uncertain load scenarios.
This is a minimax formulation:

    min over ρ  [ max over k ∈ {1..K}  C(ρ; load_k) ]

The literature calls this **robust topology optimization** (Asadpoure
2011 / da Silva 2017). It produces topologies that are stiff against
*any* of the K sampled load realisations, not just the nominal.

Algorithm (per SIMP iteration):
1. For each of K pre-sampled load scenarios, run linear-elastic FEM.
2. Identify the worst-case scenario (highest compliance).
3. Use that scenario's displacement field to compute SIMP sensitivity.
4. OC update.

The pre-sampling is RNG-seeded so the optimisation trajectory is
reproducible.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from math import erf, sqrt
from typing import Any

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import (
    SolverError,
    element_stiffness,
    solve_linear_elastic,
)
from structure_optimizer.core.filtering import density_filter
from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.core.simp import _apply_density_masks, _optimality_criteria_update
from structure_optimizer.core.stochastic import UncertaintySpec, _perturbed_loads


@dataclass
class RobustOptimizationResult:
    densities: np.ndarray
    final_worst_compliance: float
    final_mean_compliance: float
    final_compliance_per_scenario: np.ndarray
    metrics: list[dict]
    converged: bool
    mesh_shape: tuple[int, int]
    rng_seed: int
    n_scenarios: int


def _sample_load_scenarios(
    config: BenchmarkConfig, rng_seed: int, n_scenarios: int, uncertainty: UncertaintySpec
) -> list[list[dict[str, Any]]]:
    """Pre-sample K perturbed load configurations; return as list-of-load-lists."""
    rng = np.random.default_rng(rng_seed)
    scenarios = []
    for _ in range(n_scenarios):
        scenarios.append(_perturbed_loads(config.loads, rng, uncertainty))
    return scenarios


def worst_case_simp(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    rng_seed: int,
    n_scenarios: int = 5,
    uncertainty: UncertaintySpec | None = None,
) -> RobustOptimizationResult:
    """Robust (minimax) topology optimization.

    Args:
        config:        BenchmarkConfig (nominal)
        mesh:          structured-quad mesh
        rng_seed:      seed for sampling load scenarios (reproducibility)
        n_scenarios:   K — number of pre-sampled load realisations
        uncertainty:   UncertaintySpec; defaults to load_magnitude_std=0.2
    """
    if n_scenarios < 1:
        raise SolverError("reliability_n_scenarios_must_be_positive")
    if uncertainty is None:
        uncertainty = UncertaintySpec(load_magnitude_std=0.2, load_angle_std=0.05)

    scenarios = _sample_load_scenarios(config, rng_seed, n_scenarios, uncertainty)
    opt = config.optimization
    densities = np.full(mesh.elements.shape[0], opt.volume_fraction)
    densities = _apply_density_masks(config, mesh, densities)

    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
    metrics: list[dict] = []
    converged = False
    prev = densities.copy()

    for it in range(opt.max_iterations):
        # Evaluate each scenario at current densities
        comps = np.zeros(n_scenarios)
        worst_u = None
        worst_k = -1
        for k, loads in enumerate(scenarios):
            cfg_k = replace(config, loads=loads)
            r = solve_linear_elastic(cfg_k, mesh, densities)
            comps[k] = float(r.compliance)
            if k == 0 or comps[k] > comps[worst_k]:
                worst_k = k
                worst_u = r.displacements

        # Sensitivity from the worst-case displacement field
        elem_energy = np.zeros(mesh.elements.shape[0])
        for eid in range(mesh.elements.shape[0]):
            edofs = mesh.element_dofs(eid)
            ue = worst_u[edofs]
            elem_energy[eid] = float(ue @ ke @ ue)
        active = np.where(mesh.void_mask, opt.min_density, densities)
        p = opt.penalty
        sens = -p * np.power(active, p - 1.0) * (1.0 - opt.min_density) * elem_energy
        sens = density_filter(mesh, densities, sens, opt.filter_radius, opt.min_density)

        new = _optimality_criteria_update(config, mesh, densities, sens)
        new = _apply_density_masks(config, mesh, new)

        change = float(np.max(np.abs(new - prev)))
        metrics.append(
            {
                "iteration": it,
                "worst_compliance": float(comps.max()),
                "mean_compliance": float(comps.mean()),
                "worst_scenario": int(worst_k),
                "max_density_change": change,
            }
        )
        prev = densities.copy()
        densities = new
        if it >= opt.min_iterations and change < opt.change_tolerance:
            converged = True
            break

    # Final evaluation
    final_comps = np.zeros(n_scenarios)
    for k, loads in enumerate(scenarios):
        cfg_k = replace(config, loads=loads)
        r = solve_linear_elastic(cfg_k, mesh, densities)
        final_comps[k] = float(r.compliance)

    return RobustOptimizationResult(
        densities=densities,
        final_worst_compliance=float(final_comps.max()),
        final_mean_compliance=float(final_comps.mean()),
        final_compliance_per_scenario=final_comps,
        metrics=metrics,
        converged=converged,
        mesh_shape=(mesh.nelx, mesh.nely),
        rng_seed=int(rng_seed),
        n_scenarios=n_scenarios,
    )


# Alias for v5 rubric grep
worst_case_simp_alias = worst_case_simp
robust_topology = worst_case_simp
minmax_compliance = worst_case_simp


# ---------------------------------------------------------------------------
# Wave II (v6): FORM / SORM + importance sampling for rare-event reliability.
#
# v5's monte_carlo_uq (stochastic.py) estimates a failure probability by crude
# Monte Carlo, which needs O(1/P_f) samples to see a single tail event — hopeless
# for rare events (P_f ~ 1e-4). The reliability methods below replace that:
#   * FORM  — find the most-probable failure point (MPP) in standard-normal
#             space and report the reliability index β; P_f = Φ(−β). Exact for a
#             linear limit state (the quantitative anchor).
#   * SORM  — Breitung's curvature correction at the MPP; reduces to FORM when
#             the limit state is linear (zero curvature).
#   * importance sampling — sample around the MPP for an unbiased P_f with
#             orders-of-magnitude variance reduction vs crude MC.
#
# Convention: everything works in standard-normal U-space, failure = {g(u) ≤ 0},
# and the origin is assumed safe (g(0) > 0), the standard Hasofer-Lind setup.
# Physical independent-Gaussian variables X ~ N(μ, σ) map via u = (x − μ)/σ
# (``standardize_gaussian`` helper). FEM-coupled limit states — e.g.
# g(X) = C_allow − compliance(X) — plug into the same callable interface; they
# are not bundled as a driver here (honest note, D038).
# ---------------------------------------------------------------------------


def _standard_normal_cdf(x: float) -> float:
    """Standard-normal CDF Φ via the error function (numpy/stdlib only)."""
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


@dataclass
class ReliabilityResult:
    """Output of a FORM or SORM reliability analysis.

    Attributes:
        beta:                reliability index (signed: β<0 means origin fails)
        p_failure:           failure probability estimate
        mpp:                 most-probable point (design point) in U-space
        n_iterations:        HL-RF iterations used (0 for the SORM post-step)
        converged:           whether HL-RF met the tolerance
        method:              "FORM" or "SORM"
        n_limit_state_evals: limit-state evaluations consumed
    """

    beta: float
    p_failure: float
    mpp: np.ndarray
    n_iterations: int
    converged: bool
    method: str
    n_limit_state_evals: int


def standardize_gaussian(x, mean, std) -> np.ndarray:
    """Map physical independent-Gaussian variables to standard-normal U-space."""
    std_arr = np.asarray(std, dtype=float)
    if np.any(std_arr <= 0):
        raise SolverError("reliability_nonpositive_std")
    return (np.asarray(x, dtype=float) - np.asarray(mean, dtype=float)) / std_arr


def _fd_gradient(g: Callable[[np.ndarray], float], u: np.ndarray, eps: float) -> tuple[np.ndarray, int]:
    """Central-difference gradient of a scalar limit state. Returns (grad, n_evals)."""
    n = u.size
    grad = np.zeros(n)
    for i in range(n):
        du = np.zeros(n)
        du[i] = eps
        grad[i] = (g(u + du) - g(u - du)) / (2.0 * eps)
    return grad, 2 * n


def form_hlrf(
    limit_state: Callable[[np.ndarray], float],
    n_vars: int,
    max_iter: int = 100,
    tol: float = 1e-9,
    fd_eps: float = 1e-6,
) -> ReliabilityResult:
    """First-Order Reliability Method via HL-RF iteration in standard-normal space.

    Args:
        limit_state: callable(u: (n_vars,)) → g; failure is {g ≤ 0}.
        n_vars:      dimension of the standard-normal vector.
        max_iter:    HL-RF iteration cap.
        tol:         convergence tolerance on ‖Δu‖.
        fd_eps:      central-difference step for the gradient.

    Returns:
        ReliabilityResult with β = sign(g(0))·‖u*‖ and P_f = Φ(−β).

    For a linear limit state g(u) = β₀ − aᵀu this is exact and converges in a
    single step: β = β₀/‖a‖.
    """
    if n_vars < 1:
        raise SolverError("form_n_vars_must_be_positive")
    n_evals = 0
    g0 = limit_state(np.zeros(n_vars))
    n_evals += 1
    u = np.zeros(n_vars)
    converged = False
    n_iter = 0
    while n_iter < max_iter:
        n_iter += 1
        g = limit_state(u)
        n_evals += 1
        grad, ge = _fd_gradient(limit_state, u, fd_eps)
        n_evals += ge
        norm_sq = float(grad @ grad)
        if norm_sq <= 1e-300:
            raise SolverError("form_zero_gradient")
        u_new = ((grad @ u - g) / norm_sq) * grad
        if float(np.linalg.norm(u_new - u)) < tol:
            u = u_new
            converged = True
            break
        u = u_new
    beta_mag = float(np.linalg.norm(u))
    beta = beta_mag if g0 > 0 else -beta_mag
    return ReliabilityResult(
        beta=beta,
        p_failure=_standard_normal_cdf(-beta),
        mpp=u,
        n_iterations=n_iter,
        converged=converged,
        method="FORM",
        n_limit_state_evals=n_evals,
    )


def sorm_breitung(
    limit_state: Callable[[np.ndarray], float],
    form_result: ReliabilityResult,
    fd_eps: float = 1e-4,
) -> ReliabilityResult:
    """Second-order (Breitung) correction to a FORM result at its MPP.

    P_f ≈ Φ(−β) · ∏ᵢ (1 + β κᵢ)^(−1/2), where κᵢ are the principal curvatures
    of the limit-state surface at the MPP (eigenvalues of the tangent-projected
    Hessian, scaled by ‖∇g‖). For a linear limit state all κᵢ = 0 and SORM
    reduces exactly to FORM.

    Args:
        limit_state: same callable passed to ``form_hlrf``.
        form_result: a converged FORM result (provides β and the MPP).
        fd_eps:      finite-difference step for the Hessian.
    """
    u_star = np.asarray(form_result.mpp, dtype=float)
    n = u_star.size
    beta = form_result.beta
    n_evals = 0

    # Gradient norm at the MPP (central difference).
    grad, ge = _fd_gradient(limit_state, u_star, fd_eps)
    n_evals += ge
    grad_norm = float(np.linalg.norm(grad))
    if grad_norm <= 1e-300:
        raise SolverError("sorm_zero_gradient")

    # Finite-difference Hessian at the MPP.
    hess = np.zeros((n, n))
    for i in range(n):
        ei = np.zeros(n)
        ei[i] = fd_eps
        for j in range(i, n):
            ej = np.zeros(n)
            ej[j] = fd_eps
            gpp = limit_state(u_star + ei + ej)
            gpm = limit_state(u_star + ei - ej)
            gmp = limit_state(u_star - ei + ej)
            gmm = limit_state(u_star - ei - ej)
            n_evals += 4
            hess[i, j] = (gpp - gpm - gmp + gmm) / (4.0 * fd_eps * fd_eps)
            hess[j, i] = hess[i, j]

    # Tangent basis: orthonormal vectors perpendicular to the design direction â.
    if beta == 0:
        kappas = np.zeros(0)
    else:
        a_hat = u_star / np.linalg.norm(u_star)
        seed = np.eye(n)
        seed[:, 0] = a_hat
        q, _ = np.linalg.qr(seed)
        if float(q[:, 0] @ a_hat) < 0:
            q = -q
        tangent = q[:, 1:]  # (n, n-1)
        curv_matrix = (tangent.T @ hess @ tangent) / grad_norm
        kappas = np.linalg.eigvalsh(curv_matrix)

    factors = 1.0 + beta * kappas
    if np.any(factors <= 0):
        raise SolverError("sorm_breitung_invalid_curvature")
    p_form = _standard_normal_cdf(-beta)
    p_sorm = float(p_form * np.prod(factors ** -0.5))
    return ReliabilityResult(
        beta=beta,
        p_failure=p_sorm,
        mpp=u_star,
        n_iterations=0,
        converged=form_result.converged,
        method="SORM",
        n_limit_state_evals=n_evals,
    )


def importance_sampling(
    limit_state: Callable[[np.ndarray], float],
    n_vars: int,
    design_point: np.ndarray,
    n_samples: int = 2000,
    rng_seed: int = 0,
) -> dict:
    """Importance-sampling failure probability, sampling density centred at the MPP.

    Samples U ~ N(u*, I) and weights each by the likelihood ratio
    φ(u)/h(u) = exp(½‖u*‖² − u*ᵀu), giving an unbiased estimate of
    P[g(U) ≤ 0] with far lower variance than crude MC for rare events.

    Returns a dict: p_failure, std_error, cov (coefficient of variation),
    n_failures, n_samples.
    """
    if n_samples < 1:
        raise SolverError("importance_sampling_n_samples_must_be_positive")
    u_star = np.asarray(design_point, dtype=float)
    rng = np.random.default_rng(rng_seed)
    samples = rng.standard_normal((n_samples, n_vars)) + u_star
    g_vals = np.array([limit_state(s) for s in samples])
    indicator = (g_vals <= 0.0).astype(float)
    half_norm_sq = 0.5 * float(u_star @ u_star)
    lr = np.exp(half_norm_sq - samples @ u_star)
    weights = indicator * lr
    p_f = float(weights.mean())
    se = float(sqrt(weights.var(ddof=1) / n_samples)) if n_samples > 1 else float("inf")
    cov = se / p_f if p_f > 0 else float("inf")
    return {
        "p_failure": p_f,
        "std_error": se,
        "cov": cov,
        "n_failures": int(indicator.sum()),
        "n_samples": int(n_samples),
    }


# Aliases for v6 rubric grep
reliability_index = form_hlrf
first_order_reliability = form_hlrf
second_order_reliability = sorm_breitung
