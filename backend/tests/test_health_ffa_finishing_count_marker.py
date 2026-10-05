"""The /health word that says this box's database still carries the columns
the ranked-FFA finishing-count rule needs (board row 28, round 2).

Clean House / Party Crasher / Hostile Takeover (ffa_shutout_3/_4/_5) are
tiered on _ffa_finishing_count, the MINIMUM of the server's account
(ffa_lobbies.member_ids frozen by ffa_lobby_start, minus ffa_lobbies
.departed_ids appended by ffa_queue_leave) and the report's own attestation
(neither left_early nor absent, the same flags submit_ffa_match persists to
ffa_match_players.left_early / .absent). Migration 363 revokes four awards
that fail this count but adds no column of its own: the rule is new CODE over
an unchanged schema, so the release train -- which proves a route-less batch
landed by reading a /health key BY VALUE -- has nothing to read without this
word. `ffa_finishing_count` is it: 1 when a probe naming every one of the
four columns runs on the answering box's database, 0 when it fails because a
column or a table is missing. It is absent on any build before this round,
which is how the train reads the old build.

Modelled on test_health_team_dc_fallback_marker.py, scoped to what this round
asks:

  * the probe's two column lists are DERIVED from ffa_lobby_start's,
    ffa_queue_leave's and submit_ffa_match's compiled SQL, never written down;
  * against live PostgreSQL (FFA_TROPHIES_TEST_PG_DSN), in one scratch
    database this file creates and drops, with a schema per case: all four
    columns present reads 1; one renamed away (built absent from the start,
    which is the same database-level fact a live ALTER ... RENAME COLUMN
    would leave behind, without racing this route's OTHER probes -- see
    below) reads 0 on the connected arm AND on a degraded arm reading the
    cache the connected probe just wrote; no ffa_lobbies table at all reads 0
    too; every case answers status "ok" when connected;
  * the key is present in both arms' payloads in every case;
  * a negative control: swap the probe for the shape #306 warns against (a
    hardcoded constant, ignoring the database entirely) and the missing-
    column case's own decisive assertion goes red under it.

WHY NOT A LIVE ALTER ... RENAME COLUMN inside health_check's own transaction:
health_check runs THREE database probes in one request (team_dc_fallback's,
this one, and pc_trading's own savepoint). team_dc_fallback's probe reacts to
a database that lacks its OWN table (team_series, absent from this file's
scratch database) by rolling back the WHOLE transaction it shares with
whatever ran earlier in the same request -- correct for its own design, and
exactly why a live rename sitting uncommitted earlier in that same
transaction would already be gone by the time THIS probe ran, before either
probe told a database fact. Building the missing-column schema BEFORE any
request opens a transaction at all sidesteps that ordering entirely: the
database fact is committed, not in flight, so it is unaffected by what any
sibling probe does to its own transaction.

WHY A SAVEPOINT (`db.begin_nested`) rather than team_dc_fallback's bare
execute + explicit rollback: this route already runs three per-request
database probes by the time this round adds a fourth-in-spirit one, and two
of the FIVE health-marker test files sharing this suite construct a minimal
fake session for their OWN marker that implements execute()/rollback() but
not begin_nested() (team_dc_fallback's own test foremost -- its
`db.sent == [...]` assertions are exact-list). A bare execute would run
happily against such a fake, silently appending this marker's own SQL to
that list and reddening an unrelated, already-certified test. Reusing
pc_trading's own savepoint isolation (`_pc_trade_schema`'s docstring: "under
asyncpg a caught statement error otherwise aborts the caller's transaction")
makes a session with no begin_nested at all a capability gap this marker
recognises and leaves alone -- never a database fact -- rather than a
statement it happens to still get away with sending. test_health_team_dc_
fallback_marker.py was re-run whole after this round's edit and still passes.
"""
import asyncio
import ast
import os
import pathlib
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import asyncpg                                                     # noqa: E402
from sqlalchemy import text                                        # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

import main                                                         # noqa: E402
import schemas                                                      # noqa: E402

MAIN_PY = pathlib.Path(main.__file__).resolve()

# Same lane, same convention as test_ffa_shutout_finishing_count.py (#438):
# an unset DSN FAILS the live checks rather than silently skipping them.
# FFA_TROPHIES_TEST_PG_OPTOUT=1 is the explicit, printed way to say a run
# skips them on purpose.
DSN_VAR = "FFA_TROPHIES_TEST_PG_DSN"
OPTOUT_VAR = "FFA_TROPHIES_TEST_PG_OPTOUT"
DSN = os.environ.get(DSN_VAR)


def _optout(raw) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


OPTOUT = _optout(os.environ.get(OPTOUT_VAR))


