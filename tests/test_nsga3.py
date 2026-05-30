"""Wave HH (v6): NSGA-III for ≥3 objectives.

Quantitative anchors:
- Das-Dennis reference-point counts are exact combinatorials C(p+m−1, m−1) and
  lie on the unit simplex;
- on DTLZ2 (whose true 3-objective Pareto front is the unit-sphere octant
  Σf_i² = 1) the evolved front converges onto that sphere.
"""

from __future__ import annotations

from math import comb

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.pareto_nsga import (
    _non_dominated_sort,
    das_dennis_reference_points,
    nsga3,
)


def _dtlz2(x: np.ndarray, n_obj: int = 3) -> tuple[float, ...]:
    """DTLZ2 benchmark — Pareto-optimal iff g = 0, where Σf_i² = 1."""
    x = np.asarray(x, dtype=float)
    xm = x[n_obj - 1 :]
    g = float(np.sum((xm - 0.5) ** 2))
    f = []
    for i in range(n_obj):
        val = 1.0 + g
        for j in range(n_obj - 1 - i):
            val *= np.cos(x[j] * np.pi / 2.0)
        if i > 0:
            val *= np.sin(x[n_obj - 1 - i] * np.pi / 2.0)
        f.append(float(val))
    return tuple(f)


def test_das_dennis_count_three_objective():
    pts = das_dennis_reference_points(3, 12)
    assert pts.shape == (comb(12 + 2, 2), 3)  # C(14,2) = 91
    assert np.allclose(pts.sum(axis=1), 1.0)
    assert (pts >= 0).all()


def test_das_dennis_count_small_and_four_objective():
    assert das_dennis_reference_points(3, 4).shape[0] == comb(6, 2)  # 15
    assert das_dennis_reference_points(4, 3).shape[0] == comb(6, 3)  # 20


def test_das_dennis_rejects_bad_args():
    with pytest.raises(SolverError, match="n_obj_too_small"):
        das_dennis_reference_points(1, 4)
    with pytest.raises(SolverError, match="n_divisions_too_small"):
        das_dennis_reference_points(3, 0)


def test_nsga3_dtlz2_converges_to_unit_sphere():
    """The evolved 3-objective front lands on the DTLZ2 unit sphere Σf_i² = 1."""
    n_obj, k = 3, 4
    n_vars = n_obj - 1 + k
    bl, bu = np.zeros(n_vars), np.ones(n_vars)
    rng = np.random.default_rng(0)
    init = np.array([_dtlz2(x, n_obj) for x in rng.uniform(bl, bu, size=(200, n_vars))])
    init_radius = float(np.mean(np.sum(init**2, axis=1)))

    front = nsga3(
        lambda x: _dtlz2(x, n_obj),
        n_vars,
        bl,
        bu,
        n_obj=n_obj,
        n_divisions=12,
        n_generations=80,
        rng_seed=0,
    )
    radii = np.sum(front.objectives**2, axis=1)
    mean_radius = float(np.mean(radii))
    assert mean_radius < 1.2, f"front not converged to sphere: mean Σf²={mean_radius:.3f}"
    assert mean_radius < init_radius, "front did not improve over random init"
    assert front.n_front >= 10, f"front too small: {front.n_front}"


def test_nsga3_front_is_nondominated():
    n_obj, k = 3, 3
    n_vars = n_obj - 1 + k
    front = nsga3(
        lambda x: _dtlz2(x, n_obj),
        n_vars,
        np.zeros(n_vars),
        np.ones(n_vars),
        n_obj=n_obj,
        n_divisions=8,
        n_generations=40,
        rng_seed=1,
    )
    fronts = _non_dominated_sort(front.objectives)
    assert len(fronts[0]) == front.objectives.shape[0], "returned front contains dominated points"


def test_nsga3_three_objective_diversity():
    """The evolved front spreads across the objective space (not collapsed)."""
    n_obj, k = 3, 3
    n_vars = n_obj - 1 + k
    front = nsga3(
        lambda x: _dtlz2(x, n_obj),
        n_vars,
        np.zeros(n_vars),
        np.ones(n_vars),
        n_obj=n_obj,
        n_divisions=10,
        n_generations=60,
        rng_seed=2,
    )
    spreads = front.objectives.max(axis=0) - front.objectives.min(axis=0)
    assert (spreads > 0.3).all(), f"front collapsed, per-objective spread={spreads}"


def test_nsga3_rejects_single_objective():
    with pytest.raises(SolverError, match="n_obj_too_small"):
        nsga3(lambda x: (x[0],), 2, np.zeros(2), np.ones(2), n_obj=1)
