"""The read-only bound applied to the REAL covered set (ruling
REHEARSAL-FOUR-R7-A1 M1, R7-A2).

1. Enumeration. Both walks run (the whole a1 file, the gate file's source
   walks) under the ro_spy plugin; every execute position the walks ask the
   frozen lookup about inside backend/api is collected (round 8, M1: the S
   analysis is retired), and the set must equal the frozen lists
   ro_covered.COVERED, ro_covered.WRITERS and ro_covered.VISITED_WRITES
   (ruling R-C) together, exactly, both ways: a visited position in no
   table is a finding. No position may be
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

3. Grant run (ruling R-B). Each driver holding a COVERED position the
   role did not reach runs again on a READ WRITE session as the role, with
   the table privileges of the statement that refused first on its path
   (ro_covered.REFUSER_GRANTS) granted for that run only; the grant layer
   (42501) refuses every other write. Around the position's own statement
   the transaction's write counters are read (ro_covered.CountingSession):
   the position is a read only when it succeeds with a zero delta,
   OUTCOME ('ok-under-grant', grants, 0, the role's own outcome). Every
   other unreached position keeps its role outcome and its grant run is
   pinned in GRANT_OUTCOME (the measured reason it stays a write). A
   control plants a write under a grant: refused with 42501 when its table
   is not granted, counted (a nonzero delta, not green) when it is.

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

import asyncpg
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
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

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
    writes = set(ro_covered.VISITED_WRITES)
    assert len(writes) == len(ro_covered.VISITED_WRITES), "a duplicate visited write"
    assert not (writes & (frozen_read | frozen_lock))
    # ruling R-C: the visited writes in neither table are frozen too
    frozen = frozen_read | frozen_lock | writes
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
    # The ffa gather formation (W30b, ruling R-B widened along the path):
    # three searching rows with no lobby; _ffa_gather re-writes them fresh
    # before each call (the formation reads rows polled in the last 10 s).
    s.ffa_gather = [await _player(conn, "ffa_gather_%d" % i) for i in range(3)]
    s.ffa_lead = min((st for _p, st in s.ffa_gather), key=main._ffa_sort_key)
    s.ffa_other = [st for _p, st in s.ffa_gather if st != s.ffa_lead][0]
    s.admin = conn
    await _ffa_gather_rows(s)
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


async def _ffa_gather_rows(s):
    """The three gather rows, fresh and searching (admin connection)."""
    pids = [p for p, _st in s.ffa_gather]
    await s.admin.execute("DELETE FROM ffa_queue WHERE player_id = ANY($1::uuid[])", pids)
    for pid, steam in s.ffa_gather:
        await s.admin.execute(
            "INSERT INTO ffa_queue (player_id, steam_id, display_name, status, joined_at,"
            "  last_polled) VALUES ($1, $2, 'rf8ro g', 'searching', clock_timestamp(),"
            "  clock_timestamp())", pid, steam)


async def _ffa_gather(db, s, conflict_with):
    """_ffa_queue_poll_inner for the gather's leader, through its formation
    loop: the gather decision answers go and the lease check answers a
    conflict naming `conflict_with` (inputs only; restored after)."""
    async def _conflict(_db, _members, **_k):
        return (conflict_with, "rf8ro")

    saved = (main._ffa_gather_decide, main._formation_lease_conflict,
             main._ffa_gather_started_mono, main._ffa_gather_pool_seen_mono)
    await _ffa_gather_rows(s)
    main._ffa_gather_decide = lambda *_a, **_k: (True, 0)
    main._formation_lease_conflict = _conflict
    try:
        return await main._ffa_queue_poll_inner(s.ffa_lead, cf_asm.FakeRequest(), db)
    finally:
        (main._ffa_gather_decide, main._formation_lease_conflict,
         main._ffa_gather_started_mono, main._ffa_gather_pool_seen_mono) = saved


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
    # after the lobby driver, so the role outcome of an unreached ffa
    # position stays the lobby path's first refusal
    ("main._ffa_queue_poll_inner gather, conflict on another seat",
     lambda db, s, mp: _ffa_gather(db, s, s.ffa_other)),
    ("main._ffa_queue_poll_inner gather, conflict on the caller",
     lambda db, s, mp: _ffa_gather(db, s, s.ffa_lead)),
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
    out = {"logs": {}, "locks": {}, "errors": {}, "checked": [], "identity_control": None,
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
                        # E2: every covered and writer position is followed
                        # by a lock read inside its transaction.
                        db.info["lock_targets"] = LOCK_TARGETS
                        try:
                            await drive(db, s, mp)
                        except BaseException as e:   # noqa: BLE001 -- recorded
                            out["errors"][name] = "%s: %s" % (type(e).__name__,
                                                              str(e).splitlines()[0][:200])
                        finally:
                            out["logs"][name] = list(db.info.get("log", []))
                            out["locks"][name] = list(db.info.get("locks", []))
                            await db.rollback()
                finally:
                    await engine.dispose()
            out["grant_runs"] = await _grant_runs(admin_dsn, clone, c.schema, s, mp)
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


# ------------------------------------------------------------- 3. grant run

UNREACHED = [e for e in ro_covered.COVERED
             if isinstance(ro_covered.role_outcome(e), tuple)
             and ro_covered.role_outcome(e)[0] == "not reached"]

# E2: the spans after whose statements the role run reads the locks.
LOCK_TARGETS = frozenset(e[1:4] for e in ro_covered.COVERED + ro_covered.WRITERS)


class _Planting:
    """A control's session: at a production site named in
    self.info['plant'] ({(file, line): sql}) the statement is replaced by the
    planted SQL text (no parameters), the way the round-8 report changed
    main.py:16871 and :16828; everything after (record, lock read, delta) is
    the measuring session's own."""

    async def execute(self, statement, params=None, **kw):
        sql = self.info.get("plant", {}).get(ro_covered._site())
        if sql is not None:
            statement, params = text(sql), None
        return await super().execute(statement, params, **kw)


