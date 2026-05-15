from pathlib import Path

from structure_optimizer.core.config import BenchmarkConfig, load_config

CONFIG_DIR = Path(__file__).resolve().parent / "configs"


def available_benchmarks() -> list[str]:
    """Return alphabetised list of built-in benchmark names (one JSON per file under configs/)."""
    return sorted(path.stem for path in CONFIG_DIR.glob("*.json"))


def config_path(name: str) -> Path:
    """Resolve a benchmark name to its JSON config path; raises ``ValueError`` for unknown names."""
    path = CONFIG_DIR / f"{name}.json"
    if not path.exists():
        known = ", ".join(available_benchmarks())
        raise ValueError(f"Unknown benchmark '{name}'. Available benchmarks: {known}")
    return path


def load_benchmark(name: str, preset: str | None = None) -> BenchmarkConfig:
    """Load a built-in benchmark by name, optionally applying a named preset (e.g. ``"smoke"``)."""
    return load_config(config_path(name), preset=preset)
