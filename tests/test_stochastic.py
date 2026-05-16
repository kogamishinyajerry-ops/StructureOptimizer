"""Wave CC: Monte Carlo UQ + robust topology optimization tests.

Verifies:
1. UQ returns valid statistics (mean ≥ 0, std ≥ 0, p95 ≥ mean).
2. RNG-seed reproducibility (§3.3): same seed → bit-exact same samples.
3. Larger uncertainty → larger std.
4. Worst-case SIMP converges + densities in bounds.
5. Property tests: zero uncertainty → all samples equal nominal.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError, solve_linear_elastic
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.reliability import worst_case_simp
from structure_optimizer.core.stochastic import (
    UncertaintySpec,
    monte_carlo_uq,
    monte_carlo_uq_with_callback,
    uq_compliance,
)


@pytest.fixture
def uncertain_load_smoke():
    config = load_benchmark("uncertain_load_bracket", preset="smoke")
    mesh = create_structured_mesh(config)
    return config, mesh


# ---------------------------------------------------------------------------
# UQ entrypoints
# ---------------------------------------------------------------------------


def test_monte_carlo_uq_returns_valid_statistics(uncertain_load_smoke):
    config, mesh = uncertain_load_smoke
    densities = np.full(mesh.elements.shape[0], 0.5)
    result = monte_carlo_uq(config, mesh, densities, rng_seed=42, n_samples=10)
    assert result.n_samples == 10
    assert result.samples.shape == (10,)
    assert result.mean > 0
    assert result.std >= 0
    assert result.p95 >= result.mean
    assert result.max >= result.p95


def test_monte_carlo_uq_alias_uq_compliance_works(uncertain_load_smoke):
    """uq_compliance is the v5-rubric alias for monte_carlo_uq."""
    config, mesh = uncertain_load_smoke
    densities = np.full(mesh.elements.shape[0], 0.5)
    r1 = uq_compliance(config, mesh, densities, rng_seed=0, n_samples=5)
    r2 = monte_carlo_uq(config, mesh, densities, rng_seed=0, n_samples=5)
    np.testing.assert_array_equal(r1.samples, r2.samples)


def test_monte_carlo_uq_rejects_zero_samples(uncertain_load_smoke):
    config, mesh = uncertain_load_smoke
    densities = np.full(mesh.elements.shape[0], 0.5)
    with pytest.raises(SolverError, match="uq_n_samples_must_be_positive"):
        monte_carlo_uq(config, mesh, densities, rng_seed=0, n_samples=0)


# ---------------------------------------------------------------------------
# RNG-seed reproducibility (rubric §3.3)
# ---------------------------------------------------------------------------


def test_stochastic_uq_compliance_reproducible_with_same_seed(uncertain_load_smoke):
    """Rubric §3.3: same seed → bit-exact identical samples."""
    config, mesh = uncertain_load_smoke
    densities = np.full(mesh.elements.shape[0], 0.5)
    r1 = monte_carlo_uq(config, mesh, densities, rng_seed=12345, n_samples=20)
    r2 = monte_carlo_uq(config, mesh, densities, rng_seed=12345, n_samples=20)
    np.testing.assert_array_equal(r1.samples, r2.samples)
    assert r1.mean == r2.mean
    assert r1.std == r2.std


def test_monte_carlo_uq_different_seeds_produce_different_samples(uncertain_load_smoke):
    """Different seeds → different sample arrays (otherwise the RNG is
    broken or not being used)."""
    config, mesh = uncertain_load_smoke
    densities = np.full(mesh.elements.shape[0], 0.5)
    r1 = monte_carlo_uq(config, mesh, densities, rng_seed=1, n_samples=10)
    r2 = monte_carlo_uq(config, mesh, densities, rng_seed=2, n_samples=10)
    # At least one element should differ
    assert not np.array_equal(r1.samples, r2.samples)


def test_monte_carlo_uq_zero_uncertainty_returns_constant_compliance(uncertain_load_smoke):
    """With UncertaintySpec all-zero, every sample = nominal compliance."""
    config, mesh = uncertain_load_smoke
    densities = np.full(mesh.elements.shape[0], 0.5)
    spec = UncertaintySpec()  # all zero
    result = monte_carlo_uq(config, mesh, densities, rng_seed=0, n_samples=5, uncertainty=spec)
    nominal = solve_linear_elastic(config, mesh, densities).compliance
    np.testing.assert_allclose(result.samples, nominal, atol=1e-9, rtol=1e-9)
    assert result.std == pytest.approx(0.0, abs=1e-9)


def test_monte_carlo_uq_larger_uncertainty_higher_std(uncertain_load_smoke):
    """Doubling load_magnitude_std should approximately double sample std."""
    config, mesh = uncertain_load_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    r_low = monte_carlo_uq(
        config, mesh, densities, rng_seed=0, n_samples=50, uncertainty=UncertaintySpec(load_magnitude_std=0.05)
    )
    r_high = monte_carlo_uq(
        config, mesh, densities, rng_seed=0, n_samples=50, uncertainty=UncertaintySpec(load_magnitude_std=0.2)
    )
    assert r_high.std > 2.0 * r_low.std


# ---------------------------------------------------------------------------
# Generic callback wrapper
# ---------------------------------------------------------------------------


def test_monte_carlo_uq_with_callback_runs(uncertain_load_smoke):
    """Generic callback path: use it to sample max displacement instead of compliance."""
    config, mesh = uncertain_load_smoke
    densities = np.full(mesh.elements.shape[0], 0.5)

    def max_disp_callback(cfg, dens):
        r = solve_linear_elastic(cfg, mesh, dens)
        return float(np.max(np.abs(r.displacements)))

    result = monte_carlo_uq_with_callback(
        config, mesh, densities, rng_seed=0, n_samples=5,
        uncertainty=UncertaintySpec(load_magnitude_std=0.1),
        callback=max_disp_callback,
    )
    assert result.samples.shape == (5,)
    assert (result.samples > 0).all()


# ---------------------------------------------------------------------------
# Worst-case (minmax) SIMP
# ---------------------------------------------------------------------------


def test_worst_case_simp_runs_smoke(uncertain_load_smoke):
    config, mesh = uncertain_load_smoke
    result = worst_case_simp(config, mesh, rng_seed=0, n_scenarios=3)
    assert result.densities.shape == (mesh.elements.shape[0],)
    assert (result.densities >= config.optimization.min_density - 1e-12).all()
    assert (result.densities <= 1.0 + 1e-12).all()
    assert result.n_scenarios == 3
    assert result.final_compliance_per_scenario.shape == (3,)
    assert result.final_worst_compliance == pytest.approx(result.final_compliance_per_scenario.max())


def test_worst_case_simp_reproducible_with_same_seed(uncertain_load_smoke):
    """Same seed → bit-exact same densities (RNG-seeded scenario sampling)."""
    config, mesh = uncertain_load_smoke
    r1 = worst_case_simp(config, mesh, rng_seed=7, n_scenarios=3)
    r2 = worst_case_simp(config, mesh, rng_seed=7, n_scenarios=3)
    np.testing.assert_array_equal(r1.densities, r2.densities)


def test_worst_case_simp_rejects_zero_scenarios(uncertain_load_smoke):
    config, mesh = uncertain_load_smoke
    with pytest.raises(SolverError, match="n_scenarios_must_be_positive"):
        worst_case_simp(config, mesh, rng_seed=0, n_scenarios=0)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


def test_property_monte_carlo_uq_mean_bounded_by_max(uncertain_load_smoke):
    """mean ≤ max always."""
    config, mesh = uncertain_load_smoke
    densities = np.full(mesh.elements.shape[0], 0.5)
    for seed in [0, 1, 2, 3, 4]:
        result = monte_carlo_uq(config, mesh, densities, rng_seed=seed, n_samples=10)
        assert result.mean <= result.max
        assert result.mean - 3 * result.std <= result.samples.min() + 1e-9


def test_property_stochastic_monte_carlo_reproducible_with_seed(uncertain_load_smoke):
    """Property: seed-determined output bit-exact across N trials."""
    config, mesh = uncertain_load_smoke
    densities = np.full(mesh.elements.shape[0], 0.5)
    for seed in [42, 1000, 99999]:
        r1 = monte_carlo_uq(config, mesh, densities, rng_seed=seed, n_samples=5)
        r2 = monte_carlo_uq(config, mesh, densities, rng_seed=seed, n_samples=5)
        np.testing.assert_array_equal(r1.samples, r2.samples)
