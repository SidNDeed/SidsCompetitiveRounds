"""Admin evidence report, phase 2 (ship-gate row B10): the required behaviours
of review round B10-R3 (ruling B10-A7), each proven by a test here that fails
on the reviewed tip b2bc9643 and passes at the fix.

  R3-H1  a combat contribution is a match's only when its STORED match_id
         (combat_contrib.match_id, migration 401, written by the worker in the
         INSERT that derives the row) equals the reported game's id. Two
         matches sharing room, pair and UTC end day are told apart: a row the
         worker kept while it moved the games row to the other match stays
         with the match it was derived for, and on the other match it shows
         under `unattributed`, in no total. A row with no stored match (written
         before 401) is `unattributed` wherever it is shown. A window counts a
         row once: in the total of the covered game it was stored for, never
         also as `unattributed` under another covered game's identity.
         (The worker half, test_combat_evidence_live
         test_r3h1_the_worker_stamps_the_match_and_a_kept_contribution_keeps_it.)
  R3-H2  a contribution of either source whose stored match_id is a page
         game's id is found through that match id (the `contrib_keys`
         statement on ix_<contrib>_match), without an evidence record naming
         the game's room and without a games row attached to the game.
"""

import asyncio
import datetime as dt
import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

from test_admin_evidence_sections import T0, _data, _facts, _grow, _on, _pair, _rec, ae  # noqa: E402
import test_admin_evidence_sections_pg as sp  # noqa: E402
from test_admin_evidence_routes_pg import rig  # noqa: E402,F401

ENDED9 = T0 - dt.timedelta(hours=1)        # M9 ended 11:00 UTC
ENDED8 = T0 - dt.timedelta(hours=2)        # M8 ended 10:00 UTC, the same UTC day
COMPUTED = T0                              # the contributions were derived at 12:00


def _g(p1, p2, room, ended):
    return {"id": str(uuid.uuid4()), "room": room, "p1": p1, "p2": p2, "ended": ended}


def _crow(src, key, lo, hi, subject, match_id, **cols):
    """A stored contribution row, identity exactly as given, its stored
    match_id as given."""
    row = {"stable_game_key": key, "pair_lo": lo, "pair_hi": hi, "subject_player_id": subject,
           "source": "self", "coverage": "one", "computed_at": COMPUTED,
           "utc_day": T0.date(), "match_id": match_id}
    row.update({c: 0 for c in ae._SECTION_SPEC[src]["contrib_cols"]})
    if src == "combat":
        row["sums"] = "{}"
    row.update(cols)
    return row


def _seat(section, i):
    """The seat whose subject index is `i` (M8 lists B first: seats follow the
    match row's p1, p2 order)."""
    seat = next(s for s in section["seats"] if s["subject"] == i)
    return seat["state"], _facts(seat["facts"])


def _scenario():
    """The B10-R3 H1 scenario as stored: M9 (A, B) and M8 (B, A: the other
    column order) share room R and pair A/B and end the same UTC day, M8
    first. A's record under (K, A, B, R) was derived while only M9 was
    visible: A's `self` row and A's `meas` row about B, coverage one, stored
    for M9. Then B's record arrived, the worker selected the earlier M8, the
    derivation faulted, the rows were kept and the games row moved to M8
    with paired coverage."""
    a, b = _pair()
    m9, m8 = _g(a, b, "R", ENDED9), _g(b, a, "R", ENDED8)
    contrib = [_crow("combat", "K", a, b, a, m9["id"], sums='{"a1s": [1, 2, 3]}'),
               _crow("combat", "K", a, b, b, m9["id"], source="meas", sums='{"a1s": [4]}')]
    data = _data(records=[_rec("combat", "K", a, b, "R"), _rec("combat", "K", b, a, "R")],
                 games=[_grow("combat", "K", a, b, m8["id"], coverage="paired", records_n=2)],
                 contrib=contrib, switches=_on("combat"))
    return a, b, m9, m8, data


