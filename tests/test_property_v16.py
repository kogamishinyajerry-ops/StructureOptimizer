"""Wave HHHHHHHH (v16, D121): property tests for the v16 deep-embedding milestone.

Randomised property checks complementing the per-wave anchor tests:
- the fast-CBC (FFT) generating vector's worst-case error never exceeds the textbook
  Korobov vector's, for arbitrary product weights and primes (D120);
- copula k-out-of-n system reliability is non-increasing in k and bounded by the
  series (k=1) and parallel (k=m) ends, for arbitrary copula strength and betas (D119).
"""

from __future__ import annotations

import numpy as np
from structure_optimizer.core.reliability import (
    _korobov_generating_vector,
    fast_cbc_korobov_generating_vector,
    gumbel_d_copula,
    korobov_worst_case_error,
    system_reliability_k_out_of_n_copula,
    system_reliability_parallel_copula,
    system_reliability_series_copula,
)

_PRIMES = [61, 127, 251, 509, 1021]


def test_property_fast_cbc_never_worse_than_korobov():
    """For arbitrary positive product weights and several primes, the fast-CBC lattice's
    deterministic worst-case error is ≤ the textbook Korobov vector's (greedy-optimality
    certificate, D120) — to within a benign round-off slack."""
    rng = np.random.default_rng(160)
    for _ in range(10):
        n = int(rng.choice(_PRIMES))
        d = int(rng.integers(2, 6))
        gamma = rng.uniform(0.05, 1.0, size=d)
        z_fast = fast_cbc_korobov_generating_vector(d, n, gamma)
        e_fast = korobov_worst_case_error(z_fast, n, gamma)
        best_kor = min(
            korobov_worst_case_error(_korobov_generating_vector(d, a, n), n, gamma)
            for a in (3, 5, 7, int(n**0.5))
            if 1 < a < n
        )
        assert e_fast <= best_kor + 1e-12


def test_property_k_out_of_n_monotone_and_bracketed():
    """For arbitrary Gumbel copula strength and reliability indices, P(≥k fail) is
    non-increasing in k, every value is a valid probability, and the series (k=1) /
    parallel (k=m) ends bracket the family (D119)."""
    rng = np.random.default_rng(161)
    for _ in range(12):
        m = int(rng.integers(2, 6))
        betas = rng.uniform(1.0, 3.5, size=m)
        cop = gumbel_d_copula(m, float(rng.uniform(1.0, 4.0)))
        ks = [system_reliability_k_out_of_n_copula(betas, cop, k) for k in range(1, m + 1)]
        assert all(0.0 <= x <= 1.0 for x in ks)
        assert all(ks[i] >= ks[i + 1] - 1e-12 for i in range(len(ks) - 1))
        assert abs(ks[0] - system_reliability_series_copula(betas, cop)) < 1e-10
        assert abs(ks[-1] - system_reliability_parallel_copula(betas, cop)) < 1e-10
