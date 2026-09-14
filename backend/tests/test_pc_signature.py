"""Player Cards — the autograph's shop styling (Sept 14 batch, S5).

Three things are proven here. The tables in backend/api/pc_signature.py
are parsed out of plugin/NametagStyler.cs and pinned entry by entry (every
hex code, every float triple, every SKU, the layer orders), with a negative
control on the parser and on the pin. `signature_style` composes SKUs the
way the client's Wrap composes tags. And the renderer draws every style
family differently from the plain autograph, stays inside the autograph's
rect on every size band, and ignores the style on an unsigned print.
"""

from __future__ import annotations

import hashlib
import io
import re
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageChops

REPO = Path(__file__).resolve().parents[2]
API = REPO / "backend" / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

import pc_face  # noqa: E402
import pc_portrait  # noqa: E402
import pc_signature as sig  # noqa: E402

STYLER = REPO / "plugin" / "NametagStyler.cs"


# ── the client's file, parsed ──────────────────────────────────────────────

def _styler() -> str:
    return STYLER.read_text(encoding="utf-8")


def _tags(src: str) -> dict[str, tuple[str, str]]:
    body = src[src.index("_tagsBySku ="):src.index("_RAINBOW_COLORS")]
    found = re.findall(r'\{\s*"(nametag_[a-z_]+)",\s*\("([^"]*)",\s*"([^"]*)"\)\s*\}', body)
    assert len(found) >= 25 and len(found) == len({k for k, _o, _c in found})
    return {sku: (open_, close) for sku, open_, close in found}


def _rainbow(src: str) -> list[str]:
    body = src[src.index("_RAINBOW_COLORS = {"):]
    body = body[:body.index("};")]
    found = re.findall(r'"(#[0-9A-Fa-f]{6})"', body)
    assert found
    return found


def _gradients(src: str) -> dict[str, tuple[tuple[float, ...], tuple[float, ...]]]:
    body = src[src.index("_GRADIENT_PAIRS ="):src.index("public static Color GetGlowColor")]
    pat = (r'\{\s*"(nametag_gradient_[a-z]+)",\s*\(new Color\(([\d.]+)f,\s*([\d.]+)f,\s*([\d.]+)f\),'
           r'\s*new Color\(([\d.]+)f,\s*([\d.]+)f,\s*([\d.]+)f\)\)\s*\}')
    found = re.findall(pat, body)
    assert found
    return {m[0]: (tuple(float(v) for v in m[1:4]), tuple(float(v) for v in m[4:7])) for m in found}


def _glows(src: str) -> dict[str, tuple[float, ...]]:
    body = src[src.index("public static Color GetGlowColor"):src.index("public static string GetSubgroup")]
    found = re.findall(r'case "(nametag_[a-z_]+)":\s*return new Color\(([\d.]+)f,\s*([\d.]+)f,\s*([\d.]+)f,\s*1f\);', body)
    assert found
    return {m[0]: tuple(float(v) for v in m[1:4]) for m in found}


def _layers(src: str) -> list[list[str]]:
    body = src[src.index("string[][] layers = new[]"):]
    body = body[:body.index("};")]
    groups = re.findall(r"new\[\]\s*\{([^}]*)\}", body)
    layers = [re.findall(r'"(nametag_[a-z_]+)"', group) for group in groups]
    assert len(layers) >= 7 and all(layers)
    return layers


def _every_client_sku() -> set[str]:
    skus = set()
    for path in (REPO / "plugin").glob("*.cs"):
        skus.update(re.findall(r'"(nametag_[a-z_]+[a-z])"', path.read_text(encoding="utf-8", errors="replace")))
    assert len(skus) >= 40
    return skus


def _unity_hex(channels) -> str:
    return sig._hex(sig._unity(*channels))


# ── the pin against the client ─────────────────────────────────────────────

