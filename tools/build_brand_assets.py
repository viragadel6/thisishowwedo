from __future__ import annotations

import argparse
import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "exact_formula_search" / "web" / "static"

BACKGROUND_TOP = (7, 11, 24)
BACKGROUND_BOTTOM = (3, 5, 12)
GLOW_COLOR = (56, 189, 248)
GLOW_CENTER = (0.5, 0.42)
GLOW_RADIUS = 0.62
GLOW_STRENGTH = 0.3
GRADIENT_START = (125, 211, 252)
GRADIENT_MIDDLE = (167, 139, 250)
GRADIENT_END = (240, 171, 252)
GLYPH_COLOR = (248, 250, 252)
LOW_RES_GRID = 72
ICON_SIZES = (32, 76, 120, 152, 180, 192, 512)
SPLASH_SIZES = (
    (640, 1136),
    (750, 1334),
    (828, 1792),
    (1125, 2436),
    (1170, 2532),
    (1290, 2796),
    (1536, 2048),
    (1668, 2388),
    (2048, 2732),
    (2732, 2732),
)
GLYPH_SEGMENTS = (
    ((0.30, 0.83), (0.52, 0.21)),
    ((0.435, 0.50), (0.73, 0.83)),
)


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def mix(first: tuple[int, int, int], second: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    ratio = clamp(amount, 0.0, 1.0)
    return (
        int(round(first[0] + (second[0] - first[0]) * ratio)),
        int(round(first[1] + (second[1] - first[1]) * ratio)),
        int(round(first[2] + (second[2] - first[2]) * ratio)),
    )


def gradient_color(amount: float) -> tuple[int, int, int]:
    ratio = clamp(amount, 0.0, 1.0)
    if ratio < 0.5:
        return mix(GRADIENT_START, GRADIENT_MIDDLE, ratio * 2.0)
    return mix(GRADIENT_MIDDLE, GRADIENT_END, (ratio - 0.5) * 2.0)


def background_pixel(x: float, y: float) -> tuple[int, int, int]:
    base = mix(BACKGROUND_TOP, BACKGROUND_BOTTOM, y)
    distance = math.hypot(x - GLOW_CENTER[0], (y - GLOW_CENTER[1]) * 1.18)
    falloff = max(0.0, 1.0 - distance / GLOW_RADIUS)
    return mix(base, GLOW_COLOR, GLOW_STRENGTH * falloff * falloff)


def distance_to_segment(px: float, py: float, first: tuple[float, float], second: tuple[float, float]) -> float:
    ax, ay = first
    bx, by = second
    dx = bx - ax
    dy = by - ay
    length_squared = dx * dx + dy * dy
    if length_squared <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = clamp(((px - ax) * dx + (py - ay) * dy) / length_squared, 0.0, 1.0)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def glyph_coverage(x: float, y: float, half_width: float, feather: float) -> float:
    distance = min(distance_to_segment(x, y, start, end) for start, end in GLYPH_SEGMENTS)
    return clamp((half_width - distance) / feather, 0.0, 1.0)


def rounded_square_alpha(x: float, y: float, radius: float, feather: float) -> float:
    dx = abs(x - 0.5)
    dy = abs(y - 0.5)
    corner_x = max(dx - (0.5 - radius), 0.0)
    corner_y = max(dy - (0.5 - radius), 0.0)
    signed = math.hypot(corner_x, corner_y) - radius
    return clamp(0.5 - signed / feather, 0.0, 1.0)


def tile_color(x: float, y: float) -> tuple[int, int, int]:
    base = gradient_color(clamp(x * 0.72 + y * 0.38, 0.0, 1.0))
    highlight = clamp(1.0 - math.hypot(x - 0.3, y - 0.24) * 1.7, 0.0, 1.0) * 0.22
    return mix(base, (255, 255, 255), highlight)


def tile_pixel(x: float, y: float, feather: float) -> tuple[int, int, int, int]:
    alpha = rounded_square_alpha(x, y, 0.235, feather)
    if alpha <= 0.0:
        return (0, 0, 0, 0)
    glyph_feather = max(feather, 1.0 / 512.0)
    coverage = glyph_coverage(x, y, 0.058, glyph_feather)
    color = mix(tile_color(x, y), GLYPH_COLOR, coverage)
    return (color[0], color[1], color[2], int(round(alpha * 255)))


def encode_png(width: int, height: int, rows: list[bytes], alpha: bool = True) -> bytes:
    color_type = 6 if alpha else 2
    raw = bytearray()
    for row in rows:
        raw.append(0)
        raw.extend(row)
    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def render_icon(size: int) -> bytes:
    feather = 1.6 / size
    rows: list[bytes] = []
    for y in range(size):
        buffer = bytearray()
        for x in range(size):
            red, green, blue, alpha = tile_pixel((x + 0.5) / size, (y + 0.5) / size, feather)
            buffer.extend((red, green, blue, alpha))
        rows.append(bytes(buffer))
    return encode_png(size, size, rows)


def sample_background(grid: int) -> list[bytes]:
    rows: list[bytes] = []
    for row in range(grid):
        buffer = bytearray()
        for column in range(grid):
            red, green, blue = background_pixel((column + 0.5) / grid, (row + 0.5) / grid)
            buffer.extend((red, green, blue))
        rows.append(bytes(buffer))
    return rows


def expand_row(row: bytes, source_width: int, target_width: int) -> bytes:
    if target_width == source_width:
        return row
    parts: list[bytes] = []
    for index in range(source_width):
        start = index * 3
        begin = (target_width * index) // source_width
        end = (target_width * (index + 1)) // source_width
        if end > begin:
            parts.append(row[start : start + 3] * (end - begin))
    return b"".join(parts)


def render_splash(width: int, height: int) -> bytes:
    low = sample_background(LOW_RES_GRID)
    mark_half = max(24.0, min(width, height) * 0.115)
    mark_left = width * 0.5 - mark_half
    mark_top = height * 0.46 - mark_half
    mark_size = mark_half * 2.0
    feather = 1.6 / mark_size
    left_index = max(0, int(math.floor(mark_left)))
    right_index = min(width, int(math.ceil(mark_left + mark_size)) + 1)
    rows: list[bytes] = []
    for y in range(height):
        source_row = low[min(LOW_RES_GRID - 1, (y * LOW_RES_GRID) // height)]
        row = bytearray(expand_row(source_row, LOW_RES_GRID, width))
        relative_y = (y + 0.5 - mark_top) / mark_size
        if -0.01 <= relative_y <= 1.01:
            for x in range(left_index, right_index):
                relative_x = (x + 0.5 - mark_left) / mark_size
                red, green, blue, alpha = tile_pixel(relative_x, relative_y, feather)
                if alpha <= 0:
                    continue
                index = x * 3
                blended = mix((row[index], row[index + 1], row[index + 2]), (red, green, blue), alpha / 255.0)
                row[index] = blended[0]
                row[index + 1] = blended[1]
                row[index + 2] = blended[2]
        rows.append(bytes(row))
    return encode_png(width, height, rows, alpha=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the brand icons and splash images of the exact formula search interface")
    parser.add_argument("--static", default=str(STATIC), help="static asset directory")
    arguments = parser.parse_args()
    static_root = Path(arguments.static)
    icons = static_root / "icons"
    splash = static_root / "splash"
    icons.mkdir(parents=True, exist_ok=True)
    splash.mkdir(parents=True, exist_ok=True)
    for size in ICON_SIZES:
        if size == 32:
            target = icons / "favicon-32.png"
        elif size in (76, 120, 152, 180):
            target = icons / ("apple-touch-icon-" + str(size) + ".png")
        else:
            target = icons / ("icon-" + str(size) + ".png")
        target.write_bytes(render_icon(size))
    for width, height in SPLASH_SIZES:
        target = splash / ("splash-" + str(width) + "x" + str(height) + ".png")
        target.write_bytes(render_splash(width, height))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
