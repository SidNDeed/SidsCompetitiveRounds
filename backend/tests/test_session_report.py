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
# Round 2 M4: the spectate game the broadcast seat watched - A against B over
# the ranked series (games at minutes 0, 5 and 10, two minutes each), with the
# accounts holding a watched-grant record of it (round 3 N1: the record a
# master validation writes when it observes the seat; the lease row itself is
# not what the reads consult). The broadcast account is appended below, where
# it is defined.
# Round 3 M4: each spectate game also records its mode and source identity
# (a 1v1 queue room records none, so its roster is compared exactly).
W1 = str(uuid.uuid4())
WATCHED = [{"id": W1, "roster": ",".join(sorted((CALLER, OPP))), "grants": [],
            "mode": "1v1", "source_ref": "",
            "started_at": T0 - timedelta(minutes=1), "ended_at": T0 + timedelta(minutes=13)}]
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
             "same_card_rule": None, "sudden_death": None, "settings_known": False,
             # the game's own frozen settings block (migration 360); NULL = a
             # game recorded before 360, so the lobby columns above answer
             "settings_frozen": None}
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
                 ffa_players=None, series_row=None, team_series_row=None, fail_rating=False,
                 watched=None):
        self.statements = []
        # Round 2 M4: spectate games with the accounts holding a watched grant of each
        self.watched = WATCHED if watched is None else watched
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
        if "AS watched_game" in sql:
            # Round 2 M4: the broadcast account's viewer read, bound to a game it
            # watched. Every predicate the binding rests on must be in the
            # statement, or the fake refuses.
            for needle in ("JOIN spectate_watch_grants wg ON wg.spectator_steam_id = CAST(:bsid AS text) "
                           "AND wg.mode = r.mode",
                           "JOIN spectate_games ws ON ws.id = wg.game_id",
                           "CAST(:viewer AS text) = ANY(string_to_array(wg.roster, ','))",
                           "r.ended_at >= wg.game_started_at - make_interval(secs => :pre)",
                           "r.ended_at <= COALESCE(ws.ended_at, NOW()) + make_interval(secs => :post)",
                           "CASE WHEN wg.source_ref <> '' THEN wg.source_ref = r.source_id",
                           "ELSE r.played_sids = ARRAY(",
                           "SELECT '1v1' AS mode, wm.ended_at, CAST(wm.series_id AS text) AS source_id, "
                           "ARRAY[wm.player1_id, wm.player2_id] AS played FROM matches wm WHERE wm.id = CAST(:key AS uuid)",
                           "SELECT '2v2', wt.ended_at, CAST(wt.series_id AS text), "
                           "ARRAY[wt.t1a_id, wt.t1b_id, wt.t2a_id, wt.t2b_id] FROM team_matches wt WHERE wt.id = CAST(:key AS uuid)",
                           "SELECT '1v2', wo.ended_at, CAST(wo.series_id AS text), "
                           "ARRAY[wo.solo_id, wo.duo_a_id, wo.duo_b_id] FROM ovt_matches wo WHERE wo.id = CAST(:key AS uuid)",
                           "SELECT 'ffa', wf.ended_at, CAST(wf.lobby_id AS text), ARRAY(SELECT wx.player_id "
                           "FROM ffa_match_players wx WHERE wx.match_id = wf.id AND NOT wx.absent) "
                           "FROM ffa_matches wf WHERE wf.id = CAST(:key AS uuid)"):
                assert needle in sql, "the watched statement lost a predicate: " + needle
            key = params["key"]
            sid_of = {str(p["id"]): p["steam_id"] for p in self.players}

            def _played(*pids):
                return {sid_of.get(str(p)) for p in pids if p is not None}
            # (mode, end, source id, played roster) of the requested game
            wanted = [("1v1", m["ended_at"], m.get("series_id"), _played(m["player1_id"], m["player2_id"]))
                      for m in self.matches if str(m["id"]) == key]
            wanted += [("2v2", m["ended_at"], m.get("series_id"),
                        _played(m["t1a_id"], m["t1b_id"], m["t2a_id"], m["t2b_id"]))
                       for m in self.team_matches if str(m["id"]) == key]
            if str(self.ffa_match["id"]) == key:
                wanted.append(("ffa", self.ffa_match["ended_at"], self.ffa_match.get("lobby_id"),
                               _played(*[p["player_id"] for p in self.ffa_players if not p["absent"]])))
            pre, post = timedelta(seconds=params["pre"]), timedelta(seconds=params["post"])
            for w in self.watched:
                if params["bsid"] not in w["grants"] or params["viewer"] not in w["roster"].split(","):
                    continue
                for mode, e, src, played in wanted:
                    if e is None or mode != w["mode"]:
                        continue
                    if not (w["started_at"] - pre <= e <= (w["ended_at"] or datetime.now(timezone.utc)) + post):
                        continue
                    if w["source_ref"]:
                        if src is None or str(src) != w["source_ref"]:
                            continue
                    elif played != {s for s in w["roster"].split(",") if s}:
                        continue
                    return _Res([{"watched_game": w["id"]}])
            return _Res([])
        if "AS report_kind" in sql:
            # Sept 28 (board row 30a): the `sitting` anchor's kind. Every arm
            # carries its own mode's caller predicate.
            for needle in ("CAST(:cpid AS uuid) IN (km.player1_id, km.player2_id)",
                           "CAST(:cpid AS uuid) IN (kt.t1a_id, kt.t1b_id, kt.t2a_id, kt.t2b_id)",
                           "CAST(:cpid AS uuid) IN (ko.solo_id, ko.duo_a_id, ko.duo_b_id)",
                           "kx.player_id = CAST(:cpid AS uuid) AND NOT kx.absent"):
                assert needle in sql, "the kind statement lost a caller predicate: " + needle
            key, cpid = params["key"], params["cpid"]
            for m in self.matches:
                if (str(m["id"]) == key and m["invalidated_at"] is None
                        and cpid in (str(m["player1_id"]), str(m["player2_id"]))):
                    return _Res([{"report_kind": "v1", "series_id": None}])
            for m in self.team_matches:
                seats = {str(m[k]) for k in ("t1a_id", "t1b_id", "t2a_id", "t2b_id") if m[k] is not None}
                if str(m["id"]) == key and m["invalidated_at"] is None and cpid in seats:
                    sid_ = str(m["series_id"]) if m["series_id"] is not None else None
                    return _Res([{"report_kind": "team", "series_id": sid_}])
            if (str(self.ffa_match["id"]) == key and self.ffa_match["invalidated_at"] is None
                    and any(str(p["player_id"]) == cpid and not p["absent"] for p in self.ffa_players)):
                return _Res([{"report_kind": "ffa", "series_id": None}])
            return _Res([])
        if "FROM ffa_matches fm" in sql and "g.lobby_id = an.lobby_id" in sql:
            # Sept 28 (board row 30a): the FFA lobby sitting. The fake's one
            # FFA game is a one-game lobby.
            assert "fm.invalidated_at IS NULL" in sql
            assert ("EXISTS (SELECT 1 FROM ffa_match_players fpx WHERE fpx.match_id = fm.id "
                    "AND fpx.player_id = CAST(:cpid AS uuid) AND NOT fpx.absent)") in sql, \
                "the lobby statement lost the played-this-game participant predicate"
            assert f"make_interval(hours => {main.SITTING_GAP_HOURS})" in sql, \
                "the lobby statement lost the sitting rule"
            assert "COUNT(*) OVER () AS total_rows" in sql
            if str(self.ffa_match["id"]) != params["key"]:
                return _Res([])
            played = any(str(p["player_id"]) == params["cpid"] and not p["absent"]
                         for p in self.ffa_players)
            return _Res(self._with_total([self.ffa_match])[: int(params["lim"])] if played else [])
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
            assert "fp.match_id = ANY(CAST(:mids AS uuid[]))" in sql, "one roster statement per envelope"
            mids = {str(x) for x in params["mids"]}
            return _Res([dict(p, match_id=p.get("match_id", FFA1)) for p in self.ffa_players
                         if not p["absent"] and str(p.get("match_id", FFA1)) in mids])
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
            # Board row 30d: one row per (player, reference, reason), so the
            # route can tell a game's own gold from a series award.
            assert "GROUP BY gt.player_id, gt.reference_id, gt.reason" in sql, \
                "the ledger statement must keep each row's reference and reason apart"
            reasons, refs = set(params["reasons"]), set(params["refs"])
            agg = {}
            for g in self.gold:
                if g["reason"] in reasons and str(g["reference_id"]) in refs:
                    k = (g["player_id"], str(g["reference_id"]), g["reason"])
                    agg[k] = agg.get(k, 0) + g["amount"]
            return _Res([{"player_id": p, "reference_id": r, "reason": why, "amount": a}
                         for (p, r, why), a in agg.items()])
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


def test_sitting_resolves_its_anchor_kind(session_ok):
    """Board row 30a: `sitting` resolves the anchor game's KIND instead of
    assuming 1v1 - a 2v2 game gives its series (the `series` envelope
    exactly), an FFA game its lobby sitting (the `lobby` envelope exactly) -
    and the kind is decided by the statement right after the caller's."""
    db = FakeDb()
    by_sitting = _call(db, CALLER, sitting=TM1)
    assert "AS report_kind" in db.statements[1][0], "the kind is resolved right after the caller"
    assert db.statements[1][1] == {"key": TM1, "cpid": PID_A}
    assert by_sitting["kind"] == "team"
    assert by_sitting == _call(FakeDb(), CALLER, series=TEAM_SERIES)
    by_sitting = _call(FakeDb(), CALLER, sitting=FFA1)
    assert by_sitting["kind"] == "ffa"
    assert by_sitting == _call(FakeDb(), CALLER, lobby=FFA1)
    # a 1v1 anchor keeps the 1v1 sitting set (the Sept 8 tests pin its games)
    assert _call(FakeDb(), CALLER, sitting=C1)["kind"] in ("casual", "ranked")


def test_sitting_on_a_game_the_caller_did_not_play_is_the_one_404(session_ok):
    for who, anchor in ((OTHER, FFA1), (XSTEAM, TM1), (GHOST, FFA1), (CALLER, str(uuid.uuid4()))):
        db = FakeDb()
        with pytest.raises(HTTPException) as ei:
            _call(db, who, sitting=anchor)
        assert ei.value.status_code == 404 and ei.value.detail == "not_found", (who, anchor)
        assert not any("FROM team_matches tm" in s or "FROM ffa_matches fm" in s
                       for s, _ in db.statements), "no games statement runs for an unresolved kind"


def test_a_one_game_lobby_reads_like_its_game(session_ok):
    """The FFA tab sends `lobby` for every game: a game alone in its lobby
    sitting must read exactly as `match` does."""
    one = _call(FakeDb(), CALLER, match=FFA1)
    lob = _call(FakeDb(), CALLER, lobby=FFA1)
    assert [g["match_id"] for g in lob["games"]] == [FFA1]
    assert lob["players"] == one["players"] and lob["set_summary"] == one["set_summary"]
    assert lob["games"] == one["games"]
    with pytest.raises(HTTPException) as ei:
        _call(FakeDb(), GHOST, lobby=FFA1)
    assert ei.value.status_code == 404


