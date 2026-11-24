"""BAN-FIRST-1, on PostgreSQL and through the two routes of the app (main.app,
its middlewares included, the database dependency bound to the case schema of
inv_pg).

A. GET /api/v1/mod/check/{id} answers what models.player_ban_active_sql says
   of EVERY id it is asked about, a players row or none:
     a  no row, an active ban: banned, its reason, its end, the seconds left,
        the six keys in their order and no display_name
     b  no row, no ban: the body byte for byte, written out below
     c  a row, an active ban: the seven keys, their order and the ban's values
     d  no row, a ban past its end: the body of b
     e  no row, a ban that was lifted: the body of b
     f  no row, an active ban whose reason is the empty string: banned
     g  registered, banned, the players row anonymised as the deletion does it
        (_tombstone, held to the deletion's source): banned under the raw id,
        and the placeholder id answers as an account under no ban

B. DELETE /api/v1/players/{id}/data refuses an account under an active ban
   with 409 and the sweep's one body, whatever the request carries, and leaves
   the row count of every table of the schema, and the players row, as they
   were; the one [BAN-GATE] line names the route template. Refused: without a
   session; with a verified session of the account; under a reason of the
   empty string; with STEAM_WEB_API_KEY unset; and a ban that another
   connection commits while the deletion waits for the identity lock. It
   deletes, with a session, under no ban, an ended ban and a lifted ban;
   without a verified session of the same account it answers 401.

   The two reads: the statements of a deletion, as the case's engine sent
   them, name the first ban read before the session read and the second
   between the deletion's two keys and its read of the account; a refusal is
   the attempt's last statement; a refusal holds no advisory lock after it. A ban
   read that fails, the first or the second, ends the request with nothing
   written; a ban read that waits for a lock hands the bound its signal, the
   first and the second alike: 503 account_cleanup_contended, nothing written.

   Why the second read is the guarantee, over the source text (no database):
   every statement of backend/api that writes player_bans stands in one of
   three functions of main.py, each of them takes the target's identity
   lock in the same transaction before it writes, and the table's class
   (models.PlayerBan) is named by main.py's import alone, so nothing writes
   the table through it.

CF_TEST_PG_DSN names the lane database (cf_pg.require_live_pg).
"""

import ast
import asyncio
import contextlib
import hashlib
import hmac
import json
import os
import re
import sys
from datetime import datetime, timezone

import httpx
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

from sqlalchemy import event, text  # noqa: E402

from inv_pg import FLOOR, STEAM_BASE, case  # noqa: E402

import main  # noqa: E402
from test_mail_case_scrub_pg import BOUND, SECRET, _arm, _settle  # noqa: E402
from test_mdpl_gate_reread_pg import _tombstone  # noqa: E402

TOKEN = "ban-answers-session-token"
ROUTE_LINE = "[BAN-GATE] refused route=/api/v1/players/{steam_id}/data"
NOT_BANNED_NO_ROW = (b'{"registered":false,"ranked":false,"banned":false,"ban_reason":"",'
                     b'"ban_expires_at":null,"ban_seconds_left":null}')
KEYS_NO_ROW = ["registered", "ranked", "banned", "ban_reason", "ban_expires_at", "ban_seconds_left"]
KEYS_ROW = ["registered", "ranked", "display_name", "banned", "ban_reason", "ban_expires_at", "ban_seconds_left"]
WAIT_KEY = 72411240                                      # the advisory key a made wait of a ban read stands on
KEY_SQL = "SELECT pg_advisory_xact_lock(hashtext($1))"   # the identity key, exclusive


# -- the world --------------------------------------------------------------------------------------

@contextlib.asynccontextmanager
async def _client(env):
    """A client of main.app whose database sessions are the case's."""
    async def override():
        async with env.sm() as db:
            yield db
    main.app.dependency_overrides[main.get_db] = override
    try:
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
                base_url="http://ban-answers", headers={"X-Mod-Version": FLOOR}) as c:
            yield c
    finally:
        main.app.dependency_overrides.pop(main.get_db, None)


