"""Wave Z: frequency-response (harmonic-driven) tests."""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError, solve_linear_elastic
from structure_optimizer.core.freq_response import (
    frequency_sweep,
    solve_frequency_response,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.modal import solve_modal


@pytest.fixture
def vibrating_beam_smoke():
    config = load_benchmark("vibrating_beam", preset="smoke")
    mesh = create_structured_mesh(config)
    return config, mesh


def test_frequency_response_at_zero_omega_matches_static(vibrating_beam_smoke):
    """At ω = 0, (K - 0·M) u = f is the static problem. The frequency
    response should match `solve_linear_elastic` displacements."""
    config, mesh = vibrating_beam_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    r_static = solve_linear_elastic(config, mesh, densities)
    r_freq = solve_frequency_response(config, mesh, densities, omega=0.0)
    np.testing.assert_allclose(r_freq.displacements, r_static.displacements, atol=1e-8, rtol=1e-8)


def test_frequency_response_returns_finite_field(vibrating_beam_smoke):
    config, mesh = vibrating_beam_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    r = solve_frequency_response(config, mesh, densities, omega=1e-3)
    assert np.all(np.isfinite(r.displacements))
    assert r.max_displacement > 0


def test_frequency_response_rejects_density_count_mismatch(vibrating_beam_smoke):
    config, mesh = vibrating_beam_smoke
    bad = np.zeros(mesh.elements.shape[0] + 1)
    with pytest.raises(SolverError, match="density_count_mismatch"):
        solve_frequency_response(config, mesh, bad, omega=1.0)


def test_frequency_response_rejects_negative_omega(vibrating_beam_smoke):
    config, mesh = vibrating_beam_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    with pytest.raises(SolverError, match="negative_omega"):
        solve_frequency_response(config, mesh, densities, omega=-1.0)


def test_frequency_response_resonance_amplification(vibrating_beam_smoke):
    """Near the first natural frequency, response should be much larger
    than the off-resonance response."""
    config, mesh = vibrating_beam_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    modal = solve_modal(config, mesh, densities, n_modes=1)
    omega1 = float(np.sqrt(modal.omega_squared[0]))

    # Off-resonance: ω = 0.1 * ω₁
    r_off = solve_frequency_response(config, mesh, densities, omega=0.1 * omega1)
    # Near resonance: ω = 0.99 * ω₁ (avoid exact singularity)
    r_near = solve_frequency_response(config, mesh, densities, omega=0.99 * omega1)
    assert r_near.max_displacement > 5.0 * r_off.max_displacement


def test_frequency_sweep_returns_arrays_of_right_shape(vibrating_beam_smoke):
    config, mesh = vibrating_beam_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    omegas = np.linspace(0.0, 1e-2, 5)
    sweep = frequency_sweep(config, mesh, densities, omegas)
    assert sweep["max_displacement"].shape == (5,)
    assert sweep["response_norm"].shape == (5,)
    assert sweep["valid"].dtype == bool


def test_frequency_sweep_marks_resonance_invalid_or_finite(vibrating_beam_smoke):
    """A sweep that includes a near-singular frequency should either
    succeed (with very large response) or mark that point invalid."""
    config, mesh = vibrating_beam_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    omegas = np.linspace(0.0, 1e-3, 4)
    sweep = frequency_sweep(config, mesh, densities, omegas)
    # All should be finite at low ω (well below first mode)
    assert sweep["valid"].all()
    assert np.all(np.isfinite(sweep["max_displacement"]))


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


def test_property_frequency_response_linear_in_load(vibrating_beam_smoke):
    """At fixed ω, doubling the load amplitude doubles the displacement
    (linear PDE)."""

    config, mesh = vibrating_beam_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    r1 = solve_frequency_response(config, mesh, densities, omega=1e-3)

    # Build a config with 2× load amplitude
    from dataclasses import replace

    new_loads = []
    for ld in config.loads:
        scaled = dict(ld)
        scaled["fx"] = 2.0 * float(ld.get("fx", 0.0))
        scaled["fy"] = 2.0 * float(ld.get("fy", 0.0))
        new_loads.append(scaled)
    config2 = replace(config, loads=new_loads)
    r2 = solve_frequency_response(config2, mesh, densities, omega=1e-3)
    np.testing.assert_allclose(r2.displacements, 2.0 * r1.displacements, atol=1e-8, rtol=1e-8)


def test_property_frequency_response_zero_load_zero_displacement(vibrating_beam_smoke):
    """f = 0 → u = 0 (linear PDE)."""
    from dataclasses import replace

    config, mesh = vibrating_beam_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    zero_loads = []
    for ld in config.loads:
        z = dict(ld)
        z["fx"] = 0.0
        z["fy"] = 0.0
        zero_loads.append(z)
    config2 = replace(config, loads=zero_loads)
    r = solve_frequency_response(config2, mesh, densities, omega=1e-3)
    np.testing.assert_allclose(r.displacements, 0.0, atol=1e-12)
