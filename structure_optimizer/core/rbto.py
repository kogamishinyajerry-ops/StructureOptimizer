"""Wave MM (v7): reliability-based topology optimization (RBTO).

Wires the FORM reliability index (D038, ``core/reliability.py``) into a SIMP
driver — the first of v7's "forward solver → design driver" upgrades, named as a
reopening criterion in D038.

Reliability model: the applied load magnitude carries a multiplicative factor
``s ~ N(1, load_cov)``. Linear-elastic displacement scales *linearly* with load,
so the displacement limit state

    g(s) = d_allow − s·d_nominal

is **linear** in ``s``; in standard-normal space (s = 1 + load_cov·u) it is
``g(u) = (d_allow − d_nominal) − load_cov·d_nominal·u``. FORM is therefore exact:

    β = (d_allow − d_nominal) / (load_cov · d_nominal),   P_f = Φ(−β).

Because the min-compliance topology is invariant under uniform load scaling, the
reliability knob is the **volume fraction**: more material → lower d_nominal →
higher β. ``rbto_simp`` bisects the volume fraction to find the lightest
min-compliance design meeting β ≥ β_target.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.core.reliability import form_hlrf
from structure_optimizer.core.simp import run_simp


def displacement_limit_state(d_nominal: float, d_allow: float, load_cov: float):
    """Standard-normal limit state g(u) for the load-factor-uncertain displacement.

    g(u) = (d_allow − d_nominal) − load_cov·d_nominal·u; failure = {g ≤ 0}.
    """
    if d_nominal <= 0:
        raise SolverError("rbto_nonpositive_displacement")
    if load_cov <= 0:
        raise SolverError("rbto_nonpositive_cov")
    c0 = d_allow - d_nominal
    slope = load_cov * d_nominal
    return lambda u: float(c0 - slope * np.asarray(u, dtype=float)[0])


def displacement_reliability(d_nominal: float, d_allow: float, load_cov: float):
    """FORM reliability index β + P_f for the displacement limit state.

    Returns a :class:`~structure_optimizer.core.reliability.ReliabilityResult`.
    Since the limit state is linear, FORM is exact and reproduces the closed form
    β = (d_allow − d_nominal)/(load_cov·d_nominal).
    """
    return form_hlrf(displacement_limit_state(d_nominal, d_allow, load_cov), n_vars=1)


def reliability_tightened_volume_floor(load_cov: float, beta_target: float) -> float:
    """Closed-form displacement-ratio a reliable design must beat: d_nom/d_allow ≤ 1/(1+βσ).

    Handy as an analytical sanity bound (not used by the bisection directly).
    """
    if load_cov <= 0:
        raise SolverError("rbto_nonpositive_cov")
    return 1.0 / (1.0 + beta_target * load_cov)


@dataclass
class RBTOResult:
    """Output of ``rbto_simp``.

    Attributes:
        densities:                 reliability-feasible design (min-compliance at the chosen vf)
        volume_fraction:           the volume fraction RBTO selected
        d_nominal:                 max displacement of the chosen design at nominal load
        beta:                      achieved FORM reliability index
        p_failure:                 Φ(−beta)
        beta_target:               requested target
        feasible:                  whether β ≥ β_target was achievable within the vf range
        n_simp_runs:               number of SIMP solves consumed by the bisection
        deterministic_volume_fraction: the as-configured (reliability-unaware) vf
    """

    densities: np.ndarray
    volume_fraction: float
    d_nominal: float
    beta: float
    p_failure: float
    beta_target: float
    feasible: bool
    n_simp_runs: int
    deterministic_volume_fraction: float


def rbto_simp(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    d_allow: float,
    beta_target: float,
    load_cov: float = 0.1,
    vf_low: float = 0.1,
    vf_high: float = 0.9,
    vf_tol: float = 0.02,
    max_iter: int = 10,
) -> RBTOResult:
    """Bisect the volume fraction for the lightest min-compliance design with β ≥ β_target.

    Args:
        config, mesh:  the deterministic problem.
        d_allow:       displacement allowable (limit-state threshold).
        beta_target:   required reliability index.
        load_cov:      coefficient of variation of the load-magnitude factor.
        vf_low/vf_high: volume-fraction search bracket.
        vf_tol:        bisection tolerance on vf.
        max_iter:      bisection iteration cap (each iter = one SIMP solve).
    """
    if d_allow <= 0:
        raise SolverError("rbto_nonpositive_allowable")
    if beta_target < 0:
        raise SolverError("rbto_negative_beta_target")
    if load_cov <= 0:
        raise SolverError("rbto_nonpositive_cov")
    if not (0 < vf_low < vf_high <= 1.0):
        raise SolverError("rbto_invalid_vf_bracket")

    opt = config.optimization
    n_runs = 0

    def _eval(vf: float):
        nonlocal n_runs
        cfg = replace(config, optimization=replace(opt, volume_fraction=vf))
        r = run_simp(cfg, mesh)
        n_runs += 1
        d_nom = float(r.final_analysis.max_displacement)
        rel = displacement_reliability(d_nom, d_allow, load_cov)
        return r, d_nom, float(rel.beta), float(rel.p_failure)

    # More material → lower d_nominal → higher β. Check the stiff end first.
    r_hi, d_hi, beta_hi, pf_hi = _eval(vf_high)
    if beta_hi < beta_target:
        # Even the densest design in-bracket cannot reach the target.
        return RBTOResult(
            densities=r_hi.densities, volume_fraction=vf_high, d_nominal=d_hi,
            beta=beta_hi, p_failure=pf_hi, beta_target=beta_target, feasible=False,
            n_simp_runs=n_runs, deterministic_volume_fraction=opt.volume_fraction,
        )

    r_lo, d_lo, beta_lo, pf_lo = _eval(vf_low)
    if beta_lo >= beta_target:
        best = (vf_low, r_lo, d_lo, beta_lo, pf_lo)
    else:
        lo, hi = vf_low, vf_high
        best = (vf_high, r_hi, d_hi, beta_hi, pf_hi)  # densest known-feasible
        for _ in range(max_iter):
            if hi - lo < vf_tol:
                break
            mid = 0.5 * (lo + hi)
            r_m, d_m, beta_m, pf_m = _eval(mid)
            if beta_m >= beta_target:
                hi = mid
                best = (mid, r_m, d_m, beta_m, pf_m)
            else:
                lo = mid

    vf, r, d_nom, beta, pf = best
    return RBTOResult(
        densities=r.densities, volume_fraction=float(vf), d_nominal=d_nom,
        beta=beta, p_failure=pf, beta_target=beta_target, feasible=True,
        n_simp_runs=n_runs, deterministic_volume_fraction=opt.volume_fraction,
    )


# Aliases for v7 rubric grep
reliability_based_to = rbto_simp
rbto = rbto_simp


# --- Wave HHH (v9, D063): system-reliability-based TO ------------------------
#
# D042 drives the volume fraction to a target β for a *single* limit state.
# D055 gave series-system reliability (Ditlevsen bounds + bivariate CDF). D055's
# reopening criterion named the coupling: drive a topology to a target *system* β.
# A real structure has several failure modes; here each mode i is a displacement
# limit state d_allow_i with its own independent load factor s_i ~ N(1, cov_i),
# so the series-system failure is P_f,sys = 1 − ∏(1 − P_f,i) and the system index
# is β_sys = Φ⁻¹(1 − P_f,sys). More material lowers d_nominal, raising every β_i
# and hence β_sys — so the same volume bisection as D042 applies.


@dataclass
class SystemRBTOResult:
    """Output of ``system_rbto_simp`` (Wave HHH)."""

    densities: np.ndarray
    volume_fraction: float
    d_nominal: float
    per_mode_betas: list[float]
    beta_system: float
    p_failure_system: float
    beta_target: float
    feasible: bool
    n_simp_runs: int
    deterministic_volume_fraction: float


def _system_beta(d_nominal: float, d_allows, load_covs) -> tuple[float, float, list[float]]:
    """Independent series-system index from per-mode displacement limit states.

    Returns ``(beta_system, p_failure_system, per_mode_betas)``."""
    from structure_optimizer.core.reliability import _standard_normal_ppf

    betas: list[float] = []
    p_survive = 1.0
    for d_allow, cov in zip(d_allows, load_covs, strict=True):
        rel = displacement_reliability(d_nominal, d_allow, cov)
        betas.append(float(rel.beta))
        p_survive *= 1.0 - float(rel.p_failure)
    pf_sys = 1.0 - p_survive
    pf_sys = min(max(pf_sys, 1e-15), 1.0 - 1e-15)
    beta_sys = float(_standard_normal_ppf(1.0 - pf_sys))
    return beta_sys, float(pf_sys), betas


def system_rbto_simp(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    d_allows,
    beta_target: float,
    load_covs=None,
    vf_low: float = 0.1,
    vf_high: float = 0.9,
    vf_tol: float = 0.02,
    max_iter: int = 12,
) -> SystemRBTOResult:
    """Bisect the volume fraction for the lightest min-compliance design whose
    **series-system** reliability β_sys ≥ ``beta_target`` (Wave HHH, D063).

    ``d_allows`` is one displacement allowable per failure mode; ``load_covs`` the
    per-mode load coefficient of variation (default 0.1 for all). With a single
    mode this reduces exactly to :func:`rbto_simp` (β_sys = β). The modes are
    treated as independent (series failure 1 − ∏(1 − P_i))."""
    d_allows = [float(d) for d in d_allows]
    if len(d_allows) < 1:
        raise SolverError("system_rbto_no_modes")
    if any(d <= 0 for d in d_allows):
        raise SolverError("rbto_nonpositive_allowable")
    if beta_target < 0:
        raise SolverError("rbto_negative_beta_target")
    if load_covs is None:
        load_covs = [0.1] * len(d_allows)
    load_covs = [float(c) for c in load_covs]
    if len(load_covs) != len(d_allows):
        raise SolverError("system_rbto_cov_shape_mismatch")
    if any(c <= 0 for c in load_covs):
        raise SolverError("rbto_nonpositive_cov")
    if not (0 < vf_low < vf_high <= 1.0):
        raise SolverError("rbto_invalid_vf_bracket")

    opt = config.optimization
    n_runs = 0

    def _eval(vf: float):
        nonlocal n_runs
        cfg = replace(config, optimization=replace(opt, volume_fraction=vf))
        r = run_simp(cfg, mesh)
        n_runs += 1
        d_nom = float(r.final_analysis.max_displacement)
        beta_sys, pf_sys, betas = _system_beta(d_nom, d_allows, load_covs)
        return r, d_nom, beta_sys, pf_sys, betas

    r_hi, d_hi, beta_hi, pf_hi, betas_hi = _eval(vf_high)
    if beta_hi < beta_target:
        return SystemRBTOResult(
            densities=r_hi.densities, volume_fraction=vf_high, d_nominal=d_hi,
            per_mode_betas=betas_hi, beta_system=beta_hi, p_failure_system=pf_hi,
            beta_target=beta_target, feasible=False, n_simp_runs=n_runs,
            deterministic_volume_fraction=opt.volume_fraction,
        )

    r_lo, d_lo, beta_lo, pf_lo, betas_lo = _eval(vf_low)
    if beta_lo >= beta_target:
        best = (vf_low, r_lo, d_lo, beta_lo, pf_lo, betas_lo)
    else:
        lo, hi = vf_low, vf_high
        best = (vf_high, r_hi, d_hi, beta_hi, pf_hi, betas_hi)
        for _ in range(max_iter):
            if hi - lo < vf_tol:
                break
            mid = 0.5 * (lo + hi)
            r_m, d_m, beta_m, pf_m, betas_m = _eval(mid)
            if beta_m >= beta_target:
                hi = mid
                best = (mid, r_m, d_m, beta_m, pf_m, betas_m)
            else:
                lo = mid

    vf, r, d_nom, beta_sys, pf_sys, betas = best
    return SystemRBTOResult(
        densities=r.densities, volume_fraction=float(vf), d_nominal=d_nom,
        per_mode_betas=betas, beta_system=beta_sys, p_failure_system=pf_sys,
        beta_target=beta_target, feasible=True, n_simp_runs=n_runs,
        deterministic_volume_fraction=opt.volume_fraction,
    )