def test_the_kind_and_lobby_statements_carry_the_caller_predicate():
    kind = " ".join(main._REPORT_KIND_SQL.split())
    for needle in ("CAST(:cpid AS uuid) IN (km.player1_id, km.player2_id)",
                   "CAST(:cpid AS uuid) IN (kt.t1a_id, kt.t1b_id, kt.t2a_id, kt.t2b_id)",
                   "CAST(:cpid AS uuid) IN (ko.solo_id, ko.duo_a_id, ko.duo_b_id)",
                   "kx.player_id = CAST(:cpid AS uuid) AND NOT kx.absent"):
        assert needle in kind, needle
    assert kind.count("invalidated_at IS NULL") == 4, "every arm excludes invalidated games"
    lobby = " ".join(main._REPORT_FFA_LOBBY_SQL.split())
    assert ("fpx.player_id = CAST(:cpid AS uuid) AND NOT fpx.absent") in lobby
    assert "ax.player_id = CAST(:cpid AS uuid) AND NOT ax.absent" in lobby, "the anchor is a game the caller played"
    assert "g.lobby_id = an.lobby_id" in lobby and "g.ended_at >= sp.lo AND g.ended_at <= sp.hi" in lobby
    # room-free like every other report statement (#463)
    for src in (kind, lobby):
        assert "room" not in src.lower()


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
    or a casual game with no series — and `settings` for FFA from the
    block the game froze when it was recorded (migration 360), else from the
    lobby (null when the lobby predates configurable settings)."""
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
    # Migration 360: the block the game froze wins over the lobby's current
    # row, and the loader selects it (the row must carry it: a KeyError, not
    # a silent fall back to the lobby, when a surface forgets).
    frozen = {"score_target": 9, "card_cap": 3, "initial_picks": 2, "card_candidates": 4,
              "same_card_rule": False, "sudden_death": True}
    resp = _call(FakeDb(ffa_match=dict(FFA_SETTINGS_ROW, settings_frozen=json.dumps(frozen))),
                 CALLER, match=FFA1)
    assert resp["games"][0]["settings"] == frozen, "the game's frozen block, not the lobby's current row"
    assert "fm.settings_frozen" in main._REPORT_FFA_SQL

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
    rating update and skips the link).

    The pass moved out of submit_match into `_apply_series_rating_pass` when
    the report's commit moved below it, so this reads the helper. Both halves
    are asserted: the helper carries the link, and submit_match is what calls
    it — a pin on a helper nobody invokes certifies nothing (#286)."""
    submit = inspect.getsource(main._apply_series_rating_pass)
    assert "await _apply_series_rating_pass(" in inspect.getsource(main.submit_match)
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
                inspect.getsource(main._report_roster),
                # Sept 28 (board row 30a): the lobby sitting and the series/kind dispatch
                inspect.getsource(main._report_load_ffa_lobby), inspect.getsource(main._report_ffa_games),
                inspect.getsource(main._report_ffa_slot), inspect.getsource(main._report_series_set)]
    assert len(sources) >= 20
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
    # Board row 30c: the page breaks come from the pure packer the client
    # harness executes (SessionReportRules.PackPages), called once, over the
    # heights this method measured.
    assert measure.count("SessionReportRules.PackPages(blockH") == 1, \
        "the page breaks are packed exactly once in the method (#284)"
    rules = _cs_body(PLUGIN / "SessionReportRules.cs",
                     "internal static List<int> PackPages(IList<float> heights, float usable)")
    assert rules.count("starts.Add(i)") == 1, "the packer records a page break in one place"
    assert "blockH[" in builds and "blockH.Add(" in measure, "the draw path pages with the heights it measured"
    model = PLUGIN / "SessionReportModel.cs"
    assert "FIXED_PAGES = 6" in strip_comments_only(model.read_text(encoding="utf-8"))


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
    # rolled picks: parsed (the parser lives in the Unity-free rules file since
    # board row 30a, where the client harness executes it), and kept out of
    # the build list
    parse = _cs_body(PLUGIN / "SessionReportRules.cs", "private static Game ParseGame(string obj)")
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
    """LOW (r2), board row 30c: every chip is measured with the style that
    draws it and flowed into its column by the pure FlowChips rule the client
    harness executes; the stat lines are measured at the column width; the
    draw path reads the same layout it paged with."""
    src = PLUGIN / "SessionReportView.cs"
    width = _cs_body(src, "private static float ChipWidth(SessionReportModel.Chip chip, float colW)")
    assert "stChip.CalcSize(" in width
    block = _cs_body(src, "private static BlockLayout MeasureBlock(SessionReportModel.GameBuild b, float innerW, out float h)")
    assert block.count("SessionReportRules.FlowChips(") == 1
    assert "stTiny.CalcHeight(" in block and "NativeUI.BuildStatsTipBlock(" in block
    draw = _cs_body(src, "private static void DrawBuilds(Rect body, SessionReportModel.Model m, int sub)")
    assert "blockLayouts[" in draw and "DrawChip(" in draw and "cl.ChipAt[" in draw
    styles = _cs_body(src, "private static void EnsureStyles()")
    assert "stChip = Mk(13, TextAnchor.MiddleLeft" in styles, "a chip is one line: MiddleLeft does not wrap in Mk"

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

# -- board row 30d: what each game and the set earned ------------------------

def test_each_game_carries_its_own_ledger_gold_and_xp_record(session_ok):
    """A game's own gold (every ledger row written against its id under its
    mode's per-game reasons) and its XP record, keyed by steam id and sparse;
    the series award stays the summary's `gold` and the totals add the two."""
    matches = [dict(m, p1_xp_gained=40, p2_xp_gained=25) if m["id"] == M1 else m for m in MATCHES]
    db = FakeDb(matches=matches)
    resp = _call(db, CALLER, series=SERIES)
    by = {g["match_id"]: g for g in resp["games"]}
    assert by[M1]["gold"] == {CALLER: 5}
    assert by[M2]["gold"] == {} and by[M3]["gold"] == {}, "no ledger row: no key, never a zero"
    assert by[M1]["xp"] == {CALLER: 40, OPP: 25}
    assert by[M2]["xp"] == {} and by[M3]["xp"] == {}, "no XP record: no key"
    ss = resp["set_summary"]
    assert ss["gold"] == {CALLER: 12, OPP: 4}, "the award alone, as older clients read it"
    assert ss["gold_total"] == {CALLER: 17, OPP: 4}
    assert ss["xp_total"] == {CALLER: 40, OPP: 25}
    assert db.count("FROM gold_transactions gt") == 1, "one ledger statement per set"


def test_ledger_rows_are_split_by_reference_and_reason(session_ok):
    gold = GOLD + [
        {"player_id": PID_A, "amount": 1000, "reason": "series_win", "reference_id": M2},
        {"player_id": PID_B, "amount": 1000, "reason": "xp", "reference_id": SERIES},
    ]
    resp = _call(FakeDb(gold=gold), CALLER, series=SERIES)
    by = {g["match_id"]: g for g in resp["games"]}
    assert by[M2]["gold"] == {}, "an award reason written against a game is not that game's gold"
    assert resp["set_summary"]["gold"] == {CALLER: 12, OPP: 4}, \
        "a per-game reason written against the series is not the award"


def test_a_2v2_series_total_is_its_own_row(session_ok):
    row = dict(TEAM_SERIES_ROW, t1a_gold_earned=80, t1b_gold_earned=70, t2a_gold_earned=20,
               t2b_gold_earned=None, t1a_xp_earned=300, t1b_xp_earned=290, t2a_xp_earned=120,
               t2b_xp_earned=None)
    resp = _call(FakeDb(team_series_row=row), CALLER, series=TEAM_SERIES)
    ss = resp["set_summary"]
    assert ss["gold_total"] == {CALLER: 80, OTHER: 70, OPP: 20}
    assert ss["xp_total"] == {CALLER: 300, OTHER: 290, OPP: 120}
    assert resp["games"][0]["gold"] == {CALLER: 6, OTHER: 6}, "the game's own team_xp rows"
    assert resp["games"][0]["xp"] == {}, "2v2 keeps no per-game XP record"


def test_an_ffa_game_carries_its_gold_gained_and_xp_gained(session_ok):
    fps = [dict(p, xp_gained=xp) for p, xp in zip(FFA_PLAYERS, (120, 60, 0))]
    resp = _call(FakeDb(ffa_players=fps), CALLER, match=FFA1)
    g = resp["games"][0]
    assert g["gold"] == {CALLER: 30, OPP: 10}
    assert g["xp"] == {CALLER: 120, OPP: 60}, "the absent ghost never reaches the game"
    ss = resp["set_summary"]
    assert ss["gold"] == ss["gold_total"] == {CALLER: 30, OPP: 10}
    assert ss["xp_total"] == {CALLER: 120, OPP: 60}


def test_a_casual_sitting_total_is_its_games_ledger(session_ok):
    resp = _call(FakeDb(), CALLER, session=SESSION)
    ss = resp["set_summary"]
    assert ss["gold"] == ss["gold_total"] == {CALLER: 7, OPP: 2}
    by = {g["match_id"]: g for g in resp["games"]}
    assert by[C1]["gold"] == {CALLER: 3, OPP: 2} and by[C2]["gold"] == {CALLER: 4}


# -- board row 30c: the builds pages -------------------------------------------

def test_builds_are_one_block_per_game_with_chips_in_pick_order():
    """Board row 30c: one block per game (every game, no cap), a column per
    player who played it, the cards as chips in PICK order - a rolled-out FFA
    pick stays in its place, flagged - falling back to the end build only when
    the player has no pick list."""
    model = PLUGIN / "SessionReportModel.cs"
    build = _cs_body(model, "internal static Model Build(Envelope env)")
    assert build.count("m.Builds.Add(gb)") == 1
    loop = build[build.index("var gb = new GameBuild"):build.index("m.Builds.Add(gb)")]
    assert "foreach (var pk in g.Picks)" in loop and "MakeChip(pk.Card, pk.Rolled)" in loop
    assert loop.index("g.Picks") < loop.index("g.EndBuild"), "the pick list first; the end build is the fallback"
    assert "g.Scores.ContainsKey(pid)" in loop, "a column per player who played the game"
    assert "continue;" not in loop.replace("if (!g.Scores.ContainsKey(pid) && !HasCards(g, pid)) continue;", ""), \
        "no other path skips a game or a player"
    head = _cs_body(model, "private static string BlockHeader(Model m, Game g, int number)")
    assert "ScoreLine(" in head and "TeamScoreLabel(" in head and "FfaScoreLabel(" in head
    assert 'I18n.TrF("length {0}", Clock(g.DurationS))' in build, "the game's length in the block header"


def test_chip_rarity_colours_are_the_card_screens_own():
    """Board row 30c: a chip carries its card's rarity colour - the same
    colours NativeUI's card screens use (NativeUI keeps them private, so the
    model repeats them; this pin holds the two sets equal)."""
    model = PLUGIN / "SessionReportModel.cs"
    chip = _cs_body(model, "private static Chip MakeChip(string card, bool rolled)")
    assert "CardRarityLookup.GetRarity(card)" in chip and "RarityTint(rarity)" in chip
    ui = strip_comments_only((PLUGIN / "NativeUI.cs").read_text(encoding="utf-8")).replace(" ", "")
    mine = strip_comments_only(model.read_text(encoding="utf-8")).replace(" ", "")
    pairs = (("C_COMMON", "RARITY_COMMON"), ("C_UNCOMMON", "RARITY_UNCOMMON"),
             ("C_RARE", "RARITY_RARE"), ("C_LABEL", "RARITY_OTHER"))
    for theirs, ours in pairs:
        m1 = re.search(theirs + r"=newColor\(([^)]*)\)", ui)
        m2 = re.search(ours + r"=newColor\(([^)]*)\)", mine)
        assert m1 and m2, (theirs, ours)
        assert m1.group(1) == m2.group(1), (theirs, m1.group(1), ours, m2.group(1))
    tint = _cs_body(model, "internal static Color RarityTint(string rarity)")
    for word, name in (('"common"', "RARITY_COMMON"), ('"uncommon"', "RARITY_UNCOMMON"), ('"rare"', "RARITY_RARE")):
        assert word + ": return " + name in tint
    assert "default: return RARITY_OTHER" in tint


def test_a_builds_page_names_the_games_it_holds():
    """Board row 30c: the page header and the footer say "Games k-m of n"
    from the same measured page breaks the draw path uses."""
    view = PLUGIN / "SessionReportView.cs"
    draw = _cs_body(view, "private static void DrawBuilds(Rect body, SessionReportModel.Model m, int sub)")
    assert "m.BuildsRange(first, end - 1)" in draw
    footer = _cs_body(view, "private static void DrawFooter(Rect r)")
    assert "PageLine(model, page, pages)" in footer
    line = _cs_body(view, "private static string PageLine(SessionReportModel.Model m, int pg, int pages)")
    assert "m.PageTitle(pg, first, last)" in line and "buildStarts[" in line
    model = PLUGIN / "SessionReportModel.cs"
    rng = _cs_body(model, "public string BuildsRange(int first, int last)")
    assert 'I18n.TrF("Games {0}-{1} of {2}", first + 1, last + 1, Builds.Count)' in rng
    assert 'I18n.TrF("Game {0} of {1}", first + 1, Builds.Count)' in rng


# -- board row 30d: the Totals pages ------------------------------------------

def test_the_totals_pages_are_derived_by_the_executed_rules():
    """Board row 30d: every Totals number comes from SessionReportRules.Derive
    (the client harness executes it against the server's envelopes), called
    once per model; the model keeps no second summing path of its own."""
    model = PLUGIN / "SessionReportModel.cs"
    build = _cs_body(model, "internal static Model Build(Envelope env)")
    assert build.count("BuildTotalsPages(m, env)") == 1
    pages = _cs_body(model, "private static void BuildTotalsPages(Model m, Envelope env)")
    assert pages.count("Derive(env, m.Players)") == 1
    whole = strip_comments_only(model.read_text(encoding="utf-8"))
    for gone in ("kills_derived", "BuildTotals(", "SummaryLines", "TotalsRows"):
        assert gone not in whole, gone
    assert "FIXED_PAGES = 6" in whole, "timeline, rates and the four Totals pages"


