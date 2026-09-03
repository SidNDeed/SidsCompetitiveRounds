"""1v1 queue pair writers (v1.40.1, item 3).

GET /api/v1/queue/poll/{steam_id} requires the caller's own valid Steam session
(fail-closed) before it touches presence. queue_leave deletes only the leaver's
row (once that deletion commits, the partner's next accepted poll releases it and
answers "searching"). _evict_other_queue_searching keeps its own bespoke, non-RETURNING
partner reset and is NOT covered by these tests; queue_decline validates only the
caller's row and resets the partner conditionally. Both room-issuing branches
(queue_poll both-ready, queue_ready both-ready) stamp the room through ONE
conditional UPDATE ... RETURNING that requires a reciprocal, both-ready, room-less
pair; a short count dissolves only the caller's row. The ready-timeout and
ban-dissolve resets touch the partner only when reciprocal.

Style of test_viewer_h2h_retained.py: the helpers are EXECUTED against a fake
session that emulates the statements they issue and REFUSES a statement that
lost one of the load-bearing predicates, so a query edit cannot pass by keeping
the strings somewhere else in the module. Source-shape tests pin the handlers to
the helpers and to the session-before-presence order.
"""

import asyncio
import inspect
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import text

import main

ME = UUID("11111111-1111-1111-1111-111111111111")
PARTNER = UUID("22222222-2222-2222-2222-222222222222")
THIRD = UUID("33333333-3333-3333-3333-333333333333")

STAMP_PREDICATES = (
    "SET room_name = :room, room_region = :region",
    "WHERE player_id IN (:a, :b)",
    "AND status = 'matched' AND ready = true AND room_name IS NULL",
    "AND ((player_id = :a AND matched_with = :b)",
    "OR (player_id = :b AND matched_with = :a))",
    "RETURNING player_id",
)
PARTNER_RESET_PREDICATES = (
    "SET status = 'searching', matched_with = NULL,",
    "room_name = NULL, room_region = NULL, ready = false, matched_at = NULL",
    "WHERE player_id = :partner AND status = 'matched'",
    "AND matched_with = :me AND room_name IS NULL",
    "RETURNING player_id",
)
PARTNER_DELETE_PREDICATES = (
    "DELETE FROM ranked_queue",
    "WHERE player_id = :partner AND status = 'matched' AND matched_with = :me",
    "RETURNING player_id",
)
OWN_RESET_PREDICATES = (
    "SET status = 'searching', matched_with = NULL,",
    "room_name = NULL, room_region = NULL, ready = false, matched_at = NULL",
    "WHERE player_id = :pid",
)


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def mappings(self):
        return self


def _row(pid, status="matched", matched_with=None, ready=False, room=None, region=None):
    return {"player_id": pid, "status": status, "matched_with": matched_with,
            "ready": ready, "room_name": room, "room_region": region, "matched_at": None}


