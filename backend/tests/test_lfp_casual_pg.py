"""LFP-CASUAL-1, review rounds 1 and 2: the proofs that need the real database.

  A1 one admission at a time per player (round 1 finding 2, round 2 F2):
     two sessions of one player; the first holds its transaction open after
     its insert; the second is identified WAITING on the admission lock by
     its own backend pid and the complete key (the class and that player's
     hash), blocked by the first session's pid; after the first commits, it
     answers cooldown; one row is stored. Four kind orders, each once alone
     and once with an unrelated waiter of the same class present (another
     player's key, held by a third session, waited on by a fourth).
  A2 one cooldown over both kinds, sequentially (round 1 finding 5).
  B1 the admission compares a FLOORED age (round 2 F1), for each kind: a row
     3599.5 s and 3599.999 s old is still in cooldown with one second left;
     a row 3600 s and 3600.25 s old is admitted.
  B2 the stats reader (get_player_stats' lfp_seconds_left) reads the same
     floored age: 1 at 3599.5 s and 3599.999 s, 0 at 3600 s and 3600.25 s.
  P1 the pending-pings route without the casual declaration (round 1
     finding 3) answers exactly what the route at BASE_COMMIT answers for the
     rows that do not name casual, and no row naming casual, even when older
     rows naming casual would fill its LIMIT;
  P2 with the declaration it answers every pending row, in created order, up
     to its LIMIT.

THE CLOCK OF B1 AND B2: each case plants its row with created_at = NOW() -
age and calls the route or the stats reader in the SAME transaction. NOW()
is the transaction's start time, fixed for the whole transaction, so the age
the reader computes is exactly the planted age: no time passes on that clock
between plant and read, and no margin can flake. Each case first reads the
age back in that transaction and, for an answer read in it, checks that the
transaction is still the planting one (txid_current); a case whose read
happened anywhere else FAILS with that reason.

The routes run lifted from main.py by text (test_lfp_casual.route_source:
the route's span plus the lane's helpers at the end of main.py) in main's
own namespace, with a stand-in for `app` so nothing registers twice, against
a schema built from the migration chain and the ORM (ladder_pg_harness). The
base route of P1 is the tracked fixture lfp_casual_base_spans.json (round 2
F8). The mutants are text edits of the same sources; each must turn its
proof red, at the red line its test names.

Without LADDER_TEST_PG_DSN (or without asyncpg) this file FAILS, never
skips, with one test that says which proofs did not run (lesson 1219).
"""

import asyncio
import decimal
import inspect
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

import main  # noqa: E402
from ban_sweep_pg_bounds import bounded_pg  # noqa: E402,F401  (autouse: every session bounded)
import ladder_pg_harness as harness  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402
import test_lfp_casual as T  # noqa: E402

KEY = "lfp-casual-pg-internal-key"
FILTER_LINE = ("           AND (CAST(:casual_ok AS boolean) OR NOT ('casual' = ANY(string_to_array(l.modes, ','))))\n")
FILTER_DROPPED = "           AND (CAST(:casual_ok AS boolean) OR TRUE)\n"
WAIT_SEEN_S = 5.0          # well inside the bounded sessions' 10 s lock_timeout
STATS_START = '@app.get("/api/v1/players/{steam_id}", response_model=PlayerStatsResponse'
STATS_END = '@app.get("/api/v1/players/{steam_id}/rating-history"'
_ids = itertools.count(1)

# The file's own reason when it cannot run (round 2 F3): ONE failing test, defined at the end, in place of
# every proof. Never a skip: a proof that measured nothing must be loud.
if not lh.DSN:
    MISSING = ("LADDER_TEST_PG_DSN is not set, so none of LFP-CASUAL-1's real-database proofs ran: the two-session "
               "admission (A1), the cross-kind cooldown (A2), the floored cooldown in the admission and the stats "
               "reader (B1, B2) and the pending-pings filter (P1, P2), nor their mutants. Set it to a PostgreSQL 16 "
               "database the run may build schemas in.")
elif lh._asyncpg is None:
    MISSING = ("asyncpg is not importable, so none of LFP-CASUAL-1's real-database proofs ran (A1, A2, B1, B2, "
               "P1, P2 and their mutants).")
else:
    MISSING = None


def _run(coro):
    return asyncio.run(coro)


