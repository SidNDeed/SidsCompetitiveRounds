"""CHEAT-ALT-1 step 5: the retention pass of ruling R4, against a real
PostgreSQL.

  * A row is due one day before its published deadline: DUE_DAYS after its
    own last sight (last_at for a marker row, last_seen_at for a share row
    and for the facts row). One pass takes every due row of every table, in
    batches of PASS_BATCH rows, each batch its own short transaction under
    the pass's own time limits, and leaves every row that is not due.
  * A due row another transaction holds is skipped (SKIP LOCKED), counted in
    the pass's "due rows left" line, and taken by the next pass.
  * Pass first or sign-in first on one row: each side ends inside its own
    limits (the recording's lock limit; the pass never waits on a row).
  * The loop: an armed line, the first pass a minute after start, an hour
    between passes, a failing pass counted and said, the loop started on the
    primary only, and its statements in the janitor self-test's inventory.

One case schema for the module, built by the ladder harness's procedure
(test_title_ladder_hooks_live._build) with one fault table and BEFORE
INSERT/UPDATE/DELETE fault triggers on the three tables (a row (table, op,
what) makes that operation on a row of that table raise SQLSTATE `what`, or
sleep when `what` is 'sleep:<seconds>'), sealed, and dropped at the end:

    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    LADDER_TEST_PG_OPTOUT=1   waives the live cases deliberately (else they FAIL)

Ids are synthetic (below the first individual-account SteamID64).
"""
import ast
import asyncio
import inspect
import itertools
import os
import re
import sys
import textwrap
import time

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

import alt_signals as A  # noqa: E402
import main  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402
import test_alt_signals_record_pg as rec  # noqa: E402

TABLES = {"markers": "conn_markers", "shares": "steam_family_shares", "facts": "steam_signin_facts"}
LAST = {"markers": "last_at", "shares": "last_seen_at", "facts": "last_seen_at"}
_IDS = itertools.count(1)
PASS_LINE = re.compile(r"^\[ALT-RETENTION\] pass: deleted markers (\d+), shares (\d+), facts (\d+)"
                       r" in (\d+) batch\(es\)$")

_FAULTS_DDL = """
CREATE TABLE alt_test_faults (tbl text NOT NULL, op text NOT NULL, what text NOT NULL,
                              PRIMARY KEY (tbl, op));
CREATE FUNCTION alt_test_fault() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE w text;
BEGIN
  SELECT f.what INTO w FROM alt_test_faults f WHERE f.tbl = TG_TABLE_NAME AND f.op = TG_OP;
  IF w LIKE 'sleep:%' THEN
    PERFORM pg_sleep(CAST(substr(w, 7) AS double precision));
  ELSIF w IS NOT NULL THEN
    RAISE EXCEPTION 'planted fault on %', TG_TABLE_NAME USING ERRCODE = w;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END $f$;
CREATE TRIGGER alt_test_fault BEFORE INSERT OR UPDATE OR DELETE ON steam_signin_facts
  FOR EACH ROW EXECUTE FUNCTION alt_test_fault();
CREATE TRIGGER alt_test_fault BEFORE INSERT OR UPDATE OR DELETE ON steam_family_shares
  FOR EACH ROW EXECUTE FUNCTION alt_test_fault();
CREATE TRIGGER alt_test_fault BEFORE INSERT OR UPDATE OR DELETE ON conn_markers
  FOR EACH ROW EXECUTE FUNCTION alt_test_fault();
"""

# The last sight of a planted row: DUE_DAYS before now, less `secs` seconds
# (secs > 0: past due; secs < 0: short of due). Its first sight is earlier
# (ten days for a share or facts row, an hour for a marker row), so a pass
# that aged rows by their first sight would take the row short of due.
_AT = ("now() - make_interval(days => CAST(:d AS integer))"
       " - make_interval(secs => CAST(:x AS double precision))")
_PLANT = {
    "facts": ("INSERT INTO steam_signin_facts (steam_id, first_seen_at, last_seen_at)"
              " SELECT CAST(:s AS text) || lpad(CAST(g AS text), 4, '0'), z.t - interval '10 days', z.t"
              " FROM generate_series(1, CAST(:n AS integer)) g, (SELECT %s AS t) z" % _AT),
    "shares": ("INSERT INTO steam_family_shares (steam_id, key_id, owner_mark, first_seen_at, last_seen_at)"
               " SELECT CAST(:s AS text), 'aaaaaaaaaaaa', sha256(convert_to(CAST(:s AS text) || '-o-' || g, 'UTF8')),"
               " z.t - interval '10 days', z.t"
               " FROM generate_series(1, CAST(:n AS integer)) g, (SELECT %s AS t) z" % _AT),
    "markers": ("INSERT INTO conn_markers (steam_id, day, key_id, addr_mark, block_mark, family, conn_class,"
                " first_at, last_at)"
                " SELECT CAST(:s AS text), CAST((z.t AT TIME ZONE 'UTC') AS date), 'aaaaaaaaaaaa',"
                " sha256(convert_to(CAST(:s AS text) || '-a-' || g, 'UTF8')), sha256(convert_to(CAST(:s AS text) || '-b', 'UTF8')),"
                " 4, 'none', z.t - interval '1 hour', z.t"
                " FROM generate_series(1, CAST(:n AS integer)) g, (SELECT %s AS t) z" % _AT),
}


