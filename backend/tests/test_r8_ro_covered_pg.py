"""The read-only bound applied to the REAL covered set (ruling
REHEARSAL-FOUR-R7-A1 M1, R7-A2).

1. Enumeration. Both walks run (the whole a1 file, the gate file's source
   walks) under the ro_spy plugin; every execute position the walks ask the
   frozen lookup about inside backend/api is collected (round 8, M1: the S
   analysis is retired), and the set must equal the frozen lists
   ro_covered.COVERED and ro_covered.WRITERS together, exactly, both ways:
   a visited position in neither table is a finding. No position may be
   ambiguous, every answer is the read table's, and the walks must pass.

2. Execution. A clone of scr_seat_ro_tmpl is built by the harness under the
   admin DSN (the production schema, cf_pg.case, and the fixture rows) and
   granted by ro_role.grant as its owner; then every covered span runs its
   PRODUCTION code (backend/api functions, called with arguments) on a
   session opened as scr_seat_ro, whose every connection asserts SELECT
   current_user, session_user equals the role. RecordingSession logs the
   production file:line and outcome of every statement. Each covered
   position's measured outcome must equal OUTCOME: 'ok' (it ran, green), or
   ('not reached', <the statement that refused first>, SQLSTATE) when the
   production path refuses earlier (those positions leave the read-only
   claim; each is a QUESTION in the hand-back). Each WRITERS position the
   drivers reach must equal WRITER_OUTCOME: refused (25006), the writer
   proof by the role, or, for the two statements the role cannot refuse
   (main.py:16839, a transaction-local set_config of lock_timeout, and
   main.py:51703, pg_advisory_xact_lock), 'ok' as measured: writers by S
   whose bound the role does not measure.

Runs under CF_TEST_PG_DSN naming an admin DSN (superuser, or LOGIN
CREATEDB). Never skips. RO8_ENUM_FROM (a JSON of a previous enumeration of
the same tree) replaces step 1's live walk run; it exists for the mutant
runs only and the test says so in its failure text when it is set.
"""

import asyncio
import collections
import datetime
import json
import os
import sys
import types
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import cf_asm  # noqa: E402
import cf_pg  # noqa: E402
import main  # noqa: E402
import match_hold  # noqa: E402
import match_report_window  # noqa: E402
import ro_covered  # noqa: E402
import ro_role  # noqa: E402
import tournaments  # noqa: E402

ADMIN_DSN = ro_role.pg_dsn(os.environ.get("CF_TEST_PG_DSN") or "")


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------ 1. enumeration

def _enumeration():
    cached = os.environ.get("RO8_ENUM_FROM")
    if cached:
        with open(cached, encoding="utf-8") as fh:
            data = json.load(fh)
        return ({tuple(p) for p in data["positions"]}, data["ambiguous"], (0, ""),
                "RO8_ENUM_FROM=%s (a recorded enumeration, not a live walk run)" % cached)
    pos, amb, _syn, rc = ro_covered.enumerate_positions()
    return pos, amb, rc, "live walk run"


def test_covered_set_is_the_enumeration_both_ways():
    pos, amb, rc, source = _enumeration()
    frozen_read, frozen_lock = set(ro_covered.COVERED), set(ro_covered.WRITERS)
    assert len(frozen_read) == len(ro_covered.COVERED), "a duplicate covered entry"
    assert len(frozen_lock) == len(ro_covered.WRITERS), "a duplicate writer entry"
    assert not (frozen_read & frozen_lock)
    visited = {p[:5] for p in pos}
    frozen = frozen_read | frozen_lock
    # every difference reported at once: the visited set both ways, the
    # unplaceable or inconsistent answers, and the walks' own outcome
    problems = {
        "visited, in neither table": sorted(visited - frozen),
        "frozen, not visited": sorted(frozen - visited),
        "ambiguous or not the table's answer": amb,
        "the walks failed under the spy": [] if rc[0] == 0 else [rc],
    }
    assert not any(problems.values()), (source, problems)


# ------------------------------------------------------------- 2. execution

PID_NS = uuid.UUID("7d1e0c5a-8b1f-4c8e-9a0d-000000000808")


def _u(key):
    return uuid.uuid5(PID_NS, key)


class Seed:
    """The rows the harness wrote under the admin DSN."""


