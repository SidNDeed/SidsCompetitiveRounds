"""NX6: account deletion clears the Stage 2 readmission tables (in the form
of the FFA S8 scrub).

After delete_player_data no table migration 383 created holds the deleted
player's id or Steam id in any column, read as the whole row's text: the
player's live hold ended and was deleted with its attempt and open-attempt
rows, the player's presence row and journal rows are gone, another
fighter's beat and another reporter's journaled payload keep their rows
with the Steam id replaced, and a window the player settled keeps its
result with settled_reporter_id NULL.

Runs on the hold suite's case schema (its Env and seeding).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))
sys.path.insert(0, HERE)

import cf_asm  # noqa: E402
import test_match_hold_pg as hold_test  # noqa: E402
import test_match_hold_reports_pg as reports_test  # noqa: E402
import main  # noqa: E402

NEW_TABLES = ("match_games", "match_seat_presence", "match_seat_holds",
              "match_hold_open_attempts", "match_hold_attempts",
              "match_report_windows", "match_report_journal")


async def _naming(env, needle):
    out = {}
    for t in NEW_TABLES:
        n = await env.conn.fetchval(
            "SELECT count(*) FROM %s x WHERE strpos(CAST(x AS text), $1) > 0" % t, needle)
        if n:
            out[t] = n
    return out


def test_nx6_deletion_leaves_no_stage2_row_naming_the_player(monkeypatch):
    async def body(env):
        reports_test._mount(env, monkeypatch)
        s, g, hid = await hold_test.held(env, "team")
        await hold_test.claim(env, s, 1, hid)
        await hold_test.beat(env, s, 0, seen=[(10, s.steam(0)), (21, s.steam(1))])
        for i in (0, 2, 3, 1):
            r = await reports_test.post_report("team", s, i, g)
            assert r.status_code == 202, ("NX6 journal", i, r.status_code, r.text[:300])
        await env.conn.execute(
            "UPDATE match_report_windows SET settled_at = clock_timestamp(), settled_cls = 'c',"
            "       settled_reporter_id = $2 WHERE room_name = $1", s.room, s.pid(1))
        pid, steam = str(s.pid(1)), s.steam(1)
        before = (await _naming(env, pid), await _naming(env, steam))
        assert set(before[0]) >= {"match_seat_holds", "match_seat_presence",
                                  "match_hold_open_attempts", "match_report_windows",
                                  "match_report_journal"} and \
            set(before[1]) >= {"match_seat_presence", "match_report_journal"}, \
            ("NX6 fixture names the player", before)
        others_before = await env.conn.fetchval(
            "SELECT count(*) FROM match_report_journal WHERE room_name = $1 AND reporter_id <> $2",
            s.room, s.pid(1))

        monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)
        sig = reports_test._sig("delete:%s" % steam)
        async with env.sm() as db:
            await main.delete_player_data(steam, cf_asm.FakeRequest(), sig=sig, _slot=None, db=db)

        after = (await _naming(env, pid), await _naming(env, steam))
        assert after == ({}, {}), ("NX6 no identity", after)
        kept = await env.conn.fetchval(
            "SELECT count(*) FROM match_report_journal WHERE room_name = $1", s.room)
        win = await env.conn.fetchrow(
            "SELECT settled_at, settled_reporter_id FROM match_report_windows WHERE room_name = $1",
            s.room)
        assert (kept, win["settled_at"] is not None, win["settled_reporter_id"]) == \
            (others_before, True, None), ("NX6 others kept", kept, dict(win))
    hold_test.run_env(monkeypatch, body, prefix="rjs2nx6")


# H4: deletion serialization at every new identity writer, with real PostgreSQL
# guard probes. PostgreSQL rows are LEFT by the VM author pass.
import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


async def _fix1_h4_delete(env, s, victim, monkeypatch, owner=None):
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)
    steam = s.steam(victim)
    async with env.sm() as db:
        if owner is not None:
            owner["delete"] = db
        return await main.delete_player_data(
            steam, cf_asm.FakeRequest(), sig=reports_test._sig("delete:%s" % steam),
            _slot=None, db=db)


async def _fix1_h4_clean(env, s, victim):
    found = (await _naming(env, str(s.pid(victim))),
             await _naming(env, s.steam(victim)))
    assert found == ({}, {}), ("FIX1 H4 no identity", found)


async def _fix1_h4_wait(task, event):
    waiter = asyncio.create_task(event.wait())
    done, _ = await asyncio.wait((task, waiter), timeout=10,
                                 return_when=asyncio.FIRST_COMPLETED)
    if not event.is_set():
        waiter.cancel()
        if task.done():
            task.result()
        raise AssertionError(("FIX1 H4 barrier", len(done)))
    await waiter


@pytest.mark.parametrize("mode", ["team", "ovt"])
@pytest.mark.parametrize("order", ["deletion_first", "writer_first"])
@pytest.mark.parametrize("caller", [0, 1])
def test_fix1_h4_beat_deletion_orders_and_survivors(monkeypatch, mode, order, caller):
    async def body(env):
        reports_test._mount(env, monkeypatch)
        s, g, hid = await hold_test.held(env, mode)
        await hold_test.claim(env, s, 1, hid)
        for i in range(len(s.seats)):
            response = await reports_test.post_report(mode, s, i, g)
            assert response.status_code == 202, ("FIX1 H4 fixture", response.text)
        victim = 1
        state = {}
        parked, proceed, writer_seen = asyncio.Event(), asyncio.Event(), asyncio.Event()
        execute, commit = AsyncSession.execute, AsyncSession.commit

        async def observed_execute(db, statement, params=None, *args, **kwargs):
            sql = str(statement)
            is_writer = db is not state.get("delete")
            if is_writer and (
                    ("pg_advisory_xact_lock(hashtext(:sid))" in sql
                     and (params or {}).get("sid") == s.steam(victim))
                    or "INSERT INTO match_seat_presence" in sql):
                writer_seen.set()
            if (order == "writer_first" and is_writer
                    and "INSERT INTO match_seat_presence" in sql
                    and not parked.is_set()):
                parked.set()
                await proceed.wait()
            return await execute(db, statement, params, *args, **kwargs)

        async def observed_commit(db):
            if order == "deletion_first" and db is state.get("delete"):
                parked.set()
                await proceed.wait()
            return await commit(db)

        monkeypatch.setattr(AsyncSession, "execute", observed_execute)
        monkeypatch.setattr(AsyncSession, "commit", observed_commit)

        async def write():
            return await env.post("/api/v1/match/hold/beat", s.steam(caller), {
                "steam_id": s.steam(caller), "mode": mode, "series_id": str(s.sid),
                "room": s.room, "actor": 10 + caller,
                "seen": [{"actor": 11, "u_id": s.steam(victim)},
                         {"actor": 10, "u_id": s.steam(0)}]})

        tasks = []
        try:
            if order == "writer_first":
                writer = asyncio.create_task(write())
                tasks.append(writer)
                await _fix1_h4_wait(writer, parked)
                for steam in {s.steam(caller), s.steam(victim)}:
                    unlocked = await env.conn.fetchval(
                        "SELECT pg_try_advisory_xact_lock(hashtext($1))", steam)
                    assert not unlocked, ("FIX1 H4 beat guard", caller, steam == s.steam(victim))
                deleter = asyncio.create_task(_fix1_h4_delete(
                    env, s, victim, monkeypatch, state))
                tasks.append(deleter)
                proceed.set()
            else:
                deleter = asyncio.create_task(_fix1_h4_delete(
                    env, s, victim, monkeypatch, state))
                tasks.append(deleter)
                await _fix1_h4_wait(deleter, parked)
                writer = asyncio.create_task(write())
                tasks.append(writer)
                await _fix1_h4_wait(writer, writer_seen)
                proceed.set()
            result = await asyncio.wait_for(writer, 20)
            deletion = await asyncio.wait_for(deleter, 20)
            assert deletion["status"] == "anonymized", ("FIX1 H4 deletion", deletion)
            if order == "deletion_first" and caller == victim:
                assert result.status_code in (200, 404), ("FIX1 H4 deleted beat", result.text)
                if result.status_code == 200:
                    assert result.json().get("status") == "refused", result.text
            else:
                assert result.status_code == 200, ("FIX1 H4 live beat", result.text)
        finally:
            proceed.set()
            await asyncio.gather(*tasks, return_exceptions=True)
        monkeypatch.setattr(AsyncSession, "execute", execute)
        monkeypatch.setattr(AsyncSession, "commit", commit)
        await hold_test.beat(env, s, 0, seen=[(11, s.steam(victim)), (10, s.steam(0))])
        report = await reports_test.post_report(mode, s, 0, g)
        assert report.status_code in (400, 403, 404, 202), ("FIX1 H4 survivor report", report.text)
        await _fix1_h4_clean(env, s, victim)
        seen = await env.conn.fetchval(
            "SELECT seen FROM match_seat_presence WHERE room_name=$1 AND player_id=$2",
            s.room, s.pid(0))
        assert s.steam(0) in str(seen), ("FIX1 H4 live peer kept", seen)
    hold_test.run_env(monkeypatch, body, prefix="fix1h4beat")


@pytest.mark.parametrize("writer", [
    "ledger_final", "ledger_claim", "hold_open", "attempt",
    "mine", "claim", "claim_audit", "bind", "entered", "end",
])
def test_fix1_h4_each_hold_writer_guards_before_downstream_lock(monkeypatch, writer):
    async def body(env):
        module = hold_test.match_hold
        reports_test._mount(env, monkeypatch)
        if writer == "hold_open":
            s, g, _ = await hold_test.opened_series(env, "team")
            hid = None
        else:
            s, g, hid = await hold_test.held(env, "team")
        if writer in ("bind", "entered"):
            await hold_test.claim(env, s, 1, hid)
            await hold_test.beat(env, s, 0, seen=[(21, s.steam(1))])
        if writer == "entered":
            bound = await hold_test.bind(env, s, 1, hid, 21)
            assert bound["status"] == "bound", ("FIX1 H4 bound fixture", bound)
        request = module.HoldOpenReq(
            request_id="fix1h4" + uuid.uuid4().hex[:12],
            opener_steam_id=s.steam(0), held_steam_id=s.steam(1),
            mode="team", room=s.room, game_id=g, slot=1, team=0,
            t1_points=1, t2_points=0)
        reached, release = asyncio.Event(), asyncio.Event()
        execute = AsyncSession.execute
        hold_locks = 0
        if writer == "claim_audit":
            async def refused_gate(db, *args, **kwargs):
                return False, await module._ctx_now(db)
            monkeypatch.setattr(main, "_lease_admission_gate", refused_gate)

        async def observed(db, statement, params=None, *args, **kwargs):
            nonlocal hold_locks
            sql = str(statement)
            if "FROM match_seat_holds" in sql and "FOR NO KEY UPDATE" in sql:
                hold_locks += 1
            target = (
                (writer in ("ledger_final", "ledger_claim", "hold_open")
                 and "INSERT INTO match_hold_open_attempts" in sql)
                or (writer == "claim" and "FROM team_series" in sql and "FOR NO KEY UPDATE" in sql)
                or (writer == "claim_audit" and hold_locks == 2
                    and "FROM match_seat_holds" in sql and "FOR NO KEY UPDATE" in sql)
                or (writer not in ("ledger_final", "ledger_claim", "hold_open", "claim", "claim_audit")
                    and "FROM match_seat_holds" in sql and "FOR NO KEY UPDATE" in sql))
            if target and not reached.is_set():
                reached.set()
                await release.wait()
            return await execute(db, statement, params, *args, **kwargs)

        async def write():
            if writer in ("ledger_final", "ledger_claim", "attempt"):
                async with env.sm() as db:
                    now = await module._ctx_now(db)
                    if writer == "ledger_final":
                        await module._write_open_attempt(
                            db, request, s.room, s.pid(1), s.pid(0), now,
                            "refused", "fixture", None)
                    elif writer == "ledger_claim":
                        await module._claim_open_ledger(
                            db, request, s.room, s.pid(1), s.pid(0))
                        await module._finish_open_attempt(
                            db, request, now, "refused", "fixture", None)
                    else:
                        await module._attempt(db, hid, "offered", now, "ok")
                    await db.commit()
                return None
            if writer == "hold_open":
                return await hold_test.open_hold(env, s, 1, 0, g)
            if writer == "mine":
                return await env.get("/api/v1/match/hold/mine", s.steam(1),
                                     params={"steam_id": s.steam(1)})
            if writer in ("claim", "claim_audit"):
                return await hold_test.claim(env, s, 1, hid)
            if writer == "bind":
                return await hold_test.bind(env, s, 1, hid, 21)
            if writer == "entered":
                return await hold_test.entered(env, s, 1, hid, g, 21)
            return await env.post("/api/v1/match/hold/%s/end" % hid, s.steam(0),
                                  {"steam_id": s.steam(0), "reason": "survivor_leave"})

        monkeypatch.setattr(AsyncSession, "execute", observed)
        task = asyncio.create_task(write())
        try:
            await _fix1_h4_wait(task, reached)
            for i in (0, 1):
                unlocked = await env.conn.fetchval(
                    "SELECT pg_try_advisory_xact_lock(hashtext($1))", s.steam(i))
                assert not unlocked, ("FIX1 H4 writer guard", writer, i)
        finally:
            release.set()
            result = await asyncio.wait_for(task, 20)
            monkeypatch.setattr(AsyncSession, "execute", execute)
        if result is not None:
            if isinstance(result, dict):
                assert result.get("status") in ("claimed", "bound", "entered", "refused"), (
                    "FIX1 H4 writer answer", writer, result)
            else:
                assert result.status_code == 200, ("FIX1 H4 writer answer", writer, result.text)
        await _fix1_h4_delete(env, s, 1, monkeypatch)
        await _fix1_h4_clean(env, s, 1)
    hold_test.run_env(monkeypatch, body, prefix="fix1h4writers")


@pytest.mark.parametrize("writer", ["ledger_final", "ledger_claim"])
def test_fix1_h4_audit_revalidates_deleted_identity(monkeypatch, writer):
    async def body(env):
        module = hold_test.match_hold
        s, g, _ = await hold_test.opened_series(env, "team")
        req = module.HoldOpenReq(
            request_id="fix1h4audit" + uuid.uuid4().hex[:8],
            opener_steam_id=s.steam(0), held_steam_id=s.steam(1),
            mode="team", room=s.room, game_id=g, slot=1, team=0,
            t1_points=1, t2_points=0)
        await _fix1_h4_delete(env, s, 1, monkeypatch)
        async with env.sm() as db:
            with pytest.raises(hold_test.HTTPException) as caught:
                if writer == "ledger_final":
                    await module._write_open_attempt(
                        db, req, s.room, s.pid(1), s.pid(0), await module._ctx_now(db),
                        "refused", "other_mode", None)
                else:
                    await module._claim_open_ledger(db, req, s.room, s.pid(1), s.pid(0))
            assert caught.value.status_code == 404, ("FIX1 H4 stale audit", writer)
            await db.rollback()
        await _fix1_h4_clean(env, s, 1)
    hold_test.run_env(monkeypatch, body, prefix="fix1h4audit")


@pytest.mark.parametrize("writer", [
    "journal", "mark", "receive", "settle", "release", "supersede", "finish", "route",
])
def test_fix1_h4_report_writers_guard_before_their_first_lock(monkeypatch, writer):
    async def body(env):
        import json
        reports_test._mount(env, monkeypatch)
        mrw = main._mrw_mod()
        s, g, hid = await hold_test.held(env, "team")
        payload = json.dumps(reports_test.team_report(s, 0, g))
        if writer == "mark":
            async with env.sm() as db:
                await mrw.lock_window(db, mode="team", room=s.room, game_id=g,
                                      now=await hold_test.match_hold._ctx_now(db))
                await db.commit()
        reached, release = asyncio.Event(), asyncio.Event()
        execute = AsyncSession.execute
        select_game = main._report_window_game

        async def observed(db, statement, params=None, *args, **kwargs):
            sql = str(statement)
            target = (
                (writer == "journal" and "INSERT INTO match_report_journal" in sql)
                or (writer == "mark" and "UPDATE match_report_windows SET settled_at" in sql)
                or (writer not in ("journal", "mark", "route")
                    and "INSERT INTO match_report_windows" in sql))
            if target and not reached.is_set():
                reached.set()
                await release.wait()
            return await execute(db, statement, params, *args, **kwargs)

        async def observed_game(*args, **kwargs):
            reached.set()
            await release.wait()
            return await select_game(*args, **kwargs)

        async def settled(*args):
            return None

        async def write():
            if writer == "route":
                return await reports_test.post_report("team", s, 0, g)
            async with env.sm() as db:
                now = await hold_test.match_hold._ctx_now(db)
                common = dict(mode="team", room=s.room, game_id=g, now=now)
                if writer == "journal":
                    result = await mrw.journal(
                        db, **common, reporter_id=s.pid(0), reporter_steam=s.steam(0),
                        cls="c", payload=payload, held=True)
                elif writer == "mark":
                    result = await mrw._mark_settled(
                        db, s.room, g, {"reporter_id": s.pid(0), "cls": "c"}, now)
                elif writer == "receive":
                    result = await mrw.receive(
                        db, **common, reported_game_id=g, reporter_id=s.pid(0),
                        reporter_steam=s.steam(0), payload=payload,
                        member_ids=[s.pid(i) for i in range(len(s.seats))],
                        settle=settled, held=True)
                elif writer == "settle":
                    result = await mrw.settle_window(db, **common, settle=settled)
                elif writer == "release":
                    result = await mrw.release_held(db, **common, settle=settled)
                elif writer == "supersede":
                    result = await mrw.supersede_held(db, **common)
                else:
                    result = await mrw.finish_hold(db, **common, hold_id=hid, settle=settled)
                await db.commit()
                return result

        monkeypatch.setattr(AsyncSession, "execute", observed)
        if writer == "route":
            monkeypatch.setattr(main, "_report_window_game", observed_game)
        task = asyncio.create_task(write())
        try:
            await _fix1_h4_wait(task, reached)
            for i in range(len(s.seats)):
                unlocked = await env.conn.fetchval(
                    "SELECT pg_try_advisory_xact_lock(hashtext($1))", s.steam(i))
                assert not unlocked, ("FIX1 H4 report guard", writer, i)
        finally:
            release.set()
            result = await asyncio.wait_for(task, 20)
            monkeypatch.setattr(AsyncSession, "execute", execute)
            monkeypatch.setattr(main, "_report_window_game", select_game)
        if writer == "route":
            assert result.status_code == 202, ("FIX1 H4 route answer", result.text)
        await _fix1_h4_delete(env, s, 1, monkeypatch)
        await _fix1_h4_clean(env, s, 1)
    hold_test.run_env(monkeypatch, body, prefix="fix1h4reports")


def test_fix1_h4_terminal_release_preserves_cleared_attribution(monkeypatch):
    async def body(env):
        reports_test._mount(env, monkeypatch)
        s, g, hid = await hold_test.held(env, "team")
        report = await reports_test.post_report("team", s, 0, g)
        assert report.status_code == 202, ("FIX1 H4 held fixture", report.text)
        await env.conn.execute(
            "UPDATE match_report_windows SET settled_at=clock_timestamp(),"
            " settled_reporter_id=$2, settled_cls='c' WHERE room_name=$1", s.room, s.pid(1))
        await _fix1_h4_delete(env, s, 1, monkeypatch)
        called = []

        async def settled(*args):
            called.append(True)

        async with env.sm() as db:
            await main._mrw_mod().release_held(
                db, mode="team", room=s.room, game_id=g,
                now=await hold_test.match_hold._ctx_now(db), settle=settled)
            await db.commit()
        win = await env.conn.fetchrow(
            "SELECT settled_at,settled_reporter_id FROM match_report_windows WHERE room_name=$1",
            s.room)
        states = await env.conn.fetch(
            "SELECT state FROM match_report_journal WHERE room_name=$1", s.room)
        assert win["settled_at"] is not None and win["settled_reporter_id"] is None, (
            "FIX1 H4 cleared attribution", dict(win))
        assert not called and all(row["state"] == "kept" for row in states), (
            "FIX1 H4 terminal disposition", called, states)
        await _fix1_h4_clean(env, s, 1)
    hold_test.run_env(monkeypatch, body, prefix="fix1h4terminal")


@pytest.mark.parametrize("mode", ["team", "ovt"])
def test_fix1_h4_deletion_terminalizes_hold_without_journal(monkeypatch, mode):
    async def body(env):
        reports_test._mount(env, monkeypatch)
        s, g, _ = await hold_test.held(env, mode)
        assert await env.conn.fetchval(
            "SELECT count(*) FROM match_report_journal WHERE room_name=$1", s.room) == 0
        await _fix1_h4_delete(env, s, 1, monkeypatch)
        win = await env.conn.fetchrow(
            "SELECT settled_at,superseded_at,settled_reporter_id"
            " FROM match_report_windows WHERE room_name=$1 AND game_id=$2::uuid", s.room, g)
        assert win is not None and win["superseded_at"] is not None, (
            "FIX1 H4 deleted hold terminal", dict(win) if win is not None else None)
        assert win["settled_at"] is None and win["settled_reporter_id"] is None
        await _fix1_h4_clean(env, s, 1)
    hold_test.run_env(monkeypatch, body, prefix="fix1h4closed")


def test_fix1_h4_janitor_retry_reacquires_identity_guards(monkeypatch):
    async def body(env):
        import json
        reports_test._mount(env, monkeypatch)
        mrw = main._mrw_mod()
        s, g, _ = await hold_test.opened_series(env, "team")
        async with env.sm() as db:
            now = await hold_test.match_hold._ctx_now(db)
            await mrw.lock_window(db, mode="team", room=s.room, game_id=g, now=now)
            await mrw.journal(
                db, mode="team", room=s.room, game_id=g, now=now,
                reporter_id=s.pid(0), reporter_steam=s.steam(0), cls="c",
                payload=json.dumps(reports_test.team_report(s, 0, g)))
            await db.commit()
        await env.conn.execute(
            "UPDATE match_report_windows SET settle_after=clock_timestamp()-interval '1 second'"
            " WHERE room_name=$1", s.room)

        def refuse(*args, **kwargs):
            async def settle(db, entry):
                raise mrw.PermanentReportRefusal(hold_test.HTTPException(400, "immutable fixture"))
            return settle
        monkeypatch.setattr(main, "_report_window_settler", refuse)
        reached, release = asyncio.Event(), asyncio.Event()
        execute = AsyncSession.execute
        windows = 0

        async def observed(db, statement, params=None, *args, **kwargs):
            nonlocal windows
            if "INSERT INTO match_report_windows" in str(statement):
                windows += 1
                if windows == 2:
                    reached.set()
                    await release.wait()
            return await execute(db, statement, params, *args, **kwargs)
        monkeypatch.setattr(AsyncSession, "execute", observed)
        task = asyncio.create_task(main._report_window_janitor())
        try:
            await _fix1_h4_wait(task, reached)
            for i in range(len(s.seats)):
                unlocked = await env.conn.fetchval(
                    "SELECT pg_try_advisory_xact_lock(hashtext($1))", s.steam(i))
                assert not unlocked, ("FIX1 H4 retry guard", i)
        finally:
            release.set()
            result = await asyncio.wait_for(task, 20)
            monkeypatch.setattr(AsyncSession, "execute", execute)
        assert result.get("refused") == 1, ("FIX1 H4 retry disposition", result)
        await _fix1_h4_delete(env, s, 1, monkeypatch)
        await _fix1_h4_clean(env, s, 1)
    hold_test.run_env(monkeypatch, body, prefix="fix1h4retry")


@pytest.mark.parametrize("mode", ["team", "ovt"])
def test_fix1_h4_receipt_identity_wait_is_bounded(monkeypatch, mode):
    """A deletion identity lock cannot outlive the report admission budget."""
    async def body(env):
        reports_test._mount(env, monkeypatch)
        module = hold_test.match_hold
        s, g, _ = await hold_test.opened_series(env, mode)
        monkeypatch.setattr(module, "DB_LOCK_TIMEOUT_MS", 100)
        monkeypatch.setattr(module, "DB_STATEMENT_TIMEOUT_MS", 250)
        monkeypatch.setattr(module, "DB_REQUEST_TIMEOUT_S", 1.0)
        blocker = env.conn.transaction()
        await blocker.start()
        await env.conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", s.steam(0))
        rollbacks = []
        rollback = AsyncSession.rollback

        async def observed_rollback(db, *args, **kwargs):
            result = await rollback(db, *args, **kwargs)
            rollbacks.append(not db.in_transaction())
            return result

        monkeypatch.setattr(AsyncSession, "rollback", observed_rollback)
        try:
            try:
                response = await asyncio.wait_for(
                    reports_test.post_report(mode, s, 0, g), timeout=3)
            except asyncio.TimeoutError as exc:
                raise AssertionError(("FIX1 H4 receipt bound", mode, "watchdog expired")) from exc
            assert response.status_code == 503 and response.json().get("detail") == "database_deadline", (
                "FIX1 H4 receipt bound", mode, response.status_code, response.text)
            assert rollbacks and all(rollbacks), ("FIX1 H4 receipt whole rollback", mode, rollbacks)
        finally:
            await blocker.rollback()
            monkeypatch.setattr(AsyncSession, "rollback", rollback)
        for table in ("match_report_windows", "match_report_journal"):
            assert await env.conn.fetchval(
                "SELECT count(*) FROM " + table + " WHERE room_name=$1", s.room) == 0, (
                    "FIX1 H4 receipt no partial write", mode, table)
        assert not await reports_test.recorded(env, mode, s), ("FIX1 H4 receipt no settlement", mode)
        retried = await reports_test.post_report(mode, s, 0, g)
        assert retried.status_code == 202, ("FIX1 H4 receipt retry", mode, retried.text)
    hold_test.run_env(monkeypatch, body, prefix="fix1h4bound")
