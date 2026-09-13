"""Deterministic Player Cards face and back renderer.

This module is deliberately isolated from the API and persistence layers.  Its
inputs are plain mappings and canonical portrait bytes; its outputs are
pixel-only PNGs produced by one pinned encoder configuration.
"""

from __future__ import annotations

import functools
import hashlib
import io
import json
import math
import platform
import struct
import unicodedata
import warnings
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import PIL
from PIL import Image, ImageChops, ImageDraw, ImageFont, features
import regex


CARD_W, CARD_H = 750, 1050
TILE_W, TILE_H = 375, 525
PORTRAIT_SRC, PORTRAIT_CARD, PORTRAIT_TILE = 1180, 590, 295
BANDS = ("common", "uncommon", "rare", "epic", "legendary")

_MODULE_DIR = Path(__file__).resolve().parent
_ASSETS_PATH = _MODULE_DIR / "assets" / "pc"
_FONTS_PATH = _MODULE_DIR / "assets" / "fonts"
ASSETS_DIR = str(_ASSETS_PATH)
FONTS_DIR = str(_FONTS_PATH)

with (_ASSETS_PATH / "face_layout_v1.json").open("r", encoding="utf-8") as _fh:
    LAYOUT = json.load(_fh)
with (_ASSETS_PATH / "catalogue.json").open("r", encoding="utf-8") as _fh:
    ENGLISH: dict[str, str] = json.load(_fh)
LABEL_IDS: tuple[str, ...] = (
    "pc.band.common", "pc.band.uncommon", "pc.band.rare", "pc.band.epic",
    "pc.band.legendary", "pc.band_short.common", "pc.band_short.uncommon",
    "pc.band_short.rare", "pc.band_short.epic", "pc.band_short.legendary",
    "pc.foil", "pc.foil_short", "pc.signed", "pc.top_card", "pc.stat.rank",
    "pc.stat.rating", "pc.stat.pool", "pc.stat.board", "pc.stat.record",
    "pc.preview_footer", "pc.unnamed", "pc.edition", "pc.unranked",
)
if tuple(ENGLISH) != LABEL_IDS:
    raise ValueError("catalogue_keys")

Image.MAX_IMAGE_PIXELS = 20_000_000

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_PNG_MAX_CHUNKS = 4096
_PNG_OUTPUT_CHUNKS = frozenset({b"IHDR", b"IDAT", b"IEND"})
_PORTRAIT_IHDR = (PORTRAIT_SRC, PORTRAIT_SRC, 8, 6, 0)
_PORTRAIT_MIN_COVERAGE = 0.02
_PORTRAIT_MAX_COVERAGE = 0.60
_PORTRAIT_MAX_BYTES = 1 << 20

_HAS_RAQM = bool(features.check("raqm"))
_LAYOUT_ENGINE = ImageFont.Layout.RAQM if _HAS_RAQM else ImageFont.Layout.BASIC

_FONT_FILES = {
    "bold": "NotoSans-Bold.ttf",
    "black": "NotoSans-Black.ttf",
    "cjk": "NotoSansCJKsc-Bold.otf",
    "symbols": "NotoSansSymbols2-Regular.ttf",
    "emoji": "NotoColorEmoji.ttf",
    "script": "Kalam-Bold.ttf",
    "arabic": "NotoSansArabic-Bold.ttf",
    "hebrew": "NotoSansHebrew-Bold.ttf",
    "thai": "NotoSansThai-Bold.ttf",
    "devanagari": "NotoSansDevanagari-Bold.ttf",
    "bengali": "NotoSansBengali-Bold.ttf",
    "tamil": "NotoSansTamil-Bold.ttf",
    "georgian": "NotoSansGeorgian-Bold.ttf",
    "armenian": "NotoSansArmenian-Bold.ttf",
    "symbols1": "NotoSansSymbols-Bold.ttf",
}

# The order the run splitter tries the script faces in. Which font draws a
# cluster decides which pixels land, so this order is part of the render
# identity: fixed and explicit, never a set or a dict-order accident.
_SCRIPT_ROLES = ("arabic", "hebrew", "thai", "devanagari", "bengali", "tamil", "georgian", "armenian", "symbols1")


# ---------------------------------------------------------------------------
# PNG container and canonicalisation
# ---------------------------------------------------------------------------

def png_chunks(data: bytes) -> list[tuple[bytes, int]]:
    """Walk a complete PNG container and return ``(type, payload_size)``.

    The walk checks every CRC and refuses a missing/duplicate terminal chunk,
    malformed type, implausible chunk count, or any byte after IEND.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError("png_invalid")
    raw = bytes(data)
    if len(raw) < 33 or raw[:8] != _PNG_MAGIC:
        raise ValueError("png_invalid")
    out: list[tuple[bytes, int]] = []
    offset = 8
    saw_ihdr = False
    saw_plte = False
    saw_idat = False
    closed_idat = False
    saw_iend = False
    ihdr_colour = None
    while offset < len(raw):
        if len(out) >= _PNG_MAX_CHUNKS or offset + 12 > len(raw):
            raise ValueError("png_invalid")
        length = int.from_bytes(raw[offset:offset + 4], "big")
        chunk_type = raw[offset + 4:offset + 8]
        if not all(65 <= c <= 90 or 97 <= c <= 122 for c in chunk_type):
            raise ValueError("png_invalid")
        if 97 <= chunk_type[2] <= 122:
            raise ValueError("png_invalid")
        if 65 <= chunk_type[0] <= 90 and chunk_type not in {b"IHDR", b"PLTE", b"IDAT", b"IEND"}:
            raise ValueError("png_invalid")
        end = offset + 12 + length
        if end > len(raw):
            raise ValueError("png_invalid")
        payload = raw[offset + 8:offset + 8 + length]
        expected_crc = int.from_bytes(raw[offset + 8 + length:end], "big")
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != expected_crc:
            raise ValueError("png_invalid")
        if not out:
            if chunk_type != b"IHDR" or length != 13:
                raise ValueError("png_invalid")
            saw_ihdr = True
            ihdr_colour = payload[9]
        elif chunk_type == b"IHDR" or saw_iend:
            raise ValueError("png_invalid")
        if chunk_type == b"PLTE":
            if saw_plte or saw_idat or length == 0 or length > 768 or length % 3:
                raise ValueError("png_invalid")
            saw_plte = True
        if chunk_type == b"IDAT":
            if closed_idat:
                raise ValueError("png_invalid")
            saw_idat = True
        elif saw_idat:
            closed_idat = True
        if chunk_type == b"IEND":
            if length != 0:
                raise ValueError("png_invalid")
            saw_iend = True
        out.append((chunk_type, length))
        offset = end
        if saw_iend:
            break
    if (not saw_ihdr or not saw_idat or not saw_iend or offset != len(raw)
            or (ihdr_colour == 3 and not saw_plte)
            or (ihdr_colour in (0, 4) and saw_plte)):
        raise ValueError("png_invalid")
    return out


def png_ihdr(data: bytes) -> tuple[int, int, int, int, int]:
    """Return ``(width, height, depth, colour_type, interlace)`` from IHDR."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError("png_invalid")
    raw = bytes(data)
    if (len(raw) < 33 or raw[:8] != _PNG_MAGIC or raw[8:12] != b"\x00\x00\x00\r"
            or raw[12:16] != b"IHDR"):
        raise ValueError("png_invalid")
    payload = raw[16:29]
    if zlib.crc32(b"IHDR" + payload) & 0xFFFFFFFF != int.from_bytes(raw[29:33], "big"):
        raise ValueError("png_invalid")
    width, height, depth, colour, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", payload
    )
    legal_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        3: {1, 2, 4, 8},
        4: {8, 16},
        6: {8, 16},
    }
    if (not 0 < width < 2**31 or not 0 < height < 2**31
            or depth not in legal_depths.get(colour, set())
            or compression != 0 or filtering != 0 or interlace not in (0, 1)):
        raise ValueError("png_invalid")
    return width, height, depth, colour, interlace


def _encode_rgba(image: Image.Image) -> bytes:
    rgba = image if image.mode == "RGBA" else image.convert("RGBA")
    fresh = Image.frombytes("RGBA", rgba.size, rgba.tobytes())
    output = io.BytesIO()
    fresh.save(output, format="PNG", compress_level=6, optimize=False)
    data = output.getvalue()
    chunks = png_chunks(data)
    if any(kind not in _PNG_OUTPUT_CHUNKS for kind, _ in chunks):
        raise ValueError("png_encoder")
    return data


def canonical_png(data: bytes, expect_size: tuple[int, int] | None = None) -> bytes:
    """Decode a PNG, rebuild it from RGBA pixels, and apply the pinned encoder."""
    try:
        raw = bytes(data)
        png_chunks(raw)
        png_ihdr(raw)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if (source.format or "").upper() != "PNG":
                    raise ValueError("png_invalid")
                source.load()
                if expect_size is not None and source.size != tuple(expect_size):
                    raise ValueError("png_size")
                pixels = source.convert("RGBA").tobytes()
                size = source.size
        return _encode_rgba(Image.frombytes("RGBA", size, pixels))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("png_invalid") from exc