async def _player(conn, key):
    steam = "7656119900%07d" % (abs(hash(key)) % 10000000)
    return await conn.fetchval(
        "INSERT INTO players (id, steam_id, display_name) VALUES ($1, $2, $3) RETURNING id",
        _u(key), steam, "rf8ro " + key), steam


async def seed(env):
    """Every row the drivers read, written as admin (env.conn)."""
    conn = env.conn
    s = Seed()
    s.ranked = await _player(conn, "ranked")
    await conn.execute("INSERT INTO ranked_queue (player_id, steam_id, display_name, status)"
                       " VALUES ($1, $2, 'q', 'searching')", *s.ranked)
    import test_match_hold_pg as mh
    s.team = await mh.seed_series(conn, "team", flag=False, queue=True)
    s.ovt = await mh.seed_series(conn, "ovt", flag=False, queue=True)
    s.team_search = await _player(conn, "team_search")
    await mh.queue_row(conn, "team", s.team_search[0], s.team_search[1], "rjs1")
    s.ovt_search = await _player(conn, "ovt_search")
    await mh.queue_row(conn, "ovt", s.ovt_search[0], s.ovt_search[1], "rjs1")
    s.lob = await env.lobby(4)
    s.rdm_pid = s.lob.pids[0]
    await conn.execute(
        "INSERT INTO ffa_seat_readmissions (lobby_id, player_id, n, anchor_at, held_at,"
        "  hold_until) VALUES ($1, $2, 1, clock_timestamp(), clock_timestamp(),"
        "  clock_timestamp() + interval '10 minutes')", s.lob.lid, s.rdm_pid)
    s.attempt_rid = "rf8ro-" + uuid.uuid4().hex[:12]
    await conn.execute(
        "INSERT INTO match_hold_open_attempts (request_id, room_name, at, outcome, reason)"
        " VALUES ($1, 'rf8ro_room', clock_timestamp(), 'refused', 'pending')", s.attempt_rid)
    s.now = await conn.fetchval("SELECT clock_timestamp()")
    return s


def _rdm_ctx(db, s):
    return types.SimpleNamespace(
        db=db, lid=s.lob.lid, now=s.now,
        lobby={"status": "active", "departed_ids": []})


def _rdm_me(s):
    return {"player_id": s.rdm_pid, "released_at": None, "hold_n": 1,
            "hold_until": s.now + datetime.timedelta(minutes=5)}


