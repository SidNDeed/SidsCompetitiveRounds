"""FFA mid-game readmission, server half (design V3: P4.1 the hold, P4.2 the
readmission route and discovery, P4.6 the flag, P4.8 the epoch version 2,
P4.9 spectators during a hold, P5 the attempt rows), against a local
PostgreSQL through cf_pg (one case schema per case, 355 then 378 applied
whole by cf_pg.build).

Every assertion names its control in the first element of its message
("T4.1 witness", ...): the readmit mutation runner (rdm_controls.py) counts a
mutant only when it turns exactly the named assertion red, and runs each
mutant on a copy of the tree, never on a tracked file.
"""

import asyncio
import datetime as _dt
import hashlib
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import cf_asm  # noqa: E402
import cf_pg  # noqa: E402
import main  # noqa: E402
import test_ffa_assembly_pg as A  # noqa: E402

RDM_CAPS = "ffa_asm1,ffa_adm1,ffa_rdm1"


def run_env(monkeypatch, body):
    A.run_env(monkeypatch, body, prefix="rdm")


# -- fixtures -----------------------------------------------------------------

async def _rdm_lobby(env, n=4, *, t=30.0, flag=True):
    """A started (full-grant) lobby of n seats, each bound to actor 1 + slot,
    with the readmission flag as given."""
    lob = await env.lobby(n, admission=True, t=t)
    await env.set_lobby(lob, readmit_v1=flag)
    await A._full_grant(env, lob, t)
    return lob


async def _present(env, lob, slot, t):
    """The seat's own census through the route at lobby age t, listing every
    seat (the last server evidence of its presence)."""
    await env.at(lob, t)
    return await env.census_of(lob, slot, list(range(lob.n)))


async def _witness_gone(env, lob, gone, t, *, witnesses=None):
    """At lobby age t: witnesses[1]'s stored census omits `gone`, then
    witnesses[0]'s census through the route omits it too (the gone rule's
    census trigger, two current witnesses).  The default witnesses are the
    two lowest slots other than `gone` ((0, 2) for the usual gone=1): a seat
    never witnesses its own departure, so a census it sends is not one of
    the two the rule counts."""
    if witnesses is None:
        witnesses = tuple(s for s in range(lob.n) if s != gone)[:2]
    assert gone not in witnesses, ("setup: the gone seat is its own witness", gone, witnesses)
    await env.at(lob, t)
    present = [s for s in range(lob.n) if s != gone]
    await A._omit(env, lob, [witnesses[1]], gone)
    return await env.census_of(lob, witnesses[0], present)


async def _held(env, n=4, gone=1, *, t_present=50.0, t_gone=70.0, flag=True):
    lob = await _rdm_lobby(env, n, flag=flag)
    await _present(env, lob, gone, t_present)
    await _witness_gone(env, lob, gone, t_gone)
    return lob


async def _rows(env, table, lob, slot=None):
    if slot is None:
        rs = await env.conn.fetch("SELECT * FROM %s WHERE lobby_id = $1 ORDER BY 1, 2, 3" % table,
                                  lob.lid)
    else:
        rs = await env.conn.fetch(
            "SELECT * FROM %s WHERE lobby_id = $1 AND player_id = $2 ORDER BY 3" % table,
            lob.lid, lob.pids[slot])
    return [dict(r) for r in rs]


async def _attempts(env, lob, slot):
    return [(r["n"], r["kind"], r["outcome"], r["reason"])
            for r in await env.conn.fetch(
                "SELECT * FROM ffa_readmit_attempts WHERE lobby_id = $1 AND player_id = $2"
                " ORDER BY n, attempt_no", lob.lid, lob.pids[slot])]


def _rdm_lines(env, needle=""):
    return [ln for ln in env.lines if ln.startswith("[FFA-RDM]") and needle in ln]


class _Fields(cf_asm.Answer):
    """A route answer whose missing field reads None, so an assertion on a
    field the answer lacks (a success where a refusal was required) fails
    on its own named message instead of a KeyError inside the read."""

    def __getitem__(self, k):
        if isinstance(self.body, dict):
            return self.body.get(k)
        return super().__getitem__(k)


def _fields(ans):
    return _Fields(ans.status, ans.body)


async def _readmit(env, lob, slot, step, n, *, actor=None, region=None, game=None,
                   steam_id=None, lobby_id=None):
    req = main._AsmReadmitReq(steam_id=steam_id or lob.sids[slot], step=step, n=n, actor=actor,
                              region=region if region is not None
                              else (lob.region if actor is not None else None),
                              game=game, client_ms=100)

    async def go():
        async with env.sm() as db:
            return await main.ffa_lobby_readmit(lobby_id or lob.lid, req, None, db=db)
    return _fields(await env._call(go))


async def _offer(env, lob, slot):
    async def go():
        async with env.sm() as db:
            return await main.ffa_readmit_offer(None, steam_id=lob.sids[slot], db=db)
    return _fields(await env._call(go))


async def _corroborate(env, lob, slot, actor, *, witness=0, kept=True):
    """A fresh stored census of `witness` listing every other seat and
    (slot, actor) (kept unless kept=False), from the lobby's region."""
    entries = [(s, 1 + s, 1, 1) for s in range(lob.n) if s != slot]
    entries.append((slot, actor, 1, 1 if kept else 0))
    await env.census_row(lob, witness, entries)


async def _claim_bind(env, lob, slot, n, actor):
    a = await _readmit(env, lob, slot, "claim", n)
    assert a["status"] == "claimed", ("T4.5 claim", a)
    await _corroborate(env, lob, slot, actor)
    b = await _readmit(env, lob, slot, "bind", n, actor=actor)
    return a, b


def _chain(rows, lobby8):
    prev = "0"
    for r in rows:
        if int(r["chain_v"]) == 1:
            prev = main._ffa_epoch_chain(prev, lobby8, r["epoch_no"], r["slot"], r["actor_nr"])
        else:
            prev = main._ffa_epoch_chain_v2(prev, lobby8, r["epoch_no"], r["slot"],
                                            r["actor_nr"], r["kind"], r["game"], r["verifier"])
        if prev != r["chain"]:
            return False
    return True


# -- S2: the lobby flag at lock (P4.6) ---------------------------------------

def test_t2_6_the_flag_is_written_at_lock_and_never_rederived(monkeypatch):
    """T2.6 (server half): a lobby whose every member advertises ffa_rdm1
    locks readmit_v1 true and its lock payload carries readmit: 1; a mixed
    lobby locks false; after the incompatible member drops, the flag the one
    reader returns is still false, and the full lobby's is still true after
    one of its members drops."""
    async def body(env):
        out = {}
        for name, caps in (("all", [RDM_CAPS] * 4),
                           ("mixed", [RDM_CAPS] * 3 + ["ffa_asm1,ffa_adm1"])):
            lob = await A._open_lobby(env, 4, caps)
            for pid in lob.pids:
                await env.conn.execute(
                    "INSERT INTO ffa_g3_seats (player_id, expires_at)"
                    " VALUES ($1, now() + interval '1 hour')", pid)
            a = await A._start(env, main, lob)
            assert a.status == 200, ("T2.6 start", name, a)
            out[name] = lob
        row = await env.lobby_row(out["all"])
        assert row["readmit_v1"] is True, ("T2.6 all", row["readmit_v1"])
        row = await env.lobby_row(out["mixed"])
        assert row["readmit_v1"] is False, ("T2.6 mixed", row["readmit_v1"])
        p = await env.poll(out["all"], 0)
        assert p.get("readmit") == 1, ("T2.6 payload", p.body)
        p = await env.poll(out["mixed"], 0)
        assert "readmit" not in (p.body or {}), ("T2.6 payload mixed", p.body)
        # The incompatible member (sorted slot of the ffa_adm1-only caps) drops:
        # its queue row and lease go, as a leave leaves them.
        mixed = out["mixed"]
        odd = mixed.pids[3]
        await env.conn.execute("DELETE FROM ffa_queue WHERE player_id = $1", odd)
        await env.conn.execute("DELETE FROM queue_leases WHERE player_id = $1", odd)
        await env.conn.execute(
            "UPDATE ffa_lobbies SET departed_ids = array_append(departed_ids, $2) WHERE id = $1",
            mixed.lid, odd)
        full = out["all"]
        await env.conn.execute("DELETE FROM ffa_queue WHERE player_id = $1", full.pids[3])
        async with env.sm() as db:
            for lob, want in ((mixed, False), (full, True)):
                lrow = (await db.execute(main.text("SELECT * FROM ffa_lobbies WHERE id = :lid"),
                                         {"lid": lob.lid})).mappings().first()
                got = await main._asm_readmit_on(db, dict(lrow))
                assert got is want, ("T2.6 after drop", want, got)
            await db.rollback()
    run_env(monkeypatch, body)


# -- S4: the hold, its clock, its clears and the lapse (P4.1) -----------------

