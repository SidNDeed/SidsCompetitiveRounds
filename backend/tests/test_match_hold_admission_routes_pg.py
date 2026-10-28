"""H3 full-route evidence (fix 1 owed, NX0b): every admission site in main.py,
driven through its real route, in both winner orders, with no partial peer.

Fix 1 put one per-player gate (_lease_admission_gate, reached through
_lease_acquire / _lease_acquire_many) in front of every formation writer. Its
helper test drives the gate alone; this file drives every formation site of
the source census (test_match_hold_admission_gate_pg.formation_sites, derived
from the AST, with multiplicity) through the HTTP route that reaches it, against
a second transaction that commits a competing live commitment for one member
of the route's roster (a lease of another mode, written under the same gate's
player lock):

  * route_wins: the route passes its gate and is held there (holding the
    player locks) by a barrier on the gate's return; the competitor's gate
    must WAIT on the shared player row, the route then commits its formation,
    and the competitor's gate refuses: one commitment, the route's.
  * route_loses: the competitor holds the player lock with its commitment
    written; the route reaches its gate and must WAIT; the competitor commits;
    the route refuses with its contended answer and leaves no partial peer
    (the gate caps a contended lock wait at one second and answers 503
    admission_contended, the answer a client repeats: when a slow seat lets
    the cap end the wait first, the test repeats the call once the
    competitor has committed, and the repeat must refuse for it):
    every queue row, lease, series and lobby row of its roster is as it was
    before the route ran (the overlapping member's lease is the competitor's).

The barrier is a wrapper on main._lease_admission_gate that acts only on the
call whose caller is _lease_acquire or _lease_acquire_many called directly
from the case's site function (frame walk), so no other gate call of the route
is held. A function with two sites (queue_poll, queue_ready, team_queue_poll)
has each held on its own: the case names the site's source-order index k and
the barrier matches the calling frame's line against that call's span.
queue_ready's second site, the in-game fence, runs in the same request as its
first and behind the player locks that first site took, so no competitor can
commit between them: its route_loses order injects the gate's refusal at that
call and proves the route's answer and whole-formation rollback (the stage
controls' .G and .R mutants of that site are red on it), and the L1 bound of
that request is its first site's. An omitted gate fails "H3 route gate" (the
route never reaches it); an omitted refusal fails "H3 route refused" (the
route commits past it).

MATCH_HOLD_SRC and CF_TEST_PG_DSN have the meaning of test_match_hold_pg.py.
"""

import asyncio
import hashlib
import hmac
import importlib
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
import test_match_hold_admission_gate_pg as gate_test  # noqa: E402
import test_match_hold_wiring_pg as wiring  # noqa: E402
import cf_pg  # noqa: E402
import database  # noqa: E402
import main  # noqa: E402

REAL_GATE = main._lease_admission_gate
WAIT_S = 0.3
ACQUIRERS = ("_lease_acquire", "_lease_acquire_many")


class Barrier:
    """Holds the one gate call made by the case's site: the k-th admission
    call of the site function in source order (gate_test.admission_sites),
    matched by the calling frame's line against that call's span, so a
    function with two sites has each held on its own. With `refuse`, the k-th
    call answers the gate's refusal without running it (a site no competitor
    can reach: the request's first site holds the player locks)."""

    def __init__(self, site, k, hold_after, refuse=False):
        self.site, self.hold_after, self.refuse = site, hold_after, refuse
        span = gate_test.admission_sites()[site][k - 1]
        self.lo, self.hi = span.lineno, span.end_lineno
        self.entered, self.gated, self.release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self.fired, self.admitted = False, None

    def _is_site_call(self):
        f = sys._getframe(2)
        if f is not None and f.f_code.co_name in ACQUIRERS:
            f = f.f_back
        return (f is not None and f.f_code.co_name == self.site
                and self.lo <= f.f_lineno <= self.hi)

    async def gate(self, db, player_ids, mode, group_id=None, **kw):
        if self.fired or not self._is_site_call():
            return await REAL_GATE(db, player_ids, mode, group_id, **kw)
        self.fired = True
        self.entered.set()
        if self.refuse:
            self.admitted = False
            now = (await db.execute(main.text("SELECT clock_timestamp()"))).scalar_one()
            return False, now
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
    out["ranked_series"] = sorted(tuple(r) for r in await conn.fetch(
        "SELECT id::text, status FROM ranked_series"))
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


