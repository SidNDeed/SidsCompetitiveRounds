"""Admin evidence report, phase 3 (ship-gate row B10, ruling R5): stored
findings (3a) and the evidence ranks of families K and X (3b), without a
database.

  F1  a section lists the game's stored findings as stored (rule_id, scope,
      computed_at, flag id): a finding is the game's when its dedup key names
      the game's pair and its stored match_id is the game's; one under the
      game's identity for another or no match is counted, not listed; one of
      another pair is neither; past FINDINGS_MAX the rest is counted; an
      unavailable section lists none. The summary counts them per window.
  F2  the findings namespaces equal the three workers' key builders, and the
      lookup keys are every identity the source's rows name.
  K1  the evidence registry is the expansion of its declarations: exactly two
      window keys and one daily key per base key; the census and P21-style
      problems come from the registry; the vocabulary equals card_measures'
      and combat_measures' own.
  K2  the population arithmetic: per unit newest values, depth and value caps
      with the crossing unit dropped whole, mid-ranks with ties, strata never
      pooled, a reversed stored pair is no fact, a repeated fact refuses.
  K3  a window subject's cells: both window keys over the covered games'
      attributed contributions, the daily key over the summed daily rows,
      each ranked in its own distribution.
  B1  the bot decodes a phase-3 page and shows every leaf once (the render
      test's bijection), in the fallback too; it refuses each malformed
      variant; its words equal the api's; it sends both headers.
  B2  deploy order: the phase-2 bot (main at the lane's base) decodes a
      phase-2 page and refuses a phase-3 page, which is why the api adds
      phase 3 only on the second header; the new bot decodes a phase-2 page.

Rule ids are synthetic (`zz-...`); no threshold, weight or rule text.
"""

import ast
import asyncio
import copy
import datetime as dt
import os
import subprocess
import sys
import uuid
from array import array

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import test_discord_evidence_bot as tbot  # noqa: E402
from test_discord_evidence_bot import ae, bot_ns, game_body, summary_body  # noqa: E402
from test_discord_evidence_render import check_plan  # noqa: E402
from test_admin_evidence_sections import (REPO, _contrib, _data, _game, _grow,  # noqa: E402
                                          _pair, _rec)

# main at the lane's base: phase 2 live, no phase 3.
P2_BASE = "28778d95c6408e5581aafd0598ee962b121f5fcf"
SCHEMA = "Evidence report: unavailable (schema)."
T0 = dt.datetime(2026, 11, 1, 12, 0, tzinfo=dt.timezone.utc)


def _finding(src, key, a, b, match_id, rule_id="zz-r1", flag_id=None, at=T0, scope="game"):
    lo, hi = sorted((a, b))
    return {"dedup_key": "%s%s|%s|%s" % (ae.FINDING_PREFIX[src], key, lo, hi),
            "rule_id": rule_id, "scope": scope, "computed_at": at, "flag_id": flag_id,
            "match_id": match_id}


def _with_findings(data, findings):
    data["findings"] = list(findings)
    return data


def _p3_section(src, data, g, index):
    return ae.phase3_game_section(ae.game_section(src, data, g, index), src, data, g)


# ── F1 / F2: stored findings ──────────────────────────────────────────────

@pytest.mark.parametrize("src", ae.SECTION_SOURCES)
def test_f1_findings_are_listed_as_stored_and_attributed_by_stored_match(src):
    a, b = _pair()
    g = _game(a, b)
    other = str(uuid.uuid4())
    flag = uuid.uuid4()
    c, d = _pair()
    data = _with_findings(
        _data(records=[_rec(src, "k1", a, b, "room-1")],
              games=[_grow(src, "k1", a, b, g["id"])]),
        [_finding(src, "k1", a, b, g["id"], "zz-r2", flag_id=flag),
         _finding(src, "k1", a, b, g["id"], "zz-r1"),
         _finding(src, "k1", a, b, other, "zz-r3"),          # same identity, another match
         _finding(src, "k1", a, b, None, "zz-r4"),           # same identity, no match
         _finding(src, "k1", c, d, g["id"], "zz-r5"),        # another pair
         _finding("card" if src != "card" else "combat", "k1", a, b, g["id"], "zz-r6")])
    sec = _p3_section(src, data, g, {a: 0, b: 1})
    assert sec["findings"] == [["zz-r1", "game", T0.isoformat(), None],
                               ["zz-r2", "game", T0.isoformat(), str(flag)]]
    facts = dict(sec["game"])
    assert facts["findings"] == "2" and facts["findings_unattributed"] == "2"
    assert "findings_more" not in facts