# Each driver: (name, coroutine(db, seed, mp)). One role session per driver.
DRIVERS = collections.OrderedDict([
    # gate walk spans
    ("match_hold._ctx_now", lambda db, s, mp: match_hold._ctx_now(db)),
    ("match_hold._open_attempt_row",
     lambda db, s, mp: match_hold._open_attempt_row(db, s.attempt_rid)),
    ("main._rdm_row", lambda db, s, mp: main._rdm_row(_rdm_ctx(db, s), s.rdm_pid, 1)),
    ("main._rdm_claim", lambda db, s, mp: main._rdm_claim(
        _rdm_ctx(db, s), s.rdm_pid, _rdm_me(s), types.SimpleNamespace(n=1))),
    ("match_hold._hold_row", lambda db, s, mp: match_hold._hold_row(db, uuid.uuid4())),
    ("match_hold._hold_row lock", lambda db, s, mp: match_hold._hold_row(
        db, uuid.uuid4(), lock=True)),
    # a1 walk spans
    ("main._lease_admission_gate empty",
     lambda db, s, mp: main._lease_admission_gate(db, [], "ranked")),
    ("main._lease_admission_gate",
     lambda db, s, mp: main._lease_admission_gate(db, [s.ranked[0]], "ranked")),
    ("main._lease_live_claim_strict",
     lambda db, s, mp: main._lease_live_claim_strict(db, s.lob.pids[1])),
    ("main._group_region", lambda db, s, mp: main._group_region(
        db, [{"player_id": s.lob.pids[0]}], "eu", "rf8ro")),
    ("main.queue_poll", lambda db, s, mp: main.queue_poll(
        s.ranked[1], cf_asm.FakeRequest(), db)),
    ("main.team_queue_poll", lambda db, s, mp: main.team_queue_poll(
        s.team_search[1], cf_asm.FakeRequest(), db, rdm=0)),
    ("main.ovt_queue_poll", lambda db, s, mp: main.ovt_queue_poll(
        s.ovt_search[1], cf_asm.FakeRequest(), db, rdm=0)),
    ("main._ffa_queue_poll_inner", lambda db, s, mp: main._ffa_queue_poll_inner(
        s.lob.sids[2], cf_asm.FakeRequest(), db)),
    ("main._reconcile_team_series_bets", lambda db, s, mp: main._reconcile_team_series_bets(
        db, s.team.sid, "rf8ro")),
    ("main._team_lock_family_pick", lambda db, s, mp: main._team_lock_family_pick(
        db, [p for p, _ in s.team.seats])),
    ("main._team_resolve_live_family", lambda db, s, mp: main._team_resolve_live_family(
        db, [p for p, _ in s.team.seats], s.team.seats[0][0], s.team.seats[0][1], "auto")),
    ("main._team_quartet_lock", lambda db, s, mp: main._team_quartet_lock(
        db, [p for p, _ in s.team.seats])),
    ("main._rules_members", lambda db, s, mp: main._rules_members(
        db, [s.ranked[0]], "ranked_queue")),
    ("main._player_body_color", lambda db, s, mp: main._player_body_color(
        db, s.lob.pids[0])),
    ("main._service_player_uuids", lambda db, s, mp: main._service_player_uuids(db)),
    ("match_hold._hold_latch", lambda db, s, mp: match_hold._hold_latch(
        db, "team", s.team.sid, "rf8ro_room")),
    ("match_report_window.series_holds",
     lambda db, s, mp: match_report_window.series_holds(db, s.team.sid)),
    ("tournaments._region_candidate_volumes",
     lambda db, s, mp: tournaments._region_candidate_volumes(db)),
    ("main._lock_queue_rows_ordered ranked_queue", lambda db, s, mp:
     main._lock_queue_rows_ordered(db, "ranked_queue", [s.ranked[0]])),
    ("main._lock_queue_rows_ordered team_queue", lambda db, s, mp:
     main._lock_queue_rows_ordered(db, "team_queue", [s.team_search[0]])),
    ("main._lock_queue_rows_ordered ovt_queue", lambda db, s, mp:
     main._lock_queue_rows_ordered(db, "ovt_queue", [s.ovt_search[0]])),
    ("main._lock_queue_rows_ordered ffa_queue", lambda db, s, mp:
     main._lock_queue_rows_ordered(db, "ffa_queue", [s.lob.pids[0]])),
    ("main._lock_snapshot_rows", lambda db, s, mp: main._lock_snapshot_rows(
        db, "ffa_queue", parents=[("ffa_lobbies", s.lob.lid)], player_ids=[])),
])


def _prepare(mp):
    """Process state the drivers' handlers read, reset (the handlers' own
    session check is cf_asm's no-op, as in every live suite)."""
    mp.setattr(main, "_service_player_uuid_cache", None)

    async def _session_ok(*_a, **_k):
        return True

    mp.setattr(main, "_strict_steam_session_ok", _session_ok)


async def _run_all(admin_dsn, clone, mp, only=None):
    out = {"logs": {}, "errors": {}, "checked": [], "identity_control": None,
           "grant": None, "census": None, "harness_sites": []}
    clone_dsn = ro_role.dsn_for(admin_dsn, clone)
    async with cf_pg.case("rf8ro", dsn=clone_dsn) as (c, sm):
        env = cf_asm.Env(c, sm, mp)
        try:
            s = await seed(env)
            out["grant"] = await ro_role.grant(admin_dsn, clone)
            out["census"] = await ro_role.privilege_census(admin_dsn, clone)
            _prepare(mp)
            role_dsn = ro_role.dsn_for(admin_dsn, clone, user=ro_role.ROLE)
            for name, drive in DRIVERS.items():
                if only is not None and name not in only:
                    continue
                engine = ro_covered.role_engine(role_dsn, c.schema, ro_role.ROLE,
                                                out["checked"])
                rsm = ro_covered.role_sessionmaker(engine)
                try:
                    async with rsm() as db:
                        try:
                            await drive(db, s, mp)
                        except BaseException as e:   # noqa: BLE001 -- recorded
                            out["errors"][name] = "%s: %s" % (type(e).__name__,
                                                              str(e).splitlines()[0][:200])
                        finally:
                            out["logs"][name] = list(db.info.get("log", []))
                            await db.rollback()
                finally:
                    await engine.dispose()
            # Control: the identity assertion on a covered path, the
            # connection opened as the admin role.
            engine = ro_covered.role_engine(clone_dsn, c.schema, ro_role.ROLE, [])
            try:
                async with ro_covered.role_sessionmaker(engine)() as db:
                    try:
                        await match_hold._ctx_now(db)
                        out["identity_control"] = "passed"
                    except ro_covered.IdentityError as e:
                        out["identity_control"] = "refused: " + str(e)
            finally:
                await engine.dispose()
        finally:
            env.close()
    return out


