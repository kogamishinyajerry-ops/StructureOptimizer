"""Wave NN (v7): per-element anisotropic thermal field + anisotropic thermal TO.

Quantitative anchors:
- a per-element conductivity field whose elements all carry the same tensor
  reduces *exactly* to the global-tensor solve (machine precision) — so it
  inherits D036's patch test / rotation-invariance guarantees;
- a spatially-varying orientation field produces a genuinely different
  temperature field (the field does something physical);
- the anisotropic thermal SIMP sensitivity matches central finite differences.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.thermal import (
    conductivity_tensor,
    orientation_field_to_tensors,
    rotate_conductivity_tensor,
    solve_thermal,
)
from structure_optimizer.core.thermal_simp import (
    anisotropic_thermal_sensitivity,
    load_thermal_benchmark,
)


def _setup():
    config, _k_scalar, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    return config, mesh, sources, bcs


def test_uniform_field_reduces_to_global_tensor():
    config, mesh, sources, bcs = _setup()
    densities = np.full(mesh.elements.shape[0], 1.0)
    tensor = conductivity_tensor(5.0, 1.0, 0.3)
    field = np.stack([tensor] * mesh.elements.shape[0])

    r_global = solve_thermal(config, mesh, densities, 1.0, sources, bcs, conductivity_tensor=tensor)
    r_field = solve_thermal(config, mesh, densities, 1.0, sources, bcs, conductivity_tensor_field=field)
    assert np.allclose(r_field.temperatures, r_global.temperatures, atol=1e-12)
    assert r_field.thermal_compliance == pytest.approx(r_global.thermal_compliance, abs=1e-12)


def test_varying_orientation_changes_solution():
    config, mesh, sources, bcs = _setup()
    densities = np.full(mesh.elements.shape[0], 1.0)
    n = mesh.elements.shape[0]
    uniform = orientation_field_to_tensors(5.0, 1.0, np.zeros(n))
    varying = orientation_field_to_tensors(5.0, 1.0, np.linspace(0.0, np.pi / 2, n))

    r_u = solve_thermal(config, mesh, densities, 1.0, sources, bcs, conductivity_tensor_field=uniform)
    r_v = solve_thermal(config, mesh, densities, 1.0, sources, bcs, conductivity_tensor_field=varying)
    diff = np.linalg.norm(r_v.temperatures - r_u.temperatures)
    assert diff > 1e-6, f"varying orientation field did not change the solution (diff={diff:.2e})"


def test_orientation_field_to_tensors_matches_rotate():
    angles = [0.0, 0.3, 1.1]
    field = orientation_field_to_tensors(5.0, 1.0, angles, kxy=0.2)
    base = conductivity_tensor(5.0, 1.0, 0.2)
    for i, a in enumerate(angles):
        assert np.allclose(field[i], rotate_conductivity_tensor(base, a), atol=1e-12)
    # θ=0 → unchanged base tensor.
    assert np.allclose(field[0], base, atol=1e-12)


def test_anisotropic_sensitivity_matches_central_fd():
    config, mesh, sources, bcs = _setup()
    rng = np.random.default_rng(0)
    n = mesh.elements.shape[0]
    densities = np.clip(0.5 + 0.1 * rng.standard_normal(n), 0.2, 0.95)
    tensor = conductivity_tensor(4.0, 1.5, 0.4)

    sens = anisotropic_thermal_sensitivity(
        config, mesh, densities, conductivity_tensor=tensor, heat_sources=sources, thermal_bcs=bcs
    )

    def compliance(rho):
        return solve_thermal(config, mesh, rho, 1.0, sources, bcs, conductivity_tensor=tensor).thermal_compliance

    h = 1e-6
    design = np.where(~mesh.void_mask)[0]
    for e in design[:: max(1, len(design) // 5)][:5]:
        rp, rm = densities.copy(), densities.copy()
        rp[e] += h
        rm[e] -= h
        fd = (compliance(rp) - compliance(rm)) / (2.0 * h)
        assert sens[e] == pytest.approx(fd, rel=1e-4, abs=1e-7), f"elem {e}: sens={sens[e]:.4e} fd={fd:.4e}"


def test_field_shape_rejected():
    config, mesh, sources, bcs = _setup()
    densities = np.full(mesh.elements.shape[0], 1.0)
    bad = np.zeros((mesh.elements.shape[0], 3, 3))  # wrong tensor shape
    with pytest.raises(SolverError, match="conductivity_tensor_field_shape"):
        solve_thermal(config, mesh, densities, 1.0, sources, bcs, conductivity_tensor_field=bad)
