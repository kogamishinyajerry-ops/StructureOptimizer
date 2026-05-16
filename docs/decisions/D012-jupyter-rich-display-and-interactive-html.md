# D012 — Jupyter rich display + interactive demo HTML

- **Status**: accepted
- **Date**: 2026-05-16
- **Wave**: Q (v2.6.0)

## Context

The v3.x rubric §5 user-面 dimension has 4 remaining points after Wave O:

- §5.3 (2 pts): Jupyter rich display (`_repr_html_` / `_repr_png_`) on
  the main result dataclasses
- §5.4 (2 pts): Interactive review HTML upgrade (toggle / pan / zoom)

Up to v2.5, `OptimizationResult` rendered as the default
`OptimizationResult(densities=array(...), metrics=[...], ...)` dump in a
JupyterLab cell — overwhelming and useless. The static `demo.html` had
no interactivity beyond browser zoom.

## Decision

### 1. `_repr_html_` on result dataclasses (§5.3)

Added to:
- `OptimizationResult` (quad SIMP)
- `TriangleOptimizationResult` (Wave M triangle SIMP)
- `FEMResult` (single linear-elastic solve)
- `BenchmarkConfig` (top-level config)

Each method delegates to a helper in `structure_optimizer/core/repr_html.py`
(import-time lazy — only loaded when a notebook actually displays a
result). Returns a small HTML table with the most important scalars +
clear color-coded heading.

### 2. `_repr_png_` on `OptimizationResult` (§5.3)

To render a PNG we need the mesh shape (densities is flat), so
`OptimizationResult` gained a `mesh_shape: tuple[int, int] = (0, 0)`
field. Both `simp.run_simp` and `beso.run_beso` now pass
`(mesh.nelx, mesh.nely)`. When `mesh_shape == (0, 0)` (e.g., a downstream
caller constructed `OptimizationResult` directly without setting it),
`_repr_png_` returns `None` instead of raising — Jupyter falls back to
`_repr_html_` only.

The PNG encoder is pure-NumPy + zlib (already used by
`visualization/write_density_png`); we re-implemented it here with a
small `_grayscale_png_bytes(pixels)` helper that emits IHDR + IDAT +
IEND chunks plus the 8-byte PNG signature. No Pillow / no matplotlib.

### 3. Interactive demo HTML (§5.4)

`generate_demo_html` now emits:

- **Toggle controls** (`<input type="checkbox" data-toggle="...">`) for
  the three side-by-side images (baseline / loadcase / density). JS
  hides/shows the matching `<div class="toggleable-image" data-key="...">`.
- **Pan/zoom stage** wrapping the optimized density image. Mouse wheel
  zooms (clamped to 0.5×–8×); pointer-drag pans. Plus three control
  buttons (−, 100%, +) for keyboard-only / touch users.
- **Inline `<script>` block** at end of body — vanilla JS, no external
  dependencies, no jQuery, ~50 LOC. Stays consistent with our
  "no-build-step, single static HTML" red line.

CSS for the panzoom stage uses `transform-origin: 0 0` so panning math
stays simple (translate(x, y) scale(s) order, no inverse compensation).

## Why no Pillow / no matplotlib for PNG

The same reason the entire project sticks to NumPy-only at runtime:
adding a PNG encoder dep at the **runtime** layer would break the v1.x
red line. zlib is in stdlib; PNG chunk format is small. Wave J already
established this pattern for the SVG/DXF/STL geometry exports.

## Why vanilla JS for the demo HTML

Adding a JS framework (Alpine, htmx, etc.) would force a build step or
network fetch. The demo is meant to be a **single self-contained HTML
file** that opens locally and works offline forever — same constraint as
the entire project. ~50 LOC of vanilla JS does what we need.

## Limitations / not in scope

1. **`_repr_png_` only on quad `OptimizationResult`** — Triangle SIMP
   has unstructured connectivity; rendering it as a PNG needs polygon
   rasterization, which isn't a small zlib helper. `TriangleOptimizationResult`
   gets `_repr_html_` only. Future wave can add a triangle-aware PNG
   encoder if real users want it.
2. **Demo HTML pan/zoom is for the optimized density image only** —
   baseline/loadcase images don't get panzoom because they're typically
   smaller and less interesting. Could be extended trivially if needed.
3. **No JupyterLab widget integration** — no `ipywidgets` dependency
   for live interactive dashboards. Out of scope; the current
   `_repr_html_` is static rendering, not reactive.
4. **No SVG output for vector zoom** — could be a nicer pan/zoom
   target than the rasterized PNG, but matches Wave J: SVG export is
   for geometry-boundary, not density field.

## Files added / changed

- `structure_optimizer/core/repr_html.py` (NEW, ~200 LOC)
- `structure_optimizer/core/simp.py` — `OptimizationResult.mesh_shape`,
  `_repr_html_`, `_repr_png_` methods
- `structure_optimizer/core/beso.py` — passes `mesh_shape=(nelx, nely)`
  to `OptimizationResult`
- `structure_optimizer/core/triangle_simp.py` — `_repr_html_` on
  `TriangleOptimizationResult`
- `structure_optimizer/core/fem2d.py` — `_repr_html_` on `FEMResult`
- `structure_optimizer/core/config.py` — `_repr_html_` on `BenchmarkConfig`
- `structure_optimizer/core/demo.py` — toolbar + panzoom stage + JS
- `tests/test_repr_html_and_interactive.py` (NEW, 10 tests)

## Coverage

- `repr_html.py`: ~95% (the `write_png_to_buffer` convenience wrapper is
  intended for downstream users, not exercised in tests)
- `simp.py`: 100%
- `triangle_simp.py`: 100%
- `fem2d.py`: 99.1%
- `config.py`: ~86% (existing baseline)

## References

- PNG format spec (RFC 2083) for the chunk encoding (`IHDR`, `IDAT`,
  `IEND`, CRC32). zlib for DEFLATE compression.
- Jupyter `_repr_html_` / `_repr_png_` protocol — IPython's
  formatters.py picks the highest-priority `_repr_*_` method present
  on the object.
