"""The /health word that says this box's database carries migration 356.

The 2v2 disconnect-deferral batch makes a survivor's fallback report DEFER
instead of settling: team_series_report_dc stamps two columns that migration
356 adds, the sweep settles the row later, and the read-only status route
reports the deferral. Every one of those statements names the two columns, so
a box whose database lacks them fails on each. `team_dc_fallback` is the
release train's word for that: 1 when a probe naming every such column runs on
the answering box's database, 0 when it fails because a column or the table is
missing. It is absent on any build before the batch, which is how the train
reads the old build.

Unlike the code-constant siblings this word asks the DATABASE, so what is
proven here is different in kind:

  * the probe's columns are DERIVED from the four functions' compiled SQL,
    and they are exactly the columns the migration adds; an AST census over
    the whole of main.py holds the four to being every function whose SQL
    names such a column;
  * the classification is narrow: an undefined column or table reads 0, and
    anything else -- a connection lost mid-probe above all -- is left to
    health_check's own catch, which reports the box degraded as before;
  * a failed probe rolls its transaction back, so the session answers its
    next statement, and a second request on a one-connection pool answers;
  * both arms carry the key -- the connected arm from the probe, the degraded
    arm from the cache the probe writes;
  * against live PostgreSQL (SEPT16DC_TEST_PG_DSN), in scratch schemas this
    file creates and drops and nothing else: both columns present reads 1,
    either one absent reads 0, both absent reads 0, no table reads 0, an
    unrelated schema change reads 1 -- and every case answers status "ok".

The last test runs the controls on a COPY of main.py, in both directions:
each defect reddens exactly the tests that should see it, and a comment-only
twin reddens nothing. The copy keeps the controls off the tree a running
suite is reading (conftest.py's tree-movement check says why that matters).
"""
import ast
import asyncio
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import uuid

import pydantic
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import asyncpg.exceptions as apg_exc                               # noqa: E402
from sqlalchemy import text                                        # noqa: E402
from sqlalchemy.exc import ProgrammingError                        # noqa: E402

import main                                                        # noqa: E402
import schemas                                                     # noqa: E402

MAIN_PY = pathlib.Path(main.__file__).resolve()
BACKEND = MAIN_PY.parent.parent
MIGRATION = BACKEND / "sql" / "356_team_series_dc_fallback_at.sql"
LIVE_DSN = "SEPT16DC_TEST_PG_DSN"
DSN = os.environ.get(LIVE_DSN)
needs_pg = pytest.mark.skipif(
    not DSN, reason="%s unset; live-PostgreSQL half of the team_dc_fallback marker" % LIVE_DSN)

# The four functions whose SQL the probe's columns are derived from, in the
# order the binding names them.
DERIVING = ("_team_clear_dc_fallback_marker", "_team_dc_fallback_sweep_once",
            "team_series_status_readonly", "team_series_report_dc")
PROBE = "SELECT dc_fallback_at, dc_fallback_player_id FROM team_series LIMIT 0"

# This file's OWN reading of "a statement" and "a column name", deliberately
# not main's objects: a control that edits main's patterns must not be able to
# edit the census that judges them.
_STATEMENT = re.compile(r"^\s*(?:SELECT|UPDATE|INSERT|WITH|DELETE)\b")
_NAME = re.compile(r"\bdc_fallback_[a-z_]+\b")
_TREE = []


def _run(coro):
    return asyncio.run(coro)


def _tree():
    if not _TREE:
        _TREE.append(ast.parse(MAIN_PY.read_text(encoding="utf-8")))
    return _TREE[0]


def _def(tree, name):
    hits = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == name]
    assert len(hits) == 1, (name, len(hits))
    return hits[0]


