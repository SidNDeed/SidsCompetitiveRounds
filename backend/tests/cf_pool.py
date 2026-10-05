"""A content-keyed pool of built case schemas for the connect-failure lane.

Why: a case build replays every migration's DDL, and on this seat every
b-tree build waits on a data-file sync (DataFileImmediateSync), so one build
costs minutes whenever other lanes share the disk. The pool builds a schema
once per build key, records its pristine state, and puts the schema back to
that state before every case. A database holds one pool schema at a time: a
build must be the only schema holding the application's tables, as on a
clean lane database (migration 209's guard reads every schema). What a case sees is what a
fresh build would show it; a schema that cannot be put back is dropped and
rebuilt, never used.

The build key is a hash of every input the build reads: each numbered
migration file (name and bytes), the ORM module, the build code (cf_pg, this
module, the ladder harness and the ladder suite whose replay it reuses) and
the faithful flag. A mutant of a migration file therefore gets a build of its
own; a mutant of main.py reuses the key's schema.

The reset, before each case (every step checked, any failure retires the
schema):
  - rows: every table the build left empty is emptied (DELETE under
    session_replication_role = replica, so no trigger or foreign-key action
    runs); a table the build seeded must still hold exactly its seed rows;
  - pages: every table whose heap or index sizes moved is vacuumed (which
    truncates an emptied heap to zero pages) and its moved indexes are
    rebuilt, so heap and index sizes equal the pristine ones byte for byte;
  - sequences, pg_class statistics (reltuples, relpages, relallvisible) and
    pg_statistic are put back to the pristine record: the planner sees what
    it saw on the fresh build (a never-vacuumed heap keeps reltuples -1);
  - the catalog fingerprint (relations, columns and defaults, constraints,
    indexes, triggers, routines, views, sequence parameters, types) and the
    schema's object census must equal the pristine ones.

Cases in one database run one at a time (a session advisory lock held for
the case), because the harness census compares everything outside the case
schema. Parallel runs use one database each (CF_TEST_PG_DSN).

CF_PG_POOL=0 turns the pool off: every case builds a fresh schema and drops
it, the original path.
"""

import asyncio
import contextlib
import glob
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cf_pg  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

harness = cf_pg.harness
asyncpg = cf_pg._asyncpg

META = "cf_pool"
LOCK_KEY = 3557001
PAGE_TRIES = 4
PAGE_WAIT_S = 1.5


def _log(line):
    """Every retirement and build, to CF_POOL_LOG when it names a file (the
    case's own stdout is captured)."""
    path = os.environ.get("CF_POOL_LOG")
    if path:
        with open(path, "a", encoding="ascii", newline="\n") as fh:
            fh.write(line + "\n")


def build_key(faithful):
    h = hashlib.sha256()
    for path in sorted(glob.glob(os.path.join(cf_pg.SQL_DIR, "*.sql"))):
        h.update(os.path.basename(path).encode("ascii", "replace") + b"\0")
        with open(path, "rb") as fh:
            h.update(fh.read())
        h.update(b"\0")
    for mod in (cf_pg.models, harness, cf_pg.lh, cf_pg, sys.modules[__name__]):
        with open(mod.__file__, "rb") as fh:
            h.update(fh.read())
        h.update(b"\0")
    h.update(b"faithful=%d" % bool(faithful))
    return h.hexdigest()[:16]


def _q(name):
    if not (name.replace("_", "").isalnum() and name == name.lower()):
        raise harness.CensusRefusal("not a plain identifier: %r" % name)
    return '"%s"' % name


_NSP = "SELECT oid FROM pg_catalog.pg_namespace WHERE nspname = $1"

