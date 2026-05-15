from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np

from structure_optimizer.core.simp import IterationMetric
from structure_optimizer.visualization.png import write_grayscale_png


def write_convergence_png(
    path: Path, metrics: list[IterationMetric] | list[dict], width: int = 640, height: int = 360
) -> None:
    canvas = np.full((height, width), 255, dtype=np.uint8)
    _draw_axes(canvas)
    values = [_value(metric, "compliance") for metric in metrics]
    if len(values) >= 2:
        points = _scale_points(values, width, height)
        for start, end in itertools.pairwise(points):
            _draw_line(canvas, start, end, color=40)
    write_grayscale_png(path, canvas)


def _value(metric: IterationMetric | dict, name: str) -> float:
    if isinstance(metric, dict):
        return float(metric[name])
    return float(getattr(metric, name))


def _draw_axes(canvas: np.ndarray) -> None:
    h, w = canvas.shape
    canvas[h - 35 : h - 32, 45 : w - 20] = 0
    canvas[20 : h - 32, 45:48] = 0


def _scale_points(values: list[float], width: int, height: int) -> list[tuple[int, int]]:
    left, right = 50, width - 25
    top, bottom = 25, height - 40
    lo, hi = min(values), max(values)
    span = hi - lo if hi != lo else 1.0
    points = []
    for idx, value in enumerate(values):
        x = left + int((right - left) * idx / max(1, len(values) - 1))
        y = bottom - int((bottom - top) * (value - lo) / span)
        points.append((x, y))
    return points


def _draw_line(canvas: np.ndarray, start: tuple[int, int], end: tuple[int, int], color: int) -> None:
    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        if 0 <= y0 < canvas.shape[0] and 0 <= x0 < canvas.shape[1]:
            canvas[max(0, y0 - 1) : min(canvas.shape[0], y0 + 2), max(0, x0 - 1) : min(canvas.shape[1], x0 + 2)] = color
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
