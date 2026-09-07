"""Sept 6 batch, Group 4 item c — the session report envelope
(GET /api/v1/report) and the session_uuid plumbing around it.

Same harness as the sibling tests: no database. The handler is awaited as a
plain coroutine against a scripted session whose `execute` emulates each
statement in Python and REFUSES a statement that lost a load-bearing
predicate (the "lost predicate" pattern of test_queue_pair_writers). The
fixture match rows deliberately carry the three room-shaped columns a
careless serialiser would drag along, so the no-room-id pin can actually
fail; the pin's own checker is exercised against a leaky blob first.
"""
import asyncio
import inspect
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import main
from schemas import MatchHistoryEntry, MatchReport


# ── fixtures ────────────────────────────────────────────────────────────────

CALLER = "76561198000000001"      # player A, in every set below
OPP = "76561198000000002"         # player B
OTHER = "76561198000000003"       # never a participant
PID_A, PID_B, PID_C = (str(uuid.uuid4()) for _ in range(3))
SERIES = str(uuid.uuid4())
SESSION = str(uuid.uuid4())
SESSION_2 = str(uuid.uuid4())
M1, M2, M3, C1, C2, C3, N1 = (str(uuid.uuid4()) for _ in range(7))
TEAM_SERIES, TM1, FFA1 = (str(uuid.uuid4()) for _ in range(3))
ROOM_SECRET = "ranked_SECRETROOM77"
T0 = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
END_STATS = "1|" + "|".join(["100"] * 21)

ROOM_KEYS = ("photon_room_id", "room_id", "room_name")


def _room_cols():
    return {k: ROOM_SECRET for k in ROOM_KEYS}


def match_row(mid, p1, p2, *, minute, series_id=None, session_uuid=None, ranked=True,
              telemetry=True, dur=120):
    t = T0 + timedelta(minutes=minute)
    row = {
        "id": mid, "is_ranked": ranked, "series_id": series_id, "session_uuid": session_uuid,
        "started_at": t, "ended_at": t + timedelta(seconds=dur), "created_at": t,
        "invalidated_at": None, "duration_s": dur,
        "player1_id": p1, "player2_id": p2,
        "p1_rounds_won": 2, "p2_rounds_won": 1, "p1_points_total": 8, "p2_points_total": 5,
    }
    tele = {
        "point_timeline": "1:0,1:1,2:1", "point_times": "12,47,89",
        "p1_fps_timeline": "60,58,61", "p2_fps_timeline": "30,31,29",
        "p1_ping_timeline": "40,42,41", "p2_ping_timeline": "80,82,79",
        "p1_hit_timeline": "10:4,20:9,30:15", "p2_hit_timeline": "12:3,24:8,36:10",
        "p1_block_timeline": "2:1,4:3,6:4", "p2_block_timeline": "1:0,2:1,3:1",
        "p1_damage_timeline": "0,100,250", "p2_damage_timeline": "0,60,120",
        "p1_end_stats": END_STATS, "p2_end_stats": END_STATS,
        "p1_bullets_fired": 30, "p1_bullets_hit": 15, "p1_blocks_activated": 6,
        "p1_blocks_successful": 4, "p1_keys_pressed": 500, "p1_active_seconds": 100.54,
        "p1_damage_dealt": 250, "p1_deaths": 1,
        "p2_bullets_fired": 36, "p2_bullets_hit": 10, "p2_blocks_activated": 3,
        "p2_blocks_successful": 1, "p2_keys_pressed": 400, "p2_active_seconds": 90.0,
        "p2_damage_dealt": 120, "p2_deaths": 2,
    }
    if not telemetry:
        tele = {k: None for k in tele}
    row.update(tele)
    row.update(_room_cols())
    return row