def test_t4_1_the_hold_writer_and_its_predicates(monkeypatch):
    """T4.1: a hold is written on the witness path and on the involuntary
    leave path of a flagged active lobby, with its readmission row and its
    lease gone, the departure postponed; never for in_room_exit, a departed
    seat, a flag-false lobby, or a window under 15 s."""
    async def body(env):
        lob = await _held(env)
        s = await env.seat(lob, 1)
        assert s["hold_n"] == 1 and s["hold_until"] is not None, ("T4.1 witness", s["hold_n"])
        rows = await _rows(env, "ffa_seat_readmissions", lob, 1)
        assert [(r["n"], r["hold_until"]) for r in rows] == [(1, s["hold_until"])], \
            ("T4.1 readmission row", rows)
        assert await env.lease(lob, 1) is None, ("T4.1 lease", await env.lease(lob, 1))
        assert list((await env.lobby_row(lob))["departed_ids"] or []) == [], "T4.1 not departed"
        assert _rdm_lines(env, "held slot=1 n=1"), ("T4.1 line", env.lines[-5:])

        # The involuntary leave path: the trailing leave of a drop.
        lob = await _rdm_lobby(env)
        await _present(env, lob, 2, 50.0)
        await env.at(lob, 70.0)
        await A._omit(env, lob, [0, 1], 2)
        await env.leave(lob, 2, cause="in_room_timeout")
        s = await env.seat(lob, 2)
        assert s["hold_n"] == 1 and s["gone_path"] == "leave", ("T4.1 leave", s["hold_n"],
                                                                 s["gone_path"])
        assert list((await env.lobby_row(lob))["departed_ids"] or []) == [], \
            ("T4.1 leave departure postponed",)

        # in_room_exit: no hold, the departure as today.
        lob = await _rdm_lobby(env)
        await _present(env, lob, 2, 50.0)
        await env.at(lob, 70.0)
        await A._omit(env, lob, [0, 1], 2)
        await env.leave(lob, 2, cause="in_room_exit")
        s = await env.seat(lob, 2)
        assert s["hold_n"] is None, ("T4.1 in_room_exit", s["hold_n"])
        assert list((await env.lobby_row(lob))["departed_ids"]) == [lob.pids[2]], \
            ("T4.1 in_room_exit departs",)

        # A departed seat.
        lob = await _rdm_lobby(env)
        await _present(env, lob, 1, 50.0)
        await env.set_lobby(lob, departed_ids=[lob.pids[1]])
        await _witness_gone(env, lob, 1, 70.0)
        assert (await env.seat(lob, 1))["hold_n"] is None, ("T4.1 departed",)

        # A flag-false lobby.
        lob = await _held(env, flag=False)
        s = await env.seat(lob, 1)
        assert s["gone_game"] is not None and s["hold_n"] is None, ("T4.1 flag false",
                                                                    s["hold_n"])

        # A window under 15 s: present at 50, gone at 160 (10 s left).
        lob = await _held(env, t_gone=160.0)
        s = await env.seat(lob, 1)
        assert s["gone_game"] is not None and s["hold_n"] is None, ("T4.1 window", s["hold_n"])
        assert _rdm_lines(env, "no_hold slot=1 why=window"), ("T4.1 window line",)
    run_env(monkeypatch, body)


def test_t4_2_the_anchor_is_the_last_presence(monkeypatch):
    """T4.2: withheld, reordered and post-expiry witnesses cannot move the
    present_at + 120 s deadline; a vetoing census cannot move it either.  The
    clock is the transaction clock: with the application clock behind it a
    window that clock calls too short writes no hold, and held_at is it."""
    async def body(env):
        lob = await _rdm_lobby(env)
        await _present(env, lob, 1, 50.0)
        present_at = (await env.seat(lob, 1))["present_at"]
        assert present_at == await env.ts(lob, 50.0), ("T4.2 present_at", present_at)
        # A vetoing census (lists the subject) at 60, then the omissions late.
        await env.at(lob, 60.0)
        await env.census_of(lob, 0, list(range(lob.n)))
        await _witness_gone(env, lob, 1, 100.0)
        # env.at moves the lobby's whole history, so stamps are compared as
        # offsets from the lobby's creation (ts(lob, t) in the current frame).
        s = await env.seat(lob, 1)
        p50 = await env.ts(lob, 50.0)
        assert s["hold_anchor_at"] == p50 and s["present_at"] == p50, \
            ("T4.2 anchor", s["hold_anchor_at"] - await env.ts(lob, 0.0))
        assert s["hold_until"] == await env.ts(lob, 170.0), \
            ("T4.2 deadline", s["hold_until"] - await env.ts(lob, 0.0))

        # Withhold the second witness, then deliver the two real route
        # receipts in either order.  Their client seen-age values and receipt
        # order move neither the server presence anchor nor age-170 deadline.
        for first, second in ((0, 2), (2, 0)):
            lob = await _rdm_lobby(env)
            await _present(env, lob, 1, 50.0)
            present = [0, 2, 3]
            await env.at(lob, 91.0)
            await env.census_of(lob, first, present, seen_age_ms=90000)
            withheld = await env.seat(lob, 1)
            assert withheld["hold_n"] is None and withheld["gone_game"] is None, \
                ("T4.2 withheld witness", first, withheld["hold_n"], withheld["gone_game"])
            await env.at(lob, 100.0)
            await env.census_of(lob, second, present, seen_age_ms=60000)
            first_row, second_row = await env.seat(lob, first), await env.seat(lob, second)
            assert second_row["census_seen_at"] < first_row["census_seen_at"], \
                ("T4.2 reordered witness", first, second,
                 first_row["census_seen_at"], second_row["census_seen_at"])
            s = await env.seat(lob, 1)
            assert s["hold_anchor_at"] == await env.ts(lob, 50.0) \
                and s["hold_until"] == await env.ts(lob, 170.0), \
                ("T4.2 reordered deadline", first, second,
                 s["hold_anchor_at"], s["hold_until"])

        # A genuine quorum only after the shared deadline still records the
        # gone fact, but cannot create either a hold or readmission row.
        lob = await _rdm_lobby(env)
        await _present(env, lob, 1, 50.0)
        await env.at(lob, 171.0)
        await env.census_of(lob, 0, [0, 2, 3], seen_age_ms=60000)
        await env.census_of(lob, 2, [0, 2, 3], seen_age_ms=60000)
        s = await env.seat(lob, 1)
        assert s["gone_game"] is not None and s["hold_n"] is None \
            and await _rows(env, "ffa_seat_readmissions", lob, 1) == [], \
            ("T4.2 post-edge no hold", s["gone_game"], s["hold_n"])

        # Skew A: the transaction clock 60 s ahead of the application clock.
        lob = await _rdm_lobby(env)
        await _present(env, lob, 1, 50.0)
        await env.at(lob, 100.0)
        env.now = env.now + _dt.timedelta(seconds=60)
        await A._omit(env, lob, [2], 1)
        await env.census_of(lob, 0, [0, 2, 3])
        s = await env.seat(lob, 1)
        assert s["gone_game"] is not None and s["hold_n"] is None, ("T4.2 clock", s["hold_n"])

        # Skew B: a hold written; held_at is the transaction clock.
        lob = await _rdm_lobby(env)
        await _present(env, lob, 1, 50.0)
        await env.at(lob, 80.0)
        env.now = env.now + _dt.timedelta(seconds=20)
        await A._omit(env, lob, [2], 1)
        await env.census_of(lob, 0, [0, 2, 3])
        rows = await _rows(env, "ffa_seat_readmissions", lob, 1)
        assert len(rows) == 1 and rows[0]["held_at"] == env.now, \
            ("T4.2 held_at", [r["held_at"] for r in rows], env.now)
    run_env(monkeypatch, body)


def test_t4_3_old_clears_leave_the_hold(monkeypatch):
    """T4.3: the clears that run beside a live hold (a poll, a janitor pass,
    the drop's own trailing timeout leave, another witness census) leave the
    hold unchanged, and nothing mirrors it into ffa_queue.held_until or
    held_lobby."""
    async def body(env):
        lob = await _held(env)
        keys = ("hold_n", "hold_anchor_at", "hold_until")

        async def rel():
            # Offsets from the lobby's creation: env.at moves the history.
            s_, t0 = await env.seat(lob, 1), await env.ts(lob, 0.0)
            return {k: (s_[k] if k == "hold_n" or s_[k] is None else s_[k] - t0) for k in keys}
        before = await rel()
        q = await env.queue_row(lob, 1)
        assert q is None or (q["held_until"] is None and q["held_lobby"] is None), \
            ("T4.3 queue mirror", q and q["held_until"])
        await env.poll(lob, 1)
        await A._janitor_tick(env)
        await env.leave(lob, 1, cause="in_room_timeout")
        await env.at(lob, 75.0)
        await env.census_of(lob, 0, [0, 2, 3])
        after = await rel()
        assert after == before and before["hold_n"] == 1, ("T4.3 hold unchanged", after, before)
        q = await env.queue_row(lob, 1)
        assert q is None or (q["held_until"] is None and q["held_lobby"] is None), \
            ("T4.3 queue mirror", q and q["held_until"])
    run_env(monkeypatch, body)


