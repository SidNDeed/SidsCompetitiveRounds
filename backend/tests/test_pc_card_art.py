"""The top card's art in the server face (Discord card render parity, board
row 33; build brief sitting 1, item 1).

The game draws the top card's own picture beside its sideways name; the
server face now draws it too, from one optional private bundle. These are
pixel-REGION assertions on rendered fixture cards, never whole-image hashes:
a whole-image hash pins every unrelated pixel and cannot say which layer
broke. Every bundle here is SYNTHETIC (card_art_fixture): the repository
carries no art.

The containment test compares two renders with the SAME spec and the SAME
top-card name, where only the patch resolver is bypassed (pc_face.card_art_patch
answering None) -- so the sideways name, the badge and every other layer are
identical by construction, and any difference outside the art rect is the art
layer leaking.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest
from PIL import Image

HERE = Path(__file__).resolve().parent
API = HERE.parent / "api"
for _p in (str(API), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pc_face  # noqa: E402
import card_art_fixture as fx  # noqa: E402
from pc_themes_data import rows as _theme_rows  # noqa: E402

CARD_RECT = (92, 646, 172, 750)
TILE_RECT = (46, 323, 86, 375)
RECTS = {"card": CARD_RECT, "tile": TILE_RECT}


def _spec(**over):
    values = {
        "band": "rare", "name": "Sid", "title": "Master I", "title_rgb": (85, 216, 70),
        "subtitle": None, "rating": 1650, "pool_rank": 4, "board_rank": 4, "wins": 30,
        "losses": 9, "foil": False, "signed": False, "sign": None,
        "edition_label": "Edition 1", "minted_on": "2026-09-27", "print_short": "#d4c3a1",
        "top_card": "Barrage", "top_card_rgb": None,
    }
    values.update(over)
    return values


def _img(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("RGBA").copy()


def _render(spec, size):
    return _img(pc_face.render_face(spec, {}, None, size))


def _blank_rect(image, rect):
    out = image.copy()
    out.paste((0, 0, 0, 0), rect)
    return out


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    """An accepted synthetic bundle, wired in where the container mounts it."""
    dest = tmp_path / "pc-cards-synthetic"
    fx.write_bundle(dest)
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", dest)
    return dest


@pytest.fixture
def no_bundle(tmp_path, monkeypatch):
    dest = tmp_path / "no-bundle-here"
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", dest)
    return dest


def _bypassed(monkeypatch):
    monkeypatch.setattr(pc_face, "card_art_patch", lambda _name, _size: None)


# ── item 1: the layer lands, stays in its rect, and keeps its order ─────────

@pytest.mark.parametrize("size", ["card", "tile"])
def test_the_top_cards_art_lands_in_its_rect(bundle, size):
    """The crop at the backing rect IS the patch (the tile: its exact 2:1
    reduction), byte for byte. Barrage is not the first name in sorted order,
    so a resolver that only ever served the first entry fails here."""
    names = pc_face.card_art_names()
    assert names[0] != "Barrage" and "Barrage" in names
    face = _render(_spec(), size)
    patch = fx.synthetic_patch("Barrage")
    want = patch if size == "card" else patch.reduce(2)
    assert face.crop(RECTS[size]).tobytes() == want.tobytes()
    assert pc_face.card_art_drawn(_spec()) is True


@pytest.mark.parametrize("size", ["card", "tile"])
@pytest.mark.parametrize("variant", ["plain", "foil_signed"])
def test_the_art_layer_touches_nothing_outside_its_rect(bundle, monkeypatch, size, variant):
    """Containment. Same spec, same top-card name; only the resolver differs.
    Outside the art rect: EXACTLY equal. Inside it: the whole region differs
    (one region inequality, not a per-pixel claim a coincident colour could
    break)."""
    over = {"foil": True, "signed": True} if variant == "foil_signed" else {}
    with_art = _render(_spec(**over), size)
    _bypassed(monkeypatch)
    without = _render(_spec(**over), size)
    rect = RECTS[size]
    assert _blank_rect(with_art, rect).tobytes() == _blank_rect(without, rect).tobytes()
    assert with_art.crop(rect).tobytes() != without.crop(rect).tobytes()


def test_the_art_is_painted_after_the_foil_and_clear_of_the_autograph(bundle):
    """Order: the foil pass runs over the body before the badge, so the art is
    not foiled -- as in game, where the overlay sits above the foiled face. The
    autograph rect never reaches the art rect, so a signed print's line cannot
    land on it or under it."""
    face = _render(_spec(foil=True, signed=True), "card")
    assert face.crop(CARD_RECT).tobytes() == fx.synthetic_patch("Barrage").tobytes()
    auto = pc_face.LAYOUT["rects"]["autograph"]
    art = pc_face.LAYOUT["rects"]["badge_art_back"]
    assert art == list(CARD_RECT)
    assert auto[0] >= art[2] or auto[2] <= art[0] or auto[1] >= art[3] or auto[3] <= art[1]
    assert pc_face.LAYOUT["layer_order"].index("badge_art") == pc_face.LAYOUT["layer_order"].index("badge_name") + 1


@pytest.mark.parametrize("top", ["", "   "])
def test_no_top_card_draws_no_art(bundle, monkeypatch, top):
    """No top card: no badge, so no art -- the whole face equals the render
    with the art layer bypassed."""
    first = _render(_spec(top_card=top), "card")
    _bypassed(monkeypatch)
    assert first.tobytes() == _render(_spec(top_card=top), "card").tobytes()
    assert pc_face.card_art_drawn(_spec(top_card=top)) is False


def test_a_top_card_the_bundle_lacks_keeps_the_name_only_badge(bundle, monkeypatch):
    """A modded or unknown card: the badge stands as before, and the header
    says so."""
    spec = _spec(top_card="Not A Vanilla Card")
    first = _render(spec, "card")
    _bypassed(monkeypatch)
    assert first.tobytes() == _render(spec, "card").tobytes()
    assert pc_face.card_art_drawn(spec) is False


# ── item 1, MEDIUM 4: one accepted map, built only from a whole bundle ──────

def _assert_whole_bundle_refused(monkeypatch, why):
    b = pc_face.card_art_bundle()
    assert b.status == "invalid", (b.status, b.reason)
    assert why in b.reason
    assert b.patches == {} and b.identity == pc_face.CARD_ART_NONE_IDENTITY
    first = pc_face.card_art_names()[0]
    # EVERY card falls back to the name-only badge, the FIRST entry too: the
    # header and the pixels both read the one (empty) map.
    for name in (first, "Barrage"):
        spec = _spec(top_card=name)
        assert pc_face.card_art_drawn(spec) is False
        face = _render(spec, "card")
        with monkeypatch.context() as m:
            _bypassed(m)
            assert face.tobytes() == _render(spec, "card").tobytes()
    assert pc_face.card_art_selftest()["word"] == 1


@pytest.mark.parametrize("damage", ["idat", "opacity"])
def test_a_corrupt_non_first_patch_refuses_the_whole_bundle(bundle, monkeypatch, damage):
    """A self-consistent bundle (index sha256, index bytes and BUNDLE-DIGEST
    all updated) whose LAST entry does not decode, or is not opaque: nothing is
    drawn for any card, the first one included, and the word is 1."""
    last = pc_face.card_art_names()[-1]
    good = pc_face._encode_rgba(fx.synthetic_patch(last))
    if damage == "idat":
        data = fx.corrupt_idat(good)
    else:
        image = fx.synthetic_patch(last)
        image.putpixel((40, 50), (1, 2, 3, 254))
        data = pc_face._encode_rgba(image)
    with pytest.raises(Exception):
        pc_face._card_art_decode(data)
    fx.rewrite_entry(bundle, last, data)
    _assert_whole_bundle_refused(monkeypatch, repr(last))


def test_a_bundle_missing_one_name_is_refused_whole(bundle, monkeypatch):
    """One expected name dropped (file, index and digest consistent): the name
    set differs, so no card draws art -- not merely the missing one."""
    fx.drop_entry(bundle, pc_face.card_art_names()[-2])
    _assert_whole_bundle_refused(monkeypatch, "name set differs: 1 missing")


@pytest.mark.parametrize("damage", ["extra_file", "digest", "noncanonical_index"])
def test_a_bundle_that_is_not_exactly_its_index_is_refused(bundle, monkeypatch, damage):
    if damage == "extra_file":
        (bundle / "notes.txt").write_bytes(b"x")
        why = "files the index does not name"
    elif damage == "digest":
        (bundle / pc_face.CARD_ART_DIGEST_FILE).write_bytes(b"0" * 64 + b"\n")
        why = "BUNDLE-DIGEST"
    else:
        raw = (bundle / pc_face.CARD_ART_INDEX).read_bytes()
        (bundle / pc_face.CARD_ART_INDEX).write_bytes(raw.replace(b":", b": ", 1))
        why = "canonical serialization"
    _assert_whole_bundle_refused(monkeypatch, why)


def test_an_accepted_bundle_validates_every_entry(bundle):
    b = pc_face.card_art_bundle()
    assert b.status == "accepted", b.reason
    assert sorted(b.patches) == list(pc_face.card_art_names())
    assert len(b.digest) == 64
    assert (bundle / pc_face.CARD_ART_DIGEST_FILE).read_text(encoding="ascii") == b.digest + "\n"


# ── item 1, MEDIUM 2: absent or invalid art is never a refusal ──────────────

def test_an_absent_bundle_keeps_the_fingerprint_and_the_base_face(no_bundle, monkeypatch):
    """No bundle directory at all (a clone, a box before staging): the
    renderer fingerprint still answers (16 hex), every face renders with the
    name-only badge, and the word is 1 -- never a refusal."""
    fp = pc_face.renderer_fingerprint()
    assert isinstance(fp, str) and len(fp) == 16
    assert pc_face.card_art_bundle().status == "absent"
    assert pc_face.card_art_selftest()["word"] == 1
    face = _render(_spec(), "card")
    _bypassed(monkeypatch)
    assert face.tobytes() == _render(_spec(), "card").tobytes()


def test_an_empty_bundle_directory_reads_absent(tmp_path, monkeypatch):
    """What docker creates when a bind source is missing: an empty directory."""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", empty)
    assert pc_face.card_art_bundle().status == "absent"
    assert isinstance(pc_face.renderer_fingerprint(), str)


def test_the_fingerprint_frames_the_whole_bundle_as_one_optional_input(tmp_path, monkeypatch):
    """Absent and invalid share one sentinel (same pixels, same key); an
    accepted bundle moves it; a different accepted bundle moves it again."""
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", tmp_path / "none")
    absent = pc_face.renderer_fingerprint()
    good = tmp_path / "good"
    fx.write_bundle(good)
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", good)
    accepted = pc_face.renderer_fingerprint()
    other = tmp_path / "other"
    name = pc_face.card_art_names()[5]
    alt = fx.synthetic_patch(name)
    alt.putpixel((40, 60), (9, 9, 9, 255))
    fx.write_bundle(other, patches={name: alt})
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", other)
    accepted_other = pc_face.renderer_fingerprint()
    bad = tmp_path / "bad"
    fx.write_bundle(bad)
    fx.drop_entry(bad, name)
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", bad)
    invalid = pc_face.renderer_fingerprint()
    assert len({absent, accepted, accepted_other}) == 3
    assert invalid == absent


def test_the_bundle_is_never_a_required_fingerprint_path(tmp_path, monkeypatch):
    """The required-stamp list holds no path inside the bundle directory, and
    the kit PNG walk skips it even when it holds PNGs."""
    dest = tmp_path / "b"
    fx.write_bundle(dest)
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", dest)
    _layout, stamps = pc_face._fingerprint_inputs()
    required = [s for s in stamps if s[0] != "card-art"]
    assert not [s for s in required if str(dest) in str(s[0])]
    assert not [p for p in pc_face._kit_pngs() if p.relative_to(pc_face._ASSETS_PATH).parts[0] == "cards"]
    # The walk itself, over an assets tree that holds both: the mount point's
    # PNGs are never kit PNGs.
    assets = tmp_path / "assets"
    for rel in ("kit/a.png", "cards/b.png", "cardsx/c.png"):
        (assets / rel).parent.mkdir(parents=True, exist_ok=True)
        (assets / rel).write_bytes(b"png")
    monkeypatch.setattr(pc_face, "_ASSETS_PATH", assets)
    assert [p.relative_to(assets).as_posix() for p in pc_face._kit_pngs()] == ["cardsx/c.png", "kit/a.png"]


# ── the self-test behind /health pc_card_art ────────────────────────────────

def test_the_selftest_proves_every_entry_drawn(bundle):
    result = pc_face.card_art_selftest()
    assert result["word"] == 3, result
    assert result["checked"] == len(pc_face.card_art_names())


def test_the_selftest_reads_zero_when_the_accepted_art_is_not_drawn(bundle, monkeypatch):
    """The no-op-resolver mutant: an accepted bundle whose patches never reach
    a face must read 0 (fail at once), never 3 and never 1."""
    pc_face._card_art_selftest_at.cache_clear()
    _bypassed(monkeypatch)
    try:
        assert pc_face.card_art_selftest()["word"] == 0
    finally:
        pc_face._card_art_selftest_at.cache_clear()


# ── the names a bundle must carry, and what a bundle may carry ──────────────

def test_the_expected_names_are_migration_333s():
    assert pc_face.card_art_names() == tuple(sorted(n for n, _t, _i, _s in _theme_rows()))
    slugs = [pc_face.card_art_slug(n) for n in pc_face.card_art_names()]
    assert len(set(slugs)) == len(slugs) and all(slugs)


def test_a_written_bundle_carries_pixels_only(tmp_path):
    """IHDR/IDAT/IEND and nothing else in every patch: no text chunk, no time,
    no path (the privacy hard rule for harvested images)."""
    dest = tmp_path / "b"
    fx.write_bundle(dest)
    for png in sorted(dest.glob("*.png")):
        data = png.read_bytes()
        assert [k for k, _ in pc_face.png_chunks(data) if k not in (b"IHDR", b"IDAT", b"IEND")] == []
        assert b"C:\\Users" not in data and b"tEXt" not in data and b"tIME" not in data
    assert sorted(p.name for p in dest.iterdir() if not p.name.endswith(".png")) == [
        pc_face.CARD_ART_DIGEST_FILE, pc_face.CARD_ART_INDEX]


def test_the_motion_atlas_carries_the_art(bundle, monkeypatch):
    """An atlas cell is a crop of a full render_face over CARD_WINDOW, which
    overlaps the art rect (x 92..172, y 646..740): a cell derived with the
    art differs, IN THAT REGION, from one derived with the layer bypassed."""
    import pc_motion as pcm
    import pc_motion_fixtures as mfx
    # Two frames are enough to prove the layer reaches a cell; the table's
    # frame count is the container's concern, tested in its own file.
    frames = mfx.smooth_frames(2)
    monkeypatch.setattr(pcm, "parse_container", lambda _body: ({}, frames))
    body = b""
    spec = _spec(band="legendary")
    card, _tile = pcm.derive_atlases(spec, {}, body)
    _bypassed(monkeypatch)
    bare, _tile2 = pcm.derive_atlases(spec, {}, body)
    w = pcm.CARD_WINDOW
    scale = pcm.CARD_CELL / float(w[2] - w[0])
    region = (int((92 - w[0]) * scale) + 1, int((646 - w[1]) * scale) + 1,
              int((172 - w[0]) * scale) - 1, pcm.CARD_CELL)
    a, b = _img(card).crop(region), _img(bare).crop(region)
    assert a.tobytes() != b.tobytes()