_FINGERPRINT = (
    "SELECT c.relname::text, c.relkind::text, c.relpersistence::text, "
    "coalesce(pg_catalog.array_to_string(c.reloptions, ','), ''), c.relrowsecurity "
    "FROM pg_catalog.pg_class c WHERE c.relnamespace = $1 ORDER BY 1, 2",
    "SELECT c.relname::text, a.attnum, a.attname::text, "
    "pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull, a.attisdropped, "
    "a.attidentity::text, a.attgenerated::text, "
    "coalesce(pg_catalog.pg_get_expr(d.adbin, d.adrelid), '') "
    "FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid = a.attrelid "
    "LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
    "WHERE c.relnamespace = $1 AND a.attnum > 0 ORDER BY 1, 2",
    "SELECT coalesce(c.relname::text, ''), con.conname::text, con.contype::text, "
    "pg_catalog.pg_get_constraintdef(con.oid) FROM pg_catalog.pg_constraint con "
    "LEFT JOIN pg_catalog.pg_class c ON c.oid = con.conrelid "
    "WHERE con.connamespace = $1 ORDER BY 1, 2, 4",
    "SELECT ic.relname::text, pg_catalog.pg_get_indexdef(i.indexrelid) "
    "FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class ic ON ic.oid = i.indexrelid "
    "WHERE ic.relnamespace = $1 ORDER BY 1",
    "SELECT c.relname::text, t.tgname::text, pg_catalog.pg_get_triggerdef(t.oid), "
    "t.tgenabled::text FROM pg_catalog.pg_trigger t "
    "JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid "
    "WHERE c.relnamespace = $1 AND NOT t.tgisinternal ORDER BY 1, 2",
    "SELECT p.oid::pg_catalog.regprocedure::text, p.prokind::text, "
    "pg_catalog.md5(coalesce(p.prosrc, '') || '|' || p.prorettype::text || '|' "
    "|| coalesce(pg_catalog.array_to_string(p.proconfig, ','), '') || '|' "
    "|| p.provolatile::text) FROM pg_catalog.pg_proc p WHERE p.pronamespace = $1 "
    "ORDER BY 1",
    "SELECT c.relname::text, pg_catalog.md5(pg_catalog.pg_get_viewdef(c.oid)) "
    "FROM pg_catalog.pg_class c WHERE c.relnamespace = $1 AND c.relkind IN ('v', 'm') "
    "ORDER BY 1",
    "SELECT c.relname::text, s.seqtypid::pg_catalog.regtype::text, s.seqstart, "
    "s.seqincrement, s.seqmax, s.seqmin, s.seqcache, s.seqcycle "
    "FROM pg_catalog.pg_sequence s JOIN pg_catalog.pg_class c ON c.oid = s.seqrelid "
    "WHERE c.relnamespace = $1 ORDER BY 1",
    "SELECT t.typname::text, t.typtype::text, coalesce((SELECT "
    "pg_catalog.string_agg(e.enumlabel::text, ',' ORDER BY e.enumsortorder) "
    "FROM pg_catalog.pg_enum e WHERE e.enumtypid = t.oid), '') "
    "FROM pg_catalog.pg_type t WHERE t.typnamespace = $1 ORDER BY 1",
)

_TABLES = ("SELECT c.relname::text FROM pg_catalog.pg_class c "
           "WHERE c.relnamespace = $1 AND c.relkind IN ('r', 'p') ORDER BY 1")
_SEQUENCES = ("SELECT c.relname::text FROM pg_catalog.pg_class c "
              "WHERE c.relnamespace = $1 AND c.relkind = 'S' ORDER BY 1")
# Per table: the heap, its TOAST heap (-1 when none) and each index, by the
# index's own name (an index keeps its name and oid across a rebuild).
_SIZES = (
    "SELECT c.relname::text AS t, pg_catalog.pg_relation_size(c.oid) AS heap, "
    "CASE WHEN c.reltoastrelid <> 0 THEN pg_catalog.pg_relation_size(c.reltoastrelid) "
    "ELSE -1 END AS toast, "
    "coalesce((SELECT pg_catalog.json_object_agg(ic.relname::text, "
    "pg_catalog.pg_relation_size(ic.oid)) FROM pg_catalog.pg_index i "
    "JOIN pg_catalog.pg_class ic ON ic.oid = i.indexrelid WHERE i.indrelid = c.oid), "
    "'{}')::text AS idx "
    "FROM pg_catalog.pg_class c WHERE c.relnamespace = $1 AND c.relkind IN ('r', 'p') "
    "ORDER BY 1")
