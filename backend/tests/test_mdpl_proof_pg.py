"""MDPL's proof, live: each change run through the real handlers on inv_pg's
case schema, and each shown to be what makes its test pass by a negative
control run the same way: a mutant of the statement (inv_pg Env.rewriting,
which rewrites what reaches the server, so a control asserts that its
rewrite applied) or of the Python seam the change rests on.

The order (R2, R3, R4, R5) runs with the bound's new attempts off
(_order_only), so a test of the order sees PostgreSQL's 40P01 as it is.
- R3, the print scene's control: the pool snapshot key back below the
  delete of the prints the player owns (its place at 732d96b1) deadlocks.
- R2: two deletions sharing relay rows and mail_blocks rows, both ways. The
  second waits only at the key, with no transaction id, so with no row
  lock; without the key it waits on a row of the first, holding rows.
- R4, pending_dms. The deletion and the ack, each side's pass removed in
  turn, in the scene where that side's pass is what keeps the circle open
  (the reproduction for the deletion's side; the ack first, ids reversed,
  for the ack's side). The relay-off cancel takes its rows in id order: a
  probe shows it holds no row above the one it waits for. The poll's
  RETIRE skips a held row, and the next poll retires it. The anonymising
  UPDATE's FOR UPDATE, the premise of the deletion's pass: a send to the
  player arriving there waits; with the steam_id left as it is (FOR NO
  KEY UPDATE) it does not, and its envelope outlives the deletion.
- R5, the ban scene's control: the ranked step back above the lobby locks
  deadlocks.
The bound (R6a, R6b):
- C2: a lease start naming the player is refused (409 subject_busy) while
  the deletion, past its drain, holds the identity key.
- C3: the clock past the deadline between the work and the commit: 503
  account_cleanup_contended, nothing written.
- R6b: a deadlock victim inside a bet helper's savepoint runs the whole
  deletion again, and the bettor is refunded in its commit; a lock timeout
  there (55P03) refuses at once, with nothing written.
"""

import asyncio
import contextlib
import json
import os
import re
import sys
import time
import uuid

import asyncpg
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import inv_pg  # noqa: E402
from inv_pg import case  # noqa: E402

import mail_discord  # noqa: E402
import main  # noqa: E402
from test_mail_case_scrub_pg import (  # noqa: E402
    BOUND, CROCKFORD, _arm, _bad, _deadlock, _delete, _finish, _name, _parked, _parks, _relay_row,
    _settle)
from test_mdpl_deletion_lock_order_pg import (  # noqa: E402
    INTERNAL, KEY_SQL, TO_MARK, _edition, _matched, _order_only, _past_deadlock_check, _print_of,
    _sent)

BIND = r"(\$\d+|%s|%\(\w+\)s|:\w+)"          # a compiled bind, whatever the paramstyle
KEY_EXACT = re.compile(r"^SELECT pg_advisory_xact_lock\(hashtext\('pc_snapshot'\)\)$")
POOL_EXACT = re.compile(r"^DELETE FROM pc_pool_members WHERE player_id = " + BIND + "$")
POOL_MARK = "DELETE FROM pc_pool_members WHERE player_id = :pid"
PASS_MARK = "WHERE (relay_code IS NOT NULL AND steam_id = :sid)"   # _ERASE_RELAY_DMS_LOCK_SQL only
SETTLE_MARK = "UPDATE pending_dms u "                                # _PENDING_DM_SETTLE_SQL
IDENTITY_KEY = re.compile(r"pg_advisory_xact_lock\(hashtext\(" + BIND + r"\)\)")
FLUSH_SID = re.compile(r"\bsteam_id=" + BIND + r"(::\w+(?:\(\d+\))?)?")
BET_READ = re.compile(r"FROM lobby_bets\s+WHERE mode = ")
OFF_IDS = (9000000300, 9000000200, 9000000100)   # inserted in this order: physical order against id order
FAIL_ONCE = (
    "CREATE SEQUENCE mdpl_once;"
    " CREATE FUNCTION mdpl_fail_once() RETURNS boolean LANGUAGE plpgsql AS $f$"
    " BEGIN"
    "   IF nextval('mdpl_once') = 1 THEN"
    "     RAISE EXCEPTION 'mdpl: SQLSTATE %(code)s, forced' USING ERRCODE = '%(code)s';"
    "   END IF;"
    "   RETURN true;"
    " END $f$;")
