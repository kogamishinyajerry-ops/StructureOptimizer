"""v15 embedded-constraints & rigorous-closure demos (Wave HHHHHHH closure, D113).

Real, deterministic demonstrations of the v15 capability waves — each runs the actual
production function (constraint embedded in the optimiser / writer / estimator) and writes
a small HTML summary. Mirrors ``scripts/v14_demos.py``. No network, numpy-only mandatory
runtime.

Usage:  python scripts/v15_demos.py [out_dir]
"""

from __future__ import annotations

import tempfile
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


def balanced_stacking_demo(out_path: str | Path) -> dict:
    """D106: balanced=True embeds the ±θ balance into optimize_stacking_sequence — the
    optimised stack zeros A₁₆=A₂₆; balanced=False on the same input does not."""
    from structure_optimizer.core.orthotropic_simp import (
        laminate_abd,
        optimize_stacking_sequence,
        orthotropic_plane_stress_matrix,
    )

    d0 = orthotropic_plane_stress_matrix(140e3, 10e3, 0.3, 5e3)
    inv = np.deg2rad([0.0, 30.0, -30.0, 45.0])
    bal = optimize_stacking_sequence(d0, inv, 0.125, objective="max_bending", balanced=True)
    unb = optimize_stacking_sequence(d0, inv, 0.125, objective="max_bending", balanced=False)
    a_b, _, _ = laminate_abd(d0, bal.sequence, np.full(len(bal.sequence), 0.125))
    a_u, _, _ = laminate_abd(d0, unb.sequence, np.full(len(unb.sequence), 0.125))
    return _write(
        Path(out_path), "D106 balanced-embedded stacking optimiser",
        {"balanced A16": f"{a_b[0, 2]:.3e}", "balanced A26": f"{a_b[1, 2]:.3e}",
         "unbalanced A16 (≠0)": f"{a_u[0, 2]:.3e}", "balanced D_11": f"{bal.objective_value:.4f}"},
    )


def constrained_select_demo(out_path: str | Path) -> dict:
    """D108: balanced=True constrains discrete angle selection so the optimum is
    non-degenerate (≥2 distinct angles + A₁₆=A₂₆=0), removing D102's all-one-angle."""
    from structure_optimizer.core.orthotropic_simp import (
        laminate_abd,
        orthotropic_plane_stress_matrix,
        select_ply_angles,
    )

    d0 = orthotropic_plane_stress_matrix(140e3, 10e3, 0.3, 5e3)
    cand = np.deg2rad([0.0, 30.0, 45.0, 60.0])
    res = select_ply_angles(d0, cand, 4, thickness=0.125, objective="max_bending", balanced=True)
    a, _, _ = laminate_abd(d0, res.sequence, np.full(len(res.sequence), 0.125))
    return _write(
        Path(out_path), "D108 constrained discrete angle selection",
        {"selected_deg": [round(float(np.degrees(s)), 1) for s in res.sequence],
         "distinct angles": len(set(np.round(np.degrees(res.sequence), 1))),
         "A16": f"{a[0, 2]:.3e}", "D_11": f"{res.objective_value:.4f}"},
    )


def anti_symmetric_demo(out_path: str | Path) -> dict:
    """D110: an anti-symmetric stack zeros bending–shear D₁₆=D₂₆ (and A₁₆=A₂₆), at the
    cost of B₁₆≠0 — which a symmetric-balanced stack cannot do (it keeps D₁₆≠0)."""
    from structure_optimizer.core.orthotropic_simp import (
        laminate_abd,
        make_antisymmetric_laminate,
        make_balanced_laminate,
        orthotropic_plane_stress_matrix,
    )

    d0 = orthotropic_plane_stress_matrix(140e3, 10e3, 0.3, 5e3)
    anti = make_antisymmetric_laminate(np.deg2rad([30.0, 60.0]))
    _, b_a, d_a = laminate_abd(d0, anti, np.full(len(anti), 0.125))
    sym = make_balanced_laminate(np.deg2rad([30.0, 60.0]), symmetric=True)
    _, _, d_s = laminate_abd(d0, sym, np.full(len(sym), 0.125))
    return _write(
        Path(out_path), "D110 anti-symmetric bending-shear decoupling",
        {"anti-sym D16": f"{d_a[0, 2]:.3e}", "anti-sym D26": f"{d_a[1, 2]:.3e}",
         "anti-sym B16 (trade ≠0)": f"{b_a[0, 2]:.3e}",
         "symmetric-balanced D16 (≠0)": f"{d_s[0, 2]:.3e}"},
    )


