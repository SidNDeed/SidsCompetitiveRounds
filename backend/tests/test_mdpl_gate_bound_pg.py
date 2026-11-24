"""MDPL-GATE-REREAD-1 F1 (round mdplg-r1, finding 1; round mdplg-r2, finding
1): the four routes of part (b) take their player's deletion key SHARED only
through main._player_deletion_key_shared_bounded, which waits at most
main.PLAYER_DELETION_KEY_TIMEOUT_MS and answers 503 "identity_busy" past it.
The deletion key is main's two-key class PLAYER_DELETION_LOCK_CLASS over
hashtext of the steam id; delete_player_data alone takes it EXCLUSIVE,
directly after its identity key. The four routes take no identity key.

  route                      the key's id
  toggle_ranked              the path's steam_id
  unlock_achievement         req.steam_id
  admin_grant_achievement    req.target_steam_id
  generate_link_code         the query's steam_id

On PostgreSQL through inv_pg, with test_mdpl_gate_reread_b_pg.py's scenes
(SCENES: the seeds, the calls and the answer each route gives without a
deletion), its _scene for the control and its DELETION_KEY_SQL, the deletion
key's statement built from main's own text. Every statement a second session
sends for the deletion key is built that way (deletion_key_sql); none is typed.

r1, a bound row per route: the row sets the constant small (SMALL_MS); a
second session H holds P's deletion key EXCLUSIVE in an open transaction for
the whole call. Then, in this order: the route answers (503, "identity_busy")
inside the bound plus MARGIN_S, and not before the bound; it printed ONE
"[LOCK]" line, which names neither P's raw id nor P's id; every table of the
case schema counts the same rows as before the call, and P's row is the same
in every column; lock_timeout in the request's session reads after the
helper what it read before it; and once H has ended, another session takes
P's deletion key EXCLUSIVE at once (the try form), so the refused request
left nothing holding it.

r2, per route: a second session holds P's IDENTITY key EXCLUSIVE in an open
transaction for the whole call. The route answers as it does with no holder
and stores what it stores then (_stored), in less than half the bound: it
asks for no identity key.

r3, generate_link_code: a second session L holds P's link code row (FOR
UPDATE); the request takes its key and waits at its DELETE of P's link codes
on L. While it waits, pg_locks shows the request's backend holding P's
deletion key, granted, SHARE; a third session then takes P's IDENTITY key
EXCLUSIVE at once (the try form), and pg_locks shows the request still
holding its key after that. L ends; the request answers as before.

r4, toggle_ranked: a second session holds P's deletion key SHARED for the
whole call; the route answers as before, inside the bound: two shared
holders do not wait on each other.

r5, the real deletion against generate_link_code, with no key statement of
the test's own: the request stands after its key (_stand_after_key: the
route's own call of the read by id reads, then waits for the row's word; a
held link code row would also be met by the deletion itself, which deletes
P's link codes, so it cannot stand in here). (A) The request stands
throughout: with the module's budget made SHORT_BUDGET_S for the row, the
real delete_player_data answers 503 account_cleanup_contended inside that
budget plus MARGIN_S, the request still standing, and P's row is not
deleted; the request then answers as before. (B) The request ends inside the
budget: the deletion waits at its deletion key on the request; the request is
let go and answers with its code; the deletion then answers "anonymized",
and no link code of P's and no row with the request's code is left. (C) The
deletion held open after its deletion key (_pc_lease_drain, its next step
after the read of P, waits for the row's word): pg_locks shows the deletion's
key EXCLUSIVE, granted; the route answers 503 "identity_busy" inside the
bound (SMALL_MS) plus MARGIN_S; the deletion is let go and answers
"anonymized"; the route then answers 404 "Player not found".

r6, the order in the database (round mdplg-r2): toggle_ranked's first
contact for a Steam id never seen creates P's row under the deletion key and
stands after its key, the row inserted and not committed. The real
deletion of that id waits at its deletion key on the request; the request is
let go and answers as before; the deletion then reads the committed row and
answers "anonymized", and no live row is left under the raw id. The order
it reads is the census row's order (e).

The control: H holds P's identity key and deletion key and ends inside the
bound (_scene: it commits as soon as the route waits on it). Each route
answers as it does at c697dc6d, having waited at the shared key, and
lock_timeout reads after the helper what it read in the same session before
it.

The census row (no database), over the source text of every .py file
directly in backend/api, its sub-folders not read (_deletion_key_census):
the class constant and the key text's constant
stand in their definitions, in the helper and in delete_player_data, nowhere
else; the class's number stands in its definition alone, and differs from
every other advisory class number defined there; each of the four function
bodies holds ONE call of the helper and NO string naming pg_advisory; the
helper's key statement is the shared lock of the key text, bound to the class
and the steam id; in delete_player_data the exclusive lock of the key text
is the statement directly after its first identity key statement, the ban
read (_ban_gate_or_raise, BAN-FIRST-1) the statement directly after it, and
the read of P by steam_id the statement directly after that, among the
function's top-level statements of every kind; two cases plant a compound
statement in that order, two more take the ban read out of it or put it
before the deletion key, and the row names part (e).

The real session check: inv_pg puts a stand-in for main._check_steam_session
in every case. One row each for toggle_ranked and unlock_achievement, whose
key comes before that check, puts the real check back, plants a verified
steam_sessions row for P and sends its token: the route waits at the key
while H holds it, then answers as before, and the real check marked the
request verified.

The product mutants (round mdplg-r1: the arming, the handler and the
disarming taken out of the helper, one route written with its inline key
statement again; round mdplg-r2: the helper on the identity key, the
deletion's key statement removed or moved below its read of P, the helper
taking the key exclusive, the two sides on two class numbers) were run on
copies of the tree and are not part of this file.
"""

