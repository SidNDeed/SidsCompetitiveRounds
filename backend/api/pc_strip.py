"""Player Cards composites for the Discord reveal: one opened pack's five
tiles in one row (the /pack strip) and one binder page's ten in a 5 x 2 grid
(the /binder page).

This module draws no text and loads no font and no shaper. It pastes tiles
pc_face.render_face already produced at size "tile" (375 x 525), and the card
back reduced the way render_face reduces its own assets; a discarded print's
tile is stamped with a flat scrim and one diagonal bar, Pillow primitives
only. It is deliberately NOT part of pc_face.py: renderer_fingerprint() hashes
that module's source and every .png under its assets path, so a change there
would re-key every face in every locale. What keys a composite is
STRIP_COMPOSITOR_VERSION, the layout constants below and the ordered per-slot
tokens, all inside composite_digest().

Every name bound here is unique across backend/api, imports included: the
route-manifest gate resolves a name a route uses against every module, so a
new binding that shared a name with an existing one would re-fingerprint the
routes that use that name.
"""
import functools as _strip_functools
import hashlib as _strip_hashlib
import io as _strip_io
import os as _strip_os

from PIL import Image as _StripImage
from PIL import ImageDraw as _StripDraw

import pc_face as _strip_face

# Bump when the pixels a composite draws change for unchanged inputs (the
# stamp, the paste, the back's treatment): it is the first digest input.
STRIP_COMPOSITOR_VERSION = 1
STRIP_MARGIN = 12
STRIP_GUTTER = 12
STRIP_COLS = 5
STRIP_GRID_ROWS = 2
# The discarded stamp: the client's warn colour (PlayerCardsUI C_WARN) over a
# flat scrim.
STRIP_WARN_RGB = (255, 217, 77)
STRIP_SCRIM_RGBA = (0, 0, 0, 110)


class StripCompositeTooLarge(Exception):
    """The encoded composite exceeds the byte cap it was composed under."""


def strip_origin(col, row):
    """(x, y) of the tile at 1-based column `col` and row `row` - the one
    formula every paste position comes from:
    x = margin + (col - 1) * (TILE_W + gutter), y likewise with TILE_H."""
    return (STRIP_MARGIN + (col - 1) * (_strip_face.TILE_W + STRIP_GUTTER),
            STRIP_MARGIN + (row - 1) * (_strip_face.TILE_H + STRIP_GUTTER))


def strip_canvas_size(cols, rows):
    """(width, height) of a cols x rows composite: margin, then one tile and
    one gutter per cell - so the last gutter is the right and bottom margin."""
    return (STRIP_MARGIN + cols * (_strip_face.TILE_W + STRIP_GUTTER),
            STRIP_MARGIN + rows * (_strip_face.TILE_H + STRIP_GUTTER))


def strip_paste_boxes(cols, rows):
    """The paste rectangles (x0, y0, x1, y1) in paste order: row by row, left
    to right, so the cell at 1-based position p is box p - 1."""
    boxes = []
    for row in range(1, rows + 1):
        for col in range(1, cols + 1):
            x, y = strip_origin(col, row)
            boxes.append((x, y, x + _strip_face.TILE_W, y + _strip_face.TILE_H))
    return boxes


@_strip_functools.lru_cache(maxsize=4)
def _strip_back_at(assets_dir):
    with _StripImage.open(_strip_os.path.join(assets_dir, "Back.png")) as source:
        source.load()
        image = source.copy()
    return image.reduce(2).convert("RGBA")


def strip_back_tile():
    """The card back at tile size: the bundle's Back.png (the file the face
    back route serves), reduced and converted exactly as render_face treats
    its own tile assets - open, copy, reduce(2), convert("RGBA") - never
    render_back(), which draws only at card size and would overrun a cell."""
    return _strip_back_at(_strip_face.ASSETS_DIR).copy()


