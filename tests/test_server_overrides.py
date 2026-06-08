"""Finiteness enforcement in the override layer (server/overrides.py).

NaN/Infinity slip past ``validate_config``'s range guards (``nan <= 0`` and
``inf <= 0`` are both False, ``nan != 0`` is True), so the override layer — the
documented single enforcement point for the editable parameter subset — must
reject them up front with a clean ``ValueError`` (mapped to HTTP 400 by the
endpoint) instead of letting a poisoned config reach the SIMP engine.
"""

from __future__ import annotations

import math

import pytest
from server.overrides import apply_overrides
from structure_optimizer.benchmarks.registry import load_benchmark


def _cfg():
    # cantilever/smoke has empty load_cases, so point loads ARE editable here.
    return load_benchmark("cantilever", preset="smoke")


@pytest.mark.parametrize("field", ["volume_fraction", "penalty", "filter_radius"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_optimization_override_rejected(field: str, bad: float) -> None:
    with pytest.raises(ValueError, match=f"{field} must be a finite number"):
        apply_overrides(_cfg(), {"optimization": {field: bad}})


@pytest.mark.parametrize("comp", ["fx", "fy"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_nonfinite_load_override_rejected(comp: str, bad: float) -> None:
    load: dict[str, object] = {"selector": "right_mid", "fx": 0.0, "fy": -1.0}
    load[comp] = bad
    with pytest.raises(ValueError, match=f"{comp} must be a finite number"):
        apply_overrides(_cfg(), {"loads": [load]})


def test_finite_overrides_still_applied() -> None:
    """The guard is strictly narrowing — legitimate finite values pass through."""
    cfg = apply_overrides(_cfg(), {"optimization": {"penalty": 3.5, "filter_radius": 1.2}})
    assert cfg.optimization.penalty == 3.5
    assert cfg.optimization.filter_radius == 1.2
    assert math.isfinite(cfg.optimization.penalty)


def test_max_iterations_below_benchmark_minimum_rejected() -> None:
    """The editor exposes max_iterations but NOT min_iterations. Lowering max below
    the benchmark's min must raise a message phrased in the editor's own terms,
    not the raw validate_config ConfigError ('min_iterations must be in
    [1, max_iterations]') that names a parameter the user never saw."""
    cfg = _cfg()
    too_low = cfg.optimization.min_iterations - 1
    assert too_low >= 1  # stay above the positivity guard so we hit the min check
    with pytest.raises(ValueError, match=r"is below this benchmark's minimum"):
        apply_overrides(cfg, {"optimization": {"max_iterations": too_low}})


def test_max_iterations_at_minimum_allowed() -> None:
    """Boundary: max_iterations == min_iterations is valid (min > max is the error)."""
    cfg = _cfg()
    out = apply_overrides(cfg, {"optimization": {"max_iterations": cfg.optimization.min_iterations}})
    assert out.optimization.max_iterations == cfg.optimization.min_iterations