def require_pg():
    if DSN:
        return DSN
    if OPTOUT:
        pytest.skip("%s is set -- live-PostgreSQL checks for the ffa_finishing_count "
                    "marker deliberately not run in this invocation" % OPTOUT_VAR)
    pytest.fail(
        "%s is not set, so the ffa_finishing_count marker's live probe was never "
        "executed against real PostgreSQL. Set %s=postgresql+asyncpg://... to run it, "
        "or %s=1 to say out loud that this run skips it." % (DSN_VAR, DSN_VAR, OPTOUT_VAR))


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _cache_restored(monkeypatch):
    """Every test here may run the probe, which writes main's cache; the
    value the suite had before comes back afterwards (team_dc_fallback's own
    test file does the same for its own cache)."""
    monkeypatch.setattr(main, "_FFA_FINISHING_COUNT_LAST", main._FFA_FINISHING_COUNT_LAST)
    yield


class _Down:
    """A session whose first statement fails, as an unreachable database's
    does -- the degraded arm never reaches this marker's probe at all."""

    async def execute(self, *a, **k):
        raise OSError("database unreachable")

    async def rollback(self):
        raise AssertionError("nothing may roll back a session that never answered")


# -- the derivation, and the schema field ------------------------------------

def test_the_derivation_is_a_call_over_the_three_named_functions_not_a_literal():
    """A written-down tuple would still read the same four names on a box
    whose code had moved to other columns: the binding has to be a CALL of
    the deriving helper, over exactly the three functions, with no literal
    column name anywhere in it."""
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    hits = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_FFA_FINISHING_COUNT_COLUMNS"
                    for t in n.targets)]
    assert len(hits) == 1, len(hits)
    call = hits[0].value
    assert isinstance(call, ast.Call), ast.dump(call)
    assert ast.unparse(call.func) == "_ffa_finishing_count_columns", ast.unparse(call)
    assert [ast.unparse(a) for a in call.args] == [
        "ffa_lobby_start", "ffa_queue_leave", "submit_ffa_match"], ast.unparse(call)
    assert not call.keywords and not [n for n in ast.walk(call) if isinstance(n, ast.Constant)]
    assert main._FFA_FINISHING_COUNT_COLUMNS == ("absent", "departed_ids", "left_early", "member_ids"), \
        main._FFA_FINISHING_COUNT_COLUMNS
    assert main._FFA_FINISHING_COUNT_LOBBY_COLUMNS == ("departed_ids", "member_ids")
    assert main._FFA_FINISHING_COUNT_PLAYER_COLUMNS == ("absent", "left_early")
    assert main._FFA_FINISHING_COUNT_PROBES == (
        "SELECT departed_ids, member_ids FROM ffa_lobbies LIMIT 0",
        "SELECT absent, left_early FROM ffa_match_players LIMIT 0"), main._FFA_FINISHING_COUNT_PROBES


def test_the_derivation_reads_statements_and_nothing_else():
    """The helper over a function whose answer is known: a statement (even
    nested) counts; the docstring (which opens with a verb), a lower-case
    string, a bare key and a comment do not."""
    decoy_src = '''
def decoy(db):
    """SELECT member_ids FROM ffa_lobbies"""
    key = "left_early"
    note = "update ffa_match_players set absent = null"
    sql = "UPDATE ffa_lobbies SET departed_ids = departed_ids"   # member_ids comment
    def inner():
        return "  SELECT absent FROM ffa_match_players"
    return {"member_ids_response": True}, key, note, sql, inner
'''
    namespace = {}
    exec(compile(decoy_src, "<ffa_finishing_count decoy>", "exec"), namespace)
    got = main._ffa_finishing_count_columns(namespace["decoy"])
    assert got == ("absent", "departed_ids"), got


def test_the_schema_declares_the_word_required_right_after_team_dc_fallback():
    fields = list(schemas.HealthResponse.model_fields)
    field = schemas.HealthResponse.model_fields["ffa_finishing_count"]
    assert field.annotation is int and field.is_required()
    assert fields.index("ffa_finishing_count") == fields.index("team_dc_fallback") + 1, fields
    answer = run(main.health_check(db=_Down())).model_dump()
    assert "ffa_finishing_count" in answer


def test_both_arms_carry_the_key_and_only_the_probe_writes_the_cache():
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    health = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    assert len(health) == 1
    health = health[0]
    everywhere = [k for k in ast.walk(health) if isinstance(k, ast.keyword)
                  and k.arg == "ffa_finishing_count"]
    assert len(everywhere) == 2, len(everywhere)
    calls = [c for c in ast.walk(health) if isinstance(c, ast.Call)
             and isinstance(c.func, ast.Name) and c.func.id == "_ffa_finishing_count_probe"]
    assert len(calls) == 1, len(calls)


# -- the coexistence design: a session with no begin_nested at all -----------