def _stamp_discarded(tile):
    """A discarded print's tile: a flat scrim and one diagonal bar in the warn
    colour over the tile's own pixels, clipped to the tile's alpha so the
    card's rounded corners stay transparent."""
    width, height = tile.size
    overlay = _StripImage.new("RGBA", (width, height), STRIP_SCRIM_RGBA)
    draw = _StripDraw.Draw(overlay)
    draw.line((0, height - 1, width - 1, 0), fill=STRIP_WARN_RGB + (255,), width=max(8, width // 12))
    stamped = _StripImage.alpha_composite(tile, overlay)
    stamped.putalpha(tile.getchannel("A"))
    return stamped


def compose_composite(cells, cols, rows, max_bytes):
    """One cols x rows composite as canonical PNG bytes (pc_face's encoder).

    `cells` is the paste order, one per tile: ("face", png_bytes, discarded)
    or ("back", None, False). The canvas is fully transparent and each tile
    is pasted whole at its box, so a tile's own transparent corners stay
    transparent. A face that is discarded is stamped before it is pasted.
    Over `max_bytes` raises StripCompositeTooLarge: a composite is served
    whole or not at all."""
    boxes = strip_paste_boxes(cols, rows)
    if len(cells) > len(boxes):
        raise ValueError("cells")
    canvas = _StripImage.new("RGBA", strip_canvas_size(cols, rows), (0, 0, 0, 0))
    for box, (tile, data, discarded) in zip(boxes, cells):
        if tile == "face":
            with _StripImage.open(_strip_io.BytesIO(data)) as source:
                source.load()
                image = source.convert("RGBA")
            if discarded:
                image = _stamp_discarded(image)
        elif tile == "back":
            image = strip_back_tile()
        else:
            raise ValueError("tile")
        if image.size != (box[2] - box[0], box[3] - box[1]):
            raise ValueError("tile_size")
        canvas.paste(image, box[:2])
    data = _strip_face._encode_rgba(canvas)
    if len(data) > max_bytes:
        raise StripCompositeTooLarge(len(data))
    return data


def _strip_layout_word(cols, rows):
    return "margin=%d;gutter=%d;tile=%dx%d;grid=%dx%d" % (
        STRIP_MARGIN, STRIP_GUTTER, _strip_face.TILE_W, _strip_face.TILE_H, cols, rows)


def composite_digest(locale, renderer_fp, cols, rows, tokens):
    """16 hex of a SHA-256 over length-framed parts: the compositor version,
    the layout constants, the locale, the renderer fingerprint and the ORDERED
    per-slot tokens. Two composites share a digest only when every one of
    those is equal, so a back and a face in one slot, a discard, a moved face
    and a reordered slot list each key a different file."""
    digest = _strip_hashlib.sha256()
    parts = ["pc-composite", str(STRIP_COMPOSITOR_VERSION), _strip_layout_word(cols, rows),
             locale, renderer_fp]
    parts.extend(tokens)
    for part in parts:
        raw = ("" if part is None else str(part)).encode("utf-8")
        digest.update(len(raw).to_bytes(4, "big"))
        digest.update(raw)
    return digest.hexdigest()[:16]


def strip_slot_token(slot, print_id, tile, word, state):
    """A strip slot's digest token: `word` is the face_rev of a face and the
    reason of a back; `state` is live, discarded or gone."""
    return "%d:%s:%s:%s:%s" % (int(slot), print_id, tile, word, state)


def grid_slot_token(pos, print_id, tile, word):
    """A grid cell's digest token: `pos` is the 1-based grid position (a
    binder page is live prints only, so it carries no state word)."""
    return "%d:%s:%s:%s" % (int(pos), print_id, tile, word)


def _strip_hex32(ref):
    return str(ref).replace("-", "").lower()


def strip_manifest_entry(slot, print_id, subject_ref, tile, word, state):
    """{slot}:{print_id_32hex}:{subject_player_id_32hex}:{face|back}:{face_rev|reason}:{live|discarded|gone}"""
    return "%d:%s:%s:%s:%s:%s" % (int(slot), _strip_hex32(print_id), _strip_hex32(subject_ref),
                                  tile, word, state)


def grid_manifest_entry(pos, print_id, subject_ref, tile, word):
    """{pos}:{print_id_32hex}:{subject_player_id_32hex}:{face|back}:{face_rev|reason}"""
    return "%d:%s:%s:%s:%s" % (int(pos), _strip_hex32(print_id), _strip_hex32(subject_ref), tile, word)
