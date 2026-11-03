"""What DDL a piece of SQL performs, measured at the database.

Ruling REHEARSAL-FOUR-R6 (1)(a) and (2), the D2 arm: the claim "what DDL a
migration performs" is an EFFECT claim. It is not read from the migration's
text. The SQL runs against a real PostgreSQL database, the catalog is read
before and after, and the difference is the DDL it performed, whatever
language, dynamic EXECUTE, format() or function call it went through. Used by
test_r7_catalog_diff_pg.py.

Three measurements, all taken from the server:

  * CATALOG_SQL, one query over the catalogs pg_dump renders (DUMP_SWEEP
    below lists every pg_dump object type and the catalog each is read
    from). It returns one row per object as (kind, rel, ident, def, oid,
    cand). rel is the schema-qualified relation the row belongs to ('' when
    it belongs to no relation); oid is filled for pg_class rows only, so a
    table dropped and recreated with the same shape still differs; cand is
    the pg_dump object (or objects, most specific first) that renders the
    row, as 'Type|Schema|Name' (DEFAULT ACL adds '|Owner'). The system
    schemas, temporary schemas and PROBE_SCHEMA are left out. A dropped
    column stays a row ('(dropped)#attnum'). The query runs with
    search_path '' (snapshot()), as pg_dump reads, so every name it prints
    is schema-qualified the same way whatever the caller's search_path.
  * pg_dump --schema-only, split into pg_dump's own object blocks (one per
    "-- Name: ...; Type: ...; Schema: ...; Owner: ..." header).
  * the command log: the template database every measured database is
    cloned from (ruling R7-A2) carries two event triggers that RAISE
    WARNING one 'D2DDL|tag|type|identity' line per DDL command and per
    dropped object. It records DDL that leaves no catalog trace: a
    temporary table, and the commands of a migration that later fails and
    is rolled back. PROBE_SQL is kept only to compare it with the
    template's probe (the template must carry exactly this probe).

A diff is {"added": rows, "removed": rows}. A changed object is one removed
row and one added row with the same (kind, rel, ident). changers() assigns
each step's own diff to that step, so each change is attributed to the
migration that made it.

The two measurements are compared as OBJECT SETS (ruling R7-A1, M9):
catalog_objects() reduces a catalog diff to the pg_dump objects its changed
rows render in, dump_objects() reduces a pg_dump diff to the objects whose
block text changed, and match() returns every object one side changed and
the other did not. The one column pg_dump cannot print is the oid, so rows
that differ ONLY in oid are listed apart (oid_only()) and are not objects.

The object measurement is an enumeration of the catalogs pg_dump renders
(ruling REHEARSAL-R8-A1, E1: a role default, the enabled state of an
internal trigger changed unseen). snapshot() therefore ALSO returns the rows
of catalog_all: every pg_catalog relation of kind 'r', taken at run time,
read whole except the exclusions it declares one by one ('raw' rows). The
raw rows carry the relations they name, so rows_on() and changers() see
them; match() holds them to the object set: every changed raw row of a step
must be accounted for by an object change of that step on a relation the
row names, of a kind catalog_all.EXPLAINS lists for its catalog, or it is
returned as unmatched beside the objects (catalog_all.unexplained()).
"""

import os
import re
import shutil
import subprocess

import catalog_all

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

# The probe's event triggers and the functions they call, as PROBE_SQL
# defines them: {trigger: (event, function)}.
PROBE_TRIGGERS = {"d2_probe_ddl": ("ddl_command_end", "log_ddl"),
                  "d2_probe_drop": ("sql_drop", "log_drop")}


def probe_bodies():
    """{function name: body} of PROBE_SQL's two functions, byte for byte."""
    return dict(re.findall(r"CREATE FUNCTION d2_probe\.(\w+)\(\)[^$]*\$d2\$(.*?)\$d2\$", PROBE_SQL, re.S))


# pg_dump's object types (pg_dump.c / pg_backup_archiver.c, PostgreSQL 16)
# and the catalog CATALOG_SQL reads each from. None marks a type pg_dump
# --schema-only does not emit for a database (cluster-wide objects, data,
# large objects) with the reason. The sweep is asserted by the test: a
# pg_dump block of a type not listed here fails it.
DUMP_SWEEP = {
    "ACCESS METHOD": "pg_am", "ACL": "pg_namespace/pg_class/pg_attribute/pg_proc/pg_type/"
    "pg_foreign_data_wrapper/pg_foreign_server/pg_language .acl columns",
    "AGGREGATE": "pg_proc + pg_aggregate", "CAST": "pg_cast", "CHECK CONSTRAINT": "pg_constraint",
    "COLLATION": "pg_collation", "COMMENT": "pg_description", "CONSTRAINT": "pg_constraint + pg_index",
    "CONVERSION": "pg_conversion", "DEFAULT": "pg_attrdef", "DEFAULT ACL": "pg_default_acl",
    "DOMAIN": "pg_type + pg_constraint", "EVENT TRIGGER": "pg_event_trigger", "EXTENSION": "pg_extension",
    "FK CONSTRAINT": "pg_constraint", "FOREIGN DATA WRAPPER": "pg_foreign_data_wrapper",
    "FOREIGN TABLE": "pg_class + pg_foreign_table + pg_attribute", "FUNCTION": "pg_proc",
    "INDEX": "pg_class + pg_index", "INDEX ATTACH": "pg_inherits", "MATERIALIZED VIEW": "pg_class + pg_rewrite",
    "OPERATOR": "pg_operator", "OPERATOR CLASS": "pg_opclass", "OPERATOR FAMILY": "pg_opfamily",
    "POLICY": "pg_policy", "PROCEDURAL LANGUAGE": "pg_language", "PROCEDURE": "pg_proc",
    "PUBLICATION": "pg_publication", "PUBLICATION TABLE": "pg_publication_rel",
    "PUBLICATION TABLES IN SCHEMA": "pg_publication_namespace", "ROW SECURITY": "pg_class.relrowsecurity",
    "RULE": "pg_rewrite", "SCHEMA": "pg_namespace", "SEQUENCE": "pg_class + pg_sequence (+ identity pg_depend)",
    "SEQUENCE OWNED BY": "pg_depend", "SERVER": "pg_foreign_server", "STATISTICS": "pg_statistic_ext",
    "SUBSCRIPTION": "pg_subscription", "TABLE": "pg_class + pg_attribute + pg_inherits + pg_partitioned_table",
    "TABLE ATTACH": "pg_class.relpartbound + pg_inherits", "TEXT SEARCH CONFIGURATION": "pg_ts_config",
    "TEXT SEARCH DICTIONARY": "pg_ts_dict", "TEXT SEARCH PARSER": "pg_ts_parser",
    "TEXT SEARCH TEMPLATE": "pg_ts_template", "TRANSFORM": "pg_transform", "TRIGGER": "pg_trigger",
    "TYPE": "pg_type + pg_enum + pg_range (+ composite pg_class)", "USER MAPPING": "pg_user_mapping",
    "VIEW": "pg_class + pg_rewrite",
    # not emitted by pg_dump --schema-only of one database:
    "BLOB": None,                       # large objects are data in PostgreSQL 16 (--schema-only drops them)
    "BLOB METADATA": None,
    "DATABASE": None,                   # only with --create
    "DATABASE PROPERTIES": None,        # only with --create
    "ENCODING": None, "STDSTRINGS": None, "SEARCHPATH": None,   # session settings, no object
    "SECURITY LABEL": None,             # needs a label provider; none can load without a superuser
    "SHELL TYPE": "pg_type",
    "TABLE DATA": None, "SEQUENCE SET": None, "MATERIALIZED VIEW DATA": None,  # data
    "LARGE OBJECT": None,
}

