"""Card trading (migration 353, V8 sections 2-3, 8.3 and 10), the server half,
EXECUTED against a real PostgreSQL.

Every guard of the design's mutation table (E 10, M1-M55; M28 is the replica
write gate, confirmed structurally, and M56/M57 are census controls over the
design document itself, read and not run) is a named test below, written as
the row's CONTROL: the behaviour the guard produces. The mutation runs remove
each guard in turn, on a frozen tree, and record the test's RED output in the
build notes; the tests themselves never know which mutant is applied.

THE DATABASE. One schema, pc_trades_t, in the database PC_TRADES_TEST_PG_DSN
names. Every migration numbered up to 352 is replayed into it statement by
statement (each file's own transaction honoured, a statement that fails on an
empty database recorded, not fatal), the ORM creates the tables no migration
creates, the replay runs again, the ORM's missing columns are added -- all
but the ones 353 itself adds to older tables, which the ORM maps since F63
and which 353 alone may create -- then every migration numbered above 353
is replayed the same way (the routes this module drives read their objects:
358's players.active_dance_id and pc_motions), and a statement of theirs that
fails fails the build, and 353 is applied whole: the pre-353 schema (every
object but 353's) is fingerprinted, then the full one. None of the later
files touches an object 353 creates, so replaying them before it leaves the
schema 353 finds and the one it leaves as they are in numbered order; one
that did would fail its replay here.
The build is reused while the migrations, models.py and this harness are
unchanged and the schema still fingerprints as built; anything else rebuilds
it. Before any DROP or CREATE the harness CENSUSES every schema the role's
search path reaches and refuses when an object outside pc_trades_t depends
on one inside it (what DROP SCHEMA ... CASCADE would also remove); after the
build it re-censuses and requires those schemas unchanged. Every connection
the harness and the routes use has pc_trades_t as its ONLY search path entry.

States. "full" is the built schema. "walk4" drops only
pc_trades_one_open_per_pair (E 3.9, walk 4: the probe reads `partial`).
"walk5" drops the six removable objects and keeps pc_prints.acquired_by_trade
(walk 5). "missing" is the pre-353 database: the six, the column, the new
functions, and pc_prints_immutable re-created at 308's body -- asserted to
fingerprint exactly as the replay left the schema before 353 ran. Each test
that leaves "full" restores it by re-running 353 (additive and re-runnable)
and asserts the full fingerprint again.

Routes are called as the functions FastAPI would call, one database session
per request, each client on its own connection (application_name pct_<name>)
so a test can see who waits on a lock in pg_stat_activity; interleavings are
driven by pause points wrapped around the module-level helpers each step
calls, keyed on the asyncio task's name, so only the named client pauses.
Fixture timestamps a trigger forbids a route to move are backdated on a
separate connection under session_replication_role = replica.

RUNNING IT
----------
    PC_TRADES_TEST_PG_DSN="postgresql://postgres@127.0.0.1:55432/pc_trades_lane" \\
        python -m pytest backend/tests/test_pc_trades.py -q

Without the DSN every database test FAILS by name rather than skipping (a
skip is a run that proved nothing while reporting exit 0). Set
PC_TRADES_TEST_PG_OPTOUT=1 to waive the coverage deliberately and the
failures become named skips. The pure tests run either way.

There is no pytest-asyncio in this suite: each test is a sync function that
runs one coroutine.
"""
import asyncio
import hashlib
import hmac
import os
import re
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND / "api"))
sys.path.insert(0, str(HERE))

import database  # noqa: E402
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

DSN_VAR = "PC_TRADES_TEST_PG_DSN"
OPTOUT_VAR = "PC_TRADES_TEST_PG_OPTOUT"
_RAW_DSN = os.environ.get(DSN_VAR) or ""
DSN_PLAIN = re.sub(r"^postgres(?:ql)?(?:\+asyncpg)?://", "postgresql://", _RAW_DSN) if _RAW_DSN else ""
DSN_ASYNC = DSN_PLAIN.replace("postgresql://", "postgresql+asyncpg://", 1) if DSN_PLAIN else ""
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"

SCHEMA = "pc_trades_t"
HARNESS_TABLE = "pc_trades_harness"
HARNESS_VERSION = "3"
SQL_DIR = BACKEND / "sql"
MIGRATION = SQL_DIR / "353_pc_trades.sql"
MIGRATION_NUMBER = 353

SECRET = "pc-trades-test-mod-secret"
ADMIN_SECRET = "pc-trades-test-admin-secret"
# Synthetic ids inside the individual SteamID64 range
# (76561197960265728 .. 76561202255233023) and far from any live account.
STEAM_BASE = "765612022552"
ADMIN_N = 109
REQ = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"),
                      query_params={}, url=SimpleNamespace(path="/"))

# The trading objects no statement of a route may name before its schema
# gate has passed (M34-M40: "nothing read").
TRADING_NAMES = ("pc_trades", "pc_trade_holds", "pc_trade_spent_nonces", "pc_trades_open",
                 "pc_trades_generation", "acquired_by_trade")


def _require_pg():
    """Fail, not skip, when the DSN is unset (see the module docstring)."""
    if DSN_PLAIN and asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: the live-PostgreSQL trading coverage is "
                    "deliberately waived for this run." % (DSN_VAR, OPTOUT_VAR))
    if asyncpg is None:
        pytest.fail("asyncpg is not installed, so no trade route ran against migration "
                    "353. Install it, or set %s=1 to waive the coverage." % OPTOUT_VAR)
    pytest.fail(
        "%s is unset, so no trade route, no migration-353 trigger and no interleaving of "
        "the lock lattice ran against a server -- the subject of this file. Point it at "
        "a throwaway database (see the module docstring), or set %s=1 to waive the "
        "coverage deliberately." % (DSN_VAR, OPTOUT_VAR))


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


def _numbered(upto=None, above=None):
    files = sorted(p for p in SQL_DIR.glob("*.sql") if re.match(r"^\d{3}_", p.name))
    if upto is not None:
        files = [p for p in files if int(p.name[:3]) <= upto]
    if above is not None:
        files = [p for p in files if int(p.name[:3]) > above]
    return files


def _sign(canon):
    return hmac.new(SECRET.encode(), canon.encode(), hashlib.sha256).hexdigest()


def _admin_sign(admin_steam, action, target):
    return hmac.new(ADMIN_SECRET.encode(), main._admin_canonical(admin_steam, action, target).encode(),
                    hashlib.sha256).hexdigest()


def _digest(steam, give, to, get):
    return _pc.trade_digest(_pc.trade_items(steam, give, to, get))


def _nonce():
    return "n" + uuid.uuid4().hex[:20]


def _steam(n):
    return STEAM_BASE + "%05d" % n


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
# that depends on an object inside it and does not itself live inside it. A
# dependent's schema is read through the relation that owns it (a view's
# rule, a column default, a trigger); a dependent of any other kind counts as
# outside, so an unrecognised one refuses rather than passes.
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

_RELATIONS_SQL = """
SELECT n.nspname || '.' || c.relname || ':' || c.relkind::text
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = ANY($1::text[])
 ORDER BY 1
"""


async def _connect(app="harness", replica=False):
    conn = await asyncpg.connect(DSN_PLAIN, server_settings={
        "search_path": '"%s"' % SCHEMA, "application_name": "pct_" + app})
    if replica:
        await conn.execute("SET session_replication_role = replica")
    return conn


async def _census():
    """On a connection with the ROLE'S OWN search path (no override): the
    relations of every schema that path reaches ("$user" resolved, pg_catalog
    and this harness's schema aside), and every object outside pc_trades_t
    that depends on one inside it. Refuses on the latter."""
    conn = await asyncpg.connect(DSN_PLAIN, server_settings={"application_name": "pct_census"})
    try:
        path = await conn.fetchval("SELECT current_setting('search_path')")
        user = await conn.fetchval("SELECT current_user")
        names = {user if s.strip().strip('"') == "$user" else s.strip().strip('"') for s in path.split(",")}
        names |= set(await conn.fetchval("SELECT current_schemas(true)"))
        others = sorted(names - {"pg_catalog", SCHEMA, ""})
        relations = [r[0] for r in await conn.fetch(_RELATIONS_SQL, others)]
        foreign = [r[0] for r in await conn.fetch(_FOREIGN_DEPENDENTS_SQL, SCHEMA)]
    finally:
        await conn.close()
    if foreign:
        pytest.fail("REFUSED: objects outside %s depend on objects inside it, so dropping it "
                    "would remove them too: %s" % (SCHEMA, foreign[:10]))
    return {"schemas": others, "relations": relations}


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
    for p in _numbered():
        h.update(p.name.encode())
        h.update(p.read_bytes())
    h.update((BACKEND / "api" / "models.py").read_bytes())
    h.update(HARNESS_VERSION.encode())
    h.update(split_sql.__code__.co_code)
    return h.hexdigest()


async def _orm(fn):
    engine = create_async_engine(DSN_ASYNC, poolclass=NullPool, connect_args={"server_settings": {
        "search_path": '"%s"' % SCHEMA, "application_name": "pct_orm"}})
    try:
        async with engine.begin() as c:
            return await fn(c)
    finally:
        await engine.dispose()


async def _create_all(c):
    await c.run_sync(models.Base.metadata.create_all)


def _353_added_columns():
    """(table, column) for every column 353 adds to an older table. The ORM
    maps players' two since F63; were the harness to add them before 353
    ran, the pre-353 fingerprint would carry them and "missing" would not be
    the database 353 has not reached."""
    found = set(re.findall(r"(?im)^\s*ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+(\w+)",
                           MIGRATION.read_text(encoding="utf-8")))
    assert {("players", "pc_trades_open"), ("players", "pc_trades_generation"),
            ("pc_prints", "acquired_by_trade")} <= found, found
    return found


async def _orm_columns(c):
    from sqlalchemy.schema import CreateColumn
    added, skip = [], _353_added_columns()
    for table in models.Base.metadata.sorted_tables:
        have = {r[0] for r in (await c.exec_driver_sql(
            "SELECT attname FROM pg_attribute WHERE attrelid = to_regclass('\"%s\".\"%s\"') "
            "AND attnum > 0 AND NOT attisdropped" % (SCHEMA, table.name))).all()}
        for col in table.columns:
            if col.name not in have and (table.name, col.name) not in skip:
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
        before = await _census()
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
        count, failures = await _replay(conn, _numbered(above=MIGRATION_NUMBER))
        assert not failures, ("a migration above 353 failed its replay before 353", failures)
        fp_pre = await _fingerprint(conn)
        await conn.execute(MIGRATION.read_text(encoding="utf-8"))
        fp_full = await _fingerprint(conn)
        empty = []
        for t in await _tables(conn):
            if not await conn.fetchval('SELECT EXISTS (SELECT 1 FROM "%s"."%s")' % (SCHEMA, t)):
                empty.append(t)
        await conn.execute('CREATE TABLE "%s"."%s" (key text, fp_pre text, fp_full text, empty_tables text[])'
                           % (SCHEMA, HARNESS_TABLE))
        await conn.execute('INSERT INTO "%s"."%s" VALUES ($1, $2, $3, $4)' % (SCHEMA, HARNESS_TABLE),
                           key, fp_pre, fp_full, empty)
        after = await _census()
        assert after == before, ("the build changed a schema outside %s" % SCHEMA, before, after)
        return {"fp_pre": fp_pre, "fp_full": fp_full, "empty": empty, "reused": False}
    finally:
        await conn.close()


def _308_print_trigger():
    """308's pc_prints_immutable function and trigger, as 308 writes them:
    the latest definition before 353 (321 only disables and re-enables it)."""
    stmts = [s for s in split_sql((SQL_DIR / "308_player_cards.sql").read_text(encoding="utf-8"))
             if "pc_prints_immutable" in s]
    assert len(stmts) == 3, stmts
    return stmts


async def _set_state(conn, state, build):
    """Move the schema from "full" to `state` (see the module docstring)."""
    q = '"%s".' % SCHEMA
    if state == "full":
        return
    if state == "walk4":
        await conn.execute("DROP INDEX %spc_trades_one_open_per_pair" % q)
        return
    await conn.execute("DROP TABLE %spc_trade_holds, %spc_trades, %spc_trade_spent_nonces" % (q, q, q))
    await conn.execute("ALTER TABLE %splayers DROP COLUMN pc_trades_open, DROP COLUMN pc_trades_generation" % q)
    if state == "walk5":
        return
    assert state == "missing", state
    for stmt in _308_print_trigger():
        await conn.execute(stmt)
    await conn.execute("DROP TRIGGER pc_cards_immutable ON %spc_cards" % q)
    for fn in ("pc_cards_immutable", "pc_trades_guard", "pc_trades_release_holds",
               "pc_trades_no_executing_commit", "pc_trade_holds_guard"):
        await conn.execute("DROP FUNCTION %s%s()" % (q, fn))
    await conn.execute("ALTER TABLE %spc_prints DROP COLUMN acquired_by_trade" % q)
    assert await _fingerprint(conn) == build["fp_pre"], (
        "the 'missing' state is not the schema the replay left before 353 ran")


async def _restore(conn, build):
    if await _fingerprint(conn) == build["fp_full"]:
        return
    await conn.execute(MIGRATION.read_text(encoding="utf-8"))
    assert await _fingerprint(conn) == build["fp_full"], "re-running 353 did not restore the full schema"


# The sequences owned by the named tables' columns (serial or identity) that
# have been drawn from: what TRUNCATE ... RESTART IDENTITY would restart.
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
    """Every table that was empty at build empty again, every sequence they
    own restarted, the schema full. The tables that hold rows are found by
    one EXISTS probe and emptied by DELETE with triggers and foreign keys
    off (session_replication_role = replica; every table the probe names is
    emptied whole, and no table outside the empty-at-build set references
    one inside it -- the TRUNCATE this replaces required that), so a test
    pays for the few tables it wrote rather than re-creating the files of
    every empty table."""
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
def env(pg_build, monkeypatch):
    """A database test's environment: the full schema, empty of data, the
    process's found-schema cache cleared, the secrets and the session proof
    stubbed, and the janitor's session factory pointed at the schema."""
    _run(_reset(pg_build))
    monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_FOUND", False)
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    monkeypatch.setattr(main, "ADMIN_HMAC_SECRET", ADMIN_SECRET)
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)

    async def _session_ok(*_a, **_k):
        return True
    monkeypatch.setattr(main, "_strict_steam_session_ok", _session_ok)
    return SimpleNamespace(build=pg_build, monkeypatch=monkeypatch)


# ------------------------------------------------------------- the clients

class Gate:
    def __init__(self):
        self.reached = asyncio.Event()
        self.go = asyncio.Event()


