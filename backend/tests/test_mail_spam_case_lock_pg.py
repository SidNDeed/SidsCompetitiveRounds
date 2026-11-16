"""Mail's spam case row and account deletion on PostgreSQL, through inv_pg
(one cf_pg case schema per case, the real handlers in main.py).

delete_player_data scrubs the deleted player's steam id out of
moderation_cases.resolved_by, and later rewrites its own players row's
steam_id, a key column, which takes that row FOR UPDATE. A mail send's
fan-out holds FOR KEY SHARE on each recipient's players row. A send that
first took its sender's mail_spam case row at the case upsert, after its
fan-out, could wait on the scrub while the deletion's rewrite waited on the
send's key share, until PostgreSQL ended one of the two with 40P01. A send
now locks that row for the day before its message row and its fan-out
(main._MAIL_SPAM_CASE_LOCK_SQL).

In every test M (the player being deleted) resolved the sender S's
mail_spam case rows for today and tomorrow (UTC), and S's send to M crosses
the same-body threshold (MAIL_SPAM_SAME_BODY is 1 here), so the send writes
one of those rows.

- The deletion parked right AFTER its scrub, holding the case rows: the send
  waits at its lock on the case row, before its message row; once the
  deletion commits, the send finishes, its fan-out finding M deleted. The
  control removes the lock (a plain read): the send then waits at its case
  upsert after its fan-out, and the release ends in 40P01 on one side.
- The deletion parked right BEFORE its scrub, holding every lock it takes
  before the scrub: the send runs to its end while the deletion waits, so
  none of those locks conflicts with a send's path. The control makes one of
  them FOR UPDATE on M's players row: the send's fan-out then waits on the
  deletion, the deletion's scrub waits on the send's case row lock, and the
  release ends in 40P01 on one side.
"""

import asyncio
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

from inv_pg import Req, case  # noqa: E402

import main  # noqa: E402

BOUND = 30                      # seconds: no wait in this file is longer
POLL = 0.05                     # seconds between two reads of the waits
SECRET = "mail-spam-case-lock-secret"
BODY = "An ordinary message."
# delete_player_data's resolved_by scrub, as main.py sends it
SCRUB = "UPDATE moderation_cases SET resolved_by = :tomb WHERE resolved_by = :sid"
# The send's lock statement as it reaches PostgreSQL: the part before its bind
LOCK_HEAD = "SELECT 1 FROM moderation_cases WHERE kind = 'mail_spam' AND bucket_key = "
# The first statement of the deletion that locks its own players row, as sent
PC_SHARDS = "UPDATE players SET pc_shards = 0 WHERE id = $1"


def _deadlock(x):
    """True when `x` is an exception whose chain holds PostgreSQL's 40P01."""
    seen = set()
    while isinstance(x, BaseException) and id(x) not in seen:
        seen.add(id(x))
        if getattr(x, "sqlstate", None) == "40P01" or type(x).__name__ == "DeadlockDetectedError":
            return True
        x = getattr(x, "orig", None) or x.__cause__ or x.__context__
    return False


def _name(x):
    if isinstance(x, BaseException):
        return "%s: %s" % (type(x).__name__, str(x)[:300])
    return repr(x)


async def _seed(env):
    """S, M, and S's mail_spam case rows for today and tomorrow (UTC),
    resolved by M."""
    s, m = await env.players(2)
    env.mp.setattr(main, "MAIL_SPAM_SAME_BODY", 1)
    now = datetime.now(timezone.utc)
    for d in (0, 1):
        day = (now + timedelta(days=d)).strftime("%Y-%m-%d")
        await env.conn.execute(
            "INSERT INTO moderation_cases (kind, subject_player_id, evidence, bucket_key, status,"
            "                              resolved_at, resolved_by)"
            " VALUES ('mail_spam', $1, CAST($2 AS jsonb), $3, 'resolved', NOW(), $4)",
            s.id, json.dumps({"hits": 1}), "%s:%s" % (s.id, day), m.sid)
    return s, m


