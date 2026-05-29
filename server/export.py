"""Geometry export for a completed run — SVG / DXF / STL.

Mirrors the CLI ``export`` subcommand (``cli.py``) exactly: rebuild the mesh
from the persisted ``input.json``, load ``density.npy``, and write the chosen
vector/mesh format. Returns the bytes + a download filename + MIME type so the
web layer can stream it as an attachment.

This adds no geometry logic — it reuses ``core.geometry_export`` verbatim. The
only web-layer addition is a provenance + disclaimer header injected into the
text formats (SVG/DXF) so a downstream CAD consumer can't mistake an unverified
optimization candidate for a certified part. The engine/CLI path is untouched
(byte-identical), so this never affects reproducibility fingerprints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from structure_optimizer.core.config import BenchmarkConfig, parse_config, validate_config
from structure_optimizer.core.geometry_export import (
    write_dxf,
    write_stl_extrusion,
    write_svg,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.run_store import load_density, read_json

# format -> (mime type, file extension)
EXPORT_FORMATS: dict[str, tuple[str, str]] = {
    "svg": ("image/svg+xml", "svg"),
    "dxf": ("application/dxf", "dxf"),
    "stl": ("model/stl", "stl"),
}

# The standing disclaimer for every candidate exported from the workbench.
_DISCLAIMER = (
    "StructureOptimizer optimization candidate — NOT a certified result. "
    "Independent engineering review is required before production use."
)


def _safe_read(run_dir: Path, name: str) -> dict[str, Any]:
    """Read a run-dir JSON artifact, returning {} if it's missing/malformed."""
    try:
        return read_json(run_dir / name)
    except (FileNotFoundError, ValueError):
        return {}


def _provenance_lines(run_dir: Path, config: BenchmarkConfig) -> list[str]:
    """Human-readable provenance + disclaimer lines (no comment syntax).

    Sourced from the persisted summary/verification artifacts so the exported
    geometry carries the same candidate caveats the UI shows on screen.
    """
    summary = _safe_read(run_dir, "summary.json")
    verification = _safe_read(run_dir, "verification.json")
    lines = [_DISCLAIMER, f"benchmark: {config.name}   run: {run_dir.name}"]
    input_hash = summary.get("input_hash")
    if input_hash:
        lines.append(f"input_hash: {input_hash}")
    target = verification.get("target_volume_fraction")
    actual = verification.get("actual_volume_fraction")
    if target is not None and actual is not None:
        lines.append(f"volume_fraction: target {float(target):.3f} / actual {float(actual):.3f}")
    status = verification.get("status")
    if status:
        lines.append(f"verification: {status}")
    # XML comments forbid the "--" sequence; neutralise it defensively.
    return [line.replace("--", "—") for line in lines]


def _inject_svg_provenance(out_path: Path, run_dir: Path, config: BenchmarkConfig) -> bytes:
    """Splice an XML comment block after the ``<?xml ...?>`` declaration."""
    text = out_path.read_text()
    comment = "<!--\n" + "\n".join(f"  {line}" for line in _provenance_lines(run_dir, config)) + "\n-->"
    if text.startswith("<?xml"):
        head, _, tail = text.partition("\n")
        text = f"{head}\n{comment}\n{tail}"
    else:
        text = f"{comment}\n{text}"
    out_path.write_text(text)
    return text.encode("utf-8")


def _inject_dxf_provenance(out_path: Path, run_dir: Path, config: BenchmarkConfig) -> bytes:
    """Prepend DXF ``999`` comment group codes ahead of the first section."""
    text = out_path.read_text()
    header = "".join(f"999\n{line}\n" for line in _provenance_lines(run_dir, config))
    text = header + text
    out_path.write_text(text)
    return text.encode("utf-8")


def export_geometry(
    run_dir: Path,
    fmt: str,
    threshold: float = 0.5,
    extrusion_depth: float = 1.0,
) -> tuple[bytes, str, str]:
    """Build geometry for a run and return ``(data, filename, mime_type)``.

    Raises ``KeyError`` for an unknown format and ``FileNotFoundError`` if the
    run artifacts are missing.
    """
    mime, ext = EXPORT_FORMATS[fmt]

    config = parse_config(read_json(run_dir / "input.json"))
    validate_config(config)
    mesh = create_structured_mesh(config)
    densities = load_density(run_dir)

    out_path = run_dir / f"geometry.{ext}"
    if fmt == "svg":
        write_svg(out_path, mesh, densities, threshold=threshold)
        data = _inject_svg_provenance(out_path, run_dir, config)
    elif fmt == "dxf":
        write_dxf(out_path, mesh, densities, threshold=threshold)
        data = _inject_dxf_provenance(out_path, run_dir, config)
    else:  # stl
        # ASCII STL has no portable in-band comment mechanism (strict parsers
        # reject anything but facet/loop/vertex tokens), so STL provenance lives
        # in the download filename (benchmark + timestamped run id) instead.
        write_stl_extrusion(out_path, mesh, densities, extrusion_depth=extrusion_depth, threshold=threshold)
        data = out_path.read_bytes()
    filename = f"{config.name}_{run_dir.name}.{ext}"
    return data, filename, mime