@pytest.fixture(scope="module")
def runs():
    if not ADMIN_DSN:
        pytest.fail("CF_TEST_PG_DSN is unset: name an admin DSN (a superuser, or a "
                    "LOGIN CREATEDB role) on the local cluster; this module never skips")
    missing = run(ro_role.read_cluster(ADMIN_DSN))
    if missing:
        pytest.fail("the cluster is not provisioned for the read-only bound: "
                    + "; ".join(missing))
    clone = "rf8_ro_cov_" + datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%d%H%M%S") + "_" + os.urandom(2).hex()
    run(ro_role.clone(ADMIN_DSN, clone))
    try:
        with pytest.MonkeyPatch.context() as mp:
            yield run(_run_all(ADMIN_DSN, clone, mp))
    finally:
        run(ro_role.drop_clone(ADMIN_DSN, clone))


def measured(runs, entry):
    """'ok' when the position ran and every run of it succeeded; the
    position's SQLSTATE when it ran and was refused; ('not reached', site,
    sqlstate) naming the first refused statement of the drivers that hold
    the position's span; ('not reached', None, error) when no refusal
    explains it."""
    outs = []
    for name, log in runs["logs"].items():
        outs += ro_covered.outcome_at(log, entry)
    if outs:
        bad = sorted({o for o in outs if o != "ok"})
        return "ok" if not bad else bad[0]
    _walk, f, _line, _end, span = entry
    unexplained = None
    for name in DRIVERS:
        if name.split()[0].split(".")[-1] != span:
            continue
        log = runs["logs"].get(name, [])
        refused = [(lf, ll, o) for (lf, ll, o) in log if o != "ok"]
        if refused:
            lf, ll, o = refused[0]
            return ("not reached", "%s:%s" % (lf, ll), o)
        if unexplained is None:
            unexplained = ("not reached", None, runs["errors"].get(name, "no error"))
    return unexplained or ("not reached", None, "no driver")


def test_every_role_connection_was_the_role(runs):
    assert runs["checked"] and set(runs["checked"]) == {(ro_role.ROLE, ro_role.ROLE)}
    # Every statement on a role session came from production code: a frame
    # under backend/api issued it (no harness statement ran as the role).
    sites = [(n, e) for n, log in runs["logs"].items() for e in log if e[0] is None]
    assert sites == [], sites


def test_identity_assertion_refuses_the_admin_role(runs):
    """Control (R7-A1 M2): a covered path whose connection is opened as the
    admin role fails the identity assertion before any statement."""
    got = runs["identity_control"] or ""
    assert got.startswith("refused: a covered connection runs as") and \
        got.endswith("not as scr_seat_ro"), got


def test_clone_grant_census_is_empty(runs):
    assert runs["census"] == [], runs["census"]


@pytest.mark.parametrize("entry", list(ro_covered.COVERED),
                         ids=["%s:%s %s" % (e[1], e[2], e[4]) for e in ro_covered.COVERED])
def test_covered_position_under_the_role(runs, entry):
    want = ro_covered.OUTCOME[entry]
    got = measured(runs, entry)
    assert got == want, (entry, got, want, runs["errors"])
    if want != "ok":
        # A covered position the role did not reach is a writer path: the
        # statement that stopped it was a refusal by the role.
        assert got[1] is not None and got[2] in ("25006", "42501"), got


@pytest.mark.parametrize("entry", list(ro_covered.WRITERS),
                         ids=["%s:%s %s" % (e[1], e[2], e[4]) for e in ro_covered.WRITERS])
def test_writer_position_under_the_role(runs, entry):
    assert measured(runs, entry) == ro_covered.WRITER_OUTCOME[entry]


def test_outcome_tables_are_whole():
    assert set(ro_covered.OUTCOME) == set(ro_covered.COVERED)
    assert set(ro_covered.WRITER_OUTCOME) == set(ro_covered.WRITERS)
    # The read-only claim holds only the green positions; a position whose
    # outcome is a refusal or a lock is not in COVERED's 'ok' set.
    assert all(v == "ok" or (isinstance(v, tuple) and v[0] == "not reached")
               for v in ro_covered.OUTCOME.values())