def _acl_text(acl, owner):
    """SQL rendering an ACL the way pg_dump reads it: every entry as
    grantee=privilege[*]/grantor, sorted, with the object's OWNER written as
    'owner' wherever it is grantee or grantor. pg_dump emits GRANT/REVOKE
    relative to the owner's default and omits a grantor equal to the owner,
    so an ownership change (which rewrites the old owner to the new one in
    the ACL) leaves the ACL text unchanged; any other entry change moves it."""
    return ("(SELECT coalesce(string_agg(z.x, ',' ORDER BY z.x), '') FROM (SELECT "
            "CASE WHEN e.grantee = {o} THEN 'owner' WHEN e.grantee = 0 THEN 'public' "
            "ELSE quote_ident(pg_get_userbyid(e.grantee)) END || '=' || e.privilege_type "
            "|| CASE WHEN e.is_grantable THEN '*' ELSE '' END || '/' "
            "|| CASE WHEN e.grantor = {o} THEN 'owner' ELSE quote_ident(pg_get_userbyid(e.grantor)) END AS x "
            "FROM aclexplode({a}) e) z)").format(a=acl, o=owner)


def _expand(sql):
    out, i = [], 0
    while True:
        j = sql.find("@ACL(", i)
        if j < 0:
            return "".join(out) + sql[i:]
        k = sql.index(")@", j)
        acl, owner = sql[j + 5:k].rsplit("; ", 1)
        out.append(sql[i:j] + _acl_text(acl, owner))
        i = k + 2