def concentric_export_demo(out_path: str | Path) -> dict:
    """D107: concentric_shells=True wires acute-corner handling into write_stl_cdt_multi_hole
    so an acute cross-section refines to a watertight cap; plain refine fails."""
    from structure_optimizer.core.fem2d import SolverError
    from structure_optimizer.core.stl_export import write_stl_cdt_multi_hole, write_stl_concentric_export

    spike = [[0.0, 0.0], [30.0, 0.0], [30.0, 10.0], [0.0, 10.0], [-120.0, 5.0]]  # ~4.8° apex
    with tempfile.TemporaryDirectory() as dtmp:
        r = write_stl_concentric_export(spike, out_path=Path(dtmp) / "c.stl")
        plain_failed = False
        try:
            write_stl_cdt_multi_hole(spike, out_path=Path(dtmp) / "p.stl", refine=True,
                                     concentric_shells=False, min_angle_deg=20.0)
        except SolverError:
            plain_failed = True
    return _write(
        Path(out_path), "D107 concentric-export acute cross-section",
        {"concentric watertight": r["is_watertight"], "n_triangles": r["n_triangles"],
         "cross_section_area": f"{r['cross_section_area']:.4f}", "plain refine fails": plain_failed},
    )


def multi_apex_demo(out_path: str | Path) -> dict:
    """D107/D112: a cross-section with MULTIPLE separate acute apexes (left+right spikes)
    already refines to a watertight cap under concentric shells; plain refine fails."""
    from structure_optimizer.core.fem2d import SolverError
    from structure_optimizer.core.stl_export import (
        _small_angle_apexes,
        write_stl_cdt_multi_hole,
        write_stl_concentric_export,
    )

    two_spike = [[0.0, 0.0], [30.0, 0.0], [150.0, 5.0], [30.0, 10.0], [0.0, 10.0], [-120.0, 5.0]]
    n = len(two_spike)
    cons = {tuple(sorted((i, (i + 1) % n))) for i in range(n)}
    apexes = _small_angle_apexes([np.asarray(p, float) for p in two_spike], cons, np.radians(60.0))
    with tempfile.TemporaryDirectory() as dtmp:
        r = write_stl_concentric_export(two_spike, out_path=Path(dtmp) / "m.stl")
        plain_failed = False
        try:
            write_stl_cdt_multi_hole(two_spike, out_path=Path(dtmp) / "p.stl", refine=True,
                                     concentric_shells=False, min_angle_deg=20.0)
        except SolverError:
            plain_failed = True
    return _write(
        Path(out_path), "D112 multi-apex (multiple separate spikes) handled by D107",
        {"n_acute_apexes": len(apexes), "concentric watertight": r["is_watertight"],
         "n_triangles": r["n_triangles"], "plain refine fails": plain_failed},
    )


