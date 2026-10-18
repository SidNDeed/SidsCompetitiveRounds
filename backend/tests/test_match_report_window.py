"""The report window rules of Stage 2 design V3 S5 (match_report_window.py).

T5.3 runs on the helper with recorded timestamps (no database); T5.4 runs
the settle driver against a stub settle callable on a cf_pg case schema
(383 in the build); T7.1 covers the game-id canonical.

MATCH_HOLD_SRC, when set, names a directory holding mutant copies of the
Stage 2 modules; it is put first on sys.path and the census proves the copy
is the module in use (#742, #838).
"""

import asyncio
import hashlib
import hmac as _hmac
import inspect
import itertools
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
sys.path.insert(0, API)
sys.path.insert(0, HERE)
SRC = os.environ.get("MATCH_HOLD_SRC") or ""
if SRC:
    sys.path.insert(0, SRC)

import match_report_window as mrw  # noqa: E402

SECRET = "rjs2-test-secret"
W30 = timedelta(minutes=30)
T0 = datetime(2026, 1, 5, 12, 0, 0, tzinfo=timezone.utc)


def at(minutes, seconds=0):
    return T0 + timedelta(minutes=minutes, seconds=seconds)


def hold(anchor, until=None, closed=None):
    return {"held_anchor_at": anchor, "held_until": until or anchor + timedelta(seconds=120),
            "closed_at": closed}


def today(row, now):
    """The freshness of today (backend/api/main.py:46729-46735 at 9267b1fe)."""
    return any(row.get(c) is not None and (now - row[c]) < W30
               for c in ("created_at", "room_issued_at", "last_game_at"))


def test_module_census():
    want = os.path.normcase(os.path.normpath(SRC or API))
    got = os.path.normcase(os.path.dirname(os.path.abspath(mrw.__file__)))
    assert got == want, (got, want)
    for fn in (mrw.settle_window, mrw.receive, mrw.release_held, mrw.supersede_held):
        assert "async with database_deadline(db)" in inspect.getsource(fn)
    assert "await _settle_locked(" in inspect.getsource(mrw._receive)


# == T5.3 the window =============================================================

RECORDED = [
    {"created_at": at(0), "room_issued_at": at(1), "last_game_at": None},
    {"created_at": at(0), "room_issued_at": None, "last_game_at": at(12)},
    {"created_at": at(-40), "room_issued_at": at(-35), "last_game_at": at(-31)},
    {"created_at": at(-20), "room_issued_at": None, "last_game_at": None},
]


def test_t5_3_no_hold_equals_today_on_recorded_rows():
    """With no holds every recorded row reads exactly as today, at every
    probe instant from 0 to 60 minutes."""
    for row in RECORDED:
        for m in range(0, 61, 3):
            now = at(m)
            assert mrw.series_fresh(row, [], now=now, window=W30) == today(row, now), (row, m)


def test_t5_3_overlap_per_anchor_sweep_end_relock_and_newer_anchor():
    """Delayed sweep: an unclosed hold counts only up to held_until. Early
    end: a closed hold counts only up to closed_at. Two holds separated by a
    relock both count, each only after the anchor. A newer last_game_at
    gains nothing from holds before it (no banked time)."""
    v = at(0)
    unswept = hold(at(10))                                   # 120 s, never closed
    assert mrw.held_overlap([unswept], v, at(40)) == timedelta(seconds=120)
    early = hold(at(10), closed=at(10, 45))
    assert mrw.held_overlap([early], v, at(40)) == timedelta(seconds=45)
    second = hold(at(20))
    assert mrw.held_overlap([early, second], v, at(40)) == timedelta(seconds=165)
    assert mrw.held_overlap([unswept], v, at(11)) == timedelta(seconds=60)
    # an anchor at 31:00 is stale today at 30 min + 1 s after it; with one
    # 120 s hold after it, fresh until 32:00 after it
    v = at(0)
    late_hold = hold(at(5))
    assert not mrw.anchor_fresh(v, [], now=at(30, 1), window=W30)
    assert mrw.anchor_fresh(v, [late_hold], now=at(31, 59), window=W30)
    assert not mrw.anchor_fresh(v, [late_hold], now=at(32, 0), window=W30)
    # repeated lapses never bank: holds before the anchor give nothing
    newer = at(15)
    old = [hold(at(1)), hold(at(4)), hold(at(9))]
    for m in (40, 45, 46):
        assert mrw.anchor_fresh(newer, old, now=at(m), window=W30) == \
            mrw.anchor_fresh(newer, [], now=at(m), window=W30), m
    row = {"created_at": at(0), "room_issued_at": None, "last_game_at": newer}
    assert not mrw.series_fresh(row, old, now=at(45, 1), window=W30)
    # a hold straddling the anchor counts only its part after the anchor
    straddle = hold(at(14))                                  # 14:00 to 16:00
    assert mrw.held_overlap([straddle], newer, at(40)) == timedelta(seconds=60)