CATALOG_SQL = r"""
WITH ns AS (
    SELECT oid, nspname FROM pg_namespace
     WHERE nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'd2_probe')
       AND nspname NOT LIKE 'pg\_temp\_%' AND nspname NOT LIKE 'pg\_toast\_temp\_%'
), ext AS (
    SELECT d.classid, d.objid, e.extname
      FROM pg_depend d JOIN pg_extension e ON e.oid = d.refobjid
     WHERE d.refclassid = 'pg_extension'::regclass AND d.deptype = 'e'
), ip AS (
    SELECT classoid, objoid, objsubid, initprivs FROM pg_init_privs
), rel AS (
    SELECT c.oid, quote_ident(n.nspname) || '.' || quote_ident(c.relname) AS name,
           n.nspname AS nsp, c.relname, c.relkind,
           CASE WHEN x.extname IS NOT NULL THEN ARRAY['EXTENSION|-|' || x.extname]
                WHEN c.relkind IN ('i', 'I') THEN
                     ARRAY['INDEX|' || n.nspname || '|' || c.relname,
                           'CONSTRAINT|' || n.nspname || '|' || coalesce(it.relname, '') || ' ' || c.relname]
                ELSE ARRAY[CASE c.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW'
                                WHEN 'S' THEN 'SEQUENCE' WHEN 'f' THEN 'FOREIGN TABLE' WHEN 'c' THEN 'TYPE'
                                ELSE 'TABLE' END || '|' || n.nspname || '|' || c.relname] END AS cand,
           CASE c.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' WHEN 'S' THEN 'SEQUENCE'
                WHEN 'i' THEN 'INDEX' WHEN 'I' THEN 'INDEX' WHEN 'f' THEN 'FOREIGN TABLE' WHEN 'c' THEN 'TYPE'
                ELSE 'TABLE' END AS word
      FROM pg_class c JOIN ns n ON n.oid = c.relnamespace
      LEFT JOIN ext x ON x.classid = 'pg_class'::regclass AND x.objid = c.oid
      LEFT JOIN pg_index ix ON ix.indexrelid = c.oid LEFT JOIN pg_class it ON it.oid = ix.indrelid
), typ0 AS (
    SELECT t.oid, n.nspname AS nsp,
           CASE WHEN x.extname IS NOT NULL THEN ARRAY['EXTENSION|-|' || x.extname]
                WHEN t.typrelid <> 0 THEN (SELECT r.cand FROM rel r WHERE r.oid = t.typrelid)
                WHEN t.typtype = 'm' THEN (SELECT ARRAY['TYPE|' || rn.nspname || '|' || rt.typname]
                                             FROM pg_range g JOIN pg_type rt ON rt.oid = g.rngtypid
                                             JOIN pg_namespace rn ON rn.oid = rt.typnamespace
                                            WHERE g.rngmultitypid = t.oid)
                WHEN t.typtype = 'd' THEN ARRAY['DOMAIN|' || n.nspname || '|' || t.typname]
                ELSE ARRAY['TYPE|' || n.nspname || '|' || t.typname] END AS cand
      FROM pg_type t JOIN ns n ON n.oid = t.typnamespace
      LEFT JOIN ext x ON x.classid = 'pg_type'::regclass AND x.objid = t.oid
), typ AS (
    SELECT t.oid, CASE WHEN t.typcategory = 'A' AND t.typelem <> 0
                       THEN coalesce((SELECT e.cand FROM typ0 e WHERE e.oid = t.typelem), b.cand)
                       ELSE b.cand END AS cand
      FROM pg_type t JOIN typ0 b ON b.oid = t.oid
), prc AS (
    SELECT p.oid, n.nspname AS nsp,
           CASE p.prokind WHEN 'p' THEN 'PROCEDURE' WHEN 'a' THEN 'AGGREGATE' ELSE 'FUNCTION' END AS word,
           CASE p.prokind WHEN 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END AS aclword,
           p.proname || '(' || coalesce((SELECT string_agg(format_type(a.t, NULL), ', ' ORDER BY a.k)
                                           FROM unnest(p.proargtypes::oid[]) WITH ORDINALITY a(t, k)), '')
                    || ')' AS sig,
           quote_ident(p.proname) || '(' || pg_get_function_identity_arguments(p.oid) || ')' AS ident,
           CASE WHEN x.extname IS NOT NULL THEN ARRAY['EXTENSION|-|' || x.extname]
                WHEN di.refobjid IS NOT NULL THEN (SELECT y.cand FROM typ y WHERE y.oid = di.refobjid)
                ELSE NULL END AS owner_cand
      FROM pg_proc p JOIN ns n ON n.oid = p.pronamespace
      LEFT JOIN ext x ON x.classid = 'pg_proc'::regclass AND x.objid = p.oid
      LEFT JOIN pg_depend di ON di.classid = 'pg_proc'::regclass AND di.objid = p.oid
                            AND di.refclassid = 'pg_type'::regclass AND di.deptype = 'i'
)
SELECT 'namespace', '', quote_ident(n.nspname), 'owner=' || pg_get_userbyid(p.nspowner), '',
       ARRAY['SCHEMA|-|' || n.nspname]
  FROM ns n JOIN pg_namespace p ON p.oid = n.oid
UNION ALL
SELECT 'acl', '', 'SCHEMA ' || quote_ident(n.nspname), @ACL(coalesce(p.nspacl, acldefault('n'::"char", p.nspowner)); p.nspowner)@, '',
       ARRAY['ACL|-|SCHEMA ' || quote_ident(n.nspname)]
  FROM ns n JOIN pg_namespace p ON p.oid = n.oid
  LEFT JOIN ip ON ip.classoid = 'pg_namespace'::regclass AND ip.objoid = p.oid AND ip.objsubid = 0
 WHERE coalesce(p.nspacl, acldefault('n'::"char", p.nspowner))
       IS DISTINCT FROM coalesce(ip.initprivs, acldefault('n'::"char", p.nspowner))
UNION ALL
SELECT 'class', r.name, c.relkind::text,
       concat_ws(' ', 'persistence=' || c.relpersistence::text,
                 'forcerls=' || c.relforcerowsecurity,
                 'options=' || coalesce(c.reloptions::text, ''),
                 CASE WHEN c.relkind NOT IN ('i', 'I') THEN 'owner=' || pg_get_userbyid(c.relowner) END,
                 'replident=' || CASE WHEN c.relreplident = 'i' THEN 'd' ELSE c.relreplident::text END,
                 'am=' || coalesce(am.amname, ''), 'tablespace=' || c.reltablespace,
                 'oftype=' || CASE WHEN c.reloftype <> 0 THEN format_type(c.reloftype, NULL) ELSE '' END,
                 'partkey=' || CASE WHEN c.relkind = 'p' THEN pg_get_partkeydef(c.oid) ELSE '' END,
                 'ftoptions=' || coalesce((SELECT f.ftserver::text || ':' || coalesce(f.ftoptions::text, '')
                                             FROM pg_foreign_table f WHERE f.ftrelid = c.oid), '')),
       c.oid::text, r.cand
  FROM pg_class c JOIN rel r ON r.oid = c.oid LEFT JOIN pg_am am ON am.oid = c.relam
UNION ALL
SELECT 'rls', r.name, 'rls', 'rls=true', '', ARRAY['ROW SECURITY|' || r.nsp || '|' || r.relname]
  FROM pg_class c JOIN rel r ON r.oid = c.oid WHERE c.relrowsecurity
UNION ALL
SELECT 'partition', r.name, 'bound', pg_get_expr(c.relpartbound, c.oid), '',
       ARRAY[CASE WHEN c.relkind IN ('i', 'I') THEN 'INDEX ATTACH' ELSE 'TABLE ATTACH' END
             || '|' || r.nsp || '|' || r.relname]
  FROM pg_class c JOIN rel r ON r.oid = c.oid WHERE c.relispartition
UNION ALL
SELECT 'acl', r.name, CASE WHEN c.relkind = 'S' THEN 'SEQUENCE ' ELSE 'TABLE ' END || quote_ident(c.relname),
       @ACL(coalesce(c.relacl, acldefault((CASE WHEN c.relkind = 'S' THEN 's' ELSE 'r' END)::"char", c.relowner)); c.relowner)@, '',
       ARRAY['ACL|' || r.nsp || '|' || CASE WHEN c.relkind = 'S' THEN 'SEQUENCE ' ELSE 'TABLE ' END
             || quote_ident(c.relname)]
  FROM pg_class c JOIN rel r ON r.oid = c.oid
  LEFT JOIN ip ON ip.classoid = 'pg_class'::regclass AND ip.objoid = c.oid AND ip.objsubid = 0
 WHERE coalesce(c.relacl, acldefault((CASE WHEN c.relkind = 'S' THEN 's' ELSE 'r' END)::"char", c.relowner))
       IS DISTINCT FROM coalesce(ip.initprivs, acldefault((CASE WHEN c.relkind = 'S' THEN 's' ELSE 'r' END)::"char", c.relowner))
UNION ALL
SELECT 'attribute', r.name,
       CASE WHEN a.attisdropped THEN '(dropped)#' || a.attnum ELSE quote_ident(a.attname) END,
       CASE WHEN a.attisdropped THEN '' ELSE concat_ws(' ',
            'num=' || a.attnum, 'type=' || format_type(a.atttypid, a.atttypmod),
            'notnull=' || a.attnotnull,
            'identity=' || a.attidentity::text, 'generated=' || a.attgenerated::text,
            'collation=' || coalesce(co.collname, ''), 'stattarget=' || a.attstattarget,
            'storage=' || a.attstorage::text, 'compression=' || a.attcompression::text,
            'options=' || coalesce(a.attoptions::text, ''),
            'fdwoptions=' || coalesce(a.attfdwoptions::text, '')) END,
       '',
       -- an index column that is a plain table column (indkey[n] <> 0)
       -- mirrors that column: it belongs to its index/constraint, and ALSO to
       -- the table when the table's rendering changed in the same step (a
       -- column widened under a UNIQUE constraint); '~' marks a candidate
       -- that resolve() takes only when its dump block changed
       CASE WHEN ix.indexrelid IS NOT NULL AND ix.indkey[a.attnum - 1] <> 0
            THEN r.cand || ARRAY(SELECT '~' || x FROM unnest(rt.cand) x) ELSE r.cand END
  FROM pg_attribute a JOIN rel r ON r.oid = a.attrelid
  LEFT JOIN pg_collation co ON co.oid = a.attcollation
  LEFT JOIN pg_index ix ON ix.indexrelid = a.attrelid
  LEFT JOIN rel rt ON rt.oid = ix.indrelid
 WHERE a.attnum > 0
UNION ALL
SELECT 'acl', r.name, 'COLUMN ' || quote_ident(r.relname) || '.' || quote_ident(a.attname),
       @ACL(a.attacl; (SELECT k.relowner FROM pg_class k WHERE k.oid = a.attrelid))@, '',
       ARRAY['ACL|' || r.nsp || '|COLUMN ' || quote_ident(r.relname) || '.' || quote_ident(a.attname)]
  FROM pg_attribute a JOIN rel r ON r.oid = a.attrelid
 WHERE a.attnum > 0 AND coalesce(a.attacl, '{}') <> '{}'
UNION ALL
SELECT 'default', r.name, quote_ident(a.attname), pg_get_expr(d.adbin, d.adrelid), '',
       ARRAY['DEFAULT|' || r.nsp || '|' || r.relname || ' ' || a.attname] || r.cand
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
       '',
       CASE WHEN r.cand[1] LIKE 'EXTENSION|%' THEN r.cand
            WHEN k.conrelid <> 0 THEN
                 CASE k.contype WHEN 'f' THEN ARRAY['FK CONSTRAINT|' || r.nsp || '|' || r.relname || ' ' || k.conname]
                                WHEN 't' THEN ARRAY['TRIGGER|' || r.nsp || '|' || r.relname || ' ' || k.conname]
                                WHEN 'c' THEN ARRAY['CHECK CONSTRAINT|' || r.nsp || '|' || r.relname || ' ' || k.conname,
                                                    'CONSTRAINT|' || r.nsp || '|' || r.relname || ' ' || k.conname] || r.cand
                                ELSE ARRAY['CONSTRAINT|' || r.nsp || '|' || r.relname || ' ' || k.conname] END
            WHEN k.contypid <> 0 THEN
                 ARRAY['CHECK CONSTRAINT|' || n.nspname || '|' || dt.typname || ' ' || k.conname]
                 || (SELECT y.cand FROM typ y WHERE y.oid = k.contypid)
            ELSE ARRAY['CONSTRAINT|' || n.nspname || '|' || k.conname] END
  FROM pg_constraint k JOIN ns n ON n.oid = k.connamespace LEFT JOIN rel r ON r.oid = k.conrelid
  LEFT JOIN pg_type dt ON dt.oid = k.contypid
UNION ALL
SELECT 'index', r.name, quote_ident(ic.relname),
       concat_ws(' ', 'unique=' || i.indisunique, 'primary=' || i.indisprimary,
                 'valid=' || i.indisvalid, 'clustered=' || i.indisclustered,
                 'replident=' || i.indisreplident, 'nullsnotdistinct=' || i.indnullsnotdistinct,
                 regexp_replace(pg_get_indexdef(i.indexrelid), ' ON (ONLY )?\S+ USING ', ' ON \1<rel> USING ')),
       '', ri.cand
  FROM pg_index i JOIN rel r ON r.oid = i.indrelid JOIN pg_class ic ON ic.oid = i.indexrelid
  JOIN rel ri ON ri.oid = i.indexrelid
UNION ALL
SELECT 'trigger', r.name, quote_ident(t.tgname),
       concat_ws(' ', 'enabled=' || t.tgenabled::text, pg_get_triggerdef(t.oid)), '',
       ARRAY['TRIGGER|' || r.nsp || '|' || r.relname || ' ' || t.tgname]
  FROM pg_trigger t JOIN rel r ON r.oid = t.tgrelid
 WHERE NOT t.tgisinternal AND t.tgconstraint = 0
UNION ALL
SELECT 'policy', r.name, quote_ident(p.polname),
       concat_ws(' ', 'cmd=' || p.polcmd::text, 'permissive=' || p.polpermissive, 'roles=' || p.polroles::text,
                 'using=' || coalesce(pg_get_expr(p.polqual, p.polrelid), ''),
                 'check=' || coalesce(pg_get_expr(p.polwithcheck, p.polrelid), '')), '',
       ARRAY['POLICY|' || r.nsp || '|' || r.relname || ' ' || p.polname]
  FROM pg_policy p JOIN rel r ON r.oid = p.polrelid
UNION ALL
SELECT 'rule', r.name, quote_ident(w.rulename),
       concat_ws(' ', 'enabled=' || w.ev_enabled::text, 'def=' || md5(pg_get_ruledef(w.oid))), '',
       CASE WHEN w.rulename = '_RETURN' THEN r.cand
            ELSE ARRAY['RULE|' || r.nsp || '|' || r.relname || ' ' || w.rulename] END
  FROM pg_rewrite w JOIN rel r ON r.oid = w.ev_class
UNION ALL
SELECT 'proc', '', quote_ident(f.nsp) || '.' || f.ident,
       concat_ws(' ', 'kind=' || p.prokind::text, 'lang=' || l.lanname,
                 'def=' || md5(CASE WHEN p.prokind = 'a' THEN coalesce((SELECT g::text FROM pg_aggregate g
                                                                          WHERE g.aggfnoid = p.oid), '')
                                    ELSE pg_get_functiondef(p.oid) END),
                 'src=' || md5(coalesce(p.prosrc, '')), 'bin=' || coalesce(p.probin, ''),
                 'result=' || coalesce(pg_get_function_result(p.oid), ''),
                 'volatile=' || p.provolatile::text, 'secdef=' || p.prosecdef, 'strict=' || p.proisstrict,
                 'config=' || coalesce(p.proconfig::text, ''), 'owner=' || pg_get_userbyid(p.proowner)), '',
       coalesce(f.owner_cand, ARRAY[f.word || '|' || f.nsp || '|' || f.sig])
  FROM pg_proc p JOIN prc f ON f.oid = p.oid JOIN pg_language l ON l.oid = p.prolang
UNION ALL
SELECT 'acl', '', f.aclword || ' ' || f.ident, @ACL(coalesce(p.proacl, acldefault('f'::"char", p.proowner)); p.proowner)@, '',
       ARRAY['ACL|' || f.nsp || '|' || f.aclword || ' ' || f.ident]
  FROM pg_proc p JOIN prc f ON f.oid = p.oid
  LEFT JOIN ip ON ip.classoid = 'pg_proc'::regclass AND ip.objoid = p.oid AND ip.objsubid = 0
 WHERE coalesce(p.proacl, acldefault('f'::"char", p.proowner))
       IS DISTINCT FROM coalesce(ip.initprivs, acldefault('f'::"char", p.proowner))
UNION ALL
SELECT 'type', coalesce(r.name, re.name, ''), quote_ident(n.nspname) || '.' || quote_ident(t.typname),
       concat_ws(' ', 'type=' || t.typtype::text,
                 'base=' || CASE WHEN t.typbasetype <> 0 THEN format_type(t.typbasetype, t.typtypmod) ELSE '' END,
                 'typnotnull=' || t.typnotnull, 'default=' || coalesce(t.typdefault, ''),
                 'labels=' || coalesce((SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)
                                          FROM pg_enum e WHERE e.enumtypid = t.oid), ''),
                 'range=' || coalesce((SELECT g::text FROM pg_range g WHERE g.rngtypid = t.oid), ''),
                 'owner=' || pg_get_userbyid(t.typowner)), '',
       y.cand
  FROM pg_type t JOIN ns n ON n.oid = t.typnamespace JOIN typ y ON y.oid = t.oid
  LEFT JOIN rel r ON r.oid = t.typrelid
  LEFT JOIN pg_type et ON et.oid = t.typelem AND t.typcategory = 'A'
  LEFT JOIN rel re ON re.oid = et.typrelid
UNION ALL
SELECT 'acl', '', 'TYPE ' || quote_ident(t.typname), @ACL(coalesce(t.typacl, acldefault('T'::"char", t.typowner)); t.typowner)@, '',
       ARRAY['ACL|' || n.nspname || '|TYPE ' || quote_ident(t.typname)]
  FROM pg_type t JOIN ns n ON n.oid = t.typnamespace
  LEFT JOIN ip ON ip.classoid = 'pg_type'::regclass AND ip.objoid = t.oid AND ip.objsubid = 0
 WHERE coalesce(t.typacl, acldefault('T'::"char", t.typowner))
       IS DISTINCT FROM coalesce(ip.initprivs, acldefault('T'::"char", t.typowner))
UNION ALL
SELECT 'sequence', r.name, '',
       concat_ws(' ', format_type(s.seqtypid, NULL), s.seqstart, s.seqincrement, s.seqmax, s.seqmin,
                 s.seqcache, s.seqcycle), '', r.cand
  FROM pg_sequence s JOIN rel r ON r.oid = s.seqrelid
UNION ALL
SELECT 'owned', rt.name, quote_ident(sc.relname), coalesce(a.attname::text, '') || ' deptype=' || d.deptype::text, '',
       CASE WHEN d.deptype = 'i' THEN rs.cand ELSE ARRAY['SEQUENCE OWNED BY|' || rs.nsp || '|' || rs.relname] END
  FROM pg_depend d JOIN rel rs ON rs.oid = d.objid JOIN rel rt ON rt.oid = d.refobjid
  JOIN pg_class sc ON sc.oid = d.objid AND sc.relkind = 'S'
  LEFT JOIN pg_attribute a ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid
 WHERE d.classid = 'pg_class'::regclass AND d.refclassid = 'pg_class'::regclass AND d.deptype IN ('a', 'i')
UNION ALL
SELECT 'inherits', r.name, rp.name, s.inhseqno::text, '',
       CASE WHEN c.relispartition THEN ARRAY[CASE WHEN c.relkind IN ('i', 'I') THEN 'INDEX ATTACH'
                                                 ELSE 'TABLE ATTACH' END || '|' || r.nsp || '|' || r.relname]
            ELSE r.cand END
  FROM pg_inherits s JOIN rel r ON r.oid = s.inhrelid JOIN rel rp ON rp.oid = s.inhparent
  JOIN pg_class c ON c.oid = s.inhrelid
UNION ALL
SELECT 'statistics', r.name, quote_ident(x.stxname),
       concat_ws(' ', pg_get_statisticsobjdef(x.oid), 'target=' || coalesce(x.stxstattarget::text, '')), '',
       ARRAY['STATISTICS|' || xn.nspname || '|' || x.stxname]
  FROM pg_statistic_ext x JOIN rel r ON r.oid = x.stxrelid JOIN pg_namespace xn ON xn.oid = x.stxnamespace
UNION ALL
SELECT 'extension', '', quote_ident(x.extname),
       concat_ws(' ', x.extversion, x.extnamespace::regnamespace::text), '',
       ARRAY['EXTENSION|-|' || x.extname]
  FROM pg_extension x
UNION ALL
SELECT 'event_trigger', '', quote_ident(e.evtname),
       concat_ws(' ', e.evtevent, e.evtfoid::regproc::text, e.evtenabled::text, coalesce(e.evttags::text, ''),
                 'owner=' || pg_get_userbyid(e.evtowner)), '',
       ARRAY['EVENT TRIGGER|-|' || e.evtname]
  FROM pg_event_trigger e
 WHERE e.evtname NOT LIKE 'd2\_probe\_%'
UNION ALL
SELECT 'default_acl', '',
       concat_ws(' ', pg_get_userbyid(d.defaclrole),
                 CASE WHEN d.defaclnamespace = 0 THEN '-' ELSE d.defaclnamespace::regnamespace::text END,
                 d.defaclobjtype::text),
       d.defaclacl::text, '',
       ARRAY['DEFAULT ACL|' || coalesce(dn.nspname, '-') || '|DEFAULT PRIVILEGES FOR '
             || CASE d.defaclobjtype WHEN 'r' THEN 'TABLES' WHEN 'S' THEN 'SEQUENCES' WHEN 'f' THEN 'FUNCTIONS'
                     WHEN 'T' THEN 'TYPES' WHEN 'n' THEN 'SCHEMAS' END
             || '|' || pg_get_userbyid(d.defaclrole)]
  FROM pg_default_acl d LEFT JOIN pg_namespace dn ON dn.oid = d.defaclnamespace
UNION ALL
SELECT 'collation', '', quote_ident(n.nspname) || '.' || quote_ident(c.collname),
       concat_ws(' ', c.collprovider::text, c.collisdeterministic, coalesce(c.collcollate, ''),
                 coalesce(c.collctype, ''), coalesce(c.colliculocale, ''), coalesce(c.collicurules, ''),
                 'owner=' || pg_get_userbyid(c.collowner)), '',
       ARRAY['COLLATION|' || n.nspname || '|' || c.collname]
  FROM pg_collation c JOIN ns n ON n.oid = c.collnamespace
UNION ALL
SELECT 'conversion', '', quote_ident(n.nspname) || '.' || quote_ident(c.conname),
       concat_ws(' ', c.conforencoding, c.contoencoding, c.conproc::text, c.condefault,
                 'owner=' || pg_get_userbyid(c.conowner)), '',
       ARRAY['CONVERSION|' || n.nspname || '|' || c.conname]
  FROM pg_conversion c JOIN ns n ON n.oid = c.connamespace
UNION ALL
SELECT 'operator', '', quote_ident(n.nspname) || '.' || o.oprname || '(' || format_type(o.oprleft, NULL) || ','
       || format_type(o.oprright, NULL) || ')',
       concat_ws(' ', o.oprcode::text, o.oprrest::text, o.oprjoin::text, o.oprcom::text, o.oprnegate::text,
                 o.oprcanmerge, o.oprcanhash, 'owner=' || pg_get_userbyid(o.oprowner)), '',
       ARRAY['OPERATOR|' || n.nspname || '|' || o.oprname]
  FROM pg_operator o JOIN ns n ON n.oid = o.oprnamespace
UNION ALL
SELECT 'opfamily', '', quote_ident(n.nspname) || '.' || quote_ident(f.opfname) || ' ' || am.amname,
       concat_ws(' ', 'owner=' || pg_get_userbyid(f.opfowner),
                 (SELECT string_agg(a.amopstrategy || ':' || a.amopopr::regoperator::text, ',' ORDER BY a.amopstrategy)
                    FROM pg_amop a WHERE a.amopfamily = f.oid AND NOT EXISTS (
                         SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_amop'::regclass AND d.objid = a.oid
                            AND d.refclassid = 'pg_opclass'::regclass)),
                 (SELECT string_agg(a.amprocnum || ':' || a.amproc::text, ',' ORDER BY a.amprocnum)
                    FROM pg_amproc a WHERE a.amprocfamily = f.oid AND NOT EXISTS (
                         SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_amproc'::regclass AND d.objid = a.oid
                            AND d.refclassid = 'pg_opclass'::regclass))), '',
       ARRAY['OPERATOR FAMILY|' || n.nspname || '|' || f.opfname]
  FROM pg_opfamily f JOIN ns n ON n.oid = f.opfnamespace JOIN pg_am am ON am.oid = f.opfmethod
UNION ALL
SELECT 'opclass', '', quote_ident(n.nspname) || '.' || quote_ident(c.opcname) || ' ' || am.amname,
       concat_ws(' ', c.opcfamily::text, c.opcintype::regtype::text, c.opcdefault, c.opckeytype::text,
                 'owner=' || pg_get_userbyid(c.opcowner),
                 (SELECT string_agg(a.amopstrategy || ':' || a.amopopr::regoperator::text, ',' ORDER BY a.amopstrategy)
                    FROM pg_amop a JOIN pg_depend d ON d.classid = 'pg_amop'::regclass AND d.objid = a.oid
                   WHERE d.refclassid = 'pg_opclass'::regclass AND d.refobjid = c.oid),
                 (SELECT string_agg(a.amprocnum || ':' || a.amproc::text, ',' ORDER BY a.amprocnum)
                    FROM pg_amproc a JOIN pg_depend d ON d.classid = 'pg_amproc'::regclass AND d.objid = a.oid
                   WHERE d.refclassid = 'pg_opclass'::regclass AND d.refobjid = c.oid)), '',
       ARRAY['OPERATOR CLASS|' || n.nspname || '|' || c.opcname]
  FROM pg_opclass c JOIN ns n ON n.oid = c.opcnamespace JOIN pg_am am ON am.oid = c.opcmethod
UNION ALL
SELECT 'cast', '', format_type(c.castsource, NULL) || ' AS ' || format_type(c.casttarget, NULL),
       concat_ws(' ', c.castfunc::text, c.castcontext::text, c.castmethod::text), '',
       coalesce((SELECT y.cand FROM pg_depend d JOIN typ y ON y.oid = d.refobjid
                  WHERE d.classid = 'pg_cast'::regclass AND d.objid = c.oid AND d.deptype = 'i'
                    AND d.refclassid = 'pg_type'::regclass LIMIT 1),
                (SELECT ARRAY['EXTENSION|-|' || x.extname] FROM ext x
                  WHERE x.classid = 'pg_cast'::regclass AND x.objid = c.oid),
                ARRAY['CAST|-|CAST (' || format_type(c.castsource, NULL) || ' AS '
                      || format_type(c.casttarget, NULL) || ')'])
  FROM pg_cast c WHERE c.oid >= 16384
UNION ALL
SELECT 'ts_config', '', quote_ident(n.nspname) || '.' || quote_ident(c.cfgname),
       concat_ws(' ', c.cfgparser::text, 'owner=' || pg_get_userbyid(c.cfgowner),
                 (SELECT string_agg(m.maptokentype || ':' || m.mapseqno || ':' || m.mapdict::text, ','
                                    ORDER BY m.maptokentype, m.mapseqno)
                    FROM pg_ts_config_map m WHERE m.mapcfg = c.oid)), '',
       ARRAY['TEXT SEARCH CONFIGURATION|' || n.nspname || '|' || c.cfgname]
  FROM pg_ts_config c JOIN ns n ON n.oid = c.cfgnamespace
UNION ALL
SELECT 'ts_dict', '', quote_ident(n.nspname) || '.' || quote_ident(d.dictname),
       concat_ws(' ', d.dicttemplate::text, coalesce(d.dictinitoption, ''), 'owner=' || pg_get_userbyid(d.dictowner)),
       '', ARRAY['TEXT SEARCH DICTIONARY|' || n.nspname || '|' || d.dictname]
  FROM pg_ts_dict d JOIN ns n ON n.oid = d.dictnamespace
UNION ALL
SELECT 'ts_parser', '', quote_ident(n.nspname) || '.' || quote_ident(p.prsname),
       concat_ws(' ', p.prsstart::text, p.prstoken::text, p.prsend::text, p.prsheadline::text, p.prslextype::text),
       '', ARRAY['TEXT SEARCH PARSER|' || n.nspname || '|' || p.prsname]
  FROM pg_ts_parser p JOIN ns n ON n.oid = p.prsnamespace
UNION ALL
SELECT 'ts_template', '', quote_ident(n.nspname) || '.' || quote_ident(t.tmplname),
       concat_ws(' ', t.tmplinit::text, t.tmpllexize::text), '',
       ARRAY['TEXT SEARCH TEMPLATE|' || n.nspname || '|' || t.tmplname]
  FROM pg_ts_template t JOIN ns n ON n.oid = t.tmplnamespace
UNION ALL
SELECT 'language', '', quote_ident(l.lanname),
       concat_ws(' ', l.lanpltrusted, l.lanplcallfoid::text, l.laninline::text, l.lanvalidator::text,
                 'owner=' || pg_get_userbyid(l.lanowner), 'acl=' || coalesce(l.lanacl::text, '')), '',
       coalesce((SELECT ARRAY['EXTENSION|-|' || x.extname] FROM ext x
                  WHERE x.classid = 'pg_language'::regclass AND x.objid = l.oid),
                ARRAY['PROCEDURAL LANGUAGE|-|' || l.lanname])
  FROM pg_language l WHERE l.oid >= 16384
UNION ALL
SELECT 'fdw', '', quote_ident(w.fdwname),
       concat_ws(' ', w.fdwhandler::text, w.fdwvalidator::text, coalesce(w.fdwoptions::text, ''),
                 'owner=' || pg_get_userbyid(w.fdwowner), 'acl=' || coalesce(w.fdwacl::text, '')), '',
       ARRAY['FOREIGN DATA WRAPPER|-|' || w.fdwname]
  FROM pg_foreign_data_wrapper w
UNION ALL
SELECT 'server', '', quote_ident(s.srvname),
       concat_ws(' ', s.srvfdw::text, coalesce(s.srvtype, ''), coalesce(s.srvversion, ''),
                 coalesce(s.srvoptions::text, ''), 'owner=' || pg_get_userbyid(s.srvowner),
                 'acl=' || coalesce(s.srvacl::text, '')), '',
       ARRAY['SERVER|-|' || s.srvname]
  FROM pg_foreign_server s
UNION ALL
SELECT 'user_mapping', '', u.usename || ' ' || u.srvname, coalesce(u.umoptions::text, ''), '',
       ARRAY['USER MAPPING|-|USER MAPPING ' || CASE WHEN u.umuser = 0 THEN 'public' ELSE u.usename END
             || ' SERVER ' || u.srvname]
  FROM pg_user_mappings u
UNION ALL
SELECT 'publication', '', quote_ident(p.pubname),
       concat_ws(' ', p.puballtables, p.pubinsert, p.pubupdate, p.pubdelete, p.pubtruncate, p.pubviaroot,
                 'owner=' || pg_get_userbyid(p.pubowner)), '',
       ARRAY['PUBLICATION|-|' || p.pubname]
  FROM pg_publication p
UNION ALL
SELECT 'publication_rel', r.name, quote_ident(p.pubname),
       concat_ws(' ', coalesce(pg_get_expr(pr.prqual, pr.prrelid), ''), coalesce(pr.prattrs::text, '')), '',
       ARRAY['PUBLICATION TABLE|' || r.nsp || '|' || p.pubname || ' ' || r.relname]
  FROM pg_publication_rel pr JOIN pg_publication p ON p.oid = pr.prpubid JOIN rel r ON r.oid = pr.prrelid
UNION ALL
SELECT 'publication_ns', '', quote_ident(p.pubname) || ' ' || quote_ident(n.nspname), '', '',
       ARRAY['PUBLICATION TABLES IN SCHEMA|' || n.nspname || '|' || p.pubname || ' ' || n.nspname]
  FROM pg_publication_namespace pn JOIN pg_publication p ON p.oid = pn.pnpubid JOIN ns n ON n.oid = pn.pnnspid
UNION ALL
SELECT 'subscription', '', quote_ident(s.subname),
       concat_ws(' ', s.subenabled, coalesce(s.subslotname::text, ''), s.subpublications::text,
                 'owner=' || pg_get_userbyid(s.subowner)), '',
       ARRAY['SUBSCRIPTION|-|' || s.subname]
  FROM pg_subscription s WHERE s.subdbid = (SELECT oid FROM pg_database WHERE datname = current_database())
UNION ALL
SELECT 'access_method', '', quote_ident(a.amname), concat_ws(' ', a.amtype::text, a.amhandler::text), '',
       coalesce((SELECT ARRAY['EXTENSION|-|' || x.extname] FROM ext x
                  WHERE x.classid = 'pg_am'::regclass AND x.objid = a.oid),
                ARRAY['ACCESS METHOD|-|' || a.amname])
  FROM pg_am a WHERE a.oid >= 16384
UNION ALL
SELECT 'transform', '', format_type(t.trftype, NULL) || ' ' || l.lanname,
       concat_ws(' ', t.trffromsql::text, t.trftosql::text), '',
       ARRAY['TRANSFORM|-|TRANSFORM FOR ' || format_type(t.trftype, NULL) || ' LANGUAGE ' || l.lanname]
  FROM pg_transform t JOIN pg_language l ON l.oid = t.trflang
UNION ALL
SELECT 'comment', coalesce(r.name, ''), pg_describe_object(d.classoid, d.objoid, d.objsubid),
       md5(d.description), '',
       ARRAY['COMMENT|' || coalesce(
           CASE d.classoid
                WHEN 'pg_class'::regclass THEN r.nsp
                WHEN 'pg_proc'::regclass THEN (SELECT f.nsp FROM prc f WHERE f.oid = d.objoid)
                WHEN 'pg_type'::regclass THEN (SELECT tn.nspname FROM pg_type t JOIN pg_namespace tn
                                                  ON tn.oid = t.typnamespace WHERE t.oid = d.objoid)
                WHEN 'pg_constraint'::regclass THEN (SELECT kn.nspname FROM pg_constraint k JOIN pg_namespace kn
                                                        ON kn.oid = k.connamespace WHERE k.oid = d.objoid)
                WHEN 'pg_trigger'::regclass THEN (SELECT rr.nsp FROM pg_trigger t JOIN rel rr ON rr.oid = t.tgrelid
                                                     WHERE t.oid = d.objoid)
                WHEN 'pg_policy'::regclass THEN (SELECT rr.nsp FROM pg_policy p JOIN rel rr ON rr.oid = p.polrelid
                                                    WHERE p.oid = d.objoid)
                WHEN 'pg_rewrite'::regclass THEN (SELECT rr.nsp FROM pg_rewrite w JOIN rel rr ON rr.oid = w.ev_class
                                                     WHERE w.oid = d.objoid)
                WHEN 'pg_statistic_ext'::regclass THEN (SELECT xn.nspname FROM pg_statistic_ext x
                                                           JOIN pg_namespace xn ON xn.oid = x.stxnamespace
                                                          WHERE x.oid = d.objoid)
                WHEN 'pg_collation'::regclass THEN (SELECT cn.nspname FROM pg_collation c
                                                       JOIN pg_namespace cn ON cn.oid = c.collnamespace
                                                      WHERE c.oid = d.objoid)
                ELSE '-' END, '?') || '|' ||
       CASE d.classoid
            WHEN 'pg_class'::regclass THEN
                 CASE WHEN d.objsubid = 0 THEN r.word || ' ' || quote_ident(r.relname)
                      ELSE 'COLUMN ' || quote_ident(r.relname) || '.'
                           || quote_ident((SELECT a.attname FROM pg_attribute a
                                            WHERE a.attrelid = d.objoid AND a.attnum = d.objsubid)) END
            WHEN 'pg_proc'::regclass THEN (SELECT f.word || ' ' || f.ident FROM prc f WHERE f.oid = d.objoid)
            WHEN 'pg_type'::regclass THEN (SELECT CASE WHEN t.typtype = 'd' THEN 'DOMAIN ' ELSE 'TYPE ' END
                                                  || quote_ident(t.typname) FROM pg_type t WHERE t.oid = d.objoid)
            WHEN 'pg_namespace'::regclass THEN (SELECT 'SCHEMA ' || quote_ident(n.nspname)
                                                  FROM pg_namespace n WHERE n.oid = d.objoid)
            WHEN 'pg_constraint'::regclass THEN
                 (SELECT 'CONSTRAINT ' || quote_ident(k.conname) || ' ON '
                         || CASE WHEN k.contypid <> 0 THEN 'DOMAIN ' || quote_ident(t.typname)
                                 ELSE quote_ident(c.relname) END
                    FROM pg_constraint k LEFT JOIN pg_class c ON c.oid = k.conrelid
                    LEFT JOIN pg_type t ON t.oid = k.contypid WHERE k.oid = d.objoid)
            WHEN 'pg_trigger'::regclass THEN (SELECT 'TRIGGER ' || quote_ident(t.tgname) || ' ON '
                                                     || quote_ident(c.relname)
                                                FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
                                               WHERE t.oid = d.objoid)
            WHEN 'pg_policy'::regclass THEN (SELECT 'POLICY ' || quote_ident(p.polname) || ' ON '
                                                    || quote_ident(c.relname)
                                               FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
                                              WHERE p.oid = d.objoid)
            WHEN 'pg_rewrite'::regclass THEN (SELECT 'RULE ' || quote_ident(w.rulename) || ' ON '
                                                     || quote_ident(c.relname)
                                                FROM pg_rewrite w JOIN pg_class c ON c.oid = w.ev_class
                                               WHERE w.oid = d.objoid)
            WHEN 'pg_extension'::regclass THEN (SELECT 'EXTENSION ' || quote_ident(x.extname)
                                                  FROM pg_extension x WHERE x.oid = d.objoid)
            WHEN 'pg_event_trigger'::regclass THEN (SELECT 'EVENT TRIGGER ' || quote_ident(e.evtname)
                                                      FROM pg_event_trigger e WHERE e.oid = d.objoid)
            WHEN 'pg_statistic_ext'::regclass THEN (SELECT 'STATISTICS ' || quote_ident(x.stxname)
                                                      FROM pg_statistic_ext x WHERE x.oid = d.objoid)
            WHEN 'pg_collation'::regclass THEN (SELECT 'COLLATION ' || quote_ident(c.collname)
                                                  FROM pg_collation c WHERE c.oid = d.objoid)
            ELSE pg_describe_object(d.classoid, d.objoid, d.objsubid) END]
  FROM pg_description d
  LEFT JOIN rel r ON d.classoid = 'pg_class'::regclass AND r.oid = d.objoid
 WHERE d.objoid >= 16384
   AND NOT (d.classoid = 'pg_namespace'::regclass
            AND d.objoid IN (SELECT oid FROM pg_namespace WHERE nspname = 'd2_probe'))
   AND NOT (d.classoid = 'pg_proc'::regclass
            AND d.objoid IN (SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                              WHERE n.nspname = 'd2_probe'))
"""
CATALOG_SQL = _expand(CATALOG_SQL)