def _binding(tree, name):
    hits = [n for n in tree.body if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
    assert len(hits) == 1, (name, len(hits))
    return hits[0]


@pytest.fixture(autouse=True)
def _cache_restored(monkeypatch):
    """Every test here may run the probe, which writes main's cache; the
    value the suite had before comes back afterwards."""
    monkeypatch.setattr(main, "_TEAM_DC_FALLBACK_LAST", main._TEAM_DC_FALLBACK_LAST)
    monkeypatch.setattr(main, "_DISCORD_FIX_LAST", main._DISCORD_FIX_LAST)
    yield


# The discord_fix marker's probe (main._discord_fix_probe) is a bare execute
# on the same session, sent after this marker's probe, so on the connected
# arm this fake records it too; the exact lists below name it rather than
# filter it. Its cache is restored by the fixture above.
SIBLING = main._DISCORD_FIX_PROBE


# -- sessions that stand in for the database -----------------------------------

class _Session:
    """Every statement runs, unless it is the probe and `probe_raises` is set."""

    def __init__(self, probe_raises=None):
        self.sent, self.rollbacks, self.probe_raises = [], 0, probe_raises

    async def execute(self, stmt, *a, **k):
        self.sent.append(str(stmt))
        if self.probe_raises is not None and str(stmt) == main._TEAM_DC_FALLBACK_PROBE:
            raise self.probe_raises
        return None

    async def rollback(self):
        self.rollbacks += 1


class _Down:
    """A session whose first statement fails, as an unreachable database's does."""

    async def execute(self, *a, **k):
        raise OSError("database unreachable")

    async def rollback(self):
        raise AssertionError("nothing may roll back a session that never answered")


def _sa_wrapped(driver_exc):
    """`driver_exc` the way SQLAlchemy raises it over asyncpg: a DBAPIError
    whose .orig is the dialect's adapted error carrying the SQLSTATE, raised
    from the driver's own exception. The live test below reads the real
    chain; this one lets a fake session raise it."""
    adapted = Exception("%s: %s" % (type(driver_exc).__name__, driver_exc))
    adapted.sqlstate = adapted.pgcode = driver_exc.sqlstate
    adapted.__cause__ = driver_exc
    err = ProgrammingError(PROBE, {}, adapted)
    err.__cause__ = adapted
    return err


def _only_context():
    """An error raised WHILE a missing-column error was being handled: the
    missing column is on __context__ only, so it is not what went wrong."""
    try:
        try:
            raise apg_exc.UndefinedColumnError('column "dc_fallback_at" does not exist')
        except apg_exc.UndefinedColumnError:
            raise RuntimeError("the handler itself failed")
    except RuntimeError as exc:
        return exc


# -- the derivation --------------------------------------------------------------

def test_the_probe_is_derived_from_the_four_functions_and_names_the_migrations_columns():
    """Derived, bound once, over exactly the four functions, and equal to the
    migration's own ADD COLUMN list at this tip.

    The column binding has to be a CALL of the deriving helper over the four
    functions by name, with no literal anywhere in it: a written-down tuple
    would still read 1 on a box whose code had moved to other columns."""
    tree = _tree()
    call = _binding(tree, "_TEAM_DC_FALLBACK_COLUMNS").value
    assert isinstance(call, ast.Call), ast.dump(call)
    assert ast.unparse(call.func) == "_team_dc_fallback_columns", ast.unparse(call)
    assert [ast.unparse(a) for a in call.args] == list(DERIVING), ast.unparse(call)
    assert not call.keywords and not [n for n in ast.walk(call) if isinstance(n, ast.Constant)]
    for name in ("_TEAM_DC_FALLBACK_COLUMNS", "_TEAM_DC_FALLBACK_PROBE"):
        stores = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == name
                  and isinstance(n.ctx, ast.Store)]
        assert len(stores) == 1, (name, len(stores))

    added = tuple(sorted(re.findall(r"ADD COLUMN IF NOT EXISTS (\w+)",
                                    MIGRATION.read_text(encoding="utf-8"))))
    assert added == ("dc_fallback_at", "dc_fallback_player_id"), added
    assert main._TEAM_DC_FALLBACK_COLUMNS == added, main._TEAM_DC_FALLBACK_COLUMNS
    assert main._TEAM_DC_FALLBACK_PROBE == PROBE, main._TEAM_DC_FALLBACK_PROBE


def test_every_statement_naming_a_dc_fallback_column_belongs_to_the_four_functions():
    """The census the derivation's completeness rests on, read from the AST
    of the WHOLE file with this file's own patterns: every string literal
    that opens with an upper-case SQL verb and names a dc_fallback_* column,
    docstrings excluded, grouped by the top-level def (or class, or the
    module) that holds it. The owners must be exactly the four, and the names
    exactly the derived columns -- a fifth function whose SQL named a column,
    or a column the probe did not ask for, reddens this."""
    tree = _tree()
    owners = {}
    for top in tree.body:
        docs = {id(n.body[0].value) for n in ast.walk(top)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and n.body and isinstance(n.body[0], ast.Expr)
                and isinstance(n.body[0].value, ast.Constant)
                and isinstance(n.body[0].value.value, str)}
        for n in ast.walk(top):
            if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n) not in docs and _STATEMENT.match(n.value)):
                names = set(_NAME.findall(n.value))
                if names:
                    owners.setdefault(getattr(top, "name", "<module>"), set()).update(names)
    assert set(owners) == set(DERIVING), sorted(owners)
    assert set().union(*owners.values()) == set(main._TEAM_DC_FALLBACK_COLUMNS), owners