def test_t4_3b_the_trailing_timeout_leave_reaches_the_leave_guard(monkeypatch):
    """T4.3b: on a held seat whose queue row is still ready_join, the leave
    route runs the leave plan, and the plan asks _rdm_trailing_drop about the
    cause. The drop's own trailing in_room_timeout leave keeps the hold. A
    chosen in_room_exit through the same route ends the hold. T4.3 does not
    check that the guard was reached, so this test does (control B10)."""
    async def body(env):
        seen = []
        real = main._rdm_trailing_drop

        def spy(cause):
            out = real(cause)
            seen.append((cause, out))
            return out
        monkeypatch.setattr(main, "_rdm_trailing_drop", spy)
        for cause, kept in (("in_room_timeout", True), ("in_room_exit", False)):
            lob = await _held(env)
            q = await env.queue_row(lob, 1)
            assert q is not None and q["status"] == "ready_join" \
                and q["series_id"] == lob.lid, ("T4.3b queue row", cause, q)
            before = (await env.seat(lob, 1))["hold_n"]
            del seen[:]
            ans = await env.leave(lob, 1, cause=cause)
            assert ans.status == 200, ("T4.3b leave answered", cause, ans.status, ans.body)
            s = await env.seat(lob, 1)
            if kept:
                assert before == 1 and s["hold_n"] == 1 and s["hold_until"] is not None, \
                    ("T4.3b hold kept", s["hold_n"], s["hold_until"])
                assert await _attempts(env, lob, 1) == [], ("M2 trailing no decline row",)
            else:
                assert before == 1 and s["hold_n"] is None, ("T4.3b chosen exit ends", s["hold_n"])
                assert await _attempts(env, lob, 1) == [(1, "decline", "ok", None)], \
                    ("M2 implicit decline row", await _attempts(env, lob, 1))
            assert seen == [(cause, kept)], ("T4.3b guard reached", cause, seen)
    run_env(monkeypatch, body)


def test_m2_decline_checks_lifecycle_and_writes_one_success(monkeypatch):
    """M2: every successful decline writes exactly one ok attempt in the
    hold-ending transaction; expiry and closure refuse without that row, and
    automatic lapse writes no attempt."""
    async def body(env):
        live = await _held(env)
        ans = await _readmit(env, live, 1, "decline", 1)
        row = (await _rows(env, "ffa_seat_readmissions", live, 1))[0]
        attempts = await _attempts(env, live, 1)
        assert ans["status"] == "declined" and row["refused_reason"] == "declined" \
            and attempts == [(1, "decline", "ok", None)], \
            ("M2 explicit decline row", ans.body, row["refused_reason"], attempts)

        expired = await _held(env)
        await env.at(expired, 171.0)
        ans = await _readmit(env, expired, 1, "decline", 1)
        row = (await _rows(env, "ffa_seat_readmissions", expired, 1))[0]
        attempts = await _attempts(env, expired, 1)
        assert ans["reason"] == "hold_lapsed" and row["lapsed_at"] is not None \
            and not any(a[1:3] == ("decline", "ok") for a in attempts), \
            ("M2 expired decline", ans.body, row["lapsed_at"], attempts)

        closed = await _held(env)
        await env.set_lobby(closed, status="completed")
        ans = await _readmit(env, closed, 1, "decline", 1)
        row = (await _rows(env, "ffa_seat_readmissions", closed, 1))[0]
        attempts = await _attempts(env, closed, 1)
        assert ans["reason"] == "lobby_closed" and row["refused_at"] is None \
            and row["lapsed_at"] is None \
            and not any(a[1:3] == ("decline", "ok") for a in attempts), \
            ("M2 closed decline", ans.body, row["refused_at"], attempts)

        automatic = await _held(env)
        await env.at(automatic, 171.0)
        await A._janitor_tick(env)
        row = (await _rows(env, "ffa_seat_readmissions", automatic, 1))[0]
        assert row["lapsed_at"] is not None and await _attempts(env, automatic, 1) == [], \
            ("M2 automatic lapse no row", row["lapsed_at"],
             await _attempts(env, automatic, 1))
    run_env(monkeypatch, body)


def test_t4_4_the_lapse_order_and_one_commit(monkeypatch):
    """T4.4: the lapse takes the lobby row before the lobby's queue rows; a
    lapse racing a bind ends in exactly one outcome with no failure line; two
    lobbies may lapse while a claim runs; a failure between the clear and the
    departure leaves the hold whole (one commit)."""
    async def body(env):
        order = []
        real_slot, real_rows = main._ffa_lock_lobby_slot, main._ffa_lock_queue_rows

        async def slot_spy(db, lid):
            order.append("lobby")
            return await real_slot(db, lid)

        async def rows_spy(db, ids):
            order.append("queue")
            return await real_rows(db, ids)
        lob = await _held(env)
        await env.at(lob, 200.0)
        env.mp.setattr(main, "_ffa_lock_lobby_slot", slot_spy)
        env.mp.setattr(main, "_ffa_lock_queue_rows", rows_spy)
        await A._janitor_tick(env)
        env.mp.setattr(main, "_ffa_lock_lobby_slot", real_slot)
        env.mp.setattr(main, "_ffa_lock_queue_rows", real_rows)
        assert "queue" in order and order.index("lobby") < order.index("queue"), \
            ("T4.4 order", order)
        s = await env.seat(lob, 1)
        r = (await _rows(env, "ffa_seat_readmissions", lob, 1))[0]
        assert s["hold_n"] is None and r["lapsed_at"] is not None, ("T4.4 lapsed", s["hold_n"])

        # A lapse racing a bind at the deadline: one outcome.
        lob = await _held(env)
        await env.at(lob, 100.0)
        a = await _readmit(env, lob, 1, "claim", 1)
        assert a["status"] == "claimed", ("T4.4 claim", a)
        await _corroborate(env, lob, 1, 9)
        await env.at(lob, 170.0)
        await env.conn.execute(
            "UPDATE ffa_assembly_seats SET census_at = $3 WHERE lobby_id = $1 AND slot = $2",
            lob.lid, 0, env.now)

        async def bind():
            return await _readmit(env, lob, 1, "bind", 1, actor=9)
        await asyncio.gather(bind(), A._janitor_tick(env))
        r = (await _rows(env, "ffa_seat_readmissions", lob, 1))[0]
        outcomes = [r["bound_at"] is not None, r["lapsed_at"] is not None]
        assert sum(outcomes) == 1, ("T4.4 one outcome", outcomes)
        assert not _rdm_lines(env, "lapse failed"), ("T4.4 no failure", _rdm_lines(env, "failed"))

        # Two callers whose unlocked queue husks point at each other's lobby
        # still join one global UUID order before either authoritative reread.
        left, right = await _held(env), await _held(env)
        await env.conn.execute("DELETE FROM queue_leases WHERE player_id = ANY($1::uuid[])",
                               [left.pids[1], right.pids[1]])
        await env.conn.execute(
            "UPDATE ffa_queue SET series_id = $2, status = 'ready_join' WHERE player_id = $1",
            left.pids[1], right.lid)
        await env.conn.execute(
            "UPDATE ffa_queue SET series_id = $2, status = 'ready_join' WHERE player_id = $1",
            right.pids[1], left.lid)
        locked = []
        real_ordered = main._lock_queue_rows_ordered

        async def ordered_spy(db, table, ids):
            if table == "ffa_queue":
                locked.append(set(ids))
            return await real_ordered(db, table, ids)

        env.mp.setattr(main, "_lock_queue_rows_ordered", ordered_spy)
        # return_exceptions: the defect this row proves is the ABBA itself.
        # Without the caller in the sorted set, PostgreSQL aborts one claim
        # with 40P01 (a bounded wait that ends in an exception, never an
        # answer), so the deadlock is reported on THIS row's tag rather than
        # escaping the test as an unnamed error.
        answers = await asyncio.wait_for(asyncio.gather(
            _readmit(env, left, 1, "claim", 1),
            _readmit(env, right, 1, "claim", 1), return_exceptions=True), 10.0)
        env.mp.setattr(main, "_lock_queue_rows_ordered", real_ordered)
        callers = {left.pids[1], right.pids[1]}
        failed = [repr(a) for a in answers if isinstance(a, BaseException)]
        assert not failed and len(locked) == 2 and all(callers <= ids for ids in locked), \
            ("T4.4 caller sorted", failed, locked, callers)
        assert all(a.status == 200 and a["reason"] == "other_lobby" for a in answers), \
            ("T4.4 crossed husks bounded", [(a.status, a.body) for a in answers])

        # Two expired lobbies lapse concurrently while a real claim contends
        # with one of them.  Each hold has one terminal outcome and no partial
        # bound/failed residue, whichever lobby-lock winner runs first.
        first, second = await _held(env), await _held(env)
        await env.at(first, 200.0)
        await env.at(second, 200.0)

        async def lapse(lob):
            async with env.sm() as db:
                return await main._rdm_lapse_lobby(db, lob.lid)

        l1, l2, claim = await asyncio.wait_for(asyncio.gather(
            lapse(first), lapse(second), _readmit(env, first, 1, "claim", 1)), 20.0)
        assert l1[0] in ("done", "busy") and l2 == ("done", 1) \
            and claim.status == 200 and claim["reason"] in ("hold_lapsed", "not_held"), \
            ("T4.4 two-lobby bounded", l1, l2, claim.status, claim.body)
        for lob in (first, second):
            seat = await env.seat(lob, 1)
            row = (await _rows(env, "ffa_seat_readmissions", lob, 1))[0]
            assert seat["hold_n"] is None and row["lapsed_at"] is not None \
                and row["bound_at"] is None and row["refused_at"] is None, \
                ("T4.4 terminal hold", str(lob.lid), seat["hold_n"], dict(row))
        assert not _rdm_lines(env, "lapse failed"), \
            ("T4.4 two-lobby no failure", _rdm_lines(env, "failed"))

        # A failure between the clear and the departure: nothing commits.
        lob = await _rdm_lobby(env)
        await _present(env, lob, 2, 50.0)
        await env.at(lob, 70.0)
        await A._omit(env, lob, [0, 1], 2)
        await env.leave(lob, 2, cause="in_room_timeout")
        await env.at(lob, 200.0)

        async def boom(ctx, subject):
            raise RuntimeError("crash between")
        env.mp.setattr(main, "_asm_deferred_departure", boom)
        await A._janitor_tick(env)
        s = await env.seat(lob, 2)
        r = (await _rows(env, "ffa_seat_readmissions", lob, 2))[0]
        assert s["hold_n"] == 1 and r["lapsed_at"] is None, \
            ("T4.4 one commit", s["hold_n"], r["lapsed_at"])
    run_env(monkeypatch, body)


