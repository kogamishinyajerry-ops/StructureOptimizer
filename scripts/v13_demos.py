"""v13 robust drivers & validated geometry demos (Wave HHHHH closure).

Real, deterministic demonstrations of the seven v13 capability waves — each runs the
actual driver / estimator and writes a small HTML summary. Mirrors
``scripts/v12_demos.py``. No network, numpy-only mandatory runtime.

Usage:  python scripts/v13_demos.py [out_dir]
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


def buckling_constrained_demo(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """D090: buckling-constrained MMA binds λ_crit ≥ λ_safety while minimising compliance."""
    from structure_optimizer.core.buckling import buckling_constrained_mma

    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    r = buckling_constrained_mma(config, mesh, lambda_safety=8.0, max_iter=10)
    return _write(
        Path(out_path),
        "D090 buckling-constrained MMA",
        {
            "lambda_initial": f"{r.lambda_history[0]:.3f}",
            "lambda_final": f"{r.lambda_history[-1]:.3f}",
            "lambda_safety": "8.000",
        },
    )


def bandwidth_adaptive_demo(out_path: str | Path) -> dict:
    """D091: half-power relative bandwidth widens with damping (Δω/ω = α/ω + βω)."""
    from structure_optimizer.core.freq_response import half_power_relative_bandwidth

    omega = 1000.0
    return _write(
        Path(out_path),
        "D091 half-power bandwidth-adaptive window",
        {f"beta={b:g}": f"{half_power_relative_bandwidth(omega, beta=b):.5f}" for b in (5e-7, 2e-6, 8e-6)},
    )


def extent_demo(out_path: str | Path) -> dict:
    """D092: extent (Δ) + range-adaptive ρ — a two-extreme front spreads as wide as a
    dense one (spacing is blind to it); range-adaptive R2 is scale-invariant."""
    from structure_optimizer.core.multi_objective_to import (
        augmented_tchebycheff_r2,
        extent_indicator,
        spacing_indicator,
    )

    spread = np.array([[0.0, 4.0], [1.0, 3.0], [2.0, 2.0], [3.0, 1.0], [4.0, 0.0]])
    two_extreme = np.array([[0.0, 4.0], [4.0, 0.0]])
    w = np.array([[1.0, 0.0], [0.5, 0.5], [0.0, 1.0]])
    scaled = spread.copy()
    scaled[:, 0] *= 1000.0
    return _write(
        Path(out_path),
        "D092 extent + range-adaptive R2",
        {
            "extent_spread": f"{extent_indicator(spread):.4f}",
            "extent_two_extreme": f"{extent_indicator(two_extreme):.4f}",
            "spacing_both": f"{spacing_indicator(spread):.4f}",
            "r2_norm_base": f"{augmented_tchebycheff_r2(spread, weights=w, normalize_ranges=True):.4f}",
            "r2_norm_scaled_x1000": f"{augmented_tchebycheff_r2(scaled, weights=w, normalize_ranges=True):.4f}",
            "r2_fixed_scaled_x1000": f"{augmented_tchebycheff_r2(scaled, weights=w):.4f}",
        },
    )


# §5.2 grep alias
range_adaptive_demo = extent_demo


def gumbel_d_demo(out_path: str | Path) -> dict:
    """D093: d-dim exchangeable Gumbel copula — closed-form conditional CDF, τ = 1−1/θ."""
    from structure_optimizer.core.reliability import gumbel_d_copula

    g = gumbel_d_copula(3, 2.2)
    u = [0.3, 0.5, 0.7]
    return _write(
        Path(out_path),
        "D093 d-dim exchangeable Gumbel copula",
        {
            "cdf": f"{g.cdf(u):.6f}",
            "conditional_cdf": f"{g.conditional_cdf(u):.6f}",
            "kendall_tau": f"{g.kendall_tau():.6f}",
        },
    )


def genz_reorder_demo(out_path: str | Path) -> dict:
    """D094: Genz variable reordering converges to the same value with smaller error."""
    from structure_optimizer.core.reliability import genz_mvn_cdf, genz_mvn_cdf_reordered

    b = np.array([3.0, 2.5, 2.0, 1.0, 0.0, -0.5])
    R = np.full((6, 6), 0.5)
    np.fill_diagonal(R, 1.0)
    return _write(
        Path(out_path),
        "D094 Genz variable reordering",
        {
            "reordered": f"{genz_mvn_cdf_reordered(b, R, n_samples=20000, seed=0):.6f}",
            "unordered": f"{genz_mvn_cdf(b, R, n_samples=20000, seed=0):.6f}",
        },
    )


def stacking_demo(out_path: str | Path) -> dict:
    """D095: stacking-sequence optimisation — max bending vs symmetric (B=0)."""
    from structure_optimizer.core.orthotropic_simp import (
        optimize_stacking_sequence,
        orthotropic_plane_stress_matrix,
    )

    d0 = orthotropic_plane_stress_matrix(140e3, 10e3, 0.3, 5e3)
    mb = optimize_stacking_sequence(d0, np.array([0.0, 0.0, 45.0, 90.0, -45.0, 90.0]), 0.125, "max_bending")
    sym = optimize_stacking_sequence(d0, np.array([0.0, 45.0, 90.0]), 0.125, "max_bending", symmetric=True)
    return _write(
        Path(out_path),
        "D095 stacking-sequence optimisation",
        {
            "max_bending_D11": f"{mb.objective_value:.2f}",
            "max_bending_seq": str([int(a) for a in mb.sequence]),
            "symmetric_B_norm": f"{np.linalg.norm(sym.b_matrix):.2e}",
        },
    )


def ruppert_demo(out_path: str | Path) -> dict:
    """D096: Ruppert Steiner insertion lifts the min angle of a 4×1 sliver above 20°."""
    from structure_optimizer.core.stl_export import (
        _min_triangle_angle,
        constrained_delaunay_flip_recover,
        constrained_delaunay_ruppert,
    )

    rect = [[0.0, 0.0], [4.0, 0.0], [4.0, 1.0], [0.0, 1.0]]
    p_law, t_law = constrained_delaunay_flip_recover(rect, refine=True)
    p_rup, t_rup = constrained_delaunay_ruppert(rect, min_angle_deg=20.0)
    return _write(
        Path(out_path),
        "D096 Ruppert quality refinement",
        {
            "lawson_min_angle_deg": f"{np.degrees(_min_triangle_angle(p_law, t_law)):.2f}",
            "ruppert_min_angle_deg": f"{np.degrees(_min_triangle_angle(p_rup, t_rup)):.2f}",
            "n_steiner": len(p_rup) - 4,
        },
    )


def main(out_dir: str | Path = "build/v13_demos") -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    buckling_constrained_demo(out / "d090_buckling_constrained.html")
    bandwidth_adaptive_demo(out / "d091_bandwidth_adaptive.html")
    extent_demo(out / "d092_extent.html")
    gumbel_d_demo(out / "d093_gumbel_d.html")
    genz_reorder_demo(out / "d094_genz_reorder.html")
    stacking_demo(out / "d095_stacking.html")
    ruppert_demo(out / "d096_ruppert.html")
    print(f"wrote v13 demos to {out}")


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else "build/v13_demos")
