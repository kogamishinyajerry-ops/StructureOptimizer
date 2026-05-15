from __future__ import annotations

from pathlib import Path

import numpy as np

from structure_optimizer.core.mesh import StructuredMesh
from structure_optimizer.visualization.png import write_rgb_png


def write_density_png(path: Path, mesh: StructuredMesh, densities: np.ndarray, scale: int = 8) -> None:
    write_rgb_png(path, density_pixels(mesh, densities, scale=scale))


def density_pixels(mesh: StructuredMesh, densities: np.ndarray, scale: int = 8) -> np.ndarray:
    field = np.asarray(densities, dtype=float).reshape(mesh.nely, mesh.nelx)
    field = np.flipud(field)
    material = np.array([12, 62, 78], dtype=float)
    void = np.array([245, 249, 251], dtype=float)
    field = np.clip(field, 0.0, 1.0)
    rgb = void[None, None, :] * (1.0 - field[:, :, None]) + material[None, None, :] * field[:, :, None]
    rgb = np.uint8(np.clip(rgb, 0, 255))
    if scale > 1:
        rgb = np.repeat(np.repeat(rgb, scale, axis=0), scale, axis=1)
    return rgb


def write_baseline_png(path: Path, mesh: StructuredMesh, scale: int = 8) -> None:
    densities = np.ones(mesh.elements.shape[0], dtype=float)
    densities[~mesh.design_mask] = 0.0
    pixels = density_pixels(mesh, densities, scale=scale)
    _draw_border(pixels)
    write_rgb_png(path, pixels)


def write_loadcase_png(path: Path, mesh: StructuredMesh, boundary_conditions: list[dict], loads: list[dict], scale: int = 8) -> None:
    densities = np.ones(mesh.elements.shape[0], dtype=float)
    densities[~mesh.design_mask] = 0.0
    pixels = density_pixels(mesh, densities, scale=scale)
    _draw_border(pixels)
    for bc in boundary_conditions:
        for node in mesh.selector_nodes(bc["selector"]):
            x, y = _node_to_pixel(mesh, node, scale, pixels.shape[0])
            _draw_square(pixels, x, y, 6, (0, 92, 170))
        _draw_support_band(pixels, mesh, bc["selector"], scale)
    for load in loads:
        for node in mesh.selector_nodes(load["selector"]):
            x, y = _node_to_pixel(mesh, node, scale, pixels.shape[0])
            x = min(max(x, 24), pixels.shape[1] - 24)
            y = min(max(y, 24), pixels.shape[0] - 24)
            fy = float(load.get("fy", 0.0))
            fx = float(load.get("fx", 0.0))
            if abs(fy) >= abs(fx):
                if fy < 0:
                    _draw_arrow(pixels, x, y - 34, x, y + 18, (210, 44, 44))
                else:
                    _draw_arrow(pixels, x, y + 34, x, y - 18, (210, 44, 44))
            else:
                if fx > 0:
                    _draw_arrow(pixels, x - 34, y, x + 18, y, (210, 44, 44))
                else:
                    _draw_arrow(pixels, x + 34, y, x - 18, y, (210, 44, 44))
    write_rgb_png(path, pixels)


def _node_to_pixel(mesh: StructuredMesh, node_id: int, scale: int, image_height: int) -> tuple[int, int]:
    x, y = mesh.nodes[node_id]
    px = int(round(x / mesh.width * mesh.nelx * scale))
    py = image_height - 1 - int(round(y / mesh.height * mesh.nely * scale))
    return px, py


def _draw_border(pixels: np.ndarray) -> None:
    pixels[0:3, :, :] = (40, 52, 61)
    pixels[-3:, :, :] = (40, 52, 61)
    pixels[:, 0:3, :] = (40, 52, 61)
    pixels[:, -3:, :] = (40, 52, 61)


def _draw_support_band(pixels: np.ndarray, mesh: StructuredMesh, selector: str, scale: int) -> None:
    color = (0, 92, 170)
    if selector == "left_edge":
        pixels[:, 0 : max(8, scale), :] = color
        for y in range(0, pixels.shape[0], max(8, scale)):
            _draw_line(pixels, 0, y, max(16, 2 * scale), min(pixels.shape[0] - 1, y + max(16, 2 * scale)), color)
    elif selector == "right_edge":
        pixels[:, -max(8, scale) :, :] = color
    elif selector == "top_edge":
        pixels[0 : max(8, scale), :, :] = color
    elif selector == "bottom_edge":
        pixels[-max(8, scale) :, :, :] = color


def _draw_square(pixels: np.ndarray, x: int, y: int, radius: int, color: tuple[int, int, int]) -> None:
    y0, y1 = max(0, y - radius), min(pixels.shape[0], y + radius + 1)
    x0, x1 = max(0, x - radius), min(pixels.shape[1], x + radius + 1)
    pixels[y0:y1, x0:x1, :] = color


def _draw_arrow(pixels: np.ndarray, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
    _draw_line(pixels, x0, y0, x1, y1, color)
    _draw_square(pixels, x1, y1, 7, color)


def _draw_line(pixels: np.ndarray, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        if 0 <= y0 < pixels.shape[0] and 0 <= x0 < pixels.shape[1]:
            pixels[max(0, y0 - 1):min(pixels.shape[0], y0 + 2), max(0, x0 - 1):min(pixels.shape[1], x0 + 2), :] = color
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
