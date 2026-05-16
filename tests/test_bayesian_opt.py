"""Wave V tests for Bayesian-optimization-based parameter study driver."""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.core.bayesian_opt import (
    BayesianOptResult,
    ParameterSpec,
    bayesian_minimize,
    to_parameter_specs,
)


def test_parameter_spec_sample_in_bounds():
    """Sampled value must lie within [low, high]."""
    p = ParameterSpec(name="x", low=2.0, high=5.0)
    rng = np.random.default_rng(0)
    for _ in range(50):
        v = p.sample(rng)
        assert 2.0 <= v <= 5.0


def test_parameter_spec_log_scale_sample_in_bounds():
    """Log-scale sampling stays in (low, high) interval."""
    p = ParameterSpec(name="filter", low=0.5, high=5.0, log=True)
    rng = np.random.default_rng(1)
    for _ in range(50):
        v = p.sample(rng)
        assert 0.5 <= v <= 5.0


def test_parameter_spec_log_requires_positive_bounds():
    """Negative low + log=True must raise."""
    p = ParameterSpec(name="x", low=-1.0, high=5.0, log=True)
    with pytest.raises(ValueError, match="log-scale"):
        p.sample(np.random.default_rng(0))


def test_parameter_spec_clamp():
    """clamp() limits to [low, high]."""
    p = ParameterSpec(name="x", low=0.0, high=1.0)
    assert p.clamp(-0.5) == 0.0
    assert p.clamp(0.5) == 0.5
    assert p.clamp(2.0) == 1.0


def test_bayesian_minimize_finds_quadratic_minimum():
    """min (x - 0.6)² over [0, 1] should land near 0.6."""
    space = [ParameterSpec(name="x", low=0.0, high=1.0)]

    def obj(params: dict) -> float:
        return float((params["x"] - 0.6) ** 2)

    result = bayesian_minimize(space, obj, n_initial=10, n_iterations=20, seed=42)
    assert isinstance(result, BayesianOptResult)
    assert abs(result.best_params["x"] - 0.6) < 0.2
    assert result.best_objective < 0.04


def test_bayesian_minimize_handles_multiple_parameters():
    """2-D quadratic: min (x - 0.3)² + (y - 0.7)² over [0,1]²."""
    space = [
        ParameterSpec(name="x", low=0.0, high=1.0),
        ParameterSpec(name="y", low=0.0, high=1.0),
    ]

    def obj(params: dict) -> float:
        return float((params["x"] - 0.3) ** 2 + (params["y"] - 0.7) ** 2)

    result = bayesian_minimize(space, obj, n_initial=8, n_iterations=24, seed=7)
    # Loose: should be in the right quadrant
    assert abs(result.best_params["x"] - 0.3) < 0.3
    assert abs(result.best_params["y"] - 0.7) < 0.3


def test_bayesian_minimize_history_length():
    """History should contain n_initial + n_iterations entries."""
    space = [ParameterSpec(name="x", low=0.0, high=1.0)]
    obj = lambda p: float(p["x"])  # noqa: E731
    n_init, n_iter = 4, 10
    result = bayesian_minimize(space, obj, n_initial=n_init, n_iterations=n_iter, seed=0)
    assert len(result.history) == n_init + n_iter
    # Each entry must record params, objective, phase
    for entry in result.history:
        assert "params" in entry and "objective" in entry and "phase" in entry


def test_bayesian_minimize_first_entries_marked_initial():
    """The first n_initial entries are phase='initial'."""
    space = [ParameterSpec(name="x", low=0.0, high=1.0)]
    result = bayesian_minimize(space, lambda p: 0.0, n_initial=3, n_iterations=2, seed=0)
    assert result.history[0]["phase"] == "initial"
    assert result.history[2]["phase"] == "initial"
    assert result.history[3]["phase"] == "acquisition"


def test_bayesian_minimize_constant_objective():
    """If objective is constant, best_objective should equal that constant."""
    space = [ParameterSpec(name="x", low=0.0, high=1.0)]
    result = bayesian_minimize(space, lambda p: 5.0, n_initial=3, n_iterations=3, seed=0)
    assert result.best_objective == 5.0


def test_to_parameter_specs_roundtrip():
    """Parsing dict → ParameterSpec preserves all fields."""
    raw = [
        {"name": "filter_radius", "low": 0.5, "high": 3.0, "log": False},
        {"name": "volume_fraction", "low": 0.2, "high": 0.6},
    ]
    specs = to_parameter_specs(raw)
    assert len(specs) == 2
    assert specs[0].name == "filter_radius"
    assert specs[0].low == 0.5
    assert specs[0].log is False
    assert specs[1].log is False  # default


def test_bayesian_minimize_reproducible_with_seed():
    """Same seed → same best_params (within deterministic objective)."""
    space = [ParameterSpec(name="x", low=0.0, high=1.0)]

    def obj(params: dict) -> float:
        return float((params["x"] - 0.4) ** 2)

    r1 = bayesian_minimize(space, obj, n_initial=5, n_iterations=10, seed=99)
    r2 = bayesian_minimize(space, obj, n_initial=5, n_iterations=10, seed=99)
    assert r1.best_objective == r2.best_objective
    assert r1.best_params == r2.best_params