# The row kinds compared between two tables of the same shape in different
# schemas (shape()). 'default' is compared by expression (the caller
# evaluates the expressions); 'type' rows carry the schema in their ident.
SHAPE_KINDS = ("class", "attribute", "constraint", "index", "trigger", "policy",
               "rule", "comment", "statistics", "inherits", "owned", "rls", "acl", "partition")

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
    """The catalog as a frozenset of (kind, rel, ident, def, oid, cand) rows,
    read with search_path '' (as pg_dump reads) and the caller's
    search_path restored: the object rows of CATALOG_SQL and the raw rows
    of every pg_catalog relation (catalog_all.snapshot, kind 'raw')."""
    local = conn.is_in_transaction()
    old = await conn.fetchval("SELECT current_setting('search_path')")
    await conn.execute("SELECT set_config('search_path', '', $1)", local)
    try:
        rows = await conn.fetch(CATALOG_SQL)
        every = await catalog_all.snapshot(conn)
    finally:
        await conn.execute("SELECT set_config('search_path', $1, $2)", old, local)
    return frozenset(tuple(tuple(v) if isinstance(v, list) else v for v in r) for r in rows) | every


def diff(before, after):
    return {"added": sorted(after - before), "removed": sorted(before - after)}


def empty(d):
    return not d["added"] and not d["removed"]


