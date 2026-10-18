"""H3 full-route evidence (fix 1 owed, NX0b): every admission site in main.py,
driven through its real route, in both winner orders, with no partial peer.

Fix 1 put one per-player gate (_lease_admission_gate, reached through
_lease_acquire / _lease_acquire_many) in front of every formation writer. Its
helper test drives the gate alone; this file drives each of the ten main.py
sites the source census names through the HTTP route that reaches it, against
a second transaction that commits a competing live commitment for one member
of the route's roster (a lease of another mode, written under the same gate's
player lock):

  * route_wins: the route passes its gate and is held there (holding the
    player locks) by a barrier on the gate's return; the competitor's gate
    must WAIT on the shared player row, the route then commits its formation,
    and the competitor's gate refuses: one commitment, the route's.
  * route_loses: the competitor holds the player lock with its commitment
    written; the route reaches its gate and must WAIT; the competitor commits;
    the route refuses with its contended answer and leaves no partial peer:
    every queue row, lease, series and lobby row of its roster is as it was
    before the route ran (the overlapping member's lease is the competitor's).

The barrier is a wrapper on main._lease_admission_gate that acts only on the
call whose caller is _lease_acquire or _lease_acquire_many called directly
from the case's site function (frame walk), so no other gate call of the route
is held. An omitted gate fails "H3 route gate" (the route never reaches it);
an omitted refusal fails "H3 route refused" (the route commits past it).

MATCH_HOLD_SRC and CF_TEST_PG_DSN have the meaning of test_match_hold_pg.py.
"""

import asyncio
import os
import sys
import time
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import test_match_hold_pg as hold_test  # noqa: E402
import test_match_hold_wiring_pg as wiring  # noqa: E402
import cf_pg  # noqa: E402
import database  # noqa: E402
import main  # noqa: E402

REAL_GATE = main._lease_admission_gate
WAIT_S = 0.3
ACQUIRERS = ("_lease_acquire", "_lease_acquire_many")


class Barrier:
    """Holds the one gate call made by the case's site (see the docstring)."""

    def __init__(self, site, hold_after):
        self.site, self.hold_after = site, hold_after
        self.entered, self.gated, self.release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self.fired, self.admitted = False, None

    def _is_site_call(self):
        f = sys._getframe(2)
        acq = f.f_back if f is not None else None
        return (f is not None and f.f_code.co_name in ACQUIRERS and acq is not None
                and acq.f_code.co_name == self.site)

    async def gate(self, db, player_ids, mode, group_id=None, **kw):
        if self.fired or not self._is_site_call():
            return await REAL_GATE(db, player_ids, mode, group_id, **kw)
        self.fired = True
        self.entered.set()
        res = await REAL_GATE(db, player_ids, mode, group_id, **kw)
        self.admitted = res[0]
        if self.hold_after:
            self.gated.set()
            await self.release.wait()
        return res


def _other(mode):
    return ("ffa", uuid.uuid4()) if mode == "ranked" else ("ranked", None)


async def probe(conn, pids, skip=None):
    """The commitment state of a roster: its leases (generation included),
    queue rows, and every series and lobby row of the case schema."""
    ids = list(pids)
    out = {"leases": sorted(tuple(r) for r in await conn.fetch(
        "SELECT player_id::text, mode, COALESCE(group_id::text, ''), generation::text"
        "  FROM queue_leases WHERE player_id = ANY($1::uuid[])", ids)
        if skip is None or r[0] != str(skip))}
    for t, link in (("ranked_queue", "matched_with"), ("team_queue", "series_id"),
                    ("ovt_queue", "series_id"), ("ffa_queue", "series_id")):
        out[t] = sorted(tuple(r) for r in await conn.fetch(
            "SELECT player_id::text, status, COALESCE(%s::text, ''), COALESCE(room_name, '')"
            "  FROM %s WHERE player_id = ANY($1::uuid[])" % (link, t), ids))
    for t in ("team_series", "ovt_series"):
        out[t] = sorted(tuple(r) for r in await conn.fetch(
            "SELECT id::text, status, COALESCE(photon_room_id, '') FROM %s" % t))
    for t in ("team_lobbies", "ovt_lobbies"):
        out[t] = sorted(tuple(r) for r in await conn.fetch(
            "SELECT id::text, status, COALESCE(series_id::text, ''),"
            "       COALESCE(photon_room_id, ''), player_count, CAST(member_ids AS text)"
            "  FROM %s" % t))
    out["ffa_lobbies"] = sorted(tuple(r) for r in await conn.fetch(
        "SELECT id::text, status, COALESCE(photon_room_id, ''),"
        "       CAST(member_ids AS text) FROM ffa_lobbies"))
    out["ffa_assembly_seats"] = await conn.fetchval("SELECT count(*) FROM ffa_assembly_seats")
    return out


