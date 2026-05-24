"""Wave UUU (v11, D076): reference-(front)-free multi-objective quality indicators.

Quantitative anchors (closed-form + cross-indicator, not qualitative trend):
- **R2 closed form**: a hand-computed Tchebycheff R2 on a one-point front equals
  the implementation to machine precision;
- **R2 is weakly Pareto-compliant**: a dominating front scores strictly lower,
  and adding a dominated solution does not change R2;
- **reference-free indicators rank fronts identically to IGD⁺**: on a sequence of
  nested-better fronts, R2 (lower=better), reference-free hypervolume
  (higher=better), and IGD⁺ (lower=better) induce the *same* ordering — so a
  practitioner with no true Pareto front (no IGD⁺) gets the same verdict;
- **reference-free hypervolume auto-derives its reference point** and is monotone
  under adding a non-dominated point.

D068's reopening criterion: "reference-free quality indicators (hypervolume-only
/ R2)" — IGD⁺ needs a reference front you do not have in practice.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.multi_objective_to import (
    hypervolume_2d,
    igd_plus,
    r2_indicator,
    reference_free_hypervolume,
)


def test_r2_closed_form():
    # front {(1,1)}, weights {(1,0),(0,1),(0.5,0.5)}, utopia (0,0):
    # g((1,1)|(1,0))=1, |(0,1)=1, |(0.5,0.5)=0.5  → mean = 5/6
    front = np.array([[1.0, 1.0]])
    weights = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])
    ideal = np.array([0.0, 0.0])
    assert abs(r2_indicator(front, weights, ideal) - (5.0 / 6.0)) < 1e-12


def test_r2_weakly_pareto_compliant():
    weights = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])
    ideal = np.array([0.0, 0.0])
    a = np.array([[1.0, 1.0]])
    b = np.array([[2.0, 2.0]])  # dominated by a
    r2a = r2_indicator(a, weights, ideal)
    r2b = r2_indicator(b, weights, ideal)
    # the dominating front scores strictly lower (better)
    assert r2a < r2b
    # adding a dominated solution to A leaves R2 unchanged (min over solutions)
    assert abs(r2_indicator(np.vstack([a, b]), weights, ideal) - r2a) < 1e-12


def test_reference_free_indicators_rank_like_igd_plus():
    base = np.array([[3.0, 1.0], [2.0, 2.0], [1.0, 3.0]])
    scales = [1.0, 0.8, 0.6, 0.4]  # smaller = closer to origin = better
    fronts = [base * s for s in scales]

    shared_ideal = np.array([0.0, 0.0])
    shared_ref = np.array([4.0, 4.0])
    shared_reference_front = base * 0.3  # better than every obtained front

    r2 = np.array([r2_indicator(f, ideal=shared_ideal) for f in fronts])
    hv = np.array([hypervolume_2d(f, shared_ref) for f in fronts])
    igd = np.array([igd_plus(f, shared_reference_front) for f in fronts])

    # quality order = best→worst. R2 & IGD⁺ lower=better; HV higher=better.
    order_r2 = list(np.argsort(r2))
    order_hv = list(np.argsort(-hv))
    order_igd = list(np.argsort(igd))
    assert order_r2 == order_igd == order_hv == [3, 2, 1, 0]
    # and each is strictly monotone along the improving sequence
    assert np.all(np.diff(r2) < 0)
    assert np.all(np.diff(hv) > 0)
    assert np.all(np.diff(igd) < 0)


def test_reference_free_hypervolume_auto_ref_and_monotone():
    f1 = np.array([[2.0, 2.0]])
    f2 = np.array([[2.0, 2.0], [1.0, 3.0]])  # adds a non-dominated point
    hv1 = reference_free_hypervolume(f1, margin=0.1)
    hv2 = reference_free_hypervolume(f2, margin=0.1)
    assert hv1 > 0.0
    assert hv2 > hv1  # adding a non-dominated point strictly increases HV
    # auto-derived reference equals max + margin·range; check it matches a manual HV
    lo = f2.min(axis=0)
    hi = f2.max(axis=0)
    ref = hi + 0.1 * (hi - lo)
    assert abs(hv2 - hypervolume_2d(f2, ref)) < 1e-12


def test_reference_free_indicator_error_handling():
    with pytest.raises(SolverError):
        r2_indicator(np.zeros((0, 2)))
    with pytest.raises(SolverError):
        r2_indicator(np.array([[1.0, 1.0]]), weights=np.array([[1.0, 0.0, 0.0]]))  # wrong n_obj
    with pytest.raises(SolverError):
        r2_indicator(np.array([[1.0, 1.0]]), ideal=np.array([0.0, 0.0, 0.0]))
    with pytest.raises(SolverError):
        reference_free_hypervolume(np.zeros((0, 2)))
    with pytest.raises(SolverError):
        reference_free_hypervolume(np.array([[1.0, 1.0]]), margin=0.0)
