"""Wave DDDDDDDD (v16, D117) — exact KKT (envelope-theorem shadow-price) multiplier for the
flanking-peak constraint, upgrading D109's relative-sacrifice proxy J/J_ref−1.

The multiplier λ = −dJ*/d(limit) is the EXACT Lagrange multiplier for a differentiable value
function (envelope theorem). The machinery is verified exactly on controlled value functions
(closed-form λ), and applied to the production peak_binding_mma in its firmly-active regime
(λ>0). Cross-regime stability is honestly DEFERRED — the non-convex in-loop-regridded MMA
makes J*(limit) noise-dominated in the inactive regime (probe in D117 ADR). Quantitative
analytical anchors, never qualitative trends.
"""

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.freq_response import peak_binding_exact_multiplier


def test_exact_recovery_inverse_value_function():
    """Headline: for J*(L)=A/L the shadow price is λ=A/L² in closed form; the central-FD
    envelope multiplier recovers it (the machinery is exact for a differentiable J*)."""
    a = 100.0
    lam = peak_binding_exact_multiplier(lambda L: a / L, limit=5.0, rel_delta=0.01)
    assert lam == pytest.approx(a / 25.0, abs=1e-2)  # A/L² = 4.0


def test_linear_value_function_is_exact():
    """For a linear J*(L)=c−mL the central FD is exact: λ=m to machine precision."""
    lam = peak_binding_exact_multiplier(lambda L: 1000.0 - 3.0 * L, limit=8.0, rel_delta=0.05)
    assert lam == pytest.approx(3.0, abs=1e-9)


def test_flat_value_function_zero_multiplier():
    """An inactive constraint (J* independent of the limit) has λ=0 exactly — the
    envelope theorem's signature of inactivity."""
    lam = peak_binding_exact_multiplier(lambda L: 42.0, limit=3.0, rel_delta=0.1)
    assert lam == pytest.approx(0.0, abs=1e-12)


def test_active_constraint_positive_multiplier():
    """A feasible-monotone value function (J* decreasing as the limit relaxes) gives λ>0 —
    the KKT sign of an active constraint (relaxing the limit lowers the optimum)."""
    lam = peak_binding_exact_multiplier(lambda L: max(0.0, 20.0 - L), limit=5.0, rel_delta=0.02)
    assert lam == pytest.approx(1.0, abs=1e-9)
    assert lam > 0.0


def test_central_difference_converges():
    """The central-FD multiplier converges as rel_delta shrinks (O(δ²) for smooth J*),
    both estimates bracketing the closed-form λ=A/L²."""
    a, limit = 100.0, 5.0
    exact = a / limit**2
    lam_coarse = peak_binding_exact_multiplier(lambda L: a / L, limit, rel_delta=0.05)
    lam_fine = peak_binding_exact_multiplier(lambda L: a / L, limit, rel_delta=0.005)
    assert abs(lam_fine - exact) < abs(lam_coarse - exact)


def test_kkt_exact_multiplier_guards():
    """Guards: rel_delta out of (0,1) and non-positive limit raise SolverError."""
    with pytest.raises(SolverError, match="kkt_shadow_rel_delta_range"):
        peak_binding_exact_multiplier(lambda L: 1.0 / L, limit=5.0, rel_delta=0.0)
    with pytest.raises(SolverError, match="kkt_shadow_rel_delta_range"):
        peak_binding_exact_multiplier(lambda L: 1.0 / L, limit=5.0, rel_delta=1.0)
    with pytest.raises(SolverError, match="kkt_shadow_nonpositive_limit"):
        peak_binding_exact_multiplier(lambda L: 1.0 / L, limit=0.0)


def test_production_active_regime_positive_shadow_price(request):
    """Production application: at a firmly-active tight limit (0.08·init) the exact shadow
    price of peak_binding_mma's J*(limit) is positive — the genuine KKT multiplier where a
    multiplier matters (deterministic; cross-regime stability is deferred, see D117 ADR).

    Slow (two peak_binding_mma solves); skip unless --run-slow."""
    if not request.config.getoption("--run-slow", default=False):
        pytest.skip("slow test; pass --run-slow to enable")
    from structure_optimizer.benchmarks import load_benchmark
    from structure_optimizer.core.freq_response import _dynamic_compliance_objective, peak_binding_mma
    from structure_optimizer.core.mesh import create_structured_mesh
    from structure_optimizer.core.modal import solve_modal

    beta = 2e-6
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    opt = config.optimization
    rho0 = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    w = np.sqrt(solve_modal(config, mesh, rho0, n_modes=3).omega_squared)
    w_op = 0.5 * (w[0] + w[1])
    flo, fhi = 0.85 * w[1], 1.15 * w[1]
    init = max(_dynamic_compliance_objective(config, mesh, rho0, ww, beta=beta) for ww in np.linspace(flo, fhi, 120))

    def j_star(limit):
        return peak_binding_mma(
            config, mesh, w_op, flo, fhi, peak_limit=limit, beta=beta, max_iter=20
        ).dyn_compliance_history[-1]

    lam = peak_binding_exact_multiplier(j_star, 0.08 * init, rel_delta=0.125)
    assert lam > 0.0  # firmly-active ⟹ relaxing the limit lowers J* ⟹ positive shadow price