def _noid(r):
    return tuple(r[:4]) + tuple(r[5:])


def without_oid(d):
    """d with the oid column dropped: what pg_dump can see of it."""
    add = {_noid(r) for r in d["added"]}
    rem = {_noid(r) for r in d["removed"]}
    return {"added": sorted(add - rem), "removed": sorted(rem - add)}


def oid_only(d):
    """The rows of d that differ only in their oid (a relation dropped and
    recreated with the same definition): pg_dump prints no oid."""
    add = {_noid(r) for r in d["added"]}
    rem = {_noid(r) for r in d["removed"]}
    return sorted(add & rem)


def rows_on(d, rel):
    """The rows of diff d that belong to relation rel."""
    return [r for r in d["added"] + d["removed"] if r[1] == rel]


def changers(steps, rel):
    """[label] of every (label, diff) step whose OWN diff has a row on rel."""
    return [label for label, d in steps if rows_on(d, rel)]


def touched(d):
    """The relations (and, for rows on no relation, 'kind:ident') a diff's
    OBJECT rows change, sorted. The raw rows are held to these by match()
    (catalog_all.unexplained) and seen by rows_on()/changers()."""
    return sorted({r[1] if r[1] else "%s:%s" % (r[0], r[2]) for r in d["added"] + d["removed"]
                   if r[0] != "raw"})


