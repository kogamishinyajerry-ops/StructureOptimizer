from __future__ import annotations

from pathlib import Path

import numpy as np

from structure_optimizer.core.mesh import StructuredMesh


def write_density_gif(
    path: Path,
    mesh: StructuredMesh,
    density_frames: list[np.ndarray],
    scale: int = 6,
    delay_cs: int = 18,
) -> None:
    frames = [_indexed_density_frame(mesh, frame, scale=scale) for frame in density_frames]
    if not frames:
        raise ValueError("at least one frame is required")
    height, width = frames[0].shape
    data = bytearray()
    data += b"GIF89a"
    data += width.to_bytes(2, "little") + height.to_bytes(2, "little")
    data += bytes([0xF7, 0x00, 0x00])
    for value in range(256):
        t = value / 255.0
        material = (12, 62, 78)
        void = (245, 249, 251)
        data += bytes(int(material[i] * (1.0 - t) + void[i] * t) for i in range(3))
    data += b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"
    for frame in frames:
        data += b"\x21\xf9\x04\x04" + delay_cs.to_bytes(2, "little") + b"\x00\x00"
        data += b"\x2c\x00\x00\x00\x00" + width.to_bytes(2, "little") + height.to_bytes(2, "little") + b"\x00"
        data += _gif_image_data(frame.reshape(-1).tolist())
    data += b"\x3b"
    path.write_bytes(bytes(data))


def _indexed_density_frame(mesh: StructuredMesh, densities: np.ndarray, scale: int) -> np.ndarray:
    field = np.asarray(densities, dtype=float).reshape(mesh.nely, mesh.nelx)
    field = np.flipud(field)
    pixels = np.uint8(np.clip(255.0 * (1.0 - field), 0, 255))
    if scale > 1:
        pixels = np.repeat(np.repeat(pixels, scale, axis=0), scale, axis=1)
    return pixels


def _gif_image_data(pixels: list[int]) -> bytes:
    min_code_size = 8
    codes = _lzw_codes(pixels, min_code_size=min_code_size)
    packed = _pack_codes(codes)
    blocks = bytearray([min_code_size])
    for idx in range(0, len(packed), 255):
        chunk = packed[idx : idx + 255]
        blocks.append(len(chunk))
        blocks += chunk
    blocks.append(0)
    return bytes(blocks)


def _lzw_codes(pixels: list[int], min_code_size: int) -> list[tuple[int, int]]:
    clear = 1 << min_code_size
    end = clear + 1
    next_code = end + 1
    code_size = min_code_size + 1
    dictionary = {(i,): i for i in range(clear)}
    codes: list[tuple[int, int]] = [(clear, code_size)]
    current = (pixels[0],)
    for pixel in pixels[1:]:
        candidate = (*current, pixel)
        if candidate in dictionary:
            current = candidate
            continue
        codes.append((dictionary[current], code_size))
        if next_code < 4096:
            dictionary[candidate] = next_code
            next_code += 1
            if next_code == (1 << code_size) and code_size < 12:
                code_size += 1
        else:
            codes.append((clear, code_size))
            dictionary = {(i,): i for i in range(clear)}
            next_code = end + 1
            code_size = min_code_size + 1
        current = (pixel,)
    codes.append((dictionary[current], code_size))
    codes.append((end, code_size))
    return codes


def _pack_codes(codes: list[tuple[int, int]]) -> bytes:
    output = bytearray()
    accumulator = 0
    bits = 0
    for code, size in codes:
        accumulator |= code << bits
        bits += size
        while bits >= 8:
            output.append(accumulator & 0xFF)
            accumulator >>= 8
            bits -= 8
    if bits:
        output.append(accumulator & 0xFF)
    return bytes(output)
