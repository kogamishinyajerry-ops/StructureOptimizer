"""Wave QQ (v7, D046): NSGA-III directly on the density field.

Quantitative anchors:
- the 2-D hypervolume matches hand-computed exact areas (single rectangle and a
  two-point union with inclusion–exclusion);
- the cumulative-archive hypervolume is monotone non-decreasing over generations;
- the evolved front is a genuine (compliance, volume) trade-off (monotone);
- the gradient-free front never dominates the gradient-SIMP point (honest: this
  driver does not beat gradients — its value is the verifiable front).
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.multi_objective_to import (
    hypervolume_2d,
    multi_objective_to,
)
from structure_optimizer.core.simp import run_simp


def test_hypervolume_2d_exact():
    ref = np.array([3.0, 3.0])
    assert hypervolume_2d(np.array([[1.0, 1.0]]), ref) == pytest.approx(4.0)
    # union of [1,3]×[2,3] and [2,3]×[1,3] = 2 + 2 − 1 = 3
    assert hypervolume_2d(np.array([[1.0, 2.0], [2.0, 1.0]]), ref) == pytest.approx(3.0)
    # a dominated point must not change the hypervolume
    with_dom = hypervolume_2d(np.array([[1.0, 2.0], [2.0, 1.0], [2.5, 2.5]]), ref)
    assert with_dom == pytest.approx(3.0)
    # points outside the reference contribute nothing
    assert hypervolume_2d(np.array([[5.0, 5.0]]), ref) == 0.0


def _run(n_gen=10, pop=12, seed=0):
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    res = multi_objective_to(config, mesh, n_generations=n_gen, population_size=pop, rng_seed=seed)
    return config, mesh, res


def test_archive_hypervolume_is_monotone():
    _config, _mesh, res = _run()
    hv = np.array(res.hv_history)
    assert len(hv) == 11  # initial + 10 generations
    assert np.all(np.diff(hv) >= -1e-9), f"hypervolume not monotone: {hv}"
    assert hv[-1] > hv[0]  # the search actually improves the front


def test_front_is_a_genuine_tradeoff():
    _config, _mesh, res = _run()
    assert res.n_front >= 2
    obj = res.front_objectives  # already sorted by compliance ascending
    # non-dominated 2-D front: as compliance rises, volume must fall
    assert np.all(np.diff(obj[:, 1]) <= 1e-9), f"front not monotone: {obj}"
    # density fields carry the void floor and match the design DOFs
    assert res.front_densities.shape == (res.n_front, _mesh.elements.shape[0])


def test_gradientfree_front_does_not_dominate_simp():
    config, mesh, res = _run()
    simp = run_simp(config, mesh)
    c_simp = float(simp.final_analysis.compliance)
    v_simp = float(simp.metrics[-1].volume_fraction)
    for c, v in res.front_objectives:
        dominates = (c <= c_simp - 1e-9) and (v <= v_simp + 1e-9)
        assert not dominates, (
            f"gradient-free point ({c:.4g},{v:.4g}) dominates gradient SIMP "
            f"({c_simp:.4g},{v_simp:.4g}) — implausible, check the comparison"
        )


def test_reproducible_with_seed():
    _c1, _m1, r1 = _run(seed=7)
    _c2, _m2, r2 = _run(seed=7)
    assert np.allclose(r1.front_objectives, r2.front_objectives)


def test_contracts():
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    with pytest.raises(SolverError, match="n_generations_must_be_positive"):
        multi_objective_to(config, mesh, n_generations=0)
    with pytest.raises(SolverError, match="population_too_small"):
        multi_objective_to(config, mesh, population_size=2)
