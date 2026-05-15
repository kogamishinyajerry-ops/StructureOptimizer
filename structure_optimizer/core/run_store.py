from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.simp import IterationMetric

RUNS_ROOT = Path("runs")


def input_hash(config: BenchmarkConfig) -> str:
    payload = json.dumps(config.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def create_run_dir(config: BenchmarkConfig, runs_root: Path = RUNS_ROOT) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_dir = runs_root / config.name / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def save_input(run_dir: Path, config: BenchmarkConfig) -> None:
    write_json(run_dir / "input.json", config.to_dict())


def save_metrics(run_dir: Path, metrics: list[IterationMetric]) -> None:
    with (run_dir / "metrics.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["iteration", "compliance", "volume_fraction", "change", "max_displacement", "mass"],
        )
        writer.writeheader()
        for metric in metrics:
            writer.writerow(asdict(metric))


def load_metrics(run_dir: Path) -> list[dict[str, float]]:
    path = run_dir / "metrics.csv"
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        rows = []
        for row in csv.DictReader(fh):
            rows.append(
                {
                    "iteration": int(row["iteration"]),
                    "compliance": float(row["compliance"]),
                    "volume_fraction": float(row["volume_fraction"]),
                    "change": float(row["change"]),
                    "max_displacement": float(row["max_displacement"]),
                    "mass": float(row["mass"]),
                }
            )
        return rows


def save_density(run_dir: Path, densities: np.ndarray) -> None:
    np.save(run_dir / "density.npy", densities)


def load_density(run_dir: Path) -> np.ndarray:
    return np.load(run_dir / "density.npy")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())