def test_a_stat_nobody_recorded_is_omitted_never_zero():
    """Board row 30d: a column exists only when some player has a value, a
    missing cell reads "-", and every cell formatter answers null (not 0) for
    a value the set does not carry."""
    model = PLUGIN / "SessionReportModel.cs"
    col = _cs_body(model, "private static void Column(List<KeyValuePair<string, string[]>> cols, string header, int n, Func<int, string> cell)")
    assert "if (any) cols.Add(" in col
    fill = _cs_body(model, "private static void FillTable(Model m, Table t, List<KeyValuePair<string, string[]>> cols)")
    assert 'c.Value[pi] ?? "-"' in fill and "if (cols.Count == 0) return;" in fill
    for sig in ("private static string RatingCell(Envelope env, Model m, int pi, int which)",
                "private static string PerGame(List<float?> xs, string fmt)",
                "private static string KeysPerS(PlayerLine pl)",
                "private static string Kd(PlayerLine pl)"):
        assert "return null" in _cs_body(model, sig) or ": null" in _cs_body(model, sig), sig
    text = strip_comments_only(model.read_text(encoding="utf-8"))
    for helper in ("private static string F0(float? v) => v.HasValue ?",
                   "private static string Int(int? v) => v.HasValue ?",
                   "private static string Signed(int? v) => v.HasValue ?"):
        line = text[text.index(helper):text.index(";", text.index(helper))]
        assert line.rstrip().endswith(": null"), line
    bars = _cs_body(model, "private static Bars MakeBars(string title")
    assert "if (!any) b.Missing = missing;" in bars


def test_the_totals_pages_draw_one_element_per_data_type():
    """Board rows 30d/30f: the set page's tiles and game-length strip, the
    players' rate tables, the per-game comparisons as bars, the progress
    table - each page draws the element its data type calls for."""
    view = PLUGIN / "SessionReportView.cs"
    page = _cs_body(view, "private static void DrawPage(Rect body, SessionReportModel.Model m, int pg)")
    for call in ("case 2: DrawSetPage(body, m)", "case 3: DrawPlayersPage(body, m)",
                 "case 4: DrawPerGamePage(body, m)", "case 5: DrawProgressPage(body, m)"):
        assert call in page, call
    assert "DrawStrip(" in _cs_body(view, "private static void DrawSetPage(Rect body, SessionReportModel.Model m)")
    assert "DrawTiles(" in _cs_body(view, "private static void DrawSetPage(Rect body, SessionReportModel.Model m)")
    assert _cs_body(view, "private static void DrawPlayersPage(Rect body, SessionReportModel.Model m)").count("DrawTable(") == 2
    assert _cs_body(view, "private static void DrawPerGamePage(Rect body, SessionReportModel.Model m)").count("DrawBars(") == 2
    prog = _cs_body(view, "private static void DrawProgressPage(Rect body, SessionReportModel.Model m)")
    assert "DrawTable(" in prog and prog.count("DrawBars(") == 2
    model = PLUGIN / "SessionReportModel.cs"
    pages = _cs_body(model, "private static void BuildTotalsPages(Model m, Envelope env)")
    assert "d.Players[pi].Gold" in pages and "d.Players[pi].Xp" in pages, "gold and XP are the Derive lines' (set totals)"
    assert "RatingCell(env, m, pi, 0)" in pages and "RatingCell(env, m, pi, 2)" in pages


# -- board row 30e: the rounds race -------------------------------------------

def test_the_race_plots_rounds_won_on_the_modes_win_target():
    """Board row 30e: the score race plots ROUNDS won (RoundsSeries over the
    mode's divisor, executed by the client harness) as steps, the
    within-round points as a thin secondary line, and a 2v2 / 1v2 game's
    recorded end score as a dot; its y-axis is the rounds the mode is played
    to (WinTarget) and only the other panels are NiceCeil'd."""
    model = PLUGIN / "SessionReportModel.cs"
    build = _cs_body(model, "internal static Model Build(Envelope env)")
    assert 'Unit = I18n.Tr("rounds"), Rounds = true' in build
    assert "float racePer = RaceDivisor(m.Kind);" in build
    assert "RoundsSeries(score, racePer, false)" in build and "RoundsSeries(score, racePer, true)" in build
    assert ".Step = true;" in build
    # Round 2 L1: each panel is finished with its own empty text.
    assert "Finish(m.Score" not in build, "the race is not NiceCeil'd"
    for panel in ("m.Damage", "m.Dps", "m.HitPct", "m.BlockPct", "m.Ping", "m.Fps"):
        assert build.count("Finish(" + panel + ", MissingText(m.Kind, ") == 1, panel
    assert build.count("FinishRace(m, env, MissingText(m.Kind, MET_SCORE))") == 1
    race = _cs_body(model, "private static void FinishRace(Model m, Envelope env, string missing)")
    assert "p.MaxY = RaceTop(m.Kind, env.Games, recorded, out unknown);" in race and "p.Dots.Add(" in race
    assert "NiceCeil" not in race


def test_an_unrecorded_race_target_is_unknown_never_guessed():
    """Round 2 M2: the server sends settings=null for an FFA game with no
    settings record (early games were first-to-3), so the client has no
    target for it. SessionReportRules.WinTarget answers TARGET_UNKNOWN there
    and RaceTop (both executed by the client harness) draws the axis to the
    top recorded score, counting the unknown games; the race panel's Note says
    the target is not recorded, and the view prints it. No default target
    constant is left to substitute."""
    rules = strip_comments_only((PLUGIN / "SessionReportRules.cs").read_text(encoding="utf-8"))
    assert "FFA_DEFAULT_TARGET" not in rules
    target = _cs_body(PLUGIN / "SessionReportRules.cs", "internal static int WinTarget(string kind, Game g)")
    assert 'if (kind == "ffa") return g != null && g.ScoreTarget > 0 ? g.ScoreTarget : TARGET_UNKNOWN;' in target
    model = PLUGIN / "SessionReportModel.cs"
    race = _cs_body(model, "private static void FinishRace(Model m, Envelope env, string missing)")
    assert "WinTarget(" not in race, "the axis comes from RaceTop only"
    assert "if (unknown > 0)" in race
    assert 'I18n.Tr("race target not recorded: the axis ends at the top score")' in race
    assert 'I18n.TrF("race target not recorded for {0} of {1} games", unknown, env.Games.Count)' in race
    panel = _cs_body(PLUGIN / "SessionReportView.cs",
                     "private static void DrawPanel(Rect r, SessionReportModel.Panel p, SessionReportModel.Model m, bool marks)")
    assert "if (!string.IsNullOrEmpty(p.Note))" in panel and "+ p.Note +" in panel


def test_the_race_grid_is_one_line_per_round_and_the_thin_line_is_gated():
    view = PLUGIN / "SessionReportView.cs"
    panel = _cs_body(view, "private static void DrawPanel(Rect r, SessionReportModel.Panel p, SessionReportModel.Model m, bool marks)")
    assert "p.Rounds ? Mathf.Max(1, Mathf.RoundToInt(p.MaxY)) : 4" in panel
    assert "bool thinLegible = p.Thin.Count > 0 && plot.height / Mathf.Max(1f, p.MaxY) >= 24f;" in panel
    assert "thinLegible && li < p.Thin.Count" in panel
    assert "if (line.Step)" in panel and "p.Dots[i]" in panel


def test_a_game_names_only_the_players_who_played_it():
    """Round 2 M1: a fluid FFA lobby's roster is the UNION of its games'
    rosters, so a player can have no score key in a game. Every rendered
    score of a game - its timeline divider, its builds block header and the
    set's race line, which reuses the header - comes from the presence rules
    the client harness executes (SessionReportRules.PairScores, SideScore,
    Standings), which omit a player with no key; the model keeps no getter
    that reads a missing key as 0. The harness's "presence" cases hold the
    rules; this holds that the model renders through them."""
    model = PLUGIN / "SessionReportModel.cs"
    whole = strip_comments_only(model.read_text(encoding="utf-8"))
    assert "Get(g.Scores" not in whole and "Get(Dictionary<string, int>" not in whole
    assert not re.search(r"Scores\.TryGetValue\([^)]*\)\s*\?\s*\w+\s*:\s*0", whole), "a missing score read as 0"
    ffa = _cs_body(model, "private static string FfaScoreLabel(Model m, Game g, int gi, bool longForm)")
    assert "var order = Standings(g, m.Players);" in ffa
    assert "m.Players.Count; i++" not in ffa, "the label enumerates the game's standings, not the roster"
    team = _cs_body(model, "private static string TeamScoreLabel(Model m, Game g, int gi, bool longForm)")
    assert "SideScore(g, m.Players, 1, out p1)" in team and "SideScore(g, m.Players, 2, out p2)" in team
    header = _cs_body(model, "private static string BlockHeader(Model m, Game g, int number)")
    assert "if (PairScores(g, m.Players, out sa, out sb))" in header
    build = _cs_body(model, "internal static Model Build(Envelope env)")
    assert build.count("if (PairScores(g, m.Players, out sa, out sb))") == 1
    assert "if (m.Players.Count == 2)" not in build.split("m.Spans.Add(sp);")[0]


# -- board row 30g: the broadcast account names a viewer ------------------------

BROADCAST = next(iter(main.SPECTATE_BROADCAST_STEAM_IDS))
WATCHED[0]["grants"].append(BROADCAST)


@pytest.fixture
def broadcast_session(monkeypatch):
    """The fixture identities and the broadcast account hold valid sessions."""
    async def _ok(request, steam_id, db):
        return steam_id in (CALLER, OPP, OTHER, XSTEAM, YSTEAM, GHOST, NOBODY, BROADCAST)
    monkeypatch.setattr(main, "_strict_steam_session_ok", _ok)


def test_the_broadcast_account_is_served_the_set_as_its_viewer(broadcast_session):
    """Board row 30g: the broadcast seat names a player who played the set and
    gets exactly the envelope that player's own request gets - participation
    and the roster check are decided for the viewer."""
    own = _call(FakeDb(), CALLER, sitting=M1)
    db = FakeDb()
    assert _call(db, BROADCAST, sitting=M1, viewer=CALLER) == own
    assert "AS watched_game" in db.statements[0][0], "the watched binding is asked first"
    assert db.statements[1][1] == {"sid": CALLER}, "the caller lookup reads the VIEWER"
    for sel in ({"match": M1}, {"sitting": M3}):
        assert _call(FakeDb(), BROADCAST, viewer=CALLER, **sel) == _call(FakeDb(), CALLER, **sel), sel


def test_a_viewer_is_refused_to_every_other_caller(broadcast_session):
    for who in (CALLER, OPP, OTHER):
        db = FakeDb()
        with pytest.raises(HTTPException) as ei:
            _call(db, who, sitting=M1, viewer=CALLER)
        assert ei.value.status_code == 403 and ei.value.detail == "broadcast_only", who
        assert db.statements == [], "a refused viewer is decided before any statement"
    for bad in ("", CALLER[:-1], CALLER + "1", CALLER[:5] + "x" + CALLER[6:], CALLER + " "):
        db = FakeDb()
        with pytest.raises(HTTPException) as ei:
            _call(db, BROADCAST, sitting=M1, viewer=bad)
        assert ei.value.status_code == 400 and ei.value.detail == "bad_request", repr(bad)
        assert db.statements == [], repr(bad)


def test_the_broadcast_account_gets_nothing_it_did_not_name(broadcast_session):
    """Control: without a viewer the broadcast account is an ordinary caller
    (it played nothing: 404), and a viewer who did not play the set gets the
    404 every refusal gets."""
    with pytest.raises(HTTPException) as own:
        _call(FakeDb(), BROADCAST, sitting=M1)
    with pytest.raises(HTTPException) as bystander:
        # OTHER is in no roster of the watched game, and played no 1v1 with A
        _call(FakeDb(watched=[dict(WATCHED[0], roster=OTHER)]), BROADCAST, sitting=M1, viewer=OTHER)
    assert own.value.status_code == bystander.value.status_code == 404
    assert own.value.detail == bystander.value.detail == "not_found"


def test_a_viewer_still_needs_the_callers_session(monkeypatch):
    async def _no(request, steam_id, db):
        return False
    monkeypatch.setattr(main, "_strict_steam_session_ok", _no)
    db = FakeDb()
    with pytest.raises(HTTPException) as ei:
        _call(db, BROADCAST, sitting=M1, viewer=CALLER)
    assert ei.value.status_code == 401 and ei.value.detail == "session_required"
    assert db.statements == []


def _refused(db, **sel):
    with pytest.raises(HTTPException) as ei:
        _call(db, BROADCAST, **sel)
    return ei.value.status_code == 404 and ei.value.detail == "not_found"


