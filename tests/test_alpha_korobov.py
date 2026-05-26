"""Wave EEEEEEEE (v16, D118) — α≥2 higher-smoothness weighted-Korobov worst-case error
(closes D112's "higher smoothness α≥2 (B_{2α} kernel)" reopening).

D112's korobov_worst_case_error was α=1 (the B₂ kernel). This generalises it to the B_{2α}
kernel ω_α(x) = (−1)^{α+1}(2π)^{2α}/(2α)! B_{2α}({x}), so a smoother space's lattice decay
O(N^{−α+δ}) can be certified. Quantitative analytical anchors, never qualitative trends.

v16 exact-generalization discipline: (a) α=1 reproduces D112 BIT-EXACTLY (same code path);
(b) α≥2 gives the smoother-space certificate, validated by the spatial≡general two-form
identity and a strictly faster decay rate.
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    _korobov_generating_vector,
    _korobov_kernel_omega,
    _korobov_kernel_omega_alpha,
    korobov_worst_case_error,
)

_GAMMA = np.array([0.7, 0.5, 0.3])
_D = _GAMMA.size
_N = 89  # prime
_Z = _korobov_generating_vector(_D, 33, _N)


def _lattice_points(z, n):
    k = np.arange(n)[:, None]
    return np.mod(k * np.asarray(z)[None, :] / float(n), 1.0)


def _e2_general(z, n, gamma, alpha):
    """O(N²) general RKHS worst-case error with the α-smooth kernel."""
    pts = _lattice_points(z, n)
    tot = 0.0
    for k in range(n):
        diff = np.mod(pts - pts[k], 1.0)
        tot += float(np.prod(1.0 + gamma[None, :] * _korobov_kernel_omega_alpha(diff, alpha), axis=1).sum())
    return -1.0 + tot / (n * n)


def test_alpha1_bit_exact_reproduces_d112():
    """Backward-compat: smoothness=1 reproduces the D112 default bit-exactly (it uses the
    very same _korobov_kernel_omega code path)."""
    assert korobov_worst_case_error(_Z, _N, _GAMMA, smoothness=1) == korobov_worst_case_error(_Z, _N, _GAMMA)


def test_alpha2_spatial_equals_general_rkhs():
    """α=2: the O(N) spatial e² equals the O(N²) general RKHS double-sum form to machine
    precision (lattice shift-invariance, now with the B₄ kernel), and e²≥0."""
    e2_spatial = korobov_worst_case_error(_Z, _N, _GAMMA, smoothness=2) ** 2
    e2_general = _e2_general(_Z, _N, _GAMMA, 2)
    assert e2_spatial == pytest.approx(e2_general, abs=1e-12)
    assert e2_spatial >= -1e-12


def test_higher_smoothness_decays_faster():
    """The headline generalization payoff: a smoother space (higher α) gives a strictly
    faster lattice decay rate — mean error ratio per N-doubling increases with α."""
    def mean_ratio(alpha):
        es = [korobov_worst_case_error(_korobov_generating_vector(_D, 33, n), n, _GAMMA, smoothness=alpha)
              for n in (61, 127, 257, 521)]
        return float(np.mean([es[i] / es[i + 1] for i in range(len(es) - 1)]))
    r1, r2, r3 = mean_ratio(1), mean_ratio(2), mean_ratio(3)
    assert r2 > r1
    assert r3 > r2


def test_alpha3_nonnegative_and_finite():
    """α=3 (B₆ kernel) yields a non-negative, finite certificate."""
    e = korobov_worst_case_error(_Z, _N, _GAMMA, smoothness=3)
    assert e >= 0.0 and np.isfinite(e)


def test_kernel_closed_forms():
    """The α-kernel matches the closed-form Bernoulli polynomials: α=1 equals the D112
    ω=2π²B₂, and α=2 equals −(2π)⁴/4!·B₄ at a sample point."""
    x = np.array([0.3])
    assert _korobov_kernel_omega_alpha(x, 1) == pytest.approx(_korobov_kernel_omega(x), abs=1e-12)
    b4 = 0.3**4 - 2.0 * 0.3**3 + 0.3**2 - 1.0 / 30.0
    assert _korobov_kernel_omega_alpha(x, 2)[0] == pytest.approx(-((2.0 * np.pi) ** 4) / 24.0 * b4, abs=1e-12)


def test_alpha_korobov_guards():
    """Guards: smoothness < 1 and unsupported α (≥4) raise SolverError."""
    with pytest.raises(SolverError, match="korobov_smoothness_unsupported"):
        korobov_worst_case_error(_Z, _N, _GAMMA, smoothness=0)
    with pytest.raises(SolverError, match="korobov_smoothness_unsupported"):
        korobov_worst_case_error(_Z, _N, _GAMMA, smoothness=4)
    with pytest.raises(SolverError, match="korobov_smoothness_unsupported"):
        _korobov_kernel_omega_alpha(np.array([0.3]), 4)