FAIL_ONCE_GONE = "DROP FUNCTION IF EXISTS mdpl_fail_once(); DROP SEQUENCE IF EXISTS mdpl_once;"


def _circle(a, b):
    """One side ended in PostgreSQL's 40P01: the circle a control restores."""
    return _bad(a, b) and (_deadlock(a) or _deadlock(b))


async def _holding(env, row_id):
    """A side connection in an open transaction that holds pending_dms row
    `row_id` FOR UPDATE: (connection, its backend pid)."""
    side = await env.side()
    await side.execute("BEGIN")
    got = await side.fetchval("SELECT id FROM pending_dms WHERE id = $1 FOR UPDATE", row_id)
    assert got == row_id, (got, row_id)
    return side, await side.fetchval("SELECT pg_backend_pid()")


async def _free(env, row_id):
    """True when pending_dms row `row_id` can be locked FOR UPDATE at once
    (NOWAIT, in a transaction rolled back at once)."""
    probe = await env.side()
    await probe.execute("BEGIN")
    try:
        await probe.fetchval("SELECT id FROM pending_dms WHERE id = $1 FOR UPDATE NOWAIT", row_id)
        return True
    except asyncpg.exceptions.LockNotAvailableError:
        return False
    finally:
        await probe.execute("ROLLBACK")


async def _claimed_report(env, *, acked, retried):
    """The bot's report: `acked` delivered; `retried` handed out under a claim
    and to be tried again."""
    claim = uuid.uuid4()
    await env.conn.execute(
        "UPDATE pending_dms SET claim_id = $2, claim_until = NOW() + make_interval(mins => 5)"
        " WHERE id = $1", retried, claim)
    return main._PendingDmAck(dm_ids=[str(acked)], retry_ids=[str(retried)],
                              claims={str(retried): str(claim)})


def _ack(report):
    return lambda db: main.ack_pending_dms(report, x_internal_key=INTERNAL, db=db)


# -- R3 ---------------------------------------------------------------------------------------

def test_r3_control_the_key_below_the_owned_prints_deadlocks(monkeypatch):
    """R3's control, the print scene with the key at its place on 732d96b1:
    the head's key statement does nothing, and the pool-members delete (the
    statement after the delete of the prints the player owns) takes the key
    first. Q holds its print of P's card while it waits for the key P holds;
    P then waits for that print."""
    async def body(env):
        _arm(env)
        _order_only(env)
        await _edition(env)
        p, q = await env.players(2)
        await _print_of(env, q, p)
        down = (r"WITH d AS (DELETE FROM pc_pool_members WHERE player_id = \1)"
                r" SELECT pg_advisory_xact_lock(hashtext('pc_snapshot'))")
        at = _parks(env)
        spot = at(POOL_MARK, "after")
        with env.rewriting(KEY_EXACT, "SELECT 1") as head, env.rewriting(POOL_EXACT, down) as moved:
            tp = asyncio.create_task(_delete(env, p))
            await _parked(spot, tp)                   # P holds the key, taken at its pool-members delete
            tq = asyncio.create_task(_delete(env, q))
            state, w = await _settle(env, tq, by=spot.pid)
            assert state == "waits", (state, w)       # Q holds its print and waits for the key
            await _past_deadlock_check(env)
            a, b = await _finish([tp, tq], [spot])
        assert head and moved, ("the mutant did not apply", len(head), len(moved))
        assert _circle(a, b), ("no 40P01", _name(a), _name(b))
    case(monkeypatch, body, prefix="mdpl")


# -- R2 ---------------------------------------------------------------------------------------

async def _shared_mail(env):
    """P and Q with a relay row each way (P's message to Q, Q's to P) and a
    mail block each way, the blocks written after the two sends."""
    p, q = await env.players(2)
    r1 = await _relay_row(env, q, p, await _sent(env, p, q))
    r2 = await _relay_row(env, p, q, await _sent(env, q, p))
    await env.conn.execute(
        "INSERT INTO mail_blocks (blocker_id, blocked_id) VALUES ($1, $2), ($2, $1)", p.id, q.id)
    return p, q, [r1, r2]


