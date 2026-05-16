"""Wave DD: pure-NumPy reverse-mode autodiff utilities (v5 multi-physics).

Minimal autodiff implementation for **sensitivity verification**. The
intended use is to validate hand-derived gradients in SIMP-like solvers
by independently computing the same gradient via central finite
differences and comparing.

Two entrypoints:

- ``gradient_check(f, x, h=1e-6)`` — compute the central-difference
  gradient of ``f(x)`` at ``x`` with step ``h``.
- ``Var`` — minimal forward-mode tape-style variable class for
  expression-level differentiation (limited to + - * / power; useful
  for unit tests of simple analytical sensitivities).

This is intentionally NOT a competitor to JAX / PyTorch / autograd. It
exists for:
1. The SIMP sensitivity verification tests (Wave DD §5.3).
2. Educational reference for the v5 tutorial.
3. Future v6+ if a real autodiff workflow emerges.
"""

from __future__ import annotations

from typing import Callable

import numpy as np


def gradient_check(
    f: Callable[[np.ndarray], float],
    x: np.ndarray,
    h: float = 1e-6,
) -> np.ndarray:
    """Central finite-difference gradient of ``f`` at ``x``.

    Args:
        f:   scalar-valued function of a vector
        x:   evaluation point (n,)
        h:   step size (smaller → more accurate but more roundoff)

    Returns:
        ndarray of shape ``x.shape`` containing ∂f/∂x_i
    """
    x = np.asarray(x, dtype=float)
    grad = np.zeros_like(x)
    for i in range(x.size):
        e = np.zeros_like(x)
        e.flat[i] = h
        grad.flat[i] = (f(x + e) - f(x - e)) / (2.0 * h)
    return grad


class Var:
    """Minimal forward-mode AD variable for sanity-checking gradients.

    Each ``Var`` carries its value plus its derivative w.r.t. a single
    seed variable. Supports +, -, *, /, **, abs, exp, log via numpy
    operations. Reverse-mode is out of scope (would need a tape).

    Example:
        >>> x = Var(2.0, 1.0)  # seed: dx/dx = 1
        >>> y = x * x + 3 * x  # y = x² + 3x → dy/dx = 2x + 3
        >>> y.value
        10.0
        >>> y.grad  # at x=2: 2*2 + 3 = 7
        7.0
    """

    __slots__ = ("value", "grad")

    def __init__(self, value: float, grad: float = 0.0):
        self.value = float(value)
        self.grad = float(grad)

    def __repr__(self) -> str:
        return f"Var(value={self.value!r}, grad={self.grad!r})"

    def __add__(self, other: "Var | float") -> "Var":
        if isinstance(other, Var):
            return Var(self.value + other.value, self.grad + other.grad)
        return Var(self.value + other, self.grad)

    def __radd__(self, other: float) -> "Var":
        return Var(other + self.value, self.grad)

    def __sub__(self, other: "Var | float") -> "Var":
        if isinstance(other, Var):
            return Var(self.value - other.value, self.grad - other.grad)
        return Var(self.value - other, self.grad)

    def __rsub__(self, other: float) -> "Var":
        return Var(other - self.value, -self.grad)

    def __mul__(self, other: "Var | float") -> "Var":
        if isinstance(other, Var):
            return Var(self.value * other.value, self.grad * other.value + self.value * other.grad)
        return Var(self.value * other, self.grad * other)

    def __rmul__(self, other: float) -> "Var":
        return Var(other * self.value, other * self.grad)

    def __truediv__(self, other: "Var | float") -> "Var":
        if isinstance(other, Var):
            v = self.value / other.value
            g = (self.grad * other.value - self.value * other.grad) / (other.value**2)
            return Var(v, g)
        return Var(self.value / other, self.grad / other)

    def __rtruediv__(self, other: float) -> "Var":
        """c / self: d/dx (c/x) = -c/x²"""
        v = other / self.value
        g = -other * self.grad / (self.value**2)
        return Var(v, g)

    def __neg__(self) -> "Var":
        return Var(-self.value, -self.grad)

    def __pow__(self, p: float) -> "Var":
        v = self.value**p
        g = p * (self.value ** (p - 1)) * self.grad
        return Var(v, g)


def grad_check_against_analytical(
    f: Callable[[np.ndarray], float],
    df_analytical: Callable[[np.ndarray], np.ndarray],
    x: np.ndarray,
    h: float = 1e-6,
    rtol: float = 1e-5,
) -> bool:
    """Convenience: check that an analytical gradient ≈ central-difference
    within the given relative tolerance."""
    fd = gradient_check(f, x, h)
    an = np.asarray(df_analytical(x), dtype=float)
    rel = np.linalg.norm(fd - an) / max(np.linalg.norm(an), 1e-12)
    return bool(rel < rtol)