_STATS = ("SELECT c.relname::text, c.relkind::text, c.reltuples::float8, c.relpages, "
          "c.relallvisible FROM pg_catalog.pg_class c WHERE c.relnamespace = $1 "
          "AND c.relkind IN ('r', 'p', 'i', 'm', 't') ORDER BY 1, 2")


async def _fingerprint(conn, nsp):
    h = hashlib.sha256()
    for sql in _FINGERPRINT:
        for r in await conn.fetch(sql, nsp):
            h.update(repr(tuple(r)).encode("utf-8"))
            h.update(b"\n")
        h.update(b"--\n")
    return h.hexdigest()


async def _counts(conn, tables):
    if not tables:
        return {}
    sql = " UNION ALL ".join(
        "SELECT %s::text AS t, count(*) AS n FROM %s" % ("'%s'" % t, _q(t)) for t in tables)
    return {r["t"]: r["n"] for r in await conn.fetch(sql)}


async def _content(conn, table):
    return await conn.fetchval(
        "SELECT pg_catalog.md5(coalesce(pg_catalog.string_agg(x::text, chr(10) "
        "ORDER BY x::text), '')) FROM %s x" % _q(table))


async def _sizes(conn, nsp):
    return {r["t"]: [r["heap"], r["toast"], json.loads(r["idx"])]
            for r in await conn.fetch(_SIZES, nsp)}


async def _seqs(conn, sequences):
    out = {}
    for s in sequences:
        r = await conn.fetchrow("SELECT last_value, is_called FROM %s" % _q(s))
        out[s] = [r["last_value"], r["is_called"]]
    return out


async def _stats(conn, nsp):
    return {"%s|%s" % (r[0], r[1]): [r[2], r[3], r[4]] for r in await conn.fetch(_STATS, nsp)}


async def capture(conn, schema):
    """The pristine record of `schema` (conn bound to it)."""
    nsp = await conn.fetchval(_NSP, schema)
    tables = [r[0] for r in await conn.fetch(_TABLES, nsp)]
    sequences = [r[0] for r in await conn.fetch(_SEQUENCES, nsp)]
    counts = await _counts(conn, tables)
    seeded = {t: [n, await _content(conn, t)] for t, n in counts.items() if n}
    return {
        "tables": tables,
        "seeded": seeded,
        "sizes": await _sizes(conn, nsp),
        "seqs": await _seqs(conn, sequences),
        "stats": await _stats(conn, nsp),
        "fingerprint": await _fingerprint(conn, nsp),
        "own": sorted([list(x) for x in await harness.schema_objects(conn, schema)]),
    }