async def _check(env, sid):
    async with _client(env) as c:
        r = await c.get("/api/v1/mod/check/%s" % sid)
    assert r.status_code == 200, (r.status_code, r.text)
    return r


async def _admin(env):
    p = await env.player("ban answers admin")
    await env.conn.execute("INSERT INTO admin_users (steam_id) VALUES ($1)", p.sid)
    return p.sid


async def _ban(env, sid, *, reason="ban-answers", minutes=30, lifted=False):
    """One player_bans row of `sid`, begun an hour ago; `minutes` from now is
    its end (negative: ended). The row's own end."""
    adm = await _admin(env)
    return await env.conn.fetchval(
        "INSERT INTO player_bans (id, steam_id, reason, banned_by_steam_id, banned_at, expires_at,"
        "                         unbanned_at, unbanned_by_steam_id)"
        " VALUES (gen_random_uuid(), $1, $2, $3, NOW() - INTERVAL '1 hour',"
        "         NOW() + make_interval(mins => $4),"
        "         CASE WHEN $5 THEN NOW() - INTERVAL '1 minute' END, CASE WHEN $5 THEN $3 END)"
        " RETURNING expires_at", sid, reason, adm, minutes, lifted)


def _no_row_sid(env):
    """A steam id of the suite's range with no players row."""
    env.serial += 1
    return str(STEAM_BASE + env.serial)


async def _account(env):
    """A registered account with rows a deletion removes, and its own session
    (verified, of the account, unexpired) under TOKEN."""
    p = await env.player("Ban Answers P")
    await env.conn.execute("INSERT INTO player_achievements (player_id, achievement_key, unlocked_at)"
                           " VALUES ($1, 'ban_answers_probe', NOW())", p.id)
    await env.conn.execute("INSERT INTO link_codes (player_id, code, expires_at, created_at)"
                           " VALUES ($1, 'BANANS', NOW() + interval '10 minutes', NOW())", p.id)
    return p


async def _session(env, sid, *, token=TOKEN, verified=True, hours=24):
    await env.conn.execute(
        "INSERT INTO steam_sessions (steam_id, token_hash, verified, issued_at, expires_at)"
        " VALUES ($1, $2, $3, NOW() - interval '2 hours', NOW() + make_interval(hours => $4))",
        sid, hashlib.sha256(token.encode()).hexdigest(), verified, hours)


def _armed(env, key=True):
    """The deletion's secret, and STEAM_WEB_API_KEY set (or unset)."""
    _arm(env)
    if key:
        env.mp.setenv("STEAM_WEB_API_KEY", "ban-answers-web-key")


def _delete(c, p, *, token=None, sig=None):
    sig = sig or hmac.new(SECRET.encode(), ("delete:%s" % p.sid).encode(), hashlib.sha256).hexdigest()
    return c.delete("/api/v1/players/%s/data" % p.sid, params={"sig": sig},
                    headers={"X-Session-Token": token} if token else {})


async def _counts(conn):
    """Every base table of the case schema and its row count."""
    names = await conn.fetch(
        "SELECT table_name FROM information_schema.tables"
        " WHERE table_schema = current_schema() AND table_type = 'BASE TABLE' ORDER BY table_name")
    return {r["table_name"]: await conn.fetchval('SELECT count(*) FROM "%s"' % r["table_name"]) for r in names}


async def _row(conn, p):
    return dict(await conn.fetchrow("SELECT * FROM players WHERE id = $1", p.id))


def _moved(before, after):
    return {k: after.get(k, 0) - before.get(k, 0) for k in sorted(set(before) | set(after))
            if after.get(k, 0) != before.get(k, 0)}


@contextlib.contextmanager
def _statements(env):
    """The statements the case's sessions send, in order, less the bound's
    own arming; the list is live."""
    seen = []

    def note(conn, cursor, statement, parameters, context, executemany):
        if "set_config('lock_timeout'" not in statement:
            seen.append(" ".join(statement.split()))
    event.listen(env.engine.sync_engine, "before_cursor_execute", note)
    try:
        yield seen
    finally:
        event.remove(env.engine.sync_engine, "before_cursor_execute", note)


