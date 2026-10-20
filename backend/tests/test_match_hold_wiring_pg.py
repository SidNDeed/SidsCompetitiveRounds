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


async def _assert_join_roster(w, mode, answer, caller, tag):
    """Compare the join's exact slot projection with the persisted roster."""
    table = "team_series" if mode == "team" else "ovt_series"
    row = await w.conn.fetchrow("SELECT * FROM %s WHERE id = $1::uuid" % table,
                                answer["series_id"])
    assert answer["room_name"] == row["photon_room_id"] and \
        answer["hold"] == bool(row["hold_v2"] and row["hold_room"] == row["photon_room_id"]), \
        (tag, "room, series, mode and hold", answer)
    cols = ("t1a_id", "t1b_id", "t2a_id", "t2b_id") if mode == "team" else \
        ("solo_id", "duo_a_id", "duo_b_id")
    people = {p["id"]: {"steam_id": p["steam_id"], "display_name": p["display_name"]}
              for p in await w.conn.fetch("SELECT id, steam_id, display_name FROM players WHERE id = ANY($1::uuid[])",
                                          [row[c] for c in cols])}
    if mode == "ovt":
        assert (answer.get("solo"), answer.get("duo"), answer.get("solo_extra_pick"),
                answer.get("side_assigned")) == \
            (people[row["solo_id"]], [people[row["duo_a_id"]], people[row["duo_b_id"]]],
             bool(row["solo_extra_pick"]), 1 if people[row["solo_id"]]["steam_id"] == caller else 2), \
            (tag, "exact roster", answer)
    else:
        sides = ([row["t1a_id"], row["t1b_id"]], [row["t2a_id"], row["t2b_id"]])
        own = 1 if caller in [people[pid]["steam_id"] for pid in sides[0]] else 2
        expected_teammates = [dict(people[pid], team_assigned=own)
                              for pid in sides[own - 1] if people[pid]["steam_id"] != caller]
        expected_opponents = [dict(people[pid], team_assigned=3 - own)
                              for pid in sides[2 - own]]
        def members(rows):
            return sorted((p["steam_id"], p["display_name"], p["team_assigned"])
                          for p in rows)
        assert answer["team_assigned"] == own and \
            members(answer["teammates"]) == members(expected_teammates) and \
            members(answer["opponents"]) == members(expected_opponents), \
            (tag, "exact sides and slots", answer)


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
        await _assert_join_roster(w, "ovt", start, ps[0][1], "F1.M2 Start roster")
        poll = await w.ok("GET", "/api/v1/ovt/queue/poll/%s" % ps[1][1], ps[1][1],
                          tag="ovt poll")
        assert (poll["status"], poll["room_name"], poll["hold"]) == \
            ("ready_join", start["room_name"], True), ("T1.3 ovt poll answer", poll)
        await _assert_join_roster(w, "ovt", poll, ps[1][1], "F1.M2 poll roster")
        for pid, steam_id in ps:
            joined = await w.ok("GET", "/api/v1/ovt/queue/poll/%s" % steam_id, steam_id)
            await _assert_join_roster(w, "ovt", joined, steam_id, "F1.M2 every poll roster")

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
        await _assert_join_roster(w, "ovt", start, ps[0][1], "F1.M2 unflagged roster")
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
        await _assert_join_roster(w, "team", poll, ps[0][1], "F1.M2 team roster")
        for pid, steam_id in ps:
            joined = await w.ok("GET", "/api/v1/team/queue/poll/%s" % steam_id, steam_id)
            assert joined["series_id"] == str(row["id"]), ("F1.M2 team series", joined)
            await _assert_join_roster(w, "team", joined, steam_id, "F1.M2 every team roster")

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
        await _assert_join_roster(w, "team", again, ps[1][1], "F1.M2 relock roster")
        for pid, steam_id in ps:
            joined = await w.ok("GET", "/api/v1/team/queue/poll/%s" % steam_id, steam_id)
            assert joined["series_id"] == str(row["id"]), ("F1.M2 relock series", joined)
            await _assert_join_roster(w, "team", joined, steam_id, "F1.M2 every relock roster")

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


# -- NX2: the janitor sweep and the live-points post during a hold ----------

class _Stop(BaseException):
    """Ends queue_cleanup_loop after one pass (the loop catches Exception)."""


def _one_pass_sleep(real_sleep):
    calls = {"n": 0}

    async def fake(secs, *a, **kw):
        if secs == 60:
            calls["n"] += 1
            if calls["n"] > 1:
                raise _Stop()
            return None
        return await real_sleep(secs, *a, **kw)
    return fake


