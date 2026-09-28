"""The janitor self-test checks each statement by its CLASS (board row 26,
2026-09-28).

The boot self-test (main._run_janitor_query_selftest) prefixed EXPLAIN to
every statement the janitor roots reach. EXPLAIN plans only DML, so the
trading janitor's `SET LOCAL lock_timeout = '2s'` (_pc_trade_janitor_step)
answered "syntax error at or near SET" and the report read failed on a
janitor that runs correctly. Every harvested statement now carries a class
chosen by its first keyword (main._janitor_statement_class): DML is EXPLAINed
exactly as before, a session statement is EXECUTED in a transaction that is
rolled back, and anything else is "unclassified" and fails without reaching
the server (main._janitor_check_statement).

THE REPORT. Each statement gets a row in the report's `outcomes`
(explained, executed_rolled_back, failed, unclassified, timed_out,
unchecked) with its first 80 characters, whitespace folded, and the
function that issues it; `counts` keeps every older key and adds
executed_rolled_back and unclassified.

THE HEALTH WORD. /api/v1/health carries `janitor_selftest`, read from
the report the self-test recorded (main._janitor_selftest_marker): 1 it
ran and every statement passed, 0 it ran and did not pass (or a status
the map does not name), 2 skipped (the read replica), 3 not finished.

THE DATABASE. The live tests share ONE throwaway schema, built once per run
of this module in the database JANITOR_SELFTEST_TEST_PG_DSN names (which must
contain "janitor_selftest"), through ladder_pg_harness: every connection bound
to the schema at connect, a census before anything is created or dropped, and
the drop refused on any object the build did not leave. The schema is the
full one the janitor SQL plans against: the DDL of every numbered migration
replayed (test_title_ladder_hooks_live.py's replay, over every file, views
included), the ORM's create_all, the mapped tables widened to every column
the models map, the DDL replayed again -- and one sequence this file owns,
the probe that tells an EXPLAIN from an execution (EXPLAIN never advances a
sequence; executing nextval does, and a rollback does not undo it).

RUNNING IT
    JANITOR_SELFTEST_TEST_PG_DSN=postgresql://postgres@127.0.0.1:55432/janitor_selftest_lane \\
        python -m pytest backend/tests/test_janitor_selftest_classes.py -q

Without the DSN every database test FAILS by name rather than skipping;
JANITOR_SELFTEST_TEST_PG_OPTOUT=1 waives them deliberately (named skips). The
pure tests run either way. There is no pytest-asyncio here: each test is a
sync function that runs one coroutine.
"""
import ast
import asyncio
import contextlib
import glob
import inspect
import io
import os
import re
import sys
from types import SimpleNamespace

import pydantic
import pytest
from sqlalchemy import event, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import database  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402

try:
    import asyncpg as _asyncpg
except ImportError:                                    # pragma: no cover
    _asyncpg = None

DSN_VAR = "JANITOR_SELFTEST_TEST_PG_DSN"
OPTOUT_VAR = "JANITOR_SELFTEST_TEST_PG_OPTOUT"
DSN = (os.environ.get(DSN_VAR) or "").replace("postgresql+asyncpg://", "postgresql://")
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"

SQL_DIR = os.path.join(HERE, "..", "sql")
PROBE_SEQ = "janitor_selftest_probe_seq"
TRADE_STEP = "_pc_trade_janitor_step"


def _run(coro):
    return asyncio.run(coro)


def _require_pg():
    """Fail, not skip: a skipped live case reports exit 0 for coverage that
    did not run."""
    if DSN and _asyncpg is not None:
        name = DSN.rsplit("/", 1)[-1].split("?", 1)[0]
        if "janitor_selftest" not in name:
            pytest.fail("%s names the database %r. This file builds and drops a schema, "
                        "so it runs only against a lane database whose name contains "
                        "'janitor_selftest'." % (DSN_VAR, name))
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: the live janitor self-test coverage is "
                    "deliberately waived." % (DSN_VAR, OPTOUT_VAR))
    if _asyncpg is None:
        pytest.fail("asyncpg is not installed, so no statement was checked against a "
                    "server. Install it, or set %s=1 to waive deliberately." % OPTOUT_VAR)
    pytest.fail("%s is unset, so no janitor statement was EXPLAINed or executed against "
                "a server -- the subject of this file. Point it at a throwaway lane "
                "database, or set %s=1 to waive the coverage deliberately."
                % (DSN_VAR, OPTOUT_VAR))


def _planted(*sqls):
    """An inventory built by the real walker over a planted root that runs
    `sqls` in order, one text() site per line, so each entry is stamped by
    the same code that stamps the live inventory."""
    body = "\n".join("    await db.execute(text(%r))" % q for q in sqls)
    src = "from sqlalchemy import text\n\n\nasync def root(db):\n" + body + "\n"
    inv = main._janitor_sql_from_sources({"main": src}, (("main", "root"),))
    assert [s["sql"] for s in inv["statements"]] == list(sqls), inv["statements"]
    return inv