def _kind(s):
    if s.startswith("SELECT reason FROM player_bans"):
        return "ban"
    if "FROM steam_sessions" in s and s.startswith("SELECT"):
        return "session"
    if re.match(r"SELECT pg_advisory_xact_lock\(hashtext\(\$1", s):
        return "identity key"
    if re.match(r"SELECT pg_advisory_xact_lock\(CAST\(\$1", s):
        return "deletion key"
    if s.startswith("SELECT players."):
        return "player"
    return s


async def _advisory_locks(env):
    return await env.conn.fetchval(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND objsubid IN (1, 2)"
        " AND pid IN (SELECT pid FROM pg_stat_activity WHERE datname = current_database()"
        "              AND pid <> pg_backend_pid() AND xact_start IS NOT NULL)")


def _gate_lines(out):
    return [ln for ln in out.splitlines() if ln.startswith("[BAN-GATE]")]


# -- A: /mod/check ----------------------------------------------------------------------------------

def test_a_no_players_row_and_an_active_ban_answers_the_ban(monkeypatch):
    async def body(env):
        sid = _no_row_sid(env)
        end = await _ban(env, sid, reason="ban-answers a")
        r = await _check(env, sid)
        got = json.loads(r.content)
        assert list(got) == KEYS_NO_ROW, got
        assert (got["registered"], got["ranked"], got["banned"]) == (False, False, True), got
        assert got["ban_reason"] == "ban-answers a", got
        assert got["ban_expires_at"] is not None and datetime.fromisoformat(
            got["ban_expires_at"].replace("Z", "+00:00")) == end.astimezone(timezone.utc), (got, end)
        assert isinstance(got["ban_seconds_left"], int) and 1680 <= got["ban_seconds_left"] <= 1800, got
        assert got["ban_expires_at"].endswith("Z"), got
    case(monkeypatch, body, prefix="banans")


def test_b_no_players_row_and_no_ban_answers_the_exact_body_of_today(monkeypatch):
    async def body(env):
        r = await _check(env, _no_row_sid(env))
        assert r.content == NOT_BANNED_NO_ROW, r.content
    case(monkeypatch, body, prefix="banans")


def test_c_a_players_row_and_an_active_ban_answers_as_before(monkeypatch):
    async def body(env):
        p = await env.player("Ban Answers C")
        await env.conn.execute("UPDATE players SET ranked_enabled = TRUE WHERE id = $1", p.id)
        end = await _ban(env, p.sid, reason="ban-answers c")
        got = json.loads((await _check(env, p.sid)).content)
        left = got.pop("ban_seconds_left")
        assert list(got) + ["ban_seconds_left"] == KEYS_ROW, got
        assert got == {"registered": True, "ranked": True, "display_name": "Ban Answers C", "banned": True,
                       "ban_reason": "ban-answers c", "ban_expires_at": main._ban_end_iso(end)}, got
        assert isinstance(left, int) and 1680 <= left <= 1800, left
        clean = await env.player("Ban Answers C clean")
        r = await _check(env, clean.sid)
        ranked = await env.conn.fetchval("SELECT ranked_enabled FROM players WHERE id = $1", clean.id)
        assert r.content == (b'{"registered":true,"ranked":%s,"display_name":"Ban Answers C clean","banned":false,'
                             b'"ban_reason":"","ban_expires_at":null,"ban_seconds_left":null}'
                             % (b"true" if ranked else b"false")), r.content
    case(monkeypatch, body, prefix="banans")


def test_d_no_players_row_and_a_ban_past_its_end_is_not_banned(monkeypatch):
    async def body(env):
        sid = _no_row_sid(env)
        await _ban(env, sid, minutes=-1)
        assert await env.conn.fetchval("SELECT count(*) FROM player_bans WHERE steam_id = $1", sid) == 1
        assert (await _check(env, sid)).content == NOT_BANNED_NO_ROW
    case(monkeypatch, body, prefix="banans")


