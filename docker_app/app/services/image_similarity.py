from __future__ import annotations

import math
from pathlib import Path

from PIL import Image


FINGERPRINT_VERSION = "v1"
HASH_SIZE = 256


def image_fingerprint(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            average_color = rgb.resize((1, 1), Image.Resampling.LANCZOS).getpixel((0, 0))
            gray = rgb.convert("L").resize((17, 16), Image.Resampling.LANCZOS)
            pixels = list(gray.getdata())
    except Exception:
        return None
    if len(pixels) != 17 * 16:
        return None
    bits = []
    gray_values = []
    for row in range(16):
        offset = row * 17
        row_values = pixels[offset : offset + 17]
        gray_values.extend(row_values)
        bits.extend(1 if row_values[column] > row_values[column + 1] else 0 for column in range(16))
    bit_string = "".join(str(bit) for bit in bits)
    mean = sum(gray_values) / len(gray_values)
    variance = sum((value - mean) ** 2 for value in gray_values) / len(gray_values)
    contrast = max(0, min(255, round(math.sqrt(variance))))
    color_hex = "".join(f"{max(0, min(255, int(channel))):02x}" for channel in average_color[:3])
    return f"{FINGERPRINT_VERSION}:{int(bit_string, 2):064x}:{color_hex}:{contrast:02x}"


def parse_fingerprint(value: str | None) -> tuple[int, tuple[int, int, int], int] | None:
    parts = str(value or "").split(":")
    if len(parts) != 4 or parts[0] != FINGERPRINT_VERSION:
        return None
    hash_hex, color_hex, contrast_hex = parts[1:]
    if len(hash_hex) != 64 or len(color_hex) != 6 or len(contrast_hex) != 2:
        return None
    try:
        hash_bits = int(hash_hex, 16)
        color = tuple(int(color_hex[index : index + 2], 16) for index in (0, 2, 4))
        contrast = int(contrast_hex, 16)
    except ValueError:
        return None
    return hash_bits, color, contrast


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def color_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(3)))
