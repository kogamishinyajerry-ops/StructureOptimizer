"""Wave I: external mesh import via meshio (optional dep).

Provides ``MeshSource`` (ABC) + ``MeshioReader`` (concrete) that can load
any mesh format meshio supports (``.msh``, ``.vtk``, ``.vtu``, ``.xdmf``,
``.stl``, ...) and produce a :class:`TriangleMesh` for the linear-elastic
solver in :mod:`structure_optimizer.core.triangle`.

Activate with ``pip install structure-optimizer[mesh]``.

Scope (v1.9):
- Read 2D triangle meshes only.
- Mixed-element meshes (tri + quad) → use first triangle block; warn.
- 3D meshes are not supported (permanent red line: 2D / 2.5D only).
- Writes are out of scope; this is a one-way adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np

from structure_optimizer.core.triangle import TriangleMesh

try:
    import meshio

    _MESHIO_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dep
    _MESHIO_AVAILABLE = False


class MeshSource(ABC):
    """Abstract base: load a triangle mesh from some external source."""

    name: str = "abstract"

    @abstractmethod
    def load(self, path: Path | str) -> TriangleMesh:
        """Read mesh from ``path``, return a TriangleMesh."""


class MeshioReader(MeshSource):
    """Read 2D triangle meshes via meshio.

    Strategy: read all cell blocks, keep the first ``triangle`` block (warn
    if mixed); discard z coordinate if present (project to xy). Returns a
    :class:`TriangleMesh` with the kept nodes + triangle connectivity.
    """

    name = "meshio"

    def load(self, path: Path | str) -> TriangleMesh:
        if not _MESHIO_AVAILABLE:
            raise RuntimeError("meshio is not installed; install structure-optimizer[mesh] to enable .msh/.vtk import")
        mesh = meshio.read(str(path))
        triangles = None
        for block in mesh.cells:
            if block.type == "triangle":
                triangles = np.asarray(block.data, dtype=int)
                break
        if triangles is None or triangles.size == 0:
            raise ValueError(f"no triangle cells found in mesh '{path}'")

        points = np.asarray(mesh.points, dtype=float)
        if points.shape[1] >= 2:
            nodes = points[:, :2].copy()
        else:
            raise ValueError(f"mesh points must have at least 2 components, got shape {points.shape}")

        return TriangleMesh(nodes=nodes, elements=triangles)


def meshio_available() -> bool:
    """Return True if meshio is importable."""
    return _MESHIO_AVAILABLE
