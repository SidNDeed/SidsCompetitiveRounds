"""Sept 6 batch, Group 4 item c — the session report envelope
(GET /api/v1/report) and the session_uuid plumbing around it.

Same harness as the sibling tests: no database. The handler is awaited as a
plain coroutine against a scripted session whose `execute` emulates each
statement in Python and REFUSES a statement that lost a load-bearing
predicate (the "lost predicate" pattern of test_queue_pair_writers). The
fixture match rows deliberately carry the three room-shaped columns a
careless serialiser would drag along, so the no-room-id pin can actually
fail; the pin's own checker is exercised against a leaky blob first.

Review r1 added the fixtures the first suite lacked, each with a negative
control (#391): a session uuid shared by two pairs and by two rosters of the
caller, an FFA frozen-roster ghost (`absent`), stored FFA damage / kill /
score telemetry, a rolled-out FFA pick, the rating snapshot joined by series
identity rather than a time window, the byte bound against worst-case
shapes, and the C# surfaces the plugin must carry (1v2 Session control,
continuation paging, translated dividers and diagnostics).
"""
import asyncio
import inspect
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import main
from schemas import MatchHistoryEntry, MatchReport
from _cs_structure import method_spans, strip_comments_only

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


# ── fixtures ────────────────────────────────────────────────────────────────

CALLER = "76561198000000001"      # player A, in every set below
OPP = "76561198000000002"         # player B
OTHER = "76561198000000003"       # C: a 2v2 team-mate of A, never in a 1v1 with A
XSTEAM = "76561198000000004"      # X and Y: another pair whose reporter reused A's session uuid
YSTEAM = "76561198000000005"
GHOST = "76561198000000006"       # G: an FFA frozen-roster ghost (absent row)
NOBODY = "76561198000000099"      # a valid session but no player row at all
PID_A, PID_B, PID_C, PID_X, PID_Y, PID_G = (str(uuid.uuid4()) for _ in range(6))
SERIES = str(uuid.uuid4())
SERIES_LATER = str(uuid.uuid4())  # a second ranked series of A, completed 30 s after SERIES
SESSION = str(uuid.uuid4())
SESSION_2 = str(uuid.uuid4())
M1, M2, M3, C1, C2, C3, CX, X1, N1 = (str(uuid.uuid4()) for _ in range(9))
TEAM_SERIES, TM1, FFA1 = (str(uuid.uuid4()) for _ in range(3))
ROOM_SECRET = "ranked_SECRETROOM77"
T0 = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
END_STATS = "1|" + "|".join(["100"] * 21)

ROOM_KEYS = ("photon_room_id", "room_id", "room_name")


def _room_cols():
    return {k: ROOM_SECRET for k in ROOM_KEYS}


