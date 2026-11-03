"""Every pg_catalog relation of kind 'r', read whole (ruling REHEARSAL-R8-A1, E1 and E4).

The object measurement (catalog_diff.CATALOG_SQL) names the catalogs pg_dump
renders and reads them as objects. That is an ENUMERATION: whatever it does
not name (a role default in pg_db_role_setting, the enabled state of an
internal trigger) changes unseen. This module is the measurement in the
refusing direction:

  * the relations are taken at RUN TIME from pg_class (relnamespace
    pg_catalog, relkind 'r'), never from a typed list, and their number is
    asserted against FROZEN_COUNT for the server's major version, so a new
    catalog is a failure, not a silent pass;
  * every column of every one of them is read, as the row's text, except
    what EXCLUDED declares one entry at a time with its reason;
  * the shared (cluster-wide) catalogs are restricted to the rows this run
    can own (RESTRICT, each entry with its reason): other lanes create
    databases and roles on the same cluster while a run measures;
  * a column the session may not SELECT is a failure unless UNREADABLE
    declares it (with SUBSTITUTE naming the public view read instead).

snapshot(conn) returns one row per catalog row:

    ('raw', rel, key, text, '', ('RAW', own, scope, *refs))

  key   the catalog, with '/scope' where SCOPE splits it (pg_shdepend's
        database rows from its cluster rows; internal from user triggers);
  text  the row (its compared columns) as PostgreSQL prints a ROW();
  own   the row's own oid ('' for a catalog without an oid column);
  scope 'shared' for a row of a shared (cluster-wide) catalog, else 'local';
  refs  the RELATIONS the row names through any of its oid-typed columns
        (CLASS_ID_COLUMNS excepted: they name a catalog, not an object), an
        index or toast relation also named as the relation it belongs to,
        plus 'system:<catalog>' for a row describing an initdb object the
        object measurement does not render (SYSTEM_RENDERED);
  rel   one copy of the row per name in refs that is a relation ('' when
        it names none), so catalog_diff.rows_on() and changers() see it.

Rows of temporary objects are left out (TEMP_RULE).

unexplained(d) is the claim built on it (ruling R8-A1's direction rule):
every changed raw row of a step must be accounted for by a change the OBJECT
measurement shows in the same step, on one of the relations the row names,
of a kind EXPLAINS lists for the row's catalog; anything else is returned,
and catalog_diff.match() puts it beside the object set as unmatched. A
catalog whose EXPLAINS entry is empty (a role, a database, a role default,
a security label, a large object) is never accounted for: any change to it
is refused.
"""

FIRST_NORMAL_OID = 16384

# relkind 'r' relations of pg_catalog, by server major version. A server
# whose major version is not here, or whose count differs, fails the
# snapshot with a sentence: a catalog appeared or vanished and nobody has
# decided how it is measured.
FROZEN_COUNT = {16: 64}

WHOLE = None

# (relation, column or WHOLE, reason). Anything not declared is compared.
EXCLUDED = (
    ("pg_statistic", WHOLE, "planner statistics: ANALYZE and autovacuum rewrite them at any moment; "
                            "no definition is stored there"),
    ("pg_statistic_ext_data", WHOLE, "the values ANALYZE computes for extended statistics; the "
                                     "statistics objects themselves (pg_statistic_ext) are compared"),
    ("pg_largeobject", WHOLE, "large-object DATA pages; the large objects themselves "
                              "(pg_largeobject_metadata, owner and ACL) are compared"),
    ("pg_class", "relpages", "a size estimate VACUUM and ANALYZE refresh at any moment"),
    ("pg_class", "reltuples", "a row-count estimate VACUUM and ANALYZE refresh at any moment"),
    ("pg_class", "relallvisible", "a visibility-map count VACUUM refreshes at any moment"),
    ("pg_class", "relfrozenxid", "the freeze horizon VACUUM advances at any moment"),
    ("pg_class", "relminmxid", "the multixact freeze horizon VACUUM advances at any moment"),
    ("pg_class", "relhasindex", "a summary flag VACUUM clears lazily, long after the DDL; the "
                                "indexes themselves (pg_index, their pg_class rows) are compared"),
    ("pg_class", "relhasrules", "a summary flag VACUUM clears lazily; the rules (pg_rewrite) are compared"),
    ("pg_class", "relhastriggers", "a summary flag VACUUM clears lazily; the triggers (pg_trigger, "
                                   "internal ones included) are compared"),
    ("pg_class", "relhassubclass", "a summary flag ANALYZE clears lazily; the inheritance itself "
                                   "(pg_inherits) is compared"),
    ("pg_class", "relfilenode", "the storage file: TRUNCATE, CLUSTER, VACUUM FULL, REINDEX and a "
                                "sequence RESTART assign a new one without changing a definition; "
                                "every definition column of the row is compared"),
    ("pg_database", "datfrozenxid", "the database freeze horizon VACUUM advances at any moment"),
    ("pg_database", "datminmxid", "the database multixact horizon VACUUM advances at any moment"),
)

