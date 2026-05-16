"""Wave S: Method of Moving Asymptotes (MMA) — pure-NumPy implementation.

Industrial-standard gradient-based optimizer for topology optimization with
multiple constraints. Replaces Optimality Criteria (OC) for problems where
OC's bisection-on-volume structure can't accommodate stress / buckling /
robust constraints simultaneously.

The algorithm builds a *separable convex approximation* of objective and
constraints around the current iterate, using moving asymptotes (L_j, U_j)
that adapt to the iteration history (closer in oscillating, farther in
monotonic). The subproblem is solved via its dual (one variable per
constraint), which is much smaller than the primal (one per density).

References:
    Svanberg, K. (1987). "The method of moving asymptotes — a new method
        for structural optimization." *Int. J. Numer. Meth. Eng.* 24,
        359–373.
    Svanberg, K. (2002). "A class of globally convergent optimization
        methods based on conservative convex separable approximations."
        *SIAM J. Optim.* 12, 555–573.

This module implements the 1987 version (no GCMMA convexification) with
the standard asymptote-adaptation heuristic. Suitable for SIMP topology
optimization with volume + (optionally) one or more inequality constraints
such as stress p-norm. ~400 LOC pure NumPy, no scipy required for the
dual subproblem (we use a damped Newton step with bracket-fallback).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class MMAState:
    """Mutable iteration state for the MMA outer loop.

    Holds the last two iterates needed to detect oscillation and to grow /
    shrink the asymptote envelope. Callers create one ``MMAState`` for the
    entire optimization and pass it back through each ``mma_step``.
    """

    x_prev1: np.ndarray | None = None  # x at iteration k-1
    x_prev2: np.ndarray | None = None  # x at iteration k-2
    low: np.ndarray | None = None  # current lower asymptote L
    upp: np.ndarray | None = None  # current upper asymptote U
    iteration: int = 0  # 0-indexed; ++ after every step

    # Tunables (Svanberg 1987 §3 defaults)
    asyinit: float = 0.5  # initial half-width factor for L, U
    asyincr: float = 1.2  # asymptote-relax factor on monotonic moves
    asydecr: float = 0.7  # asymptote-tighten factor on oscillating moves
    move_limit: float = 0.2  # max |x_new - x| per step (fraction of span)
    raa0: float = 1e-5  # small floor on (U - x) and (x - L)
    history: list[dict] = field(default_factory=list)  # diagnostic per-iter records


def _update_asymptotes(
    x: np.ndarray,
    state: MMAState,
    xmin: np.ndarray,
    xmax: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute the current asymptote pair (L, U) per Svanberg 1987 eq. (3.11-3.13)."""
    span = xmax - xmin
    if state.iteration < 2 or state.x_prev1 is None or state.x_prev2 is None:
        # Bootstrap (iterations 0, 1): symmetric half-window
        low = x - state.asyinit * span
        upp = x + state.asyinit * span
    else:
        assert state.low is not None and state.upp is not None
        # Oscillation indicator: sign(x_k - x_{k-1}) vs sign(x_{k-1} - x_{k-2})
        # Positive product → monotonic (relax asymptote, gamma = asyincr)
        # Negative product → oscillating (tighten asymptote, gamma = asydecr)
        sign = (x - state.x_prev1) * (state.x_prev1 - state.x_prev2)
        gamma = np.ones_like(x)
        gamma[sign < 0] = state.asydecr
        gamma[sign > 0] = state.asyincr
        low = x - gamma * (state.x_prev1 - state.low)
        upp = x + gamma * (state.upp - state.x_prev1)
        # Clamp to a reasonable window around the design box to avoid runaway
        low = np.maximum(low, x - 10.0 * span)
        low = np.minimum(low, x - 0.01 * span)
        upp = np.minimum(upp, x + 10.0 * span)
        upp = np.maximum(upp, x + 0.01 * span)
    return low, upp