def test_every_colour_flag_case_and_size_tag_is_mirrored_from_the_client():
    tags = _tags(_styler())
    colours = {sku: t for sku, t in tags.items() if t[0].startswith("<color=#")}
    assert set(colours) == set(sig.COLOURS)
    for sku, (open_, _close) in colours.items():
        assert sig._hex(sig.COLOURS[sku]) == open_[len("<color="):-1].upper(), sku
    assert {sku for sku, t in tags.items() if t[0] in ("<b>", "<i>", "<u>", "<s>")} == set(sig.FLAGS)
    assert sig.FLAGS == {"nametag_bold": "bold", "nametag_italic": "italic",
                         "nametag_underline": "underline", "nametag_strike": "strike"}
    assert tags["nametag_bold"][0] == "<b>" and tags["nametag_italic"][0] == "<i>"
    assert tags["nametag_underline"][0] == "<u>" and tags["nametag_strike"][0] == "<s>"
    assert tags["nametag_font_caps"][0] == "<allcaps>" and sig.CASES["nametag_font_caps"] == "caps"
    assert tags["nametag_font_smallcaps"][0] == "<smallcaps>" and sig.CASES["nametag_font_smallcaps"] == "smallcaps"
    assert tags["nametag_font_spaced"][0].startswith("<cspace=") and sig.CASES["nametag_font_spaced"] == "spaced"
    assert {sku for sku, t in tags.items() if t[0].startswith("<cspace=") or t[0] in ("<allcaps>", "<smallcaps>")} == set(sig.CASES)
    sizes = {sku: int(t[0][len("<size="):-2]) for sku, t in tags.items() if t[0].startswith("<size=")}
    assert set(sizes) == set(sig.SIZES)
    # the bands rank as the client's percentages rank, and every band moves
    # the size (no band maps to the plain 1.0)
    assert sorted(sig.SIZES, key=sig.SIZES.get) == sorted(sizes, key=sizes.get)
    assert all(mult != 1.0 for mult in sig.SIZES.values())
    assert {sku for sku, t in tags.items() if t[0].startswith("<voffset=")} == set(sig.IGNORED)
    # nothing in the client's tag table is left undecided
    assert all(sig.decided(sku) for sku in tags)


def test_rainbow_gradients_and_glows_are_mirrored_from_the_client():
    src = _styler()
    assert [sig._hex(c) for c in sig.RAINBOW] == [c.upper() for c in _rainbow(src)]
    gradients = _gradients(src)
    assert set(gradients) == set(sig.GRADIENTS) and len(gradients) == 15
    for sku, (start, end) in gradients.items():
        assert (sig._hex(sig.GRADIENTS[sku][0]), sig._hex(sig.GRADIENTS[sku][1])) == (_unity_hex(start), _unity_hex(end)), sku
    glows = _glows(src)
    assert set(glows) == set(sig.GLOWS)
    for sku, channels in glows.items():
        assert sig._hex(sig.GLOWS[sku]) == _unity_hex(channels), sku
    # every neon is in the glow table (it doubles as its own halo); every
    # plain glow is in the dedicated glow slot and nowhere else
    assert sig.NEON <= set(sig.GLOWS) and sig.NEON == {s for s in sig.COLOURS if s.startswith("nametag_neon_")}
    assert set(sig.PLAIN_GLOWS) == {s for s in glows if s.startswith("nametag_glow_")} and len(sig.PLAIN_GLOWS) == 4
    assert "nametag_rainbow" in src and sig.RAINBOW_SKU == "nametag_rainbow"


def test_the_layer_orders_are_the_clients():
    layers = _layers(_styler())
    assert tuple(layers[0]) == sig.CASE_ORDER
    assert tuple(layers[1]) == sig.SIZE_ORDER
    assert tuple(layers[2]) == sig.COLOUR_ORDER
    assert [layer[0] for layer in layers[3:8]] == ["nametag_strike", "nametag_underline", "nametag_italic",
                                                    "nametag_bold", "nametag_float"]


def test_every_sku_literal_in_the_client_is_decided_and_the_pin_can_fail():
    skus = _every_client_sku()
    undecided = sorted(s for s in skus if not sig.decided(s))
    assert undecided == [], undecided
    assert any(s.startswith("nametag_glow_") for s in skus) and any(s.startswith("nametag_gradient_") for s in skus)
    # negative controls: an unknown family, a prefix, and a family removed from
    # the module all fail the pin
    assert not sig.decided("nametag_wings") and not sig.decided("nametag_color_") and not sig.decided("")
    assert sig.decided("nametag_typeface_impact") and "nametag_typeface_impact" not in sig.KNOWN
    assert not sig.decided("typeface_impact")