def test_f1_a_finding_whose_games_row_moved_is_still_its_match_s():
    a, b = _pair()
    g8, g9 = _game(a, b), _game(a, b)
    data = _with_findings(
        _data(records=[_rec("card", "k1", a, b, "room-1")],
              games=[_grow("card", "k1", a, b, g8["id"])]),
        [_finding("card", "k1", a, b, g9["id"])])
    assert _p3_section("card", data, g9, {a: 0, b: 1})["findings"][0][0] == "zz-r1"
    sec8 = _p3_section("card", data, g8, {a: 0, b: 1})
    assert sec8["findings"] == [] and dict(sec8["game"])["findings_unattributed"] == "1"


def test_f1_findings_past_the_cap_are_counted_and_an_unavailable_section_lists_none():
    a, b = _pair()
    g = _game(a, b)
    cap = ae.AER_CONTRACT_BOUNDS["FINDINGS_MAX"]
    data = _with_findings(_data(records=[_rec("combat", "k1", a, b, "room-1")],
                                games=[_grow("combat", "k1", a, b, g["id"])]),
                          [_finding("combat", "k1", a, b, g["id"], "zz-%02d" % i)
                           for i in range(cap + 3)])
    sec = _p3_section("combat", data, g, {a: 0, b: 1})
    assert len(sec["findings"]) == cap and sec["findings"][0][0] == "zz-00"
    assert dict(sec["game"])["findings"] == str(cap + 3)
    assert dict(sec["game"])["findings_more"] == "3"
    gone = _p3_section("combat", None, g, {a: 0, b: 1})
    assert gone["findings"] == [] and gone["state"] == "unavailable" and gone["game"] == []


def test_f1_no_finding_says_zero_and_phase_2_is_unchanged():
    a, b = _pair()
    g = _game(a, b)
    data = _with_findings(_data(records=[_rec("card", "k1", a, b, "room-1")]), [])
    plain = ae.game_section("card", copy.deepcopy(data), g, {a: 0, b: 1})
    sec = _p3_section("card", data, g, {a: 0, b: 1})
    assert sec["findings"] == [] and sec["game"] == plain["game"] + [["findings", "0"]]
    assert {k: v for k, v in sec.items() if k not in ("findings", "game")} == {
        k: v for k, v in plain.items() if k != "game"}


def test_f1_the_summary_counts_findings_over_the_covered_games():
    a, b = _pair()
    g1, g2 = _game(a, b, room="room-1"), _game(a, b, room="room-2")
    data = _with_findings(
        _data(records=[_rec("card", "k1", a, b, "room-1"), _rec("card", "k2", a, b, "room-2")],
              games=[_grow("card", "k1", a, b, g1["id"]), _grow("card", "k2", a, b, g2["id"])]),
        [_finding("card", "k1", a, b, g1["id"], "zz-r1"),
         _finding("card", "k2", a, b, g2["id"], "zz-r1"),
         _finding("card", "k2", a, b, None, "zz-r2")])
    sec = ae.phase3_summary_section(ae.summary_section("card", data, [g1, g2], a, 0), "card",
                                    data, [g1, g2])
    facts = dict(sec["facts"])
    assert facts["findings"] == "2" and facts["findings_unattributed"] == "1"


