"""Wave LLL (v10, D067): target-band placement (minimax around a target freq).

Quantitative anchors (analytical, not qualitative trend):
- the **in-band peak sensitivity** ``dJ_PN/dρ`` (p-norm over sampled in-band
  frequencies) matches central finite differences to relative error ≤ 1e-4 on
  the highest-sensitivity elements;
- after optimisation the **true worst-case in-band response** ``max_k J(ω_k)``
  drops sharply (band suppression actually works), not merely the smooth
  aggregate;
- the descent is **volume-preserving**: the design volume fraction is held at
  its initial value to numerical tolerance.

D059's reopening criterion was target-band placement; the band-gap wave (DDD)
only pushed two eigenvalues apart.
"""

from __future__ import annotations

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.freq_response import (
    target_band_peak_sensitivity,
    target_band_placement,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.modal import solve_modal

P = 12.0
ALPHA, BETA = 0.0, 1e-4


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    return config, mesh


def _band(config, mesh, rho):
    # a 7-point band straddling the first natural frequency (where the uniform
    # design resonates → something to suppress)
    w1 = float(np.sqrt(solve_modal(config, mesh, rho, n_modes=1).omega_squared[0]))
    return np.linspace(0.85 * w1, 1.15 * w1, 7)


def test_target_band_peak_sensitivity_matches_central_fd():
    config, mesh = _setup()
    opt = config.optimization
    rho = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    band = _band(config, mesh, rho)

    peak, dpeak, jvec = target_band_peak_sensitivity(config, mesh, rho, band, ALPHA, BETA, P)
    assert peak > 0.0
    # p-norm peak is an over-estimate of the true max but close
    assert peak >= jvec.max() - 1e-6

    order = np.argsort(-np.abs(dpeak))[:5]
    h = 1e-6
    for e in order:
        rp = rho.copy()
        rp[e] += h
        rm = rho.copy()
        rm[e] -= h
        fp, _, _ = target_band_peak_sensitivity(config, mesh, rp, band, ALPHA, BETA, P)
        fm, _, _ = target_band_peak_sensitivity(config, mesh, rm, band, ALPHA, BETA, P)
        fd = (fp - fm) / (2.0 * h)
        rel = abs(dpeak[e] - fd) / (abs(fd) + 1e-30)
        assert rel <= 1e-4, f"elem {e}: adjoint {dpeak[e]:.6e} vs FD {fd:.6e} (rel {rel:.2e})"


def test_target_band_placement_suppresses_peak():
    config, mesh = _setup()
    opt = config.optimization
    rho0 = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    band = _band(config, mesh, rho0)

    r = target_band_placement(config, mesh, band, alpha=ALPHA, beta=BETA, n_steps=20, p=P)
    # the true worst-case in-band response drops substantially
    assert r.peak_final < 0.5 * r.peak_initial, f"weak suppression: {r.peak_initial:.3e} → {r.peak_final:.3e}"


def test_target_band_placement_preserves_volume():
    config, mesh = _setup()
    opt = config.optimization
    design = mesh.design_mask
    rho0 = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    band = _band(config, mesh, rho0)
    target_vol = float(rho0[design].mean())

    r = target_band_placement(config, mesh, band, alpha=ALPHA, beta=BETA, n_steps=20, p=P)
    assert abs(float(r.densities[design].mean()) - target_vol) <= 1e-6


def test_target_band_placement_contract():
    config, mesh = _setup()
    opt = config.optimization
    rho0 = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    band = _band(config, mesh, rho0)
    r = target_band_placement(config, mesh, band, alpha=ALPHA, beta=BETA, n_steps=5, p=P)
    assert r.densities.shape[0] == mesh.elements.shape[0]
    assert r.band_omegas.shape[0] == band.shape[0]
    assert r.peak_history[-1] == r.peak_final
    # determinism
    r2 = target_band_placement(config, mesh, band, alpha=ALPHA, beta=BETA, n_steps=5, p=P)
    assert np.allclose(r.densities, r2.densities)