PLAYERS = [
    {"id": PID_A, "steam_id": CALLER, "display_name": "Spirit"},
    {"id": PID_B, "steam_id": OPP, "display_name": "Dopex"},
    {"id": PID_C, "steam_id": OTHER, "display_name": "Bystander"},
]
SERIES_ROW = {
    "id": SERIES, "player1_id": PID_B, "player2_id": PID_A,   # series order differs from match order
    "status": "completed", "completed_at": T0 + timedelta(minutes=30),
    "invalidated_at": None, "p1_rating_change": -12.5, "p2_rating_change": 12.5,
    **_room_cols(),
}
MATCHES = [
    match_row(M1, PID_A, PID_B, minute=0, series_id=SERIES),
    match_row(M2, PID_B, PID_A, minute=5, series_id=SERIES),
    match_row(M3, PID_A, PID_B, minute=10, series_id=SERIES),
    match_row(C1, PID_A, PID_B, minute=60, ranked=False, session_uuid=SESSION),
    match_row(C2, PID_A, PID_B, minute=65, ranked=False, session_uuid=SESSION),
    match_row(C3, PID_A, PID_B, minute=90, ranked=False, session_uuid=SESSION_2),
    match_row(N1, PID_A, PID_B, minute=120, ranked=False, telemetry=False),
]
CARDS = [
    {"match_id": M1, "player_id": PID_A, "card_name": "BombsAway", "pick_order": 1, "round_number": 0},
    {"match_id": M1, "player_id": PID_B, "card_name": "Leach", "pick_order": 1, "round_number": 0},
    {"match_id": M1, "player_id": PID_A, "card_name": "Barrage", "pick_order": 2, "round_number": 1},
]
GOLD = [
    {"player_id": PID_A, "amount": 12, "reason": "series_win", "reference_id": SERIES},
    {"player_id": PID_B, "amount": 4, "reason": "series_loss", "reference_id": SERIES},
    {"player_id": PID_A, "amount": 5, "reason": "xp", "reference_id": M1},
    {"player_id": PID_A, "amount": 6, "reason": "team_xp", "reference_id": TM1},
    {"player_id": PID_C, "amount": 6, "reason": "team_xp", "reference_id": TM1},
    {"player_id": PID_A, "amount": 3, "reason": "xp", "reference_id": C1},
    {"player_id": PID_A, "amount": 4, "reason": "xp", "reference_id": C2},
    {"player_id": PID_A, "amount": 9, "reason": "xp", "reference_id": C3},
    {"player_id": PID_B, "amount": 2, "reason": "level_reward", "reference_id": C1},
]
RATING_HISTORY = [
    {"player_id": PID_A, "rating": 1512.5, "period_end": SERIES_ROW["completed_at"] + timedelta(milliseconds=40)},
    {"player_id": PID_B, "rating": 1487.5, "period_end": SERIES_ROW["completed_at"] + timedelta(milliseconds=40)},
    # a LATER series' snapshot: must never be picked for this one
    {"player_id": PID_A, "rating": 1600.0, "period_end": SERIES_ROW["completed_at"] + timedelta(hours=2)},
]
TEAM_SERIES_ROW = {
    "id": TEAM_SERIES, "t1a_id": PID_A, "t1b_id": PID_C, "t2a_id": PID_B, "t2b_id": None,
    "status": "completed", "completed_at": T0, "invalidated_at": None,
    "t1a_rating_change": 7.0, "t1b_rating_change": 7.0, "t2a_rating_change": -7.0,
    "t2b_rating_change": None, **_room_cols(),
}
TEAM_MATCHES = [{
    "id": TM1, "series_id": TEAM_SERIES, "started_at": T0, "ended_at": T0 + timedelta(seconds=300),
    "duration_s": 300, "invalidated_at": None,
    "t1a_id": PID_A, "t1b_id": PID_C, "t2a_id": PID_B, "t2b_id": None,
    "t1_rounds_won": 3, "t2_rounds_won": 1, "t1_points_total": 9, "t2_points_total": 4,
    "t1a_end_stats": END_STATS, "t1b_end_stats": None, "t2a_end_stats": None, "t2b_end_stats": None,
    **_room_cols(),
}]
TEAM_TELE = [
    {"match_id": TM1, "player_id": PID_A, "fps_timeline": "50,52", "ping_timeline": None,
     "hit_timeline": "5:2,10:6", "block_timeline": None, "damage_dealt_timeline": "0,300",
     "bullets_fired": 10, "bullets_hit": 6, "blocks_activated": None, "blocks_successful": None,
     "keys_pressed": 80, "active_seconds": 200.0},
]
FFA_MATCH = {"id": FFA1, "started_at": T0, "ended_at": T0 + timedelta(seconds=400),
             "duration_s": 400, "invalidated_at": None, **_room_cols()}