def test_f2_namespaces_equal_the_workers_key_builders():
    import card_evidence
    import combat_evidence
    import identity_clock_evidence
    a, b = _pair()
    assert card_evidence.game_key("k", a, b) == ae.FINDING_PREFIX["card"] + "k|%s|%s" % (a, b)
    assert combat_evidence.dedup_key("k", a, b) == (
        ae.FINDING_PREFIX["combat"] + "k|%s|%s" % (a, b))
    assert identity_clock_evidence.ice_dedup_key("k", a, b) == (
        ae.FINDING_PREFIX["identity_clock"] + "k|%s|%s" % (a, b))
    assert ae._finding_ident("card", card_evidence.game_key("k", a, b)) == ("k", a, b)
    assert ae._finding_ident("card", card_evidence.window_key(a, "self", "one", "p", "d")) != (
        "k", a, b)
    assert ae._finding_ident("combat", card_evidence.game_key("k", a, b)) is None


def test_f2_the_lookup_keys_are_every_identity_the_rows_name():
    a, b = _pair()
    data = _data(records=[_rec("card", "k1", b, a, "room-1")],
                 games=[_grow("card", "k2", a, b, None)],
                 contrib=[_contrib("card", "k3", a, b, a)])
    lo, hi = sorted((a, b))
    assert ae._finding_keys("card", data) == ["card k%d|%s|%s" % (i, lo, hi) for i in (1, 2, 3)]
    assert "LATERAL" not in ae.FINDINGS_SQL and "CAST(:keys AS varchar[])" in ae.FINDINGS_SQL
    assert "LIMIT CAST(:n AS integer)" in ae.FINDINGS_SQL
    assert "details" not in ae.FINDINGS_SQL and "rules_rev" not in ae.FINDINGS_SQL


# ── K1: the registry ──────────────────────────────────────────────────────

def test_k1_the_registry_is_its_expansion_and_its_census():
    reg = ae.EV_REGISTRY
    assert ae.ev_registry_problems(reg) == []
    base = [e for e in reg if not e.is_window and e.agg == "cell"]
    assert len(base) == 2 * 2 * len(ae.EV_CARD_VARS) + 2 * sum(
        len(s) for _src, s in ae.EV_COMBAT_SETS)
    assert ae.ev_census() == {"K": [60, 120, 60], "X": [16, 32, 16]}
    assert all(e.ranked and e.scope == "seat" and e.kind == "R" for e in reg)
    assert len({e.key for e in reg}) == len(reg)
    assert {e.key for e in reg}.isdisjoint({e.key for e in ae.REPORT_REGISTRY})
    dropped = tuple(e for e in reg if e.agg != "win_max.cell" or e.base != 0)
    assert any("window aggregations" in p for p in ae.ev_registry_problems(dropped))
    no_daily = tuple(e for e in reg if not (e.agg == "window" and e.var == base[0].var
                                            and e.prov == base[0].prov
                                            and e.coverage == base[0].coverage))
    assert any("daily keys" in p for p in ae.ev_registry_problems(no_daily))
    assert ae.ev_fingerprint() != ae.registry_fingerprint()


def test_k1_the_vocabulary_is_the_measures_modules_own():
    import card_measures as cm
    import combat_measures as xm
    assert ae.EV_RARITIES == tuple(cm.RARITIES)
    assert ae.AER_CONTRACT_BOUNDS["CARD_FIXED_POINT"] == cm.W["fixed_point"]
    agg = {"games": 1, "hands": 1, "slots": 1, "notrun_hands": 1, "source": "self",
           "coverage": "one", "obs": [1, 1, 1], "exp": [1, 1, 1], "var": [1, 1, 1]}
    names = {k for k in cm.window_row(agg)} - {"b4.rar.games", "b4.rar.meas", "b4.rar.paired"}
    assert names == {v for v, _u in ae.EV_CARD_VARS}
    rec = {"rec": {"consts": 1, **{k: [0] for _s, sets in ae.EV_COMBAT_SETS for k in sets}},
           "seat": "a", "other": "b"}
    got = {(c["source"], tuple(sorted(c["sums"]))) for c in xm.contributions([rec])}
    assert got == {(s, tuple(sorted(sets))) for s, sets in ae.EV_COMBAT_SETS}


