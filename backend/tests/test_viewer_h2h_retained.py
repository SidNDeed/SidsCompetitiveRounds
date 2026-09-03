"""Retained viewer-H2H semantics behind GET /api/v1/players/{steam_id} (the stats endpoint)
(lag-332 r1 MEDIUM 17 / LOW 18; behavioural per r7 LOW 7).

The queue-room H2H feature was cut from Release A; these predicates on the
pre-existing viewer H2H stay. `_viewer_h2h_counts` is executed against a fake
session that EMULATES the two statements it issues — and REFUSES a statement
that lost one of the load-bearing predicates, so a query edit cannot pass by
keeping the strings somewhere else in the module.
"""

import asyncio
import inspect

import main

VIEWER = "viewer-id"
PLAYER = "player-id"
THIRD = "third-id"

# r8 LOW 4: the fake emulates these rules in Python, so it must also VERIFY the
# statement it receives carries the exact projection, orientation and pair
# predicates that make the emulation a faithful reading of the SQL.
MATCH_PREDICATES = (
    "COUNT(*) FILTER (WHERE m.is_ranked AND m.winner_id = :vid) AS ranked_w",
    "COUNT(*) FILTER (WHERE m.is_ranked AND m.winner_id = :pid) AS ranked_l",
    "COUNT(*) FILTER (WHERE NOT m.is_ranked AND m.winner_id = :vid) AS casual_w",
    "COUNT(*) FILTER (WHERE NOT m.is_ranked AND m.winner_id = :pid) AS casual_l",
    "WHERE ((m.player1_id = :vid AND m.player2_id = :pid)",
    "OR (m.player1_id = :pid AND m.player2_id = :vid))",
    "m.invalidated_at IS NULL",
    "m.photon_room_id IS NULL OR (",
    "LEFT(m.photon_room_id, 5) <> 'team_'",
    "LEFT(m.photon_room_id, 4) <> 'ovt_'",
    "LEFT(m.photon_room_id, 4) <> 'ffa_'",
)
SERIES_PREDICATES = (
    "SELECT rs.player1_id AS p1, rs.p1_series_wins AS p1w, rs.p2_series_wins AS p2w",
    "rs.status = 'completed'",
    "rs.invalidated_at IS NULL",
    "AND ((rs.player1_id = :vid AND rs.player2_id = :pid)",
    "OR (rs.player1_id = :pid AND rs.player2_id = :vid))",
    "AND (rs.p1_series_wins >= 2 OR rs.p2_series_wins >= 2)",
)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class FakeViewerSession:
    """Emulates exactly the two statements `_viewer_h2h_counts` issues."""

    def __init__(self, matches=(), series=()):
        self.matches = list(matches)
        self.series = list(series)
        self.statements = []

    async def execute(self, statement, params):
        sql = str(statement)
        self.statements.append(sql)
        vid, pid = params["vid"], params["pid"]
        if "FROM matches m" in sql:
            for predicate in MATCH_PREDICATES:
                assert predicate in sql, f"match query lost predicate: {predicate}"
            eligible = [
                m for m in self.matches
                if {m["player1_id"], m["player2_id"]} == {vid, pid}
                and m.get("invalidated_at") is None
                and (m.get("photon_room_id") is None
                     or not m["photon_room_id"].startswith(("team_", "ovt_", "ffa_")))
            ]

            def count(ranked, winner):
                return sum(1 for m in eligible
                           if bool(m["is_ranked"]) is ranked and m.get("winner_id") == winner)

            return _Rows([{
                "ranked_w": count(True, vid), "ranked_l": count(True, pid),
                "casual_w": count(False, vid), "casual_l": count(False, pid),
            }])
        if "FROM ranked_series rs" in sql:
            for predicate in SERIES_PREDICATES:
                assert predicate in sql, f"series query lost predicate: {predicate}"
            rows = [
                {"p1": s["player1_id"], "p1w": s["p1_series_wins"], "p2w": s["p2_series_wins"]}
                for s in self.series
                if {s["player1_id"], s["player2_id"]} == {vid, pid}
                and s["status"] == "completed"
                and s.get("invalidated_at") is None
                and (s["p1_series_wins"] >= 2 or s["p2_series_wins"] >= 2)
            ]
            return _Rows(rows)
        raise AssertionError(f"unexpected statement: {sql[:80]}")


def _match(winner, ranked=True, room=None, invalidated=None, p1=VIEWER, p2=PLAYER):
    return {"player1_id": p1, "player2_id": p2, "winner_id": winner, "is_ranked": ranked,
            "photon_room_id": room, "invalidated_at": invalidated}


def _series(p1w, p2w, status="completed", invalidated=None, p1=VIEWER, p2=PLAYER):
    return {"player1_id": p1, "player2_id": p2, "p1_series_wins": p1w, "p2_series_wins": p2w,
            "status": status, "invalidated_at": invalidated}


