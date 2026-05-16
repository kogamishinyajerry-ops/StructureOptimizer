"""Wave DD: NSGA-II Pareto-front tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.pareto_nsga import (
    ParetoFront,
    nsga_ii,
    render_pareto,
)


def _zdt1(x):
    """Classic bi-objective benchmark (Deb et al. 2002 §3.1)."""
    n = len(x)
    f1 = float(x[0])
    g = 1.0 + 9.0 * float(np.sum(x[1:])) / max(n - 1, 1)
    h = 1.0 - np.sqrt(f1 / g) if g > 0 else 1.0
    f2 = g * h
    return (f1, f2)


def test_nsga_ii_returns_pareto_front_for_zdt1():
    """ZDT1: the Pareto front is f1 + f2 = 1 with x[1:] = 0. We don't
    require exact recovery (NSGA-II is heuristic), just non-empty front
    + objectives in reasonable bounds."""
    front = nsga_ii(_zdt1, n_vars=5, bounds_lower=np.zeros(5), bounds_upper=np.ones(5),
                    population_size=30, n_generations=20, rng_seed=0)
    assert isinstance(front, ParetoFront)
    assert front.n_front >= 3
    assert front.objectives.shape[1] == 2
    assert (front.objectives[:, 0] >= 0).all()
    # Pareto-optimal points should be finite + non-NaN. NSGA-II is
    # heuristic — exact convergence to the analytical front requires
    # many more generations than we want to spend in CI.
    assert np.all(np.isfinite(front.objectives))


def test_nsga_ii_reproducible_with_same_seed():
    front_a = nsga_ii(_zdt1, n_vars=4, bounds_lower=np.zeros(4), bounds_upper=np.ones(4),
                      population_size=20, n_generations=10, rng_seed=42)
    front_b = nsga_ii(_zdt1, n_vars=4, bounds_lower=np.zeros(4), bounds_upper=np.ones(4),
                      population_size=20, n_generations=10, rng_seed=42)
    np.testing.assert_array_equal(front_a.objectives, front_b.objectives)


def test_nsga_ii_rejects_small_population():
    with pytest.raises(SolverError, match="population_too_small"):
        nsga_ii(_zdt1, n_vars=3, bounds_lower=np.zeros(3), bounds_upper=np.ones(3), population_size=2)


def test_render_pareto_writes_html_with_svg():
    front = nsga_ii(_zdt1, n_vars=4, bounds_lower=np.zeros(4), bounds_upper=np.ones(4),
                    population_size=20, n_generations=10, rng_seed=0)
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        path = Path(f.name)
    try:
        render_pareto(front, str(path), title="ZDT1 Pareto")
        content = path.read_text()
        assert "<!DOCTYPE html>" in content
        assert "<svg" in content
        assert "ZDT1 Pareto" in content
        assert str(front.n_front) in content
    finally:
        path.unlink()


def test_render_pareto_handles_empty_front():
    """Edge case: an empty front shouldn't crash."""
    empty = ParetoFront(objectives=np.zeros((0, 2)), decisions=np.zeros((0, 2)), n_front=0, rank_history=[])
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        path = Path(f.name)
    try:
        render_pareto(empty, str(path))
        content = path.read_text()
        assert "<!DOCTYPE html>" in content
    finally:
        path.unlink()


def test_property_pareto_front_is_non_dominated():
    """All Pareto-optimal points should be mutually non-dominated."""
    front = nsga_ii(_zdt1, n_vars=4, bounds_lower=np.zeros(4), bounds_upper=np.ones(4),
                    population_size=24, n_generations=15, rng_seed=1)
    objs = front.objectives
    for i in range(front.n_front):
        for j in range(front.n_front):
            if i == j:
                continue
            # j must not dominate i (≤ in both and < in at least one)
            le_all = np.all(objs[j] <= objs[i])
            lt_any = np.any(objs[j] < objs[i])
            assert not (le_all and lt_any), f"point {j} dominates {i}"
