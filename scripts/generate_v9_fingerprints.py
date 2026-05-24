"""Generate the v9 second-order-driver multi-physics fingerprints (Wave JJJ).

Runs each v9 driver once and writes a ``tests/fingerprints/*.json`` fixture with
the same schema as the v5-v8 multi-physics fingerprints (``rubric_version`` + a
``kind`` + a physics SHA + human-readable scalars). The matching re-run recipes
live in ``tests/test_multiphysics_fingerprints.py::_rerun``.

Five deterministic drivers (no RNG-sensitive front shapes): MMA-TL nonlinear TO
(CCC), band-gap sensitivity (DDD), Rosenblatt transform (FFF), coupled
density+orientation thermal TO (GGG), slit-free annulus prism (III).

Usage:  python scripts/generate_v9_fingerprints.py
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

ROSEN_MEAN = [2.0, -1.0, 0.5]
ROSEN_COV = [[1.0, 0.3, -0.2], [0.3, 1.5, 0.1], [-0.2, 0.1, 0.8]]
ROSEN_X = [3.1, 0.2, 1.0]


def _sha256(arr: np.ndarray) -> str:
    return "sha256:" + hashlib.sha256(np.ascontiguousarray(arr, dtype="<f8").tobytes()).hexdigest()


def _write(name: str, rec: dict) -> None:
    path = FINGERPRINT_DIR / f"{name}.json"
    path.write_text(json.dumps(rec, indent=2) + "\n")
    print(f"wrote {path.relative_to(REPO_ROOT)}")


def _annulus_40():
    config = load_benchmark("cantilever", preset="smoke")
    from dataclasses import replace
    config = replace(config, mesh=replace(config.mesh, nelx=40, nely=40, width=40.0, height=40.0))
    mesh = create_structured_mesh(config)
    rho = np.zeros(mesh.nelx * mesh.nely)
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            r = np.hypot(ex + 0.5 - 20.0, ey + 0.5 - 20.0)
            rho[mesh.element_index(ex, ey)] = 1.0 if 7.0 < r < 15.0 else 0.0
    return mesh, rho


def gen_mma_nonlinear() -> None:
    from structure_optimizer.core.nonlinear_simp import mma_nonlinear_to

    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    r = mma_nonlinear_to(config, mesh, n_load_steps=3, max_iter=6)
    _write("mma_nonlinear_cantilever__smoke", {
        "benchmark": "cantilever", "preset": "smoke",
        "rubric_version": "v9.0-wave-CCC", "kind": "mma_nonlinear",
        "n_load_steps": 3, "max_iter": 6,
        "densities_sha256": _sha256(np.asarray(r.densities)),
        "compliance_final": float(r.compliance_history[-1]),
        "converged": bool(r.converged),
    })


def gen_band_gap() -> None:
    from structure_optimizer.core.freq_response import band_gap_sensitivity

    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 0.6)
    gap, dgap = band_gap_sensitivity(config, mesh, densities, lower_mode=0)
    _write("band_gap_cantilever__smoke", {
        "benchmark": "cantilever", "preset": "smoke",
        "rubric_version": "v9.0-wave-DDD", "kind": "band_gap",
        "lower_mode": 0, "density_fill": 0.6,
        "dgap_sha256": _sha256(np.asarray(dgap)),
        "gap": float(gap),
    })


def gen_rosenblatt() -> None:
    from structure_optimizer.core.reliability import build_rosenblatt_normal

    rt = build_rosenblatt_normal(np.asarray(ROSEN_MEAN), np.asarray(ROSEN_COV))
    u = rt.x_to_u(np.asarray(ROSEN_X))
    _write("rosenblatt_trivariate", {
        "benchmark": "trivariate_normal",
        "rubric_version": "v9.0-wave-FFF", "kind": "rosenblatt",
        "mean": ROSEN_MEAN, "cov": ROSEN_COV, "x": ROSEN_X,
        "u_sha256": _sha256(np.asarray(u)),
        "u0": float(u[0]),
    })


def gen_coupled_thermal() -> None:
    from structure_optimizer.core.thermal_simp import coupled_density_orientation_to, load_thermal_benchmark

    config, _k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    r = coupled_density_orientation_to(config, mesh, 5.0, 1.0, n_outer=4, n_orient_steps=5,
                                       heat_sources=sources, thermal_bcs=bcs)
    _write("coupled_thermal_heat_sink__smoke", {
        "benchmark": "heat_sink", "preset": "smoke",
        "rubric_version": "v9.0-wave-GGG", "kind": "coupled_thermal",
        "kxx": 5.0, "kyy": 1.0, "n_outer": 4, "n_orient_steps": 5,
        "densities_sha256": _sha256(np.asarray(r.densities)),
        "compliance_final": float(r.compliance_history[-1]),
    })


def gen_slit_free() -> None:
    import tempfile

    from structure_optimizer.core.stl_export import write_stl_slit_free_holes

    mesh, rho = _annulus_40()
    info = write_stl_slit_free_holes(mesh, rho, tempfile.mktemp(suffix=".stl"))
    _write("slit_free_annulus", {
        "benchmark": "annulus_40", "preset": "smoke",
        "rubric_version": "v9.0-wave-III", "kind": "slit_free",
        "densities_sha256": _sha256(rho),
        "n_solid_cells": int(info["n_solid_cells"]),
        "cross_section_area": float(info["cross_section_area"]),
        "is_watertight": bool(info["is_watertight"]),
    })


def main() -> None:
    gen_mma_nonlinear()
    gen_band_gap()
    gen_rosenblatt()
    gen_coupled_thermal()
    gen_slit_free()
    print("v9 fingerprints generated.")


if __name__ == "__main__":
    main()
