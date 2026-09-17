"""A1 — the formation predicates, EXECUTED against a real PostgreSQL.

Why this file exists. The rest of the A1 suite is fake-session and source-
walking: it proves the phase order, the lease policies and the bind shapes, and
it cannot prove that any of the SQL parses. A1 moved five predicates to module
constants and gave each a typed `:only` bind -- `CAST(:only AS uuid[])` for the
four group predicates, `CAST(:only AS uuid)` for the 1v1 one -- and a bind that
Postgres cannot type is not a subtle bug: it is every gather poll answering
500, on the hottest paths in the game, in a batch whose whole tests-pass story
would otherwise be green (#438/#443 -- acceptance is a POSITIVE signal the
change emits, and "the fakes accepted it" is not one).

So each predicate is run BOTH ways here -- `only` NULL to discover, `only`
carrying discovered ids to revalidate -- against a real server, on a schema
carrying only the columns the predicates touch. The assertions are about what
the predicate SELECTS, not about matchmaking policy; the policy is tested
against the handlers elsewhere.

Skips unless A1_TEST_PG_DSN is set, exactly like
test_a1_formation_concurrency.py, so CI and the ordinary suite are unaffected:

    A1_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:55432/a1test" \\
        python -m pytest tests/test_a1_predicate_sql.py -q
"""
import asyncio
import os
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import main

DSN = os.environ.get("A1_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(
    not DSN, reason="A1_TEST_PG_DSN unset; live-Postgres predicate check")

# Outside the real SteamID64 space, so a misconfigured DSN cannot collide with
# production rows.
SIDS = ["90000000000000%03d" % n for n in (11, 12, 13, 14, 15)]

SCHEMA = """
DROP TABLE IF EXISTS ovt_queue;
DROP TABLE IF EXISTS ffa_queue;
DROP TABLE IF EXISTS team_queue;
DROP TABLE IF EXISTS ranked_queue;
DROP TABLE IF EXISTS player_bans;
DROP TABLE IF EXISTS player_blocks;
DROP TABLE IF EXISTS queue_blocks;
DROP TABLE IF EXISTS queue_leases;

CREATE TABLE ovt_queue (
    player_id UUID PRIMARY KEY,
    steam_id TEXT NOT NULL,
    display_name TEXT,
    preferred_side INT,
    solo_extra_pick BOOLEAN DEFAULT false,
    region TEXT,
    rating DOUBLE PRECISION DEFAULT 1500,
    rating_deviation DOUBLE PRECISION DEFAULT 350,
    completed_series INT DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'searching',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_polled TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE ffa_queue (
    player_id UUID PRIMARY KEY,
    steam_id TEXT NOT NULL,
    display_name TEXT,
    region TEXT,
    status TEXT NOT NULL DEFAULT 'searching',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_polled TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE team_queue (
    player_id UUID PRIMARY KEY,
    steam_id TEXT NOT NULL,
    display_name TEXT,
    rating DOUBLE PRECISION DEFAULT 1500,
    rating_deviation DOUBLE PRECISION DEFAULT 350,
    completed_series INT DEFAULT 0,
    fallback_rating DOUBLE PRECISION DEFAULT 1500,
    region TEXT,
    manual_pick_enabled BOOLEAN DEFAULT false,
    preferred_team INT,
    queue_type TEXT NOT NULL DEFAULT 'auto',
    status TEXT NOT NULL DEFAULT 'searching',
    series_id UUID,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_polled TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE ranked_queue (
    player_id UUID PRIMARY KEY,
    steam_id TEXT NOT NULL,
    display_name TEXT,
    rating DOUBLE PRECISION DEFAULT 1500,
    status TEXT NOT NULL DEFAULT 'searching',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    wait_since TIMESTAMPTZ,
    last_polled TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE player_bans (
    steam_id TEXT NOT NULL,
    unbanned_at TIMESTAMPTZ
);

CREATE TABLE player_blocks (
    blocker_id UUID NOT NULL,
    blocked_id UUID NOT NULL
);

CREATE TABLE queue_blocks (
    blocker_id UUID NOT NULL,
    blocked_id UUID NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE queue_leases (
    player_id UUID PRIMARY KEY,
    mode TEXT NOT NULL,
    group_id UUID,
    expires_at TIMESTAMPTZ NOT NULL
);
"""

