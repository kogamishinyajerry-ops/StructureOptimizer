"""Wave YY (v8, D054): fibre-steering thermal TO (orientation as design variable).

Quantitative anchors:
- the analytic orientation sensitivity dC/dθ_e matches central differences of the
  thermal compliance (the headline anchor);
- an isotropic base tensor (kxx==kyy) gives **zero** orientation sensitivity
  (rotating an isotropic conductor changes nothing — an exact analytical check);
- steepest descent on the fibre angles monotonically lowers thermal compliance.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.thermal import orientation_field_to_tensors, solve_thermal
from structure_optimizer.core.thermal_simp import (
    fibre_steering_thermal_to,
    load_thermal_benchmark,
    orientation_sensitivity,
)

KXX, KYY = 5.0, 1.0


def _setup():
    config, _k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    return config, mesh, sources, bcs


def test_orientation_sensitivity_matches_central_fd():
    config, mesh, sources, bcs = _setup()
    n = mesh.elements.shape[0]
    rho = np.full(n, 1.0)
    rng = np.random.default_rng(0)
    angles = rng.uniform(0.0, np.pi, n)

    g = orientation_sensitivity(config, mesh, rho, angles, KXX, KYY, heat_sources=sources, thermal_bcs=bcs)

    def C(a):
        f = orientation_field_to_tensors(KXX, KYY, a)
        return solve_thermal(config, mesh, rho, 1.0, sources, bcs, conductivity_tensor_field=f).thermal_compliance

    h = 1e-6
    for e in np.argsort(-np.abs(g))[:6]:
        ap, am = angles.copy(), angles.copy()
        ap[e] += h
        am[e] -= h
        fd = (C(ap) - C(am)) / (2.0 * h)
        assert g[e] == pytest.approx(fd, rel=1e-5), f"elem {e}: adj={g[e]:.6e} fd={fd:.6e}"


def test_isotropic_base_has_zero_orientation_sensitivity():
    config, mesh, sources, bcs = _setup()
    n = mesh.elements.shape[0]
    rho = np.full(n, 1.0)
    angles = np.linspace(0.0, np.pi, n)
    # kxx == kyy → isotropic → rotation is a no-op → dC/dθ ≡ 0
    g = orientation_sensitivity(config, mesh, rho, angles, 3.0, 3.0, heat_sources=sources, thermal_bcs=bcs)
    assert np.max(np.abs(g)) < 1e-6


def test_fibre_steering_lowers_thermal_compliance():
    config, mesh, sources, bcs = _setup()
    rho = np.full(mesh.elements.shape[0], 1.0)
    res = fibre_steering_thermal_to(
        config, mesh, rho, KXX, KYY, n_steps=20, step=0.3, heat_sources=sources, thermal_bcs=bcs
    )
    h = res.compliance_history
    assert len(h) == 21
    assert h[-1] < h[0]  # steering beats the fixed (axis-aligned) orientation
    assert h[-1] < 0.9 * h[0]  # a meaningful reduction
    assert all(h[i + 1] <= h[i] * (1.0 + 1e-4) for i in range(len(h) - 1)), f"not monotone: {h}"