# -- the sites: each setup returns the case the driver runs -------------------

class Case:
    def __init__(self, site, mode, pids, overlap, call, refuse, ok, k=1,
                 same_request=False):
        self.site, self.mode, self.pids, self.overlap = site, mode, pids, overlap
        self.call, self.refuse, self.ok = call, refuse, ok
        # k: the site's source-order index among the function's admission
        # calls; same_request: reached only after an earlier site of the
        # same request admitted (see the module docstring).
        self.k, self.same_request = k, same_request


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


async def _ranked_pair(w):
    """A 1v1 pair the poll matched: both rows matched, the discovery leases held."""
    ps = await hold_test.seed_players(w.conn, 2)
    for _, s in ps:
        await w.ok("POST", "/api/v1/queue/join", s, {"steam_id": s}, tag="ranked join")
    me = ps[0][1]
    body = await w.ok("GET", "/api/v1/queue/poll/%s" % me, me, tag="ranked discovery")
    assert body.get("status") == "matched", ("ranked discovery", body)
    return ps, me


async def _ranked_queue_poll_issue(w, mp):
    """Both readied, no room yet: the poll's both-ready branch issues it (the
    site first in source order; discovery is the second)."""
    ps, me = await _ranked_pair(w)
    await w.conn.execute(
        "UPDATE ranked_queue SET ready = true WHERE player_id = ANY($1::uuid[])",
        [p for p, _ in ps])
    return Case("queue_poll", "ranked", [p for p, _ in ps], ps[1][0],
                lambda: w.call("GET", "/api/v1/queue/poll/%s" % me, me), 503,
                _status("ready_join"), k=1)


async def _queue_ready_formation(w, mp):
    """The opponent readied: this ready issues the room, renewing the pair's
    formation lease (site 1) and fencing the live game (site 2)."""
    ps, me = await _ranked_pair(w)
    opp = ps[1][1]
    body = await w.ok("POST", "/api/v1/queue/ready", opp, params={"steam_id": opp},
                      tag="opponent ready")
    assert body.get("status") == "waiting", ("opponent ready", body)
    return Case("queue_ready", "ranked", [p for p, _ in ps], ps[1][0],
                lambda: w.call("POST", "/api/v1/queue/ready", me, params={"steam_id": me}),
                503, _status("both_ready"), k=1)


async def _queue_ready_ingame(w, mp):
    c = await _queue_ready_formation(w, mp)
    c.k, c.same_request = 2, True
    return c


async def _team_queue_poll_issue(w, mp):
    """All four readied, no room yet: the poll's all-ready branch issues it
    (the site first in source order; assembly is the second)."""
    ps = await hold_test.seed_players(w.conn, 4)
    c = await _team_queue_poll(w, mp, players=ps)
    me = ps[0][1]
    body = await w.ok("GET", "/api/v1/team/queue/poll/%s" % me, me, tag="team assembly")
    assert body.get("status") == "matched", ("team assembly", body)
    await w.conn.execute(
        "UPDATE team_queue SET ready = true WHERE player_id = ANY($1::uuid[])",
        [p for p, _ in ps])
    c.k, c.ok = 1, _status("ready_join")
    return c


def _action_sig(canonical):
    return hmac.new(wiring.SECRET.encode(), canonical.encode(), hashlib.sha256).hexdigest()


async def _team_series_continuation(w, mp):
    """A completed 2v2 series in its room: the continuation mints the next one."""
    ps = await hold_test.seed_players(w.conn, 4)
    pids = [p for p, _ in ps]
    steams = [s for _, s in ps]
    room = "team-sitting-" + uuid.uuid4().hex[:8]
    await w.conn.execute(
        "INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id, t1_series_wins, "
        " t2_series_wins, status, rebalance_count, created_at, completed_at, "
        " photon_room_id, spawn_confirmations, spawn_confirmed_by, region) "
        " VALUES (gen_random_uuid(), $1, $2, $3, $4, 2, 0, 'completed', 0, "
        " clock_timestamp() - interval '10 min', clock_timestamp(), $5, 0, '[]'::jsonb, 'eu')",
        *pids, room)
    reporter = steams[0]
    body = {"reporter_steam_id": reporter, "room_id": room, "region": "eu",
            "t1a_steam": steams[0], "t1b_steam": steams[1],
            "t2a_steam": steams[2], "t2b_steam": steams[3]}
    body["hmac_signature"] = _action_sig("team-continuation:%s:%s:%s:%s:%s:%s" % (
        steams[0], steams[1], steams[2], steams[3], room, reporter))
    return Case("team_series_continuation", "team", pids, pids[1],
                lambda: w.call("POST", "/api/v1/team/series/continuation", reporter, body),
                503, _status("created"))


