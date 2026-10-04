"""Bug 408: the top card's art geometry (board row 33 follow-up).

The 1.41.0 client lays the top card's art over [100,651,167,745] of the face
(67x94, its backing plate the same rect). The server face drew its own patch
at [92,646,172,750] (80x104), so in game the client covered only the middle of
it and the server's copy showed around it: the card twice. ONE geometry now,
the client's, stated once on the server (face_layout_v1.json, read through
pc_face.card_art_rect), and a bundle cut for any other geometry is refused
whole, so a box whose code and bundle disagree draws NO art rather than a
patch at the wrong size or place.

Items: 1 the rect and the patch size at every scale the bot receives, stated
once; 3 both mixed states (new code with the old bundle, a renderer on the old
layout with the new bundle) render without the patch and read 1, never 3; 5
the face revision moves with the geometry. Every bundle is SYNTHETIC.
"""
from __future__ import annotations

import ast
import io
import json
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
import pc_portrait  # noqa: E402
import pc_strip  # noqa: E402
import card_art_fixture as fx  # noqa: E402

# The 1.41.0 client lane's overlay, measured in plugin/PlayerCardsUI.cs at the
# lane tip (TC_BACK_* and TC_ART_*: x 100/750, y 651/1050, w 67/750, h
# 94/1050, both the same box). Pinned here as numbers on purpose: this is the
# contract with the client, and the layout file must keep stating it.
CLIENT_RECT = (100, 651, 167, 745)
CARD_SIZE = (67, 94)
# render_face draws the tile at scale 0.5 (_scale_rect: floor(v * 0.5 + 0.5))
# and the patch's tile image is its reduce(2); the pack strip and binder grid
# composites paste those tiles unscaled (pc_strip), so these are every scale
# at which the bot receives a pasted patch.
TILE_RECT = (50, 326, 84, 373)
TILE_SIZE = (34, 47)


def _img(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("RGBA").copy()


def _spec(**over):
    values = {
        "band": "epic", "name": "Sid", "title": "Master I", "title_rgb": (85, 216, 70),
        "subtitle": None, "rating": 1650, "pool_rank": 4, "board_rank": 4, "wins": 30,
        "losses": 9, "foil": False, "signed": False, "sign": None,
        "edition_label": "Edition 1", "minted_on": "2026-09-27", "print_short": "#d4c3a1",
        "top_card": "Barrage", "top_card_rgb": None,
    }
    values.update(over)
    return values


def _render(spec, size):
    return _img(pc_face.render_face(spec, {}, None, size))


@pytest.fixture
def clean_caches():
    pc_face._card_art_selftest_at.cache_clear()
    pc_face._card_art_bundle_at.cache_clear()
    yield
    pc_face._card_art_selftest_at.cache_clear()
    pc_face._card_art_bundle_at.cache_clear()


def _wire(monkeypatch, dest):
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", dest)


def _old_layout(monkeypatch):
    """The 71f30e01 layout's two art rects, everything else unchanged: what a
    renderer on the code before bug 408 has loaded."""
    monkeypatch.setitem(pc_face.LAYOUT["rects"], "badge_art_back", list(fx.OLD_BACK))
    monkeypatch.setitem(pc_face.LAYOUT["rects"], "badge_art", list(fx.OLD_ART))


def _no_art_render(monkeypatch, spec, size):
    with monkeypatch.context() as m:
        m.setattr(pc_face, "card_art_patch", lambda _n, _s: None)
        return _render(spec, size)


# ── item 1: one geometry, the client's ──────────────────────────────────────

def test_the_layout_states_the_clients_overlay_rect():
    rects = pc_face.LAYOUT["rects"]
    assert rects["badge_art_back"] == list(CLIENT_RECT)
    assert rects["badge_art"] == list(CLIENT_RECT)
    assert pc_face.card_art_rect() == CLIENT_RECT
    assert pc_face.card_art_size() == CARD_SIZE
    assert pc_face._scale_rect(pc_face.card_art_rect(), 0.5) == TILE_RECT
    assert pc_face.card_art_rect_word() == "100,651,167,745"


@pytest.mark.parametrize("size", ["card", "tile"])
def test_the_patch_lands_exactly_on_the_client_rect_at_each_scale(tmp_path, monkeypatch, clean_caches, size):
    dest = tmp_path / "cards"
    fx.write_bundle(dest)
    _wire(monkeypatch, dest)
    patch = pc_face.card_art_patch("Barrage", size)
    rect, want_size = (CLIENT_RECT, CARD_SIZE) if size == "card" else (TILE_RECT, TILE_SIZE)
    assert patch is not None and patch.size == want_size
    face = _render(_spec(), size)
    bare = _no_art_render(monkeypatch, _spec(), size)
    assert face.crop(rect).tobytes() == patch.tobytes()
    # Nothing of the patch outside the client rect: blank the rect in both
    # renders and the rest is byte-equal.
    for image in (face, bare):
        image.paste((0, 0, 0, 0), rect)
    assert face.tobytes() == bare.tobytes()


def test_the_composites_paste_the_tile_unscaled():
    x0, y0, x1, y1 = pc_strip.strip_paste_boxes(1, 1)[0]
    assert (x1 - x0, y1 - y0) == (pc_face.TILE_W, pc_face.TILE_H) == (375, 525)


def test_pc_face_states_the_geometry_once():
    """No second literal: the art rect is read from the layout in exactly one
    place, and pc_face.py holds no number or size pair of it."""
    source = (API / "pc_face.py").read_text(encoding="utf-8")
    assert source.count('LAYOUT["rects"]["badge_art_back"]') == 1
    tree = ast.parse(source)
    ints = {node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and type(node.value) is int}
    assert not ints & {651, 745, 167}, sorted(ints & {651, 745, 167})
    pairs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) == 2 and all(
                isinstance(e, ast.Constant) and type(e.value) is int for e in node.elts):
            pairs.add(tuple(e.value for e in node.elts))
    assert not pairs & {CARD_SIZE, (80, 104), TILE_SIZE}, sorted(pairs & {CARD_SIZE, (80, 104), TILE_SIZE})


