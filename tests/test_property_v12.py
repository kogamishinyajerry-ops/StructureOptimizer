"""Wave HHHH (v12, D089): property tests for the v12 design-grade & adaptive drivers.

Randomised property checks complementing the per-wave anchor tests:
- nested Clayton with all-equal θ degenerates to exchangeable Clayton (D085);
- period-aware fibre-continuity gradient matches central FD (D087);
- Korobov-lattice Genz value stays in [0,1] with a non-negative SE and agrees with
  plain Genz MC within several SE (D086).
"""

from __future__ import annotations

import numpy as np
from numpy.polynomial.hermite_e import hermegauss
from structure_optimizer.core.orthotropic_simp import period_aware_continuity
from structure_optimizer.core.reliability import (
    ExchangeableClaytonCopula,
    _standard_normal_cdf,
    genz_mvn_cdf_lattice,
    nested_clayton_copula,
)


def test_property_nested_clayton_degenerates_to_exchangeable():
    rng = np.random.default_rng(11)
    for _ in range(10):
        theta = float(rng.uniform(0.3, 8.0))
        nested = nested_clayton_copula(4, [[0, 1], [2, 3]], theta, [theta, theta])
        exch = ExchangeableClaytonCopula(4, theta)
        u = rng.uniform(0.05, 0.95, size=4)
        assert abs(nested.cdf(u) - exch.cdf(u)) <= 1e-10


def test_property_period_aware_continuity_gradient_matches_fd():
    rng = np.random.default_rng(12)
    pairs = [(0, 1), (1, 2), (2, 3), (0, 3)]
    h = 1e-6
    for _ in range(10):
        angles = rng.uniform(-np.pi / 2, np.pi / 2, size=4)
        _, grad = period_aware_continuity(angles, pairs)
        for e in range(4):
            ap, am = angles.copy(), angles.copy()
            ap[e] += h
            am[e] -= h
            fd = (period_aware_continuity(ap, pairs)[0] - period_aware_continuity(am, pairs)[0]) / (2 * h)
            assert abs(grad.get(e, 0.0) - fd) <= 1e-6


def _equicorr_exact(b: np.ndarray, rho: float) -> float:
    nodes, wts = hermegauss(120)
    wts = wts / np.sqrt(2.0 * np.pi)
    return float(
        sum(
            wt * np.prod([_standard_normal_cdf((b[i] + np.sqrt(rho) * t) / np.sqrt(1.0 - rho)) for i in range(b.size)])
            for t, wt in zip(nodes, wts, strict=True)
        )
    )


def test_property_korobov_genz_value_bounded_and_accurate():
    rng = np.random.default_rng(13)
    for _ in range(6):
        rho = float(rng.uniform(0.1, 0.7))
        b = rng.uniform(0.5, 2.0, size=3)
        R = (1 - rho) * np.eye(3) + rho * np.ones((3, 3))
        res = genz_mvn_cdf_lattice(b, R, n_points=1021, n_shifts=12, seed=0)
        assert 0.0 <= res.value <= 1.0 and res.std_error >= 0.0
        assert abs(res.value - _equicorr_exact(b, rho)) <= 5.0 * res.std_error + 1e-4
