"""Wave FFFF (v12, D087): period-aware fibre continuity (sin²Δθ) + laminate [A,B,D].

Quantitative anchors (closed form + FD, not qualitative trend):
- **π-periodicity**: the sin² metric is invariant to adding π to a ply angle and
  vanishes at Δθ=π, so a ±89° seam scores ~sin²(2°) — not the 178°-jump the squared
  metric (D079) reports; for small Δθ it degenerates to D079's metric (ratio→1);
- **analytic continuity gradient vs central FD** ≤ 1e-6;
- **laminate [A,B,D]**: single centred ply gives A=Q̄·t, B=0, D=Q̄·t³/12 exactly; a
  mid-plane-symmetric stack gives B=0; an unsymmetric [0/90] stack gives B≠0;
- the MMA driver's ``periodic_continuity=True`` does **not** penalise a ±89° seam
  that the default (D079) metric flags as a large discontinuity.

D079's reopening criterion: "period-aware fibre continuity (sin²Δθ) + laminates".
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.orthotropic_simp import (
    _continuity_metric,
    laminate_abd,
    orthotropic_plane_stress_matrix,
    period_aware_continuity,
    rotate_plane_stress,
    simultaneous_elastic_orientation_mma,
)

D0 = orthotropic_plane_stress_matrix(130e9, 10e9, 0.28, 5e9)


def test_period_pi_invariance_and_pm89_not_penalised():
    a89, am89 = np.deg2rad(89.0), np.deg2rad(-89.0)
    pairs = [(0, 1)]
    # ±89° seam: period-aware ≈ sin²(2°) tiny; squared metric ≈ (178°)² huge
    sin2, _ = period_aware_continuity(np.array([a89, am89]), pairs)
    sq, _ = _continuity_metric(np.array([a89, am89]), pairs)
    assert sin2 < 2e-3, f"period-aware over-penalised ±89° seam ({sin2})"
    assert sq > 9.0, "sanity: squared metric should see a large jump"
    # adding π to one ply leaves the period-aware metric unchanged (same fibre)
    base, _ = period_aware_continuity(np.array([np.deg2rad(30.0), np.deg2rad(50.0)]), pairs)
    plus_pi, _ = period_aware_continuity(np.array([np.deg2rad(30.0) + np.pi, np.deg2rad(50.0)]), pairs)
    assert abs(base - plus_pi) <= 1e-12


def test_small_angle_degenerates_to_squared_metric():
    pairs = [(0, 1)]
    angles = np.array([np.deg2rad(1.0), np.deg2rad(-1.0)])  # 2° apart
    sin2, _ = period_aware_continuity(angles, pairs)
    sq, _ = _continuity_metric(angles, pairs)
    assert abs(sin2 / sq - 1.0) <= 1e-3, "small-angle period-aware should ≈ squared metric"


def test_continuity_gradient_matches_central_fd():
    rng = np.random.default_rng(0)
    angles = rng.uniform(-np.pi / 2, np.pi / 2, size=5)
    pairs = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 4)]
    _, grad = period_aware_continuity(angles, pairs)
    h = 1e-6
    for e in range(5):
        ap, am = angles.copy(), angles.copy()
        ap[e] += h
        am[e] -= h
        fd = (period_aware_continuity(ap, pairs)[0] - period_aware_continuity(am, pairs)[0]) / (2 * h)
        assert abs(grad.get(e, 0.0) - fd) <= 1e-6, f"elem {e}: analytic {grad.get(e,0.0)} vs FD {fd}"


def test_single_ply_abd_closed_form():
    t = 2.0
    A, B, D = laminate_abd(D0, np.array([0.0]), np.array([t]))
    q = rotate_plane_stress(D0, 0.0)
    assert np.allclose(A, q * t)
    assert np.abs(B).max() <= 1e-3
    assert np.allclose(D, q * t**3 / 12.0)


def test_symmetric_stack_has_zero_coupling_unsymmetric_does_not():
    # mid-plane-symmetric [45/-45/-45/45] ⟹ B = 0
    ang_sym = np.deg2rad([45.0, -45.0, -45.0, 45.0])
    _, B_sym, _ = laminate_abd(D0, ang_sym, np.full(4, 0.5))
    assert np.abs(B_sym).max() <= 1e-3
    # unsymmetric [0/90] ⟹ B ≠ 0 (extension–bending coupling)
    _, B_unsym, _ = laminate_abd(D0, np.deg2rad([0.0, 90.0]), np.full(2, 1.0))
    assert np.abs(B_unsym).max() > 1.0
    # A and D are symmetric
    A, _, D = laminate_abd(D0, ang_sym, np.full(4, 0.5))
    assert np.allclose(A, A.T) and np.allclose(D, D.T)


def test_driver_periodic_continuity_accepts_pm89_seam():
    """A design with a ±89° seam is nearly continuous in fibre orientation; the
    period-aware driver metric reports a small continuity value where the default
    (squared) metric reports a large one."""
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    n = mesh.elements.shape[0]
    # checkerboard of +89/-89 over the design cells
    init = np.where(np.arange(n) % 2 == 0, np.deg2rad(89.0), np.deg2rad(-89.0))
    r_per = simultaneous_elastic_orientation_mma(
        config, mesh, D0, init_angles=init, max_iter=1, periodic_continuity=True
    )
    r_sq = simultaneous_elastic_orientation_mma(
        config, mesh, D0, init_angles=init, max_iter=1, periodic_continuity=False
    )
    assert r_per.continuity_history[0] < 2e-3, "period-aware driver over-penalised the ±89° seam"
    assert r_sq.continuity_history[0] > 1.0, "sanity: squared driver metric sees a large jump"


def test_guards():
    with pytest.raises(SolverError, match="laminate_no_plies"):
        laminate_abd(D0, np.array([]), np.array([]))
    with pytest.raises(SolverError, match="thickness_count_mismatch"):
        laminate_abd(D0, np.array([0.0, 0.5]), np.array([1.0]))
    with pytest.raises(SolverError, match="nonpositive_thickness"):
        laminate_abd(D0, np.array([0.0]), np.array([0.0]))