def test_a_written_bundle_records_the_geometry_it_was_cut_for(tmp_path):
    dest = tmp_path / "cards"
    fx.write_bundle(dest)
    index = json.loads((dest / pc_face.CARD_ART_INDEX).read_text(encoding="utf-8"))
    assert index["geometry"] == {"badge_art": list(CLIENT_RECT), "badge_art_back": list(CLIENT_RECT)}
    assert {(e["width"], e["height"]) for e in index["cards"].values()} == {CARD_SIZE}


# ── item 3: mixed states fail toward NO art ─────────────────────────────────

def test_new_code_with_the_bundle_cut_before_bug_408_draws_no_art(tmp_path, monkeypatch, clean_caches):
    """The bundle staged before bug 408 (80x104, no geometry) under this code:
    refused WHOLE by the geometry gate, the face draws the name-only badge (the
    whole face equals the render with the art layer bypassed, so no patch at
    the old rect nor the new), and the self-test reads 1 -- not the healthy 3."""
    dest = tmp_path / "pc-cards-old"
    fx.write_bundle_as_71f30e01(dest)
    _wire(monkeypatch, dest)
    bundle = pc_face.card_art_bundle()
    assert bundle.status == "invalid" and bundle.reason.startswith("geometry:"), bundle.reason
    assert pc_face.card_art_patch("Barrage", "card") is None
    assert pc_face.card_art_drawn(_spec()) is False
    for size in ("card", "tile"):
        assert _render(_spec(), size).tobytes() == _no_art_render(monkeypatch, _spec(), size).tobytes()
    assert pc_face.card_art_selftest()["word"] == 1


def test_a_renderer_on_the_old_layout_with_the_new_bundle_draws_no_art(tmp_path, monkeypatch, clean_caches):
    """The other mixed state, with the reader keyed on the geometry (#744):
    the new bundle is accepted under this layout first, then the layout the
    renderer holds is the 71f30e01 one -- the bundle must be refused whole,
    no patch drawn, the self-test 1. A reader cached on the directory alone
    would keep answering "accepted"."""
    dest = tmp_path / "pc-cards-new"
    fx.write_bundle(dest)
    _wire(monkeypatch, dest)
    assert pc_face.card_art_bundle().status == "accepted"                        # control
    assert pc_face.card_art_selftest()["word"] == 3                             # control
    _old_layout(monkeypatch)
    bundle = pc_face.card_art_bundle()
    assert bundle.status == "invalid" and bundle.reason.startswith("geometry:"), bundle.reason
    assert pc_face.card_art_patch("Barrage", "card") is None
    for size in ("card", "tile"):
        assert _render(_spec(), size).tobytes() == _no_art_render(monkeypatch, _spec(), size).tobytes()
    assert pc_face.card_art_selftest()["word"] == 1


def test_the_71f30e01_reader_cannot_admit_a_new_bundle(tmp_path):
    """The code before bug 408 (pc_face.py at 71f30e01) requires the index keys
    to be exactly {format, tool_version, provenance, cards} (its line 1858)
    and every entry to be 80x104 (its line 1783); a new bundle fails both, so
    that code refuses it whole and draws the name-only badge (word 1). The
    witness in the build notes runs that code against the real new bundle."""
    dest = tmp_path / "cards"
    fx.write_bundle(dest)
    index = json.loads((dest / pc_face.CARD_ART_INDEX).read_text(encoding="utf-8"))
    assert set(index) - {"format", "tool_version", "provenance", "cards"} == {"geometry"}
    assert all((e["width"], e["height"]) != (80, 104) for e in index["cards"].values())


# ── item 5: every cached face is re-keyed ───────────────────────────────────

def test_the_face_revision_moves_with_the_art_geometry_alone(monkeypatch):
    """face_rev keys on renderer_fp, and renderer_fp carries the layout the
    renderer loaded: changing ONLY the art rects moves both. (The layout
    FILE's bytes and pc_face.py ride the fingerprint too, so a deploy of this
    change moves every face_rev on its own.)"""
    spec = _spec()
    fp_new = pc_face.renderer_fingerprint()
    rev_new = pc_portrait.face_rev(fp_new, "cat", spec, "none", None)
    _old_layout(monkeypatch)
    fp_old = pc_face.renderer_fingerprint()
    assert fp_old != fp_new
    assert pc_portrait.face_rev(fp_old, "cat", spec, "none", None) != rev_new
