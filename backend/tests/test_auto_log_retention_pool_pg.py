"""Retention behind a stalled volume, on a REAL pool (round 9, R8-M1 / B15).

Round 8's report: "thirty overlapping authorised maintenance passes can
retain the 20+10 connections behind four volume workers; unrelated queue or
match requests can exceed the 30-second pool checkout timeout". Its WITNESS:
thirty concurrent authorised prune calls under a stalled volume must leave the
real main pool available to an unrelated checkout, and the request-facing
timeout must return 503.

`test_auto_logs.py` drives that shape on a MODEL of the pool. This file drives
it on a real SQLAlchemy pool over asyncpg against PostgreSQL, sized from
`database.engine`'s own pool (20 + 10, 30 s checkout timeout), each call on a
session of its own as `get_db` gives each request one, with the volume held
in its worker thread. The CONTROL is the fix reverted at its three sites --
the gate, T1's end before the hop, and the advisory lock's answer -- and it
must make the unrelated checkout wait; the TWIN spells the same three sites
otherwise and must change nothing.

Live PostgreSQL is REQUIRED, and a missing DSN FAILS (#438):

    AUTO_LOG_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>

The database name must carry `autolog`: the case creates and drops its own
`bug_reports` table there. `AUTO_LOG_TEST_PG_OPTOUT=1` says out loud that a
run skips it.
"""

import asyncio
import inspect
import os
import pathlib
import sys
import textwrap
import threading
import time
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from fastapi import HTTPException

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import auto_logs  # noqa: E402
import database  # noqa: E402
import main  # noqa: E402

DSN = os.environ.get("AUTO_LOG_TEST_PG_DSN")


def _optout(raw) -> bool:
    """Only an affirmative word opts out; "0", "false" or an unknown value do
    not, so the live check then FAILS and names the DSN (#438)."""
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


OPTOUT = _optout(os.environ.get("AUTO_LOG_TEST_PG_OPTOUT"))


def require_pg():
    if DSN:
        name = urlsplit(DSN).path.lstrip("/")
        if "autolog" not in name:
            pytest.fail("AUTO_LOG_TEST_PG_DSN points at database %r; this case "
                        "creates and drops a bug_reports table there, so it "
                        "runs only in a database whose name carries 'autolog'"
                        % name)
        return DSN
    if OPTOUT:
        pytest.skip("AUTO_LOG_TEST_PG_OPTOUT is set -- the live-PostgreSQL "
                    "retention pool check deliberately not run in this "
                    "invocation")
    pytest.fail(
        "AUTO_LOG_TEST_PG_DSN is not set, so retention was never driven on a "
        "real pool. Set AUTO_LOG_TEST_PG_DSN=postgresql+asyncpg://.../"
        "<a database named for autolog> to run it, or "
        "AUTO_LOG_TEST_PG_OPTOUT=1 to say out loud that this run skips it.")


@pytest.mark.parametrize("raw,opts_out", [
    ("1", True), ("true", True), (" yes ", True), ("on", True),
    ("0", False), ("false", False), ("", False), (None, False), ("maybe", False),
])
def test_only_an_affirmative_opt_out_turns_the_live_check_into_a_skip(raw,
                                                                    opts_out):
    assert _optout(raw) is opts_out


def test_the_live_check_cannot_be_skipped_by_a_missing_dsn_alone():
    assert "pytest.fail(" in inspect.getsource(require_pg)
    mod = sys.modules[__name__]
    saved_dsn, saved_opt = mod.DSN, mod.OPTOUT
    mod.DSN, mod.OPTOUT = None, False
    try:
        with pytest.raises(BaseException) as ex:
            require_pg()
        assert "Failed" in type(ex.value).__name__
        assert "AUTO_LOG_TEST_PG_DSN" in str(ex.value)
        mod.OPTOUT = True
        with pytest.raises(BaseException) as sk:
            require_pg()
        assert "Skipped" in type(sk.value).__name__
        mod.DSN, mod.OPTOUT = "postgresql+asyncpg://u@h:1/scr_other", False
        with pytest.raises(BaseException) as wrong:
            require_pg()
        assert "Failed" in type(wrong.value).__name__
    finally:
        mod.DSN, mod.OPTOUT = saved_dsn, saved_opt


# ── the three sites of the fix, and their reverted and inert spellings ──────

_GATE = "@_one_retention_pass_at_a_time\n"
_T1_END = ("    )).mappings().all()\n"
           "    await _end_transaction(db)\n"
           "    if not due:\n")
