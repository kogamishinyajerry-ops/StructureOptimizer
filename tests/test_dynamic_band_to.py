"""Wave VV (v8, D051): filtered multi-ω dynamic-compliance TO loop.

Quantitative anchors:
- the band-averaged dynamic compliance J = mean_ω |fᵀû(ω)|² decreases
  monotonically and the volume is preserved;
- the peak magnitude over the **whole band** drops (band resonance avoidance,
  the multi-ω value-add over single-ω);
- the Sigmund density filter suppresses checkerboarding (direct smoother
  property: a checkerboard field filters to a far smoother one).
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.filtering import density_filter
from structure_optimizer.core.freq_response import (
    _checkerboard_metric,
    dynamic_compliance_to,
)
from structure_optimizer.core.mesh import create_structured_mesh

ALPHA, BETA = 0.5, 1e-4
BAND = np.linspace(30.0, 70.0, 5)


def _smoke():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def test_band_dynamic_compliance_descends_and_cuts_band_peak():
    config, mesh = _smoke()
    res = dynamic_compliance_to(config, mesh, BAND, alpha=ALPHA, beta=BETA, n_steps=18, move=0.1)
    h = res.objective_history
    assert len(h) == 19
    assert all(h[i + 1] <= h[i] * (1.0 + 1e-9) for i in range(len(h) - 1)), f"not monotone: {h}"
    assert h[-1] < 0.5 * h[0]
    # band resonance avoidance: peak over the whole band drops
    assert res.peak_after < res.peak_before
    # volume preserved at target
    assert float(np.mean(res.densities[mesh.design_mask])) == pytest.approx(
        config.optimization.volume_fraction, rel=1e-6
    )


def test_density_filter_suppresses_checkerboard():
    config, mesh = _smoke()
    n = mesh.elements.shape[0]
    raw = np.zeros(n)
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            raw[mesh.element_index(ex, ey)] = 0.8 if (ex + ey) % 2 == 0 else 0.2
    filt = density_filter(mesh, np.ones(n), raw, config.optimization.filter_radius, config.optimization.min_density)
    assert _checkerboard_metric(mesh, filt) < _checkerboard_metric(mesh, raw)
    assert _checkerboard_metric(mesh, filt) < 0.1 * _checkerboard_metric(mesh, raw)


def test_dynamic_to_rejects_empty_band():
    config, mesh = _smoke()
    with pytest.raises(SolverError, match="no_omegas"):
        dynamic_compliance_to(config, mesh, [], alpha=ALPHA, beta=BETA)
