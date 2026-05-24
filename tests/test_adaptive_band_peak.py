"""Wave TTT (v11, D075): adaptive in-band sampling + peak-as-MMA-constraint.

Quantitative anchors (analytical / reference-sweep, not qualitative trend):
- **adaptive sampling captures a sharp resonance a coarse uniform grid misses**:
  over a damped band containing the first resonance, adaptive sampling (n_init +
  n_refine evals) recovers the dense-reference peak to ≤ 2 %, while a uniform grid
  of the initial size underestimates it by ≥ 20 %;
- **adaptive concentrates evaluations at the peak**: the nearest sample to the
  located peak is far closer than the initial uniform spacing;
- **peak-as-constraint MMA binds**: min-compliance s.t. in-band peak ≤ limit (and
  volume ≤ vf) drives the band peak down onto the limit (≤ +5 %) while volume
  stays feasible — and is deterministic.

D067's reopening criteria: "adaptive band sampling; peak-as-constraint".
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.freq_response import (
    _dynamic_compliance_objective,
    adaptive_band_sample,
    peak_constrained_mma,
    target_band_peak_sensitivity,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.modal import solve_modal
from structure_optimizer.core.simp import run_simp

BETA = 2e-6  # Rayleigh stiffness damping → finite (sharp) resonance peak


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    opt = config.optimization
    rho = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    w1 = float(np.sqrt(solve_modal(config, mesh, rho, n_modes=1).omega_squared[0]))
    return config, mesh, rho, w1


def test_adaptive_sampling_captures_sharp_resonance():
    config, mesh, rho, w1 = _setup()
    # asymmetric band so the resonance is NOT a uniform-grid node
    lo, hi = 0.80 * w1, 1.30 * w1
    n_init = 7

    dense = np.linspace(lo, hi, 400)
    jd = np.array([_dynamic_compliance_objective(config, mesh, rho, w, beta=BETA) for w in dense])
    ref_peak = float(jd.max())

    wu = np.linspace(lo, hi, n_init)
    uniform_peak = float(max(_dynamic_compliance_objective(config, mesh, rho, w, beta=BETA) for w in wu))

    ab = adaptive_band_sample(config, mesh, rho, lo, hi, n_init=n_init, n_refine=18, beta=BETA)

    # adaptive recovers (or exceeds) the dense-reference peak; bisection toward the
    # peak can even out-resolve a uniform dense grid, so allow ≥ 0.98·ref
    assert ab.peak_value >= 0.98 * ref_peak, f"adaptive {ab.peak_value:.3e} vs ref {ref_peak:.3e}"
    assert abs(ab.peak_value - ref_peak) <= 0.02 * ref_peak
    # the equal-size uniform grid badly underestimates the sharp peak
    assert uniform_peak <= 0.80 * ref_peak, f"uniform {uniform_peak:.3e} vs ref {ref_peak:.3e}"
    # adaptive captures ≥ 20 % more peak than the equal-size uniform grid
    assert ab.peak_value >= 1.2 * uniform_peak
    assert ab.n_evals == n_init + 18


def test_adaptive_concentrates_samples_at_peak():
    config, mesh, rho, w1 = _setup()
    lo, hi = 0.80 * w1, 1.30 * w1
    n_init = 7
    ab = adaptive_band_sample(config, mesh, rho, lo, hi, n_init=n_init, n_refine=18, beta=BETA)

    uniform_spacing = (hi - lo) / (n_init - 1)
    nearest = float(np.min(np.abs(ab.omegas - ab.peak_omega)))
    # the nearest refined sample is an order of magnitude closer than the coarse grid
    assert nearest < uniform_spacing / 8.0, f"nearest {nearest:.2f} vs spacing {uniform_spacing:.2f}"
    # samples are sorted and within the band
    assert np.all(np.diff(ab.omegas) >= 0)
    assert ab.omegas[0] >= lo - 1e-9 and ab.omegas[-1] <= hi + 1e-9


def test_adaptive_band_invalid_range_raises():
    config, mesh, rho, w1 = _setup()
    with pytest.raises(SolverError):
        adaptive_band_sample(config, mesh, rho, 2.0 * w1, w1, n_init=5)
    with pytest.raises(SolverError):
        adaptive_band_sample(config, mesh, rho, 0.8 * w1, 1.2 * w1, n_init=1)


def test_peak_constrained_mma_binds_and_volume_feasible():
    config, mesh, _rho0, w1 = _setup()
    opt = config.optimization
    design = mesh.design_mask
    vf = opt.volume_fraction
    band = np.linspace(0.9 * w1, 1.1 * w1, 5)

    # limit below the min-compliance design's band peak → constraint must be active
    simp = run_simp(config, mesh)
    pk_simp, _, _ = target_band_peak_sensitivity(config, mesh, simp.densities, band, beta=1e-4)
    limit = 0.6 * pk_simp

    r = peak_constrained_mma(config, mesh, peak_limit=limit, band_omegas=band, beta=1e-4, vf=vf, max_iter=100)
    # peak driven well down from the uniform start and lands on the limit (≤ +5 %)
    assert r.peak_history[-1] < 0.5 * r.peak_history[0], "peak not driven down"
    assert r.peak_history[-1] <= limit * 1.05, f"peak infeasible {r.peak_history[-1]:.3e} > {limit:.3e}"
    assert float(r.densities[design].mean()) <= vf + 0.02, "volume infeasible"


def test_peak_constrained_mma_contract_and_determinism():
    config, mesh, _rho0, w1 = _setup()
    vf = config.optimization.volume_fraction
    band = np.linspace(0.9 * w1, 1.1 * w1, 4)
    a = peak_constrained_mma(config, mesh, peak_limit=1.0e5, band_omegas=band, beta=1e-4, vf=vf, max_iter=8)
    b = peak_constrained_mma(config, mesh, peak_limit=1.0e5, band_omegas=band, beta=1e-4, vf=vf, max_iter=8)
    assert a.densities.shape[0] == mesh.elements.shape[0]
    assert len(a.compliance_history) == len(a.volume_history) == len(a.peak_history)
    assert a.peak_limit == 1.0e5
    assert np.allclose(a.densities, b.densities)
    with pytest.raises(SolverError):
        peak_constrained_mma(config, mesh, peak_limit=-1.0, band_omegas=band)
