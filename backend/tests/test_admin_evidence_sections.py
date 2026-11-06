"""Admin evidence report, phase 2 (ship-gate row B10): the evidence sections,
without a database.

The report also reads the card-draw, combat and identity-clock evidence tables
and shows their stored values under their stored names, uncolored. This file
covers the api's pure builders (`game_section`, `summary_section`, `_fact`,
`_sums_facts`), the bot's decoder, plan and fallback for the two new keys, the
equality of the api's and the bot's words, and the deploy order both ways:

  S1  every stored value lands at its seat, under its stored name; the game
      facts carry the attachment word, the three switches and the games row.
  S2  each unhandled case says so in words: no record, one seat only, waiting
      (not paired yet), another match's row, conflict, purged, no
      contribution (`not_derived`), a failed read (`unavailable`).
  S3  the summary counts and totals over the covered games, and the 30-day
      daily totals.
  S4  the bot decodes a page with sections and shows every leaf exactly once
      in its plan (the render test's bijection) and in the text fallback; it
      refuses each malformed section with `unavailable (schema)`.
  S5  deploy order: the new bot decodes a 1a page; the 1a bot of the base
      commit decodes the 1a page and refuses a page with sections (which is
      why the api adds them only on the bot's header); the new bot sends it.
"""

import ast
import asyncio
import copy
import datetime as dt
import os
import re
import subprocess
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import test_discord_evidence_bot as tbot  # noqa: E402
from test_discord_evidence_bot import ae, bot_ns, game_body, summary_body  # noqa: E402
from test_discord_evidence_render import check_plan  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
# The commit this lane was cut from: main with phase 1a live and no sections.
BASE = "1c77f580a29e33190f93cc27636c29e7dd8f2494"
SCHEMA = "Evidence report: unavailable (schema)."
T0 = dt.datetime(2026, 11, 1, 12, 0, tzinfo=dt.timezone.utc)


def _pair():
    a, b = sorted(str(uuid.uuid4()) for _ in range(2))
    return a, b


def _game(a, b, room="room-1", mid=None):
    return {"id": mid or str(uuid.uuid4()), "room": room, "p1": a, "p2": b}


def _rec(src, key, seat, other, room, **cols):
    row = {"stable_game_key": key, "attach_key": room, "seat_player_id": seat,
           "other_player_id": other, "conflict_at": None, "conflict_kind": None,
           "lists_purged_at": None}
    row.update({c: None for c in ae._SECTION_SPEC[src]["seat"]})
    row.update(cols)
    return row


def _grow(src, key, a, b, match_id, **cols):
    lo, hi = sorted((a, b))
    row = {"stable_game_key": key, "pair_lo": lo, "pair_hi": hi, "match_id": match_id}
    row.update({c: None for c in ae._SECTION_SPEC[src]["game"]})
    row.update(cols)
    return row


def _contrib(src, key, subject, **cols):
    row = {"stable_game_key": key, "subject_player_id": subject, "source": "self",
           "coverage": "one", "computed_at": T0}
    row.update({c: 0 for c in ae._SECTION_SPEC[src]["contrib_cols"]})
    if src == "combat":
        row["sums"] = "{}"
    row.update(cols)
    return row


def _data(records=(), games=(), contrib=(), switches=None, daily=None, truncated=False):
    return {"records": list(records), "games": list(games), "contrib": list(contrib),
            "switches": dict(switches or {}), "daily": dict(daily or {}),
            "truncated": truncated}


def _facts(facts):
    return dict(facts)


def _on(src):
    return {"%s_evidence_%s" % (src, w): "1" for w in ae.SECTION_SWITCHES}


# ── S1: the stored values, at their seats ─────────────────────────────────