_DECOY = '''
def decoy(db):
    """UPDATE team_series SET dc_fallback_docstring = NULL"""
    key = "dc_fallback_key"
    note = "update team_series set dc_fallback_lowercase = null"
    sql = "UPDATE team_series SET dc_fallback_real = NULL"   # dc_fallback_comment
    def inner():
        return "  SELECT dc_fallback_nested FROM team_series"
    return {"dc_fallback_response": True}, key, note, sql, inner
'''


def test_the_derivation_reads_statements_and_nothing_else():
    """The helper over a function whose answer is known: the statement and
    the nested statement count; the docstring (which opens with a verb), a
    lower-case string, a bare key, a response key and a comment do not."""
    namespace = {}
    exec(compile(_DECOY, "<team_dc_fallback decoy>", "exec"), namespace)
    got = main._team_dc_fallback_columns(namespace["decoy"])
    assert got == ("dc_fallback_nested", "dc_fallback_real"), got


# -- the classification ------------------------------------------------------------

_CLASSIFIED = {
    "driver-column": (lambda: apg_exc.UndefinedColumnError('column "x" does not exist'), True),
    "driver-table": (lambda: apg_exc.UndefinedTableError('relation "team_series" does not exist'), True),
    "wrapped-column": (lambda: _sa_wrapped(apg_exc.UndefinedColumnError('column "x" does not exist')), True),
    "wrapped-table": (lambda: _sa_wrapped(apg_exc.UndefinedTableError('relation "t" does not exist')), True),
    "state-only-on-orig": (lambda: ProgrammingError(PROBE, {}, type("E", (Exception,), {"sqlstate": "42703"})()),
                           True),
    "oserror": (lambda: OSError("connection reset by peer"), False),
    "wrapped-privilege": (lambda: _sa_wrapped(apg_exc.InsufficientPrivilegeError("permission denied")), False),
    "wrapped-admin-shutdown": (lambda: _sa_wrapped(apg_exc.AdminShutdownError("terminating connection")), False),
    "wrapped-statement-timeout": (lambda: _sa_wrapped(apg_exc.QueryCanceledError("canceling statement")), False),
    "context-only": (_only_context, False),
}


@pytest.mark.parametrize("case", list(_CLASSIFIED), ids=list(_CLASSIFIED))
def test_the_classifier_reads_the_wrapping_chain(case):
    build, want = _CLASSIFIED[case]
    assert main._team_dc_fallback_schema_missing(build()) is want, case


# -- the two arms, with sessions that stand in for the database --------------------

def test_the_connected_arm_probes_after_select_1_and_answers_1(monkeypatch):
    monkeypatch.setattr(main, "_TEAM_DC_FALLBACK_LAST", 0)
    db = _Session()
    answer = _run(main.health_check(db=db)).model_dump()
    assert (answer["status"], answer["database"], answer["team_dc_fallback"]) == ("ok", "connected", 1)
    assert db.sent == ["SELECT 1", PROBE, SIBLING], db.sent
    assert db.rollbacks == 0 and main._TEAM_DC_FALLBACK_LAST == 1


@pytest.mark.parametrize("kind", ["column", "table"])
def test_a_missing_column_or_table_reads_0_and_the_box_stays_ok(monkeypatch, kind):
    monkeypatch.setattr(main, "_TEAM_DC_FALLBACK_LAST", 1)
    driver = (apg_exc.UndefinedColumnError('column "dc_fallback_at" does not exist') if kind == "column"
              else apg_exc.UndefinedTableError('relation "team_series" does not exist'))
    db = _Session(probe_raises=_sa_wrapped(driver))
    answer = _run(main.health_check(db=db)).model_dump()
    assert (answer["status"], answer["database"], answer["team_dc_fallback"]) == ("ok", "connected", 0)
    assert db.sent == ["SELECT 1", PROBE, SIBLING], db.sent
    assert db.rollbacks == 1 and main._TEAM_DC_FALLBACK_LAST == 0


_OTHER = {
    "connection-lost": lambda: OSError("connection reset by peer"),
    "privilege": lambda: _sa_wrapped(apg_exc.InsufficientPrivilegeError("permission denied for table team_series")),
    "admin-shutdown": lambda: _sa_wrapped(apg_exc.AdminShutdownError("terminating connection")),
    "statement-timeout": lambda: _sa_wrapped(apg_exc.QueryCanceledError("canceling statement due to timeout")),
}


@pytest.mark.parametrize("kind", list(_OTHER))
def test_any_other_probe_error_is_left_to_the_outer_catch(monkeypatch, kind):
    """Degraded exactly as before this word existed, the cache untouched by
    the failed probe, nothing rolled back by the probe."""
    monkeypatch.setattr(main, "_TEAM_DC_FALLBACK_LAST", 1)
    db = _Session(probe_raises=_OTHER[kind]())
    answer = _run(main.health_check(db=db)).model_dump()
    assert (answer["status"], answer["database"]) == ("degraded", "disconnected"), answer
    assert answer["team_dc_fallback"] == 1 and main._TEAM_DC_FALLBACK_LAST == 1
    assert db.rollbacks == 0


