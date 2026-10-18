"""NX3: discovery, seating and spectating around a live hold (design V3 S3).

T3.2: the team and 1v2 polls answer `readmissible` only to rdm=1. The seat
rule: a player with a live hold is seated by no matcher and no lobby. T3.6:
in the flagged room of a 2v2 series the spectate attest is judged over H, the
server's own set of members with a live hold, and the headroom counts the
held seat as occupied.

Runs the real main.app routes on the hold suite's case schema (its Env and
seeding; MATCH_HOLD_SRC as in test_match_hold_pg.py).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))
sys.path.insert(0, HERE)

import test_match_hold_pg as hold_test  # noqa: E402
import database  # noqa: E402
import httpx  # noqa: E402
import main  # noqa: E402

VERSION = "1.41.0"


async def _session_ok(request, steam_id, db):
    token = request.headers.get("X-Session-Token") if request is not None else None
    return token == "tok:" + str(steam_id)


def _mount(env, monkeypatch):
    async def _db():
        async with env.sm() as s:
            yield s
    monkeypatch.setitem(main.app.dependency_overrides, database.get_db, _db)
    monkeypatch.setattr(main, "_strict_steam_session_ok", _session_ok)


async def _call(method, path, steam, body=None, params=None):
    headers = {"X-Mod-Version": VERSION, "X-Session-Token": "tok:" + steam}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                 base_url="http://d", timeout=120) as cl:
        return await cl.request(method, path, json=body, params=params, headers=headers)


async def _held(env, mode="team"):
    """A flagged series of `mode` whose seat 1 has an open hold."""
    s, g, _ = await hold_test.opened_series(env, mode=mode)
    r = await hold_test.open_hold(env, s, 1, 0, g, rid="req-nx3-%s" % mode)
    assert r.status_code == 200 and r.json()["status"] == "opened", ("NX3 open", r.text)
    return s, r.json()["hold_id"]


def _poll_path(mode, steam):
    return ("/api/v1/team/queue/poll/%s" if mode == "team"
            else "/api/v1/ovt/queue/poll/%s") % steam


def test_t3_2_polls_answer_readmissible_only_with_rdm(monkeypatch):
    """T3.2: the held player's team and 1v2 polls carry no readmissible
    field without rdm=1 (today's answer); with rdm=1 they answer readmissible
    with the hold."""
    async def body(env):
        _mount(env, monkeypatch)
        for mode in ("team", "ovt"):
            s, hid = await _held(env, mode)
            plain = await _call("GET", _poll_path(mode, s.steam(1)), s.steam(1))
            assert plain.status_code == 200 and "readmissible" not in plain.json(), \
                ("T3.2 no rdm", mode, plain.status_code, plain.text[:300])
            rdm = await _call("GET", _poll_path(mode, s.steam(1)), s.steam(1),
                              params={"rdm": 1})
            js = rdm.json()
            assert rdm.status_code == 200 and (js.get("readmissible"), js.get("hold_id")) \
                == (1, hid), ("T3.2 rdm", mode, rdm.status_code, rdm.text[:300])
    hold_test.run_env(monkeypatch, body, prefix="rjs2nx3p")


def test_t3_seat_rule_no_lobby_seats_a_held_player(monkeypatch):
    """V3 S3: a player with a live hold can neither open nor join a team or
    1v2 lobby while the hold lasts (409); once it closes, the same create is
    seated."""
    async def body(env):
        _mount(env, monkeypatch)
        s, hid = await _held(env, "team")
        for mode in ("team", "ovt"):
            r = await _call("POST", "/api/v1/%s/lobby/create" % mode, s.steam(1),
                            {"steam_id": s.steam(1)})
            assert r.status_code == 409, ("T3 lobby seat", mode, r.status_code, r.text[:300])
        await env.conn.execute(
            "UPDATE match_seat_holds SET closed_at = clock_timestamp(), closed_reason = 'ended'"
            " WHERE id = $1::uuid", hid)
        await env.conn.execute("DELETE FROM team_queue WHERE player_id = $1", s.pid(1))
        await env.conn.execute("DELETE FROM queue_leases WHERE player_id = $1", s.pid(1))
        r = await _call("POST", "/api/v1/ovt/lobby/create", s.steam(1), {"steam_id": s.steam(1)})
        assert r.status_code == 200, ("T3 lobby seat after close", r.status_code, r.text[:300])
    hold_test.run_env(monkeypatch, body, prefix="rjs2nx3s")


def _attest_body(s, steam, seats, cap=9):
    roster = sorted(s.steam(i) for i in seats)
    return {"steam_id": steam, "mode": "2v2", "room_name": s.room, "region": "eu",
            "actor_number": 1, "fighter_target": len(roster), "room_capacity": cap,
            "phase": "battle", "roster": ",".join(roster)}


def test_t3_6_attest_over_the_server_held_set(monkeypatch):
    """T3.6: with seat 1 held, the three present fighters attest a roster
    of three and are accepted (the room stays watchable across the 150 s
    freshness); the spectate headroom counts the held seat."""
    async def body(env):
        _mount(env, monkeypatch)
        s, _hid = await _held(env, "team")
        for i in (0, 2, 3):
            r = await _call("POST", "/api/v1/spectate/participant-attest", s.steam(i),
                            _attest_body(s, s.steam(i), (0, 2, 3)))
            assert r.status_code == 200, ("T3.6 attest over H", i, r.status_code, r.text[:300])
        game = await env.conn.fetchrow(
            "SELECT * FROM spectate_games WHERE room_name = $1 AND ended_at IS NULL", s.room)
        async with env.sm() as db:
            adm = await main._spectate_admission(db, dict(game))
        assert adm["physical_headroom"] == 9 - 4, ("T3.6 headroom", adm)
    hold_test.run_env(monkeypatch, body, prefix="rjs2nx3a")


def test_t3_6_attest_omitting_a_live_fighter_is_refused(monkeypatch):
    """T3.6: with seat 1 held, a roster naming the held seat but omitting
    the live seat 3 stands refused (roster_mismatch)."""
    async def body(env):
        _mount(env, monkeypatch)
        s, _hid = await _held(env, "team")
        r = await _call("POST", "/api/v1/spectate/participant-attest", s.steam(0),
                        _attest_body(s, s.steam(0), (0, 1, 2)))
        assert (r.status_code, r.json().get("detail")) == (409, "roster_mismatch"), \
            ("T3.6 live omitted", r.status_code, r.text[:300])
    hold_test.run_env(monkeypatch, body, prefix="rjs2nx3o")


def test_t3_6_attest_without_a_server_hold_is_refused(monkeypatch):
    """T3.6: in a flagged room with no live hold, a roster omitting a member
    stands refused: H is the server's, never what the caller left out."""
    async def body(env):
        _mount(env, monkeypatch)
        s = await hold_test.seed_series(env.conn, "team")
        r = await _call("POST", "/api/v1/spectate/participant-attest", s.steam(0),
                        _attest_body(s, s.steam(0), (0, 2, 3)))
        assert (r.status_code, r.json().get("detail")) == (409, "roster_mismatch"), \
            ("T3.6 no server hold", r.status_code, r.text[:300])
    hold_test.run_env(monkeypatch, body, prefix="rjs2nx3n")


def test_t3_seat_rule_the_1v2_lock_passes_over_a_held_searcher(monkeypatch):
    """V3 S3: a held player searching the 1v2 queue beside two others is not
    taken into a lock: every poll answers (no admission refusal of the whole
    trio) and no 1v2 series names the held player."""
    async def body(env):
        _mount(env, monkeypatch)
        s, _hid = await _held(env, "team")
        await env.conn.execute("DELETE FROM team_queue WHERE player_id = $1", s.pid(1))
        await env.conn.execute("DELETE FROM queue_leases WHERE player_id = $1", s.pid(1))
        others = await hold_test.seed_players(env.conn, 2)
        trio = [(s.pid(1), s.steam(1))] + others
        for pid, steam in trio:
            await hold_test.queue_row(env.conn, "ovt", pid, steam, "rjs1")
        await env.conn.execute(
            "UPDATE ovt_queue SET last_polled = clock_timestamp(), joined_at = clock_timestamp()"
            " WHERE player_id = ANY($1::uuid[])", [p for p, _ in trio])
        for _pid, steam in trio:
            r = await _call("GET", "/api/v1/ovt/queue/poll/%s" % steam, steam)
            assert r.status_code == 200, ("T3 1v2 lock", steam, r.status_code, r.text[:300])
        n = await env.conn.fetchval(
            "SELECT count(*) FROM ovt_series WHERE $1 IN (solo_id, duo_a_id, duo_b_id)",
            s.pid(1))
        assert n == 0, ("T3 1v2 lock seated the held player", n)
    hold_test.run_env(monkeypatch, body, prefix="rjs2nx3l")
