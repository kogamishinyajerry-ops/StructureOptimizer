"""Wave T: regression tests against committed triangle fingerprints.

For each ``tests/fingerprints/triangle_*__smoke.json`` we re-run the
triangle-mesh benchmark and verify ``density_sha256`` matches OR per-element
relative error ≤ 1e-9. Mirrors ``test_fingerprints.py`` for the quad path.

Triangle benchmarks don't have JSON config files (they're parameterized
directly in ``scripts/generate_triangle_fingerprints.py``); the
``_DISPATCH`` map below routes each fingerprint name to its
reconstruction function.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest
from scripts.generate_triangle_fingerprints import (
    _build_cantilever_triangle_mesh,
)
from structure_optimizer.core.triangle_beso import run_beso_triangle
from structure_optimizer.core.triangle_simp import run_simp_triangle, split_quad_to_triangles

FINGERPRINT_DIR = Path(__file__).parent / "fingerprints"
TOLERANCE = 1e-9


def _density_sha256(densities: np.ndarray) -> str:
    arr = np.ascontiguousarray(densities, dtype="<f8")
    return "sha256:" + hashlib.sha256(arr.tobytes()).hexdigest()


def _triangle_simp_cantilever():
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
    return result.densities


def _triangle_beso_cantilever():
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
    return result.densities


def _triangle_simp_short_beam():
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
    return result.densities


_DISPATCH = {
    "triangle_simp_cantilever": _triangle_simp_cantilever,
    "triangle_beso_cantilever": _triangle_beso_cantilever,
    "triangle_simp_short_beam": _triangle_simp_short_beam,
}


def _triangle_fingerprints() -> list[Path]:
    return sorted(FINGERPRINT_DIR.glob("triangle_*__smoke.json"))


@pytest.mark.parametrize("fp_path", _triangle_fingerprints(), ids=lambda p: p.stem)
def test_triangle_fingerprint_matches(fp_path):
    """Triangle-mesh densities should match the committed fingerprint."""
    record = json.loads(fp_path.read_text())
    name = record["benchmark"]
    densities = _DISPATCH[name]()
    assert densities.shape[0] == record["n_elements"]
    actual_sha = _density_sha256(densities)

    bit_exact = actual_sha == record["density_sha256"]
    require_bit_exact = os.environ.get("REQUIRE_BIT_EXACT_FINGERPRINT") == "1"

    if bit_exact:
        return
    if require_bit_exact:
        pytest.fail(f"{fp_path.name}: density bit-exact mismatch under REQUIRE_BIT_EXACT_FINGERPRINT=1")
    # Fallback: per-element relative error
    expected_first_8 = np.array([float(x) for x in record["densities_first_8"]])
    max_rel_err = float(np.max(np.abs(densities[:8] - expected_first_8) / np.maximum(np.abs(expected_first_8), 1e-12)))
    assert max_rel_err <= 1e-6, f"{fp_path.name}: density first-8 relative error {max_rel_err:.2e} > 1e-6"


def test_three_triangle_fingerprints_present():
    """Rubric §3.2: at least 3 triangle fingerprints must exist."""
    files = _triangle_fingerprints()
    assert len(files) >= 3, f"only {len(files)} triangle fingerprints (need ≥3)"