class Ctx:
    """One test's clients: an engine per client name (its own connection,
    application_name pct_<name>), one ordered log of every statement any
    client sent, pause points, and a monitor connection."""

    def __init__(self, env):
        self.env = env
        self.engines = {}
        self.log = []
        self.gates = {}
        self.wrapped = set()
        self.monitor = None
        self.fixture_names = {}

    async def session(self, name):
        eng = self.engines.get(name)
        if eng is None:
            eng = create_async_engine(DSN_ASYNC, poolclass=NullPool, connect_args={"server_settings": {
                "search_path": '"%s"' % SCHEMA, "application_name": "pct_" + name}})
            async with eng.connect() as c:
                await c.exec_driver_sql("SELECT 1")

            def _rec(conn, cursor, statement, parameters, context, executemany, _name=name):
                self.log.append((len(self.log), _name, statement))
            event.listen(eng.sync_engine, "before_cursor_execute", _rec)
            self.engines[name] = eng
        return async_sessionmaker(eng, expire_on_commit=False)

    def statements(self, name):
        return [s for _i, n, s in self.log if n == name]

    def first_index(self, name, pattern):
        for i, n, s in self.log:
            if n == name and re.search(pattern, s):
                return i
        return None

    async def close(self):
        for eng in self.engines.values():
            await eng.dispose()
        if self.monitor is not None:
            await self.monitor.close()

    # -- pause points ---------------------------------------------------------
    def gate(self, task, fn_name, phase="post"):
        """Pause the task named `task` the first time it calls main.<fn_name>,
        before ("pre") or after ("post") the call. Returns the Gate: wait on
        .reached, release with .go.set()."""
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

    # -- who waits ------------------------------------------------------------
    async def waiting(self, name):
        if self.monitor is None:
            self.monitor = await _connect("monitor")
        rows = await self.monitor.fetch(
            "SELECT wait_event_type FROM pg_stat_activity WHERE application_name = $1", "pct_" + name)
        return any(r["wait_event_type"] == "Lock" for r in rows)

    async def lock_or_done(self, name, task, timeout=8.0):
        """'lock' once the client waits on a lock, 'done' once its task has
        finished; fails the test if neither happens in `timeout` seconds."""
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


def _task(coro, name):
    return asyncio.create_task(coro, name=name)


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


# ------------------------------------------------------------ fixture data

# One fixture connection per scenario and replication role, closed when the
# scenario ends (each scenario runs in its own event loop). Only the
# scenario's own task calls _q, one statement at a time.
_FIXTURE_CONNS = {}


async def _q(sql, *args, replica=False):
    key = (id(asyncio.get_running_loop()), replica)
    conn = _FIXTURE_CONNS.get(key)
    if conn is None or conn.is_closed():
        conn = _FIXTURE_CONNS[key] = await _connect("fixture_q", replica=replica)
    return await conn.fetch(sql, *args)


async def _close_fixture_conns():
    loop = id(asyncio.get_running_loop())
    for key in [k for k in _FIXTURE_CONNS if k[0] == loop]:
        await _FIXTURE_CONNS.pop(key).close()


async def _val(sql, *args):
    rows = await _q(sql, *args)
    return rows[0][0] if rows else None


async def _player(ctx, n, *, series=3, mod_days=30, public=True, name=None):
    """A player: a pool member (mod seen `mod_days` ago; None = never), with
    `series` completed ranked series against the shared opponent."""
    maker = await ctx.session("fixture")
    steam = _steam(n)
    async with maker() as db:
        p = models.Player(steam_id=steam, display_name=name or ("Trader %d" % n))
        db.add(p)
        await db.flush()
        await db.execute(text("""
            UPDATE players SET mod_seen_at = CASE WHEN CAST(:days AS integer) IS NULL THEN NULL
                                                  ELSE now() - make_interval(days => CAST(:days AS integer)) END,
                               pc_collection_public = CAST(:pub AS boolean)
             WHERE id = CAST(:pid AS uuid)"""), {"days": mod_days, "pub": public, "pid": str(p.id)})
        if series:
            opp = ctx.fixture_names.get("opponent")
            if opp is None:
                o = models.Player(steam_id=_steam(199), display_name="Opponent")
                db.add(o)
                await db.flush()
                opp = ctx.fixture_names["opponent"] = o.id
            for _ in range(series):
                db.add(models.RankedSeries(player1_id=p.id, player2_id=opp, status="completed",
                                           completed_at=None))
        await db.commit()
        return SimpleNamespace(n=n, steam=steam, pid=str(p.id))


async def _print(ctx, owner, subject, rarity="legendary"):
    """One print of `subject`'s card, owned by `owner`."""
    return str(await _val("""
        WITH card AS (
            INSERT INTO pc_cards (subject_player_id, edition_id)
            VALUES ($2::uuid, (SELECT id FROM pc_editions WHERE ended_at IS NULL ORDER BY id LIMIT 1))
            ON CONFLICT (subject_player_id, edition_id, variant) DO UPDATE SET variant = EXCLUDED.variant
            RETURNING id)
        INSERT INTO pc_prints (card_id, owner_player_id, snapshot_id, rarity, pool_rank, source)
        SELECT id, $1::uuid, 1, $3, 1, 'pack' FROM card RETURNING id""", owner.pid, subject.pid, rarity))


async def _admin(ctx):
    maker = await ctx.session("fixture")
    async with maker() as db:
        if await db.get(models.AdminUser, _steam(ADMIN_N)) is None:
            db.add(models.AdminUser(steam_id=_steam(ADMIN_N)))
            await db.commit()
    return _steam(ADMIN_N)


async def _ban(ctx, player):
    admin = await _admin(ctx)
    maker = await ctx.session("fixture")
    async with maker() as db:
        db.add(models.PlayerBan(steam_id=player.steam, reason="test", banned_by_steam_id=admin))
        await db.commit()


async def _owner(print_id):
    """The print's owner id as text; None when the print row is gone."""
    v = await _val("SELECT owner_player_id FROM pc_prints WHERE id = $1::uuid", print_id)
    return None if v is None else str(v)


async def _status(trade_id):
    return await _val("SELECT status FROM pc_trades WHERE id = $1::uuid", trade_id)


async def _shards(player):
    return await _val("SELECT pc_shards FROM players WHERE id = $1::uuid", player.pid)


# -------------------------------------------------------------- the routes

async def propose(ctx, name, actor, to, give, get, *, nonce=None, sig=None, digest=None):
    nonce = nonce or _nonce()
    digest = digest or _digest(actor.steam, give, to.steam, get)
    sig = sig or _sign(_pc.canon_trade(actor.steam, nonce, "propose", to.steam, digest))
    return await _call(ctx, name, main.pc_trade_propose, request=REQ, steam_id=actor.steam, sig=sig,
                       nonce=nonce, to=to.steam, give=",".join(give), get=",".join(get), digest=digest)


async def _act(ctx, name, fn, action, actor, trade_id, digest, nonce, sig):
    nonce = nonce or _nonce()
    sig = sig or _sign(_pc.canon_trade(actor.steam, nonce, action, trade_id, digest))
    return await _call(ctx, name, fn, request=REQ, steam_id=actor.steam, sig=sig, nonce=nonce,
                       trade_id=trade_id, digest=digest)


async def accept(ctx, name, actor, trade, *, nonce=None, sig=None):
    return await _act(ctx, name, main.pc_trade_accept, "accept", actor, trade["trade_id"], trade["digest"],
                      nonce, sig)


async def decline(ctx, name, actor, trade, *, nonce=None):
    return await _act(ctx, name, main.pc_trade_decline, "decline", actor, trade["trade_id"], trade["digest"],
                      nonce, None)


async def cancel(ctx, name, actor, trade, *, nonce=None):
    return await _act(ctx, name, main.pc_trade_cancel, "cancel", actor, trade["trade_id"], trade["digest"],
                      nonce, None)


async def read_trades(ctx, name, actor, view="summary"):
    return await _call(ctx, name, main.pc_trades, request=REQ, steam_id=actor.steam,
                       sig=_sign(_pc.canon_read(actor.steam, "trades", view)), view=view)


async def reverse(ctx, name, trade_id, reason="test"):
    admin = await _admin(ctx)
    return await _call(ctx, name, main.admin_pc_trade_reverse, admin_steam_id=admin,
                       sig=_admin_sign(admin, "pc_trade_reverse", trade_id), trade_id=trade_id, reason=reason)


async def admin_list(ctx, name, player):
    admin = await _admin(ctx)
    return await _call(ctx, name, main.admin_pc_trades, steam_id=player.steam, admin_steam_id=admin,
                       sig=_admin_sign(admin, "pc_trade_list", player.steam))


async def setting(ctx, name, actor, key, value):
    rev = await _val("SELECT pc_settings_revision FROM players WHERE id = $1::uuid", actor.pid)
    nonce = _nonce()
    return await _call(ctx, name, main.pc_set_setting, request=REQ, steam_id=actor.steam,
                       sig=_sign(_pc.canon_settings(actor.steam, nonce, int(rev), key, int(value))),
                       nonce=nonce, revision=int(rev), key=key, value=int(value))


async def discard(ctx, name, actor, print_id):
    return await _call(ctx, name, main.pc_discard_print, request=REQ, steam_id=actor.steam,
                       sig=_sign(_pc.canon_discard(actor.steam, print_id)), print_id=print_id)


async def delete_data(ctx, name, actor):
    sig = hmac.new(SECRET.encode(), ("delete:%s" % actor.steam).encode(), hashlib.sha256).hexdigest()
    return await _call(ctx, name, main.delete_player_data, steam_id=actor.steam, request=REQ, sig=sig,
                       _slot=None)


async def me(ctx, name, actor):
    return await _call(ctx, name, main.pc_me, request=REQ, steam_id=actor.steam,
                       sig=_sign(_pc.canon_read(actor.steam, "me", "-")))


async def collection(ctx, name, actor):
    return await _call(ctx, name, main.pc_collection, request=REQ, steam_id=actor.steam,
                       sig=_sign(_pc.canon_read(actor.steam, "collection", "-")), subject=None)


async def health(ctx, name):
    maker = await ctx.session(name)
    async with maker() as db:
        return await main.health_check(db=db)


async def janitor(ctx):
    maker = await ctx.session("janitor")
    ctx.env.monkeypatch.setattr(database, "async_session", maker)
    await main._pc_trade_janitor_step()


def scenario(env, body):
    """Run `body(ctx)` in a fresh event loop with a fresh Ctx."""
    async def _go():
        ctx = Ctx(env)
        try:
            return await body(ctx)
        finally:
            await ctx.close()
            await _close_fixture_conns()
    return _run(_go())


async def _world(ctx, n=2, **kw):
    """`n` traders (players 101..), a card subject (150), and the admin."""
    traders = [await _player(ctx, 101 + i, **kw) for i in range(n)]
    subject = await _player(ctx, 150, series=0)
    await _admin(ctx)
    return traders, subject


async def _trade(ctx, a, b, give, get, name="setup"):
    status, body = await propose(ctx, name, a, b, give, get)
    assert status == 200, body
    return body


async def _executed(ctx, a, b, give, get):
    t = await _trade(ctx, a, b, give, get)
    status, body = await accept(ctx, "setup_accept", b, t)
    assert status == 200, body
    return t


async def _set_state_now(env, state):
    conn = await _connect()
    try:
        await _set_state(conn, state, env.build)
    finally:
        await conn.close()


async def _restore_now(env):
    conn = await _connect()
    try:
        await _restore(conn, env.build)
    finally:
        await conn.close()