import ast
import asyncio
import hashlib
import os
import re
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
sys.path.insert(0, API)
sys.path.insert(0, HERE)

from sqlalchemy import text  # noqa: E402

from inv_pg import P, Req, case  # noqa: E402

import main  # noqa: E402
import schemas  # noqa: E402
from test_mail_case_scrub_pg import BOUND, _delete, _settle  # noqa: E402
from test_mdpl_gate_reread_b_pg import (  # noqa: E402
    DELETION_KEY_SQL, GRANT_KEY, SCENES, UNLOCK_KEY, Scene, _scene, _seams, _sig, _toggle_call, deletion_key_sql, _end)
from test_mdpl_gate_reread_pg import KEY_SQL, NOT_FOUND, _row, _sid  # noqa: E402

ROUTES = ("toggle_ranked", "unlock_achievement", "admin_grant_achievement", "generate_link_code")
HELPER = "_player_deletion_key_shared_bounded"
CLASS = "PLAYER_DELETION_LOCK_CLASS"
ARGS = "_PLAYER_DELETION_KEY_ARGS"
BUSY = (503, "identity_busy")
SMALL_MS = 300
MARGIN_S = 5.0
SHORT_BUDGET_S = 6.0
TOKEN = "mdpl-bound-session-token"
# Taken at import, before any case puts inv_pg's stand-in in its place.
_REAL_CHECK = main._check_steam_session
# The deletion key's other forms, from main's text as DELETION_KEY_SQL is.
SHARED_SQL = deletion_key_sql("pg_advisory_xact_lock_shared")
TRY_SQL = deletion_key_sql("pg_try_advisory_xact_lock")
# Who holds P's deletion key: pg_locks shows a two-key advisory lock with
# classid the first key, objid the second, objsubid 2.
HOLDERS_SQL = ("SELECT pid, mode, granted FROM pg_locks WHERE locktype = 'advisory' AND objsubid = 2"
               " AND classid = CAST(CAST($1 AS integer) AS oid)"
               " AND objid = CAST(hashtext(CAST($2 AS text)) AS oid) ORDER BY pid")


async def _counts(conn):
    """Every base table of the case schema and its row count."""
    names = await conn.fetch(
        "SELECT table_name FROM information_schema.tables"
        " WHERE table_schema = current_schema() AND table_type = 'BASE TABLE' ORDER BY table_name")
    return {r["table_name"]: await conn.fetchval('SELECT count(*) FROM "%s"' % r["table_name"]) for r in names}


async def _holders(conn, sid):
    """(pid, mode, granted) of every backend that holds or asks for P's deletion key."""
    return [tuple(r) for r in await conn.fetch(HOLDERS_SQL, main.PLAYER_DELETION_LOCK_CLASS, sid)]


async def _stored(env, s, body):
    """What the route stores with no holder, read back: toggle_ranked P's
    ranked_enabled (seeded off), the two achievement routes their
    achievement row, generate_link_code its code's row."""
    c, pid = env.conn, s.p.id
    if s.route == "toggle_ranked":
        return await c.fetchval("SELECT ranked_enabled FROM players WHERE id = $1", pid) is True
    if s.route in ("unlock_achievement", "admin_grant_achievement"):
        key = UNLOCK_KEY if s.route == "unlock_achievement" else GRANT_KEY
        return await c.fetchval("SELECT count(*) FROM player_achievements WHERE player_id = $1"
                                " AND achievement_key = $2", pid, key) == 1
    return await c.fetchval("SELECT count(*) FROM link_codes WHERE player_id = $1 AND code = $2",
                            pid, body["code"]) == 1


