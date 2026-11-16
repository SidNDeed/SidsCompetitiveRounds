"""Account deletion and the moderation_cases rows that name the deleted
account, on PostgreSQL, through inv_pg (one cf_pg case schema per case, the
real handlers in main.py). The mail spam case lock lane, route B.

delete_player_data writes moderation_cases in ONE statement, its last before
its commit (main._DELETE_CASE_SCRUB_SQL): reporter_id goes NULL and
resolved_by takes the deletion's tombstone, on the rows it can lock now, FOR
NO KEY UPDATE SKIP LOCKED. A row another transaction holds keeps its values
until the janitor's main._mail_case_scrub_pass finishes it: by predicate,
SKIP LOCKED, each half in a transaction of its own. So the deletion never
holds a case row while it waits for anything, and never waits for one. That
closes the circles through a case row and nothing wider: waits between the
deletion and the retention purge, or two deletions, on mail rows that are
not case rows are the open item MDPL (the purge tests here seed none).

A mutant here is a statement rewrite (inv_pg Env.rewriting: what reaches
PostgreSQL) or a stand-in for one function or one transaction boundary of
main.py. Each control runs its green test's own schedule under the mutant
and names the assertion of that test which the mutant breaks (lesson 712):

  green test (the schedule)                      mutant -> what fails
  a send over a threshold finishes while the     the resolved_by scrub put back before the flush (at
    deletion is parked at the base's scrub point   the base's place) -> 40P01: "outcomes"
  a send, a relay-off and the purge all finish   (control: this test at 8cd7fa8c, the lane's first
                                                   route, must end in 40P01; run on a proof tree)
  a held case row is skipped, kept and finished  SKIP LOCKED taken out -> "not inside the bound";
    by one sweep pass (the battery case)           the sweep taken out -> "completeness"
  the last statement does not wait on the        the base's separate early reporter scrub -> the
    subject's players row held FOR UPDATE          row's second write re-checks its foreign keys and
                                                   trips lock_timeout: "outcome"
  one sweep pass over a row both halves match    both halves in one transaction -> the same:
    does not wait on that row either               "outcome"
  the sweep skips a held row and finds it again  SKIP LOCKED taken out of both halves -> lock_timeout
    on the next pass                               at pass 1: "pass 1"
  a ban in an open lobby both share and the      the base's early reporter scrub -> 40P01 (the base
    deletion both finish                           circle; also run at 95b795ab): "outcomes"
  the purge holding the case row (its SET NULL)  SKIP LOCKED taken out -> 40P01: "outcomes"
    waits for the relay row the deletion removed;
    the deletion skips the case row
  the purge runs to its end while the deletion   the base's early reporter scrub -> the purge waits
    is parked at the base's scrub point            on the deletion; 40P01 when the purge had taken the
                                                   relay row first (the base circle)
Static and schema tests pin what the never-waits argument rests on: the case
table has no trigger of its own and no scrubbed column in a unique index;
the foreign keys into the three tables; the deletion names moderation_cases
in that one statement only and deletes no mail_messages row; the statement
is last; the janitor runs the pass on every pass and its statements EXPLAIN.
"""

import ast
import asyncio
import contextlib
import hashlib
import hmac
import inspect
import json
import os
import re
import sys
import uuid
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
SKIP_BOUND = 10                 # seconds: a deletion that skips a held case row commits inside this
LOCK_WAIT = 3                   # seconds: lock_timeout of the never-waits tests (LOCK_TIMEOUT_SQL)
SECRET = "mail-case-scrub-secret"
BODY = "An ordinary message."
# Deleted resolvers that have no players row: 17-digit ids on the deletion ledger only
RESOLVER_A, RESOLVER_B = "76561190040699901", "76561190040699902"
CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Statements as main.py hands them to AsyncSession.execute (the text() form): where a session parks.
# The deletion's last statement:
LAST = "SET reporter_id = CASE WHEN reporter_id = CAST(:pid AS uuid) THEN NULL"
# The deletion's statement right after the base's resolved_by scrub (and after the base's reporter scrub):
BULK_GRANT = "UPDATE mail_bulk_grants SET granted_by = :tomb WHERE granted_by = :sid"
# The deletion's first statement after its lobby locks (also the ban core's; a spot parks once):
STEAM_SESSIONS = "DELETE FROM steam_sessions WHERE steam_id = :sid"
# A send's fan-out (main._MAIL_FANOUT_SQL, its head) and relay-off's cancel (RELAY_OFF_CANCEL_SQL):
FANOUT = "INSERT INTO mail_recipients (message_id, recipient_id, kind, delivery) SELECT CAST("
CANCEL = "UPDATE pending_dms SET cancelled_at = NOW()"
# ...and as they reach PostgreSQL ($n binds): what a mutant rewrites.
LAST_PG = "SET reporter_id = CASE WHEN reporter_id = CAST("
SKIP = " FOR NO KEY UPDATE SKIP LOCKED)"
# The base's resolved_by scrub, put back where the base ran it: before the bulk-grant rewrite
EARLY_RESOLVER = (
    re.compile(r"^UPDATE mail_bulk_grants SET granted_by = (\$\d+) WHERE granted_by = (\$\d+)\s*$"),
    r"WITH early AS (UPDATE moderation_cases SET resolved_by = CAST(\1 AS varchar)"
    r" WHERE resolved_by = CAST(\2 AS varchar) RETURNING 1) "
    r"UPDATE mail_bulk_grants SET granted_by = \1 WHERE granted_by = \2")
# The base's separate early reporter scrub, put back two statements after its base place (the
# mail_blocks delete; the bulk-grant delete between them touches no case row)
EARLY_REPORTER = (
    re.compile(r"^DELETE FROM mail_censor_hits WHERE sender_id = (\$\d+)\s*$"),
    r"WITH early AS (UPDATE moderation_cases SET reporter_id = NULL"
    r" WHERE reporter_id = CAST(\1 AS uuid) RETURNING 1) "
    r"DELETE FROM mail_censor_hits WHERE sender_id = \1")
# Route P's order put back (8cd7fa8c): the send locks its spam case rows (both days' rows here) in the
# statement that writes its message row, before its fan-out. A data-modifying CTE runs unreferenced.
EARLY_SEND_LOCK = (
    re.compile(r"^INSERT INTO mail_messages(\s+\(id, sender_id, kind, thread_id, in_reply_to, subject, body,"
               r" idempotency_key, via\) VALUES \((\$\d+), (\$\d+), )"),
    r"WITH early AS (UPDATE moderation_cases SET resolved_by = resolved_by"
    r" WHERE kind = 'mail_spam' AND subject_player_id = CAST(\3 AS uuid) RETURNING 1) "
    r"INSERT INTO mail_messages\1")
# Heads of statements as pg_stat_activity shows them
PURGE_HEAD = "DELETE FROM mail_messages WHERE id IN ("
LOBBY_LOCK_HEAD = "SELECT 1 FROM team_lobbies WHERE id = "
# lock_timeout from a typed interval (make_interval), in this transaction only
LOCK_TIMEOUT_SQL = (
    "SELECT set_config('lock_timeout', CAST(CAST(EXTRACT(EPOCH FROM"
    " make_interval(secs => CAST(:s AS double precision))) * 1000 AS bigint) AS text), true)")
NEW_JANITOR_SQL = ("_CASE_SCRUB_REPORTER_SQL", "_CASE_SCRUB_RESOLVER_IDS_SQL", "_CASE_SCRUB_LEDGER_SQL",
                   "_CASE_SCRUB_RESOLVER_SQL")


# -- outcomes -----------------------------------------------------------------------------------

def _chain(x):
    seen = set()
    while isinstance(x, BaseException) and id(x) not in seen:
        seen.add(id(x))
        yield x
        x = getattr(x, "orig", None) or x.__cause__ or x.__context__


def _sqlstate(x):
    for e in _chain(x):
        s = getattr(e, "sqlstate", None) or getattr(e, "pgcode", None)
        if s:
            return s
    return None


def _deadlock(x):
    """True when `x` is an exception whose chain holds PostgreSQL's 40P01."""
    return _sqlstate(x) == "40P01" or any(type(e).__name__ == "DeadlockDetectedError" for e in _chain(x))


def _lock_timeout(x):
    """True when `x` is an exception whose chain holds 55P03 (lock_timeout)."""
    return _sqlstate(x) == "55P03" or any(type(e).__name__ == "LockNotAvailableError" for e in _chain(x))


