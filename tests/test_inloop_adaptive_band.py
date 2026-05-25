"""Wave BBBB (v12, D083): in-loop adaptively re-gridded peak-constrained TO.

Quantitative anchors (dense-sweep reference + guards, not qualitative trend):
- the tracked resonance **drifts materially** during the optimisation, so
  re-gridding is doing non-trivial work (≈ +100 % on the smoke cantilever);
- **in-loop tracking beats a stale fixed band on constraint fidelity**: at the
  final design the adaptively-tracked band reports the independent dense-sweep
  true peak to within a few %, whereas a band frozen at the *initial* resonance
  under-reports it by a large margin — the decisive D075-reopening contrast;
- the final design is **feasible w.r.t. the independent dense sweep** (true peak
  ≤ limit), not merely w.r.t. the in-loop sampled band;
- determinism; input guards.

D075's reopening criterion: "in-loop adaptive re-gridding" so the peak constraint
tracks the moving resonance instead of a band fixed up front.
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
    target_band_peak_sensitivity,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.modal import solve_modal

BETA = 2e-6  # light damping → sharp, trackable, finite resonance


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    opt = config.optimization
    rho0 = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    w1 = float(np.sqrt(solve_modal(config, mesh, rho0, n_modes=1).omega_squared[0]))
    return config, mesh, w1


def _dense_true_peak(config, mesh, rho, lo, hi, n=800):
    omegas = np.linspace(lo, hi, n)
    j = np.array([_dynamic_compliance_objective(config, mesh, rho, w, beta=BETA) for w in omegas])
    k = int(j.argmax())
    return float(j[k]), float(omegas[k])


def _band(w, lo, hi, rel=0.05, n=5):
    return np.clip(w * np.linspace(1.0 - rel, 1.0 + rel, n), lo, hi)


def test_resonance_drifts_so_regridding_does_real_work():
    config, mesh, w1 = _setup()
    lo, hi = 0.6 * w1, 2.1 * w1
    tp0, _ = _dense_true_peak(config, mesh, np.where(mesh.void_mask, config.optimization.min_density, config.optimization.volume_fraction), lo, hi)
    r = adaptive_peak_constrained_mma(config, mesh, 3.0 * tp0, lo, hi, beta=BETA, max_iter=45)
    w_init, w_fin = r.peak_omega_history[0], r.peak_omega_history[-1]
    drift = abs(w_fin - w_init) / w_init
    assert drift >= 0.2, f"resonance barely moved ({w_init:.0f}->{w_fin:.0f}); re-gridding would be pointless"


def test_inloop_tracking_beats_stale_fixed_band():
    """The core D075-reopening claim, anchored to an independent dense sweep:
    the in-loop tracked band stays faithful to the true peak; a band frozen at
    the initial resonance does not."""
    config, mesh, w1 = _setup()
    lo, hi = 0.6 * w1, 2.1 * w1
    tp0, _ = _dense_true_peak(config, mesh, np.where(mesh.void_mask, config.optimization.min_density, config.optimization.volume_fraction), lo, hi)
    r = adaptive_peak_constrained_mma(config, mesh, 3.0 * tp0, lo, hi, beta=BETA, max_iter=45)
    rho = r.densities
    true_peak, _ = _dense_true_peak(config, mesh, rho, lo, hi)
    w_init, w_fin = r.peak_omega_history[0], r.peak_omega_history[-1]

    tracked, _, _ = target_band_peak_sensitivity(config, mesh, rho, _band(w_fin, lo, hi), 0.0, BETA, 12.0, "consistent")
    stale, _, _ = target_band_peak_sensitivity(config, mesh, rho, _band(w_init, lo, hi), 0.0, BETA, 12.0, "consistent")

    tracked_err = abs(tracked - true_peak) / true_peak
    stale_err = abs(stale - true_peak) / true_peak
    assert tracked_err <= 0.10, f"tracked band lost the resonance (err {tracked_err:.2%})"
    assert stale_err >= 0.30, f"stale band did NOT mis-measure — no case for re-gridding (err {stale_err:.2%})"
    assert stale_err > 3.0 * tracked_err, "in-loop must be substantially more faithful than the fixed band"


def test_final_design_feasible_against_dense_sweep():
    config, mesh, w1 = _setup()
    lo, hi = 0.6 * w1, 2.1 * w1
    tp0, _ = _dense_true_peak(config, mesh, np.where(mesh.void_mask, config.optimization.min_density, config.optimization.volume_fraction), lo, hi)
    limit = 3.0 * tp0
    r = adaptive_peak_constrained_mma(config, mesh, limit, lo, hi, beta=BETA, vf=config.optimization.volume_fraction, max_iter=45)
    true_peak, _ = _dense_true_peak(config, mesh, r.densities, lo, hi)
    assert true_peak <= 1.05 * limit, f"true peak {true_peak:.3e} exceeds limit {limit:.3e}"
    # volume constraint honoured
    vol = float(r.densities[mesh.design_mask].mean())
    assert vol <= config.optimization.volume_fraction + 0.02


def test_determinism():
    config, mesh, w1 = _setup()
    lo, hi = 0.6 * w1, 2.1 * w1
    tp0, _ = _dense_true_peak(config, mesh, np.where(mesh.void_mask, config.optimization.min_density, config.optimization.volume_fraction), lo, hi)
    a = adaptive_peak_constrained_mma(config, mesh, 3.0 * tp0, lo, hi, beta=BETA, max_iter=8)
    b = adaptive_peak_constrained_mma(config, mesh, 3.0 * tp0, lo, hi, beta=BETA, max_iter=8)
    assert np.allclose(a.densities, b.densities)
    assert np.allclose(a.peak_omega_history, b.peak_omega_history)


def test_overdamped_has_no_resonance_to_track():
    """Honest scope: when damping is heavy the forced response is monotone in ω
    (no peak), so the re-gridder pins to the band's lower edge — in-loop has
    nothing a fixed band would miss. Bounds the method's claimed value."""
    config, mesh, w1 = _setup()
    lo, hi = 0.6 * w1, 2.1 * w1
    rho = np.where(mesh.void_mask, config.optimization.min_density, config.optimization.volume_fraction)
    ab = adaptive_band_sample(config, mesh, rho, lo, hi, n_init=7, n_refine=14, beta=1e-2)
    first_step = (hi - lo) / 6.0
    assert ab.peak_omega <= lo + first_step, "overdamped response should peak at the low edge, not an interior resonance"


def test_input_guards():
    config, mesh, w1 = _setup()
    lo, hi = 0.6 * w1, 2.1 * w1
    with pytest.raises(SolverError, match="nonpositive_limit"):
        adaptive_peak_constrained_mma(config, mesh, 0.0, lo, hi, max_iter=1)
    with pytest.raises(SolverError, match="invalid_range"):
        adaptive_peak_constrained_mma(config, mesh, 1.0, hi, lo, max_iter=1)
    with pytest.raises(SolverError, match="band_too_few"):
        adaptive_peak_constrained_mma(config, mesh, 1.0, lo, hi, n_band=0, max_iter=1)
