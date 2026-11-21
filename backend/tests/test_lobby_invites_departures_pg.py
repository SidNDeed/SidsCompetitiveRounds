"""Lobby invites on PostgreSQL (migration 416's change): departures, through
inv_pg (one cf_pg case schema per case, the real handlers in main.py).

Each departure path in _PATHS takes the lobby row's lock before it removes
the seat, then ends the departed sender's pending invites in the same
transaction, after the queue-row delete. (The removals that end no invite,
note 13 (g) and (m), are in test_lobby_invites_sweep_pg.py.) Each path is
run with a second session holding the lobby row FOR NO KEY UPDATE (which
conflicts with every row lock a path takes, and with no foreign-key check):
while it is held the departure waits, the member is seated and the invite
pending; once it is released the member is gone and the invite is void with
sender_left. Every test has a mutant it must fail (a statement rewrite whose
hits are asserted, or a monkeypatch of a main.py function) and a control.

Also here: an accept after a departure is refused invite_void by the
accept's own re-check of the sender's seat; a kick ends the invites to the
kicked player too (invitee_kicked); a ban takes its lobby locks in the order
FFA, 2v2, 1v2, FOR NO KEY UPDATE, and holds them through _pc_lease_drain.
"""

import ast
import asyncio
import hashlib
import hmac
import inspect
import os
import re
import sys
import types
import uuid

import asyncpg
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

from fastapi import HTTPException  # noqa: E402

from inv_pg import LOBBY_TABLE, MODES, QUEUE_TABLE, Req, case, key, mail_discord, waiting_on  # noqa: E402

import main  # noqa: E402

BOUND = 30                      # seconds: no wait in this file is longer
VOID_LEFT = ("void", "sender_left", True)
VOID_KICKED = ("void", "invitee_kicked", True)
PENDING = ("pending", None, False)
SECRET = "inv-departure-secret"

# Every statement, unchanged: a rewrite that matches once at the start of
# each statement, so its hits list is the transaction's statement log.
_EVERY = re.compile(r"\A")

# A path's lobby row lock: `FROM <lobby table> WHERE id = <bind> FOR [NO KEY]
# UPDATE`, as the group helpers, the join cores, account deletion and the ban
# send it (never a SKIP LOCKED re-read). The mutant rewrites it to a plain read.
_LOCK_RX = {m: re.compile(r"(FROM %s WHERE id = \S+) FOR (?:NO KEY )?UPDATE(?! SKIP)" % LOBBY_TABLE[m])
            for m in MODES}
_BAN_LOCK_RX = re.compile(r"(SELECT 1 FROM (?:ffa|team|ovt)_lobbies WHERE id = \S+) FOR NO KEY UPDATE")


# -- helpers --------------------------------------------------------------------

def _end(row):
    return (row["state"], row["end_reason"], row["ended_at"] is not None)


async def _end_nothing(db, mode, lobby_id, player_ids):
    """The mutant: a void step that ends no invite."""
    return []


async def _drain_now(db, pid):
    """_pc_lease_drain without its wait (up to 65 s): no line is in flight."""
    return 0.0


async def _admin(env):
    a = await env.player()
    await env.conn.execute("INSERT INTO admin_users (steam_id, granted_at) VALUES ($1, NOW())"
                           " ON CONFLICT DO NOTHING", a.sid)
    return a


async def _ban(env, admin, p):
    """The ban's write core, committed as admin_ban commits it."""
    async def go(db):
        out = await main._apply_ban_core(db, admin_steam_id=admin.sid, target_steam_id=p.sid,
                                         reason="test")
        await db.commit()
        return out
    return await env.call(go)


async def _delete(env, p):
    """Account deletion for `p`, signed with the case's secret."""
    env.mp.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    env.mp.delenv("STEAM_WEB_API_KEY", raising=False)
    sig = hmac.new(SECRET.encode(), ("delete:%s" % p.sid).encode(), hashlib.sha256).hexdigest()
    return await env.call(lambda db: main.delete_player_data(p.sid, Req(p.sid), sig=sig, _slot=None,
                                                             db=db))


async def _nowait(conn, sql, *args):
    """True when `conn` takes the lock in `sql` (NOWAIT) at once; released at once."""
    tr = conn.transaction()
    await tr.start()
    try:
        await conn.fetchval(sql, *args)
        return True
    except asyncpg.exceptions.LockNotAvailableError:
        return False
    finally:
        await tr.rollback()


async def _row_lock(conn, mode, lid):
    """How another session holds a lobby row: 'free', 'no_key' (FOR NO KEY
    UPDATE: a key share is still granted) or 'update' (FOR UPDATE: not even
    that). Read by NOWAIT probes that are rolled back at once."""
    sql = "SELECT 1 FROM %s WHERE id = $1 FOR %%s NOWAIT" % LOBBY_TABLE[mode]
    if await _nowait(conn, sql % "NO KEY UPDATE", lid):
        return "free"
    if await _nowait(conn, sql % "KEY SHARE", lid):
        return "no_key"
    return "update"


def _source_mutant(fn, *swaps):
    """`fn` rebuilt from its source with each (old, new) applied in turn, in
    main's namespace. Each `old` must occur exactly once when it is applied."""
    src = inspect.getsource(fn)
    for old, new in swaps:
        assert src.count(old) == 1, ("the mutant's anchor is not unique in the source", old)
        src = src.replace(old, new)
    ns = {}
    exec(compile(src, inspect.getsourcefile(fn) or "<mutant>", "exec"), vars(main), ns)
    return ns[fn.__name__]


def _first(log, pred, before=None):
    for i, s in enumerate(log if before is None else log[:before]):
        if pred(s):
            return i
    return None


def _order(log, mode):
    """(lobby lock, the departed seat's queue-row delete, the sender_left void)
    as indexes in the statement log: the lock is the first lobby lock, the
    void the departure step's own statement, the delete the last delete of
    the mode's queue rows before it."""
    void = _first(log, lambda s: "UPDATE lobby_invites" in s and "'sender_left'" in s)
    lock = _first(log, lambda s: _LOCK_RX[mode].search(s) is not None)
    dels = [i for i, s in enumerate(log[:void] if void is not None else log)
            if ("DELETE FROM %s" % QUEUE_TABLE[mode]) in s]
    return lock, (dels[-1] if dels else None), void


async def _under_lock(env, mode, lid, who, iids, depart):
    """`depart()` run while a side session holds the lobby row FOR NO KEY
    UPDATE. What it observes: whether the departure waited on that session;
    whether it finished while the lock was held; `who`'s seat and the
    invites' states while held; and after the release, the departure's
    answer, `who`'s seat and each invite's end. Every wait is bounded."""
    side = await env.side()
    await side.execute("BEGIN")
    await side.execute("SELECT 1 FROM %s WHERE id = $1 FOR NO KEY UPDATE" % LOBBY_TABLE[mode], lid)
    task = asyncio.ensure_future(depart())
    obs = {}
    try:
        done, _rest = await asyncio.wait({task}, timeout=1.0)
        waiters = [] if done else await waiting_on(env, side.get_server_pid())
        obs["waited"] = bool(waiters) and not task.done()
        if not obs["waited"] and not task.done():
            await asyncio.wait({task}, timeout=BOUND)
        obs["finished_while_held"] = task.done()
        obs["seated_while_held"] = who.id in await env.members(mode, lid)
        obs["while_held"] = [(await env.row(i))["state"] for i in iids]
    finally:
        await side.execute("ROLLBACK")
        ans = await asyncio.wait_for(task, BOUND)
    obs["answer"] = ans
    obs["seated_after"] = who.id in await env.members(mode, lid)
    obs["after"] = [_end(await env.row(i)) for i in iids]
    return obs