class FakeQueueSession:
    """Emulates exactly the four pair-writer statements over an in-memory
    ranked_queue, verifying each statement still carries its predicates."""

    def __init__(self, rows):
        self.rows = {r["player_id"]: dict(r) for r in rows}
        self.statements = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        params = params or {}
        if "SET room_name = :room, room_region = :region" in sql:
            for p in STAMP_PREDICATES:
                assert " ".join(p.split()) in sql, f"stamp lost predicate: {p}"
            a, b = params["a"], params["b"]
            out = []
            for pid, r in self.rows.items():
                if pid not in (a, b) or r["status"] != "matched" or not r["ready"] or r["room_name"] is not None:
                    continue
                if not ((pid == a and r["matched_with"] == b) or (pid == b and r["matched_with"] == a)):
                    continue
                r["room_name"] = params["room"]
                r["room_region"] = params["region"]
                out.append((pid,))
            return _Result(out)
        if "WHERE player_id = :partner AND status = 'matched' AND matched_with = :me RETURNING" in sql and sql.startswith("DELETE"):
            for p in PARTNER_DELETE_PREDICATES:
                assert " ".join(p.split()) in sql, f"partner delete lost predicate: {p}"
            r = self.rows.get(params["partner"])
            if r and r["status"] == "matched" and r["matched_with"] == params["me"]:
                del self.rows[params["partner"]]
                return _Result([(params["partner"],)])
            return _Result([])
        if "WHERE player_id = :partner AND status = 'matched'" in sql:
            for p in PARTNER_RESET_PREDICATES:
                assert " ".join(p.split()) in sql, f"partner reset lost predicate: {p}"
            r = self.rows.get(params["partner"])
            if r and r["status"] == "matched" and r["matched_with"] == params["me"] and r["room_name"] is None:
                r.update(status="searching", matched_with=None, room_name=None, room_region=None,
                         ready=False, matched_at=None)
                return _Result([(params["partner"],)])
            return _Result([])
        if "WHERE player_id = :pid" in sql and "SET status = 'searching'" in sql:
            for p in OWN_RESET_PREDICATES:
                assert " ".join(p.split()) in sql, f"own reset lost predicate: {p}"
            r = self.rows.get(params["pid"])
            if r:
                r.update(status="searching", matched_with=None, room_name=None, room_region=None,
                         ready=False, matched_at=None)
            return _Result([])
        raise AssertionError(f"unexpected statement: {sql[:100]}")


def _run(coro):
    return asyncio.run(coro)


# ── the pure reciprocity predicate ──────────────────────────────────────────

def test_reciprocal_predicate_requires_both_rows_to_name_each_other():
    me = _row(ME, matched_with=PARTNER)
    assert main._queue_pair_reciprocal(me, _row(PARTNER, matched_with=ME))
    assert not main._queue_pair_reciprocal(me, _row(PARTNER, matched_with=THIRD))       # partner re-paired
    assert not main._queue_pair_reciprocal(me, _row(PARTNER, status="searching"))       # partner reset
    assert not main._queue_pair_reciprocal(me, _row(PARTNER, status="matched"))         # partner points nowhere
    assert not main._queue_pair_reciprocal(_row(ME, matched_with=THIRD), _row(PARTNER, matched_with=ME))
    assert not main._queue_pair_reciprocal(_row(ME, status="searching"), _row(PARTNER, matched_with=ME))
    assert not main._queue_pair_reciprocal(me, None)
    assert not main._queue_pair_reciprocal(None, _row(PARTNER, matched_with=ME))
    assert not main._queue_pair_reciprocal({}, {})


# ── the conditional room stamp ───────────────────────────────────────────────

def test_stamp_writes_both_rows_of_an_intact_pair_and_reports_true():
    session = FakeQueueSession([
        _row(ME, matched_with=PARTNER, ready=True),
        _row(PARTNER, matched_with=ME, ready=True),
    ])
    assert _run(main._queue_stamp_room_reciprocal(session, ME, PARTNER, "ranked_abc", "eu")) is True
    assert session.rows[ME]["room_name"] == "ranked_abc" and session.rows[PARTNER]["room_name"] == "ranked_abc"
    assert session.rows[ME]["room_region"] == "eu" and session.rows[PARTNER]["room_region"] == "eu"


@pytest.mark.parametrize("partner", [
    _row(PARTNER, matched_with=THIRD, ready=True),          # re-paired elsewhere
    _row(PARTNER, status="searching"),                      # reset to searching
    _row(PARTNER, matched_with=ME, ready=False),            # not ready
    _row(PARTNER, matched_with=ME, ready=True, room="ranked_old"),   # already room-issued
])
def test_stamp_reports_false_when_the_partner_is_not_reciprocal_both_ready_and_room_less(partner):
    session = FakeQueueSession([_row(ME, matched_with=PARTNER, ready=True), partner])
    assert _run(main._queue_stamp_room_reciprocal(session, ME, PARTNER, "ranked_abc", "eu")) is False
    # the partner row is never stamped by a failed pair stamp
    assert session.rows[PARTNER].get("room_name") != "ranked_abc"


