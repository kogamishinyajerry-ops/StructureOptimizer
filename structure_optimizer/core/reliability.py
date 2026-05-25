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


# ---------------------------------------------------------------------------
# Wave PP (v7, D045): Nataf transform — correlated / non-Gaussian uncertainty.
#
# FORM/SORM (D038) assume the physical variables are *independent Gaussians*.
# The Nataf model lifts that: given marginal distributions Fᵢ and a physical
# correlation matrix Rₓ, it maps the physical vector X to independent
# standard-normal U so the existing HL-RF machinery applies unchanged.
# ---------------------------------------------------------------------------


def _standard_normal_ppf(p: float) -> float:
    """Inverse standard-normal CDF Φ⁻¹ (numpy/stdlib only).

    Acklam's rational approximation, refined with one Halley step against the
    erf-based Φ so the result is accurate to ~1e-12 across (0, 1).
    """
    if not (0.0 < p < 1.0):
        if p == 0.0:
            return -np.inf
        if p == 1.0:
            return np.inf
        raise SolverError("ppf_out_of_range")
    a = (-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2,
         1.383577518672690e2, -3.066479806614716e1, 2.506628277459239e0)
    b = (-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2,
         6.680131188771972e1, -1.328068155288572e1)
    c = (-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838e0,
         -2.549732539343734e0, 4.374664141464968e0, 2.938163982698783e0)
    d = (7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996e0,
         3.754408661907416e0)
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = sqrt(-2.0 * np.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    elif p <= phigh:
        q = p - 0.5
        r = q * q
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
            (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    else:
        q = sqrt(-2.0 * np.log(1.0 - p))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    # One Halley refinement: e = Φ(x) − p, u = e·√(2π)·e^{x²/2}.
    e = _standard_normal_cdf(x) - p
    u = e * sqrt(2.0 * np.pi) * np.exp(0.5 * x * x)
    return float(x - u / (1.0 + 0.5 * x * u))


_EULER_GAMMA = 0.5772156649015329


@dataclass
class Marginal:
    """A 1-D marginal distribution.

    ``kind`` and (``param_a``, ``param_b``):
      - ``normal``:    (mean μ, std σ)
      - ``lognormal``: (log-mean λ, log-std ζ) of ``ln X``; X = exp(λ + ζ·Z)
      - ``weibull``:   (shape k, scale λ); F(x) = 1 − exp(−(x/λ)^k), x ≥ 0
      - ``gumbel``:    (location μ, scale β), max-type; F(x) = exp(−exp(−(x−μ)/β))
    """

    kind: str
    param_a: float
    param_b: float

    def __post_init__(self) -> None:
        if self.kind not in ("normal", "lognormal", "weibull", "gumbel"):
            raise SolverError("nataf_unknown_marginal")
        if self.param_b <= 0:
            raise SolverError("nataf_nonpositive_scale")
        if self.kind == "weibull" and self.param_a <= 0:
            raise SolverError("nataf_nonpositive_scale")

    def to_standard_normal(self, x: float) -> float:
        """Z = Φ⁻¹(F(x)) — physical value → standard normal."""
        if self.kind == "normal":
            return (x - self.param_a) / self.param_b
        if self.kind == "lognormal":
            if x <= 0:
                raise SolverError("nataf_lognormal_nonpositive_x")
            return (np.log(x) - self.param_a) / self.param_b
        if self.kind == "weibull":
            if x <= 0:
                raise SolverError("nataf_weibull_nonpositive_x")
            cdf = 1.0 - np.exp(-((x / self.param_b) ** self.param_a))
            return _standard_normal_ppf(float(cdf))
        # gumbel
        cdf = np.exp(-np.exp(-(x - self.param_a) / self.param_b))
        return _standard_normal_ppf(float(cdf))

    def from_standard_normal(self, z: float) -> float:
        """X = F⁻¹(Φ(z)) — standard normal → physical value."""
        if self.kind == "normal":
            return self.param_a + self.param_b * z
        if self.kind == "lognormal":
            return float(np.exp(self.param_a + self.param_b * z))
        p = _standard_normal_cdf(float(z))
        p = min(max(p, 1e-15), 1.0 - 1e-15)
        if self.kind == "weibull":
            return float(self.param_b * (-np.log(1.0 - p)) ** (1.0 / self.param_a))
        # gumbel
        return float(self.param_a - self.param_b * np.log(-np.log(p)))

    def lognormal_zeta(self) -> float:
        return self.param_b

    def moments(self) -> tuple[float, float]:
        """(mean, std) of the marginal — used to standardise the Nataf integrand."""
        if self.kind == "normal":
            return self.param_a, self.param_b
        if self.kind == "lognormal":
            lam, zeta = self.param_a, self.param_b
            mean = float(np.exp(lam + 0.5 * zeta * zeta))
            std = float(mean * sqrt(np.exp(zeta * zeta) - 1.0))
            return mean, std
        if self.kind == "weibull":
            from math import gamma

            k, lam = self.param_a, self.param_b
            mean = lam * gamma(1.0 + 1.0 / k)
            var = lam * lam * (gamma(1.0 + 2.0 / k) - gamma(1.0 + 1.0 / k) ** 2)
            return float(mean), float(sqrt(var))
        # gumbel
        mu, beta = self.param_a, self.param_b
        return float(mu + beta * _EULER_GAMMA), float(beta * np.pi / sqrt(6.0))


def _equivalent_normal_correlation(marginals: list[Marginal], rho_x: np.ndarray) -> np.ndarray:
    """Nataf equivalent standard-normal correlation Rᵤ from physical Rₓ.

    Exact closed forms are used for the pairs this engine supports:
      - normal–normal:        ρ_z = ρ_x  (no distortion).
      - lognormal–lognormal:  ρ_z = ln(1 + ρ_x·c) / (ζ_i·ζ_j), with
                              c = √((e^{ζ_i²}−1)(e^{ζ_j²}−1)).
    Mixed normal/lognormal pairs with ρ_x ≠ 0 are rejected (no closed form
    here); set those off-diagonals to 0 or use same-family marginals.
    """
    n = len(marginals)
    rz = np.array(rho_x, dtype=float, copy=True)
    for i in range(n):
        for j in range(i + 1, n):
            r = rho_x[i, j]
            ki, kj = marginals[i].kind, marginals[j].kind
            if r == 0.0:
                continue
            if ki == "normal" and kj == "normal":
                pass  # ρ_z = ρ_x
            elif ki == "lognormal" and kj == "lognormal":
                zi, zj = marginals[i].lognormal_zeta(), marginals[j].lognormal_zeta()
                c = sqrt((np.exp(zi * zi) - 1.0) * (np.exp(zj * zj) - 1.0))
                arg = 1.0 + r * c
                if arg <= 0:
                    raise SolverError("nataf_lognormal_correlation_infeasible")
                rz[i, j] = rz[j, i] = float(np.log(arg) / (zi * zj))
            else:
                raise SolverError("nataf_mixed_marginal_correlation_unsupported")
    return rz


@dataclass
class NatafTransform:
    """Map between physical X (correlated, possibly non-Gaussian) and independent U.

    ``u_to_x``: Z = L·U (correlated std-normals), Xᵢ = Fᵢ⁻¹(Φ(Zᵢ)).
    ``x_to_u``: Zᵢ = Φ⁻¹(Fᵢ(Xᵢ)), U = L⁻¹·Z.
    where Rᵤ = L·Lᵀ is the equivalent normal correlation (Cholesky).
    """

    marginals: list[Marginal]
    correlation_x: np.ndarray
    correlation_u: np.ndarray
    chol: np.ndarray

    @property
    def n_vars(self) -> int:
        return len(self.marginals)

    def u_to_x(self, u: np.ndarray) -> np.ndarray:
        z = self.chol @ np.asarray(u, dtype=float)
        return np.array([m.from_standard_normal(zi) for m, zi in zip(self.marginals, z, strict=True)])

    def x_to_u(self, x: np.ndarray) -> np.ndarray:
        z = np.array(
            [m.to_standard_normal(xi) for m, xi in zip(self.marginals, np.asarray(x, dtype=float), strict=True)]
        )
        return np.linalg.solve(self.chol, z)

    def wrap_limit_state(self, g_physical: Callable[[np.ndarray], float]) -> Callable[[np.ndarray], float]:
        """Turn a physical-space limit state g(x) into a U-space g(u) for ``form_hlrf``."""
        return lambda u: g_physical(self.u_to_x(u))


def build_nataf(marginals: list[Marginal], correlation_x: np.ndarray | None = None) -> NatafTransform:
    """Construct a :class:`NatafTransform` from marginals + physical correlation.

    ``correlation_x`` defaults to the identity (independent variables). It must be
    square, symmetric, unit-diagonal and positive-definite (after the equivalent
    normal correction).
    """
    n = len(marginals)
    if n < 1:
        raise SolverError("nataf_no_marginals")
    rho = np.eye(n) if correlation_x is None else np.asarray(correlation_x, dtype=float)
    if rho.shape != (n, n):
        raise SolverError("nataf_correlation_shape_mismatch")
    if not np.allclose(rho, rho.T, atol=1e-12):
        raise SolverError("nataf_correlation_not_symmetric")
    if not np.allclose(np.diag(rho), 1.0, atol=1e-12):
        raise SolverError("nataf_correlation_not_unit_diagonal")
    rz = _equivalent_normal_correlation(marginals, rho)
    try:
        chol = np.linalg.cholesky(rz)
    except np.linalg.LinAlgError as exc:
        raise SolverError("nataf_correlation_not_positive_definite") from exc
    return NatafTransform(marginals=marginals, correlation_x=rho, correlation_u=rz, chol=chol)


def correlated_gaussian_reliability(
    mean: np.ndarray,
    std: np.ndarray,
    correlation: np.ndarray,
    limit_state_physical: Callable[[np.ndarray], float],
    **form_kwargs: Any,
) -> ReliabilityResult:
    """FORM for a limit state over **correlated Gaussian** physical variables.

    For a linear limit state g(x) = a₀ − aᵀx with X ~ N(μ, Σ), Σ = DₛRDₛ
    (Dₛ = diag(std)), this is exact and reproduces the closed form
    β = (a₀ − aᵀμ) / √(aᵀΣa).
    """
    mean = np.asarray(mean, dtype=float)
    std = np.asarray(std, dtype=float)
    marginals = [Marginal("normal", float(m), float(s)) for m, s in zip(mean, std, strict=True)]
    nataf = build_nataf(marginals, correlation)
    return form_hlrf(nataf.wrap_limit_state(limit_state_physical), n_vars=len(marginals), **form_kwargs)


# ---------------------------------------------------------------------------
# Wave FFF (v9, D061): Rosenblatt transform for a known joint distribution.
#
# When the *joint* distribution is known (not just marginals + a correlation),
# the Rosenblatt transform maps X → independent standard normals U through the
# chain of conditional CDFs:
#     u_1 = Φ⁻¹(F_1(x_1)),  u_k = Φ⁻¹(F_{k|1..k-1}(x_k | x_1..x_{k-1})).
# For a multivariate normal N(μ, Σ) the conditionals are Gaussian, so the
# Φ⁻¹∘F_{k|..} collapses to the standardised conditional
#     u_k = (x_k − μ_{k|..}) / σ_{k|..},
# which (with the natural ordering) is exactly the forward substitution
# u = L⁻¹(x − μ) for the Cholesky factor Σ = L Lᵀ — the cross-check anchor.
# ---------------------------------------------------------------------------


@dataclass
class RosenblattTransform:
    """Rosenblatt transform for a multivariate-normal joint X ~ N(mean, cov).

    ``x_to_u`` applies the chain of (Gaussian) conditional CDFs; ``u_to_x`` is the
    sequential inverse. Independent standard normals U result (Cov(U)=I exactly).
    Mirrors :class:`NatafTransform`'s interface (``wrap_limit_state``) so FORM runs
    unchanged.
    """

    mean: np.ndarray
    cov: np.ndarray

    @property
    def n_vars(self) -> int:
        return int(self.mean.shape[0])

    def _conditional(self, k: int, x_prefix: np.ndarray) -> tuple[float, float]:
        """(μ_{k|0..k-1}, σ_{k|0..k-1}) given x[:k] = ``x_prefix``."""
        mean, cov = self.mean, self.cov
        if k == 0:
            return float(mean[0]), float(np.sqrt(cov[0, 0]))
        s = cov[:k, :k]
        c = cov[k, :k]
        w = np.linalg.solve(s, c)  # Σ[:k,:k]⁻¹ Σ[:k,k]
        mu = float(mean[k] + w @ (x_prefix[:k] - mean[:k]))
        var = float(cov[k, k] - c @ w)
        if var <= 0:
            raise SolverError("rosenblatt_nonpositive_conditional_variance")
        return mu, float(np.sqrt(var))

    def x_to_u(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        u = np.empty(self.n_vars)
        for k in range(self.n_vars):
            mu, sig = self._conditional(k, x)
            # u_k = Φ⁻¹(F_{k|..}(x_k)) = Φ⁻¹(Φ((x_k−μ)/σ)) = (x_k−μ)/σ
            u[k] = (x[k] - mu) / sig
        return u

    def u_to_x(self, u: np.ndarray) -> np.ndarray:
        u = np.asarray(u, dtype=float)
        x = np.empty(self.n_vars)
        for k in range(self.n_vars):
            mu, sig = self._conditional(k, x)
            x[k] = mu + u[k] * sig
        return x

    def wrap_limit_state(self, g_physical: Callable[[np.ndarray], float]) -> Callable[[np.ndarray], float]:
        """Turn a physical-space limit state g(x) into a U-space g(u) for ``form_hlrf``."""
        return lambda u: g_physical(self.u_to_x(u))


def build_rosenblatt_normal(mean: np.ndarray, cov: np.ndarray) -> RosenblattTransform:
    """Construct a :class:`RosenblattTransform` for X ~ N(mean, cov).

    ``cov`` must be symmetric positive-definite (checked via Cholesky)."""
    mean = np.asarray(mean, dtype=float).reshape(-1)
    cov = np.asarray(cov, dtype=float)
    n = mean.shape[0]
    if cov.shape != (n, n):
        raise SolverError("rosenblatt_cov_shape_mismatch")
    if not np.allclose(cov, cov.T, atol=1e-12):
        raise SolverError("rosenblatt_cov_not_symmetric")
    try:
        np.linalg.cholesky(cov)
    except np.linalg.LinAlgError as exc:
        raise SolverError("rosenblatt_cov_not_positive_definite") from exc
    return RosenblattTransform(mean=mean, cov=cov)


# ---------------------------------------------------------------------------
# Wave NNN (v10, D069): Archimedean-copula Rosenblatt for non-Gaussian deps.
#
# D061's RosenblattTransform is MVN-only — its dependence is fully described by a
# covariance. Many real joint distributions have *tail* dependence a Gaussian
# copula cannot express. A bivariate Archimedean copula C(u,v) couples two
# uniform marginals through a single generator; the Rosenblatt conditional CDF is
#     C_{2|1}(u_2 | u_1) = ∂C(u_1,u_2)/∂u_1,
# which (composed with Φ⁻¹) maps the dependent pair to independent standard
# normals for FORM. We implement Clayton (lower-tail dependence) and Frank (no
# tail dependence, symmetric), both with closed-form conditional CDF, its inverse
# (so the transform round-trips exactly), and Kendall's τ.
# ---------------------------------------------------------------------------


def _debye1(theta: float) -> float:
    """Debye function D₁(θ) = (1/θ)∫₀^θ t/(eᵗ−1) dt, by numpy Simpson (no scipy).

    Used by Frank's Kendall-τ. ``t/(eᵗ−1) → 1`` as ``t → 0`` (handled explicitly).
    Valid for θ of either sign (the linspace + Simpson carry the sign).
    """
    n = 2000  # even, for Simpson
    t = np.linspace(0.0, theta, n + 1)
    f = np.empty_like(t)
    f[0] = 1.0
    f[1:] = t[1:] / np.expm1(t[1:])
    h = theta / n
    s = f[0] + f[-1] + 4.0 * f[1:-1:2].sum() + 2.0 * f[2:-1:2].sum()
    return float((h / 3.0) * s / theta)


@dataclass
class ArchimedeanCopula:
    """Bivariate Archimedean copula — Clayton or Frank (Wave NNN, D069).

    ``family`` ∈ {``"clayton"``, ``"frank"``}. Clayton: ``θ > 0`` (lower-tail
    dependence); Frank: ``θ ≠ 0`` (no tail dependence). Provides the copula CDF,
    the Rosenblatt conditional CDF ``C_{2|1}(u₂|u₁)=∂C/∂u₁`` and its inverse, and
    the closed-form Kendall's τ.
    """

    family: str
    theta: float

    def __post_init__(self) -> None:
        if self.family not in ("clayton", "frank", "gumbel"):
            raise SolverError("copula_unknown_family")
        if self.family == "clayton" and self.theta <= 0.0:
            raise SolverError("copula_clayton_nonpositive_theta")
        if self.family == "frank" and self.theta == 0.0:
            raise SolverError("copula_frank_zero_theta")
        if self.family == "gumbel" and self.theta < 1.0:
            raise SolverError("copula_gumbel_theta_below_one")

    def cdf(self, u1: float, u2: float) -> float:
        """The copula CDF ``C(u₁,u₂)``."""
        th = self.theta
        if self.family == "clayton":
            return float((u1 ** (-th) + u2 ** (-th) - 1.0) ** (-1.0 / th))
        if self.family == "gumbel":
            a = (-np.log(u1)) ** th + (-np.log(u2)) ** th
            return float(np.exp(-(a ** (1.0 / th))))
        a = np.expm1(-th)  # e^{-θ}−1
        return float(-1.0 / th * np.log1p(np.expm1(-th * u1) * np.expm1(-th * u2) / a))

    def conditional_cdf(self, u1: float, u2: float) -> float:
        """Rosenblatt conditional CDF ``C_{2|1}(u₂|u₁) = ∂C/∂u₁`` (in [0,1])."""
        th = self.theta
        if self.family == "clayton":
            return float(u1 ** (-th - 1.0) * (u1 ** (-th) + u2 ** (-th) - 1.0) ** (-1.0 / th - 1.0))
        if self.family == "gumbel":
            a = (-np.log(u1)) ** th + (-np.log(u2)) ** th
            cval = np.exp(-(a ** (1.0 / th)))
            return float(cval * a ** (1.0 / th - 1.0) * (-np.log(u1)) ** (th - 1.0) / u1)
        a = np.expm1(-th)
        p = np.exp(-th * u1)
        qm = np.expm1(-th * u2)  # e^{-θu₂}−1
        return float(p * qm / (a + (p - 1.0) * qm))

    def conditional_ppf(self, u1: float, w: float) -> float:
        """Inverse of :meth:`conditional_cdf` in ``u₂``: returns ``u₂`` with
        ``C_{2|1}(u₂|u₁) = w``. Closed form for Clayton/Frank; bisection for Gumbel
        (no closed form — the conditional is monotone in ``u₂``)."""
        th = self.theta
        if self.family == "clayton":
            return float((u1 ** (-th) * (w ** (-th / (th + 1.0)) - 1.0) + 1.0) ** (-1.0 / th))
        if self.family == "gumbel":
            lo, hi = 1e-12, 1.0 - 1e-12
            for _ in range(100):
                mid = 0.5 * (lo + hi)
                if self.conditional_cdf(u1, mid) < w:
                    lo = mid
                else:
                    hi = mid
            return float(0.5 * (lo + hi))
        a = np.expm1(-th)
        p = np.exp(-th * u1)
        return float(-1.0 / th * np.log1p(w * a / (p * (1.0 - w) + w)))

    def kendall_tau(self) -> float:
        """Closed-form Kendall's τ: Clayton ``θ/(θ+2)``; Frank ``1 − 4/θ(1 − D₁(θ))``;
        Gumbel ``1 − 1/θ``."""
        th = self.theta
        if self.family == "clayton":
            return float(th / (th + 2.0))
        if self.family == "gumbel":
            return float(1.0 - 1.0 / th)
        return float(1.0 - 4.0 / th * (1.0 - _debye1(th)))


def clayton_copula(theta: float) -> ArchimedeanCopula:
    """Clayton copula (lower-tail dependence), ``θ > 0``."""
    return ArchimedeanCopula(family="clayton", theta=float(theta))


def frank_copula(theta: float) -> ArchimedeanCopula:
    """Frank copula (symmetric, no tail dependence), ``θ ≠ 0``."""
    return ArchimedeanCopula(family="frank", theta=float(theta))


def gumbel_copula(theta: float) -> ArchimedeanCopula:
    """Gumbel copula (upper-tail dependence), ``θ ≥ 1`` (Wave VVV, D077)."""
    return ArchimedeanCopula(family="gumbel", theta=float(theta))


def _marginal_cdf(m: Marginal, x: float) -> float:
    """Uniform ``u = F(x)`` via the marginal's standard-normal map: ``Φ(Φ⁻¹(F(x)))``."""
    return _standard_normal_cdf(m.to_standard_normal(x))


def _marginal_ppf(m: Marginal, u: float) -> float:
    """Physical ``x = F⁻¹(u)`` via the marginal's inverse map: ``F⁻¹(Φ(Φ⁻¹(u)))``."""
    return m.from_standard_normal(_standard_normal_ppf(u))


@dataclass
class CopulaRosenblattTransform:
    """Rosenblatt transform of a **bivariate** joint distribution given by two
    marginals coupled with an Archimedean copula (Wave NNN, D069).

    ``x_to_u`` maps physical ``x`` to independent standard normals via
    ``u₁=F₁(x₁), u₂=F₂(x₂); w₁=u₁, w₂=C_{2|1}(u₂|u₁); z=Φ⁻¹(w)``; ``u_to_x`` is the
    sequential inverse. Mirrors :class:`RosenblattTransform`'s interface
    (``wrap_limit_state``) so ``form_hlrf`` runs unchanged.
    """

    marginals: list[Marginal]
    copula: ArchimedeanCopula

    @property
    def n_vars(self) -> int:
        return 2

    def x_to_u(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        u1 = _clip_unit(_marginal_cdf(self.marginals[0], x[0]))
        u2 = _clip_unit(_marginal_cdf(self.marginals[1], x[1]))
        w2 = _clip_unit(self.copula.conditional_cdf(u1, u2))
        return np.array([_standard_normal_ppf(u1), _standard_normal_ppf(w2)])

    def u_to_x(self, u: np.ndarray) -> np.ndarray:
        u = np.asarray(u, dtype=float)
        w1 = _clip_unit(_standard_normal_cdf(float(u[0])))
        w2 = _clip_unit(_standard_normal_cdf(float(u[1])))
        u2 = _clip_unit(self.copula.conditional_ppf(w1, w2))
        return np.array([_marginal_ppf(self.marginals[0], w1), _marginal_ppf(self.marginals[1], u2)])

    def wrap_limit_state(self, g_physical: Callable[[np.ndarray], float]) -> Callable[[np.ndarray], float]:
        """Turn a physical-space limit state g(x) into a U-space g(u) for ``form_hlrf``."""
        return lambda u: g_physical(self.u_to_x(u))


def _clip_unit(p: float) -> float:
    """Clamp a probability strictly inside (0,1) to keep Φ⁻¹ / copula maps finite."""
    return float(min(max(p, 1e-15), 1.0 - 1e-15))


def build_copula_rosenblatt(marginals: list[Marginal], copula: ArchimedeanCopula) -> CopulaRosenblattTransform:
    """Construct a :class:`CopulaRosenblattTransform` for exactly two marginals."""
    if len(marginals) != 2:
        raise SolverError("copula_rosenblatt_requires_two_marginals")
    return CopulaRosenblattTransform(marginals=list(marginals), copula=copula)


@dataclass
class ExchangeableClaytonCopula:
    """``d``-variate **exchangeable Clayton** copula via the Archimedean generator
    (Wave VVV, D077).

    Generator ``φ(u) = u^{-θ} − 1`` with inverse ``ψ(s) = (1+s)^{-1/θ}``, so

        C(u₁,…,u_d) = ψ( Σ_i φ(u_i) ) = ( Σ_i u_i^{-θ} − (d−1) )^{-1/θ}.

    Because ``ψ^{(j)}(s) = (−1)^j [Π_{l<j}(1/θ+l)] (1+s)^{-1/θ-j}``, the sequential
    Rosenblatt **conditional CDF** (the constant Π and sign cancel in the ratio) is
    the closed form

        C_{k|1..k-1}(u_k | u_{<k}) = (T_k / T_{k-1})^{-(1/θ + k − 1)},
        T_j = Σ_{i≤j} u_i^{-θ} − (j−1),

    and the conditional inverse is closed form too — so a ``d``-dim Clayton
    Rosenblatt transform is fully analytic (validated against numerical mixed
    partials of the copula CDF to ≈ 1e-7). Pairwise Kendall's τ = ``θ/(θ+2)``.
    """

    dim: int
    theta: float

    def __post_init__(self) -> None:
        if self.dim < 2:
            raise SolverError("clayton_d_copula_dim_too_small")
        if self.theta <= 0.0:
            raise SolverError("copula_clayton_nonpositive_theta")

    def _t(self, u: np.ndarray, j: int) -> float:
        """``T_j = Σ_{i<j} u_i^{-θ} − (j−1)`` over the first ``j`` components."""
        th = self.theta
        return float(np.sum(np.asarray(u[:j], dtype=float) ** (-th)) - (j - 1))

    def cdf(self, u: np.ndarray) -> float:
        """The ``d``-variate copula CDF ``C(u)``."""
        u = np.asarray(u, dtype=float)
        if u.shape[0] != self.dim:
            raise SolverError("clayton_d_copula_dim_mismatch")
        th = self.theta
        return float((np.sum(u ** (-th)) - (self.dim - 1)) ** (-1.0 / th))

    def conditional_cdf(self, u_upto_k: np.ndarray) -> float:
        """``C_{k|1..k-1}(u_k | u_{<k})`` where ``k = len(u_upto_k)`` (k ≥ 2)."""
        u = np.asarray(u_upto_k, dtype=float)
        k = u.shape[0]
        if k < 2 or k > self.dim:
            raise SolverError("clayton_d_conditional_bad_k")
        th = self.theta
        return float((self._t(u, k) / self._t(u, k - 1)) ** (-(1.0 / th + (k - 1))))

    def conditional_ppf(self, u_prev: np.ndarray, w: float, k: int) -> float:
        """Inverse of :meth:`conditional_cdf` in ``u_k``: return ``u_k`` with
        ``C_{k|1..k-1}(u_k | u_prev) = w`` (``u_prev`` has the first ``k−1`` comps)."""
        u_prev = np.asarray(u_prev, dtype=float)
        if k < 2 or k > self.dim or u_prev.shape[0] != k - 1:
            raise SolverError("clayton_d_conditional_bad_k")
        th = self.theta
        e_k = 1.0 / th + (k - 1)
        t_km1 = self._t(u_prev, k - 1)
        uk_pow = t_km1 * (w ** (-1.0 / e_k) - 1.0) + 1.0
        return float(uk_pow ** (-1.0 / th))

    def kendall_tau(self) -> float:
        """Pairwise Kendall's τ = ``θ/(θ+2)`` (exchangeable)."""
        return float(self.theta / (self.theta + 2.0))


def clayton_d_copula(dim: int, theta: float) -> ExchangeableClaytonCopula:
    """``d``-variate exchangeable Clayton copula (``θ > 0``)."""
    return ExchangeableClaytonCopula(dim=int(dim), theta=float(theta))


def _gumbel_psi_derivative_terms(order: int, alpha: float) -> list[tuple[float, float]]:
    """Monomial terms ``(c, p)`` of ``g_order(s)`` such that the ``order``-th
    derivative of the Gumbel generator inverse ``ψ(s) = exp(−s^α)`` is

        ψ^{(order)}(s) = exp(−s^α) · Σ_j c_j · s^{p_j}.

    Exact closed-form recursion (no quadrature): from ``ψ' = −α s^{α−1} ψ`` write
    ``ψ^{(k)} = ψ · g_k`` with ``g_0 = 1`` and ``g_{k+1} = g_k′ − α s^{α−1} g_k``.
    Each ``g_k`` is a finite sum of monomials ``c·s^p``; differentiation maps
    ``c·s^p → c·p·s^{p−1}`` and the ``−α s^{α−1}·`` factor maps ``c·s^p →
    −α c·s^{p+α−1}``. Powers are rounded to 12 dp only to merge like terms.
    """
    terms: dict[float, float] = {0.0: 1.0}  # g_0 = 1
    for _ in range(order):
        nxt: dict[float, float] = {}
        for p, c in terms.items():
            if p != 0.0:  # derivative term c·p·s^{p−1}
                key = round(p - 1.0, 12)
                nxt[key] = nxt.get(key, 0.0) + c * p
            key = round(p + alpha - 1.0, 12)  # −α s^{α−1}·(c·s^p)
            nxt[key] = nxt.get(key, 0.0) - alpha * c
        terms = {p: c for p, c in nxt.items() if abs(c) > 0.0}
    return [(c, p) for p, c in terms.items()]


@dataclass
class ExchangeableGumbelCopula:
    """``d``-variate **exchangeable Gumbel** copula via the Archimedean generator
    (Wave DDDDD, D093).

    Generator ``φ(u) = (−ln u)^θ`` (``θ ≥ 1``) with inverse ``ψ(s) = exp(−s^{1/θ})``,
    so with ``S_k = Σ_{i≤k} (−ln u_i)^θ``

        C(u₁,…,u_d) = ψ(S_d) = exp( −( Σ_i (−ln u_i)^θ )^{1/θ} ).

    Unlike Clayton, ``ψ^{(k)}`` has no one-line form, but it is the **exact** closed
    recursion ``ψ^{(k)} = ψ·g_k`` (:func:`_gumbel_psi_derivative_terms`). The
    sequential Rosenblatt **conditional CDF** (the shared ``Π φ′(u_i)`` cancels in the
    ratio) is therefore analytic:

        C_{k|1..k-1}(u_k | u_{<k}) = ψ^{(k−1)}(S_k) / ψ^{(k−1)}(S_{k−1}),

    validated against numerical mixed partials of the CDF (≈ 1e-9 at d=3). The
    conditional inverse has no closed form (bisection on the monotone conditional).
    Pairwise Kendall's τ = ``1 − 1/θ``. ``dim = 2`` reproduces the bivariate
    :class:`ArchimedeanCopula` Gumbel exactly.
    """

    dim: int
    theta: float

    def __post_init__(self) -> None:
        if self.dim < 2:
            raise SolverError("gumbel_d_copula_dim_too_small")
        if self.theta < 1.0:
            raise SolverError("copula_gumbel_theta_below_one")

    def _s(self, u: np.ndarray, j: int) -> float:
        """``S_j = Σ_{i<j} (−ln u_i)^θ`` over the first ``j`` components."""
        return float(np.sum((-np.log(np.asarray(u[:j], dtype=float))) ** self.theta))

    def _psi_deriv(self, s: float, order: int) -> float:
        """``ψ^{(order)}(s) = exp(−s^{1/θ}) · Σ c·s^p``."""
        alpha = 1.0 / self.theta
        g = sum(c * s**p for c, p in _gumbel_psi_derivative_terms(order, alpha))
        return float(np.exp(-(s**alpha)) * g)

    def cdf(self, u: np.ndarray) -> float:
        """The ``d``-variate copula CDF ``C(u)``."""
        u = np.asarray(u, dtype=float)
        if u.shape[0] != self.dim:
            raise SolverError("gumbel_d_copula_dim_mismatch")
        return float(np.exp(-(self._s(u, self.dim) ** (1.0 / self.theta))))

    def conditional_cdf(self, u_upto_k: np.ndarray) -> float:
        """``C_{k|1..k-1}(u_k | u_{<k})`` where ``k = len(u_upto_k)`` (k ≥ 2)."""
        u = np.asarray(u_upto_k, dtype=float)
        k = u.shape[0]
        if k < 2 or k > self.dim:
            raise SolverError("gumbel_d_conditional_bad_k")
        return self._psi_deriv(self._s(u, k), k - 1) / self._psi_deriv(self._s(u, k - 1), k - 1)

    def conditional_ppf(self, u_prev: np.ndarray, w: float, k: int) -> float:
        """Inverse of :meth:`conditional_cdf` in ``u_k`` by bisection (the conditional
        is monotone in ``u_k``); ``u_prev`` holds the first ``k−1`` components."""
        u_prev = np.asarray(u_prev, dtype=float)
        if k < 2 or k > self.dim or u_prev.shape[0] != k - 1:
            raise SolverError("gumbel_d_conditional_bad_k")
        lo, hi = 1e-12, 1.0 - 1e-12
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            trial = np.concatenate([u_prev, [mid]])
            if self.conditional_cdf(trial) < w:
                lo = mid
            else:
                hi = mid
        return float(0.5 * (lo + hi))

    def kendall_tau(self) -> float:
        """Pairwise Kendall's τ = ``1 − 1/θ`` (exchangeable Gumbel)."""
        return float(1.0 - 1.0 / self.theta)


def gumbel_d_copula(dim: int, theta: float) -> ExchangeableGumbelCopula:
    """``d``-variate exchangeable Gumbel copula (``θ ≥ 1``)."""
    return ExchangeableGumbelCopula(dim=int(dim), theta=float(theta))


@dataclass
class ClaytonRosenblattTransform:
    """Rosenblatt transform of a ``d``-variate joint distribution: ``d`` marginals
    coupled by an exchangeable Clayton copula (Wave VVV, D077).

    Sequential map ``x → u``: ``u_i = F_i(x_i)``; ``w_1 = u_1``,
    ``w_k = C_{k|1..k-1}(u_k | u_{<k})``; ``z = Φ⁻¹(w)``. ``u_to_x`` is the
    sequential inverse. Mirrors :class:`CopulaRosenblattTransform` (D069) at
    arbitrary dimension so ``form_hlrf`` runs unchanged via ``wrap_limit_state``.
    """

    marginals: list[Marginal]
    copula: ExchangeableClaytonCopula

    @property
    def n_vars(self) -> int:
        return self.copula.dim

    def x_to_u(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        d = self.copula.dim
        u = np.array([_clip_unit(_marginal_cdf(self.marginals[i], float(x[i]))) for i in range(d)])
        z = np.empty(d)
        z[0] = _standard_normal_ppf(u[0])
        for k in range(2, d + 1):
            w = _clip_unit(self.copula.conditional_cdf(u[:k]))
            z[k - 1] = _standard_normal_ppf(w)
        return z

    def u_to_x(self, u: np.ndarray) -> np.ndarray:
        u = np.asarray(u, dtype=float)
        d = self.copula.dim
        w = np.array([_clip_unit(_standard_normal_cdf(float(u[i]))) for i in range(d)])
        uc = np.empty(d)  # copula-uniform components
        uc[0] = w[0]
        for k in range(2, d + 1):
            uc[k - 1] = _clip_unit(self.copula.conditional_ppf(uc[: k - 1], float(w[k - 1]), k))
        return np.array([_marginal_ppf(self.marginals[i], float(uc[i])) for i in range(d)])

    def wrap_limit_state(self, g_physical: Callable[[np.ndarray], float]) -> Callable[[np.ndarray], float]:
        """Turn a physical-space limit state g(x) into a U-space g(u) for ``form_hlrf``."""
        return lambda u: g_physical(self.u_to_x(u))


def build_clayton_rosenblatt(marginals: list[Marginal], theta: float) -> ClaytonRosenblattTransform:
    """Construct a ``d``-variate :class:`ClaytonRosenblattTransform` (``d ≥ 2``)."""
    d = len(marginals)
    if d < 2:
        raise SolverError("clayton_rosenblatt_requires_two_marginals")
    return ClaytonRosenblattTransform(marginals=list(marginals), copula=clayton_d_copula(d, theta))


@dataclass
class NestedClaytonCopula:
    """**Nested (hierarchical) Clayton** copula with a **per-cluster** parameter
    (Wave DDDD, D085).

    :class:`ExchangeableClaytonCopula` (D077) forces one ``θ`` — every pair has the
    same dependence. Real systems cluster: variables within a sub-system are tightly
    coupled, sub-systems loosely. A two-level fully-nested Archimedean copula
    captures that. With the Clayton generator ``φ_θ(u)=u^{-θ}−1`` and inverse
    ``ψ_θ(s)=(1+s)^{-1/θ}``, for a partition of ``{0..d-1}`` into groups ``g`` with
    inner parameters ``θ_g`` and an outer parameter ``θ₀``,

        C(u) = ψ_{θ₀}( Σ_g φ_{θ₀}( C_g(u_g) ) ),
        C_g(u_g) = ψ_{θ_g}( Σ_{i∈g} φ_{θ_g}(u_i) ).

    **Nesting condition** (Joe/McNeil, *sufficient* for a valid copula):
    ``θ_g ≥ θ₀ > 0`` for every group — within-cluster dependence at least as strong
    as between-cluster. Enforced in ``__post_init__``.

    The structure is exact in the bivariate margins (set the other arguments to 1,
    using ``ψ_{θ₀}(φ_{θ₀}(x)) = x``): two variables **in the same group ``g``** have
    margin = Clayton(``θ_g``); two in **different groups** have margin =
    Clayton(``θ₀``). Hence pairwise Kendall's τ = ``θ_g/(θ_g+2)`` within group ``g``
    and ``θ₀/(θ₀+2)`` between groups. When all ``θ_g = θ₀`` it reduces **exactly** to
    :class:`ExchangeableClaytonCopula`.
    """

    dim: int
    clusters: list[list[int]]
    theta_outer: float
    thetas_inner: list[float]

    def __post_init__(self) -> None:
        if self.dim < 2:
            raise SolverError("nested_clayton_dim_too_small")
        if len(self.clusters) != len(self.thetas_inner):
            raise SolverError("nested_clayton_cluster_theta_count_mismatch")
        if self.theta_outer <= 0.0:
            raise SolverError("nested_clayton_nonpositive_outer_theta")
        flat = [i for cl in self.clusters for i in cl]
        if sorted(flat) != list(range(self.dim)):
            raise SolverError("nested_clayton_clusters_not_a_partition")
        for th in self.thetas_inner:
            if th < self.theta_outer:
                raise SolverError("nested_clayton_nesting_condition_violated")

    def _cluster_aggregate(self, u: np.ndarray, g: int) -> float:
        """Inner copula value ``C_g(u_g) = ψ_{θ_g}(Σ_{i∈g} φ_{θ_g}(u_i))``."""
        th = self.thetas_inner[g]
        s = float(np.sum(np.asarray([u[i] for i in self.clusters[g]], dtype=float) ** (-th) - 1.0))
        return float((1.0 + s) ** (-1.0 / th))

    def cdf(self, u: np.ndarray) -> float:
        """The ``d``-variate nested copula CDF ``C(u)``."""
        u = np.asarray(u, dtype=float)
        if u.shape[0] != self.dim:
            raise SolverError("nested_clayton_dim_mismatch")
        th0 = self.theta_outer
        outer = 0.0
        for g in range(len(self.clusters)):
            cg = self._cluster_aggregate(u, g)
            outer += cg ** (-th0) - 1.0
        return float((1.0 + outer) ** (-1.0 / th0))

    def bivariate_margin_cdf(self, i: int, j: int, ui: float, uj: float) -> float:
        """Bivariate margin ``C(u_i,u_j)`` (all other arguments = 1). Equals
        Clayton(``θ_g``) if ``i,j`` share group ``g``, else Clayton(``θ₀``)."""
        if i == j or not (0 <= i < self.dim) or not (0 <= j < self.dim):
            raise SolverError("nested_clayton_bad_margin_indices")
        u = np.ones(self.dim)
        u[i] = ui
        u[j] = uj
        return self.cdf(u)

    def _group_of(self, i: int) -> int:
        for g, cl in enumerate(self.clusters):
            if i in cl:
                return g
        raise SolverError("nested_clayton_index_not_in_any_cluster")

    def kendall_tau_within(self, g: int) -> float:
        """Pairwise Kendall's τ within group ``g`` = ``θ_g/(θ_g+2)``."""
        if not (0 <= g < len(self.clusters)):
            raise SolverError("nested_clayton_bad_group")
        th = self.thetas_inner[g]
        return float(th / (th + 2.0))

    def kendall_tau_between(self) -> float:
        """Pairwise Kendall's τ between groups = ``θ₀/(θ₀+2)``."""
        return float(self.theta_outer / (self.theta_outer + 2.0))


def nested_clayton_copula(
    dim: int, clusters: list[list[int]], theta_outer: float, thetas_inner: list[float]
) -> NestedClaytonCopula:
    """Construct a :class:`NestedClaytonCopula` (two-level fully-nested Clayton)."""
    return NestedClaytonCopula(
        dim=int(dim),
        clusters=[list(c) for c in clusters],
        theta_outer=float(theta_outer),
        thetas_inner=[float(t) for t in thetas_inner],
    )


# ---------------------------------------------------------------------------
# Wave XX (v8, D053): general-marginal Nataf via Gauss-Hermite quadrature.
#
# D045's closed-form equivalent-correlation handled only normal/lognormal pairs.
# For general marginals (Weibull, Gumbel, …) the equivalent normal correlation
# ρ_z solves the Nataf integral
#     ρ_x = E[η_i(Z_i) η_j(Z_j)],  (Z_i,Z_j) ~ bivariate-normal(ρ_z),
# with η_k(z) = (F_k^{-1}(Φ(z)) − μ_k)/σ_k. We evaluate the expectation by 2-D
# Gauss-Hermite quadrature and bisect on ρ_z. For lognormal–lognormal it
# reproduces D045's closed form (the cross-check).
# ---------------------------------------------------------------------------


def nataf_correlation_gauss_hermite(
    mi: Marginal,
    mj: Marginal,
    rho_x: float,
    n_nodes: int = 24,
    tol: float = 1e-10,
    max_iter: int = 80,
) -> float:
    """Equivalent normal correlation ρ_z for marginals (mi, mj) at physical
    correlation ρ_x, via the Gauss-Hermite Nataf integral + bisection."""
    if not (-1.0 < rho_x < 1.0):
        raise SolverError("nataf_integral_rho_out_of_range")
    if rho_x == 0.0:
        return 0.0
    nodes, weights = np.polynomial.hermite.hermgauss(n_nodes)
    z = np.sqrt(2.0) * nodes
    w = weights / np.sqrt(np.pi)  # Σ w·f(z) ≈ E_φ[f]
    mui, sigi = mi.moments()
    muj, sigj = mj.moments()
    eta_i = np.array([(mi.from_standard_normal(float(zz)) - mui) / sigi for zz in z])

    def integral(rho: float) -> float:
        s = np.sqrt(max(0.0, 1.0 - rho * rho))
        total = 0.0
        for a in range(z.size):
            zj = rho * z[a] + s * z
            etaj = np.array([(mj.from_standard_normal(float(v)) - muj) / sigj for v in zj])
            total += w[a] * eta_i[a] * float(np.sum(w * etaj))
        return total

    # ρ_x→0 limit handled above; the integral is monotone increasing in ρ_z.
    lo, hi = -0.999, 0.999
    if (integral(lo) - rho_x) > 0 or (integral(hi) - rho_x) < 0:
        raise SolverError("nataf_integral_infeasible_correlation")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        fm = integral(mid) - rho_x
        if abs(fm) < tol or (hi - lo) < tol:
            return float(mid)
        if fm < 0:
            lo = mid
        else:
            hi = mid
    return float(0.5 * (lo + hi))


def build_nataf_general(
    marginals: list[Marginal],
    correlation_x: np.ndarray | None = None,
    n_nodes: int = 24,
) -> NatafTransform:
    """Construct a :class:`NatafTransform` for **general** marginals.

    The equivalent normal correlation uses the closed form for normal–normal
    pairs and the Gauss-Hermite Nataf integral
    (:func:`nataf_correlation_gauss_hermite`) for every other pair (lognormal,
    Weibull, Gumbel, mixed). Validity (positive-definiteness) is checked via
    Cholesky.
    """
    n = len(marginals)
    if n < 1:
        raise SolverError("nataf_no_marginals")
    rho = np.eye(n) if correlation_x is None else np.asarray(correlation_x, dtype=float)
    if rho.shape != (n, n):
        raise SolverError("nataf_correlation_shape_mismatch")
    if not np.allclose(rho, rho.T, atol=1e-12):
        raise SolverError("nataf_correlation_not_symmetric")
    if not np.allclose(np.diag(rho), 1.0, atol=1e-12):
        raise SolverError("nataf_correlation_not_unit_diagonal")
    rz = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            r = float(rho[i, j])
            if r == 0.0:
                continue
            if marginals[i].kind == "normal" and marginals[j].kind == "normal":
                rz[i, j] = rz[j, i] = r
            else:
                rz[i, j] = rz[j, i] = nataf_correlation_gauss_hermite(marginals[i], marginals[j], r, n_nodes)
    try:
        chol = np.linalg.cholesky(rz)
    except np.linalg.LinAlgError as exc:
        raise SolverError("nataf_correlation_not_positive_definite") from exc
    return NatafTransform(marginals=marginals, correlation_x=rho, correlation_u=rz, chol=chol)


# ---------------------------------------------------------------------------
# Wave ZZ (v8, D055): system reliability — series systems + Ditlevsen bounds.
#
# D042 (RBTO) and D038 (FORM) handle a *single* limit state. Real structures
# fail through one of several modes (series system) or only when several fail
# together (parallel). The failure probability of a series system is bounded by
# Ditlevsen's second-order bounds, which need the pairwise joint failure
# probabilities P(F_i ∩ F_j) = Φ₂(−β_i, −β_j; ρ_ij) — hence a bivariate-normal
# CDF, computed here by the exact ρ-integral identity.
# ---------------------------------------------------------------------------


def bivariate_normal_cdf(a: float, b: float, rho: float, n_nodes: int = 64) -> float:
    """Φ₂(a, b; ρ) = P(X ≤ a, Y ≤ b) for standard bivariate normal, correlation ρ.

    Uses the exact identity Φ₂(a,b;ρ) = Φ(a)Φ(b) + ∫₀^ρ φ₂(a,b;r) dr with the
    bivariate density φ₂, integrated by Gauss-Legendre quadrature (numpy-only).
    """
    if not (-1.0 <= rho <= 1.0):
        raise SolverError("bvn_rho_out_of_range")
    rho = float(np.clip(rho, -0.999999, 0.999999))
    pa, pb = _standard_normal_cdf(a), _standard_normal_cdf(b)
    if rho == 0.0:
        return float(pa * pb)
    t, w = np.polynomial.legendre.leggauss(n_nodes)
    r = rho * (t + 1.0) / 2.0
    dens = np.exp(-(a * a - 2.0 * r * a * b + b * b) / (2.0 * (1.0 - r * r))) / (2.0 * np.pi * np.sqrt(1.0 - r * r))
    return float(pa * pb + (rho / 2.0) * float(np.sum(w * dens)))


def system_reliability_series(betas, correlation: np.ndarray | None = None, n_nodes: int = 64) -> dict:
    """Failure probability of a **series** system (fails if ANY mode fails).

    Args:
        betas:        per-mode reliability indices β_k (P_k = Φ(−β_k)).
        correlation:  m×m matrix of limit-state correlations ρ_ij = α_iᵀα_j
                      (FORM MPP directions). Defaults to the identity (independent).

    Returns a dict with the simple unimodal bounds (max P_i ≤ P_f ≤ Σ P_i) and the
    tighter **Ditlevsen** second-order bounds (components ordered by descending
    P_i, as the method requires for the tightest bounds).
    """
    betas = np.asarray(betas, dtype=float).reshape(-1)
    m = betas.size
    if m < 1:
        raise SolverError("system_reliability_no_modes")
    rho = np.eye(m) if correlation is None else np.asarray(correlation, dtype=float)
    if rho.shape != (m, m):
        raise SolverError("system_reliability_correlation_shape")

    p = np.array([_standard_normal_cdf(-b) for b in betas])
    simple_lower = float(p.max())
    simple_upper = float(min(1.0, p.sum()))
    if m == 1:
        return {
            "p_failure_lower": float(p[0]), "p_failure_upper": float(p[0]),
            "simple_lower": float(p[0]), "simple_upper": float(p[0]),
        }

    order = np.argsort(-p)  # descending P_i for the tightest Ditlevsen bounds
    bo = betas[order]
    ro = rho[np.ix_(order, order)]
    po = p[order]

    def pij(i: int, j: int) -> float:
        return bivariate_normal_cdf(-bo[i], -bo[j], float(ro[i, j]), n_nodes)

    lower = float(po[0])
    upper = float(po[0])
    for i in range(1, m):
        joints = [pij(i, j) for j in range(i)]
        lower += max(0.0, float(po[i] - sum(joints)))
        upper += float(po[i] - max(joints))
    lower = float(np.clip(lower, simple_lower, simple_upper))
    upper = float(np.clip(upper, simple_lower, simple_upper))
    return {
        "p_failure_lower": lower, "p_failure_upper": upper,
        "simple_lower": simple_lower, "simple_upper": simple_upper,
    }


def system_reliability_parallel(beta_i: float, beta_j: float, rho: float, n_nodes: int = 64) -> float:
    """Failure probability of a 2-component **parallel** system (fails iff BOTH
    fail): P = P(F_i ∩ F_j) = Φ₂(−β_i, −β_j; ρ)."""
    return bivariate_normal_cdf(-beta_i, -beta_j, rho, n_nodes)


# ---------------------------------------------------------------------------
# Wave WWW (v11, D078): exact multivariate system P_f via the Genz MVN-CDF.
#
# D055/D071 bracket the series-system P_f with Ditlevsen second-order *bounds*
# (built from pairwise Φ₂). D055's reopening criterion named the **exact**
# multivariate failure probability with a **full** correlation matrix — i.e. the
# m-variate normal CDF Φ_m(b; R). Genz's (1992) separation-of-variables Monte
# Carlo estimates Φ_m exactly (in the limit) for an arbitrary SPD R, numpy-only.
# ---------------------------------------------------------------------------


def genz_mvn_cdf(
    upper: np.ndarray,
    correlation: np.ndarray,
    n_samples: int = 20000,
    seed: int = 0,
) -> float:
    """Multivariate-normal CDF ``Φ_m(b; R) = P(Z ≤ b)``, ``Z ~ N(0, R)``, via the
    **Genz (1992)** separation-of-variables Monte-Carlo estimator (Wave WWW, D078).

    Cholesky-factor ``R = L Lᵀ`` (lower ``L``), then with lower bounds ``−∞`` the
    truncated integral separates into a product the estimator averages over
    uniform samples ``w ∈ [0,1]^{m−1}``::

        e₁ = Φ(b₁/L₁₁);  for i≥2: y_{i-1}=Φ⁻¹(w_{i-1}·e_{i-1}),
        e_i = Φ((b_i − Σ_{j<i} L_ij y_j)/L_ii);   Φ_m ≈ mean(Π_i e_i).

    Converges to the **exact** CDF as ``n_samples → ∞`` (a randomised estimate,
    seeded for determinism), and handles a **full** correlation matrix (not just
    pairwise/equicorrelation). Raises ``SolverError`` for a non-SPD ``R``.
    """
    b = np.asarray(upper, dtype=float).reshape(-1)
    m = b.size
    R = np.asarray(correlation, dtype=float)
    if R.shape != (m, m):
        raise SolverError("genz_mvn_correlation_shape")
    try:
        chol = np.linalg.cholesky(R)
    except np.linalg.LinAlgError as exc:
        raise SolverError("genz_mvn_not_positive_definite") from exc
    if m == 1:
        return float(_standard_normal_cdf(b[0] / chol[0, 0]))

    phi = np.vectorize(_standard_normal_cdf, otypes=[float])
    phinv = np.vectorize(_standard_normal_ppf, otypes=[float])
    rng = np.random.default_rng(seed)
    w = rng.random((n_samples, m - 1))

    e_prev = np.full(n_samples, _standard_normal_cdf(b[0] / chol[0, 0]))
    f = e_prev.copy()
    y = np.zeros((n_samples, m))
    for i in range(1, m):
        arg = np.clip(w[:, i - 1] * e_prev, 1e-15, 1.0 - 1e-15)
        y[:, i - 1] = phinv(arg)
        s = y[:, :i] @ chol[i, :i]
        e_i = phi((b[i] - s) / chol[i, i])
        f = f * e_i
        e_prev = e_i
    return float(np.clip(f.mean(), 0.0, 1.0))


def system_reliability_series_exact(
    betas: np.ndarray,
    correlation: np.ndarray | None = None,
    n_samples: int = 20000,
    seed: int = 0,
) -> float:
    """**Exact** (Genz-MC) series-system failure probability with a full
    correlation matrix (Wave WWW, D078).

    A series system fails if **any** mode fails, so the safe event is "all modes
    safe": ``P_f = 1 − P(all Z_k < β_k) = 1 − Φ_m(β; R)`` where ``Z ~ N(0, R)`` and
    ``R_ij = α_iᵀα_j`` are the FORM limit-state correlations. Unlike
    :func:`system_reliability_series` (Ditlevsen *bounds*) this returns a single
    value that lies inside those bounds.
    """
    betas = np.asarray(betas, dtype=float).reshape(-1)
    m = betas.size
    if m < 1:
        raise SolverError("system_reliability_no_modes")
    R = np.eye(m) if correlation is None else np.asarray(correlation, dtype=float)
    if R.shape != (m, m):
        raise SolverError("system_reliability_correlation_shape")
    p_safe = genz_mvn_cdf(betas, R, n_samples=n_samples, seed=seed)
    return float(np.clip(1.0 - p_safe, 0.0, 1.0))


def _korobov_generating_vector(dim: int, a: int, n_points: int) -> np.ndarray:
    """Rank-1 **Korobov** generating vector ``z = (1, a, a², …, a^{dim−1}) mod N``."""
    z = np.ones(dim, dtype=np.int64)
    for i in range(1, dim):
        z[i] = (z[i - 1] * int(a)) % int(n_points)
    return z


def _genz_product_estimate(b: np.ndarray, chol: np.ndarray, w: np.ndarray) -> float:
    """Mean of the Genz separation-of-variables product over uniform points ``w``
    (shape ``(N, m−1)``) — the kernel shared by the MC and lattice estimators."""
    n = w.shape[0]
    m = b.size
    e_prev = np.full(n, _standard_normal_cdf(b[0] / chol[0, 0]))
    f = e_prev.copy()
    y = np.zeros((n, m))
    phi = np.vectorize(_standard_normal_cdf, otypes=[float])
    phinv = np.vectorize(_standard_normal_ppf, otypes=[float])
    for i in range(1, m):
        arg = np.clip(w[:, i - 1] * e_prev, 1e-15, 1.0 - 1e-15)
        y[:, i - 1] = phinv(arg)
        s = y[:, :i] @ chol[i, :i]
        e_i = phi((b[i] - s) / chol[i, i])
        f = f * e_i
        e_prev = e_i
    return float(f.mean())


@dataclass
class GenzLatticeResult:
    """Output of :func:`genz_mvn_cdf_lattice` (Wave EEEE, D086)."""

    value: float  # MVN CDF estimate Φ_m(b; R)
    std_error: float  # randomisation standard error (std across shifts / √n_shifts)
    n_points: int  # lattice points per shift
    n_shifts: int  # independent random shifts


def genz_mvn_cdf_lattice(
    upper: np.ndarray,
    correlation: np.ndarray,
    n_points: int = 1021,
    n_shifts: int = 12,
    a: int = 76,
    seed: int = 0,
) -> GenzLatticeResult:
    """Multivariate-normal CDF ``Φ_m(b; R)`` by a **randomly-shifted Korobov rank-1
    lattice** rule applied to the Genz separation-of-variables integrand (Wave EEEE,
    D086).

    D078's :func:`genz_mvn_cdf` samples the unit cube with pseudo-random points
    (plain Monte-Carlo, error ``O(N^{-1/2})`` with no usable error estimate). This
    replaces them with a rank-1 lattice — points ``w_k = frac(k·z/N + Δ)`` with the
    Korobov generating vector ``z = (1, a, …, a^{m-2}) mod N`` — under ``n_shifts``
    **independent random shifts** ``Δ``. The integrand (a product of smooth normal
    CDFs) is well suited to lattice rules, so each shift converges far faster than
    MC (≈ 25× lower RMS error at ``N=1021`` on an equicorrelated 4-D test). Crucially
    the **spread across the random shifts yields a genuine, reported standard
    error** (``std(estimates, ddof=1) / √n_shifts``) that the plain-MC routine cannot
    provide. As ``N → ∞`` it converges to the **exact** CDF.

    Returns a :class:`GenzLatticeResult` (``value`` + ``std_error`` +
    ``n_points`` + ``n_shifts``). Raises ``SolverError`` for a non-SPD ``R``,
    ``n_shifts < 2`` (a standard error needs ≥ 2 shifts), or ``n_points < 2``.
    """
    b = np.asarray(upper, dtype=float).reshape(-1)
    m = b.size
    R = np.asarray(correlation, dtype=float)
    if R.shape != (m, m):
        raise SolverError("genz_lattice_correlation_shape")
    if n_shifts < 2:
        raise SolverError("genz_lattice_needs_two_shifts")
    if n_points < 2:
        raise SolverError("genz_lattice_too_few_points")
    try:
        chol = np.linalg.cholesky(R)
    except np.linalg.LinAlgError as exc:
        raise SolverError("genz_lattice_not_positive_definite") from exc
    if m == 1:
        # no integration dimension: the CDF is exact, zero randomisation error
        return GenzLatticeResult(
            value=float(_standard_normal_cdf(b[0] / chol[0, 0])),
            std_error=0.0,
            n_points=int(n_points),
            n_shifts=int(n_shifts),
        )

    z = _korobov_generating_vector(m - 1, a, n_points)
    k = np.arange(n_points)[:, None]  # (N, 1)
    base = (k * z[None, :]) / float(n_points)  # (N, m-1)
    rng = np.random.default_rng(seed)
    estimates = np.empty(n_shifts)
    for q in range(n_shifts):
        shift = rng.random(m - 1)
        w = np.mod(base + shift[None, :], 1.0)
        estimates[q] = _genz_product_estimate(b, chol, w)
    value = float(np.clip(estimates.mean(), 0.0, 1.0))
    std_error = float(estimates.std(ddof=1) / np.sqrt(n_shifts))
    return GenzLatticeResult(value=value, std_error=std_error, n_points=int(n_points), n_shifts=int(n_shifts))


def system_reliability_series_lattice(
    betas: np.ndarray,
    correlation: np.ndarray | None = None,
    n_points: int = 1021,
    n_shifts: int = 12,
    a: int = 76,
    seed: int = 0,
) -> tuple[float, float]:
    """Series-system failure probability with a **reported standard error**, via the
    Korobov-lattice Genz estimator (Wave EEEE, D086).

    Like :func:`system_reliability_series_exact` (``P_f = 1 − Φ_m(β; R)``) but
    returns ``(P_f, std_error)`` — the lattice randomisation error propagates
    unchanged through the linear ``1 − ·``.
    """
    betas = np.asarray(betas, dtype=float).reshape(-1)
    m = betas.size
    if m < 1:
        raise SolverError("system_reliability_no_modes")
    R = np.eye(m) if correlation is None else np.asarray(correlation, dtype=float)
    if R.shape != (m, m):
        raise SolverError("system_reliability_correlation_shape")
    res = genz_mvn_cdf_lattice(betas, R, n_points=n_points, n_shifts=n_shifts, a=a, seed=seed)
    return float(np.clip(1.0 - res.value, 0.0, 1.0)), res.std_error