# Shared catalogs: {relation: (predicate over t, reason)}. The predicate may
# use {db} (the measured database's oid) and {me} (current_user's oid). A
# shared catalog not listed here is compared WHOLE.
RESTRICT = {
    "pg_database": ("t.oid = {db}",
                    "other lanes create and drop databases on this cluster at any moment; the measured "
                    "database's own row is compared"),
    "pg_authid": ("t.oid = {me}",
                  "other lanes create and drop roles at any moment; the session role's own row is compared"),
    "pg_auth_members": ("t.roleid = {me} OR t.member = {me}",
                        "memberships among other lanes' roles; every membership OF or IN the session "
                        "role is compared"),
    "pg_db_role_setting": ("t.setdatabase = {db} OR (t.setdatabase = 0 AND t.setrole IN (0, {me}))",
                           "other roles' settings in other databases; every setting that applies in "
                           "the measured database to anyone, and every database-independent setting of "
                           "the session role or of all roles, is compared"),
    "pg_shdepend": ("t.dbid = {db} OR (t.dbid = 0 AND ((t.classid = 'pg_catalog.pg_database'::pg_catalog.regclass "
                    "AND t.objid = {db}) OR (t.classid <> 'pg_catalog.pg_database'::pg_catalog.regclass "
                    "AND t.refclassid = 'pg_catalog.pg_authid'::pg_catalog.regclass AND t.refobjid = {me})))",
                    "dependencies of other databases' objects and of other databases (this run's own "
                    "clones are created between steps); every dependency recorded for the measured "
                    "database's objects, for the database itself, and on the session role from a "
                    "shared object, is compared"),
    "pg_shdescription": ("NOT ((t.classoid = 'pg_catalog.pg_database'::pg_catalog.regclass AND t.objoid <> {db}) "
                         "OR (t.classoid = 'pg_catalog.pg_authid'::pg_catalog.regclass AND t.objoid <> {me}))",
                         "comments on other databases and other roles; every other shared comment is compared"),
    "pg_shseclabel": ("NOT ((t.classoid = 'pg_catalog.pg_database'::pg_catalog.regclass AND t.objoid <> {db}) "
                      "OR (t.classoid = 'pg_catalog.pg_authid'::pg_catalog.regclass AND t.objoid <> {me}))",
                      "labels on other databases and other roles; every other shared label is compared"),
    "pg_subscription": ("t.subdbid = {db}",
                        "subscriptions of other databases; the measured database's are compared"),
    "pg_replication_origin": ("t.roname !~ '^pg_[0-9]+$' OR t.roname IN (SELECT 'pg_' || s.oid "
                              "FROM pg_catalog.pg_subscription s WHERE s.subdbid = {db})",
                              "the origins of other databases' subscriptions (named pg_<subscription "
                              "oid>); the origins of the measured database's subscriptions and every "
                              "origin not named that way are compared"),
}