def test_a_session_without_begin_nested_cannot_run_the_probe_and_leaves_the_cache(monkeypatch):
    """The exact shape of the sibling health-marker tests' own minimal fake
    sessions (team_dc_fallback's foremost): execute()/rollback(), no
    begin_nested(). Calling health_check on one must not send this marker's
    SQL at all -- the whole reason those already-certified tests' exact
    `db.sent == [...]` assertions still hold with this marker wired in."""
    class _NoSavepoint:
        def __init__(self):
            self.sent = []

        async def execute(self, stmt, *a, **k):
            self.sent.append(str(stmt))
            return None

        async def rollback(self):
            pass

    monkeypatch.setattr(main, "_FFA_FINISHING_COUNT_LAST", 1)
    db = _NoSavepoint()
    answer = run(main.health_check(db=db)).model_dump()
    assert answer["ffa_finishing_count"] == 1, answer   # the cache, untouched
    assert not any("ffa_lobbies" in s or "ffa_match_players" in s for s in db.sent), db.sent

    monkeypatch.setattr(main, "_FFA_FINISHING_COUNT_LAST", 0)
    db2 = _NoSavepoint()
    answer2 = run(main.health_check(db=db2)).model_dump()
    assert answer2["ffa_finishing_count"] == 0, answer2
    assert not any("ffa_lobbies" in s or "ffa_match_players" in s for s in db2.sent), db2.sent


# -- live PostgreSQL: one scratch database, a schema per case ------------------

LANE_MARKER_PREFIX = "ffa_trophies_r2_marker_"


def _raw_dsn(dsn):
    for prefix in ("postgresql+asyncpg://", "postgresql://"):
        if dsn.startswith(prefix):
            return "postgresql://" + dsn[len(prefix):]
    raise RuntimeError("%s is not a postgresql URL" % DSN_VAR)


def _with_database(raw_dsn: str, name: str) -> str:
    root, _, _ = raw_dsn.rpartition("/")
    assert root, raw_dsn
    return root + "/" + name


def _lobby_ddl(has_member_ids: bool, has_departed_ids: bool) -> str:
    cols = ["id UUID PRIMARY KEY"]
    if has_member_ids:
        cols.append("member_ids UUID[] NOT NULL DEFAULT '{}'")
    if has_departed_ids:
        cols.append("departed_ids UUID[] NOT NULL DEFAULT '{}'")
    return "CREATE TABLE ffa_lobbies (%s)" % ", ".join(cols)


def _player_ddl(has_left_early: bool, has_absent: bool) -> str:
    cols = ["match_id UUID NOT NULL", "player_id UUID NOT NULL"]
    if has_left_early:
        cols.append("left_early BOOLEAN NOT NULL DEFAULT false")
    if has_absent:
        cols.append("absent BOOLEAN NOT NULL DEFAULT false")
    cols.append("PRIMARY KEY (match_id, player_id)")
    return "CREATE TABLE ffa_match_players (%s)" % ", ".join(cols)


# case: (ffa_lobbies DDL or None, ffa_match_players DDL, marker wanted, the
#        SQLSTATE the probe itself raises there)
CASES = {
    "both_present": (_lobby_ddl(True, True), _player_ddl(True, True), 1, None),
    "lobby_missing_departed_ids": (_lobby_ddl(True, False), _player_ddl(True, True), 0, "42703"),
    "player_missing_left_early": (_lobby_ddl(True, True), _player_ddl(False, True), 0, "42703"),
    "no_lobby_table": (None, _player_ddl(True, True), 0, "42P01"),
}
NEGATIVE_CONTROL_CASE = "lobby_missing_departed_ids"


async def _create_scratch_db(raw: str) -> str:
    import uuid
    name = LANE_MARKER_PREFIX + uuid.uuid4().hex[:16]
    conn = await asyncpg.connect(raw)
    try:
        taken = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        assert taken is None, name
        await conn.execute('CREATE DATABASE "%s"' % name)
    finally:
        await conn.close()
    return name


async def _prepare_schemas(raw: str, dbname: str) -> None:
    conn = await asyncpg.connect(_with_database(raw, dbname))
    try:
        for case, (lobby_ddl, player_ddl, _want, _state) in CASES.items():
            schema = "case_" + case
            await conn.execute('CREATE SCHEMA "%s"' % schema)
            await conn.execute('SET search_path TO "%s"' % schema)
            if lobby_ddl:
                await conn.execute(lobby_ddl)
            await conn.execute(player_ddl)
        await conn.execute("SET search_path TO public")
    finally:
        await conn.close()


async def _drop_scratch_db(raw: str, name: str) -> bool:
    assert name.startswith(LANE_MARKER_PREFIX), name
    conn = await asyncpg.connect(raw)
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()", name)
        await conn.execute('DROP DATABASE IF EXISTS "%s"' % name)
        still_there = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
    finally:
        await conn.close()
    return still_there is None