def _sid():
    """A fresh synthetic 13-digit prefix; the facts plant appends four digits
    (a 17-digit id below 76561197960265728); the other tables use it as is."""
    return "7656119042%03d" % next(_IDS)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def case():
    lh._require_live_pg()
    built = {}

    async def extra(conn, schema):
        await conn.execute(_FAULTS_DDL)

    async def build():
        c = harness.CaseSchema(lh.DSN, "alt_retention")
        await c.__aenter__()
        try:
            await lh._build(c, extra)
            await c.conn.execute(
                "INSERT INTO pending_channel_posts (channel_id, content, sort_order, revision, posted_revision)"
                " VALUES ($1, $2, 1, 3, 3)", rec.FAQ_CHANNEL, rec._faq_text())
        except BaseException:
            await c.__aexit__(None, None, None)
            raise
        built.update(schema=c.schema, own=c.own)
        await c.conn.close()
    _run(build())
    try:
        yield built["schema"]
    finally:
        async def drop():
            conn = await harness.connect_bound(lh.DSN, built["schema"])
            try:
                await harness.drop_case_schema(conn, built["schema"], built["own"])
            finally:
                await conn.close()
        _run(drop())


@pytest.fixture
def clean(case):
    """The case with no fault and no row in the three tables, so each test's
    pass sees only the rows it plants."""
    async def body(sm, _rsm):
        async with sm() as db:
            await db.execute(text("DELETE FROM alt_test_faults"))
            for t in TABLES.values():
                await db.execute(text("DELETE FROM %s" % t))
            await db.commit()
    rec._with(case, body)
    return case