def test_the_parsers_themselves_can_fail():
    # The regexes above find nothing in a file without the tables: a rename
    # on the client side fails the pin instead of pinning an empty set.
    with pytest.raises((AssertionError, ValueError)):
        _tags("_tagsBySku = { }; _RAINBOW_COLORS")
    with pytest.raises((AssertionError, ValueError)):
        _glows("public static Color GetGlowColor { } public static string GetSubgroup")


# ── the composition ────────────────────────────────────────────────────────

def test_nothing_applies_for_an_unstyled_or_undrawable_name():
    assert sig.signature_style(None) is None and sig.signature_style([]) is None
    assert sig.signature_style(["", None]) is None
    assert sig.signature_style(["nametag_float"]) is None
    assert sig.signature_style(["nametag_typeface_impact", "nametag_typeface_papyrus"]) is None
    # a SKU the shop retired and the client no longer knows is ignored, not an error
    assert sig.signature_style(["nametag_font_script", "not_a_nametag"]) is None


def test_a_solid_colour_a_neon_and_a_glow_compose_as_the_client_does():
    gold = sig.signature_style(["nametag_color_gold"])
    assert gold == {"bold": False, "case": None, "fill": "solid", "glow": None, "italic": False,
                    "rgb": "#FFCC44", "rgb2": None, "size": 1.0, "strike": False, "underline": False}
    assert tuple(gold) == sig.STYLE_KEYS
    neon = sig.signature_style(["nametag_neon_cyan"])
    assert neon["rgb"] == "#1FF0FF" and neon["glow"] == sig._hex(sig.GLOWS["nametag_neon_cyan"]) and neon["fill"] == "solid"
    # a plain glow beats the neon's own halo (GetActiveGlowSku), and colours nothing else
    both = sig.signature_style(["nametag_neon_cyan", "nametag_glow_red"])
    assert both["rgb"] == "#1FF0FF" and both["glow"] == sig._hex(sig.GLOWS["nametag_glow_red"]) == "#FF4554"
    alone = sig.signature_style(["nametag_glow_blue"])
    assert alone["rgb"] is None and alone["glow"] == "#4587FF" and alone["fill"] == "solid"
    # the first colour in the client's layer order wins, whatever the list order
    assert sig.signature_style(["nametag_color_cyan", "nametag_color_red"])["rgb"] == "#FF5566"
    assert sig.signature_style(["nametag_color_red", "nametag_color_cyan"])["rgb"] == "#FF5566"
    assert sig.signature_style(["nametag_neon_pink", "nametag_color_indigo"])["rgb"] == "#7A6BFF"


def test_rainbow_and_gradients_replace_the_colour_and_keep_the_halo():
    rainbow = sig.signature_style(["nametag_color_gold", "nametag_rainbow"])
    assert rainbow["fill"] == "rainbow" and rainbow["rgb"] is None and rainbow["rgb2"] is None
    sunset = sig.signature_style(["nametag_gradient_sunset"])
    assert sunset["fill"] == "gradient"
    assert (sunset["rgb"], sunset["rgb2"]) == tuple(sig._hex(c) for c in sig.GRADIENTS["nametag_gradient_sunset"])
    # the rainbow wins over a gradient; gradients rank by name (recorded deviation)
    assert sig.signature_style(["nametag_gradient_sunset", "nametag_rainbow"])["fill"] == "rainbow"
    pair = sig.signature_style(["nametag_gradient_sunset", "nametag_gradient_aurora"])
    assert pair["rgb"] == sig._hex(sig.GRADIENTS["nametag_gradient_aurora"][0])
    # a neon under a gradient still glows
    glowing = sig.signature_style(["nametag_gradient_ocean", "nametag_neon_lime"])
    assert glowing["fill"] == "gradient" and glowing["glow"] == sig._hex(sig.GLOWS["nametag_neon_lime"])


