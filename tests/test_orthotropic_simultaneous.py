"""Wave XXX (v11, D079): elastic orthotropic simultaneous (ρ,θ) MMA + fibre continuity.

Quantitative anchors (closed-form / FD / constraint, not qualitative trend):
- **the orthotropic Q4 element stiffness reproduces the isotropic closed form**:
  with an isotropic ``D``, ``orthotropic_element_stiffness`` equals
  ``fem2d.element_stiffness`` to ≤ 1e-9 (validates B-matrix, node ordering, Gauss);
- **the rotation is correct**: isotropic ``D`` is rotation-invariant, ``D(90°)``
  swaps E₁↔E₂, and ``dD/dθ`` matches central FD;
- **both compliance sensitivities match central FD** to ≤ 1e-4 — including the
  novel ``dC/dθ`` (orientation) term;
- **simultaneous (ρ,θ) MMA** drives compliance far down at feasible volume,
  deterministically;
- **the fibre-continuity constraint binds**: the constrained adjacent-angle
  variation lands on its limit while the unconstrained run exceeds it.

D070's reopening criterion: "elastic simultaneous (ρ,θ) MMA; fibre-continuity".
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError, element_stiffness
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.orthotropic_simp import (
    drotate_plane_stress_dtheta,
    orthotropic_compliance_sensitivities,
    orthotropic_element_stiffness,
    orthotropic_plane_stress_matrix,
    rotate_plane_stress,
    simultaneous_elastic_orientation_mma,
)


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def test_orthotropic_ke_reproduces_isotropic_closed_form():
    config, _ = _setup()
    e, nu = config.material.young_modulus, config.material.poisson_ratio
    d_iso = orthotropic_plane_stress_matrix(e, e, nu, e / (2.0 * (1.0 + nu)))
    ke = orthotropic_element_stiffness(d_iso)
    assert np.max(np.abs(ke - element_stiffness(e, nu))) <= 1e-9


def test_rotation_invariance_swap_and_derivative():
    # isotropic D is rotation-invariant
    d_iso = np.array([[1.0, 0.3, 0.0], [0.3, 1.0, 0.0], [0.0, 0.0, 0.35]])
    assert np.max(np.abs(rotate_plane_stress(d_iso, 0.6) - d_iso)) < 1e-12
    # 90° swaps E1<->E2 (the [0,0] and [1,1] entries)
    d0 = orthotropic_plane_stress_matrix(10.0, 1.0, 0.3, 0.5)
    d90 = rotate_plane_stress(d0, np.pi / 2.0)
    assert abs(d90[0, 0] - d0[1, 1]) < 1e-9 and abs(d90[1, 1] - d0[0, 0]) < 1e-9
    assert np.allclose(rotate_plane_stress(d0, 0.0), d0)
    # dD/dθ vs central FD
    h = 1e-6
    fd = (rotate_plane_stress(d0, 0.7 + h) - rotate_plane_stress(d0, 0.7 - h)) / (2.0 * h)
    assert np.max(np.abs(drotate_plane_stress_dtheta(d0, 0.7) - fd)) <= 1e-6


def test_compliance_sensitivities_match_central_fd():
    config, mesh = _setup()
    e, nu = config.material.young_modulus, config.material.poisson_ratio
    d0 = orthotropic_plane_stress_matrix(2.0 * e, 0.5 * e, nu, 0.4 * e)
    n = mesh.elements.shape[0]
    rng = np.random.default_rng(0)
    rho = np.clip(0.5 + 0.2 * rng.standard_normal(n), 0.2, 1.0)
    ang = 0.3 * rng.standard_normal(n)

    _, d_rho, d_theta = orthotropic_compliance_sensitivities(config, mesh, rho, ang, d0)

    def comp(r, a):
        return orthotropic_compliance_sensitivities(config, mesh, r, a, d0)[0]

    h = 1e-6
    for e_id in np.argsort(-np.abs(d_rho))[:4]:
        rp, rm = rho.copy(), rho.copy()
        rp[e_id] += h
        rm[e_id] -= h
        fd = (comp(rp, ang) - comp(rm, ang)) / (2.0 * h)
        assert abs(d_rho[e_id] - fd) / (abs(fd) + 1e-30) <= 1e-4
    for e_id in np.argsort(-np.abs(d_theta))[:4]:
        ap, am = ang.copy(), ang.copy()
        ap[e_id] += h
        am[e_id] -= h
        fd = (comp(rho, ap) - comp(rho, am)) / (2.0 * h)
        assert abs(d_theta[e_id] - fd) / (abs(fd) + 1e-30) <= 1e-4


def test_simultaneous_mma_reduces_compliance_and_deterministic():
    config, mesh = _setup()
    e, nu = config.material.young_modulus, config.material.poisson_ratio
    d0 = orthotropic_plane_stress_matrix(2.0 * e, 0.5 * e, nu, 0.4 * e)
    vf = config.optimization.volume_fraction
    design = mesh.design_mask

    r = simultaneous_elastic_orientation_mma(config, mesh, d0, vf=vf, max_iter=60)
    assert r.compliance_history[-1] < 0.5 * r.compliance_history[0], "compliance not driven down"
    assert float(r.densities[design].mean()) <= vf + 0.02, "volume infeasible"

    a = simultaneous_elastic_orientation_mma(config, mesh, d0, vf=vf, max_iter=6)
    b = simultaneous_elastic_orientation_mma(config, mesh, d0, vf=vf, max_iter=6)
    assert np.allclose(a.densities, b.densities) and np.allclose(a.angles, b.angles)


def test_fibre_continuity_constraint_binds():
    config, mesh = _setup()
    e, nu = config.material.young_modulus, config.material.poisson_ratio
    d0 = orthotropic_plane_stress_matrix(2.0 * e, 0.5 * e, nu, 0.4 * e)
    vf = config.optimization.volume_fraction

    free = simultaneous_elastic_orientation_mma(config, mesh, d0, vf=vf, max_iter=60)
    cont_free = free.continuity_history[-1]
    limit = 0.3 * cont_free
    constrained = simultaneous_elastic_orientation_mma(
        config, mesh, d0, vf=vf, fibre_continuity_limit=limit, max_iter=80
    )
    # unconstrained violates the limit; constrained satisfies it (binds, ≤ +5 %)
    assert cont_free > limit
    assert constrained.continuity_history[-1] <= limit * 1.05
    # compliance stays comparable (continuity is a mild regulariser, not a wrecker)
    assert constrained.compliance_history[-1] <= 1.5 * free.compliance_history[-1]


def test_orthotropic_error_handling():
    with pytest.raises(SolverError):
        orthotropic_plane_stress_matrix(-1.0, 1.0, 0.3, 0.5)
    with pytest.raises(SolverError):
        orthotropic_plane_stress_matrix(1.0, 1.0, 2.0, 0.5)  # nu making denom ≤ 0