def prepare_portrait(data: bytes) -> tuple[bytes, dict]:
    """Validate and canonicalise one 1180-square, straight-alpha portrait."""
    try:
        raw = bytes(data)
    except Exception:
        raise ValueError("portrait_invalid") from None
    if len(raw) > _PORTRAIT_MAX_BYTES:
        raise ValueError("portrait_too_large")
    try:
        png_chunks(raw)
        if png_ihdr(raw) != _PORTRAIT_IHDR:
            raise ValueError("header")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if (source.format or "").upper() != "PNG" or source.size != (PORTRAIT_SRC, PORTRAIT_SRC):
                    raise ValueError("decode")
                if getattr(source, "n_frames", 1) != 1:
                    raise ValueError("animated")
                source.load()
                if source.mode != "RGBA":
                    raise ValueError("mode")
                portrait = Image.frombytes("RGBA", source.size, source.tobytes())
        alpha = portrait.getchannel("A")
        coverage = sum(alpha.histogram()[1:]) / float(PORTRAIT_SRC * PORTRAIT_SRC)
    except Exception:
        raise ValueError("portrait_invalid") from None

    if not _PORTRAIT_MIN_COVERAGE <= coverage <= _PORTRAIT_MAX_COVERAGE:
        raise ValueError("portrait_coverage")

    try:
        hidden = alpha.point(lambda value: 255 if value == 0 else 0)
        portrait.paste((0, 0, 0, 0), (0, 0, PORTRAIT_SRC, PORTRAIT_SRC), hidden)
        first_pass = _encode_rgba(portrait)
        canonical = canonical_png(first_pass, (PORTRAIT_SRC, PORTRAIT_SRC))
    except Exception:
        raise ValueError("portrait_invalid") from None
    if len(canonical) > _PORTRAIT_MAX_BYTES:
        raise ValueError("portrait_too_large")
    return canonical, {
        "coverage": coverage,
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "width": PORTRAIT_SRC,
        "height": PORTRAIT_SRC,
    }


# ---------------------------------------------------------------------------
# Font coverage, shaping runs, and CBDT emoji fallback
# ---------------------------------------------------------------------------

def _u8(data: bytes, offset: int) -> int:
    return data[offset]


def _s8(data: bytes, offset: int) -> int:
    return struct.unpack_from(">b", data, offset)[0]


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def _s16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">h", data, offset)[0]


def _u24(data: bytes, offset: int) -> int:
    return data[offset] << 16 | data[offset + 1] << 8 | data[offset + 2]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _font_tables(font: bytes) -> dict[str, bytes]:
    offset = _u32(font, 12) if font[:4] == b"ttcf" else 0
    count = _u16(font, offset + 4)
    tables: dict[str, bytes] = {}
    for index in range(count):
        record = offset + 12 + 16 * index
        tag = font[record:record + 4].decode("latin1")
        table_offset = _u32(font, record + 8)
        table_size = _u32(font, record + 12)
        if table_offset + table_size > len(font):
            raise ValueError("font_table")
        tables[tag] = font[table_offset:table_offset + table_size]
    return tables