async def reset(conn, schema, p):
    """Put `schema` back to the pristine record `p`. Returns None when every
    check holds, else the reason the schema must be retired."""
    nsp = await conn.fetchval(_NSP, schema)
    if nsp is None:
        return "schema %s is gone" % schema
    if await _fingerprint(conn, nsp) != p["fingerprint"]:
        return "catalog fingerprint moved (a case ran DDL)"
    tables = p["tables"]
    counts = await _counts(conn, tables)
    for t, (n, digest) in p["seeded"].items():
        if counts.get(t) != n or await _content(conn, t) != digest:
            return "seeded table %s moved" % t
    dirty = [t for t in tables if t not in p["seeded"] and counts.get(t)]
    if dirty:
        await conn.execute("SET session_replication_role = replica")
        try:
            async with conn.transaction():
                for t in dirty:
                    await conn.execute("DELETE FROM %s" % _q(t))
        finally:
            await conn.execute("RESET session_replication_role")
    # VACUUM removes the deleted rows only once no session of this database
    # can still see them; one that is ending keeps them for a moment, so the
    # page step is retried a few times before the schema is retired.
    for attempt in range(PAGE_TRIES):
        sizes = await _sizes(conn, nsp)
        moved = [t for t in tables if sizes.get(t) != p["sizes"].get(t)]
        if not moved:
            break
        if attempt:
            await asyncio.sleep(PAGE_WAIT_S)
        for t in moved:
            heap, toast, _ = sizes[t]
            if heap != p["sizes"][t][0] or toast != p["sizes"][t][1]:
                await conn.execute("VACUUM %s" % _q(t))
        # The heaps' statistics go back before any index is rebuilt: an index
        # build reads its heap's estimate (and keeps a never-vacuumed heap's
        # -1), as it did on the fresh build.
        await _restore_stats(conn, nsp, p)
        for t in moved:
            idx = (await _sizes(conn, nsp))[t][2]
            for name in sorted(idx):
                if idx[name] != p["sizes"][t][2].get(name):
                    await conn.execute("REINDEX INDEX %s" % _q(name))
    sizes = await _sizes(conn, nsp)
    for t in tables:
        if sizes.get(t) != p["sizes"].get(t):
            others = [tuple(r) for r in await conn.fetch(
                "SELECT pid, state, backend_xmin IS NOT NULL, "
                "       CAST(EXTRACT(EPOCH FROM now() - xact_start) AS integer) "
                "  FROM pg_catalog.pg_stat_activity "
                " WHERE datname = current_database() AND pid <> pg_backend_pid()")]
            return "table %s sizes %r, pristine %r; other sessions %r" % (
                t, sizes.get(t), p["sizes"].get(t), others)
    seqs = await _seqs(conn, list(p["seqs"]))
    for s, (last, called) in p["seqs"].items():
        if seqs[s] != [last, called]:
            await conn.execute("SELECT pg_catalog.setval($1::regclass, $2, $3)",
                               _q(s), last, called)
    await _restore_stats(conn, nsp, p)
    # Every check again, from the catalog and the tables as they now are.
    if await _counts(conn, tables) != {t: p["seeded"].get(t, [0])[0] for t in tables}:
        return "row counts did not return to the pristine ones"
    if await _seqs(conn, list(p["seqs"])) != p["seqs"]:
        return "sequences did not return to the pristine state"
    if await _stats(conn, nsp) != p["stats"]:
        return "pg_class statistics did not return to the pristine ones"
    if await conn.fetchval(
            "SELECT count(*) FROM pg_catalog.pg_statistic s JOIN pg_catalog.pg_class c "
            "ON c.oid = s.starelid WHERE c.relnamespace = $1", nsp):
        return "pg_statistic still holds rows for the schema"
    if await _fingerprint(conn, nsp) != p["fingerprint"]:
        return "catalog fingerprint moved during the reset"
    own = sorted([list(x) for x in await harness.schema_objects(conn, schema)])
    if own != p["own"]:
        return "the schema's object census moved"
    return None


async def _restore_stats(conn, nsp, p):
    async with conn.transaction():
        stats = await _stats(conn, nsp)
        for k, want in p["stats"].items():
            if stats.get(k) != want:
                rel, kind = k.split("|")
                await conn.execute(
                    "UPDATE pg_catalog.pg_class SET reltuples = $1, relpages = $2, "
                    "relallvisible = $3 WHERE relnamespace = $4 AND relname = $5 "
                    "AND relkind::text = $6", want[0], want[1], want[2], nsp, rel, kind)
        await conn.execute(
            "DELETE FROM pg_catalog.pg_statistic WHERE starelid IN (SELECT c.oid "
            "FROM pg_catalog.pg_class c WHERE c.relnamespace = $1)", nsp)


async def _ensure_meta(meta):
    await meta.execute("CREATE SCHEMA IF NOT EXISTS %s" % META)
    await meta.execute(
        "CREATE TABLE IF NOT EXISTS %s.entries (key text PRIMARY KEY, "
        "schema_name text NOT NULL, pristine text NOT NULL, "
        "built_at timestamptz NOT NULL DEFAULT now(), "
        "used_at timestamptz NOT NULL DEFAULT now(), uses integer NOT NULL DEFAULT 0)"
        % META)


