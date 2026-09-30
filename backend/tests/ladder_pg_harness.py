"""One throwaway schema per case: bound, and censused before anything is
created or dropped.

Used by the ladder's live-PostgreSQL tests. Each case builds a schema of its
own in the database LADDER_TEST_PG_DSN names -- on an instance other lanes'
sessions share -- runs DDL into it, and drops it afterwards. Two of those
steps do damage if they reach the wrong place: DDL landing outside the case
schema, and a DROP ... CASCADE reaching past it. This module is the ticket-
redaction lane's discipline ("one schema, and a census before anything
destructive") adapted to a schema per case:

  BIND     every connection a case opens is bound at connect to the case
           schema alone (search_path in the startup packet). Before the
           schema is created, current_schemas(true) must be exactly
           [pg_catalog]: the path reaches nothing a statement could land in
           or resolve against, so an unqualified statement sent too early
           fails instead of landing elsewhere. Right after, the path must be
           exactly [pg_catalog, <case>] and the case schema must hold no
           object. DDL a case composes names the schema (a widening ALTER, a
           relaxed NOT NULL). DDL it executes as text -- the migration files,
           and test_title_ladders.LADDER_PREREQ, which that suite shares --
           runs as written, unqualified, and the binding is what makes it
           single-schema; the build is then PROVED single-schema: seal()
           requires every object outside the case schema, in every schema a
           client can create, to be exactly what it was before the build.
  CREATE   the name is fresh (a uuid suffix) and a schema that already
           exists is refused, never reused.
  DROP     the census runs first, on a bound connection: the path must still
           be [pg_catalog, <case>] -- preceded, at most, by this session's
           OWN temporary schema (pg_my_temp_schema()), which migration 331's
           ON COMMIT DROP post-check table leaves on the building session's
           path and which only that session can put objects in; every
           object in the case schema must be
           one the build left there (the set seal() recorded), so an object
           the case did not create refuses the drop; and no object OUTSIDE
           the schema may depend on one inside it (pg_depend normal
           dependencies, each dependent homed through its own catalog,
           because pg_identify_object reports no schema for a column default
           or a view's rule; a dependent it cannot home counts as outside).
           Only then DROP SCHEMA ... CASCADE, which can then remove only what
           the case created. A refusal leaves the schema in place.
  NEVER    no pg_terminate_backend, no DROP of anything but the case's own
           schema, nothing created in or dropped from public.
"""

import uuid

try:
    import asyncpg as _asyncpg
except ImportError:                                    # pragma: no cover
    _asyncpg = None

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

CENSUS_TAG = "/* ladder harness census */"

PATH_SQL = "SELECT pg_catalog.current_schemas(true)::text[] " + CENSUS_TAG
EXISTS_SQL = ("SELECT count(*) FROM pg_catalog.pg_namespace WHERE nspname = $1 "
              + CENSUS_TAG)
# This session's own temporary schema, if it has one (NULL otherwise).
MY_TEMP_SQL = ("SELECT n.nspname::text FROM pg_catalog.pg_namespace n "
               "WHERE n.oid = pg_catalog.pg_my_temp_schema() " + CENSUS_TAG)

# The objects a statement could land in or resolve against by name, per
# schema: relations of every kind, routines, types (a table's row and array
# types included), operators and collations.
_OBJECTS = """
SELECT n.nspname::text AS schema, 'relation ' || c.relkind::text AS kind,
       c.relname::text AS name
  FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
 WHERE {where}
UNION ALL
SELECT n.nspname::text, 'routine',
       p.proname::text || '(' || pg_catalog.pg_get_function_identity_arguments(p.oid) || ')'
  FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
 WHERE {where}
UNION ALL
SELECT n.nspname::text, 'type', t.typname::text
  FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
 WHERE {where}
UNION ALL
SELECT n.nspname::text, 'operator',
       o.oprname::text || '(' || o.oprleft::pg_catalog.regtype::text || ','
       || o.oprright::pg_catalog.regtype::text || ')'
  FROM pg_catalog.pg_operator o JOIN pg_catalog.pg_namespace n ON n.oid = o.oprnamespace
 WHERE {where}
UNION ALL
SELECT n.nspname::text, 'collation', co.collname::text
  FROM pg_catalog.pg_collation co JOIN pg_catalog.pg_namespace n ON n.oid = co.collnamespace
 WHERE {where}
UNION ALL
SELECT n.nspname::text, 'schema', n.nspname::text
  FROM pg_catalog.pg_namespace n
 WHERE {where}
"""
SCHEMA_OBJECTS_SQL = (_OBJECTS.format(where="n.nspname = $1")
                      + " ORDER BY 1, 2, 3 " + CENSUS_TAG)
# Every schema a client can create: not the reserved pg_ prefix (which also
# excludes other sessions' temporary schemas) and not information_schema.
OUTSIDE_OBJECTS_SQL = (_OBJECTS.format(
    where="n.nspname <> $1 AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'")
    + " ORDER BY 1, 2, 3 " + CENSUS_TAG)