def test_r2_two_deletions_sharing_mail_rows_wait_only_at_the_key(monkeypatch):
    """R2: P holds the key; Q waits for it with no transaction id, so with no
    row lock (a backend takes one with its first row write or row lock);
    both commit, and every shared row is gone."""
    async def body(env):
        _arm(env)
        _order_only(env)
        p, q, rel = await _shared_mail(env)
        at = _parks(env)
        spot = at(KEY_SQL, "after")
        tp = asyncio.create_task(_delete(env, p))
        await _parked(spot, tp)
        tq = asyncio.create_task(_delete(env, q))
        state, w = await _settle(env, tq, by=spot.pid)
        assert state == "waits" and (w["query"] or "").startswith(KEY_SQL), (state, w)
        assert w["xid"] is None, ("Q holds a row lock while it waits for the key", w)
        a, b = await _finish([tp, tq], [spot])
        assert not _bad(a, b), ("outcomes", _name(a), _name(b))
        assert a["status"] == "anonymized" and b["status"] == "anonymized", (a, b)
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM pending_dms WHERE id = ANY($1::bigint[])", rel) == 0
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM mail_blocks WHERE blocker_id = ANY($1::uuid[])"
            "    OR blocked_id = ANY($1::uuid[])", [p.id, q.id]) == 0
    case(monkeypatch, body, prefix="mdpl")


def test_r2_control_without_the_key_two_deletions_hold_rows_at_once(monkeypatch):
    """R2's control: the key statement made a plain SELECT. P, parked past its
    relay pass, holds the shared relay rows; Q runs into a row P holds and
    waits there with a transaction id of its own. After the release a 40P01
    is allowed (the circle the key keeps out); no other error is."""
    async def body(env):
        _arm(env)
        _order_only(env)
        p, q, _rel = await _shared_mail(env)
        at = _parks(env)
        spot = at(PASS_MARK, "after")
        with env.rewriting(KEY_EXACT, "SELECT 1") as head:
            tp = asyncio.create_task(_delete(env, p))
            await _parked(spot, tp)
            tq = asyncio.create_task(_delete(env, q))
            state, w = await _settle(env, tq, by=spot.pid)
            assert state == "waits", (state, w)
            assert w["xid"] is not None and not (w["query"] or "").startswith(("SELECT 1", KEY_SQL)), w
            a, b = await _finish([tp, tq], [spot])
        assert len(head) >= 2, len(head)
        for x in (a, b):
            assert not _bad(x) or _deadlock(x), _name(x)
    case(monkeypatch, body, prefix="mdpl")


# -- R4: the deletion and the ack -------------------------------------------------------------

def test_r4_control_the_deletions_pass_removed_deadlocks_with_the_ack(monkeypatch):
    """R4, the deletion's side: the relay-ack reproduction with the deletion's
    pass made a no-op (LIMIT 0: no row, no lock). Parked after its TO delete
    the deletion holds r_to only; the ack's pass takes r_from (the lower id)
    and waits for r_to; the deletion's FROM delete then waits for r_from."""
    async def body(env):
        _arm(env)
        _order_only(env)
        env.mp.setenv("API_SECRET_KEY", INTERNAL)
        p, t = await env.players(2)
        r_from = await _relay_row(env, t, p, await _sent(env, p, t))
        r_to = await _relay_row(env, p, t, await _sent(env, t, p))
        report = await _claimed_report(env, acked=r_to, retried=r_from)
        at = _parks(env)
        spot = at(TO_MARK, "after")
        with env.rewriting("ORDER BY id FOR UPDATE", "ORDER BY id LIMIT 0",
                           where="WHERE (relay_code IS NOT NULL AND steam_id = ") as off:
            td = asyncio.create_task(_delete(env, p))
            await _parked(spot, td)
            tb = asyncio.create_task(env.call(_ack(report)))
            state, w = await _settle(env, tb, by=spot.pid)
            assert state == "waits", (state, w)
            await _past_deadlock_check(env)
            a, b = await _finish([td, tb], [spot])
        assert off, "the mutant did not apply"
        assert _circle(a, b), ("no 40P01", _name(a), _name(b))
    case(monkeypatch, body, prefix="mdpl")