# Columns the session may not SELECT: (relation, column or WHOLE, reason).
# Any other unreadable column fails the snapshot.
UNREADABLE = (
    ("pg_authid", WHOLE, "no SELECT for a role that is not a superuser: read through the pg_roles "
                         "view (SUBSTITUTE), which shows every column but the password"),
    ("pg_user_mapping", WHOLE, "no SELECT for a role that is not a superuser; the object measurement's "
                               "user_mapping arm reads the pg_user_mappings view"),
    ("pg_subscription", "subconninfo", "no column SELECT for a role that is not a superuser "
                                       "(connection strings)"),
)

# {relation: (view, columns the view masks)}: what an unreadable relation is
# read through.
SUBSTITUTE = {"pg_authid": ("pg_roles", ("rolpassword",))}

# Column renderings other than the value: the password hash is compared by
# its md5, never printed into a diff.
RENDER = {("pg_authid", "rolpassword"): "pg_catalog.md5(t.rolpassword)"}

# The columns that name a CATALOG in a polymorphic reference (classid with
# objid): they are not references to a relation.
CLASS_ID_COLUMNS = (("pg_depend", "classid"), ("pg_depend", "refclassid"),
                    ("pg_shdepend", "classid"), ("pg_shdepend", "refclassid"),
                    ("pg_description", "classoid"), ("pg_shdescription", "classoid"),
                    ("pg_seclabel", "classoid"), ("pg_shseclabel", "classoid"),
                    ("pg_init_privs", "classoid"))

# {relation: SQL scope expression}: one catalog read as two keys.
SCOPE = {
    "pg_shdepend": "CASE WHEN t.dbid = 0 THEN 'cluster' ELSE 'database' END",
    "pg_trigger": "CASE WHEN t.tgisinternal THEN 'internal' ELSE 'user' END",
}

# Rows with an oid below FIRST_NORMAL_OID describe initdb objects, which the
# object measurement leaves out (pg_catalog, information_schema), so a change
# to one is never accounted for: such a row names 'system:<catalog>'. These
# are the initdb objects the object measurement DOES render.
SYSTEM_RENDERED = {
    "pg_namespace": ("t.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')",
                     "the public schema is created by initdb and rendered by the namespace and acl arms"),
    "pg_extension": ("true", "plpgsql is installed by initdb and rendered by the extension arm"),
}

TEMP_RULE = ("rows of temporary objects: a row is left out when one of its oid-typed columns names a "
             "temporary schema (pg_temp_N, pg_toast_temp_N) or an object whose row names one, closed "
             "transitively. A temporary object ends with its session; the chain reads each step after "
             "its session has ended, and the object measurement leaves temporary schemas out the same "
             "way. The temporary schema rows themselves persist across sessions and are left out too.")

ALL = "*"
# The relation-level object kinds (rows of the object measurement whose rel
# is a relation).
RELATION_KINDS = frozenset(("class", "rls", "partition", "attribute", "constraint", "index", "sequence",
                            "acl"))
