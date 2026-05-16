"""Wave DD: pure-NumPy autodiff sanity tests."""

from __future__ import annotations

import numpy as np
from structure_optimizer.core.autodiff import (
    Var,
    grad_check_against_analytical,
    gradient_check,
)


# ---------------------------------------------------------------------------
# Central-difference gradient check
# ---------------------------------------------------------------------------


def test_gradient_check_linear_function():
    """For f(x) = a · x, the gradient is the coefficient vector a."""
    a = np.array([1.0, -2.0, 3.0])

    def f(x):
        return float(a @ x)

    x0 = np.array([0.5, -1.0, 2.0])
    g = gradient_check(f, x0, h=1e-7)
    np.testing.assert_allclose(g, a, atol=1e-5)


def test_gradient_check_quadratic_function():
    """For f(x) = x · x, the gradient is 2x."""

    def f(x):
        return float(x @ x)

    x0 = np.array([1.0, 2.0, 3.0])
    g = gradient_check(f, x0, h=1e-7)
    np.testing.assert_allclose(g, 2 * x0, atol=1e-5)


def test_gradient_check_supports_analytical_comparison():
    """Convenience wrapper returns True when analytical = FD."""

    def f(x):
        return float(np.sum(x**3))

    def df(x):
        return 3 * x**2

    assert grad_check_against_analytical(f, df, np.array([1.0, 2.0]), h=1e-6, rtol=1e-4)


def test_gradient_check_catches_wrong_analytical_gradient():
    """Convenience wrapper returns False when analytical is wrong."""

    def f(x):
        return float(np.sum(x**2))

    def df_wrong(x):
        return x  # should be 2x

    assert not grad_check_against_analytical(f, df_wrong, np.array([1.0, 2.0]), h=1e-6, rtol=1e-3)


# ---------------------------------------------------------------------------
# Var forward-mode AD
# ---------------------------------------------------------------------------


def test_var_addition_propagates_gradient():
    x = Var(2.0, 1.0)
    y = x + 3.0
    assert y.value == 5.0
    assert y.grad == 1.0


def test_var_multiplication_uses_product_rule():
    x = Var(2.0, 1.0)
    y = x * x  # y = x², dy/dx = 2x = 4
    assert y.value == 4.0
    assert y.grad == 4.0


def test_var_quadratic_expression():
    x = Var(2.0, 1.0)
    y = x * x + 3.0 * x  # y = x² + 3x, dy/dx = 2x + 3 = 7
    assert y.value == 10.0
    assert y.grad == 7.0


def test_var_division():
    x = Var(4.0, 1.0)
    y = 1.0 / x  # y = 1/x, dy/dx = -1/x² = -1/16
    assert y.value == 0.25
    np.testing.assert_allclose(y.grad, -1.0 / 16.0, atol=1e-12)


def test_var_power():
    x = Var(2.0, 1.0)
    y = x**3  # y = x³, dy/dx = 3x² = 12
    assert y.value == 8.0
    np.testing.assert_allclose(y.grad, 12.0, atol=1e-12)


def test_var_subtraction():
    x = Var(5.0, 1.0)
    y = x - 2.0  # y = x - 2, dy/dx = 1
    assert y.value == 3.0
    assert y.grad == 1.0


def test_var_rsub():
    x = Var(5.0, 1.0)
    y = 10.0 - x  # y = 10 - x, dy/dx = -1
    assert y.value == 5.0
    assert y.grad == -1.0


def test_var_var_subtraction():
    x = Var(5.0, 1.0)
    y = Var(2.0, 0.5)
    z = x - y  # dz/d... = 1*1 - 1*0.5 = 0.5
    assert z.value == 3.0
    assert z.grad == 0.5


def test_var_rmul_with_scalar():
    x = Var(2.0, 1.0)
    y = 5.0 * x
    assert y.value == 10.0
    assert y.grad == 5.0


def test_property_var_matches_central_difference():
    """Compare Var forward AD against central FD on a complex expression."""

    def expression_value(x: float) -> float:
        return float(x * x * x - 2.0 * x + 1.0 / x)

    def expression_var(v: Var) -> Var:
        return v * v * v - 2.0 * v + 1.0 / v

    for x0 in [0.5, 1.0, 2.0, 3.0]:
        var_x = Var(x0, 1.0)
        var_y = expression_var(var_x)
        fd_grad = gradient_check(lambda x: expression_value(float(x[0])), np.array([x0]), h=1e-7)[0]
        np.testing.assert_allclose(var_y.grad, fd_grad, atol=1e-5)
