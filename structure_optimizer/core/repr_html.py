"""Wave Q: Jupyter rich-display helpers.

Provides ``_repr_html_`` formatters for the main result dataclasses so they
render as nice tables in JupyterLab / VS Code Notebooks instead of the
default ``OptimizationResult(densities=array(...), ...)`` ndarray dump.

Also provides ``_repr_png_`` for ``OptimizationResult`` — a small PNG
preview of the final density field, rendered with the existing pure-NumPy
``visualization.write_density_png`` machinery.

All formatters are import-time lazy; if the result dataclass classes import
this module they don't pull in `visualization` until an actual notebook
renders the result.
"""

from __future__ import annotations

import io
import struct
import zlib
from html import escape
from typing import Any

import numpy as np


def _table_row(label: str, value: str) -> str:
    return f"<tr><td style='padding:2px 8px;border-bottom:1px solid #eee;font-weight:600'>{escape(label)}</td><td style='padding:2px 8px;border-bottom:1px solid #eee'>{escape(value)}</td></tr>"


def _format_number(value: float, precision: int = 4) -> str:
    if not np.isfinite(value):
        return str(value)
    if value == 0:
        return "0"
    abs_v = abs(value)
    if abs_v >= 1e6 or abs_v < 1e-3:
        return f"{value:.{precision}e}"
    return f"{value:.{precision}g}"


def optimization_result_repr_html(result: Any) -> str:
    """Render an ``OptimizationResult`` (quad SIMP) as an HTML table.

    Shape: header (n_iters, stop_reason) + scalar metrics table (final
    compliance vs baseline, mass, max disp) + first/last iteration row.
    """
    final = result.final_analysis
    base = result.baseline
    n_iters = len(result.metrics)
    rows = [
        _table_row("Iterations", str(n_iters)),
        _table_row("Stop reason", str(result.stop_reason)),
        _table_row("Density elements", str(int(result.densities.shape[0]))),
        _table_row("Compliance (final)", _format_number(float(final.compliance))),
        _table_row("Compliance (baseline)", _format_number(float(base.compliance))),
        _table_row("Mass (final)", _format_number(float(final.mass))),
        _table_row("Max displacement (final)", _format_number(float(final.max_displacement))),
        _table_row("Max von-Mises stress (final)", _format_number(float(final.max_stress))),
        _table_row("Load cases", ", ".join(str(n) for n in result.load_case_names) or "(default)"),
    ]
    if result.metrics:
        first = result.metrics[0]
        last = result.metrics[-1]
        rows.append(
            _table_row(
                "Volume fraction (first → last)",
                f"{_format_number(first.volume_fraction)} → {_format_number(last.volume_fraction)}",
            )
        )
        rows.append(
            _table_row("Δρ (last iter)", _format_number(float(last.change))),
        )
    body = "".join(rows)
    return (
        "<div style='font-family:ui-sans-serif,system-ui,-apple-system'>"
        "<div style='font-weight:700;font-size:13px;margin-bottom:4px;color:#147d45'>"
        "OptimizationResult"
        "</div>"
        f"<table style='border-collapse:collapse;font-size:12px'>{body}</table>"
        "</div>"
    )


def triangle_optimization_result_repr_html(result: Any) -> str:
    """Render a ``TriangleOptimizationResult`` as an HTML table."""
    n_iters = len(result.metrics)
    rows = [
        _table_row("Iterations", str(n_iters)),
        _table_row("Stop reason", str(result.stop_reason)),
        _table_row("Density elements", str(int(result.densities.shape[0]))),
        _table_row("Compliance (final)", _format_number(float(result.final_compliance))),
        _table_row("Compliance (baseline, full-solid)", _format_number(float(result.baseline_compliance))),
    ]
    if result.metrics:
        first = result.metrics[0]
        last = result.metrics[-1]
        rows.append(
            _table_row(
                "Volume fraction (first → last)",
                f"{_format_number(first.volume_fraction)} → {_format_number(last.volume_fraction)}",
            )
        )
        rows.append(_table_row("Δρ (last iter)", _format_number(float(last.change))))
    body = "".join(rows)
    return (
        "<div style='font-family:ui-sans-serif,system-ui,-apple-system'>"
        "<div style='font-weight:700;font-size:13px;margin-bottom:4px;color:#007c89'>"
        "TriangleOptimizationResult"
        "</div>"
        f"<table style='border-collapse:collapse;font-size:12px'>{body}</table>"
        "</div>"
    )


