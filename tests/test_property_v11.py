"""Property-based invariants for v11 exact-&-robust drivers (Wave ZZZ, D081).

Randomised invariants (hold for many inputs, not one anchor point):
- R2 is monotone under uniform front contraction toward the utopia;
- the d-dim Clayton Rosenblatt transform round-trips for random points/dimensions;
- qp-relaxation never amplifies a raw element stress (σ̃_e = ρ^q·σ_e ≤ σ_e).
"""

from __future__ import annotations

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import solve_linear_elastic
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.multi_objective_to import r2_indicator
from structure_optimizer.core.reliability import Marginal, build_clayton_rosenblatt
from structure_optimizer.core.stress import element_von_mises_stresses


def test_property_r2_monotone_under_contraction():
    """Contracting every front point toward the utopia (×s, 0<s<1) cannot raise R2."""
    rng = np.random.default_rng(0)
    ideal = np.array([0.0, 0.0])
    for _ in range(40):
        front = rng.uniform(0.5, 3.0, (rng.integers(2, 6), 2))
        s = float(rng.uniform(0.3, 0.95))
        r2_full = r2_indicator(front, ideal=ideal)
        r2_contracted = r2_indicator(front * s, ideal=ideal)
        assert r2_contracted <= r2_full + 1e-12


def test_property_clayton_d_rosenblatt_roundtrip():
    """z → x → z round-trips for random dimensions, thetas and points."""
    rng = np.random.default_rng(1)
    for _ in range(20):
        d = int(rng.integers(2, 6))
        theta = float(rng.uniform(0.3, 4.0))
        marg = [Marginal("normal", 0.0, 1.0) for _ in range(d)]
        tr = build_clayton_rosenblatt(marg, theta=theta)
        z = rng.standard_normal(d)
        z_back = tr.x_to_u(tr.u_to_x(z))
        assert np.max(np.abs(z - z_back)) <= 1e-7


def test_property_qp_relaxation_never_amplifies_stress():
    """The qp-relaxed element stress σ̃_e = ρ_e^q·σ_e is ≤ the raw σ_e for ρ∈(0,1]."""
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    n = mesh.elements.shape[0]
    rng = np.random.default_rng(2)
    q = 2.5
    for _ in range(20):
        rho = np.clip(rng.uniform(0.05, 1.0, n), 1e-6, 1.0)
        u = solve_linear_elastic(config, mesh, rho).displacements
        raw = element_von_mises_stresses(config, mesh, u)
        relaxed = np.power(rho, q) * raw
        assert np.all(relaxed <= raw + 1e-9)
