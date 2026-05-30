"""v16 deep-embedding & exact-generalization demos (Wave HHHHHHHH closure, D121).

Real, deterministic demonstrations of the v16 capability waves — each runs the actual
production function (deeper embedding / exact upgrade / generalization) and writes a small
HTML summary. Mirrors ``scripts/v15_demos.py``. No network, numpy-only mandatory runtime.

Usage:  python scripts/v16_demos.py [out_dir]
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


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


def antisym_embed_demo(out_path: str | Path) -> dict:
    """D114: bending_shear_decoupled=True embeds the anti-symmetric ordering into
    optimize_stacking_sequence — the optimised stack zeros D₁₆=D₂₆ (and A₁₆=A₂₆);
    the plain (=False) optimum on the same input keeps D₁₆≠0."""
    from structure_optimizer.core.orthotropic_simp import (
        laminate_abd,
        optimize_stacking_sequence,
        orthotropic_plane_stress_matrix,
    )

    d0 = orthotropic_plane_stress_matrix(140e3, 10e3, 0.3, 5e3)
    inv = np.deg2rad([20.0, 35.0, 55.0, 70.0])
    anti = optimize_stacking_sequence(d0, inv, 0.125, objective="max_bending", bending_shear_decoupled=True)
    plain = optimize_stacking_sequence(d0, inv, 0.125, objective="max_bending")
    _, _, d_a = laminate_abd(d0, anti.sequence, np.full(len(anti.sequence), 0.125))
    _, _, d_p = laminate_abd(d0, plain.sequence, np.full(len(plain.sequence), 0.125))
    return _write(
        Path(out_path),
        "D114 anti-symmetric ordering embedded in stacking optimiser",
        {
            "decoupled D16": f"{d_a[0, 2]:.3e}",
            "decoupled D26": f"{d_a[1, 2]:.3e}",
            "plain D16 (≠0)": f"{d_p[0, 2]:.3e}",
            "decoupled D_11": f"{anti.objective_value:.4f}",
        },
    )


def general_marginal_demo(out_path: str | Path) -> dict:
    """D115: series-copula reliability with general non-normal marginals — Weibull/Gumbel
    per-mode CDFs coupled by the copula; the all-N(0,1) case reduces exactly to D098."""
    from structure_optimizer.core.reliability import (
        Marginal,
        gumbel_d_copula,
        system_reliability_series_copula,
        system_reliability_series_copula_marginals,
    )

    betas = np.array([2.0, 2.5])
    cop = gumbel_d_copula(2, 2.0)
    norm = [Marginal("normal", 0.0, 1.0)] * 2
    pf_norm = system_reliability_series_copula_marginals(norm, betas, cop)
    pf_orig = system_reliability_series_copula(betas, cop)
    mg = [Marginal("weibull", 2.0, 3.0), Marginal("gumbel", 1.0, 0.5)]
    pf_gen = system_reliability_series_copula_marginals(mg, [2.5, 1.2], cop)
    return _write(
        Path(out_path),
        "D115 general non-normal marginals (mixture-copula series P_f)",
        {
            "P_f normal-marginals": f"{pf_norm:.6e}",
            "P_f D098 reference (=)": f"{pf_orig:.6e}",
            "bit-exact match": pf_norm == pf_orig,
            "P_f Weibull+Gumbel marginals": f"{pf_gen:.6e}",
        },
    )


def cbc_lattice_demo(out_path: str | Path) -> dict:
    """D116: genz_mvn_cdf_cbc estimates a bivariate-normal CDF with a deterministic CBC
    rank-1 lattice (seed-free) and reports a deterministic worst-case-error certificate."""
    from structure_optimizer.core.reliability import _standard_normal_cdf, genz_mvn_cdf_cbc

    upper = np.array([1.0, 0.5])
    corr = np.array([[1.0, 0.3], [0.3, 1.0]])
    res = genz_mvn_cdf_cbc(upper, corr, n_points=1021)
    res2 = genz_mvn_cdf_cbc(upper, corr, n_points=1021)  # seed-free reproducibility
    indep = _standard_normal_cdf(1.0) * _standard_normal_cdf(0.5)
    return _write(
        Path(out_path),
        "D116 CBC deterministic lattice Genz MVN CDF",
        {
            "Φ₂(b;R) estimate": f"{res.value:.6f}",
            "worst-case-error cert e(z)": f"{res.worst_case_error:.3e}",
            "n_points": res.n_points,
            "reproducible (seed-free)": res.value == res2.value,
            "independence ref Φ(b₁)Φ(b₂)": f"{indep:.6f}",
        },
    )


def exact_multiplier_demo(out_path: str | Path) -> dict:
    """D117: peak_binding_exact_multiplier is the envelope-theorem shadow price λ=−dJ*/dlimit.
    For a closed-form value function J*(L)=A/L it recovers λ=A/L² exactly; a flat J* gives
    λ=0 (inactive); a decreasing J* gives λ>0 (active)."""
    from structure_optimizer.core.freq_response import peak_binding_exact_multiplier

    a, limit = 100.0, 5.0
    lam_inv = peak_binding_exact_multiplier(lambda ll: a / ll, limit, rel_delta=0.005)
    lam_flat = peak_binding_exact_multiplier(lambda ll: 42.0, limit=3.0, rel_delta=0.1)
    lam_active = peak_binding_exact_multiplier(lambda ll: max(0.0, 20.0 - ll), limit=5.0, rel_delta=0.02)
    return _write(
        Path(out_path),
        "D117 exact KKT shadow-price multiplier (envelope theorem)",
        {
            "λ for J*=A/L (closed form A/L²=4.0)": f"{lam_inv:.4f}",
            "λ flat J* (inactive, =0)": f"{lam_flat:.2e}",
            "λ decreasing J* (active, >0)": f"{lam_active:.4f}",
        },
    )


def alpha_korobov_demo(out_path: str | Path) -> dict:
    """D118: higher-smoothness (α≥2) weighted-Korobov worst-case error via the B_{2α}
    kernel — α=1 reproduces D112; larger α certifies a smoother space with faster decay."""
    from structure_optimizer.core.reliability import korobov_worst_case_error

    n = 1021
    z = np.array([1, 374, 593, 453, 781])
    gamma = np.array([1.0 / (i + 1) ** 2 for i in range(5)])
    rows = {}
    prev = None
    for alpha in (1, 2, 3):
        e = korobov_worst_case_error(z, n, gamma, smoothness=alpha)
        rows[f"e(z) α={alpha}"] = f"{e:.4e}"
        if prev is not None:
            rows[f"ratio α={alpha}/α={alpha - 1}"] = f"{prev / max(e, 1e-300):.2f}×"
        prev = e
    return _write(Path(out_path), "D118 α≥2 higher-smoothness Korobov worst-case error", rows)


def parallel_system_demo(out_path: str | Path) -> dict:
    """D119: copula parallel (fails iff all fail) and k-out-of-n system reliability —
    k=1 ≡ series, k=m ≡ parallel, parallel ≤ series, P(≥k) non-increasing in k."""
    from structure_optimizer.core.reliability import (
        gumbel_d_copula,
        system_reliability_k_out_of_n_copula,
        system_reliability_parallel_copula,
        system_reliability_series_copula,
    )

    betas = np.array([2.0, 2.5, 3.0, 1.8])
    cop = gumbel_d_copula(4, 2.5)
    pf_series = system_reliability_series_copula(betas, cop)
    pf_par = system_reliability_parallel_copula(betas, cop)
    ks = {f"P(≥{k} fail)": f"{system_reliability_k_out_of_n_copula(betas, cop, k):.6e}" for k in (1, 2, 3, 4)}
    return _write(
        Path(out_path),
        "D119 copula parallel / k-out-of-n system reliability",
        {
            "P_f series (k=1)": f"{pf_series:.6e}",
            "P_f parallel (k=m)": f"{pf_par:.6e}",
            "parallel ≤ series": pf_par <= pf_series,
            **ks,
        },
    )


def fast_cbc_demo(out_path: str | Path) -> dict:
    """D120: fast-CBC (Nuyens–Cools FFT, O(d·N·log N)) builds a certified-optimal lattice
    generating vector deterministically — its worst-case error is ≤ the textbook Korobov
    vector's, computed via one FFT pair instead of the naive O(N²) rescan."""
    from structure_optimizer.core.reliability import (
        _korobov_generating_vector,
        fast_cbc_korobov_generating_vector,
        korobov_worst_case_error,
    )

    n, d = 1021, 5
    gamma = np.array([1.0 / (i + 1) ** 2 for i in range(d)])
    z_fast = fast_cbc_korobov_generating_vector(d, n, gamma)
    z_kor = _korobov_generating_vector(d, 76, n)
    return _write(
        Path(out_path),
        "D120 fast-CBC (FFT) certified-optimal lattice",
        {
            "N (prime)": n,
            "fast-CBC z": np.asarray(z_fast).tolist(),
            "e(z_fastCBC)": f"{korobov_worst_case_error(z_fast, n, gamma):.6e}",
            "e(z_Korobov textbook)": f"{korobov_worst_case_error(z_kor, n, gamma):.6e}",
            "fast-CBC ≤ Korobov": korobov_worst_case_error(z_fast, n, gamma)
            <= korobov_worst_case_error(z_kor, n, gamma),
        },
    )


def main(out_dir: str | Path = "build/v16_demos") -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    antisym_embed_demo(out / "d114_antisym_embed.html")
    general_marginal_demo(out / "d115_general_marginal.html")
    cbc_lattice_demo(out / "d116_cbc_lattice.html")
    exact_multiplier_demo(out / "d117_exact_multiplier.html")
    alpha_korobov_demo(out / "d118_alpha_korobov.html")
    parallel_system_demo(out / "d119_parallel_system.html")
    fast_cbc_demo(out / "d120_fast_cbc.html")
    print(f"wrote v16 demos to {out}")


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else "build/v16_demos")