def test_the_degraded_arm_answers_the_cache_the_probe_writes(monkeypatch):
    monkeypatch.setattr(main, "_TEAM_DC_FALLBACK_LAST", 0)
    missing = _sa_wrapped(apg_exc.UndefinedColumnError('column "dc_fallback_at" does not exist'))
    steps = []
    for db in (_Down(), _Session(), _Down(), _Session(probe_raises=missing), _Down()):
        answer = _run(main.health_check(db=db)).model_dump()
        steps.append((answer["status"], answer["team_dc_fallback"]))
    assert steps == [("degraded", 0), ("ok", 1), ("degraded", 1), ("ok", 0), ("degraded", 0)], steps


def test_both_arms_carry_the_key_and_only_the_probe_writes_the_cache():
    tree = _tree()
    health = _def(tree, "health_check")
    tries = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    assert len(tries) == 1, len(tries)
    body = tries[0].body
    assert ast.unparse(body[0]) == "await db.execute(text('SELECT 1'))", ast.unparse(body[0])
    probe = body[1]
    assert isinstance(probe, ast.Assign) and len(probe.targets) == 1, ast.unparse(probe)
    assert ast.unparse(probe.value) == "await _team_dc_fallback_probe(db)", ast.unparse(probe)
    bound = probe.targets[0].id

    ok = [k for stmt in body for k in ast.walk(stmt)
          if isinstance(k, ast.keyword) and k.arg == "team_dc_fallback"]
    degraded = [k for h in tries[0].handlers for k in ast.walk(h)
                if isinstance(k, ast.keyword) and k.arg == "team_dc_fallback"]
    assert [ast.unparse(k.value) for k in ok] == [bound]
    assert [ast.unparse(k.value) for k in degraded] == ["_TEAM_DC_FALLBACK_LAST"]
    everywhere = [k for k in ast.walk(tree) if isinstance(k, ast.keyword) and k.arg == "team_dc_fallback"]
    assert len(everywhere) == 2, len(everywhere)

    calls = [c for c in ast.walk(tree) if isinstance(c, ast.Call)
             and isinstance(c.func, ast.Name) and c.func.id == "_team_dc_fallback_probe"]
    assert len(calls) == 1 and calls[0] in list(ast.walk(health)), len(calls)

    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
              and n.id == "_TEAM_DC_FALLBACK_LAST" and isinstance(n.ctx, ast.Store)]
    in_probe = [n for n in ast.walk(_def(tree, "_team_dc_fallback_probe"))
                if isinstance(n, ast.Name) and n.id == "_TEAM_DC_FALLBACK_LAST"
                and isinstance(n.ctx, ast.Store)]
    module_level = _binding(tree, "_TEAM_DC_FALLBACK_LAST")
    assert len(in_probe) == 3 and len(stores) == 4, (len(in_probe), len(stores))
    assert ast.unparse(module_level.value) == "0"


def test_the_schema_declares_the_word_required_after_ladder_hook():
    fields = list(schemas.HealthResponse.model_fields)
    field = schemas.HealthResponse.model_fields["team_dc_fallback"]
    assert field.annotation is int and field.is_required()
    assert fields.index("team_dc_fallback") == fields.index("ladder_hook") + 1, fields
    answer = _run(main.health_check(db=_Session())).model_dump()
    answer.pop("team_dc_fallback")
    with pytest.raises(pydantic.ValidationError):
        schemas.HealthResponse(**answer)


# -- live PostgreSQL: scratch schemas this file creates and drops --------------------