async def _ack_first(env, *, pass_off):
    """The ack first, the ids reversed (r_to below r_from): the ack parks
    after its settle of r_from, and the deletion's pass then meets the ack's
    rows. pass_off: the ack's pass made a no-op (LIMIT 0)."""
    _arm(env)
    _order_only(env)
    env.mp.setenv("API_SECRET_KEY", INTERNAL)
    p, t = await env.players(2)
    r_to = await _relay_row(env, p, t, await _sent(env, t, p))
    r_from = await _relay_row(env, t, p, await _sent(env, p, t))
    assert r_to < r_from, (r_to, r_from)
    report = await _claimed_report(env, acked=r_to, retried=r_from)
    at = _parks(env)
    spot = at(SETTLE_MARK, "after")
    ctx = (env.rewriting("ORDER BY id FOR NO KEY UPDATE", "ORDER BY id LIMIT 0",
                         where="id::text = ANY(CAST(") if pass_off else contextlib.nullcontext([]))
    with ctx as off:
        tb = asyncio.create_task(env.call(_ack(report)))
        await _parked(spot, tb)
        td = asyncio.create_task(_delete(env, p))
        state, w = await _settle(env, td, by=spot.pid)
        assert state == "waits", (state, w)
        await _past_deadlock_check(env)
        b, a = await _finish([tb, td], [spot])
    assert off or not pass_off, "the mutant did not apply"
    return a, b, [r_to, r_from]


def test_r4_the_ack_first_and_a_deletion_both_finish(monkeypatch):
    """R4, the ack's side: the ack holds both rows from its pass on; the
    deletion's pass waits for the lower one holding none; both commit."""
    async def body(env):
        a, b, rows = await _ack_first(env, pass_off=False)
        assert not _bad(a, b), ("outcomes", _name(a), _name(b))
        assert a.status == 200 and a["status"] == "anonymized", a
        assert b.status == 200 and b["acked"] == 1 and b["settled"] == 1, b
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM pending_dms WHERE id = ANY($1::bigint[])", rows) == 0
    case(monkeypatch, body, prefix="mdpl")


def test_r4_control_the_acks_pass_removed_deadlocks_with_a_deletion(monkeypatch):
    """R4, the ack's side, its control: without its pass the ack holds r_from
    only; the deletion's pass takes r_to and waits for r_from; the ack's ack
    of r_to then waits for the deletion."""
    async def body(env):
        a, b, _rows = await _ack_first(env, pass_off=True)
        assert _circle(a, b), ("no 40P01", _name(a), _name(b))
    case(monkeypatch, body, prefix="mdpl")


# -- R4: the relay-off cancel -----------------------------------------------------------------

def _discord_id(p):
    """A Discord id for player p: 18 digits (players.discord_id is
    VARCHAR(20) and UNIQUE), one per harness Steam id."""
    return str(910000000000000000 + int(p.sid[-9:]))


def _code(n):
    return "SCR-" + "".join(CROCKFORD[(n >> (5 * i)) & 31] for i in range(12))


async def _relay_off(env, *, pass_off):
    """X with three relay rows addressed to it, inserted with ids against
    their physical order (a sequential scan meets 300, then 200, then 100); a
    side transaction holds the middle row; X's relay-off through the bot's
    route then waits for it. Returns (whether row 300 could be locked while
    the relay-off waited, the route's answer). pass_off: RELAY_OFF_LOCK_SQL
    made a no-op (LIMIT 0)."""
    env.mp.setenv("API_SECRET_KEY", INTERNAL)
    s, x = await env.players(2)
    for rid in OFF_IDS:
        mid = await _sent(env, s, x)
        await env.conn.execute(
            "INSERT INTO pending_dms (id, steam_id, content, mail_id, relay_code, sender_steam_id)"
            " VALUES ($1, $2, 'A relayed copy.', $3, $4, $5)", rid, x.sid, mid, _code(rid), s.sid)
    did = _discord_id(x)
    await env.conn.execute(
        "UPDATE players SET discord_id = $2, mail_discord_relay = true WHERE id = $1", x.id, did)
    order = [r["id"] for r in await env.conn.fetch(
        "SELECT id FROM pending_dms WHERE steam_id = $1 ORDER BY ctid", x.sid)]
    assert order == list(OFF_IDS), order
    assert x.sid.isdigit(), x.sid
    plan = json.loads(await env.conn.fetchval(
        "EXPLAIN (FORMAT JSON) UPDATE pending_dms SET cancelled_at = NOW(), claim_id = NULL,"
        " claim_until = NULL WHERE steam_id = '%s' AND relay_code IS NOT NULL"
        " AND delivered_at IS NULL AND cancelled_at IS NULL" % x.sid))
    node = plan[0]["Plan"]["Plans"][0]["Node Type"]
    print("[MDPL-PLAN] the relay-off cancel's scan: %s" % node)
    if pass_off:   # the control's premise: the cancel alone meets the rows in physical order
        assert node == "Seq Scan", plan
    side, side_pid = await _holding(env, OFF_IDS[1])
    req = mail_discord._RelayPrefReq(discord_id=did, enabled=False)
    ctx = (env.rewriting("ORDER BY id FOR NO KEY UPDATE", "ORDER BY id LIMIT 0",
                         where="SELECT id FROM pending_dms WHERE steam_id = ")
           if pass_off else contextlib.nullcontext([]))
    with ctx as off:
        t = asyncio.create_task(env.call(
            lambda db: mail_discord.mail_relay_pref(req, x_internal_key=INTERNAL, db=db)))
        state, w = await _settle(env, t, by=side_pid)
        assert state == "waits", (state, w)
        free = await _free(env, OFF_IDS[0])
        await side.execute("ROLLBACK")
        ans = await asyncio.wait_for(t, BOUND)
    assert off or not pass_off, "the mutant did not apply"
    return free, ans