class PlantedRecording(_Planting, ro_covered.RecordingSession):
    pass


class PlantedCounting(_Planting, ro_covered.CountingSession):
    pass


def _entry(f, line):
    return next(e for e in ro_covered.COVERED if e[1] == f and e[2] == line)


E_16828 = _entry("main.py", 16828)
E_16871 = _entry("main.py", 16871)
FOR_UPDATE = "SELECT clock_timestamp() FROM players LIMIT 1 FOR UPDATE"
ADVISORY = ("SELECT clock_timestamp() FROM (SELECT pg_catalog.pg_advisory_xact_lock(808))"
            " AS planted")
# Each E2 control: (name, driver, entry, planted SQL or None, grants or None
# for the read-only role session). The first two are the round-8 report's
# own examples; the third plants FOR UPDATE at a position whose unplanted
# run under the same grant is lock-clean (the fourth, its negative control).
LOCK_CONTROLS = (
    ("for_update_at_16871_under_grant", "main._lease_admission_gate", E_16871,
     FOR_UPDATE, ("UPDATE players",)),
    ("advisory_at_16828_under_role", "main._lease_admission_gate empty", E_16828,
     ADVISORY, None),
    ("for_update_at_16828_under_grant", "main._lease_admission_gate empty", E_16828,
     FOR_UPDATE, ("UPDATE players",)),
    ("unplanted_16828_under_grant", "main._lease_admission_gate empty", E_16828,
     None, ("UPDATE players",)),
)


async def _grants(admin, schema, grants, verb):
    for g in sorted(grants):
        priv, table = g.split()
        await admin.execute("%s %s ON %s.%s %s %s" % (
            verb, priv, ro_role._q(schema), ro_role._q(table),
            "TO" if verb == "GRANT" else "FROM", ro_role._q(ro_role.ROLE)))


async def _counted(role_dsn, schema, checked, drive, s, mp, targets, plant=None,
                   read_write=True):
    """One driver on a role session: READ WRITE with the write counters and
    the lock read at `targets` (the grant run), or, with read_write False,
    the read-only role session with the lock read alone; `plant` replaces
    statements at named sites (the E2 controls)."""
    engine = ro_covered.role_engine(role_dsn, schema, ro_role.ROLE, checked,
                                    read_write=read_write)
    cls = ((PlantedCounting if read_write else PlantedRecording) if plant
           else (ro_covered.CountingSession if read_write else ro_covered.RecordingSession))
    try:
        async with ro_covered.role_sessionmaker(engine, cls)() as db:
            db.info["targets"] = targets
            db.info["lock_targets"] = targets
            if plant:
                db.info["plant"] = plant
            try:
                await drive(db, s, mp)
            except BaseException:   # noqa: BLE001 -- the log holds the outcome
                pass
            finally:
                log = list(db.info.get("log", []))
                deltas = list(db.info.get("deltas", []))
                locks = list(db.info.get("locks", []))
                await db.rollback()
    finally:
        await engine.dispose()
    return log, deltas, locks