def test_a_viewer_read_is_bound_to_a_game_the_broadcast_seat_watched(broadcast_session):
    """Round 2 M4: with viewer= the requested set must be one the broadcast
    seat watched - a spectate game the calling account holds a watched grant
    on, whose roster names the viewer and whose span holds the requested
    game's end. Inside that binding the viewer's own envelope is served;
    outside it the ordinary 404, decided before any player statement runs.
    Control: every refused request below is one the viewer's OWN request is
    served, so the refusal is the binding, not participation."""
    assert _call(FakeDb(), BROADCAST, sitting=M1, viewer=CALLER) == _call(FakeDb(), CALLER, sitting=M1)
    # a game of A outside the watched span (the casual sitting, minute 60)
    db = FakeDb()
    assert _refused(db, sitting=C1, viewer=CALLER)
    assert len(db.statements) == 1 and "AS watched_game" in db.statements[0][0], "no player statement ran"
    assert _call(FakeDb(), CALLER, sitting=C1)["games"], "control: the viewer's own request is served"
    # the watched grant belongs to another account
    assert _refused(FakeDb(watched=[dict(WATCHED[0], grants=[OTHER])]), sitting=M1, viewer=CALLER)
    # the watched game's roster does not name the viewer
    assert _refused(FakeDb(watched=[dict(WATCHED[0], roster=OPP)]), sitting=M1, viewer=CALLER)
    # no watched game at all
    assert _refused(FakeDb(watched=[]), match=M1, viewer=CALLER)
    # a series or session key is not a game id: nothing to bind it to
    assert _refused(FakeDb(), series=SERIES, viewer=CALLER)
    assert _refused(FakeDb(), session=SESSION, viewer=CALLER)
    assert _call(FakeDb(), CALLER, series=SERIES)["games"], "control: the viewer's own series request is served"
    # the span: a game ending just inside the post slack is bound, past it not
    late = dict(WATCHED[0], ended_at=MATCHES[2]["ended_at"] - timedelta(seconds=main._REPORT_WATCH_POST_S - 1))
    early = dict(WATCHED[0], ended_at=MATCHES[2]["ended_at"] - timedelta(seconds=main._REPORT_WATCH_POST_S + 1))
    assert _call(FakeDb(watched=[late]), BROADCAST, sitting=M3, viewer=CALLER)["games"]
    assert _refused(FakeDb(watched=[dict(early, started_at=MATCHES[2]["started_at"] - timedelta(hours=1))]),
                    match=M3, viewer=CALLER)


def test_the_watched_binding_is_a_named_report_statement():
    """The binding runs through _report_rows like every report statement, so
    the /health probe analyses its tables and columns too (spectate_games,
    spectate_watch_grants); its window constants mirror the broadcaster's."""
    assert main._SESSION_REPORT_NAMED["_REPORT_WATCHED_SQL"] is main._REPORT_WATCHED_SQL
    assert main._REPORT_WATCHED_SQL in main._SESSION_REPORT_STATEMENTS
    src = inspect.getsource(main.get_set_report)
    assert src.count("_report_rows(db, _REPORT_WATCHED_SQL,") == 1
    assert src.index("_REPORT_WATCHED_SQL") < src.index("_REPORT_CALLER_SQL"), "bound before any player read"
    post = strip_comments_only((PLUGIN / "PostSessionReport.cs").read_text(encoding="utf-8"))
    m = re.search(r"WINDOW_PRE_START_SECONDS = ([0-9.]+)f;", post)
    assert m and float(m.group(1)) == main._REPORT_WATCH_PRE_S


class _StatusDb:
    """report-status's two statements over a spectate world with watched-grant
    holders. A grant is a holder's steam id (a grant of the game row's own
    tuple) or a dict of the holder's granted tuple (sid, mode, roster,
    game_started_at, observed_seq). The games statement must JOIN the grants
    and answer each game with the tuple of the caller's grant with the
    greatest observed_seq (round 4 LOW 2, round 5 LOW 1), or the fake
    refuses it."""

    GAMES_SQL = ("SELECT DISTINCT ON (g.id) g.id, l.mode, l.game_started_at AS started_at, g.ended_at, l.roster "
                 "FROM spectate_games g JOIN spectate_watch_grants l "
                 "ON l.game_id = g.id AND l.spectator_steam_id = CAST(:sid AS text) "
                 "WHERE g.id = ANY(CAST(:gids AS uuid[])) "
                 "ORDER BY g.id, l.observed_seq DESC")

    def __init__(self, games, grants, names):
        self.games, self.grants, self.names = games, grants, names
        self.statements = []

    def _grants_of(self, g, sid):
        out = []
        for n, gr in enumerate(self.grants.get(g["id"], ())):
            if isinstance(gr, str):
                gr = {"sid": gr, "mode": g["mode"], "roster": g["roster"],
                      "game_started_at": g["started_at"], "observed_seq": n}
            if gr["sid"] == sid:
                out.append(gr)
        return out

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.statements.append((sql, params))
        if "FROM spectate_games g" in sql:
            assert self.GAMES_SQL in sql, "unexpected games statement: " + sql[:240]
            rows = []
            for g in self.games:
                if g["id"] not in params["gids"]:
                    continue
                mine = self._grants_of(g, params["sid"])
                if mine:
                    last = max(mine, key=lambda gr: gr["observed_seq"])
                    rows.append({"id": g["id"], "mode": last["mode"], "started_at": last["game_started_at"],
                                 "ended_at": g["ended_at"], "roster": last["roster"]})
            return _Res(rows)
        if "FROM players" in sql:
            return _Res([{"steam_id": s, "display_name": n} for s, n in self.names.items() if s in params["sids"]])
        raise AssertionError("unexpected statement: " + sql[:120])


def _status(db, ids, who=None):
    return _run(main.broadcast_report_status(request=None, steam_id=who or BROADCAST,
                                             game_ids=",".join(str(i) for i in ids), db=db))


def test_report_status_answers_only_games_the_seat_watched(broadcast_session):
    """Round 2 M4 / round 3 N1: /broadcast/report-status answers a spectate
    game only when the calling broadcast account holds a watched-grant record
    of it; any other id is omitted, as an id with no row is. Control: with a
    grant on both, both answer - the omission is the grant rule, not the
    lookup."""
    g1, g2 = uuid.uuid4(), uuid.uuid4()
    games = [{"id": g, "mode": "1v1", "started_at": T0, "ended_at": T0 + timedelta(minutes=9),
              "roster": ",".join(sorted((CALLER, OPP)))} for g in (g1, g2)]
    names = {CALLER: "A", OPP: "B"}
    got = _status(_StatusDb(games, {g1: [BROADCAST], g2: [OTHER]}, names), [g1, g2])
    assert [r["game_id"] for r in got] == [str(g1)]
    both = _status(_StatusDb(games, {g1: [BROADCAST], g2: [BROADCAST]}, names), [g1, g2])
    assert [r["game_id"] for r in both] == [str(g1), str(g2)]
    assert both[0]["names"] == ["A", "B"]
    with pytest.raises(HTTPException) as ei:
        _status(_StatusDb(games, {g1: [CALLER]}, names), [g1], who=CALLER)
    assert ei.value.status_code == 403 and ei.value.detail == "broadcast_only"


def test_report_status_answers_the_granted_tuple_not_the_live_row(broadcast_session):
    """Round 4 LOW 2: the seat's grant recorded the watch under roster A-B;
    the spectate game row has since been rewritten to A-C (a participant
    attest). Status answers the GRANTED tuple - mode, roster, names and
    start - and only ended_at from the row. Controls: with a second grant
    under A-C (the seat observed there too) the latest grant answers, and a
    game whose only grant is another account's is omitted."""
    g1, g2 = uuid.uuid4(), uuid.uuid4()
    third = "76561190000000777"
    ab, ac = ",".join(sorted((CALLER, OPP))), ",".join(sorted((CALLER, third)))
    end = T0 + timedelta(minutes=9)
    live = [{"id": g1, "mode": "1v1", "started_at": T0 + timedelta(minutes=2), "ended_at": end, "roster": ac},
            {"id": g2, "mode": "1v1", "started_at": T0, "ended_at": end, "roster": ac}]
    granted = {"sid": BROADCAST, "mode": "1v1", "roster": ab, "game_started_at": T0, "observed_seq": 1}
    names = {CALLER: "A", OPP: "B", third: "C"}
    got = _status(_StatusDb(live, {g1: [granted], g2: [OTHER]}, names), [g1, g2])
    assert got == [{"game_id": str(g1), "mode": "1v1", "started_at": T0.isoformat(), "ended_at": end.isoformat(),
                    "roster": ab, "names": [names[s] for s in ab.split(",")]}], got
    later = dict(granted, roster=ac, observed_seq=2)
    both = _status(_StatusDb(live, {g1: [later, granted]}, names), [g1])
    assert [(r["roster"], r["names"]) for r in both] == [(ac, [names[s] for s in ac.split(",")])], both
    # round 5 LOW 1: the room back on A-B, observed again (the repeat refreshed its order)
    back = _status(_StatusDb(live, {g1: [later, dict(granted, observed_seq=3)]}, names), [g1])
    assert [r["roster"] for r in back] == [ab], back


def test_the_broadcaster_retargets_only_to_the_granted_tuple():
    """Round 4 LOW 2, the client half: ApplyStatus changes the queued
    target's mode and roster only through SessionReportRules.StatusTarget
    (executed in the rules harness: the answer is adopted whole, mode and
    roster together, or not at all), and ApplyRosterFromStatus takes the
    ids StatusTarget returned, never the answer's raw roster."""
    post = PLUGIN / "PostSessionReport.cs"
    apply = _cs_body(post, "private static void ApplyStatus(List<ApiClient.BroadcastReportStatusEntry> list)")
    gate = "if (SessionReportRules.StatusTarget(s.mode, s.roster, out playMode, out grantIds))"
    assert apply.count(gate) == 1
    tail = apply[apply.index(gate):]
    block = tail[:tail.index("}") + 1]
    assert "e.mode = playMode;" in block and "ApplyRosterFromStatus(e, grantIds, s.names);" in block
    assert apply.count("e.mode =") == 1 and apply.count("ApplyRosterFromStatus(") == 1
    assert "s.roster" not in apply.replace(gate, ""), "the raw roster reaches the target only through StatusTarget"
    src = strip_comments_only(post.read_text(encoding="utf-8"))
    assert len(re.findall(r"(?<![\w.])ApplyRosterFromStatus\(", src)) - 1 == 1, "one caller, ApplyStatus"
    roster = _cs_body(post, "private static void ApplyRosterFromStatus(Entry e, string[] ids, List<string> names)")
    assert re.search(r"\.roster\b", roster) is None, "no raw roster field is read there"


