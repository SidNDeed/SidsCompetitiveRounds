"""A1 acceptance item 5 — two REAL PostgreSQL transactions, with barriers.

Everything else in the A1 suite runs against a fake session, which can prove
what statements are issued and in what order but cannot prove that the identity
lock actually BLOCKS a second formation. Advisory-lock blocking and FOR UPDATE
waiting are Postgres behaviours; a fake cannot exhibit them, and a test that
merely observes "no deadlock after enough repetitions" would pass with the
serialization removed entirely (that was r1's version of this item, and it was
wrong).

So this file needs a live server. Point A1_TEST_PG_DSN at a throwaway cluster:

    A1_TEST_PG_DSN=postgresql+asyncpg://postgres@127.0.0.1:55432/a1test

and the file skips when it is unset, so the ordinary suite is unaffected. It
NEVER runs against a real deployment: it creates and drops its own tables, and
every steam id it uses is outside the real id space.

No pytest-asyncio: the rest of this suite drives coroutines through a plain
asyncio.run helper, and an opt-in acceptance test is not a good reason to add a
test dependency the other 66 files do not have.

What it asserts, in one scenario:

  * both formations complete discovery before either locks anything (the
    barrier is a real asyncio.Event, not a sleep);
  * the second formation BLOCKS in the identity phase while holding no row;
  * the winner commits;
  * the loser then wakes and is refused by the STRICT lease gate;
  * exactly one formation exists and the loser wrote nothing at all.
"""

import asyncio
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import main

DSN = os.environ.get("A1_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(
    not DSN, reason="A1_TEST_PG_DSN unset; live-Postgres acceptance item")

# Deliberately outside the real SteamID64 space so a misconfigured DSN cannot
# collide with production rows.
SID_A = "90000000000000001"
SID_B = "90000000000000002"

SCHEMA = """
DROP TABLE IF EXISTS queue_leases;
DROP TABLE IF EXISTS ranked_queue;
DROP TABLE IF EXISTS players;

CREATE TABLE players (
    id UUID PRIMARY KEY,
    steam_id TEXT UNIQUE NOT NULL
);

CREATE TABLE ranked_queue (
    player_id UUID PRIMARY KEY,
    steam_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'searching',
    matched_with UUID,
    matched_at TIMESTAMPTZ
);

CREATE TABLE queue_leases (
    player_id UUID PRIMARY KEY,
    mode TEXT NOT NULL,
    group_id UUID,
    generation UUID NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL,
    renewed_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
"""


def run(coro):
    return asyncio.run(coro)


async def _setup():
    engine = create_async_engine(DSN)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        for stmt in [s for s in SCHEMA.split(";") if s.strip()]:
            await conn.execute(text(stmt))
    pid_a, pid_b = uuid.uuid4(), uuid.uuid4()
    async with sm() as db:
        for pid, sid in ((pid_a, SID_A), (pid_b, SID_B)):
            await db.execute(
                text("INSERT INTO players (id, steam_id) VALUES (:i, :s)"),
                {"i": pid, "s": sid})
            await db.execute(
                text("INSERT INTO ranked_queue (player_id, steam_id, status)"
                     " VALUES (:i, :s, 'searching')"),
                {"i": pid, "s": sid})
        await db.commit()
    return engine, sm, pid_a, pid_b