# A team_series with the columns the pre-356 row carries that the cases touch.
# The real migration is then run on it from disk, verbatim.
PRE_356_TEAM_SERIES = """
CREATE TABLE team_series (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active',
    t1_color_hex TEXT,
    t2_color_hex TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""
_CREATED = set()

# case: (create the table, run migration 356, then these, marker wanted,
#        the SQLSTATE the probe itself raises there)
CASES = {
    "both-present": (True, True, (), 1, None),
    "at-absent": (True, True, ("ALTER TABLE team_series DROP COLUMN dc_fallback_at",), 0, "42703"),
    "player-id-absent": (True, True, ("ALTER TABLE team_series DROP COLUMN dc_fallback_player_id",),
                         0, "42703"),
    "both-absent": (True, False, (), 0, "42703"),
    "no-table": (False, False, (), 0, "42P01"),
    "unrelated-change": (True, True, ("ALTER TABLE team_series ADD COLUMN unrelated_note TEXT",
                                      "ALTER TABLE team_series DROP COLUMN t2_color_hex"), 1, None),
}


def _raw_dsn():
    return DSN.replace("postgresql+asyncpg://", "postgresql://", 1)


def _refuse_unless_local_scratch():
    """A local cluster and a scratch database, or nothing runs."""
    from sqlalchemy.engine import make_url
    url = make_url(DSN)
    assert url.host in ("127.0.0.1", "localhost", "::1"), url.host
    assert (url.database or "").startswith("scr_"), url.database


async def _make_schema(case, table, migrate, extra):
    import asyncpg
    name = "dcfm_%s_%s" % (case.replace("-", "_"), uuid.uuid4().hex[:10])
    conn = await asyncpg.connect(_raw_dsn())
    try:
        taken = await conn.fetchval("SELECT count(*) FROM pg_namespace WHERE nspname = $1", name)
        assert taken == 0, name
        await conn.execute('CREATE SCHEMA "%s"' % name)
        _CREATED.add(name)
        await conn.execute('SET search_path TO "%s"' % name)
        if table:
            await conn.execute(PRE_356_TEAM_SERIES)
        if migrate:
            await conn.execute(MIGRATION.read_text(encoding="utf-8"))
        for stmt in extra:
            await conn.execute(stmt)
    finally:
        await conn.close()
    return name


async def _drop_schema(name):
    import asyncpg
    assert name in _CREATED and name.startswith("dcfm_"), name
    conn = await asyncpg.connect(_raw_dsn())
    try:
        await conn.execute('DROP SCHEMA "%s" CASCADE' % name)
        _CREATED.discard(name)
    finally:
        await conn.close()


def _engine(schema):
    from sqlalchemy.ext.asyncio import create_async_engine
    return create_async_engine(DSN, pool_size=1, max_overflow=0, pool_timeout=5,
                               connect_args={"server_settings": {"search_path": schema}})


def _sessions(engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _probe_state(schema):
    """The SQLSTATE the probe raises in `schema`, asked directly of the driver."""
    import asyncpg
    conn = await asyncpg.connect(_raw_dsn(), server_settings={"search_path": schema})
    try:
        await conn.execute(main._TEAM_DC_FALLBACK_PROBE)
        return None
    except asyncpg.PostgresError as exc:
        return exc.sqlstate
    finally:
        await conn.close()


def _chain(exc):
    out, cur, seen = [], exc, set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        out.append("%s[%s]" % (type(cur).__name__, getattr(cur, "sqlstate", None) or "-"))
        cur = getattr(cur, "orig", None) or cur.__cause__
    return " <- ".join(out)


@needs_pg
@pytest.mark.parametrize("case", list(CASES))
def test_pg_the_probe_reads_the_schema_the_code_needs(case):
    """health_check on a real session in a scratch schema: the word follows
    the schema, the answer stays "ok"/"connected" in every case, and the same
    session answers its next statement -- the probe's rollback is what makes
    that true after a failed probe."""
    _refuse_unless_local_scratch()
    table, migrate, extra, want, want_state = CASES[case]

    async def body():
        schema = await _make_schema(case, table, migrate, extra)
        try:
            state = await _probe_state(schema)
            engine = _engine(schema)
            try:
                async with _sessions(engine)() as session:
                    answer = (await main.health_check(db=session)).model_dump()
                    after = (await session.execute(text("SELECT 1"))).scalar()
            finally:
                await engine.dispose()
            return state, answer, after
        finally:
            await _drop_schema(schema)

    state, answer, after = _run(body())
    assert state == want_state, (case, state)
    assert (answer["status"], answer["database"]) == ("ok", "connected"), (case, answer)
    assert answer["team_dc_fallback"] == want, (case, answer["team_dc_fallback"])
    assert after == 1, (case, after)
    print("case %-17s probe SQLSTATE %-6s status %s database %s team_dc_fallback %d next statement %d"
          % (case, state or "none", answer["status"], answer["database"], answer["team_dc_fallback"], after))


@needs_pg
def test_pg_the_real_error_chains_are_classified():
    """The chains SQLAlchemy and asyncpg really raise: the probe on a table
    without the columns and a statement on a missing table are recognised; a
    different SQL error (division by zero, 22012) is not."""
    _refuse_unless_local_scratch()

    async def body():
        schema = await _make_schema("chains", True, False, ())
        out = {}
        try:
            engine = _engine(schema)
            try:
                for label, sql in (("missing-column", main._TEAM_DC_FALLBACK_PROBE),
                                   ("missing-table", "SELECT dc_fallback_at FROM team_series_absent LIMIT 0"),
                                   ("division-by-zero", "SELECT 1 / 0")):
                    async with _sessions(engine)() as session:
                        try:
                            await session.execute(text(sql))
                            out[label] = (None, "no error")
                        except Exception as exc:
                            out[label] = (main._team_dc_fallback_schema_missing(exc), _chain(exc))
            finally:
                await engine.dispose()
        finally:
            await _drop_schema(schema)
        return out

    out = _run(body())
    for label, (verdict, chain) in out.items():
        print("%-16s classified %-5s chain %s" % (label, verdict, chain))
    assert [out[k][0] for k in ("missing-column", "missing-table", "division-by-zero")] == [True, True, False], out


@needs_pg
@pytest.mark.parametrize("case", ["both-absent", "both-present"])
def test_pg_requests_after_a_probe_on_a_one_connection_pool_answer(monkeypatch, case):
    """The route as a worker serves it: the real get_db dependency over a pool
    of ONE connection, three requests in a row. A connection the first request
    left in a failed transaction, or never returned, would make the second
    fail or wait out the pool's timeout; each request is also bounded here."""
    _refuse_unless_local_scratch()
    import database
    import httpx
    from fastapi import FastAPI

    assert main.get_db is database.get_db
    table, migrate, extra, want, _ = CASES[case]

    async def body():
        schema = await _make_schema("pool_" + case, table, migrate, extra)
        try:
            engine = _engine(schema)
            monkeypatch.setattr(database, "async_session", _sessions(engine))
            app = FastAPI()
            routes = [r for r in main.app.routes if getattr(r, "path", None) == "/api/v1/health"]
            assert len(routes) == 1 and routes[0].endpoint is main.health_check, routes
            app.add_api_route("/api/v1/health", main.health_check, methods=["GET"],
                              response_model=schemas.HealthResponse)
            answers = []
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                             base_url="http://team-dc-fallback.test") as client:
                    for _ in range(3):
                        r = await asyncio.wait_for(client.get("/api/v1/health"), 30)
                        answers.append((r.status_code, r.json()))
                out_after = engine.pool.checkedout()
            finally:
                await engine.dispose()
            return answers, out_after
        finally:
            await _drop_schema(schema)

    answers, out_after = _run(body())
    got = [(code, a.get("status"), a.get("database"), a.get("team_dc_fallback")) for code, a in answers]
    assert got == [(200, "ok", "connected", want)] * 3, got
    assert out_after == 0, out_after
    print("pool of one, %s: %s; connections still checked out afterwards: %d" % (case, got, out_after))