def test_stamp_missing_partner_row_reports_false():
    session = FakeQueueSession([_row(ME, matched_with=PARTNER, ready=True)])
    assert _run(main._queue_stamp_room_reciprocal(session, ME, PARTNER, "ranked_abc", "eu")) is False


# ── partner reset / delete only when reciprocal ─────────────────────────────

def test_partner_reset_only_touches_a_row_that_still_points_back():
    session = FakeQueueSession([
        _row(ME, matched_with=PARTNER),
        _row(PARTNER, matched_with=ME),
    ])
    assert _run(main._queue_reset_partner_if_reciprocal(session, ME, PARTNER)) is True
    assert session.rows[PARTNER]["status"] == "searching" and session.rows[PARTNER]["matched_with"] is None

    session = FakeQueueSession([_row(ME, matched_with=PARTNER), _row(PARTNER, matched_with=THIRD)])
    assert _run(main._queue_reset_partner_if_reciprocal(session, ME, PARTNER)) is False
    assert session.rows[PARTNER]["matched_with"] == THIRD          # untouched

    session = FakeQueueSession([_row(ME, matched_with=PARTNER), _row(PARTNER, matched_with=ME, room="ranked_x")])
    assert _run(main._queue_reset_partner_if_reciprocal(session, ME, PARTNER)) is False
    assert session.rows[PARTNER]["room_name"] == "ranked_x"        # room-issued rows are past the point of no return

    assert _run(main._queue_reset_partner_if_reciprocal(session, ME, None)) is False


def test_partner_delete_only_removes_a_row_that_still_points_back():
    session = FakeQueueSession([_row(ME, matched_with=PARTNER), _row(PARTNER, matched_with=ME)])
    assert _run(main._queue_delete_partner_if_reciprocal(session, ME, PARTNER)) is True
    assert PARTNER not in session.rows
    session = FakeQueueSession([_row(ME, matched_with=PARTNER), _row(PARTNER, matched_with=THIRD)])
    assert _run(main._queue_delete_partner_if_reciprocal(session, ME, PARTNER)) is False
    assert PARTNER in session.rows


def test_own_reset_targets_exactly_the_caller():
    session = FakeQueueSession([_row(ME, matched_with=PARTNER, ready=True), _row(PARTNER, matched_with=ME, ready=True)])
    _run(main._queue_reset_to_searching(session, ME))
    assert session.rows[ME]["status"] == "searching" and session.rows[ME]["ready"] is False
    assert session.rows[ME]["matched_at"] is None
    assert session.rows[PARTNER]["status"] == "matched" and session.rows[PARTNER]["matched_with"] == ME


# ── the oracle itself: mutated real statements are refused ──────────────────

def test_fake_session_refuses_statements_that_lost_a_predicate():
    recorder = FakeQueueSession([_row(ME, matched_with=PARTNER, ready=True), _row(PARTNER, matched_with=ME, ready=True)])
    _run(main._queue_stamp_room_reciprocal(recorder, ME, PARTNER, "r", "eu"))
    _run(main._queue_reset_partner_if_reciprocal(recorder, ME, PARTNER))
    _run(main._queue_delete_partner_if_reciprocal(recorder, ME, PARTNER))
    stamp_sql = next(q for q in recorder.statements if "SET room_name = :room" in q)
    reset_sql = next(q for q in recorder.statements if "WHERE player_id = :partner AND status = 'matched' AND matched_with = :me AND room_name IS NULL" in q)
    delete_sql = next(q for q in recorder.statements if q.startswith("DELETE"))
    mutations = (
        stamp_sql.replace("AND status = 'matched' AND ready = true AND room_name IS NULL", "AND status = 'matched' AND ready = true"),
        stamp_sql.replace("OR (player_id = :b AND matched_with = :a))", "OR player_id = :b)"),
        stamp_sql.replace("RETURNING player_id", ""),
        reset_sql.replace("AND matched_with = :me AND room_name IS NULL", "AND matched_with = :me"),
        delete_sql.replace("AND matched_with = :me", ""),
    )
    session = FakeQueueSession([])
    for mutated in mutations:
        assert mutated not in (stamp_sql, reset_sql, delete_sql)
        with pytest.raises(AssertionError, match="lost predicate"):
            _run(session.execute(text(mutated), {"a": ME, "b": PARTNER, "room": "r", "region": "eu",
                                                 "partner": PARTNER, "me": ME}))