_LIVE = []


def _live_inventory():
    """main._janitor_sql_inventory(), harvested once per process: one walk of
    main.py costs seconds, and the tree must not move under a run anyway
    (conftest's tree-movement check). The runner under test still walks the
    files itself on every run."""
    if not _LIVE:
        _LIVE.append(main._janitor_sql_inventory())
    return _LIVE[0]


def _trade_session_statement():
    """The trading janitor's harvested session statement, from the LIVE
    inventory: the entry the production report showed as failed."""
    inv = _live_inventory()
    hits = [s for s in inv["statements"]
            if s["func"] == TRADE_STEP and s["class"] == "session"]
    assert len(hits) == 1, [(s["line"], s["class"], s["sql"]) for s in inv["statements"]
                            if s["func"] == TRADE_STEP]
    return hits[0]


# ---------------------------------------------------------------- pure tests

@pytest.mark.parametrize("sql, cls, word", [
    ("SELECT 1", "explain", "SELECT"),
    ("\n    select 1", "explain", "SELECT"),
    ("WITH x AS (SELECT 1) SELECT * FROM x", "explain", "WITH"),
    ("INSERT INTO t VALUES (1)", "explain", "INSERT"),
    ("UPDATE t SET a = 1", "explain", "UPDATE"),
    ("DELETE FROM t", "explain", "DELETE"),
    ("VALUES (1)", "explain", "VALUES"),
    ("MERGE INTO t USING s ON true WHEN MATCHED THEN DO NOTHING", "explain", "MERGE"),
    ("SET LOCAL lock_timeout = '2s'", "session", "SET"),
    ("RESET lock_timeout", "session", "RESET"),
    ("SHOW lock_timeout", "session", "SHOW"),
    ("BEGIN", "session", "BEGIN"),
    ("START TRANSACTION", "session", "START"),
    ("COMMIT", "session", "COMMIT"),
    ("END", "session", "END"),
    ("ROLLBACK TO SAVEPOINT s", "session", "ROLLBACK"),
    ("ABORT", "session", "ABORT"),
    ("SAVEPOINT s", "session", "SAVEPOINT"),
    ("RELEASE SAVEPOINT s", "session", "RELEASE"),
    ("-- why\n  SET x.y = 1", "session", "SET"),
    ("/* a /* nested */ comment */ SELECT 1", "explain", "SELECT"),
    ("/* never closed SELECT 1", "unclassified", ""),
    ("-- only a comment", "unclassified", ""),
    ("", "unclassified", ""),
    ("(SELECT 1)", "unclassified", ""),
    ("TABLE t", "unclassified", "TABLE"),
    ("LOCK TABLE t", "unclassified", "LOCK"),
    ("EXPLAIN SELECT 1", "unclassified", "EXPLAIN"),
    ("SELECTED 1", "unclassified", "SELECTED"),
    ("FROBNICATE janitor_selftest", "unclassified", "FROBNICATE"),
    ("\u00a0SELECT 1", "unclassified", ""),
])
def test_the_first_keyword_chooses_the_check(sql, cls, word):
    assert main._janitor_statement_class(sql) == (cls, word)


def test_the_walker_stamps_every_statement_with_its_class():
    inv = _planted("SET LOCAL lock_timeout = '2s'", "SELECT 1", "FROBNICATE janitor_selftest")
    assert [(s["class"], s["keyword"]) for s in inv["statements"]] == [
        ("session", "SET"), ("explain", "SELECT"), ("unclassified", "FROBNICATE")]


def test_the_live_inventory_classifies_every_statement():
    """A pytest property, like the walker's `dynamic == []`: a janitor that
    adopts a form the classes do not know reds HERE, before a boot banner."""
    inv = _live_inventory()
    classes = {}
    for s in inv["statements"]:
        assert (s["class"], s["keyword"]) == main._janitor_statement_class(s["sql"]), s
        classes.setdefault(s["class"], []).append(s)
    assert "unclassified" not in classes, [(s["module"], s["line"], s["sql"][:80])
                                           for s in classes["unclassified"]]
    assert all(s["keyword"] in main._JANITOR_SESSION_WORDS for s in classes.get("session", []))
    assert _trade_session_statement() in classes["session"]


class _ScriptedSession:
    """Stands in for an AsyncSession: records what reaches it, and can make
    its rollback raise."""

    def __init__(self, rollback_raises=False):
        self.sent = []
        self.rollbacks = 0
        self.rollback_raises = rollback_raises

    async def execute(self, stmt, params=None):
        self.sent.append(str(stmt))

    async def rollback(self):
        self.rollbacks += 1
        if self.rollback_raises:
            raise RuntimeError("connection lost")


