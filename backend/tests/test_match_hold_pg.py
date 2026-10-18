"""The 2v2 and 1v2 readmission server half (Stage 2 design V3), against a
local PostgreSQL through cf_pg (one case schema per case, 383 in the build).

The router of backend/api/match_hold.py is mounted on a test app of its own
(main.py does not include it until NX1 of the build brief) and every route
is called through HTTP with a session bound to the case schema. The Steam
session check of main is replaced by a fixture that accepts exactly the
token "tok:<steam id>" for the claimed id and answers 401 otherwise, so a
route that skips the check, or checks the wrong id, is visible.

MATCH_HOLD_SRC, when set, names a directory holding a MUTANT copy of
match_hold.py; it is put first on sys.path, and the module census below
proves the copy is the module the routes run (#742, #838). The mutation
runner (backend/tests/evidence/match-hold-mutation-runner.py) sets it.
"""

import asyncio
import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
sys.path.insert(0, API)
sys.path.insert(0, HERE)
SRC = os.environ.get("MATCH_HOLD_SRC") or ""

import cf_pg  # noqa: E402
import httpx  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402

import database  # noqa: E402
import main  # noqa: E402

# The mutant directory goes first only now: the imports above put the api
# directory back at the head of sys.path, which hid the copy (census, run
# rj-s2s-N2-mut1).
if SRC:
    sys.path.insert(0, SRC)
import match_hold  # noqa: E402

SECRET = "rjs2-test-secret"


def test_module_census():
    """The match_hold the routes run is the one this run names: the mutant
    copy when MATCH_HOLD_SRC is set, the tracked file otherwise."""
    want = os.path.normcase(os.path.normpath(SRC or API))
    got = os.path.normcase(os.path.dirname(os.path.abspath(match_hold.__file__)))
    assert got == want, (got, want)
    assert sys.modules["match_hold"] is match_hold


def _run(coro):
    return asyncio.run(coro)


async def _fake_session(request, steam_id, db):
    token = request.headers.get("X-Session-Token") if request is not None else None
    if token != "tok:" + str(steam_id):
        raise HTTPException(401, "session")
    request.state.scr_session_verified = True


class _SessionLookupErrorDB:
    async def execute(self, *args, **kwargs):
        raise RuntimeError("session lookup unavailable")


@pytest.mark.parametrize("method,path,body,params", [
    ("POST", "/game/start",
     {"steam_id": "s2auth", "mode": "team", "series_id": str(uuid.uuid4()), "room": "r"}, None),
    ("POST", "/hold/beat",
     {"steam_id": "s2auth", "mode": "team", "series_id": str(uuid.uuid4()), "room": "r"}, None),
    ("POST", "/hold/open",
     {"request_id": "authreq1", "opener_steam_id": "s2auth", "mode": "team", "room": "r",
      "game_id": str(uuid.uuid4()), "held_steam_id": "s2held", "slot": 0, "team": 0,
      "t1_points": 0, "t2_points": 0, "hmac": "invalid"}, None),
    ("GET", f"/hold/{uuid.uuid4()}/state", None, {"steam_id": "s2auth"}),
    ("GET", "/hold/by-room", None,
     {"room": "r", "game_id": str(uuid.uuid4()), "steam_id": "s2auth"}),
    ("POST", f"/hold/{uuid.uuid4()}/end", {"steam_id": "s2auth", "reason": "refused"}, None),
    ("GET", "/hold/mine", None, {"steam_id": "s2auth"}),
    ("POST", f"/hold/{uuid.uuid4()}/claim", {"steam_id": "s2auth"}, None),
    ("POST", f"/hold/{uuid.uuid4()}/bind", {"steam_id": "s2auth", "actor": 1}, None),
    ("POST", f"/hold/{uuid.uuid4()}/entered",
     {"steam_id": "s2auth", "game_id": str(uuid.uuid4()), "actor": 1}, None),
])
def test_h1_real_helper_soft_fail_paths_require_verified_session(
        monkeypatch, method, path, body, params):
    """Log-only and lookup-error returns never authorize a stage 2 route."""
    real_check = main._check_steam_session
    app = FastAPI()
    app.include_router(match_hold.router)

    async def _db():
        yield _SessionLookupErrorDB()

    app.dependency_overrides[database.get_db] = _db
    monkeypatch.setattr(main, "_check_steam_session", real_check)
    monkeypatch.setattr(main.os, "getenv", lambda *args, **kwargs: "")

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            route = "/api/v1/match" + path
            log_only = await client.request(method, route, json=body, params=params)
            lookup_error = await client.request(
                method, route, json=body, params=params,
                headers={"X-Session-Token": "unavailable"})
        for response in (log_only, lookup_error):
            assert response.status_code == 401
            assert response.json() == {"detail": "session_required"}

    _run(exercise())


class Env:
    """One case: the schema, a session maker bound to it, and a test app
    with the match_hold router mounted."""

    def __init__(self, c, sm, monkeypatch):
        self.c, self.sm, self.conn = c, sm, c.conn
        app = FastAPI()
        app.include_router(match_hold.router)

        async def _db():
            async with sm() as s:
                yield s
        app.dependency_overrides[database.get_db] = _db
        self.app = app
        monkeypatch.setattr(main, "_check_steam_session", _fake_session)
        monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)

    async def call(self, method, path, steam, body=None, params=None, token=None):
        headers = {"X-Session-Token": token if token is not None else "tok:" + steam}
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as cl:
            r = await cl.request(method, path, json=body, params=params, headers=headers)
        return r

    async def post(self, path, steam, body, **kw):
        return await self.call("POST", path, steam, body=body, **kw)

    async def get(self, path, steam, params=None, **kw):
        return await self.call("GET", path, steam, params=params, **kw)


def run_env(monkeypatch, body, prefix="rjs2"):
    cf_pg.require_live_pg()

    async def inside():
        async with cf_pg.case(prefix) as (c, sm):
            await body(Env(c, sm, monkeypatch))
    _run(inside())


# -- seeding ------------------------------------------------------------------

async def seed_players(conn, n):
    out = []
    for _ in range(n):
        steam = "s2" + uuid.uuid4().hex[:12]
        pid = await conn.fetchval(
            "INSERT INTO players (steam_id, display_name) VALUES ($1, $2) RETURNING id",
            steam, "rjs2 " + steam[-4:])
        out.append((pid, steam))
    return out


async def queue_row(conn, mode, pid, steam, caps, series_id=None):
    """A queue row of `mode`: matched into `series_id`, or (None) a search
    or hosted lobby seat."""
    status = "matched" if series_id else "searching"
    if mode == "team":
        await conn.execute(
            "INSERT INTO team_queue (player_id, steam_id, display_name, rating, "
            " rating_deviation, completed_series, fallback_rating, status, ready, joined_at, "
            " queue_type, seen_settings_version, caps, series_id) "
            "VALUES ($1, $2, 'q', 1500, 350, 0, 1500, $4, FALSE, clock_timestamp(), "
            " 'auto', 0, $3, $5)", pid, steam, caps, status, series_id)
    else:
        await conn.execute(
            "INSERT INTO ovt_queue (player_id, steam_id, display_name, status, caps, series_id) "
            "VALUES ($1, $2, 'q', $4, $3, $5)", pid, steam, caps, status, series_id)


class Series:
    def __init__(self, mode, sid, room, seats):
        self.mode, self.sid, self.room, self.seats = mode, sid, room, seats

    def steam(self, i):
        return self.seats[i][1]

    def pid(self, i):
        return self.seats[i][0]


