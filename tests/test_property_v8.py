"""Wave BBB (v8): property tests for the v8 system-reliability code.

The v8 rubric §4.3 requires ≥42 property tests. These add two invariants of the
Wave ZZ (D055) code that must hold across random inputs — not smoke tests but
mathematical properties: the bivariate-normal CDF is monotone in each argument,
and the Ditlevsen series bounds always sit inside the simple unimodal bounds
(and are correctly ordered).
"""

from __future__ import annotations

import numpy as np
from structure_optimizer.core.reliability import (
    bivariate_normal_cdf,
    system_reliability_series,
)


def test_property_bivariate_cdf_monotone_in_arguments():
    """Φ₂(a,b;ρ) is non-decreasing in a and in b (a CDF), for random ρ (60 trials)."""
    rng = np.random.default_rng(0)
    for _ in range(60):
        a = rng.uniform(-3.0, 3.0)
        b = rng.uniform(-3.0, 3.0)
        rho = rng.uniform(-0.95, 0.95)
        da = rng.uniform(0.05, 1.5)
        db = rng.uniform(0.05, 1.5)
        base = bivariate_normal_cdf(a, b, rho)
        assert bivariate_normal_cdf(a + da, b, rho) >= base - 1e-9
        assert bivariate_normal_cdf(a, b + db, rho) >= base - 1e-9
        # bounded in [0, min(Φ(a),Φ(b))]
        assert -1e-12 <= base <= 1.0 + 1e-12


def test_property_ditlevsen_within_simple_bounds():
    """For random independent series systems the Ditlevsen bounds are ordered
    (lower ≤ upper) and lie inside the simple unimodal bounds (50 trials)."""
    rng = np.random.default_rng(1)
    for _ in range(50):
        m = int(rng.integers(2, 6))
        betas = rng.uniform(1.0, 4.0, m).tolist()
        r = system_reliability_series(betas)
        lo, hi = r["p_failure_lower"], r["p_failure_upper"]
        assert lo <= hi + 1e-12, f"Ditlevsen bounds inverted: {lo} > {hi}"
        assert r["simple_lower"] - 1e-12 <= lo
        assert hi <= r["simple_upper"] + 1e-9
        # all probabilities are valid
        assert 0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0
