"""What DDL a piece of SQL performs, measured at the database.

Ruling REHEARSAL-FOUR-R6 (1)(a) and (2), the D2 arm: the claim "what DDL a
migration performs" is an EFFECT claim. It is not read from the migration's
text. The SQL runs against a real PostgreSQL database, the catalog is read
before and after, and the difference is the DDL it performed, whatever
language, dynamic EXECUTE, format() or function call it went through. Used by
test_r7_catalog_diff_pg.py.

Three measurements, all taken from the server:

  * CATALOG_SQL, one query over pg_namespace, pg_class, pg_attribute,
    pg_attrdef, pg_constraint, pg_index, pg_proc, pg_trigger, pg_policy,
    pg_type (with pg_enum), pg_rewrite, pg_sequence, pg_inherits,
    pg_extension, pg_event_trigger, pg_description, pg_statistic_ext and the
    sequence-ownership rows of pg_depend. It returns one row per object as
    (kind, rel, ident, def, oid). rel is the schema-qualified relation the
    row belongs to ('' when the row belongs to no relation), and oid is
    filled for pg_class rows only, so a table that is dropped and recreated
    with the same shape still differs. The system schemas, temporary schemas
    and PROBE_SCHEMA are left out. A dropped column stays a row
    ('(dropped)#attnum'), so a column added and dropped again is still a
    difference.
  * pg_dump --schema-only, split into pg_dump's own object blocks (one per
    "-- Name: ...; Type: ...; Schema: ...; Owner: ..." header).
  * the command log: PROBE_SQL installs two event triggers that RAISE WARNING
    one 'D2DDL|tag|type|identity' line per DDL command and per dropped object.
    It records DDL that leaves no catalog trace: a temporary table, and the
    commands of a migration that later fails and is rolled back.

A diff is {"added": rows, "removed": rows}. A changed object is one removed
row and one added row with the same (kind, rel, ident). changers() assigns
each step's own diff to that step, so each change is attributed to the
migration that made it.
"""

import os
import re
import shutil
import subprocess

PROBE_SCHEMA = "d2_probe"

PROBE_SQL = """
CREATE SCHEMA d2_probe;
CREATE FUNCTION d2_probe.log_ddl() RETURNS event_trigger LANGUAGE plpgsql AS $d2$
DECLARE r record;
BEGIN
    FOR r IN SELECT * FROM pg_event_trigger_ddl_commands() LOOP
        RAISE WARNING 'D2DDL|%|%|%', r.command_tag, r.object_type, r.object_identity;
    END LOOP;
END
$d2$;
CREATE FUNCTION d2_probe.log_drop() RETURNS event_trigger LANGUAGE plpgsql AS $d2$
DECLARE r record;
BEGIN
    FOR r IN SELECT * FROM pg_event_trigger_dropped_objects() LOOP
        RAISE WARNING 'D2DDL|DROP|%|%', r.object_type, r.object_identity;
    END LOOP;
END
$d2$;
CREATE EVENT TRIGGER d2_probe_ddl ON ddl_command_end EXECUTE FUNCTION d2_probe.log_ddl();
CREATE EVENT TRIGGER d2_probe_drop ON sql_drop EXECUTE FUNCTION d2_probe.log_drop();
"""

