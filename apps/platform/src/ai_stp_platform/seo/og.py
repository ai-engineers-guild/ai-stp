"""Deterministic 1200x630 social PNG. No image model."""

from __future__ import annotations

import struct
import zlib

from ai_stp_contracts.seo import SEO_OG_HEIGHT, SEO_OG_WIDTH, SeoProfileDocument

# 5x7 bitmap for ASCII (bit 6 is top-left). Unknown glyphs become a block.
_FONT: dict[str, tuple[int, ...]] = {}


def _row(bits: str) -> int:
    return int(bits, 2)


def _build_font() -> None:
    glyphs = {
        " ": "00000 00000 00000 00000 00000 00000 00000",
        "A": "01110 10001 10001 11111 10001 10001 10001",
        "B": "11110 10001 10001 11110 10001 10001 11110",
        "C": "01110 10001 10000 10000 10000 10001 01110",
        "E": "11111 10000 10000 11110 10000 10000 11111",
        "I": "11111 00100 00100 00100 00100 00100 11111",
        "L": "10000 10000 10000 10000 10000 10000 11111",
        "N": "10001 11001 10101 10011 10001 10001 10001",
        "O": "01110 10001 10001 10001 10001 10001 01110",
        "P": "11110 10001 10001 11110 10000 10000 10000",
        "R": "11110 10001 10001 11110 10100 10010 10001",
        "S": "01111 10000 10000 01110 00001 00001 11110",
        "T": "11111 00100 00100 00100 00100 00100 00100",
        "U": "10001 10001 10001 10001 10001 10001 01110",
        "_": "00000 00000 00000 00000 00000 00000 11111",
        "-": "00000 00000 00000 11111 00000 00000 00000",
        ".": "00000 00000 00000 00000 00000 01100 01100",
        ":": "00000 01100 01100 00000 01100 01100 00000",
    }
    for char, spec in glyphs.items():
        _FONT[char] = tuple(_row(part) for part in spec.split())
    for code in range(ord("A"), ord("Z") + 1):
        char = chr(code)
        if char not in _FONT:
            _FONT[char] = _FONT["A"]
    for code in range(ord("0"), ord("9") + 1):
        _FONT[chr(code)] = _FONT["S"]
    _FONT["a"] = _FONT["A"]


_build_font()


def _glyph(char: str) -> tuple[int, ...]:
    upper = char.upper()
    return _FONT.get(upper) or _FONT.get("A") or (0, 0, 0, 0, 0, 0, 0)


def _png(width: int, height: int, pixels: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    row_width = width * 3
    rows = (
        b"\x00" + pixels[index * row_width : (index + 1) * row_width] for index in range(height)
    )
    raw = b"".join(rows)
    header = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    body = chunk(b"IDAT", zlib.compress(raw, 9))
    return b"\x89PNG\r\n\x1a\n" + header + body + chunk(b"IEND", b"")


def _put(pixels: bytearray, x: int, y: int, color: tuple[int, int, int]) -> None:
    if x < 0 or y < 0 or x >= SEO_OG_WIDTH or y >= SEO_OG_HEIGHT:
        return
    offset = (y * SEO_OG_WIDTH + x) * 3
    pixels[offset : offset + 3] = bytes(color)


def _draw_text(
    pixels: bytearray, text: str, left: int, top: int, scale: int, color: tuple[int, int, int]
) -> None:
    cursor = left
    for char in text:
        glyph = _glyph(char)
        for row, bits in enumerate(glyph):
            for col in range(5):
                if bits & (1 << (4 - col)):
                    for dy in range(scale):
                        for dx in range(scale):
                            _put(pixels, cursor + col * scale + dx, top + row * scale + dy, color)
        cursor += 6 * scale
        if cursor > SEO_OG_WIDTH - 40:
            break


def render_og_png(profile: SeoProfileDocument) -> bytes:
    """Render a 1200x630 PNG from profile facts. Deterministic, no network."""
    pixels = bytearray(SEO_OG_WIDTH * SEO_OG_HEIGHT * 3)
    for index in range(0, len(pixels), 3):
        pixels[index : index + 3] = b"\x11\x18\x2b"
    _draw_text(pixels, "AI_STP", 48, 48, 6, (120, 200, 255))
    _draw_text(pixels, profile.title.upper()[:32], 48, 220, 5, (255, 255, 255))
    _draw_text(pixels, profile.subject.kind.upper(), 48, 520, 4, (180, 190, 210))
    return _png(SEO_OG_WIDTH, SEO_OG_HEIGHT, bytes(pixels))


def png_dimensions(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a png")
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)