async def _drop(dsn, schema, own):
    conn = await harness.connect_bound(dsn, schema)
    try:
        await harness.drop_case_schema(
            conn, schema, None if own is None else {tuple(x) for x in own})
    finally:
        await conn.close()


async def _build(dsn, faithful):
    """A new pool schema: the harness's create-under-census, the build, the
    outside census, the pristine record."""
    import types
    schema = harness.case_schema("cfpool")
    conn = await harness.connect_bound(dsn, schema)
    created = False
    try:
        # Migration 209's rename guard reads information_schema.columns
        # across every schema of the database: the build must be the only
        # schema holding the application's tables, as on a clean lane
        # database.
        others = [r[0] for r in await conn.fetch(
            "SELECT n.nspname::text FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n "
            "ON n.oid = c.relnamespace WHERE c.relname = 'ffa_lobbies' AND c.relkind = 'r'")]
        if others:
            raise harness.CensusRefusal("refusing to build %s: schema(s) %r already hold "
                                        "ffa_lobbies in this database" % (schema, others))
        await harness.create_case_schema(conn, schema)
        created = True
        outside = await harness.outside_objects(conn, schema)
        await cf_pg.build(types.SimpleNamespace(conn=conn, schema=schema),
                          with_355=True, dsn=dsn, faithful=faithful)
        after = await harness.outside_objects(conn, schema)
        if after != outside:
            changed = sorted(set(after) ^ set(outside))
            raise harness.CensusRefusal("the build of %s changed %d object(s) outside it: "
                                        "%r" % (schema, len(changed), changed[:5]))
        pristine = await capture(conn, schema)
    except BaseException:
        if created:
            try:
                await harness.drop_case_schema(conn, schema, None)
            finally:
                await conn.close()
        else:
            await conn.close()
        raise
    await conn.close()
    return schema, pristine


async def _faithful_dsn():
    """The faithful builds live in a database of their own (migration 209's
    guard reads information_schema.columns across every schema of its
    database): the lane database's name plus _faithful, made once."""
    base, name = cf_pg.DSN.rsplit("/", 1)
    name = name.split("?", 1)[0] + "_faithful"
    admin = await asyncpg.connect(cf_pg.DSN)
    try:
        if not await admin.fetchval("SELECT count(*) FROM pg_catalog.pg_database "
                                    "WHERE datname = $1", name):
            try:
                await admin.execute('CREATE DATABASE "%s"' % name)
            except asyncpg.DuplicateDatabaseError:
                pass
    finally:
        await admin.close()
    return base + "/" + name


class PoolCase:
    """What cf_pg.case yields for a pooled case: conn bound to the schema,
    schema, dsn, seal() and own, as harness.CaseSchema gives them."""

    def __init__(self, dsn, schema, own):
        self.dsn = dsn
        self.schema = schema
        self.own = {tuple(x) for x in own}
        self.declared = set()
        self.conn = None
        self._outside = None

    async def open(self):
        self.conn = await harness.connect_bound(self.dsn, self.schema)
        self._outside = await harness.outside_objects(self.conn, self.schema)

    async def seal(self):
        """As the harness's seal: nothing outside the schema moved, and the
        schema's objects become the case's own. Those the build did not
        leave (a case's own fixture objects, S55's sleeping trigger
        function) are declared, and go when the case ends."""
        after = await harness.outside_objects(self.conn, self.schema)
        if after != self._outside:
            changed = sorted(set(after) ^ set(self._outside))
            raise harness.CensusRefusal("the case of %s changed %d object(s) outside it: %r"
                                        % (self.schema, len(changed), changed[:5]))
        now = {tuple(x) for x in await harness.schema_objects(self.conn, self.schema)}
        self.declared = now - self.own
        return self.own | self.declared

    async def close(self):
        if self.conn is not None:
            await self.conn.close()


_DECLARED_DROP = {"routine": "FUNCTION", "relation r": "TABLE", "relation p": "TABLE",
                  "relation v": "VIEW", "relation m": "MATERIALIZED VIEW",
                  "relation S": "SEQUENCE"}