def _sid():
    return "300000000000%05d" % next(_ids)


def _span(text_, start, end):
    text_ = text_.replace("\r\n", "\n")
    assert text_.count(start) == 1 and text_.count(end) == 1, "a span is not found once: " + start
    i = text_.index(start)
    return text_[i:text_.index(end, i)]


with open(T.MAIN, encoding="utf-8") as _fh:
    _MAIN_TEXT = _fh.read().replace("\r\n", "\n")
PENDING_SRC = T.pending_segment(_MAIN_TEXT) + "\n" + T._tail(_MAIN_TEXT)
STATS_SRC = _span(_MAIN_TEXT, STATS_START, STATS_END)


def base_pending_src():
    return T.base_span("internal_lfp_pings")


def lifted(src):
    """src run in a copy of main's namespace, with a stand-in app (the decorators register nothing)."""
    ns = dict(vars(main))
    ns["app"] = T._App()
    exec(compile(src, main.__file__, "exec"), ns)
    return ns


@pytest.fixture(scope="module")
def case():
    built = {}

    async def build():
        c = harness.CaseSchema(lh.DSN, "lfp_casual")
        await c.__aenter__()
        try:
            await lh._build(c)
        except BaseException:
            await c.__aexit__(None, None, None)
            raise
        built.update(schema=c.schema, own=c.own)
        await c.conn.close()
    _run(build())
    try:
        yield built["schema"]
    finally:
        async def drop():
            conn = await harness.connect_bound(lh.DSN, built["schema"])
            try:
                await harness.drop_case_schema(conn, built["schema"], built["own"])
            finally:
                await conn.close()
        _run(drop())


@pytest.fixture(autouse=True)
def soft_session(monkeypatch):
    """The session check in its soft mode (enforcement not armed), the internal key known."""
    monkeypatch.delenv("STEAM_AUTH_ENFORCE", raising=False)
    monkeypatch.setenv("API_SECRET_KEY", KEY)