async def seed_series(conn, mode="team", flag=True, caps=None, room=None, queue=True,
                      status="active"):
    """A series of `mode` with its members' queue rows; flagged for `room`
    unless flag=False. Seat i is slot i: team = i // 2 (team), i > 0 (ovt)."""
    n = 4 if mode == "team" else 3
    seats = await seed_players(conn, n)
    room = room or ("%s_%s" % (mode, uuid.uuid4().hex[:8]))
    pids = [p for p, _ in seats]
    if mode == "team":
        sid = await conn.fetchval(
            "INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id, t1_series_wins, "
            " t2_series_wins, status, rebalance_count, created_at, spawn_confirmations, "
            " spawn_confirmed_by, photon_room_id, region) VALUES (gen_random_uuid(), "
            " $1, $2, $3, $4, 0, 0, $5, 0, clock_timestamp(), 0, '[]'::jsonb, $6, 'eu') "
            "RETURNING id", *pids, status, room)
    else:
        sid = await conn.fetchval(
            "INSERT INTO ovt_series (solo_id, duo_a_id, duo_b_id, status, photon_room_id, "
            " region) VALUES ($1, $2, $3, $4, $5, 'eu') RETURNING id", *pids, status, room)
    if queue:
        for i, (pid, steam) in enumerate(seats):
            await queue_row(conn, mode, pid, steam,
                            (caps[i] if caps is not None else "rjs1"), sid)
    if flag:
        await conn.execute(
            "UPDATE %s SET hold_v2 = TRUE, hold_room = $2 WHERE id = $1"
            % ("team_series" if mode == "team" else "ovt_series"), sid, room)
    return Series(mode, sid, room, seats)


async def game_start(env, s, seat=0, prev=None, room=None):
    r = await env.post("/api/v1/match/game/start", s.steam(seat), {
        "steam_id": s.steam(seat), "mode": s.mode, "series_id": str(s.sid),
        "room": room or s.room, "prev_game": str(prev) if prev else None})
    assert r.status_code == 200, (r.status_code, r.text)
    return r.json()


# == N2. S1 server: the game id route (T1.4) and the latch helper =============

def test_t1_4_game_id_chain_rematch_delayed_and_handover(monkeypatch):
    """T1.4: consecutive same-room games chain by the previous G with seq
    1, 2, 3; a re-post of the first start returns the first G; a rematch
    (previous G = the current G) mints a NEW G; a delayed post naming an
    earlier previous G returns the existing successor and mints nothing; a
    promoted master re-posting the same previous G (handover between mint and
    publish) receives the same G, also when both posts race."""
    async def body(env):
        for mode in ("team", "ovt"):
            s = await seed_series(env.conn, mode)
            a = await game_start(env, s, 0)
            assert (a["status"], a["seq"], a["minted"]) == ("ok", 1, True), a
            again = await game_start(env, s, 1)
            assert (again["game_id"], again["minted"]) == (a["game_id"], False), again
            b = await game_start(env, s, 0, prev=a["game_id"])          # rematch
            assert b["game_id"] != a["game_id"] and b["seq"] == 2 and b["minted"], b
            hand = await game_start(env, s, 2, prev=a["game_id"])       # promoted master
            assert (hand["game_id"], hand["minted"]) == (b["game_id"], False), hand
            c = await game_start(env, s, 1, prev=b["game_id"])
            assert c["seq"] == 3 and c["game_id"] not in (a["game_id"], b["game_id"]), c
            late = await game_start(env, s, 0, prev=a["game_id"])       # delayed
            assert (late["game_id"], late["minted"]) == (b["game_id"], False), late
            race = await asyncio.gather(game_start(env, s, 0, prev=c["game_id"]),
                                        game_start(env, s, 1, prev=c["game_id"]))
            assert race[0]["game_id"] == race[1]["game_id"], race
            assert sorted(r["minted"] for r in race) == [False, True], race
            rows = await env.conn.fetch(
                "SELECT id, seq, prev_game FROM match_games WHERE series_id = $1 "
                " AND room_name = $2 ORDER BY seq", s.sid, s.room)
            assert [r["seq"] for r in rows] == [1, 2, 3, 4], rows
            assert rows[0]["prev_game"] is None
            for prev, cur in zip(rows, rows[1:]):
                assert cur["prev_game"] == prev["id"]
    run_env(monkeypatch, body)


def test_t1_4_game_start_refusals(monkeypatch):
    """The start route requires the poster's session, membership, a series
    flagged for this room and still active, and a previous G of this series
    and room; each refusal names its reason and mints nothing."""
    async def body(env):
        s = await seed_series(env.conn, "team")
        stranger = (await seed_players(env.conn, 1))[0]
        r = await env.post("/api/v1/match/game/start", s.steam(0), {
            "steam_id": s.steam(0), "mode": "team", "series_id": str(s.sid),
            "room": s.room}, token="tok:wrong")
        assert r.status_code == 401
        r = await env.post("/api/v1/match/game/start", stranger[1], {
            "steam_id": stranger[1], "mode": "team", "series_id": str(s.sid),
            "room": s.room})
        assert r.json() == {"status": "refused", "reason": "not_member"}
        assert (await game_start(env, s, 0, room=s.room + "_x"))["reason"] == "not_flagged"
        u = await seed_series(env.conn, "team", flag=False)
        assert (await game_start(env, u, 0))["reason"] == "not_flagged"
        o = await seed_series(env.conn, "ovt", status="completed")
        assert (await game_start(env, o, 0))["reason"] == "series_closed"
        other = await seed_series(env.conn, "team")
        g_other = (await game_start(env, other, 0))["game_id"]
        assert (await game_start(env, s, 0, prev=g_other))["reason"] == "unknown_prev"
        r = await env.post("/api/v1/match/game/start", s.steam(0), {
            "steam_id": s.steam(0), "mode": "duel", "series_id": str(s.sid),
            "room": s.room})
        assert r.status_code == 400
        assert await env.conn.fetchval(
            "SELECT count(*) FROM match_games WHERE series_id = ANY($1::uuid[])",
            [s.sid, u.sid, o.sid]) == 0
    run_env(monkeypatch, body)


def test_hold_latch_helper(monkeypatch):
    """_hold_latch: TRUE only when every member's queue row of the mode
    carries rjs1 (among other tokens); one member without the token or
    without a row gives FALSE; a second latch for the same room changes
    nothing even after the caps changed; a latch for a new room re-judges;
    an empty room latches nothing. Both modes."""
    async def latch(env, s, room):
        async with env.sm() as db:
            flag = await match_hold._hold_latch(db, s.mode, s.sid, room)
            await db.commit()
        tbl = "team_series" if s.mode == "team" else "ovt_series"
        row = await env.conn.fetchrow(
            "SELECT hold_v2, hold_room FROM %s WHERE id = $1" % tbl, s.sid)
        assert row["hold_v2"] is flag
        return flag, row["hold_room"]

    async def body(env):
        for mode, n in (("team", 4), ("ovt", 3)):
            s = await seed_series(env.conn, mode, flag=False,
                                  caps=["ffa_asm1,rjs1"] + ["rjs1"] * (n - 1))
            assert await latch(env, s, s.room) == (True, s.room)
            q = "team_queue" if mode == "team" else "ovt_queue"
            await env.conn.execute("UPDATE %s SET caps = '' WHERE player_id = $1" % q,
                                   s.pid(1))
            assert await latch(env, s, s.room) == (True, s.room), "a written flag moved"
            assert await latch(env, s, s.room + "_r") == (False, s.room + "_r")
            await env.conn.execute("UPDATE %s SET caps = 'rjs1' WHERE player_id = $1" % q,
                                   s.pid(1))
            assert await latch(env, s, s.room + "_r2") == (True, s.room + "_r2")

            t = await seed_series(env.conn, mode, flag=False,
                                  caps=["rjs1"] * (n - 1) + ["rjs10"])
            assert await latch(env, t, t.room) == (False, t.room), "a token prefix passed"
            u = await seed_series(env.conn, mode, flag=False)
            await env.conn.execute("DELETE FROM %s WHERE player_id = $1" % q, u.pid(n - 1))
            assert await latch(env, u, u.room) == (False, u.room), "a missing row passed"
            v = await seed_series(env.conn, mode, flag=False)
            assert await latch(env, v, "  ") == (False, None)
    run_env(monkeypatch, body)


# == N3. S2 server: beat, open, state, by-room, end, attempts, sweep ===========

import hashlib  # noqa: E402
import hmac as _hmac  # noqa: E402
from datetime import datetime as _dt, timedelta  # noqa: E402


def sign_open(body):
    msg = match_hold.hold_open_canonical(body["mode"], body["room"], body["game_id"],
                                         body["held_steam_id"], body["slot"], body["team"],
                                         body["opener_steam_id"])
    return _hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()