def match_row(mid, p1, p2, *, minute, series_id=None, session_uuid=None, ranked=True,
              telemetry=True, dur=120, rules=None):
    t = T0 + timedelta(minutes=minute)
    row = {
        "id": mid, "is_ranked": ranked, "series_id": series_id, "session_uuid": session_uuid,
        "rules": rules,   # the series record the games statement LEFT JOINs (migration 306)
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
    {"id": PID_X, "steam_id": XSTEAM, "display_name": "Xavier"},
    {"id": PID_Y, "steam_id": YSTEAM, "display_name": "Yara"},
    {"id": PID_G, "steam_id": GHOST, "display_name": "Ghost"},
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
    # A's casual sitting with B, then — under the SAME reporter-minted uuid —
    # one game A played against C (a different roster) and one game the X/Y
    # pair filed with A's uuid (a client-chosen label, not a fact about A).
    match_row(CX, PID_A, PID_C, minute=55, ranked=False, session_uuid=SESSION),
    match_row(C1, PID_A, PID_B, minute=60, ranked=False, session_uuid=SESSION),
    match_row(C2, PID_A, PID_B, minute=65, ranked=False, session_uuid=SESSION),
    match_row(X1, PID_X, PID_Y, minute=70, ranked=False, session_uuid=SESSION),
    match_row(C3, PID_A, PID_B, minute=90, ranked=False, session_uuid=SESSION_2),
    match_row(N1, PID_A, PID_B, minute=120, ranked=False, telemetry=False),
]
CARDS = [
    {"match_id": M1, "player_id": PID_A, "card_name": "BombsAway", "pick_order": 1, "round_number": 0, "rolled": False},
    {"match_id": M1, "player_id": PID_B, "card_name": "Leach", "pick_order": 1, "round_number": 0, "rolled": False},
    {"match_id": M1, "player_id": PID_A, "card_name": "Barrage", "pick_order": 2, "round_number": 1, "rolled": False},
]
FFA_CARDS = [
    # A's sixth pick rolled "Alpha" out of the five-card build (migration 156).
    {"match_id": FFA1, "player_id": PID_A, "card_name": "Alpha", "pick_order": 1, "round_number": 0, "rolled": True},
    {"match_id": FFA1, "player_id": PID_A, "card_name": "Beta", "pick_order": 2, "round_number": 1, "rolled": False},
    {"match_id": FFA1, "player_id": PID_A, "card_name": "Gamma", "pick_order": 3, "round_number": 2, "rolled": False},
    {"match_id": FFA1, "player_id": PID_G, "card_name": "GhostCard", "pick_order": 1, "round_number": 0, "rolled": False},
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
    {"player_id": PID_A, "amount": 8, "reason": "xp", "reference_id": CX},
    {"player_id": PID_B, "amount": 2, "reason": "level_reward", "reference_id": C1},
]
# Snapshots: the two the completion of SERIES linked (migration 299), a
# decoy A snapshot the 097/104 backfills could not attribute (series_id NULL)
# that sits EARLIER in the old 60-second window, and A's next series 30 s
# later. Identity picks 1512.5; the old window rule picked 1499.0.
RATING_HISTORY = [
    {"player_id": PID_A, "rating": 1499.0, "series_id": None,
     "period_end": SERIES_ROW["completed_at"] - timedelta(seconds=20)},
    {"player_id": PID_A, "rating": 1512.5, "series_id": SERIES,
     "period_end": SERIES_ROW["completed_at"] + timedelta(milliseconds=40)},
    {"player_id": PID_B, "rating": 1487.5, "series_id": SERIES,
     "period_end": SERIES_ROW["completed_at"] + timedelta(milliseconds=40)},
    {"player_id": PID_A, "rating": 1600.0, "series_id": SERIES_LATER,
     "period_end": SERIES_ROW["completed_at"] + timedelta(seconds=30)},
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
# FFA: six half-point events, "slot[R][G]" (migration 156). A is slot 0, B slot
# 1; G (slot 2) is a frozen-roster ghost who did NOT play this game.
FFA_TIMELINE = "0,0R,1,1R,0,0RG"
FFA_MATCH = {"id": FFA1, "started_at": T0, "ended_at": T0 + timedelta(seconds=400),
             "duration_s": 400, "invalidated_at": None, "timeline": FFA_TIMELINE, **_room_cols(),
             # the lobby settings columns the games statement LEFT JOINs (a
             # lobby that predates configurable settings: nothing known)
             "score_target": None, "card_cap": None, "initial_picks": None, "card_candidates": None,
             "same_card_rule": None, "sudden_death": None, "settings_known": False}
# An FFA lobby played under a known configuration.
FFA_SETTINGS_ROW = dict(FFA_MATCH, score_target=7, card_cap=5, initial_picks=1, card_candidates=5,
                        same_card_rule=True, sudden_death=False, settings_known=True)


def ffa_player(pid, slot, placement, **over):
    row = {"player_id": pid, "slot": slot, "placement": placement, "rounds_won": 0, "points_total": 0,
           "rating_before": None, "rating_after": None, "rating_change": None, "gold_gained": None,
           "fps_timeline": None, "ping_timeline": None, "hit_timeline": None, "block_timeline": None,
           "damage_dealt_timeline": None, "kill_timeline": None, "damage_dealt": None,
           "end_stats": None, "color_hex": None, "absent": False,
           "bullets_fired": None, "bullets_hit": None, "blocks_activated": None,
           "blocks_successful": None, "keys_pressed": None, "active_seconds": None, "kills": 0}
    row.update(over)
    return row


FFA_PLAYERS = [
    ffa_player(PID_A, 0, 1, rounds_won=5, points_total=5, rating_before=1500.0, rating_after=1520.0,
               rating_change=20.0, gold_gained=30, fps_timeline="60,60", ping_timeline="30,31",
               hit_timeline="4:1,8:3", block_timeline="1:1,2:2", damage_dealt_timeline="0,400,900",
               kill_timeline="0,2,4", damage_dealt=900, end_stats=END_STATS, color_hex="#FF8800",
               bullets_fired=8, bullets_hit=3, blocks_activated=2, blocks_successful=2,
               keys_pressed=50, active_seconds=300.0, kills=4),
    ffa_player(PID_B, 1, 2, rounds_won=3, points_total=3, rating_before=1500.0, rating_after=1490.0,
               rating_change=-10.0, gold_gained=10, kills=1),
    # The ghost: holds slot 2 in the frozen roster, absent from THIS game, and
    # carries the all-zero tallies plus a rating stamp the writer never applies.
    ffa_player(PID_G, 2, 3, absent=True, rating_before=1500.0, rating_after=1500.0,
               rating_change=0.0, gold_gained=0, fps_timeline="1,1", kills=0),
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


class _NoopSavepoint:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeDb:
    """Scripted read-only session. Each branch asserts the predicates the
    envelope's guarantees rest on, so a statement that lost one refuses.
    Every table can be overridden per test (the size-bound tests build their
    own worst-case worlds); `fail_rating` makes the rating statement raise,
    the pre-299 schema shape."""

    def __init__(self, *, matches=None, players=None, cards=None, ffa_cards=None, gold=None,
                 rating_history=None, team_matches=None, team_tele=None, ffa_match=None,
                 ffa_players=None, series_row=None, team_series_row=None, fail_rating=False):
        self.statements = []
        self.matches = MATCHES if matches is None else matches
        self.players = PLAYERS if players is None else players
        self.cards = CARDS if cards is None else cards
        self.ffa_cards = FFA_CARDS if ffa_cards is None else ffa_cards
        self.gold = GOLD if gold is None else gold
        self.rating_history = RATING_HISTORY if rating_history is None else rating_history
        self.team_matches = TEAM_MATCHES if team_matches is None else team_matches
        self.team_tele = TEAM_TELE if team_tele is None else team_tele
        self.ffa_match = FFA_MATCH if ffa_match is None else ffa_match
        self.ffa_players = FFA_PLAYERS if ffa_players is None else ffa_players
        self.series_row = SERIES_ROW if series_row is None else series_row
        self.team_series_row = TEAM_SERIES_ROW if team_series_row is None else team_series_row
        self.fail_rating = fail_rating

    def count(self, needle):
        return sum(1 for s, _ in self.statements if needle in s)

    def begin_nested(self):
        return _NoopSavepoint()

    @staticmethod
    def _with_total(rows):
        out = []
        for r in rows:
            r = dict(r)
            r["total_rows"] = len(rows)
            # the set-wide ranked flag rides every row like total_rows does
            r["all_ranked"] = all(bool(x.get("is_ranked", True)) for x in rows)   # team/ovt rows carry no flag
            # the series record the games statement LEFT JOINs (migration 306):
            # None unless the fixture row carries one
            r.setdefault("rules", None)
            out.append(r)
        return out

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        self.statements.append((sql, params))
        if "FROM players p WHERE p.steam_id = :sid" in sql:
            return _Res([{"id": p["id"]} for p in self.players if p["steam_id"] == params["sid"]])
        if "FROM matches m" in sql:
            assert "m.invalidated_at IS NULL" in sql, "1v1 statement lost the invalidation predicate"
            assert "CAST(:cpid AS uuid) IN (m.player1_id, m.player2_id)" in sql, \
                "1v1 statement lost the participant predicate"
            assert "COUNT(*) OVER () AS total_rows" in sql, "1v1 statement lost its set count"
            assert "BOOL_AND(m.is_ranked) OVER () AS all_ranked" in sql, (
                "1v1 statement lost its set-wide ranked flag (the label must not depend on the retained rows)")
            key, cpid = params["key"], params["cpid"]
            if "m.series_id = CAST(:key AS uuid)" in sql:
                rows = [m for m in self.matches if str(m["series_id"]) == key]
            elif "m.session_uuid = CAST(:key AS uuid)" in sql:
                rows = [m for m in self.matches if str(m["session_uuid"]) == key]
            elif "m.id = CAST(:key AS uuid)" in sql:
                rows = [m for m in self.matches if str(m["id"]) == key]
            elif "anchor AS (" in sql and "make_interval(hours => " in sql:
                # Sept 8 item 5: the caller's sitting that contains the anchor
                # (gaps over SITTING_GAP_HOURS between the caller's finished
                # games split sittings), then the anchor pair's games inside it.
                # The fake's activity is its matches table only.
                assert f"make_interval(hours => {main.SITTING_GAP_HOURS})" in sql
                assert "CAST(:cpid AS uuid) IN (a.player1_id, a.player2_id)" in sql, \
                    "the anchor lost the caller predicate"
                mine = [m for m in self.matches if m["invalidated_at"] is None
                        and cpid in (str(m["player1_id"]), str(m["player2_id"]))]
                anchor = next((m for m in mine if str(m["id"]) == key), None)
                rows = []
                if anchor is not None:
                    sittings, cur = [], []
                    for t in sorted({m["ended_at"] for m in mine}):
                        if cur and t - cur[-1] > timedelta(hours=main.SITTING_GAP_HOURS):
                            sittings.append(cur)
                            cur = []
                        cur.append(t)
                    sittings.append(cur)
                    span = next(s for s in sittings if anchor["ended_at"] in s)
                    pair = {str(anchor["player1_id"]), str(anchor["player2_id"])}
                    rows = [m for m in self.matches
                            if span[0] <= m["ended_at"] <= span[-1]
                            and {str(m["player1_id"]), str(m["player2_id"])} == pair]
            else:
                raise AssertionError("1v1 statement lost its selector predicate")
            rows = [m for m in rows if m["invalidated_at"] is None
                    and cpid in (str(m["player1_id"]), str(m["player2_id"]))]
            rows.sort(key=lambda m: m["started_at"], reverse=True)
            return _Res(self._with_total(rows)[: int(params["lim"])])
        if "FROM ranked_series rs" in sql:
            return _Res([r for r in [self.series_row] if str(r["id"]) == params["key"]])
        if "FROM team_series ts" in sql:
            return _Res([r for r in [self.team_series_row] if str(r["id"]) == params["key"]])
        if "FROM ovt_series os" in sql:
            return _Res([])
        if "FROM team_matches tm" in sql:
            assert "tm.invalidated_at IS NULL" in sql
            assert "CAST(:cpid AS uuid) IN (tm.t1a_id, tm.t1b_id, tm.t2a_id, tm.t2b_id)" in sql, \
                "2v2 statement lost the participant predicate"
            assert "COUNT(*) OVER () AS total_rows" in sql
            key, cpid = params["key"], params["cpid"]
            if "tm.series_id = CAST(:key AS uuid)" in sql:
                rows = [m for m in self.team_matches if str(m["series_id"]) == key]
            else:
                rows = [m for m in self.team_matches if str(m["id"]) == key]
            rows = [m for m in rows if cpid in {str(m[k]) for k in ("t1a_id", "t1b_id", "t2a_id", "t2b_id")
                                                if m[k] is not None}]
            rows.sort(key=lambda m: m["started_at"], reverse=True)
            return _Res(self._with_total(rows)[: int(params["lim"])])
        if "FROM team_match_telemetry tt" in sql:
            mids = set(params["mids"])
            return _Res([t for t in self.team_tele if str(t["match_id"]) in mids])
        if "FROM ovt_matches om" in sql:
            assert "CAST(:cpid AS uuid) IN (om.solo_id, om.duo_a_id, om.duo_b_id)" in sql, \
                "1v2 statement lost the participant predicate"
            return _Res([])
        if "FROM ffa_matches fm" in sql:
            assert "fm.invalidated_at IS NULL" in sql
            assert ("EXISTS (SELECT 1 FROM ffa_match_players fpx WHERE fpx.match_id = fm.id "
                    "AND fpx.player_id = CAST(:cpid AS uuid) AND NOT fpx.absent)") in sql, \
                "FFA statement lost the played-this-game participant predicate"
            if str(self.ffa_match["id"]) != params["key"]:
                return _Res([])
            played = any(str(p["player_id"]) == params["cpid"] and not p["absent"]
                         for p in self.ffa_players)
            return _Res([self.ffa_match] if played else [])
        if "FROM ffa_match_players fp" in sql:
            assert "AND NOT fp.absent" in sql, "FFA roster statement lost the absent filter"
            return _Res([p for p in self.ffa_players if not p["absent"]] if params["key"] == FFA1 else [])
        if "FROM players p" in sql:
            pids = set(params["pids"])
            return _Res([p for p in self.players if str(p["id"]) in pids])
        if " c WHERE c.match_id = ANY(CAST(:mids AS uuid[]))" in sql:
            table = sql.split("FROM ")[1].split(" ")[0]
            assert table in ("match_cards", "team_match_cards", "ovt_match_cards", "ffa_match_cards"), table
            if table == "ffa_match_cards":
                assert "c.rolled" in sql, "FFA card statement lost the rolled column"
            else:
                assert "FALSE AS rolled" in sql and "c.rolled" not in sql, \
                    "only the FFA card table records `rolled`"
            mids = set(params["mids"])
            source = {"match_cards": self.cards, "ffa_match_cards": self.ffa_cards}.get(table, [])
            return _Res([c for c in source if str(c["match_id"]) in mids])
        if "FROM gold_transactions gt" in sql:
            reasons, refs = set(params["reasons"]), set(params["refs"])
            agg = {}
            for g in self.gold:
                if g["reason"] in reasons and str(g["reference_id"]) in refs:
                    agg[g["player_id"]] = agg.get(g["player_id"], 0) + g["amount"]
            return _Res([{"player_id": p, "amount": a} for p, a in agg.items()])
        if "FROM rating_history rh" in sql:
            if self.fail_rating:
                raise RuntimeError('column rh.series_id does not exist')
            assert "rh.series_id = CAST(:key AS uuid)" in sql, "rating statement lost its identity join"
            assert "make_interval" not in sql and "period_end >=" not in sql, \
                "rating statement is a time window again"
            pids, key = set(params["pids"]), params["key"]
            rows = [r for r in self.rating_history
                    if str(r["player_id"]) in pids and str(r["series_id"]) == key]
            rows.sort(key=lambda r: r["period_end"])
            return _Res(rows)
        raise AssertionError(f"unexpected statement: {sql[:90]}")


def _run(coro):
    return asyncio.run(coro)


def _call(db, steam_id, **sel):
    return _run(main.get_set_report(request=None, steam_id=steam_id, db=db, **sel))


@pytest.fixture
def session_ok(monkeypatch):
    """Strict session check passes for every fixture identity (they all hold
    valid sessions in this world); nobody else."""
    async def _ok(request, steam_id, db):
        return steam_id in (CALLER, OPP, OTHER, XSTEAM, YSTEAM, GHOST, NOBODY)
    monkeypatch.setattr(main, "_strict_steam_session_ok", _ok)


def _no_room_leak(payload) -> bool:
    blob = json.dumps(payload, default=str)
    if ROOM_SECRET in blob:
        return False
    return not any(k in blob for k in ROOM_KEYS)


def _wire_bytes(payload) -> int:
    """The size FastAPI's JSONResponse puts on the wire: compact separators."""
    return len(json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8"))


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
    db = FakeDb()
    with pytest.raises(HTTPException) as no_row:
        _call(db, NOBODY, series=SERIES)
    assert bystander.value.status_code == missing.value.status_code == no_row.value.status_code == 404
    assert bystander.value.detail == missing.value.detail == no_row.value.detail == "not_found"
    # a caller with no player row is decided by the FIRST statement: nothing
    # about the set is read for an identity that cannot be a participant
    assert len(db.statements) == 1 and "p.steam_id = :sid" in db.statements[0][0]


def test_caller_is_resolved_first_and_required_in_every_games_statement(session_ok):
    db = FakeDb()
    _call(db, CALLER, series=SERIES)
    assert "p.steam_id = :sid" in db.statements[0][0] and db.statements[0][1] == {"sid": CALLER}
    games_stmt, params = next((s, p) for s, p in db.statements if "FROM matches m" in s)
    assert params["cpid"] == PID_A, "the games statement binds the CALLER's player id"
    assert "CAST(:cpid AS uuid) IN (m.player1_id, m.player2_id)" in games_stmt
    # every loader carries the predicate (the FakeDb refuses one that lost it)
    for src_name, needle in (("_REPORT_1V1_SQL", "CAST(:cpid AS uuid) IN (m.player1_id, m.player2_id)"),
                             ("_REPORT_TEAM_SQL", "CAST(:cpid AS uuid) IN (tm.t1a_id, tm.t1b_id, tm.t2a_id, tm.t2b_id)"),
                             ("_REPORT_OVT_SQL", "CAST(:cpid AS uuid) IN (om.solo_id, om.duo_a_id, om.duo_b_id)"),
                             ("_REPORT_FFA_SQL", "AND NOT fpx.absent")):
        assert needle in " ".join(getattr(main, src_name).split()), src_name


def test_ranked_series_envelope(session_ok):
    db = FakeDb()
    resp = _call(db, CALLER, series=SERIES)
    assert _no_room_leak(resp), "a room-shaped value or key reached the envelope"
    assert resp["v"] == 1 and resp["kind"] == "ranked"
    assert resp["truncated"] is False and resp["games_omitted"] == 0
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
                           {"t": None, "id": CALLER, "card": "Barrage"}], "pick order, no rolled key in 1v1"
    assert "picks_capped" not in g1
    assert g1["end_build"] == {CALLER: ["BombsAway", "Barrage"], OPP: ["Leach"]}
    assert g1["end_stats"] == {CALLER: END_STATS, OPP: END_STATS}
    assert g1["totals"] == {
        CALLER: {"shots": 30, "hits": 15, "blocks": 6, "blocks_ok": 4, "keys": 500,
                 "damage": 250, "deaths": 1, "active_s": 100.5},
        OPP: {"shots": 36, "hits": 10, "blocks": 3, "blocks_ok": 1, "keys": 400,
              "damage": 120, "deaths": 2, "active_s": 90.0}}
    # game 2 was reported with the players swapped: still keyed by steam id
    assert resp["games"][1]["scores"] == {OPP: 2, CALLER: 1}
    # set_summary ONCE per set, from the series row + the linked snapshot
    ss = resp["set_summary"]
    assert ss["rating"] == {CALLER: {"before": 1500.0, "after": 1512.5, "delta": 12.5},
                            OPP: {"before": 1500.0, "after": 1487.5, "delta": -12.5}}
    assert ss["gold"] == {CALLER: 12, OPP: 4}
    assert db.count("FROM gold_transactions gt") == 1
    assert db.count("FROM rating_history rh") == 1
    assert db.count("FROM matches m") == 1, "one games statement per set, not one per game"


def test_session_uuid_groups_only_the_callers_games_with_one_roster(session_ok):
    """The uuid is a client-chosen label. Under SESSION the fixture holds A vs
    B twice, A vs C once and X vs Y once: A's report is A-vs-B only (the
    roster of A's newest game), the A-vs-C game is counted as omitted, and
    the X/Y game is not in the set at all."""
    db = FakeDb()
    resp = _call(db, CALLER, session=SESSION)
    assert _no_room_leak(resp)
    assert resp["kind"] == "casual"
    assert [g["match_id"] for g in resp["games"]] == [C1, C2]
    assert [p["id"] for p in resp["players"]] == [CALLER, OPP]
    assert resp["games_omitted"] == 1 and resp["truncated"] is True, "the A-vs-C game is omitted, and said so"
    stmt, params = next((s, p) for s, p in db.statements if "FROM matches m" in s)
    assert "m.session_uuid = CAST(:key AS uuid)" in stmt and params["key"] == SESSION
    assert params["cpid"] == PID_A
    blob = json.dumps(resp)
    assert XSTEAM not in blob and YSTEAM not in blob and "Xavier" not in blob and X1 not in blob
    assert OTHER not in blob and "Bystander" not in blob and CX not in blob
    # no rating on a casual sitting; gold is the per-game ledger fetched ONCE,
    # for the games SHOWN only (CX's 8 gold is not in this envelope)
    assert resp["set_summary"]["rating"] == {}
    assert resp["set_summary"]["gold"] == {CALLER: 7, OPP: 2}
    assert db.count("FROM gold_transactions gt") == 1
    assert db.count("FROM rating_history rh") == 0


def test_the_same_uuid_gives_the_other_pair_only_their_own_game(session_ok):
    resp = _call(FakeDb(), XSTEAM, session=SESSION)
    assert [g["match_id"] for g in resp["games"]] == [X1]
    assert {p["id"] for p in resp["players"]} == {XSTEAM, YSTEAM}
    assert resp["games_omitted"] == 0 and resp["truncated"] is False
    blob = json.dumps(resp)
    for absent in (CALLER, OPP, OTHER, "Spirit", "Dopex", "Bystander", C1, C2, CX):
        assert absent not in blob
    # C played exactly one game under the uuid: a one-game report, nothing of A-vs-B
    resp_c = _call(FakeDb(), OTHER, session=SESSION)
    assert [g["match_id"] for g in resp_c["games"]] == [CX]
    assert {p["id"] for p in resp_c["players"]} == {CALLER, OTHER}
    assert OPP not in json.dumps(resp_c)


# ── Sept 8 item 5: the sitting selector and the head flag ──────────────

S1, S2, S3, S4, S5 = (str(uuid.uuid4()) for _ in range(5))


def _sitting_world():
    """A's day, minutes after T0: A-B at 0 and 100, A-C at 200 (A stays active),
    A-B at 330 (230 min after the previous A-B game - only the A-C game keeps
    A's sitting alive), a break, then A-B at 560 (a new sitting for A). For B
    the 100 -> 330 gap is 230 min, so B's sitting at 330 holds that game alone."""
    return [
        match_row(S1, PID_A, PID_B, minute=0, ranked=False),
        match_row(S2, PID_B, PID_A, minute=100, ranked=True),
        match_row(S3, PID_A, PID_C, minute=200, ranked=False),
        match_row(S4, PID_A, PID_B, minute=330, ranked=False),
        match_row(S5, PID_A, PID_B, minute=560, ranked=False),
    ]


def test_sitting_selector_groups_the_pair_across_other_opponents_until_a_gap(session_ok):
    db = FakeDb(matches=_sitting_world())
    resp = _call(db, CALLER, sitting=S4)
    assert _no_room_leak(resp)
    assert [g["match_id"] for g in resp["games"]] == [S1, S2, S4], \
        "oldest first; the A-C game bridged A's sitting but is not a pair game, so it is not in the set"
    assert [p["id"] for p in resp["players"]] == [CALLER, OPP]
    assert resp["games_omitted"] == 0 and resp["truncated"] is False
    assert resp["kind"] == "casual", "one ranked game among casual ones: the session rule"
    stmt, params = next((s, p) for s, p in db.statements if "FROM matches m" in s)
    assert "anchor AS (" in stmt and params["key"] == S4 and params["cpid"] == PID_A
    assert "m.invalidated_at IS NULL" in stmt
    blob = json.dumps(resp)
    assert OTHER not in blob and "Bystander" not in blob and S3 not in blob and S5 not in blob
    # the summary follows the session rules: no rating, per-game gold only
    assert resp["set_summary"]["rating"] == {}
    assert db.count("FROM rating_history rh") == 0

    # after the break the pair's next game is a sitting of its own
    resp2 = _call(FakeDb(matches=_sitting_world()), CALLER, sitting=S5)
    assert [g["match_id"] for g in resp2["games"]] == [S5]

    # the sitting is the CALLER's: for B the 100 -> 330 gap split it, so B's
    # report on the same anchor holds that game alone (no foreign data either way)
    resp_b = _call(FakeDb(matches=_sitting_world()), OPP, sitting=S4)
    assert [g["match_id"] for g in resp_b["games"]] == [S4]
    assert {p["id"] for p in resp_b["players"]} == {CALLER, OPP}


def test_sitting_anchor_must_be_a_valid_game_of_the_caller(session_ok):
    with pytest.raises(HTTPException) as ei:
        _call(FakeDb(matches=_sitting_world()), OTHER, sitting=S4)
    assert ei.value.status_code == 404
    world = _sitting_world()
    world[3]["invalidated_at"] = T0
    with pytest.raises(HTTPException) as ei:
        _call(FakeDb(matches=world), CALLER, sitting=S4)
    assert ei.value.status_code == 404
    with pytest.raises(HTTPException) as ei:
        _call(FakeDb(matches=_sitting_world()), CALLER, sitting=S4, session=SESSION)
    assert ei.value.status_code == 400, "one selector at a time, sitting included"


def test_sitting_gap_is_the_clients_session_window():
    """Both halves of the contract carry the same literal (#341/#152): the
    server's gap and the client's SESSION_INACTIVITY_HOURS (My Stats Session Info)."""
    src = (PLUGIN / "GameStateWatcher.cs").read_text(encoding="utf-8")
    m = re.search(r"SESSION_INACTIVITY_HOURS\s*=\s*([0-9.]+)", src)
    assert m, "the client's session window constant moved"
    assert float(m.group(1)) == float(main.SITTING_GAP_HOURS)
    assert f"make_interval(hours => {main.SITTING_GAP_HOURS})" in main._SITTING_CTES
    assert "|| " not in main._SITTING_CTES and "::interval" not in main._SITTING_CTES, \
        "the gap must stay a typed make_interval (#275/#448)"


def test_sitting_ctes_count_every_mode_and_never_a_ghost_or_an_invalid_game():
    ctes = main._SITTING_CTES
    for src in ("FROM matches m", "FROM team_matches t", "FROM ovt_matches o", "FROM ffa_matches f"):
        assert src in ctes, src
    assert "NOT fp.absent" in ctes, "an absent FFA seat is not activity"
    assert ctes.count("invalidated_at IS NULL") == 4, "every mode excludes invalidated games"
    assert ctes.count("CAST({pid} AS uuid)") == 4 and "{pid}" not in main._sitting_ctes(":pid")
    assert "LATERAL" not in ctes.upper()
    for bad in ("photon_room", "room_id", "room_name"):
        assert bad not in ctes.lower() and bad not in main._REPORT_1V1_WHERE["sitting"].lower()
    history = inspect.getsource(main.get_player_matches)
    assert "LEFT JOIN sit ON sit.ended_at = m.ended_at" in history, \
        "an inner join would drop invalidated rows (not in acts) from the history"
    assert "PARTITION BY sit.sn," in history and "AS sitting_head" in history
    assert "CASE WHEN m.player1_id = :pid THEN m.player2_id ELSE m.player1_id END" in history
    assert "m.is_ranked, (m.invalidated_at IS NULL)" in history
    assert "(m.invalidated_at IS NULL AND ROW_NUMBER() OVER (" in history
    assert 'sitting_head=bool(row["sitting_head"])' in history
    assert MatchHistoryEntry.model_fields["sitting_head"].default is False, \
        "additive: an older server's rows (no field) read as not-a-head"
    assert MatchHistoryEntry.model_fields["sitting_head"].annotation is bool


def test_the_plugin_consumes_the_head_flag_and_nothing_else_arms_a_session_button():
    api = (PLUGIN / "ApiClient.cs").read_text(encoding="utf-8")
    assert 'selector != "sitting"' in api, "the report fetch must let the sitting selector through"
    assert 'entry.sitting_head = chunk.Contains("\\"sitting_head\\":true")' in api
    ui = (PLUGIN / "NativeUI.cs").read_text(encoding="utf-8")
    assert 'SetSessionButton(casualRows[ri],"sitting",casual[i].match_id)' in ui
    assert 'SetSessionButton(rankedRows[ri],"sitting",m.match_id)' in ui
    assert 'SetSessionButton(rankedRows[ri],"sitting",first.match_id)' in ui
    # zero survivors of the per-series / per-session-uuid arming
    for gone in ('hasSes?"session":"match"', 'SetSessionButton(rankedRows[firstRi],"series"',
                 'SetSessionButton(rankedRows[ri],"match"'):
        assert gone not in ui, gone
    assert "sesSlot.transform.SetSiblingIndex(1);" in ui, "ID, Session, then W/L + score"


def test_control_roster_rule_is_what_drops_the_foreign_roster(session_ok, monkeypatch):
    """Negative control (#391): with the consistency rule disabled, the
    A-vs-C game rides along under the uuid — so the assertion above is
    load-bearing, not decoration."""
    monkeypatch.setattr(main, "_report_consistent", lambda games, anchor: (games, 0))
    resp = _call(FakeDb(), CALLER, session=SESSION)
    assert CX in [g["match_id"] for g in resp["games"]]


def test_match_selector_single_game(session_ok):
    resp = _call(FakeDb(), CALLER, match=M1)
    assert resp["kind"] == "ranked" and [g["match_id"] for g in resp["games"]] == [M1]
    assert resp["set_summary"]["rating"] == {}, "a one-game view carries no series rating"
    assert resp["set_summary"]["gold"] == {CALLER: 5}
    resp2 = _call(FakeDb(), CALLER, match=C3)
    assert resp2["kind"] == "casual" and resp2["set_summary"]["gold"] == {CALLER: 9}
    # X asking for A's game by id: not a participant, same 404 as a missing id
    with pytest.raises(HTTPException) as ei:
        _call(FakeDb(), XSTEAM, match=M1)
    assert ei.value.status_code == 404 and ei.value.detail == "not_found"


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
    db = FakeDb()
    resp = _call(db, CALLER, series=TEAM_SERIES)
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
    params = next(p for s, p in db.statements if "FROM team_matches tm" in s)
    assert params["cpid"] == PID_A
    # X is not on either team: the 2v2 loader's predicate returns nothing -> 404
    with pytest.raises(HTTPException) as ei:
        _call(FakeDb(), XSTEAM, series=TEAM_SERIES)
    assert ei.value.status_code == 404


def test_ffa_match_path_excludes_the_absent_ghost(session_ok):
    """HIGH 2: an `absent` roster row is not a participant. The ghost is not a
    player of the envelope, not a slot, not telemetry — and the ghost's own
    verified session cannot open the game it did not play."""
    db = FakeDb()
    resp = _call(db, CALLER, match=FFA1)
    assert _no_room_leak(resp)
    assert resp["kind"] == "ffa"
    assert [p["id"] for p in resp["players"]] == [CALLER, OPP]
    blob = json.dumps(resp)
    assert GHOST not in blob and "Ghost" not in blob, "the ghost is nowhere in the envelope"
    colors = {p["id"]: p["color"] for p in resp["players"]}
    assert colors[CALLER] == "#FF8800" and colors[OPP].startswith("#")
    g = resp["games"][0]
    assert g["scores"] == {CALLER: 5, OPP: 3}
    assert set(g["timelines"].keys()) == {CALLER, OPP}
    assert set(g["end_build"].keys()) == {CALLER, OPP}
    assert resp["set_summary"]["rating"] == {CALLER: {"before": 1500.0, "after": 1520.0, "delta": 20.0},
                                             OPP: {"before": 1500.0, "after": 1490.0, "delta": -10.0}}
    assert resp["set_summary"]["gold"] == {CALLER: 30, OPP: 10}
    stmt = next(s for s, _ in db.statements if "FROM ffa_match_players fp WHERE" in s)
    assert "AND NOT fp.absent" in stmt
    # the ghost's verified session + the game id: same 404 as a stranger
    for who in (GHOST, OTHER):
        with pytest.raises(HTTPException) as ei:
            _call(FakeDb(), who, match=FFA1)
        assert ei.value.status_code == 404 and ei.value.detail == "not_found", who


def test_control_absent_flag_is_what_excludes_the_ghost(session_ok):
    """Negative control (#391): the identical roster row with absent=false IS
    a participant — the predicate decides, not the tallies."""
    played = [dict(p, absent=False) for p in FFA_PLAYERS]
    resp = _call(FakeDb(ffa_players=played), GHOST, match=FFA1)
    assert resp["kind"] == "ffa" and GHOST in {p["id"] for p in resp["players"]}


def test_envelope_carries_the_room_rules_record(session_ok):
    """Migration 306: every game carries the record it was played under, read
    from the ONE games statement per set (no second lookup): `rules` from the
    series row for 1v1 / 2v2 / 1v2 — null for a series born before the record
    or a casual game with no series — and `settings` for FFA from the lobby
    (null when the lobby predates configurable settings)."""
    rec = {"ff": False, "sc": True, "src": "prefs"}
    db = FakeDb(matches=[match_row(M1, PID_A, PID_B, minute=0, series_id=SERIES, rules=rec),
                         match_row(M2, PID_B, PID_A, minute=5, series_id=SERIES)])
    resp = _call(db, CALLER, series=SERIES)
    by_id = {g["match_id"]: g for g in resp["games"]}
    assert by_id[M1]["rules"] == {"ff": False, "sc": True}, "the src tag is not a history fact"
    assert by_id[M2]["rules"] is None
    assert all("settings" not in g for g in resp["games"])
    assert db.count("FROM matches m") == 1, "the record rides the games statement, no second lookup"
    assert "LEFT JOIN ranked_series rs ON rs.id = m.series_id" in next(
        s for s, _ in db.statements if "FROM matches m" in s)

    resp = _call(FakeDb(), CALLER, match=FFA1)
    assert resp["games"][0]["settings"] is None and "rules" not in resp["games"][0]
    resp = _call(FakeDb(ffa_match=FFA_SETTINGS_ROW), CALLER, match=FFA1)
    assert resp["games"][0]["settings"] == {
        "score_target": 7, "card_cap": 5, "initial_picks": 1, "card_candidates": 5,
        "same_card_rule": True, "sudden_death": False}
    assert "LEFT JOIN ffa_lobbies l ON l.id = fm.lobby_id" in " ".join(main._REPORT_FFA_SQL.split())

    resp = _call(FakeDb(), CALLER, series=TEAM_SERIES)
    assert all(g["rules"] is None for g in resp["games"]) and resp["games"]
    assert "LEFT JOIN team_series ts ON ts.id = tm.series_id" in " ".join(main._REPORT_TEAM_SQL.split())
    assert "LEFT JOIN ovt_series os ON os.id = om.series_id" in " ".join(main._REPORT_OVT_SQL.split())
    assert "os.solo_extra_pick AS solo_extra_pick" in main._REPORT_OVT_SQL


def test_ffa_envelope_carries_stored_damage_kills_and_score(session_ok):
    """MEDIUM: the FFA row's stored telemetry reaches the same envelope shape
    1v1 uses — `available` names it, the DPS source stream exists, totals
    carry damage, and the match row's half-point list becomes each player's
    score race (half points as .5, index-stamped over the duration)."""
    resp = _call(FakeDb(), CALLER, match=FFA1)
    g = resp["games"][0]
    assert g["available"] == ["blocks", "blocks_ok", "damage", "fps", "hits", "kills", "ping", "score", "shots"]
    tl = g["timelines"][CALLER]
    assert tl["damage"] == [[133.3, 0], [266.7, 400], [400.0, 900]]
    assert tl["kills"] == [[133.3, 0], [266.7, 2], [400.0, 4]]
    assert tl["score"] == [[66.7, 0.5], [133.3, 1.0], [200.0, 1.0], [266.7, 1.0], [333.3, 1.5], [400.0, 2.0]]
    assert g["timelines"][OPP]["score"] == [[66.7, 0.0], [133.3, 0.0], [200.0, 0.5], [266.7, 1.0], [333.3, 1.0], [400.0, 1.0]]
    assert g["timelines"][OPP].keys() == {"score"}, "B recorded nothing else — no fake streams"
    assert g["totals"] == {CALLER: {"shots": 8, "hits": 3, "blocks": 2, "blocks_ok": 2, "keys": 50,
                                    "damage": 900, "kills": 4, "active_s": 300.0},
                           OPP: {"kills": 1}}


def test_ffa_rolled_pick_is_a_pick_but_not_part_of_the_end_build(session_ok):
    resp = _call(FakeDb(), CALLER, match=FFA1)
    g = resp["games"][0]
    assert g["picks"] == [{"t": None, "id": CALLER, "card": "Alpha", "rolled": True},
                          {"t": None, "id": CALLER, "card": "Beta"},
                          {"t": None, "id": CALLER, "card": "Gamma"}], "the ghost's pick is not here either"
    assert g["end_build"] == {CALLER: ["Beta", "Gamma"], OPP: []}
    # negative control: the same card with rolled=false is in the build
    unrolled = [dict(c, rolled=False) for c in FFA_CARDS]
    resp2 = _call(FakeDb(ffa_cards=unrolled), CALLER, match=FFA1)
    assert resp2["games"][0]["end_build"][CALLER] == ["Alpha", "Beta", "Gamma"]
    assert all("rolled" not in p for p in resp2["games"][0]["picks"])


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


# ── the rating snapshot: identity, not a window ──────────────────────────────

def test_rating_snapshot_is_joined_by_series_identity(session_ok):
    """MEDIUM: the fixture holds an EARLIER unlinked snapshot (1499, inside the
    old 60 s window) and a LATER one linked to A's next series (1600, 30 s
    after). Only the snapshot linked to THIS series is the answer."""
    db = FakeDb()
    resp = _call(db, CALLER, series=SERIES)
    assert resp["set_summary"]["rating"][CALLER] == {"before": 1500.0, "after": 1512.5, "delta": 12.5}
    stmt, params = next((s, p) for s, p in db.statements if "FROM rating_history rh" in s)
    assert "rh.series_id = CAST(:key AS uuid)" in stmt and params["key"] == SERIES
    assert set(params["pids"]) == {PID_A, PID_B}
    assert "make_interval" not in stmt and "completed_at" not in stmt and "t0" not in params
    # negative control (#391): the OLD rule — earliest snapshot within
    # [completed_at - 60 s, completed_at + 10 min] — lands on the decoy, so
    # the fixture can tell the two mechanisms apart
    t0 = SERIES_ROW["completed_at"]
    window = sorted((r for r in RATING_HISTORY if r["player_id"] == PID_A
                     and t0 - timedelta(seconds=60) <= r["period_end"] <= t0 + timedelta(minutes=10)),
                    key=lambda r: r["period_end"])
    assert window[0]["rating"] == 1499.0


def test_rating_lookup_degrades_to_delta_only_when_the_column_is_missing(session_ok):
    """#235: the identity join runs under a savepoint, so a box whose schema
    predates migration 299 answers the report with before/after null and the
    authoritative delta, instead of a 500."""
    resp = _call(FakeDb(fail_rating=True), CALLER, series=SERIES)
    assert resp["set_summary"]["rating"] == {CALLER: {"before": None, "after": None, "delta": 12.5},
                                             OPP: {"before": None, "after": None, "delta": -12.5}}
    assert resp["set_summary"]["gold"] == {CALLER: 12, OPP: 4}, "the rest of the summary is intact"
    src = inspect.getsource(main._report_rating_after)
    assert "begin_nested" in src


def test_series_completion_links_its_snapshots_to_the_series():
    """The writer half of the identity: the Glicko update stamps the two
    snapshots it just added with the series id, by raw SQL under a savepoint
    (the column is deliberately not on the model — a pre-299 box keeps the
    rating update and skips the link)."""
    submit = inspect.getsource(main.submit_match)
    assert submit.count("_RATING_HISTORY_LINK_SQL") == 1
    link = " ".join(main._RATING_HISTORY_LINK_SQL.split())
    assert link == ("UPDATE rating_history SET series_id = CAST(:sid AS uuid) "
                    "WHERE id = ANY(CAST(:ids AS uuid[]))"), "typed binds (#275/#448), ids only"
    # the link sits in a savepoint AFTER the snapshots exist, keyed on the ids
    # the writer chose itself
    i_add = submit.index("db.add(RatingHistory(")
    i_link = submit.index("_RATING_HISTORY_LINK_SQL")
    assert i_add < i_link
    between = submit[i_add:i_link]
    assert "id=snapshot_id" in between and "await db.flush()" in between and "begin_nested()" in between
    assert '{"sid": str(series.id), "ids": snapshot_ids}' in submit
    from models import RatingHistory
    assert "series_id" not in RatingHistory.__table__.columns, \
        "NOT declared on purpose: an ORM column would ride every INSERT before 299 lands (#477)"


def test_migration_299_shape():
    path = SQL_DIR / "299_rating_history_series_id.sql"
    sql = path.read_text(encoding="utf-8")
    body = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    assert body.strip().startswith("BEGIN;") and body.strip().endswith("COMMIT;")
    assert "ALTER TABLE rating_history ADD COLUMN IF NOT EXISTS series_id UUID;" in body
    assert "CREATE INDEX IF NOT EXISTS idx_rating_history_series" in body
    assert "WHERE rh.series_id IS NULL" in body, "the backfill touches unlinked rows only (#168)"
    assert "LATERAL" not in body.upper()
    assert body.count("rs.status = 'completed'") == 2 and body.count("rs.invalidated_at IS NULL") == 2
    assert "UNION ALL" in body, "one row per (series, player): an equality join, not an OR"
    assert "ORDER BY s.completed_at DESC, s.series_id) AS rn" in body, "deterministic numbering"
    assert "COUNT(*) OVER (PARTITION BY rh.id, s.completed_at) AS same_instant" in body
    assert "AND cand.same_instant = 1;" in body, "a same-instant tie stays NULL instead of being guessed (r2)"
    assert "s.completed_at <= rh.period_end" in body and "interval '10 minutes'" in body


def test_no_room_column_in_any_report_statement():
    """Static half of the pin: none of the envelope's statements or serialisers
    name a room column, so the runtime pin above is not the only guard."""
    sources = [getattr(main, n) for n in dir(main) if n.startswith("_REPORT_") and n.endswith("_SQL")]
    sources += [inspect.getsource(main.get_set_report), inspect.getsource(main._report_game_json),
                inspect.getsource(main._report_totals), inspect.getsource(main._report_slot),
                inspect.getsource(main._report_load_1v1), inspect.getsource(main._report_load_team),
                inspect.getsource(main._report_load_ovt), inspect.getsource(main._report_load_ffa),
                inspect.getsource(main._report_ffa_scores), inspect.getsource(main._report_consistent),
                inspect.getsource(main._report_roster)]
    assert len(sources) >= 14
    for src in sources:
        low = src.lower()
        for bad in ("photon_room", "room_id", "room_name", "select *", "select m.*"):
            assert bad not in low, bad


# ── the byte bound ───────────────────────────────────────────────────────────

def _big_stream(n, scale):
    return ",".join(str(i * scale) for i in range(n))


def _big_pairs(n, scale):
    return ",".join(f"{i * scale}:{i * scale // 2}" for i in range(n))


BIG_SESSION = str(uuid.uuid4())
BIG_END_STATS = "1|" + "|".join(["1234567.123"] * 21)
LONG_NAME = "N" * 40


def _worst_1v1_world(n_games=30, card_prefix=None):
    """30 casual games under one uuid (the envelope keeps 24), every stream
    300 samples of six-digit values, 200 point events, 400 cards each with
    40-character names, maximal end stats and long display names."""
    matches, cards = [], []
    for i in range(n_games):
        mid = str(uuid.uuid4())
        row = match_row(mid, PID_A, PID_B, minute=i * 3, ranked=False, session_uuid=BIG_SESSION, dur=3600)
        for side in ("p1", "p2"):
            row[f"{side}_fps_timeline"] = _big_stream(300, 333)
            row[f"{side}_ping_timeline"] = _big_stream(300, 333)
            row[f"{side}_damage_timeline"] = _big_stream(300, 3333)
            row[f"{side}_hit_timeline"] = _big_pairs(300, 3333)
            row[f"{side}_block_timeline"] = _big_pairs(300, 3333)
            row[f"{side}_end_stats"] = BIG_END_STATS
        row["point_times"] = ",".join(str(t * 18) for t in range(1, 201))
        row["point_timeline"] = ",".join(f"{(t + 1) // 2}:{t // 2}" for t in range(1, 201))
        matches.append(row)
        for k in range(400):
            for pid in (PID_A, PID_B):
                cards.append({"match_id": mid, "player_id": pid, "card_name": (f"{k:03d}" + card_prefix) if card_prefix else f"Card{k:03d}" + "x" * 60,
                              "pick_order": k + 1, "round_number": k, "rolled": False})
    players = [{"id": PID_A, "steam_id": CALLER, "display_name": LONG_NAME},
               {"id": PID_B, "steam_id": OPP, "display_name": LONG_NAME}]
    return FakeDb(matches=matches, cards=cards, players=players, gold=[])


def _worst_team_world():
    """24 2v2 games of one series, four players, every telemetry row 300
    samples, 400 cards each."""
    series = str(uuid.uuid4())
    team_row = dict(TEAM_SERIES_ROW, id=series, t1a_id=PID_A, t1b_id=PID_C, t2a_id=PID_B, t2b_id=PID_X)
    matches, tele = [], []
    for i in range(24):
        mid = str(uuid.uuid4())
        matches.append({"id": mid, "series_id": series, "started_at": T0 + timedelta(minutes=i * 5),
                        "ended_at": T0 + timedelta(minutes=i * 5, seconds=3600), "duration_s": 3600,
                        "invalidated_at": None, "t1a_id": PID_A, "t1b_id": PID_C, "t2a_id": PID_B, "t2b_id": PID_X,
                        "t1_rounds_won": 3, "t2_rounds_won": 2, "t1_points_total": 9, "t2_points_total": 8,
                        "t1a_end_stats": BIG_END_STATS, "t1b_end_stats": BIG_END_STATS,
                        "t2a_end_stats": BIG_END_STATS, "t2b_end_stats": BIG_END_STATS, **_room_cols()})
        for pid in (PID_A, PID_B, PID_C, PID_X):
            tele.append({"match_id": mid, "player_id": pid, "fps_timeline": _big_stream(300, 333),
                         "ping_timeline": _big_stream(300, 333), "hit_timeline": _big_pairs(300, 3333),
                         "block_timeline": _big_pairs(300, 3333), "damage_dealt_timeline": _big_stream(300, 3333),
                         "bullets_fired": 999999, "bullets_hit": 999999, "blocks_activated": 999999,
                         "blocks_successful": 999999, "keys_pressed": 9999999, "active_seconds": 3599.9})
    players = [{"id": p, "steam_id": s, "display_name": LONG_NAME}
               for p, s in ((PID_A, CALLER), (PID_B, OPP), (PID_C, OTHER), (PID_X, XSTEAM))]
    return FakeDb(team_series_row=team_row, team_matches=matches, team_tele=tele, players=players, gold=[]), series


def _worst_ffa_world(card_prefix=None):
    """One FFA game with the ten-player maximum, nine streams of 300 samples
    each, a 400-token half-point list and 400 cards per player."""
    pids = [PID_A] + [str(uuid.uuid4()) for _ in range(9)]
    steams = [CALLER] + [f"7656119800000010{i}" for i in range(9)]
    fps = []
    for slot, pid in enumerate(pids):
        fps.append(ffa_player(pid, slot, slot + 1, rounds_won=5 - min(slot, 5), points_total=5,
                              rating_before=1500.0, rating_after=1520.0, rating_change=20.0, gold_gained=30,
                              fps_timeline=_big_stream(300, 333), ping_timeline=_big_stream(300, 333),
                              hit_timeline=_big_pairs(300, 3333), block_timeline=_big_pairs(300, 3333),
                              damage_dealt_timeline=_big_stream(300, 3333), kill_timeline=_big_stream(300, 33),
                              damage_dealt=999999, end_stats=BIG_END_STATS, color_hex="#FF8800",
                              bullets_fired=999999, bullets_hit=999999, blocks_activated=999999,
                              blocks_successful=999999, keys_pressed=9999999, active_seconds=3599.9, kills=999))
    timeline = ",".join(f"{i % 10}{'R' if i % 3 == 0 else ''}" for i in range(400))
    ffa_match = dict(FFA_MATCH, duration_s=3600, timeline=timeline)
    cards = [{"match_id": FFA1, "player_id": pid, "card_name": (f"{k:03d}" + card_prefix) if card_prefix else f"Card{k:03d}" + "x" * 60,
              "pick_order": k + 1, "round_number": k, "rolled": k % 2 == 0}
             for pid in pids for k in range(400)]
    players = [{"id": p, "steam_id": s, "display_name": LONG_NAME} for p, s in zip(pids, steams)]
    return FakeDb(ffa_match=ffa_match, ffa_players=fps, ffa_cards=cards, players=players, gold=[])


def _pairs(resp):
    return sum(len(v) for g in resp["games"] for tls in g["timelines"].values() for v in tls.values())


def _picks(resp):
    return sum(len(g["picks"]) for g in resp["games"])


def test_envelope_stays_under_the_documented_bound_for_worst_case_shapes(session_ok):
    """MEDIUM (size): the bound is a literal here on purpose — widening a cap
    in main.py must fail THIS line, not move it (#391)."""
    assert main._REPORT_MAX_BYTES == 512 * 1024
    assert main._REPORT_MAX_GAMES == 24
    assert main._REPORT_SAMPLE_PAIRS_BUDGET == 12288 and main._REPORT_SAMPLES_MAX == 128 and main._REPORT_SAMPLES_MIN == 16
    assert main._REPORT_CARD_BUDGET == 1024 and main._REPORT_CARDS_MAX == 32 and main._REPORT_CARDS_MIN == 8
    assert main._REPORT_DEATHS_MAX == 48 and main._REPORT_CARD_NAME_MAX == 40 and main._REPORT_NAME_MAX == 32

    # 1v1: 30 games in the sitting, 24 shown, 6 omitted and said so
    resp = _call(_worst_1v1_world(), CALLER, session=BIG_SESSION)
    assert len(resp["games"]) == 24 and resp["games_omitted"] == 6 and resp["truncated"] is True
    size_1v1 = _wire_bytes(resp)
    assert size_1v1 <= main._REPORT_MAX_BYTES, size_1v1
    assert _pairs(resp) <= main._REPORT_SAMPLE_PAIRS_BUDGET
    assert _picks(resp) <= main._REPORT_CARD_BUDGET
    for g in resp["games"]:
        assert g["picks_capped"] is True
        assert len(g["deaths"]) <= main._REPORT_DEATHS_MAX
        for tls in g["timelines"].values():
            for name, v in tls.items():
                assert len(v) <= 32, (name, len(v))          # 12288 // (24 x 2 x 8)
                assert v[-1][0] == 3600.0, "decimation keeps the last sample (#318)"
        for cards in g["end_build"].values():
            assert len(cards) <= main._REPORT_CARDS_MAX and all(len(c) <= 40 for c in cards)
    assert all(len(p["name"]) <= main._REPORT_NAME_MAX for p in resp["players"])
    # the oldest picks are the ones dropped: the newest card is still there
    assert resp["games"][0]["end_build"][CALLER][-1].startswith("Card399")

    # 2v2: 24 games, four players — the per-stream cap floors at 16
    db, series = _worst_team_world()
    resp_t = _call(db, CALLER, series=series)
    assert len(resp_t["games"]) == 24
    size_team = _wire_bytes(resp_t)
    assert size_team <= main._REPORT_MAX_BYTES, size_team
    assert _pairs(resp_t) <= main._REPORT_SAMPLE_PAIRS_BUDGET and _picks(resp_t) <= main._REPORT_CARD_BUDGET

    # FFA: ten players, one game — every stream keeps its full 128
    resp_f = _call(_worst_ffa_world(), CALLER, match=FFA1)
    assert len(resp_f["players"]) == 10
    size_ffa = _wire_bytes(resp_f)
    assert size_ffa <= main._REPORT_MAX_BYTES, size_ffa
    assert _pairs(resp_f) <= main._REPORT_SAMPLE_PAIRS_BUDGET and _picks(resp_f) <= main._REPORT_CARD_BUDGET
    assert max(len(v) for tls in resp_f["games"][0]["timelines"].values() for v in tls.values()) == 128


def test_control_without_the_caps_the_same_world_breaks_the_bound(session_ok, monkeypatch):
    """Negative control (#391): lift the budgets and the identical fixture
    serialises far past the bound BEFORE the fit step — the caps are what
    size it. With the fit step in place even the uncapped world fits, because
    the fit is the guarantee and the caps are the sizing (r2)."""
    monkeypatch.setattr(main, "_REPORT_SAMPLES_MIN", 10 ** 6)
    monkeypatch.setattr(main, "_REPORT_SAMPLES_MAX", 10 ** 6)
    monkeypatch.setattr(main, "_REPORT_CARDS_MIN", 10 ** 6)
    monkeypatch.setattr(main, "_REPORT_CARDS_MAX", 10 ** 6)
    monkeypatch.setattr(main, "_REPORT_DEATHS_MAX", 10 ** 6)
    fitted = _call(_worst_1v1_world(), CALLER, session=BIG_SESSION)
    assert _wire_bytes(fitted) <= main._REPORT_MAX_BYTES and fitted["truncated"] is True, _wire_bytes(fitted)
    monkeypatch.setattr(main, "_report_fit", lambda env: env)
    resp = _call(_worst_1v1_world(), CALLER, session=BIG_SESSION)
    assert _wire_bytes(resp) > 2 * main._REPORT_MAX_BYTES
    assert _pairs(resp) > main._REPORT_SAMPLE_PAIRS_BUDGET and _picks(resp) > main._REPORT_CARD_BUDGET


# ── helpers ──────────────────────────────────────────────────────────────────

def test_samples_are_index_stamped_over_the_duration():
    assert main._report_samples("0,100,250", 120) == [[40.0, 0], [80.0, 100], [120.0, 250]]
    assert main._report_samples("10:4,20:9", 90, 0) == [[45.0, 10], [90.0, 20]]
    assert main._report_samples("10:4,20:9", 90, 1) == [[45.0, 4], [90.0, 9]]
    assert main._report_samples("5,x,7", 30) == [[10.0, 5], [30.0, 7]], "malformed token skipped, index kept"
    assert main._report_samples("", 120) is None
    assert main._report_samples(None, 120) is None
    assert main._report_samples("1,2,3", 0) is None, "no duration -> no timeline, never a fake grid"


def test_decimation_keeps_first_and_last_and_the_true_positions():
    pairs = [[float(i + 1), i * 10] for i in range(300)]
    out = main._report_decimate(pairs, 32)
    assert len(out) == 32 and out[0] == [1.0, 0] and out[-1] == [300.0, 2990]
    assert all(out[i][0] < out[i + 1][0] for i in range(len(out) - 1))
    assert main._report_decimate(pairs[:5], 32) == pairs[:5], "short series untouched"
    assert main._report_samples(_big_stream(300, 1), 3000, cap=32)[-1] == [3000.0, 299]
    # the caps derive from the report's shape
    assert main._report_sample_cap(1, 2) == 128 and main._report_sample_cap(6, 2) == 128
    assert main._report_sample_cap(12, 2) == 64 and main._report_sample_cap(24, 2) == 32
    assert main._report_sample_cap(24, 4) == 16 and main._report_sample_cap(1, 10) == 128
    assert main._report_card_cap(1, 2) == 32 and main._report_card_cap(24, 2) == 21
    assert main._report_card_cap(24, 4) == 10 and main._report_card_cap(1, 10) == 32


def test_points_become_scores_and_deaths():
    sa, sb, deaths = main._report_points("12,47,89", "1:0,1:1,2:1", "A", "B")
    assert sa == [[12.0, 1], [47.0, 1], [89.0, 2]] and sb == [[12.0, 0], [47.0, 1], [89.0, 1]]
    assert deaths == [{"t": 12.0, "id": "B"}, {"t": 47.0, "id": "A"}, {"t": 89.0, "id": "B"}]
    assert main._report_points(None, "1:0", "A", "B") == (None, None, [])
    assert main._report_points("12", None, "A", "B") == (None, None, [])
    times = ",".join(str(t) for t in range(1, 101))
    totals = ",".join(f"{t}:0" for t in range(1, 101))
    sa, _sb, deaths = main._report_points(times, totals, "A", "B")
    assert len(deaths) == main._REPORT_DEATHS_MAX and len(sa) == 100


def test_ffa_half_point_grammar():
    out = main._report_ffa_scores("0,0R,1,1R,0,0RG", [0, 1], 400)
    assert out[0] == [[66.7, 0.5], [133.3, 1.0], [200.0, 1.0], [266.7, 1.0], [333.3, 1.5], [400.0, 2.0]]
    assert out[1] == [[66.7, 0.0], [133.3, 0.0], [200.0, 0.5], [266.7, 1.0], [333.3, 1.0], [400.0, 1.0]]
    assert main._report_ffa_scores("0,0R", [0, 1], 0) == {}, "no duration -> no timeline"
    assert main._report_ffa_scores("", [0], 100) == {}
    assert main._report_ffa_scores("7,7R", [0, 1], 100) == {}, "events of an unknown slot are ignored"
    assert main._report_ffa_scores("x,0R", [0], 100)[0] == [[100.0, 1.0]]


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


# ── the plugin's half (source pins, structure read on a mask) ────────────────

def _cs_body(path, signature):
    spans = list(method_spans(path, signature))
    assert spans, f"signature not found: {signature}"
    open_brace, end = spans[0]
    return strip_comments_only(path.read_text(encoding="utf-8")[open_brace:end])


def test_cs_pin_helper_ignores_prose():
    """Negative control for the pins below: a needle that lives only in a
    comment does not satisfy them."""
    body = _cs_body(PLUGIN / "SessionReportView.cs", "private static string ErrorMessage(string raw)")
    assert "ErrorMessage" not in body or "I18n.Tr(" in body
    assert "//" not in body.replace("://", "")


def test_the_1v2_history_rows_carry_a_session_control():
    """MEDIUM: the Recent 1v2 Games rows open the series report through the
    shared opener, the binding is read from an index-aligned list at click
    time (#265), that list is cleared with the row pools on rebuild, and the
    control is armed only for a seat of the series."""
    src = PLUGIN / "NativeUI.cs"
    refresh = _cs_body(src, "private static void RefreshOvtRecent()")
    assert 'OpenSessionReport("series"' in refresh
    assert "ovtRecentSessionKeys" in refresh and "ovtRecentSessionBtns" in refresh
    assert "MatchTracker.LocalSteamId" in refresh
    assert refresh.count("!string.IsNullOrEmpty(s.series_id)") == 1, "an empty series id disarms the control (r2 mutation pin)"
    assert "solo_steam" in refresh and "duo_a_steam" in refresh and "duo_b_steam" in refresh
    assert 'I18n.Tr("Session")' in refresh
    build = _cs_body(src, "private static void BuildPage(Transform canvasParent)")
    assert "ovtRecentSessionKeys.Clear()" in build and "ovtRecentSessionBtns.Clear()" in build
    assert "ovtRecentRows.Clear()" in build


def test_the_builds_page_continues_instead_of_discarding_rows():
    """MEDIUM: page 4 paginates its build rows (4, 4b, 4c ...) inside the
    view's existing pager — the page count is dynamic and every key/footer
    path reads it; nothing is silently dropped."""
    src = PLUGIN / "SessionReportView.cs"
    whole = strip_comments_only(src.read_text(encoding="utf-8"))
    assert "SessionReportModel.PAGE_COUNT" not in whole, "the fixed page count is gone"
    assert "PageCount()" in _cs_body(src, "private static void HandleKey(Event ev)")
    assert "PageCount()" in _cs_body(src, "private static void DrawFooter(Rect r)")
    builds = _cs_body(src, "private static void DrawBuilds(Rect body, SessionReportModel.Model m, int sub)")
    assert "buildPages" in builds and "sub" in builds
    assert "showing {0} of {1}" not in builds, "the discard notice is gone with the discard"
    measure = _cs_body(src, "private static void MeasureBuildPages(Rect body, SessionReportModel.Model m)")
    assert measure.count("buildStarts.Add(i)") == 1, "the page break is recorded exactly once in the method (#284)"
    assert "blockH[" in builds and "blockH.Add(" in measure, "the draw path pages with the heights it measured"
    model = PLUGIN / "SessionReportModel.cs"
    assert "FIXED_PAGES = 3" in strip_comments_only(model.read_text(encoding="utf-8"))


def test_dividers_and_diagnostics_are_translated():
    """LOWs: multiplayer dividers carry the recorded score through the
    catalogue; the view's visible diagnostics are short codes routed through
    I18n and the raw tail goes to the log."""
    model = PLUGIN / "SessionReportModel.cs"
    build = _cs_body(model, "internal static Model Build(Envelope env)")
    assert '"G" + gi.ToString(INV)' not in build, "the bare untranslated G<n> is gone"
    assert "TeamScoreLabel(" in build and "FfaScoreLabel(" in build
    team = _cs_body(model, "private static string TeamScoreLabel(Model m, Game g, int gi, bool longForm)")
    assert "I18n.TrF(" in team
    ffa = _cs_body(model, "private static string FfaScoreLabel(Model m, Game g, int gi, bool longForm)")
    assert "I18n.TrF(" in ffa
    # rolled picks: parsed, and kept out of the build list
    parse = _cs_body(model, "private static Game ParseGame(string obj)")
    assert '"rolled"' in parse and "pk.Rolled" in parse
    assert "Rolled" in build and "GamesOmitted" in build
    view = PLUGIN / "SessionReportView.cs"
    whole = strip_comments_only(view.read_text(encoding="utf-8"))
    for gone in ('"local: "', '"model: "', 'errorText = "parse"'):
        assert gone not in whole, gone
    err = _cs_body(view, "private static string ErrorMessage(string raw)")
    assert "ERR_LOCAL" in err and "ERR_PARSE" in err and "ERR_MODEL" in err
    assert "Substring(0, 90)" not in err, "no raw error tail on the label"
    assert err.count("I18n.Tr") >= 6
    fetched = _cs_body(view, "private static void OnFetched(int g, bool ok, string body)")
    assert "Plugin.Log.LogWarning" in fetched and "ERR_" in fetched


def test_the_bound_is_enforced_not_estimated(session_ok, monkeypatch):
    """PARTIAL (r2): the caps count code points, so 1,008 non-rolled card names
    of 40 four-byte code points in both `picks` and `end_build` put the 1v1
    worst case far over _REPORT_MAX_BYTES. The envelope is measured on the way
    out exactly as FastAPI emits it and the OLDEST games are dropped until it
    fits, counted in `games_omitted`. A single maximal ten-player FFA game fits
    without dropping - the loop's precondition. Negative control: with the fit
    step disabled the same 1v1 world is over the bound (#391)."""
    wide = "\U0001F600" * 60            # cut to _REPORT_CARD_NAME_MAX code points, 4 B each
    world = _worst_1v1_world(card_prefix=wide)          # ONE world: the game ids must match below
    fitted = _call(world, CALLER, session=BIG_SESSION)
    monkeypatch.setattr(main, "_report_fit", lambda env: env)
    raw = _call(world, CALLER, session=BIG_SESSION)
    assert len(raw["games"]) == 24 and _wire_bytes(raw) > main._REPORT_MAX_BYTES, _wire_bytes(raw)
    assert _wire_bytes(fitted) <= main._REPORT_MAX_BYTES, _wire_bytes(fitted)
    kept = len(fitted["games"])
    assert 1 < kept < 24, kept
    assert fitted["games_omitted"] == 30 - kept and fitted["truncated"] is True
    assert fitted["games"] == raw["games"][-kept:], "the newest games survive; the oldest are dropped"
    ffa = _call(_worst_ffa_world(card_prefix=wide), CALLER, match=FFA1)
    assert len(ffa["games"]) == 1 and _wire_bytes(ffa) <= main._REPORT_MAX_BYTES, _wire_bytes(ffa)


def test_build_blocks_measure_their_card_text():
    """LOW (r2): the card list wraps to the column width and the block height
    is measured from it, not a fixed 40 px strip; the draw path reads the same
    measured height it paged with."""
    src = PLUGIN / "SessionReportView.cs"
    cards = _cs_body(src, "private static float CardsHeight(SessionReportModel.BuildBlock b, float textW)")
    assert "CalcHeight(" in cards
    draw = _cs_body(src, "private static void DrawBuilds(Rect body, SessionReportModel.Model m, int sub)")
    assert "blockCardsH[" in draw and "stCards" in draw
    assert ", 40f), b.Cards" not in draw, "the fixed 40 px card strip is gone"
    styles = _cs_body(src, "private static void EnsureStyles()")
    assert "stCards = Mk(14, TextAnchor.UpperLeft" in styles, "UpperLeft is the wrapping anchor in Mk"

def test_sitting_label_counts_the_games_the_report_omits(session_ok):
    """r1b M2: the ranked/casual label is a claim about the WHOLE sitting. The statement
    keeps only the newest _REPORT_MAX_GAMES rows, so a casual game old enough to be
    omitted must still make the set casual; the negative control flips it."""
    import uuid as _uuid
    ids = [str(_uuid.UUID(int=0x5E551 + i)) for i in range(main._REPORT_MAX_GAMES + 2)]
    world = [match_row(ids[0], PID_A, PID_B, minute=0, ranked=False)]
    world += [match_row(ids[i], PID_A, PID_B, minute=5 * i, ranked=True) for i in range(1, len(ids))]
    resp = _call(FakeDb(matches=world), CALLER, sitting=ids[-1])
    assert resp["truncated"] is True and resp["games_omitted"] >= 1
    assert ids[0] not in {g["match_id"] for g in resp["games"]}, "the casual game is among the omitted"
    assert resp["kind"] == "casual", "label over the whole sitting, not the retained rows"
    world[0] = match_row(ids[0], PID_A, PID_B, minute=0, ranked=True)
    resp2 = _call(FakeDb(matches=world), CALLER, sitting=ids[-1])
    assert resp2["truncated"] is True and resp2["kind"] == "ranked", "negative control"
