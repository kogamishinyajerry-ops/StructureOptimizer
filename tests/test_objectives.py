"""Wave E: multi-load-case compliance aggregator tests.

Pins these properties of ``core/objectives.py``:

- ``weighted_sum`` with all weights = 1 reduces to the same value as ``average``.
- ``worst_case`` ≥ ``average`` for any case set (worst is at least the mean).
- ``worst_case`` ≥ each individual case compliance.
- ``element_strain_energy`` field follows the same aggregator semantics.
- Empty case list raises ValueError.
- Unknown aggregator name raises ValueError.
- ``solve_and_aggregate`` is the composition of ``solve_all_cases`` and
  ``aggregate``.
- The multi_load_cantilever benchmark loads and runs under all three modes.
"""

from __future__ import annotations

import random

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.config import (
    BenchmarkConfig,
    ConfigError,
    parse_config,
    validate_config,
)
from structure_optimizer.core.fem2d import FEMResult
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.objectives import (
    AGGREGATORS,
    CaseResult,
    aggregate,
    solve_all_cases,
    solve_and_aggregate,
)
from structure_optimizer.core.simp import run_simp


def _synth_case(name: str, weight: float, compliance: float, strain_energy: np.ndarray) -> CaseResult:
    """Build a synthetic CaseResult with a given compliance + strain energy field."""
    return CaseResult(
        name=name,
        weight=weight,
        result=FEMResult(
            displacements=np.zeros(8),
            compliance=compliance,
            max_displacement=compliance * 0.001,
            max_stress=compliance * 0.01,
            mass=1.0,
            element_strain_energy=strain_energy.astype(float).copy(),
        ),
    )


def _benchmark(**overrides) -> BenchmarkConfig:
    """Build a multi-case benchmark synthetically."""
    raw = {
        "name": "test_objectives_synth",
        "dimension": "2d",
        "units": "mm_N_MPa",
        "thickness": 1.0,
        "mesh": {"type": "structured_quad", "nelx": 8, "nely": 4, "width": 8.0, "height": 4.0},
        "material": {"young_modulus": 1000.0, "poisson_ratio": 0.3, "density": 1.0},
        "boundary_conditions": [{"selector": "left_edge", "components": ["ux", "uy"]}],
        "load_cases": [
            {"name": "a", "weight": 2.0, "loads": [{"selector": "right_mid", "fx": 0.0, "fy": -1.0}]},
            {"name": "b", "weight": 1.0, "loads": [{"selector": "right_mid", "fx": 1.0, "fy": 0.0}]},
        ],
        "optimization": {
            "objective": "min_compliance",
            "volume_fraction": 0.4,
            "penalty": 3.0,
            "filter_radius": 1.5,
            "max_iterations": 3,
            "min_iterations": 1,
            "change_tolerance": 0.01,
            "min_density": 0.001,
        },
    }
    raw.update(overrides)
    config = parse_config(raw)
    validate_config(config)
    return config


# --- pure aggregator semantics ----------------------------------------


def test_aggregators_set_contains_three_modes():
    assert {"weighted_sum", "average", "worst_case"} == AGGREGATORS


def test_average_equals_weighted_sum_when_weights_are_equal():
    """When all weights are equal, weighted_sum and average must coincide."""
    energy_a = np.array([1.0, 2.0, 3.0, 4.0])
    energy_b = np.array([4.0, 3.0, 2.0, 1.0])
    cases = [_synth_case("a", 1.0, 10.0, energy_a), _synth_case("b", 1.0, 20.0, energy_b)]
    ws = aggregate("weighted_sum", cases)
    avg = aggregate("average", cases)
    assert ws.compliance == pytest.approx(avg.compliance)
    assert np.allclose(ws.element_strain_energy, avg.element_strain_energy)