def _writes(statements):
    return [s for s in statements if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", s, re.I)]


def _row_locks(statements):
    return [s for s in statements if re.search(r"\bFOR\s+(NO\s+KEY\s+)?UPDATE\b", s, re.I)]


# ======================================================================
# Walk 1 and M25: the traded discard value
# ======================================================================

def test_m25_walk1_a_traded_legendary_discards_for_traded_discard_shards(env):
    """M25 (E 10): a print received by trade discards for
    PC_TRADE["traded_discard_shards"] (0) whatever its rarity; an untraded
    Legendary still pays shards_for("legendary") (the negative control).
    Walk 1: A11 sets the owner and the flag in one statement."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p = await _print(ctx, a, s, "legendary")
        q = await _print(ctx, b, s, "common")
        own = await _print(ctx, b, s, "legendary")
        t = await _executed(ctx, a, b, [p], [q])
        assert await _owner(p) == b.pid and await _owner(q) == a.pid
        assert await _val("SELECT acquired_by_trade FROM pc_prints WHERE id = $1::uuid", p) is True
        assert await _status(t["trade_id"]) == "executed"
        before = await _shards(b)
        traded = await discard(ctx, "discard", b, p)
        untraded = await discard(ctx, "discard2", b, own)
        return traded, untraded, before, await _shards(b)
    traded, untraded, before, after = scenario(env, body)
    assert traded[0] == 200 and traded[1]["shards_gained"] == int(_pc.PC_TRADE["traded_discard_shards"]) == 0, traded
    assert untraded[0] == 200 and untraded[1]["shards_gained"] == _pc.shards_for("legendary"), untraded
    assert after - before == _pc.shards_for("legendary"), (before, after)


# ======================================================================
# Pure checks: no database
# ======================================================================

def test_m14_the_signed_term_is_injective():
    """M14 (E 10), a contract statement with no mutant: every field of the
    signed term but the nonce has a fixed format with no ':', so the fixed
    fields parse from both ends and recover the nonce, and no two valid
    tuples share one canonical string. The nonce's own grammar excludes ':'
    too (defence in depth)."""
    steam, to = _steam(101), _steam(102)
    tid = str(uuid.uuid4())
    digest = hashlib.sha256(b"x").hexdigest()
    for rx, good, colon in ((main._PC_TRADE_NONCE_RE, "abcdefghi", "abcd:efgh"),
                            (main._PC_TRADE_STEAM_RE, steam, steam[:12] + ":" + steam[13:]),
                            (main._PC_TRADE_DIGEST_RE, digest, digest[:63] + ":")):
        assert len(colon) == len(good) and rx.match(good) and not rx.match(colon), (good, colon)
    assert main._pc_trade_uuid(tid) == tid and ":" not in tid
    assert main._pc_trade_uuid(tid.upper()) is None
    seen = {}
    for nonce in ("abcdefgh", "abc-defgh_1", "Z" * 64):
        for action, target in (("propose", to), ("accept", tid), ("decline", tid), ("cancel", tid)):
            canon = _pc.canon_trade(steam, nonce, action, target, digest)
            parts = canon.split(":")
            assert parts[0] == "pctrade" and parts[1] == steam
            assert parts[-3:] == [action, target, digest]
            assert ":".join(parts[2:-3]) == nonce
            assert canon not in seen, (canon, seen.get(canon))
            seen[canon] = (nonce, action, target)


def test_m26_the_marker_is_derived_from_the_literals_the_routes_run():
    """M26 (E 10): the /health word is DERIVED from the accept's claim and
    move literals the routes run (8.3). The derivation refuses a move that
    lost its owner predicate and a claim that lost its status or expiry
    term; the build's flag is the derivation of the literals as they stand,
    and the word reads `broken` exactly when they do not derive. (Its two
    control legs: the check restored with the literal still stripped reads
    `broken`; both restored reads `ready`.)"""
    move, claim = main._PC_TRADE_MOVE_SQL, main._PC_TRADE_CLAIM_SQL
    owner = "owner_player_id = CAST(:from AS uuid) AND "
    assert main._pc_trade_derive(claim, move.replace(owner, "")) is False
    assert main._pc_trade_derive(claim.replace("AND expires_at > clock_timestamp() ", ""), move) is False
    assert main._pc_trade_derive(claim.replace("AND status = 'proposed'", ""), move) is False
    whole = owner in move and "AND status = 'proposed'" in claim and "AND expires_at > clock_timestamp() " in claim
    assert main._PC_TRADE_DERIVED is main._pc_trade_derive(claim, move) is whole
    word = ("ready" if _pc.PC_TRADE["enabled"] else "off") if whole else "broken"
    assert main._pc_trade_word_of("found") == word


def test_every_trade_refusal_has_one_shape():
    """3.13: every trade conflict answers error, permanent, state and
    retry_after; the pure helpers that choose a code return (code,
    permanent)."""
    e = main._pc_trade_refusal("pair_busy")
    assert e.status_code == 409 and set(e.detail) == {"error", "permanent", "state", "retry_after"}
    e = main._pc_trade_refusal("expired", permanent=True, state="expired", retry_after=5)
    assert e.detail == {"error": "expired", "permanent": True, "state": "expired", "retry_after": 5}
    assert main._pc_trade_refusal("trading_off", 503, retry_after=300).status_code == 503


def test_the_void_reason_is_the_dead_word_term_by_term():
    """The janitor's void_reason (_PC_TRADE_VOID_REASON_SQL) is the CASE built
    from the dead word's own terms (_PC_TRADE_DEAD_SQL) and the codes in
    order: the two literals are written out whole for the janitor
    self-test, and this pins them together."""
    dead, void, codes = main._PC_TRADE_DEAD_SQL, main._PC_TRADE_VOID_REASON_SQL, main._PC_TRADE_DEAD_CODES
    head, tail = "(t.status = 'proposed' AND (", "))"
    assert dead.startswith(head) and dead.endswith(tail)
    terms = dead[len(head):-len(tail)].split("\n      OR ")
    assert len(terms) == len(codes) == 7, (len(terms), codes)
    built = "(CASE " + "\n      ".join("WHEN %s THEN '%s'" % (t, c) for t, c in zip(terms, codes)) + " END)"
    assert built == void
    assert set(main._PC_TRADE_REASON_FOR_RECEIVER) <= set(codes)


def test_retention_outlives_every_window_that_reads_a_trade_row():
    """A cooldown or window that reads pc_trades must not outlive the row it
    reads: the decline cooldown reads declined rows (retention_closed_days),
    the reversal window, the re-trade freeze and the reversal cooldown read
    executed and reversed rows (retention_executed_days), and an open
    proposal expires long before either retention could touch it."""
    t = _pc.PC_TRADE
    assert t["retention_closed_days"] * 24 > t["decline_cooldown_hours"]
    assert t["retention_executed_days"] * 24 * 60 > t["reversal_window_minutes"]
    assert t["retention_executed_days"] * 24 > t["reversal_cooldown_hours"]
    assert t["retention_closed_days"] * 24 > t["ttl_hours"]
    assert t["executed_per_pair_day"] <= t["executed_per_day"]
    assert t["traded_discard_shards"] == 0


def test_353_states_its_deploy_order_and_its_permanent_column():
    """8.1: the migration's header names the deploy order (this file first)
    and the permanence of pc_prints.acquired_by_trade; it is one explicit
    transaction (#340) with a bounded lock wait."""
    src = MIGRATION.read_text(encoding="utf-8")
    assert "DEPLOY ORDER: THIS FILE FIRST" in src
    assert "PERMANENT: no later migration may drop or" in src
    stmts = [_bare(s) for s in split_sql(src)]
    assert (stmts[0], stmts[1], stmts[-1]) == ("BEGIN", "SET LOCAL lock_timeout = '5s'", "COMMIT"), stmts[:2]


def _permanence_violations(paths):
    """Every statement in `paths` that would remove the flag column: a drop
    or rename of pc_prints.acquired_by_trade, or a drop of pc_prints; and,
    in a file after 353, a re-creation of pc_prints_immutable without the
    flag's rule."""
    out = []
    for path in paths:
        later = not re.match(r"^\d{3}_", path.name) or int(path.name[:3]) > MIGRATION_NUMBER
        for stmt in split_sql(path.read_text(encoding="utf-8")):
            s = _bare(stmt).lower()
            if (re.search(r"\bdrop\s+column\s+(if\s+exists\s+)?\"?acquired_by_trade\b", s)
                    or re.search(r"\brename\s+column\s+\"?acquired_by_trade\b", s)
                    or re.search(r"\bdrop\s+table\s+(if\s+exists\s+)?[^;]*\bpc_prints\b(?!_)", s)):
                out.append("%s: %s" % (path.name, s[:120]))
            elif (later and path.name != MIGRATION.name
                  and re.search(r"\bfunction\s+(\"?\w+\"?\.)?\"?pc_prints_immutable\"?\s*\(", s)
                  and "acquired_by_trade" not in s):
                out.append("%s: %s" % (path.name, s[:120]))
    return out


def test_m53_no_migration_removes_the_flag_column():
    """M53 (E 10), the column's permanence (F36, 8.1): no file in
    backend/sql -- numbered migrations, rollback and resume scripts alike --
    drops or renames pc_prints.acquired_by_trade, and no file after 353
    re-creates pc_prints_immutable without the flag's rule. The api reads
    the column's absence as 'never installed' and pays the pre-trading
    value on that reading alone, so a drop would re-price every traded
    print. A violation names the file."""
    files = sorted(SQL_DIR.glob("*.sql"))
    assert any(p.name.startswith("rollback_") for p in files)
    assert _permanence_violations(files) == []
    # the scan reads what it claims to: a drop, a rename and a bare trigger
    # re-creation in a later file are each named
    probe = SQL_DIR / "354_probe.sql"
    for body in ("ALTER TABLE pc_prints DROP COLUMN IF EXISTS acquired_by_trade;",
                 "ALTER TABLE pc_prints RENAME COLUMN acquired_by_trade TO x;",
                 _308_print_trigger()[0] + ";"):
        fake = SimpleNamespace(name=probe.name, read_text=lambda encoding=None, b=body: b)
        want = "354_probe.sql: " + _bare(split_sql(body)[0]).lower()[:120]
        assert _permanence_violations([fake]) == [want], body


# ======================================================================
# The accept (3.5): A1-A15 and the lock lattice
# ======================================================================

_LEAKED_SQL = ("SELECT count(*) FROM pc_prints pr JOIN players p ON p.id = pr.owner_player_id "
               "WHERE p.deleted_at IS NOT NULL AND pr.discarded_at IS NULL")


async def _backdate(trade_id, **cols):
    """Move a trade's timestamps into the past, as fixture data: col=interval
    text, each column set to itself minus the interval. The status guard
    forbids any UPDATE that is not a transition, so this runs with
    session_replication_role = replica."""
    sets = ", ".join("%s = %s - interval '%s'" % (c, c, v) for c, v in cols.items())
    await _q("UPDATE pc_trades SET %s WHERE id = $1::uuid" % sets, trade_id, replica=True)


def test_m1_accept_rereads_ownership_under_the_print_locks(env):
    """M1 and M1+M2 (E 10): print p, offered by A in trade X which B accepted
    more than an hour ago (the re-trade freeze lapsed, X's holds gone), is
    also requested from A in C's proposal Y, still open (no janitor pass).
    A accepts Y: A10's ownership re-read answers not_owned and nothing
    moves. Removing A10's ownership terms turns it into A11's
    transfer_conflict; removing A11's owner predicate as well moves p from
    B, who signed nothing, to C."""
    async def body(ctx):
        (a, b, c), s = await _world(ctx, 3)
        p, q, r = await _print(ctx, a, s), await _print(ctx, b, s), await _print(ctx, c, s)
        y = await _trade(ctx, c, a, [r], [p], name="c_proposes_y")
        x = await _executed(ctx, a, b, [p], [q])
        await _backdate(x["trade_id"], executed_at="61 minutes", closed_at="61 minutes")
        held = await _val("SELECT count(*) FROM pc_trade_holds WHERE trade_id = $1::uuid", x["trade_id"])
        ans = await accept(ctx, "a_accepts_y", a, y)
        return dict(ans=ans, held=held, p=await _owner(p), r=await _owner(r), y=await _status(y["trade_id"]),
                    b=b.pid, c=c.pid)
    out = scenario(env, body)
    assert out["held"] == 0
    assert (out["p"], out["r"], out["y"]) == (out["b"], out["c"], "proposed"), out
    assert _err(out["ans"]) == (409, "not_owned"), out["ans"]


def test_m3_a_discard_landing_at_a6_leaves_both_sides_whole(env):
    """M3+liveness (E 10), M11's interleaving: the owner discards one print
    of a side while the accept waits at A6 on a second session's hold of the
    trade row. A10's liveness term answers print_gone and nothing commits;
    without it, A11's count check answers transfer_conflict; without both,
    the trade commits with one side short."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p1, p2, q = await _print(ctx, a, s), await _print(ctx, a, s), await _print(ctx, b, s)
        t = await _trade(ctx, a, b, [p1, p2], [q])
        holder = await _connect("holder")
        await holder.execute("BEGIN")
        await holder.execute("SELECT 1 FROM pc_trades WHERE id = $1::uuid FOR NO KEY UPDATE", t["trade_id"])
        acc = _task(accept(ctx, "acc", b, t), "acc")
        how = await ctx.lock_or_done("acc", acc)
        gone = await discard(ctx, "discard", a, p1)
        await holder.execute("COMMIT")
        await holder.close()
        ans = await acc
        return dict(how=how, gone=gone, ans=ans, p2=await _owner(p2), q=await _owner(q),
                    t=await _status(t["trade_id"]), a=a.pid, b=b.pid)
    out = scenario(env, body)
    assert out["how"] == "lock" and out["gone"][0] == 200, out
    assert (out["p2"], out["q"], out["t"]) == (out["a"], out["b"], "proposed"), out
    assert _err(out["ans"]) == (409, "print_gone"), out["ans"]


async def _executed_fixture(owner_pid, other_pid, n):
    """An executed trade of today between two players, as fixture data (the
    status guard admits no row born executed, so replica mode)."""
    await _q("""
        INSERT INTO pc_trades (pair_lo, pair_hi, proposer, a_prints, b_prints, digest, propose_nonce,
                               proposer_generation, counterparty_generation, status, created_at, expires_at,
                               closed_at, executed_at)
        VALUES (LEAST($1::uuid, $2::uuid), GREATEST($1::uuid, $2::uuid), $1::uuid,
                ARRAY[gen_random_uuid()], ARRAY[gen_random_uuid()], repeat('0', 64), $3, 0, 0, 'executed',
                now(), now() + interval '48 hours', now(), now())""", owner_pid, other_pid,
             "fixture%04d" % n, replica=True)


def test_m4_the_players_locks_serialize_the_daily_cap(env):
    """M4 (E 10): a player at executed_today = 4 accepts two proposals at
    once. A8 (L3) makes the second accept wait for the first's commit and
    read 5: cap_executed_day. Without A8 both commit: 6 in a day."""
    async def body(ctx):
        (a, b, c), s = await _world(ctx, 3)
        for i in range(4):
            filler = await _player(ctx, 111 + i, series=0)
            await _executed_fixture(a.pid, filler.pid, i)
        x1, y1 = await _print(ctx, b, s), await _print(ctx, a, s)
        x2, y2 = await _print(ctx, c, s), await _print(ctx, a, s)
        t1 = await _trade(ctx, b, a, [x1], [y1], name="b_proposes")
        t2 = await _trade(ctx, c, a, [x2], [y2], name="c_proposes")
        g1 = ctx.gate("acc1", "_pc_trade_accept_recheck", "post")
        acc1 = _task(accept(ctx, "acc1", a, t1), "acc1")
        await ctx.reached(g1, "the first accept past A10")
        acc2 = _task(accept(ctx, "acc2", a, t2), "acc2")
        how = await ctx.lock_or_done("acc2", acc2)
        g1.go.set()
        r1, r2 = await acc1, await acc2
        today = await _val("""SELECT count(*) FROM pc_trades WHERE status IN ('executed', 'reversed')
                               AND (pair_lo = $1::uuid OR pair_hi = $1::uuid)
                               AND (executed_at AT TIME ZONE 'UTC')::date = (now() AT TIME ZONE 'UTC')::date""",
                           a.pid)
        return dict(how=how, r1=r1, r2=r2, today=today)
    out = scenario(env, body)
    assert out["r1"][0] == 200, out
    assert _err(out["r2"]) == (409, "cap_executed_day"), out
    assert (out["how"], out["today"]) == ("lock", 5), out


def test_m5_a_forged_accept_writes_nothing(env):
    """M5 (E 10): an accept with a signature the mod secret did not make
    answers 403 Invalid signature before any write or row lock (the
    request's recorded statements carry neither), and the trade is
    untouched."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        t = await _trade(ctx, a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        ans = await accept(ctx, "forged", b, t, sig="0" * 64)
        stmts = ctx.statements("forged")
        return ans, _writes(stmts), _row_locks(stmts), await _status(t["trade_id"])
    ans, writes, locks, status = scenario(env, body)
    assert ans == (403, "Invalid signature"), ans
    assert (writes, locks, status) == ([], [], "proposed")


def test_m6_a_replayed_accept_takes_no_row_lock(env):
    """M6 (E 10): the acceptor's replay of an executed accept -- under its
    own nonce or any other -- answers 200 replayed from A4's plain read with
    no row lock and no write."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        t = await _trade(ctx, a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        nonce = _nonce()
        first = await accept(ctx, "acc", b, t, nonce=nonce)
        again = await accept(ctx, "replay", b, t, nonce=nonce)
        other = await accept(ctx, "replay_other", b, t)
        stmts = ctx.statements("replay") + ctx.statements("replay_other")
        return first, again, other, _row_locks(stmts), _writes(stmts)
    first, again, other, locks, writes = scenario(env, body)
    assert first[0] == 200 and first[1]["replayed"] is False, first
    for ans in (again, other):
        assert ans[0] == 200 and ans[1]["replayed"] is True and ans[1]["state"] == "executed", ans
    assert (locks, writes) == ([], []), (locks, writes)


def test_m7_the_accept_rereads_the_proposers_switch(env):
    """M7 (E 10): the proposer turns trading off after proposing; the accept
    answers counterparty_closed (the switch and the consent generation,
    either alone suffices) and nothing moves."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p, q = await _print(ctx, a, s), await _print(ctx, b, s)
        t = await _trade(ctx, a, b, [p], [q])
        off = await setting(ctx, "off", a, "trades_open", 0)
        ans = await accept(ctx, "acc", b, t)
        return off, ans, await _owner(p) == a.pid, await _owner(q) == b.pid
    off, ans, p_home, q_home = scenario(env, body)
    assert off[0] == 200 and off[1]["trades_open"] is False, off
    assert _err(ans) == (409, "counterparty_closed"), ans
    assert p_home and q_home


def test_m8_the_accept_rereads_the_proposers_ban(env):
    """M8 (E 10): the proposer is banned after proposing; the accept answers
    counterparty_unavailable and nothing moves."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p, q = await _print(ctx, a, s), await _print(ctx, b, s)
        t = await _trade(ctx, a, b, [p], [q])
        await _ban(ctx, a)
        ans = await accept(ctx, "acc", b, t)
        return ans, await _owner(p) == a.pid, await _owner(q) == b.pid
    ans, p_home, q_home = scenario(env, body)
    assert _err(ans) == (409, "counterparty_unavailable"), ans
    assert p_home and q_home


def test_m9_a_deletion_during_an_accept_leaves_no_print_in_a_deleted_binder(env):
    """M9 (E 10, the M9 walk): X proposed giving q for Y's p (p's card does
    not show X). Y's accept pauses after A9, holding both prints; X's data
    deletion starts and waits; the accept resumes and commits. The deletion
    then removes p with X's other prints: no live print is owned by a
    deleted player. Two guards, either sufficient: A5's try-lock of X's
    identity key (the deletion waits at its exclusive key), and the
    deletion's trade statements before its print purge (the trade delete
    waits on the accept's L2)."""
    async def body(ctx):
        (x, y), s = await _world(ctx)
        q, p = await _print(ctx, x, s), await _print(ctx, y, s)
        t = await _trade(ctx, x, y, [q], [p])
        g = ctx.gate("acc", "_pc_trade_lock_prints", "post")
        acc = _task(accept(ctx, "acc", y, t), "acc")
        await ctx.reached(g, "the accept after A9")
        dele = _task(delete_data(ctx, "del", x), "del")
        how = await ctx.lock_or_done("del", dele)
        g.go.set()
        acc_ans, del_ans = await acc, await dele
        return dict(how=how, acc=acc_ans, dele=del_ans, leaked=await _val(_LEAKED_SQL),
                    p=await _val("SELECT count(*) FROM pc_prints WHERE id = $1::uuid", p),
                    trades=await _val("SELECT count(*) FROM pc_trades WHERE pair_lo = $1::uuid OR pair_hi = $1::uuid",
                                      x.pid))
    out = scenario(env, body)
    assert out["how"] == "lock", out
    assert out["acc"][0] == 200 and out["dele"][0] == 200, out
    assert (out["leaked"], out["p"], out["trades"]) == (0, 0, 0), out


def test_m9_a_deletion_holding_the_key_first_makes_the_accept_busy(env):
    """M9's other order (E 10): a deletion that holds X's identity key first
    makes Y's accept answer 409 busy at A5 with nothing written; the
    deletion then completes and removes the trade."""
    async def body(ctx):
        (x, y), s = await _world(ctx)
        q, p = await _print(ctx, x, s), await _print(ctx, y, s)
        t = await _trade(ctx, x, y, [q], [p])
        g = ctx.gate("del", "_pc_lease_drain", "post")
        dele = _task(delete_data(ctx, "del", x), "del")
        await ctx.reached(g, "the deletion holding X's key")
        acc_ans = await accept(ctx, "acc", y, t)
        g.go.set()
        del_ans = await dele
        return dict(acc=acc_ans, dele=del_ans, leaked=await _val(_LEAKED_SQL), p=await _owner(p),
                    y=y.pid, writes=_writes(ctx.statements("acc")))
    out = scenario(env, body)
    assert _err(out["acc"]) == (409, "busy") and out["writes"] == [], out
    assert out["dele"][0] == 200 and out["leaked"] == 0 and out["p"] == out["y"], out


def test_m10_a_cancel_committing_while_the_accept_waits_at_l2(env):
    """M10 (E 10): the accept passes A4 and waits at A6 on the trade row,
    which the proposer's cancel holds; the cancel commits; the claim's
    status = 'proposed' finds no row and the fresh read answers 409
    cancelled. Nothing moves."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p, q = await _print(ctx, a, s), await _print(ctx, b, s)
        t = await _trade(ctx, a, b, [p], [q])
        ga = ctx.gate("acc", "_pc_trade_try_identities", "post")
        acc = _task(accept(ctx, "acc", b, t), "acc")
        await ctx.reached(ga, "the accept past A5")
        gc = ctx.gate("can", "_pc_trade_lock_players", "post")
        can = _task(cancel(ctx, "can", a, t), "can")
        await ctx.reached(gc, "the cancel holding L2 and L3")
        ga.go.set()
        how = await ctx.lock_or_done("acc", acc)
        gc.go.set()
        can_ans, acc_ans = await can, await acc
        return dict(how=how, can=can_ans, acc=acc_ans, t=await _status(t["trade_id"]),
                    home=(await _owner(p) == a.pid and await _owner(q) == b.pid))
    out = scenario(env, body)
    assert (out["t"], out["home"]) == ("cancelled", True), out
    assert out["how"] == "lock" and out["can"][0] == 200, out
    assert _err(out["acc"]) == (409, "cancelled"), out["acc"]


def test_m11_the_claim_rereads_the_expiry(env):
    """M11 (E 10): the accept passes A4 a moment before expires_at and waits
    at A6 while a second session holds the trade row past it; the claim's
    expires_at > clock_timestamp() finds no row and the fresh read answers
    409 expired, before any janitor pass."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p, q = await _print(ctx, a, s), await _print(ctx, b, s)
        t = await _trade(ctx, a, b, [p], [q])
        await _q("""UPDATE pc_trades SET created_at = clock_timestamp() - interval '1 hour',
                                         expires_at = clock_timestamp() + interval '1500 milliseconds'
                     WHERE id = $1::uuid""", t["trade_id"], replica=True)
        holder = await _connect("holder")
        await holder.execute("BEGIN")
        await holder.execute("SELECT 1 FROM pc_trades WHERE id = $1::uuid FOR NO KEY UPDATE", t["trade_id"])
        acc = _task(accept(ctx, "acc", b, t), "acc")
        how = await ctx.lock_or_done("acc", acc)
        while not await _val("SELECT clock_timestamp() > expires_at + interval '300 milliseconds' "
                             "FROM pc_trades WHERE id = $1::uuid", t["trade_id"]):
            await asyncio.sleep(0.05)
        await holder.execute("COMMIT")
        await holder.close()
        ans = await acc
        return dict(how=how, ans=ans, t=await _status(t["trade_id"]),
                    home=(await _owner(p) == a.pid and await _owner(q) == b.pid))
    out = scenario(env, body)
    assert out["how"] == "lock", ("the accept must pass A4 before the expiry and wait at A6", out)
    assert _err(out["ans"]) == (409, "expired"), out["ans"]
    assert (out["t"], out["home"]) == ("proposed", True), out


def test_m30_the_consent_generation_ends_every_earlier_proposal(env):
    """M30 (E 10, F4): the proposer turns trading off and on again before
    any janitor pass; the old proposal's accept answers counterparty_closed
    (the generation moved), and the janitor voids it -- trading_closed as
    stored (the proposer's side), counterparty_closed as the receiver reads
    it."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p, q = await _print(ctx, a, s), await _print(ctx, b, s)
        t = await _trade(ctx, a, b, [p], [q])
        off = await setting(ctx, "off", a, "trades_open", 0)
        on = await setting(ctx, "on", a, "trades_open", 1)
        ans = await accept(ctx, "acc", b, t)
        await janitor(ctx)
        row = (await _q("SELECT status, void_reason FROM pc_trades WHERE id = $1::uuid", t["trade_id"]))[0]
        seen = await read_trades(ctx, "b_reads", b, "full")
        gen = await _val("SELECT pc_trades_generation FROM players WHERE id = $1::uuid", a.pid)
        return dict(off=off, on=on, ans=ans, row=dict(row), seen=seen, gen=gen,
                    home=(await _owner(p) == a.pid and await _owner(q) == b.pid))
    out = scenario(env, body)
    assert out["off"][0] == out["on"][0] == 200 and out["on"][1]["trades_open"] is True and out["gen"] == 1, out
    assert _err(out["ans"]) == (409, "counterparty_closed"), out["ans"]
    assert out["row"] == {"status": "void", "void_reason": "trading_closed"} and out["home"], out
    recent = out["seen"][1]["recent"]
    assert [(r["state"], r["reason"], r["role"]) for r in recent] == [("void", "counterparty_closed", "received")]


# ======================================================================
# Propose (3.4), decline and cancel (3.6), the janitor (3.8)
# ======================================================================

def test_m12_one_open_proposal_per_pair(env):
    """M12 (E 10): a second proposal for a pair with one open, in either
    direction, answers 409 pair_busy (P11's term; the pair index behind
    it), and one proposed row exists."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        await _trade(ctx, a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        again = await propose(ctx, "again", a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        back = await propose(ctx, "back", b, a, [await _print(ctx, b, s)], [await _print(ctx, a, s)])
        rows = await _val("SELECT count(*) FROM pc_trades WHERE status = 'proposed'")
        return again, back, rows
    again, back, rows = scenario(env, body)
    assert _err(again) == (409, "pair_busy") and _err(back) == (409, "pair_busy"), (again, back)
    assert rows == 1


def test_m13_a_print_is_offered_in_one_open_trade(env):
    """M13 (E 10): a print already offered in an open trade cannot be
    offered in a second one (P11's term; the hold's primary key behind it):
    409 print_offered_elsewhere, and the print has one hold."""
    async def body(ctx):
        (a, b, c), s = await _world(ctx, 3)
        p = await _print(ctx, a, s)
        await _trade(ctx, a, b, [p], [await _print(ctx, b, s)])
        second = await propose(ctx, "second", a, c, [p], [await _print(ctx, c, s)])
        holds = await _val("SELECT count(*) FROM pc_trade_holds WHERE print_id = $1::uuid", p)
        return second, holds
    second, holds = scenario(env, body)
    assert _err(second) == (409, "print_offered_elsewhere"), second
    assert holds == 1


def test_m15_the_retrade_freeze_keeps_a_reversal_possible(env):
    """M15 (E 10): B cannot re-trade a print received within the reversal
    window (409 recently_traded), so the reversal of A to B still finds
    every print where the trade put it and succeeds."""
    async def body(ctx):
        (a, b, c), s = await _world(ctx, 3)
        p, q, r = await _print(ctx, a, s), await _print(ctx, b, s), await _print(ctx, c, s)
        x = await _executed(ctx, a, b, [p], [q])
        again = await propose(ctx, "retrade", b, c, [p], [r])
        taken = None
        if again[0] == 200:
            taken = await accept(ctx, "retrade_accept", c, again[1])
        rev = await reverse(ctx, "reverse", x["trade_id"])
        return dict(again=again, taken=taken, rev=rev, p=await _owner(p), a=a.pid)
    out = scenario(env, body)
    assert _err(out["again"]) == (409, "recently_traded") and out["again"][1]["retry_after"] > 0, out
    assert out["taken"] is None and out["rev"][0] == 200 and out["p"] == out["a"], out


def test_m16_the_reversal_window_closes_after_an_hour(env):
    """M16 (E 10): a reversal 61 minutes after the trade executed answers
    409 window_closed and nothing moves."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p, q = await _print(ctx, a, s), await _print(ctx, b, s)
        x = await _executed(ctx, a, b, [p], [q])
        await _backdate(x["trade_id"], executed_at="61 minutes", closed_at="61 minutes")
        rev = await reverse(ctx, "reverse", x["trade_id"])
        return rev, await _status(x["trade_id"]), await _owner(p) == b.pid
    rev, status, moved = scenario(env, body)
    assert _err(rev) == (409, "window_closed"), rev
    assert (status, moved) == ("executed", True)


def test_m17_a_reversal_writes_exactly_one_audit_row(env):
    """M17 (E 10): a reversal commits with exactly one pc_trade_reverse
    AdminAction row; a refused second reversal writes none. The admin list
    shows the trade reversed."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p, q = await _print(ctx, a, s), await _print(ctx, b, s)
        x = await _executed(ctx, a, b, [p], [q])
        rev = await reverse(ctx, "reverse", x["trade_id"])
        again = await reverse(ctx, "reverse_again", x["trade_id"])
        audit = await _q("SELECT action, target_steam_id, details FROM admin_actions "
                         "WHERE action = 'pc_trade_reverse'")
        listed = await admin_list(ctx, "list", a)
        return dict(rev=rev, again=again, audit=[dict(r) for r in audit], listed=listed, tid=x["trade_id"],
                    home=(await _owner(p) == a.pid and await _owner(q) == b.pid))
    out = scenario(env, body)
    assert out["rev"][0] == 200 and out["rev"][1]["status"] == "reversed", out
    assert _err(out["again"]) == (409, "reversed"), out["again"]
    assert [(r["action"], r["target_steam_id"]) for r in out["audit"]] == [("pc_trade_reverse", out["tid"])]
    assert out["home"]
    assert [(t["trade_id"], t["state"]) for t in out["listed"][1]["trades"]] == [(out["tid"], "reversed")]


def test_m18_a_reversal_after_a_discard_moves_nothing(env):
    """M18 (E 10): the recipient discarded one received print; the reversal
    answers 409 moved_on and the transaction rolls back whole -- no
    partial reversal."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p1, p2, q = await _print(ctx, a, s), await _print(ctx, a, s), await _print(ctx, b, s)
        x = await _executed(ctx, a, b, [p1, p2], [q])
        gone = await discard(ctx, "discard", b, p1)
        rev = await reverse(ctx, "reverse", x["trade_id"])
        return dict(gone=gone, rev=rev, p2=await _owner(p2), q=await _owner(q), x=await _status(x["trade_id"]),
                    a=a.pid, b=b.pid)
    out = scenario(env, body)
    assert out["gone"][0] == 200, out
    assert _err(out["rev"]) == (409, "moved_on"), out["rev"]
    assert (out["p2"], out["q"], out["x"]) == (out["b"], out["a"], "executed"), out


def test_m19a_a_private_binder_is_no_oracle(env):
    """M19 (a) (E 10, F43): with the counterparty's binder private, a
    proposal naming a print they hold and one naming a print they do not
    hold both answer 403 private (P6; P11's binder term behind it), and no
    trade row exists."""
    async def body(ctx):
        (a, b, c), s = await _world(ctx, 3)
        await _q("UPDATE players SET pc_collection_public = false WHERE id = $1::uuid", b.pid)
        mine = await _print(ctx, a, s)
        held = await propose(ctx, "held", a, b, [mine], [await _print(ctx, b, s)])
        other = await propose(ctx, "other", a, b, [mine], [await _print(ctx, c, s)])
        return held, other, await _val("SELECT count(*) FROM pc_trades")
    held, other, rows = scenario(env, body)
    assert _err(held) == (403, "private") and _err(other) == (403, "private"), (held, other)
    assert rows == 0


def test_m19b_no_print_read_precedes_the_private_refusal(env):
    """M19 (b) (E 10, F43): P6 runs before P7, so the 403 private for a
    private binder follows no statement that reads a print (the schema
    probe names pc_prints only as text)."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        await _q("UPDATE players SET pc_collection_public = false WHERE id = $1::uuid", b.pid)
        ans = await propose(ctx, "held", a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        reads = [st for st in ctx.statements("held") if re.search(r"\b(FROM|JOIN)\s+pc_prints\b", st)]
        return ans, reads
    ans, reads = scenario(env, body)
    assert _err(ans) == (403, "private"), ans
    assert reads == [], reads


def test_m20_the_trading_switch_moves_only_trades_open(env):
    """M20 (E 10), the server's reading: the settings key trades_open is its
    own third value -- toggling it leaves announce and collection_public
    as they were; every write of off bumps the consent generation, a write
    of on does not."""
    async def body(ctx):
        (a,), _s = await _world(ctx, 1)
        before = await me(ctx, "before", a)
        off = await setting(ctx, "off", a, "trades_open", 0)
        gen_off = await _val("SELECT pc_trades_generation FROM players WHERE id = $1::uuid", a.pid)
        on = await setting(ctx, "on", a, "trades_open", 1)
        gen_on = await _val("SELECT pc_trades_generation FROM players WHERE id = $1::uuid", a.pid)
        after = await me(ctx, "after", a)
        return before, off, on, gen_off, gen_on, after
    before, off, on, gen_off, gen_on, after = scenario(env, body)
    assert before[0] == 200 and before[1]["settings"]["trades_open"] is True, before
    keep = {k: before[1]["settings"][k] for k in ("collection_public", "announce")}
    assert off[0] == 200 and off[1]["trades_open"] is False and {k: off[1][k] for k in keep} == keep, off
    assert on[0] == 200 and on[1]["trades_open"] is True and {k: on[1][k] for k in keep} == keep, on
    assert (gen_off, gen_on) == (1, 1)
    assert after[0] == 200 and after[1]["settings"]["trades_open"] is True, after
    assert {k: after[1]["settings"][k] for k in keep} == keep, after


def test_m21_every_exit_from_proposed_releases_the_holds(env):
    """M21 (E 10): a decline releases the offered print at once (the next
    proposal offering it succeeds), and an executed trade leaves no hold."""
    async def body(ctx):
        (a, b, c), s = await _world(ctx, 3)
        p = await _print(ctx, a, s)
        t = await _trade(ctx, a, b, [p], [await _print(ctx, b, s)])
        dec = await decline(ctx, "decline", b, t)
        again = await propose(ctx, "again", a, c, [p], [await _print(ctx, c, s)])
        acc = await accept(ctx, "accept", c, again[1]) if again[0] == 200 else None
        return dec, again, acc, await _val("SELECT count(*) FROM pc_trade_holds")
    dec, again, acc, holds = scenario(env, body)
    assert dec[0] == 200 and dec[1]["state"] == "declined", dec
    assert again[0] == 200, again
    assert acc[0] == 200 and holds == 0, (acc, holds)


def test_m22_an_executing_trade_cannot_commit(env):
    """M22 (E 10): a transaction that claims a trade (A7) and commits without
    A12 raises at commit (the deferred constraint trigger), and the trade
    stays proposed."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        t = await _trade(ctx, a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        maker = await ctx.session("raw")
        async with maker() as db:
            claimed = (await db.execute(text(main._PC_TRADE_CLAIM_SQL), {
                "actor": b.pid, "nonce": "rawclaim01", "t": t["trade_id"], "digest": t["digest"]})).all()
            try:
                await db.commit()
                outcome = "committed"
            except Exception as e:
                outcome = "%s: %s" % (type(e).__name__, str(e))
        return len(claimed), outcome, await _status(t["trade_id"])
    claimed, outcome, status = scenario(env, body)
    assert claimed == 1
    assert "still executing at commit" in outcome, outcome
    assert status == "proposed"


def test_m23_a_data_deletion_removes_every_trade_naming_the_player(env):
    """M23 (E 10), 3.9: a data deletion removes every pc_trades row naming
    the player (their holds cascade) and every spent-nonce tombstone of
    theirs; a trade between two other players survives."""
    async def body(ctx):
        (a, b, c), s = await _world(ctx, 3)
        await _trade(ctx, a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        await _executed(ctx, a, c, [await _print(ctx, a, s)], [await _print(ctx, c, s)])
        await _trade(ctx, b, c, [await _print(ctx, b, s)], [await _print(ctx, c, s)])
        gone = await delete_data(ctx, "del", a)
        left = await _val("SELECT count(*) FROM pc_trades WHERE pair_lo = $1::uuid OR pair_hi = $1::uuid", a.pid)
        nonces = await _val("SELECT count(*) FROM pc_trade_spent_nonces WHERE proposer = $1::uuid", a.pid)
        others = await _val("SELECT count(*) FROM pc_trades")
        holds = await _val("SELECT count(*) FROM pc_trade_holds h JOIN pc_trades t ON t.id = h.trade_id")
        return gone, left, nonces, others, holds, await _val("SELECT count(*) FROM pc_trade_holds")
    gone, left, nonces, others, holds, all_holds = scenario(env, body)
    assert gone[0] == 200, gone
    assert (left, nonces, others) == (0, 0, 1)
    assert holds == all_holds == 1


def test_m24_the_janitor_expires_a_lapsed_proposal(env):
    """M24 (E 10), 3.8 step 1: a proposal past expires_at reads expired
    after a janitor pass, and its holds are gone."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        t = await _trade(ctx, a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        await _backdate(t["trade_id"], created_at="3 days", expires_at="3 days")
        await janitor(ctx)
        row = (await _q("SELECT status, closed_at IS NOT NULL AS closed FROM pc_trades WHERE id = $1::uuid",
                        t["trade_id"]))[0]
        return dict(row), await _val("SELECT count(*) FROM pc_trade_holds")
    row, holds = scenario(env, body)
    assert row == {"status": "expired", "closed": True} and holds == 0, (row, holds)


def test_the_janitor_voids_a_dead_proposal_with_its_reason(env):
    """3.8 step 2: a proposal whose offered print was discarded is dead; the
    janitor voids it with void_reason print_gone, and a read shows it."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p = await _print(ctx, a, s)
        t = await _trade(ctx, a, b, [p], [await _print(ctx, b, s)])
        gone = await discard(ctx, "discard", a, p)
        await janitor(ctx)
        row = (await _q("SELECT status, void_reason FROM pc_trades WHERE id = $1::uuid", t["trade_id"]))[0]
        return gone, dict(row)
    gone, row = scenario(env, body)
    assert gone[0] == 200 and row == {"status": "void", "void_reason": "print_gone"}, (gone, row)


def test_m27_decline_and_cancel_work_while_trading_is_switched_off(env):
    """M27 (E 10), 3.13: the kill switch stops propose and accept (503
    trading_off) and nothing else: a decline and a cancel succeed while it
    is off, and the read reports enabled false."""
    async def body(ctx):
        (a, b, c), s = await _world(ctx, 3)
        t1 = await _trade(ctx, a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        t2 = await _trade(ctx, a, c, [await _print(ctx, a, s)], [await _print(ctx, c, s)])
        ctx.env.monkeypatch.setitem(_pc.PC_TRADE, "enabled", False)
        dec = await decline(ctx, "decline", b, t1)
        can = await cancel(ctx, "cancel", a, t2)
        prop = await propose(ctx, "propose", b, c, [await _print(ctx, b, s)], [await _print(ctx, c, s)])
        seen = await read_trades(ctx, "read", a, "summary")
        return dec, can, prop, seen
    dec, can, prop, seen = scenario(env, body)
    assert dec[0] == 200 and dec[1]["state"] == "declined", dec
    assert can[0] == 200 and can[1]["state"] == "cancelled", can
    assert _err(prop) == (503, "trading_off"), prop
    assert seen[0] == 200 and seen[1]["enabled"] is False, seen


def test_m29_the_spent_nonce_outlives_retention(env):
    """M29 (E 10, F2): a declined proposal's row is purged by retention;
    the identical signed propose, resubmitted, answers 409
    already_processed and creates nothing. The same holds for an executed
    trade whose prints came back through a reversal and whose row retention
    then purged."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p, q = await _print(ctx, a, s), await _print(ctx, b, s)
        terms = dict(nonce=_nonce())
        terms["digest"] = _digest(a.steam, [p], b.steam, [q])
        terms["sig"] = _sign(_pc.canon_trade(a.steam, terms["nonce"], "propose", b.steam, terms["digest"]))
        first = await propose(ctx, "first", a, b, [p], [q], **terms)
        await decline(ctx, "decline", b, first[1])
        await _backdate(first[1]["trade_id"], closed_at="31 days")
        await janitor(ctx)
        purged = await _val("SELECT count(*) FROM pc_trades")
        again = await propose(ctx, "again", a, b, [p], [q], **terms)
        after_one = (await _val("SELECT count(*) FROM pc_trades"), await _val("SELECT count(*) FROM pc_trade_holds"))
        leg_one = dict(first=first, purged=purged, again=again, after_one=after_one)
        if _err(again) != (409, "already_processed"):
            # the resubmission was let through: judged here, before the
            # executed leg, whose own propose its open row would refuse
            return leg_one
        # the executed leg: execute, reverse, age past retention, resubmit
        terms2 = dict(nonce=_nonce())
        terms2["digest"] = terms["digest"]
        terms2["sig"] = _sign(_pc.canon_trade(a.steam, terms2["nonce"], "propose", b.steam, terms2["digest"]))
        second = await propose(ctx, "second", a, b, [p], [q], **terms2)
        await accept(ctx, "accept", b, second[1])
        rev = await reverse(ctx, "reverse", second[1]["trade_id"])
        await _backdate(second[1]["trade_id"], executed_at="181 days", closed_at="181 days",
                        reversed_at="181 days")
        await janitor(ctx)
        purged2 = await _val("SELECT count(*) FROM pc_trades")
        again2 = await propose(ctx, "again2", a, b, [p], [q], **terms2)
        after_two = (await _val("SELECT count(*) FROM pc_trades"), await _val("SELECT count(*) FROM pc_trade_holds"))
        return dict(leg_one, rev=rev, purged2=purged2, again2=again2, after_two=after_two)
    out = scenario(env, body)
    assert out["first"][0] == 200 and out["purged"] == 0, out
    assert _err(out["again"]) == (409, "already_processed") and out["after_one"] == (0, 0), out
    assert out["rev"][0] == 200 and out["purged2"] == 0, out
    assert _err(out["again2"]) == (409, "already_processed") and out["after_two"] == (0, 0), out


def test_m31_the_reversal_window_reads_the_wall_clock(env):
    """M31 (E 10, F5): a trade executed 59 min 58 s ago; a second session
    holds its row; the reversal passes step 2 inside the hour and waits at
    L2; the holder lets go once the hour has passed (well inside the
    reversal's 3 s lock_timeout), and the claim -- clock_timestamp(), not
    the transaction's start -- answers 409 window_closed."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p, q = await _print(ctx, a, s), await _print(ctx, b, s)
        x = await _executed(ctx, a, b, [p], [q])
        await _admin(ctx)
        await _q("""UPDATE pc_trades SET executed_at = clock_timestamp() - interval '59 minutes 58 seconds',
                                         closed_at = clock_timestamp() - interval '59 minutes 58 seconds'
                     WHERE id = $1::uuid""", x["trade_id"], replica=True)
        holder = await _connect("holder")
        await holder.execute("BEGIN")
        await holder.execute("SELECT 1 FROM pc_trades WHERE id = $1::uuid FOR NO KEY UPDATE", x["trade_id"])
        rev = _task(reverse(ctx, "rev", x["trade_id"]), "rev")
        how = await ctx.lock_or_done("rev", rev)
        while not await _val("SELECT clock_timestamp() > executed_at + interval '60 minutes 300 milliseconds' "
                             "FROM pc_trades WHERE id = $1::uuid", x["trade_id"]):
            await asyncio.sleep(0.05)
        await holder.execute("COMMIT")
        await holder.close()
        ans = await rev
        claimed = any("SET status = 'reversed'" in st for st in ctx.statements("rev"))
        return dict(how=how, ans=ans, claimed=claimed, x=await _status(x["trade_id"]),
                    moved=(await _owner(p) == b.pid))
    out = scenario(env, body)
    assert out["how"] == "lock" and out["claimed"], ("the reversal must pass step 2 and wait at L2", out)
    assert _err(out["ans"]) == (409, "window_closed"), out["ans"]
    assert (out["x"], out["moved"]) == ("executed", True), out


def test_m32_the_timeouts_come_before_the_first_lock(env):
    """M32 (E 10, F6): a second session holds the proposer's identity key
    exclusively (as a deletion or a ban would) for up to ten seconds; the
    propose's lock_timeout, set before its first lock, stops it at three
    seconds with 409 busy and nothing written."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p, q = await _print(ctx, a, s), await _print(ctx, b, s)
        holder = await _connect("holder")
        await holder.execute("BEGIN")
        await holder.execute("SELECT pg_advisory_xact_lock(hashtext($1::text))", a.steam)
        t0 = time.monotonic()
        prop = _task(propose(ctx, "prop", a, b, [p], [q]), "prop")
        await asyncio.wait({prop}, timeout=10.0)
        waited = time.monotonic() - t0
        await holder.execute("COMMIT")
        await holder.close()
        ans = await prop
        return ans, waited, await _val("SELECT count(*) FROM pc_trades")
    ans, waited, rows = scenario(env, body)
    assert _err(ans) == (409, "busy") and waited < 5.0, (ans, waited)
    assert rows == 0


def _cooldown(answer):
    status, code = _err(answer)
    return status == 409 and str(code).startswith("cooldown_")


def test_m54_propose_first_the_decline_waits_at_l3(env):
    """M54 (E 10, F41), propose first: A's second proposal to B pauses
    between P11's decline-cooldown term and its pair term; B's decline of
    the first waits at D3's L3 until the proposal answers 409 pair_busy.
    A fresh decline and a new proposal inside the cooldown never coexist."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        t1 = await _trade(ctx, a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        g = ctx.gate("prop2", "_pc_trade_pair_open", "pre")
        prop = _task(propose(ctx, "prop2", a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)]), "prop2")
        await ctx.reached(g, "the second proposal before its pair term")
        dec = _task(decline(ctx, "dec", b, t1), "dec")
        how = await ctx.lock_or_done("dec", dec)
        g.go.set()
        p_ans, d_ans = await prop, await dec
        return how, p_ans, d_ans, await _val("SELECT count(*) FROM pc_trades WHERE status = 'proposed'")
    how, p_ans, d_ans, open_rows = scenario(env, body)
    assert how == "lock", how
    assert _err(p_ans) == (409, "pair_busy"), p_ans
    assert d_ans[0] == 200 and open_rows == 0, (d_ans, open_rows)


def test_m54_decline_first_the_proposal_waits_at_p8(env):
    """M54, decline first: B's decline holds L3; A's second proposal waits
    at P8 and, once the decline commits, answers the cooldown refusal."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        t1 = await _trade(ctx, a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        g = ctx.gate("dec", "_pc_trade_lock_players", "post")
        dec = _task(decline(ctx, "dec", b, t1), "dec")
        await ctx.reached(g, "the decline holding L3")
        prop = _task(propose(ctx, "prop2", a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)]), "prop2")
        how = await ctx.lock_or_done("prop2", prop)
        g.go.set()
        d_ans, p_ans = await dec, await prop
        return how, d_ans, p_ans
    how, d_ans, p_ans = scenario(env, body)
    assert how == "lock" and d_ans[0] == 200, (how, d_ans)
    assert _cooldown(p_ans) and _err(p_ans)[1] == "cooldown_declined", p_ans


def test_m54_a_decline_older_than_the_cooldown_lets_the_proposal_commit(env):
    """M54's negative control: the first proposal was declined more than 24
    hours ago; the new proposal commits."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        t1 = await _trade(ctx, a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        await decline(ctx, "dec", b, t1)
        await _backdate(t1["trade_id"], closed_at="25 hours")
        return await propose(ctx, "prop2", a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
    ans = scenario(env, body)
    assert ans[0] == 200 and ans[1]["state"] == "proposed", ans


def test_m55_reversal_first_the_proposal_waits_and_meets_the_cooldown(env):
    """M55 (E 10, F49), reversal first: the pair's trade T executed ten
    minutes ago; the reversal pauses after its claim, which it makes under
    L3 and L4 (step 3); a same-pair proposal naming prints T did not move
    waits at P8 and, once the reversal commits, answers the cooldown
    refusal with nothing written."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        x = await _executed(ctx, a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        await _backdate(x["trade_id"], executed_at="10 minutes", closed_at="10 minutes")
        g = ctx.gate("rev", "_pc_trade_reverse_claim", "post")
        rev = _task(reverse(ctx, "rev", x["trade_id"]), "rev")
        await ctx.reached(g, "the reversal after its claim")
        prop = _task(propose(ctx, "prop", a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)]), "prop")
        how = await ctx.lock_or_done("prop", prop)
        g.go.set()
        r_ans, p_ans = await rev, await prop
        return how, r_ans, p_ans, await _val("SELECT count(*) FROM pc_trades")
    how, r_ans, p_ans, rows = scenario(env, body)
    assert how == "lock" and r_ans[0] == 200, (how, r_ans)
    assert _cooldown(p_ans) and _err(p_ans)[1] == "cooldown_reversal", p_ans
    assert rows == 1


