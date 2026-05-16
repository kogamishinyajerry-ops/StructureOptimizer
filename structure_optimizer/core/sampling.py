"""Wave O: design-of-experiments sampling.

Two methods supported beyond the default Cartesian-product grid:

- **LHS (Latin Hypercube Sampling)** — pure NumPy. Each parameter
  dimension is divided into ``n_samples`` equiprobable bins; one sample
  per bin per dimension; bin assignments are randomly permuted across
  dimensions so the joint distribution covers the unit hypercube
  uniformly.
- **Sobol (low-discrepancy sequence)** — uses ``scipy.stats.qmc.Sobol``
  when scipy is available; raises a clear ``RuntimeError`` otherwise. We
  intentionally do NOT implement Sobol from scratch (the direction
  vectors and carryover bookkeeping are non-trivial; reusing scipy's
  vetted implementation keeps the code small).

Both return an ``(n_samples, n_dims)`` array of values in ``[0, 1)``.
The study runner maps these to actual parameter values via
``parameters[name][int(sample * len(parameters[name]))]``.
"""

from __future__ import annotations

import numpy as np


def lhs_samples(n_samples: int, n_dims: int, rng: np.random.Generator | None = None) -> np.ndarray:
    """Latin Hypercube Sampling on ``[0, 1)^n_dims``.

    Each dim partitioned into ``n_samples`` equiprobable bins; one sample
    drawn uniformly from each bin; bin orders permuted independently per
    dim so the joint coverage is well-distributed.

    Args:
        n_samples: number of samples (rows in result).
        n_dims: number of dimensions (columns in result).
        rng: optional seeded ``np.random.Generator``; when ``None``, uses
             the global default (non-reproducible across runs).

    Returns:
        ``(n_samples, n_dims)`` float array, all entries in ``[0, 1)``.
    """
    if n_samples < 1:
        raise ValueError(f"n_samples must be ≥1, got {n_samples}")
    if n_dims < 1:
        raise ValueError(f"n_dims must be ≥1, got {n_dims}")
    if rng is None:
        rng = np.random.default_rng()
    cuts = np.linspace(0.0, 1.0, n_samples + 1)
    samples = np.empty((n_samples, n_dims), dtype=float)
    for dim in range(n_dims):
        # one uniform draw per bin, then permute the bin order
        u = rng.uniform(cuts[:-1], cuts[1:])
        rng.shuffle(u)
        samples[:, dim] = u
    return samples


def sobol_samples(n_samples: int, n_dims: int, rng: np.random.Generator | None = None) -> np.ndarray:
    """Sobol low-discrepancy quasi-random sequence on ``[0, 1)^n_dims``.

    Requires scipy (``pip install structure-optimizer[sparse]``); raises
    ``RuntimeError`` if unavailable. Sobol gives better coverage than
    LHS at the cost of a non-NumPy dependency at runtime.
    """
    if n_samples < 1:
        raise ValueError(f"n_samples must be ≥1, got {n_samples}")
    if n_dims < 1:
        raise ValueError(f"n_dims must be ≥1, got {n_dims}")
    try:
        from scipy.stats.qmc import Sobol
    except ImportError as exc:
        raise RuntimeError(
            "Sobol sampling requires scipy. Install with: pip install structure-optimizer[sparse]"
        ) from exc
    seed: int | None = None
    if rng is not None:
        seed = int(rng.integers(0, 2**32))
    sampler = Sobol(d=n_dims, seed=seed)
    return np.asarray(sampler.random(n_samples))


def map_samples_to_grid(samples: np.ndarray, parameters: dict[str, list]) -> list[dict]:
    """Convert ``[0, 1)`` samples into concrete parameter overrides.

    For each (sample row, parameter dim) pair, pick the parameter value
    at index ``floor(u * len(values))`` (clamped to ``len-1`` for the
    edge case ``u == 1.0``).

    Args:
        samples: ``(n_samples, n_dims)`` array from ``lhs_samples`` /
                 ``sobol_samples`` (or any uniform sampler).
        parameters: ``{name: [value, value, ...]}`` map. Iteration order
                    of the dict defines column order in ``samples``.

    Returns:
        List of ``{name: value, ...}`` dicts, one per sample row.
    """
    names = list(parameters)
    if samples.shape[1] != len(names):
        raise ValueError(f"samples have {samples.shape[1]} dims but {len(names)} parameter names")
    overrides_list = []
    for row in samples:
        overrides = {}
        for col, name in enumerate(names):
            values = parameters[name]
            idx = min(int(row[col] * len(values)), len(values) - 1)
            overrides[name] = values[idx]
        overrides_list.append(overrides)
    return overrides_list