def _name(x):
    if isinstance(x, BaseException):
        return "%s: %s" % (type(x).__name__, str(x)[:300])
    return repr(x)


def _bad(*xs):
    return any(isinstance(x, BaseException) for x in xs)


# -- schedules ----------------------------------------------------------------------------------

class _Spot:
    """Where a session parks: before or after the first statement whose text
    holds `mark` (once), holding every lock it has taken until released."""

    def __init__(self, mark, when):
        assert when in ("before", "after"), when
        self.mark, self.when = mark, when
        self.taken = False
        self.parked, self.release = asyncio.Event(), asyncio.Event()
        self.pid = None

    async def hold(self, db, execute):
        self.pid = (await execute(db, text("SELECT pg_backend_pid()"))).scalar()
        self.parked.set()
        await self.release.wait()


def _parks(env):
    """Patches AsyncSession.execute for the case; returns at(mark, when) -> _Spot."""
    spots = []
    execute = AsyncSession.execute

    async def observed(db, statement, params=None, *args, **kwargs):
        sql = str(statement)
        spot = next((s for s in spots if not s.taken and s.mark in sql), None)
        if spot is not None:
            spot.taken = True
            if spot.when == "before":
                await spot.hold(db, execute)
        out = await execute(db, statement, params, *args, **kwargs)
        if spot is not None and spot.when == "after":
            await spot.hold(db, execute)
        return out
    env.mp.setattr(AsyncSession, "execute", observed)

    def at(mark, when):
        s = _Spot(mark, when)
        spots.append(s)
        return s
    return at


def _timed(env, secs=LOCK_WAIT):
    """While flag["on"], every statement sent through AsyncSession.execute is
    preceded in its transaction by LOCK_TIMEOUT_SQL (so a rollback inside a
    handler cannot shed it)."""
    flag = {"on": False}
    execute = AsyncSession.execute

    async def timed(db, statement, params=None, *args, **kwargs):
        if flag["on"]:
            await execute(db, text(LOCK_TIMEOUT_SQL), {"s": secs})
        return await execute(db, statement, params, *args, **kwargs)
    env.mp.setattr(AsyncSession, "execute", timed)
    return flag


def _timed_factory(env, secs=LOCK_WAIT):
    """A session factory for _mail_case_scrub_pass whose every transaction
    starts with LOCK_TIMEOUT_SQL."""
    @contextlib.asynccontextmanager
    async def factory():
        async with env.sm() as db:
            await db.execute(text(LOCK_TIMEOUT_SQL), {"s": secs})
            yield db
    return factory


class _OneTransaction:
    """The mutant of _mail_case_scrub_pass's transaction boundary: both halves
    get this one session and its first commit is dropped, so the two halves
    share one transaction."""

    def __init__(self, db):
        self.db, self.commits = db, 0

    def __getattr__(self, k):
        return getattr(self.db, k)

    async def commit(self):
        self.commits += 1
        if self.commits > 1:
            await self.db.commit()


async def _until(what, cond, bound=BOUND):
    for _ in range(int(bound / POLL)):
        if cond():
            return
        await asyncio.sleep(POLL)
    raise AssertionError("not within %ss: %s" % (bound, what))


async def _parked(spot, task):
    await _until("parked at %r" % spot.mark[:60], lambda: spot.parked.is_set() or task.done())
    assert spot.parked.is_set(), ("did not park", spot.mark, _name(task.exception()) if task.done() else None)


async def _waiters(env):
    """Every backend of this database that waits on a lock: its pid, statement,
    the pids it waits for, and its transaction id."""
    return [dict(r) for r in await env.conn.fetch(
        "SELECT pid, query, pg_blocking_pids(pid) AS by, CAST(backend_xid AS text) AS xid"
        "  FROM pg_stat_activity"
        " WHERE datname = current_database() AND pid <> pg_backend_pid()"
        "   AND cardinality(pg_blocking_pids(pid)) > 0")]


async def _settle(env, task, *, head=None, by=None, bound=BOUND):
    """Polls until `task` is done ('done', None) or a backend whose statement
    starts with `head` and that waits on `by` waits ('waits', its row)."""
    for _ in range(int(bound / POLL)):
        if task.done():
            return "done", None
        for w in await _waiters(env):
            if (head is None or (w["query"] or "").startswith(head)) and (by is None or by in (w["by"] or [])):
                return "waits", w
        await asyncio.sleep(POLL)
    raise AssertionError(("neither done nor waiting", head, by, bound))


async def _finish(tasks, spots):
    """Releases every spot, then waits for the tasks: their outcomes in order
    (None for a task never started)."""
    for s in spots:
        s.release.set()
    live = [t for t in tasks if t is not None]
    got = iter(await asyncio.wait_for(asyncio.gather(*live, return_exceptions=True), BOUND))
    return [next(got) if t is not None else None for t in tasks]


async def _xmax(env, table, rid):
    """The transaction that holds or wrote the row (its visible version's xmax)."""
    return await env.conn.fetchval("SELECT CAST(xmax AS text) FROM %s WHERE id = $1" % table, rid)


@contextlib.asynccontextmanager
async def _held(env, sql, *args):
    """Another session holds rows (`sql`, a locking SELECT) until the block ends."""
    side = await env.side()
    tr = side.transaction()
    await tr.start()
    try:
        got = await side.fetch(sql, *args)
        assert got, ("the holder locked nothing", sql)
        yield side
    finally:
        await tr.rollback()


# -- seeds ----------------------------------------------------------------------------------------

def _arm(env):
    env.mp.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    env.mp.delenv("STEAM_WEB_API_KEY", raising=False)


async def _delete(env, p):
    """Account deletion for `p`, signed with the case's secret."""
    sig = hmac.new(SECRET.encode(), ("delete:%s" % p.sid).encode(), hashlib.sha256).hexdigest()
    return await env.call(lambda db: main.delete_player_data(p.sid, Req(p.sid), sig=sig, _slot=None,
                                                             db=db))


async def _case_row(env, subject, *, kind="mail_report", reporter=None, resolved_by=None, resolved_at=None,
                    message=None, bucket=None, status="open", evidence=None):
    return await env.conn.fetchval(
        "INSERT INTO moderation_cases (kind, subject_player_id, reporter_id, message_id, evidence,"
        "                              bucket_key, status, resolved_at, resolved_by)"
        " VALUES ($1, $2, $3, $4, CAST($5 AS jsonb), $6, $7, $8, $9) RETURNING id",
        kind, subject.id, reporter.id if reporter is not None else None, message,
        json.dumps(evidence or {"seeded": True}), bucket or "seed:%s" % uuid.uuid4(), status, resolved_at,
        resolved_by)


async def _row(env, cid):
    return dict(await env.conn.fetchrow(
        "SELECT reporter_id, resolved_by, message_id, status FROM moderation_cases WHERE id = $1", cid))


async def _left(env, p):
    """Rows that still name `p`'s account: its players.id as reporter, its raw id as resolver."""
    return await env.conn.fetchval(
        "SELECT COUNT(*) FROM moderation_cases WHERE reporter_id = $1 OR resolved_by = $2", p.id, p.sid)


async def _ledger(env, sid, deleted_at=None):
    """A deletion-ledger row for `sid`, hashed as the deletion hashes it."""
    await env.conn.execute(
        "INSERT INTO deleted_steam_ids (steam_id_hash, deleted_at)"
        " VALUES ($1, COALESCE(CAST($2 AS timestamptz), NOW()))", main._hash_steam_id(sid), deleted_at)


async def _old_mail(env, sender, to, body):
    """A message the retention purge takes: sent, then deleted by its sender,
    with no envelope left (deleted, as the retention's own expiry does), so
    no deletion of an addressee holds one of its envelopes."""
    ans = await env.mail(sender, to, body=body)
    assert ans.status == 200 and ans["accepted"] is True, ans
    mid = uuid.UUID(str(ans["id"]))
    await env.conn.execute("DELETE FROM mail_recipients WHERE message_id = $1", mid)
    await env.conn.execute("UPDATE mail_messages SET deleted_by_sender_at = NOW() WHERE id = $1", mid)
    return mid


