"""Bug 333 step 2 - the colour-emoji atlas build tool (tools/emoji_atlas.py), as source.

The tool has no suite of its own, so it is imported by path and RUN. What is pinned:

  * emoji-test.txt parsing and the default selection (fully-qualified rows, no skin
    tones, no components), with the negative controls that prove the filter bites;
  * index naming (hyphenated upper-case hex sequence, 4-digit minimum) and the
    bottom-left GlyphRect flip the runtime applies;
  * deterministic row-major placement, overflow to a second sheet, the per-sheet
    cells_used counters, byte-identical index/PNG output for the same input;
  * composition with a MOCK renderer (no font needed): skips are recorded with a
    reason, survivors keep input order, one shared ascent, paste geometry;
  * the CBDT renderer against a SYNTHETIC OpenType font built here (cmap 12 + 14,
    GSUB ligature-through-extension + single substitution, CBLC/CBDT format 1/17):
    sequence resolution, bitmap lifting, skip reasons, end-to-end `main`;
  * the reference matcher: the shared vectors, tag transparency, modifier
    transparency, and that plugin/EmojiSprites.cs carries the SAME vectors (read as
    text, decoded from C# escapes) - with a mutation control so the comparison can
    fail.

Pillow is needed only for the pixel-producing tests (Image.new / PNG encode); those
skip cleanly where it is absent. No network, no NotoColorEmoji.ttf.
"""

import hashlib
import importlib.util
import io
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "emoji_atlas.py"
CS = REPO / "plugin" / "EmojiSprites.cs"


