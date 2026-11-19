"""Bans part 2a, FIX-2 class I: the writers against the three ban states.

(a) The 1v1 writer (submit_match). A result from a sitting whose series the
ban void ended is refused before any match row or payment (409
series_ended_by_ban), while the ban is active (the gate answers first), after
it has run out and after an unban, for each binding the room can have: a queue
room (the room ledger, issued before the void), a private room (no binding:
no series of the pair created after the void) and a room with a recorded game
of the ended series. Controls (no levelling down): after the ban, a queue room
issued later and a private room whose new series was created later are
admitted and paid.

(b) The admin completion (admin_resolve_team_series action=complete) reads
the roster's bans under their identity keys before it pays: a series a
banned member is on that the void did not end is refused; the same series
with the ban run out or lifted completes.

Each with a mutant that removes the disposition read.
"""
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

import main  # noqa: E402
import test_ban_sweep_live as L  # noqa: E402
from test_ban_sweep_live import case, soft  # noqa: E402,F401  (fixtures)
lh = L.lh

STATES = ("active", "run_out", "lifted")
ROOMS = ("queue", "private", "recorded")
INTERNAL_KEY = "ban-sweep-internal-key"


async def _set_state(sm, sid, state):
    async with sm() as db:
        if state == "run_out":
            await db.execute(text(
                "UPDATE player_bans SET banned_at = NOW() - INTERVAL '2 hours',"
                " expires_at = NOW() - INTERVAL '1 second'"
                " WHERE steam_id = :s AND unbanned_at IS NULL"), {"s": sid})
        elif state == "lifted":
            await db.execute(text(
                "UPDATE player_bans SET unbanned_at = NOW() WHERE steam_id = :s AND unbanned_at IS NULL"),
                {"s": sid})
        await db.commit()


async def _counts(sm, pa, pb):
    async with sm() as db:
        q = {"a": pa, "b": pb}
        pair = "((player1_id = :a AND player2_id = :b) OR (player1_id = :b AND player2_id = :a))"
        return (
            (await db.execute(text("SELECT count(*) FROM matches WHERE " + pair), q)).scalar(),
            (await db.execute(text("SELECT count(*) FROM ranked_series WHERE " + pair), q)).scalar(),
            (await db.execute(text(
                "SELECT count(*) FROM gold_transactions WHERE player_id IN (:a, :b)"), q)).scalar(),
        )


async def _world(sm, room_kind):
    """A, B in an active ranked series bound to a room of `room_kind`; B is
    banned (the void ends the series). Returns (a, b, pa, pb, room)."""
    a, b = L._sid(), L._sid()
    room = "bs_room_" + uuid.uuid4().hex[:8]
    async with sm() as db:
        pa = await L._player(db, a, ranked_enabled=True)
        pb = await L._player(db, b, ranked_enabled=True)
        rs = uuid.uuid4()
        await lh._insert(db, "ranked_series", {"id": rs, "player1_id": pa, "player2_id": pb,
                                               "status": "active"})
        if room_kind == "queue":
            room = "ranked_" + uuid.uuid4().hex[:10]
            await db.execute(text(
                "INSERT INTO issued_room_regions (room_name, region, issued_at, player1_id, player2_id)"
                " VALUES (:r, 'eu', NOW() - INTERVAL '5 minutes', :a, :b)"), {"r": room, "a": pa, "b": pb})
        elif room_kind == "recorded":
            await lh._insert(db, "matches", {"player1_id": pa, "player2_id": pb, "winner_id": pa,
                                             "p1_rounds_won": 3, "p2_rounds_won": 1, "is_ranked": True,
                                             "photon_room_id": room, "series_id": rs,
                                             "reported_by_id": pa})
        await db.commit()
    await L._ban(sm, b)
    async with sm() as db:
        why = (await db.execute(text("SELECT invalidation_reason FROM ranked_series WHERE id = :i"),
                                {"i": rs})).scalar()
    assert why in main.BAN_VOID_REASONS, why
    return a, b, pa, pb, room


def _submit(a, b, room, ranked=True):
    lo, hi = sorted([a, b])
    rep = L._report(lo, hi, a, ranked)
    rep.photon_room_id = room
    return lambda db: main.submit_match(rep, L._req("/api/v1/matches"), db=db)


async def _attempt(sm, call):
    async with sm() as db:
        try:
            out = await call(db)
            await db.commit()
            return ("admitted", str(out)[:80])
        except HTTPException as e:
            await db.rollback()
            return (e.status_code, str(e.detail))


@pytest.mark.parametrize("room_kind", ROOMS)
@pytest.mark.parametrize("state", STATES)
def test_i_a_1v1_result_of_a_ban_ended_sitting_is_refused(case, soft, monkeypatch, state, room_kind):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")

    async def body(sm):
        a, b, pa, pb, room = await _world(sm, room_kind)
        await _set_state(sm, b, state)
        before = await _counts(sm, pa, pb)
        got = await _attempt(sm, _submit(a, b, room))
        return got, before, await _counts(sm, pa, pb)

    got, before, after = L._with_sm(case, body)
    want = "Banned: participant" if state == "active" else "series_ended_by_ban"
    assert got == (409, want) and after == before, (got, before, after)