MERGE_ORDER = {"refused under grant": 0, "lock under grant": 1}


def _merge(results):
    """One position held by several drivers (ruling REHEARSAL-R8-A1 E3): a
    reached execution is green only when EVERY driver that reached it
    succeeded with zero measured effects. A refusal at it in any driver is
    the merged outcome (unproven, never green), then a lock found by any
    driver's lock read, then any other outcome this merge does not name;
    only when none occurred does a green run stand, with the largest delta
    of the runs that reached it; a position no driver reached keeps the
    first run's reason."""
    ok = [r for r in results if r[0] == "ok-under-grant"]
    bad = [r for r in results if r[0] not in ("ok-under-grant", "not reached under grant")]
    if bad:
        return min(bad, key=lambda r: MERGE_ORDER.get(r[0], len(MERGE_ORDER)))
    if ok:
        return ("ok-under-grant", ok[0][1], max(r[2] for r in ok))
    got = [r for r in results if r[0] == "not reached under grant"]
    return got[0] if got else None


async def _grant_runs(admin_dsn, clone, schema, s, mp):
    out = {"outcomes": {}, "control": {}, "checked": [], "plan": {}}
    role_dsn = ro_role.dsn_for(admin_dsn, clone, user=ro_role.ROLE)
    plan = collections.OrderedDict()
    for e in UNREACHED:
        grants = ro_covered.REFUSER_GRANTS[ro_covered.role_outcome(e)[1]]
        for name in DRIVERS:
            if name.split()[0].split(".")[-1] == e[4]:
                g, es = plan.setdefault(name, (set(), []))
                g.update(grants)
                es.append(e)
    results = collections.defaultdict(list)
    admin = await asyncpg.connect(ro_role.dsn_for(admin_dsn, clone))
    try:
        for name, (grants, entries) in plan.items():
            out["plan"][name] = sorted(grants)
            await _grants(admin, schema, grants, "GRANT")
            try:
                log, deltas, locks = await _counted(role_dsn, schema, out["checked"],
                                                    DRIVERS[name], s, mp,
                                                    {e[1:4] for e in entries})
            finally:
                await _grants(admin, schema, grants, "REVOKE")
            for e in entries:
                results[e].append(ro_covered.under_grant(log, deltas, e, sorted(grants),
                                                         locks))
        out["results"] = {e: list(r) for e, r in results.items()}
        out["outcomes"] = {e: _merge(r) for e, r in results.items()}
        # E2 controls: a planted locking statement at a read position.
        out["lock_controls"] = {}
        for cname, driver, entry, sql, grants in LOCK_CONTROLS:
            plant = {entry[1:3]: sql} if sql else None
            if grants:
                await _grants(admin, schema, set(grants), "GRANT")
            try:
                log, deltas, locks = await _counted(
                    role_dsn, schema, out["checked"], DRIVERS[driver], s, mp,
                    {entry[1:4]}, plant=plant, read_write=bool(grants))
            finally:
                if grants:
                    await _grants(admin, schema, set(grants), "REVOKE")
            if grants:
                got = ro_covered.under_grant(log, deltas, entry, list(grants), locks)
            else:
                outs = ro_covered.outcome_at(log, entry)
                got = (ro_covered.ran_outcome(outs, ro_covered.locks_at(locks, entry))
                       if outs and all(o == "ok" for o in outs) else ("ran", outs))
            out["lock_controls"][cname] = {"outcome": got, "log": log}
        save = os.environ.get("RO8_GRANT_SAVE")
        if save:
            with open(save, "w", encoding="utf-8") as fh:
                json.dump([[list(e), list(o) if o else o]
                           for e, o in out["outcomes"].items()], fh)
        # Control: a write planted under a grant is counted (its table
        # granted) or refused by the grant layer (its table not granted).
        ctl = out["control"]
        await _grants(admin, schema, {"UPDATE players"}, "GRANT")
        try:
            engine = ro_covered.role_engine(role_dsn, schema, ro_role.ROLE,
                                            out["checked"], read_write=True)
            try:
                async with ro_covered.role_sessionmaker(
                        engine, ro_covered.CountingSession)() as db:
                    before = await db.writes()
                    await AsyncSession.execute(db, text(
                        "UPDATE players SET display_name = display_name"
                        " WHERE id = CAST(:p AS uuid)"), {"p": str(s.lob.pids[0])})
                    ctl["granted_delta"] = await db.writes() - before
                    try:
                        await AsyncSession.execute(db, text(
                            "DELETE FROM ranked_queue WHERE false"))
                        ctl["ungranted"] = "ran"
                    except DBAPIError as e:
                        ctl["ungranted"] = ro_covered._sqlstate(e)
                    await db.rollback()
            finally:
                await engine.dispose()
        finally:
            await _grants(admin, schema, {"UPDATE players"}, "REVOKE")
    finally:
        await admin.close()
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
            got = run(_run_all(ADMIN_DSN, clone, mp))
            save = os.environ.get("RO9_MEASURE_SAVE")
            if save:
                # The measured tables (role run, grant run, controls), for
                # the freeze and the notes; never read back by a test.
                with open(save, "w", encoding="utf-8") as fh:
                    json.dump({
                        "role": [[list(e), measured(got, e)]
                                 for e in ro_covered.COVERED + ro_covered.WRITERS],
                        "grant": [[list(e), o] for e, o in got["grant_runs"]["outcomes"].items()],
                        "grant_results": [[list(e), r] for e, r in
                                          got["grant_runs"]["results"].items()],
                        "lock_controls": {k: v["outcome"] for k, v in
                                          got["grant_runs"]["lock_controls"].items()},
                    }, fh, indent=1, default=list)
            yield got
    finally:
        run(ro_role.drop_clone(ADMIN_DSN, clone))