def multi_family_demo(out_path: str | Path) -> dict:
    """D111: a multi-family mixture copula (Gumbel upper-tail + Clayton lower-tail) gives a
    series P_f that is the exact convex combination of the two pure-family P_f's."""
    from structure_optimizer.core.reliability import (
        clayton_d_copula,
        gumbel_d_copula,
        multi_family_copula,
        system_reliability_series_copula,
    )

    betas = np.array([2.0, 2.5, 3.0, 1.8])
    gum, cla, w = gumbel_d_copula(4, 3.0), clayton_d_copula(4, 2.0), 0.65
    pf_g = system_reliability_series_copula(betas, gum)
    pf_c = system_reliability_series_copula(betas, cla)
    pf_m = system_reliability_series_copula(betas, multi_family_copula([gum, cla], [w, 1 - w]))
    return _write(
        Path(out_path), "D111 multi-family mixture copula reliability",
        {"P_f Gumbel (upper-tail)": f"{pf_g:.6e}", "P_f Clayton (lower-tail)": f"{pf_c:.6e}",
         "P_f mixture (w=0.65)": f"{pf_m:.6e}",
         "convex-combo check": f"{w * pf_g + (1 - w) * pf_c:.6e}"},
    )


def deterministic_qmc_demo(out_path: str | Path) -> dict:
    """D112: a CBC-constructed rank-1 lattice gives a deterministic (seed-free) worst-case
    error certificate strictly not worse than the textbook Korobov vector's."""
    from structure_optimizer.core.reliability import (
        _korobov_generating_vector,
        cbc_korobov_generating_vector,
        korobov_worst_case_error,
    )

    gamma, n = [0.7, 0.5, 0.3], 89
    z_cbc = cbc_korobov_generating_vector(3, n, gamma)
    z_kor = _korobov_generating_vector(3, 33, n)
    return _write(
        Path(out_path), "D112 deterministic CBC-lattice worst-case error",
        {"N (prime)": n, "CBC z": np.asarray(z_cbc).tolist(),
         "e(z_CBC)": f"{korobov_worst_case_error(z_cbc, n, gamma):.6e}",
         "e(z_Korobov)": f"{korobov_worst_case_error(z_kor, n, gamma):.6e}"},
    )


def kkt_peak_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """D109: at a tight flanking-peak limit (≲0.1·init) the constraint is strictly
    KKT-active (g₁≈0) and J(ω_op) is sacrificed (positive multiplier) — closing D104."""
    from structure_optimizer.core.freq_response import (
        _dynamic_compliance_objective,
        kkt_binding_status,
        peak_binding_mma,
    )
    from structure_optimizer.core.modal import solve_modal

    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    opt = config.optimization
    rho0 = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
    w = np.sqrt(solve_modal(config, mesh, rho0, n_modes=3).omega_squared)
    w_op = 0.5 * (w[0] + w[1])
    flo, fhi = 0.85 * w[1], 1.15 * w[1]
    init = max(_dynamic_compliance_objective(config, mesh, rho0, ww, beta=2e-6) for ww in np.linspace(flo, fhi, 120))
    j_unc = peak_binding_mma(config, mesh, w_op, flo, fhi, peak_limit=1e9 * init, beta=2e-6, max_iter=20).dyn_compliance_history[-1]
    tight = peak_binding_mma(config, mesh, w_op, flo, fhi, peak_limit=0.08 * init, beta=2e-6, max_iter=20)
    s = kkt_binding_status(config, mesh, tight, beta=2e-6, j_reference=j_unc)
    return _write(
        Path(out_path), "D109 strictly KKT-binding peak-binding (tight limit)",
        {"peak_limit": "0.08·init", "constraint g₁ (≈0 active)": f"{s.constraint_value:.4f}",
         "active": s.active, "active_multiplier (J sacrificed >0)": f"{s.active_multiplier:.4f}"},
    )


def main(out_dir: str | Path = "build/v15_demos") -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    balanced_stacking_demo(out / "d106_balanced_stacking.html")
    constrained_select_demo(out / "d108_constrained_select.html")
    anti_symmetric_demo(out / "d110_anti_symmetric.html")
    concentric_export_demo(out / "d107_concentric_export.html")
    multi_apex_demo(out / "d112_multi_apex.html")
    multi_family_demo(out / "d111_multi_family.html")
    deterministic_qmc_demo(out / "d112_deterministic_qmc.html")
    kkt_peak_demo(out / "d109_kkt_peak.html")
    print(f"wrote v15 demos to {out}")


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else "build/v15_demos")