# -- the controls, on a copy of the file ---------------------------------------------

# Run in a fresh interpreter over the copied tree: import main from the copy,
# print the columns it derived, then run every other test in this file from
# the copy.
_DRIVER = (
    "import sys\n"
    "api = sys.argv[1]\n"
    "sys.path.insert(0, api)\n"
    "import main\n"
    "print('COLUMNS=%s' % ','.join(main._TEAM_DC_FALLBACK_COLUMNS), flush=True)\n"
    "import pytest\n"
    "sys.exit(pytest.main(['-v', '-p', 'no:cacheprovider', '-k', 'not controls'] + sys.argv[2:]))\n"
)
_SELF = "tests/test_health_team_dc_fallback_marker.py"
_OUTCOME = re.compile(
    r"^(?:\S*[\\/])?tests[\\/]test_health_team_dc_fallback_marker\.py::(\S+) "
    r"(PASSED|FAILED|ERROR|SKIPPED)", re.MULTILINE)
_ZERO_CASES = ["test_pg_the_probe_reads_the_schema_the_code_needs[%s]" % c
               for c in ("at-absent", "player-id-absent", "both-absent", "no-table")]
_OTHER_IDS = ["test_any_other_probe_error_is_left_to_the_outer_catch[%s]" % k for k in _OTHER]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _copy_tree(dst: pathlib.Path) -> pathlib.Path:
    """The smallest tree this file runs from: the api modules, the
    migrations, and the test-side files it and conftest.py import."""
    api = dst / "backend" / "api"
    sql = dst / "backend" / "sql"
    tests = dst / "backend" / "tests"
    for d in (api, sql, tests):
        d.mkdir(parents=True)
    for p in (BACKEND / "api").glob("*.py"):
        shutil.copyfile(p, api / p.name)
    for p in (BACKEND / "sql").glob("*.sql"):
        shutil.copyfile(p, sql / p.name)
    for name in ("conftest.py", "pc_themes_data.py", pathlib.Path(__file__).name):
        shutil.copyfile(BACKEND / "tests" / name, tests / name)
    return api / "main.py"