FFA_PLAYERS = [
    {"player_id": PID_A, "slot": 0, "placement": 1, "rounds_won": 5, "points_total": 5,
     "rating_before": 1500.0, "rating_after": 1520.0, "rating_change": 20.0, "gold_gained": 30,
     "fps_timeline": "60,60", "ping_timeline": "30,31", "hit_timeline": "4:1,8:3",
     "block_timeline": "1:1,2:2", "end_stats": END_STATS, "color_hex": "#FF8800",
     "bullets_fired": 8, "bullets_hit": 3, "blocks_activated": 2, "blocks_successful": 2,
     "keys_pressed": 50, "active_seconds": 300.0, "kills": 4},
    {"player_id": PID_B, "slot": 1, "placement": 2, "rounds_won": 3, "points_total": 3,
     "rating_before": 1500.0, "rating_after": 1490.0, "rating_change": -10.0, "gold_gained": 10,
     "fps_timeline": None, "ping_timeline": None, "hit_timeline": None,
     "block_timeline": None, "end_stats": None, "color_hex": None,
     "bullets_fired": None, "bullets_hit": None, "blocks_activated": None,
     "blocks_successful": None, "keys_pressed": None, "active_seconds": None, "kills": 1},
]


class _Res:
    def __init__(self, rows):
        self._rows = list(rows)

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class FakeDb:
    """Scripted read-only session. Each branch asserts the predicates the
    envelope's guarantees rest on, so a statement that lost one refuses."""

    def __init__(self):
        self.statements = []

    def count(self, needle):
        return sum(1 for s, _ in self.statements if needle in s)

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        self.statements.append((sql, params))
        if "FROM matches m" in sql:
            assert "m.invalidated_at IS NULL" in sql, "1v1 statement lost the invalidation predicate"
            key = params["key"]
            if "m.series_id = CAST(:key AS uuid)" in sql:
                rows = [m for m in MATCHES if str(m["series_id"]) == key]
            elif "m.session_uuid = CAST(:key AS uuid)" in sql:
                rows = [m for m in MATCHES if str(m["session_uuid"]) == key]
            elif "m.id = CAST(:key AS uuid)" in sql:
                rows = [m for m in MATCHES if str(m["id"]) == key]
            else:
                raise AssertionError("1v1 statement lost its selector predicate")
            rows.sort(key=lambda m: m["started_at"], reverse=True)
            return _Res(rows[: int(params["lim"])])
        if "FROM ranked_series rs" in sql:
            return _Res([r for r in [SERIES_ROW] if str(r["id"]) == params["key"]])
        if "FROM team_series ts" in sql:
            return _Res([r for r in [TEAM_SERIES_ROW] if str(r["id"]) == params["key"]])
        if "FROM ovt_series os" in sql:
            return _Res([])
        if "FROM team_matches tm" in sql:
            assert "tm.invalidated_at IS NULL" in sql
            key = params["key"]
            if "tm.series_id = CAST(:key AS uuid)" in sql:
                return _Res([m for m in TEAM_MATCHES if str(m["series_id"]) == key])
            return _Res([m for m in TEAM_MATCHES if str(m["id"]) == key])
        if "FROM team_match_telemetry tt" in sql:
            mids = set(params["mids"])
            return _Res([t for t in TEAM_TELE if str(t["match_id"]) in mids])
        if "FROM ovt_matches om" in sql:
            return _Res([])
        if "FROM ffa_matches fm" in sql:
            assert "fm.invalidated_at IS NULL" in sql
            return _Res([FFA_MATCH] if str(FFA_MATCH["id"]) == params["key"] else [])
        if "FROM ffa_match_players fp" in sql:
            return _Res(FFA_PLAYERS if params["key"] == FFA1 else [])
        if "FROM players p" in sql:
            pids = set(params["pids"])
            return _Res([p for p in PLAYERS if str(p["id"]) in pids])
        if " c WHERE c.match_id = ANY(CAST(:mids AS uuid[]))" in sql:
            table = sql.split("FROM ")[1].split(" ")[0]
            assert table in ("match_cards", "team_match_cards", "ovt_match_cards", "ffa_match_cards"), table
            mids = set(params["mids"])
            rows = [c for c in CARDS if str(c["match_id"]) in mids] if table == "match_cards" else []
            return _Res(rows)
        if "FROM gold_transactions gt" in sql:
            reasons, refs = set(params["reasons"]), set(params["refs"])
            agg = {}
            for g in GOLD:
                if g["reason"] in reasons and str(g["reference_id"]) in refs:
                    agg[g["player_id"]] = agg.get(g["player_id"], 0) + g["amount"]
            return _Res([{"player_id": p, "amount": a} for p, a in agg.items()])
        if "FROM rating_history rh" in sql:
            assert "make_interval" in sql and "CAST(:t0 AS timestamptz)" in sql, "rating window lost its typed binds"
            pids, t0 = set(params["pids"]), params["t0"]
            lo, hi = t0 - timedelta(seconds=60), t0 + timedelta(minutes=10)
            rows = [r for r in RATING_HISTORY if str(r["player_id"]) in pids and lo <= r["period_end"] <= hi]
            rows.sort(key=lambda r: r["period_end"])
            return _Res(rows)
        raise AssertionError(f"unexpected statement: {sql[:90]}")