# {key: object kinds whose change in the same step accounts for a changed
# row of that key}; ALL: any object change in the step. A key with an empty
# set is never accounted for. 'attribute' appears where ALTER COLUMN TYPE
# rebuilds the dependent rows under new oids with the same definition.
EXPLAINS = {
    "pg_aggregate": {"proc"},
    "pg_am": {"access_method"},
    "pg_amop": {"opfamily", "opclass"},
    "pg_amproc": {"opfamily", "opclass"},
    "pg_attrdef": {"default", "attribute"},
    # atthasdef moves with a default, attinhcount with an inheritance link
    "pg_attribute": {"attribute", "class", "acl", "index", "constraint", "default", "inherits"},
    "pg_auth_members": set(),
    "pg_authid": set(),
    "pg_cast": {"cast"},
    "pg_class": RELATION_KINDS,
    "pg_collation": {"collation"},
    "pg_constraint": {"constraint", "attribute"},
    "pg_conversion": {"conversion"},
    "pg_database": set(),
    "pg_db_role_setting": set(),
    "pg_default_acl": {"default_acl"},
    "pg_depend": ALL,
    "pg_description": {"comment", "attribute"},
    "pg_enum": {"type"},
    "pg_event_trigger": {"event_trigger"},
    "pg_extension": {"extension"},
    "pg_foreign_data_wrapper": {"fdw"},
    "pg_foreign_server": {"server"},
    "pg_foreign_table": {"class"},
    "pg_index": {"index", "constraint", "attribute"},
    "pg_inherits": {"inherits", "partition"},
    "pg_init_privs": {"extension"},
    "pg_language": {"language"},
    "pg_largeobject_metadata": set(),
    "pg_namespace": {"namespace", "acl"},
    "pg_opclass": {"opclass"},
    "pg_operator": {"operator"},
    "pg_opfamily": {"opfamily", "opclass"},
    "pg_parameter_acl": set(),
    "pg_partitioned_table": {"class"},
    "pg_policy": {"policy"},
    "pg_proc": {"proc", "acl"},
    "pg_publication": {"publication"},
    "pg_publication_namespace": {"publication_ns"},
    "pg_publication_rel": {"publication_rel"},
    "pg_range": {"type"},
    "pg_replication_origin": {"subscription"},
    "pg_rewrite": {"rule", "class"},
    "pg_seclabel": set(),
    "pg_sequence": {"sequence"},
    "pg_shdepend/database": ALL,
    "pg_shdepend/cluster": {"subscription"},
    "pg_shdescription": set(),
    "pg_shseclabel": set(),
    "pg_statistic_ext": {"statistics", "attribute"},
    "pg_subscription": {"subscription"},
    "pg_subscription_rel": {"subscription"},
    "pg_tablespace": set(),
    "pg_transform": {"transform"},
    "pg_trigger/internal": {"constraint", "attribute"},
    "pg_trigger/user": {"trigger", "constraint"},
    "pg_ts_config": {"ts_config"},
    "pg_ts_config_map": {"ts_config"},
    "pg_ts_dict": {"ts_dict"},
    "pg_ts_parser": {"ts_parser"},
    "pg_ts_template": {"ts_template"},
    "pg_type": {"type", "class", "acl", "attribute"},
    "pg_user_mapping": {"user_mapping"},
}
# A row changed IN PLACE (the same own oid removed and added in one step)
# is accounted for only by these kinds where they differ from EXPLAINS: an
# internal trigger's own row changes only by ALTER CONSTRAINT (its
# deferrability) or by ENABLE/DISABLE TRIGGER, which no object renders.
EXPLAINS_IN_PLACE = {
    "pg_trigger/internal": {"constraint"},
}

COLUMNS_SQL = """
SELECT c.relname::text AS rel, c.relisshared AS shared, a.attname::text AS col,
       pg_catalog.format_type(a.atttypid, NULL) AS typ,
       pg_catalog.has_column_privilege(c.oid, a.attnum, 'SELECT') AS can
  FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
 WHERE c.relnamespace = 'pg_catalog'::pg_catalog.regnamespace AND c.relkind = 'r'
 ORDER BY c.relname, a.attnum
"""

SESSION_SQL = """
SELECT (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user) AS me,
       (SELECT oid FROM pg_catalog.pg_database WHERE datname = pg_catalog.current_database()) AS db,
       pg_catalog.current_setting('server_version_num')::int / 10000 AS major
"""

NAMES_SQL = """
SELECT c.oid, pg_catalog.quote_ident(n.nspname) || '.' || pg_catalog.quote_ident(c.relname) AS name,
       CASE WHEN c.relkind IN ('i', 'I') THEN (SELECT i.indrelid FROM pg_catalog.pg_index i
                                                WHERE i.indexrelid = c.oid)
            WHEN c.relkind = 't' THEN (SELECT o.oid FROM pg_catalog.pg_class o
                                        WHERE o.reltoastrelid = c.oid LIMIT 1) END AS parent
  FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
"""

TEMP_NS_SQL = "SELECT oid FROM pg_catalog.pg_namespace WHERE nspname ~ '^pg_(toast_)?temp_[0-9]+$'"

_OID_SCALAR = ("oid", "regproc", "regclass", "regtype", "regprocedure", "regoper", "regoperator",
               "regnamespace", "regrole", "regcollation", "regconfig", "regdictionary")