def test_the_watched_grant_is_written_once_per_tuple_and_never_changed():
    """Round 3 N1: spectate_watch_grants is written only by the validation
    route, after the lease validated as observed, as an INSERT on its (game,
    spectator, mode, source, roster) tuple inside a savepoint whose conflict
    clause (round 5 LOW 1) sets observed_seq and nothing else - a fresh
    nextval of the sequence, drawn under the room lock; no other statement
    of the api or of any migration after 364 updates or deletes it, and its
    key into spectate_games carries no cascade. The status and report reads
    name it, never spectate_leases."""
    root = PLUGIN.parent
    src = " ".join((root / "backend" / "api" / "main.py").read_text(encoding="utf-8").split())
    assert src.count("INSERT INTO spectate_watch_grants") == 1
    for verb in ("UPDATE spectate_watch_grants", "DELETE FROM spectate_watch_grants",
                 "TRUNCATE spectate_watch_grants", "ALTER TABLE spectate_watch_grants"):
        assert verb not in src, verb
    val = " ".join(inspect.getsource(main.spectate_validate).split())
    assert ("g.started_at, nextval('spectate_watch_grants_observed_seq') FROM spectate_games g "
            "WHERE g.id = CAST(:game_id AS uuid) ON CONFLICT ON CONSTRAINT uq_spectate_watch_grants_tuple "
            "DO UPDATE SET observed_seq = EXCLUDED.observed_seq \"\"\"") in val
    assert val.count("DO UPDATE") == 1 and src.count("spectate_watch_grants_observed_seq") == 1
    assert val.index("SELECT pg_advisory_xact_lock(hashtext(:k))") < val.index("nextval(")
    # Round 4 LOW 1: the binding and the grant share one savepoint, and ok is
    # answered only after both, outside the handler that drops the lease on
    # any failure of either - so ok=True to a request that carried its
    # observed tuple always carries a durable grant (round 5 MEDIUM 1: the
    # released request shape records no watch; see the test below).
    bind = val.index("UPDATE spectate_leases SET bound_actor = :actor")
    ins = val.index("INSERT INTO spectate_watch_grants")
    sp = val.rindex("async with db.begin_nested():", 0, bind)
    assert bind < ins and val.count("async with db.begin_nested():", sp, ins) == 1, \
        "the binding and the grant write share one savepoint"
    handler = val.index("except Exception as ex:", ins)
    ok_at = val.index("if lease is not None: ok = True")
    assert ins < handler < ok_at and "lease = None" in val[handler:ok_at], \
        "a failed grant write refuses the validation"
    assert val.count("ok = True") == 1
    status = " ".join(inspect.getsource(main.broadcast_report_status).split())
    assert "JOIN spectate_watch_grants l" in status and "spectate_leases" not in status
    # Round 5 LOW 1: the recency order is observed_seq alone - never
    # granted_at (the transaction's start) nor id (random)
    assert status.count("ORDER BY g.id, l.observed_seq DESC") == 1
    assert "granted_at" not in status and "l.id" not in status
    assert "spectate_leases" not in main._REPORT_WATCHED_SQL
    sql = root / "backend" / "sql"
    mig = (sql / "364_spectate_watch_grants.sql").read_text(encoding="utf-8")
    body = mig[mig.index("CREATE TABLE IF NOT EXISTS spectate_watch_grants"):]
    body = body[:body.index(");")]
    assert "REFERENCES spectate_games(id)" in body and "ON DELETE" not in body
    assert "UNIQUE (game_id, generation, spectator_steam_id, mode, source_ref, roster)" in body
    assert "observed_seq BIGINT NOT NULL DEFAULT nextval('spectate_watch_grants_observed_seq')" in body
    assert mig.count("CREATE SEQUENCE IF NOT EXISTS spectate_watch_grants_observed_seq AS BIGINT CACHE 1;") == 1
    # Round 4 MEDIUM 1: 364 writes no grant. A pre-364 lease binding recorded
    # no tuple, and the spectate game row's tuple is the room's last attest,
    # so a backfill from it could grant a tuple the seat never observed; the
    # file creates the table, its index, (round 5 LOW 1) the observation
    # sequence and (round 7 MEDIUM 1) the room generation - its sequence, the
    # spectate_games column and the trigger that owns it - and no statement
    # inserts, updates or deletes a row (the trigger's own event list names
    # INSERT and UPDATE; no INSERT INTO, UPDATE ... SET or DELETE FROM).
    code = " ".join(" ".join(l for l in mig.splitlines() if not l.lstrip().startswith("--")).split()).upper()
    for verb in (r"\bINSERT\s+INTO\b", r"\bUPDATE\s+\w+\s+SET\b", r"\bDELETE\b", r"\bTRUNCATE\b",
                 r"SPECTATE_LEASES", r"\bFROM\s+SPECTATE_GAMES\b"):
        assert not re.search(verb, code), ("364 statement", verb)
    assert code.count("CREATE TABLE IF NOT EXISTS") == 1 and code.count("CREATE INDEX IF NOT EXISTS") == 1
    assert code.count("CREATE SEQUENCE IF NOT EXISTS") == 2 and code.count("CREATE OR REPLACE FUNCTION") == 1
    assert code.count("CREATE OR REPLACE TRIGGER") == 1 and code.count("CREATE ") == 6
    assert code.count("ALTER TABLE SPECTATE_GAMES ADD COLUMN IF NOT EXISTS GENERATION BIGINT NOT NULL DEFAULT "
                      "NEXTVAL('SPECTATE_GAMES_GENERATION_SEQ');") == 1 and code.count("ALTER TABLE") == 1
    for f in sorted(sql.glob("*.sql")):
        head = f.name.split("_")[0]
        if head.isdigit() and int(head) > 364:
            low = " ".join(f.read_text(encoding="utf-8").split()).upper()
            for verb in ("UPDATE SPECTATE_WATCH_GRANTS", "DELETE FROM SPECTATE_WATCH_GRANTS",
                         "TRUNCATE SPECTATE_WATCH_GRANTS", "DROP TABLE IF EXISTS SPECTATE_WATCH_GRANTS",
                         "DROP TABLE SPECTATE_WATCH_GRANTS"):
                assert verb not in low, (f.name, verb)


def test_a_watch_is_recorded_only_under_the_tuple_the_master_observed():
    """Round 5 MEDIUM 1, the source half (the PG tests execute it): the
    validation route compares the master's observed tuple with the live row
    it read under the room lock BEFORE any write of the request (drains,
    tombstone clearance, the lease sweep, bindings, grants), and on a
    mismatch rolls back and answers the typed retry result; the grant insert
    runs only for a request that carried a tuple. The client sends the tuple
    it reads with its snapshot, derived by the same two helpers as its
    attest, and handles the retry before the results are parsed (so no kick
    and no roster publish), re-snapshotting a bounded number of times."""
    val = " ".join(inspect.getsource(main.spectate_validate).split())
    lock = val.index("SELECT pg_advisory_xact_lock(hashtext(:k))")
    read = val.index("FROM spectate_games WHERE room_name = :room AND ended_at IS NULL")
    check = val.index("grant_tuple = _spectate_observed_grant_tuple(game, req) if records_watch else None "
                      "if records_watch and grant_tuple is None: await db.rollback() return {\"status\": \"retry\", "
                      "\"reason\": \"participants_changed\", \"results\": []}")
    assert lock < read < check
    for write in ("await _spectate_record_drains(db, game)", "DELETE FROM spectate_drain_tombstones",
                  "DELETE FROM spectate_leases", "UPDATE spectate_leases", "INSERT INTO spectate_watch_grants"):
        assert val.index(write) > check, write
    # round 8 MEDIUM 1: a request that records a watch has the room's
    # authoritative source resolved again, once, under the room lock and
    # after the row read, and compared with the row BEFORE the request is
    # compared with the row and before any write of the request; a row
    # behind the resolution is refused with the typed retry, and the one
    # statement that writes it back is an UPDATE of the room row by its id
    # binding the refresh values (the columns of _SPECTATE_ROW_REFRESHED_COLUMNS)
    resolve = val.index('if records_watch: now_roster, now_ref = await _spectate_authoritative_roster('
                        'db, game["mode"], req.room_name)')
    assert val.count("_spectate_authoritative_roster(") == 1
    agree = val.index("agrees, refresh = _spectate_row_agrees_with_resolution( "
                      "game, _spectate_resolved_room_values(now_roster, now_ref))")
    refuse = val.index("if not agrees:", agree)
    answer = val.index('return {"status": "retry", "reason": "source_changed", "results": []}', refuse)
    assert read < resolve < agree < refuse < answer < check and val.count('"source_changed"') == 1
    back = re.findall(r'UPDATE spectate_games SET (.*?) WHERE id = :gid\W', val)
    assert len(back) == 1 and val.count("UPDATE spectate_games") == 1, back
    assert [c.split("=")[0].strip() for c in back[0].split(",")] == list(main._SPECTATE_ROW_REFRESHED_COLUMNS)
    assert all(c.split("=")[1].strip() == ":" + c.split("=")[0].strip() for c in back[0].split(","))
    wb = val.index("UPDATE spectate_games")
    assert refuse < val.index("if refresh:", refuse) < wb < val.index("await db.commit()", wb) < answer
    assert val.index('{**refresh, "gid": str(game["id"])}', wb) < answer
    assert refuse < val.index("else: await db.rollback()", refuse) < answer
    # round 6: all four observed values or none (some without the others: 422)
    assert val.count("sent = [getattr(req, field) is not None for field, _c, _g in "
                     "_SPECTATE_GRANT_OBSERVED_TUPLE] if any(sent) and not all(sent): raise HTTPException("
                     "status_code=422, detail=\"observed_tuple_incomplete\") records_watch = all(sent)") == 1
    assert val.count("if lease is not None and grant_tuple is not None: await db.execute(text(\"\"\" "
                     "INSERT INTO spectate_watch_grants") == 1
    fields = main.SpectateValidateBody.model_fields
    for field, _row, _grant in main._SPECTATE_GRANT_OBSERVED_TUPLE:
        assert fields[field].default is None, field
    assert sorted(f for f in fields if f.startswith("observed_")) == \
        sorted(f for f, _r, _g in main._SPECTATE_GRANT_OBSERVED_TUPLE)

    api = strip_comments_only((PLUGIN / "ApiClient.cs").read_text(encoding="utf-8"))
    body = _cs_body(PLUGIN / "ApiClient.cs", "private static void SpectateValidateActors(int attempt)")
    assert "GameStateWatcher.SpectateModeOfRoomPrefix(roomAtSend)" in body
    assert "GameStateWatcher.SpectateFighterIds(RoomActors.ActiveFighters())" in body
    # the tuple goes out when the snapshot has a fighter id AND this seat
    # holds the server's answer to its last attest of the same room, mode
    # and roster; exactly that condition guards the four fields, each sent
    # once (a mutant that never sends them, sends them under any other
    # condition, or drops the attest answer's check fails here; controls
    # R5M1-e, R6M1-h)
    flat = " ".join(body.split())
    assert flat.count('if (seenMode.Length == 0) seenMode = "1v1";') == 1
    assert flat.count("bool sendTuple = seenRoster.Length > 0 && SpectateAttestAnswerFor( "
                      "roomAtSend, seenMode, seenRoster, out seenGameId, out seenSource, out seenGeneration);") == 1
    # round 7: the generation goes out as a bare number, and only a value
    # SpectateGenerationToken accepted (digits) can reach it
    assert flat.count(r'if (sendTuple) sb.Append($"\"observed_game_id\":\"{Escape(seenGameId)}\",") '
                      r'.Append($"\"observed_generation\":{seenGeneration},") '
                      r'.Append($"\"observed_mode\":\"{Escape(seenMode)}\",") '
                      r'.Append($"\"observed_source_ref\":\"{Escape(seenSource)}\",") '
                      r'.Append($"\"observed_roster\":\"{Escape(seenRoster)}\",");') == 1
    for f, _r, _g in main._SPECTATE_GRANT_OBSERVED_TUPLE:
        assert flat.count('\\"%s\\":' % f) == 1, f
    assert flat.count("if (sendTuple)") == 1 and flat.count("sendTuple") == 3
    assert flat.count("if (!sendTuple && seenRoster.Length > 0) GameStateWatcher.RequestSpectateAttestSoon();") == 1
    # the attest answer is kept only for the room, mode and roster it answered
    note = " ".join(_cs_body(PLUGIN / "ApiClient.cs", "internal static void NoteSpectateAttestAnswer("
                             "bool ok, string resp, string room, string mode, string roster)").split())
    assert 'ExtractJsonString(resp, "status") != "ok"' in note
    assert 'spectateAttestAnswerGameId = ExtractJsonString(resp, "game_id");' in note
    assert 'spectateAttestAnswerSourceRef = ExtractJsonString(resp, "source_ref");' in note
    # round 7: the generation is kept only when it is a digits token, and an
    # answer without one clears the room's answer like any refusal
    assert 'string generation = ExtractJsonIdToken(resp, "generation");' in note
    assert "|| !SpectateGenerationToken(generation))" in note
    assert "spectateAttestAnswerGeneration = generation;" in note
    assert "spectateAttestAnswerGeneration = \"\";" in note
    answer_for = " ".join(_cs_body(PLUGIN / "ApiClient.cs", "internal static bool SpectateAttestAnswerFor("
                                   "string room, string mode, string roster,").split())
    for kept in ("spectateAttestAnswerRoom", "spectateAttestAnswerMode", "spectateAttestAnswerRoster"):
        assert answer_for.count("if (!string.Equals(%s," % kept) == 1, kept
    assert answer_for.count("if (!SpectateGenerationToken(spectateAttestAnswerGeneration)) return false;") == 1
    assert answer_for.count("generation = spectateAttestAnswerGeneration;") == 1
    token = " ".join(_cs_body(PLUGIN / "ApiClient.cs", "internal static bool SpectateGenerationToken(string s)").split())
    assert "if (string.IsNullOrEmpty(s) || s.Length > 18 || s[0] == '0') return false;" in token
    assert "if (s[i] < '0' || s[i] > '9') return false;" in token
    # round 7 MEDIUM 1 (a): the attest takes the room lock BEFORE it resolves
    # the source it writes, and answers what it read back from the row it
    # wrote, under that lock, before its commit
    att = " ".join(inspect.getsource(main.spectate_participant_attest).split())
    lock_at = att.index("SELECT pg_advisory_xact_lock(hashtext(:k))")
    assert att.count("SELECT pg_advisory_xact_lock(") == 1
    first = att.index("await _spectate_authoritative_roster(db, req.mode, req.room_name)")
    assert lock_at < first
    # round 8 MEDIUM 1: and resolves it a second time, under the same lock,
    # after its last write of the room and the attestation and before the
    # read-back; a source that moved is written to the row, which the answer
    # then names; a roster that moved refuses the attest (as the first check,
    # the server-held set of a readmission lobby or a flagged stage 2 room
    # counted as present, exact equality elsewhere)
    assert att.count("_spectate_authoritative_roster(") == 2
    final = att.index("final_roster, final_ref = await _spectate_authoritative_roster(db, req.mode, req.room_name)")
    wrote = att.index("SELECT id, source_ref, generation FROM spectate_games WHERE id = :gid")
    assert first < att.index("INSERT INTO spectate_attestations") < final < wrote
    assert att.count("if final_roster is not None: if not final_roster: raise HTTPException(status_code=409, "
                     "detail=\"room_unknown\") _final_ok = await _rdm_attest_check(db, req.mode, final_ref, "
                     "roster, final_roster, req.steam_id) _final_held = await _s2_spectate_held(db, req.mode, "
                     "final_ref, req.room_name) if _final_held is not None: _final_ok = _rdm_attest_ok(roster, "
                     "final_roster, _final_held, req.steam_id) elif _s2_short: raise HTTPException(status_code=422, "
                     "detail=\"bad_cardinality\") if _final_ok is not None: if not _final_ok: raise HTTPException("
                     "status_code=409, detail=\"roster_mismatch\") elif set(roster) != final_roster or "
                     "req.steam_id not in final_roster: raise HTTPException(status_code=409, "
                     "detail=\"roster_mismatch\")") == 1
    rewrite = att.index('if final_ref[:64] != derived_ref[:64]: await db.execute(text("UPDATE spectate_games SET '
                        'source_ref = :ref WHERE id = :gid"), {"ref": final_ref[:64], "gid": str(game["id"])})')
    assert final < rewrite < wrote
    assert lock_at < wrote < att.index("await db.commit()") and att.count("await db.commit()") == 1
    assert att.count('return {"status": "ok", "game_id": str(wrote["id"]), "source_ref": wrote["source_ref"], '
                     '"generation": int(wrote["generation"])}') == 1
    attest = " ".join(_cs_body(PLUGIN / "ApiClient.cs", "public static void SpectateAttest(").split())
    assert attest.count("NoteSpectateAttestAnswer(ok, resp, attestedRoom, attestedMode, attestedRoster);") == 1
    assert 'string attestedMode = mode ?? "", attestedRoster = rosterCsv ?? "", attestedRoom = roomName ?? "";' \
        in attest
    assert '+ $"\\"roster\\":\\"{Escape(rosterCsv ?? "")}\\""' in attest, "the roster kept is the one sent"
    retry = body.index('if (ExtractJsonString(resp, "status") == "retry")')
    assert retry < body.index('int arr = resp.IndexOf("\\"results\\"", StringComparison.Ordinal);')
    assert body.count("if (attempt < SPECTATE_VALIDATE_RETRY_MAX)") == 1
    assert body.count("SpectateValidateRetryAfter(attempt + 1, roomAtSend)") == 1
    assert re.search(r"internal const int SPECTATE_VALIDATE_RETRY_MAX = [1-5];", api)
    assert "public static void SpectateValidateActors() { SpectateValidateActors(0); }" in api
    tick = _cs_body(PLUGIN / "GameStateWatcher.cs", "private static void TickSpectateAttest()")
    assert tick.count("string mode = SpectateModeOfRoomPrefix(room);") == 1
    assert tick.count("var sids = SpectateFighterIds(fighters);") == 1
    assert "sids.Sort(" not in tick and "StartsWith(\"team_\"" not in tick, "one derivation, shared"
    assert _cs_body(PLUGIN / "GameStateWatcher.cs", "internal static void RequestSpectateAttestSoon()").split() \
        == ["{", "spectateAttestEdgePending", "=", "true;", "}"]


