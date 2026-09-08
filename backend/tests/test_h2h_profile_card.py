"""Mini-profile card on hover (Sept 6 Group 4 item a): the two ADDITIVE
members `profile` and `modes` on GET /api/v1/h2h/{steam_id}/{opponent_steam_id}.

What is pinned, each with a control that fails when the rule is broken:

* the flat contract survives untouched — names, order at the head of the
  JSON, defaults — and no nested member name equals a flat key the in-room
  line reads with a whole-response key search (A-4);
* the profile field matrix (A-5): the eight public fields always present,
  is_online / last_seen_s null under appear_offline, gold and Discord never
  carried — in the model AND in the statement's projection;
* the split cache (A-2): modes 60 s per (viewer, target), capped with
  expired-first eviction; profile read on every request;
* ranked_1v1 / casual_1v1 are _viewer_h2h_counts's ANSWER (A-L), shown to
  differ from the flat series fields where the two rules differ;
* team_2v2 / ffa / ovt / last_meeting from fixture rows, with the same-team,
  absent, invalidated and one-side-only negative controls;
* streak and net rating over the ordered decided series;
* an unknown opponent carries no card and issues no card statement;
* a failed card statement leaves the flat line intact (savepoint, fail-soft).

The FakeSession emulates every statement the handler can issue and REFUSES
one that lost a load-bearing predicate (the h2h suites' shape), so a query
edit cannot pass by keeping the strings elsewhere in the module. The clock
is frozen the way test_h2h_summary.py freezes it.
"""

import asyncio
import inspect
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.routing import APIRoute

import main
import schemas

ME_SID = "76561198000000001"
OPP_SID = "76561198000000002"
THIRD_SID = "76561198000000003"
FOURTH_SID = "76561198000000004"
ME = UUID("11111111-1111-1111-1111-111111111111")
OPP = UUID("22222222-2222-2222-2222-222222222222")
THIRD = UUID("33333333-3333-3333-3333-333333333333")
FOURTH = UUID("44444444-4444-4444-4444-444444444444")

SRC = (Path(__file__).resolve().parents[1] / "api" / "main.py").read_text(encoding="utf-8")

# The flat contract, in declaration order — the in-room line's whole response
# before this item. Anything added must come AFTER these.
FLAT_FIELDS = [
    "opponent_display_name",
    "games_total", "games_won", "games_lost",
    "series_total", "series_won", "series_lost", "series_tied",
    "last_played_at", "last_played_days_ago", "played_today",
]
# The keys H2HSummary.Parse (plugin/H2HSummary.cs) searches across the WHOLE
# response text; no nested member may reuse one.
LINE_SEARCHED_KEYS = {
    "opponent_display_name", "games_total", "games_won", "games_lost",
    "series_total", "played_today", "last_played_at", "last_played_days_ago",
}