TABLES = ("ovt_queue", "ffa_queue", "team_queue", "ranked_queue")


def run(coro):
    return asyncio.run(coro)


async def _setup():
    engine = create_async_engine(DSN)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        for stmt in [s for s in SCHEMA.split(";") if s.strip()]:
            await conn.execute(text(stmt))
    pids = [uuid.uuid4() for _ in SIDS]
    async with sm() as db:
        for tbl in TABLES:
            for pid, sid in zip(pids, SIDS):
                await db.execute(text(
                    f"INSERT INTO {tbl} (player_id, steam_id, display_name)"
                    f" VALUES (:p, :s, :n)"),
                    {"p": pid, "s": sid, "n": "seat-" + sid[-2:]})
        await db.commit()
    return engine, sm, pids


def _service_ids():
    return sorted(main.SPECTATE_BROADCAST_STEAM_IDS)


# ── the group predicates: CAST(:only AS uuid[]) both ways ────────────────

async def _ovt(sm, only):
    async with sm() as db:
        return (await db.execute(
            text(main._OVT_CANDIDATE_SQL),
            {"service_ids": _service_ids(), "only": only})).mappings().all()


async def _ffa(sm, only):
    async with sm() as db:
        return (await db.execute(
            text(main._FFA_CANDIDATE_SQL),
            {"maxp": main.FFA_MAX_PLAYERS, "service_ids": _service_ids(),
             "only": only})).mappings().all()


async def _team(sm, caller, only, qtype="auto", bilateral=True):
    # `bilateral` is the TEMPLATE shape (dropped for manual queues); `qtype` is
    # the row filter. They move together in the handler and are independent
    # here on purpose -- the point of this file is that each shape PARSES.
    sql = main._TEAM_CANDIDATE_SQL_TMPL.format(
        bilateral=main._TEAM_BILATERAL_SQL if bilateral else "")
    async with sm() as db:
        return (await db.execute(text(sql), {
            "pid": caller, "my_r": 1500.0, "range": 100.0, "qt": qtype,
            "service_ids": _service_ids(), "only": only})).mappings().all()


async def _resume(sm, pids, caller, series_id, only):
    async with sm() as db:
        return (await db.execute(text(main._TEAM_RESUME_CONSENT_SQL), {
            "pids": pids, "me": caller, "sid": series_id,
            "only": only})).mappings().all()


async def _ranked(sm, caller, only):
    async with sm() as db:
        return (await db.execute(text(main._RANKED_CANDIDATE_SQL), {
            "pid": caller, "rmin": 1400.0, "rmax": 1600.0,
            "my_uncapped": False, "my_rating": 1500.0,
            "service_ids": _service_ids(), "only": only})).mappings().all()


def test_ovt_predicate_runs_both_ways():
    async def go():
        engine, sm, pids = await _setup()
        try:
            found = await _ovt(sm, None)
            assert len(found) == 3, "LIMIT 3 is the 1v2 lobby size"
            ids = [r["player_id"] for r in found]
            again = await _ovt(sm, ids)
            assert [r["player_id"] for r in again] == ids, (
                "revalidation must return exactly the rows it was aimed at, "
                "in the same join order")
            # and it can come back SHORT -- which is the drift signal
            assert len(await _ovt(sm, ids[:2])) == 2
        finally:
            await engine.dispose()
    run(go())


def test_ffa_predicate_runs_both_ways():
    async def go():
        engine, sm, pids = await _setup()
        try:
            found = await _ffa(sm, None)
            assert len(found) == len(SIDS) or len(found) == main.FFA_MAX_PLAYERS
            ids = [r["player_id"] for r in found]
            again = await _ffa(sm, ids)
            assert [r["player_id"] for r in again] == ids
        finally:
            await engine.dispose()
    run(go())


def test_team_predicate_runs_both_ways_and_in_both_shapes():
    async def go():
        engine, sm, pids = await _setup()
        try:
            # BOTH template shapes must parse: the auto queue carries the
            # bilateral band, the manual queue drops it (#127 -- joining the
            # lobby is the consent). A template that only ever gets formatted
            # one way in the tests is a template only half-checked.
            for bilateral in (True, False):
                found = await _team(sm, pids[0], None, bilateral=bilateral)
                assert len(found) == 3, (bilateral, "LIMIT 3 is the other three")
                assert pids[0] not in [r["player_id"] for r in found], (
                    "the caller is excluded by the predicate, which is why the "
                    "gate has to add them back by hand")
                ids = [r["player_id"] for r in found]
                again = await _team(sm, pids[0], ids, bilateral=bilateral)
                assert sorted(str(r["player_id"]) for r in again) == sorted(
                    str(i) for i in ids)
            # and the queue_type bind is live, not decoration: the seeded rows
            # are all 'auto', so a manual caller must see none of them
            assert await _team(sm, pids[0], None, qtype="manual") == []
        finally:
            await engine.dispose()
    run(go())