def _sql_list(s):
    """Top-level comma split of a SQL expression list."""
    out, depth, cur = [], 0, ""
    for ch in s:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return out + [cur.strip()]


def test_the_grant_copies_no_room_value_it_did_not_compare():
    """Round 6 MEDIUM 1 (b), the structural guarantee: a watch grant takes
    its tuple from ONE place, main._SPECTATE_GRANT_OBSERVED_TUPLE, which is
    also the compared set. The comparator iterates that definition and
    returns the request's own values keyed by grant column; the grant insert
    binds exactly that mapping, names every tuple column as its own bind
    parameter (never a room-row column), and reads from the room row only
    started_at, by the compared game id. Every other column the insert names
    is declared in _SPECTATE_GRANT_OTHER_COLUMNS, and every column of the
    table (364) is either named by the insert or filled by a default that
    reads no row. started_at is a property of the game id: no statement of
    the api writes it after the row's insert. A column copied into the grant
    without being in the compared set fails one of these."""
    tup = main._SPECTATE_GRANT_OBSERVED_TUPLE
    other = main._SPECTATE_GRANT_OTHER_COLUMNS
    grant_cols = [g for _f, _r, g in tup]
    assert len(set(grant_cols)) == len(grant_cols) and not set(grant_cols) & set(other)
    # the comparator: every entry compared, the request's value kept
    cmp_src = " ".join(inspect.getsource(main._spectate_observed_grant_tuple).split())
    assert cmp_src.count("for field, row_column, grant_column in _SPECTATE_GRANT_OBSERVED_TUPLE:") == 1
    assert cmp_src.count("seen = _spectate_observed_canon(row_column, getattr(req, field)) "
                         "if seen != _spectate_observed_canon(row_column, game[row_column]): return None "
                         "got[grant_column] = seen") == 1
    assert cmp_src.count("return") == 2 and "game[" not in cmp_src.replace("game[row_column]", "")
    # every compared row column is read by the route's own row read
    val_raw = inspect.getsource(main.spectate_validate)
    val = " ".join(val_raw.split())
    marker = "game = (await db.execute(text(\"\"\" SELECT "
    row_read = val[val.index(marker) + len(marker):]
    row_read = row_read[:row_read.index(" FROM spectate_games WHERE room_name = :room AND ended_at IS NULL")]
    for _f, row_col, _g in tup:
        assert row_col in _sql_list(row_read), row_col
    # the insert: its column list is the definition's columns, then the declared others
    ins = val[val.index("INSERT INTO spectate_watch_grants"):]
    ins = ins[:ins.index('"""')]
    assert val.count("INSERT INTO spectate_watch_grants") == 1
    cols = _sql_list(ins[ins.index("(") + 1:ins.index(")")])
    assert cols == grant_cols + list(other), cols
    select = ins[ins.index(" SELECT ") + 8:ins.index(" FROM spectate_games g ")]
    exprs = dict(zip(cols, _sql_list(select)))
    assert len(_sql_list(select)) == len(cols)
    for g in grant_cols:
        assert re.fullmatch(r"CAST\(:%s AS (text|uuid|bigint)\)" % g, exprs[g]), (g, exprs[g])
    assert exprs["spectator_steam_id"] == "CAST(:sid AS text)"
    assert exprs["game_started_at"] == "g.started_at"
    assert exprs["observed_seq"] == "nextval('spectate_watch_grants_observed_seq')"
    assert re.findall(r"\bg\.(\w+)", select) == ["started_at"], "the only room-row value the grant reads"
    assert ins[ins.index(" FROM spectate_games g "):].split(" ON CONFLICT ")[0].strip() == \
        "FROM spectate_games g WHERE g.id = CAST(:game_id AS uuid)"
    assert val.count('"""), {**grant_tuple, "sid": entry.steam_id})') == 1
    assert val.count("grant_tuple = _spectate_observed_grant_tuple(game, req) if records_watch else None") == 1
    assert val.count("grant_tuple =") == 1
    # the table: every column named by the insert, or a default reading no row
    mig = (PLUGIN.parent / "backend" / "sql" / "364_spectate_watch_grants.sql").read_text(encoding="utf-8")
    head = "CREATE TABLE IF NOT EXISTS spectate_watch_grants ("
    body = mig[mig.index(head) + len(head):]
    body = body[:body.index(");")]
    table = {}
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if line and not line.startswith(("CONSTRAINT", "UNIQUE", "--")):
            table[line.split()[0]] = line
    assert set(table) - set(cols) == {"id", "granted_at"}, sorted(table)
    assert "DEFAULT gen_random_uuid()" in table["id"] and "DEFAULT NOW()" in table["granted_at"]
    assert set(cols) <= set(table)
    # Round 7 MEDIUM 1 (b): the grant's unique tuple is the definition's
    # columns and the seat, so a return of the room to earlier values (a new
    # generation) is a new grant row and the recorded generation never changes
    unique = re.search(r"UNIQUE \(([^)]*)\)", body).group(1)
    assert [c.strip() for c in unique.split(",")] == [grant_cols[0], grant_cols[1]] + \
        ["spectator_steam_id"] + grant_cols[2:], unique
    # ... and the room row's generation: the definition carries it, and the
    # trigger of 364 draws a new one on every INSERT and on every UPDATE that
    # changes any OTHER spectate_games column of the definition, keeps the old
    # one otherwise, and replaces whatever value a statement supplied
    row_cols = [r for _f, r, _g in tup]
    assert "generation" in row_cols and ("observed_generation", "generation", "generation") in tup
    fn = mig[mig.index("CREATE OR REPLACE FUNCTION spectate_games_generation_advance()"):]
    fn = " ".join(fn[:fn.index("$$;")].split())
    advanced = re.findall(r"NEW\.(\w+) IS DISTINCT FROM OLD\.(\w+)", fn)
    assert all(a == b for a, b in advanced) and sorted(a for a, _b in advanced) == \
        sorted(set(row_cols) - {"generation"}), advanced
    cond = fn[fn.index("ELSIF ") + 6:fn.index(" THEN NEW.generation := nextval('spectate_games_generation_seq');"
                                               " ELSE")]
    assert cond.split(" OR ") == ["NEW.%s IS DISTINCT FROM OLD.%s" % (c, c) for c, _o in advanced], cond
    assert fn.count("IF TG_OP = 'INSERT' THEN NEW.generation := nextval('spectate_games_generation_seq');") == 1
    assert fn.count("ELSE NEW.generation := OLD.generation; END IF; RETURN NEW;") == 1
    assert fn.count("NEW.generation :=") == 3 and fn.count("nextval(") == 2
    trig = " ".join(mig[mig.index("CREATE OR REPLACE TRIGGER"):].split())
    assert trig.startswith("CREATE OR REPLACE TRIGGER trg_spectate_games_generation BEFORE INSERT OR UPDATE ON "
                           "spectate_games FOR EACH ROW EXECUTE FUNCTION spectate_games_generation_advance();")
    # started_at is never written after the row's insert (nor the id)
    src = " ".join((PLUGIN.parent / "backend" / "api" / "main.py").read_text(encoding="utf-8").split())
    updates = [m.start() for m in re.finditer(r"UPDATE spectate_games\b", src)]
    assert len(updates) >= 4
    for at in updates:
        stmt = src[at:src.index(" WHERE ", at)]
        assert not re.search(r"\b(started_at|id)\s*=", stmt.split(" SET ", 1)[1]), stmt[:160]
    # Round 8 MEDIUM 1: the compared set grew by the resolution. The room
    # values the authoritative resolution decides are row columns of the one
    # definition (so a grant records them only as compared values, and they
    # equal the resolution when it is written); the resolution helper answers
    # exactly those keys; the agreement iterates that tuple; what a
    # validation writes back is a subset of it
    resolved = main._SPECTATE_GRANT_RESOLVED_COLUMNS
    assert set(resolved) <= set(row_cols) - {"id", "generation", "mode"} and len(set(resolved)) == len(resolved)
    assert set(main._SPECTATE_ROW_REFRESHED_COLUMNS) <= set(resolved)
    assert tuple(main._spectate_resolved_room_values({"b", "a"}, "s")) == resolved
    agree_src = " ".join(inspect.getsource(main._spectate_row_agrees_with_resolution).split())
    assert agree_src.count("for col in _SPECTATE_GRANT_RESOLVED_COLUMNS if col in resolved") == 1
    assert agree_src.count("_spectate_observed_canon(col, resolved[col]) != _spectate_observed_canon(col, game[col])") == 1
    assert agree_src.count("if col in _SPECTATE_ROW_REFRESHED_COLUMNS") == 1