def test_r4_the_relay_off_takes_its_rows_in_id_order(monkeypatch):
    """Waiting for row 200, the relay-off holds no row above it: 300 is free."""
    async def body(env):
        free, ans = await _relay_off(env, pass_off=False)
        assert free, "the relay-off held a row above the one it waited for"
        assert ans.status == 200 and ans["withdrawn"] == 3, ans
    case(monkeypatch, body, prefix="mdpl")


def test_r4_control_without_its_pass_the_relay_off_holds_a_higher_row(monkeypatch):
    """The control: the cancel alone, in scan order, holds 300 while it waits."""
    async def body(env):
        free, ans = await _relay_off(env, pass_off=True)
        assert not free, "the cancel did not hold 300: the control's premise failed"
        assert ans.status == 200, ans
    case(monkeypatch, body, prefix="mdpl")


# -- R4: the poll's RETIRE --------------------------------------------------------------------

async def _retire(env, *, skip_off):
    """Three DMs at the attempt cap; a side transaction holds the middle one;
    the bot's poll runs. Returns (ids, how the poll stood, its answer).
    skip_off: the RETIRE's SKIP LOCKED removed."""
    env.mp.setenv("API_SECRET_KEY", INTERNAL)
    (x,) = await env.players(1)
    ids = []
    for _ in range(3):
        ids.append(await env.conn.fetchval(
            "INSERT INTO pending_dms (steam_id, content, attempts) VALUES ($1, 'A notice.', $2) RETURNING id",
            x.sid, main.PENDING_DM_MAX_ATTEMPTS))
    side, side_pid = await _holding(env, ids[1])
    ctx = (env.rewriting("FOR NO KEY UPDATE SKIP LOCKED)", "FOR NO KEY UPDATE)",
                         where="SET undeliverable = true") if skip_off else contextlib.nullcontext([]))
    with ctx as off:
        t = asyncio.create_task(env.call(
            lambda db: main.internal_pending_dms(x_internal_key=INTERNAL, db=db)))
        state, _w = await _settle(env, t, by=side_pid)
        await side.execute("ROLLBACK")
        first = await asyncio.wait_for(t, BOUND)
    assert off or not skip_off, "the mutant did not apply"
    return ids, state, first


def test_r4_the_polls_retire_skips_a_held_row_and_the_next_poll_retires_it(monkeypatch):
    async def body(env):
        ids, state, first = await _retire(env, skip_off=False)
        assert state == "done" and first.status == 200, (state, first)
        got = {r["id"]: r["undeliverable"] for r in await env.conn.fetch(
            "SELECT id, undeliverable FROM pending_dms WHERE id = ANY($1::bigint[])", ids)}
        assert got == {ids[0]: True, ids[1]: False, ids[2]: True}, got
        second = await env.call(lambda db: main.internal_pending_dms(x_internal_key=INTERNAL, db=db))
        assert second.status == 200, second
        assert await env.conn.fetchval(
            "SELECT undeliverable FROM pending_dms WHERE id = $1", ids[1]) is True
    case(monkeypatch, body, prefix="mdpl")


def test_r4_control_without_skip_locked_the_retire_waits(monkeypatch):
    async def body(env):
        _ids, state, first = await _retire(env, skip_off=True)
        assert state == "waits", state
        assert first.status == 200, first
    case(monkeypatch, body, prefix="mdpl")


