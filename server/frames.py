"""Density-field wire encoding.

The engine stores a flat density array; we reshape to ``(nely, nelx)`` for
display (matching ``OptimizationResult._repr_png_`` and the ``visualization``
PNG path). Values are in ``[0, 1]``; for the wire we quantize to ``uint8`` and
base64-encode — compact, exact enough for a viewport, trivial for the browser
to decode into an ImageData / texture.

Color mapping is left to the client; it mirrors the engine's PNG colormap
(void ``rgb(245,249,251)`` → material ``rgb(12,62,78)`` linear in density) so the
live viewport matches the saved ``density.png``.
"""

from __future__ import annotations

import base64

import numpy as np


def encode_density(densities: np.ndarray, nelx: int, nely: int) -> tuple[list[int], str]:
    """Return ``([nely, nelx], base64(uint8 row-major))`` for a flat density array.

    Element row 0 is the *bottom* of the domain (``mesh.py``: ``y = height*j/nely``
    increases with j). Every engine renderer flips vertically so row 0 lands at the
    visual bottom (``visualization/density_plot.py``, ``gif.py``, ``repr_html``).
    We do the same ``flipud`` here so the live viewport — which draws row 0 at the
    canvas top — matches the saved ``density.png`` exactly.
    """
    grid = np.asarray(densities, dtype=float).reshape((nely, nelx))
    grid = np.flipud(grid)
    quant = np.clip(grid * 255.0 + 0.5, 0, 255).astype(np.uint8)
    payload = base64.b64encode(quant.tobytes()).decode("ascii")
    return [nely, nelx], payload