_LOCK_ANSWER = "    return got is True\n"

REVERTED = {
    "prune_auto_logs": [(_GATE, ""),
                        (_T1_END, "    )).mappings().all()\n    if not due:\n")],
    "_take_prune_lock": [(_LOCK_ANSWER, "    return True\n")],
}
TWIN = {
    "prune_auto_logs": [(_GATE, "@(_one_retention_pass_at_a_time)\n"),
                        (_T1_END, "    )).mappings().all()\n"
                                  "    await (_end_transaction)(db)\n"
                                  "    if not due:\n")],
    "_take_prune_lock": [(_LOCK_ANSWER, "    return bool(got is True)\n")],
}


def _mutant(name, pairs):
    """`auto_logs.<name>` with every (anchor, replacement) applied, each
    anchor asserted to be exactly one site of the function (#432/#279),
    compiled against a copy of the module's globals."""
    src = textwrap.dedent(inspect.getsource(getattr(auto_logs, name)))
    for anchor, replacement in pairs:
        assert src.count(anchor) == 1, (name, anchor)
        src = src.replace(anchor, replacement)
    namespace = dict(vars(auto_logs))
    exec(compile(src, "<mutant:%s>" % name, "exec"), namespace)
    return namespace[name]


class _Stall:
    """`_unlink_due_blobs`, held IN ITS WORKER THREAD until `release()`: a
    volume that does not answer. Bounded, so a failing case cannot park a
    thread for ever."""

    def __init__(self, fn):
        self.fn = fn
        self.gate = threading.Event()
        self.lock = threading.Lock()
        self.entered = 0
        self.finished = 0

    def __call__(self, *a, **kw):
        with self.lock:
            self.entered += 1
        try:
            self.gate.wait(60.0)
            return self.fn(*a, **kw)
        finally:
            with self.lock:
                self.finished += 1

    def release(self):
        self.gate.set()


async def _until(predicate, cap_s=10.0, step=0.02):
    for _ in range(max(1, int(cap_s / step))):
        if predicate():
            return True
        await asyncio.sleep(step)
    return bool(predicate())


async def _seed(engine, logdir, n_due):
    """A bare `bug_reports` of the columns retention reads: `n_due` automatic
    rows past fourteen days with blobs on the volume, two bug reports as old,
    and two young automatic rows."""
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS bug_reports"))
        await conn.execute(text(
            "CREATE TABLE bug_reports (id uuid PRIMARY KEY, "
            "kind varchar(16) NOT NULL DEFAULT 'report', "
            "created_at timestamptz NOT NULL DEFAULT now(), "
            "log_filename text)"))
        for i in range(n_due):
            name = "due-%02d.log.gz" % i
            (logdir / name).write_bytes(b"x")
            await conn.execute(text(
                "INSERT INTO bug_reports (id, kind, created_at, log_filename) "
                "VALUES (CAST(:id AS uuid), 'auto', now() - make_interval("
                "days => CAST(:d AS integer)), :n)"),
                {"id": str(UUID(int=0x9000 + i)), "d": 20 + i, "n": name})
        for i in range(2):
            await conn.execute(text(
                "INSERT INTO bug_reports (id, kind, created_at) VALUES "
                "(CAST(:id AS uuid), 'report', now() - make_interval(days => 30))"),
                {"id": str(UUID(int=0xA000 + i))})
            await conn.execute(text(
                "INSERT INTO bug_reports (id, kind, created_at, log_filename) "
                "VALUES (CAST(:id AS uuid), 'auto', now() - make_interval("
                "days => 1), :n)"),
                {"id": str(UUID(int=0xB000 + i)), "n": "young-%d.log.gz" % i})


async def _counts(engine):
    from sqlalchemy import text
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT kind, created_at < now() - make_interval(days => 14) AS old, "
            "count(*) AS n FROM bug_reports GROUP BY 1, 2"))).all()
    return {(r[0], bool(r[1])): int(r[2]) for r in rows}