def test_e_no_players_row_and_a_lifted_ban_is_not_banned(monkeypatch):
    async def body(env):
        sid = _no_row_sid(env)
        await _ban(env, sid, lifted=True)
        assert await env.conn.fetchval("SELECT count(*) FROM player_bans WHERE steam_id = $1", sid) == 1
        assert (await _check(env, sid)).content == NOT_BANNED_NO_ROW
    case(monkeypatch, body, prefix="banans")


def test_f_no_players_row_and_an_active_ban_with_an_empty_reason_is_banned(monkeypatch):
    async def body(env):
        sid = _no_row_sid(env)
        end = await _ban(env, sid, reason="")
        got = json.loads((await _check(env, sid)).content)
        assert (got["banned"], got["ban_reason"]) == (True, ""), got
        assert got["ban_expires_at"] == main._ban_end_iso(end) and got["ban_seconds_left"] > 0, got
    case(monkeypatch, body, prefix="banans")


def test_g_an_account_anonymised_under_its_ban_is_banned_under_its_raw_id(monkeypatch):
    async def body(env):
        p = await env.player("Ban Answers G")
        end = await _ban(env, p.sid, reason="ban-answers g")
        before = json.loads((await _check(env, p.sid)).content)
        assert (before["registered"], before["banned"]) == (True, True), before
        side = await env.side()
        await side.execute("BEGIN")
        await side.execute(KEY_SQL, p.sid)
        await _tombstone(side, p)
        await side.execute("COMMIT")
        row = await _row(env.conn, p)
        assert row["deleted_at"] is not None and row["steam_id"].startswith("deleted_"), row["steam_id"]
        got = json.loads((await _check(env, p.sid)).content)
        left = got.pop("ban_seconds_left")
        assert got == {"registered": False, "ranked": False, "banned": True, "ban_reason": "ban-answers g",
                       "ban_expires_at": main._ban_end_iso(end)}, got
        assert 1680 <= left <= 1800, left
        r = await _check(env, row["steam_id"])
        assert r.content == (b'{"registered":true,"ranked":false,"display_name":"[Deleted User]","banned":false,'
                             b'"ban_reason":"","ban_expires_at":null,"ban_seconds_left":null}'), r.content
    case(monkeypatch, body, prefix="banans")


# -- B: the deletion refuses an account under an active ban -----------------------------------------

async def _refused(env, capsys, p, *, token=None, detail="Banned: ban-answers", kinds=("ban",)):
    """The deletion of `p` is refused: its answer, its one line, its
    statements, and nothing of the schema moved."""
    rows, row = await _counts(env.conn), await _row(env.conn, p)
    capsys.readouterr()
    async with _client(env) as c:
        with _statements(env) as sent:
            r = await asyncio.wait_for(_delete(c, p, token=token), BOUND)
    out = capsys.readouterr().out
    assert (r.status_code, r.json()) == (409, {"detail": detail}), (r.status_code, r.text)
    assert [_kind(s) for s in sent] == list(kinds), sent
    assert _gate_lines(out) == [ROUTE_LINE], out
    assert await _advisory_locks(env) == 0
    assert _moved(rows, await _counts(env.conn)) == {}, "row counts"
    assert await _row(env.conn, p) == row, "the players row"


def test_deletion_under_an_active_ban_without_a_session_is_refused(monkeypatch, capsys):
    async def body(env):
        _armed(env)
        p = await _account(env)
        await _ban(env, p.sid)
        await _refused(env, capsys, p)
    case(monkeypatch, body, prefix="banans")


def test_deletion_under_an_active_ban_with_a_verified_session_is_refused(monkeypatch, capsys):
    async def body(env):
        _armed(env)
        p = await _account(env)
        await _session(env, p.sid)
        await _ban(env, p.sid)
        await _refused(env, capsys, p, token=TOKEN)
    case(monkeypatch, body, prefix="banans")


