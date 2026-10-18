"""NX1: the Stage 2 wiring in main.py (design V3 S1, T1.3 server half, T1.6).

Drives the real main.app routes against a cf_pg case schema: the hold flag is
latched in the transaction that issues a room, TRUE only when every member's
queue row carries the rjs1 capability token; it rides every join answer the
client pins from (the team poll's ready_join, the 1v2 poll's locked payload
and the 1v2 Start answer); a relock clears it with the room; and both
continuations copy it for the same room. The structure census pins every
issue site to one latch call within its own function.

MATCH_HOLD_SRC has the meaning of test_match_hold_pg.py (imported first, so
its module census and main's rebound name hold here too).
"""

import ast
import asyncio
import hashlib
import hmac as _hmac
import inspect
import os
import sys
import textwrap


HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import test_match_hold_pg as hold_test  # noqa: E402
import cf_pg  # noqa: E402
import database  # noqa: E402
import httpx  # noqa: E402
import main  # noqa: E402

match_hold = hold_test.match_hold
SECRET = "rjs2-wiring-secret"
VERSION = "1.41.0"


# -- structure census (DSN-free) -------------------------------------------

def _fn_src(name):
    return textwrap.dedent(inspect.getsource(getattr(main, name)))


def _calls(src, attr):
    tree = ast.parse(src)
    return sum(1 for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == attr)


def test_nx1_router_is_mounted_and_main_reaches_the_loaded_module():
    paths = {getattr(r, "path", "") for r in main.app.routes}
    for p in ("/api/v1/match/hold/open", "/api/v1/match/hold/mine",
              "/api/v1/match/game/start"):
        assert p in paths, ("router", p)
    assert main._match_hold is match_hold, "main rebound"


def test_nx1_every_issue_site_latches_once_and_the_relocks_clear():
    for fn in ("team_queue_poll", "ovt_queue_poll", "ovt_lobby_start"):
        assert _calls(_fn_src(fn), "_hold_latch") == 1, ("latch", fn)
    for fn in ("_team_relock_existing_series", "team_lobby_start"):
        src = _fn_src(fn)
        assert src.count("hold_v2 = FALSE,") == 1 and src.count("hold_room = NULL,") == 1, \
            ("relock clear", fn)
    for fn in ("team_series_continuation", "ovt_series_continuation"):
        assert _fn_src(fn).count("_continuation_hold(prior,") == 1, ("continuation", fn)


# -- live routes -------------------------------------------------------------

class W:
    def __init__(self, c, sm):
        self.c, self.sm, self.conn = c, sm, c.conn

    async def call(self, method, path, steam=None, body=None, params=None):
        headers = {"X-Mod-Version": VERSION}
        if steam is not None:
            headers["X-Session-Token"] = "tok:" + steam
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                     base_url="http://w", timeout=120) as cl:
            r = await cl.request(method, path, json=body, params=params, headers=headers)
        return r

    async def ok(self, method, path, steam=None, body=None, params=None, tag="call"):
        r = await self.call(method, path, steam, body, params)
        assert r.status_code == 200, (tag, r.status_code, r.text[:400])
        return r.json()


def run_w(monkeypatch, body, prefix="rjs2w"):
    cf_pg.require_live_pg()
    monkeypatch.setattr(main, "_check_steam_session", hold_test._fake_session)
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)

    async def inside():
        async with cf_pg.case(prefix) as (c, sm):
            async def _db():
                async with sm() as s:
                    yield s
            monkeypatch.setitem(main.app.dependency_overrides, database.get_db, _db)
            await body(W(c, sm))
    asyncio.run(inside())


def _caps(flags, i):
    return "ffa_asm1,rjs1" if flags[i] else "ffa_asm1"


async def ovt_start(w, flags):
    """A 1v2 lobby of three (caps per seat) started by its host: (players,
    Start answer, series row)."""
    ps = await hold_test.seed_players(w.conn, 3)
    lob = await w.ok("POST", "/api/v1/ovt/lobby/create", ps[0][1],
                     {"steam_id": ps[0][1], "caps": _caps(flags, 0)}, tag="ovt create")
    for i in (1, 2):
        await w.ok("POST", "/api/v1/ovt/lobby/join", ps[i][1],
                   {"steam_id": ps[i][1], "lobby_id": lob["lobby_id"],
                    "caps": _caps(flags, i)}, tag="ovt join")
    start = await w.ok("POST", "/api/v1/ovt/lobby/start", ps[0][1],
                       {"steam_id": ps[0][1]}, tag="ovt start")
    row = await w.conn.fetchrow(
        "SELECT id, hold_v2, hold_room, photon_room_id, solo_id, duo_a_id, duo_b_id"
        "  FROM ovt_series WHERE id = $1::uuid", start["series_id"])
    return ps, start, row


