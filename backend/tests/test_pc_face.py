"""Player Cards face renderer contract and visual proof outputs."""

from __future__ import annotations

import hashlib
import io
import json
import random
import re
import struct
import sys
import zlib
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFont, PngImagePlugin


REPO = Path(__file__).resolve().parents[2]
API = REPO / "backend" / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

import pc_face  # noqa: E402

PC_ASSETS = API / "assets" / "pc"
if str(PC_ASSETS) not in sys.path:
    sys.path.insert(0, str(PC_ASSETS))
import ingest as pc_ingest  # noqa: E402


# Tracked fixtures, not the gitignored ai-collab scratch: this suite has to
# be runnable from a clone of the repository. Both files were scanned for
# PNG text chunks before being vendored.
PORTRAITS = Path(__file__).resolve().parent / "fixtures" / "pc"
BASE_PORTRAIT = PORTRAITS / "pc_portrait_base_matte.png"
COS_PORTRAIT = PORTRAITS / "pc_portrait_cos_matte.png"
OUT = REPO / "backend" / "tests" / "_out" / "pc"


RANK_COLOURS = {
    "Grand Master": (244, 135, 169),
    "Master": (85, 216, 70),
    "Advanced": (119, 163, 252),
    "Intermediate": (253, 199, 119),
    "Beginner": (187, 121, 238),
}


def _spec(**overrides):
    values = {
        "band": "legendary",
        "name": "Sid",
        "title": "Grand Master I",
        "title_rgb": RANK_COLOURS["Grand Master"],
        "rating": 1850,
        "pool_rank": 1,
        "board_rank": 1,
        "wins": 60,
        "losses": 12,
        "foil": False,
        "signed": False,
        "edition_label": "Edition 1",
        "minted_on": "2026-09-11",
        "print_short": "#a3f2c1",
        "top_card": True,
    }
    values.update(overrides)
    return values


UK_CHIPS = {
    "pc.band.legendary": "ЛЕГЕНДАРНА",
    "pc.foil": "ФОЛЬГОВАНА",
    "pc.band_short.legendary": "ЛЕГ",
    "pc.foil_short": "ФОЛ",
}
UK_ALL = {
    **UK_CHIPS,
    "pc.signed": "ПІДПИСАНО",
    "pc.top_card": "ТОП-КАРТА",
    "pc.stat.rank": "РАНГ",
    "pc.stat.rating": "РЕЙТИНГ ГРАВЦЯ",
    "pc.stat.pool": "ПУЛ",
    "pc.stat.board": "ТАБЛИЦЯ",
    "pc.stat.record": "ПЕРЕМОГИ/ПОРАЗКИ",
    "pc.edition": "Видання",
}


PROOFS = (
    ("01_nameless", _spec(band="common", name="", title="Beginner I",
                           title_rgb=RANK_COLOURS["Beginner"], rating=1390,
                           pool_rank=112, board_rank=112, wins=3, losses=6), {}, None),
    ("02_long_latin", _spec(band="rare",
                             name="Maximilian Featherstonehaugh-Cholmondeley",
                             title="Advanced II", title_rgb=RANK_COLOURS["Advanced"],
                             rating=1560, pool_rank=19, board_rank=19, wins=28, losses=21), {}, None),
    ("03_cjk", _spec(band="epic", name="競技ラウンズ最強プレイヤー",
                      title="Master III", title_rgb=RANK_COLOURS["Master"],
                      rating=1655, pool_rank=6, board_rank=6, wins=35, losses=17), {}, None),
    ("04_projected_pua", _spec(band="uncommon", name="Sid 🔥🎯 the Great",
                                title="Advanced I", title_rgb=RANK_COLOURS["Advanced"],
                                rating=1520, pool_rank=30, board_rank=30, wins=20, losses=24), {}, "cos"),
    ("05_foil", _spec(foil=True), {}, "cos"),
    ("06_signed", _spec(signed=True, print_short="#b71e09"), {}, "cos"),
    ("07_uk_chips", _spec(name="Сід", foil=True), UK_CHIPS, "cos"),
    ("08_no_upload", _spec(band="rare", name="Pexiltd", title="Advanced III",
                            title_rgb=RANK_COLOURS["Advanced"], rating=1588,
                            pool_rank=14, board_rank=14, wins=30, losses=22), {}, None),
    ("09_uk_signed", _spec(name="Сід", signed=True, print_short="#c41d77"),
     {**UK_CHIPS, "pc.signed": "ПІДПИСАНО"}, "cos"),
    ("10_fully_localized", _spec(name="Сід", title="Гранд Майстер I",
                                  edition_label="Видання 1", foil=True, signed=True,
                                  print_short="#e0a9b3"), UK_ALL, "cos"),
    ("11_signed_cjk", _spec(band="epic", name="競技ラウンズ", title="Master III",
                             title_rgb=RANK_COLOURS["Master"], rating=1655,
                             pool_rank=6, board_rank=6, wins=35, losses=17,
                             signed=True, print_short="#7c2e11"), {}, None),
    ("12_emoji_signed", _spec(band="rare", name="🔥🎯👾", title="Advanced II",
                               title_rgb=RANK_COLOURS["Advanced"], rating=1560,
                               pool_rank=19, board_rank=19, wins=28, losses=21,
                               signed=True, print_short="#5d0a42"), {}, None),
    ("13_max_entropy", _spec(band="epic", name="Static", title="Master I",
                              title_rgb=RANK_COLOURS["Master"], rating=1620,
                              pool_rank=9, board_rank=9, wins=31, losses=20,
                              foil=True, signed=True, print_short="#f4d2a9"), {}, "noise"),
)


def _png(image: Image.Image, **save_options) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", **save_options)
    return output.getvalue()


