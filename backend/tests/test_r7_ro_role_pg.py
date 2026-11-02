"""The read-only role as the effect bound of B2 binding soundness and S SQL
positions (ruling REHEARSAL-FOUR-R6 (1)(a), (2), (3)).

Runs under CF_TEST_PG_DSN naming an ADMIN (superuser) DSN. The module
creates its own scratch database and role (ro_role.provision), runs every
control there, and drops both. It never skips: an unset DSN, or a refused
CREATE DATABASE / CREATE ROLE, fails the module.

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

The DSN census (brief item 4) counts, by AST over a frozen file list, every
site where the covered files read a DSN from the environment or open a
connection from one.
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


@pytest.fixture(scope="module")
def env():
    if not ADMIN_DSN:
        pytest.fail("CF_TEST_PG_DSN is unset: name an admin (superuser) DSN on the "
                    "local cluster; this module never skips")
    name = "rf7_ro_" + _stamp()
    out = {"db": name, "role": name}

    async def setup():
        admin = await asyncpg.connect(ADMIN_DSN)
        try:
            await admin.execute('CREATE DATABASE "%s"' % name)
        finally:
            await admin.close()
        conn = await asyncpg.connect(ro_role.dsn_for(ADMIN_DSN, name))
        try:
            for s in FIXTURE_SQL:
                await conn.execute(s)
            await conn.execute('GRANT CREATE ON DATABASE "%s" TO PUBLIC' % name)
        finally:
            await conn.close()
        out["report"] = await ro_role.provision(ADMIN_DSN, name, name)
        out["admin_db_dsn"] = ro_role.dsn_for(ADMIN_DSN, name)
        out["ro_dsn"] = out["report"]["dsn"]

    try:
        run(setup())
        yield out
    finally:
        run(ro_role.drop(ADMIN_DSN, name, name))


# ---------------------------------------------------------------- runners

def _sqlstate(exc):
    for e in (exc, getattr(exc, "orig", None), getattr(getattr(exc, "orig", None),
                                                        "__cause__", None)):
        s = getattr(e, "sqlstate", None)
        if isinstance(s, str) and len(s) == 5:
            return s
    raise AssertionError("no SQLSTATE on %r" % (exc,))


async def raw_attempt(dsn, layer, body):
    """`body(conn)` on a fresh asyncpg connection, in a transaction that is
    always rolled back; 'OK' or the SQLSTATE PostgreSQL returned."""
    conn = await asyncpg.connect(dsn)
    try:
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


async def orm_attempt(dsn, layer, prog):
    """`prog(db)` on a SQLAlchemy AsyncSession over asyncpg (the repo's
    driver), always rolled back; 'OK' or the SQLSTATE."""
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


async def _attempt(dsn, layer, cls):
    kind, body = CLASSES[cls]
    return await (raw_attempt if kind == RAW else orm_attempt)(dsn, layer, body)


def test_expected_table_is_whole_and_never_ok():
    assert set(EXPECTED) == {(c, l) for c in CLASSES for l in LAYERS}
    assert all(v != "OK" for v in EXPECTED.values())


@pytest.mark.parametrize("layer", LAYERS)
@pytest.mark.parametrize("cls", list(CLASSES))
def test_write_class_refused_under_role(env, cls, layer):
    got = run(_attempt(env["ro_dsn"], layer, cls))
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
    assert run(raw_attempt(env["ro_dsn"], layer, body)) == "OK"


def test_privilege_census_is_empty(env):
    rep = env["report"]
    assert rep["lo_unclassified"] == [], rep["lo_unclassified"]
    revoked = {s.split("(", 1)[0] for s in rep["lo_revoked"]}
    assert revoked == set(ro_role.LO_WRITERS), sorted(revoked)
    assert any(s.startswith("rf_secdef_write") or ".rf_secdef_write" in s
               for s in rep["secdef_revoked"]), rep["secdef_revoked"]
    assert set(rep["schemas"]) == {"public", "rf_s"}, rep["schemas"]
    found = run(ro_role.privilege_census(ADMIN_DSN, env["db"], env["role"]))
    assert found == [], found


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
    got = run(orm_attempt(env["ro_dsn"], layer, prog))
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

# A site: (a) an environment read -- os.environ.get / os.getenv / environ.get
# call or os.environ[...] subscript -- whose key is a string constant
# containing DSN or DATABASE_URL, or a Name ending in DSN_VAR; (b) a call
# whose callee's dotted name ends in one of OPENERS, or equals one of
# OPENER_DOTTED. Nothing else is resolved (rule (1)(c)).
OPENERS = ("create_async_engine", "create_engine", "bound_engine", "connect_bound",
           "CaseSchema", "fresh_database", "create_pool", "make_asm_engine")
OPENER_DOTTED = ("asyncpg.connect", "_asyncpg.connect", "cf_pg.case",
                 "cf_pool.checkout")
ENV_CALLS = ("os.environ.get", "os.getenv", "environ.get")


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _env_key(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value if ("DSN" in node.value or "DATABASE_URL" in node.value) else None
    if isinstance(node, ast.Name) and node.id.endswith("DSN_VAR"):
        return node.id
    return None


def census_sites(path, source):
    sites = []
    for node in ast.walk(ast.parse(source, filename=path)):
        if isinstance(node, ast.Call):
            d = _dotted(node.func)
            if d in ENV_CALLS and node.args and _env_key(node.args[0]):
                sites.append((node.lineno, "env", _env_key(node.args[0])))
            elif d is not None and (d.split(".")[-1] in OPENERS or d in OPENER_DOTTED):
                arg = node.args[0] if node.args else None
                for kw in node.keywords:
                    if kw.arg == "dsn":
                        arg = kw.value
                sites.append((node.lineno, "open:" + d,
                              ast.unparse(arg) if arg is not None else ""))
        elif isinstance(node, ast.Subscript) and _dotted(node.value) == "os.environ":
            if _env_key(node.slice):
                sites.append((node.lineno, "env", _env_key(node.slice)))
    return sorted(sites)


def census(root=BACKEND):
    out = {}
    for rel in CENSUS_FILES:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            out[rel] = census_sites(rel, fh.read())
    return out


# Frozen: per file, the (kind, DSN expression) of every site. A file with
# no site is absent.
CENSUS_FROZEN = {'api/database.py': [('env', 'DATABASE_URL'),
                     ('open:create_async_engine', 'DATABASE_URL'),
                     ('open:create_async_engine', 'DATABASE_URL'),
                     ('open:create_async_engine', 'url'),
                     ('open:make_asm_engine', '')],
 'tests/cf_pg.py': [('env', 'DSN_VAR'),
                    ('open:_asyncpg.connect', 'DSN'),
                    ('open:_asyncpg.connect', 'DSN'),
                    ('open:cf_pool.checkout', ''),
                    ('open:harness.CaseSchema', 'dsn or DSN'),
                    ('open:harness.bound_engine', 'dsn or DSN'),
                    ('open:harness.bound_engine', 'dsn or DSN')],
 'tests/cf_pool.py': [('open:asyncpg.connect', 'cf_pg.DSN'),
                      ('open:asyncpg.connect', 'dsn'),
                      ('open:asyncpg.connect', 'dsn'),
                      ('open:asyncpg.connect', 'dsn'),
                      ('open:harness.bound_engine', 'dsn'),
                      ('open:harness.connect_bound', 'dsn'),
                      ('open:harness.connect_bound', 'dsn'),
                      ('open:harness.connect_bound', 'dsn'),
                      ('open:harness.connect_bound', 'dsn'),
                      ('open:harness.connect_bound', 'self.dsn')],
 'tests/ladder_pg_harness.py': [('open:_asyncpg.connect',
                                 "dsn.replace('postgresql+asyncpg://', 'postgresql://')"),
                                ('open:connect_bound', 'self.dsn'),
                                ('open:create_async_engine', 'async_dsn(dsn)')],
 'tests/test_a1_formation_concurrency.py': [('env', 'A1_TEST_PG_DSN'),
                                            ('open:create_async_engine', 'DSN')],
 'tests/test_a1_predicate_sql.py': [('env', 'A1_TEST_PG_DSN'),
                                    ('open:create_async_engine', 'DSN')],
 'tests/test_match_hold_admission_gate_pg.py': [('open:cf_pg.case', "'h3gate'")],
 'tests/test_match_hold_pg.py': [('open:cf_pg.case', 'prefix'),
                                 ('open:cf_pg.harness.connect_bound', 'env.c.dsn'),
                                 ('open:cf_pg.harness.connect_bound', 'env.c.dsn'),
                                 ('open:cf_pg.harness.connect_bound', 'env.c.dsn')],
 'tests/test_title_ladder_hooks_live.py': [('env', 'DSN_VAR'),
                                           ('open:harness.CaseSchema', 'DSN'),
                                           ('open:harness.bound_engine', 'DSN'),
                                           ('open:harness.bound_engine', 'DSN'),
                                           ('open:harness.bound_engine', 'DSN'),
                                           ('open:harness.bound_engine', 'DSN'),
                                           ('open:harness.bound_engine', 'DSN'),
                                           ('open:harness.connect_bound', 'DSN'),
                                           ('open:harness.connect_bound', 'DSN'),
                                           ('open:harness.connect_bound', 'DSN'),
                                           ('open:harness.connect_bound', 'DSN'),
                                           ('open:harness.connect_bound', 'DSN')],
 'tests/test_title_ladders.py': [('env', 'DSN_VAR'),
                                 ('env', 'LADDER_DSN_VAR'),
                                 ('open:_asyncpg.connect', 'LADDER_DSN'),
                                 ('open:_asyncpg.connect', 'LADDER_DSN'),
                                 ('open:_asyncpg.connect', 'LADDER_DSN'),
                                 ('open:_asyncpg.connect', 'LADDER_DSN'),
                                 ('open:_asyncpg.connect', 'LADDER_DSN'),
                                 ('open:_asyncpg.connect', 'LADDER_DSN'),
                                 ('open:asyncpg.connect',
                                  "DSN.replace('postgresql+asyncpg://', 'postgresql://')"),
                                 ('open:create_async_engine',
                                  "LADDER_DSN.replace('postgresql://', "
                                  "'postgresql+asyncpg://')")]}
CENSUS_COUNT = 56


def _frozen_view(c):
    return {f: sorted((k, e) for _, k, e in s) for f, s in c.items() if s}


def test_dsn_census_is_closed():
    root = os.environ.get("RF7RO_CENSUS_ROOT") or BACKEND
    got = census(root)
    view = _frozen_view(got)
    total = sum(len(s) for s in got.values())
    assert total == CENSUS_COUNT, (total, view)
    assert view == CENSUS_FROZEN, view


def test_dsn_census_negative_control():
    """A site added to a covered file changes the count."""
    rel = "tests/cf_pg.py"
    with open(os.path.join(BACKEND, rel), encoding="utf-8") as fh:
        src = fh.read()
    planted = src + "\n\nasync def _planted():\n    return await _asyncpg.connect(DSN)\n"
    assert len(census_sites(rel, planted)) == len(census_sites(rel, src)) + 1
    planted_env = src + "\n\nX = os.environ.get('OTHER_PG_DSN')\n"
    assert len(census_sites(rel, planted_env)) == len(census_sites(rel, src)) + 1
