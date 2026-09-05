"""In-room head-to-head summary: GET /api/v1/h2h/{steam_id}/{opponent_steam_id}
(Release B §1).

The route requires the caller's own valid Steam session (the strict, fail-closed
gate queue_poll uses) before any other statement, validates the opponent id as
17 digits, answers aggregates only (no room name, match id or series id) and
debounces a per-(caller, opponent) echo with 429 rate_debounced + retry_after.

Style of test_viewer_h2h_retained.py: the handler is EXECUTED against a fake
session that emulates the statements it issues — the session lookup, the
players lookup and the ONE facts CTE (game counters, timestamps and the
series classification; the handler delegates to no module-level helper, so
its route fingerprint covers every statement it issues) — and REFUSES a
statement that lost one of the load-bearing predicates, so a query edit cannot
pass by keeping the strings somewhere else in the module. The fake also
refuses a facts statement that carries the stats helper's ">= 2 wins" series
pre-filter (design r3 §1.1 MEDIUM): every completed valid pair series is
classified here, so a completed 2-2 row is one tie and one series.
Source-shape tests pin the gate order and the rate-limit prefix.

The clock is FROZEN, not anchored: an autouse fixture points main._utc_now —
the one seam the handler's UTC-day boundary and the strict session gate read
— at a fixed instant, so every fixture below holds on any calendar date
(review r6 LOW: a real-clock production path under a fixed-date fixture
starts failing the day the fixture's session expires). A parametrised test
moves that instant to 2020 and 2099 to prove the seam is the one production
reads. The client's retry delays are pinned against the server's debounce
window by reading plugin/H2HRules.cs (both sides of one contract).
"""

import asyncio
import inspect
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy import text

import main
import schemas

ME_SID = "76561198000000001"
OPP_SID = "76561198000000002"
THIRD_SID = "76561198000000003"
ME = UUID("11111111-1111-1111-1111-111111111111")
OPP = UUID("22222222-2222-2222-2222-222222222222")
THIRD = UUID("33333333-3333-3333-3333-333333333333")

ROUTE_PATH = "/api/v1/h2h/{steam_id}/{opponent_steam_id}"

# The facts CTE must carry the stats helper's pair / invalidation /
# room-prefix predicates VERBATIM (test_viewer_h2h_retained.py pins them on
# the helper; repeated here so THIS fake refuses a drift too), the caller-
# oriented game counters, its own typed day boundary, and the series
# classification: every completed valid pair series, wins oriented to the
# caller, won/lost/tied split in the projection.
FACTS_PREDICATES = (
    "SELECT m.ended_at, m.winner_id",
    "WHERE ((m.player1_id = :vid AND m.player2_id = :pid)",
    "OR (m.player1_id = :pid AND m.player2_id = :vid))",
    "m.invalidated_at IS NULL",
    "m.photon_room_id IS NULL OR (",
    "LEFT(m.photon_room_id, 5) <> 'team_'",
    "LEFT(m.photon_room_id, 4) <> 'ovt_'",
    "LEFT(m.photon_room_id, 4) <> 'ffa_'",
    "CASE WHEN rs.player1_id = :vid THEN rs.p1_series_wins ELSE rs.p2_series_wins END AS vw",
    "CASE WHEN rs.player1_id = :vid THEN rs.p2_series_wins ELSE rs.p1_series_wins END AS pw",
    "rs.status = 'completed'",
    "rs.invalidated_at IS NULL",
    "AND ((rs.player1_id = :vid AND rs.player2_id = :pid)",
    "OR (rs.player1_id = :pid AND rs.player2_id = :vid))",
    "WHERE pm.winner_id = :vid) AS games_won",
    "WHERE pm.winner_id = :pid) AS games_lost",
    "WHERE pm.ended_at < CAST(:day_start AS TIMESTAMPTZ)) AS last_played_at",
    "WHERE pm.ended_at >= CAST(:day_start AS TIMESTAMPTZ)) AS played_today",
    "WHERE ps.vw > ps.pw) AS series_won",
    "WHERE ps.vw < ps.pw) AS series_lost",
    "WHERE ps.vw = ps.pw) AS series_tied",
)
# The stats helper's decided-only pre-filter must NOT reach the facts
# statement: it would drop a level row before the tie count (r3 §1.1).
SERIES_PREFILTER = "rs.p1_series_wins >= 2"


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


def _aware(dt):
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _match_eligible(m, vid, pid):
    return ({m["player1_id"], m["player2_id"]} == {vid, pid}
            and m.get("invalidated_at") is None
            and (m.get("photon_room_id") is None
                 or not m["photon_room_id"].startswith(("team_", "ovt_", "ffa_"))))