def test_case_size_and_flags_follow_the_layer_orders_and_stack():
    assert sig.signature_style(["nametag_font_spaced", "nametag_font_caps"])["case"] == "caps"
    assert sig.signature_style(["nametag_font_smallcaps"])["case"] == "smallcaps"
    assert sig.signature_style(["nametag_size_huge", "nametag_size_smaller"])["size"] == sig.SIZES["nametag_size_smaller"]
    assert sig.signature_style(["nametag_size_xl"])["size"] == sig.SIZES["nametag_size_xl"]
    flags = sig.signature_style(["nametag_bold", "nametag_strike", "nametag_underline", "nametag_italic"])
    assert flags["bold"] and flags["strike"] and flags["underline"] and flags["italic"]
    assert flags["rgb"] is None and flags["fill"] == "solid" and flags["case"] is None
    # deterministic in the input order: the same dict, the same rev
    a = sig.signature_style(["nametag_bold", "nametag_neon_pink", "nametag_size_bigger", "nametag_font_caps"])
    b = sig.signature_style(["nametag_font_caps", "nametag_size_bigger", "nametag_neon_pink", "nametag_bold"])
    assert a == b and list(a) == list(b) == list(sig.STYLE_KEYS)
    assert pc_portrait.spec_records({"sign": str(a)}) == pc_portrait.spec_records({"sign": str(b)})


# ── the renderer ───────────────────────────────────────────────────────────

def _autograph_crop(png: bytes) -> Image.Image:
    with Image.open(io.BytesIO(png)) as image:
        return image.crop(tuple(pc_face.LAYOUT["rects"]["autograph"])).convert("RGB")


def _digest(image: Image.Image) -> str:
    return hashlib.sha1(image.tobytes()).hexdigest()


def _spec(**overrides):
    values = {
        "band": "epic", "name": "Sid", "title": "Advanced I", "title_rgb": (119, 163, 252),
        "subtitle": None, "rating": 1400, "pool_rank": 7, "board_rank": 9, "wins": 20, "losses": 11,
        "foil": False, "signed": True, "sign": None, "edition_label": "Edition 1", "minted_on": "2026-09-14",
        "print_short": "#a3f2c1", "top_card": False,
    }
    values.update(overrides)
    return values


STYLE_CASES = {
    "gold": ["nametag_color_gold"],
    "neon": ["nametag_neon_cyan"],
    "glow": ["nametag_glow_red"],
    "rainbow": ["nametag_rainbow"],
    "gradient": ["nametag_gradient_sunset"],
    "bold": ["nametag_bold"],
    "italic": ["nametag_italic"],
    "underline": ["nametag_underline"],
    "strike": ["nametag_strike"],
    "caps": ["nametag_font_caps"],
    "smallcaps": ["nametag_font_smallcaps"],
    "spaced": ["nametag_font_spaced"],
    "smaller": ["nametag_size_smaller"],
    "huge": ["nametag_size_huge"],
}


def test_every_style_family_draws_a_different_autograph_and_only_there():
    plain = pc_face.render_face(_spec(), {}, None, "card")
    plain_crop = _autograph_crop(plain)
    seen = {_digest(plain_crop): "plain"}
    for label, skus in STYLE_CASES.items():
        style = sig.signature_style(skus)
        assert style is not None, label
        styled = pc_face.render_face(_spec(sign=style), {}, None, "card")
        crop = _autograph_crop(styled)
        assert ImageChops.difference(crop, plain_crop).getbbox() is not None, label
        digest = _digest(crop)
        assert digest not in seen, (label, seen[digest])
        seen[digest] = label
        # the style changes nothing outside the autograph's rect
        with Image.open(io.BytesIO(plain)) as a, Image.open(io.BytesIO(styled)) as b:
            box = pc_face.LAYOUT["rects"]["autograph"]
            for region in ((0, 0, a.width, box[1]), (0, box[3], a.width, a.height)):
                assert ImageChops.difference(a.crop(region), b.crop(region)).convert("RGB").getbbox() is None, label