_OID_ARRAY = ("oidvector", "oid[]")


def _declared(entries, rel, col):
    return any(e[0] == rel and e[1] in (WHOLE, col) for e in entries)


def _whole(entries, rel):
    return any(e[0] == rel and e[1] is WHOLE for e in entries)


def _q(name):
    return '"%s"' % name.replace('"', '""')


def _keys(rel):
    return ["%s/%s" % (rel, s) for s in _SCOPES[rel]] if rel in _SCOPES else [rel]


# the values each SCOPE expression can take (asserted in plan()).
_SCOPES = {"pg_shdepend": ("cluster", "database"), "pg_trigger": ("internal", "user")}


def plan(meta, major, superuser=None):
    """The measurement plan from the run-time relation list `meta` (rows of
    COLUMNS_SQL): {"relations": {rel: {...}}, "problems": [sentences]}.
    Every declaration is checked against the relations that exist, so a
    declaration cannot outlive its catalog unnoticed."""
    rels = {}
    for r in meta:
        e = rels.setdefault(r["rel"], {"shared": r["shared"], "cols": []})
        e["cols"].append((r["col"], r["typ"], r["can"]))
    problems = []
    want = FROZEN_COUNT.get(major)
    if want is None:
        problems.append("server major version %s has no frozen catalog count: decide how its %d "
                        "pg_catalog relations are measured" % (major, len(rels)))
    elif len(rels) != want:
        problems.append("pg_catalog has %d relations of kind 'r' on major version %s, frozen at %d: "
                        "a catalog appeared or vanished" % (len(rels), major, want))
    cols = {(rel, c) for rel, e in rels.items() for c, _t, _k in e["cols"]}
    for name, entries in (("EXCLUDED", EXCLUDED), ("UNREADABLE", UNREADABLE)):
        for rel, col, _why in entries:
            if rel not in rels or (col is not WHOLE and (rel, col) not in cols):
                problems.append("%s names %s.%s, which this server does not have" % (name, rel, col or "*"))
    for name, table in (("RESTRICT", RESTRICT), ("SUBSTITUTE", SUBSTITUTE), ("SCOPE", SCOPE),
                        ("SYSTEM_RENDERED", SYSTEM_RENDERED)):
        for rel in table:
            if rel not in rels:
                problems.append("%s names %s, which this server does not have" % (name, rel))
    for rel, col in list(RENDER) + list(CLASS_ID_COLUMNS):
        if (rel, col) not in cols:
            problems.append("RENDER/CLASS_ID_COLUMNS name %s.%s, which this server does not have" % (rel, col))
    for rel in RESTRICT:
        if rel in rels and not rels[rel]["shared"]:
            problems.append("RESTRICT names %s, which is not a shared catalog" % rel)
    keys = set()
    for rel in rels:
        if not _whole(EXCLUDED, rel):
            keys.update(_keys(rel))
    for k in sorted(keys - set(EXPLAINS)):
        problems.append("%s has no EXPLAINS entry: decide which object changes account for it" % k)
    for k in sorted(set(EXPLAINS) - keys):
        problems.append("EXPLAINS names %s, which is not measured" % k)
    out = {}
    for rel, e in sorted(rels.items()):
        if _whole(EXCLUDED, rel):
            continue
        source, masked = rel, ()
        readable = all(k for _c, _t, k in e["cols"])
        if not readable and _whole(UNREADABLE, rel) and rel in SUBSTITUTE:
            source, masked = SUBSTITUTE[rel]
        elif not readable and _whole(UNREADABLE, rel):
            continue                      # declared unreadable as a whole, no view
        body, oids, arrays, own = [], [], [], None
        for c, typ, can in e["cols"]:
            if _declared(EXCLUDED, rel, c) or c in masked:
                continue
            if source == rel and not can:
                if _declared(UNREADABLE, rel, c):
                    continue
                problems.append("the session may not read %s.%s and no declaration names it" % (rel, c))
                continue
            body.append(RENDER.get((rel, c), "t.%s" % _q(c)) if source == rel else "t.%s" % _q(c))
            if c == "oid":
                own = "t.oid"
            if (rel, c) in CLASS_ID_COLUMNS:
                continue
            if typ in _OID_SCALAR:
                oids.append("t.%s::pg_catalog.oid" % _q(c))
            elif typ in _OID_ARRAY:
                arrays.append("coalesce(t.%s::pg_catalog.oid[], '{}')" % _q(c))
        out[rel] = {"source": source, "shared": e["shared"], "body": body, "oids": oids,
                    "arrays": arrays, "own": own, "masked": masked}
    return {"relations": out, "problems": problems, "count": len(rels)}


