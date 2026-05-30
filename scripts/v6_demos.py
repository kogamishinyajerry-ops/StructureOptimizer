"""Wave LL (v6): production-grade demo / render artifacts.

Self-contained HTML + STL demos for the v6 formulations, in the same inline-SVG,
no-external-dependency spirit as the v3 interactive demo (D012). Each function
runs a real v6 computation and writes a real artifact; ``main()`` regenerates
them all into ``out_dir`` (default ``build/v6_demos/``).

Demos:
- ``convergence_study`` — analytical-vs-numerical area convergence of the
  marching-squares boundary (O(h²)) vs the voxel staircase (O(h)); HTML log-log.
- ``render_bode`` — damped frequency-response Bode plot (magnitude + phase) from
  ``solve_damped_frequency_response`` over a frequency sweep.
- ``render_nsga3_html`` — 3-objective NSGA-III Pareto front projected to HTML.
- ``smooth_vs_voxel_demo`` — writes the smooth (marching-squares) and voxel STLs
  of the same density field side by side and reports the triangle counts.

These are illustrative; the quantitative correctness lives in the test suite.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.pareto_nsga import nsga3
from structure_optimizer.core.stl_export import (
    marching_squares_contours,
    polygon_area,
    write_stl,
    write_stl_marching_squares,
)


def _disk_field(n: int, r: float = 0.3, cx: float = 0.5, cy: float = 0.5):
    xs = np.linspace(0.0, 1.0, n)
    ys = np.linspace(0.0, 1.0, n)
    grid_x, grid_y = np.meshgrid(xs, ys)
    field = r * r - ((grid_x - cx) ** 2 + (grid_y - cy) ** 2)
    return field, xs, ys


def convergence_study(out_path: str | Path, radius: float = 0.3) -> dict:
    """Marching-squares vs voxel area convergence to the analytical disk area.

    Writes a self-contained HTML log-log convergence plot and returns the
    measured errors.
    """
    exact = math.pi * radius * radius
    rows = []
    for n in (33, 65, 129, 257):
        field, xs, ys = _disk_field(n, r=radius)
        loops = marching_squares_contours(field, xs, ys, level=0.0)
        ms_area = sum(polygon_area(lp) for lp in loops)
        h = float(xs[1] - xs[0])
        voxel_area = float((field > 0.0).sum()) * h * h
        rows.append((n, h, abs(ms_area - exact), abs(voxel_area - exact)))

    # log-log SVG: error vs h
    w, hgt, m = 640, 420, 60
    hs = [r[1] for r in rows]
    errs = [r[2] for r in rows] + [r[3] for r in rows]
    lx = [math.log10(v) for v in hs]
    ly = [math.log10(v) for v in errs if v > 0]
    xmin, xmax = min(lx), max(lx)
    ymin, ymax = min(ly), max(ly)

    def px(lxv):
        return m + (lxv - xmin) / max(xmax - xmin, 1e-9) * (w - 2 * m)

    def py(lyv):
        return hgt - m - (lyv - ymin) / max(ymax - ymin, 1e-9) * (hgt - 2 * m)

    def series(idx, color):
        pts = " ".join(f"{px(math.log10(r[1])):.1f},{py(math.log10(r[idx])):.1f}" for r in rows)
        dots = "".join(
            f'<circle cx="{px(math.log10(r[1])):.1f}" cy="{py(math.log10(r[idx])):.1f}" r="4" fill="{color}"/>'
            for r in rows
        )
        return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>{dots}'

    svg = (
        f'<svg width="{w}" height="{hgt}" style="background:#fafafa;border:1px solid #ccc">'
        f"{series(2, '#0066cc')}{series(3, '#cc3300')}"
        f'<text x="{w / 2}" y="{hgt - 20}" text-anchor="middle" font-size="13">log₁₀ h (cell size)</text>'
        f'<text x="20" y="{hgt / 2}" text-anchor="middle" font-size="13" transform="rotate(-90,20,{hgt / 2})">log₁₀ |area error|</text>'
        f'<text x="{w - 160}" y="40" font-size="12" fill="#0066cc">■ marching squares O(h²)</text>'
        f'<text x="{w - 160}" y="58" font-size="12" fill="#cc3300">■ voxel staircase O(h)</text>'
        "</svg>"
    )
    table = "".join(
        f"<tr><td>{n}</td><td>{h:.4f}</td><td>{e_ms:.3e}</td><td>{e_vx:.3e}</td><td>{e_ms / e_vx:.3f}</td></tr>"
        for (n, h, e_ms, e_vx) in rows
    )
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>v6 convergence study — boundary area</title>
<style>body{{font-family:-apple-system,sans-serif;margin:24px}}table{{border-collapse:collapse}}
td,th{{border:1px solid #ccc;padding:4px 10px;font-size:13px}}</style></head><body>
<h2>Boundary-area convergence: marching squares vs voxel</h2>
<p>Exact disk area πR² = {exact:.6f}. Marching-squares error quarters as h halves
(O(h²)); voxel error only halves (O(h)).</p>
{svg}
<table><tr><th>n</th><th>h</th><th>MS error</th><th>voxel error</th><th>MS/voxel</th></tr>{table}</table>
</body></html>"""
    out_path = Path(out_path)
    out_path.write_text(html)
    return {"out_path": str(out_path), "exact_area": exact, "rows": rows}