class _Cmap:
    def __init__(self, table: bytes):
        self.groups: list[tuple[int, int, int]] = []
        self.format4: tuple[bytes, int, int] | None = None
        self.uvs_nondefault: dict[tuple[int, int], int] = {}
        self.uvs_default: dict[int, list[tuple[int, int]]] = {}
        best12 = best4 = format14 = None
        for index in range(_u16(table, 2)):
            record = 4 + 8 * index
            platform_id = _u16(table, record)
            encoding_id = _u16(table, record + 2)
            offset = _u32(table, record + 4)
            fmt = _u16(table, offset)
            if fmt == 12 and (best12 is None or (platform_id, encoding_id) == (3, 10)):
                best12 = offset
            elif fmt == 4 and (best4 is None or (platform_id, encoding_id) == (3, 1)):
                best4 = offset
            elif fmt == 14 and (platform_id, encoding_id) == (0, 5):
                format14 = offset
        if best12 is not None:
            for index in range(_u32(table, best12 + 12)):
                pos = best12 + 16 + 12 * index
                self.groups.append((_u32(table, pos), _u32(table, pos + 4), _u32(table, pos + 8)))
        if best4 is not None:
            self.format4 = (table, best4, _u16(table, best4 + 6) // 2)
        if format14 is not None:
            self._parse_format14(table, format14)

    def _parse_format14(self, table: bytes, offset: int) -> None:
        for index in range(_u32(table, offset + 6)):
            record = offset + 10 + 11 * index
            selector = _u24(table, record)
            default_offset = _u32(table, record + 3)
            nondefault_offset = _u32(table, record + 7)
            if default_offset:
                base = offset + default_offset
                ranges = []
                for range_index in range(_u32(table, base)):
                    pos = base + 4 + 4 * range_index
                    start = _u24(table, pos)
                    ranges.append((start, start + _u8(table, pos + 3)))
                self.uvs_default[selector] = ranges
            if nondefault_offset:
                base = offset + nondefault_offset
                for map_index in range(_u32(table, base)):
                    pos = base + 4 + 5 * map_index
                    self.uvs_nondefault[(_u24(table, pos), selector)] = _u16(table, pos + 3)

    def covered(self) -> set[int]:
        """Every code point this cmap maps to a glyph.

        Enumerated from the tables rather than probed one code point at a
        time, and from the SAME parser the renderer draws through — the
        coverage manifest and the renderer must not be able to disagree about
        what this font can draw (#341)."""
        out: set[int] = set()
        for start, end, first_gid in self.groups:
            # A group whose startGlyphID is 0 still maps every code point AFTER
            # the first to a real glyph (glyph = first_gid + offset), so
            # skipping the group whole removed characters this same parser
            # renders. Only the one code point that would map to glyph 0 is
            # excluded -- `lookup()` answers 0 there and 0 is .notdef.
            for codepoint in range(start, min(end, 0x10FFFF) + 1):
                if first_gid + (codepoint - start):
                    out.add(codepoint)
        if self.format4 is not None:
            table, offset, segments = self.format4
            ends = offset + 14
            starts = ends + segments * 2 + 2
            for index in range(segments):
                end = _u16(table, ends + 2 * index)
                start = _u16(table, starts + 2 * index)
                if start > end or start == 0xFFFF:
                    continue
                for codepoint in range(start, end + 1):
                    if self.lookup(codepoint):
                        out.add(codepoint)
        return out

    def lookup(self, codepoint: int) -> int:
        for start, end, first_gid in self.groups:
            if start <= codepoint <= end:
                return first_gid + codepoint - start
        if self.format4 is not None and codepoint <= 0xFFFF:
            table, offset, segments = self.format4
            ends = offset + 14
            starts = ends + segments * 2 + 2
            deltas = starts + segments * 2
            ranges = deltas + segments * 2
            for index in range(segments):
                end = _u16(table, ends + 2 * index)
                if codepoint > end:
                    continue
                start = _u16(table, starts + 2 * index)
                if codepoint < start:
                    return 0
                delta = _s16(table, deltas + 2 * index)
                range_offset = _u16(table, ranges + 2 * index)
                if range_offset == 0:
                    return (codepoint + delta) & 0xFFFF
                address = ranges + 2 * index + range_offset + 2 * (codepoint - start)
                gid = _u16(table, address)
                return (gid + delta) & 0xFFFF if gid else 0
        return 0

    def variation(self, base: int, selector: int) -> int | None:
        gid = self.uvs_nondefault.get((base, selector))
        if gid is not None:
            return gid
        for start, end in self.uvs_default.get(selector, ()):
            if start <= base <= end:
                return self.lookup(base)
        return None


def _coverage(table: bytes, offset: int) -> dict[int, int]:
    fmt = _u16(table, offset)
    result: dict[int, int] = {}
    if fmt == 1:
        for index in range(_u16(table, offset + 2)):
            result[_u16(table, offset + 4 + 2 * index)] = index
    elif fmt == 2:
        for index in range(_u16(table, offset + 2)):
            pos = offset + 4 + 6 * index
            start, end, first = _u16(table, pos), _u16(table, pos + 2), _u16(table, pos + 4)
            for gid in range(start, end + 1):
                result[gid] = first + gid - start
    return result


@dataclass
class _Gsub:
    order: list[tuple[str, dict]] = field(default_factory=list)


def _parse_ligatures(table: bytes, offset: int, output: dict[int, list[tuple[tuple[int, ...], int]]]) -> None:
    if _u16(table, offset) != 1:
        return
    covered = _coverage(table, offset + _u16(table, offset + 2))
    by_index = {coverage_index: gid for gid, coverage_index in covered.items()}
    for set_index in range(_u16(table, offset + 4)):
        first = by_index.get(set_index)
        if first is None:
            continue
        set_offset = offset + _u16(table, offset + 6 + 2 * set_index)
        for ligature_index in range(_u16(table, set_offset)):
            pos = set_offset + _u16(table, set_offset + 2 + 2 * ligature_index)
            ligature = _u16(table, pos)
            count = _u16(table, pos + 2)
            components = tuple(_u16(table, pos + 4 + 2 * i) for i in range(max(count - 1, 0)))
            output.setdefault(first, []).append((components, ligature))
    for first in output:
        output[first].sort(key=lambda item: -len(item[0]))


def _parse_singles(table: bytes, offset: int, output: dict[int, int]) -> None:
    fmt = _u16(table, offset)
    covered = _coverage(table, offset + _u16(table, offset + 2))
    if fmt == 1:
        delta = _s16(table, offset + 4)
        for gid in covered:
            output[gid] = (gid + delta) & 0xFFFF
    elif fmt == 2:
        count = _u16(table, offset + 4)
        for gid, coverage_index in covered.items():
            if coverage_index < count:
                output[gid] = _u16(table, offset + 6 + 2 * coverage_index)


def _parse_gsub(table: bytes) -> _Gsub:
    result = _Gsub()
    feature_list = _u16(table, 6)
    lookup_list = _u16(table, 8)
    wanted: list[int] = []
    for feature_index in range(_u16(table, feature_list)):
        record = feature_list + 2 + 6 * feature_index
        feature = feature_list + _u16(table, record + 4)
        for index in range(_u16(table, feature + 2)):
            lookup_index = _u16(table, feature + 4 + 2 * index)
            if lookup_index not in wanted:
                wanted.append(lookup_index)
    lookup_count = _u16(table, lookup_list)
    for lookup_index in sorted(wanted):
        if lookup_index >= lookup_count:
            continue
        lookup = lookup_list + _u16(table, lookup_list + 2 + 2 * lookup_index)
        lookup_type = _u16(table, lookup)
        ligatures: dict[int, list[tuple[tuple[int, ...], int]]] = {}
        singles: dict[int, int] = {}
        for sub_index in range(_u16(table, lookup + 4)):
            subtable = lookup + _u16(table, lookup + 6 + 2 * sub_index)
            sub_type = lookup_type
            if sub_type == 7:
                sub_type = _u16(table, subtable + 2)
                subtable += _u32(table, subtable + 4)
            if sub_type == 4:
                _parse_ligatures(table, subtable, ligatures)
            elif sub_type == 1:
                _parse_singles(table, subtable, singles)
        if ligatures:
            result.order.append(("ligature", ligatures))
        if singles:
            result.order.append(("single", singles))
    return result


def _apply_gsub(glyphs: list[int], gsub: _Gsub) -> list[int]:
    current = list(glyphs)
    for kind, table in gsub.order:
        if kind == "single":
            current = [table.get(gid, gid) for gid in current]
            continue
        index = 0
        replaced: list[int] = []
        while index < len(current):
            matched = False
            for components, ligature in table.get(current[index], ()):
                count = len(components)
                if tuple(current[index + 1:index + count + 1]) == components:
                    replaced.append(ligature)
                    index += count + 1
                    matched = True
                    break
            if not matched:
                replaced.append(current[index])
                index += 1
        current = replaced
    return current


@dataclass
class _BitmapGlyph:
    png: bytes
    width: int
    height: int
    bearing_x: int
    bearing_y: int
    advance: int


class _CbdtStrike:
    def __init__(self, cblc: bytes, cbdt: bytes):
        self.cblc = cblc
        self.cbdt = cbdt
        best: tuple[int, int] | None = None
        for index in range(_u32(cblc, 4)):
            record = 8 + 48 * index
            ppem = _u8(cblc, record + 45)
            if best is None or ppem > best[1]:
                best = (record, ppem)
        if best is None:
            raise ValueError("emoji_strike")
        record, self.ppem = best
        self.ascender = _s8(cblc, record + 16)
        self.descender = _s8(cblc, record + 17)
        array_offset = _u32(cblc, record)
        self.subtables: list[tuple[int, int, int]] = []
        for index in range(_u32(cblc, record + 8)):
            pos = array_offset + 8 * index
            self.subtables.append((
                _u16(cblc, pos),
                _u16(cblc, pos + 2),
                array_offset + _u32(cblc, pos + 4),
            ))

    @staticmethod
    def _big_metrics(table: bytes, offset: int) -> tuple[int, int, int, int, int]:
        return (_u8(table, offset), _u8(table, offset + 1), _s8(table, offset + 2),
                _s8(table, offset + 3), _u8(table, offset + 4))

    def glyph(self, gid: int) -> _BitmapGlyph | None:
        table = self.cblc
        for first, last, subtable in self.subtables:
            if not first <= gid <= last:
                continue
            index_format = _u16(table, subtable)
            image_format = _u16(table, subtable + 2)
            data_offset = _u32(table, subtable + 4)
            big = None
            if index_format == 1:
                pos = subtable + 8 + 4 * (gid - first)
                start, end = _u32(table, pos), _u32(table, pos + 4)
            elif index_format == 3:
                pos = subtable + 8 + 2 * (gid - first)
                start, end = _u16(table, pos), _u16(table, pos + 2)
            elif index_format == 2:
                size = _u32(table, subtable + 8)
                big = self._big_metrics(table, subtable + 12)
                start, end = size * (gid - first), size * (gid - first + 1)
            elif index_format == 4:
                count = _u32(table, subtable + 8)
                start = end = None
                for index in range(count):
                    pos = subtable + 12 + 4 * index
                    if _u16(table, pos) == gid:
                        start = _u16(table, pos + 2)
                        end = _u16(table, pos + 6)
                        break
                if start is None or end is None:
                    return None
            elif index_format == 5:
                size = _u32(table, subtable + 8)
                big = self._big_metrics(table, subtable + 12)
                count = _u32(table, subtable + 20)
                found = None
                for index in range(count):
                    if _u16(table, subtable + 24 + 2 * index) == gid:
                        found = index
                        break
                if found is None:
                    return None
                start, end = size * found, size * (found + 1)
            else:
                return None
            if end <= start:
                return None
            data = self.cbdt[data_offset + start:data_offset + end]
            if image_format == 17:
                height, width = _u8(data, 0), _u8(data, 1)
                bearing_x, bearing_y, advance = _s8(data, 2), _s8(data, 3), _u8(data, 4)
                size = _u32(data, 5)
                return _BitmapGlyph(bytes(data[9:9 + size]), width, height, bearing_x, bearing_y, advance)
            if image_format == 18:
                height, width = _u8(data, 0), _u8(data, 1)
                bearing_x, bearing_y, advance = _s8(data, 2), _s8(data, 3), _u8(data, 4)
                size = _u32(data, 8)
                return _BitmapGlyph(bytes(data[12:12 + size]), width, height, bearing_x, bearing_y, advance)
            if image_format == 19:
                size = _u32(data, 0)
                height, width, bearing_x, bearing_y, advance = big or (0, 0, 0, 0, 0)
                return _BitmapGlyph(bytes(data[4:4 + size]), width, height, bearing_x, bearing_y, advance)
            return None
        return None


class _EmojiFont:
    def __init__(self, data: bytes):
        tables = _font_tables(data)
        self.cmap = _Cmap(tables["cmap"])
        self.gsub = _parse_gsub(tables["GSUB"]) if "GSUB" in tables else _Gsub()
        self.strike = _CbdtStrike(tables["CBLC"], tables["CBDT"])
        self.ascent = self.strike.ascender
        self.descent = -self.strike.descender

    def resolve(self, codepoints: Sequence[int]) -> int | None:
        points = list(codepoints)
        if len(points) == 2 and points[1] == 0xFE0F:
            varied = self.cmap.variation(points[0], points[1])
            if varied:
                return varied
        glyphs: list[int] = []
        for codepoint in points:
            gid = self.cmap.lookup(codepoint)
            if not gid:
                if codepoint == 0xFE0F:
                    continue
                return None
            glyphs.append(gid)
        shaped = _apply_gsub(glyphs, self.gsub)
        if len(shaped) == 1:
            return shaped[0]
        selector_gid = self.cmap.lookup(0xFE0F)
        if selector_gid:
            shaped = [gid for gid in shaped if gid != selector_gid]
        if len(shaped) == 1:
            return shaped[0]
        if 0xFE0F in points:
            return self.resolve([point for point in points if point != 0xFE0F])
        return None

    def render(self, text: str) -> Image.Image | None:
        gid = self.resolve([ord(char) for char in text])
        bitmap = self.strike.glyph(gid) if gid is not None else None
        if bitmap is None:
            return None
        with Image.open(io.BytesIO(bitmap.png)) as source:
            glyph = source.convert("RGBA")
        height = max(1, self.ascent + self.descent)
        canvas = Image.new("RGBA", (max(glyph.width, 1), height), (0, 0, 0, 0))
        canvas.alpha_composite(glyph, (max(0, bitmap.bearing_x), self.ascent - bitmap.bearing_y))
        return canvas


@functools.lru_cache(maxsize=None)
def _font(role: str, size: int) -> ImageFont.FreeTypeFont:
    actual_size = 109 if role == "emoji" else max(1, int(size))
    return ImageFont.truetype(
        str(_FONTS_PATH / _FONT_FILES[role]),
        actual_size,
        layout_engine=_LAYOUT_ENGINE,
    )


@functools.lru_cache(maxsize=None)
def _cmap(role: str) -> _Cmap:
    tables = _font_tables((_FONTS_PATH / _FONT_FILES[role]).read_bytes())
    return _Cmap(tables["cmap"])


@functools.lru_cache(maxsize=1)
def _emoji_font() -> _EmojiFont:
    return _EmojiFont((_FONTS_PATH / _FONT_FILES["emoji"]).read_bytes())


# Code points every role is treated as covering: none of them is a glyph and
# each one holds a sequence together, so a font that does not list it must not
# be the reason a cluster is refused. ONE definition — it was written here and
# again, differently, in the coverage generator, and the generator's copy is
# what the manifest was built from (#341).
_ALWAYS_GLYPH = frozenset({0x20, 0x200C, 0x200D, 0xFE0E, 0xFE0F}
                          | set(range(0xFE00, 0xFE10))
                          | set(range(0xE0100, 0xE01F0)))


@functools.lru_cache(maxsize=None)
def _has_glyph(role: str, codepoint: int) -> bool:
    if codepoint in _ALWAYS_GLYPH:
        return True
    return bool(_cmap(role).lookup(codepoint))


_EMOJI_RE = regex.compile(
    r"\p{Extended_Pictographic}|\p{Emoji_Presentation}|\p{Emoji_Modifier}"
    r"|\p{Regional_Indicator}|\u20E3"
)


def graphemes(s: str) -> list[str]:
    """Return UAX #29 extended grapheme clusters."""
    return regex.findall(r"\X", str(s))


def _is_emoji_cluster(cluster: str) -> bool:
    return bool(_EMOJI_RE.search(cluster))


# The base roles the renderer draws text with: the name and the labels at
# "black"/"bold", the autograph at "script". A cluster only SOME of them can
# draw is still a box on the others, which is why the coverage projection takes
# every one of them into account.
BASE_ROLES = ("black", "bold", "script")


def candidate_roles(base_role: str) -> tuple[str, ...]:
    """The fonts the run splitter tries, in order, for a non-emoji cluster.

    ONE definition: the splitter picks the font that draws the pixels and the
    coverage manifest decides which clusters may reach it, so a candidate list
    written twice is a manifest that promises what the renderer will not do."""
    candidates = [base_role]
    if base_role == "script":
        candidates.append("bold")
    candidates.extend(("cjk", "symbols"))
    candidates.extend(_SCRIPT_ROLES)
    return tuple(dict.fromkeys(candidates))


def _cluster_role(cluster: str, base_role: str) -> tuple[str, str]:
    if _is_emoji_cluster(cluster):
        return "emoji", cluster
    for role in candidate_roles(base_role):
        if all(_has_glyph(role, ord(char)) for char in cluster):
            return role, cluster
    return "symbols", "▯"


# --------------------------------------------------------------- bidi order
#
# UAX#9, the implicit half.  A level per character, so `_runs` can order whole
# runs by rule L2.  Explicit embeddings and isolates are NOT implemented: the
# name projection removes those controls before a name reaches this module, and
# what is left is exactly strong types, weak types and neutrals.  Paired
# brackets (N0, Unicode 6.3) are not implemented either -- a bracket resolves
# through N1/N2 as it did before that rule existed.
#
# The one thing this must not do is repeat the shaper's work.  The shaper
# reorders and joins characters WITHIN the text it is handed, deciding the
# direction from that text; this decides where each handed-over fragment goes.

_BIDI_STRONG = ("L", "R", "AL")
_BIDI_REMOVED = frozenset({"RLE", "LRE", "RLO", "LRO", "PDF", "BN"})
_BIDI_ISOLATE = frozenset({"LRI", "RLI", "FSI", "PDI"})
_BIDI_NI = frozenset({"B", "S", "WS", "ON"}) | _BIDI_ISOLATE

# UAX#9 L4.  Only the pairs a display name plausibly carries; the table is here
# rather than derived from `unicodedata` because that module reports THAT a
# character mirrors and never what it mirrors to.
_BIDI_MIRROR = str.maketrans({
    "(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{",
    "<": ">", ">": "<", "\u00ab": "\u00bb", "\u00bb": "\u00ab",
    "\u2039": "\u203a", "\u203a": "\u2039",
})


def _bidi_class(char: str) -> str:
    # An unassigned code point reports "" here.  The coverage projection only
    # keeps what a font draws, so this is a guard rather than a path.
    return unicodedata.bidirectional(char) or "L"


def _bidi_levels(text: str) -> list[int]:
    """One embedding level per character of `text` (UAX#9, implicit rules)."""
    kinds = [_bidi_class(char) for char in text]

    base = 0                                                    # P2, P3
    for kind in kinds:
        if kind == "L":
            break
        if kind in ("R", "AL"):
            base = 1
            break

    # X9: the explicit controls take no part; they are given a level at the end.
    live = [i for i, kind in enumerate(kinds) if kind not in _BIDI_REMOVED]
    seq = [kinds[i] for i in live]
    edge = "R" if base else "L"                                 # X10 sos == eos

    for n, kind in enumerate(seq):                              # W1
        if kind == "NSM":
            prior = seq[n - 1] if n else edge
            seq[n] = "ON" if prior in _BIDI_ISOLATE else prior

    strong = edge                                               # W2
    for n, kind in enumerate(seq):
        if kind in _BIDI_STRONG:
            strong = kind
        elif kind == "EN" and strong == "AL":
            seq[n] = "AN"

    seq = ["R" if kind == "AL" else kind for kind in seq]       # W3

    for n in range(1, len(seq) - 1):                            # W4
        if seq[n] in ("ES", "CS") and seq[n - 1] == "EN" == seq[n + 1]:
            seq[n] = "EN"
        elif seq[n] == "CS" and seq[n - 1] == "AN" == seq[n + 1]:
            seq[n] = "AN"

    n = 0                                                       # W5
    while n < len(seq):
        if seq[n] != "ET":
            n += 1
            continue
        end = n
        while end < len(seq) and seq[end] == "ET":
            end += 1
        before = seq[n - 1] if n else edge
        after = seq[end] if end < len(seq) else edge
        if before == "EN" or after == "EN":
            seq[n:end] = ["EN"] * (end - n)
        n = end

    seq = ["ON" if kind in ("ET", "ES", "CS") else kind for kind in seq]   # W6

    strong = edge                                               # W7
    for n, kind in enumerate(seq):
        if kind in ("L", "R"):
            strong = kind
        elif kind == "EN" and strong == "L":
            seq[n] = "L"

    n = 0                                                       # N1, N2
    while n < len(seq):
        if seq[n] not in _BIDI_NI:
            n += 1
            continue
        end = n
        while end < len(seq) and seq[end] in _BIDI_NI:
            end += 1
        # a number counts as R for the purpose of the text around it
        before = seq[n - 1] if n else edge
        after = seq[end] if end < len(seq) else edge
        before = "R" if before in ("EN", "AN") else before
        after = "R" if after in ("EN", "AN") else after
        seq[n:end] = [before if before == after else edge] * (end - n)
        n = end

    resolved = [base] * len(seq)                                # I1, I2
    for n, kind in enumerate(seq):
        if base % 2 == 0:
            resolved[n] = base + (1 if kind == "R" else 2 if kind in ("EN", "AN") else 0)
        else:
            resolved[n] = base + (1 if kind in ("L", "EN", "AN") else 0)

    levels = [base] * len(text)
    for n, i in enumerate(live):
        levels[i] = resolved[n]
    for i in range(len(text)):                                  # a removed
        if kinds[i] in _BIDI_REMOVED:                           # control sits
            levels[i] = levels[i - 1] if i else base            # with its text

    trailing = True                                             # L1
    for i in range(len(text) - 1, -1, -1):
        if kinds[i] in ("S", "B"):
            levels[i] = base
            trailing = True
        elif trailing and (kinds[i] == "WS" or kinds[i] in _BIDI_ISOLATE
                           or kinds[i] in _BIDI_REMOVED):
            levels[i] = base
        else:
            trailing = False
    return levels


def _rtl_by_hand(value: str, level: int) -> str:
    """The half of a right-to-left run the shaper will not do for us.

    Laying runs out by L2 is only equivalent to L2 over characters while
    SOMEBODY reverses the characters inside each run, and mirrors the paired
    punctuation among them (L4).  For a run carrying strong right-to-left text
    the shaper does both, deciding from that run's own characters.  A run that
    is nothing but neutrals -- the ` (` between two Hebrew words, drawn from
    the Latin face because that is the face covering it -- gives the shaper
    nothing strong to read, so it lays the run out left-to-right and does
    neither.  This is the complement of the shaper, never a repeat of it: a run
    holding a strong right-to-left character is handed over untouched.
    """
    if level % 2 == 0 or any(_bidi_class(char) in ("R", "AL") for char in value):
        return value
    return "".join(reversed(graphemes(value.translate(_BIDI_MIRROR))))


def _visual(runs: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
    """UAX#9 L2, applied to whole runs instead of characters.

    Equivalent, because a run is a maximal stretch at ONE level: reversing the
    run sequence at each level from the highest down is the same permutation,
    and the reversals at or above a run's own level are what the shaper already
    performs inside it.
    """
    order = list(runs)
    if not order:
        return order
    levels = [level for _, _, level in order]
    # "including intermediate levels not actually present" -- an even-level
    # island still gets reversed twice and lands back where it started.
    lowest_odd = min(level if level % 2 else level + 1 for level in levels)
    for level in range(max(levels), lowest_odd - 1, -1):
        n = 0
        while n < len(order):
            if order[n][2] < level:
                n += 1
                continue
            end = n
            while end < len(order) and order[end][2] >= level:
                end += 1
            order[n:end] = order[n:end][::-1]
            n = end
    return order


def _runs(text: str, base_role: str) -> list[tuple[str, str, int]]:
    levels = _bidi_levels(text)
    result: list[list] = []
    at = 0
    for cluster in graphemes(text):
        role, visible = _cluster_role(cluster, base_role)
        level = levels[at]
        at += len(cluster)
        # A run is one face at one level: a level change splits it even when
        # the face does not, because `_visual` reorders whole runs.
        if role != "emoji" and result and result[-1][0] == role and result[-1][2] == level:
            result[-1][1] += visible
        else:
            result.append([role, visible, level])
    return [(role, _rtl_by_hand(value, level), level) for role, value, level in result]


@functools.lru_cache(maxsize=1024)
def _emoji_image(text: str, size: int) -> Image.Image | None:
    source = None
    try:
        # This is the specified Pillow path.  Stock Windows Pillow has no RAQM
        # and returns a blank canvas for this CBDT font, so the table reader
        # below supplies the same embedded strike (including GSUB sequences).
        font = _font("emoji", 109)
        ascent, descent = font.getmetrics()
        width = max(1, int(math.ceil(font.getlength(text))))
        scratch = Image.new("RGBA", (width + 4, ascent + descent), (0, 0, 0, 0))
        ImageDraw.Draw(scratch).text((2, ascent), text, font=font, anchor="ls", embedded_color=True)
        source = scratch if scratch.getbbox() else None
    except Exception:
        source = None
    if source is None:
        source = _emoji_font().render(text)
    if source is None:
        return None
    target_height = max(1, int(size))
    target_width = max(1, int(round(source.width * target_height / source.height)))
    return source.resize((target_width, target_height), Image.Resampling.LANCZOS)


def _run_metrics(role: str, text: str, size: int) -> tuple[float, int, int, Image.Image | None]:
    if role == "emoji":
        image = _emoji_image(text, size)
        if image is None:
            return _run_metrics("symbols", "▯", size)
        return float(image.width), image.height, 0, image
    font = _font(role, size)
    ascent, descent = font.getmetrics()
    return float(font.getlength(text)), ascent, descent, None


def _measure_text(text: str, size: int, base_role: str = "black") -> float:
    # Order-independent: the line is as wide as its runs however they sit.
    return sum(_run_metrics(role, value, size)[0]
               for role, value, _level in _runs(text, base_role))


def _render_text_line(text: str, size: int, fill: tuple[int, int, int, int],
                      base_role: str = "black") -> tuple[Image.Image, float]:
    runs = _visual(_runs(text, base_role))
    metrics = [(role, value, *_run_metrics(role, value, size)) for role, value, _lv in runs]
    width = sum(item[2] for item in metrics)
    ascent = max((item[3] for item in metrics), default=max(1, size))
    descent = max((item[4] for item in metrics), default=0)
    canvas = Image.new("RGBA", (max(1, int(math.ceil(width)) + 2), max(1, ascent + descent)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    x = 0.0
    for role, value, advance, run_ascent, _run_descent, run_image in metrics:
        if run_image is not None:
            canvas.alpha_composite(run_image, (int(round(x)), ascent - run_image.height))
        else:
            draw.text((x, ascent), value, font=_font(role, size), fill=fill, anchor="ls")
        x += advance
    return canvas, width


def _draw_text(image: Image.Image, xy: tuple[float, float], text: str, size: int,
               fill: tuple[int, int, int, int], anchor: str = "lm",
               base_role: str = "black") -> None:
    if not text:
        return
    line, width = _render_text_line(text, size, fill, base_role)
    x, y = xy
    if anchor.startswith("m"):
        x -= width / 2
    elif anchor.startswith("r"):
        x -= width
    if anchor.endswith("m"):
        y -= line.height / 2
    image.alpha_composite(line, (int(round(x)), int(round(y))))


def _fit_text(text: str, box_width: float, sizes: Iterable[int], base_role: str,
              *, normalize: bool = False) -> tuple[str, int]:
    value = " ".join(str(text).split()) if normalize else str(text)
    offered = tuple(max(1, int(size)) for size in sizes)
    if not offered:
        raise ValueError("font_sizes")
    for size in offered:
        if _measure_text(value, size, base_role) <= box_width:
            return value, size
    floor = offered[-1]
    clusters = graphemes(value)
    while clusters and _measure_text("".join(clusters) + "...", floor, base_role) > box_width:
        clusters.pop()
    return "".join(clusters) + "...", floor


# The name shrinks before it is cut: from 58 px down to the floor in steps of
# two. The tile used to stop at 56 (28 px drawn) and cut nearly every real
# name to eleven characters ("Twenty Char..."); the budget is now whatever
# the chips actually leave free rather than the layout rect's constant
# (2026-09-13, bug #361 feedback), and the tile has no floor of its own: its
# fit is the card's fit at half size, so a name whole on the card is whole on
# the tile by construction (r5 L11).
NAME_SIZE_MAX = 58
NAME_SIZE_MIN_CARD = 34
NAME_LEFT = 54               # anchors.name x in face_layout_v1
NAME_RIGHT_DEFAULT = 490     # the layout's name rect right edge: the budget when no chip edge is known
NAME_CHIP_GAP = 24           # card px kept clear between the name and the nearest chip


def _name_fit(name: str, size: str, right_edge: float | None = None) -> tuple[str, int]:
    """(fitted text, font px) for the name at `size`. `right_edge`, when
    given, is the x the name may not cross (the nearest chip's left edge less
    the gap, in that size's pixels); without it the layout rect applies."""
    if size not in ("card", "tile"):
        raise ValueError("size")
    if size == "tile":
        # Parity by construction: the fit is decided once, at card scale,
        # against the tile's edge doubled, and the chosen size is halved.
        # Halving keeps the text inside its budget to within the font's
        # rounding, well inside the 12 px the gap leaves clear at the tile.
        text, px = _name_fit(name, "card", None if right_edge is None else float(right_edge) * 2.0)
        budget = max(1.0, (NAME_RIGHT_DEFAULT * 0.5 if right_edge is None else float(right_edge)) - NAME_LEFT * 0.5)
        px = max(1, int(round(px * 0.5)))
        # hinting rounds advances up at small sizes: step down a pixel at a
        # time until the SAME text fits the tile's own budget (measured, not
        # assumed; three steps at most in practice)
        while px > 8 and _measure_text(text, px, "black") > budget:
            px -= 1
        return text, px
    sizes = list(range(NAME_SIZE_MAX, NAME_SIZE_MIN_CARD - 1, -2))
    right = NAME_RIGHT_DEFAULT if right_edge is None else float(right_edge)
    return _fit_text(str(name), max(1.0, right - NAME_LEFT), sizes, "black")


def fit_name(name: str, size: str) -> str:
    """Apply the pass-specific, end-only grapheme ellipsis transform F."""
    return _name_fit(name, size)[0]


# ---------------------------------------------------------------------------
# Drawing helpers and face composition
# ---------------------------------------------------------------------------

def _rgba(colour: Sequence[int], alpha: int = 255) -> tuple[int, int, int, int]:
    return int(colour[0]), int(colour[1]), int(colour[2]), int(alpha)


def _mix(left: Sequence[int], right: Sequence[int], amount: float) -> tuple[int, int, int]:
    return tuple(int(round(left[i] + (right[i] - left[i]) * amount)) for i in range(3))


def _luminance(colour: Sequence[int]) -> float:
    return 0.299 * colour[0] + 0.587 * colour[1] + 0.114 * colour[2]


def _vertical_gradient(size: tuple[int, int], top: Sequence[int], bottom: Sequence[int]) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size)
    pixels = image.load()
    for y in range(height):
        colour = _mix(top, bottom, y / max(1, height - 1))
        for x in range(width):
            pixels[x, y] = _rgba(colour)
    return image


def _noise_bytes(width: int, height: int, seed: int) -> bytes:
    # xorshift32 is specified here rather than delegating to a process-global
    # generator; its output is identical across Python and Pillow releases.
    state = (int(seed) & 0xFFFFFFFF) or 0x6D2B79F5
    output = bytearray(width * height)
    for index in range(len(output)):
        state ^= state << 13 & 0xFFFFFFFF
        state ^= state >> 17
        state ^= state << 5 & 0xFFFFFFFF
        state &= 0xFFFFFFFF
        output[index] = state & 0xFF
    return bytes(output)


def _grain_layer(width: int, height: int, alpha: int, seed: int) -> Image.Image:
    noise = Image.frombytes("L", (width, height), _noise_bytes(width, height, seed))
    opacity = noise.point([int(alpha * value / 255) for value in range(256)])
    layer = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    layer.putalpha(opacity)
    return layer


def _rounded_mask(width: int, height: int, radius: int) -> Image.Image:
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
    return mask


def _clip_rounded(image: Image.Image, radius: int) -> Image.Image:
    output = Image.new("RGBA", image.size, (0, 0, 0, 0))
    output.paste(image.convert("RGBA"), (0, 0), _rounded_mask(*image.size, radius))
    return output


def _scale_value(value: float, scale: float) -> int:
    return int(math.floor(value * scale + 0.5))


def _scale_rect(rect: Sequence[int], scale: float) -> tuple[int, int, int, int]:
    return tuple(_scale_value(value, scale) for value in rect)  # type: ignore[return-value]


@functools.lru_cache(maxsize=64)
def _asset(name: str, size: str) -> Image.Image:
    with Image.open(_ASSETS_PATH / name) as source:
        source.load()
        image = source.copy()
    if size == "tile":
        image = image.reduce(2)
    return image


def _effective_labels(labels: dict) -> dict[str, str]:
    supplied = labels if isinstance(labels, dict) else {}
    return {identifier: str(supplied.get(identifier, english)) for identifier, english in ENGLISH.items()}


STEAM_PICTURE_MIN_EDGE, STEAM_PICTURE_MAX_EDGE = 32, 1024


def steam_picture_ihdr(ihdr: tuple[int, int, int, int, int]) -> bool:
    """A stored Steam profile picture: square straight-alpha RGBA, 32–1024 px
    (design v2 §2/§5). The rig's 1180 lies outside the range by construction."""
    width, height, depth, colour_type, interlace = ihdr
    return (width == height and STEAM_PICTURE_MIN_EDGE <= width <= STEAM_PICTURE_MAX_EDGE
            and (depth, colour_type, interlace) == (8, 6, 0))


def _portrait_bg() -> tuple[int, int, int, int]:
    return tuple(int(LAYOUT["portrait_bg"][i:i + 2], 16) for i in (1, 3, 5)) + (255,)


def _portrait_image(portrait_png: bytes, output_edge: int) -> Image.Image:
    """The portrait square from a stored blob of either shape: the rig
    (1180×1180, composited over portrait_bg and reduced) or a Steam profile
    picture (square 32–1024, composited the same way and LANCZOS-resized to
    the edge — no upscale filter beyond that; a 184 px picture at 590 is soft,
    and that is what the account offers). Any other header is invalid."""
    ihdr = png_ihdr(portrait_png)
    rig = ihdr == _PORTRAIT_IHDR
    if not rig and not steam_picture_ihdr(ihdr):
        raise ValueError("portrait_invalid")
    try:
        with Image.open(io.BytesIO(portrait_png)) as source:
            source.load()
            if source.mode != "RGBA" or source.size != (ihdr[0], ihdr[1]):
                raise ValueError("portrait_invalid")
            foreground = Image.frombytes("RGBA", source.size, source.tobytes())
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("portrait_invalid") from exc
    composed = Image.alpha_composite(Image.new("RGBA", foreground.size, _portrait_bg()), foreground)
    if rig:
        return composed.reduce(PORTRAIT_SRC // output_edge)
    return composed.resize((output_edge, output_edge), Image.Resampling.LANCZOS)


def _emblem_plate(colour: Sequence[int], edge: int) -> Image.Image:
    """The no-picture portrait (design v2 §5): the band-tinted plate carrying
    the card back's motif — no letter, no figure. It is what opt-out, None,
    deletion, a ban and a picture that could not be fetched show, and it is
    deliberately not a person. Drawn once at the card edge; the tile is its
    exact reduction, so both sizes agree."""
    base = _rgba(_mix(colour, LAYOUT["colours"]["card"], 0.78))
    ink = _rgba(_mix(colour, LAYOUT["colours"]["card"], 0.55))
    plate = Image.new("RGBA", (PORTRAIT_CARD, PORTRAIT_CARD), base)
    for angle, dx in ((-18, -70), (18, 70), (0, 0)):
        card = Image.new("RGBA", (170, 238), (0, 0, 0, 0))
        mini = ImageDraw.Draw(card)
        mini.rounded_rectangle((0, 0, 169, 237), radius=18, fill=ink)
        mini.rounded_rectangle((19, 19, 150, 150), radius=12, fill=base)
        mini.ellipse((56, 56, 113, 113), fill=ink)
        mini.rounded_rectangle((19, 166, 150, 182), radius=5, fill=base)
        mini.rounded_rectangle((19, 194, 100, 210), radius=5, fill=base)
        rotated = card.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        plate.alpha_composite(rotated, (PORTRAIT_CARD // 2 - rotated.width // 2 + dx,
                                        PORTRAIT_CARD // 2 - rotated.height // 2 - (0 if angle else 14)))
    return plate if edge == PORTRAIT_CARD else plate.reduce(PORTRAIT_CARD // edge)


def _foil(body: Image.Image, size: str) -> Image.Image:
    overlay = _asset("FoilOverlay.png", size).convert("RGBA")
    mask = _asset("FoilMask.png", size).convert("L")
    screened = ImageChops.screen(body.convert("RGB"), overlay.convert("RGB"))
    strength = ImageChops.multiply(overlay.getchannel("A"), mask)
    opacity = float(LAYOUT["materials"]["foil_global_opacity"])
    strength = strength.point([max(0, min(255, int(value * opacity))) for value in range(256)])
    output = Image.composite(screened, body.convert("RGB"), strength).convert("RGBA")
    output.putalpha(body.getchannel("A"))
    return output


def _fit_range(maximum: int, minimum: int, scale: float, step: int = 1) -> list[int]:
    values = []
    for value in range(maximum, minimum - 1, -step):
        scaled = max(1, _scale_value(value, scale))
        if not values or values[-1] != scaled:
            values.append(scaled)
    return values


def _draw_fitted(image: Image.Image, xy: tuple[int, int], text: str, box_width: int,
                 maximum: int, minimum: int, scale: float, fill: tuple[int, int, int, int],
                 anchor: str, base_role: str, step: int = 1) -> tuple[str, int]:
    fitted, font_size = _fit_text(
        text,
        box_width,
        _fit_range(maximum, minimum, scale, step),
        base_role,
        normalize=True,
    )
    _draw_text(image, xy, fitted, font_size, fill, anchor, base_role)
    return fitted, font_size


def _draw_chip(image: Image.Image, x_right: int, y: int, full: str, short: str,
               colour: tuple[int, int, int], text_colour: tuple[int, int, int],
               scale: float, tile: bool) -> int:
    """Draw one right-anchored chip; returns its LEFT edge x, which is what
    the name's budget is measured against."""
    height = _scale_value(44, scale)
    padding = _scale_value(20, scale)
    max_width = _scale_value(194, scale)
    size_values = [_scale_value(26, scale)] if tile else [_scale_value(value, scale) for value in (26, 24, 22)]
    candidates = [short] if tile else [full] + ([short] if short != full else [])
    chosen: tuple[str, int] | None = None
    for candidate in candidates:
        for font_size in size_values:
            if _measure_text(candidate, font_size, "bold") + 2 * padding <= max_width:
                chosen = candidate, font_size
                break
        if chosen is not None:
            break
    if chosen is None:
        candidate = candidates[-1]
        font_size = size_values[-1]
        available = max_width - 2 * padding
        candidate, _ = _fit_text(candidate, available, (font_size,), "bold", normalize=True)
        chosen = candidate, font_size
    label, font_size = chosen
    width = min(max_width, int(math.ceil(_measure_text(label, font_size, "bold"))) + 2 * padding)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (x_right - width, y, x_right, y + height),
        radius=_scale_value(22, scale),
        fill=_rgba(colour),
    )
    _draw_text(image, (x_right - width / 2, y + height / 2 + _scale_value(1, scale)),
               label, font_size, _rgba(text_colour), "mm", "bold")
    return x_right - width


def _draw_badge(image: Image.Image, band_colour: tuple[int, int, int], labels: dict[str, str],
                scale: float, size: str) -> None:
    badge = _scale_rect(LAYOUT["rects"]["badge"], scale)
    ImageDraw.Draw(image).rounded_rectangle(
        badge,
        radius=_scale_value(20, scale),
        fill=_rgba(LAYOUT["colours"]["card"]),
    )
    neutral = _asset("BadgeFrame.png", size).convert("RGBA")
    tint = Image.new("RGBA", neutral.size, _rgba(band_colour))
    tinted = ImageChops.multiply(neutral, tint)
    tinted.putalpha(neutral.getchannel("A"))
    image.alpha_composite(tinted)
    draw = ImageDraw.Draw(image)
    mark = _scale_rect(LAYOUT["rects"]["badge_mark"], scale)
    radius = _scale_value(7, scale)
    draw.rounded_rectangle(mark, radius=radius, fill=(240, 240, 244, 255),
                           outline=(30, 30, 30, 255), width=max(1, _scale_value(3, scale)))
    inner = _scale_rect((102, 666, 134, 690), scale)
    draw.rectangle(inner, fill=(30, 30, 30, 255))
    anchor = tuple(_scale_value(value, scale) for value in LAYOUT["anchors"]["badge_label"])
    _draw_fitted(image, anchor, labels["pc.top_card"], _scale_value(108, scale),
                 11, 8, scale, _rgba(band_colour), "mm", "bold")


def _autograph_fit(name: str, scale: float) -> tuple[str, int]:
    max_width = _scale_value(380, scale)
    sizes = _fit_range(96, 40, scale, 4)
    return _fit_text(name, max_width, sizes, "script")


def _draw_autograph(image: Image.Image, name: str, scale: float) -> None:
    box = _scale_rect(LAYOUT["rects"]["autograph"], scale)
    center = tuple(_scale_value(value, scale) for value in LAYOUT["anchors"]["autograph"])
    fitted, font_size = _autograph_fit(name, scale)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow = _scale_value(4, scale)
    _draw_text(layer, (center[0] + shadow, center[1] + shadow), fitted, font_size,
               (0, 0, 0, 200), "mm", "script")
    _draw_text(layer, center, fitted, font_size, _rgba(LAYOUT["colours"]["sign"]), "mm", "script")
    layer = layer.rotate(6, resample=Image.Resampling.BICUBIC, center=center)
    clipped = Image.new("RGBA", image.size, (0, 0, 0, 0))
    clipped.alpha_composite(layer)
    clip = Image.new("L", image.size, 0)
    ImageDraw.Draw(clip).rectangle(box, fill=255)
    clipped.putalpha(ImageChops.multiply(clipped.getchannel("A"), clip))
    image.alpha_composite(clipped)


def _draw_seal(image: Image.Image, labels: dict[str, str], scale: float, size: str) -> None:
    image.alpha_composite(_asset("SignedSeal.png", size).convert("RGBA"))
    anchor = tuple(_scale_value(value, scale) for value in LAYOUT["anchors"]["seal_label"])
    _draw_fitted(image, anchor, labels["pc.signed"], _scale_value(88, scale),
                 22, 14, scale, (60, 40, 10, 255), "mm", "bold")


def _draw_stats(image: Image.Image, spec: dict, labels: dict[str, str], scale: float) -> None:
    label_colour = _rgba(LAYOUT["colours"]["label"])
    white = _rgba(LAYOUT["colours"]["white"])
    anchors = LAYOUT["anchors"]
    entries = (
        ("pc.stat.rank", "stat_rank_label", 224, 22, "lm"),
        ("pc.stat.rating", "stat_rating_label", 224, 22, "rm"),
        ("pc.stat.pool", "stat_pool_label", 160, 20, "lm"),
        ("pc.stat.board", "stat_board_label", 160, 20, "mm"),
        ("pc.stat.record", "stat_record_label", 160, 20, "rm"),
    )
    for identifier, anchor_name, width, maximum, anchor in entries:
        xy = tuple(_scale_value(value, scale) for value in anchors[anchor_name])
        _draw_fitted(image, xy, labels[identifier], _scale_value(width, scale), maximum, 14,
                     scale, label_colour, anchor, "bold")

    title = "" if spec.get("title") is None else str(spec["title"])
    title_colour = spec.get("title_rgb")
    if title_colour is None:
        title_colour = LAYOUT["colours"]["label"]
    xy = tuple(_scale_value(value, scale) for value in anchors["stat_title_value"])
    _draw_fitted(image, xy, title, _scale_value(380, scale), 40, 28, scale,
                 _rgba(title_colour), "lm", "black")

    rating = labels["pc.unranked"] if spec.get("rating") is None else str(int(spec["rating"]))
    xy = tuple(_scale_value(value, scale) for value in anchors["stat_rating_value"])
    _draw_fitted(image, xy, rating, _scale_value(198, scale), 66, 28, scale,
                 white, "rm", "black")

    board_rank = "—" if spec.get("board_rank") is None else f"#{int(spec['board_rank'])}"
    values = (
        (f"#{int(spec['pool_rank'])}", "stat_pool_value", "lm"),
        (board_rank, "stat_board_value", "mm"),
        (f"{int(spec['wins'])}W  {int(spec['losses'])}L", "stat_record_value", "rm"),
    )
    for value, anchor_name, anchor in values:
        xy = tuple(_scale_value(component, scale) for component in anchors[anchor_name])
        _draw_fitted(image, xy, value, _scale_value(160, scale), 32, 20, scale,
                     white, anchor, "black")


def render_face(spec: dict, labels: dict, portrait_png: bytes | None, size: str) -> bytes:
    """Render one Player Card face as canonical RGBA PNG bytes."""
    if size not in ("card", "tile"):
        raise ValueError("size")
    if not isinstance(spec, dict) or spec.get("band") not in BANDS:
        raise ValueError("band")
    scale = 1.0 if size == "card" else 0.5
    output_size = (CARD_W, CARD_H) if size == "card" else (TILE_W, TILE_H)
    band = str(spec["band"])
    colour = tuple(int(value) for value in LAYOUT["colours"]["bands"][band])
    effective = _effective_labels(labels)
    raw_name = "" if spec.get("name") is None else str(spec.get("name"))
    display_name = raw_name or effective["pc.unnamed"]

    body = _asset(f"Base_{band}.png", size).convert("RGBA").copy()

    portrait_rect = _scale_rect(LAYOUT["rects"]["portrait"], scale)
    portrait_edge = PORTRAIT_CARD if size == "card" else PORTRAIT_TILE
    # No picture = the emblem plate, never a letter or a figure (2026-09-12).
    portrait = (_portrait_image(portrait_png, portrait_edge) if portrait_png is not None
                else _emblem_plate(colour, portrait_edge))
    portrait_mask = _rounded_mask(portrait_edge, portrait_edge, _scale_value(28, scale))
    body.paste(portrait, portrait_rect[:2], portrait_mask)

    body = Image.alpha_composite(body, _asset(f"Frame_{band}.png", size).convert("RGBA"))
    body = Image.alpha_composite(body, _asset(f"Plates_{band}.png", size).convert("RGBA"))
    if bool(spec.get("foil")):
        body = _foil(body, size)

    _draw_stats(body, spec, effective, scale)
    if bool(spec.get("top_card")):
        _draw_badge(body, colour, effective, scale, size)
    if bool(spec.get("signed")):
        _draw_autograph(body, display_name, scale)
        _draw_seal(body, effective, scale, size)

    chip_text = (0, 0, 0) if _luminance(colour) > 150 else (255, 255, 255)
    right = _scale_value(696, scale)
    chip_left = _draw_chip(body, right, _scale_value(38, scale), effective[f"pc.band.{band}"],
                           effective[f"pc.band_short.{band}"], colour, chip_text, scale, size == "tile")
    if bool(spec.get("foil")):
        # The foil chip sits in the name's row too (88..132 against a name
        # centred on 85), so the nearer of the two edges bounds the name.
        chip_left = min(chip_left, _draw_chip(body, right, _scale_value(88, scale), effective["pc.foil"],
                                              effective["pc.foil_short"], (255, 255, 255), (20, 20, 24),
                                              scale, size == "tile"))

    fitted_name, name_size = _name_fit(display_name, size, chip_left - _scale_value(NAME_CHIP_GAP, scale))
    subtitle = "" if spec.get("subtitle") is None else str(spec["subtitle"]).strip()
    # A shop title the player wears sits under the name as a subtitle; the
    # name moves up to make the room (the RANK slot below draws the tier and
    # only the tier — 2026-09-12). No subtitle: the name keeps its anchor.
    name_key = "name_subtitled" if subtitle else "name"
    name_anchor = tuple(_scale_value(value, scale) for value in LAYOUT["anchors"][name_key])
    _draw_text(body, name_anchor, fitted_name, name_size, _rgba(LAYOUT["colours"]["white"]),
               "lm", "black")
    if subtitle:
        sub_anchor = tuple(_scale_value(value, scale) for value in LAYOUT["anchors"]["subtitle"])
        _draw_fitted(body, sub_anchor, subtitle, _scale_value(436, scale), 22, 14, scale,
                     _rgba(LAYOUT["colours"]["label"]), "lm", "bold")

    if size == "card":
        # The separator belongs BETWEEN two parts. The /card preview has no
        # minted date, and drawing it anyway left the footer ending in a
        # dangling "·" under the preview label.
        footer_left = "  ·  ".join(part for part in (str(spec.get("edition_label") or "").strip(),
                                                     str(spec.get("minted_on") or "").strip()) if part)
        footer_right = str(spec.get("print_short", ""))
        left_xy = tuple(LAYOUT["anchors"]["footer_left"])
        right_xy = tuple(LAYOUT["anchors"]["footer_right"])
        footer_fill = _rgba(LAYOUT["colours"]["dim"])
        _draw_fitted(body, left_xy, footer_left, 500, 22, 14, 1.0,
                     footer_fill, "lm", "bold")
        _draw_fitted(body, right_xy, footer_right, 150, 22, 14, 1.0,
                     footer_fill, "rm", "bold")

    body = _clip_rounded(body, _scale_value(40, scale))
    if body.size != output_size:
        raise ValueError("asset_size")
    output = _encode_rgba(body)
    ceiling = 4 << 20 if size == "card" else 1 << 20
    if len(output) > ceiling:
        raise ValueError("face_too_large")
    return output


def render_back() -> bytes:
    """Render the canonical 750x1050 card back."""
    body = _vertical_gradient((CARD_W, CARD_H), (34, 37, 48), (14, 15, 20))
    body = Image.alpha_composite(body, _grain_layer(CARD_W, CARD_H, 26, 3))
    draw = ImageDraw.Draw(body)
    draw.rounded_rectangle((0, 0, CARD_W - 1, CARD_H - 1), radius=40,
                           outline=(70, 74, 90, 255), width=14)
    draw.rounded_rectangle((30, 30, CARD_W - 31, CARD_H - 31), radius=28,
                           outline=(120, 126, 150, 255), width=3)
    draw.rounded_rectangle((44, 44, CARD_W - 45, CARD_H - 45), radius=24,
                           outline=(50, 53, 66, 255), width=2)
    for angle, dx, colour in ((-18, -82, (150, 156, 178)),
                              (18, 82, (150, 156, 178)),
                              (0, 0, (235, 236, 240))):
        card = Image.new("RGBA", (200, 280), (0, 0, 0, 0))
        mini = ImageDraw.Draw(card)
        mini.rounded_rectangle((0, 0, 199, 279), radius=22, fill=_rgba(colour),
                               outline=(20, 22, 28, 255), width=6)
        mini.rounded_rectangle((22, 22, 177, 177), radius=14, fill=(40, 43, 54, 255))
        mini.ellipse((66, 66, 133, 133), fill=(96, 101, 124, 255))
        mini.rounded_rectangle((22, 196, 177, 214), radius=6, fill=(40, 43, 54, 255))
        mini.rounded_rectangle((22, 228, 118, 246), radius=6, fill=(40, 43, 54, 255))
        rotated = card.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        body.alpha_composite(rotated, (375 - rotated.width // 2 + dx,
                                       470 - rotated.height // 2 - (0 if angle else 16)))
    _draw_text(body, (375, 700), "PLAYER CARDS", 46, (200, 204, 220, 255), "mm", "black")
    _draw_text(body, (375, 748), "COMPETITIVE ROUNDS", 22,
               (120, 126, 150, 255), "mm", "bold")
    return _encode_rgba(_clip_rounded(body, 40))


# ---------------------------------------------------------------------------
# Reproducibility identity
# ---------------------------------------------------------------------------

def _feature_record(name: str) -> dict[str, object]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        available = bool(features.check(name))
        try:
            version = features.version(name) if available else None
        except Exception:
            version = None
    return {"available": available, "version": None if version is None else str(version)}


def _frame_hash_record(digest, label: str, payload: bytes) -> None:
    label_bytes = label.encode("utf-8")
    digest.update(len(label_bytes).to_bytes(4, "big"))
    digest.update(label_bytes)
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)


def _frame_package_field(digest, payload: bytes) -> None:
    digest.update(len(payload).to_bytes(4, "big"))
    digest.update(payload)


@functools.lru_cache(maxsize=1)
def _package_digest() -> str:
    roots = [("PIL", Path(PIL.__file__).resolve().parent)]
    sibling = roots[0][1].parent / "pillow.libs"
    if sibling.is_dir():
        roots.append(("pillow.libs", sibling))
    records: list[tuple[str, str, Path]] = []
    for root_name, root in roots:
        for path in root.rglob("*"):
            relative = path.relative_to(root)
            if (not path.is_file() or "__pycache__" in relative.parts
                    or path.suffix.lower() in (".pyc", ".pyo")):
                continue
            records.append((root_name, relative.as_posix(), path))
    digest = hashlib.sha256()
    for root_name, relative, path in sorted(records, key=lambda item: (item[1], item[0])):
        _frame_package_field(digest, root_name.encode("utf-8"))
        _frame_package_field(digest, relative.encode("utf-8"))
        _frame_package_field(digest, path.read_bytes())
    return digest.hexdigest()


def runtime_provenance() -> dict:
    """Return the path-free interpreter, Pillow, shaping, and package identity."""
    return {
        "python": platform.python_version(),
        "PIL": PIL.__version__,
        # The grapheme splitter is the third-party `regex` module (`\X`), not
        # the stdlib, so its behaviour moves with its own releases: a bump that
        # changes cluster boundaries changes where text wraps and which pixels
        # land, under an unchanged Python.
        "regex": regex.__version__,
        "features": {name: _feature_record(name) for name in
                     ("zlib", "freetype2", "harfbuzz", "fribidi", "raqm")},
        "layout_engine": "raqm" if _HAS_RAQM else "basic",
        "package_digest": _package_digest(),
    }


def _require_every_font() -> None:
    """Raise unless every font the renderer draws with is present.

    The fingerprint is built by walking the font directory, so a missing font
    simply made a smaller walk: `renderer_fingerprint()` answered, health
    reported a non-null `pc_renderer_fp`, the deploy assertion passed, and the
    FIRST face request was what discovered the file was not there — a 500 on a
    player's card instead of a refusal at boot. The set the renderer needs is
    declared, so it is required rather than discovered."""
    missing = sorted(name for name in _FONT_FILES.values()
                     if not (_FONTS_PATH / name).is_file())
    if missing:
        raise FileNotFoundError("fonts missing: " + ", ".join(missing))


def _fingerprint_inputs() -> tuple[str, tuple[tuple[str, int, int], ...]]:
    _require_every_font()
    semantic_layout = json.dumps(LAYOUT, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"))
    paths = [Path(__file__), _ASSETS_PATH / "face_layout_v1.json", _ASSETS_PATH / "catalogue.json",
             _ASSETS_PATH / "name_coverage.json"]
    paths.extend(sorted((path for path in _ASSETS_PATH.rglob("*")
                         if path.is_file() and path.suffix.lower() == ".png"),
                        key=lambda path: path.relative_to(_ASSETS_PATH).as_posix()))
    paths.extend(sorted((path for path in _FONTS_PATH.iterdir()
                         if path.is_file() and path.suffix.lower() in (".ttf", ".otf")),
                        key=lambda path: path.name))
    stamps = tuple((str(path), path.stat().st_size, path.stat().st_mtime_ns) for path in paths)
    return semantic_layout, stamps


@functools.lru_cache(maxsize=8)
def _renderer_fingerprint_cached(semantic_layout: str,
                                 _stamps: tuple[tuple[str, int, int], ...]) -> str:
    provenance = runtime_provenance()
    records: list[tuple[str, bytes]] = [
        ("source/pc_face.py", Path(__file__).read_bytes()),
        ("manifest/face_layout_v1.json", (_ASSETS_PATH / "face_layout_v1.json").read_bytes()),
        ("manifest/catalogue.json", (_ASSETS_PATH / "catalogue.json").read_bytes()),
        # The coverage manifest decides which code points survive into a name,
        # so a change to it draws different pixels and must re-key every face.
        ("manifest/name_coverage.json", (_ASSETS_PATH / "name_coverage.json").read_bytes()),
        ("manifest/layout_runtime.json", semantic_layout.encode("utf-8")),
    ]
    asset_pngs = (path for path in _ASSETS_PATH.rglob("*")
                  if path.is_file() and path.suffix.lower() == ".png")
    for path in sorted(asset_pngs, key=lambda item: item.relative_to(_ASSETS_PATH).as_posix()):
        relative = path.relative_to(_ASSETS_PATH).as_posix()
        records.append((f"assets/{relative}", path.read_bytes()))
    for path in sorted((item for item in _FONTS_PATH.iterdir()
                        if item.is_file() and item.suffix.lower() in (".ttf", ".otf")),
                       key=lambda item: item.name):
        records.append((f"fonts/{path.name}", path.read_bytes()))
    provenance_identity = {key: value for key, value in provenance.items()
                           if key != "package_digest"}
    provenance_bytes = json.dumps(provenance_identity, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8")
    records.append(("runtime/provenance.json", provenance_bytes))
    records.append(("runtime/package_digest", provenance["package_digest"].encode("ascii")))
    digest = hashlib.sha256()
    for label, payload in records:
        _frame_hash_record(digest, label, payload)
    return digest.hexdigest()[:16]


def renderer_fingerprint() -> str:
    """Return the cached 16-hex identity of every rendering dependency."""
    semantic_layout, stamps = _fingerprint_inputs()
    return _renderer_fingerprint_cached(semantic_layout, stamps)


# No `renderer_fingerprint.cache_clear` alias here. Nothing called it -- the
# lru_cache sits on _renderer_fingerprint_cached and is keyed on the layout and
# the stamps, so a changed input already returns a new value without anyone
# clearing anything. It also made this module-level name disagree with itself:
# the reviewed-surface index reads every module-level statement that binds
# `renderer_fingerprint`, so the alias landed inside its segment while
# inspect.getsource returned the def alone.
