"""The read-only role as the effect bound of B2 binding soundness and S SQL
positions (rulings REHEARSAL-FOUR-R6 (1)(a), (2), (3); R7-A1 M2; R7-A2).

Runs under CF_TEST_PG_DSN naming an ADMIN DSN: a superuser, or a LOGIN
CREATEDB role that is not one (a seat's scr_gate). No role is created,
altered or dropped and no pg_catalog ACL is changed: the standing role
scr_seat_ro and template scr_seat_ro_tmpl are read from the cluster
(ro_role.read_cluster; absent or wrong, the module FAILS with the sentence
naming it). The module clones the template as the admin user, builds its
fixture there as that user, runs ro_role.grant inside the clone as its
owner, runs every control as the role, and drops the clone. A second clone,
of template1, carries the same fixture for the admin's validity controls
(the large-object writers are not executable by PUBLIC in the role's
template, so a non-superuser admin could not show them to be writes there).
Its fixture never skips: an unset DSN or a refused CREATE DATABASE fails the module.
Every role connection asserts SELECT current_user, session_user equals the
role before its body runs. The round-10 controls of catalog_all.py:99
and :138 plant a setting and a password only on an rf10_* role a run
created (the stand-in measurer, or R10_CAT_ROLE under a superuser),
inside the rolled-back harness transaction, undone again in finally; under
a seat administrator (neither) they skip with a stated reason (55432 only).

Every harness position is bound to its transaction at both ends
(catalog_position: a token, a transaction-level advisory lock and the
vxid; round 10, report test_r7_ro_role_pg.py:257): a body that ends the
harness transaction returns 'ENDED:...', an effect, whatever it does next.

Each write class runs under the role in two layers:
  provisioned  the role as provisioned (default_transaction_read_only on);
  grant_only   the session turned it off (SET default_transaction_read_only
               = off at session level, SET TRANSACTION READ WRITE in the
               transaction, SHOW transaction_read_only asserted 'off'), so
               the GRANT layer alone is measured.
The SQLSTATE PostgreSQL returns is asserted exactly (EXPECTED); no control
may be 'OK' under the role. Every class also runs under the admin DSN in a
rolled-back transaction and must succeed there: the statement is valid and
is a write wherever the privilege exists.

A refusal is not the only bound (ruling REHEARSAL-R8-A1, E4): an ordinary
role keeps the right to change its OWN persistent defaults (ALTER ROLE
CURRENT_USER SET), which no grant and no read-only layer past READ WRITE
refuses. So every attempt on a role connection reads the catalogs before
and after its body, inside its transaction, as catalog_all reads them for
the catalog diff (every pg_catalog relation, the role's own shared rows
included); a body that succeeds with any catalog difference returns
'CATALOG:<catalogs>' instead of 'OK'.

The sixteen prior-finding programs (rounds 2 to 6) run as Python against a
real SQLAlchemy/asyncpg session under the role, the route the walker missed
being the route executed.

The DSN census (brief item 4, R7-A1 M2) is default-deny over the import,
opener, identity-argument and DSN-text forms of a frozen file list
(ro_census; the freeze in ro_census_frozen).
"""

import ast
import asyncio
import collections
import datetime
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import asyncpg  # noqa: E402
from sqlalchemy import event, text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import catalog_all  # noqa: E402
import catalog_position  # noqa: E402
import ro_census  # noqa: E402
import ro_census_frozen  # noqa: E402
import ro_role  # noqa: E402

ADMIN_DSN = ro_role.pg_dsn(os.environ.get("CF_TEST_PG_DSN") or "")
PROVISIONED, GRANT_ONLY = "provisioned", "grant_only"
LAYERS = (PROVISIONED, GRANT_ONLY)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- fixture

FIXTURE_SQL = [
    "CREATE TABLE public.rf_t (id int PRIMARY KEY, x int)",
    "INSERT INTO public.rf_t VALUES (1, 1), (2, 2)",
    "CREATE VIEW public.rf_v AS SELECT id, x FROM public.rf_t",
    "CREATE SEQUENCE public.rf_seq",
    # Legacy PUBLIC grants a database may carry; provisioning must revoke
    # each, or the role inherits a write route through PUBLIC.
    "CREATE TABLE public.rf_pub (id int)",
    "GRANT INSERT, UPDATE, DELETE ON public.rf_pub TO PUBLIC",
    "CREATE SEQUENCE public.rf_pubseq",
    "GRANT USAGE, UPDATE ON SEQUENCE public.rf_pubseq TO PUBLIC",
    "GRANT CREATE ON SCHEMA public TO PUBLIC",
    "CREATE SCHEMA rf_s",
    "CREATE TABLE rf_s.t (id int, x int)",
    "INSERT INTO rf_s.t VALUES (1, 1)",
    "GRANT USAGE, CREATE ON SCHEMA rf_s TO PUBLIC",
    # A schema PUBLIC holds nothing on: the role reaches it only through
    # the grant step's own USAGE (public and rf_s carry PUBLIC's USAGE, so
    # without this schema the schema_usage step would be unobserved).
    "CREATE SCHEMA rf_priv",
    "CREATE TABLE rf_priv.t (id int)",
    "INSERT INTO rf_priv.t VALUES (1)",
    "CREATE FUNCTION public.rf_secdef_write() RETURNS int LANGUAGE sql "
    "SECURITY DEFINER AS 'INSERT INTO public.rf_t VALUES (100, 100) RETURNING id'",
    # The tables the real admission path locks (main.py _lease_admission_gate
    # and _rdm_claim), reduced to the columns the two statements read.
    "CREATE TABLE public.players (id uuid PRIMARY KEY)",
    "INSERT INTO public.players VALUES ('00000000-0000-0000-0000-000000000001')",
    "CREATE TABLE public.ffa_queue (player_id uuid, status text, series_id uuid)",
    "INSERT INTO public.ffa_queue VALUES "
    "('00000000-0000-0000-0000-000000000001', 'searching', NULL)",
]
PID = "00000000-0000-0000-0000-000000000001"


def _stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S") \
        + "_" + os.urandom(2).hex()


async def _fixture(dsn, name):
    conn = await asyncpg.connect(ro_role.dsn_for(dsn, name))
    try:
        for s in FIXTURE_SQL:
            await conn.execute(s)
        await conn.execute('GRANT CREATE ON DATABASE "%s" TO PUBLIC' % name)
    finally:
        await conn.close()


@pytest.fixture(scope="module")
def env():
    if not ADMIN_DSN:
        pytest.fail("CF_TEST_PG_DSN is unset: name an admin DSN (a superuser, or a "
                    "LOGIN CREATEDB role) on the local cluster; this fixture never skips")
    missing = run(ro_role.read_cluster(ADMIN_DSN))
    if missing:
        pytest.fail("the cluster is not provisioned for the read-only bound: "
                    + "; ".join(missing))
    name = "rf8_ro_" + _stamp()
    out = {"db": name, "role": ro_role.ROLE}
    made = []

    async def setup():
        await ro_role.clone(ADMIN_DSN, name)
        made.append(name)
        await _fixture(ADMIN_DSN, name)
        out["report"] = await ro_role.grant(ADMIN_DSN, name)
        out["admin_ro_db_dsn"] = ro_role.dsn_for(ADMIN_DSN, name)
        out["ro_dsn"] = out["report"]["dsn"]

    try:
        run(setup())
        yield out
    finally:
        for db in made:
            run(ro_role.drop_clone(ADMIN_DSN, db))