def test_k1_card_values_are_window_row_s_measures_of_one_row():
    import card_measures as cm
    fix = cm.W["fixed_point"]
    row = {"source": "meas", "coverage": "paired", "deal_profile": "p1", "hands": 4,
           "slots": 9, "notrun_hands": 1, "obs_common": 5, "exp_common": 3 * fix,
           "var_common": 4 * fix, "obs_uncommon": 1, "exp_uncommon": fix, "var_uncommon": 0,
           "obs_rare": 0, "exp_rare": 0, "var_rare": 0}
    want = cm.window_row({"games": 1, "hands": 4, "slots": 9, "notrun_hands": 1,
                          "source": "meas", "coverage": "paired", "obs": [5, 1, 0],
                          "exp": [3 * fix, fix, 0], "var": [4 * fix, 0, 0]})
    facts = {ae.EV_REGISTRY[ki].var: v for ki, _s, v in ae.ev_row_facts("card", row)}
    for var, value in facts.items():
        assert value == pytest.approx(want[var]), var
    assert facts["b4.rar.dev.common"] == pytest.approx(1.0)
    assert "b4.rar.dev.uncommon" not in facts            # var 0: unknown, never a 0
    assert {ae.EV_REGISTRY[ki].prov for ki, _s, _v in ae.ev_row_facts("card", row)} == {"MEAS"}
    assert ae.ev_row_facts("card", dict(row, source="other")) == []
    assert ae.ev_row_facts("card", dict(row, coverage="half")) == []


def test_k1_combat_values_are_each_admitted_set_s_total():
    row = {"source": "self", "coverage": "one", "consts_version": 3,
           "sums": '{"a1s": [1, 2, 3], "a1p": [true], "a1m": [9], "zz": [5]}'}
    facts = {(ae.EV_REGISTRY[ki].var, s): v for ki, s, v in ae.ev_row_facts("combat", row)}
    assert facts == {("a1s.total", "3"): 6.0}


# ── K2: the population arithmetic ─────────────────────────────────────────

def _prow(src, mid, ended, a, b, subject, **cols):
    lo, hi = sorted((a, b))
    row = {"match_id": mid, "ended_at": ended, "player1_id": a, "player2_id": b,
           "pair_lo": lo, "pair_hi": hi, "subject_player_id": subject, "source": "self",
           "coverage": "one"}
    if src == "card":
        row.update({c: 0 for c in ae._CARD_COUNTERS}, deal_profile="p1")
    else:
        row.update(consts_version=3, sums="{}")
    row.update(cols)
    return row


def _hands_ki(prov="SELF", cov="one"):
    return ae.EV_BASE_KI[("card_record", "b4.rar.hands", prov, cov)]


def test_k2_units_take_their_newest_values_and_ranks_are_mid_ranks():
    accounts = [str(uuid.uuid4()) for _ in range(5)]
    rows = []
    for i, acc in enumerate(accounts):
        opp = str(uuid.uuid4())
        for j in range(3):
            rows.append(_prow("card", str(uuid.uuid4()), T0 - dt.timedelta(hours=10 * i + j),
                              acc, opp, acc, hands=10 * i + j))
    pops, cut = ae.ev_population("card", rows)
    assert cut == set()
    values, offsets = pops[(_hands_ki(), "p1", "player")]
    assert list(offsets) == [0, 3, 6, 9, 12, 15]
    assert list(values[:3]) == [0.0, 1.0, 2.0]       # unit 0, newest first
    dist = ae.window_population(values, offsets, "win_max", 2)
    assert list(dist) == [1.0, 11.0, 21.0, 31.0, 41.0]
    assert ae.pop_measures(dist, 21.0)["pop_rank"] == pytest.approx(0.5)
    assert ae.pop_measures(dist, 11.0)["pop_rank"] == pytest.approx(0.3)
    assert ae.mid_rank(5.0, array("d", [5.0] * 4)) == pytest.approx(0.5)
    # basis pair: one unit per directional (account, opponent)
    assert len(pops[(_hands_ki(), "p1", "pair")][1]) == 6