def test_deletion_under_an_active_ban_with_an_empty_reason_is_refused(monkeypatch, capsys):
    async def body(env):
        _armed(env)
        p = await _account(env)
        await _session(env, p.sid)
        await _ban(env, p.sid, reason="")
        await _refused(env, capsys, p, token=TOKEN, detail="Banned: violation")
    case(monkeypatch, body, prefix="banans")


def test_deletion_under_an_active_ban_is_refused_with_the_web_api_key_unset(monkeypatch, capsys):
    async def body(env):
        _armed(env, key=False)
        p = await _account(env)
        await _ban(env, p.sid)
        await _refused(env, capsys, p)
    case(monkeypatch, body, prefix="banans")


def test_a_wrong_signature_is_answered_before_any_ban_is_read(monkeypatch, capsys):
    async def body(env):
        _armed(env)
        p = await _account(env)
        await _ban(env, p.sid)
        async with _client(env) as c:
            with _statements(env) as sent:
                r = await _delete(c, p, token=TOKEN, sig="0" * 64)
        assert (r.status_code, r.json()) == (403, {"detail": "Invalid signature"}), r.text
        assert sent == [] and _gate_lines(capsys.readouterr().out) == [], sent
    case(monkeypatch, body, prefix="banans")


def test_a_ban_committed_while_the_deletion_waits_for_the_identity_lock_refuses_it(monkeypatch, capsys):
    """The ban core (_apply_ban_core) holds the account's identity lock on a
    connection of its own, not yet committed. The deletion, with a verified
    session, has passed its first ban read and its session check and waits for
    that lock (seen in pg_locks, the ban's backend its blocker); the ban
    commits; the deletion answers 409 and only the ban's own rows moved."""
    async def body(env):
        _armed(env)
        env.mp.setattr(main, "_DELETION_WAIT_CAP_S", 8.0)   # one attempt waits out the interleave
        p = await _account(env)
        await _session(env, p.sid)
        adm = await _admin(env)
        rows = await _counts(env.conn)
        ban_db = env.sm()
        async with _client(env) as c:
            task = None
            try:
                bpid = (await ban_db.execute(text("SELECT pg_backend_pid()"))).scalar()
                ans = await main._apply_ban_core(ban_db, admin_steam_id=adm, target_steam_id=p.sid,
                                                 reason="ban-answers late", duration_minutes=60)
                assert ans["status"] == "banned", ans
                banned_row = dict((await ban_db.execute(
                    text("SELECT * FROM players WHERE id = :p"), {"p": p.id})).mappings().first())
                capsys.readouterr()
                with _statements(env) as sent:
                    task = asyncio.create_task(_delete(c, p, token=TOKEN))
                    state, w = await _settle(env, task, head="SELECT pg_advisory_xact_lock(hashtext(", by=bpid)
                    assert state == "waits", ("the deletion did not wait on the ban", state,
                                              task.result().text if task.done() else None)
                    before_wait = [_kind(s) for s in sent]
                    await ban_db.commit()
                    r = await asyncio.wait_for(task, BOUND)
                out = capsys.readouterr().out
            finally:
                await ban_db.rollback()
                await ban_db.close()
                if task is not None and not task.done():
                    task.cancel()
        assert before_wait == ["ban", "session", "identity key"], before_wait
        assert (r.status_code, r.json()) == (409, {"detail": "Banned: ban-answers late"}), (r.status_code, r.text)
        assert [_kind(s) for s in sent] == ["ban", "session", "identity key", "deletion key", "ban"], sent
        assert _gate_lines(out) == [ROUTE_LINE], out
        # the ban's own writes and nothing else: its row, its record, the session it ended
        assert _moved(rows, await _counts(env.conn)) == {"admin_actions": 1, "player_bans": 1, "steam_sessions": -1}
        assert await _row(env.conn, p) == banned_row, "the players row, as the ban's own transaction read it"
        assert await _advisory_locks(env) == 0
    case(monkeypatch, body, prefix="banans")


# -- B: what still deletes, and what asks for a session ---------------------------------------------