def test_s1_card_values_land_at_their_seat_under_their_names():
    a, b = _pair()
    g = _game(a, b)
    data = _data(
        records=[_rec("card", "k1", a, b, "room-1", pool_state="ok", deal_profile="prof-a",
                      header_mod_version="1.41.0", received_at=T0),
                 _rec("card", "k1", b, a, "room-1", pool_state="collision",
                      deal_profile="prof-b")],
        games=[_grow("card", "k1", a, b, g["id"], series_sc="1-0", processed_at=T0,
                     derive_fault="ValueError", fault_attempts=2, parked_at=T0)],
        contrib=[_contrib("card", "k1", a, hands=5, slots=12, obs_rare=1, exp_rare=3,
                          deal_profile="prof-a")],
        switches=dict(_on("card"), card_evidence_accept="0"))
    s = ae.game_section("card", data, g, {a: 0, b: 1})
    assert (s["src"], s["state"], s["truncated"]) == ("card", "ok", False)
    gf = _facts(s["game"])
    assert gf["paired"] == "attached" and gf["accept"] == "0" and gf["worker"] == "1"
    assert gf["series_sc"] == "1-0" and gf["derive_fault"] == "ValueError"
    assert gf["fault_attempts"] == "2" and gf["parked_at"] == T0.isoformat()
    assert gf["processed_at"] == T0.isoformat() and gf["finalized_at"] is None
    (sa, fa), (sb, fb) = [(x["subject"], _facts(x["facts"])) for x in s["seats"]]
    assert (sa, sb) == (0, 1) and [x["state"] for x in s["seats"]] == ["ok", "ok"]
    assert fa["pool_state"] == "ok" and fa["deal_profile"] == "prof-a"
    assert fa["header_mod_version"] == "1.41.0" and fa["lists_purged"] == "no"
    assert fa["contrib1.hands"] == "5" and fa["contrib1.slots"] == "12"
    assert fa["contrib1.obs_rare"] == "1" and fa["contrib1.exp_rare"] == "3"
    assert fa["contrib1.source"] == "self" and fa["contrib1.deal_profile"] == "prof-a"
    assert fb["pool_state"] == "collision" and fb["contrib"] == "not_derived"
    assert "evaluated_rev" not in gf and "rules_rev" not in fa


def test_s1_combat_sums_show_bins_and_totals_by_stored_key():
    a, b = _pair()
    g = _game(a, b)
    data = _data(records=[_rec("combat", "k1", a, b, "room-1", consts_version=3)],
                 games=[_grow("combat", "k1", a, b, g["id"], coverage="one", records_n=1,
                              record_faults='{"derive": 1, "BAD KEY": 2}')],
                 contrib=[_contrib("combat", "k1", a, consts_version=3,
                                   sums='{"a1s": [1, 2, 3], "a1p": [], "x y": [1], '
                                        '"p3dp0": [1, "no"]}')],
                 switches=_on("combat"))
    s = ae.game_section("combat", data, g, {a: 0, b: 1})
    gf, fa = _facts(s["game"]), _facts(s["seats"][0]["facts"])
    assert gf["coverage"] == "one" and gf["records_n"] == "1"
    assert gf["record_faults"] == "derive"
    assert fa["consts_version"] == "3"
    assert (fa["contrib1.a1s.bins"], fa["contrib1.a1s.total"]) == ("3", "6")
    assert (fa["contrib1.a1p.bins"], fa["contrib1.a1p.total"]) == ("0", "0")
    assert fa["contrib1.unnamed"] == "2"
    assert s["seats"][1]["state"] == "no_record" and s["seats"][1]["facts"] == []


def test_s1_identity_clock_values_and_no_contribution_line():
    a, b = _pair()
    g = _game(a, b)
    data = _data(records=[_rec("identity_clock", "k1", b, a, "room-1", consts_version=1,
                               post_clock="ok", post_proc="abc", post_sw_ms=10,
                               post_unity_ms=11, post_photon_ts=12, conn_class="unknown",
                               conn_ranges="absent")],
                 games=[_grow("identity_clock", "k1", a, b, g["id"], records_n=1,
                              paired_points=0)],
                 switches=_on("identity_clock"))
    s = ae.game_section("identity_clock", data, g, {a: 0, b: 1})
    fb = _facts(s["seats"][1]["facts"])
    assert (fb["post_clock"], fb["post_proc"], fb["post_sw_ms"]) == ("ok", "abc", "10")
    assert (fb["conn_class"], fb["conn_ranges"]) == ("unknown", "absent")
    assert "contrib" not in fb
    assert _facts(s["game"])["paired_points"] == "0"


def test_s1_text_values_are_encoded_and_names_match_the_bot_pattern():
    a, b = _pair()
    g = _game(a, b)
    evil = "p" + chr(0x202E) + "x"
    data = _data(records=[_rec("card", "k1", a, b, "room-1", deal_profile=evil)],
                 games=[_grow("card", "k1", a, b, g["id"])])
    s = ae.game_section("card", data, g, {a: 0, b: 1})
    fa = _facts(s["seats"][0]["facts"])
    assert fa["deal_profile"] == ae._aer_enc(evil) and chr(0x202E) not in fa["deal_profile"]
    for name, _v in s["game"] + s["seats"][0]["facts"]:
        assert re.fullmatch(ae.FACT_NAME_PATTERN, name), name