async def _delete(env, p):
    """Account deletion for `p`, signed with the case's secret."""
    env.mp.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    env.mp.delenv("STEAM_WEB_API_KEY", raising=False)
    sig = hmac.new(SECRET.encode(), ("delete:%s" % p.sid).encode(), hashlib.sha256).hexdigest()
    return await env.call(lambda db: main.delete_player_data(p.sid, Req(p.sid), sig=sig, _slot=None,
                                                             db=db))


async def _race(env, s, m, *, park):
    """Delete M and park the deletion at its scrub (park "after": the scrub
    has run; "before": it has not), then send S's mail to M. Wait until the
    send has finished or waits on the deletion; then release the deletion
    and wait for both. Returns the deletion's and the send's outcomes (an
    Answer, or the exception it raised), whether the send finished while the
    deletion was parked, and the statement the send waited at (None if it
    did not wait)."""
    assert park in ("after", "before")
    parked, release = asyncio.Event(), asyncio.Event()
    state = {}
    execute = AsyncSession.execute

    async def observed(db, statement, params=None, *args, **kwargs):
        hold = SCRUB in str(statement) and not parked.is_set()
        if hold and park == "before":
            state["pid"] = (await execute(db, text("SELECT pg_backend_pid()"))).scalar()
            parked.set()
            await release.wait()
        out = await execute(db, statement, params, *args, **kwargs)
        if hold and park == "after":
            state["pid"] = (await execute(db, text("SELECT pg_backend_pid()"))).scalar()
            parked.set()
            await release.wait()
        return out
    env.mp.setattr(AsyncSession, "execute", observed)

    a = asyncio.ensure_future(_delete(env, m))
    b = None
    where = None
    try:
        for _ in range(int(BOUND / POLL)):
            if parked.is_set() or a.done():
                break
            await asyncio.sleep(POLL)
        assert parked.is_set(), ("the deletion did not reach its scrub",
                                 _name(a.exception() or a.result()) if a.done() else "still running")
        b = asyncio.ensure_future(env.mail(s, [m], body=BODY))
        for _ in range(int(BOUND / POLL)):
            if b.done():
                break
            row = await env.conn.fetchrow(
                "SELECT pid, query FROM pg_stat_activity WHERE $1 = ANY(pg_blocking_pids(pid))",
                state["pid"])
            if row is not None:
                where = row["query"]
                break
            await asyncio.sleep(POLL)
        finished = b.done()
        assert finished or where is not None, "the send neither finished nor waited on the deletion"
    finally:
        release.set()
        outcomes = await asyncio.wait_for(
            asyncio.gather(a, *([b] if b is not None else []), return_exceptions=True), BOUND)
    return outcomes[0], outcomes[1], finished, where


async def _rows(env, s):
    return [dict(r) for r in await env.conn.fetch(
        "SELECT bucket_key, resolved_by, evidence->>'latest_message_id' AS latest"
        "  FROM moderation_cases WHERE kind = 'mail_spam' AND subject_player_id = $1"
        " ORDER BY bucket_key", s.id)]


def test_a_send_waits_for_the_scrub_before_its_fan_out_and_both_finish(monkeypatch):
    """The deletion holds S's case rows through its scrub. The send waits at
    its lock on the case row, before its message row and fan-out; the
    deletion then rewrites M's row and commits; the send finishes after it.
    Without the lock this is the cycle: the outcomes are checked first, so
    on such a tree the failure names the 40P01."""
    async def body(env):
        s, m = await _seed(env)
        a, b, finished, where = await _race(env, s, m, park="after")
        assert not isinstance(a, BaseException) and not isinstance(b, BaseException), (_name(a), _name(b))
        assert a.status == 200 and a["status"] == "anonymized", a
        assert b.status == 200 and b["accepted"] is True, b
        assert not finished and where is not None and where.startswith(LOCK_HEAD), where
        assert "FOR NO KEY UPDATE" in where, where
        assert LOCK_HEAD in main._MAIL_SPAM_CASE_LOCK_SQL.replace(":bucket", "")
        # the fan-out ran after the deletion committed: M, deleted, got no envelope
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM mail_recipients WHERE message_id = CAST($1 AS uuid)", b["id"]) == 0
        rows = await _rows(env, s)
        assert [r["resolved_by"] for r in rows] == [a["placeholder"]] * 2, rows
        assert [r["latest"] for r in rows].count(b["id"]) == 1, rows
    case(monkeypatch, body)


