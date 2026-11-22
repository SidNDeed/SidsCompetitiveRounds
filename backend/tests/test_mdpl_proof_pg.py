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
  player arriving there waits; with steam_id and discord_id left as they
  are (FOR NO KEY UPDATE) it does not, and its envelope outlives the
  deletion.
- R5, the ban scene's control: the ranked step back above the lobby locks
  deadlocks.
The bound (R6a, R6b):
- C2: a lease start naming the player is refused (409 subject_busy) while
  the deletion, past its drain, holds the identity key.
- C3: the clock past the deadline between the work and the commit: 503
  account_cleanup_contended, nothing written. Two checks stand there: the
  deadline read before the commit, and (since round 2's HIGH 1) the
  commit's own hold, which reads the clock before it flushes, arms and
  commits. Each refuses with the other off; with both off the deletion
  commits late.
- R6a: a wait for a held pool key ends at the deadline (the attempt's
  lock_timeout): 503 within the budget, nothing written; without the
  lock_timeout the wait outlasts the deadline.
- R6b: a deadlock victim inside a bet helper's savepoint runs the whole
  deletion again, and the bettor is refunded in its commit; a lock timeout
  there (55P03) refuses at once, with nothing written.
Round 1's HIGH, by class, with its hold half (test_mdpl_deletion_lock_order_pg
scenes 4 to 6 are the positive side):
- Each scene's control removes the change's own seam: the party guard a
  no-op (scene 4, the ban route's circle), the guard's identity key never
  taken (scene 5, the bettor's cancel), the FFA bet guard a no-op (scene 6,
  the stranded-bet sweep). The R5 control runs the ban's full route.
- POINT 2, what a refusal costs (#430): a party's players row, or its
  identity key, held for a moment ends one attempt; the holder lets go
  inside the first pause, and the next attempt answers 200 within the
  bound, with the log line naming what was held (#438).
- POINT 3: inside an attempt, a party row that does not exist leaves the
  stake refund as it is outside one (StakeRefundRefused, nothing written);
  a row or key another transaction holds is the signal, with nothing moved;
  a row and key the attempt holds itself pass. The FFA bet guard tells a
  held bet from a settled one, and takes a free one.
"""

import asyncio
import contextlib
import hashlib
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
from sqlalchemy.exc import DBAPIError  # noqa: E402
from test_mail_case_scrub_pg import (  # noqa: E402
    BOUND, CROCKFORD, _arm, _bad, _deadlock, _delete, _finish, _name, _parked, _parks, _relay_row,
    _settle)
from test_mdpl_deletion_lock_order_pg import (  # noqa: E402
    INTERNAL, KEY_SQL, TO_MARK, _admin_armed, _ban_route, _cancel_scene, _cap_scene, _circle_closed, _edition,
    _matched, _order_only, _past_deadlock_check, _print_of, _sent, _step4_scene, _sweep_scene,
    _phase_b_scene, _upgrade_scene, _wager_ban_scene)

BIND = r"(\$\d+|%s|%\(\w+\)s|:\w+)"          # a compiled bind, whatever the paramstyle
KEY_EXACT = re.compile(r"^SELECT pg_advisory_xact_lock\(hashtext\('pc_snapshot'\)\)$")
POOL_EXACT = re.compile(r"^DELETE FROM pc_pool_members WHERE player_id = " + BIND + "$")
POOL_MARK = "DELETE FROM pc_pool_members WHERE player_id = :pid"
PASS_MARK = "WHERE (relay_code IS NOT NULL AND steam_id = :sid)"   # _ERASE_RELAY_DMS_LOCK_SQL only
SETTLE_MARK = "UPDATE pending_dms u "                                # _PENDING_DM_SETTLE_SQL
IDENTITY_KEY = re.compile(r"pg_advisory_xact_lock\(hashtext\(" + BIND + r"\)\)")
# The flush's UPDATE of the player's row changes two columns that carry a
# unique index, steam_id always and discord_id when the player had a link:
# either change makes it FOR UPDATE. The mutant keeps both.
FLUSH_SID = re.compile(r"\b(steam_id|discord_id)=" + BIND + r"(::\w+(?:\(\d+\))?)?")
# pg_stat_activity keeps the head of a long statement: the envelope fan-out,
# main._MAIL_FANOUT_SQL, whose FOR KEY SHARE OF p is at its end.
FANOUT_HEAD = "INSERT INTO mail_recipients (message_id, recipient_id, kind, delivery) SELECT"
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
    """Y (relay on, so with a Discord link) is deleted, parked just before
    its relay pass, past the anonymising UPDATE's flush; S sends to Y
    meanwhile. keep_sid: the mutant, that UPDATE leaves steam_id and
    discord_id (each with a unique index) as they are, so it takes FOR NO
    KEY UPDATE in place of FOR UPDATE."""
    _arm(env)
    _order_only(env)
    y, s = await env.players(2)
    await env.conn.execute(
        "UPDATE players SET discord_id = $2, mail_discord_relay = true WHERE id = $1", y.id,
        _discord_id(y))
    at = _parks(env)
    spot = at(PASS_MARK, "before")
    ctx = (env.rewriting(FLUSH_SID, r"\1=COALESCE(players.\1, \2\3)",
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
        assert "FOR KEY SHARE OF p" in main._MAIL_FANOUT_SQL
        assert main._MAIL_FANOUT_SQL.startswith(FANOUT_HEAD)
        assert state == "waits" and (w["query"] or "").startswith(FANOUT_HEAD), (state, w)
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

async def _r5_scene(env, *, step4_waiting):
    """R5's ban scene with the deletion's ranked_queue rows deleted at its key
    statement, above its lobby locks (a data-modifying WITH, which always
    runs): the deletion holds X's ranked row, the ban holds the lobby and
    waits for that row, and the deletion comes to its step-4 lock of the
    lobby. step4_waiting: step 4's locks taken with a wait, as at 8d920c07
    (the form of _step4_scene's blocking mutant). Returns the deletion's and
    the ban's answers."""
    _arm(env)
    _admin_armed(env)
    _order_only(env)
    if step4_waiting:
        async def _wait_for_it(db, what, lock_stmt, seen_stmt, params):
            await db.execute(main.text(str(lock_stmt).replace(" SKIP LOCKED", "")), params)
        env.mp.setattr(main, "_deletion_take_or_yield", _wait_for_it)
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

    at = _parks(env)
    spot = at(KEY_SQL, "after")
    with env.rewriting(KEY_EXACT, early) as moved:
        td = asyncio.create_task(_delete(env, p))
        await _parked(spot, td)                   # holds P's and X's ranked rows, no lobby yet
        tb = asyncio.create_task(env.call(_ban_route(mod, x)))
        state, w = await _settle(env, tb, by=spot.pid)
        assert state == "waits", (state, w)
        await _past_deadlock_check(env)
        a, b = await _finish([td, tb], [spot])
    assert moved, "the mutant did not apply"
    return a, b


def test_r5_control_the_ranked_step_above_the_lobby_locks_with_step_4_waiting_deadlocks(monkeypatch):
    """R5's control: the ranked step above the lobby locks, and step 4's
    locks taken with a wait as at 8d920c07. The deletion then waits for the
    lobby the ban holds while the ban waits for X's ranked row: the circle
    closes. With step 4 as at the tip the same order closes no circle (the
    mirror below), so this control takes both changes back."""
    async def body(env):
        a, b = await _r5_scene(env, step4_waiting=True)
        assert _circle(a, b), ("no 40P01", _name(a), _name(b))
    case(monkeypatch, body, prefix="mdpl")


def test_r5_mirror_the_ranked_step_above_the_lobby_locks_yields_at_step_4_and_both_finish(monkeypatch, capsys):
    """R5's mirror: the ranked step above the lobby locks, step 4 as at the
    tip. The deletion meets the lobby the ban holds, ends its attempt with
    the held signal (which lets X's ranked row go), and a later attempt
    finishes after the ban: both answer 200, and neither is a 40P01."""
    async def body(env):
        capsys.readouterr()
        a, b = await _r5_scene(env, step4_waiting=False)
        out = capsys.readouterr().out
        assert not _circle(a, b), ("a 40P01", _name(a), _name(b))
        assert a.status == 200 and a["status"] == "anonymized", _name(a)
        assert b.status == 200 and b["status"] == "banned", _name(b)
        assert "met a held" in out, out[-2000:]
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

async def _past_the_deadline(env, *, read_off, arming_off):
    """The deletion of P parked after its last statement (the case scrub);
    the clock then moves past the attempt's deadline. Two checks stand
    between that point and a COMMIT: the route's deadline read before its
    commit (main._deletion_past), and the commit's own hold, which reads the
    clock before it flushes, arms and commits (the session's commit as
    main._deletion_arm_every_statement installs it). read_off: the mutant,
    the deadline read made false. arming_off: the mutant, the arming made to
    install nothing on the session and to return a no-op undo (what it
    returns for a session without execute), so the session's own commit
    runs. Each switch that is on asserts that its replacement was called."""
    _arm(env)
    (p,) = await env.players(1)
    skew = {"s": 0.0}
    real = time.monotonic
    env.mp.setattr(main, "_deletion_clock", lambda: real() + skew["s"])
    reads, armings = [], []
    if read_off:
        def no_read(deadline):
            reads.append(deadline)
            return False
        env.mp.setattr(main, "_deletion_past", no_read)
    if arming_off:
        def no_arming(db, deadline):
            armings.append(deadline)
            return lambda: None
        env.mp.setattr(main, "_deletion_arm_every_statement", no_arming)
    at = _parks(env)
    spot = at(main._DELETE_CASE_SCRUB_SQL[:40], "after")
    td = asyncio.create_task(_delete(env, p))
    await _parked(spot, td)
    skew["s"] = main._DELETION_BUDGET_S + 1.0
    (a,) = await _finish([td], [spot])
    row = await env.conn.fetchrow("SELECT steam_id, deleted_at FROM players WHERE id = $1", p.id)
    kept = await env.conn.fetchval(
        "SELECT COUNT(*) FROM deleted_steam_ids WHERE steam_id_hash = $1", main._hash_steam_id(p.sid))
    assert reads or not read_off, "the mutant did not apply"
    assert armings or not arming_off, "the mutant did not apply"
    return p, a, row, kept


def test_c3_no_commit_after_the_deadline(monkeypatch):
    async def body(env):
        p, a, row, kept = await _past_the_deadline(env, read_off=False, arming_off=False)
        assert (a.status, a.body) == (503, main._DELETION_REFUSAL), a
        assert row["steam_id"] == p.sid and row["deleted_at"] is None, dict(row)
        assert kept == 0, kept
    case(monkeypatch, body, prefix="mdpl")


def test_c3_the_commit_s_own_hold_refuses_without_the_deadline_read(monkeypatch, capsys):
    """The deadline read made false, the arming on: the commit's own hold
    reads the clock and raises the signal, so the bound prints that the
    attempt reached its deadline and answers 503, with nothing written."""
    async def body(env):
        capsys.readouterr()
        p, a, row, kept = await _past_the_deadline(env, read_off=True, arming_off=False)
        out = capsys.readouterr().out
        assert (a.status, a.body) == (503, main._DELETION_REFUSAL), a
        assert row["steam_id"] == p.sid and row["deleted_at"] is None, dict(row)
        assert kept == 0, kept
        assert "deletion attempt 1 reached its deadline" in out, out[-2000:]
    case(monkeypatch, body, prefix="mdpl")


def test_c3_the_deadline_read_refuses_without_the_arming(monkeypatch, capsys):
    """The arming off, the deadline read on: the read refuses by itself
    before the commit, 503 with nothing written, and the bound receives no
    signal, so it prints no deadline line."""
    async def body(env):
        capsys.readouterr()
        p, a, row, kept = await _past_the_deadline(env, read_off=False, arming_off=True)
        out = capsys.readouterr().out
        assert (a.status, a.body) == (503, main._DELETION_REFUSAL), a
        assert row["steam_id"] == p.sid and row["deleted_at"] is None, dict(row)
        assert kept == 0, kept
        assert "reached its deadline" not in out, out[-2000:]
    case(monkeypatch, body, prefix="mdpl")


def test_c3_control_without_the_read_and_the_arming_the_deletion_commits_late(monkeypatch):
    """C3's control: the deadline read made false and the arming off. No
    check stands between the parked point and the session's own COMMIT, so
    the deletion commits past its deadline: the scene can commit late."""
    async def body(env):
        p, a, row, kept = await _past_the_deadline(env, read_off=True, arming_off=True)
        assert a.status == 200 and a["status"] == "anonymized", a
        assert row["steam_id"] != p.sid and row["deleted_at"] is not None, dict(row)
        assert kept == 1, kept
    case(monkeypatch, body, prefix="mdpl")


# -- R6a: one wait ends at the deadline -------------------------------------------------------

async def _key_held_past_the_budget(env, *, timeout_off):
    """A side session holds the pool snapshot key; the deletion of P, with a
    budget of 4 s, waits for it there. The side lets go 3 s after the
    deadline. The wait cap is off (_DELETION_WAIT_CAP_S past the budget), so
    the one wait is armed with the time left, as in lesson 689's control:
    one long holder shows that the time-left arming fires. timeout_off: the
    mutant, the statement arming made to set nothing (the arming SQL
    replaced by a read of its two values). Returns (P, the answer, the
    seconds from the call to the answer, P's row)."""
    _arm(env)
    (p,) = await env.players(1)
    env.mp.setattr(main, "_DELETION_BUDGET_S", 4.0)
    env.mp.setattr(main, "_DELETION_ATTEMPT_MIN_S", 1.0)
    env.mp.setattr(main, "_DELETION_WAIT_CAP_S", 60.0, raising=False)
    if timeout_off:
        env.mp.setattr(main, "_DELETION_ARM_SQL", "SELECT CAST(:lt AS text), CAST(:st AS text)")
    side = await env.side()
    await side.execute("SELECT pg_advisory_lock(hashtext('pc_snapshot'))")

    async def let_go():
        await asyncio.sleep(main._DELETION_BUDGET_S + 3.0)
        await side.execute("SELECT pg_advisory_unlock(hashtext('pc_snapshot'))")

    rel = asyncio.create_task(let_go())
    t0 = time.monotonic()
    a = await _delete(env, p)
    spent = time.monotonic() - t0
    await rel
    row = await env.conn.fetchrow("SELECT steam_id, deleted_at FROM players WHERE id = $1", p.id)
    return p, a, spent, row


def test_r6a_a_wait_for_a_held_key_ends_at_the_deadline(monkeypatch):
    """The wait's timeouts, armed with the time left, end it at the deadline:
    503 account_cleanup_contended within the budget, nothing written."""
    async def body(env):
        p, a, spent, row = await _key_held_past_the_budget(env, timeout_off=False)
        assert (a.status, a.body) == (503, main._DELETION_REFUSAL), a
        assert spent < main._DELETION_BUDGET_S + 1.0, spent
        assert row["steam_id"] == p.sid and row["deleted_at"] is None, dict(row)
    case(monkeypatch, body, prefix="mdpl")


def test_r6a_control_without_the_lock_timeout_the_wait_outlasts_the_deadline(monkeypatch):
    """The mutant: the wait lasts until the side lets go, past the deadline;
    the next statement is refused before it starts (past the deadline), so
    nothing is written."""
    async def body(env):
        p, a, spent, row = await _key_held_past_the_budget(env, timeout_off=True)
        assert spent >= main._DELETION_BUDGET_S + 3.0, spent
        assert (a.status, a.body) == (503, main._DELETION_REFUSAL), a
        assert row["steam_id"] == p.sid and row["deleted_at"] is None, dict(row)
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


def test_r6b_a_lock_wait_that_reached_the_cap_in_a_bet_helper_runs_the_deletion_again(monkeypatch, capsys):
    """55P03 before the deadline is a lock wait that reached the cap (0.5 s):
    a held lock. The statement arming raises it as the held signal, the
    helper hands it back, and the bound runs the attempt again after the
    pause: 200, the wager refunded once."""
    async def body(env):
        a, st, spent, calls, anon = await _wager_on_a_disbanded_lobby(env, flag_off=False, code="55P03")
        assert a.status == 200 and a["status"] == "anonymized" and anon, (a, anon)
        assert st == "refunded" and spent == 90, (st, spent)
        assert calls >= 2, calls
    case(monkeypatch, body, prefix="mdpl")
    out = capsys.readouterr().out
    assert ("deletion attempt 1 met a held %s;" % main._DELETION_WAIT_WHAT) in out, out[-3000:]


def test_r6b_a_statement_timeout_in_a_bet_helper_refuses_at_once(monkeypatch, capsys):
    """57014 is the statement_timeout armed with the time left: the deadline
    has come. The statement arming raises it as the deadline, the helper
    hands it back, and the bound refuses at once: 503
    account_cleanup_contended, nothing written, no second attempt."""
    async def body(env):
        a, st, spent, calls, anon = await _wager_on_a_disbanded_lobby(env, flag_off=False, code="57014")
        assert (a.status, a.body) == (503, main._DELETION_REFUSAL), a
        assert not anon, "the refused deletion wrote the player's row"
        assert st == "open" and spent == 100, (st, spent)
        assert calls == 1, calls
    case(monkeypatch, body, prefix="mdpl")
    out = capsys.readouterr().out
    assert "deletion attempt 1 reached its deadline" in out, out[-3000:]
    assert "deletion attempt 1 ended" not in out and "met a held" not in out, out[-3000:]


@pytest.mark.parametrize("code", ["40P01", "55P03", "57014"])
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


# -- R6b, a caller that is not the deletion (the integrator's C1 and C2) -----------------------
#
# The flag travels as an argument: raise_retryable, False by default at
# every helper; the deletion passes True at its four calls, and
# _reconcile_ffa_lobby_bets passes its own value on at its two calls of
# _refund_ffa_lobby_bets. Nothing else carries it. The deadline is the one
# value the bound keeps in a context variable (_deletion_deadline), set for
# each attempt and reset in the same try's finally, in _deletion_bounded
# alone.

LEAVE_DISBANDED = inv_pg.Answer(200, {"status": "ok", "disbanded": True, "remaining": 0})
POOL_KEY_FAILS = "SELECT mdpl_fail_once(), pg_advisory_xact_lock(hashtext('pc_snapshot'))"
REFUND_FAILED = "[LOBBY-BETS] refund pass failed for team lobby "


async def _open_wager(env, lid, p):
    """B's open wager of 10 on `lid`, backing `p`: (B, the wager's id)."""
    (b,) = await env.players(1)
    await env.conn.execute("UPDATE players SET gold_earned = 200, gold_spent = 100 WHERE id = $1", b.id)
    bet = await env.conn.fetchval(
        "INSERT INTO lobby_bets (mode, lobby_id, player_id, amount, target_steams)"
        " VALUES ('team', $1, $2, 10, $3) RETURNING id", lid, b.id, p.sid)
    return b, bet


async def _wager_state(env, b, bet):
    st = await env.conn.fetchval("SELECT status FROM lobby_bets WHERE id = $1", bet)
    spent = await env.conn.fetchval("SELECT gold_spent FROM players WHERE id = $1", b.id)
    return st, spent


async def _leave_with_a_forced_55p03(env, p, lid):
    """P, alone in `lid`, leaves it: the lobby is disbanded and
    _lobby_leave_impl calls _refund_lobby_bets with its default flag. The
    helper's read ends once in 55P03, as in the deletion's R6b test. Returns
    (the answer, or the database error that escaped, the function's calls)."""
    await env.conn.execute(FAIL_ONCE % {"code": "55P03"})
    try:
        with env.rewriting(BET_READ, "FROM lobby_bets WHERE mdpl_fail_once() AND mode = ",
                           where="ORDER BY created_at, id") as hits:
            try:
                out = await env.leave("team", p, lid)
            except DBAPIError as exc:
                out = exc
        assert hits, "the forced error did not apply"
        calls = await env.conn.fetchval("SELECT last_value FROM mdpl_once")
    finally:
        await env.conn.execute(FAIL_ONCE_GONE)
    return out, calls


def test_r6b_c1_a_lobby_leave_keeps_the_helpers_catch(monkeypatch, capsys):
    """C1: the same forced 55P03 through a caller that is not the deletion
    (the leave that disbands a lobby) is caught where it was caught -- the
    helper's savepoint, its failure line, the wager left open for the
    janitor's orphan arm -- and the leave answers as a leave without the
    error does."""
    async def body(env):
        _arm(env)
        lid, (p,) = await env.lobby("team", 1)
        b, bet = await _open_wager(env, lid, p)
        out, calls = await _leave_with_a_forced_55p03(env, p, lid)
        assert not isinstance(out, BaseException), out
        assert out == LEAVE_DISBANDED, out
        assert calls == 1, calls
        assert await _wager_state(env, b, bet) == ("open", 100)
        # The twin: the same leave with no error refunds at once.
        lid2, (p2,) = await env.lobby("team", 1)
        b2, bet2 = await _open_wager(env, lid2, p2)
        plain = await env.leave("team", p2, lid2)
        assert plain == out, (plain, out)
        assert await _wager_state(env, b2, bet2) == ("refunded", 90)
    case(monkeypatch, body, prefix="mdpl")
    printed = capsys.readouterr().out
    assert printed.count(REFUND_FAILED) == 1, printed[-3000:]


def test_r6b_c1_control_a_predicate_that_ignores_the_flag_breaks_the_leave(monkeypatch):
    """C1's mutant: _retryable_for_caller answers as under the deletion for
    every caller. The 55P03 leaves the helper and the leave itself fails."""
    async def body(env):
        _arm(env)
        real = main._retryable_for_caller
        env.mp.setattr(main, "_retryable_for_caller", lambda ex, raise_retryable: real(ex, True))
        lid, (p,) = await env.lobby("team", 1)
        b, bet = await _open_wager(env, lid, p)
        out, calls = await _leave_with_a_forced_55p03(env, p, lid)
        assert isinstance(out, DBAPIError), out
        assert getattr(out.orig, "sqlstate", None) == "55P03", out
        assert calls == 1, calls
        assert await _wager_state(env, b, bet) == ("open", 100)
        assert await env.members("team", lid), "the failed leave was written"
    case(monkeypatch, body, prefix="mdpl")


def test_r6b_c2_a_call_after_a_refused_and_a_failed_deletion_sees_the_flag_off(monkeypatch, capsys):
    """C2, in one task: (1) a deletion refused (a 57014 in its bet helper,
    503); (2) a deletion ended by another error (23505 at its pool key
    statement, which leaves the route as it came); after each, the deadline
    variable is unset in the caller's context; (3) then a leave of the
    refused deletion's player disbands the same lobby, meets the same forced
    55P03 in the same helper, and the helper catches it: the flag is off."""
    async def body(env):
        _arm(env)
        assert main._deletion_deadline.get() is None
        lid, (p,) = await env.lobby("team", 1)
        b, bet = await _open_wager(env, lid, p)
        await env.conn.execute(FAIL_ONCE % {"code": "57014"})
        try:
            with env.rewriting(BET_READ, "FROM lobby_bets WHERE mdpl_fail_once() AND mode = ",
                               where="ORDER BY created_at, id") as hits:
                a = await _delete(env, p)
            assert hits, "the forced error did not apply"
        finally:
            await env.conn.execute(FAIL_ONCE_GONE)
        assert (a.status, a.body) == (503, main._DELETION_REFUSAL), a
        assert await _wager_state(env, b, bet) == ("open", 100)
        assert main._deletion_deadline.get() is None, "set after a refusal"

        (y,) = await env.players(1)
        await env.conn.execute(FAIL_ONCE % {"code": "23505"})
        try:
            with env.rewriting(KEY_EXACT, POOL_KEY_FAILS) as hits:
                try:
                    err = await _delete(env, y)
                except DBAPIError as exc:
                    err = exc
            assert hits, "the forced error did not apply"
        finally:
            await env.conn.execute(FAIL_ONCE_GONE)
        assert isinstance(err, DBAPIError) and getattr(err.orig, "sqlstate", None) == "23505", err
        assert main._deletion_deadline.get() is None, "set after an error"
        assert await env.conn.fetchval("SELECT deleted_at FROM players WHERE id = $1", y.id) is None

        out, calls = await _leave_with_a_forced_55p03(env, p, lid)
        assert not isinstance(out, BaseException), out
        assert out == LEAVE_DISBANDED and calls == 1, (out, calls)
        assert await _wager_state(env, b, bet) == ("open", 100)
    case(monkeypatch, body, prefix="mdpl")
    printed = capsys.readouterr().out
    assert printed.count(REFUND_FAILED) == 1, printed[-3000:]


# -- round 1's HIGH, by class: the scenes' controls, POINT 2 and POINT 3 ------------------------

def test_r1h_scene4_control_without_the_guard_the_ban_s_circle_closes(monkeypatch, capsys):
    """Scene 4 with _deletion_lock_party_row a no-op: the deletion waits for
    the moderator's players row, which the ban route holds while it waits
    for X's ranked row: the circle round 1 found."""
    async def body(env):
        a, b, st, spent, out = await _wager_ban_scene(env, capsys, guard_off=True)
        assert _circle_closed(a, b, out), ("no circle", _name(a), _name(b), out[-1500:])
    case(monkeypatch, body, prefix="mdpl")


def test_r1h_scene5_control_without_the_identity_key_the_cancel_s_circle_closes(monkeypatch, capsys):
    """Scene 5 with the guard's identity key never taken: the cancel claims
    the L2 wager and waits for B's players row, which the deletion holds
    from L1's refund; the deletion then waits for that wager row."""
    async def body(env):
        a, c, st, spent, out = await _cancel_scene(env, capsys, key_off=True)
        assert _circle_closed(a, c, out), ("no circle", _name(a), _name(c), out[-1500:])
    case(monkeypatch, body, prefix="mdpl")


def test_r1h_scene6_control_without_the_bet_guard_the_sweep_s_circle_closes(monkeypatch, capsys):
    """Scene 6 with _deletion_lock_ffa_bet a no-op: the deletion's claim
    waits for the sweep's, while the sweep waits for P's players row."""
    async def body(env):
        a, s, kind, spent, out = await _sweep_scene(env, capsys, guard_off=True)
        assert _circle_closed(a, s, out), ("no circle", _name(a), _name(s), out[-1500:])
    case(monkeypatch, body, prefix="mdpl")


async def _hold(env, kind, p):
    """A side session in an open transaction holding `p`'s players row FOR NO
    KEY UPDATE (kind "row") or `p`'s identity key (kind "key")."""
    side = await env.side()
    await side.execute("BEGIN")
    if kind == "row":
        assert await side.fetchval("SELECT id FROM players WHERE id = $1 FOR NO KEY UPDATE", p.id) == p.id
    else:
        await side.execute("SELECT pg_advisory_xact_lock(hashtext($1))", p.sid)
    return side


async def _held_for_a_moment(env, capsys, kind):
    """POINT 2's scene. B's open wager on P's lobby; a side session holds B's
    players row or identity key when the deletion starts, and lets it go
    0.1 s after the deletion's first miss, inside the bound's first pause.
    Returns (the answer, the misses, the wager's state, the seconds the
    deletion took, everything printed)."""
    _arm(env)
    capsys.readouterr()
    lid, (p,) = await env.lobby("team", 1)
    b, bet = await _open_wager(env, lid, p)
    side = await _hold(env, kind, b)
    real = main._deletion_lock_party_row
    misses, later = [], []

    async def let_go():
        await asyncio.sleep(0.1)
        await side.execute("ROLLBACK")

    async def spy(db, player_id, *, no_wait=False):
        try:
            await real(db, player_id, no_wait=no_wait)
        except main._DeletionRowHeld as ex:
            misses.append(ex.what)
            if len(misses) == 1:
                later.append(asyncio.ensure_future(let_go()))
            raise
    env.mp.setattr(main, "_deletion_lock_party_row", spy)
    t0 = time.monotonic()
    a = await asyncio.wait_for(_delete(env, p), 30)
    took = time.monotonic() - t0
    for t in later:
        await t
    return a, misses, await _wager_state(env, b, bet), took, capsys.readouterr().out


@pytest.mark.parametrize("kind,what", [("row", "bet party row"), ("key", "bet party's identity key")])
def test_r1h_point2_a_party_held_for_a_moment_costs_one_attempt_and_the_next_answers_200(
        monkeypatch, capsys, kind, what):
    """What a refusal costs (#430): ordinary traffic holding a party's row or
    key for a moment ends one attempt; the next, after the 0.25 s pause,
    answers 200 well inside the bound, and the log line names what was held
    with the attempt's number (#438: the signal its rate is read from)."""
    async def body(env):
        a, misses, state, took, out = await _held_for_a_moment(env, capsys, kind)
        assert a.status == 200 and a["status"] == "anonymized", a
        assert misses == [what], misses
        assert state == ("refunded", 90), state
        assert ("deletion attempt 1 met a held %s;" % what) in out, out[-2000:]
        assert "next attempt after 0.25s" in out, out[-2000:]
        assert took < main._DELETION_BUDGET_S, took
    case(monkeypatch, body, prefix="mdpl")


def test_r1h_point3_an_absent_party_row_leaves_the_refund_as_it_was(monkeypatch):
    """POINT 3, absent: no players row of that id. In the no-wait mode (as the
    deletion's bet path calls it) the guard's two reads find nothing, raise
    nothing, and the refund's own statement runs and refuses
    (StakeRefundRefused), exactly as the same call does without it; nothing
    is written."""
    async def body(env):
        ghost = uuid.uuid4()
        for inside in (True, False):
            async def go(db):
                async def refund():
                    await main._return_stake_exactly(db, ghost, 10, reason="mdpl_point3",
                                                     reference_id="mdpl-point3", no_wait=inside)
                try:
                    await refund()
                except main.StakeRefundRefused:
                    await db.rollback()
                    return {"refused": True}
                await db.commit()
                return {"refused": False}
            ans = await asyncio.wait_for(env.call(go), 30)
            assert ans.status == 200 and ans["refused"] is True, (inside, ans)
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM gold_transactions WHERE reference_id = 'mdpl-point3'") == 0
    case(monkeypatch, body, prefix="mdpl")


@pytest.mark.parametrize("kind,what", [("row", "bet party row"), ("key", "bet party's identity key")])
def test_r1h_point3_a_held_party_row_or_key_is_the_signal_and_moves_nothing(monkeypatch, kind, what):
    """POINT 3, held: another transaction holds the party's players row, or
    its identity key. In the no-wait mode: the signal, at once, and the
    party's gold is as it was."""
    async def body(env):
        (b,) = await env.players(1)
        await env.conn.execute("UPDATE players SET gold_earned = 200, gold_spent = 100 WHERE id = $1", b.id)
        side = await _hold(env, kind, b)

        async def go(db):
            try:
                await main._return_stake_exactly(
                    db, b.id, 10, reason="mdpl_point3", reference_id="mdpl-point3", no_wait=True)
            except main._DeletionRowHeld as ex:
                await db.rollback()
                return {"held": ex.what}
            await db.commit()
            return {"held": None}
        try:
            ans = await asyncio.wait_for(env.call(go), 30)
        finally:
            await side.execute("ROLLBACK")
        assert ans.status == 200 and ans["held"] == what, ans
        assert await env.conn.fetchval("SELECT gold_spent FROM players WHERE id = $1", b.id) == 100
    case(monkeypatch, body, prefix="mdpl")


def test_r1h_point3_a_row_and_key_the_attempt_holds_itself_pass(monkeypatch):
    """The attempt's own lock on the row (as on the deleted player's own row)
    is not skipped, and its own identity key is granted again: the refund
    applies."""
    async def body(env):
        (b,) = await env.players(1)
        await env.conn.execute("UPDATE players SET gold_earned = 200, gold_spent = 100 WHERE id = $1", b.id)

        async def go(db):
            await db.execute(main.text("SELECT id FROM players WHERE id = :pid FOR NO KEY UPDATE"), {"pid": b.id})
            await db.execute(main.text(main._IDENTITY_KEY_SQL), {"sid": b.sid})
            await main._return_stake_exactly(
                db, b.id, 10, reason="mdpl_point3", reference_id="mdpl-point3", no_wait=True)
            await db.commit()
            return {"ok": True}
        ans = await asyncio.wait_for(env.call(go), 30)
        assert ans.status == 200, ans
        assert await env.conn.fetchval("SELECT gold_spent FROM players WHERE id = $1", b.id) == 90
    case(monkeypatch, body, prefix="mdpl")


def test_r1h_the_ffa_bet_guard_tells_a_held_bet_from_a_settled_one(monkeypatch):
    """In the no-wait mode: an unsettled bet another transaction holds is
    the signal; a settled bet is passed over (no raise; its claim would find
    it settled); a free unsettled bet is taken, so a NOWAIT probe from
    another session fails while the caller's transaction is open."""
    async def body(env):
        p, q, b1, b2, b3 = await env.players(5)
        lid = await env.create("ffa", p)
        bets = []
        for b in (b1, b2, b3):
            bets.append(await env.conn.fetchval(
                "INSERT INTO ffa_bets (lobby_id, game_number, player_id, bet_on_player_id, amount,"
                " odds_multiplier) VALUES ($1, 1, $2, $3, 10, 2.0) RETURNING id", lid, b.id, q.id))
        held, settled, free = bets
        await env.conn.execute("UPDATE ffa_bets SET settled_at = NOW(), settlement_kind = 'refunded',"
                               " payout = amount WHERE id = $1", settled)
        side = await env.side()
        await side.execute("BEGIN")
        assert await side.fetchval("SELECT id FROM ffa_bets WHERE id = $1 FOR NO KEY UPDATE", held) == held

        async def go(db):
            out = {}
            try:
                await main._deletion_lock_ffa_bet(db, held, no_wait=True)
                out["held"] = None
            except main._DeletionRowHeld as ex:
                out["held"] = ex.what
            await db.rollback()
            await main._deletion_lock_ffa_bet(db, settled, no_wait=True)
            await main._deletion_lock_ffa_bet(db, free, no_wait=True)
            probe = await env.side()
            await probe.execute("BEGIN")
            try:
                await probe.fetchval("SELECT id FROM ffa_bets WHERE id = $1 FOR NO KEY UPDATE NOWAIT", free)
                out["free_taken"] = False
            except asyncpg.exceptions.LockNotAvailableError:
                out["free_taken"] = True
            finally:
                await probe.execute("ROLLBACK")
            await db.rollback()
            return out
        try:
            ans = await asyncio.wait_for(env.call(go), 30)
        finally:
            await side.execute("ROLLBACK")
        assert ans.status == 200 and ans.body == {"held": "FFA bet row", "free_taken": True}, ans
    case(monkeypatch, body, prefix="mdpl")


# -- (a), the option, point 4: controls ---------------------------------------------------------

def test_r1h_a_control_with_the_step_4_lock_waiting_the_circle_closes(monkeypatch, capsys):
    """(a)'s scene with the step-4 lock taken with a wait (8d920c07's form):
    the deletion waits for L, which H holds while it waits for P's row."""
    async def body(env):
        a, h, out = await _step4_scene(env, capsys, blocking=True)
        assert _circle_closed(a, h, out), ("no circle", _name(a), _name(h), out[-1500:])
    case(monkeypatch, body, prefix="mdpl")


def test_r1h_a_mirror_the_holder_gone_before_the_attempt_answers_200_at_once(monkeypatch, capsys):
    """(a)'s mirror: H took L and let it go before the deletion came to it;
    the first attempt takes L and answers 200, with no held row and no
    second attempt."""
    async def body(env):
        a, h, out = await _step4_scene(env, capsys, gone_before=True)
        assert a.status == 200 and a["status"] == "anonymized", a
        assert h is None, h
        assert "met a held" not in out and "deletion attempt 1 ended" not in out, out[-2000:]
    case(monkeypatch, body, prefix="mdpl")


def test_r1h_option_control_with_waits_of_the_time_left_postgresql_ends_the_peer(monkeypatch, capsys):
    """The option's scene with the cap off (each wait armed with the time
    left, as at 8d920c07): the deletion is still waiting at H's deadlock
    check, and PostgreSQL ends H."""
    async def body(env):
        a, h, out = await _cap_scene(env, capsys, cap_off=True)
        assert _circle_closed(a, h, out), ("no circle", _name(a), _name(h), out[-1500:])
        assert _deadlock(h), ("the peer was not the one ended", _name(a), _name(h))
    case(monkeypatch, body, prefix="mdpl")


def test_r1h_upgrade_control_with_waits_of_the_time_left_the_deletion_is_ended(monkeypatch, capsys):
    """The UPGRADE scene with the cap off (each wait armed with the time
    left, as at 8d920c07): the deletion still waits at its tombstone when its
    own deadlock check runs, and PostgreSQL ends it."""
    async def body(env):
        a, h, out = await _upgrade_scene(env, capsys, cap_off=True)
        assert _circle_closed(a, h, out), ("no circle", _name(a), _name(h), out[-1500:])
        assert _deadlock(a), ("the deletion was not the one ended", _name(a), _name(h))
    case(monkeypatch, body, prefix="mdpl")


def test_r1h_phase_b_control_with_waits_of_the_time_left_the_deletion_is_ended(monkeypatch, capsys):
    """The phase-B scene with the cap off: the deletion still waits for H's
    revision row when its own deadlock check runs, and PostgreSQL ends it."""
    async def body(env):
        a, h, out = await _phase_b_scene(env, capsys, cap_off=True)
        assert _circle_closed(a, h, out), ("no circle", _name(a), _name(h), out[-1500:])
        assert _deadlock(a), ("the deletion was not the one ended", _name(a), _name(h))
    case(monkeypatch, body, prefix="mdpl")


def test_r1h_point4_control_a_two_argument_key_does_not_hold_off_the_cancel(monkeypatch, capsys):
    """Point 4's mutant: the guard's key in a two-argument form, a different
    key from the one B's cancel takes. The cancel is not held off at its
    first statement: it claims the wager and waits for B's players row, and
    the circle closes as with no key at all."""
    async def body(env):
        a, c, st, spent, out = await _cancel_scene(
            env, capsys, key_sql="SELECT pg_try_advisory_xact_lock(0, hashtext(CAST(:sid AS text)))")
        assert _circle_closed(a, c, out), ("no circle", _name(a), _name(c), out[-1500:])
    case(monkeypatch, body, prefix="mdpl")


# -- the hold-time figure, lesson 689's form ------------------------------------------------------

async def _staggered_holders(env, *, cap):
    """Three holders on the three things the deletion of P waits for in turn
    -- P's identity key, the pool snapshot key, P's players row (its
    pc_shards write) -- released 2.5 s apart. Each single wait is under the
    lock_timeout 8d920c07 armed once per attempt (the time left at its
    start, 6 s); their sum, 7.5 s, passes the 6 s budget. cap: the wait cap
    for the run (None: as built; 60.0: off, so every wait is armed with the
    time left). Returns (P, the answer, the seconds from the call to the
    answer, P's row)."""
    _arm(env)
    (p,) = await env.players(1)
    env.mp.setattr(main, "_DELETION_BUDGET_S", 6.0)
    env.mp.setattr(main, "_DELETION_ATTEMPT_MIN_S", 1.0)
    if cap is not None:
        env.mp.setattr(main, "_DELETION_WAIT_CAP_S", cap, raising=False)
    s1, s2, s3 = await env.side(), await env.side(), await env.side()
    await s1.execute("SELECT pg_advisory_lock(hashtext($1))", p.sid)
    await s2.execute("SELECT pg_advisory_lock(hashtext('pc_snapshot'))")
    await s3.execute("BEGIN")
    assert await s3.fetchval("SELECT id FROM players WHERE id = $1 FOR NO KEY UPDATE", p.id) == p.id

    async def let_go():
        await asyncio.sleep(2.5)
        await s1.execute("SELECT pg_advisory_unlock(hashtext($1))", p.sid)
        await asyncio.sleep(2.5)
        await s2.execute("SELECT pg_advisory_unlock(hashtext('pc_snapshot'))")
        await asyncio.sleep(2.5)
        await s3.execute("ROLLBACK")

    rel = asyncio.create_task(let_go())
    t0 = time.monotonic()
    a = await _delete(env, p)
    spent = time.monotonic() - t0
    await rel
    row = await env.conn.fetchrow("SELECT steam_id, deleted_at FROM players WHERE id = $1", p.id)
    return p, a, spent, row


@pytest.mark.parametrize("cap", [None, 60.0], ids=["cap_as_built", "cap_off"])
def test_r1h_figure_staggered_holders_end_the_attempt_by_its_deadline(monkeypatch, cap):
    """Lesson 689's form. With the time left armed before every statement the
    third wait ends at the deadline (cap off), or every wait ends at the cap
    (as built): 503 by the deadline, nothing written. At 8d920c07 this fails
    at "spent": the three waits add up to 7.5 s and the attempt holds what
    it took until its pre-commit check. Its control is R6a's: one holder past
    the budget, where the time-left arming fires."""
    async def body(env):
        p, a, spent, row = await _staggered_holders(env, cap=cap)
        assert spent < main._DELETION_BUDGET_S + 0.5, ("spent", spent)
        assert (a.status, a.body) == (503, main._DELETION_REFUSAL), a
        assert row["steam_id"] == p.sid and row["deleted_at"] is None, dict(row)
    case(monkeypatch, body, prefix="mdpl")


# -- R6c: the arming on the attempt's real connection (r2 HIGH 1) --------------------------------

def _sent_label(statement):
    """A statement as R6c compares it: "ARM" for the arming, the verb and its
    table for a write, the first word for anything else."""
    if statement.startswith("SELECT set_config('lock_timeout'"):
        return "ARM"
    words = statement.split()
    if words[0] == "UPDATE":
        return "UPDATE " + words[1]
    if words[0] == "INSERT":
        return "INSERT " + words[2]
    return words[0]


def _r6c_pairs(sent):
    """Each statement sent but an arming, in order: (its label, armed -- the
    arming came right before it --, its execute style, that arming's
    (lock_timeout, statement_timeout in ms) or None)."""
    out, arming = [], None
    for label, params, style in sent:
        if label == "ARM":
            assert arming is None, "two armings with no statement between them: %r" % (sent,)
            lt, st = list(params.values()) if isinstance(params, dict) else list(params)
            arming = (lt, int(st[:-2]))
            continue
        out.append((label, arming is not None, style, arming))
        arming = None
    assert arming is None, "an arming with no statement after it: %r" % (sent,)
    return out


def _r6c_shape(pairs):
    """(label, armed) for each statement, the first flush's two sorted: the
    unit of work orders the two tables' statements its own way, and R6c
    claims nothing about that order."""
    shape = [(label, armed) for label, armed, _s, _a in pairs]
    return shape[:1] + sorted(shape[1:3]) + shape[3:]


async def _r6c_scene(env):
    """An attempt's session, armed for 60 s, on a real AsyncSession over
    asyncpg: an ORM read; a flush of a row of players and one of
    gold_transactions (two statements); an autoflush ahead of an ORM read; a
    savepoint around a statement; an executemany of two runs; the commit,
    whose flush inserts two rows of gold_transactions in one statement
    (insertmanyvalues); a statement on the connection the session checks out
    after the commit; then, after the undo, one more statement on that same
    connection. Returns _r6c_pairs of what was sent, in the order sent
    (after_cursor_execute, and the engine's commit event for the COMMIT),
    after checking that the writes committed."""
    from sqlalchemy import event as sa_event
    p, q = await env.players(2)
    sent = []

    def rec(conn, cursor, statement, parameters, context, executemany):
        sent.append((_sent_label(statement), parameters,
                     getattr(getattr(context, "execute_style", None), "name", None)))

    def rec_commit(conn):
        sent.append(("COMMIT", None, None))
    sa_event.listen(env.engine.sync_engine, "after_cursor_execute", rec)
    sa_event.listen(env.engine.sync_engine, "commit", rec_commit)
    try:
        async with env.sm() as db:
            undo = main._deletion_arm_every_statement(db, main._deletion_clock() + 60.0)
            try:
                one = (await db.execute(
                    main.select(main.Player).where(main.Player.id == p.id))).scalar_one()
                one.display_name = "mdpl r6c one"
                db.add(main.GoldTransaction(player_id=q.id, amount=1, reason="mdpl_r6c", reference_id="1"))
                await db.flush()
                one.display_name = "mdpl r6c two"
                (await db.execute(main.select(main.Player).where(main.Player.id == q.id))).scalar_one()
                async with db.begin_nested():
                    await db.execute(main.text("SELECT 1"))
                await db.execute(main.text("UPDATE players SET display_name = display_name WHERE id = :i"),
                                 [{"i": p.id}, {"i": q.id}])
                db.add(main.GoldTransaction(player_id=p.id, amount=1, reason="mdpl_r6c", reference_id="2"))
                db.add(main.GoldTransaction(player_id=q.id, amount=1, reason="mdpl_r6c", reference_id="3"))
                await db.commit()
                await db.execute(main.text("SELECT 3"))
            finally:
                undo()
            await db.execute(main.text("SELECT 4"))
            await db.rollback()
    finally:
        sa_event.remove(env.engine.sync_engine, "after_cursor_execute", rec)
        sa_event.remove(env.engine.sync_engine, "commit", rec_commit)
    row = await env.conn.fetchrow("SELECT display_name FROM players WHERE id = $1", p.id)
    assert row["display_name"] == "mdpl r6c two", dict(row)
    assert await env.conn.fetchval("SELECT count(*) FROM gold_transactions WHERE reason = 'mdpl_r6c'") == 3
    return _r6c_pairs(sent)


# What the scene sends when every statement is armed: the read; the flush's two
# (sorted, _r6c_shape); the autoflush and its read; the savepoint, unarmed
# around its armed statement; the executemany; the commit's flush and the
# COMMIT; the statement on the connection checked out after the commit; the
# statement after the undo, unarmed.
_R6C_ARMED = [("SELECT", True),
              ("INSERT gold_transactions", True), ("UPDATE players", True),
              ("UPDATE players", True), ("SELECT", True),
              ("SAVEPOINT", False), ("SELECT", True), ("RELEASE", False),
              ("UPDATE players", True),
              ("INSERT gold_transactions", True), ("COMMIT", True),
              ("SELECT", True),
              ("SELECT", False)]


def test_r6c_every_statement_of_the_attempt_s_connection_is_armed_first(monkeypatch):
    """r2 HIGH 1 through SQLAlchemy's own events (the bound tests' fakes stand
    in for them): each statement is armed right before it is sent -- each of
    the flush's two, the autoflush and its read, the executemany, the
    commit's insert of two rows -- with lock_timeout the cap and
    statement_timeout the time left; the executemany's two runs share the
    time left; the insert of two rows is one statement and is not shared;
    the savepoint's own two statements are not armed; the COMMIT is armed
    after the commit's flush; the connection checked out after the commit is
    armed too; after the undo that connection sends unarmed."""
    async def body(env):
        pairs = await _r6c_scene(env)
        assert _r6c_shape(pairs) == _R6C_ARMED, pairs
        cap = "%dms" % int(main._DELETION_WAIT_CAP_S * 1000)
        armed = [(label, style, arming) for label, is_armed, style, arming in pairs if is_armed]
        assert all(lt == cap for _l, _s, (lt, _st) in armed), armed
        many = [st for label, style, (_lt, st) in armed if style == "EXECUTEMANY"]
        batch = [st for label, style, (_lt, st) in armed if style == "INSERTMANYVALUES"]
        whole = [st for label, style, (_lt, st) in armed if style not in ("EXECUTEMANY", "INSERTMANYVALUES")]
        assert len(many) == 1 and 25000 < many[0] <= 30000, armed
        assert len(batch) == 1 and 50000 < batch[0] <= 60000, armed
        assert whole == sorted(whole, reverse=True) and 50000 < whole[-1] <= 60000, armed
    case(monkeypatch, body, prefix="mdpl")


def test_r6c_control_without_the_listener_only_the_commit_is_armed(monkeypatch):
    """The control, mutant B27 run as a test: _deletion_listen attaches
    nothing (and the undo has nothing to take off). The scene then sends
    every statement unarmed but the COMMIT, the one the commit arms itself,
    so the armed test above fails on it."""
    async def body(env):
        env.mp.setattr(main, "_deletion_listen", lambda conn, fn: None)
        env.mp.setattr(main, "_deletion_unlisten", lambda conn, fn: None)
        shape = _r6c_shape(await _r6c_scene(env))
        assert shape == [(label, label == "COMMIT") for label, _armed in _R6C_ARMED], shape
        assert shape != _R6C_ARMED
    case(monkeypatch, body, prefix="mdpl")


# -- point 6: a call outside a deletion issues the statements it issued before -------------------

_EVERY_STATEMENT = re.compile(r"\A")
# Measured at 8d920c07 (B's tree) by this file's capture with MDPL_CAPTURE_WRITE set: per call,
# each statement it sent (whitespace collapsed, savepoints included) as its first 64 characters
# and the first 12 hex digits of its md5.
_OUTSIDE_STATEMENTS_8D920C07 = [
    ["ffa_refund_pass", [
        ["SAVEPOINT sa_savepoint_1", "7b295c9ab4d8"],
        ["SELECT DISTINCT game_number FROM ffa_bets WHERE lobby_id = $1 AN", "47ab78fe8cc2"],
        ["SELECT winner_id, score_target_frozen, score_target_played FROM ", "050980280a7f"],
        ["RELEASE SAVEPOINT sa_savepoint_1", "04cba0342a98"],
        ["SAVEPOINT sa_savepoint_2", "021c976aa7bd"],
        ["SELECT id, player_id, amount FROM ffa_bets WHERE lobby_id = $1 A", "3c15f8b614ce"],
        ["SAVEPOINT sa_savepoint_3", "527906cd5237"],
        ["SELECT id::text FROM players WHERE steam_id = ANY(CAST($1 AS tex", "53fa53e24196"],
        ["RELEASE SAVEPOINT sa_savepoint_3", "4cf8dfd57094"],
        ["UPDATE ffa_bets SET payout = amount, settled_at = NOW(), settlem", "aea377f6539c"],
        ["UPDATE players SET gold_spent = COALESCE(gold_spent, 0) - CAST($", "c88cc6868dd3"],
        ["INSERT INTO gold_transactions (player_id, amount, reason, refere", "f909f3314cdd"],
        ["RELEASE SAVEPOINT sa_savepoint_2", "ecdae5907008"],
    ]],
    ["ffa_settle", [
        ["SELECT id, player_id, bet_on_player_id, amount, odds_multiplier ", "eed3b5646136"],
        ["SELECT 1 FROM players WHERE id = $1 FOR NO KEY UPDATE", "b255d297c589"],
        ["UPDATE ffa_bets SET payout = $1, settled_at = NOW(), settlement_", "f04b491bb385"],
        ["UPDATE players SET gold_earned = COALESCE(gold_earned,0) + $1 WH", "f1925db06215"],
        ["INSERT INTO gold_transactions (player_id, amount, reason, refere", "f909f3314cdd"],
    ]],
    ["team_lobby_refund", [
        ["SAVEPOINT sa_savepoint_1", "7b295c9ab4d8"],
        ["SELECT id, player_id FROM lobby_bets WHERE mode = $1 AND lobby_i", "162c5b7135f9"],
        ["UPDATE lobby_bets SET status = 'refund_pending', resolved_at = N", "edc54e973ad7"],
        ["SELECT player_id FROM lobby_bets WHERE id = $1 AND status = 'ref", "c8b818fa5dfd"],
        ["UPDATE lobby_bets SET status = 'refunded', resolved_at = NOW() W", "cb8cef8bacbc"],
        ["UPDATE players SET gold_spent = COALESCE(gold_spent, 0) - CAST($", "c88cc6868dd3"],
        ["INSERT INTO gold_transactions (player_id, amount, reason, refere", "f909f3314cdd"],
        ["RELEASE SAVEPOINT sa_savepoint_1", "04cba0342a98"],
    ]],
]


def _digest(sql):
    s = " ".join(sql.split())
    return [s[:64], hashlib.md5(s.encode("utf-8")).hexdigest()[:12]]


async def _outside_statements(env):
    """The SQL three bet helpers send when called outside a deletion, each
    with one open wager: the FFA refund pass (_reconcile_ffa_lobby_bets on a
    closed lobby whose game has no result, through _refund_ffa_lobby_bets),
    an FFA settlement (_settle_ffa_bets_for_game on a game Q won), and a team
    lobby's refund (_refund_lobby_bets). Returns ([[call, [digest, ...]], ...],
    every statement in full)."""
    _arm(env)
    # _service_player_uuids keeps its lookup for the process. The capture at
    # 8d920c07 began with it unfilled or expired, so the first call carries the
    # lookup (a savepoint, SELECT id::text FROM players, its release) and the
    # later ones read the filled cache. Emptied here, whatever an earlier test
    # of this process left, so the capture does not depend on the order.
    env.mp.setattr(main, "_service_player_uuid_cache", None)
    h1, h2, q, r = await env.players(4)
    await env.conn.execute("UPDATE players SET gold_earned = 200, gold_spent = 100 WHERE id = $1", r.id)
    out, raw = [], []
    for call, host in (("ffa_refund_pass", h1), ("ffa_settle", h2)):
        lid = await env.create("ffa", host)
        await env.conn.execute(
            "UPDATE ffa_lobbies SET status = 'completed', completed_at = NOW() WHERE id = $1", lid)
        await env.conn.execute(
            "INSERT INTO ffa_bets (lobby_id, game_number, player_id, bet_on_player_id, amount, odds_multiplier)"
            " VALUES ($1, 1, $2, $3, 10, 2.0)", lid, r.id, q.id)

        async def go(db, call=call, lid=lid):
            if call == "ffa_refund_pass":
                await main._reconcile_ffa_lobby_bets(db, lid, "mdpl capture")
            else:
                await main._settle_ffa_bets_for_game(db, lid, 1, q.id)
            await db.commit()
            return {"ok": True}
        with env.rewriting(_EVERY_STATEMENT, "") as hits:
            ans = await env.call(go)
        assert ans.status == 200, ans
        out.append([call, [_digest(s) for s in hits]])
        raw.extend(" ".join(s.split()) for s in hits)
    lid, (p,) = await env.lobby("team", 1)
    await _open_wager(env, lid, p)

    async def refund(db):
        await main._refund_lobby_bets(db, "team", lid, "mdpl capture")
        await db.commit()
        return {"ok": True}
    with env.rewriting(_EVERY_STATEMENT, "") as hits:
        ans = await env.call(refund)
    assert ans.status == 200, ans
    out.append(["team_lobby_refund", [_digest(s) for s in hits]])
    raw.extend(" ".join(s.split()) for s in hits)
    return out, raw


def test_r1h_point6_a_call_outside_a_deletion_issues_the_statements_it_issued_before(monkeypatch):
    """Point 6: the no-wait mode is off by default, so the janitor's and the
    reports' calls of the bet helpers send the SQL they sent at 8d920c07,
    with only 3e56313f's named delta: no guard statement, nothing else moved."""
    async def body(env):
        got, _raw = await _outside_statements(env)
        path = os.environ.get("MDPL_CAPTURE_WRITE")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(got, fh, indent=1)
            return
        assert _OUTSIDE_STATEMENTS_8D920C07 is not None, "not measured at 8d920c07 yet"
        assert got == _outside_expected(), got
    case(monkeypatch, body, prefix="mdpl")


def test_r1h_point6_control_the_guards_on_for_every_caller_add_their_statements(monkeypatch):
    """Point 6's mutant: both guards in the no-wait mode whatever their
    caller says. The same calls then send the guards' statements too."""
    async def body(env):
        party, bet = main._deletion_lock_party_row, main._deletion_lock_ffa_bet

        async def party_on(db, player_id, *, no_wait=False):
            await party(db, player_id, no_wait=True)

        async def bet_on(db, bet_id, *, no_wait=False):
            await bet(db, bet_id, no_wait=True)
        env.mp.setattr(main, "_deletion_lock_party_row", party_on)
        env.mp.setattr(main, "_deletion_lock_ffa_bet", bet_on)
        got, raw = await _outside_statements(env)
        assert _OUTSIDE_STATEMENTS_8D920C07 is not None, "not measured at 8d920c07 yet"
        assert got != _outside_expected()
        assert any("SKIP LOCKED" in s and "FROM players" in s for s in raw), raw
        assert any("SKIP LOCKED" in s and "FROM ffa_bets" in s for s in raw), raw
        assert any("pg_try_advisory_xact_lock" in s for s in raw), raw
    case(monkeypatch, body, prefix="mdpl")


# THE ONE NAMED DELTA to _OUTSIDE_STATEMENTS_8D920C07 (above), which stays exactly as measured at 8d920c07.
# 3e56313f (19 Nov, Bans part 2a, BAN-R21) gave _refund_lobby_bets's open-wager SELECT its bettor filter,
# "AND (CAST(:b AS uuid) IS NULL OR player_id = CAST(:b AS uuid))", so team_lobby_refund's statement 2 has a
# new digest. Keyed (call, index): (the pin's item, the item now).
_OUTSIDE_DELTA_3E56313F = {
    ("team_lobby_refund", 1): (["SELECT id, player_id FROM lobby_bets WHERE mode = $1 AND lobby_i", "162c5b7135f9"],
                               ["SELECT id, player_id FROM lobby_bets WHERE mode = $1 AND lobby_i", "720a23864c80"]),
}


def _outside_expected():
    """The measured pin with the named delta applied. Each delta's old item must be the pin's item at its place,
    so the delta names exactly what moved, and every other statement is still the one measured at 8d920c07."""
    want = [[call, [list(item) for item in items]] for call, items in _OUTSIDE_STATEMENTS_8D920C07]
    for (call, i), (old, new) in sorted(_OUTSIDE_DELTA_3E56313F.items()):
        rows = [r for r in want if r[0] == call]
        assert len(rows) == 1 and rows[0][1][i] == old, ("the delta's old item is not the pin's", call, i, old)
        rows[0][1][i] = list(new)
    return want