# -- each departure path takes the lobby lock, removes, then voids ---------------
#
# One case per path and mode. The member m (not the host, so no path writes
# the lobby row to promote a host or disband) sends one invite, then departs:
#   leave        _lobby_leave_impl (2v2, 1v2), ffa_queue_leave (FFA)
#   queue_leave  team_queue_leave, ovt_queue_leave
#   state        _lobby_state_impl (the seat's lease is gone, so the lobby
#                state's renewal fails and the seat ends)
#   join_prune   _lobby_join_core, _ffa_lobby_join_core (m is stale; a join prunes it)
#   delete       delete_player_data
#   ban          _apply_ban_core
# The kick has its own test below. The three queue polls' same lease-expiry
# branch (team_queue_poll, ovt_queue_poll, and FFA's body
# _ffa_queue_poll_inner) ends no invite, note 13 (m), and is tested in the
# sweep suite.

_PATHS = (
    ("leave", "team"), ("leave", "ovt"), ("leave", "ffa"),
    ("queue_leave", "team"), ("queue_leave", "ovt"),
    ("state", "team"), ("state", "ovt"),
    ("join_prune", "team"), ("join_prune", "ovt"), ("join_prune", "ffa"),
    ("delete", "team"), ("delete", "ovt"), ("delete", "ffa"),
    ("ban", "team"), ("ban", "ovt"), ("ban", "ffa"),
)
# FFA deletion goes on to the FFA lobby's bet reconciliation and readmission
# steps once its lock is rewritten away, which this file does not model, so
# its lock statement is not mutated; its void mutant still runs.
_NO_LOCK_MUTANT = {("delete", "ffa")}


async def _seat(env, path, mode):
    """A lobby of `mode`: host h and member m; m's pending invite to x; the
    departure's trigger armed."""
    lid, (h, m) = await env.lobby(mode, 2)
    x = await env.player()
    iid = await env.invite(m, x, mode, lid)
    await env.fresh(mode, lid)
    s = types.SimpleNamespace(mode=mode, lid=lid, h=h, m=m, x=x, iid=iid, j=None, admin=None)
    if path == "state":
        await env.conn.execute("DELETE FROM queue_leases WHERE player_id = $1", m.id)
    elif path == "join_prune":
        await env.stale(mode, m, lid)
        s.j = await env.player()
    elif path == "ban":
        s.admin = await _admin(env)
    return s


def _depart(env, path, s):
    mode, m = s.mode, s.m
    if path == "leave":
        return lambda: env.leave(mode, m, s.lid)
    if path == "queue_leave":
        if mode == "team":
            return lambda: env.call(lambda db: main.team_queue_leave(
                Req(m.sid), steam_id=m.sid, expected_series_id=None, db=db))
        return lambda: env.call(lambda db: main.ovt_queue_leave(
            Req(m.sid), steam_id=m.sid, cause="", expected_series_id=None, db=db))
    if path == "state":
        return lambda: env.call(lambda db: main._lobby_state_impl(mode, m.sid, Req(m.sid), db))
    if path == "join_prune":
        return lambda: env.join(mode, s.j, s.lid)
    if path == "delete":
        return lambda: _delete(env, m)
    if path == "ban":
        return lambda: _ban(env, s.admin, m)
    raise AssertionError(path)                             # pragma: no cover


@pytest.mark.parametrize("path,mode", _PATHS, ids=["%s-%s" % p for p in _PATHS])
def test_a_departure_waits_on_the_lobby_lock_then_voids_the_departed_senders_invites(
        monkeypatch, path, mode):
    """While another session holds the lobby row, the departure waits with
    the member seated and the invite pending (neither the queue-row delete
    nor the void has happened); after the release the member is gone and the
    invite is void with sender_left, and the statement log shows the lobby
    lock, then the seat's delete, then the void. Mutants: the path's lobby
    lock rewritten to a plain read (the departure then finishes while the
    lock is held); _invite_end_departed ending nothing (the invite stays
    pending)."""
    async def body(env):
        if path == "ban":
            env.mp.setattr(main, "_pc_lease_drain", _drain_now)
        s = await _seat(env, path, mode)
        with env.rewriting(_EVERY, "") as log:
            obs = await _under_lock(env, mode, s.lid, s.m, [s.iid], _depart(env, path, s))
        assert obs["waited"] and not obs["finished_while_held"], ("the departure did not wait", obs)
        assert obs["seated_while_held"] and obs["while_held"] == ["pending"], obs
        assert obs["answer"].status == 200, obs["answer"]
        assert not obs["seated_after"] and obs["after"] == [VOID_LEFT], obs
        if s.j is not None:
            assert s.j.id in await env.members(mode, s.lid), "the pruning join did not seat its joiner"
        lock, gone, void = _order(log, mode)
        assert None not in (lock, gone, void) and lock < gone < void, (
            "lobby lock, seat delete, void out of order", lock, gone, void)

        # mutant 1: the path's lobby lock rewritten to a plain read
        if (path, mode) not in _NO_LOCK_MUTANT:
            s = await _seat(env, path, mode)
            with env.rewriting(_LOCK_RX[mode], r"\1") as hits:
                obs = await _under_lock(env, mode, s.lid, s.m, [s.iid], _depart(env, path, s))
            assert hits
            assert not obs["waited"] and obs["finished_while_held"] and not obs["seated_while_held"], (
                "without its lock statement the departure still waited", obs)

        # mutant 2: the void step taken out
        with pytest.MonkeyPatch.context() as mp2:
            mp2.setattr(main, "_invite_end_departed", _end_nothing)
            s = await _seat(env, path, mode)
            obs = await _under_lock(env, mode, s.lid, s.m, [s.iid], _depart(env, path, s))
        assert obs["waited"] and not obs["seated_after"], obs
        assert obs["after"] == [PENDING], ("the void mutant still ended the invite", obs)
    case(monkeypatch, body)


# -- a kick ends the kicked member's invites, both ways --------------------------

