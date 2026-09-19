"""The ladder route is SERVED, and it answers the shape the client reads.

Two failures this file exists to stop, both of which are silent everywhere
else:

  * the route not being mounted. `backend/api/title_ladders.py` has defined
    `GET /api/v1/players/{steam_id}/title-ladders` since migration 331's
    release, and for that whole time main.py never called `include_router`
    on it -- so the route existed, was unit-tested, and answered 404 in
    production. Importing the module proves nothing about whether the app
    serves it; only `app.routes` does.
  * a key rename. The client parses this answer by NAME, field by field, with
    no schema in between. Renaming `games_to_next` to `remaining` is a
    one-word edit here and a silently empty progress bar there -- the reader
    finds no key, `PcInt(null)` is 0, and the bar renders "0 to go" on a
    player who has 45 to go. Every key the client reads is pinned below
    against the LIVE route's own answer, not against a docstring.

The answer is produced by calling the route function with a fake session, so
these are assertions about what the code DOES rather than about what its
source text looks like.
"""

import asyncio
import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import title_ladders as tl  # noqa: E402
import main  # noqa: E402

ROUTE_PATH = "/api/v1/players/{steam_id}/title-ladders"

# Exactly the keys plugin/ApiClient.cs ParseTitleLadders / ParseTitleLadderRung
# read. Kept as three flat sets rather than one nested shape, because that is
# how the client reads them: three separate depth-1 lookups against three
# different objects.
TOP_KEYS = {"steam_id", "active_line", "ladders"}
LINE_KEYS = {"line", "name", "games", "tier", "max_tier", "next_tier",
             "next_threshold", "next_names", "games_to_next", "rungs"}
RUNG_KEYS = {"tier", "sku", "item_id", "name", "description", "rarity",
             "preview_color", "threshold", "price", "owned", "active"}


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Served ─────────────────────────────────────────────────────────

def test_the_ladder_route_is_mounted_on_the_app():
    paths = {getattr(r, "path", None) for r in main.app.routes}
    assert ROUTE_PATH in paths, (
        "%s is not in app.routes. The module defines it, but main.py does not "
        "include_router(title_ladders.router) -- so it answers 404 in "
        "production and the Titles tab renders its unavailable state." % ROUTE_PATH)


def test_the_route_is_mounted_exactly_once():
    """Two include_router calls for one router mount every path twice. It
    works, which is why it survives review -- and then a later edit removes
    one of them and the reviewer reads the remaining line as the fix."""
    hits = [r for r in main.app.routes if getattr(r, "path", None) == ROUTE_PATH]
    assert len(hits) == 1, "the ladder route is mounted %d times" % len(hits)


def test_the_route_is_a_GET():
    hits = [r for r in main.app.routes if getattr(r, "path", None) == ROUTE_PATH]
    assert "GET" in hits[0].methods, hits[0].methods


def test_main_includes_the_ladder_router_exactly_once():
    """Two include_router calls for one router is the failure mode this
    change was warned about by name: the hook brief may add the line too, and
    two of them mount every path twice. That WORKS, which is why it survives
    review -- until a later edit removes one and the remaining line reads as
    the fix. Counted in the source, because app.routes cannot tell one
    include_router call from two identical ones."""
    src = open(main.__file__, encoding="utf-8").read()
    calls = [ln for ln in src.split("\n")
             if ln.strip().startswith("app.include_router(")
             and "title_ladders" in ln]
    assert len(calls) == 1, (
        "expected one include_router for the ladder router, found %d: %r"
        % (len(calls), calls))


# ── The shape the client parses ────────────────────────────────────

class _FakeResult:
    def __init__(self, rows, scalar=None):
        self._rows = rows
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar


class _FakePlayer:
    def __init__(self, steam_id):
        self.id = uuid.uuid4()
        self.steam_id = steam_id
        self.active_title_id = None


class _FakeDb:
    """Answers the route's five queries in order. Deliberately positional:
    the route's query ORDER is part of what this fixture encodes, so a
    reordering shows up as a wrong-shaped answer rather than as a pass."""

    def __init__(self, player, owned_skus, item_ids, progress, active_sku):
        self._answers = [
            _FakeResult([], scalar=player),
            _FakeResult([(s,) for s in owned_skus]),
            _FakeResult(list(item_ids.items())),
            _FakeResult(progress),
            _FakeResult([], scalar=active_sku),
        ]
        self._i = 0

    async def execute(self, *_args, **_kw):
        r = self._answers[self._i]
        self._i += 1
        return r


def _answer(owned=(), progress=(), active_sku=None):
    player = _FakePlayer("76561198000000001")
    # The route resolves the worn sku ONLY when the player row names an item,
    # so a fixture that supplies the sku without the id exercises the
    # never-worn branch while claiming to test the worn one -- which is how
    # this fixture first reported active_line=None for a seeded player.
    if active_sku is not None:
        player.active_title_id = 1
    item_ids = {sku: 1000 + i for i, sku in enumerate(tl.ALL_SKUS)}
    db = _FakeDb(player, owned, item_ids, list(progress), active_sku)
    return _run(tl.get_title_ladders("76561198000000001", db))


