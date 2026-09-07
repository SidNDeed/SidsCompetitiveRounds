#!/usr/bin/env python3
"""Build the colour-emoji sprite atlas for the mod's TextMeshPro labels (bug 333 step 2).

Inputs (the tool downloads NOTHING - fetch these yourself):

  * NotoColorEmoji.ttf  - Google's Noto Color Emoji, CBDT bitmap strikes at 109 ppem.
        https://github.com/googlefonts/noto-emoji  (fonts/NotoColorEmoji.ttf)
        Licence: SIL Open Font License 1.1 (fonts/LICENSE in that repository). The
        licence text MUST ship beside the atlas; pass it with --licence (or keep a
        LICENSE*/OFL* file next to the .ttf and the tool picks it up).
  * emoji-test.txt      - Unicode's emoji test data; the "fully-qualified" rows are
        the default sequence list.  https://unicode.org/Public/emoji/latest/emoji-test.txt

Outputs (deterministic: same font + same list + same options => byte-identical index
and identical sheet pixels):

  emoji-sheet-0.png            RGBA, --sheet px square (default 2048), --cell px cells
                               (default 48 => 42 x 42 = 1,764 cells). A second sheet
                               only when the list overflows; the runtime accepts at most
                               MAX_RUNTIME_SHEETS.
  emoji-index.json             {"version":"emoji-atlas-v1","cell":48,"sheet":2048,
                               "pad":1,"origin":"top-left","ascent":<px from the cell
                               top to the baseline>,"sheets":[{"file","sha256","bytes",
                               "cells_used"}],"sequences":{"1F600":[sheet,x,y],
                               "1F468-200D-1F469-200D-1F467":[sheet,x,y],...}}
                               Keys are the hyphenated upper-case hex code-point
                               SEQUENCE exactly as the fully-qualified form spells it
                               (VS16 / ZWJ / skin-tone modifiers included). x,y are the
                               cell's top-left pixel in PNG coordinates.
  LICENSE-NotoColorEmoji.txt   the licence text, copied verbatim.
  emoji-atlas-report.txt       counts + every skipped sequence with its reason.

Rendering. The design named Pillow's ImageFont at size 109 with embedded_color=True.
That works for single code points, but Pillow's BASIC layout engine (what a stock
Windows install of Pillow has - libraqm is absent) does no GSUB shaping, so ZWJ
families, skin tones, flags and keycaps come out as separate glyphs. This tool
therefore has two renderers and picks automatically (--renderer to force):

  cbdt    (default when the font has CBDT+GSUB tables): resolve the sequence through
          the font's own cmap + GSUB ligature lookups and lift the embedded PNG strike
          for the resulting glyph. Full sequence coverage, no shaping engine needed.
  pillow  the design's mechanism; sequences the layout engine cannot shape are
          detected (multi-glyph advance, blank, .notdef) and skipped with a reason.

Both renderers hand back an RGBA canvas whose top edge is the ascender line and bottom
edge the descender line, so one "ascent" value places every glyph on the baseline.

The Matcher class near the bottom is the reference implementation of the runtime's
longest-match substitution (plugin/EmojiSprites.cs mirrors it and self-checks the same
vectors; backend/tests/test_emoji_atlas.py compares the two vector lists as text).

Release step (the integrator's): the tool also writes emoji-atlas-v1.zip (flat: index,
sheets, licence) and prints the index's SHA-256 - paste that hex into
EmojiSprites.INDEX_SHA256. The runtime refuses any index whose hash differs, and each
sheet is checked against the sha256 the index carries, so the DLL pins the bytes the way
MusicAssets.ASSET_REVISION pins the music (#458). Publish the zip on the dedicated
immutable GitHub release "emoji-atlas-v1" with --latest=false (#474), never on a
version release and never under /latest/.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import struct
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ATLAS_VERSION = "emoji-atlas-v1"
DEFAULT_CELL = 48
DEFAULT_SHEET = 2048
DEFAULT_PAD = 1
NOTO_STRIKE_PPEM = 109
MAX_RUNTIME_SHEETS = 2          # plugin/EmojiSprites.cs rejects an index with more
SPRITE_NAME_PREFIX = "e_"       # TMP hashes sprite names case-sensitively on both sides (3.x)
INDEX_FILE = "emoji-index.json"
SHEET_FILE = "emoji-sheet-{}.png"
LICENCE_FILE = "LICENSE-NotoColorEmoji.txt"
REPORT_FILE = "emoji-atlas-report.txt"
ZIP_FILE = ATLAS_VERSION + ".zip"

VS16 = 0xFE0F
ZWJ = 0x200D
SKIN_TONE_MIN, SKIN_TONE_MAX = 0x1F3FB, 0x1F3FF
FULLY_QUALIFIED = "fully-qualified"


# ---------------------------------------------------------------------------
# emoji-test.txt
# ---------------------------------------------------------------------------

@dataclass
class EmojiTestEntry:
    cps: Tuple[int, ...]
    status: str
    name: str
    group: str
    subgroup: str

    @property
    def key(self) -> str:
        return seq_key(self.cps)


def seq_key(cps: Sequence[int]) -> str:
    """'1F468-200D-1F469' - upper-case hex, hyphen separated, no zero padding beyond 4."""
    return "-".join("%04X" % cp for cp in cps)


def key_to_cps(key: str) -> Tuple[int, ...]:
    return tuple(int(part, 16) for part in key.split("-") if part)


def parse_emoji_test(lines: Iterable[str]) -> List[EmojiTestEntry]:
    """Parse emoji-test.txt rows: '<cps> ; <status> # <emoji> E<ver> <name>'."""
    out: List[EmojiTestEntry] = []
    group = subgroup = ""
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        if line.startswith("#"):
            body = line[1:].strip()
            if body.startswith("group:"):
                group = body[len("group:"):].strip()
            elif body.startswith("subgroup:"):
                subgroup = body[len("subgroup:"):].strip()
            continue
        left, _, comment = line.partition("#")
        cps_part, semi, status = left.partition(";")
        if not semi:
            continue
        try:
            cps = tuple(int(tok, 16) for tok in cps_part.split())
        except ValueError:
            continue
        if not cps:
            continue
        name = ""
        toks = comment.strip().split(None, 2)
        if len(toks) == 3:
            name = toks[2]
        out.append(EmojiTestEntry(cps, status.strip(), name, group, subgroup))
    return out


def is_skin_tone(cp: int) -> bool:
    return SKIN_TONE_MIN <= cp <= SKIN_TONE_MAX


def has_skin_tone(cps: Sequence[int]) -> bool:
    return any(is_skin_tone(cp) for cp in cps)


def select_sequences(entries: Iterable[EmojiTestEntry], include_skin_tones: bool = False,
                     statuses: Sequence[str] = (FULLY_QUALIFIED,)) -> List[str]:
    """Ordered, de-duplicated keys. Default: fully-qualified rows without skin-tone
    modifiers (the ~1,400 that fit one sheet). The runtime shows the neutral base for a
    toned emoji the atlas lacks, so excluding tones costs nothing but the tint."""
    wanted = set(statuses)
    seen = set()
    keys: List[str] = []
    for e in entries:
        if e.status not in wanted:
            continue
        if not include_skin_tones and has_skin_tone(e.cps):
            continue
        k = e.key
        if k in seen:
            continue
        seen.add(k)
        keys.append(k)
    return keys


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def cells_per_sheet(cell: int, sheet: int) -> int:
    per_row = sheet // cell
    return per_row * per_row


def plan_layout(keys: Sequence[str], cell: int, sheet: int) -> Dict[str, Tuple[int, int, int]]:
    """Row-major, sequential, in input order: key -> (sheet, x, y) with x,y the cell's
    top-left pixel (PNG top-left origin). Pure function; same input => same output."""
    if cell <= 0 or sheet < cell:
        raise ValueError("cell must be > 0 and sheet >= cell")
    per_row = sheet // cell
    per_sheet = per_row * per_row
    plan: Dict[str, Tuple[int, int, int]] = {}
    for i, k in enumerate(keys):
        if k in plan:
            raise ValueError("duplicate key " + k)
        s, r = divmod(i, per_sheet)
        row, col = divmod(r, per_row)
        plan[k] = (s, col * cell, row * cell)
    return plan


def glyph_rect_bottom_left(x_top_left: int, y_top_left: int, cell: int, sheet: int) -> Tuple[int, int, int, int]:
    """The runtime's GlyphRect for an index entry: Unity texture space has its origin at
    the BOTTOM-left, PNG coordinates at the top-left."""
    return (x_top_left, sheet - y_top_left - cell, cell, cell)


# ---------------------------------------------------------------------------
# OpenType parsing (only what the CBDT renderer needs)
# ---------------------------------------------------------------------------

def _u8(b, o): return b[o]
def _s8(b, o): return struct.unpack_from(">b", b, o)[0]
def _u16(b, o): return struct.unpack_from(">H", b, o)[0]
def _s16(b, o): return struct.unpack_from(">h", b, o)[0]
def _u24(b, o): return (b[o] << 16) | (b[o + 1] << 8) | b[o + 2]
def _u32(b, o): return struct.unpack_from(">I", b, o)[0]


def read_table_directory(font: bytes) -> Dict[str, bytes]:
    """tag -> table bytes. TrueType / OpenType / first font of a TTC."""
    off = 0
    tag = font[:4]
    if tag == b"ttcf":
        off = _u32(font, 12)
    num = _u16(font, off + 4)
    tables: Dict[str, bytes] = {}
    for i in range(num):
        rec = off + 12 + 16 * i
        t = font[rec:rec + 4].decode("latin1")
        toff = _u32(font, rec + 8)
        tlen = _u32(font, rec + 12)
        tables[t] = font[toff:toff + tlen]
    return tables


class Cmap:
    """Unicode -> glyph id from a cmap table (formats 12 and 4), plus format 14
    variation sequences (non-default mappings and default-UVS ranges)."""

    def __init__(self, table: bytes):
        self.groups: List[Tuple[int, int, int]] = []       # format 12 (start, end, startGid)
        self.f4: Optional[Tuple[bytes, int, int]] = None    # (table, subtable offset, segCount)
        self.uvs_nondefault: Dict[Tuple[int, int], int] = {}
        self.uvs_default: Dict[int, List[Tuple[int, int]]] = {}
        num = _u16(table, 2)
        best12 = best4 = f14 = None
        for i in range(num):
            rec = 4 + 8 * i
            pid, eid, off = _u16(table, rec), _u16(table, rec + 2), _u32(table, rec + 4)
            fmt = _u16(table, off)
            if fmt == 12 and (best12 is None or (pid, eid) == (3, 10)):
                best12 = off
            elif fmt == 4 and (best4 is None or (pid, eid) == (3, 1)):
                best4 = off
            elif fmt == 14 and (pid, eid) == (0, 5):
                f14 = off
        if best12 is not None:
            n = _u32(table, best12 + 12)
            for g in range(n):
                o = best12 + 16 + 12 * g
                self.groups.append((_u32(table, o), _u32(table, o + 4), _u32(table, o + 8)))
        if best4 is not None:
            self.f4 = (table, best4, _u16(table, best4 + 6) // 2)
        if f14 is not None:
            self._parse_14(table, f14)

    def _parse_14(self, t: bytes, off: int) -> None:
        n = _u32(t, off + 6)
        for i in range(n):
            rec = off + 10 + 11 * i
            vs = _u24(t, rec)
            d_off = _u32(t, rec + 3)
            nd_off = _u32(t, rec + 7)
            if d_off:
                base = off + d_off
                cnt = _u32(t, base)
                ranges = []
                for r in range(cnt):
                    ro = base + 4 + 4 * r
                    start = _u24(t, ro)
                    ranges.append((start, start + _u8(t, ro + 3)))
                self.uvs_default[vs] = ranges
            if nd_off:
                base = off + nd_off
                cnt = _u32(t, base)
                for m in range(cnt):
                    mo = base + 4 + 5 * m
                    self.uvs_nondefault[(_u24(t, mo), vs)] = _u16(t, mo + 3)

    def lookup(self, cp: int) -> int:
        for start, end, gid0 in self.groups:
            if start <= cp <= end:
                return gid0 + (cp - start)
        if self.f4 is not None and cp <= 0xFFFF:
            t, off, seg = self.f4
            end_arr = off + 14
            start_arr = end_arr + seg * 2 + 2
            delta_arr = start_arr + seg * 2
            range_arr = delta_arr + seg * 2
            for i in range(seg):
                end = _u16(t, end_arr + 2 * i)
                if cp > end:
                    continue
                start = _u16(t, start_arr + 2 * i)
                if cp < start:
                    return 0
                delta = _s16(t, delta_arr + 2 * i)
                ro = _u16(t, range_arr + 2 * i)
                if ro == 0:
                    return (cp + delta) & 0xFFFF
                addr = range_arr + 2 * i + ro + 2 * (cp - start)
                gid = _u16(t, addr)
                return (gid + delta) & 0xFFFF if gid else 0
        return 0

    def variation(self, base: int, vs: int) -> Optional[int]:
        """Glyph for (base, variation selector): explicit non-default mapping, or the
        base's own glyph when a default-UVS range covers it. None when unknown."""
        gid = self.uvs_nondefault.get((base, vs))
        if gid is not None:
            return gid
        for start, end in self.uvs_default.get(vs, ()):
            if start <= base <= end:
                return self.lookup(base)
        return None


