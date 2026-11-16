"""Lobby invites on PostgreSQL (migration 416's change): how pending invites
end -- after a refused accept, in the janitor's sweep, at a lobby's start --
and the one-pending-invite rule, against a local PostgreSQL through inv_pg
(one cf_pg case schema per case, the real handlers in main.py).

Every test pins one behaviour. Each has a mutant that must turn its check
red -- a statement rewrite that asserts it reached a statement, or a main.py
function swapped for the length of one call, which records that it ran --
and runs the same check on the real path, which must pass.

The states these tests need that no handler produces on its own (a lobby
closed, a seat removed or gone stale, a player on a kicked list) are made by
direct SQL, so nothing but the path under test ends the invites.
"""

import asyncio
import contextlib
import inspect
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import asyncpg  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

import inv_pg as inv  # noqa: E402
from inv_pg import Answer, Req, case  # noqa: E402

import main  # noqa: E402


# -- helpers -------------------------------------------------------------------

@contextlib.contextmanager
def _swap(obj, name, value):
    """`obj.name` replaced by `value` while the block runs (a mutant scoped
    to one call, leaving the case's own patches in place)."""
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


async def _end(env, iid):
    """An invite's (state, end_reason)."""
    r = await env.row(iid)
    return (r["state"], r["end_reason"])


async def _ends(env, ids):
    return [await _end(env, i) for i in ids]


async def _set_status(env, mode, lid, status):
    """A lobby row's status changed directly: no path that ends invites runs."""
    await env.conn.execute("UPDATE %s SET status = $2 WHERE id = $1" % inv.LOBBY_TABLE[mode],
                           lid, status)


async def _add_kicked(env, mode, lid, p):
    """`p` put on a lobby's kicked list directly (the list a join reads)."""
    await env.conn.execute(
        "UPDATE %s SET kicked_steam_ids = CONCAT_WS(',', NULLIF(kicked_steam_ids, ''), CAST($2 AS text))"
        " WHERE id = $1" % inv.LOBBY_TABLE[mode], lid, p.sid)


async def _seat(env, mode, p):
    """`p`'s queue row of `mode` as (status, lobby id as text), or None."""
    r = await env.conn.fetchrow(
        "SELECT status, series_id FROM %s WHERE player_id = $1" % inv.QUEUE_TABLE[mode], p.id)
    return None if r is None else (r["status"], str(r["series_id"]))


async def _member_ids(env, mode, lid):
    return [str(i) for i in await env.members(mode, lid)]


async def _accept_receipts(env, iid):
    return await env.conn.fetchval(
        "SELECT COUNT(*) FROM invite_receipts WHERE invite_id = $1 AND route = 'accept'", iid)


async def _ban(env, p):
    """An active ban on `p`, issued by a synthetic admin."""
    admin = await env.player()
    await env.conn.execute(
        "INSERT INTO admin_users (steam_id, granted_at) VALUES ($1, NOW()) ON CONFLICT DO NOTHING",
        admin.sid)
    await env.conn.execute(
        "INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, expires_at)"
        " VALUES ($1, 'test', $2, NOW() + INTERVAL '30 days')",
        p.sid, admin.sid)


async def _start(env, mode, host):
    """The host presses Start: the mode's start route, its Answer."""
    if mode == "ffa":
        req = main._FfaLobbyStartReq(steam_id=host.sid)
        return await env.call(lambda db: main.ffa_lobby_start(req, Req(host.sid), db))
    req = main._LobbyStartReq(steam_id=host.sid)
    fn = main.team_lobby_start if mode == "team" else main.ovt_lobby_start
    return await env.call(lambda db: fn(req, Req(host.sid), db))


async def _sweep_within(env, ms):
    """The janitor's invite sweep with lock_timeout `ms` set in its own
    transaction: (number ended, None), or (None, the error's text)."""
    try:
        async with env.sm() as db:
            await db.execute(text("SELECT set_config('lock_timeout', :v, true)"), {"v": "%dms" % ms})
            n = await main._invite_sweep(db)
            await db.commit()
        return n, None
    except Exception as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)