def test_k2_depth_and_value_caps_drop_the_crossing_unit_whole(monkeypatch):
    monkeypatch.setitem(ae.AER_CONTRACT_BOUNDS, "WIN_UNIT_DEPTH", 2)
    monkeypatch.setitem(ae.AER_CONTRACT_BOUNDS, "WIN_VALUES_MAX", 5)
    rows = []
    for i in range(4):
        acc, opp = str(uuid.uuid4()), str(uuid.uuid4())
        for j in range(3):
            rows.append(_prow("card", str(uuid.uuid4()), T0 - dt.timedelta(hours=10 * i + j),
                              acc, opp, acc, hands=j))
    pops, cut = ae.ev_population("card", rows)
    values, offsets = pops[(_hands_ki(), "p1", "player")]
    assert list(offsets) == [0, 2, 4]                 # depth 2; the third unit crosses 5
    assert (_hands_ki(), "p1", "player") in cut


def test_k2_strata_never_pool_and_a_reversed_stored_pair_is_no_fact():
    a, b = _pair()
    rows = [_prow("card", "m1", T0, a, b, a, hands=1, deal_profile="p1"),
            _prow("card", "m2", T0, a, b, a, hands=2, deal_profile="p2"),
            dict(_prow("card", "m3", T0, a, b, a, hands=3), pair_lo=b, pair_hi=a)]
    pops, _cut = ae.ev_population("card", rows)
    assert list(pops[(_hands_ki(), "p1", "player")][0]) == [1.0]
    assert list(pops[(_hands_ki(), "p2", "player")][0]) == [2.0]


def test_k2_a_repeated_fact_refuses():
    a, b = _pair()
    row = _prow("combat", "m1", T0, a, b, a, sums='{"a1s": [1]}')
    with pytest.raises(ae.EvidenceDuplicate):
        ae.ev_population("combat", [row, dict(row)])


def test_k2_the_daily_population_sums_each_subject_s_days():
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    day = {"source": "self", "coverage": "one", "deal_profile": "p1", "games": 1,
           **{c: 0 for c in ae._CARD_COUNTERS}}
    rows = [dict(day, subject_player_id=a, hands=2), dict(day, subject_player_id=a, hands=3),
            dict(day, subject_player_id=b, hands=4)]
    pops = ae.ev_daily_population("card", rows)
    assert list(pops[(ae.EV_DAILY_KI[_hands_ki()], "p1")]) == [4.0, 5.0]


# ── K3: a window subject's cells ──────────────────────────────────────────

def test_k3_window_cells_aggregate_attributed_contributions_and_rank_them():
    a, b = _pair()
    games = [_game(a, b, room="room-%d" % i) for i in range(3)]
    contrib = [_contrib("card", "k%d" % i, a, b, a, match_id=g["id"], hands=h,
                        deal_profile="p1", **{c: 0 for c in ae._CARD_COUNTERS if c != "hands"})
               for i, (g, h) in enumerate(zip(games, (4, 1, 7)))]
    contrib.append(_contrib("card", "k9", a, b, a, match_id=str(uuid.uuid4()), hands=99,
                            deal_profile="p1"))         # another match's: not in the window
    data = _data(contrib=contrib, daily={a: [
        {"source": "self", "coverage": "one", "deal_profile": "p1", "games": 2,
         **dict({c: 0 for c in ae._CARD_COUNTERS}, hands=6)}]})
    pops = {(_hands_ki(), "p1", "player"): (array("d", [1, 2, 3, 9, 9, 9]),
                                            array("i", [0, 3, 6]))}
    daily = {(ae.EV_DAILY_KI[_hands_ki()], "p1"): array("d", [1.0, 6.0, 8.0])}
    cells = ae.ev_window_cells("card", data, games, a, "player", pops, daily)
    hands = [c for c in cells if ae.EV_REGISTRY[c["ki"]].var == "b4.rar.hands"]
    by_agg = {ae.EV_REGISTRY[c["ki"]].agg: c for c in hands}
    assert by_agg["win_median.cell"]["val"] == 4.0 and by_agg["win_median.cell"]["n"] == 3
    assert by_agg["win_max.cell"]["val"] == 7.0
    assert by_agg["win_max.cell"]["pop_n"] == 2 and by_agg["win_max.cell"]["pop_p50"] == 3.0
    assert by_agg["win_max.cell"]["pop_rank"] == pytest.approx(0.5)
    assert by_agg["window"]["val"] == 6.0 and by_agg["window"]["n"] == 2
    assert by_agg["window"]["pop_rank"] == pytest.approx(0.5)
    assert by_agg["window"]["basis"] == "player"
    assert ae.ev_window_cells("card", data, games, b, "player", pops, daily) == []