def _series_eligible(s, vid, pid):
    """Every completed, non-invalidated series between the pair — no
    decided-only pre-filter (r3 §1.1)."""
    return ({s["player1_id"], s["player2_id"]} == {vid, pid}
            and s["status"] == "completed"
            and s.get("invalidated_at") is None)


def _series_oriented(s, vid):
    """(viewer wins, opponent wins) for one row, the CASE projection in Python."""
    if s["player1_id"] == vid:
        return s["p1_series_wins"], s["p2_series_wins"]
    return s["p2_series_wins"], s["p1_series_wins"]


class FakeSession:
    """Emulates every statement the handler can issue, in Python."""

    def __init__(self, session_row=None, players=(), matches=(), series=()):
        self.session_row = session_row
        self.players = list(players)
        self.matches = list(matches)
        self.series = list(series)
        self.statements = []
        self.facts_params = None

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        params = params or {}
        if "FROM steam_sessions" in sql:
            return _Rows([self.session_row] if self.session_row else [])
        if "FROM players p" in sql:
            wanted = {params["me"], params["opp"]}
            return _Rows([p for p in self.players if p["steam_id"] in wanted])
        if "WITH pair_matches" in sql:
            for predicate in FACTS_PREDICATES:
                assert predicate in sql, f"facts query lost predicate: {predicate}"
            assert SERIES_PREFILTER not in sql, "facts query carries the decided-only series pre-filter"
            vid, pid, day_start = params["vid"], params["pid"], params["day_start"]
            assert isinstance(day_start, datetime) and day_start.tzinfo is not None
            self.facts_params = dict(params)
            eligible = [m for m in self.matches if _match_eligible(m, vid, pid)]
            # a naive ended_at compares as UTC (the column's zone) and is
            # returned as stored, the way a naive row would reach the handler
            before = [m["ended_at"] for m in eligible if _aware(m["ended_at"]) < day_start]
            today = any(_aware(m["ended_at"]) >= day_start for m in eligible)
            oriented = [_series_oriented(s, vid) for s in self.series if _series_eligible(s, vid, pid)]
            return _Rows([{"games_won": sum(1 for m in eligible if m.get("winner_id") == vid),
                           "games_lost": sum(1 for m in eligible if m.get("winner_id") == pid),
                           "last_played_at": max(before) if before else None,
                           "played_today": today,
                           "series_won": sum(1 for vw, pw in oriented if vw > pw),
                           "series_lost": sum(1 for vw, pw in oriented if vw < pw),
                           "series_tied": sum(1 for vw, pw in oriented if vw == pw)}])
        # The stats helper's own two statements (its match counters and its
        # decided-only series read) are not ones this handler may issue: every
        # aggregate comes from the facts CTE above, so a bare "FROM matches m"
        # or "FROM ranked_series rs" is unexpected.
        raise AssertionError(f"unexpected statement: {sql[:80]}")


# A fixed instant, honoured because _freeze_clock (autouse, below) points
# main._utc_now at it — see the module docstring.
NOW = datetime(2026, 9, 4, 15, 30, tzinfo=timezone.utc)
DAY_START = NOW.replace(hour=0, minute=0, second=0, microsecond=0)


def _good_session(sid=ME_SID, now=NOW):
    return {"steam_id": sid, "verified": True, "expires_at": now + timedelta(hours=1)}


def _players(opp_name="Opp Name"):
    return [{"steam_id": ME_SID, "id": ME, "display_name": "Me"},
            {"steam_id": OPP_SID, "id": OPP, "display_name": opp_name}]


def _match(winner, ended_at, ranked=True, room=None, invalidated=None, p1=ME, p2=OPP):
    return {"player1_id": p1, "player2_id": p2, "winner_id": winner, "is_ranked": ranked,
            "photon_room_id": room, "invalidated_at": invalidated, "ended_at": ended_at}


def _series(p1w, p2w, status="completed", invalidated=None, p1=ME, p2=OPP):
    return {"player1_id": p1, "player2_id": p2, "p1_series_wins": p1w, "p2_series_wins": p2w,
            "status": status, "invalidated_at": invalidated}


def _req(token="tok"):
    return SimpleNamespace(headers={"X-Session-Token": token} if token else {})


def _call(session, me=ME_SID, opp=OPP_SID, token="tok"):
    return asyncio.run(main.h2h_summary(me, opp, _req(token), session))


def _call_fresh(session, **kw):
    """A call outside any debounce window (the window itself is tested on
    its own below)."""
    main._h2h_last_read.clear()
    return _call(session, **kw)


def _raises(session, me=ME_SID, opp=OPP_SID, token="tok"):
    with pytest.raises(HTTPException) as info:
        _call(session, me, opp, token)
    return info.value


