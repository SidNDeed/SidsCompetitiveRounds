"""The standing read-only role and its template, as the effect bound of B2
binding soundness and S SQL positions (rulings REHEARSAL-FOUR-R6 (1)(a),
R7-A1 M1/M2 and R7-A2).

No test creates, alters or drops a role, and none changes a pg_catalog ACL.
The cluster carries, provisioned once by postgres (ai-collab/rehearsal-1410/
seat-ro-d2/provision.sql, checked there by verify.sql):

  - ROLE (scr_seat_ro): LOGIN, no superuser, createdb, createrole,
    replication or bypassrls attribute, NOINHERIT, member of no role,
    default_transaction_read_only = on;
  - TEMPLATE (scr_seat_ro_tmpl): a template database owned by postgres,
    PUBLIC unable to CONNECT, on which PUBLIC cannot EXECUTE the large-object
    writer functions or any SECURITY DEFINER routine.

read_cluster() reads both from the catalogs at run time and returns the
sentences of every property that does not hold (the caller FAILS with them;
an absent role or template is such a sentence). clone() makes a database
from the template as the admin DSN user (CREATEDB suffices). grant() then
runs, inside the clone and as its owner, the grants and revokes listed in
GRANT_STEPS: the role reads every relation and sequence of every non-system
schema and can do nothing else that a privilege controls. grant() asserts
nothing about its own result: privilege_census() reads the catalog
afterwards and the test asserts it empty, so a mutant that drops one step is
caught by the census and by the executed control the step guards.
"""

import re

import asyncpg

ROLE = "scr_seat_ro"
TEMPLATE = "scr_seat_ro_tmpl"

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

DB_RE = re.compile(r"^rf8_ro_[a-z0-9_]+$")

# The role and template properties verify.sql prints, read from the shared
# catalogs (any database answers them).
ROLE_SQL = """
SELECT r.rolcanlogin, r.rolsuper, r.rolcreatedb, r.rolcreaterole,
       r.rolreplication, r.rolbypassrls, r.rolinherit,
       (SELECT count(*) FROM pg_catalog.pg_auth_members m WHERE m.member = r.oid) AS members,
       EXISTS (SELECT 1 FROM pg_catalog.pg_db_role_setting s
                WHERE s.setrole = r.oid AND s.setdatabase = 0
                  AND 'default_transaction_read_only=on' = ANY (s.setconfig)) AS ro_default
  FROM pg_catalog.pg_roles r WHERE r.rolname = $1
"""
TEMPLATE_SQL = """
SELECT d.datistemplate, pg_catalog.pg_get_userbyid(d.datdba) AS owner,
       pg_catalog.has_database_privilege('public', d.oid, 'CONNECT') AS public_connect
  FROM pg_catalog.pg_database d WHERE d.datname = $1
"""
ROLE_WANT = (("rolcanlogin", True), ("rolsuper", False), ("rolcreatedb", False),
             ("rolcreaterole", False), ("rolreplication", False),
             ("rolbypassrls", False), ("rolinherit", False), ("members", 0),
             ("ro_default", True))
TEMPLATE_WANT = (("datistemplate", True), ("owner", "postgres"),
                 ("public_connect", False))

SCHEMAS_SQL = ("SELECT nspname FROM pg_catalog.pg_namespace "
               "WHERE nspname <> 'information_schema' AND nspname !~ '^pg_' "
               "ORDER BY 1")
# SECURITY DEFINER routines outside pg_catalog: the clone's own (its
# migrations' and its harness's). pg_catalog's are the template's (revoked
# there, by postgres).
SECDEF_SQL = ("SELECT p.oid::pg_catalog.regprocedure::text AS sig "
              "FROM pg_catalog.pg_proc p WHERE p.prosecdef "
              "AND p.pronamespace <> 'pg_catalog'::pg_catalog.regnamespace ORDER BY 1")
LO_TEMPLATE_SQL = """
SELECT count(*) AS writers,
       count(*) FILTER (WHERE pg_catalog.has_function_privilege($1, p.oid, 'EXECUTE')) AS executable
  FROM pg_catalog.pg_proc p
 WHERE p.pronamespace = 'pg_catalog'::pg_catalog.regnamespace
   AND p.proname = ANY($2::text[])
"""

