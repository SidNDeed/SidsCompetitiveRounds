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
import hashlib
import os
import pathlib
import time
import types
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
DROP TABLE IF EXISTS ovt_series;
DROP TABLE IF EXISTS ffa_lobbies;
DROP TABLE IF EXISTS steam_sessions;
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
    spawn_confirmations INT NOT NULL DEFAULT 0,
    -- Migration 206's frozen team colours. PRE-326 is what this schema is,
    -- not pre-everything: the read-only status route reads these in its one
    -- SELECT, and a harness missing a column the route legitimately expects
    -- would be testing the harness.
    t1_color_name TEXT, t1_color_hex TEXT,
    t2_color_name TEXT, t2_color_hex TEXT
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

-- The two other group tables presence_ping's membership read names. It asks
-- all three kinds in one statement, so a harness without them would fail that
-- statement and test nothing about the team branch; the columns are exactly
-- the ones the read touches.
CREATE TABLE ovt_series (
    id UUID PRIMARY KEY,
    solo_id UUID, duo_a_id UUID, duo_b_id UUID
);

CREATE TABLE ffa_lobbies (
    id UUID PRIMARY KEY,
    member_ids UUID[]
);

-- The session table presence_ping reads twice before its series lock: the
-- session check, and the seat binding that confines an in-match claim to the
-- seat the request's own session names (residual 26). The columns are exactly
-- the ones those reads touch.
CREATE TABLE steam_sessions (
    token_hash TEXT PRIMARY KEY,
    steam_id VARCHAR(20) NOT NULL,
    verified BOOLEAN NOT NULL DEFAULT false,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);