@pytest.fixture(scope="session")
def canonical_portraits():
    base, base_meta = pc_face.prepare_portrait(BASE_PORTRAIT.read_bytes())
    cosmetic, cos_meta = pc_face.prepare_portrait(COS_PORTRAIT.read_bytes())

    with Image.open(io.BytesIO(cosmetic)) as source:
        alpha = source.getchannel("A")
    rng = random.Random(20260911)
    rgb = Image.frombytes("RGB", alpha.size, rng.randbytes(alpha.width * alpha.height * 3))
    visible = alpha.point(lambda value: 255 if value > 0 else 0)
    rgb = Image.composite(rgb, Image.new("RGB", alpha.size, (0, 0, 0)), visible)
    rgb.putalpha(alpha)
    noise, noise_meta = pc_face.prepare_portrait(_png(rgb, compress_level=6, optimize=False))
    return {
        "base": (base, base_meta),
        "cos": (cosmetic, cos_meta),
        "noise": (noise, noise_meta),
    }


def _write_sheet(outputs: dict[tuple[str, str], bytes]) -> None:
    width, height = 2424, 2020
    sheet = Image.new("RGBA", (width, height), (24, 26, 33, 255))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(str(API / "assets" / "fonts" / "NotoSans-Bold.ttf"), 18)
    for index, (proof_id, _specification, _labels, _portrait) in enumerate(PROOFS):
        column, row = index % 4, index // 4
        x, y = 24 + column * 600, 60 + row * 490
        with Image.open(io.BytesIO(outputs[(proof_id, "tile")])) as tile:
            thumb = tile.resize((236, 330), Image.Resampling.LANCZOS)
            sheet.alpha_composite(thumb, (x, y + 90))
        with Image.open(io.BytesIO(outputs[(proof_id, "card")])) as card:
            thumb = card.resize((300, 420), Image.Resampling.LANCZOS)
            sheet.alpha_composite(thumb, (x + 260, y))
        draw.text((x, y + 440), proof_id.replace("_", " "), font=font,
                  fill=(179, 179, 191, 255), anchor="lm")
    fresh = Image.frombytes("RGBA", sheet.size, sheet.tobytes())
    (OUT / "sheet_proofs.png").write_bytes(_png(fresh, compress_level=6, optimize=False))


@pytest.fixture(scope="session")
def proof_outputs(canonical_portraits):
    OUT.mkdir(parents=True, exist_ok=True)
    outputs: dict[tuple[str, str], bytes] = {}
    for proof_id, specification, labels, portrait_name in PROOFS:
        portrait = canonical_portraits[portrait_name][0] if portrait_name else None
        for size in ("card", "tile"):
            rendered = pc_face.render_face(specification, labels, portrait, size)
            outputs[(proof_id, size)] = rendered
            (OUT / f"{proof_id}_{size}.png").write_bytes(rendered)
    _write_sheet(outputs)
    return outputs


def test_proof_manifest_has_thirteen_unique_cases():
    identifiers = [proof[0] for proof in PROOFS]
    assert len(identifiers) == len(set(identifiers)) == 13


@pytest.mark.parametrize(
    ("proof_id", "size"),
    [(proof[0], size) for proof in PROOFS for size in ("card", "tile")],
)
def test_thirteen_proofs_at_both_sizes(proof_outputs, proof_id, size):
    data = proof_outputs[(proof_id, size)]
    expected = (pc_face.CARD_W, pc_face.CARD_H) if size == "card" else (pc_face.TILE_W, pc_face.TILE_H)
    ceiling = 4 << 20 if size == "card" else 1 << 20
    with Image.open(io.BytesIO(data)) as image:
        assert image.mode == "RGBA"
        assert image.size == expected
        assert [image.getpixel(point)[3] for point in
                ((0, 0), (expected[0] - 1, 0), (0, expected[1] - 1),
                 (expected[0] - 1, expected[1] - 1))] == [0, 0, 0, 0]
    chunks = pc_face.png_chunks(data)
    assert chunks[0] == (b"IHDR", 13) and chunks[-1] == (b"IEND", 0)
    assert {kind for kind, _ in chunks} <= {b"IHDR", b"IDAT", b"IEND"}
    assert len(data) <= ceiling
    assert pc_face.canonical_png(data, expected) == data


def test_fixture_ihdr_and_prepare_acceptance(canonical_portraits):
    assert pc_face.png_ihdr(BASE_PORTRAIT.read_bytes()) == (1180, 1180, 8, 6, 0)
    assert pc_face.png_ihdr(COS_PORTRAIT.read_bytes()) == (1180, 1180, 8, 6, 0)
    assert canonical_portraits["base"][1]["coverage"] == pytest.approx(0.1052384372)
    assert canonical_portraits["cos"][1]["coverage"] == pytest.approx(0.1310155128)
    for data, metadata in canonical_portraits.values():
        assert metadata["sha256"] == hashlib.sha256(data).hexdigest()
        assert metadata["width"] == metadata["height"] == 1180
        assert len(data) <= 1 << 20
        assert pc_face.canonical_png(data, (1180, 1180)) == data
        with Image.open(io.BytesIO(data)) as image:
            alpha_zero = image.getchannel("A").point(lambda value: 255 if value == 0 else 0)
            for channel in image.convert("RGB").split():
                assert ImageChops.multiply(channel, alpha_zero).getbbox() is None