# ── source shape: the handlers use the helpers, and the poll gates first ─────

def test_queue_poll_requires_own_session_before_presence_and_takes_request():
    sig = inspect.signature(main.queue_poll)
    assert "request" in sig.parameters
    assert sig.parameters["request"].annotation is main.Request
    src = inspect.getsource(main.queue_poll)
    gate = src.index("_strict_steam_session_ok(request, steam_id, db)")
    presence = src.index("_presence_touch(steam_id)")
    assert gate < presence, "the session gate must run before presence is touched"
    assert 'raise HTTPException(status_code=401, detail="session_required")' in src[gate:presence]
    # no soft-fail compatibility gate stands in for the strict one on this route
    assert "_check_steam_session(" not in src


def test_room_issuing_branches_stamp_only_through_the_reciprocal_helper():
    for handler, own in ((main.queue_poll, "my_pid"), (main.queue_ready, "player.id")):
        src = inspect.getsource(handler)
        assert "_queue_stamp_room_reciprocal(" in src, handler.__name__
        assert "UPDATE ranked_queue SET room_name = :room, room_region = :region WHERE player_id = :pid" not in src, handler.__name__
        # a failed stamp dissolves ONLY the caller's row, INSIDE the stamp-failure
        # branch itself (not merely somewhere later in the handler)
        m = re.search(r"if not await _queue_stamp_room_reciprocal\([^\n]*\):\n(?:[^\n]*\n){1,2}?\s*await _queue_reset_to_searching\(db, "
                      + re.escape(own) + r"\)", src)
        assert m, f"{handler.__name__}: the stamp-failure branch does not reset the caller's own row"
        assert "_queue_reset_partner_if_reciprocal(db, " not in src[m.start():m.end()]


def test_ready_dissolutions_reset_the_own_row_and_answer_dissolved():
    """A dissolution (non-reciprocal pair, failed reciprocal stamp, replay room
    mismatch) resets the caller's OWN row and answers 200 'dissolved' — the
    1.40.1 client returns to Searching on it. The pair is read under the locks
    BEFORE the caller's ready write. The only 503 left is the pre-existing
    re-pair race (a 5xx is what the generic retry loop is built for); the ban
    dissolution keeps its 409."""
    src = inspect.getsource(main.queue_ready)
    assert '"status": "not_matched", "message": "Match dissolved' not in src
    assert "pair_changed" not in src and "dissolved_at_ready" not in src
    adjacent = re.findall(r"await _queue_reset_to_searching\(db, player\.id\)\s+await db\.commit\(\)\s+"
                          r"return \{\"status\": \"dissolved\"", src)
    assert len(adjacent) == 3
    assert src.count('raise HTTPException(status_code=503, detail="queue_contended")') == 1
    assert 'raise HTTPException(409, "match dissolved (participant banned)")' in src
    opp_read = src.index("FROM ranked_queue WHERE player_id = :oid")
    reciprocal = src.index("_queue_pair_reciprocal(entry, opp)")
    ready_write = src.index("UPDATE ranked_queue SET ready = true WHERE player_id = :pid")
    assert opp_read < reciprocal < ready_write


