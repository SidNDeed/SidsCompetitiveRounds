"""Every ordering of a fallback and a real-totals 2v2 disconnect report.

WHAT THIS FILE PROVES, and why it needs a live server. The property under test
is that the outcome of a 2v2 disconnect no longer depends on which of two
client requests reaches the series row first. That is a statement about row
locks, about lock WAITS, and about which clock a marker is stamped on -- all
PostgreSQL behaviours. A fake session can show which statements are issued and
in what order, but it cannot block one transaction behind another, and a test
that merely ran the two calls back to back would pass with the whole deferral
removed.

So this file needs a throwaway cluster. Point SEPT16DC_TEST_PG_DSN at one:

    SEPT16DC_TEST_PG_DSN=postgresql+asyncpg://postgres@127.0.0.1:55432/scr_sept16dc

and the file skips when it is unset, so the ordinary suite is unaffected. It
never runs against a real deployment: it drops and recreates its own three
tables, and every Steam id it uses is outside the real id space.

THE SCHEMA IS DELIBERATELY PRE-MIGRATION. The tables are created WITHOUT the
two marker columns, and then backend/sql/326_team_series_dc_fallback_at.sql is
executed verbatim from disk. The harness therefore exercises the migration
itself, and an edit to that file is carried into every scenario below rather
than silently diverging from a copy.

WHAT IS STUBBED, AND WHAT IS NOT. _complete_team_series_with_ratings is
replaced by a recorder that performs the one write the real helper's callers
depend on (status='completed') and counts its invocations. Standing up Glicko,
gold, the ledger and the bet tables would test those, not this; what these
scenarios must answer is "was the rating path reached, exactly once, and with
which winner". Everything else -- the row locks, the room and membership
fences, the service-subject assertion, the marker, the sweep -- is the real
code against the real database.

No pytest-asyncio: the rest of the suite drives coroutines through asyncio.run
and an opt-in acceptance file is not a reason to add a dependency the other
files do not have.
"""

import asyncio
import contextlib
import os
import pathlib
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import main


DSN = os.environ.get("SEPT16DC_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(
    not DSN,
    reason="SEPT16DC_TEST_PG_DSN unset; live-PostgreSQL ordering acceptance")

SQL_DIR = pathlib.Path(__file__).resolve().parents[1] / "sql"
MIGRATION = SQL_DIR / "326_team_series_dc_fallback_at.sql"

# Outside the real SteamID64 space, so a misconfigured DSN cannot collide with
# production rows. T1 disconnects; T2A is the elected reporter.
SID_T1A = "90000000000000021"          # the player who disconnects
SID_T1B = "90000000000000022"
SID_T2A = "90000000000000023"          # the reporter (non-DC team)
SID_T2B = "90000000000000024"

PRE_326_SCHEMA = """
DROP TABLE IF EXISTS team_matches;
DROP TABLE IF EXISTS team_series;
DROP TABLE IF EXISTS players;

CREATE TABLE players (
    id UUID PRIMARY KEY,
    steam_id VARCHAR(20) UNIQUE NOT NULL,
    display_name VARCHAR(64) NOT NULL DEFAULT 'tester'
);

CREATE TABLE team_series (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active',
    t1a_id UUID, t1b_id UUID, t2a_id UUID, t2b_id UUID,
    t1_series_wins INT NOT NULL DEFAULT 0,
    t2_series_wins INT NOT NULL DEFAULT 0,
    photon_room_id TEXT,
    relocked_at TIMESTAMPTZ,
    dc_player_id UUID,
    dc_team_remaining INT,
    dc_grace_until TIMESTAMPTZ,
    winner_team INT,
    completed_at TIMESTAMPTZ,
    invalidated_at TIMESTAMPTZ,
    invalidation_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    room_issued_at TIMESTAMPTZ,
    spawn_confirmations INT NOT NULL DEFAULT 0
);

CREATE TABLE team_matches (
    id BIGSERIAL PRIMARY KEY,
    series_id UUID NOT NULL,
    t1a_id UUID, t1b_id UUID, t2a_id UUID, t2b_id UUID,
    t1_rounds_won INT, t2_rounds_won INT,
    t1_points_total INT, t2_points_total INT,
    winner_team INT, dc_player_id UUID,
    dc_at TIMESTAMPTZ, ended_at TIMESTAMPTZ,
    photon_room_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def _raw_dsn():
    """asyncpg's own DSN form, for running multi-statement scripts."""
    return (DSN or "").replace("postgresql+asyncpg://", "postgresql://")