def _controls():
    """(name, [(old, new)], columns wanted, [test ids that must FAIL]).

    Each (old, new) is applied once and `old` must occur exactly once in the
    file, so a control can neither miss its target nor hit a second one.
    Every test not named must PASS (or SKIP, when it is live and no database
    is configured)."""
    return [
        ("derivation-misses-a-column",
         [('_TEAM_DC_FALLBACK_NAME = _re.compile(r"\\bdc_fallback_[a-z_]+\\b")\n',
           '_TEAM_DC_FALLBACK_NAME = _re.compile(r"\\bdc_fallback_at\\b")\n')],
         "dc_fallback_at",
         ["test_the_probe_is_derived_from_the_four_functions_and_names_the_migrations_columns",
          "test_every_statement_naming_a_dc_fallback_column_belongs_to_the_four_functions",
          "test_the_derivation_reads_statements_and_nothing_else",
          "test_the_connected_arm_probes_after_select_1_and_answers_1",
          "test_a_missing_column_or_table_reads_0_and_the_box_stays_ok[column]",
          "test_a_missing_column_or_table_reads_0_and_the_box_stays_ok[table]",
          "test_pg_the_probe_reads_the_schema_the_code_needs[player-id-absent]"]),
        ("catch-broadened",
         [("        if not _team_dc_fallback_schema_missing(exc):\n"
           "            raise\n", "")],
         "dc_fallback_at,dc_fallback_player_id",
         list(_OTHER_IDS)),
        ("rollback-removed",
         [("        await db.rollback()\n"
           "        _TEAM_DC_FALLBACK_LAST = 0\n",
           "        _TEAM_DC_FALLBACK_LAST = 0\n")],
         "dc_fallback_at,dc_fallback_player_id",
         ["test_a_missing_column_or_table_reads_0_and_the_box_stays_ok[column]",
          "test_a_missing_column_or_table_reads_0_and_the_box_stays_ok[table]"] + list(_ZERO_CASES)
         # The discord_fix probe is a bare statement sent after this one on the
         # same session, so a transaction this probe left failed now fails the
         # route's own answer (degraded) on the first request of the pool test.
         + ["test_pg_requests_after_a_probe_on_a_one_connection_pool_answer[both-absent]"]),
        ("degraded-arm-unwired",
         [("                              team_dc_fallback=_TEAM_DC_FALLBACK_LAST,\n",
           "                              team_dc_fallback=0,\n")],
         "dc_fallback_at,dc_fallback_player_id",
         list(_OTHER_IDS) + ["test_the_degraded_arm_answers_the_cache_the_probe_writes",
                             "test_both_arms_carry_the_key_and_only_the_probe_writes_the_cache"]),
        ("answers-without-asking",
         [("        await db.execute(text(_TEAM_DC_FALLBACK_PROBE))\n", "        pass\n")],
         "dc_fallback_at,dc_fallback_player_id",
         ["test_the_connected_arm_probes_after_select_1_and_answers_1",
          "test_a_missing_column_or_table_reads_0_and_the_box_stays_ok[column]",
          "test_a_missing_column_or_table_reads_0_and_the_box_stays_ok[table]",
          "test_the_degraded_arm_answers_the_cache_the_probe_writes",
          "test_pg_requests_after_a_probe_on_a_one_connection_pool_answer[both-absent]"]
         + list(_OTHER_IDS) + list(_ZERO_CASES)),
        ("missing-table-not-classified",
         [('_TEAM_DC_FALLBACK_SQLSTATES = frozenset({"42703", "42P01"})',
           '_TEAM_DC_FALLBACK_SQLSTATES = frozenset({"42703"})'),
          ("        if isinstance(cur, (_team_dc_apg_exc.UndefinedColumnError,\n"
           "                            _team_dc_apg_exc.UndefinedTableError)):\n",
           "        if isinstance(cur, (_team_dc_apg_exc.UndefinedColumnError,)):\n")],
         "dc_fallback_at,dc_fallback_player_id",
         ["test_the_classifier_reads_the_wrapping_chain[driver-table]",
          "test_the_classifier_reads_the_wrapping_chain[wrapped-table]",
          "test_a_missing_column_or_table_reads_0_and_the_box_stays_ok[table]",
          "test_pg_the_probe_reads_the_schema_the_code_needs[no-table]",
          "test_pg_the_real_error_chains_are_classified"]),
        ("comment-twin",
         [("_TEAM_DC_FALLBACK_COLUMNS = _team_dc_fallback_columns(\n",
           "# a comment beside the derivation: it changes nothing the derivation reads\n"
           "_TEAM_DC_FALLBACK_COLUMNS = _team_dc_fallback_columns(\n"),
          ("        await db.execute(text(_TEAM_DC_FALLBACK_PROBE))\n",
           "        # a comment inside the probe: it changes nothing the probe asks\n"
           "        await db.execute(text(_TEAM_DC_FALLBACK_PROBE))\n")],
         "dc_fallback_at,dc_fallback_player_id",
         []),
    ]