@pytest.fixture(scope="module")
def plain():
    """A clone of template1 carrying the same fixture, as the admin owns it:
    where the admin's validity controls run (every privilege present)."""
    if not ADMIN_DSN:
        pytest.fail("CF_TEST_PG_DSN is unset; this fixture never skips")
    name = "rf8_ro_plain_" + _stamp()
    made = []

    async def setup():
        await ro_role.clone(ADMIN_DSN, name, template="template1")
        made.append(name)
        await _fixture(ADMIN_DSN, name)

    try:
        run(setup())
        yield {"admin_db_dsn": ro_role.dsn_for(ADMIN_DSN, name)}
    finally:
        for db in made:
            run(ro_role.drop_clone(ADMIN_DSN, db))


# ---------------------------------------------------------------- runners

def _sqlstate(exc):
    for e in (exc, getattr(exc, "orig", None), getattr(getattr(exc, "orig", None),
                                                        "__cause__", None)):
        s = getattr(e, "sqlstate", None)
        if isinstance(s, str) and len(s) == 5:
            return s
    raise AssertionError("no SQLSTATE on %r" % (exc,))


WHO_SQL = "SELECT current_user, session_user"


def assert_identity(row, expect):
    """The connection's effective identity (R7-A1 M2): current_user and
    session_user both `expect`."""
    got = (row[0], row[1])
    assert got == (expect, expect), (
        "a connection of the read-only bound runs as current_user=%s "
        "session_user=%s, not as %s" % (got[0], got[1], expect))


async def _catalog(conn):
    """The write bound's catalog reading (ruling REHEARSAL-R8-A1, E4): every
    pg_catalog relation as catalog_all reads it for the catalog diff, inside
    the caller's transaction (its own uncommitted changes are visible)."""
    return await catalog_all.snapshot(conn)


async def _shared(conn):
    """The shared rows catalog_all.RESTRICT leaves out (catalog_all.outside),
    read in the position's REPEATABLE READ transaction (ruling R9-A1 (A))."""
    return await catalog_all.outside(conn)


def _effect(before, after, shared_before, shared_after, xid):
    """The effect of a position that kept its transaction: 'CATALOG:' and the
    catalogs whose measured rows differ; else 'SHARED:' and the shared
    catalogs whose rows outside RESTRICT differ; else 'WRITE:xid' when the
    transaction was assigned an xid (it wrote something no catalog reading
    shows: a stored password, which pg_roles masks; round 10, report
    catalog_all.py:138); else 'OK'."""
    k = catalog_all.keys({"added": sorted(after - before), "removed": sorted(before - after)})
    if k:
        return "CATALOG:" + ",".join(k)
    s = catalog_all.keys({"added": sorted(shared_after - shared_before),
                          "removed": sorted(shared_before - shared_after)})
    if s:
        return "SHARED:" + ",".join(s)
    return "WRITE:xid" if xid else "OK"


async def _verdict(conn, pos, monitor_dsn):
    """The position's transaction identity at its end (catalog_position):
    'ENDED:<token,vxid>' when the program ended the harness transaction
    (an effect, whatever else it did: round 10, report
    test_r7_ro_role_pg.py:257), else None; with the reading."""
    seen = await catalog_position.check(conn, pos, monitor_dsn)
    return (catalog_position.ended_effect(seen["ended"]) if seen["ended"] else None), seen


async def raw_attempt(dsn, layer, body, expect=None):
    """`body(conn)` on a fresh asyncpg connection, in a REPEATABLE READ
    transaction that is always rolled back; 'OK' or the SQLSTATE PostgreSQL
    returned. The position is bound to its transaction at both ends
    (catalog_position): a body that ends it returns 'ENDED:...' on the
    success and on the error path alike. With `expect`, the connection's
    identity is asserted first, and the catalogs (and the shared rows
    outside RESTRICT) are read before and after the body (_effect: a body
    that succeeds and changes anything returns 'CATALOG:...', 'SHARED:...'
    or 'WRITE:xid', not 'OK'). The connection is closed after the attempt:
    no session state a body leaves reaches another attempt."""
    conn = await asyncpg.connect(dsn)
    try:
        if expect is not None:
            assert_identity(await conn.fetchrow(WHO_SQL), expect)
        if layer == GRANT_ONLY:
            await conn.execute("SET default_transaction_read_only = off")
        tr = conn.transaction(isolation="repeatable_read")
        await tr.start()
        try:
            if layer == GRANT_ONLY:
                await conn.execute("SET TRANSACTION READ WRITE")
            ro = await conn.fetchval("SHOW transaction_read_only")
            assert ro == ("on" if layer == PROVISIONED else "off"), (layer, ro)
            pos = await catalog_position.start(conn)
            before = await _catalog(conn) if expect is not None else None
            shared = await _shared(conn) if expect is not None else None
            try:
                await body(conn)
            except asyncpg.PostgresError as e:
                ended, _seen = await _verdict(conn, pos, dsn)
                return ended or e.sqlstate
            ended, seen = await _verdict(conn, pos, dsn)
            if ended:
                return ended
            if expect is None:
                return "OK"
            return _effect(before, await _catalog(conn), shared, await _shared(conn), seen["xid"])
        finally:
            await tr.rollback()
    finally:
        await conn.close()


class _Base(DeclarativeBase):
    pass


class RfRow(_Base):
    __tablename__ = "rf_t"
    __table_args__ = {"schema": "public"}
    id: Mapped[int] = mapped_column(primary_key=True)
    x: Mapped[int]


async def orm_attempt(dsn, layer, prog, expect=None):
    """`prog(db)` on a SQLAlchemy AsyncSession over asyncpg (the repo's
    driver), in a REPEATABLE READ transaction always rolled back; 'OK' or
    the SQLSTATE. The position is bound to its transaction at both ends on
    the session's own driver connection (catalog_position; 'ENDED:...' when
    the program ended it, a session commit included). With `expect`, the
    session's identity is asserted first, and the catalogs and the shared
    rows outside RESTRICT are read before and after the program, inside its
    transaction (_effect). The engine has no pool and is disposed after the
    attempt: its connection is never reused.

    On the error path the position is read when the error is raised, in the
    engine's handle_error event, before SQLAlchemy's own error handling runs:
    a failed flush makes the session roll back its transaction, and a
    position read after that would report the session's rollback as the
    program ending the transaction."""
    engine = create_async_engine(dsn.replace("postgresql://", "postgresql+asyncpg://"),
                                 poolclass=NullPool, isolation_level="REPEATABLE READ")
    held, at_error = [], []

    @event.listens_for(engine.sync_engine, "handle_error")
    def _position_at_error(ctx):
        if not held or at_error:
            return
        try:
            at_error.append(ctx.connection.connection.dbapi_connection.run_async(
                lambda c: catalog_position.check(c, held[0], dsn)))
        except Exception as exc:  # the reading itself failed: never admitted
            at_error.append({"ended": ["unread:%s" % type(exc).__name__], "xid": None, "via": "error"})
    if layer == GRANT_ONLY:
        @event.listens_for(engine.sync_engine, "connect")
        def _rw(dbapi_conn, _rec):
            dbapi_conn.run_async(
                lambda c: c.execute("SET default_transaction_read_only = off"))
    sm = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sm() as db:
            try:
                if layer == GRANT_ONLY:
                    await db.execute(text("SET TRANSACTION READ WRITE"))
                if expect is not None:
                    assert_identity((await db.execute(text(WHO_SQL))).one(), expect)
                ro = (await db.execute(text("SHOW transaction_read_only"))).scalar()
                assert ro == ("on" if layer == PROVISIONED else "off"), (layer, ro)
                driver = (await (await db.connection()).get_raw_connection()).driver_connection
                pos = await catalog_position.start(driver)
                before = await _catalog(driver) if expect is not None else None
                shared = await _shared(driver) if expect is not None else None
                held.append(pos)
                try:
                    await prog(db)
                except DBAPIError as e:
                    if at_error:
                        seen = at_error[0]
                        ended = catalog_position.ended_effect(seen["ended"]) if seen["ended"] else None
                    else:
                        ended, _seen = await _verdict(driver, pos, dsn)
                    return ended or _sqlstate(e)
                ended, seen = await _verdict(driver, pos, dsn)
                if ended:
                    return ended
                if expect is None:
                    return "OK"
                return _effect(before, await _catalog(driver), shared, await _shared(driver), seen["xid"])
            finally:
                await db.rollback()
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- classes