def changes(d):
    """(added, removed, changed) (kind, rel, ident) keys of a diff."""
    add = {r[:3] for r in d["added"]}
    rem = {r[:3] for r in d["removed"]}
    return sorted(add - rem), sorted(rem - add), sorted(add & rem)


def shape(rows, rel):
    """The (kind, ident, def) rows of rel, for comparing two relations of the
    same definition that live in different schemas."""
    return sorted((r[0], r[2], r[3]) for r in rows if r[1] == rel and r[0] in SHAPE_KINDS)


def defaults(rows, rel):
    """{column: default expression} of rel."""
    return {r[2]: r[3] for r in rows if r[1] == rel and r[0] == "default"}


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
    """pg_dump --schema-only of the database, newlines normalised, its
    session key pair removed (without_session_key)."""
    proc = subprocess.run([pg_dump, "--schema-only", "-d", dsn], capture_output=True)
    if proc.returncode:
        raise AssertionError("pg_dump failed: %s" % proc.stderr.decode("utf-8", "replace")[-500:])
    return without_session_key(proc.stdout.decode("utf-8").replace("\r\n", "\n"))


# pg_dump 16.10 and later open the script with '\restrict <key>' (after the
# header comments, before any object block) and close it with
# '\unrestrict <key>', a fresh random key per dump. The pair belongs to no
# object. Exactly that pair is removed: the restrict line in the region
# before the first object header, the unrestrict line as the dump's last
# line, both naming one key. A dump with neither is returned unchanged
# (pg_dump 16.9 and earlier).
_RESTRICT = re.compile(r"^\\restrict ([A-Za-z0-9]+)\n", re.M)
_UNRESTRICT_END = re.compile(r"\n\\unrestrict ([A-Za-z0-9]+)\n*\Z")


