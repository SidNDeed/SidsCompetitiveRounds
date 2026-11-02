"""A read-only LOGIN role for the effect bounds of B2 binding soundness and S
SQL positions (ruling REHEARSAL-FOUR-R6 (1)(a) and (2)).

The claim the walker could not prove ("this SQL is a read") is enforced at
the database instead: a test session that opens the database as this role
cannot write by any route, because PostgreSQL refuses the write. provision()
does, inside ONE database and nowhere else (apart from creating the role):

  - CREATE ROLE <role> LOGIN, with no superuser, createdb, createrole,
    replication or bypassrls attribute and no membership in any role;
  - for every non-system schema (every pg_namespace row except
    information_schema and the pg_* schemas): USAGE on the schema, SELECT on
    every relation in it (tables, views, materialized views, foreign and
    partitioned tables) and SELECT on every sequence; INSERT, UPDATE, DELETE,
    TRUNCATE, REFERENCES and TRIGGER revoked from PUBLIC on every relation,
    USAGE and UPDATE revoked from PUBLIC on every sequence (the role inherits
    PUBLIC's privileges, so a PUBLIC grant would be a write route); CREATE
    revoked on the schema from PUBLIC and from the role;
  - TEMPORARY and CREATE on the database revoked from PUBLIC and the role;
  - EXECUTE revoked from PUBLIC and the role on every overload of every
    large-object function that can write (LO_WRITERS); the large-object
    functions in pg_catalog are listed from pg_proc and each must be in
    LO_WRITERS or LO_READERS: report["lo_unclassified"] names any other, and
    the test requires it empty;
  - EXECUTE revoked from PUBLIC and the role on every SECURITY DEFINER
    routine in the database (listed from pg_proc);
  - ALTER ROLE <role> SET default_transaction_read_only = on.

provision() asserts nothing about its own result: privilege_census() reads
the catalog afterwards and the test asserts it, so a mutant that drops one
revoke is caught by the executed control the revoke guards.
"""

import re

import asyncpg

LO_WRITERS = (
    "lo_creat",
    "lo_create",
    "lo_export",
    "lo_from_bytea",
    "lo_import",
    "lo_open",
    "lo_put",
    "lo_truncate",
    "lo_truncate64",
    "lo_unlink",
    "lowrite",
)
LO_READERS = ("lo_close", "lo_get", "lo_lseek", "lo_lseek64", "lo_tell",
              "lo_tell64", "loread")

ROLE_RE = re.compile(r"^rf7_ro_[a-z0-9_]+$")
DB_RE = re.compile(r"^[a-z0-9_]+$")

SCHEMAS_SQL = ("SELECT nspname FROM pg_catalog.pg_namespace "
               "WHERE nspname <> 'information_schema' AND nspname !~ '^pg_' "
               "ORDER BY 1")
LO_FUNCS_SQL = ("SELECT p.oid::pg_catalog.regprocedure::text AS sig, p.proname "
                "FROM pg_catalog.pg_proc p "
                "WHERE p.pronamespace = 'pg_catalog'::pg_catalog.regnamespace "
                "AND (p.proname ~ '^lo_' OR p.proname IN ('loread', 'lowrite')) "
                "ORDER BY 1")
SECDEF_SQL = ("SELECT p.oid::pg_catalog.regprocedure::text AS sig "
              "FROM pg_catalog.pg_proc p WHERE p.prosecdef ORDER BY 1")


def pg_dsn(dsn):
    """asyncpg's form of a DSN (the SQLAlchemy dialect prefix removed)."""
    return dsn.replace("postgresql+asyncpg://", "postgresql://")


def dsn_for(dsn, database, user=None):
    """`dsn` pointed at `database`, and at `user` when given. No query
    string is carried (the lane's DSNs have none)."""
    head = pg_dsn(dsn).split("?", 1)[0].rsplit("/", 1)[0]
    if user is not None:
        scheme, rest = head.split("://", 1)
        head = "%s://%s@%s" % (scheme, user, rest.split("@", 1)[-1])
    return head + "/" + database


def _ident(name, pattern):
    if not pattern.match(name):
        raise ValueError("refusing identifier %r" % name)
    return '"%s"' % name


def _schema_ident(name):
    return '"%s"' % name.replace('"', '""')


async def provision(admin_dsn, database, role):
    """Create `role` and confine it in `database` (module docstring).
    Returns a report dict; report["dsn"] is the role's asyncpg DSN."""
    ident = _ident(role, ROLE_RE)
    db_ident = _ident(database, DB_RE)
    admin = await asyncpg.connect(dsn_for(admin_dsn, database))
    report = {"role": role, "database": database, "schemas": [],
              "lo_revoked": [], "lo_unclassified": [], "secdef_revoked": []}
    try:
        await admin.execute(
            "CREATE ROLE %s LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOREPLICATION NOBYPASSRLS" % ident)
        for row in await admin.fetch(SCHEMAS_SQL):
            schema = _schema_ident(row["nspname"])
            report["schemas"].append(row["nspname"])
            await admin.execute("GRANT USAGE ON SCHEMA %s TO %s" % (schema, ident))
            await admin.execute("GRANT SELECT ON ALL TABLES IN SCHEMA %s TO %s" % (schema, ident))
            await admin.execute("GRANT SELECT ON ALL SEQUENCES IN SCHEMA %s TO %s" % (schema, ident))
            await admin.execute(
                "REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER "
                "ON ALL TABLES IN SCHEMA %s FROM PUBLIC" % schema)
            await admin.execute("REVOKE USAGE, UPDATE ON ALL SEQUENCES IN SCHEMA %s FROM PUBLIC" % schema)
            await admin.execute("REVOKE CREATE ON SCHEMA %s FROM PUBLIC, %s" % (schema, ident))
        await admin.execute("REVOKE TEMPORARY ON DATABASE %s FROM PUBLIC, %s" % (db_ident, ident))
        await admin.execute("REVOKE CREATE ON DATABASE %s FROM PUBLIC, %s" % (db_ident, ident))
        await admin.execute("GRANT CONNECT ON DATABASE %s TO %s" % (db_ident, ident))
        for row in await admin.fetch(LO_FUNCS_SQL):
            if row["proname"] in LO_WRITERS:
                await admin.execute("REVOKE EXECUTE ON FUNCTION pg_catalog.%s FROM PUBLIC, %s"
                                    % (row["sig"], ident))
                report["lo_revoked"].append(row["sig"])
            elif row["proname"] not in LO_READERS:
                report["lo_unclassified"].append(row["sig"])
        for row in await admin.fetch(SECDEF_SQL):
            await admin.execute("REVOKE EXECUTE ON ROUTINE %s FROM PUBLIC, %s" % (row["sig"], ident))
            report["secdef_revoked"].append(row["sig"])
        await admin.execute("ALTER ROLE %s SET default_transaction_read_only = on" % ident)
    finally:
        await admin.close()
    report["dsn"] = dsn_for(admin_dsn, database, user=role)
    return report