class _Skew(datetime):
    delta = timedelta(0)

    @classmethod
    def now(cls, tz=None):
        return datetime.now(tz) + cls.delta


@pytest.mark.parametrize("skew", [timedelta(hours=2), timedelta(hours=-2)])
def test_t5_3_application_skew_and_long_transaction(monkeypatch, skew):
    """Positive and negative application skew change nothing: the answer is
    a function of the passed `now` alone, including a `now` read at the start
    of a long transaction that the application clock has long passed. `now`
    has no default."""
    _Skew.delta = skew
    monkeypatch.setattr(mrw, "datetime", _Skew, raising=False)
    for row in RECORDED:
        for m in range(0, 61, 7):
            holds = [hold(at(5)), hold(at(20), closed=at(20, 30))]
            got = mrw.series_fresh(row, holds, now=at(m), window=W30)
            manual = any(row.get(c) is not None and
                         (at(m) - row[c]) - sum(
                             (max(timedelta(0), min(min(h["closed_at"] or h["held_until"],
                                                        h["held_until"]), at(m))
                                  - max(h["held_anchor_at"], row[c])) for h in holds),
                             timedelta(0)) < W30
                         for c in ("created_at", "room_issued_at", "last_game_at"))
            assert got == manual, (row, m)
    for fn in (mrw.anchor_fresh, mrw.series_fresh):
        p = inspect.signature(fn).parameters["now"]
        assert p.default is inspect.Parameter.empty and p.kind is p.KEYWORD_ONLY
    with pytest.raises(TypeError):
        mrw.series_fresh(RECORDED[0], [], window=W30)


# == T7.1 the game-id canonical ======================================================

def test_t7_1_game_id_canonical_one_field_at_a_time():
    """Changing any one of the three fields makes the game-id signature
    reject; the canonical is its own message (the hold-open canonical of the
    same values is a different string)."""
    g, rep, room = str(uuid.uuid4()), "s2rep", "team_room1"
    sig = _hmac.new(SECRET.encode(), mrw.game_id_canonical(g, rep, room).encode(),
                    hashlib.sha256).hexdigest()
    assert mrw.game_id_canonical(g, rep, room) == "game-id:%s:%s:%s" % (g, rep, room)
    assert mrw.verify_game_id(SECRET, g, rep, room, sig)
    assert not mrw.verify_game_id(SECRET, str(uuid.uuid4()), rep, room, sig)
    assert not mrw.verify_game_id(SECRET, g, "s2rep2", room, sig)
    assert not mrw.verify_game_id(SECRET, g, rep, "team_room2", sig)
    assert not mrw.verify_game_id(SECRET, g, rep, room, "0" * 64)
    import match_hold
    other = match_hold.hold_open_canonical("team", room, g, rep, 0, 0, rep)
    assert other != mrw.game_id_canonical(g, rep, room)


# == T5.4 the server matrix, against a stub settle callable ===========================

def _run(coro):
    return asyncio.run(coro)