def test_poll_commits_the_block_sweep_before_any_pair_lock():
    src = inspect.getsource(main.queue_poll)
    assert "dissolved_at_ready" not in src and 'if entry["matched_at"] is not None:' not in src
    # r11 finding 4: the expired-block sweep commits before any pair lock
    sweep = src.index("DELETE FROM queue_blocks")
    commit = src.index("await db.commit()", sweep)
    lock = src.index("_lock_queue_rows_ordered(")
    assert sweep < commit < lock


def test_queue_decline_resets_the_partner_only_when_reciprocal():
    src = inspect.getsource(main.queue_decline)
    assert "_queue_reset_to_searching(db, p1.id)" in src
    assert "_queue_reset_partner_if_reciprocal(db, p1.id, p2.id)" in src
    assert "for pid in [p1.id, p2.id]" not in src


def test_poll_and_ready_read_partner_status_and_matched_with_under_the_locks():
    for handler in (main.queue_poll, main.queue_ready):
        src = inspect.getsource(handler)
        assert re.search(r"SELECT[^;]*?status, matched_with\s+FROM ranked_queue WHERE player_id = :oid", src), handler.__name__
        assert "_queue_pair_reciprocal(entry, opp)" in src, handler.__name__


def test_timeout_and_ban_resets_touch_the_partner_only_through_conditional_helpers():
    poll = inspect.getsource(main.queue_poll)
    ready = inspect.getsource(main.queue_ready)
    for src, name in ((poll, "queue_poll"), (ready, "queue_ready")):
        assert "_queue_reset_partner_if_reciprocal(db, " in src, name
        assert "_queue_delete_partner_if_reciprocal(db, " in src, name
        # the old unconditional pair loops are gone
        assert 'for pid in [my_pid, opp["player_id"]]' not in src, name
        assert 'for _pp, _ps in _pair' not in src, name
        assert "WHERE player_id = ANY(:pids)" not in src, name


def test_queue_leave_deletes_only_the_caller():
    """The partner is released by its OWN next poll, which answers "searching" —
    the client-visible boundary a ReadySent seat needs before it can be
    re-matched. A direct partner reset here let that seat's next poll re-match
    it at once (Codex r13 finding 4)."""
    src = inspect.getsource(main.queue_leave)
    assert "DELETE FROM ranked_queue WHERE player_id = :pid" in src
    assert "_queue_reset_partner_if_reciprocal" not in src
    assert "UPDATE ranked_queue" not in src
    assert "_lock_queue_rows_ordered" not in src


def test_strict_session_gate_is_fail_closed_for_the_poll():
    """The gate the poll uses, executed: no token / unknown token / mismatched
    steam_id / expired / unverified all fail; a matching verified row passes."""
    now = datetime.now(timezone.utc)

    class _S:
        def __init__(self, row):
            self.row = row

        async def execute(self, statement, params):
            assert "FROM steam_sessions" in str(statement)
            return _Result([self.row] if self.row else [])

    def req(token):
        return SimpleNamespace(headers={"X-Session-Token": token} if token else {})

    good = {"steam_id": "76561198000000001", "verified": True, "expires_at": now + timedelta(hours=1)}
    assert _run(main._strict_steam_session_ok(req("t"), "76561198000000001", _S(good))) is True
    assert _run(main._strict_steam_session_ok(req(None), "76561198000000001", _S(good))) is False
    assert _run(main._strict_steam_session_ok(req("t"), "76561198000000001", _S(None))) is False
    assert _run(main._strict_steam_session_ok(req("t"), "76561198000000002", _S(good))) is False
    assert _run(main._strict_steam_session_ok(req("t"), "76561198000000001",
                                              _S(dict(good, expires_at=now - timedelta(seconds=1))))) is False
    assert _run(main._strict_steam_session_ok(req("t"), "76561198000000001", _S(dict(good, verified=False)))) is False
    assert _run(main._strict_steam_session_ok(None, "76561198000000001", _S(good))) is False