# The clone's grant step: (name, statement template). {schema} is each
# non-system schema (quoted), {db} the clone, {role} the role, {sig} each
# SECURITY DEFINER routine of the clone's own. The mutants of
# test_r8_ro_role_pg remove one step each.
GRANT_STEPS = (
    ("schema_usage", "GRANT USAGE ON SCHEMA {schema} TO {role}"),
    ("tables_select", "GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {role}"),
    ("sequences_select", "GRANT SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {role}"),
    ("tables_public_writes", "REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, "
                             "TRIGGER ON ALL TABLES IN SCHEMA {schema} FROM PUBLIC"),
    ("sequences_public", "REVOKE USAGE, UPDATE ON ALL SEQUENCES IN SCHEMA {schema} "
                         "FROM PUBLIC"),
    ("schema_create", "REVOKE CREATE ON SCHEMA {schema} FROM PUBLIC, {role}"),
    ("database_temporary", "REVOKE TEMPORARY ON DATABASE {db} FROM PUBLIC, {role}"),
    ("database_create", "REVOKE CREATE ON DATABASE {db} FROM PUBLIC, {role}"),
    ("database_connect_public", "REVOKE CONNECT ON DATABASE {db} FROM PUBLIC"),
    ("database_connect_role", "GRANT CONNECT ON DATABASE {db} TO {role}"),
    ("secdef_execute", "REVOKE EXECUTE ON ROUTINE {sig} FROM PUBLIC, {role}"),
)
PER_SCHEMA = ("schema_usage", "tables_select", "sequences_select",
              "tables_public_writes", "sequences_public", "schema_create")
PER_DATABASE = ("database_temporary", "database_create",
                "database_connect_public", "database_connect_role")


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


def _db_ident(name):
    if not DB_RE.match(name):
        raise ValueError("refusing database name %r" % name)
    return '"%s"' % name


def _q(name):
    return '"%s"' % name.replace('"', '""')


async def read_cluster(admin_dsn, role=ROLE, template=TEMPLATE):
    """Sentences naming every property of `role` and `template` that does
    not hold (verify.sql's first line); [] when the cluster is provisioned."""
    conn = await asyncpg.connect(dsn_for(admin_dsn, "postgres"))
    try:
        r = await conn.fetchrow(ROLE_SQL, role)
        t = await conn.fetchrow(TEMPLATE_SQL, template)
    finally:
        await conn.close()
    out = []
    if r is None:
        out.append("the role %s does not exist on this cluster (provision.sql "
                   "step 1 has not run here)" % role)
    else:
        out += ["the role %s has %s=%r, provisioned as %r" % (role, k, r[k], v)
                for k, v in ROLE_WANT if r[k] != v]
    if t is None:
        out.append("the template database %s does not exist on this cluster "
                   "(provision.sql step 2 has not run here)" % template)
    else:
        out += ["the template %s has %s=%r, provisioned as %r" % (template, k, t[k], v)
                for k, v in TEMPLATE_WANT if t[k] != v]
    return out


async def clone(admin_dsn, database, template=TEMPLATE):
    """CREATE DATABASE `database` TEMPLATE `template`, as the admin DSN's
    user (CREATEDB suffices); that user owns the clone."""
    conn = await asyncpg.connect(dsn_for(admin_dsn, "postgres"))
    try:
        await conn.execute("CREATE DATABASE %s TEMPLATE %s"
                           % (_db_ident(database), _q(template)))
    finally:
        await conn.close()


async def template_lo_state(admin_dsn, database, role=ROLE):
    """(large-object writer count, how many `role` may EXECUTE) in the
    clone: the template's revokes, carried by the clone's pg_proc."""
    conn = await asyncpg.connect(dsn_for(admin_dsn, database))
    try:
        row = await conn.fetchrow(LO_TEMPLATE_SQL, role, list(LO_WRITERS))
        return row["writers"], row["executable"]
    finally:
        await conn.close()