@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch):
    """Production's wall-clock seam, frozen at NOW for every test; a test
    that needs another instant re-points it."""
    monkeypatch.setattr(main, "_utc_now", lambda: NOW)


@pytest.fixture(autouse=True)
def _clear_debounce():
    main._h2h_last_read.clear()
    yield
    main._h2h_last_read.clear()


# ── route and schema shape ────────────────────────────────────────────────

def test_route_is_registered_at_the_literal_path_with_the_response_model():
    routes = [r for r in main.app.routes if isinstance(r, APIRoute) and r.path == ROUTE_PATH]
    assert len(routes) == 1
    route = routes[0]
    assert route.methods == {"GET"}
    assert route.endpoint is main.h2h_summary
    assert route.response_model is schemas.H2HSummaryResponse
    assert route.path.startswith("/api/v1/h2h/")


def test_gate_is_the_strict_one_and_runs_before_the_first_statement():
    sig = inspect.signature(main.h2h_summary)
    assert sig.parameters["request"].annotation is main.Request
    src = inspect.getsource(main.h2h_summary)
    gate = src.index("_strict_steam_session_ok(request, steam_id, db)")
    first_statement = src.index("db.execute(")
    assert gate < first_statement, "the session gate must run before any statement"
    assert 'raise HTTPException(status_code=401, detail="session_required")' in src[gate:first_statement]
    # the 400 validation and the debounce sit AFTER the gate too
    assert gate < src.index('detail="bad_request"') < first_statement
    assert gate < src.index('"rate_debounced"') < first_statement
    # no soft compatibility gate, no presence touch on a read
    assert "_check_steam_session(" not in src
    assert "_presence_touch(" not in src
    # the win/loss counters come from the shared helper, not a re-derivation
    # No module-level helper is delegated to: the route fingerprint
    # (test_route_manifest_net_seat) covers every statement this handler
    # issues, and the stats helper keeps its own decided-only series rule.
    assert "_viewer_h2h_counts(" not in src
    assert "WITH pair_matches AS (" in src


def test_response_schema_is_exactly_the_aggregates_and_carries_nothing_room_derived():
    fields = set(schemas.H2HSummaryResponse.model_fields)
    assert fields == {
        "opponent_display_name",
        "games_total", "games_won", "games_lost",
        "series_total", "series_won", "series_lost", "series_tied",
        "last_played_at", "played_today", "last_played_days_ago",
    }
    for name in fields:
        for banned in ("room", "_id", "region", "token", "code", "match_"):
            assert banned not in name, f"{name} looks room-derived"
    empty = schemas.H2HSummaryResponse()
    assert empty.opponent_display_name is None
    assert empty.last_played_at is None
    assert empty.last_played_days_ago is None
    assert empty.played_today is False
    assert (empty.games_total, empty.games_won, empty.games_lost) == (0, 0, 0)
    assert (empty.series_total, empty.series_won, empty.series_lost, empty.series_tied) == (0, 0, 0, 0)


def test_rate_prefix_is_a_literal_that_does_not_throttle_player_reads():
    assert "/api/v1/h2h/" in main._RL_SENSITIVE_PREFIXES
    concrete = ROUTE_PATH.replace("{steam_id}", ME_SID).replace("{opponent_steam_id}", OPP_SID)
    assert any(concrete.startswith(p) for p in main._RL_SENSITIVE_PREFIXES)
    assert not any(f"/api/v1/players/{ME_SID}".startswith(p) for p in main._RL_SENSITIVE_PREFIXES)
    assert not any(p.startswith("/api/v1/players/") and p.endswith("/") for p in main._RL_SENSITIVE_PREFIXES)


# ── executed behaviour ────────────────────────────────────────────────────

def test_401_without_a_session_and_before_any_other_statement():
    session = FakeSession(session_row=None, players=_players())
    err = _raises(session, token=None)
    assert err.status_code == 401 and err.detail == "session_required"
    assert session.statements == []            # no token: refused with no statement at all

    session = FakeSession(session_row=None, players=_players())
    err = _raises(session)
    assert err.status_code == 401 and err.detail == "session_required"
    assert len(session.statements) == 1 and "FROM steam_sessions" in session.statements[0]


def test_401_when_the_session_belongs_to_another_seat():
    session = FakeSession(session_row=_good_session(THIRD_SID), players=_players())
    err = _raises(session)
    assert err.status_code == 401 and err.detail == "session_required"
    assert len(session.statements) == 1


