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


# -- derivation fixtures (S4.2-S4.5) ------------------------------------------

def spec(**overrides):
    """A print spec pc_face.render_face draws (every field it reads), ASCII."""
    values = {
        "band": "legendary", "name": "Dancer", "title": "Master I", "title_rgb": (85, 216, 70),
        "subtitle": None, "rating": 1650, "pool_rank": 4, "board_rank": 4, "wins": 30, "losses": 9,
        "foil": False, "signed": False, "sign": None, "edition_label": "Edition 1",
        "minted_on": "2026-09-27", "print_short": "#d4c3a1", "top_card": "", "top_card_rgb": None,
    }
    values.update(overrides)
    return values


# A second locale's labels (ASCII): every chip, stat and footer label moves.
LABELS_XX = {
    "pc.signed": "SIGNIERT", "pc.edition": "Ausgabe", "pc.foil": "FOLIE", "pc.foil_short": "FOL",
    "pc.stat.rank": "RANG", "pc.stat.rating": "WERTUNG", "pc.stat.pool": "POOL",
    "pc.stat.board": "TABELLE", "pc.stat.record": "SIEGE/NIEDERLAGEN",
}


def edge_still(level=1):
    """A valid 1180 still (coverage inside the writer's 2-60 % band) whose
    content reaches its outer edge: an 8-pixel border (4 at card, 2 at tile)
    plus a disc. Frames keep their outer 2 pixels clear (S2.5), so a face
    drawn from this still and one drawn from a frame differ along the very
    edge of the window -- the strip a shrunk-window mutant drops (M8)."""
    image = Image.new("RGBA", (2 * EDGE, 2 * EDGE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 2 * EDGE - 1, 2 * EDGE - 1), outline=(40, 90, 200, 255), width=8)
    draw.ellipse((420, 300, 760, 980), fill=(230, 120, 60, 255))
    return png_bytes(image, level)


def edge_frame(t=0.0, level=1):
    """A frame the content checks accept whose content touches the first
    column and row a frame may change (index EDGE_MARGIN, just inside the
    clear band): the dancer plus a one-pixel ring at that index."""
    image = figure(t)
    m = pcm.EDGE_MARGIN
    ImageDraw.Draw(image).rectangle((m, m, EDGE - 1 - m, EDGE - 1 - m), outline=(250, 250, 90, 255), width=1)
    return png_bytes(image, level)


def fake_render(spec_, labels, portrait_png, size):
    """A fast stand-in for pc_face.render_face with its geometry -- a card or
    tile of a fixed pattern, the rig portrait composited over the portrait
    background and reduced by 2 or 4 into the window -- for the encoder tests
    that must not wait on the real renderer (T23, T24). T21 and T22 use the
    real one."""
    import pc_face
    card = size == "card"
    w, h = (pc_face.CARD_W, pc_face.CARD_H) if card else (pc_face.TILE_W, pc_face.TILE_H)
    window = pcm.CARD_WINDOW if card else pcm.TILE_WINDOW
    body = Image.new("RGBA", (w, h), (30, 30, 46, 255))
    draw = ImageDraw.Draw(body)
    for y in range(0, h, 16):
        draw.line((0, y, w, y), fill=(60 + (y % 64), 40, 90, 255))
    draw.text((10, h - 40), str(spec_.get("name", "")) + " " + str(labels.get("pc.edition", "Edition")),
              fill=(240, 240, 240, 255))
    with Image.open(io.BytesIO(portrait_png)) as source:
        source.load()
        fg = source.convert("RGBA")
    over = Image.alpha_composite(Image.new("RGBA", fg.size, pc_face._portrait_bg()), fg)
    body.paste(over.reduce(2 if card else 4), window[:2])
    out = io.BytesIO()
    body.save(out, format="PNG", compress_level=1)
    return out.getvalue()


def noise_frames(count, seed=7, level=1):
    """Frames holding one 230-pixel square of seeded noise (15 % coverage,
    centred, each frame under the 256 KiB frame cap): valid shapes that
    encode to large GIFs, for the size ladder's real overflow."""
    import random
    rnd = random.Random(seed)
    out = []
    for _k in range(count):
        image = blank()
        image.paste(Image.frombytes("RGB", (230, 230), rnd.randbytes(230 * 230 * 3)).convert("RGBA"), (180, 180))
        out.append(png_bytes(image, level))
    return out