async def grant(admin_dsn, database, role=ROLE, skip=()):
    """GRANT_STEPS inside `database`, as its owner (the admin DSN's user).
    `skip` names steps to leave out (the mutants). Returns a report dict;
    report["dsn"] is the role's asyncpg DSN for the clone."""
    db = _db_ident(database)
    ident = _q(role)
    steps = dict(GRANT_STEPS)
    conn = await asyncpg.connect(dsn_for(admin_dsn, database))
    report = {"role": role, "database": database, "schemas": [],
              "secdef_revoked": [], "ran": []}
    try:
        for row in await conn.fetch(SCHEMAS_SQL):
            report["schemas"].append(row["nspname"])
            for name in PER_SCHEMA:
                if name not in skip:
                    await conn.execute(steps[name].format(
                        schema=_q(row["nspname"]), role=ident))
                    report["ran"].append(name)
        for name in PER_DATABASE:
            if name not in skip:
                await conn.execute(steps[name].format(db=db, role=ident))
                report["ran"].append(name)
        for row in await conn.fetch(SECDEF_SQL):
            if "secdef_execute" not in skip:
                await conn.execute(steps["secdef_execute"].format(
                    sig=row["sig"], role=ident))
                report["ran"].append("secdef_execute")
            report["secdef_revoked"].append(row["sig"])
    finally:
        await conn.close()
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
 WHERE CASE WHEN relkind = 'S' THEN pg_catalog.has_sequence_privilege($1, oid, p)
            ELSE false END
UNION ALL
SELECT 'sequence ' || nspname || '.' || relname || ' not readable'
  FROM rels WHERE CASE WHEN relkind = 'S'
                      THEN NOT pg_catalog.has_sequence_privilege($1, oid, 'SELECT')
                      ELSE false END
UNION ALL
SELECT 'schema ' || nspname || ' CREATE' FROM pg_catalog.pg_namespace
 WHERE pg_catalog.has_schema_privilege($1, oid, 'CREATE')
UNION ALL
SELECT 'schema ' || nspname || ' no USAGE' FROM pg_catalog.pg_namespace
 WHERE nspname <> 'information_schema' AND nspname !~ '^pg_'
   AND NOT pg_catalog.has_schema_privilege($1, oid, 'USAGE')
UNION ALL
SELECT 'database ' || datname || ' ' || p
  FROM pg_catalog.pg_database, unnest(ARRAY['CREATE', 'TEMPORARY']) AS p
 WHERE datname = pg_catalog.current_database()
   AND pg_catalog.has_database_privilege($1, oid, p)
UNION ALL
SELECT 'database ' || datname || ' CONNECT by PUBLIC'
  FROM pg_catalog.pg_database
 WHERE datname = pg_catalog.current_database()
   AND pg_catalog.has_database_privilege('public', oid, 'CONNECT')
UNION ALL
SELECT 'function ' || p.oid::pg_catalog.regprocedure::text || ' EXECUTE'
  FROM pg_catalog.pg_proc p
 WHERE (p.prosecdef OR (p.pronamespace = 'pg_catalog'::pg_catalog.regnamespace
                        AND p.proname = ANY($2::text[])))
   AND pg_catalog.has_function_privilege($1, p.oid, 'EXECUTE')
UNION ALL
SELECT 'role attribute ' || a FROM pg_catalog.pg_roles r,
       unnest(ARRAY['rolsuper', 'rolcreatedb', 'rolcreaterole', 'rolreplication',
                    'rolbypassrls', 'rolinherit']) AS a
 WHERE r.rolname = $1 AND (CASE a WHEN 'rolsuper' THEN r.rolsuper
                                  WHEN 'rolcreatedb' THEN r.rolcreatedb
                                  WHEN 'rolcreaterole' THEN r.rolcreaterole
                                  WHEN 'rolreplication' THEN r.rolreplication
                                  WHEN 'rolinherit' THEN r.rolinherit
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


async def privilege_census(admin_dsn, database, role=ROLE):
    """Every write privilege `role` holds in `database`, and every read it
    lacks, read from the catalog (has_*_privilege counts PUBLIC's grants);
    [] when confined."""
    conn = await asyncpg.connect(dsn_for(admin_dsn, database))
    try:
        return [r["what"] for r in await conn.fetch(CENSUS_SQL, role, list(LO_WRITERS))]
    finally:
        await conn.close()


async def drop_clone(admin_dsn, database):
    """Drop the clone `database` (an rf8_ro_ name). Only this user's client
    backends of it are terminated (a non-superuser may signal no other)."""
    db = _db_ident(database)
    conn = await asyncpg.connect(dsn_for(admin_dsn, "postgres"))
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid() "
            "AND backend_type = 'client backend' AND usename = current_user", database)
        await conn.execute("DROP DATABASE IF EXISTS %s" % db)
    finally:
        await conn.close()