async def _relay_row(env, to, sender, mid):
    """A queued relay DM to `to` of message `mid` (undelivered, not cancelled)."""
    n = uuid.uuid4().int
    code = "SCR-" + "".join(CROCKFORD[(n >> (5 * i)) & 31] for i in range(12))
    return await env.conn.fetchval(
        "INSERT INTO pending_dms (steam_id, content, mail_id, relay_code, sender_steam_id)"
        " VALUES ($1, $2, $3, $4, $5) RETURNING id", to.sid, "A relayed copy.", mid, code, sender.sid)


async def _spam_seed(env, message=None, resolver=None):
    """S and M; S's mail_spam case rows for today and tomorrow (UTC); a send
    from S crosses the same-body threshold (MAIL_SPAM_SAME_BODY 1), so it
    writes one of them. `resolver`: the rows were resolved by M."""
    s, m = await env.players(2)
    now = datetime.now(timezone.utc)
    rows = []
    for d in (0, 1):
        day = (now + timedelta(days=d)).strftime("%Y-%m-%d")
        rows.append(await _case_row(
            env, s, kind="mail_spam", bucket="%s:%s" % (s.id, day), message=message,
            status="resolved" if resolver else "open", resolved_at=now if resolver else None,
            resolved_by=m.sid if resolver else None, evidence={"hits": 1}))
    return s, m, rows


async def _spam_rows(env, s):
    return [dict(r) for r in await env.conn.fetch(
        "SELECT bucket_key, resolved_by, evidence->>'latest_message_id' AS latest"
        "  FROM moderation_cases WHERE kind = 'mail_spam' AND subject_player_id = $1"
        " ORDER BY bucket_key", s.id)]


async def _delete_trigger_order(env):
    """The tables mail_messages' foreign-key actions write, in the order
    PostgreSQL fires them for one deleted row (trigger name order)."""
    return [r["t"] for r in await env.conn.fetch(
        "SELECT CAST(CAST(k.conrelid AS regclass) AS text) AS t FROM pg_trigger g"
        "  JOIN pg_constraint k ON k.oid = g.tgconstraint"
        " WHERE g.tgrelid = to_regclass('mail_messages') AND g.tgisinternal AND k.contype = 'f'"
        "   AND k.confrelid = to_regclass('mail_messages') AND (g.tgtype & 8) = 8"
        " ORDER BY g.tgname")]


# -- 1. a send over a threshold against the deletion ---------------------------------------------

async def _send_vs_deletion(env, *, park, mutant=None):
    """M resolved S's spam case rows. The deletion of M parks at `park`
    ('base': right after the base's scrub point; 'last': before its last
    statement); then S's send to M runs until it finishes or waits on the
    deletion; then the deletion is released."""
    env.mp.setattr(main, "MAIL_SPAM_SAME_BODY", 1)
    s, m, _ = await _spam_seed(env, resolver=True)
    at = _parks(env)
    spot = at(BULK_GRANT, "after") if park == "base" else at(LAST, "before")
    mutants = {"scrub-before-flush": EARLY_RESOLVER, "case-lock-before-message": EARLY_SEND_LOCK}
    mut = env.rewriting(*mutants[mutant]) if mutant else contextlib.nullcontext([])
    o = {"s": s, "m": m, "state": None, "where": None}
    a = b = None
    with mut as hits:
        try:
            a = asyncio.ensure_future(_delete(env, m))
            await _parked(spot, a)
            b = asyncio.ensure_future(env.mail(s, [m], body=BODY))
            o["state"], w = await _settle(env, b, by=spot.pid)
            o["where"] = w["query"] if w else None
        finally:
            o["a"], o["b"] = await _finish([a, b], [spot])
    o["hits"] = list(hits)
    return o


def _check_send_finished(o):
    a, b = o["a"], o["b"]
    assert not _bad(a, b), ("outcomes", _name(a), _name(b))
    assert o["state"] == "done", ("the send waited on the parked deletion", o["where"])
    assert a.status == 200 and a["status"] == "anonymized", a
    assert b.status == 200 and b["accepted"] is True, b


def test_a_send_over_a_threshold_finishes_while_the_deletion_is_parked_at_the_base_scrub_point(monkeypatch):
    """At the base the deletion held S's case rows here (its resolved_by
    scrub had run) and the send waited at its case upsert after its fan-out:
    the cycle. Now the deletion holds no case row here; the send runs to its
    end; the deletion's last statement then scrubs the rows the send wrote."""
    async def body(env):
        _arm(env)
        o = await _send_vs_deletion(env, park="base")
        _check_send_finished(o)
        rows = await _spam_rows(env, o["s"])
        assert [r["resolved_by"] for r in rows] == [o["a"]["placeholder"]] * 2, rows
        assert [r["latest"] for r in rows].count(o["b"]["id"]) == 1, rows
        # the fan-out ran before the rewrite; the deletion's second sweep removed M's envelope
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM mail_recipients WHERE message_id = CAST($1 AS uuid)", o["b"]["id"]) == 0
    case(monkeypatch, body, prefix="mcs")


def test_control_the_scrub_put_back_before_the_flush_closes_the_send_cycle(monkeypatch):
    """The mutant: the resolved_by scrub runs where the base ran it, before
    the flush. The send waits at its case upsert on the parked deletion;
    released, the deletion's rewrite of M's row waits for the send's key
    share: one of the two ends with 40P01, and the green test's first
    assertion ("outcomes") is the one that fails."""
    async def body(env):
        _arm(env)
        o = await _send_vs_deletion(env, park="base", mutant="scrub-before-flush")
        assert len(o["hits"]) == 1, o["hits"]
        assert o["state"] == "waits" and "INSERT INTO moderation_cases" in (o["where"] or ""), o["where"]
        assert [_deadlock(o["a"]), _deadlock(o["b"])].count(True) == 1, (_name(o["a"]), _name(o["b"]))
        with pytest.raises(AssertionError, match="outcomes"):
            _check_send_finished(o)
    case(monkeypatch, body, prefix="mcs")


async def _check_other_order(env, o):
    a, b = o["a"], o["b"]
    assert not _bad(a, b), ("outcomes", _name(a), _name(b))
    assert o["state"] == "waits" and (o["where"] or "").startswith(FANOUT), o["where"]
    assert a.status == 200 and a["status"] == "anonymized", a
    assert b.status == 200 and b["accepted"] is True, b
    rows = await _spam_rows(env, o["s"])
    assert [r["resolved_by"] for r in rows] == [a["placeholder"]] * 2, ("scrub incomplete", rows)
    assert [r["latest"] for r in rows].count(b["id"]) == 1, rows
    assert await env.conn.fetchval(
        "SELECT COUNT(*) FROM mail_recipients WHERE message_id = CAST($1 AS uuid)", b["id"]) == 0


def test_a_send_waits_at_its_fan_out_for_the_deletions_rewrite_and_both_finish(monkeypatch):
    """The other order: the deletion parked before its last statement holds
    M's row FOR UPDATE (its rewrite has been flushed). The send waits at its
    fan-out, holding no case row; released, the last statement takes the
    free case rows, the deletion commits, and the send finishes. The control
    is the next test."""
    async def body(env):
        _arm(env)
        await _check_other_order(env, await _send_vs_deletion(env, park="last"))
    case(monkeypatch, body, prefix="mcs")


def test_control_a_case_lock_before_the_message_row_leaves_the_rows_to_the_sweep(monkeypatch):
    """The mutant: route P's order (8cd7fa8c) put back, the send locking its
    spam case rows in the statement that writes its message row
    (EARLY_SEND_LOCK). The send waits at its fan-out holding them; released,
    the deletion's last statement skips them and commits, so both rows keep
    M's id until a sweep pass: the green test's "scrub incomplete" assertion
    is the one that fails."""
    async def body(env):
        _arm(env)
        o = await _send_vs_deletion(env, park="last", mutant="case-lock-before-message")
        assert len(o["hits"]) == 1, o["hits"]
        assert [r["resolved_by"] for r in await _spam_rows(env, o["s"])] == [o["m"].sid] * 2
        with pytest.raises(AssertionError, match="scrub incomplete"):
            await _check_other_order(env, o)
    case(monkeypatch, body, prefix="mcs")


# -- 2. a send, a relay-off and the purge (mscl-r1's circle) --------------------------------------

