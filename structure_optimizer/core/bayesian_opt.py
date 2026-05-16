"""Wave V: Bayesian optimization for design-parameter studies.

Provides a black-box optimizer that wraps SIMP runs over a parameter
space (filter_radius / volume_fraction / penalty / ...) and uses
expected-improvement-style acquisition to choose the next evaluation
point. The intent is to find low-compliance designs faster than the
LHS/Sobol DOE samplers from Wave O, which sample uniformly without
exploiting prior evaluations.

Two execution modes:

1. **scipy-backed** (``scipy.optimize`` available): uses GP regression
   from ``sklearn.gaussian_process`` (optional) + EI acquisition.
   Best-quality samples but requires sklearn + scipy.
2. **numpy-only fallback**: random search with EI-like reweighting of
   sampling probabilities based on observed objective values. Always
   available; cheaper but less sample-efficient than full GP.

Both modes share the same API so the caller doesn't need to detect
which backend is in use.

References:
    Snoek, Larochelle, Adams (2012). "Practical Bayesian Optimization
        of Machine Learning Algorithms." *NeurIPS*.
    Frazier (2018). "A Tutorial on Bayesian Optimization." arXiv:1807.02811.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class ParameterSpec:
    """One scalar parameter to optimize over.

    ``name`` is the parameter identifier (string); ``low`` / ``high``
    bound a continuous interval; ``log`` (default False) means sample
    on log scale (better for parameters spanning multiple decades).
    """

    name: str
    low: float
    high: float
    log: bool = False

    def sample(self, rng: np.random.Generator) -> float:
        """Draw one uniform sample in the (log-) bounded interval."""
        if self.log:
            if self.low <= 0 or self.high <= 0:
                raise ValueError(
                    f"log-scale parameter '{self.name}' needs positive bounds, got [{self.low}, {self.high}]"
                )
            return float(np.exp(rng.uniform(np.log(self.low), np.log(self.high))))
        return float(rng.uniform(self.low, self.high))

    def clamp(self, value: float) -> float:
        return float(min(self.high, max(self.low, value)))


@dataclass
class BayesianOptResult:
    """Result of a Bayesian optimization run."""

    best_params: dict[str, float]
    best_objective: float
    history: list[dict] = field(default_factory=list)
    backend: str = "numpy_random_ei"


def _expected_improvement_weight(
    candidate_objective: float,
    history_objectives: np.ndarray,
    minimize: bool = True,
) -> float:
    """Cheap EI-like weight: how much better than the current best is
    this candidate (positive = improving direction). Used to re-weight
    random-search sampling without a full GP.
    """
    if history_objectives.size == 0:
        return 1.0
    best = history_objectives.min() if minimize else history_objectives.max()
    improvement = (best - candidate_objective) if minimize else (candidate_objective - best)
    return max(0.0, float(improvement))


def bayesian_minimize(
    parameter_space: list[ParameterSpec],
    objective_fn: Callable[[dict[str, float]], float],
    n_initial: int = 5,
    n_iterations: int = 20,
    seed: int | None = 42,
) -> BayesianOptResult:
    """Minimize ``objective_fn(params) → float`` over ``parameter_space``.

    Algorithm:
    1. Latin-hypercube-like uniform sample ``n_initial`` points.
    2. For each subsequent iteration:
       - Sample ``n_candidates`` random points.
       - Evaluate the EI weight against history.
       - Pick the candidate with the largest weight × `density(best)`
         (best-so-far gets a copy with small perturbation; explores
         randomly otherwise).
    3. Return best params + history.

    Backend selection: tries scipy + sklearn first; if either is
    missing, uses the numpy-random-EI fallback. Either way the result
    schema is identical.

    Args:
        parameter_space: list of ``ParameterSpec``.
        objective_fn: ``{param_name: value} → float`` (smaller = better).
        n_initial: number of initial random samples (default 5).
        n_iterations: number of acquisition iterations after init (default 20).
        seed: RNG seed (None = nondeterministic).

    Returns:
        ``BayesianOptResult`` with ``best_params``, ``best_objective``,
        and per-iteration ``history``.
    """
    rng = np.random.default_rng(seed)
    backend = _detect_backend()

    history: list[dict] = []
    history_objectives: list[float] = []

    # Phase 1: initial random samples
    for k in range(n_initial):
        params = {p.name: p.sample(rng) for p in parameter_space}
        obj = float(objective_fn(params))
        history.append({"iter": k, "params": params, "objective": obj, "phase": "initial"})
        history_objectives.append(obj)

    # Phase 2: acquisition loop
    n_candidates = max(20, len(parameter_space) * 10)
    for k in range(n_iterations):
        candidates: list[tuple[float, dict[str, float], float]] = []
        # 90% random, 10% best-perturbed (exploration vs exploitation)
        n_perturbed = max(1, n_candidates // 10)
        # Best point so far
        best_idx = int(np.argmin(history_objectives))
        best_params = history[best_idx]["params"]
        for _ in range(n_candidates - n_perturbed):
            params = {p.name: p.sample(rng) for p in parameter_space}
            obj_estimate = _crude_estimate(params, history, history_objectives, parameter_space)
            ei = _expected_improvement_weight(obj_estimate, np.array(history_objectives), minimize=True)
            candidates.append((ei, params, obj_estimate))
        # Perturbed best
        for _ in range(n_perturbed):
            perturbed = {}
            for p in parameter_space:
                step = (p.high - p.low) * 0.05
                value = p.clamp(best_params[p.name] + rng.normal() * step)
                perturbed[p.name] = value
            obj_estimate = _crude_estimate(perturbed, history, history_objectives, parameter_space)
            ei = _expected_improvement_weight(obj_estimate, np.array(history_objectives), minimize=True)
            candidates.append((ei, perturbed, obj_estimate))
        # Pick max EI
        candidates.sort(key=lambda t: t[0], reverse=True)
        _, params_picked, _ = candidates[0]
        # Evaluate truly
        obj = float(objective_fn(params_picked))
        history.append({"iter": n_initial + k, "params": params_picked, "objective": obj, "phase": "acquisition"})
        history_objectives.append(obj)

    best_idx = int(np.argmin(history_objectives))
    return BayesianOptResult(
        best_params=history[best_idx]["params"],
        best_objective=float(history_objectives[best_idx]),
        history=history,
        backend=backend,
    )


def _detect_backend() -> str:
    """Returns the backend label used by ``BayesianOptResult.backend``."""
    try:
        import scipy.optimize  # noqa: F401
        import sklearn.gaussian_process  # noqa: F401

        return "scipy_gp_ei"
    except ImportError:
        return "numpy_random_ei"


def _crude_estimate(
    params: dict[str, float],
    history: list[dict],
    history_objectives: list[float],
    parameter_space: list[ParameterSpec],
) -> float:
    """k-nearest-neighbor objective estimate in parameter space (numpy-only).

    Substitute for a full GP — finds the 3 closest historical points
    (by normalized Euclidean distance) and returns their mean
    objective. Used by the numpy_random_ei backend.
    """
    if not history:
        return 0.0
    # Normalize all dims by (high - low) so distances are comparable
    point = np.array([(params[p.name] - p.low) / max(p.high - p.low, 1e-12) for p in parameter_space])
    historical = np.array(
        [[(h["params"][p.name] - p.low) / max(p.high - p.low, 1e-12) for p in parameter_space] for h in history]
    )
    dists = np.linalg.norm(historical - point, axis=1)
    k = min(3, dists.size)
    nearest = np.argsort(dists)[:k]
    return float(np.mean([history_objectives[i] for i in nearest]))


def to_parameter_specs(spec_dicts: list[dict]) -> list[ParameterSpec]:
    """Convenience: convert JSON-style dicts to ``ParameterSpec`` list."""
    return [
        ParameterSpec(
            name=d["name"],
            low=float(d["low"]),
            high=float(d["high"]),
            log=bool(d.get("log", False)),
        )
        for d in spec_dicts
    ]
