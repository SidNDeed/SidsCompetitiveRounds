"""LFP-CASUAL-1, review round 1: the proofs that need the real database.

  A1 one admission at a time per player (finding 2): two sessions of one
     player; the first holds its transaction open after its insert, the
     second is observed WAITING on the admission lock (pg_locks, from a third
     connection), and once the first commits it answers cooldown; one row is
     stored. Ranked then ranked, ranked then casual, casual then ranked.
  A2 one cooldown over both kinds, sequentially, on the real cooldown read
     (finding 5): casual after ranked and ranked after casual answer cooldown.
  P1 the pending-pings route without the casual declaration (finding 3)
     answers exactly what the route at main's earlier commit (BASE_COMMIT)
     answers for the rows that do not name casual, and no row naming casual,
     even when older rows naming casual would fill its LIMIT;
  P2 with the declaration it answers every pending row, in created order, up
     to its LIMIT.

The routes run lifted from main.py by text (test_lfp_casual.route_source:
the route's span plus the lane's helpers at the end of main.py) in main's
own namespace, with a stand-in for `app` so nothing registers twice, against
a schema built from the migration chain and the ORM (ladder_pg_harness).
The mutants are text edits of the same source; each must turn its proof red.
Needs LADDER_TEST_PG_DSN; fails, never skips, without it.
"""

import asyncio
import inspect
import itertools
import os
import subprocess
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
PEND_START = '@app.get("/api/v1/internal/lfp-pings"'
PEND_END = "class _LfpPingAck(BaseModel):"
FILTER_LINE = ("           AND (CAST(:casual_ok AS boolean) OR NOT ('casual' = ANY(string_to_array(l.modes, ','))))\n")
FILTER_DROPPED = "           AND (CAST(:casual_ok AS boolean) OR TRUE)\n"
WAIT_SEEN_S = 5.0          # well inside the bounded sessions' 10 s lock_timeout
_ids = itertools.count(1)


def _run(coro):
    return asyncio.run(coro)


def _sid():
    return "300000000000%05d" % next(_ids)


def _pending_src(text_):
    text_ = text_.replace("\r\n", "\n")
    assert text_.count(PEND_START) == 1 and text_.count(PEND_END) == 1, "the pending-pings route is not found once"
    start = text_.index(PEND_START)
    return text_[start:text_.index(PEND_END, start)]


with open(T.MAIN, encoding="utf-8") as _fh:
    _MAIN_TEXT = _fh.read().replace("\r\n", "\n")
PENDING_SRC = _pending_src(_MAIN_TEXT) + "\n" + T._tail(_MAIN_TEXT)


def base_pending_src():
    out = subprocess.run(["git", "-C", T.REPO, "show", "%s:backend/api/main.py" % T.BASE_COMMIT],
                         capture_output=True, check=True, timeout=120)
    return _pending_src(out.stdout.decode("utf-8"))


def lifted(src):
    """src run in a copy of main's namespace, with a stand-in app (the decorators register nothing)."""
    ns = dict(vars(main))
    ns["app"] = T._App()
    exec(compile(src, main.__file__, "exec"), ns)
    return ns


@pytest.fixture(scope="module")
def case():
    lh._require_live_pg()
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


async def _two_sessions(sm, ns, sid, first, second):
    """The first request's commit is held open (its insert done, its transaction and lock alive) until the
    second request has been seen waiting, or has finished, or WAIT_SEEN_S passed. Returns both answers,
    whether the second was seen waiting on the admission lock, and the rows stored."""
    s1, s2 = sm(), sm()
    observer = await harness.connect_bound(lh.DSN, "public")
    try:
        reached, release = asyncio.Event(), asyncio.Event()
        real_commit = s1.commit

        async def held_commit():
            reached.set()
            await release.wait()
            await real_commit()
        s1.commit = held_commit
        t1 = asyncio.create_task(ns["lfp_ping"](_req(ns, sid, first), None, s1))
        await asyncio.wait_for(reached.wait(), 20)
        t2 = asyncio.create_task(ns["lfp_ping"](_req(ns, sid, second), None, s2))
        seen, loop = False, asyncio.get_running_loop()
        deadline = loop.time() + WAIT_SEEN_S
        while not t2.done() and loop.time() < deadline:
            row = await observer.fetchrow(
                "SELECT a.wait_event_type, l.granted FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                " WHERE l.locktype = 'advisory' AND l.classid = $1::oid AND l.objsubid = 2 AND NOT l.granted"
                "   AND l.database = (SELECT oid FROM pg_database WHERE datname = current_database())",
                ns["LFP_ADMISSION_LOCK_CLASS"])
            if row is not None and not row["granted"] and row["wait_event_type"] == "Lock":
                seen = True
                break
            await asyncio.sleep(0.05)
        second_done_early = t2.done()
        release.set()
        a1 = await asyncio.wait_for(t1, 20)
        a2 = await asyncio.wait_for(t2, 20)
    finally:
        await observer.close()
        await s1.close()
        await s2.close()
    return a1, a2, seen, second_done_early, await _rows(sm, sid)


def check_a1(schema, src):
    ns = lifted(src)
    out = []

    async def body(sm):
        for first, second in (("1v1", "1v1"), ("1v1", "casual"), ("casual", "2v2"), ("ffa,casual", "casual")):
            sid = _sid()
            await _player(sm, sid)
            out.append((first, second) + await _two_sessions(sm, ns, sid, first, second))
    _with_sm(schema, body)
    for first, second, a1, a2, seen, early, rows in out:
        # the stored rows first: without the lock the second request does not wait and stores a second row
        assert rows == [first], "rows stored: %d %r (%s then %s)" % (len(rows), rows, first, second)
        assert a1 == T.QUEUED and a2["status"] == "cooldown" and 3590 <= a2["seconds_left"] <= 3600, (a1, a2)
        assert seen and not early, "the second request was not seen waiting on the admission lock (%s then %s)" % (
            first, second)
    return out


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


def test_p_pending_pings_by_declaration(case):
    check_p(case, PENDING_SRC)


def _mutated(src, old, new):
    assert src.count(old) == 1, old
    return src.replace(old, new, 1)


def _red(check, *args):
    try:
        check(*args)
    except AssertionError as ex:
        return str(ex)
    raise AssertionError("the mutant left its proof green")


def test_mutant_lock_removed_stores_two_rows(case):
    red = _red(check_a1, case, _mutated(T.ROUTE_SRC, T.LOCK_MUTANT_OLD, ""))
    assert red.startswith("rows stored: 2 "), red


def test_mutant_cooldown_read_of_one_kind_stores_two_rows(case):
    red = _red(check_a2, case, _mutated(T.ROUTE_SRC, T.COOLDOWN_MUTANT_OLD, T.COOLDOWN_MUTANT_NEW))
    assert red.startswith("rows stored: 2 "), red


def test_mutant_pending_filter_dropped(case):
    red = _red(check_p, case, _mutated(PENDING_SRC, FILTER_LINE, FILTER_DROPPED))
    assert red.startswith("('new_undeclared_"), red


def test_mutant_pending_declaration_ignored(case):
    red = _red(check_p, case, _mutated(PENDING_SRC, '{"casual_ok": _lfp_declares_casual(kinds)}',
                                       '{"casual_ok": False}'))
    assert red.startswith("('casual'"), red
