"""ladder_pg_harness's refusals, each one made to happen (#342, #391).

The harness creates and drops schemas on an instance other lanes share, and
every guard it has is a refusal. A refusal nobody has triggered is a guard
nobody has seen work, so each is triggered here, in the lane database
LADDER_TEST_PG_DSN names, behind the same fail-not-skip gate as the ladder's
other live files:
    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    LADDER_TEST_PG_OPTOUT=1   waives the live cases deliberately

Every object below is created inside a schema a case created, and every
schema is dropped by the harness under its own census.
"""

import asyncio
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ladder_pg_harness as harness  # noqa: E402

DSN_VAR = "LADDER_TEST_PG_DSN"
OPTOUT_VAR = "LADDER_TEST_PG_OPTOUT"
DSN = (os.environ.get(DSN_VAR) or "").replace("postgresql+asyncpg://", "postgresql://")
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"

# Unqualified on purpose: where it lands is decided by the binding alone.
TABLE_SQL = "CREATE TABLE t (id integer PRIMARY KEY)"


def _require_live_pg():
    """Fail, not skip: a skipped live case reports exit 0 for coverage that
    did not run."""
    if DSN and harness._asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: the harness's refusals are "
                    "deliberately untested." % (DSN_VAR, OPTOUT_VAR))
    pytest.fail("%s is unset (or asyncpg is missing), so none of the harness's "
                "refusals was ever triggered. Point it at the lane database, or "
                "set %s=1 to waive deliberately." % (DSN_VAR, OPTOUT_VAR))


def _run(coro):
    return asyncio.run(coro)


def test_pg_an_unbuilt_case_reaches_nothing():
    """BIND. Before its schema exists, a case's bound path is [pg_catalog]
    alone, so an unqualified CREATE TABLE sent too early fails -- no schema
    selected to create in, SQLSTATE 3F000 -- instead of landing anywhere.
    Once the schema is created the path is [pg_catalog, <case>], and the
    same statement lands in it."""
    _require_live_pg()

    async def _go():
        schema = harness.case_schema("ladder_harness")
        conn = await harness.connect_bound(DSN, schema)
        created = False
        try:
            before = await harness.search_path(conn)
            try:
                await conn.execute(TABLE_SQL)
                early = "created"
            except harness._asyncpg.PostgresError as exc:
                early = exc.sqlstate
            await harness.create_case_schema(conn, schema)
            created = True
            after = await harness.search_path(conn)
            await conn.execute(TABLE_SQL)
            landed = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL",
                                         "%s.t" % harness.quoted(schema))
            return schema, before, early, after, landed
        finally:
            try:
                if created:
                    await harness.drop_case_schema(conn, schema, None)
            finally:
                await conn.close()

    schema, before, early, after, landed = _run(_go())
    assert before == ["pg_catalog"], before
    assert early == "3F000", early
    assert after == ["pg_catalog", schema], after
    assert landed is True


def test_pg_an_existing_schema_is_refused_not_reused():
    """CREATE. A case never builds into a schema it did not create: asked to
    create one that exists, the harness refuses, and the schema is left as
    it was."""
    _require_live_pg()

    async def _go():
        async with harness.CaseSchema(DSN, "ladder_harness") as a:
            await a.conn.execute(TABLE_SQL)
            await a.seal()
            conn = await harness.connect_bound(DSN, a.schema)
            try:
                with pytest.raises(harness.CensusRefusal) as refused:
                    await harness.create_case_schema(conn, a.schema)
            finally:
                await conn.close()
            return str(refused.value), await harness.schema_objects(a.conn, a.schema) == a.own

    message, unchanged = _run(_go())
    assert "already exists" in message, message
    assert unchanged


def test_pg_a_build_that_writes_outside_its_schema_is_refused_at_seal():
    """BIND, proved after the fact: a statement of A's build that names
    another schema (B's, here) changes an object outside A, and A's seal()
    refuses -- so a migration that qualified a name could not pass a build
    off as single-schema."""
    _require_live_pg()

    async def _go():
        async with harness.CaseSchema(DSN, "ladder_harness") as a:
            async with harness.CaseSchema(DSN, "ladder_harness") as b:
                await a.conn.execute("CREATE TABLE %s.escaped (id integer)"
                                     % harness.quoted(b.schema))
                with pytest.raises(harness.CensusRefusal) as refused:
                    await a.seal()
                # B adopts the table, so B's own drop removes it.
                await b.seal()
                return str(refused.value), b.schema

    message, b_schema = _run(_go())
    assert "changed" in message and b_schema in message and "escaped" in message, message


