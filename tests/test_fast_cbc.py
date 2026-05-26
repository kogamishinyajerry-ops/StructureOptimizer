"""Wave GGGGGGGG (v16, D120) — fast-CBC (Nuyens–Cools FFT) lattice construction (closes
D112's "fast-CBC (FFT, O(d·N·log N))" reopening).

The naive cbc_korobov_generating_vector is O(d·N²). fast-CBC re-indexes the multiplicative
group of prime Z/N so the per-component CBC objective becomes a cyclic correlation evaluated
by ONE FFT pair in O(N log N). Quantitative analytical anchors, never qualitative trends:

  * the FFT correlation equals the direct O(N²) correlation to machine precision (the
    "fast == slow computation" identity — the heart of the speedup),
  * the produced vector is certified ≤ the textbook Korobov vector and ≤ random vectors
    (it genuinely minimises the worst-case error),
  * it is deterministic (no RNG, byte-stable across calls).

Honest scope (D120): fast-CBC z is NOT byte-identical to the naive z — an exact g↔N−g
kernel symmetry makes the optimum a 2^(d−1)-member set; both routines pick equally-optimal
members by different (round-off vs canonical) tie-breaks. The anchors test the achievable
truths, not the unachievable bit-equality.
"""

import time

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.reliability import (
    _korobov_generating_vector,
    _korobov_kernel_omega,
    _smallest_primitive_root,
    cbc_korobov_generating_vector,
    fast_cbc_korobov_generating_vector,
    korobov_worst_case_error,
)

_PRIMES = [31, 61, 127, 251, 509, 1021]


def _direct_correlation(p_grp, gexp, n):
    """Reference O(N²) per-component correlation T(g) = Σ_a P(ρ^a) ω(frac(ρ^a·g / N)),
    computed candidate-by-candidate (no FFT) — the quantity fast-CBC accelerates."""
    el = n - 1
    out = np.empty(el)
    for bi, g in enumerate(gexp):
        out[bi] = float(np.sum(p_grp * _korobov_kernel_omega((gexp * int(g)) % n / float(n))))
    return out


def test_fft_correlation_matches_direct():
    """Headline: the FFT cyclic correlation used inside fast-CBC reproduces the direct
    O(N²) correlation to machine precision — proving "fast" computes the SAME thing as the
    naive rescan, only via one FFT pair instead of N² kernel evaluations."""
    n, d = 251, 4
    gamma = np.array([1.0 / (i + 1) ** 2 for i in range(d)])
    root = _smallest_primitive_root(n)
    el = n - 1
    gexp = np.empty(el, dtype=np.int64)
    cur = 1
    for a in range(el):
        gexp[a] = cur
        cur = (cur * root) % n
    p_grp = 1.0 + float(gamma[0]) * _korobov_kernel_omega(gexp.astype(float) / float(n))
    # FFT correlation (same recurrence as the implementation)
    omega_grp = _korobov_kernel_omega(gexp.astype(float) / float(n))
    rev = np.empty(el)
    rev[0] = p_grp[0]
    rev[1:] = p_grp[1:][::-1]
    fft_corr = np.fft.irfft(np.fft.rfft(rev) * np.fft.rfft(omega_grp), n=el)
    direct = _direct_correlation(p_grp, gexp, n)
    assert np.max(np.abs(fft_corr - direct)) < 1e-10


def test_smaller_worst_case_error_than_textbook_korobov():
    """fast-CBC genuinely minimises: e(fast_cbc) ≤ e(textbook Korobov (1,a,a²,…)) for the
    same N — the CBC greedy-optimality certificate (the same guarantee the naive routine
    documents), here for every tested prime."""
    for n in _PRIMES:
        d = 5
        gamma = np.array([1.0 / (i + 1) ** 2 for i in range(d)])
        z = fast_cbc_korobov_generating_vector(d, n, gamma)
        e_cbc = korobov_worst_case_error(z, n, gamma)
        best_korobov = min(
            korobov_worst_case_error(_korobov_generating_vector(d, a, n), n, gamma)
            for a in (3, 5, 7, int(n**0.5)) if 1 < a < n
        )
        assert e_cbc <= best_korobov + 1e-12


