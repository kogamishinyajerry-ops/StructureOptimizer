"""Wave P: regenerate ``tests/fingerprints/*.json`` for the canonical benchmark set.

Each benchmark+preset combo gets a JSON file with:

- ``benchmark`` / ``preset``
- ``input_hash`` (existing canonical config SHA-256, for provenance)
- ``density_sha256`` — SHA-256 of the float64 ``densities`` array bytes
  (sensitive to any ordering or value change)
- ``scalar_sha256`` — SHA-256 of canonical bytes for a small set of
  scalar metrics (compliance, mass, max_displacement, max_stress)
- ``densities_sample`` — the first 8 values of densities, written as
  full-precision repr() so a human can spot-check
- ``scalars`` — same scalars, full-precision repr

Re-run when intentionally changing a benchmark's expected behavior:

    python scripts/generate_fingerprints.py

CI / tests/test_fingerprints.py compares against the committed JSON;
mismatch indicates either an unintended numerical regression OR an
intended change that requires re-generating + re-committing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.run_store import input_hash
from structure_optimizer.core.simp import run_simp

FINGERPRINT_TARGETS: list[tuple[str, str | None]] = [
    ("mbb_beam", "smoke"),
    ("cantilever", "smoke"),
    ("l_bracket", "smoke"),
    ("simple_bracket", "smoke"),
    ("loaded_hook", None),
    ("multi_load_cantilever", "smoke"),
    ("stress_limited_bracket", "smoke"),
]

OUTPUT_DIR = Path(__file__).parent.parent / "tests" / "fingerprints"


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _density_fingerprint(densities: np.ndarray) -> str:
    """SHA-256 of float64 little-endian densities bytes (platform-stable)."""
    arr = np.ascontiguousarray(densities, dtype="<f8")
    return _sha256_bytes(arr.tobytes())


def _scalar_fingerprint(scalars: dict[str, float]) -> str:
    """SHA-256 of canonical (sorted-key) scalar bytes."""
    arr = np.ascontiguousarray(
        [float(scalars[k]) for k in sorted(scalars)],
        dtype="<f8",
    )
    return _sha256_bytes(arr.tobytes())


def regenerate_one(benchmark: str, preset: str | None) -> Path:
    config = load_benchmark(benchmark, preset=preset)
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    scalars = {
        "compliance": float(result.final_analysis.compliance),
        "mass": float(result.final_analysis.mass),
        "max_displacement": float(result.final_analysis.max_displacement),
        "max_stress": float(result.final_analysis.max_stress),
        "baseline_compliance": float(result.baseline.compliance),
    }
    record = {
        "benchmark": benchmark,
        "preset": preset,
        "input_hash": input_hash(config),
        "n_elements": int(result.densities.shape[0]),
        "density_sha256": _density_fingerprint(result.densities),
        "scalar_sha256": _scalar_fingerprint(scalars),
        "densities_first_8": [repr(float(x)) for x in result.densities[:8]],
        "scalars": {k: repr(v) for k, v in scalars.items()},
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{benchmark}__{preset or 'default'}.json"
    path = OUTPUT_DIR / name
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return path


def main() -> None:
    for benchmark, preset in FINGERPRINT_TARGETS:
        path = regenerate_one(benchmark, preset)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