CATALOG_SQL = r"""
WITH ns AS (
    SELECT oid, nspname FROM pg_namespace
     WHERE nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'd2_probe')
       AND nspname NOT LIKE 'pg\_temp\_%' AND nspname NOT LIKE 'pg\_toast\_temp\_%'
), rel AS (
    SELECT c.oid, quote_ident(n.nspname) || '.' || quote_ident(c.relname) AS name
      FROM pg_class c JOIN ns n ON n.oid = c.relnamespace
)
SELECT 'namespace', '', quote_ident(n.nspname),
       concat_ws(' ', 'owner=' || pg_get_userbyid(p.nspowner), 'acl=' || coalesce(p.nspacl::text, '')), ''
  FROM ns n JOIN pg_namespace p ON p.oid = n.oid
UNION ALL
SELECT 'class', r.name, c.relkind::text,
       concat_ws(' ', 'persistence=' || c.relpersistence::text, 'rls=' || c.relrowsecurity,
                 'forcerls=' || c.relforcerowsecurity, 'partition=' || c.relispartition,
                 'options=' || coalesce(c.reloptions::text, ''), 'acl=' || coalesce(c.relacl::text, ''),
                 'owner=' || pg_get_userbyid(c.relowner), 'replident=' || c.relreplident::text,
                 'am=' || coalesce(am.amname, ''), 'tablespace=' || c.reltablespace,
                 'oftype=' || CASE WHEN c.reloftype <> 0 THEN format_type(c.reloftype, NULL) ELSE '' END,
                 'bound=' || coalesce(pg_get_expr(c.relpartbound, c.oid), '')),
       c.oid::text
  FROM pg_class c JOIN rel r ON r.oid = c.oid LEFT JOIN pg_am am ON am.oid = c.relam
UNION ALL
SELECT 'attribute', r.name,
       CASE WHEN a.attisdropped THEN '(dropped)#' || a.attnum ELSE quote_ident(a.attname) END,
       CASE WHEN a.attisdropped THEN '' ELSE concat_ws(' ',
            'num=' || a.attnum, 'type=' || format_type(a.atttypid, a.atttypmod),
            'notnull=' || a.attnotnull,
            'identity=' || a.attidentity::text, 'generated=' || a.attgenerated::text,
            'collation=' || coalesce(co.collname, ''), 'stattarget=' || a.attstattarget,
            'storage=' || a.attstorage::text, 'compression=' || a.attcompression::text,
            'options=' || coalesce(a.attoptions::text, ''), 'acl=' || coalesce(a.attacl::text, '')) END,
       ''
  FROM pg_attribute a JOIN rel r ON r.oid = a.attrelid
  LEFT JOIN pg_collation co ON co.oid = a.attcollation
 WHERE a.attnum > 0
UNION ALL
SELECT 'default', r.name, quote_ident(a.attname), pg_get_expr(d.adbin, d.adrelid), ''
  FROM pg_attrdef d JOIN rel r ON r.oid = d.adrelid
  JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
UNION ALL
SELECT 'constraint',
       CASE WHEN k.conrelid <> 0 THEN coalesce(r.name, '?')
            WHEN k.contypid <> 0 THEN 'type:' || format_type(k.contypid, NULL) ELSE '' END,
       quote_ident(k.conname),
       concat_ws(' ', 'type=' || k.contype::text, pg_get_constraintdef(k.oid),
                 'deferrable=' || k.condeferrable, 'deferred=' || k.condeferred,
                 'validated=' || k.convalidated, 'noinherit=' || k.connoinherit),
       ''
  FROM pg_constraint k JOIN ns n ON n.oid = k.connamespace LEFT JOIN rel r ON r.oid = k.conrelid
UNION ALL
SELECT 'index', r.name, quote_ident(ic.relname),
       concat_ws(' ', 'unique=' || i.indisunique, 'primary=' || i.indisprimary,
                 'valid=' || i.indisvalid, 'clustered=' || i.indisclustered,
                 'replident=' || i.indisreplident, 'nullsnotdistinct=' || i.indnullsnotdistinct,
                 regexp_replace(pg_get_indexdef(i.indexrelid), ' ON (ONLY )?\S+ USING ', ' ON \1<rel> USING ')),
       ''
  FROM pg_index i JOIN rel r ON r.oid = i.indrelid JOIN pg_class ic ON ic.oid = i.indexrelid
UNION ALL
SELECT 'trigger', r.name, quote_ident(t.tgname),
       concat_ws(' ', 'enabled=' || t.tgenabled::text, pg_get_triggerdef(t.oid)), ''
  FROM pg_trigger t JOIN rel r ON r.oid = t.tgrelid
 WHERE NOT t.tgisinternal
UNION ALL
SELECT 'policy', r.name, quote_ident(p.polname),
       concat_ws(' ', 'cmd=' || p.polcmd::text, 'permissive=' || p.polpermissive, 'roles=' || p.polroles::text,
                 'using=' || coalesce(pg_get_expr(p.polqual, p.polrelid), ''),
                 'check=' || coalesce(pg_get_expr(p.polwithcheck, p.polrelid), '')), ''
  FROM pg_policy p JOIN rel r ON r.oid = p.polrelid
UNION ALL
SELECT 'rule', r.name, quote_ident(w.rulename),
       concat_ws(' ', 'enabled=' || w.ev_enabled::text, 'def=' || md5(pg_get_ruledef(w.oid))), ''
  FROM pg_rewrite w JOIN rel r ON r.oid = w.ev_class
UNION ALL
SELECT 'proc', '',
       quote_ident(n.nspname) || '.' || quote_ident(p.proname) || '(' || pg_get_function_identity_arguments(p.oid) || ')',
       concat_ws(' ', 'kind=' || p.prokind::text, 'lang=' || l.lanname, 'src=' || md5(coalesce(p.prosrc, '')),
                 'bin=' || coalesce(p.probin, ''), 'result=' || coalesce(pg_get_function_result(p.oid), ''),
                 'volatile=' || p.provolatile::text, 'secdef=' || p.prosecdef, 'strict=' || p.proisstrict,
                 'config=' || coalesce(p.proconfig::text, ''), 'acl=' || coalesce(p.proacl::text, ''),
                 'owner=' || pg_get_userbyid(p.proowner)), ''
  FROM pg_proc p JOIN ns n ON n.oid = p.pronamespace JOIN pg_language l ON l.oid = p.prolang
UNION ALL
SELECT 'type', coalesce(r.name, re.name, ''), quote_ident(n.nspname) || '.' || quote_ident(t.typname),
       concat_ws(' ', 'type=' || t.typtype::text,
                 'base=' || CASE WHEN t.typbasetype <> 0 THEN format_type(t.typbasetype, t.typtypmod) ELSE '' END,
                 'typnotnull=' || t.typnotnull, 'default=' || coalesce(t.typdefault, ''),
                 'labels=' || coalesce((SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)
                                          FROM pg_enum e WHERE e.enumtypid = t.oid), ''),
                 'acl=' || coalesce(t.typacl::text, ''), 'owner=' || pg_get_userbyid(t.typowner)), ''
  FROM pg_type t JOIN ns n ON n.oid = t.typnamespace
  LEFT JOIN rel r ON r.oid = t.typrelid
  LEFT JOIN pg_type et ON et.oid = t.typelem AND t.typcategory = 'A'
  LEFT JOIN rel re ON re.oid = et.typrelid
UNION ALL
SELECT 'sequence', r.name, '',
       concat_ws(' ', format_type(s.seqtypid, NULL), s.seqstart, s.seqincrement, s.seqmax, s.seqmin,
                 s.seqcache, s.seqcycle), ''
  FROM pg_sequence s JOIN rel r ON r.oid = s.seqrelid
UNION ALL
SELECT 'owned', rt.name, quote_ident(sc.relname), coalesce(a.attname::text, ''), ''
  FROM pg_depend d JOIN rel rs ON rs.oid = d.objid JOIN rel rt ON rt.oid = d.refobjid
  JOIN pg_class sc ON sc.oid = d.objid AND sc.relkind = 'S'
  LEFT JOIN pg_attribute a ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid
 WHERE d.classid = 'pg_class'::regclass AND d.refclassid = 'pg_class'::regclass AND d.deptype IN ('a', 'i')
UNION ALL
SELECT 'inherits', r.name, rp.name, s.inhseqno::text, ''
  FROM pg_inherits s JOIN rel r ON r.oid = s.inhrelid JOIN rel rp ON rp.oid = s.inhparent
UNION ALL
SELECT 'statistics', r.name, quote_ident(x.stxname), pg_get_statisticsobjdef(x.oid), ''
  FROM pg_statistic_ext x JOIN rel r ON r.oid = x.stxrelid
UNION ALL
SELECT 'extension', '', quote_ident(x.extname),
       concat_ws(' ', x.extversion, x.extnamespace::regnamespace::text), ''
  FROM pg_extension x
UNION ALL
SELECT 'event_trigger', '', quote_ident(e.evtname),
       concat_ws(' ', e.evtevent, e.evtfoid::regproc::text, e.evtenabled::text, coalesce(e.evttags::text, '')), ''
  FROM pg_event_trigger e
 WHERE e.evtname NOT LIKE 'd2\_probe\_%'
UNION ALL
SELECT 'comment', coalesce(r.name, ''), pg_describe_object(d.classoid, d.objoid, d.objsubid),
       md5(d.description), ''
  FROM pg_description d
  LEFT JOIN rel r ON d.classoid = 'pg_class'::regclass AND r.oid = d.objoid
 WHERE d.objoid >= 16384
"""

