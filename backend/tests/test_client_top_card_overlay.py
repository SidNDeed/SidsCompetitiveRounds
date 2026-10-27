"""The in-game Top card overlay lands inside the badge the server drew.

Item 9a turned the face's Top card badge into a NAME COLUMN up the left plus
an empty framed ART AREA beside it. The server draws the column, the frame and
the fill into the PNG; the client lays the live ROUNDS card art over the empty
area at runtime, because only the client knows what the card actually looks
like. Two halves, one rectangle, and NOTHING makes them agree: the client's
fractions were typed by hand from the layout file.

Every way they can disagree is a defect a screenshot shows and no existing
test does -- art over the sideways name, art outside the frame, art at the old
pre-9a size floating in the middle of the badge. So the client's constants are
read out of its own source and checked against `face_layout_v1.json`, which is
the file the renderer itself reads.

This is a CLIENT claim pinned in the backend test tree (the `test_client_*`
arrangement): the layout file is the shared artifact, so a test that reads only
the plugin would pin the copy rather than the contract.
"""
from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
UI = REPO / "plugin" / "PlayerCardsUI.cs"
LAYOUT = REPO / "backend" / "api" / "assets" / "pc" / "face_layout_v1.json"

CARD_W, CARD_H = 750, 1050


def _layout():
    return json.loads(io.open(LAYOUT, encoding="utf-8").read())


def _consts():
    """The four TC_* fractions, as the pixel box they describe.

    Read as ARITHMETIC, not as text: the constants are written `100f / 750f`
    precisely so a reader can see the pixel figure, and evaluating them here
    means a change to either the numerator or the denominator moves what this
    test measures.
    """
    src = io.open(UI, encoding="utf-8").read()
    out = {}
    for m in re.finditer(r"TC_(BACK|ART)_([XYWH])\s*=\s*(\d+(?:\.\d+)?)f\s*/\s*(\d+(?:\.\d+)?)f", src):
        which, axis, num, den = m.group(1), m.group(2), float(m.group(3)), float(m.group(4))
        expected_den = CARD_W if axis in ("X", "W") else CARD_H
        assert den == expected_den, (
            "TC_%s_%s is a fraction of %g, not of the face's %d" % (which, axis, den, expected_den))
        out[(which, axis)] = num
    assert len(out) == 8, "expected eight TC_ constants, found %d" % len(out)
    boxes = {}
    for which in ("BACK", "ART"):
        x, y = out[(which, "X")], out[(which, "Y")]
        boxes[which] = (x, y, x + out[(which, "W")], y + out[(which, "H")])
    return boxes


def test_the_layout_file_still_carries_the_two_rects_this_reads():
    lay = _layout()
    assert "badge" in lay["rects"] and "badge_name" in lay["rects"], (
        "face_layout_v1.json no longer names the badge and its name column; "
        "the client overlay has nothing to be checked against")


def test_the_art_never_covers_the_sideways_name():
    """The column is the card's own name, drawn upward in the card's theme
    colour. Art starting one pixel to its left erases it, and the badge then
    says nothing at all -- which is exactly the state 9a replaced."""
    lay = _layout()
    _, _, name_right, _ = lay["rects"]["badge_name"]
    art_left = _consts()["ART"][0]
    assert art_left >= name_right + 4, (
        "the overlay starts at x=%g and the name column ends at x=%g: the art "
        "is laid over the name" % (art_left, name_right))


def test_the_art_stays_inside_the_frame_the_server_drew():
    """BadgeFrame.png's rails and corner arcs are part of the picture. Art that
    overhangs them reads as a rendering fault rather than as a card."""
    lay = _layout()
    bx0, by0, bx1, by1 = lay["rects"]["badge"]
    ax0, ay0, ax1, ay1 = _consts()["ART"]
    assert ax0 >= bx0 and ay0 >= by0 and ax1 <= bx1 and ay1 <= by1, (
        "the overlay %r is not inside the badge %r"
        % ((ax0, ay0, ax1, ay1), (bx0, by0, bx1, by1)))
    # ...and it does not sit ON the rails: the frame owns four pixels of edge.
    assert ay0 >= by0 + 4 and ay1 <= by1 - 4, (
        "the overlay's top/bottom edge is drawn over the frame's rails: %r in %r"
        % ((ay0, ay1), (by0, by1)))


def test_the_art_actually_uses_the_area_the_badge_reserves_for_it():
    """The pre-9a overlay was 50x73, inset inside a silhouette. Left at that
    size against the new badge it is a small picture floating in a large empty
    frame -- which is what "the card is tiny" looks like from a player's seat.

    The area the badge reserves is everything right of the name column and
    inside the frame; the overlay has to claim essentially all of it.
    """
    lay = _layout()
    bx0, by0, bx1, by1 = lay["rects"]["badge"]
    _, _, name_right, _ = lay["rects"]["badge_name"]
    ax0, ay0, ax1, ay1 = _consts()["ART"]
    avail_w = (bx1 - 6) - (name_right + 4)
    avail_h = (by1 - 4) - (by0 + 4)
    assert (ax1 - ax0) >= avail_w * 0.9, (
        "the overlay is %g wide where %g is clear: the card renders small in "
        "an empty frame" % (ax1 - ax0, avail_w))
    assert (ay1 - ay0) >= avail_h * 0.9, (
        "the overlay is %g tall where %g is clear" % (ay1 - ay0, avail_h))


def test_the_backing_and_the_art_are_one_rectangle():
    """Two rects that can differ are two rects that will. The backing exists so
    a card whose aspect does not match the box has the badge's own dark either
    side of it rather than the portrait showing through."""
    boxes = _consts()
    assert boxes["BACK"] == boxes["ART"], (
        "the backing %r and the art %r are different boxes"
        % (boxes["BACK"], boxes["ART"]))


def test_the_overlay_is_scaled_against_the_drawn_picture_not_the_slot():
    """The face Image preserves its 5:7 aspect inside whatever rect the layout
    gives the slot, so the picture is generally SMALLER than the slot and
    centred in it. An overlay positioned against the slot's rect drifts away
    from the badge by however much letterboxing there is -- and the drift is
    invisible at one tile size and obvious at another.
    """
    src = io.open(UI, encoding="utf-8").read()
    body = src[src.index("private static void PlaceOverFace("):]
    body = body[:body.index("\n        /// <summary>")]
    assert "Mathf.Min(r.width / PlayerCardFaces.CARD_W" in body, (
        "PlaceOverFace no longer derives the drawn picture's scale")
    assert "PlayerCardFaces.CARD_W * s" in body and "PlayerCardFaces.CARD_H * s" in body, (
        "PlaceOverFace sizes the overlay against the slot rather than against "
        "the picture: " + body[:300])


def test_the_overlay_is_replaced_when_the_layout_or_the_snapshot_moves():
    """It is re-placed every frame the tab is up, deliberately: the snapshot
    lands after the tile is built, the layout settles a frame later, and a
    snapshot generation change can void the sprite under it."""
    src = io.open(UI, encoding="utf-8").read()
    assert "PlaceTopCards()" in src, "the per-frame placement call is gone"
    body = src[src.index("private static void PlaceTopCards()"):][:600]
    for tiles in ("revealTiles", "binderTiles", "cardPopupTile"):
        assert tiles in body, (
            "%s no longer gets its overlay placed, so its badge keeps whatever "
            "rect it was built with" % tiles)