def without_session_key(text):
    h = _DUMP_HEADER.search(text)
    head_end = h.start() if h else len(text)
    r = list(_RESTRICT.finditer(text, 0, head_end))
    u = _UNRESTRICT_END.search(text)
    if not r and not u:
        return text
    if len(r) != 1 or not u or r[0].group(1) != u.group(1):
        raise AssertionError("unreadable pg_dump session key: restrict %s, unrestrict %s"
                             % ([m.group(1) for m in r], u.group(1) if u else None))
    return text[:r[0].start()] + text[r[0].end():u.start()] + "\n"


_DUMP_HEADER = re.compile(r"^--\n-- (Name: [^\n]*)\n--\n", re.M)
_HEADER_FIELDS = re.compile(r"^Name: (.*); Type: (.*); Schema: (.*); Owner: (.*)$")


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


def dump_object(header):
    """The pg_dump object a block header names: 'Type|Schema|Name', plus
    '|Owner' for a DEFAULT ACL (two roles' default privileges in one
    schema are two objects). The '(preamble)' is its own object."""
    if header == "(preamble)":
        return "(preamble)"
    m = _HEADER_FIELDS.match(re.sub(r"#\d+$", "", header))
    if not m:
        raise AssertionError("unreadable pg_dump header: %r" % header)
    name, typ, schema, owner = m.groups()
    key = "%s|%s|%s" % (typ, schema, name)
    return key + "|" + owner if typ == "DEFAULT ACL" else key