def parse_coverage(t: bytes, off: int) -> Dict[int, int]:
    """glyph -> coverage index (formats 1 and 2)."""
    fmt = _u16(t, off)
    cov: Dict[int, int] = {}
    if fmt == 1:
        n = _u16(t, off + 2)
        for i in range(n):
            cov[_u16(t, off + 4 + 2 * i)] = i
    elif fmt == 2:
        n = _u16(t, off + 2)
        for r in range(n):
            ro = off + 4 + 6 * r
            start, end, ci = _u16(t, ro), _u16(t, ro + 2), _u16(t, ro + 4)
            for g in range(start, end + 1):
                cov[g] = ci + (g - start)
    else:
        raise ValueError("coverage format %d" % fmt)
    return cov


@dataclass
class GsubLookups:
    """The subset of GSUB this tool applies, in lookup order:
    ligatures: per lookup, {first glyph: [(components tuple, ligature glyph), ...]}
    singles:   per lookup, {glyph: substitute}
    Each element of `order` is ('lig', dict) or ('single', dict)."""
    order: List[Tuple[str, dict]] = field(default_factory=list)


def parse_gsub(table: bytes) -> GsubLookups:
    """Collect every lookup referenced by any feature (types 1 and 4, through type 7
    extensions); other lookup types are ignored - a sequence that needs them is
    reported as unrenderable rather than guessed."""
    out = GsubLookups()
    feature_list = _u16(table, 6)
    lookup_list = _u16(table, 8)
    wanted: List[int] = []
    fcount = _u16(table, feature_list)
    for f in range(fcount):
        foff = feature_list + _u16(table, feature_list + 2 + 6 * f + 4)
        lcount = _u16(table, foff + 2)
        for i in range(lcount):
            li = _u16(table, foff + 4 + 2 * i)
            if li not in wanted:
                wanted.append(li)
    wanted.sort()
    lcount = _u16(table, lookup_list)
    for li in wanted:
        if li >= lcount:
            continue
        loff = lookup_list + _u16(table, lookup_list + 2 + 2 * li)
        ltype = _u16(table, loff)
        scount = _u16(table, loff + 4)
        ligs: Dict[int, List[Tuple[Tuple[int, ...], int]]] = {}
        singles: Dict[int, int] = {}
        for s in range(scount):
            soff = loff + _u16(table, loff + 6 + 2 * s)
            stype = ltype
            if stype == 7:
                stype = _u16(table, soff + 2)
                soff = soff + _u32(table, soff + 4)
            if stype == 4:
                _parse_ligature_subtable(table, soff, ligs)
            elif stype == 1:
                _parse_single_subtable(table, soff, singles)
        if ligs:
            out.order.append(("lig", ligs))
        if singles:
            out.order.append(("single", singles))
    return out