async def _three_players(conn):
    out = []
    for i in range(3):
        steam = "s3%d%s" % (i, uuid.uuid4().hex[:8])      # equal length, ordered by i
        pid = await conn.fetchval(
            "INSERT INTO players (steam_id, display_name) VALUES ($1, 'w') RETURNING id", steam)
        out.append((pid, steam))
    return out


async def _window_game(conn, mode, room):
    return await conn.fetchval(
        "INSERT INTO match_games (mode, series_id, room_name, seq) "
        "VALUES ($1, gen_random_uuid(), $2, 1) RETURNING id", mode, room)


async def _entered(conn, mode, room, g, pid, opener):
    await conn.execute(
        "INSERT INTO match_seat_holds (mode, room_name, series_id, game_id, player_id, n, slot, "
        " team, opener_player_id, held_anchor_at, held_at, held_until, entered_at, closed_at, "
        " closed_reason) SELECT $1, $2, series_id, $3, $4, 1, 0, 0, $5, clock_timestamp(), "
        " clock_timestamp(), clock_timestamp() + interval '2 minutes', clock_timestamp(), "
        " clock_timestamp(), 'entered' FROM match_games WHERE id = $3", mode, room, g, pid, opener)


def test_t5_4_matrix_every_class_assignment_both_modes(monkeypatch):
    """T5.4: for both modes, every assignment of classes C, R and unclassed
    to three filers, in arrival order and reversed, with no fresh beat (so
    nothing settles at receipt): every report answers journaled; the expired
    window settles exactly once, through the stub, the first non-empty class
    by lowest Steam id; a second settle and a later report settle nothing
    (the late report answers duplicate)."""
    import cf_pg
    cf_pg.require_live_pg()

    async def go():
        async with cf_pg.case("rjs2w") as (c, sm):
            conn = c.conn
            seats = await _three_players(conn)
            settled = []

            async def stub(db, entry):
                settled.append(entry)

            for mode in ("team", "ovt"):
                for classes in itertools.product("cru", repeat=3):
                    for order in ((0, 1, 2), (2, 1, 0)):
                        room = "%s_w%s" % (mode, uuid.uuid4().hex[:10])
                        g = await _window_game(conn, mode, room)
                        for i, cls in enumerate(classes):
                            if cls == "r":
                                await _entered(conn, mode, room, g, seats[i][0], seats[0][0])
                        for i in order:
                            async with sm() as db:
                                now = await _db_now(db)
                                out = await mrw.receive(
                                    db, mode=mode, room=room, game_id=g,
                                    reported_game_id=(None if classes[i] == "u" else g),
                                    reporter_id=seats[i][0], reporter_steam=seats[i][1],
                                    payload='{"seat": %d}' % i, member_ids=[s[0] for s in seats],
                                    now=now, settle=stub)
                                await db.commit()
                            assert out == {"status": "journaled", "cls": classes[i]}, \
                                (classes, order, out)
                        before = len(settled)
                        later = None
                        async with sm() as db:
                            now = await _db_now(db) + timedelta(seconds=31)
                            done = await mrw.settle_window(db, mode=mode, room=room, game_id=g,
                                                           now=now, settle=stub)
                            again = await mrw.settle_window(db, mode=mode, room=room, game_id=g,
                                                            now=now, settle=stub)
                            later = await mrw.receive(
                                db, mode=mode, room=room, game_id=g, reported_game_id=g,
                                reporter_id=seats[0][0], reporter_steam=seats[0][1],
                                payload="{}", member_ids=[], now=now, settle=stub)
                            await db.commit()
                        assert again is None and later == {"status": "duplicate"}
                        assert len(settled) == before + 1, (classes, order)
                        rank = {"c": 0, "r": 1, "u": 2}
                        want = min(range(3), key=lambda i: (rank[classes[i]], i))
                        got = settled[-1]
                        assert (got["reporter_steam"], got["cls"]) == \
                            (seats[want][1], classes[want]), (classes, order, got)
                        assert done["reporter_steam"] == seats[want][1]
                        rows = await conn.fetch(
                            "SELECT reporter_id, state FROM match_report_journal "
                            " WHERE room_name = $1", room)
                        assert sorted(r["state"] for r in rows) == ["kept", "kept", "settled"]
                        win = await conn.fetchrow(
                            "SELECT settled_at, settled_reporter_id, settled_cls "
                            "  FROM match_report_windows WHERE room_name = $1", room)
                        assert (win["settled_reporter_id"], win["settled_cls"]) == \
                            (seats[want][0], classes[want])
    _run(go())