# -- the janitor bound (the round 1 census ruling: no unbounded janitor wait) --

def bound_fast(env):
    """The janitor bound at test scale: its lock timeout cut to 300 ms and its
    statement timeout to 2 s, so a held row ends as a bound line at once."""
    env.mp.setattr(main, "RDM_JANITOR_LOCK_TIMEOUT_MS", 300)
    env.mp.setattr(main, "RDM_JANITOR_STATEMENT_TIMEOUT_MS", 2000)


async def tick_within(env, s=20.0):
    """One janitor pass that must end within s seconds: True when it did."""
    try:
        await asyncio.wait_for(A._janitor_tick(env), s)
        return True
    except asyncio.TimeoutError:
        return False


async def tick_holding(env, sql, *args):
    """One janitor pass while a second transaction (the case connection, all
    fixtures written before) holds the row lock `sql` takes; the hold is
    rolled back whatever the pass did. Returns tick_within's answer."""
    tr = env.conn.transaction()
    await tr.start()
    try:
        await env.conn.execute(sql, *args)
        return await tick_within(env)
    finally:
        await tr.rollback()


def test_t4_16_the_lapse_entry_declines_a_held_lobby(monkeypatch):
    """T4.16: the lapse takes its lobby row with SKIP LOCKED: a lobby another
    transaction holds is skipped this tick with one busy line and its hold
    left whole, and the next tick lapses it; a lobby with no row answers
    gone, never busy (#430: one value never means both)."""
    async def body(env):
        bound_fast(env)
        lob = await _held(env)
        await env.at(lob, 200.0)
        done = await tick_holding(env, "SELECT 1 FROM ffa_lobbies WHERE id = $1 FOR UPDATE",
                                  lob.lid)
        assert done, ("T4.16 bounded",)
        busy = _rdm_lines(env, "lapse lobby %s busy" % main._asm_id8(lob.lid))
        assert len(busy) == 1, ("T4.16 busy", _rdm_lines(env))
        s = await env.seat(lob, 1)
        assert s["hold_n"] == 1, ("T4.16 hold kept", s["hold_n"])
        await A._janitor_tick(env)
        s = await env.seat(lob, 1)
        assert s["hold_n"] is None, ("T4.16 next tick", s["hold_n"])

        got = {}

        async def gone():
            async with env.sm() as db:
                got["out"] = await main._rdm_lapse_lobby(db, cf_asm.uuid.uuid4())
        await env._call(gone)
        assert got.get("out") == ("gone", 0), ("T4.16 gone", got.get("out"))
    run_env(monkeypatch, body)


def test_t4_17_a_held_queue_row_bounds_the_lapse(monkeypatch):
    """T4.17: under the lobby lock the lapse's queue rows wait no longer than
    the janitor bound: a member's queue row another transaction holds ends
    that lobby's lapse as one bound line (stage=lock), the pass finishes and
    the hold is whole; the next tick lapses it."""
    async def body(env):
        bound_fast(env)
        lob = await _held(env)
        await env.at(lob, 200.0)
        q = await env.queue_row(lob, 0)
        assert q is not None and q["series_id"] == lob.lid, ("T4.17 precondition", q)
        done = await tick_holding(env, "SELECT 1 FROM ffa_queue WHERE player_id = $1 FOR UPDATE",
                                  lob.pids[0])
        assert done, ("T4.17 bounded",)
        line = _rdm_lines(env, "lapse lobby %s bound stage=lock" % main._asm_id8(lob.lid))
        assert len(line) == 1, ("T4.17 bound line", _rdm_lines(env))
        s = await env.seat(lob, 1)
        assert s["hold_n"] == 1, ("T4.17 hold kept", s["hold_n"])
        await A._janitor_tick(env)
        s = await env.seat(lob, 1)
        assert s["hold_n"] is None, ("T4.17 next tick", s["hold_n"])
    run_env(monkeypatch, body)


def test_t4_18_the_bound_arms_every_janitor_transaction(monkeypatch):
    """T4.18: the bound is armed on every transaction the janitor session
    begins, one begun after a rollback or a commit included (the report body
    rolls back and re-locks the lobby on its insert-failure branches), and on
    no session the janitor did not arm."""
    async def body(env):
        bound_fast(env)

        async def shown(db):
            return ((await db.execute(main.text("SHOW lock_timeout"))).scalar(),
                    (await db.execute(main.text("SHOW statement_timeout"))).scalar())
        async with env.sm() as db:
            main._rdm_janitor_bound(db)
            first = await shown(db)
            await db.rollback()
            second = await shown(db)
            await db.commit()
            third = await shown(db)
            await db.rollback()
        async with env.sm() as db:
            plain = await shown(db)
            await db.rollback()
        assert first == second == third == ("300ms", "2s"), \
            ("T4.18 every transaction", first, second, third)
        assert plain != first, ("T4.18 only the armed session", plain)
    run_env(monkeypatch, body)


# -- S5: discovery, claim, bind, decline, entered, epoch version 2 -----------

def test_m1_started_readmit_uses_cadence_and_per_hold_caps(monkeypatch):
    """M1: a started readmit-v1 sitting is not killed by the historical
    lifetime write count.  Its census uses the stored server receipt cadence,
    and claim/bind/entered traffic is instead bounded per hold by attempts."""
    async def body(env):
        lob = await _rdm_lobby(env)
        await env.set_seat(lob, 0, writes=170, census_at=30.0)
        await env.at(lob, 40.0)
        first = await env.census_of(lob, 0, list(range(lob.n)))
        assert first.status == 200, ("M1 post-start census", first.status, first.body)
        after_first = await env.seat(lob, 0)
        second = await env.census_of(lob, 0, list(range(lob.n)))
        after_second = await env.seat(lob, 0)
        assert second.status == 429 and after_second == after_first, \
            ("M1 census cadence", second.status, after_first, after_second)

        returning = await _held(env)
        await env.set_seat(returning, 1, writes=170)
        claim, bind = await _claim_bind(env, returning, 1, 1, 9)
        await _corroborate(env, returning, 1, 9)
        entered = await _readmit(env, returning, 1, "entered", 1, actor=9, game=1)
        assert claim["status"] == "claimed" and bind["status"] == "admitted_late" \
            and entered["status"] == "entered", \
            ("M1 post-start readmit", claim.body, bind.body, entered.body)

        capped = await _held(env)
        await env.set_seat(capped, 1, writes=170)
        await env.conn.execute(
            "INSERT INTO ffa_readmit_attempts"
            " (lobby_id, player_id, n, attempt_no, kind, at, outcome, reason)"
            " SELECT $1, $2, 1, g, 'claim', now(), 'refused', 'uncorroborated'"
            " FROM generate_series(1, 170) AS g", capped.lid, capped.pids[1])
        blocked = await _readmit(env, capped, 1, "claim", 1)
        n1 = await env.conn.fetchval(
            "SELECT count(*) FROM ffa_readmit_attempts"
            " WHERE lobby_id = $1 AND player_id = $2 AND n = 1",
            capped.lid, capped.pids[1])
        assert blocked.status == 429 and n1 == 170, \
            ("M1 per-hold cap", blocked.status, n1)
        fresh = await _readmit(env, capped, 1, "claim", 2)
        assert fresh.status == 200 and fresh["reason"] == "not_held", \
            ("M1 fresh hold independent", fresh.status, fresh.body)

        plain = await _rdm_lobby(env, flag=False)
        await env.set_seat(plain, 0, writes=170)
        plain_ans = await env.census_of(plain, 0, list(range(plain.n)))
        assert plain_ans.status == 429, ("M1 flag false cap", plain_ans.status)

        pre = await env.lobby(4, admission=True, t=30.0)
        await env.set_lobby(pre, readmit_v1=True)
        await env.set_seat(pre, 0, writes=170)
        await env.at(pre, 40.0)
        pre_ans = await env.census_of(pre, 0, list(range(pre.n)))
        assert pre_ans.status == 429, ("M1 pre-start cap", pre_ans.status)
    run_env(monkeypatch, body)


