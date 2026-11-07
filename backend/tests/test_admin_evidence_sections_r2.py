"""Admin evidence report, phase 2 (ship-gate row B10): the required behaviours
of review round B10-R2 (ruling B10-A4), each proven by a test here that fails
on the reviewed tip afd9493b and passes at the fix.

  R2-H1  a contribution is shown or totalled for a match only when its
         provenance against that match is established from stored state.
         Card: card_contrib.match_id equals the reported game's id. Combat
         (combat_contrib stores no match): the contribution's own record
         (`self`: the subject's record; `meas`: the other seat's record about
         the subject) is one of the game's records (same stored identity,
         attach key = the game's room), its utc_day is the match's UTC end day
         and it was computed no earlier than the match ended; any other
         combat contribution under the game's identity is shown under the
         word `unattributed` and is in no total.
  R2-H2  a games or contribution row's stored identity (stable_game_key,
         pair_lo, pair_hi) is compared exactly as stored, never reordered;
         only an evidence record's two seats are put lower first.
  Bot    the contribution group words equal the api's; a seat fact group under
         `unattributed` decodes and reaches the plan, a seat fact group under
         any other word is refused.
"""

import copy
import datetime as dt
import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

from test_admin_evidence_sections import (SCHEMA, T0, _data, _facts, _grow, _on,  # noqa: E402
                                          _pair, _rec, _sections_for, ae)
from test_discord_evidence_bot import bot_ns, game_body  # noqa: E402
from test_discord_evidence_render import check_plan  # noqa: E402
import test_admin_evidence_sections_pg as sp  # noqa: E402
from test_admin_evidence_routes_pg import rig  # noqa: E402,F401

ENDED9 = T0 - dt.timedelta(hours=3)        # M9 ended first
ENDED8 = T0 - dt.timedelta(hours=2)        # M8 ended later the same UTC day
COMPUTED = T0 - dt.timedelta(hours=1)      # the contributions were derived after both


def _g(a, b, room, ended, mid=None):
    return {"id": mid or str(uuid.uuid4()), "room": room, "p1": a, "p2": b, "ended": ended}


def _row(src, key, lo, hi, subject, match_id=None, utc_day=None, computed_at=COMPUTED, **cols):
    """A stored contribution row with its identity exactly as given (lo, hi
    are NOT reordered here) and its provenance columns."""
    row = {"stable_game_key": key, "pair_lo": lo, "pair_hi": hi, "subject_player_id": subject,
           "source": "self", "coverage": "one", "computed_at": computed_at,
           "utc_day": utc_day or T0.date()}
    row.update({c: 0 for c in ae._SECTION_SPEC[src]["contrib_cols"]})
    if src == "combat":
        row["sums"] = "{}"
    else:
        row["match_id"] = match_id
    row.update(cols)
    return row


def _seat(section, i):
    return section["seats"][i]["state"], _facts(section["seats"][i]["facts"])


def _reattached(src, a, b):
    """The B10-R2 scenario: A's record names r9, B's names r8; the worker
    attached (K, A, B) to M9 and stored the contributions derived from A's
    record (A's `self`, and A's `meas` of B), then B's record selected the
    earlier-scored M8 and a derivation fault kept those contributions while
    moving the games row to M8 (card_evidence.py:683-708,
    combat_evidence.py:379-413)."""
    m9, m8 = _g(a, b, "r9", ENDED9), _g(a, b, "r8", ENDED8)
    cols = {"hands": 5} if src == "card" else {"sums": '{"a1s": [1, 2, 3]}'}
    contrib = [_row(src, "K", a, b, a, match_id=m9["id"], **cols),
               _row(src, "K", a, b, b, source="meas", match_id=m9["id"], **cols)]
    data = _data(records=[_rec(src, "K", a, b, "r9"), _rec(src, "K", b, a, "r8")],
                 games=[_grow(src, "K", a, b, m8["id"])], contrib=contrib, switches=_on(src))
    return m9, m8, data


# ── R2-H1: provenance against the reported match ──────────────────────────

def test_r2h1_card_a_retained_contribution_stays_with_the_match_it_was_derived_for():
    a, b = _pair()
    m9, m8, data = _reattached("card", a, b)
    s8 = ae.game_section("card", data, m8, {a: 0, b: 1})
    for i in (0, 1):
        _state, f = _seat(s8, i)
        assert not any(k.startswith("contrib1.") for k in f), (i, f)
    w8 = _facts(ae.summary_section("card", data, [m8], a, 0)["facts"])
    assert "self.hands" not in w8 and "meas.hands" not in w8, w8
    w8b = _facts(ae.summary_section("card", data, [m8], b, 1)["facts"])
    assert "meas.hands" not in w8b, w8b
    # M9's report and window keep them: card_contrib.match_id is M9
    s9 = ae.game_section("card", data, m9, {a: 0, b: 1})
    _sa, fa = _seat(s9, 0)
    _sb, fb = _seat(s9, 1)
    assert (fa.get("contrib1.source"), fa.get("contrib1.hands")) == ("self", "5"), fa
    assert (fb.get("contrib1.source"), fb.get("contrib1.hands")) == ("meas", "5"), fb
    w9 = _facts(ae.summary_section("card", data, [m9], a, 0)["facts"])
    assert w9.get("self.hands") == "5", w9