def test_pg_an_object_the_case_did_not_create_refuses_the_drop():
    """DROP. After the seal, a table appears in A's schema from another
    connection. The census finds an object the build did not leave there
    and refuses the drop; the schema survives. Adopting it (a second seal)
    is what lets A's own exit drop it."""
    _require_live_pg()

    async def _go():
        async with harness.CaseSchema(DSN, "ladder_harness") as a:
            await a.conn.execute(TABLE_SQL)
            await a.seal()
            other = await harness.connect_bound(DSN, a.schema)
            try:
                await other.execute("CREATE TABLE planted (id integer)")
            finally:
                await other.close()
            with pytest.raises(harness.CensusRefusal) as refused:
                await harness.drop_case_schema(a.conn, a.schema, a.own)
            survived = await a.conn.fetchval(harness.EXISTS_SQL, a.schema)
            await a.seal()
            return str(refused.value), survived

    message, survived = _run(_go())
    assert "did not leave there" in message and "planted" in message, message
    assert survived == 1, survived


def test_pg_an_outside_dependent_refuses_the_drop():
    """DROP. B's view reads A's table, so DROP SCHEMA A CASCADE would remove
    B's view. The census names the dependent and refuses; A survives. With
    B dropped first, A drops cleanly."""
    _require_live_pg()

    async def _go():
        async with harness.CaseSchema(DSN, "ladder_harness") as a:
            await a.conn.execute(TABLE_SQL)
            await a.seal()
            async with harness.CaseSchema(DSN, "ladder_harness") as b:
                await b.conn.execute("CREATE VIEW v AS SELECT id FROM %s.t"
                                     % harness.quoted(a.schema))
                await b.seal()
                with pytest.raises(harness.CensusRefusal) as refused:
                    await harness.drop_case_schema(a.conn, a.schema, a.own)
                survived = await a.conn.fetchval(harness.EXISTS_SQL, a.schema)
                dependents = await harness.outside_dependents(a.conn, a.schema)
            after_b = await harness.outside_dependents(a.conn, a.schema)
            return str(refused.value), survived, dependents, after_b, b.schema

    message, survived, dependents, after_b, b_schema = _run(_go())
    assert "depend on objects inside it" in message, message
    assert survived == 1, survived
    assert any(b_schema + ".v" in d for d, _ref in dependents), dependents
    assert after_b == [], after_b


def test_pg_a_path_reaching_another_schema_refuses_the_drop():
    """DROP. The census reads the dropping connection's own path: once a SET
    has put a second schema on it, the drop is refused. The session's own
    temporary schema is admitted -- migration 331's ON COMMIT DROP post-check
    table leaves it on the building session's path, and no other session can
    put an object in it -- and A then drops on its own exit."""
    _require_live_pg()

    async def _go():
        async with harness.CaseSchema(DSN, "ladder_harness") as a:
            await a.conn.execute(TABLE_SQL)
            await a.seal()
            async with harness.CaseSchema(DSN, "ladder_harness") as b:
                await a.conn.execute("SET search_path TO %s, %s"
                                     % (harness.quoted(a.schema), harness.quoted(b.schema)))
                with pytest.raises(harness.CensusRefusal) as refused:
                    await harness.drop_case_schema(a.conn, a.schema, a.own)
                survived = await a.conn.fetchval(harness.EXISTS_SQL, a.schema)
            await a.conn.execute("SET search_path TO %s" % harness.quoted(a.schema))
            await a.conn.execute("CREATE TEMP TABLE scratch (id integer) ON COMMIT DROP")
            with_temp = await harness.search_path(a.conn)
            own_temp = await a.conn.fetchval(harness.MY_TEMP_SQL)
            name = a.schema
        probe = await harness.connect_bound(DSN, harness.case_schema("ladder_harness"))
        try:
            gone = await probe.fetchval(harness.EXISTS_SQL, name) == 0
        finally:
            await probe.close()
        return str(refused.value), survived, with_temp, own_temp, name, gone

    message, survived, with_temp, own_temp, name, gone = _run(_go())
    assert "search path" in message, message
    assert survived == 1, survived
    assert own_temp and with_temp == [own_temp, "pg_catalog", name], (with_temp, own_temp)
    assert gone, "the case schema outlived its exit with only its own temp schema on the path"