def _sql(stmt):
    async def body(conn):
        await conn.execute(stmt)
    return body


async def _copy_from_stdin(conn):
    await conn.copy_records_to_table("rf_t", schema_name="public", records=[(60, 60)])


async def _formatted_update(conn):
    tbl = "public.rf_t"
    await conn.execute("UPDATE {tbl} SET x = 3".format(tbl=tbl))


async def _formatted_function(conn):
    fn = "lo_create"
    await conn.fetchval("SELECT {fn}(0)".format(fn=fn))


async def _orm_add_flush(db):
    db.add(RfRow(id=70, x=70))
    await db.flush()


# The two locks the real admission path takes before it can refuse, copied
# verbatim from backend/api/main.py (test_lock_texts_are_main_py_verbatim
# re-reads them there).
GATE_LOCK_SQL = ("SELECT id FROM players WHERE id = CAST(:pid AS uuid) "
                 "FOR NO KEY UPDATE")
CLAIM_LOCK_SQL = "SELECT status, series_id FROM ffa_queue WHERE player_id = :pid FOR UPDATE"


async def _gate_lock(db):
    await db.execute(text(GATE_LOCK_SQL), {"pid": PID})


async def _claim_lock(db):
    await db.execute(text(CLAIM_LOCK_SQL), {"pid": PID})


RAW = "raw"
ORM = "orm"
CLASSES = collections.OrderedDict([
    ("update", (RAW, _sql("UPDATE public.rf_t SET x = x + 1"))),
    ("insert", (RAW, _sql("INSERT INTO public.rf_t VALUES (50, 50)"))),
    ("delete", (RAW, _sql("DELETE FROM public.rf_t WHERE id = 1"))),
    ("truncate", (RAW, _sql("TRUNCATE public.rf_t"))),
    ("update_other_schema", (RAW, _sql("UPDATE rf_s.t SET x = 5"))),
    ("insert_public_granted", (RAW, _sql("INSERT INTO public.rf_pub VALUES (1)"))),
    ("create_table", (RAW, _sql("CREATE TABLE public.rf_new (i int)"))),
    ("create_table_other_schema", (RAW, _sql("CREATE TABLE rf_s.rf_new (i int)"))),
    ("create_temp_table", (RAW, _sql("CREATE TEMP TABLE rf_tmp (i int)"))),
    ("create_schema", (RAW, _sql("CREATE SCHEMA rf_new_schema"))),
    ("create_function", (RAW, _sql("CREATE FUNCTION public.rf_new_fn() RETURNS int "
                                   "LANGUAGE sql AS 'SELECT 1'"))),
    ("lo_create", (RAW, _sql("SELECT lo_create(0)"))),
    ("lo_from_bytea", (RAW, _sql("SELECT lo_from_bytea(0, 'ab'::bytea)"))),
    ("nextval", (RAW, _sql("SELECT nextval('public.rf_seq')"))),
    ("setval", (RAW, _sql("SELECT setval('public.rf_seq', 5)"))),
    ("nextval_public_granted", (RAW, _sql("SELECT nextval('public.rf_pubseq')"))),
    ("select_into", (RAW, _sql("SELECT * INTO public.rf_into FROM public.rf_t"))),
    ("copy_from_stdin", (RAW, _copy_from_stdin)),
    ("do_update", (RAW, _sql("DO $$BEGIN UPDATE public.rf_t SET x = 7; END$$"))),
    ("formatted_update", (RAW, _formatted_update)),
    ("formatted_function", (RAW, _formatted_function)),
    ("for_update", (RAW, _sql("SELECT id FROM public.rf_t WHERE id = 1 FOR UPDATE"))),
    ("for_no_key_update", (RAW, _sql("SELECT id FROM public.rf_t WHERE id = 1 "
                                     "FOR NO KEY UPDATE"))),
    ("for_share", (RAW, _sql("SELECT id FROM public.rf_t WHERE id = 1 FOR SHARE"))),
    ("for_key_share", (RAW, _sql("SELECT id FROM public.rf_t WHERE id = 1 "
                                 "FOR KEY SHARE"))),
    ("secdef_call", (RAW, _sql("SELECT public.rf_secdef_write()"))),
    ("orm_add_flush", (ORM, _orm_add_flush)),
    ("gate_players_lock", (ORM, _gate_lock)),
    ("claim_ffa_queue_lock", (ORM, _claim_lock)),
])

# Measured on PostgreSQL 16.9 (127.0.0.1:55432). 25006 read_only_sql_transaction,
# 42501 insufficient_privilege. A function's EXECUTE privilege is checked when
# the expression is initialised, before the function body's own read-only
# check, so a revoked large-object writer is 42501 in both layers; nextval and
# setval check the sequence privilege, and COPY FROM the table privilege, before
# the read-only check, so those are 42501 in both layers too.
EXPECTED = {}
for _c in CLASSES:
    EXPECTED[(_c, PROVISIONED)] = "25006"
    EXPECTED[(_c, GRANT_ONLY)] = "42501"
for _c in ("lo_create", "lo_from_bytea", "formatted_function", "secdef_call",
           "nextval", "setval", "nextval_public_granted", "copy_from_stdin"):
    EXPECTED[(_c, PROVISIONED)] = "42501"


async def _attempt(dsn, layer, cls, expect=None):
    kind, body = CLASSES[cls]
    return await (raw_attempt if kind == RAW else orm_attempt)(dsn, layer, body, expect)


def test_expected_table_is_whole_and_never_ok():
    assert set(EXPECTED) == {(c, l) for c in CLASSES for l in LAYERS}
    assert all(v != "OK" for v in EXPECTED.values())


@pytest.mark.parametrize("layer", LAYERS)
@pytest.mark.parametrize("cls", list(CLASSES))
def test_write_class_refused_under_role(env, cls, layer):
    got = run(_attempt(env["ro_dsn"], layer, cls, ro_role.ROLE))
    assert got == EXPECTED[(cls, layer)], (
        "write class %s, layer %s: PostgreSQL returned %s, expected %s"
        % (cls, layer, got, EXPECTED[(cls, layer)]))


@pytest.mark.parametrize("cls", list(CLASSES))
def test_write_class_succeeds_under_admin(plain, cls):
    """The control is a real write: valid, and applied where the privilege
    exists (rolled back)."""
    assert run(_attempt(plain["admin_db_dsn"], GRANT_ONLY, cls)) == "OK"