# -- R4: the premise of the deletion's pass -------------------------------------------------

async def _send_after_the_flush(env, *, keep_sid):
    """Y (relay on) is deleted, parked just before its relay pass, past the
    anonymising UPDATE's flush; S sends to Y meanwhile. keep_sid: the
    mutant, that UPDATE leaves steam_id as it is, so it takes FOR NO KEY
    UPDATE in place of FOR UPDATE."""
    _arm(env)
    _order_only(env)
    y, s = await env.players(2)
    await env.conn.execute(
        "UPDATE players SET discord_id = $2, mail_discord_relay = true WHERE id = $1", y.id,
        _discord_id(y))
    at = _parks(env)
    spot = at(PASS_MARK, "before")
    ctx = (env.rewriting(FLUSH_SID, r"steam_id=COALESCE(players.steam_id, \1\2)",
                         where="UPDATE players SET") if keep_sid else contextlib.nullcontext([]))
    with ctx as kept:
        td = asyncio.create_task(_delete(env, y))
        await _parked(spot, td)
        ts = asyncio.create_task(env.mail(s, [y], body="A message racing the deletion."))
        state, w = await _settle(env, ts, by=spot.pid)
        a, b = await _finish([td, ts], [spot])
    assert kept or not keep_sid, "the mutant did not apply"
    return y, state, w, a, b


def test_r4_after_the_flush_a_send_to_the_player_waits(monkeypatch):
    async def body(env):
        y, state, w, a, b = await _send_after_the_flush(env, keep_sid=False)
        assert state == "waits" and "FOR KEY SHARE" in (w["query"] or ""), (state, w)
        assert a.status == 200 and a["status"] == "anonymized", a
        assert not _bad(b), _name(b)
        assert await env.conn.fetchval("SELECT COUNT(*) FROM pending_dms WHERE steam_id = $1", y.sid) == 0
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM mail_recipients WHERE recipient_id = $1", y.id) == 0
    case(monkeypatch, body, prefix="mdpl")


def test_r4_control_with_the_steam_id_kept_the_send_does_not_wait(monkeypatch):
    async def body(env):
        y, state, w, _a, _b = await _send_after_the_flush(env, keep_sid=True)
        assert state == "done", (state, w)
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM mail_recipients WHERE recipient_id = $1", y.id) == 1
    case(monkeypatch, body, prefix="mdpl")


# -- R5 ---------------------------------------------------------------------------------------

def test_r5_control_the_ranked_step_above_the_lobby_locks_deadlocks(monkeypatch):
    """R5's control, the ban scene with the deletion's ranked_queue rows
    deleted at its key statement, above its lobby locks (a data-modifying
    WITH, which always runs): the deletion holds X's ranked row, the ban
    holds the lobby and waits for that row, the deletion then waits for the
    lobby."""
    async def body(env):
        _arm(env)
        _order_only(env)
        _lid, (p, x) = await env.lobby("team", 2)
        (mod,) = await env.players(1)
        await env.conn.execute("INSERT INTO admin_users (steam_id, granted_at) VALUES ($1, NOW())"
                               " ON CONFLICT DO NOTHING", mod.sid)
        await _matched(env, p, x)
        await _matched(env, x, p)
        early = ("WITH rq AS (DELETE FROM ranked_queue WHERE player_id IN ("
                 "SELECT player_id FROM ranked_queue WHERE player_id = '%s' OR matched_with = '%s'"
                 " FOR UPDATE SKIP LOCKED)) SELECT pg_advisory_xact_lock(hashtext('pc_snapshot'))"
                 % (p.id, p.id))

        async def ban(db):
            out = await main._apply_ban_core(db, admin_steam_id=mod.sid, target_steam_id=x.sid,
                                             reason="mdpl staged ban")
            await db.commit()
            return out

        at = _parks(env)
        spot = at(KEY_SQL, "after")
        with env.rewriting(KEY_EXACT, early) as moved:
            td = asyncio.create_task(_delete(env, p))
            await _parked(spot, td)                   # holds P's and X's ranked rows, no lobby yet
            tb = asyncio.create_task(env.call(ban))
            state, w = await _settle(env, tb, by=spot.pid)
            assert state == "waits", (state, w)
            await _past_deadlock_check(env)
            a, b = await _finish([td, tb], [spot])
        assert moved, "the mutant did not apply"
        assert _circle(a, b), ("no 40P01", _name(a), _name(b))
    case(monkeypatch, body, prefix="mdpl")