def test_s1_the_section_encoder_agrees_with_the_display_encoder():
    """`_section_enc` is kept apart from `_aer_enc` only for the privacy
    pass; on every code point of the escaped set and its neighbours, and on
    the backslash, the two must write the same text."""
    points = set(range(0, 0x300)) | {0x5C}
    for cp in ae.AER_ESC:
        points |= {cp - 1, cp, cp + 1}
    points = sorted(p for p in points if 0 <= p <= 0x10FFFF and not 0xD800 <= p <= 0xDFFF)
    for cp in points:
        text = "a" + chr(cp) + chr(0x5C) + chr(cp)
        assert ae._section_enc(text) == ae._aer_enc(text), hex(cp)
    assert ae._section_enc("") == ae._aer_enc("") == ""


# ── S2: the unhandled cases, in words ─────────────────────────────────────

def test_s2_no_record_anywhere():
    a, b = _pair()
    s = ae.game_section("card", _data(switches=_on("card")), _game(a, b), {a: 0, b: 1})
    assert s["state"] == "no_record"
    assert [x["state"] for x in s["seats"]] == ["no_record", "no_record"]
    assert _facts(s["game"])["paired"] is None


def test_s2_waiting_records_under_the_room_before_the_worker_pairs():
    a, b = _pair()
    g = _game(a, b, room="room-w")
    data = _data(records=[_rec("card", "kw", a, b, "room-w")],
                 games=[_grow("card", "kw", a, b, None)])
    s = ae.game_section("card", data, g, {a: 0, b: 1})
    assert s["state"] == "ok" and _facts(s["game"])["paired"] == "waiting"


def test_s2_a_row_attached_to_another_match_is_not_this_games():
    a, b = _pair()
    g = _game(a, b, room="room-x")
    other = str(uuid.uuid4())
    data = _data(records=[_rec("combat", "kx", a, b, "room-x")],
                 games=[_grow("combat", "kx", a, b, other)])
    s = ae.game_section("combat", data, g, {a: 0, b: 1})
    gf = _facts(s["game"])
    assert s["state"] == "no_record" and gf["paired"] is None and gf["other_game"] == "1"


def test_s2_conflict_and_purged_are_seat_words_with_their_facts():
    a, b = _pair()
    g = _game(a, b)
    data = _data(records=[_rec("identity_clock", "k1", a, b, "room-1", conflict_at=T0,
                               conflict_kind="payload", post_clock="ok"),
                          _rec("identity_clock", "k1", b, a, "room-1", lists_purged_at=T0,
                               post_clock="absent")],
                 games=[_grow("identity_clock", "k1", a, b, g["id"])])
    s = ae.game_section("identity_clock", data, g, {a: 0, b: 1})
    assert [x["state"] for x in s["seats"]] == ["conflict", "purged"]
    fa, fb = _facts(s["seats"][0]["facts"]), _facts(s["seats"][1]["facts"])
    assert fa["conflict_kind"] == "payload" and fa["post_clock"] == "ok"
    assert fb["lists_purged"] == "yes" and fb["post_clock"] == "absent"


def test_s2_a_failed_read_is_unavailable_and_carries_nothing():
    a, b = _pair()
    s = ae.game_section("combat", None, _game(a, b), {a: 0, b: 1})
    assert s == {"src": "combat", "state": "unavailable", "truncated": False, "game": [],
                 "seats": []}
    t = ae.summary_section("combat", None, [_game(a, b)], a, 0)
    assert (t["state"], t["facts"], t["days30"]) == ("unavailable", [], [])


def test_s2_contribution_rows_beyond_the_cap_are_counted():
    a, b = _pair()
    g = _game(a, b)
    cap = ae.AER_CONTRACT_BOUNDS["SECTION_CONTRIB_MAX"]
    data = _data(records=[_rec("card", "k1", a, b, "room-1")],
                 games=[_grow("card", "k1", a, b, g["id"])],
                 contrib=[_contrib("card", "k1", a, hands=i, source="meas")
                          for i in range(cap + 2)])
    fa = _facts(ae.game_section("card", data, g, {a: 0, b: 1})["seats"][0]["facts"])
    assert ("contrib%d.hands" % cap) in fa and ("contrib%d.hands" % (cap + 1)) not in fa
    assert fa["contrib_more"] == "2"


# ── S3: the summary ───────────────────────────────────────────────────────

