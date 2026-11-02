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
It never skips: an unset DSN or a refused CREATE DATABASE fails the module.
Every role connection asserts SELECT current_user, session_user equals the
role before its body runs.

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
                    "LOGIN CREATEDB role) on the local cluster; this module never skips")
    missing = run(ro_role.read_cluster(ADMIN_DSN))
    if missing:
        pytest.fail("the cluster is not provisioned for the read-only bound: "
                    + "; ".join(missing))
    stamp = _stamp()
    name, plain = "rf8_ro_" + stamp, "rf8_ro_plain_" + stamp
    out = {"db": name, "plain_db": plain, "role": ro_role.ROLE}
    made = []

    async def setup():
        await ro_role.clone(ADMIN_DSN, name)
        made.append(name)
        await _fixture(ADMIN_DSN, name)
        out["report"] = await ro_role.grant(ADMIN_DSN, name)
        await ro_role.clone(ADMIN_DSN, plain, template="template1")
        made.append(plain)
        await _fixture(ADMIN_DSN, plain)
        out["admin_db_dsn"] = ro_role.dsn_for(ADMIN_DSN, plain)
        out["admin_ro_db_dsn"] = ro_role.dsn_for(ADMIN_DSN, name)
        out["ro_dsn"] = out["report"]["dsn"]

    try:
        run(setup())
        yield out
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


async def raw_attempt(dsn, layer, body, expect=None):
    """`body(conn)` on a fresh asyncpg connection, in a transaction that is
    always rolled back; 'OK' or the SQLSTATE PostgreSQL returned. With
    `expect`, the connection's identity is asserted first."""
    conn = await asyncpg.connect(dsn)
    try:
        if expect is not None:
            assert_identity(await conn.fetchrow(WHO_SQL), expect)
        if layer == GRANT_ONLY:
            await conn.execute("SET default_transaction_read_only = off")
        tr = conn.transaction()
        await tr.start()
        try:
            if layer == GRANT_ONLY:
                await conn.execute("SET TRANSACTION READ WRITE")
            ro = await conn.fetchval("SHOW transaction_read_only")
            assert ro == ("on" if layer == PROVISIONED else "off"), (layer, ro)
            try:
                await body(conn)
                return "OK"
            except asyncpg.PostgresError as e:
                return e.sqlstate
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
    driver), always rolled back; 'OK' or the SQLSTATE. With `expect`, the
    session's identity is asserted first."""
    engine = create_async_engine(dsn.replace("postgresql://", "postgresql+asyncpg://"),
                                 poolclass=NullPool)
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
                try:
                    await prog(db)
                    return "OK"
                except DBAPIError as e:
                    return _sqlstate(e)
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
def test_write_class_succeeds_under_admin(env, cls):
    """The control is a real write: valid, and applied where the privilege
    exists (rolled back)."""
    assert run(_attempt(env["admin_db_dsn"], GRANT_ONLY, cls)) == "OK"


@pytest.mark.parametrize("layer", LAYERS)
def test_role_reads(env, layer):
    """Positive control: the role is confined to reads, not refused
    everything."""
    async def body(conn):
        assert await conn.fetchval("SELECT count(*) FROM public.rf_t") == 2
        assert await conn.fetchval("SELECT count(*) FROM public.rf_v") == 2
        assert await conn.fetchval("SELECT count(*) FROM rf_s.t") == 1
        # nextval/setval are not rolled back, so the admin controls move it.
        assert await conn.fetchval("SELECT last_value FROM public.rf_seq") >= 1
        assert await conn.fetchval("SELECT abs(-3)") == 3
    assert run(raw_attempt(env["ro_dsn"], layer, body, ro_role.ROLE)) == "OK"


def test_privilege_census_is_empty(env):
    rep = env["report"]
    assert any(s.startswith("rf_secdef_write") or ".rf_secdef_write" in s
               for s in rep["secdef_revoked"]), rep["secdef_revoked"]
    assert set(rep["schemas"]) == {"public", "rf_s"}, rep["schemas"]
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
    # template1 exists and is a template, but PUBLIC may CONNECT to it and
    # (on a superuser-initialised cluster) it is owned by the bootstrap user.
    got = run(ro_role.read_cluster(ADMIN_DSN, template="template1"))
    assert "the template template1 has public_connect=True, provisioned as False" in got, got


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
def test_prior_finding_program_writes_under_admin(env, fid):
    """The program really writes: under the admin DSN it succeeds (rolled
    back), so the role's refusal is the only thing stopping it."""
    assert run(orm_attempt(env["admin_db_dsn"], GRANT_ONLY, FINDINGS[fid][2])) == "OK"


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