async def _form(sm, pid_a, pid_b, *, label,
                discovered, both_discovered, acquired, may_commit, outcome):
    """One whole formation attempt, following the A1 phase order exactly."""
    async with sm() as db:
        # 2. UNLOCKED discovery -- both contenders see the same free pair.
        rows = (await db.execute(text(
            "SELECT player_id, steam_id FROM ranked_queue"
            " WHERE status = 'searching' ORDER BY steam_id"))).mappings().all()
        rows = [dict(r) for r in rows]
        outcome[label + "_discovered"] = [r["steam_id"] for r in rows]
        discovered.set()
        await both_discovered.wait()

        # 3. the identity barrier. The loser blocks HERE, holding no row.
        await main._identity_lock_many(db, [r["steam_id"] for r in rows])
        acquired.set()
        await may_commit.wait()

        # 5. the discovered snapshot, in global row order.
        await main._lock_snapshot_rows(
            db, "ranked_queue", player_ids=[r["player_id"] for r in rows])

        # 6. revalidate under the locks.
        still = (await db.execute(text(
            "SELECT player_id FROM ranked_queue"
            " WHERE player_id = ANY(:ids) AND status = 'searching'"),
            {"ids": [r["player_id"] for r in rows]})).scalars().all()
        if len(still) != len(rows):
            outcome[label] = "drift"
            await db.rollback()
            return

        # 7. the STRICT lease gate -- fresh roster, so no live lease at all.
        conflict = await main._formation_lease_conflict(
            db, [(r["steam_id"], r["player_id"]) for r in rows])
        if conflict is not None:
            outcome[label] = f"refused:{conflict[1]}"
            await db.rollback()
            return

        for pid, other in ((pid_a, pid_b), (pid_b, pid_a)):
            await db.execute(text(
                "UPDATE ranked_queue SET status = 'matched', matched_with = :o,"
                " matched_at = now() WHERE player_id = :p"),
                {"o": other, "p": pid})
        await main._lease_acquire_many(
            db, [pid_a, pid_b], "ranked", None, main.LEASE_TTL_POLLING)
        await db.commit()
        outcome[label] = "formed"


async def _scenario():
    engine, sm, pid_a, pid_b = await _setup()
    try:
        d1, d2 = asyncio.Event(), asyncio.Event()
        both = asyncio.Event()
        acq1, acq2 = asyncio.Event(), asyncio.Event()
        go1, go2 = asyncio.Event(), asyncio.Event()
        outcome = {}

        t1 = asyncio.create_task(_form(
            sm, pid_a, pid_b, label="t1", discovered=d1, both_discovered=both,
            acquired=acq1, may_commit=go1, outcome=outcome))
        t2 = asyncio.create_task(_form(
            sm, pid_a, pid_b, label="t2", discovered=d2, both_discovered=both,
            acquired=acq2, may_commit=go2, outcome=outcome))

        # Both must finish discovery before EITHER locks. This is the overlap
        # the race needs; without it the test proves nothing.
        await asyncio.wait_for(d1.wait(), 15)
        await asyncio.wait_for(d2.wait(), 15)
        assert outcome["t1_discovered"] == [SID_A, SID_B], outcome
        assert outcome["t2_discovered"] == [SID_A, SID_B], outcome
        both.set()

        # Exactly one should get through the identity phase.
        w1 = asyncio.create_task(acq1.wait())
        w2 = asyncio.create_task(acq2.wait())
        done, pending = await asyncio.wait(
            [w1, w2], return_when=asyncio.FIRST_COMPLETED, timeout=15)
        assert done, "neither formation acquired the identity locks"
        await asyncio.sleep(1.5)
        assert acq1.is_set() != acq2.is_set(), (
            "BOTH formations crossed the identity barrier -- the advisory "
            "locks are not serializing, which is the entire defect this "
            "change exists to remove"
        )
        for p in pending:
            p.cancel()

        winner, loser = ("t1", "t2") if acq1.is_set() else ("t2", "t1")

        # The loser is blocked in the IDENTITY phase, so it holds no queue row
        # and has written nothing. Prove it from a third connection.
        async with sm() as probe:
            assert (await probe.execute(text(
                "SELECT count(*) FROM ranked_queue WHERE status = 'matched'"
            ))).scalar() == 0, "a formation wrote before the winner committed"

        (go1 if winner == "t1" else go2).set()
        await asyncio.wait_for(t1 if winner == "t1" else t2, 30)
        assert outcome[winner] == "formed", outcome

        # Release the loser. It wakes holding the identity locks and must
        # refuse -- at the REVALIDATION, which is the first defence to notice
        # in a SAME-MODE overlap: the winner moved both rows out of
        # 'searching', so the snapshot the loser discovered no longer exists
        # and the lease gate is never reached. That ordering is worth pinning
        # rather than glossing: the cross-mode case below is what exercises
        # the gate, and if this assertion ever reads "formed" the whole design
        # has failed regardless of which guard was supposed to fire.
        (go1 if loser == "t1" else go2).set()
        await asyncio.wait_for(t1 if loser == "t1" else t2, 30)
        assert outcome[loser] == "drift", outcome

        # Exactly one formation, and the loser left nothing behind.
        async with sm() as probe:
            assert (await probe.execute(text(
                "SELECT count(*) FROM ranked_queue WHERE status = 'matched'"
            ))).scalar() == 2
            assert (await probe.execute(text(
                "SELECT count(*) FROM queue_leases"))).scalar() == 2
            gens = (await probe.execute(text(
                "SELECT DISTINCT generation FROM queue_leases"))).scalars().all()
            assert len(gens) == 2, (
                "each player holds exactly one lease from the winning formation"
            )
        return outcome
    finally:
        await engine.dispose()