@pytest.fixture
def env(monkeypatch):
    """A verified sign-in, as the recording tests make one."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", rec.HMAC_KEY)
    monkeypatch.setenv("STEAM_WEB_API_KEY", "alt-retention-steam-key")
    monkeypatch.delenv("STEAM_AUTH_ENFORCE", raising=False)
    monkeypatch.setattr(main, "_steam_http_get_json",
                        lambda url, timeout: {"response": {"params": dict(rec.STEAM["params"])}})
    A.install_key(rec.KEY_HEX)
    main._alt_notice_line_at[0] = None
    yield monkeypatch
    A.install_key(None)
    main._alt_notice_line_at[0] = None


async def _plant(sm, kind, sid, secs, n=1):
    async with sm() as db:
        await db.execute(text(_PLANT[kind]), {"s": sid, "n": n, "d": A.DUE_DAYS, "x": float(secs)})
        await db.commit()


async def _count(sm, kind, sid):
    """Rows of `kind` planted under `sid` (for facts: every id it prefixes)."""
    async with sm() as db:
        if kind == "facts":
            return (await db.execute(text("SELECT count(*) FROM steam_signin_facts WHERE steam_id LIKE :p"),
                                     {"p": sid + "%"})).scalar()
        return (await db.execute(text("SELECT count(*) FROM %s WHERE steam_id = :s" % TABLES[kind]),
                                 {"s": sid})).scalar()


async def _fault(sm, kind, op, what):
    async with sm() as db:
        if what is None:
            await db.execute(text("DELETE FROM alt_test_faults WHERE tbl = :t AND op = :o"),
                             {"t": TABLES[kind], "o": op})
        else:
            await db.execute(text("INSERT INTO alt_test_faults (tbl, op, what) VALUES (:t, :o, :w)"
                                  " ON CONFLICT (tbl, op) DO UPDATE SET what = EXCLUDED.what"),
                             {"t": TABLES[kind], "o": op, "w": what})
        await db.commit()


async def _sleeping(sm, want=1, tries=100):
    """Wait until `want` backends of this database sleep in a fault trigger."""
    for _ in range(tries):
        async with sm() as db:
            n = (await db.execute(text(
                "SELECT count(*) FROM pg_stat_activity"
                " WHERE datname = current_database() AND wait_event = 'PgSleep'"))).scalar()
        if n >= want:
            return
        await asyncio.sleep(0.03)
    raise AssertionError("no backend reached the planted sleep")


def _alt_lines(capsys, tag="[ALT-RETENTION]"):
    return [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith(tag)]


def _pass_line(lines):
    got = [PASS_LINE.match(ln) for ln in lines]
    got = [m for m in got if m]
    assert len(got) == 1, lines
    return tuple(int(g) for g in got[0].groups())


# -- the pass ---------------------------------------------------------------------

@pytest.mark.parametrize("kind", list(TABLES))
def test_one_pass_takes_a_row_a_minute_past_due_and_leaves_one_a_minute_short(clean, capsys, kind):
    past, short = _sid(), _sid()

    async def body(sm, _rsm):
        await _plant(sm, kind, past, 60)
        await _plant(sm, kind, short, -60)
        res = await main._alt_retention_pass(sm)
        return res, await _count(sm, kind, past), await _count(sm, kind, short)

    res, n_past, n_short = rec._with(clean, body)
    assert (n_past, n_short) == (0, 1)
    want = {k: (1 if k == kind else 0) for k in TABLES}
    assert res["deleted"] == want and res["left"] == {k: 0 for k in TABLES}, res
    lines = _alt_lines(capsys)
    assert _pass_line(lines)[:3] == (want["markers"], want["shares"], want["facts"])
    assert not [ln for ln in lines if "due rows left" in ln], lines


def test_due_rows_above_one_batch_all_go_in_one_pass(clean, monkeypatch, capsys):
    monkeypatch.setattr(A, "PASS_BATCH", 7)
    sids = {k: (_sid(), _sid()) for k in TABLES}

    async def body(sm, _rsm):
        for k, (due, keep) in sids.items():
            await _plant(sm, k, due, 3600, n=20)
            await _plant(sm, k, keep, -3600, n=1)
        res = await main._alt_retention_pass(sm)
        counts = {k: (await _count(sm, k, due), await _count(sm, k, keep)) for k, (due, keep) in sids.items()}
        return res, counts

    res, counts = rec._with(clean, body)
    assert counts == {k: (0, 1) for k in TABLES}, counts
    assert res["deleted"] == {k: 20 for k in TABLES} and res["batches"] == 9, res
    assert res["left"] == {k: 0 for k in TABLES}, res
    assert _pass_line(_alt_lines(capsys)) == (20, 20, 20, 9)


@pytest.mark.parametrize("count", ["counted", "not counted"])
def test_a_pass_that_fails_in_batch_two_of_three_says_what_it_did_and_what_is_left(
        clean, monkeypatch, capsys, count):
    """Finding R2-3. One due row in each table: a pass of three batches
    (markers, shares, facts). The second batch raises after the first has
    committed: the pass says it ended by a failed batch, what it deleted per
    table up to there, and the due rows left, counted in a session of their
    own (or, when that count fails too, that they were not counted); then it
    raises the batch's exception for the loop to count."""
    sids = {k: _sid() for k in TABLES}
    real = main._alt_retention_batch
    calls = []

    async def second_fails(db, table, at=None):
        calls.append(table)
        if len(calls) == 2:
            raise RuntimeError("planted")
        return await real(db, table, at)

    async def left_fails(db, at=None):
        raise OSError("planted")

    monkeypatch.setattr(main, "_alt_retention_batch", second_fails)
    if count == "not counted":
        monkeypatch.setattr(main, "_alt_retention_left", left_fails)

    async def body(sm, _rsm):
        for k, s in sids.items():
            await _plant(sm, k, s, 3600)
        with pytest.raises(RuntimeError):
            await main._alt_retention_pass(sm)
        return {k: await _count(sm, k, s) for k, s in sids.items()}

    counts = rec._with(clean, body)
    assert calls == ["markers", "shares"], calls
    assert counts == {"markers": 0, "shares": 1, "facts": 1}, counts
    lines = _alt_lines(capsys)
    left = ("[ALT-RETENTION] due rows left: markers 0, shares 1, facts 1" if count == "counted"
            else "[ALT-RETENTION] due rows left: not counted (OSError)")
    assert lines == ["[ALT-RETENTION] pass ended by a failed batch (RuntimeError): deleted markers 1,"
                     " shares 0, facts 0 in 1 batch(es)", left], lines


@pytest.mark.parametrize("where", ["in a batch", "in the count"])
def test_a_cancelled_pass_re_raises_and_prints_nothing(monkeypatch, capsys, where):
    """The pass's third end: a CancelledError raised in a batch, or in the
    count of the due rows left, is raised again by the pass, and the pass
    prints nothing."""
    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    async def batch(db, table, at=None):
        if where == "in a batch":
            raise asyncio.CancelledError()
        return 0

    async def left(db, at=None):
        if where == "in the count":
            raise asyncio.CancelledError()
        return {"markers": 0, "shares": 0, "facts": 0}

    monkeypatch.setattr(main, "_alt_retention_batch", batch)
    monkeypatch.setattr(main, "_alt_retention_left", left)
    capsys.readouterr()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main._alt_retention_pass(_Session))
    assert capsys.readouterr().out == ""