def _timeouts(env, seen):
    """The helper as the routes reach it, recording lock_timeout in the
    request's session before it and after it, on either outcome."""
    real = main._player_deletion_key_shared_bounded

    async def helper(db, steam_id):
        before = (await db.execute(text("SHOW lock_timeout"))).scalar()
        try:
            await real(db, steam_id)
        finally:
            seen.append((steam_id, before, (await db.execute(text("SHOW lock_timeout"))).scalar()))
    env.mp.setattr(main, HELPER, helper)


# -- r1: the bound ----------------------------------------------------------------------------------

def _bound_case(monkeypatch, capsys, tmp_path, route):
    """The route's bound row, the five assertions of r1 in its order."""
    async def body(env):
        _seams(env, tmp_path)
        env.mp.setattr(main, "PLAYER_DELETION_KEY_TIMEOUT_MS", SMALL_MS, raising=False)
        seen = []
        _timeouts(env, seen)
        s = await SCENES[route](env)
        rows = await _counts(env.conn)
        left = await _row(env.conn, s.p)
        side = await env.side()
        await side.execute("BEGIN")
        await side.execute(DELETION_KEY_SQL, main.PLAYER_DELETION_LOCK_CLASS, s.p.sid)
        capsys.readouterr()
        try:
            t0 = time.monotonic()
            ans = await asyncio.wait_for(env.call(s.call), SMALL_MS / 1000.0 + MARGIN_S)
            took = time.monotonic() - t0
        finally:
            await side.execute("ROLLBACK")
        out = capsys.readouterr().out
        assert (ans.status, ans.body) == BUSY, ("answer", route, ans)
        assert took >= 0.9 * SMALL_MS / 1000.0, ("answered before the bound", route, took)
        lines = [ln for ln in out.splitlines() if ln.startswith("[LOCK]")]
        assert len(lines) == 1 and s.p.sid not in lines[0] and str(s.p.id) not in lines[0], (
            "the line", route, lines)
        now = await _counts(env.conn)
        assert now == rows, ("row counts", route, {k: (rows.get(k), now.get(k)) for k in set(rows) | set(now)
                                                    if rows.get(k) != now.get(k)})
        assert await _row(env.conn, s.p) == left, ("P's row", route)
        assert len(seen) == 1 and seen[0][0] == s.p.sid and seen[0][2] == seen[0][1], (
            "lock_timeout after the refusal", route, seen)
        free = await env.side()
        await free.execute("BEGIN")
        got = await free.fetchval(TRY_SQL, main.PLAYER_DELETION_LOCK_CLASS, s.p.sid)
        await free.execute("ROLLBACK")
        assert got is True, ("P's deletion key after the holder ended", route)
    case(monkeypatch, body, prefix="mdplbd")


def test_toggle_ranked_answers_503_inside_the_bound_while_the_deletion_key_is_held(monkeypatch, capsys, tmp_path):
    _bound_case(monkeypatch, capsys, tmp_path, "toggle_ranked")


def test_unlock_achievement_answers_503_inside_the_bound_while_the_deletion_key_is_held(monkeypatch, capsys,
                                                                                       tmp_path):
    _bound_case(monkeypatch, capsys, tmp_path, "unlock_achievement")


def test_admin_grant_achievement_answers_503_inside_the_bound_while_the_deletion_key_is_held(monkeypatch, capsys,
                                                                                            tmp_path):
    _bound_case(monkeypatch, capsys, tmp_path, "admin_grant_achievement")


def test_generate_link_code_answers_503_inside_the_bound_while_the_deletion_key_is_held(monkeypatch, capsys,
                                                                                       tmp_path):
    _bound_case(monkeypatch, capsys, tmp_path, "generate_link_code")


# -- r2: an identity key holder is not met ----------------------------------------------------------

def _identity_case(monkeypatch, tmp_path, route):
    """r2: P's identity key held EXCLUSIVE for the whole call; the route answers
    and stores as with no holder, in less than half the bound."""
    async def body(env):
        _seams(env, tmp_path)
        s = await SCENES[route](env)
        side = await env.side()
        await side.execute("BEGIN")
        await side.execute(KEY_SQL, s.p.sid)
        try:
            t0 = time.monotonic()
            ans = await asyncio.wait_for(env.call(s.call), BOUND)
            took = time.monotonic() - t0
        finally:
            await side.execute("ROLLBACK")
        assert ans.status == 200 and s.ok(ans.body), ("answer", route, ans)
        assert took < 0.5 * main.PLAYER_DELETION_KEY_TIMEOUT_MS / 1000.0, ("not well inside the bound", route, took)
        assert await _stored(env, s, ans.body), ("what the route stores", route)
    case(monkeypatch, body, prefix="mdplbd")