def _load_tool():
    spec = importlib.util.spec_from_file_location("emoji_atlas", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["emoji_atlas"] = mod          # dataclasses resolve cls.__module__ through here
    spec.loader.exec_module(mod)
    return mod


ea = _load_tool()

# A stand-in for the OFL 1.1 text: its title, every section heading the tool
# requires, and enough length (review E-M1, round 2) -- never the real text,
# which is the font's to ship, not this test's.
OFL_TEXT = ("SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007" + '\\n' +
            "PREAMBLE" + '\\n' + "DEFINITIONS" + '\\n' + "PERMISSION & CONDITIONS" + '\\n' +
            "Reserved Font Name" + '\\n' + "TERMINATION" + '\\n' + "DISCLAIMER" + '\\n' +
            ("the terms of the licence, paragraph after paragraph. " * 70))

EMOJI_TEST_SNIPPET = (
    "# emoji-test.txt (synthetic excerpt)\n"
    "\n"
    "# group: Smileys & Emotion\n"
    "# subgroup: face-smiling\n"
    "1F600                                                  ; fully-qualified     # \U0001F600 E1.0 grinning face\n"
    "263A FE0F                                              ; fully-qualified     # \u263A\uFE0F E0.6 smiling face\n"
    "263A                                                   ; unqualified         # \u263A E0.6 smiling face\n"
    "# subgroup: hand-fingers-closed\n"
    "1F44D 1F3FD                                            ; fully-qualified     # \U0001F44D\U0001F3FD E1.0 thumbs up: medium skin tone\n"
    "1F3FB                                                  ; component           # \U0001F3FB E1.0 light skin tone\n"
    "# group: People & Body\n"
    "# subgroup: family\n"
    "1F468 200D 1F469 200D 1F467                            ; fully-qualified     # \U0001F468\u200D\U0001F469\u200D\U0001F467 E2.0 family: man, woman, girl\n"
    "0023 FE0F 20E3                                         ; fully-qualified     # #\uFE0F\u20E3 E0.6 keycap: #\n"
    "1F1FA 1F1F8                                            ; fully-qualified     # \U0001F1FA\U0001F1F8 E2.0 flag: United States\n"
    "1F600                                                  ; fully-qualified     # duplicate row must collapse\n"
    "garbage line without a semicolon\n"
)


# ---------------------------------------------------------------------------
# emoji-test.txt + naming
# ---------------------------------------------------------------------------

def test_parse_emoji_test_rows_statuses_and_groups():
    entries = ea.parse_emoji_test(io.StringIO(EMOJI_TEST_SNIPPET))
    assert len(entries) == 9                       # the garbage line is dropped
    first = entries[0]
    assert first.cps == (0x1F600,)
    assert first.status == "fully-qualified"
    assert first.name == "grinning face"
    assert (first.group, first.subgroup) == ("Smileys & Emotion", "face-smiling")
    fam = [e for e in entries if e.key == "1F468-200D-1F469-200D-1F467"][0]
    assert fam.subgroup == "family" and fam.group == "People & Body"
    assert [e.status for e in entries if e.cps == (0x263A,)] == ["unqualified"]
    assert [e.status for e in entries if e.cps == (0x1F3FB,)] == ["component"]


def test_seq_key_is_hyphenated_upper_hex_with_four_digit_floor():
    assert ea.seq_key((0x1F600,)) == "1F600"
    assert ea.seq_key((0x23, 0xFE0F, 0x20E3)) == "0023-FE0F-20E3"
    assert ea.seq_key((0x1F468, 0x200D, 0x1F469)) == "1F468-200D-1F469"
    assert ea.key_to_cps("0023-FE0F-20E3") == (0x23, 0xFE0F, 0x20E3)
    assert ea.key_to_cps(ea.seq_key((0x1F1FA, 0x1F1F8))) == (0x1F1FA, 0x1F1F8)


def test_select_sequences_default_and_negative_controls():
    entries = ea.parse_emoji_test(io.StringIO(EMOJI_TEST_SNIPPET))
    default = ea.select_sequences(entries)
    assert default == ["1F600", "263A-FE0F", "1F468-200D-1F469-200D-1F467", "0023-FE0F-20E3", "1F1FA-1F1F8"]
    # negative controls: the filter is what removes these, not the data
    assert "1F44D-1F3FD" not in default and "1F3FB" not in default and "263A" not in default
    with_tones = ea.select_sequences(entries, include_skin_tones=True)
    assert "1F44D-1F3FD" in with_tones and "1F3FB" not in with_tones
    with_unq = ea.select_sequences(entries, statuses=("fully-qualified", "unqualified"))
    assert "263A" in with_unq and with_unq.index("263A-FE0F") < with_unq.index("263A")
    assert default.count("1F600") == 1             # duplicate row collapsed


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def test_plan_layout_row_major_deterministic_and_overflow():
    assert ea.cells_per_sheet(48, 2048) == 42 * 42 == 1764
    keys = ["K%d" % i for i in range(1765)]
    plan = ea.plan_layout(keys, 48, 2048)
    assert plan["K0"] == (0, 0, 0)
    assert plan["K1"] == (0, 48, 0)
    assert plan["K41"] == (0, 41 * 48, 0)
    assert plan["K42"] == (0, 0, 48)
    assert plan["K1763"] == (0, 41 * 48, 41 * 48)
    assert plan["K1764"] == (1, 0, 0)               # the 1,765th cell overflows to sheet 1
    assert ea.plan_layout(keys[:1764], 48, 2048)["K1763"][0] == 0
    assert ea.plan_layout(keys, 48, 2048) == plan   # same input, same placement
    with pytest.raises(ValueError):
        ea.plan_layout(["A", "A"], 48, 2048)
    with pytest.raises(ValueError):
        ea.plan_layout(["A"], 64, 32)


def test_glyph_rect_flips_to_bottom_left_origin():
    assert ea.glyph_rect_bottom_left(0, 0, 48, 2048) == (0, 2000, 48, 48)
    assert ea.glyph_rect_bottom_left(96, 2000, 48, 2048) == (96, 0, 48, 48)


# ---------------------------------------------------------------------------
# Composition with a mock renderer (no font)
# ---------------------------------------------------------------------------

class MockRenderer:
    """box_h 20 = ascender 14 + descender 6; every glyph 10 px wide; one key unrenderable."""
    name = "mock"

    def __init__(self, fail_keys=(), colour=(255, 0, 0, 255)):
        self.ascent = 14
        self.box_h = 20
        self.fail = set(fail_keys)
        self.colour = colour
        self.last_reason = ""
        self.rendered = []

    def measure(self, cps):
        if ea.seq_key(cps) in self.fail:
            self.last_reason = "mock cannot render"
            return None
        return (10, self.box_h)

    def render(self, cps):
        from PIL import Image
        self.rendered.append(ea.seq_key(cps))
        return Image.new("RGBA", (10, self.box_h), self.colour)


def test_compose_mock_skips_orders_ascent_and_paste_geometry():
    pytest.importorskip("PIL")
    keys = ["1F600", "1F601", "1F602", "1F603", "1F604"]
    r = MockRenderer(fail_keys=["1F602"])
    b = ea.compose(keys, r, cell=48, sheet=96, pad=1)       # 2 x 2 cells per sheet
    assert b.skipped == [("1F602", "mock cannot render")]
    assert list(b.placements) == ["1F600", "1F601", "1F603", "1F604"]   # input order, survivor-packed
    assert b.placements["1F603"] == (0, 0, 48)
    assert b.placements["1F604"] == (0, 48, 48)
    assert len(b.sheets) == 1
    # scale = 46 / max(10, 20) = 2.3; y_off = 1 + (46 - 46) / 2 = 1; ascent = round(1 + 14 * 2.3) = 33
    assert b.ascent == 33
    sheet = b.sheets[0]
    # glyph 10x20 -> 23x46 pasted at dx = x + 1 + (46 - 23) // 2 = x + 12, dy = y + 1
    x, y = 48, 48
    assert sheet.getpixel((x + 12 + 5, y + 1 + 5)) == (255, 0, 0, 255)
    assert sheet.getpixel((x, y))[3] == 0                    # the padding gutter stays clear
    assert sheet.getpixel((x + 5, y + 5))[3] == 0            # left of the centred glyph


def test_compose_overflows_to_second_sheet_and_counts_cells():
    pytest.importorskip("PIL")
    keys = ["1F60%X" % i for i in range(5)]
    b = ea.compose(keys, MockRenderer(), cell=48, sheet=96, pad=1)
    assert len(b.sheets) == 2
    assert b.placements[keys[4]] == (1, 0, 0)
    index = ea.build_index(b, ea.encode_sheets(b))
    assert index["version"] == "emoji-atlas-v1"
    assert (index["cell"], index["sheet"], index["pad"], index["ascent"]) == (48, 96, 1, 33)
    assert [s["file"] for s in index["sheets"]] == ["emoji-sheet-0.png", "emoji-sheet-1.png"]
    assert [s["cells_used"] for s in index["sheets"]] == [4, 1]
    assert index["sequences"][keys[4]] == [1, 0, 0]
    for s in index["sheets"]:
        assert re.fullmatch(r"[0-9a-f]{64}", s["sha256"]) and s["bytes"] > 0


def test_same_input_gives_identical_index_and_sheet_bytes():
    pytest.importorskip("PIL")
    keys = ["1F600", "1F601", "1F602"]

    def run():
        b = ea.compose(keys, MockRenderer(), cell=48, sheet=96, pad=1)
        sheets = ea.encode_sheets(b)
        return ea.index_json(ea.build_index(b, sheets)), [d for _, d in sheets]

    j1, s1 = run()
    j2, s2 = run()
    assert j1 == j2 and s1 == s2
    parsed = json.loads(j1)
    assert list(parsed["sequences"]) == keys       # order preserved, not sorted
    m = ea.Matcher.from_index(parsed)
    assert m.count == 3
    assert m.substitute("\U0001F602") == '<sprite name="e_1F602">'
    # a different input must NOT give the same index (control for the equality above)
    b3 = ea.compose(keys[:2], MockRenderer(), cell=48, sheet=96, pad=1)
    assert ea.index_json(ea.build_index(b3, ea.encode_sheets(b3))) != j1


# ---------------------------------------------------------------------------
# Synthetic OpenType font for the CBDT renderer
# ---------------------------------------------------------------------------

GID_GRIN, GID_ZWJ, GID_WOMAN, GID_FAMILY, GID_HEART_TEXT, GID_HEART_EMOJI, GID_HEART_SUBST = 1, 2, 3, 4, 5, 6, 7
CP_GRIN, CP_WOMAN, CP_ROCKET_ABSENT, CP_HEART = 0x1F600, 0x1F469, 0x1F680, 0x2764
STRIKE_ASC, STRIKE_DESC, PPEM = 8, -2, 109


def _png(w, h, colour):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", (w, h), colour).save(buf, format="PNG")
    return buf.getvalue()


def _cmap_table():
    groups = [(CP_GRIN, CP_GRIN, GID_GRIN), (ea.ZWJ, ea.ZWJ, GID_ZWJ),
              (CP_WOMAN, CP_WOMAN, GID_WOMAN), (CP_HEART, CP_HEART, GID_HEART_TEXT)]
    f12 = struct.pack(">HHIII", 12, 0, 16 + 12 * len(groups), 0, len(groups))
    for s, e, g in groups:
        f12 += struct.pack(">III", s, e, g)
    # format 14: one VS record (FE0F): a default range covering CP_GRIN, a non-default
    # mapping (CP_HEART, FE0F) -> GID_HEART_EMOJI
    default_uvs = struct.pack(">I", 1) + struct.pack(">I", CP_GRIN)[1:] + bytes([0])
    non_default = struct.pack(">I", 1) + struct.pack(">I", CP_HEART)[1:] + struct.pack(">H", GID_HEART_EMOJI)
    rec_len = 10 + 11
    f14 = struct.pack(">HII", 14, rec_len + len(default_uvs) + len(non_default), 1)
    f14 += struct.pack(">I", ea.VS16)[1:] + struct.pack(">II", rec_len, rec_len + len(default_uvs))
    f14 += default_uvs + non_default
    header = struct.pack(">HH", 0, 2) + struct.pack(">HHI", 3, 10, 20) + struct.pack(">HHI", 0, 5, 20 + len(f12))
    return header + f12 + f14


def _gsub_table():
    # ligature GRIN ZWJ WOMAN -> FAMILY through a type-7 extension; single HEART_TEXT -> HEART_SUBST
    cov_lig = struct.pack(">HHH", 1, 1, GID_GRIN)
    ligature = struct.pack(">HHHH", GID_FAMILY, 3, GID_ZWJ, GID_WOMAN)
    lig_set = struct.pack(">HH", 1, 4) + ligature                       # ligature at +4 of the set
    lig_sub = struct.pack(">HHHH", 1, 8 + len(lig_set), 1, 8) + lig_set + cov_lig   # coverage after the set
    ext = struct.pack(">HHI", 1, 4, 8) + lig_sub
    lookup0 = struct.pack(">HHHH", 7, 0, 1, 8) + ext
    cov_single = struct.pack(">HHH", 1, 1, GID_HEART_TEXT)
    single_sub = struct.pack(">HHHH", 2, 8, 1, GID_HEART_SUBST) + cov_single
    lookup1 = struct.pack(">HHHH", 1, 0, 1, 8) + single_sub
    lookup_list = struct.pack(">HHH", 2, 6, 6 + len(lookup0)) + lookup0 + lookup1
    feature = struct.pack(">HHHH", 0, 2, 0, 1)
    feature_list = struct.pack(">H", 1) + b"liga" + struct.pack(">H", 8) + feature
    script_list = struct.pack(">H", 0)
    header = struct.pack(">HHHHH", 1, 0, 10, 12, 12 + len(feature_list))
    assert len(script_list) == 2
    return header + script_list + feature_list + lookup_list


def _cblc_cbdt(bitmaps):
    """bitmaps: gid -> (png, h, w, bearing_x, bearing_y, advance); index format 1, image format 17."""
    first, last = min(bitmaps), max(bitmaps)
    data = b""
    offsets = []
    for gid in range(first, last + 1):
        offsets.append(len(data))
        if gid in bitmaps:
            png, h, w, bx, by, adv = bitmaps[gid]
            data += struct.pack(">BBbbB", h, w, bx, by, adv) + struct.pack(">I", len(png)) + png
    offsets.append(len(data))
    cbdt = struct.pack(">HH", 3, 0) + data
    sub_header = struct.pack(">HHI", 1, 17, 4) + b"".join(struct.pack(">I", o) for o in offsets)
    array = struct.pack(">HHI", first, last, 8)
    hori = struct.pack(">bbB", STRIKE_ASC, STRIKE_DESC, 12) + bytes(9)
    vert = bytes(12)
    size_rec = struct.pack(">IIII", 56, len(array) + len(sub_header), 1, 0) + hori + vert
    size_rec += struct.pack(">HHBBBb", first, last, PPEM, PPEM, 32, 1)
    assert len(size_rec) == 48
    cblc = struct.pack(">HHI", 3, 0, 1) + size_rec + array + sub_header
    return cblc, cbdt


def _synthetic_font():
    pytest.importorskip("PIL")
    bitmaps = {
        GID_GRIN: (_png(6, 8, (255, 0, 0, 255)), 8, 6, 0, STRIKE_ASC, 6),
        GID_WOMAN: (_png(6, 8, (0, 255, 0, 255)), 8, 6, 0, STRIKE_ASC, 6),
        GID_FAMILY: (_png(10, 8, (0, 0, 255, 255)), 8, 10, 0, STRIKE_ASC, 10),
        GID_HEART_EMOJI: (_png(6, 8, (255, 255, 0, 255)), 8, 6, 0, STRIKE_ASC, 6),
        GID_HEART_SUBST: (_png(6, 8, (255, 0, 255, 255)), 8, 6, 0, STRIKE_ASC, 6),
    }
    cblc, cbdt = _cblc_cbdt(bitmaps)
    head = bytearray(54)
    struct.pack_into(">H", head, 18, 1000)
    hhea = bytearray(36)
    struct.pack_into(">hh", hhea, 4, 800, -200)
    tables = {"CBDT": cbdt, "CBLC": cblc, "GSUB": _gsub_table(), "cmap": _cmap_table(),
              "head": bytes(head), "hhea": bytes(hhea)}
    names = sorted(tables)
    off = 12 + 16 * len(names)
    directory = struct.pack(">IHHHH", 0x00010000, len(names), 0, 0, 0)
    body = b""
    for n in names:
        t = tables[n]
        directory += n.encode("latin1") + struct.pack(">III", 0, off + len(body), len(t))
        body += t + bytes((-len(t)) % 4)
    return directory + body


def test_cbdt_font_resolves_sequences_and_lifts_bitmaps():
    font = ea.OTFont(_synthetic_font())
    assert font.strike is not None and font.strike.ppem == PPEM
    assert font.cmap.lookup(CP_GRIN) == GID_GRIN and font.cmap.lookup(CP_ROCKET_ABSENT) == 0
    assert font.cmap.variation(CP_HEART, ea.VS16) == GID_HEART_EMOJI          # non-default UVS
    assert font.cmap.variation(CP_GRIN, ea.VS16) == GID_GRIN                  # default-UVS range
    assert font.cmap.variation(CP_WOMAN, ea.VS16) is None
    assert font.resolve_sequence([CP_GRIN]) == (GID_GRIN, "cmap")
    assert font.resolve_sequence([CP_GRIN, ea.ZWJ, CP_WOMAN]) == (GID_FAMILY, "gsub")
    assert font.resolve_sequence([CP_HEART, ea.VS16]) == (GID_HEART_EMOJI, "cmap14")
    assert font.resolve_sequence([CP_HEART]) == (GID_HEART_SUBST, "cmap")     # single substitution applied
    assert font.resolve_sequence([CP_WOMAN, ea.VS16]) == (GID_WOMAN, "cmap")  # VS16 absent from cmap: dropped
    gid, why = font.resolve_sequence([CP_WOMAN, ea.ZWJ, CP_GRIN])
    assert gid is None and why == "GSUB leaves 3 glyphs"
    gid, why = font.resolve_sequence([CP_ROCKET_ABSENT])
    assert gid is None and why == "U+1F680 not in cmap"
    bg = font.strike.glyph(GID_FAMILY)
    assert (bg.width, bg.height, bg.bearing_y, bg.advance) == (10, 8, STRIKE_ASC, 10)
    assert font.strike.glyph(GID_ZWJ) is None                                 # no bitmap for the joiner


def test_cbdt_renderer_canvas_places_glyph_on_the_shared_baseline():
    r = ea.CbdtRenderer(ea.OTFont(_synthetic_font()))
    assert (r.ascent, r.descent, r.box_h) == (STRIKE_ASC, -STRIKE_DESC, 10)
    img = r.render([CP_GRIN])
    assert img.size == (6, 10)
    assert img.getpixel((3, 3)) == (255, 0, 0, 255)
    assert img.getpixel((3, 9))[3] == 0                # the descender band below the bitmap
    assert r.measure([CP_GRIN, ea.ZWJ, CP_WOMAN]) == (10, 10)
    assert r.render([CP_ROCKET_ABSENT]) is None and r.last_reason == "U+1F680 not in cmap"


def test_pick_renderer_prefers_cbdt_for_a_bitmap_font(tmp_path):
    p = tmp_path / "synthetic.ttf"
    p.write_bytes(_synthetic_font())
    assert isinstance(ea.pick_renderer(str(p), "auto"), ea.CbdtRenderer)
    assert isinstance(ea.pick_renderer(str(p), "cbdt"), ea.CbdtRenderer)
    with pytest.raises(ValueError):
        ea.pick_renderer(str(p), "sideways")


def test_compose_with_cbdt_renderer_records_skips_with_reasons():
    r = ea.CbdtRenderer(ea.OTFont(_synthetic_font()))
    keys = ["1F600", "1F600-200D-1F469", "2764-FE0F", "2764", "1F469-200D-1F600", "1F680"]
    b = ea.compose(keys, r, cell=16, sheet=32, pad=1)
    assert list(b.placements) == ["1F600", "1F600-200D-1F469", "2764-FE0F", "2764"]
    assert b.skipped == [("1F469-200D-1F600", "GSUB leaves 3 glyphs"), ("1F680", "U+1F680 not in cmap")]
    assert len(b.sheets) == 1
    # scale = 14 / max(10, 10) = 1.4; y_off = 1; ascent = round(1 + 8 * 1.4) = 12
    assert b.ascent == 12
    x, y = b.placements["1F600-200D-1F469"][1:]
    assert (x, y) == (16, 0)
    assert b.sheets[0].getpixel((x + 1 + 7, y + 1 + 5)) == (0, 0, 255, 255)      # the 14-px-wide family glyph, centred
    assert b.sheets[0].getpixel((x + 1 + 7, y + 1 + 13))[3] == 0                  # its descender band


def test_main_end_to_end_writes_pinned_index_zip_and_report(tmp_path, capsys):
    font = tmp_path / "NotoColorEmoji.ttf"
    font.write_bytes(_synthetic_font())
    (tmp_path / "LICENSE").write_text(OFL_TEXT, encoding="utf-8")
    et = tmp_path / "emoji-test.txt"
    et.write_text(
        "1F600 ; fully-qualified # x\n"
        "1F600 200D 1F469 ; fully-qualified # x\n"
        "2764 FE0F ; fully-qualified # x\n"
        "1F680 ; fully-qualified # x\n", encoding="utf-8")
    out = tmp_path / "out"
    rc = ea.main(["--font", str(font), "--emoji-test", str(et), "--out", str(out), "--cell", "16", "--sheet", "32"])
    assert rc == 0
    printed = capsys.readouterr().out
    index_bytes = (out / "emoji-index.json").read_bytes()
    sha = hashlib.sha256(index_bytes).hexdigest()
    assert 'INDEX_SHA256 = "%s";' % sha in printed
    assert "sequences rendered:  3" in printed and "sequences skipped:   1" in printed
    index = json.loads(index_bytes)
    assert index["version"] == "emoji-atlas-v1" and list(index["sequences"]) == ["1F600", "1F600-200D-1F469", "2764-FE0F"]
    sheet_bytes = (out / "emoji-sheet-0.png").read_bytes()
    assert index["sheets"][0]["sha256"] == hashlib.sha256(sheet_bytes).hexdigest()
    assert index["sheets"][0]["bytes"] == len(sheet_bytes)
    with zipfile.ZipFile(out / "emoji-atlas-v1.zip") as zf:
        assert sorted(zf.namelist()) == ["LICENSE-NotoColorEmoji.txt", "emoji-index.json", "emoji-sheet-0.png"]
        assert zf.read("emoji-index.json") == index_bytes
        assert all(zi.date_time == (1980, 1, 1, 0, 0, 0) for zi in zf.infolist())
    report = (out / "emoji-atlas-report.txt").read_text(encoding="utf-8")
    assert "1F680  U+1F680 not in cmap" in report and "sha256 %s" % sha in report
    assert (out / "LICENSE-NotoColorEmoji.txt").read_text(encoding="utf-8") == OFL_TEXT
    # the sheet budget gate is real: the same list cannot fit one 16-px cell
    rc2 = ea.main(["--font", str(font), "--emoji-test", str(et), "--out", str(tmp_path / "out2"),
                   "--cell", "16", "--sheet", "16", "--max-sheets", "1"])
    assert rc2 == 1
    out2 = tmp_path / "out2"
    assert not out2.exists() or not any(out2.iterdir()), "an over-budget atlas must not be written at all"


def test_find_licence_beside_font_or_explicit_else_refuses(tmp_path):
    font = tmp_path / "f.ttf"
    font.write_bytes(b"x")
    with pytest.raises(SystemExit):
        ea.find_licence(str(font), None)
    (tmp_path / "LICENSE").write_text("Apache License, Version 2.0 - the repository licence beside the font", encoding="utf-8")
    with pytest.raises(SystemExit):
        ea.find_licence(str(font), None)          # a LICENSE file that is not the OFL is skipped (review E-M1)
    (tmp_path / "NOTICE.txt").write_text("SIL OPEN FONT LICENSE - see the font", encoding="utf-8")
    with pytest.raises(SystemExit):
        ea.find_licence(str(font), str(tmp_path / "NOTICE.txt"))   # the title alone is a notice, not the licence (round 2)
    (tmp_path / "OFL.txt").write_text(OFL_TEXT.lower(), encoding="utf-8")   # case does not matter, the terms do
    assert ea.find_licence(str(font), None) == OFL_TEXT.lower()
    (tmp_path / "OFL.txt").write_text(OFL_TEXT[:1200], encoding="utf-8")   # truncated: refused
    with pytest.raises(SystemExit):
        ea.find_licence(str(font), None)
    (tmp_path / "OFL.txt").write_text(OFL_TEXT, encoding="utf-8")
    other = tmp_path / "other.txt"
    other.write_text("explicit", encoding="utf-8")
    with pytest.raises(SystemExit, match="not the complete SIL Open Font License"):
        ea.find_licence(str(font), str(other))    # an explicit path must BE the OFL too
    other.write_text(OFL_TEXT + "explicit", encoding="utf-8")
    assert ea.find_licence(str(font), str(other)) == OFL_TEXT + "explicit"


# ---------------------------------------------------------------------------
# Reference matcher
# ---------------------------------------------------------------------------

def test_matcher_shared_vectors_pass_and_tint_form():
    assert ea.self_check() is None
    m = ea.Matcher(ea.SELF_CHECK_KEYS)
    assert m.count == len(ea.SELF_CHECK_KEYS)
    for text, expected in ea.SELF_CHECK_VECTORS:
        assert m.substitute(text) == expected, text
    assert m.substitute(ea.SELF_CHECK_TINT[0], tint=True) == ea.SELF_CHECK_TINT[1]


def test_matcher_self_check_can_fail(monkeypatch):
    monkeypatch.setattr(ea, "SELF_CHECK_VECTORS", [("\U0001F600", "wrong")])
    assert ea.self_check() is not None


def test_matcher_rules_modifier_transparency_and_tags():
    m = ea.Matcher(["1F469-200D-1F680", "1F469", "1F44D", "1F600", "2764-FE0F"])
    woman_rocket_toned = "\U0001F469\U0001F3FD\u200D\U0001F680"
    assert m.substitute(woman_rocket_toned) == '<sprite name="e_1F469-200D-1F680">'
    assert m.substitute("\U0001F44D\U0001F3FF\U0001F44D") == '<sprite name="e_1F44D"><sprite name="e_1F44D">'
    assert m.substitute("\U0001F3FD") == "\U0001F3FD"            # a lone modifier is left alone
    assert m.substitute("\u2764") == "\u2764"                    # unqualified form: untouched
    assert m.substitute("\u2764\uFE0F\uFE0F") == '<sprite name="e_2764-FE0F">'
    # tags are copied verbatim; only text between them is matched
    assert m.substitute('<sprite name="e_1F600" tint=1>\U0001F600') == '<sprite name="e_1F600" tint=1><sprite name="e_1F600">'
    assert m.substitute("<b>\U0001F600</b>") == '<b><sprite name="e_1F600"></b>'
    assert m.substitute("</color>x") == "</color>x"
    assert m.substitute("<\U0001F600") == '<<sprite name="e_1F600">'    # not a tag: no name after '<'
    assert m.substitute("a\nb") == "a\nb"
    # a longer key beats a shorter one only when the WHOLE longer sequence is present
    assert m.substitute("\U0001F469\u200D") == '<sprite name="e_1F469">\u200D'
    # unknown code points and plain text never change
    assert m.substitute("caf\u00E9 \u2603 \U0001F9FF") == "caf\u00E9 \u2603 \U0001F9FF"
    assert m.substitute("") == "" and m.substitute("ascii only") == "ascii only"


# ---------------------------------------------------------------------------
# The C# mirror
# ---------------------------------------------------------------------------

_CS_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'", "0": "\0"}


def _decode_cs_literal(body):
    out = []
    i = 0
    while i < len(body):
        c = body[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        e = body[i + 1]
        if e == "u":
            out.append(chr(int(body[i + 2:i + 6], 16)))
            i += 6
        elif e == "U":
            out.append(chr(int(body[i + 2:i + 10], 16)))
            i += 10
        else:
            out.append(_CS_ESCAPES[e])
            i += 2
    return "".join(out)


def _cs_block_literals(text, name):
    m = re.search(r"// EMOJI-SELFCHECK-%s-BEGIN(.*?)// EMOJI-SELFCHECK-%s-END" % (name, name), text, re.S)
    assert m, "marker block %s missing from EmojiSprites.cs" % name
    return [_decode_cs_literal(b) for b in re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))]