@pytest.mark.parametrize("layer", LAYERS)
def test_role_reads(env, layer):
    """Positive control: the role is confined to reads, not refused
    everything."""
    async def body(conn):
        assert await conn.fetchval("SELECT count(*) FROM public.rf_t") == 2
        assert await conn.fetchval("SELECT count(*) FROM public.rf_v") == 2
        assert await conn.fetchval("SELECT count(*) FROM rf_s.t") == 1
        assert await conn.fetchval("SELECT count(*) FROM rf_priv.t") == 1
        # nextval/setval are not rolled back, so the admin controls move it.
        assert await conn.fetchval("SELECT last_value FROM public.rf_seq") >= 1
        assert await conn.fetchval("SELECT abs(-3)") == 3
    assert run(raw_attempt(env["ro_dsn"], layer, body, ro_role.ROLE)) == "OK"


# E4 (ruling REHEARSAL-R8-A1): the role changing its own persistent default,
# the reviewer's example (application_name) and E1's (work_mem). PostgreSQL
# refuses it in the read-only layer; past READ WRITE it lets an ordinary role
# do it, and the catalog reading exposes it. The attempt is rolled back, and
# the key is RESET (that key only, never the role: the role's own
# default_transaction_read_only lives in the same setconfig array) in a
# finally block; the role's setconfig must read the same before and after.
ROLE_DEFAULT_CONTROLS = (("application_name", "'rf9_probe'"), ("work_mem", "'63MB'"))
ROLE_DEFAULT_EXPECTED = {PROVISIONED: "25006", GRANT_ONLY: "CATALOG:pg_db_role_setting"}


async def _role_setconfig(dsn, role):
    """The role's database-independent setconfig (pg_db_role_setting), or None."""
    conn = await asyncpg.connect(dsn)
    try:
        got = await conn.fetchval(
            "SELECT s.setconfig FROM pg_catalog.pg_db_role_setting s JOIN pg_catalog.pg_roles r "
            "ON r.oid = s.setrole WHERE s.setdatabase = 0 AND r.rolname = $1", role)
        return list(got) if got is not None else None
    finally:
        await conn.close()


async def _reset_own_key(ro_dsn, key):
    """ALTER ROLE CURRENT_USER RESET key, as the role itself."""
    conn = await asyncpg.connect(ro_dsn)
    try:
        assert_identity(await conn.fetchrow(WHO_SQL), ro_role.ROLE)
        await conn.execute("SET default_transaction_read_only = off")
        await conn.execute("ALTER ROLE CURRENT_USER RESET %s" % key)
    finally:
        await conn.close()


def _alter_own_default(route, key, value):
    """The control's program for each route: the raw asyncpg body, or the
    SQLAlchemy session program (its catalog reading runs on the session's own
    driver connection)."""
    stmt = "ALTER ROLE CURRENT_USER SET %s = %s" % (key, value)
    if route == RAW:
        return _sql(stmt)

    async def prog(db):
        await db.execute(text(stmt))
    return prog


@pytest.mark.parametrize("layer", LAYERS)
@pytest.mark.parametrize("route", (RAW, ORM))
@pytest.mark.parametrize("key,value", ROLE_DEFAULT_CONTROLS, ids=[k for k, _v in ROLE_DEFAULT_CONTROLS])
def test_role_default_change_is_exposed_by_the_write_bound(env, key, value, route, layer):
    before = run(_role_setconfig(env["admin_ro_db_dsn"], ro_role.ROLE))
    assert before is not None and "default_transaction_read_only=on" in before, before
    # round 10 (report catalog_all.py:99, swept by class): the role's
    # settings in every database, not only the database-independent ones
    every_before = run(_role_settings(env["admin_ro_db_dsn"], ro_role.ROLE))
    assert not [s for s in before if s.startswith(key + "=")], (
        "%s already carries %s in its setconfig %s: the control does not plant over it"
        % (ro_role.ROLE, key, before))
    try:
        got = run((raw_attempt if route == RAW else orm_attempt)(
            env["ro_dsn"], layer, _alter_own_default(route, key, value), ro_role.ROLE))
    finally:
        run(_reset_own_key(env["ro_dsn"], key))
        after = run(_role_setconfig(env["admin_ro_db_dsn"], ro_role.ROLE))
        every_after = run(_role_settings(env["admin_ro_db_dsn"], ro_role.ROLE))
    assert after == before, (before, after)
    assert every_after == every_before, (every_before, every_after)
    assert got == ROLE_DEFAULT_EXPECTED[layer], (
        "ALTER ROLE CURRENT_USER SET %s, route %s, layer %s: %s, expected %s"
        % (key, route, layer, got, ROLE_DEFAULT_EXPECTED[layer]))


@pytest.mark.parametrize("layer", LAYERS)
def test_role_reads_through_the_orm_change_no_catalog(env, layer):
    """Positive control of the ORM route's catalog reading: a read through a
    SQLAlchemy session under the role returns 'OK' (no catalog row moved)."""
    async def prog(db):
        assert (await db.execute(text("SELECT count(*) FROM public.rf_t"))).scalar() == 2
    assert run(orm_attempt(env["ro_dsn"], layer, prog, ro_role.ROLE)) == "OK"


def test_r9_role_harness_reports_a_program_that_ends_it(env):
    """raw_attempt and orm_attempt (round 9's refusal, restated in round 10):
    a body that ends the harness transaction is reported as an effect,
    'ENDED:...', on both routes and both layers, with and without the
    catalog reading; never 'OK' and never a SQLSTATE. The bodies commit an
    empty transaction: nothing reaches the database."""
    async def raw_body(conn):
        await conn.execute("COMMIT")

    async def orm_prog(db):
        await db.commit()

    for layer in (PROVISIONED, GRANT_ONLY):
        for got in (run(raw_attempt(env["ro_dsn"], layer, raw_body)),
                    run(orm_attempt(env["ro_dsn"], layer, orm_prog)),
                    run(raw_attempt(env["ro_dsn"], layer, raw_body, ro_role.ROLE)),
                    run(orm_attempt(env["ro_dsn"], layer, orm_prog, ro_role.ROLE))):
            assert got.startswith("ENDED:"), (layer, got)


# Round 10, report test_r7_ro_role_pg.py:257: round 9 checked only that SOME
# transaction was open when the program returned, so a program that ended the
# harness transaction and began another one passed as unchanged. Each body
# here ends the harness transaction; every one must come back 'ENDED:...',
# on the success path and on the error path alike.
R10_ENDING_RAW = collections.OrderedDict([
    ("commit_begin", "SET application_name = 'r9_probe'; COMMIT; BEGIN; RESET application_name"),
    ("commit_and_chain", "COMMIT AND CHAIN"),
    ("rollback_and_chain", "ROLLBACK AND CHAIN"),
    ("rollback", "ROLLBACK"),
    ("end_begin", "END; BEGIN"),
    ("abort_begin", "ABORT; BEGIN"),
    ("prepare_transaction", "PREPARE TRANSACTION 'rf10_cat_prep'"),
    ("commit_begin_error", "COMMIT; BEGIN; SELECT 1 / 0"),
])


async def _orm_commit_begin(db):
    await db.execute(text("SET application_name = 'r9_probe'"))
    await db.commit()
    await db.execute(text("RESET application_name"))


async def _orm_commit_begin_error(db):
    await db.commit()
    await db.execute(text("SELECT 1 / 0"))


def _orm_text(stmt):
    async def prog(db):
        await db.execute(text(stmt))
    return prog


def _orm_text_pair(first, second):
    async def prog(db):
        await db.execute(text(first))
        await db.execute(text(second))
    return prog


def _orm_text_then_flush(stmt):
    """stmt, then a flush that fails (a duplicate key): SQLAlchemy rolls its
    session back after the failed flush, after the position is read."""
    async def prog(db):
        await db.execute(text(stmt))
        await db.execute(text("BEGIN"))
        db.add(RfRow(id=1, x=1))
        await db.flush()
    return prog