async def _refresh_live(env):
    """Every lobby seat polled within the last 300 s is polled now, so a slow
    setup across three modes cannot age a kept invite's sender past the
    75 s live-member window; a seat a case made stale on purpose (inv_pg's
    stale: 600 s ago) stays stale."""
    for q in inv.QUEUE_TABLE.values():
        await env.conn.execute(
            "UPDATE %s SET last_polled = clock_timestamp()"
            " WHERE status = 'lobby' AND last_polled > clock_timestamp() - INTERVAL '300 seconds'" % q)


# The sweep statement, and nothing else, carries this text.
_SWEEP_MARK = "FOR NO KEY UPDATE OF i SKIP LOCKED"
_LOBBY_OPEN = "COALESCE(tl.status, ol.status, fl.status, '') = 'open'"
_SENDER_SEAT = "THEN EXISTS (SELECT 1 FROM"
_VOID = {"error": "invite_void", "end_reason": "sender_left"}


# -- an accept refused in a way that ends the invite (section 11, item 8) -------
#
# The join refuses "That lobby is no longer open" (closed, or started) or
# kicked_from_lobby, or the invite's re-check finds its sender's seat stale.
# The accept rolls the join back whole, ends the invite in a second short
# transaction, and returns the refusal unchanged.

ENDING_REFUSALS = ("lobby_closed", "lobby_started", "invitee_kicked", "sender_left")


async def _ending_setup(env, mode, why):
    """A lobby of `mode` whose host sent three pending invites, then the state
    `why` names, made directly: the lobby canceled, or active (a start); the
    invitees on its kicked list; or the host's seat stale. Returns (lobby id,
    host, [(invitee, invite)])."""
    lid, (h,) = await env.lobby(mode, 1)
    out = []
    for p in await env.players(3):
        out.append((p, await env.invite(h, p, mode, lid)))
    if why == "lobby_closed":
        await _set_status(env, mode, lid, "canceled")
    elif why == "lobby_started":
        await _set_status(env, mode, lid, "active")
    elif why == "invitee_kicked":
        for p, _i in out:
            await _add_kicked(env, mode, lid, p)
    else:
        await env.stale(mode, h, lid)
    assert await _ends(env, [i for _p, i in out]) == [("pending", None)] * 3, (mode, why)
    return lid, h, out


@pytest.mark.parametrize("why", ENDING_REFUSALS)
def test_a_refused_accept_ends_its_invite_after_the_rollback_and_answers_the_refusal_unchanged(
        monkeypatch, why):
    """In each mode: the accept answers byte for byte what the join itself
    answers for that state (for a stale sender, the invite_void refusal,
    which is also what the ended invite answers afterwards), writes no
    receipt, and leaves the invite void with the end the state names; for a
    stale sender the rollback restored the seat the join had pruned.
    Mutants: the ending after the refusal removed (the invite stays
    pending); the refusal rewritten on its way out (the answer differs)."""
    async def body(env):
        for mode in inv.MODES:
            lid, h, out = await _ending_setup(env, mode, why)
            (p1, i1), (p2, i2), (p3, i3) = out
            if why == "sender_left":
                want = Answer(409, _VOID)
            else:
                # The join's own refusal for this state, from the mode's join.
                want = await env.join(mode, p1, lid)
                expect = (Answer(403, "kicked_from_lobby") if why == "invitee_kicked"
                          else Answer(404, "That lobby is no longer open"))
                assert want == expect, (mode, why, want)
            assert await _end(env, i1) == ("pending", None), (mode, why, "the join ended the invite")

            # the real path
            got = await env.accept(p1, i1)
            assert got.wire == want.wire, (mode, why, got, want)
            assert await _end(env, i1) == ("void", why), (mode, why)
            assert await _accept_receipts(env, i1) == 0, (mode, why, "a refused accept wrote a receipt")
            if why == "sender_left":
                assert await _seat(env, mode, h) == ("lobby", str(lid)), \
                    (mode, "the pruned seat was not restored by the rollback")
            again = await env.accept(p1, i1)
            assert again == Answer(409, {"error": "invite_void", "end_reason": why}), (mode, why, again)

            # mutant 1: no ending after the refusal
            calls = []

            async def _no_end(db, invite_id, why_, steam_id):
                calls.append(str(invite_id))
            with _swap(main, "_invite_end_after_refusal", _no_end):
                got = await env.accept(p2, i2)
            assert calls == [str(i2)], (mode, why, calls)
            assert got.wire == want.wire, (mode, why, got)
            assert await _end(env, i2) == ("pending", None), \
                (mode, why, "the invite ended without the ending step")

            # mutant 2: the refusal altered on its way out
            real_ending = main._invite_join_ending
            seen = []

            def _altered(exc):
                w = real_ending(exc)
                if w is not None:
                    seen.append(w)
                    exc.detail = {"error": "invite_ended", "end_reason": w}
                return w
            with _swap(main, "_invite_join_ending", _altered):
                got = await env.accept(p3, i3)
            assert len(seen) == 1, (mode, why, seen)
            assert got.wire != want.wire, (mode, why, "the altered refusal still matched", got)
            assert await _end(env, i3) == ("void", why), (mode, why)
    case(monkeypatch, body)