def test_an_unclassified_statement_never_reaches_the_server():
    s = _planted("FROBNICATE janitor_selftest")["statements"][0]
    db = _ScriptedSession()
    verdict, detail = _run(main._janitor_check_statement(db, s))
    assert verdict == "unclassified"
    assert detail.startswith("unclassified statement (first keyword 'FROBNICATE')"), detail
    assert db.sent == [] and db.rollbacks == 0


def test_an_executed_statement_is_rolled_back_before_it_passes():
    """'executed_rolled_back' claims both halves: a rollback that raised
    makes the verdict 'failed'. An EXPLAIN's verdict never waited on its
    rollback and still does not."""
    session, dml = _planted("SET LOCAL lock_timeout = '2s'", "SELECT 1")["statements"]
    ok = _ScriptedSession()
    assert _run(main._janitor_check_statement(ok, session)) == ("executed_rolled_back", None)
    assert ok.sent == ["SET LOCAL statement_timeout = '5s'", "SET LOCAL lock_timeout = '2s'"]
    assert ok.rollbacks == 1
    broken = _ScriptedSession(rollback_raises=True)
    verdict, detail = _run(main._janitor_check_statement(broken, session))
    assert verdict == "failed", (verdict, detail)
    assert detail == ("executed, but the rollback that must undo it raised: "
                      "RuntimeError: connection lost")
    assert _run(main._janitor_check_statement(_ScriptedSession(rollback_raises=True),
                                              dml)) == ("explained", None)


class _InfraSession(_ScriptedSession):
    """A session whose server goes away when `fail_on` reaches it."""

    def __init__(self, fail_on):
        super().__init__()
        self.fail_on = fail_on

    async def execute(self, stmt, params=None):
        await super().execute(stmt, params)
        if str(stmt) == self.fail_on:
            raise ConnectionRefusedError("janitor_selftest: the server went away")


def test_a_statement_the_run_never_reached_reads_unchecked(monkeypatch):
    """The server goes away at the second statement: the run stops as
    db_unreachable, and the statements it never checked still get their
    rows, 'unchecked', as many as counts.unchecked says."""
    inv = _planted("SELECT 1", "SET LOCAL lock_timeout = '2s'", "SELECT 2")
    db = _InfraSession("SET LOCAL lock_timeout = '2s'")

    @contextlib.asynccontextmanager
    async def factory():
        yield db
    monkeypatch.setattr(database, "async_session", factory)
    monkeypatch.setattr(main, "_janitor_sql_inventory", lambda: inv)
    monkeypatch.setattr(main, "_janitor_selftest_report", {"status": "pending"})
    _run(main._run_janitor_query_selftest())
    report = main._janitor_selftest_report
    assert report["status"] == "db_unreachable", report
    assert "ConnectionRefusedError" in report["db_error"], report
    assert [o["outcome"] for o in report["outcomes"]] == [
        "explained", "unchecked", "unchecked"], report["outcomes"]
    assert report["counts"]["unchecked"] == 2, report["counts"]
    assert report["counts"]["explained_ok"] == 1, report["counts"]
    assert db.sent == ["SET LOCAL statement_timeout = '5s'", "EXPLAIN SELECT 1",
                       "SET LOCAL statement_timeout = '5s'",
                       "SET LOCAL lock_timeout = '2s'"], db.sent


class _DownSession:
    """A session whose server is gone: every statement raises."""

    async def execute(self, *a, **k):
        raise OSError("janitor_selftest: the database is down")

    async def rollback(self):
        pass


@pytest.mark.parametrize("status, word", [
    ("ok", 1), ("failed", 0), ("db_unreachable", 0), ("partial", 0), ("error", 0),
    ("skipped", 2), ("pending", 3), ("running", 3), ("frobnicated", 0), (None, 0),
])
def test_the_health_word_is_the_recorded_verdict(monkeypatch, status, word):
    """/health `janitor_selftest` for every status the self-test records --
    running, then ok / failed / db_unreachable / partial / error; pending
    before it starts; skipped on the read replica -- and for a status the map
    does not name, or none: 0, never a pass."""
    monkeypatch.setattr(main, "_janitor_selftest_report", {} if status is None else {"status": status})
    assert main._janitor_selftest_marker() == word


