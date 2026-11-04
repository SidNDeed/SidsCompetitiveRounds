"""Every pg_catalog relation of kind 'r', read whole (rulings REHEARSAL-R8-A1 E1/E4, R9-A1 (A)).

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
    databases and roles on the same cluster while a run measures. The rows
    OUTSIDE a restriction are measured too, by outside(), wherever the two
    readings are taken in one REPEATABLE READ transaction (every harness
    position: only the position's own writes can differ there); the chain's
    readings are separate transactions, and routes() states for every run
    that rows outside RESTRICT are not measured there;
  * a column the session may not SELECT is a failure unless UNREADABLE
    declares it (with SUBSTITUTE naming the public view read instead); a
    column the view masks (pg_authid.rolpassword under a measurer that is
    not a superuser) is reported by routes() as unmeasured for the run.

snapshot(conn) returns one row per catalog row:

    ('raw', rel, key, text, '', ('RAW', ident, scope, *refs, *marks))

  key    the catalog, with '/scope' where SCOPE splits it (pg_shdepend's
         database rows from its cluster rows; internal from user triggers);
  text   the row (its compared columns) as PostgreSQL prints a ROW();
  ident  the row's IDENTITY: its own oid, or for a catalog without an oid
         column the columns of its unique key (PRIMARY); '' for a catalog
         without one (pg_depend, pg_shdepend);
  scope  'shared' for a row of a shared (cluster-wide) catalog, else 'local';
  refs   the RELATIONS the row names through any of its oid-typed columns
         (CLASS_ID_COLUMNS excepted: they name a catalog, not an object), an
         index or toast relation also named as the relation it belongs to,
         plus 'system:<catalog>' for a row describing an initdb object the
         object measurement does not render (SYSTEM_RENDERED);
  marks  '@<id>' for every identity the row describes (SELF: its own oid,
         '<relation>.<column>' for a column, the object a dependency names),
         in the vocabulary of the object rows' identity column (r[4] of
         catalog_diff.CATALOG_SQL); '%<relation name>' for the relation its
         identity lies in; '^<relation name>' for the table a toast
         relation's row belongs to;
  rel    one copy of the row per name in refs that is a relation ('' when
         it names none), so catalog_diff.rows_on() and changers() see it.

Rows of temporary objects are left out (TEMP_RULE).

unexplained(d) is the claim built on it (rulings R8-A1 and R9-A1 (A)):
every changed raw row of a step must be accounted for by a change the OBJECT
measurement shows in the same step OF THE OBJECT THE ROW DESCRIBES (an
object row whose identity is one of the row's '@' identities), of a kind
EXPLAINS lists for the row's catalog; a row changed IN PLACE (the same
identity on both sides) is accounted for column by column: every column
that changed must be one IN_PLACE declares for that catalog, with the kind
of object change that renders it, on that object. Anything else is
returned, and catalog_diff.match() puts it beside the object set as
unmatched. A catalog whose EXPLAINS entry is empty (a role, a database, a
role default, a security label, a large object) is never accounted for:
any change to it is refused. An object added in a step explains only its
own rows: the presence of some object change of the right kind, on the
same table or anywhere, explains nothing (round 9: an index created on
players accounted for players_pkey's pg_index.indislive changed in place).
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
# shared catalog not listed here is compared WHOLE. The rows a predicate
# leaves out are read by outside() (the complement, `(predicate) IS NOT
# TRUE`) and compared in every harness position, where both readings share
# one REPEATABLE READ snapshot and nothing but the position's own writes can
# differ; the chain's readings cannot share a snapshot (each migration
# commits, other lanes commit between them), and there they are not
# measured: routes()["outside_restrict"] says so for every run.
RESTRICT = {
    "pg_database": ("t.oid = {db}",
                    "other lanes create and drop databases on this cluster at any moment; the measured "
                    "database's own row is compared"),
    "pg_authid": ("t.oid = {me}",
                  "other lanes create and drop roles at any moment; the session role's own row is compared"),
    "pg_auth_members": ("t.roleid = {me} OR t.member = {me}",
                        "memberships among other lanes' roles; every membership OF or IN the session "
                        "role is compared"),
    # round 10 (R9-A1 (A), report catalog_all.py:99): the session role's
    # settings in EVERY database (ALTER ROLE CURRENT_USER IN DATABASE <any>
    # SET), not only in the measured one
    "pg_db_role_setting": ("t.setrole = {me} OR t.setdatabase = {db} OR (t.setdatabase = 0 AND t.setrole = 0)",
                           "other roles' settings in other databases; every setting of the session role "
                           "in any database, every setting that applies in the measured database to "
                           "anyone, and the database-independent setting of all roles, is compared"),
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
# read through. A masked column is reported by routes() as unmeasured.
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

# ---------------------------------------------------------------- identity
#
# PRIMARY: the identity of a row of a catalog without an oid column (its
# unique key). A catalog with an oid column is identified by its oid. A
# catalog listed with None has no unique key: its rows are never changed
# in place, only added or removed.
PRIMARY = {
    "pg_aggregate": ("aggfnoid",),
    "pg_attribute": ("attrelid", "attnum"),
    "pg_db_role_setting": ("setdatabase", "setrole"),
    "pg_depend": None,
    "pg_description": ("objoid", "classoid", "objsubid"),
    "pg_foreign_table": ("ftrelid",),
    "pg_index": ("indexrelid",),
    "pg_inherits": ("inhrelid", "inhseqno"),
    "pg_init_privs": ("objoid", "classoid", "objsubid"),
    "pg_partitioned_table": ("partrelid",),
    "pg_range": ("rngtypid",),
    "pg_replication_origin": ("roident",),
    "pg_seclabel": ("objoid", "classoid", "objsubid", "provider"),
    "pg_sequence": ("seqrelid",),
    "pg_shdepend": None,
    "pg_shdescription": ("objoid", "classoid"),
    "pg_shseclabel": ("objoid", "classoid", "provider"),
    "pg_subscription_rel": ("srrelid", "srsubid"),
    "pg_ts_config_map": ("mapcfg", "maptokentype", "mapseqno"),
}
# The PRIMARY keys written as '<oid>.<number>' (the object rows' column and
# inheritance-link identity); every other multi-column key is ':'-joined.
PRIMARY_SUB = ("pg_attribute", "pg_inherits")

# SELF: {relation: forms}: besides the row's own oid, the identities of the
# objects the row describes, each form (oid column,) or (oid column, sub
# column) written '<oid>' or '<oid>.<sub>' (sub 0 omitted), a zero oid
# naming nothing. These are what an explaining object row's identity must
# equal.
SELF = {
    "pg_aggregate": (("aggfnoid",),),
    "pg_amop": (("amopfamily",),),
    "pg_amproc": (("amprocfamily",),),
    "pg_attrdef": (("adrelid", "adnum"),),
    "pg_attribute": (("attrelid", "attnum"),),
    # a dependency is recorded, changed and removed with its DEPENDENT object
    "pg_depend": (("objid", "objsubid"),),
    "pg_description": (("objoid", "objsubid"),),
    "pg_enum": (("enumtypid",),),
    "pg_foreign_table": (("ftrelid",),),
    "pg_index": (("indexrelid",),),
    "pg_inherits": (("inhrelid", "inhseqno"),),
    "pg_init_privs": (("objoid", "objsubid"),),
    "pg_partitioned_table": (("partrelid",),),
    "pg_range": (("rngtypid",),),
    "pg_seclabel": (("objoid", "objsubid"),),
    "pg_sequence": (("seqrelid",),),
    "pg_shdepend": (("objid", "objsubid"),),
    "pg_shdescription": (("objoid",),),
    "pg_shseclabel": (("objoid",),),
    "pg_subscription_rel": (("srsubid",),),
    "pg_trigger": (("tgconstraint",),),
    "pg_ts_config_map": (("mapcfg",),),
    "pg_type": (("typrelid",),),
}

# {relation: extra SQL identity expressions} beside SELF (conditional forms).
SELF_SQL = {
    "pg_attribute": ("CASE WHEN t.attnum < 0 THEN t.attrelid::pg_catalog.oid::text END",),
    # a subscription's origin is named pg_<subscription oid>
    "pg_replication_origin": ("CASE WHEN t.roname ~ '^pg_[0-9]+$' THEN pg_catalog.substr(t.roname, 4) END",),
}

ALL = "*"
# A dependency-like catalog: its row records a fact ABOUT the objects it
# names (a dependency, an initial privilege) and changes with them. Such a
# row is accounted for by a change of one of the objects it names: an
# object row whose identity it carries, or a changed raw row whose identity
# it carries (that row is held to its own explanation in turn).
DEPENDS = "<the objects it names>"
# The relation-level object kinds (rows of the object measurement whose rel
# is a relation).
RELATION_KINDS = frozenset(("class", "rls", "partition", "attribute", "constraint", "index", "sequence",
                            "acl"))
# {key: object kinds whose change OF THE OBJECT THE ROW DESCRIBES, in the
# same step, accounts for a row of that key added or removed whole}. A key
# with an empty set is never accounted for.
EXPLAINS = {
    "pg_aggregate": {"proc"},
    "pg_am": {"access_method"},
    "pg_amop": {"opfamily", "opclass"},
    "pg_amproc": {"opfamily", "opclass"},
    # ALTER COLUMN TYPE rebuilds a column's default (a new row, a new stored
    # tree) whose rendered text can stay the same: bound to that column's
    # attribute (adrelid.adnum), the object whose change rebuilt it
    "pg_attrdef": {"default", "attribute"},
    # a system column (attnum < 0) is created and dropped with its relation and
    # rendered by no object row: it alone carries the relation's identity
    # (SELF_SQL), so only it can be bound to the class row
    "pg_attribute": {"attribute", "class"},
    "pg_auth_members": set(),
    "pg_authid": set(),
    "pg_cast": {"cast"},
    "pg_class": RELATION_KINDS,
    "pg_collation": {"collation"},
    "pg_constraint": {"constraint"},
    "pg_conversion": {"conversion"},
    "pg_database": set(),
    "pg_db_role_setting": set(),
    "pg_default_acl": {"default_acl"},
    "pg_depend": DEPENDS,
    "pg_description": {"comment"},
    "pg_enum": {"type"},
    "pg_event_trigger": {"event_trigger"},
    "pg_extension": {"extension"},
    "pg_foreign_data_wrapper": {"fdw"},
    "pg_foreign_server": {"server"},
    "pg_foreign_table": {"class"},
    "pg_index": {"index"},
    "pg_inherits": {"inherits"},
    "pg_init_privs": DEPENDS,
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
    "pg_rewrite": {"rule"},
    "pg_seclabel": set(),
    "pg_sequence": {"sequence"},
    "pg_shdepend/database": DEPENDS,
    "pg_shdepend/cluster": {"subscription"},
    "pg_shdescription": set(),
    "pg_shseclabel": set(),
    "pg_statistic_ext": {"statistics"},
    "pg_subscription": {"subscription"},
    "pg_subscription_rel": {"subscription"},
    "pg_tablespace": set(),
    "pg_transform": {"transform"},
    "pg_trigger/internal": {"constraint"},
    "pg_trigger/user": {"trigger", "constraint"},
    "pg_ts_config": {"ts_config"},
    "pg_ts_config_map": {"ts_config"},
    "pg_ts_dict": {"ts_dict"},
    "pg_ts_parser": {"ts_parser"},
    "pg_ts_template": {"ts_template"},
    "pg_type": {"type", "class", "acl"},
    "pg_user_mapping": {"user_mapping"},
}

# A toast relation (and its index) is rendered by no object row; its rows
# are created and dropped with the table's toastable columns. A row whose
# identity lies in a toast relation is accounted for by a change of one of
# these kinds on the table the toast relation belongs to ('^' mark).
TOAST_KINDS = ("attribute", "class")

S, R, O = "self", "rel", "owner"   # binding modes: the object row's
#                        identity is one of the row's '@' identities (S); or
#                        the object row's relation is the relation the row's
#                        identity is in ('%' mark; R); or the object row's
#                        relation is a relation the row names through its
#                        oid-typed columns, an index's or toast relation's
#                        owning table included (O)
_CLASS = (("class", S),)
# {key: {column: ((object kind, mode), ...)}}: the columns whose change IN
# PLACE an object change accounts for, and how that change must be bound. A
# column not listed (and every column of a key not listed) is accounted for
# by nothing: changed in place, the row is unexplained (refuse by default).
IN_PLACE = {
    "pg_class": dict(
        {c: _CLASS for c in ("relname", "relnamespace", "relkind", "relpersistence", "relforcerowsecurity",
                             "reloptions", "relreplident", "relam", "reltablespace", "reloftype")},
        # ALTER TABLE OWNER changes the owner of the table's indexes and toast
        # relation too; pg_dump renders only the table's
        relowner=(("class", S), ("class", O)),
        relrowsecurity=(("rls", S),), relispartition=(("partition", S),), relpartbound=(("partition", S),),
        # an owner change rewrites the grantor of every grant on the relation,
        # which no ACL object renders: bound to the relation's own class object
        relacl=(("acl", S), ("class", S)),
        # a column added or dropped changes the table's column count, and a
        # toastable one creates its toast relation
        relnatts=(("attribute", R),), reltoastrelid=(("attribute", R),),
        relchecks=(("constraint", R),)),
    "pg_attribute": dict(
        {c: (("attribute", S),) for c in ("attname", "atttypid", "attlen", "atttypmod", "attndims", "attbyval",
                                          "attalign", "attstorage", "attcompression", "attnotnull", "attidentity",
                                          "attgenerated", "attisdropped", "attstattarget", "attcollation",
                                          "attoptions", "attfdwoptions")},
        atthasdef=(("default", S), ("attribute", S)),
        # the stored value of a column added with a default: set with the
        # column, cleared when the table is rewritten by another column's change
        atthasmissing=(("default", S), ("attribute", S), ("attribute", R)),
        attmissingval=(("default", S), ("attribute", S), ("attribute", R)),
        # an owner change rewrites the grantor of every column grant: bound to
        # the class object of the relation the column is in
        attacl=(("acl", S), ("class", R)), attinhcount=(("inherits", R),), attislocal=(("inherits", R),)),
    "pg_attrdef": {"adbin": (("default", S),)},
    "pg_constraint": dict(
        {c: (("constraint", S),) for c in ("conname", "contype", "condeferrable", "condeferred", "convalidated",
                                           "confrelid", "confupdtype", "confdeltype", "confmatchtype",
                                           "connoinherit", "conkey", "confkey", "confdelsetcols", "conexclop",
                                           "conbin")},
        conislocal=(("inherits", R),), coninhcount=(("inherits", R),)),
    "pg_trigger/user": {c: (("trigger", S), ("constraint", S)) for c in (
        "tgname", "tgfoid", "tgtype", "tgenabled", "tgconstrrelid", "tgdeferrable", "tginitdeferred",
        "tgnargs", "tgattr", "tgargs", "tgqual", "tgoldtable", "tgnewtable")},
    # an internal trigger's own row changes only by ALTER CONSTRAINT (its
    # deferrability); its enabled state is rendered by no object
    "pg_trigger/internal": {"tgdeferrable": (("constraint", S),), "tginitdeferred": (("constraint", S),)},
    # indcheckxmin, indisready, indislive, indimmediate are rendered by no object
    "pg_index": {c: (("index", S),) for c in (
        "indnatts", "indnkeyatts", "indisunique", "indnullsnotdistinct", "indisprimary", "indisexclusion",
        "indisclustered", "indisvalid", "indisreplident", "indkey", "indcollation", "indclass", "indoption",
        "indexprs", "indpred")},
    "pg_proc": dict({c: (("proc", S),) for c in (
        "proname", "pronamespace", "proowner", "prolang", "procost", "prorows", "provariadic", "prosupport",
        "prokind", "prosecdef", "proleakproof", "proisstrict", "proretset", "provolatile", "proparallel",
        "pronargs", "pronargdefaults", "prorettype", "proargtypes", "proallargtypes", "proargmodes",
        "proargnames", "proargdefaults", "protrftypes", "prosrc", "probin", "prosqlbody", "proconfig")},
        proacl=(("acl", S),)),
    "pg_aggregate": {c: (("proc", S),) for c in (
        "aggkind", "aggnumdirectargs", "aggtransfn", "aggfinalfn", "aggcombinefn", "aggserialfn",
        "aggdeserialfn", "aggmtransfn", "aggminvtransfn", "aggmfinalfn", "aggfinalextra", "aggmfinalextra",
        "aggfinalmodify", "aggmfinalmodify", "aggsortop", "aggtranstype", "aggtransspace", "aggmtranstype",
        "aggmtransspace", "agginitval", "aggminitval")},
    "pg_type": dict({c: (("type", S),) for c in (
        "typname", "typnamespace", "typowner", "typtype", "typnotnull", "typbasetype", "typtypmod",
        "typdefault", "typdefaultbin")}, typacl=(("acl", S),)),
    "pg_namespace": {"nspname": (("namespace", S),), "nspowner": (("namespace", S),), "nspacl": (("acl", S),)},
    "pg_rewrite": {c: (("rule", S),) for c in ("rulename", "ev_type", "ev_enabled", "is_instead", "ev_qual",
                                                "ev_action")},
    "pg_policy": {c: (("policy", S),) for c in ("polname", "polcmd", "polpermissive", "polroles", "polqual",
                                                 "polwithcheck")},
    "pg_statistic_ext": {c: (("statistics", S),) for c in ("stxname", "stxnamespace", "stxstattarget", "stxkeys",
                                                            "stxkind", "stxexprs")},
    "pg_extension": {c: (("extension", S),) for c in ("extname", "extversion", "extnamespace")},
    "pg_sequence": {c: (("sequence", S),) for c in ("seqtypid", "seqstart", "seqincrement", "seqmax", "seqmin",
                                                     "seqcache", "seqcycle")},
    "pg_description": {"description": (("comment", S),)},
    "pg_inherits": {"inhparent": (("inherits", S),)},
    "pg_enum": {"enumlabel": (("type", S),), "enumsortorder": (("type", S),)},
    "pg_range": {c: (("type", S),) for c in ("rngsubtype", "rngmultitypid", "rngcollation", "rngsubopc",
                                             "rngcanonical", "rngsubdiff")},
    "pg_event_trigger": {c: (("event_trigger", S),) for c in ("evtname", "evtevent", "evtowner", "evtfoid",
                                                               "evtenabled", "evttags")},
    "pg_default_acl": {"defaclacl": (("default_acl", S),)},
    "pg_language": {c: (("language", S),) for c in ("lanname", "lanowner", "lanpltrusted", "lanplcallfoid",
                                                     "laninline", "lanvalidator", "lanacl")},
    "pg_cast": {c: (("cast", S),) for c in ("castfunc", "castcontext", "castmethod")},
    "pg_operator": {c: (("operator", S),) for c in ("oprname", "oprowner", "oprcode", "oprrest", "oprjoin",
                                                     "oprcom", "oprnegate", "oprcanmerge", "oprcanhash")},
    "pg_collation": {c: (("collation", S),) for c in ("collname", "collowner", "collprovider",
                                                       "collisdeterministic", "collcollate", "collctype",
                                                       "colliculocale", "collicurules")},
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
       pg_catalog.current_setting('server_version_num')::int / 10000 AS major,
       (SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname = current_user) AS superuser,
       current_user::text AS measurer
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

ISOLATION_SQL = "SELECT pg_catalog.current_setting('transaction_isolation')"

_OID_SCALAR = ("oid", "regproc", "regclass", "regtype", "regprocedure", "regoper", "regoperator",
               "regnamespace", "regrole", "regcollation", "regconfig", "regdictionary")
_OID_ARRAY = ("oidvector", "oid[]")

# {relation: [compared column names, in the order of the row text]} of the
# last plan read (read()); unexplained() takes the changed columns of a row
# changed in place from it, and refuses a row whose columns it does not know.
BODY_COLUMNS = {}


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


def _ref_sql(form):
    """SQL text of one SELF form: '<oid>' or '<oid>.<sub>' (sub 0 omitted);
    NULL when the oid is 0."""
    oid = "t.%s::pg_catalog.oid" % _q(form[0])
    if len(form) == 1:
        return "NULLIF(%s::text, '0')" % oid
    sub = "t.%s" % _q(form[1])
    return ("CASE WHEN %s = 0 THEN NULL WHEN %s <> 0 THEN %s::text || '.' || %s::text ELSE %s::text END"
            % (oid, sub, oid, sub, oid))


def _primary_sql(rel, cols):
    if "oid" in cols:
        return "t.oid::text"
    key = PRIMARY.get(rel)
    if not key:
        return "''::text"
    if rel in PRIMARY_SUB or len(key) == 1:
        return _ref_sql(key) if rel in PRIMARY_SUB else "t.%s::pg_catalog.oid::text" % _q(key[0])
    return "pg_catalog.concat_ws(':', %s)" % ", ".join("t.%s::text" % _q(c) for c in key)


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
                        ("SYSTEM_RENDERED", SYSTEM_RENDERED), ("PRIMARY", PRIMARY), ("SELF", SELF),
                        ("SELF_SQL", SELF_SQL)):
        for rel in table:
            if rel not in rels:
                problems.append("%s names %s, which this server does not have" % (name, rel))
    for rel, col in list(RENDER) + list(CLASS_ID_COLUMNS):
        if (rel, col) not in cols:
            problems.append("RENDER/CLASS_ID_COLUMNS name %s.%s, which this server does not have" % (rel, col))
    for rel, forms in list(SELF.items()) + [(r, (k,)) for r, k in PRIMARY.items() if k]:
        for form in forms:
            for c in form:
                if rel in rels and (rel, c) not in cols:
                    problems.append("PRIMARY/SELF name %s.%s, which this server does not have" % (rel, c))
    for rel in rels:
        if not _whole(EXCLUDED, rel) and not any(c == "oid" for c, _t, _k in rels[rel]["cols"]) \
                and rel not in PRIMARY:
            problems.append("%s has no oid column and no PRIMARY entry: decide what identifies its rows" % rel)
    for key, decl in IN_PLACE.items():
        rel = key.split("/")[0]
        for c in decl:
            if (rel, c) not in cols:
                problems.append("IN_PLACE names %s.%s, which this server does not have" % (rel, c))
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
    for k in sorted(set(IN_PLACE) - keys):
        problems.append("IN_PLACE names %s, which is not measured" % k)
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
        body, names, oids, arrays, own = [], [], [], [], None
        for c, typ, can in e["cols"]:
            if _declared(EXCLUDED, rel, c) or c in masked:
                continue
            if source == rel and not can:
                if _declared(UNREADABLE, rel, c):
                    continue
                problems.append("the session may not read %s.%s and no declaration names it" % (rel, c))
                continue
            body.append(RENDER.get((rel, c), "t.%s" % _q(c)) if source == rel else "t.%s" % _q(c))
            names.append(c)
            if c == "oid":
                own = "t.oid"
            if (rel, c) in CLASS_ID_COLUMNS:
                continue
            if typ in _OID_SCALAR:
                oids.append("t.%s::pg_catalog.oid" % _q(c))
            elif typ in _OID_ARRAY:
                arrays.append("coalesce(t.%s::pg_catalog.oid[], '{}')" % _q(c))
        all_cols = [c for c, _t, _k in e["cols"]]
        selves = [_ref_sql(f) for f in SELF.get(rel, ())] + list(SELF_SQL.get(rel, ()))
        out[rel] = {"source": source, "shared": e["shared"], "body": body, "names": names, "oids": oids,
                    "arrays": arrays, "own": own, "masked": masked,
                    "ident": _primary_sql(rel, all_cols),
                    "selves": "ARRAY[%s]::text[]" % ", ".join(selves) if selves else "'{}'::text[]"}
    return {"relations": out, "problems": problems, "count": len(rels)}


def query(p, outside=False):
    """The one UNION ALL query reading every planned relation; with
    `outside`, the rows of the RESTRICT relations their predicate leaves out
    (and nothing else)."""
    parts = []
    for rel, e in sorted(p["relations"].items()):
        if outside and rel not in RESTRICT:
            continue
        refs = "ARRAY[%s]::pg_catalog.oid[]" % ", ".join(e["oids"]) if e["oids"] else "'{}'::pg_catalog.oid[]"
        for a in e["arrays"]:
            refs = "pg_catalog.array_cat(%s, %s)" % (refs, a)
        system = "false"
        if e["own"]:
            rendered = SYSTEM_RENDERED.get(rel, ("false",))[0]
            system = "(t.oid < %d AND NOT (%s))" % (FIRST_NORMAL_OID, rendered)
        where = ""
        if rel in RESTRICT:
            pred = RESTRICT[rel][0].format(db="$1", me="$2")
            where = (" WHERE (%s) IS NOT TRUE" % pred) if outside else (" WHERE " + pred)
        parts.append("SELECT %s::text AS rel, %s::text AS scope, %s AS shared, ROW(%s)::text AS body, "
                     "%s AS own, %s AS system, %s AS refs, %s AS ident, %s AS selves FROM pg_catalog.%s t%s"
                     % ("'%s'" % rel, SCOPE.get(rel, "''"), "true" if e["shared"] else "false",
                        ", ".join(e["body"]),
                        e["own"] or "NULL::pg_catalog.oid", system, refs, e["ident"], e["selves"],
                        _q(e["source"]), where))
    return "\nUNION ALL\n".join(parts)


async def read(conn, outside=False):
    """(plan, rows of query(), relation names, temporary schema oids, session)."""
    s = await conn.fetchrow(SESSION_SQL)
    p = plan(await conn.fetch(COLUMNS_SQL), s["major"])
    if p["problems"]:
        raise AssertionError("catalog_all cannot measure this server: " + "; ".join(p["problems"]))
    BODY_COLUMNS.update({rel: list(e["names"]) for rel, e in p["relations"].items()})
    rows = await conn.fetch(query(p, outside), s["db"], s["me"])
    names = {r["oid"]: (r["name"], r["parent"]) for r in await conn.fetch(NAMES_SQL)}
    temp = {r["oid"] for r in await conn.fetch(TEMP_NS_SQL)}
    return p, rows, names, temp, s


def _relation_names(oid, names, depth=0):
    if oid not in names or depth > 4:
        return []
    name, parent = names[oid]
    return [name] + (_relation_names(parent, names, depth + 1) if parent else [])


def _toast_owner(oid, names):
    """The table a toast relation (or a toast relation's index) belongs to,
    or None for any other relation."""
    chain = _relation_names(oid, names)
    if not chain or not chain[0].startswith("pg_toast."):
        return None
    rest = [n for n in chain if not n.startswith("pg_toast.")]
    return rest[0] if rest else None


def _lead_oid(ident):
    head = ident.split(".", 1)[0].split(":", 1)[0]
    return int(head) if head.isdigit() else None


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
        ident = r["ident"] or ""
        ids = {x for x in (r["selves"] or []) if x}
        if r["own"] is not None:
            ids.add(str(r["own"]))
        marks = ["@" + i for i in sorted(ids)]
        lead = _lead_oid(ident) if r["rel"] not in ("pg_description", "pg_init_privs", "pg_seclabel",
                                                     "pg_shdescription", "pg_shseclabel",
                                                     "pg_db_role_setting", "pg_ts_config_map",
                                                     "pg_subscription_rel", "pg_replication_origin") else None
        if lead is not None and lead in names:
            marks.append("%" + names[lead][0])
            owner = _toast_owner(lead, names)
            if owner:
                marks.append("^" + owner)
        cand = (("RAW", ident, "shared" if r["shared"] else "local") + tuple(sorted(named)) + tuple(marks))
        rels = sorted(n for n in named if not n.startswith("system:")) or [""]
        for rel in rels:
            out.add(("raw", rel, key, r["body"], "", cand))
    return out


async def snapshot(conn):
    """The raw rows of every measured catalog row (a frozenset)."""
    _p, rows, names, temp, _s = await read(conn)
    return frozenset(rows_from(rows, names, temp))


async def outside(conn):
    """The raw rows of the shared catalogs that RESTRICT leaves out (a
    frozenset), for a harness position: read only inside a REPEATABLE READ
    (or SERIALIZABLE) transaction, where two readings share one snapshot
    and differ only by the position's own writes. The caller binds the two
    readings to the same transaction (catalog_position); this refuses a
    reading at any other isolation (each statement would see other lanes'
    commits)."""
    iso = await conn.fetchval(ISOLATION_SQL)
    if iso not in ("repeatable read", "serializable"):
        raise AssertionError("catalog_all.outside() reads the rows outside RESTRICT only inside one "
                             "REPEATABLE READ transaction; this reading is at %r" % iso)
    _p, rows, names, temp, _s = await read(conn, outside=True)
    return frozenset(rows_from(rows, names, temp))


async def routes(conn):
    """What this run's measurer measures, by field (ruling R9-A1 (A)):
    {"measurer", "superuser", "rolpassword", "outside_restrict", "unmeasured"}.
    rolpassword: 'digest' when the measurer reads pg_authid (a superuser: the
    stored value compared as its md5), else 'unmeasured' (pg_roles masks
    it); outside_restrict: how the shared rows RESTRICT leaves out are
    measured. 'unmeasured' lists (relation, column, reason) for the run."""
    s = await conn.fetchrow(SESSION_SQL)
    p = plan(await conn.fetch(COLUMNS_SQL), s["major"])
    unmeasured = []
    for rel, e in sorted(p["relations"].items()):
        for c in e["masked"]:
            unmeasured.append((rel, c, "read through %s, which masks it; the measurer %s may not read %s"
                               % (e["source"], s["measurer"], rel)))
    pw = p["relations"].get("pg_authid", {})
    return {"measurer": s["measurer"], "superuser": bool(s["superuser"]),
            "rolpassword": "unmeasured" if "rolpassword" in pw.get("masked", ()) else "digest",
            "outside_restrict": ("measured in every harness position (outside(), one REPEATABLE READ "
                                 "snapshot at both ends of the position); not measured between two chain "
                                 "readings, which are separate transactions"),
            "unmeasured": unmeasured}


def _groups(d):
    """{(side, key, text, cand): rels} of the raw rows of diff d."""
    g = {}
    for side in ("added", "removed"):
        for r in d[side]:
            if r[0] == "raw":
                g.setdefault((side, r[2], r[3], tuple(r[5])), set()).add(r[1])
    return g


def _marks(cand):
    """(refs, '@' identities, '%' relations, '^' toast owners) of a raw row's cand."""
    refs, ids, rels, toast = set(), set(), set(), set()
    for c in cand[3:]:
        if c[:1] == "@":
            ids.add(c[1:])
        elif c[:1] == "%":
            rels.add(c[1:])
        elif c[:1] == "^":
            toast.add(c[1:])
        else:
            refs.add(c)
    return refs, ids, rels, toast


def _blank_own_oid(text, own):
    """Row text with every field equal to the row's own oid replaced by '?'
    (the row text is a ROW(...)::text, its fields comma-separated inside
    parentheses; the replacement is whole-field only)."""
    o = str(own)
    body = "," + text[1:-1] + ","
    while "," + o + "," in body:
        body = body.replace("," + o + ",", ",?,")
    return "(" + body[1:-1] + ")"


def fields(text):
    """The fields of a ROW(...)::text (record_out: comma-separated, a field
    quoted with '"' when it holds a special character, '""' and a doubled
    backslash inside quotes; an empty unquoted field is NULL)."""
    s, out, i = text[1:-1], [], 0
    n = len(s)
    while True:
        if i < n and s[i] == '"':
            i += 1
            buf = []
            while i < n:
                c = s[i]
                if c == '"':
                    if i + 1 < n and s[i + 1] == '"':
                        buf.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                if c == chr(92) and i + 1 < n:
                    buf.append(s[i + 1])
                    i += 2
                    continue
                buf.append(c)
                i += 1
            out.append("".join(buf))
        else:
            j = s.find(",", i)
            j = n if j < 0 else j
            out.append(s[i:j] if j > i else None)
            i = j
        if i >= n:
            break
        i += 1
    return out


def changed_columns(key, a_text, b_text):
    """The names of the columns two row texts of catalog key differ in, or
    None when the columns of the key are not known or a text does not split
    into them."""
    cols = BODY_COLUMNS.get(key.split("/")[0])
    if cols is None:
        return None
    fa, fb = fields(a_text), fields(b_text)
    if len(fa) != len(cols) or len(fb) != len(cols):
        return None
    return [c for c, x, y in zip(cols, fa, fb) if x != y]


def unexplained(d):
    """The changed raw rows of diff d that no object change of the same diff
    accounts for, as sorted [side, key, text, refs] lists (module
    docstring). A row is accounted for:

      * changed IN PLACE (its identity on both sides): when it changed in
        at least one column, every changed column is one IN_PLACE lists for
        its key, and for each an object row of a listed kind changed in d
        bound as listed (S: its identity is one of the row's '@'
        identities; R: its relation is the relation the row's identity lies
        in); when no column changed, only the relation names it carries
        differ, and they are exactly names a renamed relation's class row
        changed between;
      * added or removed whole, of a DEPENDS key: an object row changed in
        d, or a raw row changed in d, whose identity the row carries;
      * added or removed whole, of any other key: an object row of a kind
        EXPLAINS lists changed in d whose identity is one of the row's '@'
        identities; or, for a row of a toast relation, an object row of a
        TOAST_KINDS kind changed on the table it belongs to; or (the same
        object dropped and created again with an identical definition) its
        text, with its own oid blanked, is the text of a row of the same key
        on the other side with that row's own oid blanked.
    """
    objects = [r for r in d["added"] + d["removed"] if r[0] != "raw"]
    ids_of, rels_of = {}, {}
    for o in objects:
        ids_of.setdefault(o[0], set()).add(o[4])
        rels_of.setdefault(o[0], set()).add(o[1])
    every_id = set()
    for v in ids_of.values():
        every_id |= v
    cls = {"added": {}, "removed": {}}
    for side in ("added", "removed"):
        for o in d[side]:
            if o[0] == "class":
                cls[side].setdefault(o[4], set()).add(o[1])
    renamed = set()
    for oid in set(cls["added"]) & set(cls["removed"]):
        if cls["added"][oid] != cls["removed"][oid]:
            renamed |= cls["added"][oid] | cls["removed"][oid]
    g = _groups(d)
    marks = {k: _marks(k[3]) for k in g}
    by_ident = {"added": {}, "removed": {}}
    for k in g:
        if k[3][1]:
            by_ident[k[0]].setdefault((k[1], k[3][1]), []).append(k)
    in_place = set(by_ident["added"]) & set(by_ident["removed"])
    raw_ids = {k[3][1] for k in g if k[3][1] and ":" not in k[3][1] and EXPLAINS.get(k[1]) != DEPENDS}
    same = {"added": set(), "removed": set()}
    for side, key, text, cand in g:
        if cand[1] and (key, cand[1]) not in in_place:
            same[side].add((key, _blank_own_oid(text, cand[1])))
    other = {"added": "removed", "removed": "added"}

    def bound(kind, mode, ids, rels, refs):
        if mode == S:
            return bool(ids & ids_of.get(kind, set()))
        return bool((rels if mode == R else refs) & rels_of.get(kind, set()))

    def in_place_ok(key, ident):
        decl = IN_PLACE.get(key, {})
        for a in by_ident["added"][(key, ident)]:
            for b in by_ident["removed"][(key, ident)]:
                ra, ia, la, ta = marks[a]
                rb, ib, lb, tb = marks[b]
                ids, rels, named = ia | ib, la | lb, ra | rb
                changed = changed_columns(key, a[2], b[2])
                if changed is None:
                    return False
                if not changed:
                    names = (ra ^ rb) | (la ^ lb) | (ta ^ tb)
                    if not names or not names <= renamed:
                        return False
                    continue
                for c in changed:
                    if not any(bound(kind, mode, ids, rels, named) for kind, mode in decl.get(c, ())):
                        return False
        return True

    # a dependency row changed in d links its dependent object (objid) to the
    # object it depends on (refobjid): a whole row whose identity is a
    # dependent there is bound to that object (the operators and support
    # functions CREATE OPERATOR CLASS makes depend on the class)
    linked = {"added": {}, "removed": {}}
    for side in linked:
        for r in d[side]:
            if r[0] == "raw" and r[2] == "pg_depend":
                f = fields(r[3])
                if len(f) == 7 and f[1] and f[4]:
                    linked[side].setdefault(f[1], set()).add(f[4])
    # an inheritance link (relid.seqno) is a part of its relation: it explains
    # the relation's own dependency rows (ALTER TABLE INHERIT)
    inherits_of = {i.split(".", 1)[0] for i in ids_of.get("inherits", set())}
    # rows with no key identity whose text is the same on both sides
    by_text = {"added": {}, "removed": {}}
    for k in g:
        by_text[k[0]].setdefault((k[1], k[2]), []).append(k)

    verdict = {}
    out = []
    for k in sorted(g):
        side, key, text, cand = k
        refs, ids, _rels, toast = marks[k]
        kinds = EXPLAINS.get(key, set())
        if cand[1] and (key, cand[1]) in in_place:
            if (key, cand[1]) not in verdict:
                verdict[(key, cand[1])] = in_place_ok(key, cand[1])
            ok = verdict[(key, cand[1])]
        elif kinds == DEPENDS:
            ok = bool(ids & (every_id | raw_ids | inherits_of))
        else:
            ok = any(ids & ids_of.get(kk, set()) for kk in kinds)
            if not ok and kinds and toast:
                ok = any(toast & rels_of.get(kk, set()) for kk in TOAST_KINDS)
            if not ok and kinds and cand[1]:
                ok = (key, _blank_own_oid(text, cand[1])) in same[other[side]]
            if not ok and kinds:
                ok = any(ref in ids_of.get(kk, set()) for i in ids for ref in linked[side].get(i, ())
                         for kk in kinds)
        if not ok and not cand[1]:
            # the same text on both sides, the same identities: only relation
            # names it carries differ, and they are names a renamed class row
            # changed between
            for o in by_text[other[side]].get((key, text), ()):
                ro, io, lo, to = marks[o]
                names = (refs ^ ro) | (_rels ^ lo) | (toast ^ to)
                if io == ids and names and names <= renamed:
                    ok = True
                    break
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