# -- the sweep keeps exactly the states it names (section 11, item 11) ----------
#
# _INVITE_SWEEP_SQL keeps a pending invite only while it is unexpired, its
# lobby is open, and its sender holds a live seat in it (a queue row that is
# the sender's, in that lobby, a 'lobby' row, polled within the live-member
# window); it touches no row that is not pending. One case per condition:
# that condition alone made false ends the invite (or, for the pending rule,
# leaves an ended row as it is), and the rewrite that drops the condition
# from the keep list must change that outcome. Each mutant's text is counted
# in the statement: the sender's conditions occur once per mode.

_SWEEP_KEEPS = {
    "unexpired": ("i.expires_at > t.at", "TRUE", 1),
    "lobby_open": (_LOBBY_OPEN, "TRUE", 1),
    "sender_has_a_seat": (_SENDER_SEAT, "THEN TRUE OR EXISTS (SELECT 1 FROM", 3),
    "seat_is_the_senders": ("q.player_id = i.sender_player_id", "TRUE", 3),
    "seat_is_in_the_lobby": ("q.series_id = i.lobby_id", "TRUE", 3),
    "seat_is_a_lobby_seat": ("q.status = 'lobby'", "TRUE", 3),
    "seat_is_fresh": ("q.last_polled > clock_timestamp() - INTERVAL '75 seconds'", "TRUE", 3),
    "only_pending_rows": ("WHERE i.state = 'pending'", "WHERE TRUE", 1),
}