@pytest.mark.parametrize("ban", ["none", "ended", "lifted"])
def test_deletion_with_a_session_still_deletes_under_no_active_ban(monkeypatch, capsys, ban):
    async def body(env):
        _armed(env)
        p = await _account(env)
        await _session(env, p.sid)
        if ban == "ended":
            await _ban(env, p.sid, minutes=-1)
        elif ban == "lifted":
            await _ban(env, p.sid, lifted=True)
        rows = await _counts(env.conn)
        async with _client(env) as c:
            with _statements(env) as sent:
                r = await asyncio.wait_for(_delete(c, p, token=TOKEN), BOUND)
        assert r.status_code == 200 and r.json()["status"] == "anonymized", (r.status_code, r.text)
        row = await _row(env.conn, p)
        assert row["deleted_at"] is not None and row["steam_id"] == r.json()["placeholder"], row["steam_id"]
        moved = _moved(rows, await _counts(env.conn))
        assert (moved["player_achievements"], moved["link_codes"], moved["steam_sessions"]) == (-1, -1, -1), moved
        assert moved["deleted_steam_ids"] == 1 and "player_bans" not in moved, moved
        assert _gate_lines(capsys.readouterr().out) == []
        kinds = [_kind(s) for s in sent]
        assert kinds[:kinds.index("player") + 1] == [
            "ban", "session", "identity key", "deletion key", "ban", "player"], kinds[:8]
        assert kinds.count("ban") == 2, kinds
    case(monkeypatch, body, prefix="banans")


@pytest.mark.parametrize("which", ["none", "another account's", "unverified", "expired", "none, ended ban"])
def test_deletion_without_a_verified_session_of_the_account_answers_401(monkeypatch, which):
    async def body(env):
        _armed(env)
        p = await _account(env)
        token = TOKEN
        if which == "another account's":
            await _session(env, (await env.player("Ban Answers other")).sid)
        elif which == "unverified":
            await _session(env, p.sid, verified=False)
        elif which == "expired":
            await _session(env, p.sid, hours=-1)
        else:
            token = None
            if which == "none, ended ban":
                await _ban(env, p.sid, minutes=-1)
        rows, row = await _counts(env.conn), await _row(env.conn, p)
        async with _client(env) as c:
            with _statements(env) as sent:
                r = await asyncio.wait_for(_delete(c, p, token=token), BOUND)
        assert (r.status_code, r.json()) == (401, {"detail": "session_required_update_mod"}), r.text
        assert [_kind(s) for s in sent] == ["ban"] + (["session"] if token else []), sent
        assert _moved(rows, await _counts(env.conn)) == {} and await _row(env.conn, p) == row
    case(monkeypatch, body, prefix="banans")


# -- B: a ban read that fails, and a ban read that waits --------------------------------------------

@pytest.mark.parametrize("nth", [1, 2])
def test_a_failed_ban_read_never_lets_a_deletion_go_on(monkeypatch, nth):
    async def body(env):
        _armed(env)
        p = await _account(env)
        await _session(env, p.sid)
        rows, row = await _counts(env.conn), await _row(env.conn, p)
        reads = []

        def fail(sql):
            if sql.startswith("SELECT reason FROM player_bans"):
                reads.append(sql)
                if len(reads) == nth:
                    return sql.replace("FROM player_bans", "FROM player_bans_unreadable", 1)
            return sql
        env._rewrites.append(fail)
        try:
            async with _client(env) as c:
                r = await asyncio.wait_for(_delete(c, p, token=TOKEN), BOUND)
        finally:
            env._rewrites.remove(fail)
        assert len(reads) == nth and r.status_code == 500, (len(reads), r.status_code, r.text)
        assert _moved(rows, await _counts(env.conn)) == {} and await _row(env.conn, p) == row
        assert await _advisory_locks(env) == 0
    case(monkeypatch, body, prefix="banans")


