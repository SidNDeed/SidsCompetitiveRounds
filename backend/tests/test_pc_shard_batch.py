"""Board row 25 (whole-pack quick shard), the server half, EXECUTED against
a real PostgreSQL.

POST /api/v1/pc/prints/discard-batch discards up to
player_cards.PC_DISCARD_BATCH_CAP prints of the caller's in one transaction,
pays each by the rarity table, credits the total as ONE delta, and records
its idempotency key (migration 361) so a replay answers the same total and
credits nothing. It reads its own body under a byte ceiling before parsing
it. Both discard routes pass one refusal gate
(main._pc_discard_gate). The harness below is also the one
test_pc_settings_preview (board row 24) imports.

Every rule is a named test below, written as the rule's CONTROL (the
behaviour it produces). The mutation runs (ai-collab/v1410/asks-b-*.log)
break each rule in turn on a copy of the tree and record the named test's
red output; the tests never know which mutant is applied.

THE DATABASE. One schema, pc_shard_t, in the database PC_SHARD_TEST_PG_DSN
names. Every migration numbered below 361 is replayed into it statement by
statement (each file's own transaction honoured; a statement that fails on
an empty database is recorded, not fatal), the ORM creates the tables no
migration creates, the replay runs again, the ORM's missing columns are
added, and 361 is applied whole. The build is reused while the migrations,
models.py and this harness are unchanged and the schema still fingerprints
as built. Before the schema is dropped the harness refuses when an object
outside pc_shard_t depends on one inside it (what DROP SCHEMA ... CASCADE
would also remove). Every connection the harness and the routes use has
pc_shard_t as its ONLY search path entry.

Routes are called as the functions FastAPI would call, one session per
request, each client on its own connection (application_name pcs_<name>),
so a test can see who waits on a lock in pg_stat_activity and read the
ordered log of every statement each client sent.

RUNNING IT
----------
    PC_SHARD_TEST_PG_DSN="postgresql://postgres@127.0.0.1:55432/asksb_cards" \\
        python -m pytest backend/tests/test_pc_shard_batch.py -q

Without the DSN every database test FAILS by name rather than skipping (a
skip is a run that proved nothing while reporting exit 0). Set
PC_SHARD_TEST_PG_OPTOUT=1 to waive the coverage deliberately and the
failures become named skips. The structure tests run either way.

There is no pytest-asyncio in this suite: each test is a sync function that
runs one coroutine.
"""
import asyncio
import hashlib
import hmac
import json
import os
import re
import sys
import textwrap
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND / "api"))
sys.path.insert(0, str(HERE))

import main  # noqa: E402
import models  # noqa: E402
import player_cards as _pc  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import event, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

try:
    import asyncpg
except ImportError:                                    # pragma: no cover
    asyncpg = None

DSN_VAR = "PC_SHARD_TEST_PG_DSN"
OPTOUT_VAR = "PC_SHARD_TEST_PG_OPTOUT"
_RAW_DSN = os.environ.get(DSN_VAR) or ""
DSN_PLAIN = re.sub(r"^postgres(?:ql)?(?:\+asyncpg)?://", "postgresql://", _RAW_DSN) if _RAW_DSN else ""
DSN_ASYNC = DSN_PLAIN.replace("postgresql://", "postgresql+asyncpg://", 1) if DSN_PLAIN else ""
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"

SCHEMA = "pc_shard_t"
HARNESS_TABLE = "pc_shard_harness"
HARNESS_VERSION = "1"
SQL_DIR = BACKEND / "sql"
MIGRATION = SQL_DIR / "361_pc_shard_batches.sql"
MIGRATION_NUMBER = 361

SECRET = "pc-shard-test-mod-secret"
INTERNAL_KEY = "pc-shard-test-internal-key"
# Synthetic ids inside the individual SteamID64 range
# (76561197960265728 .. 76561202255233023) and far from any live account.
STEAM_BASE = "765612022551"
REQ = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"),
                      query_params={}, url=SimpleNamespace(path="/"))
PAY = {"common": 5, "uncommon": 15, "rare": 40, "epic": 150, "legendary": 600}


def _require_pg():
    """Fail, not skip, when the DSN is unset (see the module docstring)."""
    if DSN_PLAIN and asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: the live-PostgreSQL batch shard coverage is "
                    "deliberately waived for this run." % (DSN_VAR, OPTOUT_VAR))
    if asyncpg is None:
        pytest.fail("asyncpg is not installed, so no discard route ran against migration "
                    "361. Install it, or set %s=1 to waive the coverage." % OPTOUT_VAR)
    pytest.fail(
        "%s is unset, so neither discard route, the batch idempotency record (migration 361) "
        "nor the Settings preview route ran against a server -- the subject of this file. "
        "Point it at a throwaway database (see the module docstring), or set %s=1 to waive "
        "the coverage deliberately." % (DSN_VAR, OPTOUT_VAR))


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- pure helpers

def split_sql(sql):
    """Statements of a script, split on ';' outside comments, quotes and
    dollar quotes -- psql's own rule. A statement that is only comments is
    dropped."""
    out, buf, i, n = [], [], 0, len(sql)
    bare = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
    while i < n:
        c = sql[i]
        if c == "-" and sql.startswith("--", i):
            j = sql.find("\n", i)
            j = n if j < 0 else j
            buf.append(sql[i:j])
            i = j
        elif c == "/" and sql.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if sql.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif sql.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            buf.append(sql[i:j])
            i = j
        elif c == "'":
            escaped = i > 0 and sql[i - 1] in "eE" and (i < 2 or not (sql[i - 2].isalnum() or sql[i - 2] == "_"))
            j = i + 1
            while j < n:
                if escaped and sql[j] == chr(92):
                    j += 2
                    continue
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            buf.append(sql[i:j + 1])
            i = j + 1
        elif c == '"':
            j = sql.find('"', i + 1)
            j = n - 1 if j < 0 else j
            buf.append(sql[i:j + 1])
            i = j + 1
        elif c == "$":
            m = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$", sql[i:])
            if m and not (i > 0 and (sql[i - 1].isalnum() or sql[i - 1] == "_")):
                tag = m.group(0)
                j = sql.find(tag, i + len(tag))
                j = n if j < 0 else j + len(tag)
                buf.append(sql[i:j])
                i = j
            else:
                buf.append(c)
                i += 1
        elif c == ";":
            stmt = "".join(buf).strip()
            if bare.sub("", stmt).strip():
                out.append(stmt)
            buf = []
            i += 1
        else:
            buf.append(c)
            i += 1
    stmt = "".join(buf).strip()
    if bare.sub("", stmt).strip():
        out.append(stmt)
    return out


def _bare(stmt):
    return " ".join(re.sub(r"--[^\n]*|/\*.*?\*/", "", stmt, flags=re.S).split())


def _numbered(upto=None):
    files = sorted(p for p in SQL_DIR.glob("*.sql") if re.match(r"^\d{3}_", p.name))
    if upto is not None:
        files = [p for p in files if int(p.name[:3]) <= upto]
    return files


def _sign(canon):
    return hmac.new(SECRET.encode(), canon.encode(), hashlib.sha256).hexdigest()


def _steam(n):
    return STEAM_BASE + "%05d" % n


def _flat(s):
    return " ".join(s.split())


def _fn_src(name):
    """The source of one module-level function of main.py, dedented."""
    import inspect
    return textwrap.dedent(inspect.getsource(getattr(main, name)))