async def _sweep_targets(env, mode, cond):
    """The rows one condition case sweeps, in `mode`: ([(invite, the end the
    sweep must give it)], [invites the sweep must keep pending]). A control
    lobby's invite is always kept; the host's invite in the target lobby is
    kept wherever the condition is about the member who sent the target."""
    q = inv.QUEUE_TABLE[mode]
    kl, (kh,) = await env.lobby(mode, 1)
    kept = [await env.invite(kh, await env.player(), mode, kl)]
    targets = []
    statuses = ((("canceled", "lobby_closed"), ("active", "lobby_started"),
                 ("completed", "lobby_started")) if cond == "lobby_open" else ((None, None),))
    for status, reason in statuses:
        lid, (h, m) = await env.lobby(mode, 2)
        x, z = await env.players(2)
        target = await env.invite(m, x, mode, lid)
        other = await env.invite(h, z, mode, lid)
        await env.fresh(mode, lid)
        await env.fresh(mode, kl)
        end = ("void", "sender_left")
        if cond == "unexpired":
            await env.age(target, expired_s=5)
            end = ("expired", None)
        elif cond == "lobby_open":
            await _set_status(env, mode, lid, status)
            end = ("void", reason)
            targets.append((other, end))
        elif cond in ("sender_has_a_seat", "seat_is_the_senders"):
            await env.conn.execute("DELETE FROM %s WHERE player_id = $1" % q, m.id)
        elif cond == "seat_is_in_the_lobby":
            await env.conn.execute("UPDATE %s SET series_id = $2 WHERE player_id = $1" % q, m.id, kl)
        elif cond == "seat_is_a_lobby_seat":
            await env.conn.execute("UPDATE %s SET status = 'searching' WHERE player_id = $1" % q, m.id)
        elif cond == "seat_is_fresh":
            await env.stale(mode, m, lid)
        elif cond == "only_pending_rows":
            assert (await env.decline(x, target)).status == 200
            assert (await env.cancel(h, other)).status == 200
            await _set_status(env, mode, lid, "canceled")
            end = ("declined", None)
            targets.append((other, ("cancelled", None)))
        else:                                              # pragma: no cover
            raise AssertionError(cond)
        if cond not in ("lobby_open", "only_pending_rows"):
            kept.append(other)
        targets.append((target, end))
    return targets, kept


@pytest.mark.parametrize("cond", sorted(_SWEEP_KEEPS))
def test_the_sweep_keeps_exactly_the_states_it_names(monkeypatch, cond):
    """For each keep condition of the sweep, in every mode: the invite whose
    only failing condition is this one is ended with the right state and
    reason (or, for the pending rule, an ended row is left as it is), and
    the invites the condition does not touch stay pending. Mutant: the
    condition dropped from the statement."""
    old, new, count = _SWEEP_KEEPS[cond]
    assert main._INVITE_SWEEP_SQL.count(old) == count, (cond, "the sweep's text moved")

    async def body(env):
        targets, kept = [], []
        for mode in inv.MODES:
            t, k = await _sweep_targets(env, mode, cond)
            targets += [(mode, i, e) for i, e in t]
            kept += k
        want = [(mode, e) for mode, _i, e in targets]

        async def got():
            return [(mode, await _end(env, i)) for mode, i, _e in targets]

        async def mutant_sweep():
            await _refresh_live(env)
            with env.rewriting(old, new, where=_SWEEP_MARK) as hits:
                await env.sweep()
            assert hits, (cond, "the mutant reached no statement")
            now = await got()
            same = [w for g, w in zip(now, want) if g == w]
            assert not same, (cond, "the mutant left these ends as the real sweep gives them", same)

        if cond == "only_pending_rows":
            await _refresh_live(env)
            await env.sweep()
            assert await got() == want, cond
            await mutant_sweep()
        else:
            await mutant_sweep()
            await _refresh_live(env)
            await env.sweep()
            assert await got() == want, cond
        assert await _ends(env, kept) == [("pending", None)] * len(kept), (cond, "a kept invite ended")
    case(monkeypatch, body)


def test_the_sweep_leaves_a_row_an_accept_holds_and_does_not_wait_for_it(monkeypatch):
    """A second session holds an expired invite's row the way an accept locks
    it (FOR NO KEY UPDATE, the hook's lock). The sweep, bounded by a lock
    timeout set in its transaction, finishes, leaves that row pending and
    ends an unlocked expired row; once the lock is released, the next sweep
    ends the held row too. Mutant: the sweep's SKIP LOCKED removed, so it
    waits on the row and its lock timeout fires."""
    assert "FOR NO KEY UPDATE" in inspect.getsource(main._InviteJoinHook.lock)

    async def body(env):
        lid, (h,) = await env.lobby("team", 1)
        x, y = await env.players(2)
        held = await env.invite(h, x, "team", lid)
        free = await env.invite(h, y, "team", lid)
        for i in (held, free):
            await env.age(i, expired_s=5)
        side = await env.side()
        await side.execute("BEGIN")
        try:
            assert await side.fetchval(
                "SELECT state FROM lobby_invites WHERE id = $1 FOR NO KEY UPDATE", held) == "pending"
            n, err = await asyncio.wait_for(_sweep_within(env, 2000), 30)
            assert err is None, err
            assert n >= 1, n
            assert await _end(env, held) == ("pending", None), "the sweep ended a row an accept holds"
            assert await _end(env, free) == ("expired", None)
            with env.rewriting(" SKIP LOCKED", "", where=_SWEEP_MARK) as hits:
                n, err = await asyncio.wait_for(_sweep_within(env, 1000), 30)
            assert hits, "the SKIP LOCKED mutant reached no statement"
            assert err is not None and "lock timeout" in err.lower(), (n, err)
            assert await _end(env, held) == ("pending", None)
        finally:
            await side.execute("ROLLBACK")
        await env.sweep()
        assert await _end(env, held) == ("expired", None)
    case(monkeypatch, body)


