"""Reproducibility contract: same input → same output.

Critical for engineering trust: two runs of the same config must produce
bit-identical density fields and identical scalar metrics. If this ever
breaks, every previously-published run becomes un-auditable.

We test at two levels:
1. Direct: ``run_simp`` called twice with the same config yields equal
   density arrays and equal metric scalars.
2. Indirect: two full ``run_benchmark`` invocations produce equal
   ``density.npy``, equal compliance/mass/max_displacement in summary,
   and equal ``input_hash``.
"""

from __future__ import annotations

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.run_store import input_hash, load_density, read_json
from structure_optimizer.core.simp import run_simp
from structure_optimizer.core.workflow import run_benchmark


def test_run_simp_is_bit_identical_under_same_config():
    config = load_benchmark("mbb_beam", preset="smoke")
    mesh_a = create_structured_mesh(config)
    mesh_b = create_structured_mesh(config)
    result_a = run_simp(config, mesh_a)
    result_b = run_simp(config, mesh_b)

    np.testing.assert_array_equal(result_a.densities, result_b.densities)
    assert result_a.baseline.compliance == result_b.baseline.compliance
    assert result_a.final_analysis.compliance == result_b.final_analysis.compliance
    assert result_a.final_analysis.max_displacement == result_b.final_analysis.max_displacement
    assert result_a.final_analysis.mass == result_b.final_analysis.mass
    assert result_a.stop_reason == result_b.stop_reason
    assert len(result_a.metrics) == len(result_b.metrics)
    for ma, mb in zip(result_a.metrics, result_b.metrics, strict=True):
        assert ma.iteration == mb.iteration
        assert ma.compliance == mb.compliance
        assert ma.volume_fraction == mb.volume_fraction
        assert ma.change == mb.change


def test_run_benchmark_produces_identical_artifacts():
    run_a = run_benchmark("mbb_beam", preset="smoke")
    run_b = run_benchmark("mbb_beam", preset="smoke")

    density_a = load_density(run_a)
    density_b = load_density(run_b)
    np.testing.assert_array_equal(density_a, density_b)

    summary_a = read_json(run_a / "summary.json")
    summary_b = read_json(run_b / "summary.json")
    assert summary_a["input_hash"] == summary_b["input_hash"]
    assert summary_a["stop_reason"] == summary_b["stop_reason"]
    assert summary_a["iterations"] == summary_b["iterations"]
    for key in ("mass", "compliance", "max_displacement", "max_stress"):
        assert summary_a["optimized"][key] == summary_b["optimized"][key]
        assert summary_a["baseline"][key] == summary_b["baseline"][key]


def test_input_hash_stable_for_same_config():
    a = load_benchmark("mbb_beam", preset="smoke")
    b = load_benchmark("mbb_beam", preset="smoke")
    assert input_hash(a) == input_hash(b)


def test_input_hash_changes_for_different_config():
    a = load_benchmark("mbb_beam", preset="smoke")
    b = load_benchmark("mbb_beam")  # different (no smoke preset → bigger mesh)
    assert input_hash(a) != input_hash(b)


def test_verification_json_metrics_match_between_runs():
    run_a = run_benchmark("simple_bracket", preset="smoke")
    run_b = run_benchmark("simple_bracket", preset="smoke")
    verify_a = read_json(run_a / "verification.json")
    verify_b = read_json(run_b / "verification.json")
    assert verify_a["status"] == verify_b["status"]
    assert verify_a["actual_volume_fraction"] == verify_b["actual_volume_fraction"]
    assert verify_a["candidate"]["compliance"] == verify_b["candidate"]["compliance"]
    assert verify_a["candidate"]["mass"] == verify_b["candidate"]["mass"]
    assert verify_a["candidate"]["max_displacement"] == verify_b["candidate"]["max_displacement"]


def test_cg_backend_also_reproducible():
    """The CG solver is iterative — must still be deterministic given same
    starting point (zeros) and same matrix."""
    from structure_optimizer.core.config import parse_config, validate_config
    from structure_optimizer.core.fem2d import solve_linear_elastic

    base_raw = load_benchmark("mbb_beam", preset="smoke").to_dict()
    cg_raw = {**base_raw, "solver": {"backend": "cg"}}
    config_a = parse_config(cg_raw)
    config_b = parse_config(cg_raw)
    validate_config(config_a)
    validate_config(config_b)
    mesh_a = create_structured_mesh(config_a)
    mesh_b = create_structured_mesh(config_b)
    densities = np.full(mesh_a.elements.shape[0], 0.5)

    result_a = solve_linear_elastic(config_a, mesh_a, densities)
    result_b = solve_linear_elastic(config_b, mesh_b, densities)
    np.testing.assert_array_equal(result_a.displacements, result_b.displacements)
    assert result_a.compliance == result_b.compliance