def measured(runs, entry):
    """'ok' when the position ran, every run of it succeeded and every run's
    lock read found only the expected rows (('lock', rows) when one found
    more; ruling REHEARSAL-R8-A1 E2); the
    position's SQLSTATE when it ran and was refused; ('not reached', site,
    sqlstate) naming the first refused statement of the drivers that hold
    the position's span; ('not reached', None, error) when no refusal
    explains it."""
    outs, reads = [], []
    for name, log in runs["logs"].items():
        outs += ro_covered.outcome_at(log, entry)
        reads += ro_covered.locks_at(runs["locks"].get(name, []), entry)
    if outs:
        bad = sorted({o for o in outs if o != "ok"})
        # E2: every run succeeded; its lock reads decide 'ok' or ('lock', rows)
        return ro_covered.ran_outcome(outs, reads) if not bad else bad[0]
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
    want = ro_covered.role_outcome(entry)
    got = measured(runs, entry)
    assert got == want, (entry, got, want, runs["errors"])
    if want != "ok" and want[0] == "lock":
        # E2: it ran, and its lock read found rows beyond the expected ones.
        assert got[1], got
    elif want != "ok":
        # A covered position the role did not reach is a writer path: the
        # statement that stopped it was a refusal by the role.
        assert got[1] is not None and got[2] in ("25006", "42501"), got


@pytest.mark.parametrize("entry", list(ro_covered.WRITERS),
                         ids=["%s:%s %s" % (e[1], e[2], e[4]) for e in ro_covered.WRITERS])
def test_writer_position_under_the_role(runs, entry):
    assert measured(runs, entry) == ro_covered.WRITER_OUTCOME[entry]


@pytest.mark.parametrize("entry", UNREACHED,
                         ids=["%s:%s %s" % (e[1], e[2], e[4]) for e in UNREACHED])
def test_unreached_position_under_grant(runs, entry):
    """Ruling R-B: the grant run's measured outcome at every position the
    role did not reach equals OUTCOME's (a read: 'ok-under-grant' with a
    zero delta) or GRANT_OUTCOME's (the measured reason it stays a write)."""
    o = ro_covered.OUTCOME[entry]
    want = o[:3] if o[0] == "ok-under-grant" else ro_covered.GRANT_OUTCOME.get(entry)
    got = runs["grant_runs"]["outcomes"].get(entry)
    assert got == want, (entry, got, want, runs["grant_runs"]["plan"])


def test_grant_run_planted_write_is_refused_or_counted(runs):
    ctl = runs["grant_runs"]["control"]
    assert ctl.get("ungranted") == "42501", ctl
    assert ctl.get("granted_delta", 0) > 0, ctl
    planted = ("ok-under-grant", ("UPDATE players",), ctl["granted_delta"], None)
    assert not ro_covered.green(planted), planted
    assert ro_covered.green(("ok-under-grant", ("UPDATE players",), 0, None))