def test_a_send_a_relay_off_and_the_purge_all_finish(monkeypatch):
    """Three sessions. S's spam case rows reference an old message Q; M has a
    queued relay DM of another old message O; the purge takes both messages.
    The send parks before its fan-out, relay-off (M's row FOR UPDATE) before
    its cancel; the purge runs; relay-off is released, then the send.

    At 8cd7fa8c the send took its case row before its fan-out: the purge took
    the relay row (O) and waited for the case row (Q) on the send, relay-off
    waited for the relay row on the purge, and the send's fan-out waited for
    M's row on relay-off: 40P01 (this test, run on that tree, is the
    control). Now the send takes its case row only after its fan-out: the
    purge runs to its end while the others are parked."""
    async def body(env):
        _arm(env)
        s, m = await env.players(2)
        o_mid = await _old_mail(env, s, [m], "An old message.")
        q_mid = await _old_mail(env, s, [m], "Another old message.")
        relay = await _relay_row(env, m, s, o_mid)
        env.mp.setattr(main, "MAIL_SPAM_SAME_BODY", 1)
        await _spam_seed_for(env, s, q_mid)
        at = _parks(env)
        send_spot, off_spot = at(FANOUT, "before"), at(CANCEL, "before")
        send = off = purge = None
        st = {"purge": None, "off": None, "held": None, "w": None}
        try:
            send = asyncio.ensure_future(env.mail(s, [m], body=BODY))
            await _parked(send_spot, send)
            off = asyncio.ensure_future(env.call(lambda db: main.mail_settings_put(
                main._MailSettingsReq(discord_relay=False), Req(m.sid), db=db)))
            await _parked(off_spot, off)
            purge = asyncio.ensure_future(env.retention())
            st["purge"], w = await _settle(env, purge, head=PURGE_HEAD)
            if w:
                st["w"] = w["query"][:120]
                st["held"] = (await _xmax(env, "pending_dms", relay)) == w["xid"]
            off_spot.release.set()
            st["off"], _ = await _settle(env, off, head=CANCEL)
        finally:
            outs = await _finish([send, off, purge], [send_spot, off_spot])
        print("MCS-THREE state %s" % st)
        assert not _bad(*outs), ("outcomes", [_name(x) for x in outs], st)
        assert st["purge"] == "done", ("the purge waited", st)
        assert st["off"] == "done", ("relay-off waited", st)
        sent, offd, _ = outs
        assert sent.status == 200 and sent["accepted"] is True, sent
        assert offd.status == 200 and offd["withdrawn"] == 1, offd
        r = await env.conn.fetchrow("SELECT mail_id, cancelled_at FROM pending_dms WHERE id = $1", relay)
        assert r["mail_id"] is None and r["cancelled_at"] is not None, dict(r)
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM mail_messages WHERE id = ANY($1::uuid[])", [o_mid, q_mid]) == 0
    case(monkeypatch, body, prefix="mcs")


async def _spam_seed_for(env, s, message):
    """S's spam case rows for today and tomorrow (UTC), open, referencing `message`."""
    now = datetime.now(timezone.utc)
    return [await _case_row(env, s, kind="mail_spam", bucket="%s:%s" % (s.id, (now + timedelta(days=d)).strftime(
        "%Y-%m-%d")), message=message, evidence={"hits": 1}) for d in (0, 1)]


# -- 3. the skip, and the battery case ------------------------------------------------------------

async def _skip(env, *, mutant=None):
    """D reported and resolved one case (held by another session through the
    deletion), reported a second and resolved a third. Delete D inside
    SKIP_BOUND; release the holder; run one sweep pass."""
    d, s = await env.players(2)
    now = datetime.now(timezone.utc)
    ids = {"held": await _case_row(env, s, reporter=d, resolved_by=d.sid, resolved_at=now, status="resolved"),
           "reported": await _case_row(env, s, reporter=d),
           "resolved": await _case_row(env, s, resolved_by=d.sid, resolved_at=now, status="resolved")}
    if mutant == "no-sweep":
        async def _none(session_factory):
            return {"armed": True, "checked": 0, "deleted": 0, "resolvers": 0, "reporters": 0}
        env.mp.setattr(main, "_mail_case_scrub_pass", _none)
    mut = (env.rewriting(SKIP, " FOR NO KEY UPDATE)", where=LAST_PG) if mutant == "no-skip-locked"
           else contextlib.nullcontext([]))
    o = {"d": d}
    loop = asyncio.get_running_loop()
    with mut as hits:
        async with _held(env, "SELECT 1 FROM moderation_cases WHERE id = $1 FOR NO KEY UPDATE", ids["held"]):
            a = asyncio.ensure_future(_delete(env, d))
            t0 = loop.time()
            for _ in range(int(SKIP_BOUND / POLL)):
                if a.done():
                    break
                await asyncio.sleep(POLL)
            o["in_bound"], o["took"] = a.done(), round(loop.time() - t0, 2)
            if a.done():
                o["after"] = {k: await _row(env, v) for k, v in ids.items()}
        try:
            o["a"] = await asyncio.wait_for(a, BOUND)
        except Exception as e:
            o["a"] = e
    o["hits"] = list(hits)
    o["sweep"] = await main._mail_case_scrub_pass(env.sm)
    o["swept"] = {k: await _row(env, v) for k, v in ids.items()}
    o["left"] = await _left(env, d)
    return o


def _check_skip(o):
    a, d = o["a"], o["d"]
    assert not _bad(a), ("outcome", _name(a))
    assert o["in_bound"], ("the deletion did not commit inside the bound", SKIP_BOUND, o["took"])
    assert a.status == 200 and a["status"] == "anonymized", a
    tomb = a["placeholder"]
    after = o["after"]
    # the held row keeps both links until the sweep; the rows not held were finished at once
    assert (after["held"]["reporter_id"], after["held"]["resolved_by"]) == (d.id, d.sid), after["held"]
    assert after["reported"]["reporter_id"] is None, after["reported"]
    assert after["resolved"]["resolved_by"] == tomb, after["resolved"]
    # completeness: after one sweep pass no case row names the deleted account
    assert o["left"] == 0, ("completeness", o["left"], o["swept"], o["sweep"])
    held = o["swept"]["held"]
    assert held["reporter_id"] is None and held["resolved_by"].startswith("deleted_"), held
    assert held["resolved_by"] not in (d.sid, tomb), held
    assert o["sweep"]["armed"] is True and (o["sweep"]["reporters"], o["sweep"]["resolvers"]) == (1, 1), o["sweep"]


def test_a_held_case_row_is_skipped_kept_and_finished_by_one_sweep_pass(monkeypatch):
    """The battery case of route B (conditions 4 and 6, B3): a case the
    deleted account both reported and resolved, held by another session at
    the deletion. The deletion commits inside the bound; both columns still
    stand after it commits; one sweep pass finishes both; then no case row
    names the deleted account. The rows not held are finished at once."""
    async def body(env):
        _arm(env)
        _check_skip(await _skip(env))
    case(monkeypatch, body, prefix="mcs")


def test_control_without_skip_locked_the_deletion_waits_past_the_bound(monkeypatch):
    async def body(env):
        _arm(env)
        o = await _skip(env, mutant="no-skip-locked")
        assert len(o["hits"]) == 1 and not o["in_bound"], (o["hits"], o["in_bound"])
        with pytest.raises(AssertionError, match="did not commit inside the bound"):
            _check_skip(o)
    case(monkeypatch, body, prefix="mcs")


def test_control_without_the_sweep_the_completeness_check_fails(monkeypatch):
    async def body(env):
        _arm(env)
        o = await _skip(env, mutant="no-sweep")
        assert o["left"] == 1, o["left"]
        with pytest.raises(AssertionError, match="completeness"):
            _check_skip(o)
    case(monkeypatch, body, prefix="mcs")


# -- 4. the last statement and the subject's players row ------------------------------------------

async def _subject_held(env, *, mutant=None):
    """D reported and resolved a case on S; S's players row is held FOR
    UPDATE by another session through D's deletion, every statement of which
    runs under a lock_timeout of LOCK_WAIT."""
    d, s = await env.players(2)
    cid = await _case_row(env, s, reporter=d, resolved_by=d.sid, resolved_at=datetime.now(timezone.utc),
                          status="resolved")
    flag = _timed(env)
    mut = env.rewriting(*EARLY_REPORTER) if mutant == "early-reporter-scrub" else contextlib.nullcontext([])
    with mut as hits:
        async with _held(env, "SELECT 1 FROM players WHERE id = $1 FOR UPDATE", s.id):
            flag["on"] = True
            try:
                a = await asyncio.wait_for(_delete(env, d), BOUND)
            except Exception as e:
                a = e
            finally:
                flag["on"] = False
    return {"a": a, "row": await _row(env, cid), "hits": list(hits), "d": d}