def _parse_ligature_subtable(t: bytes, off: int, ligs: Dict[int, List[Tuple[Tuple[int, ...], int]]]) -> None:
    if _u16(t, off) != 1:
        return
    cov = parse_coverage(t, off + _u16(t, off + 2))
    set_count = _u16(t, off + 4)
    by_index = {ci: g for g, ci in cov.items()}
    for si in range(set_count):
        first = by_index.get(si)
        if first is None:
            continue
        set_off = off + _u16(t, off + 6 + 2 * si)
        lig_count = _u16(t, set_off)
        for li in range(lig_count):
            lo = set_off + _u16(t, set_off + 2 + 2 * li)
            lig_glyph = _u16(t, lo)
            comp_count = _u16(t, lo + 2)
            comps = tuple(_u16(t, lo + 4 + 2 * c) for c in range(max(comp_count - 1, 0)))
            ligs.setdefault(first, []).append((comps, lig_glyph))
    # longest ligature first, so a greedy match prefers the fuller sequence
    for first in ligs:
        ligs[first].sort(key=lambda e: -len(e[0]))


def _parse_single_subtable(t: bytes, off: int, singles: Dict[int, int]) -> None:
    fmt = _u16(t, off)
    cov = parse_coverage(t, off + _u16(t, off + 2))
    if fmt == 1:
        delta = _s16(t, off + 4)
        for g in cov:
            singles[g] = (g + delta) & 0xFFFF
    elif fmt == 2:
        n = _u16(t, off + 4)
        for g, ci in cov.items():
            if ci < n:
                singles[g] = _u16(t, off + 6 + 2 * ci)