def test_outcome_tables_are_whole():
    assert set(ro_covered.GRANT_OUTCOME) == {
        e for e in UNREACHED if ro_covered.OUTCOME[e][0] != "ok-under-grant"}
    assert set(ro_covered.OUTCOME) == set(ro_covered.COVERED)
    assert set(ro_covered.WRITER_OUTCOME) == set(ro_covered.WRITERS)
    # The read-only claim holds only the green positions; a position whose
    # outcome is a refusal or a lock is not in COVERED's 'ok' set.
    assert all(v == "ok" or (isinstance(v, tuple) and v[0] in ("not reached", "lock",
                                                               "ok-under-grant"))
               for v in ro_covered.OUTCOME.values())
    # E2: a lock outcome is never green, so never 'read' in the lookup.
    table = ro_covered.lookup_table()
    for e, v in ro_covered.OUTCOME.items():
        if isinstance(v, tuple) and v[0] == "lock":
            assert not ro_covered.green(v) and table.get(e[1:4]) != "read", e


# ------------------------------------------------- E2: locks refuse a read

@pytest.mark.parametrize("name", [c[0] for c in LOCK_CONTROLS])
def test_lock_control(runs, name):
    """Ruling REHEARSAL-R8-A1 E2: a locking statement planted at a read
    position is refused as a read by the lock read (its outcome names the
    lock and is not green); the unplanted run under the same grant is green
    (the negative control)."""
    got = runs["grant_runs"]["lock_controls"][name]["outcome"]
    _n, _d, _e, sql, grants = next(c for c in LOCK_CONTROLS if c[0] == name)
    if sql is None:
        assert got == ("ok-under-grant", tuple(grants), 0), got
        return
    if grants:
        assert got[0] == "lock under grant" and got[1] == tuple(grants), got
        rows = got[2]
    else:
        assert got[0] == "lock", got
        rows = got[1]
    assert not ro_covered.green(got), got
    want = ({"relation RowShareLock players", "transactionid ExclusiveLock"}
            if "FOR UPDATE" in sql else {"advisory ExclusiveLock"})
    assert want <= set(rows), (got, want)


# ---------------------------------------------- E3: a refusal is never merged away

def test_merge_keeps_a_refusal_unproven():
    """Ruling REHEARSAL-R8-A1 E3: one driver green with a zero delta, another
    refused 42501 at the same position: the merged outcome is the refusal
    (never green), in either order; likewise a lock found by one driver."""
    g = ("UPDATE players",)
    ok = ("ok-under-grant", g, 0)
    refused = ("refused under grant", g, "42501")
    lock = ("lock under grant", g, ("advisory ExclusiveLock",))
    unreached = ("not reached under grant", g, None)
    for results in ([ok, refused], [refused, ok], [unreached, ok, refused]):
        got = _merge(results)
        assert got == refused and not ro_covered.green(got), (results, got)
    for results in ([ok, lock], [lock, ok]):
        assert _merge(results) == lock, results
    assert _merge([ok, unreached]) == ok
    assert _merge([("ok-under-grant", g, 0), ("ok-under-grant", g, 2)]) == (
        "ok-under-grant", g, 2)


def test_merge_of_the_measured_runs(runs):
    """E3 on the measured runs: every position whose merged grant outcome is
    green was reached green by every driver that reached it."""
    for e, results in runs["grant_runs"]["results"].items():
        merged = runs["grant_runs"]["outcomes"][e]
        if merged and merged[0] == "ok-under-grant":
            assert all(r[0] in ("ok-under-grant", "not reached under grant")
                       for r in results), (e, results)
            assert merged[2] == 0, (e, merged)


# ------------------------------------------ G1: complete opener forms

