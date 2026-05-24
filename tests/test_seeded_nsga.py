"""Wave WW (v8, D052): gradient-seeded NSGA-III density-field TO.

Quantitative anchors:
- a gradient-seeded initial population yields a higher final hypervolume than a
  random one at the **same budget** (D046 reopening: sharper front);
- the seeded front reaches far lower compliance (gradient-SIMP quality) than the
  random front — its low-compliance endpoint matches single-objective SIMP;
- the cumulative-archive hypervolume stays monotone and the run is reproducible.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.multi_objective_to import (
    gradient_seeded_multi_objective_to,
    multi_objective_to,
)

N_GEN, POP = 10, 12


def _smoke():
    config = load_benchmark("cantilever", preset="smoke")
    return config, create_structured_mesh(config)


def test_seeded_beats_random_at_same_budget():
    config, mesh = _smoke()
    seeded = gradient_seeded_multi_objective_to(config, mesh, n_generations=N_GEN, population_size=POP, rng_seed=0)
    random = multi_objective_to(config, mesh, n_generations=N_GEN, population_size=POP, rng_seed=0)
    # warm-start → strictly larger final hypervolume at the same budget
    assert seeded.hv_history[-1] > random.hv_history[-1]
    # gradient-quality low-compliance endpoint (matches single-objective SIMP)
    assert seeded.front_objectives[:, 0].min() < random.front_objectives[:, 0].min()
    assert seeded.front_objectives[:, 0].min() < 0.5 * random.front_objectives[:, 0].min()


def test_seeded_hypervolume_monotone():
    config, mesh = _smoke()
    res = gradient_seeded_multi_objective_to(config, mesh, n_generations=N_GEN, population_size=POP, rng_seed=1)
    hv = np.array(res.hv_history)
    assert np.all(np.diff(hv) >= -1e-9), f"hypervolume not monotone: {hv}"


def test_seeded_reproducible():
    config, mesh = _smoke()
    r1 = gradient_seeded_multi_objective_to(config, mesh, n_generations=N_GEN, population_size=POP, rng_seed=3)
    r2 = gradient_seeded_multi_objective_to(config, mesh, n_generations=N_GEN, population_size=POP, rng_seed=3)
    assert np.allclose(r1.front_objectives, r2.front_objectives)


def test_seed_genome_shape_contract():
    config, mesh = _smoke()
    with pytest.raises(SolverError, match="seed_genome_shape_mismatch"):
        multi_objective_to(config, mesh, n_generations=2, population_size=8, seed_genomes=[np.zeros(3)])