async def team_issue(w, flags, players=None):
    """A team lobby of four started by its host, all four ready, and the
    host's poll issuing the room: (players, poll answer, series row)."""
    ps = players or await hold_test.seed_players(w.conn, 4)
    lob = await w.ok("POST", "/api/v1/team/lobby/create", ps[0][1],
                     {"steam_id": ps[0][1], "caps": _caps(flags, 0)}, tag="team create")
    for i in (1, 2, 3):
        await w.ok("POST", "/api/v1/team/lobby/join", ps[i][1],
                   {"steam_id": ps[i][1], "lobby_id": lob["lobby_id"],
                    "caps": _caps(flags, i)}, tag="team join")
    start = await w.ok("POST", "/api/v1/team/lobby/start", ps[0][1],
                       {"steam_id": ps[0][1]}, tag="team start")
    await w.conn.execute(
        "UPDATE team_queue SET ready = true WHERE player_id = ANY($1::uuid[])",
        [p[0] for p in ps])
    poll = await w.ok("GET", "/api/v1/team/queue/poll/%s" % ps[0][1], ps[0][1],
                      tag="team poll")
    row = await w.conn.fetchrow(
        "SELECT id, hold_v2, hold_room, photon_room_id FROM team_series"
        " WHERE id = $1::uuid", poll.get("series_id") or start.get("series_id"))
    return ps, poll, row