def _check_subject(o):
    a = o["a"]
    assert not _bad(a), ("outcome", _name(a))
    assert a.status == 200 and a["status"] == "anonymized", a
    assert (o["row"]["reporter_id"], o["row"]["resolved_by"]) == (None, a["placeholder"]), o["row"]


def test_the_last_statement_does_not_wait_on_the_subjects_players_row(monkeypatch):
    """B4: the last statement writes the row once in its transaction, so no
    foreign key of the row is re-checked and it takes no KEY SHARE on the
    subject's row another session holds FOR UPDATE."""
    async def body(env):
        _arm(env)
        _check_subject(await _subject_held(env))
    case(monkeypatch, body, prefix="mcs")


def test_control_the_early_reporter_scrub_trips_lock_timeout(monkeypatch):
    """The mutant: the base's separate early reporter scrub writes the row
    first; the last statement is then the row's second write in the
    transaction, which re-checks its foreign keys (ri_triggers.c,
    RI_FKey_fk_upd_check_required) and waits for KEY SHARE on the subject's
    row: lock_timeout (55P03)."""
    async def body(env):
        _arm(env)
        o = await _subject_held(env, mutant="early-reporter-scrub")
        assert len(o["hits"]) == 1, o["hits"]
        assert _lock_timeout(o["a"]), _name(o["a"])
        with pytest.raises(AssertionError, match="outcome"):
            _check_subject(o)
    case(monkeypatch, body, prefix="mcs")


# -- 5. the sweep ---------------------------------------------------------------------------------

async def _both_halves_seed(env):
    """A case reported by a deleted account R (players.deleted_at set) and
    resolved by a deleted account on the ledger only; its subject S."""
    r, s = await env.players(2)
    await env.conn.execute("UPDATE players SET deleted_at = NOW() WHERE id = $1", r.id)
    await _ledger(env, RESOLVER_A)
    cid = await _case_row(env, s, reporter=r, resolved_by=RESOLVER_A,
                          resolved_at=datetime.now(timezone.utc) - timedelta(minutes=1), status="resolved")
    return s, cid


async def _pass_over_held_subject(env, *, mutant=None):
    s, cid = await _both_halves_seed(env)
    async with _held(env, "SELECT 1 FROM players WHERE id = $1 FOR UPDATE", s.id):
        try:
            if mutant == "one-transaction":
                async with env.sm() as db:
                    await db.execute(text(LOCK_TIMEOUT_SQL), {"s": LOCK_WAIT})
                    shared = _OneTransaction(db)

                    @contextlib.asynccontextmanager
                    async def factory():
                        yield shared
                    res = await asyncio.wait_for(main._mail_case_scrub_pass(factory), BOUND)
            else:
                res = await asyncio.wait_for(main._mail_case_scrub_pass(_timed_factory(env)), BOUND)
        except Exception as e:
            res = e
    return {"res": res, "row": await _row(env, cid)}


def _check_pass(o):
    res = o["res"]
    assert not _bad(res), ("outcome", _name(res))
    assert (res["reporters"], res["resolvers"]) == (1, 1), res
    assert o["row"]["reporter_id"] is None and o["row"]["resolved_by"].startswith("deleted_"), o["row"]


def test_one_sweep_pass_over_a_row_both_halves_match_does_not_wait(monkeypatch):
    """B2 and B4: each half writes the row once in a transaction of its own,
    so neither re-checks the row's foreign keys and neither waits for the
    subject's row another session holds FOR UPDATE."""
    async def body(env):
        _arm(env)
        _check_pass(await _pass_over_held_subject(env))
    case(monkeypatch, body, prefix="mcs")


def test_control_one_transaction_for_both_halves_trips_lock_timeout(monkeypatch):
    async def body(env):
        _arm(env)
        o = await _pass_over_held_subject(env, mutant="one-transaction")
        assert _lock_timeout(o["res"]), _name(o["res"])
        with pytest.raises(AssertionError, match="outcome"):
            _check_pass(o)
    case(monkeypatch, body, prefix="mcs")


async def _pass_over_held_row(env, *, mutant=None):
    """The case row itself is held through pass 1, then released; pass 2."""
    s, cid = await _both_halves_seed(env)
    mut = (env.rewriting(" SKIP LOCKED)", ")", where="UPDATE moderation_cases SET ")
           if mutant == "no-skip-locked" else contextlib.nullcontext([]))
    o = {}
    with mut as hits:
        async with _held(env, "SELECT 1 FROM moderation_cases WHERE id = $1 FOR NO KEY UPDATE", cid):
            try:
                o["pass1"] = await asyncio.wait_for(main._mail_case_scrub_pass(_timed_factory(env)), BOUND)
            except Exception as e:
                o["pass1"] = e
            o["row1"] = await _row(env, cid)
    o["hits"] = list(hits)
    o["pass2"] = await main._mail_case_scrub_pass(env.sm)
    o["row2"] = await _row(env, cid)
    return o


def _check_refind(o):
    p1 = o["pass1"]
    assert not _bad(p1), ("pass 1", _name(p1))
    assert (p1["reporters"], p1["resolvers"]) == (0, 0), ("pass 1", p1)
    assert o["row1"]["reporter_id"] is not None and o["row1"]["resolved_by"] == RESOLVER_A, o["row1"]
    p2 = o["pass2"]
    assert (p2["reporters"], p2["resolvers"]) == (1, 1), ("pass 2", p2)
    assert o["row2"]["reporter_id"] is None and o["row2"]["resolved_by"].startswith("deleted_"), o["row2"]


def test_the_sweep_skips_a_held_row_and_finds_it_again_on_the_next_pass(monkeypatch):
    """Condition 2: by predicate and SKIP LOCKED. A pass skips the held row
    (it finishes nothing and waits for nothing); the next pass, by the same
    predicates and no list of skipped rows, finds it and finishes it."""
    async def body(env):
        _arm(env)
        _check_refind(await _pass_over_held_row(env))
    case(monkeypatch, body, prefix="mcs")


def test_control_a_sweep_without_skip_locked_waits_for_the_held_row(monkeypatch):
    async def body(env):
        _arm(env)
        o = await _pass_over_held_row(env, mutant="no-skip-locked")
        assert o["hits"] and _lock_timeout(o["pass1"]), (o["hits"], _name(o["pass1"]))
        with pytest.raises(AssertionError, match="pass 1"):
            _check_refind(o)
    case(monkeypatch, body, prefix="mcs")


def test_the_resolver_margin_is_one_hour_at_its_edge(monkeypatch):
    """Condition 2's time guard: resolved_at (the action's NOW(), its
    transaction start) at or before the ledger's deleted_at (the deleting
    transaction's NOW()) plus one hour. A second inside or at the edge is
    finished; a second past it is kept."""
    async def body(env):
        _arm(env)
        s = await env.player()
        t = datetime.now(timezone.utc) - timedelta(hours=3)
        await _ledger(env, RESOLVER_B, t)
        ids = {}
        for name, secs in (("inside", -1), ("edge", 0), ("outside", 1)):
            ids[name] = await env.conn.fetchval(
                "INSERT INTO moderation_cases (kind, subject_player_id, evidence, bucket_key, status,"
                "                              resolved_at, resolved_by)"
                " VALUES ('mail_report', $1, CAST($2 AS jsonb), $3, 'resolved',"
                "         CAST($4 AS timestamptz) + make_interval(hours => 1, secs => CAST($5 AS double precision)),"
                "         $6) RETURNING id",
                s.id, json.dumps({"seeded": True}), "seed:%s" % uuid.uuid4(), t, float(secs), RESOLVER_B)
        res = await main._mail_case_scrub_pass(env.sm)
        got = {k: (await _row(env, v))["resolved_by"] for k, v in ids.items()}
        assert res["resolvers"] == 2 and res["deleted"] == 1, res
        assert got["inside"].startswith("deleted_") and got["edge"].startswith("deleted_"), got
        assert got["outside"] == RESOLVER_B, got
    case(monkeypatch, body, prefix="mcs")