# -- C2 ---------------------------------------------------------------------------------------

async def _individual(env):
    """A player whose Steam id is a public individual SteamID64: the lease
    route refuses any other id (404) before its identity lock."""
    q = await env.player()
    sid = str(0x0110000100000000 + 40600000 + env.serial)
    await env.conn.execute("UPDATE players SET steam_id = $2 WHERE id = $1", q.id, sid)
    return inv_pg.P(q.id, sid, q.name)


async def _lease_during_deletion(env, *, key_off):
    """The deletion of P parked past its drain, before the pool key (it holds
    the identity key and no row lock); a lease start naming P meanwhile.
    key_off: the mutant, the identity key statement takes no lock."""
    _arm(env)
    _order_only(env)
    env.mp.setenv("API_SECRET_KEY", INTERNAL)
    p = await _individual(env)
    at = _parks(env)
    spot = at(KEY_SQL, "before")
    ctx = env.rewriting(IDENTITY_KEY, r"hashtext(\1)") if key_off else contextlib.nullcontext([])
    with ctx as off:
        td = asyncio.create_task(_delete(env, p))
        await _parked(spot, td)
        lease = await env.call(lambda db: main.internal_pc_lease(
            {"subject_ref": str(p.id)}, x_internal_key=INTERNAL, db=db))
        (a,) = await _finish([td], [spot])
    assert off or not key_off, "the mutant did not apply"
    return lease, a


def _busy(ans):
    return ans.status == 409 and isinstance(ans.body, dict) and ans.body.get("error") == "subject_busy"


def test_c2_no_lease_starts_while_the_deletion_holds_the_identity_key(monkeypatch):
    async def body(env):
        lease, a = await _lease_during_deletion(env, key_off=False)
        assert _busy(lease), lease
        assert a.status == 200 and a["status"] == "anonymized", a
    case(monkeypatch, body, prefix="mdpl")


def test_c2_control_without_the_identity_key_the_lease_is_not_refused_busy(monkeypatch):
    async def body(env):
        lease, _a = await _lease_during_deletion(env, key_off=True)
        assert not _busy(lease), lease
    case(monkeypatch, body, prefix="mdpl")


# -- C3 ---------------------------------------------------------------------------------------

async def _past_the_deadline(env, *, check_off):
    """The deletion of P parked after its last statement (the case scrub);
    the clock then moves past the attempt's deadline. check_off: the mutant,
    the deadline read made false (main._deletion_past)."""
    _arm(env)
    (p,) = await env.players(1)
    skew = {"s": 0.0}
    real = time.monotonic
    env.mp.setattr(main, "_deletion_clock", lambda: real() + skew["s"])
    if check_off:
        env.mp.setattr(main, "_deletion_past", lambda deadline: False)
    at = _parks(env)
    spot = at(main._DELETE_CASE_SCRUB_SQL[:40], "after")
    td = asyncio.create_task(_delete(env, p))
    await _parked(spot, td)
    skew["s"] = main._DELETION_BUDGET_S + 1.0
    (a,) = await _finish([td], [spot])
    row = await env.conn.fetchrow("SELECT steam_id, deleted_at FROM players WHERE id = $1", p.id)
    kept = await env.conn.fetchval(
        "SELECT COUNT(*) FROM deleted_steam_ids WHERE steam_id_hash = $1", main._hash_steam_id(p.sid))
    return p, a, row, kept


def test_c3_no_commit_after_the_deadline(monkeypatch):
    async def body(env):
        p, a, row, kept = await _past_the_deadline(env, check_off=False)
        assert (a.status, a.body) == (503, main._DELETION_REFUSAL), a
        assert row["steam_id"] == p.sid and row["deleted_at"] is None, dict(row)
        assert kept == 0, kept
    case(monkeypatch, body, prefix="mdpl")


def test_c3_control_without_the_deadline_read_the_deletion_commits_late(monkeypatch):
    async def body(env):
        p, a, row, kept = await _past_the_deadline(env, check_off=True)
        assert a.status == 200 and a["status"] == "anonymized", a
        assert row["steam_id"] != p.sid and row["deleted_at"] is not None, dict(row)
        assert kept == 1, kept
    case(monkeypatch, body, prefix="mdpl")