def test_prepare_portrait_rejections():
    opaque = Image.new("RGBA", (1180, 1180), (30, 40, 50, 255))
    empty = Image.new("RGBA", (1180, 1180), (30, 40, 50, 0))
    wrong = Image.new("RGBA", (1179, 1180), (0, 0, 0, 0))
    palette = Image.new("P", (1180, 1180), 0)
    sixteen = Image.new("I;16", (1180, 1180), 1000)
    jpeg = io.BytesIO()
    Image.new("RGB", (1180, 1180)).save(jpeg, format="JPEG")

    valid_header = bytearray(_png(opaque, compress_level=6, optimize=False))
    valid_header[28] = 1
    valid_header[29:33] = struct.pack(">I", zlib.crc32(valid_header[12:29]) & 0xFFFFFFFF)

    invalid = (
        jpeg.getvalue(),
        _png(wrong, compress_level=6, optimize=False),
        _png(sixteen, compress_level=6, optimize=False),
        _png(palette, compress_level=6, optimize=False),
        bytes(valid_header),
    )
    for data in invalid:
        with pytest.raises(ValueError, match="^portrait_invalid$"):
            pc_face.prepare_portrait(data)
    for data in (_png(empty, compress_level=6, optimize=False),
                 _png(opaque, compress_level=6, optimize=False)):
        with pytest.raises(ValueError, match="^portrait_coverage$"):
            pc_face.prepare_portrait(data)


def test_prepare_portrait_rejects_post_canonical_oversize(monkeypatch):
    original = pc_face.canonical_png

    def oversized(data, expect_size=None):
        original(data, expect_size)
        return b"x" * ((1 << 20) + 1)

    monkeypatch.setattr(pc_face, "canonical_png", oversized)
    # Coverage is made legal without constructing a megabyte of random pixels.
    image = Image.new("RGBA", (1180, 1180), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((0, 0, 1179, 235), fill=(1, 2, 3, 255))
    with pytest.raises(ValueError, match="^portrait_too_large$"):
        pc_face.prepare_portrait(_png(image, compress_level=6, optimize=False))


def test_prepare_portrait_rejects_transport_oversize():
    with pytest.raises(ValueError, match="^portrait_too_large$"):
        pc_face.prepare_portrait(b"x" * ((1 << 20) + 1))


def test_canonical_png_strips_ancillary_chunks():
    image = Image.new("RGBA", (8, 8), (1, 2, 3, 4))
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "discard me")
    source = _png(image, compress_level=9, optimize=True, pnginfo=info)
    assert b"tEXt" in source
    canonical = pc_face.canonical_png(source, (8, 8))
    assert b"tEXt" not in canonical
    assert pc_face.canonical_png(canonical) == canonical