def test_the_validation_grants_only_what_the_resolution_agrees_with():
    """Round 8 MEDIUM 1, the agreement check by behaviour (the PG tests run
    it through the routes): the resolution decides the source always and the
    roster when the server has one; a row agreeing in every decided value
    (rosters as sets) agrees; a row behind in the source disagrees and is
    written back to the resolved source; a row behind in the roster
    disagrees and nothing is written back; no mapping where one must exist
    (an empty roster) disagrees with nothing to write back. Negative
    controls: a 1v1 fallback resolution (no roster) never refuses on the
    roster; the source is cut to 64 characters as the attest cuts it."""
    ab, ba = "p1,p2", "p2,p1"
    ids = {"p1", "p2"}
    row = {"source_ref": "x", "roster": ab}
    values = main._spectate_resolved_room_values
    agree = main._spectate_row_agrees_with_resolution
    assert values(ids, "x") == {"source_ref": "x", "roster": ab}
    assert values(None, "x") == {"source_ref": "x"} and values(set(), "") is None
    assert values(None, "y" * 80) == {"source_ref": "y" * 64}
    assert agree(row, values(ids, "x")) == (True, {})
    assert agree({**row, "roster": ba}, values(ids, "x")) == (True, {})
    assert agree(row, values(ids, "y")) == (False, {"source_ref": "y"})
    assert agree(row, values(ids | {"p3"}, "x")) == (False, {})
    assert agree(row, values(ids | {"p3"}, "y")) == (False, {"source_ref": "y"})
    assert agree(row, values(set(), "")) == (False, {})
    assert agree({**row, "roster": "p9"}, values(None, "x")) == (True, {})
    assert agree(row, values(None, "")) == (False, {"source_ref": ""})


# -- board row 30g: the broadcaster pages through the session report ------------

POST = PLUGIN / "PostSessionReport.cs"


def test_the_broadcaster_asks_for_the_watched_sets_report():
    """Board row 30g: once the history fetches are done the engine anchors the
    set's report on the newest game of the screens' own selection
    (SessionReportRules.NewestAnchor, executed by the client harness) and
    asks the route for that game's sitting as a player who played it; the
    screens it built are kept as the fallback."""
    fetch = _cs_body(POST, "private static void TickFetch(float now)")
    assert "anchor = SessionAnchor(e, f, out viewer);" in fetch
    assert "_fallbackPages = pages;" in fetch and "BeginReportFetch(e, anchor, viewer, now);" in fetch
    assert fetch.index("pages = BuildPages(e, f);") < fetch.index("SessionAnchor(e, f, out viewer)")
    assert "EnterPlayback(e, null, pages);" in fetch, "no anchor: the screens play (through the gate)"
    anchor = _cs_body(POST, "private static string SessionAnchor(Entry e, FetchBox f, out string viewer)")
    assert "SessionReportRules.NewestAnchor(games, lo, hi, idA, e.rosterIds, out viewer)" in anchor
    assert "GetWindow(e, out lo, out hi);" in anchor
    for same in ("TeamRosterMatches(s, rosterSet)", "TeamMatchesInWindow(s, lo, hi)",
                 "FfaSessionMatches(e, f, lo, hi)", "m.opponent_steam_id, idB", "!pl.absent"):
        assert same in anchor, same
    begin = _cs_body(POST, "private static void BeginReportFetch(Entry e, string anchor, string viewer, float now)")
    assert ('ApiClient.FetchSessionReport("sitting", anchor, viewer, (ok, body) => OnReportFetched(gen, ok, body));'
            in begin)
    assert "_phase = PHASE_REPORT_FETCH;" in begin


def test_the_report_plays_through_the_f5_model_and_view():
    got = _cs_body(POST, "private static void OnReportFetched(int gen, bool ok, string body)")
    assert "if (gen != _gen || _phase != PHASE_REPORT_FETCH) return;" in got
    assert "SessionReportRules.Parse(body)" in got and "SessionReportModel.Build(env)" in got
    assert "EnterPlayback(_current, model, null);" in got
    draw = _cs_body(POST, "public static void Draw()")
    assert "SessionReportView.DrawBroadcast(_srModel, _pageIdx)" in draw
    assert draw.index("NativeUI.IsOpen") < draw.index("DrawBroadcast"), "F5 open still hides the report"
    view = PLUGIN / "SessionReportView.cs"
    b = _cs_body(view, "internal static int DrawBroadcast(SessionReportModel.Model m, int pg)")
    for same in ("DrawHeader(content, m);", "MeasureBuildPages(body, m);", "DrawPage(body, m, pg);",
                 "PageLine(m, pg, pages)", "SessionReportModel.FIXED_PAGES + Mathf.Max(1, buildPages)"):
        assert same in b, same
    for input_ in ("GUI.Button", ".Use()", "HandleKey", "Close()", "NativeUI.IsOpen"):
        assert input_ not in b, "the broadcast draw takes no input: " + input_
    f5 = _cs_body(view, "public static void Draw()")
    assert "DrawHeader(content, model);" in f5 and "BodyRect(content)" in f5


def test_every_page_once_one_dwell_each_then_on():
    tick = _cs_body(POST, "public static void Tick(bool directorIdleNoTicket)")
    assert "SessionReportRules.BroadcastNextPage(_pageIdx, _srPageCount)" in tick
    assert "if (next < 0) { Consume(); return; }" in tick
    assert "SessionReportRules.BroadcastPageDwell(PageSecondsConfigured())" in tick
    assert "if (_phase == PHASE_REPORT_FETCH) { TickReportFetch(now); return; }" in tick
    play = _cs_body(POST, "private static void PlaySessionReport(SessionReportModel.Model model)")
    assert "_pageRemaining = SessionReportRules.BroadcastPageDwell(PageSecondsConfigured());" in play
    assert "_srPageCount = SessionReportModel.FIXED_PAGES + 1;" in play
    draw = _cs_body(POST, "public static void Draw()")
    assert "if (measured > 0) _srPageCount = measured;" in draw
    cfg = _cs_body(POST, "private static float PageSecondsConfigured()")
    assert "Plugin.BroadcastSessionReportPageSeconds.Value" in cfg
    plugin = strip_comments_only((PLUGIN / "Plugin.cs").read_text(encoding="utf-8"))
    m = re.search(r'Config\.Bind\(\s*"Broadcast", "SessionReportPageSeconds", ([0-9.]+)f,', plugin)
    rules = strip_comments_only((PLUGIN / "SessionReportRules.cs").read_text(encoding="utf-8"))
    d = re.search(r"BROADCAST_PAGE_SECONDS = ([0-9.]+)f", rules)
    assert m and d and float(m.group(1)) == float(d.group(1)) == 12.0


def test_the_kind_stays_report_and_the_screens_are_the_fallback():
    """The director's scene choice (idle_content) and the bot's thumbnail gate
    (report_screen == "report") key on the kind: every session report page is
    "report". A report that cannot be had plays the screens instead."""
    screen = _cs_body(POST, "public static string CurrentScreenKind")
    assert 'if (_srModel != null) return "report";' in screen
    assert screen.index('if (_srModel != null) return "report";') < screen.index('"graphs"')
    fb = _cs_body(POST, "private static void ReportFallback(string why)")
    assert "EnterPlayback(e, null, pages);" in fb
    tr = _cs_body(POST, "private static void TickReportFetch(float now)")
    assert "SR_FETCH_DEADLINE" in tr and "ReportFallback(" in tr
    got = _cs_body(POST, "private static void OnReportFetched(int gen, bool ok, string body)")
    assert got.count("ReportFallback(") == 3, "fetch failure, build failure and a non-envelope body"


def test_every_door_into_playback_asks_the_stream_now():
    """Round 2 M3: the report GET can take up to SR_FETCH_DEADLINE, so the
    stream may die while it runs. Every path out of a fetch - no anchor,
    success, HTTP failure, the timeout, a non-envelope body - enters playback
    through EnterPlayback, whose SessionReportRules.PlaybackAfterFetch asks the
    stream at that moment (the harness drives it with a stream that goes down
    mid-fetch); a dead stream defers the set with the first gate's own
    DeferEntry. PlaySessionReport and PlayScreens have no other caller, so no
    later edit can add a door that skips the gate without failing here."""
    src = strip_comments_only(POST.read_text(encoding="utf-8"))
    door = _cs_body(POST, "private static void EnterPlayback(Entry e, SessionReportModel.Model model, List<Page> pages)")
    assert "SessionReportRules.PlaybackAfterFetch(model != null, StreamLiveNow, IsDevEntry(e))" in door
    assert door.index("PLAYBACK_DEFER") < door.index("PlaySessionReport(model)") < door.index("PlayScreens(e, pages)")
    assert "DeferEntry(e);" in door
    for callee, sig in (("PlaySessionReport(", "private static void PlaySessionReport(SessionReportModel.Model model)"),
                        ("PlayScreens(", "private static void PlayScreens(Entry e, List<Page> pages)")):
        calls = len(re.findall(r"(?<![\w.])" + re.escape(callee), src)) - 1   # minus the definition
        assert calls == 1 and door.count(callee) == 1, "%s is called %d times; the only call is EnterPlayback's" % (callee, calls)
    assert len(re.findall(r"(?<![\w.])EnterPlayback\(", src)) - 1 == 3, "no anchor, success, the fallback"
    fb = _cs_body(POST, "private static void ReportFallback(string why)")
    assert "EnterPlayback(e, null, pages);" in fb
    assert "ReportFallback(" in _cs_body(POST, "private static void TickReportFetch(float now)"), "the timeout"
    got = _cs_body(POST, "private static void OnReportFetched(int gen, bool ok, string body)")
    assert got.count("ReportFallback(") == 3 and "EnterPlayback(_current, model, null);" in got
    fetch = _cs_body(POST, "private static void TickFetch(float now)")
    assert "if (!SessionReportRules.PlaybackMayStart(StreamLiveNow, IsDevEntry(e)))" in fetch and "DeferEntry(e);" in fetch
    assert "BroadcastMode.StreamInfoLive" not in fetch, "one shared gate, not a copy"
    assert "private static bool StreamLiveNow() => BroadcastMode.StreamInfoLive;" in src
    defer = _cs_body(POST, "private static void DeferEntry(Entry e)")
    assert "_phase = PHASE_NONE;" in defer and "_current = null;" in defer and "_gen++;" in defer
    assert "_queue.Remove" not in defer, "a deferred set stays queued"


def test_the_viewer_rides_only_when_named_and_well_formed():
    api = PLUGIN / "ApiClient.cs"
    body = _cs_body(api, "public static void FetchSessionReport(string selector, string key, string viewer, Action<bool, string> callback)")
    assert 'if (named) url += "&viewer=" + viewer;' in body
    assert "viewer.Length != 17" in body and "ch < '0' || ch > '9'" in body
    whole = strip_comments_only(api.read_text(encoding="utf-8"))
    assert "=> FetchSessionReport(selector, key, null, callback);" in whole, "the F5 view names no viewer"


def test_the_watched_set_lever_replays_a_recorded_set_through_the_pipeline():
    dev = _cs_body(POST, "internal static void DevWatchSet(string gameId)")
    assert "NotePairActivated(_devGameId," in dev and "NoteTargetGone(_devGameId);" in dev
    tick = _cs_body(POST, "public static void Tick(bool directorIdleNoTicket)")
    assert "if (!streamLive && !IsDevEntry(e)) return;" in tick
    fetch = _cs_body(POST, "private static void TickFetch(float now)")
    assert "if (!SessionReportRules.PlaybackMayStart(StreamLiveNow, IsDevEntry(e)))" in fetch
    plugin = PLUGIN / "Plugin.cs"
    lever = _cs_body(plugin, "private void TickTestWatchedSet()")
    assert "!BroadcastMode.IsBroadcastIdentity" in lever and "PostSessionReport.DevWatchSet(raw);" in lever
    # Round 2 M4: the lever refuses unless the configured API is a local test
    # server (SessionReportRules.DevLeverApiAllowed, executed by the harness),
    # asked before the set is queued, and its refusal says so.
    gate = "if (!SessionReportRules.DevLeverApiAllowed(ApiClient.BaseUrl, out apiHost))"
    assert gate in lever and lever.index(gate) < lever.index("PostSessionReport.DevWatchSet(raw);")
    assert "test watched set refused: the configured API (" in lever and "is production" in lever
    post = strip_comments_only(POST.read_text(encoding="utf-8"))
    whole = "".join(strip_comments_only(p.read_text(encoding="utf-8")) for p in sorted(PLUGIN.glob("*.cs")))
    assert whole.count("PostSessionReport.DevWatchSet(") == 1, "the lever is the only way in"
    assert post.count("DevWatchSet(") == 1, "no caller inside PostSessionReport either"
    assert "if (_lastTestWatchedSet == null) { _lastTestWatchedSet = raw; return; }" in lever
    assert strip_comments_only(plugin.read_text(encoding="utf-8")).count("try { TickTestWatchedSet(); } catch { }") == 1


# -- board row 30f: the witness lever -------------------------------------------


