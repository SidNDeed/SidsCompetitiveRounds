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
   proof by the role, or, for the two statements the role cannot refuse,
   the effect the harness measures: main.py:16869, a transaction-local
   set_config of lock_timeout, ('continuity', the changed setting) by the
   round-10 residue reading, and main.py:51898, pg_advisory_xact_lock,
   ('lock', advisory) by the lock read.

4. Transaction continuity (ruling REHEARSAL-R9-A1 (B)): every measured
   position runs inside ro_covered's continuity bracket (a position token
   and the virtual transaction id read at both ends, the session residue
   compared); a position that is not the same transaction is an effect.
   The controls plant every transaction-ending form, a changed token, a
   restored token after a chain, residue, and a later position after a
   chain (test_continuity_control).

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
import ro_census  # noqa: E402
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


R11_PLANTED_FN = "rf11res_planted"


async def _proc_census(clone_dsn, schema):
    """Ruling FOUR-R11-A6 (4): PROC_CENSUS_SQL on the clone as the admin
    role, then again inside a transaction that plants a function carrying
    set_config(..., false) in the case schema and is rolled back, then once
    more after the rollback."""
    conn = await asyncpg.connect(clone_dsn)
    try:
        rows = [tuple(r) for r in await conn.fetch(ro_covered.PROC_CENSUS_SQL)]
        tr = conn.transaction()
        await tr.start()
        try:
            await conn.execute(
                "CREATE FUNCTION %s.%s() RETURNS text LANGUAGE sql AS $f$"
                " SELECT pg_catalog.set_config('rf11res.planted', '1', false) $f$"
                % (ro_role._q(schema), R11_PLANTED_FN))
            planted = [tuple(r) for r in await conn.fetch(ro_covered.PROC_CENSUS_SQL)]
        finally:
            await tr.rollback()
        after = [tuple(r) for r in await conn.fetch(ro_covered.PROC_CENSUS_SQL)]
    finally:
        await conn.close()
    return {"rows": rows, "planted": planted, "after": after, "schema": schema}


async def _role_run(role_dsn, schema, s, mp, only, out):
    for name, drive in DRIVERS.items():
        if only is not None and name not in only:
            continue
        engine = ro_covered.role_engine(role_dsn, schema, ro_role.ROLE, out["checked"])
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
                    # REHEARSAL-R9-A1 (B): every position's continuity
                    out["conts"][name] = list(db.info.get("continuity", []))
                    out["pids"][name] = sorted(db.info.get("pids", ()))
                    # FIX-R11-RES: every position's RESET ALL proof
                    out["gone"][name] = list(db.info.get("gone", []))
                    await db.rollback()
        finally:
            await engine.dispose()


async def _run_all(admin_dsn, clone, mp, rec, only=None):
    out = {"logs": {}, "locks": {}, "conts": {}, "pids": {}, "gone": {}, "errors": {},
           "checked": [], "window": None,
           "identity_control": None, "grant": None, "census": None, "harness_sites": []}
    clone_dsn = ro_role.dsn_for(admin_dsn, clone)
    async with cf_pg.case("rf8ro", dsn=clone_dsn) as (c, sm):
        env = cf_asm.Env(c, sm, mp)
        try:
            s = await seed(env)
            # ruling FOUR-R11-A6 (4): the function census of the measured
            # database, and its control (a planted function, rolled back)
            out["proc_census"] = await _proc_census(clone_dsn, c.schema)
            out["grant"] = await ro_role.grant(admin_dsn, clone)
            out["census"] = await ro_role.privilege_census(admin_dsn, clone)
            _prepare(mp)
            role_dsn = ro_role.dsn_for(admin_dsn, clone, user=ro_role.ROLE)
            # Ruling FOUR-R11-A8: the measured run (the role run and the grant
            # runs with their controls) carries the open recorder. Every open
            # of another identity precedes the freeze: the admin opens above
            # and the grant runs' admin connection here, which grants and
            # revokes over the connection it already holds.
            admin = await asyncpg.connect(clone_dsn)
            try:
                rec.freeze(role_dsn, [None, {"search_path": '"%s"' % c.schema}])
                try:
                    try:
                        await _role_run(role_dsn, c.schema, s, mp, only, out)
                        out["grant_runs"] = await _grant_runs(admin, role_dsn, c.schema, s, mp)
                    finally:
                        # every task the run left ends INSIDE the window, so
                        # an open it was making is recorded
                        pending = [t for t in asyncio.all_tasks()
                                   if t is not asyncio.current_task()]
                        out["pending_tasks"] = len(pending)
                        for t in pending:
                            t.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        out["window"] = rec.report()
                finally:
                    rec.thaw()
            finally:
                await admin.close()
            # Control: the identity assertion on a covered path, the
            # connection opened as the admin role (after the thaw: its purpose
            # is an open that is not the frozen identity).
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
    self.info['plant'] ({(file, line): plant}) the statement the position
    runs is the planted one, the way the round-8 report changed main.py:16901
    and :16858 (main.py itself is never changed: the program a position runs
    is the harness's input). A plant is SQL text (run with no parameters in
    place of the production statement), or a planted PROGRAM: an async
    callable (ex, statement, params) whose statements run at the position,
    in its place, through `ex(sql_or_clause, params=None)`, and whose result
    is the position's (round 10: COMMIT AND CHAIN, then the production
    statement itself, so the program continues as written). Everything
    around it (the continuity bracket, record, counters, lock read) is the
    measuring session's own."""

    async def run_statement(self, site, statement, params=None, **kw):
        plant = self.info.get("plant", {}).get(site)
        if plant is None:
            return await super().run_statement(site, statement, params, **kw)
        if callable(plant):
            async def ex(sql, p=None):
                return await AsyncSession.execute(
                    self, text(sql) if isinstance(sql, str) else sql, p)
            return await plant(ex, statement, params)
        return await super().run_statement(site, text(plant), None)


class PlantedRecording(_Planting, ro_covered.RecordingSession):
    pass


class PlantedCounting(_Planting, ro_covered.CountingSession):
    pass


def _entry(f, line):
    return next(e for e in ro_covered.COVERED if e[1] == f and e[2] == line)


E_16828 = _entry("main.py", 16858)
E_16871 = _entry("main.py", 16901)
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


# ---- ruling REHEARSAL-R9-A1 (B): transaction continuity controls ----------
#
# Route (main.py unchanged): the planted statement or planted program runs at
# the position through _Planting.run_statement, inside the measuring
# session's continuity bracket. A planted program `_then_own(sql)` runs `sql`
# and then the position's own production statement, so the program continues
# exactly as written (the round-9 report's case: COMMIT AND CHAIN at
# main.py:16858, the drivers then return normally).

def _then_own(sql):
    async def program(ex, statement, params):
        await ex(sql)
        return await ex(statement, params)
    program.planted = sql
    return program


async def _token_restored(ex, statement, params):
    """A program that reads the position token, ends the transaction with
    COMMIT AND CHAIN, writes the token back into the new transaction, then
    runs the production statement: the token reads back unchanged, so only
    the virtual transaction id can refuse it."""
    token = (await ex("SELECT pg_catalog.current_setting('rf10.position')")).scalar()
    await ex("COMMIT AND CHAIN")
    await ex(text("SELECT pg_catalog.set_config('rf10.position', :t, true)"), {"t": token})
    return await ex(statement, params)