_PLANT_AT = {
    "facts": ("INSERT INTO steam_signin_facts (steam_id, first_seen_at, last_seen_at)"
              " VALUES (CAST(:s AS text) || '0001', CAST(:t AS timestamptz) - interval '10 days',"
              " CAST(:t AS timestamptz))"),
    "shares": ("INSERT INTO steam_family_shares (steam_id, key_id, owner_mark, first_seen_at, last_seen_at)"
               " VALUES (CAST(:s AS text), 'aaaaaaaaaaaa', sha256(convert_to(CAST(:s AS text), 'UTF8')),"
               " CAST(:t AS timestamptz) - interval '10 days', CAST(:t AS timestamptz))"),
    "markers": ("INSERT INTO conn_markers (steam_id, day, key_id, addr_mark, block_mark, family, conn_class,"
                " first_at, last_at)"
                " VALUES (CAST(:s AS text), CAST((CAST(:t AS timestamptz) AT TIME ZONE 'UTC') AS date),"
                " 'aaaaaaaaaaaa', sha256(convert_to(CAST(:s AS text), 'UTF8')),"
                " sha256(convert_to(CAST(:s AS text) || '-b', 'UTF8')), 4, 'none',"
                " CAST(:t AS timestamptz), CAST(:t AS timestamptz))"),
}


@pytest.mark.parametrize("hm", [(0, 1), (12, 0)], ids=["a minute after midnight UTC", "noon UTC"])
def test_ages_count_to_the_given_instant_by_last_sight_never_by_day(clean, hm):
    """Finding R2-10 (M3). The pass is GIVEN its instant `at` (a day in 2026's
    first quarter, at 00:01 or at 12:00 UTC); rows are planted relative to
    it, in sessions whose time zone is UTC. For each table one row a minute
    past due goes and one a minute short of due stays. The marker row short
    of due lies on the same UTC day as the due instant, so aging by DAY
    (the day's midnight before the due instant) disagrees with aging by last
    sight: the first discriminator. The second: every planted row is months
    past due by the server's own clock, so a pass that ignored `at` would
    take the rows that must stay. Margins: one minute either side of due."""
    from datetime import datetime, timedelta, timezone
    at = datetime(2026, 3, 10, hm[0], hm[1], tzinfo=timezone.utc)
    due = at - timedelta(days=A.DUE_DAYS)
    sids = {k: (_sid(), _sid()) for k in TABLES}

    async def body(sm, _rsm):
        async with sm() as db:
            await db.execute(text("SET TIME ZONE 'UTC'"))
            for k, (go, stay) in sids.items():
                await db.execute(text(_PLANT_AT[k]), {"s": go, "t": due - timedelta(minutes=1)})
                await db.execute(text(_PLANT_AT[k]), {"s": stay, "t": due + timedelta(minutes=1)})
            await db.commit()

        def utc_sessions():
            db = sm()
            real_execute = db.execute
            state = {"set": False}

            async def execute(stmt, *a, **kw):
                if not state["set"]:
                    state["set"] = True
                    await real_execute(text("SET TIME ZONE 'UTC'"))
                return await real_execute(stmt, *a, **kw)
            db.execute = execute
            return db

        res = await main._alt_retention_pass(utc_sessions, at=at)
        return res, {k: (await _count(sm, k, go), await _count(sm, k, stay)) for k, (go, stay) in sids.items()}

    res, counts = rec._with(clean, body)
    assert counts == {k: (0, 1) for k in TABLES}, counts
    assert res["deleted"] == {k: 1 for k in TABLES} and res["left"] == {k: 0 for k in TABLES}, res


def test_a_batch_of_the_real_size_is_measured_inside_its_limits(clean, capsys):
    """PASS_BATCH as shipped (2,000): a batch on each table is timed on this
    database, and the figure is printed for the hand-back. The design's
    capacity claim assumes at most two seconds a batch."""
    sids = {k: _sid() for k in TABLES}
    extra = 3

    async def body(sm, _rsm):
        for k, s in sids.items():
            await _plant(sm, k, s, 3600, n=A.PASS_BATCH + extra)
        took = {}
        for k in TABLES:
            async with sm() as db:
                t0 = time.monotonic()
                n = await main._alt_retention_batch(db, k)
                took[k] = (n, time.monotonic() - t0)
        res = await main._alt_retention_pass(sm)
        return took, res, {k: await _count(sm, k, s) for k, s in sids.items()}

    took, res, left = rec._with(clean, body)
    assert all(n == A.PASS_BATCH for n, _t in took.values()), took
    assert res["deleted"] == {k: extra for k in TABLES} and left == {k: 0 for k in TABLES}, (res, left)
    with capsys.disabled():
        print("[ALT-RETENTION-MEASURE] one batch of %d rows: %s" % (
            A.PASS_BATCH, ", ".join("%s %.3fs" % (k, t) for k, (_n, t) in took.items())))
    assert max(t for _n, t in took.values()) < 2.0, took