async def _drive(logdir, stall, n=30):
    """`n` authorised prune calls at once on one real pool sized like
    production, each on a session of its own, while the volume does not
    answer. Answers what the pool and an unrelated checkout read while they
    wait, every call's status, and the table before and after."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                        create_async_engine)
    prod = database.engine.pool
    engine = create_async_engine(
        DSN, pool_size=prod.size(), max_overflow=prod._max_overflow,
        pool_timeout=prod._timeout, pool_pre_ping=True)
    Session = async_sessionmaker(engine, class_=AsyncSession,
                                 expire_on_commit=False)
    try:
        await _seed(engine, logdir, n_due=n + 10)
        before = await _counts(engine)
        await engine.dispose()

        t = time.monotonic()
        async with Session() as s:
            await s.execute(text("SELECT 1"))
        baseline_s = time.monotonic() - t

        async def one_call():
            async with Session() as s:          # what get_db gives a request
                try:
                    await auto_logs.run_auto_log_prune(
                        x_internal_key="shh", days=14, db=s)
                    return 200
                except HTTPException as e:
                    return e.status_code
                finally:
                    await s.close()

        calls = [asyncio.ensure_future(one_call()) for _ in range(n)]
        reached = await _until(lambda: stall.entered >= 1, 10.0)
        await asyncio.sleep(1.0)        # every other call reaches its state
        out_while_stalled = engine.pool.checkedout()
        refused_early = sum(1 for c in calls if c.done())
        t = time.monotonic()
        try:
            async def unrelated():
                async with Session() as s:      # a queue join, a match report
                    await s.execute(text("SELECT 1"))
            await asyncio.wait_for(unrelated(), 5.0)
            unrelated_outcome = "served"
        except (asyncio.TimeoutError, TimeoutError):
            unrelated_outcome = "still waiting at 5s"
        except Exception as ex:                 # the pool's own timeout
            unrelated_outcome = "failed: %s" % type(ex).__name__
        unrelated_s = time.monotonic() - t
        statuses = list(await asyncio.gather(*calls))
        stall.release()
        await _until(lambda: stall.finished >= stall.entered
                     and auto_logs._VOLUME_POOL._work_queue.qsize() == 0, 30.0)
        await asyncio.sleep(0.2)
        after = await _counts(engine)
        return {"reached": reached, "baseline_s": baseline_s,
                "out": out_while_stalled, "refused_early": refused_early,
                "unrelated": unrelated_outcome, "unrelated_s": unrelated_s,
                "statuses": statuses, "before": before, "after": after,
                "pool_after": engine.pool.checkedout(),
                "pool": (prod.size(), prod._max_overflow, prod._timeout)}
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS bug_reports"))
        await engine.dispose()


def _findings(seen):
    bad = []
    if not seen["reached"]:
        return ["no pass reached the volume: %r" % (seen,)]
    if seen["out"]:
        bad.append("%d connection(s) of the real pool checked out while the "
                   "passes waited on the volume" % seen["out"])
    if seen["unrelated"] != "served" or seen["unrelated_s"] > 2.0:
        bad.append("an unrelated checkout was %s after %.2fs (baseline %.3fs)"
                   % (seen["unrelated"], seen["unrelated_s"],
                      seen["baseline_s"]))
    if 200 in seen["statuses"]:
        bad.append("a pass past its ceiling answered 200")
    return bad


def _run_case(logdir, monkeypatch, patches=None):
    monkeypatch.setattr(auto_logs, "_PRUNE_PASS", [None])
    monkeypatch.setattr(auto_logs, "_PRUNE_HELD", {})
    stall = _Stall(auto_logs._unlink_due_blobs)
    monkeypatch.setattr(auto_logs, "_unlink_due_blobs", stall)
    real = {name: getattr(auto_logs, name) for name in (patches or {})}
    for name, pairs in (patches or {}).items():
        monkeypatch.setattr(auto_logs, name, _mutant(name, pairs))
    try:
        seen = asyncio.run(_drive(logdir, stall))
    finally:
        stall.release()
        for name, fn in real.items():
            monkeypatch.setattr(auto_logs, name, fn)
    print("[POOL-WITNESS] %s: pool %r, connections checked out while stalled "
          "%d, refused before any statement %d, unrelated checkout %s in "
          "%.3fs (baseline %.3fs), statuses %r, rows before %r after %r"
          % ("fix" if not patches else
             ("REVERTED" if patches is REVERTED else "TWIN"),
             seen["pool"], seen["out"], seen["refused_early"],
             seen["unrelated"], seen["unrelated_s"], seen["baseline_s"],
             sorted(seen["statuses"]), sorted(seen["before"].items()),
             sorted(seen["after"].items())))
    return seen


def test_thirty_prune_calls_on_the_real_pool_leave_it_available(tmp_path,
                                                                monkeypatch):
    """THE WITNESS. Thirty authorised prune calls, the volume stalled, the
    real pool at production's size: no connection checked out while they
    wait, the unrelated checkout served in its normal time, twenty-nine
    refused 409 before any statement, the admitted pass 503 at its ceiling,
    and no row deleted by it. CONTROL (the fix reverted): the unrelated
    checkout waits. TWIN: nothing changes."""
    require_pg()
    prod = database.engine.pool
    assert (prod.size(), prod._max_overflow, prod._timeout) == (20, 10, 30), (
        "database.engine's pool is not 20 + 10 with a 30 s timeout any more; "
        "this witness sizes itself from it, so re-read round 8's finding "
        "against the new size")
    monkeypatch.setattr(main, "BUG_REPORT_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("API_SECRET_KEY", "shh")
    monkeypatch.setattr(auto_logs, "AUTO_LOG_SWEEP_HOP_WAIT_S", 4.0)
    monkeypatch.setattr(auto_logs, "_PRUNE_BATCH", 1)

    seen = _run_case(tmp_path, monkeypatch)
    assert _findings(seen) == [], (_findings(seen), seen)
    assert sorted(seen["statuses"]) == [409] * 29 + [503], seen["statuses"]
    assert seen["refused_early"] == 29, seen
    assert seen["after"] == seen["before"], (
        "the pass past its ceiling deleted a row: %r -> %r"
        % (seen["before"], seen["after"]))
    assert seen["pool_after"] == 0, seen

    reverted = _run_case(tmp_path, monkeypatch, REVERTED)
    assert _findings(reverted), (
        "with the fix reverted the unrelated checkout was still served at "
        "once, so this witness cannot see the pool retained: %r" % (reverted,))
    assert reverted["out"] == 30 and reverted["unrelated"] != "served", reverted

    twin = _run_case(tmp_path, monkeypatch, TWIN)
    assert _findings(twin) == [], (
        "the inert twin reds, so the control above is reacting to the sites "
        "being edited rather than to the fix: %r" % (twin,))


def test_a_pass_whose_lock_another_session_holds_is_refused_holding_nothing(
        tmp_path, monkeypatch):
    """The advisory lock is what refuses a second PROCESS. Another session
    holds the retention pass's lock in an open transaction: the route answers
    409, deletes nothing, and returns its connection."""
    require_pg()
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                        create_async_engine)
    monkeypatch.setattr(main, "BUG_REPORT_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("API_SECRET_KEY", "shh")
    monkeypatch.setattr(auto_logs, "_PRUNE_PASS", [None])

    async def drive():
        engine = create_async_engine(DSN, pool_size=2, max_overflow=0)
        other = create_async_engine(DSN, pool_size=1, max_overflow=0)
        Session = async_sessionmaker(engine, class_=AsyncSession)
        try:
            await _seed(engine, tmp_path, n_due=3)
            before = await _counts(engine)
            async with other.connect() as holder:
                tx = await holder.begin()
                await holder.execute(
                    text("SELECT pg_advisory_xact_lock(CAST(:c AS integer), "
                         "CAST(:k AS integer))"),
                    {"c": auto_logs.AUTO_LOG_PRUNE_LOCK_CLASS,
                     "k": auto_logs.AUTO_LOG_PRUNE_LOCK_KEY})
                async with Session() as s:
                    try:
                        await auto_logs.run_auto_log_prune(
                            x_internal_key="shh", days=14, db=s)
                        status = 200
                    except HTTPException as e:
                        status = e.status_code
                    out_after_refusal = engine.pool.checkedout()
                await tx.rollback()
            after = await _counts(engine)
            async with Session() as s:
                out = await auto_logs.run_auto_log_prune(
                    x_internal_key="shh", days=14, db=s)
            return status, out_after_refusal, before, after, out
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DROP TABLE IF EXISTS bug_reports"))
            await engine.dispose()
            await other.dispose()

    status, out_after_refusal, before, after, out = asyncio.run(drive())
    print("[LOCK-WITNESS] refused %d with the lock held elsewhere; connections "
          "checked out after the refusal %d; rows before %r after %r; the pass "
          "after the lock was released deleted %d"
          % (status, out_after_refusal, sorted(before.items()),
             sorted(after.items()), out["rows"]))
    assert status == 409, status
    assert out_after_refusal == 0, out_after_refusal
    assert after == before, (before, after)
    assert out["rows"] == 3, out
