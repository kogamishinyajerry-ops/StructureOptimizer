from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np


def write_grayscale_png(path: Path, pixels: np.ndarray) -> None:
    array = np.asarray(pixels, dtype=np.uint8)
    if array.ndim != 2:
        raise ValueError("grayscale PNG expects a 2D array")
    height, width = array.shape
    raw = b"".join(b"\x00" + array[y].tobytes() for y in range(height))
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(raw, level=9))
    png += _chunk(b"IEND", b"")
    path.write_bytes(png)


def write_rgb_png(path: Path, pixels: np.ndarray) -> None:
    array = np.asarray(pixels, dtype=np.uint8)
    if array.ndim != 3 or array.shape[2] != 3:
        raise ValueError("RGB PNG expects an H x W x 3 array")
    height, width, _ = array.shape
    raw = b"".join(b"\x00" + array[y].tobytes() for y in range(height))
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(raw, level=9))
    png += _chunk(b"IEND", b"")
    path.write_bytes(png)


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