def apply_gsub(glyphs: List[int], gsub: GsubLookups) -> List[int]:
    """Apply the collected lookups in order, each left-to-right, greedy per position."""
    seq = list(glyphs)
    for kind, table in gsub.order:
        if kind == "single":
            seq = [table.get(g, g) for g in seq]
            continue
        i = 0
        out: List[int] = []
        while i < len(seq):
            cands = table.get(seq[i])
            matched = False
            if cands:
                for comps, lig in cands:
                    n = len(comps)
                    if tuple(seq[i + 1:i + 1 + n]) == comps:
                        out.append(lig)
                        i += 1 + n
                        matched = True
                        break
            if not matched:
                out.append(seq[i])
                i += 1
        seq = out
    return seq


@dataclass
class BitmapGlyph:
    png: bytes
    width: int
    height: int
    bearing_x: int
    bearing_y: int
    advance: int


class CbdtStrike:
    """The largest-ppem CBLC/CBDT strike: line metrics + glyph -> PNG."""

    def __init__(self, cblc: bytes, cbdt: bytes):
        self.cbdt = cbdt
        num = _u32(cblc, 4)
        best = None
        for i in range(num):
            rec = 8 + 48 * i
            ppem = _u8(cblc, rec + 45)
            if best is None or ppem > best[1]:
                best = (rec, ppem)
        if best is None:
            raise ValueError("CBLC has no strikes")
        rec, self.ppem = best
        self.ascender = _s8(cblc, rec + 16)
        self.descender = _s8(cblc, rec + 17)
        self.width_max = _u8(cblc, rec + 18)
        self.start_glyph = _u16(cblc, rec + 40)
        self.end_glyph = _u16(cblc, rec + 42)
        arr_off = _u32(cblc, rec)
        n_sub = _u32(cblc, rec + 8)
        self.subtables: List[Tuple[int, int, int]] = []   # (first, last, absolute subheader offset)
        for s in range(n_sub):
            so = arr_off + 8 * s
            first, last = _u16(cblc, so), _u16(cblc, so + 2)
            self.subtables.append((first, last, arr_off + _u32(cblc, so + 4)))
        self.cblc = cblc

    def glyph(self, gid: int) -> Optional[BitmapGlyph]:
        t = self.cblc
        for first, last, sub in self.subtables:
            if not (first <= gid <= last):
                continue
            index_format = _u16(t, sub)
            image_format = _u16(t, sub + 2)
            data_off = _u32(t, sub + 4)
            big = None
            if index_format == 1:
                o = sub + 8 + 4 * (gid - first)
                start, end = _u32(t, o), _u32(t, o + 4)
            elif index_format == 3:
                o = sub + 8 + 2 * (gid - first)
                start, end = _u16(t, o), _u16(t, o + 2)
            elif index_format == 2:
                size = _u32(t, sub + 8)
                big = self._big_metrics(t, sub + 12)
                start = size * (gid - first)
                end = start + size
            elif index_format == 4:
                n = _u32(t, sub + 8)
                start = end = None
                for k in range(n):
                    o = sub + 12 + 4 * k
                    if _u16(t, o) == gid:
                        start = _u16(t, o + 2)
                        end = _u16(t, o + 6)
                        break
                if start is None:
                    return None
            elif index_format == 5:
                size = _u32(t, sub + 8)
                big = self._big_metrics(t, sub + 12)
                n = _u32(t, sub + 20)
                idx = None
                for k in range(n):
                    if _u16(t, sub + 24 + 2 * k) == gid:
                        idx = k
                        break
                if idx is None:
                    return None
                start = size * idx
                end = start + size
            else:
                return None
            if end <= start:
                return None
            data = self.cbdt[data_off + start:data_off + end]
            if not data:
                return None
            if image_format == 17:
                h, w, bx, by, adv = _u8(data, 0), _u8(data, 1), _s8(data, 2), _s8(data, 3), _u8(data, 4)
                n = _u32(data, 5)
                return BitmapGlyph(bytes(data[9:9 + n]), w, h, bx, by, adv)
            if image_format == 18:
                h, w, bx, by, adv = _u8(data, 0), _u8(data, 1), _s8(data, 2), _s8(data, 3), _u8(data, 4)
                n = _u32(data, 8)
                return BitmapGlyph(bytes(data[12:12 + n]), w, h, bx, by, adv)
            if image_format == 19:
                n = _u32(data, 0)
                h, w, bx, by, adv = big if big else (0, 0, 0, 0, 0)
                return BitmapGlyph(bytes(data[4:4 + n]), w, h, bx, by, adv)
            return None
        return None

    @staticmethod
    def _big_metrics(t: bytes, o: int) -> Tuple[int, int, int, int, int]:
        return (_u8(t, o), _u8(t, o + 1), _s8(t, o + 2), _s8(t, o + 3), _u8(t, o + 4))


class OTFont:
    """Just enough of an OpenType reader: cmap + GSUB sequence resolution + CBDT strike."""

    def __init__(self, data: bytes):
        self.tables = read_table_directory(data)
        if "cmap" not in self.tables:
            raise ValueError("font has no cmap table")
        self.cmap = Cmap(self.tables["cmap"])
        self.gsub = parse_gsub(self.tables["GSUB"]) if "GSUB" in self.tables else GsubLookups()
        self.strike = (CbdtStrike(self.tables["CBLC"], self.tables["CBDT"])
                       if "CBLC" in self.tables and "CBDT" in self.tables else None)
        self.units_per_em = _u16(self.tables["head"], 18) if "head" in self.tables else 1000
        if "hhea" in self.tables:
            self.hhea_ascender = _s16(self.tables["hhea"], 4)
            self.hhea_descender = _s16(self.tables["hhea"], 6)
        else:
            self.hhea_ascender, self.hhea_descender = 0, 0

    @classmethod
    def open(cls, path: str) -> "OTFont":
        with open(path, "rb") as fh:
            return cls(fh.read())

    def resolve_sequence(self, cps: Sequence[int]) -> Tuple[Optional[int], str]:
        """(glyph id, reason). None when the font cannot represent the sequence as ONE
        glyph. VS16 is tried literally, then via cmap format 14, then dropped."""
        cps = list(cps)
        if len(cps) == 2 and cps[1] == VS16:
            g = self.cmap.variation(cps[0], VS16)
            if g:
                return g, "cmap14"
        glyphs: List[int] = []
        for cp in cps:
            g = self.cmap.lookup(cp)
            if g == 0:
                if cp == VS16:
                    continue                    # not in cmap: shaping engines drop it too
                return None, "U+%04X not in cmap" % cp
            glyphs.append(g)
        if not glyphs:
            return None, "empty after dropping VS16"
        shaped = apply_gsub(glyphs, self.gsub)
        if len(shaped) == 1:
            return shaped[0], "gsub" if len(glyphs) > 1 else "cmap"
        # a leftover VS16 glyph (some fonts map it to an empty glyph) is harmless
        vs_glyph = self.cmap.lookup(VS16)
        trimmed = [g for g in shaped if g != vs_glyph] if vs_glyph else shaped
        if len(trimmed) == 1:
            return trimmed[0], "gsub"
        if len(cps) > 1 and VS16 in cps:
            return self.resolve_sequence([cp for cp in cps if cp != VS16])
        return None, "GSUB leaves %d glyphs" % len(shaped)


