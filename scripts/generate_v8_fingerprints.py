"""Generate the v8 closing-the-loop multi-physics fingerprints (Wave BBB).

Runs each v8 driver once and writes a ``tests/fingerprints/*.json`` fixture with
the same schema as the v5/v6/v7 multi-physics fingerprints (``rubric_version`` +
a ``kind`` + a physics SHA + human-readable scalars). The matching re-run recipes
live in ``tests/test_multiphysics_fingerprints.py::_rerun`` — running this
generator then that test confirms the pair is consistent.

Five deterministic drivers (no RNG-sensitive front shapes): nonlinear TL OC loop
(UU), general-marginal Nataf correlation matrix (XX), series-system reliability
bounds (ZZ), fibre-steering thermal TO angles (YY), and the marching-squares
holed-cap triangulation (AAA).

Usage:  python scripts/generate_v8_fingerprints.py
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

# Shared constants for the general-Nataf fingerprint (mirrored in the recipe).
NATAF_GEN_CORR = [[1.0, 0.5], [0.5, 1.0]]
# Shared constants for the series-system fingerprint.
SERIES_BETAS = [2.0, 2.5, 3.0]
# Shared geometry for the holed-cap fingerprint.
HOLE_OUTER = [[6.0, 6.0], [34.0, 6.0], [34.0, 34.0], [6.0, 34.0]]
HOLE_INNER = [[15.0, 15.0], [25.0, 15.0], [25.0, 25.0], [15.0, 25.0]]


def _sha256(arr: np.ndarray) -> str:
    return "sha256:" + hashlib.sha256(np.ascontiguousarray(arr, dtype="<f8").tobytes()).hexdigest()


def _write(name: str, rec: dict) -> None:
    path = FINGERPRINT_DIR / f"{name}.json"
    path.write_text(json.dumps(rec, indent=2) + "\n")
    print(f"wrote {path.relative_to(REPO_ROOT)}")


def gen_nonlinear_oc() -> None:
    from structure_optimizer.core.nonlinear_simp import nonlinear_to_oc

    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    r = nonlinear_to_oc(config, mesh, n_load_steps=3, max_iter=6)
    _write(
        "nonlinear_oc_cantilever__smoke",
        {
            "benchmark": "cantilever",
            "preset": "smoke",
            "rubric_version": "v8.0-wave-UU",
            "kind": "nonlinear_oc",
            "n_load_steps": 3,
            "max_iter": 6,
            "densities_sha256": _sha256(np.asarray(r.densities)),
            "compliance_final": float(r.compliance_history[-1]),
            "converged": bool(r.converged),
        },
    )


def gen_general_nataf() -> None:
    from structure_optimizer.core.reliability import Marginal, build_nataf_general

    marginals = [Marginal("weibull", 5.0, 130.0), Marginal("gumbel", 70.0, 12.0)]
    nataf = build_nataf_general(marginals, np.asarray(NATAF_GEN_CORR))
    _write(
        "general_nataf_weibull_gumbel",
        {
            "benchmark": "weibull_gumbel_pair",
            "rubric_version": "v8.0-wave-XX",
            "kind": "general_nataf",
            "correlation_x": NATAF_GEN_CORR,
            "correlation_u_sha256": _sha256(np.asarray(nataf.correlation_u)),
            "rho_u_01": float(nataf.correlation_u[0, 1]),
        },
    )


def gen_system_reliability() -> None:
    from structure_optimizer.core.reliability import system_reliability_series

    r = system_reliability_series(SERIES_BETAS)
    bounds = np.array([r["p_failure_lower"], r["p_failure_upper"], r["simple_lower"], r["simple_upper"]])
    _write(
        "system_reliability_series",
        {
            "benchmark": "series_system",
            "rubric_version": "v8.0-wave-ZZ",
            "kind": "system_reliability",
            "betas": SERIES_BETAS,
            "bounds_sha256": _sha256(bounds),
            "p_failure_lower": float(r["p_failure_lower"]),
            "p_failure_upper": float(r["p_failure_upper"]),
        },
    )


def gen_fibre_steering() -> None:
    from structure_optimizer.core.thermal_simp import fibre_steering_thermal_to, load_thermal_benchmark

    config, _k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    rho = np.full(mesh.elements.shape[0], 1.0)
    r = fibre_steering_thermal_to(
        config, mesh, rho, 5.0, 1.0, n_steps=10, step=0.3, heat_sources=sources, thermal_bcs=bcs
    )
    _write(
        "fibre_steering_heat_sink__smoke",
        {
            "benchmark": "heat_sink",
            "preset": "smoke",
            "rubric_version": "v8.0-wave-YY",
            "kind": "fibre_steering",
            "kxx": 5.0,
            "kyy": 1.0,
            "n_steps": 10,
            "step": 0.3,
            "angles_sha256": _sha256(np.asarray(r.angles)),
            "compliance_initial": float(r.compliance_history[0]),
            "compliance_final": float(r.compliance_history[-1]),
        },
    )


def gen_holed_cap() -> None:
    from structure_optimizer.core.stl_export import _tri_area, triangulate_with_holes

    pts, tris = triangulate_with_holes(HOLE_OUTER, [HOLE_INNER])
    area = sum(_tri_area(pts[i], pts[j], pts[k]) for i, j, k in tris)
    _write(
        "holed_cap_rect",
        {
            "benchmark": "rect_with_rect_hole",
            "rubric_version": "v8.0-wave-AAA",
            "kind": "holed_cap",
            "vertices_sha256": _sha256(np.asarray(pts)),
            "n_triangles": len(tris),
            "cross_section_area": float(area),
        },
    )


def main() -> None:
    gen_nonlinear_oc()
    gen_general_nataf()
    gen_system_reliability()
    gen_fibre_steering()
    gen_holed_cap()
    print("v8 fingerprints generated.")


if __name__ == "__main__":
    main()