def test_a_held_due_row_is_skipped_said_and_taken_by_the_next_pass(clean, capsys):
    held, free = _sid(), _sid()

    async def body(sm, _rsm):
        for k in TABLES:
            await _plant(sm, k, held, 60)
            await _plant(sm, k, free, 60)
        holder = sm()
        try:
            for k, t in TABLES.items():
                await holder.execute(text("SELECT 1 FROM %s WHERE steam_id LIKE :p FOR UPDATE" % t),
                                     {"p": held + "%"})
            t0 = time.monotonic()
            first = await main._alt_retention_pass(sm)
            took = time.monotonic() - t0
            mid = {k: (await _count(sm, k, held), await _count(sm, k, free)) for k in TABLES}
            await holder.rollback()
        finally:
            await holder.close()
        second = await main._alt_retention_pass(sm)
        return first, took, mid, second, {k: await _count(sm, k, held) for k in TABLES}

    first, took, mid, second, after = rec._with(clean, body)
    assert mid == {k: (1, 0) for k in TABLES}, mid
    assert first["deleted"] == {k: 1 for k in TABLES} and first["left"] == {k: 1 for k in TABLES}, first
    # H4. Discriminator: the fixed batch skips the held rows (SKIP LOCKED);
    # a batch that waits for them is ended by the pass's lock limit
    # (A.PASS_LOCK_TIMEOUT_MS, 1.0 s) and raises. Margin: 0.1 s under that
    # limit. Clock: the test's time.monotonic around the call; the broken
    # wait is ended by the server's lock timer, which a test cannot give.
    assert took < 0.9, ("H4: a skipped held row takes no wait; 0.9 s is 0.1 s under the 1.0 s pass lock limit"
                        " (test's monotonic clock)", took)
    assert second["deleted"] == {k: 1 for k in TABLES} and second["left"] == {k: 0 for k in TABLES}, second
    assert after == {k: 0 for k in TABLES}, after
    lines = _alt_lines(capsys)
    assert lines.count("[ALT-RETENTION] due rows left: markers 1, shares 1, facts 1") == 1, lines


def test_the_budget_ends_a_pass_after_a_batch_and_the_rest_is_said(clean, monkeypatch, capsys):
    monkeypatch.setattr(A, "PASS_BATCH", 7)
    monkeypatch.setattr(A, "PASS_BUDGET_S", 0)
    sids = {k: _sid() for k in TABLES}

    async def body(sm, _rsm):
        for k, s in sids.items():
            await _plant(sm, k, s, 3600, n=20)
        return await main._alt_retention_pass(sm)

    res = rec._with(clean, body)
    assert res["deleted"] == {"markers": 7, "shares": 0, "facts": 0} and res["batches"] == 1, res
    assert res["left"] == {"markers": 13, "shares": 20, "facts": 20}, res
    lines = _alt_lines(capsys)
    assert _pass_line(lines) == (7, 0, 0, 1)
    assert "[ALT-RETENTION] due rows left: markers 13, shares 20, facts 20" in lines, lines


def test_the_statement_limit_ends_a_slow_batch_and_the_row_stays(clean, monkeypatch):
    monkeypatch.setattr(A, "PASS_STATEMENT_TIMEOUT_MS", 300)
    sid = _sid()

    async def body(sm, _rsm):
        await _plant(sm, "facts", sid, 60)
        await _fault(sm, "facts", "DELETE", "sleep:5")
        try:
            t0 = time.monotonic()
            with pytest.raises(Exception) as got:
                await main._alt_retention_pass(sm)
            took = time.monotonic() - t0
        finally:
            await _fault(sm, "facts", "DELETE", None)
        return got.value, took, await _count(sm, "facts", sid)

    exc, took, n = rec._with(clean, body)
    # H4. Discriminator: the pass's statement limit (set to 0.3 s here)
    # cancels the batch whose delete sleeps 5 s in the fault trigger;
    # without the limit the batch runs the whole 5 s (the pass's own 15 s
    # limit is longer). Margin: 2.2 s above the 0.3 s limit, 2.5 s under the
    # 5 s sleep. Clock: the test's time.monotonic; the cancel comes from the
    # server's statement timer, which a test cannot give.
    assert took < 2.5 and n == 1, ("H4: cancelled at the 0.3 s statement limit, not after the 5 s sleep;"
                                   " bound 2.5 s (test's monotonic clock)", took, n, exc)
    assert "57014" in repr(exc) or "QueryCanceled" in repr(exc) or "canceling statement" in str(exc), repr(exc)


