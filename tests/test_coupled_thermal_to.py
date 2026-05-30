"""Wave GGG (v9, D062): coupled density + orientation thermal TO (alternating min).

Quantitative anchors:
- alternating minimisation of (density, fibre orientation) reaches a thermal
  compliance at least as low as optimising either field alone (the coupling
  payoff — the headline);
- the per-cycle compliance history is monotonically non-increasing;
- with an isotropic base tensor (kxx==kyy) the orientation step is a no-op
  (dC/dθ ≡ 0), so the coupled run reduces *exactly* to the density-only run and
  the angles stay zero.
"""

from __future__ import annotations

import numpy as np
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.thermal_simp import (
    coupled_density_orientation_to,
    fibre_steering_thermal_to,
    load_thermal_benchmark,
)

KXX, KYY = 5.0, 1.0


def _setup():
    config, _k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    return config, create_structured_mesh(config), sources, bcs


def test_coupled_beats_each_single_field():
    config, mesh, sources, bcs = _setup()
    coupled = coupled_density_orientation_to(
        config, mesh, KXX, KYY, n_outer=8, n_orient_steps=8, heat_sources=sources, thermal_bcs=bcs
    )
    density_only = coupled_density_orientation_to(
        config, mesh, KXX, KYY, n_outer=8, n_orient_steps=0, heat_sources=sources, thermal_bcs=bcs
    )
    rho_uniform = np.full(mesh.elements.shape[0], config.optimization.volume_fraction)
    orient_only = fibre_steering_thermal_to(
        config, mesh, rho_uniform, KXX, KYY, n_steps=20, heat_sources=sources, thermal_bcs=bcs
    )
    c = coupled.compliance_history[-1]
    assert c <= density_only.compliance_history[-1] + 1e-6
    assert c <= orient_only.compliance_history[-1] + 1e-6


def test_coupled_monotone_descent():
    config, mesh, sources, bcs = _setup()
    res = coupled_density_orientation_to(
        config, mesh, KXX, KYY, n_outer=8, n_orient_steps=8, heat_sources=sources, thermal_bcs=bcs
    )
    h = res.compliance_history
    assert len(h) >= 2
    assert all(h[i + 1] <= h[i] + 1e-6 * abs(h[i]) for i in range(len(h) - 1)), h


def test_isotropic_reduces_to_density_only():
    config, mesh, sources, bcs = _setup()
    coupled = coupled_density_orientation_to(
        config, mesh, 3.0, 3.0, n_outer=6, n_orient_steps=8, heat_sources=sources, thermal_bcs=bcs
    )
    density_only = coupled_density_orientation_to(
        config, mesh, 3.0, 3.0, n_outer=6, n_orient_steps=0, heat_sources=sources, thermal_bcs=bcs
    )
    # isotropic base tensor → rotation is a no-op → identical run, angles stay 0
    assert coupled.compliance_history[-1] == density_only.compliance_history[-1]
    assert np.max(np.abs(coupled.angles)) == 0.0


def test_coupled_deterministic():
    config, mesh, sources, bcs = _setup()
    a = coupled_density_orientation_to(
        config, mesh, KXX, KYY, n_outer=5, n_orient_steps=5, heat_sources=sources, thermal_bcs=bcs
    )
    b = coupled_density_orientation_to(
        config, mesh, KXX, KYY, n_outer=5, n_orient_steps=5, heat_sources=sources, thermal_bcs=bcs
    )
    np.testing.assert_array_equal(a.densities, b.densities)
    np.testing.assert_array_equal(a.angles, b.angles)
    assert a.compliance_history == b.compliance_history