def render_bode(out_path: str | Path, benchmark: str = "cantilever") -> dict:
    """Damped frequency-response Bode plot (magnitude + phase) over a sweep."""
    from structure_optimizer.core.freq_response import solve_damped_frequency_response

    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    densities = np.ones(mesh.elements.shape[0])
    omegas = np.linspace(0.5, 40.0, 60)
    mags, phases = [], []
    for om in omegas:
        r = solve_damped_frequency_response(config, mesh, densities, omega=float(om), alpha=0.5, beta=1e-4)
        mags.append(r.max_magnitude)
        phases.append(float(np.mean(r.phase)))

    w, hgt, m = 640, 240, 50

    def plot(values, color, ylabel):
        vmin, vmax = min(values), max(values)

        def px(i):
            return m + i / (len(values) - 1) * (w - 2 * m)

        def py(v):
            return hgt - m - (v - vmin) / max(vmax - vmin, 1e-12) * (hgt - 2 * m)

        pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(values))
        return (
            f'<svg width="{w}" height="{hgt}" style="background:#fafafa;border:1px solid #ccc">'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>'
            f'<text x="{w / 2}" y="{hgt - 15}" text-anchor="middle" font-size="12">ω (rad/s)</text>'
            f'<text x="18" y="{hgt / 2}" text-anchor="middle" font-size="12" transform="rotate(-90,18,{hgt / 2})">{ylabel}</text>'
            "</svg>"
        )

    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>v6 damped frequency response (Bode)</title>
<style>body{{font-family:-apple-system,sans-serif;margin:24px}}</style></head><body>
<h2>Rayleigh-damped frequency response — Bode plot</h2>
<p>C = αM + βK with α=0.5, β=1e-4; response stays finite through resonance.</p>
<h3>Magnitude</h3>{plot(mags, "#0066cc", "max |û|")}
<h3>Phase</h3>{plot(phases, "#9900cc", "mean phase (rad)")}
</body></html>"""
    out_path = Path(out_path)
    out_path.write_text(html)
    return {"out_path": str(out_path), "n_points": len(omegas), "peak_magnitude": max(mags)}


def render_nsga3_html(out_path: str | Path) -> dict:
    """Render a 3-objective NSGA-III Pareto front (DTLZ2) to self-contained HTML."""

    def dtlz2(x):
        x = np.asarray(x, dtype=float)
        g = float(np.sum((x[2:] - 0.5) ** 2))
        f0 = (1 + g) * math.cos(x[0] * math.pi / 2) * math.cos(x[1] * math.pi / 2)
        f1 = (1 + g) * math.cos(x[0] * math.pi / 2) * math.sin(x[1] * math.pi / 2)
        f2 = (1 + g) * math.sin(x[0] * math.pi / 2)
        return (f0, f1, f2)

    n_vars = 2 + 4
    front = nsga3(
        dtlz2,
        n_vars,
        np.zeros(n_vars),
        np.ones(n_vars),
        n_obj=3,
        n_divisions=12,
        n_generations=60,
        rng_seed=0,
    )
    objs = front.objectives
    # Simple isometric projection of (f0,f1,f2) onto 2D.
    w, hgt, m = 520, 420, 60
    proj = np.column_stack(
        [
            objs[:, 0] - objs[:, 1] * 0.5,
            objs[:, 2] - (objs[:, 0] + objs[:, 1]) * 0.25,
        ]
    )
    pmin, pmax = proj.min(axis=0), proj.max(axis=0)
    rng = np.maximum(pmax - pmin, 1e-9)
    dots = "".join(
        f'<circle cx="{m + (p[0] - pmin[0]) / rng[0] * (w - 2 * m):.1f}" '
        f'cy="{hgt - m - (p[1] - pmin[1]) / rng[1] * (hgt - 2 * m):.1f}" r="3.5" fill="#0066cc" opacity="0.7"/>'
        for p in proj
    )
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>v6 NSGA-III 3-objective Pareto front</title>
<style>body{{font-family:-apple-system,sans-serif;margin:24px}}</style></head><body>
<h2>NSGA-III — 3-objective Pareto front (DTLZ2, isometric projection)</h2>
<p>{front.n_front} non-dominated points on the unit-sphere octant Σf²=1
(Das-Dennis reference directions + niching).</p>
<svg width="{w}" height="{hgt}" style="background:#fafafa;border:1px solid #ccc">{dots}</svg>
</body></html>"""
    out_path = Path(out_path)
    out_path.write_text(html)
    return {"out_path": str(out_path), "n_front": front.n_front}


def smooth_vs_voxel_demo(out_dir: str | Path, benchmark: str = "cantilever") -> dict:
    """Write the smooth (marching-squares) and voxel STLs of one density field.

    Returns the two paths + triangle counts so the smooth-vs-voxel difference is
    visible (the smooth boundary cuts the staircase corners).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    config = load_benchmark(benchmark, preset="smoke")
    mesh = create_structured_mesh(config)
    densities = np.zeros(mesh.elements.shape[0])
    cw, ch = mesh.width / mesh.nelx, mesh.height / mesh.nely
    rad = 0.35 * min(mesh.width, mesh.height)
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            xc, yc = (ex + 0.5) * cw, (ey + 0.5) * ch
            if (xc - mesh.width / 2) ** 2 + (yc - mesh.height / 2) ** 2 < rad * rad:
                densities[mesh.element_index(ex, ey)] = 1.0
    voxel = write_stl(mesh, densities, out_dir / "demo_voxel.stl")
    smooth = write_stl_marching_squares(mesh, densities, out_dir / "demo_smooth.stl")
    return {"voxel": voxel, "smooth": smooth}


def main(out_dir: str | Path = "build/v6_demos") -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print("convergence_study:", convergence_study(out_dir / "convergence_study.html")["exact_area"])
    print("render_bode:", render_bode(out_dir / "bode.html")["peak_magnitude"])
    print("render_nsga3_html:", render_nsga3_html(out_dir / "nsga3_pareto.html")["n_front"])
    print("smooth_vs_voxel_demo:", smooth_vs_voxel_demo(out_dir))
    print(f"v6 demos written to {out_dir}/")


if __name__ == "__main__":
    main()