def test_m55_proposal_first_the_reversal_stamps_after_it(env):
    """M55, proposal first (the pass-through twin): the reversal starts, the
    proposal takes L3 first and commits while the reversal waits at step 3;
    the reversal then claims. The proposal's P11 read precedes the claim in
    the recorded order, and reversed_at (clock_timestamp() at the claim,
    under L3) is later than the proposal's created_at."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        x = await _executed(ctx, a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        await _backdate(x["trade_id"], executed_at="10 minutes", closed_at="10 minutes")
        gr = ctx.gate("rev", "_pc_trade_reverse_lock", "pre")
        rev = _task(reverse(ctx, "rev", x["trade_id"]), "rev")
        await ctx.reached(gr, "the reversal before step 3")
        gp = ctx.gate("prop", "_pc_trade_lock_players", "post")
        prop = _task(propose(ctx, "prop", a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)]), "prop")
        await ctx.reached(gp, "the proposal holding L3")
        gr.go.set()
        how = await ctx.lock_or_done("rev", rev)
        gp.go.set()
        p_ans, r_ans = await prop, await rev
        stamps = (await _q("""SELECT (SELECT reversed_at FROM pc_trades WHERE id = $1::uuid) AS reversed_at,
                                     (SELECT created_at FROM pc_trades WHERE id = $2::uuid) AS created_at""",
                           x["trade_id"], p_ans[1]["trade_id"] if p_ans[0] == 200 else x["trade_id"]))[0]
        p11 = ctx.first_index("prop", r"status = 'reversed'")
        claim = ctx.first_index("rev", r"SET status = 'reversed'")
        return dict(how=how, p=p_ans, r=r_ans, stamps=dict(stamps), p11=p11, claim=claim)
    out = scenario(env, body)
    assert out["how"] == "lock" and out["p"][0] == 200 and out["r"][0] == 200, out
    assert out["p11"] is not None and out["claim"] is not None and out["p11"] < out["claim"], out
    assert out["stamps"]["reversed_at"] > out["stamps"]["created_at"], out["stamps"]


def test_m55_a_reversal_older_than_the_cooldown_lets_the_proposal_commit(env):
    """M55's negative control: the pair's reversal is more than 72 hours
    old; a new proposal commits."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        x = await _executed(ctx, a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        await reverse(ctx, "rev", x["trade_id"])
        await _backdate(x["trade_id"], executed_at="73 hours", closed_at="73 hours", reversed_at="73 hours")
        return await propose(ctx, "prop", a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
    ans = scenario(env, body)
    assert ans[0] == 200 and ans[1]["state"] == "proposed", ans


# ======================================================================
# Reads (3.7), the own binder (6.1), the trader word (2.7)
# ======================================================================

def test_the_reads_never_write_and_show_each_side(env):
    """3.7: summary and full answer each side's open proposals, the full view
    each trade from its viewer's side with its faces and bounds; a proposal
    past its expiry reads `expired` in recent before any janitor pass, and
    the row itself is still proposed -- reads never write, lock, expire or
    void anything."""
    async def body(ctx):
        (a, b, c), s = await _world(ctx, 3)
        p, q = await _print(ctx, a, s), await _print(ctx, b, s)
        t = await _trade(ctx, a, b, [p], [q])
        lapsed = await _trade(ctx, a, c, [await _print(ctx, a, s)], [await _print(ctx, c, s)])
        await _backdate(lapsed["trade_id"], created_at="3 days", expires_at="3 days")
        sa, fa = await read_trades(ctx, "a_sum", a, "summary"), await read_trades(ctx, "a_full", a, "full")
        fb = await read_trades(ctx, "b_full", b, "full")
        stmts = [st for n in ("a_sum", "a_full", "b_full") for st in ctx.statements(n)]
        return dict(sa=sa, fa=fa, fb=fb, writes=_writes(stmts), locks=_row_locks(stmts), t=t["trade_id"],
                    lapsed=lapsed["trade_id"], still=await _status(lapsed["trade_id"]), p=p, q=q)
    out = scenario(env, body)
    sa, fa, fb = out["sa"][1], out["fa"][1], out["fb"][1]
    assert out["sa"][0] == out["fa"][0] == out["fb"][0] == 200
    assert (sa["sent_open"], sa["received_open"]) == ([out["t"]], []), sa
    assert [o["trade_id"] for o in fa["offers"]] == [out["t"]]
    mine = fa["offers"][0]
    assert (mine["role"], mine["possible"], [g["print_id"] for g in mine["give"]]) == ("sent", True, [out["p"]])
    theirs = fb["offers"][0]
    assert (theirs["role"], [g["print_id"] for g in theirs["give"]]) == ("received", [out["q"]])
    assert [(r["trade_id"], r["state"]) for r in fa["recent"]] == [(out["lapsed"], "expired")]
    assert fa["bounds"]["traded_discard_shards"] == 0 and fa["bounds"]["proposals_today"] == 1
    assert (out["writes"], out["locks"], out["still"]) == ([], [], "proposed")


def test_the_own_binder_marks_prints_received_by_trade(env):
    """6.1 (B4c): the own binder carries `traded` on every print, true for a
    print ever received by trade; another player's binder never carries
    it."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p, q = await _print(ctx, a, s), await _print(ctx, b, s)
        kept = await _print(ctx, b, s)
        await _executed(ctx, a, b, [p], [q])
        own = await collection(ctx, "own", b)
        other = await _call(ctx, "other", main.pc_collection, request=REQ, steam_id=a.steam,
                            sig=_sign(_pc.canon_read(a.steam, "collection", b.steam)), subject=b.steam)
        return own, other, p, kept
    own, other, p, kept = scenario(env, body)
    assert own[0] == 200 and {x["print_id"]: x["traded"] for x in own[1]["prints"]} == {p: True, kept: False}
    assert other[0] == 200 and all("traded" not in x for x in other[1]["prints"]), other


def test_the_trader_word_and_its_terms_agree(env):
    """2.7: the party read's trader word (_PC_TRADER_OK_SQL, the gate) is the
    conjunction of the terms the refusal reads one by one (live, not banned,
    switch on, an individual SteamID64, the mod seen, old enough, the
    history floor), on a fixture set that fails each term alone."""
    async def body(ctx):
        (ok,), s = await _world(ctx, 1)
        cases = {"ok": ok}
        cases["no_mod"] = await _player(ctx, 121, mod_days=None)
        cases["new_mod"] = await _player(ctx, 122, mod_days=1)
        cases["no_history"] = await _player(ctx, 123, series=2)
        cases["banned"] = await _player(ctx, 124)
        await _ban(ctx, cases["banned"])
        cases["switch_off"] = await _player(ctx, 125)
        await _q("UPDATE players SET pc_trades_open = false WHERE id = $1::uuid", cases["switch_off"].pid)
        cases["deleted"] = await _player(ctx, 126)
        await _q("UPDATE players SET deleted_at = now() WHERE id = $1::uuid", cases["deleted"].pid)
        odd = await _player(ctx, 127)
        await _q("UPDATE players SET steam_id = '90071992547409927' WHERE id = $1::uuid", odd.pid)
        cases["not_individual"] = odd
        maker = await ctx.session("party")
        async with maker() as db:
            rows = await main._pc_trade_parties(db, [p.pid for p in cases.values()])
        out = {}
        for name, p in cases.items():
            r = rows[p.pid]
            terms = (r["live"], r["not_banned"], r["switch_on"], main._sid64.is_individual_id(r["steam_id"]),
                     r["has_mod"], r["old_enough"], r["has_history"])
            out[name] = (bool(r["trader_ok"]), all(terms),
                         main._pc_trade_party_refusal(r, own=True))
        return out
    out = scenario(env, body)
    for name, (word, terms, refusal) in out.items():
        assert word == terms, (name, word, terms)
        assert (refusal is None) == (name == "ok"), (name, refusal)
    assert out["switch_off"][2] == ("trading_closed", True)
    assert out["banned"][2] == ("not_eligible", True) and out["deleted"][2] == ("not_eligible", True)
    assert out["no_mod"][2] == ("not_eligible", False) and out["not_individual"][2] == ("not_eligible", True)


# ======================================================================
# The schema census (3.9, 8.1): every route on a database 353 has not
# reached, and the words partial and unknown
# ======================================================================

# A probe that raises inside its savepoint: the word `unknown` (F29).
_FAILING_PROBE = "SELECT CAST('probe' AS integer) AS trades"


def _names_trading(statement):
    """A statement other than the schema probe naming a trading object."""
    return statement != main._PC_TRADE_SCHEMA_PROBE_SQL and any(
        re.search(r"\b%s\b" % n, statement) for n in TRADING_NAMES)


async def _missing(ctx, env):
    """The database 353 has not reached, and an api that has cached nothing."""
    await _set_state_now(env, "missing")
    env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_FOUND", False)


def _random_trade():
    return {"trade_id": str(uuid.uuid4()), "digest": "0" * 64}


_CENSUS = {
    "M34_propose": lambda ctx, a, b: propose(ctx, "census", a, b, [str(uuid.uuid4())], [str(uuid.uuid4())]),
    "M35_accept": lambda ctx, a, b: accept(ctx, "census", b, _random_trade()),
    "M36_decline": lambda ctx, a, b: decline(ctx, "census", b, _random_trade()),
    "M37_cancel": lambda ctx, a, b: cancel(ctx, "census", a, _random_trade()),
    "M38_reads_summary": lambda ctx, a, b: read_trades(ctx, "census", a, "summary"),
    "M38_reads_full": lambda ctx, a, b: read_trades(ctx, "census", a, "full"),
    "M39_admin_reverse": lambda ctx, a, b: reverse(ctx, "census", str(uuid.uuid4())),
    "M40_admin_list": lambda ctx, a, b: admin_list(ctx, "census", a),
}


@pytest.mark.parametrize("route", sorted(_CENSUS))
def test_m34_to_m40_every_trade_route_refuses_before_naming_the_schema(env, route):
    """M34-M40 (E 10), census 1-7: on a database 353 has not reached, every
    trade route -- propose, accept, decline, cancel, both read views, the
    admin reversal and the admin list -- answers 503 trading_unavailable,
    and no statement it sent but the schema probe names a trading object."""
    async def body(ctx):
        await _missing(ctx, env)
        try:
            (a, b), _s = await _world(ctx)
            ans = await _CENSUS[route](ctx, a, b)
            stmts = ctx.statements("census")
            return ans, [st for st in stmts if _names_trading(st)], stmts.count(main._PC_TRADE_SCHEMA_PROBE_SQL)
        finally:
            await _restore_now(env)
    ans, named, probes = scenario(env, body)
    assert _err(ans) == (503, "trading_unavailable"), ans
    assert named == [] and probes >= 1, named


def test_m41a_a_settings_write_without_the_trading_schema(env):
    """M41 (a) (E 10), census 8: on a database 353 has not reached, a
    collection_public write commits and answers 200 without trades_open."""
    async def body(ctx):
        await _missing(ctx, env)
        try:
            (a,), _s = await _world(ctx, 1)
            ans = await setting(ctx, "pub", a, "collection_public", 0)
            return ans, await _val("SELECT pc_collection_public FROM players WHERE id = $1::uuid", a.pid)
        finally:
            await _restore_now(env)
    ans, written = scenario(env, body)
    assert ans[0] == 200 and "trades_open" not in ans[1] and ans[1]["collection_public"] is False, ans
    assert written is False


def test_m41b_a_trading_switch_write_without_the_schema_writes_nothing(env):
    """M41 (b) (E 10), census 8: on a database 353 has not reached, a
    trades_open write answers 503 trading_unavailable before any write."""
    async def body(ctx):
        await _missing(ctx, env)
        try:
            (a,), _s = await _world(ctx, 1)
            before = await _val("SELECT pc_settings_revision FROM players WHERE id = $1::uuid", a.pid)
            ans = await setting(ctx, "tro", a, "trades_open", 0)
            after = await _val("SELECT pc_settings_revision FROM players WHERE id = $1::uuid", a.pid)
            return ans, before, after, _writes(ctx.statements("tro"))
        finally:
            await _restore_now(env)
    ans, before, after, writes = scenario(env, body)
    assert _err(ans) == (503, "trading_unavailable"), ans
    assert (after, writes) == (before, []), writes


def test_m42_pc_me_without_the_trading_schema(env):
    """M42 (E 10), census 9: on a database 353 has not reached, /pc/me
    answers 200 without trades_open."""
    async def body(ctx):
        await _missing(ctx, env)
        try:
            (a,), _s = await _world(ctx, 1)
            return await me(ctx, "me", a)
        finally:
            await _restore_now(env)
    ans = scenario(env, body)
    assert ans[0] == 200 and "trades_open" not in ans[1]["settings"], ans
    assert set(ans[1]["settings"]) == {"collection_public", "announce", "revision"}, ans[1]["settings"]


def test_m43_the_own_binder_without_the_trading_schema(env):
    """M43 (E 10), census 10: on a database 353 has not reached, the own
    binder answers 200 without `traded`."""
    async def body(ctx):
        await _missing(ctx, env)
        try:
            (a,), s = await _world(ctx, 1)
            p = await _print(ctx, a, s)
            return await collection(ctx, "own", a), p
        finally:
            await _restore_now(env)
    ans, p = scenario(env, body)
    assert ans[0] == 200 and [x["print_id"] for x in ans[1]["prints"]] == [p], ans
    assert all("traded" not in x for x in ans[1]["prints"])


def test_m44_a_discard_without_the_trading_schema_pays_todays_value(env):
    """M44 (E 10), census 11, and M48's last clause: on a database 353 has
    not reached -- a completed probe that finds the schema missing -- an
    unflagged Legendary discards for shards_for("legendary"), the legacy
    value's one case."""
    async def body(ctx):
        await _missing(ctx, env)
        try:
            (a,), s = await _world(ctx, 1)
            p = await _print(ctx, a, s)
            return await discard(ctx, "disc", a, p)
        finally:
            await _restore_now(env)
    ans = scenario(env, body)
    assert ans[0] == 200 and ans[1]["shards_gained"] == _pc.shards_for("legendary"), ans


def test_m45_a_deletion_without_the_trading_schema_completes(env):
    """M45 (E 10), census 12: on a database 353 has not reached, a data
    deletion completes as it did before trading."""
    async def body(ctx):
        await _missing(ctx, env)
        try:
            (a,), s = await _world(ctx, 1)
            await _print(ctx, a, s)
            ans = await delete_data(ctx, "del", a)
            return ans, await _val("SELECT deleted_at IS NOT NULL FROM players WHERE id = $1::uuid", a.pid), \
                await _val("SELECT count(*) FROM pc_prints WHERE owner_player_id = $1::uuid", a.pid)
        finally:
            await _restore_now(env)
    ans, deleted, prints = scenario(env, body)
    assert ans[0] == 200 and (deleted, prints) == (True, 0), (ans, deleted, prints)


def test_m46_health_without_the_trading_schema(env):
    """M46 (E 10), census 13: on a database 353 has not reached, /health's
    connected arm answers every marker and pc_trading: schema_missing.

    The sweep word is read twice -- once inside /health, once below -- and it
    is a function of the clock: a heartbeat stamp reads `running` and then
    `stale` once _PC_STEAM_STALE_S has passed. Its inputs are pinned to the
    never-run state (no stamp, no fault, a breaker never paused), whose word
    no clock reading can change, so both reads answer the same word however
    long the process has been running."""
    mp = env.monkeypatch
    mp.setattr(main, "IS_REPLICA", False)
    mp.delenv("PC_STEAM_SWEEP", raising=False)
    for key, value in (("clean_at", None), ("started_at", None), ("error", None)):
        mp.setitem(main._PC_STEAM_SWEEP_STATE, key, value)
    if main._pcs is not None:
        mp.setattr(main, "_pc_steam_breaker", main._pcs.Breaker())
    sweep = "paused:renderer" if main._pcs is None else "starting"

    async def body(ctx):
        await _missing(ctx, env)
        try:
            return await health(ctx, "health")
        finally:
            await _restore_now(env)
    h = scenario(env, body)
    assert (h.status, h.database, h.pc_trading) == ("ok", "connected", "schema_missing"), h
    assert (h.pc_renderer_fp, h.pc_raqm, h.pc_steam_sweep, h.pc_steam_render) == (
        main._pc_renderer_fp(), main._pc_raqm(), main._pc_steam_sweep_word(), main._pc_steam_render_word())
    assert h.pc_steam_sweep == sweep, h


class _Down:
    """A session whose database is unreachable: every statement raises, and
    each attempt is counted."""

    def __init__(self):
        self.calls = 0

    async def execute(self, *_a, **_k):
        self.calls += 1
        raise ConnectionError("database unreachable")


def test_b14_the_marker_in_both_health_arms(env):
    """B14 (8.3): pc_trading in both arms. The degraded arm reads the cache
    alone -- `unknown` before any probe, never probing (its one statement is
    the failed SELECT 1) -- and the found word once the connected arm has
    probed; the connected arm probes: `ready`; `off` with the switch off,
    in both arms; `broken` when the literals do not derive, in both arms;
    `unknown` when the probe raises; `partial` on walk 4's database, which
    it never caches."""
    async def body(ctx):
        out = {}
        down = _Down()
        out["degraded_cold"] = ((await main.health_check(db=down)).pc_trading, down.calls)
        h = await health(ctx, "h1")
        out["connected"] = (h.database, h.pc_trading, main._PC_TRADE_SCHEMA_FOUND)
        out["degraded_warm"] = (await main.health_check(db=_Down())).pc_trading
        env.monkeypatch.setitem(_pc.PC_TRADE, "enabled", False)
        out["off"] = ((await health(ctx, "h2")).pc_trading, (await main.health_check(db=_Down())).pc_trading)
        env.monkeypatch.setitem(_pc.PC_TRADE, "enabled", True)
        env.monkeypatch.setattr(main, "_PC_TRADE_DERIVED", False)
        out["broken"] = ((await health(ctx, "h3")).pc_trading, (await main.health_check(db=_Down())).pc_trading)
        env.monkeypatch.setattr(main, "_PC_TRADE_DERIVED", True)
        probe = main._PC_TRADE_SCHEMA_PROBE_SQL
        env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_FOUND", False)
        env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_PROBE_SQL", _FAILING_PROBE)
        out["probe_error"] = ((await health(ctx, "h4")).pc_trading, main._PC_TRADE_SCHEMA_FOUND)
        env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_PROBE_SQL", probe)
        await _set_state_now(env, "walk4")
        try:
            h = await health(ctx, "h5")
            out["partial"] = (h.pc_trading, main._PC_TRADE_SCHEMA_FOUND,
                              (await main.health_check(db=_Down())).pc_trading)
        finally:
            await _restore_now(env)
        return out
    out = scenario(env, body)
    assert out["degraded_cold"] == ("unknown", 1), out
    assert out["connected"] == ("connected", "ready", True), out
    assert out["degraded_warm"] == "ready", out
    assert out["off"] == ("off", "off") and out["broken"] == ("broken", "broken"), out
    assert out["probe_error"] == ("unknown", False), out
    assert out["partial"] == ("partial", False, "unknown"), out
    assert main.HealthResponse.model_fields["pc_trading"].default is None


def test_m47_the_flag_outlives_retention(env):
    """M47 (E 10, F1): B received two Legendaries by trade. Discarded on day
    5 one pays 0; on day 200 -- after retention deleted the executed row --
    the other pays 0 too: the value reads the print's flag, never the
    trade row."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p1, p2 = await _print(ctx, a, s), await _print(ctx, a, s)
        x = await _executed(ctx, a, b, [p1, p2], [await _print(ctx, b, s, "common")])
        await _backdate(x["trade_id"], executed_at="5 days", closed_at="5 days")
        day5 = await discard(ctx, "day5", b, p1)
        await _backdate(x["trade_id"], executed_at="195 days", closed_at="195 days")
        await janitor(ctx)
        row = await _val("SELECT count(*) FROM pc_trades WHERE id = $1::uuid", x["trade_id"])
        day200 = await discard(ctx, "day200", b, p2)
        return day5, row, day200
    day5, row, day200 = scenario(env, body)
    assert day5[0] == 200 and day5[1]["shards_gained"] == 0, day5
    assert row == 0
    assert day200[0] == 200 and day200[1]["shards_gained"] == 0, day200


def test_m48_a_probe_error_pays_nothing_until_a_probe_completes(env):
    """M48 (E 10, F29), and M48+M52's control: a flagged Legendary; the api
    restarted (nothing cached) and its schema probe forced to raise. The
    discard answers 503 trading_unavailable and credits nothing; once a
    probe completes, the same discard pays 0 (`ready`, the flag true)."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p = await _print(ctx, a, s)
        await _executed(ctx, a, b, [p], [await _print(ctx, b, s, "common")])
        probe = main._PC_TRADE_SCHEMA_PROBE_SQL
        env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_FOUND", False)
        env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_PROBE_SQL", _FAILING_PROBE)
        before = await _shards(b)
        refused = await discard(ctx, "refused", b, p)
        mid = (await _shards(b), await _val("SELECT discarded_at IS NULL FROM pc_prints WHERE id = $1::uuid", p))
        env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_PROBE_SQL", probe)
        paid = await discard(ctx, "paid", b, p)
        return before, refused, mid, paid, await _shards(b)
    before, refused, mid, paid, after = scenario(env, body)
    assert _err(refused) == (503, "trading_unavailable"), refused
    assert mid == (before, True), (before, mid)
    assert paid[0] == 200 and paid[1]["shards_gained"] == 0 and after == before, (paid, before, after)


def test_m49_a_probe_error_refuses_the_deletion(env):
    """M49 (E 10, F29): the schema present, a proposal A made, the probe
    forced to raise: A's data deletion answers 503 and deletes nothing (A
    live, the trade and its tombstone in place); the retry after a probe
    completes leaves no row naming A."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        t = await _trade(ctx, a, b, [await _print(ctx, a, s)], [await _print(ctx, b, s)])
        probe = main._PC_TRADE_SCHEMA_PROBE_SQL
        env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_FOUND", False)
        env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_PROBE_SQL", _FAILING_PROBE)
        refused = await delete_data(ctx, "refused", a)
        kept = (await _val("SELECT deleted_at IS NULL FROM players WHERE id = $1::uuid", a.pid),
                await _status(t["trade_id"]),
                await _val("SELECT count(*) FROM pc_trade_spent_nonces WHERE proposer = $1::uuid", a.pid))
        env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_PROBE_SQL", probe)
        done = await delete_data(ctx, "done", a)
        left = (await _val("SELECT count(*) FROM pc_trades WHERE pair_lo = $1::uuid OR pair_hi = $1::uuid", a.pid),
                await _val("SELECT count(*) FROM pc_trade_spent_nonces WHERE proposer = $1::uuid", a.pid))
        return refused, kept, done, left
    refused, kept, done, left = scenario(env, body)
    assert _err(refused) == (503, "trading_unavailable") and kept == (True, "proposed", 1), (refused, kept)
    assert done[0] == 200 and left == (0, 0), (done, left)


def test_m50_the_probe_error_stays_inside_its_savepoint(env):
    """M50 (E 10, F29, F3): a collection_public write with the probe forced
    to raise answers 200 without trades_open and the value is written: the
    probe's error never reaches the write's transaction (#235)."""
    async def body(ctx):
        (a,), _s = await _world(ctx, 1)
        env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_FOUND", False)
        env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_PROBE_SQL", _FAILING_PROBE)
        ans = await setting(ctx, "pub", a, "collection_public", 0)
        return ans, await _val("SELECT pc_collection_public FROM players WHERE id = $1::uuid", a.pid)
    ans, written = scenario(env, body)
    assert ans[0] == 200 and "trades_open" not in ans[1] and ans[1]["collection_public"] is False, ans
    assert written is False


def test_m51_a_partial_schema_refuses_the_discard_and_the_deletion(env):
    """M51 (E 10, F36), and M51+M52's control: walk 4's database (the pair
    index gone), the api restarted. A flagged Legendary's discard and the
    data deletion of a player with an open proposal both answer 503 and
    write nothing; with the schema restored the discard pays 0 and the
    deletion leaves no row naming the player."""
    async def body(ctx):
        (a, b, c), s = await _world(ctx, 3)
        p = await _print(ctx, a, s)
        await _executed(ctx, a, b, [p], [await _print(ctx, b, s, "common")])
        t = await _trade(ctx, c, b, [await _print(ctx, c, s)], [await _print(ctx, b, s)])
        before = await _shards(b)
        await _set_state_now(env, "walk4")
        try:
            env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_FOUND", False)
            disc = await discard(ctx, "disc", b, p)
            dele = await delete_data(ctx, "dele", c)
            mid = (await _shards(b), await _val("SELECT discarded_at IS NULL FROM pc_prints WHERE id = $1::uuid", p),
                   await _val("SELECT deleted_at IS NULL FROM players WHERE id = $1::uuid", c.pid),
                   await _status(t["trade_id"]),
                   await _val("SELECT count(*) FROM pc_trade_spent_nonces WHERE proposer = $1::uuid", c.pid))
        finally:
            await _restore_now(env)
        paid = await discard(ctx, "paid", b, p)
        done = await delete_data(ctx, "done", c)
        left = await _val("SELECT count(*) FROM pc_trades WHERE pair_lo = $1::uuid OR pair_hi = $1::uuid", c.pid)
        return before, disc, dele, mid, paid, done, left
    before, disc, dele, mid, paid, done, left = scenario(env, body)
    assert _err(disc) == (503, "trading_unavailable") and _err(dele) == (503, "trading_unavailable"), (disc, dele)
    assert mid == (before, True, True, "proposed", 1), mid
    assert paid[0] == 200 and paid[1]["shards_gained"] == 0, paid
    assert done[0] == 200 and left == 0, (done, left)


def test_f36_walk5_the_flag_column_alone_refuses_the_discard(env):
    """F36, walk 5 (3.9; M53's control): the six removable objects gone and
    the flag column kept, the api restarted: the probe reads `partial` and a
    flagged Legendary's discard answers 503, nothing credited; with the
    schema restored it pays 0."""
    async def body(ctx):
        (a, b), s = await _world(ctx)
        p = await _print(ctx, a, s)
        await _executed(ctx, a, b, [p], [await _print(ctx, b, s, "common")])
        before = await _shards(b)
        await _set_state_now(env, "walk5")
        try:
            env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_FOUND", False)
            maker = await ctx.session("probe")
            async with maker() as db:
                word = await main._pc_trade_schema(db)
            disc = await discard(ctx, "disc", b, p)
            mid = await _shards(b)
        finally:
            await _restore_now(env)
        paid = await discard(ctx, "paid", b, p)
        return word, disc, before, mid, paid
    word, disc, before, mid, paid = scenario(env, body)
    assert word == "partial" and _err(disc) == (503, "trading_unavailable") and mid == before, (word, disc)
    assert paid[0] == 200 and paid[1]["shards_gained"] == 0, paid


def test_m53_later_migrations_keep_the_traded_value(env):
    """M53's database leg (E 10, F36, F46): after walk 1's trade every
    numbered migration above 353 in backend/sql is applied in order, and the
    flagged Legendary's discard then pays 0 or answers 503 -- never
    shards_for("legendary"), which a file removing the flag column with the
    six would make it pay, and never a failure, which a file dropping the
    column alone would cause. With no such file this applies nothing.

    The next test's reset only re-runs 353, which restores 353's own
    objects and nothing else, so any other change those files make that
    the schema fingerprint sees fails that reset. Whenever a file was
    applied, the schema is therefore rebuilt afterwards by the session
    build's own path, whether or not the leg passed, and the rebuild must
    reproduce that build's two fingerprints and its empty-table list."""
    later = _numbered(above=MIGRATION_NUMBER)

    async def body(ctx):
        (a, b), s = await _world(ctx)
        p = await _print(ctx, a, s)
        await _executed(ctx, a, b, [p], [await _print(ctx, b, s, "common")])
        conn = await _connect("later")
        try:
            for path in later:
                await conn.execute(path.read_text(encoding="utf-8"))
        finally:
            await conn.close()
        env.monkeypatch.setattr(main, "_PC_TRADE_SCHEMA_FOUND", False)
        return [path.name for path in later], await discard(ctx, "disc", b, p)
    try:
        names, ans = scenario(env, body)
    finally:
        if later:
            again = _run(_build())
            assert [again[k] for k in ("fp_pre", "fp_full", "empty")] == [
                env.build[k] for k in ("fp_pre", "fp_full", "empty")], (
                "the rebuild after the later files is not the session's build", again)
    assert ans[0] in (200, 503), (names, ans)
    if ans[0] == 200:
        assert ans[1]["shards_gained"] == 0, (names, ans)
    else:
        assert _err(ans) == (503, "trading_unavailable"), (names, ans)


# ------------------------------------------------------------------ the LAND

async def _sql_trade(proposer, other, give, get, digest):
    """A proposed trade written straight into the table with the stored
    digest given -- a row the propose route never writes when `digest` is
    not its own sides' (P3 refuses those terms), so at accept only F62's
    recompute can tell it apart. The spent nonce and the proposer's holds
    are written beside it, as P12 and P13 write them."""
    lo, hi = sorted((proposer, other), key=lambda p: uuid.UUID(p.pid))
    a_side, b_side = (give, get) if proposer is lo else (get, give)
    nonce = _nonce()
    tid = str(await _val("""
        INSERT INTO pc_trades (pair_lo, pair_hi, proposer, a_prints, b_prints, digest, propose_nonce,
                               proposer_generation, counterparty_generation, expires_at)
        VALUES ($1::uuid, $2::uuid, $3::uuid, $4::uuid[], $5::uuid[], $6, $7, 0, 0,
                now() + make_interval(hours => 48))
        RETURNING id""", lo.pid, hi.pid, proposer.pid, sorted(a_side, key=uuid.UUID),
        sorted(b_side, key=uuid.UUID), digest, nonce))
    await _q("INSERT INTO pc_trade_spent_nonces (proposer, propose_nonce, trade_id) "
             "VALUES ($1::uuid, $2, $3::uuid)", proposer.pid, nonce, tid)
    await _q("INSERT INTO pc_trade_holds (print_id, trade_id) SELECT unnest($1::uuid[]), $2::uuid",
             list(give), tid)
    return {"trade_id": tid, "digest": digest}


async def _f62_case(ctx, side, consistent):
    """F62's fixture: the pair ordered by id, the proposer at the `side` end
    (so both arms of the recompute's party order run), the proposer owning
    p1 and p2 and the other party q. The row's sides say p1 for q; its
    stored digest is that of p1 for q (`consistent`) or of p2 for q. The
    other party accepts, signing the STORED digest, so A3 and A7 pass."""
    traders, s = await _world(ctx)
    lo, hi = sorted(traders, key=lambda p: uuid.UUID(p.pid))
    a, b = (lo, hi) if side == "lo" else (hi, lo)
    p1, p2, q = await _print(ctx, a, s), await _print(ctx, a, s), await _print(ctx, b, s)
    t = await _sql_trade(a, b, [p1], [q], _digest(a.steam, [p1] if consistent else [p2], b.steam, [q]))
    ans = await accept(ctx, "acc", b, t)
    held = await _val("SELECT count(*) FROM pc_trade_holds WHERE trade_id = $1::uuid", t["trade_id"])
    return dict(ans=ans, status=await _status(t["trade_id"]), held=held,
                owners=[await _owner(x) for x in (p1, p2, q)], a=a.pid, b=b.pid)


@pytest.mark.parametrize("side", ["lo", "hi"])
def test_f62_accept_recomputes_the_locked_terms_digest(env, side):
    """F62 (LAND): a proposed row whose stored digest is not the digest of
    its own sides is refused at accept although the signed digest equals
    the stored one. A10 recomputes the digest by P3's recipe from the two
    locked party rows' steam ids and the row's sides: signed = stored =
    recomputed, or 409 bad_terms (permanent). The claim rolls back with the
    refusal: the row stays proposed, its hold stays, nothing moves. Without
    the recompute this accept executes and moves p1 and q (the mutation leg
    in trading-server-land-f62.log)."""
    out = scenario(env, lambda ctx: _f62_case(ctx, side, consistent=False))
    assert _err(out["ans"]) == (409, "bad_terms") and out["ans"][1]["permanent"] is True, out
    assert (out["status"], out["held"]) == ("proposed", 1), out
    assert out["owners"] == [out["a"], out["a"], out["b"]], out


@pytest.mark.parametrize("side", ["lo", "hi"])
def test_f62_control_a_consistent_sql_row_executes(env, side):
    """F62's control: the same SQL-written row carrying its own sides'
    digest executes through the same accept, so the recompute agrees with
    every consistent row and the refusal above is the terms, not the
    fixture."""
    out = scenario(env, lambda ctx: _f62_case(ctx, side, consistent=True))
    assert out["ans"][0] == 200, out
    assert (out["status"], out["held"]) == ("executed", 0), out
    assert out["owners"] == [out["b"], out["a"], out["a"]], out


_F63_NAMES = ("pc_trades_open", "pc_trades_generation")


def test_f63_the_player_mapper_carries_both_trade_columns():
    """F63 (LAND; build brief B3): the Player mapper carries both columns 353
    adds to players -- Boolean and Integer, NOT NULL, their defaults 353's
    own (true, 0) held server-side with no Python-side default -- deferred,
    so select(Player) names neither, and Player's eager_defaults is off, so
    an ORM insert never RETURNs them (the note above the class in
    models.py). The database leg below runs both schema states."""
    from sqlalchemy import Boolean, Integer, inspect as sa_inspect, select
    from sqlalchemy.dialects import postgresql
    mapper = sa_inspect(models.Player)
    for name, kind, default in (("pc_trades_open", Boolean, "true"), ("pc_trades_generation", Integer, "0")):
        col = models.Player.__table__.columns[name]
        assert type(col.type) is kind and col.nullable is False, (name, col.type, col.nullable)
        assert col.default is None and str(col.server_default.arg) == default, (name, col.default,
                                                                              col.server_default)
        assert mapper.column_attrs[name].deferred is True, name
    assert mapper.eager_defaults is False
    compiled = str(select(models.Player).compile(dialect=postgresql.dialect()))
    assert "players.steam_id" in compiled and not any(n in compiled for n in _F63_NAMES), compiled


def _f63_orm_uses(sources):
    """Every ORM-shaped use of the two names in (label, source) pairs: an
    attribute (player.pc_trades_open, Player.pc_trades_generation), a
    keyword argument (Player(pc_trades_open=...), .values(...)), or a
    getattr/setattr/hasattr literal. A raw-SQL string naming them is none."""
    import ast
    found = []
    for label, src in sources:
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Attribute) and node.attr in _F63_NAMES:
                found.append("%s:%d attribute %s" % (label, node.lineno, node.attr))
            elif isinstance(node, ast.keyword) and node.arg in _F63_NAMES:
                found.append("%s:%d keyword %s" % (label, node.value.lineno, node.arg))
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                  and node.func.id in ("getattr", "setattr", "hasattr") and len(node.args) >= 2
                  and isinstance(node.args[1], ast.Constant) and node.args[1].value in _F63_NAMES):
                found.append("%s:%d %s %s" % (label, node.lineno, node.func.id, node.args[1].value))
    return found


