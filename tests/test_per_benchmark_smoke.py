"""Wave R: per-benchmark smoke tests across all canonical benchmarks.

Adds parametrized coverage for each registered benchmark so a regression
in any one of them is caught individually (vs the existing tests which
mostly target mbb_beam / cantilever specifically).

Pinned per benchmark (uses smoke preset where available, default otherwise):

- ``run_simp`` produces n_elements densities in valid range
- ``BenchmarkConfig._repr_html_`` produces a non-empty HTML string
  containing the benchmark name
- ``input_hash`` is stable across two ``load_benchmark`` calls
- mesh dims match config

Each benchmark contributes 4 tests via parametrize → ≥32 tests over 8
benchmarks (helps push toward §4.1 ≥400).
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import available_benchmarks, load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.run_store import input_hash
from structure_optimizer.core.simp import run_simp


def _smoke_preset_or_default(name: str) -> str | None:
    """Return ``"smoke"`` if the benchmark has it, otherwise ``None``.

    ``loaded_hook`` and ``large_cantilever`` warrant case-by-case decisions:
    - loaded_hook has no smoke preset → use default
    - large_cantilever's default is 500×500 (too slow for default pytest);
      excluded from these tests via the dedicated perf suite
    """
    cfg = load_benchmark(name)
    if "smoke" in cfg.to_dict().get("presets", {}):
        return "smoke"
    return None


_BENCHMARKS = [
    n
    for n in available_benchmarks()
    if n not in {"large_cantilever", "xlarge_cantilever"}
]


@pytest.mark.parametrize("benchmark", _BENCHMARKS)
def test_benchmark_simp_runs(benchmark):
    preset = _smoke_preset_or_default(benchmark)
    config = load_benchmark(benchmark, preset=preset)
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    assert result.densities.shape[0] == mesh.elements.shape[0]
    assert (result.densities >= config.optimization.min_density - 1e-9).all()
    assert (result.densities <= 1.0 + 1e-9).all()
    assert np.isfinite(result.final_analysis.compliance)


@pytest.mark.parametrize("benchmark", _BENCHMARKS)
def test_benchmark_config_repr_html_works(benchmark):
    config = load_benchmark(benchmark, preset=_smoke_preset_or_default(benchmark))
    html = config._repr_html_()
    assert benchmark in html
    assert "BenchmarkConfig" in html


@pytest.mark.parametrize("benchmark", _BENCHMARKS)
def test_benchmark_input_hash_stable(benchmark):
    a = load_benchmark(benchmark, preset=_smoke_preset_or_default(benchmark))
    b = load_benchmark(benchmark, preset=_smoke_preset_or_default(benchmark))
    assert input_hash(a) == input_hash(b)


@pytest.mark.parametrize("benchmark", _BENCHMARKS)
def test_benchmark_mesh_dims_match_config(benchmark):
    config = load_benchmark(benchmark, preset=_smoke_preset_or_default(benchmark))
    mesh = create_structured_mesh(config)
    assert mesh.nelx == config.mesh.nelx
    assert mesh.nely == config.mesh.nely
    expected_n_elem = config.mesh.nelx * config.mesh.nely
    assert mesh.elements.shape[0] == expected_n_elem


@pytest.mark.parametrize("benchmark", _BENCHMARKS)
def test_benchmark_simp_result_repr_html_works(benchmark):
    config = load_benchmark(benchmark, preset=_smoke_preset_or_default(benchmark))
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    html = result._repr_html_()
    assert "OptimizationResult" in html
    assert "Compliance" in html