def seat_of(s, i):
    """(slot, team) of seat i: team = slot // 2 in 2v2; slot 0 solo in 1v2."""
    return i, (i // 2 if s.mode == "team" else (0 if i == 0 else 1))


async def beat(env, s, i, actor=None, seen=(), digest=None, room=None):
    r = await env.post("/api/v1/match/hold/beat", s.steam(i), {
        "steam_id": s.steam(i), "mode": s.mode, "series_id": str(s.sid),
        "room": room or s.room, "actor": actor if actor is not None else 10 + i,
        "seen": [{"actor": a, "u_id": u} for a, u in seen], "boundary_digest": digest})
    assert r.status_code == 200, r.text
    return r.json()


async def open_hold(env, s, held, opener, g, rid=None, sign=True, **over):
    slot, team = seat_of(s, held)
    body = {"request_id": rid or ("req" + uuid.uuid4().hex[:16]),
            "opener_steam_id": s.steam(opener), "mode": s.mode, "room": s.room,
            "game_id": str(g), "held_steam_id": s.steam(held), "slot": slot, "team": team,
            "t1_points": 1, "t2_points": 0}
    body.update(over)
    body["hmac"] = sign_open(body) if sign else "0" * 64
    r = await env.post("/api/v1/match/hold/open", body["opener_steam_id"], body)
    return r


async def backdate_presence(env, s, i, secs):
    """The seat stopped beating `secs` ago (a dropped fighter beats no more)."""
    await env.conn.execute(
        "UPDATE match_seat_presence SET present_at = clock_timestamp() - make_interval(secs => $3),"
        " beat_at = clock_timestamp() - make_interval(secs => $3)"
        " WHERE room_name = $1 AND player_id = $2", s.room, s.pid(i), float(secs))
    return await env.conn.fetchval(
        "SELECT present_at FROM match_seat_presence WHERE room_name = $1 AND player_id = $2",
        s.room, s.pid(i))


async def hold_db(env, hid):
    return await env.conn.fetchrow("SELECT * FROM match_seat_holds WHERE id = $1",
                                   uuid.UUID(str(hid)))


async def shift_hold(env, hid, secs):
    """Move one hold back in time by `secs`, every stamp together (the
    invariant held_until = held_anchor_at + HOLD_S is kept)."""
    await env.conn.execute(
        "UPDATE match_seat_holds SET held_anchor_at = held_anchor_at - make_interval(secs => $2),"
        " held_at = held_at - make_interval(secs => $2),"
        " held_until = held_until - make_interval(secs => $2),"
        " claimed_at = claimed_at - make_interval(secs => $2),"
        " bound_at = bound_at - make_interval(secs => $2) WHERE id = $1",
        uuid.UUID(str(hid)), float(secs))


async def sweep(env):
    async with env.sm() as db:
        return await match_hold.hold_sweep(db)


async def dbclock(env):
    return await env.conn.fetchval("SELECT clock_timestamp()")


async def opened_series(env, mode="team", held=1, opener=0, back=30):
    """A flagged series, G1 started, the held seat's beat backdated `back` s
    and every other seat beating now."""
    s = await seed_series(env.conn, mode)
    g = (await game_start(env, s, opener))["game_id"]
    for i in range(len(s.seats)):
        await beat(env, s, i)
    pres = await backdate_presence(env, s, held, back)
    return s, g, pres


class _SkewedDatetime(_dt):
    """An application clock five minutes ahead of the DB clock: a route that
    reads it instead of clock_timestamp() writes a stamp outside the
    transaction's DB-clock bounds."""
    @classmethod
    def now(cls, tz=None):
        return _dt.now(tz) + timedelta(minutes=5)


def test_t2_1_open_anchor_idempotent_and_refusals(monkeypatch):
    """T2.1: one row; held_anchor_at = the held seat's last present_at and
    held_until = present_at + 120 s exactly; held_at is the DB clock read
    after the series lock wait (inside the request's DB-clock bounds, even
    with a skewed application clock and a 2 s lock wait); the lease of the
    held player is released; a repeat answers the same row; each refusal on
    its own fixture; a sweep with nothing due moves no held_until, and the
    sweep of a lapsed row stamps closed_at = held_until, never moving it."""
    monkeypatch.setattr(match_hold, "datetime", _SkewedDatetime, raising=False)

    async def body(env):
        s, g, pres = await opened_series(env)
        await env.conn.execute(
            "INSERT INTO queue_leases (player_id, mode, group_id, generation, acquired_at, "
            " renewed_at, expires_at) VALUES ($1, 'team', $2, gen_random_uuid(), "
            " clock_timestamp(), clock_timestamp(), clock_timestamp() + interval '10 minutes')",
            s.pid(1), s.sid)
        blk = await cf_pg.harness.connect_bound(env.c.dsn, env.c.schema)
        tr = blk.transaction()
        await tr.start()
        await blk.execute("SELECT 1 FROM team_series WHERE id = $1 FOR NO KEY UPDATE", s.sid)
        t0 = await dbclock(env)
        task = asyncio.ensure_future(open_hold(env, s, 1, 0, g, rid="req-first-open"))
        await asyncio.sleep(2.0)
        released = await blk.fetchval("SELECT clock_timestamp()")
        await tr.rollback()
        await blk.close()
        r = await task
        t1 = await dbclock(env)
        out = r.json()
        assert (r.status_code, out["status"], out["repeat"]) == (200, "opened", False), out
        h = await hold_db(env, out["hold_id"])
        assert h["held_anchor_at"] == pres, (h["held_anchor_at"], pres)
        assert h["held_until"] == pres + timedelta(seconds=120)
        assert released <= h["held_at"] <= t1 and t0 <= h["held_at"], (released, h["held_at"])
        assert (h["n"], h["slot"], h["team"], h["seq"], h["closed_at"]) == (1, 1, 0, 0, None)
        assert h["opener_player_id"] == s.pid(0) and h["game_id"] == uuid.UUID(g)
        assert 85 <= out["deadline_s"] <= 90, out
        assert await env.conn.fetchval(
            "SELECT count(*) FROM queue_leases WHERE player_id = $1", s.pid(1)) == 0
        rep = (await open_hold(env, s, 1, 2, g)).json()
        assert (rep["status"], rep["repeat"], rep["hold_id"]) == ("opened", True, out["hold_id"])
        assert await env.conn.fetchval(
            "SELECT count(*) FROM match_seat_holds WHERE room_name = $1", s.room) == 1

        assert await sweep(env) == {}
        assert (await hold_db(env, out["hold_id"]))["held_until"] == h["held_until"]
        await shift_hold(env, out["hold_id"], 200)
        lapsed_until = (await hold_db(env, out["hold_id"]))["held_until"]
        late = (await open_hold(env, s, 1, 2, g)).json()     # past the deadline, unswept
        assert (late["status"], late["reason"]) == ("refused", "duplicate_game"), late
        assert await sweep(env) == {"lapsed": 1}
        hh = await hold_db(env, out["hold_id"])
        assert (hh["held_until"], hh["closed_at"], hh["closed_reason"]) == \
            (lapsed_until, lapsed_until, "lapsed")
        assert await sweep(env) == {}

        # each refusal on its fixture
        async def refusal(r):
            assert r.status_code == 200, r.text
            j = r.json()
            assert j["status"] == "refused", j
            return j["reason"]

        assert await refusal(await open_hold(env, s, 1, 0, g)) == "duplicate_game"
        busy, gb, _ = await opened_series(env)
        assert (await open_hold(env, busy, 1, 0, gb)).json()["status"] == "opened"
        await beat(env, busy, 2)
        assert await refusal(await open_hold(env, busy, 2, 0, gb)) == "room_busy"
        nm, gn, _ = await opened_series(env)
        stranger = (await seed_players(env.conn, 1))[0]
        assert await refusal(await open_hold(env, nm, 1, 0, gn,
                                             held_steam_id=stranger[1])) == "not_member"
        assert await refusal(await open_hold(env, nm, 1, 1, gn)) == "not_member"
        assert await refusal(await open_hold(env, nm, 1, 0, gn, team=1)) == "not_member"
        assert await refusal(await open_hold(env, nm, 1, 0, gn, slot=3)) == "not_member"
        cl, gc, _ = await opened_series(env, "ovt")
        await env.conn.execute("UPDATE ovt_series SET status = 'completed' WHERE id = $1", cl.sid)
        assert await refusal(await open_hold(env, cl, 1, 0, gc)) == "series_closed"
        nf, gf, _ = await opened_series(env)
        await env.conn.execute("UPDATE team_series SET hold_room = 'elsewhere' WHERE id = $1",
                               nf.sid)
        assert await refusal(await open_hold(env, nf, 1, 0, gf)) == "not_flagged"
        nc, g1, _ = await opened_series(env)
        await game_start(env, nc, 0, prev=g1)
        assert await refusal(await open_hold(env, nc, 1, 0, g1)) == "not_current_game"
        assert await refusal(await open_hold(env, nc, 1, 0, uuid.uuid4())) == "not_current_game"
        npz = await seed_series(env.conn, "ovt")
        gp = (await game_start(env, npz, 0))["game_id"]
        assert await refusal(await open_hold(env, npz, 2, 0, gp)) == "no_presence"
        ws, gw, _ = await opened_series(env, back=110)
        assert await refusal(await open_hold(env, ws, 1, 0, gw)) == "window_spent"
        bad = await open_hold(env, ws, 1, 0, gw, sign=False)
        assert bad.status_code == 403
        assert await env.conn.fetchval(
            "SELECT count(*) FROM match_seat_holds WHERE room_name = ANY($1::text[])",
            [nm.room, cl.room, nf.room, nc.room, npz.room, ws.room]) == 0
    run_env(monkeypatch, body)


def test_m1_hold_open_requires_exact_roster_slot_and_team(monkeypatch):
    """A valid geometric slot cannot identify a roster sibling: both 2v2
    teams and the 1v2 duo require the held player's exact server-side seat."""
    async def body(env):
        for mode, held_seat, sibling_slot, sibling_team in (
                ("team", 1, 0, 0),
                ("team", 3, 2, 1),
                ("ovt", 2, 1, 1)):
            s, g, _ = await opened_series(env, mode, held=held_seat)
            swapped = (await open_hold(
                env, s, held_seat, 0, g,
                slot=sibling_slot, team=sibling_team)).json()
            assert swapped == {"status": "refused", "reason": "not_member"}, swapped
            assert await env.conn.fetchval(
                "SELECT count(*) FROM match_seat_holds WHERE room_name = $1", s.room) == 0
            valid = (await open_hold(env, s, held_seat, 0, g)).json()
            assert (valid["status"], valid["slot"], valid["team"]) == \
                ("opened", *seat_of(s, held_seat)), valid

    run_env(monkeypatch, body, prefix="rjs2m1")


def test_t2_1_open_stores_the_crossing_of_the_locked_series(monkeypatch):
    """A team hold stores what _team_game_crossed_two answers for the series
    row read under the lock (wins and room), as crossed_at_hold; a 1v2 hold
    never asks it."""
    seen = []

    async def crossed(db, series_id, row, reported_points=None):
        seen.append((series_id, dict(row)))
        return True

    async def body(env):
        monkeypatch.setattr(main, "_team_game_crossed_two", crossed)
        s, g, _ = await opened_series(env)
        await env.conn.execute(
            "UPDATE team_series SET t1_series_wins = 1 WHERE id = $1", s.sid)
        out = (await open_hold(env, s, 1, 0, g)).json()
        assert (await hold_db(env, out["hold_id"]))["crossed_at_hold"] is True
        assert seen == [(s.sid, {"t1_series_wins": 1, "t2_series_wins": 0,
                                 "photon_room_id": s.room})], seen
        o, go, _ = await opened_series(env, "ovt")
        out = (await open_hold(env, o, 1, 0, go)).json()
        assert (await hold_db(env, out["hold_id"]))["crossed_at_hold"] is False
        assert len(seen) == 1
    run_env(monkeypatch, body)


def test_t2_2_closure_once_for_every_reason(monkeypatch):
    """T2.2: every end reason stamps closed_at and the reason exactly once;
    a member without a fresh beat, a non-member and an unknown reason are
    refused; two racing ends stamp one closure and both answer it; after an
    end the hold reads closed, a re-open of the seat is duplicate_game and
    the room takes another hold; a bound row with no entry closes
    entry_failed at bound_at + 60 s; an end after a deadline answers the
    deadline's closure."""
    async def body(env):
        for reason in sorted(match_hold.END_REASONS):
            s, g, _ = await opened_series(env, "ovt" if len(reason) % 2 else "team")
            hid = (await open_hold(env, s, 1, 0, g)).json()["hold_id"]
            r = await env.post("/api/v1/match/hold/%s/end" % hid, s.steam(2),
                               {"steam_id": s.steam(2), "reason": reason})
            j = r.json()
            assert (j["status"], j["closed_reason"], j["already"]) == ("closed", reason, False)
            h = await hold_db(env, hid)
            assert (h["closed_reason"], h["closed_at"].isoformat()) == (reason, j["closed_at"])
            st = (await env.get("/api/v1/match/hold/%s/state" % hid, s.steam(0),
                                {"steam_id": s.steam(0)})).json()
            assert (st["state"], st["closed_reason"]) == ("closed", reason), st

        s, g, _ = await opened_series(env)
        hid = (await open_hold(env, s, 1, 0, g)).json()["hold_id"]
        r = await env.post("/api/v1/match/hold/%s/end" % hid, s.steam(2),
                           {"steam_id": s.steam(2), "reason": "dance"})
        assert r.status_code == 400
        stranger = (await seed_players(env.conn, 1))[0]
        r = await env.post("/api/v1/match/hold/%s/end" % hid, stranger[1],
                           {"steam_id": stranger[1], "reason": "ceiling"})
        assert r.status_code == 404
        await env.conn.execute(
            "UPDATE match_seat_presence SET beat_at = clock_timestamp() - interval '30 seconds'"
            " WHERE room_name = $1 AND player_id = $2", s.room, s.pid(3))
        r = await env.post("/api/v1/match/hold/%s/end" % hid, s.steam(3),
                           {"steam_id": s.steam(3), "reason": "ceiling"})
        assert r.json() == {"status": "refused", "reason": "no_fresh_beat"}
        assert (await hold_db(env, hid))["closed_at"] is None
        race = await asyncio.gather(*[
            env.post("/api/v1/match/hold/%s/end" % hid, s.steam(i),
                     {"steam_id": s.steam(i), "reason": why})
            for i, why in ((0, "ceiling"), (2, "second_departure"))])
        answers = [x.json() for x in race]
        assert answers[0]["closed_at"] == answers[1]["closed_at"], answers
        assert answers[0]["closed_reason"] == answers[1]["closed_reason"], answers
        assert sorted(a["already"] for a in answers) == [False, True], answers
        h = await hold_db(env, hid)
        assert h["closed_reason"] == answers[0]["closed_reason"]
        assert (await open_hold(env, s, 1, 0, g)).json()["reason"] == "duplicate_game"
        await beat(env, s, 3)
        assert (await open_hold(env, s, 3, 0, g)).json()["status"] == "opened"

        b, gb, _ = await opened_series(env, "ovt")
        hid = (await open_hold(env, b, 1, 0, gb)).json()["hold_id"]
        await env.conn.execute(
            "UPDATE match_seat_holds SET claimed_at = clock_timestamp() - interval '70 seconds',"
            " bound_at = clock_timestamp() - interval '61 seconds', bound_actor = 7, seq = 1"
            " WHERE id = $1", uuid.UUID(hid))
        st = (await env.get("/api/v1/match/hold/%s/state" % hid, b.steam(0),
                            {"steam_id": b.steam(0)})).json()
        assert (st["state"], st["closed_reason"]) == ("closed", "entry_failed"), st
        until_before = (await hold_db(env, hid))["held_until"]
        assert await sweep(env) == {"entry_failed": 1}
        h = await hold_db(env, hid)
        assert h["held_until"] == until_before, "the sweep moved held_until"
        assert h["closed_at"] == h["bound_at"] + timedelta(seconds=60)
        assert h["closed_at"].isoformat() == st["closed_at"]

        late, gl, _ = await opened_series(env)
        hid = (await open_hold(env, late, 1, 0, gl)).json()["hold_id"]
        await shift_hold(env, hid, 300)
        j = (await env.post("/api/v1/match/hold/%s/end" % hid, late.steam(0),
                            {"steam_id": late.steam(0), "reason": "ceiling"})).json()
        h = await hold_db(env, hid)
        assert (j["closed_reason"], j["already"], h["closed_reason"]) == \
            ("lapsed", True, "lapsed")
        assert h["closed_at"] == h["held_until"]
    run_env(monkeypatch, body)


def test_t2_state_by_room_and_beat(monkeypatch):
    """The state and by-room reads answer series members only (404
    otherwise); by-room answers 404 for a game with no hold; a beat from a
    non-member or for an unflagged room is refused; present_at moves only
    when the poster names itself with its own actor, beat_at always."""
    async def body(env):
        s, g, _ = await opened_series(env)
        out = (await open_hold(env, s, 1, 0, g)).json()
        st = (await env.get("/api/v1/match/hold/%s/state" % out["hold_id"], s.steam(3),
                            {"steam_id": s.steam(3)})).json()
        assert (st["state"], st["seq"], st["slot"], st["team"]) == ("opened", 0, 1, 0)
        br = (await env.get("/api/v1/match/hold/by-room", s.steam(2), {
            "steam_id": s.steam(2), "room": s.room, "game_id": g})).json()
        assert br["hold_id"] == out["hold_id"]
        stranger = (await seed_players(env.conn, 1))[0]
        assert (await env.get("/api/v1/match/hold/%s/state" % out["hold_id"], stranger[1],
                              {"steam_id": stranger[1]})).status_code == 404
        assert (await env.get("/api/v1/match/hold/by-room", s.steam(2), {
            "steam_id": s.steam(2), "room": s.room,
            "game_id": str(uuid.uuid4())})).status_code == 404
        assert (await env.get("/api/v1/match/hold/%s/state" % out["hold_id"], s.steam(3),
                              {"steam_id": s.steam(3)}, token="tok:x")).status_code == 401

        r = await env.post("/api/v1/match/hold/beat", stranger[1], {
            "steam_id": stranger[1], "mode": "team", "series_id": str(s.sid),
            "room": s.room, "actor": 3})
        assert r.json() == {"status": "refused", "reason": "not_member"}
        assert (await beat(env, s, 0, room=s.room + "_x"))["reason"] == "not_flagged"
        before = await env.conn.fetchrow(
            "SELECT present_at, beat_at FROM match_seat_presence WHERE room_name = $1 "
            " AND player_id = $2", s.room, s.pid(2))
        await beat(env, s, 2, actor=12, seen=[(99, s.steam(2)), (11, s.steam(1))])
        after = await env.conn.fetchrow(
            "SELECT present_at, beat_at, seen FROM match_seat_presence WHERE room_name = $1 "
            " AND player_id = $2", s.room, s.pid(2))
        assert after["present_at"] == before["present_at"], "named itself with another actor"
        assert after["beat_at"] > before["beat_at"]
        await beat(env, s, 2, actor=12, seen=[(12, s.steam(2))], digest="d" * 64)
        last = await env.conn.fetchrow(
            "SELECT present_at, beat_at, boundary_digest FROM match_seat_presence "
            " WHERE room_name = $1 AND player_id = $2", s.room, s.pid(2))
        assert last["present_at"] == last["beat_at"] and last["boundary_digest"] == "d" * 64
    run_env(monkeypatch, body)


def test_t2_8_open_attempt_rows(monkeypatch):
    """T2.8: every open request writes its own match_hold_open_attempts row
    in the request's transaction: each refusal and each retry its own row
    with no hold, the open and the repeat rows naming the hold; a request id
    reused writes no second row."""
    async def body(env):
        s, g, _ = await opened_series(env)
        other = await seed_series(env.conn, "team")
        go = (await game_start(env, other, 0))["game_id"]
        await game_start(env, other, 0, prev=go)
        await open_hold(env, s, 1, 0, uuid.uuid4(), rid="req-unknown-g1")
        await open_hold(env, s, 1, 0, uuid.uuid4(), rid="req-unknown-g2")
        await open_hold(env, other, 1, 0, go, rid="req-stale-g001")
        await open_hold(env, s, 1, 0, g, rid="req-opened-001")
        await open_hold(env, s, 1, 2, g, rid="req-repeat-001")
        await open_hold(env, s, 1, 2, g, rid="req-repeat-001")
        rows = await env.conn.fetch(
            "SELECT request_id, outcome, reason, hold_id, held_player_id, opener_player_id "
            "  FROM match_hold_open_attempts WHERE request_id LIKE 'req-%' ORDER BY at, request_id")
        got = {r["request_id"]: (r["outcome"], r["reason"], r["hold_id"] is not None)
               for r in rows}
        assert got == {
            "req-unknown-g1": ("refused", "not_current_game", False),
            "req-unknown-g2": ("refused", "not_current_game", False),
            "req-stale-g001": ("refused", "not_current_game", False),
            "req-opened-001": ("opened", None, True),
            "req-repeat-001": ("repeat", None, True),
        }, got
        assert len(rows) == 5
        assert await env.conn.fetchval("SELECT count(*) FROM match_seat_holds") == 1
        byid = {r["request_id"]: r for r in rows}
        assert byid["req-opened-001"]["hold_id"] == byid["req-repeat-001"]["hold_id"]
        assert byid["req-opened-001"]["held_player_id"] == s.pid(1)
        assert byid["req-repeat-001"]["opener_player_id"] == s.pid(2)
    run_env(monkeypatch, body)


def test_m6_open_request_id_replays_only_its_original_tuple(monkeypatch):
    """An exact request-id retry replays its recorded result; cross-game or
    cross-seat reuse refuses without a hold, lease action, or ledger rewrite."""
    async def body(env):
        opened, opened_game, _ = await opened_series(env)
        opened_rid = "req-m6-opened"
        first = (await open_hold(
            env, opened, 1, 0, opened_game, rid=opened_rid)).json()
        replay = (await open_hold(
            env, opened, 1, 0, opened_game, rid=opened_rid)).json()
        assert (first["status"], first["repeat"], replay["status"], replay["repeat"]) == \
            ("opened", False, "opened", False)
        assert replay["hold_id"] == first["hold_id"]

        refused, refused_game, _ = await opened_series(env, back=110)
        refused_rid = "req-m6-refused"
        initial_refusal = (await open_hold(
            env, refused, 1, 0, refused_game, rid=refused_rid)).json()
        assert initial_refusal == {"status": "refused", "reason": "window_spent"}
        await beat(env, refused, 1)
        await backdate_presence(env, refused, 1, 30)
        refusal_replay = (await open_hold(
            env, refused, 1, 0, refused_game, rid=refused_rid)).json()
        assert refusal_replay == initial_refusal
        assert await env.conn.fetchval(
            "SELECT count(*) FROM match_seat_holds WHERE room_name = $1", refused.room) == 0

        other, other_game, _ = await opened_series(env)
        cross_game = (await open_hold(
            env, other, 1, 0, other_game, rid=opened_rid)).json()
        assert cross_game == {"status": "refused", "reason": "request_mismatch"}
        assert await env.conn.fetchval(
            "SELECT count(*) FROM match_seat_holds WHERE room_name = $1", other.room) == 0

        seat, seat_game, _ = await opened_series(env)
        seat_rid = "req-m6-seat"
        original = (await open_hold(env, seat, 1, 0, seat_game, rid=seat_rid)).json()
        ended = await env.post(
            "/api/v1/match/hold/%s/end" % original["hold_id"], seat.steam(2),
            {"steam_id": seat.steam(2), "reason": "ceiling"})
        assert ended.json()["status"] == "closed"
        cross_seat = (await open_hold(env, seat, 3, 2, seat_game, rid=seat_rid)).json()
        assert cross_seat == {"status": "refused", "reason": "request_mismatch"}
        assert await env.conn.fetchval(
            "SELECT count(*) FROM match_seat_holds WHERE room_name = $1", seat.room) == 1

        rows = await env.conn.fetch(
            "SELECT request_id, room_name, game_id, held_player_id, opener_player_id, outcome, reason "
            "FROM match_hold_open_attempts WHERE request_id = ANY($1::varchar[]) ORDER BY request_id",
            [opened_rid, refused_rid, seat_rid])
        assert len(rows) == 3
        by_id = {row["request_id"]: row for row in rows}
        assert (by_id[opened_rid]["room_name"], by_id[opened_rid]["game_id"],
                by_id[opened_rid]["held_player_id"], by_id[opened_rid]["opener_player_id"],
                by_id[opened_rid]["outcome"]) == \
            (opened.room, uuid.UUID(opened_game), opened.pid(1), opened.pid(0), "opened")
        assert (by_id[refused_rid]["outcome"], by_id[refused_rid]["reason"]) == \
            ("refused", "window_spent")

    run_env(monkeypatch, body, prefix="rjs2m6tuple")


def test_m6_bad_signature_records_refusal_before_403(monkeypatch):
    """A bad signature records one refusal with the authenticated opener and
    no asserted held identity before the route returns 403."""
    async def body(env):
        s, g, _ = await opened_series(env)
        rid = "req-m6-bad-signature"
        bad = await open_hold(env, s, 1, 0, g, rid=rid, sign=False)
        assert bad.status_code == 403
        row = await env.conn.fetchrow(
            "SELECT room_name, game_id, held_player_id, opener_player_id, outcome, reason, hold_id "
            "FROM match_hold_open_attempts WHERE request_id = $1", rid)
        assert (row["room_name"], row["game_id"], row["held_player_id"],
                row["opener_player_id"], row["outcome"], row["reason"], row["hold_id"]) == \
            (s.room, uuid.UUID(g), None, s.pid(0), "refused", "bad_signature", None)
        assert await env.conn.fetchval(
            "SELECT count(*) FROM match_seat_holds WHERE room_name = $1", s.room) == 0
        again = await open_hold(env, s, 1, 0, g, rid=rid, sign=False)
        assert again.status_code == 403
        assert await env.conn.fetchval(
            "SELECT count(*) FROM match_hold_open_attempts WHERE request_id = $1", rid) == 1

    run_env(monkeypatch, body, prefix="rjs2m6sig")


def test_m7_team_open_requires_both_point_snapshots(monkeypatch):
    """Team opens refuse each missing point shape before mutation, while a
    complete team snapshot and a 1v2 omission retain their intended behavior."""
    async def body(env):
        s, g, _ = await opened_series(env)
        cases = (
            ("req-m7-no-t1", None, 0),
            ("req-m7-no-t2", 1, None),
            ("req-m7-no-points", None, None),
        )
        for rid, t1_points, t2_points in cases:
            refused = (await open_hold(
                env, s, 1, 0, g, rid=rid,
                t1_points=t1_points, t2_points=t2_points)).json()
            assert refused == {"status": "refused", "reason": "missing_points"}, refused
        assert await env.conn.fetchval(
            "SELECT count(*) FROM match_seat_holds WHERE room_name = $1", s.room) == 0
        reasons = await env.conn.fetch(
            "SELECT request_id, outcome, reason FROM match_hold_open_attempts "
            "WHERE request_id LIKE 'req-m7-%' ORDER BY request_id")
        assert [(r["outcome"], r["reason"]) for r in reasons] == \
            [("refused", "missing_points")] * 3

        valid = (await open_hold(env, s, 1, 0, g, rid="req-m7-valid")).json()
        assert valid["status"] == "opened"
        stored = await hold_db(env, valid["hold_id"])
        assert (stored["drop_t1_points"], stored["drop_t2_points"]) == (1, 0)

        ovt, ovt_game, _ = await opened_series(env, "ovt")
        omitted = (await open_hold(
            env, ovt, 1, 0, ovt_game, rid="req-m7-ovt",
            t1_points=None, t2_points=None)).json()
        assert omitted["status"] == "opened"
        ovt_stored = await hold_db(env, omitted["hold_id"])
        assert (ovt_stored["drop_t1_points"], ovt_stored["drop_t2_points"]) == (None, None)

    run_env(monkeypatch, body, prefix="rjs2m7")


def test_t7_1_hold_open_canonical_one_field_at_a_time(monkeypatch):
    """T7.1 (hold-open half): changing any one of the eight fields of the
    hold-open canonical makes the signature reject; the team-DC canonical
    of today is a different message (its signature never verifies as a
    hold-open signature, nor the reverse), and main's team-DC verifier still
    accepts its own signature unchanged."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    base = {"mode": "team", "room": "team_room1", "game_id": str(uuid.uuid4()),
            "held_steam_id": "s2held", "slot": 1, "team": 0, "opener_steam_id": "s2open",
            "request_id": "req-canonical-1"}
    sig = sign_open(base)
    req = match_hold.HoldOpenReq(**base, hmac=sig)
    assert match_hold._verify_hold_open_hmac(req)
    changes = {"mode": "ovt", "room": "team_room2", "game_id": str(uuid.uuid4()),
               "held_steam_id": "s2held2", "slot": 2, "team": 1,
               "opener_steam_id": "s2open2"}
    for field, value in changes.items():
        bad = dict(base, **{field: value})
        assert not match_hold._verify_hold_open_hmac(match_hold.HoldOpenReq(**bad, hmac=sig)), \
            field
    dc_sig = _hmac.new(SECRET.encode(), b"s2open:sid1:s2held:dc", hashlib.sha256).hexdigest()
    assert main._verify_team_dc_hmac("s2open", "sid1", "s2held", dc_sig)
    assert not main._verify_team_dc_hmac("s2open", "sid1", "s2held", sig)
    assert not match_hold._verify_hold_open_hmac(match_hold.HoldOpenReq(**base, hmac=dc_sig))


# == N4. S3 server: mine, claim, bind, entered =================================

async def mine(env, s, i):
    r = await env.get("/api/v1/match/hold/mine", s.steam(i), {"steam_id": s.steam(i)})
    assert r.status_code == 200, r.text
    return r.json()


async def claim(env, s, i, hid, **kw):
    r = await env.post("/api/v1/match/hold/%s/claim" % hid, s.steam(i),
                       {"steam_id": s.steam(i)}, **kw)
    assert r.status_code == 200, r.text
    return r.json()


async def bind(env, s, i, hid, actor, region="eu"):
    r = await env.post("/api/v1/match/hold/%s/bind" % hid, s.steam(i),
                       {"steam_id": s.steam(i), "actor": actor, "region": region})
    assert r.status_code == 200, r.text
    return r.json()


async def entered(env, s, i, hid, g, actor):
    r = await env.post("/api/v1/match/hold/%s/entered" % hid, s.steam(i),
                       {"steam_id": s.steam(i), "game_id": str(g), "actor": actor})
    assert r.status_code == 200, r.text
    return r.json()


async def attempts(env, hid):
    return [(r["attempt_no"], r["kind"], r["outcome"], r["reason"]) for r in await env.conn.fetch(
        "SELECT attempt_no, kind, outcome, reason FROM match_hold_attempts WHERE hold_id = $1 "
        " ORDER BY attempt_no", uuid.UUID(str(hid)))]


async def held(env, mode="team", held_seat=1):
    s, g, _ = await opened_series(env, mode, held=held_seat)
    hid = (await open_hold(env, s, held_seat, 0, g)).json()["hold_id"]
    return s, g, hid


def test_t3_discovery_mine(monkeypatch):
    """Discovery: a live hold answers readmissible 1 with the seat, room,
    region and tally, sets offered_at once and writes one `offered` row per
    call, committed before the answer; no hold, or a lapsed one, answers
    readmissible 0 and writes nothing; a failed row write answers 503."""
    async def body(env):
        s, g, hid = await held(env)
        assert await mine(env, s, 2) == {"readmissible": 0}
        m = await mine(env, s, 1)
        assert (m["readmissible"], m["hold_id"], m["slot"], m["team"], m["mode"],
                m["room_name"], m["room_region"], m["series_tally"]) == \
            (1, hid, 1, 0, "team", s.room, "eu", [0, 0]), m
        first = (await hold_db(env, hid))["offered_at"]
        assert first is not None
        await mine(env, s, 1)
        assert (await hold_db(env, hid))["offered_at"] == first
        assert await attempts(env, hid) == [(1, "offered", "ok", None), (2, "offered", "ok", None)]
        await shift_hold(env, hid, 300)
        assert await mine(env, s, 1) == {"readmissible": 0}
        assert len(await attempts(env, hid)) == 2

        s2, g2, hid2 = await held(env, "ovt", held_seat=2)
        orig = match_hold._attempt

        async def broken(*a, **kw):
            raise RuntimeError("row write failed")
        monkeypatch.setattr(match_hold, "_attempt", broken)
        r = await env.get("/api/v1/match/hold/mine", s2.steam(2), {"steam_id": s2.steam(2)})
        monkeypatch.setattr(match_hold, "_attempt", orig)
        assert r.status_code == 503
        assert (await hold_db(env, hid2))["offered_at"] is None
        assert await attempts(env, hid2) == []
    run_env(monkeypatch, body)


def test_t3_1_claim_refusals_grant_and_rotation(monkeypatch):
    """T3.1: a claim by another player is not_yours; a lapsed or ended hold
    is hold_lapsed (a late claim never binds); a closed series is
    lobby_closed; a live lease of another mode, or a hosted team or 1v2
    lobby seat, is other_mode. The grant answers a 256-bit token once,
    stores only its SHA-256 verifier, re-takes the lease for this mode and
    series, and moves no held_until; a repeat rotates the token and keeps
    the first claimed_at. Every claim writes its attempt row."""
    import hashlib as _h

    async def body(env):
        s, g, hid = await held(env)
        before = await hold_db(env, hid)
        assert (await claim(env, s, 2, hid))["reason"] == "not_yours"
        c1 = await claim(env, s, 1, hid)
        assert c1["status"] == "claimed" and len(c1["token"]) == 64, c1
        assert (c1["room_name"], c1["room_region"], c1["slot"], c1["team"], c1["game_id"],
                c1["hold"]) == (s.room, "eu", 1, 0, g, True), c1
        h1 = await hold_db(env, hid)
        assert h1["verifier"] == _h.sha256(c1["token"].encode()).hexdigest()
        assert c1["token"] not in str(dict(h1))
        assert h1["held_until"] == before["held_until"] and h1["claimed_at"] is not None
        lease = await env.conn.fetchrow(
            "SELECT mode, group_id FROM queue_leases WHERE player_id = $1", s.pid(1))
        assert (lease["mode"], lease["group_id"]) == ("team", s.sid)
        c2 = await claim(env, s, 1, hid)
        h2 = await hold_db(env, hid)
        assert c2["token"] != c1["token"]
        assert h2["verifier"] == _h.sha256(c2["token"].encode()).hexdigest()
        assert (h2["claimed_at"], h2["held_until"]) == (h1["claimed_at"], before["held_until"])
        assert await attempts(env, hid) == [(1, "claim", "refused", "not_yours"),
                                            (2, "claim", "ok", None), (3, "claim", "ok", None)]

        e, ge, hide = await held(env, "ovt")
        await env.post("/api/v1/match/hold/%s/end" % hide, e.steam(0),
                       {"steam_id": e.steam(0), "reason": "survivor_leave"})
        assert (await claim(env, e, 1, hide))["reason"] == "hold_lapsed"
        lp, gl, hidl = await held(env)
        await shift_hold(env, hidl, 300)
        assert (await claim(env, lp, 1, hidl))["reason"] == "hold_lapsed"
        cl, gc, hidc = await held(env)
        await env.conn.execute("UPDATE team_series SET status = 'completed' WHERE id = $1",
                               cl.sid)
        assert (await claim(env, cl, 1, hidc))["reason"] == "lobby_closed"
        om, go, hido = await held(env)
        await env.conn.execute(
            "INSERT INTO queue_leases (player_id, mode, group_id, generation, acquired_at, "
            " renewed_at, expires_at) VALUES ($1, 'ffa', gen_random_uuid(), gen_random_uuid(), "
            " clock_timestamp(), clock_timestamp(), clock_timestamp() + interval '5 minutes')",
            om.pid(1))
        assert (await claim(env, om, 1, hido))["reason"] == "other_mode"
        await env.conn.execute(
            "UPDATE queue_leases SET acquired_at = clock_timestamp() - interval '10 minutes',"
            " renewed_at = clock_timestamp() - interval '10 minutes',"
            " expires_at = clock_timestamp() - interval '1 second' "
            " WHERE player_id = $1", om.pid(1))      # lapsed (expires_at > renewed_at kept)
        assert (await claim(env, om, 1, hido))["status"] == "claimed"
        hs, gh, hidh = await held(env, "ovt")
        await env.conn.execute("DELETE FROM ovt_queue WHERE player_id = $1", hs.pid(1))
        await queue_row(env.conn, "team", hs.pid(1), hs.steam(1), "rjs1")
        assert (await claim(env, hs, 1, hidh))["reason"] == "other_mode"
        await env.conn.execute("DELETE FROM team_queue WHERE player_id = $1", hs.pid(1))
        assert (await claim(env, hs, 1, hidh))["status"] == "claimed"
        r = await env.post("/api/v1/match/hold/%s/claim" % uuid.uuid4(), hs.steam(1),
                           {"steam_id": hs.steam(1)})
        assert r.status_code == 404
        r = await env.post("/api/v1/match/hold/%s/claim" % hidh, hs.steam(1),
                           {"steam_id": hs.steam(1)}, token="tok:x")
        assert r.status_code == 401
    run_env(monkeypatch, body)


def test_h2_verifier_lifecycle_on_claim_state_bind_and_entry(monkeypatch, capsys):
    """Only the claim answer carries raw T; authorized reads carry SHA-256(T)
    while claimed or bound, including rotation, and clear it after entry."""
    raw_tokens = []

    async def body(env):
        s, g, hid = await held(env)

        async def views():
            state = (await env.get(
                "/api/v1/match/hold/%s/state" % hid, s.steam(0),
                {"steam_id": s.steam(0)})).json()
            by_room = (await env.get(
                "/api/v1/match/hold/by-room", s.steam(2),
                {"steam_id": s.steam(2), "room": s.room, "game_id": g})).json()
            return state, by_room

        before = await views()
        assert [v["verifier"] for v in before] == [None, None]

        first = await claim(env, s, 1, hid)
        raw_tokens.append(first["token"])
        first_hash = hashlib.sha256(first["token"].encode()).hexdigest()
        assert first["verifier"] == first_hash
        claimed = await views()
        assert [v["verifier"] for v in claimed] == [first_hash, first_hash]
        assert all(first["token"] not in str(v) for v in claimed)

        second = await claim(env, s, 1, hid)
        raw_tokens.append(second["token"])
        second_hash = hashlib.sha256(second["token"].encode()).hexdigest()
        assert second["verifier"] == second_hash and second_hash != first_hash
        rotated = await views()
        assert [v["verifier"] for v in rotated] == [second_hash, second_hash]
        assert all(second["token"] not in str(v) for v in rotated)

        await beat(env, s, 0, seen=[(10, s.steam(0)), (21, s.steam(1))])
        bound = await bind(env, s, 1, hid, 21)
        assert bound["verifier"] == second_hash
        bound_views = await views()
        assert [v["verifier"] for v in bound_views] == [second_hash, second_hash]

        accepted = await entered(env, s, 1, hid, g, 21)
        assert accepted["verifier"] is None
        after = await views()
        assert [v["verifier"] for v in after] == [None, None]

    run_env(monkeypatch, body, prefix="rjs2h2")
    captured = capsys.readouterr()
    assert all(token not in captured.out and token not in captured.err for token in raw_tokens)


def test_t3_7_bind_identity_and_entry(monkeypatch):
    """T3.7 server half: another session cannot bind the seat (not_yours);
    an unclaimed hold refuses (not_claimed); a bind no fresh beat of
    another fighter corroborates is refused (uncorroborated), and so is
    one where a fresh beat lists another actor for the held Steam id
    (actor_identity_mismatch); the genuine owner, claimed and corroborated,
    binds (seq + 1) and a repeat with the same actor answers bound while
    another actor is already_bound. Entry requires the bound actor, the
    hold's G and a corroborating beat, then closes the hold as entered once
    and spends the verifier; nothing binds or enters after the closure."""
    async def body(env):
        s, g, hid = await held(env)
        assert (await bind(env, s, 1, hid, 21))["reason"] == "not_claimed"
        await claim(env, s, 1, hid)
        assert (await bind(env, s, 2, hid, 21))["reason"] == "not_yours"
        assert (await bind(env, s, 1, hid, 21))["reason"] == "uncorroborated"
        await beat(env, s, 0, seen=[(10, s.steam(0)), (21, s.steam(1))])
        await beat(env, s, 3, seen=[(13, s.steam(3)), (22, s.steam(1))])
        assert (await bind(env, s, 1, hid, 21))["reason"] == "actor_identity_mismatch"
        await beat(env, s, 3, seen=[(13, s.steam(3)), (21, s.steam(1))])
        await env.conn.execute(
            "UPDATE match_seat_presence SET beat_at = clock_timestamp() - interval '30 seconds'"
            " WHERE room_name = $1 AND player_id = ANY($2::uuid[])", s.room, [s.pid(0), s.pid(3)])
        assert (await bind(env, s, 1, hid, 21))["reason"] == "uncorroborated"
        await beat(env, s, 0, seen=[(10, s.steam(0)), (21, s.steam(1))])
        b = await bind(env, s, 1, hid, 21)
        assert (b["status"], b["state"], b["seq"], b["bound_actor"]) == ("bound", "bound", 1, 21)
        h = await hold_db(env, hid)
        assert (h["bound_actor"], h["bound_region"], h["seq"]) == (21, "eu", 1)
        assert (await bind(env, s, 1, hid, 21))["status"] == "bound"
        assert (await bind(env, s, 1, hid, 23))["reason"] == "already_bound"
        assert (await hold_db(env, hid))["seq"] == 1

        assert (await entered(env, s, 2, hid, g, 21))["reason"] == "not_yours"
        assert (await entered(env, s, 1, hid, g, 23))["reason"] == "actor_mismatch"
        assert (await entered(env, s, 1, hid, uuid.uuid4(), 21))["reason"] == "game_mismatch"
        en = await entered(env, s, 1, hid, g, 21)
        assert (en["status"], en["state"], en["seq"], en["closed_reason"]) == \
            ("entered", "entered", 2, "entered"), en
        h = await hold_db(env, hid)
        assert h["verifier"] is None and h["entered_at"] == h["closed_at"]
        assert (await entered(env, s, 1, hid, g, 21))["reason"] == "hold_lapsed"
        assert (await claim(env, s, 1, hid))["reason"] == "hold_lapsed"
        assert (await hold_db(env, hid))["closed_at"] == h["closed_at"]
        kinds = [(k, o, r) for _, k, o, r in await attempts(env, hid)]
        assert kinds == [
            ("bind", "refused", "not_claimed"), ("claim", "ok", None),
            ("bind", "refused", "not_yours"), ("bind", "refused", "uncorroborated"),
            ("bind", "refused", "actor_identity_mismatch"), ("bind", "refused", "uncorroborated"),
            ("bind", "ok", None), ("bind", "ok", None),
            ("bind", "refused", "already_bound"),
            ("entered", "refused", "not_yours"), ("entered", "refused", "actor_mismatch"),
            ("entered", "refused", "game_mismatch"), ("entered", "ok", None),
            ("entered", "refused", "hold_lapsed"), ("claim", "refused", "hold_lapsed")], kinds

        u, gu, hidu = await held(env, "ovt")
        await claim(env, u, 1, hidu)
        await beat(env, u, 0, seen=[(10, u.steam(0)), (31, u.steam(1))])
        await bind(env, u, 1, hidu, 31)
        await env.conn.execute(
            "UPDATE match_seat_presence SET beat_at = clock_timestamp() - interval '30 seconds'"
            " WHERE room_name = $1", u.room)
        assert (await entered(env, u, 1, hidu, gu, 31))["reason"] == "uncorroborated"
        await env.conn.execute(
            "UPDATE match_seat_holds SET bound_at = bound_at - interval '61 seconds' WHERE id = $1",
            uuid.UUID(hidu))
        await beat(env, u, 2, seen=[(12, u.steam(2)), (31, u.steam(1))])
        assert (await entered(env, u, 1, hidu, gu, 31))["reason"] == "hold_lapsed"
    run_env(monkeypatch, body)


# == N6. S6 attempt rows: numbering, the second hold, rollback together =======

def test_t6_1_attempt_rows_numbered_and_rolled_back_with_their_action(monkeypatch):
    """T6.1: every hold action writes its attempt row in the action's own
    transaction. One full flow numbers its rows 1..5 in order (offered,
    claim, a refused bind, bind, entered); a second hold of the same player
    in the same room, at the next game, is n = 2 with its own numbering from
    1; an open refused while the room holds an open hold writes one open
    attempt row with no hold id; and a claim whose lease step fails leaves
    NO claim row, no claimed_at and no verifier, so the next claim is
    attempt 1."""
    async def body(env):
        s, g, hid = await held(env)
        m = await mine(env, s, 1)
        assert m["readmissible"] == 1 and m["hold_id"] == hid, m
        await claim(env, s, 1, hid)
        assert (await bind(env, s, 1, hid, 21))["reason"] == "uncorroborated"
        await beat(env, s, 0, seen=[(10, s.steam(0)), (21, s.steam(1))])
        assert (await bind(env, s, 1, hid, 21))["status"] == "bound"
        assert (await entered(env, s, 1, hid, g, 21))["status"] == "entered"
        assert await attempts(env, hid) == [
            (1, "offered", "ok", None), (2, "claim", "ok", None),
            (3, "bind", "refused", "uncorroborated"), (4, "bind", "ok", None),
            (5, "entered", "ok", None)]
        opened = await env.conn.fetch(
            "SELECT outcome, hold_id FROM match_hold_open_attempts WHERE room_name = $1",
            s.room)
        assert [(r["outcome"], str(r["hold_id"])) for r in opened] == [("opened", hid)]

        g2 = (await game_start(env, s, 0, prev=g))["game_id"]
        await beat(env, s, 1, actor=21)
        await backdate_presence(env, s, 1, 30)
        r2 = await open_hold(env, s, 1, 0, g2)
        assert r2.status_code == 200 and r2.json()["status"] == "opened", r2.text
        hid2 = r2.json()["hold_id"]
        h2 = await hold_db(env, hid2)
        assert (h2["n"], h2["player_id"], str(h2["game_id"])) == (2, s.pid(1), g2)
        assert await attempts(env, hid2) == []
        assert (await mine(env, s, 1))["hold_id"] == hid2
        assert await attempts(env, hid2) == [(1, "offered", "ok", None)]
        assert await attempts(env, hid) == [
            (1, "offered", "ok", None), (2, "claim", "ok", None),
            (3, "bind", "refused", "uncorroborated"), (4, "bind", "ok", None),
            (5, "entered", "ok", None)], "a row moved on the closed hold"

        await backdate_presence(env, s, 2, 30)
        rid = "reqbusy" + uuid.uuid4().hex[:8]
        busy = await open_hold(env, s, 2, 0, g2, rid=rid)
        assert busy.json()["reason"] == "room_busy", busy.text
        rows = await env.conn.fetch(
            "SELECT outcome, reason, hold_id FROM match_hold_open_attempts WHERE request_id = $1",
            rid)
        assert [(r["outcome"], r["reason"], r["hold_id"]) for r in rows] == \
            [("refused", "room_busy", None)]

        u, gu, hidu = await held(env, "ovt")
        fail = {"on": True}
        real = main._lease_acquire

        async def lease(*a, **k):
            if fail["on"]:
                raise RuntimeError("lease step failed (test)")
            return await real(*a, **k)
        monkeypatch.setattr(main, "_lease_acquire", lease)
        try:
            r = await env.post("/api/v1/match/hold/%s/claim" % hidu, u.steam(1),
                               {"steam_id": u.steam(1)})
            failed = r.status_code >= 500
        except RuntimeError:
            failed = True
        assert failed, "the claim answered through a failed lease step"
        h = await hold_db(env, hidu)
        assert (h["claimed_at"], h["verifier"]) == (None, None), dict(h)
        assert await attempts(env, hidu) == [], "an attempt row outlived its rolled-back claim"
        fail["on"] = False
        c = await claim(env, u, 1, hidu)
        assert c["status"] == "claimed" and len(c["token"]) == 64, c
        assert await attempts(env, hidu) == [(1, "claim", "ok", None)]
        h = await hold_db(env, hidu)
        assert h["claimed_at"] is not None and h["verifier"] is not None
    run_env(monkeypatch, body)
