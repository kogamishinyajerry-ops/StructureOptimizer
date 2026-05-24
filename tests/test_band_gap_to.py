"""Wave DDD (v9, D059): eigenfrequency band-gap objective on the modal solver.

Quantitative anchors:
- the analytic band-gap sensitivity dg/dρ (g = ω²_{m+1} − ω²_m) matches central
  differences of the gap (the headline — textbook eigenvalue sensitivity for
  mass-normalised modes);
- volume-preserving ascent on the gap widens it (a band-stop topology);
- a negative mode index / mismatched densities raise the documented errors.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.freq_response import band_gap_sensitivity, maximize_band_gap
from structure_optimizer.core.mesh import create_structured_mesh


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def test_property_band_gap_sensitivity_matches_central_fd():
    config, mesh = _setup()
    rng = np.random.default_rng(0)
    rho = rng.uniform(0.3, 1.0, mesh.elements.shape[0])
    rho[mesh.void_mask] = config.optimization.min_density
    gap, dgap = band_gap_sensitivity(config, mesh, rho, lower_mode=0)
    assert gap > 0.0
    design = np.where(mesh.design_mask)[0]
    top = design[np.argsort(-np.abs(dgap[design]))[:6]]
    h = 1e-6
    for e in top:
        rp, rm = rho.copy(), rho.copy()
        rp[e] += h
        rm[e] -= h
        gp, _ = band_gap_sensitivity(config, mesh, rp, 0)
        gm, _ = band_gap_sensitivity(config, mesh, rm, 0)
        fd = (gp - gm) / (2.0 * h)
        assert dgap[e] == pytest.approx(fd, rel=1e-4), f"elem {e}: adj={dgap[e]:.6e} fd={fd:.6e}"


def test_maximize_band_gap_widens_gap():
    config, mesh = _setup()
    res = maximize_band_gap(config, mesh, lower_mode=0, n_steps=15, move=0.1)
    g0, gf = res.gap_history[0], res.gap_history[-1]
    # ascent opens the gap meaningfully (observed ~2.2×)
    assert gf > 1.1 * g0, f"gap did not widen: {g0:.3e} → {gf:.3e}"
    # the modes did stay ordered (gap positive throughout the recorded history)
    assert all(g > 0 for g in res.gap_history)


def test_band_gap_pushes_modes_apart():
    config, mesh = _setup()
    res = maximize_band_gap(config, mesh, lower_mode=0, n_steps=15, move=0.1)
    gap0 = res.omega2_initial[1] - res.omega2_initial[0]
    gapf = res.omega2_final[1] - res.omega2_final[0]
    assert gapf > gap0, f"final eigen-gap {gapf:.3e} not above initial {gap0:.3e}"


def test_band_gap_deterministic():
    config, mesh = _setup()
    a = maximize_band_gap(config, mesh, lower_mode=0, n_steps=8, move=0.1)
    b = maximize_band_gap(config, mesh, lower_mode=0, n_steps=8, move=0.1)
    np.testing.assert_array_equal(a.densities, b.densities)
    assert a.gap_history == b.gap_history


def test_contracts():
    config, mesh = _setup()
    rho = np.full(mesh.elements.shape[0], 0.5)
    with pytest.raises(SolverError, match="band_gap_negative_mode"):
        band_gap_sensitivity(config, mesh, rho, lower_mode=-1)
    with pytest.raises(SolverError, match="density_count_mismatch"):
        band_gap_sensitivity(config, mesh, np.ones(3), lower_mode=0)
