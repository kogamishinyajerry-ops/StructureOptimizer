"""Wave GGGGGGG (v15, D112) — deterministic CBC-lattice worst-case error bound.

Closes D099's reopening ("CBC-certified lattice deterministic error bound"). Quantitative
analytical anchors (the O(N) spatial worst-case-error formula equals the O(N²) general
RKHS form exactly; the deterministic Koksma–Hlawka inequality holds), never qualitative
trends.

UNLIKE `genz_mvn_cdf_lattice`'s *randomised* `std_error` (a statistical estimate from
random shifts), `korobov_worst_case_error` is a **deterministic, a-priori certificate**
that holds for every function in the space's unit ball, with **no RNG / no seed** — so it
is byte-exact reproducible. The "constraint binds" evidence (v15): the CBC vector
*changes* the textbook Korobov vector and *lowers* the certified bound.
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    _korobov_generating_vector,
    _korobov_kernel_omega,
    cbc_korobov_generating_vector,
    korobov_worst_case_error,
)

_GAMMA = np.array([0.7, 0.5, 0.3])
_D = _GAMMA.size
_N = 89  # prime


def _lattice_points(z, n):
    k = np.arange(n)[:, None]
    return np.mod(k * np.asarray(z)[None, :] / float(n), 1.0)


def _e2_general(z, n, gamma):
    """O(N²) general RKHS worst-case error: −1 + (1/N²) ΣΣ K(t_k − t_l)."""
    pts = _lattice_points(z, n)
    tot = 0.0
    for k in range(n):
        diff = np.mod(pts - pts[k], 1.0)
        tot += float(np.prod(1.0 + gamma[None, :] * _korobov_kernel_omega(diff), axis=1).sum())
    return -1.0 + tot / (n * n)


def test_spatial_form_equals_general_rkhs_form():
    """Headline: the O(N) lattice spatial formula equals the O(N²) general RKHS
    double-sum form to machine precision (lattice shift-invariance collapses ΣΣ → Σ)."""
    z = _korobov_generating_vector(_D, 33, _N)
    e2_spatial = korobov_worst_case_error(z, _N, _GAMMA) ** 2
    e2_general = _e2_general(z, _N, _GAMMA)
    assert e2_spatial == pytest.approx(e2_general, abs=1e-12)
    assert e2_spatial >= -1e-12  # squared error is non-negative


def test_cbc_beats_korobov_and_is_deterministic():
    """Binding evidence: the CBC vector CHANGES the textbook Korobov vector and gives a
    strictly-not-worse certified bound; and it is fully deterministic (byte-exact on
    repeat — no RNG)."""
    z_cbc = cbc_korobov_generating_vector(_D, _N, _GAMMA)
    z_kor = _korobov_generating_vector(_D, 33, _N)
    e_cbc = korobov_worst_case_error(z_cbc, _N, _GAMMA)
    e_kor = korobov_worst_case_error(z_kor, _N, _GAMMA)
    assert e_cbc <= e_kor + 1e-15  # CBC is greedily optimal ⟹ never worse
    assert not np.array_equal(z_cbc, z_kor)  # it genuinely changes the vector
    assert np.array_equal(z_cbc, cbc_korobov_generating_vector(_D, _N, _GAMMA))  # deterministic


def test_koksma_hlawka_deterministic_bound_holds():
    """The deterministic certificate in action: for f = K(·,t) (integral 1, norm √K(t,t))
    the quadrature error obeys |Q_N f − 1| ≤ e(z)·‖f‖ for every anchor t — no randomness."""
    z = cbc_korobov_generating_vector(_D, _N, _GAMMA)
    e = korobov_worst_case_error(z, _N, _GAMMA)
    norm_f = np.sqrt(float(np.prod(1.0 + _GAMMA * _korobov_kernel_omega(np.zeros(_D)))))
    pts = _lattice_points(z, _N)
    rng = np.random.default_rng(1)
    for _ in range(6):
        t = rng.random(_D)
        diff = np.mod(pts - t[None, :], 1.0)
        q_f = float(np.prod(1.0 + _GAMMA[None, :] * _korobov_kernel_omega(diff), axis=1).mean())
        assert abs(q_f - 1.0) <= e * norm_f + 1e-12


def test_worst_case_error_decreases_with_n():
    """Convergence: refining N (with a CBC vector each time) lowers the certified bound
    monotonically — a deterministic O(N^{−1+δ}) decay, not a noisy MC trend."""
    es = [korobov_worst_case_error(cbc_korobov_generating_vector(_D, n, _GAMMA), n, _GAMMA) for n in (31, 61, 127, 257)]
    assert all(es[i] > es[i + 1] for i in range(len(es) - 1))


def test_independence_weights_zero_is_exact():
    """All-zero weights ⟹ the space is one-dimensional (only constants) ⟹ the lattice
    integrates exactly ⟹ e(z) = 0 to machine precision (a degenerate sanity anchor)."""
    z = _korobov_generating_vector(_D, 33, _N)
    assert korobov_worst_case_error(z, _N, np.zeros(_D)) == pytest.approx(0.0, abs=1e-12)


def test_deterministic_qmc_guards():
    """Guards: too-few points, z/weights length mismatch, negative weight, CBC dim<1,
    CBC weights mismatch all raise SolverError."""
    with pytest.raises(SolverError, match="korobov_wce_too_few_points"):
        korobov_worst_case_error(np.array([1, 1]), 1, np.array([0.5, 0.5]))
    with pytest.raises(SolverError, match="korobov_wce_dim_mismatch"):
        korobov_worst_case_error(np.array([1, 7]), _N, np.array([0.5]))
    with pytest.raises(SolverError, match="korobov_wce_negative_weight"):
        korobov_worst_case_error(np.array([1, 7]), _N, np.array([0.5, -0.1]))
    with pytest.raises(SolverError, match="cbc_dim_too_small"):
        cbc_korobov_generating_vector(0, _N, np.array([]))
    with pytest.raises(SolverError, match="cbc_weights_dim_mismatch"):
        cbc_korobov_generating_vector(3, _N, np.array([0.5, 0.5]))
    with pytest.raises(SolverError, match="korobov_wce_too_few_points"):
        cbc_korobov_generating_vector(3, 1, np.array([0.5, 0.5, 0.5]))
    with pytest.raises(SolverError, match="korobov_wce_negative_weight"):
        cbc_korobov_generating_vector(3, _N, np.array([0.5, -0.1, 0.5]))