CENSUS_REL = "tests/cf_pg.py"
CENSUS_CALL = "admin = await _asyncpg.connect(DSN)"
# Each row: (name, change of tests/cf_pg.py's text: ('replace', old, new) on
# the first occurrence, or ('append', program), the complete-layer forms the
# change must add, refused). The first two are the round-8 report's forms;
# with them the coarse layer is unchanged (the finding), and the complete
# layer refuses each.
G1_PLANTED = (
    ("keyword_unpacking",
     ("replace", CENSUS_CALL, 'admin = await _asyncpg.connect(DSN, **{"user": "scr_gate"})'),
     {("refuse", "_asyncpg.connect(DSN, **{'user': 'scr_gate'})")}, True),
    ("constructed_getattr",
     ("append", "\nasync def _planted(driver):\n"
                "    return await getattr(driver, 'con' + 'nect')(DSN)\n"),
     {("dynamic", "getattr(driver, 'con' + 'nect')")}, True),
    ("positional_dsn",
     ("replace", CENSUS_CALL, "admin = await _asyncpg.connect(ADMIN_DSN)"),
     {("call", "_asyncpg.connect(ADMIN_DSN)")}, True),
    ("starred_args",
     ("replace", CENSUS_CALL, "admin = await _asyncpg.connect(*ARGS)"),
     {("refuse", "_asyncpg.connect(*ARGS)")}, True),
    ("unbound_receiver",
     ("append", "\nasync def _planted(make):\n    return await make().connect(DSN)\n"),
     {("refuse", "make().connect(DSN)")}, False),
    ("alias_capture",
     ("append", "\n_planted = _asyncpg.connect\n"),
     {("ref", "_planted = _asyncpg.connect")}, False),
    ("module_table",
     ("append", "\nasync def _planted():\n"
                "    return await sys.modules['asyncpg'].connect(DSN)\n"),
     {("dynamic", "sys.modules"), ("refuse", "sys.modules['asyncpg'].connect(DSN)")}, False),
    ("vars_lookup",
     ("append", "\nasync def _planted():\n"
                "    return await vars(_asyncpg)['con' + 'nect'](DSN)\n"),
     {("dynamic", "vars(_asyncpg)")}, True),
)


def _census_src():
    with open(os.path.join(HERE, "..", CENSUS_REL), encoding="utf-8") as fh:
        return fh.read()


@pytest.mark.parametrize("name", [p[0] for p in G1_PLANTED])
def test_census_refuses_incomplete_opener_form(name):
    """Ruling REHEARSAL-R8-A1 G1: each planted form is refused by the
    complete layer: the census diff of the planted text against the frozen
    layer adds exactly the row's forms; where the row says so, the coarse
    layer is unchanged (it alone would have accepted the form)."""
    import ro_census
    import ro_census_frozen
    _n, change, want, coarse_same = next(p for p in G1_PLANTED if p[0] == name)
    src = _census_src()
    if change[0] == "replace":
        assert src.count(change[1]) >= 1, change[1]
        planted = src.replace(change[1], change[2], 1)
    else:
        planted = src + change[1]
    key = CENSUS_REL + ro_census.COMPLETE
    frozen = {k: ro_census_frozen.FROZEN[k] for k in (CENSUS_REL, key)}
    refused = ro_census.diff(ro_census.file_forms(CENSUS_REL, planted), frozen)
    added = {r[2:] for r in refused if r[0] == key and r[1] == "+"}
    assert added == want, ("the planted form is not refused as the row requires",
                           refused, want)
    coarse = [r for r in refused if r[0] == CENSUS_REL]
    if coarse_same:
        assert coarse == [], coarse
    # Unplanted, the file is the freeze (both layers): the refusal is the plant's.
    assert ro_census.diff(ro_census.file_forms(CENSUS_REL, src), frozen) == []


def test_census_complete_layer_frozen_whole():
    """G1: the complete layer is frozen for every census file, holds no
    refuse form, and each declared FORWARDING exception is frozen exactly
    once as a call; the count is the coarse 363 plus the complete layer."""
    import ro_census
    import ro_census_frozen as fz
    import test_r7_ro_role_pg as r7
    coarse = {k for k in fz.FROZEN if not k.endswith(ro_census.COMPLETE)}
    complete = {k for k in fz.FROZEN if k.endswith(ro_census.COMPLETE)}
    # every census file has a complete layer (empty or not); the coarse
    # freeze lists only the files with a coarse form
    assert complete == {k + ro_census.COMPLETE for k in r7.CENSUS_FILES}
    assert coarse <= set(r7.CENSUS_FILES)
    assert sum(len(fz.FROZEN[k]) for k in coarse) == fz.COARSE_COUNT == 363
    assert sum(len(fz.FROZEN[k]) for k in complete) == fz.COMPLETE_COUNT
    assert fz.FROZEN_COUNT == fz.COARSE_COUNT + fz.COMPLETE_COUNT
    assert not [f for k in complete for f in fz.FROZEN[k] if f[0] == "refuse"]
    for (rel, call) in ro_census.FORWARDING:
        assert list(map(tuple, fz.FROZEN[rel + ro_census.COMPLETE])).count(
            ("call", call)) == 1, (rel, call)