async def _run_script(sql: str) -> None:
    import asyncpg
    conn = await asyncpg.connect(_raw_dsn())
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


class _Rated:
    """Recorder standing in for _complete_team_series_with_ratings."""

    def __init__(self):
        self.calls = []

    async def __call__(self, db, series_uuid, winner_team, reason, dc_pid=None):
        self.calls.append({"series": str(series_uuid), "winner": winner_team,
                           "reason": reason})
        await db.execute(
            text("""UPDATE team_series
                       SET status = 'completed', winner_team = :wt,
                           completed_at = NOW(), invalidation_reason = :rsn,
                           dc_player_id = COALESCE(:dpid, dc_player_id)
                     WHERE id = :sid AND status <> 'completed'"""),
            {"sid": series_uuid, "wt": winner_team, "rsn": reason, "dpid": dc_pid},
        )
        return {}


@contextlib.contextmanager
def _harness_globals():
    """Swap the module state these scenarios must control, and put it back.

    * the rating/economy helper becomes a recorder;
    * the DC signature check runs in its no-secret mode, so no secret is read
      from anywhere -- the environment's own value, whatever it is, is neither
      read nor written by this file;
    * the in-match evidence map is emptied and the process is aged past the
      trust window, because _group_game_in_progress vetoes EVERYTHING while the
      process is young and pytest's process is seconds old.
    """
    rated = _Rated()
    old_complete = main._complete_team_series_with_ratings
    old_secret = main.MATCH_HMAC_SECRET
    old_started = main._PROCESS_STARTED_AT
    old_seen = dict(main._in_match_seen)
    main._complete_team_series_with_ratings = rated
    main.MATCH_HMAC_SECRET = ""
    main._PROCESS_STARTED_AT = time.monotonic() - (main.IN_MATCH_TTL_SEC * 3)
    main._in_match_seen.clear()
    try:
        assert main._in_match_evidence_trustworthy()
        yield rated
    finally:
        main._complete_team_series_with_ratings = old_complete
        main.MATCH_HMAC_SECRET = old_secret
        main._PROCESS_STARTED_AT = old_started
        main._in_match_seen.clear()
        main._in_match_seen.update(old_seen)