def test_the_lock_limit_ends_a_wait_on_a_held_table(clean):
    sid = _sid()

    async def body(sm, _rsm):
        await _plant(sm, "facts", sid, 60)
        holder = sm()
        try:
            await holder.execute(text("LOCK TABLE steam_signin_facts IN ACCESS EXCLUSIVE MODE"))
            t0 = time.monotonic()
            with pytest.raises(Exception) as got:
                await main._alt_retention_pass(sm)
            took = time.monotonic() - t0
            await holder.rollback()
        finally:
            await holder.close()
        return got.value, took, await _count(sm, "facts", sid)

    exc, took, n = rec._with(clean, body)
    # H4. Discriminator: the pass's lock limit (A.PASS_LOCK_TIMEOUT_MS,
    # 1.0 s) ends the wait on the table the holder locks until after the
    # pass returns; without it the wait lasts until the pass's 15 s
    # statement limit. Margin: 2.0 s above the 1.0 s limit, 12 s under the
    # 15 s one. Clock: the test's time.monotonic; the end comes from the
    # server's lock timer, which a test cannot give.
    assert took < 3.0 and n == 1, ("H4: ended at the 1.0 s pass lock limit, not at the 15 s statement limit;"
                                   " bound 3.0 s (test's monotonic clock)", took, n, exc)
    assert "55P03" in repr(exc) or "LockNotAvailable" in repr(exc) or "lock timeout" in str(exc), repr(exc)


# -- one row, two writers ---------------------------------------------------------

def test_pass_first_the_sign_in_waits_at_most_its_lock_limit_and_both_finish(clean, env, capsys):
    """The pass holds the account's due facts row (its delete sleeps three
    seconds in the fault trigger); the sign-in's facts upsert gives up at the
    recording's lock limit, the answer is the baseline's, nothing of the
    recording stays, and the pass then deletes the row."""
    prefix = _sid()
    sid = prefix + "0001"

    async def body(sm, rsm):
        await _plant(sm, "facts", prefix, 60)
        await _fault(sm, "facts", "DELETE", "sleep:3")
        try:
            t0 = time.monotonic()
            janitor = asyncio.create_task(main._alt_retention_pass(sm))
            await _sleeping(sm)
            t1 = time.monotonic()
            status, ans, plan = await rec._sign_in(rsm, sid, owner=rec._sid())
            sign_in_took = time.monotonic() - t1
            res = await janitor
            pass_took = time.monotonic() - t0
        finally:
            await _fault(sm, "facts", "DELETE", None)
        await rec._nothing_recorded(sm, sid, status, ans)
        return sign_in_took, pass_took, res, plan

    sign_in_took, pass_took, res, plan = rec._with(clean, body)
    # H4. Discriminator: the recording's limits (lock 0.5 s, statement 1.5 s)
    # end the sign-in's wait on the row whose delete sleeps 3 s; with both
    # limits gone the sign-in waits for the pass's sleep to end. The lock
    # limit alone is not told apart here (the 1.5 s statement limit also
    # ends the wait under 2.0 s): the record test's lock-limit holder tells
    # it by SQLSTATE. Margin: 1.5 s above the 0.5 s lock limit, 0.5 s above
    # the 1.5 s statement limit; the broken wait is the rest of the 3 s
    # sleep. Clock: the test's time.monotonic; the server's timers end the
    # wait, and a test cannot give them. The pass bound (6.0 s) is the 3 s
    # sleep plus 3 s; it holds that the pass finishes, not a limit.
    assert sign_in_took < 2.0, ("H4: the recording's limits end its wait (0.5 s lock, 1.5 s statement), not"
                                " the pass's 3 s sleep; bound 2.0 s (test's monotonic clock)", sign_in_took)
    assert pass_took < 6.0 and res["deleted"]["facts"] == 1, (pass_took, res)
    assert "INSERT INTO steam_signin_facts" in plan.after()[-1] and plan.rollbacks == 1, plan.after()
    lines = _alt_lines(capsys, "[ALT-SIGNALS]")
    assert len(lines) == 1 and rec._LINE.match(lines[0]) and lines[0] != rec.NOTICE_LINE, lines