def test_toggle_ranked_answers_while_the_identity_key_is_held(monkeypatch, tmp_path):
    _identity_case(monkeypatch, tmp_path, "toggle_ranked")


def test_unlock_achievement_answers_while_the_identity_key_is_held(monkeypatch, tmp_path):
    _identity_case(monkeypatch, tmp_path, "unlock_achievement")


def test_admin_grant_achievement_answers_while_the_identity_key_is_held(monkeypatch, tmp_path):
    _identity_case(monkeypatch, tmp_path, "admin_grant_achievement")


def test_generate_link_code_answers_while_the_identity_key_is_held(monkeypatch, tmp_path):
    _identity_case(monkeypatch, tmp_path, "generate_link_code")


# -- r3: a request standing after its key holds no identity key ------------------------------------

def test_generate_link_code_waiting_after_its_key_leaves_the_identity_key_free(monkeypatch, tmp_path):
    """r3, the order of events: the request holds its key and waits at its
    DELETE on L; then the identity key is taken at once; the request still
    holds its key."""
    async def body(env):
        _seams(env, tmp_path)
        s = await SCENES["generate_link_code"](env)
        hold = await env.side()
        lpid = await hold.fetchval("SELECT pg_backend_pid()")
        await hold.execute("BEGIN")
        await hold.execute("SELECT 1 FROM link_codes WHERE player_id = $1 FOR UPDATE", s.p.id)
        task = asyncio.create_task(env.call(s.call))
        try:
            third = await env.side()
            try:
                state, w = await _settle(env, task, by=lpid)
                assert state == "waits" and (w["query"] or "").startswith("DELETE FROM link_codes"), (
                    "the request does not wait at its DELETE", state, w)
                assert await _holders(env.conn, s.p.sid) == [(w["pid"], "ShareLock", True)], "the key before"
                await third.execute("BEGIN")
                t0 = time.monotonic()
                got = await third.fetchval("SELECT pg_try_advisory_xact_lock(hashtext($1))", s.p.sid)
                took = time.monotonic() - t0
                after = await _holders(env.conn, s.p.sid)
                await third.execute("ROLLBACK")
                assert got is True and took < 1.0, ("the identity key while the request held its key", got, took)
                assert after == [(w["pid"], "ShareLock", True)], ("the key after", after)
            finally:
                await hold.execute("ROLLBACK")
            ans = await asyncio.wait_for(task, BOUND)
            assert ans.status == 200 and s.ok(ans.body), ("answer", ans)
        finally:
            await _end(task)
    case(monkeypatch, body, prefix="mdplbd")


# -- r4: two shared holders -------------------------------------------------------------------------

def test_toggle_ranked_answers_while_the_deletion_key_is_held_shared(monkeypatch, tmp_path):
    """r4: a second session holds P's deletion key SHARED for the whole call."""
    async def body(env):
        _seams(env, tmp_path)
        s = await SCENES["toggle_ranked"](env)
        side = await env.side()
        await side.execute("BEGIN")
        await side.execute(SHARED_SQL, main.PLAYER_DELETION_LOCK_CLASS, s.p.sid)
        try:
            t0 = time.monotonic()
            ans = await asyncio.wait_for(env.call(s.call), BOUND)
            took = time.monotonic() - t0
        finally:
            await side.execute("ROLLBACK")
        assert ans.status == 200 and s.ok(ans.body), ("answer", ans)
        assert took < 0.9 * main.PLAYER_DELETION_KEY_TIMEOUT_MS / 1000.0, ("not at once", took)
    case(monkeypatch, body, prefix="mdplbd")


# -- r5: the real deletion against the real route ---------------------------------------------------

def _stand_after_key(env, route):
    """main._reread_player_or_404 as `route`'s own body reaches it: it reads,
    sets `there`, then waits for `go`; for any other caller it runs as
    before. A plain function, so frame 1 is the caller's body. The request
    then stands after its key, holding it and no row lock."""
    real = main._reread_player_or_404
    there, go = asyncio.Event(), asyncio.Event()

    async def stand(db, player_id):
        await real(db, player_id)
        there.set()
        await go.wait()

    def reread(db, player_id):
        if sys._getframe(1).f_code.co_name == route:
            return stand(db, player_id)
        return real(db, player_id)
    env.mp.setattr(main, "_reread_player_or_404", reread)
    return there, go