@pytest.mark.parametrize("mode", MODES)
def test_a_kick_waits_on_the_lobby_lock_and_ends_the_kicked_members_invites_both_ways(monkeypatch, mode):
    """The host kicks m, who joined with the host's invite still pending and
    then sent one of their own. While another session holds the lobby row
    the kick waits, m seated and both invites pending; after the release m
    is gone, m's invite is void with sender_left and the invite to m is void
    with invitee_kicked, each after the seat's delete. (A kick writes the
    lobby row's kicked list before its delete, so a kick with its lock
    statements rewritten away still waits; its mutants are the two steps.)
    Mutants: _invite_end_departed ending nothing (m's invite stays pending);
    _invite_end_kicked ending nothing (the invite to m stays pending)."""
    async def scene(env):
        lid, (h,) = await env.lobby(mode, 1)
        m, x = await env.players(2)
        to_m = await env.invite(h, m, mode, lid)
        ans = await env.join(mode, m, lid)
        assert ans.status == 200, ans
        await env.fresh(mode, lid)
        from_m = await env.invite(m, x, mode, lid)
        assert (await env.row(to_m))["state"] == "pending", "a plain join ended the invite to the joiner"
        return lid, h, m, [from_m, to_m]

    async def body(env):
        lid, h, m, iids = await scene(env)
        with env.rewriting(_EVERY, "") as log:
            obs = await _under_lock(env, mode, lid, m, iids, lambda: env.kick(mode, h, m))
        assert obs["waited"] and not obs["finished_while_held"], obs
        assert obs["seated_while_held"] and obs["while_held"] == ["pending", "pending"], obs
        assert obs["answer"].status == 200 and obs["answer"]["status"] == "kicked", obs["answer"]
        assert not obs["seated_after"] and obs["after"] == [VOID_LEFT, VOID_KICKED], obs
        lock, gone, void = _order(log, mode)
        kicked = _first(log, lambda s: "UPDATE lobby_invites" in s and "'invitee_kicked'" in s)
        assert None not in (lock, gone, void, kicked) and lock < gone < void and gone < kicked, (
            lock, gone, void, kicked)

        for name, idx in (("_invite_end_departed", 0), ("_invite_end_kicked", 1)):
            with pytest.MonkeyPatch.context() as mp2:
                mp2.setattr(main, name, _end_nothing)
                lid, h, m, iids = await scene(env)
                obs = await _under_lock(env, mode, lid, m, iids, lambda: env.kick(mode, h, m))
            assert obs["waited"] and not obs["seated_after"], (name, obs)
            want = [VOID_LEFT, VOID_KICKED]
            want[idx] = PENDING
            assert obs["after"] == want, ("the %s mutant still ended its invite" % name, obs)
    case(monkeypatch, body)


# -- an accept after a departure: the accept's own re-check ----------------------

def _recheck_without_sender(self, live):
    """The mutant: the accept's re-check keeps its row checks and drops the
    sender's live seat."""
    if self.row is None:
        raise HTTPException(status_code=404, detail="invite_not_found")
    main._invite_refuse_ended(self.row, void_as_answered=False)


@pytest.mark.parametrize("mode", MODES)
def test_an_accept_after_the_senders_departure_is_refused_invite_void_by_its_own_recheck(
        monkeypatch, mode):
    """With the departure's void step taken out, the sender's leave leaves
    the invite pending; the invitee's accept is still refused 409 invite_void
    (sender_left) by its re-check of the sender's live seat, seats nobody,
    and ends the invite void with sender_left after the rollback. Mutant: the
    re-check without the sender's seat (the accept then seats the invitee)."""
    async def scene(env, mp2):
        mp2.setattr(main, "_invite_end_departed", _end_nothing)
        lid, (h, m) = await env.lobby(mode, 2)
        x = await env.player()
        iid = await env.invite(m, x, mode, lid)
        await env.fresh(mode, lid)
        assert (await env.leave(mode, m, lid)).status == 200
        assert m.id not in await env.members(mode, lid)
        assert (await env.row(iid))["state"] == "pending", "the void step was not taken out"
        return lid, x, iid

    async def body(env):
        with pytest.MonkeyPatch.context() as mp2:
            lid, x, iid = await scene(env, mp2)
            got = await env.accept(x, iid)
        assert got.status == 409 and got.body == {"error": "invite_void", "end_reason": "sender_left"}, got
        assert x.id not in await env.members(mode, lid)
        assert _end(await env.row(iid)) == VOID_LEFT

        # mutant: the re-check without the sender's live seat
        with pytest.MonkeyPatch.context() as mp2:
            mp2.setattr(main._InviteJoinHook, "recheck", _recheck_without_sender)
            lid, x, iid = await scene(env, mp2)
            got = await env.accept(x, iid)
        assert got.status == 200 and x.id in await env.members(mode, lid), (
            "the re-check mutant still refused the accept", got)
        assert (await env.row(iid))["state"] == "accepted"
    case(monkeypatch, body)


# -- a ban: lobby locks FFA, 2v2, 1v2, FOR NO KEY UPDATE, held through the drain --

_BAN_ORDER = ("ffa", "team", "ovt")


async def _ban_scene(env):
    """The banned player t seated in an open lobby of each mode, with one
    pending invite of theirs in each, then banned while another session
    holds the 2v2 lobby row. What it observes: while the ban waits there,
    how the FFA and 1v2 lobby rows are held; when _pc_lease_drain runs, how
    each lobby row is held; after it, t's seats and the invites' ends."""
    lids = {}
    for mode in _BAN_ORDER:
        lids[mode], _host = await env.lobby(mode, 1)
    t = await env.player()
    for mode in ("team", "ovt", "ffa"):
        ans = await env.join(mode, t, lids[mode])
        assert ans.status == 200, ("setup: t takes a seat in each mode", mode, ans)
        # The seat's lease is what refuses a seat in a second mode.
        await env.conn.execute("DELETE FROM queue_leases WHERE player_id = $1", t.id)
    iids = {}
    for mode in _BAN_ORDER:
        await env.fresh(mode, lids[mode])
        iids[mode] = await env.invite(t, await env.player(), mode, lids[mode])
    admin = await _admin(env)
    probe = await env.side()
    seen = {}

    async def drain(db, pid):
        seen["at_drain"] = {m: await _row_lock(probe, m, lids[m]) for m in _BAN_ORDER}
        return 0.0
    env.mp.setattr(main, "_pc_lease_drain", drain)

    side = await env.side()
    await side.execute("BEGIN")
    await side.execute("SELECT 1 FROM team_lobbies WHERE id = $1 FOR NO KEY UPDATE", lids["team"])
    task = asyncio.ensure_future(_ban(env, admin, t))
    obs = {}
    try:
        waiters = await waiting_on(env, side.get_server_pid())
        obs["waited"] = bool(waiters) and not task.done()
        obs["while_waiting"] = ({m: await _row_lock(probe, m, lids[m]) for m in ("ffa", "ovt")}
                                if obs["waited"] else None)
        obs["seated_while_waiting"] = all([t.id in await env.members(m, lids[m]) for m in _BAN_ORDER])
    finally:
        await side.execute("ROLLBACK")
        ans = await asyncio.wait_for(task, BOUND)
    obs["answer"] = ans
    obs["at_drain"] = seen.get("at_drain")
    obs["seated_after"] = any([t.id in await env.members(m, lids[m]) for m in _BAN_ORDER])
    obs["after"] = {m: _end(await env.row(iids[m])) for m in _BAN_ORDER}
    return obs


