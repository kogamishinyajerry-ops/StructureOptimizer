"""Wave T: regenerate triangle-mesh fingerprints under ``tests/fingerprints/``.

Closes §3.2 v4 rubric (≥3 triangle fingerprints). Triangle paths
(SIMP-on-triangle from Wave M, BESO-on-triangle from Wave T) produce
``TriangleOptimizationResult`` / ``TriangleBesoResult`` rather than the
quad ``OptimizationResult``, so they need their own canonical scalars
record (no ``mass`` / no ``max_stress`` fields here).

Re-run when intentionally changing a triangle benchmark's expected
behavior::

    python scripts/generate_triangle_fingerprints.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from structure_optimizer.core.triangle_beso import run_beso_triangle
from structure_optimizer.core.triangle_simp import run_simp_triangle, split_quad_to_triangles

OUTPUT_DIR = Path(__file__).parent.parent / "tests" / "fingerprints"


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _density_fingerprint(densities: np.ndarray) -> str:
    arr = np.ascontiguousarray(densities, dtype="<f8")
    return _sha256_bytes(arr.tobytes())


def _scalar_fingerprint(scalars: dict[str, float]) -> str:
    arr = np.ascontiguousarray([float(scalars[k]) for k in sorted(scalars)], dtype="<f8")
    return _sha256_bytes(arr.tobytes())


def _build_cantilever_triangle_mesh(nelx: int = 12, nely: int = 6):
    mesh = split_quad_to_triangles(nelx, nely, width=2.0, height=1.0)
    left_nodes = np.where(mesh.nodes[:, 0] < 1e-9)[0]
    fixed_dofs = np.concatenate([[2 * n, 2 * n + 1] for n in left_nodes])
    right_mid = np.argmin(np.abs(mesh.nodes[:, 0] - 2.0) + np.abs(mesh.nodes[:, 1] - 0.5))
    force = np.zeros(mesh.ndof)
    force[2 * right_mid + 1] = -1.0
    return mesh, fixed_dofs, force


def regenerate_triangle_simp_cantilever() -> Path:
    mesh, fixed_dofs, force = _build_cantilever_triangle_mesh(nelx=12, nely=6)
    result = run_simp_triangle(
        mesh,
        young_modulus=1.0,
        poisson_ratio=0.3,
        fixed_dofs=fixed_dofs,
        force=force,
        volume_fraction=0.4,
        penalty=3.0,
        filter_radius=0.18,
        min_density=1e-3,
        max_iterations=12,
        min_iterations=3,
        change_tolerance=0.01,
    )
    scalars = {
        "baseline_compliance": float(result.baseline_compliance),
        "final_compliance": float(result.final_compliance),
        "final_max_disp": float(np.max(np.linalg.norm(result.final_displacements.reshape(-1, 2), axis=1))),
    }
    record = {
        "benchmark": "triangle_simp_cantilever",
        "preset": "smoke",
        "n_elements": int(result.densities.shape[0]),
        "density_sha256": _density_fingerprint(result.densities),
        "scalar_sha256": _scalar_fingerprint(scalars),
        "densities_first_8": [repr(float(x)) for x in result.densities[:8]],
        "scalars": {k: repr(v) for k, v in scalars.items()},
    }
    path = OUTPUT_DIR / "triangle_simp_cantilever__smoke.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return path


def regenerate_triangle_beso_cantilever() -> Path:
    mesh, fixed_dofs, force = _build_cantilever_triangle_mesh(nelx=12, nely=6)
    result = run_beso_triangle(
        mesh,
        young_modulus=1.0,
        poisson_ratio=0.3,
        fixed_dofs=fixed_dofs,
        force=force,
        volume_fraction=0.4,
        er=0.1,
        filter_radius=0.18,
        min_density=1e-3,
        max_iterations=10,
        min_iterations=2,
        change_tolerance=0.01,
    )
    scalars = {
        "baseline_compliance": float(result.baseline_compliance),
        "final_compliance": float(result.final_compliance),
        "final_volume_frac": float(result.metrics[-1].volume_fraction),
    }
    record = {
        "benchmark": "triangle_beso_cantilever",
        "preset": "smoke",
        "n_elements": int(result.densities.shape[0]),
        "density_sha256": _density_fingerprint(result.densities),
        "scalar_sha256": _scalar_fingerprint(scalars),
        "densities_first_8": [repr(float(x)) for x in result.densities[:8]],
        "scalars": {k: repr(v) for k, v in scalars.items()},
    }
    path = OUTPUT_DIR / "triangle_beso_cantilever__smoke.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return path


def regenerate_triangle_simp_short_beam() -> Path:
    """Short-beam triangle SIMP fingerprint (different aspect ratio than cantilever)."""
    mesh = split_quad_to_triangles(8, 8, width=1.0, height=1.0)
    bot_left = np.where((mesh.nodes[:, 0] < 1e-9) & (mesh.nodes[:, 1] < 1e-9))[0]
    bot_right = np.where((mesh.nodes[:, 0] > 1.0 - 1e-9) & (mesh.nodes[:, 1] < 1e-9))[0]
    fixed = np.concatenate([[2 * n, 2 * n + 1] for n in np.concatenate([bot_left, bot_right])])
    top_mid = np.argmin(np.abs(mesh.nodes[:, 0] - 0.5) + np.abs(mesh.nodes[:, 1] - 1.0))
    force = np.zeros(mesh.ndof)
    force[2 * top_mid + 1] = -1.0
    result = run_simp_triangle(
        mesh,
        young_modulus=1.0,
        poisson_ratio=0.3,
        fixed_dofs=fixed,
        force=force,
        volume_fraction=0.5,
        penalty=3.0,
        filter_radius=0.12,
        min_density=1e-3,
        max_iterations=10,
        min_iterations=3,
        change_tolerance=0.01,
    )
    scalars = {
        "baseline_compliance": float(result.baseline_compliance),
        "final_compliance": float(result.final_compliance),
        "final_max_disp": float(np.max(np.linalg.norm(result.final_displacements.reshape(-1, 2), axis=1))),
    }
    record = {
        "benchmark": "triangle_simp_short_beam",
        "preset": "smoke",
        "n_elements": int(result.densities.shape[0]),
        "density_sha256": _density_fingerprint(result.densities),
        "scalar_sha256": _scalar_fingerprint(scalars),
        "densities_first_8": [repr(float(x)) for x in result.densities[:8]],
        "scalars": {k: repr(v) for k, v in scalars.items()},
    }
    path = OUTPUT_DIR / "triangle_simp_short_beam__smoke.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for fn in (
        regenerate_triangle_simp_cantilever,
        regenerate_triangle_beso_cantilever,
        regenerate_triangle_simp_short_beam,
    ):
        path = fn()
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
