"""Generate the v10 constraint-rich / manufacturable multi-physics fingerprints
(Wave RRR closure).

Runs five deterministic v10 drivers once and writes ``tests/fingerprints/*.json``
fixtures with the same schema as the v5–v9 fingerprints (``rubric_version`` +
``kind`` + a physics SHA + human-readable scalars). The matching re-run recipes
live in ``tests/test_multiphysics_fingerprints.py::_rerun``.

Five deterministic drivers (no RNG-sensitive output): multi-constraint MMA (KKK),
target-band placement (LLL), Archimedean-copula Rosenblatt (NNN), simultaneous
(ρ,θ) MMA (OOO), smooth-watertight annulus prism (QQQ).

Usage:  python scripts/generate_v10_fingerprints.py
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh

REPO_ROOT = Path(__file__).resolve().parent.parent
FINGERPRINT_DIR = REPO_ROOT / "tests" / "fingerprints"

COPULA_MARGINALS = [("normal", 10.0, 2.0), ("lognormal", 0.5, 0.3)]
COPULA_THETA = 4.0
COPULA_X = [11.5, 1.9]
BAND_FACTORS = (0.85, 1.15)
BAND_N = 7


def _sha256(arr: np.ndarray) -> str:
    return "sha256:" + hashlib.sha256(np.ascontiguousarray(arr, dtype="<f8").tobytes()).hexdigest()


def _write(name: str, rec: dict) -> None:
    path = FINGERPRINT_DIR / f"{name}.json"
    path.write_text(json.dumps(rec, indent=2) + "\n")
    print(f"wrote {path.relative_to(REPO_ROOT)}")


def gen_multi_constraint() -> None:
    from structure_optimizer.core.nonlinear_simp import multi_constraint_mma

    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    r = multi_constraint_mma(config, mesh, sigma_limit=5.0e3, p=8.0, max_iter=6)
    _write(
        "multi_constraint_cantilever__smoke",
        {
            "benchmark": "cantilever",
            "preset": "smoke",
            "rubric_version": "v10.0-wave-KKK",
            "kind": "multi_constraint",
            "sigma_limit": 5.0e3,
            "p": 8.0,
            "max_iter": 6,
            "densities_sha256": _sha256(np.asarray(r.densities)),
            "compliance_final": float(r.compliance_history[-1]),
            "stress_final": float(r.stress_history[-1]),
        },
    )


def gen_target_band() -> None:
    from structure_optimizer.core.freq_response import target_band_placement
    from structure_optimizer.core.modal import solve_modal

    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    rho0 = np.where(mesh.void_mask, config.optimization.min_density, config.optimization.volume_fraction)
    w1 = float(np.sqrt(solve_modal(config, mesh, rho0, n_modes=1).omega_squared[0]))
    band = np.linspace(BAND_FACTORS[0] * w1, BAND_FACTORS[1] * w1, BAND_N)
    r = target_band_placement(config, mesh, band, beta=1e-4, n_steps=6, p=12.0)
    _write(
        "target_band_cantilever__smoke",
        {
            "benchmark": "cantilever",
            "preset": "smoke",
            "rubric_version": "v10.0-wave-LLL",
            "kind": "target_band",
            "w1": w1,
            "band_factors": list(BAND_FACTORS),
            "band_n": BAND_N,
            "n_steps": 6,
            "p": 12.0,
            "densities_sha256": _sha256(np.asarray(r.densities)),
            "peak_final": float(r.peak_final),
        },
    )


def gen_copula_rosenblatt() -> None:
    from structure_optimizer.core.reliability import Marginal, build_copula_rosenblatt, clayton_copula

    marginals = [Marginal(k, a, b) for k, a, b in COPULA_MARGINALS]
    rb = build_copula_rosenblatt(marginals, clayton_copula(COPULA_THETA))
    u = rb.x_to_u(np.asarray(COPULA_X))
    _write(
        "copula_rosenblatt_clayton",
        {
            "benchmark": "clayton_bivariate",
            "rubric_version": "v10.0-wave-NNN",
            "kind": "copula_rosenblatt",
            "marginals": COPULA_MARGINALS,
            "theta": COPULA_THETA,
            "x": COPULA_X,
            "u_sha256": _sha256(np.asarray(u)),
            "u0": float(u[0]),
        },
    )


def gen_simultaneous_coupled() -> None:
    from structure_optimizer.core.thermal_simp import (
        load_thermal_benchmark,
        simultaneous_density_orientation_mma,
    )

    config, _k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    r = simultaneous_density_orientation_mma(config, mesh, 5.0, 1.0, max_iter=6, heat_sources=sources, thermal_bcs=bcs)
    _write(
        "simultaneous_coupled_heat_sink__smoke",
        {
            "benchmark": "heat_sink",
            "preset": "smoke",
            "rubric_version": "v10.0-wave-OOO",
            "kind": "simultaneous_coupled",
            "kxx": 5.0,
            "kyy": 1.0,
            "max_iter": 6,
            "densities_sha256": _sha256(np.asarray(r.densities)),
            "compliance_final": float(r.compliance_history[-1]),
        },
    )


def _ring_field(n: int = 64):
    xs = np.linspace(0.0, 1.0, n)
    ys = np.linspace(0.0, 1.0, n)
    gx, gy = np.meshgrid(xs, ys, indexing="xy")
    r = np.sqrt((gx - 0.5) ** 2 + (gy - 0.5) ** 2)
    field = ((r >= 0.25) & (r <= 0.45)).astype(float)
    return field, xs, ys


def gen_smooth_watertight() -> None:
    from structure_optimizer.core.stl_export import write_stl_smooth_watertight_holes

    field, xs, ys = _ring_field()
    info = write_stl_smooth_watertight_holes(field, xs, ys, tempfile.mktemp(suffix=".stl"), n_samples=96)
    _write(
        "smooth_watertight_ring",
        {
            "benchmark": "ring_64",
            "preset": "smoke",
            "rubric_version": "v10.0-wave-QQQ",
            "kind": "smooth_watertight",
            "n_samples": 96,
            "field_sha256": _sha256(field),
            "n_triangles": int(info["n_triangles"]),
            "cross_section_area": float(info["cross_section_area"]),
            "is_watertight": bool(info["is_watertight"]),
        },
    )


def main() -> None:
    gen_multi_constraint()
    gen_target_band()
    gen_copula_rosenblatt()
    gen_simultaneous_coupled()
    gen_smooth_watertight()
    print("v10 fingerprints generated.")


if __name__ == "__main__":
    main()