async def _token_overwritten(ex, statement, params):
    """A program that changes the position token in the SAME transaction:
    only the token check can refuse it."""
    await ex("SELECT pg_catalog.set_config('rf10.position', 'planted', true)")
    return await ex(statement, params)


PREPARED_GID = "rf10_ro_" + os.urandom(4).hex()
# The round-10 report's exact text (codex-rehearsal-four-r10.out, F4).
R11_HIDDEN = "SELECT set_config('rf10.hidden','yes',false)"
R11_HIDDEN_PARTS = {"session set_config rf10.hidden", "placeholder rf10.hidden=yes"}
E_16886 = _entry("main.py", 16916)
LEASE_GRANT_TARGETS = [e for e in ro_covered.COVERED if e[4] == "_lease_admission_gate"
                       and e[2] >= 16898]

# Each control: (name, driver, entry, plant, grants or None, want). want is
# 'continuity' (the run stayed 'ok' and the bracket refused it, with
# `parts` all among the refusal's detail), or 'sqlstate' (the planted
# statement was refused by the server; never green either way). Every
# transaction-ending form of PostgreSQL 16 (COMMIT / END / ROLLBACK / ABORT,
# each with WORK or TRANSACTION, AND CHAIN or AND NO CHAIN; PREPARE
# TRANSACTION; COMMIT PREPARED and a DO block that commits, both refused
# inside a transaction block) and the residue routes.
CONTINUITY_CONTROLS = (
    # the round-9 report's case, both drivers
    ("commit_and_chain_at_16828_under_role", "main._lease_admission_gate empty", E_16828,
     _then_own("COMMIT AND CHAIN"), None, ("continuity", {"token", "virtualxid"})),
    ("commit_and_chain_at_16828_under_grant", "main._lease_admission_gate empty", E_16828,
     _then_own("COMMIT AND CHAIN"), ("UPDATE players",), ("continuity", {"token", "virtualxid"})),
    # the same case by the round-9 controls' own route: the position's
    # statement replaced by the planted text (the program then fails on the
    # result it expected; the position itself ran 'ok')
    ("commit_and_chain_replaces_16828_under_role", "main._lease_admission_gate empty",
     E_16828, "COMMIT AND CHAIN", None, ("continuity", {"token", "virtualxid"})),
    ("commit_and_chain_replaces_16828_under_grant", "main._lease_admission_gate empty",
     E_16828, "COMMIT AND CHAIN", ("UPDATE players",), ("continuity", {"token", "virtualxid"})),
    # every ending form
    ("commit_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("COMMIT"), None, ("continuity", {"token", "virtualxid"})),
    ("commit_work_and_no_chain_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("COMMIT WORK AND NO CHAIN"), None, ("continuity", {"token", "virtualxid"})),
    ("end_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("END"), None, ("continuity", {"token", "virtualxid"})),
    ("end_transaction_and_chain_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("END TRANSACTION AND CHAIN"), None, ("continuity", {"token", "virtualxid"})),
    ("rollback_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("ROLLBACK"), None, ("continuity", {"token", "virtualxid"})),
    ("rollback_and_chain_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("ROLLBACK AND CHAIN"), None, ("continuity", {"token", "virtualxid"})),
    ("abort_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("ABORT"), None, ("continuity", {"token", "virtualxid"})),
    ("abort_work_and_chain_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("ABORT WORK AND CHAIN"), None, ("continuity", {"token", "virtualxid"})),
    ("prepare_transaction_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("PREPARE TRANSACTION '%s'" % PREPARED_GID), None, ("continuity or sqlstate", set())),
    ("commit_prepared_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("COMMIT PREPARED 'rf10_ro_absent'"), None, ("sqlstate", set())),
    ("do_block_commit_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("DO $$ BEGIN COMMIT; END $$"), None, ("sqlstate", set())),
    # each identity part decides alone
    ("token_overwritten_at_16828", "main._lease_admission_gate empty", E_16828,
     _token_overwritten, None, ("continuity", {"token"})),
    ("token_restored_after_chain_at_16828", "main._lease_admission_gate empty", E_16828,
     _token_restored, None, ("continuity", {"virtualxid"})),
    # session residue, measured
    ("plain_set_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("SET application_name = 'rf10_ro'"), None,
     ("continuity", {"setting application_name=rf10_ro"})),
    ("sql_prepare_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("PREPARE rf10_ro_p AS SELECT 1"), None, ("continuity", {"prepared 0->1"})),
    ("holdable_cursor_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("DECLARE rf10_ro_c CURSOR WITH HOLD FOR SELECT 1"), None,
     ("continuity", {"holdable cursors 0->1"})),
    # a later position on a session an earlier position broke (under grant:
    # 16901 ends the transaction 16881 locked; 16916 then runs, lock-clean
    # and with a zero delta, in the replacement transaction)
    ("chain_at_16871_then_16886_under_grant", "main._lease_admission_gate", E_16886,
     _then_own("COMMIT AND CHAIN"), ("UPDATE players",),
     ("continuity", {"after txn ended at main.py:16901"})),
    # the negative control: the same bracket, nothing planted
    ("unplanted_16828_under_role", "main._lease_admission_gate empty", E_16828,
     None, None, ("ok", set())),
    # Ruling FOUR-R10-A2 (3) FIX-R11-RES: settings with no pg_settings row
    # (the 16.9 probes, RF11 logs r11-res-probe-55432-20261106T065356Z.log and
    # r11-res-probe2-55432-20261106T090205Z.log). The round-10 report's case
    # (ro_covered.py:515): a session-scope custom placeholder at
    # main.py:16858, both drivers and the replacing route; then one control
    # per route, each refused by that route alone (R11_EXACT): the text
    # reading (a session set_config of '', and setseed, which no reading of
    # the session moves), the placeholder reading (a transaction-local
    # placeholder, which the text reading does not count), the hidden
    # settings reading (SET ROLE), and the RESET ALL check
    # (transaction_read_only, which read 'on' with source 'session' after
    # RESET ALL in the second 16.9 probe).
    ("set_config_hidden_at_16828_under_role", "main._lease_admission_gate empty", E_16828,
     _then_own(R11_HIDDEN), None, ("continuity", R11_HIDDEN_PARTS)),
    ("set_config_hidden_at_16828_under_grant", "main._lease_admission_gate empty", E_16828,
     _then_own(R11_HIDDEN), ("UPDATE players",), ("continuity", R11_HIDDEN_PARTS)),
    ("set_config_hidden_replaces_16828_under_role", "main._lease_admission_gate empty",
     E_16828, R11_HIDDEN, None, ("continuity", R11_HIDDEN_PARTS)),
    ("set_config_blank_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("SELECT pg_catalog.set_config('rf11res.blank', '', false)"), None,
     ("continuity", {"session set_config rf11res.blank"})),
    ("setseed_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("SELECT pg_catalog.setseed(0.5)"), None, ("continuity", {"session setseed"})),
    ("set_config_local_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("SELECT pg_catalog.set_config('rf11res.local', 'v', true)"), None,
     ("continuity", {"placeholder rf11res.local=v"})),
    ("set_role_at_16828", "main._lease_admission_gate empty", E_16828,
     _then_own("SET ROLE " + ro_role.ROLE), None,
     ("continuity", {"session SET role", "setting hidden role=none",
                     "setting hidden role=" + ro_role.ROLE})),
    ("transaction_read_only_at_16828_under_grant", "main._lease_admission_gate empty",
     E_16828, _then_own("SET transaction_read_only = on"), ("UPDATE players",),
     ("continuity", {"not reset transaction_read_only=on (session)"})),
)
# The controls whose refusal must be exactly their parts (each identity part
# or settings route decides alone).
R11_EXACT = ("set_config_blank_at_16828", "setseed_at_16828", "set_config_local_at_16828")
# The control whose RESET ALL proof must refuse (transaction_read_only is
# not reset by RESET ALL); every other measured position's proof is clean.
R11_NOT_RESET = {"transaction_read_only_at_16828_under_grant": ("transaction_read_only",)}
# The plant's site when it is not the measured entry's own; the measured
# targets when they are more than the entry (the grant driver's positions).
PLANT_AT = {"chain_at_16871_then_16886_under_grant": E_16871}
CONTROL_TARGETS = {"chain_at_16871_then_16886_under_grant": LEASE_GRANT_TARGETS}


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
                conts = list(db.info.get("continuity", []))
                # FIX-R11-RES: every measured position's RESET ALL proof
                GONE.append((tuple(sorted(targets)), plant is not None,
                             list(db.info.get("gone", []))))
                try:
                    await db.rollback()
                except BaseException:   # noqa: BLE001 -- a planted end left no transaction
                    pass
    finally:
        await engine.dispose()
    return log, deltas, locks, conts


# FIX-R11-RES: (targets, planted, the session's gone records) of every
# _counted run, in run order (the grant runs and the controls).
GONE = []

MERGE_ORDER = {"refused under grant": 0, "continuity under grant": 1, "lock under grant": 2}


def _control_outcome(log, deltas, locks, conts, entry, grants):
    """A control run's outcome at `entry`: under_grant's on a grant run;
    on the read-only role session, ran_outcome's when every run of it
    succeeded, else ('ran', outcomes)."""
    if grants:
        return ro_covered.under_grant(log, deltas, entry, list(grants), locks, conts)
    outs = ro_covered.outcome_at(log, entry)
    if outs and all(o == "ok" for o in outs):
        return ro_covered.ran_outcome(outs, ro_covered.locks_at(locks, entry),
                                      ro_covered.continuity_at(conts, entry))
    return ("ran", outs)


async def _prepared_left(role_dsn):
    """A prepared transaction the PREPARE TRANSACTION control left (only on a
    cluster with max_prepared_transactions > 0): rolled back on a role
    connection (its owner), and reported."""
    conn = await asyncpg.connect(role_dsn)
    try:
        left = await conn.fetchval(
            "SELECT count(*) FROM pg_catalog.pg_prepared_xacts WHERE gid = $1", PREPARED_GID)
        if left:
            await conn.execute("ROLLBACK PREPARED '%s'" % PREPARED_GID)
        return int(left)
    finally:
        await conn.close()


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


async def _grant_runs(admin, role_dsn, schema, s, mp):
    """The grant runs on `role_dsn`; `admin` is the admin connection on the
    clone, opened by the caller before the open recorder's freeze."""
    out = {"outcomes": {}, "control": {}, "checked": [], "plan": {}}
    plan = collections.OrderedDict()
    for e in UNREACHED:
        grants = ro_covered.REFUSER_GRANTS[ro_covered.role_outcome(e)[1]]
        for name in DRIVERS:
            if name.split()[0].split(".")[-1] == e[4]:
                g, es = plan.setdefault(name, (set(), []))
                g.update(grants)
                es.append(e)
    results = collections.defaultdict(list)
    for name, (grants, entries) in plan.items():
        out["plan"][name] = sorted(grants)
        await _grants(admin, schema, grants, "GRANT")
        try:
            log, deltas, locks, conts = await _counted(
                role_dsn, schema, out["checked"], DRIVERS[name], s, mp,
                {e[1:4] for e in entries})
        finally:
            await _grants(admin, schema, grants, "REVOKE")
        out.setdefault("conts", {})[name] = conts
        for e in entries:
            results[e].append(ro_covered.under_grant(log, deltas, e, sorted(grants),
                                                     locks, conts))
    out["results"] = {e: list(r) for e, r in results.items()}
    out["outcomes"] = {e: _merge(r) for e, r in results.items()}
    # E2 controls: a planted locking statement at a read position.
    out["lock_controls"] = {}
    for cname, driver, entry, sql, grants in LOCK_CONTROLS:
        plant = {entry[1:3]: sql} if sql else None
        if grants:
            await _grants(admin, schema, set(grants), "GRANT")
        try:
            log, deltas, locks, conts = await _counted(
                role_dsn, schema, out["checked"], DRIVERS[driver], s, mp,
                {entry[1:4]}, plant=plant, read_write=bool(grants))
        finally:
            if grants:
                await _grants(admin, schema, set(grants), "REVOKE")
        got = _control_outcome(log, deltas, locks, conts, entry, grants)
        out["lock_controls"][cname] = {"outcome": got, "log": log}
    # REHEARSAL-R9-A1 (B): the continuity controls, same route.
    out["continuity_controls"] = {}
    for cname, driver, entry, prog, grants, _want in CONTINUITY_CONTROLS:
        at = PLANT_AT.get(cname, entry)
        plant = {at[1:3]: prog} if prog else None
        targets = {e[1:4] for e in CONTROL_TARGETS.get(cname, [entry])}
        if grants:
            await _grants(admin, schema, set(grants), "GRANT")
        try:
            log, deltas, locks, conts = await _counted(
                role_dsn, schema, out["checked"], DRIVERS[driver], s, mp,
                targets, plant=plant, read_write=bool(grants))
        finally:
            if grants:
                await _grants(admin, schema, set(grants), "REVOKE")
        got = _control_outcome(log, deltas, locks, conts, entry, grants)
        out["continuity_controls"][cname] = {
            "outcome": got, "log": log, "conts": conts, "gone": GONE[-1][2],
            "prepared_left": await _prepared_left(role_dsn)}
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
    rec = ro_census.OpenRecorder()
    try:
        with pytest.MonkeyPatch.context() as mp:
            got = run(_run_all(ADMIN_DSN, clone, mp, rec))
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
                        "continuity_controls": {
                            k: {"outcome": v["outcome"], "conts": v["conts"]} for k, v in
                            got["grant_runs"]["continuity_controls"].items()},
                        "conts": got["conts"], "pids": got["pids"],
                    }, fh, indent=1, default=list)
            yield got
    finally:
        rec.thaw()
        run(ro_role.drop_clone(ADMIN_DSN, clone))


# ------------------------------------------- FOUR-R11-A8: the open recorder

def _window_refusal(w):
    """None when the window report `w` (OpenRecorder.report, read at the thaw)
    shows the bound held: the recorder was active, recorded at least one
    open and built at least one connection, and found no violation.
    Otherwise the sentence naming what failed (an installed recorder that
    saw nothing is refused, not passed)."""
    if not w or not w["active"]:
        return "the open recorder was not active at the thaw of the role and grant runs: %r" % (w,)
    if w["opens"] < 1 or w["built"] < 1:
        return "the open recorder of the role and grant runs recorded no open: %r" % (w,)
    if w["violations"]:
        return "the role and grant runs broke the open bound: %r" % (w["violations"],)
    return None


def test_r11_open_window_holds(runs):
    """Ruling FOUR-R11-A8 (2): in the role and grant runs, which carry the
    recorder, every connection that was built was opened to the frozen DSN
    (the role DSN of the clone)."""
    assert _window_refusal(runs["window"]) is None, _window_refusal(runs["window"])


def test_r11_open_window_control():
    """Ruling FOUR-R11-A8 (2), the control: an open to another DSN inside a
    window installed as _run_all installs it is refused by the module's own
    assertion, with the recorder's message."""
    if not ADMIN_DSN:
        pytest.fail("CF_TEST_PG_DSN is unset: name an admin DSN; this module never skips")
    rec = ro_census.OpenRecorder()
    frozen = ro_role.dsn_for(ADMIN_DSN, "rf8_ro_r11rec_never_opened", user=ro_role.ROLE)

    async def planted():
        rec.freeze(frozen, [None])
        try:
            conn = await asyncpg.connect(ADMIN_DSN)   # the planted open: another DSN
            await conn.close()
            return rec.report()
        finally:
            rec.thaw()

    w = run(planted())
    refusal = _window_refusal(w)
    assert refusal is not None and "open not the frozen DSN" in refusal, (refusal, w)
    assert (w["opens"], w["built"]) == (1, 1), w
    assert asyncpg.connect is asyncpg.connection.connect, "the thaw did not restore connect"


def measured(runs, entry):
    """'ok' when the position ran, every run of it succeeded and every run's
    lock read found only the expected rows (('lock', rows) when one found
    more; ruling REHEARSAL-R8-A1 E2); the
    position's SQLSTATE when it ran and was refused; ('not reached', site,
    sqlstate) naming the first refused statement of the drivers that hold
    the position's span; ('not reached', None, error) when no refusal
    explains it."""
    outs, reads, conts = [], [], []
    for name, log in runs["logs"].items():
        outs += ro_covered.outcome_at(log, entry)
        reads += ro_covered.locks_at(runs["locks"].get(name, []), entry)
        conts += ro_covered.continuity_at(runs["conts"].get(name, []), entry)
    if outs:
        bad = sorted({o for o in outs if o != "ok"})
        # E2: every run succeeded; its continuity (REHEARSAL-R9-A1 (B)) and
        # its lock reads decide 'ok', ('continuity', ...) or ('lock', rows)
        return ro_covered.ran_outcome(outs, reads, conts) if not bad else bad[0]
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


# ------------------------------- REHEARSAL-R9-A1 (B): transaction continuity

def _refused_parts(got):
    """The continuity refusal's detail of a control outcome, or None when
    the outcome is not a continuity refusal."""
    if got and got[0] == "continuity":
        return set(got[1])
    if got and got[0] == "continuity under grant":
        return set(got[2])
    return None


@pytest.mark.parametrize("name", [c[0] for c in CONTINUITY_CONTROLS])
def test_continuity_control(runs, name):
    """Ruling REHEARSAL-R9-A1 (B): a statement planted at a read position
    that ends the transaction (every ending form), changes the position
    token, or leaves session residue is refused as an effect by the
    continuity bracket (the run itself succeeded: the refusal is the
    bracket's), or is refused by the server; never green. Each identity
    part refuses alone (token_overwritten: the token only;
    token_restored_after_chain: the virtual transaction id only). A later
    position on a session an earlier position broke is refused too. The
    unplanted run is 'ok' (the negative control). No prepared transaction
    is left behind."""
    rec = runs["grant_runs"]["continuity_controls"][name]
    got = rec["outcome"]
    _n, _d, _e, _p, grants, (want, parts) = next(c for c in CONTINUITY_CONTROLS if c[0] == name)
    assert rec["prepared_left"] == 0, rec
    if want == "ok":
        assert got == "ok" and ro_covered.green(got), got
        assert rec["conts"] and all(c[2] for c in rec["conts"]), rec["conts"]
        return
    assert not ro_covered.green(got), got
    refused = _refused_parts(got)
    if want == "sqlstate":
        assert got[0] == "ran" and got[1] and all(o != "ok" for o in got[1]), got
        return
    if want == "continuity or sqlstate":
        assert refused is not None or (got[0] == "ran" and "55000" in got[1]), got
        return
    assert refused is not None, got
    if grants:
        assert got[1] == tuple(grants), got
    assert parts <= refused, (got, parts)
    if name in ("token_overwritten_at_16828", "token_restored_after_chain_at_16828") + R11_EXACT:
        assert refused == parts, (got, parts)


@pytest.mark.parametrize("driver", ["role", "grant", "replaces_role", "replaces_grant"])
def test_r10_n_ro_covered_488_commit_and_chain_at_16828_refused(runs, driver):
    """The round-9 report's case (ro_covered.py:488): `COMMIT AND CHAIN` at
    main.py:16858 must not classify as a read; the lock and counter
    measurements must not read the replacement transaction. Executed at the
    control's route (a planted program at the position: COMMIT AND CHAIN,
    then the position's own statement; main.py unchanged), under the
    read-only role and under a grant: refused by the continuity bracket
    (token and virtual transaction id both changed), never green, and the
    lookup can never answer 'read' for it. The side control (RF/r10/ro,
    r10-ro-neg-side-*.log) runs the same case on the round-9 harness:
    admitted there ('ok' / ('ok-under-grant', grants, 0))."""
    name = {"role": "commit_and_chain_at_16828_under_role",
            "grant": "commit_and_chain_at_16828_under_grant",
            "replaces_role": "commit_and_chain_replaces_16828_under_role",
            "replaces_grant": "commit_and_chain_replaces_16828_under_grant"}[driver]
    got = runs["grant_runs"]["continuity_controls"][name]["outcome"]
    assert not ro_covered.green(got), got
    assert {"token", "virtualxid"} <= (_refused_parts(got) or set()), got
    # the same position unplanted stays a read: the refusal is the plant's
    assert ro_covered.green(ro_covered.OUTCOME[E_16828])


def test_r10_driver_connections_discarded(runs):
    """REHEARSAL-R9-A1 (B), session residue: every driver ran its positions
    on connections of its own (its NullPool engine is disposed after it),
    never one another driver used: a connection a position ran on (its
    backend pid with that backend's start time) is discarded, not reused."""
    seen = {}
    for name, pids in runs["pids"].items():
        for pid in pids:
            assert pid not in seen, (name, seen.get(pid), pid)
            seen[pid] = name
    assert seen, "no driver measured a position"


@pytest.mark.parametrize("driver", ["role", "grant", "replaces_role"])
def test_r11_n_ro_covered_515_hidden_set_config_at_16828_refused(runs, driver):
    """The round-10 report's case (ro_covered.py:515): `SELECT
    set_config('rf10.hidden','yes',false)` at main.py:16858 must refuse as
    session residue; pg_settings had no row for such a placeholder on 16.9
    (RF11 log r11-res-probe-55432-20261106T065356Z.log). Executed at the
    control's route (planted program then the position's own statement, and
    the replacing text), under the read-only role and under a grant: refused
    by the text reading (a session-scope set_config) AND by the placeholder
    reading (the name read on the session), never green; after RESET ALL the
    placeholder reads '' (the gone record names it, with no name away from
    its reset value)."""
    name = {"role": "set_config_hidden_at_16828_under_role",
            "grant": "set_config_hidden_at_16828_under_grant",
            "replaces_role": "set_config_hidden_replaces_16828_under_role"}[driver]
    rec = runs["grant_runs"]["continuity_controls"][name]
    got = rec["outcome"]
    assert not ro_covered.green(got), got
    assert R11_HIDDEN_PARTS <= (_refused_parts(got) or set()), got
    at = [g for g in rec["gone"] if g[0] == E_16828[1] and g[1] == E_16828[2]]
    assert at and all("rf10.hidden" in g[2] and g[3] == () for g in at), rec["gone"]
    assert ro_covered.green(ro_covered.OUTCOME[E_16828])


def _r11_control_names(gone_rows):
    return {n for g in gone_rows for n in g[2]}


def test_r11_every_measured_position_is_reset(runs):
    """FIX-R11-RES: every bracketed position of every run (the role run, the
    grant runs and every control) is followed by RESET ALL with its proof:
    one gone record per continuity record, and every record clean (each name
    its texts set, and the position token, at its reset value by class),
    except the transaction_read_only control (on, source 'session', after
    RESET ALL in the second 16.9 probe), where the check names exactly that
    setting."""
    total = 0
    for name, conts in runs["conts"].items():
        gone = runs["gone"][name]
        assert len(gone) == len(conts), (name, len(gone), len(conts))
        assert all(g[3] == () for g in gone), (name, [g for g in gone if g[3]])
        total += len(gone)
    for cname, rec in runs["grant_runs"]["continuity_controls"].items():
        assert len(rec["gone"]) == len(rec["conts"]), (cname, rec["gone"], rec["conts"])
        want = R11_NOT_RESET.get(cname)
        for g in rec["gone"]:
            if want and (g[0], g[1]) == tuple(E_16828[1:3]):
                assert tuple(sorted({x.split("=", 1)[0][len("not reset "):]
                                     for x in g[3]})) == want, (cname, g)
            else:
                assert g[3] == (), (cname, g)
        total += len(rec["gone"])
    for targets, planted, gone in GONE:
        if not planted:
            assert all(g[3] == () for g in gone), (targets, gone)
    assert total > 0


def test_r11_res_capture_reads_every_planted_text(runs):
    """FIX-R11-RES: the names the measurement read at a planted position
    come from the planted program's own statements (captured at the engine,
    not only the production statement): each settings control's gone record
    names the setting its plant sets."""
    want = {"set_config_hidden_at_16828_under_role": "rf10.hidden",
            "set_config_blank_at_16828": "rf11res.blank",
            "set_config_local_at_16828": "rf11res.local",
            "set_role_at_16828": "role",
            "transaction_read_only_at_16828_under_grant": "transaction_read_only"}
    for cname, n in want.items():
        rec = runs["grant_runs"]["continuity_controls"][cname]
        assert n in _r11_control_names(rec["gone"]), (cname, rec["gone"])


def _r11_production_records(runs):
    """The gone records of every run that planted nothing (the role run's
    drivers and the unplanted grant and control runs): the program's own
    texts only."""
    out = [g for gone in runs["gone"].values() for g in gone]
    out += [g for _targets, planted, gone in GONE if not planted for g in gone]
    return out


# Ruling FOUR-R11-A6 (3a): every (name, class, scope) the program's own
# captured texts set, measured on seat-3 (16.15) at ec9ecef6 (RF11 log
# r11-res-p2-r8-ec9ecef6.log): one name, the SET LOCAL lock_timeout of
# main._identity_lock_many (main.py 17369-17400 at this tip; NOTES-r11-res.md).
R11_SETTING_NAMES = (("lock_timeout", "server", "local"),)
# (3b): the placeholders those texts set at session scope: frozen at none.
R11_SESSION_PLACEHOLDERS = ()


def test_r11_res_settings_census(runs):
    """Ruling FOUR-R11-A6 (3): (a) every setting name the program's own
    captured texts set, with its class and scope, equals the frozen list;
    (b) the placeholders they set at session scope are the frozen ones
    (none), named otherwise; (c) the harness token's name stands in no
    captured text of any run (planted controls aside: they plant it on
    purpose) and in no function source of the measured database."""
    recs = _r11_production_records(runs)
    assert recs, "no production position was measured"
    got = tuple(sorted({e for g in recs for e in g[4]}))
    assert got == R11_SETTING_NAMES, got
    sess = tuple(sorted({e[0] for e in got if e[1] == "placeholder" and e[2] == "session"}))
    assert sess == R11_SESSION_PLACEHOLDERS, sess
    assert not [g for g in recs if g[5]], [g for g in recs if g[5]]
    census = runs["proc_census"]
    _m, _c, token_sources = ro_covered.proc_census(census["rows"], census["schema"])
    assert token_sources == (), token_sources


def _r11_census_report(matched, compiled):
    """The census as text, for the failure message: each match with its
    language, md5, words, proconfig; each compiled function."""
    return json.dumps({"matched": {k: list(v) for k, v in sorted(matched.items())},
                       "compiled": [list(c) for c in compiled]}, indent=0)


def test_r11_res_proc_census(runs):
    """Ruling FOUR-R11-A6 (4): the census of the measured database's
    functions outside the system schemas equals the frozen PROC_SIDES (each
    match by its md5) and PROC_COMPILED; a new match, a changed md5 or a new
    compiled function fails with its name. No frozen function sets at
    session scope."""
    census = runs["proc_census"]
    matched, compiled, _t = ro_covered.proc_census(census["rows"], census["schema"])
    diff = ro_covered.proc_census_diff(matched, compiled)
    # a str message, printed whole (a tuple's repr is shortened)
    assert diff == (), "%r\n%s" % (diff, _r11_census_report(matched, compiled))
    assert compiled == (), compiled
    assert not [k for k, v in ro_covered.PROC_SIDES.items() if v[1] == "session"]
    assert all(v[1] in ("transaction", "neither") for v in ro_covered.PROC_SIDES.values())


def test_r11_res_proc_census_control(runs):
    """The control: a function planted in the case schema inside a
    transaction that is rolled back, its body set_config(..., false), is
    reported by name, and only it; after the rollback the census is the
    frozen one again."""
    census = runs["proc_census"]
    matched, compiled, _t = ro_covered.proc_census(census["planted"], census["schema"])
    key = "<case>.%s() f" % R11_PLANTED_FN
    assert ro_covered.proc_census_diff(matched, compiled) == ("new " + key,), (
        ro_covered.proc_census_diff(matched, compiled))
    assert "set_config" in matched[key][2], matched[key]
    matched, compiled, _t = ro_covered.proc_census(census["after"], census["schema"])
    assert ro_covered.proc_census_diff(matched, compiled) == ()


def test_r10_every_position_is_bracketed(runs):
    """Every successful run of every measured position on the role run has a
    continuity record (a run with none is never 'ok': ran_outcome's
    'unmeasured'), and every position the walks may read ('ok' in OUTCOME)
    kept its transaction in every run."""
    for name, log in runs["logs"].items():
        conts = runs["conts"].get(name, [])
        oks = [e for e in log if e[2] == "ok" and ro_covered._in(e[:2], LOCK_TARGETS)]
        assert len(conts) == len(oks), (name, len(conts), len(oks))
    for e in ro_covered.COVERED:
        if ro_covered.OUTCOME[e] == "ok":
            got = [c for n in runs["conts"] for c in ro_covered.continuity_at(runs["conts"][n], e)]
            assert got and all(same for same, _d in got), (e, got)


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
     {("dynamic", "getattr(driver, 'con' + 'nect')"),
      # round 10: the call of getattr's result is a constructed callee
      ("constructed", "getattr(driver, 'con' + 'nect')(DSN)")}, True),
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
     {("dynamic", "vars(_asyncpg)"),
      # round 10: the call of a subscript is a constructed callee
      ("constructed", "vars(_asyncpg)['con' + 'nect'](DSN)")}, True),
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
    once as a call; the count is the coarse 365 (363, plus the two coarse forms
    of the round-11 merge, re-frozen once from the seat derivation), plus the
    one coarse form of the B10 merge (B10_MERGE_FROZEN, frozen by hand), plus
    the complete layer."""
    import ro_census
    import ro_census_frozen as fz
    import test_r7_ro_role_pg as r7
    coarse = {k for k in fz.FROZEN if not k.endswith(ro_census.COMPLETE)}
    complete = {k for k in fz.FROZEN if k.endswith(ro_census.COMPLETE)}
    # round 10: the R10 kinds join each file's complete layer
    assert set(fz.R10_FROZEN) == complete
    # every census file has a complete layer (empty or not); the coarse
    # freeze lists only the files with a coarse form
    assert complete == {k + ro_census.COMPLETE for k in r7.CENSUS_FILES}
    assert coarse <= set(r7.CENSUS_FILES)
    assert sum(len(fz.FROZEN[k]) for k in coarse) == fz.COARSE_COUNT + fz.B10_MERGE_COUNT == 366
    assert fz.COARSE_COUNT == 365
    # the B10 merge: one hand-frozen coarse import form (W30k)
    assert sum(len(v) for v in fz.B10_MERGE_FROZEN.values()) == fz.B10_MERGE_COUNT == 1
    assert set(fz.B10_MERGE_FROZEN) <= coarse
    assert {f[0] for v in fz.B10_MERGE_FROZEN.values() for f in v} == {"import"}
    assert sum(len(fz.COMPLETE_FROZEN[k]) for k in complete) == fz.COMPLETE_COUNT == 218
    assert sum(len(fz.R10_FROZEN[k]) for k in complete) == fz.R10_COUNT == 114
    # round 10's merge: the hand-frozen block (W30b), fifteen forms of the gr child's providers
    assert sum(len(v) for v in fz.R10_MERGE_FROZEN.values()) == fz.R10_MERGE_COUNT == 15
    assert set(fz.R10_MERGE_FROZEN) <= complete
    assert {f[0] for v in fz.R10_MERGE_FROZEN.values() for f in v} <= {"alias", "dynamic"}
    # round 11: the two derived blocks (R11_ID_FROZEN, R11_OPEN_FROZEN) join
    # the complete layer only, with alias and dynamic forms only
    r11 = list(fz.R11_ID_FROZEN.items()) + list(fz.R11_OPEN_FROZEN.items())
    assert {k for k, _v in r11} <= complete
    assert {f[0] for _k, v in r11 for f in v} <= {"alias", "dynamic"}
    assert sum(len(v) for v in fz.R11_ID_FROZEN.values()) == fz.R11_ID_COUNT
    assert sum(len(v) for v in fz.R11_OPEN_FROZEN.values()) == fz.R11_OPEN_COUNT
    assert sum(len(fz.FROZEN[k]) for k in complete) == (fz.COMPLETE_COUNT + fz.R10_COUNT
                                                        + fz.R10_MERGE_COUNT
                                                        + fz.R11_ID_COUNT + fz.R11_OPEN_COUNT)
    assert fz.FROZEN_COUNT == (fz.COARSE_COUNT + fz.COMPLETE_COUNT + fz.R10_COUNT
                               + fz.R10_MERGE_COUNT + fz.R11_ID_COUNT + fz.R11_OPEN_COUNT
                               + fz.B10_MERGE_COUNT) == 855
    assert not [f for k in complete for f in fz.FROZEN[k] if f[0] == "refuse"]
    assert {f[0] for k in complete for f in fz.R10_FROZEN[k]} <= set(R10_KINDS)
    # the declared forwarding wrapper is bound whole, exactly once
    assert [f for f in fz.FROZEN["api/database.py" + ro_census.COMPLETE]
            if f[0] == "wrapper" and f[1].startswith(
                "def create_async_engine(url, **options):")] == [
        ("wrapper", "def create_async_engine(url, **options):\n"
                    "    return _sqlalchemy_create_async_engine(url, hide_parameters=True,"
                    " **options)")]
    for (rel, call) in ro_census.FORWARDING:
        assert list(map(tuple, fz.FROZEN[rel + ro_census.COMPLETE])).count(
            ("call", call)) == 1, (rel, call)


# ------------------------- REHEARSAL-R9-A1 (C): refuse by default, the census

R10_KINDS = ("constructed", "alias", "wrapper", "argdef")
DB_REL = "api/database.py"
LADDER_REL = "tests/ladder_pg_harness.py"
POOL_REL = "tests/cf_pool.py"
WRAPPER_HEAD = "def create_async_engine(url, **options):\n    return _sqlalchemy"
ASM_UPDATE = "    args.update(connect_args)\n"
ASM_DEF = "def make_asm_engine(url=DATABASE_URL, **connect_args):"


def _wrapper_of(rel, name):
    """The frozen wrapper form of function `name` in `rel`."""
    import ro_census
    import ro_census_frozen as fz
    heads = ("def %s(" % name, "async def %s(" % name)
    got = [f for f in fz.FROZEN[rel + ro_census.COMPLETE]
           if f[0] == "wrapper" and any(line.startswith(heads)
                                        for line in f[1].split("\n")[:3])]
    assert len(got) == 1, (rel, name, got)
    return tuple(got[0])


# Each row: (name, file, change (('replace', old, new) once, or ('append',
# program)), the complete-layer forms the change must ADD, the forms it must
# REMOVE, whether the coarse layer stays unchanged). An added wrapper is
# written ('wrapper', '~' + a text the one added wrapper must contain).
R10_PLANTED = (
    # (C) constructed callees: each refuses unless its exact form is frozen
    ("constructed_call_result", CENSUS_REL,
     ("append", "\nasync def _planted(factory):\n    return await factory()(DSN)\n"),
     {("constructed", "factory()(DSN)")}, set(), True),
    ("constructed_subscript", CENSUS_REL,
     ("append", "\nasync def _planted(table):\n    return await table['pg'](DSN)\n"),
     {("constructed", "table['pg'](DSN)")}, set(), True),
    ("constructed_dunder_call", CENSUS_REL,
     ("append", "\nasync def _planted(opener):\n    return await opener.__call__(DSN)\n"),
     {("constructed", "opener.__call__(DSN)")}, set(), True),
    ("constructed_boolean", CENSUS_REL,
     ("append", "\nasync def _planted(a, b):\n    return await (a or b)(DSN)\n"),
     {("constructed", "(a or b)(DSN)")}, set(), True),
    # (C) aliases of a dynamic-access name or of an opener
    ("alias_import_from_builtins", CENSUS_REL,
     ("append", "\nfrom builtins import getattr as pick\n"),
     {("alias", "from builtins import getattr as pick")}, set(), True),
    ("alias_import_builtins", CENSUS_REL,
     ("append", "\nimport builtins\n"),
     {("alias", "import builtins")}, set(), True),
    ("alias_assign_getattr", CENSUS_REL,
     ("append", "\npick = getattr\n"),
     {("alias", "pick = getattr")}, set(), True),
    ("alias_attribute_getattr", CENSUS_REL,
     ("append", "\npick = builtins_mod.getattr\n"),
     {("alias", "pick = builtins_mod.getattr")}, set(), True),
    ("alias_builtins_table", CENSUS_REL,
     ("append", "\nasync def _planted():\n"
                "    return await __builtins__['getattr'](_asyncpg, 'con' + 'nect')(DSN)\n"),
     {("alias", "__builtins__['getattr']"), ("alias", "str getattr"),
      ("constructed", "__builtins__['getattr'](_asyncpg, 'con' + 'nect')"),
      ("constructed", "__builtins__['getattr'](_asyncpg, 'con' + 'nect')(DSN)")}, set(), True),
    ("alias_globals_key", CENSUS_REL,
     ("append", "\nasync def _planted():\n"
                "    return await globals()['getattr'](_asyncpg, 'con' + 'nect')(DSN)\n"),
     {("dynamic", "globals()"), ("alias", "str getattr"),
      ("constructed", "globals()['getattr'](_asyncpg, 'con' + 'nect')"),
      ("constructed", "globals()['getattr'](_asyncpg, 'con' + 'nect')(DSN)")}, set(), True),
    ("alias_attribute_vars", CENSUS_REL,
     ("append", "\nasync def _planted(b):\n"
                "    return await b.vars(_asyncpg)['con' + 'nect'](DSN)\n"),
     {("alias", "b.vars(_asyncpg)"),
      ("constructed", "b.vars(_asyncpg)['con' + 'nect'](DSN)")}, set(), True),
    ("alias_rebinding_def", CENSUS_REL,
     ("append", "\ndef getattr(o, n):\n    return o\n"),
     {("alias", "def getattr")}, set(), True),
    ("alias_parameter", CENSUS_REL,
     ("append", "\ndef _planted(getattr=None):\n    return getattr\n"),
     {("alias", "arg getattr"), ("alias", "return getattr")}, set(), True),
    # (C) the forwarding wrapper bound whole, and a forwarded argument's
    # local definition
    ("wrapper_local_definition", DB_REL,
     ("replace", ASM_UPDATE, ASM_UPDATE + "    args['user'] = 'scr_gate'\n"),
     {("wrapper", "~args['user'] = 'scr_gate'")}, {"make_asm_engine"}, True),
    ("wrapper_signature_default", DB_REL,
     ("replace", ASM_DEF, ASM_DEF.replace("DATABASE_URL", "ADMIN_URL")),
     {("wrapper", "~def make_asm_engine(url=ADMIN_URL, **connect_args):")},
     {"make_asm_engine"}, True),
    # (C) the definitions of a forwarded module-scope name
    ("argdef_module_rebinding", CENSUS_REL,
     ("append", "\nDSN = DSN_ALT\n"),
     {("argdef", "DSN <- DSN = DSN_ALT")}, set(), True),
    ("argdef_augmented", DB_REL,
     ("append", "\nDATABASE_URL += '?options=x'\n"),
     {("argdef", "DATABASE_URL <- DATABASE_URL += '?options=x'")}, set(), True),
    ("argdef_mutated_definition", LADDER_REL,
     ("append", "\nasync_dsn.__defaults__ = ('x',)\n"),
     {("argdef", "async_dsn <- async_dsn.__defaults__ = ('x',)")}, set(), True),
    ("argdef_global_function", CENSUS_REL,
     ("append", "\ndef _planted(x):\n    global DSN\n    DSN = x\n"),
     {("argdef", "DSN <- def _planted(x):\n    global DSN\n    DSN = x")}, set(), True),
    ("argdef_method_mutation", POOL_REL,
     ("append", "\ncf_pg.DSN_PARTS.update(host='h')\n"),
     {("argdef", "cf_pg <- cf_pg.DSN_PARTS.update(host='h')")}, set(), False),
)


def _r10_planted_diff(rel, change):
    """(added, removed, coarse diff, unplanted diff) of one planted change
    against the frozen census of `rel`."""
    import ro_census
    import ro_census_frozen
    with open(os.path.join(HERE, "..", rel), encoding="utf-8") as fh:
        src = fh.read()
    if change[0] == "replace":
        assert src.count(change[1]) == 1, change[1]
        planted = src.replace(change[1], change[2], 1)
    else:
        planted = src + change[1]
    key = rel + ro_census.COMPLETE
    frozen = {k: ro_census_frozen.FROZEN[k] for k in (rel, key) if k in ro_census_frozen.FROZEN}
    frozen.setdefault(rel, [])
    refused = ro_census.diff(ro_census.file_forms(rel, planted), frozen)
    added = {r[2:] for r in refused if r[0] == key and r[1] == "+"}
    removed = {r[2:] for r in refused if r[0] == key and r[1] == "-"}
    coarse = [r for r in refused if r[0] == rel]
    clean = ro_census.diff(ro_census.file_forms(rel, src), frozen)
    return added, removed, coarse, clean


@pytest.mark.parametrize("name", [p[0] for p in R10_PLANTED])
def test_r10_census_refuses_by_default(name):
    """Ruling REHEARSAL-R9-A1 (C): each planted form adds exactly the row's
    round-10 forms to the complete layer (refused: the freeze lacks them) and
    removes exactly the row's frozen wrappers; where the row says so, the
    coarse layer is unchanged (it alone would have accepted the form)."""
    _n, rel, change, want_add, want_removed, coarse_same = next(
        p for p in R10_PLANTED if p[0] == name)
    added, removed, coarse, clean = _r10_planted_diff(rel, change)
    exact = {f for f in want_add if not (f[0] == "wrapper" and f[1].startswith("~"))}
    loose = [f[1][1:] for f in want_add if f[0] == "wrapper" and f[1].startswith("~")]
    got_loose = [f for f in added if f[0] == "wrapper"]
    rest = added - set(got_loose) if loose else added
    assert rest == exact, ("the planted form is not refused as the row requires",
                           added, want_add)
    if loose:
        assert len(got_loose) == len(loose) and all(
            any(t in f[1] for f in got_loose) for t in loose), (got_loose, loose)
    assert removed == {_wrapper_of(rel, n) for n in want_removed}, (removed, want_removed)
    if coarse_same:
        assert coarse == [], coarse
    assert clean == [], clean


def test_r10_n_ro_census_199_dynamic_alias_opener():
    """The round-9 report's case (ro_census.py:199): `from builtins import
    getattr as pick` followed by `await pick(_asyncpg, 'con' + 'nect')(DSN,
    **{'user':'scr_gate'})` must refuse as an unfrozen opener. Planted into
    tests/cf_pg.py's text: the coarse layer is unchanged (the finding: no
    form at round 9 in either layer) and the complete layer adds exactly the
    import alias and the constructed callee, both refused. The side control
    (r10-ro-neg-side-census-*.log) records the case admitted by the round-9
    census (no form in either layer)."""
    program = ("\nfrom builtins import getattr as pick\n\nasync def _planted():\n"
               "    return await pick(_asyncpg, 'con' + 'nect')(DSN, **{'user':'scr_gate'})\n")
    added, removed, coarse, clean = _r10_planted_diff(CENSUS_REL, ("append", program))
    assert added == {
        ("alias", "from builtins import getattr as pick"),
        ("constructed", "pick(_asyncpg, 'con' + 'nect')(DSN, **{'user': 'scr_gate'})")}, added
    assert removed == set() and coarse == [] and clean == [], (removed, coarse, clean)


def test_r10_n_ro_census_193_forwarding_connect_args():
    """The round-9 report's case (ro_census.py:193): adding
    `options['connect_args']={'user':'scr_gate'}` inside
    `database.create_async_engine` must refuse. Planted into
    api/database.py's text: the coarse layer is unchanged and the FORWARDING
    call keeps its frozen `call` form (the finding), but the wrapper bound
    whole changes: its frozen form is missing and the changed one is added,
    both refused. The side control records it admitted by the round-9
    census."""
    planted = WRAPPER_HEAD.replace(
        ":\n    return", ":\n    options['connect_args']={'user':'scr_gate'}\n    return")
    added, removed, coarse, clean = _r10_planted_diff(DB_REL, ("replace", WRAPPER_HEAD, planted))
    assert removed == {_wrapper_of(DB_REL, "create_async_engine")}, removed
    assert len(added) == 1 and next(iter(added))[0] == "wrapper" and (
        "options['connect_args'] = {'user': 'scr_gate'}" in next(iter(added))[1]), added
    assert coarse == [] and clean == [], (coarse, clean)

# ---- SWEEP (E), round 10 child ro: the counted operation sites ----
#
# Ruling REHEARSAL-R9-A1 (E): every presence check of a transaction in
# ro_covered.py and in this file above this mark (every lock read, counter
# read, continuity read, catalog read, outcome computed from a read, and
# every transaction end or presence test), and every callee classification
# site and forwarding binding in ro_census.py, counted by its operation
# (comments excluded). Each site and its disposition (fixed, or hold with the
# reason) is listed in RF/r10/ro/NOTES-r10-ro.md (the sweep table); a new
# site changes a count and fails here until the table and these counts are
# changed together by a reviewed edit.
# FIX-R11-RES: catalog read 11 -> 22 in ro_covered.py (RESIDUE_SQL's temporary
# objects in 8 more catalogs, NAMED_SETTINGS_SQL, placeholder_residue's and
# not_reset's docstrings) and 1 -> 2 here (the r11 negative's docstring);
# each listed in RF11 r11/res/NOTES-r11-res.md.
# FIX-R11-RES under ruling FOUR-R11-A6: catalog read 22 -> 23 in ro_covered.py
# (docstrings of setting_classes, placeholder_residue, not_reset: three in,
# two out) and transaction end 3 -> 4 here (_proc_census's rollback of the
# planted function's own transaction, on its own connection).
SWEEP_TXN = {'lock read': 'LOCKS_SQL|lock_read\\(', 'counter read': 'WRITES_SQL|\\.writes\\(\\)', 'continuity read': 'POSITION_(?:START|END)_SQL|RESIDUE_SQL|position_(?:start|end)\\(|\\.residue\\(\\)', 'catalog read': 'pg_locks|pg_stat_xact|pg_settings|pg_prepared_statements|pg_cursors|pg_listening_channels|pg_my_temp_schema|pg_prepared_xacts', 'outcome from a read': 'ran_outcome\\(|lock_outcome\\(|under_grant\\(|broken_continuity\\(|continuity_at\\(|locks_at\\(', 'transaction end or presence': 'rollback\\(|commit\\(|in_transaction|get_transaction|\\.begin\\('}
SWEEP_CALLEE = {'callee read': '\\.func\\b', 'callee name': '_name_of\\(|_dotted\\(', 'callee class': '_constructed\\(|_classified_callee\\(|CLASSIFIED_(?:NAME|ATTR)_CALLS', 'call node': 'ast\\.Call\\b', 'forwarding binding': 'FORWARDING|_forwarding\\(|_arg_names\\(|_binds\\(|_stmt_binds\\(|_stmt_mutates\\(|_module_statements\\(|_own_nodes\\('}
SWEEP_COUNTS = {'ro_covered.py': {'lock read': 5, 'counter read': 4, 'continuity read': 12, 'catalog read': 23, 'outcome from a read': 12, 'transaction end or presence': 0}, 'test_r8_ro_covered_pg.py': {'lock read': 0, 'counter read': 2, 'continuity read': 0, 'catalog read': 2, 'outcome from a read': 10, 'transaction end or presence': 4}, 'ro_census.py': {'callee read': 10, 'callee name': 9, 'callee class': 10, 'call node': 5, 'forwarding binding': 17}}


def _sweep_code(name):
    import io
    import tokenize
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        src = fh.read()
    if SWEEP_MARK in src:
        src = src[:src.index(SWEEP_MARK)]
    toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type != tokenize.COMMENT]
    return tokenize.untokenize(toks)


SWEEP_MARK = "# ---- SWEEP (E), round 10 child ro: " + "the counted operation sites ----"


@pytest.mark.parametrize("name", sorted(SWEEP_COUNTS))
def test_r10_sweep_counts(name):
    """(E): the operation counts equal the swept table's."""
    import re
    pats = SWEEP_CALLEE if name == "ro_census.py" else SWEEP_TXN
    text = _sweep_code(name)
    got = {k: len(re.findall(v, text)) for k, v in pats.items()}
    assert got == SWEEP_COUNTS[name], (name, got, SWEEP_COUNTS[name])
