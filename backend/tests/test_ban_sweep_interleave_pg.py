"""Bans part 2a, F4: a ban that commits between a writer's ban check and its
write does not let the write stand. Driven against a real PostgreSQL with
the case schema of test_ban_sweep_live.

Each case is the same interleave. A second connection runs the ban core
(_apply_ban_core) and holds its transaction open, so it holds the target's
identity lock without committing. The route is called and must WAIT: its
backend is seen waiting on an advisory lock in pg_locks (any backend of the
case's database: the case runs alone there). The ban then
commits, and the route must refuse and leave no row. The wait is observed,
never assumed: the poll ends as soon as the route's backend waits or the
route returns, within a bound, so the case cannot pass by timing.

    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
"""
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

import main  # noqa: E402
from ban_sweep_pg_bounds import bounded_pg  # noqa: E402,F401  (autouse: every session bounded)
import schemas  # noqa: E402
import test_ban_sweep_live as L  # noqa: E402
from test_ban_sweep_live import case, mode  # noqa: E402,F401  (fixtures)

INTERNAL_KEY = "ban-sweep-internal-key"


async def _interleave(sm, target, route):
    """Hold the ban core's transaction open on one connection, start `route`
    (a coroutine function taking (db, pid_box)) on another, observe it wait,
    commit the ban, and return (waited, the route's answer)."""
    async with sm() as db:
        admin = await L._admin(db)
        await db.commit()
    ban_db = sm()
    try:
        ans = await main._apply_ban_core(ban_db, admin_steam_id=admin, target_steam_id=target,
                                         reason="ban-sweep", duration_minutes=60)
        assert ans["status"] == "banned", ans
        box = {}

        async def run():
            async with sm() as db:
                box["pid"] = (await db.execute(text("SELECT pg_backend_pid()"))).scalar()
                try:
                    out = await route(db)
                    await db.commit()
                    return ("admitted", out)
                except HTTPException as e:
                    await db.rollback()
                    return (e.status_code, str(e.detail))

        task = asyncio.create_task(run())
        waited = False
        for _ in range(200):                     # bound: about ten seconds
            await asyncio.sleep(0.05)
            if task.done():
                break
            if "pid" not in box:
                continue
            # Any backend of this database: a handler that ends a transaction
            # (the bug report's T1) may take its writing one on another pooled
            # connection, so the route's first pid is not the one that waits.
            async with sm() as probe:
                waiting, blocked = (await probe.execute(text(
                    "SELECT count(*) FILTER (WHERE l.locktype = 'advisory'), count(*)"
                    " FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid"
                    " WHERE NOT l.granted"
                    " AND a.datname = current_database() AND l.pid <> pg_backend_pid()"))).one()
            if waiting:
                waited = True
                break
            # A wait on anything else (a mutant without the identity key waits
            # on the ban's row lock instead): the identity key was not what it
            # waited on, so the answer is not-waited, and the ban commits now,
            # inside the session's lock_timeout (ban_sweep_pg_bounds).
            if blocked:
                break
        await ban_db.commit()
    finally:
        await ban_db.close()
    return waited, await task