# -- one pending invite per lobby and invitee ------------------------------------

_INSERT_INVITE = (
    "INSERT INTO lobby_invites (mode, lobby_id, sender_player_id, invitee_player_id, kind, state,"
    "                           ended_at, expires_at)"
    " VALUES ($1, $2, $3, $4, 'invite', CAST($5 AS text),"
    "         CASE WHEN CAST($5 AS text) = 'pending' THEN NULL ELSE NOW() END,"
    "         NOW() + make_interval(mins => 10))")


async def _pending_to(env, mode, lid, p):
    return await env.conn.fetchval(
        "SELECT COUNT(*) FROM lobby_invites WHERE mode = $1 AND lobby_id = $2"
        "   AND invitee_player_id = $3 AND state = 'pending'", mode, lid, p.id)


def test_one_pending_invite_per_lobby_and_invitee_the_index_and_the_sends_answer(monkeypatch):
    """In each mode: a second pending row for the same lobby and invitee is
    refused by uq_lobby_invites_pending, whoever sent it, while an ended row
    for them and a pending row for another invitee are admitted (the index
    is partial and per invitee). A send to an invitee already invited
    answers already_invited with the pending invite's id, from the host and
    from another member alike. Mutant: the send's own duplicate check reads
    no pending row, so the index refuses the insert instead and nothing is
    written."""
    async def body(env):
        for mode in inv.MODES:
            lid, (h, m) = await env.lobby(mode, 2)
            x, z = await env.players(2)
            iid = await env.invite(h, x, mode, lid)
            with pytest.raises(asyncpg.exceptions.UniqueViolationError) as ei:
                await env.conn.execute(_INSERT_INVITE, mode, lid, m.id, x.id, "pending")
            assert ei.value.constraint_name == "uq_lobby_invites_pending", (mode, ei.value)
            await env.conn.execute(_INSERT_INVITE, mode, lid, m.id, x.id, "declined")
            await env.conn.execute(_INSERT_INVITE, mode, lid, m.id, z.id, "pending")
            want = Answer(409, {"error": "already_invited", "invite_id": str(iid)})
            for sender in (h, m):
                ans = await env.send(sender, x, mode, lid)
                assert ans == want, (mode, sender, ans)
            assert await _pending_to(env, mode, lid, x) == 1
            # The duplicate check reads no row; its clock placeholder stays in
            # the text, so the statement keeps every argument it is sent.
            with env.rewriting(re.compile(r" AND expires_at > CAST\((\$\d+|%s|%\(\w+\)s|:\w+) AS timestamptz\)"),
                               r" AND FALSE AND CAST(\1 AS timestamptz) IS NOT NULL",
                               where="SELECT id, invitee_player_id FROM lobby_invites") as hits:
                with pytest.raises(Exception) as ei:
                    await env.send(m, x, mode, lid)
            assert hits, (mode, "the duplicate-check mutant reached no statement")
            assert "uq_lobby_invites_pending" in str(ei.value), (mode, ei.value)
            assert await _pending_to(env, mode, lid, x) == 1, mode
    case(monkeypatch, body)