# ── R3-H1: the stored match decides ───────────────────────────────────────

def test_r3h1_the_review_scenario_the_kept_rows_are_the_match_they_were_stored_for():
    a, b, m9, m8, data = _scenario()
    index = {a: 0, b: 1}
    s8 = ae.game_section("combat", data, m8, index)
    assert _facts(s8["game"])["paired"] == "attached"
    _sa, fa = _seat(s8, 0)
    _sb, fb = _seat(s8, 1)
    assert not any(k.startswith("contrib1.") for k in fa | fb), (fa, fb)
    assert (fa.get("unattributed1.source"), fa.get("unattributed1.a1s.total")) == ("self", "6"), fa
    assert (fb.get("unattributed1.source"), fb.get("unattributed1.a1s.total")) == ("meas", "4"), fb
    s9 = ae.game_section("combat", data, m9, index)
    _sa, fa9 = _seat(s9, 0)
    _sb, fb9 = _seat(s9, 1)
    assert (fa9.get("contrib1.source"), fa9.get("contrib1.a1s.total")) == ("self", "6"), fa9
    assert (fb9.get("contrib1.source"), fb9.get("contrib1.a1s.total")) == ("meas", "4"), fb9
    assert not any(k.startswith("unattributed") for k in fa9 | fb9), (fa9, fb9)


def test_r3h1_the_review_scenario_windows_count_each_row_once_for_its_match():
    a, b, m9, m8, data = _scenario()
    w8a = _facts(ae.summary_section("combat", data, [m8], a, 0)["facts"])
    w8b = _facts(ae.summary_section("combat", data, [m8], b, 1)["facts"])
    assert "self.a1s.total" not in w8a and w8a.get("contrib") == "not_derived", w8a
    assert w8a.get("unattributed") == "1" and w8b.get("unattributed") == "1", (w8a, w8b)
    assert "meas.a1s.total" not in w8b, w8b
    w9a = _facts(ae.summary_section("combat", data, [m9], a, 0)["facts"])
    w9b = _facts(ae.summary_section("combat", data, [m9], b, 1)["facts"])
    assert w9a.get("self.a1s.total") == "6" and "unattributed" not in w9a, w9a
    assert w9b.get("meas.a1s.total") == "4" and "unattributed" not in w9b, w9b
    for order in ([m8, m9], [m9, m8]):
        wa = _facts(ae.summary_section("combat", data, order, a, 0)["facts"])
        wb = _facts(ae.summary_section("combat", data, order, b, 1)["facts"])
        assert wa.get("self.a1s.total") == "6" and "unattributed" not in wa, wa
        assert wb.get("meas.a1s.total") == "4" and "unattributed" not in wb, wb


def test_r3h1_a_row_without_a_stored_match_is_unattributed():
    """A combat row written before 401 (match_id NULL) under the game's own
    attached identity, with the subject's record naming the game's room and
    the game's UTC end day: no read-time condition makes it the game's."""
    a, b = _pair()
    g = _g(a, b, "R", ENDED9)
    data = _data(records=[_rec("combat", "K", a, b, "R")],
                 games=[_grow("combat", "K", a, b, g["id"])],
                 contrib=[_crow("combat", "K", a, b, a, None, utc_day=ENDED9.date(),
                                sums='{"a1s": [2, 3]}')],
                 switches=_on("combat"))
    _s, fa = _seat(ae.game_section("combat", data, g, {a: 0, b: 1}), 0)
    assert "contrib1.source" not in fa and fa.get("unattributed1.a1s.total") == "5", fa
    assert fa.get("contrib") == "not_derived", fa
    w = _facts(ae.summary_section("combat", data, [g], a, 0)["facts"])
    assert "self.a1s.total" not in w and w.get("unattributed") == "1", w


# ── R3-H2: discovery through the stored match id (statement level) ────────