def test_a_ban_locks_the_banned_players_lobbies_in_order_and_holds_them_through_the_drain(monkeypatch):
    """A ban locks each open lobby the banned player sits in, FFA then 2v2
    then 1v2, FOR NO KEY UPDATE, before any queue-row delete, and holds the
    locks while _pc_lease_drain runs (stubbed: it records how each lobby row
    is held, so no case waits its 65 s); the banned player's seats go and
    their invites end void with sender_left. Mutants: the order reversed,
    the ban core's loop walking _BAN_LOBBY_TABLES backwards (waiting on
    2v2, the 1v2 row is held and the FFA row free); the drain
    run before the locks (no lobby row of the ban's is held at the drain);
    the locks taken FOR UPDATE (a key share is refused at the drain)."""
    expect_waiting = {"ffa": "no_key", "ovt": "free"}
    expect_drain = {m: "no_key" for m in _BAN_ORDER}

    async def body(env):
        obs = await _ban_scene(env)
        assert obs["waited"] and obs["seated_while_waiting"], obs
        assert obs["while_waiting"] == expect_waiting, ("the ban's lock order", obs)
        assert obs["at_drain"] == expect_drain, ("the locks at the drain", obs)
        assert obs["answer"].status == 200 and obs["answer"]["status"] == "banned", obs["answer"]
        assert not obs["seated_after"], obs
        assert obs["after"] == {m: VOID_LEFT for m in _BAN_ORDER}, obs

        # mutant 1: the order reversed (1v2, 2v2, FFA). The ban core's lobby
        # loop walks the module's closed list _BAN_LOBBY_TABLES (FFA, 2v2,
        # 1v2); the mutant walks that list backwards, on the loop's own line.
        reversed_core = _source_mutant(
            main._apply_ban_core,
            ("        for _lmode, _lqt, _llt in _BAN_LOBBY_TABLES:\n",
             "        for _lmode, _lqt, _llt in tuple(reversed(_BAN_LOBBY_TABLES)):\n"))
        with pytest.MonkeyPatch.context() as mp2:
            mp2.setattr(main, "_apply_ban_core", reversed_core)
            obs = await _ban_scene(env)
        assert obs["waited"] and obs["while_waiting"] == {"ffa": "free", "ovt": "no_key"}, (
            "the reversed-order mutant kept the order", obs)

        # mutant 2: the drain run before the lobby locks
        drain_first = _source_mutant(
            main._apply_ban_core,
            ("        _ban_lobbies = []\n",
             "        await _pc_lease_drain(db, str(_bpid))\n        _ban_lobbies = []\n"),
            ("        waited = await _pc_lease_drain(db, str(_bpid))\n", "        waited = 0.0\n"))
        with pytest.MonkeyPatch.context() as mp2:
            mp2.setattr(main, "_apply_ban_core", drain_first)
            obs = await _ban_scene(env)
        # The 2v2 row reads held there: the side session holds it, not the ban.
        assert obs["at_drain"] == {"ffa": "free", "team": "no_key", "ovt": "free"}, (
            "the drain-first mutant still held the locks at the drain", obs)

        # mutant 3: the lobby locks taken FOR UPDATE
        with env.rewriting(_BAN_LOCK_RX, r"\1 FOR UPDATE") as hits:
            obs = await _ban_scene(env)
        assert hits
        assert obs["at_drain"] == {m: "update" for m in _BAN_ORDER}, (
            "the FOR UPDATE mutant still granted a key share", obs)
    case(monkeypatch, body)


# -- a revision bump while the invitee's account is being deleted ----------------

# The bump as first built: an upsert through the invitees' players rows, with
# no players lock and no deleted_at test.
_UPSERT_BUMP = (
    "INSERT INTO mail_inbox_rev (recipient_id, rev)"
    " SELECT p.id, 1 FROM players p"
    "  WHERE p.id IN (SELECT r.recipient_id FROM mail_recipients r"
    "         WHERE r.message_id = ANY(CAST(:mids AS uuid[])) AND r.delivery = 'delivered')"
    "  ORDER BY p.id"
    " ON CONFLICT (recipient_id) DO UPDATE"
    "   SET rev = mail_inbox_rev.rev + 1, updated_at = NOW()"
)
# The bump at stage 4: the same upsert under FOR KEY SHARE OF p SKIP LOCKED
# and deleted_at IS NULL, which skips any invitee whose players row is held
# at FOR UPDATE strength.
_SKIPPING_BUMP = (
    "INSERT INTO mail_inbox_rev (recipient_id, rev)"
    " SELECT p.id, 1 FROM players p"
    "  WHERE p.deleted_at IS NULL AND p.id IN (SELECT r.recipient_id FROM mail_recipients r"
    "         WHERE r.message_id = ANY(CAST(:mids AS uuid[])) AND r.delivery = 'delivered')"
    "  ORDER BY p.id FOR KEY SHARE OF p SKIP LOCKED"
    " ON CONFLICT (recipient_id) DO UPDATE"
    "   SET rev = mail_inbox_rev.rev + 1, updated_at = NOW()"
)


def test_a_bump_racing_an_account_deletion_leaves_the_account_no_revision_row(monkeypatch):
    """An invite change that owes a revision to an invitee whose account is
    being deleted leaves that account no revision row, at either point of
    the deletion's end. The real deletion is paused at its last bump (the
    call with `drop`), and the sender cancels the invite:
      before the bump -- the deletion holds the players row at FOR UPDATE
        strength (its steam_id rewrite) but no revision row: the cancel
        answers 200 at once, its bump moving the row the deletion then
        deletes;
      after the bump -- the deletion holds the account's revision row (its
        ascending lock pass), not yet deleted: the cancel's bump waits, and
        once the deletion deletes the row and commits it finds none.
    Mutant: the bump as first built (an upsert) waits there too, and then
    writes the deleted account a new revision row."""
    async def body(env):
        lid, (h,) = await env.lobby("team", 1)
        real_bump = main._invite_bump
        gate = {"at": None}

        async def paused_bump(db, mids, drop=None):
            # The deletion's last bump waits for the test, before or after it
            # runs; every other call runs as written.
            if drop is None or gate["at"] is None:
                return await real_bump(db, mids, drop=drop)
            at, gate["at"] = gate["at"], None
            if at == "before":
                gate["paused"].set()
                await gate["resume"].wait()
            out = await real_bump(db, mids, drop=drop)
            if at == "after":
                gate["paused"].set()
                await gate["resume"].wait()
            return out
        env.mp.setattr(main, "_invite_bump", paused_bump)

        async def scene(at):
            p = await env.player()
            iid = await env.invite(h, p, "team", lid)
            assert await env.rev(p) > 0, "the send left no revision row"
            gate.update(at=at, paused=asyncio.Event(), resume=asyncio.Event())
            deletion = asyncio.ensure_future(_delete(env, p))
            cancel = None
            try:
                await asyncio.wait_for(gate["paused"].wait(), BOUND)
                cancel = asyncio.ensure_future(env.cancel(h, iid))
                done, _rest = await asyncio.wait([cancel], timeout=10)
                waited = not done
            finally:
                gate["resume"].set()
            gone = await asyncio.wait_for(deletion, BOUND)
            ans = await asyncio.wait_for(cancel, BOUND)
            left = await env.conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM mail_inbox_rev WHERE recipient_id = $1)", p.id)
            return {"deleted": gone.status, "cancel": ans.status, "waited": waited, "left": left}

        got = await scene("before")
        assert got == {"deleted": 200, "cancel": 200, "waited": False, "left": False}, got
        got = await scene("after")
        assert got == {"deleted": 200, "cancel": 200, "waited": True, "left": False}, got
        env.mp.setattr(main, "_INVITE_REV_BUMP_SQL", _UPSERT_BUMP)
        got = await scene("after")
        assert got["waited"] and got["left"], ("the upsert mutant left no revision row", got)
    case(monkeypatch, body)