CENSUS_SQL = """
WITH rels AS (
  SELECT c.oid, n.nspname, c.relname, c.relkind
    FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
     AND c.relkind IN ('r', 'v', 'm', 'f', 'p', 'S'))
SELECT 'relation ' || nspname || '.' || relname || ' ' || p AS what
  FROM rels, unnest(ARRAY['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES',
                          'TRIGGER']) AS p
 WHERE relkind <> 'S' AND pg_catalog.has_table_privilege($1, oid, p)
UNION ALL
SELECT 'relation ' || nspname || '.' || relname || ' not readable'
  FROM rels WHERE relkind <> 'S' AND NOT pg_catalog.has_table_privilege($1, oid, 'SELECT')
UNION ALL
SELECT 'sequence ' || nspname || '.' || relname || ' ' || p
  FROM rels, unnest(ARRAY['USAGE', 'UPDATE']) AS p
 WHERE relkind = 'S' AND pg_catalog.has_sequence_privilege($1, oid, p)
UNION ALL
SELECT 'schema ' || nspname || ' CREATE' FROM pg_catalog.pg_namespace
 WHERE pg_catalog.has_schema_privilege($1, oid, 'CREATE')
UNION ALL
SELECT 'database ' || datname || ' ' || p
  FROM pg_catalog.pg_database, unnest(ARRAY['CREATE', 'TEMPORARY']) AS p
 WHERE datname = pg_catalog.current_database()
   AND pg_catalog.has_database_privilege($1, oid, p)
UNION ALL
SELECT 'function ' || p.oid::pg_catalog.regprocedure::text || ' EXECUTE'
  FROM pg_catalog.pg_proc p
 WHERE (p.prosecdef OR (p.pronamespace = 'pg_catalog'::pg_catalog.regnamespace
                        AND p.proname = ANY($2::text[])))
   AND pg_catalog.has_function_privilege($1, p.oid, 'EXECUTE')
UNION ALL
SELECT 'role attribute ' || a FROM pg_catalog.pg_roles r,
       unnest(ARRAY['rolsuper', 'rolcreatedb', 'rolcreaterole', 'rolreplication',
                    'rolbypassrls']) AS a
 WHERE r.rolname = $1 AND (CASE a WHEN 'rolsuper' THEN r.rolsuper
                                  WHEN 'rolcreatedb' THEN r.rolcreatedb
                                  WHEN 'rolcreaterole' THEN r.rolcreaterole
                                  WHEN 'rolreplication' THEN r.rolreplication
                                  ELSE r.rolbypassrls END)
UNION ALL
SELECT 'member of ' || g.rolname FROM pg_catalog.pg_auth_members m
  JOIN pg_catalog.pg_roles g ON g.oid = m.roleid
  JOIN pg_catalog.pg_roles u ON u.oid = m.member
 WHERE u.rolname = $1
UNION ALL
SELECT 'setting default_transaction_read_only missing'
 WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_db_role_setting s
                     JOIN pg_catalog.pg_roles r ON r.oid = s.setrole
                    WHERE r.rolname = $1 AND s.setdatabase = 0
                      AND 'default_transaction_read_only=on' = ANY(s.setconfig))
ORDER BY 1
"""


async def privilege_census(admin_dsn, database, role):
    """Every write privilege `role` holds in `database`, read from the
    catalog (has_*_privilege counts PUBLIC's grants); [] when confined."""
    admin = await asyncpg.connect(dsn_for(admin_dsn, database))
    try:
        return [r["what"] for r in await admin.fetch(CENSUS_SQL, role, list(LO_WRITERS))]
    finally:
        await admin.close()


async def drop(admin_dsn, database, role, *, drop_database=True):
    """Drop `database` (when asked) and then `role`; both names must be this
    module's (rf7_ro_ prefix for the role). Only client backends of
    `database` are terminated."""
    ident = _ident(role, ROLE_RE)
    db_ident = _ident(database, DB_RE)
    admin = await asyncpg.connect(dsn_for(admin_dsn, "postgres"))
    try:
        if drop_database:
            await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid() "
                "AND backend_type = 'client backend'", database)
            await admin.execute("DROP DATABASE IF EXISTS %s" % db_ident)
        else:
            sub = await asyncpg.connect(dsn_for(admin_dsn, database))
            try:
                await sub.execute("DROP OWNED BY %s" % ident)
            finally:
                await sub.close()
        await admin.execute("DROP ROLE IF EXISTS %s" % ident)
    finally:
        await admin.close()