def test_k3_two_facts_for_one_key_in_one_game_refuse():
    a, b = _pair()
    g = _game(a, b)
    data = _data(contrib=[_contrib("card", "k1", a, b, a, match_id=g["id"], hands=1,
                                   deal_profile="p1"),
                          _contrib("card", "k2", a, b, a, match_id=g["id"], hands=2,
                                   deal_profile="p1")])
    with pytest.raises(ae.EvidenceDuplicate):
        ae.ev_window_cells("card", data, [g], a, "player", {}, {})


def test_k3_the_statements_are_typed_bounded_and_lateral_free():
    for src in ae.EV_SOURCES:
        for sql in (ae.EV_POP_SQL[src], ae.EV_DAILY_SQL[src]):
            assert "LATERAL" not in sql and "LIMIT CAST(:n AS integer)" in sql
        assert "c.match_id = g.id" in ae.EV_POP_SQL[src]
        assert "CAST(:pop_days AS integer)" in ae.EV_POP_SQL[src]
        assert "CAST(:subjects AS uuid[])" in ae.EV_DAILY_SQL[src]


# ── B1 / B2: the bot ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def bot():
    return bot_ns()


def _p3_game_body(a, b):
    body = game_body()
    g = _game(a, b)
    flag = uuid.uuid4()
    data = {
        "card": _with_findings(
            _data(records=[_rec("card", "k1", a, b, "room-1", pool_state="ok")],
                  games=[_grow("card", "k1", a, b, g["id"])]),
            [_finding("card", "k1", a, b, g["id"], "zz-r1", flag_id=flag),
             _finding("card", "k1", a, b, None, "zz-r2")]),
        "combat": None,
        "identity_clock": _with_findings(
            _data(records=[_rec("identity_clock", "k1", b, a, "room-1", post_clock="ok")]),
            [_finding("identity_clock", "k1", a, b, g["id"], "zz-r9")]),
    }
    body["games"][0]["sections"] = [_p3_section(src, data[src], g, {a: 0, b: 1})
                                    for src in ae.SECTION_SOURCES]
    return body


def _evidence(shape, cells=True):
    nwin = 1 if shape == "player" else 2
    w = next(e for e in ae.EV_REGISTRY if e.agg == "win_median.cell")
    d = next(e for e in ae.EV_REGISTRY if e.agg == "window")
    ev = {"state": "ok", "rows": 7, "truncated": False, "fingerprint": ae.ev_fingerprint(),
          "census": ae.ev_census(),
          "catalog": [{"ki": e.ki, "key": e.key, "unit": e.unit} for e in (w, d)],
          "strata": ["p1", "3"],
          "windows": [{"oi": oi, "cells": [[w.ki, 0, "player", 3, 4.0, 0.5, 6, 3.0, 9.0, 9.0],
                                           [d.ki, 1, "player", 2, 6.0, None, 0, None, None,
                                            None]] if cells else [], "more": 0}
                      for oi in range(nwin)]}
    if not cells:
        ev.update(state="not_derived", catalog=[], strata=[], rows=0)
    return ev


def _p3_summary_body(shape, cells=True):
    body = summary_body(shape=shape)
    a, b = _pair()
    g = _game(a, b)
    data = _with_findings(_data(records=[_rec("card", "k1", a, b, "room-1")],
                                games=[_grow("card", "k1", a, b, g["id"])]),
                          [_finding("card", "k1", a, b, g["id"])])
    accounts = (a, b) if shape == "pair" else (a,)
    body["sections_summary"] = [
        ae.phase3_summary_section(ae.summary_section(src, data if src == "card" else None,
                                                     [g], acc, oi), src,
                                  data if src == "card" else None, [g])
        for oi, acc in enumerate(accounts) for src in ae.SECTION_SOURCES]
    body["evidence"] = _evidence(shape, cells)
    return body