def test_the_real_deletion_is_refused_while_a_request_stands_after_its_key(monkeypatch, tmp_path):
    """r5 (A)."""
    async def body(env):
        _seams(env, tmp_path)
        env.mp.setattr(main, "_DELETION_BUDGET_S", SHORT_BUDGET_S)
        s = await SCENES["generate_link_code"](env)
        there, go = _stand_after_key(env, s.route)
        req = asyncio.create_task(env.call(s.call))
        try:
            try:
                await asyncio.wait_for(there.wait(), BOUND)
                assert [h[1:] for h in await _holders(env.conn, s.p.sid)] == [("ShareLock", True)], "the request's key"
                t0 = time.monotonic()
                ans = await asyncio.wait_for(_delete(env, s.p), SHORT_BUDGET_S + MARGIN_S)
                took = time.monotonic() - t0
                stood = not req.done()
            finally:
                go.set()
            assert (ans.status, ans.body) == (503, main._DELETION_REFUSAL), ("the deletion's answer", ans)
            assert stood, "the request did not stand throughout"
            assert took <= SHORT_BUDGET_S + MARGIN_S, took
            assert await env.conn.fetchval("SELECT deleted_at FROM players WHERE id = $1", s.p.id) is None, "P deleted"
            rans = await asyncio.wait_for(req, BOUND)
            assert rans.status == 200 and s.ok(rans.body), ("the request's answer", rans)
        finally:
            await _end(req)
    case(monkeypatch, body, prefix="mdplbd")


def test_the_real_deletion_completes_after_the_request_and_keeps_nothing_it_stored(monkeypatch, tmp_path):
    """r5 (B)."""
    async def body(env):
        _seams(env, tmp_path)
        s = await SCENES["generate_link_code"](env)
        there, go = _stand_after_key(env, s.route)
        req = asyncio.create_task(env.call(s.call))
        try:
            dele = None
            try:
                await asyncio.wait_for(there.wait(), BOUND)
                held = await _holders(env.conn, s.p.sid)
                assert [h[1:] for h in held] == [("ShareLock", True)], ("the request's key", held)
                rpid = held[0][0]
                dele = asyncio.create_task(_delete(env, s.p))
                state, w = await _settle(env, dele, head="SELECT pg_advisory_xact_lock(CAST(", by=rpid)
                assert state == "waits", ("the deletion did not wait at its deletion key on the request", state)
            finally:
                go.set()
            rans = await asyncio.wait_for(req, BOUND)
            assert rans.status == 200 and s.ok(rans.body), ("the request's answer", rans)
            dans = await asyncio.wait_for(dele, main._DELETION_BUDGET_S + MARGIN_S)
            assert dans.status == 200 and dans.body.get("status") == "anonymized", ("the deletion's answer", dans)
            assert await env.conn.fetchval("SELECT deleted_at FROM players WHERE id = $1", s.p.id) is not None
            assert await env.conn.fetchval("SELECT count(*) FROM link_codes WHERE player_id = $1", s.p.id) == 0, (
                "a link code of P's is left")
            assert await env.conn.fetchval("SELECT count(*) FROM link_codes WHERE code = $1", rans.body["code"]) == 0, (
                "the request's code is left")
        finally:
            await _end(req, dele)
    case(monkeypatch, body, prefix="mdplbd")


def test_a_request_meets_the_real_deletion_held_open_after_its_key_then_answers_404(monkeypatch, tmp_path):
    """r5 (C)."""
    async def body(env):
        _seams(env, tmp_path)
        env.mp.setattr(main, "PLAYER_DELETION_KEY_TIMEOUT_MS", SMALL_MS, raising=False)
        s = await SCENES["generate_link_code"](env)
        real_drain = main._pc_lease_drain
        inside, out = asyncio.Event(), asyncio.Event()

        async def drain(db, pid):
            inside.set()
            await out.wait()
            return await real_drain(db, pid)
        env.mp.setattr(main, "_pc_lease_drain", drain)
        dele = asyncio.create_task(_delete(env, s.p))
        try:
            try:
                await asyncio.wait_for(inside.wait(), BOUND)
                assert [h[1:] for h in await _holders(env.conn, s.p.sid)] == [("ExclusiveLock", True)], (
                    "the deletion's key")
                t0 = time.monotonic()
                ans = await asyncio.wait_for(env.call(s.call), SMALL_MS / 1000.0 + MARGIN_S)
                took = time.monotonic() - t0
            finally:
                out.set()
            assert (ans.status, ans.body) == BUSY and took >= 0.9 * SMALL_MS / 1000.0, ("the route's answer", ans, took)
            dans = await asyncio.wait_for(dele, BOUND)
            assert dans.status == 200 and dans.body.get("status") == "anonymized", ("the deletion's answer", dans)
            again = await asyncio.wait_for(env.call(s.call), BOUND)
            assert (again.status, again.body) == NOT_FOUND, ("the route after the deletion", again)
        finally:
            await _end(dele)
    case(monkeypatch, body, prefix="mdplbd")