def _run(coro):
    return asyncio.run(coro)


def _call(db, steam_id, **sel):
    return _run(main.get_set_report(request=None, steam_id=steam_id, db=db, **sel))


@pytest.fixture
def session_ok(monkeypatch):
    """Strict session check passes for CALLER and OTHER (both have valid
    sessions in this world); nobody else."""
    async def _ok(request, steam_id, db):
        return steam_id in (CALLER, OTHER)
    monkeypatch.setattr(main, "_strict_steam_session_ok", _ok)


def _no_room_leak(payload) -> bool:
    blob = json.dumps(payload, default=str)
    if ROOM_SECRET in blob:
        return False
    return not any(k in blob for k in ROOM_KEYS)


# ── the pins ─────────────────────────────────────────────────────────────────

def test_leak_checker_can_fail():
    """Negative control: the checker flags a leaky blob, so a passing pin means
    something (#391)."""
    assert not _no_room_leak({"x": ROOM_SECRET})
    assert not _no_room_leak({"photon_room_id": "anything"})
    assert _no_room_leak({"v": 1, "games": []})


def test_session_check_is_first_and_fail_closed(monkeypatch):
    async def _no(request, steam_id, db):
        return False
    monkeypatch.setattr(main, "_strict_steam_session_ok", _no)
    db = FakeDb()
    with pytest.raises(HTTPException) as ei:
        _call(db, CALLER, series=SERIES)
    assert ei.value.status_code == 401 and ei.value.detail == "session_required"
    assert db.statements == [], "a rejected session must not reach the database"


def test_selector_exclusivity_and_shape(session_ok):
    db = FakeDb()
    for sel in ({}, {"series": SERIES, "match": M1}, {"series": SERIES, "session": SESSION},
                {"match": "not-a-uuid"}, {"session": "12345"}):
        with pytest.raises(HTTPException) as ei:
            _call(db, CALLER, **sel)
        assert ei.value.status_code == 400 and ei.value.detail == "bad_request", sel
    assert db.statements == [], "selector errors are decided before any statement"


def test_participant_gate_is_a_404_indistinguishable_from_missing(session_ok):
    with pytest.raises(HTTPException) as bystander:
        _call(FakeDb(), OTHER, series=SERIES)
    with pytest.raises(HTTPException) as missing:
        _call(FakeDb(), CALLER, series=str(uuid.uuid4()))
    assert bystander.value.status_code == missing.value.status_code == 404
    assert bystander.value.detail == missing.value.detail == "not_found"


