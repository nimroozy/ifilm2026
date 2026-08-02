"""Local synthetic PNG placeholders (no copyrighted artwork)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from app.core.config import Settings
from app.services.storage import ensure_artwork_layout

# Minimal 5x7 uppercase glyph set for title text on placeholders.
_FONT: dict[str, list[str]] = {
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01110"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10001", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10001", "10101", "11011", "10001"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    "'": ["00100", "00100", "01000", "00000", "00000", "00000", "00000"],
}


def _parse_hex_color(color: str) -> tuple[int, int, int]:
    text = color.strip().lstrip("#")
    if len(text) != 6:
        return 26, 58, 92
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_rgb_png(path: Path, width: int, height: int, rgb: tuple[int, int, int], title: str) -> None:
    """Write a solid-color PNG with a simple bitmap title overlay."""
    r, g, b = rgb
    # Slightly lighter text color for contrast.
    tr, tg, tb = min(255, r + 140), min(255, g + 140), min(255, b + 140)
    pixels = bytearray()
    # Pre-render title lines (max 2).
    words = title.upper().replace("_", " ")
    lines: list[str] = []
    current = ""
    for word in words.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > 18 and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    lines = lines[:2]

    scale = 3 if width >= 600 else 2
    glyph_w, glyph_h = 5 * scale, 7 * scale
    gap = scale
    line_gap = 4 * scale

    def blit_text(row0: int, text: str) -> set[tuple[int, int]]:
        on: set[tuple[int, int]] = set()
        total_w = len(text) * (glyph_w + gap) - gap
        x0 = max(0, (width - total_w) // 2)
        y0 = row0
        for idx, ch in enumerate(text):
            glyph = _FONT.get(ch, _FONT[" "])
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit != "1":
                        continue
                    for dy in range(scale):
                        for dx in range(scale):
                            x = x0 + idx * (glyph_w + gap) + gx * scale + dx
                            y = y0 + gy * scale + dy
                            if 0 <= x < width and 0 <= y < height:
                                on.add((x, y))
        return on

    text_pixels: set[tuple[int, int]] = set()
    block_h = len(lines) * glyph_h + max(0, len(lines) - 1) * line_gap
    start_y = max(0, (height - block_h) // 2)
    for i, line in enumerate(lines):
        text_pixels |= blit_text(start_y + i * (glyph_h + line_gap), line)

    for y in range(height):
        pixels.append(0)  # filter none
        for x in range(width):
            if (x, y) in text_pixels:
                pixels.extend((tr, tg, tb))
            else:
                # Soft vertical gradient.
                factor = y / max(height - 1, 1)
                pixels.extend(
                    (
                        max(0, int(r * (1.0 - 0.25 * factor))),
                        max(0, int(g * (1.0 - 0.25 * factor))),
                        max(0, int(b * (1.0 - 0.15 * factor))),
                    )
                )

    raw = zlib.compress(bytes(pixels), level=9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", raw) + _png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def ensure_placeholder_pair(
    settings: Settings,
    *,
    slug: str,
    title: str,
    color: str,
    public_base_url: str,
) -> tuple[str, str, list[str]]:
    """Create poster/backdrop PNGs; return (poster_url, backdrop_url, relative_paths)."""
    ensure_artwork_layout()
    root = Path(settings.artwork_root).resolve()
    rgb = _parse_hex_color(color)
    # Slugs are already demo-prefixed (e.g. demo-kabul-nights); do not add another demo-.
    file_stem = slug if slug.startswith("demo-") else f"demo-{slug}"
    poster_rel = f"posters/{file_stem}.png"
    backdrop_rel = f"backdrops/{file_stem}.png"
    write_rgb_png(root / poster_rel, 300, 450, rgb, title)
    write_rgb_png(root / backdrop_rel, 1280, 720, rgb, title)
    base = public_base_url.rstrip("/")
    return f"{base}/artwork/{poster_rel}", f"{base}/artwork/{backdrop_rel}", [poster_rel, backdrop_rel]