# -- a start ends its lobby's pending invites -------------------------------------

# Members a start needs: 2v2 and 1v2 exactly, FFA at least.
_ROSTER = {"team": 4, "ovt": 3, "ffa": main.FFA_MIN_PLAYERS}


async def _startable(env, mode):
    """A lobby of `mode` with two pending invites, one from its host and one
    from a member, then its roster filled to what a start needs. Returns
    (lobby id, host, member, [the two invites])."""
    n = _ROSTER[mode]
    lid, ps = await env.lobby(mode, n if mode == "ffa" else n - 1)
    h, m = ps[0], ps[1]
    ids = [await env.invite(h, await env.player(), mode, lid),
           await env.invite(m, await env.player(), mode, lid)]
    if mode != "ffa":
        ans = await env.join(mode, await env.player(), lid)
        assert ans.status == 200, (mode, ans)
    await env.fresh(mode, lid)
    return lid, h, m, ids


@pytest.mark.parametrize("mode", inv.MODES)
def test_a_start_ends_its_lobbys_pending_invites_as_lobby_started(monkeypatch, mode):
    """The mode's start path ends every pending invite of the lobby as void
    with lobby_started, in its own transaction. Mutant: the start's ending
    call removed (the start still goes through; the invites stay pending)."""
    async def body(env):
        lid, h, _m, ids = await _startable(env, mode)
        ans = await _start(env, mode, h)
        assert ans.status == 200, ans
        assert await env.lobby_status(mode, lid) != "open"
        assert await _ends(env, ids) == [("void", "lobby_started")] * 2

        lid, h, _m, ids = await _startable(env, mode)
        calls = []

        async def _no_end(db, mode_, lobby_id, why):
            calls.append((mode_, str(lobby_id), why))
            return []
        with _swap(main, "_invite_end_lobby", _no_end):
            ans = await _start(env, mode, h)
        assert ans.status == 200, ans
        assert calls == [(mode, str(lid), "lobby_started")], calls
        assert await env.lobby_status(mode, lid) != "open"
        assert await _ends(env, ids) == [("pending", None)] * 2, "the start ended invites without its call"
    case(monkeypatch, body)


@pytest.mark.parametrize("mode", ("team", "ovt"))
def test_a_start_refused_after_a_banned_seats_eviction_ends_that_seats_invites(monkeypatch, mode):
    """_lobby_start_common removes a banned member, the roster is then short,
    and the refusal commits the eviction: the removed seat's pending invite
    ends void with sender_left, in the same commit, and the host's invite
    stays pending. Mutant: that ending call removed (the seat still goes;
    its invite stays pending)."""
    async def body(env):
        n = _ROSTER[mode]
        want = Answer(409, "Need exactly %d players to start (%d in the lobby)" % (n, n - 1))
        for mutant in (False, True):
            lid, h, m, (hosts, mine) = await _startable(env, mode)
            await _ban(env, m)
            calls = []

            async def _no_end(db, mode_, lobby_id, player_ids):
                calls.append(sorted(str(p) for p in player_ids))
                return []
            if mutant:
                with _swap(main, "_invite_end_departed", _no_end):
                    ans = await _start(env, mode, h)
            else:
                ans = await _start(env, mode, h)
            assert ans == want, (mutant, ans)
            assert await _seat(env, mode, m) is None, (mutant, "the banned seat was not evicted")
            assert await env.lobby_status(mode, lid) == "open"
            assert await _end(env, hosts) == ("pending", None), mutant
            if mutant:
                assert calls == [[str(m.id)]], calls
                assert await _end(env, mine) == ("pending", None), "the invite ended without the call"
            else:
                assert await _end(env, mine) == ("void", "sender_left")
    case(monkeypatch, body)


# -- removals that end no invite rely on the sweep and accept's re-check ----------
#
# The janitor's stale and husk prunes and its lobby-not-open deletes do not
# take the lobby lock, so they may leave a pending invite behind: accept
# re-checks the sender's live seat itself, and the sweep ends the rest. The
# three queue polls' lease-expiry branch ends no invite either (note 13 (m)):
# team_queue_poll, ovt_queue_poll and FFA's body _ffa_queue_poll_inner are
# walked by test_a1_identity_formation.py under a frozen grammar that an
# ending call there does not fit.

