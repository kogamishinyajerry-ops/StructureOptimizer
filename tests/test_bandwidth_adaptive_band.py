"""Wave BBBBB (v13, D091): half-power bandwidth-adaptive in-loop constraint window.

Quantitative anchors (closed-form half-power relation + dense-sweep reference):
- the half-power **fractional** bandwidth is the closed form ``α/ω + β·ω = 2ζ``;
- a **bandwidth-adaptive** window is robust across resonance sharpness: over a β
  range the adaptive band's worst-case error vs the dense-sweep true peak is far
  below a fixed-fraction band's worst case (a fixed width is accurate only near one
  damping level — at ζ≈0.009 the fixed-5% band errs ~62% while the adaptive ~11%);
- the adaptive driver runs stably and stays feasible vs the dense sweep;
- determinism; guards.

D083's reopening criterion: "bandwidth-adaptive window: set band_rel_width from the
local half-power bandwidth so the constraint window scales with the resonance
sharpness." (The companion 'peak-binding produces a different design' claim is
**deferred** — see D091 honest-scope notes for the probe evidence.)
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.freq_response import (
    _dynamic_compliance_objective,
    adaptive_band_sample,
    adaptive_peak_constrained_mma,
    half_power_relative_bandwidth,
    target_band_peak_sensitivity,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.modal import solve_modal


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    opt = config.optimization
    rho = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    w1 = float(np.sqrt(solve_modal(config, mesh, rho, n_modes=1).omega_squared[0]))
    return config, mesh, rho, w1


def test_half_power_bandwidth_closed_form():
    # Δω/ω = α/ω + β·ω = 2ζ
    assert abs(half_power_relative_bandwidth(1000.0, alpha=0.0, beta=2e-6) - 2e-6 * 1000.0) <= 1e-15
    assert abs(half_power_relative_bandwidth(500.0, alpha=0.1, beta=0.0) - 0.1 / 500.0) <= 1e-15
    # combined matches 2·ζ from the modal damping ratio ζ = ½(α/ω + βω)
    a, b, w = 0.05, 1e-6, 800.0
    zeta = 0.5 * (a / w + b * w)
    assert abs(half_power_relative_bandwidth(w, a, b) - 2.0 * zeta) <= 1e-15


def _band(w, lo, hi, relw, n=5):
    return np.clip(w * np.linspace(1.0 - relw, 1.0 + relw, n), lo, hi)


def _true_peak(config, mesh, rho, lo, hi, beta, n=1200):
    omegas = np.linspace(lo, hi, n)
    j = np.array([_dynamic_compliance_objective(config, mesh, rho, w, beta=beta) for w in omegas])
    return float(j.max())


def test_adaptive_window_robust_across_sharpness():
    """A fixed 5% band is accurate only near one damping level; the half-power
    adaptive width stays bounded across sharp→broad resonances."""
    config, mesh, rho, w1 = _setup()
    lo, hi = 0.5 * w1, 1.8 * w1
    adaptive_errs, fixed_errs = [], []
    for beta in (5e-7, 2e-6, 8e-6):
        true_peak = _true_peak(config, mesh, rho, lo, hi, beta)
        ab = adaptive_band_sample(config, mesh, rho, lo, hi, n_init=9, n_refine=16, beta=beta)
        relw = half_power_relative_bandwidth(ab.peak_omega, 0.0, beta)
        p_adapt, _, _ = target_band_peak_sensitivity(
            config, mesh, rho, _band(ab.peak_omega, lo, hi, relw), 0.0, beta, 12.0, "consistent"
        )
        p_fixed, _, _ = target_band_peak_sensitivity(
            config, mesh, rho, _band(ab.peak_omega, lo, hi, 0.05), 0.0, beta, 12.0, "consistent"
        )
        adaptive_errs.append(abs(p_adapt - true_peak) / true_peak)
        fixed_errs.append(abs(p_fixed - true_peak) / true_peak)
    # worst-case robustness: the adaptive band's max error is well below the fixed band's
    assert max(adaptive_errs) < 0.5 * max(fixed_errs), f"adaptive {adaptive_errs} vs fixed {fixed_errs}"
    # at the sharpest resonance (first β) the adaptive band is dramatically better
    assert adaptive_errs[0] < 0.3 * fixed_errs[0]


def test_adaptive_driver_runs_feasible():
    config, mesh, rho, w1 = _setup()
    lo, hi = 0.6 * w1, 2.1 * w1
    beta = 2e-6
    tp0 = _true_peak(config, mesh, rho, lo, hi, beta)
    r = adaptive_peak_constrained_mma(config, mesh, 3.0 * tp0, lo, hi, beta=beta, max_iter=25, bandwidth_adaptive=True)
    true_peak = _true_peak(config, mesh, r.densities, lo, hi, beta)
    assert true_peak <= 1.05 * 3.0 * tp0
    # the recorded bands use the half-power width, not the fixed default. Check the
    # FIRST regrid (peak ≈ ω₁, mid-range, so the band is not clipped to [lo,hi]).
    w0 = r.peak_omega_history[0]
    relw = (r.band_history[0].max() / w0) - 1.0
    expected = half_power_relative_bandwidth(w0, 0.0, beta)
    assert abs(relw - expected) <= 0.05 * expected + 1e-9, f"width {relw} vs half-power {expected}"
    # it is NOT the fixed 0.05 default (the adaptive path is genuinely active)
    assert abs(relw - 0.05) > 1e-3


def test_determinism_and_guards():
    config, mesh, rho, w1 = _setup()
    lo, hi = 0.6 * w1, 2.1 * w1
    tp0 = _true_peak(config, mesh, rho, lo, hi, 2e-6)
    a = adaptive_peak_constrained_mma(config, mesh, 3.0 * tp0, lo, hi, beta=2e-6, max_iter=6, bandwidth_adaptive=True)
    b = adaptive_peak_constrained_mma(config, mesh, 3.0 * tp0, lo, hi, beta=2e-6, max_iter=6, bandwidth_adaptive=True)
    assert np.allclose(a.densities, b.densities)
    with pytest.raises(SolverError, match="half_power_nonpositive_omega"):
        half_power_relative_bandwidth(0.0, 0.0, 2e-6)
    with pytest.raises(SolverError, match="negative_coefficient"):
        half_power_relative_bandwidth(100.0, -1.0, 2e-6)
