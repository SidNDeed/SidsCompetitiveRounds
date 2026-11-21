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
from ban_sweep_pg_bounds import bounded_pg  # noqa: E402,F401  (autouse: every session bounded)
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
                                             "reported_by": pa})
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
            "INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
            " VALUES (:s, 'ban-sweep', :a, NOW(), NOW() + INTERVAL '1 hour')"), {"s": sids[3], "a": admin})
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


# ---------------------------------------------------------------- FIX-3 2 a
# The tournament-room cell, and one mutant per rule of _pair_sitting_ended_by_ban,
# each red in its own cell. In every refusal cell below the pair also has a
# series created after the void (`newer`), so the private-room rule alone would
# admit the report: the refusal is the named rule's own.

async def _tournament_bind(sm, room, series_id):
    async with sm() as db:
        # This file's database serves all its tests, and migration 089's unique
        # index uniq_tournaments_active_per_kind admits one tournament of a kind in
        # a status before completion (voting, locked, running; a new row is
        # 'voting'). So a second call reuses the sync tournament that stands. The
        # reads under test (_TM_ROOM_MATCH_SQL in main) select from
        # tournament_matches alone and never read the tournaments row.
        tid = (await db.execute(text(
            "SELECT id FROM tournaments WHERE kind = 'sync'"
            " AND status IN ('voting', 'locked', 'running') LIMIT 1"))).scalar()
        if tid is None:
            tid = uuid.uuid4()
            await db.execute(text(
                # kind is a column of tournaments (sql/047), not of tournament_matches
                "INSERT INTO tournaments (id, kind, default_start_ts, lock_at)"
                " VALUES (:t, 'sync', NOW(), NOW())"), {"t": tid})
        # The shared tournament's matches take the next free slot: sql/047 keeps
        # (tournament_id, round, bracket_side, slot_idx) unique, and the reads
        # under test never read the slot.
        slot = (await db.execute(text(
            "SELECT COALESCE(MAX(slot_idx) + 1, 0) FROM tournament_matches"
            " WHERE tournament_id = :t AND round = 1 AND bracket_side = 'W'"), {"t": tid})).scalar()
        await db.execute(text(
            # every NOT NULL column named: in this case schema the ORM built the
            # array columns without their migration defaults (sql/049, sql/132)
            "INSERT INTO tournament_matches (id, tournament_id, round, bracket_side, slot_idx, prereq_match_ids,"
            " prereq_roles, early_ok_signup_ids, is_bye, status, series_id, photon_room_name)"
            " VALUES (:i, :t, 1, 'W', :slot, '{}', '{}', '{}', false, 'pending', :s, :r)"),
            {"i": uuid.uuid4(), "t": tid, "slot": slot, "s": series_id, "r": room})
        await db.commit()


async def _newer_series(sm, pa, pb):
    async with sm() as db:
        sid = uuid.uuid4()
        await lh._insert(db, "ranked_series", {"id": sid, "player1_id": pa, "player2_id": pb,
                                               "status": "active"})
        await db.commit()
    return sid


async def _ended_series(sm, pa, pb):
    async with sm() as db:
        return (await db.execute(text(
            "SELECT id FROM ranked_series WHERE invalidation_reason = ANY(CAST(:w AS text[]))"
            " AND ((player1_id = :a AND player2_id = :b) OR (player1_id = :b AND player2_id = :a))"),
            {"w": sorted(main.BAN_VOID_REASONS), "a": pa, "b": pb})).scalar()


def _rule_cell(cell):
    """cell: tournament_ended, tournament_live, recorded, queue, private."""
    async def body(sm):
        kind = {"tournament_ended": "private", "tournament_live": "private",
                "recorded": "recorded", "queue": "queue", "private": "private"}[cell]
        a, b, pa, pb, room = await _world(sm, kind)
        await _set_state(sm, b, "run_out" if cell != "tournament_live" else "lifted")
        ended = await _ended_series(sm, pa, pb)
        if cell.startswith("tournament"):
            room = "bs_tm_" + uuid.uuid4().hex[:8]
        if cell != "private":
            newer = await _newer_series(sm, pa, pb)
        if cell == "tournament_ended":
            await _tournament_bind(sm, room, ended)
        elif cell == "tournament_live":
            await _tournament_bind(sm, room, newer)
        before = await _counts(sm, pa, pb)
        got = await _attempt(sm, _submit(a, b, room))
        return got, before, await _counts(sm, pa, pb)
    return body


_RULE_MUTANTS = {
    "tournament_ended": ("        if bound:\n            return any(", "        if False:\n            return any("),
    "recorded": ("                {\"room\": room, \"ids\": ids})).first() is not None:\n",
                 "                {\"room\": room, \"ids\": ids})).first() is not None and False:\n"),
    "queue": ("            return not stamps or issued <= max(stamps)\n", "            return not stamps\n"),
    "private": ("    return newer is None\n", "    return False\n"),
}


def _rule_mutant(old, new):
    import inspect
    import textwrap
    src = textwrap.dedent(inspect.getsource(main._pair_sitting_ended_by_ban))
    assert src.count(old) == 1, old
    ns = dict(vars(main))
    exec(compile(src.replace(old, new), "<mutant>", "exec"), ns)
    return ns["_pair_sitting_ended_by_ban"]


@pytest.mark.parametrize("cell", sorted(_RULE_MUTANTS))
def test_i_a_each_rule_refuses_its_own_cell(case, soft, monkeypatch, cell):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")
    got, before, after = L._with_sm(case, _rule_cell(cell))
    assert got == (409, "series_ended_by_ban") and after == before, (got, before, after)


@pytest.mark.parametrize("cell", sorted(_RULE_MUTANTS))
def test_i_a_mutant_per_rule_its_cell_is_admitted(case, soft, monkeypatch, cell):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")
    monkeypatch.setattr(main, "_pair_sitting_ended_by_ban", _rule_mutant(*_RULE_MUTANTS[cell]))
    got, before, after = L._with_sm(case, _rule_cell(cell))
    # admitted: the refusal of the fixed rule is gone (in the recorded cell the
    # route answers with the game already recorded in that room, no new row)
    assert got[0] == "admitted", (got, before, after)


def test_i_a_control_a_tournament_room_bound_to_a_live_series_is_admitted(case, soft, monkeypatch):
    """The pair has a series the void ended; the room is bound to the bracket
    match of a series the void did not end: admitted and recorded."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")
    got, before, after = L._with_sm(case, _rule_cell("tournament_live"))
    assert got[0] == "admitted" and after[0] == before[0] + 1, (got, before, after)
