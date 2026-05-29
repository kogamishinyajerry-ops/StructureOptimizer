"""v1.7 topology-optimization algorithm plug-in interface (Wave G).

This is the single boundary where the choice of optimization algorithm crosses
into the rest of the codebase. ``run_config`` / ``run_benchmark`` go through
a ``TopologyAlgorithm`` instance, so swapping SIMP ↔ BESO requires no changes
outside this directory.

Built-in algorithms:
- ``simp`` (default): density-based SIMP with optimality criteria update
  (Bendsøe 1989; Sigmund 99-line MATLAB). Smooth gradient flow.
- ``beso``: Bidirectional Evolutionary Structural Optimization (Huang & Xie
  2010). Discrete remove/add of elements per iteration; sensitivity-ranked.

Extension hooks (not implemented):
- ``level_set``: level-set method (Allaire / Wang) — distinct geometry repr.
- ``phase_field`` — Cahn-Hilliard-style smoothing of binary indicator.
- ``mma`` — Method of Moving Asymptotes; replace OC update inside SIMP.

Contract:
- Algorithm receives ``BenchmarkConfig`` + ``StructuredMesh``.
- Algorithm returns ``OptimizationResult`` with the same dataclass shape SIMP
  produces (so downstream demo/report/study code is algorithm-agnostic).
- Algorithms honor ``design_mask`` / ``frozen_solid_mask`` / ``void_mask``.
- Algorithms honor manufacturing constraints via ``apply_manufacturing_projections``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.core.simp import IterationMetric, OptimizationResult

IterationCallback = Callable[[int, IterationMetric, "np.ndarray"], None]
"""Observational per-iteration hook ``(iteration, IterationMetric, densities)``.

Used by the web runner to stream live convergence. ``None`` (the default
everywhere, including the CLI path) leaves behaviour unchanged.
"""


class TopologyAlgorithm(ABC):
    """Abstract base: given (config, mesh), return OptimizationResult."""

    name: str = "abstract"

    @abstractmethod
    def run(
        self,
        config: BenchmarkConfig,
        mesh: StructuredMesh,
        on_iteration: IterationCallback | None = None,
    ) -> OptimizationResult:
        """Run the algorithm to convergence (or max_iterations).

        Implementations may use ``config.optimization.algorithm`` is one of the
        registered keys; the dispatcher already routed here, so no double-check.

        ``on_iteration`` is an optional observational callback for live progress
        streaming; ``None`` preserves the original behaviour.
        """


class SimpAlgorithm(TopologyAlgorithm):
    """SIMP wrapper around ``core.simp.run_simp``."""

    name = "simp"

    def run(
        self,
        config: BenchmarkConfig,
        mesh: StructuredMesh,
        on_iteration: IterationCallback | None = None,
    ) -> OptimizationResult:
        from structure_optimizer.core.simp import run_simp

        return run_simp(config, mesh, on_iteration=on_iteration)


class BesoAlgorithm(TopologyAlgorithm):
    """BESO wrapper around ``core.beso.run_beso``."""

    name = "beso"

    def run(
        self,
        config: BenchmarkConfig,
        mesh: StructuredMesh,
        on_iteration: IterationCallback | None = None,
    ) -> OptimizationResult:
        from structure_optimizer.core.beso import run_beso

        # BESO does not yet support live streaming; the callback is accepted for
        # signature parity with the plug-in contract and ignored.
        return run_beso(config, mesh)


_REGISTRY: dict[str, type[TopologyAlgorithm]] = {
    SimpAlgorithm.name: SimpAlgorithm,
    BesoAlgorithm.name: BesoAlgorithm,
}


def available_algorithms() -> list[str]:
    """Return alphabetised list of registered algorithm names."""
    return sorted(_REGISTRY)


def get_algorithm(name: str | None) -> TopologyAlgorithm:
    """Factory: return a ``TopologyAlgorithm`` instance for an algorithm name.

    ``None`` / empty string defaults to ``"simp"``. Unknown names raise
    ``ValueError`` listing valid options.
    """
    key = (name or "simp").lower()
    impl = _REGISTRY.get(key)
    if impl is None:
        raise ValueError(f"Unknown algorithm '{name}'. Available: {available_algorithms()}")
    return impl()
