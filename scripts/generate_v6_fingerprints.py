"""Generate the v6 production-grade multi-physics fingerprints (Wave LL).

Runs each v6 solver once and writes a ``tests/fingerprints/*.json`` fixture with
the same schema as the v5 multi-physics fingerprints (``rubric_version`` + a
``kind`` + a physics SHA + human-readable scalars). The matching re-run recipes
live in ``tests/test_multiphysics_fingerprints.py::_rerun`` — running this
generator then that test confirms the pair is consistent.

The v5 multi-physics fingerprints never had a generator ("a follow-up", per that
test's docstring); this closes that gap for the v6 set.

Usage:  python scripts/generate_v6_fingerprints.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.stl_export import marching_squares_contours, polygon_area

REPO_ROOT = Path(__file__).resolve().parent.parent
FINGERPRINT_DIR = REPO_ROOT / "tests" / "fingerprints"


def _sha256(arr: np.ndarray) -> str:
    """float64 little-endian byte hash — same convention as the other generators."""
    return "sha256:" + hashlib.sha256(np.ascontiguousarray(arr, dtype="<f8").tobytes()).hexdigest()


def _linear_limit_state(u) -> float:
    u = np.asarray(u, dtype=float)
    return float(10.0 - (3.0 * u[0] + 4.0 * u[1]))


def _disk_field(n: int, r: float, cx: float = 0.5, cy: float = 0.5):
    xs = np.linspace(0.0, 1.0, n)
    ys = np.linspace(0.0, 1.0, n)
    gx, gy = np.meshgrid(xs, ys)
    return r * r - ((gx - cx) ** 2 + (gy - cy) ** 2), xs, ys


def _write(name: str, rec: dict) -> None:
    path = FINGERPRINT_DIR / f"{name}.json"
    path.write_text(json.dumps(rec, indent=2) + "\n")
    print(f"wrote {path.relative_to(REPO_ROOT)}")


def gen_total_lagrangian() -> None:
    from structure_optimizer.core.total_lagrangian import solve_total_lagrangian

    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 1.0)
    r = solve_total_lagrangian(config, mesh, densities, n_load_steps=3)
    _write("tl_cantilever__smoke", {
        "benchmark": "cantilever", "preset": "smoke",
        "rubric_version": "v6.0-wave-EE", "kind": "total_lagrangian",
        "n_load_steps": 3,
        "displacements_sha256": _sha256(np.asarray(r.displacements)),
        "max_displacement": float(r.max_displacements[-1]),
        "n_newton_iters": int(r.n_newton_iters),
        "converged": bool(r.converged),
        "load_steps": [float(x) for x in r.load_steps],
        "max_disp_per_step": [float(x) for x in r.max_displacements],
    })


def gen_damped_fr() -> None:
    from structure_optimizer.core.freq_response import solve_damped_frequency_response

    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 1.0)
    r = solve_damped_frequency_response(config, mesh, densities, omega=8.0, alpha=0.5, beta=1e-4)
    _write("damped_fr_cantilever__smoke", {
        "benchmark": "cantilever", "preset": "smoke",
        "rubric_version": "v6.0-wave-FF", "kind": "damped_frequency_response",
        "omega": 8.0, "alpha": 0.5, "beta": 1e-4,
        "magnitude_sha256": _sha256(np.asarray(r.magnitude)),
        "max_magnitude": float(r.max_magnitude),
        "response_norm": float(r.response_norm),
    })


def gen_anisotropic_thermal() -> None:
    from structure_optimizer.core.thermal import conductivity_tensor, solve_thermal
    from structure_optimizer.core.thermal_simp import load_thermal_benchmark

    config, k_scalar, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    mesh = create_structured_mesh(config)
    densities = np.full(mesh.elements.shape[0], 1.0)
    ktensor = conductivity_tensor(5.0, 1.0, 0.3)
    r = solve_thermal(config, mesh, densities, k_scalar, sources, bcs, conductivity_tensor=ktensor)
    _write("anisotropic_thermal_heat_sink__smoke", {
        "benchmark": "heat_sink", "preset": "smoke",
        "rubric_version": "v6.0-wave-GG", "kind": "anisotropic_thermal",
        "kxx": 5.0, "kyy": 1.0, "kxy": 0.3,
        "temperatures_sha256": _sha256(np.asarray(r.temperatures)),
        "thermal_compliance": float(r.thermal_compliance),
        "max_temperature": float(r.max_temperature),
    })


def gen_form() -> None:
    from structure_optimizer.core.reliability import form_hlrf

    r = form_hlrf(_linear_limit_state, n_vars=2)
    _write("form_linear_limit_state", {
        "benchmark": "linear_limit_state",
        "rubric_version": "v6.0-wave-II", "kind": "form_reliability",
        "n_vars": 2,
        "mpp_sha256": _sha256(np.asarray(r.mpp)),
        "beta": float(r.beta),
        "p_failure": float(r.p_failure),
        "converged": bool(r.converged),
    })


def gen_marching_squares() -> None:
    field, xs, ys = _disk_field(65, 0.3)
    loops = [lp for lp in marching_squares_contours(field, xs, ys, level=0.0) if polygon_area(lp) > 1e-12]
    total_area = sum(polygon_area(lp) for lp in loops)
    pts = np.vstack([np.asarray(lp, dtype=float) for lp in loops]) if loops else np.zeros((0, 2))
    _write("marching_squares_disk", {
        "benchmark": "disk_field",
        "rubric_version": "v6.0-wave-JJ", "kind": "marching_squares",
        "grid_n": 65, "radius": 0.3,
        "contour_sha256": _sha256(pts),
        "total_area": float(total_area),
        "n_loops": len(loops),
    })


def main() -> None:
    gen_total_lagrangian()
    gen_damped_fr()
    gen_anisotropic_thermal()
    gen_form()
    gen_marching_squares()
    print("v6 fingerprints generated.")


if __name__ == "__main__":
    main()