class _Db:
    """A stand-in for the session `_section_read` reads through: each
    statement of the source answers the rows given for it by name."""

    def __init__(self, src, answers):
        self.names = {v: k for k, v in ae.SECTION_SQL[src].items()}
        self.answers = answers
        self.calls = []

    async def execute(self, clause, params):
        name = self.names[str(clause)]
        self.calls.append((name, params))
        rows = self.answers.get(name, [])
        return type("R", (), {"mappings": lambda _s: type(
            "M", (), {"all": lambda _m: [dict(r) for r in rows]})()})()


@pytest.mark.parametrize("src", ("card", "combat"))
def test_r3h2_a_key_found_only_by_a_contribution_s_match_is_read(src):
    a, b = _pair()
    m9 = _g(a, b, "R", ENDED9)
    row = _crow(src, "K", a, b, a, m9["id"])
    db = _Db(src, {"contrib_keys": [{"stable_game_key": "K"}], "contrib": [row]})
    data = asyncio.run(ae._section_read(db, src, [m9], [], T0.date()))
    asked = dict(db.calls)
    assert asked["contrib_keys"]["ids"] == [m9["id"]], db.calls
    assert asked["contrib"]["keys"] == ["K"], db.calls
    assert data["contrib"] == [row] and data["truncated"] is False, data


@pytest.mark.parametrize("src", ("card", "combat"))
def test_r3h2_a_full_contribution_key_read_marks_the_section_truncated(src):
    a, b = _pair()
    m9 = _g(a, b, "R", ENDED9)
    full = [{"stable_game_key": "K%03d" % i}
            for i in range(ae.AER_CONTRACT_BOUNDS["SECTION_KEYS_MAX"])]
    data = asyncio.run(ae._section_read(_Db(src, {"contrib_keys": full}), src, [m9], [],
                                        T0.date()))
    assert data["truncated"] is True


# ── Both through the routes, live PostgreSQL ──────────────────────────────

def _seat_of(body, src, steam):
    s = sp._section(body, 0, src)
    seat = next(x for x in s["seats"] if body["subjects"][x["subject"]]["steam_id"] == steam)
    return s, seat["state"], _facts(seat["facts"])


@pytest.mark.parametrize("src", ("card", "combat"))
@pytest.mark.parametrize("games_row", ("absent", "elsewhere"))
def test_r3h2_pg_a_contribution_with_no_record_and_no_games_row_for_the_game(rig, src,
                                                                         games_row):
    """M9 (A, B) has one stored contribution of `src`, subject A, match_id M9;
    no evidence record of `src` names any room, and the games row of its
    identity is absent or attached to M8. M9's report and an M9-only pair
    window show it; nothing is truncated."""
    async def go():
        await sp._up(rig)
        admin = await sp._admin(rig)
        a, sa, _d = await rig.player()
        b, sb, _d = await rig.player()
        m8 = await rig.match(b, a, sp.NOW - dt.timedelta(hours=3), photon_room_id="r8",
                             is_ranked=True)
        m9 = await rig.match(a, b, sp.NOW - dt.timedelta(hours=2), photon_room_id="r9",
                             is_ranked=True)
        if games_row == "elsewhere":
            await sp.grow(rig, src, "K", a, b, m8)
        cols = {"hands": 5} if src == "card" else {"sums": '{"a1s": [1, 2, 3]}'}
        await sp.contrib(rig, src, "K", a, b, a, match_id=m9, **cols)
        await rig.commit()
        out = {}
        for name, path in (("m9", "%s/game/%s" % (sp.ROOT, m9.hex)),
                           ("pair", "%s/pair?a=%s&b=%s&games=1" % (sp.ROOT, sa, sb))):
            st, c = await sp.get(rig, path, admin, sp.HEADER)
            out[name] = (st, sp._body(c))
        return sa, out

    sa, out = rig.run(go())
    assert all(st == 200 for st, _b in out.values()), {k: v[0] for k, v in out.items()}
    sec, state, fa = _seat_of(out["m9"][1], src, sa)
    want = ("contrib1.hands", "5") if src == "card" else ("contrib1.a1s.total", "6")
    assert state == "no_record" and fa.get(want[0]) == want[1], (state, fa)
    assert sec["truncated"] is False, sec
    entries = {(e["oi"], e["src"]): e for e in out["pair"][1]["sections_summary"]}
    w = entries[(0, src)]
    total = ("self.hands", "5") if src == "card" else ("self.a1s.total", "6")
    assert _facts(w["facts"]).get(total[0]) == total[1] and w["truncated"] is False, w