def test_s3_summary_counts_totals_and_days():
    a, b = _pair()
    g1, g2, g3 = (_game(a, b, room="r1"), _game(b, a, room="r2"), _game(a, b, room="r3"))
    data = _data(
        records=[_rec("card", "k1", a, b, "r1"), _rec("card", "k2", a, b, "r2",
                                                      conflict_kind="payload"),
                 _rec("card", "k3", b, a, "r3")],
        games=[_grow("card", "k1", a, b, g1["id"]), _grow("card", "k2", a, b, None)],
        contrib=[_contrib("card", "k1", a, hands=4, slots=10),
                 _contrib("card", "k2", a, hands=1, source="meas")],
        daily={a: [{"source": "self", "coverage": "one", "games": 2, "hands": 7,
                    **{c: 0 for c in ae._CARD_COUNTERS if c != "hands"}}]})
    s = ae.summary_section("card", data, [g1, g2, g3], a, 0)
    f, d = _facts(s["facts"]), _facts(s["days30"])
    assert (s["oi"], s["state"]) == (0, "ok")
    assert (f["games"], f["with_record"], f["attached"], f["waiting"]) == ("3", "2", "1", "2")
    assert (f["conflict"], f["purged"]) == ("1", "0")
    assert f["self.hands"] == "4" and f["self.slots"] == "10" and f["meas.hands"] == "1"
    assert d["self.games"] == "2" and d["self.hands"] == "7"
    empty = ae.summary_section("card", _data(), [g1], b, 1)
    assert _facts(empty["facts"])["contrib"] == "not_derived"
    assert _facts(empty["days30"])["daily"] == "not_derived" and empty["state"] == "no_record"


def test_s3_identity_clock_summary_counts_stored_words_and_has_no_days():
    a, b = _pair()
    g1, g2 = _game(a, b, room="r1"), _game(a, b, room="r2")
    data = _data(records=[_rec("identity_clock", "k1", a, b, "r1", post_clock="ok",
                               conn_class="unknown"),
                          _rec("identity_clock", "k2", a, b, "r2", post_clock="other_proc",
                               conn_class="BAD WORD")],
                 games=[_grow("identity_clock", "k1", a, b, g1["id"]),
                        _grow("identity_clock", "k2", a, b, g2["id"])])
    s = ae.summary_section("identity_clock", data, [g1, g2], a, 0)
    f = _facts(s["facts"])
    assert f["post_clock.ok"] == "1" and f["post_clock.other_proc"] == "1"
    assert f["conn_class.unknown"] == "1" and not any("BAD" in k for k in f)
    assert s["days30"] == [] and "contrib" not in f


def test_s3_the_daily_window_is_pop_days_utc_days_today_included():
    today = dt.datetime.now(dt.timezone.utc).date()
    day0 = ae._section_day0()
    assert (today - day0).days + 1 == ae.DISPLAY_DEFAULTS["pop_days"]


def test_s3_audit_counts_states_per_source():
    out = ae.section_audit([{"src": "card", "state": "ok"}, {"src": "card", "state": "ok"},
                            {"src": "combat", "state": "unavailable"}])
    assert out == {"card": {"ok": 2}, "combat": {"unavailable": 1}, "identity_clock": {}}


# ── S4: the bot ───────────────────────────────────────────────────────────

def _sections_for(body, a, b):
    """The game page of game_body() with every source's section built by the
    api's own builder (subjects 0 and 1 seated p1 and p2)."""
    g = _game(a, b)
    data = {
        "card": _data(records=[_rec("card", "k1", a, b, "room-1", pool_state="ok",
                                    received_at=T0)],
                      games=[_grow("card", "k1", a, b, g["id"], processed_at=T0)],
                      contrib=[_contrib("card", "k1", a, hands=3)], switches=_on("card")),
        "combat": None,
        "identity_clock": _data(records=[_rec("identity_clock", "k1", b, a, "room-1",
                                              post_clock="ok", conflict_kind="dup")],
                                games=[_grow("identity_clock", "k1", a, b, None)]),
    }
    body["games"][0]["sections"] = [ae.game_section(src, data[src], g, {a: 0, b: 1})
                                    for src in ae.SECTION_SOURCES]
    return body


def _summary_sections_for(body, a, b):
    g = _game(a, b)
    data = _data(records=[_rec("card", "k1", a, b, "room-1")],
                 games=[_grow("card", "k1", a, b, g["id"])],
                 daily={a: [{"source": "self", "coverage": "one", "games": 1,
                             **{c: 1 for c in ae._CARD_COUNTERS}}]})
    accounts = (a, b) if body["shape"] == "pair" else (a,)
    body["sections_summary"] = [
        ae.summary_section(src, data if src == "card" else None, [g], acc, oi)
        for oi, acc in enumerate(accounts) for src in ae.SECTION_SOURCES]
    return body