def test_sign_in_first_the_pass_skips_the_row_and_both_finish(clean, env, capsys):
    """The sign-in's facts upsert holds the account's due row (its update
    sleeps one second in the fault trigger, inside the recording's statement
    limit); the pass skips the row without waiting and says it is left; the
    recording completes, which moves the row's last sight, so the next pass
    leaves it too."""
    prefix = _sid()
    sid = prefix + "0001"

    async def body(sm, rsm):
        await _plant(sm, "facts", prefix, 60)
        await _fault(sm, "facts", "UPDATE", "sleep:1")
        try:
            signing = asyncio.create_task(rec._sign_in(rsm, sid, owner=rec._sid()))
            await _sleeping(sm)
            t0 = time.monotonic()
            first = await main._alt_retention_pass(sm)
            pass_took = time.monotonic() - t0
            status, ans, _plan = await signing
        finally:
            await _fault(sm, "facts", "UPDATE", None)
        rows = await rec._rows(sm, sid)
        second = await main._alt_retention_pass(sm)
        return pass_took, first, status, ans, rows, second, await _count(sm, "facts", prefix)

    pass_took, first, status, ans, rows, second, n = rec._with(clean, body)
    # H4. Discriminator: the fixed batch skips the row the sign-in holds
    # (SKIP LOCKED); a batch that waits for it waits out the rest of the
    # update's 1 s sleep. Margin: 0.9 s is about 0.1 s under that wait, so
    # the time alone is thin; the second discriminator is the count on the
    # next line: a pass that waited reads the row after the recording moved
    # its last sight, and leaves no due row. Clock: the test's
    # time.monotonic; the 1 s is the server's own sleep.
    assert pass_took < 0.9, ("H4: a skipped held row takes no wait; 0.9 s against the rest of a 1 s sleep,"
                             " the left count below is the second discriminator (test's monotonic clock)",
                             pass_took)
    assert first["deleted"]["facts"] == 0 and first["left"]["facts"] == 1, first
    rec._like_baseline(status, ans)
    assert rows == [1, 1, 1], rows
    assert second["deleted"] == {k: 0 for k in TABLES} and second["left"] == {k: 0 for k in TABLES}, second
    assert n == 1
    assert _alt_lines(capsys, "[ALT-SIGNALS]") == []


# -- the loop ---------------------------------------------------------------------

class _Stop(BaseException):
    pass


def _drive_loop(monkeypatch, outcomes, durations=None, start=0.0):
    """Run the loop with its pass, its sleeps and its clock given: the clock
    starts at `start`; each pass takes the next outcome (an exception to
    raise, or a result) and moves the clock by its duration (0 unless
    `durations` gives one); each sleep moves the clock by what it asked for;
    the sleep after the last pass ends the loop. Returns the sleeps asked for
    and the clock reading at each pass's start."""
    sleeps, passes = [], []
    todo = list(outcomes)
    took = list(durations or [0.0] * len(outcomes))
    now = [float(start)]

    async def fake_pass(*a, **kw):
        passes.append(now[0])
        out = todo.pop(0)
        now[0] += took.pop(0)
        if isinstance(out, BaseException):
            raise out
        return out

    async def fake_sleep(s, *a, **kw):
        sleeps.append(s)
        now[0] += s
        if len(sleeps) > len(outcomes):
            raise _Stop()

    monkeypatch.setattr(main, "_alt_retention_pass", fake_pass)
    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)
    with pytest.raises(_Stop):
        asyncio.run(main.alt_signals_retention_loop(clock=lambda: now[0]))
    return sleeps, passes


def test_the_loop_says_it_is_armed_and_keeps_its_schedule(monkeypatch, capsys):
    ok = {"deleted": {}, "left": {}, "batches": 0}
    sleeps, passes = _drive_loop(monkeypatch, [ok, ok, ok])
    assert sleeps == [A.PASS_FIRST_DELAY_S, A.PASS_PERIOD_S, A.PASS_PERIOD_S, A.PASS_PERIOD_S], sleeps
    assert len(passes) == 3
    lines = _alt_lines(capsys)
    assert lines[0] == ("[ALT-RETENTION] pass armed: every %ds, rows past %d days, first pass in %ds"
                        % (A.PASS_PERIOD_S, A.DUE_DAYS, A.PASS_FIRST_DELAY_S)), lines


@pytest.mark.parametrize("start", [0.0, 987654.25])
def test_each_pass_starts_one_period_after_the_previous_start_and_an_overrun_is_followed_at_once(
        monkeypatch, capsys, start):
    """Finding R2-4, on a given clock at two starting readings. Passes of
    600 s, 1,800 s and 4,000 s (the third longer than the period): the waits
    after them are 3,000 s, 1,800 s and 0, and each pass starts exactly one
    period after the one before while it has not overrun. The discriminator
    is the wait itself: counted from a pass's END the waits would be 3,600 s
    each (a 600 s margin at the first pass, the smallest)."""
    ok = {"deleted": {}, "left": {}, "batches": 0}
    sleeps, passes = _drive_loop(monkeypatch, [ok, ok, ok], durations=[600.0, 1800.0, 4000.0], start=start)
    assert sleeps == [A.PASS_FIRST_DELAY_S, 3000.0, 1800.0, 0], sleeps
    assert [p - passes[0] for p in passes] == [0.0, A.PASS_PERIOD_S, 2 * A.PASS_PERIOD_S], passes
    lines = _alt_lines(capsys)
    assert lines[1:] == ["[ALT-RETENTION] pass overran its period by 400s: the next starts now"], lines