async def _db_now(db):
    from sqlalchemy import text
    return (await db.execute(text("SELECT clock_timestamp()"))).scalar()


def test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c(monkeypatch):
    """At receipt: a class R report and a higher-Steam-id class C report are
    journaled while a lower class C fighter beats; the lowest fresh class C
    fighter's report settles at once, exactly once; a class C fighter with
    no fresh beat is not waited for; a held game-over settles nothing until
    released, and a superseded one never. M2 also proves every public window
    operation bounds a blocked row and nested receipt settlement installs one
    database budget."""
    import cf_pg
    import match_hold
    cf_pg.require_live_pg()

    async def go():
        async with cf_pg.case("rjs2w") as (c, sm):
            conn = c.conn
            seats = await _three_players(conn)
            ids = [s[0] for s in seats]
            settled = []

            async def stub(db, entry):
                settled.append(entry)

            async def rec(room, g, i, held=False, reported=True):
                async with sm() as db:
                    out = await mrw.receive(
                        db, mode="team", room=room, game_id=g,
                        reported_game_id=g if reported else None, reporter_id=seats[i][0],
                        reporter_steam=seats[i][1], payload="{}", member_ids=ids,
                        now=await _db_now(db), settle=stub, held=held)
                    await db.commit()
                return out

            async def beat(room, i, age=0):
                await conn.execute(
                    "INSERT INTO match_seat_presence (room_name, player_id, mode, series_id, "
                    " present_at, beat_at) VALUES ($1, $2, 'team', gen_random_uuid(), "
                    " clock_timestamp(), clock_timestamp() - make_interval(secs => $3))",
                    room, seats[i][0], float(age))

            room = "team_r" + uuid.uuid4().hex[:8]
            g = await _window_game(conn, "team", room)
            await _entered(conn, "team", room, g, seats[0][0], seats[1][0])
            for i in range(3):
                await beat(room, i)
            assert await rec(room, g, 0) == {"status": "journaled", "cls": "r"}
            assert await rec(room, g, 2) == {"status": "journaled", "cls": "c"}
            assert settled == []
            assert await rec(room, g, 1) == {"status": "settled", "cls": "c"}
            assert [e["reporter_steam"] for e in settled] == [seats[1][1]]
            assert await rec(room, g, 1) == {"status": "duplicate"}
            assert len(settled) == 1

            room = "team_r" + uuid.uuid4().hex[:8]
            g = await _window_game(conn, "team", room)
            await beat(room, 0, age=40)
            await beat(room, 1)
            await beat(room, 2)
            assert await rec(room, g, 1) == {"status": "settled", "cls": "c"}
            assert settled[-1]["reporter_steam"] == seats[1][1]

            room = "team_r" + uuid.uuid4().hex[:8]
            g = await _window_game(conn, "team", room)
            for i in range(3):
                await beat(room, i)
            assert (await rec(room, g, 0, held=True))["state"] == "held"
            assert (await rec(room, g, 1, held=True))["state"] == "held"
            n = len(settled)
            async with sm() as db:
                now = await _db_now(db)
                assert await mrw.settle_window(db, mode="team", room=room, game_id=g,
                                               now=now + timedelta(seconds=31),
                                               settle=stub) is None
                assert await mrw.release_held(db, mode="team", room=room, game_id=g,
                                              now=now) == 2
                assert await mrw.settle_window(db, mode="team", room=room, game_id=g,
                                               now=now + timedelta(seconds=29),
                                               settle=stub) is None
                done = await mrw.settle_window(db, mode="team", room=room, game_id=g,
                                               now=now + timedelta(seconds=31), settle=stub)
                await db.commit()
            assert done["reporter_steam"] == seats[0][1] and len(settled) == n + 1

            room = "team_r" + uuid.uuid4().hex[:8]
            g = await _window_game(conn, "team", room)
            await rec(room, g, 0, held=True)
            async with sm() as db:
                now = await _db_now(db)
                assert await mrw.supersede_held(db, mode="team", room=room, game_id=g,
                                                now=now) == 1
                assert await mrw.settle_window(db, mode="team", room=room, game_id=g,
                                               now=now + timedelta(seconds=31),
                                               settle=stub) is None
                await db.commit()
            assert await conn.fetchval(
                "SELECT state FROM match_report_journal WHERE room_name = $1", room) == \
                "superseded"
            assert len(settled) == n + 1

            # H4: once the stored window expires, a later better C cannot
            # enter the journal or displace evidence received in-window.
            room = "team_r" + uuid.uuid4().hex[:8]
            g = await _window_game(conn, "team", room)
            await _entered(conn, "team", room, g, seats[1][0], seats[0][0])
            assert await rec(room, g, 1) == {"status": "journaled", "cls": "r"}
            assert await rec(room, g, 2) == {"status": "journaled", "cls": "c"}
            settle_after = await conn.fetchval(
                "SELECT settle_after FROM match_report_windows"
                " WHERE room_name = $1 AND game_id = $2", room, g)
            before = len(settled)
            async with sm() as db:
                late = await mrw.receive(
                    db, mode="team", room=room, game_id=g, reported_game_id=g,
                    reporter_id=seats[0][0], reporter_steam=seats[0][1],
                    payload='{"late": true}', member_ids=ids,
                    now=settle_after + timedelta(seconds=1), settle=stub)
                await db.commit()
            assert late == {"status": "duplicate"}
            assert len(settled) == before + 1
            assert (settled[-1]["reporter_steam"], settled[-1]["cls"]) == \
                (seats[2][1], "c")
            rows = await conn.fetch(
                "SELECT reporter_id, state FROM match_report_journal"
                " WHERE room_name = $1 AND game_id = $2 ORDER BY reporter_steam", room, g)
            assert {r["reporter_id"] for r in rows} == {seats[1][0], seats[2][0]}
            assert sorted(r["state"] for r in rows) == ["kept", "settled"]

            # H6: a retry can trigger settlement, but only the first payload
            # accepted into the journal is authoritative.
            room = "team_r" + uuid.uuid4().hex[:8]
            g = await _window_game(conn, "team", room)
            await beat(room, 0)
            await beat(room, 2)
            receipt = await conn.fetchval("SELECT clock_timestamp()")

            async def receive_payload(payload):
                async with sm() as db:
                    out = await mrw.receive(
                        db, mode="team", room=room, game_id=g, reported_game_id=g,
                        reporter_id=seats[2][0], reporter_steam=seats[2][1],
                        payload=payload, member_ids=ids, now=receipt, settle=stub)
                    await db.commit()
                return out

            before = len(settled)
            assert await receive_payload('{"proof": "A"}') == \
                {"status": "journaled", "cls": "c"}
            await conn.execute(
                "UPDATE match_seat_presence"
                " SET beat_at = $1 - interval '26 seconds'"
                " WHERE room_name = $2 AND player_id = $3", receipt, room, seats[0][0])
            assert await receive_payload('{"proof": "B"}') == \
                {"status": "settled", "cls": "c"}
            assert len(settled) == before + 1
            settled_payload = settled[-1]["payload"]
            if isinstance(settled_payload, str):
                settled_payload = json.loads(settled_payload)
            assert settled_payload == {"proof": "A"}
            stored = await conn.fetchrow(
                "SELECT payload ->> 'proof' AS proof, state"
                " FROM match_report_journal WHERE room_name = $1 AND game_id = $2", room, g)
            assert (stored["proof"], stored["state"]) == ("A", "settled")

            for operation in ("settle", "receive", "release", "supersede"):
                room = "m2_%s_%s" % (operation, uuid.uuid4().hex[:8])
                game_id = await _window_game(conn, "team", room)
                now = await conn.fetchval("SELECT clock_timestamp()")
                await conn.execute(
                    "INSERT INTO match_report_windows"
                    " (room_name, game_id, mode, opened_at, settle_after)"
                    " VALUES ($1, $2, 'team', $3::timestamptz - interval '31 seconds',"
                    "         $3::timestamptz - interval '1 second')", room, game_id, now)
                state = "held" if operation in ("release", "supersede") else "journaled"
                if operation != "receive":
                    await conn.execute(
                        "INSERT INTO match_report_journal"
                        " (room_name, game_id, reporter_id, mode, reporter_steam, cls, state,"
                        "  payload, received_at) VALUES ($1, $2, $3, 'team', $4, 'c', $5,"
                        "  '{}'::jsonb, $6 - interval '2 seconds')",
                        room, game_id, seats[0][0], seats[0][1], state, now)

                blocker = await cf_pg.harness.connect_bound(c.dsn, c.schema)
                transaction = blocker.transaction()
                await transaction.start()
                await blocker.execute(
                    "SELECT 1 FROM match_report_windows"
                    " WHERE room_name = $1 AND game_id = $2 FOR UPDATE", room, game_id)
                before_settled = len(settled)
                started = asyncio.get_running_loop().time()
                try:
                    async with sm() as db:
                        if operation == "settle":
                            call = mrw.settle_window(
                                db, mode="team", room=room, game_id=game_id,
                                now=now, settle=stub)
                        elif operation == "receive":
                            call = mrw.receive(
                                db, mode="team", room=room, game_id=game_id,
                                reported_game_id=game_id, reporter_id=seats[0][0],
                                reporter_steam=seats[0][1], payload="{}",
                                member_ids=[s[0] for s in seats], now=now, settle=stub)
                        elif operation == "release":
                            call = mrw.release_held(
                                db, mode="team", room=room, game_id=game_id, now=now)
                        else:
                            call = mrw.supersede_held(
                                db, mode="team", room=room, game_id=game_id, now=now)
                        with pytest.raises(HTTPException) as caught:
                            await asyncio.wait_for(call, 7.5)
                        elapsed = asyncio.get_running_loop().time() - started
                        assert (caught.value.status_code, caught.value.detail) == \
                            (503, "database_deadline")
                        assert 4.0 <= elapsed < 7.0, (operation, elapsed)
                        assert db.info.get(match_hold._DB_DEADLINE_INFO) is None
                finally:
                    await transaction.rollback()
                    await blocker.close()

                window = await conn.fetchrow(
                    "SELECT settled_at FROM match_report_windows"
                    " WHERE room_name = $1 AND game_id = $2", room, game_id)
                rows = await conn.fetch(
                    "SELECT state FROM match_report_journal"
                    " WHERE room_name = $1 AND game_id = $2", room, game_id)
                assert window["settled_at"] is None
                assert [row["state"] for row in rows] == \
                    ([] if operation == "receive" else [state])
                assert len(settled) == before_settled

            setups = 0
            original_setup = match_hold._install_database_timeouts

            async def counted_setup(db):
                nonlocal setups
                setups += 1
                await original_setup(db)

            monkeypatch.setattr(match_hold, "_install_database_timeouts", counted_setup)
            room = "m2_nested_" + uuid.uuid4().hex[:8]
            game_id = await _window_game(conn, "team", room)
            now = await conn.fetchval("SELECT clock_timestamp()")
            async with sm() as db:
                answer = await mrw.receive(
                    db, mode="team", room=room, game_id=game_id, reported_game_id=None,
                    reporter_id=seats[0][0], reporter_steam=seats[0][1], payload="{}",
                    member_ids=[s[0] for s in seats], now=now, settle=stub)
                assert db.info.get(match_hold._DB_DEADLINE_INFO) is None
                await db.commit()
            assert answer == {"status": "journaled", "cls": "u"}
            assert setups == 1

    _run(go())
