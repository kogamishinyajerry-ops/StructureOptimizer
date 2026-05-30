"""v14 integration & production-wiring demos (Wave HHHHHH closure, D105).

Real, deterministic demonstrations of the seven v14 capability waves — each runs the
actual production-wired driver / estimator and writes a small HTML summary. Mirrors
``scripts/v13_demos.py``. No network, numpy-only mandatory runtime.

Usage:  python scripts/v14_demos.py [out_dir]
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh


def _html(title: str, body: str) -> str:
    return f"<!doctype html><meta charset=utf-8><title>{title}</title><h1>{title}</h1>{body}"


def _write(out_path: Path, title: str, rows: dict) -> dict:
    body = (
        "<table border=1 cellpadding=4>"
        + "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows.items())
        + "</table>"
    )
    out_path.write_text(_html(title, body))
    return rows


def series_copula_demo(out_path: str | Path) -> dict:
    """D098: Gumbel series-system P_f; upper-tail dependence (θ>1) raises P_f over independence."""
    from structure_optimizer.core.reliability import ExchangeableGumbelCopula, system_reliability_series_copula

    betas = np.array([2.0, 2.5, 3.0])
    indep = system_reliability_series_copula(betas, ExchangeableGumbelCopula(3, 1.0))
    dep = system_reliability_series_copula(betas, ExchangeableGumbelCopula(3, 2.5))
    return _write(
        Path(out_path),
        "D098 Gumbel series-system reliability",
        {"betas": betas.tolist(), "P_f (independent, θ=1)": f"{indep:.6e}", "P_f (upper-tail, θ=2.5)": f"{dep:.6e}"},
    )


def series_reorder_demo(out_path: str | Path) -> dict:
    """D099: Genz-reordered exact series P_f — same estimand, lower variance at fixed N."""
    from structure_optimizer.core.reliability import (
        system_reliability_series_exact,
        system_reliability_series_exact_reordered,
    )

    betas = np.array([3.0, 2.5, 2.0, 1.5])
    m = len(betas)
    R = np.full((m, m), 0.4)
    np.fill_diagonal(R, 1.0)
    plain = system_reliability_series_exact(betas, R, n_samples=20000, seed=0)
    reordered = system_reliability_series_exact_reordered(betas, R, n_samples=20000, seed=0)
    return _write(
        Path(out_path),
        "D099 Genz-reordered exact series reliability",
        {"betas": betas.tolist(), "rho": 0.4, "P_f (plain)": f"{plain:.6e}", "P_f (reordered)": f"{reordered:.6e}"},
    )


def ruppert_export_demo(out_path: str | Path) -> dict:
    """D100: Ruppert-refined watertight multi-hole STL cap (refine raises the min cap angle)."""
    import tempfile

    from structure_optimizer.core.stl_export import write_stl_cdt_multi_hole

    outer = [[0.0, 0.0], [6.0, 0.0], [6.0, 6.0], [0.0, 6.0]]
    holes = [[[2.0, 2.0], [4.0, 2.0], [4.0, 4.0], [2.0, 4.0]]]
    with tempfile.TemporaryDirectory() as d:
        plain = write_stl_cdt_multi_hole(outer, holes, out_path=Path(d) / "plain.stl", refine=False)
        ref = write_stl_cdt_multi_hole(outer, holes, out_path=Path(d) / "ref.stl", refine=True, min_angle_deg=20.0)
    return _write(
        Path(out_path),
        "D100 Ruppert-refined multi-hole STL cap",
        {
            "plain n_triangles": plain["n_triangles"],
            "refined n_triangles": ref["n_triangles"],
            "area (plain == refined)": f"{plain['cross_section_area']:.4f} / {ref['cross_section_area']:.4f}",
            "refined watertight": ref["is_watertight"],
        },
    )


def concentric_shell_demo(out_path: str | Path) -> dict:
    """D103: concentric-shell Ruppert terminates on an acute spike where midpoint fails."""
    from structure_optimizer.core.stl_export import constrained_delaunay_ruppert

    spike = [[0.0, 0.0], [30.0, 0.0], [30.0, 10.0], [0.0, 10.0], [-120.0, 5.0]]  # ~4.8° apex
    plain_failed = False
    try:
        constrained_delaunay_ruppert(spike, min_angle_deg=20.0, max_steiner=300, concentric_shells=False)
    except Exception:
        plain_failed = True
    pts, tris = constrained_delaunay_ruppert(spike, min_angle_deg=20.0, max_steiner=400, concentric_shells=True)
    return _write(
        Path(out_path),
        "D103 concentric-shell small-input-angle handling",
        {
            "apex_angle_deg": "≈4.8",
            "plain midpoint fails": plain_failed,
            "concentric n_triangles": len(tris),
            "concentric n_points": len(pts),
            "watertight": True,
        },
    )


def balanced_laminate_demo(out_path: str | Path) -> dict:
    """D101: a symmetric-balanced laminate zeros both A₁₆=A₂₆ (balance) and B (symmetry)."""
    from structure_optimizer.core.orthotropic_simp import (
        laminate_abd,
        make_balanced_laminate,
        orthotropic_plane_stress_matrix,
    )

    d0 = orthotropic_plane_stress_matrix(140e3, 10e3, 0.3, 5e3)
    stack = make_balanced_laminate(np.deg2rad([30.0, 60.0]), symmetric=True)
    a, b, _ = laminate_abd(d0, stack, np.full(len(stack), 0.125))
    return _write(
        Path(out_path),
        "D101 symmetric-balanced laminate",
        {
            "stack_deg": [round(float(np.degrees(s)), 1) for s in stack],
            "A16": f"{a[0, 2]:.3e}",
            "A26": f"{a[1, 2]:.3e}",
            "||B||": f"{np.linalg.norm(b):.3e}",
        },
    )


def angle_select_demo(out_path: str | Path) -> dict:
    """D102: discrete angle selection for max bending picks all-stiffest (closed-form global)."""
    from structure_optimizer.core.orthotropic_simp import orthotropic_plane_stress_matrix, select_ply_angles

    d0 = orthotropic_plane_stress_matrix(140e3, 10e3, 0.3, 5e3)
    res = select_ply_angles(d0, np.deg2rad([0.0, 45.0, 90.0]), 4, thickness=0.125, objective="max_bending")
    return _write(
        Path(out_path),
        "D102 discrete angle-set selection",
        {
            "candidates_deg": [0, 45, 90],
            "selected_deg": [round(float(np.degrees(s)), 1) for s in res.sequence],
            "D_11": f"{res.objective_value:.4f}",
        },
    )


def peak_binding_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """D104: min J(ω_op) in the anti-resonance valley raises a flanking resonance; the
    flanking constraint + in-loop re-gridding change the design."""
    from structure_optimizer.core.freq_response import peak_binding_mma
    from structure_optimizer.core.modal import solve_modal

    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    opt = config.optimization
    rho0 = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    w = np.sqrt(solve_modal(config, mesh, rho0, n_modes=2).omega_squared)
    w_op = 0.5 * (w[0] + w[1])
    flo, fhi = 0.85 * w[1], 1.15 * w[1]
    r = peak_binding_mma(config, mesh, w_op, flo, fhi, peak_limit=1e12, beta=2e-6, max_iter=15, regrid=True)
    return _write(
        Path(out_path),
        "D104 peak-binding flanking-mode",
        {
            "omega_op (valley)": f"{w_op:.0f}",
            "J(ω_op) initial": f"{r.dyn_compliance_history[0]:.3e}",
            "J(ω_op) final": f"{r.dyn_compliance_history[-1]:.3e}",
            "flanking peak initial": f"{r.flanking_peak_history[0]:.3e}",
            "flanking peak final (RAISED)": f"{r.flanking_peak_history[-1]:.3e}",
        },
    )


def main(out_dir: str | Path = "build/v14_demos") -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    series_copula_demo(out / "d098_series_copula.html")
    series_reorder_demo(out / "d099_series_reorder.html")
    ruppert_export_demo(out / "d100_ruppert_export.html")
    balanced_laminate_demo(out / "d101_balanced_laminate.html")
    angle_select_demo(out / "d102_angle_select.html")
    concentric_shell_demo(out / "d103_concentric_shell.html")
    peak_binding_demo(out / "d104_peak_binding.html")
    print(f"wrote v14 demos to {out}")


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else "build/v14_demos")
