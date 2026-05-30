"""Wave FF (v6): Rayleigh-damped complex frequency-response tests.

The analytical anchor (rubric §2.5) is the half-power bandwidth: for light
Rayleigh damping the −3 dB bandwidth of a resonance peak is Δω ≈ 2 ζ ω_n, so
the bandwidth recovered from a magnitude sweep must imply the ζ we put in.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.freq_response import (
    half_power_bandwidth,
    rayleigh_modal_damping_ratio,
    solve_damped_frequency_response,
    solve_frequency_response,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.modal import solve_modal


@pytest.fixture
def cantilever_smoke():
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    return config, mesh


def _first_natural_omega(config, mesh, densities) -> float:
    r = solve_modal(config, mesh, densities, n_modes=3, mass_type="consistent")
    return float(np.sqrt(r.omega_squared[0]))


def test_damped_reduces_to_undamped_when_zero_damping(cantilever_smoke):
    """α = β = 0 → damped magnitude equals the undamped real solve."""
    config, mesh = cantilever_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    omega = 0.3 * _first_natural_omega(config, mesh, densities)  # well below resonance
    undamped = solve_frequency_response(config, mesh, densities, omega)
    damped = solve_damped_frequency_response(config, mesh, densities, omega, alpha=0.0, beta=0.0)
    np.testing.assert_allclose(damped.magnitude, np.abs(undamped.displacements), rtol=1e-9, atol=1e-12)


def test_damped_response_finite_at_resonance(cantilever_smoke):
    """At ω = ω₁ the undamped dynamic stiffness is (near-)singular; the damped
    system stays finite — the whole point of adding damping."""
    config, mesh = cantilever_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    omega1 = _first_natural_omega(config, mesh, densities)
    damped = solve_damped_frequency_response(config, mesh, densities, omega1, alpha=0.05 * omega1, beta=0.0)
    assert np.isfinite(damped.max_magnitude)
    assert damped.max_magnitude > 0.0


def test_rayleigh_half_power_bandwidth_matches_analytical(cantilever_smoke):
    """§2.5: the −3 dB bandwidth implies ζ ≈ ½(α/ω₁) for mass-proportional
    Rayleigh damping (β = 0), to within the continuum-vs-SDOF approximation."""
    config, mesh = cantilever_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    omega1 = _first_natural_omega(config, mesh, densities)
    zeta_target = 0.05
    alpha = 2.0 * zeta_target * omega1  # β = 0 → ζ₁ = α/(2ω₁)
    assert rayleigh_modal_damping_ratio(alpha, 0.0, omega1) == pytest.approx(zeta_target)

    omegas = np.linspace(0.85 * omega1, 1.15 * omega1, 401)
    mag = np.array(
        [
            solve_damped_frequency_response(config, mesh, densities, float(w), alpha=alpha, beta=0.0).response_norm
            for w in omegas
        ]
    )
    bw = half_power_bandwidth(omegas, mag)
    assert bw["damping_ratio"] == pytest.approx(zeta_target, rel=0.25), (
        f"half-power ζ={bw['damping_ratio']:.4f} vs target {zeta_target}"
    )
    assert bw["omega_peak"] == pytest.approx(omega1, rel=0.05)


def test_rayleigh_modal_damping_ratio_formula():
    """ζ = ½(α/ω + βω)."""
    assert rayleigh_modal_damping_ratio(2.0, 0.0, 10.0) == pytest.approx(0.1)
    assert rayleigh_modal_damping_ratio(0.0, 0.01, 10.0) == pytest.approx(0.05)


def test_damped_rejects_negative_coefficients(cantilever_smoke):
    config, mesh = cantilever_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    with pytest.raises(SolverError, match="rayleigh_damping_negative_coefficient"):
        solve_damped_frequency_response(config, mesh, densities, 1.0, alpha=-1.0)


def test_property_damping_lowers_resonance_peak(cantilever_smoke):
    """Property: heavier damping → smaller peak response at resonance."""
    config, mesh = cantilever_smoke
    densities = np.full(mesh.elements.shape[0], 1.0)
    omega1 = _first_natural_omega(config, mesh, densities)
    light = solve_damped_frequency_response(config, mesh, densities, omega1, alpha=0.02 * omega1)
    heavy = solve_damped_frequency_response(config, mesh, densities, omega1, alpha=0.20 * omega1)
    assert heavy.max_magnitude < light.max_magnitude