def _code(src):
    """A function's source as its code tokens, space-joined: comments and
    string-only statements (docstrings) are dropped, so prose can never
    satisfy a structural assertion. String literals inside code stay whole."""
    import io
    import tokenize
    toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type not in (tokenize.COMMENT, tokenize.NL)]
    out = []
    for i, tok in enumerate(toks):
        if tok.type == tokenize.STRING:
            before = toks[i - 1].type if i else tokenize.NEWLINE
            after = toks[i + 1].type if i + 1 < len(toks) else tokenize.NEWLINE
            if before in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT) and after == tokenize.NEWLINE:
                continue
        out.append(tok.string)
    return " ".join(out)


# ------------------------------------------------------------------ the schema

_BEGIN_RE = re.compile(r"(?is)^(begin|start\s+transaction)(\s+(transaction|work))?(\s+isolation\s+level\s+[a-z ]+)?$")
_END_RE = re.compile(r"(?is)^(commit|end)(\s+(transaction|work))?$")
_ROLLBACK_RE = re.compile(r"(?is)^rollback(\s+(transaction|work))?$")

_FINGERPRINT_SQL = """
SELECT md5(string_agg(x, '|' ORDER BY x)) FROM (
  SELECT 'col:' || c.relname || '.' || a.attname || ':' || format_type(a.atttypid, a.atttypmod)
         || ':' || a.attnotnull || ':' || coalesce(pg_get_expr(d.adbin, d.adrelid), '') AS x
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
   WHERE n.nspname = $1 AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped
     AND c.relname <> $2
  UNION ALL
  SELECT 'idx:' || pg_get_indexdef(i.indexrelid)
    FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = $1 AND c.relname <> $2
  UNION ALL
  SELECT 'con:' || c.relname || '.' || k.conname || ':' || pg_get_constraintdef(k.oid)
    FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = $1 AND c.relname <> $2
  UNION ALL
  SELECT 'trg:' || c.relname || '.' || t.tgname || ':' || t.tgenabled::text || ':' || pg_get_triggerdef(t.oid)
    FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = $1 AND NOT t.tgisinternal
  UNION ALL
  SELECT 'fn:' || p.proname || '(' || pg_get_function_identity_arguments(p.oid) || '):' || md5(p.prosrc)
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname = $1
) s
"""

# What DROP SCHEMA ... CASCADE would remove OUTSIDE the schema: every object
# that depends on an object inside it and does not itself live inside it.
_FOREIGN_DEPENDENTS_SQL = """
WITH dep AS (
    SELECT d.classid, d.objid, d.objsubid
      FROM pg_depend d
     WHERE d.deptype IN ('n', 'a')
       AND (pg_identify_object(d.refclassid, d.refobjid, d.refobjsubid)).schema = $1
), placed AS (
    SELECT dep.*, CASE dep.classid
        WHEN 'pg_class'::regclass THEN (SELECT c.relnamespace FROM pg_class c WHERE c.oid = dep.objid)
        WHEN 'pg_rewrite'::regclass THEN (SELECT c.relnamespace FROM pg_rewrite r
                                            JOIN pg_class c ON c.oid = r.ev_class WHERE r.oid = dep.objid)
        WHEN 'pg_attrdef'::regclass THEN (SELECT c.relnamespace FROM pg_attrdef a
                                            JOIN pg_class c ON c.oid = a.adrelid WHERE a.oid = dep.objid)
        WHEN 'pg_constraint'::regclass THEN (SELECT k.connamespace FROM pg_constraint k WHERE k.oid = dep.objid)
        WHEN 'pg_trigger'::regclass THEN (SELECT c.relnamespace FROM pg_trigger t
                                            JOIN pg_class c ON c.oid = t.tgrelid WHERE t.oid = dep.objid)
        WHEN 'pg_proc'::regclass THEN (SELECT p.pronamespace FROM pg_proc p WHERE p.oid = dep.objid)
        WHEN 'pg_type'::regclass THEN (SELECT y.typnamespace FROM pg_type y WHERE y.oid = dep.objid)
        WHEN 'pg_policy'::regclass THEN (SELECT c.relnamespace FROM pg_policy o
                                           JOIN pg_class c ON c.oid = o.polrelid WHERE o.oid = dep.objid)
        END AS nsp
      FROM dep
)
SELECT DISTINCT (pg_identify_object(classid, objid, objsubid)).identity AS dependent
  FROM placed
 WHERE nsp IS DISTINCT FROM (SELECT n.oid FROM pg_namespace n WHERE n.nspname = $1)
"""


async def _connect(app="harness", replica=False):
    conn = await asyncpg.connect(DSN_PLAIN, server_settings={
        "search_path": '"%s"' % SCHEMA, "application_name": "pcs_" + app})
    if replica:
        await conn.execute("SET session_replication_role = replica")
    return conn


async def _refuse_foreign(conn):
    foreign = [r[0] for r in await conn.fetch(_FOREIGN_DEPENDENTS_SQL, SCHEMA)]
    if foreign:
        pytest.fail("REFUSED: objects outside %s depend on objects inside it, so dropping it "
                    "would remove them too: %s" % (SCHEMA, foreign[:10]))


async def _fingerprint(conn):
    return await conn.fetchval(_FINGERPRINT_SQL, SCHEMA, HARNESS_TABLE)


async def _replay(conn, files):
    failures, count = [], 0
    for f in files:
        in_tx = False
        for stmt in split_sql(f.read_text(encoding="utf-8")):
            b = _bare(stmt)
            if _BEGIN_RE.match(b):
                await conn.execute("BEGIN")
                in_tx = True
                continue
            if _END_RE.match(b) or _ROLLBACK_RE.match(b):
                if in_tx:
                    await conn.execute("COMMIT")
                in_tx = False
                continue
            count += 1
            if in_tx:
                await conn.execute("SAVEPOINT harness_stmt")
            try:
                await conn.execute(stmt)
                if in_tx:
                    await conn.execute("RELEASE SAVEPOINT harness_stmt")
            except Exception as e:                      # recorded, not fatal
                if in_tx:
                    await conn.execute("ROLLBACK TO SAVEPOINT harness_stmt")
                failures.append("%s: %s" % (f.name, (str(e).splitlines() or [""])[0][:120]))
        if in_tx:
            await conn.execute("COMMIT")
    return count, failures


def _harness_key():
    h = hashlib.sha256()
    for p in _numbered(upto=MIGRATION_NUMBER):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    h.update((BACKEND / "api" / "models.py").read_bytes())
    h.update(HARNESS_VERSION.encode())
    h.update(split_sql.__code__.co_code)
    return h.hexdigest()


async def _orm(fn):
    engine = create_async_engine(DSN_ASYNC, poolclass=NullPool, connect_args={"server_settings": {
        "search_path": '"%s"' % SCHEMA, "application_name": "pcs_orm"}})
    try:
        async with engine.begin() as c:
            return await fn(c)
    finally:
        await engine.dispose()


async def _create_all(c):
    await c.run_sync(models.Base.metadata.create_all)


