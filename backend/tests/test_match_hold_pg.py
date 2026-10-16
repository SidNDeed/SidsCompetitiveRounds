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
