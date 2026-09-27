"""Synthetic dance-motion fixtures for the pc_motion tests.

A stick dancer drawn with Pillow (well inside the 2-pixel edge band, about
10% coverage), whole frame sequences built from it, hand-made PNG chunks for
the header refusals, and containers in the one accepted layout. Nothing here
is a real capture: the eight-dance corpus the client captures is read from
PC_MOTION_CORPUS_DIR by the tests that need it.
"""
import io
import math
import struct
import zlib

from PIL import Image, ImageDraw

import pc_motion as pcm

EDGE = pcm.FRAME_EDGE
STATIC = "ab" * 32          # a 64-hex still hash for headers


def png_bytes(image, level=1):
    out = io.BytesIO()
    image.save(out, format="PNG", compress_level=level)
    return out.getvalue()


def blank():
    return Image.new("RGBA", (EDGE, EDGE), (0, 0, 0, 0))


def figure(t=0.0, colour=(200, 180, 160, 255), dx=0):
    """The dancer at phase t in [0, 1): body, head and two arms whose angle
    follows sin(2 pi t), so a sequence over one period loops smoothly."""
    image = blank()
    draw = ImageDraw.Draw(image)
    cx = 295 + dx
    draw.ellipse((cx - 60, 230, cx + 60, 470), fill=colour)
    draw.ellipse((cx - 45, 130, cx + 45, 220), fill=colour)
    for side in (-1, 1):
        angle = math.radians(20 + 50 * math.sin(2 * math.pi * t) * side)
        x0, y0 = cx + side * 55, 260
        x1, y1 = x0 + side * 130 * math.cos(angle), y0 - 130 * math.sin(angle)
        draw.line((x0, y0, x1, y1), fill=colour, width=26)
    return image


def smooth_frames(count, level=1):
    return [png_bytes(figure(k / float(count)), level) for k in range(count)]


def block(box, colour):
    """A frame holding one opaque rectangle."""
    image = blank()
    ImageDraw.Draw(image).rectangle(box, fill=colour)
    return image


def container(dance, frames, static=STATIC, recipe=pcm.MOTION_RECIPE, ms=None, count=None):
    row = pcm.table_row(recipe, dance) or (50, len(frames))
    header = pcm.header_text(dance, recipe, row[1] if count is None else count,
                             row[0] if ms is None else ms, static)
    return pcm.build_container(header, frames)


def chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def raw_png(width, height, depth=8, colour=6, interlace=0):
    """A structurally valid PNG with any IHDR: its IDAT is a zlib stream of
    zero bytes, enough for the chunk walk and the IHDR read (the checks that
    refuse these never decode a pixel)."""
    ihdr = struct.pack(">IIBBBBB", width, height, depth, colour, 0, 0, interlace)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(b"\x00" * 64)) + chunk(b"IEND", b""))


def with_chunk_after_ihdr(png, kind, data):
    """png with one more chunk right after IHDR (8 magic + 25 IHDR bytes)."""
    return png[:33] + chunk(kind, data) + png[33:]


_ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def decodable_png(image, depth=8, interlace=0):
    """A DECODABLE PNG of an RGBA image with the given depth (8 or 16) and
    interlace (0, or 1 = Adam7), written by hand: Pillow reads both, so a
    frame like this is refused only by the IHDR comparison itself."""
    width, height = image.size
    px = image.tobytes()
    size = 4 * (2 if depth == 16 else 1)

    def pixel(x, y):
        raw = px[(y * width + x) * 4:(y * width + x) * 4 + 4]
        return bytes(b for v in raw for b in ((v, v) if depth == 16 else (v,)))

    rows = []
    passes = _ADAM7 if interlace else ((0, 0, 1, 1),)
    for x0, y0, dx, dy in passes:
        for y in range(y0, height, dy):
            line = [pixel(x, y) for x in range(x0, width, dx)]
            if line:
                rows.append(b"\x00" + b"".join(line))
    assert all(len(r) == 1 + size * len(range(p[0], width, p[2]))
               for r, p in zip(rows[:1], passes[:1]))
    ihdr = struct.pack(">IIBBBBB", width, height, depth, 6, 0, 0, interlace)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))
