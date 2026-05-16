"""Wave V: comparative side-by-side HTML report for multiple SIMP runs.

Given ≥2 ``OptimizationResult`` instances (typically from the same
benchmark with different parameters), emits a single HTML page showing
their density fields side-by-side plus a compliance / volume / mass
comparison table. Useful for parameter studies and reviewer-facing
sanity checks.

Stays consistent with the rest of the project's HTML-rendering style:
- Pure NumPy (no Pillow / no JS framework).
- Grayscale PNG via the existing ``repr_html`` helpers.
- One CommonMark-friendly structure so it can be embedded into reports.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import numpy as np

from structure_optimizer.core.repr_html import _grayscale_png_bytes
from structure_optimizer.core.simp import OptimizationResult


@dataclass(frozen=True)
class ComparisonEntry:
    """One run + label for a side-by-side comparison."""

    label: str
    result: OptimizationResult
    notes: str = ""


def comparison_html(entries: list[ComparisonEntry], title: str = "Comparison") -> str:
    """Render ≥2 OptimizationResults side by side as a standalone HTML page.

    Layout:
        <h1>{title}</h1>
        <table>
            <thead>label1 | label2 | ... | labelN</thead>
            <tbody>
                <tr>thumbnail | thumbnail | ... | thumbnail</tr>
                <tr>compliance | compliance | ... </tr>
                <tr>volume_fraction | ...</tr>
                ...
            </tbody>
        </table>
    """
    if len(entries) < 2:
        raise ValueError("comparison_html needs ≥2 entries")

    rows: list[str] = []
    rows.append(f"<h1>{_html_escape(title)}</h1>")
    rows.append('<table border="1" cellpadding="6" cellspacing="0">')
    # Header row: labels
    header = "<tr>" + "".join(f"<th>{_html_escape(e.label)}</th>" for e in entries) + "</tr>"
    rows.append("<thead>" + header + "</thead>")
    rows.append("<tbody>")

    # Image row (each PNG embedded as base64)
    img_row = "<tr>"
    for e in entries:
        png = _entry_thumbnail_png(e.result)
        if png is None:
            img_row += "<td>(no mesh_shape)</td>"
        else:
            b64 = base64.b64encode(png).decode("ascii")
            img_row += f'<td><img src="data:image/png;base64,{b64}" /></td>'
    img_row += "</tr>"
    rows.append(img_row)

    # Metric rows
    metric_specs = [
        ("compliance", lambda r: float(r.final_analysis.compliance), "{:.4f}"),
        ("baseline_compliance", lambda r: float(r.baseline.compliance), "{:.4f}"),
        ("mass", lambda r: float(r.final_analysis.mass), "{:.4e}"),
        (
            "max_disp",
            lambda r: float(r.final_analysis.max_displacement),
            "{:.4f}",
        ),
        ("stop_reason", lambda r: str(r.stop_reason), "{}"),
        ("iterations", lambda r: len(r.metrics), "{}"),
    ]
    for label, getter, fmt in metric_specs:
        row = f"<tr><th align='left'>{_html_escape(label)}</th>"
        # The header row above shows N labels; here the leftmost cell is the
        # metric name and the remaining N-1 cells show values. But we need
        # the column count to match the header (N). Adjust by adding the
        # metric name as a row label outside the table, or by including all
        # N columns with values. We'll go with the latter, fitted via a
        # "metric: value" cell:
        row = "<tr>"
        for e in entries:
            row += f"<td><b>{_html_escape(label)}</b>: " + fmt.format(getter(e.result)) + "</td>"
        row += "</tr>"
        rows.append(row)

    # Notes row
    if any(e.notes for e in entries):
        notes_row = "<tr>"
        for e in entries:
            notes_row += f"<td><i>{_html_escape(e.notes)}</i></td>"
        notes_row += "</tr>"
        rows.append(notes_row)

    rows.append("</tbody></table>")

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{_html_escape(title)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1200px;margin:2em auto;padding:0 1em}}
img{{max-width:280px;image-rendering:pixelated;border:1px solid #ccc}}</style>
</head><body>
{"".join(rows)}
</body></html>"""


def _entry_thumbnail_png(result: OptimizationResult) -> bytes | None:
    """Return a small grayscale PNG of the density field, or None if mesh_shape unknown."""
    nelx, nely = result.mesh_shape
    if nelx <= 0 or nely <= 0:
        return None
    grid = np.asarray(result.densities, dtype=float).reshape((nely, nelx))
    pixels = np.clip((1.0 - grid) * 255.0, 0, 255).astype(np.uint8)
    scale = max(1, 280 // max(nelx, nely))
    if scale > 1:
        pixels = np.repeat(np.repeat(pixels, scale, axis=0), scale, axis=1)
    return _grayscale_png_bytes(pixels)


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def write_comparison_html(
    entries: list[ComparisonEntry],
    output_path: str,
    title: str = "Comparison",
) -> str:
    """Write the HTML report to ``output_path``; return the path."""
    html = comparison_html(entries, title=title)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path
