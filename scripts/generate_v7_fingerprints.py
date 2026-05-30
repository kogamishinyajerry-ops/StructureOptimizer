"""Generate the v7 production-driver multi-physics fingerprints (Wave TT).

Runs each v7 driver once and writes a ``tests/fingerprints/*.json`` fixture with
the same schema as the v5/v6 multi-physics fingerprints (``rubric_version`` + a
``kind`` + a physics SHA + human-readable scalars). The matching re-run recipes
live in ``tests/test_multiphysics_fingerprints.py::_rerun`` — running this
generator then that test confirms the pair is consistent.

Five deterministic drivers (no RNG-sensitive front shapes): TL adjoint, Nataf
correlated FORM, dynamic-compliance sensitivity, per-element anisotropic thermal
field, and the ear-clipping holed-polygon triangulation.

Usage:  python scripts/generate_v7_fingerprints.py
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

# Shared constants for the Nataf correlated-FORM fingerprint (mirrored in the
# rerun recipe so the limit state is reconstructable).
NATAF_MEAN = [10.0, 8.0, 5.0]
NATAF_STD = [2.0, 1.5, 1.0]
NATAF_CORR = [[1.0, 0.5, -0.3], [0.5, 1.0, 0.2], [-0.3, 0.2, 1.0]]
NATAF_A0 = 40.0
NATAF_A = [1.0, 1.0, 1.0]


def _sha256(arr: np.ndarray) -> str:
    return "sha256:" + hashlib.sha256(np.ascontiguousarray(arr, dtype="<f8").tobytes()).hexdigest()


def _write(name: str, rec: dict) -> None:
    path = FINGERPRINT_DIR / f"{name}.json"
    path.write_text(json.dumps(rec, indent=2) + "\n")
    print(f"wrote {path.relative_to(REPO_ROOT)}")


def gen_tl_adjoint() -> None:
    from structure_optimizer.core.nonlinear_simp import tl_adjoint_compliance_sensitivity

    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.6)
    r = tl_adjoint_compliance_sensitivity(config, mesh, densities, n_load_steps=3)
    _write(
        "tl_adjoint_cantilever__smoke",
        {
            "benchmark": "cantilever",
            "preset": "smoke",
            "rubric_version": "v7.0-wave-OO",
            "kind": "tl_adjoint",
            "n_load_steps": 3,
            "sensitivity_sha256": _sha256(np.asarray(r.sensitivity)),
            "compliance": float(r.compliance),
            "converged": bool(r.converged),
        },
    )


def gen_nataf_form() -> None:
    from structure_optimizer.core.reliability import correlated_gaussian_reliability

    a0, a = NATAF_A0, np.asarray(NATAF_A)
    r = correlated_gaussian_reliability(NATAF_MEAN, NATAF_STD, NATAF_CORR, lambda x: a0 - a @ x)
    _write(
        "nataf_correlated_form",
        {
            "benchmark": "correlated_gaussian",
            "rubric_version": "v7.0-wave-PP",
            "kind": "nataf_correlated_form",
            "mean": NATAF_MEAN,
            "std": NATAF_STD,
            "correlation": NATAF_CORR,
            "a0": NATAF_A0,
            "a": NATAF_A,
            "mpp_sha256": _sha256(np.asarray(r.mpp)),
            "beta": float(r.beta),
            "p_failure": float(r.p_failure),
            "converged": bool(r.converged),
        },
    )


def gen_dynamic_compliance() -> None:
    from structure_optimizer.core.freq_response import dynamic_compliance_sensitivity

    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.6)
    r = dynamic_compliance_sensitivity(config, mesh, densities, omega=8.0, alpha=0.5, beta=1e-4)
    _write(
        "dynamic_compliance_cantilever__smoke",
        {
            "benchmark": "cantilever",
            "preset": "smoke",
            "rubric_version": "v7.0-wave-RR",
            "kind": "dynamic_compliance",
            "omega": 8.0,
            "alpha": 0.5,
            "beta": 1e-4,
            "sensitivity_sha256": _sha256(np.asarray(r.sensitivity)),
            "objective": float(r.objective),
            "c_real": float(r.dynamic_compliance.real),
            "c_imag": float(r.dynamic_compliance.imag),
        },
    )


def gen_anisotropic_thermal_field() -> None:
    from structure_optimizer.core.thermal import orientation_field_to_tensors, solve_thermal
    from structure_optimizer.core.thermal_simp import load_thermal_benchmark

    config, k_scalar, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    n_elem = mesh.elements.shape[0]
    densities = np.full(n_elem, 1.0)
    field = orientation_field_to_tensors(5.0, 1.0, np.linspace(0.0, np.pi / 2, n_elem))
    r = solve_thermal(config, mesh, densities, k_scalar, sources, bcs, conductivity_tensor_field=field)
    _write(
        "anisotropic_thermal_field_heat_sink__smoke",
        {
            "benchmark": "heat_sink",
            "preset": "smoke",
            "rubric_version": "v7.0-wave-NN",
            "kind": "anisotropic_thermal_field",
            "kxx": 5.0,
            "kyy": 1.0,
            "temperatures_sha256": _sha256(np.asarray(r.temperatures)),
            "thermal_compliance": float(r.thermal_compliance),
            "max_temperature": float(r.max_temperature),
        },
    )


def gen_earclip_polygon() -> None:
    from structure_optimizer.core.stl_export import _tri_area, triangulate_with_holes

    outer = [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (4.0, 4.0), (4.0, 10.0), (0.0, 10.0)]
    hole = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]
    pts, tris = triangulate_with_holes(outer, [hole])
    area = sum(_tri_area(pts[i], pts[j], pts[k]) for i, j, k in tris)
    _write(
        "earclip_holed_polygon",
        {
            "benchmark": "L_shape_with_hole",
            "rubric_version": "v7.0-wave-SS",
            "kind": "earclip_polygon",
            "vertices_sha256": _sha256(np.asarray(pts)),
            "n_triangles": len(tris),
            "cross_section_area": float(area),
        },
    )


def main() -> None:
    gen_tl_adjoint()
    gen_nataf_form()
    gen_dynamic_compliance()
    gen_anisotropic_thermal_field()
    gen_earclip_polygon()
    print("v7 fingerprints generated.")


if __name__ == "__main__":
    main()