R10_ENDING_ORM = collections.OrderedDict([
    ("commit_begin", _orm_commit_begin),
    ("text_commit_then_begin", _orm_text_pair("COMMIT", "BEGIN")),
    ("text_commit_then_flush_error", _orm_text_then_flush("COMMIT")),
    ("commit_and_chain", _orm_text("COMMIT AND CHAIN")),
    ("rollback_and_chain", _orm_text("ROLLBACK AND CHAIN")),
    ("rollback", _orm_text("ROLLBACK")),
    ("prepare_transaction", _orm_text("PREPARE TRANSACTION 'rf10_cat_prep'")),
    ("commit_begin_error", _orm_commit_begin_error),
])


@pytest.mark.parametrize("layer", LAYERS)
@pytest.mark.parametrize("name", list(R10_ENDING_RAW))
def test_r10_n_ro_role_257_raw(env, name, layer):
    got = run(raw_attempt(env["ro_dsn"], layer, _sql(R10_ENDING_RAW[name]), ro_role.ROLE))
    assert got.startswith("ENDED:"), (name, layer, got)


@pytest.mark.parametrize("layer", LAYERS)
@pytest.mark.parametrize("name", list(R10_ENDING_ORM))
def test_r10_n_ro_role_257_orm(env, name, layer):
    got = run(orm_attempt(env["ro_dsn"], layer, R10_ENDING_ORM[name], ro_role.ROLE))
    assert got.startswith("ENDED:"), (name, layer, got)


def test_r10_ro_role_257_negative_control(env):
    """The same harness, a body that keeps its transaction: 'OK'."""
    for layer in LAYERS:
        assert run(raw_attempt(env["ro_dsn"], layer, _sql("SELECT 1; SELECT 2"), ro_role.ROLE)) == "OK"
        assert run(orm_attempt(env["ro_dsn"], layer, _orm_text("SELECT 1"), ro_role.ROLE)) == "OK"


def test_r10_prepare_transaction_outcome_on_this_cluster(env):
    """PREPARE TRANSACTION on the measured cluster: with max_prepared_transactions
    0 it returns 55000 and the transaction is gone (PostgreSQL ends a
    transaction whose PREPARE fails); the harness reports that position
    ENDED (test_r10_n_ro_role_257_*[prepare_transaction])."""
    async def probe():
        conn = await asyncpg.connect(env["ro_dsn"])
        try:
            limit = await conn.fetchval("SHOW max_prepared_transactions")
            await conn.execute("BEGIN; SET LOCAL application_name = 'rf10_inside'")
            try:
                await conn.execute("PREPARE TRANSACTION 'rf10_cat_prep'")
                state = "prepared"
            except asyncpg.PostgresError as e:
                state = e.sqlstate
            # the next statement runs (no 25P02) and no longer sees the
            # transaction's SET LOCAL: the transaction ended with the failure
            name = await conn.fetchval("SHOW application_name")
            return limit, state, conn.is_in_transaction(), name
        finally:
            await conn.close()
    limit, state, open_after, name = run(probe())
    print("r10 PREPARE TRANSACTION: max_prepared_transactions=%s, outcome %s, transaction open after: %s, "
          "application_name after: %r" % (limit, state, open_after, name))
    assert limit == "0", limit
    assert state == "55000", state
    assert open_after is False and name != "rf10_inside", (open_after, name)


# Round 10, reports catalog_all.py:99 (the measured role's settings in another
# database) and catalog_all.py:138 (a stored password). These plant only on an
# rf10_* role a run created: the stand-in measurer itself (rf10_cat_gate,
# rf10_w30b_gate), or, under a superuser, the role R10_CAT_ROLE names. Every
# plant runs inside the harness transaction, which is rolled back, and is
# undone again in a finally block (RESET, PASSWORD NULL).

PLANT_VALUE = "rf10_cat_fixed_value"
# Round-10 plants run only on a role whose name starts with PLANT_PREFIX: a
# role created for a run, by any lane (rf10_cat_*, rf10_w30b_*). The seat
# objects and the administrators are never one; NEVER_PLANTED names them
# again so a refusal states them. A measurer that is neither a superuser nor
# an rf10_* stand-in (a seat's scr_gate: CREATEDB, not a superuser, not
# CREATEROLE) could plant only on its own role, so these cases SKIP there
# with SEAT_SKIP and run on 55432 only.
PLANT_PREFIX = "rf10_"
NEVER_PLANTED = ("postgres", "scr_gate", "scr_seat_ro", "scr_seat_ro_tmpl", "scr_seat_d2_tmpl")
SEAT_SKIP = ("round-10 plant: the measurer %s is neither a superuser nor an rf10_* stand-in, so the only role "
             "it could plant on is its own (a seat administrator's); this case runs on 55432 only, as an "
             "rf10_* stand-in or as a superuser with R10_CAT_ROLE naming an rf10_* role")


def _plant_decision(me, superuser, named):
    """The role a round-10 case plants on: an rf10_* measurer (a stand-in)
    plants on itself; a superuser plants only on the rf10_* role
    R10_CAT_ROLE names, and fails when it names none; any other measurer is
    skipped with SEAT_SKIP, never failed and never planted on."""
    if me.startswith(PLANT_PREFIX) and me not in NEVER_PLANTED:
        return me
    if not superuser:
        pytest.skip(SEAT_SKIP % me)
    if not named.startswith(PLANT_PREFIX) or named in NEVER_PLANTED:
        pytest.fail("round-10 plants run only on an rf10_* role created for the run: the measurer %s is a "
                    "superuser and R10_CAT_ROLE=%r does not name one" % (me, named))
    return named


def _other_role(me):
    """Under a stand-in, the rf10_* role R10_CAT_ROLE names, other than the
    stand-in (the target of the 42501 case)."""
    other = os.environ.get("R10_CAT_ROLE") or ""
    assert other.startswith(PLANT_PREFIX) and other not in NEVER_PLANTED and other != me, (
        "R10_CAT_ROLE must name an rf10_* role other than the stand-in: %r" % other)
    return other


def test_r10_plant_decision_admits_any_rf10_role_and_skips_a_seat_admin():
    """W30b's form: any lane's rf10_* stand-in or planted role is admitted;
    a seat administrator (not a superuser, not rf10_*) is skipped with the
    stated reason; a superuser with no rf10_* R10_CAT_ROLE fails; no seat
    object, administrator or other role is ever returned."""
    assert _plant_decision("rf10_w30b_gate", False, "") == "rf10_w30b_gate"
    assert _plant_decision("rf10_cat_gate", False, "rf10_cat_pw_1") == "rf10_cat_gate"
    assert _plant_decision("postgres", True, "rf10_w30b_pw_1") == "rf10_w30b_pw_1"
    for seat_admin in ("scr_gate", "scr_seat_ro"):
        with pytest.raises(pytest.skip.Exception) as e:
            _plant_decision(seat_admin, False, "rf10_w30b_pw_1")
        assert "55432 only" in str(e.value) and seat_admin in str(e.value), e.value
    for named in ("", "scr_seat_ro", "postgres", "scr_gate", "scr_seat_d2_tmpl", "rf9_x", "RF10_x", "xrf10_"):
        with pytest.raises(pytest.fail.Exception):
            _plant_decision("postgres", True, named)


async def _who(dsn):
    conn = await asyncpg.connect(dsn)
    try:
        return await conn.fetchrow("SELECT current_user::text AS me, "
                                   "(SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname = current_user) AS su")
    finally:
        await conn.close()


