"""QDIG-1: the classification of held game reports, and the words built on it.

Pure: the facts _qdig_load would read are built by qdig_fixtures from the
numbers of the six live rows of 16 Nov 2026 (invented names and ids). The
live-PostgreSQL half (the janitor pass, the posted route, the feed, the Admin
list, migration 419) is test_qdig_pg.py.

FOR THE RECORD is narrow by construction: a mistake there costs an admin one
question, never a held game. Every case below that is not the fixture's own
A or B game must come out NEEDS A DECISION.
"""

import ast
import inspect
import os
import re
import textwrap

import pytest

import main
import qdig_fixtures as fx

MAIN_SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api", "main.py"))
FTR, NEEDS = main.QDIG_FOR_THE_RECORD, main.QDIG_NEEDS_DECISION


def classify(game, numbers=None, *, reason=None, keyed=True, recorded=None, flags=None, winner=None,
             **facts_kw):
    body = fx.payload(game, numbers, flags=flags, winner=winner)
    r = fx.row(game, keyed=keyed, reason=reason, body=body)
    f = fx.facts(game, recorded=recorded, **facts_kw)
    return main._qdig_classify(r, f), r, f


# ── the six live rows ──────────────────────────────────────────────────────

def test_the_four_live_contradiction_rows_are_for_the_record():
    rows = fx.live_rows()
    f = fx.facts("A", "B", "C2", "C3")
    got = [(main._qdig_classify(r, f)["class"], r["reason"]) for r in rows]
    assert got == [(FTR, "ffa_game_contradiction")] * 4 + [(NEEDS, "lobby_completed")] * 2


def test_a_variant_row_finds_its_recorded_game_by_the_room_its_body_names():
    v, _, _ = classify("A", keyed=False)
    assert v["class"] == FTR and v["recorded_game"] == "b8ffc875f9d8"


def test_the_two_unrecorded_october_games_need_a_decision():
    for game in ("C2", "C3"):
        v, _, _ = classify(game)
        assert v["class"] == NEEDS and v["recorded_game"] is None


# ── one difference besides kills, each on its own ──────────────────────────

A_REC = fx.GAMES["A"]["recorded"]


def _with(nums, i, j, value):
    out = [list(n) for n in nums]
    out[i][j] = value
    return [tuple(n) for n in out]


@pytest.mark.parametrize("field,numbers", [
    ("rounds_won", _with(fx.GAMES["A"]["held"], 3, 0, 2)),
    ("points_total", _with(fx.GAMES["A"]["held"], 1, 1, 9)),
])
def test_a_rounds_or_points_difference_needs_a_decision(field, numbers):
    v, _, _ = classify("A", numbers)
    assert v["class"] == NEEDS
    assert field in {d["field"] for d in v["differences"]}


def test_a_winner_difference_needs_a_decision():
    v, _, _ = classify("A", winner=2)
    assert v["class"] == NEEDS and "winner" in {d["field"] for d in v["differences"]}


@pytest.mark.parametrize("flags,field", [({4: (True, False)}, "left_early"), ({4: (False, True)}, "absent")])
def test_a_raw_left_early_or_absent_difference_needs_a_decision(flags, field):
    v, _, _ = classify("A", flags=flags)
    assert v["class"] == NEEDS
    assert field in {d["field"] for d in v["differences"]}


def test_the_servers_own_comparison_is_consulted(monkeypatch):
    """The arm's comparison (kills not compared) must agree as well: a
    difference it finds, and the raw fields do not, keeps the row."""
    monkeypatch.setattr(main, "_ffa_report_contradiction", lambda *a, **k: "did-not-play differs")
    v, _, _ = classify("A")
    assert v["class"] == NEEDS


# ── placements: kills move a place only where they break a tie ─────────────

TIE_REC = [(5, 14, 31), (4, 10, 18), (4, 10, 24), (3, 8, 13)]
TIE_HELD = [(5, 14, 31), (4, 10, 19), (4, 10, 23), (3, 8, 13)]


def test_a_tie_kills_decide_needs_a_decision():
    v, _, _ = classify("A", TIE_HELD, recorded=TIE_REC, kills_tiebreak=True)
    assert v["class"] == NEEDS
    assert v["blockers"] == ["two players share rounds and points where kills break ties"]


def test_the_same_tie_in_a_lobby_whose_kills_break_no_tie_is_for_the_record():
    v, _, _ = classify("A", TIE_HELD, recorded=TIE_REC, kills_tiebreak=False)
    assert v["class"] == FTR


