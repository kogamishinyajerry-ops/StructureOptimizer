"""Milestone 3 — apply user-supplied overrides to a benchmark config before a run.

The problem-definition editor lets users tweak a small, safe subset of the
optimization parameters, mesh resolution, and point loads on top of a built-in
benchmark. This module is the single enforcement point for that subset:

- ``RunOverrides`` shape (all keys optional)::

    {
      "optimization": {"volume_fraction": float, "penalty": float,
                       "filter_radius": float, "max_iterations": int},
      "mesh": {"nelx": int, "nely": int},
      "loads": [{"selector": str, "fx": float, "fy": float}, ...],
    }

- Server-side caps (``ValueError`` -> HTTP 400 with a user-facing message):
  ``nelx <= 160``, ``nely <= 160``, ``nelx*nely <= 12000``,
  ``max_iterations <= 200``, and every load ``selector`` must be one of the 13
  named selectors.

``apply_overrides`` patches the frozen config via ``dataclasses.replace``,
enforces the caps, then runs ``validate_config`` so any deeper engine invariant
violation surfaces as ``ConfigError`` (also mapped to HTTP 400 by the endpoint).

Benchmarks that drive the optimizer from ``load_cases`` are not load-editable in
M3, so ``overrides["loads"]`` is ignored when ``config.load_cases`` is non-empty.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from structure_optimizer.core.config import (
    BenchmarkConfig,
    MeshConfig,
    validate_config,
)

# The 13 named selectors the editor exposes (mirrors the engine's selector set).
VALID_SELECTORS: tuple[str, ...] = (
    "left_edge",
    "right_edge",
    "top_edge",
    "bottom_edge",
    "left_mid",
    "right_mid",
    "top_mid",
    "bottom_mid",
    "top_left",
    "top_right",
    "bottom_left",
    "bottom_right",
    "center",
)

# Hard server-side caps (keep the interactive workbench responsive + bounded).
NELX_MAX = 160
NELY_MAX = 160
ELEMENTS_MAX = 12000
MAX_ITERATIONS_MAX = 200


def apply_overrides(config: BenchmarkConfig, overrides: dict[str, Any] | None) -> BenchmarkConfig:
    """Return a new ``BenchmarkConfig`` with the editor overrides applied.

    Raises ``ValueError`` for cap/selector violations (user-facing message) and
    lets ``ConfigError`` from ``validate_config`` propagate. With no overrides the
    config is returned unchanged.
    """
    if not overrides:
        return config

    opt_override = overrides.get("optimization")
    if opt_override:
        config = replace(config, optimization=_apply_optimization(config, opt_override))

    mesh_override = overrides.get("mesh")
    if mesh_override:
        config = replace(config, mesh=_apply_mesh(config, mesh_override))

    loads_override = overrides.get("loads")
    if loads_override is not None and not config.load_cases:
        config = replace(config, loads=_apply_loads(loads_override))

    validate_config(config)
    return config


def _apply_optimization(config: BenchmarkConfig, override: dict[str, Any]) -> Any:
    opt = config.optimization
    new_values: dict[str, Any] = {}
    if "volume_fraction" in override:
        new_values["volume_fraction"] = float(override["volume_fraction"])
    if "penalty" in override:
        new_values["penalty"] = float(override["penalty"])
    if "filter_radius" in override:
        new_values["filter_radius"] = float(override["filter_radius"])
    if "max_iterations" in override:
        max_iterations = int(override["max_iterations"])
        if max_iterations > MAX_ITERATIONS_MAX:
            raise ValueError(f"max_iterations {max_iterations} exceeds cap of {MAX_ITERATIONS_MAX}")
        new_values["max_iterations"] = max_iterations
    return replace(opt, **new_values)


def _apply_mesh(config: BenchmarkConfig, override: dict[str, Any]) -> MeshConfig:
    nelx = int(override["nelx"]) if "nelx" in override else config.mesh.nelx
    nely = int(override["nely"]) if "nely" in override else config.mesh.nely
    if nelx > NELX_MAX:
        raise ValueError(f"nelx {nelx} exceeds cap of {NELX_MAX}")
    if nely > NELY_MAX:
        raise ValueError(f"nely {nely} exceeds cap of {NELY_MAX}")
    if nelx * nely > ELEMENTS_MAX:
        raise ValueError(f"mesh has {nelx * nely} elements, exceeding cap of {ELEMENTS_MAX}")
    # Rebuild fresh (width/height=None) so unit cells re-derive to square.
    return MeshConfig(type=config.mesh.type, nelx=nelx, nely=nely)


def _apply_loads(override: list[Any]) -> list[dict[str, Any]]:
    loads: list[dict[str, Any]] = []
    for entry in override:
        selector = entry.get("selector")
        if selector not in VALID_SELECTORS:
            raise ValueError(f"unknown selector '{selector}'; must be one of {', '.join(VALID_SELECTORS)}")
        loads.append(
            {
                "selector": selector,
                "fx": float(entry.get("fx", 0.0)),
                "fy": float(entry.get("fy", 0.0)),
            }
        )
    return loads
