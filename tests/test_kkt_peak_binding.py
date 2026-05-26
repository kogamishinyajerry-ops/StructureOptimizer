"""Wave DDDDDDD (v15, D109) — strictly KKT-binding peak-binding (closes D104's deferral).

D104 demonstrated the *coupling* (min J(ω_op) in the anti-resonance valley raises a
flanking resonance) but honestly recorded that the flanking constraint was **never
strictly KKT-active** at the limits it probed (a "basin selector": at loose limits the
J-optimum basin already has a low flank, so J was not sacrificed). This wave closes that:
a **tight enough limit** (≲0.1·initial flank) drives the flank below the basin's natural
level, so the constraint goes **active** (g₁≈0) AND J(ω_op) is forced up — a strictly
binding constraint with a positive KKT multiplier.

Quantitative anchors against an independent dense sweep, never qualitative trends.
"""

import numpy as np
import pytest
from structure_optimizer.benchmarks import load_benchmark
from structure_optimizer.core.freq_response import (
    _dynamic_compliance_objective,
    kkt_binding_status,
    peak_binding_mma,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.modal import solve_modal

_BETA = 2e-6


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    opt = config.optimization
    rho0 = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    w = np.sqrt(solve_modal(config, mesh, rho0, n_modes=3).omega_squared)
    w_op = 0.5 * (w[0] + w[1])
    flo, fhi = 0.85 * w[1], 1.15 * w[1]
    init = max(_dynamic_compliance_objective(config, mesh, rho0, ww, beta=_BETA) for ww in np.linspace(flo, fhi, 120))
    return config, mesh, w_op, flo, fhi, init


@pytest.fixture(scope="module")
def runs():
    config, mesh, w_op, flo, fhi, init = _setup()
    unconstr = peak_binding_mma(config, mesh, w_op, flo, fhi, peak_limit=1e9 * init, beta=_BETA, max_iter=25)
    j_unc = unconstr.dyn_compliance_history[-1]
    tight = peak_binding_mma(config, mesh, w_op, flo, fhi, peak_limit=0.08 * init, beta=_BETA, max_iter=25)
    loose = peak_binding_mma(config, mesh, w_op, flo, fhi, peak_limit=0.40 * init, beta=_BETA, max_iter=25)
    return {"cfg": (config, mesh), "init": init, "j_unc": j_unc, "tight": tight, "loose": loose}


def test_tight_limit_is_strictly_kkt_binding(runs):
    """Closes D104: at a tight limit the constraint is ACTIVE (g₁≈0) and J is SACRIFICED
    (positive multiplier) — strict KKT binding, not just a design change."""
    config, mesh = runs["cfg"]
    s = kkt_binding_status(config, mesh, runs["tight"], beta=_BETA, j_reference=runs["j_unc"])
    assert s.active is True  # flank sits at the limit (|g₁| ≤ tol)
    assert abs(s.constraint_value) <= 0.1
    assert s.active_multiplier > 0.0  # J(ω_op) genuinely exceeds the unconstrained minimum


def test_loose_limit_is_inactive_basin_selector(runs):
    """The D104 regime: at a loose limit the constraint is INACTIVE (flank below limit)
    and J is NOT sacrificed (the J-optimum basin already satisfies it)."""
    config, mesh = runs["cfg"]
    s = kkt_binding_status(config, mesh, runs["loose"], beta=_BETA, j_reference=runs["j_unc"])
    assert s.active is False
    assert s.constraint_value < -0.1  # flank comfortably below the limit
    assert s.active_multiplier < 0.0  # J no larger than unconstrained (basin selector)


def test_active_constraint_suppresses_the_flank(runs):
    """The active constraint actually drives the flanking peak far below the
    unconstrained design's flank (it does real work, at a J cost)."""
    config, mesh = runs["cfg"]
    s_tight = kkt_binding_status(config, mesh, runs["tight"], beta=_BETA)
    s_unc = kkt_binding_status(config, mesh, runs["loose"], beta=_BETA)  # loose ~ unconstrained flank level
    assert s_tight.flank_peak < 0.5 * s_unc.flank_peak


def test_constraint_value_matches_dense_sweep(runs):
    """g₁ = flank/limit − 1 is consistent with an independent dense sweep."""
    config, mesh = runs["cfg"]
    s = kkt_binding_status(config, mesh, runs["tight"], beta=_BETA)
    lo, hi = runs["tight"].flanking_range
    flank = max(_dynamic_compliance_objective(config, mesh, runs["tight"].densities, w, beta=_BETA) for w in np.linspace(lo, hi, 120))
    assert s.flank_peak == pytest.approx(flank, rel=1e-9)
    assert s.constraint_value == pytest.approx(flank / runs["tight"].peak_limit - 1.0, rel=1e-9)


def test_active_multiplier_none_without_reference(runs):
    """Without j_reference the active_multiplier is None; the active flag still computes."""
    config, mesh = runs["cfg"]
    s = kkt_binding_status(config, mesh, runs["tight"], beta=_BETA)
    assert s.active_multiplier is None
    assert isinstance(s.active, bool)


def test_kkt_status_deterministic(runs):
    """Same result ⟹ identical status (no randomness in the diagnostic)."""
    config, mesh = runs["cfg"]
    a = kkt_binding_status(config, mesh, runs["tight"], beta=_BETA)
    b = kkt_binding_status(config, mesh, runs["tight"], beta=_BETA)
    assert a.active == b.active
    assert a.constraint_value == b.constraint_value
    assert a.flank_peak == b.flank_peak