def query(p):
    """The one UNION ALL query reading every planned relation."""
    parts = []
    for rel, e in sorted(p["relations"].items()):
        refs = "ARRAY[%s]::pg_catalog.oid[]" % ", ".join(e["oids"]) if e["oids"] else "'{}'::pg_catalog.oid[]"
        for a in e["arrays"]:
            refs = "pg_catalog.array_cat(%s, %s)" % (refs, a)
        system = "false"
        if e["own"]:
            rendered = SYSTEM_RENDERED.get(rel, ("false",))[0]
            system = "(t.oid < %d AND NOT (%s))" % (FIRST_NORMAL_OID, rendered)
        where = ""
        if rel in RESTRICT:
            where = " WHERE " + RESTRICT[rel][0].format(db="$1", me="$2")
        parts.append("SELECT %s::text AS rel, %s::text AS scope, %s AS shared, ROW(%s)::text AS body, "
                     "%s AS own, %s AS system, %s AS refs FROM pg_catalog.%s t%s"
                     % ("'%s'" % rel, SCOPE.get(rel, "''"), "true" if e["shared"] else "false",
                        ", ".join(e["body"]),
                        e["own"] or "NULL::pg_catalog.oid", system, refs, _q(e["source"]), where))
    return "\nUNION ALL\n".join(parts)


async def read(conn):
    """(plan, rows of query(), relation names, temporary schema oids, session)."""
    s = await conn.fetchrow(SESSION_SQL)
    p = plan(await conn.fetch(COLUMNS_SQL), s["major"])
    if p["problems"]:
        raise AssertionError("catalog_all cannot measure this server: " + "; ".join(p["problems"]))
    rows = await conn.fetch(query(p), s["db"], s["me"])
    names = {r["oid"]: (r["name"], r["parent"]) for r in await conn.fetch(NAMES_SQL)}
    temp = {r["oid"] for r in await conn.fetch(TEMP_NS_SQL)}
    return p, rows, names, temp, s


def _relation_names(oid, names, depth=0):
    if oid not in names or depth > 4:
        return []
    name, parent = names[oid]
    return [name] + (_relation_names(parent, names, depth + 1) if parent else [])


def rows_from(rows, names, temp):
    """The snapshot rows (module docstring) of query() rows."""
    tempset = set(temp)
    grew = True
    while grew:
        grew = False
        for r in rows:
            own = r["own"]
            if own is not None and own not in tempset and any(o in tempset for o in r["refs"] if o):
                tempset.add(own)
                grew = True
    out = set()
    for r in rows:
        refs = [o for o in r["refs"] if o]
        if (r["own"] is not None and r["own"] in tempset) or any(o in tempset for o in refs):
            continue
        named = set()
        for o in refs:
            named.update(_relation_names(o, names))
        if r["system"]:
            named.add("system:" + r["rel"])
        key = r["rel"] + ("/" + r["scope"] if r["scope"] else "")
        cand = (("RAW", "" if r["own"] is None else str(r["own"]), "shared" if r["shared"] else "local")
                + tuple(sorted(named)))
        rels = sorted(n for n in named if not n.startswith("system:")) or [""]
        for rel in rels:
            out.add(("raw", rel, key, r["body"], "", cand))
    return out


async def snapshot(conn):
    """The raw rows of every measured catalog row (a frozenset)."""
    _p, rows, names, temp, _s = await read(conn)
    return frozenset(rows_from(rows, names, temp))