async def lease_of(conn, pid):
    r = await conn.fetchrow(
        "SELECT mode, group_id FROM queue_leases WHERE player_id = $1"
        "   AND expires_at > clock_timestamp()", pid)
    return None if r is None else (r["mode"], r["group_id"])


# -- the ten sites: each setup returns the case the driver runs ---------------

class Case:
    def __init__(self, site, mode, pids, overlap, call, refuse, ok):
        self.site, self.mode, self.pids, self.overlap = site, mode, pids, overlap
        self.call, self.refuse, self.ok = call, refuse, ok


def _status(want):
    return lambda body: body.get("status") == want


async def _ranked_queue_poll(w, mp):
    ps = await hold_test.seed_players(w.conn, 2)
    for _, s in ps:
        await w.ok("POST", "/api/v1/queue/join", s, {"steam_id": s}, tag="ranked join")
    me = ps[0][1]
    return Case("queue_poll", "ranked", [p for p, _ in ps], ps[1][0],
                lambda: w.call("GET", "/api/v1/queue/poll/%s" % me, me), 503,
                _status("matched"))


async def _team_queue_poll(w, mp, players=None):
    ps = players or await hold_test.seed_players(w.conn, 4)
    for _, s in ps:
        await w.ok("POST", "/api/v1/team/queue/join", s, {"steam_id": s}, tag="team join")
    me = ps[0][1]
    return Case("team_queue_poll", "team", [p for p, _ in ps], ps[1][0],
                lambda: w.call("GET", "/api/v1/team/queue/poll/%s" % me, me), 503,
                _status("matched"))


async def _team_relock(w, mp):
    ps = await hold_test.seed_players(w.conn, 4)
    await w.conn.execute(
        "INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id, t1_series_wins, "
        " t2_series_wins, status, rebalance_count, created_at, spawn_confirmations, "
        " spawn_confirmed_by, region) VALUES (gen_random_uuid(), $1, $2, $3, $4, 1, 0, "
        " 'active', 0, clock_timestamp(), 0, '[]'::jsonb, 'eu')", *[p for p, _ in ps])
    c = await _team_queue_poll(w, mp, players=ps)
    c.site = "_team_relock_existing_series"
    return c


async def _ovt_queue_poll(w, mp):
    ps = await hold_test.seed_players(w.conn, 3)
    for _, s in ps:
        await w.ok("POST", "/api/v1/ovt/queue/join", s, {"steam_id": s}, tag="ovt join")
    me = ps[0][1]   # non-numeric ids: the decider is the earliest joiner
    return Case("ovt_queue_poll", "ovt", [p for p, _ in ps], ps[1][0],
                lambda: w.call("GET", "/api/v1/ovt/queue/poll/%s" % me, me), 503,
                _status("ready_join"))


async def _lobby_enroll(w, mp):
    ps = await hold_test.seed_players(w.conn, 2)
    lob = await w.ok("POST", "/api/v1/ovt/lobby/create", ps[0][1],
                     {"steam_id": ps[0][1], "caps": "ffa_asm1,rjs1"}, tag="ovt create")
    j = ps[1][1]
    return Case("_lobby_enroll_caller", "ovt", [ps[1][0]], ps[1][0],
                lambda: w.call("POST", "/api/v1/ovt/lobby/join", j,
                               {"steam_id": j, "lobby_id": lob["lobby_id"],
                                "caps": "ffa_asm1,rjs1"}), 409,
                lambda body: True)


async def _team_lobby_start(w, mp):
    ps = await hold_test.seed_players(w.conn, 4)
    lob = await w.ok("POST", "/api/v1/team/lobby/create", ps[0][1],
                     {"steam_id": ps[0][1], "caps": "ffa_asm1,rjs1"}, tag="team create")
    for i in (1, 2, 3):
        await w.ok("POST", "/api/v1/team/lobby/join", ps[i][1],
                   {"steam_id": ps[i][1], "lobby_id": lob["lobby_id"],
                    "caps": "ffa_asm1,rjs1"}, tag="team lobby join")
    h = ps[0][1]
    return Case("team_lobby_start", "team", [p for p, _ in ps], ps[1][0],
                lambda: w.call("POST", "/api/v1/team/lobby/start", h, {"steam_id": h}), 409,
                lambda body: bool(body.get("series_id")))