def test_400_on_a_malformed_or_self_opponent_after_the_gate():
    for bad in ("7656119800000000", "765611980000000012", "7656119800000000x", "", ME_SID):
        session = FakeSession(session_row=_good_session(), players=_players())
        err = _raises(session, opp=bad)
        assert err.status_code == 400, bad
        assert len(session.statements) == 1        # gate ran, nothing else did
    # a refused session is 401 even with a malformed opponent (gate first)
    session = FakeSession(session_row=None, players=_players())
    assert _raises(session, opp="x").status_code == 401


def test_counts_exclude_misroutes_and_invalidated_rows_and_ties_count_for_neither():
    old = NOW - timedelta(days=3)
    session = FakeSession(session_row=_good_session(), players=_players(), matches=[
        _match(ME, old), _match(ME, old), _match(OPP, old),
        _match(ME, old, ranked=False), _match(OPP, old, ranked=False),
        _match(None, old),                          # no winner: neither
        _match(ME, old, invalidated="2026-01-01"),  # admin-invalidated
        _match(ME, old, room="team_abc"), _match(ME, old, room="ovt_abc"), _match(ME, old, room="ffa_abc"),
        _match(ME, old, room="ranked_0123456789ab"), _match(ME, old, room="ABCDEF"),
        _match(ME, old, p1=THIRD, p2=ME),           # another pair
    ], series=[
        _series(2, 0), _series(1, 2), _series(2, 2), _series(3, 3),
        _series(2, 0, status="active"),
        # A completed 1-0 row: the completion writer (first to 2) cannot
        # produce it, but the rule classifies EVERY completed valid row and
        # this one has a side ahead — decided, won.
        _series(1, 0),
        _series(2, 0, invalidated="2026-01-01"),
        _series(0, 2, p1=OPP, p2=ME),               # caller is player2 and won
        _series(2, 1, p1=OPP, p2=ME),               # caller is player2 and lost
    ])
    r = _call(session)
    assert (r.games_won, r.games_lost, r.games_total) == (5, 2, 7)
    assert (r.series_won, r.series_lost, r.series_tied, r.series_total) == (3, 2, 2, 7)
    assert r.opponent_display_name == "Opp Name"
    kinds = [s for s in session.statements]
    assert sum("FROM steam_sessions" in s for s in kinds) == 1
    assert sum("FROM players p" in s for s in kinds) == 1
    assert sum("WITH pair_matches" in s for s in kinds) == 1
    # every aggregate comes from the facts CTE — neither of the stats
    # helper's standalone statements is issued
    standalone = [s for s in kinds if "WITH pair_matches" not in s]
    assert sum("FROM matches m" in s for s in standalone) == 0
    assert sum("FROM ranked_series rs" in s for s in standalone) == 0
    assert len(kinds) == 3


def test_a_completed_two_two_series_is_one_tie_and_one_series():
    """r3 §1.1 MEDIUM: total=1, tied=1, won=lost=0 for a 2-2 row — from
    either seat of the pair."""
    for row in (_series(2, 2), _series(2, 2, p1=OPP, p2=ME)):
        session = FakeSession(session_row=_good_session(), players=_players(), series=[row])
        r = _call_fresh(session)
        assert (r.series_total, r.series_tied, r.series_won, r.series_lost) == (1, 1, 0, 0)
    # ...and a level row below the BO3 line is a tie too, never dropped
    session = FakeSession(session_row=_good_session(), players=_players(), series=[_series(1, 1)])
    r = _call_fresh(session)
    assert (r.series_total, r.series_tied, r.series_won, r.series_lost) == (1, 1, 0, 0)
    # the handler's own source carries no decided-only pre-filter
    assert SERIES_PREFILTER not in inspect.getsource(main.h2h_summary)
    # ...while the stats helper keeps its rule (its own tests pin it)
    assert SERIES_PREFILTER in inspect.getsource(main._viewer_h2h_counts)


def test_last_played_excludes_today_while_played_today_sees_it():
    three_days = NOW - timedelta(days=3)
    yesterday_late = DAY_START - timedelta(minutes=1)
    today_early = DAY_START + timedelta(minutes=1)
    session = FakeSession(session_row=_good_session(), players=_players(), matches=[
        _match(ME, three_days), _match(OPP, yesterday_late), _match(ME, today_early),
        _match(ME, today_early + timedelta(hours=1), invalidated="2026-09-04"),
        _match(ME, NOW, room="ffa_today"),         # a misroute today is not "played today"
    ])
    r = _call(session)
    assert r.last_played_at == yesterday_late
    assert r.last_played_days_ago == 1
    assert r.played_today is True
    assert (r.games_won, r.games_lost) == (2, 1)

    # only history before today
    session = FakeSession(session_row=_good_session(), players=_players(),
                          matches=[_match(ME, three_days)])
    r = _call_fresh(session)
    assert r.last_played_at == three_days and r.played_today is False
    assert r.last_played_days_ago == 3

    # only history today: no "last played", but played_today
    session = FakeSession(session_row=_good_session(), players=_players(),
                          matches=[_match(ME, today_early)])
    r = _call_fresh(session)
    assert r.last_played_at is None and r.played_today is True and r.games_total == 1
    assert r.last_played_days_ago is None

    # the day boundary is the caller's CURRENT UTC midnight, sent as a typed bind
    cte = next(s for s in session.statements if "WITH pair_matches" in s)
    assert "CAST(:day_start AS TIMESTAMPTZ)" in cte


