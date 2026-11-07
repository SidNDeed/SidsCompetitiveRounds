"""Effects of the admission gate's refusals, read by execution (round 8).

Two refusal properties the gate walks cannot name by a shape are bound here
to what the real production functions do, against a live database:

* main._lease_acquire answers False (not a lease generation) when the
  per-player admission gate refuses, and leaves the player's existing lease as it was (read by a
  separate connection);
* match_hold.match_hold_claim's other_mode refusal writes its audit row in a
  fresh transaction that has both transaction-local bounds armed
  (lock_timeout and statement_timeout, as _install_database_timeouts sets
  them), read on the claim's own session just before the refusal row.

Each has a positive control. CF_TEST_PG_DSN/CF_TEST_PG_OPTOUT mean what they
mean in the other match-hold PostgreSQL suites; a non-superuser admin DSN
runs in the lane database gate_lane makes.
"""

import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import cf_pg  # noqa: E402
from gate_lane import gate_lane  # noqa: E402,F401  (the live tests' fixture)
import main  # noqa: E402
import test_match_hold_pg as hold_test  # noqa: E402
from sqlalchemy import text  # noqa: E402

match_hold = hold_test.match_hold


async def _lease(conn, pid):
    rows = await conn.fetch(
        "SELECT mode, group_id, generation FROM queue_leases WHERE player_id = $1", pid)
    return [tuple(r) for r in rows]


@pytest.mark.usefixtures("gate_lane")
def test_r8_lease_acquire_answers_false_when_the_gate_refuses():
    """A committed ffa lease for lobby A; an acquire of an ffa lease for
    lobby B is refused by the gate: _lease_acquire answers False and the
    lease is still A's. The control: the same acquire for lobby A is
    admitted and answers its new lease generation."""
    cf_pg.require_live_pg()

    async def inside():
        async with cf_pg.case("r8eff") as (case, sm):
            (pid, _steam), = await hold_test.seed_players(case.conn, 1)
            mine, other = uuid.uuid4(), uuid.uuid4()
            async with sm() as db:
                gen = await main._lease_acquire(db, pid, "ffa", mine, 600)
                assert isinstance(gen, uuid.UUID), gen
                await db.commit()
            held = await _lease(case.conn, pid)
            assert [r[:2] for r in held] == [("ffa", mine)], held
            async with sm() as db:
                got = await main._lease_acquire(db, pid, "ffa", other, 600)
                assert got is False, got
                await db.rollback()
            assert await _lease(case.conn, pid) == held
            async with sm() as db:
                gen = await main._lease_acquire(db, pid, "ffa", mine, 600)
                assert isinstance(gen, uuid.UUID), gen
                await db.commit()
            again = await _lease(case.conn, pid)
            assert [r[:2] for r in again] == [("ffa", mine)] and again != held, again

    hold_test._run(inside())


@pytest.mark.usefixtures("gate_lane")
def test_r8_claim_refusal_row_is_written_with_its_bounds_armed(monkeypatch):
    """match_hold_claim refused other_mode (a live team lease for another
    series): just before its refusal row, the claim's session has
    lock_timeout and statement_timeout at the values
    _install_database_timeouts arms, not the session defaults. The control:
    a separate session's defaults differ from the armed values."""
    async def body(env):
        series, game, _ = await hold_test.opened_series(env, "team", held=1)
        held_pid = series.pid(1)
        opened = await hold_test.open_hold(env, series, 1, 0, game)
        assert opened.status_code == 200 and opened.json()["status"] == "opened"
        hold_id = uuid.UUID(opened.json()["hold_id"])
        await env.conn.execute(
            "INSERT INTO queue_leases (player_id, mode, group_id, generation, expires_at) "
            "VALUES ($1, 'team', $2, gen_random_uuid(), clock_timestamp() + interval '5 min')",
            held_pid, uuid.uuid4())

        bounds = "SELECT current_setting('lock_timeout'), current_setting('statement_timeout')"
        async with env.sm() as db:
            defaults = tuple((await db.execute(text(bounds))).first())
            await match_hold._install_database_timeouts(db)
            armed = tuple((await db.execute(text(bounds))).first())
            await db.rollback()
        assert armed != defaults, (armed, defaults)

        seen = []
        real = match_hold._refuse_attempt

        async def reading(db, hid, kind, now, reason):
            if reason == "other_mode":
                seen.append(tuple((await db.execute(text(bounds))).first()))
            return await real(db, hid, kind, now, reason)

        monkeypatch.setattr(match_hold, "_refuse_attempt", reading)
        claimed = await hold_test.claim(env, series, 1, hold_id)
        assert claimed == {"status": "refused", "reason": "other_mode"}, claimed
        assert seen == [armed], (seen, armed, defaults)
        attempts = [tuple(r) for r in await env.conn.fetch(
            "SELECT kind, outcome, reason FROM match_hold_attempts WHERE hold_id=$1"
            " ORDER BY attempt_no", hold_id)]
        assert attempts[-1] == ("claim", "refused", "other_mode"), attempts

    hold_test.run_env(monkeypatch, body, "r8eff")