def _with_sm(schema, body):
    async def go():
        engine = harness.bound_engine(lh.DSN, schema)
        try:
            return await body(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()
    return _run(go())


async def _player(sm, sid, ranked=True):
    async with sm() as db:
        await lh._insert(db, "players", {"steam_id": sid, "display_name": "P" + sid[-5:],
                                         "discord_id": "4%017d" % int(sid[-5:]), "ranked_enabled": ranked})
        await db.commit()


async def _rows(sm, sid):
    async with sm() as db:
        return [r[0] for r in (await db.execute(text(
            "SELECT modes FROM lfp_pings WHERE steam_id = :sid ORDER BY id"), {"sid": sid})).all()]


def _req(ns, sid, modes):
    return ns["LfpPingRequest"](steam_id=sid, message="", expires_minutes=60, modes=modes)


# -- A1: one admission at a time, the waiter identified -------------------------------------------

_KEY_WAITERS = """
    SELECT l.pid, a.wait_event_type, pg_blocking_pids(l.pid) AS blockers
      FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid
     WHERE l.locktype = 'advisory' AND NOT l.granted AND l.objsubid = 2
       AND l.classid = $1::oid
       AND l.objid::bigint = ((hashtext($2)::bigint + 4294967296) % 4294967296)
       AND l.database = (SELECT oid FROM pg_database WHERE datname = current_database())"""
_CLASS_WAITERS = """
    SELECT count(*) FROM pg_locks l
     WHERE l.locktype = 'advisory' AND NOT l.granted AND l.objsubid = 2 AND l.classid = $1::oid
       AND l.database = (SELECT oid FROM pg_database WHERE datname = current_database())"""


async def _unrelated_waiter(cls, observer):
    """Another player's key of the same class, held by one connection and waited on by another; returns
    them and the waiting task once the waiter is seen in pg_locks."""
    other = _sid()
    holder = await harness.connect_bound(lh.DSN, "public")
    waiter = await harness.connect_bound(lh.DSN, "public")
    await holder.execute("BEGIN")
    await holder.execute("SELECT pg_advisory_xact_lock($1::int, hashtext($2))", cls, other)
    await waiter.execute("BEGIN")
    task = asyncio.create_task(waiter.execute("SELECT pg_advisory_xact_lock($1::int, hashtext($2))", cls, other))
    for _ in range(100):
        if await observer.fetchval(_CLASS_WAITERS, cls) >= 1:
            return holder, waiter, task
        await asyncio.sleep(0.02)
    raise AssertionError("the unrelated waiter was never seen waiting: the case cannot run")


async def _two_sessions(sm, ns, sid, first, second, unrelated):
    """The first request's commit is held open (its insert done, its transaction and lock alive) until the
    second request has been seen waiting on the full key, or has finished, or WAIT_SEEN_S passed."""
    cls = ns["LFP_ADMISSION_LOCK_CLASS"]
    s1, s2 = sm(), sm()
    observer = await harness.connect_bound(lh.DSN, "public")
    holder = waiter = task = None
    decoys = 0
    try:
        if unrelated:
            holder, waiter, task = await _unrelated_waiter(cls, observer)
            decoys = await observer.fetchval(_CLASS_WAITERS, cls)
        pids, reached, release = {}, asyncio.Event(), asyncio.Event()
        real_commit = s1.commit

        async def held_commit():
            pids["first"] = (await s1.execute(text("SELECT pg_backend_pid()"))).scalar()
            reached.set()
            await release.wait()
            await real_commit()
        s1.commit = held_commit
        t1 = asyncio.create_task(ns["lfp_ping"](_req(ns, sid, first), None, s1))
        await asyncio.wait_for(reached.wait(), 20)
        t2 = asyncio.create_task(ns["lfp_ping"](_req(ns, sid, second), None, s2))
        seen, loop = [], asyncio.get_running_loop()
        deadline = loop.time() + WAIT_SEEN_S
        while not t2.done() and loop.time() < deadline:
            rows = await observer.fetch(_KEY_WAITERS, cls, sid)
            if rows:
                seen = [(r["pid"], list(r["blockers"]), r["wait_event_type"]) for r in rows]
                break
            await asyncio.sleep(0.05)
        second_done_early = t2.done()
        release.set()
        a1 = await asyncio.wait_for(t1, 20)
        a2 = await asyncio.wait_for(t2, 20)
        # the second session's pid, in its own transaction: still open after a cooldown answer
        pids["second"] = (await s2.execute(text("SELECT pg_backend_pid()"))).scalar()
    finally:
        try:
            if holder is not None:
                await holder.execute("ROLLBACK")
                if task is not None:
                    await asyncio.wait_for(task, 10)
                await waiter.execute("ROLLBACK")
        finally:
            for conn in (holder, waiter, observer):
                if conn is not None:
                    await conn.close()
            await s1.close()
            await s2.close()
    return dict(a1=a1, a2=a2, seen=seen, early=second_done_early, pids=pids, decoys=decoys,
                rows=await _rows(sm, sid))


ORDERS = (("1v1", "1v1"), ("1v1", "casual"), ("casual", "2v2"), ("ffa,casual", "casual"))
A1_CASES = [(f, s, u) for (f, s) in ORDERS for u in (False, True)]


def check_a1(schema, src, cases=A1_CASES):
    ns = lifted(src)
    out = []

    async def body(sm):
        for first, second, unrelated in cases:
            sid = _sid()
            await _player(sm, sid)
            out.append(((first, second, unrelated), await _two_sessions(sm, ns, sid, first, second, unrelated)))
    _with_sm(schema, body)
    for (first, second, unrelated), r in out:
        where = "%s then %s%s" % (first, second, ", with an unrelated waiter" if unrelated else "")
        # the stored rows first: without the lock the second request does not wait and stores a second row
        assert r["rows"] == [first], "rows stored: %d %r (%s)" % (len(r["rows"]), r["rows"], where)
        assert r["a1"] == T.QUEUED and r["a2"]["status"] == "cooldown" and \
            3590 <= r["a2"]["seconds_left"] <= 3600, (where, r["a1"], r["a2"])
        if unrelated:
            assert r["decoys"] >= 1, "the unrelated waiter was not in place (%s)" % where
        assert not r["early"] and r["seen"] == [(r["pids"]["second"], [r["pids"]["first"]], "Lock")], \
            "the second session (pid %s) was not seen waiting on the full key, blocked by the first (pid %s): " \
            "%r (%s)" % (r["pids"].get("second"), r["pids"].get("first"), r["seen"], where)
    return out


# -- A2: one cooldown over both kinds -------------------------------------------------------------

def check_a2(schema, src):
    ns = lifted(src)
    out = []

    async def body(sm):
        for first, second in (("1v1", "casual"), ("casual", "1v1"), ("2v2,casual", "ffa")):
            sid = _sid()
            await _player(sm, sid)
            answers = []
            for modes in (first, second):
                async with sm() as db:
                    answers.append(await ns["lfp_ping"](_req(ns, sid, modes), None, db))
            out.append((first, second, answers, await _rows(sm, sid)))
        # a player with ranked off: casual, then casual again
        sid = _sid()
        await _player(sm, sid, ranked=False)
        answers = []
        for modes in ("casual", "casual"):
            async with sm() as db:
                answers.append(await ns["lfp_ping"](_req(ns, sid, modes), None, db))
        out.append(("casual", "casual", answers, await _rows(sm, sid)))
    _with_sm(schema, body)
    for first, second, answers, rows in out:
        assert rows == [first], "rows stored: %d %r (%s then %s)" % (len(rows), rows, first, second)
        assert answers[0] == T.QUEUED and answers[1]["status"] == "cooldown", (first, second, answers)
    return out


# -- B1, B2: the floored age at the boundary ------------------------------------------------------

UNDER = ("3599.5", "3599.999")     # inside the half second where rounding (3600) and flooring (3599) differ
OVER = ("3600", "3600.25")         # the full hour and past it


async def _plant(db, sid, modes, age):
    """A row `age` seconds old by THIS transaction's clock; returns the transaction id after reading the
    age back exactly."""
    await db.execute(text(
        "INSERT INTO lfp_pings (steam_id, message, expires_minutes, expires_at, created_at, modes) "
        "VALUES (:sid, '', 60, NOW() + INTERVAL '1 hour', NOW() - make_interval(secs => CAST(:age AS numeric)), "
        ":modes)"), {"sid": sid, "age": age, "modes": modes})
    back = (await db.execute(text(
        "SELECT EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) FROM lfp_pings WHERE steam_id = :sid"),
        {"sid": sid})).scalar()
    assert decimal.Decimal(back) == decimal.Decimal(age), "the planted age reads %s, not %s" % (back, age)
    return (await db.execute(text("SELECT txid_current()"))).scalar()


async def _same_tx(db, txid, what):
    now = (await db.execute(text("SELECT txid_current()"))).scalar()
    assert now == txid, "%s was not read in the planting transaction (%s, then %s): the case proves nothing" % (
        what, txid, now)


def check_b1(schema, src):
    """The admission, for each kind, at ages under and over the hour, each planted and read in one
    transaction (its NOW() fixed): under -> cooldown with 1 s left; over -> queued."""
    ns = lifted(src)
    out = []

    async def body(sm):
        for kind, ranked in (("1v1", True), ("casual", False)):
            for age in UNDER + OVER:
                sid = _sid()
                await _player(sm, sid, ranked=ranked)
                async with sm() as db:
                    txid = await _plant(db, sid, kind, age)
                    answer = await ns["lfp_ping"](_req(ns, sid, kind), None, db)
                    if answer.get("status") == "cooldown":
                        await _same_tx(db, txid, "the cooldown answer")
                out.append((kind, age, answer, await _rows(sm, sid)))
    _with_sm(schema, body)
    for kind, age, answer, rows in out:
        if age in UNDER:
            assert answer == {"status": "cooldown", "seconds_left": 1}, \
                "admitted inside the hour: %s s, %s -> %r, rows %r" % (age, kind, answer, rows)
            assert rows == [], (kind, age, rows)      # the plant was rolled back with the answer's transaction
        else:
            assert answer == T.QUEUED and rows == [kind, kind], (kind, age, answer, rows)
    return out


def check_b2(schema, stats_src):
    """The stats reader in the planting transaction: lfp_seconds_left 1 under the hour, 0 at and past it."""
    ns = lifted(stats_src)
    out = []

    async def body(sm):
        for age in UNDER + OVER:
            sid = _sid()
            await _player(sm, sid)
            async with sm() as db:
                txid = await _plant(db, sid, "1v1", age)
                stats = await ns["get_player_stats"](steam_id=sid, viewer_steam_id=None, db=db)
                await _same_tx(db, txid, "the stats answer")
                out.append((age, stats.lfp_seconds_left))
                await db.rollback()
    _with_sm(schema, body)
    for age, left in out:
        want = 1 if age in UNDER else 0
        assert left == want, "lfp_seconds_left at %s s reads %r, not %r" % (age, left, want)
    return out


# -- the pending-pings route -----------------------------------------------------------------------

_T0 = "TIMESTAMPTZ '2026-11-22 00:00:00+00'"


async def _seed(db, specs):
    """Rows of lfp_pings by (modes, minute offset, pending?), created in that order of minutes."""
    for modes, minute, state in specs:
        await db.execute(text(
            "INSERT INTO lfp_pings (steam_id, message, expires_minutes, expires_at, created_at, modes, posted_at,"
            " undeliverable) VALUES (:sid, :msg, 60, NOW() + make_interval(mins => :exp), "
            + _T0 + " + make_interval(mins => :minute), :modes,"
            " CASE WHEN :state = 'posted' THEN NOW() END, :state = 'dead')"),
            {"sid": _sid(), "msg": "m%d" % minute, "exp": -5 if state == "expired" else 60, "minute": minute,
             "modes": modes, "state": state})


RANKED_ROWS = [(m, 100 + i, "pending") for i, m in enumerate(
    ["1v1", "2v2", "ffa", "1v1,ffa", "1v1,2v2,ffa", "2v2,ffa", "1v1", "ffa", "1v1,2v2", "2v2"])] + [
    ("1v1", 200, "posted"), ("ffa", 201, "expired"), ("2v2", 202, "dead")]
CASUAL_ROWS = [("casual" if i % 3 else "1v1,casual", i, "pending") for i in range(25)] + [
    ("casual", 300, "pending"), ("ffa,casual", 301, "pending"), ("casual", 302, "posted")]


async def _poll(ns, db, declare):
    """declare None is a poll without the parameter: the route at BASE_COMMIT has none; the route as it stands
    then gets its declared Query default, as FastAPI resolves it."""
    fn = ns["internal_lfp_pings"]
    params = inspect.signature(fn).parameters
    if declare is None:
        if "kinds" not in params:
            return await fn(x_internal_key=KEY, db=db)
        declare = params["kinds"].default.default
        assert declare == "", declare
    return await fn(x_internal_key=KEY, kinds=declare, db=db)


def check_p(schema, src):
    """P1 and P2 in one transaction that is rolled back: the table holds only these rows meanwhile."""
    new, old = lifted(src), lifted(base_pending_src())
    assert src != base_pending_src(), "the route at BASE_COMMIT is the route as it stands: nothing is compared"
    res = {}

    async def body(sm):
        async with sm() as db:
            await db.execute(text("DELETE FROM lfp_pings"))
            await _seed(db, RANKED_ROWS)
            res["base_ranked_only"] = await _poll(old, db, None)
            res["new_ranked_only"] = await _poll(new, db, None)
            await _seed(db, CASUAL_ROWS)
            res["base_all"] = await _poll(old, db, None)
            for word in ("", "lfp", "gambler", "casualx"):
                res["new_undeclared_" + word] = await _poll(new, db, word)
            res["new_absent"] = await _poll(new, db, None)
            for word in ("casual", "lfp,casual", " Casual "):
                res["new_declared_" + word] = await _poll(new, db, word)
            res["pending"] = [str(r[0]) for r in (await db.execute(text(
                "SELECT id FROM lfp_pings WHERE posted_at IS NULL AND NOT undeliverable AND expires_at > NOW()"
                " ORDER BY created_at ASC"))).all()]
            await db.rollback()
    _with_sm(schema, body)
    ranked_only = res["base_ranked_only"]
    assert len(ranked_only["pings"]) == 10, ranked_only
    # P1: undeclared answers are the base route's answer over the rows that do not name casual
    assert res["new_ranked_only"] == ranked_only
    for key in [k for k in res if k.startswith("new_undeclared_")] + ["new_absent"]:
        assert res[key] == ranked_only, (key, [p["modes"] for p in res[key]["pings"]])
        assert all("casual" not in p["modes"].split(",") for p in res[key]["pings"]), key
    # the older casual rows would have filled the base route's LIMIT: the filter is not a post-filter
    assert len(res["base_all"]["pings"]) == 20 and all(
        "casual" in p["modes"] for p in res["base_all"]["pings"]), "the seed no longer fills the LIMIT with casual"
    # P2: declared, every pending row in created order, up to the LIMIT of 20
    for word in ("casual", "lfp,casual", " Casual "):
        got = [p["ping_id"] for p in res["new_declared_" + word]["pings"]]
        assert got == res["pending"][:20], (word, got)
    assert len(res["pending"]) == 10 + 27
    return res


# -- the proofs and their mutants ------------------------------------------------------------------

def test_a1_one_admission_at_a_time(case):
    check_a1(case, T.ROUTE_SRC)


def test_a2_one_cooldown_over_both_kinds(case):
    check_a2(case, T.ROUTE_SRC)


def test_b1_the_admission_floors_the_age(case):
    check_b1(case, T.ROUTE_SRC)


def test_b2_the_stats_reader_floors_the_age(case):
    check_b2(case, STATS_SRC)


def test_p_pending_pings_by_declaration(case):
    check_p(case, PENDING_SRC)


def test_b_control_a_comment_only_edit_keeps_b1_and_b2_green(case):
    anchor = "async def _lfp_admit(db, steam_id):\n"
    check_b1(case, _mutated(T.ROUTE_SRC, anchor, "# control: a comment only\n" + anchor))
    anchor = "    # LFP-ping cooldown surface (July 21): seconds until this player may fire\n"
    check_b2(case, _mutated(STATS_SRC, anchor, "    # control: a comment only\n" + anchor))


def test_the_stats_reader_uses_the_route_cooldown():
    """The stats reader counts down from LFP_COOLDOWN_SECONDS, the gate's own constant, from a floored age."""
    assert "lfp_seconds_left = max(0, LFP_COOLDOWN_SECONDS - int(_lfp_elapsed))" in STATS_SRC
    assert STATS_SRC.count(T.STATS_FLOOR_OLD) == 1 and main.LFP_COOLDOWN_SECONDS == 3600


def _mutated(src, old, new):
    assert src.count(old) == 1, old
    return src.replace(old, new, 1)


def _red(check, *args):
    try:
        check(*args)
    except AssertionError as ex:
        return str(ex)
    raise AssertionError("the mutant left its proof green")


@pytest.mark.parametrize("first,second,unrelated", A1_CASES,
                         ids=["%s-then-%s%s" % (f, s, "-with-unrelated-waiter" if u else "") for f, s, u in A1_CASES])
def test_mutant_lock_removed_stores_two_rows_in_every_case(case, first, second, unrelated):
    red = _red(check_a1, case, _mutated(T.ROUTE_SRC, T.LOCK_MUTANT_OLD, ""), [(first, second, unrelated)])
    assert red.startswith("rows stored: 2 "), red


def test_mutant_cooldown_read_of_one_kind_stores_two_rows(case):
    red = _red(check_a2, case, _mutated(T.ROUTE_SRC, T.COOLDOWN_MUTANT_OLD, T.COOLDOWN_MUTANT_NEW))
    assert red.startswith("rows stored: 2 "), red


def test_mutant_admission_floor_removed(case):
    red = _red(check_b1, case, _mutated(T.ROUTE_SRC, T.FLOOR_MUTANT_OLD, T.FLOOR_MUTANT_NEW))
    assert red.startswith("admitted inside the hour: 3599.5 s"), red


def test_mutant_stats_floor_removed(case):
    red = _red(check_b2, case, _mutated(STATS_SRC, T.STATS_FLOOR_OLD, T.STATS_FLOOR_NEW))
    assert red.startswith("lfp_seconds_left at 3599.5 s reads 0, not 1"), red


def test_mutant_pending_filter_dropped(case):
    red = _red(check_p, case, _mutated(PENDING_SRC, FILTER_LINE, FILTER_DROPPED))
    assert red.startswith("('new_undeclared_"), red


def test_mutant_pending_declaration_ignored(case):
    red = _red(check_p, case, _mutated(PENDING_SRC, '{"casual_ok": _lfp_declares_casual(kinds)}',
                                       '{"casual_ok": False}'))
    assert red.startswith("('casual'"), red


if MISSING:
    # Without a database every proof above would measure nothing: they are removed, and one test fails in
    # their place with the reason (round 2 F3). Not a skip.
    for _name in [n for n in list(globals()) if n.startswith("test_")]:
        del globals()[_name]

    def test_lfp_casual_real_database_proofs_need_a_database():
        pytest.fail(MISSING, pytrace=False)