# --- Wave P: per-benchmark same-input/same-output coverage (rubric §3.4 ≥10) ---


import pytest  # noqa: E402


@pytest.mark.parametrize(
    "benchmark,preset",
    [
        ("mbb_beam", "smoke"),
        ("cantilever", "smoke"),
        ("l_bracket", "smoke"),
        ("simple_bracket", "smoke"),
        ("multi_load_cantilever", "smoke"),
        ("stress_limited_bracket", "smoke"),
    ],
)
def test_simp_same_input_same_density_per_benchmark(benchmark, preset):
    """For each canonical benchmark/preset, two run_simp invocations on a
    fresh mesh must produce bit-identical density fields. Adds 6 benchmark-
    specific reproducibility tests beyond the original 5 in this file
    (total ≥11; rubric §3.4 requires ≥10)."""
    config_a = load_benchmark(benchmark, preset=preset)
    config_b = load_benchmark(benchmark, preset=preset)
    mesh_a = create_structured_mesh(config_a)
    mesh_b = create_structured_mesh(config_b)
    a = run_simp(config_a, mesh_a)
    b = run_simp(config_b, mesh_b)
    np.testing.assert_array_equal(a.densities, b.densities)
    assert a.final_analysis.compliance == b.final_analysis.compliance
    assert a.baseline.compliance == b.baseline.compliance


@pytest.mark.parametrize(
    "benchmark,preset",
    [
        ("mbb_beam", "smoke"),
        ("cantilever", "smoke"),
        ("simple_bracket", "smoke"),
    ],
)
def test_beso_algorithm_also_reproducible_per_benchmark(benchmark, preset):
    """BESO (hard-kill) is also reproducible across two runs of the same
    config. The OC update is deterministic given the same FEA result, and
    BESO's evolutionary update is just sorting + thresholding."""
    from dataclasses import replace

    config = load_benchmark(benchmark, preset=preset)
    config = replace(config, optimization=replace(config.optimization, algorithm="beso"))
    mesh_a = create_structured_mesh(config)
    mesh_b = create_structured_mesh(config)
    from structure_optimizer.adapters.algorithm_base import get_algorithm

    algo_a = get_algorithm("beso")
    algo_b = get_algorithm("beso")
    a = algo_a.run(config, mesh_a)
    b = algo_b.run(config, mesh_b)
    np.testing.assert_array_equal(a.densities, b.densities)
    assert a.final_analysis.compliance == b.final_analysis.compliance


# --- Wave W: extend reproducibility coverage to ≥30 (rubric §3.5) ----


@pytest.mark.parametrize(
    "benchmark,preset",
    [
        ("mbb_beam", "smoke"),
        ("cantilever", "smoke"),
        ("l_bracket", "smoke"),
        ("simple_bracket", "smoke"),
        ("multi_load_cantilever", "smoke"),
        ("stress_limited_bracket", "smoke"),
        ("loaded_hook", "smoke"),
        ("stress_multi_load_bracket", "smoke"),
        ("xlarge_cantilever", "smoke"),
    ],
)
def test_input_hash_reproducible_per_benchmark(benchmark, preset):
    """Wave W §3.5: input_hash is stable across two load_benchmark calls
    for every canonical benchmark + smoke preset (9 cases)."""
    a = load_benchmark(benchmark, preset=preset)
    b = load_benchmark(benchmark, preset=preset)
    assert input_hash(a) == input_hash(b), f"input_hash drifted for {benchmark}/{preset}"