async def _fresh_series(t2_wins: int = 1):
    """Reset the schema, apply migration 326, seed one active series.

    t2_wins=1 puts the NON-disconnecting team one game up, which is the
    condition under which a real-totals report carrying >=2 points completes
    the series WITH ratings. That is the outcome a fallback must never be able
    to displace, so it is the outcome every ordering below asserts.
    """
    await _run_script(PRE_326_SCHEMA)
    await _run_script(MIGRATION.read_text(encoding="utf-8"))
    engine = create_async_engine(DSN, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    ids = {"sid": uuid.uuid4()}
    async with Session() as s:
        for key, steam in (("t1a", SID_T1A), ("t1b", SID_T1B),
                           ("t2a", SID_T2A), ("t2b", SID_T2B)):
            ids[key] = uuid.uuid4()
            await s.execute(
                text("INSERT INTO players (id, steam_id) VALUES (:i, :s)"),
                {"i": ids[key], "s": steam})
        await s.execute(
            text("""INSERT INTO team_series
                       (id, status, t1a_id, t1b_id, t2a_id, t2b_id,
                        t1_series_wins, t2_series_wins)
                    VALUES (:sid, 'active', :t1a, :t1b, :t2a, :t2b, 0, :w)"""),
            {"sid": ids["sid"], "t1a": ids["t1a"], "t1b": ids["t1b"],
             "t2a": ids["t2a"], "t2b": ids["t2b"], "w": t2_wins})
        await s.commit()
    return engine, Session, ids


async def _fallback(Session, sid):
    """The zero-total report a non-elected survivor files."""
    async with Session() as s:
        return await main.team_series_report_dc(
            series_id=str(sid), reporter_steam_id=SID_T2A,
            dc_player_steam_id=SID_T1A, t1_points_total=0, t2_points_total=0,
            photon_room_id=None, is_fallback=True, hmac_sig="", db=s)


async def _real_totals(Session, sid):
    """The elected reporter's report, carrying the abandoned game's points."""
    async with Session() as s:
        return await main.team_series_report_dc(
            series_id=str(sid), reporter_steam_id=SID_T2A,
            dc_player_steam_id=SID_T1A, t1_points_total=3, t2_points_total=4,
            photon_room_id=None, is_fallback=False, hmac_sig="", db=s)


async def _row(Session, sid):
    async with Session() as s:
        return (await s.execute(
            text("""SELECT status, invalidation_reason, dc_player_id,
                           dc_team_remaining, dc_fallback_at,
                           dc_fallback_player_id,
                           EXTRACT(EPOCH FROM (clock_timestamp() - dc_fallback_at))
                               AS marker_age
                      FROM team_series WHERE id = :sid"""),
            {"sid": sid})).mappings().first()


async def _age_marker(Session, sid, seconds):
    """Back-date the marker by `seconds`, which is how a scenario reaches the
    far side of a 120 s bound without sleeping for two minutes."""
    async with Session() as s:
        await s.execute(
            text("""UPDATE team_series
                       SET dc_fallback_at =
                               dc_fallback_at - make_interval(secs => :n)
                     WHERE id = :sid"""),
            {"sid": sid, "n": float(seconds)})
        await s.commit()


async def _sweep(Session):
    async with Session() as s:
        return await main._team_dc_fallback_sweep_once(s)


def _drive(body):
    return asyncio.run(body())


# ── Ordering 1: fallback first, then the real-totals report ──────────────


def test_fallback_first_then_real_totals_ends_rated():
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals() as rated:
                out = await _fallback(Session, sid)
                assert out["status"] == "deferred", out
                assert out["deferred"] is True
                assert out["defer_seconds"] == main._DC_FALLBACK_DEFER_SECONDS
                mid = await _row(Session, sid)
                # It settled nothing and attributed nothing to the live row.
                assert mid["status"] == "active"
                assert mid["invalidation_reason"] is None
                assert mid["dc_player_id"] is None
                assert mid["dc_team_remaining"] is None
                # It did record who filed, and when, on the marker.
                assert mid["dc_fallback_at"] is not None
                assert mid["dc_fallback_player_id"] == ids["t1a"]
                assert not rated.calls

                out2 = await _real_totals(Session, sid)
                assert out2["status"] == "completed", out2
                assert out2["reason"] == "dc_leadforfeit"
                end = await _row(Session, sid)
                assert end["status"] == "completed"
                assert [c["winner"] for c in rated.calls] == [2]
        finally:
            await engine.dispose()
    _drive(body)


# ── Ordering 2: the real-totals report first, then the fallback ──────────


def test_real_totals_first_then_fallback_ends_rated():
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals() as rated:
                out = await _real_totals(Session, sid)
                assert out["status"] == "completed", out
                assert len(rated.calls) == 1

                # The late fallback is refused by the existing settled-row
                # guard, exactly as any late report is, and writes no marker.
                out2 = await _fallback(Session, sid)
                assert out2["ignored"] is True, out2
                assert out2["status"] == "completed"
                end = await _row(Session, sid)
                assert end["status"] == "completed"
                assert end["dc_fallback_at"] is None
                assert len(rated.calls) == 1
        finally:
            await engine.dispose()
    _drive(body)


# ── Ordering 3: both in flight, decided by a real lock wait ──────────────


def test_both_in_flight_across_the_lock_wait_ends_rated():
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals() as rated:
                # A third session holds the series row, so BOTH reports queue
                # on the same lock and the database, not this test, decides
                # which of them gets it first.
                blocker = Session()
                await blocker.execute(
                    text("SELECT id FROM team_series WHERE id = :sid"
                         "  FOR NO KEY UPDATE"), {"sid": sid})
                a = asyncio.create_task(_fallback(Session, sid))
                b = asyncio.create_task(_real_totals(Session, sid))
                await asyncio.sleep(1.0)
                assert not a.done() and not b.done(), "neither report waited"
                await blocker.rollback()
                await blocker.close()
                fb, rt = await a, await b

                # Whichever won the lock, the series is rated and the rating
                # path ran exactly once.
                end = await _row(Session, sid)
                assert end["status"] == "completed", (fb, rt, dict(end))
                assert [c["winner"] for c in rated.calls] == [2]
                # And the fallback's own answer is one of the two dispositions
                # that cannot decide anything.
                assert (fb.get("status") == "deferred"
                        or fb.get("ignored") is True), fb
        finally:
            await engine.dispose()
    _drive(body)


# ── Ordering 4: a sweep tick lands between the two reports ───────────────


def test_a_sweep_between_the_reports_does_not_settle_inside_the_bound():
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals() as rated:
                assert (await _fallback(Session, sid))["status"] == "deferred"
                # The marker is seconds old; the bound is 120.
                assert await _sweep(Session) == 0
                mid = await _row(Session, sid)
                assert mid["status"] == "active"
                assert mid["marker_age"] < main._DC_FALLBACK_DEFER_SECONDS

                out = await _real_totals(Session, sid)
                assert out["status"] == "completed", out
                assert [c["winner"] for c in rated.calls] == [2]
        finally:
            await engine.dispose()
    _drive(body)


# ── Ordering 5: a sweep tick lands after the series is already rated ─────


def test_a_sweep_after_a_completed_series_is_a_no_op():
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals() as rated:
                assert (await _fallback(Session, sid))["status"] == "deferred"
                assert (await _real_totals(Session, sid))["status"] == "completed"
                # The marker outlives the completion by design -- "a fallback
                # was filed" is worth keeping -- so age it well past the bound
                # and prove the status predicate is what makes it inert.
                await _age_marker(Session, sid, main._DC_FALLBACK_DEFER_SECONDS * 3)
                assert await _sweep(Session) == 0
                end = await _row(Session, sid)
                assert end["status"] == "completed"
                assert end["invalidation_reason"] == "dc_leadforfeit"
                assert len(rated.calls) == 1
        finally:
            await engine.dispose()
    _drive(body)


# ── The bound: dc_incomplete ONLY when nothing else arrived ──────────────


def test_the_sweep_settles_only_after_the_bound_and_only_to_dc_incomplete():
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals() as rated:
                assert (await _fallback(Session, sid))["status"] == "deferred"

                # Negative control: just INSIDE the bound, nothing happens.
                await _age_marker(Session, sid, main._DC_FALLBACK_DEFER_SECONDS - 30)
                assert await _sweep(Session) == 0
                assert (await _row(Session, sid))["status"] == "active"

                # Past it, and with no real-totals report ever arriving, the
                # series reaches the admin panel -- and nothing else.
                await _age_marker(Session, sid, 60)
                assert await _sweep(Session) == 1
                end = await _row(Session, sid)
                assert end["status"] == "dc_incomplete"
                assert end["invalidation_reason"] == "dc_manual_pending"
                # The attribution the settling path used to write inline is
                # carried across from the marker at settle time.
                assert end["dc_player_id"] == ids["t1a"]
                assert end["dc_team_remaining"] == 2
                assert not rated.calls, "the sweep moved a rating"

                # Idempotent: a second tick finds nothing.
                assert await _sweep(Session) == 0
        finally:
            await engine.dispose()
    _drive(body)


# ── The marker is stamped AFTER the lock wait ────────────────────────────


def test_the_deferral_marker_is_stamped_on_the_post_lock_clock():
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals():
                # Hold the row for three seconds. The report's transaction has
                # already begun by the time it reaches the locked read, so a
                # marker taken from NOW() would carry the time BEFORE this
                # wait and arrive three seconds stale.
                blocker = Session()
                await blocker.execute(
                    text("SELECT id FROM team_series WHERE id = :sid"
                         "  FOR NO KEY UPDATE"), {"sid": sid})
                started = time.monotonic()
                task = asyncio.create_task(_fallback(Session, sid))
                await asyncio.sleep(3.0)
                assert not task.done(), "the report did not wait on the lock"
                await blocker.rollback()
                await blocker.close()
                out = await task
                waited = time.monotonic() - started
                assert out["status"] == "deferred"
                assert waited >= 2.5, waited

                row = await _row(Session, sid)
                # Measured on the SAME clock the sweep compares against.
                assert row["marker_age"] is not None
                assert float(row["marker_age"]) < 1.0, (
                    f"marker is {row['marker_age']}s old after a {waited:.1f}s "
                    "lock wait -- it was stamped before the wait")
        finally:
            await engine.dispose()
    _drive(body)


# ── The live-game veto ───────────────────────────────────────────────────


def test_the_sweep_is_vetoed_by_live_game_evidence():
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals():
                assert (await _fallback(Session, sid))["status"] == "deferred"
                await _age_marker(Session, sid, main._DC_FALLBACK_DEFER_SECONDS * 2)

                # A client has reported being in a game for this series.
                main._in_match_touch(str(sid))
                assert await _sweep(Session) == 0
                assert (await _row(Session, sid))["status"] == "active"

                # Negative control: with the evidence aged out, the same row
                # settles. Without this half the assertion above would also
                # pass on a sweep that never settles anything.
                main._in_match_seen[str(sid)] = (
                    time.monotonic() - (main.IN_MATCH_TTL_SEC * 2))
                assert await _sweep(Session) == 1
                assert (await _row(Session, sid))["status"] == "dc_incomplete"
        finally:
            await engine.dispose()
    _drive(body)


# ── Holding the sweep at a chosen statement ──────────────────────────────


class _GateOnStatement:
    """A session wrapper that pauses the sweep at one chosen statement.

    The sweep's discovery SELECT and its locked re-read are two round trips
    with nothing awaitable of OURS in between, and after the lock the liveness
    re-check is a plain synchronous call. Landing a competing commit, or a
    client ping, in one of those gaps is otherwise a race. This holds the sweep
    at the door of (or just past) a named statement so the gap is a place the
    test can stand.

    It is the TEST's wrapper, around the session the test itself hands in:
    production code gets no seam it would have to carry, and the sweep runs
    unmodified (#342 -- a harness that needed the code to grow a hook would be
    proving something about the hook).
    """

    def __init__(self, inner, needle, gate, when="before"):
        self._inner, self._needle, self._gate, self._when = inner, needle, gate, when
        self.fired = False

    async def execute(self, statement, *args, **kwargs):
        hit = not self.fired and self._needle in str(statement)
        if hit:
            self.fired = True
            if self._when == "before":
                await self._gate.wait()
        result = await self._inner.execute(statement, *args, **kwargs)
        if hit and self._when == "after":
            await self._gate.wait()
        return result

    def __getattr__(self, name):          # commit, rollback, begin_nested, ...
        return getattr(self._inner, name)


async def _gated_sweep(Session, gate, needle, when):
    async with Session() as inner:
        return await main._team_dc_fallback_sweep_once(
            _GateOnStatement(inner, needle, gate, when))


LOCK_STATEMENT = "FOR NO KEY UPDATE SKIP LOCKED"


# ── The in-transaction re-check ──────────────────────────────────────────


def test_the_sweep_does_not_clobber_a_series_completed_after_discovery():
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals() as rated:
                assert (await _fallback(Session, sid))["status"] == "deferred"
                await _age_marker(Session, sid, main._DC_FALLBACK_DEFER_SECONDS * 2)

                # Hold the sweep at the door of its locked re-read. Its
                # UNLOCKED discovery SELECT has already run and has already
                # seen 'active'.
                gate = asyncio.Event()
                task = asyncio.create_task(
                    _gated_sweep(Session, gate, LOCK_STATEMENT, "before"))
                await asyncio.sleep(0.5)
                assert not task.done(), "the sweep never reached its locked read"

                # Now a real-totals report takes the row, completes the series
                # WITH ratings, and COMMITS -- so the row is free by the time
                # the sweep locks it. Nothing about the lock saves the series
                # here; only re-reading the predicate inside the transaction
                # does.
                out = await _real_totals(Session, sid)
                assert out["status"] == "completed", out
                assert [c["winner"] for c in rated.calls] == [2]

                gate.set()
                assert await task == 0
                end = await _row(Session, sid)
                assert end["status"] == "completed", dict(end)
                assert end["invalidation_reason"] == "dc_leadforfeit"
                assert len(rated.calls) == 1
        finally:
            await engine.dispose()
    _drive(body)


# ── The lock is never a queue ────────────────────────────────────────────


def test_the_sweep_skips_a_held_row_instead_of_queueing_behind_it():
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals():
                assert (await _fallback(Session, sid))["status"] == "deferred"
                await _age_marker(Session, sid, main._DC_FALLBACK_DEFER_SECONDS * 2)

                # Somebody holds the row: an admin resolution, or the family
                # pick four players just triggered by pressing Start. There is
                # no lock_timeout on the engine and none set in the sweep, so
                # an unqualified lock here is an unbounded wait that starves
                # every other due row in the batch.
                blocker = Session()
                await blocker.execute(
                    text("SELECT id FROM team_series WHERE id = :sid"
                         "  FOR NO KEY UPDATE"), {"sid": sid})

                task = asyncio.create_task(_sweep(Session))
                await asyncio.sleep(2.0)
                finished_while_held = task.done()
                # Release before asserting, so a regression reddens instead of
                # hanging the suite on a lock that is never granted.
                await blocker.rollback()
                await blocker.close()
                settled = await task

                assert finished_while_held, (
                    "the sweep queued behind the holder instead of skipping it")
                assert settled == 0
                assert (await _row(Session, sid))["status"] == "active"

                # NEGATIVE CONTROL: the row really was due. Skipping is a
                # deferral to the next tick, not a drop -- without this half the
                # assertion above would also pass on a sweep that settles
                # nothing at all.
                assert await _sweep(Session) == 1
                assert (await _row(Session, sid))["status"] == "dc_incomplete"
        finally:
            await engine.dispose()
    _drive(body)


# ── Liveness is re-read after the lock is held ───────────────────────────


def test_the_sweep_re_reads_liveness_after_taking_the_lock():
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals():
                assert (await _fallback(Session, sid))["status"] == "deferred"
                await _age_marker(Session, sid, main._DC_FALLBACK_DEFER_SECONDS * 2)

                # Hold the sweep JUST PAST its locked read: the pre-lock veto
                # has already been evaluated and found no evidence.
                gate = asyncio.Event()
                task = asyncio.create_task(
                    _gated_sweep(Session, gate, LOCK_STATEMENT, "after"))
                await asyncio.sleep(0.5)
                assert not task.done(), "the sweep never reached its locked read"

                # While it holds the lock, the four resume and the first
                # in-match ping of the new room lands. The row's COLUMNS are
                # unchanged -- status, marker and dueness all still say settle
                # -- so the in-transaction re-check cannot see this. Only
                # re-reading the veto can.
                main._in_match_touch(str(sid))
                gate.set()
                assert await task == 0
                assert (await _row(Session, sid))["status"] == "active"

                # NEGATIVE CONTROL: the identical interleave with no ping
                # settles. Without it, a sweep that had simply stopped working
                # would pass the half above.
                main._in_match_seen.clear()
                gate2 = asyncio.Event()
                task2 = asyncio.create_task(
                    _gated_sweep(Session, gate2, LOCK_STATEMENT, "after"))
                await asyncio.sleep(0.5)
                gate2.set()
                assert await task2 == 1
                assert (await _row(Session, sid))["status"] == "dc_incomplete"
        finally:
            await engine.dispose()
    _drive(body)


# ── The second refusal: the room a held report could still name ──────────


def test_the_sweep_declines_while_the_stored_room_is_still_young():
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals():
                assert (await _fallback(Session, sid))["status"] == "deferred"
                await _age_marker(Session, sid, main._DC_FALLBACK_DEFER_SECONDS * 2)

                # The series still stores the room its abandoned sitting was
                # played in, issued moments ago. A report held through an
                # assembly would still name that room and the report handler's
                # room fence would still accept it, so the marker's age is not
                # the whole question.
                async with Session() as s:
                    await s.execute(
                        text("UPDATE team_series"
                             "   SET photon_room_id = 'sct-aaaaaaaaaaaa',"
                             "       room_issued_at = clock_timestamp()"
                             " WHERE id = :sid"), {"sid": sid})
                    await s.commit()
                assert await _sweep(Session) == 0
                assert (await _row(Session, sid))["status"] == "active"

                # NEGATIVE CONTROL: age the room past the quiet window and the
                # same row settles, so the refusal above is the room term and
                # not a sweep that stopped working.
                async with Session() as s:
                    await s.execute(
                        text("UPDATE team_series SET room_issued_at ="
                             "  room_issued_at - make_interval(secs => :n)"
                             " WHERE id = :sid"),
                        {"sid": sid,
                         "n": float(main._DC_FALLBACK_ROOM_QUIET_SECONDS + 30)})
                    await s.commit()
                assert await _sweep(Session) == 1
                assert (await _row(Session, sid))["status"] == "dc_incomplete"
        finally:
            await engine.dispose()
    _drive(body)


# ── A revived series does not get settled again ──────────────────────────


def test_an_adopted_series_carries_no_marker_into_the_next_tick():
    """The hosted-lobby Start funnel, which the first cut of this change missed.

    _team_lock_family_pick admits a 'dc_incomplete' row as resumable, so four
    players pressing Start again adopt the settled series back to 'active'. The
    row's DC fields are cleared inline by that handler; the marker is cleared by
    the shared helper, which is what this drives -- the call SITE is bound by
    test_sept16_dc_fallback_shape.py, which counts the revival operation across
    the whole file.
    """
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]

        async def adopt(clear_marker: bool):
            """What both adoption funnels do to the row."""
            async with Session() as s:
                await s.execute(
                    text("""UPDATE team_series
                               SET status = 'active',
                                   dc_team_remaining = NULL,
                                   dc_player_id = NULL,
                                   photon_room_id = NULL,
                                   room_issued_at = NULL,
                                   invalidation_reason = CASE
                                       WHEN invalidation_reason = 'dc_manual_pending'
                                       THEN NULL ELSE invalidation_reason END
                             WHERE id = :sid"""), {"sid": sid})
                if clear_marker:
                    await main._team_clear_dc_fallback_marker(s, sid)
                await s.commit()

        try:
            with _harness_globals():
                assert (await _fallback(Session, sid))["status"] == "deferred"
                await _age_marker(Session, sid, main._DC_FALLBACK_DEFER_SECONDS * 2)
                assert await _sweep(Session) == 1
                assert (await _row(Session, sid))["status"] == "dc_incomplete"

                # NEGATIVE CONTROL FIRST, because it is the bug: adopt WITHOUT
                # clearing the marker and the next tick settles the sitting the
                # four just resumed, attributed to the previous disconnect.
                await adopt(clear_marker=False)
                assert (await _row(Session, sid))["status"] == "active"
                assert await _sweep(Session) == 1
                back = await _row(Session, sid)
                assert back["status"] == "dc_incomplete"
                assert back["invalidation_reason"] == "dc_manual_pending"

                # And with the clear, which is what both funnels call: the row
                # is revived and STAYS revived, tick after tick.
                await adopt(clear_marker=True)
                after = await _row(Session, sid)
                assert after["status"] == "active"
                assert after["dc_fallback_at"] is None
                assert after["dc_fallback_player_id"] is None
                assert after["invalidation_reason"] is None
                assert await _sweep(Session) == 0
                assert await _sweep(Session) == 0
                assert (await _row(Session, sid))["status"] == "active"
        finally:
            await engine.dispose()
    _drive(body)