def test_f63_no_code_reads_or_writes_them_through_the_orm():
    """F63's control: raw SQL stays the only reader and writer of both
    columns (learning #346; the models.py note). No backend module but
    models.py uses either name as an attribute, a keyword argument or a
    getattr/setattr/hasattr literal -- such a use would load a deferred
    column (failing on a database 353 has not reached) or write through
    the ORM. The detector sees each form (the planted source), and a use
    planted in main.py turns this red (the mutation leg in
    trading-server-land-f63.log)."""
    planted = ("p.pc_trades_open\nPlayer(steam_id='x', pc_trades_generation=1)\n"
               "getattr(p, 'pc_trades_open')\nq = 'SELECT pc_trades_open, pc_trades_generation FROM players'\n")
    assert len(_f63_orm_uses([("planted", planted)])) == 3
    paths = sorted(p for p in BACKEND.rglob("*.py")
                   if "tests" not in p.relative_to(BACKEND).parts and p.name != "models.py")
    assert any(p.name == "main.py" for p in paths) and any(p.name == "player_cards.py" for p in paths), paths
    uses = _f63_orm_uses([(str(p.relative_to(BACKEND)), p.read_text(encoding="utf-8")) for p in paths])
    assert uses == [], uses


def test_f63_an_orm_player_round_trips_on_both_schemas(env):
    """F63's database leg (learning #674: run the ORM's own INSERT on both
    schema states). On the database 353 has not reached, an ORM insert of a
    player, select(Player), Session.get and Session.refresh all succeed and
    not one of their statements names either column; on the full schema the
    same round trip names neither, the ORM-made player reads 353's own
    defaults (true, 0), and an explicit ORM read of the two mapped columns
    answers them."""
    from sqlalchemy import select
    pattern = re.compile(r"\bpc_trades_(?:open|generation)\b")

    async def orm_round(ctx, name, n):
        maker = await ctx.session(name)
        async with maker() as db:
            db.add(models.Player(steam_id=_steam(n), display_name="Mapper %d" % n))
            await db.commit()
        async with maker() as db:
            got = (await db.execute(select(models.Player).where(models.Player.steam_id == _steam(n)))).scalar_one()
            again = await db.get(models.Player, got.id)
            await db.refresh(again)
            return str(got.id), [s for s in ctx.statements(name) if pattern.search(s)]

    async def body(ctx):
        await _missing(ctx, env)
        try:
            _pid, named_missing = await orm_round(ctx, "orm_missing", 120)
        finally:
            await _restore_now(env)
        pid, named_full = await orm_round(ctx, "orm_full", 121)
        row = (await _q("SELECT pc_trades_open, pc_trades_generation FROM players WHERE id = $1::uuid", pid))[0]
        maker = await ctx.session("orm_read")
        async with maker() as db:
            mapped = (await db.execute(select(models.Player.pc_trades_open, models.Player.pc_trades_generation)
                                       .where(models.Player.id == uuid.UUID(pid)))).one()
        return dict(named_missing=named_missing, named_full=named_full, row=tuple(row), mapped=tuple(mapped))
    out = scenario(env, body)
    assert out["named_missing"] == [] and out["named_full"] == [], out
    assert out["row"] == (True, 0) and out["mapped"] == (True, 0), out