# -- R6b --------------------------------------------------------------------------------------

async def _wager_on_a_disbanded_lobby(env, *, flag_off, code="40P01"):
    """P alone in an open team lobby, B's open wager on it. The bet helper's
    read in the deletion's savepoint ends once in SQLSTATE `code`: it calls a
    function that raises it the first time only (its sequence survives the
    rollback). flag_off: the mutant, _retryable_for_caller made false.
    Returns (the answer, the wager's status, B's gold_spent, the function's
    calls, whether P's row is anonymised)."""
    _arm(env)
    lid, (p,) = await env.lobby("team", 1)
    (b,) = await env.players(1)
    await env.conn.execute("UPDATE players SET gold_earned = 200, gold_spent = 100 WHERE id = $1", b.id)
    bet = await env.conn.fetchval(
        "INSERT INTO lobby_bets (mode, lobby_id, player_id, amount, target_steams)"
        " VALUES ('team', $1, $2, 10, $3) RETURNING id", lid, b.id, p.sid)
    await env.conn.execute(FAIL_ONCE % {"code": code})
    try:
        if flag_off:
            env.mp.setattr(main, "_retryable_for_caller", lambda ex, raise_retryable: False)
        with env.rewriting(BET_READ, "FROM lobby_bets WHERE mdpl_fail_once() AND mode = ",
                           where="ORDER BY created_at, id") as hits:
            a = await _delete(env, p)
        assert hits, "the forced error did not apply"
        st = await env.conn.fetchval("SELECT status FROM lobby_bets WHERE id = $1", bet)
        spent = await env.conn.fetchval("SELECT gold_spent FROM players WHERE id = $1", b.id)
        calls = await env.conn.fetchval("SELECT last_value FROM mdpl_once")
        anon = await env.conn.fetchval("SELECT steam_id <> $2 FROM players WHERE id = $1", p.id, p.sid)
    finally:
        # The case schema must hold only what its build left (the harness's
        # census refuses to drop or reuse it otherwise).
        await env.conn.execute(FAIL_ONCE_GONE)
    return a, st, spent, calls, anon


def test_r6b_a_deadlock_victim_in_a_bet_helper_runs_the_deletion_again(monkeypatch, capsys):
    async def body(env):
        a, st, spent, calls, anon = await _wager_on_a_disbanded_lobby(env, flag_off=False)
        assert a.status == 200 and a["status"] == "anonymized" and anon, (a, anon)
        assert st == "refunded" and spent == 90, (st, spent)
        assert calls >= 2, calls
    case(monkeypatch, body, prefix="mdpl")
    out = capsys.readouterr().out
    assert "deletion attempt 1 ended by 40P01" in out, out[-3000:]


def test_r6b_a_lock_timeout_in_a_bet_helper_refuses_at_once(monkeypatch, capsys):
    """55P03 is the attempt's lock_timeout ending a wait: the deadline has
    come. The helper hands it to the bound, which refuses at once: 503
    account_cleanup_contended, nothing written, no second attempt."""
    async def body(env):
        a, st, spent, calls, anon = await _wager_on_a_disbanded_lobby(env, flag_off=False, code="55P03")
        assert (a.status, a.body) == (503, main._DELETION_REFUSAL), a
        assert not anon, "the refused deletion wrote the player's row"
        assert st == "open" and spent == 100, (st, spent)
        assert calls == 1, calls
    case(monkeypatch, body, prefix="mdpl")
    assert "deletion attempt 1 ended" not in capsys.readouterr().out


@pytest.mark.parametrize("code", ["40P01", "55P03"])
def test_r6b_control_without_the_flag_the_helper_keeps_the_wager_open(monkeypatch, capsys, code):
    """The mutant for both tests above: the helper keeps its error, the
    deletion goes on and commits (a forced error moves no clock), and the
    wager stays open for the janitor's sweep."""
    async def body(env):
        a, st, spent, calls, anon = await _wager_on_a_disbanded_lobby(env, flag_off=True, code=code)
        assert a.status == 200 and a["status"] == "anonymized" and anon, (a, anon)
        assert st == "open" and spent == 100, (st, spent)
        assert calls >= 1, calls
    case(monkeypatch, body, prefix="mdpl")
    assert "deletion attempt 1 ended" not in capsys.readouterr().out