@pytest.mark.parametrize("room_kind", ("queue", "private"))
def test_i_a_control_a_new_sitting_after_the_ban_is_admitted(case, soft, monkeypatch, room_kind):
    """No levelling down: once the ban is lifted, a queue room issued after the
    void, or a private room whose new series preflight created after it, is
    admitted and recorded."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")

    async def body(sm):
        a, b, pa, pb, _old = await _world(sm, room_kind)
        await _set_state(sm, b, "lifted")
        room = "bs_room_" + uuid.uuid4().hex[:8]
        async with sm() as db:
            if room_kind == "queue":
                room = "ranked_" + uuid.uuid4().hex[:10]
                await db.execute(text(
                    "INSERT INTO issued_room_regions (room_name, region, player1_id, player2_id)"
                    " VALUES (:r, 'eu', :a, :b)"), {"r": room, "a": pa, "b": pb})
            else:
                await lh._insert(db, "ranked_series", {"id": uuid.uuid4(), "player1_id": pa,
                                                       "player2_id": pb, "status": "active",
                                                       "is_private": True})
            await db.commit()
        got = await _attempt(sm, _submit(a, b, room))
        return got, await _counts(sm, pa, pb)

    got, after = L._with_sm(case, body)
    assert got[0] == "admitted" and after[0] == 1, (got, after)


def test_i_a_mutant_without_the_sitting_read_a_ban_ended_result_is_paid(case, soft, monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")

    async def none(*a, **k):
        return False
    monkeypatch.setattr(main, "_pair_sitting_ended_by_ban", none)

    async def body(sm):
        a, b, pa, pb, room = await _world(sm, "queue")
        await _set_state(sm, b, "run_out")
        before = await _counts(sm, pa, pb)
        got = await _attempt(sm, _submit(a, b, room))
        return got, before, await _counts(sm, pa, pb)

    got, before, after = L._with_sm(case, body)
    assert got[0] == "admitted" and after[0] == before[0] + 1, (got, before, after)


# ------------------------------------------------------------- (b) admin completion

async def _team_world(sm, ban_state):
    """A live 2v2 series whose member t2b holds a ban the void never saw (a
    row written directly), in `ban_state`."""
    sids = [L._sid() for _ in range(4)]
    async with sm() as db:
        pids = [await L._player(db, s) for s in sids]
        ts = uuid.uuid4()
        await lh._insert(db, "team_series", {"id": ts, "t1a_id": pids[0], "t1b_id": pids[1],
                                             "t2a_id": pids[2], "t2b_id": pids[3], "status": "active"})
        admin = await L._admin(db)
        await db.execute(text(
            "INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, banned_at)"
            " VALUES (:s, 'ban-sweep', :a, NOW())"), {"s": sids[3], "a": admin})
        await db.commit()
    await _set_state(sm, sids[3], ban_state)
    return sids, pids, ts


def _resolve(ts):
    return lambda db: L._call(main.admin_resolve_team_series, series_id=str(ts), action="complete",
                              winner_team=1, x_internal_key=INTERNAL_KEY, db=db)


async def _team_paid(sm, ts):
    async with sm() as db:
        return (await db.execute(text("SELECT status FROM team_series WHERE id = :i"), {"i": ts})).scalar()


@pytest.mark.parametrize("state", STATES)
def test_i_b_admin_completion_reads_the_rosters_bans_before_it_pays(case, soft, monkeypatch, state):
    monkeypatch.setenv("API_SECRET_KEY", INTERNAL_KEY)

    async def body(sm):
        sids, pids, ts = await _team_world(sm, state)
        got = await _attempt(sm, _resolve(ts))
        return got, await _team_paid(sm, ts)

    got, status = L._with_sm(case, body)
    if state == "active":
        assert got == (409, "Banned: participant") and status == "active", (got, status)
    else:
        assert got[0] == "admitted" and status == "completed", (got, status)


def test_i_b_mutant_without_the_roster_read_the_banned_roster_is_paid(case, soft, monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", INTERNAL_KEY)
    orig = main._ban_lock_and_gate

    async def no_read(db, steam_ids, request=None, actor=None, exclusive=()):
        if actor is None and request is None and not exclusive and len(list(steam_ids)) == 4:
            return None
        return await orig(db, steam_ids, request, actor=actor, exclusive=exclusive)
    monkeypatch.setattr(main, "_ban_lock_and_gate", no_read)

    async def body(sm):
        sids, pids, ts = await _team_world(sm, "active")
        got = await _attempt(sm, _resolve(ts))
        return got, await _team_paid(sm, ts)

    got, status = L._with_sm(case, body)
    assert got[0] == "admitted" and status == "completed", (got, status)