@pytest.mark.parametrize("mode", inv.MODES)
def test_a_seat_or_lobby_gone_without_an_ending_is_caught_by_accept_and_the_sweep(monkeypatch, mode):
    """(i) The sender's seat row deleted directly, nothing ended: an accept
    answers invite_void (sender_left), seats nobody and ends the invite; the
    next sweep ends the sender's other pending invite. (ii) A lobby's status
    set past open directly: the sweep ends its invite as lobby_closed.
    Mutants: accept's live-sender re-check removed (the accept seats the
    invitee); the sweep's sender condition removed; its lobby condition
    removed (each leaves the invite pending)."""
    async def body(env):
        q = inv.QUEUE_TABLE[mode]
        lid, (h, m) = await env.lobby(mode, 2)
        x, y, z = await env.players(3)
        ix, iy, iz = [await env.invite(m, p, mode, lid) for p in (x, y, z)]
        await env.fresh(mode, lid)
        await env.conn.execute("DELETE FROM %s WHERE player_id = $1 AND series_id = $2" % q, m.id, lid)
        assert await _ends(env, [ix, iy, iz]) == [("pending", None)] * 3

        # (i) accept's own re-check
        got = await env.accept(x, ix)
        assert got == Answer(409, _VOID), got
        assert str(x.id) not in await _member_ids(env, mode, lid)
        assert await _end(env, ix) == ("void", "sender_left")
        calls = []

        def _no_sender_check(self, live):
            calls.append(1)
            if self.row is None:
                raise HTTPException(status_code=404, detail="invite_not_found")
            main._invite_refuse_ended(self.row, void_as_answered=False)
        with _swap(main._InviteJoinHook, "recheck", _no_sender_check):
            got = await env.accept(y, iy)
        assert calls, "the re-check mutant was not reached"
        assert got.status == 200 and got != Answer(409, _VOID), got
        assert str(y.id) in await _member_ids(env, mode, lid), "the mutant accept seated nobody"

        # (i) the sweep's sender condition
        await env.fresh(mode, lid)
        with env.rewriting(_SENDER_SEAT, "THEN TRUE OR EXISTS (SELECT 1 FROM", where=_SWEEP_MARK) as hits:
            await env.sweep()
        assert hits
        assert await _end(env, iz) == ("pending", None), "the sender mutant still ended the invite"
        await env.sweep()
        assert await _end(env, iz) == ("void", "sender_left")

        # (ii) the sweep's lobby condition
        l2, (h2,) = await env.lobby(mode, 1)
        iw = await env.invite(h2, await env.player(), mode, l2)
        await env.fresh(mode, l2)
        await _set_status(env, mode, l2, "canceled")
        with env.rewriting(_LOBBY_OPEN, "TRUE", where=_SWEEP_MARK) as hits:
            await env.sweep()
        assert hits
        assert await _end(env, iw) == ("pending", None), "the lobby mutant still ended the invite"
        await env.sweep()
        assert await _end(env, iw) == ("void", "lobby_closed")
    case(monkeypatch, body)


# Every statement, for a statement log (a rewrite that changes nothing); and
# a write to lobby_invites.
_EVERY = re.compile(r"\A")
_INVITE_WRITE = re.compile(r"\b(?:UPDATE|INSERT INTO|DELETE FROM)\s+lobby_invites\b")


# Each mode's queue poll, called as its route calls it.
_QUEUE_POLL = {
    "team": lambda sid: (lambda db: main.team_queue_poll(sid, Req(sid), db=db, rdm=0)),
    "ovt": lambda sid: (lambda db: main.ovt_queue_poll(sid, Req(sid), db=db, rdm=0)),
    "ffa": lambda sid: (lambda db: main.ffa_queue_poll(sid, Req(sid), db=db)),
}


