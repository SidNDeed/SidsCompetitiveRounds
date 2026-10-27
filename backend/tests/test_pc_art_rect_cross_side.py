"""The top card's art rect, read from BOTH sides (v1.41.0 merge pass 6).

The server states the art geometry once, in face_layout_v1.json, read through
pc_face.card_art_rect (rects.badge_art_back) and rects.badge_art. The client
places its backing plate and its art over the face with TC_BACK_* and TC_ART_*
in plugin/PlayerCardsUI.cs, as fractions of the 750x1050 face. The two must
name the same pixels, or the client covers only part of the server's patch
and the card shows twice. test_pc_card_art_geometry.py pins the server half
to a number written into the test; this file derives both halves from their
own sources, so an edit to either side alone fails here.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = HERE.parent / "api"
ROOT = HERE.parent.parent
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

import pc_face  # noqa: E402

CS = ROOT / "plugin" / "PlayerCardsUI.cs"
CONST = re.compile(r"\bTC_(BACK|ART)_(X|Y|W|H)\s*=\s*(\d+)f\s*/\s*(\d+)f")


def _client_rects():
    src = CS.read_text(encoding="utf-8")
    found = {}
    for kind, axis, num, den in CONST.findall(src):
        key = (kind, axis)
        assert key not in found, ("stated twice", key)
        found[key] = (int(num), int(den))
    assert len(found) == 8, sorted(found)
    card_w, card_h = pc_face.LAYOUT["canvas"]["card"]
    rects = {}
    for kind in ("BACK", "ART"):
        for axis in ("X", "W"):
            assert found[(kind, axis)][1] == card_w, (kind, axis, found[(kind, axis)])
        for axis in ("Y", "H"):
            assert found[(kind, axis)][1] == card_h, (kind, axis, found[(kind, axis)])
        x, y = found[(kind, "X")][0], found[(kind, "Y")][0]
        w, h = found[(kind, "W")][0], found[(kind, "H")][0]
        rects[kind] = (x, y, x + w, y + h)
    return src, rects


def test_the_client_overlay_and_the_server_layout_name_the_same_pixels():
    src, rects = _client_rects()
    assert rects["BACK"] == tuple(pc_face.card_art_rect()), (rects, pc_face.card_art_rect())
    assert rects["ART"] == tuple(int(v) for v in pc_face.LAYOUT["rects"]["badge_art"]), (
        rects, pc_face.LAYOUT["rects"]["badge_art"])
    # The constants are the ones the overlay is placed with, once each.
    assert src.count("PlaceOverFace(t.face, t.topBack, TC_BACK_X, TC_BACK_Y, TC_BACK_W, TC_BACK_H);") == 1
    assert src.count("PlaceOverFace(t.face, t.topArt, TC_ART_X, TC_ART_Y, TC_ART_W, TC_ART_H);") == 1