def test_control_a_send_that_does_not_lock_the_case_row_first_closes_a_cycle(monkeypatch):
    """The mutant: the send's lock on the case row becomes a plain read. The
    send then runs its fan-out (key share on M's row) and waits at its case
    upsert on the scrub; released, the deletion's rewrite of M's row waits
    on the send: one of the two ends with 40P01."""
    async def body(env):
        s, m = await _seed(env)
        with env.rewriting(" FOR NO KEY UPDATE", "", where=LOCK_HEAD) as hits:
            a, b, finished, where = await _race(env, s, m, park="after")
        assert hits and all(h.startswith(LOCK_HEAD) for h in hits), hits
        assert not finished and where is not None and "INSERT INTO moderation_cases" in where, where
        assert [_deadlock(a), _deadlock(b)].count(True) == 1, (_name(a), _name(b))
        ok = b if _deadlock(a) else a
        assert not isinstance(ok, BaseException) and ok.status == 200, _name(ok)
    case(monkeypatch, body)


def test_a_send_finishes_while_the_deletion_holds_every_lock_it_takes_before_its_scrub(monkeypatch):
    """The deletion parked just before its scrub holds every lock it takes
    before it, its own players row among them (non-key updates: FOR NO KEY
    UPDATE). The send, its lock on the case row and its fan-out's key share
    on M's row included, runs to its end meanwhile; the deletion then
    scrubs the rows the send wrote and finishes."""
    async def body(env):
        s, m = await _seed(env)
        a, b, finished, where = await _race(env, s, m, park="before")
        assert not isinstance(a, BaseException) and not isinstance(b, BaseException), (_name(a), _name(b))
        assert finished and where is None, where
        assert b.status == 200 and b["accepted"] is True, b
        assert a.status == 200 and a["status"] == "anonymized", a
        rows = await _rows(env, s)
        assert [r["resolved_by"] for r in rows] == [a["placeholder"]] * 2, rows
        assert [r["latest"] for r in rows].count(b["id"]) == 1, rows
    case(monkeypatch, body)


def test_control_a_deletion_that_locked_its_players_row_for_update_before_its_scrub_closes_a_cycle(
        monkeypatch):
    """The mutant: the deletion's first update of its own players row also
    takes that row FOR UPDATE. The send takes its case row lock, then its
    fan-out waits on the deletion for M's row; released, the deletion's
    scrub waits on the send's case row lock: one of the two ends with
    40P01. So the mode in which the deletion holds its own row before the
    scrub is what keeps this order free of a cycle."""
    async def body(env):
        s, m = await _seed(env)
        mutant = PC_SHARDS + " AND EXISTS (SELECT 1 FROM players q WHERE q.id = $1 FOR UPDATE)"
        with env.rewriting(PC_SHARDS, mutant) as hits:
            a, b, finished, where = await _race(env, s, m, park="before")
        assert len(hits) == 1, hits
        assert not finished and where is not None and "FOR KEY SHARE OF p" in where, where
        assert [_deadlock(a), _deadlock(b)].count(True) == 1, (_name(a), _name(b))
        ok = b if _deadlock(a) else a
        assert not isinstance(ok, BaseException) and ok.status == 200, _name(ok)
    case(monkeypatch, body)
