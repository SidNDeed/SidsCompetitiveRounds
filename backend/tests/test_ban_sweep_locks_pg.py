"""Bans part 2a, FIX-2 classes V and VI against a real PostgreSQL: what the
static census (test_ban_sweep_locks.py) cannot read from the syntax.

  * steam_auth holds no identity key across the Steam call (a blocked stub
    holds the call open while another connection takes the account's key),
    and its writing transaction takes the key EXCLUSIVE (a shared holder makes
    it wait; the mutant that asks the key shared does not wait).
  * report_casual_dc takes the leaver's key EXCLUSIVE in its one taking call
    (the merged take: a shared holder makes it wait; the shared mutant not).
  * the settle gate's TYPED P2a entry is tested in test_ban_sweep_window_pg.py.

    LADDER_TEST_PG_DSN / CF_TEST_PG_DSN = the lane database
"""
import asyncio
import os
import sys
import threading
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402,F401
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

import main  # noqa: E402
import test_ban_sweep_live as L  # noqa: E402
from test_ban_sweep_live import case, soft  # noqa: E402,F401  (fixtures)


async def _waiting(sm):
    async with sm() as probe:
        return (await probe.execute(text(
            "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid"
            " WHERE NOT l.granted AND l.locktype = 'advisory'"
            " AND a.datname = current_database() AND l.pid <> pg_backend_pid()"))).scalar()


async def _run_route(sm, route):
    async with sm() as db:
        try:
            out = await route(db)
            await db.commit()
            return ("admitted", out)
        except HTTPException as e:
            await db.rollback()
            return (e.status_code, str(e.detail))


async def _behind_shared(sm, sid, route, before=None):
    """Hold the SHARED identity key of sid on one connection, run `route`
    (after awaiting `before(task)` when given), and return (waited, answer)."""
    holder = sm()
    try:
        await holder.execute(text("SELECT pg_advisory_xact_lock_shared(hashtext(CAST(:s AS text)))"),
                             {"s": sid})
        task = asyncio.create_task(_run_route(sm, route))
        if before is not None:
            await before(task)
        waited = False
        for _ in range(200):                     # bound: about ten seconds
            await asyncio.sleep(0.05)
            if task.done():
                break
            if await _waiting(sm):
                waited = True
                break
        await holder.rollback()
    finally:
        await holder.close()
    return waited, await task


def _shared_gate(monkeypatch):
    """The mutant: every exclusive= of the gate is asked shared."""
    orig = main._ban_lock_and_gate

    async def mut(db, steam_ids, *a, exclusive=(), **kw):
        return await orig(db, list(steam_ids) + list(exclusive or ()), *a, **kw)
    monkeypatch.setattr(main, "_ban_lock_and_gate", mut)


# ------------------------------------------------------------- steam_auth

def _steam_stub(monkeypatch, sid):
    entered, release = threading.Event(), threading.Event()

    def stub(url, timeout):
        entered.set()
        release.wait(20)
        return {"response": {"params": {"result": "OK", "steamid": sid}}}
    monkeypatch.setattr(main, "_steam_http_get_json", stub)
    monkeypatch.setenv("STEAM_WEB_API_KEY", "ban-sweep-steam-key")
    return entered, release


def _steam_route(sid):
    async def route(db):
        req = main.SteamAuthRequest(steam_id=sid, ticket_hex="abcd", mod_version="1.41.0")
        return await L._call(main.steam_auth, req=req, db=db)
    return route


async def _wait_entered(entered):
    for _ in range(200):
        if entered.is_set():
            return True
        await asyncio.sleep(0.05)
    return False


def test_vi_steam_auth_holds_no_identity_key_across_the_steam_call(case, soft, monkeypatch):
    """While the Steam call is in flight another connection takes the
    account's identity key EXCLUSIVE at once: nothing of the route holds it."""
    sid = L._sid()
    entered, release = _steam_stub(monkeypatch, sid)

    async def body(sm):
        async with sm() as db:
            await L._player(db, sid)
            await db.commit()
        task = asyncio.create_task(_run_route(sm, _steam_route(sid)))
        try:
            assert await _wait_entered(entered), "the Steam call was never reached"
            async with sm() as probe:
                free = (await probe.execute(text(
                    "SELECT pg_try_advisory_xact_lock(hashtext(CAST(:s AS text)))"), {"s": sid})).scalar()
                await probe.rollback()
        finally:
            release.set()
        return free, await task

    free, got = L._with_sm(case, body)
    assert free is True, ("a key was held across the Steam call", got)
    assert got[0] == "admitted", got


def test_vi_steam_auth_writing_transaction_takes_the_key_exclusive(case, soft, monkeypatch):
    sid = L._sid()
    entered, release = _steam_stub(monkeypatch, sid)

    async def body(sm):
        async with sm() as db:
            await L._player(db, sid)
            await db.commit()

        async def before(task):
            assert await _wait_entered(entered)
            release.set()
        return await _behind_shared(sm, sid, _steam_route(sid), before)

    waited, got = L._with_sm(case, body)
    assert waited and got[0] == "admitted", (waited, got)


def test_vi_mutant_steam_auth_asking_the_key_shared_does_not_wait(case, soft, monkeypatch):
    sid = L._sid()
    entered, release = _steam_stub(monkeypatch, sid)
    _shared_gate(monkeypatch)

    async def body(sm):
        async with sm() as db:
            await L._player(db, sid)
            await db.commit()

        async def before(task):
            assert await _wait_entered(entered)
            release.set()
        return await _behind_shared(sm, sid, _steam_route(sid), before)

    waited, got = L._with_sm(case, body)
    assert not waited and got[0] == "admitted", (waited, got)


# ------------------------------------------------------------- casual DC

def _casual_route(rep, lv):
    async def route(db):
        return await L._call(main.report_casual_dc, request=L._req("/api/v1/casual-dc"),
                             reporter_steam_id=rep, leaver_steam_id=lv,
                             room_id="bs_room_" + uuid.uuid4().hex[:8], db=db)
    return route


def _casual_body(rep, lv):
    async def body(sm):
        async with sm() as db:
            await L._player(db, rep)
            await L._player(db, lv)
            await db.commit()
        return await _behind_shared(sm, lv, _casual_route(rep, lv))
    return body


def test_v_casual_dc_takes_the_leaver_key_exclusive_in_its_one_taking_call(case, soft):
    rep, lv = L._sid(), L._sid()
    waited, got = L._with_sm(case, _casual_body(rep, lv))
    assert waited and got[0] == "admitted", (waited, got)


def test_v_mutant_casual_dc_asking_the_leaver_key_shared_does_not_wait(case, soft, monkeypatch):
    _shared_gate(monkeypatch)
    rep, lv = L._sid(), L._sid()
    waited, got = L._with_sm(case, _casual_body(rep, lv))
    assert not waited and got[0] == "admitted", (waited, got)