def test_r2h1_card_a_contribution_without_its_match_is_not_the_games():
    a, b = _pair()
    g = _g(a, b, "r1", ENDED9)
    data = _data(records=[_rec("card", "K", a, b, "r1")], games=[_grow("card", "K", a, b, g["id"])],
                 contrib=[_row("card", "K", a, b, a, match_id=None, hands=4)], switches=_on("card"))
    _s, fa = _seat(ae.game_section("card", data, g, {a: 0, b: 1}), 0)
    assert "contrib1.hands" not in fa and fa.get("contrib") == "not_derived", fa
    assert "self.hands" not in _facts(ae.summary_section("card", data, [g], a, 0)["facts"])


def test_r2h1_combat_a_retained_contribution_is_unattributed_on_the_new_match():
    a, b = _pair()
    m9, m8, data = _reattached("combat", a, b)
    s8 = ae.game_section("combat", data, m8, {a: 0, b: 1})
    _sa, fa = _seat(s8, 0)
    _sb, fb = _seat(s8, 1)
    assert not any(k.startswith("contrib1.") for k in fa), fa
    assert not any(k.startswith("contrib1.") for k in fb), fb
    assert (fa.get("unattributed1.source"), fa.get("unattributed1.a1s.total")) == ("self", "6"), fa
    assert (fb.get("unattributed1.source"), fb.get("unattributed1.a1s.total")) == ("meas", "6"), fb
    w8 = _facts(ae.summary_section("combat", data, [m8], a, 0)["facts"])
    assert "self.a1s.total" not in w8 and w8.get("unattributed") == "1", w8
    assert w8.get("contrib") == "not_derived", w8
    # M9: the games row is another match's, so nothing of it is M9's here
    s9 = ae.game_section("combat", data, m9, {a: 0, b: 1})
    assert not any(k.startswith(("contrib1.", "unattributed1."))
                   for i in (0, 1) for k in _seat(s9, i)[1]), s9


def test_r2h1_combat_attributed_when_its_record_names_the_room_and_the_day_agrees():
    a, b = _pair()
    m9 = _g(a, b, "r9", ENDED9)
    good = _row("combat", "K", a, b, a, sums='{"a1s": [1, 2, 3]}')
    meas = _row("combat", "K", a, b, b, source="meas", sums='{"a1s": [4]}')
    recs = [_rec("combat", "K", a, b, "r9")]
    games = [_grow("combat", "K", a, b, m9["id"])]
    s = ae.game_section("combat", _data(records=recs, games=games, contrib=[good, meas]),
                        m9, {a: 0, b: 1})
    _sa, fa = _seat(s, 0)
    _sb, fb = _seat(s, 1)
    assert fa.get("contrib1.a1s.total") == "6" and "unattributed1.source" not in fa, fa
    assert fb.get("contrib1.a1s.total") == "4" and "unattributed1.source" not in fb, fb
    # each provenance condition on its own: a `self` row about B with no
    # record of B, a row of another UTC day, a row computed before the match
    # ended; each is unattributed and in no total
    other_day = T0.date() - dt.timedelta(days=1)
    for bad in (_row("combat", "K", a, b, b, sums='{"a1s": [9]}'),
                _row("combat", "K", a, b, a, utc_day=other_day, sums='{"a1s": [9]}'),
                _row("combat", "K", a, b, a, computed_at=ENDED9 - dt.timedelta(minutes=1),
                     sums='{"a1s": [9]}')):
        d = _data(records=recs, games=games, contrib=[bad])
        sub = 0 if bad["subject_player_id"] == a else 1
        _st, f = _seat(ae.game_section("combat", d, m9, {a: 0, b: 1}), sub)
        assert "contrib1.source" not in f and f.get("unattributed1.a1s.total") == "9", (bad, f)
        w = _facts(ae.summary_section("combat", d, [m9], bad["subject_player_id"], 0)["facts"])
        assert "self.a1s.total" not in w and w.get("unattributed") == "1", w


# ── R2-H2: stored identities compared exactly ─────────────────────────────

