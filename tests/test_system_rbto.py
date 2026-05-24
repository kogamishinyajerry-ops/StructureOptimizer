"""Wave HHH (v9, D063): system-reliability-based TO (drive to a target system β).

Quantitative anchors:
- the volume bisection reaches a design whose series-system β meets the target,
  and the system β is below the smallest single-mode β (two independent ways to
  fail make the system harder than any one mode);
- a single mode reduces exactly to D042 ``rbto_simp``;
- the selected volume fraction is monotone non-decreasing in the target β;
- the exact independent series failure probability lies within the D055
  Ditlevsen bounds (consistency with the system-reliability module).
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.rbto import rbto_simp, system_rbto_simp
from structure_optimizer.core.reliability import system_reliability_series
from structure_optimizer.core.simp import run_simp


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    d_mid = float(run_simp(replace(config, optimization=replace(config.optimization, volume_fraction=0.45)), mesh).final_analysis.max_displacement)
    return config, mesh, d_mid * 1.6  # allowable in-bracket


def test_system_rbto_meets_target_and_harder_than_single_mode():
    config, mesh, da = _setup()
    res = system_rbto_simp(config, mesh, [da, da * 1.1], beta_target=2.0,
                           load_covs=[0.15, 0.15], vf_low=0.2, vf_high=0.85)
    assert res.feasible
    assert res.beta_system >= 2.0 - 1e-9
    # an independent 2-mode series system is harder than either mode alone
    assert res.beta_system < min(res.per_mode_betas)


def test_single_mode_reduces_to_rbto():
    config, mesh, da = _setup()
    sm = system_rbto_simp(config, mesh, [da], beta_target=2.0, load_covs=[0.15], vf_low=0.2, vf_high=0.85)
    rb = rbto_simp(config, mesh, d_allow=da, beta_target=2.0, load_cov=0.15, vf_low=0.2, vf_high=0.85)
    assert sm.volume_fraction == pytest.approx(rb.volume_fraction, abs=1e-9)
    assert sm.beta_system == pytest.approx(rb.beta, abs=1e-9)


def test_volume_monotone_in_target_beta():
    config, mesh, da = _setup()
    lo = system_rbto_simp(config, mesh, [da], beta_target=1.5, load_covs=[0.15], vf_low=0.2, vf_high=0.85)
    hi = system_rbto_simp(config, mesh, [da], beta_target=3.0, load_covs=[0.15], vf_low=0.2, vf_high=0.85)
    assert lo.volume_fraction <= hi.volume_fraction + 1e-9


def test_system_pf_within_ditlevsen_bounds():
    config, mesh, da = _setup()
    res = system_rbto_simp(config, mesh, [da, da * 1.1], beta_target=2.0,
                           load_covs=[0.15, 0.2], vf_low=0.2, vf_high=0.85)
    bounds = system_reliability_series(res.per_mode_betas)
    assert bounds["p_failure_lower"] - 1e-9 <= res.p_failure_system <= bounds["p_failure_upper"] + 1e-9


def test_contracts():
    config, mesh, da = _setup()
    with pytest.raises(SolverError, match="system_rbto_no_modes"):
        system_rbto_simp(config, mesh, [], beta_target=2.0)
    with pytest.raises(SolverError, match="system_rbto_cov_shape_mismatch"):
        system_rbto_simp(config, mesh, [da, da], beta_target=2.0, load_covs=[0.1])
    with pytest.raises(SolverError, match="rbto_negative_beta_target"):
        system_rbto_simp(config, mesh, [da], beta_target=-1.0)