def test_a_bump_moves_a_live_invitees_revision_while_their_players_row_is_held(monkeypatch):
    """A live invitee's players row held at FOR UPDATE strength by another
    request -- mail_discord's relay-off gate, run as written on a second
    session -- neither stops nor delays the revision bump an invite change
    owes them: the sender's cancel answers 200 without waiting and the
    invitee's revision moves by one. Mutant: the stage-4 bump (FOR KEY SHARE
    OF p SKIP LOCKED) answers 200 and leaves it unmoved."""
    gate_sql = re.sub(r":me\b", "$1", mail_discord.RELAY_OFF_GATE_BY_ID_SQL)
    assert gate_sql.endswith("FOR UPDATE") and "$1" in gate_sql, gate_sql

    async def body(env):
        lid, (h,) = await env.lobby("team", 1)

        async def scene():
            p = await env.player()
            iid = await env.invite(h, p, "team", lid)
            before = await env.rev(p)
            side = await env.side()
            await side.execute("BEGIN")
            await side.fetchval(gate_sql, p.id)
            try:
                task = asyncio.ensure_future(env.cancel(h, iid))
                done, _rest = await asyncio.wait([task], timeout=10)
            finally:
                await side.execute("ROLLBACK")
            ans = await asyncio.wait_for(task, BOUND)
            return {"cancel": ans.status, "waited": not done, "moved": await env.rev(p) - before}

        assert await scene() == {"cancel": 200, "waited": False, "moved": 1}
        env.mp.setattr(main, "_INVITE_REV_BUMP_SQL", _SKIPPING_BUMP)
        got = await scene()
        assert got == {"cancel": 200, "waited": False, "moved": 0}, (
            "the stage-4 bump moved a held invitee's revision", got)
    case(monkeypatch, body)


# -- expiry decided after the lock waits ------------------------------------

async def _past_expiry_behind_a_lock(env, iid, hold_sql, hold_arg, call):
    """The invite's expires_at 2.5 s ahead; a second session holds a lock
    (`hold_sql`, with `hold_arg` as its one parameter, or with none when it
    is None) while `call` starts and waits on it, the wait confirmed while
    the invite is still unexpired; the expiry passes; the lock is released.
    Returns the call's answer. The time left is computed from the expires_at
    the update returned, so nothing here reads lobby_invites while a second
    session holds a lock on the table itself."""
    until = await env.conn.fetchval(
        "UPDATE lobby_invites SET expires_at = clock_timestamp() + make_interval(secs => 2.5)"
        " WHERE id = $1 RETURNING expires_at", iid)
    side = await env.side()
    await side.execute("BEGIN")
    if hold_arg is None:
        await side.execute(hold_sql)
    else:
        await side.fetch(hold_sql, hold_arg)
    task = asyncio.ensure_future(call())
    try:
        waiters = await waiting_on(env, side.get_server_pid())
        ahead = await env.conn.fetchval(
            "SELECT EXTRACT(EPOCH FROM (CAST($1 AS timestamptz) - clock_timestamp()))", until)
        assert waiters and not task.done() and ahead > 0, (
            "the call was not seen waiting before the expiry", waiters, task.done(), ahead)
        await asyncio.sleep(float(ahead) + 0.3)
    finally:
        await side.execute("ROLLBACK")
    return await asyncio.wait_for(task, BOUND)


def _lobby_hold(mode="team"):
    return "SELECT id FROM %s WHERE id = $1 FOR UPDATE" % LOBBY_TABLE[mode]


_INVITE_HOLD = "SELECT id FROM lobby_invites WHERE id = $1 FOR NO KEY UPDATE"


def test_an_accept_held_behind_the_lobby_lock_past_the_expiry_is_refused_expired(monkeypatch):
    """An accept that waits on the lobby row's lock while its invite expires
    is answered 410 invite_expired, seats nobody, and leaves the invite as it
    was: the join hook decides expiry after its locks are held. Mutant: the
    hook's read on NOW(), the transaction's start, seats the invitee."""
    async def body(env):
        async def scene():
            lid, (h,) = await env.lobby("team", 1)
            p = await env.player()
            iid = await env.invite(h, p, "team", lid)
            ans = await _past_expiry_behind_a_lock(env, iid, _lobby_hold(), lid,
                                                   lambda: env.accept(p, iid))
            return ans, p.id in await env.members("team", lid), (await env.row(iid))["state"]

        ans, seated, state = await scene()
        assert (ans.status, ans.body, seated, state) == (410, "invite_expired", False, "pending"), (
            ans, seated, state)
        with env.rewriting("(expires_at <= clock_timestamp()) AS past", "(expires_at <= NOW()) AS past",
                           where="SELECT state, end_reason, (expires_at") as hits:
            ans, seated, state = await scene()
        assert hits
        assert ans.status == 200 and seated, ("the NOW() mutant refused the accept", ans, seated)
    case(monkeypatch, body)


def test_a_decline_held_behind_the_invite_row_lock_past_the_expiry_is_refused_expired(monkeypatch):
    """A decline that waits on the invite row's lock while the invite expires
    is answered 410 invite_expired and leaves it pending: its read after the
    row lock decides. Mutant: that read on NOW() declines it."""
    async def body(env):
        lid, (h,) = await env.lobby("team", 1)

        async def scene():
            p = await env.player()
            iid = await env.invite(h, p, "team", lid)
            ans = await _past_expiry_behind_a_lock(env, iid, _INVITE_HOLD, iid,
                                                   lambda: env.decline(p, iid))
            return ans, (await env.row(iid))["state"]

        ans, state = await scene()
        assert (ans.status, ans.body, state) == (410, "invite_expired", "pending"), (ans, state)
        with env.rewriting("(i.expires_at <= clock_timestamp()) AS past", "(i.expires_at <= NOW()) AS past",
                           where="i.invitee_player_id = ") as hits:
            ans, state = await scene()
        assert hits
        assert ans.status == 200 and state == "declined", ("the NOW() mutant refused the decline", ans)
    case(monkeypatch, body)


def test_a_cancel_held_behind_the_lobby_lock_past_the_expiry_is_refused_expired(monkeypatch):
    """A cancel that waits on the lobby row's lock while the invite expires
    is answered 410 invite_expired and leaves it pending. Mutant: the read
    after the locks on NOW() cancels it."""
    async def body(env):
        lid, (h,) = await env.lobby("team", 1)

        async def scene():
            p = await env.player()
            iid = await env.invite(h, p, "team", lid)
            ans = await _past_expiry_behind_a_lock(env, iid, _lobby_hold(), lid,
                                                   lambda: env.cancel(h, iid))
            return ans, (await env.row(iid))["state"]

        ans, state = await scene()
        assert (ans.status, ans.body, state) == (410, "invite_expired", "pending"), (ans, state)
        with env.rewriting("(expires_at <= clock_timestamp()) AS past", "(expires_at <= NOW()) AS past",
                           where="SELECT id, sender_player_id, state, end_reason") as hits:
            ans, state = await scene()
        assert hits
        assert ans.status == 200 and state == "cancelled", ("the NOW() mutant refused the cancel", ans)
    case(monkeypatch, body)


def test_a_departure_held_behind_the_lobby_lock_past_the_expiry_ends_the_invite_expired(monkeypatch):
    """A sender who leaves while a second session holds the lobby row, the
    invite expiring during that wait, ends it 'expired' with no end_reason
    and ended_at at or after its expires_at: the ending statement reads the
    clock once, after the lock. Mutant: that reading on NOW() ends it void,
    sender_left."""
    async def body(env):
        async def scene():
            lid, (h, s) = await env.lobby("team", 2)
            p = await env.player()
            iid = await env.invite(s, p, "team", lid)
            ans = await _past_expiry_behind_a_lock(env, iid, _lobby_hold(), lid,
                                                   lambda: env.leave("team", s, lid))
            assert ans.status == 200, ans
            r = await env.row(iid)
            return r["state"], r["end_reason"], r["ended_at"] >= r["expires_at"]

        assert await scene() == ("expired", None, True)
        with env.rewriting("SELECT clock_timestamp() AS at", "SELECT NOW() AS at",
                           where="'sender_left'") as hits:
            got = await scene()
        assert hits
        assert got[:2] == ("void", "sender_left"), ("the NOW() mutant ended it expired", got)
    case(monkeypatch, body)