def test_an_unsigned_print_ignores_the_style_and_the_tile_carries_it_too():
    style = sig.signature_style(["nametag_rainbow", "nametag_bold"])
    assert pc_face.render_face(_spec(signed=False), {}, None, "card") == pc_face.render_face(
        _spec(signed=False, sign=style), {}, None, "card")
    plain_tile = pc_face.render_face(_spec(), {}, None, "tile")
    styled_tile = pc_face.render_face(_spec(sign=style), {}, None, "tile")
    assert plain_tile != styled_tile
    # deterministic bytes with a style, as without one
    assert styled_tile == pc_face.render_face(_spec(sign=style), {}, None, "tile")


def test_the_rev_moves_with_the_style_and_not_with_the_floating_name():
    fp, cat = "f" * 16, "0" * 16
    plain = pc_portrait.face_rev(fp, cat, _spec(), "none", None)
    styled = pc_portrait.face_rev(fp, cat, _spec(sign=sig.signature_style(["nametag_color_gold"])), "none", None)
    assert plain != styled
    same = pc_portrait.face_rev(fp, cat, _spec(sign=sig.signature_style(["nametag_color_gold", "nametag_float"])), "none", None)
    assert same == styled
    other = pc_portrait.face_rev(fp, cat, _spec(sign=sig.signature_style(["nametag_color_red"])), "none", None)
    assert other != styled


def test_the_autograph_line_ends_before_the_seal():
    rect, seal = pc_face.LAYOUT["rects"]["autograph"], pc_face.LAYOUT["rects"]["seal"]
    anchor_x = pc_face.LAYOUT["anchors"]["autograph"][0]
    max_width, max_height = pc_face._autograph_box(1.0)
    assert max_height == rect[3] - rect[1] == 108
    assert anchor_x + max_width / 2 <= seal[0] - pc_face._SIGN_SEAL_GAP
    assert anchor_x - max_width / 2 >= rect[0] + pc_face._SIGN_MARGIN
    # the seal overlaps the rect's right end, which is why the measure is not the rect's
    assert seal[0] < rect[2] and max_width < rect[2] - rect[0]
    # the tile scales the same box
    assert pc_face._autograph_box(0.5) == (max_width // 2, max_height // 2)


@pytest.mark.parametrize("band", [None] + sorted(sig.SIZES, key=sig.SIZES.get))
def test_the_size_bands_stay_inside_the_autograph_rect_and_never_below_the_floor(band):
    style = sig.signature_style([band]) if band else None
    mult = sig.SIZES[band] if band else 1.0
    max_width, max_height = pc_face._autograph_box(1.0)
    top = round(pc_face._SIGN_SIZE_MAX * max(1.0, mult))
    for name in ("Stan", "Pyjama Gypsy", "ttv/Pexiltd_long"):
        plain_px = pc_face._autograph_fit(name, 1.0, None)[1]
        fitted, px = pc_face._autograph_fit(name, 1.0, style)
        assert fitted == name, (band, name)               # never cut at these lengths
        if mult < 1.0:
            # the shrinking band always shows, and never goes under the floor
            assert px == max(pc_face._SIGN_SIZE_MIN, round(plain_px * mult)) and px < plain_px
        else:
            # a growing band grows only as far as the card allows
            assert plain_px <= px <= top, (band, name, px)
        assert pc_face._SIGN_SIZE_MIN <= px <= top
        assert pc_face._sign_width(fitted, px, style) <= max_width
        mask, _emoji, _width, _baseline = pc_face._sign_mask(fitted, px, style, 0)
        bbox = mask.getchannel("A").getbbox()
        assert bbox is not None and bbox[3] - bbox[1] <= max_height + 2, (band, name, px, bbox)   # +2: the antialias fringe
    # an absurd name is cut with an ellipsis at the floor, not shrunk further
    fitted, px = pc_face._autograph_fit("W" * 60, 1.0, style)
    assert fitted.endswith("...") and px == pc_face._SIGN_SIZE_MIN
    # a tall short name at the band's top would leave the rect: the height bound holds it
    if mult > 1.0:
        assert pc_face._sign_ink_height("Stan", top, style) > max_height or pc_face._autograph_fit("Stan", 1.0, style)[1] == top