def test_weighted_sum_honors_user_weights():
    """weighted_sum with weights (2, 1) on compliances (10, 20) → 40/3 ≈ 13.333."""
    energy_a = np.array([1.0, 0.0])
    energy_b = np.array([0.0, 1.0])
    cases = [_synth_case("a", 2.0, 10.0, energy_a), _synth_case("b", 1.0, 20.0, energy_b)]
    result = aggregate("weighted_sum", cases)
    assert result.compliance == pytest.approx((2 * 10 + 1 * 20) / 3)
    assert np.allclose(result.element_strain_energy, np.array([2 / 3, 1 / 3]))


def test_average_ignores_user_weights():
    """average must collapse to plain mean regardless of user weights."""
    energy = np.array([1.0])
    cases = [_synth_case("a", 100.0, 10.0, energy), _synth_case("b", 1.0, 20.0, energy)]
    result = aggregate("average", cases)
    assert result.compliance == pytest.approx(15.0)


def test_worst_case_picks_argmax_compliance():
    """worst_case = max over cases; strain energy follows the argmax case."""
    energy_a = np.array([1.0, 0.0])
    energy_b = np.array([0.0, 10.0])
    cases = [_synth_case("a", 1.0, 5.0, energy_a), _synth_case("b", 1.0, 50.0, energy_b)]
    result = aggregate("worst_case", cases)
    assert result.compliance == pytest.approx(50.0)
    assert np.allclose(result.element_strain_energy, energy_b)


def test_worst_case_geq_average_property():
    """Property test: worst_case ≥ average for any random case set."""
    rng = random.Random(20260516)
    for _ in range(50):
        n_cases = rng.randint(2, 6)
        cases = [
            _synth_case(f"c{i}", rng.uniform(0.5, 5.0), rng.uniform(0.0, 100.0), np.array([rng.random()]))
            for i in range(n_cases)
        ]
        worst = aggregate("worst_case", cases).compliance
        avg = aggregate("average", cases).compliance
        assert worst >= avg - 1e-12, f"worst {worst} < avg {avg} for cases {[c.result.compliance for c in cases]}"


def test_worst_case_geq_each_case_compliance():
    rng = random.Random(20260517)
    for _ in range(20):
        n_cases = rng.randint(1, 5)
        cases = [_synth_case(f"c{i}", 1.0, rng.uniform(0.0, 100.0), np.array([0.0])) for i in range(n_cases)]
        worst = aggregate("worst_case", cases).compliance
        for case in cases:
            assert worst >= case.result.compliance - 1e-12


def test_max_displacement_takes_worst_over_cases_regardless_of_mode():
    """All 3 aggregators must report the worst max_displacement, not aggregated."""
    energy = np.array([1.0])
    case_a = CaseResult(
        name="a",
        weight=1.0,
        result=FEMResult(
            displacements=np.zeros(8),
            compliance=10.0,
            max_displacement=0.05,
            max_stress=100.0,
            mass=1.0,
            element_strain_energy=energy,
        ),
    )
    case_b = CaseResult(
        name="b",
        weight=1.0,
        result=FEMResult(
            displacements=np.zeros(8),
            compliance=20.0,
            max_displacement=0.20,
            max_stress=50.0,
            mass=1.0,
            element_strain_energy=energy,
        ),
    )
    for mode in AGGREGATORS:
        result = aggregate(mode, [case_a, case_b])
        assert result.max_displacement == pytest.approx(0.20)
        assert result.max_stress == pytest.approx(100.0)


def test_aggregate_rejects_empty_case_list():
    with pytest.raises(ValueError, match="at least one CaseResult"):
        aggregate("weighted_sum", [])


def test_aggregate_rejects_unknown_aggregator():
    energy = np.array([1.0])
    cases = [_synth_case("a", 1.0, 10.0, energy)]
    with pytest.raises(ValueError, match="unknown aggregator"):
        aggregate("squared_sum", cases)


# --- config parsing ----------------------------------------------------


def test_default_aggregator_is_weighted_sum():
    config = _benchmark()
    assert config.optimization.case_aggregator == "weighted_sum"


def test_config_accepts_all_three_aggregators():
    for mode in ("weighted_sum", "average", "worst_case"):
        config = _benchmark(optimization={**_benchmark().optimization.__dict__, "case_aggregator": mode})
        assert config.optimization.case_aggregator == mode