def test_nx2_queue_cleanup_loop_sweeps_a_lapsed_hold(monkeypatch, capsys):
    """NX2 (V3 S2 write-once): one pass of queue_cleanup_loop closes a hold
    past its deadline with reason lapsed, stamped at held_until (never the
    sweep's time), and prints the sweep line."""
    async def body(env):
        s, g, _ = await hold_test.opened_series(env)
        r = await hold_test.open_hold(env, s, 1, 0, g, rid="req-nx2-sweep")
        assert r.status_code == 200 and r.json()["status"] == "opened", ("NX2 open", r.text)
        hid = r.json()["hold_id"]
        await hold_test.shift_hold(env, hid, 300)
        before = await hold_test.hold_db(env, hid)
        assert before["closed_at"] is None, ("NX2 open before",)
        monkeypatch.setattr(database, "async_session", env.sm)

        async def _no_audit():
            return None
        monkeypatch.setattr(main, "_run_service_policy_audit", _no_audit)
        monkeypatch.setattr(asyncio, "sleep", _one_pass_sleep(asyncio.sleep))
        try:
            await main.queue_cleanup_loop()
        except _Stop:
            pass
        after = await hold_test.hold_db(env, hid)
        assert (after["closed_reason"], after["closed_at"]) == \
            ("lapsed", before["held_until"]), ("NX2 swept", dict(after))
        assert after["held_until"] == before["held_until"], ("NX2 held_until moved",)
    hold_test.run_env(monkeypatch, body, prefix="rjs2nx2")
    assert "[HOLD] sweep closed {'lapsed': 1}" in capsys.readouterr().out, ("NX2 log",)


def _live_sig(sid, steam, t1, t2):
    return _sig_with(hold_test.SECRET, "team-live-points:%s:%s:%s:%s" % (sid, steam, t1, t2))


def _sig_with(secret, canonical):
    return _hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def test_nx2_live_points_during_an_open_team_hold_are_recorded_and_ignored(
        monkeypatch, capsys):
    """NX2 (V3 S2): while a team hold of the series is open, a member's
    live-points post answers ignored with reason hold_open, writes no points
    and no per-game record, and logs the post; once the hold is closed the
    same post is filed as today."""
    async def body(env):
        s, g, _ = await hold_test.opened_series(env)
        r = await hold_test.open_hold(env, s, 1, 0, g, rid="req-nx2-live")
        assert r.json()["status"] == "opened", ("NX2 open", r.text)
        hid = r.json()["hold_id"]

        async def _db():
            async with env.sm() as sess:
                yield sess
        monkeypatch.setitem(main.app.dependency_overrides, database.get_db, _db)

        async def post():
            steam = s.steam(0)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                         base_url="http://w", timeout=120) as cl:
                return await cl.post(
                    "/api/v1/team/series/%s/live-points" % s.sid,
                    params={"t1_points": 2, "t2_points": 2, "reporter_steam_id": steam,
                            "sig": _live_sig(s.sid, steam, 2, 2)},
                    headers={"X-Mod-Version": VERSION, "X-Session-Token": "tok:" + steam})

        ignored = await post()
        assert ignored.status_code == 200 and \
            (ignored.json()["status"], ignored.json()["reason"]) == ("ignored", "hold_open"), \
            ("NX2 ignored", ignored.status_code, ignored.text)
        row = await env.conn.fetchrow(
            "SELECT live_t1_points, live_t2_points FROM team_series WHERE id = $1", s.sid)
        assert (row[0] or 0, row[1] or 0) == (0, 0), ("NX2 no points", dict(row))
        assert await env.conn.fetchval(
            "SELECT count(*) FROM team_series_games WHERE series_id = $1", s.sid) == 0, \
            ("NX2 no game record",)

        await env.conn.execute(
            "UPDATE match_seat_holds SET closed_at = clock_timestamp(), closed_reason = 'ended'"
            " WHERE id = $1::uuid", hid)
        filed = await post()
        assert filed.status_code == 200 and filed.json()["status"] == "ok", \
            ("NX2 filed after close", filed.status_code, filed.text)
        row = await env.conn.fetchrow(
            "SELECT live_t1_points, live_t2_points FROM team_series WHERE id = $1", s.sid)
        assert (row[0], row[1]) == (2, 2), ("NX2 points after close", dict(row))
    hold_test.run_env(monkeypatch, body, prefix="rjs2nx2l")
    out = capsys.readouterr().out
    assert out.count("[HOLD] live points ignored") == 1, ("NX2 log", out[-800:])
