"""Synthetic top-card art bundles for the tests (Discord card render parity,
board row 33).

The repository carries NO card art: the real bundle is game-derived and lives
outside every repository, bind-mounted read-only into the api container. The
tests build their own: one deterministic opaque patch of the layout's art size
(pc_face.card_art_size) per canonical name, written through
pc_face.card_art_write_bundle (the format's one writer), so every chunk is
IHDR/IDAT/IEND and nothing identifies a machine or a time.
Each patch is a pattern no face layer draws (stripes in colours keyed on the
name), so a region that carries the art cannot equal one that does not.

Every size and box here is DERIVED from the layout (bug 408): the synthetic
source has the shape of a real harvested thumbnail (352x480), so the fitted
box leaves backing rows above and below the card, as a real patch does.

write_bundle_as_71f30e01 writes a bundle exactly as the tool at 71f30e01
wrote one (80x104 patches fitted into the 78x104 box at column 2, an index
with no geometry): the bundle staged on the boxes before bug 408.
"""
from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path

from PIL import Image, ImageDraw

import pc_face

# The shape of every thumbnail of the 2026-10-01 harvest (harvest.tsv w, h).
SOURCE_W, SOURCE_H = 352, 480

# The 71f30e01 geometry, for the old-bundle writer only: rects.badge_art_back
# [92,646,172,750] and rects.badge_art [94,646,172,750] of that layout.
OLD_BACK = (92, 646, 172, 750)
OLD_ART = (94, 646, 172, 750)


def _stripes(name: str, size, box) -> Image.Image:
    seed = hashlib.sha256(name.encode("utf-8")).digest()
    back = tuple(pc_face.LAYOUT["colours"]["badge_art_back"]) + (255,)
    image = Image.new("RGBA", size, back)
    draw = ImageDraw.Draw(image)
    a = (60 + seed[0] % 190, 40 + seed[1] % 200, 50 + seed[2] % 200, 255)
    b = (seed[3] % 120, 120 + seed[4] % 130, 200 - seed[5] % 120, 255)
    x0, y0, x1, y1 = box
    for y in range(y0, y1, 4):
        draw.rectangle((x0, y, x1 - 1, min(y + 1, y1 - 1)), fill=a)
        if y + 2 < y1:
            draw.rectangle((x0, y + 2, x1 - 1, min(y + 3, y1 - 1)), fill=b)
    draw.rectangle((x0 + 8, y0 + 9, x1 - 9, y0 + 29), fill=(250, 250, 250, 255))
    return image


def synthetic_box() -> tuple[int, int, int, int]:
    """Where a real-shaped thumbnail lands in the patch (the fitted box)."""
    return pc_face.card_art_fit_box(SOURCE_W, SOURCE_H)


def synthetic_patch(name: str) -> Image.Image:
    """The art backing over the whole patch and a striped 'card' over the
    fitted box, the shape the bundle builder composes (backing around a
    fitted card)."""
    return _stripes(name, pc_face.card_art_size(), synthetic_box())


def synthetic_provenance(**over) -> dict:
    """A complete provenance block, marked synthetic in every free-text field
    (the renderer checks presence, English and the backing colour; it cannot
    tell a test bundle from a harvest, and does not need to)."""
    prov = {"language": "en", "rounds_locale": "en", "game_build": "synthetic test bundle",
            "mod_build": "synthetic test bundle", "harvest": "synthetic",
            "backing_rgb": list(pc_face.card_art_backing_rgb()),
            "backing_method": "synthetic: the layout constant (tests only)"}
    prov.update(over)
    return prov


def synthetic_source(name: str) -> dict:
    """The harvest record of a synthetic patch: a real-shaped source and a
    per-name hash."""
    return {"source_sha256": hashlib.sha256(b"synthetic-source\n" + name.encode("utf-8")).hexdigest(),
            "source_rect": [0, 0, SOURCE_W, SOURCE_H]}


def write_bundle(dest: Path, names=None, patches=None, provenance=None, tool_version=None) -> str:
    """A valid bundle at `dest` for `names` (default: every expected name)."""
    names = pc_face.card_art_names() if names is None else names
    patches = {} if patches is None else patches
    kwargs = {} if tool_version is None else {"tool_version": tool_version}
    return pc_face.card_art_write_bundle(
        dest, {n: patches.get(n) or synthetic_patch(n) for n in names},
        {n: synthetic_source(n) for n in names},
        synthetic_provenance() if provenance is None else provenance, **kwargs)


