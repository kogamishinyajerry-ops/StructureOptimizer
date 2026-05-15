import pytest
from structure_optimizer.benchmarks.registry import available_benchmarks, load_benchmark
from structure_optimizer.core.config import ConfigError, parse_config, validate_config


def test_invalid_volume_fraction_is_rejected():
    config = load_benchmark("mbb_beam", preset="smoke").to_dict()
    config["optimization"]["volume_fraction"] = -0.1

    with pytest.raises(ConfigError, match="volume_fraction"):
        validate_config(parse_config(config))


def test_missing_loads_are_rejected():
    config = load_benchmark("mbb_beam", preset="smoke").to_dict()
    config["loads"] = []

    with pytest.raises(ConfigError, match="load"):
        validate_config(parse_config(config))


def test_required_benchmark_configs_validate():
    names = available_benchmarks()
    assert {"mbb_beam", "cantilever", "l_bracket"}.issubset(set(names))
    for name in ("mbb_beam", "cantilever", "l_bracket"):
        config = load_benchmark(name)
        assert config.name == name