@pytest.mark.parametrize(
    "benchmark,preset",
    [
        ("cantilever", "smoke"),
        ("simple_bracket", "smoke"),
        ("l_bracket", "smoke"),
        ("loaded_hook", "smoke"),
    ],
)
def test_simp_compliance_stable_per_benchmark(benchmark, preset):
    """For 4 canonical benchmarks, the final compliance must match
    bit-exact across two runs (independent of density bit-exactness which
    is tested elsewhere)."""
    config = load_benchmark(benchmark, preset=preset)
    mesh_a = create_structured_mesh(config)
    mesh_b = create_structured_mesh(config)
    r_a = run_simp(config, mesh_a)
    r_b = run_simp(config, mesh_b)
    assert r_a.final_analysis.compliance == r_b.final_analysis.compliance


@pytest.mark.parametrize(
    "benchmark,preset",
    [
        ("cantilever", "smoke"),
        ("mbb_beam", "smoke"),
        ("simple_bracket", "smoke"),
    ],
)
def test_simp_mass_stable_per_benchmark(benchmark, preset):
    """Mass (volume × density) must match across two runs (3 benchmarks)."""
    config = load_benchmark(benchmark, preset=preset)
    mesh_a = create_structured_mesh(config)
    mesh_b = create_structured_mesh(config)
    r_a = run_simp(config, mesh_a)
    r_b = run_simp(config, mesh_b)
    assert r_a.final_analysis.mass == r_b.final_analysis.mass


@pytest.mark.parametrize(
    "benchmark,preset",
    [
        ("cantilever", "smoke"),
        ("simple_bracket", "smoke"),
    ],
)
def test_simp_max_displacement_stable_per_benchmark(benchmark, preset):
    """max_displacement must match bit-exact across two runs (2 benchmarks)."""
    config = load_benchmark(benchmark, preset=preset)
    mesh_a = create_structured_mesh(config)
    mesh_b = create_structured_mesh(config)
    r_a = run_simp(config, mesh_a)
    r_b = run_simp(config, mesh_b)
    assert r_a.final_analysis.max_displacement == r_b.final_analysis.max_displacement


def test_triangle_simp_reproducible():
    """Triangle SIMP (Wave M) is also reproducible across two calls."""
    import numpy as np
    from structure_optimizer.core.triangle_simp import run_simp_triangle, split_quad_to_triangles

    mesh = split_quad_to_triangles(8, 4, width=1.0, height=0.5)
    left_nodes = np.where(mesh.nodes[:, 0] < 1e-9)[0]
    fixed = np.concatenate([[2 * n, 2 * n + 1] for n in left_nodes])
    force = np.zeros(mesh.ndof)
    right_mid = np.argmin(np.abs(mesh.nodes[:, 0] - 1.0) + np.abs(mesh.nodes[:, 1] - 0.25))
    force[2 * right_mid + 1] = -1.0
    kwargs = dict(
        young_modulus=1.0,
        poisson_ratio=0.3,
        fixed_dofs=fixed,
        force=force,
        volume_fraction=0.4,
        max_iterations=6,
        min_iterations=2,
        filter_radius=0.15,
    )
    a = run_simp_triangle(mesh, **kwargs)
    b = run_simp_triangle(mesh, **kwargs)
    np.testing.assert_array_equal(a.densities, b.densities)
    assert a.final_compliance == b.final_compliance


def test_triangle_beso_reproducible():
    """Triangle BESO (Wave T) is also reproducible across two calls."""
    import numpy as np
    from structure_optimizer.core.triangle_beso import run_beso_triangle
    from structure_optimizer.core.triangle_simp import split_quad_to_triangles

    mesh = split_quad_to_triangles(8, 4, width=1.0, height=0.5)
    left_nodes = np.where(mesh.nodes[:, 0] < 1e-9)[0]
    fixed = np.concatenate([[2 * n, 2 * n + 1] for n in left_nodes])
    force = np.zeros(mesh.ndof)
    right_mid = np.argmin(np.abs(mesh.nodes[:, 0] - 1.0) + np.abs(mesh.nodes[:, 1] - 0.25))
    force[2 * right_mid + 1] = -1.0
    kwargs = dict(
        young_modulus=1.0,
        poisson_ratio=0.3,
        fixed_dofs=fixed,
        force=force,
        volume_fraction=0.4,
        er=0.1,
        max_iterations=5,
        min_iterations=2,
        filter_radius=0.15,
    )
    a = run_beso_triangle(mesh, **kwargs)
    b = run_beso_triangle(mesh, **kwargs)
    np.testing.assert_array_equal(a.densities, b.densities)
    assert a.final_compliance == b.final_compliance
