"""H3: one durable per-player gate across holds and every formation writer.

The source census is DSN-free and names every authorized admission span.  The
live controls exercise open and claim refusals plus the common gate in both
target orders for all four queue modes.  CF_TEST_PG_DSN/CF_TEST_PG_OPTOUT have
the same meaning as in the other match-hold PostgreSQL suites.
"""

import asyncio
import ast
import inspect
import os
import sys
import textwrap
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import cf_pg  # noqa: E402
import main  # noqa: E402
import match_hold  # noqa: E402
import test_match_hold_pg as hold_test  # noqa: E402


def test_h3_every_admission_site_uses_shared_gate_recheck_and_rollback():
    gate = inspect.getsource(main._lease_admission_gate)
    assert "for pid in pid_text:" in gate
    assert "FOR NO KEY UPDATE" in gate
    assert "queue_leases" in gate and "match_seat_holds" in gate
    assert "ranked_queue" in gate and "team_queue" in gate
    assert "ovt_queue" in gate and "ffa_queue" in gate
    assert "clock_timestamp()" in gate

    sites = {
        "queue_poll": "_lease_acquire_many",
        "team_queue_poll": "_lease_acquire_many",
        "_team_relock_existing_series": "_lease_acquire_many",
        "ovt_queue_poll": "_lease_acquire_many",
        "_lobby_enroll_caller": "_lease_acquire",
        "team_lobby_start": "_lease_acquire_many",
        "ovt_lobby_start": "_lease_acquire_many",
        "_ffa_lobby_enroll_caller": "_lease_acquire",
        "_ffa_lock_roster": "_lease_acquire_many",
        "_ffa_queue_poll_inner": "_lease_acquire_many",
    }
    for name, helper in sites.items():
        source = inspect.getsource(getattr(main, name))
        calls = [node.func.id for node in ast.walk(
            ast.parse(textwrap.dedent(source)))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in ("_lease_acquire", "_lease_acquire_many")]
        assert calls == [helper], (name, calls)
        tail = source[source.rfind(helper):]
        assert "is False" in tail, name
        assert "await db.rollback()" in tail, name

    open_source = inspect.getsource(match_hold.match_hold_open)
    claim_source = inspect.getsource(match_hold.match_hold_claim)
    for name, source in (("open", open_source), ("claim", claim_source)):
        calls = [node.func.id for node in ast.walk(
            ast.parse(textwrap.dedent(source)))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "_lease_admission_gate"]
        assert calls == ["_lease_admission_gate"], (name, calls)
    assert "admitted, now = await _lease_admission_gate" in open_source
    assert "admitted, now = await _lease_admission_gate" in claim_source
    assert "await db.rollback()" in open_source and "await db.rollback()" in claim_source
    assert "_gate_held=True" in claim_source
    for helper in (main._lease_acquire, main._lease_acquire_many):
        source = inspect.getsource(helper)
        calls = [node.func.id for node in ast.walk(
            ast.parse(textwrap.dedent(source)))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "_lease_admission_gate"]
        assert calls == ["_lease_admission_gate"], helper.__name__


def test_h3_hold_open_and_claim_reject_another_live_commitment(monkeypatch):
    async def body(env):
        series, game, _ = await hold_test.opened_series(env, "team", held=1)
        held_pid = series.pid(1)
        other_group = uuid.uuid4()
        await env.conn.execute(
            "INSERT INTO queue_leases (player_id, mode, group_id, generation, expires_at) "
            "VALUES ($1, 'ffa', $2, gen_random_uuid(), clock_timestamp() + interval '5 min')",
            held_pid, other_group)

        refused = await hold_test.open_hold(env, series, 1, 0, game)
        assert refused.status_code == 200 and refused.json() == {
            "status": "refused", "reason": "other_mode"}
        assert await env.conn.fetchval(
            "SELECT count(*) FROM match_seat_holds WHERE player_id=$1", held_pid) == 0
        assert await env.conn.fetchval(
            "SELECT group_id FROM queue_leases WHERE player_id=$1", held_pid) == other_group

        await env.conn.execute("DELETE FROM queue_leases WHERE player_id=$1", held_pid)
        opened = await hold_test.open_hold(env, series, 1, 0, game)
        assert opened.status_code == 200 and opened.json()["status"] == "opened"
        hold_id = uuid.UUID(opened.json()["hold_id"])
        same_mode_other_group = uuid.uuid4()
        await env.conn.execute(
            "INSERT INTO queue_leases (player_id, mode, group_id, generation, expires_at) "
            "VALUES ($1, 'team', $2, gen_random_uuid(), clock_timestamp() + interval '5 min')",
            held_pid, same_mode_other_group)
        claimed = await hold_test.claim(env, series, 1, hold_id)
        assert claimed == {"status": "refused", "reason": "other_mode"}
        row = await env.conn.fetchrow(
            "SELECT claimed_at, verifier FROM match_seat_holds WHERE id=$1", hold_id)
        assert tuple(row) == (None, None)
        assert await env.conn.fetchval(
            "SELECT group_id FROM queue_leases WHERE player_id=$1", held_pid) == same_mode_other_group

    hold_test.run_env(monkeypatch, body, "h3hold")


@pytest.mark.parametrize("mode", ["ranked", "team", "ovt", "ffa"])
@pytest.mark.parametrize("first", [0, 1])
def test_h3_common_gate_serializes_every_mode_in_both_target_orders(mode, first):
    cf_pg.require_live_pg()

    async def inside():
        async with cf_pg.case("h3gate") as (case, sm):
            seats = await hold_test.seed_players(case.conn, 2)
            pids = [row[0] for row in seats]
            groups = [None, None] if mode == "ranked" else [uuid.uuid4(), uuid.uuid4()]
            winner = groups[first]
            loser = groups[1 - first]
            async with sm() as one, sm() as two:
                admitted, _ = await main._lease_admission_gate(one, pids, mode, winner)
                assert admitted
                for pid in sorted(pids, key=str):
                    await main._lease_acquire(
                        one, pid, mode, winner, main.LEASE_TTL_ASSEMBLY,
                        _gate_held=True)

                waiting = asyncio.create_task(
                    main._lease_admission_gate(two, pids, mode, loser))
                await asyncio.sleep(0.05)
                assert not waiting.done(), "overlapping roster did not wait on the player gate"
                await one.commit()
                admitted_two, _ = await asyncio.wait_for(waiting, 2)
                assert not admitted_two
                await two.rollback()

            rows = await case.conn.fetch(
                "SELECT player_id, mode, group_id FROM queue_leases ORDER BY player_id::text")
            assert len(rows) == 2
            assert all(row["mode"] == mode and row["group_id"] == winner for row in rows)

    asyncio.run(inside())
