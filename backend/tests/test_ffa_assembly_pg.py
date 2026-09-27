"""The connect-failure lane's server controls (DESIGN V11, evidence sec8.1),
against a local PostgreSQL through cf_pg (one case schema per case).

Every case builds its schema with 355_ffa_assembly.sql applied WHOLE inside
its own BEGIN/COMMIT as the first apply (cf_pg.build), and calls the real
handlers in main.py with a session bound to that schema. The mutation half of
each control (the mutant that must turn the named assertion red, and the
inert twin that must stay green) is run by cf_controls.py, which rewrites
main.py in a scratch copy and runs the named test against it.
"""

import asyncio
import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import cf_pg  # noqa: E402

try:
    import asyncpg as _asyncpg
except ImportError:                                    # pragma: no cover
    _asyncpg = None


def _run(coro):
    return asyncio.run(coro)


# -- the migration: first apply, re-run, the standing invariants, the CHECKs --

_CONSTRAINTS_SQL = (
    "SELECT c.conname, c.oid::bigint AS oid FROM pg_constraint c "
    " WHERE c.conrelid IN (to_regclass('ffa_assembly_seats'), to_regclass('ffa_lobbies'), "
    "                      to_regclass('ffa_kept_epochs'), to_regclass('ffa_g3_seats')) "
    " ORDER BY 1")
_INDEX_SQL = "SELECT to_regclass('ffa_assembly_seats_player_verdict')::oid::bigint"


async def _seed_pre_355(conn):
    """A player and a lobby that exist BEFORE 355 runs, as production's do."""
    pid = await conn.fetchval(
        "INSERT INTO players (steam_id, display_name) VALUES ('76561190000355001', 'cf pre') "
        "RETURNING id")
    lid = await conn.fetchval(
        "INSERT INTO ffa_lobbies (id, status, member_ids, player_count, photon_room_id, region) "
        "VALUES (gen_random_uuid(), 'active', ARRAY[$1::uuid], 1, 'ffa_pre355', 'eu') "
        "RETURNING id", pid)
    return pid, lid


def test_355_first_apply_rerun_invariants_and_checks():
    """B2: the whole file, first apply then re-run, on a schema that holds a
    pre-migration lobby; the proof block ran (it raises on any gap); a re-run
    replaces no constraint or index; the pre-migration lobby reads ungated and
    bettable; every standing invariant is 0; each CHECK refuses its bad row
    and admits the good one (the write half of the dry run)."""
    cf_pg.require_live_pg()

    async def go():
        async with cf_pg.case("cf_mig", with_355=False) as (c, sm):
            conn = c.conn
            assert await conn.fetchval("SELECT to_regclass('ffa_assembly_seats')") is None
            pid, lid = await _seed_pre_355(conn)
            await cf_pg.apply_355(conn)
            first = [tuple(r) for r in await conn.fetch(_CONSTRAINTS_SQL)]
            index_oid = await conn.fetchval(_INDEX_SQL)
            await cf_pg.apply_355(conn)
            second = [tuple(r) for r in await conn.fetch(_CONSTRAINTS_SQL)]
            assert first == second, "a re-run replaced a constraint"
            assert await conn.fetchval(_INDEX_SQL) == index_oid, "a re-run rebuilt the index"
            names = {r[0] for r in first}
            for want in ("ck_ffa_seat_late_body", "ck_ffa_seat_gone", "ck_ffa_seat_release",
                         "ck_ffa_seat_verdict", "ck_ffa_lobby_reform_no_bets",
                         "ck_ffa_lobby_short_no_bets", "ck_ffa_lobby_region_why"):
                assert want in names, want
            await c.seal()
            row = await conn.fetchrow(
                "SELECT assembly_v1, admission_v1, bets_disabled, reformed_from, "
                "start_granted_at FROM ffa_lobbies WHERE id = $1", lid)
            assert (row["assembly_v1"], row["admission_v1"], row["bets_disabled"]) == \
                (False, False, False)
            assert row["reformed_from"] is None and row["start_granted_at"] is None
            assert await conn.fetchval(
                "SELECT caps FROM ffa_queue LIMIT 0") is None
            inv = await cf_pg.standing_invariants(conn)
            assert inv == {k: 0 for k in inv}, inv

            async def refused(sql, *args):
                try:
                    await conn.execute(sql, *args)
                except _asyncpg.CheckViolationError:
                    return True
                return False

            ins = ("INSERT INTO ffa_assembly_seats (lobby_id, player_id, slot, %s) "
                   "VALUES ($1, $2, 0, %s)")
            bad = [
                ("verdict", "'started'"),
                ("late_body_game, late_game", "1, 2"),
                ("late_body_game", "1"),
                ("gone_game", "1"),
                ("gone_game, gone_path", "1, 'claim'"),
                ("released_at", "NOW()"),
                ("released_at, release_why", "NOW(), 'leave'"),
            ]
            for cols, vals in bad:
                assert await refused(ins % (cols, vals), lid, pid), cols
            await conn.execute(
                ins % ("verdict, late_game, late_body_game, gone_game, gone_path, "
                       "released_at, release_why",
                       "'granted', 1, 1, 2, 'witness', NOW(), 'fence_expired'"), lid, pid)
            assert await refused(
                "UPDATE ffa_lobbies SET reformed_from = gen_random_uuid() WHERE id = $1", lid)
            assert await refused(
                "UPDATE ffa_lobbies SET short_started_at = NOW() WHERE id = $1", lid)
            assert await refused(
                "UPDATE ffa_lobbies SET region_why = 'guess' WHERE id = $1", lid)
            await conn.execute(
                "UPDATE ffa_lobbies SET bets_disabled = TRUE, short_started_at = NOW(), "
                "region_why = 'quorum' WHERE id = $1", lid)
            assert await refused(
                "INSERT INTO ffa_kept_epochs (lobby_id, epoch_no, slot, actor_nr, chain) "
                "VALUES ($1, 0, 0, 1, '0000000000000000')", lid)
            await conn.execute(
                "INSERT INTO ffa_kept_epochs (lobby_id, epoch_no, slot, actor_nr, chain) "
                "VALUES ($1, 1, 0, 1, '0000000000000000')", lid)
            await conn.execute(
                "DELETE FROM ffa_kept_epochs WHERE lobby_id = $1", lid)
            await conn.execute(
                "DELETE FROM ffa_assembly_seats WHERE lobby_id = $1", lid)
    _run(go())


PSQL = os.environ.get("CF_PSQL", "C:/pg16/pgsql/bin/psql.exe")


def test_355_applies_twice_through_psql():
    """The deploy's migrate verb runs the file through psql -f: run it that
    way too, twice, with ON_ERROR_STOP, on a built case schema that lacks it
    (the search path in the startup packet binds psql to the case schema, as
    the harness binds its own connections)."""
    import subprocess
    cf_pg.require_live_pg()
    assert os.path.exists(PSQL), "psql not found at %s (set CF_PSQL)" % PSQL

    async def go():
        async with cf_pg.case("cf_psql", with_355=False) as (c, sm):
            from urllib.parse import urlparse
            u = urlparse(c.dsn)
            env = dict(os.environ, PGOPTIONS="-c search_path=%s" % c.schema)
            outs = []
            for _ in range(2):
                p = subprocess.run(
                    [PSQL, "-X", "-v", "ON_ERROR_STOP=1", "-h", u.hostname, "-p", str(u.port),
                     "-U", u.username, "-d", u.path.lstrip("/"), "-f", cf_pg.M355],
                    env=env, capture_output=True, text=True, timeout=120)
                outs.append((p.returncode, p.stdout, p.stderr))
            assert outs[0][0] == 0, outs[0]
            assert outs[1][0] == 0, outs[1]
            assert "COMMIT" in outs[0][1] and "COMMIT" in outs[1][1]
            assert await c.conn.fetchval("SELECT to_regclass('ffa_assembly_seats') IS NOT NULL")
            await c.seal()
    _run(go())


# -- The server controls (evidence sec8.1) ------------------------------------
#
# Each test runs in its own case schema through cf_asm.Env (the frozen clocks,
# the route callers, the second-session readers). Every assertion names its
# control in its message ("S1 40.0", ...): cf_controls.py counts a mutant only
# when it turns exactly the named assertion red. Every test ends with the
# standing invariants (evidence V11:2985-3007) and, under CF_TRACE_DIR, writes
# the normalised trace the inert twins are compared against.

import cf_asm  # noqa: E402

SKIP_REFORM = ("reform_rows_left",)


def run_env(monkeypatch, body, prefix="cf_s", skip=SKIP_REFORM, fresh=False):
    """One case: build, run `body(env)`, the standing invariants, the trace.
    fresh=True builds the case in a throwaway database of its own
    (cf_pg.fresh_database), for a check that reads information_schema."""
    cf_pg.require_live_pg()

    async def inside(dsn, faithful):
        async with cf_pg.case(prefix, dsn=dsn, faithful=faithful) as (c, sm):
            env = cf_asm.Env(c, sm, monkeypatch)
            try:
                await body(env)
                inv = await cf_pg.standing_invariants(c.conn, skip=skip)
                assert inv == {k: 0 for k in inv}, ("standing invariants", inv)
                # The node id without its directory: the same name whatever
                # pytest's rootdir (cf_controls.trace_file names it so).
                node = os.environ.get("PYTEST_CURRENT_TEST", "case").split(" ")[0]
                await env.trace(node.rsplit("/", 1)[-1])
            finally:
                env.close()

    async def go():
        if not fresh:
            await inside(None, False)
            return
        if cf_pg.POOL:
            await inside(None, True)
            return
        async with cf_pg.fresh_database() as dsn:
            await inside(dsn, True)
    _run(go())


async def _post(env, lob, slot, ready, **kw):
    """Refresh the READY seats' censuses at the frozen now, then an assembly
    POST from `slot` listing them (a present seat's completed round trip)."""
    await env.ready_all(lob, ready)
    return await env.census_of(lob, slot, ready, **kw)


def test_s1_rule_b_boundary_both_tables(monkeypatch):
    """S1: rule B at 39.9 answers assembling; at 40.0 an admission lobby
    starts short and a fallback lobby re-forms."""
    async def body(env):
        for admission, want in ((True, "start_ok"), (False, "reformed")):
            lob = await env.lobby(5, admission=admission, t=39.9)
            a = await _post(env, lob, 0, [0, 1, 2, 3])
            assert a.status == 200 and a["status"] == "assembling", ("S1 39.9", admission, a)
            await env.at(lob, 40.0)
            a = await _post(env, lob, 0, [0, 1, 2, 3])
            assert a["status"] == want, ("S1 40.0", admission, a)
            assert (await env.lobby_row(lob))["asm_rule"] == "B", ("S1 rule", admission)
    run_env(monkeypatch, body)


def test_s2_attempt_hold_is_table_two_only(monkeypatch):
    """S2: attempt=1 phase=connect at 25 holds rule B at 40 in a fallback
    lobby, and does not in an admission lobby (START-SHORT at 40)."""
    async def body(env):
        for admission, want in ((False, "assembling"), (True, "start_ok")):
            lob = await env.lobby(5, admission=admission, t=25.0)
            await env.ready_all(lob, [0, 1, 2, 3])
            a = await env.connect(lob, 4, "attempt", attempt=1, phase="connect")
            assert a.status == 200 and a["status"] == "assembling", ("S2 attempt", admission, a)
            await env.at(lob, 40.0)
            a = await _post(env, lob, 0, [0, 1, 2, 3])
            assert a["status"] == want, ("S2 hold", admission, a)
    run_env(monkeypatch, body)


def test_s3_rule_e_reads_lock_offered_at_only(monkeypatch):
    """S3: an offered lock with no receipt holds rule E off; a lock never
    offered fires it at 20 whatever the receipt says."""
    async def body(env):
        for admission, decided in ((True, "start_ok"), (False, "reformed")):
            lob = await env.lobby(5, admission=admission, t=20.0)
            a = await _post(env, lob, 0, [0, 1, 2, 3])
            assert a["status"] == "assembling", ("S3 offered", admission, a)
            lob = await env.lobby(5, admission=admission, offered=[0, 1, 2, 3], t=20.0)
            await env.set_seat(lob, 4, lock_seen_at=5.0)
            a = await _post(env, lob, 0, [0, 1, 2, 3])
            assert a["status"] == decided, ("S3 unoffered", admission, a)
            assert (await env.lobby_row(lob))["asm_rule"] == "E", ("S3 rule", admission)
    run_env(monkeypatch, body)


def test_s4_corroboration(monkeypatch):
    """S4: self only is PENDING; self plus one peer entry from the claim's
    region is READY; two peer entries without the seat's own census are
    PENDING (deviation 3); one peer entry alone is PENDING."""
    async def body(env):
        async def case(own, peers):
            lob = await env.lobby(4, t=10.0)
            await env.ready_all(lob, [0, 1, 2])
            if own:
                await env.census_row(lob, 3, [(0, 1, 1, 1), (1, 2, 1, 1), (2, 3, 1, 1),
                                              (3, 4, 1, 1)], claim=4)
            else:
                await env.set_seat(lob, 3, actor_claim=4, claim_region=lob.region)
            for p in peers:
                await env.census_row(lob, p, [(0, 1, 1, 1), (1, 2, 1, 1), (2, 3, 1, 1),
                                              (3, 4, 1, 1)], claim=1 + p, bind=True)
            a = await env.census_of(lob, 0, [0, 1, 2])
            assert a["status"] in ("assembling", "admitted"), ("S4 answer", own, peers, a)
            return a["pending"]
        assert await case(True, []) == 1, "S4 self only"
        assert await case(True, [1]) == 0, "S4 self and one peer"
        assert await case(False, [1, 2]) == 1, "S4 two peers without own"
        assert await case(False, [1]) == 1, "S4 one peer alone"
    run_env(monkeypatch, body)


def test_s18_rule_d_and_d0(monkeypatch):
    """S18: a leave at 8 decides nothing (and a POST at 8 still answers
    assembling); at 20 rule D starts short (admission) or re-forms
    (fallback); with fewer than 3 READY or PENDING at 20, DISSOLVE at once,
    whatever the holds."""
    async def body(env):
        for admission, want in ((True, "start_ok"), (False, "reformed")):
            lob = await env.lobby(5, admission=admission, t=8.0)
            await env.ready_all(lob, [0, 1, 2, 3])
            await env.leave(lob, 4)
            assert (await env.seat(lob, 4))["left_path"] == "kept", ("S18 kept", admission)
            a = await _post(env, lob, 0, [0, 1, 2, 3])
            assert a["status"] == "assembling", ("S18 t8", admission, a)
            await env.at(lob, 20.0)
            a = await _post(env, lob, 0, [0, 1, 2, 3])
            assert a["status"] == want, ("S18 t20", admission, a)
            assert (await env.lobby_row(lob))["asm_rule"] == "D", ("S18 rule", admission)
        # D0: n = 4, one leave at 8 (kept), a PENDING seat holding an attempt,
        # then a second leave at 20 leaves READY + PENDING at 2: DISSOLVE.
        lob = await env.lobby(4, t=8.0)
        await env.ready_all(lob, [0, 1])
        await env.leave(lob, 3)
        await env.at(lob, 15.0)
        await env.ready_all(lob, [0, 1])
        await env.connect(lob, 2, "attempt", attempt=1, phase="connect")
        await env.at(lob, 20.0)
        await env.ready_all(lob, [0, 1])
        await env.leave(lob, 1)
        row = await env.lobby_row(lob)
        assert row["status"] == "canceled" and row["asm_rule"] == "D", \
            ("S18 D0", row["status"], row["asm_rule"])
        assert row["dissolve_path"] == "asm_dissolve", ("S18 D0 path", row["dissolve_path"])
    run_env(monkeypatch, body)


@pytest.mark.parametrize("rule", ["E", "B", "S", "C", "K", "D", "D-floor"])
def test_s22_every_rule_at_its_threshold(monkeypatch, rule):
    """S22: one isolated fixture per rule, each its own node; each answers
    assembling at 19.9 and at its threshold minus 0.1, and decides at its
    threshold; a second D fixture (leave at 8) decides at 20.0, the floor."""
    async def body(env):
        ready = [0, 1, 2, 3]

        async def step(lob, t, want, tag, seed=None):
            await env.at(lob, t)
            if seed is not None:
                await seed(lob)
            a = await _post(env, lob, 0, ready)
            assert a["status"] == want, (tag, t, a)
            return a

        async def adm_hold(lob):
            await env.set_seat(lob, 4, admitted_at=(env.now - await env.ts(lob, 0))
                               .total_seconds() - 1.0, arrived_at=1.0)

        async def att_hold(lob):
            now_t = (env.now - await env.ts(lob, 0)).total_seconds()
            await env.set_seat(lob, 4, attempt=1, attempt_phase="connect",
                               attempt_at=now_t - 1.0, first_attempt_at=now_t - 1.0)
        if rule == "E":
            # E (20): the pending seat was never offered its lock.
            lob = await env.lobby(5, offered=ready, t=19.9)
            await step(lob, 19.9, "assembling", "S22 E 19.9")
            await step(lob, 20.0, "reformed", "S22 E 20.0")
            assert (await env.lobby_row(lob))["asm_rule"] == "E", "S22 E rule"
        elif rule == "B":
            # B (40)
            lob = await env.lobby(5, t=19.9)
            await step(lob, 19.9, "assembling", "S22 B 19.9")
            await step(lob, 39.9, "assembling", "S22 B 39.9")
            await step(lob, 40.0, "reformed", "S22 B 40.0")
            assert (await env.lobby_row(lob))["asm_rule"] == "B", "S22 B rule"
        elif rule == "S":
            # S (46): an admission hold keeps B off; S ignores it.
            lob = await env.lobby(5, admission=True, t=19.9)
            await step(lob, 19.9, "assembling", "S22 S 19.9")
            await step(lob, 45.9, "assembling", "S22 S 45.9", adm_hold)
            await step(lob, 46.0, "start_ok", "S22 S 46.0", adm_hold)
            assert (await env.lobby_row(lob))["asm_rule"] == "S", "S22 S rule"
        elif rule == "C":
            # C (75): an attempt hold keeps B off; C ignores it.
            lob = await env.lobby(5, t=19.9)
            await step(lob, 19.9, "assembling", "S22 C 19.9")
            await step(lob, 74.9, "assembling", "S22 C 74.9", att_hold)
            await step(lob, 75.0, "reformed", "S22 C 75.0", att_hold)
            assert (await env.lobby_row(lob))["asm_rule"] == "C", "S22 C rule"
        elif rule == "K":
            # K (81): an admission hold keeps B and C off; K ignores it.
            lob = await env.lobby(5, t=19.9)
            await step(lob, 19.9, "assembling", "S22 K 19.9")
            await step(lob, 80.9, "assembling", "S22 K 80.9", adm_hold)
            await step(lob, 81.0, "reformed", "S22 K 81.0", adm_hold)
            assert (await env.lobby_row(lob))["asm_rule"] == "K", "S22 K rule"
        elif rule == "D":
            # D at a leave (25): nobody is PENDING before it.
            lob = await env.lobby(5, t=19.9)
            await env.ready_all(lob, [0, 1, 2, 3, 4])
            a = await env.census_of(lob, 0, [0, 1, 2, 3, 4])
            assert a["status"] == "assembling", ("S22 D 19.9", a)
            await env.at(lob, 24.9)
            await env.ready_all(lob, [0, 1, 2, 3, 4])
            a = await env.census_of(lob, 0, [0, 1, 2, 3, 4])
            assert a["status"] == "assembling", ("S22 D 24.9", a)
            await env.at(lob, 25.0)
            await env.ready_all(lob, [0, 1, 2, 3])
            await env.leave(lob, 4)
            row = await env.lobby_row(lob)
            assert row["asm_rule"] == "D" and row["reformed_to"] is not None, \
                ("S22 D 25.0", row["asm_rule"], row["status"])
        else:
            # D at the floor: a leave at 8 decides at 20.0 and not at 19.9.
            lob = await env.lobby(5, t=8.0)
            await env.ready_all(lob, [0, 1, 2, 3])
            await env.leave(lob, 4)
            await step(lob, 19.9, "assembling", "S22 D-floor 19.9")
            await step(lob, 20.0, "reformed", "S22 D-floor 20.0")
            assert (await env.lobby_row(lob))["asm_rule"] == "D", "S22 D-floor rule"
    run_env(monkeypatch, body)