def test_r3h1_pg_the_review_scenario_through_the_game_and_pair_routes(rig):
    """The R3-H1 scenario in the production tables, read by the production
    statements: M8's report shows the rows stored for M9 as `unattributed`
    only, M9's report and the pair windows count them for M9, once."""
    async def go():
        await sp._up(rig)
        admin = await sp._admin(rig)
        a, sa, _d = await rig.player()
        b, sb, _d = await rig.player()
        e9, e8 = sp.NOW - dt.timedelta(hours=2), sp.NOW - dt.timedelta(hours=3)
        m9 = await rig.match(a, b, e9, photon_room_id="rR", is_ranked=True)
        m8 = await rig.match(b, a, e8, photon_room_id="rR", is_ranked=True)
        await sp.rec(rig, "combat", "K", a, b, "rR")
        await sp.rec(rig, "combat", "K", b, a, "rR")
        await sp.grow(rig, "combat", "K", a, b, m8, coverage="paired", records_n=2)
        await sp.contrib(rig, "combat", "K", a, b, a, sums='{"a1s": [1, 2, 3]}',
                         utc_day=e9.date(), match_id=m9)
        await sp.contrib(rig, "combat", "K", a, b, b, source="meas", sums='{"a1s": [4]}',
                         utc_day=e9.date(), match_id=m9)
        await rig.commit()
        pages = {}
        for name, path in (("m8", "%s/game/%s" % (sp.ROOT, m8.hex)),
                           ("m9", "%s/game/%s" % (sp.ROOT, m9.hex)),
                           ("both", "%s/pair?a=%s&b=%s&games=2" % (sp.ROOT, sa, sb)),
                           ("m9only", "%s/pair?a=%s&b=%s&games=1" % (sp.ROOT, sa, sb))):
            st, c = await sp.get(rig, path, admin, sp.HEADER)
            pages[name] = (st, sp._body(c))
        return sa, sb, pages

    sa, sb, pages = rig.run(go())
    assert all(st == 200 for st, _b in pages.values()), {k: v[0] for k, v in pages.items()}
    _s, _st, fa8 = _seat_of(pages["m8"][1], "combat", sa)
    _s, _st, fb8 = _seat_of(pages["m8"][1], "combat", sb)
    assert not any(k.startswith("contrib1.") for k in fa8 | fb8), (fa8, fb8)
    assert fa8.get("unattributed1.a1s.total") == "6", fa8
    assert fb8.get("unattributed1.a1s.total") == "4", fb8
    _s, _st, fa9 = _seat_of(pages["m9"][1], "combat", sa)
    _s, _st, fb9 = _seat_of(pages["m9"][1], "combat", sb)
    assert fa9.get("contrib1.a1s.total") == "6" and fb9.get("contrib1.a1s.total") == "4"
    assert not any(k.startswith("unattributed") for k in fa9 | fb9), (fa9, fb9)
    for name in ("both", "m9only"):
        entries = {(e["oi"], e["src"]): e for e in pages[name][1]["sections_summary"]}
        wa, wb = _facts(entries[(0, "combat")]["facts"]), _facts(entries[(1, "combat")]["facts"])
        assert wa.get("self.a1s.total") == "6" and "unattributed" not in wa, (name, wa)
        assert wb.get("meas.a1s.total") == "4" and "unattributed" not in wb, (name, wb)