def test_team_resume_predicate_runs_both_ways():
    async def go():
        engine, sm, pids = await _setup()
        sid = uuid.uuid4()
        try:
            quartet = pids[:4]
            found = await _resume(sm, quartet, quartet[0], sid, None)
            assert len(found) == 3, "the other three originals"
            ids = [r["player_id"] for r in found]
            again = await _resume(sm, quartet, quartet[0], sid, ids)
            assert sorted(str(r["player_id"]) for r in again) == sorted(
                str(i) for i in ids)
        finally:
            await engine.dispose()
    run(go())


def test_ranked_predicate_runs_both_ways():
    """The 1v1 one uses a SCALAR uuid bind, not an array -- a different typing
    path, and the one already deployed behind the other two commits."""
    async def go():
        engine, sm, pids = await _setup()
        try:
            found = await _ranked(sm, pids[0], None)
            assert len(found) == 1, "LIMIT 1 -- the 1v1 matcher picks one"
            one = found[0]["player_id"]
            again = await _ranked(sm, pids[0], one)
            assert len(again) == 1 and again[0]["player_id"] == one
            # aimed at a row that does not satisfy the predicate: empty, which
            # is exactly the drift signal the handler acts on
            assert await _ranked(sm, pids[0], pids[0]) == []
        finally:
            await engine.dispose()
    run(go())


def test_the_lease_exclusion_actually_excludes():
    """The discovery-side lease filter is the thing that keeps one committed
    seat from wedging a whole pool, and it is three lines of correlated
    subquery per predicate -- exactly the shape that can be silently wrong
    (a mis-correlated NOT EXISTS matching nothing, or everything)."""
    async def go():
        engine, sm, pids = await _setup()
        try:
            before = {r["player_id"] for r in await _ovt(sm, None)}
            victim = sorted(before, key=str)[0]
            async with sm() as db:
                await db.execute(text(
                    "INSERT INTO queue_leases (player_id, mode, group_id,"
                    " expires_at) VALUES (:p, 'ffa', :g,"
                    " clock_timestamp() + INTERVAL '5 minutes')"),
                    {"p": victim, "g": uuid.uuid4()})
                await db.commit()
            after = {r["player_id"] for r in await _ovt(sm, None)}
            assert victim not in after, (
                "a seat holding a live lease elsewhere is still discoverable")
            assert len(after) == 3, (
                "the rest of the pool must still fill the lobby -- an "
                "over-broad exclusion would empty it")
            # an EXPIRED lease excludes nobody
            async with sm() as db:
                await db.execute(text(
                    "UPDATE queue_leases SET expires_at ="
                    " clock_timestamp() - INTERVAL '1 second'"))
                await db.commit()
            assert victim in {r["player_id"] for r in await _ovt(sm, None)}, (
                "an expired lease must not exclude -- leases expire by design, "
                "and nothing runs to clean them up")
        finally:
            await engine.dispose()
    run(go())


def test_the_resume_predicate_ignores_leases_on_purpose():
    """The mirror of the test above, and the reason the two predicates differ:
    the four resuming a DC'd series still hold THAT series' lease."""
    async def go():
        engine, sm, pids = await _setup()
        sid = uuid.uuid4()
        try:
            quartet = pids[:4]
            async with sm() as db:
                for p in quartet:
                    await db.execute(text(
                        "INSERT INTO queue_leases (player_id, mode, group_id,"
                        " expires_at) VALUES (:p, 'team', :g,"
                        " clock_timestamp() + INTERVAL '5 minutes')"),
                        {"p": p, "g": sid})
                await db.commit()
            found = await _resume(sm, quartet, quartet[0], sid, None)
            assert len(found) == 3, (
                "a lease-filtered resume predicate would refuse every healthy "
                "resume, because the resume IS the lease")
        finally:
            await engine.dispose()
    run(go())