def test_s4_words_and_header_equal_the_api(bot):
    assert bot["AER_SECTIONS_HEADER"] == ae.SECTIONS_HEADER
    assert bot["AER_SECTIONS_PHASE"] == ae.SECTIONS_PHASE
    assert bot["AER_SECTION_SOURCES"] == ae.SECTION_SOURCES
    assert bot["AER_SECTION_STATES"] == ae.SECTION_STATES
    assert bot["AER_SECTION_SEAT_STATES"] == ae.SECTION_SEAT_STATES
    assert bot["AER_FACT_NAME_MAX"] == ae.AER_CONTRACT_BOUNDS["FACT_NAME_MAX"]
    assert bot["_AER_FACT_NAME"].pattern == ae.FACT_NAME_PATTERN


@pytest.fixture(scope="module")
def bot():
    return bot_ns()


def test_s4_plan_shows_every_section_leaf_once(bot):
    a, b = _pair()
    body = _sections_for(game_body(), a, b)
    page, plan = check_plan(bot, body)
    assert [s["state"] for s in page.games[0]["sections"]] == ["ok", "unavailable", "ok"]
    kinds = [i.kind for i in plan]
    assert kinds.count("section") == 3 and "facts" in kinds
    per_line = bot["AER_FACTS_PER_LINE"]
    assert all(len(i.fields) <= 2 * per_line for i in plan if i.kind == "facts")
    assert any(len(i.fields) == 2 * per_line for i in plan if i.kind == "facts")
    for shape in ("pair", "player"):
        sbody = _summary_sections_for(summary_body(shape=shape), a, b)
        spage, splan = check_plan(bot, sbody)
        assert len(spage.sections) == len(sbody["sections_summary"])
        assert [i.kind for i in splan].count("section") == len(sbody["sections_summary"])


def test_s4_fallback_text_carries_the_facts(bot):
    a, b = _pair()
    body = _sections_for(game_body(), a, b)
    page = bot["_aer_decode_response"](copy.deepcopy(body), "1a")
    plan = bot["_aer_plan"](page)
    text, files = bot["_aer_fallback"]("H", plan, "g", 1)
    shown = text if not files else files[0].data.decode("utf-8")
    assert "pool_state=ok" in shown and "contrib1.hands=3" in shown
    assert "conflict_kind=dup" in shown and "paired=waiting" in shown


def _section_breaks():
    def first(b):
        return b["games"][0]["sections"][0]
    return [
        ("unknown section key", lambda b: first(b).update(extra=1)),
        ("source order", lambda b: b["games"][0]["sections"].reverse()),
        ("missing source", lambda b: b["games"][0]["sections"].pop()),
        ("unknown state", lambda b: first(b).update(state="armed")),
        ("truncated not bool", lambda b: first(b).update(truncated="no")),
        ("bad fact name", lambda b: first(b)["game"].append(["Bad Name", "x"])),
        ("numeric fact value", lambda b: first(b)["game"].append(["n", 3])),
        ("fact not a pair", lambda b: first(b)["game"].append(["n"])),
        ("escaped code point", lambda b: first(b)["game"].append(["n", chr(0x202E)])),
        ("seat order", lambda b: first(b)["seats"].reverse()),
        ("seat state", lambda b: first(b)["seats"][0].update(state="c3")),
        ("seat extra key", lambda b: first(b)["seats"][0].update(cls="c1")),
        ("unavailable with facts", lambda b: b["games"][0]["sections"][1]["game"].append(
            ["n", "x"])),
        ("sections_summary on a game page", lambda b: b.update(sections_summary=[])),
    ]


@pytest.mark.parametrize("label,mutate", _section_breaks(), ids=[x[0] for x in _section_breaks()])
def test_s4_each_malformed_section_is_refused(bot, label, mutate):
    a, b = _pair()
    body = _sections_for(game_body(), a, b)
    assert bot["_aer_outcome"](200, copy.deepcopy(body))[1] is None
    mutate(body)
    assert bot["_aer_outcome"](200, body) == (None, SCHEMA), label