def test_a_ban_that_comes_and_is_lifted_inside_a_deletion_leaves_the_session_required(monkeypatch):
    """A request without a session: no ban at the first read, and a ban that
    stands for exactly the read after it. It answers 401 and deletes nothing:
    no ban read decides whether a session is asked for."""
    async def body(env):
        _armed(env)
        p = await _account(env)
        real, reads = main._is_banned, []

        async def read(db, sid):
            reads.append(sid)
            if len(reads) == 2:
                await _ban(env, sid)
            out = await real(db, sid)
            if len(reads) == 2:
                await env.conn.execute("UPDATE player_bans SET unbanned_at = NOW() WHERE steam_id = $1", sid)
            return out
        env.mp.setattr(main, "_is_banned", read)
        row = await _row(env.conn, p)
        async with _client(env) as c:
            r = await asyncio.wait_for(_delete(c, p), BOUND)
        assert (r.status_code, r.json()) == (401, {"detail": "session_required_update_mod"}), (r.status_code, r.text)
        assert reads == [p.sid] and await _row(env.conn, p) == row, reads
    case(monkeypatch, body, prefix="banans")


@pytest.mark.parametrize("nth", [1, 2])
def test_a_ban_read_that_waits_hands_the_bound_its_signal(monkeypatch, nth):
    """The first (the second) ban read of every attempt is made to wait for an
    advisory lock another connection holds. The bound reads the wait as a
    held row (_DeletionRowHeld) and answers its refusal inside its budget;
    with the lock free the same request deletes."""
    async def body(env):
        _armed(env)
        env.mp.setattr(main, "_DELETION_BUDGET_S", 6.0)
        p = await _account(env)
        await _session(env, p.sid)
        rows, row = await _counts(env.conn), await _row(env.conn, p)
        seen = {"key": False, "waited": 0}

        def wait(sql):
            if sql.startswith("SELECT pg_advisory_xact_lock(hashtext("):
                seen["key"] = True
            elif sql.startswith("SELECT reason FROM player_bans WHERE "):
                after_key, seen["key"] = seen["key"], False
                if after_key is (nth == 2):
                    seen["waited"] += 1
                    return sql.replace(" WHERE ", " WHERE (SELECT pg_advisory_xact_lock(%d)) IS NOT NULL AND "
                                       % WAIT_KEY, 1)
            return sql
        env._rewrites.append(wait)
        hold = await env.side()
        try:
            async with _client(env) as c:
                await hold.execute("BEGIN")
                await hold.execute("SELECT pg_advisory_xact_lock($1)", WAIT_KEY)
                with _statements(env) as sent:
                    r = await asyncio.wait_for(_delete(c, p, token=TOKEN), BOUND)
                assert (r.status_code, r.json()) == (503, {"detail": main._DELETION_REFUSAL}), (r.status_code, r.text)
                kinds = [_kind(s) for s in sent]
                one = ["ban"] if nth == 1 else ["ban", "session", "identity key", "deletion key", "ban"]
                assert seen["waited"] >= 2 and kinds == one * seen["waited"], (seen, kinds)
                assert _moved(rows, await _counts(env.conn)) == {} and await _row(env.conn, p) == row
                await hold.execute("ROLLBACK")
                r = await asyncio.wait_for(_delete(c, p, token=TOKEN), BOUND)
                assert r.status_code == 200 and r.json()["status"] == "anonymized", (r.status_code, r.text)
        finally:
            env._rewrites.remove(wait)
            await hold.execute("ROLLBACK")
    case(monkeypatch, body, prefix="banans")


# -- why the second read is the guarantee (no database) ----------------------------------------------

