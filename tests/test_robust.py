"""Wave U tests for Heaviside / robust three-field formulation."""

from __future__ import annotations

import itertools

import numpy as np
import pytest
from structure_optimizer.core.robust import (
    HeavisideParams,
    RobustFields,
    beta_schedule,
    heaviside_project,
    heaviside_project_grad,
    project_robust_fields,
    worst_case_compliance,
)


def test_heaviside_projects_to_unit_interval():
    """H ∈ [0, 1] for ρ̃ ∈ [0, 1] across reasonable β values."""
    rho = np.linspace(0, 1, 50)
    for beta in [0.5, 1.0, 5.0, 20.0]:
        for eta in [0.3, 0.5, 0.7]:
            proj = heaviside_project(rho, HeavisideParams(eta=eta, beta=beta))
            assert proj.min() >= -1e-9, f"min<0 at β={beta},η={eta}: {proj.min()}"
            assert proj.max() <= 1.0 + 1e-9


def test_heaviside_at_threshold_equals_half():
    """At ρ̃ = η, H = (tanh(βη) + 0) / (tanh(βη) + tanh(β(1-η)))."""
    rho = np.array([0.5])
    proj = heaviside_project(rho, HeavisideParams(eta=0.5, beta=10.0))
    # When η = 0.5 (symmetric), H(0.5) = 0.5 exactly
    assert abs(proj[0] - 0.5) < 1e-9


def test_heaviside_endpoints_zero_and_one():
    """H(0, η, β) = 0 and H(1, η, β) = 1 for any β."""
    for beta in [1.0, 5.0, 20.0]:
        for eta in [0.3, 0.5, 0.7]:
            assert abs(heaviside_project(np.array([0.0]), HeavisideParams(eta, beta))[0]) < 1e-9
            assert abs(heaviside_project(np.array([1.0]), HeavisideParams(eta, beta))[0] - 1.0) < 1e-9


def test_heaviside_monotonic_in_rho():
    """H is monotone increasing in ρ̃."""
    rho = np.linspace(0, 1, 100)
    for beta in [1.0, 5.0, 20.0]:
        proj = heaviside_project(rho, HeavisideParams(eta=0.5, beta=beta))
        assert np.all(np.diff(proj) >= -1e-12)


def test_heaviside_sharpens_with_beta():
    """Larger β → sharper transition (larger gradient at η)."""
    rho = np.array([0.5])
    g_low = heaviside_project_grad(rho, HeavisideParams(eta=0.5, beta=1.0))
    g_high = heaviside_project_grad(rho, HeavisideParams(eta=0.5, beta=20.0))
    assert g_high[0] > g_low[0]


def test_heaviside_grad_via_finite_difference():
    """Analytical grad should match FD on the smooth interior."""
    rho = np.array([0.4])
    params = HeavisideParams(eta=0.5, beta=5.0)
    analytical = heaviside_project_grad(rho, params)
    eps = 1e-7
    fd = (heaviside_project(rho + eps, params) - heaviside_project(rho - eps, params)) / (2 * eps)
    np.testing.assert_allclose(analytical, fd, atol=1e-5)


def test_heaviside_zero_beta_returns_identity():
    """β = 0 (degenerate) → no projection, identity."""
    rho = np.array([0.1, 0.5, 0.9])
    proj = heaviside_project(rho, HeavisideParams(eta=0.5, beta=0.0))
    np.testing.assert_allclose(proj, rho)


def test_robust_fields_ordering():
    """eroded ≤ nominal ≤ dilated for every element."""
    rho = np.linspace(0, 1, 20)
    fields = project_robust_fields(rho, eta_eroded=0.6, eta_dilated=0.4, beta=5.0)
    assert isinstance(fields, RobustFields)
    assert np.all(fields.eroded <= fields.nominal + 1e-12)
    assert np.all(fields.nominal <= fields.dilated + 1e-12)


def test_robust_fields_invalid_thresholds_raise():
    """eta_eroded < 0.5 or eta_dilated > 0.5 → ValueError."""
    with pytest.raises(ValueError, match="thresholds must satisfy"):
        project_robust_fields(np.array([0.5]), eta_eroded=0.4, eta_dilated=0.6)
    with pytest.raises(ValueError, match="thresholds must satisfy"):
        project_robust_fields(np.array([0.5]), eta_eroded=0.6, eta_dilated=0.7)


def test_robust_eta_min_mean_max_correspondence():
    """Three fields with η ∈ {0.4, 0.5, 0.6} correspond to dilated/nominal/eroded."""
    rho = np.array([0.5])
    fields = project_robust_fields(rho, eta_eroded=0.6, eta_dilated=0.4, beta=10.0)
    # At ρ̃=0.5, η_eroded=0.6 (above threshold): projection pushes down toward 0
    # η_dilated=0.4 (below threshold): projection pushes up toward 1
    assert fields.eroded[0] < fields.nominal[0]
    assert fields.nominal[0] < fields.dilated[0]


def test_worst_case_compliance_picks_max():
    """Worst-case compliance returns the field name + max value."""
    field, c = worst_case_compliance({"eroded": 12.0, "nominal": 10.0, "dilated": 8.5})
    assert field == "eroded"
    assert c == 12.0
    # Tie-broken consistently (max returns first encountered max)
    name, value = worst_case_compliance({"a": 5.0, "b": 5.0})
    assert value == 5.0
    assert name in {"a", "b"}


def test_beta_schedule_monotone_and_clamped():
    """β should monotonically increase and clamp at target."""
    iters = list(range(0, 100, 10))
    betas = [beta_schedule(i, 1.0, 32.0, 50) for i in iters]
    # Monotone non-decreasing
    for prev, curr in itertools.pairwise(betas):
        assert curr >= prev - 1e-9
    # Starts at 1.0
    assert betas[0] == 1.0
    # Reaches target by iter 50
    assert beta_schedule(50, 1.0, 32.0, 50) == 32.0
    # Past target, stays at target
    assert beta_schedule(80, 1.0, 32.0, 50) == 32.0


def test_eta_min_mean_max_three_field_benchmark_compare():
    """Comparison benchmark anchor: a known-bad gray design should have
    eroded ≪ nominal in mass, demonstrating the eroded field's
    conservativism. Used by rubric §1.6 evidence."""
    # Heavily gray design: all densities at 0.5 (worst case for binarization)
    rho_gray = np.full(100, 0.5)
    fields = project_robust_fields(rho_gray, eta_eroded=0.7, eta_dilated=0.3, beta=15.0)
    # Eroded (high threshold) should have much less mass than dilated
    mass_eroded = float(fields.eroded.sum())
    mass_nominal = float(fields.nominal.sum())
    mass_dilated = float(fields.dilated.sum())
    assert mass_eroded < mass_nominal < mass_dilated
    # The gap eroded vs dilated demonstrates the manufacturing uncertainty
    # the robust formulation guards against
    assert mass_dilated - mass_eroded > 0.5 * mass_nominal