def test_t4_5_claim_bind_entered_and_a_second_drop(monkeypatch):
    """T4.5: from hold through discovery, claim, bind and entered, then a
    second drop with hold n = 2: the claim answers a token whose SHA-256 alone
    is stored, the queue row ready_join and the lease back; the bind rebinds
    the seat, moves the gone and leave columns into the readmission row and
    writes a kind r version 2 epoch the serializer carries; the second drop
    is judged on the new actor."""
    async def body(env):
        lob = await _held(env)
        await env.at(lob, 90.0)
        o = await _offer(env, lob, 1)
        assert o["readmissible"] == 1 and o["n"] == 1 and o["slot"] == 1, ("T4.5 offer", o.body)
        p = await env.poll(lob, 1)
        a = await _readmit(env, lob, 1, "claim", 1)
        assert a["status"] == "claimed" and a["n"] == 1, ("T4.5 claim", a.body)
        row = (await _rows(env, "ffa_seat_readmissions", lob, 1))[0]
        assert row["verifier"] == hashlib.sha256(a["token"].encode("ascii")).hexdigest(), \
            ("T4.5 verifier",)
        assert a["token"] not in "\n".join(env.lines), ("T4.5 token in a log line",)
        q = await env.queue_row(lob, 1)
        assert q["status"] == "ready_join" and q["series_id"] == lob.lid, ("T4.5 queue", q)
        assert (await env.lease(lob, 1))["mode"] == "ffa", ("T4.5 lease",)
        await _corroborate(env, lob, 1, 9)
        b = await _readmit(env, lob, 1, "bind", 1, actor=9)
        assert b["status"] == "admitted_late" and b["kind"] == "r", ("T4.5 bind", b.body)
        s = await env.seat(lob, 1)
        assert (s["actor_nr"], s["actor_region"]) == (9, lob.region), \
            ("T4.5 rebound", s["actor_nr"], s["actor_region"])
        assert s["gone_game"] is None and s["left_at"] is None and s["hold_n"] is None, \
            ("T4.5 moved", s["gone_game"], s["left_at"], s["hold_n"])
        row = (await _rows(env, "ffa_seat_readmissions", lob, 1))[0]
        assert row["bound_at"] is not None and row["gone_game"] == 1 and row["game"] == 1, \
            ("T4.5 row", row["gone_game"], row["game"])
        ep = await env.conn.fetch("SELECT * FROM ffa_kept_epochs WHERE lobby_id = $1"
                                  " ORDER BY epoch_no", lob.lid)
        assert [(e["kind"], e["chain_v"], e["game"]) for e in ep] == [("r", 2, 1)], \
            ("T4.5 epoch row", [dict(e) for e in ep])
        assert _chain([dict(e) for e in ep], str(lob.lid)[:8]), ("T4.5 chain",)
        async with env.sm() as db:
            ctx = await main._asm_ctx_slot(db, lob.lid, route="t", trigger="t")
            got = await main._asm_epoch(ctx)
            await db.rollback()
        assert got["kept"][0].get("kind") == "r" and got["kept"][0].get("game") == 1, \
            ("T4.5 serializer", got)
        # entered: refused with a wrong game, accepted with the bound triple.
        e1 = await _readmit(env, lob, 1, "entered", 1, actor=9, game=2)
        assert e1["status"] == "refused", ("T4.5 entered wrong", e1.body)
        await _corroborate(env, lob, 1, 9)
        e2 = await _readmit(env, lob, 1, "entered", 1, actor=9, game=1)
        assert e2["status"] == "entered", ("T4.5 entered", e2.body)
        # The returner's own census, then a second drop judged on actor 9.
        await env.at(lob, 100.0)
        entries = [env.entry(lob, s_, 1 + s_) for s_ in (0, 2, 3)] + [env.entry(lob, 1, 9)]
        await env.assembly(lob, 1, 9, entries)
        await env.at(lob, 120.0)
        await env.census_row(lob, 2, [(0, 1, 1, 1), (2, 3, 1, 1), (3, 4, 1, 1)])
        await env.census_of(lob, 0, [0, 2, 3])
        s = await env.seat(lob, 1)
        assert s["gone_game"] == 1 and s["hold_n"] == 2, \
            ("T4.5 second drop", s["gone_game"], s["hold_n"])
        assert s["left_at"] is None, ("T4.5 second drop left_at", s["left_at"])
    run_env(monkeypatch, body)


def test_t4_5_every_refusal_reason(monkeypatch):
    """T4.5 refusals: lobby_closed, departed, not_held, hold_lapsed,
    other_mode, other_lobby, actor_conflict, uncorroborated (with retry), and
    a flag-false lobby answers not_held and writes no row."""
    async def body(env):
        async def first(lob, step="claim", n=1, **kw):
            return await _readmit(env, lob, 1, step, n, **kw)

        lob = await _held(env)
        await env.set_lobby(lob, status="completed")
        assert (await first(lob))["reason"] == "lobby_closed", ("T4.5 lobby_closed",)

        lob = await _held(env)
        await env.set_lobby(lob, departed_ids=[lob.pids[1]])
        assert (await first(lob))["reason"] == "departed", ("T4.5 departed",)

        lob = await _held(env)
        assert (await first(lob, n=2))["reason"] == "not_held", ("T4.5 not_held",)

        lob = await _held(env)
        await env.at(lob, 171.0)
        r = await first(lob)
        assert r["reason"] == "hold_lapsed", ("T4.5 hold_lapsed", r.body)
        assert (await env.seat(lob, 1))["hold_n"] is None, ("T4.5 lapsed at claim",)

        lob = await _held(env)
        async with env.sm() as db:
            await main._lease_acquire(db, lob.pids[1], "ranked", None, 600)
            await db.commit()
        assert (await first(lob))["reason"] == "other_mode", ("T4.5 other_mode",)

        lob = await _held(env)
        other = await env.lobby(4, t=30.0)
        async with env.sm() as db:
            await main._lease_acquire(db, lob.pids[1], "ffa", other.lid, 600)
            await db.commit()
        assert (await first(lob))["reason"] == "other_lobby", ("T4.5 other_lobby",)

        lob = await _held(env)
        assert (await first(lob))["status"] == "claimed", ("T4.5 claim",)
        r = await first(lob, "bind", actor=3)
        assert r["reason"] in ("actor_conflict", "actor_identity_mismatch"), \
            ("T4.5 actor_conflict", r.body)
        r = await first(lob, "bind", actor=9)
        assert r["reason"] == "uncorroborated" and r["retry"] == 1, ("T4.5 uncorroborated",
                                                                    r.body)
        await _corroborate(env, lob, 1, 9)
        assert (await first(lob, "bind", actor=9))["status"] == "admitted_late", \
            ("T4.5 retry binds",)
        att = await _attempts(env, lob, 1)
        assert [a[1:3] for a in att][-3:] == [("bind", "refused"), ("bind", "refused"),
                                              ("bind", "ok")], ("T4.5 attempts", att)

        lob = await _held(env, flag=False)
        r = await first(lob)
        assert r["reason"] == "not_held", ("T4.5 flag false", r.body)
        assert await _attempts(env, lob, 1) == [], ("T4.5 flag false rows",)
    run_env(monkeypatch, body)


def test_nx0c_claim_takes_the_admission_gate_over_an_open_match_hold(monkeypatch):
    """NX0c: the FFA claim takes the per-player admission gate of every
    formation path. A held FFA seat whose player also has an open 2v2 match
    hold is refused other_mode with its refused claim row and no claimed
    stamp or verifier; once that match hold is closed the same claim is
    granted (the negative control)."""
    async def body(env):
        lob = await _held(env)
        room = "nx0c_" + lob.sids[1][-6:]
        series = await env.conn.fetchval("SELECT gen_random_uuid()")
        game = await env.conn.fetchval(
            "INSERT INTO match_games (mode, series_id, room_name, seq)"
            " VALUES ('team', $1, $2, 1) RETURNING id", series, room)
        hold = await env.conn.fetchval(
            "INSERT INTO match_seat_holds (mode, room_name, series_id, game_id, player_id, n,"
            "        slot, team, opener_player_id, held_anchor_at, held_at, held_until)"
            " VALUES ('team', $1, $2, $3, $4, 1, 1, 0, $5, clock_timestamp(),"
            "         clock_timestamp(), clock_timestamp() + make_interval(secs => 120))"
            " RETURNING id", room, series, game, lob.pids[1], lob.pids[0])
        r = await _readmit(env, lob, 1, "claim", 1)
        assert r["reason"] == "other_mode", ("NX0c refused", r.body)
        assert (await _attempts(env, lob, 1))[-1] == (1, "claim", "refused", "other_mode"), \
            ("NX0c attempt row",)
        rows = await _rows(env, "ffa_seat_readmissions", lob, 1)
        assert rows and all(x["claimed_at"] is None and x["verifier"] is None for x in rows), \
            ("NX0c no claim write", rows)
        await env.conn.execute(
            "UPDATE match_seat_holds SET closed_at = clock_timestamp(), closed_reason = 'ceiling'"
            " WHERE id = $1", hold)
        r = await _readmit(env, lob, 1, "claim", 1)
        assert r["status"] == "claimed", ("NX0c control", r.body)
    run_env(monkeypatch, body)