def test_without_the_secret_the_resolver_half_finishes_nothing_and_says_so(monkeypatch, capsys):
    """Condition 2's secret: with MATCH_HMAC_SECRET unset no ledger hash can
    be made; the pass finishes no resolver row, keeps it, and its log says
    so. With the secret set the same row is finished and the log's armed
    line counts it."""
    async def body(env):
        _arm(env)
        s = await env.player()
        await _ledger(env, RESOLVER_A)
        cid = await _case_row(env, s, resolved_by=RESOLVER_A,
                              resolved_at=datetime.now(timezone.utc) - timedelta(minutes=1), status="resolved")
        env.mp.setitem(main._CASE_SCRUB_STATE, "next", 0.0)
        env.mp.setattr(main, "MATCH_HMAC_SECRET", "")
        capsys.readouterr()
        res1 = await main._mail_case_scrub_pass(env.sm)
        main._mail_case_scrub_log(res1, now=1000.0)
        out1, row1 = capsys.readouterr().out, await _row(env, cid)
        env.mp.setattr(main, "MATCH_HMAC_SECRET", SECRET)
        env.mp.setitem(main._CASE_SCRUB_STATE, "next", 0.0)
        res2 = await main._mail_case_scrub_pass(env.sm)
        main._mail_case_scrub_log(res2, now=2000.0)
        out2, row2 = capsys.readouterr().out, await _row(env, cid)
        assert res1 == {"armed": False, "checked": 0, "deleted": 0, "resolvers": 0, "reporters": 0}, res1
        assert row1["resolved_by"] == RESOLVER_A, row1
        assert ("[MAIL-CASE-SCRUB] MATCH_HMAC_SECRET is not set: the resolver half finishes nothing;"
                " reporter row(s) finished 0") in out1, out1
        assert (res2["armed"], res2["checked"], res2["deleted"], res2["resolvers"]) == (True, 1, 1, 1), res2
        assert row2["resolved_by"].startswith("deleted_"), row2
        assert ("[MAIL-CASE-SCRUB] armed: 1 resolver id(s) checked, 1 on the deletion ledger;"
                " finished 1 resolver row(s) and 0 reporter row(s)") in out2, out2
    case(monkeypatch, body, prefix="mcs")


def test_the_pass_log_prints_at_boot_hourly_and_on_any_finished_row(monkeypatch, capsys):
    """Lessons 438 and 443: a line that shows the pass runs. The first pass
    prints; a quiet pass inside the hour does not; a pass that finished a row
    does; an hour on, a quiet pass prints again."""
    monkeypatch.setitem(main._CASE_SCRUB_STATE, "next", 0.0)
    quiet = {"armed": True, "checked": 3, "deleted": 0, "resolvers": 0, "reporters": 0}
    capsys.readouterr()
    main._mail_case_scrub_log(quiet, now=100.0)
    main._mail_case_scrub_log(quiet, now=200.0)
    main._mail_case_scrub_log(dict(quiet, reporters=1), now=300.0)
    main._mail_case_scrub_log(quiet, now=3700.0)
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("[MAIL-CASE-SCRUB]")]
    head = "[MAIL-CASE-SCRUB] armed: 3 resolver id(s) checked, 0 on the deletion ledger; finished 0 resolver row(s)"
    assert lines == [head + " and 0 reporter row(s)", head + " and 1 reporter row(s)",
                     head + " and 0 reporter row(s)"], lines


# -- 6. the two base circles (B5) -----------------------------------------------------------------

async def _ban(db, cid, actor):
    out = await main._moderation_case_act(db, case_id=str(cid), actor_steam_id=actor.sid, action="ban",
                                          hours=None, reason="A live test.", via="test")
    await db.commit()
    return out


async def _lobby_ban(env, *, mutant=None):
    """D (a joiner) and B (the host) sit in one open team lobby; D reported B
    (case C, open); admin X bans B through C. D's deletion parks after its
    lobby locks; X's ban runs until it waits; then the deletion is released."""
    lid, (b, d) = await env.lobby("team", n=2)
    x = await env.player()
    await env.conn.execute("INSERT INTO admin_users (steam_id) VALUES ($1)", x.sid)
    seats = await env.conn.fetch(
        "SELECT player_id, series_id FROM team_queue WHERE status = 'lobby' AND player_id = ANY($1::uuid[])",
        [b.id, d.id])
    assert sorted((r["player_id"], r["series_id"]) for r in seats) == sorted([(b.id, lid), (d.id, lid)]), seats
    cid = await _case_row(env, b, reporter=d)
    at = _parks(env)
    spot = at(STEAM_SESSIONS, "before")
    mut = env.rewriting(*EARLY_REPORTER) if mutant == "early-reporter-scrub" else contextlib.nullcontext([])
    o = {"d": d, "x": x, "cid": cid, "state": None, "where": None}
    a = t = None
    with mut as hits:
        try:
            a = asyncio.ensure_future(_delete(env, d))
            await _parked(spot, a)
            t = asyncio.ensure_future(env.call(lambda db: _ban(db, cid, x)))
            o["state"], w = await _settle(env, t, by=spot.pid)
            o["where"] = w["query"] if w else None
        finally:
            o["a"], o["ban"] = await _finish([a, t], [spot])
    o["hits"] = list(hits)
    return o


def _check_lobby(o):
    a, x = o["a"], o["ban"]
    assert not _bad(a, x), ("outcomes", _name(a), _name(x))
    assert a.status == 200 and a["status"] == "anonymized", a
    assert x.status == 200 and x["status"] == "ok" and x["resolution"] == "ban", x


def test_a_ban_in_an_open_lobby_both_share_and_the_deletion_both_finish(monkeypatch):
    """Base circle 1, closed by a staged schedule of two sessions. The ban
    holds C (FOR NO KEY UPDATE OF c) and waits for the lobby row the parked
    deletion locked. At the base the deletion's early reporter scrub then
    waited for C: 40P01. Now the deletion's only case write is its last
    statement, which skips C: it commits, and the ban follows. C keeps D as
    reporter until one sweep pass."""
    async def body(env):
        _arm(env)
        o = await _lobby_ban(env)
        assert o["state"] == "waits" and (o["where"] or "").startswith(LOBBY_LOCK_HEAD), o["where"]
        _check_lobby(o)
        row = await _row(env, o["cid"])
        assert (row["reporter_id"], row["status"], row["resolved_by"]) == (o["d"].id, "resolved", o["x"].sid), row
        res = await main._mail_case_scrub_pass(env.sm)
        assert res["reporters"] == 1 and (await _row(env, o["cid"]))["reporter_id"] is None, res
    case(monkeypatch, body, prefix="mcs")


def test_control_the_early_reporter_scrub_closes_the_lobby_circle(monkeypatch):
    """The mutant puts the base's early reporter scrub back: the deletion,
    released, waits for C on the ban while the ban waits for the lobby row
    on the deletion: one of the two ends with 40P01 ("outcomes")."""
    async def body(env):
        _arm(env)
        o = await _lobby_ban(env, mutant="early-reporter-scrub")
        assert len(o["hits"]) == 1, o["hits"]
        assert o["state"] == "waits" and (o["where"] or "").startswith(LOBBY_LOCK_HEAD), o["where"]
        assert [_deadlock(o["a"]), _deadlock(o["ban"])].count(True) == 1, (_name(o["a"]), _name(o["ban"]))
        with pytest.raises(AssertionError, match="outcomes"):
            _check_lobby(o)
    case(monkeypatch, body, prefix="mcs")


async def _purge_seed(env, *, two):
    """Y mailed D; D reported a message (case C) and has a queued relay DM
    (R) of a message; the purge takes both messages. `two`: R's message O
    and C's message Q differ; else both are one message X."""
    y, d = await env.players(2)
    first = await _old_mail(env, y, [d], "An old message.")
    second = await _old_mail(env, y, [d], "Another old message.") if two else first
    relay = await _relay_row(env, d, y, first)
    cid = await _case_row(env, y, reporter=d, message=second)
    return d, relay, cid