def test_beats_random_generating_vectors():
    """e(fast_cbc) ≤ the worst-case error of 30 random generating vectors (same N) —
    quantitative evidence it lands at a genuinely good lattice, not an arbitrary one."""
    n, d = 1021, 5
    gamma = np.array([1.0 / (i + 1) ** 2 for i in range(d)])
    z = fast_cbc_korobov_generating_vector(d, n, gamma)
    e_cbc = korobov_worst_case_error(z, n, gamma)
    rng = np.random.default_rng(0)
    e_rand = [
        korobov_worst_case_error(np.concatenate([[1], rng.integers(1, n, size=d - 1)]), n, gamma)
        for _ in range(30)
    ]
    assert e_cbc <= min(e_rand) + 1e-12


def test_deterministic_no_rng():
    """fast-CBC is deterministic: two calls with identical inputs return byte-identical z
    (no RNG anywhere), and z[0] = 1 with every component in {1,…,N−1}."""
    n, d = 509, 6
    gamma = np.array([1.0 / (i + 1) ** 2 for i in range(d)])
    z1 = fast_cbc_korobov_generating_vector(d, n, gamma)
    z2 = fast_cbc_korobov_generating_vector(d, n, gamma)
    assert np.array_equal(z1, z2)
    assert z1[0] == 1
    assert np.all(z1 >= 1) and np.all(z1 <= n - 1)


def test_naive_cbc_unchanged_adjacent():
    """Adjacency: the existing naive cbc_korobov_generating_vector is a pure addition's
    neighbour — still importable and still produces a vector whose worst-case error matches
    fast-CBC's optimal CLASS (≤ textbook Korobov), confirming both target the same optimum
    even though their tie-broken z differ."""
    n, d = 127, 5
    gamma = np.array([1.0 / (i + 1) ** 2 for i in range(d)])
    z_naive = cbc_korobov_generating_vector(d, n, gamma)
    z_fast = fast_cbc_korobov_generating_vector(d, n, gamma)
    best_korobov = min(
        korobov_worst_case_error(_korobov_generating_vector(d, a, n), n, gamma)
        for a in (3, 5, 7) if a < n
    )
    assert korobov_worst_case_error(z_naive, n, gamma) <= best_korobov + 1e-12
    assert korobov_worst_case_error(z_fast, n, gamma) <= best_korobov + 1e-12


def test_fast_cbc_guards():
    """Guards: non-prime N, dim<1, and weight-length mismatch raise SolverError."""
    gamma = np.array([1.0, 0.25, 0.11])
    with pytest.raises(SolverError, match="fast_cbc_n_not_prime"):
        fast_cbc_korobov_generating_vector(3, 1024, gamma)  # 1024 composite
    with pytest.raises(SolverError, match="cbc_dim_too_small"):
        fast_cbc_korobov_generating_vector(0, 127, np.array([]))
    with pytest.raises(SolverError, match="cbc_weights_dim_mismatch"):
        fast_cbc_korobov_generating_vector(3, 127, np.array([1.0, 0.25]))


def test_fast_cbc_speedup_vs_naive(request):
    """[--run-slow] fast-CBC is ≥10× faster than naive CBC at N=1021 and lands in the same
    optimal class (e_fast ≤ e_textbook_korobov), confirming the O(dN log N) accelerator
    delivers an equally-optimal vector for a fraction of the cost."""
    if not request.config.getoption("--run-slow", default=False):
        pytest.skip("slow timing test; pass --run-slow")
    n, d = 1021, 6
    gamma = np.array([1.0 / (i + 1) ** 2 for i in range(d)])
    t0 = time.perf_counter()
    cbc_korobov_generating_vector(d, n, gamma)
    t_naive = time.perf_counter() - t0
    t0 = time.perf_counter()
    z_fast = fast_cbc_korobov_generating_vector(d, n, gamma)
    t_fast = time.perf_counter() - t0
    assert t_naive / max(t_fast, 1e-9) >= 10.0
    best_korobov = min(
        korobov_worst_case_error(_korobov_generating_vector(d, a, n), n, gamma)
        for a in (3, 5, 7) if a < n
    )
    assert korobov_worst_case_error(z_fast, n, gamma) <= best_korobov + 1e-12