"""


def _token(steam_id):
    """The session token the harness gives one seat. Test-only and unique per
    seat; only its sha256 is stored, as the mint stores it."""
    return "sept16dc-session-" + steam_id


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


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


async def _take_clean_slate() -> None:
    """The per-case reset TAKES the clean slate rather than assuming it (#753).

    A case that dies while one of its sessions holds a row lock -- a mutation
    run that times out mid-interleave, say -- leaves that lock behind, and
    PostgreSQL does not notice a vanished client until it next writes to its
    socket, which can be minutes and outlives the process. Every later case
    would then block on its own DROP TABLE. So every other backend on THIS
    throwaway database is terminated first, and the schema is rebuilt under a
    short lock_timeout, so a DROP that is still blocked fails loudly with a
    lock error instead of hanging the run.

    current_database() and never a name: the DSN is the throwaway cluster's,
    and this statement cannot reach any other database on the server.
    """
    import asyncpg
    conn = await asyncpg.connect(_raw_dsn())
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
            " WHERE datname = current_database() AND pid <> pg_backend_pid()")
        await conn.execute("SET lock_timeout = '5s'")
        await conn.execute(PRE_326_SCHEMA)
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
      process is young and pytest's process is seconds old;
    * the hourly service-account UUID cache is emptied and put back. It is
      module state, so one scenario's fill would otherwise decide whether the
      NEXT scenario's service-subject assertion issues SQL at all -- and one
      scenario below has to stand inside exactly that SQL's gap.
    """
    rated = _Rated()
    old_complete = main._complete_team_series_with_ratings
    old_secret = main.MATCH_HMAC_SECRET
    old_started = main._PROCESS_STARTED_AT
    old_seen = dict(main._in_match_seen)
    old_svc = main._service_player_uuid_cache
    old_svc_at = main._service_uuid_cache_monotonic
    main._complete_team_series_with_ratings = rated
    main.MATCH_HMAC_SECRET = ""
    main._PROCESS_STARTED_AT = time.monotonic() - (main.IN_MATCH_TTL_SEC * 3)
    main._in_match_seen.clear()
    main._service_player_uuid_cache = None
    try:
        assert main._in_match_evidence_trustworthy()
        yield rated
    finally:
        main._complete_team_series_with_ratings = old_complete
        main.MATCH_HMAC_SECRET = old_secret
        main._PROCESS_STARTED_AT = old_started
        main._in_match_seen.clear()
        main._in_match_seen.update(old_seen)
        main._service_player_uuid_cache = old_svc
        main._service_uuid_cache_monotonic = old_svc_at


async def _fresh_series(t2_wins: int = 1):
    """Reset the schema, apply migration 326, seed one active series.

    t2_wins=1 puts the NON-disconnecting team one game up, which is the
    condition under which a real-totals report carrying >=2 points completes
    the series WITH ratings. That is the outcome a fallback must never be able
    to displace, so it is the outcome every ordering below asserts.
    """
    await _take_clean_slate()
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
            # Each seat holds one session of its own, unverified and current:
            # the ordinary client, which pings as the id whose token it holds.
            await s.execute(
                text("INSERT INTO steam_sessions"
                     " (token_hash, steam_id, verified, expires_at)"
                     " VALUES (:th, :s, false, NOW() + INTERVAL '1 day')"),
                {"th": _token_hash(_token(steam)), "s": steam})
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
    far side of the 420 s bound without sleeping for seven minutes."""
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


# ── Ordering 3: both in flight across a real lock wait, in BOTH orders ───


async def _lock_waiters(Session, want, attempts=200):
    """How many backends of this database are waiting on a lock, polled until
    it reaches `want` or the attempts run out -- the observed count either
    way, so a caller asserts on what the server said and not on a timer."""
    seen = -1
    for _ in range(attempts):
        async with Session() as s:
            seen = (await s.execute(text(
                "SELECT count(*) FROM pg_stat_activity"
                " WHERE datname = current_database()"
                "   AND wait_event_type = 'Lock'"))).scalar()
        if seen >= want:
            return seen
        await asyncio.sleep(0.05)
    return seen


def test_both_in_flight_across_the_lock_wait_ends_rated():
    """Both reports queue on the series lock, and BOTH arrival orders run.

    A third session holds the series row, so the two reports wait on the same
    lock. A contended row is granted to its waiters in the order they began
    to wait: the first waiter holds the tuple lock while it waits for the
    holder, and the second waits behind it. So the order is SET, not left to
    chance: the second report starts only once the first is seen waiting in
    pg_stat_activity, and each order runs on its own fresh series.

    An earlier form started both at once and let the scheduler decide, so each
    run covered one order, picked by timing. A mutation that only the
    fallback-first order exposes was then killed on some runs and not on
    others, and a control set whose kill set does not repeat is not a control
    set (#753). Either order must end rated, with the rating path run once.
    """
    async def one_order(first):
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        second = "real totals" if first == "fallback" else "fallback"
        start = {"fallback": lambda: _fallback(Session, sid),
                 "real totals": lambda: _real_totals(Session, sid)}
        try:
            with _harness_globals() as rated:
                blocker = Session()
                await blocker.execute(
                    text("SELECT id FROM team_series WHERE id = :sid"
                         "  FOR NO KEY UPDATE"), {"sid": sid})
                t_first = asyncio.create_task(start[first]())
                assert await _lock_waiters(Session, 1) == 1, (
                    first + ": the first report never queued on the lock")
                t_second = asyncio.create_task(start[second]())
                assert await _lock_waiters(Session, 2) == 2, (
                    first + ": the second report never queued behind it")
                await blocker.rollback()
                await blocker.close()
                got = {first: await t_first, second: await t_second}

                # In either order the series is rated and the rating path ran
                # exactly once.
                end = await _row(Session, sid)
                assert end["status"] == "completed", (first, got, dict(end))
                assert [c["winner"] for c in rated.calls] == [2], first
                # And the fallback's own answer is one of the two dispositions
                # that cannot decide anything.
                fb = got["fallback"]
                assert (fb.get("status") == "deferred"
                        or fb.get("ignored") is True), (first, fb)
        finally:
            await engine.dispose()

    async def body():
        await one_order("fallback")
        await one_order("real totals")
    _drive(body)


# ── Ordering 4: a sweep tick lands between the two reports ───────────────


def test_a_sweep_between_the_reports_does_not_settle_inside_the_bound():
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals() as rated:
                assert (await _fallback(Session, sid))["status"] == "deferred"
                # The marker is seconds old; the bound is 420.
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
    with nothing awaitable of OURS in between, and the post-lock liveness veto
    is read synchronously while the settlement statement's parameters are
    built. Landing a competing commit, or a client ping, in one of those gaps
    is otherwise a race. This holds the sweep at the door of (or just past) a
    named statement so the gap is a place the test can stand.

    Evidence reaches a HELD sweep's gaps below in one way only: through
    `main.presence_ping`, the real publisher, with its own lock and its own
    membership read, asking whether evidence can ARRIVE at a moment the veto
    has already passed and what becomes of a ping that tries. A direct call
    into the evidence map (`main._in_match_touch`) stands for a ping that has
    already COMPLETED, which production's one publisher can do before a
    sweep holds the series lock or after it commits -- never while it holds
    it, because the publisher is then waiting for that commit. Two scenarios
    here once wrote the map directly inside a held window and asserted the
    opposite of what production does (the round-8 cold lens), and the shape
    suite's test_no_ordering_scenario_writes_evidence_inside_a_held_sweep
    now refuses that shape anywhere in this file. The round-7c HIGH was an
    arrival question this file had only asked with a direct write.

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


# ── The deleted second refusal: the sweep does not read the room clock ───


def test_the_sweep_settles_on_the_bound_whatever_the_room_clock_says():
    """Round 4's 214 s room-quiet term is gone, and this is what that means.

    That term was meant to be a second, independent refusal. It could not
    refuse anything: an ordinary room is stamped when it is ISSUED, which is
    before the sitting that produces the marker, so a marker past 420 s always
    sat on a room past 214 s; and a continuation series carries a real room
    with a NULL room_issued_at, which made the arm true on arrival. A check
    that cannot fail is worse than no check (#342, #441).

    The two rows below are the two shapes production ordinarily produces.
    Both settle on the bound alone. The third -- a room stamped AFTER the
    marker -- is the shape the round-4 test manufactured to make the term
    look load-bearing. Production reaches it only when a clear fails:
    issuing a room ATTEMPTS the marker clear in the same function (asserted
    file-wide in the shape suite), and that attempt swallows what it
    raises, so a failed clear leaves exactly this row. It settles on the
    bound too, which is the whole content of the deletion.
    """
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals():
                # (a) ORDINARY: room issued before the sitting, so it is at
                # least as old as the marker.
                assert (await _fallback(Session, sid))["status"] == "deferred"
                async with Session() as s:
                    await s.execute(
                        text("UPDATE team_series"
                             "   SET photon_room_id = 'sct-aaaaaaaaaaaa',"
                             "       room_issued_at = clock_timestamp()"
                             "        - make_interval(secs => 900)"
                             " WHERE id = :sid"), {"sid": sid})
                    await s.commit()
                await _age_marker(Session, sid, main._DC_FALLBACK_DEFER_SECONDS * 2)
                assert await _sweep(Session) == 1
                assert (await _row(Session, sid))["status"] == "dc_incomplete"

            # (b) CONTINUATION: a real room, no room_issued_at at all.
            engine2, Session2, ids2 = await _fresh_series()
            sid2 = ids2["sid"]
            try:
                with _harness_globals():
                    assert (await _fallback(Session2, sid2))["status"] == "deferred"
                    async with Session2() as s:
                        await s.execute(
                            text("UPDATE team_series"
                                 "   SET photon_room_id = 'sct-bbbbbbbbbbbb',"
                                 "       room_issued_at = NULL"
                                 " WHERE id = :sid"), {"sid": sid2})
                        await s.commit()
                    await _age_marker(Session2, sid2,
                                      main._DC_FALLBACK_DEFER_SECONDS * 2)
                    assert await _sweep(Session2) == 1
                    assert (await _row(Session2, sid2))["status"] == "dc_incomplete"
            finally:
                await engine2.dispose()

            # (c) The manufactured reverse ordering: a room stamped NOW on a
            # row whose marker is old. Under the deleted term this refused;
            # now it settles. Production reaches this row only when the
            # room-issue clear fails: every site that stamps room_issued_at
            # ATTEMPTS the clear in the same function (the structural suite
            # counts that), and the attempt swallows what it raises.
            engine3, Session3, ids3 = await _fresh_series()
            sid3 = ids3["sid"]
            try:
                with _harness_globals():
                    assert (await _fallback(Session3, sid3))["status"] == "deferred"
                    await _age_marker(Session3, sid3,
                                      main._DC_FALLBACK_DEFER_SECONDS * 2)
                    async with Session3() as s:
                        await s.execute(
                            text("UPDATE team_series"
                                 "   SET photon_room_id = 'sct-cccccccccccc',"
                                 "       room_issued_at = clock_timestamp()"
                                 " WHERE id = :sid"), {"sid": sid3})
                        await s.commit()
                    assert await _sweep(Session3) == 1
                    assert (await _row(Session3, sid3))["status"] == "dc_incomplete"
            finally:
                await engine3.dispose()
        finally:
            await engine.dispose()
    _drive(body)


# ── The read-only status route writes nothing ────────────────────────────


class _RecordStatements:
    """Every statement the connection executes, in order.

    An engine-level listener rather than a wrapper around the session: it sees
    what actually reaches the cursor, including a SAVEPOINT or a statement
    issued by a helper the route calls, neither of which a session wrapper
    would catch.
    """

    def __init__(self, engine):
        from sqlalchemy import event
        self.seen = []
        self._engine = engine.sync_engine

        def _on(conn, cursor, statement, params, context, executemany):
            self.seen.append(" ".join(str(statement).split()))
        self._fn = _on
        event.listen(self._engine, "before_cursor_execute", _on)

    def close(self):
        from sqlalchemy import event
        event.remove(self._engine, "before_cursor_execute", self._fn)

    def non_selects(self):
        return [s for s in self.seen if not s.upper().startswith("SELECT")]


def test_the_read_only_status_route_issues_only_selects():
    """The route has no mutating arm -- measured, with its own positive control.

    The series is put in the exact state under which the MUTATING state GET
    cancels a series and reconciles its bets: 'active', fewer than four
    spawn-confirms, past the assembly deadline, no live-game evidence. The
    read-only route is called first and must leave the row alone while issuing
    nothing but SELECTs. Then the state GET is called on the same row under the
    same recorder: it records an UPDATE and cancels the row. That second half
    is the control -- without it, a recorder that had silently stopped
    listening would pass the first half (#391).
    """
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        rec = _RecordStatements(engine)
        try:
            with _harness_globals():
                async with Session() as s:
                    await s.execute(
                        text("UPDATE team_series"
                             "   SET created_at = clock_timestamp()"
                             "        - make_interval(secs => :n),"
                             "       room_issued_at = NULL,"
                             "       spawn_confirmations = 0"
                             " WHERE id = :sid"),
                        {"sid": sid,
                         "n": float(main._ASSEMBLY_DEADLINE_SECONDS * 3)})
                    await s.commit()

                rec.seen.clear()
                async with Session() as s:
                    out = await main.team_series_status_readonly(
                        series_id=str(sid), db=s)
                assert out["readonly"] is True
                assert out["status"] == "active"
                # Past the deadline and reported as such -- the route SEES the
                # condition the state GET acts on, and does not act on it.
                assert out["age_seconds"] > main._ASSEMBLY_DEADLINE_SECONDS
                assert rec.non_selects() == [], rec.non_selects()
                assert (await _row(Session, sid))["status"] == "active"

                # POSITIVE CONTROL for the recorder and for the row's state.
                calls = []

                async def _fake_reconcile(db, series_uuid, reason):
                    calls.append(reason)
                old = main._reconcile_team_series_bets
                main._reconcile_team_series_bets = _fake_reconcile
                try:
                    rec.seen.clear()
                    async with Session() as s:
                        state = await main.team_series_state(
                            series_id=str(sid), db=s)
                finally:
                    main._reconcile_team_series_bets = old
                assert state["status"] == "canceled", state
                assert calls == ["assembly_timeout"], calls
                assert any(s.upper().startswith("UPDATE") for s in rec.seen), (
                    "the recorder saw no write on a call that demonstrably "
                    "wrote -- it is not measuring anything")
                assert (await _row(Session, sid))["status"] == "canceled"
        finally:
            rec.close()
            await engine.dispose()
    _drive(body)


async def _status(Session, sid):
    async with Session() as s:
        return await main.team_series_status_readonly(series_id=str(sid), db=s)


# The three field names are the CONTRACT's, and they are written here once so
# a rename on one lane cannot quietly become a rename on both.
BANNER_FIELDS = ("dc_deferred", "dc_deferred_seconds_remaining",
                 "dc_deferred_bound_seconds")


def test_the_status_route_carries_the_deferral_state_it_read():
    """The banner's whole input, read off the live route against a real row.

    Every assertion below is of the form "change the ROW, and the field
    changes with it": a field that reported a plausible constant would pass a
    presence check and fail every one of these (#342). The last block re-runs
    the no-write measurement on the widened SELECT, because a route that grew
    a column is a route whose statements have to be counted again (#308).
    """
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        rec = _RecordStatements(engine)
        try:
            with _harness_globals():
                bound = main._DC_FALLBACK_DEFER_SECONDS

                # 1. No marker: present, false, floored, and the bound echoed
                #    from the one constant rather than from a literal.
                out = await _status(Session, sid)
                for f in BANNER_FIELDS:
                    assert f in out, (f, sorted(out))
                assert out["dc_deferred"] is False, out
                assert out["dc_deferred_seconds_remaining"] == 0, out
                assert out["dc_deferred_bound_seconds"] == bound, out
                assert isinstance(out["dc_deferred_seconds_remaining"], int)
                assert isinstance(out["dc_deferred_bound_seconds"], int)
                assert isinstance(out["dc_deferred"], bool)

                # 2. A parked report puts the row in the deferral window.
                assert (await _fallback(Session, sid))["status"] == "deferred"
                out = await _status(Session, sid)
                assert out["dc_deferred"] is True, out
                left = out["dc_deferred_seconds_remaining"]
                assert bound - 30 <= left <= bound, left

                # 3. DERIVED FROM THE ROW: age the marker and the remaining
                #    time falls by the same amount. A field computed from
                #    anything other than dc_fallback_at cannot follow this.
                await _age_marker(Session, sid, 120)
                after = (await _status(Session, sid))["dc_deferred_seconds_remaining"]
                assert 110 <= (left - after) <= 130, (left, after)

                # 4. Past the bound, before any tick settles it: still
                #    deferred, and the remaining time is FLOORED at 0 rather
                #    than going negative. This is the state the banner must
                #    still render, which is why its predicate is the flag and
                #    never "remaining > 0".
                await _age_marker(Session, sid, bound)
                out = await _status(Session, sid)
                assert out["dc_deferred"] is True, out
                assert out["dc_deferred_seconds_remaining"] == 0, out
                assert (await _row(Session, sid))["marker_age"] > bound

                # 5. Once the row is out of the statuses the sweep admits, the
                #    marker is inert and the route says so -- even though the
                #    columns still carry it.
                async with Session() as s:
                    await s.execute(
                        text("UPDATE team_series SET status = 'completed'"
                             " WHERE id = :sid"), {"sid": sid})
                    await s.commit()
                row = await _row(Session, sid)
                assert row["dc_fallback_at"] is not None, row
                out = await _status(Session, sid)
                assert out["dc_deferred"] is False, out
                assert out["dc_deferred_seconds_remaining"] == 0, out

                # 6. The widened path still writes nothing, with the same
                #    positive control the narrower one had: the recorder is
                #    shown to see an UPDATE on a call that demonstrably writes.
                rec.seen.clear()
                await _status(Session, sid)
                assert rec.non_selects() == [], rec.non_selects()
                rec.seen.clear()
                async with Session() as s:
                    await s.execute(
                        text("UPDATE team_series SET status = 'completed'"
                             " WHERE id = :sid"), {"sid": sid})
                    await s.commit()
                assert any(s.upper().startswith("UPDATE") for s in rec.seen), (
                    "the recorder saw no write on a statement that "
                    "demonstrably wrote -- it is not measuring anything")
        finally:
            rec.close()
            await engine.dispose()
    _drive(body)


def test_the_status_route_is_a_different_path_from_the_mutating_one():
    """Both routes exist, on different paths, and only one of them writes.

    The capability is proven per RESPONSE by the box that answered: a box
    without this route has no handler for the path and answers 404, which the
    client treats as no answer. Read off the live app rather than the source,
    so a route that failed to register cannot pass.
    """
    paths = {r.path: r for r in main.app.routes if hasattr(r, "path")}
    assert "/api/v1/team/series/{series_id}/status" in paths
    assert "/api/v1/team/series/{series_id}/state" in paths
    ro = paths["/api/v1/team/series/{series_id}/status"]
    assert set(ro.methods) == {"GET"}, ro.methods
    # And the deleted flag is not a parameter of either one any more.
    import inspect
    for p in ("/api/v1/team/series/{series_id}/status",
              "/api/v1/team/series/{series_id}/state"):
        sig = inspect.signature(paths[p].endpoint)
        assert "lifecycle" not in sig.parameters, (p, list(sig.parameters))


def test_every_settling_answer_says_it_was_not_deferred():
    """W23 is a measurement, not an absence (r4 client L4).

    Absent from a 200, "deferred" means the box that answered predates the
    flag. Present and false, it means this build did not PARK the report --
    which is a statement about this call and not about the series: the
    settled-row exit below answers false for a row something else had already
    terminated, and the next test drives the two fences, which answer false
    and leave the series open. The client cannot tell false from absent
    unless every non-deferring exit carries the field, so they all do.
    """
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals():
                # A settling report: the lead-forfeit branch.
                out = await _real_totals(Session, sid)
                assert out["status"] == "completed"
                assert out["deferred"] is False, out

                # And the settled-row exit a later report takes.
                again = await _real_totals(Session, sid)
                assert again["ignored"] is True
                assert again["deferred"] is False, again

            # A deferral still says true.
            engine2, Session2, ids2 = await _fresh_series()
            try:
                with _harness_globals():
                    d = await _fallback(Session2, ids2["sid"])
                    assert d["deferred"] is True, d
            finally:
                await engine2.dispose()
        finally:
            await engine.dispose()
    _drive(body)


def test_a_fenced_report_answers_not_deferred_and_leaves_the_series_open():
    """"deferred": false is not a statement that the call settled anything.

    Three of the five non-deferring exits decide nothing. The settled-row exit
    is covered above; the two room fences are here, and they are the ones a
    reader is most likely to get wrong, because they answer false about a
    series that is STILL ACTIVE and still expecting a real-totals report. A
    guard built on "false means this build settled it" would close it.

    Both fences are driven against the live schema rather than read off the
    source: the source test pins the file's wording, and this pins what the
    endpoint actually answers and what it leaves in the row.
    """
    async def body():
        # 1. The stored-room fence: the report names a room this series does
        #    not own -- its dead predecessor.
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        try:
            with _harness_globals():
                async with Session() as s:
                    await s.execute(
                        text("UPDATE team_series"
                             "   SET photon_room_id = 'sct-aaaaaaaaaaaa'"
                             " WHERE id = :sid"), {"sid": sid})
                    await s.commit()
                async with Session() as s:
                    out = await main.team_series_report_dc(
                        series_id=str(sid), reporter_steam_id=SID_T2A,
                        dc_player_steam_id=SID_T1A, t1_points_total=3,
                        t2_points_total=4, photon_room_id="sct-zzzzzzzzzzzz",
                        is_fallback=False, hmac_sig="", db=s)
                assert out["ignored"] is True, out
                assert out["reason"] == "dc_room_mismatch", out
                assert out["deferred"] is False, out
                row = await _row(Session, sid)
                assert row["status"] == "active", row
                assert row["dc_player_id"] is None, row
        finally:
            await engine.dispose()

        # 2. The post-relock fence: a ROOMLESS report inside the ten minutes
        #    after a resume, which is the held-report case the fence exists
        #    for. The four are playing; the row must stay open.
        engine2, Session2, ids2 = await _fresh_series()
        sid2 = ids2["sid"]
        try:
            with _harness_globals():
                async with Session2() as s:
                    await s.execute(
                        text("UPDATE team_series"
                             "   SET relocked_at = clock_timestamp()"
                             " WHERE id = :sid"), {"sid": sid2})
                    await s.commit()
                out = await _real_totals(Session2, sid2)
                assert out["ignored"] is True, out
                assert out["reason"] == "dc_after_resume", out
                assert out["deferred"] is False, out
                row = await _row(Session2, sid2)
                assert row["status"] == "active", row
                assert row["dc_player_id"] is None, row
        finally:
            await engine2.dispose()
    _drive(body)


# ── The publisher cannot land between the veto and the write ────────────


SETTLE_STATEMENT = "SET status = 'dc_incomplete'"


class _PingRequest:
    """The two attributes presence_ping reads off its request, and no more.

    `token` is the X-Session-Token the request carries, or None for none. The
    ordinary scenario passes the pinging seat's own token, as the client does:
    the route's seat binding refuses an in-match claim for any seat the
    request's session does not name (residual 26)."""

    def __init__(self, token=None):
        self.state = types.SimpleNamespace()
        self.headers = {} if token is None else {"X-Session-Token": token}


@contextlib.contextmanager
def _presence_harness():
    """Let the REAL presence_ping run against this file's schema.

    * the Steam-session check is made to pass: authentication is not what
      these scenarios measure. The seat binding after it is NOT replaced: each
      ping below carries its own seat's session token, which the harness
      schema holds, so the binding runs for real and passes as it does for
      the client;
    * the lease renewal is RECORDED instead of executed: the harness has no
      lease table, and the record is how a scenario proves the ping got as far
      as a verified membership decision rather than failing early and
      publishing nothing for an unrelated reason.

    Everything the publication decision rests on -- the series lock, the
    membership read and the status it reads -- is the real route against the
    real database. The route's last_seen stamp fails against this schema and
    the route's own guard swallows that, exactly as it does in production for
    any stamp failure; nothing below depends on it.
    """
    renewals = []
    old_check = main._check_steam_session
    old_renew = main._lease_renew

    async def _session_ok(request, steam_id, db):
        return None

    async def _renew(db, pid, mode, gid, ttl, **kwargs):
        renewals.append((str(pid), mode, str(gid)))

    main._check_steam_session = _session_ok
    main._lease_renew = _renew
    try:
        yield renewals
    finally:
        main._check_steam_session = old_check
        main._lease_renew = old_renew


async def _ping(Session, steam_id, sid, token="own"):
    """One in-match presence ping through the real route.

    By default the request carries the claimed seat's own session token, as
    the client's does; `token` names another token, or None for none."""
    async with Session() as s:
        return await main.presence_ping(
            request=_PingRequest(_token(steam_id) if token == "own" else token),
            steam_id=steam_id, in_match=str(sid), db=s)


def test_a_ping_queued_between_the_veto_and_the_write_publishes_nothing_the_settlement_missed():
    """The round-7c HIGH, as a run and not as a shape.

    The sweep read its post-lock veto -- no evidence -- and is held at the door
    of its settlement UPDATE, still holding the series lock. A seat of this
    series now pings, claiming to be in its game. Before the fix the ping's
    membership read was a plain SELECT: it saw the row still open, published
    evidence, and the sweep then committed a settlement that evidence never
    reached -- the stale publication. With the fix the ping takes FOR SHARE on
    the series row before that read, so it waits for the sweep's commit, finds
    the row settled, and publishes nothing.

    THE PROPERTY is that evidence for a series is never published in a window
    the settlement's veto has already passed. It is asserted in three parts:
    nothing was published while the write was held; the settlement happened
    (so the first part is not a sweep that simply stopped); and the ping did
    reach a verified membership decision -- its lease renewal is recorded -- so
    "nothing published" is the route declining and not the route failing.
    """
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        key = str(sid)
        try:
            with _harness_globals(), _presence_harness() as renewals:
                assert (await _fallback(Session, sid))["status"] == "deferred"
                await _age_marker(Session, sid, main._DC_FALLBACK_DEFER_SECONDS * 2)

                gate = asyncio.Event()
                sweep = asyncio.create_task(
                    _gated_sweep(Session, gate, SETTLE_STATEMENT, "before"))
                await asyncio.sleep(0.5)
                assert not sweep.done(), (
                    "the sweep never reached its settlement write")
                assert key not in main._in_match_seen

                ping = asyncio.create_task(_ping(Session, SID_T1B, sid))
                await asyncio.sleep(1.0)
                published_while_held = key in main._in_match_seen
                ping_waited = not ping.done()

                gate.set()
                settled = await asyncio.wait_for(sweep, 15)
                await asyncio.wait_for(ping, 15)
                end = await _row(Session, sid)

                assert not published_while_held, (
                    "a presence ping published in-match evidence for this "
                    "series between the sweep's veto read and its settlement "
                    "write -- the stale publication")
                assert settled == 1, settled
                assert end["status"] == "dc_incomplete", dict(end)
                assert key not in main._in_match_seen, (
                    "evidence was published for a series already settled")
                assert ping_waited, (
                    "the ping finished while the sweep held the series lock")
                assert renewals == [(str(ids["t1b"]), "team", key)], renewals
        finally:
            await engine.dispose()
    _drive(body)


def test_a_ping_before_the_sweep_takes_its_lock_is_published_and_vetoes_it():
    """The other direction, and the negative control of the test above (#391).

    The same real ping, delivered while the sweep is held at the door of its
    LOCKED re-read -- its pass-1 filter has already run and found nothing, and
    it holds no lock yet. Nothing makes the ping wait, so it publishes, and the
    settlement statement's veto reads that evidence and refuses in SQL. Without
    this half, the test above would also pass on a route that never publishes
    at all.
    """
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        key = str(sid)
        try:
            with _harness_globals(), _presence_harness() as renewals:
                assert (await _fallback(Session, sid))["status"] == "deferred"
                await _age_marker(Session, sid, main._DC_FALLBACK_DEFER_SECONDS * 2)

                gate = asyncio.Event()
                sweep = asyncio.create_task(
                    _gated_sweep(Session, gate, LOCK_STATEMENT, "before"))
                await asyncio.sleep(0.5)
                assert not sweep.done(), "the sweep never reached its locked read"

                await asyncio.wait_for(_ping(Session, SID_T1B, sid), 15)
                assert key in main._in_match_seen, (
                    "an unobstructed ping from a member published nothing")
                assert renewals == [(str(ids["t1b"]), "team", key)], renewals

                gate.set()
                assert await asyncio.wait_for(sweep, 15) == 0
                end = await _row(Session, sid)
                assert end["status"] == "active", dict(end)
                assert end["invalidation_reason"] is None
        finally:
            await engine.dispose()
    _drive(body)


# ── A heartbeat after the lock grant is ordered after the settlement ─────


SERVICE_LOOKUP_STATEMENT = "SELECT id::text FROM players"
DECLINED_LINE = "[PRESENCE] in_match evidence not published"


def _post_lock_window(capsys, needle):
    """One real ping delivered while the sweep is held just past `needle`.

    Shared by the two windows after the lock grant, which differ only in
    where the sweep stands. Returns nothing; asserts the whole outcome.
    """
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        key = str(sid)
        try:
            with _harness_globals(), _presence_harness() as renewals:
                assert (await _fallback(Session, sid))["status"] == "deferred"
                await _age_marker(Session, sid, main._DC_FALLBACK_DEFER_SECONDS * 2)
                # Cold cache, so the service-subject assertion really puts
                # its SELECT on the wire whichever window is being held.
                main._service_player_uuid_cache = None

                gate = asyncio.Event()
                sweep = asyncio.create_task(
                    _gated_sweep(Session, gate, needle, "after"))
                await asyncio.sleep(0.5)
                assert not sweep.done(), (
                    "the sweep never reached the statement it is held past: "
                    + needle)
                assert key not in main._in_match_seen

                ping = asyncio.create_task(_ping(Session, SID_T1B, sid))
                await asyncio.sleep(1.0)
                ping_waited = not ping.done()
                published_while_held = key in main._in_match_seen

                gate.set()
                settled = await asyncio.wait_for(sweep, 15)
                await asyncio.wait_for(ping, 15)
                end = await _row(Session, sid)

                assert ping_waited, (
                    "the ping finished while the sweep held the series lock")
                assert not published_while_held, (
                    "a presence ping published in-match evidence for this "
                    "series while the sweep held its lock")
                assert settled == 1, settled
                assert end["status"] == "dc_incomplete", dict(end)
                assert end["invalidation_reason"] == "dc_manual_pending"
                assert key not in main._in_match_seen, (
                    "evidence was published for a series already settled")
                # The ping reached a verified membership decision: "nothing
                # published" is the route declining, not the route failing.
                assert renewals == [(str(ids["t1b"]), "team", key)], renewals
        finally:
            await engine.dispose()
    _drive(body)
    assert DECLINED_LINE in capsys.readouterr().out, (
        "the route never said it declined the publication")


def test_a_ping_after_the_lock_is_granted_is_ordered_after_the_settlement(capsys):
    """A heartbeat that arrives once the sweep holds the lock waits for it.

    The sweep has taken FOR NO KEY UPDATE on the series row and passed its
    locked re-read -- status, marker and dueness all say settle -- and is held
    just past that read. A seat of this series now pings through the real
    route. The route takes FOR SHARE on the same row before its membership
    read, FOR SHARE conflicts with the sweep's lock, so the ping WAITS; when
    the sweep commits, the ping reads the row as the sweep left it -- settled
    -- and publishes nothing. A heartbeat that arrives after the lock grant is
    ordered after the settlement: the row settles, the evidence is dropped,
    and the ping still reaches its membership decision and renews its lease.

    Until the round-8 cold lens this window was driven by a direct write into
    the evidence map, with the row asserted to stay active. No production
    caller can put evidence there while the sweep holds the lock, because the
    one publisher is waiting; so the test asserted the opposite of what
    production does, and a publisher with no lock at all (mutation H1-b) left
    it green. Through the real route it is RED under H1-b, H1-d and H1-e.

    ITS NEGATIVE CONTROL is the same ping delivered BEFORE the lock is
    granted, test_a_ping_before_the_sweep_takes_its_lock_is_published_and_vetoes_it:
    nothing makes that ping wait, it publishes, and the settlement statement's
    veto refuses on it. Without that pairing this test would also pass on a
    route that never publishes; the recorded renewal and the route's own
    declined line make "nothing published" a decision the route took.
    """
    _post_lock_window(capsys, LOCK_STATEMENT)


def test_a_ping_during_the_service_subject_lookup_is_ordered_after_the_settlement(capsys):
    """The round-4 HIGH's window, asked of the real publisher.

    Round 4 ran the awaited service-subject lookup AFTER the post-lock veto,
    and on a cold or hourly-expired cache that lookup issues its own SELECT.
    The concern was a presence ping running to completion inside that await
    and publishing evidence the veto had already missed. So the sweep is held
    just past that SELECT, with the lock held, and a seat pings through the
    real route. It cannot run to completion there: its FOR SHARE waits for
    the sweep's commit, and it then reads the settled row and publishes
    nothing. The ping is ordered after the settlement, as in the test above.

    That is also why the lookup's position relative to the veto read is not
    something a run can see any more. Mutation L moves the lookup back between
    the veto read and the write; under the lock discipline that changes no
    outcome, so L is scored on the structural check that holds the
    integrator's statement shape, and THIS test is the inert test the
    mutation runner requires to stay GREEN under L. Until the round-8 cold
    lens this window was driven by a direct write into the evidence map, with
    the row asserted to stay active, which no production caller can do there.
    """
    _post_lock_window(capsys, SERVICE_LOOKUP_STATEMENT)


# ── The publisher publishes under its lock, not after releasing it ───────


class _HoldAfterCommit:
    """A session wrapper that holds a ping just after its FIRST commit.

    presence_ping's first commit is the one that releases its series lock;
    the status read, the membership read and the publication all come before
    it. Holding the ping there turns the gap between "the lock is released"
    and "whatever the route does next" into a place the test can stand. The
    route runs unmodified; the wrapper is the test's, around a session the
    test hands in, as with _GateOnStatement.
    """

    def __init__(self, inner, gate, reached):
        self._inner, self._gate, self._reached = inner, gate, reached
        self.fired = False

    async def commit(self):
        await self._inner.commit()
        if not self.fired:
            self.fired = True
            self._reached.set()
            await self._gate.wait()

    def __getattr__(self, name):          # execute, rollback, ...
        return getattr(self._inner, name)


def test_a_pings_evidence_is_in_the_map_before_its_series_lock_is_released():
    """The route decides under FOR SHARE and publishes under it too.

    The touch comes before the commit that releases the series lock. Here the
    real ping is held just after that commit -- lock released, lease renewal
    not yet run -- and a whole sweep pass runs in the gap. With the touch
    before the commit, the evidence is already in the map when the lock is
    released: the sweep's pass-1 filter reads it and the row stays open. With
    the commit moved above the touch (mutation H1-f), a sweep could take the
    lock the ping had just released, read no evidence and settle, and the
    ping would then publish to a series the settlement never saw. H1-f was
    killed only by the structural publisher check until the round-8 cold
    lens asked for a run; this is that run.

    NEGATIVE CONTROL (#391): once the ping has finished and its evidence is
    aged past IN_MATCH_TTL_SEC, the same row settles on the next pass, so the
    refusal above is the evidence and not a sweep that stopped working.
    """
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        key = str(sid)
        try:
            with _harness_globals(), _presence_harness() as renewals:
                assert (await _fallback(Session, sid))["status"] == "deferred"
                await _age_marker(Session, sid, main._DC_FALLBACK_DEFER_SECONDS * 2)

                gate, reached = asyncio.Event(), asyncio.Event()

                async def held_ping():
                    async with Session() as s:
                        return await main.presence_ping(
                            request=_PingRequest(_token(SID_T1B)),
                            steam_id=SID_T1B, in_match=key,
                            db=_HoldAfterCommit(s, gate, reached))

                ping = asyncio.create_task(held_ping())
                try:
                    await asyncio.wait_for(reached.wait(), 15)
                    published_before_release = key in main._in_match_seen
                    settled = await _sweep(Session)
                    during = await _row(Session, sid)
                finally:
                    gate.set()
                await asyncio.wait_for(ping, 15)

                assert published_before_release, (
                    "the ping released its series lock before publishing, so "
                    "a sweep pass could run in between and settle")
                assert settled == 0, settled
                assert during["status"] == "active", dict(during)
                assert renewals == [(str(ids["t1b"]), "team", key)], renewals

                # NEGATIVE CONTROL: the same row, the evidence aged out.
                main._in_match_seen[key] = (
                    time.monotonic() - (main.IN_MATCH_TTL_SEC * 2))
                assert await _sweep(Session) == 1
                assert (await _row(Session, sid))["status"] == "dc_incomplete"
        finally:
            await engine.dispose()
    _drive(body)


# ── An in-match claim acts only for the requester's own seat (residual 26) ─


SOFT_FAIL_LINE = "[STEAM-AUTH] soft-fail path="
SEAT_REFUSED_LINE = "[PRESENCE] in_match claim refused, not the requester's own seat"


@contextlib.contextmanager
def _seat_harness(monkeypatch):
    """The REAL session check on its soft-fail branch, the renewal recorded.

    Nothing about authentication is replaced here, unlike _presence_harness:
    the session check reads this schema's session table and, with both of its
    switches removed from this process's environment for the scenario, takes
    the soft-fail branch -- logs one line and returns -- which is the branch
    residual 26 names. The lease renewal is recorded, as there, because the
    harness has no lease table and the record is the evidence of what the
    route renewed and for whom.
    """
    monkeypatch.delenv("STEAM_AUTH_ENFORCE", raising=False)
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)
    renewals = []
    old_renew = main._lease_renew

    async def _renew(db, pid, mode, gid, ttl, **kwargs):
        renewals.append((str(pid), mode, str(gid)))

    main._lease_renew = _renew
    try:
        yield renewals
    finally:
        main._lease_renew = old_renew


async def _set_session(Session, steam_id, verified=None, expired=False):
    """Change one seat's harness session in place."""
    async with Session() as s:
        if verified is not None:
            await s.execute(
                text("UPDATE steam_sessions SET verified = :v WHERE steam_id = :s"),
                {"v": verified, "s": steam_id})
        if expired:
            await s.execute(
                text("UPDATE steam_sessions"
                     "   SET expires_at = NOW() - INTERVAL '1 hour'"
                     " WHERE steam_id = :s"), {"s": steam_id})
        await s.commit()


# Every request shape that does NOT carry the claimed seat's own session. Each
# claims SID_T1A, a roster member of the series; where a session rides along
# it is SID_T1B's, another member of the same series. (id, token, verified)
NOT_OWN_SEAT = (
    ("another-seat-unverified", "t1b", False),
    ("another-seat-verified", "t1b", True),
    ("no-session", None, False),
    ("token-no-session-carries", "unknown", False),
)


@pytest.mark.parametrize("carrier,verified", [s[1:] for s in NOT_OWN_SEAT],
                         ids=[s[0] for s in NOT_OWN_SEAT])
def test_a_soft_fail_ping_claiming_another_seat_publishes_and_renews_nothing(
        monkeypatch, capsys, carrier, verified):
    """R8-L8, residual 26: a claim for a seat the request does not hold is refused.

    On the session check's soft-fail branch the check returns without binding
    the claimed steam_id to anything, so before this round a request could name
    another roster member, publish destruction-veto evidence for that member's
    series and renew that member's lease. The route now compares the claim with
    the seat the request's own session names and refuses any other before the
    series lock. Four shapes, one outcome: nothing is published for the series,
    no lease is renewed for anyone, the series is untouched, and the route says
    why. The soft-fail line proves the scenario stood on the branch the residual
    names rather than on an armed check that would have refused anyway.

    ITS NEGATIVE CONTROL is the next test: the same route and harness, a claim
    for the seat the request's session names, published and renewed. Without
    it, this test would also pass on a route that never publishes at all.
    """
    token = {"t1b": _token(SID_T1B), "unknown": "sept16dc-session-unknown",
             None: None}[carrier]

    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        key = str(sid)
        try:
            with _harness_globals(), _seat_harness(monkeypatch) as renewals:
                if verified:
                    await _set_session(Session, SID_T1B, verified=True)
                await asyncio.wait_for(
                    _ping(Session, SID_T1A, sid, token=token), 15)
                assert key not in main._in_match_seen, (
                    "a claim for another seat published in-match evidence")
                assert renewals == [], (
                    "a claim for another seat renewed a lease", renewals)
                assert (await _row(Session, sid))["status"] == "active"
        finally:
            await engine.dispose()
    _drive(body)
    out = capsys.readouterr().out
    assert SOFT_FAIL_LINE in out, (
        "the scenario never reached the session check's soft-fail branch")
    assert SEAT_REFUSED_LINE in out, "the route never said it refused the claim"


# The request shapes that DO carry the claimed seat's own session, on the same
# soft-fail branch: verification and expiry are the session check's business,
# not the seat binding's. (id, expired)
OWN_SEAT = (
    ("own-unverified", False),
    ("own-expired", True),
)


@pytest.mark.parametrize("expired", [s[1] for s in OWN_SEAT],
                         ids=[s[0] for s in OWN_SEAT])
def test_a_soft_fail_ping_for_the_requesters_own_seat_publishes_and_renews(
        monkeypatch, capsys, expired):
    """The negative control of the test above (#391), and the honest caller.

    The same real route on the same soft-fail branch, the claim naming the seat
    whose session the request carries: the evidence is published and that
    seat's own lease is renewed, exactly as before the binding existed. A fix
    that refused every soft-fail claim would close residual 26 by breaking the
    honest client, and this is where that would show.
    """
    async def body():
        engine, Session, ids = await _fresh_series()
        sid = ids["sid"]
        key = str(sid)
        try:
            with _harness_globals(), _seat_harness(monkeypatch) as renewals:
                if expired:
                    await _set_session(Session, SID_T1B, expired=True)
                await asyncio.wait_for(_ping(Session, SID_T1B, sid), 15)
                assert key in main._in_match_seen, (
                    "a claim for the requester's own seat published nothing")
                assert renewals == [(str(ids["t1b"]), "team", key)], renewals
        finally:
            await engine.dispose()
    _drive(body)
    out = capsys.readouterr().out
    assert SOFT_FAIL_LINE in out, (
        "the scenario never reached the session check's soft-fail branch")
    assert SEAT_REFUSED_LINE not in out, out


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