# ---------------------------------------------------------------------------
# Renderers - both return an RGBA canvas: top = ascender line, bottom = descender line
# ---------------------------------------------------------------------------

class CbdtRenderer:
    name = "cbdt"

    def __init__(self, font: OTFont):
        if font.strike is None:
            raise ValueError("font has no CBDT strike")
        self.font = font
        st = font.strike
        self.ascent = st.ascender
        self.descent = -st.descender
        if self.ascent + self.descent <= 0:                 # broken line metrics: derive from hhea
            scale = st.ppem / float(font.units_per_em or 1000)
            self.ascent = int(round(font.hhea_ascender * scale))
            self.descent = int(round(-font.hhea_descender * scale))
        self.box_h = self.ascent + self.descent
        self.last_reason = ""

    def _glyph(self, cps: Sequence[int]) -> Optional[BitmapGlyph]:
        gid, why = self.font.resolve_sequence(cps)
        if gid is None:
            self.last_reason = why
            return None
        bg = self.font.strike.glyph(gid)
        if bg is None or not bg.png:
            self.last_reason = "no bitmap for glyph %d" % gid
            return None
        return bg

    def measure(self, cps: Sequence[int]) -> Optional[Tuple[int, int]]:
        bg = self._glyph(cps)
        if bg is None:
            return None
        return (max(bg.width, 1), self.box_h)

    def render(self, cps: Sequence[int]):
        from PIL import Image
        bg = self._glyph(cps)
        if bg is None:
            return None
        img = Image.open(io.BytesIO(bg.png)).convert("RGBA")
        canvas = Image.new("RGBA", (max(img.width, 1), self.box_h), (0, 0, 0, 0))
        top = self.ascent - bg.bearing_y
        canvas.paste(img, (0, top), img)
        return canvas


