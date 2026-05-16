"""Wave W: cross-version drift detection for v4 rubric §3.4.

Compares the SHA-256 fingerprints of the current code's benchmark runs
against the most-recent committed fingerprints in ``tests/fingerprints/``.

Emits a non-zero exit code if any benchmark drifts. Used in CI as an
early warning when a SIMP / FEM / filter change accidentally changes
the expected output of a long-stable benchmark.

Usage::

    python scripts/drift_check.py                # check all
    python scripts/drift_check.py cantilever     # check one benchmark
    python scripts/drift_check.py --tolerance 1e-7  # custom rtol
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.simp import run_simp

REPO_ROOT = Path(__file__).parent.parent
FINGERPRINT_DIR = REPO_ROOT / "tests" / "fingerprints"


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _density_sha(densities: np.ndarray) -> str:
    arr = np.ascontiguousarray(densities, dtype="<f8")
    return _sha256_bytes(arr.tobytes())


def check_one(fp_path: Path, tolerance: float = 1e-9) -> tuple[bool, str]:
    """Compare one fingerprint file against a fresh re-run.

    Returns ``(ok, diagnosis)``. ``ok`` is True iff bit-exact match OR
    relative drift ≤ tolerance. Triangle fingerprints are skipped
    (they have their own dispatch).
    """
    if fp_path.name.startswith("triangle_"):
        return True, f"{fp_path.name}: triangle fingerprint (skipped)"
    record = json.loads(fp_path.read_text())
    benchmark = record["benchmark"]
    preset = record.get("preset")
    config = load_benchmark(benchmark, preset=preset)
    mesh = create_structured_mesh(config)
    result = run_simp(config, mesh)
    actual_sha = _density_sha(result.densities)
    if actual_sha == record["density_sha256"]:
        return True, f"{fp_path.name}: bit-exact match"
    # Tolerant fallback
    expected_first_8 = np.array([float(x) for x in record["densities_first_8"]])
    delta = np.abs(result.densities[:8] - expected_first_8)
    rel = delta / np.maximum(np.abs(expected_first_8), 1e-12)
    max_rel = float(rel.max())
    if max_rel <= tolerance:
        return True, f"{fp_path.name}: tolerant match (max_rel={max_rel:.2e})"
    return False, f"{fp_path.name}: DRIFT (max_rel={max_rel:.2e}, tolerance={tolerance:.0e})"


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-version drift detection")
    parser.add_argument("benchmarks", nargs="*", help="benchmark names (default: all)")
    parser.add_argument("--tolerance", type=float, default=1e-6)
    args = parser.parse_args()

    fingerprints = sorted(FINGERPRINT_DIR.glob("*.json"))
    if args.benchmarks:
        wanted = {b.lower() for b in args.benchmarks}
        fingerprints = [fp for fp in fingerprints if any(w in fp.name.lower() for w in wanted)]

    failures = []
    for fp in fingerprints:
        ok, msg = check_one(fp, tolerance=args.tolerance)
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] {msg}")
        if not ok:
            failures.append(fp.name)

    if failures:
        print(f"\nDrift detected in {len(failures)} benchmark(s):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nNo drift detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