def test_unknown_opponent_answers_zeros_and_a_null_name_with_no_aggregate_statement():
    session = FakeSession(session_row=_good_session(),
                          players=[{"steam_id": ME_SID, "id": ME, "display_name": "Me"}],
                          matches=[_match(ME, NOW - timedelta(days=1))])
    r = _call(session)
    assert r == schemas.H2HSummaryResponse()
    assert not any("FROM matches m" in s or "WITH pair_matches" in s for s in session.statements)


def test_no_history_answers_zeros_with_the_opponent_name():
    session = FakeSession(session_row=_good_session(), players=_players("Fresh"))
    r = _call(session)
    assert r.opponent_display_name == "Fresh"
    assert r.games_total == 0 and r.series_total == 0
    assert r.last_played_at is None and r.played_today is False
    assert r.last_played_days_ago is None


def test_an_id_shaped_name_is_cleaned_to_null_like_the_stats_endpoint():
    session = FakeSession(session_row=_good_session(), players=_players(OPP_SID))
    assert _call_fresh(session).opponent_display_name is None
    session = FakeSession(session_row=_good_session(), players=_players("   "))
    assert _call_fresh(session).opponent_display_name is None


def test_echo_within_the_window_is_429_with_retry_after_and_a_refused_request_does_not_arm_it():
    # a refused request never arms the debounce
    session = FakeSession(session_row=None, players=_players())
    _raises(session)
    assert main._h2h_last_read == {}
    # first accepted read arms it; the echo is 429 with a body retry_after
    session = FakeSession(session_row=_good_session(), players=_players())
    _call(session)
    assert (ME_SID, OPP_SID) in main._h2h_last_read
    session = FakeSession(session_row=_good_session(), players=_players())
    err = _raises(session)
    assert err.status_code == 429
    assert err.detail["error"] == "rate_debounced"
    assert 1 <= err.detail["retry_after"] <= 5
    assert err.headers["Retry-After"] == str(err.detail["retry_after"])
    assert len(session.statements) == 1        # gate ran, no data statement
    # a different opponent is its own key
    session = FakeSession(session_row=_good_session(), players=_players())
    _call(session, opp=THIRD_SID)
    # and the window expires
    main._h2h_last_read[(ME_SID, OPP_SID)] -= main._H2H_DEBOUNCE_SECONDS + 1
    session = FakeSession(session_row=_good_session(), players=_players())
    _call(session)