async def _orm_columns(c):
    from sqlalchemy.schema import CreateColumn
    added = []
    for table in models.Base.metadata.sorted_tables:
        have = {r[0] for r in (await c.exec_driver_sql(
            "SELECT attname FROM pg_attribute WHERE attrelid = to_regclass('\"%s\".\"%s\"') "
            "AND attnum > 0 AND NOT attisdropped" % (SCHEMA, table.name))).all()}
        for col in table.columns:
            if col.name not in have:
                ddl = str(CreateColumn(col).compile(dialect=c.dialect))
                await c.exec_driver_sql('ALTER TABLE "%s"."%s" ADD COLUMN %s' % (SCHEMA, table.name, ddl))
                added.append("%s.%s" % (table.name, col.name))
    return added


async def _tables(conn):
    return [r[0] for r in await conn.fetch(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = $1 AND c.relkind = 'r' AND c.relname <> $2 ORDER BY 1", SCHEMA, HARNESS_TABLE)]


async def _build():
    conn = await _connect()
    try:
        await _refuse_foreign(conn)
        key = _harness_key()
        exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", '"%s"."%s"' % (SCHEMA, HARNESS_TABLE))
        if exists:
            row = await conn.fetchrow('SELECT key, fp_pre, fp_full, empty_tables FROM "%s"."%s"'
                                      % (SCHEMA, HARNESS_TABLE))
            if row is not None and row["key"] == key:
                if await _fingerprint(conn) != row["fp_full"]:
                    await conn.execute(MIGRATION.read_text(encoding="utf-8"))
                if await _fingerprint(conn) == row["fp_full"]:
                    return {"fp_pre": row["fp_pre"], "fp_full": row["fp_full"],
                            "empty": list(row["empty_tables"]), "reused": True}
        await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % SCHEMA)
        await conn.execute('CREATE SCHEMA "%s"' % SCHEMA)
        files = _numbered(upto=MIGRATION_NUMBER - 1)
        await _replay(conn, files)
        await _orm(_create_all)
        await _replay(conn, files)
        await _orm(_orm_columns)
        fp_pre = await _fingerprint(conn)
        assert await conn.fetchval("SELECT to_regclass('pc_shard_batches') IS NULL"), (
            "pc_shard_batches exists before 361 ran: the ORM or an earlier file creates it")
        await conn.execute(MIGRATION.read_text(encoding="utf-8"))
        fp_full = await _fingerprint(conn)
        assert fp_full != fp_pre, "361 changed nothing"
        empty = []
        for t in await _tables(conn):
            if not await conn.fetchval('SELECT EXISTS (SELECT 1 FROM "%s"."%s")' % (SCHEMA, t)):
                empty.append(t)
        await conn.execute('CREATE TABLE "%s"."%s" (key text, fp_pre text, fp_full text, empty_tables text[])'
                           % (SCHEMA, HARNESS_TABLE))
        await conn.execute('INSERT INTO "%s"."%s" VALUES ($1, $2, $3, $4)' % (SCHEMA, HARNESS_TABLE),
                           key, fp_pre, fp_full, empty)
        return {"fp_pre": fp_pre, "fp_full": fp_full, "empty": empty, "reused": False}
    finally:
        await conn.close()


async def _restore(conn, build):
    if await _fingerprint(conn) == build["fp_full"]:
        return
    await conn.execute(MIGRATION.read_text(encoding="utf-8"))
    assert await _fingerprint(conn) == build["fp_full"], "re-running 361 did not restore the full schema"


_DRAWN_SEQUENCES_SQL = """
    SELECT format('%I.%I', n.nspname, s.relname)
      FROM pg_class s
      JOIN pg_namespace n ON n.oid = s.relnamespace
      JOIN pg_depend d ON d.classid = 'pg_class'::regclass AND d.objid = s.oid
                      AND d.refclassid = 'pg_class'::regclass AND d.deptype IN ('a', 'i')
      JOIN pg_class t ON t.oid = d.refobjid
      JOIN pg_sequences q ON q.schemaname = n.nspname AND q.sequencename = s.relname
     WHERE s.relkind = 'S' AND n.nspname = $1 AND t.relname = ANY($2::text[])
       AND q.last_value IS NOT NULL
"""


async def _reset(build):
    """Every table that was empty at build empty again, the sequences they
    own restarted, the schema full (361 re-run if a test removed it)."""
    conn = await _connect("reset")
    try:
        await _restore(conn, build)
        probe = " UNION ALL ".join("SELECT '%s' WHERE EXISTS (SELECT 1 FROM \"%s\".\"%s\")" % (t, SCHEMA, t)
                                   for t in build["empty"])
        full = [r[0] for r in await conn.fetch(probe)]
        await conn.execute("SET session_replication_role = replica")
        for t in full:
            await conn.execute('DELETE FROM "%s"."%s"' % (SCHEMA, t))
        for seq in [r[0] for r in await conn.fetch(_DRAWN_SEQUENCES_SQL, SCHEMA, build["empty"])]:
            await conn.execute("ALTER SEQUENCE %s RESTART" % seq)
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def pg_build():
    _require_pg()
    return _run(_build())


@pytest.fixture
def env(pg_build, monkeypatch, tmp_path):
    """A database test's environment: the full schema, empty of data, the mod
    secret and the internal key set, the session proof stubbed, the Steam
    picture sweep paused (no outbound request), and the face cache in a
    temporary directory."""
    _run(_reset(pg_build))
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    monkeypatch.setenv("API_SECRET_KEY", INTERNAL_KEY)
    monkeypatch.setenv("PC_STEAM_SWEEP", "off")
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)

    async def _session_ok(*_a, **_k):
        return True
    monkeypatch.setattr(main, "_strict_steam_session_ok", _session_ok)
    monkeypatch.setattr(main, "_pc_face_cache", main._pcp.FaceCache(str(tmp_path / "faces")))
    return SimpleNamespace(build=pg_build, monkeypatch=monkeypatch, tmp=tmp_path)


# ------------------------------------------------------------- the clients

class Gate:
    def __init__(self):
        self.reached = asyncio.Event()
        self.go = asyncio.Event()