def test_the_real_deletion_of_a_new_id_waits_for_the_request_that_creates_it_then_deletes_it(monkeypatch,
                                                                                              tmp_path):
    """r6, the order in the database: toggle_ranked's first contact for a
    Steam id never seen creates P's row under the deletion key and stands
    after its key (the row inserted, not committed). The real deletion of
    that id waits at its deletion key on the request, then reads the
    committed row and deletes it: answered "anonymized", the row
    tombstoned, no live row left under the raw id."""
    async def body(env):
        _seams(env, tmp_path)
        new = P(None, _sid(161), "Bound toggle new")
        call = _toggle_call(new, new.name)
        assert await env.conn.fetchval("SELECT count(*) FROM players WHERE steam_id = $1", new.sid) == 0
        there, go = _stand_after_key(env, "toggle_ranked")
        req = asyncio.create_task(env.call(call))
        try:
            dele, state = None, None
            try:
                await asyncio.wait_for(there.wait(), BOUND)
                held = await _holders(env.conn, new.sid)
                assert [h[1:] for h in held] == [("ShareLock", True)], ("the request's key", held)
                rpid = held[0][0]
                dele = asyncio.create_task(_delete(env, new))
                state, _w = await _settle(env, dele, head="SELECT pg_advisory_xact_lock(CAST(", by=rpid)
            finally:
                go.set()
            rans = await asyncio.wait_for(req, BOUND)
            assert rans.status == 200 and rans.body == {"steam_id": new.sid, "ranked_enabled": True}, (
                "the request's answer", rans)
            dans = await asyncio.wait_for(dele, main._DELETION_BUDGET_S + MARGIN_S)
            assert state == "waits", ("the deletion did not wait at its deletion key on the request", state, dans)
            assert dans.status == 200 and dans.body.get("status") == "anonymized", ("the deletion's answer", dans)
            made = await env.conn.fetchval(
                "SELECT count(*) FROM players WHERE steam_id = $1 AND deleted_at IS NULL", new.sid)
            assert made == 0, "a live row is left under the raw id"
        finally:
            await _end(req, dele)
    case(monkeypatch, body, prefix="mdplbd")


# -- the control ------------------------------------------------------------------------------------

def test_control_the_holder_ends_inside_the_bound_and_lock_timeout_reads_its_default(monkeypatch, tmp_path):
    """Every scene of the four, H holding P's two keys and committing nothing as
    soon as the route waits: each route answers as before, having waited at
    the shared key, and the helper left lock_timeout as the session had it."""
    async def body(env):
        _seams(env, tmp_path)
        seen = []
        _timeouts(env, seen)
        for route, build in SCENES.items():
            s = await build(env)
            del seen[:]
            ans, waited, _left, _named = await _scene(env, s, delete=False)
            assert ans.status == 200 and s.ok(ans.body), ("control", route, ans)
            assert "pg_advisory_xact_lock_shared" in waited, ("the wait", route, waited)
            assert len(seen) == 1 and seen[0][0] == s.p.sid and seen[0][2] == seen[0][1], (
                "lock_timeout after the helper", route, seen)
    case(monkeypatch, body, prefix="mdplbd")


# -- the census row (no database) -------------------------------------------------------------------

def _api_sources():
    """{file name: text} of every .py file directly in backend/api (its sub-folders are not read)."""
    out = {}
    for name in sorted(os.listdir(API)):
        if name.endswith(".py"):
            with open(os.path.join(API, name), encoding="utf-8") as fh:
                out[name] = fh.read()
    return out


def _owner(st):
    """Where a top-level statement stands: a function's name, or "= NAME" for
    an assignment to NAME, or its line."""
    if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return st.name
    if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
        return "= " + st.targets[0].id
    return "line %d" % st.lineno