def test_a_send_held_behind_the_lobby_lock_ends_the_invite_that_expired_meanwhile(monkeypatch):
    """A second invite to the same player, sent while a second session holds
    the lobby row and the first invite expires during that wait, ends the
    first one 'expired' and is answered 200: one clock reading after the
    lobby lock decides both the ending and the pending count. Mutant: that
    reading on NOW() counts the expired invite as pending, already_invited."""
    async def body(env):
        async def scene():
            lid, (h,) = await env.lobby("team", 1)
            p = await env.player()
            first = await env.invite(h, p, "team", lid)
            ans = await _past_expiry_behind_a_lock(env, first, _lobby_hold(), lid,
                                                   lambda: env.send(h, p, "team", lid))
            return ans, (await env.row(first))["state"]

        ans, state = await scene()
        assert ans.status == 200 and state == "expired", (ans, state)
        with env.rewriting(re.compile(r"^SELECT clock_timestamp\(\)$"), "SELECT NOW()") as hits:
            ans, state = await scene()
        assert hits
        assert (ans.status, state) == (409, "pending") and ans["error"] == "already_invited", (
            "the NOW() mutant ended the expired invite", ans, state)
    case(monkeypatch, body)


# SHARE on lobby_invites conflicts with the ROW EXCLUSIVE a send's ending
# takes, and with no lock a send takes on the table before it.
_SHARE_HOLD = "LOCK TABLE lobby_invites IN SHARE MODE"
# The live-member read's table. A plain read waits only behind ACCESS
# EXCLUSIVE, and no statement of a send before that read touches the table.
_QUEUE_HOLD = "LOCK TABLE %s IN ACCESS EXCLUSIVE MODE" % QUEUE_TABLE["team"]


def test_a_send_held_behind_a_share_lock_on_the_invites_ends_the_invite_that_expired_meanwhile(monkeypatch):
    """A second invite to the same player, sent while a second session holds
    SHARE on lobby_invites and the first invite expires during that wait,
    ends the first one 'expired' and is answered 200: the send takes its
    ending's table lock (ROW EXCLUSIVE) before its clock reading. Mutant:
    without that LOCK TABLE the UPDATE takes the lock as it starts, after
    the reading, and the send counts the expired invite as pending,
    already_invited."""
    async def body(env):
        async def scene():
            lid, (h,) = await env.lobby("team", 1)
            p = await env.player()
            first = await env.invite(h, p, "team", lid)
            ans = await _past_expiry_behind_a_lock(env, first, _SHARE_HOLD, None,
                                                   lambda: env.send(h, p, "team", lid))
            return ans, (await env.row(first))["state"]

        ans, state = await scene()
        assert ans.status == 200 and state == "expired", (ans, state)
        with env.rewriting("LOCK TABLE lobby_invites IN ROW EXCLUSIVE MODE", "SELECT 1") as hits:
            ans, state = await scene()
        assert hits
        assert (ans.status, state) == (409, "pending") and ans["error"] == "already_invited", (
            "the mutant without the table lock ended the expired invite", ans, state)
    case(monkeypatch, body)


def _gates_reading_before_the_live_read():
    """A mutant of the send's lobby gates, compiled in main's namespace: its
    clock reading moved ahead of the live-member read, the order the a6s6
    round reviewed."""
    src = inspect.getsource(main._invite_lobby_gates)
    reading = '    at = (await db.execute(text("SELECT clock_timestamp()"))).scalar()\n'
    live = "    live = await _invite_live_members(db, mode, lobby_id)\n"
    assert src.count(reading) == 1 and src.count(live) == 1, "the gates' text changed shape"
    out = src.replace(reading, "").replace(live, reading + live)
    assert out != src
    ns = {}
    exec(compile(out, "<mutant _invite_lobby_gates>", "exec"), vars(main), ns)
    return ns["_invite_lobby_gates"]


def test_a_send_held_behind_a_lock_on_the_queue_table_ends_the_invite_that_expired_meanwhile(monkeypatch):
    """A second invite to the same player, sent while a second session holds
    the mode's queue table (the live-member read waits on it) and the first
    invite expires during that wait, ends the first one 'expired' and is
    answered 200: the send reads its live members before its clock reading.
    Mutant: the reading ahead of the live-member read counts the expired
    invite as pending, already_invited."""
    async def body(env):
        async def scene():
            lid, (h,) = await env.lobby("team", 1)
            p = await env.player()
            first = await env.invite(h, p, "team", lid)
            ans = await _past_expiry_behind_a_lock(env, first, _QUEUE_HOLD, None,
                                                   lambda: env.send(h, p, "team", lid))
            return ans, (await env.row(first))["state"]

        ans, state = await scene()
        assert ans.status == 200 and state == "expired", (ans, state)
        with monkeypatch.context() as mp:
            mp.setattr(main, "_invite_lobby_gates", _gates_reading_before_the_live_read())
            ans, state = await scene()
        assert (ans.status, state) == (409, "pending") and ans["error"] == "already_invited", (
            "the mutant reading ahead of the live-member read ended the expired invite", ans, state)
    case(monkeypatch, body)

def test_an_ending_after_a_refused_accept_decides_expiry_after_its_lobby_lock(monkeypatch):
    """The ending written after an accept the join refused (here: the lobby
    no longer open) re-reads the invite after the lobby lock, against the
    clock: an invite that expired while that transaction waited is left
    pending (every read calls it expired), not ended lobby_closed. The wait
    is a real one: inside the ending's transaction, between its first
    statement and its lobby lock, a second session takes the lobby row and
    holds it past the expiry, and the ending is seen waiting on it before the
    expiry. Mutant: the read on NOW() ends it void, lobby_closed."""
    async def body(env):
        real_lock = main._invite_lock_lobby
        hold = {"until": None, "seen": None, "task": None}

        async def contested_lock(db, mode, lobby_id):
            until, hold["until"] = hold["until"], None
            if until is not None:
                side = await env.side()
                await side.execute("BEGIN")
                await side.fetch(_lobby_hold(mode), lobby_id)

                async def release():
                    try:
                        waiters = await waiting_on(env, side.get_server_pid())
                        ahead = await env.conn.fetchval(
                            "SELECT EXTRACT(EPOCH FROM (CAST($1 AS timestamptz) - clock_timestamp()))", until)
                        hold["seen"] = (bool(waiters), ahead > 0)
                        await asyncio.sleep(max(0.0, float(ahead)) + 0.3)
                    finally:
                        await side.execute("ROLLBACK")
                hold["task"] = asyncio.ensure_future(release())
            return await real_lock(db, mode, lobby_id)
        env.mp.setattr(main, "_invite_lock_lobby", contested_lock)

        async def scene():
            lid, (h,) = await env.lobby("team", 1)
            p = await env.player()
            iid = await env.invite(h, p, "team", lid)
            hold["seen"], hold["task"] = None, None
            hold["until"] = await env.conn.fetchval(
                "UPDATE lobby_invites SET expires_at = clock_timestamp() + make_interval(secs => 1.5)"
                " WHERE id = $1 RETURNING expires_at", iid)
            await env.conn.execute("UPDATE %s SET status = 'canceled' WHERE id = $1" % LOBBY_TABLE["team"],
                                   lid)
            ans = await asyncio.wait_for(env.accept(p, iid), BOUND)
            assert hold["task"] is not None, "the ending never took the lobby lock"
            await asyncio.wait_for(hold["task"], BOUND)
            assert hold["seen"] == (True, True), (
                "the ending was not seen waiting on the lobby row before the expiry", hold["seen"])
            r = await env.row(iid)
            return ans.status, r["state"], r["end_reason"]

        status, state, reason = await scene()
        assert status == 404 and (state, reason) == ("pending", None), (status, state, reason)
        with env.rewriting("(expires_at <= clock_timestamp()) AS past", "(expires_at <= NOW()) AS past",
                           where="SELECT state, sender_player_id, mail_message_id,") as hits:
            got = await scene()
        assert hits
        assert got == (404, "void", "lobby_closed"), ("the NOW() mutant left it pending", got)
    case(monkeypatch, body)