def test_s4_each_malformed_summary_section_is_refused(bot):
    a, b = _pair()
    good = _summary_sections_for(summary_body(shape="pair"), a, b)
    assert bot["_aer_outcome"](200, copy.deepcopy(good))[1] is None
    for mutate in (lambda s: s.pop(),
                   lambda s: s[0].update(oi=1),
                   lambda s: s[0].update(src="combat"),
                   lambda s: s[1].update(days30=[["n", "x"]]),
                   lambda s: s[0]["facts"].append(["n", 1])):
        body = copy.deepcopy(good)
        mutate(body["sections_summary"])
        assert bot["_aer_outcome"](200, body) == (None, SCHEMA)


# ── S5: the deploy order, both ways ───────────────────────────────────────

def old_bot_ns():
    """The base commit's bot evidence code (phase 1a, no sections), lifted as
    test_discord_evidence_bot lifts the current one."""
    out = subprocess.run(["git", "-C", REPO, "show", BASE + ":backend/discord_bot.py"],
                         capture_output=True, timeout=60)
    if out.returncode:
        pytest.fail("the base bot source is not readable here: %s"
                    % out.stderr.decode("utf-8", "replace")[:200])
    tree = ast.parse(out.stdout.decode("utf-8"))
    picked = []
    for node in tree.body:
        if tbot._wanted(node):
            node = copy.deepcopy(node)
            if not isinstance(node, ast.ClassDef):
                node.decorator_list = []
            picked.append(node)
    assert "AER_SECTIONS_HEADER" not in {t.id for n in picked if isinstance(n, ast.Assign)
                                         for t in n.targets if isinstance(t, ast.Name)}
    ns = {k: v for k, v in bot_ns().items()
          if not k.startswith(("_aer_", "AER_", "_AER_")) and k not in (
              "BotPage", "AerItem", "AerSchemaError")}
    exec(compile(ast.Module(body=picked, type_ignores=[]), "old_discord_bot.py", "exec"), ns)
    return ns


def test_s5_the_new_bot_decodes_a_1a_page(bot):
    for body in (game_body(), summary_body(), summary_body(shape="pair")):
        page, word = bot["_aer_outcome"](200, copy.deepcopy(body))
        assert word is None and page.sections == ()
        assert all(g["sections"] == () for g in page.games)


def test_s5_the_base_bot_decodes_a_1a_page_and_refuses_sections():
    old = old_bot_ns()
    a, b = _pair()
    for body in (game_body(), summary_body(shape="pair")):
        page, word = old["_aer_outcome"](200, copy.deepcopy(body))
        assert word is None and page is not None
    assert old["_aer_outcome"](200, _sections_for(game_body(), a, b)) == (None, SCHEMA)
    assert old["_aer_outcome"](200, _summary_sections_for(summary_body(shape="pair"), a, b)
                               ) == (None, SCHEMA)


def test_s5_the_new_bot_asks_for_sections_by_header():
    calls = []

    class _Resp:
        status = 200
        headers = {}

        async def read(self):
            return b"{}"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _Session:
        def get(self, url, headers=None, timeout=None):
            calls.append(dict(headers or {}))
            return _Resp()

    ns = bot_ns(api=_Session())
    asyncio.run(ns["_aer_fetch"]("/x", 42))
    assert calls[0][ae.SECTIONS_HEADER] == ae.SECTIONS_PHASE
    assert calls[0]["X-Actor-Discord-Id"] == "42"


def test_s1_section_reads_use_their_own_reader():
    """The section reads go through `_section_rows` only, never the shared
    `_aer_rows` (whose analysed summary the 1a display slots read)."""
    with open(ae.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    funcs = {f.name: f for f in tree.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    called = {n.func.id for n in ast.walk(funcs["_section_read"])
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_section_rows" in called and "_aer_rows" not in called, called
    for name in ("read_sections", "_page_sections", "game_section", "summary_section"):
        names = {n.id for n in ast.walk(funcs[name]) if isinstance(n, ast.Name)}
        assert "_aer_rows" not in names, name


def test_s1_the_fact_key_test_is_the_stored_key_pattern():
    """`_fact_key` admits exactly `[a-z0-9_]{1,24}`."""
    samples = ["", "a", "a_1", "A", "a.b", "a-b", "x" * 24, "x" * 25, "é", "a b",
               "z9_", "_", "9", None, 7, "a" + chr(0x202E)]
    samples += [chr(c) for c in range(0, 0x180)]
    for w in samples:
        want = isinstance(w, str) and re.fullmatch(r"[a-z0-9_]{1,24}", w) is not None
        assert ae._fact_key(w) == want, repr(w)