PROFILE_PREDICATES = (
    "CASE WHEN p.appear_offline THEN NULL ELSE (p.presence_seen_at > NOW() - INTERVAL '3 minutes'",
    "END AS is_online",
    "CASE WHEN p.appear_offline THEN NULL",
    "END AS last_seen_s",
    "LEFT JOIN glicko_ratings gr ON gr.player_id = p.id",
    "LEFT JOIN shop_items si ON si.id = p.active_title_id",
    "WHERE p.id = :pid",
)
MODES_PREDICATES = (
    "WITH team_games AS (",
    "FROM team_matches tm",
    "tm.invalidated_at IS NULL",
    "(((tm.t1a_id = :vid OR tm.t1b_id = :vid) AND (tm.t2a_id = :pid OR tm.t2b_id = :pid))",
    "OR ((tm.t2a_id = :vid OR tm.t2b_id = :vid) AND (tm.t1a_id = :pid OR tm.t1b_id = :pid)))",
    "JOIN ffa_match_players mv ON mv.match_id = fm.id AND mv.player_id = :vid AND NOT mv.absent",
    "JOIN ffa_match_players mt ON mt.match_id = fm.id AND mt.player_id = :pid AND NOT mt.absent",
    "fm.invalidated_at IS NULL",
    "FROM ovt_matches om",
    "om.invalidated_at IS NULL",
    "((om.solo_id = :vid AND (om.duo_a_id = :pid OR om.duo_b_id = :pid))",
    "OR (om.solo_id = :pid AND (om.duo_a_id = :vid OR om.duo_b_id = :vid)))",
    "m.invalidated_at IS NULL",
    "m.winner_id IS NOT NULL",
    "LEFT(m.photon_room_id, 5) <> 'team_'",
    "LEFT(m.photon_room_id, 4) <> 'ovt_'",
    "LEFT(m.photon_room_id, 4) <> 'ffa_'",
    "CASE WHEN vpl < tpl THEN 'W' WHEN vpl > tpl THEN 'L' ELSE 'T' END",
    "ORDER BY mt.ended_at DESC, mt.mode DESC, mt.result DESC LIMIT 1",   # deterministic tie-break (review a residual)
)
SERIES_LIST_PREDICATES = (
    "AS vchange",
    "rs.status = 'completed'",
    "rs.invalidated_at IS NULL",
    "AND ((rs.player1_id = :vid AND rs.player2_id = :pid)",
    "OR (rs.player1_id = :pid AND rs.player2_id = :vid))",
    "AND (rs.p1_series_wins >= 2 OR rs.p2_series_wins >= 2)",
    "ORDER BY rs.completed_at DESC NULLS LAST",
)


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def mappings(self):
        return self

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _Savepoint:
    """Models PostgreSQL's transaction state (review a-L2): a failed statement
    leaves the session ABORTED -- every later statement is refused -- until the
    savepoint that encloses it exits on the exception, which rolls back to the
    savepoint and clears the state. Without the savepoint the state sticks."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.session.aborted = False
        return False


def _aware(dt):
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _match_eligible(m, vid, pid):
    return ({m["player1_id"], m["player2_id"]} == {vid, pid}
            and m.get("invalidated_at") is None
            and (m.get("photon_room_id") is None
                 or not m["photon_room_id"].startswith(("team_", "ovt_", "ffa_"))))


def _series_pair(s, vid, pid):
    return ({s["player1_id"], s["player2_id"]} == {vid, pid}
            and s["status"] == "completed" and s.get("invalidated_at") is None)


def _oriented(s, vid):
    if s["player1_id"] == vid:
        return s["p1_series_wins"], s["p2_series_wins"], s.get("p1_rating_change")
    return s["p2_series_wins"], s["p1_series_wins"], s.get("p2_rating_change")


class FakeSession:
    """Emulates every statement the handler can issue, in Python, and refuses
    a card statement that lost a load-bearing predicate."""

    def __init__(self, session_row=None, players=(), matches=(), series=(),
                 team=(), ffa=(), ovt=(), fail_profile=False):
        self.session_row = session_row
        self.players = list(players)
        self.matches = list(matches)
        self.series = list(series)
        self.team = list(team)
        self.ffa = list(ffa)
        self.ovt = list(ovt)
        self.fail_profile = fail_profile
        self.aborted = False          # set by a failed statement, cleared by a savepoint exit
        self.statements = []
        # Every begin_nested, tagged with the statement that ran just before
        # it. The session gate (_seat_attestation_verdict) opens its own
        # savepoint around the steam_sessions read BEFORE any statement, so
        # a bare count would attribute the gate's to the card; the card's
        # is the one opened right after the flat facts statement.
        self.savepoint_after = []

    def begin_nested(self):
        self.savepoint_after.append(self.statements[-1] if self.statements else "")
        return _Savepoint(self)

    @property
    def card_savepoints(self):
        return sum("WITH pair_matches" in q for q in self.savepoint_after)

    # ── the emulations ──────────────────────────────────────────────────
    def _meetings(self, vid, pid):
        out = []
        for m in self.matches:
            if _match_eligible(m, vid, pid) and m.get("winner_id") is not None:
                out.append((_aware(m["ended_at"]), "ranked_1v1" if m["is_ranked"] else "casual_1v1",
                            "W" if m["winner_id"] == vid else "L", None))
        for t in self.team:
            if t.get("invalidated_at") is not None:
                continue
            t1, t2 = {t["t1a"], t["t1b"]}, {t["t2a"], t["t2b"]}
            if vid in t1 and pid in t2:
                vteam = 1
            elif vid in t2 and pid in t1:
                vteam = 2
            else:
                continue
            out.append((_aware(t["ended_at"]), "team_2v2", "W" if t["winner_team"] == vteam else "L", None))
        for f in self.ffa:
            if f.get("invalidated_at") is not None:
                continue
            pl = f["players"]
            if vid not in pl or pid not in pl:
                continue
            (vpl, vabs), (tpl, tabs) = pl[vid], pl[pid]
            if vabs or tabs:
                continue
            out.append((_aware(f["ended_at"]), "ffa", "W" if vpl < tpl else ("L" if vpl > tpl else "T"), None))
        for o in self.ovt:
            if o.get("invalidated_at") is not None:
                continue
            duo = {o["duo_a"], o["duo_b"]}
            if o["solo"] == vid and pid in duo:
                vside = 1
            elif o["solo"] == pid and vid in duo:
                vside = 2
            else:
                continue
            out.append((_aware(o["ended_at"]), "ovt", "W" if o["winner_side"] == vside else "L", vside))
        return out

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        params = params or {}
        if self.aborted:
            raise RuntimeError("current transaction is aborted, commands ignored until end of transaction block")
        if "FROM steam_sessions" in sql:
            return _Rows([self.session_row] if self.session_row else [])
        if "rank_role_colors" in sql:
            return _Rows([])                       # _rank_colors' ORM select
        if "LEFT JOIN glicko_ratings gr ON gr.player_id = p.id" in sql:
            for needle in PROFILE_PREDICATES:
                assert needle in sql, f"profile statement lost: {needle}"
            low = sql.lower()
            assert "gold" not in low and "discord" not in low, "the card must not carry gold or Discord identity"
            if self.fail_profile:
                self.aborted = True
                raise RuntimeError("profile statement refused by the fake")
            p = next((x for x in self.players if x["id"] == params["pid"]), None)
            if p is None:
                return _Rows([])
            off = bool(p.get("appear_offline", False))
            return _Rows([{
                "steam_id": p["steam_id"], "display_name": p["display_name"],
                "total_xp": p.get("total_xp", 0),
                "title": p.get("title"), "title_color": p.get("title_color"), "title_sku": p.get("title_sku"),
                "rating": p.get("rating"), "rd": p.get("rd"),
                "is_online": None if off else bool(p.get("online", False)),
                "last_seen_s": None if off else int(p.get("last_seen_s", 0)),
            }])
        if "FROM players p" in sql:
            wanted = {params["me"], params["opp"]}
            return _Rows([{"steam_id": p["steam_id"], "id": p["id"], "display_name": p["display_name"]}
                          for p in self.players if p["steam_id"] in wanted])
        if "WITH pair_matches" in sql:
            vid, pid, day_start = params["vid"], params["pid"], params["day_start"]
            eligible = [m for m in self.matches if _match_eligible(m, vid, pid)]
            before = [m["ended_at"] for m in eligible if _aware(m["ended_at"]) < day_start]
            oriented = [_oriented(s, vid)[:2] for s in self.series if _series_pair(s, vid, pid)]
            return _Rows([{"games_won": sum(1 for m in eligible if m.get("winner_id") == vid),
                           "games_lost": sum(1 for m in eligible if m.get("winner_id") == pid),
                           "last_played_at": max(before) if before else None,
                           "played_today": any(_aware(m["ended_at"]) >= day_start for m in eligible),
                           "series_won": sum(1 for vw, pw in oriented if vw > pw),
                           "series_lost": sum(1 for vw, pw in oriented if vw < pw),
                           "series_tied": sum(1 for vw, pw in oriented if vw == pw)}])
        if "AS ranked_w" in sql and "FROM matches m" in sql:
            # _viewer_h2h_counts's match counters (its own suite pins the text)
            vid, pid = params["vid"], params["pid"]
            el = [m for m in self.matches if _match_eligible(m, vid, pid)]
            return _Rows([{
                "ranked_w": sum(1 for m in el if m["is_ranked"] and m.get("winner_id") == vid),
                "ranked_l": sum(1 for m in el if m["is_ranked"] and m.get("winner_id") == pid),
                "casual_w": sum(1 for m in el if not m["is_ranked"] and m.get("winner_id") == vid),
                "casual_l": sum(1 for m in el if not m["is_ranked"] and m.get("winner_id") == pid)}])
        if "AS p1w" in sql and "FROM ranked_series rs" in sql:
            # _viewer_h2h_counts's decided-only series read
            vid, pid = params["vid"], params["pid"]
            return _Rows([{"p1": s["player1_id"], "p1w": s["p1_series_wins"], "p2w": s["p2_series_wins"]}
                          for s in self.series if _series_pair(s, vid, pid)
                          and (s["p1_series_wins"] >= 2 or s["p2_series_wins"] >= 2)])
        if "WITH team_games AS (" in sql:
            for needle in MODES_PREDICATES:
                assert needle in sql, f"modes statement lost: {needle}"
            vid, pid = params["vid"], params["pid"]
            mt = self._meetings(vid, pid)
            newest = max(mt, key=lambda x: x[0]) if mt else None
            return _Rows([{
                "team_w": sum(1 for x in mt if x[1] == "team_2v2" and x[2] == "W"),
                "team_l": sum(1 for x in mt if x[1] == "team_2v2" and x[2] == "L"),
                "ffa_above": sum(1 for x in mt if x[1] == "ffa" and x[2] == "W"),
                "ffa_below": sum(1 for x in mt if x[1] == "ffa" and x[2] == "L"),
                "ovt_solo_w": sum(1 for x in mt if x[1] == "ovt" and x[3] == 1 and x[2] == "W"),
                "ovt_solo_l": sum(1 for x in mt if x[1] == "ovt" and x[3] == 1 and x[2] == "L"),
                "ovt_duo_w": sum(1 for x in mt if x[1] == "ovt" and x[3] == 2 and x[2] == "W"),
                "ovt_duo_l": sum(1 for x in mt if x[1] == "ovt" and x[3] == 2 and x[2] == "L"),
                "last_at": newest[0] if newest else None,
                "last_mode": newest[1] if newest else None,
                "last_result": newest[2] if newest else None}])
        if "AS vchange" in sql:
            for needle in SERIES_LIST_PREDICATES:
                assert needle in sql, f"series list lost: {needle}"
            vid, pid = params["vid"], params["pid"]
            rows = [s for s in self.series if _series_pair(s, vid, pid)
                    and (s["p1_series_wins"] >= 2 or s["p2_series_wins"] >= 2)]
            rows.sort(key=lambda s: _aware(s["completed_at"]), reverse=True)
            out = []
            for s in rows:
                vw, pw, vchange = _oriented(s, vid)
                out.append({"vw": vw, "pw": pw, "vchange": vchange})
            return _Rows(out)
        raise AssertionError(f"unexpected statement: {sql[:90]}")


NOW = datetime(2026, 9, 6, 15, 30, tzinfo=timezone.utc)
OLD = NOW - timedelta(days=3)


def _good_session(sid=ME_SID, now=NOW):
    return {"steam_id": sid, "verified": True, "expires_at": now + timedelta(hours=1)}


def _player(sid, pid, name, **extra):
    row = {"steam_id": sid, "id": pid, "display_name": name}
    row.update(extra)
    return row


def _players(**opp_extra):
    return [_player(ME_SID, ME, "Me", rating=1600.0, rd=60.0),
            _player(OPP_SID, OPP, "Opp Name", rating=1720.0, rd=55.0, total_xp=5000,
                    online=True, last_seen_s=120, **opp_extra)]


def _match(winner, ended_at=OLD, ranked=True, room=None, invalidated=None, p1=ME, p2=OPP):
    return {"player1_id": p1, "player2_id": p2, "winner_id": winner, "is_ranked": ranked,
            "photon_room_id": room, "invalidated_at": invalidated, "ended_at": ended_at}


def _series(p1w, p2w, status="completed", invalidated=None, p1=ME, p2=OPP,
            p1_change=None, p2_change=None, completed_at=OLD):
    return {"player1_id": p1, "player2_id": p2, "p1_series_wins": p1w, "p2_series_wins": p2w,
            "status": status, "invalidated_at": invalidated,
            "p1_rating_change": p1_change, "p2_rating_change": p2_change, "completed_at": completed_at}


def _team(t1a, t1b, t2a, t2b, winner_team, ended_at=OLD, invalidated=None):
    return {"t1a": t1a, "t1b": t1b, "t2a": t2a, "t2b": t2b, "winner_team": winner_team,
            "ended_at": ended_at, "invalidated_at": invalidated}


def _ffa(players, ended_at=OLD, invalidated=None):
    """players: {player_id: (placement, absent)}"""
    return {"players": players, "ended_at": ended_at, "invalidated_at": invalidated}


def _ovt(solo, duo_a, duo_b, winner_side, ended_at=OLD, invalidated=None):
    return {"solo": solo, "duo_a": duo_a, "duo_b": duo_b, "winner_side": winner_side,
            "ended_at": ended_at, "invalidated_at": invalidated}


def _req(token="tok"):
    return SimpleNamespace(headers={"X-Session-Token": token} if token else {})


def _call(session, me=ME_SID, opp=OPP_SID, token="tok", keep_modes_cache=False):
    """One call outside any debounce window (the window is another suite's).

    The modes cache is module state keyed by the steam-id pair, so two
    FakeSessions for the SAME pair inside one test would otherwise share it
    and the second's fixture rows would never be read (that is what the cache
    is for, and exactly what the cache tests assert by passing
    keep_modes_cache=True). Every other call starts from an empty cache."""
    main._h2h_last_read.clear()
    if not keep_modes_cache:
        main._h2h_modes_cache.clear()
    return asyncio.run(main.h2h_summary(me, opp, _req(token), session))


def _count(statements, needle):
    return sum(needle in s for s in statements)


@pytest.fixture(autouse=True)
def _frozen_and_clean(monkeypatch):
    monkeypatch.setattr(main, "_utc_now", lambda: NOW)
    main._h2h_last_read.clear()
    main._h2h_modes_cache.clear()
    main._h2h_card_last_warn = 0.0
    yield
    main._h2h_last_read.clear()
    main._h2h_modes_cache.clear()


# ── the flat contract survives (A-4) ─────────────────────────────────────

def test_the_flat_contract_is_untouched_and_the_two_members_are_optional_and_last():
    names = list(schemas.H2HSummaryResponse.model_fields)
    assert names == FLAT_FIELDS + ["profile", "modes"], "flat fields first, unchanged; the card's members last"
    empty = schemas.H2HSummaryResponse()
    assert empty.profile is None and empty.modes is None
    # the empty response still serialises the flat defaults the line expects
    dumped = json.loads(empty.model_dump_json())
    assert list(dumped)[:len(FLAT_FIELDS)] == FLAT_FIELDS
    assert dumped["games_total"] == 0 and dumped["played_today"] is False and dumped["last_played_at"] is None
    assert dumped["profile"] is None and dumped["modes"] is None
    # the route still answers with this model
    routes = [r for r in main.app.routes if isinstance(r, APIRoute)
              and r.path == "/api/v1/h2h/{steam_id}/{opponent_steam_id}"]
    assert len(routes) == 1 and routes[0].response_model is schemas.H2HSummaryResponse


def test_no_nested_member_name_reuses_a_key_the_line_searches_for():
    nested = set()

    def walk(model):
        for name, field in model.model_fields.items():
            nested.add(name)
            for ann in getattr(field.annotation, "__args__", (field.annotation,)):
                if inspect.isclass(ann) and issubclass(ann, schemas.BaseModel):
                    walk(ann)
    walk(schemas.H2HProfileBlock)
    walk(schemas.H2HModesBlock)
    assert nested, "the walk found no members"
    assert not (nested & LINE_SEARCHED_KEYS), nested & LINE_SEARCHED_KEYS
    # negative control: the walk does see a real nested key
    assert {"is_online", "series_w", "as_solo", "holder"} <= nested


# ── the profile matrix (A-5) ─────────────────────────────────────────────

def test_profile_matrix_public_fields_always_presence_nulled_by_appear_offline_and_no_gold_or_discord():
    assert set(schemas.H2HProfileBlock.model_fields) == {
        "display_name", "title", "title_color", "tier", "tier_color",
        "rating_1v1", "rd_1v1", "level", "is_online", "last_seen_s",
    }
    for name in schemas.H2HProfileBlock.model_fields:
        assert "gold" not in name and "discord" not in name
    # visible target
    s = FakeSession(session_row=_good_session(), players=_players(title="Sharpshooter", title_color="#ABCDEF", title_sku="title_x"))
    r = _call(s)
    p = r.profile
    assert p is not None
    assert p.display_name == "Opp Name"
    assert (p.title, p.title_color) == ("Sharpshooter", "#ABCDEF")   # a static title passes through
    assert (p.rating_1v1, p.rd_1v1) == (1720, 55)
    assert p.level == main.level_from_xp(5000)[0] and p.level > 0
    assert (p.tier, p.tier_color) == (main._rank_name_for(1720.0), p.tier_color) and p.tier
    assert p.is_online is True and p.last_seen_s == 120
    # appear_offline: presence nulled, everything public still present
    s2 = FakeSession(session_row=_good_session(), players=_players(appear_offline=True))
    p2 = _call(s2).profile
    assert p2.is_online is None and p2.last_seen_s is None
    assert (p2.display_name, p2.rating_1v1, p2.rd_1v1, p2.level, p2.tier) == \
        ("Opp Name", 1720, 55, main.level_from_xp(5000)[0], main._rank_name_for(1720.0))
    # the projection carries no gold / Discord column (the fake refuses it)
    prof_sql = next(q for q in s.statements if "LEFT JOIN glicko_ratings gr" in q)
    assert "gold" not in prof_sql.lower() and "discord" not in prof_sql.lower()


def test_profile_title_and_tier_come_from_the_canonical_utilities():
    # the dynamic 'Current Rank' title renders as the live tier + tier colour,
    # exactly as the boards render it (_display_title_sync)
    s = FakeSession(session_row=_good_session(),
                    players=_players(title="Current Rank", title_color="#000000", title_sku=main.TITLE_RANK_SKU))
    p = _call(s).profile
    expected_tier = main._rank_name_for(1720.0)
    assert p.title == expected_tier == p.tier
    assert p.title_color == p.tier_color == main._rank_fallback_color(expected_tier)
    # a player with no glicko row reads as the defaults the boards assume
    s2 = FakeSession(session_row=_good_session(), players=[_player(ME_SID, ME, "Me"),
                                                            _player(OPP_SID, OPP, "Opp Name", rating=None, rd=None)])
    p2 = _call(s2).profile
    assert (p2.rating_1v1, p2.rd_1v1) == (1500, 350)
    assert p2.tier == main._rank_name_for(1500.0)


def test_the_card_uses_the_boards_online_marker_and_the_boards_pin_still_holds():
    # the four boards' exact form is untouched (test_online_marker pins == 4);
    # the card wraps the SAME constant in the appear_offline CASE
    assert SRC.count("{_ONLINE_MARKER_SQL} AS is_online") == 4
    assert SRC.count("CASE WHEN p.appear_offline THEN NULL ELSE {_ONLINE_MARKER_SQL} END AS is_online") == 1
    src = inspect.getsource(main._h2h_profile_block)
    assert "{_ONLINE_MARKER_SQL}" in src
    assert "p.last_seen > NOW() - INTERVAL" not in src, "no inline copy of the presence rule"


# ── the split cache (A-2) ────────────────────────────────────────────────

def test_modes_are_cached_sixty_seconds_per_pair_while_profile_is_read_every_time(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(main, "_h2h_cache_clock", lambda: clock["t"])
    players = _players()
    s = FakeSession(session_row=_good_session(), players=players,
                    matches=[_match(ME), _match(OPP, ranked=False)], series=[_series(2, 0)])

    def card_statements():
        return (_count(s.statements, "AS ranked_w"), _count(s.statements, "WITH team_games AS ("),
                _count(s.statements, "AS vchange"), _count(s.statements, "LEFT JOIN glicko_ratings gr"))

    r1 = _call(s, keep_modes_cache=True)
    assert card_statements() == (1, 1, 1, 1)
    assert (r1.modes.ranked_1v1.games_w, r1.modes.casual_1v1.l) == (1, 1)
    # 30 s later: modes from the cache (no helper / mode statements), profile read again
    clock["t"] += 30.0
    players[1]["appear_offline"] = True          # the toggle applies immediately (A-2)
    r2 = _call(s, keep_modes_cache=True)
    assert card_statements() == (1, 1, 1, 2)
    assert r2.modes is r1.modes, "a hit returns the cached block"
    assert r2.profile.is_online is None and r1.profile.is_online is True
    # 61 s after the first read: recomputed
    clock["t"] += 31.0
    r3 = _call(s, keep_modes_cache=True)
    assert card_statements() == (2, 2, 2, 3)
    assert r3.modes is not r1.modes
    # the reverse orientation is its own entry — computed, not served from ours
    s_rev = FakeSession(session_row=_good_session(sid=OPP_SID), players=players,
                        matches=[_match(ME), _match(OPP, ranked=False)], series=[_series(2, 0)])
    r_rev = _call(s_rev, me=OPP_SID, opp=ME_SID, keep_modes_cache=True)
    assert _count(s_rev.statements, "WITH team_games AS (") == 1
    assert (r_rev.modes.ranked_1v1.games_l, r_rev.modes.casual_1v1.w) == (1, 1)
    assert set(main._h2h_modes_cache) == {(ME_SID, OPP_SID), (OPP_SID, ME_SID)}


def test_the_modes_cache_is_capped_expired_first_then_oldest(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(main, "_h2h_cache_clock", lambda: clock["t"])
    monkeypatch.setattr(main, "_H2H_MODES_MAX_KEYS", 2)
    s = FakeSession(players=_players())

    def fill(a, b):
        return asyncio.run(main._h2h_modes_cached(s, a, b, ME, OPP))

    fill("A", "B")
    clock["t"] = 1.0
    fill("A", "C")
    clock["t"] = 2.0
    fill("A", "D")                                   # over the cap: nothing expired, oldest goes
    assert set(main._h2h_modes_cache) == {("A", "C"), ("A", "D")}
    clock["t"] = 70.0                                # both survivors are past the TTL
    fill("A", "E")
    assert set(main._h2h_modes_cache) == {("A", "E")}, "expired entries are dropped before any live one"
    # a live entry is never evicted while an expired one exists
    clock["t"] = 71.0
    fill("A", "F")
    clock["t"] = 72.0
    fill("A", "G")
    assert set(main._h2h_modes_cache) == {("A", "F"), ("A", "G")}
    # negative control: within the TTL, the same key is a hit, not a recompute
    before = _count(s.statements, "WITH team_games AS (")
    fill("A", "G")
    assert _count(s.statements, "WITH team_games AS (") == before


# ── the helper is the ranked/casual source (A-L) ─────────────────────────

def test_ranked_and_casual_blocks_are_the_helpers_answer(monkeypatch):
    calls = []

    async def fake_counts(db, viewer_id, player_id):
        calls.append((viewer_id, player_id))
        return 7, 3, 4, 6, 2, 1

    monkeypatch.setattr(main, "_viewer_h2h_counts", fake_counts)
    s = FakeSession(session_row=_good_session(), players=_players())
    r = _call(s)
    assert calls == [(ME, OPP)]
    assert (r.modes.ranked_1v1.series_w, r.modes.ranked_1v1.series_l,
            r.modes.ranked_1v1.games_w, r.modes.ranked_1v1.games_l) == (2, 1, 7, 3)
    assert (r.modes.casual_1v1.w, r.modes.casual_1v1.l) == (4, 6)
    # and the static half: the modes block CALLS the helper rather than restating it
    src = inspect.getsource(main._h2h_modes_block)
    assert "await _viewer_h2h_counts(" in src
    assert "COUNT(*) FILTER (WHERE m.is_ranked" not in src


def test_the_helpers_decided_only_rule_shows_beside_the_flat_series_fields():
    # flat: every completed valid series classified (a 1-0 row is won, a 2-2
    # row is a tie); helper: decided rows only (>= 2 on a side), a tie for neither
    s = FakeSession(session_row=_good_session(), players=_players(),
                    series=[_series(2, 0), _series(2, 2), _series(1, 0), _series(0, 2, p1=OPP, p2=ME)])
    r = _call(s)
    assert (r.series_won, r.series_lost, r.series_tied, r.series_total) == (3, 0, 1, 4)
    assert (r.modes.ranked_1v1.series_w, r.modes.ranked_1v1.series_l) == (2, 0)


# ── team / ffa / ovt / last meeting ──────────────────────────────────────

def test_team_ffa_ovt_blocks_and_last_meeting_from_fixture_rows():
    t0 = OLD
    s = FakeSession(session_row=_good_session(), players=_players(), team=[
        _team(ME, THIRD, OPP, FOURTH, 1, t0),                 # viewer's team won
        _team(OPP, THIRD, FOURTH, ME, 2, t0 + timedelta(hours=1)),   # viewer on team 2, won
        _team(ME, THIRD, FOURTH, OPP, 2, t0 + timedelta(hours=2)),   # lost
        _team(ME, OPP, THIRD, FOURTH, 1, t0 + timedelta(hours=3)),   # SAME team: not a meeting
        _team(ME, THIRD, OPP, FOURTH, 1, t0 + timedelta(hours=4), invalidated="x"),
        _team(THIRD, FOURTH, OPP, ME, 2, t0 + timedelta(hours=5)),   # same team again (team 2)
    ], ffa=[
        _ffa({ME: (1, False), OPP: (3, False), THIRD: (2, False)}, t0 + timedelta(hours=6)),   # above
        _ffa({ME: (4, False), OPP: (2, False)}, t0 + timedelta(hours=7)),                       # below
        _ffa({ME: (2, False), OPP: (2, False)}, t0 + timedelta(hours=8)),                       # tie: neither
        _ffa({ME: (1, True), OPP: (2, False)}, t0 + timedelta(hours=9)),                        # viewer absent
        _ffa({ME: (1, False), THIRD: (2, False)}, t0 + timedelta(hours=10)),                    # target not in it
        _ffa({ME: (1, False), OPP: (2, False)}, t0 + timedelta(hours=11), invalidated="x"),
    ], ovt=[
        _ovt(ME, OPP, THIRD, 1, t0 + timedelta(hours=12)),    # as_solo win
        _ovt(ME, THIRD, OPP, 2, t0 + timedelta(hours=13)),    # as_solo loss
        _ovt(OPP, ME, THIRD, 2, t0 + timedelta(hours=14)),    # as_duo win
        _ovt(OPP, THIRD, ME, 1, t0 + timedelta(hours=15)),    # as_duo loss
        _ovt(THIRD, ME, OPP, 2, t0 + timedelta(hours=16)),    # same duo: not a meeting
        _ovt(ME, OPP, THIRD, 1, t0 + timedelta(hours=17), invalidated="x"),
    ])
    m = _call(s).modes
    assert (m.team_2v2.w, m.team_2v2.l) == (2, 1)
    assert (m.ffa.above, m.ffa.below) == (1, 1)
    assert (m.ovt.as_solo.w, m.ovt.as_solo.l, m.ovt.as_duo.w, m.ovt.as_duo.l) == (1, 1, 1, 1)
    # the newest COUNTED game across every mode: the as_duo loss at +15h
    assert m.last_meeting is not None
    assert (m.last_meeting.mode, m.last_meeting.result) == ("ovt", "L")
    assert m.last_meeting.at == t0 + timedelta(hours=15)


def test_last_meeting_prefers_the_newest_across_modes_and_is_null_without_history():
    s = FakeSession(session_row=_good_session(), players=_players(),
                    matches=[_match(OPP, OLD + timedelta(hours=20), ranked=False),
                             _match(ME, OLD + timedelta(hours=1))],
                    team=[_team(ME, THIRD, OPP, FOURTH, 1, OLD + timedelta(hours=10))])
    m = _call(s).modes
    assert (m.last_meeting.mode, m.last_meeting.result) == ("casual_1v1", "L")
    assert m.last_meeting.at == OLD + timedelta(hours=20)
    # a no-winner game is nobody's meeting; a misroute never is
    s2 = FakeSession(session_row=_good_session(), players=_players(),
                     matches=[_match(None, OLD + timedelta(hours=30)), _match(ME, OLD + timedelta(hours=31), room="ffa_x")])
    assert _call(s2).modes.last_meeting is None
    empty = FakeSession(session_row=_good_session(), players=_players())
    m3 = _call(empty).modes
    assert m3.last_meeting is None and m3.streak is None and m3.net_rating_1v1 == 0
    assert (m3.team_2v2.w, m3.ffa.above, m3.ovt.as_duo.l) == (0, 0, 0)


# ── streak and net rating ────────────────────────────────────────────────

def test_streak_and_net_rating_fold_the_ordered_series():
    fold = main._h2h_series_streak_and_net
    rows = lambda *t: [{"vw": a, "pw": b, "vchange": c} for a, b, c in t]
    streak, net = fold(rows((2, 0, 12.4), (2, 1, 8.0), (1, 2, -10.0)))
    assert (streak.n, streak.holder, net) == (2, "viewer", 10)
    streak, net = fold(rows((0, 2, -5.0), (2, 0, 5.0)))
    assert (streak.n, streak.holder, net) == (1, "target", 0)
    assert fold([]) == (None, 0)
    # a level row ends the run before it starts; a NULL change counts as 0
    streak, net = fold(rows((2, 2, None), (2, 0, 9.0)))
    assert streak is None and net == 9
    # the run is counted from the NEWEST row, never the longest anywhere
    streak, net = fold(rows((0, 2, -1.0), (2, 0, 1.0), (2, 0, 1.0), (2, 0, 1.0)))
    assert (streak.n, streak.holder) == (1, "target") and net == 2


def test_streak_and_net_rating_via_the_route_are_oriented_to_the_caller():
    s = FakeSession(session_row=_good_session(), players=_players(), series=[
        _series(2, 0, p1_change=10.0, p2_change=-10.0, completed_at=OLD + timedelta(hours=3)),
        _series(0, 2, p1=OPP, p2=ME, p1_change=-7.0, p2_change=7.0, completed_at=OLD + timedelta(hours=2)),
        _series(1, 2, p1_change=-9.0, p2_change=9.0, completed_at=OLD + timedelta(hours=1)),
        _series(2, 1, p1_change=99.0, p2_change=-99.0, status="active"),                   # not completed
        _series(2, 0, p1_change=50.0, p2_change=-50.0, invalidated="x"),                   # invalidated
        _series(1, 0, p1_change=40.0, p2_change=-40.0, completed_at=OLD),                  # not decided
    ])
    m = _call(s).modes
    assert (m.streak.n, m.streak.holder) == (2, "viewer")
    assert m.net_rating_1v1 == 8
    # the same rows from the opponent's seat
    s2 = FakeSession(session_row=_good_session(sid=OPP_SID), players=_players(), series=s.series)
    m2 = _call(s2, me=OPP_SID, opp=ME_SID).modes
    assert (m2.streak.n, m2.streak.holder) == (2, "target")
    assert m2.net_rating_1v1 == -8


# ── edges ────────────────────────────────────────────────────────────────

def test_an_unknown_opponent_carries_no_card_and_issues_no_card_statement():
    s = FakeSession(session_row=_good_session(), players=[_player(ME_SID, ME, "Me")])
    r = _call(s)
    assert r.profile is None and r.modes is None and r.opponent_display_name is None
    assert not any("glicko_ratings" in q or "team_games" in q or "AS vchange" in q for q in s.statements)
    assert s.card_savepoints == 0
    # negative control for the attribution: the gate's own savepoint IS seen
    assert len(s.savepoint_after) == 1 and s.savepoint_after[0] == ""


def test_a_failed_card_statement_leaves_the_flat_line_intact():
    s = FakeSession(session_row=_good_session(), players=_players(),
                    matches=[_match(ME), _match(OPP)], series=[_series(2, 1)], fail_profile=True)
    r = _call(s)
    assert (r.opponent_display_name, r.games_won, r.games_lost, r.series_won) == ("Opp Name", 1, 1, 1)
    assert r.profile is None and r.modes is None
    assert s.card_savepoints == 1, "the card blocks run inside their own savepoint, after the flat facts"
    assert not s.aborted, "the savepoint exit rolled the failed statement back; the transaction is usable again"
    assert (ME_SID, OPP_SID) not in main._h2h_modes_cache
    # negative control: the same fixture without the fault carries both blocks
    ok = FakeSession(session_row=_good_session(), players=_players(),
                     matches=[_match(ME), _match(OPP)], series=[_series(2, 1)])
    r2 = _call(ok)
    assert r2.profile is not None and r2.modes is not None


def test_the_route_reads_profile_before_modes_and_only_after_the_flat_values():
    src = inspect.getsource(main.h2h_summary)
    facts = src.index("WITH pair_matches AS (")
    card = src.index("_h2h_card_blocks(")
    ret = src.index("return H2HSummaryResponse(\n        opponent_display_name=opp_name")
    assert facts < card < ret
    blocks = inspect.getsource(main._h2h_card_blocks)
    assert blocks.index("_h2h_profile_block(") < blocks.index("_h2h_modes_cached(")
    assert "begin_nested()" in blocks
    # the strict gate and the 400 still run before the first statement (the
    # other suite pins this too; repeated because the card added statements)
    gate = src.index("_strict_steam_session_ok(request, steam_id, db)")
    assert gate < src.index("db.execute(")


def test_fake_session_refuses_a_card_statement_that_lost_a_predicate():
    from sqlalchemy import text
    s = FakeSession(players=_players())
    with pytest.raises(AssertionError, match="modes statement lost"):
        asyncio.run(s.execute(text("WITH team_games AS (SELECT 1) SELECT 1"), {"vid": ME, "pid": OPP}))
    with pytest.raises(AssertionError, match="profile statement lost"):
        asyncio.run(s.execute(text("SELECT 1 FROM players p LEFT JOIN glicko_ratings gr ON gr.player_id = p.id"),
                              {"pid": OPP}))
    with pytest.raises(AssertionError, match="gold"):
        asyncio.run(s.execute(text(" ".join(PROFILE_PREDICATES) + " , p.gold_earned"), {"pid": OPP}))
    with pytest.raises(AssertionError, match="series list lost"):
        asyncio.run(s.execute(text("SELECT 1 AS vchange FROM ranked_series rs"), {"vid": ME, "pid": OPP}))
    # ...and the real statements pass the same fake
    real = FakeSession(session_row=_good_session(), players=_players())
    _call(real)
    assert _count(real.statements, "WITH team_games AS (") == 1


def test_the_fake_models_an_aborted_transaction_until_a_savepoint_exits():
    """Control for the assertion above (#391): the aborted state is real and
    sticky. Without a savepoint the refused statement leaves the session
    refusing everything; the same failure inside begin_nested() is rolled back."""
    s = FakeSession(session_row=_good_session(), players=_players(), fail_profile=True)

    async def bare():
        with pytest.raises(RuntimeError, match="refused by the fake"):
            await main._h2h_profile_block(s, OPP)
        assert s.aborted
        with pytest.raises(RuntimeError, match="transaction is aborted"):
            await s.execute("SELECT 1 FROM rank_role_colors")

    asyncio.run(bare())
    s2 = FakeSession(session_row=_good_session(), players=_players(), fail_profile=True)

    async def guarded():
        try:
            async with s2.begin_nested():
                await main._h2h_profile_block(s2, OPP)
        except RuntimeError:
            pass
        assert not s2.aborted
        await s2.execute("SELECT 1 FROM rank_role_colors")   # usable again

    asyncio.run(guarded())


def test_a_the_profile_card_reads_the_podium_maps_without_refreshing_or_granting():
    """Review a-H1: the card is a read; the refreshing podium lookup can sync
    (grant/revoke) the podium cosmetics and must not run on a hover."""
    src = inspect.getsource(main._h2h_profile_block)
    assert "_podium_maps_cached(" in src
    for forbidden in ("_podium_maps_for(", "_podium_map(", "_podium_map_2v2(", "_podium_map_ffa(", "_sync_podium"):
        assert forbidden not in src, forbidden
    cached = inspect.getsource(main._podium_maps_cached)
    body = cached.split('"""')[-1]                    # the code after the docstring
    assert not inspect.iscoroutinefunction(main._podium_maps_cached)
    assert "await" not in body and "_sync_podium" not in body and "_podium_map" + "(" not in body
    saved = (dict(main._podium_cache), dict(main._podium_2v2_cache), dict(main._podium_ffa_cache))
    try:
        for c in (main._podium_cache, main._podium_2v2_cache, main._podium_ffa_cache):
            c.clear()
        assert main._podium_maps_cached((main.TITLE_PODIUM_SKU,)) == ({}, {}, {})   # cold: nothing, no refresh
        main._podium_cache.update({"map": {"abc": 1}, "at": time.monotonic()})
        main._podium_ffa_cache.update({"map": {"fff": 3}, "at": time.monotonic()})
        m, m2, mf = main._podium_maps_cached((main.TITLE_PODIUM_SKU, main.TITLE_PODIUM_2V2_SKU))
        assert (m, m2, mf) == ({"abc": 1}, {}, {})                                  # only the asked-for ladders
        m["zzz"] = 2
        assert "zzz" not in main._podium_cache["map"], "a copy, never the cache itself"
        assert main._podium_maps_cached((None, "")) == ({}, {}, {})
        # round 2: a map the boards have not refreshed for longer than the bound is not served
        main._podium_cache["at"] = time.monotonic() - main._PODIUM_CACHED_MAX_AGE_S - 1
        assert main._podium_maps_cached((main.TITLE_PODIUM_SKU,)) == ({}, {}, {})
        main._podium_cache["at"] = time.monotonic() - main._PODIUM_CACHED_MAX_AGE_S + 5   # inside the bound: served
        assert main._podium_maps_cached((main.TITLE_PODIUM_SKU,))[0] == {"abc": 1}
        main._podium_cache["map"] = {}                                              # a refresh that emptied the map
        assert main._podium_maps_cached((main.TITLE_PODIUM_SKU,)) == ({}, {}, {})
    finally:
        for c, v in zip((main._podium_cache, main._podium_2v2_cache, main._podium_ffa_cache), saved):
            c.clear(); c.update(v)