def _ending_statement_defects(sql):
    """What is wrong with one ending statement's clock: [] when it reads
    clock_timestamp() once, in a leading MATERIALIZED CTE, takes state,
    end_reason and ended_at from that one reading (c.at, three times) and
    holds no NOW()."""
    out = []
    if not sql.startswith("WITH c AS MATERIALIZED (SELECT clock_timestamp() AS at)"):
        out.append("no leading MATERIALIZED clock reading")
    if sql.count("clock_timestamp()") != 1:
        out.append("%d clock_timestamp() calls" % sql.count("clock_timestamp()"))
    if "NOW()" in sql.upper():
        out.append("a NOW()")
    if sql.count("c.at") != 3:
        out.append("%d uses of c.at, not 3" % sql.count("c.at"))
    return out


def test_each_ending_statement_reads_the_clock_once_and_never_now():
    """The three ending statements decide expiry at one clock reading: a
    MATERIALIZED CTE over clock_timestamp(), and no NOW() and no second
    clock call, which could give state and end_reason two different
    instants (ck_lobby_invites_void_reason refuses a void row without one).
    The negative control: each defect, planted in a copy of a real ending
    statement, is reported."""
    for name in ("_INVITE_END_DEPARTED_SQL", "_INVITE_END_LOBBY_SQL", "_INVITE_END_KICKED_SQL"):
        assert _ending_statement_defects(getattr(main, name)) == [], name
    real = main._INVITE_END_LOBBY_SQL
    mutants = {
        "the reading on NOW()": real.replace("SELECT clock_timestamp() AS at", "SELECT NOW() AS at"),
        "the reading not materialized": real.replace("WITH c AS MATERIALIZED (", "WITH c AS ("),
        "a second clock call": real.replace("c.at", "clock_timestamp()", 1),
        "a field on NOW()": real.replace("c.at", "NOW()", 1),
    }
    for what, sql in mutants.items():
        assert sql != real, what
        assert _ending_statement_defects(sql), "%s was not reported" % what


# -- the reads: expiry against the clock when the statement runs ------------

_TABLE_HOLD = "LOCK TABLE lobby_invites IN ACCESS EXCLUSIVE MODE"
# The per-sender mail lock a send takes after its identity barrier and before
# it reads its key's receipt. (The barrier's own wait is bounded at 2.5 s, so
# a hold there would refuse the send 503 before the invite expired.)
_SENDER_HOLD = "SELECT pg_advisory_xact_lock(hashtext('mail:' || CAST(CAST($1 AS uuid) AS text)))"
_VIEW_FROM = "FROM lobby_invites i JOIN players s ON s.id = i.sender_player_id"
_LIST_FROM = "FROM lobby_invites i JOIN players p ON p.id = i.invitee_player_id"


def _invite_in_inbox(answer, iid):
    """The invite object of `iid`'s mail row in an inbox answer, or None."""
    for m in answer["messages"]:
        inv = m.get("invite")
        if inv and inv["invite_id"] == str(iid):
            return inv
    return None


def test_a_send_repeat_held_behind_the_sender_lock_past_the_expiry_answers_expired(monkeypatch):
    """A send repeated with its key while a second session holds the
    sender's per-sender mail lock, the invite expiring during that wait,
    answers it 'expired': the repeat compares expiry with the clock when its
    read runs. Mutant: that read on NOW(), the transaction's start, answers
    'pending'."""
    async def body(env):
        async def scene():
            lid, (h,) = await env.lobby("team", 1)
            p = await env.player()
            k = key()
            first = await env.send(h, p, "team", lid, k=k)
            assert first.status == 200, first
            iid = uuid.UUID(first["invite_id"])
            ans = await _past_expiry_behind_a_lock(env, iid, _SENDER_HOLD, h.id,
                                                   lambda: env.send(h, p, "team", lid, k=k))
            assert ans.status == 200 and ans["invite_id"] == str(iid), ans
            return ans["state"]

        assert await scene() == "expired"
        with env.rewriting("(expires_at <= clock_timestamp()) AS past", "(expires_at <= NOW()) AS past",
                           where="SELECT id, mode, lobby_id, kind, state, expires_at,") as hits:
            state = await scene()
        assert hits
        assert state == "pending", ("the NOW() mutant answered it expired", state)
    case(monkeypatch, body)


def test_the_inbox_held_behind_a_table_lock_past_the_expiry_shows_the_invite_expired(monkeypatch):
    """The invitee's inbox, read while a second session holds lobby_invites
    and the invite expires during that wait, shows the invite 'expired' with
    no seconds left: the invite view compares expiry with the clock when its
    statement runs. Mutant: that reading on NOW() shows it pending."""
    async def body(env):
        async def scene():
            lid, (h,) = await env.lobby("team", 1)
            p = await env.player()
            iid = await env.invite(h, p, "team", lid)
            ans = await _past_expiry_behind_a_lock(
                env, iid, _TABLE_HOLD, None,
                lambda: env.call(lambda db: main.mail_inbox(Req(p.sid), cursor="",
                                                            limit=main.MAIL_PAGE_MAX, db=db)))
            assert ans.status == 200, ans
            inv = _invite_in_inbox(ans, iid)
            assert inv is not None, ans
            return inv["state"], inv["seconds_left"]

        assert await scene() == ("expired", 0)
        with env.rewriting("SELECT clock_timestamp() AS at", "SELECT NOW() AS at", where=_VIEW_FROM) as hits:
            state, left = await scene()
        assert hits
        assert state == "pending" and left > 0, ("the NOW() mutant showed it expired", state, left)
    case(monkeypatch, body)


def test_the_pending_list_held_behind_a_table_lock_past_the_expiry_leaves_the_invite_out(monkeypatch):
    """The invitee's pending list, read while a second session holds
    lobby_invites and the invite expires during that wait, leaves it out:
    its filter compares expiry with the clock when the statement runs.
    Mutant: that reading on NOW() lists it."""
    async def body(env):
        async def scene():
            lid, (h,) = await env.lobby("team", 1)
            p = await env.player()
            iid = await env.invite(h, p, "team", lid)
            ans = await _past_expiry_behind_a_lock(env, iid, _TABLE_HOLD, None, lambda: env.pending(p))
            assert ans.status == 200, ans
            return [i["invite_id"] for i in ans["invites"]], str(iid)

        listed, _iid = await scene()
        assert listed == [], listed
        with env.rewriting("SELECT clock_timestamp() AS at", "SELECT NOW() AS at", where=_VIEW_FROM) as hits:
            listed, iid = await scene()
        assert hits
        assert listed == [iid], ("the NOW() mutant left the invite out", listed)
    case(monkeypatch, body)