def _plant_role(dsn):
    """(measurer, planted role, superuser), by _plant_decision."""
    w = run(_who(dsn))
    role = _plant_decision(w["me"], bool(w["su"]), os.environ.get("R10_CAT_ROLE") or "")
    return w["me"], role, bool(w["su"])


def _ident(role):
    return '"%s"' % role


async def _admin_exec(dsn, stmt):
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(stmt)
    finally:
        await conn.close()


async def _role_settings(dsn, role):
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT s.setdatabase::int8 AS db, s.setconfig::text AS cfg FROM pg_catalog.pg_db_role_setting s "
            "JOIN pg_catalog.pg_roles r ON r.oid = s.setrole WHERE r.rolname = $1 ORDER BY 1", role)
        return [(r["db"], r["cfg"]) for r in rows]
    finally:
        await conn.close()


def _prog(route, stmt):
    return _sql(stmt) if route == RAW else _orm_text(stmt)


@pytest.mark.parametrize("route", (RAW, ORM))
def test_r10_n_ro_role_catalog_all_99(env, route):
    """ALTER ROLE <measured or planted role> IN DATABASE postgres SET, in the
    grant_only layer: the stand-in sees its own row (RESTRICT now keys
    pg_db_role_setting on the role in every database: 'CATALOG:...'); a
    superuser sees the planted role's row among the shared rows outside
    RESTRICT ('SHARED:...'). Round 9 filtered the row to this database and
    returned 'OK'."""
    dsn = env["admin_ro_db_dsn"]
    me, role, su = _plant_role(dsn)
    target = "CURRENT_USER" if role == me else _ident(role)
    before = run(_role_settings(dsn, role))
    try:
        got = run((raw_attempt if route == RAW else orm_attempt)(
            dsn, GRANT_ONLY, _prog(route, "ALTER ROLE %s IN DATABASE postgres SET application_name = 'r9_probe'"
                                   % target), me))
    finally:
        run(_admin_exec(dsn, "ALTER ROLE %s IN DATABASE postgres RESET application_name" % target))
    assert run(_role_settings(dsn, role)) == before, before
    want = "SHARED:pg_db_role_setting" if role != me else "CATALOG:pg_db_role_setting"
    print("r10 catalog_all.py:99 route %s, measurer %s, planted %s: %s" % (route, me, role, got))
    assert got == want, (route, me, role, got)


@pytest.mark.parametrize("route", (RAW, ORM))
def test_r10_n_ro_role_catalog_all_138(env, route):
    """ALTER ROLE <role> PASSWORD '<fixed value>' in the grant_only layer.
    Under a superuser (rolpassword route 'digest') the planted role's stored
    value is compared as its md5 among the shared rows outside RESTRICT:
    'SHARED:pg_authid'. Under the stand-in (route 'unmeasured': pg_roles masks
    it) the change to its own password reaches no catalog reading and is
    reported by its xid: 'WRITE:xid'. Round 9 returned 'OK' on both."""
    dsn = env["admin_ro_db_dsn"]
    me, role, su = _plant_role(dsn)
    route_name = run(_routes(dsn))["rolpassword"]
    assert route_name == ("digest" if su else "unmeasured"), (su, route_name)
    try:
        got = run((raw_attempt if route == RAW else orm_attempt)(
            dsn, GRANT_ONLY, _prog(route, "ALTER ROLE %s PASSWORD '%s'" % (_ident(role), PLANT_VALUE)), me))
    finally:
        run(_admin_exec(dsn, "ALTER ROLE %s PASSWORD NULL" % _ident(role)))
    print("r10 catalog_all.py:138 route %s, measurer %s (rolpassword %s), planted %s: %s"
          % (route, me, route_name, role, got))
    assert got == ("SHARED:pg_authid" if su else "WRITE:xid"), (route, me, role, got)


def test_r10_n_ro_role_catalog_all_138_other_role(env):
    """Under the stand-in, another role's password is out of reach: ALTER ROLE
    on R10_CAT_ROLE returns 42501 (no CREATEROLE), so the unmeasured field
    cannot be changed for any role but the measurer's own. Under a superuser
    this case is the digest route above."""
    dsn = env["admin_ro_db_dsn"]
    w = run(_who(dsn))
    if w["su"]:
        print("r10 catalog_all.py:138 other role: measurer %s is a superuser; the digest route covers it" % w["me"])
        return
    if not w["me"].startswith(PLANT_PREFIX):
        pytest.skip(SEAT_SKIP % w["me"])
    other = _other_role(w["me"])
    got = run(raw_attempt(dsn, GRANT_ONLY, _sql("ALTER ROLE %s PASSWORD '%s'" % (_ident(other), PLANT_VALUE)),
                          w["me"]))
    print("r10 catalog_all.py:138 other role %s under %s: %s" % (other, w["me"], got))
    assert got == "42501", got


async def _routes(dsn):
    conn = await asyncpg.connect(dsn)
    try:
        return await catalog_all.routes(conn)
    finally:
        await conn.close()


def test_r10_routes_state_this_run(env):
    """The run's measurer and its routes (catalog_all.routes), printed for the
    log of record: rolpassword 'digest' under a superuser, else
    'unmeasured', with pg_authid.rolpassword in the unmeasured list."""
    r = run(_routes(env["admin_ro_db_dsn"]))
    print("r10 routes: measurer %s superuser %s rolpassword %s; outside RESTRICT: %s; unmeasured: %s"
          % (r["measurer"], r["superuser"], r["rolpassword"], r["outside_restrict"], r["unmeasured"]))
    assert r["rolpassword"] == ("digest" if r["superuser"] else "unmeasured"), r
    assert (("pg_authid", "rolpassword") in [(u[0], u[1]) for u in r["unmeasured"]]) == (not r["superuser"]), r


def test_privilege_census_is_empty(env):
    rep = env["report"]
    assert any(s.startswith("rf_secdef_write") or ".rf_secdef_write" in s
               for s in rep["secdef_revoked"]), rep["secdef_revoked"]
    assert set(rep["schemas"]) == {"public", "rf_s", "rf_priv"}, rep["schemas"]
    # The template's large-object revokes, carried into the clone: every
    # overload of every writer (12 on PostgreSQL 16), none executable.
    writers, executable = run(ro_role.template_lo_state(ADMIN_DSN, env["db"]))
    assert writers >= len(ro_role.LO_WRITERS) and executable == 0, (writers, executable)
    found = run(ro_role.privilege_census(ADMIN_DSN, env["db"], env["role"]))
    assert found == [], found


def test_cluster_read_names_what_is_missing():
    """read_cluster's sentences are the module's failure text: an absent
    role or template is named (nothing is created to show it)."""
    got = run(ro_role.read_cluster(ADMIN_DSN, role="rf8_ro_absent_role",
                                   template="rf8_ro_absent_tmpl"))
    assert got == [
        "the role rf8_ro_absent_role does not exist on this cluster (provision.sql "
        "step 1 has not run here)",
        "the template database rf8_ro_absent_tmpl does not exist on this cluster "
        "(provision.sql step 2 has not run here)"], got
    # The postgres database exists on every cluster and initdb makes it no
    # template; provisioning never changes it, so its sentence is named on
    # every cluster.
    got = run(ro_role.read_cluster(ADMIN_DSN, template="postgres"))
    assert "the template postgres has datistemplate=False, provisioned as True" in got, got
    # template1's sentences are exactly the properties a separate read finds
    # unmet: PUBLIC may CONNECT to it on 55432, and a seat may have revoked
    # that, so the expectation is read, not assumed.
    got = run(ro_role.read_cluster(ADMIN_DSN, template="template1"))
    want = run(_template_unmet(ADMIN_DSN, "template1"))
    assert got == want, (got, want)