def test_second_formation_blocks_then_is_refused_and_writes_nothing():
    outcome = run(_scenario())
    assert sorted(v for k, v in outcome.items() if not k.endswith("_discovered")) == [
        "drift", "formed"]


async def _cross_mode():
    """The scenario A1 actually exists for, and the one that reaches the lease
    gate: the same player is searching in two modes at once.

    A team formation takes A's identity and commits a ('team', lobby) lease.
    The ranked formation is blocked on A's identity the whole time, so when it
    wakes its ranked_queue rows are untouched -- no drift -- and the ONLY thing
    standing between it and a second commitment is the strict lease gate.
    Before this change there was nothing there at all, and both formations
    committed.
    """
    engine, sm, pid_a, pid_b = await _setup()
    try:
        ranked_reached_gate = asyncio.Event()
        team_committed = asyncio.Event()
        outcome = {}

        async def team():
            async with sm() as db:
                await main._identity_lock_many(db, [SID_A])
                await main._lease_acquire(
                    db, pid_a, "team", uuid.uuid4(), main.LEASE_TTL_ASSEMBLY)
                await db.commit()
                team_committed.set()

        async def ranked():
            async with sm() as db:
                # discovery happens before team commits, so this formation
                # genuinely believes both seats are free
                rows = [dict(r) for r in (await db.execute(text(
                    "SELECT player_id, steam_id FROM ranked_queue"
                    " WHERE status = 'searching' ORDER BY steam_id"
                ))).mappings().all()]
                ranked_reached_gate.set()
                await team_committed.wait()
                await main._identity_lock_many(
                    db, [r["steam_id"] for r in rows])
                await main._lock_snapshot_rows(
                    db, "ranked_queue",
                    player_ids=[r["player_id"] for r in rows])
                still = (await db.execute(text(
                    "SELECT player_id FROM ranked_queue"
                    " WHERE player_id = ANY(:ids) AND status = 'searching'"),
                    {"ids": [r["player_id"] for r in rows]})).scalars().all()
                outcome["drifted"] = len(still) != len(rows)
                conflict = await main._formation_lease_conflict(
                    db, [(r["steam_id"], r["player_id"]) for r in rows])
                outcome["conflict"] = conflict
                await db.rollback()

        r = asyncio.create_task(ranked())
        await asyncio.wait_for(ranked_reached_gate.wait(), 15)
        await asyncio.wait_for(asyncio.create_task(team()), 15)
        await asyncio.wait_for(r, 30)
        return outcome
    finally:
        await engine.dispose()


def test_cross_mode_live_lease_is_what_the_gate_actually_catches():
    outcome = run(_cross_mode())
    assert outcome["drifted"] is False, (
        "premise check: the ranked rows must be UNTOUCHED, or this is just "
        "the drift test again and the gate is never exercised"
    )
    assert outcome["conflict"] is not None, (
        "the player is committed to a team lobby and the ranked formation "
        "was about to commit them to a 1v1 as well -- this is the double-lock"
    )
    assert outcome["conflict"] == (SID_A, "lease_held_elsewhere"), outcome


async def _exclusive():
    engine, sm, _pa, _pb = await _setup()
    try:
        async with sm() as one, sm() as two:
            await main._identity_lock_many(one, [SID_A])
            blocked = False
            try:
                await asyncio.wait_for(
                    main._identity_lock_many(two, [SID_A]), timeout=3.0)
            except asyncio.TimeoutError:
                blocked = True
            await one.rollback()
            await two.rollback()
        return blocked
    finally:
        await engine.dispose()


def test_identity_lock_is_actually_exclusive_across_connections():
    """The narrowest possible statement of the guarantee: two connections, one
    sid. If this ever passes without blocking, nothing above means anything."""
    assert run(_exclusive()) is True, (
        "a second connection took the same identity lock without waiting -- "
        "the lock is not exclusive and every other assertion here is vacuous"
    )