def test_both_health_arms_carry_the_word_and_the_schema_requires_it():
    """Both arms of health_check pass janitor_selftest=_janitor_selftest_marker()
    and nothing else in main.py passes the key; HealthResponse declares it an
    int with no default, so an arm that left it out would raise rather than
    drop the key. The standby's 2 rests on lifespan's replica branch recording
    the status "skipped"."""
    with open(main.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    (health,) = [n for n in ast.walk(tree)
                 if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    (tried,) = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    connected = [ast.unparse(k.value) for s in tried.body for k in ast.walk(s)
                 if isinstance(k, ast.keyword) and k.arg == "janitor_selftest"]
    degraded = [ast.unparse(k.value) for h in tried.handlers for k in ast.walk(h)
                if isinstance(k, ast.keyword) and k.arg == "janitor_selftest"]
    assert (connected, degraded) == (["_janitor_selftest_marker()"], ["_janitor_selftest_marker()"])
    everywhere = [k for k in ast.walk(tree) if isinstance(k, ast.keyword) and k.arg == "janitor_selftest"]
    assert len(everywhere) == 2, len(everywhere)
    field = schemas.HealthResponse.model_fields.get("janitor_selftest")
    assert field is not None and field.annotation is int and field.is_required(), field
    answer = _run(main.health_check(db=_DownSession())).model_dump()
    assert answer["status"] == "degraded" and "janitor_selftest" in answer, answer
    answer.pop("janitor_selftest")
    with pytest.raises(pydantic.ValidationError):
        schemas.HealthResponse(**answer)
    assert '"status": "skipped"' in inspect.getsource(main.lifespan)


# ------------------------------------------------------- the lane schema

_TOKEN = re.compile(
    r"(?P<line>--[^\n]*)"
    r"|(?P<block>/\*.*?\*/)"
    r"|(?P<str>'(?:[^']|'')*')"
    r"|(?P<ident>\"(?:[^\"]|\"\")*\")"
    r"|(?P<dq0>\$\$.*?\$\$)"
    r"|(?P<dq>\$(?P<tag>[A-Za-z_][A-Za-z0-9_]*)\$.*?\$(?P=tag)\$)"
    r"|(?P<semi>;)",
    re.S)


def _split_sql(sql):
    """Statements, split on the semicolons that end them (not inside a quoted
    string or identifier, a dollar-quoted body or a comment)."""
    out, buf, pos = [], [], 0
    for m in _TOKEN.finditer(sql):
        buf.append(sql[pos:m.start()])
        if m.group("line") is not None or m.group("block") is not None:
            buf.append(" ")
        elif m.group("semi") is not None:
            s = "".join(buf).strip()
            if s:
                out.append(s)
            buf = []
        else:
            buf.append(m.group(0))
        pos = m.end()
    buf.append(sql[pos:])
    s = "".join(buf).strip()
    if s:
        out.append(s)
    return out


_DDL_HEAD = re.compile(
    r"^(CREATE\s+(?:UNIQUE\s+)?INDEX|DROP\s+INDEX|CREATE\s+TABLE|ALTER\s+TABLE"
    r"|CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION|CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER"
    r"|DROP\s+TRIGGER|CREATE\s+TYPE|CREATE\s+SEQUENCE"
    r"|CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?VIEW)\b", re.I)
_DO_DDL = re.compile(r"\b(ALTER\s+TABLE|CREATE\s+(?:UNIQUE\s+)?INDEX|CREATE\s+TABLE"
                     r"|ADD\s+COLUMN)\b", re.I)
# Codes the second pass answers because the first pass or the ORM already made
# the object: duplicate table/relation, object, column, schema, function.
_ALREADY = {"42P07", "42710", "42701", "42P06", "42723"}


def _ddl_statements():
    out = []
    for path in sorted(glob.glob(os.path.join(SQL_DIR, "*.sql"))):
        name = os.path.basename(path)
        if not re.match(r"^\d{3}_", name):
            continue
        for s in _split_sql(io.open(path, encoding="utf-8").read()):
            head = s.lstrip()
            if re.search(r"\bpg_temp\.", s):
                continue
            if _DDL_HEAD.match(head) or (re.match(r"^DO\b", head, re.I) and _DO_DDL.search(head)):
                s = re.sub(r"\buuid_generate_v4\(\)", "gen_random_uuid()", s)
                s = re.sub(r"\s+CONCURRENTLY\b", "", s, flags=re.I)
                out.append((name, s))
    return out


async def _replay(conn, statements):
    failed = []
    for name, s in statements:
        try:
            await conn.execute(s)
        except _asyncpg.PostgresError as e:
            failed.append((name, e.sqlstate, str(e).split("\n")[0][:160]))
    return failed


async def _widen(conn, schema):
    """Every column a model maps, on its table: added nullable and
    default-free where the replayed DDL did not make it."""
    dialect = postgresql.dialect()
    added = []
    for table in models.Base.metadata.sorted_tables:
        have = {r["column_name"] for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            " WHERE table_schema = $1 AND table_name = $2", schema, table.name)}
        for col in table.columns:
            if col.name not in have:
                await conn.execute('ALTER TABLE %s."%s" ADD COLUMN "%s" %s' % (
                    harness.quoted(schema), table.name, col.name,
                    col.type.compile(dialect=dialect)))
                added.append("%s.%s" % (table.name, col.name))
    return added


async def _build(conn, schema):
    statements = _ddl_statements()
    first = await _replay(conn, statements)      # the ORM's tables are not there yet
    engine = harness.bound_engine(DSN, schema)
    try:
        async with engine.begin() as c:
            await c.run_sync(models.Base.metadata.create_all)
    finally:
        await engine.dispose()
    widened = await _widen(conn, schema)
    second = await _replay(conn, statements)
    await conn.execute("CREATE SEQUENCE %s.%s" % (harness.quoted(schema), PROBE_SEQ))
    return {"ddl": len(statements), "first_pass_failed": len(first), "widened": widened,
            "second_pass_failed": [f for f in second if f[1] not in _ALREADY]}


async def _create_and_build(schema):
    """ladder_pg_harness.CaseSchema's CREATE, build and seal, split from its
    DROP so one schema serves every test of this module."""
    conn = await harness.connect_bound(DSN, schema)
    created = False
    try:
        await harness.create_case_schema(conn, schema)
        created = True
        before = await harness.outside_objects(conn, schema)
        info = await _build(conn, schema)
        after = await harness.outside_objects(conn, schema)
        if after != before:
            changed = sorted(set(after) ^ set(before))
            raise harness.CensusRefusal("the build of %s changed %d object(s) outside it: %r"
                                        % (schema, len(changed), changed[:5]))
        return await harness.schema_objects(conn, schema), info
    except BaseException:
        if created:
            await harness.drop_case_schema(conn, schema, None)
        raise
    finally:
        await conn.close()


async def _drop(schema, own):
    conn = await harness.connect_bound(DSN, schema)
    try:
        await harness.drop_case_schema(conn, schema, own)
        assert not await conn.fetchval(harness.EXISTS_SQL, schema), schema
    finally:
        await conn.close()


@pytest.fixture(scope="module")
def lane():
    _require_pg()
    schema = harness.case_schema("janitor_selftest")
    own, info = _run(_create_and_build(schema))
    print("[janitor-selftest lane] schema %s: %d DDL statements, %d first-pass refusals, "
          "%d columns widened, second-pass refusals other than already-exists: %r"
          % (schema, info["ddl"], info["first_pass_failed"], len(info["widened"]),
             info["second_pass_failed"]))
    try:
        yield SimpleNamespace(schema=schema, own=own, info=info)
    finally:
        _run(_drop(schema, own))
        print("[janitor-selftest lane] schema %s dropped under the census" % schema)


def _engine(schema, pool_size=None):
    """An engine bound to the lane schema. pool_size=1 makes every checkout
    the SAME connection, which is what a session setting would follow."""
    kw = {"connect_args": {"server_settings": {"search_path": harness.quoted(schema)}}}
    if pool_size is None:
        return harness.bound_engine(DSN, schema)
    return create_async_engine(harness.async_dsn(DSN), pool_size=pool_size, max_overflow=0, **kw)


def _record(engine):
    """Every statement the engine sends and every rollback it makes, in order."""
    log = []

    def _sql(conn, cursor, statement, parameters, context, executemany):
        log.append(("sql", statement))

    def _rollback(conn):
        log.append(("rollback",))
    event.listen(engine.sync_engine, "before_cursor_execute", _sql)
    event.listen(engine.sync_engine, "rollback", _rollback)
    return log


async def _check_one(schema, s):
    engine = _engine(schema)
    try:
        async with engine.connect() as c:          # connect-time chatter stays out of the log
            await c.exec_driver_sql("SELECT 1")
        log = _record(engine)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            verdict = await main._janitor_check_statement(db, s)
        return verdict, log
    finally:
        await engine.dispose()


async def _selftest(monkeypatch, schema, inventory=None, pool_size=1):
    """Run the real self-test against the lane schema: the session factory it
    imports is the lane's, and the inventory is the live one unless planted.
    Returns (report, log of what the engine sent)."""
    engine = _engine(schema, pool_size=pool_size)
    try:
        async with engine.connect() as c:
            await c.exec_driver_sql("SELECT 1")
        log = _record(engine)
        monkeypatch.setattr(database, "async_session",
                            async_sessionmaker(engine, expire_on_commit=False))
        if inventory is not None:
            monkeypatch.setattr(main, "_janitor_sql_inventory", lambda: inventory)
        monkeypatch.setattr(main, "_janitor_selftest_report", {"status": "pending"})
        await main._run_janitor_query_selftest()
        return main._janitor_selftest_report, log
    finally:
        await engine.dispose()


# -------------------------------------------------------------- live tests

def test_pg_the_trading_janitors_set_local_is_executed_and_rolled_back(lane):
    s = _trade_session_statement()
    (verdict, detail), log = _run(_check_one(lane.schema, s))
    assert (verdict, detail) == ("executed_rolled_back", None)
    # sent VERBATIM, never behind EXPLAIN, and rolled back after
    assert log == [("sql", "SET LOCAL statement_timeout = '5s'"), ("sql", s["sql"]),
                   ("rollback",)], log


def test_pg_the_same_statement_with_a_bad_value_or_name_fails(lane):
    s = _trade_session_statement()
    assert s["sql"] == "SET LOCAL lock_timeout = '2s'", s["sql"]
    bad_value, bad_name = _planted("SET LOCAL lock_timeout = 'banana'",
                                   "SET LOCAL lock_timout = '2s'")["statements"]
    (verdict, detail), _log = _run(_check_one(lane.schema, bad_value))
    assert verdict == "failed" and detail.startswith("[22023]"), (verdict, detail)
    assert 'invalid value for parameter "lock_timeout": "banana"' in detail, detail
    (verdict, detail), _log = _run(_check_one(lane.schema, bad_name))
    assert verdict == "failed" and detail.startswith("[42704]"), (verdict, detail)


def test_pg_dml_is_still_explained_and_never_executed(lane):
    malformed, probe = _planted("SELECT id FROM WHERE status = 1",
                                "SELECT nextval('%s')" % PROBE_SEQ)["statements"]
    (verdict, detail), log = _run(_check_one(lane.schema, malformed))
    assert verdict == "failed" and detail.startswith("[42601]"), (verdict, detail)
    assert 'syntax error at or near "WHERE"' in detail, detail
    assert ("sql", "EXPLAIN " + malformed["sql"]) in log, log
    (verdict, detail), log = _run(_check_one(lane.schema, probe))
    assert (verdict, detail) == ("explained", None)
    assert ("sql", "EXPLAIN " + probe["sql"]) in log, log

    async def called():
        conn = await harness.connect_bound(DSN, lane.schema)
        try:
            return await conn.fetchval("SELECT is_called FROM %s" % PROBE_SEQ)
        finally:
            await conn.close()
    assert _run(called()) is False, "the EXPLAIN check EXECUTED a DML statement"
    # and the trading janitor's own DML still plans through the same path
    trade_dml = [s for s in _live_inventory()["statements"]
                 if s["func"] == TRADE_STEP and s["class"] == "explain"]
    assert len(trade_dml) == 4, [s["sql"][:60] for s in trade_dml]
    for s in trade_dml:
        assert _run(_check_one(lane.schema, s))[0] == ("explained", None), s["sql"][:80]


def test_pg_an_unclassified_statement_is_reported_and_fails(lane, monkeypatch):
    inv = _planted("SELECT 1", "FROBNICATE janitor_selftest")
    report, log = _run(_selftest(monkeypatch, lane.schema, inv))
    assert report["status"] == "failed", report
    assert report["counts"]["failed"] == 1 and report["counts"]["explained_ok"] == 1, report
    (failure,) = report["failures"]
    assert failure["error"].startswith(
        "unclassified statement (first keyword 'FROBNICATE')"), failure
    assert failure["sql"] == "FROBNICATE janitor_selftest"
    assert not any("FROBNICATE" in e[1] for e in log if e[0] == "sql"), log
    assert report["counts"]["unclassified"] == 1, report["counts"]
    assert [(o["outcome"], o["class"], o["keyword"]) for o in report["outcomes"]] == [
        ("explained", "explain", "SELECT"),
        ("unclassified", "unclassified", "FROBNICATE")], report["outcomes"]


PLANTED_LONG = ("\n        SELECT 'janitor_selftest' AS first_column,\n"
                "               'the report keeps the first eighty characters' "
                "AS second_column\n")


def test_pg_the_report_names_each_statements_outcome(lane, monkeypatch, capsys):
    """One statement of each outcome through the real runner: the report's
    rows, its counts (every older key kept, two added) and the banner."""
    inv = _planted(PLANTED_LONG, "SET LOCAL lock_timeout = '2s'",
                   "SET LOCAL lock_timeout = 'banana'", "FROBNICATE janitor_selftest")
    report, _log = _run(_selftest(monkeypatch, lane.schema, inv))
    assert report["status"] == "failed", report
    assert report["counts"] == {"statements": 4, "explained_ok": 1, "failed": 2,
                                "timed_out": 0, "dynamic": 0, "unchecked": 0,
                                "executed_rolled_back": 1,
                                "unclassified": 1}, report["counts"]
    rows = report["outcomes"]
    assert [(o["outcome"], o["class"], o["keyword"]) for o in rows] == [
        ("explained", "explain", "SELECT"),
        ("executed_rolled_back", "session", "SET"),
        ("failed", "session", "SET"),
        ("unclassified", "unclassified", "FROBNICATE")], rows
    assert [o["sql80"] for o in rows] == [
        "SELECT 'janitor_selftest' AS first_column, 'the report keeps the first eighty ch",
        "SET LOCAL lock_timeout = '2s'", "SET LOCAL lock_timeout = 'banana'",
        "FROBNICATE janitor_selftest"], rows
    assert all(o["func"] == "root" and o["roots"] == ["root"] for o in rows), rows
    assert [f["error"][:7] for f in report["failures"]] == ["[22023]", "unclass"], report
    banner = capsys.readouterr().out.splitlines()
    head = [ln for ln in banner if ln.startswith("[JANITOR-SELFTEST] EXPLAINed ")]
    assert len(head) == 1, banner
    assert head[0].startswith("[JANITOR-SELFTEST] EXPLAINed 1/1, executed and rolled "
                              "back 1/2, unclassified 1: 4 janitor statements in "), head
    assert head[0].endswith("s (2 failed, 0 timed out)"), head
    assert ("[JANITOR-SELFTEST]   executed and rolled back, not EXPLAINed: "
            "main.py:%d (root): SET LOCAL lock_timeout = '2s'" % rows[1]["line"]
            in banner), banner
    assert any("JANITOR QUERIES FAIL THEIR CHECK" in ln for ln in banner), banner


def test_pg_the_rollback_leaves_no_session_setting_behind(lane, monkeypatch):
    """Read on the SAME connection after the self-test: a session-level SET
    or RESET the check executed is gone, and the value the connection held
    before is back. The pool holds one connection, so every checkout -- the
    reads before and after, and every statement of the run -- is that one."""
    trade = _trade_session_statement()
    planted = _planted("RESET lock_timeout", "SET lock_timeout = '7s'",
                       "SET application_name = 'janitor_selftest_leak_probe'")
    inv = {**planted, "statements": [trade] + planted["statements"],
           "root_counts": {"root": 4}}

    async def go():
        engine = _engine(lane.schema, pool_size=1)
        seen = []
        event.listen(engine.sync_engine.pool, "checkout",
                     lambda dbapi_conn, rec, proxy: seen.append(id(dbapi_conn)))
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as db:
                await db.execute(text("SET lock_timeout = '9s'"))   # the connection's own value
                await db.commit()
                before = (await db.execute(text(
                    "SELECT pg_backend_pid(), current_setting('lock_timeout'), "
                    "current_setting('application_name')"))).one()
                await db.rollback()
            log = _record(engine)
            monkeypatch.setattr(database, "async_session", sm)
            monkeypatch.setattr(main, "_janitor_sql_inventory", lambda: inv)
            monkeypatch.setattr(main, "_janitor_selftest_report", {"status": "pending"})
            await main._run_janitor_query_selftest()
            async with sm() as db:
                after = (await db.execute(text(
                    "SELECT pg_backend_pid(), current_setting('lock_timeout'), "
                    "current_setting('application_name')"))).one()
                await db.rollback()
            return before, after, seen, log, main._janitor_selftest_report
        finally:
            await engine.dispose()
    before, after, seen, log, report = _run(go())
    assert report["status"] == "ok", report
    sent = [e[1] for e in log if e[0] == "sql"]
    for s in inv["statements"]:
        assert s["sql"] in sent, (s["sql"], sent)       # each one really ran
    assert len(set(seen)) == 1 and len(seen) >= 6, seen
    assert before[0] == after[0], (before, after)
    assert before[1] == "9s", before
    assert tuple(after) == tuple(before), (before, after)


def test_pg_transaction_words_run_without_breaking_the_run(lane, monkeypatch):
    """The class table's claims for the transaction words, executed: BEGIN,
    START and SAVEPOINT run inside the check's transaction, COMMIT, END,
    ROLLBACK and ABORT end it early -- and the run goes on unharmed -- while
    RELEASE and ROLLBACK TO name a savepoint no earlier statement made and
    report failed."""
    ok = _planted("COMMIT", "SELECT 1", "END", "ROLLBACK", "ABORT", "BEGIN",
                  "START TRANSACTION", "SAVEPOINT janitor_selftest_sp", "SELECT 1")
    report, _log = _run(_selftest(monkeypatch, lane.schema, ok))
    assert report["status"] == "ok" and report["db_error"] is None, report
    assert report["counts"]["explained_ok"] == 2 and report["counts"]["failed"] == 0, report
    loud = _planted("RELEASE SAVEPOINT janitor_selftest_sp",
                    "ROLLBACK TO SAVEPOINT janitor_selftest_sp")
    report, _log = _run(_selftest(monkeypatch, lane.schema, loud))
    assert report["status"] == "failed", report
    assert [f["error"][:7] for f in report["failures"]] == ["[3B001]", "[3B001]"], report


def test_pg_the_full_self_test_is_green_with_the_trading_schema(lane, monkeypatch):
    """The whole live inventory, checked by the real runner against the full
    lane schema with migration 353's trading objects in it. The process's
    trading-schema latch is clear going in (conftest), so nothing here rests
    on a cached "found"; the probe itself answers found afterwards."""
    assert main._PC_TRADE_SCHEMA_FOUND is False
    inv = _live_inventory()
    by_class = {}
    for s in inv["statements"]:
        by_class[s["class"]] = by_class.get(s["class"], 0) + 1

    async def present():
        conn = await harness.connect_bound(DSN, lane.schema)
        try:
            return [await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", t)
                    for t in ("pc_trades", "pc_trade_holds", "pc_trade_spent_nonces")]
        finally:
            await conn.close()
    assert _run(present()) == [True, True, True]
    report, _log = _run(_selftest(monkeypatch, lane.schema))
    print("[janitor-selftest] full run: %r" % ({k: report.get(k) for k in
                                                ("status", "counts", "root_counts")},))
    assert report["failures"] == [], report["failures"]
    assert report["timed_out"] == [] and report["db_error"] is None, report
    assert report["status"] == "ok", report
    counts = report["counts"]
    assert counts["statements"] == len(inv["statements"]), counts
    assert counts["explained_ok"] == by_class["explain"], (counts, by_class)
    assert counts["failed"] == 0 and counts["unchecked"] == 0, counts
    # Every older key keeps its meaning; the executed statement is counted
    # apart, and each statement has its row, in harvest order.
    assert counts["executed_rolled_back"] == by_class["session"] == 1, (counts, by_class)
    assert counts["unclassified"] == 0 and "unclassified" not in by_class, counts
    assert counts["explained_ok"] + counts["executed_rolled_back"] == counts["statements"]
    rows = report["outcomes"]
    assert [(o["module"], o["func"], o["line"]) for o in rows] == [
        (s["module"], s["func"], s["line"]) for s in inv["statements"]]
    assert {o["outcome"] for o in rows if o["class"] == "explain"} == {"explained"}
    (trade,) = [o for o in rows if o["outcome"] == "executed_rolled_back"]
    want = _trade_session_statement()
    assert (trade["func"], trade["line"], trade["class"], trade["keyword"]) == (
        TRADE_STEP, want["line"], "session", "SET"), trade
    assert trade["roots"] == want["roots"] and trade["roots"], trade
    assert trade["sql80"] == "SET LOCAL lock_timeout = '2s'", trade

    async def probe():
        engine = _engine(lane.schema)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                return await main._pc_trade_schema(db)
        finally:
            await engine.dispose()
    assert _run(probe()) == "found"


async def _health_payload(monkeypatch, schema, down=False):
    """GET /api/v1/health through the real handler and response model, as a
    worker serves it: the real get_db over the lane schema, or a session whose
    server is gone (the degraded arm)."""
    import httpx
    from fastapi import FastAPI
    assert main.get_db is database.get_db
    engine = _engine(schema)
    app = FastAPI()
    app.add_api_route("/api/v1/health", main.health_check, methods=["GET"],
                      response_model=schemas.HealthResponse)
    if down:
        async def gone():
            yield _DownSession()
        app.dependency_overrides[database.get_db] = gone
    monkeypatch.setattr(database, "async_session", async_sessionmaker(engine, expire_on_commit=False))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://janitor-selftest.test") as client:
            r = await asyncio.wait_for(client.get("/api/v1/health"), 60)
        assert r.status_code == 200, (r.status_code, r.text[:300])
        return r.json()
    finally:
        await engine.dispose()


def test_pg_the_health_word_reads_the_self_tests_verdict(lane, monkeypatch):
    """/api/v1/health `janitor_selftest` through the real handler and response
    model on the lane schema: the self-test run with its per-statement check
    forced to fail reads 0; the key is in the payload; the same run with the
    real check restored reads 1, on the degraded arm too (the word needs no
    database)."""
    inv = _live_inventory()
    real = main._janitor_check_statement

    async def forced(db, s):
        return "failed", "janitor_selftest health control: the check forced to fail"
    monkeypatch.setattr(main, "_janitor_check_statement", forced)
    report, _log = _run(_selftest(monkeypatch, lane.schema, inv))
    assert report["status"] == "failed", report["counts"]
    assert report["counts"]["failed"] == len(inv["statements"]), report["counts"]
    body = _run(_health_payload(monkeypatch, lane.schema))
    assert (body["status"], body.get("janitor_selftest", "absent")) == ("ok", 0), body
    monkeypatch.setattr(main, "_janitor_check_statement", real)
    report, _log = _run(_selftest(monkeypatch, lane.schema, inv))
    assert report["status"] == "ok", report["counts"]
    body = _run(_health_payload(monkeypatch, lane.schema))
    assert (body["status"], body.get("janitor_selftest", "absent")) == ("ok", 1), body
    down = _run(_health_payload(monkeypatch, lane.schema, down=True))
    assert (down["status"], down.get("janitor_selftest", "absent")) == ("degraded", 1), down
    print("[janitor-selftest] /health janitor_selftest: forced to fail 0, restored 1, degraded arm 1")