# Every object outside schema $1 that holds a NORMAL dependency on an object
# inside it: what DROP ... RESTRICT would refuse over and CASCADE would
# remove. Automatic and internal dependencies (a table's indexes, its TOAST
# table, a column-owned sequence) belong to the object they depend on and go
# with it under either form, so they are not the question.
DEPENDENTS_SQL = """
WITH own AS (
    SELECT 'pg_catalog.pg_class'::pg_catalog.regclass AS cls, c.oid
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = $1
    UNION ALL
    SELECT 'pg_catalog.pg_type'::pg_catalog.regclass, t.oid
      FROM pg_catalog.pg_type t
      JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
     WHERE n.nspname = $1
    UNION ALL
    SELECT 'pg_catalog.pg_proc'::pg_catalog.regclass, p.oid
      FROM pg_catalog.pg_proc p
      JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = $1
    UNION ALL
    SELECT 'pg_catalog.pg_namespace'::pg_catalog.regclass, n.oid
      FROM pg_catalog.pg_namespace n
     WHERE n.nspname = $1
), hits AS (
    SELECT d.classid, d.objid, d.objsubid, d.refclassid, d.refobjid, d.refobjsubid
      FROM pg_catalog.pg_depend d
      JOIN own ON own.cls = d.refclassid AND own.oid = d.refobjid
     WHERE d.deptype = 'n'
), homed AS (
    SELECT h.classid, h.objid, h.objsubid, h.refclassid, h.refobjid, h.refobjsubid,
           CASE h.classid
             WHEN 'pg_catalog.pg_class'::pg_catalog.regclass THEN
               (SELECT c.relnamespace FROM pg_catalog.pg_class c WHERE c.oid = h.objid)
             WHEN 'pg_catalog.pg_attrdef'::pg_catalog.regclass THEN
               (SELECT c.relnamespace FROM pg_catalog.pg_attrdef a
                  JOIN pg_catalog.pg_class c ON c.oid = a.adrelid WHERE a.oid = h.objid)
             WHEN 'pg_catalog.pg_rewrite'::pg_catalog.regclass THEN
               (SELECT c.relnamespace FROM pg_catalog.pg_rewrite r
                  JOIN pg_catalog.pg_class c ON c.oid = r.ev_class WHERE r.oid = h.objid)
             WHEN 'pg_catalog.pg_trigger'::pg_catalog.regclass THEN
               (SELECT c.relnamespace FROM pg_catalog.pg_trigger t
                  JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid WHERE t.oid = h.objid)
             WHEN 'pg_catalog.pg_constraint'::pg_catalog.regclass THEN
               (SELECT x.connamespace FROM pg_catalog.pg_constraint x WHERE x.oid = h.objid)
             WHEN 'pg_catalog.pg_type'::pg_catalog.regclass THEN
               (SELECT t.typnamespace FROM pg_catalog.pg_type t WHERE t.oid = h.objid)
             WHEN 'pg_catalog.pg_proc'::pg_catalog.regclass THEN
               (SELECT p.pronamespace FROM pg_catalog.pg_proc p WHERE p.oid = h.objid)
             WHEN 'pg_catalog.pg_policy'::pg_catalog.regclass THEN
               (SELECT c.relnamespace FROM pg_catalog.pg_policy p
                  JOIN pg_catalog.pg_class c ON c.oid = p.polrelid WHERE p.oid = h.objid)
           END AS home
      FROM hits h
)
SELECT (pg_catalog.pg_identify_object(classid, objid, objsubid)).identity AS dependent,
       (pg_catalog.pg_identify_object(refclassid, refobjid, refobjsubid)).identity AS referenced
  FROM homed
 WHERE home IS DISTINCT FROM (SELECT n.oid FROM pg_catalog.pg_namespace n WHERE n.nspname = $1)
 ORDER BY 1, 2
""" + CENSUS_TAG


class CensusRefusal(RuntimeError):
    """The census found something this case did not create, or would reach."""


def case_schema(prefix):
    """A fresh case-schema name: `prefix`, an underscore, ten hex digits."""
    return "%s_%s" % (prefix, uuid.uuid4().hex[:10])


def quoted(schema):
    if not (schema.replace("_", "").isalnum() and schema == schema.lower()):
        raise CensusRefusal("not a harness schema name: %r" % schema)
    return '"%s"' % schema


def async_dsn(dsn):
    return dsn.replace("postgresql://", "postgresql+asyncpg://")


async def connect_bound(dsn, schema):
    """An asyncpg connection whose search_path is `schema` alone."""
    return await _asyncpg.connect(dsn.replace("postgresql+asyncpg://", "postgresql://"),
                                  server_settings={"search_path": quoted(schema)})


