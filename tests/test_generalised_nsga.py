"""Wave MMM (v10, D068): generalised nsga3_density_to + IGD+ indicator.

Quantitative anchors (analytical / bit-exact, not qualitative trend):
- the **refactor is bit-identical**: the public ``multi_objective_to`` (2-obj)
  and ``multi_load_case_to`` (3-obj) now delegate to the single generalised
  ``nsga3_density_to``, and reproduce direct ``nsga3_density_to`` calls
  element-for-element (front objectives, densities, hypervolume history);
- **IGD⁺ matches closed form**: a hand-computed 3-point example equals 1/3
  exactly; IGD⁺(Z, Z) = 0; a front weakly dominating the reference scores 0; and
  a front pushed radially outward by δ from an analytical quarter-circle Pareto
  front has IGD⁺ = δ exactly (and is monotone in δ).

D060's reopening criterion: *one generalised nsga3_density_to* (not two parallel
loops) + a many-objective IGD⁺ indicator.
"""

from __future__ import annotations

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.multi_objective_to import (
    igd_plus,
    multi_load_case_to,
    multi_objective_to,
    nsga3_density_to,
)

GEN, POP = 6, 12


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def test_two_objective_delegation_is_bit_identical():
    config, mesh = _setup()
    pub = multi_objective_to(config, mesh, n_generations=GEN, population_size=POP, rng_seed=0)
    gen = nsga3_density_to(
        config, mesh, load_cases=[list(config.loads)], n_generations=GEN, population_size=POP, rng_seed=0
    )
    assert np.array_equal(pub.front_objectives, gen.front_objectives)
    assert np.array_equal(pub.front_densities, gen.front_densities)
    assert np.array_equal(np.array(pub.hv_history), np.array(gen.hv_history))
    assert pub.front_objectives.shape[1] == 2


def test_three_objective_delegation_is_bit_identical():
    config, mesh = _setup()
    default_lc = [
        list(config.loads),
        [{**ld, "fx": ld.get("fy", 0.0), "fy": ld.get("fx", 0.0)} for ld in config.loads],
    ]
    pub = multi_load_case_to(config, mesh, n_generations=GEN, population_size=POP, rng_seed=0)
    gen = nsga3_density_to(
        config, mesh, load_cases=default_lc, n_generations=GEN, population_size=POP, rng_seed=0
    )
    assert np.array_equal(pub.front_objectives, gen.front_objectives)
    assert np.array_equal(pub.front_densities, gen.front_densities)
    assert np.array_equal(np.array(pub.hv_history), np.array(gen.hv_history))
    assert pub.front_objectives.shape[1] == 3


def test_generalised_driver_handles_four_objectives():
    config, mesh = _setup()
    # three load cases → 4 objectives (3 compliances + volume): the generalised
    # driver works beyond the 2/3-obj originals
    lc = [
        list(config.loads),
        [{**ld, "fx": ld.get("fy", 0.0), "fy": ld.get("fx", 0.0)} for ld in config.loads],
        [{**ld, "fx": -ld.get("fx", 0.0), "fy": ld.get("fy", 0.0)} for ld in config.loads],
    ]
    r = nsga3_density_to(config, mesh, load_cases=lc, n_generations=4, population_size=POP, rng_seed=1)
    assert r.front_objectives.shape[1] == 4
    assert r.reference_point.shape[0] == 4
    assert r.n_front >= 1


def test_igd_plus_matches_closed_form():
    # minimisation; obtained front misses the middle reference point
    z = np.array([[0.0, 2.0], [1.0, 1.0], [2.0, 0.0]])
    a = np.array([[0.0, 2.0], [2.0, 0.0]])
    assert abs(igd_plus(a, z) - 1.0 / 3.0) < 1e-12
    # reference against itself, and a weakly dominating front, score 0
    assert igd_plus(z, z) == 0.0
    assert igd_plus(np.array([[-1.0, -1.0]]), z) == 0.0


def test_igd_plus_radial_offset_on_analytical_front():
    # analytical Pareto front: unit quarter-circle f1²+f2²=1 (first quadrant)
    t = np.linspace(0.0, np.pi / 2.0, 50)
    z = np.column_stack([np.cos(t), np.sin(t)])
    prev = -1.0
    for delta in (0.0, 0.05, 0.1, 0.2):
        a = z * (1.0 + delta)  # pushed radially outward by δ → worse by δ
        val = igd_plus(a, z)
        assert abs(val - delta) < 1e-3, f"δ={delta}: IGD+ {val:.4f} ≠ δ"
        assert val > prev  # strictly increasing in δ
        prev = val


def test_igd_plus_input_guards():
    import pytest
    from structure_optimizer.core.fem2d import SolverError

    z = np.array([[0.0, 1.0], [1.0, 0.0]])
    with pytest.raises(SolverError):
        igd_plus(np.zeros((0, 2)), z)  # empty front
    with pytest.raises(SolverError):
        igd_plus(np.array([[1.0, 2.0, 3.0]]), z)  # dim mismatch
