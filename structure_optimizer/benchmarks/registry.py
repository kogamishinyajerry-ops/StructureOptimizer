from pathlib import Path

from structure_optimizer.core.config import BenchmarkConfig, load_config


CONFIG_DIR = Path(__file__).resolve().parent / "configs"


def available_benchmarks() -> list[str]:
    return sorted(path.stem for path in CONFIG_DIR.glob("*.json"))


def config_path(name: str) -> Path:
    path = CONFIG_DIR / f"{name}.json"
    if not path.exists():
        known = ", ".join(available_benchmarks())
        raise ValueError(f"Unknown benchmark '{name}'. Available benchmarks: {known}")
    return path


def load_benchmark(name: str, preset: str | None = None) -> BenchmarkConfig:
    return load_config(config_path(name), preset=preset)