def test_config_rejects_unknown_aggregator():
    with pytest.raises(ConfigError, match="case_aggregator"):
        _benchmark(optimization={**_benchmark().optimization.__dict__, "case_aggregator": "tricky"})


# --- integration: solve + aggregate + run_simp ------------------------


def test_solve_all_cases_returns_per_case_results():
    config = _benchmark()
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    cases = solve_all_cases(config, mesh, densities, config.load_cases)
    assert [c.name for c in cases] == ["a", "b"]
    assert all(c.result.compliance >= 0 for c in cases)


def test_solve_and_aggregate_matches_manual_composition():
    config = _benchmark()
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.5)
    via_helper = solve_and_aggregate(config, mesh, densities, config.load_cases, "average")
    cases = solve_all_cases(config, mesh, densities, config.load_cases)
    via_manual = aggregate("average", cases)
    assert via_helper.compliance == pytest.approx(via_manual.compliance)
    assert np.allclose(via_helper.element_strain_energy, via_manual.element_strain_energy)


def test_run_simp_worst_case_compliance_geq_average():
    """End-to-end: optimizing with worst_case yields aggregate compliance ≥ optimizing
    with average for the same case set (worst_case is the more conservative target)."""
    config_avg = _benchmark(optimization={**_benchmark().optimization.__dict__, "case_aggregator": "average"})
    config_worst = _benchmark(optimization={**_benchmark().optimization.__dict__, "case_aggregator": "worst_case"})
    mesh_avg = create_structured_mesh(config_avg)
    mesh_worst = create_structured_mesh(config_worst)
    res_avg = run_simp(config_avg, mesh_avg)
    res_worst = run_simp(config_worst, mesh_worst)
    # When evaluated under worst_case semantics, the worst_case-trained design
    # should not be worse than the average-trained design.
    avg_eval_worst = solve_and_aggregate(
        config_worst, mesh_worst, res_avg.densities, config_worst.load_cases, "worst_case"
    )
    worst_eval_worst = res_worst.final_analysis.compliance
    # Robust design should be at least as good as the average design on the
    # worst-case metric (within 5% tolerance for finite-iteration noise).
    assert worst_eval_worst <= avg_eval_worst.compliance * 1.05


# --- benchmark loading ------------------------------------------------


def test_multi_load_cantilever_benchmark_loads():
    config = load_benchmark("multi_load_cantilever", preset="smoke")
    assert len(config.load_cases) == 3
    assert {c.name for c in config.load_cases} == {"down", "up", "shear"}
    assert config.optimization.case_aggregator == "worst_case"


def test_multi_load_cantilever_runs_end_to_end_under_all_aggregators():
    """Smoke test: each preset runs to completion and produces non-empty density."""
    for preset, expected_agg in [("smoke", "worst_case"), ("weighted", "weighted_sum"), ("average", "average")]:
        if preset == "smoke":
            config = load_benchmark("multi_load_cantilever", preset="smoke")
        else:
            # Combine smoke mesh + alternate aggregator
            from structure_optimizer.benchmarks.registry import config_path
            from structure_optimizer.core.config import load_config

            config = load_config(config_path("multi_load_cantilever"), preset=preset)
            # Override to smoke mesh by re-parsing with deep merge
            raw = config.to_dict()
            raw["mesh"]["nelx"] = 24
            raw["mesh"]["nely"] = 10
            raw["mesh"]["width"] = 24.0
            raw["mesh"]["height"] = 10.0
            raw["optimization"]["max_iterations"] = 8
            raw["optimization"]["min_iterations"] = 8
            config = parse_config(raw)
            validate_config(config)
        assert config.optimization.case_aggregator == expected_agg
        mesh = create_structured_mesh(config)
        result = run_simp(config, mesh)
        assert result.densities.shape == (mesh.elements.shape[0],)
        assert (result.densities >= 0).all() and (result.densities <= 1.0).all()
        assert len(result.metrics) >= 1