@pytest.fixture(scope="module")
def lane_db():
    """(sa_base, raw, name): sa_base keeps the +asyncpg driver prefix, for
    create_async_engine; raw is the asyncpg-native form (no driver prefix),
    for asyncpg.connect(). Both name the SAME scratch database once its
    trailing path segment is swapped -- SQLAlchemy defaults to the SYNC
    psycopg2 dialect on a bare postgresql:// URL, which is not installed
    here, so the engine must never be built from the stripped form."""
    sa_base = require_pg()
    raw = _raw_dsn(sa_base)
    name = run(_create_scratch_db(raw))
    run(_prepare_schemas(raw, name))
    try:
        yield sa_base, raw, name
    finally:
        dropped = run(_drop_scratch_db(raw, name))
        print("\nlane database %s dropped: %s" % (name, dropped))
        assert dropped, "scratch database %r survived DROP DATABASE" % name


async def _answer_for(db_dsn: str, schema: str) -> tuple[dict, int, dict]:
    engine = create_async_engine(db_dsn, connect_args={"server_settings": {"search_path": schema}})
    try:
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as session:
            answer = (await main.health_check(db=session)).model_dump()
            after = (await session.execute(text("SELECT 1"))).scalar()
    finally:
        await engine.dispose()
    degraded = (await main.health_check(db=_Down())).model_dump()
    return answer, after, degraded


@pytest.mark.parametrize("case", list(CASES))
def test_pg_the_connected_arm_matches_the_schema_and_the_cache_carries_to_the_degraded_arm(lane_db, case):
    """Steps 1-3 of the brief, per case: the connected arm reads exactly what
    this case's schema supports; the SAME session answers its next statement
    (the probe's savepoint did not abort anything); a degraded arm run right
    after reads back the cache the connected probe just wrote; the key is
    present in both arms' payloads; status stays ok/connected when
    connected, whatever this marker itself answered."""
    sa_base, _raw, dbname = lane_db
    _, _, want, want_state = CASES[case]
    schema = "case_" + case
    db_dsn = _with_database(sa_base, dbname)

    answer, after, degraded = run(_answer_for(db_dsn, schema))

    assert (answer["status"], answer["database"]) == ("ok", "connected"), (case, answer)
    assert answer["ffa_finishing_count"] == want, (case, answer)
    assert after == 1, (case, "the session did not answer its next statement")
    assert "ffa_finishing_count" in answer

    assert (degraded["status"], degraded["database"]) == ("degraded", "disconnected"), (case, degraded)
    assert degraded["ffa_finishing_count"] == want, (case, degraded)
    assert "ffa_finishing_count" in degraded

    print("case %-27s want %d probe-sqlstate %-6s connected %d degraded(cached) %d"
          % (case, want, want_state or "none", answer["ffa_finishing_count"], degraded["ffa_finishing_count"]))


def test_pg_negative_control_a_constant_probe_would_not_have_caught_the_missing_column(lane_db, monkeypatch):
    """If ffa_finishing_count's probe regressed into a hardcoded constant --
    the shape #306 warns against and the shape _TICKET_REDACTION_MARKER uses
    for a fact that needs no live check -- the case above named
    NEGATIVE_CONTROL_CASE would not have caught a database missing a column
    the rule needs. Proven by swapping in exactly that shape and showing the
    decisive assertion from that case, `answer["ffa_finishing_count"] == 0`,
    goes RED under it: the mutant answers 1 instead, ignoring the database
    entirely."""
    sa_base, _raw, dbname = lane_db
    schema = "case_" + NEGATIVE_CONTROL_CASE
    db_dsn = _with_database(sa_base, dbname)
    _, _, want, _ = CASES[NEGATIVE_CONTROL_CASE]
    assert want == 0, "the negative control needs a case this marker normally reads 0 for"

    async def _constant_probe(db):
        main._FFA_FINISHING_COUNT_LAST = 1
        return 1

    monkeypatch.setattr(main, "_ffa_finishing_count_probe", _constant_probe)

    async def body():
        engine = create_async_engine(db_dsn, connect_args={"server_settings": {"search_path": schema}})
        try:
            Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with Session() as session:
                return (await main.health_check(db=session)).model_dump()
        finally:
            await engine.dispose()

    answer = run(body())
    assert answer["ffa_finishing_count"] == 1, answer   # the mutant's wrong answer, unconditionally

    red_line = 'assert answer["ffa_finishing_count"] == %d, (case, answer)' % want
    with pytest.raises(AssertionError):
        assert answer["ffa_finishing_count"] == want, (NEGATIVE_CONTROL_CASE, answer)
    print("RED under the constant-probe mutant (case %s): %s -- got ffa_finishing_count=%d instead of %d"
          % (NEGATIVE_CONTROL_CASE, red_line, answer["ffa_finishing_count"], want))