class PillowRenderer:
    """The design's mechanism. Skips what the layout engine cannot shape into one glyph."""
    name = "pillow"

    def __init__(self, font_path: str, size: int = NOTO_STRIKE_PPEM, font=None):
        if font is None:
            from PIL import ImageFont
            try:
                from PIL import features
                engine = ImageFont.Layout.RAQM if features.check("raqm") else ImageFont.Layout.BASIC
            except Exception:
                engine = None
            font = (ImageFont.truetype(font_path, size, layout_engine=engine) if engine is not None
                    else ImageFont.truetype(font_path, size))
        self.font = font
        self.ascent, self.descent = font.getmetrics()
        self.box_h = self.ascent + self.descent
        self.ref_advance = float(font.getlength("\U0001F600"))
        try:
            self.notdef_bbox = font.getbbox("͸")     # unassigned: renders .notdef
        except Exception:
            self.notdef_bbox = None
        self.last_reason = ""

    def _check(self, text: str) -> Optional[Tuple[int, int, int, int]]:
        bbox = self.font.getbbox(text)
        if bbox is None or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            self.last_reason = "renders blank"
            return None
        length = float(self.font.getlength(text))
        if self.ref_advance > 0 and length > self.ref_advance * 1.5:
            self.last_reason = "layout engine leaves several glyphs (advance %.0f vs %.0f)" % (length, self.ref_advance)
            return None
        if self.notdef_bbox is not None and bbox == self.notdef_bbox and len(text) == 1:
            self.last_reason = "renders .notdef"
            return None
        return bbox

    def measure(self, cps: Sequence[int]) -> Optional[Tuple[int, int]]:
        text = "".join(chr(c) for c in cps)
        bbox = self._check(text)
        if bbox is None:
            return None
        return (max(bbox[2] - bbox[0], 1), self.box_h)

    def render(self, cps: Sequence[int]):
        from PIL import Image, ImageDraw
        text = "".join(chr(c) for c in cps)
        bbox = self._check(text)
        if bbox is None:
            return None
        w = max(bbox[2] - bbox[0], 1)
        canvas = Image.new("RGBA", (w, self.box_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.text((-bbox[0], 0), text, font=self.font, embedded_color=True)
        return canvas


def pick_renderer(font_path: str, which: str = "auto"):
    if which not in ("auto", "cbdt", "pillow"):
        raise ValueError("renderer must be auto, cbdt or pillow")
    if which in ("auto", "cbdt"):
        try:
            otf = OTFont.open(font_path)
        except Exception as ex:
            if which == "cbdt":
                raise
            otf = None
        if otf is not None and otf.strike is not None:
            return CbdtRenderer(otf)
        if which == "cbdt":
            raise ValueError("font has no CBDT bitmap strike - use --renderer pillow")
    return PillowRenderer(font_path)


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

@dataclass
class AtlasBuild:
    sheets: list                                   # PIL images
    placements: Dict[str, Tuple[int, int, int]]
    ascent: int
    skipped: List[Tuple[str, str]]
    cell: int
    sheet: int
    pad: int


def compose(keys: Sequence[str], renderer, cell: int = DEFAULT_CELL, sheet: int = DEFAULT_SHEET,
            pad: int = DEFAULT_PAD) -> AtlasBuild:
    """Render every key (skipping what the renderer cannot), lay the survivors out in
    input order, paste each glyph scaled by ONE common factor so a single ascent value
    puts all of them on the baseline."""
    from PIL import Image
    inner = cell - 2 * pad
    if inner < 8:
        raise ValueError("cell too small for the padding")
    measured: List[Tuple[str, Tuple[int, ...], Tuple[int, int]]] = []
    skipped: List[Tuple[str, str]] = []
    for k in keys:
        cps = key_to_cps(k)
        m = renderer.measure(cps)
        if m is None:
            skipped.append((k, getattr(renderer, "last_reason", "") or "unrenderable"))
            continue
        measured.append((k, cps, m))
    box_w = max([m[0] for _, _, m in measured] + [1])
    box_h = max(getattr(renderer, "box_h", 1), 1)
    scale = inner / float(max(box_w, box_h))
    y_off = pad + (inner - box_h * scale) / 2.0
    ascent = int(round(y_off + renderer.ascent * scale))
    plan = plan_layout([k for k, _, _ in measured], cell, sheet)
    n_sheets = (max(s for s, _, _ in plan.values()) + 1) if plan else 0
    sheets = [Image.new("RGBA", (sheet, sheet), (0, 0, 0, 0)) for _ in range(n_sheets)]
    for k, cps, _ in measured:
        img = renderer.render(cps)
        if img is None:
            # measure said yes, render said no: keep the plan honest by leaving the
            # cell empty and recording it (the runtime shows an empty sprite there)
            skipped.append((k, "render failed after measure: " + (getattr(renderer, "last_reason", "") or "")))
            continue
        w = max(int(round(img.width * scale)), 1)
        h = max(int(round(img.height * scale)), 1)
        small = img.resize((w, h), Image.LANCZOS)
        s, x, y = plan[k]
        dx = x + pad + (inner - w) // 2
        dy = y + int(round(y_off))
        sheets[s].paste(small, (dx, dy), small)
    return AtlasBuild(sheets, plan, ascent, skipped, cell, sheet, pad)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_index(build: AtlasBuild, sheet_files: Sequence[Tuple[str, bytes]]) -> dict:
    per_sheet = cells_per_sheet(build.cell, build.sheet)
    used = [0] * len(sheet_files)
    for s, _, _ in build.placements.values():
        used[s] += 1
    return {
        "version": ATLAS_VERSION,
        "cell": build.cell,
        "sheet": build.sheet,
        "pad": build.pad,
        "origin": "top-left",
        "ascent": build.ascent,
        "cells_per_sheet": per_sheet,
        "sheets": [
            {"file": name, "sha256": sha256_bytes(data), "bytes": len(data), "cells_used": used[i]}
            for i, (name, data) in enumerate(sheet_files)
        ],
        "sequences": {k: list(v) for k, v in build.placements.items()},
    }


def index_json(index: dict) -> str:
    # one entry per line, no key sorting: order = input order = deterministic
    return json.dumps(index, indent=1, ensure_ascii=True) + "\n"


def encode_sheets(build: AtlasBuild) -> List[Tuple[str, bytes]]:
    out: List[Tuple[str, bytes]] = []
    for i, img in enumerate(build.sheets):
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=False)
        out.append((SHEET_FILE.format(i), buf.getvalue()))
    return out


def write_zip(path: str, files: Sequence[Tuple[str, bytes]]) -> None:
    """Flat, deterministic (fixed timestamps, stored PNGs, deflated text); exactly the
    entry set the runtime accepts: index, sheets named by the index, licence."""
    import zipfile
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files:
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_STORED if name.endswith(".png") else zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, data)


def write_atlas(out_dir: str, build: AtlasBuild, licence_text: str, make_zip: bool = True) -> Tuple[dict, bytes, Optional[str]]:
    """Write sheets, index, licence (and the release zip). Returns (index, the exact
    index bytes written - hash THOSE for the pin -, zip path or None)."""
    os.makedirs(out_dir, exist_ok=True)
    sheet_files = encode_sheets(build)
    for name, data in sheet_files:
        with open(os.path.join(out_dir, name), "wb") as fh:
            fh.write(data)
    index = build_index(build, sheet_files)
    index_bytes = index_json(index).encode("utf-8")
    with open(os.path.join(out_dir, INDEX_FILE), "wb") as fh:
        fh.write(index_bytes)
    licence_bytes = licence_text.encode("utf-8")
    with open(os.path.join(out_dir, LICENCE_FILE), "wb") as fh:
        fh.write(licence_bytes)
    zip_path = None
    if make_zip:
        zip_path = os.path.join(out_dir, ZIP_FILE)
        write_zip(zip_path, [(INDEX_FILE, index_bytes)] + list(sheet_files) + [(LICENCE_FILE, licence_bytes)])
    return index, index_bytes, zip_path


def write_report(out_dir: str, report_lines: Sequence[str]) -> None:
    with open(os.path.join(out_dir, REPORT_FILE), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(report_lines) + "\n")


LICENCE_MARKER = "SIL OPEN FONT LICENSE"
# The OFL 1.1's own section headings and defined terms: a file that carries the
# title but not the terms (a notice, a truncated copy) is not the licence.
LICENCE_TERMS = ("PERMISSION & CONDITIONS", "RESERVED FONT NAME", "TERMINATION", "DISCLAIMER")
LICENCE_MIN_CHARS = 3000                 # the OFL 1.1 text is about 4,400 characters


def check_licence_text(text: str, source: str) -> str:
    """The file must BE the OFL (review E-M1, round 2): the title, every section
    heading of the 1.1 text, and its length. A repository's Apache LICENSE
    beside the font, a notice that merely names the OFL, or a truncated copy
    must not ship as the font's licence."""
    up = text.upper()
    missing = [m for m in (LICENCE_MARKER,) + LICENCE_TERMS if m not in up]
    if missing or len(text) < LICENCE_MIN_CHARS:
        why = ("missing %s" % ", ".join("'%s'" % m for m in missing)) if missing else (
            "only %d characters, the licence text is longer" % len(text))
        raise SystemExit("%s is not the complete SIL Open Font License text (%s): pass --licence "
                         "<path to Noto's OFL 1.1 LICENSE file>" % (source, why))
    return text