def _sig(canonical):
    return _hmac.new(SECRET.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def test_t1_3_ovt_start_and_poll_carry_the_latched_flag(monkeypatch):
    """T1.3 (1v2 Start, 1v2 locked poll, 1v2 continuation): three rjs1 rows
    latch TRUE for the issued room; the Start answer and every member's
    locked poll answer say hold; a continuation for the same room copies the
    flag onto the new series."""
    async def body(w):
        ps, start, row = await ovt_start(w, [1, 1, 1])
        assert (row["hold_v2"], row["hold_room"]) == (True, start["room_name"]), \
            ("T1.3 ovt start row", dict(row))
        assert start["hold"] is True, ("T1.3 ovt start answer", start)
        poll = await w.ok("GET", "/api/v1/ovt/queue/poll/%s" % ps[1][1], ps[1][1],
                          tag="ovt poll")
        assert (poll["status"], poll["room_name"], poll["hold"]) == \
            ("ready_join", start["room_name"], True), ("T1.3 ovt poll answer", poll)

        await w.conn.execute(
            "UPDATE ovt_series SET status = 'completed', completed_at = NOW()"
            " WHERE id = $1", row["id"])
        steam = {p[0]: p[1] for p in ps}
        t1a, t1b, t2a = steam[row["solo_id"]], steam[row["duo_a_id"]], steam[row["duo_b_id"]]
        reporter = min((t1a, t1b, t2a))
        room = start["room_name"]
        cont = await w.ok("POST", "/api/v1/ovt/series/continuation", None, {
            "reporter_steam_id": reporter, "room_id": room, "region": "us",
            "t1a_steam": t1a, "t1b_steam": t1b, "t2a_steam": t2a, "t2b_steam": "",
            "hmac_signature": _sig("ovt-continuation:%s:%s:%s:%s:%s"
                                   % (t1a, t1b, t2a, room, reporter))},
            tag="ovt continuation")
        new = await w.conn.fetchrow(
            "SELECT hold_v2, hold_room, photon_room_id FROM ovt_series WHERE id = $1::uuid",
            cont["series_id"])
        assert (new["hold_v2"], new["hold_room"], new["photon_room_id"]) == \
            (True, room, room), ("T1.3 ovt continuation", dict(new))
    run_w(monkeypatch, body)


def test_t1_6_ovt_start_with_one_row_lacking_rjs1_is_today(monkeypatch, capsys):
    """T1.6 negative control (#391): one member row lacks rjs1, so the flag is
    FALSE at the issue, every answer says no hold, and the logs carry no
    Stage 2 line."""
    async def body(w):
        ps, start, row = await ovt_start(w, [1, 1, 0])
        assert (row["hold_v2"], row["hold_room"]) == (False, start["room_name"]), \
            ("T1.6 ovt row", dict(row))
        assert start["hold"] is False, ("T1.6 ovt start answer", start)
        poll = await w.ok("GET", "/api/v1/ovt/queue/poll/%s" % ps[2][1], ps[2][1],
                          tag="ovt poll")
        assert poll["hold"] is False, ("T1.6 ovt poll answer", poll)
    run_w(monkeypatch, body)
    assert "[HOLD]" not in capsys.readouterr().out, ("T1.6 logs",)


def test_t1_3_team_issue_relock_and_continuation(monkeypatch):
    """T1.3 (team hosted Start through the team poll, the relock, the team
    continuation): four rjs1 rows latch TRUE at the poll's room issue and the
    ready_join answer says hold; one row lacking rjs1 gives FALSE; an adopt
    relock of the same four clears the flag with the room, so the old room is
    no longer flagged, and the re-issue judges the new rows; a continuation
    copies the flag for the same room."""
    async def body(w):
        ps, poll, row = await team_issue(w, [1, 1, 1, 1])
        assert poll["status"] == "ready_join" and poll["hold"] is True, \
            ("T1.3 team answer", poll)
        assert (row["hold_v2"], row["hold_room"]) == (True, poll["room_name"]), \
            ("T1.3 team row", dict(row))

        # Relock: one game played (the series is resumable while active),
        # the four drop out of the sitting (queue rows and leases gone) and
        # start a new lobby asking for the stored split; Start adopts it.
        old_room = poll["room_name"]
        ids = [p[0] for p in ps]
        split = await w.conn.fetchrow(
            "SELECT t1a_id, t1b_id FROM team_series WHERE id = $1", row["id"])
        team_of = {p[0]: (1 if p[0] in (split["t1a_id"], split["t1b_id"]) else 2) for p in ps}
        await w.conn.execute("DELETE FROM team_queue WHERE player_id = ANY($1::uuid[])", ids)
        await w.conn.execute("DELETE FROM queue_leases WHERE player_id = ANY($1::uuid[])", ids)
        await w.conn.execute("UPDATE team_series SET t1_series_wins = 1 WHERE id = $1",
                             row["id"])
        lob = await w.ok("POST", "/api/v1/team/lobby/create", ps[0][1],
                         {"steam_id": ps[0][1], "caps": "rjs1",
                          "preferred_team": team_of[ps[0][0]]}, tag="relock create")
        for i in (1, 2, 3):
            await w.ok("POST", "/api/v1/team/lobby/join", ps[i][1],
                       {"steam_id": ps[i][1], "lobby_id": lob["lobby_id"],
                        "caps": "rjs1" if i != 3 else "",
                        "preferred_team": team_of[ps[i][0]]}, tag="relock join")
        start = await w.ok("POST", "/api/v1/team/lobby/start", ps[0][1],
                           {"steam_id": ps[0][1]}, tag="relock start")
        assert start.get("series_id") in (None, str(row["id"])), ("adopt", start)
        mid = await w.conn.fetchrow(
            "SELECT hold_v2, hold_room, photon_room_id FROM team_series WHERE id = $1",
            row["id"])
        assert (mid["hold_v2"], mid["hold_room"], mid["photon_room_id"]) == \
            (False, None, None), ("T1.3 relock clears", dict(mid), old_room)
        await w.conn.execute(
            "UPDATE team_queue SET ready = true WHERE player_id = ANY($1::uuid[])", ids)
        again = await w.ok("GET", "/api/v1/team/queue/poll/%s" % ps[1][1], ps[1][1],
                           tag="re-issue poll")
        assert again["status"] == "ready_join" and again["room_name"] != old_room \
            and again["hold"] is False, ("T1.3 re-issue judges the new rows", again)

        # Continuation: a fresh four, flagged, completed, continued.
        ps2, poll2, row2 = await team_issue(w, [1, 1, 1, 1])
        assert poll2["hold"] is True, ("T1.3 team answer 2", poll2)
        await w.conn.execute(
            "UPDATE team_series SET status = 'completed', completed_at = NOW()"
            " WHERE id = $1", row2["id"])
        srow = await w.conn.fetchrow(
            "SELECT t1a_id, t1b_id, t2a_id, t2b_id FROM team_series WHERE id = $1", row2["id"])
        steam = {p[0]: p[1] for p in ps2}
        t = [steam[srow[k]] for k in ("t1a_id", "t1b_id", "t2a_id", "t2b_id")]
        reporter = min(t)
        room = poll2["room_name"]
        cont = await w.ok("POST", "/api/v1/team/series/continuation", None, {
            "reporter_steam_id": reporter, "room_id": room, "region": "us",
            "t1a_steam": t[0], "t1b_steam": t[1], "t2a_steam": t[2], "t2b_steam": t[3],
            "hmac_signature": _sig("team-continuation:%s:%s:%s:%s:%s:%s"
                                   % (t[0], t[1], t[2], t[3], room, reporter))},
            tag="team continuation")
        new = await w.conn.fetchrow(
            "SELECT hold_v2, hold_room FROM team_series WHERE id = $1::uuid",
            cont["series_id"])
        assert (new["hold_v2"], new["hold_room"]) == (True, room), \
            ("T1.3 team continuation", dict(new), cont)
    run_w(monkeypatch, body)