def test_the_controls_run_on_a_copy_in_both_directions(tmp_path):
    """RED: each defect reddens exactly the tests named for it and no other --
    the derivation missing a column, the catch broadened to every error, the
    rollback removed, the degraded arm unwired from the cache, the probe
    answering without asking, and a missing table left unclassified. GREEN:
    a comment-only twin reddens nothing, which is also what proves the copied
    tree runs every test at all. Every mutation lands on the COPY, is restored
    byte for byte (sha256), and the worktree's main.py is the same bytes at
    the end.

    The rollback control carries the question the design left open: whether
    the real get_db teardown would have made a failed probe safe for the NEXT
    request on its own. The one-connection pool test stays green without the
    rollback -- get_db's close() returns the connection clean -- while the
    same-session statement after the probe goes red: the rollback is what the
    session itself needs.

    The live half needs SEPT16DC_TEST_PG_DSN. Without it the live tests SKIP
    in the copy, the rest is still asserted, and this test then SKIPS rather
    than passing: a skipped live half is an unrun test, not an acceptance."""
    original = MAIN_PY.read_bytes()
    before = _sha256(original)
    copy = _copy_tree(tmp_path)
    assert _sha256(copy.read_bytes()) == before
    source = original.decode("utf-8")
    nl = "\r\n" if "\r\n" in source else "\n"
    driver = tmp_path / "marker_driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    live = bool(DSN)
    env = {k: v for k, v in os.environ.items()
           if not (k.endswith("_PG_DSN") and k != LIVE_DSN)
           and not k.endswith("_TESTS_REQUIRED") and k != "PYTEST_ADDOPTS"}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")

    universe = None
    for name, edits, want_columns, want_failed in _controls():
        mutated = source
        for old, new in edits:
            old, new = old.replace("\n", nl), new.replace("\n", nl)
            assert source.count(old) == 1, (name, old, source.count(old))
            mutated = mutated.replace(old, new, 1)
        mutated_bytes = mutated.encode("utf-8")
        assert _sha256(mutated_bytes) != before, name
        copy.write_bytes(mutated_bytes)
        try:
            proc = subprocess.run(
                [sys.executable, str(driver), str(copy.parent), _SELF],
                cwd=str(tmp_path / "backend"), env=env, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=900)
        finally:
            copy.write_bytes(original)
        restored = _sha256(copy.read_bytes())
        assert restored == before, (name, restored, before)

        out = proc.stdout + proc.stderr
        columns = re.findall(r"^COLUMNS=(\S*)$", out, re.MULTILINE)
        assert columns == [want_columns], (name, columns, out[-3000:])
        outcomes = dict(_OUTCOME.findall(out))
        if universe is None:
            universe = set(outcomes)
            assert len(universe) >= 30, (name, sorted(universe), out[-3000:])
        assert set(outcomes) == universe, (name, sorted(set(outcomes) ^ universe))
        assert set(want_failed) <= universe, (name, sorted(set(want_failed) - universe))
        want = {}
        for test in universe:
            if test.startswith("test_pg_") and not live:
                want[test] = "SKIPPED"
            else:
                want[test] = "FAILED" if test in want_failed else "PASSED"
        wrong = {t: (outcomes[t], want[t]) for t in universe if outcomes[t] != want[t]}
        assert not wrong, (name, wrong, out[-4000:])
        assert proc.returncode == (1 if "FAILED" in want.values() else 0), \
            (name, proc.returncode, out[-3000:])
        tally = {k: sum(1 for v in outcomes.values() if v == k) for k in ("PASSED", "FAILED", "SKIPPED")}
        print("control %-29s columns %-37s passed %2d failed %2d skipped %2d rc %d  "
              "mutated sha256 %s  restored sha256 %s == original"
              % (name, want_columns, tally["PASSED"], tally["FAILED"], tally["SKIPPED"],
                 proc.returncode, _sha256(mutated_bytes)[:16], restored[:16]))
        for test in sorted(t for t in universe if outcomes[t] == "FAILED"):
            print("    red: %s" % test)

    assert _sha256(MAIN_PY.read_bytes()) == before
    print("worktree main.py sha256 %s, unchanged by the controls" % before[:16])
    if not live:
        pytest.skip("the controls' offline half is asserted on the copy; the live half needs "
                    "%s (PostgreSQL), so the controls are not accepted by this run" % LIVE_DSN)