def write_bundle_as_71f30e01(dest: Path) -> str:
    """A bundle in the exact shape the 71f30e01 tool wrote (the bundle on the
    boxes before bug 408): format 2, tool_version 2, NO geometry key, and one
    80x104 patch per name with the card fitted into the 78x104 box at column
    2 (that layout's badge_art relative to its badge_art_back). Written by
    hand here because the format's writer now always records the layout's
    geometry."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=False)
    size = (OLD_BACK[2] - OLD_BACK[0], OLD_BACK[3] - OLD_BACK[1])
    box = (OLD_ART[0] - OLD_BACK[0], OLD_ART[1] - OLD_BACK[1], OLD_ART[2] - OLD_BACK[0], OLD_ART[3] - OLD_BACK[1])
    cards = {}
    for name in pc_face.card_art_names():
        data = pc_face._encode_rgba(_stripes(name, size, box))
        stem = pc_face.card_art_slug(name)
        (dest / f"{stem}.png").write_bytes(data)
        cards[name] = {"file": f"{stem}.png", "sha256": hashlib.sha256(data).hexdigest(),
                       "width": size[0], "height": size[1],
                       "source_sha256": synthetic_source(name)["source_sha256"],
                       "source_rect": [0, 0, box[2] - box[0], box[3] - box[1]]}
    index_bytes = pc_face.card_art_index_bytes({"format": 2, "tool_version": 2,
                                                "provenance": synthetic_provenance(), "cards": cards})
    (dest / pc_face.CARD_ART_INDEX).write_bytes(index_bytes)
    digest = hashlib.sha256(index_bytes).hexdigest()
    (dest / pc_face.CARD_ART_DIGEST_FILE).write_bytes((digest + "\n").encode("ascii"))
    return digest


def rewrite_index(dest: Path, mutate) -> None:
    """Apply mutate(index_dict) and keep index bytes and BUNDLE-DIGEST
    self-consistent, so only the checks under test can refuse."""
    dest = Path(dest)
    index = json.loads((dest / pc_face.CARD_ART_INDEX).read_text(encoding="utf-8"))
    mutate(index)
    index_bytes = pc_face.card_art_index_bytes(index)
    (dest / pc_face.CARD_ART_INDEX).write_bytes(index_bytes)
    (dest / pc_face.CARD_ART_DIGEST_FILE).write_bytes(
        (hashlib.sha256(index_bytes).hexdigest() + "\n").encode("ascii"))


def rewrite_entry(dest: Path, name: str, data: bytes) -> None:
    """Replace one patch's bytes and keep the bundle SELF-CONSISTENT: the
    index's sha256 for it, the canonical index bytes and BUNDLE-DIGEST all
    follow, so only the per-entry checks can refuse it."""
    dest = Path(dest)
    index = json.loads((dest / pc_face.CARD_ART_INDEX).read_text(encoding="utf-8"))
    entry = index["cards"][name]
    (dest / entry["file"]).write_bytes(data)
    entry["sha256"] = hashlib.sha256(data).hexdigest()
    index_bytes = pc_face.card_art_index_bytes(index)
    (dest / pc_face.CARD_ART_INDEX).write_bytes(index_bytes)
    (dest / pc_face.CARD_ART_DIGEST_FILE).write_bytes(
        (hashlib.sha256(index_bytes).hexdigest() + "\n").encode("ascii"))


def drop_entry(dest: Path, name: str) -> None:
    """Remove one name from a bundle, consistently (file, index, digest)."""
    dest = Path(dest)
    index = json.loads((dest / pc_face.CARD_ART_INDEX).read_text(encoding="utf-8"))
    entry = index["cards"].pop(name)
    (dest / entry["file"]).unlink()
    index_bytes = pc_face.card_art_index_bytes(index)
    (dest / pc_face.CARD_ART_INDEX).write_bytes(index_bytes)
    (dest / pc_face.CARD_ART_DIGEST_FILE).write_bytes(
        (hashlib.sha256(index_bytes).hexdigest() + "\n").encode("ascii"))


def corrupt_idat(png: bytes) -> bytes:
    """The same PNG with one byte of its compressed pixel stream changed and
    the chunk CRC recomputed: a container that walks clean and a stream that
    does not inflate to the declared pixels."""
    offset = 8
    out = bytearray(png)
    while offset < len(png):
        length = struct.unpack(">I", png[offset:offset + 4])[0]
        kind = png[offset + 4:offset + 8]
        if kind == b"IDAT":
            start = offset + 8
            pos = start + length // 2
            out[pos] ^= 0x5A
            crc = zlib.crc32(bytes(out[offset + 4:start + length])) & 0xFFFFFFFF
            out[start + length:start + length + 4] = struct.pack(">I", crc)
            return bytes(out)
        offset += 12 + length
    raise AssertionError("no IDAT")