def test_t4_6_identity_mismatch(monkeypatch):
    """T4.6 (server half): a bind of actor X refused actor_identity_mismatch
    while a fresh census lists the seat's slot with another actor; the genuine
    new actor binds once only X is listed for it."""
    async def body(env):
        lob = await _held(env)
        assert (await _readmit(env, lob, 1, "claim", 1))["status"] == "claimed", "T4.6 claim"
        await _corroborate(env, lob, 1, 9)
        await env.census_row(lob, 2, [(0, 1, 1, 1), (1, 7, 1, 1), (3, 4, 1, 1)])
        r = await _readmit(env, lob, 1, "bind", 1, actor=9)
        assert r["reason"] == "actor_identity_mismatch", ("T4.6 mismatch", r.body)
        await env.census_row(lob, 2, [(0, 1, 1, 1), (1, 9, 1, 1), (3, 4, 1, 1)])
        r = await _readmit(env, lob, 1, "bind", 1, actor=9)
        assert r["status"] == "admitted_late", ("T4.6 genuine", r.body)
    run_env(monkeypatch, body)


def test_t4_13_flag_false_negative_control(monkeypatch):
    """T4.13: with the flag false the same drop writes zero holds, zero
    readmission rows, zero [FFA-RDM] lines, no offer, and its trailing leave
    appends the departure as today."""
    async def body(env):
        lob = await _rdm_lobby(env, flag=False)
        await _present(env, lob, 2, 50.0)
        await env.at(lob, 70.0)
        await A._omit(env, lob, [0, 1], 2)
        await env.leave(lob, 2, cause="in_room_timeout")
        s = await env.seat(lob, 2)
        assert s["gone_game"] is not None and s["hold_n"] is None, ("T4.13 hold", s["hold_n"])
        assert s["present_at"] is None, ("T4.13 present_at", s["present_at"])
        assert await _rows(env, "ffa_seat_readmissions", lob) == [], ("T4.13 rows",)
        assert _rdm_lines(env) == [], ("T4.13 lines", _rdm_lines(env))
        o = await _offer(env, lob, 2)
        assert o["readmissible"] == 0, ("T4.13 offer", o.body)
        assert list((await env.lobby_row(lob))["departed_ids"]) == [lob.pids[2]], \
            ("T4.13 departure",)
    run_env(monkeypatch, body)


def test_a25_a_pre_migration_chain_keeps_verifying(monkeypatch):
    """A25: a lobby holding version 1 epoch rows from before the migration
    keeps verifying its chain, row by row in its own version, after a version
    2 row is appended by a bind, and its late actor stays in the kept list."""
    async def body(env):
        lob = await _held(env)
        lobby8 = str(lob.lid)[:8]
        c1 = main._ffa_epoch_chain("0", lobby8, 1, 3, 4)
        await env.conn.execute(
            "INSERT INTO ffa_kept_epochs (lobby_id, epoch_no, slot, actor_nr, chain)"
            " VALUES ($1, 1, 3, 4, $2)", lob.lid, c1)
        await _claim_bind(env, lob, 1, 1, 9)
        ep = [dict(e) for e in await env.conn.fetch(
            "SELECT * FROM ffa_kept_epochs WHERE lobby_id = $1 ORDER BY epoch_no", lob.lid)]
        assert [(e["chain_v"], e["kind"]) for e in ep] == [(1, "l"), (2, "r")], ("A25 rows", ep)
        assert _chain(ep, lobby8), ("A25 chain",)
        async with env.sm() as db:
            ctx = await main._asm_ctx_slot(db, lob.lid, route="t", trigger="t")
            got = await main._asm_epoch(ctx)
            await db.rollback()
        assert [(k["slot"], k["actor"]) for k in got["kept"]] == [(3, 4), (1, 9)], \
            ("A25 kept", got)
    run_env(monkeypatch, body)


# -- S6: headroom and attest during a hold (P4.9) ----------------------------

def test_t4_14_headroom_reserves_the_held_place(monkeypatch):
    """T4.14: in a readmission lobby's room the headroom formula reads members
    minus departed (the held seat's place stays reserved), not the attested
    fighter count; any other room keeps the attested count."""
    async def body(env):
        lob = await _held(env, n=4)
        room = (await env.lobby_row(lob))["photon_room_id"]
        async with env.sm() as db:
            r = await main._rdm_spectate_fighters(db, room)
            assert r == 4, ("T4.14 fighters", r)
            plain = await env.lobby(4, t=30.0)
            proom = (await env.lobby_row(plain))["photon_room_id"]
            assert await main._rdm_spectate_fighters(db, proom) is None, ("T4.14 plain",)
            assert await main._rdm_spectate_fighters(db, "team_x") is None, ("T4.14 mode",)
            game = {"id": "00000000-0000-0000-0000-000000000000", "room_name": room,
                    "room_region": lob.region, "fighter_target": 3, "room_capacity": 9,
                    "spectator_cap": 5}
            adm = await main._spectate_admission(db, game, None, broadcast=False)
            await db.rollback()
        assert adm["physical_headroom"] == 5, ("T4.14 headroom", adm)
    run_env(monkeypatch, body)


def test_t4_15_attest_counts_a_held_seat_present(monkeypatch):
    """T4.15: the attest equality of a readmission lobby accepts the attested
    set united with the server's held set; it still refuses an attest that
    omits a live fighter, and a held set is never taken from the caller."""
    async def body(env):
        lob = await _held(env, n=4)
        true = set(lob.sids)
        async with env.sm() as db:
            h = await main._rdm_spectate_held(db, str(lob.lid))
            await db.rollback()
        assert h == {lob.sids[1]}, ("T4.15 held", h)
        live = [lob.sids[0], lob.sids[2], lob.sids[3]]
        plain = await env.lobby(4, t=30.0)
        async with env.sm() as db:
            ok = await main._rdm_attest_check(db, "ffa", str(lob.lid), live, true, lob.sids[0])
            assert ok is True, ("T4.15 accept", ok)
            ok = await main._rdm_attest_check(db, "ffa", str(lob.lid),
                                              [lob.sids[0], lob.sids[2]], true, lob.sids[0])
            assert ok is False, ("T4.15 omit a live fighter", ok)
            ok = await main._rdm_attest_check(db, "ffa", str(lob.lid), list(lob.sids), true,
                                              lob.sids[0])
            assert ok is True, ("T4.15 the returner attested", ok)
            ok = await main._rdm_attest_check(db, "ffa", str(plain.lid), live,
                                              set(plain.sids), plain.sids[0])
            assert ok is None, ("T4.15 plain", ok)
            assert await main._rdm_spectate_held(db, str(plain.lid)) is None, ("T4.15 plain",)
            await db.rollback()
    run_env(monkeypatch, body)


def test_l2_attest_held_snapshot_has_an_active_lobby_fence(monkeypatch):
    """L2: the held set is one snapshot of an active flagged lobby.  Bind
    and lapse remove H, and an attest paused after its roster read cannot use
    a stale held seat after the real poll closer completes the lobby."""
    async def body(env):
        bound = await _held(env)
        await _claim_bind(env, bound, 1, 1, 9)
        async with env.sm() as db:
            held = await main._rdm_spectate_held(db, str(bound.lid))
            await db.rollback()
        assert held == set(), ("L2 bind clears held", held)

        lapsed = await _held(env)
        await env.at(lapsed, 171.0)
        await A._janitor_tick(env)
        async with env.sm() as db:
            held = await main._rdm_spectate_held(db, str(lapsed.lid))
            await db.rollback()
        assert held == set(), ("L2 lapse clears held", held)

        async def session_ok(request, steam_id, db):
            return True

        env.mp.setattr(main, "_strict_steam_session_ok", session_ok)
        # The close must land while the hold is still LIVE: a hold anchored at
        # lobby age 940 runs to 1060, past the poll closer at 1000.  (Anchored
        # at the default 50, the hold had expired by 1000, the pre-fix reader
        # already returned an empty H, and the fence was never observed.)  The
        # gone census comes 20 s after the seat's own, as in the default: an
        # own census at most ASM_WITNESS_FRESH_S old that lists itself vetoes
        # the gone rule.
        lob = await _held(env, t_present=940.0, t_gone=960.0)
        assert (await env.seat(lob, 1))["hold_n"] is not None, ("L2 hold premise",)
        room = (await env.lobby_row(lob))["photon_room_id"]
        roster = sorted(s for i, s in enumerate(lob.sids) if i != 1)
        req = main.SpectateAttestBody(
            steam_id=roster[0], mode="ffa", room_name=room, region=lob.region,
            actor_number=1, fighter_target=len(roster), room_capacity=lob.n,
            spectator_protocol=main.SPECTATE_PROTOCOL, phase="transition",
            roster=",".join(roster))
        roster_read, release = asyncio.Event(), asyncio.Event()
        real_roster = main._spectate_authoritative_roster

        async def paused_roster(db, mode, room_name):
            out = await real_roster(db, mode, room_name)
            roster_read.set()
            await release.wait()
            return out

        env.mp.setattr(main, "_spectate_authoritative_roster", paused_roster)

        async def attest():
            async with env.sm() as db:
                return await main.spectate_participant_attest(req, None, db=db)

        task = asyncio.create_task(env._call(attest))
        await asyncio.wait_for(roster_read.wait(), 10.0)
        await env.at(lob, 1000.0)
        poll = await env.poll(lob, 0)
        closed = await env.lobby_row(lob)
        assert poll.status == 200 and closed["status"] == "completed", \
            ("L2 close premise", poll.status, closed["status"])
        live = await env.seat(lob, 1)
        assert live["hold_n"] is not None and live["hold_until"] > env.now, \
            ("L2 live hold premise", live["hold_n"], live["hold_until"], env.now)
        release.set()
        answer = await asyncio.wait_for(task, 10.0)
        env.mp.setattr(main, "_spectate_authoritative_roster", real_roster)
        assert answer.status == 409 and answer.body == "roster_mismatch", \
            ("T4.15 close fence", answer.status, answer.body)

        async with env.sm() as db:
            retry = await env._call(
                lambda: main.spectate_participant_attest(req, None, db=db))
        assert retry.status == 409 and retry.body == "room_unknown", \
            ("L2 closed retry", retry.status, retry.body)
    run_env(monkeypatch, body)


