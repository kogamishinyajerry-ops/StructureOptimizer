"""Generate the v12 design-grade & adaptive fingerprints (Wave HHHH closure).

Runs five deterministic v12 drivers once and writes ``tests/fingerprints/*.json``
fixtures with the v5-v11 schema (``rubric_version`` + ``kind`` + a SHA + scalars).
The matching re-run recipes live in
``tests/test_multiphysics_fingerprints.py::_rerun``.

Five fast, deterministic drivers (no MMA loop, so CI-cheap): design-grade buckling
sensitivity (AAAA/D082), nested Clayton copula CDF (DDDD/D085), Korobov-lattice
Genz (EEEE/D086 — seeded, bit-reproducible on the canonical CI cell), laminate
[A,B,D] (FFFF/D087), flip-recovery CDT (GGGG/D088).

Usage:  python scripts/generate_v12_fingerprints.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh

REPO_ROOT = Path(__file__).resolve().parent.parent
FINGERPRINT_DIR = REPO_ROOT / "tests" / "fingerprints"

STAR = [
    [2.6146, 0.045], [0.3886, 0.0405], [2.1953, 0.578], [-0.096, 0.7683],
    [-2.5324, -0.7121], [-1.381, -1.0942], [-0.1425, -1.1], [0.558, -1.3289],
    [0.1514, -0.3447], [0.5424, -0.3312], [1.9375, -0.8374],
]


def _sha256(arr: np.ndarray) -> str:
    return "sha256:" + hashlib.sha256(np.ascontiguousarray(arr, dtype="<f8").tobytes()).hexdigest()


def _write(name: str, rec: dict) -> None:
    (FINGERPRINT_DIR / name).write_text(json.dumps(rec, indent=2))
    print(f"wrote {name}")


def gen_design_grade_buckling() -> None:
    from structure_optimizer.core.buckling import buckling_load_factor, design_grade_buckling_sensitivity
    from structure_optimizer.core.fem2d import solve_linear_elastic
    from structure_optimizer.core.simp import run_simp

    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    rho = run_simp(config, mesh).densities
    u = solve_linear_elastic(config, mesh, rho).displacements
    lambdas, phis = buckling_load_factor(config, mesh, rho, u, n_modes=1)
    dl = design_grade_buckling_sensitivity(config, mesh, rho, u, float(lambdas[0]), phis[:, 0])
    _write(
        "design_grade_buckling_cantilever__smoke.json",
        {
            "benchmark": "cantilever", "preset": "smoke",
            "rubric_version": "v12.0-wave-AAAA", "kind": "design_grade_buckling",
            "eigenvalue": float(lambdas[0]),
            "dl_sha256": _sha256(dl),
        },
    )


def gen_nested_clayton() -> None:
    from structure_optimizer.core.reliability import nested_clayton_copula

    c = nested_clayton_copula(4, [[0, 1], [2, 3]], 2.0, [6.0, 4.0])
    u = [0.4, 0.6, 0.5, 0.7]
    cdf = c.cdf(np.asarray(u))
    margins = np.array([c.bivariate_margin_cdf(0, 1, 0.4, 0.6), c.bivariate_margin_cdf(2, 3, 0.4, 0.6), c.bivariate_margin_cdf(0, 2, 0.4, 0.6)])
    _write(
        "nested_clayton_4d.json",
        {
            "benchmark": "nested_clayton", "preset": "n/a",
            "rubric_version": "v12.0-wave-DDDD", "kind": "nested_clayton",
            "clusters": [[0, 1], [2, 3]], "theta_outer": 2.0, "thetas_inner": [6.0, 4.0],
            "u": u, "cdf": float(cdf),
            "margins_sha256": _sha256(margins),
            "m01": float(margins[0]),
        },
    )


def gen_korobov_genz() -> None:
    from structure_optimizer.core.reliability import genz_mvn_cdf_lattice

    rho = 0.5
    R = (1 - rho) * np.eye(4) + rho * np.ones((4, 4))
    res = genz_mvn_cdf_lattice(np.ones(4), R, n_points=1021, n_shifts=12, a=76, seed=0)
    _write(
        "korobov_genz_equicorr.json",
        {
            "benchmark": "korobov_genz", "preset": "n/a",
            "rubric_version": "v12.0-wave-EEEE", "kind": "korobov_genz",
            "rho": rho, "n_points": 1021, "n_shifts": 12, "a": 76, "seed": 0,
            "value": res.value, "std_error": res.std_error,
            "value_sha256": _sha256(np.array([res.value, res.std_error])),
        },
    )


def gen_laminate_abd() -> None:
    from structure_optimizer.core.orthotropic_simp import laminate_abd, orthotropic_plane_stress_matrix

    d0 = orthotropic_plane_stress_matrix(130e9, 10e9, 0.28, 5e9)
    angles = np.deg2rad([45.0, -45.0, -45.0, 45.0])
    thick = np.full(4, 0.5)
    A, B, D = laminate_abd(d0, angles, thick)
    stacked = np.concatenate([A.ravel(), B.ravel(), D.ravel()])
    _write(
        "laminate_abd_symmetric.json",
        {
            "benchmark": "laminate", "preset": "n/a",
            "rubric_version": "v12.0-wave-FFFF", "kind": "laminate_abd",
            "angles_deg": [45.0, -45.0, -45.0, 45.0], "thicknesses": [0.5, 0.5, 0.5, 0.5],
            "A00": float(A[0, 0]), "B_absmax": float(np.abs(B).max()),
            "abd_sha256": _sha256(stacked),
        },
    )


def gen_cdt_recovery() -> None:
    from structure_optimizer.core.stl_export import _tri_area, constrained_delaunay_flip_recover

    pts, tris = constrained_delaunay_flip_recover([np.array(p, float) for p in STAR], refine=True)
    area = sum(_tri_area(pts[i], pts[j], pts[k]) for i, j, k in tris)
    flat = np.array(sorted(tuple(sorted(t)) for t in tris), dtype=float).ravel()
    _write(
        "cdt_flip_recovery_star.json",
        {
            "benchmark": "cdt_star", "preset": "n/a",
            "rubric_version": "v12.0-wave-GGGG", "kind": "cdt_flip_recovery",
            "n_triangles": len(tris), "total_area": float(area),
            "tris_sha256": _sha256(flat),
        },
    )


def main() -> None:
    gen_design_grade_buckling()
    gen_nested_clayton()
    gen_korobov_genz()
    gen_laminate_abd()
    gen_cdt_recovery()


if __name__ == "__main__":
    main()