def test_a_lobby_list_held_behind_a_table_lock_past_the_expiry_shows_the_invite_expired(monkeypatch):
    """A member's lobby state, read while a second session holds lobby_invites
    and an invite expires during that wait, lists it 'expired' with no
    seconds left and no cancel: the lobby list compares expiry with the clock
    when its statement runs. Mutant: that reading on NOW() lists it pending
    and cancellable."""
    async def body(env):
        async def scene():
            lid, (h,) = await env.lobby("team", 1)
            p = await env.player()
            iid = await env.invite(h, p, "team", lid)
            ans = await _past_expiry_behind_a_lock(
                env, iid, _TABLE_HOLD, None,
                lambda: env.call(lambda db: main._lobby_state_impl("team", h.sid, Req(h.sid), db)))
            assert ans.status == 200, ans
            (inv,) = [i for i in ans["invites"] if i["invite_id"] == str(iid)]
            return inv["state"], inv["seconds_left"], inv["can_cancel"]

        assert await scene() == ("expired", 0, False)
        with env.rewriting("SELECT clock_timestamp() AS at", "SELECT NOW() AS at", where=_LIST_FROM) as hits:
            state, left, can_cancel = await scene()
        assert hits
        assert (state, can_cancel) == ("pending", True) and left > 0, (
            "the NOW() mutant listed it expired", state, left, can_cancel)
    case(monkeypatch, body)


def test_the_sweep_held_behind_a_table_lock_past_the_expiry_ends_the_invite_expired(monkeypatch):
    """A pending invite whose lobby has closed, swept while a second session
    holds lobby_invites and the invite expires during that wait, is ended
    'expired' with no end_reason: the sweep compares expiry with the clock
    when its statement runs. Mutant: that reading on NOW() ends it void,
    lobby_closed."""
    async def body(env):
        async def scene():
            lid, (h,) = await env.lobby("team", 1)
            p = await env.player()
            iid = await env.invite(h, p, "team", lid)
            await env.conn.execute("UPDATE %s SET status = 'canceled' WHERE id = $1" % LOBBY_TABLE["team"],
                                   lid)
            await _past_expiry_behind_a_lock(env, iid, _TABLE_HOLD, None, env.sweep)
            r = await env.row(iid)
            return r["state"], r["end_reason"]

        assert await scene() == ("expired", None)
        with env.rewriting("SELECT clock_timestamp() AS at", "SELECT NOW() AS at",
                           where="UPDATE lobby_invites i") as hits:
            got = await scene()
        assert hits
        assert got == ("void", "lobby_closed"), ("the NOW() mutant ended it expired", got)
    case(monkeypatch, body)


# main.py's invite code runs from INVITE_LIFETIME_MINUTES to the end of
# _invite_retention_sweep. Every SQL text there compares an invite's expiry
# with the clock when its statement runs. NOW() and the other clocks that
# stand still for a transaction or a statement appear there only as a value a
# write stores: an invite's ended_at, a revision's updated_at, and a new
# invite's expires_at (NOW() plus its lifetime).
_STILL_CLOCKS = re.compile(r"\b(now\(\)|current_timestamp|transaction_timestamp\(\)|statement_timestamp\(\)"
                           r"|localtimestamp|current_time|current_date)", re.I)
_STORED_VALUES = (re.compile(r", ended_at = NOW\(\)"), re.compile(r", updated_at = NOW\(\)"),
                  re.compile(r"NOW\(\) \+ make_interval\(mins => CAST\(:life AS integer\)\)"))


_REGION_FIRST = re.compile(r"^INVITE_LIFETIME_MINUTES = ", re.M)
_REGION_LAST = re.compile(r"^async def _invite_retention_sweep\(", re.M)
_TOP_LEVEL = re.compile(r"^[^\s#)\]}]", re.M)
# The statements and functions that hold the expiry reads; each must stand in the region.
_REGION_NAMES = ("_INVITE_END_DEPARTED_SQL", "_INVITE_END_LOBBY_SQL", "_INVITE_END_KICKED_SQL",
                 "_invite_send_repeat", "_INVITE_VIEW_SELECT", "_INVITE_LOBBY_LIST_SQL", "_INVITE_SWEEP_SQL",
                 "_invite_retention_sweep")


def _invite_region(source):
    """main.py's invite code, parsed alone (one parse of the whole of
    main.py takes seconds): from the INVITE_LIFETIME_MINUTES assignment to
    the end of _invite_retention_sweep, where the next top-level statement
    starts."""
    assert len(_REGION_FIRST.findall(source)) == 1 and len(_REGION_LAST.findall(source)) == 1
    first = _REGION_FIRST.search(source).start()
    after = _TOP_LEVEL.search(source, source.index("\n", _REGION_LAST.search(source).end()) + 1)
    tree = ast.parse(source[first:after.start() if after else len(source)])
    last = tree.body[-1]
    assert isinstance(last, ast.AsyncFunctionDef) and last.name == "_invite_retention_sweep", ast.dump(last)[:80]
    return tree


def _region_names(tree):
    """The names the region's top-level statements define."""
    out = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            out.update(getattr(t, "id", None) for t in node.targets)
    return out


def _invite_sql_texts(source):
    """Every string constant in main.py's invite code, docstrings left out."""
    tree = _invite_region(source)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body \
                and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
            docs.add(id(node.body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]


def _invite_clock_defects(source):
    """Each still clock in the invite code's SQL that is not a stored value."""
    out = []
    for sql in _invite_sql_texts(source):
        rest = sql
        for stored in _STORED_VALUES:
            rest = stored.sub("", rest)
        out.extend("%s in %r" % (m.group(0), sql[:70]) for m in _STILL_CLOCKS.finditer(rest))
    return out


def test_no_invite_read_compares_expiry_with_a_clock_that_stands_still():
    """No SQL text in the invite code compares with NOW() or another clock
    that stands still for a transaction or a statement; such a clock appears
    only as a value a write stores. The negative control: each still clock,
    planted in a copy of main.py at one expiry comparison of each read (the
    send's repeat, the invitee's view, the pending filter, the lobby list's
    horizon, the sweep, retention), is reported."""
    with open(main.__file__, encoding="utf-8") as f:
        source = f.read()
    missing = set(_REGION_NAMES) - _region_names(_invite_region(source))
    assert not missing, ("the invite region lacks", sorted(missing))
    assert _invite_sql_texts(source), "the invite code holds no SQL text"
    assert _invite_clock_defects(source) == []
    mutants = {
        "the send's repeat": ("expires_at, (expires_at <= clock_timestamp()) AS past",
                              "expires_at, (expires_at <= NOW()) AS past"),
        "the invitee's view": ("i.mail_message_id, (i.expires_at <= t.at) AS past,",
                               "i.mail_message_id, (i.expires_at <= CURRENT_TIMESTAMP) AS past,"),
        "the pending filter": ("AND i.state = 'pending' AND i.expires_at > t.at",
                               "AND i.state = 'pending' AND i.expires_at > statement_timestamp()"),
        "the lobby list's horizon": ("> t.at - make_interval(secs => CAST(:shown AS double precision))",
                                     "> transaction_timestamp() - make_interval(secs => CAST(:shown AS double precision))"),
        "the sweep": ("AND NOT (i.expires_at > t.at", "AND NOT (i.expires_at > now()"),
        "retention": ("WHERE expires_at < (SELECT clock_timestamp())", "WHERE expires_at < LOCALTIMESTAMP"),
    }
    for what, (old, new) in mutants.items():
        assert source.count(old) == 1, what
        assert _invite_clock_defects(source.replace(old, new)), "%s was not reported" % what
