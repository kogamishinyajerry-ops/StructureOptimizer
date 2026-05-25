"""v12 design-grade & adaptive demos (Wave HHHH closure).

Real, deterministic demonstrations of the seven v12 capability waves — each runs
the actual driver / estimator and writes a small HTML summary. Mirrors
``scripts/v11_demos.py``. No network, numpy-only mandatory runtime.

Usage:  python scripts/v12_demos.py [out_dir]
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh


def _html(title: str, body: str) -> str:
    return f"<!doctype html><meta charset=utf-8><title>{title}</title><h1>{title}</h1>{body}"


def _write(out_path: Path, title: str, rows: dict) -> dict:
    body = "<table border=1 cellpadding=4>" + "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows.items()
    ) + "</table>"
    out_path.write_text(_html(title, body))
    return rows


def design_grade_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """D082: design-grade buckling sensitivity raises λ_crit (vs analysis-grade)."""
    from structure_optimizer.core.buckling import maximize_buckling_load

    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    r = maximize_buckling_load(config, mesh, vf=config.optimization.volume_fraction, n_steps=30)
    return _write(
        Path(out_path), "D082 design-grade buckling",
        {"lambda_initial": f"{r.lambda_history[0]:.3f}", "lambda_final": f"{r.lambda_history[-1]:.3f}"},
    )


def inloop_band_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """D083: in-loop adaptive band re-gridding tracks the moving resonance."""
    from structure_optimizer.core.freq_response import adaptive_peak_constrained_mma
    from structure_optimizer.core.modal import solve_modal

    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    opt = config.optimization
    rho0 = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    w1 = float(np.sqrt(solve_modal(config, mesh, rho0, n_modes=1).omega_squared[0]))
    r = adaptive_peak_constrained_mma(config, mesh, 3e9, 0.6 * w1, 2.1 * w1, beta=2e-6, max_iter=10)
    return _write(
        Path(out_path), "D083 in-loop adaptive band",
        {"peak_omega_initial": f"{r.peak_omega_history[0]:.0f}", "peak_omega_final": f"{r.peak_omega_history[-1]:.0f}"},
    )


def augmented_r2_demo(out_path: str | Path) -> dict:
    """D084: augmented R2 discriminates a weakly- from a properly-efficient point."""
    from structure_optimizer.core.multi_objective_to import augmented_tchebycheff_r2, r2_indicator, spacing_indicator

    w = np.array([[0.5, 0.5]])
    z = np.zeros(2)
    weak, proper = np.array([[0.5, 0.5]]), np.array([[0.5, 0.3]])
    front = np.array([[0.0, 1.0], [0.5, 0.5], [1.0, 0.0]])
    return _write(
        Path(out_path), "D084 augmented R2 + spacing",
        {
            "plain_r2_weak": f"{r2_indicator(weak, weights=w, ideal=z):.3f}",
            "plain_r2_proper": f"{r2_indicator(proper, weights=w, ideal=z):.3f}",
            "aug_r2_weak": f"{augmented_tchebycheff_r2(weak, weights=w, ideal=z, rho=0.1):.3f}",
            "aug_r2_proper": f"{augmented_tchebycheff_r2(proper, weights=w, ideal=z, rho=0.1):.3f}",
            "spacing": f"{spacing_indicator(front):.4f}",
        },
    )


def spacing_demo(out_path: str | Path) -> dict:
    """D084 alias: Schott spacing on an even vs clustered front."""
    from structure_optimizer.core.multi_objective_to import spacing_indicator

    even = np.array([[0.0, 3.0], [1.0, 2.0], [2.0, 1.0], [3.0, 0.0]])
    clustered = np.array([[0.0, 3.0], [0.1, 2.9], [2.0, 1.0], [3.0, 0.0]])
    return _write(
        Path(out_path), "D084 spacing",
        {"even_S": f"{spacing_indicator(even):.4f}", "clustered_S": f"{spacing_indicator(clustered):.4f}"},
    )


def nested_copula_demo(out_path: str | Path) -> dict:
    """D085: nested Clayton with per-cluster Kendall τ."""
    from structure_optimizer.core.reliability import nested_clayton_copula

    c = nested_clayton_copula(4, [[0, 1], [2, 3]], 2.0, [6.0, 4.0])
    return _write(
        Path(out_path), "D085 nested Clayton copula",
        {
            "cdf": f"{c.cdf(np.array([0.4, 0.6, 0.5, 0.7])):.5f}",
            "tau_within_g0": f"{c.kendall_tau_within(0):.3f}",
            "tau_within_g1": f"{c.kendall_tau_within(1):.3f}",
            "tau_between": f"{c.kendall_tau_between():.3f}",
        },
    )


def lattice_genz_demo(out_path: str | Path) -> dict:
    """D086: Korobov-lattice Genz with a reported standard error."""
    from structure_optimizer.core.reliability import genz_mvn_cdf_lattice

    rho = 0.5
    R = (1 - rho) * np.eye(4) + rho * np.ones((4, 4))
    res = genz_mvn_cdf_lattice(np.ones(4), R, n_points=1021, n_shifts=12)
    return _write(
        Path(out_path), "D086 Korobov-lattice Genz",
        {"value": f"{res.value:.6f}", "std_error": f"{res.std_error:.2e}", "n_points": res.n_points},
    )


def laminate_demo(out_path: str | Path) -> dict:
    """D087: laminate [A,B,D] — symmetric stack decouples (B=0)."""
    from structure_optimizer.core.orthotropic_simp import laminate_abd, orthotropic_plane_stress_matrix

    d0 = orthotropic_plane_stress_matrix(130e9, 10e9, 0.28, 5e9)
    A_sym, B_sym, _ = laminate_abd(d0, np.deg2rad([45.0, -45.0, -45.0, 45.0]), np.full(4, 0.5))
    _, B_unsym, _ = laminate_abd(d0, np.deg2rad([0.0, 90.0]), np.full(2, 1.0))
    return _write(
        Path(out_path), "D087 laminate ABD",
        {"A00_symmetric": f"{A_sym[0, 0]:.3e}", "B_norm_symmetric": f"{np.abs(B_sym).max():.3e}",
         "B_norm_unsymmetric": f"{np.abs(B_unsym).max():.3e}"},
    )


def periodic_fibre_demo(out_path: str | Path) -> dict:
    """D087: period-aware sin²Δθ does not over-penalise a ±89° seam."""
    from structure_optimizer.core.orthotropic_simp import _continuity_metric, period_aware_continuity

    angles = np.deg2rad([89.0, -89.0])
    pairs = [(0, 1)]
    return _write(
        Path(out_path), "D087 period-aware fibre continuity",
        {"sin2_metric": f"{period_aware_continuity(angles, pairs)[0]:.5f}",
         "squared_metric": f"{_continuity_metric(angles, pairs)[0]:.3f}"},
    )


def cdt_refine_demo(out_path: str | Path) -> dict:
    """D088: flip recovery triangulates a non-convex star that D080 rejects."""
    from structure_optimizer.core.stl_export import _min_triangle_angle, constrained_delaunay_flip_recover

    star = np.array([
        [2.6146, 0.045], [0.3886, 0.0405], [2.1953, 0.578], [-0.096, 0.7683],
        [-2.5324, -0.7121], [-1.381, -1.0942], [-0.1425, -1.1], [0.558, -1.3289],
        [0.1514, -0.3447], [0.5424, -0.3312], [1.9375, -0.8374],
    ])
    pts, tris = constrained_delaunay_flip_recover([p for p in star], refine=True)
    return _write(
        Path(out_path), "D088 flip-recovery CDT",
        {"n_triangles": len(tris), "min_angle_deg": f"{np.rad2deg(_min_triangle_angle(pts, tris)):.2f}"},
    )


def main(out_dir: str | Path = "build/v12_demos") -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    design_grade_demo(out / "d082_buckling.html")
    inloop_band_demo(out / "d083_inloop_band.html")
    augmented_r2_demo(out / "d084_augmented_r2.html")
    spacing_demo(out / "d084_spacing.html")
    nested_copula_demo(out / "d085_nested_copula.html")
    lattice_genz_demo(out / "d086_lattice_genz.html")
    laminate_demo(out / "d087_laminate.html")
    periodic_fibre_demo(out / "d087_periodic_fibre.html")
    cdt_refine_demo(out / "d088_cdt_refine.html")
    print(f"wrote v12 demos to {out}")


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else "build/v12_demos")
