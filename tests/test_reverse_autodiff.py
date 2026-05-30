"""Wave KK (v6): reverse-mode (tape) autodiff.

Quantitative anchors:
- reverse-mode gradient == forward-mode (Var) == analytical == central finite
  difference, on a battery of functions;
- a single backward pass yields every input's partial;
- shared subexpressions accumulate adjoint correctly (the chain-rule
  bookkeeping a per-seed approach drops);
- the iterative backward handles chains far deeper than Python's recursion
  limit.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.core.autodiff import (
    RVar,
    Var,
    gradient_check,
    reverse_grad,
)
from structure_optimizer.core.fem2d import SolverError

# --- a mixed function exercising +, -, *, /, ** and a reused input ----------


def _mixed_rvar(v):
    return v[0] * v[0] * v[1] + 3 * v[0] + v[1] / v[2]


def _mixed_np(x):
    return x[0] ** 2 * x[1] + 3 * x[0] + x[1] / x[2]


def _mixed_grad(x):
    return np.array([2 * x[0] * x[1] + 3, x[0] ** 2 + 1 / x[2], -x[1] / x[2] ** 2])


def test_reverse_matches_analytical_and_fd():
    x = np.array([1.5, 2.0, 0.5])
    rg = reverse_grad(_mixed_rvar, x)
    assert np.allclose(rg, _mixed_grad(x), atol=1e-9)  # exact (analytic)
    assert np.allclose(rg, gradient_check(_mixed_np, x), atol=1e-6)  # vs central-FD


def test_reverse_matches_forward_var_single_input():
    x = 1.7
    # reverse mode
    rg = reverse_grad(lambda v: v[0] ** 3 + 2 * v[0] ** 2 - 5 * v[0], np.array([x]))
    # forward mode (single seed)
    xv = Var(x, 1.0)
    yv = xv**3 + 2 * xv**2 - 5 * xv
    analytical = 3 * x**2 + 4 * x - 5
    assert rg[0] == pytest.approx(yv.grad, rel=1e-12)
    assert rg[0] == pytest.approx(analytical, rel=1e-12)


def test_reverse_rosenbrock_all_partials_one_pass():
    def f_rvar(v):
        return 100.0 * (v[1] - v[0] * v[0]) ** 2 + (1.0 - v[0]) ** 2

    def f_np(x):
        return 100.0 * (x[1] - x[0] ** 2) ** 2 + (1.0 - x[0]) ** 2

    x = np.array([0.7, -0.3])
    rg = reverse_grad(f_rvar, x)
    an = np.array([-400.0 * x[0] * (x[1] - x[0] ** 2) - 2.0 * (1.0 - x[0]), 200.0 * (x[1] - x[0] ** 2)])
    assert rg.shape == (2,)  # both partials from one backward pass
    assert np.allclose(rg, an, atol=1e-9)
    assert np.allclose(rg, gradient_check(f_np, x), atol=1e-6)


def test_reverse_dag_reuse_accumulates():
    """A shared node y = a·b feeding y·y + y: adjoint must accumulate from both
    consumers. ∂/∂a = (2ab+1)·b, ∂/∂b = (2ab+1)·a."""

    def f_rvar(v):
        y = v[0] * v[1]  # reused
        return y * y + y

    def f_np(x):
        return (x[0] * x[1]) ** 2 + x[0] * x[1]

    x = np.array([1.3, 2.1])
    rg = reverse_grad(f_rvar, x)
    a, b = x
    an = np.array([(2 * a * b + 1) * b, (2 * a * b + 1) * a])
    assert np.allclose(rg, an, atol=1e-9)
    assert np.allclose(rg, gradient_check(f_np, x), atol=1e-6)


def test_backward_direct_example():
    a, b = RVar(2.0), RVar(3.0)
    y = a * b + a  # ∂y/∂a = b+1 = 4, ∂y/∂b = a = 2
    y.backward()
    assert a.grad == pytest.approx(4.0)
    assert b.grad == pytest.approx(2.0)


def test_reverse_deep_chain_no_recursion_limit():
    """20k chained ops would blow Python's recursion limit with a recursive
    backward; the iterative traversal handles it. d/dx of x scaled by 1 = 1."""

    def deep(v):
        acc = v[0]
        for _ in range(20000):
            acc = acc * 1.0 + 0.0
        return acc

    rg = reverse_grad(deep, np.array([3.0]))
    assert rg[0] == pytest.approx(1.0)


def test_reverse_grad_rejects_nonscalar_output():
    with pytest.raises(SolverError, match="output_not_scalar_rvar"):
        reverse_grad(lambda v: 5.0, np.array([1.0]))