# The row kinds compared between two tables of the same shape in different
# schemas (shape()). 'default' is compared by value (the caller evaluates the
# expressions); 'type' rows carry the schema in their ident.
SHAPE_KINDS = ("class", "attribute", "constraint", "index", "trigger", "policy",
               "rule", "comment", "statistics", "inherits", "owned")

ERROR_RE = re.compile(r"ERROR:\s+([0-9A-Z]{5}):\s*([^\r\n]*)")
ERROR_LINE_RE = re.compile(r":(\d+): ERROR:")
DDL_RE = re.compile(r"D2DDL\|([^|\r\n]*)\|([^|\r\n]*)\|([^\r\n]*)")


def client(env_var, name):
    """The PostgreSQL client program: the one env_var names, else the one on
    PATH, else None. No path in this file names a seat."""
    named = os.environ.get(env_var)
    if named:
        return named if (os.path.isfile(named) or shutil.which(named)) else None
    return shutil.which(name)


async def snapshot(conn):
    """The catalog as a frozenset of (kind, rel, ident, def, oid) rows."""
    return frozenset(tuple(r) for r in await conn.fetch(CATALOG_SQL))


def diff(before, after):
    return {"added": sorted(after - before), "removed": sorted(before - after)}


def empty(d):
    return not d["added"] and not d["removed"]