def test_s39_rule_s_ignores_the_admission_hold(monkeypatch):
    """S39: an admission lobby with an admission hold answers assembling at
    45.9 and starts short at 46.0 whatever the holds say."""
    async def body(env):
        lob = await env.lobby(5, admission=True, t=45.9)
        await env.set_seat(lob, 4, arrived_at=45.5, admitted_at=45.5)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "assembling", ("S39 45.9", a)
        await env.at(lob, 46.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "start_ok", ("S39 46.0", a)
        assert (await env.lobby_row(lob))["asm_rule"] == "S", "S39 rule"
    run_env(monkeypatch, body)


import main  # noqa: E402


async def _blocker(env, lob, clause="FOR NO KEY UPDATE"):
    """A second session holding the lobby row lock, open until released."""
    conn = await cf_pg.harness.connect_bound(env.c.dsn, env.c.schema)
    tr = conn.transaction()
    await tr.start()
    await conn.execute("SELECT 1 FROM ffa_lobbies WHERE id = $1 " + clause, lob.lid)
    bpid = await conn.fetchval("SELECT pg_backend_pid()")
    return conn, tr, bpid


async def _waiting_on(env, bpid, tries=60, rel=None):
    """How many backends pg_locks shows waiting on the blocker's locks. With
    `rel`, only a waiter that holds the tuple lock on a row of that table
    (the lock a row-lock waiter takes to queue for the row) is counted, so a
    wait on some other row of the transaction's does not satisfy the probe."""
    n = 0
    for _ in range(tries):
        if rel is None:
            n = await env.conn.fetchval(
                "SELECT count(*) FROM pg_stat_activity WHERE $1 = ANY(pg_blocking_pids(pid))",
                bpid)
        else:
            n = await env.conn.fetchval(
                "SELECT count(DISTINCT a.pid) FROM pg_stat_activity a"
                "  JOIN pg_locks l ON l.pid = a.pid AND l.locktype = 'tuple' AND l.granted"
                "   AND l.relation = to_regclass($2)"
                " WHERE $1 = ANY(pg_blocking_pids(a.pid))", bpid, rel)
        if n:
            return n
        await asyncio.sleep(0.02)
    return n


def test_s5_ungated_leave_is_todays_dissolve(monkeypatch):
    """S5: an ungated lobby's leave at t >= 20 is today's dissolve, row for row
    in today's tables; a gated leave with 4 READY at t >= 20 starts short
    (admission) or re-forms (fallback)."""
    async def body(env):
        lob = await env.lobby(5, gated=False, t=25.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        a = await env.leave(lob, 4)
        assert a.status == 200, ("S5 ungated answer", a)
        row = await env.lobby_row(lob)
        assert (row["status"], row["invalidation_reason"]) == ("canceled", "assembly_timeout"), \
            ("S5 ungated", row["status"], row["invalidation_reason"])
        assert row["asm_rule"] is None and row["reformed_to"] is None, ("S5 ungated rule", row)
        assert row["dissolve_path"] == "leave_dissolve", ("S5 ungated record", row["dissolve_path"])
        for s in range(4):
            q = await env.queue_row(lob, s)
            assert q is not None and (q["status"], q["series_id"], q["slot"], q["room_name"]) == \
                ("searching", None, None, None), ("S5 ungated survivor", s, q)
        assert await env.queue_row(lob, 4) is None, "S5 ungated leaver row"
        assert await env.lease(lob, 4) is None, "S5 ungated leaver lease"
        for admission, want in ((True, True), (False, False)):
            lob = await env.lobby(5, admission=admission, t=25.0)
            await env.ready_all(lob, [0, 1, 2, 3])
            await env.leave(lob, 4)
            row = await env.lobby_row(lob)
            if want:
                assert row["status"] == "active" and row["short_started_at"] is not None, \
                    ("S5 gated short", row["status"])
            else:
                assert row["status"] == "canceled" and row["reformed_to"] is not None, \
                    ("S5 gated reform", row["status"], row["reformed_to"])
            assert row["asm_rule"] == "D", ("S5 gated rule", admission, row["asm_rule"])
    run_env(monkeypatch, body)


def test_s6_answers_and_the_lobby_lock(monkeypatch):
    """S6: admitted, admitting, excluded and wrong_region answers; an arrived
    waits while a second session holds the URL lobby's row lock."""
    async def body(env):
        lob = await env.lobby(5, t=10.0)
        await env.ready_all(lob, [0, 1, 2])
        a = await env.connect(lob, 3, "arrived", region=lob.region, actor=4, count=4)
        assert a["status"] == "admitted", ("S6 admitted", a)
        lob = await env.lobby(5, admission=True, t=40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "start_ok", ("S6 start", a)
        a = await env.connect(lob, 4, "arrived", region=lob.region, actor=5, count=5)
        assert a["status"] == "admitting", ("S6 admitting", a)
        lob = await env.lobby(5, t=40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "reformed", ("S6 reform", a)
        a = await env.connect(lob, 4, "arrived", region=lob.region, actor=5, count=5)
        assert a["status"] == "excluded", ("S6 excluded", a)
        env.mp.setattr(main, "JOIN_REGION_GUARD", True)
        lob = await env.lobby(5, t=10.0)
        a = await env.connect(lob, 3, "arrived", region="us", actor=4, count=4)
        assert a["status"] == "wrong_region", ("S6 wrong_region", a)
        env.mp.setattr(main, "JOIN_REGION_GUARD", False)
        lob = await env.lobby(5, t=10.0)
        await env.ready_all(lob, [0, 1, 2])
        conn, tr, bpid = await _blocker(env, lob)
        try:
            task = asyncio.ensure_future(
                env.connect(lob, 3, "arrived", region=lob.region, actor=4, count=4))
            n = await _waiting_on(env, bpid)
            assert n >= 1 and not task.done(), ("S6 blocks", n, task.done())
        finally:
            await tr.commit()
            await conn.close()
        a = await task
        assert a["status"] == "admitted", ("S6 after the lock", a)
    run_env(monkeypatch, body)


def test_s8_rule_c_honours_the_admission_hold_and_k_does_not(monkeypatch):
    """S8: with admitted_at 70 and an attempt at 70, 75.0 is assembling and
    76.1 re-forms (C); with admitted_at 74.9, 80.9 is assembling and 81.0
    re-forms; a hold still active at 81.0 does not stop K; a granted seat is
    answered from its seat row at every t."""
    async def body(env):
        lob = await env.lobby(5, t=75.0)
        await env.set_seat(lob, 4, arrived_at=70.0, admitted_at=70.0, attempt=1,
                           attempt_phase="connect", attempt_at=70.0, first_attempt_at=70.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "assembling", ("S8 C 75.0", a)
        await env.at(lob, 76.1)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "reformed", ("S8 C 76.1", a)
        assert (await env.lobby_row(lob))["asm_rule"] == "C", "S8 C rule"
        lob = await env.lobby(5, t=80.9)
        await env.set_seat(lob, 4, arrived_at=74.9, admitted_at=74.9)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "assembling", ("S8 K 80.9", a)
        await env.at(lob, 81.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "reformed", ("S8 K 81.0", a)
        lob = await env.lobby(5, t=81.0)
        await env.set_seat(lob, 4, arrived_at=76.0, admitted_at=76.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "reformed", ("S8 K 81.0 held", a)
        assert (await env.lobby_row(lob))["asm_rule"] == "K", "S8 K held rule"
        lob = await env.lobby(5, admission=True, t=40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "start_ok", ("S8 grant", a)
        for t in (75.0, 76.1, 80.9, 81.0):
            await env.at(lob, t)
            await env.set_seat(lob, 4, arrived_at=t - 1.0, admitted_at=t - 1.0)
            a = await _post(env, lob, 1, [0, 1, 2, 3])
            assert a["status"] == "start_ok", ("S8 seat row", t, a)
    run_env(monkeypatch, body)


def test_s9_labels_cannot_change_a_decision(monkeypatch):
    """S9: cause "" with label in_room_exit takes the gated pre-room path;
    cause in_room_exit with label menu_leave takes the departure path; the
    verdict reads no label."""
    import inspect
    src = inspect.getsource(main._ffa_assembly_verdict)
    assert src.count("left_label") == 0 and src.count("first_leave_label") == 0, \
        "S9 verdict reads a label"

    async def body(env):
        lob = await env.lobby(5, t=8.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        await env.leave(lob, 4, cause="", label="in_room_exit")
        s = await env.seat(lob, 4)
        row = await env.lobby_row(lob)
        assert s["left_path"] == "kept" and not row["departed_ids"], \
            ("S9 pre-room", s["left_path"], row["departed_ids"])
        assert s["left_label"] == "unlabelled" and s["left_cause"] is None, \
            ("S9 receipts", s["left_label"], s["left_cause"])
        lob = await env.lobby(5, t=8.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        await env.leave(lob, 4, cause="in_room_exit", label="menu_leave")
        s = await env.seat(lob, 4)
        row = await env.lobby_row(lob)
        assert s["left_path"] == "departure" and list(row["departed_ids"]) == [lob.pids[4]], \
            ("S9 departure", s["left_path"], row["departed_ids"])
        assert row["status"] == "active", ("S9 departure keeps", row["status"])
    run_env(monkeypatch, body)


def test_s14_the_writes_cap(monkeypatch):
    """S14: after 170 accepted writes the next answers 429 and changes
    nothing; 167 writes (58 connect, 109 assembly) are accepted in full."""
    async def body(env):
        lob = await env.lobby(10, t=10.0)
        await env.ready_all(lob, list(range(10)))
        for i in range(58):
            a = await env.connect(lob, 1, ("lock_seen", "countdown", "notice_seen")[i % 3])
            assert a.status == 200, ("S14 167", "connect", i, a)
        for i in range(109):
            a = await env.census_of(lob, 1, list(range(10)))
            assert a.status == 200, ("S14 167", "assembly", i, a)
        assert (await env.seat(lob, 1))["writes"] == 167, "S14 167 count"
        lob = await env.lobby(5, t=10.0)
        await env.set_seat(lob, 0, writes=169)
        a = await env.connect(lob, 0, "lock_seen")
        assert a.status == 200, ("S14 170th", a)
        before = await env.seat(lob, 0)
        a = await env.connect(lob, 0, "countdown")
        after = await env.seat(lob, 0)
        assert a.status == 429 and after == before, ("S14 cap", a.status, after["writes"])
    run_env(monkeypatch, body)


def test_s16_the_attempt_hold(monkeypatch):
    """S16: (i) an attempt at 25 holds B at 40; (ii) the same attempt's
    refresh moves attempt_at; (iii) a late lower attempt does not; (iv)
    attempt=0 is a 422 with no write."""
    async def body(env):
        lob = await env.lobby(5, t=25.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        await env.connect(lob, 4, "attempt", attempt=1, phase="connect")
        await env.at(lob, 40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "assembling", ("S16 i", a)
        lob = await env.lobby(5, t=8.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        await env.connect(lob, 4, "attempt", attempt=1, phase="leave")
        await env.at(lob, 25.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        await env.connect(lob, 4, "attempt", attempt=1, phase="connect")
        s = await env.seat(lob, 4)
        assert s["attempt_at"] == await env.ts(lob, 25.0) and s["attempt_phase"] == "connect", \
            ("S16 ii refresh", s["attempt_at"], s["attempt_phase"])
        await env.at(lob, 40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "assembling", ("S16 ii hold", a)
        lob = await env.lobby(5, t=30.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        await env.connect(lob, 4, "attempt", attempt=2, phase="connect")
        await env.at(lob, 33.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        await env.connect(lob, 4, "attempt", attempt=1, phase="connect")
        s = await env.seat(lob, 4)
        assert s["attempt_at"] == await env.ts(lob, 30.0) and s["attempt"] == 2, \
            ("S16 iii", s["attempt_at"], s["attempt"])
        before = await env.seat(lob, 4)
        a = await env.connect(lob, 4, "attempt", attempt=0, phase="connect")
        assert a.status == 422 and await env.seat(lob, 4) == before, ("S16 iv", a)
    run_env(monkeypatch, body)


def test_s17_the_reform_aware_fence(monkeypatch):
    """S17: a leave naming the old lobby from a seat carried into L' deletes
    its L' row and lease and runs L''s gated leave as pre-room even with
    cause=in_room_exit; an unrelated lobby still answers membership moved on."""
    async def body(env):
        lob = await env.lobby(5, t=40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "reformed", ("S17 reform", a)
        new = (await env.lobby_row(lob))["reformed_to"]
        assert (await env.queue_row(lob, 1))["series_id"] == new, "S17 carried"
        lease = await env.lease(lob, 1)
        assert lease is not None and lease["group_id"] == new, ("S17 lease", lease)
        a = await env.leave(lob, 1, cause="in_room_exit", expected=str(lob.lid))
        assert a.status == 200 and a.get("note") is None, ("S17 hop answer", a)
        assert await env.queue_row(lob, 1) is None, "S17 L' row"
        assert await env.lease(lob, 1) is None, "S17 L' lease"
        s = await env.conn.fetchrow(
            "SELECT left_path, left_cause, verdict FROM ffa_assembly_seats"
            " WHERE lobby_id = $1 AND player_id = $2", new, lob.pids[1])
        assert s["left_path"] == "kept" and s["verdict"] == "left", \
            ("S17 pre-room", s["left_path"], s["verdict"])
        nrow = await env.lobby_row(new)
        assert nrow["status"] == "active" and not nrow["departed_ids"], \
            ("S17 L' kept", nrow["status"], nrow["departed_ids"])
        a = await env.leave(lob, 2, cause="", expected=str(uuid.uuid4()))
        assert a.get("note") == "membership moved on", ("S17 unrelated", a)
        assert (await env.queue_row(lob, 2))["series_id"] == new, "S17 unrelated kept"
    run_env(monkeypatch, body)


def test_s19_join_region_guard_gates_the_region_answer(monkeypatch):
    """S19: with JOIN_REGION_GUARD false a foreign-region arrival is admitted
    (its wrong_region column recorded); with it true, wrong_region."""
    async def body(env):
        assert main.JOIN_REGION_GUARD is False, "S19 constant"
        lob = await env.lobby(5, t=10.0)
        a = await env.connect(lob, 3, "arrived", region="us", actor=4, count=4)
        s = await env.seat(lob, 3)
        assert a["status"] == "admitted" and s["arrived_at"] is not None, ("S19 off", a)
        assert s["wrong_region"] == "us" and s["wrong_region_n"] == 0, \
            ("S19 off column", s["wrong_region"], s["wrong_region_n"])
        env.mp.setattr(main, "JOIN_REGION_GUARD", True)
        lob = await env.lobby(5, t=10.0)
        a = await env.connect(lob, 3, "arrived", region="us", actor=4, count=4)
        s = await env.seat(lob, 3)
        assert a["status"] == "wrong_region" and s["arrived_at"] is None, ("S19 on", a)
        assert s["wrong_region_n"] == 1, ("S19 on column", s["wrong_region_n"])
    run_env(monkeypatch, body)


def test_s20_writer_2_commits(monkeypatch):
    """S20: one ready_join poll commits lock_offered_at; after A, the same
    poll's expiry commits before it answers not_in_queue."""
    async def body(env):
        lob = await env.lobby(5, offered=[0, 1, 3, 4], t=5.0)
        assert (await env.seat(lob, 2))["lock_offered_at"] is None, "S20 fixture"
        a = await env.poll(lob, 2)
        assert a.status == 200, ("S20 poll", a)
        assert (await env.seat(lob, 2))["lock_offered_at"] is not None, "S20 offered"
        lob = await env.lobby(5, admission=True, t=40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "start_ok", ("S20 start", a)
        assert (await env.seat(lob, 4))["verdict"] == "admissible", "S20 admissible"
        await env.at(lob, 140.0)
        a = await env.poll(lob, 4)
        # The committed state first: an expiry that ran but never committed
        # is what "S20 expiry" names; the answer it would have produced is
        # checked after.
        s = await env.seat(lob, 4)
        row = await env.lobby_row(lob)
        assert s["verdict"] == "excluded" and await env.queue_row(lob, 4) is None, \
            ("S20 expiry", s["verdict"])
        assert list(row["departed_ids"]) == [lob.pids[4]], ("S20 departed", row["departed_ids"])
        assert a.get("status") == "not_in_queue", ("S20 answer", a)
    run_env(monkeypatch, body)


import hashlib  # noqa: E402
import hmac as _hmac  # noqa: E402
import importlib.util  # noqa: E402
import re as _re  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402

BASE_COMMIT = "9a1dd9d"
_BET_SECRET = "cf-bet-secret"


def _sig(msg):
    return _hmac.new(_BET_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _new_lobby_columns():
    """The ffa_lobbies columns migration 355 adds."""
    return set(_re.findall(r"ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS\s+(\w+)",
                           cf_pg.read_355()))


_PRE = {}


def _pre_refactor_main():
    """main.py as the lane's base commit left it, imported as module
    main_pre (CF_PRE_MAIN names a copy when git is not reachable)."""
    if "mod" in _PRE:
        return _PRE["mod"]
    path = os.environ.get("CF_PRE_MAIN")
    if not path:
        repo = os.path.normpath(os.path.join(HERE, "..", ".."))
        src = subprocess.run(["git", "-C", repo, "show", BASE_COMMIT + ":backend/api/main.py"],
                             capture_output=True, check=True).stdout
        d = tempfile.mkdtemp(prefix="cf_pre_")
        path = os.path.join(d, "main_pre.py")
        with open(path, "wb") as fh:
            fh.write(src)
    spec = importlib.util.spec_from_file_location("main_pre", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _PRE["mod"] = mod
    return mod


async def _open_lobby(env, n, caps):
    """An open hosted lobby of n fresh members (queue rows status 'lobby'),
    slot 0 hosting."""
    env.serial += 1
    base = cf_asm.STEAM_BASE + env.serial * 20
    sids = [str(base + i) for i in range(n)]
    pids = []
    for i, sid in enumerate(sids):
        pids.append(await env.conn.fetchval(
            "INSERT INTO players (id, steam_id, display_name, mod_version)"
            " VALUES ($3, $1, $2, '1.41.0') RETURNING id", sid, "cf o%d-%d" % (env.serial, i),
            cf_asm.fixture_uuid("player", sid)))
    lid = cf_asm.fixture_uuid("lobby", env.serial)
    await env.conn.execute(
        "INSERT INTO ffa_lobbies (id, status, host_player_id, created_at, is_ranked,"
        "  player_count, member_ids) VALUES ($1, 'open', $2, clock_timestamp() - interval"
        " '5 minutes', TRUE, 0, '{}')", lid, pids[0])
    for i in range(n):
        await env.conn.execute(
            "INSERT INTO ffa_queue (player_id, steam_id, display_name, status, series_id,"
            "  joined_at, last_polled, caps, mod_version)"
            " VALUES ($1, $2, $3, 'lobby', $4, clock_timestamp() - make_interval(secs => $5),"
            "         clock_timestamp(), $6, '1.41.0')",
            pids[i], sids[i], "cf o%d-%d" % (env.serial, i), lid, float(300 - i), caps[i])
    lob = cf_asm.Lob(lid, sids, pids, None, False, True)
    env.lobbies.append(lob)
    return lob


async def _start(env, module, lob):
    req = module._FfaLobbyStartReq(steam_id=lob.sids[0])

    async def go():
        async with env.sm() as db:
            return await module.ffa_lobby_start(req, None, db=db)
    return await env._call(go)


def _anon(obj, names):
    if isinstance(obj, dict):
        return {k: _anon(v, names) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_anon(v, names) for v in obj]
    if isinstance(obj, str):
        for k, v in names.items():
            obj = obj.replace(k, v)
    return obj


async def _lobby_shape(env, lob):
    """One started lobby's rows in today's tables, normalised on their own:
    its members' steam ids, names and its room become placeholders."""
    row = await env.lobby_row(lob)
    q = [dict(r) for r in await env.conn.fetch(
        "SELECT * FROM ffa_queue WHERE series_id = $1 ORDER BY slot", lob.lid)]
    lz = [dict(r) for r in await env.conn.fetch(
        "SELECT l.mode, l.group_id, q.slot FROM queue_leases l JOIN ffa_queue q"
        "  ON q.player_id = l.player_id WHERE q.series_id = $1 ORDER BY q.slot", lob.lid)]
    names = {}
    for i, sid in enumerate(lob.sids):
        names[sid] = "SID%d" % i
    for r in q:
        if r.get("display_name"):
            names[r["display_name"]] = "NAME%d" % lob.sids.index(r["steam_id"])
    if row.get("photon_room_id"):
        names[row["photon_room_id"]] = "ROOM"
    return cf_asm.normalise(_anon({"lobby": row, "queue": q, "leases": lz}, names))


def test_s10_the_start_refactor_is_equivalent(monkeypatch):
    """S10: one Start through _ffa_lock_roster leaves the same rows in today's
    tables as the base commit's Start on the same fixture, apart from the new
    columns; created_at is the activation time; the host's seat row is offered
    at insert and no other; assembly_v1 and admission_v1 follow the caps."""
    pre = _pre_refactor_main()

    async def no_session(request, steam_id, db):
        return None
    monkeypatch.setattr(pre, "_check_steam_session", no_session)
    new_cols = _new_lobby_columns()
    assert {"assembly_v1", "admission_v1", "bets_disabled"} <= new_cols, ("S10 columns", new_cols)

    async def body(env):
        both = ["ffa_asm1,ffa_adm1"] * 5
        old = await _open_lobby(env, 5, both)
        a = await _start(env, pre, old)
        assert a.status == 200, ("S10 base start", a)
        new = await _open_lobby(env, 5, both)
        before = await env.conn.fetchval("SELECT clock_timestamp()")
        a = await _start(env, main, new)
        assert a.status == 200, ("S10 start", a)
        want = await _lobby_shape(env, old)
        got = await _lobby_shape(env, new)
        for k in new_cols:
            want["lobby"].pop(k, None)
            got["lobby"].pop(k, None)
        assert got == want, ("S10 golden", got, want)
        row = await env.lobby_row(new)
        assert row["created_at"] >= before, ("S10 created_at", row["created_at"], before)
        seats = await env.seats(new)
        host = [s for s in seats if s["player_id"] == new.pids[0]]
        assert len(host) == 1 and host[0]["lock_offered_at"] is not None, "S10 host offered"
        assert all(s["lock_offered_at"] is None for s in seats
                   if s["player_id"] != new.pids[0]), "S10 others not offered"
        assert (row["assembly_v1"], row["admission_v1"]) == (True, False), \
            ("S10 gates unenrolled", row["assembly_v1"], row["admission_v1"])
        for caps, want_gates in (
                (both, (True, True)),
                (["ffa_asm1,ffa_adm1"] * 4 + ["ffa_asm1"], (True, False)),
                (["ffa_asm1,ffa_adm1"] * 4 + ["ffa_adm1"], (False, False))):
            lob = await _open_lobby(env, 5, caps)
            for pid in lob.pids:
                await env.conn.execute(
                    "INSERT INTO ffa_g3_seats (player_id, expires_at)"
                    " VALUES ($1, now() + interval '1 hour')", pid)
            a = await _start(env, main, lob)
            assert a.status == 200, ("S10 gate start", a)
            row = await env.lobby_row(lob)
            assert (row["assembly_v1"], row["admission_v1"]) == want_gates, \
                ("S10 gates", caps, row["assembly_v1"], row["admission_v1"])
    run_env(monkeypatch, body)


async def _bound_lobby_bet(env, lob, bettor_pid, on_slot, bet_id):
    await env.conn.execute(
        "INSERT INTO lobby_bets (mode, lobby_id, player_id, amount, target_steams, status,"
        "  bound_bet_id, resolved_at, resolve_reason)"
        " VALUES ('ffa', $1, $2, 100, $3, 'bound', $4, now(), 'bound')",
        lob.lid, bettor_pid, lob.sids[on_slot], bet_id)


def test_s7_reform_carries_wagers_and_refunds_none(monkeypatch):
    """S7: a REFORM moves every unsettled wager to L' unchanged and refunds
    none; L''s game 1 settles them, the one on the excluded seat lost; in the
    other fixture a DISSOLVE of L' before any game refunds them there, and not
    before."""
    async def body(env):
        for dissolve in (False, True):
            lob = await env.lobby(5, t=39.9)
            b1, _ = await env.bettor()
            b2, _ = await env.bettor()
            b3, _ = await env.bettor()
            w1 = await env.wager(lob, b1, lob.pids[0])
            w2 = await env.wager(lob, b2, lob.pids[4])
            w3 = await env.wager(lob, b3, lob.pids[1])
            await _bound_lobby_bet(env, lob, b3, 1, w3)
            snap = {b["id"]: b for b in await env.bets(lob)}
            await env.at(lob, 40.0)
            a = await _post(env, lob, 0, [0, 1, 2, 3])
            assert a["status"] == "reformed", ("S7 reform", a)
            new = (await env.lobby_row(lob))["reformed_to"]
            moved = {b["id"]: b for b in await env.bets(new)}
            assert set(moved) == {w1, w2, w3}, ("S7 carried", sorted(map(str, moved)))
            for bid, b in moved.items():
                was = dict(snap[bid])
                was["lobby_id"] = new
                assert b == was, ("S7 unchanged", bid, b, was)
            assert await env.refunds(lob) == 0, "S7 no refund"
            assert await env.conn.fetchval(
                "SELECT count(*) FROM lobby_bets WHERE lobby_id = $1", new) == 0, "S7 lobby_bets"
            if not dissolve:
                res = {lob.sids[0]: (5, 10), lob.sids[1]: (3, 6), lob.sids[2]: (2, 4),
                       lob.sids[3]: (1, 2)}
                a = await env.report(new, 1, res)
                assert a.status == 200, ("S7 report", a)
                after = {b["id"]: b for b in await env.bets(new)}
                assert all(b["settled_at"] is not None for b in after.values()), \
                    ("S7 settled", after)
                assert after[w2]["payout"] == 0 and after[w2]["settlement_kind"] == "lost", \
                    ("S7 excluded seat lost", after[w2])
                assert after[w1]["payout"] > 0, ("S7 winner paid", after[w1])
                assert await env.refunds(new) == 0, "S7 no refund at the report"
            else:
                nlob = cf_asm.Lob(new, lob.sids[:4], lob.pids[:4], lob.region, False, True)
                await env.at(nlob, 25.0)
                await env.ready_all(nlob, [0, 1])
                assert all(b["settled_at"] is None for b in await env.bets(new)), \
                    "S7 not before"
                assert await env.refunds(new) == 0, "S7 no refund before"
                await env.leave(nlob, 3)
                nrow = await env.lobby_row(new)
                assert nrow["status"] == "canceled" and nrow["asm_rule"] is not None, \
                    ("S7 dissolve", nrow["status"], nrow["asm_rule"])
                after = await env.bets(new)
                assert len(after) == 3 and all(
                    b["settled_at"] is not None and b["payout"] == b["amount"] for b in after), \
                    ("S7 refunded", [(b["settled_at"] is not None, b["payout"], b["amount"],
                                      b["settlement_kind"], b["id"] == w3) for b in after],
                     [ln for ln in env.lines if "BETS" in ln or "ASM" in ln][-12:])
                assert await env.refunds(new) == 3, ("S7 refund rows", await env.refunds(new))
    run_env(monkeypatch, body)


def test_s12_start_short_is_one_transaction_and_refunds_none(monkeypatch):
    """S12: a fault injected after START-SHORT's writes, before the COMMIT,
    leaves no grant, no verdict, departed_ids unchanged and the wagers
    unsettled; a clean START-SHORT leaves every wager unchanged and writes no
    refund."""
    async def body(env):
        orig = main._asm_decision_record
        for fault in (True, False):
            lob = await env.lobby(6, admission=True, t=40.0)
            await env.conn.execute("DELETE FROM ffa_queue WHERE player_id = $1", lob.pids[5])
            b1, _ = await env.bettor()
            await env.wager(lob, b1, lob.pids[0])
            snap = await env.bets(lob)
            if fault:
                async def boom(ctx):
                    raise RuntimeError("cf fault after START-SHORT")
                env.mp.setattr(main, "_asm_decision_record", boom)
                await env.ready_all(lob, [0, 1, 2, 3])
                try:
                    await env.census_of(lob, 0, [0, 1, 2, 3])
                    raised = False
                except RuntimeError:
                    raised = True
                finally:
                    env.mp.setattr(main, "_asm_decision_record", orig)
                assert raised, "S12 fault raised"
                row = await env.lobby_row(lob)
                assert row["start_granted_at"] is None and row["short_started_at"] is None, \
                    ("S12 fault", row["start_granted_at"])
                assert all(s["verdict"] is None for s in await env.seats(lob)), \
                    "S12 fault verdicts"
                assert not row["departed_ids"], ("S12 fault departed", row["departed_ids"])
                assert await env.bets(lob) == snap, "S12 fault wagers"
            else:
                a = await _post(env, lob, 0, [0, 1, 2, 3])
                assert a["status"] == "start_ok", ("S12 clean", a)
                row = await env.lobby_row(lob)
                assert list(row["departed_ids"]) == [lob.pids[5]], \
                    ("S12 clean departed", row["departed_ids"])
                assert await env.bets(lob) == snap, "S12 clean wagers"
                assert await env.refunds(lob) == 0, "S12 clean refunds"
    run_env(monkeypatch, body)


def test_s12b_reform_is_one_transaction(monkeypatch):
    """S12b: with the carry patched to raise, the old lobby stays active, no
    row names it in reformed_from, every carried queue row still names it,
    and every wager still names it, unsettled."""
    from sqlalchemy import event as _event

    async def body(env):
        lob = await env.lobby(5, t=40.0)
        b1, _ = await env.bettor()
        await env.wager(lob, b1, lob.pids[0])

        def carry_fault(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().startswith("UPDATE ffa_bets SET lobby_id"):
                raise RuntimeError("cf fault at the carry")
        _event.listen(env.engine.sync_engine, "before_cursor_execute", carry_fault)
        try:
            await env.ready_all(lob, [0, 1, 2, 3])
            try:
                await env.census_of(lob, 0, [0, 1, 2, 3])
                raised = False
            except Exception:
                raised = True
        finally:
            _event.remove(env.engine.sync_engine, "before_cursor_execute", carry_fault)
        assert raised, "S12b fault raised"
        row = await env.lobby_row(lob)
        assert row["status"] == "active" and row["reformed_to"] is None, \
            ("S12b old lobby", row["status"])
        assert await env.conn.fetchval(
            "SELECT count(*) FROM ffa_lobbies WHERE reformed_from = $1", lob.lid) == 0, "S12b no L'"
        for s in range(5):
            assert (await env.queue_row(lob, s))["series_id"] == lob.lid, ("S12b queue", s)
        assert all(b["lobby_id"] == lob.lid and b["settled_at"] is None
                   for b in await env.bets(lob)), "S12b wagers"
    run_env(monkeypatch, body)


def test_s15_the_seat_row_answer(monkeypatch):
    """S15: admissible after START-SHORT answers admitting twice; a present
    seat's POST to a lobby its absent seat's leave re-formed answers reformed
    with L''s room and offers it; after a DISSOLVE, dissolved; after today's
    dissolve under a veto an arrived answers dissolved; an admissible or
    admitted_late seat of a lobby since closed reads dissolved."""
    async def body(env):
        lob = await env.lobby(5, admission=True, t=40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "start_ok", ("S15 start", a)
        for _ in range(2):
            a = await env.census_of(lob, 4, [0, 1, 2, 3, 4])
            assert a["status"] == "admitting" and "admit_left_ms" in a.body, ("S15 admitting", a)
        lob = await env.lobby(5, t=25.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        await env.leave(lob, 4)
        row = await env.lobby_row(lob)
        assert row["reformed_to"] is not None, ("S15 leave reform", row["status"])
        new = await env.lobby_row(row["reformed_to"])
        a = await env.census_of(lob, 1, [0, 1, 2, 3])
        assert a["status"] == "reformed" and isinstance(a["lock"], dict) \
            and a["lock"].get("room_name") == new["photon_room_id"], ("S15 reformed", a)
        off = await env.conn.fetchval(
            "SELECT lock_offered_at FROM ffa_assembly_seats WHERE lobby_id = $1 AND player_id = $2",
            new["id"], lob.pids[1])
        assert off is not None, "S15 L' offered"
        lob = await env.lobby(4, t=20.0)
        await env.ready_all(lob, [0, 1])
        await env.set_seat(lob, 3, left_at=8.0, verdict="left", verdict_at=8.0)
        await env.conn.execute("DELETE FROM ffa_queue WHERE player_id = $1", lob.pids[3])
        a = await env.census_of(lob, 0, [0, 1])
        assert (await env.lobby_row(lob))["status"] == "canceled", ("S15 dissolve", a)
        a = await env.census_of(lob, 1, [0, 1])
        assert a["status"] == "dissolved", ("S15 dissolved", a)
        lob = await env.lobby(5, t=25.0)
        await env.leave(lob, 4)
        row = await env.lobby_row(lob)
        assert row["status"] == "canceled" and row["asm_rule"] is None, \
            ("S15 veto dissolve", row["status"], row["asm_rule"])
        a = await env.connect(lob, 1, "arrived", region=lob.region, actor=2, count=5)
        assert a["status"] == "dissolved", ("S15 veto answer", a)
        lob = await env.lobby(6, admission=True, t=40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "start_ok", ("S15 closed start", a)
        await env.set_seat(lob, 5, verdict="admitted_late", late_admitted_at=40.0, late_game=1,
                           actor_nr=6, actor_region=lob.region)
        await env.conn.execute(
            "INSERT INTO ffa_kept_epochs (lobby_id, epoch_no, slot, actor_nr, chain)"
            " VALUES ($1, 1, 5, 6, '0000000000000000')", lob.lid)
        await env.set_lobby(lob, status="completed")
        for s in (4, 5):
            a = await env.connect(lob, s, "lock_seen")
            assert a["status"] == "dissolved", ("S15 closed", s, a)
    run_env(monkeypatch, body)


def test_s21_grant_and_verdict_exclude_each_other(monkeypatch):
    """S21 (i)-(vi)."""
    async def body(env):
        # (i) a full grant, then a census at 55 answers start_ok; nothing closes.
        lob = await env.lobby(5, t=30.0)
        await env.ready_all(lob, [0, 1, 2, 3, 4])
        a = await env.connect(lob, 0, "start")
        assert a["status"] == "start_ok", ("S21 i grant", a)
        await env.at(lob, 55.0)
        a = await _post(env, lob, 1, [0, 1, 2, 3, 4])
        row = await env.lobby_row(lob)
        assert a["status"] == "start_ok" and row["status"] == "active", ("S21 i", a)
        # (ii) a second START-SHORT updates nothing.
        lob = await env.lobby(5, admission=True, t=40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "start_ok", ("S21 ii first", a)

        async def again():
            async with env.sm() as db:
                ctx = await main._asm_ctx_slot(db, lob.lid, route="assembly", trigger="assembly")
                cls = {p["player_id"]: "READY" for p in ctx.seats}
                done = await main._asm_start_short(ctx, "B", cls)
                await db.commit()
                return done
        assert await again() is False, "S21 ii second"
        # (iii) after a REFORM a carried seat's start answers reformed, an
        # excluded seat's excluded, and no grant is written.
        lob = await env.lobby(5, t=40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "reformed", ("S21 iii reform", a)
        a = await env.connect(lob, 1, "start")
        b = await env.connect(lob, 4, "start")
        row = await env.lobby_row(lob)
        new = await env.lobby_row(row["reformed_to"])
        assert a["status"] == "reformed" and b["status"] == "excluded", ("S21 iii", a, b)
        assert row["start_granted_at"] is None and new["start_granted_at"] is None, \
            "S21 iii no grant"
        # (iv) a start waits on a second session holding the lobby row, then
        # answers from the seat row that session wrote.
        lob = await env.lobby(5, t=30.0)
        await env.ready_all(lob, [0, 1, 2, 3, 4])
        conn, tr, bpid = await _blocker(env, lob)
        try:
            await conn.execute("UPDATE ffa_lobbies SET start_granted_at = now() WHERE id = $1",
                               lob.lid)
            await conn.execute(
                "UPDATE ffa_assembly_seats SET verdict = 'granted', start_roster = TRUE,"
                "  verdict_at = now() WHERE lobby_id = $1", lob.lid)
            task = asyncio.ensure_future(env.connect(lob, 2, "start"))
            n = await _waiting_on(env, bpid)
            assert n >= 1 and not task.done(), ("S21 iv blocks", n)
        finally:
            await tr.commit()
            await conn.close()
        a = await task
        assert a["status"] == "start_ok", ("S21 iv answer", a)
        # (v) function level: a granted lobby whose rows would meet S and D.
        lob = await env.lobby(6, admission=True, t=50.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        await env.set_lobby(lob, start_granted_at=45.0)
        await env.conn.execute("DELETE FROM ffa_queue WHERE player_id = $1", lob.pids[5])
        before = await env.seats(lob)
        out = await env.verdict_direct(lob)
        assert out.body["outcome"] == "unknown" and await env.seats(lob) == before, \
            ("S21 v", out.body)
        assert (await env.lobby_row(lob))["short_started_at"] is None, "S21 v no decision"
        # (vi) ordered: A holds the lock and commits a closing verdict; B's
        # start waits, then answers from its seat row; no grant exists. In
        # the two "own" cases A's own transaction removes the leaver's queue
        # row before its verdict, so a read taken before the lobby lock would
        # see every seat READY.
        for close, own, slot, want in (("reform", True, 1, "reformed"),
                                       ("dissolve", True, 1, "dissolved"),
                                       ("reform", False, 1, "reformed"),
                                       ("reform", False, 4, "excluded"),
                                       ("dissolve", False, 1, "dissolved")):
            if own:
                n = 5 if close == "reform" else 3
                lob = await env.lobby(n, t=40.0)
                await env.ready_all(lob, list(range(n)))
            else:
                lob = await env.lobby(5 if close == "reform" else 4, t=40.0)
                await env.ready_all(lob, [0, 1, 2, 3] if close == "reform" else [0, 1])
            if close == "dissolve" and not own:
                await env.set_seat(lob, 3, left_at=8.0, verdict="left", verdict_at=8.0)
                await env.conn.execute("DELETE FROM ffa_queue WHERE player_id = $1", lob.pids[3])
            sess = env.sm()
            db = await sess.__aenter__()
            try:
                ctx = await main._asm_ctx_slot(db, lob.lid, route="assembly", trigger="assembly")
                apid = (await db.execute(main.text("SELECT pg_backend_pid()"))).scalar()
                if own:
                    await db.execute(main.text("DELETE FROM ffa_queue WHERE player_id = :p"),
                                     {"p": lob.pids[n - 1]})
                    await ctx.reload()
                out = await main._ffa_assembly_verdict(ctx, "assembly")
                assert out["outcome"] == close, ("S21 vi A", close, own, out)
                task = asyncio.ensure_future(env.connect(lob, slot, "start"))
                waiting = await _waiting_on(env, apid)
                assert waiting >= 1 and not task.done(), ("S21 vi blocks", waiting)
                await db.commit()
            finally:
                await sess.__aexit__(None, None, None)
            a = await task
            row = await env.lobby_row(lob)
            assert row["start_granted_at"] is None, ("S21 vi grant", close, own, slot, a)
            assert a["status"] == want, ("S21 vi", close, own, slot, a)
    run_env(monkeypatch, body)


def test_s23_the_listing_excludes_bets_disabled(monkeypatch):
    """S23: of a plain, a short-started and a re-formed active ranked
    zero-game lobby, only the plain one is listed."""
    async def body(env):
        plain = await env.lobby(4, gated=False, t=5.0)
        short = await env.lobby(5, admission=True, t=40.0)
        a = await _post(env, short, 0, [0, 1, 2, 3])
        assert a["status"] == "start_ok", ("S23 short", a)
        old = await env.lobby(5, t=40.0)
        a = await _post(env, old, 0, [0, 1, 2, 3])
        assert a["status"] == "reformed", ("S23 reform", a)
        reformed = (await env.lobby_row(old))["reformed_to"]
        for lid in (short.lid, reformed):
            assert (await env.lobby_row(lid))["bets_disabled"] is True, ("S23 flag", lid)

        async def go():
            async with env.sm() as db:
                return await main.ffa_bettable(steam_id="", db=db)
        out = await env._call(go)
        ids = {x["lobby_id"] for x in out["lobbies"]}
        assert str(plain.lid) in ids, ("S23 plain", ids)
        assert str(short.lid) not in ids and str(reformed) not in ids, ("S23 excluded", ids)
    run_env(monkeypatch, body)


async def _bet(env, lob, bsid, on_slot, amount=100, g=1):
    on = lob.sids[on_slot]
    sig = _sig("ffa-bet:%s:%s:%s:%d:%d" % (bsid, lob.lid, on, amount, g))

    async def go():
        async with env.sm() as db:
            return await main.place_ffa_bet(cf_asm.FakeRequest(), steam_id=bsid,
                                            lobby_id=str(lob.lid), bet_on_steam_id=on,
                                            amount=amount, game_number=g, sig=sig, db=db)
    return go


def test_s24_the_bet_post_refuses_from_the_locked_row(monkeypatch):
    """S24: session B sets bets_disabled and holds it; the bet POST waits on
    B's row, then answers 409 and writes no ffa_bets row. The same POST on a
    twin lobby without B is accepted (the fixture is otherwise bettable)."""
    async def body(env):
        env.mp.setattr(main, "MATCH_HMAC_SECRET", _BET_SECRET)
        ok = await env.lobby(5, gated=False, t=5.0)
        _, bsid = await env.bettor()
        a = await env._call(await _bet(env, ok, bsid, 1))
        assert a.status == 200 and len(await env.bets(ok)) == 1, ("S24 accept", a)
        lob = await env.lobby(5, gated=False, t=5.0)
        conn = await cf_pg.harness.connect_bound(env.c.dsn, env.c.schema)
        tr = conn.transaction()
        await tr.start()
        await conn.execute("UPDATE ffa_lobbies SET bets_disabled = TRUE WHERE id = $1", lob.lid)
        bpid = await conn.fetchval("SELECT pg_backend_pid()")
        try:
            task = asyncio.ensure_future(env._call(await _bet(env, lob, bsid, 1)))
            n = await _waiting_on(env, bpid)
            assert n >= 1 and not task.done(), ("S24 waits", n)
        finally:
            await tr.commit()
            await conn.close()
        a = await task
        assert a.status == 409, ("S24 refused", a)
        assert await env.bets(lob) == [], "S24 no row"
    run_env(monkeypatch, body)


def test_s25_lobby_phase_wagers_after_a_reform(monkeypatch):
    """S25: after a REFORM of a lobby whose Start bound lobby-phase wagers, no
    lobby_bets row names L', the bound wager's ffa_bets row names L' with
    every other column unchanged, no refund is written, the REFORM issues no
    statement on lobby_bets, and a lobby-bet POST for L' is refused."""
    from sqlalchemy import event as _event

    async def body(env):
        env.mp.setattr(main, "MATCH_HMAC_SECRET", _BET_SECRET)
        lob = await env.lobby(5, t=39.9)
        b3, b3sid = await env.bettor()
        w3 = await env.wager(lob, b3, lob.pids[1])
        await _bound_lobby_bet(env, lob, b3, 1, w3)
        snap = (await env.bets(lob))[0]
        await env.at(lob, 40.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        seen = []

        def spy(conn, cursor, statement, parameters, context, executemany):
            if "lobby_bets" in statement:
                seen.append(statement)
        _event.listen(env.engine.sync_engine, "before_cursor_execute", spy)
        try:
            a = await env.census_of(lob, 0, [0, 1, 2, 3])
        finally:
            _event.remove(env.engine.sync_engine, "before_cursor_execute", spy)
        assert a["status"] == "reformed", ("S25 reform", a)
        assert seen == [], ("S25 no lobby_bets statement", seen)
        new = (await env.lobby_row(lob))["reformed_to"]
        assert await env.conn.fetchval(
            "SELECT count(*) FROM lobby_bets WHERE lobby_id = $1", new) == 0, "S25 lobby_bets"
        moved = await env.bets(new)
        want = dict(snap)
        want["lobby_id"] = new
        assert moved == [want], ("S25 carried", moved)
        assert await env.refunds(lob) == 0 and await env.refunds(new) == 0, "S25 no refund"
        amount = 50
        sig = _sig("lobby-bet:%s:ffa:%s:%s:%d" % (b3sid, new, lob.sids[2], amount))

        async def go():
            async with env.sm() as db:
                return await main.place_lobby_bet(steam_id=b3sid, mode="ffa", lobby_id=str(new),
                                                  target_steams=lob.sids[2], amount=amount,
                                                  sig=sig, db=db, request=None)
        a = await env._call(go)
        assert a.status == 409, ("S25 lobby-bet refused", a)
    run_env(monkeypatch, body)


# -- closers, the leave, the re-formed row (S26-S28, S31-S33, S35, S36, S38) --

PIN_COMMIT = "edf9aee"


class _StopTick(BaseException):
    """Ends queue_cleanup_loop after one pass (it catches Exception)."""


async def _janitor_tick(env):
    """One pass of queue_cleanup_loop against the case schema: its session
    factory is the case's, its first sleep returns at once and its second
    ends the pass."""
    import asyncio as _aio
    import database
    real_sleep = _aio.sleep
    n = {"k": 0}

    async def fake_sleep(delay, *a, **k):
        if delay == 60:
            n["k"] += 1
            if n["k"] > 1:
                raise _StopTick()
            return None
        return await real_sleep(0)
    env.mp.setattr(database, "async_session", env.sm)
    env.mp.setattr(_aio, "sleep", fake_sleep)
    try:
        await env._call(main.queue_cleanup_loop)
    except _StopTick:
        pass
    finally:
        env.mp.setattr(_aio, "sleep", real_sleep)


async def _delete_member(env, sid):
    """delete_player_data for one member, signed with the case's secret."""
    env.mp.setattr(main, "MATCH_HMAC_SECRET", _BET_SECRET)
    env.mp.delenv("STEAM_WEB_API_KEY", raising=False)
    sig = _sig("delete:%s" % sid)

    async def go():
        async with env.sm() as db:
            return await main.delete_player_data(sid, cf_asm.FakeRequest(), sig=sig, _slot=None,
                                                 db=db)
    try:
        return await env._call(go)
    finally:
        env.mp.setattr(main, "MATCH_HMAC_SECRET", "")


async def _full_grant(env, lob, t=30.0):
    """Every seat READY and bodied at t, then a real full-room grant."""
    await env.at(lob, t)
    await env.ready_all(lob, list(range(lob.n)))
    a = await env.connect(lob, 0, "start")
    assert a["status"] == "start_ok", ("full grant", a)
    return a


async def _age_queue(env, lob, *, matched_s=None, polled_s=None):
    if matched_s is not None:
        await env.conn.execute(
            "UPDATE ffa_queue SET matched_at = clock_timestamp() - make_interval(secs => $2)"
            " WHERE series_id = $1", lob.lid, float(matched_s))
    if polled_s is not None:
        await env.conn.execute(
            "UPDATE ffa_queue SET last_polled = clock_timestamp() - make_interval(secs => $2)"
            " WHERE series_id = $1", lob.lid, float(polled_s))


def _record(row, path, trigger, t, tag):
    assert row["dissolve_path"] == path and row["dissolve_trigger"] == trigger, \
        (tag, row["dissolve_path"], row["dissolve_trigger"])
    ms = row["dissolve_after_ms"]
    assert ms is not None and t * 1000 - 1000 <= ms <= t * 1000 + 180000, (tag, "after_ms", ms)


def test_s26_the_reform_copies_every_field(monkeypatch):
    """S26: each COPY and COPY-AND field from a parent whose values differ
    from the schema defaults, with one carried member's players.mod_version
    below the config floor (the collapse must not run on reform); COPY-AND
    with the parent FALSE and K capable stays FALSE; with K not capable a
    TRUE parent gives FALSE."""
    async def body(env):
        parent = {"is_ranked": False, "score_target": 7, "card_candidates": 3,
                  "initial_picks": 2, "card_cap": 4, "same_card_rule": True,
                  "settings_known": False, "password_hash": "cf-hash",
                  "kicked_steam_ids": str(cf_asm.STEAM_BASE + 999)}
        for case, kt_sd, capable, want in (("copy", True, True, True),
                                           ("and-false", False, True, False),
                                           ("not-capable", True, False, False)):
            lob = await env.lobby(5, t=39.0)
            await env.set_lobby(lob, settings_changed_at=10.0, kills_tiebreak=kt_sd,
                                sudden_death=kt_sd, **parent)
            await env.conn.execute("UPDATE players SET mod_version = '1.0.0' WHERE id = $1",
                                   lob.pids[2])
            if not capable:
                await env.conn.execute("UPDATE ffa_queue SET mod_version = '1.30.0'"
                                       " WHERE player_id = $1", lob.pids[1])
            await env.at(lob, 40.0)
            prow = await env.lobby_row(lob)
            a = await _post(env, lob, 0, [0, 1, 2, 3])
            assert a["status"] == "reformed", ("S26 reform", case, a)
            new = await env.lobby_row((await env.lobby_row(lob))["reformed_to"])
            for k in main._ASM_REFORM_CLASSES["COPY"]:
                assert new[k] == prow[k], ("S26 COPY", case, k, new[k], prow[k])
            assert (new["kills_tiebreak"], new["sudden_death"]) == (want, want), \
                ("S26 COPY-AND", case, new["kills_tiebreak"], new["sudden_death"])
    run_env(monkeypatch, body)


def _insert_columns():
    import re as _r
    head = main._ASM_REFORM_INSERT_SQL.split("VALUES")[0]
    return [c.strip() for c in _r.sub(r"^.*?\(", "", head, count=1, flags=_r.S)
            .rstrip().rstrip(")").split(",") if c.strip()]


def test_s27_the_schema_census_both_directions(monkeypatch):
    """S27: information_schema.columns of ffa_lobbies equals the union of the
    four classes, the classes are disjoint, and REFORM's INSERT names exactly
    that union (46 columns, N12)."""
    async def body(env):
        cols = {r[0] for r in await env.conn.fetch(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'ffa_lobbies'")}
        classes = main._ASM_REFORM_CLASSES
        names = [c for v in classes.values() for c in v]
        assert len(names) == len(set(names)), ("S27 disjoint", sorted(names))
        assert set(names) - cols == set(), ("S27 class not live", sorted(set(names) - cols))
        assert cols - set(names) == set(), ("S27 live not classed", sorted(cols - set(names)))
        ins = _insert_columns()
        assert len(ins) == len(set(ins)) == 46 and set(ins) == set(names), \
            ("S27 insert", len(ins), sorted(set(ins) ^ set(names)))
    run_env(monkeypatch, body, fresh=True)


def test_s27b_a_committed_baseline_reform(monkeypatch):
    """S27b: one REFORM of a seeded 5-seat lobby commits, and a second
    session reads L' with every column of the class table."""
    async def body(env):
        lob = await env.lobby(5, t=40.0)
        try:
            a = await _post(env, lob, 0, [0, 1, 2, 3])
        except Exception as exc:          # a REFORM whose transaction rolled back
            a = {"status": "raised", "error": type(exc).__name__}
        names = [c for v in main._ASM_REFORM_CLASSES.values() for c in v]
        row = await env.conn.fetchrow("SELECT %s FROM ffa_lobbies WHERE reformed_from = $1"
                                      % ", ".join(names), lob.lid)
        assert row is not None and len(row) == len(names), ("S27b read", a)
        assert a["status"] == "reformed", ("S27b reform", a)
        assert row["id"] == (await env.lobby_row(lob))["reformed_to"] \
            and row["status"] == "active", ("S27b row", row["status"])
    run_env(monkeypatch, body)


def test_s28_every_closer_writes_its_record(monkeypatch):
    """S28: each of the eleven closers, driven once on a lobby with seat
    rows, writes dissolve_path, dissolve_trigger and dissolve_after_ms; the
    arrays are exact where one seat arrived and then left; the earliest
    leaver is first_leaver."""
    async def body(env):
        # janitor_dead_lock
        dead = await env.lobby(5, t=1900.0)
        await _age_queue(env, dead, polled_s=1200)
        # dispersed_close
        disp = await env.lobby(5, t=3700.0)
        # quiet_close
        quiet = await env.lobby(5, t=600.0)
        await _janitor_tick(env)
        row = await env.lobby_row(dead)
        assert row["status"] == "canceled", ("S28 dead", row["status"])
        _record(row, "janitor_dead_lock", "janitor", 1900, "S28 dead")
        row = await env.lobby_row(disp)
        assert row["status"] == "completed", ("S28 dispersed", row["status"])
        _record(row, "dispersed_close", "janitor", 3700, "S28 dispersed")
        row = await env.lobby_row(quiet)
        assert row["status"] == "completed", ("S28 quiet", row["status"])
        _record(row, "quiet_close", "janitor", 600, "S28 quiet")
        # member_deleted and member_deleted_played
        for games, path, status in ((0, "member_deleted", "canceled"),
                                    (1, "member_deleted_played", "completed")):
            lob = await env.lobby(5, t=30.0, games_played=games)
            a = await _delete_member(env, lob.sids[2])
            assert a.status == 200, ("S28 delete", path, a)
            row = await env.lobby_row(lob)
            assert row["status"] == status, ("S28 " + path, row["status"])
            _record(row, path, "member_delete", 30, "S28 " + path)
        # leave_dissolve
        lob = await env.lobby(5, gated=False, t=25.0)
        await env.leave(lob, 4)
        _record(await env.lobby_row(lob), "leave_dissolve", "leave", 25, "S28 leave_dissolve")
        # leave_all_but_one
        lob = await env.lobby(3, gated=False, t=100.0, games_played=1)
        await env.leave(lob, 1)
        assert (await env.lobby_row(lob))["status"] == "active", "S28 all_but_one first"
        await env.leave(lob, 2)
        row = await env.lobby_row(lob)
        assert row["status"] == "completed", ("S28 all_but_one", row["status"])
        _record(row, "leave_all_but_one", "leave", 100, "S28 all_but_one")
        # asm_reform, asm_dissolve
        lob = await env.lobby(5, t=40.0)
        await _post(env, lob, 0, [0, 1, 2, 3])
        _record(await env.lobby_row(lob), "asm_reform", "assembly", 40, "S28 asm_reform")
        lob = await env.lobby(4, t=40.0)
        await env.set_seat(lob, 3, left_at=8.0, verdict="left", verdict_at=8.0)
        await env.conn.execute("DELETE FROM ffa_queue WHERE player_id = $1", lob.pids[3])
        await _post(env, lob, 0, [0, 1])
        _record(await env.lobby_row(lob), "asm_dissolve", "assembly", 40, "S28 asm_dissolve")
        # sitting_over
        lob = await env.lobby(5, t=30.0)
        await _full_grant(env, lob, 30.0)
        await env.at(lob, 1000.0)
        await env.poll(lob, 0)
        row = await env.lobby_row(lob)
        assert row["status"] == "completed", ("S28 sitting_over", row["status"])
        _record(row, "sitting_over", "poll", 1000, "S28 sitting_over")
        # poll_dead_lock, poll_assembly_failed
        lob = await env.lobby(5, t=700.0)
        await _age_queue(env, lob, matched_s=700)
        await env.poll(lob, 0)
        row = await env.lobby_row(lob)
        assert row["status"] == "canceled", ("S28 poll_dead_lock", row["status"])
        _record(row, "poll_dead_lock", "poll", 700, "S28 poll_dead_lock")
        lob = await env.lobby(5, t=400.0)
        await _age_queue(env, lob, matched_s=400)
        await env.poll(lob, 0)
        row = await env.lobby_row(lob)
        assert row["status"] == "canceled", ("S28 poll_assembly_failed", row["status"])
        _record(row, "poll_assembly_failed", "poll", 400, "S28 poll_assembly_failed")
        # the arrays and the earliest leaver: seat 5 arrives and leaves at +5
        # (kept), seats 0-3 post, seat 4 stays silent, seat 6's leave at +25
        # closes the lobby.
        lob = await env.lobby(7, t=5.0)
        a = await env.connect(lob, 5, "arrived", region=lob.region, actor=6, count=6)
        await env.leave(lob, 5, label="menu_leave")
        assert (await env.seat(lob, 5))["left_path"] == "kept", "S28 arrays kept"
        await env.at(lob, 25.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        await env.leave(lob, 6)
        row = await env.lobby_row(lob)
        assert row["reformed_to"] is not None, ("S28 arrays close", row["status"])
        assert list(row["present_at_dissolve"]) == [0, 1, 2, 3], \
            ("S28 present", row["present_at_dissolve"])
        assert list(row["absent_at_dissolve"]) == [4], ("S28 absent", row["absent_at_dissolve"])
        assert list(row["arrived_at_dissolve"]) == [5], ("S28 arrived", row["arrived_at_dissolve"])
        assert row["first_leaver"] == lob.pids[5], ("S28 first_leaver", row["first_leaver"])
        assert row["first_leave_label"] == "menu_leave", ("S28 label", row["first_leave_label"])
    run_env(monkeypatch, body)


def test_s31_the_leave_before_20(monkeypatch):
    """S31: n = 5, a leave at t = 8 keeps the lobby active with no decision
    (left_path 'kept'); n = 3, a leave at t = 8 runs today's dissolve."""
    async def body(env):
        lob = await env.lobby(5, t=8.0)
        await env.leave(lob, 4)
        row = await env.lobby_row(lob)
        assert row["status"] == "active" and row["asm_rule"] is None, ("S31 kept", row["status"])
        assert (await env.seat(lob, 4))["left_path"] == "kept", "S31 kept path"
        lob = await env.lobby(3, t=8.0)
        await env.leave(lob, 2)
        row = await env.lobby_row(lob)
        assert row["status"] == "canceled" and row["dissolve_path"] == "leave_dissolve", \
            ("S31 dissolve", row["status"], row["dissolve_path"])
        assert (await env.seat(lob, 2))["left_path"] == "dissolve", "S31 dissolve path"
    run_env(monkeypatch, body)


async def _omit(env, lob, witnesses, gone_slot, *, actor0=1):
    """Fresh censuses from `witnesses` that omit `gone_slot`, each listing
    itself and the other witnesses (their own round trip, not the subject's)."""
    present = [s for s in range(lob.n) if s != gone_slot]
    entries = [(s, actor0 + s, 1, 1) for s in present]
    for w in witnesses:
        await env.census_row(lob, w, entries, claim=actor0 + w, bind=False)


def test_s32_the_started_lobby_departure(monkeypatch):
    """S32: a pre-room leave on a granted lobby, and one on a short-started
    lobby, append the departure and keep the lobby active (the granted
    seat's leave corroborated by two witnesses, N8)."""
    async def body(env):
        lob = await env.lobby(5, t=30.0)
        await _full_grant(env, lob, 30.0)
        await env.at(lob, 60.0)
        await _omit(env, lob, [0, 2], 1)
        await env.set_seat(lob, 1, census_at=40.0)
        await env.leave(lob, 1)
        row = await env.lobby_row(lob)
        assert row["status"] == "active" and list(row["departed_ids"]) == [lob.pids[1]], \
            ("S32 granted", row["status"], row["departed_ids"])
        lob = await env.lobby(5, admission=True, t=40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "start_ok", ("S32 short", a)
        await env.leave(lob, 4)
        row = await env.lobby_row(lob)
        assert row["status"] == "active" and list(row["departed_ids"]) == [lob.pids[4]], \
            ("S32 short leave", row["status"], row["departed_ids"])
    run_env(monkeypatch, body)


_PIN = {}


def _pin_main():
    """main.py at the production pin, imported as module main_pin
    (CF_PIN_MAIN names a copy, which is how a mutant of it is run)."""
    if "mod" in _PIN:
        return _PIN["mod"]
    path = os.environ.get("CF_PIN_MAIN")
    if not path:
        repo = os.path.normpath(os.path.join(HERE, "..", ".."))
        src = subprocess.run(["git", "-C", repo, "show", PIN_COMMIT + ":backend/api/main.py"],
                             capture_output=True, check=True).stdout
        d = tempfile.mkdtemp(prefix="cf_pin_")
        path = os.path.join(d, "main_pin.py")
        with open(path, "wb") as fh:
            fh.write(src)
    spec = importlib.util.spec_from_file_location("main_pin", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _PIN["mod"] = mod
    return mod


def test_s33_the_undeclared_label_at_the_pin(monkeypatch):
    """S33: the pin's own leave route (cause, no label), on an active
    zero-game lobby where an in-room cause keeps the lobby and an empty one
    dissolves it, called with cause="" and &label=in_room_exit, dissolves it
    exactly as without the parameter: answers and rows identical."""
    import httpx
    import database
    pin = _pin_main()

    async def no_session(request, steam_id, db):
        return None
    monkeypatch.setattr(pin, "_check_steam_session", no_session)

    async def body(env):
        monkeypatch.setattr(pin, "time", main.time)
        monkeypatch.setattr(pin, "_presence_seen", {})

        async def override():
            async with env.sm() as db:
                yield db
        pin.app.dependency_overrides[database.get_db] = override
        try:
            async def call(lob, slot, params):
                q = dict({"steam_id": lob.sids[slot], "expected_lobby_id": str(lob.lid)},
                         **params)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=pin.app),
                                             base_url="http://cf") as cl:
                    r = await cl.post("/api/v1/ffa/queue/leave", params=q,
                                      headers={"X-Mod-Version": "1.41.0"})
                return r.status_code, r.json()

            async def shape(lob, ans):
                rows = {"answer": ans, "lobby": await env.lobby_row(lob),
                        "queue": [dict(r) for r in await env.conn.fetch(
                            "SELECT * FROM ffa_queue WHERE player_id = ANY($1::uuid[])"
                            " ORDER BY steam_id", lob.pids)],
                        "seats": await env.seats(lob)}
                names = {sid: "SID%d" % i for i, sid in enumerate(lob.sids)}
                names[rows["lobby"]["photon_room_id"]] = "ROOM"
                for r in rows["queue"]:
                    names[r["display_name"]] = "NAME%d" % lob.sids.index(r["steam_id"])
                return cf_asm.normalise(_anon(rows, names))
            kept = await env.lobby(5, gated=False, t=25.0)
            st, ans = await call(kept, 4, {"cause": "in_room_exit"})
            assert st == 200 and (await env.lobby_row(kept))["status"] == "active", \
                ("S33 in-room keeps", st, ans)
            with_label = await env.lobby(5, gated=False, t=25.0)
            st1, ans1 = await call(with_label, 4, {"cause": "", "label": "in_room_exit"})
            plain = await env.lobby(5, gated=False, t=25.0)
            st2, ans2 = await call(plain, 4, {"cause": ""})
            assert st1 == st2 == 200, ("S33 status", st1, st2)
            assert (await env.lobby_row(with_label))["status"] == "canceled", \
                ("S33 dissolves", ans1)
            got, want = await shape(with_label, ans1), await shape(plain, ans2)
            assert got == want, ("S33 identical", got, want)
        finally:
            pin.app.dependency_overrides.pop(database.get_db, None)
    run_env(monkeypatch, body)


def test_s35_dissolve_releases_the_pending_seats(monkeypatch):
    """S35: after a DISSOLVE the PENDING seats have no queue row and no
    lease; the READY seats are searching."""
    async def body(env):
        lob = await env.lobby(4, t=40.0)
        await env.set_seat(lob, 3, left_at=8.0, verdict="left", verdict_at=8.0)
        await env.conn.execute("DELETE FROM ffa_queue WHERE player_id = $1", lob.pids[3])
        a = await _post(env, lob, 0, [0, 1])
        row = await env.lobby_row(lob)
        assert row["status"] == "canceled" and row["asm_rule"] is not None, ("S35 dissolve", a)
        assert await env.queue_row(lob, 2) is None and await env.lease(lob, 2) is None, \
            "S35 pending released"
        for s in (0, 1):
            q = await env.queue_row(lob, s)
            assert q is not None and q["status"] == "searching", ("S35 ready searching", s, q)
    run_env(monkeypatch, body)


def test_s36_every_closer_on_a_started_lobby(monkeypatch):
    """S36a-k: on a started zero-game lobby (start_granted_at set) each
    closer either leaves it active or closes it completed; none cancels it."""
    async def body(env):
        # (a) the janitor dead lock: not a candidate (no queue rows, so the
        # quiet close has nobody to look at either).
        a_lob = await env.lobby(5, t=30.0)
        await _full_grant(env, a_lob, 30.0)
        await env.at(a_lob, 1900.0)
        await env.conn.execute("DELETE FROM ffa_queue WHERE series_id = $1", a_lob.lid)
        # (b) the dispersed close; (c) the quiet close.
        b_lob = await env.lobby(5, t=30.0)
        await _full_grant(env, b_lob, 30.0)
        await env.at(b_lob, 3700.0)
        c_lob = await env.lobby(5, t=30.0)
        await _full_grant(env, c_lob, 30.0)
        await env.at(c_lob, 600.0)
        for lob in (b_lob, c_lob):
            bid, _ = await env.bettor()
            await env.wager(lob, bid, lob.pids[0])
        await _janitor_tick(env)
        row = await env.lobby_row(a_lob)
        assert row["status"] == "active", ("S36 a", row["status"], row["dissolve_path"])
        row = await env.lobby_row(b_lob)
        assert row["status"] == "completed" and row["dissolve_path"] == "dispersed_close", \
            ("S36 b", row["status"], row["dissolve_path"])
        assert all(b["settled_at"] is not None for b in await env.bets(b_lob)), "S36 b reconcile"
        row = await env.lobby_row(c_lob)
        assert row["status"] == "completed" and row["dissolve_path"] == "quiet_close", \
            ("S36 c", row["status"], row["dissolve_path"])
        assert all(b["settled_at"] is not None for b in await env.bets(c_lob)), "S36 c reconcile"
        # (d) member deletion with zero games does not cancel it; (e) the
        # played-or-started row closes it completed with the reconcile.
        lob = await env.lobby(5, t=30.0)
        await _full_grant(env, lob, 30.0)
        bid, _ = await env.bettor()
        await env.wager(lob, bid, lob.pids[0])
        a = await _delete_member(env, lob.sids[2])
        assert a.status == 200, ("S36 d delete", a)
        row = await env.lobby_row(lob)
        assert row["status"] != "canceled", ("S36 d", row["status"])
        assert row["status"] == "completed" and row["dissolve_path"] == "member_deleted_played", \
            ("S36 e", row["status"], row["dissolve_path"])
        assert all(b["settled_at"] is not None for b in await env.bets(lob)), "S36 e reconcile"
        # (f) the leave dissolve does not match: the departure path. Twice:
        # gated, and with assembly_v1 cleared so the statement's own grant
        # term is the only guard.
        for gated in (True, False):
            lob = await env.lobby(5, t=30.0)
            await _full_grant(env, lob, 30.0)
            if not gated:
                await env.set_lobby(lob, assembly_v1=False)
            await env.leave(lob, 1)
            row = await env.lobby_row(lob)
            assert row["status"] == "active", ("S36 f", gated, row["status"])
        # (g) all but one leave (uncorroborated, N8): active, no reconcile,
        # no departure appended, the survivors' rows and leases untouched.
        lob = await env.lobby(3, t=30.0)
        await _full_grant(env, lob, 30.0)
        bid, _ = await env.bettor()
        await env.wager(lob, bid, lob.pids[0])
        await env.leave(lob, 1)
        await env.leave(lob, 2)
        row = await env.lobby_row(lob)
        assert row["status"] == "active" and not row["departed_ids"], \
            ("S36 g", row["status"], row["departed_ids"])
        assert all(b["settled_at"] is None for b in await env.bets(lob)), "S36 g no reconcile"
        assert await env.queue_row(lob, 0) is not None and await env.lease(lob, 0) is not None, \
            "S36 g survivor"
        # (i) the poll's dead-lock inputs: neither is met. Before (h): a
        # mutant of these inputs would close (h)'s lobby too.
        lob = await env.lobby(5, t=30.0)
        await _full_grant(env, lob, 30.0)
        await env.at(lob, 700.0)
        await env.set_lobby(lob, start_granted_at=650.0)
        await _age_queue(env, lob, matched_s=700)
        await env.poll(lob, 0)
        row = await env.lobby_row(lob)
        assert row["status"] == "active", ("S36 i", row["status"], row["dissolve_path"])
        # (h) the sitting-over close: every member polling, 900 s since the grant.
        lob = await env.lobby(5, t=30.0)
        await _full_grant(env, lob, 30.0)
        await env.at(lob, 935.0)
        await env.poll(lob, 0)
        row = await env.lobby_row(lob)
        assert row["status"] == "completed" and row["dissolve_path"] == "sitting_over", \
            ("S36 h", row["status"])
        # (j) REFORM and (k) DISSOLVE at function level on a granted lobby:
        # both are judged first; the tag names each fixture that decided.
        outs = {}
        for n, ready, close in ((5, [0, 1, 2, 3], "j"), (4, [0, 1], "k")):
            lob = await env.lobby(n, t=40.0)
            await env.ready_all(lob, ready)
            await env.set_lobby(lob, start_granted_at=35.0)
            await env.conn.execute(
                "UPDATE ffa_assembly_seats SET verdict = 'granted', start_roster = TRUE,"
                " verdict_at = $2 WHERE lobby_id = $1 AND slot = ANY($3::smallint[])",
                lob.lid, await env.ts(lob, 35.0), ready)
            await env.conn.execute("DELETE FROM ffa_queue WHERE player_id = $1", lob.pids[n - 1])
            out = await env.verdict_direct(lob)
            row = await env.lobby_row(lob)
            outs[close] = (out.body["outcome"], row["status"])
        decided = "".join(c for c in ("j", "k") if outs[c] != ("unknown", "active"))
        assert not decided, ("S36 " + decided, outs)
    run_env(monkeypatch, body)


def test_s38_the_leave_cause(monkeypatch):
    """S38: (i) a started lobby's leave with cause "" takes the departure
    path and never dissolves; (ii) on a gated unstarted lobby at t >= 20,
    in_room_exit and "" both leave the leaver LEFT and the next verdict gives
    the others the same outcome; (iii) an ungated lobby, today's behaviour."""
    async def body(env):
        lob = await env.lobby(5, t=30.0)
        await _full_grant(env, lob, 30.0)
        await env.leave(lob, 2, cause="")
        row = await env.lobby_row(lob)
        assert row["status"] == "active", ("S38 i", row["status"])
        assert (await env.seat(lob, 2))["left_path"] == "departure", "S38 i path"
        outs = {}
        for cause in ("in_room_exit", ""):
            lob = await env.lobby(5, t=25.0)
            await env.ready_all(lob, [0, 1, 2, 3])
            await env.leave(lob, 4, cause=cause)
            assert (await env.seat(lob, 4))["verdict"] == "left", ("S38 ii left", cause)
            await _post(env, lob, 0, [0, 1, 2, 3])
            row = await env.lobby_row(lob)
            new = await env.lobby_row(row["reformed_to"]) if row["reformed_to"] else None
            outs[cause] = (row["status"], row["asm_rule"],
                           sorted(new["member_ids"]) == sorted(lob.pids[:4]) if new else None)
        assert outs["in_room_exit"] == outs[""] == ("canceled", "D", True), ("S38 ii", outs)
        for cause, want in (("", "canceled"), ("in_room_exit", "active")):
            lob = await env.lobby(5, gated=False, t=25.0)
            await env.leave(lob, 4, cause=cause)
            assert (await env.lobby_row(lob))["status"] == want, ("S38 iii", cause)
    run_env(monkeypatch, body)


# -- the writers, the notice, the projection, every answer's fields (S11a-j,
#    S29, S30, S34, S51, S65) --

import ast as _ast  # noqa: E402
import json as _json  # noqa: E402


async def _short(env, n=5, roster=(0, 1, 2, 3), t=40.0, **kw):
    """An admission lobby started short at lobby age t: `roster` READY (each
    bound to actor 1 + slot, bodied), every other seat PENDING and so
    admissible after the decision."""
    lob = await env.lobby(n, admission=True, t=t, **kw)
    a = await _post(env, lob, roster[0], list(roster))
    assert a["status"] == "start_ok", ("short start", a)
    return lob


async def _admit(env, lob, slot, actor, peer, roster, *, game=0, check=True):
    """Admit an admissible seat through the routes: its own census claiming
    `actor` (it stays admitting), then a granted peer's census listing it
    with that actor (the admission check, state B). check=False leaves the
    verdict to the caller's own named assertion (S11h)."""
    entries = [env.entry(lob, s, 1 + s) for s in roster] + [env.entry(lob, slot, actor)]
    a = await env.assembly(lob, slot, actor, entries, game=game)
    assert a["status"] == "admitting", ("admit own census", slot, a)
    b = await env.assembly(lob, peer, 1 + peer, entries, game=game)
    s = await env.seat(lob, slot)
    if check:
        assert s["verdict"] == "admitted_late", ("admitted", slot, s["verdict"], b)
    return b


def _changed(before, after, ignore=()):
    return {k for k in after if k not in ignore and before.get(k) != after.get(k)}


def test_s11a_the_lock_seat_rows(monkeypatch):
    """S11(a), writer 1: a Start writes one seat row per member in the
    sorted roster's slot order, locked_at at the lock (the lobby's
    created_at, one transaction) and lock_offered_at on the starter's row
    only; read from a second session."""
    async def body(env):
        lob = await _open_lobby(env, 4, ["ffa_asm1,ffa_adm1"] * 4)
        a = await _start(env, main, lob)
        assert a.status == 200, ("S11a start", a)
        row = await env.lobby_row(lob)
        seats = [dict(r) for r in await env.conn.fetch(
            "SELECT s.*, p.steam_id FROM ffa_assembly_seats s JOIN players p"
            "    ON p.id = s.player_id WHERE s.lobby_id = $1 ORDER BY s.slot", lob.lid)]
        order = sorted(lob.sids, key=main._ffa_sort_key)
        assert [s["steam_id"] for s in seats] == order, ("S11a rows", seats)
        qslot = {r["player_id"]: r["slot"] for r in await env.conn.fetch(
            "SELECT player_id, slot FROM ffa_queue WHERE series_id = $1", lob.lid)}
        assert all(qslot[s["player_id"]] == s["slot"] for s in seats), ("S11a slots", qslot)
        assert all(s["locked_at"] == row["created_at"] for s in seats), "S11a locked_at"
        offered = [s["steam_id"] for s in seats if s["lock_offered_at"] is not None]
        assert offered == [lob.sids[0]], ("S11a offered", offered)
        assert all(s["verdict"] is None and s["writes"] == 0 for s in seats), "S11a fresh rows"
    run_env(monkeypatch, body)


def test_s11b_the_poll_offer(monkeypatch):
    """S11(b), writer 2: a ready_join poll writes the caller's
    lock_offered_at and nothing else on any seat row."""
    async def body(env):
        lob = await env.lobby(4, offered=[], t=5.0)
        before = await env.seats(lob)
        a = await env.poll(lob, 1)
        assert a["status"] == "ready_join", ("S11b poll", a)
        after = await env.seats(lob)
        got = {s: _changed(before[s], after[s]) for s in range(4)}
        assert got == {0: set(), 1: {"lock_offered_at"}, 2: set(), 3: set()}, ("S11b", got)
    run_env(monkeypatch, body)


def test_s11c_the_connect_receipts(monkeypatch):
    """S11(c), writer 3: each receipt lands on the caller's row; start_ok_at
    in the granting transaction; started_at on a granted start-roster seat."""
    async def body(env):
        lob = await env.lobby(5, t=10.0)
        for step, kw, col, want in (
                ("lock_seen", {}, "lock_seen_at", None),
                ("countdown", {}, "countdown_at", None),
                ("countdown_abort", {"phase": "gen"}, "countdown_abort", "gen"),
                ("arrived", {"region": "eu", "actor": 9, "count": 4}, "arrived_at", None),
                ("start", {}, "start_req_at", None),
                ("notice_seen", {}, "notice_seen_at", None)):
            a = await env.connect(lob, 4, step, **kw)
            assert a.status == 200, ("S11c", step, a)
            got = (await env.seat(lob, 4))[col]
            assert got == (env.now if want is None else want), ("S11c", step, col, got)
        lob = await env.lobby(5, t=30.0)
        await env.ready_all(lob, [0, 1, 2, 3, 4])
        mark = len(env.rec.stmts)
        a = await env.connect(lob, 0, "start")
        assert a["status"] == "start_ok", ("S11c grant", a)
        assert (await env.seat(lob, 0))["start_ok_at"] == env.now, "S11c start_ok_at"
        stm = env.rec.stmts[mark:]
        grant = {x[4] for x in stm if x[0] == "UPDATE" and x[1] == "ffa_lobbies"
                 and "start_granted_at" in x[2]}
        stamp = {x[4] for x in stm if x[0] == "UPDATE" and x[1] == "ffa_assembly_seats"
                 and "start_ok_at" in x[2]}
        assert len(grant) == 1 and stamp == grant, ("S11c one transaction", grant, stamp)
        a = await env.connect(lob, 1, "started")
        assert a["status"] == "start_ok", ("S11c started", a)
        assert (await env.seat(lob, 1))["started_at"] == env.now, "S11c started_at"
    run_env(monkeypatch, body)


def test_s11d_the_attempt_columns(monkeypatch):
    """S11(d), writer 3: attempt, attempt_at and attempt_phase follow the
    highest attempt; first_attempt_at is the first."""
    async def body(env):
        lob = await env.lobby(5, t=12.0)

        async def cols():
            s = await env.seat(lob, 4)
            return (s["attempt"], s["attempt_at"], s["attempt_phase"], s["first_attempt_at"])
        await env.connect(lob, 4, "attempt", attempt=1, phase="connect")
        t12 = await env.ts(lob, 12.0)
        assert await cols() == (1, t12, "connect", t12), ("S11d first", await cols())
        await env.at(lob, 14.0)
        await env.connect(lob, 4, "attempt", attempt=2, phase="leave")
        t12, t14 = await env.ts(lob, 12.0), await env.ts(lob, 14.0)
        assert await cols() == (2, t14, "leave", t12), ("S11d second", await cols())
        await env.at(lob, 16.0)
        await env.connect(lob, 4, "attempt", attempt=1, phase="connect")
        t12, t14 = await env.ts(lob, 12.0), await env.ts(lob, 14.0)
        assert await cols() == (2, t14, "leave", t12), ("S11d older", await cols())
    run_env(monkeypatch, body)


def test_s11e_census_claim_binding_body(monkeypatch):
    """S11(e), writer 4: the census columns, the claim, the binding and the
    body columns, each as its rule defines it."""
    async def body(env):
        lob = await env.lobby(5, t=5.0)
        for p in (1, 2):
            await env.census_row(lob, p, [(0, 1, 1, 1), (p, 1 + p, 1, 1)], claim=1 + p, bind=True)
        census = [env.entry(lob, 0, 1), env.entry(lob, 1, 2, b=0),
                  env.entry(lob, 2, 3, k=0), {"a": 7, "s": "", "b": 1, "k": 1}]
        a = await env.assembly(lob, 0, 1, census, seen_age_ms=4500, epoch_seen=2)
        assert a["status"] == "assembling", ("S11e", a)
        s = await env.seat(lob, 0)
        got = {k: s[k] for k in ("census_slots", "census_actors", "census_nobody",
                                 "census_unkept", "census_anon", "census_region",
                                 "census_game", "census_at", "census_seen_at", "actor_claim",
                                 "claim_region", "actor_nr", "actor_region", "body_seen_at",
                                 "epoch_seen")}
        want = {"census_slots": [0, 1, 2], "census_actors": [1, 2, 3], "census_nobody": [1],
                "census_unkept": [2], "census_anon": 1, "census_region": "eu",
                "census_game": 0, "census_at": env.now,
                "census_seen_at": await env.ts(lob, 4.5), "actor_claim": 1,
                "claim_region": "eu", "actor_nr": 1, "actor_region": "eu",
                "body_seen_at": env.now, "epoch_seen": 2}
        assert got == want, ("S11e census", got)
        # bodiless_at: a fallback seat bound to actor 5, arrived at +5, and
        # three censuses built from +28 (the reference + 23) listing it b = 0.
        lob = await env.lobby(5, t=30.0)
        await env.set_seat(lob, 4, actor_claim=5, claim_region="eu", actor_nr=5,
                           actor_region="eu", arrived_at=5.0)
        miss = [(0, 1, 1, 1), (1, 2, 1, 1), (2, 3, 1, 1), (4, 5, 0, 1)]
        for p in (1, 2):
            await env.census_row(lob, p, miss, seen=29.0, claim=1 + p, bind=True)
        a = await env.assembly(lob, 0, 1, [env.entry(lob, s, a_, b=b_) for s, a_, b_, _k in miss])
        assert a["status"] == "assembling", ("S11e bodiless", a)
        s = await env.seat(lob, 4)
        assert s["bodiless_at"] == env.now and s["body_seen_at"] is None, \
            ("S11e bodiless_at", s["bodiless_at"], s["body_seen_at"])
    run_env(monkeypatch, body)


def test_s11f_the_leave_columns(monkeypatch):
    """S11(f), writer 5: left_at, left_cause, left_label and left_path."""
    async def body(env):
        for cause, label, want in (("", "menu_leave", (None, "menu_leave", "kept")),
                                   ("in_room_timeout", "room_exit",
                                    ("in_room_timeout", "room_exit", "departure")),
                                   ("", "not_a_site", (None, "unlabelled", "kept"))):
            lob = await env.lobby(5, t=8.0)
            a = await env.leave(lob, 4, cause=cause, label=label)
            assert a.status == 200, ("S11f", cause, a)
            s = await env.seat(lob, 4)
            got = (s["left_at"], s["left_cause"], s["left_label"], s["left_path"])
            assert got == (env.now,) + want, ("S11f", cause, label, got)
    run_env(monkeypatch, body)


def test_s11g_the_verdict_and_the_decision_record(monkeypatch):
    """S11(g), writer 6: verdict, verdict_at and start_roster; dec_at on
    every seat row, and dec_census/dec_census_at as the decision read them
    (a row read as final keeps none), unchanged by a later census."""
    async def body(env):
        lob = await env.lobby(6, admission=True, t=7.0)
        await env.census_row(lob, 5, [(5, 6, 1, 1)], claim=6)
        await env.at(lob, 8.0)
        await env.leave(lob, 5)
        await env.at(lob, 39.0)
        await env.census_row(lob, 4, [(4, 5, 1, 1)], claim=5)
        await env.at(lob, 40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "start_ok", ("S11g start", a)
        now = env.now
        seats = await env.seats(lob)
        for s in seats[:4]:
            assert (s["verdict"], s["verdict_at"], s["start_roster"]) == ("granted", now, True), \
                ("S11g roster", s["slot"], s["verdict"])
        assert (seats[4]["verdict"], seats[4]["verdict_at"], seats[4]["start_roster"]) == \
            ("admissible", now, False), ("S11g admissible", seats[4]["verdict"])
        assert seats[5]["verdict"] == "left", ("S11g left", seats[5]["verdict"])
        for s in seats:
            assert s["dec_at"] == now, ("S11g dec_at", s["slot"], s["dec_at"])
        for s in seats[:5]:
            assert (s["dec_census"], s["dec_census_at"]) == (s["census_slots"], s["census_at"]) \
                and s["dec_census"], ("S11g dec_census", s["slot"], s["dec_census"])
        assert (seats[5]["dec_census"], seats[5]["dec_census_at"]) == (None, None), \
            ("S11g final row", seats[5]["dec_census"])
        await env.at(lob, 45.0)
        await env.census_of(lob, 0, [0, 1])
        again = await env.seats(lob)
        assert again[0]["census_slots"] == [0, 1] and again[0]["dec_census"] == [0, 1, 2, 3], \
            ("S11g first write wins", again[0]["census_slots"], again[0]["dec_census"])
    run_env(monkeypatch, body)


def test_s11h_the_admission_columns(monkeypatch):
    """S11(h), writer 6's admission: the binding, verdict admitted_late,
    late_admitted_at, late_game = games_played + 1 and verdict_at, in one
    transaction with the seat's kept epoch."""
    async def body(env):
        lob = await _short(env)
        await env.at(lob, 50.0)
        mark = len(env.rec.stmts)
        await _admit(env, lob, 4, 5, 0, [0, 1, 2, 3], check=False)
        s = await env.seat(lob, 4)
        got = (s["actor_nr"], s["actor_region"], s["verdict"], s["late_admitted_at"],
               s["late_game"], s["verdict_at"])
        assert got == (5, "eu", "admitted_late", env.now, 1, env.now), ("S11h", got)
        stm = env.rec.stmts[mark:]
        adm = {x[4] for x in stm if x[0] == "UPDATE" and x[1] == "ffa_assembly_seats"
               and "late_admitted_at" in x[2]}
        ep = {x[4] for x in stm if x[0] == "INSERT" and x[1] == "ffa_kept_epochs"}
        assert len(adm) == 1 and ep == adm, ("S11h one transaction", adm, ep)
    run_env(monkeypatch, body)


def test_s11i_the_expiry_verdict(monkeypatch):
    """S11(i), the expiry: at A the admissible seat reads excluded."""
    async def body(env):
        lob = await _short(env)
        await env.at(lob, 140.0)
        a = await env.poll(lob, 0)
        assert a["status"] == "ready_join", ("S11i poll", a)
        s = await env.seat(lob, 4)
        assert (s["verdict"], s["verdict_at"]) == ("excluded", env.now), ("S11i", s["verdict"])
    run_env(monkeypatch, body)


def test_s11j_spawn_entered_late_body_entered_game(monkeypatch):
    """S11(j): spawn_ok_at; entered's late_entered_at and late_game_claim;
    the late-body rule's late_body_game and late_body_at; writer 7's
    entered_game."""
    async def body(env):
        lob = await env.lobby(5, admission=True, t=10.0)
        a = await env.connect(lob, 4, "lock_seen")
        assert a["spawn_ok"] == 1, ("S11j spawn_ok", a)
        assert (await env.seat(lob, 4))["spawn_ok_at"] == env.now, "S11j spawn_ok_at"
        await env.at(lob, 40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "start_ok", ("S11j start", a)
        await env.at(lob, 50.0)
        await _admit(env, lob, 4, 5, 0, [0, 1, 2, 3])
        await env.at(lob, 55.0)
        a = await env.connect(lob, 4, "entered", game=1)
        s = await env.seat(lob, 4)
        assert (s["late_entered_at"], s["late_game_claim"], s["late_body_game"]) == \
            (env.now, 1, None), ("S11j entered", s["late_entered_at"], s["late_game_claim"])
        await env.at(lob, 60.0)
        entries = [env.entry(lob, x, 1 + x) for x in range(5)]
        for w in (0, 1):
            await env.assembly(lob, w, 1 + w, entries, game=1)
        s = await env.seat(lob, 4)
        assert (s["late_body_game"], s["late_body_at"]) == (1, env.now), \
            ("S11j late body", s["late_body_game"], s["late_body_at"])
        res = {lob.sids[0]: (5, 10), lob.sids[1]: (3, 6), lob.sids[2]: (2, 4),
               lob.sids[3]: (1, 2)}
        a = await env.report(lob, 1, res)
        assert a.status == 200, ("S11j report", a)
        assert (await env.seat(lob, 4))["entered_game"] == 1, "S11j entered_game"
    run_env(monkeypatch, body)


# -- S29: the notice --

async def _swap_member(env, lob, slot, pid, sid):
    """Make player (pid, sid) the member at `slot` of fixture lobby `lob` in
    place of the fixture's own player: member_ids, the queue row, the seat
    row and the lease all move to it."""
    old = lob.pids[slot]
    await env.conn.execute(
        "UPDATE ffa_lobbies SET member_ids = array_replace(member_ids, $2, $3) WHERE id = $1",
        lob.lid, old, pid)
    await env.conn.execute("UPDATE ffa_queue SET player_id = $2, steam_id = $3"
                           " WHERE player_id = $1", old, pid, sid)
    await env.conn.execute("UPDATE ffa_assembly_seats SET player_id = $3"
                           " WHERE lobby_id = $1 AND player_id = $2", lob.lid, old, pid)
    await env.conn.execute("UPDATE queue_leases SET player_id = $2 WHERE player_id = $1",
                           old, pid)
    lob.pids[slot], lob.sids[slot] = pid, sid


def test_s29_the_notice(monkeypatch):
    """S29: after an exclusion every poll answer (not_in_queue, searching
    after re-enrolment, another lobby's ready_join) carries asm_notice with
    its outcome until notice_seen lands, and none after; none after 60
    minutes; a poll leaves every seat row as it was."""
    async def body(env):
        async def notice(lob, slot):
            a = await env.poll(lob, slot)
            return a.get("asm_notice"), a

        def want(lob, outcome):
            return {"lobby_id": str(lob.lid), "outcome": outcome, "upload": 1}
        # dissolved: READY {0, 1}, PENDING {2, 3} at 40.
        lob = await env.lobby(4, t=40.0)
        await _post(env, lob, 0, [0, 1])
        assert (await env.lobby_row(lob))["status"] == "canceled", "S29 dissolve"
        assert (await env.seat(lob, 2))["verdict"] == "excluded", "S29 excluded"
        before = await env.seats(lob)
        n, a = await notice(lob, 2)
        assert a["status"] == "not_in_queue" and n == want(lob, "dissolved"), ("S29 d", a)
        assert await env.seats(lob) == before, "S29 rows unchanged"
        await env.conn.execute(
            "INSERT INTO ffa_queue (player_id, steam_id, display_name, status, joined_at,"
            "  last_polled, caps, mod_version) VALUES ($1, $2, 'cf re', 'searching',"
            "  clock_timestamp(), clock_timestamp(), 'ffa_asm1,ffa_adm1', '1.41.0')",
            lob.pids[2], lob.sids[2])
        n, a = await notice(lob, 2)
        assert a["status"] == "searching" and n == want(lob, "dissolved"), ("S29 searching", a)
        assert await env.seats(lob) == before, "S29 rows unchanged (searching)"
        a = await env.connect(lob, 2, "notice_seen")
        assert a.status == 200 and a["status"] == "excluded", ("S29 notice_seen", a)
        n, a = await notice(lob, 2)
        assert n is None, ("S29 after notice_seen", a)
        # reformed: PENDING seat 4 excluded; then a ready_join in another lobby.
        lob = await env.lobby(5, t=40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert a["status"] == "reformed", ("S29 reform", a)
        n, a = await notice(lob, 4)
        assert a["status"] == "not_in_queue" and n == want(lob, "reformed"), ("S29 r", a)
        other = await env.lobby(3, t=5.0, host_slot=1)
        await _swap_member(env, other, 2, lob.pids[4], lob.sids[4])
        before = await env.seats(lob)
        n, a = await notice(lob, 4)
        assert await env.seats(lob) == before, "S29 rows unchanged (ready_join)"
        assert a["status"] == "ready_join" and n == want(lob, "reformed"), ("S29 ready_join", a)
        # started: the expiry at A; none after 60 minutes.
        lob = await _short(env)
        await env.at(lob, 140.0)
        await env.poll(lob, 0)
        n, a = await notice(lob, 4)
        assert a["status"] == "not_in_queue" and n == want(lob, "started"), ("S29 s", a)
        await env.conn.execute(
            "UPDATE ffa_assembly_seats SET verdict_at = clock_timestamp() - interval '61 minutes'"
            " WHERE lobby_id = $1 AND slot = 4", lob.lid)
        n, a = await notice(lob, 4)
        assert n is None, ("S29 60 minutes", a)
        await env.conn.execute(
            "UPDATE ffa_assembly_seats SET verdict_at = clock_timestamp() - interval '59 minutes'"
            " WHERE lobby_id = $1 AND slot = 4", lob.lid)
        n, a = await notice(lob, 4)
        assert n == want(lob, "started"), ("S29 59 minutes", a)
    run_env(monkeypatch, body, skip=("reform_rows_left",))


# -- S30: the I5 projection --

_S30_UUID = _re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}")
_S30_DIG = _re.compile(r"[0-9]{17}")
_S30_TOKENS = {"tie": {"measured", "lexical"},
               "state": {"absent", "stale", "missing_baseline", "fresh"},
               "admitted_by": {"majority", "bounded"}}


def _s30_clean(out, tag):
    """No UUID-shaped value, no 17-digit run, and no string outside its
    key's vocabulary anywhere in the projection."""
    blob = _json.dumps(out)
    assert not _S30_UUID.search(blob) and not _S30_DIG.search(blob), (tag, "ids", blob)

    def walk(o, key=None):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, list):
            for v in o:
                walk(v, key)
        elif isinstance(o, str):
            if key in ("baseline", "region"):
                assert main._REGION_CODE_RE.match(o), (tag, key, o)
            else:
                assert o in _S30_TOKENS.get(key, ()), (tag, "free text", key, o)
        elif isinstance(o, bool):
            assert key in ("error",), (tag, "bool", key)
        elif isinstance(o, int):
            assert 0 <= o <= 100000 or key == "v", (tag, "clamp", key, o)
        else:
            assert o is None, (tag, "type", key, type(o).__name__)
    walk(out)


class _S30Exploding(dict):
    def get(self, *a, **k):
        raise ValueError("secret 76561190035500001 " + str(uuid.uuid4()))


def _s30_raw(ids):
    return {
        "baseline": "eu", "tie": "measured", "n": 3, "sum_b": 250000, "sum_pick": -5,
        "worst_b": 12.7, "worst_pick": True, "gain": float("nan"), "max_regret": "12",
        "seats": [{"id": ids[0], "state": "fresh", "cost_b": 10, "cost_pick": 20,
                   "name": "free text"},
                  {"id": ids[1], "state": "hacked", "cost_b": 1e12, "cost_pick": None},
                  {"id": "76561190035500001", "state": "fresh", "cost_b": 1},
                  "not a dict"],
        "candidates": [{"region": "us", "sum": 3, "worst": 4, "gain": 5, "max_regret": 6,
                        "admitted_by": "majority", "note": "x"},
                       {"region": "US!", "sum": 1},
                       {"region": "asia", "admitted_by": "other text"}],
        "steam": "76561190035500009", "lobby": ids[2], "text": "free words"}


def test_s30_the_region_projection(monkeypatch):
    """S30: for each why token and the error path: v = 1, the whitelisted
    keys, slots for ids, integers clamped, no UUID-shaped, 17-digit or
    free-text value; the error collapses to {"v": 1, "error": true}; a Start
    stores the projection on the lobby row."""
    ids = [str(uuid.uuid4()) for _ in range(3)]
    slot_of = {ids[0]: 0, ids[1]: 1, ids[2]: 2}
    raw = _s30_raw(ids)
    top = {"v", "baseline", "tie", "n", "sum_b", "sum_pick", "worst_b", "worst_pick", "gain",
           "max_regret", "seats", "candidates"}
    for why in ("baseline", "majority", "bounded", "quorum", "surprise"):
        tok, out = main._region_projection(why, raw, slot_of)
        assert tok == (why if why != "surprise" else "other"), ("S30 token", why, tok)
        assert out["v"] == 1 and set(out) == top, ("S30 keys", why, sorted(out))
        assert out["seats"] == [{"slot": 0, "state": "fresh", "cost_b": 10, "cost_pick": 20},
                                {"slot": 1, "state": None, "cost_b": 100000,
                                 "cost_pick": None}], ("S30 seats", why, out["seats"])
        assert out["candidates"] == [
            {"region": "us", "sum": 3, "worst": 4, "gain": 5, "max_regret": 6,
             "admitted_by": "majority"},
            {"region": "asia", "sum": None, "worst": None, "gain": None, "max_regret": None,
             "admitted_by": None}], ("S30 candidates", why, out["candidates"])
        assert (out["baseline"], out["tie"], out["n"], out["sum_b"], out["sum_pick"],
                out["worst_b"], out["worst_pick"], out["gain"], out["max_regret"]) == \
            ("eu", "measured", 3, 100000, 0, 12, None, None, None), ("S30 scalars", why, out)
        _s30_clean(out, why)
    for why, r in (("error", raw), ("baseline", {"error": "Traceback 76561190035500001"}),
                   ("majority", "not a dict"), ("bounded", _S30Exploding()),
                   ("quorum", None)):
        tok, out = main._region_projection(why, r, slot_of)
        assert out == {"v": 1, "error": True}, ("S30 error form", why, out)

    async def body(env):
        seen = {}

        async def fake_region(db, ordered, mode, label, room=None, explain=None):
            hostile = _s30_raw([str(ordered[0]["player_id"]), str(ordered[1]["player_id"]),
                                str(uuid.uuid4())])
            if explain is not None:
                explain["why"] = seen["why"]
                explain["raw"] = hostile
            return "eu"
        monkeypatch.setattr(main, "_group_region", fake_region)
        for why in ("bounded", "error"):
            seen["why"] = why
            lob = await _open_lobby(env, 4, ["ffa_asm1,ffa_adm1"] * 4)
            a = await _start(env, main, lob)
            assert a.status == 200, ("S30 start", why, a)
            row = await env.lobby_row(lob)
            detail = row["region_detail"]
            detail = _json.loads(detail) if isinstance(detail, str) else detail
            assert row["region_why"] == why, ("S30 stored token", why, row["region_why"])
            if why == "error":
                assert detail == {"v": 1, "error": True}, ("S30 stored error", detail)
            else:
                assert [s["slot"] for s in detail["seats"]] == [0, 1], ("S30 stored", detail)
                _s30_clean(detail, "stored")
    run_env(monkeypatch, body)


# -- the answer tour: every answer shape, for S34, S51 and S65 --

async def _answer_tour(env, monkeypatch):
    """Drive one answer of every shape of the connect and assembly routes (the
    I2 answer table, states A-E), the poll's lock payload, and a reformed
    answer. Returns [(label, answer, t, lobby_kind, started)] with t the
    lobby age the answer was built at (the frozen clock), lobby_kind
    'admission', 'fallback' or 'ungated', and started whether the lobby held
    start_granted_at when the answer was built."""
    out = []

    def rec(label, a, t, kind, started, status=None):
        assert a.status == 200, (label, a)
        if status is not None:
            got = a["status"]
            assert got == status, (label, got, a)
        out.append((label, a, t, kind, started))
    # L1: an admission lobby, seat 4 never offered its lock.
    l1 = await env.lobby(5, admission=True, offered=[0, 1, 2, 3], t=12.5)
    rec("A assembling connect", await env.connect(l1, 3, "lock_seen"), 12.5, "admission",
        False, "assembling")
    rec("A assembling assembly", await env.assembly(l1, 3, 4, [env.entry(l1, 3, 4)]), 12.5,
        "admission", False, "assembling")
    rec("A admitted", await env.connect(l1, 2, "arrived", region="eu", actor=3, count=4), 12.5,
        "admission", False, "admitted")
    monkeypatch.setattr(main, "JOIN_REGION_GUARD", True)
    rec("A wrong_region", await env.connect(l1, 1, "arrived", region="us", actor=2, count=4),
        12.5, "admission", False, "wrong_region")
    monkeypatch.setattr(main, "JOIN_REGION_GUARD", False)
    rec("payload admission", await env.poll(l1, 0), 12.5, "admission", False, "ready_join")
    await env.at(l1, 20.0)
    a = await _post(env, l1, 0, [0, 1, 2, 3])
    assert a["status"] == "start_ok" and (await env.lobby_row(l1))["asm_rule"] == "E", \
        ("tour start at 20", a)
    await env.at(l1, 31.5)
    rec("B start_ok connect", await env.connect(l1, 0, "lock_seen"), 31.5, "admission", True,
        "start_ok")
    rec("B start_ok assembly", await env.census_of(l1, 1, [0, 1, 2, 3]), 31.5, "admission",
        True, "start_ok")
    rec("payload started", await env.poll(l1, 0), 31.5, "admission", True, "ready_join")
    rec("C admitting connect", await env.connect(l1, 4, "lock_seen"), 31.5, "admission", True,
        "admitting")
    await env.at(l1, 33.0)
    ent = [env.entry(l1, s, 1 + s) for s in range(5)]
    rec("C admitting assembly", await env.assembly(l1, 4, 5, ent), 33.0, "admission", True,
        "admitting")
    rec("B admission answer", await env.assembly(l1, 0, 1, ent), 33.0, "admission", True,
        "start_ok")
    assert (await env.seat(l1, 4))["verdict"] == "admitted_late", "tour admission"
    await env.at(l1, 34.5)
    rec("D admitted_late connect", await env.connect(l1, 4, "lock_seen"), 34.5, "admission",
        True, "admitted_late")
    rec("D admitted_late assembly", await env.assembly(l1, 4, 5, ent), 34.5, "admission", True,
        "admitted_late")
    # L2: a short-started lobby, since closed, with an admissible and an
    # admitted seat whose body never entered.
    l2 = await _short(env, 6)
    await env.at(l2, 45.0)
    await _admit(env, l2, 5, 6, 0, [0, 1, 2, 3])
    await env.set_lobby(l2, status="completed")
    await env.at(l2, 50.0)
    for slot, st in ((4, "C"), (5, "D")):
        rec(st + " dissolved connect", await env.connect(l2, slot, "lock_seen"), 50.0,
            "admission", True, "dissolved")
        rec(st + " dissolved assembly", await env.assembly(l2, slot, 1 + slot, [env.entry(l2, 0, 1)]), 50.0,
            "admission", True, "dissolved")
    # L3: a fallback REFORM at 40 (seat 4 excluded); L4: a DISSOLVE at 40.
    l3 = await env.lobby(5, t=40.0)
    a = await _post(env, l3, 0, [0, 1, 2, 3])
    assert a["status"] == "reformed", ("tour reform", a)
    await env.at(l3, 41.25)
    rec("E reformed connect", await env.connect(l3, 1, "lock_seen"), 41.25, "fallback", False,
        "reformed")
    rec("E reformed assembly", await env.census_of(l3, 2, [0, 1, 2, 3]), 41.25, "fallback",
        False, "reformed")
    rec("E excluded connect", await env.connect(l3, 4, "lock_seen"), 41.25, "fallback", False,
        "excluded")
    rec("E excluded assembly", await env.census_of(l3, 4, [4]), 41.25, "fallback", False,
        "excluded")
    l4 = await env.lobby(4, t=40.0)
    await _post(env, l4, 0, [0, 1])
    assert (await env.lobby_row(l4))["status"] == "canceled", "tour dissolve"
    await env.at(l4, 42.75)
    rec("E dissolved connect", await env.connect(l4, 0, "lock_seen"), 42.75, "fallback", False,
        "dissolved")
    rec("E dissolved assembly", await env.census_of(l4, 1, [0, 1]), 42.75, "fallback", False,
        "dissolved")
    l6 = await env.lobby(5, t=13.5)
    rec("A fallback assembling", await env.connect(l6, 0, "lock_seen"), 13.5, "fallback", False,
        "assembling")
    rec("payload fallback", await env.poll(l6, 0), 13.5, "fallback", False, "ready_join")
    # L5: an ungated lobby.
    l5 = await env.lobby(4, gated=False, t=5.5)
    rec("A ungated connect", await env.connect(l5, 0, "lock_seen"), 5.5, "ungated", False,
        "assembling")
    rec("payload ungated", await env.poll(l5, 0), 5.5, "ungated", False, "ready_join")
    return out


def test_s34_server_age_ms_on_every_answer(monkeypatch):
    """S34: server_age_ms on the lock payload, every connect and assembly
    answer and the seat-row answers, exact on the frozen clock; the tour's
    admission lobby decided at 20 (verdict_at 20 s after created_at)."""
    async def body(env):
        tour = await _answer_tour(env, monkeypatch)
        for label, a, t, _kind, _st in tour:
            got = a.get("server_age_ms")
            assert got == int(round(t * 1000)), ("S34", label, got, t)
            if a.get("status") == "reformed":
                emb = a["lock"].get("server_age_ms")
                assert isinstance(emb, int) and emb >= 0, ("S34 embedded", label, emb)
    run_env(monkeypatch, body, skip=("reform_rows_left",))


def test_s51_admit_left_ms(monkeypatch):
    """S51: every answer to a seat of an admission lobby (admitted,
    admitting, assembling, the lock payload) carries admit_left_ms = A - now
    floored at 0; a fallback or ungated lobby's carries ASM_JOIN_CAP_S."""
    async def body(env):
        tour = await _answer_tour(env, monkeypatch)
        seen = set()
        for label, a, t, kind, _st in tour:
            if a.get("status") not in ("admitted", "admitting", "assembling", "ready_join"):
                continue
            want = (max(0, int(round((140.0 - t) * 1000))) if kind == "admission"
                    else main.ASM_JOIN_CAP_S * 1000)
            got = a.get("admit_left_ms")
            assert got == want, ("S51", label, got, want)
            seen.add((a["status"], kind))
        assert {("admitted", "admission"), ("admitting", "admission"),
                ("assembling", "admission"), ("ready_join", "admission"),
                ("assembling", "fallback"), ("ready_join", "fallback")} <= seen, ("S51 seen", seen)
        lob = await _short(env)
        await env.at(lob, 150.0)
        a = await env.poll(lob, 0)
        assert a["status"] == "ready_join" and a["admit_left_ms"] == 0, ("S51 floor", a)
    run_env(monkeypatch, body, skip=("reform_rows_left",))


def test_s65_the_sittings_state_on_every_answer(monkeypatch):
    """S65: every connect and assembly answer of every state, and every lock
    payload, carries assembly and asm_started; asm_started is 0 before
    start_granted_at and 1 after it with games_played 0; a reformed
    answer's embedded payload carries the new lobby's values; an ungated
    lobby answers assembly 0."""
    async def body(env):
        tour = await _answer_tour(env, monkeypatch)
        for label, a, _t, kind, started in tour:
            assert "assembly" in a.body and "asm_started" in a.body, ("S65 keys", label, a)
            assert a["assembly"] == (0 if kind == "ungated" else 1), ("S65 assembly", label, a)
            assert a["asm_started"] == (1 if started else 0), ("S65 asm_started", label, a)
            if a.get("status") == "reformed":
                emb = a["lock"]
                assert (emb.get("assembly"), emb.get("asm_started")) == (1, 0), \
                    ("S65 embedded", label, emb)
        assert any(a.get("status") == "start_ok" for _l, a, _t, _k, _s in tour), "S65 B seen"
    run_env(monkeypatch, body, skip=("reform_rows_left",))


# -- identity, admission, expiry, START-SHORT's rows, start_n, spawn_ok, the
#    body rule, entered, started, READY, the census echo, the granted list,
#    the binding after a grant, the kept epoch (S37, S40-S42, S44-S47, S49,
#    S50, S59-S63) --

@pytest.mark.parametrize("case", ["i", "ii", "iii", "iv"])
def test_s37_identity_and_substitution(monkeypatch, case):
    """S37 (i)-(iv), one node per fixture."""
    async def body(env):
        if case == "i":
            # (i) three published seats, a fourth whose entries carry s = "".
            lob = await env.lobby(4, t=10.0)

            def ents(named):
                e = [env.entry(lob, s, 1 + s) for s in (0, 1, 2)]
                return e + [env.entry(lob, 3, 4, anon=not named)]
            for s in (0, 1, 2, 3):
                a = await env.assembly(lob, s, 1 + s, ents(False))
            seats = await env.seats(lob)
            assert [x["actor_nr"] for x in seats] == [1, 2, 3, None], ("S37 i bound", seats)
            assert all(x["body_seen_at"] is not None for x in seats[:3]), "S37 i bodied"
            assert a["pending"] == 1, ("S37 i pending", a)
            for s in (0, 1, 2, 3):
                a = await env.assembly(lob, s, 1 + s, ents(True))
            assert (await env.seat(lob, 3))["actor_nr"] == 4 and a["pending"] == 0, \
                ("S37 i one round later", a)
        elif case == "ii":
            # (ii) X claims the actor a peer lists anonymously; an absent seat
            # with no census of its own stays PENDING whatever its peers list.
            lob = await env.lobby(5, t=10.0)
            peer = [env.entry(lob, s, 1 + s) for s in (0, 1, 2)] + \
                [{"a": 9, "s": "", "b": 1, "k": 1}, env.entry(lob, 4, 5)]
            for s in (0, 1, 2):
                await env.assembly(lob, s, 1 + s, peer)
            a = await env.assembly(lob, 3, 9, [env.entry(lob, 3, 9)])
            seats = await env.seats(lob)
            assert seats[3]["actor_nr"] is None and seats[3]["actor_claim"] == 9, \
                ("S37 ii substitution", seats[3]["actor_nr"])
            assert seats[4]["actor_nr"] is None and a["pending"] == 2, ("S37 ii absent", a)
        elif case == "iii":
            # (iii) two claims of one actor in one region: the first binds.
            lob = await env.lobby(5, t=10.0)
            await env.ready_all(lob, [0, 1])
            await env.assembly(lob, 2, 7, [env.entry(lob, 2, 7)])
            await env.assembly(lob, 3, 7, [env.entry(lob, 3, 7)])
            await env.assembly(lob, 0, 1, [env.entry(lob, 0, 1), env.entry(lob, 1, 2),
                                           env.entry(lob, 2, 7)])
            assert (await env.seat(lob, 2))["actor_nr"] == 7, "S37 iii first binds"
            await env.assembly(lob, 1, 2, [env.entry(lob, 0, 1), env.entry(lob, 1, 2),
                                           env.entry(lob, 3, 7)])
            assert (await env.seat(lob, 3))["actor_nr"] is None, "S37 iii second unbound"
            assert env.asm_lines("lobby %s actor_conflict slot=3" % str(lob.lid)[:8]), \
                ("S37 iii print", env.asm_lines("actor_conflict"))
        else:
            # (iv) a census from another region than the claim's does not bind.
            lob = await env.lobby(5, t=10.0)
            await env.assembly(lob, 3, 4, [env.entry(lob, 3, 4)])
            for p in (0, 1):
                await env.assembly(lob, p, 1 + p,
                                   [env.entry(lob, p, 1 + p), env.entry(lob, 3, 4)],
                                   region="us")
            assert (await env.seat(lob, 3))["actor_nr"] is None, "S37 iv region"
            await env.assembly(lob, 2, 3, [env.entry(lob, 2, 3), env.entry(lob, 3, 4)])
            assert (await env.seat(lob, 3))["actor_nr"] == 4, "S37 iv control binds from eu"
    run_env(monkeypatch, body)


def test_s40_the_admission(monkeypatch):
    """S40: own census alone stays admitting; one peer entry admits in one
    transaction; two peers without its own census neither admit nor bind; a
    fault after the binding statement rolls everything back; the late list
    for every granted seat until late_body_game, entered removing nothing."""
    async def body(env):
        lob = await _short(env)
        await env.at(lob, 50.0)
        ent = [env.entry(lob, s, 1 + s) for s in range(5)]
        for _ in range(2):
            a = await env.assembly(lob, 4, 5, ent)
            assert a["status"] == "admitting", ("S40 own only", a)
        s = await env.seat(lob, 4)
        assert (s["verdict"], s["actor_nr"]) == ("admissible", None), ("S40 own only row", s)
        await env.assembly(lob, 0, 1, ent)
        s = await env.seat(lob, 4)
        got = (s["actor_nr"], s["actor_region"], s["verdict"], s["late_admitted_at"],
               s["late_game"])
        assert got == (5, "eu", "admitted_late", env.now, 1), ("S40 admitted", got)
        want = [{"slot": 4, "actor": 5}]
        for slot in (0, 1, 2, 3):
            a = await env.connect(lob, slot, "lock_seen")
            assert a["late"] == want and all(e["actor"] is not None for e in a["late"]), \
                ("S40 late", slot, a)
        await env.at(lob, 52.0)
        await env.connect(lob, 4, "entered", game=1)
        a = await env.connect(lob, 1, "lock_seen")
        assert a["late"] == want, ("S40 entered removes nothing", a)
        await env.at(lob, 55.0)
        for w in (0, 1):
            await env.assembly(lob, w, 1 + w, ent, game=1)
        assert (await env.seat(lob, 4))["late_body_game"] == 1, "S40 late body"
        a = await env.connect(lob, 2, "lock_seen")
        assert a["late"] == [], ("S40 late after the body", a)
        # two peers' censuses and none of its own: admitting, nothing bound.
        lob = await _short(env)
        await env.at(lob, 50.0)
        ent = [env.entry(lob, s, 1 + s) for s in range(5)]
        for p in (0, 1):
            await env.assembly(lob, p, 1 + p, ent)
        s = await env.seat(lob, 4)
        assert (s["verdict"], s["actor_nr"], s["actor_region"]) == ("admissible", None, None), \
            ("S40 peers only", s["verdict"], s["actor_nr"])
        a = await env.connect(lob, 4, "lock_seen")
        assert a["status"] == "admitting", ("S40 peers only answer", a)
        # a fault after the binding statement: a second session reads none.
        lob = await _short(env)
        await env.at(lob, 50.0)
        ent = [env.entry(lob, s, 1 + s) for s in range(5)]
        await env.assembly(lob, 4, 5, ent)
        real = main._ffa_epoch_chain

        def boom(*a, **k):
            raise RuntimeError("cf fault after the binding statement")
        monkeypatch.setattr(main, "_ffa_epoch_chain", boom)
        try:
            with pytest.raises(RuntimeError):
                await env.assembly(lob, 0, 1, ent)
        finally:
            monkeypatch.setattr(main, "_ffa_epoch_chain", real)
        s = await env.seat(lob, 4)
        got = (s["verdict"], s["actor_nr"], s["actor_region"], s["late_admitted_at"],
               s["late_game"])
        assert got == ("admissible", None, None, None, None), ("S40 fault", got)
        assert await env.conn.fetchval("SELECT count(*) FROM ffa_kept_epochs WHERE lobby_id = $1",
                                       lob.lid) == 0, "S40 fault epoch"
    run_env(monkeypatch, body)


@pytest.mark.parametrize("route", ["connect", "assembly", "poll", "leave", "report"])
def test_s41_the_expiry_at_a(monkeypatch, route):
    """S41: at 139.9 still admissible; at 140.0 the first touch of each route
    (one node per route) excludes it, deletes its queue row and lease,
    appends it to departed_ids once and leaves departure_causes; a second
    call changes nothing; no admission at or after A (the seat is
    corroborated at 140.0)."""
    async def body(env):
        def res(lob):
            return {lob.sids[0]: (5, 10), lob.sids[1]: (3, 6), lob.sids[2]: (2, 4),
                    lob.sids[3]: (1, 2)}
        touches = {
            "connect": lambda lob: env.connect(lob, 0, "lock_seen"),
            "assembly": lambda lob: env.census_of(lob, 0, [0, 1, 2, 3]),
            "poll": lambda lob: env.poll(lob, 0),
            "leave": lambda lob: env.leave(lob, 3),
            "report": lambda lob: env.report(lob, 1, res(lob))}
        touch = touches[route]
        lob = await _short(env)
        await env.at(lob, 139.9)
        await env.connect(lob, 1, "lock_seen")
        s = await env.seat(lob, 4)
        assert s["verdict"] == "admissible" and await env.queue_row(lob, 4) is not None \
            and await env.lease(lob, 4) is not None, ("S41 139.9", route, s["verdict"])
        assert list((await env.lobby_row(lob))["departed_ids"] or []) == [], "S41 139.9 dep"
        await env.at(lob, 140.0)
        allv = [(x, 1 + x, 1, 1) for x in range(5)]
        await env.census_row(lob, 4, allv, claim=5)
        await env.census_row(lob, 1, allv, claim=2)
        causes = (await env.lobby_row(lob))["departure_causes"]
        a = await touch(lob)
        assert a.status == 200, ("S41 touch", route, a)
        s = await env.seat(lob, 4)
        row = await env.lobby_row(lob)
        assert (s["verdict"], s["actor_nr"], s["late_admitted_at"]) == \
            ("excluded", None, None), ("S41 excluded", route, s["verdict"], s["actor_nr"])
        assert await env.queue_row(lob, 4) is None and await env.lease(lob, 4) is None, \
            ("S41 released", route)
        assert list(row["departed_ids"]).count(lob.pids[4]) == 1, ("S41 once", route)
        assert row["departure_causes"] == causes, ("S41 causes", route)
        snap = (s, list(row["departed_ids"]))
        await touch(lob)
        s2 = await env.seat(lob, 4)
        row2 = await env.lobby_row(lob)
        assert (s2, list(row2["departed_ids"])) == snap, ("S41 second call", route)
        lines = env.asm_lines("lobby %s admission expired slot=4" % str(lob.lid)[:8])
        assert len(lines) == 1, ("S41 one expiry line", route, lines)
    run_env(monkeypatch, body)


def test_s42_start_shorts_rows(monkeypatch):
    """S42: LEFT members appended to departed_ids, admissible seats not; the
    host passes to the earliest-joined start-roster seat where joined_at
    order differs from slot and Steam-id order; bets_disabled and
    short_started_at together."""
    async def body(env):
        lob = await env.lobby(5, admission=True, t=7.0, joined=[0, 3, 2, 1, 4], host_slot=0)
        await env.at(lob, 8.0)
        await env.leave(lob, 0)
        await env.at(lob, 20.0)
        try:
            a = await _post(env, lob, 1, [1, 2, 3])
        except Exception as exc:          # START-SHORT's transaction rolled back
            a = {"status": "raised", "error": type(exc).__name__}
        assert a["status"] == "start_ok", ("S42 start", a)
        row = await env.lobby_row(lob)
        assert row["asm_rule"] == "D", ("S42 rule", row["asm_rule"])
        assert list(row["departed_ids"]) == [lob.pids[0]], ("S42 departed", row["departed_ids"])
        assert (await env.seat(lob, 4))["verdict"] == "admissible", "S42 admissible"
        assert row["host_player_id"] == lob.pids[3], ("S42 host", lob.pids.index(
            row["host_player_id"]) if row["host_player_id"] in lob.pids else None)
        assert row["bets_disabled"] is True and row["short_started_at"] is not None, \
            ("S42 bets", row["bets_disabled"], row["short_started_at"])
    run_env(monkeypatch, body)


def _slots(a):
    return [r["slot"] for r in a["roster"]]


def test_s44_the_live_start_n(monkeypatch):
    """S44 (N8): a start-roster seat's leave while the current witnesses list
    it moves nothing (start_n 4); the gone record from two omitting
    witnesses lowers start_n to 3; censuses without its body, its own failed
    phase=spawn, a full-room grant and anything after A move nothing."""
    async def body(env):
        lob = await _short(env)
        await env.at(lob, 50.0)
        full = [(s, 1 + s, 1, 1) for s in range(4)]
        for w in (0, 1, 2):
            await env.census_row(lob, w, full, claim=1 + w)
        await env.leave(lob, 3)
        s3 = await env.seat(lob, 3)
        assert (s3["verdict"], s3["gone_game"]) == ("granted", None), ("S44 leave", s3["verdict"])
        a = await env.connect(lob, 0, "lock_seen")
        assert a["start_n"] == 4 and _slots(a) == [0, 1, 2, 3], ("S44 after leave", a)
        await env.at(lob, 62.0)
        omit = [(s, 1 + s, 1, 1) for s in (0, 1, 2)]
        await env.census_row(lob, 2, omit, claim=3)
        await env.assembly(lob, 0, 1, [env.entry(lob, s, 1 + s) for s in (0, 1, 2)])
        s3 = await env.seat(lob, 3)
        assert (s3["gone_game"], s3["gone_path"]) == (1, "leave"), ("S44 gone", s3["gone_game"])
        a = await env.connect(lob, 1, "lock_seen")
        assert a["start_n"] == 3 and _slots(a) == [0, 1, 2], ("S44 lowered", a)
        # no body in two peers' censuses built 23 s after spawn_ok_at; its own
        # failed phase=spawn; a seeded bodiless_at (V4's lowering input).
        lob = await _short(env)
        await env.set_seat(lob, 2, spawn_ok_at=40.0)
        await env.at(lob, 64.0)
        nob = [env.entry(lob, s, 1 + s, b=0 if s == 2 else 1) for s in range(4)]
        for w in (0, 1):
            await env.assembly(lob, w, 1 + w, nob, seen_age_ms=63500)
        await env.connect(lob, 2, "failed", phase="spawn", code=1, state="Spawning")
        s2 = await env.seat(lob, 2)
        assert s2["verdict"] == "granted" and s2["bodiless_at"] is None, \
            ("S44 no body", s2["verdict"], s2["bodiless_at"])
        a = await env.connect(lob, 0, "lock_seen")
        assert a["start_n"] == 4 and _slots(a) == [0, 1, 2, 3], ("S44 no body start_n", a)
        await env.set_seat(lob, 2, bodiless_at=64.0)
        a = await env.connect(lob, 1, "lock_seen")
        assert a["start_n"] == 4 and _slots(a) == [0, 1, 2, 3], ("S44 seeded bodiless", a)
        # a full-room grant: a gone record lowers nothing.
        lob = await env.lobby(5, t=30.0)
        await _full_grant(env, lob, 30.0)
        await env.at(lob, 50.0)
        await env.leave(lob, 4)
        await env.at(lob, 62.0)
        present = [(s, 1 + s, 1, 1) for s in range(4)]
        await env.census_row(lob, 2, present, claim=3)
        await env.assembly(lob, 0, 1, [env.entry(lob, s, 1 + s) for s in range(4)])
        assert (await env.seat(lob, 4))["gone_game"] == 1, "S44 full grant gone"
        a = await env.connect(lob, 1, "lock_seen")
        assert a["start_n"] == 5 and _slots(a) == [0, 1, 2, 3, 4], ("S44 full grant", a)
        # after A: a gone record lowers nothing.
        lob = await _short(env)
        await env.at(lob, 141.0)
        await env.leave(lob, 3)
        await env.at(lob, 153.0)
        await env.census_row(lob, 2, omit, claim=3)
        await env.assembly(lob, 0, 1, [env.entry(lob, s, 1 + s) for s in (0, 1, 2)])
        assert (await env.seat(lob, 3))["gone_game"] == 1, "S44 after A gone"
        a = await env.connect(lob, 1, "lock_seen")
        assert a["start_n"] == 4 and _slots(a) == [0, 1, 2, 3], ("S44 after A", a)
    run_env(monkeypatch, body)


def test_s45_spawn_ok_and_its_window(monkeypatch):
    """S45: spawn_ok 1 at 14.9 uncorroborated; 0 at 15.0 until corroborated,
    then 1; start_ok carries 1; admitting and admitted_late carry 0;
    spawn_ok_at first write wins; spawn_ok_age_ms on every state-A answer
    carrying 1, identical 3 s later; the lock payload's spawn_open_s 6."""
    async def body(env):
        lob = await env.lobby(5, admission=True, t=11.0)
        for route in ("connect", "assembly"):
            a = (await env.connect(lob, 4, "lock_seen") if route == "connect"
                 else await env.assembly(lob, 4, 5, [env.entry(lob, 4, 5)]))
            assert (a["spawn_ok"], a.get("spawn_ok_age_ms")) == (1, 11000), ("S45 11", route, a)
        await env.at(lob, 14.0)
        for route in ("connect", "assembly"):
            a = (await env.connect(lob, 4, "lock_seen") if route == "connect"
                 else await env.assembly(lob, 4, 5, [env.entry(lob, 4, 5)]))
            assert (a["spawn_ok"], a.get("spawn_ok_age_ms")) == (1, 11000), ("S45 14", route, a)
        assert (await env.seat(lob, 4))["spawn_ok_at"] == await env.ts(lob, 11.0), "S45 first"
        lob = await env.lobby(5, admission=True, t=14.9)
        a = await env.connect(lob, 4, "lock_seen")
        assert (a["spawn_ok"], a.get("spawn_ok_age_ms")) == (1, 14900), ("S45 14.9", a)
        lob = await env.lobby(5, admission=True, t=15.0)
        a = await env.connect(lob, 4, "lock_seen")
        assert a["spawn_ok"] == 0 and "spawn_ok_age_ms" not in a.body, ("S45 15.0", a)
        assert (await env.seat(lob, 4))["spawn_ok_at"] is None, "S45 15.0 unwritten"
        await env.ready_all(lob, [0, 1, 2, 3, 4])
        a = await env.connect(lob, 4, "lock_seen")
        assert (a["spawn_ok"], a.get("spawn_ok_age_ms")) == (1, 15000), ("S45 corroborated", a)
        p = await env.poll(lob, 0)
        assert p["spawn_open_s"] == 6, ("S45 payload", p)
        lob = await env.lobby(6, admission=True, t=40.0)
        a = await _post(env, lob, 0, [0, 1, 2, 3])
        assert (a["status"], a["spawn_ok"]) == ("start_ok", 1), ("S45 start_ok", a)
        await env.at(lob, 45.0)
        await _admit(env, lob, 5, 6, 0, [0, 1, 2, 3])
        for slot, st in ((4, "admitting"), (5, "admitted_late")):
            a = await env.connect(lob, slot, "lock_seen")
            assert (a["status"], a["spawn_ok"]) == (st, 0), ("S45", st, a)
        a = await env.connect(lob, 1, "lock_seen")
        assert (a["status"], a["spawn_ok"]) == ("start_ok", 1), ("S45 start_ok 2", a)
    run_env(monkeypatch, body)


async def _body_rule(env, lob):
    """The body rule alone, in its own transaction under the lobby lock (a
    function-level fixture: the verdict would decide at these ages)."""
    async with env.sm() as db:
        ctx = await main._asm_ctx_slot(db, lob.lid, route="assembly", trigger="assembly")
        await main._asm_body(ctx)
        await db.commit()
    return await env.seat(lob, 4)


@pytest.mark.parametrize("case", ["i", "i-late", "iii", "iv", "v"])
def test_s46_the_body_rule(monkeypatch, case):
    """S46 (i)-(v), one node per fixture: the grace on census_seen_at, two
    other non-final censuses, never the seat's own, and the maximum-latency
    healthy spawn. Node i also carries (ii) on its lobby."""
    async def body(env):
        async def subject(t, spawn_ok):
            lob = await env.lobby(5, admission=True, t=t)
            await env.set_seat(lob, 4, actor_claim=5, claim_region="eu", actor_nr=5,
                               actor_region="eu", spawn_ok_at=spawn_ok)
            return lob

        def lst(b):
            return [(0, 1, 1, 1), (4, 5, b, 1)]
        if case == "i":
            # (i) two fresh censuses built at the reference + 23 or later.
            lob = await subject(36.0, 10.0)
            await env.census_row(lob, 0, lst(0), t_at=35.0, seen=34.0)
            s = await _body_rule(env, lob)
            assert s["bodiless_at"] is None, "S46 i one census"
            await env.census_row(lob, 1, lst(0), t_at=35.5, seen=33.0)
            s = await _body_rule(env, lob)
            assert s["bodiless_at"] == env.now and s["body_seen_at"] is None, "S46 i two"
            # (ii) two later censuses listing it b = 1: body_seen_at.
            await env.at(lob, 37.0)
            for p in (2, 3):
                await env.census_row(lob, p, lst(1))
            s = await _body_rule(env, lob)
            assert s["body_seen_at"] == env.now, ("S46 ii", s["body_seen_at"])
        elif case == "i-late":
            # (i) a census built at +22.9 does not count, however late it arrives.
            lob = await subject(41.0, 10.0)
            await env.census_row(lob, 0, lst(0), t_at=40.0, seen=33.5)
            await env.census_row(lob, 1, lst(0), t_at=40.0, seen=32.9)
            s = await _body_rule(env, lob)
            assert s["bodiless_at"] is None, "S46 i 22.9"
        elif case == "iii":
            # (iii) the seat's own census never counts.
            lob = await subject(36.0, 10.0)
            await env.census_row(lob, 4, lst(0), seen=34.0)
            await env.census_row(lob, 0, lst(0), seen=34.0)
            s = await _body_rule(env, lob)
            assert s["bodiless_at"] is None, "S46 iii own bodiless"
            await env.census_row(lob, 4, lst(1))
            await env.census_row(lob, 0, lst(1))
            s = await _body_rule(env, lob)
            assert s["body_seen_at"] is None, "S46 iii own body"
        elif case == "iv":
            # (iv) a final row's census never counts.
            lob = await subject(36.0, 10.0)
            await env.set_seat(lob, 3, verdict="left", verdict_at=30.0, left_at=30.0)
            await env.census_row(lob, 3, lst(0), seen=34.0)
            await env.census_row(lob, 0, lst(0), seen=34.0)
            s = await _body_rule(env, lob)
            assert s["bodiless_at"] is None, "S46 iv final bodiless"
            await env.census_row(lob, 3, lst(1))
            await env.census_row(lob, 0, lst(1))
            s = await _body_rule(env, lob)
            assert s["body_seen_at"] is None, "S46 iv final body"
        else:
            # (v) the maximum-latency healthy spawn: spawn_ok_at +33.
            lob = await subject(49.0, 33.0)
            for p in (0, 1):
                await env.census_row(lob, p, lst(0), t_at=49.0, seen=48.5)
            s = await _body_rule(env, lob)
            assert s["bodiless_at"] is None, "S46 v +49"
            for t_arr in (59.5, 60.0):
                await env.at(lob, t_arr)
                for p in (0, 1):
                    await env.census_row(lob, p, lst(0), t_at=t_arr, seen=55.5)
                s = await _body_rule(env, lob)
                assert s["bodiless_at"] is None, ("S46 v", t_arr)
            await env.at(lob, 60.5)
            for p in (2, 3):
                await env.census_row(lob, p, lst(1), t_at=60.5, seen=56.0)
            s = await _body_rule(env, lob)
            assert s["bodiless_at"] is None and s["body_seen_at"] == env.now, \
                ("S46 v body", s["bodiless_at"], s["body_seen_at"])
    run_env(monkeypatch, body)


def test_s47_entered_is_telemetry(monkeypatch):
    """S47: entered writes only late_entered_at and late_game_claim, first
    write wins; it leaves the seat in late; writer 7's rows and every rating
    input are identical with and without the POST (a claim of game 3 beside
    a late_game of 1)."""
    async def body(env):
        async def sitting(entered):
            lob = await _short(env)
            await env.at(lob, 50.0)
            await _admit(env, lob, 4, 5, 0, [0, 1, 2, 3])
            await env.at(lob, 55.0)
            if entered:
                before = await env.seat(lob, 4)
                a = await env.connect(lob, 4, "entered", game=3)
                after = await env.seat(lob, 4)
                assert _changed(before, after, ignore=("writes", "client_ms")) == \
                    {"late_entered_at", "late_game_claim"}, ("S47 cell", _changed(before, after))
                assert a["status"] == "admitted_late" and a["late"] == [{"slot": 4, "actor": 5}], \
                    ("S47 answer", a)
                await env.connect(lob, 4, "entered", game=1)
                again = await env.seat(lob, 4)
                assert (again["late_game_claim"], again["late_entered_at"]) == \
                    (3, after["late_entered_at"]), "S47 first write wins"
                a = await env.connect(lob, 0, "lock_seen")
                assert a["late"] == [{"slot": 4, "actor": 5}], ("S47 still late", a)
            await env.at(lob, 60.0)
            ent = [env.entry(lob, x, 1 + x) for x in range(5)]
            for w in (0, 1):
                await env.assembly(lob, w, 1 + w, ent, game=1)
            assert (await env.seat(lob, 4))["late_body_game"] == 1, ("S47 late body", entered)
            r1 = await env.report(lob, 1, {lob.sids[0]: (5, 10), lob.sids[1]: (3, 6),
                                           lob.sids[2]: (2, 4), lob.sids[3]: (1, 2)})
            r2 = await env.report(lob, 2, {lob.sids[0]: (5, 10), lob.sids[4]: (3, 6),
                                           lob.sids[1]: (2, 4), lob.sids[2]: (1, 2)})
            assert r1.status == 200 and r2.status == 200, ("S47 reports", r1, r2)
            slot = {sid: i for i, sid in enumerate(lob.sids)}
            out = []
            for r in (r1, r2):
                out.append(sorted((slot[k], v) for k, v in r["rating_changes"].items()))
            seats = [(x["slot"], x["entered_game"], x["late_body_game"])
                     for x in await env.seats(lob)]
            lines = [ln.split(" ", 3)[3] for ln in
                     env.asm_lines("lobby %s report game=" % str(lob.lid)[:8])]
            return out, seats, lines
        with_post = await sitting(True)
        without = await sitting(False)
        assert with_post == without, ("S47 identical", with_post, without)
        assert any(s == 4 for s, _v in with_post[0][1]), ("S47 rated at game 2", with_post[0])
    run_env(monkeypatch, body)


def _s49_count(fn):
    """Uses of the identifier started_at in a function's own code: string
    constants (the SQL), names and attributes; its docstring excluded and
    short_started_at not counted (#432: the count within the function span)."""
    import inspect
    import textwrap
    src = textwrap.dedent(inspect.getsource(fn))
    tree = _ast.parse(src)
    node = tree.body[0]
    doc = None
    if node.body and isinstance(node.body[0], _ast.Expr) \
            and isinstance(getattr(node.body[0], "value", None), _ast.Constant) \
            and isinstance(node.body[0].value.value, str):
        doc = node.body[0].value
    rx = _re.compile(r"(?<![A-Za-z0-9_])started_at(?![A-Za-z0-9_])")
    n = 0
    for x in _ast.walk(node):
        if x is doc:
            continue
        if isinstance(x, _ast.Constant) and isinstance(x.value, str):
            n += len(rx.findall(x.value))
        elif isinstance(x, _ast.Name) and x.id == "started_at":
            n += 1
        elif isinstance(x, _ast.Attribute) and x.attr == "started_at":
            n += 1
    return n


def test_s49_an_unbacked_started(monkeypatch):
    """S49: (i) no grant: started writes nothing but writes and prints
    started without grant; (ii) a grant-backed starter whose row turned final
    writes started_at; (iii) no verdict, veto or closer reads started_at."""
    import inspect
    closers = sorted({f for _n, f in inspect.getmembers(main, inspect.isfunction)
                      if f.__module__ == main.__name__
                      and "_FFA_CLOSE_RECORD_SET" in f.__code__.co_names},
                     key=lambda f: f.__name__)
    names = {f.__name__ for f in closers}
    assert {"queue_cleanup_loop", "delete_player_data", "ffa_queue_leave", "_asm_reform",
            "_asm_dissolve", "_ffa_queue_poll_inner"} <= names, ("S49 closers", names)
    fns = closers + [main._ffa_assembly_verdict, main._asm_classify, main._asm_full_grant,
                     main._asm_start_short, main._group_game_positively_live,
                     main._in_match_evidence_trustworthy, main._asm_deferred_departure,
                     main._ffa_expire_admissions, main._asm_answer_lists]
    counts = {f.__name__: _s49_count(f) for f in fns}
    assert all(v == 0 for v in counts.values()), ("S49 iii", counts)
    probe = "async def _cf_probe():\n    x = 'SELECT started_at FROM t'\n"
    assert _s49_count_src(probe) == 1, "S49 iii probe counts"

    async def body(env):
        # At 16.0 an uncorroborated seat's answer carries spawn_ok = 0, so the
        # answer writes no spawn_ok_at record and the cell alone shows.
        lob = await env.lobby(5, t=16.0)
        before = await env.seat(lob, 4)
        a = await env.connect(lob, 4, "started")
        assert a.status == 200 and a["spawn_ok"] == 0, ("S49 i", a)
        after = await env.seat(lob, 4)
        assert _changed(before, after) == {"writes", "client_ms"}, ("S49 i", _changed(before, after))
        assert env.asm_lines("lobby %s started without grant slot=4" % str(lob.lid)[:8]), \
            "S49 i print"
        lob = await env.lobby(5, t=30.0)
        await _full_grant(env, lob, 30.0)
        await env.set_seat(lob, 2, verdict="dissolved")
        a = await env.connect(lob, 2, "started")
        assert a.status == 200 and a["status"] == "dissolved", ("S49 ii", a)
        assert (await env.seat(lob, 2))["started_at"] == env.now, "S49 ii started_at"
    run_env(monkeypatch, body)


def _s49_count_src(src):
    """_s49_count over a source text (the probe that proves the count can
    move)."""
    tree = _ast.parse(src)
    rx = _re.compile(r"(?<![A-Za-z0-9_])started_at(?![A-Za-z0-9_])")
    return sum(len(rx.findall(x.value)) for x in _ast.walk(tree)
               if isinstance(x, _ast.Constant) and isinstance(x.value, str))


def test_s50_ready_needs_the_seats_own_census(monkeypatch):
    """S50: a seat listed by two peers with no census of its own is PENDING:
    START-SHORT leaves it out of the roster and admissible; in a fallback
    lobby it is PENDING for Table 2 (excluded at the REFORM)."""
    async def body(env):
        for admission in (True, False):
            lob = await env.lobby(5, admission=admission, t=39.9)
            entries = [(s, 1 + s, 1, 1) for s in range(5)]
            await env.set_seat(lob, 4, actor_claim=5, claim_region="eu", actor_nr=5,
                               actor_region="eu", body_seen_at=30.0)
            for s in range(4):
                await env.census_row(lob, s, entries, claim=1 + s, bind=True)
                await env.set_seat(lob, s, body_seen_at=30.0)
            a = await env.assembly(lob, 0, 1, [env.entry(lob, s, 1 + s) for s in range(5)])
            assert a["status"] == "assembling" and a["pending"] == 1, ("S50 39.9", admission, a)
            await env.at(lob, 40.0)
            for s in range(1, 4):
                await env.census_row(lob, s, entries, claim=1 + s)
            a = await env.assembly(lob, 0, 1, [env.entry(lob, s, 1 + s) for s in range(5)])
            s4 = await env.seat(lob, 4)
            if admission:
                assert a["status"] == "start_ok" and _slots(a) == [0, 1, 2, 3], ("S50 short", a)
                assert (s4["verdict"], s4["start_roster"]) == ("admissible", False), \
                    ("S50 admissible", s4["verdict"])
            else:
                assert a["status"] == "reformed" and s4["verdict"] == "excluded", \
                    ("S50 fallback", a, s4["verdict"])
    run_env(monkeypatch, body)


def test_s59_rule_s_and_the_spawning_hold(monkeypatch):
    """S59: a SPAWNING seat holds B at 40, E at 20 and D after a leave at 25;
    at 46.0 rule S starts the bodied four short and admits the SPAWNING seat
    in the same transaction (kind l); with its body seen and nobody PENDING
    the start writes the full-room grant; three bodied and two SPAWNING
    start the three short at 46."""
    async def body(env):
        async def seed(lob, ready, spawning):
            entries = [(s, 1 + s, 1, 1) for s in ready] + [(s, 1 + s, 0, 1) for s in spawning]
            for s in list(ready) + list(spawning):
                await env.census_row(lob, s, entries, claim=1 + s, bind=True)
            await env.conn.execute(
                "UPDATE ffa_assembly_seats SET body_seen_at = $3"
                " WHERE lobby_id = $1 AND slot = ANY($2::smallint[])", lob.lid, list(ready),
                env.now)
            return [env.entry(lob, s, a_, b=b_) for s, a_, b_, _k in entries]

        async def post(lob, ready, spawning, slot=0):
            census = await seed(lob, ready, spawning)
            return await env.assembly(lob, slot, 1 + slot, census)
        # B at 40 held; S at 46 starts the four short and admits seat 4.
        lob = await env.lobby(6, admission=True, t=40.0)
        a = await post(lob, [0, 1, 2, 3], [4])
        assert a["status"] == "assembling" and a["hold"] == 1, ("S59 B held", a)
        await env.at(lob, 45.9)
        a = await post(lob, [0, 1, 2, 3], [4])
        assert a["status"] == "assembling", ("S59 45.9", a)
        await env.at(lob, 46.0)
        a = await post(lob, [0, 1, 2, 3], [4])
        row = await env.lobby_row(lob)
        assert a["status"] == "start_ok" and row["asm_rule"] == "S", ("S59 S", a, row["asm_rule"])
        assert _slots(a) == [0, 1, 2, 3], ("S59 roster", a)
        seats = await env.seats(lob)
        assert (seats[4]["verdict"], seats[4]["late_admitted_at"]) == ("admitted_late", env.now), \
            ("S59 admitted", seats[4]["verdict"])
        assert seats[5]["verdict"] == "admissible", ("S59 pending", seats[5]["verdict"])
        assert {"slot": 4, "actor": 5, "kind": "l"} in a["granted"], ("S59 kind l", a)
        for slot in (1, 4):
            b = await env.connect(lob, slot, "lock_seen")
            assert {"slot": 4, "actor": 5, "kind": "l"} in b["granted"], ("S59 every answer", b)
        # E at 20 held.
        lob = await env.lobby(6, admission=True, offered=[0, 1, 2, 3, 4], t=20.0)
        a = await post(lob, [0, 1, 2, 3], [4])
        assert a["status"] == "assembling" and (await env.lobby_row(lob))["asm_rule"] is None, \
            ("S59 E held", a)
        # D after a leave at 25 held.
        lob = await env.lobby(6, admission=True, t=25.0)
        await seed(lob, [0, 1, 2, 3], [4])
        await env.leave(lob, 5)
        row = await env.lobby_row(lob)
        assert row["status"] == "active" and row["asm_rule"] is None, ("S59 D held", row["asm_rule"])
        a = await post(lob, [0, 1, 2, 3], [4])
        assert a["status"] == "assembling", ("S59 D answer", a)
        # the body seen, nobody PENDING: no rule; the start is the full grant.
        lob = await env.lobby(5, admission=True, t=30.0)
        await seed(lob, [0, 1, 2, 3, 4], [])
        a = await env.assembly(lob, 1, 2, [env.entry(lob, s, 1 + s) for s in range(5)])
        assert a["status"] == "assembling", ("S59 no rule", a)
        a = await env.connect(lob, 0, "start")
        row = await env.lobby_row(lob)
        assert a["status"] == "start_ok" and row["start_granted_at"] is not None \
            and row["short_started_at"] is None and a["start_n"] == 5, ("S59 full grant", a)
        # three bodied, two SPAWNING: S at 46 starts the three short.
        lob = await env.lobby(5, admission=True, t=46.0)
        a = await post(lob, [0, 1, 2], [3, 4])
        assert a["status"] == "start_ok" and _slots(a) == [0, 1, 2], ("S59 three", a)
        seats = await env.seats(lob)
        assert [s["verdict"] for s in seats[3:]] == ["admitted_late", "admitted_late"], \
            ("S59 three admitted", [s["verdict"] for s in seats])
    run_env(monkeypatch, body)


def test_s60_the_census_echo(monkeypatch):
    """S60: seen_age_ms missing, negative or above the server's age at
    receipt answers 422 and writes nothing; a valid one stores census_seen_at
    = created_at + seen_age_ms exactly, the census columns replaced
    together."""
    import httpx
    import database

    async def body(env):
        async def override():
            async with env.sm() as db:
                yield db
        main.app.dependency_overrides[database.get_asm_db] = override
        try:
            lob = await env.lobby(5, t=15.0)
            base = {"steam_id": lob.sids[0], "actor": 1, "region": "eu", "game": 0,
                    "census": [env.entry(lob, 0, 1), env.entry(lob, 2, 3)], "client_ms": 100}

            async def post(payload):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                             base_url="http://cf") as cl:
                    r = await cl.post("/api/v1/ffa/lobby/%s/assembly" % lob.lid, json=payload,
                                      headers={"X-Mod-Version": "1.41.0"})
                return r.status_code, r.json()
            before = await env.seat(lob, 0)
            for tag, extra in (("missing", {}), ("negative", {"seen_age_ms": -1}),
                               ("future", {"seen_age_ms": 15001})):
                st, js = await post(dict(base, **extra))
                assert st == 422, ("S60 " + tag, st, js)
                assert await env.seat(lob, 0) == before, ("S60 wrote " + tag,)
            st, js = await post(dict(base, seen_age_ms=12345))
            assert st == 200, ("S60 valid", st, js)
            s = await env.seat(lob, 0)
            assert (s["census_seen_at"], s["census_at"]) == (await env.ts(lob, 12.345), env.now), \
                ("S60 seen", s["census_seen_at"])
            assert (s["census_slots"], s["census_actors"]) == ([0, 2], [1, 3]), "S60 first"
            st, js = await post(dict(base, seen_age_ms=15000, game=1,
                                     census=[env.entry(lob, 1, 2, b=0, k=0),
                                             {"a": 9, "s": "", "b": 1, "k": 1}]))
            assert st == 200, ("S60 second", st, js)
            s = await env.seat(lob, 0)
            got = (s["census_slots"], s["census_actors"], s["census_nobody"], s["census_unkept"],
                   s["census_anon"], s["census_game"], s["census_seen_at"])
            assert got == ([1], [2], [1], [1], 1, 1, await env.ts(lob, 15.0)), ("S60 replaced", got)
        finally:
            main.app.dependency_overrides.pop(database.get_asm_db, None)
    run_env(monkeypatch, body)


def test_s61_the_granted_list(monkeypatch):
    """S61: after a START-SHORT with roster {0, 1, 3, 4}, answers in B, C and
    D carry granted with the bound actors as kind s; slot 2's admission adds
    it as kind l; a claim is not a binding; a LEFT or admissible seat is
    omitted; a full-room grant lists every seat as s; state A carries none."""
    async def body(env):
        # Slot 2 bound in state A (actor 3) and PENDING at the decision (no
        # peer lists it): admissible WITH a binding, which the list omits.
        lob = await env.lobby(5, admission=True, t=40.0)
        await env.set_seat(lob, 2, actor_nr=3, actor_region="eu", actor_claim=3,
                           claim_region="eu")
        a = await _post(env, lob, 0, [0, 1, 3, 4])
        assert a["status"] == "start_ok", ("short start", a)
        assert (await env.seat(lob, 2))["verdict"] == "admissible", "S61 bound admissible"
        await env.at(lob, 45.0)
        want = [{"slot": s, "actor": 1 + s, "kind": "s"} for s in (0, 1, 3, 4)]
        for slot, st in ((0, "start_ok"), (2, "admitting")):
            a = await env.connect(lob, slot, "lock_seen")
            assert (a["status"], a["granted"]) == (st, want), ("S61 before", slot, a)
        await _admit(env, lob, 2, 3, 0, [0, 1, 3, 4])
        want2 = sorted(want + [{"slot": 2, "actor": 3, "kind": "l"}], key=lambda e: e["slot"])
        for slot, st in ((0, "start_ok"), (2, "admitted_late")):
            a = await env.connect(lob, slot, "lock_seen")
            assert (a["status"], a["granted"]) == (st, want2), ("S61 admitted", slot, a)
        await env.at(lob, 47.0)
        await env.assembly(lob, 1, 9, [env.entry(lob, 1, 9)])
        a = await env.connect(lob, 0, "lock_seen")
        assert a["granted"] == want2, ("S61 claim is not a binding", a)
        await env.leave(lob, 4)
        a = await env.connect(lob, 0, "lock_seen")
        assert a["granted"] == [e for e in want2 if e["slot"] != 4], ("S61 left omitted", a)
        lob = await env.lobby(5, t=10.0)
        a = await env.connect(lob, 0, "lock_seen")
        assert a["status"] == "assembling" and "granted" not in a.body, ("S61 state A", a)
        g = await _full_grant(env, lob, 30.0)
        assert g["granted"] == [{"slot": s, "actor": 1 + s, "kind": "s"} for s in range(5)], \
            ("S61 full grant", g)
    run_env(monkeypatch, body)


def test_s62_no_rebinding_after_a_grant(monkeypatch):
    """S62: a corroborated newer claim of a granted (i) or admitted_late (ii)
    seat changes no binding and prints rebind_refused; in state A (iii) it
    re-binds and prints nothing."""
    async def body(env):
        lob = await _short(env, roster=(0, 1, 3, 4))
        await env.at(lob, 45.0)
        await _admit(env, lob, 2, 3, 0, [0, 1, 3, 4])
        id8 = str(lob.lid)[:8]
        for slot, old, new, peers in ((1, 2, 9, (0, 3)), (2, 3, 8, (0, 4))):
            await env.at(lob, 50.0 + slot)
            listing = [env.entry(lob, s, 1 + s) for s in (0, 3, 4)] + [env.entry(lob, slot, new)]
            for p in peers:
                await env.assembly(lob, p, 1 + p, listing)
            await env.assembly(lob, slot, new, [env.entry(lob, slot, new)])
            s = await env.seat(lob, slot)
            assert (s["actor_nr"], s["actor_region"], s["actor_claim"]) == (old, "eu", new), \
                ("S62 binding kept", slot, s["actor_nr"])
            assert env.asm_lines("lobby %s rebind_refused slot=%d" % (id8, slot)), \
                ("S62 print", slot)
            a = await env.connect(lob, 0, "lock_seen")
            got = [e for e in a["granted"] if e["slot"] == slot]
            assert got and got[0]["actor"] == old, ("S62 granted names the old actor", slot, a)
        lob = await env.lobby(5, t=10.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        listing = [env.entry(lob, s, 1 + s) for s in (0, 2, 3)] + [env.entry(lob, 1, 9)]
        for p in (0, 2):
            await env.assembly(lob, p, 1 + p, listing)
        await env.assembly(lob, 1, 9, [env.entry(lob, 1, 9)])
        assert (await env.seat(lob, 1))["actor_nr"] == 9, "S62 iii re-binds"
        assert not env.asm_lines("lobby %s rebind_refused" % str(lob.lid)[:8]), "S62 iii print"
    run_env(monkeypatch, body)


def test_s63_the_kept_epoch(monkeypatch):
    """S63 (i)-(v): the admitting transaction writes the epoch row, every
    later answer carries it, row 1 never changes, no UPDATE or DELETE ever
    touches the table, two concurrent admissions number 1 and 2, and the
    chain vectors."""
    assert main._ffa_epoch_chain("0", "1a2b3c4d", 1, 2, 7) == "19de52a1bf1b36a9", "S63 v 1"
    assert main._ffa_epoch_chain("19de52a1bf1b36a9", "1a2b3c4d", 2, 4, 9) == \
        "b92768aebf890ca6", "S63 v 2"
    assert main._ffa_epoch_chain("19de52a1bf1b36a9", "1a2b3c4d", 2, 4, 8) == \
        "b92769aebf890e59", "S63 v 3"

    async def body(env):
        lid = uuid.UUID("1a2b3c4d-0000-4000-8000-%012x" % (os.getpid() & 0xFFFFFFFFFFFF))
        lob = await _short(env, roster=(0, 1, 3), lid=lid)
        await env.at(lob, 45.0)
        mark = len(env.rec.stmts)
        ent = [env.entry(lob, s, 1 + s) for s in (0, 1, 3)]
        a = await env.assembly(lob, 2, 7, ent + [env.entry(lob, 2, 7)])
        assert a["status"] == "admitting" and "epoch" not in a.body, ("S63 before", a)
        a = await env.assembly(lob, 0, 1, ent + [env.entry(lob, 2, 7)])
        ep1 = {"n": 1, "chain": "19de52a1bf1b36a9", "kept": [{"slot": 2, "actor": 7}]}
        assert a.get("epoch") == ep1, ("S63 i admitting answer", a)
        rel = ("SELECT lobby_id, epoch_no, slot, actor_nr, chain,"
               "       e.created_at - l.created_at AS age"
               "  FROM ffa_kept_epochs e JOIN ffa_lobbies l ON l.id = e.lobby_id"
               " WHERE e.lobby_id = $1 ORDER BY epoch_no")
        rows = [dict(r) for r in await env.conn.fetch(rel, lob.lid)]
        assert [(r["epoch_no"], r["slot"], r["actor_nr"], r["chain"]) for r in rows] == \
            [(1, 2, 7, "19de52a1bf1b36a9")], ("S63 i row", rows)
        for slot in (1, 2, 4):
            b = await env.connect(lob, slot, "lock_seen")
            assert b["epoch"] == ep1, ("S63 i later answer", slot, b)
        await env.at(lob, 48.0)
        ent2 = ent + [env.entry(lob, 2, 7), env.entry(lob, 4, 9)]
        await env.assembly(lob, 4, 9, ent2)
        try:
            a = await env.assembly(lob, 1, 2, ent2)
        except Exception as exc:  # a refused INSERT is what (ii) reads
            a = cf_asm.Answer("raised", {"error": type(exc).__name__})
        ep2 = {"n": 2, "chain": "b92768aebf890ca6",
               "kept": [{"slot": 2, "actor": 7}, {"slot": 4, "actor": 9}]}
        assert a.get("epoch") == ep2, ("S63 ii", a)
        rows2 = [dict(r) for r in await env.conn.fetch(rel, lob.lid)]
        assert rows2[0] == rows[0] and len(rows2) == 2, ("S63 ii row 1 unchanged", rows2)
        for slot in (0, 2, 4):
            b = await env.connect(lob, slot, "lock_seen")
            assert b["epoch"] == ep2, ("S63 ii later answer", slot, b)
        touched = [x for x in env.rec.stmts[mark:]
                   if x[1] == "ffa_kept_epochs" and x[0] in ("UPDATE", "DELETE")]
        assert touched == [], ("S63 iii", touched)
        # (iv) two admissions of one lobby at once: numbered 1 and 2.
        lob = await _short(env, roster=(0, 1, 3))
        await env.at(lob, 45.0)
        both = [(s, 1 + s, 1, 1) for s in (0, 1, 3)] + [(2, 7, 1, 1), (4, 9, 1, 1)]
        for p in (0, 1):
            await env.census_row(lob, p, both, claim=1 + p)
        age = int(round((env.now - await env.ts(lob, 0)).total_seconds() * 1000))
        conn, tr, bpid = await _blocker(env, lob)

        async def waiters(want):
            # The second request queues behind the first on the same row, so
            # its blocker is the first request: count the waiters reachable
            # from the blocker, not only its direct ones.
            n = 0
            for _ in range(100):
                n = await env.conn.fetchval(
                    "WITH RECURSIVE w(pid) AS ("
                    "  SELECT pid FROM pg_stat_activity WHERE $1 = ANY(pg_blocking_pids(pid))"
                    "  UNION SELECT a.pid FROM pg_stat_activity a JOIN w"
                    "    ON w.pid = ANY(pg_blocking_pids(a.pid)))"
                    " SELECT count(*) FROM w", bpid)
                if n >= want:
                    break
                await asyncio.sleep(0.02)
            return n
        try:
            # Slot 2's request queues first and slot 4's behind it. A row lock
            # is granted in queue order, so which admission numbers 1 is the
            # same in every run (a twin compares the epoch rows byte for byte),
            # and both requests still wait on the one lock at once.
            t2 = asyncio.ensure_future(env.assembly(lob, 2, 7, [env.entry(lob, 2, 7)],
                                                    seen_age_ms=age))
            queued = await waiters(1)
            t4 = asyncio.ensure_future(env.assembly(lob, 4, 9, [env.entry(lob, 4, 9)],
                                                    seen_age_ms=age))
            waiting = await waiters(2)
            assert queued >= 1 and waiting >= 2 and not t2.done() and not t4.done(), \
                ("S63 iv waiting", queued, waiting)
        finally:
            await tr.commit()
            await conn.close()
        a2, a4 = [x if not isinstance(x, BaseException)
                  else cf_asm.Answer("raised", {"error": type(x).__name__})
                  for x in await asyncio.gather(t2, t4, return_exceptions=True)]
        assert a2.get("status") == a4.get("status") == "admitted_late", ("S63 iv", a2, a4)
        rows = [dict(r) for r in await env.conn.fetch(
            "SELECT epoch_no, slot, actor_nr, chain FROM ffa_kept_epochs WHERE lobby_id = $1"
            " ORDER BY epoch_no", lob.lid)]
        assert [r["epoch_no"] for r in rows] == [1, 2] and \
            sorted(r["slot"] for r in rows) == [2, 4], ("S63 iv rows", rows)
        id8 = str(lob.lid)[:8]
        first = main._ffa_epoch_chain("0", id8, 1, rows[0]["slot"], rows[0]["actor_nr"])
        assert rows[0]["chain"] == first and rows[1]["chain"] == main._ffa_epoch_chain(
            first, id8, 2, rows[1]["slot"], rows[1]["actor_nr"]), ("S63 iv chain", rows)
    run_env(monkeypatch, body)


# -- the final-row write matrix and the classification fixture (S52) --

_S52_IGNORE = ("writes", "client_ms")
_S52_CENSUS = {"census_slots", "census_actors", "census_nobody", "census_unkept", "census_anon",
               "census_region", "census_game", "census_at", "census_seen_at", "epoch_seen"}
_S52_RECEIPT = {
    "lock_seen": {"lock_seen_at"},
    "countdown": {"countdown_at"},
    "attempt": {"attempt", "attempt_at", "attempt_phase", "first_attempt_at"},
    "start": {"start_req_at"},
    "entered": {"late_entered_at", "late_game_claim"},
    "failed": {"fail_count", "failed_step", "failed_code", "failed_state", "failed_at"},
    "notice_seen": {"notice_seen_at"},
}
_S52_ARRIVED = {"arrived_at", "arrived_region", "arrived_count"}
# What a repeat of the step changes: receipts are first-wins, the attempt
# telemetry follows the highest attempt, fail_count counts, and the census is
# replaced together.
_S52_REPEAT = {"attempt": {"attempt_at"}, "failed": {"fail_count"},
               "assembly": {"census_at", "census_seen_at"}}
_S52_STEPS = ("lock_seen", "countdown", "attempt", "arrived", "assembly", "start",
              "started", "entered", "failed", "notice_seen")


def _s52_cell(state, step):
    """The final-row write matrix (evidence V11:572-584) as the columns each
    cell changes on this fixture: every claim differs from the stored one, so
    a claim the cell writes shows."""
    if step in _S52_RECEIPT:
        return set(_S52_RECEIPT[step])
    if step == "started":
        return {"started_at"} if state in ("B", "D") else set()
    if step == "arrived":
        return {"A": _S52_ARRIVED | {"admitted_at", "actor_claim", "claim_region"},
                "B": _S52_ARRIVED | {"actor_claim"},
                "C": _S52_ARRIVED | {"actor_claim", "claim_region"},
                "D": _S52_ARRIVED | {"actor_claim"},
                "E": set(_S52_ARRIVED)}[state]
    if step == "assembly":
        return _S52_CENSUS | ({"actor_claim", "claim_region"} if state != "E" else set())
    raise AssertionError(step)


async def _s52_drive(env, lob, slot, step, actor):
    """One step from `slot`. arrived claims `actor` in the lobby's region; the
    census claims actor + 50 from region us and changes every census column:
    its own entry unbodied and unkept, one anonymous entry, game 2, epoch 3."""
    if step == "assembly":
        census = [env.entry(lob, slot, actor + 50, b=0, k=0), {"a": 99, "s": "", "b": 1, "k": 1}]
        return await env.assembly(lob, slot, actor + 50, census, region="us", game=2,
                                  epoch_seen=3)
    kw = {"attempt": {"attempt": 1, "phase": "connect"},
          "arrived": {"region": lob.region, "actor": actor, "count": 4},
          "entered": {"game": 1},
          "failed": {"phase": "join", "code": 32758, "state": "Joining"}}.get(step, {})
    return await env.connect(lob, slot, step, **kw)


async def _s52_matrix(env, cases):
    """cases: [state, lob, slot, actor, t]. Every step in every state, each
    driven twice 0.1 s apart; a second session asserts the cell, then the
    repeat (first-wins), `writes` + 1 each time and every other row of the
    lobby unchanged."""
    for step in _S52_STEPS:
        for case in cases:
            state, lob, slot, actor = case[:4]
            for rep in (0, 1):
                case[4] += 0.1
                await env.at(lob, case[4])
                before = await env.seats(lob)
                a = await _s52_drive(env, lob, slot, step, actor)
                assert a.status == 200, ("S52 status", state, step, rep, a)
                after = await env.seats(lob)
                got = _changed(before[slot], after[slot], _S52_IGNORE)
                want = _s52_cell(state, step) if rep == 0 else _S52_REPEAT.get(step, set())
                assert got == want, ("S52 cell", state, step, rep, sorted(got), sorted(want))
                assert after[slot]["writes"] == before[slot]["writes"] + 1, \
                    ("S52 writes", state, step, rep)
                others = [s for s in range(len(after))
                          if s != slot and _changed(before[s], after[s])]
                assert others == [], ("S52 others", state, step, rep, others)


async def _s52_rows(env, lob, fn, tag):
    """Run fn(); return {slot: changed columns} over the lobby's rows."""
    before = await env.seats(lob)
    a = await fn()
    assert a.status == 200, (tag, a)
    after = await env.seats(lob)
    got = {s: _changed(before[s], after[s], _S52_IGNORE) for s in range(len(after))}
    return {s: c for s, c in got.items() if c}, after


@pytest.mark.parametrize("part", ["matrix", "gone", "classification"])
def test_s52_the_final_row_matrix(monkeypatch, part):
    """S52 (evidence V11:2876), one node per part: every step in every
    seat-row state A-E and its repeat; the gone cells of arrived and the
    census in states B and D (the claim of another actor in the bound region,
    the census that completes the witness test, first write wins on a gone
    seat, and the claim of the bound actor itself triggering nothing); and
    the classification fixture: a pending seat whose only corroborating
    census comes from a final row stays unbound and PENDING, and the decision
    record excludes the final row's census."""
    async def body(env):
        if part == "matrix":
            la = await env.lobby(5, t=16.0)
            await env.ready_all(la, [0, 1, 2])
            lb = await _short(env, 6)
            await env.at(lb, 45.0)
            await _admit(env, lb, 5, 6, 0, [0, 1, 2, 3])
            le = await env.lobby(5, t=40.0)
            a = await _post(env, le, 0, [0, 1, 2, 3])
            assert a["status"] == "reformed", ("S52 E fixture", a)
            cases = [["A", la, 4, 9, 16.0], ["B", lb, 1, 12, 50.0], ["C", lb, 4, 5, 50.0],
                     ["D", lb, 5, 13, 50.0], ["E", le, 4, 14, 45.0]]
            # The first answer to a seat writes its answer records (start_ok_at,
            # spawn_ok_at) in the answering transaction; a telemetry step no cell
            # of the matrix uses takes them first, so each cell shows alone.
            primed = {"A": set(), "B": {"start_ok_at", "spawn_ok_at"}, "C": set(), "D": set(),
                      "E": set()}
            for state, lob, slot, _actor, t in cases:
                await env.at(lob, t)
                got, _rows = await _s52_rows(env, lob, lambda: env.connect(
                    lob, slot, "countdown_abort", phase="gen"), "S52 prime")
                assert got == {slot: {"countdown_abort"} | primed[state]}, ("S52 prime", state, got)
            states = {c[0]: (await env.seat(c[1], c[2]))["verdict"] for c in cases}
            assert states == {"A": None, "B": "granted", "C": "admissible",
                              "D": "admitted_late", "E": "excluded"}, ("S52 states", states)
            await _s52_matrix(env, cases)
        elif part == "gone":
            # The gone cells: two current witnesses (seats 0 and 2) whose
            # censuses omit exactly the cell's subject, re-seeded per cell.
            lg = await _short(env, 6)
            await env.at(lg, 45.0)
            roster = [env.entry(lg, s, 1 + s) for s in (0, 1, 2, 3)]
            for slot in (4, 5):
                a = await env.assembly(lg, slot, 1 + slot, roster + [env.entry(lg, slot, 1 + slot)])
                assert a["status"] == "admitting", ("S52 gone admitting", slot, a)
            await env.assembly(lg, 0, 1, roster + [env.entry(lg, 4, 5), env.entry(lg, 5, 6)])
            assert [s["verdict"] for s in await env.seats(lg)][4:] == ["admitted_late"] * 2, \
                "S52 gone admitted"
            await env.set_seat(lg, 4, late_body_game=1)
            await env.set_seat(lg, 5, late_body_game=1)
            await env.at(lg, 56.0)
            for slot in (1, 3, 4, 5):
                await env.connect(lg, slot, "countdown_abort", phase="gen")

            async def omit(*gone):
                ent = [(s, 1 + s, 1, 1) for s in range(6) if s not in gone]
                for w in (0, 2):
                    await env.census_row(lg, w, ent, claim=1 + w)

            def arrived(slot, actor):
                return lambda: env.connect(lg, slot, "arrived", region=lg.region, actor=actor, count=6)

            def census(slot, actor):
                return lambda: env.assembly(lg, slot, actor, [env.entry(lg, slot, actor)])

            gone = {"gone_game", "gone_path"}
            await omit(1)
            got, rows = await _s52_rows(env, lg, arrived(1, 2), "S52 gone bound claim")
            assert got == {1: set(_S52_ARRIVED)}, ("S52 gone bound claim", got)
            assert not env.asm_lines("gone_trigger slot=1 claim=2 "), "S52 gone bound claim print"
            got, rows = await _s52_rows(env, lg, arrived(1, 12), "S52 gone B arrived")
            assert got == {1: {"actor_claim"} | gone} and \
                (rows[1]["gone_game"], rows[1]["gone_path"]) == (1, "witness"), \
                ("S52 gone B arrived", got)
            assert env.asm_lines("gone_trigger slot=1 claim=12 bound=2 result=witness"), \
                "S52 gone B arrived print"
            await omit(5)
            got, rows = await _s52_rows(env, lg, arrived(5, 16), "S52 gone D arrived")
            assert got == {5: _S52_ARRIVED | {"actor_claim"} | gone} and \
                rows[5]["gone_game"] == 1, ("S52 gone D arrived", got)
            await omit(4)
            got, rows = await _s52_rows(env, lg, census(4, 15), "S52 gone D census")
            assert got == {4: {"census_slots", "census_actors", "census_at", "census_seen_at",
                               "actor_claim"} | gone} and rows[4]["gone_game"] == 1, \
                ("S52 gone D census", got)
            await omit(3)
            got, rows = await _s52_rows(env, lg, census(3, 14), "S52 gone B census")
            assert got == {3: {"census_slots", "census_actors", "census_at", "census_seen_at",
                               "epoch_seen", "actor_claim"} | gone}, ("S52 gone B census", got)
            # First write wins: with games_played moved to 1 a rewrite would
            # record game 2; every witness now omits all four gone seats.
            await env.set_lobby(lg, games_played=1)
            await omit(1, 3, 4, 5)
            for fn, slot, want in ((arrived(1, 13), 1, {"actor_claim"}),
                                   (arrived(5, 18), 5, {"actor_claim"}),
                                   (census(3, 17), 3, {"census_actors", "actor_claim"}),
                                   (census(4, 19), 4, {"census_actors", "actor_claim"})):
                got, rows = await _s52_rows(env, lg, fn, "S52 gone first wins")
                assert got == {slot: want} and rows[slot]["gone_game"] == 1, \
                    ("S52 gone first wins", slot, got)

            # The census that completes the witness test for another seat
            # (S64 (v)): seat 0 omits seat 3 alone; seat 1's census is the second.
            lv = await _short(env, 5)
            await env.at(lv, 52.0)
            await env.connect(lv, 1, "countdown_abort", phase="gen")
            await env.census_row(lv, 0, [(0, 1, 1, 1), (1, 2, 1, 1), (2, 3, 1, 1)], claim=1)
            got, rows = await _s52_rows(env, lv, lambda: env.assembly(
                lv, 1, 2, [env.entry(lv, s, 1 + s) for s in (0, 1, 2)]), "S52 gone completes")
            assert got == {1: {"census_slots", "census_actors", "census_at", "census_seen_at",
                               "epoch_seen"}, 3: gone} and \
                (rows[3]["gone_game"], rows[3]["gone_path"]) == (1, "witness"), \
                ("S52 gone completes", got)
        else:
            # The classification fixture: P (seat 4) has its own fresh census and
            # a claim; the only census listing {a: 5, s: P} is final row F's
            # (seat 5, left); seat 0's POST decides (REFORM at 40).
            lc = await env.lobby(6, t=40.0)
            await env.ready_all(lc, [0, 1, 2, 3])
            await env.census_row(lc, 4, [(4, 5, 1, 1)], claim=5)
            await env.set_seat(lc, 5, left_at=30.0, verdict="left", verdict_at=30.0)
            await env.conn.execute("DELETE FROM ffa_queue WHERE player_id = $1", lc.pids[5])
            await env.census_row(lc, 5, [(4, 5, 1, 1), (5, 6, 1, 1)], claim=6)
            before = await env.seats(lc)
            a = await _post(env, lc, 0, [0, 1, 2, 3])
            assert a["status"] == "reformed", ("S52 classification decides", a)
            after = await env.seats(lc)
            p, f = after[4], after[5]
            assert (p["actor_nr"], p["actor_region"]) == (None, None), \
                ("S52 classification P unbound", p["actor_nr"])
            assert (p["body_seen_at"], p["bodiless_at"]) == \
                (before[4]["body_seen_at"], before[4]["bodiless_at"]), "S52 classification P body"
            assert p["verdict"] == "excluded", ("S52 classification P pending", p["verdict"])
            assert (f["dec_census"], f["dec_census_at"]) == (None, None) and \
                f["dec_at"] is not None, ("S52 classification record", f["dec_census"])
            kept = [(r["dec_census"], r["dec_census_at"]) == (r["census_slots"], r["census_at"])
                    and r["dec_at"] is not None for r in after[:5]]
            assert all(kept), ("S52 classification read rows", kept)
    run_env(monkeypatch, body)


# -- writer 7 on the late-body evidence, the sticky reporter, the deadline's
#    pool, lock and statement paths, the late-body rule, the G3 gate and its
#    fence (S43, S48, S53-S58) --

import time as _rt  # noqa: E402

_REPORT_COUNTS_SQL = (
    "SELECT (SELECT count(*) FROM ffa_matches WHERE lobby_id = $1) AS matches,"
    "       (SELECT count(*) FROM ffa_match_players mp JOIN ffa_matches m ON m.id = mp.match_id"
    "         WHERE m.lobby_id = $1) AS match_players,"
    "       (SELECT count(*) FROM match_report_quarantine WHERE group_id = $1) AS quarantine,"
    "       (SELECT games_played FROM ffa_lobbies WHERE id = $1) AS games,"
    "       (SELECT count(*) FROM glicko_ratings_ffa WHERE player_id = ANY($2::uuid[]))"
    "         AS ratings")


async def _report_counts(env, lob):
    return dict(await env.conn.fetchrow(_REPORT_COUNTS_SQL, lob.lid, lob.pids))


async def _mp(env, lob, g):
    """{slot: ffa_match_players row} of game g of the fixture lobby."""
    rows = await env.conn.fetch(
        "SELECT mp.* FROM ffa_match_players mp JOIN ffa_matches m ON m.id = mp.match_id"
        " WHERE m.lobby_id = $1 AND m.game_number = $2", lob.lid, g)
    return {r["slot"]: dict(r) for r in rows}


def _rated(row):
    """A settled seat that played the game: not in the effective unrated set,
    with a rating change."""
    return not row["absent"] and row["rating_change"] is not None


def _unrated(row):
    return bool(row["absent"]) and row["rating_change"] is None \
        and not row["xp_gained"] and not row["gold_gained"]


def test_s43_writer_7_on_the_late_body_evidence(monkeypatch):
    """S43: (i) an admitted seat with late_game 1 and no late_body_game is
    unrated for every game whatever the report lists; (ii) late_body_game 2:
    unrated for games 1 and 2, rated for 3; (iii) a report never writes
    late_body_game, and entered_game is only the copy at the first accepted
    report with g >= late_body_game; (iv) writer 7 (b): a seat never granted
    game g in a short-started lobby is unrated; (v) a refused or rolled-back
    report writes no entered_game."""
    async def body(env):
        l1 = await _short(env, 6)
        await env.at(l1, 50.0)
        await _admit(env, l1, 4, 5, 0, [0, 1, 2, 3])
        await env.at(l1, 55.0)
        s = l1.sids
        full = {s[0]: (5, 10), s[1]: (4, 8), s[2]: (3, 6), s[3]: (2, 4), s[4]: (3, 7),
                s[5]: (1, 3)}
        for g in (1, 2):
            r = await env.report(l1, g, full)
            rows = await _mp(env, l1, g)
            assert r.status == 200 and _unrated(rows[4]), ("S43 i", g, r, rows.get(4))
            if g == 1:
                assert _unrated(rows[5]), ("S43 iv", rows.get(5))
                assert all(_rated(rows[x]) for x in range(4)), ("S43 roster rated", rows)
                assert env.asm_lines("report game=1 unrated=4:a,5:b"), "S43 i print"
        ghost = dict(full)
        ghost[s[4]] = (0, 0)
        r = await env.report(l1, 3, ghost, left={s[4]}, absent={s[4]})
        rows = await _mp(env, l1, 3)
        assert r.status == 200 and _unrated(rows[4]), ("S43 i", 3, r, rows.get(4))
        seat = await env.seat(l1, 4)
        assert (seat["late_body_game"], seat["entered_game"]) == (None, None), \
            ("S43 iii no write", seat["late_body_game"], seat["entered_game"])

        l2 = await _short(env)
        await env.at(l2, 50.0)
        await _admit(env, l2, 4, 5, 0, [0, 1, 2, 3])
        await env.at(l2, 52.0)
        a = await env.connect(l2, 4, "entered", game=3)
        assert a.status == 200, ("S43 entered", a)
        await env.set_seat(l2, 4, late_body_game=2)
        s = l2.sids
        res = {s[0]: (5, 10), s[1]: (4, 8), s[2]: (3, 6), s[3]: (2, 4), s[4]: (3, 7)}
        r = await env.report(l2, 1, res)
        rows = await _mp(env, l2, 1)
        assert r.status == 200 and _unrated(rows[4]), ("S43 ii", 1, r, rows.get(4))
        assert (await env.seat(l2, 4))["entered_game"] is None, "S43 iii before"
        r = await env.report(l2, 2, res, reporter=s[4])
        assert r.status == 409, ("S43 v refused", r)
        assert (await env.seat(l2, 4))["entered_game"] is None, "S43 v refused"
        orig = main._ffa_advance_lobby_slot

        async def boom(*_a, **_k):
            raise RuntimeError("cf rollback")
        env.mp.setattr(main, "_ffa_advance_lobby_slot", boom)
        try:
            with pytest.raises(RuntimeError):
                await env.report(l2, 2, res)
        finally:
            env.mp.setattr(main, "_ffa_advance_lobby_slot", orig)
        assert (await env.seat(l2, 4))["entered_game"] is None, "S43 v rolled back"
        r = await env.report(l2, 2, res)
        rows = await _mp(env, l2, 2)
        assert r.status == 200 and _unrated(rows[4]), ("S43 ii", 2, r, rows.get(4))
        assert (await env.seat(l2, 4))["entered_game"] == 2, "S43 iii copy"
        r = await env.report(l2, 3, res)
        rows = await _mp(env, l2, 3)
        assert r.status == 200 and _rated(rows[4]), ("S43 ii", 3, r, rows.get(4))
        seat = await env.seat(l2, 4)
        assert (seat["entered_game"], seat["late_body_game"], seat["late_game_claim"]) == \
            (2, 2, 3), ("S43 iii after", seat["entered_game"], seat["late_body_game"])
    run_env(monkeypatch, body)


def test_s48_the_sticky_reporter_rule(monkeypatch):
    """S48: a seat with late_admitted_at, and a seat without start_roster in
    a short-started lobby, may not report any game of the sitting
    (late_reporter, 409, through _ffa_record_and_refuse, writing only the
    quarantine); writer 7 (e): the reporter's own lag step for game g refuses
    its report of g (lag_reporter) and nothing else; a lag step writes only
    its sender's row."""
    async def body(env):
        lob = await _short(env, 6)
        await env.at(lob, 50.0)
        await _admit(env, lob, 4, 5, 0, [0, 1, 2, 3])
        await env.at(lob, 55.0)
        s = lob.sids
        res = {s[0]: (5, 10), s[1]: (4, 8), s[2]: (3, 6), s[3]: (2, 4), s[4]: (1, 2)}
        # Seat 1's first answer stamps its answer records (the answer
        # writer's, not the cell's): answer it once before the lag steps.
        a = await env.connect(lob, 1, "lock_seen")
        assert a.status == 200, ("S48 prime", a)
        before = await env.seats(lob)
        for _rep in (0, 1):
            a = await env.connect(lob, 1, "lag", game=1, k=1, why="timeout")
            assert a.status == 200, ("S48 lag", a)
        after = await env.seats(lob)
        got = {x: _changed(before[x], after[x], _S52_IGNORE) for x in range(6)}
        assert got == {0: set(), 1: {"lag_games"}, 2: set(), 3: set(), 4: set(), 5: set()} \
            and after[1]["lag_games"] == [1], ("S48 lag row", got, after[1]["lag_games"])
        assert len(env.asm_lines("lag slot=1 game=1 k=1 why=timeout")) == 2, "S48 lag print"
        room = (await env.lobby_row(lob))["photon_room_id"]

        async def refused(g, slot, reason, tag):
            counts = await _report_counts(env, lob)
            mark = len(env.lines)
            rid = "%s_s%d_r%d" % (room, slot, g)
            r = await env.report(lob, g, res, reporter=s[slot], room=rid)
            new = [ln for ln in env.lines[mark:] if " refused (" in ln]
            q = await env.conn.fetchval(
                "SELECT reason FROM match_report_quarantine WHERE group_id = $1"
                "   AND photon_room_id = $2", lob.lid, rid)
            now = await _report_counts(env, lob)
            assert r.status == 409 and q == reason and len(new) == 1 \
                and (" refused (%s:" % reason) in new[0], (tag, r, q, new)
            want = dict(counts, quarantine=counts["quarantine"] + 1)
            assert now == want, (tag + " rows", counts, now)

        await refused(1, 1, "lag_reporter", "S48 lag")
        await refused(1, 4, "late_reporter", "S48 late game 1")
        await refused(1, 5, "late_reporter", "S48 unrostered")
        r = await env.report(lob, 1, res, reporter=s[0])
        assert r.status == 200 and s[1] in r["rating_changes"], ("S48 lag others", r)
        await refused(2, 4, "late_reporter", "S48 sticky")
        r = await env.report(lob, 2, res, reporter=s[1])
        assert r.status == 200, ("S48 lag game 2", r)
    run_env(monkeypatch, body)


def _running_clock(env):
    """main's monotonic clock runs with real time from env.mono (the deadline
    fixtures): the routes' elapsed-time checks see real waits."""
    base = _rt.monotonic()
    env.mp.setattr(main.time, "monotonic", lambda: env.mono + (_rt.monotonic() - base))


def _age_ms(env, created):
    return int(round((env.now - created).total_seconds() * 1000))


def test_s53_the_deadline_pool(monkeypatch):
    """S53: with all eight assembly-pool connections checked out, an assembly
    POST answers 503 asm_deadline within 3.5 s, writes nothing and logs
    stage=pool; the poll, on get_db, still answers."""
    import httpx
    import database
    import ladder_pg_harness as harness
    from sqlalchemy.ext.asyncio import async_sessionmaker as _asm_maker

    async def body(env):
        eng = database.make_asm_engine(harness.async_dsn(env.c.dsn),
                                       server_settings={"search_path": harness.quoted(env.c.schema)})
        asm_sm = _asm_maker(eng, expire_on_commit=False)

        async def asm_dep():
            async with asm_sm() as db:
                yield db

        async def db_dep():
            async with env.sm() as db:
                yield db
        main.app.dependency_overrides[database.get_asm_db] = asm_dep
        main.app.dependency_overrides[database.get_db] = db_dep
        held = []
        try:
            lob = await env.lobby(5, t=15.0)
            before = await env.seat(lob, 0)
            payload = {"steam_id": lob.sids[0], "actor": 1, "region": "eu", "game": 0,
                       "seen_age_ms": 15000, "census": [env.entry(lob, 0, 1)], "client_ms": 100}
            for _ in range(database.ASM_POOL_SIZE + database.ASM_POOL_OVERFLOW):
                sess = asm_sm()
                await sess.connection()
                held.append(sess)

            async def http(method, path, js=None):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                             base_url="http://cf", timeout=60) as cl:
                    r = await cl.request(method, path, json=js,
                                         headers={"X-Mod-Version": "1.41.0"})
                return r.status_code, r.json()
            t0 = _rt.monotonic()
            a = await env._call(lambda: http("POST", "/api/v1/ffa/lobby/%s/assembly" % lob.lid,
                                             payload))
            dt = _rt.monotonic() - t0
            st, js = a.body
            assert st == 503 and js == {"error": "asm_deadline"} and dt < 3.5, ("S53 503", st, js, dt)
            assert await env.seat(lob, 0) == before, "S53 no write"
            assert env.asm_lines("lobby %s deadline route=assembly stage=pool"
                                 % str(lob.lid)[:8]), "S53 log"
            a = await env._call(lambda: http("GET", "/api/v1/ffa/queue/poll/%s" % lob.sids[1]))
            st, js = a.body
            assert st == 200, ("S53 poll", st, js)
        finally:
            for sess in held:
                await sess.close()
            main.app.dependency_overrides.pop(database.get_asm_db, None)
            main.app.dependency_overrides.pop(database.get_db, None)
            await eng.dispose()
    run_env(monkeypatch, body)


async def _s54_closer(env, lob):
    """Session A: the lobby row lock, seats 1 and 2 leaving under it, and a
    closing verdict computed (DISSOLVE: |READY| 2), not yet committed."""
    sess = env.sm()
    db = await sess.__aenter__()
    ctx = await main._asm_ctx_slot(db, lob.lid, route="leave", trigger="leave")
    await db.execute(main.text(
        "UPDATE ffa_assembly_seats SET left_at = CAST(:now AS timestamptz), verdict = 'left',"
        "       verdict_at = CAST(:now AS timestamptz) WHERE lobby_id = :lid AND slot IN (1, 2)"),
        {"now": env.now, "lid": lob.lid})
    await db.execute(main.text("DELETE FROM ffa_queue WHERE series_id = :lid AND slot IN (1, 2)"),
                     {"lid": lob.lid})
    await ctx.reload()
    out = await main._ffa_assembly_verdict(ctx, "leave")
    assert out["outcome"] == "dissolve", ("S54 A decides", out)
    apid = (await db.execute(main.text("SELECT pg_backend_pid()"))).scalar()
    return sess, db, apid


def test_s54_the_lock_deadline_ordered(monkeypatch):
    """S54: A holds the lobby row lock and B's assembly POST waits on it.
    (i) past the deadline: 503 asm_deadline stage=lock, no write; (ii) A
    commits a closing verdict at about 1 s: B answers from its seat row
    inside the deadline; (iii) A commits at about 2.9 s: B answers inside
    the deadline or 503 with no write, never a grant or a verdict from rows
    read before A's commit."""
    async def body(env):
        _running_clock(env)
        lob = await env.lobby(5, admission=True, t=40.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        age = _age_ms(env, await env.ts(lob, 0))
        before = await env.seats(lob)
        conn, tr, bpid = await _blocker(env, lob)
        try:
            t0 = _rt.monotonic()
            task = asyncio.ensure_future(env.census_of(lob, 0, [0, 1, 2, 3], seen_age_ms=age))
            n = await _waiting_on(env, bpid)
            done, _pend = await asyncio.wait({task}, timeout=4.0)
            dt = _rt.monotonic() - t0
        finally:
            await tr.rollback()
            await conn.close()
        a = await task
        assert n >= 1 and done and a.status == 503 and a.body == {"error": "asm_deadline"} \
            and dt < 3.5, ("S54 i", n, a, dt)
        assert env.asm_lines("lobby %s deadline route=assembly stage=lock" % str(lob.lid)[:8]), \
            "S54 i log"
        assert await env.seats(lob) == before, "S54 i no write"
        for tag, hold in (("S54 ii", 1.0), ("S54 iii", 2.9)):
            lob = await env.lobby(5, admission=True, t=40.0)
            await env.ready_all(lob, [0, 1, 2, 3])
            age = _age_ms(env, await env.ts(lob, 0))
            seat0 = await env.seat(lob, 0)
            sess, db, apid = await _s54_closer(env, lob)
            try:
                t0 = _rt.monotonic()
                task = asyncio.ensure_future(env.census_of(lob, 0, [0, 1, 2, 3], seen_age_ms=age))
                n = await _waiting_on(env, apid)
                await asyncio.sleep(max(0.0, hold - (_rt.monotonic() - t0)))
                await db.commit()
            finally:
                await sess.__aexit__(None, None, None)
            a = await task
            dt = _rt.monotonic() - t0
            row = await env.lobby_row(lob)
            after0 = await env.seat(lob, 0)
            assert n >= 1, (tag + " waits", n)
            assert row["start_granted_at"] is None and row["short_started_at"] is None \
                and row["status"] != "active", (tag + " no grant", row["status"])
            if tag == "S54 ii" or a.status == 200:
                assert a.status == 200 and a["status"] == "dissolved" and dt < 3.0, \
                    (tag + " answer", a, dt)
            else:
                assert a.status == 503 and a.body == {"error": "asm_deadline"} and \
                    (after0["writes"], after0["census_at"]) == (seat0["writes"], seat0["census_at"]), \
                    (tag + " no write", a)
    run_env(monkeypatch, body)


def test_s55_statement_precommit_and_the_slow_commit(monkeypatch):
    """S55: (i) a statement made slow by a sleeping trigger: 503 stage=stmt,
    no write; (ii) the elapsed time forced past the deadline before the
    COMMIT: rollback, 503 stage=precommit, no write; (iii) a slow COMMIT
    keeps its write and logs slow_commit (ms over 4000, pre_ms under 3000);
    (iv) a second POST of the lobby waits on the row lock during it and then
    answers with the decision the first wrote, writing none of its own."""
    async def body(env):
        lob = await env.lobby(5, t=15.0)
        await env.conn.execute(
            "CREATE FUNCTION cf_slow_seat() RETURNS trigger LANGUAGE plpgsql AS"
            " $f$ BEGIN PERFORM pg_sleep(4); RETURN NEW; END $f$")
        await env.conn.execute(
            "CREATE TRIGGER cf_slow_seat BEFORE UPDATE ON ffa_assembly_seats FOR EACH ROW"
            " WHEN (NEW.census_region = 'zz') EXECUTE FUNCTION cf_slow_seat()")
        await env.c.seal()
        before = await env.seat(lob, 0)
        a = await env.assembly(lob, 0, 1, [env.entry(lob, 0, 1)], region="zz")
        assert a.status == 503 and a.body == {"error": "asm_deadline"} \
            and env.asm_lines("lobby %s deadline route=assembly stage=stmt" % str(lob.lid)[:8]) \
            and await env.seat(lob, 0) == before, ("S55 i", a)

        lob = await env.lobby(5, t=15.0)
        before = await env.seat(lob, 0)
        orig = main._asm_answer_plan

        async def late(ctx, pid, **kw):
            out = await orig(ctx, pid, **kw)
            env.mono += 3.5
            return out
        env.mp.setattr(main, "_asm_answer_plan", late)
        try:
            a = await env.assembly(lob, 0, 1, [env.entry(lob, 0, 1)])
        finally:
            env.mp.setattr(main, "_asm_answer_plan", orig)
        assert a.status == 503 and a.body == {"error": "asm_deadline"} \
            and env.asm_lines("lobby %s deadline route=assembly stage=precommit"
                              % str(lob.lid)[:8]) \
            and await env.seat(lob, 0) == before, ("S55 ii no write", a)

        _running_clock(env)
        lob = await env.lobby(5, admission=True, t=40.0)
        await env.ready_all(lob, [0, 1, 2, 3])
        age = _age_ms(env, await env.ts(lob, 0))
        entries = [env.entry(lob, x, 1 + x) for x in range(4)]
        req0 = main._AsmAssemblyReq(steam_id=lob.sids[0], actor=1, region="eu", game=0,
                                    seen_age_ms=age, epoch_seen=0, census=entries, client_ms=100)
        in_commit = asyncio.Event()
        pid1 = {}

        async def first():
            async def go():
                async with env.sm() as db:
                    pid1["pid"] = (await db.execute(main.text("SELECT pg_backend_pid()"))).scalar()
                    orig_commit = db.commit

                    async def slow():
                        in_commit.set()
                        await asyncio.sleep(4.5)
                        await orig_commit()
                    db.commit = slow
                    return await main.ffa_lobby_assembly(lob.lid, req0, None, db=db)
            return await env._call(go)
        t1 = asyncio.ensure_future(first())
        await asyncio.wait_for(in_commit.wait(), 10)
        await asyncio.sleep(2.3)
        t2 = asyncio.ensure_future(env.census_of(lob, 1, [0, 1, 2, 3], seen_age_ms=age))
        n = await _waiting_on(env, pid1["pid"], rel="ffa_lobbies")
        a1 = await t1
        a2 = await t2
        row = await env.lobby_row(lob)
        assert a1.status == 200 and a1["status"] == "start_ok" \
            and row["start_granted_at"] is not None, ("S55 iii keeps", a1)
        slow = env.asm_lines("lobby %s slow_commit route=assembly" % str(lob.lid)[:8])
        parsed = [dict(kv.split("=", 1) for kv in ln.split() if "=" in kv) for ln in slow]
        assert len(parsed) == 1 and int(parsed[0]["ms"]) > 4000 \
            and int(parsed[0]["pre_ms"]) < 3000, ("S55 iii log", slow)
        assert n >= 1, ("S55 iv waits", n)
        starts = env.asm_lines("lobby %s short start" % str(lob.lid)[:8])
        assert a2.status == 200 and a2["status"] == "start_ok" and len(starts) == 1 \
            and row["asm_rule"] == "B", ("S55 iv answer", a2, starts, row["asm_rule"])
    run_env(monkeypatch, body)


def test_s56_the_late_body_rule_and_the_lone_report(monkeypatch):
    """S56: admitted seat L (slot 4, actor 5, late_game 1). (i) entered alone
    writes nothing; (ii) entered and one witness: path i; (iii) two witnesses
    without entered: path ii; (iv) one witness alone, a witness built before
    the admission, one from a final row, or one from an admitted seat without
    its own late_body_game writes nothing; (v) evidence naming game 0 writes
    nothing; (vi) a lone report cannot enable rating."""
    async def body(env):
        async def admitted(n=5, extra=False):
            lob = await _short(env, n)
            await env.at(lob, 50.0)
            await _admit(env, lob, 4, 5, 0, [0, 1, 2, 3])
            if extra:
                await _admit(env, lob, 5, 6, 0, [0, 1, 2, 3])
            await env.at(lob, 52.0)
            return lob

        async def late(lob):
            return (await env.seat(lob, 4))["late_body_game"]

        def wit(lob, n=5):
            return [env.entry(lob, x, 1 + x) for x in range(n)]

        la = await admitted()
        await env.connect(la, 4, "entered", game=1)
        assert await late(la) is None, "S56 i"
        await env.assembly(la, 0, 1, wit(la), game=1)
        assert await late(la) == 1 and env.asm_lines(
            "lobby %s late_body slot=4 game=1 path=i" % str(la.lid)[:8]), "S56 ii"

        lb = await admitted()
        await env.assembly(lb, 0, 1, wit(lb), game=1)
        assert await late(lb) is None, "S56 iv one witness"
        await env.assembly(lb, 1, 2, wit(lb), game=1)
        assert await late(lb) == 1 and env.asm_lines(
            "lobby %s late_body slot=4 game=1 path=ii" % str(lb.lid)[:8]), "S56 iii"

        lc = await admitted()
        await env.connect(lc, 4, "entered", game=1)
        await env.assembly(lc, 0, 1, wit(lc), game=1, seen_age_ms=49000)
        assert await late(lc) is None, "S56 iv before the admission"

        ld = await admitted()
        await env.census_row(ld, 3, [(x, 1 + x, 1, 1) for x in range(5)], game=1, claim=4)
        await env.set_seat(ld, 3, verdict="excluded")
        await env.connect(ld, 4, "entered", game=1)
        assert await late(ld) is None, "S56 iv final row"

        le = await admitted(6, extra=True)
        await env.assembly(le, 5, 6, wit(le, 6), game=1)
        await env.connect(le, 4, "entered", game=1)
        assert await late(le) is None, "S56 iv admitted without its own"

        lf = await admitted()
        for w in (0, 1):
            await env.assembly(lf, w, 1 + w, wit(lf), game=0)
        assert await late(lf) is None, "S56 v game 0"

        lg = await admitted()
        s = lg.sids
        res = {s[0]: (5, 10), s[1]: (4, 8), s[2]: (3, 6), s[3]: (2, 4), s[4]: (3, 7)}
        for g in (1, 2):
            r = await env.report(lg, g, res)
            rows = await _mp(env, lg, g)
            assert r.status == 200 and _unrated(rows[4]) and s[4] not in r["rating_changes"], \
                ("S56 vi", g, r, rows.get(4))
        assert await late(lg) is None, "S56 vi no late body"
    run_env(monkeypatch, body)


def test_s57_the_g3_server_gate(monkeypatch):
    """S57: while ADM_PRODUCTION_ENABLED is False a lock is an admission
    lobby only when every member advertises ffa_adm1 and holds an unexpired
    ffa_g3_seats row; patched True, the rows are not needed. The admin route:
    403 for a non-admin, a bad signature, or a signature over another
    duration; 422 for hours 73; hours 0 expires the row; a valid call upserts
    expires_at = now + hours."""
    async def body(env):
        async def enrol(pids, expired=()):
            for p in pids:
                await env.conn.execute(
                    "INSERT INTO ffa_g3_seats (player_id, added_at, expires_at)"
                    " VALUES ($1, now(), CASE WHEN $2 THEN now() - interval '1 second'"
                    "                         ELSE now() + interval '1 hour' END)"
                    " ON CONFLICT (player_id) DO UPDATE SET expires_at = EXCLUDED.expires_at",
                    p, p in expired)

        async def lock(pick, expired=()):
            lob = await _open_lobby(env, 4, ["ffa_asm1,ffa_adm1"] * 4)
            await enrol(pick(lob), [lob.pids[i] for i in expired])
            a = await _start(env, main, lob)
            assert a.status == 200, ("S57 lock", a)
            row = await env.lobby_row(lob)
            return row["assembly_v1"], row["admission_v1"]

        assert main.ADM_PRODUCTION_ENABLED is False, "S57 constant"
        got = await lock(lambda lob: lob.pids)
        assert got == (True, True), ("S57 enrolled", got)
        got = await lock(lambda lob: lob.pids[:3])
        assert got == (True, False), ("S57 unenrolled", got)
        got = await lock(lambda lob: lob.pids, expired=(2,))
        assert got == (True, False), ("S57 expired", got)
        env.mp.setattr(main, "ADM_PRODUCTION_ENABLED", True)
        got = await lock(lambda lob: [])
        env.mp.setattr(main, "ADM_PRODUCTION_ENABLED", False)
        assert got == (True, True), ("S57 production", got)

        secret = "cf-g3-secret"
        env.mp.setattr(main, "ADMIN_HMAC_SECRET", secret)
        lob = await env.lobby(3, t=5.0)
        admin, other, target = lob.sids
        await env.conn.execute("INSERT INTO admin_users (steam_id, granted_at) VALUES ($1, now())",
                               admin)
        seen = []
        orig = main._verify_admin_hmac

        def spy(a, act, tgt, sig):
            seen.append(tgt)
            return orig(a, act, tgt, sig)
        env.mp.setattr(main, "_verify_admin_hmac", spy)

        def sign(tgt):
            return _hmac.new(secret.encode(), main._admin_canonical(admin, "ffa_g3_seat", tgt)
                             .encode(), hashlib.sha256).hexdigest()

        async def call(who, hours, sig):
            payload = {"admin_steam_id": who, "target_steam_id": target, "hours": hours,
                       "signature": sig}

            async def go():
                async with env.sm() as db:
                    return await main.admin_ffa_g3_seat(payload, db=db)
            return await env._call(go)

        async def left():
            return await env.conn.fetchval(
                "SELECT EXTRACT(EPOCH FROM expires_at - now()) FROM ffa_g3_seats"
                " WHERE player_id = $1", lob.pids[2])

        a = await call(other, 5, "0" * 64)
        assert a.status == 403, ("S57 not admin", a)
        a = await call(admin, 5, "0" * 64)
        assert a.status == 403 and seen, ("S57 bad signature", a)
        signed5 = seen[-1]
        a = await call(admin, 5, sign(signed5))
        assert a.status == 200 and 5 * 3600 - 60 <= await left() <= 5 * 3600 + 5, \
            ("S57 valid", a)
        a = await call(admin, 6, sign(signed5))
        assert a.status == 403, ("S57 other duration", a)
        a = await call(admin, 73, sign(signed5))
        assert a.status == 422, ("S57 hours 73", a)
        seen.clear()
        await call(admin, 0, "0" * 64)
        a = await call(admin, 0, sign(seen[-1]))
        assert a.status == 200 and await left() <= 0, ("S57 hours 0", a)
        a = await call(admin, 5, sign(signed5))
        assert a.status == 200 and await left() > 5 * 3600 - 60 and await env.conn.fetchval(
            "SELECT count(*) FROM ffa_g3_seats WHERE player_id = $1", lob.pids[2]) == 1, \
            ("S57 upsert", a)
    run_env(monkeypatch, body)


def _write_facts(facts):
    """A structural case's trace for cf_controls.py's twin comparison
    (cf_controls.trace_file's name): the facts it asserts on."""
    d = os.environ.get("CF_TRACE_DIR")
    if not d:
        return
    node = os.environ.get("PYTEST_CURRENT_TEST", "case").split(" ")[0].rsplit("/", 1)[-1]
    path = os.path.join(d, _re.sub(r"[^A-Za-z0-9_.-]", "_", node) + ".json")
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write(_json.dumps(facts, sort_keys=True, indent=1))


_CSPROJ = os.path.join(HERE, "..", "..", "plugin", "CompetitiveRounds.csproj")
_SQL_DIR = os.path.join(HERE, "..", "sql")


def test_s58_the_g3_fence():
    """S58 (structural, both states): while ADM_PRODUCTION_ENABLED is False
    the enrolment clause, the route and the csproj's G3 configuration exist;
    once it is True, ffa_g3_seats is in no route, predicate or query of
    main.py, no route path names ffa-g3-seats, a migration drops the table,
    and the csproj has no G3 configuration."""
    src = open(main.__file__, encoding="utf-8").read()
    csproj = open(_CSPROJ, encoding="utf-8").read()
    paths = [getattr(r, "path", "") for r in main.app.routes]
    g3_config = bool(_re.search(r"'\$\(Configuration\)'\s*==\s*'G3'", csproj)) and \
        "SCR_G3" in csproj
    _write_facts({"production": bool(main.ADM_PRODUCTION_ENABLED), "g3_config": g3_config,
                  "clause": "LEFT JOIN ffa_g3_seats g ON g.player_id = q.player_id AND g.expires_at > now()" in src,
                  "route": "/api/v1/admin/ffa-g3-seats" in paths})
    if not main.ADM_PRODUCTION_ENABLED:
        assert "LEFT JOIN ffa_g3_seats g ON g.player_id = q.player_id AND g.expires_at > now()" \
            in src, "S58 clause"
        assert "/api/v1/admin/ffa-g3-seats" in paths, "S58 route"
        assert g3_config, "S58 G3 configuration"
    else:
        assert "ffa_g3_seats" not in src, "S58 production query"
        assert not any("ffa-g3-seats" in p for p in paths), "S58 production route"
        drops = [f for f in os.listdir(_SQL_DIR) if f.endswith(".sql") and _re.search(
            r"DROP\s+TABLE\s+(IF\s+EXISTS\s+)?ffa_g3_seats",
            open(os.path.join(_SQL_DIR, f), encoding="utf-8").read(), _re.I)]
        assert drops, "S58 production drop"
        assert not g3_config and "SCR_G3" not in csproj, "S58 production configuration"


# -- writer 7 (d) and the gone record (S64), the release (S66), section 12's
#    closures (N8, N10, N12), the census literal and the assembly pool --

_REAL_SESSION_CHECK = main._check_steam_session


def _s64_res(lob):
    """Distinct placements for seven seats: R (seat 6) places fifth, below
    seats 0, 1, 4 and 2, with a non-zero signed tally."""
    s = lob.sids
    return {s[0]: (5, 10), s[1]: (4, 8), s[2]: (3, 6), s[3]: (2, 4), s[4]: (3, 7),
            s[5]: (1, 3), s[6]: (2, 5)}


async def _s64_lobby(env, t=32.0, **kw):
    """Seven seats, every one granted at t = 30 (R = seat 6, bound to actor 7
    by the ready_all numbering), then the clock at lobby age t."""
    lob = await env.lobby(7, t=30.0, **kw)
    await _full_grant(env, lob, 30.0)
    await env.at(lob, t)
    return lob


def _pool_spy(env):
    """Every (place, beaten, n_live) the report route pays with, in its award
    order (sorted player id): the beaten counts the settlement used."""
    calls = []
    orig = main._ffa_pool_shape

    def spy(place, beaten, n_live):
        calls.append((place, beaten, n_live))
        return orig(place, beaten, n_live)
    env.mp.setattr(main, "_ffa_pool_shape", spy)
    return calls


async def _beaten(env, lob, g, calls, tag):
    """Game g was paid with the beaten counts computed from its settled rows
    over the seats outside the effective unrated set: a seat in that set is
    in nobody's count, and every other seat is in the count of each seat it
    placed below."""
    rows = await _mp(env, lob, g)
    live = {s: r for s, r in rows.items() if not r["absent"]}
    order = sorted(live, key=lambda s: str(live[s]["player_id"]))
    want = [(live[s]["placement"],
             sum(1 for x in live if live[x]["placement"] > live[s]["placement"]),
             len(live)) for s in order]
    assert calls == want, (tag + " beaten", calls, want)


async def _econ(env, pid):
    """A player's FFA rating row and XP/gold totals (a second session)."""
    g = await env.conn.fetchrow(
        "SELECT rating, rating_deviation, volatility, games_played FROM glicko_ratings_ffa"
        " WHERE player_id = $1", pid)
    p = await env.conn.fetchrow(
        "SELECT total_xp, ffa_xp_earned, gold_earned FROM players WHERE id = $1", pid)
    return (dict(g) if g is not None else None), dict(p)


async def _gone(env, lob, slot):
    s = await env.seat(lob, slot)
    return s["gone_game"], s["gone_path"]


async def _refused(env, lob, g, slot, reason, res, tag, **kw):
    """A report of game g filed by `slot`, refused 409 with `reason` through
    _ffa_record_and_refuse: its quarantine row and its one refusal line, and
    no other write."""
    counts = await _report_counts(env, lob)
    room = (await env.lobby_row(lob))["photon_room_id"]
    rid = "%s_s%d_r%d" % (room, slot, g)
    mark = len(env.lines)
    r = await env.report(lob, g, res, reporter=lob.sids[slot], room=rid, **kw)
    new = [ln for ln in env.lines[mark:] if " refused (" in ln]
    q = await env.conn.fetchval(
        "SELECT reason FROM match_report_quarantine WHERE group_id = $1"
        "   AND photon_room_id = $2", lob.lid, rid)
    assert r.status == 409 and q == reason and len(new) == 1 \
        and (" refused (%s:" % reason) in new[0], (tag, r, q, new)
    now = await _report_counts(env, lob)
    assert now == dict(counts, quarantine=counts["quarantine"] + 1), (tag + " rows", counts, now)


async def _settled(env, lob, g, res, tag, *, rated, calls=None, **kw):
    """An accepted report of game g. rated=True: R (seat 6) rated and paid as
    any present seat. rated=False: R in the unrated set, its rating row and
    XP/gold totals unchanged. With `calls`, the beaten counts it paid."""
    before = await _econ(env, lob.pids[6])
    m = len(calls) if calls is not None else 0
    r = await env.report(lob, g, res, **kw)
    rows = await _mp(env, lob, g)
    assert r.status == 200 and 6 in rows, (tag, r)
    if rated:
        assert _rated(rows[6]) and rows[6]["xp_gained"] > 0 and rows[6]["gold_gained"] > 0, \
            (tag + " rated", rows[6])
    else:
        assert _unrated(rows[6]), (tag + " unrated", rows[6])
        assert await _econ(env, lob.pids[6]) == before, (tag + " unchanged", before)
    if calls is not None:
        await _beaten(env, lob, g, calls[m:], tag)
    return rows


def test_s64_i_ii_the_false_mark_and_the_refuted_tally(monkeypatch):
    """S64 (i): another seat's game-1 report marks a present R left_early at
    5 points: no gone record; game 2 settles R as any present seat and R's
    own game-2 report is accepted. (ii) the same mark refuted by R's signed
    tally: game 1 through the refutation guard with the raw fields kept,
    game 2 as in (i)."""
    async def body(env):
        calls = _pool_spy(env)
        for case in ("mark", "refuted"):
            lob = await _s64_lobby(env)
            s, res = lob.sids, _s64_res(lob)
            await env.ready_all(lob, list(range(7)))
            if case == "mark":
                kw = {"left": {s[6]}, "gp_leave": {s[6]: 5}}
            else:
                kw = {"left": {s[6]}, "absent": {s[6]}, "gp_leave": {s[6]: 1}}
            mark = len(env.lines)
            rows = await _settled(env, lob, 1, res, "S64 %s game 1" % case, rated=True,
                                  reporter=s[0], **kw)
            if case == "refuted":
                new = env.lines[mark:]
                assert any(("absent claim REFUTED for %s" % s[6]) in ln for ln in new) and \
                    any(("early-leave grace REFUTED for %s" % s[6]) in ln for ln in new), \
                    ("S64 ii guard", new)
                assert rows[6]["left_early"] is True and rows[6]["game_points_at_leave"] == 1, \
                    ("S64 ii raw fields", rows[6])
            assert await _gone(env, lob, 6) == (None, None), ("S64 i no record", case)
            await env.at(lob, 40.0)
            await env.ready_all(lob, list(range(7)))
            await _settled(env, lob, 2, res, "S64 %s game 2" % case, rated=True, calls=calls,
                           reporter=s[6])
            assert await _gone(env, lob, 6) == (None, None), ("S64 i after", case)
    run_env(monkeypatch, body)


def test_s64_iii_the_seats_own_leave_corroborated(monkeypatch):
    """S64 (iii): actor 7 has left, two current witnesses omit it, none lists
    it, R's own census is 30 s old: R's leave during game 1 writes gone_game
    1 and gone_path 'leave' in its own transaction and R stays granted; game
    1 settles R by today's rules; game 2, filed by another seat with R a
    present leaver, leaves R unrated, unpaid and in nobody's beaten count;
    R's own game-2 report is refused (left_reporter)."""
    async def body(env):
        calls = _pool_spy(env)
        lob = await _s64_lobby(env, t=60.0)
        s, res = lob.sids, _s64_res(lob)
        await _omit(env, lob, [0, 2], 6)
        a = await env.leave(lob, 6)
        assert a.status == 200, ("S64 iii leave", a)
        seat = await env.seat(lob, 6)
        assert (seat["gone_game"], seat["gone_path"], seat["verdict"]) == (1, "leave", "granted"), \
            ("S64 iii record", seat["gone_game"], seat["gone_path"], seat["verdict"])
        assert env.asm_lines("gone_trigger slot=6 path=leave result=witness") and \
            env.asm_lines("gone slot=6 game=1 path=leave by=0,2 "), \
            ("S64 iii prints", env.asm_lines("gone"))
        await _settled(env, lob, 1, res, "S64 iii game 1", rated=True, reporter=s[0],
                       left={s[6]}, gp_leave={s[6]: 5})
        await _refused(env, lob, 2, 6, "left_reporter", res, "S64 iii refused")
        await _settled(env, lob, 2, res, "S64 iii game 2", rated=False, calls=calls,
                       reporter=s[0], left={s[6]}, gp_leave={s[6]: 8})
        assert env.asm_lines("report game=2 unrated=6:d"), "S64 iii print"
    run_env(monkeypatch, body)


def test_s64_iv_the_false_claim(monkeypatch):
    """S64 (iv): after game 1's report, R's arrived claims actor 12 in its
    bound region while actor 7 is present (every current witness lists 7,
    R's own census within 10 s lists itself): the claim runs the witness
    test and writes nothing; game 3 settles R as any present seat and R's
    game-3 report is accepted; a claim of actor 7, or of another region,
    triggers nothing."""
    async def body(env):
        calls = _pool_spy(env)
        lob = await _s64_lobby(env)
        s, res = lob.sids, _s64_res(lob)
        r = await env.report(lob, 1, res, reporter=s[0])
        assert r.status == 200, ("S64 iv game 1", r)
        await env.at(lob, 45.0)
        await env.ready_all(lob, list(range(7)))
        mark = len(env.lines)
        a = await env.connect(lob, 6, "arrived", actor=12, region=lob.region, count=7)
        got = [ln for ln in env.lines[mark:] if "gone_trigger" in ln]
        assert a.status == 200 and len(got) == 1 and \
            "gone_trigger slot=6 claim=12 bound=7 result=none" in got[0], ("S64 iv trigger", a, got)
        assert await _gone(env, lob, 6) == (None, None), "S64 iv no record"
        r = await env.report(lob, 2, res, reporter=s[0])
        assert r.status == 200, ("S64 iv game 2", r)
        await env.at(lob, 50.0)
        await env.ready_all(lob, list(range(7)))
        await _settled(env, lob, 3, res, "S64 iv game 3", rated=True, calls=calls, reporter=s[6])
        for claim, region in ((7, lob.region), (12, "us")):
            mark = len(env.lines)
            a = await env.connect(lob, 6, "arrived", actor=claim, region=region, count=7)
            got = [ln for ln in env.lines[mark:] if "gone_trigger" in ln]
            assert a.status == 200 and got == [], ("S64 iv no trigger", claim, region, got)
        assert await _gone(env, lob, 6) == (None, None), "S64 iv after"
    run_env(monkeypatch, body)


def test_s64_iv_a_the_true_leave(monkeypatch):
    """S64 (iv-a): actor 7 leaves during game 2 and R's leave lands while every
    peer's census still lists 7 (result=none, no record); the census after
    which two current witnesses omit 7 and none lists it writes gone_game 2
    and gone_path 'leave'; game 2 settles R as its leaver by today's rules,
    game 3 leaves R unrated and refuses R's game-3 report."""
    async def body(env):
        calls = _pool_spy(env)
        lob = await _s64_lobby(env)
        s, res = lob.sids, _s64_res(lob)
        r = await env.report(lob, 1, res, reporter=s[0])
        assert r.status == 200, ("S64 iv-a game 1", r)
        await env.at(lob, 45.0)
        await env.ready_all(lob, list(range(7)))
        a = await env.leave(lob, 6)
        assert a.status == 200 and env.asm_lines("gone_trigger slot=6 path=leave result=none"), \
            ("S64 iv-a leave", a)
        assert await _gone(env, lob, 6) == (None, None), "S64 iv-a no record at the leave"
        await env.at(lob, 60.0)
        await _omit(env, lob, [2], 6)
        a = await env.census_of(lob, 0, [0, 1, 2, 3, 4, 5])
        assert a.status == 200 and await _gone(env, lob, 6) == (2, "leave"), \
            ("S64 iv-a record", a, await _gone(env, lob, 6))
        assert env.asm_lines("gone slot=6 game=2 path=leave by=0,2 "), "S64 iv-a print"
        await _settled(env, lob, 2, res, "S64 iv-a game 2", rated=True, reporter=s[0],
                       left={s[6]}, gp_leave={s[6]: 8})
        await _refused(env, lob, 3, 6, "left_reporter", res, "S64 iv-a refused")
        await _settled(env, lob, 3, res, "S64 iv-a game 3", rated=False, calls=calls,
                       reporter=s[0])
    run_env(monkeypatch, body)


def test_s64_iv_b_the_corroborated_absence(monkeypatch):
    """S64 (iv-b): actor 7 has left, two current witnesses omit it, none lists
    it, and R's own fresh census lists slot 6 as actor 12, not 7: R's claim of
    actor 12 writes gone_game 2 and gone_path 'witness' in the claim's own
    transaction; game 3 as in (iv-a)."""
    async def body(env):
        calls = _pool_spy(env)
        lob = await _s64_lobby(env)
        s, res = lob.sids, _s64_res(lob)
        r = await env.report(lob, 1, res, reporter=s[0])
        assert r.status == 200, ("S64 iv-b game 1", r)
        await env.at(lob, 60.0)
        await _omit(env, lob, [0, 2], 6)
        await env.census_row(lob, 6, [(x, 1 + x, 1, 1) for x in range(6)] + [(6, 12, 1, 1)])
        mark = len(env.lines)
        a = await env.connect(lob, 6, "arrived", actor=12, region=lob.region, count=7)
        got = [ln for ln in env.lines[mark:] if "gone" in ln]
        assert a.status == 200 and await _gone(env, lob, 6) == (2, "witness"), \
            ("S64 iv-b record", a, got)
        assert any("gone_trigger slot=6 claim=12 bound=7 result=witness" in ln for ln in got), \
            ("S64 iv-b print", got)
        await _settled(env, lob, 2, res, "S64 iv-b game 2", rated=True, reporter=s[0])
        await _refused(env, lob, 3, 6, "left_reporter", res, "S64 iv-b refused")
        await _settled(env, lob, 3, res, "S64 iv-b game 3", rated=False, calls=calls,
                       reporter=s[0])
    run_env(monkeypatch, body)


_S64_V = ("two", "one", "listing", "own", "gone", "claim", "seen", "anon", "region")


def test_s64_v_the_witness_path(monkeypatch):
    """S64 (v): with R's own census 30 s old, two current witnesses (census_anon
    0, R's region) omitting actor 7 write gone_path 'witness'; one writes
    nothing; a third current witness listing 7 blocks it; R's own census
    within 10 s listing itself blocks it; a witness that is itself gone,
    whose claim differs from its binding, whose census_seen_at precedes R's
    verdict_at, or whose census is anonymous or from another region, does
    not count."""
    async def body(env):
        got = {}
        for case in _S64_V:
            lob = await _s64_lobby(env, t=60.0)
            present = [(x, 1 + x, 1, 1) for x in range(6)]
            kw = {"claim": {"claim": 20}, "seen": {"seen": 29.0}, "anon": {"anon": 1},
                  "region": {"region": "us"}}.get(case, {})
            if case != "one":
                await env.census_row(lob, 2, present, **kw)
            if case == "gone":
                await env.set_seat(lob, 2, gone_game=1, gone_path="witness")
            if case == "listing":
                await env.census_row(lob, 3, present + [(6, 7, 1, 1)])
            if case == "own":
                await env.census_row(lob, 6, present + [(6, 7, 1, 1)])
            a = await env.census_of(lob, 0, [0, 1, 2, 3, 4, 5])
            assert a.status == 200, ("S64 v census", case, a)
            got[case] = await _gone(env, lob, 6)
        want = {c: ((1, "witness") if c == "two" else (None, None)) for c in _S64_V}
        assert got == want, ("S64 v", got)
    run_env(monkeypatch, body)


def test_s64_vi_the_omitted_report(monkeypatch):
    """S64 (vi): R's record names game 1, written by its leave's own test (as
    in (iii)) or by a census of game 1 (as in (iv-a)); game 1's accepted
    report leaves R's leave out: game 2 still settles R unrated and refuses
    R's report. With R present and no record, the same report settles game
    1 as today and game 2 settles R as any present seat. A report that omits
    R's ROW is refused 403 by today's exact-roster rule with no write (the
    build's reading of "omits R's row", notes)."""
    async def body(env):
        calls = _pool_spy(env)
        for case in ("leave", "census", "present"):
            lob = await _s64_lobby(env, t=45.0)
            s, res = lob.sids, _s64_res(lob)
            if case == "leave":
                await env.at(lob, 60.0)
                await _omit(env, lob, [0, 2], 6)
                await env.leave(lob, 6)
            elif case == "census":
                await env.ready_all(lob, list(range(7)))
                await env.leave(lob, 6)
                await env.at(lob, 60.0)
                await _omit(env, lob, [2], 6)
                await env.census_of(lob, 0, [0, 1, 2, 3, 4, 5])
            want = (None, None) if case == "present" else (1, "leave")
            assert await _gone(env, lob, 6) == want, ("S64 vi record", case)
            counts = await _report_counts(env, lob)
            r = await env.report(lob, 1, res, reporter=s[0], omit={s[6]})
            assert r.status == 403 and await _report_counts(env, lob) == counts, \
                ("S64 vi row omitted", case, r)
            await _settled(env, lob, 1, res, "S64 vi game 1 " + case, rated=True,
                           reporter=s[0])
            if case == "present":
                await _settled(env, lob, 2, res, "S64 vi game 2 present", rated=True,
                               calls=calls, reporter=s[6])
            else:
                await _refused(env, lob, 2, 6, "left_reporter", res, "S64 vi refused " + case)
                await _settled(env, lob, 2, res, "S64 vi game 2 " + case, rated=False,
                               calls=calls, reporter=s[0])
    run_env(monkeypatch, body)


def test_s64_vii_the_in_flight_leave(monkeypatch):
    """S64 (vii): R leaves during game 2 while game 1's report is still in
    flight (games_played 0). When the transaction that writes R's record
    (the leave's own, or a corroborating census's) commits before game 1's
    acceptance, the record names game 1 and game 2's report (R leaving game
    2 at 8 points) leaves R unrated; when the corroborating census commits
    after the acceptance, it names game 2 and game 2 settles R as its leaver
    by today's rules (R42)."""
    async def body(env):
        for case in ("leave", "census_before", "census_after"):
            lob = await _s64_lobby(env, t=45.0)
            s, res = lob.sids, _s64_res(lob)
            if case == "leave":
                await env.at(lob, 60.0)
                await _omit(env, lob, [0, 2], 6)
                await env.leave(lob, 6)
            else:
                await env.ready_all(lob, list(range(7)))
                await env.leave(lob, 6)
                assert await _gone(env, lob, 6) == (None, None), ("S64 vii leave", case)
                if case == "census_after":
                    r = await env.report(lob, 1, res, reporter=s[0])
                    assert r.status == 200, ("S64 vii game 1", case, r)
                await env.at(lob, 60.0)
                await _omit(env, lob, [2], 6)
                await env.census_of(lob, 0, [0, 1, 2, 3, 4, 5])
            want = (2, "leave") if case == "census_after" else (1, "leave")
            assert await _gone(env, lob, 6) == want, \
                ("S64 vii record", case, await _gone(env, lob, 6))
            if case != "census_after":
                await _settled(env, lob, 1, res, "S64 vii game 1 " + case, rated=True,
                               reporter=s[0])
            await _settled(env, lob, 2, res, "S64 vii game 2 " + case,
                           rated=(case == "census_after"), reporter=s[0],
                           left={s[6]}, gp_leave={s[6]: 8})
    run_env(monkeypatch, body)


def test_s64_viii_first_write_wins_and_the_negatives(monkeypatch):
    """S64 (viii): a later claim trigger, witness finding or leave trigger
    leaves R's record as first written, and the leave, corroborated by that
    record, appends R's departure (N8); a seat admissible when it leaves,
    and every seat of an unstarted lobby, get no record; a lobby that is not
    assembly_v1 settles as today whatever its seat rows hold; the CHECK
    ck_ffa_seat_gone refuses a gone_game without a gone_path and a path
    outside 'leave' and 'witness'."""
    async def body(env):
        lob = await _s64_lobby(env, t=60.0)
        s, res = lob.sids, _s64_res(lob)
        await _omit(env, lob, [2], 6)
        await env.census_of(lob, 0, [0, 1, 2, 3, 4, 5])
        assert await _gone(env, lob, 6) == (1, "witness"), "S64 viii first"
        r = await env.report(lob, 1, res, reporter=s[0])
        assert r.status == 200, ("S64 viii game 1", r)
        await env.at(lob, 62.0)
        await _omit(env, lob, [2, 3], 6)
        await env.census_row(lob, 6, [(x, 1 + x, 1, 1) for x in range(6)] + [(6, 12, 1, 1)])
        mark = len(env.lines)
        a = await env.connect(lob, 6, "arrived", actor=12, region=lob.region, count=6)
        assert a.status == 200 and \
            any("gone_trigger slot=6 claim=12 bound=7 result=none" in ln
                for ln in env.lines[mark:]), ("S64 viii claim", a, env.lines[mark:])
        await env.census_of(lob, 0, [0, 1, 2, 3, 4, 5])
        a = await env.leave(lob, 6)
        assert a.status == 200 and await _gone(env, lob, 6) == (1, "witness"), \
            ("S64 viii first write wins", a, await _gone(env, lob, 6))
        assert env.asm_lines("gone_trigger slot=6 path=leave result=none"), "S64 viii leave"
        row = await env.lobby_row(lob)
        assert list(row["departed_ids"]) == [lob.pids[6]], \
            ("S64 viii departure", row["departed_ids"])

        sh = await _short(env)
        await env.at(sh, 60.0)
        await _omit(env, sh, [0, 2], 4)
        a = await env.leave(sh, 4)
        seat = await env.seat(sh, 4)
        assert a.status == 200 and \
            (seat["gone_game"], seat["gone_path"], seat["verdict"]) == (None, None, "left"), \
            ("S64 viii admissible", a, seat["gone_game"], seat["verdict"])

        un = await env.lobby(5, t=16.0)
        await env.ready_all(un, [0, 1, 2, 3])
        await env.census_of(un, 0, [0, 1, 2, 3])
        await env.leave(un, 4)
        assert [x["gone_game"] for x in await env.seats(un)] == [None] * 5, "S64 viii unstarted"

        ug = await env.lobby(7, gated=False, t=30.0)
        await env.set_lobby(ug, start_granted_at=30.0)
        await env.set_seat(ug, 6, gone_game=1, gone_path="witness")
        r = await env.report(ug, 1, _s64_res(ug), reporter=ug.sids[0])
        assert r.status == 200, ("S64 viii ungated game 1", r)
        r = await env.report(ug, 2, _s64_res(ug), reporter=ug.sids[6])
        rows = await _mp(env, ug, 2)
        assert r.status == 200 and _rated(rows[6]), ("S64 viii not assembly_v1", r, rows.get(6))

        upd = ("UPDATE ffa_assembly_seats SET gone_game = $3, gone_path = $4"
               " WHERE lobby_id = $1 AND slot = $2")
        for gp in (None, "claim"):
            with pytest.raises(_asyncpg.CheckViolationError):
                await env.conn.execute(upd, lob.lid, 5, 1, gp)
        await env.conn.execute(upd, lob.lid, 5, 1, "witness")
        assert await _gone(env, lob, 5) == (1, "witness"), "S64 viii CHECK twin"
    run_env(monkeypatch, body)


async def _waiters(env, bpid, n, tag):
    """Wait until n backends wait, directly or through one another, on the
    blocker's lock (the second request queues behind the first)."""
    k = 0
    for _ in range(200):
        k = await env.conn.fetchval(
            "WITH RECURSIVE w(pid) AS ("
            "  SELECT pid FROM pg_stat_activity WHERE $1 = ANY(pg_blocking_pids(pid))"
            "  UNION SELECT a.pid FROM pg_stat_activity a JOIN w"
            "    ON w.pid = ANY(pg_blocking_pids(a.pid)))"
            " SELECT count(*) FROM w", bpid)
        if k >= n:
            return k
        await asyncio.sleep(0.02)
    raise AssertionError((tag, "waiting", k, n))


def test_s64_x_the_lock(monkeypatch):
    """S64 (x): the transaction that writes R's record (a corroborating census,
    or R's leave with its witness test holding) and game 1's acceptance run
    in two sessions, ordered through the lobby row lock: the acceptance
    first, the record names game 2; the record's transaction first, game 1.
    With the leave's own test not holding, the leave before the acceptance
    and the corroborating census after it name game 2."""
    async def body(env):
        # The ordering is what this control forces, not the deadline: a
        # census queued behind a whole report acceptance must not answer 503
        # on a loaded seat, so the budget is widened for this case only.
        env.mp.setattr(main, "ASM_TXN_DEADLINE_S", 30)
        got = {}
        for writer in ("census", "leave"):
            for first in ("accept", "record"):
                lob = await _s64_lobby(env, t=60.0)
                s, res = lob.sids, _s64_res(lob)
                await _omit(env, lob, [2] if writer == "census" else [0, 2], 6)
                rep = await env.report_req(lob, 1, res, reporter=s[0])
                age = _age_ms(env, await env.ts(lob, 0))
                ents = [env.entry(lob, x, 1 + x) for x in range(6)]

                def record():
                    if writer == "census":
                        return env.assembly(lob, 0, 1, ents, seen_age_ms=age)
                    return env.leave(lob, 6)
                conn, tr, bpid = await _blocker(env, lob)
                try:
                    t1 = asyncio.ensure_future(env.submit(rep) if first == "accept"
                                               else record())
                    await _waiters(env, bpid, 1, "S64 x first")
                    t2 = asyncio.ensure_future(record() if first == "accept"
                                               else env.submit(rep))
                    await _waiters(env, bpid, 2, "S64 x second")
                finally:
                    await tr.commit()
                    await conn.close()
                a1, a2 = await t1, await t2
                assert a1.status == a2.status == 200, ("S64 x answers", writer, first, a1, a2)
                got[(writer, first)] = await _gone(env, lob, 6)
        want = {("census", "accept"): (2, "witness"), ("census", "record"): (1, "witness"),
                ("leave", "accept"): (2, "leave"), ("leave", "record"): (1, "leave")}
        assert got == want, ("S64 x", got)
        lob = await _s64_lobby(env, t=45.0)
        s, res = lob.sids, _s64_res(lob)
        await env.ready_all(lob, list(range(7)))
        await env.leave(lob, 6)
        r = await env.report(lob, 1, res, reporter=s[0])
        assert r.status == 200, ("S64 x staged game 1", r)
        await env.at(lob, 60.0)
        await _omit(env, lob, [2], 6)
        await env.census_of(lob, 0, [0, 1, 2, 3, 4, 5])
        assert await _gone(env, lob, 6) == (2, "leave"), ("S64 x staged", await _gone(env, lob, 6))
    run_env(monkeypatch, body)


def _others(snap, lob, slot):
    """The snapshot's seat, queue and lease rows of every seat but `slot`."""
    pid = lob.pids[slot]
    return {"seats": [r for r in snap["seats"] if not (r["lobby_id"] == lob.lid
                                                      and r["slot"] == slot)],
            "queue": [r for r in snap["queue"] if r["player_id"] != pid],
            "leases": [r for r in snap["leases"] if r["player_id"] != pid]}


@pytest.mark.parametrize("part", ["leave", "all_but_one"])
def test_s64_xi_the_false_leave(monkeypatch, part):
    """S64 (xi) under section 12's N8, one node per part. The false leave:
    during game 2 R's leave lands while actor 7 is present (every current
    witness lists 7, R's own fresh census lists itself): R's receipts,
    left_path 'departure' and its own queue row go; nothing is appended to
    departed_ids, no verdict and no record is written, and no other seat's
    row, lease or queue row changes; censuses that keep listing 7, or one
    omitting witness among listing ones, write nothing; games 2 and 3 settle
    R as any present seat and R's report is accepted. All but one: every
    other member's leave lands too while R's is the only current census: the
    lobby stays active with departed_ids empty and its wager unsettled and
    unrefunded."""
    async def body(env):
        if part == "leave":
            calls = _pool_spy(env)
            lob = await _s64_lobby(env)
            s, res = lob.sids, _s64_res(lob)
            r = await env.report(lob, 1, res, reporter=s[0])
            assert r.status == 200, ("S64 xi game 1", r)
            await env.at(lob, 45.0)
            await env.ready_all(lob, list(range(7)))
            before = await env.snapshot()
            row0 = await env.lobby_row(lob)
            a = await env.leave(lob, 6)
            assert a.status == 200 and env.asm_lines("gone_trigger slot=6 path=leave result=none"), \
                ("S64 xi leave", a)
            seat = await env.seat(lob, 6)
            assert seat["left_at"] is not None and seat["left_path"] == "departure" and \
                seat["verdict"] == "granted" and seat["start_roster"] and \
                (seat["gone_game"], seat["gone_path"]) == (None, None), ("S64 xi seat", seat)
            assert await env.queue_row(lob, 6) is None, "S64 xi own queue row"
            row = await env.lobby_row(lob)
            assert list(row["departed_ids"]) == [] and \
                row["departure_causes"] == row0["departure_causes"] and row["status"] == "active", \
                ("S64 xi N8 no departure", row["departed_ids"], row["status"])
            assert _others(await env.snapshot(), lob, 6) == _others(before, lob, 6), \
                "S64 xi other seats untouched"
            await env.at(lob, 47.0)
            await env.ready_all(lob, list(range(7)))
            await env.census_of(lob, 0, list(range(7)))
            assert await _gone(env, lob, 6) == (None, None), "S64 xi listing census"
            await env.at(lob, 49.0)
            await env.ready_all(lob, list(range(7)))
            await _omit(env, lob, [2], 6)
            await env.census_of(lob, 1, list(range(7)))
            assert await _gone(env, lob, 6) == (None, None), "S64 xi one omitting witness"
            await _settled(env, lob, 2, res, "S64 xi game 2", rated=True, calls=calls, reporter=s[0])
            await _settled(env, lob, 3, res, "S64 xi game 3", rated=True, calls=calls, reporter=s[6])
        else:
            ab = await _s64_lobby(env)
            bp, _bs = await env.bettor()
            await env.wager(ab, bp, ab.pids[0], game=1)
            bets = await env.bets(ab)
            await env.at(ab, 60.0)
            await env.census_row(ab, 6, [(6, 7, 1, 1)])
            for x in (6, 0, 1, 2, 3, 4, 5):
                a = await env.leave(ab, x)
                assert a.status == 200, ("S64 xi all but one leave", x, a)
            row = await env.lobby_row(ab)
            assert row["status"] == "active" and list(row["departed_ids"]) == [] and \
                row["completed_at"] is None, ("S64 xi all but one", row["status"], row["departed_ids"])
            assert await env.bets(ab) == bets and await env.refunds(ab) == 0, "S64 xi all but one bets"
            assert [x["gone_game"] for x in await env.seats(ab)] == [None] * 7, "S64 xi no record"
    run_env(monkeypatch, body)


def test_n8_a_delayed_leave_touches_no_other_row(monkeypatch):
    """Section 12, N8: in a started gated lobby whose departed_ids already
    holds all but two members, R's delayed leave while its actor is present
    (the next census shows it present) appends nothing and leaves every
    other seat's queue row and lease untouched; the control, the same leave
    corroborated by two current witnesses, appends R and releases the other
    seats' queue rows and leases at all but one (a mechanism control: the
    seeded departed seats serve as the witnesses, notes)."""
    async def body(env):
        for case in ("present", "corroborated"):
            lob = await _s64_lobby(env, t=60.0)
            await env.set_lobby(lob, departed_ids=lob.pids[:5])
            if case == "present":
                await env.ready_all(lob, list(range(7)))
            else:
                await _omit(env, lob, [0, 2], 6)
            before = await env.snapshot()
            a = await env.leave(lob, 6)
            assert a.status == 200, ("N8 leave", case, a)
            row = await env.lobby_row(lob)
            if case == "present":
                c = await env.census_of(lob, 0, list(range(7)))
                assert c.status == 200, ("N8 next census", c)
                row = await env.lobby_row(lob)
                assert sorted(row["departed_ids"]) == sorted(lob.pids[:5]) and \
                    row["status"] == "active", ("N8 no append", row["departed_ids"])
                assert await _gone(env, lob, 6) == (None, None), "N8 no record"
                got = _others(await env.snapshot(), lob, 6)
                want = _others(before, lob, 6)
                assert got["queue"] == want["queue"] and got["leases"] == want["leases"], \
                    "N8 other rows untouched"
            else:
                assert sorted(row["departed_ids"]) == sorted(lob.pids[:5] + [lob.pids[6]]) \
                    and row["status"] == "active", ("N8 control append", row["departed_ids"])
                gone = [x for x in range(6) if await env.queue_row(lob, x) is None
                        and await env.lease(lob, x) is None]
                assert gone == list(range(6)), ("N8 control release", gone)
    run_env(monkeypatch, body)


def test_s64_xi_a_the_corroborated_leave(monkeypatch):
    """S64 (xi-a): R's leave lands during game 2 while two current witnesses
    still list 7 (result=none); the census after which two current witnesses
    omit 7 writes gone_game 2 and gone_path 'leave' at that census's game,
    and game 3 leaves R unrated. Later-census variant: R's leave lands while 7
    is present, R plays games 2 and 3, actor 7 leaves during game 4 with no
    further request: the corroborating census writes gone_game 4, never 2;
    games 2 and 3 settle R as any present seat, game 4 by today's rules as
    the game it left, and game 5 with R unrated."""
    async def body(env):
        calls = _pool_spy(env)
        lob = await _s64_lobby(env)
        s, res = lob.sids, _s64_res(lob)
        r = await env.report(lob, 1, res, reporter=s[0])
        assert r.status == 200, ("S64 xi-a game 1", r)
        await env.at(lob, 45.0)
        await env.ready_all(lob, list(range(7)))
        await env.leave(lob, 6)
        assert env.asm_lines("gone_trigger slot=6 path=leave result=none"), "S64 xi-a leave"
        await env.at(lob, 60.0)
        await _omit(env, lob, [2], 6)
        await env.census_of(lob, 0, [0, 1, 2, 3, 4, 5])
        assert await _gone(env, lob, 6) == (2, "leave"), ("S64 xi-a record", await _gone(env, lob, 6))
        await _settled(env, lob, 2, res, "S64 xi-a game 2", rated=True, reporter=s[0],
                       left={s[6]}, gp_leave={s[6]: 8})
        await _settled(env, lob, 3, res, "S64 xi-a game 3", rated=False, calls=calls,
                       reporter=s[0])

        lob = await _s64_lobby(env)
        s, res = lob.sids, _s64_res(lob)
        r = await env.report(lob, 1, res, reporter=s[0])
        assert r.status == 200, ("S64 xi-a later game 1", r)
        await env.at(lob, 45.0)
        await env.ready_all(lob, list(range(7)))
        await env.leave(lob, 6)
        await _settled(env, lob, 2, res, "S64 xi-a later game 2", rated=True, calls=calls,
                       reporter=s[0])
        await env.at(lob, 50.0)
        await env.ready_all(lob, list(range(7)))
        await _settled(env, lob, 3, res, "S64 xi-a later game 3", rated=True, calls=calls,
                       reporter=s[0])
        assert await _gone(env, lob, 6) == (None, None), "S64 xi-a later no record yet"
        await env.at(lob, 70.0)
        await _omit(env, lob, [2], 6)
        await env.census_of(lob, 0, [0, 1, 2, 3, 4, 5])
        assert await _gone(env, lob, 6) == (4, "leave"), \
            ("S64 xi-a later record", await _gone(env, lob, 6))
        await _settled(env, lob, 4, res, "S64 xi-a later game 4", rated=True, reporter=s[0],
                       left={s[6]}, gp_leave={s[6]: 8})
        await _settled(env, lob, 5, res, "S64 xi-a later game 5", rated=False, calls=calls,
                       reporter=s[0])
    run_env(monkeypatch, body)


def test_s64_xi_b_the_absence_corroborated_at_the_leave(monkeypatch):
    """S64 (xi-b): R's process died with actor 7 during game 2; two current
    witnesses omit 7, none lists it, R's own census is 28 s old and no census
    transaction wrote R's record: R's relaunch's startup leave writes
    gone_game 2 and gone_path 'leave' in its own transaction, and game 3 as
    in (iv-a)."""
    async def body(env):
        calls = _pool_spy(env)
        lob = await _s64_lobby(env)
        s, res = lob.sids, _s64_res(lob)
        r = await env.report(lob, 1, res, reporter=s[0])
        assert r.status == 200, ("S64 xi-b game 1", r)
        await env.at(lob, 60.0)
        await _omit(env, lob, [0, 2], 6)
        a = await env.leave(lob, 6)
        assert a.status == 200 and await _gone(env, lob, 6) == (2, "leave") and \
            env.asm_lines("gone_trigger slot=6 path=leave result=witness"), \
            ("S64 xi-b record", a, await _gone(env, lob, 6))
        await _settled(env, lob, 2, res, "S64 xi-b game 2", rated=True, reporter=s[0],
                       left={s[6]}, gp_leave={s[6]: 8})
        await _refused(env, lob, 3, 6, "left_reporter", res, "S64 xi-b refused")
        await _settled(env, lob, 3, res, "S64 xi-b game 3", rated=False, calls=calls,
                       reporter=s[0])
    run_env(monkeypatch, body)


def _s66_strip(snap, lob, slot):
    """The snapshot with the caller's own release columns, queue row and
    lease taken out: what the release must leave byte-identical."""
    pid = lob.pids[slot]
    out = dict(snap)
    out["seats"] = [dict(r, released_at=None, release_why=None)
                    if (r["lobby_id"] == lob.lid and r["slot"] == slot) else r
                    for r in snap["seats"]]
    out["queue"] = [r for r in snap["queue"] if r["player_id"] != pid]
    out["leases"] = [r for r in snap["leases"] if r["player_id"] != pid]
    return out


@pytest.mark.parametrize("part", ["i-iii", "iv", "v", "check"])
def test_s66_the_release(monkeypatch, part):
    """S66, one node per part. (i) fence_expired: a granted seat's release
    answers 200, writes released_at and release_why, frees its lease for this
    lobby and deletes its own queue row, prints lease=1 row=1, and leaves
    every other row of the fixture (departures, causes, receipts, verdicts,
    gone records, status, wagers, every other seat's row, lease and queue
    row) byte-identical; (ii) join_timeout on an admitted_late seat, which
    keeps its verdict; (iii) a repeat answers 200 with lease=0 row=0 and
    keeps the first values; (iv) a why outside the two, or a body without
    steam_id, is a 422, a caller with no seat row in that lobby a 404, a
    failed session check the leave route's refusal, each with no write; (v)
    a release naming a lobby other than the one the caller's lease holds
    frees no lease and deletes no queue row there; the CHECK
    ck_ffa_seat_release."""
    import httpx
    import database

    async def body(env):
        if part == "i-iii":
            lob = await _s64_lobby(env, t=40.0)
            bp, _bs = await env.bettor()
            await env.wager(lob, bp, lob.pids[0], game=1)
            before = await env.snapshot()
            a = await env.release(lob, 1, "fence_expired")
            seat = await env.seat(lob, 1)
            assert a.status == 200 and a.body == {"status": "ok"} and seat["released_at"] is not None \
                and seat["release_why"] == "fence_expired", ("S66 i", a, seat["release_why"])
            assert await env.queue_row(lob, 1) is None and await env.lease(lob, 1) is None, \
                "S66 i own rows"
            assert env.asm_lines("release slot=1 why=fence_expired lease=1 row=1"), "S66 i print"
            assert _s66_strip(await env.snapshot(), lob, 1) == _s66_strip(before, lob, 1), \
                "S66 i byte-identical"
            a = await env.release(lob, 1, "join_timeout")
            again = await env.seat(lob, 1)
            assert a.status == 200 and env.asm_lines("release slot=1 why=join_timeout lease=0 row=0") \
                and (again["released_at"], again["release_why"]) == \
                (seat["released_at"], "fence_expired"), ("S66 iii", a, again["release_why"])

            sh = await _short(env, 6)
            await env.at(sh, 50.0)
            await _admit(env, sh, 4, 5, 0, [0, 1, 2, 3])
            before = await env.snapshot()
            a = await env.release(sh, 4, "join_timeout")
            seat = await env.seat(sh, 4)
            assert a.status == 200 and seat["verdict"] == "admitted_late" and \
                seat["release_why"] == "join_timeout", ("S66 ii", a, seat["verdict"])
            assert env.asm_lines("release slot=4 why=join_timeout lease=1 row=1"), "S66 ii print"
            assert _s66_strip(await env.snapshot(), sh, 4) == _s66_strip(before, sh, 4), \
                "S66 ii byte-identical"
        elif part == "iv":
            lob = await _s64_lobby(env, t=40.0)
            other = await env.lobby(5, t=40.0)
            before = await env.snapshot()
            try:
                a = await env.release(lob, 2, "other")
            except Exception as exc:  # a write the CHECK refuses surfaces here
                a = cf_asm.Answer("raised", {"error": type(exc).__name__})
            assert a.status == 422, ("S66 iv why", a)
            a = await env.release(lob, 0, "fence_expired", steam_id=other.sids[0])
            assert a.status == 404, ("S66 iv no seat row", a)
            a = await env.release(lob, 0, "fence_expired", steam_id=str(cf_asm.STEAM_BASE + 999999))
            assert a.status == 404, ("S66 iv no player", a)

            async def db_dep():
                async with env.sm() as db:
                    yield db
            main.app.dependency_overrides[database.get_asm_db] = db_dep
            try:
                async def http():
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                                 base_url="http://cf", timeout=60) as cl:
                        r = await cl.post("/api/v1/ffa/lobby/%s/release" % lob.lid,
                                          json={"why": "fence_expired"},
                                          headers={"X-Mod-Version": "1.41.0"})
                    return r.status_code, r.json()
                a = await env._call(http)
                assert a.body[0] == 422, ("S66 iv no steam_id", a.body)
            finally:
                main.app.dependency_overrides.pop(database.get_asm_db, None)

            noop = main._check_steam_session
            env.mp.setattr(main, "_check_steam_session", _REAL_SESSION_CHECK)
            env.mp.setenv("STEAM_AUTH_ENFORCE", "1")
            env.mp.setenv("STEAM_WEB_API_KEY", "cf-lane")
            tok = main._current_mod_version.set("1.41.0")
            try:
                a = await env.release(lob, 2, "fence_expired")
                b = await env.leave(lob, 2)
            finally:
                main._current_mod_version.reset(tok)
                env.mp.setattr(main, "_check_steam_session", noop)
                env.mp.delenv("STEAM_AUTH_ENFORCE", raising=False)
                env.mp.delenv("STEAM_WEB_API_KEY", raising=False)
            assert a.status == 401 and (a.status, a.body) == (b.status, b.body), \
                ("S66 iv session", a, b)
            assert await env.snapshot() == before, "S66 iv no write"
        elif part == "v":
            old = await env.lobby(5, t=40.0)
            a = await _post(env, old, 0, [0, 1, 2, 3])
            assert a["status"] == "reformed", ("S66 v reform", a)
            new = (await env.lobby_row(old))["reformed_to"]
            lease, q = await env.lease(old, 1), await env.queue_row(old, 1)
            assert lease["group_id"] == new and q["series_id"] == new, ("S66 v carried", lease, q)
            a = await env.release(old, 1, "fence_expired")
            assert a.status == 200 and env.asm_lines("release slot=1 why=fence_expired lease=0 row=0"), \
                ("S66 v", a)
            assert await env.lease(old, 1) == lease and await env.queue_row(old, 1) == q, \
                "S66 v the held lobby's rows"
        else:
            lob = await _s64_lobby(env, t=40.0)
            upd = ("UPDATE ffa_assembly_seats SET released_at = CASE WHEN $3 THEN now() END,"
                   "  release_why = $4 WHERE lobby_id = $1 AND slot = $2")
            for at, why in ((True, None), (False, "fence_expired"), (True, "other")):
                with pytest.raises(_asyncpg.CheckViolationError):
                    await env.conn.execute(upd, lob.lid, 3, at, why)
            await env.conn.execute(upd, lob.lid, 3, True, "join_timeout")
            assert (await env.seat(lob, 3))["release_why"] == "join_timeout", "S66 CHECK twin"
    run_env(monkeypatch, body)


def test_n10_a_released_seat_never_reaches_the_gone_rule(monkeypatch):
    """Section 12, N10: R's FENCE_EXPIRED release, then two omission censuses,
    then the reports: no gone record, R's game-2 report accepted and R rated;
    a released seat's own census is no witness either. The control, the same
    censuses without the release, writes the record and refuses R's game-2
    report."""
    async def body(env):
        for case in ("released", "control"):
            lob = await _s64_lobby(env, t=40.0)
            s, res = lob.sids, _s64_res(lob)
            if case == "released":
                a = await env.release(lob, 6, "fence_expired")
                assert a.status == 200, ("N10 release", a)
            await env.at(lob, 60.0)
            await _omit(env, lob, [2], 6)
            c = await env.census_of(lob, 0, [0, 1, 2, 3, 4, 5])
            assert c.status == 200, ("N10 census", case, c)
            r = await env.report(lob, 1, res, reporter=s[0])
            assert r.status == 200, ("N10 game 1", case, r)
            if case == "released":
                assert await _gone(env, lob, 6) == (None, None), "N10 no record"
                await _settled(env, lob, 2, res, "N10 game 2", rated=True, reporter=s[6])
            else:
                assert await _gone(env, lob, 6) == (1, "witness"), "N10 control record"
                await _refused(env, lob, 2, 6, "left_reporter", res, "N10 control refused")
        lob = await _s64_lobby(env, t=40.0)
        a = await env.release(lob, 2, "fence_expired")
        assert a.status == 200, ("N10 witness release", a)
        await env.at(lob, 60.0)
        await _omit(env, lob, [2], 6)
        await env.census_of(lob, 0, [0, 1, 2, 3, 4, 5])
        assert await _gone(env, lob, 6) == (None, None), "N10 released witness"
    run_env(monkeypatch, body)


_N12_CLASSES = {
    "COPY": ("score_target", "card_candidates", "initial_picks", "card_cap", "same_card_rule",
             "is_ranked", "settings_known", "settings_changed_at", "password_hash",
             "kicked_steam_ids"),
    "COPY_AND": ("kills_tiebreak", "sudden_death"),
    "FRESH": ("id", "status", "photon_room_id", "region", "player_count", "member_ids",
              "created_at", "host_player_id", "reformed_from", "bets_disabled", "assembly_v1",
              "admission_v1", "region_why", "region_detail"),
    "RESET": ("games_played", "departed_ids", "departure_causes", "live_total_points",
              "live_points_game", "completed_at", "invalidated_at", "invalidation_reason",
              "reformed_to", "start_granted_at", "short_started_at", "asm_rule",
              "dissolve_path", "dissolve_trigger", "first_leaver", "first_leave_label",
              "dissolve_after_ms", "present_at_dissolve", "absent_at_dissolve",
              "arrived_at_dissolve"),
}


def test_n12_the_46_column_partition(monkeypatch):
    """Section 12, N12: the L' partition, class by class and column by column,
    is V11's table (COPY 10, COPY-AND 2, FRESH 14, RESET 20), disjoint, and
    its union is information_schema's ffa_lobbies."""
    async def body(env):
        classes = main._ASM_REFORM_CLASSES
        assert {k: set(v) for k, v in classes.items()} == \
            {k: set(v) for k, v in _N12_CLASSES.items()}, ("N12 classes", classes)
        assert {k: len(v) for k, v in classes.items()} == \
            {"COPY": 10, "COPY_AND": 2, "FRESH": 14, "RESET": 20}, "N12 counts"
        names = [c for v in classes.values() for c in v]
        cols = {r[0] for r in await env.conn.fetch(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'ffa_lobbies'")}
        assert len(names) == len(set(names)) == 46 and set(names) == cols, \
            ("N12 union", sorted(set(names) ^ cols))
    run_env(monkeypatch, body, fresh=True)


def test_n12_reform_keeps_the_ranked_flag(monkeypatch):
    """Section 12, N12: is_ranked is COPIED into L', never left to the schema's
    TRUE default: a casual lobby's re-form stays casual, a rated one's stays
    rated."""
    async def body(env):
        for ranked in (False, True):
            lob = await env.lobby(5, t=40.0, ranked=ranked)
            a = await _post(env, lob, 0, [0, 1, 2, 3])
            assert a["status"] == "reformed", ("N12 reform", ranked, a)
            new = await env.lobby_row((await env.lobby_row(lob))["reformed_to"])
            assert new["is_ranked"] is ranked, ("N12 is_ranked", ranked, new["is_ranked"])
    run_env(monkeypatch, body)


def test_n12_the_gated_leave_branch_order(monkeypatch):
    """Section 12, N12: an in-room cause takes the departure path first: a
    3-seat gated lobby's in-room leave at t = 8 appends the departure and
    keeps the lobby (left_path 'departure'); only a pre-room leave below
    three closes the lobby in its own transaction (left_path 'dissolve')."""
    async def body(env):
        lob = await env.lobby(3, t=8.0)
        a = await env.leave(lob, 2, cause="in_room_exit")
        row = await env.lobby_row(lob)
        assert a.status == 200 and row["status"] == "active" and \
            list(row["departed_ids"]) == [lob.pids[2]], \
            ("N12 in-room", row["status"], row["departed_ids"])
        assert (await env.seat(lob, 2))["left_path"] == "departure", "N12 in-room path"
        lob = await env.lobby(3, t=8.0)
        a = await env.leave(lob, 2, cause="")
        row = await env.lobby_row(lob)
        assert a.status == 200 and row["status"] == "canceled" and \
            row["dissolve_path"] == "leave_dissolve", ("N12 pre-room", row["status"])
        assert (await env.seat(lob, 2))["left_path"] == "dissolve", "N12 pre-room path"
    run_env(monkeypatch, body)


def test_the_census_fresh_literal_is_the_constant():
    """The closers' record fragment cannot name the Python constant, so its
    four literal intervals must equal ASM_CENSUS_FRESH_S."""
    found = _re.findall(r"census_at >= NOW\(\) - interval '(\d+) seconds'",
                        main._FFA_CLOSE_RECORD_SET)
    _write_facts({"found": found, "constant": main.ASM_CENSUS_FRESH_S})
    assert len(found) == 4 and all(int(x) == main.ASM_CENSUS_FRESH_S for x in found), \
        ("census literal", found)


def test_the_assembly_pool_and_its_connect_timeout():
    """database.make_asm_engine: pool 4 plus overflow 4 and a 3 s checkout
    timeout; and asyncpg's 2 s connect timeout, measured against a listener
    that accepts and never answers: the checkout fails in about 2 s, not in
    the driver's default 60."""
    import database

    async def go():
        eng = database.make_asm_engine("postgresql+asyncpg://cf@127.0.0.1:1/cf")
        try:
            args = [eng.pool.size(), eng.pool._max_overflow, eng.pool.timeout()]
            assert tuple(args) == (4, 4, 3), "pool arguments"
        finally:
            await eng.dispose()
        held = []

        async def hold(reader, writer):
            held.append(writer)
        srv = await asyncio.start_server(hold, "127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]
        eng = database.make_asm_engine("postgresql+asyncpg://cf@127.0.0.1:%d/cf" % port)
        t0 = _rt.monotonic()
        try:
            with pytest.raises(Exception):
                async with eng.connect():
                    pass
            dt = _rt.monotonic() - t0
            assert 1.5 <= dt < 3.0, ("connect timeout", dt)
        finally:
            await eng.dispose()
            for w in held:
                w.close()
            srv.close()
            await srv.wait_closed()
        # The twin comparison's trace (cf_controls.trace_file's name): the pool
        # arguments and the bound the timeout met, never the measured time.
        d = os.environ.get("CF_TRACE_DIR")
        if d:
            import json as _json
            import re as _tre
            node = os.environ.get("PYTEST_CURRENT_TEST", "case").split(" ")[0].rsplit("/", 1)[-1]
            path = os.path.join(d, _tre.sub(r"[^A-Za-z0-9_.-]", "_", node) + ".json")
            with open(path, "w", encoding="ascii", newline="\n") as fh:
                fh.write(_json.dumps({"pool": args, "connect_bound": [1.5, 3.0]},
                                     sort_keys=True, indent=1))
    _run(go())