def test_a_failing_pass_is_counted_said_and_the_loop_goes_on(monkeypatch, capsys):
    ok = {"deleted": {}, "left": {}, "batches": 0}
    sleeps, passes = _drive_loop(monkeypatch, [RuntimeError("x"), ValueError("y"), ok, RuntimeError("z")])
    assert len(passes) == 4 and sleeps[1:] == [A.PASS_PERIOD_S] * 4, sleeps
    lines = _alt_lines(capsys)[1:]
    assert lines == ["[ALT-RETENTION] pass FAILED (1 in a row): RuntimeError",
                     "[ALT-RETENTION] pass FAILED (2 in a row): ValueError",
                     "[ALT-RETENTION] pass recovered after 2 failed pass(es)",
                     "[ALT-RETENTION] pass FAILED (1 in a row): RuntimeError"], lines


def test_a_cancelled_loop_stops(monkeypatch):
    async def cancelled(*a, **kw):
        raise asyncio.CancelledError()

    monkeypatch.setattr(main, "_alt_retention_pass", cancelled)

    async def no_wait(s, *a, **kw):
        return None

    monkeypatch.setattr(main.asyncio, "sleep", no_wait)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main.alt_signals_retention_loop())


def _lifespan_branches():
    tree = ast.parse(textwrap.dedent(inspect.getsource(main.lifespan)))
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "IS_REPLICA":
            return node.body, node.orelse
    raise AssertionError("lifespan has no `if IS_REPLICA:` branch")


def _supervised_names(stmts):
    out = []
    for st in stmts:
        for node in ast.walk(st):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_supervised"
                    and len(node.args) == 2 and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[1], ast.Name)):
                out.append((node.args[0].value, node.args[1].id))
    return out


def test_the_loop_runs_on_the_primary_only_and_the_replica_line_names_it():
    replica, primary = _lifespan_branches()
    entry = ("alt_signals_retention", "alt_signals_retention_loop")
    assert _supervised_names(primary).count(entry) == 1
    assert entry not in _supervised_names(replica)
    said = [n.args[0].value for st in replica for n in ast.walk(st)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print"
            and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)]
    joined = [s for s in said if "write schedulers disabled" in s]
    assert joined and "alt_signals_retention" in joined[0], said


def test_the_pass_is_called_by_its_own_loop_alone():
    """The pass runs on its own task, behind no other arm: in main.py only
    alt_signals_retention_loop calls _alt_retention_pass, and only lifespan
    starts that loop."""
    with open(main.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    def users(name):
        return [top.name for top in tree.body
                if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)) and top.name != name
                and any(isinstance(n, ast.Name) and n.id == name for n in ast.walk(top))]

    assert users("_alt_retention_pass") == ["alt_signals_retention_loop"]
    assert users("alt_signals_retention_loop") == ["lifespan"]


def test_the_pass_is_a_janitor_root_and_its_statements_are_inventoried():
    assert ("main", "alt_signals_retention_loop") in main._JANITOR_SELFTEST_ROOTS
    inv = main._janitor_sql_inventory()
    assert inv["dynamic"] == [], inv["dynamic"]
    mine = [" ".join(s["sql"].split()) for s in inv["statements"]
            if s["module"] == "main" and s["func"] in ("_alt_retention_batch", "_alt_retention_left", "_alt_limits")]
    deletes = [q for q in mine if q.startswith("DELETE FROM ")]
    assert sorted(q.split()[2] for q in deletes) == ["conn_markers", "steam_family_shares", "steam_signin_facts"], mine
    assert all("FOR UPDATE SKIP LOCKED" in q and "make_interval(days => CAST(:days AS integer))" in q
               for q in deletes), deletes
    assert len([q for q in mine if q.startswith("SELECT (SELECT count(*)")]) == 1, mine
    assert len([q for q in mine if "set_config('lock_timeout'" in q]) == 1, mine
    assert len(mine) == 5, mine
    census = main._janitor_lock_census()
    assert [r["func"] for r in census["declines"]].count("_alt_retention_batch") == 3, census["declines"]
    assert "_alt_retention_batch" not in [r["func"] for r in census["waits"]], census["waits"]
