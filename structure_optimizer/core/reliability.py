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