def _cs_lists(text):
    keys = _cs_block_literals(text, "KEYS")
    flat = _cs_block_literals(text, "VECTORS")
    assert len(flat) % 2 == 0
    vectors = [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
    tint = _cs_block_literals(text, "TINT")
    return keys, vectors, tuple(tint)


def test_cs_runtime_carries_the_same_self_check_vectors():
    text = CS.read_text(encoding="utf-8")
    keys, vectors, tint = _cs_lists(text)
    assert keys == list(ea.SELF_CHECK_KEYS)
    assert vectors == list(ea.SELF_CHECK_VECTORS)
    assert tint == ea.SELF_CHECK_TINT
    assert len(vectors) >= 15
    # mutation control: a drifted C# vector is detected (mutate INSIDE the block)
    blk = re.search(r"// EMOJI-SELFCHECK-VECTORS-BEGIN.*?// EMOJI-SELFCHECK-VECTORS-END", text, re.S)
    mutated_block = blk.group(0).replace('e_1F600\\"', 'e_1f600\\"', 1)
    assert mutated_block != blk.group(0)
    mutated = text[:blk.start()] + mutated_block + text[blk.end():]
    _, mvectors, _ = _cs_lists(mutated)
    assert mvectors != list(ea.SELF_CHECK_VECTORS)


def test_cs_runtime_constants_match_the_tool():
    text = CS.read_text(encoding="utf-8")
    assert 'ATLAS_VERSION = "%s"' % ea.ATLAS_VERSION in text
    assert "MAX_SHEETS = %d" % ea.MAX_RUNTIME_SHEETS in text
    assert 'SPRITE_NAME_PREFIX = "%s"' % ea.SPRITE_NAME_PREFIX in text
    assert '"%s"' % ea.INDEX_FILE in text and '"%s"' % ea.LICENCE_FILE in text
    pin = re.search(r'INDEX_SHA256 = "([0-9a-f]*)"', text)
    assert pin, "INDEX_SHA256 constant missing"
    assert pin.group(1) == "" or len(pin.group(1)) == 64