def _deletion_key_census(sources):
    """[] when the deletion key's census holds over `sources` (the module
    docstring's census row); else what fails, each naming its part."""
    out = []
    trees = {name: ast.parse(src) for name, src in sources.items()}
    # (a) where the two names stand
    where = {CLASS: [], ARGS: []}
    classes = {}
    for name, tree in sorted(trees.items()):
        for st in tree.body:
            for n in ast.walk(st):
                got = n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else None
                if got in where:
                    where[got].append((name, _owner(st)))
            if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) \
                    and st.targets[0].id.endswith("_LOCK_CLASS") and isinstance(st.value, ast.Constant):
                classes[(name, st.targets[0].id)] = st.value.value
    for const in (CLASS, ARGS):
        want = sorted([("main.py", "= " + const), ("main.py", HELPER), ("main.py", "delete_player_data")])
        if sorted(where[const]) != want:
            out.append("(a) %s stands at %s" % (const, sorted(where[const])))
    # (b) the class's number: its definition alone, and no other class of that number
    number = main.PLAYER_DELETION_LOCK_CLASS
    texts = sum(len(re.findall(r"(?<!\d)%d(?!\d)" % number, src)) for src in sources.values())
    ints = [(name, n.lineno) for name, tree in trees.items() for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and type(n.value) is int and n.value == number]
    if texts != 1 or len(ints) != 1 or classes.get(("main.py", CLASS)) != number:
        out.append("(b) the class's number stands %d times in the text, as an int at %s" % (texts, ints))
    if sorted(classes.values()).count(number) != 1 or len(set(classes.values())) != len(classes):
        out.append("(b) two advisory classes share a number: %s" % sorted(classes.items()))
    top = {n.name: n for n in trees["main.py"].body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    # (c) the four route spans
    got = {}
    for name in ROUTES:
        fn = top[name]
        calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
                 and ((isinstance(c.func, ast.Name) and c.func.id == HELPER)
                      or (isinstance(c.func, ast.Attribute) and c.func.attr == HELPER))]
        named = [c.value for c in ast.walk(fn) if isinstance(c, ast.Constant) and isinstance(c.value, str)
                 and "pg_advisory" in c.value]
        got[name] = (len(calls), named)
    if got != {name: (1, []) for name in ROUTES}:
        out.append("(c) the four routes: %s" % got)
    # the two statements, as written
    shared = ("await db.execute(text('SELECT pg_advisory_xact_lock_shared(' + %s + ')'), "
              "{'cls': %s, 'sid': steam_id})" % (ARGS, CLASS))
    exclusive = ("await db.execute(text('SELECT pg_advisory_xact_lock(' + %s + ')'), "
                 "{'cls': %s, 'sid': steam_id})" % (ARGS, CLASS))
    helper = [ast.unparse(n) for n in ast.walk(top[HELPER]) if isinstance(n, ast.Await)
              and "pg_advisory" in ast.unparse(n)]
    if helper != [shared]:
        out.append("(d) the helper's key statement: %s" % helper)
    # (e) the deletion's order: the identity key, the deletion key, the ban read (BAN-FIRST-1), the read of P,
    # among the function's top-level statements of every kind (an if, a try or an annotated assignment between
    # them is seen)
    body = top["delete_player_data"].body
    lines = [ast.unparse(st) for st in body]
    ident = next((i for i, (st, ln) in enumerate(zip(body, lines))
                  if isinstance(st, ast.Expr) and "pg_advisory_xact_lock(hashtext(" in ln), None)
    if ident is None or lines[ident + 1:ident + 2] != [exclusive] \
            or lines[ident + 2:ident + 3] != ["await _ban_gate_or_raise(db, steam_id, request)"] \
            or "select(Player).where(Player.steam_id == steam_id)" not in "".join(lines[ident + 3:ident + 4]):
        out.append("(e) the deletion's statements after its first identity key: %s"
                   % (None if ident is None else [ln[:90] for ln in lines[ident:ident + 4]]))
    if sum(ln == exclusive for ln in lines) != 1:
        out.append("(e) the deletion's key statement stands %d times" % sum(ln == exclusive for ln in lines))
    return out


def test_census_only_the_four_routes_and_the_deletion_take_the_deletion_key():
    """The census row of the module docstring, over backend/api as it stands."""
    assert _deletion_key_census(_api_sources()) == []


# The deletion's key statement and the ban read after it, as main.py writes them.
_DELETION_KEY_LINE = (
    '    await db.execute(text("SELECT pg_advisory_xact_lock(" + _PLAYER_DELETION_KEY_ARGS + ")"),'
    ' {"cls": PLAYER_DELETION_LOCK_CLASS, "sid": steam_id})\n')
_BAN_READ_LINE = (
    "    await _ban_gate_or_raise(db, steam_id, request)"
    "  # every writer of a key's player_bans rows holds its identity lock to its commit\n")

