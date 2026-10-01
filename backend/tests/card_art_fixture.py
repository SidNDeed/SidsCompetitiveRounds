"""Synthetic top-card art bundles for the tests (Discord card render parity,
board row 33).

The repository carries NO card art: the real bundle is game-derived and lives
outside every repository, bind-mounted read-only into the api container. The
tests build their own: one deterministic 80x104 opaque patch per canonical
name, written through pc_face.card_art_write_bundle (the format's one writer),
so every chunk is IHDR/IDAT/IEND and nothing identifies a machine or a time.
Each patch is a pattern no face layer draws (stripes in colours keyed on the
name), so a region that carries the art cannot equal one that does not.
"""
from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path

from PIL import Image, ImageDraw

import pc_face


def synthetic_patch(name: str) -> Image.Image:
    """The art backing over all 80x104 and a striped 'card' in columns
    2..80, the shape the bundle builder composes (backing either side of a
    height-fitted card)."""
    seed = hashlib.sha256(name.encode("utf-8")).digest()
    back = tuple(pc_face.LAYOUT["colours"]["badge_art_back"]) + (255,)
    image = Image.new("RGBA", (pc_face.CARD_ART_W, pc_face.CARD_ART_H), back)
    draw = ImageDraw.Draw(image)
    a = (60 + seed[0] % 190, 40 + seed[1] % 200, 50 + seed[2] % 200, 255)
    b = (seed[3] % 120, 120 + seed[4] % 130, 200 - seed[5] % 120, 255)
    for y in range(0, pc_face.CARD_ART_H, 4):
        draw.rectangle((2, y, 79, y + 1), fill=a)
        draw.rectangle((2, y + 2, 79, y + 3), fill=b)
    draw.rectangle((10, 10, 70, 30), fill=(250, 250, 250, 255))
    return image


def write_bundle(dest: Path, names=None, patches=None) -> str:
    """A valid bundle at `dest` for `names` (default: every expected name)."""
    names = pc_face.card_art_names() if names is None else names
    patches = {} if patches is None else patches
    return pc_face.card_art_write_bundle(dest, {n: patches.get(n) or synthetic_patch(n) for n in names})


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