def test_ranked_series_envelope(session_ok):
    db = FakeDb()
    resp = _call(db, CALLER, series=SERIES)
    assert _no_room_leak(resp), "a room-shaped value or key reached the envelope"
    assert resp["v"] == 1 and resp["kind"] == "ranked" and resp["truncated"] is False
    ids = [p["id"] for p in resp["players"]]
    assert ids == [OPP, CALLER], "roster follows the series row order, keyed by steam id"
    names = {p["id"]: p["name"] for p in resp["players"]}
    assert names == {CALLER: "Spirit", OPP: "Dopex"}
    assert all(p["color"].startswith("#") for p in resp["players"])
    assert [g["match_id"] for g in resp["games"]] == [M1, M2, M3], "oldest first, whole set"
    g1 = resp["games"][0]
    assert g1["scores"] == {CALLER: 2, OPP: 1} and g1["points"] == {CALLER: 8, OPP: 5}
    assert g1["duration_s"] == 120
    assert g1["available"] == sorted(["blocks", "blocks_ok", "damage", "fps", "hits", "ping", "score", "shots"])
    tl = g1["timelines"][CALLER]
    assert tl["damage"] == [[40.0, 0], [80.0, 100], [120.0, 250]], "samples spread over the duration"
    assert tl["shots"] == [[40.0, 10], [80.0, 20], [120.0, 30]] and tl["hits"][-1] == [120.0, 15]
    assert tl["blocks"][-1] == [120.0, 6] and tl["blocks_ok"][-1] == [120.0, 4]
    assert tl["score"] == [[12.0, 1], [47.0, 1], [89.0, 2]]
    assert g1["timelines"][OPP]["score"] == [[12.0, 0], [47.0, 1], [89.0, 1]]
    assert g1["deaths"] == [{"t": 12.0, "id": OPP}, {"t": 47.0, "id": CALLER}, {"t": 89.0, "id": OPP}]
    assert g1["picks"] == [{"t": None, "id": CALLER, "card": "BombsAway"},
                           {"t": None, "id": OPP, "card": "Leach"},
                           {"t": None, "id": CALLER, "card": "Barrage"}]
    assert g1["end_build"] == {CALLER: ["BombsAway", "Barrage"], OPP: ["Leach"]}
    assert g1["end_stats"] == {CALLER: END_STATS, OPP: END_STATS}
    assert g1["totals"] == {
        CALLER: {"shots": 30, "hits": 15, "blocks": 6, "blocks_ok": 4, "keys": 500,
                 "damage": 250, "deaths": 1, "active_s": 100.5},
        OPP: {"shots": 36, "hits": 10, "blocks": 3, "blocks_ok": 1, "keys": 400,
              "damage": 120, "deaths": 2, "active_s": 90.0}}
    # game 2 was reported with the players swapped: still keyed by steam id
    assert resp["games"][1]["scores"] == {OPP: 2, CALLER: 1}
    # set_summary ONCE per set, from the series row + the completion snapshot
    ss = resp["set_summary"]
    assert ss["rating"] == {CALLER: {"before": 1500.0, "after": 1512.5, "delta": 12.5},
                            OPP: {"before": 1500.0, "after": 1487.5, "delta": -12.5}}
    assert ss["gold"] == {CALLER: 12, OPP: 4}
    assert db.count("FROM gold_transactions gt") == 1
    assert db.count("FROM rating_history rh") == 1
    assert db.count("FROM matches m") == 1, "one games statement per set, not one per game"


def test_session_selector_groups_by_uuid_only(session_ok):
    db = FakeDb()
    resp = _call(db, CALLER, session=SESSION)
    assert _no_room_leak(resp)
    assert resp["kind"] == "casual"
    assert [g["match_id"] for g in resp["games"]] == [C1, C2], "every game with that uuid and nothing else"
    stmt, params = next((s, p) for s, p in db.statements if "FROM matches m" in s)
    assert "m.session_uuid = CAST(:key AS uuid)" in stmt and params["key"] == SESSION
    # no rating on a casual sitting; gold is the per-game ledger fetched ONCE
    assert resp["set_summary"]["rating"] == {}
    assert resp["set_summary"]["gold"] == {CALLER: 7, OPP: 2}
    assert db.count("FROM gold_transactions gt") == 1
    assert db.count("FROM rating_history rh") == 0


def test_match_selector_single_game(session_ok):
    resp = _call(FakeDb(), CALLER, match=M1)
    assert resp["kind"] == "ranked" and [g["match_id"] for g in resp["games"]] == [M1]
    assert resp["set_summary"]["rating"] == {}, "a one-game view carries no series rating"
    assert resp["set_summary"]["gold"] == {CALLER: 5}
    resp2 = _call(FakeDb(), CALLER, match=C3)
    assert resp2["kind"] == "casual" and resp2["set_summary"]["gold"] == {CALLER: 9}


