"""Wave S: Augmented Lagrangian wrapper for inequality-constrained SIMP.

Closes the v3.1 caveat (D007) where a simple quadratic penalty couldn't
guarantee strict stress-limit satisfaction: σ_PN ≤ σ_lim was only
encouraged, not enforced. The augmented Lagrangian method (Hestenes 1969,
Powell 1969; topology-optimization treatment Birgin & Martínez 2014)
iteratively updates a Lagrange-multiplier estimate so that on convergence
the constraint is satisfied to within a user-supplied feasibility tolerance.

For an inequality constraint ``g(x) ≤ 0`` the augmented Lagrangian is::

    L_A(x, μ, ρ) = f(x) + (1/(2ρ)) * ( max(0, μ + ρ g(x))^2 - μ² )

with gradient w.r.t. x::

    ∂L_A/∂x = ∂f/∂x + max(0, μ + ρ g(x)) * ∂g/∂x

Outer iteration update::

    μ ← max(0, μ + ρ g(x))     (Powell-Hestenes)
    ρ ← γ · ρ                    if |g(x)|_+ does not decrease enough

The outer loop terminates when ``g(x) ≤ feas_tol`` (constraint satisfied)
and ``|x_{k+1} - x_k| ≤ x_tol`` (design stable). Inner loop is any
gradient-based topology optimizer (OC or MMA) that minimizes ``L_A`` for
the current ``(μ, ρ)``.

This module deliberately keeps the AL update logic separate from the
inner-loop optimizer so it composes with both ``run_simp`` (OC) and the
new MMA driver.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class AugLagState:
    """Mutable state for the augmented-Lagrangian outer loop.

    ``mu`` is the multiplier estimate (one per inequality constraint);
    ``rho`` is the penalty coefficient; ``prev_violation`` tracks the
    previous |g|_+ so we know whether to grow ``rho``.
    """

    mu: np.ndarray  # shape (m,), Lagrange multiplier estimate, ≥ 0
    rho: float = 1.0  # penalty coefficient
    prev_violation: float | None = None
    growth: float = 2.0  # ρ growth factor when violation didn't shrink enough
    shrink_threshold: float = 0.5  # require new violation ≤ this × prev
    outer_iter: int = 0
    history: list[dict] = field(default_factory=list)

    @classmethod
    def init(cls, m: int, rho0: float = 1.0) -> AugLagState:
        return cls(mu=np.zeros(m, dtype=float), rho=rho0)


def augmented_objective(
    f: float,
    df: np.ndarray,
    g: np.ndarray,
    dg: np.ndarray,
    state: AugLagState,
) -> tuple[float, np.ndarray]:
    """Compute ``L_A(x, μ, ρ)`` and ``∂L_A/∂x`` from raw objective/constraint.

    Args:
        f: objective value f(x).
        df: ∂f/∂x, shape (n,).
        g: constraint values g(x), shape (m,). Convention g ≤ 0 feasible.
        dg: constraint Jacobian ∂g/∂x, shape (m, n).
        state: current ``AugLagState``.

    Returns:
        ``(L_A, ∂L_A/∂x)`` — augmented objective and its gradient.
    """
    g = np.atleast_1d(np.asarray(g, dtype=float))
    dg = np.atleast_2d(np.asarray(dg, dtype=float))
    if dg.shape == (g.size,) or dg.shape == (1, g.size) or dg.ndim == 1:
        dg = dg.reshape(g.size, -1)
    mu = state.mu
    rho = state.rho

    # ψ_i = max(0, μ_i + ρ g_i) — KKT-compatible inequality treatment
    psi = np.maximum(0.0, mu + rho * g)
    # Augmented objective: f + (1/(2ρ)) Σ (ψ² - μ²)
    aug_term = float(np.sum(psi**2 - mu**2) / (2.0 * rho))
    L_A = f + aug_term
    # Gradient: df + Σ_i ψ_i ∂g_i/∂x
    dL_A = df + psi @ dg
    return L_A, dL_A


def update_multipliers(
    g: np.ndarray,
    state: AugLagState,
) -> None:
    """Powell-Hestenes outer update: μ ← max(0, μ + ρ g); maybe grow ρ.

    Mutates ``state`` in place. Records per-outer-iteration diagnostics.
    """
    g = np.atleast_1d(np.asarray(g, dtype=float))
    violation = float(np.max(np.maximum(0.0, g)))

    new_mu = np.maximum(0.0, state.mu + state.rho * g)

    # Grow rho only if the violation didn't shrink "enough" since last outer
    grew = False
    if (
        state.prev_violation is not None
        and violation > 0.0
        and violation > state.shrink_threshold * state.prev_violation
    ):
        state.rho *= state.growth
        grew = True

    state.history.append(
        {
            "outer_iter": state.outer_iter,
            "mu_before": state.mu.copy(),
            "mu_after": new_mu.copy(),
            "rho": state.rho,
            "violation": violation,
            "rho_grew": grew,
        }
    )
    state.mu = new_mu
    state.prev_violation = violation
    state.outer_iter += 1


def auglag_minimize(
    x0: np.ndarray,
    objective_and_grad,
    constraints_and_jac,
    inner_step,
    feas_tol: float = 1e-3,
    x_tol: float = 1e-4,
    max_outer: int = 30,
    rho0: float = 1.0,
    state: AugLagState | None = None,
) -> dict:
    """Augmented-Lagrangian outer loop wrapping an arbitrary inner minimizer.

    Args:
        x0: initial design vector.
        objective_and_grad: callable ``x → (f, df/dx)``.
        constraints_and_jac: callable ``x → (g, dg/dx)`` (g ≤ 0 feasible).
        inner_step: callable
            ``(x, state, objective_and_grad_aug) → x_new``
            performing one or more iterations of an inner optimizer on the
            augmented objective. The simplest implementation is a single
            OC / MMA step; more elaborate is to run inner-to-convergence.
        feas_tol: outer-loop stop when ``max(g)+ ≤ feas_tol``.
        x_tol: outer-loop stop when ``|x_new - x|∞ ≤ x_tol``.
        max_outer: cap on outer iterations.
        rho0: initial penalty.
        state: pre-seeded ``AugLagState`` (else fresh zero-multiplier start).

    Returns:
        dict with ``x``, ``f``, ``g``, ``state``, ``outer_iter``, ``stop_reason``.
    """
    x = np.asarray(x0, dtype=float).copy()
    g_init, _ = constraints_and_jac(x)
    g_init = np.atleast_1d(np.asarray(g_init, dtype=float))
    if state is None:
        state = AugLagState.init(g_init.size, rho0=rho0)

    stop_reason = "max_outer"
    f = 0.0
    g = g_init
    for _ in range(max_outer):

        def aug_obj_grad(xx, _state=state):
            ff, dff = objective_and_grad(xx)
            gg, dgg = constraints_and_jac(xx)
            return augmented_objective(ff, dff, gg, dgg, _state)

        x_new = inner_step(x, state, aug_obj_grad)
        x_change = float(np.max(np.abs(x_new - x)))
        x = x_new

        f, _ = objective_and_grad(x)
        g, _ = constraints_and_jac(x)
        g_arr = np.atleast_1d(np.asarray(g, dtype=float))
        violation = float(np.max(np.maximum(0.0, g_arr)))

        update_multipliers(g_arr, state)

        if violation <= feas_tol and x_change <= x_tol:
            stop_reason = "converged"
            break
        if x_change <= x_tol and violation > feas_tol:
            # Stuck but infeasible — boost ρ and continue
            state.rho *= state.growth

    return {
        "x": x,
        "f": f,
        "g": g,
        "state": state,
        "outer_iter": state.outer_iter,
        "stop_reason": stop_reason,
    }