def test_b1_words_and_headers_equal_the_api(bot):
    assert bot["AER_PHASE3_HEADER"] == ae.PHASE3_HEADER
    assert bot["AER_PHASE3_VALUE"] == ae.PHASE3_VALUE
    assert bot["AER_EV_STATES"] == ae.EV_STATES
    assert bot["AER_EV_CELL_SLOTS"] == ae.EV_CELL_SLOTS
    assert set(bot["AER_EV_SOURCES"]) == {s for x in ae.EV_SPEC.values()
                                          for s in (x["rec"], x["daily"])}
    assert set(bot["AER_EV_AGGS"]) == {e.agg for e in ae.EV_REGISTRY if e.agg != "cell"}
    assert set(bot["AER_EV_STRATA"]) == {e.stratum for e in ae.EV_REGISTRY}
    assert bot["AER_FINDING_WIDTH"] == len(ae._finding_row(_finding("card", "k", "a", "b", "m")))


def test_b1_plan_shows_every_phase3_leaf_once(bot):
    a, b = _pair()
    body = _p3_game_body(a, b)
    page, plan = check_plan(bot, body)
    secs = page.games[0]["sections"]
    assert [len(s["findings"]) for s in secs] == [1, 0, 1]
    assert sum(1 for i in plan if i.text.startswith("FINDING")) == 2
    for shape in ("pair", "player"):
        for cells in (True, False):
            sbody = _p3_summary_body(shape, cells)
            spage, splan = check_plan(bot, sbody)
            assert spage.evidence["state"] == ("ok" if cells else "not_derived")
            texts = [i.text for i in splan]
            assert any(t.startswith("EVIDENCE RANKS") for t in texts)
            if not cells:
                assert any("no stored contribution yet" in t for t in texts)
            else:
                assert sum(1 for t in texts if t.startswith("EVIDENCE WINDOW")) == (
                    1 if shape == "player" else 2)
            limit = bot["AER_FACTS_LINE_CHARS"]
            assert all(len(t) <= limit for t in texts if t.startswith(("M ", "S ")))


def test_b1_fallback_text_carries_findings_and_ranks(bot):
    a, b = _pair()
    for body in (_p3_game_body(a, b), _p3_summary_body("pair")):
        page = bot["_aer_decode_response"](copy.deepcopy(body), "1a")
        text, files = bot["_aer_fallback"]("H", bot["_aer_plan"](page), "g", 1)
        shown = text if not files else files[0].data.decode("utf-8")
        assert ("rule_id=zz-r1" in shown) or ("pop_rank=0.5" in shown and "s=0" in shown)