# Part (e)'s cases, each main.py's text with one change (old, new), red on (e).
_ORDER_CASES = {
    "a compound statement planted between the two keys": (
        '    await db.execute(text("SELECT pg_advisory_xact_lock(" + _PLAYER_DELETION_KEY_ARGS + ")"),',
        '    if steam_id:\n'
        '        await db.execute(text("SELECT 1"))\n'
        '    await db.execute(text("SELECT pg_advisory_xact_lock(" + _PLAYER_DELETION_KEY_ARGS + ")"),'),
    "a compound statement planted between the deletion key and the read of P": (
        '    player = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()\n'
        '    if player is None:\n'
        '        await _alt_delete_account(db, steam_id)',
        '    try:\n'
        '        pass\n'
        '    finally:\n'
        '        pass\n'
        '    player = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()\n'
        '    if player is None:\n'
        '        await _alt_delete_account(db, steam_id)'),
    "the ban read under the two keys taken out": (_BAN_READ_LINE, ""),
    "the ban read put before the deletion key": (
        _DELETION_KEY_LINE + _BAN_READ_LINE, _BAN_READ_LINE + _DELETION_KEY_LINE),
}


@pytest.mark.parametrize("name", sorted(_ORDER_CASES))
def test_the_census_row_s_order_part_reads_every_kind_of_statement(name):
    """Part (e) over main.py with a statement of another kind planted in the
    deletion's order: the census row names (e); the unchanged text gives []
    (the row above)."""
    old, new = _ORDER_CASES[name]
    sources = _api_sources()
    src = sources["main.py"].replace("\r\n", "\n")
    assert src.count(old) == 1, ("the case's text is not in main.py once", name)
    sources["main.py"] = src.replace(old, new)
    got = _deletion_key_census(sources)
    assert got and all(x.startswith("(e)") for x in got), (name, got)


# -- the real session check -------------------------------------------------------------------------

class _TokenReq(Req):
    """inv_pg's Req carrying a session token, for the real session check."""

    def __init__(self, sid):
        super().__init__(sid)
        self.headers = {"X-Session-Token": TOKEN}


def _toggle_real(p, request):
    name = "Reread toggle P renamed"
    sig = _sig("toggle-ranked:%s:true" % p.sid)
    name_sig = _sig("toggle-ranked-name:%s:%s" % (p.sid, name))
    return lambda db: main.toggle_ranked(steam_id=p.sid, request=request, enabled=True, sig=sig,
                                         display_name=name, name_sig=name_sig, db=db)


def _unlock_real(p, request):
    req = schemas.AchievementUnlockRequest(
        steam_id=p.sid, achievement_key=UNLOCK_KEY,
        hmac_signature=_sig("achievement:%s:%s" % (p.sid, UNLOCK_KEY)))
    return lambda db: main.unlock_achievement(req=req, request=request, db=db)


def _real_check_case(monkeypatch, tmp_path, route, make_call):
    async def body(env):
        _seams(env, tmp_path)
        env.mp.setattr(main, "_check_steam_session", _REAL_CHECK)
        assert getattr(_REAL_CHECK, "__module__", None) == "main" and _REAL_CHECK.__name__ == "_check_steam_session"
        s = await SCENES[route](env)
        await env.conn.execute(
            "INSERT INTO steam_sessions (steam_id, token_hash, verified, issued_at, expires_at)"
            " VALUES ($1, $2, TRUE, NOW(), NOW() + interval '1 day')",
            s.p.sid, hashlib.sha256(TOKEN.encode()).hexdigest())
        request = _TokenReq(s.p.sid)
        real = Scene(route, s.p, make_call(s.p, request), NOT_FOUND, s.ok)
        ans, waited, _left, _named = await asyncio.wait_for(_scene(env, real, delete=False), BOUND)
        assert ans.status == 200 and real.ok(ans.body), ("answer", route, ans)
        assert "pg_advisory_xact_lock_shared" in waited, ("the wait", route, waited)
        assert getattr(request.state, "scr_session_verified", None) is True, ("the real session check", route)
    case(monkeypatch, body, prefix="mdplbd")


def test_toggle_ranked_with_the_real_session_check_answers_as_before(monkeypatch, tmp_path):
    _real_check_case(monkeypatch, tmp_path, "toggle_ranked", _toggle_real)


def test_unlock_achievement_with_the_real_session_check_answers_as_before(monkeypatch, tmp_path):
    _real_check_case(monkeypatch, tmp_path, "unlock_achievement", _unlock_real)