def test_debounce_table_is_bounded_by_a_ttl_and_a_hard_cap():
    """r3 §1.1 LOW: a session holder rotating opponent ids mints a fresh key
    per request, so the table needs BOTH a TTL and a cap. Past the cap, keys
    older than the TTL go first; if the table is still over, the oldest go
    until the cap holds — and the key just written always survives."""
    cap, ttl = main._H2H_DEBOUNCE_MAX_KEYS, main._H2H_DEBOUNCE_TTL_SECONDS
    assert cap == 4096 and ttl >= 10 * main._H2H_DEBOUNCE_SECONDS

    # AT the cap nothing is pruned, stale or not — the handler's trigger is
    # "exceeds", so the sort never runs on an ordinary table
    now = time.monotonic()
    main._h2h_last_read.clear()
    for i in range(cap - 1):
        main._h2h_last_read[("caller", f"opp{i:05d}")] = now - ttl - 1   # all stale
    session = FakeSession(session_row=_good_session(), players=_players())
    _call(session)
    assert len(main._h2h_last_read) == cap
    assert ("caller", "opp00000") in main._h2h_last_read

    # TTL: the insert that takes the table past the cap drops every key
    # older than the TTL first — the fresh half and the caller's key remain
    main._h2h_last_read.clear()
    for i in range(cap // 2):
        main._h2h_last_read[("caller", f"old{i:05d}")] = now - ttl - 1
    for i in range(cap // 2):
        main._h2h_last_read[("caller", f"new{i:05d}")] = now - 1
    assert len(main._h2h_last_read) == cap
    session = FakeSession(session_row=_good_session(), players=_players())
    _call(session)
    assert len(main._h2h_last_read) == cap // 2 + 1
    assert (ME_SID, OPP_SID) in main._h2h_last_read
    assert all(k[1].startswith("new") or k == (ME_SID, OPP_SID) for k in main._h2h_last_read)

    # hard cap: all fresh (every age inside the TTL), so the TTL drops
    # nothing — the oldest is evicted, the newest and the caller's survive
    main._h2h_last_read.clear()
    now = time.monotonic()
    for i in range(cap):
        main._h2h_last_read[("caller", f"opp{i:05d}")] = now - (cap - i) * 0.01  # i=0 oldest
    assert all(now - v < ttl for v in main._h2h_last_read.values())
    session = FakeSession(session_row=_good_session(), players=_players())
    _call(session)
    assert len(main._h2h_last_read) == cap
    assert ("caller", "opp00000") not in main._h2h_last_read      # the oldest is gone
    assert ("caller", "opp00001") in main._h2h_last_read
    assert ("caller", f"opp{cap - 1:05d}") in main._h2h_last_read  # the newest survives
    assert (ME_SID, OPP_SID) in main._h2h_last_read

    # the bound is the handler's own (no helper the route fingerprint would miss)
    src = inspect.getsource(main.h2h_summary)
    assert "_H2H_DEBOUNCE_TTL_SECONDS" in src
    assert "sorted(_h2h_last_read, key=_h2h_last_read.__getitem__)[:_over]" in src


def test_fake_session_refuses_a_facts_statement_that_lost_a_predicate():
    """The oracle: the REAL statement the handler emits, mutated one predicate
    at a time, is refused at execution time — and so is the statement with
    the stats helper's decided-only pre-filter put back."""
    recorder = FakeSession(session_row=_good_session(), players=_players())
    _call(recorder)
    real = next(s for s in recorder.statements if "WITH pair_matches" in s)
    session = FakeSession()
    params = {"vid": ME, "pid": OPP, "day_start": DAY_START}
    mutations = (
        real.replace("WHERE ((m.player1_id = :vid AND m.player2_id = :pid)", "WHERE (TRUE"),
        real.replace("AND m.invalidated_at IS NULL", ""),
        real.replace("LEFT(m.photon_room_id, 4) <> 'ffa_'", "TRUE"),
        real.replace("WHERE pm.winner_id = :vid) AS games_won", "WHERE pm.winner_id = :pid) AS games_won"),
        real.replace("AND rs.invalidated_at IS NULL", ""),
        real.replace("OR (rs.player1_id = :pid AND rs.player2_id = :vid))", "OR TRUE)"),
        real.replace("CASE WHEN rs.player1_id = :vid THEN rs.p1_series_wins ELSE rs.p2_series_wins END AS vw",
                     "rs.p1_series_wins AS vw"),
        real.replace("WHERE pm.ended_at < CAST(:day_start AS TIMESTAMPTZ)) AS last_played_at",
                     ") AS last_played_at"),
        real.replace("CAST(:day_start AS TIMESTAMPTZ)) AS played_today", ":day_start) AS played_today"),
        real.replace("WHERE ps.vw = ps.pw) AS series_tied", ") AS series_tied"),
        real.replace("WHERE ps.vw > ps.pw) AS series_won", "WHERE ps.vw >= ps.pw) AS series_won"),
    )
    for mutated in mutations:
        assert mutated != real
        with pytest.raises(AssertionError, match="lost predicate"):
            asyncio.run(session.execute(text(mutated), params))
    # negative control on the pre-filter: the statement with it put back is
    # refused with its own message
    with_prefilter = real.replace(
        "OR (rs.player1_id = :pid AND rs.player2_id = :vid))",
        "OR (rs.player1_id = :pid AND rs.player2_id = :vid))\n"
        "               AND (rs.p1_series_wins >= 2 OR rs.p2_series_wins >= 2)")
    assert with_prefilter != real
    with pytest.raises(AssertionError, match="pre-filter"):
        asyncio.run(session.execute(text(with_prefilter), params))


# ── review r6: server-computed day distance, frozen clock, retry window ───

def test_last_played_days_ago_is_the_utc_day_distance_on_the_server_clock(monkeypatch):
    """r6 LOW: the relative-day copy's integer is computed here, on the clock
    that set day_start — the client never subtracts last_played_at from its
    own clock. Whole UTC days between the game's UTC date and the caller's
    current UTC date; at least 1 because the facts statement bounds
    last_played_at strictly below day_start."""
    def days_for(ended_at, now=NOW):
        monkeypatch.setattr(main, "_utc_now", lambda: now)
        session = FakeSession(session_row=_good_session(now=now), players=_players(),
                              matches=[_match(ME, ended_at)])
        r = _call_fresh(session)
        assert r.last_played_at == ended_at
        return r.last_played_days_ago

    assert days_for(NOW - timedelta(days=3)) == 3
    assert days_for(DAY_START - timedelta(microseconds=1)) == 1       # yesterday's last instant
    assert days_for(DAY_START - timedelta(days=1)) == 1               # yesterday's first instant
    assert days_for(DAY_START - timedelta(days=1, microseconds=1)) == 2
    assert days_for(NOW - timedelta(days=400)) == 400
    # a naive row (no tzinfo) is read as UTC, the column's zone
    assert days_for((NOW - timedelta(days=13)).replace(tzinfo=None)) == 13
    # just past UTC midnight, a 23:59 game is one day ago on the server's
    # day — a client clock an hour behind UTC would have called it "today";
    # it never gets to decide
    early = datetime(2026, 9, 5, 0, 30, tzinfo=timezone.utc)
    assert days_for(datetime(2026, 9, 4, 23, 59, tzinfo=timezone.utc), now=early) == 1
    # no counted game before today: no timestamp and no distance
    monkeypatch.setattr(main, "_utc_now", lambda: NOW)
    session = FakeSession(session_row=_good_session(), players=_players(),
                          matches=[_match(ME, DAY_START + timedelta(minutes=1))])
    r = _call_fresh(session)
    assert r.last_played_at is None and r.last_played_days_ago is None and r.played_today is True


@pytest.mark.parametrize("instant", [
    datetime(2020, 1, 1, 0, 30, tzinfo=timezone.utc),      # past: a raw-clock gate would 401 the +1 h session
    datetime(2099, 12, 31, 23, 59, tzinfo=timezone.utc),   # future: a raw-clock day_start would find no game before it
])
def test_the_suite_holds_on_any_date_because_production_reads_the_frozen_seam(monkeypatch, instant):
    """r6 LOW (test lifetime): the fixtures are anchored to an instant that
    production is made to share through main._utc_now. Moving that instant to
    2020 and to 2099 keeps every expectation true — and each choice is a
    negative control for one reader of the raw clock: the strict session gate
    (2020) and the handler's day boundary (2099)."""
    monkeypatch.setattr(main, "_utc_now", lambda: instant)
    day_start = instant.replace(hour=0, minute=0, second=0, microsecond=0)
    session = FakeSession(session_row=_good_session(now=instant), players=_players(), matches=[
        _match(ME, day_start - timedelta(minutes=1)),
        _match(OPP, day_start + timedelta(minutes=1)),
    ])
    r = _call_fresh(session)
    assert session.facts_params["day_start"] == day_start
    assert r.last_played_at == day_start - timedelta(minutes=1)
    assert r.last_played_days_ago == 1 and r.played_today is True
    assert (r.games_won, r.games_lost) == (1, 1)
    # the seam is the only wall clock either reader consults
    for fn in (main.h2h_summary, main._strict_steam_session_ok):
        src = inspect.getsource(fn)
        assert "_utc_now()" in src, fn.__name__
        assert "datetime.now(" not in src and "utcnow(" not in src, fn.__name__
    # ...while the debounce window stays on the monotonic clock, untouched by the freeze
    assert "time.monotonic()" in inspect.getsource(main.h2h_summary)


H2H_RULES_CS = Path(__file__).resolve().parents[2] / "plugin" / "H2HRules.cs"


def _cs_float_const(name):
    src = H2H_RULES_CS.read_text(encoding="utf-8")
    m = re.search(rf"internal const float {name} = (\d+(?:\.\d+)?)f;", src)
    assert m, f"{name} not found in {H2H_RULES_CS}"
    return float(m.group(1))


def test_client_retry_delays_sit_beyond_the_server_debounce_window():
    """r6 LOW: an accepted request arms the window; if its response is lost
    the client's re-send must land OUTSIDE the window or it is refused as an
    echo — and a 429 is retried once after retry_after, not treated as
    permanent. The server half is pinned as literals and executed; the client
    half is read from plugin/H2HRules.cs (one contract, both sides — a change
    to either literal fails here)."""
    window = main._H2H_DEBOUNCE_SECONDS
    assert window == 5.0
    assert _cs_float_const("SERVER_DEBOUNCE_SECONDS") == window
    transport = _cs_float_const("TRANSPORT_RETRY_DELAY")
    fallback = _cs_float_const("DEBOUNCE_RETRY_FALLBACK")
    margin = _cs_float_const("DEBOUNCE_RETRY_MARGIN")
    assert transport > window, "a transport re-send inside the window is refused as an echo"
    assert fallback > window, "a 429 retry without a readable retry_after must outlast the window"
    assert margin >= 1.0

    # executed: arm the window, then re-send exactly the client's transport
    # delay later — accepted, not 429
    session = FakeSession(session_row=_good_session(), players=_players())
    _call(session)
    main._h2h_last_read[(ME_SID, OPP_SID)] = time.monotonic() - transport
    session = FakeSession(session_row=_good_session(), players=_players())
    assert _call(session).opponent_display_name == "Opp Name"

    # an echo inside the window: a 429 whose retry_after never exceeds the
    # window, in the detail shape the client reads — and the request re-sent
    # retry_after + margin later is accepted
    main._h2h_last_read[(ME_SID, OPP_SID)] = time.monotonic() - 1.0
    session = FakeSession(session_row=_good_session(), players=_players())
    err = _raises(session)
    assert err.status_code == 429
    assert set(err.detail) == {"error", "retry_after"}
    assert 1 <= err.detail["retry_after"] <= window
    main._h2h_last_read[(ME_SID, OPP_SID)] = time.monotonic() - (err.detail["retry_after"] + margin)
    session = FakeSession(session_row=_good_session(), players=_players())
    assert _call(session).opponent_display_name == "Opp Name"


H2H_SUMMARY_CS = Path(__file__).resolve().parents[2] / "plugin" / "H2HSummary.cs"


def _cs_int_const(name):
    src = H2H_RULES_CS.read_text(encoding="utf-8")
    m = re.search(r"const int %s\s*=\s*(\d+)" % re.escape(name), src)
    assert m, f"{name} not found in {H2H_RULES_CS}"
    return int(m.group(1))


def test_the_read_budget_is_per_key_and_per_room_not_one_per_room():
    """r12 LOW. The class summary opened with "one GET per room incarnation"
    while the paragraphs below it described a four-request ladder per key and a
    six-request budget per room. Both numbers are deliberate; the headline was
    the wrong one, and a headline is what a reader takes away.

    What is true: one read ANSWERS a key, the ladder is what a key may spend
    when it is not answered, and the room budget is what bounds a room whose
    key keeps changing."""
    doc = H2H_SUMMARY_CS.read_text(encoding="utf-8")
    head = doc[:doc.index("Trigger, each Poll tick")]
    assert "One GET /api/v1/h2h/{me}/{opponent} per room" not in head, (
        "the retired claim came back"
    )
    assert "MAX_REQUESTS_PER_ROOM" in head, "the headline must name the real bound"
    per_room = _cs_int_const("MAX_REQUESTS_PER_ROOM")
    assert per_room > 1, "a per-room budget of one would make the old claim true"
    ladder = (1 + _cs_int_const("MAX_SESSION_RESENDS")
              + _cs_int_const("MAX_TRANSPORT_RETRIES")
              + _cs_int_const("MAX_DEBOUNCE_RETRIES"))
    assert ladder > 1
    assert per_room >= ladder, "one key's whole ladder has to fit inside the room budget"


def test_the_room_spacing_can_delay_the_one_retry_whose_delay_is_the_servers():
    """r12 LOW. MIN_REQUEST_SPACING_SECONDS said it "never delays a retry",
    which held for the two delays this client picks and not for the third,
    which it does not pick: a 429 is re-sent retry_after + margin later, and
    retry_after comes from the server. At the smallest value the server sends,
    that schedule lands inside the spacing.

    The retry is not lost -- TooSoon is not a refusal, the caller asks again on
    a later tick -- so what the finding costs is the accuracy of the comment,
    and that is what is fixed."""
    spacing = _cs_float_const("MIN_REQUEST_SPACING_SECONDS")
    margin = _cs_float_const("DEBOUNCE_RETRY_MARGIN")
    assert _cs_float_const("TRANSPORT_RETRY_DELAY") > spacing
    assert _cs_float_const("DEBOUNCE_RETRY_FALLBACK") > spacing

    # the smallest retry_after the endpoint will hand out, taken from the
    # endpoint rather than assumed
    main._h2h_last_read[(ME_SID, OPP_SID)] = time.monotonic() - (main._H2H_DEBOUNCE_SECONDS - 0.1)
    err = _raises(FakeSession(session_row=_good_session(), players=_players()))
    assert err.status_code == 429
    smallest = err.detail["retry_after"]
    assert smallest + margin < spacing, (
        "if this ever stops being true the comment below should be re-checked, "
        "not the other way round"
    )

    rules = H2H_RULES_CS.read_text(encoding="utf-8")
    assert "never delays a retry" not in rules, "the retired claim came back"
    summary = rules[rules.index("Least time between two reads"):]
    summary = summary[:summary.index("</summary>")]
    assert "retry_after" in summary, "the exception has to be named where the claim was"

    # and the delay is a delay, not a drop
    assert "RoomGate.TooSoon) return;" in H2H_SUMMARY_CS.read_text(encoding="utf-8")