def _build_subproblem(
    x: np.ndarray,
    df0dx: np.ndarray,
    fval: np.ndarray,
    dfdx: np.ndarray,
    low: np.ndarray,
    upp: np.ndarray,
    raa0: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build the MMA convex separable subproblem coefficients.

    For each variable j and each constraint i (plus the objective i=0),
    the local convex approximation is:
        f̃_i(x) = r_i + Σ_j [ p_{ij} / (U_j - x_j) + q_{ij} / (x_j - L_j) ]

    where (Svanberg 1987 eq. 3.9-3.10):
        p_{ij} = (U_j - x_j)^2 · max(∂f_i/∂x_j, 0)
        q_{ij} = (x_j - L_j)^2 · max(-∂f_i/∂x_j, 0)
        r_i = f_i(x) - Σ_j [ p_{ij}/(U_j-x_j) + q_{ij}/(x_j-L_j) ]

    The ``raa0`` floor adds a tiny ε to keep p, q strictly positive even
    when ∂f/∂x is zero — required for the dual subproblem's Hessian.
    """
    ux = np.maximum(upp - x, raa0)
    xl = np.maximum(x - low, raa0)
    ux2 = ux * ux
    xl2 = xl * xl

    df0_pos = np.maximum(df0dx, 0.0)
    df0_neg = np.maximum(-df0dx, 0.0)
    p0 = ux2 * (df0_pos + 0.001 * np.abs(df0dx) + raa0)
    q0 = xl2 * (df0_neg + 0.001 * np.abs(df0dx) + raa0)

    m = fval.size
    n = x.size
    P = np.zeros((m, n))
    Q = np.zeros((m, n))
    for i in range(m):
        dfi_pos = np.maximum(dfdx[i], 0.0)
        dfi_neg = np.maximum(-dfdx[i], 0.0)
        P[i] = ux2 * (dfi_pos + 0.001 * np.abs(dfdx[i]) + raa0)
        Q[i] = xl2 * (dfi_neg + 0.001 * np.abs(dfdx[i]) + raa0)

    b = (P / ux + Q / xl).sum(axis=1) - fval

    return p0, q0, P, Q, b


def _solve_dual_subproblem(
    p0: np.ndarray,
    q0: np.ndarray,
    P: np.ndarray,
    Q: np.ndarray,
    b: np.ndarray,
    low: np.ndarray,
    upp: np.ndarray,
    alpha: np.ndarray,
    beta: np.ndarray,
    max_inner: int = 100,
    tol: float = 1e-7,
) -> tuple[np.ndarray, np.ndarray]:
    """Solve the MMA dual subproblem to find x_new and Lagrange multipliers λ.

    Given Lagrange multipliers λ ∈ R^m_+, the primal solution is closed-form:
        x_j(λ) = ( √(p_j(λ)) L_j + √(q_j(λ)) U_j ) / ( √(p_j(λ)) + √(q_j(λ)) )
    where p_j(λ) = p_{0j} + Σ_i λ_i P_{ij}, q_j(λ) likewise. Then x_j is
    clipped to [α_j, β_j] (move-limited box).

    The dual objective W(λ) = b^T λ - Σ_j [ p_j(λ)/(U_j - x_j(λ)) + q_j(λ)/(x_j(λ) - L_j) ]
    is concave; we maximize over λ ≥ 0 by projected gradient with damping.
    For a single constraint (m=1), we use scalar bisection — exact and
    cheap. For m > 1, we use damped Newton on the dual with multiplier
    clipped to non-negative.
    """
    m = b.size

    if m == 0:
        # Unconstrained: primal x = closed-form min of separable convex approx
        sqrt_p = np.sqrt(p0)
        sqrt_q = np.sqrt(q0)
        x_new = (sqrt_p * low + sqrt_q * upp) / (sqrt_p + sqrt_q)
        return np.clip(x_new, alpha, beta), np.zeros(0)

    def primal_x(lmbda: np.ndarray) -> np.ndarray:
        # Aggregate p, q across constraints
        p_total = p0 + lmbda @ P
        q_total = q0 + lmbda @ Q
        sqrt_p = np.sqrt(p_total)
        sqrt_q = np.sqrt(q_total)
        x_new = (sqrt_p * low + sqrt_q * upp) / (sqrt_p + sqrt_q)
        return np.clip(x_new, alpha, beta)

    def constraint_residual(lmbda: np.ndarray) -> np.ndarray:
        """g_i(λ) = ∂W/∂λ_i — should be ≤ 0 at optimum (≤ 0 = constraint inactive)."""
        x_new = primal_x(lmbda)
        ux = np.maximum(upp - x_new, 1e-12)
        xl = np.maximum(x_new - low, 1e-12)
        return (P / ux + Q / xl).sum(axis=1) - b

    if m == 1:
        # Bisection on λ ≥ 0: find λ s.t. g(λ) = 0 (or λ=0 with g(0) ≤ 0)
        lmbda = np.array([0.0])
        g0 = constraint_residual(lmbda)
        if g0[0] <= tol:
            return primal_x(lmbda), lmbda
        lo, hi = 0.0, 1.0
        # Bracket: grow hi until g(hi) ≤ 0
        for _ in range(80):
            lmbda[0] = hi
            if constraint_residual(lmbda)[0] <= 0.0:
                break
            hi *= 2.0
            if hi > 1e20:
                break
        # Bisect
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            lmbda[0] = mid
            g = constraint_residual(lmbda)[0]
            if abs(g) < tol or hi - lo < tol * max(1.0, mid):
                break
            if g > 0.0:
                lo = mid
            else:
                hi = mid
        return primal_x(lmbda), lmbda

    # m > 1: block-coordinate bisection — solve each constraint's multiplier
    # holding others fixed, cycle until residuals stabilize. This handles the
    # KKT complementarity ``λ_i ≥ 0 ∧ g_i ≤ 0 ∧ λ_i g_i = 0`` cleanly: when
    # a constraint is inactive at the current λ, bisection picks λ_i = 0.
    lmbda = np.zeros(m)
    for _outer in range(max_inner):
        prev_lmbda = lmbda.copy()
        for i in range(m):
            # Bisect on λ_i ≥ 0 to drive g_i(λ) to 0 (or pin at 0 if g_i(0) ≤ 0)
            lmbda[i] = 0.0
            g0 = constraint_residual(lmbda)[i]
            if g0 <= tol:
                continue
            lo, hi = 0.0, 1.0
            for _ in range(80):
                lmbda[i] = hi
                if constraint_residual(lmbda)[i] <= 0.0:
                    break
                hi *= 2.0
                if hi > 1e20:
                    break
            for _ in range(80):
                mid = 0.5 * (lo + hi)
                lmbda[i] = mid
                gi = constraint_residual(lmbda)[i]
                if abs(gi) < tol or hi - lo < tol * max(1.0, mid):
                    break
                if gi > 0.0:
                    lo = mid
                else:
                    hi = mid
        if np.max(np.abs(lmbda - prev_lmbda)) < tol * max(1.0, float(np.max(lmbda))):
            break
    return primal_x(lmbda), lmbda


def mma_step(
    x: np.ndarray,
    df0dx: np.ndarray,
    fval: np.ndarray,
    dfdx: np.ndarray,
    xmin: np.ndarray,
    xmax: np.ndarray,
    state: MMAState,
) -> tuple[np.ndarray, np.ndarray]:
    """One outer iteration of MMA.

    Args:
        x: current design vector, shape ``(n,)``.
        df0dx: gradient of objective, shape ``(n,)``.
        fval: current constraint values, shape ``(m,)``. Convention: feasible
            when ``fval ≤ 0`` (i.e. constraints are written as ``f_i(x) ≤ 0``).
        dfdx: constraint Jacobian, shape ``(m, n)``.
        xmin, xmax: global box bounds on x.
        state: mutable ``MMAState``. ``state.iteration`` is auto-incremented.

    Returns:
        ``(x_new, lmbda)`` — next design vector (within the move-limited box
        intersected with [xmin, xmax]) and Lagrange multipliers ``lmbda ≥ 0``
        useful for KKT diagnostics.
    """
    x = np.asarray(x, dtype=float).copy()
    df0dx = np.asarray(df0dx, dtype=float)
    fval = np.atleast_1d(np.asarray(fval, dtype=float))
    if fval.size == 0:
        # Treat as truly unconstrained (m=0): coerce dfdx to (0, n)
        dfdx = np.zeros((0, x.size))
    else:
        dfdx = np.asarray(dfdx, dtype=float)
        if dfdx.ndim == 1:
            dfdx = dfdx.reshape(1, x.size)
        if dfdx.shape != (fval.size, x.size):
            raise ValueError(f"dfdx shape {dfdx.shape} must equal (m={fval.size}, n={x.size})")

    low, upp = _update_asymptotes(x, state, xmin, xmax)

    # Move-limited box: alpha = max(xmin, low + 0.1·(x-low), x - move·span)
    span = xmax - xmin
    move = state.move_limit * span
    alpha = np.maximum.reduce([xmin, low + 0.1 * (x - low), x - move])
    beta = np.minimum.reduce([xmax, upp - 0.1 * (upp - x), x + move])
    # Ensure alpha ≤ beta (can violate by tiny float drift)
    alpha = np.minimum(alpha, beta - 1e-12)

    p0, q0, P, Q, b = _build_subproblem(x, df0dx, fval, dfdx, low, upp, state.raa0)

    x_new, lmbda = _solve_dual_subproblem(p0, q0, P, Q, b, low, upp, alpha, beta)
    x_new = np.clip(x_new, xmin, xmax)

    # Advance state
    state.x_prev2 = state.x_prev1.copy() if state.x_prev1 is not None else x.copy()
    state.x_prev1 = x.copy()
    state.low = low
    state.upp = upp
    state.iteration += 1
    state.history.append(
        {
            "iteration": state.iteration,
            "max_change": float(np.max(np.abs(x_new - x))),
            "constraint_max": float(np.max(fval)) if fval.size else 0.0,
            "lmbda": lmbda.copy(),
        }
    )
    return x_new, lmbda


def mma_minimize(
    x0: np.ndarray,
    objective_and_grad,
    constraints_and_jac,
    xmin: np.ndarray,
    xmax: np.ndarray,
    max_iter: int = 100,
    tol_change: float = 1e-3,
    state: MMAState | None = None,
) -> dict:
    """Convenience wrapper: run MMA to convergence.

    Args:
        x0: initial design vector.
        objective_and_grad: callable ``x → (f0, df0/dx)``.
        constraints_and_jac: callable ``x → (fval, dfdx)`` where ``fval``
            has shape ``(m,)``, ``dfdx`` has shape ``(m, n)``. Convention:
            constraint feasible iff ``fval ≤ 0``.
        xmin, xmax: box bounds.
        max_iter: outer-loop iteration cap.
        tol_change: stop when ``max(|x_{k+1} - x_k|) ≤ tol_change``.
        state: optional pre-seeded ``MMAState``.

    Returns:
        Dict with keys ``x``, ``f0``, ``fval``, ``iterations``,
        ``stop_reason``, ``history`` (per-iter dicts), ``state``.
    """
    x = np.asarray(x0, dtype=float).copy()
    xmin = np.asarray(xmin, dtype=float)
    xmax = np.asarray(xmax, dtype=float)
    if state is None:
        state = MMAState()

    stop_reason = "max_iter"
    f0 = 0.0
    fval = np.zeros(1)
    for _ in range(max_iter):
        f0, df0dx = objective_and_grad(x)
        fval, dfdx = constraints_and_jac(x)
        x_new, _lmbda = mma_step(x, df0dx, fval, dfdx, xmin, xmax, state)
        change = float(np.max(np.abs(x_new - x)))
        x = x_new
        if change <= tol_change:
            stop_reason = "tol_change"
            break

    return {
        "x": x,
        "f0": f0,
        "fval": fval,
        "iterations": state.iteration,
        "stop_reason": stop_reason,
        "history": state.history,
        "state": state,
    }
