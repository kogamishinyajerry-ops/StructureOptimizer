"""Wave EEE (v9, D060): ≥3-objective multi-load-case NSGA-III + seeded warm-start.

Quantitative anchors:
- the exact n-D hypervolume (HSO) matches the 2-D formula and known 3-D boxes;
- Das-Dennis reference points for 3 objectives have the exact combinatorial
  count C(d+2, 2);
- the 3-objective front (compliance under two conflicting load cases + volume)
  shows a genuine trade-off: the design best for load case 1 is worse under load
  case 2 than the design best for load case 2;
- a gradient-SIMP warm-start lifts the final hypervolume above a random start and
  gives a far sharper single-objective endpoint.
"""

from __future__ import annotations

from dataclasses import replace
from math import comb

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.multi_objective_to import (
    hypervolume_2d,
    hypervolume_nd,
    multi_load_case_to,
)
from structure_optimizer.core.pareto_nsga import das_dennis_reference_points
from structure_optimizer.core.simp import run_simp


def _setup():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def test_property_hypervolume_nd_matches_2d_and_known_boxes():
    # consistency with the exact 2-D formula over random fronts
    rng = np.random.default_rng(0)
    for _ in range(40):
        pts = rng.uniform(0.0, 1.0, (rng.integers(3, 9), 2))
        ref = np.array([1.2, 1.2])
        assert hypervolume_nd(pts, ref) == pytest.approx(hypervolume_2d(pts, ref), abs=1e-12)
    # single 3-D box and inclusion-exclusion of two overlapping boxes
    assert hypervolume_nd(np.array([[0.0, 0.0, 0.0]]), np.array([1.0, 1.0, 1.0])) == pytest.approx(1.0)
    two = np.array([[0.0, 0.5, 0.5], [0.5, 0.0, 0.5]])
    assert hypervolume_nd(two, np.array([1.0, 1.0, 1.0])) == pytest.approx(0.375, abs=1e-12)
    # a dominated point contributes nothing
    dom = np.array([[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]])
    assert hypervolume_nd(dom, np.array([1.0, 1.0, 1.0])) == pytest.approx(1.0)


def test_das_dennis_three_objective_exact_count():
    for d in (4, 6, 8):
        n = das_dennis_reference_points(3, d).shape[0]
        assert n == comb(d + 2, 2), f"d={d}: {n} != {comb(d + 2, 2)}"


def test_three_objective_front_and_monotone_hypervolume():
    config, mesh = _setup()
    res = multi_load_case_to(config, mesh, n_generations=8, population_size=16, rng_seed=0)
    # three objectives: C under two load cases + volume
    assert res.front_objectives.shape[1] == 3
    assert res.n_front >= 1
    # cumulative-archive hypervolume is non-decreasing
    h = res.hv_history
    assert all(h[i + 1] >= h[i] - 1e-9 for i in range(len(h) - 1))


def test_load_cases_genuinely_conflict():
    config, mesh = _setup()
    res = multi_load_case_to(config, mesh, n_generations=8, population_size=16, rng_seed=0)
    fo = res.front_objectives
    i0 = int(np.argmin(fo[:, 0]))  # best under load case 1
    i1 = int(np.argmin(fo[:, 1]))  # best under load case 2
    assert i0 != i1, "load cases not conflicting (same optimum)"
    # the LC1-optimal design is worse under LC2 than the LC2-optimal design
    assert fo[i0, 1] > fo[i1, 1]


def test_seeded_warm_start_improves_front():
    config, mesh = _setup()
    design = mesh.design_mask
    seeds = [
        run_simp(replace(config, optimization=replace(config.optimization, volume_fraction=vf)), mesh).densities[design]
        for vf in (0.3, 0.5, 0.7)
    ]
    rand = multi_load_case_to(config, mesh, n_generations=8, population_size=16, rng_seed=0)
    seeded = multi_load_case_to(config, mesh, n_generations=8, population_size=16, rng_seed=0, seed_genomes=seeds)
    assert seeded.hv_history[-1] >= rand.hv_history[-1]
    # the gradient seed gives a far sharper single-objective (load-case-1) endpoint
    assert seeded.front_objectives[:, 0].min() < 0.5 * rand.front_objectives[:, 0].min()


def test_contracts():
    config, mesh = _setup()
    with pytest.raises(SolverError, match="n_generations_must_be_positive"):
        multi_load_case_to(config, mesh, n_generations=0)
    with pytest.raises(SolverError, match="population_too_small"):
        multi_load_case_to(config, mesh, population_size=2)
    with pytest.raises(SolverError, match="seed_genome_shape_mismatch"):
        multi_load_case_to(config, mesh, n_generations=2, seed_genomes=[np.ones(3)])