def test_f4_a_booster_grant_waits_for_a_committing_ban_and_pays_nothing(case, mode, monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", INTERNAL_KEY)

    async def body(sm):
        sid = L._sid()
        disc = "8800" + sid[-8:]
        async with sm() as db:
            pid = await L._player(db, sid, discord_id=disc)
            await db.commit()

        async def route(db):
            return await L._call(main.booster_grant, discord_id=disc, month="2026-11",
                                 x_internal_key=INTERNAL_KEY, db=db)

        waited, got = await _interleave(sm, sid, route)
        async with sm() as db:
            grants = (await db.execute(text(
                "SELECT count(*) FROM booster_grants WHERE discord_id = :d"), {"d": disc})).scalar()
            gold = (await db.execute(text(
                "SELECT count(*) FROM gold_transactions WHERE player_id = :p"
                " AND reason = 'booster_monthly'"), {"p": pid})).scalar()
        return waited, got, grants, gold

    waited, got, grants, gold = L._with_sm(case, body, mode)
    assert waited, got
    assert got[0] == 409 and got[1].startswith("Banned: "), got
    assert (grants, gold) == (0, 0)


def _bug_report_ban_between_t1_and_t2(case, mode, monkeypatch, *, drop_reread=False, no_ban=False):
    """The ban commits AFTER the report's first transaction (T1: its own ban
    read, then _auto_logs._end_transaction) and BEFORE its writing one (T2).
    Only T2's own read can refuse it. drop_reread: the mutant that removes that
    read (the gate's second call answers without reading)."""
    calls = {"gate": 0, "banned": False}
    orig_end = main._auto_logs._end_transaction
    orig_gate = main._ban_lock_and_gate

    async def body(sm):
        sid = L._sid()
        async with sm() as db:
            await L._player(db, sid)
            await db.commit()

        async def end_then_ban(db):
            await orig_end(db)
            if not calls["banned"] and not no_ban:
                calls["banned"] = True
                await L._ban(sm, sid)

        async def gate(db, steam_ids, *a, **kw):
            calls["gate"] += 1
            if drop_reread and calls["gate"] == 2:
                return None
            return await orig_gate(db, steam_ids, *a, **kw)
        monkeypatch.setattr(main._auto_logs, "_end_transaction", end_then_ban)
        monkeypatch.setattr(main, "_ban_lock_and_gate", gate)

        async with sm() as db:
            req = schemas.BugReportRequest(steam_id=sid, description="ban-sweep interleave")
            try:
                out = ("admitted", await L._call(main.submit_bug_report, req=req,
                                                 request=L._req("/api/v1/bug-reports"), db=db))
            except HTTPException as e:
                await db.rollback()
                out = (e.status_code, str(e.detail))
        async with sm() as db:
            rows = (await db.execute(text(
                "SELECT count(*) FROM bug_reports WHERE steam_id = :s"), {"s": sid})).scalar()
        return out, rows

    got, rows = L._with_sm(case, body, mode)
    return got, rows, calls


def test_f4_a_bug_report_ban_between_its_transactions_is_refused_in_the_writing_one(
        case, mode, monkeypatch):
    got, rows, calls = _bug_report_ban_between_t1_and_t2(case, mode, monkeypatch)
    assert calls == {"gate": 2, "banned": True}, calls     # T2 was reached
    assert got[0] == 409 and got[1].startswith("Banned: "), got
    assert rows == 0


def test_f4_mutant_bug_report_without_the_writing_transactions_read_stores_the_report(
        case, mode, monkeypatch):
    got, rows, calls = _bug_report_ban_between_t1_and_t2(case, mode, monkeypatch, drop_reread=True)
    assert calls == {"gate": 2, "banned": True}, calls
    assert got[0] == "admitted" and rows == 1, (got, rows)


def test_f4_control_the_same_bug_report_with_no_ban_is_stored(case, mode, monkeypatch):
    """FIX-3 2 i: the same report, both transactions, no ban anywhere: stored."""
    got, rows, calls = _bug_report_ban_between_t1_and_t2(case, mode, monkeypatch, no_ban=True)
    assert calls == {"gate": 2, "banned": False}, calls
    assert got[0] == "admitted" and rows == 1, (got, rows)


def test_f4_control_without_a_ban_the_grant_pays_once(case, mode, monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", INTERNAL_KEY)

    async def body(sm):
        sid = L._sid()
        disc = "8801" + sid[-8:]
        async with sm() as db:
            await L._player(db, sid, discord_id=disc)
            await db.commit()
        async with sm() as db:
            ans = await L._call(main.booster_grant, discord_id=disc, month="2026-11",
                                x_internal_key=INTERNAL_KEY, db=db)
            await db.commit()
        return ans

    assert L._with_sm(case, body, mode)["status"] == "granted"


def test_f4_mutant_the_helper_without_its_lock_lets_the_grant_stand(case, mode, monkeypatch):
    """The helper's lock removed: the route does not wait and pays."""
    monkeypatch.setenv("API_SECRET_KEY", INTERNAL_KEY)

    async def unlocked(db, steam_ids, request=None, actor=None):
        ids = sorted({str(s) for s in steam_ids if s})
        await main._ban_gate_any_or_raise(db, actor, ids, request)

    monkeypatch.setattr(main, "_ban_lock_and_gate", unlocked)

    async def body(sm):
        sid = L._sid()
        disc = "8802" + sid[-8:]
        async with sm() as db:
            await L._player(db, sid, discord_id=disc)
            await db.commit()

        async def route(db):
            return await L._call(main.booster_grant, discord_id=disc, month="2026-11",
                                 x_internal_key=INTERNAL_KEY, db=db)

        return await _interleave(sm, sid, route)

    waited, got = L._with_sm(case, body, mode)
    assert not waited and got[0] == "admitted", got


def test_f4_a_deferred_1v2_settle_waits_for_a_committing_ban_and_records_nothing(case, mode):
    """The F1 writer's check holds the same lock: a journaled settle of a
    report naming the account waits for the ban and refuses for good."""
    import uuid

    async def body(sm):
        sids, pids, os_id = await L._ovt_world(sm)

        async def route(db):
            return await main._settle_ovt_report(
                db, L._ovt_report(os_id, *sids, sids[0]), in_window=True)

        waited, got = await _interleave(sm, sids[1], route)
        return waited, got, await L._ovt_rows(sm, os_id)

    waited, got, rows = L._with_sm(case, body, mode)
    assert waited, got
    assert got[0] == 409, got
    assert rows == 0