async def _f67_derived(ctx, name, a, b, c, frozen_print):
    """What R15's fourth clause names, read through the lane's own helpers:
    the re-trade freeze on a print, B's open received count (a capacity
    count), B's executed trades of today (the per-day cap's count) and A's
    decline cooldown toward C."""
    maker = await ctx.session(name)
    async with maker() as db:
        return dict(
            freeze=await main._pc_trade_freeze_left(db, [frozen_print]),
            b_received=int((await main._pc_trade_open_counts(db, c.pid, b.pid))["open_received"]),
            b_today=int((await main._pc_trade_executed_counts(db, b.pid, c.pid))["lo_today"]),
            a_cooldown=await main._pc_trade_decline_cooldown_left(db, a.pid, c.pid))


def test_f67_a_deletion_meets_the_r15_ruling_clause_by_clause(env):
    """F67 (LAND; R15 decided by default 2026-09-26): A's data deletion
    against the ruling, clause by clause. A (deleted), B (A's counterparty),
    C (a third trader), S an ordinary card's subject; B also holds a print of
    A's OWN card. T0: A proposed pa4 to C, C declined (A's decline cooldown
    toward C). T3: executed, A's pa3 for B's pb2 (pa3 frozen, one executed
    trade today for each). T1: open, A offers pa1 for B's pb1 (pa1 held, one
    open received for B). T2: open, C offers pc1 for A's pa2 (pc1 held).
    T4: open, B offers pb3 for C's pc2 -- no party is A.
    (a) A's open trades go and their holds with them: no trade row names A,
    pc1 is C's and free; T4 and its hold are untouched. (b) A's own prints
    and shards go. (c) Prints of S held by B and C -- pa3 included, which B
    received from A -- keep their owners; the print of A's OWN card that B
    held goes, the pre-existing withdrawal of a deleted player's card from
    every binder (the migration-320 line of the deletion), not this lane's.
    (d) Capacity, cooldown and freeze derived from A's trade rows are gone:
    the freeze on pa3, B's open received count, B's executed-today count and
    A's cooldown toward C; a recreated account on A's steam id starts with
    the switch on, generation 0, and proposes to C at once. The lane's own
    two deletes are keyed to A alone: B's and C's spent-nonce rows stay, A's
    go. (e) The wager refund is not reached from here (no lobby); the
    deletion outside the trading block is main's, compared in
    trading-server-land-f67.log, whose mutation legs also remove or widen
    each of the deletion's statements this test names."""
    async def body(ctx):
        (a, b, c), s = await _world(ctx, 3)
        pa1, pa2, pa3, pa4 = [await _print(ctx, a, s) for _ in range(4)]
        pb1, pb2, pb3 = [await _print(ctx, b, s) for _ in range(3)]
        pc1, pc2, pc3 = [await _print(ctx, c, s) for _ in range(3)]
        pba = await _print(ctx, b, a)
        t0 = await _trade(ctx, a, c, [pa4], [pc3], name="t0")
        assert (await decline(ctx, "t0_decline", c, t0))[0] == 200
        await _executed(ctx, a, b, [pa3], [pb2])
        t1 = await _trade(ctx, a, b, [pa1], [pb1], name="t1")
        t2 = await _trade(ctx, c, a, [pc1], [pa2], name="t2")
        t4 = await _trade(ctx, b, c, [pb3], [pc2], name="t4")
        await _q("UPDATE players SET pc_shards = pc_shards + 7 WHERE id = $1::uuid", a.pid)
        before = dict(derived=await _f67_derived(ctx, "derived0", a, b, c, pa3), shards=await _shards(a),
                      cooldown=_err(await propose(ctx, "cool", a, c, [pa4], [pc3])),
                      holds=sorted(str(r[0]) for r in await _q("SELECT print_id FROM pc_trade_holds")))
        ans = await delete_data(ctx, "del", a)
        after = dict(
            dele=ans[0],
            naming_a=await _val("SELECT count(*) FROM pc_trades WHERE $1::uuid IN (pair_lo, pair_hi, proposer)",
                                a.pid),
            t1_t2=[await _status(t["trade_id"]) for t in (t1, t2)], t4=await _status(t4["trade_id"]),
            holds=sorted(str(r[0]) for r in await _q("SELECT print_id FROM pc_trade_holds")),
            a_prints=await _val("SELECT count(*) FROM pc_prints WHERE owner_player_id = $1::uuid", a.pid),
            shards=await _shards(a),
            others={name: await _owner(p) for name, p in (("pb1", pb1), ("pb3", pb3), ("pc1", pc1),
                                                          ("pc2", pc2), ("pc3", pc3), ("pa3", pa3))},
            own_card=await _owner(pba),
            nonces={k: await _val("SELECT count(*) FROM pc_trade_spent_nonces WHERE proposer = $1::uuid", p.pid)
                    for k, p in (("a", a), ("b", b), ("c", c))},
            derived=await _f67_derived(ctx, "derived1", a, b, c, pa3))
        a2 = await _player(ctx, a.n)
        fresh = (await _q("SELECT pc_trades_open, pc_trades_generation FROM players WHERE id = $1::uuid",
                          a2.pid))[0]
        again = await propose(ctx, "again", a2, c, [await _print(ctx, a2, s)], [pc3])
        return dict(before=before, after=after, fresh=tuple(fresh), again=again, pids=(a.pid, a2.pid),
                    owners={"b": b.pid, "c": c.pid}, held=sorted([pa1, pc1, pb3]), kept=[pb3])
    out = scenario(env, body)
    before, after, own = out["before"], out["after"], out["owners"]
    bd, ad = before["derived"], after["derived"]
    assert bd["freeze"] and bd["b_received"] == 1 and bd["b_today"] == 1 and bd["a_cooldown"], ("before", bd)
    assert before["cooldown"] == (409, "cooldown_declined") and before["shards"] == 7, ("before", before)
    assert before["holds"] == out["held"], ("before: the three open trades' holds", before["holds"])
    assert after["dele"] == 200, ("the deletion's answer", after["dele"])
    assert after["naming_a"] == 0 and after["t1_t2"] == [None, None], (
        "(a) A's trades", after["naming_a"], after["t1_t2"])
    assert after["t4"] == "proposed" and after["holds"] == out["kept"], (
        "(a) T4, naming no deleted party, and its hold", after["t4"], after["holds"])
    assert (after["a_prints"], after["shards"]) == (0, 0), (
        "(b) A's own prints and shards", after["a_prints"], after["shards"])
    assert after["others"] == {"pb1": own["b"], "pb3": own["b"], "pc1": own["c"], "pc2": own["c"],
                               "pc3": own["c"], "pa3": own["b"]}, ("(c) prints held by others", after["others"])
    assert after["own_card"] is None, ("the migration-320 withdrawal of A's own card", after["own_card"])
    assert after["nonces"] == {"a": 0, "b": 1, "c": 1}, ("the spent-nonce rows by proposer", after["nonces"])
    assert ad == dict(freeze=None, b_received=0, b_today=0, a_cooldown=None), ("(d) derived state", ad)
    assert out["pids"][0] != out["pids"][1] and out["fresh"] == (True, 0), ("(d) recreated", out["fresh"])
    assert out["again"][0] == 200, ("(d) the recreated account proposes", out["again"])