# Text pg_dump places between object blocks that belongs to no object: the
# session settings it emits once before the first table (they land at the
# tail of whichever block precedes that table) and the closing trailer
# (it lands at the tail of the last block).
_SESSION_LINES = re.compile(r"^(SET default_tablespace = '[^'\n]*';|SET default_table_access_method = \w+;)\n",
                            re.M)
_TRAILER = re.compile(r"--\n-- PostgreSQL database dump complete\n--\n\s*$")


def _object_text(block):
    return _SESSION_LINES.sub("", _TRAILER.sub("", block)).rstrip("\n")


def dump_objects_text(text):
    """{object: the text of its block(s)} of one dump, without the session
    settings and trailer that belong to no object."""
    out = {}
    for header, block in dump_blocks(text).items():
        key = dump_object(header)
        out[key] = out.get(key, "") + _object_text(block)
    return out


def dump_types(text):
    """The pg_dump object types of one dump."""
    return sorted({dump_object(h).split("|")[0] for h in dump_blocks(text) if h != "(preamble)"})


def dump_objects(before, after):
    """The pg_dump objects whose block text differs between two dumps (an
    object present in one only included). An object whose header changed
    only in its Owner field and whose text is the same is not changed."""
    a, b = dump_objects_text(before), dump_objects_text(after)
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def resolve(cand, present, changed=frozenset()):
    """The pg_dump object a catalog row renders in: a '~' candidate (a row
    derived from another object's rendering) when that object's block
    changed in this step; otherwise the first of its plain candidates that
    is a block of either dump, else its first plain candidate (which then
    matches nothing)."""
    for c in cand:
        if c.startswith("~") and c[1:] in changed:
            return c[1:]
    plain = [c for c in cand if not c.startswith("~")]
    for c in plain:
        if c in present:
            return c
    return plain[0] if plain else "(no candidate)"


def catalog_objects(d, present, changed=frozenset()):
    """{object: [rows]}: the pg_dump objects the changed rows of catalog
    diff d render in (rows differing only in oid are excluded: oid_only).
    The raw rows are not pg_dump objects: unexplained_raw() holds them."""
    add = {_noid(r) for r in d["added"] if r[0] != "raw"}
    rem = {_noid(r) for r in d["removed"] if r[0] != "raw"}
    out = {}
    for r in sorted(add ^ rem):
        out.setdefault(resolve(r[4], present, changed), []).append(list(r[:4]))
    return out


def unexplained_raw(d):
    """{'RAW|<catalog key>': [[side, row text, relations named]]}: the changed
    raw rows of d no object change of d accounts for (catalog_all)."""
    out = {}
    for side, key, text, refs in catalog_all.unexplained(d):
        out.setdefault("RAW|" + key, []).append([side, text, refs])
    return out


def match(d, before_dump, after_dump):
    """Compare one step's catalog diff with its pg_dump diff as object sets:
    {"catalog_only": {object: rows}, "dump_only": [object], "matched": [object]}.
    Every changed object on either side must be on the other, and every
    changed raw row must be accounted for (unexplained_raw(), returned under
    catalog_only as 'RAW|<catalog key>')."""
    present = set(dump_objects_text(before_dump)) | set(dump_objects_text(after_dump))
    dmp = set(dump_objects(before_dump, after_dump))
    cat = catalog_objects(d, present, dmp)
    return {"catalog_only": dict({k: v for k, v in cat.items() if k not in dmp}, **unexplained_raw(d)),
            "dump_only": sorted(dmp - set(cat)),
            "matched": sorted(dmp & set(cat))}
