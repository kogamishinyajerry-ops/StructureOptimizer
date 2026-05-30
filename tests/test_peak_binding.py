"""Wave GGGGGG (v14, D104) — peak-binding flanking-mode (closes D091's twice-deferred
criterion).

D091 placed the operating frequency ω_op near the fundamental ω₁, where minimising the
response *lowered* the whole transfer function — objective and constraint **aligned**, so
"in-loop re-gridding changes the design" could not be shown, and it deferred. The missing
ingredient is placing ω_op in the **anti-resonance valley between two modes**: deepening
the anti-resonance there *raises* the neighbouring (flanking) resonance, so the objective
and the flanking-peak constraint genuinely couple.

Quantitative anchors against an independent dense frequency sweep, never qualitative
trends. **Honest scope (see D104):** the flanking constraint is NOT strictly KKT-binding
(it never sits active at the limit and J is not sacrificed — the constrained problem finds
a basin low in both); what is demonstrated is the *coupling* (min J(ω_op) raises the
flank) + the *design change* from constraining it + in-loop re-gridding changing the
design.
"""

import numpy as np
import pytest
from structure_optimizer.benchmarks import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.freq_response import (
    _dynamic_compliance_objective,
    peak_binding_mma,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.modal import solve_modal

_BETA = 2e-6


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    opt = config.optimization
    rho0 = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    w = np.sqrt(solve_modal(config, mesh, rho0, n_modes=3).omega_squared)
    w_op = 0.5 * (w[0] + w[1])  # anti-resonance valley between modes 1 and 2
    flo, fhi = 0.85 * w[1], 1.15 * w[1]  # flanking band around mode 2
    return config, mesh, rho0, w_op, flo, fhi


def _dense_flank(config, mesh, rho, lo, hi, n=150):
    return max(_dynamic_compliance_objective(config, mesh, rho, w, beta=_BETA) for w in np.linspace(lo, hi, n))


@pytest.fixture(scope="module")
def runs():
    config, mesh, rho0, w_op, flo, fhi = _setup()
    init = _dense_flank(config, mesh, rho0, flo, fhi)
    unconstr = peak_binding_mma(
        config, mesh, w_op, flo, fhi, peak_limit=1e9 * init, beta=_BETA, max_iter=25, regrid=True
    )
    lim = 1.2 * init
    regrid = peak_binding_mma(config, mesh, w_op, flo, fhi, peak_limit=lim, beta=_BETA, max_iter=25, regrid=True)
    stale = peak_binding_mma(config, mesh, w_op, flo, fhi, peak_limit=lim, beta=_BETA, max_iter=25, regrid=False)
    return {
        "cfg": (config, mesh, flo, fhi),
        "init": init,
        "unconstr": unconstr,
        "regrid": regrid,
        "stale": stale,
        "flank": lambda r: _dense_flank(config, mesh, r.densities, flo, fhi),
    }


def test_minimizing_dynamic_compliance_raises_flanking_resonance(runs):
    """The D091 blocker, now resolved: unconstrained min J(ω_op) in the valley RAISES the
    flanking resonance (dense sweep) instead of lowering it."""
    init = runs["init"]
    unconstr_flank = runs["flank"](runs["unconstr"])
    # the objective itself dropped (the anti-resonance deepened) ...
    assert runs["unconstr"].dyn_compliance_history[-1] < runs["unconstr"].dyn_compliance_history[0]
    # ... while the flanking resonance ROSE — the coupling D091 could not exhibit.
    assert unconstr_flank > init * 1.05


def test_flanking_constraint_changes_the_design(runs):
    """Constraining the flanking peak yields a design with a much lower flanking
    resonance than the unconstrained optimum — the constraint demonstrably changes the
    design."""
    unconstr_flank = runs["flank"](runs["unconstr"])
    constr_flank = runs["flank"](runs["regrid"])
    assert constr_flank < 0.7 * unconstr_flank  # flanking peak controlled
    # and the density field genuinely differs
    drho = np.linalg.norm(runs["regrid"].densities - runs["unconstr"].densities)
    assert drho > 1e-6


def test_inloop_regridding_changes_the_design(runs):
    """In-loop re-gridding (tracking the moving flanking resonance) produces a different
    design than a band frozen at the initial flanking location."""
    rel = np.linalg.norm(runs["regrid"].densities - runs["stale"].densities) / np.linalg.norm(runs["stale"].densities)
    assert rel > 0.05  # designs differ by > 5%
    # the tracked flanking resonance actually moves over the optimisation (re-gridding
    # is doing real work, not re-measuring a static peak)
    wh = np.array(runs["regrid"].flanking_omega_history)
    assert (wh.max() - wh.min()) / wh.mean() > 0.02


def test_peak_binding_feasible_against_dense_sweep(runs):
    """The constrained (regrid) design's true flanking peak respects the limit (dense
    sweep), confirming the in-loop p-norm constraint is faithful."""
    true_flank = runs["flank"](runs["regrid"])
    assert true_flank <= runs["regrid"].peak_limit * 1.15


def test_peak_binding_deterministic():
    """Same inputs ⟹ bit-identical design (no randomness in the driver)."""
    config, mesh, _rho0, w_op, flo, fhi = _setup()
    kw = dict(beta=_BETA, max_iter=6, regrid=True)
    a = peak_binding_mma(config, mesh, w_op, flo, fhi, peak_limit=1e6, **kw)
    b = peak_binding_mma(config, mesh, w_op, flo, fhi, peak_limit=1e6, **kw)
    assert np.array_equal(a.densities, b.densities)


def test_peak_binding_guards():
    """ω_op ≤ 0, invalid flanking range, nonpositive limit raise SolverError."""
    config, mesh, _rho0, w_op, flo, fhi = _setup()
    with pytest.raises(SolverError, match="peak_binding_nonpositive_omega"):
        peak_binding_mma(config, mesh, 0.0, flo, fhi, peak_limit=1.0)
    with pytest.raises(SolverError, match="adaptive_band_invalid_range"):
        peak_binding_mma(config, mesh, w_op, fhi, flo, peak_limit=1.0)
    with pytest.raises(SolverError, match="peak_constrained_nonpositive_limit"):
        peak_binding_mma(config, mesh, w_op, flo, fhi, peak_limit=0.0)