@pytest.mark.parametrize("src", ("card", "combat"))
def test_r2h2_a_reversed_stored_contribution_identity_is_not_the_games(src):
    a, b = _pair()                                   # a < b
    g = _g(a, b, "r1", ENDED9)
    five = {"hands": 5} if src == "card" else {"sums": '{"a1s": [5]}'}
    seven = {"hands": 7} if src == "card" else {"sums": '{"a1s": [7]}'}
    data = _data(records=[_rec(src, "K", a, b, "r1")], games=[_grow(src, "K", a, b, g["id"])],
                 contrib=[_row(src, "K", a, b, a, match_id=g["id"], **five),
                          _row(src, "K", b, a, a, match_id=g["id"], **seven)],
                 switches=_on(src))
    _s, fa = _seat(ae.game_section(src, data, g, {a: 0, b: 1}), 0)
    key = "contrib1.hands" if src == "card" else "contrib1.a1s.total"
    assert fa.get(key) == "5" and "contrib2.source" not in fa, fa
    assert "unattributed1.source" not in fa, fa
    w = _facts(ae.summary_section(src, data, [g], a, 0)["facts"])
    total = "self.hands" if src == "card" else "self.a1s.total"
    assert w.get(total) == "5", w


# ── The bot: the new word decodes, any other group word is refused ────────

@pytest.fixture(scope="module")
def bot():
    return bot_ns()


def test_bot_contribution_words_equal_the_api(bot):
    assert bot["AER_SECTION_CONTRIB_WORDS"] == ae.SECTION_CONTRIB_WORDS
    assert "unattributed" in ae.SECTION_CONTRIB_WORDS


def test_bot_decodes_an_unattributed_group_and_refuses_an_unknown_one(bot):
    a, b = _pair()
    body = _sections_for(game_body(), a, b)
    seat = body["games"][0]["sections"][0]["seats"][0]
    seat["facts"] += [["unattributed1.source", "self"], ["unattributed1.hands", "2"]]
    check_plan(bot, copy.deepcopy(body))           # every leaf exactly once in the plan
    page = bot["_aer_decode_response"](copy.deepcopy(body), "1a")
    text, files = bot["_aer_fallback"]("H", bot["_aer_plan"](page), "g", 1)
    shown = text if not files else files[0].data.decode("utf-8")
    assert "unattributed1.source=self" in shown and "unattributed1.hands=2" in shown, shown
    bad = copy.deepcopy(body)
    bad["games"][0]["sections"][0]["seats"][0]["facts"].append(["bogus1.source", "self"])
    assert bot["_aer_outcome"](200, bad) == (None, SCHEMA)


# ── R2-H1 through the routes, live PostgreSQL ─────────────────────────────

def test_r2h1_pg_the_reattachment_through_the_game_and_pair_routes(rig):
    """The R2-H1 scenario in the production tables, read by the production
    statements: the card select carries card_contrib.match_id and the combat
    select carries combat_contrib.utc_day, and M8's report and the pair
    window over M8 and M9 count the retained contributions for M9 only."""
    async def go():
        await sp._up(rig)
        admin = await sp._admin(rig)
        a, sa, _d = await rig.player()
        b, sb, _d = await rig.player()
        e9, e8 = sp.NOW - dt.timedelta(hours=3), sp.NOW - dt.timedelta(hours=2)
        m9 = await rig.match(a, b, e9, photon_room_id="r9", is_ranked=True)
        m8 = await rig.match(a, b, e8, photon_room_id="r8", is_ranked=True)
        for src in ("card", "combat"):
            await sp.rec(rig, src, "K", a, b, "r9")
            await sp.rec(rig, src, "K", b, a, "r8")
            await sp.grow(rig, src, "K", a, b, m8)
        await sp.contrib(rig, "card", "K", a, b, a, hands=5, match_id=m9)
        await sp.contrib(rig, "combat", "K", a, b, a, sums='{"a1s": [1, 2, 3]}',
                         utc_day=e9.date())
        await rig.commit()
        pages = {}
        for name, path in (("m8", "%s/game/%s" % (sp.ROOT, m8.hex)),
                           ("m9", "%s/game/%s" % (sp.ROOT, m9.hex)),
                           ("pair", "%s/pair?a=%s&b=%s&games=2" % (sp.ROOT, sa, sb))):
            st, c = await sp.get(rig, path, admin, sp.HEADER)
            pages[name] = (st, sp._body(c))
        return sa, pages

    sa, pages = rig.run(go())
    assert all(st == 200 for st, _b in pages.values()), {k: v[0] for k, v in pages.items()}

    def seat_a(body, src):
        s = sp._section(body, 0, src)
        return _facts(next(x for x in s["seats"]
                           if body["subjects"][x["subject"]]["steam_id"] == sa)["facts"])

    c8, k8 = seat_a(pages["m8"][1], "card"), seat_a(pages["m8"][1], "combat")
    assert "contrib1.hands" not in c8, c8
    assert "contrib1.source" not in k8 and k8.get("unattributed1.a1s.total") == "6", k8
    c9 = seat_a(pages["m9"][1], "card")
    assert c9.get("contrib1.hands") == "5", c9
    entries = {(e["oi"], e["src"]): e for e in pages["pair"][1]["sections_summary"]}
    wc, wk = _facts(entries[(0, "card")]["facts"]), _facts(entries[(0, "combat")]["facts"])
    assert wc.get("self.hands") == "5", wc
    assert "self.a1s.total" not in wk and wk.get("unattributed") == "1", wk