class Ctx:
    """One test's clients: an engine per client name (its own connection),
    one ordered log of every statement any client sent, pause points around
    module-level helpers keyed on the asyncio task's name, and a monitor."""

    def __init__(self, env):
        self.env = env
        self.engines = {}
        self.log = []
        self.gates = {}
        self.wrapped = set()
        self.monitor = None

    async def session(self, name):
        eng = self.engines.get(name)
        if eng is None:
            eng = create_async_engine(DSN_ASYNC, poolclass=NullPool, connect_args={"server_settings": {
                "search_path": '"%s"' % SCHEMA, "application_name": "pcs_" + name}})
            async with eng.connect() as c:
                await c.exec_driver_sql("SELECT 1")

            def _rec(conn, cursor, statement, parameters, context, executemany, _name=name):
                self.log.append((len(self.log), _name, statement))
            event.listen(eng.sync_engine, "before_cursor_execute", _rec)
            self.engines[name] = eng
        return async_sessionmaker(eng, expire_on_commit=False)

    def statements(self, name):
        return [s for _i, n, s in self.log if n == name]

    async def close(self):
        for eng in self.engines.values():
            await eng.dispose()
        if self.monitor is not None:
            await self.monitor.close()

    def gate(self, task, fn_name, phase="post"):
        """Pause the task named `task` the first time it calls main.<fn_name>,
        before ("pre") or after ("post") the call."""
        g = Gate()
        self.gates[(task, fn_name, phase)] = g
        if fn_name not in self.wrapped:
            self.wrapped.add(fn_name)
            orig = getattr(main, fn_name)
            gates = self.gates

            async def wrapper(*a, **k):
                me = asyncio.current_task().get_name()
                pre = gates.pop((me, fn_name, "pre"), None)
                if pre is not None:
                    pre.reached.set()
                    await pre.go.wait()
                result = await orig(*a, **k)
                post = gates.pop((me, fn_name, "post"), None)
                if post is not None:
                    post.reached.set()
                    await post.go.wait()
                return result
            self.env.monkeypatch.setattr(main, fn_name, wrapper)
        return g

    async def waiting(self, name):
        if self.monitor is None:
            self.monitor = await _connect("monitor")
        rows = await self.monitor.fetch(
            "SELECT wait_event_type FROM pg_stat_activity WHERE application_name = $1", "pcs_" + name)
        return any(r["wait_event_type"] == "Lock" for r in rows)

    async def lock_or_done(self, name, task, timeout=8.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if task.done():
                return "done"
            if await self.waiting(name):
                return "lock"
            await asyncio.sleep(0.02)
        pytest.fail("client %s neither waited on a lock nor finished in %.0fs" % (name, timeout))

    async def reached(self, g, what, timeout=8.0):
        try:
            await asyncio.wait_for(g.reached.wait(), timeout)
        except asyncio.TimeoutError:
            pytest.fail("pause point never reached: %s" % what)


async def _call(ctx, name, fn, **kw):
    """One request: its own session, the route function as FastAPI calls it.
    (status, body); an HTTPException is its status and detail, anything else
    a 500 with the exception's first line."""
    maker = await ctx.session(name)
    async with maker() as db:
        try:
            return 200, await fn(db=db, **kw)
        except HTTPException as e:
            return e.status_code, e.detail
        except Exception as e:                           # the route's own 500
            return 500, "%s: %s" % (type(e).__name__, (str(e).splitlines() or [""])[0][:200])


def _err(answer):
    status, body = answer
    return status, (body.get("error") if isinstance(body, dict) else body)


class _BodyReq:
    """REQ carrying a body, as Starlette hands one to a route that reads its
    own: the attributes the actor gate reads, a Content-Length header (the
    body's own length, `length` when given, none when `declared` is False:
    a chunked upload) and stream() in `chunk`-byte pieces, counting the
    bytes the route pulled."""

    def __init__(self, raw, declared=True, chunk=4096, length=None):
        self.headers = {"content-length": str(len(raw) if length is None else length)} if declared else {}
        self.client, self.query_params, self.url = REQ.client, REQ.query_params, REQ.url
        self.raw, self.chunk, self.pulled = raw, chunk, 0

    async def stream(self):
        for i in range(0, len(self.raw), self.chunk):
            part = self.raw[i:i + self.chunk]
            self.pulled += len(part)
            yield part


def _body(key, ids):
    return json.dumps({"key": key, "print_ids": list(ids)}).encode("ascii")


def _batch(ctx, name, who, key, ids, sig=None, req=None):
    return _call(ctx, name, main.pc_discard_batch, request=req or _BodyReq(_body(key, ids)), steam_id=who.steam,
                 sig=sig if sig is not None else _sign(_pc.canon_discard_batch(who.steam, key, list(ids))))


def _single(ctx, name, who, print_id):
    return _call(ctx, name, main.pc_discard_print, request=REQ, steam_id=who.steam, print_id=print_id,
                 sig=_sign(_pc.canon_discard(who.steam, print_id)))


# ------------------------------------------------------------ fixture data

async def _q(sql, *args):
    conn = await _connect("fixture")
    try:
        return await conn.fetch(sql, *args)
    finally:
        await conn.close()


async def _val(sql, *args):
    rows = await _q(sql, *args)
    return rows[0][0] if rows else None


async def _player(n, *, shards=0, name=None, member=None):
    """A player who ran the mod a day ago, with `shards` in the balance; with
    `member` = (rarity, pool_rank), a row in the latest pool snapshot too."""
    steam = _steam(n)
    # Through the ORM, as the api creates a player: several columns carry
    # only an ORM default, so a bare INSERT would not be a real row.
    engine = create_async_engine(DSN_ASYNC, poolclass=NullPool, connect_args={"server_settings": {
        "search_path": '"%s"' % SCHEMA, "application_name": "pcs_fixture_orm"}})
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            p = models.Player(steam_id=steam, display_name=name or ("Collector %d" % n))
            db.add(p)
            await db.flush()
            await db.execute(text("UPDATE players SET mod_seen_at = now() - interval '1 day', "
                                  "pc_shards = CAST(:s AS integer) WHERE id = CAST(:pid AS uuid)"),
                             {"s": shards, "pid": str(p.id)})
            await db.commit()
            pid = str(p.id)
    finally:
        await engine.dispose()
    if member is not None:
        snap = await _val("SELECT MAX(id) FROM pc_pool_snapshots")
        if snap is None:
            snap = await _val("INSERT INTO pc_pool_snapshots (member_count) VALUES (0) RETURNING id")
        await _q("""INSERT INTO pc_pool_members (snapshot_id, player_id, pool_rank, rarity, rating,
                                                 board_rank, series_wins, series_losses, top_card, title)
                    VALUES ($1, $2::uuid, $3, $4, 1712.0, 9, 11, 4, NULL, NULL)""",
                 snap, pid, member[1], member[0])
    return SimpleNamespace(n=n, steam=steam, pid=pid)


async def _print(owner, subject, rarity):
    """One live print of `subject`'s card, owned by `owner`."""
    return str(await _val("""
        WITH card AS (
            INSERT INTO pc_cards (subject_player_id, edition_id)
            VALUES ($2::uuid, (SELECT id FROM pc_editions WHERE ended_at IS NULL ORDER BY id LIMIT 1))
            ON CONFLICT (subject_player_id, edition_id, variant) DO UPDATE SET variant = EXCLUDED.variant
            RETURNING id)
        INSERT INTO pc_prints (card_id, owner_player_id, snapshot_id, rarity, pool_rank, source)
        SELECT id, $1::uuid, 1, $3, 1, 'pack' FROM card RETURNING id""", owner.pid, subject.pid, rarity))


async def _shards(who):
    return await _val("SELECT pc_shards FROM players WHERE id = $1::uuid", who.pid)


async def _discarded(ids):
    rows = await _q("SELECT id::text AS id, discarded_at IS NOT NULL AS gone, discard_shards "
                    "FROM pc_prints WHERE id = ANY($1::uuid[]) ORDER BY id", list(ids))
    return {r["id"]: (r["gone"], r["discard_shards"]) for r in rows}


async def _batches(who):
    return [dict(r) for r in await _q("SELECT batch_key, print_ids, prints, shards_gained FROM pc_shard_batches "
                                      "WHERE player_id = $1::uuid ORDER BY batch_key", who.pid)]


def _scenario(env, body):
    """Run one async scenario with a fresh Ctx, closing every connection."""
    async def _go():
        ctx = Ctx(env)
        try:
            return await body(ctx)
        finally:
            await ctx.close()
    return _run(_go())


def _key():
    return uuid.uuid4().hex


# ============================================================ row 25: payout

def test_the_batch_pays_the_rarity_table_and_credits_one_delta_onto_the_balance(env):
    """Five prints, one of each rarity, start balance 7: the answer and the
    balance carry 7 + 5 + 15 + 40 + 150 + 600, every print is discarded at
    its own value, the key's row records the batch, and the credit is ONE
    delta statement (rules R1 payout and R2 delta)."""
    async def body(ctx):
        me = await _player(1, shards=7)
        subject = await _player(2)
        ids = [await _print(me, subject, r) for r in ("common", "uncommon", "rare", "epic", "legendary")]
        k = _key()
        status, ans = await _batch(ctx, "a", me, k, ids)
        assert status == 200, ans
        assert ans["shards_gained"] == 810 and ans["prints"] == 5 and ans["replayed"] is False
        assert ans["shards"] == 817 == await _shards(me)
        paid = {r["print_id"]: (r["rarity"], r["shards_gained"]) for r in ans["results"]}
        assert {p: v for p, (_r, v) in paid.items()} == {p: PAY[r] for p, (r, _v) in paid.items()}
        assert set(paid) == set(ids)
        state = await _discarded(ids)
        assert all(gone for gone, _v in state.values())
        assert sorted(v for _g, v in state.values()) == [5, 15, 40, 150, 600]
        assert await _batches(me) == [{"batch_key": k, "print_ids": ",".join(sorted(ids)),
                                       "prints": 5, "shards_gained": 810}]
        credits = [s for s in ctx.statements("a") if "UPDATE players SET pc_shards" in _flat(s)]
        assert len(credits) == 1 and "pc_shards = pc_shards + CAST(" in _flat(credits[0])
    _scenario(env, body)


def test_a_replay_of_the_same_key_answers_the_same_total_and_credits_nothing(env):
    """The same key and the same SET of prints (listed in another order):
    replayed, the same total, the balance and the prints untouched, still one
    row (rule R3)."""
    async def body(ctx):
        me = await _player(1, shards=0)
        subject = await _player(2)
        ids = [await _print(me, subject, r) for r in ("rare", "epic", "common")]
        k = _key()
        first = await _batch(ctx, "a", me, k, ids)
        assert first[0] == 200 and first[1]["shards_gained"] == 195, first
        before = (await _shards(me), await _discarded(ids))
        again = await _batch(ctx, "b", me, k, list(reversed(ids)))
        assert again[0] == 200, again
        assert again[1]["replayed"] is True and again[1]["shards_gained"] == 195 and again[1]["prints"] == 3
        assert again[1]["shards"] == 195
        assert sorted((r["print_id"], r["shards_gained"]) for r in again[1]["results"]) == sorted(
            (r["print_id"], r["shards_gained"]) for r in first[1]["results"])
        assert (await _shards(me), await _discarded(ids)) == before
        assert len(await _batches(me)) == 1
        assert not any("UPDATE players SET pc_shards" in _flat(s) for s in ctx.statements("b"))
    _scenario(env, body)


def test_the_same_key_with_other_prints_is_refused_and_changes_nothing(env):
    """A key committed for {a, b} and sent again for {c}: 409 key_reused, c
    live, the balance untouched (rule R4)."""
    async def body(ctx):
        me = await _player(1, shards=3)
        subject = await _player(2)
        a, b, c = [await _print(me, subject, "uncommon") for _ in range(3)]
        k = _key()
        assert (await _batch(ctx, "a", me, k, [a, b]))[0] == 200
        balance = await _shards(me)
        assert _err(await _batch(ctx, "b", me, k, [c])) == (409, "key_reused")
        assert await _shards(me) == balance == 33
        assert (await _discarded([c]))[c] == (False, None)
    _scenario(env, body)


def test_the_cap_refuses_before_anything_is_read_and_the_cap_itself_passes(env):
    """41 prints: 422 too_many and not one statement sent; exactly 40: every
    one discarded (rule R5)."""
    async def body(ctx):
        assert _pc.PC_DISCARD_BATCH_CAP == 40
        me = await _player(1)
        subject = await _player(2)
        ids = [await _print(me, subject, "common") for _ in range(41)]
        status, detail = await _batch(ctx, "over", me, _key(), ids)
        assert (status, detail.get("error"), detail.get("cap")) == (422, "too_many", 40), detail
        assert not any("pc_prints" in s or "players" in s for s in ctx.statements("over"))
        assert all(not gone for gone, _v in (await _discarded(ids)).values())
        status, ans = await _batch(ctx, "at", me, _key(), ids[:40])
        assert status == 200 and ans["prints"] == 40 and ans["shards_gained"] == 200, ans
        assert sum(1 for gone, _v in (await _discarded(ids)).values() if gone) == 40
    _scenario(env, body)


def test_one_print_the_caller_may_not_discard_refuses_the_whole_batch(env):
    """a and b are the caller's, c is another player's, d is already
    discarded: each refuses the whole batch (404 not_owned naming it), and
    nothing is discarded, credited or recorded (rule R6)."""
    async def body(ctx):
        me = await _player(1, shards=1)
        other = await _player(3)
        subject = await _player(2)
        a, b = await _print(me, subject, "rare"), await _print(me, subject, "rare")
        c = await _print(other, subject, "rare")
        d = await _print(me, subject, "epic")
        assert (await _single(ctx, "pre", me, d))[0] == 200
        balance = await _shards(me)
        for bad in (c, d):
            status, detail = await _batch(ctx, "x" + bad[:4], me, _key(), [a, bad, b])
            assert (status, detail.get("error"), detail.get("print_ids")) == (404, "not_owned", [bad]), detail
        assert await _shards(me) == balance
        assert (await _discarded([a, b])) == {a: (False, None), b: (False, None)}
        assert await _batches(me) == []
    _scenario(env, body)


def test_the_body_is_refused_before_the_signature_is_even_checked(env):
    """bad_key (empty and too short: never a NULL key, #147), no_prints,
    bad_print_id, duplicate_print: 422 each, no statement sent."""
    async def body(ctx):
        me = await _player(1)
        subject = await _player(2)
        p = await _print(me, subject, "common")
        cases = [("", [p], "bad_key"), ("short", [p], "bad_key"), ("bad key!x", [p], "bad_key"),
                 (_key(), [], "no_prints"), (_key(), ["not-a-uuid"], "bad_print_id"),
                 (_key(), [p, p.upper()], "duplicate_print")]
        for i, (k, ids, word) in enumerate(cases):
            assert _err(await _batch(ctx, "c%d" % i, me, k, ids, sig="0" * 64)) == (422, word), (k, ids)
            assert ctx.statements("c%d" % i) == []
    _scenario(env, body)

def test_the_body_is_read_under_its_ceiling_and_parsed_only_then(env):
    """Rule R12. A declared length past the ceiling is refused before a byte
    is pulled; a chunked body, or one longer than it declared, the moment it
    passes the ceiling, the rest never pulled; a length that is not a number
    is 400; a body of exactly the ceiling is read, parsed and discarded like
    any other. No refusal sends a statement."""
    async def body(ctx):
        cap = _pc.PC_DISCARD_BATCH_BODY_MAX
        assert cap == 8192
        me = await _player(1)
        subject = await _player(2)
        p = await _print(me, subject, "rare")
        declared = _BodyReq(b" " * (cap + 1))
        assert _err(await _batch(ctx, "decl", me, _key(), [p], sig="0" * 64, req=declared)) == (413, "body_too_large")
        assert declared.pulled == 0, declared.pulled
        chunked = _BodyReq(b" " * (cap * 4), declared=False, chunk=1024)
        assert _err(await _batch(ctx, "chunked", me, _key(), [p], sig="0" * 64, req=chunked)) == (413, "body_too_large")
        assert cap < chunked.pulled <= cap + 1024, chunked.pulled
        longer = _BodyReq(b" " * (cap * 4), length=10, chunk=1024)
        assert _err(await _batch(ctx, "longer", me, _key(), [p], sig="0" * 64, req=longer)) == (413, "body_too_large")
        assert cap < longer.pulled <= cap + 1024, longer.pulled
        bad_length = _BodyReq(_body(_key(), [p]), length="12x")
        assert _err(await _batch(ctx, "badlen", me, _key(), [p], sig="0" * 64, req=bad_length)) == (400, "bad_length")
        assert bad_length.pulled == 0, bad_length.pulled
        for name in ("decl", "chunked", "longer", "badlen"):
            assert ctx.statements(name) == [], name
        key = _key()
        exact = _body(key, [p])
        exact += b" " * (cap - len(exact))
        assert len(exact) == cap
        status, ans = await _batch(ctx, "exact", me, key, [p], req=_BodyReq(exact))
        assert status == 200 and ans["prints"] == 1 and ans["shards_gained"] == PAY["rare"], (status, ans)
        assert (await _discarded([p]))[p] == (True, PAY["rare"])
    _scenario(env, body)


def test_only_a_json_object_with_a_string_key_and_string_ids_is_parsed(env):
    """Rule R12. Not JSON, not UTF-8, nested past the decoder's depth, not an
    object, a key that is not a string, print_ids that is not a list or holds
    a non-string: 422 bad_body each, no statement sent. An absent key or
    absent print_ids reads as empty, so the route's own words name them."""
    async def body(ctx):
        me = await _player(1)
        subject = await _player(2)
        p = await _print(me, subject, "common")
        k = _key()
        bad = [b"not json", b"\xff\xfe", b"[" * 4000 + b"]" * 4000, b"[1, 2]", b'"text"',
               json.dumps({"key": 12345678, "print_ids": [p]}).encode("ascii"),
               json.dumps({"key": k, "print_ids": p}).encode("ascii"),
               json.dumps({"key": k, "print_ids": [p, 7]}).encode("ascii"),
               json.dumps({"key": k, "print_ids": [[p]]}).encode("ascii")]
        for i, raw in enumerate(bad):
            name = "b%d" % i
            assert _err(await _batch(ctx, name, me, k, [p], sig="0" * 64, req=_BodyReq(raw))) == (422, "bad_body"), raw[:40]
            assert ctx.statements(name) == [], name
        no_key = _BodyReq(json.dumps({"print_ids": [p]}).encode("ascii"))
        assert _err(await _batch(ctx, "nokey", me, k, [p], sig="0" * 64, req=no_key)) == (422, "bad_key")
        no_ids = _BodyReq(json.dumps({"key": k}).encode("ascii"))
        assert _err(await _batch(ctx, "noids", me, k, [p], sig="0" * 64, req=no_ids)) == (422, "no_prints")
        assert (await _discarded([p]))[p] == (False, None)
    _scenario(env, body)


def test_on_fastapi_s_own_request_path_the_body_is_read_only_by_the_route(env):
    """Rule R12 on the real request path (#388's method): the route itself,
    mounted on a throwaway FastAPI app whose one dependency override is this
    test's database session, driven by httpx over ASGI. The route declares no
    body parameter, so FastAPI hands the stream on unread: a chunked body far
    past the ceiling is pulled only until it passes the ceiling, and refused;
    a declared one is refused; and a signed batch posted as ordinary JSON is
    served and discards."""
    import httpx
    from fastapi import FastAPI

    route = next(r for r in main.app.routes if getattr(r, "path", "") == "/api/v1/pc/prints/discard-batch")
    assert route.dependant.body_params == [], route.dependant.body_params

    async def body(ctx):
        cap = _pc.PC_DISCARD_BATCH_BODY_MAX
        me = await _player(1)
        subject = await _player(2)
        p = await _print(me, subject, "epic")
        maker = await ctx.session("stack")

        async def _db():
            async with maker() as db:
                yield db

        app = FastAPI()
        app.add_api_route("/api/v1/pc/prints/discard-batch", main.pc_discard_batch, methods=["POST"])
        app.dependency_overrides[main.get_db] = _db
        pulled = [0]

        async def flood():
            for _ in range(64):
                pulled[0] += 1024
                yield b" " * 1024

        path = "/api/v1/pc/prints/discard-batch"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://stack") as client:
            unsigned = {"steam_id": me.steam, "sig": "0" * 64}
            r = await client.post(path, params=unsigned, content=flood())
            assert r.status_code == 413 and r.json()["detail"]["error"] == "body_too_large", r.text
            assert cap < pulled[0] <= cap + 1024 < 64 * 1024, pulled[0]
            r = await client.post(path, params=unsigned, content=b" " * (cap + 1))
            assert r.status_code == 413 and r.json()["detail"]["error"] == "body_too_large", r.text
            assert ctx.statements("stack") == []
            key = _key()
            signed = {"steam_id": me.steam, "sig": _sign(_pc.canon_discard_batch(me.steam, key, [p]))}
            r = await client.post(path, params=signed, json={"key": key, "print_ids": [p]})
            assert r.status_code == 200, r.text
            assert (r.json()["prints"], r.json()["shards_gained"]) == (1, PAY["epic"]), r.text
        assert (await _discarded([p]))[p] == (True, PAY["epic"])
        assert ctx.statements("stack"), "the served request ran on this test's session"
    _scenario(env, body)


def test_a_wrong_signature_and_a_signature_over_another_key_are_refused(env):
    """The signed line carries the key and every id in order: a signature
    over another key, or over the ids in another order, is 403 and nothing
    moves."""
    async def body(ctx):
        me = await _player(1)
        subject = await _player(2)
        a, b = await _print(me, subject, "common"), await _print(me, subject, "rare")
        k = _key()
        other_key = _sign(_pc.canon_discard_batch(me.steam, _key(), [a, b]))
        assert (await _batch(ctx, "s1", me, k, [a, b], sig=other_key))[0] == 403
        swapped = _sign(_pc.canon_discard_batch(me.steam, k, [b, a]))
        assert (await _batch(ctx, "s2", me, k, [a, b], sig=swapped))[0] == 403
        assert all(not g for g, _v in (await _discarded([a, b])).values())
        assert _pc.canon_discard_batch(me.steam, k, [a, b]) == "pcdiscardn:%s:%s:%s,%s" % (me.steam, k, a, b)
    _scenario(env, body)


# ================================================== row 25: locks and races

def test_the_lock_order_is_the_players_row_then_the_prints_in_id_order(env):
    """In the batch's own statement log: the players row FOR NO KEY UPDATE,
    then the gate's SELECT ... ORDER BY id FOR NO KEY UPDATE, then the first
    conditional discard, then the credit, then the key's row (rule R8)."""
    async def body(ctx):
        me = await _player(1)
        subject = await _player(2)
        ids = [await _print(me, subject, "common") for _ in range(4)]
        assert (await _batch(ctx, "a", me, _key(), ids))[0] == 200
        log = [_flat(s) for s in ctx.statements("a")]

        def first(pred):
            hits = [i for i, s in enumerate(log) if pred(s)]
            assert hits, "statement missing from the batch's log"
            return hits[0]
        lock = first(lambda s: s.startswith("SELECT id FROM players") and s.endswith("FOR NO KEY UPDATE"))
        gate = first(lambda s: "FROM pc_prints" in s and "ORDER BY id FOR NO KEY UPDATE" in s)
        disc = first(lambda s: s.startswith("UPDATE pc_prints SET discarded_at = now()"))
        cred = first(lambda s: s.startswith("UPDATE players SET pc_shards = pc_shards +"))
        rec = first(lambda s: s.startswith("INSERT INTO pc_shard_batches"))
        assert lock < gate < disc < cred < rec, (lock, gate, disc, cred, rec)
        assert sum(1 for s in log if s.startswith("UPDATE pc_prints SET discarded_at = now()")) == 4
    _scenario(env, body)


def _first(log, pred, what):
    hits = [i for i, s in enumerate(log) if pred(s)]
    assert hits, "statement missing from the batch's log: " + what
    return hits[0]


def test_the_key_is_locked_between_the_players_row_and_the_prints(env):
    """Finding 1, the statement trace: on a first submission AND on a replay,
    the batch takes the players row FOR NO KEY UPDATE, then the advisory
    lock on the (player, key) value, then the key's row FOR NO KEY UPDATE,
    and only then (first submission) the prints; never FOR UPDATE (#202)."""
    async def body(ctx):
        me = await _player(1)
        subject = await _player(2)
        ids = [await _print(me, subject, "common") for _ in range(3)]
        k = _key()
        assert (await _batch(ctx, "a", me, k, ids))[0] == 200
        again = await _batch(ctx, "b", me, k, ids)
        assert again[0] == 200 and again[1]["replayed"] is True, again
        for name, prints in (("a", True), ("b", False)):
            log = [_flat(s) for s in ctx.statements(name)]
            players = _first(log, lambda s: s.startswith("SELECT id FROM players") and s.endswith("FOR NO KEY UPDATE"),
                             "the players row lock")
            value = _first(log, lambda s: s.startswith("SELECT pg_advisory_xact_lock(hashtextextended("),
                           "the advisory lock on the key's value")
            row = _first(log, lambda s: "FROM pc_shard_batches" in s and s.startswith("SELECT print_ids"),
                         "the key row read")
            assert log[row].endswith("FOR NO KEY UPDATE"), "the key row is read without its lock: " + log[row]
            assert players < value < row, (name, players, value, row)
            assert not any(s.endswith("FOR UPDATE") and not s.endswith("NO KEY UPDATE") for s in log), name
            gate = [i for i, s in enumerate(log) if "FROM pc_prints" in s and s.endswith("ORDER BY id FOR NO KEY UPDATE")]
            if prints:
                assert gate and row < gate[0], (name, row, gate)
            else:
                assert not gate, "a replay locked the prints"
    _scenario(env, body)


def test_two_first_submissions_of_one_key_credit_once(env):
    """Finding 1, concurrency: two sessions submit one key for one list at
    once. The first is paused after its gate (it holds the players row, the
    key's value and the prints); the second WAITS on a lock; once the first
    commits the second answers the recorded result (replayed) and credits
    nothing: one row, one credit."""
    async def body(ctx):
        me = await _player(1, shards=0)
        subject = await _player(2)
        ids = [await _print(me, subject, "epic"), await _print(me, subject, "uncommon")]
        k = _key()
        g = ctx.gate("first", "_pc_discard_gate", "post")
        t1 = asyncio.create_task(_batch(ctx, "first", me, k, ids), name="first")
        await ctx.reached(g, "the first submission's gate")
        t2 = asyncio.create_task(_batch(ctx, "second", me, k, list(reversed(ids))), name="second")
        assert await ctx.lock_or_done("second", t2) == "lock"
        g.go.set()
        first, second = await t1, await t2
        assert first[0] == 200 and first[1]["replayed"] is False and first[1]["shards_gained"] == 165, first
        assert second[0] == 200 and second[1]["replayed"] is True and second[1]["shards_gained"] == 165, second
        assert await _shards(me) == 165
        assert [(r["batch_key"], r["prints"], r["shards_gained"]) for r in await _batches(me)] == [(k, 2, 165)]
    _scenario(env, body)


def test_a_row_for_the_key_that_appears_anyway_answers_409_and_rolls_back(env):
    """Finding 1, the last line of defence: a row for the key written by a
    transaction outside the route's locks (still uncommitted when the batch
    reaches its record) makes the batch wait on the primary key; once that
    row commits, the batch answers 409 key_reused -- never a 500 -- and
    everything it did is rolled back: the prints live, the balance as it
    was, only the other row."""
    async def body(ctx):
        me = await _player(1, shards=6)
        subject = await _player(2)
        ids = [await _print(me, subject, "rare"), await _print(me, subject, "common")]
        k = _key()
        other = await _connect("other")
        try:
            tx = other.transaction()
            await tx.start()
            await other.execute("INSERT INTO pc_shard_batches (player_id, batch_key, print_ids, prints, shards_gained) "
                                "VALUES ($1::uuid, $2, $3, 1, 5)", me.pid, k, str(uuid.uuid4()))
            t = asyncio.create_task(_batch(ctx, "a", me, k, ids), name="a")
            assert await ctx.lock_or_done("a", t) == "lock"
            await tx.commit()
            answer = await t
        finally:
            await other.close()
        assert _err(answer) == (409, "key_reused"), answer
        assert await _discarded(ids) == {i: (False, None) for i in ids}
        assert await _shards(me) == 6
        assert [(r["batch_key"], r["prints"]) for r in await _batches(me)] == [(k, 1)]
    _scenario(env, body)


def test_a_single_discard_racing_a_batch_over_the_same_print_pays_once(env):
    """The batch is paused after its gate (it holds the players row and the
    prints); a single discard of one of its prints waits on a lock, and once
    the batch commits it is refused (not_owned). The print paid once, the
    balance holds exactly the batch's total."""
    async def body(ctx):
        me = await _player(1, shards=0)
        subject = await _player(2)
        ids = [await _print(me, subject, "legendary"), await _print(me, subject, "common")]
        g = ctx.gate("batch", "_pc_discard_gate", "post")
        t1 = asyncio.create_task(_batch(ctx, "batch", me, _key(), ids), name="batch")
        await ctx.reached(g, "the batch's gate")
        t2 = asyncio.create_task(_single(ctx, "single", me, ids[0]), name="single")
        assert await ctx.lock_or_done("single", t2) == "lock"
        g.go.set()
        first, second = await t1, await t2
        assert first[0] == 200 and first[1]["shards_gained"] == 605, first
        assert _err(second) == (404, "not_owned")
        assert await _shards(me) == 605
        assert (await _discarded(ids))[ids[0]] == (True, 600)
    _scenario(env, body)


def test_a_missing_table_answers_503_before_any_lock_or_write(env):
    """Migration 361 not run on this box (the table dropped for the test and
    restored by the next reset): 503 shard_batch_unavailable, and the
    batch's statement trace holds the table check and nothing that locks --
    no advisory lock (the verified actor's shared identity lock included,
    round 2 finding 2), no row lock -- and nothing is discarded (rule R9)."""
    async def body(ctx):
        me = await _player(1, shards=2)
        subject = await _player(2)
        p = await _print(me, subject, "rare")
        await _q("DROP TABLE pc_shard_batches")
        assert _err(await _batch(ctx, "a", me, _key(), [p])) == (503, "shard_batch_unavailable")
        trace = [_flat(s) for s in ctx.statements("a")]
        assert any("to_regclass('pc_shard_batches')" in s for s in trace), trace
        assert not any("pg_advisory" in s for s in trace), "a lock ran before the 503: %r" % trace
        assert not any(re.search(r"FOR (NO KEY |KEY )?(UPDATE|SHARE)", s) for s in trace), trace
        assert (await _discarded([p]))[p] == (False, None) and await _shards(me) == 2
        # the single route does not depend on the table
        assert (await _single(ctx, "b", me, p))[0] == 200
    _scenario(env, body)


# ======================================= row 25: the gate both routes share

def test_both_discard_routes_refuse_through_the_one_gate(env):
    """Another player's print and an already discarded one: refused by the
    single route and by the batch route alike (404 not_owned). The brief's
    equipped-print refusal has no state to read (no print carries one; notes
    F1), so these are the gate's refusals, asserted on BOTH routes, and the
    structure test below pins that both routes call the one gate."""
    async def body(ctx):
        me = await _player(1)
        other = await _player(3)
        subject = await _player(2)
        theirs = await _print(other, subject, "epic")
        spent = await _print(me, subject, "common")
        assert (await _single(ctx, "pre", me, spent))[0] == 200
        for bad in (theirs, spent):
            assert _err(await _single(ctx, "s" + bad[:4], me, bad)) == (404, "not_owned")
            assert _err(await _batch(ctx, "b" + bad[:4], me, _key(), [bad])) == (404, "not_owned")
        assert (await _discarded([theirs]))[theirs] == (False, None)
    _scenario(env, body)


def test_both_routes_call_the_gate_once_and_only_after_the_players_lock():
    """Structure, per FUNCTION (#279): each discard route calls
    _pc_discard_gate exactly once, after its players-row lock and before its
    first conditional discard; the gate locks FOR NO KEY UPDATE (never FOR
    UPDATE, #202) in id order and filters on owner and liveness."""
    for name in ("pc_discard_print", "pc_discard_batch"):
        code = _code(_fn_src(name))
        assert code.count("_pc_discard_gate (") == 1, name
        lock = code.index("FOR NO KEY UPDATE")
        gate = code.index("_pc_discard_gate (")
        disc = code.index("UPDATE pc_prints SET discarded_at = now()")
        assert lock < gate < disc, name
    gate_sql = _flat(main._PC_DISCARD_GATE_SQL)
    assert gate_sql.endswith("ORDER BY id FOR NO KEY UPDATE") and " FOR UPDATE" not in gate_sql
    assert "owner_player_id = CAST(:pid AS uuid) AND discarded_at IS NULL" in gate_sql
    assert "_PC_DISCARD_GATE_SQL" in _code(_fn_src("_pc_discard_gate"))


def test_the_credit_is_a_delta_and_the_discard_conditional_in_the_batch_route():
    """Structure, per function: the batch's credit is `pc_shards = pc_shards
    + ...` and nowhere an absolute write of pc_shards (#326); its discard is
    the single route's conditional UPDATE, statement for statement."""
    code = _flat(_code(_fn_src("pc_discard_batch")))
    assert code.count("pc_shards = pc_shards + CAST(:value AS integer)") == 1
    assert not re.search(r"pc_shards\s*=\s*CAST\(", code)
    single = _flat(_code(_fn_src("pc_discard_print")))
    stmt = ("UPDATE pc_prints SET discarded_at = now(), discard_shards = CAST(:value AS integer) "
            "WHERE id = CAST(:print AS uuid) AND owner_player_id = CAST(:pid AS uuid) AND discarded_at IS NULL "
            "RETURNING id")
    assert code.count(stmt) == 1 and single.count(stmt) == 1


# ========================== row 25: deletion and durability of the key's rows

def test_the_data_deletion_removes_the_players_batch_rows_by_name():
    """#437: the players row is anonymised, so the CASCADE never fires; the
    deletion endpoint deletes the rows by name, once, guarded only on the
    table's existence."""
    code = _flat(_code(_fn_src("delete_player_data")))
    assert code.count("DELETE FROM pc_shard_batches WHERE player_id = :pid") == 1
    guard = code.index("to_regclass('pc_shard_batches') IS NOT NULL")
    assert guard < code.index("DELETE FROM pc_shard_batches WHERE player_id = :pid")


def test_nothing_in_the_api_deletes_batch_rows_but_the_data_deletion():
    """The key's rows are kept (asks-b round 2, finding 1): across every api
    module, the one statement that deletes from pc_shard_batches is the data
    deletion's, and nothing truncates the table or names it in a retention
    predicate."""
    hits = []
    for f in sorted((BACKEND / "api").glob("*.py")):
        src = f.read_text(encoding="utf-8")
        for m in re.finditer(r"(?is)(DELETE\s+FROM|TRUNCATE(\s+TABLE)?)\s+pc_shard_batches\b", src):
            hits.append((f.name, src.count("\n", 0, m.start()) + 1))
    assert len(hits) == 1 and hits[0][0] == "main.py", hits
    code = _flat(_code(_fn_src("delete_player_data")))
    assert code.count("DELETE FROM pc_shard_batches WHERE player_id = :pid") == 1
    assert "pc_shard_batches" not in _code(_fn_src("_pc_snapshot_janitor_step"))


def test_a_key_older_than_thirty_days_survives_the_real_janitor_and_still_refuses_another_list(env):
    """Key K commits for list A; its row is aged 400 days; the ACTUAL
    janitor step (_pc_snapshot_janitor_step, on this schema, stopped after
    its retention and rollover by the snapshot due-check) runs; the row is
    still there, K over another owned live list B is 409 key_reused with B
    live and the balance untouched, and K over A still answers the recorded
    result without crediting (finding 1: durable idempotency)."""
    import database

    async def body(ctx):
        me = await _player(1, shards=4)
        subject = await _player(2)
        a = [await _print(me, subject, "rare"), await _print(me, subject, "common")]
        b = [await _print(me, subject, "legendary")]
        k = _key()
        first = await _batch(ctx, "a", me, k, a)
        assert first[0] == 200 and first[1]["shards_gained"] == 45, first
        await _q("UPDATE pc_shard_batches SET created_at = now() - interval '400 days' WHERE player_id = $1::uuid",
                 me.pid)
        maker = await ctx.session("janitor")
        env.monkeypatch.setattr(database, "async_session", maker)

        async def _not_due(_db):
            return None
        env.monkeypatch.setattr(main, "_pc_snapshot_due", _not_due)
        await main._pc_snapshot_janitor_step()
        assert any("pc_events" in _flat(s) for s in ctx.statements("janitor")), "the janitor step did not run"
        assert [(r["batch_key"], r["prints"], r["shards_gained"]) for r in await _batches(me)] == [(k, 2, 45)]
        balance = await _shards(me)
        assert balance == 49
        assert _err(await _batch(ctx, "b", me, k, b)) == (409, "key_reused")
        assert (await _discarded(b))[b[0]] == (False, None) and await _shards(me) == balance
        again = await _batch(ctx, "c", me, k, a)
        assert again[0] == 200 and again[1]["replayed"] is True and again[1]["shards_gained"] == 45, again
        assert await _shards(me) == balance and len(await _batches(me)) == 1
    _scenario(env, body)
