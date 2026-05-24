"""Generate the v11 exact-&-robust multi-physics fingerprints (Wave ZZZ closure).

Runs five deterministic v11 drivers once and writes ``tests/fingerprints/*.json``
fixtures with the same schema as the v5–v10 fingerprints (``rubric_version`` +
``kind`` + a physics SHA + human-readable scalars). The matching re-run recipes
live in ``tests/test_multiphysics_fingerprints.py::_rerun``.

Five deterministic drivers: qp-relaxed stress sensitivity (SSS/D074), adaptive
band sampling (TTT/D075), reference-free R2 + HV indicators (UUU/D076), d-dim
Clayton Rosenblatt (VVV/D077), Genz exact series P_f (WWW/D078 — seeded MC, so
bit-reproducible on the canonical CI cell, tolerant elsewhere).

Usage:  python scripts/generate_v11_fingerprints.py
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


def _sha256(arr: np.ndarray) -> str:
    return "sha256:" + hashlib.sha256(np.ascontiguousarray(arr, dtype="<f8").tobytes()).hexdigest()


def _write(name: str, rec: dict) -> None:
    (FINGERPRINT_DIR / name).write_text(json.dumps(rec, indent=2))
    print(f"wrote {name}")


def gen_qp_relaxed_stress() -> None:
    from structure_optimizer.core.simp import run_simp
    from structure_optimizer.core.stress import qp_relaxed_stress_pnorm_sensitivity

    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    rho = run_simp(config, mesh).densities
    sigma_pn, dsdrho = qp_relaxed_stress_pnorm_sensitivity(config, mesh, rho, p=8.0, q=2.5)
    _write(
        "qp_relaxed_stress_cantilever__smoke.json",
        {
            "benchmark": "cantilever",
            "preset": "smoke",
            "rubric_version": "v11.0-wave-SSS",
            "kind": "qp_relaxed_stress",
            "p": 8.0,
            "q": 2.5,
            "sigma_pn": float(sigma_pn),
            "dsdrho_sha256": _sha256(dsdrho),
        },
    )


def gen_adaptive_band() -> None:
    from structure_optimizer.core.freq_response import adaptive_band_sample
    from structure_optimizer.core.modal import solve_modal

    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    opt = config.optimization
    rho = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    w1 = float(np.sqrt(solve_modal(config, mesh, rho, n_modes=1).omega_squared[0]))
    ab = adaptive_band_sample(config, mesh, rho, 0.80 * w1, 1.30 * w1, n_init=7, n_refine=18, beta=2e-6)
    _write(
        "adaptive_band_cantilever__smoke.json",
        {
            "benchmark": "cantilever",
            "preset": "smoke",
            "rubric_version": "v11.0-wave-TTT",
            "kind": "adaptive_band",
            "band_factors": [0.80, 1.30],
            "n_init": 7,
            "n_refine": 18,
            "beta": 2e-6,
            "peak_value": float(ab.peak_value),
            "peak_omega": float(ab.peak_omega),
            "omegas_sha256": _sha256(ab.omegas),
        },
    )


def gen_r2_indicator() -> None:
    from structure_optimizer.core.multi_objective_to import r2_indicator, reference_free_hypervolume

    front = np.array([[3.0, 1.0], [2.0, 2.0], [1.0, 3.0]])
    r2 = r2_indicator(front, ideal=np.array([0.0, 0.0]))
    hv = reference_free_hypervolume(front, margin=0.1)
    out = np.array([r2, hv])
    _write(
        "reference_free_indicators.json",
        {
            "benchmark": "r2_three_point_front",
            "rubric_version": "v11.0-wave-UUU",
            "kind": "r2_indicator",
            "front": front.tolist(),
            "ideal": [0.0, 0.0],
            "margin": 0.1,
            "r2": float(r2),
            "reference_free_hv": float(hv),
            "values_sha256": _sha256(out),
        },
    )


def gen_clayton_d_rosenblatt() -> None:
    from structure_optimizer.core.reliability import Marginal, build_clayton_rosenblatt

    marginals = [("normal", 10.0, 2.0), ("lognormal", 0.5, 0.3), ("normal", -1.0, 0.5)]
    theta = 1.7
    x = [11.5, 1.9, -0.7]
    tr = build_clayton_rosenblatt([Marginal(k, a, b) for k, a, b in marginals], theta=theta)
    u = tr.x_to_u(np.asarray(x))
    _write(
        "clayton_d_rosenblatt_trivariate.json",
        {
            "benchmark": "clayton_trivariate",
            "rubric_version": "v11.0-wave-VVV",
            "kind": "clayton_d_rosenblatt",
            "marginals": marginals,
            "theta": theta,
            "x": x,
            "u0": float(u[0]),
            "u_sha256": _sha256(u),
        },
    )


def gen_genz_mvn() -> None:
    from structure_optimizer.core.reliability import system_reliability_series_exact

    betas = [2.5, 2.0, 3.0, 2.2]
    rng = np.random.default_rng(1)
    alpha = rng.standard_normal((4, 3))
    alpha /= np.linalg.norm(alpha, axis=1, keepdims=True)
    r = alpha @ alpha.T
    np.fill_diagonal(r, 1.0)
    r = 0.98 * r + 0.02 * np.eye(4)
    pf = system_reliability_series_exact(np.asarray(betas), r, n_samples=20000, seed=0)
    _write(
        "genz_system_reliability.json",
        {
            "benchmark": "genz_series_4mode",
            "rubric_version": "v11.0-wave-WWW",
            "kind": "genz_mvn",
            "betas": betas,
            "correlation": r.tolist(),
            "n_samples": 20000,
            "seed": 0,
            "p_failure": float(pf),
            "pf_sha256": _sha256(np.array([pf])),
        },
    )


if __name__ == "__main__":
    FINGERPRINT_DIR.mkdir(parents=True, exist_ok=True)
    gen_qp_relaxed_stress()
    gen_adaptive_band()
    gen_r2_indicator()
    gen_clayton_d_rosenblatt()
    gen_genz_mvn()
    print("v11 fingerprints generated.")