def test_match_without_telemetry_reports_nothing_recorded(session_ok):
    resp = _call(FakeDb(), CALLER, match=N1)
    g = resp["games"][0]
    assert g["available"] == []
    assert g["timelines"] == {CALLER: {}, OPP: {}}
    assert g["deaths"] == [] and g["picks"] == [] and g["end_stats"] == {}
    assert g["end_build"] == {CALLER: [], OPP: []}
    assert g["totals"] == {}, "NULL counters are absent, never zero (#257)"
    assert g["scores"] == {CALLER: 2, OPP: 1}, "scores exist even when telemetry does not"


def test_team_series_path(session_ok):
    resp = _call(FakeDb(), CALLER, series=TEAM_SERIES)
    assert _no_room_leak(resp)
    assert resp["kind"] == "team"
    teams = {p["id"]: p["team"] for p in resp["players"]}
    assert teams == {CALLER: 1, OTHER: 1, OPP: 2}
    g = resp["games"][0]
    assert g["scores"] == {CALLER: 3, OTHER: 3, OPP: 1}
    assert g["timelines"][CALLER]["damage"] == [[150.0, 0], [300.0, 300]]
    assert g["timelines"][CALLER]["shots"] == [[150.0, 5], [300.0, 10]]
    assert g["available"] == ["damage", "fps", "hits", "shots"]
    assert g["timelines"][OPP] == {}
    assert g["totals"] == {CALLER: {"shots": 10, "hits": 6, "keys": 80, "active_s": 200.0}}
    ss = resp["set_summary"]
    assert ss["rating"] == {CALLER: {"before": None, "after": None, "delta": 7.0},
                            OTHER: {"before": None, "after": None, "delta": 7.0},
                            OPP: {"before": None, "after": None, "delta": -7.0}}


def test_ffa_match_path(session_ok):
    resp = _call(FakeDb(), CALLER, match=FFA1)
    assert _no_room_leak(resp)
    assert resp["kind"] == "ffa"
    colors = {p["id"]: p["color"] for p in resp["players"]}
    assert colors[CALLER] == "#FF8800" and colors[OPP].startswith("#")
    g = resp["games"][0]
    assert g["scores"] == {CALLER: 5, OPP: 3}
    assert g["available"] == ["blocks", "blocks_ok", "fps", "hits", "ping", "shots"]
    assert resp["set_summary"]["rating"] == {CALLER: {"before": 1500.0, "after": 1520.0, "delta": 20.0},
                                             OPP: {"before": 1500.0, "after": 1490.0, "delta": -10.0}}
    assert resp["set_summary"]["gold"] == {CALLER: 30, OPP: 10}
    assert g["totals"] == {CALLER: {"shots": 8, "hits": 3, "blocks": 2, "blocks_ok": 2, "keys": 50,
                                    "kills": 4, "active_s": 300.0},
                           OPP: {"kills": 1}}
    # participant gate holds on the FFA path too: a bystander gets the same 404
    with pytest.raises(HTTPException) as ei:
        _call(FakeDb(), OTHER, match=FFA1)
    assert ei.value.status_code == 404 and ei.value.detail == "not_found"


def test_team_single_match_path(session_ok):
    """One 2v2 game by match id: resolved through team_matches after the 1v1
    miss, no series rating (no set row), gold from the 2v2 XP ledger ONCE."""
    db = FakeDb()
    resp = _call(db, CALLER, match=TM1)
    assert _no_room_leak(resp)
    assert resp["kind"] == "team" and [g["match_id"] for g in resp["games"]] == [TM1]
    assert resp["set_summary"]["rating"] == {}
    assert resp["set_summary"]["gold"] == {CALLER: 6, OTHER: 6}
    assert db.count("FROM gold_transactions gt") == 1
    stmt, params = next((s, p) for s, p in db.statements if "FROM gold_transactions gt" in s)
    assert set(params["reasons"]) == {"team_xp", "level_reward"} and params["refs"] == [TM1]


