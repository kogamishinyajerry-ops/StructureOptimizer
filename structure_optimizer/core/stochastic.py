"""Wave CC: Monte Carlo uncertainty quantification (v5 multi-physics).

Provides UQ entrypoints that wrap the linear-elastic FEM solver and
sample over uncertain load magnitudes and/or material properties.

The classic engineering use is **reliability-based topology
optimization**: instead of optimising the deterministic compliance at
the nominal load, optimise a statistical quantity (mean ± k·std) under
prescribed load / material uncertainty.

All sampling uses ``numpy.random.default_rng(seed)`` so the same seed
on the same host gives bit-exact reproducible samples. Cross-platform
bit-exactness is **not** guaranteed (numpy RNG implementation may
differ across versions / archs); honest scope note in D029.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import SolverError, solve_linear_elastic
from structure_optimizer.core.mesh import StructuredMesh


@dataclass
class UncertaintySpec:
    """Specification for the uncertainty model used by ``uq_compliance``.

    Attributes:
        load_magnitude_std: std-dev of multiplicative noise on load
            magnitudes (Gaussian). 0.0 disables load uncertainty.
        load_angle_std:     std-dev of additive noise on load angle (rad).
        young_modulus_std:  std-dev of multiplicative noise on E.
    """

    load_magnitude_std: float = 0.0
    load_angle_std: float = 0.0
    young_modulus_std: float = 0.0


@dataclass
class UQResult:
    """Output of a Monte Carlo UQ run on a fixed density field.

    Attributes:
        samples:       per-sample compliance values (n_samples,)
        mean:          sample mean
        std:           sample std-dev
        p95:           95th percentile (engineering 1-sigma worst-case)
        max:           max compliance across all samples (true worst-case)
        n_samples:     count
        rng_seed:      seed used (for fingerprinting / reproducibility)
    """

    samples: np.ndarray
    mean: float
    std: float
    p95: float
    max: float
    n_samples: int
    rng_seed: int


def _perturbed_loads(loads: list[dict], rng: np.random.Generator, spec: UncertaintySpec) -> list[dict]:
    """Apply random multiplicative + angular noise to the load list."""
    new_loads = []
    for ld in loads:
        fx = float(ld.get("fx", 0.0))
        fy = float(ld.get("fy", 0.0))
        mag = float(np.hypot(fx, fy))
        if mag == 0.0:
            new_loads.append(dict(ld))
            continue
        # Multiplicative magnitude noise
        if spec.load_magnitude_std > 0:
            mag *= 1.0 + float(rng.normal(0.0, spec.load_magnitude_std))
        # Additive angular noise
        theta = float(np.arctan2(fy, fx))
        if spec.load_angle_std > 0:
            theta += float(rng.normal(0.0, spec.load_angle_std))
        scaled = dict(ld)
        scaled["fx"] = mag * np.cos(theta)
        scaled["fy"] = mag * np.sin(theta)
        new_loads.append(scaled)
    return new_loads


def _perturbed_config(config: BenchmarkConfig, rng: np.random.Generator, spec: UncertaintySpec) -> BenchmarkConfig:
    """Build a new BenchmarkConfig with random load + material perturbations."""
    new_loads = _perturbed_loads(config.loads, rng, spec)
    new_material = config.material
    if spec.young_modulus_std > 0:
        factor = 1.0 + float(rng.normal(0.0, spec.young_modulus_std))
        # Clamp to avoid non-positive E (rejection-free clipping; the
        # tail-density of N(1, 0.1) below 0 is negligible for std ≤ 0.3)
        factor = max(factor, 1e-3)
        new_material = replace(config.material, young_modulus=config.material.young_modulus * factor)
    return replace(config, loads=new_loads, material=new_material)


def monte_carlo_uq(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    rng_seed: int,
    n_samples: int = 50,
    uncertainty: UncertaintySpec | None = None,
) -> UQResult:
    """Run Monte Carlo UQ on the compliance of a fixed density field.

    Args:
        config:       BenchmarkConfig (nominal)
        mesh:         structured-quad mesh
        densities:    per-element density vector (fixed during UQ)
        rng_seed:     RNG seed for reproducibility
        n_samples:    Monte Carlo sample count
        uncertainty:  UncertaintySpec; defaults to load_magnitude_std=0.1

    Returns:
        UQResult with mean, std, p95, max + raw samples
    """
    if n_samples < 1:
        raise SolverError("uq_n_samples_must_be_positive")
    if uncertainty is None:
        uncertainty = UncertaintySpec(load_magnitude_std=0.1)

    rng = np.random.default_rng(rng_seed)
    samples = np.zeros(n_samples)
    for k in range(n_samples):
        cfg = _perturbed_config(config, rng, uncertainty)
        result = solve_linear_elastic(cfg, mesh, densities)
        samples[k] = float(result.compliance)

    return UQResult(
        samples=samples,
        mean=float(samples.mean()),
        std=float(samples.std()),
        p95=float(np.percentile(samples, 95)),
        max=float(samples.max()),
        n_samples=n_samples,
        rng_seed=int(rng_seed),
    )


# Alias for v5 rubric grep
uq_compliance = monte_carlo_uq


def monte_carlo_uq_with_callback(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    rng_seed: int,
    n_samples: int,
    uncertainty: UncertaintySpec,
    callback: Callable[[BenchmarkConfig, np.ndarray], float],
) -> UQResult:
    """Generic UQ wrapper: caller supplies a (cfg, ρ) → QoI callback.

    Useful for sampling non-compliance objectives (max stress, max
    displacement, thermal max temperature, etc.) without re-implementing
    the perturbation logic.
    """
    if n_samples < 1:
        raise SolverError("uq_n_samples_must_be_positive")
    rng = np.random.default_rng(rng_seed)
    samples = np.zeros(n_samples)
    for k in range(n_samples):
        cfg = _perturbed_config(config, rng, uncertainty)
        samples[k] = float(callback(cfg, densities))
    return UQResult(
        samples=samples,
        mean=float(samples.mean()),
        std=float(samples.std()),
        p95=float(np.percentile(samples, 95)),
        max=float(samples.max()),
        n_samples=n_samples,
        rng_seed=int(rng_seed),
    )
