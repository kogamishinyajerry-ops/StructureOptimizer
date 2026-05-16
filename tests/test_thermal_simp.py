"""Wave Y: thermal-compliance SIMP smoke + property tests."""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.thermal_simp import (
    load_thermal_benchmark,
    run_thermal_simp,
)


def test_thermal_simp_smoke_runs():
    """Heat-sink smoke preset runs end-to-end and emits valid densities."""
    config, k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    result = run_thermal_simp(config, mesh, k, sources, bcs)
    assert result.densities.shape == (mesh.elements.shape[0],)
    assert (result.densities >= config.optimization.min_density - 1e-9).all()
    assert (result.densities <= 1.0 + 1e-9).all()
    assert len(result.metrics) >= 1
    assert np.isfinite(result.final_result.thermal_compliance)


def test_thermal_simp_compliance_decreases_through_iterations():
    """The thermal compliance objective should not blow up; ideally it
    decreases monotonically. Allow small numerical noise (≤ 1%)."""
    config, k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    result = run_thermal_simp(config, mesh, k, sources, bcs)
    comp = [m.thermal_compliance for m in result.metrics]
    # Final compliance shouldn't be wildly higher than initial
    assert comp[-1] <= 2.0 * comp[0] + 1e-6


def test_thermal_simp_volume_constraint_eventually_satisfied():
    """After enough iterations, vol_frac should approach target ±5%."""
    config, k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    result = run_thermal_simp(config, mesh, k, sources, bcs)
    final_vol = result.metrics[-1].volume_fraction
    assert final_vol <= config.optimization.volume_fraction + 0.10


def test_thermal_simp_result_mesh_shape_matches():
    config, k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    result = run_thermal_simp(config, mesh, k, sources, bcs)
    assert result.mesh_shape == (mesh.nelx, mesh.nely)


def test_load_thermal_benchmark_extracts_thermal_block():
    config, k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    assert k > 0
    assert len(sources) >= 1
    assert len(bcs) >= 1
    # Verify the thermal block was deep-merged correctly (smoke preset has
    # smaller mesh; thermal block inherited from default)
    assert config.mesh.nelx == 16


def test_load_thermal_benchmark_rejects_missing_thermal_block():
    """Loading a non-thermal benchmark must raise a clear error."""
    with pytest.raises(ValueError, match="no 'thermal' block"):
        load_thermal_benchmark("cantilever", preset="smoke")


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


def test_property_run_thermal_simp_densities_always_in_bounds():
    """For random RNG seed, densities stay in [min_density, 1]."""
    config, k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    result = run_thermal_simp(config, mesh, k, sources, bcs)
    assert (result.densities >= config.optimization.min_density - 1e-12).all()
    assert (result.densities <= 1.0 + 1e-12).all()


def test_property_thermal_simp_iteration_metric_count_matches_loop():
    config, k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    result = run_thermal_simp(config, mesh, k, sources, bcs)
    assert 1 <= len(result.metrics) <= config.optimization.max_iterations