def without_oid(d):
    """d with the oid column dropped: what pg_dump can see of it."""
    add = {r[:4] for r in d["added"]}
    rem = {r[:4] for r in d["removed"]}
    return {"added": sorted(add - rem), "removed": sorted(rem - add)}


def rows_on(d, rel):
    """The rows of diff d that belong to relation rel."""
    return [r for r in d["added"] + d["removed"] if r[1] == rel]


def changers(steps, rel):
    """[label] of every (label, diff) step whose OWN diff has a row on rel."""
    return [label for label, d in steps if rows_on(d, rel)]


def touched(d):
    """The relations (and, for rows on no relation, 'kind:ident') a diff
    changes, sorted."""
    return sorted({r[1] if r[1] else "%s:%s" % (r[0], r[2]) for r in d["added"] + d["removed"]})


def changes(d):
    """(added, removed, changed) (kind, rel, ident) keys of a diff."""
    add = {r[:3] for r in d["added"]}
    rem = {r[:3] for r in d["removed"]}
    return sorted(add - rem), sorted(rem - add), sorted(add & rem)


def shape(rows, rel):
    """The (kind, ident, def) rows of rel, for comparing two relations of the
    same definition that live in different schemas."""
    return sorted((k, i, d) for k, r, i, d, _oid in rows if r == rel and k in SHAPE_KINDS)


def defaults(rows, rel):
    """{column: default expression} of rel."""
    return {i: d for k, r, i, d, _oid in rows if r == rel and k == "default"}


def commands(text):
    """The command log lines (tag, object type, identity) in client output."""
    return [list(m) for m in DDL_RE.findall(text)]


def apply_file(psql, dsn, path):
    """Run one SQL file with psql the way a migration is applied: whole, in
    file order, stopping at the first error. Returns rc, the SQLSTATE and
    message of the error (None when it ran to its end) and the command log."""
    env = dict(os.environ, PGCLIENTENCODING="UTF8")
    proc = subprocess.run(
        [psql, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose",
         "-d", dsn, "-f", path],
        capture_output=True, env=env)
    err = proc.stderr.decode("utf-8", "replace")
    m = ERROR_RE.search(err)
    at = ERROR_LINE_RE.search(err)
    return {"rc": proc.returncode,
            "error_line": int(at.group(1)) if at else None,
            "sqlstate": m.group(1) if m else None,
            "error": m.group(2)[:300] if m else (err.strip()[-300:] if proc.returncode else None),
            "commands": commands(err)}


def dump(pg_dump, dsn):
    """pg_dump --schema-only of the database, newlines normalised."""
    proc = subprocess.run([pg_dump, "--schema-only", "-d", dsn], capture_output=True)
    if proc.returncode:
        raise AssertionError("pg_dump failed: %s" % proc.stderr.decode("utf-8", "replace")[-500:])
    return proc.stdout.decode("utf-8").replace("\r\n", "\n")


_DUMP_HEADER = re.compile(r"^--\n-- (Name: [^\n]*)\n--\n", re.M)


def dump_blocks(text):
    """{header: block}: pg_dump's object blocks, each keyed by its own
    '-- Name: ...; Type: ...; Schema: ...; Owner: ...' header (a repeated
    header gets a '#n' suffix)."""
    parts = _DUMP_HEADER.split(text)
    out = {"(preamble)": parts[0]}
    for k in range(1, len(parts) - 1, 2):
        key, n = parts[k], 1
        while key in out:
            n += 1
            key = "%s#%d" % (parts[k], n)
        out[key] = parts[k + 1]
    return out


def dump_diff(before, after):
    """{added, removed, changed}: header keys of pg_dump blocks."""
    a, b = dump_blocks(before), dump_blocks(after)
    return {"added": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)),
            "changed": sorted(k for k in set(a) & set(b) if a[k] != b[k])}
