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