async def _drop_declared(dsn, schema, declared):
    """Drop the objects a case declared through seal(), relations first
    (their row types go with them), then routines (CASCADE takes a trigger
    that calls one). Returns None when none of them is left, else why."""
    conn = await harness.connect_bound(dsn, schema)
    try:
        await conn.execute("SET lock_timeout = '10s'")
        order = sorted(declared, key=lambda kn: (kn[0] == "routine", kn[0] == "type", kn))
        for kind, name in order:
            what = _DECLARED_DROP.get(kind)
            if what is None:
                continue
            if kind == "routine":
                fname, _, args = name.partition("(")
                target = "%s(%s" % (_q(fname), args)
            else:
                target = _q(name)
            await conn.execute("DROP %s IF EXISTS %s.%s CASCADE" % (what, _q(schema), target))
        left = {tuple(x) for x in await harness.schema_objects(conn, schema)} & set(declared)
        return None if not left else "declared object(s) left: %r" % sorted(left)[:5]
    except Exception as exc:
        return "dropping the declared objects raised %r" % (exc,)
    finally:
        await conn.close()


@contextlib.asynccontextmanager
async def checkout(faithful=False):
    """A pristine pool schema for one case; yields (case, sessionmaker)."""
    dsn = await _faithful_dsn() if faithful else cf_pg.DSN
    key = build_key(faithful)
    meta = await asyncpg.connect(dsn)
    try:
        await meta.execute("SELECT pg_advisory_lock($1)", LOCK_KEY)
        await _ensure_meta(meta)
        row = await meta.fetchrow("SELECT schema_name, pristine FROM %s.entries "
                                  "WHERE key = $1" % META, key)
        schema = pristine = None
        if row is not None:
            schema, pristine = row["schema_name"], json.loads(row["pristine"])
            conn = await harness.connect_bound(dsn, schema)
            try:
                why = await reset(conn, schema, pristine)
            except Exception as exc:                   # pragma: no cover
                why = "reset raised %r" % (exc,)
            finally:
                await conn.close()
            if why is not None:
                print("[cf_pool] retiring %s: %s" % (schema, why))
                _log("retire %s key=%s: %s" % (schema, key, why))
                await meta.execute("DELETE FROM %s.entries WHERE key = $1" % META, key)
                await _drop(dsn, schema, pristine["own"])
                schema = pristine = None
        if schema is None:
            # One pool schema per database (_build's guard): another key's
            # schema goes before this key's build.
            for old in await meta.fetch("SELECT key, schema_name, pristine FROM %s.entries "
                                        "WHERE key <> $1" % META, key):
                await meta.execute("DELETE FROM %s.entries WHERE key = $1" % META,
                                   old["key"])
                await _drop(dsn, old["schema_name"], json.loads(old["pristine"])["own"])
            schema, pristine = await _build(dsn, faithful)
            _log("built %s key=%s" % (schema, key))
            await meta.execute(
                "INSERT INTO %s.entries (key, schema_name, pristine) VALUES ($1, $2, $3)"
                % META, key, schema, json.dumps(pristine, sort_keys=True))
        await meta.execute("UPDATE %s.entries SET used_at = now(), uses = uses + 1 "
                           "WHERE key = $1" % META, key)
        c = PoolCase(dsn, schema, pristine["own"])
        await c.open()
        engine = harness.bound_engine(dsn, schema)
        try:
            yield c, async_sessionmaker(engine, expire_on_commit=False)
        finally:
            await engine.dispose()
            await c.close()
            if c.declared:
                why = await _drop_declared(dsn, schema, c.declared)
                if why is None:
                    _log("dropped declared %s: %r" % (schema, sorted(c.declared)))
                else:
                    print("[cf_pool] retiring %s: %s" % (schema, why))
                    _log("retire %s key=%s: %s" % (schema, key, why))
                    await meta.execute("DELETE FROM %s.entries WHERE key = $1" % META, key)
                    await _drop(dsn, schema, sorted(c.own | c.declared))
    finally:
        await meta.close()
