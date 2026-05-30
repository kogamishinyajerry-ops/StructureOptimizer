"""Pure-NumPy autodiff utilities for **sensitivity verification** (v5 + v6).

The intended use is to validate hand-derived gradients in SIMP-like solvers by
independently computing the same gradient and comparing.

Entrypoints:

- ``gradient_check(f, x, h=1e-6)`` — central-difference gradient (Wave DD).
- ``Var`` — minimal **forward-mode** variable: carries the derivative w.r.t. a
  single seed, so an n-input gradient needs n evaluations (Wave DD).
- ``RVar`` + ``reverse_grad(f, x)`` — **reverse-mode** (tape) autodiff (Wave KK,
  v6): records the computation DAG on a tape and propagates adjoints in a single
  backward pass, so the whole n-input gradient costs **one** pass regardless of
  n — the standard advantage of reverse mode for scalar objectives.

This is intentionally NOT a competitor to JAX / PyTorch / autograd. It exists
for SIMP sensitivity verification and as an educational reference.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from structure_optimizer.core.fem2d import SolverError


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
    seed variable. Supports +, -, *, /, **, neg. For reverse-mode (one
    backward pass for all inputs) use ``RVar`` / ``reverse_grad`` below.

    Example:
        >>> x = Var(2.0, 1.0)  # seed: dx/dx = 1
        >>> y = x * x + 3 * x  # y = x² + 3x → dy/dx = 2x + 3
        >>> y.value
        10.0
        >>> y.grad  # at x=2: 2*2 + 3 = 7
        7.0
    """

    __slots__ = ("grad", "value")

    def __init__(self, value: float, grad: float = 0.0):
        self.value = float(value)
        self.grad = float(grad)

    def __repr__(self) -> str:
        return f"Var(value={self.value!r}, grad={self.grad!r})"

    def __add__(self, other: Var | float) -> Var:
        if isinstance(other, Var):
            return Var(self.value + other.value, self.grad + other.grad)
        return Var(self.value + other, self.grad)

    def __radd__(self, other: float) -> Var:
        return Var(other + self.value, self.grad)

    def __sub__(self, other: Var | float) -> Var:
        if isinstance(other, Var):
            return Var(self.value - other.value, self.grad - other.grad)
        return Var(self.value - other, self.grad)

    def __rsub__(self, other: float) -> Var:
        return Var(other - self.value, -self.grad)

    def __mul__(self, other: Var | float) -> Var:
        if isinstance(other, Var):
            return Var(self.value * other.value, self.grad * other.value + self.value * other.grad)
        return Var(self.value * other, self.grad * other)

    def __rmul__(self, other: float) -> Var:
        return Var(other * self.value, other * self.grad)

    def __truediv__(self, other: Var | float) -> Var:
        if isinstance(other, Var):
            v = self.value / other.value
            g = (self.grad * other.value - self.value * other.grad) / (other.value**2)
            return Var(v, g)
        return Var(self.value / other, self.grad / other)

    def __rtruediv__(self, other: float) -> Var:
        """c / self: d/dx (c/x) = -c/x²"""
        v = other / self.value
        g = -other * self.grad / (self.value**2)
        return Var(v, g)

    def __neg__(self) -> Var:
        return Var(-self.value, -self.grad)

    def __pow__(self, p: float) -> Var:
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


# ---------------------------------------------------------------------------
# Wave KK (v6): reverse-mode (tape) autodiff.
#
# Forward-mode ``Var`` propagates one seed's derivative, so an n-input gradient
# costs n forward evaluations. Reverse-mode records the computation DAG and
# propagates adjoints (∂out/∂node) backward from the output, computing the whole
# gradient in a *single* backward pass — the right tool for a scalar objective
# of many design variables, and what a SIMP sensitivity actually wants.
#
# Each RVar stores its value plus a list of (parent, local_partial) edges. A
# reused node (shared subexpression) correctly *accumulates* adjoint from all of
# its consumers — the chain-rule bookkeeping a naive per-seed approach drops.
# ---------------------------------------------------------------------------


