"""H3: one durable per-player gate across holds and every formation writer.

The source census is DSN-free and names every authorized admission span.  The
live controls exercise open and claim refusals plus the common gate in both
target orders for all four queue modes.  CF_TEST_PG_DSN/CF_TEST_PG_OPTOUT have
the same meaning as in the other match-hold PostgreSQL suites.
"""

import asyncio
import ast
import collections
import inspect
import os
import re
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
import test_match_hold_pg as hold_test  # noqa: E402
# The match_hold the hold suite loaded: the MATCH_HOLD_SRC copy when set
# (a plain import here would bind the tracked copy main cached).
match_hold = hold_test.match_hold


ACQUIRERS = ("_lease_acquire", "_lease_acquire_many")
GATE = "_lease_admission_gate"
Site = collections.namedtuple("Site", "lineno end_lineno callee held")
_INVENTORY = {}


def admission_sites():
    """Every admission call in main.py by the module-level function that makes
    it, in source order: a call of _lease_acquire, _lease_acquire_many or the
    gate itself.  `held` marks an acquire made with _gate_held=True, the form
    a direct gate caller uses after its own gate.  Derived from the AST, not
    listed by hand: a site a reviewer forgot is a site this inventory shows
    and the census below refuses (the re-land's Codex round, F2, found four
    hand-listed omissions: queue_ready's two sites and both continuations)."""
    if "sites" not in _INVENTORY:
        tree = ast.parse(inspect.getsource(main))
        sites, ends = {}, {}
        for fn in tree.body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            found = []
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in ACQUIRERS + (GATE,)):
                    held = any(kw.arg == "_gate_held" and isinstance(kw.value, ast.Constant)
                               and kw.value.value is True for kw in node.keywords)
                    found.append(Site(node.lineno, node.end_lineno, node.func.id, held))
            if found:
                sites[fn.name] = sorted(found)
                ends[fn.name] = fn.end_lineno
        _INVENTORY["sites"], _INVENTORY["ends"] = sites, ends
    return _INVENTORY["sites"]


def formation_sites():
    """(function, k) of every formation site: an unheld acquirer call outside
    the acquirers, k its source-order index among the function's calls."""
    return sorted((name, k) for name, sites in admission_sites().items()
                  if name not in ACQUIRERS
                  for k, site in enumerate(sites, 1)
                  if site.callee in ACQUIRERS and not site.held)


# The census: every function of main.py that makes an admission call, with
# its calls in source order. The two acquirers gate once, and _lease_acquire_many
# then acquires per player under the gate it holds; _rdm_claim gates directly
# and acquires under that gate. Every other entry is a formation site, whose
# refusal takes the shared form checked below. queue_poll, queue_ready and
# team_queue_poll carry two sites each: the polls' room issuance (first in
# source) and their discovery or assembly, in different requests; queue_ready's
# formation renewal and its in-game fence, in one request.
CENSUS = {
    "_lease_acquire": [(GATE, False)],
    "_lease_acquire_many": [(GATE, False), ("_lease_acquire", True)],
    "queue_poll": [("_lease_acquire_many", False)] * 2,
    "queue_ready": [("_lease_acquire_many", False)] * 2,
    "team_queue_poll": [("_lease_acquire_many", False)] * 2,
    "_team_relock_existing_series": [("_lease_acquire_many", False)],
    "team_series_continuation": [("_lease_acquire_many", False)],
    "ovt_queue_poll": [("_lease_acquire_many", False)],
    "ovt_series_continuation": [("_lease_acquire_many", False)],
    "_lobby_enroll_caller": [("_lease_acquire", False)],
    "team_lobby_start": [("_lease_acquire_many", False)],
    "ovt_lobby_start": [("_lease_acquire_many", False)],
    "_ffa_lobby_enroll_caller": [("_lease_acquire", False)],
    "_ffa_lock_roster": [("_lease_acquire_many", False)],
    "_rdm_claim": [(GATE, False), ("_lease_acquire", True)],
    "_ffa_queue_poll_inner": [("_lease_acquire_many", False)],
}


def test_h3_every_admission_site_uses_shared_gate_recheck_and_rollback():
    gate = inspect.getsource(main._lease_admission_gate)
    assert "for pid in pid_text:" in gate
    assert "FOR NO KEY UPDATE" in gate
    assert "queue_leases" in gate and "match_seat_holds" in gate
    assert "ranked_queue" in gate and "team_queue" in gate
    assert "ovt_queue" in gate and "ffa_queue" in gate
    assert "clock_timestamp()" in gate

    found = admission_sites()
    assert {name: [(s.callee, s.held) for s in sites] for name, sites in found.items()} \
        == CENSUS, ("H3 census", found)
    lines = inspect.getsource(main).splitlines()
    for name, sites in found.items():
        for k, site in enumerate(sites):
            end = sites[k + 1].lineno - 1 if k + 1 < len(sites) else _INVENTORY["ends"][name]
            tail = "\n".join(lines[site.lineno - 1:end])
            if site.held:
                # An acquire under a gate the function holds: the gate is an
                # earlier call of the same function.
                assert any(s.callee == GATE for s in sites[:k]), (name, site)
                continue
            if site.callee == GATE:
                assert "admitted, _ = await _lease_admission_gate" in tail, (name, site)
                if name not in ACQUIRERS:
                    # The direct form: the refusal answers before any write.
                    assert "if not admitted:" in tail, (name, site)
                    assert "return await _rdm_refuse(" in tail, (name, site)
                continue
            # The shared form: each site refuses the gate's False with a rollback.
            assert "is False" in tail, (name, site)
            assert "await db.rollback()" in tail, (name, site)

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