def _p3_breaks():
    def fset(body, path, value):
        node = body
        for step in path[:-1]:
            node = node[step]
        node[path[-1]] = value
        return body
    at = ("games", 0, "sections", 0)
    ev = ("evidence",)
    return [
        ("finding width", "g", lambda x: fset(x, at + ("findings", 0), ["zz", "game", "t"])),
        ("finding null rule", "g", lambda x: fset(x, at + ("findings", 0, 0), None)),
        ("finding escaped", "g", lambda x: fset(x, at + ("findings", 0, 0), "a\x07")),
        ("findings not list", "g", lambda x: fset(x, at + ("findings",), {})),
        ("unavailable with findings", "g", lambda x: fset(
            x, ("games", 0, "sections", 1, "findings"), [["zz", "game", "t", None]])),
        ("evidence key extra", "s", lambda x: fset(x, ev + ("extra",), 1)),
        ("evidence state", "s", lambda x: fset(x, ev + ("state",), "armed")),
        ("evidence fingerprint", "s", lambda x: fset(x, ev + ("fingerprint",), "XYZ")),
        ("evidence census", "s", lambda x: fset(x, ev + ("census", "K"), [1, 2])),
        ("evidence key fields", "s", lambda x: fset(x, ev + ("catalog", 0, "key"), "a|b")),
        ("evidence key prov", "s", lambda x: fset(
            x, ev + ("catalog", 0, "key"),
            x["evidence"]["catalog"][0]["key"].replace("|SELF|", "|PEER|"))),
        ("evidence duplicate ki", "s", lambda x: fset(
            x, ev + ("catalog", 1, "ki"), x["evidence"]["catalog"][0]["ki"])),
        ("evidence windows count", "s", lambda x: fset(x, ev + ("windows",), [])),
        ("evidence cell width", "s", lambda x: fset(x, ev + ("windows", 0, "cells", 0), [1])),
        ("evidence cell ki", "s", lambda x: fset(x, ev + ("windows", 0, "cells", 0, 0), 99999)),
        ("evidence cell stratum", "s", lambda x: fset(x, ev + ("windows", 0, "cells", 0, 1), 9)),
        ("evidence cell basis", "s", lambda x: fset(x, ev + ("windows", 0, "cells", 0, 2), "x")),
        ("evidence cell null value", "s", lambda x: fset(
            x, ev + ("windows", 0, "cells", 0, 4), None)),
        ("evidence cell rank text", "s", lambda x: fset(
            x, ev + ("windows", 0, "cells", 0, 5), "0.5")),
        ("evidence not ok with cells", "s", lambda x: fset(x, ev + ("state",), "not_derived")),
        ("evidence on a game page", "g", lambda x: fset(x, ("evidence",), _evidence("player"))),
    ]


@pytest.mark.parametrize("label,kind,mutate", _p3_breaks(), ids=[x[0] for x in _p3_breaks()])
def test_b1_each_malformed_phase3_variant_is_refused(bot, label, kind, mutate):
    a, b = _pair()
    body = _p3_game_body(a, b) if kind == "g" else _p3_summary_body("pair")
    assert bot["_aer_outcome"](200, copy.deepcopy(body))[1] is None, label
    assert bot["_aer_outcome"](200, mutate(copy.deepcopy(body))) == (None, SCHEMA), label


def test_b1_the_new_bot_sends_both_headers():
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
    assert calls[0][ae.PHASE3_HEADER] == ae.PHASE3_VALUE


def p2_bot_ns():
    """Main's bot at the lane's base (phase 2, no phase 3), lifted as
    test_discord_evidence_bot lifts the current one."""
    out = subprocess.run(["git", "-C", REPO, "show", P2_BASE + ":backend/discord_bot.py"],
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
    names = {t.id for n in picked if isinstance(n, ast.Assign) for t in n.targets
             if isinstance(t, ast.Name)}
    assert "AER_SECTIONS_HEADER" in names and "AER_PHASE3_HEADER" not in names
    ns = {k: v for k, v in bot_ns().items()
          if not k.startswith(("_aer_", "AER_", "_AER_")) and k not in (
              "BotPage", "AerItem", "AerSchemaError")}
    exec(compile(ast.Module(body=picked, type_ignores=[]), "p2_discord_bot.py", "exec"), ns)
    return ns


def _strip3(body):
    body = copy.deepcopy(body)
    body.pop("evidence", None)
    for g in body.get("games", []):
        for sec in g.get("sections", []):
            sec.pop("findings", None)
            sec["game"] = [f for f in sec["game"] if not f[0].startswith("findings")]
    for sec in body.get("sections_summary", []):
        sec["facts"] = [f for f in sec["facts"] if not f[0].startswith("findings")]
    return body


def test_b2_deploy_order_both_ways(bot):
    old = p2_bot_ns()
    a, b = _pair()
    for body in (_p3_game_body(a, b), _p3_summary_body("pair"), _p3_summary_body("player")):
        p2 = _strip3(body)
        page, word = old["_aer_outcome"](200, copy.deepcopy(p2))
        assert word is None and page is not None
        assert old["_aer_outcome"](200, copy.deepcopy(body)) == (None, SCHEMA)
        page, word = bot["_aer_outcome"](200, copy.deepcopy(p2))
        assert word is None and page.evidence is None
        assert all(s["findings"] == () for g in page.games for s in g["sections"])