def fem_result_repr_html(result: Any) -> str:
    """Render an ``FEMResult`` (single linear-elastic solve) as an HTML table."""
    rows = [
        _table_row("Compliance", _format_number(float(result.compliance))),
        _table_row("Max displacement", _format_number(float(result.max_displacement))),
        _table_row("Max von-Mises stress", _format_number(float(result.max_stress))),
        _table_row("Mass", _format_number(float(result.mass))),
        _table_row("DOFs", str(int(result.displacements.shape[0]))),
        _table_row(
            "Element strain energy (mean / max)",
            f"{_format_number(float(np.mean(result.element_strain_energy)))} / {_format_number(float(np.max(result.element_strain_energy)))}",
        ),
    ]
    body = "".join(rows)
    return (
        "<div style='font-family:ui-sans-serif,system-ui,-apple-system'>"
        "<div style='font-weight:700;font-size:13px;margin-bottom:4px;color:#a15c00'>"
        "FEMResult"
        "</div>"
        f"<table style='border-collapse:collapse;font-size:12px'>{body}</table>"
        "</div>"
    )


def benchmark_config_repr_html(config: Any) -> str:
    """Render a ``BenchmarkConfig`` summary as an HTML table."""
    rows = [
        _table_row("Benchmark", str(config.name)),
        _table_row("Dimension", str(config.dimension)),
        _table_row("Mesh", f"{config.mesh.nelx} × {config.mesh.nely}"),
        _table_row("Domain", f"{config.mesh.width} × {config.mesh.height}"),
        _table_row("Material E", _format_number(float(config.material.young_modulus))),
        _table_row("Poisson ν", _format_number(float(config.material.poisson_ratio))),
        _table_row("Algorithm", str(config.optimization.algorithm)),
        _table_row("Volume fraction", _format_number(float(config.optimization.volume_fraction))),
        _table_row("Penalty p", _format_number(float(config.optimization.penalty))),
        _table_row("Filter radius", _format_number(float(config.optimization.filter_radius))),
        _table_row("Max iterations", str(int(config.optimization.max_iterations))),
        _table_row("Solver backend", str(config.solver.backend)),
        _table_row("Stress constraint", "enabled" if config.stress_constraint.enabled else "disabled"),
    ]
    body = "".join(rows)
    return (
        "<div style='font-family:ui-sans-serif,system-ui,-apple-system'>"
        "<div style='font-weight:700;font-size:13px;margin-bottom:4px;color:#007c89'>"
        f"BenchmarkConfig — {escape(config.name)}"
        "</div>"
        f"<table style='border-collapse:collapse;font-size:12px'>{body}</table>"
        "</div>"
    )


# --- _repr_png_ helpers ------------------------------------------------


def _grayscale_png_bytes(pixels: np.ndarray) -> bytes:
    """Encode an (H, W) uint8 grayscale array as PNG bytes (pure-NumPy + zlib)."""
    if pixels.ndim != 2:
        raise ValueError(f"pixels must be 2-D, got shape {pixels.shape}")
    if pixels.dtype != np.uint8:
        pixels = pixels.astype(np.uint8)
    h, w = pixels.shape

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)  # 8-bit grayscale
    raw = b"".join(b"\x00" + bytes(row) for row in pixels)  # filter byte 0 per scanline
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def density_field_repr_png(densities: np.ndarray, mesh: Any, max_dim: int = 320) -> bytes:
    """Render a density field as a small grayscale PNG for Jupyter ``_repr_png_``.

    Uses the structured-quad mesh layout to reshape densities to (nely, nelx)
    then up/down-samples to fit ``max_dim``. Returns PNG bytes.
    """
    nelx = int(mesh.nelx)
    nely = int(mesh.nely)
    grid = np.asarray(densities, dtype=float).reshape((nely, nelx))
    # densities ∈ [0, 1]; map 0 → white, 1 → black for traditional topo viz
    pixels = np.clip((1.0 - grid) * 255.0, 0, 255).astype(np.uint8)
    # nearest-neighbor upscale so small meshes are visible
    h, w = pixels.shape
    scale = max(1, int(max_dim // max(h, w)))
    if scale > 1:
        pixels = np.repeat(np.repeat(pixels, scale, axis=0), scale, axis=1)
    return _grayscale_png_bytes(pixels)


def write_png_to_buffer(densities: np.ndarray, mesh: Any) -> io.BytesIO:
    """Convenience wrapper for callers that want a file-like buffer."""
    return io.BytesIO(density_field_repr_png(densities, mesh))