def test_no_room_column_in_any_report_statement():
    """Static half of the pin: none of the envelope's statements or serialisers
    name a room column, so the runtime pin above is not the only guard."""
    sources = [getattr(main, n) for n in dir(main) if n.startswith("_REPORT_") and n.endswith("_SQL")]
    sources += [inspect.getsource(main.get_set_report), inspect.getsource(main._report_game_json),
                inspect.getsource(main._report_totals), inspect.getsource(main._report_slot),
                inspect.getsource(main._report_load_1v1), inspect.getsource(main._report_load_team),
                inspect.getsource(main._report_load_ovt), inspect.getsource(main._report_load_ffa)]
    assert len(sources) >= 12
    for src in sources:
        low = src.lower()
        for bad in ("photon_room", "room_id", "room_name", "select *", "select m.*"):
            assert bad not in low, bad


# ── helpers ──────────────────────────────────────────────────────────────────

def test_samples_are_index_stamped_over_the_duration():
    assert main._report_samples("0,100,250", 120) == [[40.0, 0], [80.0, 100], [120.0, 250]]
    assert main._report_samples("10:4,20:9", 90, 0) == [[45.0, 10], [90.0, 20]]
    assert main._report_samples("10:4,20:9", 90, 1) == [[45.0, 4], [90.0, 9]]
    assert main._report_samples("5,x,7", 30) == [[10.0, 5], [30.0, 7]], "malformed token skipped, index kept"
    assert main._report_samples("", 120) is None
    assert main._report_samples(None, 120) is None
    assert main._report_samples("1,2,3", 0) is None, "no duration -> no timeline, never a fake grid"


def test_points_become_scores_and_deaths():
    sa, sb, deaths = main._report_points("12,47,89", "1:0,1:1,2:1", "A", "B")
    assert sa == [[12.0, 1], [47.0, 1], [89.0, 2]] and sb == [[12.0, 0], [47.0, 1], [89.0, 1]]
    assert deaths == [{"t": 12.0, "id": "B"}, {"t": 47.0, "id": "A"}, {"t": 89.0, "id": "B"}]
    assert main._report_points(None, "1:0", "A", "B") == (None, None, [])
    assert main._report_points("12", None, "A", "B") == (None, None, [])


def test_parse_uuid():
    u = str(uuid.uuid4())
    assert main._report_parse_uuid(u.upper()) == u
    assert main._report_parse_uuid(" " + u + " ") == u
    for bad in ("", None, "abc", "12345678-1234-1234-1234-12345678901", 42):
        assert main._report_parse_uuid(bad) is None


# ── the plumbing around the endpoint ─────────────────────────────────────────

def _min_report(**extra):
    body = {
        "player1": {"steam_id": CALLER, "display_name": "A"},
        "player2": {"steam_id": OPP, "display_name": "B"},
        "p1_rounds_won": 2, "p2_rounds_won": 0, "reported_by_steam_id": CALLER,
    }
    body.update(extra)
    return body


def test_match_report_schema_session_uuid():
    assert MatchReport(**_min_report()).session_uuid is None
    u = uuid.uuid4()
    assert MatchReport(**_min_report(session_uuid=str(u))).session_uuid == u
    with pytest.raises(ValidationError):
        MatchReport(**_min_report(session_uuid="ranked_room_1234"))
    with pytest.raises(ValidationError):
        MatchReport(**_min_report(session_uuid=12345))
    assert "session_uuid" in MatchHistoryEntry.model_fields
    assert MatchHistoryEntry.model_fields["session_uuid"].default is None


def test_insert_history_and_canonical_pins():
    submit = inspect.getsource(main.submit_match)
    assert submit.count("session_uuid=report.session_uuid") == 1, "stored on the ORM insert, once"
    canonical = inspect.getsource(main.verify_hmac)
    assert "session_uuid" not in canonical, "the 7-field canonical is untouched"
    assert 'f"{report.photon_room_id or \'\'}"' in canonical
    history = inspect.getsource(main.get_player_matches)
    assert "m.session_uuid," in history
    assert 'session_uuid=str(row["session_uuid"]) if row["session_uuid"] else None' in history
    from models import Match
    assert "session_uuid" in Match.__table__.columns, "declared on the model (#346)"
