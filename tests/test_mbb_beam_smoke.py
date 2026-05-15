import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.fem2d import solve_linear_elastic
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.simp import run_simp


def test_structured_mesh_node_and_element_counts():
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh = create_structured_mesh(config)

    assert mesh.nodes.shape[0] == (config.mesh.nelx + 1) * (config.mesh.nely + 1)
    assert mesh.elements.shape[0] == config.mesh.nelx * config.mesh.nely


def test_small_fem_solve_has_nonzero_displacement():
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh = create_structured_mesh(config)
    densities = np.ones(mesh.elements.shape[0])

    result = solve_linear_elastic(config, mesh, densities)

    assert result.max_displacement > 0
    assert result.compliance > 0


def test_simp_density_bounds_and_smoke_iterations():
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh = create_structured_mesh(config)

    result = run_simp(config, mesh)

    assert len(result.metrics) == config.optimization.max_iterations
    assert np.all(result.densities >= config.optimization.min_density)
    assert np.all(result.densities <= 1.0)
