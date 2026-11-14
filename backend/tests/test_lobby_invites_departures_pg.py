"""Lobby invites on PostgreSQL (migration 405's change): departures, through
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

import asyncio
import hashlib
import hmac
import inspect
import os
import re
import sys
import types

import asyncpg
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

from fastapi import HTTPException  # noqa: E402

from inv_pg import LOBBY_TABLE, MODES, QUEUE_TABLE, Req, case, waiting_on  # noqa: E402

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
#   poll         ffa_queue_poll (the seat's lease is gone, so its renewal
#                fails and the seat ends; the 2v2 and 1v2 polls' same branch
#                ends no invite, note 13 (m), and is tested in the sweep suite)
#   state        _lobby_state_impl (the same renewal, from the lobby state)
#   join_prune   _lobby_join_core, _ffa_lobby_join_core (m is stale; a join prunes it)
#   delete       delete_player_data
#   ban          _apply_ban_core
# The kick has its own test below.

_PATHS = (
    ("leave", "team"), ("leave", "ovt"), ("leave", "ffa"),
    ("queue_leave", "team"), ("queue_leave", "ovt"),
    ("poll", "ffa"),
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
    if path in ("poll", "state"):
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
    if path == "poll":
        assert mode == "ffa", mode                         # note 13 (m)
        return lambda: env.call(lambda db: main.ffa_queue_poll(m.sid, Req(m.sid), db=db))
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
    their invites end void with sender_left. Mutants: the order reversed
    (waiting on 2v2, the 1v2 row is held and the FFA row free); the drain
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

        # mutant 1: the order reversed (1v2, 2v2, FFA)
        reversed_core = _source_mutant(
            main._apply_ban_core,
            ('("ffa", "ffa_queue", "ffa_lobbies")', "@@first@@"),
            ('("ovt", "ovt_queue", "ovt_lobbies")', '("ffa", "ffa_queue", "ffa_lobbies")'),
            ("@@first@@", '("ovt", "ovt_queue", "ovt_lobbies")'))
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

_BUMP = "INSERT INTO mail_inbox_rev"


def test_a_bump_skips_an_account_being_deleted_and_leaves_it_no_revision_row(monkeypatch):
    """An invite change that owes a revision to an invitee whose account is
    being deleted skips that account at once, and the deletion's removal of
    the account's revision row stands. The real deletion is paused at its
    last bump, after its steam_id rewrite (FOR UPDATE strength on the players
    row) and its delete of the revision row; the sender's cancel answers 200
    without waiting, and once the deletion commits the account has no
    revision row. Mutants: the bump as first built (no players lock, no
    deleted_at test) waits on the deleted revision row and, when the deletion
    commits, writes the account a new one; the players lock without SKIP
    LOCKED waits for the deletion's commit."""
    async def body(env):
        lid, (h,) = await env.lobby("team", 1)
        real_bump = main._invite_bump
        gate = {"armed": False}

        async def paused_bump(db, mids):
            # The deletion's last bump (the first call while armed) waits for
            # the test; every other call runs as written.
            if gate["armed"]:
                gate["armed"] = False
                gate["paused"].set()
                await gate["resume"].wait()
            return await real_bump(db, mids)
        env.mp.setattr(main, "_invite_bump", paused_bump)

        async def scene():
            p = await env.player()
            iid = await env.invite(h, p, "team", lid)
            assert await env.rev(p) > 0, "the send left no revision row to delete"
            gate.update(armed=True, paused=asyncio.Event(), resume=asyncio.Event())
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

        got = await scene()
        assert got == {"deleted": 200, "cancel": 200, "waited": False, "left": False}, got
        with env.rewriting("p.deleted_at IS NULL AND ", "", where=_BUMP) as h1, \
                env.rewriting(" FOR KEY SHARE OF p SKIP LOCKED", "", where=_BUMP) as h2:
            got = await scene()
        assert h1 and h2
        assert got["waited"] and got["left"], ("the first-built bump left no revision row", got)
        with env.rewriting(" SKIP LOCKED", "", where=_BUMP) as h3:
            got = await scene()
        assert h3
        assert got["waited"] and not got["left"], ("the waiting players lock did not wait", got)
    case(monkeypatch, body)