def _groups(d):
    """{(side, key, text, cand): rels} of the raw rows of diff d."""
    g = {}
    for side in ("added", "removed"):
        for r in d[side]:
            if r[0] == "raw":
                g.setdefault((side, r[2], r[3], tuple(r[5])), set()).add(r[1])
    return g


def _blank_own_oid(text, own):
    """Row text with every field equal to the row's own oid replaced by '?'
    (the row text is a ROW(...)::text, its fields comma-separated inside
    parentheses; the replacement is whole-field only)."""
    o = str(own)
    body = "," + text[1:-1] + ","
    while "," + o + "," in body:
        body = body.replace("," + o + ",", ",?,")
    return "(" + body[1:-1] + ")"


def unexplained(d):
    """The changed raw rows of diff d that no object change of the same diff
    accounts for, as sorted [side, key, text, refs] lists (module
    docstring). Three ways to be accounted for:

      * by kind: an object row of a kind EXPLAINS lists for the row's key
        changed in d, on a relation the row names (any relation when it
        names none); for a row changed IN PLACE (its own oid on both sides)
        EXPLAINS_IN_PLACE narrows the kinds;
      * by creation: a row added or removed (not in place) that names a
        relation CREATED OR DROPPED in d (its object 'class' row on one side
        only, or with another oid on the other: a relation dropped and
        recreated with the same definition, whose other object rows do not
        change);
      * by re-creation: a row added or removed (not in place) whose text,
        with its own oid blanked, is the text of a row of the same key on
        the other side with that row's own oid blanked: the same object
        dropped and created again with an identical definition, which the
        object measurement renders identically. Any other column that
        differs (an enabled state, an owner, a function) leaves the pair
        unaccounted for.
    Neither of the last two for a key whose EXPLAINS is empty.
    """
    objects = [r for r in d["added"] + d["removed"] if r[0] != "raw"]
    by_kind = {}
    for o in objects:
        by_kind.setdefault(o[0], set()).add(o[1])
    cls_add = {(o[1], o[4]) for o in d["added"] if o[0] == "class"}
    cls_rem = {(o[1], o[4]) for o in d["removed"] if o[0] == "class"}
    born_or_gone = {rel for rel, _oid in cls_add ^ cls_rem}
    g = _groups(d)
    owns = {"added": set(), "removed": set()}
    for side, key, _text, cand in g:
        if cand[1]:
            owns[side].add((key, cand[1]))
    in_place = owns["added"] & owns["removed"]
    same = {"added": set(), "removed": set()}
    for side, key, text, cand in g:
        if cand[1] and (key, cand[1]) not in in_place:
            same[side].add((key, _blank_own_oid(text, cand[1])))
    other = {"added": "removed", "removed": "added"}
    out = []
    for side, key, text, cand in sorted(g):
        refs = set(cand[3:])
        kinds = EXPLAINS.get(key, set())
        placed = bool(cand[1]) and (key, cand[1]) in in_place
        if placed:
            kinds = EXPLAINS_IN_PLACE.get(key, kinds)
        if kinds == ALL:
            ok = bool(objects)
        else:
            ok = any(k in by_kind and (not refs or refs & by_kind[k]) for k in kinds)
            if not ok and kinds and not placed:
                ok = bool(refs & born_or_gone) or (
                    bool(cand[1]) and (key, _blank_own_oid(text, cand[1])) in same[other[side]])
        if not ok:
            out.append([side, key, text, sorted(refs)])
    return out


def cluster_rows(d):
    """The changed raw rows of diff d read from a SHARED catalog, other than
    pg_shdepend's rows for the measured database's own objects."""
    out = []
    for (side, key, text, cand), _rels in sorted(_groups(d).items()):
        if cand[2] == "shared" and key != "pg_shdepend/database":
            out.append([side, key, text])
    return out


def keys(d):
    """{key: number of changed raw rows} of diff d (each row once)."""
    out = {}
    for (_side, key, _text, _cand) in _groups(d):
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))