WRITE = re.compile(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+player_bans\b", re.I)


def _api_functions():
    """(module, name, node) of every top-level function of backend/api/*.py."""
    api = os.path.join(HERE, "..", "api")
    for name in sorted(os.listdir(api)):
        if name.endswith(".py"):
            with open(os.path.join(api, name), encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in tree.body:
                yield name[:-3], getattr(node, "name", None), node


def _write_lines(node):
    docs = {id(n.body[0].value) for n in ast.walk(node)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body
            and isinstance(n.body[0], ast.Expr)}
    return sorted(n.lineno for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                  and id(n) not in docs and WRITE.search(n.value))


def _call_lines(node, name):
    return sorted(n.lineno for n in ast.walk(node) if isinstance(n, ast.Call)
                  and name == (n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", None)))


def _class_names(tree):
    """(line, kind) of everything that names PlayerBan: its class, an import,
    a name, an attribute, a keyword, a parameter, an assignment's target, or a
    string that is or holds the word outside a docstring (getattr, a
    relationship's string)."""
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body
            and isinstance(n.body[0], ast.Expr)}
    word = re.compile(r"\bPlayerBan\b")
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == "PlayerBan":
            out.append((n.lineno, "class"))
        elif isinstance(n, ast.alias) and "PlayerBan" in (n.name.split(".")[-1], n.asname):
            out.append((n.lineno, "import" if n.asname is None else "import under another name"))
        elif isinstance(n, ast.Name) and n.id == "PlayerBan":
            out.append((n.lineno, "name"))
        elif isinstance(n, ast.Attribute) and n.attr == "PlayerBan":
            out.append((n.lineno, "attribute"))
        elif isinstance(n, (ast.keyword, ast.arg)) and n.arg == "PlayerBan":
            out.append((n.lineno, "keyword"))
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs and word.search(n.value):
            out.append((n.lineno, "string"))
    return sorted(out)


def test_no_orm_writer_of_player_bans_stands_in_the_api():
    """models.PlayerBan is named by its class in models.py and by main.py's
    import, once each, and by nothing else in backend/api/*.py."""
    api = os.path.join(HERE, "..", "api")
    named = {}
    for name in sorted(os.listdir(api)):
        if name.endswith(".py"):
            with open(os.path.join(api, name), encoding="utf-8") as fh:
                kinds = [k for _ln, k in _class_names(ast.parse(fh.read()))]
            if kinds:
                named[name] = kinds
    assert named == {"main.py": ["import"], "models.py": ["class"]}, named


def test_every_writer_of_player_bans_takes_the_targets_identity_lock_before_it_writes():
    """The writers of player_bans are three functions of main.py (no ORM
    writer: test_no_orm_writer_of_player_bans_stands_in_the_api). The ban core
    takes the target's identity lock before its two writes and before its one
    call of the length change, which writes the third and is called by
    nothing else; neither of the two commits or rolls back. The unban takes
    the target's lock (_mail_lock_identities) before its write and commits
    once, after it."""
    fns, writers, length_callers = {}, {}, []
    for mod, name, node in _api_functions():
        lines = _write_lines(node)
        if lines:
            writers[(mod, name)] = len(lines)
            fns[name] = (node, lines)
        if name != "_ban_set_length_core":
            length_callers += [name] * len(_call_lines(node, "_ban_set_length_core"))
    assert writers == {("main", "_ban_set_length_core"): 1, ("main", "_apply_ban_core"): 2,
                       ("main", "admin_unban"): 1}, writers
    assert length_callers == ["_apply_ban_core"], length_callers
    core, core_writes = fns["_apply_ban_core"]
    locks = [n.lineno for n in ast.walk(core) if isinstance(n, ast.Call)
             and ast.unparse(n) == "db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:sid))'),"
                                   " {'sid': target_steam_id})"]
    assert len(locks) == 1 and locks[0] < min(core_writes + _call_lines(core, "_ban_set_length_core")), locks
    for name in ("_apply_ban_core", "_ban_set_length_core"):
        assert not _call_lines(fns[name][0], "commit") + _call_lines(fns[name][0], "rollback"), name
    unban, (write,) = fns["admin_unban"]
    (lock,) = [n for n in ast.walk(unban) if isinstance(n, ast.Call)
               and ast.unparse(n.func) == "_mail_lock_identities"]
    assert "req.target_steam_id" in [ast.unparse(a) for a in lock.args], ast.unparse(lock)
    (commit,) = _call_lines(unban, "commit")
    assert lock.lineno < write < commit and not _call_lines(unban, "rollback"), (lock.lineno, write, commit)