async def _template_unmet(dsn, template):
    """The provisioned template properties `template` does not hold, read
    through pg_roles and the expanded ACL (not ro_role.TEMPLATE_SQL), in
    read_cluster's sentence form."""
    conn = await asyncpg.connect(ro_role.dsn_for(dsn, "postgres"))
    try:
        r = await conn.fetchrow(
            "SELECT d.datistemplate, o.rolname AS owner, EXISTS (SELECT 1 FROM "
            "aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) a "
            "WHERE a.grantee = 0 AND a.privilege_type = 'CONNECT') AS public_connect "
            "FROM pg_database d JOIN pg_roles o ON o.oid = d.datdba WHERE d.datname = $1",
            template)
    finally:
        await conn.close()
    want = (("datistemplate", True), ("owner", "postgres"), ("public_connect", False))
    return ["the template %s has %s=%r, provisioned as %r" % (template, k, r[k], v)
            for k, v in want if r[k] != v]


def test_identity_assertion_refuses_another_role(env):
    """Control (R7-A1 M2): the identity assertion on a covered path, with the
    connection opened as the admin role, fails."""
    async def body(conn):
        await conn.fetchval("SELECT count(*) FROM public.rf_t")
    with pytest.raises(AssertionError, match="not as scr_seat_ro"):
        run(raw_attempt(env["admin_ro_db_dsn"], GRANT_ONLY,
                        body, ro_role.ROLE))
    with pytest.raises(AssertionError, match="not as scr_seat_ro"):
        run(orm_attempt(env["admin_ro_db_dsn"], GRANT_ONLY, _gate_lock, ro_role.ROLE))
    # ...and the role's own connection passes it.
    assert run(raw_attempt(env["ro_dsn"], PROVISIONED, body, ro_role.ROLE)) == "OK"


def test_lock_texts_are_main_py_verbatim():
    src = open(os.path.join(BACKEND, "api", "main.py"), encoding="utf-8").read()
    assert src.count('"SELECT id FROM players WHERE id = CAST(:pid AS uuid) "\n'
                     '                "FOR NO KEY UPDATE"') == 1
    # main.py carries this literal twice: _rdm_claim and one other function
    # (_ffa_lobby_enroll_caller, line 59215 at a30d37f6), both FOR UPDATE.
    assert src.count('"' + CLAIM_LOCK_SQL + '"') == 2


# ------------------------------------------------- prior-finding programs

Q = "SELECT 1"   # the module constant the r4 closed_walk:322 / r5 a1:665 local masks


def _row(n):
    return RfRow(id=n, x=n)


async def p_r2_a1_590(db):
    await db.execute(text("SELECT lo_create(0)"))


async def p_r3_a1_672(db):
    await db.execute(text('SELECT "lo_create"(0)'))


async def p_r3_gate_179(db):
    await db.execute(text("SELECT '/*' || lo_create(0)::text || '*/'"))


async def p_r4_cw_712(db):
    def helper(session, row):
        session.add(row)
    helper(db, _row(80))
    await db.flush()


async def p_r4_cw_322(db):
    Q = "UPDATE public.rf_t SET x=1"
    await db.execute(text(Q))


async def p_r4_cw_345(db):
    name = "abs"
    if name in ("abs",):
        name = "lo_create(0)"
        await db.execute(text(f"SELECT {name}"))


async def p_r4_gate_245(db):
    class Ctx:
        pass
    ctx = Ctx()
    ctx.db = db

    async def _rdm_claim(ctx, _answer):
        await ctx.db.flush()
    await _rdm_claim(ctx, ctx.db.add(_row(81)))


async def p_r4_mtd_138(db):
    await db.execute(text("SELECT 1 -- comment\r, lo_create(0)"))


async def p_r5_a1_665(db):
    Q = "UPDATE public.rf_t SET x=1"
    await db.execute(text(Q))


async def p_r5_cw_1005(db):
    s = db
    s.add(_row(82))
    await s.flush()


async def p_r5_cw_501_else(db):
    allowed = ("abs",)
    name = "abs"
    if name not in allowed:
        raise ValueError(name)
    else:
        name = "lo_create"
    await db.execute(text(f"SELECT {name}(0)"))


async def p_r5_cw_501_mutated(db):
    allowed = ["abs"]
    allowed.append("lo_create")
    name = "lo_create"
    if name not in allowed:
        raise ValueError(name)
    await db.execute(text(f"SELECT {name}(0)"))


async def p_r5_cw_326(db):
    name = "lo_create"
    if name not in ("lo_create",):
        raise ValueError(name)
    await db.execute(text(f"SELECT {name}(0)"))


async def p_r5_cw_441(db):
    def build(mode):
        table = {"a": "SELECT 1", "b": "SELECT 2"}
        if mode in table:
            return table[mode]
        if mode == "evil":
            return "UPDATE public.rf_t SET x = 1"
        return "SELECT 0"
    await db.execute(text(build("evil")))


async def p_r6_cw_330(db):
    _T = {"a": "abs"}
    alias = _T
    alias.update(a="lo_create")
    mode = "a"
    await db.execute(text(f"SELECT {_T[mode]}(0)"))


async def p_r6_cw_727(db):
    d = collections.defaultdict(lambda: "lo_create", {"x": "abs"})
    await db.execute(text(f"SELECT {d['y']}(0)"))


async def p_r6_cw_771(db):
    g1, g2 = ("abs",), ("lo_create",)
    n1, n2 = "abs", "lo_create"
    if n1 in g1:
        assert (await db.execute(text(f"SELECT {n1}(0)"))).scalar() == 0
    if n2 in g2:
        await db.execute(text(f"SELECT {n2}(0)"))


# (round, report file:line, program, effect) -- effect names the write the
# program performs: "lo" a large-object create, "update" a row update,
# "orm" an ORM insert at flush.
FINDINGS = collections.OrderedDict([
    ("r2_a1_590", ("r2", "test_a1_identity_formation.py:590", p_r2_a1_590, "lo")),
    ("r3_a1_672", ("r3", "test_a1_identity_formation.py:672", p_r3_a1_672, "lo")),
    ("r3_gate_179", ("r3", "test_match_hold_admission_gate_pg.py:179", p_r3_gate_179, "lo")),
    ("r4_cw_712", ("r4", "closed_walk.py:712", p_r4_cw_712, "orm")),
    ("r4_cw_322", ("r4", "closed_walk.py:322", p_r4_cw_322, "update")),
    ("r4_cw_345", ("r4", "closed_walk.py:345", p_r4_cw_345, "lo")),
    ("r4_gate_245", ("r4", "test_match_hold_admission_gate_pg.py:245", p_r4_gate_245, "orm")),
    ("r4_mtd_138", ("r4", "migration_table_ddl.py:138", p_r4_mtd_138, "lo")),
    ("r5_a1_665", ("r5", "test_a1_identity_formation.py:665", p_r5_a1_665, "update")),
    ("r5_cw_1005", ("r5", "closed_walk.py:1005", p_r5_cw_1005, "orm")),
    ("r5_cw_501_else", ("r5", "closed_walk.py:501", p_r5_cw_501_else, "lo")),
    ("r5_cw_501_mutated", ("r5", "closed_walk.py:501", p_r5_cw_501_mutated, "lo")),
    ("r5_cw_326", ("r5", "closed_walk.py:326", p_r5_cw_326, "lo")),
    ("r5_cw_441", ("r5", "closed_walk.py:441", p_r5_cw_441, "update")),
    ("r6_cw_330", ("r6", "closed_walk.py:330", p_r6_cw_330, "lo")),
    ("r6_cw_727", ("r6", "closed_walk.py:727", p_r6_cw_727, "lo")),
    ("r6_cw_771", ("r6", "closed_walk.py:771", p_r6_cw_771, "lo")),
])
FINDING_EXPECTED = {
    ("lo", PROVISIONED): "42501", ("lo", GRANT_ONLY): "42501",
    ("update", PROVISIONED): "25006", ("update", GRANT_ONLY): "42501",
    ("orm", PROVISIONED): "25006", ("orm", GRANT_ONLY): "42501",
}


