"""Geometry export for a completed run — SVG / DXF / STL.

Mirrors the CLI ``export`` subcommand (``cli.py``) exactly: rebuild the mesh
from the persisted ``input.json``, load ``density.npy``, and write the chosen
vector/mesh format. Returns the bytes + a download filename + MIME type so the
web layer can stream it as an attachment.

This adds no geometry logic — it reuses ``core.geometry_export`` verbatim.
"""

from __future__ import annotations

from pathlib import Path

from structure_optimizer.core.config import parse_config, validate_config
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
    elif fmt == "dxf":
        write_dxf(out_path, mesh, densities, threshold=threshold)
    else:  # stl
        write_stl_extrusion(out_path, mesh, densities, extrusion_depth=extrusion_depth, threshold=threshold)

    data = out_path.read_bytes()
    filename = f"{config.name}_{run_dir.name}.{ext}"
    return data, filename, mime