@pytest.mark.parametrize("mode", ("team", "ovt", "ffa"))
def test_an_expired_lobby_seat_ends_no_invite_and_accept_and_the_sweep_end_them(monkeypatch, mode):
    """Note 13 (m). The member's seat lease is gone, so the mode's own poll
    (team_queue_poll, ovt_queue_poll; ffa_queue_poll, whose body
    _ffa_queue_poll_inner holds the branch) ends the seat, its row and its
    lease, and ends no invite: its statements include the seat's delete and no
    write to lobby_invites, the member's three invites stay pending, and no
    invitee's revision moves. Then an accept answers invite_void
    (sender_left), seats nobody and ends its invite, and the next sweep ends
    another and bumps its invitee's revision. Negative control: before the
    poll, with the sender's fresh 'lobby' row in place, the sweep keeps all
    three pending. Mutants: accept's live-sender re-check removed (the
    accept seats the invitee); the sweep's sender condition removed (the
    invite stays pending)."""
    async def body(env):
        q = inv.QUEUE_TABLE[mode]
        lid, (h, m) = await env.lobby(mode, 2)
        x, y, z = await env.players(3)
        ix, iy, iz = [await env.invite(m, p, mode, lid) for p in (x, y, z)]
        await env.fresh(mode, lid)

        # negative control: the sender's fresh 'lobby' row keeps the invites
        await env.sweep()
        assert await _ends(env, [ix, iy, iz]) == [("pending", None)] * 3, "the sweep ended a live sender's invite"

        # the poll, with the seat's lease gone
        await env.conn.execute("DELETE FROM queue_leases WHERE player_id = $1", m.id)
        revs = [await env.rev(p) for p in (x, y, z)]
        with env.rewriting(_EVERY, "") as log:
            ans = await env.call(_QUEUE_POLL[mode](m.sid))
        status = ans.body.get("status") if isinstance(ans.body, dict) else getattr(ans.body, "status", None)
        assert ans.status == 200 and status == "lobby_closed", ans
        assert await _seat(env, mode, m) is None, "the expired seat was not ended"
        assert [s for s in log if ("DELETE FROM %s" % q) in s], "the poll's seat delete is not in its statements"
        assert not [s for s in log if _INVITE_WRITE.search(s)], "the poll wrote to lobby_invites"
        assert await _ends(env, [ix, iy, iz]) == [("pending", None)] * 3, "the poll ended an invite"
        assert [await env.rev(p) for p in (x, y, z)] == revs, "the poll bumped an invitee's revision"

        # accept's own re-check
        got = await env.accept(x, ix)
        assert got == Answer(409, _VOID), got
        assert str(x.id) not in await _member_ids(env, mode, lid)
        assert await _end(env, ix) == ("void", "sender_left")
        calls = []

        def _no_sender_check(self, live):
            calls.append(1)
            if self.row is None:
                raise HTTPException(status_code=404, detail="invite_not_found")
            main._invite_refuse_ended(self.row, void_as_answered=False)
        with _swap(main._InviteJoinHook, "recheck", _no_sender_check):
            got = await env.accept(y, iy)
        assert calls, "the re-check mutant was not reached"
        assert got.status == 200 and got != Answer(409, _VOID), got
        assert str(y.id) in await _member_ids(env, mode, lid), "the mutant accept seated nobody"

        # the sweep's sender condition
        await env.fresh(mode, lid)
        with env.rewriting(_SENDER_SEAT, "THEN TRUE OR EXISTS (SELECT 1 FROM", where=_SWEEP_MARK) as hits:
            await env.sweep()
        assert hits
        assert await _end(env, iz) == ("pending", None), "the sender mutant still ended the invite"
        rz = await env.rev(z)
        await env.sweep()
        assert await _end(env, iz) == ("void", "sender_left")
        assert await env.rev(z) > rz, "the sweep's ending did not bump the invitee's revision"
    case(monkeypatch, body)