def test_findings_cover_the_sixteen():
    assert len({v[1] for v in FINDINGS.values()}) == 16


@pytest.mark.parametrize("layer", LAYERS)
@pytest.mark.parametrize("fid", list(FINDINGS))
def test_prior_finding_program_refused_under_role(env, fid, layer):
    rnd, where, prog, effect = FINDINGS[fid]
    got = run(orm_attempt(env["ro_dsn"], layer, prog, ro_role.ROLE))
    assert got == FINDING_EXPECTED[(effect, layer)], (
        "%s %s (%s), layer %s: PostgreSQL returned %s" % (rnd, where, fid, layer, got))


@pytest.mark.parametrize("fid", list(FINDINGS))
def test_prior_finding_program_writes_under_admin(plain, fid):
    """The program really writes: under the admin DSN it succeeds (rolled
    back), so the role's refusal is the only thing stopping it."""
    assert run(orm_attempt(plain["admin_db_dsn"], GRANT_ONLY, FINDINGS[fid][2])) == "OK"


# ---------------------------------------------------------- DSN census

# The census roots (brief item 4) and the local modules they import,
# transitively (the closure computed once by RF/r7/ro/import_closure.py and
# frozen here). Paths relative to backend/.
CENSUS_FILES = (
    "api/admin_evidence.py", "api/auto_logs.py", "api/build_manifest.py",
    "api/card_evidence.py", "api/card_measures.py", "api/combat_evidence.py",
    "api/combat_measures.py", "api/conn_ranges.py", "api/database.py",
    "api/flag_evidence.py", "api/glicko2.py", "api/identity_clock_evidence.py",
    "api/identity_clock_measures.py", "api/log_redaction.py", "api/mail_discord.py",
    "api/main.py", "api/match_hold.py", "api/match_report_window.py", "api/models.py",
    "api/pc_face.py", "api/pc_motion.py", "api/pc_portrait.py", "api/pc_signature.py",
    "api/pc_steam.py", "api/pc_strip.py", "api/player_cards.py", "api/read_gate.py",
    "api/region_pick.py", "api/review_boot.py", "api/review_measures.py",
    "api/review_rules.py", "api/schemas.py", "api/seat_evidence.py",
    "api/steamid64.py", "api/title_ladders.py", "api/tournament_bracket.py",
    "api/tournaments.py",
    "tests/cf_pg.py", "tests/cf_pool.py", "tests/closed_walk.py",
    "tests/ladder_pg_harness.py", "tests/migration_table_ddl.py",
    "tests/pc_themes_data.py", "tests/resolution_sites.py",
    "tests/test_a1_formation_concurrency.py", "tests/test_a1_identity_formation.py",
    "tests/test_a1_predicate_sql.py", "tests/test_match_hold_admission_gate_pg.py",
    "tests/test_match_hold_pg.py", "tests/test_pc_routes.py", "tests/test_pc_sept12.py",
    "tests/test_player_cards_server.py", "tests/test_title_ladder_hooks_live.py",
    "tests/test_title_ladders.py", "tests/title_ladders_lane_schema.py",
)

# The census (ruling REHEARSAL-FOUR-R7-A1 M2): default-deny over import and
# opener forms, ro_census.forms per file, equal to the frozen multiset
# ro_census_frozen.FROZEN (taken once at 3130bb9d, never regenerated). A
# form the freeze lacks is refused by its shape; the refusal names it.

def _census_diff(root=BACKEND):
    return ro_census.diff(ro_census.census(root, CENSUS_FILES), ro_census_frozen.FROZEN)


def test_dsn_census_is_closed():
    root = os.environ.get("RF7RO_CENSUS_ROOT") or BACKEND
    got = ro_census.census(root, CENSUS_FILES)
    assert sum(len(v) for v in got.values()) == ro_census_frozen.FROZEN_COUNT
    assert ro_census.diff(got, ro_census_frozen.FROZEN) == []
    # No identity-changing SQL text anywhere in the closure, frozen or not.
    assert not [f for v in ro_census_frozen.FROZEN.values() for f in v
                if f[0] == "identity"]


# Each census refusal rule, with the program that exercises it planted into a
# covered file's text (cf_pg.py, the file the round-7 report's example
# names); the census of the planted text must refuse exactly the planted
# forms. The first row is the report's own example.
PLANTED = (
    ("aliased_import",
     "\nimport asyncpg as pg\n\nasync def _planted():\n    return await pg.connect(DSN)\n",
     {("import", "import asyncpg as pg"), ("opener", "Load pg.connect")}),
    ("bare_connect",
     "\nfrom asyncpg import connect\n\nasync def _planted():\n"
     "    return await connect(DSN)\n",
     {("import", "from asyncpg import connect"), ("opener", "alias connect"),
      ("opener", "Load connect")}),
    ("user_kwarg",
     "\nasync def _planted():\n    return await _asyncpg.connect(DSN, user='postgres')\n",
     {("opener", "Load _asyncpg.connect"), ("kwarg", "_asyncpg.connect user='postgres'"),
      ("dsntext", "postgres")}),
    ("rebuilt_dsn",
     "\nasync def _planted(who):\n    return DSN.replace('//', '//%s@' % who)\n",
     {("dsntext", "//%s@")}),
    ("set_role",
     "\nasync def _planted(conn):\n    await conn.execute('SET ROLE scr_gate')\n",
     {("identity", "SET ROLE scr_gate")}),
    ("session_authorization",
     "\nasync def _planted(conn):\n"
     "    await conn.execute('SET SESSION AUTHORIZATION scr_gate')\n",
     {("identity", "SET SESSION AUTHORIZATION scr_gate")}),
    ("options_role",
     "\nasync def _planted():\n"
     "    return await harness.connect_bound(DSN, 's', options='-c role=scr_gate')\n",
     {("opener", "Load harness.connect_bound"),
      ("kwarg", "harness.connect_bound options='-c role=scr_gate'"),
      ("identity", "-c role=scr_gate")}),
    ("getattr_opener",
     "\nasync def _planted():\n    return await getattr(_asyncpg, 'connect')(DSN)\n",
     {("opener", "str connect")}),
)


@pytest.mark.parametrize("name", [p[0] for p in PLANTED])
def test_dsn_census_refuses_unfrozen_form(name):
    _n, program, want = next(p for p in PLANTED if p[0] == name)
    rel = "tests/cf_pg.py"
    with open(os.path.join(BACKEND, rel), encoding="utf-8") as fh:
        src = fh.read()
    got = {rel: ro_census.forms(rel, src + program)}
    frozen = {rel: ro_census_frozen.FROZEN[rel]}
    refused = ro_census.diff(got, frozen)
    assert refused and all(r[1] == "+" for r in refused), refused
    assert {r[2:] for r in refused} == want, refused
    # Unplanted, the same file is clean (the refusal is the program's).
    assert ro_census.diff({rel: ro_census.forms(rel, src)}, frozen) == []