def _counts(session, viewer=VIEWER, player=PLAYER):
    return asyncio.run(main._viewer_h2h_counts(session, viewer, player))


def test_helper_is_the_handler_s_only_h2h_source():
    source = inspect.getsource(main.get_player_stats)
    assert "await _viewer_h2h_counts(db, viewer_row, player.id)" in source
    assert "h2h_q = text(" not in source   # the H2H queries live in the helper only
    assert "h2h_series_l += 1" not in source


def test_match_counters_split_ranked_casual_and_orient_to_the_viewer():
    session = FakeViewerSession(matches=[
        _match(VIEWER), _match(VIEWER), _match(PLAYER),
        _match(VIEWER, ranked=False), _match(PLAYER, ranked=False), _match(PLAYER, ranked=False),
        _match(None),                       # unfinished / no winner: counts for neither
        _match(VIEWER, p1=THIRD, p2=VIEWER),  # another pair
    ])
    assert _counts(session) == (2, 1, 1, 2, 0, 0)
    # the same rows seen from the other seat swap wins and losses
    assert _counts(session, viewer=PLAYER, player=VIEWER) == (1, 2, 2, 1, 0, 0)


def test_invalidated_and_team_mode_matches_never_count_but_null_rooms_do():
    session = FakeViewerSession(matches=[
        _match(VIEWER, invalidated="2026-01-01"),
        _match(VIEWER, room="team_abc"),
        _match(VIEWER, room="ovt_abc"),
        _match(VIEWER, room="ffa_abc"),
        _match(VIEWER, room=None),
        _match(VIEWER, room="ranked_0123456789ab"),
        _match(VIEWER, room="ABCDEF"),
    ])
    assert _counts(session) == (3, 0, 0, 0, 0, 0)


def test_series_count_only_completed_decided_non_invalidated_rows_and_ties_for_neither():
    session = FakeViewerSession(series=[
        _series(2, 0),                                  # viewer won
        _series(1, 2),                                  # viewer lost
        _series(2, 2),                                  # tie: neither
        _series(3, 3),                                  # tie: neither
        _series(2, 0, status="active"),                 # not completed
        _series(1, 0),                                  # completed but undecided
        _series(2, 0, invalidated="2026-01-01"),        # invalidated
        _series(0, 2, p1=PLAYER, p2=VIEWER),            # viewer is player2 and won
    ])
    assert _counts(session) == (0, 0, 0, 0, 2, 1)
    assert _counts(session, viewer=PLAYER, player=VIEWER) == (0, 0, 0, 0, 1, 2)


def test_fake_session_refuses_a_query_that_lost_a_predicate():
    """The oracle itself: dropping any load-bearing predicate is caught at
    execution time, not by a substring search over the whole module."""
    import pytest
    from sqlalchemy import text

    session = FakeViewerSession()
    with pytest.raises(AssertionError, match="lost predicate"):
        asyncio.run(session.execute(text("SELECT 1 FROM matches m WHERE m.player1_id = :vid"),
                                    {"vid": VIEWER, "pid": PLAYER}))
    with pytest.raises(AssertionError, match="lost predicate"):
        asyncio.run(session.execute(text("SELECT 1 FROM ranked_series rs WHERE rs.status = 'completed'"),
                                    {"vid": VIEWER, "pid": PLAYER}))
    # r8 LOW 4 negative controls on the REAL statements the helper emits: a
    # swapped orientation, a dropped pair predicate and de-parenthesised series
    # wins each make the fake refuse the statement.
    recorder = FakeViewerSession()
    _counts(recorder)
    real_match_sql = next(q for q in recorder.statements if "FROM matches m" in q)
    real_series_sql = next(q for q in recorder.statements if "FROM ranked_series rs" in q)
    mutations = (
        real_match_sql.replace("m.winner_id = :vid) AS ranked_w", "m.winner_id = :pid) AS ranked_w"),
        real_match_sql.replace("WHERE ((m.player1_id = :vid AND m.player2_id = :pid)", "WHERE (TRUE"),
        real_series_sql.replace("AND (rs.p1_series_wins >= 2 OR rs.p2_series_wins >= 2)",
                                "AND rs.p1_series_wins >= 2 OR rs.p2_series_wins >= 2"),
        real_series_sql.replace("OR (rs.player1_id = :pid AND rs.player2_id = :vid))", "OR TRUE)"),
    )
    for mutated in mutations:
        assert mutated not in (real_match_sql, real_series_sql)
        with pytest.raises(AssertionError, match="lost predicate"):
            asyncio.run(session.execute(text(mutated), {"vid": VIEWER, "pid": PLAYER}))