async def _purge_vs_deletion(env, *, park, two, mutant=None):
    d, relay, cid = await _purge_seed(env, two=two)
    at = _parks(env)
    spot = at(LAST, "before") if park == "last" else at(BULK_GRANT, "after")
    if mutant == "no-skip-locked":
        mut = env.rewriting(SKIP, " FOR NO KEY UPDATE)", where=LAST_PG)
    elif mutant == "early-reporter-scrub":
        mut = env.rewriting(*EARLY_REPORTER)
    else:
        mut = contextlib.nullcontext([])
    o = {"d": d, "cid": cid, "relay": relay, "state": None, "where": None, "held_case": None, "held_relay": None}
    a = p = None
    with mut as hits:
        try:
            a = asyncio.ensure_future(_delete(env, d))
            await _parked(spot, a)
            p = asyncio.ensure_future(env.retention())
            o["state"], w = await _settle(env, p, by=spot.pid)
            if w:
                o["where"] = w["query"]
                o["held_case"] = (await _xmax(env, "moderation_cases", cid)) == w["xid"]
                o["held_relay"] = (await _xmax(env, "pending_dms", relay)) == w["xid"]
        finally:
            o["a"], o["p"] = await _finish([a, p], [spot])
    o["hits"] = list(hits)
    return o


def _check_purge(o):
    a, p = o["a"], o["p"]
    assert not _bad(a, p), ("outcomes", _name(a), _name(p), o["held_case"], o["held_relay"])
    assert a.status == 200 and a["status"] == "anonymized", a


def test_the_purge_holding_the_case_row_does_not_stop_the_deletion(monkeypatch):
    """One message X carries both C and R. The deletion parks before its last
    statement, R already deleted by it. The purge's delete of X fires
    moderation_cases' SET NULL before pending_dms' (trigger name order,
    checked here): it takes C, then waits for R on the deletion. Released, the
    last statement skips C and the deletion commits; the purge follows. C
    keeps D as reporter until one sweep pass."""
    async def body(env):
        _arm(env)
        order = await _delete_trigger_order(env)
        assert order.index("moderation_cases") < order.index("pending_dms"), ("trigger order", order)
        o = await _purge_vs_deletion(env, park="last", two=False)
        assert o["state"] == "waits" and o["held_case"], ("the purge did not hold C while it waited", o)
        _check_purge(o)
        row = await _row(env, o["cid"])
        assert (row["reporter_id"], row["message_id"]) == (o["d"].id, None), row
        assert await env.conn.fetchval("SELECT COUNT(*) FROM pending_dms WHERE id = $1", o["relay"]) == 0
        res = await main._mail_case_scrub_pass(env.sm)
        assert res["reporters"] == 1 and (await _row(env, o["cid"]))["reporter_id"] is None, res
    case(monkeypatch, body, prefix="mcs")


def test_control_without_skip_locked_the_purge_circle_closes(monkeypatch):
    """The mutant takes SKIP LOCKED out of the last statement: it waits for C
    on the purge while the purge waits for R on the deletion: 40P01."""
    async def body(env):
        _arm(env)
        o = await _purge_vs_deletion(env, park="last", two=False, mutant="no-skip-locked")
        assert len(o["hits"]) == 1, o["hits"]
        assert o["state"] == "waits" and o["held_case"], o
        assert [_deadlock(o["a"]), _deadlock(o["p"])].count(True) == 1, (_name(o["a"]), _name(o["p"]))
        with pytest.raises(AssertionError, match="outcomes"):
            _check_purge(o)
    case(monkeypatch, body, prefix="mcs")


def test_the_purge_runs_to_its_end_while_the_deletion_is_parked_at_the_base_scrub_point(monkeypatch):
    """Base circle 2. R and C on two messages O and Q. At the base the
    deletion held C here (its early reporter scrub had run); a purge that
    took R first then waited for C, and the deletion's relay erase then
    waited for R: 40P01, whenever the purge's one statement reached O before
    Q (it keeps no set order). Now the deletion holds no case row here, and
    the seed leaves the purge no other row of D's to wait for (_old_mail
    leaves no envelope): the purge runs to its end, whichever message it
    reaches first. A seed with such rows is the open item MDPL."""
    async def body(env):
        _arm(env)
        o = await _purge_vs_deletion(env, park="base", two=True)
        _check_purge(o)
        assert o["state"] == "done", ("the purge waited on the deletion parked at the base's scrub point", o)
        row = await _row(env, o["cid"])
        assert (row["reporter_id"], row["message_id"]) == (None, None), row
        assert await env.conn.fetchval("SELECT COUNT(*) FROM pending_dms WHERE id = $1", o["relay"]) == 0
    case(monkeypatch, body, prefix="mcs")


def test_control_the_early_reporter_scrub_makes_the_purge_wait(monkeypatch):
    """The mutant puts the base's early reporter scrub back: the parked
    deletion holds C, and the purge waits for it there. Released, the two
    end in 40P01 exactly when the purge had taken R before it reached C."""
    async def body(env):
        _arm(env)
        o = await _purge_vs_deletion(env, park="base", two=True, mutant="early-reporter-scrub")
        print("MCS-PURGE-BASE held_relay=%s held_case=%s where=%s" % (o["held_relay"], o["held_case"],
                                                                      (o["where"] or "")[:60]))
        assert len(o["hits"]) == 1, o["hits"]
        assert o["state"] == "waits" and (o["where"] or "").startswith(PURGE_HEAD), o
        if o["held_relay"]:
            assert [_deadlock(o["a"]), _deadlock(o["p"])].count(True) == 1, (_name(o["a"]), _name(o["p"]))
            with pytest.raises(AssertionError, match="outcomes"):
                _check_purge(o)
        else:
            assert not _bad(o["a"], o["p"]), (_name(o["a"]), _name(o["p"]))
    case(monkeypatch, body, prefix="mcs")


# -- 7. what the never-waits argument rests on ----------------------------------------------------

def test_the_case_table_has_no_trigger_no_unique_scrubbed_column_and_the_known_foreign_keys(monkeypatch):
    """Condition 1 and B1: no trigger of the table's own; neither scrubbed
    column in a unique index or an exclusion constraint; and every foreign
    key into moderation_cases, mail_messages and pending_dms, and out of
    moderation_cases, with its actions (a new one changes the protocol
    table, ORDER-V2)."""
    async def body(env):
        own = await env.conn.fetch(
            "SELECT tgname FROM pg_trigger WHERE tgrelid = to_regclass('moderation_cases') AND NOT tgisinternal")
        assert [r["tgname"] for r in own] == [], own
        # the same query finds migration 415's trigger of mail_messages' own, so the check above can fail
        assert await env.conn.fetch(
            "SELECT tgname FROM pg_trigger WHERE tgrelid = to_regclass('mail_messages') AND NOT tgisinternal")
        uniq = await env.conn.fetch(
            "SELECT DISTINCT a.attname FROM pg_index i"
            "  JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)"
            " WHERE i.indrelid = to_regclass('moderation_cases') AND i.indisunique")
        assert sorted(r["attname"] for r in uniq) == ["bucket_key", "id", "kind"], uniq
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM pg_constraint WHERE conrelid = to_regclass('moderation_cases')"
            "   AND contype = 'x'") == 0
        fks = await env.conn.fetch(
            "SELECT CAST(CAST(c.conrelid AS regclass) AS text) AS t,"
            "       (SELECT string_agg(attname, ',' ORDER BY attnum) FROM pg_attribute"
            "         WHERE attrelid = c.conrelid AND attnum = ANY(c.conkey)) AS cols,"
            "       CAST(CAST(c.confrelid AS regclass) AS text) AS ref,"
            "       CAST(c.confdeltype AS text) AS del, CAST(c.confupdtype AS text) AS upd"
            "  FROM pg_constraint c"
            " WHERE c.contype = 'f'"
            "   AND (c.conrelid = to_regclass('moderation_cases')"
            "        OR c.confrelid IN (to_regclass('moderation_cases'), to_regclass('mail_messages'),"
            "                           to_regclass('pending_dms')))")
        got = sorted((r["t"], r["cols"], r["ref"], r["del"], r["upd"]) for r in fks)
        assert got == sorted([
            ("lobby_invites", "mail_message_id", "mail_messages", "n", "a"),
            ("mail_recipients", "message_id", "mail_messages", "c", "a"),
            ("moderation_cases", "message_id", "mail_messages", "n", "a"),
            ("moderation_cases", "reporter_id", "players", "a", "a"),
            ("moderation_cases", "subject_player_id", "players", "a", "a"),
            ("pending_dms", "mail_id", "mail_messages", "n", "a"),
        ]), got
    case(monkeypatch, body, prefix="mcs")