async def _ovt_series_continuation(w, mp):
    """A completed 1v2 series in its room: the continuation mints the next one."""
    ps = await hold_test.seed_players(w.conn, 3)
    pids = [p for p, _ in ps]
    steams = [s for _, s in ps]
    room = "ovt-sitting-" + uuid.uuid4().hex[:8]
    await w.conn.execute(
        "INSERT INTO ovt_series (solo_id, duo_a_id, duo_b_id, status, photon_room_id, "
        " region, completed_at) VALUES ($1, $2, $3, 'completed', $4, 'eu', clock_timestamp())",
        *pids, room)
    reporter = steams[0]
    body = {"reporter_steam_id": reporter, "room_id": room, "region": "eu",
            "t1a_steam": steams[0], "t1b_steam": steams[1],
            "t2a_steam": steams[2], "t2b_steam": steams[2]}
    body["hmac_signature"] = _action_sig("ovt-continuation:%s:%s:%s:%s:%s" % (
        steams[0], steams[1], steams[2], room, reporter))
    return Case("ovt_series_continuation", "ovt", pids, pids[1],
                lambda: w.call("POST", "/api/v1/ovt/series/continuation", reporter, body),
                503, _status("created"))


SETUPS = {
    "ranked_queue_poll_issue": _ranked_queue_poll_issue,
    "ranked_queue_poll": _ranked_queue_poll,
    "queue_ready_formation": _queue_ready_formation,
    "queue_ready_ingame": _queue_ready_ingame,
    "team_queue_poll_issue": _team_queue_poll_issue,
    "team_series_continuation": _team_series_continuation,
    "ovt_series_continuation": _ovt_series_continuation,
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


# (site function, k) of each setup: k is the site's source-order index among
# the function's admission calls (gate_test.admission_sites). queue_ready's
# in-game site is reached in the same request as its formation site.
COVERAGE = {
    "ranked_queue_poll_issue": ("queue_poll", 1),
    "ranked_queue_poll": ("queue_poll", 2),
    "queue_ready_formation": ("queue_ready", 1),
    "queue_ready_ingame": ("queue_ready", 2),
    "team_queue_poll_issue": ("team_queue_poll", 1),
    "team_queue_poll": ("team_queue_poll", 2),
    "team_relock": ("_team_relock_existing_series", 1),
    "team_series_continuation": ("team_series_continuation", 1),
    "ovt_queue_poll": ("ovt_queue_poll", 1),
    "ovt_series_continuation": ("ovt_series_continuation", 1),
    "lobby_enroll": ("_lobby_enroll_caller", 1),
    "team_lobby_start": ("team_lobby_start", 1),
    "ovt_lobby_start": ("ovt_lobby_start", 1),
    "ffa_lobby_enroll": ("_ffa_lobby_enroll_caller", 1),
    "ffa_lock_roster": ("_ffa_lock_roster", 1),
    "ffa_queue_poll": ("_ffa_queue_poll_inner", 1),
}
SAME_REQUEST = {"queue_ready_ingame"}
# The direct gate site: _rdm_claim gates itself and acquires under that gate.
# Its route coverage is the readmission suite's refusal tests, named here so
# the census cannot lose them silently.
DIRECT_SITES = {
    ("_rdm_claim", 1): ("test_ffa_readmit_pg",
                        ("test_t4_5_every_refusal_reason",
                         "test_nx0c_claim_takes_the_admission_gate_over_an_open_match_hold")),
}


def test_h3_routes_cover_every_census_site():
    """Every formation site of the AST-derived census has a setup here, every
    direct gate site a named route test elsewhere, and each setup names a
    site and index the census has: a site the census gains without coverage
    fails here."""
    assert set(SETUPS) == set(COVERAGE), (set(SETUPS) ^ set(COVERAGE))
    assert sorted(COVERAGE.values()) == gate_test.formation_sites(), \
        ("H3 route coverage", sorted(COVERAGE.values()), gate_test.formation_sites())
    direct = sorted((name, k) for name, sites in gate_test.admission_sites().items()
                    if name not in gate_test.ACQUIRERS
                    for k, site in enumerate(sites, 1) if site.callee == gate_test.GATE)
    assert direct == sorted(DIRECT_SITES), ("H3 direct sites", direct)
    for (name, _k), (module, tests) in DIRECT_SITES.items():
        mod = importlib.import_module(module)
        for t in tests:
            assert callable(getattr(mod, t, None)), (name, module, t)
    for name, (site, k) in COVERAGE.items():
        assert callable(getattr(main, site)), name
        assert 1 <= k <= len(gate_test.admission_sites()[site]), name
    assert SAME_REQUEST <= set(SETUPS)


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
        assert (case.site, case.k) == COVERAGE[route], (route, case.site, case.k)
        c_mode, c_gid = _other(case.mode)
        injected = order == "route_loses" and case.same_request
        bar = Barrier(case.site, case.k, hold_after=(order == "route_wins"),
                      refuse=injected)
        monkeypatch.setattr(main, "_lease_admission_gate", bar.gate)

        if injected:
            # The request's first site admitted and holds the player locks,
            # so no competitor can commit before this site: the gate's
            # refusal is injected at the call, and the route must answer
            # its contended refusal with the whole formation rolled back.
            before = await probe(w.conn, case.pids)
            lease_before = await lease_of(w.conn, case.overlap)
            task = asyncio.ensure_future(case.call())
            await _first(bar.entered.wait(), task)
            assert bar.entered.is_set(), ("H3 route gate", route, order,
                                          task.done() and task.result().text[:300])
            r = await asyncio.wait_for(task, 120)
            assert r.status_code == case.refuse, \
                ("H3 route refused", route, r.status_code, r.text[:300])
            after = await probe(w.conn, case.pids)
            assert after == before, ("H3 no partial peer", route,
                                     {k: (before[k], after[k]) for k in before
                                      if before[k] != after[k]})
            assert await lease_of(w.conn, case.overlap) == lease_before, \
                ("H3 lease as before", route)
            return

        if order == "route_wins":
            task = asyncio.ensure_future(case.call())
            await _first(bar.gated.wait(), task)
            assert bar.gated.is_set(), ("H3 route gate", route, order,
                                        task.done() and task.result().text[:300])
            assert bar.admitted is True, ("H3 route admitted", route)
            c_entered = asyncio.Event()

            async def compete():
                # The gate's one-second cap on a contended lock wait answers 503
                # admission_contended, which a caller repeats; the competitor
                # repeats its gate until the definitive answer, as a route
                # would, so a slow seat's wait never reads as a verdict.
                while True:
                    async with sm() as two:
                        c_entered.set()
                        try:
                            admitted, _ = await REAL_GATE(two, [case.overlap], c_mode, c_gid)
                        except main.HTTPException as exc:
                            if exc.status_code != 503:
                                raise
                            await asyncio.sleep(0.05)
                            continue
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
        # The route is inside its gate's lock wait: not answered. Checked at
        # once, because the gate's one-second cap on that wait runs from here
        # and the competitor's commit below has to land inside it.
        assert not task.done(), ("H3 route waits", route)
        go.set()
        await asyncio.wait_for(holder, 30)
        r = await asyncio.wait_for(task, 120)
        if r.status_code == 503 and case.refuse != 503:
            # The cap ended the wait before the commit landed (a slow seat):
            # the repeat a client makes meets the committed commitment.
            r = await asyncio.wait_for(case.call(), 120)
        assert r.status_code == case.refuse, \
            ("H3 route refused", route, r.status_code, r.text[:300])
        after = await probe(w.conn, case.pids, skip=case.overlap)
        assert after == before, ("H3 no partial peer", route,
                                 {k: (before[k], after[k]) for k in before
                                  if before[k] != after[k]})
        assert await lease_of(w.conn, case.overlap) == (c_mode, c_gid), \
            ("H3 competitor stands", route)
    _run(monkeypatch, body)


@pytest.mark.parametrize("route", sorted(r for r in SETUPS if r not in SAME_REQUEST))
def test_l1_shared_admission_wait_is_bounded_for_every_caller(monkeypatch, route):
    """Each formation returns while its blocker still owns the player lock.

    FOR NO KEY UPDATE permits the route's foreign-key inserts, so the blocker
    targets the shared admission acquisition. The state probe includes all
    roster leases, queues, series, lobbies and assembly seats.
    """
    async def body(w, sm):
        case = await SETUPS[route](w, monkeypatch)
        before = await probe(w.conn, case.pids)
        bar = Barrier(case.site, case.k, hold_after=False)
        monkeypatch.setattr(main, "_lease_admission_gate", bar.gate)
        task, response, after, bounded = None, None, None, False
        async with sm() as blocker:
            await blocker.execute(main.text(
                "SELECT id FROM players WHERE id = CAST(:pid AS uuid) "
                "FOR NO KEY UPDATE"), {"pid": str(case.overlap)})
            try:
                task = asyncio.ensure_future(case.call())
                await _first(bar.entered.wait(), task)
                assert bar.entered.is_set(), ("L1 route gate", route,
                    task.done() and task.result().text[:300])
                # The production cap is one second per contended statement.
                # This barrier has exactly one blocked player. The bound here
                # proves the wait ends (an unbounded one runs to the rescue in
                # the finally); ten seconds absorbs a shared seat's scheduling.
                done, _ = await asyncio.wait([task], timeout=10.0)
                bounded = task in done
                if bounded:
                    response = task.result()
                    after = await probe(w.conn, case.pids)
            finally:
                await blocker.rollback()
                if task is not None and not task.done():
                    await asyncio.wait_for(task, 30)
        assert bounded, ("L1 admission bound", route)
        assert response.status_code == 503, (
            "L1 retryable refusal", route, response.status_code, response.text[:300])
        assert after == before, ("L1 whole formation rollback", route,
            {key: (before[key], after[key]) for key in before if before[key] != after[key]})
    _run(monkeypatch, body)


def test_l1_existing_tighter_bound_wins_and_success_restores_setting(monkeypatch):
    """Read the effective server setting at the actual player-lock statement."""
    async def body(w, sm):
        players = await hold_test.seed_players(w.conn, 1)
        pid = players[0][0]
        for supplied, effective, restored in (("0", 1000, 0),
                                              ("10s", 1000, 10000),
                                              ("25ms", 25, 25)):
            async with sm() as db:
                await db.execute(main.text(
                    "SELECT set_config('lock_timeout', :value, true)"),
                    {"value": supplied})
                real_execute = db.execute
                seen = []

                async def observe(statement, *args, **kwargs):
                    if ("SELECT id FROM players" in str(statement)
                            and "FOR NO KEY UPDATE" in str(statement)):
                        seen.append((await real_execute(main.text(
                            "SELECT setting::int FROM pg_settings "
                            "WHERE name = 'lock_timeout' AND unit = 'ms'"))).scalar_one())
                    return await real_execute(statement, *args, **kwargs)

                monkeypatch.setattr(db, "execute", observe)
                admitted, _ = await REAL_GATE(db, [pid], "ranked")
                assert admitted, ("L1 successful formation", supplied)
                assert seen == [effective], ("L1 tighter bound", supplied, seen)
                assert (await real_execute(main.text(
                    "SELECT setting::int FROM pg_settings WHERE name = 'lock_timeout' "
                    "AND unit = 'ms'"))).scalar_one() == restored, ("L1 restored setting", supplied)
                missing, _ = await REAL_GATE(db, [uuid.uuid4()], "ranked")
                assert not missing, ("L1 missing player", supplied)
                assert seen == [effective, effective], ("L1 missing-player bound", supplied, seen)
                assert (await real_execute(main.text(
                    "SELECT setting::int FROM pg_settings WHERE name = 'lock_timeout' "
                    "AND unit = 'ms'"))).scalar_one() == restored, ("L1 missing-player restore", supplied)
                await db.rollback()
    _run(monkeypatch, body)