def test_the_witness_lever_opens_a_set_at_a_page():
    """[Broadcast] TestSessionReport opens the F5 session report on a set and
    turns it to a page for the in-game witness (the history row's Session
    button is a click the witness cannot give the overlay, #420): broadcast
    identity only, a NEW value only, and a value that arrives while the F5
    page is closed waits for it instead of being spent."""
    plugin = PLUGIN / "Plugin.cs"
    lever = _cs_body(plugin, "private void TickTestSessionReport()")
    assert "!BroadcastMode.IsBroadcastIdentity" in lever
    assert "if (_lastTestSessionReport == null) { _lastTestSessionReport = raw; return; }" in lever
    wait = lever.index("if (raw.Length > 0 && !NativeUI.IsOpen) return;")
    assert lever.index("_lastTestSessionReport = raw;", wait) > wait, "the value is spent only once the page is open"
    assert lever.index("SessionReportView.DevDirective(raw);") > wait
    whole = strip_comments_only(plugin.read_text(encoding="utf-8"))
    assert whole.count("try { TickTestSessionReport(); } catch { }") == 1
    assert '"Broadcast", "TestSessionReport", "",' in whole


def test_the_lever_turns_the_open_sets_page_after_the_measure():
    view = PLUGIN / "SessionReportView.cs"
    d = _cs_body(view, "internal static void DevDirective(string raw)")
    assert "Close();" in d
    assert "bool same = Active && sel == openSelector && key == openKey;" in d
    assert "if (!same) NativeUI.OpenSessionReport(sel, key);" in d
    assert d.index("NativeUI.OpenSessionReport(sel, key)") < d.index("devPage = want - 1;"), "Open resets the page: the ask comes after it"
    draw = _cs_body(view, "public static void Draw()")
    measure = draw.index("MeasureBuildPages(body, model)")
    apply = draw.index("if (devPage >= 0 && model != null)")
    clamp = draw.index("page = Mathf.Clamp(page, 0, PageCount() - 1);")
    assert measure < apply < clamp, "the page is asked of the measured count and still clamped"
    op = _cs_body(view, "public static void Open(string selector, string key)")
    assert "openSelector = selector;" in op and "openKey = key;" in op
    cl = _cs_body(view, "public static void Close()")
    assert "devPage = -1;" in cl and "openSelector = null;" in cl


# -- round 2 L1: an empty chart says whether the set or the mode lacks it -----

def test_an_empty_chart_says_whether_the_set_or_the_mode_lacks_it():
    """Round 2 L1: no report surface reads "not recorded for this mode" any
    more; every chart, bar set, table and the game-length strip takes its
    empty text from MissingText(kind, metric) with its own metric."""
    model = PLUGIN / "SessionReportModel.cs"
    view = PLUGIN / "SessionReportView.cs"
    for p in sorted(PLUGIN.glob("*.cs")):
        if p.name in ("I18nCatalogues.cs", "I18nSourceKeys.g.cs"):
            continue
        assert "not recorded for this mode" not in strip_comments_only(p.read_text(encoding="utf-8")), p.name
    mt = _cs_body(model, "private static string MissingText(string kind, string metric)")
    assert "MissingReason(kind, metric) == MISSING_MODE" in mt
    assert 'I18n.Tr("not supported for this mode")' in mt and 'I18n.Tr("not recorded for this set")' in mt
    build = _cs_body(model, "internal static Model Build(Envelope env)")
    for panel, met in (("m.Damage", "MET_DAMAGE"), ("m.Dps", "MET_DAMAGE"), ("m.HitPct", "MET_HIT"),
                       ("m.BlockPct", "MET_BLOCK"), ("m.Ping", "MET_PING"), ("m.Fps", "MET_FPS")):
        assert build.count(f"Finish({panel}, MissingText(m.Kind, {met}));") == 1, panel
    assert "FinishRace(m, env, MissingText(m.Kind, MET_SCORE));" in build
    assert "m.StripMissing = MissingText(m.Kind, MET_DURATION);" in build
    assert "Finish(pn," not in build, "no panel keeps a shared text"
    totals = _cs_body(model, "private static void BuildTotalsPages(Model m, Envelope env)")
    assert "m.Combat.Missing = MissingText(m.Kind, MET_COMBAT);" in totals
    assert "m.Play.Missing = MissingText(m.Kind, MET_PLAY);" in totals
    for bars, met in (("m.DamageBars", "MET_DAMAGE_TOTAL"), ("m.KillsBars", "MET_KILLS"),
                      ("m.GoldBars", "MET_GOLD"), ("m.XpBars", "MET_XP")):
        at = totals.index(bars + " = MakeBars(")
        call = totals[at:totals.index(";", at)]
        assert call.rstrip().endswith(f"MissingText(m.Kind, {met}))"), call
    make = _cs_body(model, "private static Bars MakeBars(string title")
    assert "if (!any) b.Missing = missing;" in make
    players = _cs_body(view, "private static void DrawPlayersPage(Rect body, SessionReportModel.Model m)")
    assert "m.Combat, m.Combat.Missing);" in players and "m.Play, m.Play.Missing);" in players
    strip = _cs_body(view, "private static void DrawStrip(Rect r, SessionReportModel.Model m)")
    assert '"<color=#8FA3B8>" + m.StripMissing + "</color>"' in strip


def _carries_lists():
    """The client's per-mode lists, read from SessionReportRules.cs: the
    metric constants and each CARRIES_<MODE> array, as sets of names."""
    text = strip_comments_only((PLUGIN / "SessionReportRules.cs").read_text(encoding="utf-8"))
    consts = dict(re.findall(r'\b(MET_[A-Z_]+) = "([a-z_]+)"', text))
    assert len(consts) == 13, consts
    lists = {}
    for mode, body in re.findall(r"private static readonly string\[\] CARRIES_([A-Z0-9]+) = \{([^}]*)\};", text):
        lists[mode] = {consts[n.strip()] for n in body.split(",") if n.strip()}
    assert sorted(lists) == ["1V1", "FFA", "OVT", "TEAM"], sorted(lists)
    return consts, lists


_SAT_NS = uuid.UUID("5e55a0e0-0000-4000-8000-000000000001")
_SAT_MID = str(uuid.uuid5(_SAT_NS, "match"))


def _sat_value(k):
    """A populated value for any column a report loader reads."""
    if k in ("id", "match_id"):
        return _SAT_MID
    if k == "player_id":
        return str(uuid.uuid5(_SAT_NS, "t1a_id"))     # the 2v2 telemetry row of seat t1a
    if k.endswith("_id"):
        return str(uuid.uuid5(_SAT_NS, k))
    if k in ("started_at", "ended_at"):
        return T0
    if k == "duration_s":
        return 600
    if k == "timeline":
        return FFA_TIMELINE
    if k == "point_times":
        return "60,120,180"
    if k == "point_timeline":
        return "1:0,1:1,2:1"
    if k.endswith("timeline"):
        return "0:0,5:3,9:6" if ("hit" in k or "block" in k) else "0,10,20"
    if k.endswith("end_stats"):
        return END_STATS
    if k == "rules":
        return None
    if k in ("is_ranked", "all_ranked", "settings_known"):
        return True
    if k in ("absent", "solo_extra_pick", "same_card_rule", "sudden_death"):
        return False
    if k == "slot":
        return 0
    if k == "color_hex":
        return "#FFFFFF"
    if k.endswith("active_seconds"):
        return 30.0
    if k.startswith("rating"):
        return 1500.0
    if k == "total_rows":
        return 1
    return 3


class _Saturated(dict):
    """A row in which every column is populated, except the `drop` suffixes."""

    def __init__(self, drop=()):
        super().__init__()
        self.drop = tuple(drop)

    def __getitem__(self, k):
        return None if self.drop and k.endswith(self.drop) else _sat_value(k)

    def get(self, k, default=None):
        return self[k]

    def __contains__(self, k):
        return True

    def __bool__(self):
        return True     # `tele_by.get(...) or {}` must keep it


def _loader_metrics(monkeypatch, consts, mode, drop=(), strip=()):
    """Run the server's loader for `mode` on saturated rows and name the
    metrics its games carry (the client's metric names). `strip` names
    envelope keys of each game emptied before they are read (round 3 L1: the
    loaders name every seat in `scores`, so an envelope without scores is
    built by emptying that key)."""
    async def _rows(db, sql, params):
        return [_Saturated(drop)]
    monkeypatch.setattr(main, "_report_rows", _rows)
    key, cpid = _SAT_MID, str(uuid.uuid5(_SAT_NS, "caller"))
    if mode == "1V1":
        games = asyncio.run(main._report_load_1v1(None, "match", key, cpid))[0]
    elif mode == "TEAM":
        games = asyncio.run(main._report_load_team(None, "match", key, cpid))[0]
    elif mode == "OVT":
        games = asyncio.run(main._report_load_ovt(None, "match", key, cpid))[0]
    else:
        games = asyncio.run(main._report_load_ffa(None, key, cpid))[0]
    assert games, mode
    got = set()
    stream = {"damage": "MET_DAMAGE", "score": "MET_SCORE", "shots": "MET_HIT", "hits": "MET_HIT",
              "blocks": "MET_BLOCK", "blocks_ok": "MET_BLOCK", "ping": "MET_PING", "fps": "MET_FPS",
              "kills": "MET_KILLS"}
    gold_mode = {"1V1": "1v1", "TEAM": "team", "OVT": "ovt"}.get(mode)
    for game in games:
        sid_of = {s["pid"]: "7656119%010d" % i for i, s in enumerate(game["slots"])}
        out = main._report_game_json(game, sid_of, {})
        for k in strip:
            out[k] = type(out[k])()
        for name in out["available"]:
            got.add(consts[stream[name]])
        for tot in out["totals"].values():
            if tot:
                got.add(consts["MET_COMBAT"])
            if "damage" in tot:
                got.add(consts["MET_DAMAGE_TOTAL"])
            if "kills" in tot or ("deaths" in tot and mode == "1V1"):
                got.add(consts["MET_KILLS"])
        if out["xp"]:
            got.add(consts["MET_XP"])
        if out["scores"]:
            got.add(consts["MET_PLAY"])
            # round 3 L1: a game's end scores are the score race's dots in
            # every mode (FinishRace) - for 2v2 and 1v2 the whole race
            got.add(consts["MET_SCORE"])
        if out["duration_s"] > 0:
            got.add(consts["MET_DURATION"])
        # Gold is the ledger's per-game record (1v1 / 2v2 / 1v2) or the FFA
        # row's gold_gained - read outside the loader's games statement.
        if (gold_mode in main._REPORT_GAME_GOLD_REASONS
                or (mode == "FFA" and all(s.get("gold_gained") is not None for s in game["slots"]))):
            got.add(consts["MET_GOLD"])
    return got


def test_the_modes_carry_lists_are_what_the_server_loaders_read(monkeypatch):
    """Round 2 L1, executed: each mode's CARRIES list in the client is exactly
    what the server's loader for that mode can put on a game - so "not
    supported for this mode" is said only of a metric no set of the mode can
    carry, and every other gap reads "not recorded for this set"."""
    consts, lists = _carries_lists()
    for mode in ("1V1", "TEAM", "OVT", "FFA"):
        got = _loader_metrics(monkeypatch, consts, mode)
        assert got == lists[mode], (mode, "loader only", sorted(got - lists[mode]),
                                    "client only", sorted(lists[mode] - got))
    # Control: the saturation is what produces a metric - the 1v2 loader with
    # its damage timelines empty carries no damage at all.
    bare = _loader_metrics(monkeypatch, consts, "OVT", drop=("_damage_timeline",))
    assert consts["MET_DAMAGE"] not in bare and consts["MET_DAMAGE"] in lists["OVT"], sorted(bare)


def test_a_team_or_1v2_set_without_scores_reads_not_recorded_for_this_set(monkeypatch):
    """Round 3 L1: the 2v2 and 1v2 loaders put end scores on every game, and
    those scores are the whole of those modes' score race (FinishRace's
    dots), so both modes carry MET_SCORE. An envelope of either mode whose
    games carry no scores (the loader's own envelope with `scores` emptied)
    has no score race, and the race panel's text is MissingText(kind,
    MET_SCORE): with the metric in the mode's list that is "not recorded for
    this set", never "not supported for this mode". Control: the same
    envelope with its scores carries the metric."""
    consts, lists = _carries_lists()
    score = consts["MET_SCORE"]
    for mode in ("TEAM", "OVT"):
        full = _loader_metrics(monkeypatch, consts, mode)
        bare = _loader_metrics(monkeypatch, consts, mode, strip=("scores",))
        assert score in full, (mode, "control: the loader's envelope carries scores")
        assert score not in bare, (mode, sorted(bare))
        assert score in lists[mode], (mode, "the race would read 'not supported for this mode'")
    build = _cs_body(PLUGIN / "SessionReportModel.cs", "internal static Model Build(Envelope env)")
    assert "FinishRace(m, env, MissingText(m.Kind, MET_SCORE));" in build
    race = _cs_body(PLUGIN / "SessionReportModel.cs",
                    "private static void FinishRace(Model m, Envelope env, string missing)")
    assert "if (p.Lines.Count == 0 && p.Dots.Count == 0) { p.Missing = missing; return; }" in race
    assert "g.Scores.TryGetValue(pid, out v)" in race, "the dots are the games' end scores"