def _sources():
    import tournaments
    out = {}
    for name, path in (("main", main.__file__), ("tournaments", tournaments.__file__)):
        with open(path, encoding="utf-8") as fh:
            out[name] = fh.read()
    return out


# Anchors for the source mutants of the static checks below; _mutate asserts each occurs exactly once.
CENSOR_LINE = '    await db.execute(text("DELETE FROM mail_censor_hits WHERE sender_id = :pid"), {"pid": pid})\n'
INBOX_LINE = '    await db.execute(text("DELETE FROM mail_inbox_rev WHERE recipient_id = :pid"), {"pid": pid})\n'
SCRUB_LINE = '    await db.execute(text(_DELETE_CASE_SCRUB_SQL), {"pid": pid, "sid": steam_id, "tomb": _tomb})\n'
ARM_BLOCK = ('        try:\n'
             '            _mail_case_scrub_log(await _mail_case_scrub_pass(async_session))\n'
             '        except Exception as e:\n'
             '            print(f"[MAIL-CASE-SCRUB] sweep error: {e}")\n')


def _mutate(src, old, new):
    assert src.count(old) == 1, ("mutant anchor", src.count(old), old[:70])
    return src.replace(old, new, 1)


def _b1_check(sources):
    """B1 from the call graph (main._janitor_sql_from_sources, rooted at
    delete_player_data) over `sources`: one reachable statement names
    moderation_cases, the last one; none deletes a mail_messages row (whose
    ON DELETE SET NULL would write a case row) or a players row; no dynamic
    statement names either table. Each assertion names its part."""
    inv = main._janitor_sql_from_sources(sources, (("main", "delete_player_data"),))
    stmts = inv["statements"]
    assert len(stmts) > 40, ("reachable", len(stmts))
    named = [s["sql"] for s in stmts if re.search(r"\bmoderation_cases\b", s["sql"])]
    assert named == [main._DELETE_CASE_SCRUB_SQL], ("named", named)
    deletes = [s["sql"] for s in stmts if re.search(r"\bDELETE\s+FROM\s+(mail_messages|players)\b", s["sql"], re.I)]
    assert deletes == [], ("deletes", deletes)
    lines = {name: src.splitlines() for name, src in sources.items()}
    for dyn in inv["dynamic"]:
        window = "\n".join(lines[dyn["module"]][dyn["line"] - 1:dyn["line"] + 4])
        assert "moderation_cases" not in window and "mail_messages" not in window, ("dynamic", dyn, window)


def test_the_deletion_writes_a_case_row_only_in_its_last_statement():
    """B1 (_b1_check) on main.py as it stands; the handler deletes no ORM object."""
    _b1_check(_sources())
    assert "db.delete(" not in inspect.getsource(main.delete_player_data)


def test_control_the_b1_check_fails_on_an_early_case_write_and_on_a_message_delete():
    """_b1_check over two mutants of main.py's text: the base's early reporter
    scrub put back after the censor-hit delete fails on "named"; a delete of
    the account's sent messages in the same place fails on "deletes"."""
    sources = _sources()
    early = dict(sources, main=_mutate(sources["main"], CENSOR_LINE, CENSOR_LINE + (
        '    await db.execute(text("UPDATE moderation_cases SET reporter_id = NULL WHERE reporter_id = :pid"),'
        ' {"pid": pid})\n')))
    with pytest.raises(AssertionError, match="'named'"):
        _b1_check(early)
    sent = dict(sources, main=_mutate(sources["main"], CENSOR_LINE, CENSOR_LINE + (
        '    await db.execute(text("DELETE FROM mail_messages WHERE sender_id = :pid"), {"pid": pid})\n')))
    with pytest.raises(AssertionError, match="'deletes'"):
        _b1_check(sent)


def _last_check(fn_src):
    """Condition 1 over a handler's source: the scrub is awaited once, and
    nothing is awaited after it but the commit."""
    fn = ast.parse(fn_src).body[0]
    awaits = sorted((n.lineno, n.col_offset, ast.unparse(n.value)) for n in ast.walk(fn)
                    if isinstance(n, ast.Await))
    at = [i for i, a in enumerate(awaits) if "text(_DELETE_CASE_SCRUB_SQL)" in a[2]]
    assert len(at) == 1, ("scrub awaits", awaits)
    assert [a[2] for a in awaits[at[0] + 1:]] == ["db.commit()"], ("after the scrub", awaits[at[0]:])


def _loop_check(loop_src):
    """Condition 2 over queue_cleanup_loop's source: its one while loop calls
    _mail_case_scrub_pass(async_session) in a try of its own, whose handler
    prints the sweep error."""
    loop = ast.parse(loop_src).body[0]
    whiles = [n for n in ast.walk(loop) if isinstance(n, ast.While)]
    assert len(whiles) == 1, ("loops", len(whiles))
    tries = [t for t in ast.walk(whiles[0]) if isinstance(t, ast.Try)
             and any(isinstance(c, ast.Call) and ast.unparse(c.func) == "_mail_case_scrub_pass"
                     for s in t.body for c in ast.walk(s))]
    assert len(tries) == 1, ("tries", len(tries))
    (call,) = [c for s in tries[0].body for c in ast.walk(s)
               if isinstance(c, ast.Call) and ast.unparse(c.func) == "_mail_case_scrub_pass"]
    assert [ast.unparse(x) for x in call.args] == ["async_session"], ("args", ast.unparse(call))
    assert "[MAIL-CASE-SCRUB] sweep error" in ast.unparse(tries[0].handlers[0]), (
        "handler", ast.unparse(tries[0].handlers[0]))


def test_the_scrub_is_last_and_the_janitor_runs_the_pass_on_every_pass():
    """Condition 1 (_last_check) and condition 2 (_loop_check) on main.py as
    it stands, and the pass's four statements are in the boot inventory
    under queue_cleanup_loop, each one EXPLAIN takes."""
    _last_check(inspect.getsource(main.delete_player_data))
    _loop_check(inspect.getsource(main.queue_cleanup_loop))
    inv = main._janitor_sql_inventory()
    by_sql = {s["sql"]: s for s in inv["statements"]}
    for const in NEW_JANITOR_SQL:
        s = by_sql.get(getattr(main, const))
        assert s is not None and "queue_cleanup_loop" in s["roots"] and s["class"] == "explain", (const, s)


def test_control_the_last_and_loop_checks_fail_on_their_mutants():
    """The inbox revision delete moved after the scrub fails _last_check on
    "after the scrub"; the pass called bare in the loop, without a try of its
    own, fails _loop_check on "tries"."""
    handler = inspect.getsource(main.delete_player_data)
    moved = _mutate(_mutate(handler, INBOX_LINE, ""), SCRUB_LINE, SCRUB_LINE + INBOX_LINE)
    with pytest.raises(AssertionError, match="'after the scrub'"):
        _last_check(moved)
    loop = inspect.getsource(main.queue_cleanup_loop)
    bare = _mutate(loop, ARM_BLOCK, "        _mail_case_scrub_log(await _mail_case_scrub_pass(async_session))\n")
    with pytest.raises(AssertionError, match="'tries'"):
        _loop_check(bare)


def test_the_pass_statements_pass_the_boot_explain(monkeypatch):
    """The boot self-test's own check (main._janitor_check_statement: EXPLAIN,
    every bind NULL) on each of the pass's statements, in a case schema; and
    the same check on one of them with its table name misspelt answers
    'failed', so the check can fail."""
    async def body(env):
        inv = main._janitor_sql_inventory()
        want = sorted(getattr(main, c) for c in NEW_JANITOR_SQL)
        picked = [s for s in inv["statements"] if s["sql"] in want]
        assert sorted(s["sql"] for s in picked) == want, [s["sql"][:60] for s in picked]
        for s in picked:
            async with env.sm() as db:
                verdict, detail = await main._janitor_check_statement(db, s)
            assert verdict == "explained", (s["sql"][:80], verdict, detail)
        src = next(s for s in picked if "moderation_cases" in s["sql"])
        bad = dict(src, sql=src["sql"].replace("moderation_cases", "moderation_cases_absent", 1))
        async with env.sm() as db:
            verdict, detail = await main._janitor_check_statement(db, bad)
        assert verdict == "failed", (verdict, detail)
    case(monkeypatch, body, prefix="mcs")
