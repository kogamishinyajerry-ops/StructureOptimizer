"""Stress aggregation utilities (Wave F / v1.6.0).

Per-element von Mises stress is already computed inside
``fem2d.solve_linear_elastic`` (kept private as ``_approx_element_stress``);
this module re-exposes it as a vector for downstream tooling, and adds two
smooth-max aggregations:

- **p-norm**: ``(Σ σ_e^p)^(1/p)`` — classical smoothed max
- **Kreisselmeier-Steinhauser (KS)**: ``(1/p) log Σ exp(p σ_e)`` (with
  max-shift for numerical stability)

Both approach ``max σ`` as ``p → ∞``; both are differentiable surrogates for
the discontinuous max. Use p = 8-12 for p-norm, p = 50-100 for KS in
practice (Le et al. 2010; Duysinx & Bendsøe 1998).

This module is integration-light: F 波 wires it through ``verification.py``
to produce ``stress_constraint_failed`` status when a final density fails a
configured limit. Full stress-constrained SIMP (gradient via adjoint method)
is intentionally **not** in v1.6 scope — that's a separate adjoint-method
ADR not yet written.
"""

from __future__ import annotations

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.mesh import StructuredMesh


def element_von_mises_stresses(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    displacements: np.ndarray,
) -> np.ndarray:
    """Per-element von Mises stress (length = number of elements).

    Uses the same plane-stress kernel as the FEM solver
    (``fem2d._approx_element_stress``); reading from displacement is
    cheaper than re-solving when stresses are needed at a known design.
    """
    from structure_optimizer.core.fem2d import _approx_element_stress

    stresses = np.zeros(mesh.elements.shape[0], dtype=float)
    for eid in range(mesh.elements.shape[0]):
        edofs = mesh.element_dofs(eid)
        ue = displacements[edofs]
        stresses[eid] = _approx_element_stress(mesh, eid, ue, config)
    return stresses


def p_norm_stress(
    stresses: np.ndarray,
    p: float,
    mask: np.ndarray | None = None,
) -> float:
    """Compute ``(Σ σ_e^p)^(1/p)`` over (optionally masked) elements.

    Uses max-shift normalization to avoid overflow for large p. Returns 0.0
    if no elements remain after masking or all stresses are zero.
    """
    if p <= 0:
        raise ValueError("p must be positive")
    s = stresses[mask] if mask is not None else stresses
    if s.size == 0:
        return 0.0
    s_abs = np.abs(s)
    smax = float(s_abs.max())
    if smax == 0.0:
        return 0.0
    normalized = s_abs / smax
    return float(smax * np.sum(normalized**p) ** (1.0 / p))


def ks_stress(
    stresses: np.ndarray,
    p: float,
    mask: np.ndarray | None = None,
) -> float:
    """Kreisselmeier-Steinhauser smooth max: ``max σ + (1/p) log Σ exp(p (σ - max σ))``.

    The max-shift form is numerically stable for large p. KS approaches
    ``max σ`` faster than p-norm at the same p but has steeper gradients.
    """
    if p <= 0:
        raise ValueError("p must be positive")
    s = stresses[mask] if mask is not None else stresses
    if s.size == 0:
        return 0.0
    s_abs = np.abs(s)
    smax = float(s_abs.max())
    if smax == 0.0:
        return 0.0
    return float(smax + (1.0 / p) * np.log(np.sum(np.exp(p * (s_abs - smax)))))


def aggregate_stress(
    stresses: np.ndarray,
    aggregation: str,
    p: float,
    mask: np.ndarray | None = None,
) -> float:
    """Dispatch to ``p_norm_stress`` or ``ks_stress`` by ``aggregation`` string."""
    if aggregation == "p_norm":
        return p_norm_stress(stresses, p, mask)
    if aggregation == "ks":
        return ks_stress(stresses, p, mask)
    raise ValueError(f"unknown stress aggregation '{aggregation}'; expected 'p_norm' or 'ks'")