def test_the_borrowed_placement_rule_is_the_settlements():
    """Ruling 1 as changed by the integrator: with rounds and points equal,
    kills can move a placement only through submit_ffa_match's _place_key,
    whose third field is kills, and only when kills_break_ties. Red when the
    settlement's key changes."""
    src = inspect.getsource(main.submit_ffa_match)
    m = re.search(r"def _place_key\(p\) -> tuple:\s*\n\s*return \((.*)\)\n", src)
    assert m, "submit_ffa_match no longer defines _place_key"
    assert [f.strip() for f in m.group(1).split(",")] == [
        "p.rounds_won", "p.points_total", "p.kills if kills_break_ties else 0"]
    assert "kills_break_ties = kills_in_canonical and _lobby_kills_capable" in src
    assert "_lobby_kills_capable = bool(lobby[\"kills_tiebreak\"])" in src


# ── kills: the gap and the paid thresholds ─────────────────────────────────

@pytest.mark.parametrize("held,recorded,want", [
    (31, 32, FTR),       # one kill apart, both under 50
    (49, 51, NEEDS),     # crosses the >50 grant
    (18, 21, NEEDS),     # three apart
    (100, 102, NEEDS),   # crosses the >100 grant
    (60, 62, FTR),       # both over 50, both under 100
])
def test_kill_counts(held, recorded, want):
    nums_rec = _with(A_REC, 1, 2, recorded)
    nums_held = _with(A_REC, 1, 2, held)
    v, _, _ = classify("A", nums_held, recorded=nums_rec)
    assert v["class"] == want, v["blockers"]


def test_the_kill_thresholds_are_the_settlements_grant_site():
    src = inspect.getsource(main.submit_ffa_match)
    found = [int(n) for n in re.findall(r"if _kills > (\d+):\s*\n\s*await _grant_achievement_inline\("
                                        r"db, _ach_pid, \"ffa_kills_\d+\"\)", src)]
    assert found == list(main.QDIG_KILLS_THRESHOLDS)
    assert main.QDIG_KILLS_TOLERANCE == 2


# ── what is never FOR THE RECORD ───────────────────────────────────────────

def test_a_row_whose_room_is_not_recorded_needs_a_decision():
    f = fx.facts("A")
    f["matches"].clear()
    v = main._qdig_classify(fx.row("A"), f)
    assert v["class"] == NEEDS and v["recorded_game"] is None


def test_only_the_contradiction_reason_is_ever_filed():
    """A lobby_completed row whose room a recorded game holds with the very
    same numbers is still a decision."""
    v, _, _ = classify("A", fx.GAMES["A"]["recorded"], reason="lobby_completed")
    assert v["class"] == NEEDS


def _team_row(shape):
    p = lambda n: {"steam_id": fx.steam(n), "display_name": fx.NAMES[n]}   # noqa: E731
    if shape == "2v2":
        body = {"series_id": "s", "t1a": p(1), "t1b": p(2), "t2a": p(3), "t2b": p(4), "t1_rounds_won": 3,
                "t2_rounds_won": 1, "t1_points_total": 25, "t2_points_total": 12, "winner_team": 1,
                "reported_by_steam_id": fx.steam(1), "photon_room_id": "QDIGTEAM_r1", "is_ranked": True}
    else:
        body = {"series_id": "s", "solo": p(1), "duo_a": p(2), "duo_b": p(3), "solo_rounds_won": 2,
                "duo_rounds_won": 3, "solo_points_total": 18, "duo_points_total": 26, "winner_side": 2,
                "reported_by_steam_id": fx.steam(2), "photon_room_id": "QDIGOVT_r1", "is_ranked": False}
    return {"id": "d0d0d0d0-0000-4000-8000-0000000000d0", "mode": "team", "reason": "series_completed",
            "group_id": None, "photon_room_id": body["photon_room_id"], "payload": body,
            "created_at": fx.T_LIVE, "digest_posted_at": None}


@pytest.mark.parametrize("shape", ["2v2", "1v2"])
def test_2v2_and_1v2_rows_are_never_filed(shape):
    f = fx.facts("A")
    v = main._qdig_classify(_team_row(shape), f)
    assert v["class"] == NEEDS


def test_a_voided_recorded_game_still_files_and_the_note_says_so():
    v, _, f = classify("A", voided=True)
    assert v["class"] == FTR and v["voided"] is True
    assert "that game was later voided" in main._qdig_filed_note(v, f)


# ── the words ──────────────────────────────────────────────────────────────