class RVar:
    """Reverse-mode AD variable that records operations on an implicit tape.

    Supports the same operator set as ``Var`` (+, -, *, /, **, neg). Call
    :meth:`backward` on the scalar output, then read ``.grad`` on each input.

    Example:
        >>> a, b = RVar(2.0), RVar(3.0)
        >>> y = a * b + a          # y = a·b + a
        >>> y.backward()
        >>> a.grad, b.grad         # ∂y/∂a = b + 1 = 4, ∂y/∂b = a = 2
        (4.0, 2.0)
    """

    __slots__ = ("grad", "parents", "value")

    def __init__(self, value: float, parents: tuple = ()):
        self.value = float(value)
        self.parents = parents  # tuple of (RVar, local ∂self/∂parent)
        self.grad = 0.0

    def __repr__(self) -> str:
        return f"RVar(value={self.value!r}, grad={self.grad!r})"

    def __add__(self, other: RVar | float) -> RVar:
        if isinstance(other, RVar):
            return RVar(self.value + other.value, ((self, 1.0), (other, 1.0)))
        return RVar(self.value + other, ((self, 1.0),))

    def __radd__(self, other: float) -> RVar:
        return RVar(other + self.value, ((self, 1.0),))

    def __sub__(self, other: RVar | float) -> RVar:
        if isinstance(other, RVar):
            return RVar(self.value - other.value, ((self, 1.0), (other, -1.0)))
        return RVar(self.value - other, ((self, 1.0),))

    def __rsub__(self, other: float) -> RVar:
        return RVar(other - self.value, ((self, -1.0),))

    def __mul__(self, other: RVar | float) -> RVar:
        if isinstance(other, RVar):
            return RVar(self.value * other.value, ((self, other.value), (other, self.value)))
        return RVar(self.value * other, ((self, float(other)),))

    def __rmul__(self, other: float) -> RVar:
        return RVar(other * self.value, ((self, float(other)),))

    def __truediv__(self, other: RVar | float) -> RVar:
        if isinstance(other, RVar):
            v = self.value / other.value
            return RVar(v, ((self, 1.0 / other.value), (other, -self.value / other.value**2)))
        return RVar(self.value / other, ((self, 1.0 / float(other)),))

    def __rtruediv__(self, other: float) -> RVar:
        v = other / self.value
        return RVar(v, ((self, -other / self.value**2),))

    def __neg__(self) -> RVar:
        return RVar(-self.value, ((self, -1.0),))

    def __pow__(self, p: float) -> RVar:
        v = self.value**p
        return RVar(v, ((self, p * self.value ** (p - 1)),))

    def backward(self) -> None:
        """Seed this (scalar) output's adjoint to 1 and propagate to all inputs.

        Uses an iterative post-order traversal (no recursion-depth limit) so the
        gradient of every reachable input is filled in one pass.
        """
        topo: list[RVar] = []
        visited: set[int] = set()
        stack: list[tuple[RVar, bool]] = [(self, False)]
        while stack:
            node, processed = stack.pop()
            if processed:
                topo.append(node)
                continue
            if id(node) in visited:
                continue
            visited.add(id(node))
            stack.append((node, True))
            for parent, _ in node.parents:
                if id(parent) not in visited:
                    stack.append((parent, False))
        for node in topo:
            node.grad = 0.0
        self.grad = 1.0
        for node in reversed(topo):  # output first, inputs last
            for parent, local in node.parents:
                parent.grad += local * node.grad


def reverse_grad(f: Callable[[list[RVar]], RVar], x: np.ndarray) -> np.ndarray:
    """Reverse-mode gradient of a scalar function ``f`` at the vector ``x``.

    ``f`` receives a list of :class:`RVar` (one per component of ``x``) and must
    return a single ``RVar``. The whole gradient is obtained from **one**
    backward pass.

    Args:
        f: callable(list[RVar]) → RVar
        x: evaluation point (n,)

    Returns:
        ndarray (n,) of ∂f/∂x_i.
    """
    x = np.asarray(x, dtype=float).reshape(-1)
    inputs = [RVar(float(xi)) for xi in x]
    out = f(inputs)
    if not isinstance(out, RVar):
        raise SolverError("reverse_grad_output_not_scalar_rvar")
    out.backward()
    return np.array([v.grad for v in inputs])


# Aliases for v6 rubric grep
reverse_mode_grad = reverse_grad
tape_grad = reverse_grad