def test_png_walk_rejects_crc_and_trailing_bytes():
    source = bytearray(_png(Image.new("RGBA", (2, 2))))
    source[-1] ^= 1
    with pytest.raises(ValueError):
        pc_face.png_chunks(bytes(source))
    valid = _png(Image.new("RGBA", (2, 2)))
    with pytest.raises(ValueError):
        pc_face.png_chunks(valid + b"tail")

    def chunk(kind, payload=b""):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    with pytest.raises(ValueError):
        pc_face.png_chunks(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND"))
    with pytest.raises(ValueError):
        pc_face.png_chunks(valid[:33] + chunk(b"ABCD") + valid[33:])
    with pytest.raises(ValueError):
        pc_face.png_chunks(valid[:33] + chunk(b"text") + valid[33:])


def test_ingest_rejects_wrong_depth_and_bad_registration():
    valid = bytearray(_png(Image.new("RGBA", (750, 1050), (0, 0, 0, 0))))
    valid[24] = 16
    valid[29:33] = struct.pack(">I", zlib.crc32(valid[12:29]) & 0xFFFFFFFF)
    with pytest.raises(ValueError, match="^asset_shape:Frame_common.png$"):
        pc_ingest.canonicalise_bytes(bytes(valid), "Frame_common.png")

    transparent = _png(Image.new("RGBA", (750, 1050), (0, 0, 0, 0)))
    with pytest.raises(ValueError, match="^asset_opacity:Back.png$"):
        pc_ingest.canonicalise_bytes(transparent, "Back.png")

    misplaced = Image.new("RGBA", (750, 1050), (0, 0, 0, 0))
    misplaced.putpixel((100, 100), (255, 255, 255, 255))
    with pytest.raises(ValueError, match="^asset_registration:Plates_common.png$"):
        pc_ingest.canonicalise_bytes(_png(misplaced), "Plates_common.png")


def test_name_fit_is_grapheme_safe_and_uses_ascii_dots():
    original = "競" * 64
    for size in ("card", "tile"):
        fitted = pc_face.fit_name(original, size)
        assert fitted.endswith("...") and "…" not in fitted
        prefix = fitted[:-3]
        assert pc_face.graphemes(prefix) == pc_face.graphemes(original)[:len(pc_face.graphemes(prefix))]
    # parity (r5 L11): the tile keeps exactly the graphemes the card keeps
    assert pc_face.fit_name(original, "tile") == pc_face.fit_name(original, "card")
    autograph, autograph_size = pc_face._autograph_fit("W" * 64, 1.0)
    assert autograph.endswith("...") and autograph_size == 40
    assert pc_face._measure_text(autograph, autograph_size, "script") <= 380


def test_nameless_uses_label_and_the_plate_ignores_the_name(canonical_portraits):
    specification = _spec(band="rare", name="", top_card=False)
    english = pc_face.render_face(specification, {}, None, "card")
    localized = pc_face.render_face(specification, {"pc.unnamed": "Без імені"}, None, "card")
    emoji = pc_face.render_face(_spec(band="rare", name="🔥🎯👾", top_card=False), {}, None, "card")
    named = pc_face.render_face(_spec(band="rare", name="Ace", top_card=False), {}, None, "card")
    with (
        Image.open(io.BytesIO(english)) as first,
        Image.open(io.BytesIO(localized)) as second,
        Image.open(io.BytesIO(emoji)) as third,
        Image.open(io.BytesIO(named)) as fourth,
    ):
        assert ImageChops.difference(first.crop((54, 38, 490, 132)),
                                     second.crop((54, 38, 490, 132))).convert("RGB").getbbox() is not None
        # No picture = the emblem plate (2026-09-12): no initial, so the portrait
        # area is byte-identical across a blank, an emoji and a plain name.
        for other in (third, fourth):
            assert ImageChops.difference(first.crop((120, 190, 630, 620)),
                                         other.crop((120, 190, 630, 620))).convert("RGB").getbbox() is None
    assert not hasattr(pc_face, "_initial")


def test_portrait_reduction_is_direct_for_each_pass(canonical_portraits):
    portrait = canonical_portraits["cos"][0]
    specification = _spec(band="common", top_card=False)
    tile = pc_face.render_face(specification, {}, portrait, "tile")
    with Image.open(io.BytesIO(portrait)) as foreground:
        background = Image.new("RGBA", foreground.size, (12, 15, 32, 255))
        expected = Image.alpha_composite(background, foreground).reduce(4)
    with Image.open(io.BytesIO(tile)) as rendered:
        # Stay clear of the reduced five-pixel frame stroke; the interior must
        # be the direct 1180 -> 295 reduction byte for byte.
        assert ImageChops.difference(rendered.crop((52, 87, 323, 315)),
                                     expected.crop((12, 12, 283, 240))).convert("RGB").getbbox() is None

    card = pc_face.render_face(specification, {}, portrait, "card")
    with Image.open(io.BytesIO(portrait)) as foreground:
        background = Image.new("RGBA", foreground.size, (12, 15, 32, 255))
        expected = Image.alpha_composite(background, foreground).reduce(2)
    with Image.open(io.BytesIO(card)) as rendered:
        assert ImageChops.difference(rendered.crop((104, 174, 646, 716)),
                                     expected.crop((24, 24, 566, 566))).convert("RGB").getbbox() is None


def test_tile_is_not_a_downscaled_card(proof_outputs):
    with (
        Image.open(io.BytesIO(proof_outputs[("05_foil", "card")])) as card,
        Image.open(io.BytesIO(proof_outputs[("05_foil", "tile")])) as tile,
    ):
        assert ImageChops.difference(card.reduce(2), tile).convert("RGB").getbbox() is not None


def test_signed_badge_localization_and_foil_semantics(canonical_portraits):
    portrait = canonical_portraits["cos"][0]
    base = _spec(band="legendary", top_card=False)
    unsigned = pc_face.render_face(base, {}, portrait, "card")
    signed = pc_face.render_face({**base, "signed": True}, {}, portrait, "card")
    badge = pc_face.render_face({**base, "top_card": True}, {}, portrait, "card")
    plain = pc_face.render_face({**base, "top_card": True}, {}, portrait, "card")
    foil = pc_face.render_face({**base, "top_card": True, "foil": True}, {}, portrait, "card")
    localized = pc_face.render_face({**base, "top_card": True}, UK_ALL, portrait, "card")
    with (
        Image.open(io.BytesIO(unsigned)) as a,
        Image.open(io.BytesIO(signed)) as b,
        Image.open(io.BytesIO(badge)) as c,
        Image.open(io.BytesIO(plain)) as d,
        Image.open(io.BytesIO(foil)) as e,
        Image.open(io.BytesIO(localized)) as f,
    ):
        assert ImageChops.difference(a.crop((190, 636, 530, 744)),
                                     b.crop((190, 636, 530, 744))).convert("RGB").getbbox() is not None
        assert ImageChops.difference(a.crop((58, 642, 178, 754)),
                                     c.crop((58, 642, 178, 754))).convert("RGB").getbbox() is not None
        assert d.getpixel((400, 880)) == e.getpixel((400, 880))
        assert d.getpixel((400, 400)) != e.getpixel((400, 400))
        assert ImageChops.difference(c.crop((58, 642, 178, 754)),
                                     f.crop((58, 642, 178, 754))).convert("RGB").getbbox() is not None


def test_tile_short_chips_footer_and_signed_signal(canonical_portraits):
    portrait = canonical_portraits["cos"][0]
    specification = _spec(foil=True, signed=False)
    first = pc_face.render_face(specification, {
        "pc.band.legendary": "FULL ONE",
        "pc.band_short.legendary": "A",
        "pc.foil": "LONG FOIL ONE",
        "pc.foil_short": "B",
    }, portrait, "tile")
    full_only_changed = pc_face.render_face({**specification, "edition_label": "Different",
                                              "minted_on": "1900-01-01", "print_short": "#000000"}, {
        "pc.band.legendary": "FULL TWO",
        "pc.band_short.legendary": "A",
        "pc.foil": "LONG FOIL TWO",
        "pc.foil_short": "B",
    }, portrait, "tile")
    short_changed = pc_face.render_face(specification, {
        "pc.band.legendary": "FULL ONE",
        "pc.band_short.legendary": "C",
        "pc.foil": "LONG FOIL ONE",
        "pc.foil_short": "D",
    }, portrait, "tile")
    signed = pc_face.render_face({**specification, "signed": True}, {}, portrait, "tile")
    assert first == full_only_changed
    assert first != short_changed
    with Image.open(io.BytesIO(first)) as a, Image.open(io.BytesIO(signed)) as b:
        assert ImageChops.difference(a.crop((270, 315, 335, 377)),
                                     b.crop((270, 315, 335, 377))).convert("RGB").getbbox() is not None

    card_full_one = pc_face.render_face(_spec(foil=True), {
        "pc.band.legendary": "FULL ONE", "pc.band_short.legendary": "A",
        "pc.foil": "FOIL ONE", "pc.foil_short": "B",
    }, portrait, "card")
    card_full_two = pc_face.render_face(_spec(foil=True), {
        "pc.band.legendary": "FULL TWO", "pc.band_short.legendary": "A",
        "pc.foil": "FOIL TWO", "pc.foil_short": "B",
    }, portrait, "card")
    card_short_changed = pc_face.render_face(_spec(foil=True), {
        "pc.band.legendary": "FULL ONE", "pc.band_short.legendary": "C",
        "pc.foil": "FOIL ONE", "pc.foil_short": "D",
    }, portrait, "card")
    assert card_full_one != card_full_two
    assert card_full_one == card_short_changed

    too_long = "W" * 64
    card_short_a = pc_face.render_face(_spec(), {
        "pc.band.legendary": too_long, "pc.band_short.legendary": "A",
    }, portrait, "card")
    card_short_b = pc_face.render_face(_spec(), {
        "pc.band.legendary": "M" * 64, "pc.band_short.legendary": "A",
    }, portrait, "card")
    card_short_c = pc_face.render_face(_spec(), {
        "pc.band.legendary": too_long, "pc.band_short.legendary": "B",
    }, portrait, "card")
    assert card_short_a == card_short_b
    assert card_short_a != card_short_c


def test_localized_seal_stats_and_autograph_run_selection(canonical_portraits):
    portrait = canonical_portraits["cos"][0]
    specification = _spec(name="Сід", signed=True, top_card=False)
    english = pc_face.render_face(specification, {}, portrait, "card")
    localized = pc_face.render_face(specification, UK_ALL, portrait, "card")
    with Image.open(io.BytesIO(english)) as a, Image.open(io.BytesIO(localized)) as b:
        assert ImageChops.difference(a.crop((540, 630, 660, 750)),
                                     b.crop((540, 630, 660, 750))).convert("RGB").getbbox() is not None
        assert ImageChops.difference(a.crop((54, 758, 696, 972)),
                                     b.crop((54, 758, 696, 972))).convert("RGB").getbbox() is not None
        for key in ("stat_rank_label", "stat_rating_label", "stat_pool_label",
                    "stat_board_label", "stat_record_label"):
            box = tuple(pc_face.LAYOUT["rects"][key])
            assert ImageChops.difference(a.crop(box), b.crop(box)).convert("RGB").getbbox() is not None
    assert pc_face._runs("競技ラウンズ", "script") == [("cjk", "競技ラウンズ", 0)]
    assert pc_face._runs("🔥🎯👾", "script") == [
        ("emoji", "🔥", 0), ("emoji", "🎯", 0), ("emoji", "👾", 0)
    ]




def test_a_right_to_left_name_is_composited_in_the_order_it_is_read():
    """The renderer hands the shaper one FACE at a time, and the space between
    two Arabic words is drawn from the Latin face -- so the shaper never sees
    the line and cannot order it.  Painting the fragments in the order they are
    stored puts the FIRST word of every multi-word right-to-left name on the
    left, where the last one belongs."""
    arabic = "\u0645\u062d\u0645\u062f \u0639\u0644\u064a"      # two Arabic words
    hebrew = "\u05e9\u05dc\u05d5\u05dd"                            # one Hebrew word

    runs = pc_face._runs(arabic, "black")
    assert [value for _r, value, _l in runs] == ["\u0645\u062d\u0645\u062f", " ",
                                                 "\u0639\u0644\u064a"]
    assert [level for _r, _v, level in runs] == [1, 1, 1], "a right-to-left line"
    assert [value for _r, value, _l in pc_face._visual(runs)] == [
        "\u0639\u0644\u064a", " ", "\u0645\u062d\u0645\u062f"], "last word leftmost"

    # A mixed line takes its direction from the first strong character, so a
    # Hebrew name with a Latin tag reads Hebrew-on-the-right...
    runs = pc_face._runs(hebrew + " Sid", "black")
    assert [(value, level) for _r, value, level in runs] == [(hebrew, 1), (" ", 1), ("Sid", 2)]
    assert [value for _r, value, _l in pc_face._visual(runs)] == ["Sid", " ", hebrew]
    # ...and the same two words the other way round keep the Latin on the left
    runs = pc_face._runs("Sid " + hebrew, "black")
    assert [(value, level) for _r, value, level in runs] == [("Sid ", 0), (hebrew, 1)]
    assert [value for _r, value, _l in pc_face._visual(runs)] == ["Sid ", hebrew]

    # A number inside a right-to-left line stays a number: an even level inside
    # an odd one is reversed twice and lands back where it started.
    runs = pc_face._runs(hebrew + " 42", "black")
    assert [(value, level) for _r, value, level in runs] == [(hebrew, 1), (" ", 1), ("42", 2)]
    assert [value for _r, value, _l in pc_face._visual(runs)] == ["42", " ", hebrew]

    # A line with nothing strong in it is left exactly alone.
    assert pc_face._visual(pc_face._runs("Sid", "black")) == [("black", "Sid", 0)]
    assert pc_face._runs("\u05e9", "black") == [("hebrew", "\u05e9", 1)], "one run, no reversal"


def test_the_shaper_is_complemented_at_a_neutral_run_never_repeated():
    """Reordering whole runs is UAX#9 L2 only while somebody reverses the
    characters inside each run and mirrors the brackets among them.  The shaper
    does that for a run with strong right-to-left text in it, and cannot for a
    run of pure neutrals -- which is what ` (` between two Hebrew words is,
    because the bracket and the space are drawn from the Latin face."""
    hebrew = "\u05e9\u05dc\u05d5\u05dd"
    runs = pc_face._runs(hebrew + " (" + hebrew + ")", "black")
    assert [value for _r, value, _l in runs] == [hebrew, ") ", hebrew, "("]
    assert [level for _r, _v, level in runs] == [1, 1, 1, 1]
    # left to right: ( shalom ) space shalom -- the bracket pair around the
    # second word, and the space outside it, which is how the line is read
    assert "".join(value for _r, value, _l in pc_face._visual(runs)) == \
        "(" + hebrew + ") " + hebrew

    # the same characters in a left-to-right line are not touched at all
    assert pc_face._runs("Sid (x)", "black") == [("black", "Sid (x)", 0)]

    # and a run the shaper WILL handle is handed over as it stands, because
    # doing it here too would undo it
    assert pc_face._rtl_by_hand("(" + hebrew, 1) == "(" + hebrew
    assert pc_face._rtl_by_hand(" (", 1) == ") "
    assert pc_face._rtl_by_hand(" (", 0) == " ("



def test_the_compositor_itself_lays_the_line_out_visually():
    """`_visual` knowing the order is worth nothing unless the compositor asks
    it.  An emoji is painted from a colour strike and the text is painted in
    the fill, so the side the colour lands on says which order was used --
    without a second copy of the compositor living in this test."""
    hebrew = "\u05e9\u05dc\u05d5\u05dd"
    line, _width = pc_face._render_text_line(hebrew + "\U0001f525", 48,
                                             (255, 255, 255, 255), "black")
    half = line.width // 2

    def colour(image, box):
        raw = image.crop(box).tobytes()          # RGBA, four bytes a pixel
        return sum(1 for n in range(0, len(raw), 4)
                   if raw[n + 3] > 40 and max(raw[n:n + 3]) - min(raw[n:n + 3]) > 30)

    # the emoji is the LAST thing in the string and the FIRST thing on the
    # canvas, because the line is read right to left
    assert colour(line, (0, 0, half, line.height)) > 0
    assert colour(line, (half, 0, line.width, line.height)) == 0, "emoji drawn after the name"

    # and the same two runs in a left-to-right line stay where they are stored
    line, _width = pc_face._render_text_line("Sid\U0001f525", 48,
                                             (255, 255, 255, 255), "black")
    half = line.width // 2
    assert colour(line, (half, 0, line.width, line.height)) > 0
    assert colour(line, (0, 0, half, line.height)) == 0


def test_autograph_content_is_the_unsubstituted_name():
    names = ("Sid", "競技ラウンズ", "🔥🎯👾")
    outputs = []
    for name in names:
        fitted, _font_size = pc_face._autograph_fit(name, 1.0)
        assert fitted == name
        outputs.append(pc_face.render_face(
            _spec(band="rare", name=name, signed=True, top_card=False), {}, None, "card"
        ))
    crops = []
    for data in outputs:
        with Image.open(io.BytesIO(data)) as image:
            crops.append(image.crop((190, 670, 530, 744)).copy())
    assert all(ImageChops.difference(crops[0], crop).convert("RGB").getbbox() is not None
               for crop in crops[1:])


def test_deterministic_bytes(canonical_portraits):
    portrait = canonical_portraits["base"][0]
    specification = _spec(band="epic", foil=True, signed=True)
    assert pc_face.render_face(specification, {}, portrait, "card") == pc_face.render_face(
        specification, {}, portrait, "card"
    )


def test_back_and_placeholder_assets_are_canonical():
    assets = Path(pc_face.ASSETS_DIR)
    back = (assets / "Back.png").read_bytes()
    # Compared as an IMAGE, not as bytes. A bytes assertion here also pins the
    # zlib output of one Pillow build: measured 2026-09-12, 11.3.0 (pinned in
    # requirements.txt, so what the container runs) and 12.3.0 (this machine)
    # encode these identical pixels nine bytes apart. That assertion is green
    # in exactly one of the two environments and reads as a corrupted asset in
    # the other, and regenerating the file only swaps which one that is.
    with Image.open(io.BytesIO(back)) as shipped:
        with Image.open(io.BytesIO(pc_face.render_back())) as fresh:
            assert shipped.size == fresh.size == (750, 1050)
            assert shipped.mode == fresh.mode == "RGBA"
            assert shipped.tobytes() == fresh.tobytes(), (
                "Back.png is not the image render_back() draws")
    # ...and it is already canonical: the three chunks and nothing else, and
    # re-canonicalising it describes the same image.
    assert {kind for kind, _ in pc_face.png_chunks(back)} <= {b"IHDR", b"IDAT", b"IEND"}
    assert pc_face.png_ihdr(back) == pc_face.png_ihdr(
        pc_face.canonical_png(back, (750, 1050)))
    assert len(back) <= 4 << 20
    expected = {
        *(f"Base_{band}.png" for band in pc_face.BANDS),
        *(f"Frame_{band}.png" for band in pc_face.BANDS),
        *(f"Plates_{band}.png" for band in pc_face.BANDS),
        "BadgeFrame.png", "SignedSeal.png", "FoilOverlay.png", "FoilMask.png",
        "RetryGlyph.png", "Back.png",
    }
    assert {path.name for path in assets.glob("*.png")} == expected
    for path in assets.glob("*.png"):
        chunks = pc_face.png_chunks(path.read_bytes())
        assert {kind for kind, _ in chunks} <= {b"IHDR", b"IDAT", b"IEND"}
        expected_size, expected_mode, cap = pc_ingest._asset_class(path)
        assert len(path.read_bytes()) <= cap
        with Image.open(path) as image:
            assert image.size == expected_size
            assert image.mode == expected_mode


def test_the_projection_and_the_run_splitter_agree_about_every_cluster():
    """Two readings of one manifest: `pc_portrait.cluster_drawable` decides
    which clusters may reach the renderer, and `pc_face._cluster_role` picks
    the font that draws one. A cluster the first admits and the second cannot
    place is a box on the card under a `face_rev` that says otherwise -- so
    they are asked about the same strings, at every base role.

    THE MUTATION THIS MUST FAIL ON: dropping a role from `candidate_roles`, or
    projecting against the flat union instead of the per-role ranges."""
    import sys
    sys.path.insert(0, str(Path(pc_face.__file__).parent))
    import pc_portrait

    samples = (
        "Sid", "a\u0651", "\u0645\u062d\u0645\u062f", "\u05d3\u05d5\u05d3",
        "\u0e2a\u0e21\u0e0a\u0e32\u0e22", "\u0905\u092e\u093f\u0924", "\u0986",
        "\u0b85", "\u10d0", "\u0561", "\u4e2d\u6587", "\u2605", "\u266a",
        "\U0001f409", "\U0001f469\u200d\U0001f4bb", "\ue001", "\U000f0000",
        "e\u0301", "\u0915\u094d\u0937", "\u05d0\u0591", "A\u200dB", "\u00e9",
        "\U0001f1fa\U0001f1f8", "#\ufe0f\u20e3", "\u4e2d\u0651",
    )
    disagreements = []
    for raw in samples:
        for cluster in pc_portrait.graphemes(raw):
            admitted = pc_portrait.cluster_drawable(cluster)
            placed = all(pc_face._cluster_role(cluster, base)[1] != "\u25af"
                         for base in pc_face.BASE_ROLES)
            if admitted != placed:
                disagreements.append((cluster.encode("unicode_escape"), admitted, placed))
    assert not disagreements, disagreements


def test_the_coverage_manifest_still_matches_the_fonts_it_was_generated_from():
    """The manifest is committed and the fonts are fetched, so the two can
    drift. A font swap that widens or narrows coverage must regenerate it --
    otherwise names lose glyphs the renderer now has, or keep glyphs it lost."""
    import importlib.util
    path = Path(pc_face.__file__).parent / "assets" / "pc" / "build_name_coverage.py"
    spec = importlib.util.spec_from_file_location("scr_build_name_coverage", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--check"]) == 0


def test_the_coverage_manifest_is_a_fingerprint_input():
    """It decides which code points reach the canvas, so changing it draws
    different pixels and must re-key every face."""
    src = Path(pc_face.__file__).read_text(encoding="utf-8")
    assert 'manifest/name_coverage.json' in src
    assert '_ASSETS_PATH / "name_coverage.json"' in src
    _, stamps = pc_face._fingerprint_inputs()
    assert any("name_coverage.json" in str(p) for p, _, _ in stamps)


def test_the_renderer_fingerprint_carries_the_grapheme_splitters_version():
    """The splitter is the third-party `regex` module (`\\X`), whose cluster
    boundaries move with its own releases and not with Python's."""
    import regex as _regex
    prov = pc_face.runtime_provenance()
    assert prov["regex"] == _regex.__version__
    assert "\\X" in Path(pc_face.__file__).read_text(encoding="utf-8")


def test_the_preview_footer_has_no_dangling_separator():
    """The separator belongs BETWEEN two parts. The /card preview carries no
    minted date, and drawing it anyway ended the footer in a bare mark."""
    src = Path(pc_face.__file__).read_text(encoding="utf-8")
    assert '"  ·  ".join(part for part in' in src and "if part)" in src
    # and the shape it produces, for both the print footer and the preview
    joined = lambda a, b: "  ·  ".join(p for p in (str(a or "").strip(), str(b or "").strip()) if p)
    assert joined("Edition 1", "2026-09-11") == "Edition 1  ·  2026-09-11"
    assert joined("Preview", "") == "Preview"
    assert joined("", "") == ""


def test_the_fingerprint_requires_every_declared_font_before_it_answers(tmp_path, monkeypatch):
    """A missing font used to make a SMALLER walk, not a refusal: the
    fingerprint answered, health reported it non-null, the deploy assertion
    passed, and the first player to open a card got the 500."""
    for name in pc_face._FONT_FILES.values():
        (tmp_path / name).write_bytes(b"not really a font")
    monkeypatch.setattr(pc_face, "_FONTS_PATH", tmp_path)
    pc_face._require_every_font()                     # all present: no complaint
    (tmp_path / pc_face._FONT_FILES["cjk"]).unlink()
    with pytest.raises(FileNotFoundError) as ex:
        pc_face._require_every_font()
    assert pc_face._FONT_FILES["cjk"] in str(ex.value)
    # and the fingerprint is the thing that asks, so health cannot answer over
    # an incomplete set
    with pytest.raises(FileNotFoundError):
        pc_face.renderer_fingerprint()


def test_renderer_fingerprint_and_provenance(monkeypatch):
    first = pc_face.renderer_fingerprint()
    assert len(first) == 16 and all(char in "0123456789abcdef" for char in first)
    monkeypatch.setitem(pc_face.LAYOUT["materials"], "foil_global_opacity", 0.401)
    assert pc_face.renderer_fingerprint() != first
    provenance = pc_face.runtime_provenance()
    assert provenance["layout_engine"] in {"raqm", "basic"}
    assert set(provenance["features"]) == {"zlib", "freetype2", "harfbuzz", "fribidi", "raqm"}
    assert len(provenance["package_digest"]) == 64


def test_catalogue_keys_equal_label_ids():
    catalogue = json.loads((Path(pc_face.ASSETS_DIR) / "catalogue.json").read_text(encoding="utf-8"))
    expected = (
        "pc.band.common", "pc.band.uncommon", "pc.band.rare", "pc.band.epic",
        "pc.band.legendary", "pc.band_short.common", "pc.band_short.uncommon",
        "pc.band_short.rare", "pc.band_short.epic", "pc.band_short.legendary",
        "pc.foil", "pc.foil_short", "pc.signed", "pc.top_card", "pc.stat.rank",
        "pc.stat.rating", "pc.stat.pool", "pc.stat.board", "pc.stat.record",
        "pc.preview_footer", "pc.unnamed", "pc.edition", "pc.unranked",
    )
    assert pc_face.LABEL_IDS == expected
    assert tuple(catalogue) == pc_face.LABEL_IDS
    assert catalogue == pc_face.ENGLISH

    # ...and the CLIENT table that produces the translation keys. `_pc_labels`
    # resolves each label by the composite `english + U+0004 + identifier`, and
    # only a `TrC` call site with that identifier as its context creates such a
    # row -- so a catalogue identifier missing from PcLabels.cs is a label that
    # renders in English in every locale, quietly, with nothing to see in a log
    # (r19 H2: the consumer shipped and the producer did not).
    # resolve() first: whichever test module imported pc_face first decides
    # whether __file__ carries a "tests/../api" segment, and parents[] of an
    # unresolved path counts that ".." as a directory (collection-order flake)
    repo = Path(pc_face.__file__).resolve().parents[2]
    labels_cs = (repo / "plugin" / "PcLabels.cs").read_text(encoding="utf-8")
    call = re.compile(r'case "([^"]+)":\s*return I18n\.TrC\("([^"]+)",\s*'
                      r'"((?:[^"\\]|\\.)*)"\);')
    pairs = {}
    for ident, ctx, english in call.findall(labels_cs):
        assert ident == ctx, (ident, ctx)   # the context IS the identifier
        pairs[ident] = english.replace('\\"', '"').replace("\\\\", "\\")
    assert pairs == catalogue, (sorted(set(pairs) ^ set(catalogue)),
                                {k: (pairs.get(k), catalogue.get(k))
                                 for k in catalogue if pairs.get(k) != catalogue.get(k)})

    # ...and that the extractor really harvested them, so `sync-keys` has rows
    # to create. The msgctxt the server queries is the ENGLISH, then U+0004,
    # then the identifier -- built here from the catalogue so the test cannot
    # agree with a typo on both sides.
    source = json.loads((repo / "tools" / "i18n_source.json").read_text(encoding="utf-8"))
    harvested = set(source.get("contexts") or {})
    want = {v + "\x04" + k for k, v in catalogue.items()}
    assert want <= harvested, sorted(want - harvested)


def test_the_name_budget_follows_the_chips_and_the_tile_shrinks_before_it_cuts():
    """2026-09-13 (bug #361 feedback): the name is measured against the chips
    actually drawn, not the layout rect, with a gap kept clear, and the tile
    shrinks to its own floor before it ellipsises. A common chip is narrower
    than a legendary one, so the same name gets more room beside it; a foil
    chip on the same row can only narrow the budget."""
    name = "Twenty Character Nam"
    img = Image.new("RGBA", (750, 1050))
    left_leg = pc_face._draw_chip(img, 696, 38, "LEGENDARY", "LEG", (1, 1, 1), (2, 2, 2), 1.0, False)
    left_com = pc_face._draw_chip(img, 696, 38, "COMMON", "COM", (1, 1, 1), (2, 2, 2), 1.0, False)
    assert 502 <= left_leg < left_com < 696          # the chip reports its left edge; the wider chip, the smaller x
    gap = pc_face.NAME_CHIP_GAP
    beside_leg = pc_face._name_fit(name, "card", left_leg - gap)
    beside_com = pc_face._name_fit(name, "card", left_com - gap)
    assert beside_leg[0] == beside_com[0] == name and beside_com[1] >= beside_leg[1]
    # the fitted text never crosses the edge it was given
    assert pc_face._measure_text(beside_leg[0], beside_leg[1], "black") <= left_leg - gap - pc_face.NAME_LEFT
    # the tile: beside the RARE chip this name was cut to eleven characters at the old 28 px floor; whole now
    tile = Image.new("RGBA", (375, 525))
    left_rare = pc_face._draw_chip(tile, 348, 19, "RARE", "RARE", (1, 1, 1), (2, 2, 2), 0.5, True)
    fitted, px = pc_face._name_fit(name, "tile", left_rare - gap * 0.5)
    assert fitted == name and pc_face.NAME_SIZE_MIN_CARD // 2 <= px < 28
    # one floor, the card's; the tile has none of its own (r5 L11)
    assert pc_face.NAME_SIZE_MIN_CARD == 34 and not hasattr(pc_face, "NAME_SIZE_MIN_TILE")
    # parity by construction: beside the widest chip, for every length, the tile keeps
    # exactly the text the card keeps (whole or cut alike) at half the size, and that
    # text stays inside the tile's own budget to within the font's rounding
    left_leg_t = pc_face._draw_chip(tile, 348, 19, "LEGENDARY", "LEG", (1, 1, 1), (2, 2, 2), 0.5, True)
    edge_t = left_leg_t - gap * 0.5
    flips = 0
    for n in range(1, 41):
        nm = ("Wm" * 20)[:n]
        card = pc_face._name_fit(nm, "card", edge_t * 2.0)
        tile_fit = pc_face._name_fit(nm, "tile", edge_t)
        assert tile_fit[0] == card[0], (n, card, tile_fit)                 # the same text, whole or cut alike
        half = max(1, round(card[1] * 0.5))
        assert half - 3 <= tile_fit[1] <= half, (n, card, tile_fit)        # half the size, less the font's rounding
        assert pc_face._measure_text(tile_fit[0], tile_fit[1], "black") <= edge_t - pc_face.NAME_LEFT * 0.5, n
        flips += card[0] != nm
    assert 0 < flips < 40   # the range crosses the whole/cut boundary, so the parity was exercised on both sides
    # without a chip edge the layout rect still bounds the name (fit_name, the old entry point)
    assert pc_face.fit_name("Ace", "card") == "Ace" and pc_face.fit_name("x" * 60, "card").endswith("...")