async def _ovt_lobby_start(w, mp):
    ps = await hold_test.seed_players(w.conn, 3)
    lob = await w.ok("POST", "/api/v1/ovt/lobby/create", ps[0][1],
                     {"steam_id": ps[0][1], "caps": "ffa_asm1,rjs1"}, tag="ovt create")
    for i in (1, 2):
        await w.ok("POST", "/api/v1/ovt/lobby/join", ps[i][1],
                   {"steam_id": ps[i][1], "lobby_id": lob["lobby_id"],
                    "caps": "ffa_asm1,rjs1"}, tag="ovt lobby join")
    h = ps[0][1]
    return Case("ovt_lobby_start", "ovt", [p for p, _ in ps], ps[2][0],
                lambda: w.call("POST", "/api/v1/ovt/lobby/start", h, {"steam_id": h}), 409,
                lambda body: bool(body.get("series_id")))


async def _ffa_lobby_enroll(w, mp):
    ps = await hold_test.seed_players(w.conn, 2)
    lob = await w.ok("POST", "/api/v1/ffa/lobby/create", ps[0][1],
                     {"steam_id": ps[0][1]}, tag="ffa create")
    j = ps[1][1]
    return Case("_ffa_lobby_enroll_caller", "ffa", [ps[1][0]], ps[1][0],
                lambda: w.call("POST", "/api/v1/ffa/lobby/join", j,
                               {"steam_id": j, "lobby_id": lob["lobby_id"]}), 409,
                lambda body: True)


async def _ffa_lock_roster(w, mp):
    ps = await hold_test.seed_players(w.conn, 3)
    lob = await w.ok("POST", "/api/v1/ffa/lobby/create", ps[0][1],
                     {"steam_id": ps[0][1]}, tag="ffa create")
    for i in (1, 2):
        await w.ok("POST", "/api/v1/ffa/lobby/join", ps[i][1],
                   {"steam_id": ps[i][1], "lobby_id": lob["lobby_id"]}, tag="ffa lobby join")
    h = ps[0][1]
    return Case("_ffa_lock_roster", "ffa", [p for p, _ in ps], ps[1][0],
                lambda: w.call("POST", "/api/v1/ffa/lobby/start", h, {"steam_id": h}), 503,
                lambda body: True)


async def _ffa_queue_poll(w, mp):
    ps = await hold_test.seed_players(w.conn, 3)
    # The join stamps this module clock; registered so the test leaves it as found.
    mp.setattr(main, "_ffa_gather_last_join_mono", main._ffa_gather_last_join_mono)
    for _, s in ps:
        await w.ok("POST", "/api/v1/ffa/queue/join", s, {"steam_id": s}, tag="ffa queue join")
    me = min((s for _, s in ps), key=main._ffa_sort_key)
    # The gather window: capped (waited past 120 s) and the pool seen now.
    mp.setattr(main, "_ffa_gather_started_mono", time.monotonic() - 130)
    mp.setattr(main, "_ffa_gather_pool_seen_mono", time.monotonic())

    async def call():
        main._ffa_gather_pool_seen_mono = time.monotonic()
        return await w.call("GET", "/api/v1/ffa/queue/poll/%s" % me, me)
    return Case("_ffa_queue_poll_inner", "ffa", [p for p, _ in ps],
                next(p for p, s in ps if s != me), call, 503, lambda body: True)


SETUPS = {
    "ranked_queue_poll": _ranked_queue_poll,
    "team_queue_poll": _team_queue_poll,
    "team_relock": _team_relock,
    "ovt_queue_poll": _ovt_queue_poll,
    "lobby_enroll": _lobby_enroll,
    "team_lobby_start": _team_lobby_start,
    "ovt_lobby_start": _ovt_lobby_start,
    "ffa_lobby_enroll": _ffa_lobby_enroll,
    "ffa_lock_roster": _ffa_lock_roster,
    "ffa_queue_poll": _ffa_queue_poll,
}


def test_h3_routes_cover_every_census_site():
    """The ten setups name the ten sites of the fix 1 source census."""
    census = {"queue_poll", "team_queue_poll", "_team_relock_existing_series",
              "ovt_queue_poll", "_lobby_enroll_caller", "team_lobby_start",
              "ovt_lobby_start", "_ffa_lobby_enroll_caller", "_ffa_lock_roster",
              "_ffa_queue_poll_inner"}
    for name in census:
        assert callable(getattr(main, name)), name
    assert len(SETUPS) == len(census)