# -- S7: P5 rows -------------------------------------------------------------

def test_t5_1_rows_per_transition(monkeypatch):
    """T5.1: two readmissions in one game give rows n = 1 and n = 2 with no
    crossed receipts; an early entered before any bind is refused and
    recorded; an offer whose row cannot be written answers 503 with no offer;
    a hold whose transaction rolls back leaves no readmission row."""
    async def body(env):
        lob = await _held(env)
        await env.at(lob, 80.0)
        early = await _readmit(env, lob, 1, "entered", 1, actor=9, game=1)
        assert early["status"] == "refused", ("T5.1 early entered", early.body)
        await _claim_bind(env, lob, 1, 1, 9)
        await _corroborate(env, lob, 1, 9)
        assert (await _readmit(env, lob, 1, "entered", 1, actor=9, game=1))["status"] \
            == "entered", "T5.1 entered"
        await env.at(lob, 90.0)
        entries = [env.entry(lob, s_, 1 + s_) for s_ in (0, 2, 3)] + [env.entry(lob, 1, 9)]
        await env.assembly(lob, 1, 9, entries)
        await env.at(lob, 110.0)
        await env.census_row(lob, 2, [(0, 1, 1, 1), (2, 3, 1, 1), (3, 4, 1, 1)])
        await env.census_of(lob, 0, [0, 2, 3])
        rows = await _rows(env, "ffa_seat_readmissions", lob, 1)
        assert [r["n"] for r in rows] == [1, 2], ("T5.1 n", [r["n"] for r in rows])
        assert rows[0]["entered_at"] is not None and rows[1]["claimed_at"] is None, \
            ("T5.1 crossed",)
        att = await _attempts(env, lob, 1)
        assert att[0] == (1, "entered", "refused", "not_held"), ("T5.1 early row", att)
        assert {a[0] for a in att} == {1}, ("T5.1 attempts n", att)
        exact = {(kind, outcome): sum(1 for a in att if a[1:3] == (kind, outcome))
                 for kind, outcome in (("claim", "ok"), ("bind", "ok"),
                                       ("entered", "ok"), ("entered", "refused"))}
        assert exact == {("claim", "ok"): 1, ("bind", "ok"): 1,
                         ("entered", "ok"): 1, ("entered", "refused"): 1}, \
            ("T5.1 exact attempts", exact, att)

        async def broken(*a, **k):
            raise RuntimeError("attempt write failed")
        real = main._rdm_attempt
        env.mp.setattr(main, "_rdm_attempt", broken)
        o = await _offer(env, lob, 1)
        env.mp.setattr(main, "_rdm_attempt", real)
        assert o.status == 503 and "readmissible" not in (o.body or {}), \
            ("T5.1 offer 503", o.status, o.body)

    run_env(monkeypatch, body)


def test_t5_1_a_rolled_back_hold_leaves_no_row(monkeypatch):
    """T5.1 rollback fixture: the census transaction that wrote a hold fails
    before its commit; no hold and no readmission row survive."""
    async def body(env):
        lob = await _rdm_lobby(env)
        await _present(env, lob, 1, 50.0)
        await env.at(lob, 70.0)
        await A._omit(env, lob, [2], 1)

        async def boom(ctx):
            raise RuntimeError("after the hold")
        env.mp.setattr(main, "_ffa_admission_check", boom)
        try:
            await env.census_of(lob, 0, [0, 2, 3])
        except RuntimeError:
            pass
        s = await env.seat(lob, 1)
        assert await _rows(env, "ffa_seat_readmissions", lob, 1) == [], ("T5.1 rollback",)
        assert s["hold_n"] is None, ("T5.1 rollback seat", s["hold_n"])
    run_env(monkeypatch, body)


def test_health_marker_counts_every_site():
    """The ffa_readmit health word reads 9 on this build (every wiring site
    loads its helper)."""
    assert main._FFA_READMIT == len(main._FFA_READMIT_SITES) == 9, \
        ("health ffa_readmit", main._FFA_READMIT)


# -- S8: deletion redaction ---------------------------------------------------

def test_s8_deletion_clears_the_readmission_tables(monkeypatch):
    """S8: deleting a held player's data ends the hold (departure appended),
    deletes its readmission and attempt rows and its journal rows, rewrites
    its Steam id out of other journaled payloads, and NULLs it as a window's
    settled reporter."""
    async def body(env):
        lob = await _held(env)
        await env.at(lob, 80.0)
        await _offer(env, lob, 1)
        await env.conn.execute(
            "INSERT INTO ffa_report_windows (lobby_id, game, opened_at, settle_after,"
            "  settled_at, settled_reporter, settled_cls)"
            " VALUES ($1, 1, now(), now(), now(), $2, 'r')", lob.lid, lob.pids[1])
        await env.conn.execute(
            "INSERT INTO ffa_report_journal (lobby_id, game, reporter_id, cls, received_at,"
            "  payload) VALUES ($1, 2, $2, 'r', now(), $3::jsonb)",
            lob.lid, lob.pids[1], '{"reported_by_steam_id": "%s"}' % lob.sids[1])
        await env.conn.execute(
            "INSERT INTO ffa_report_journal (lobby_id, game, reporter_id, cls, received_at,"
            "  payload) VALUES ($1, 2, $2, 'l', now(), $3::jsonb)",
            lob.lid, lob.pids[0], '{"players": [{"steam_id": "%s"}]}' % lob.sids[1])
        a = await A._delete_member(env, lob.sids[1])
        assert a.status == 200, ("S8 delete", a)
        pid, sid = lob.pids[1], lob.sids[1]
        for table, col in (("ffa_seat_readmissions", "player_id"),
                           ("ffa_readmit_attempts", "player_id"),
                           ("ffa_report_journal", "reporter_id"),
                           ("ffa_report_windows", "settled_reporter")):
            n = await env.conn.fetchval("SELECT count(*) FROM %s WHERE %s = $1" % (table, col),
                                        pid)
            assert n == 0, ("S8 %s" % table, n)
        n = await env.conn.fetchval(
            "SELECT count(*) FROM ffa_report_journal WHERE strpos(payload::text, $1) > 0", sid)
        assert n == 0, ("S8 payload", n)
        s = await env.seat(lob, 1)
        assert s["hold_n"] is None, ("S8 hold", s["hold_n"])
        assert pid in list((await env.lobby_row(lob))["departed_ids"] or []), ("S8 departure",)
    run_env(monkeypatch, body)


async def _h5_delete_active_seat(env, *, queue_row):
    """An active readmit seat (present at 50, omitted by one stored census at
    70, no hold yet) whose account is deleted; a census that would complete
    the gone rule is sent while deletion is paused after its readmission
    sweep.  queue_row=False first removes the seat's ffa_queue row, so the
    seat-row discovery is deletion's only route to the lobby (the queue-row
    route also closes a played lobby, which fences the hold by itself).
    Returns (lobby, seat, readmission rows, departed ids)."""
    lob = await _rdm_lobby(env)
    await _present(env, lob, 1, 50.0)
    await env.at(lob, 70.0)
    await A._omit(env, lob, [2], 1)
    if not queue_row:
        await env.conn.execute("DELETE FROM ffa_queue WHERE player_id = $1", lob.pids[1])
    real = main._rdm_delete_player
    swept, release = asyncio.Event(), asyncio.Event()

    async def after_sweep(*args, **kwargs):
        await real(*args, **kwargs)
        swept.set()
        await release.wait()

    env.mp.setattr(main, "_rdm_delete_player", after_sweep)
    deleting = asyncio.create_task(A._delete_member(env, lob.sids[1]))
    await asyncio.wait_for(swept.wait(), 10)
    census = asyncio.create_task(env.census_of(lob, 0, [0, 2, 3]))
    await asyncio.sleep(0)
    release.set()
    await deleting
    await census
    env.mp.setattr(main, "_rdm_delete_player", real)
    seat = await env.seat(lob, 1)
    rows = await _rows(env, "ffa_seat_readmissions", lob, 1)
    departed = list((await env.lobby_row(lob))["departed_ids"] or [])
    return lob, seat, rows, departed


def test_h5_deletion_locks_an_active_seat_before_hold_creation(monkeypatch):
    """H5 hold side: deletion discovers an active readmit seat from its seat
    row even before it has a hold and when no queue row names the lobby, and
    a later census cannot recreate identity or a live hold."""
    async def body(env):
        lob, seat, rows, departed = await _h5_delete_active_seat(env, queue_row=False)
        assert seat["hold_n"] is None and rows == [], \
            ("H5 active lobby", seat["hold_n"], rows)
        assert lob.pids[1] in departed, ("H5 active lobby departed", departed)
    run_env(monkeypatch, body)