def bound_engine(dsn, schema):
    """A SQLAlchemy async engine whose every connection has search_path
    `schema` alone; NullPool, so no connection outlives its use."""
    return create_async_engine(
        async_dsn(dsn), poolclass=NullPool,
        connect_args={"server_settings": {"search_path": quoted(schema)}})


async def search_path(conn):
    return list(await conn.fetchval(PATH_SQL) or [])


async def schema_objects(conn, schema):
    return {(r["kind"], r["name"]) for r in await conn.fetch(SCHEMA_OBJECTS_SQL, schema)}


async def outside_objects(conn, schema):
    return [(r["schema"], r["kind"], r["name"])
            for r in await conn.fetch(OUTSIDE_OBJECTS_SQL, schema)]


async def outside_dependents(conn, schema):
    """(dependent, referenced) for every object outside `schema` that
    depends on an object inside it."""
    return [(r["dependent"], r["referenced"])
            for r in await conn.fetch(DEPENDENTS_SQL, schema)]


async def create_case_schema(conn, schema):
    """CREATE (module docstring). `conn` must be bound to `schema`."""
    if await conn.fetchval(EXISTS_SQL, schema):
        raise CensusRefusal("schema %s already exists; a case never builds into a "
                            "schema it did not create" % schema)
    path = await search_path(conn)
    if path != ["pg_catalog"]:
        raise CensusRefusal("before CREATE SCHEMA the search path reaches %r, not "
                            "[pg_catalog] alone" % (path,))
    await conn.execute("CREATE SCHEMA %s" % quoted(schema))
    path = await search_path(conn)
    if path != ["pg_catalog", schema]:
        raise CensusRefusal("after CREATE SCHEMA the search path is %r, not "
                            "[pg_catalog, %s]" % (path, schema))
    found = await schema_objects(conn, schema) - {("schema", schema)}
    if found:
        raise CensusRefusal("the new schema %s already holds %r" % (schema, sorted(found)[:5]))


async def drop_case_schema(conn, schema, own):
    """DROP (module docstring). `own` is the set seal() recorded, or None
    when the build never finished -- then only the path and the dependents
    census gate the drop of a schema this case proved it created."""
    if conn.is_in_transaction():
        await conn.execute("ROLLBACK")
    if not await conn.fetchval(EXISTS_SQL, schema):
        return
    path = await search_path(conn)
    own_temp = await conn.fetchval(MY_TEMP_SQL)
    if path not in (["pg_catalog", schema], [own_temp, "pg_catalog", schema]):
        raise CensusRefusal("refusing DROP SCHEMA %s: the connection's search path "
                            "is %r (own temporary schema %r)" % (schema, path, own_temp))
    if own is not None:
        foreign = await schema_objects(conn, schema) - own
        if foreign:
            raise CensusRefusal("refusing DROP SCHEMA %s CASCADE: it holds %d object(s) "
                                "the build did not leave there: %r"
                                % (schema, len(foreign), sorted(foreign)[:5]))
    outside = await outside_dependents(conn, schema)
    if outside:
        raise CensusRefusal("refusing DROP SCHEMA %s CASCADE: %d object(s) outside it "
                            "depend on objects inside it: %r"
                            % (schema, len(outside), outside[:5]))
    await conn.execute("DROP SCHEMA %s CASCADE" % quoted(schema))


class CaseSchema:
    """`async with CaseSchema(dsn, prefix) as case:` -- case.conn is an
    asyncpg connection bound to case.schema, which exists, empty, on entry.
    Build into it, then `await case.seal()`; on exit the schema is dropped
    under the census (or left in place if the census refuses)."""

    def __init__(self, dsn, prefix):
        self.dsn = dsn
        self.schema = case_schema(prefix)
        self.conn = None
        self.own = None
        self._outside = None
        self._created = False

    async def __aenter__(self):
        self.conn = await connect_bound(self.dsn, self.schema)
        try:
            await create_case_schema(self.conn, self.schema)
            self._created = True
            self._outside = await outside_objects(self.conn, self.schema)
        except BaseException:
            try:
                if self._created:
                    await drop_case_schema(self.conn, self.schema, None)
            finally:
                await self.conn.close()
            raise
        return self

    async def seal(self):
        """After the build: everything outside the case schema is exactly
        what it was before the build, and the schema's objects become this
        case's own -- the set the drop's census admits."""
        after = await outside_objects(self.conn, self.schema)
        if after != self._outside:
            changed = sorted(set(after) ^ set(self._outside))
            raise CensusRefusal("the build of %s changed %d object(s) outside it: %r"
                                % (self.schema, len(changed), changed[:5]))
        self.own = await schema_objects(self.conn, self.schema)
        return self.own

    async def __aexit__(self, *exc):
        try:
            if self._created:
                await drop_case_schema(self.conn, self.schema, self.own)
        finally:
            await self.conn.close()