def _run(monkeypatch, body):
    cf_pg.require_live_pg()
    monkeypatch.setattr(main, "_check_steam_session", hold_test._fake_session)

    async def _strict(request, steam_id, db):
        tok = request.headers.get("X-Session-Token") if request is not None else None
        return tok == "tok:" + str(steam_id)
    monkeypatch.setattr(main, "_strict_steam_session_ok", _strict)
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", wiring.SECRET)

    async def inside():
        async with cf_pg.case("h3route") as (c, sm):
            async def _db():
                async with sm() as s:
                    yield s
            monkeypatch.setitem(main.app.dependency_overrides, database.get_db, _db)
            monkeypatch.setattr(database, "async_session", sm)
            await body(wiring.W(c, sm), sm)
    asyncio.run(inside())


async def _first(*aws, timeout=60):
    done, _ = await asyncio.wait([asyncio.ensure_future(a) for a in aws],
                                 timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
    return done


@pytest.mark.parametrize("order", ["route_wins", "route_loses"])
@pytest.mark.parametrize("route", sorted(SETUPS))
def test_h3_full_route_gate_in_both_winner_orders(monkeypatch, route, order):
    async def body(w, sm):
        case = await SETUPS[route](w, monkeypatch)
        c_mode, c_gid = _other(case.mode)
        bar = Barrier(case.site, hold_after=(order == "route_wins"))
        monkeypatch.setattr(main, "_lease_admission_gate", bar.gate)

        if order == "route_wins":
            task = asyncio.ensure_future(case.call())
            await _first(bar.gated.wait(), task)
            assert bar.gated.is_set(), ("H3 route gate", route, order,
                                        task.done() and task.result().text[:300])
            assert bar.admitted is True, ("H3 route admitted", route)
            c_entered = asyncio.Event()

            async def compete():
                async with sm() as two:
                    c_entered.set()
                    admitted, _ = await REAL_GATE(two, [case.overlap], c_mode, c_gid)
                    if admitted:
                        await main._lease_acquire(two, case.overlap, c_mode, c_gid,
                                                  main.LEASE_TTL_ASSEMBLY, _gate_held=True)
                        await two.commit()
                    else:
                        await two.rollback()
                    return admitted
            other = asyncio.ensure_future(compete())
            await asyncio.wait_for(c_entered.wait(), 30)
            await asyncio.sleep(WAIT_S)
            assert not other.done(), ("H3 competitor waits", route)
            bar.release.set()
            r = await asyncio.wait_for(task, 120)
            assert r.status_code == 200 and case.ok(r.json()), \
                ("H3 route formed", route, r.status_code, r.text[:300])
            assert await asyncio.wait_for(other, 30) is False, ("H3 competitor refused", route)
            lease = await lease_of(w.conn, case.overlap)
            assert lease is not None and lease[0] == case.mode, \
                ("H3 one commitment", route, lease)
            return

        before = await probe(w.conn, case.pids, skip=case.overlap)
        locked, go = asyncio.Event(), asyncio.Event()

        async def hold():
            async with sm() as two:
                await REAL_GATE(two, [case.overlap], c_mode, c_gid)
                await main._lease_acquire(two, case.overlap, c_mode, c_gid,
                                          main.LEASE_TTL_ASSEMBLY, _gate_held=True)
                locked.set()
                await go.wait()
                await two.commit()
        holder = asyncio.ensure_future(hold())
        await asyncio.wait_for(locked.wait(), 30)
        task = asyncio.ensure_future(case.call())
        await _first(bar.entered.wait(), task)
        assert bar.entered.is_set(), ("H3 route gate", route, order,
                                      task.done() and task.result().text[:300])
        await asyncio.sleep(WAIT_S)
        assert not task.done(), ("H3 route waits", route)
        go.set()
        await asyncio.wait_for(holder, 30)
        r = await asyncio.wait_for(task, 120)
        assert r.status_code == case.refuse, \
            ("H3 route refused", route, r.status_code, r.text[:300])
        after = await probe(w.conn, case.pids, skip=case.overlap)
        assert after == before, ("H3 no partial peer", route,
                                 {k: (before[k], after[k]) for k in before
                                  if before[k] != after[k]})
        assert await lease_of(w.conn, case.overlap) == (c_mode, c_gid), \
            ("H3 competitor stands", route)
    _run(monkeypatch, body)