def test_h5_deletion_records_the_departure_of_an_active_seat(monkeypatch):
    """H5 departure side: with the seat's queue row in place (deletion closes
    the played lobby through it), the seat-row discovery still appends the
    departure before the lobby closes, and no hold is recreated."""
    async def body(env):
        lob, seat, rows, departed = await _h5_delete_active_seat(env, queue_row=True)
        assert lob.pids[1] in departed, ("H5 active departed", departed)
        assert seat["hold_n"] is None and rows == [], \
            ("H5 departed no hold", seat["hold_n"], rows)
    run_env(monkeypatch, body)


def test_h5_readmit_revalidates_identity_below_the_lobby_lock(monkeypatch):
    """H5 readmit side: a caller paused before the lobby lock cannot write an
    attempt after deletion commits."""
    async def body(env):
        lob = await _held(env)
        await env.at(lob, 80.0)
        real = main._ffa_lock_lobby_slot
        reached, release = asyncio.Event(), asyncio.Event()
        once = {"done": False}

        async def before_lock(db, lid):
            if str(lid) == str(lob.lid) and not once["done"]:
                once["done"] = True
                reached.set()
                await release.wait()
            return await real(db, lid)

        env.mp.setattr(main, "_ffa_lock_lobby_slot", before_lock)
        claiming = asyncio.create_task(_readmit(env, lob, 1, "claim", 1))
        await asyncio.wait_for(reached.wait(), 10)
        deleted = await A._delete_member(env, lob.sids[1])
        release.set()
        answer = await claiming
        assert deleted.status == 200 and answer.status == 404, \
            ("H5 readmit identity", deleted.status, answer.status, answer.body)
        assert await _attempts(env, lob, 1) == [], ("H5 readmit attempt",)
    run_env(monkeypatch, body)


def test_h5_offer_holds_the_shared_identity_key_through_commit(monkeypatch):
    """H5 offer side: deletion sweeps a writer-first offered attempt; a write
    paused after selection cannot land after deletion's one-shot scrub."""
    async def body(env):
        lob = await _held(env)
        await env.at(lob, 80.0)
        real_attempt = main._rdm_attempt
        real_delete = main._rdm_delete_player
        offer_reached, offer_release = asyncio.Event(), asyncio.Event()
        swept, delete_release = asyncio.Event(), asyncio.Event()

        async def pause_offer(db, lid, pid, n, kind, at, outcome, reason=None):
            if kind == "offered":
                offer_reached.set()
                await offer_release.wait()
            return await real_attempt(db, lid, pid, n, kind, at, outcome, reason)

        async def after_sweep(*args, **kwargs):
            await real_delete(*args, **kwargs)
            swept.set()
            await delete_release.wait()

        env.mp.setattr(main, "_rdm_attempt", pause_offer)
        env.mp.setattr(main, "_rdm_delete_player", after_sweep)
        offering = asyncio.create_task(_offer(env, lob, 1))
        await asyncio.wait_for(offer_reached.wait(), 10)
        deleting = asyncio.create_task(A._delete_member(env, lob.sids[1]))
        try:
            await asyncio.wait_for(asyncio.shield(swept.wait()), 0.3)
        except asyncio.TimeoutError:
            pass
        offer_release.set()
        await offering
        await asyncio.wait_for(swept.wait(), 10)
        delete_release.set()
        deleted = await deleting
        assert deleted.status == 200 and await _attempts(env, lob, 1) == [], \
            ("H5 offer identity", deleted.status, await _attempts(env, lob, 1))
    run_env(monkeypatch, body)


def test_h5_report_repeats_participant_lookup_below_the_lobby_lock(monkeypatch):
    """H5 report side: a participant deleted while a report waits for the
    lobby lock is rejected before journaling; no raw identity is recreated."""
    async def body(env):
        lob = await _rdm_lobby(env)
        await env.at(lob, 60.0)
        results = {lob.sids[0]: (5, 10), lob.sids[1]: (3, 7),
                   lob.sids[2]: (2, 5), lob.sids[3]: (1, 2)}
        rep = await env.report_req(lob, 1, results, reporter=lob.sids[0])
        real = main._ffa_lock_lobby_slot
        reached, release = asyncio.Event(), asyncio.Event()
        once = {"done": False}

        async def before_lock(db, lid):
            if str(lid) == str(lob.lid) and not once["done"]:
                once["done"] = True
                reached.set()
                await release.wait()
            return await real(db, lid)

        env.mp.setattr(main, "_ffa_lock_lobby_slot", before_lock)
        filing = asyncio.create_task(env.submit(rep))
        await asyncio.wait_for(reached.wait(), 10)
        deleted = await A._delete_member(env, lob.sids[3])
        release.set()
        answer = await filing
        raw = await env.conn.fetchval(
            "SELECT count(*) FROM ffa_report_journal WHERE strpos(payload::text, $1) > 0",
            lob.sids[3])
        assert deleted.status == 200 and answer.status == 404 and raw == 0, \
            ("H5 report identity", deleted.status, answer.status, raw)
    run_env(monkeypatch, body)


# -- the finishing count of a readmission lobby --------------------------------

def test_fin_a_seat_gone_during_the_game_did_not_finish_it(monkeypatch):
    """The "N or more players" shutout tiers count the players who FINISHED
    the game. A readmission lobby's count reads server rows only: the unrated
    set with the seats the rows show gone during the game and not back. A
    seat witnessed gone during game 1 and never readmitted is rated for the
    game (it left after the grace threshold: a loss) and did not finish it,
    so the count is three of four; the same seat claimed, bound and entered
    before the report finished it: four of four."""
    async def body(env):
        calls = []
        real = main._ffa_finishing_count

        def finishing(member_ids, departed_ids, report, effective_absent=None):
            out = real(member_ids, departed_ids, report, effective_absent)
            calls.append((None if effective_absent is None else set(effective_absent), out))
            return out

        env.mp.setattr(main, "_ffa_finishing_count", finishing)

        async def report(lob, tag):
            results = {lob.sids[0]: (5, 10), lob.sids[1]: (3, 7),
                       lob.sids[2]: (2, 5), lob.sids[3]: (1, 2)}
            rep = await env.report_req(lob, 1, results, reporter=lob.sids[0])
            a = await env.submit(rep)
            assert a.status == 200, (tag + " report", a.status, a.body)
            rows = await A._mp(env, lob, 1)
            assert A._rated(rows[1]), (tag + " rated", rows[1])
            return calls[-1]

        # (a) gone during game 1 (two witnesses), never readmitted: rated, not finished.
        lob = await _held(env)
        await env.at(lob, 90.0)
        await env.census_of(lob, 0, [0, 2, 3])
        absent, out = await report(lob, "FIN gone")
        assert absent == {lob.pids[1]} and out == (3, 3, 3), \
            ("FIN gone not finished", absent, out)

        # (b) the same seat claimed, bound and entered before the report: finished.
        lob = await _held(env)
        await env.at(lob, 90.0)
        o = await _offer(env, lob, 1)
        assert o["readmissible"] == 1, ("FIN offer", o.body)
        _a, b = await _claim_bind(env, lob, 1, 1, 9)
        assert b["status"] == "admitted_late", ("FIN bind", b.body)
        await _corroborate(env, lob, 1, 9)
        e = await _readmit(env, lob, 1, "entered", 1, actor=9, game=1)
        assert e["status"] == "entered", ("FIN entered", e.body)
        await env.at(lob, 96.0)
        absent, out = await report(lob, "FIN returner")
        assert absent == set() and out == (4, 4, 4), ("FIN returner finished", absent, out)
    run_env(monkeypatch, body)


def test_fin_a_late_admitted_seat_kept_in_finished_it(monkeypatch):
    """A seat admitted late and first seen kept in during game 1 is unrated
    for it (writer 7's rule (a): its game is not rated) and was there at the
    end: the finishing count of a readmission lobby counts it, as a flag-false
    lobby's accounts do. Four of four, the seat unrated with the reason asm_a."""
    async def body(env):
        calls = []
        real = main._ffa_finishing_count

        def finishing(member_ids, departed_ids, report, effective_absent=None):
            out = real(member_ids, departed_ids, report, effective_absent)
            calls.append((None if effective_absent is None else set(effective_absent), out))
            return out

        env.mp.setattr(main, "_ffa_finishing_count", finishing)
        lob = await _rdm_lobby(env)
        await env.set_seat(lob, 3, start_roster=False, late_admitted_at=20.0,
                           late_game=1, late_body_game=1)
        await env.at(lob, 60.0)
        # The reporter's fresh census elects it: the report settles at
        # receipt instead of being journaled (P3).
        await env.census_of(lob, 0, [0, 1, 2, 3])
        results = {lob.sids[0]: (5, 10), lob.sids[1]: (3, 7),
                   lob.sids[2]: (2, 5), lob.sids[3]: (1, 2)}
        rep = await env.report_req(lob, 1, results, reporter=lob.sids[0])
        a = await env.submit(rep)
        assert a.status == 200, ("FIN late report", a.status, a.body)
        rows = await A._mp(env, lob, 1)
        assert A._unrated(rows[3]) and rows[3]["exclusion_reasons"] == ["asm_a"], \
            ("FIN late unrated", rows[3])
        absent, out = calls[-1]
        assert absent == set() and out == (4, 4, 4), ("FIN late present", absent, out)
    run_env(monkeypatch, body)