def test_the_machine_note_names_the_players_and_both_counts():
    v, _, f = classify("A")
    assert main._qdig_filed_note(v, f) == (
        "auto-filed: same result as the recorded game b8ffc875f9d8; kills differ for 2 players "
        "(Heron 19 against 18, Iris 23 against 24) (held report against recorded game)")
    v, _, f = classify("B")
    assert main._qdig_filed_note(v, f) == (
        "auto-filed: same result as the recorded game 5e1f00d277aa; kills differ for 1 player "
        "(Heron 33 against 34) (held report against recorded game)")


def test_the_admin_lists_three_strings_for_an_f5_row():
    r = fx.row("C2")
    f = fx.facts("C2")
    v = main._qdig_classify(r, f)
    reason = main._qdig_admin_reason(r, v, f)
    score = main._qdig_score(r, v, f)
    assert reason == ("The lobby had already been closed when this report arrived, so the game was never "
                      "recorded. [lobby_completed]")
    # Cedar would take it to 68 characters, so the last two players are +2.
    assert score == "Dune 5r 11p | Elm 2r 5p | Ash 0r 2p | Birch 0r 2p | +2"
    assert len(reason) <= 140 and len(score) <= 64
    assert main._quarantine_accept_verdict(40, 6) == (
        False, "6 players have played rated games since; adding this game now would need a full replay")
    assert main._quarantine_accept_verdict(1, 1) == (
        False, "1 player has played rated games since; adding this game now would need a full replay")
    assert main._quarantine_accept_verdict(0, 0) == (True, "")


def test_the_admin_strings_stay_within_the_clients_lengths_for_long_names():
    f = fx.facts("C2")
    for s in f["names"].values():
        s["display_name"] = "W" * 64
    for reason in ("lobby_completed", "ffa_game_contradiction", "ffa_replay_roster_mismatch",
                   "lobby_" + "x" * 58, "score_shape_mismatch"):
        r = fx.row("C2", reason=reason)
        v = main._qdig_classify(r, f)
        assert len(main._qdig_admin_reason(r, v, f)) <= 140
        assert len(main._qdig_score(r, v, f)) <= 64
        assert main._qdig_admin_reason(r, v, f).endswith("[" + reason[:64] + "]")


def test_a_needs_decision_contradiction_says_what_differs_with_names_and_numbers():
    v, r, f = classify("A", _with(fx.GAMES["A"]["held"], 3, 0, 2))
    assert v["class"] == NEEDS
    assert main._qdig_reason_sentence(r, v, f) == (
        "Another seat's report of the recorded game b8ffc875f9d8 that disagrees with it: "
        "rounds differ for 1 player (Juniper 2 against 3); "
        "kills differ for 2 players (Heron 19 against 18, Iris 23 against 24).")


def test_the_texts_are_ascii_apart_from_names():
    rows = fx.live_rows()
    f = fx.facts("A", "B", "C2", "C3")
    for r in rows:
        v = main._qdig_classify(r, f)
        for s in (main._qdig_reason_sentence(r, v, f), main._qdig_admin_reason(r, v, f),
                  main._qdig_score(r, v, f)):
            assert s.isascii(), s


# ── one copy of the rule ───────────────────────────────────────────────────

def _functions():
    tree = ast.parse(open(MAIN_SRC, encoding="utf-8").read())
    return {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_census_one_classifier_and_every_reader_calls_it():
    fns = _functions()
    deciders = sorted(name for name, fn in fns.items()
                      if any(isinstance(n, ast.Assign) and isinstance(n.value, ast.Name)
                             and n.value.id == "QDIG_FOR_THE_RECORD" for n in ast.walk(fn)))
    assert deciders == ["_qdig_classify"], deciders
    readers = sorted(name for name, fn in fns.items()
                     if any(isinstance(n, ast.Name) and n.id in ("QDIG_KILLS_THRESHOLDS", "QDIG_KILLS_TOLERANCE")
                            for n in ast.walk(fn)))
    assert readers == ["_qdig_classify"], readers

    def calls(fn):
        return {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    for consumer in ("_qdig_janitor_pass", "_qdig_feed_rows", "admin_list_quarantine", "_qdig_needs_games"):
        assert "_qdig_classify" in calls(fns[consumer]), consumer
    assert "_qdig_needs_games" in calls(fns["_qdig_janitor_pass"])
    # The word 'filed' is written by one statement only.
    src = open(MAIN_SRC, encoding="utf-8").read()
    assert len(re.findall(r"status\s*=\s*'filed'", src)) == 1


def test_census_one_accept_verdict():
    fns = _functions()

    def calls(fn):
        return {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_quarantine_accept_verdict" in calls(fns["admin_list_quarantine"])
    assert "_quarantine_accept_verdict" in calls(fns["_qdig_feed_keys"])
    src = open(MAIN_SRC, encoding="utf-8").read()
    assert src.count("played rated games since") == 1
