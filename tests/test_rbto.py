"""Wave MM (v7): reliability-based topology optimization (RBTO).

Quantitative anchors:
- The displacement limit state is linear in the load factor, so the FORM
  reliability index reproduces the closed form β = (d_allow−d_nom)/(cov·d_nom)
  to machine precision (the analytical anchor wiring FORM into the driver).
- rbto_simp returns a design meeting β ≥ β_target; a more demanding target
  needs more material (higher volume fraction) — the RBTO-vs-deterministic
  difference, quantified.
"""

from __future__ import annotations

from math import erf, sqrt

import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.rbto import (
    displacement_reliability,
    rbto_simp,
    reliability_tightened_volume_floor,
)


def _phi(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


# --- analytical reliability anchor -----------------------------------------

def test_form_reliability_matches_closed_form():
    d_nom, d_allow, cov = 0.8, 1.0, 0.15
    res = displacement_reliability(d_nom, d_allow, cov)
    beta_closed = (d_allow - d_nom) / (cov * d_nom)  # linear limit state → exact
    assert res.converged
    assert res.beta == pytest.approx(beta_closed, abs=1e-7)
    assert res.p_failure == pytest.approx(_phi(-beta_closed), abs=1e-9)


def test_reliability_monotone_in_margin_and_cov():
    # Larger margin (smaller d_nom) → higher β; larger cov → lower β.
    b_tight = displacement_reliability(0.9, 1.0, 0.15).beta
    b_loose = displacement_reliability(0.6, 1.0, 0.15).beta
    assert b_loose > b_tight > 0
    b_lowcov = displacement_reliability(0.8, 1.0, 0.05).beta
    b_hicov = displacement_reliability(0.8, 1.0, 0.30).beta
    assert b_lowcov > b_hicov


def test_reliability_origin_unsafe_when_nominal_exceeds_allowable():
    # d_nom > d_allow → origin (nominal load) already fails → β < 0.
    res = displacement_reliability(1.2, 1.0, 0.1)
    assert res.beta < 0
    assert res.p_failure > 0.5


def test_tightened_volume_floor_closed_form():
    assert reliability_tightened_volume_floor(0.2, 2.0) == pytest.approx(1.0 / 1.4)


def test_reliability_rejects_bad_inputs():
    with pytest.raises(SolverError, match="nonpositive_displacement"):
        displacement_reliability(0.0, 1.0, 0.1)
    with pytest.raises(SolverError, match="nonpositive_cov"):
        displacement_reliability(0.5, 1.0, 0.0)


# --- RBTO driver -----------------------------------------------------------

def _smoke():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def _d_nominal_at(config, mesh, vf: float) -> float:
    """Max displacement of the min-compliance design at volume fraction vf."""
    from dataclasses import replace

    from structure_optimizer.core.simp import run_simp
    cfg = replace(config, optimization=replace(config.optimization, volume_fraction=vf))
    return float(run_simp(cfg, mesh).final_analysis.max_displacement)


def test_rbto_meets_target_at_lightest_when_target_trivial():
    config, mesh = _smoke()
    # d_allow huge + beta_target 0 → the lightest vf already satisfies β ≥ 0.
    res = rbto_simp(config, mesh, d_allow=1e9, beta_target=0.0, load_cov=0.15,
                    vf_low=0.2, vf_high=0.6, max_iter=4)
    assert res.feasible
    assert res.beta >= res.beta_target
    assert res.volume_fraction == pytest.approx(0.2, abs=1e-9)


def test_rbto_higher_target_needs_more_volume():
    config, mesh = _smoke()
    # Calibrate d_allow from a mid-vf design so targets are achievable in-bracket.
    d_allow = _d_nominal_at(config, mesh, 0.45) * 1.6  # margin so β>0 is reachable

    low_target = rbto_simp(config, mesh, d_allow=d_allow, beta_target=1.0, load_cov=0.15,
                           vf_low=0.2, vf_high=0.8, vf_tol=0.05, max_iter=6)
    high_target = rbto_simp(config, mesh, d_allow=d_allow, beta_target=2.5, load_cov=0.15,
                            vf_low=0.2, vf_high=0.8, vf_tol=0.05, max_iter=6)
    assert low_target.feasible and high_target.feasible
    assert low_target.beta >= 1.0 - 1e-9
    assert high_target.beta >= 2.5 - 1e-9
    # More demanding reliability → at least as much material.
    assert high_target.volume_fraction >= low_target.volume_fraction - 1e-9


def test_rbto_infeasible_when_target_unreachable():
    config, mesh = _smoke()
    # Allowable barely above the densest displacement → even max material can't
    # reach a large β.
    d_allow = _d_nominal_at(config, mesh, 0.6) * 1.01
    res = rbto_simp(config, mesh, d_allow=d_allow, beta_target=5.0, load_cov=0.15,
                    vf_low=0.2, vf_high=0.6, max_iter=3)
    assert not res.feasible
    assert res.beta < res.beta_target


def test_rbto_rejects_bad_inputs():
    config, mesh = _smoke()
    with pytest.raises(SolverError, match="nonpositive_allowable"):
        rbto_simp(config, mesh, d_allow=0.0, beta_target=1.0)
    with pytest.raises(SolverError, match="invalid_vf_bracket"):
        rbto_simp(config, mesh, d_allow=1.0, beta_target=1.0, vf_low=0.8, vf_high=0.2)