def is_licence_text(text: str) -> bool:
    try:
        check_licence_text(text, "candidate")
        return True
    except SystemExit:
        return False


def find_licence(font_path: str, explicit: Optional[str]) -> str:
    if explicit:
        with open(explicit, "r", encoding="utf-8", errors="replace") as fh:
            return check_licence_text(fh.read(), explicit)
    d = os.path.dirname(os.path.abspath(font_path))
    for name in sorted(os.listdir(d)):
        up = name.upper()
        if up.startswith("LICENSE") or up.startswith("LICENCE") or up.startswith("OFL"):
            with open(os.path.join(d, name), "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            if is_licence_text(text):
                return text
    raise SystemExit("no OFL licence text beside the font: pass --licence <path to Noto's OFL 1.1 "
                     "LICENSE file> (the atlas must ship with it)")


# ---------------------------------------------------------------------------
# Reference matcher (the runtime's algorithm; plugin/EmojiSprites.cs mirrors it)
# ---------------------------------------------------------------------------

class Matcher:
    """Longest-match substitution of known emoji sequences with TMP sprite tags.

    Rules (identical in C#, EmojiMatcher):
      * text without any char >= U+00A9 is returned as-is (the lowest emoji code point);
      * a rich-text tag '<...>' (letter, '/' or '#' after '<', a '>' within 128 chars, no
        newline or second '<' inside) is copied verbatim - sprite tags included. User
        text is paren-escaped upstream, so every '<' that reaches a label is markup;
      * at every other position the trie is followed over code points; the LONGEST
        terminal wins and becomes <sprite name="e_<KEY>"> (tint=1 appended only when
        asked: TMP already takes the label's ALPHA for an untinted sprite, and tinting
        would multiply the emoji by the text colour);
      * modifier transparency: a skin-tone modifier or VS16 the trie does not spell at
        the current node is skipped during the walk, and any that directly follow a
        match are consumed - so a toned emoji or toned ZWJ sequence the atlas lacks
        resolves to its neutral sprite instead of a sprite plus a stray swatch;
      * anything else - unknown code points, unqualified forms - is copied unchanged.
    """

    def __init__(self, keys: Iterable[str]):
        self.root: dict = {}
        self.count = 0
        for k in keys:
            cps = key_to_cps(k)
            if not cps:
                continue
            node = self.root
            for cp in cps:
                node = node.setdefault(cp, {})
            if "$" not in node:
                self.count += 1
            node["$"] = k.upper()

    @classmethod
    def from_index(cls, index: dict) -> "Matcher":
        return cls(index.get("sequences", {}).keys())

    @staticmethod
    def tag(key: str, tint: bool = False) -> str:
        return '<sprite name="%s%s"%s>' % (SPRITE_NAME_PREFIX, key, " tint=1" if tint else "")

    @staticmethod
    def _is_modifier(cp: int) -> bool:
        return cp == VS16 or is_skin_tone(cp)

    def substitute(self, text: str, tint: bool = False) -> str:
        if not text or not any(ord(c) >= 0xA9 for c in text):
            return text
        out: List[str] = []
        i, n = 0, len(text)
        while i < n:
            c = text[i]
            if c == "<":
                end = self._tag_end(text, i)
                if end > 0:
                    out.append(text[i:end])
                    i = end
                    continue
            match_end, key = self._match(text, i)
            if key is not None:
                out.append(self.tag(key, tint))
                i = match_end
                while i < n:
                    cp, ln = self._cp(text, i)
                    if self._is_modifier(cp):
                        i += ln
                    else:
                        break
                continue
            _, ln = self._cp(text, i)
            out.append(text[i:i + ln])
            i += ln
        return "".join(out)

    @staticmethod
    def _tag_end(text: str, i: int) -> int:
        n = len(text)
        if i + 1 >= n:
            return -1
        c1 = text[i + 1]
        if not (c1.isascii() and (c1.isalpha() or c1 in "/#")):
            return -1
        limit = min(n, i + 129)
        for j in range(i + 1, limit):
            ch = text[j]
            if ch == ">":
                return j + 1
            if ch == "<" or ch == "\n":
                return -1
        return -1

    @staticmethod
    def _cp(text: str, i: int) -> Tuple[int, int]:
        c = ord(text[i])
        if 0xD800 <= c <= 0xDBFF and i + 1 < len(text):
            d = ord(text[i + 1])
            if 0xDC00 <= d <= 0xDFFF:
                return (0x10000 + ((c - 0xD800) << 10) + (d - 0xDC00), 2)
        return (c, 1)

    def _match(self, text: str, i: int) -> Tuple[int, Optional[str]]:
        node = self.root
        j = i
        best_end, best_key = -1, None
        n = len(text)
        while j < n:
            cp, ln = self._cp(text, j)
            nxt = node.get(cp)
            if nxt is None:
                if j > i and self._is_modifier(cp):
                    j += ln          # transparent: the walk continues past it
                    continue
                break
            node = nxt
            j += ln
            if "$" in node:
                best_end, best_key = j, node["$"]
        return best_end, best_key


# Shared self-check vectors: (input, expected). plugin/EmojiSprites.cs carries the SAME
# lists between its EMOJI-SELFCHECK markers and backend/tests/test_emoji_atlas.py fails
# when the two drift - a change here is a change there. ASCII escapes only: a literal
# ZWJ or VS16 in source is invisible.
SELF_CHECK_KEYS = ["1F600", "1F468-200D-1F469-200D-1F467", "1F468", "1F469", "1F467",
                   "2764-FE0F", "0023-FE0F-20E3", "1F44D", "1F1FA-1F1F8", "1F469-200D-1F680",
                   "1F634"]
SELF_CHECK_VECTORS = [
    ("hi \U0001F600", 'hi <sprite name="e_1F600">'),
    ("\U0001F468\u200D\U0001F469\u200D\U0001F467", '<sprite name="e_1F468-200D-1F469-200D-1F467">'),
    ("\U0001F468\u200D\U0001F469\u200D\U0001F466",
     '<sprite name="e_1F468">\u200D<sprite name="e_1F469">\u200D\U0001F466'),
    ("\u2764", "\u2764"),
    ("\u2764\uFE0F", '<sprite name="e_2764-FE0F">'),
    ("#\uFE0F\u20E3", '<sprite name="e_0023-FE0F-20E3">'),
    ("#\u20E3", "#\u20E3"),
    ("# 1", "# 1"),
    ("\U0001F44D\U0001F3FD!", '<sprite name="e_1F44D">!'),
    ("\U0001F469\U0001F3FD\u200D\U0001F680", '<sprite name="e_1F469-200D-1F680">'),
    ("\U0001F600\uFE0F", '<sprite name="e_1F600">'),
    ('<sprite name="e_1F600"> \U0001F600', '<sprite name="e_1F600"> <sprite name="e_1F600">'),
    ("<color=#FF0000>\U0001F600</color>", '<color=#FF0000><sprite name="e_1F600"></color>'),
    ("a < b \U0001F600", 'a < b <sprite name="e_1F600">'),
    ("\U0001F1FA\U0001F1F8", '<sprite name="e_1F1FA-1F1F8">'),
    ("\U0001F1FA", "\U0001F1FA"),
    ("hello", "hello"),
    ("", ""),
    ("\U0001F600\U0001F600", '<sprite name="e_1F600"><sprite name="e_1F600">'),
    ("caf\u00E9 \u2603", "caf\u00E9 \u2603"),
    ("(\U0001F634)", '(<sprite name="e_1F634">)'),
]
SELF_CHECK_TINT = ("\U0001F600", '<sprite name="e_1F600" tint=1>')


def self_check() -> Optional[str]:
    m = Matcher(SELF_CHECK_KEYS)
    for text, expected in SELF_CHECK_VECTORS:
        got = m.substitute(text)
        if got != expected:
            return "matcher mismatch for %r: got %r, expected %r" % (text, got, expected)
    if m.substitute(SELF_CHECK_TINT[0], tint=True) != SELF_CHECK_TINT[1]:
        return "tint=1 form wrong"
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--font", required=True, help="path to NotoColorEmoji.ttf")
    ap.add_argument("--emoji-test", required=True, help="path to Unicode's emoji-test.txt")
    ap.add_argument("--out", required=True, help="output directory (the zip's flat contents)")
    ap.add_argument("--cell", type=int, default=DEFAULT_CELL)
    ap.add_argument("--sheet", type=int, default=DEFAULT_SHEET)
    ap.add_argument("--pad", type=int, default=DEFAULT_PAD, help="transparent gutter inside each cell")
    ap.add_argument("--renderer", default="auto", choices=("auto", "cbdt", "pillow"))
    ap.add_argument("--skin-tones", action="store_true", help="include skin-tone sequences (needs 3 sheets)")
    ap.add_argument("--status", action="append", default=None,
                    help="emoji-test status to include (repeatable; default fully-qualified)")
    ap.add_argument("--licence", default=None, help="licence text to ship (default: LICENSE*/OFL* beside the font)")
    ap.add_argument("--max-sheets", type=int, default=MAX_RUNTIME_SHEETS,
                    help="fail when the list needs more sheets than this (runtime budget)")
    ap.add_argument("--no-zip", action="store_true", help="do not write %s" % ZIP_FILE)
    args = ap.parse_args(argv)

    failure = self_check()
    if failure:
        print("SELF-CHECK FAILED: " + failure, file=sys.stderr)
        return 2
    with open(args.emoji_test, "r", encoding="utf-8") as fh:
        entries = parse_emoji_test(fh)
    keys = select_sequences(entries, include_skin_tones=args.skin_tones,
                            statuses=tuple(args.status) if args.status else (FULLY_QUALIFIED,))
    licence = find_licence(args.font, args.licence)
    renderer = pick_renderer(args.font, args.renderer)
    build = compose(keys, renderer, args.cell, args.sheet, args.pad)
    per_sheet = cells_per_sheet(args.cell, args.sheet)
    n_sheets = len(build.sheets)
    if n_sheets == 0:
        print("ERROR: nothing rendered - wrong font or list?", file=sys.stderr)
        return 1
    if n_sheets > args.max_sheets:
        # Review E-M3: refuse BEFORE anything is written -- an over-budget atlas
        # must not exist on disk to be published by mistake.
        print("ERROR: %d sheets exceed the runtime budget of %d - nothing written" % (n_sheets, args.max_sheets),
              file=sys.stderr)
        return 1
    index, index_bytes, zip_path = write_atlas(args.out, build, licence, make_zip=not args.no_zip)
    index_sha = sha256_bytes(index_bytes)
    lines = [
        "emoji atlas %s" % ATLAS_VERSION,
        "renderer: %s" % renderer.name,
        "font: %s" % os.path.basename(args.font),
        "cell %d px (pad %d), sheet %d px, %d cells per sheet, ascent %d px" % (
            args.cell, args.pad, args.sheet, per_sheet, build.ascent),
        "sequences requested: %d" % len(keys),
        "sequences rendered:  %d" % len(build.placements),
        "sequences skipped:   %d" % len(build.skipped),
        "sheets: %d (%d cells free on the last one)" % (
            n_sheets, n_sheets * per_sheet - len(build.placements)),
    ]
    for s in index["sheets"]:
        lines.append("  %s  %d bytes  sha256 %s  cells %d" % (s["file"], s["bytes"], s["sha256"], s["cells_used"]))
    lines.append("index: %s  %d bytes  sha256 %s" % (INDEX_FILE, len(index_bytes), index_sha))
    lines.append('PIN  plugin/EmojiSprites.cs  INDEX_SHA256 = "%s";' % index_sha)
    if zip_path:
        lines.append("zip: %s  %d bytes  (publish on release %s with --latest=false)" % (
            os.path.basename(zip_path), os.path.getsize(zip_path), ATLAS_VERSION))
    summary_len = len(lines)
    lines += ["", "skipped:"] + ["  %s  %s" % (k, why) for k, why in build.skipped]
    write_report(args.out, lines)
    print("\n".join(lines[:summary_len]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