def test_the_answer_carries_every_key_the_client_reads():
    a = _answer()
    assert TOP_KEYS <= set(a), TOP_KEYS - set(a)
    assert len(a["ladders"]) == 8
    for ln in a["ladders"]:
        assert LINE_KEYS <= set(ln), (ln["line"], LINE_KEYS - set(ln))
        assert ln["rungs"], ln["line"]
        for r in ln["rungs"]:
            assert RUNG_KEYS <= set(r), (r.get("sku"), RUNG_KEYS - set(r))


def test_the_repeated_key_names_are_real():
    """The client's parser has to be depth-aware, and this is the fact that
    makes it so. If these keys ever STOP recurring, the depth-aware reader is
    still correct -- but the mutation control that proves it is dead, and the
    next person to simplify the parser will find nothing arguing back."""
    ln = _answer()["ladders"][0]
    for key in ("name", "tier", "sku", "threshold"):
        at_line = key in ln
        in_rungs = all(key in r for r in ln["rungs"])
        if key in ("name", "tier"):
            assert at_line and in_rungs, key
        else:
            assert in_rungs, key
    # ...and the line's own name is NOT the first rung's name, so a reader
    # that answers with the first occurrence is visibly wrong rather than
    # accidentally right.
    assert ln["name"] != ln["rungs"][1]["name"]


def test_zero_progress_answers_a_full_board_with_nothing_owned():
    """What every account looks like until the completion hook ships: eight
    lines, 48 rungs, games 0, tier 1, nothing owned, nothing active. The
    client renders this as NOT STARTED per line -- which it can only do if
    `owned` is present and false rather than absent."""
    a = _answer()
    assert a["active_line"] is None
    for ln in a["ladders"]:
        assert ln["games"] == 0 and ln["tier"] == 1
        assert ln["next_tier"] == 2 and ln["next_threshold"] == 10
        assert ln["games_to_next"] == 10
        assert ln["next_names"], ln["line"]
        assert not any(r["owned"] for r in ln["rungs"])
        assert not any(r["active"] for r in ln["rungs"])


def test_a_seeded_player_reports_progress_and_the_worn_rung():
    """30 series on the rat line: tier 3, next rung at 75, 45 to go, and the
    two rungs already crossed owned. The rat tier-4 pair is the case the
    client renders as two chips at one tier."""
    line = "rat"
    owned = [r["sku"] for r in tl.LINES[line]["rungs"] if r["tier"] <= 3]
    active = "title_ladder_rat_3"
    a = _answer(owned=owned, progress=[(line, 30, 3)], active_sku=active)
    assert a["active_line"] == line
    rat = [ln for ln in a["ladders"] if ln["line"] == line][0]
    assert rat["games"] == 30 and rat["tier"] == 3
    assert rat["next_tier"] == 4 and rat["next_threshold"] == 75
    assert rat["games_to_next"] == 45
    assert rat["next_names"] == ["Rat King", "Rat Queen"]
    assert [r["sku"] for r in rat["rungs"] if r["owned"]] == owned
    assert [r["sku"] for r in rat["rungs"] if r["active"]] == [active]
    # Two rungs at tier 4, which is why `rungs` is a list and `next_names` is
    # a list -- a client reading either as a single value shows one crown.
    assert len([r for r in rat["rungs"] if r["tier"] == 4]) == 2
    # Untouched lines stay at zero in the same answer.
    cat = [ln for ln in a["ladders"] if ln["line"] == "cat"][0]
    assert cat["games"] == 0 and not any(r["owned"] for r in cat["rungs"])


def test_the_top_of_a_line_answers_null_and_not_zero():
    """A player at the top has no next rung. The three next_* fields must be
    null: a 0 there reads as "0 more to go", and the client's `has_next` is
    a PRESENCE test for exactly this reason."""
    a = _answer(progress=[("cat", 400, 6)])
    cat = [ln for ln in a["ladders"] if ln["line"] == "cat"][0]
    assert cat["next_tier"] is None
    assert cat["next_threshold"] is None
    assert cat["games_to_next"] is None
    assert cat["next_names"] == []


def test_every_rung_carries_an_item_id_and_a_preview_colour():
    """`item_id` is what the Set Active call names; `preview_color` is the
    column that exists -- `color` does not, and two shipped endpoints already
    500'd on that name (#219)."""
    a = _answer()
    for ln in a["ladders"]:
        for r in ln["rungs"]:
            assert isinstance(r["item_id"], int), (r["sku"], r["item_id"])
            assert r["preview_color"].startswith("#"), r["sku"]
            assert len(r["preview_color"]) == 7, r["preview_color"]


def test_this_file_is_pure_crlf():
    """Tracked .py in this repo is CRLF (#675/#592). Counted in bytes."""
    raw = open(os.path.abspath(__file__), "rb").read()
    crlf, cr, lf = raw.count(b"\r\n"), raw.count(b"\r"), raw.count(b"\n")
    assert cr == crlf == lf, "CRLF=%d CR=%d LF=%d" % (crlf, cr, lf)


def test_an_unknown_steam_id_is_a_404_not_an_empty_board():
    from fastapi import HTTPException
    db = _FakeDb(None, (), {}, [], None)
    with pytest.raises(HTTPException) as exc:
        _run(tl.get_title_ladders("76561198000000002", db))
    assert exc.value.status_code == 404
