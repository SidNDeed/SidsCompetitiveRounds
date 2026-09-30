"""DISCORD-COLLECTION: the shared harness of the reveal lane's section 10 rows
(DISCORD-COLLECTION-DESIGN.md rev 13). Not a test module: the rows live in
test_discord_collection_server.py and test_discord_collection_bot.py, the
mutations and their controls in discord_collection_controls.py.

Live PostgreSQL is REQUIRED by the server and end-to-end rows, and a missing
DSN FAILS, naming the variable (the test_ticket_redaction.py:390 shape):
    DISCORD_COLLECTION_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    DISCORD_COLLECTION_TEST_PG_OPTOUT=1   says out loud that this run skips them

ONE SCHEMA. Everything this harness builds lives in the schema SCHEMA of a
database whose name carries DB_NAME_MARK. The build runs the repository's own
migrations (backend/sql/NNN_*.sql) on a connection bound to SCHEMA at connect,
then the ORM's create_all with SCHEMA named in every statement it renders,
then the ORM columns the migration chain does not add, then the migrations
that failed, again, until a pass applies nothing new. A migration names no
schema, so after EACH file the census proves that nothing it made landed
outside SCHEMA. Every statement this file writes itself names SCHEMA.

A CENSUS BEFORE ANYTHING DESTRUCTIVE. Before the harness ends a session,
sends a DROP, a TRUNCATE or a CREATE, it reads every relation, function,
type, extension and schema the database holds above the initdb line (OID
16384), in EVERY schema, and refuses to proceed if one is not its own: a
relation outside SCHEMA (other than the TOAST storage of a SCHEMA table), any
function, type or extension outside it, any schema but SCHEMA and the
per-session temporary ones, or -- once built -- any relation inside SCHEMA
that the build did not record, by name. A SCHEMA without this harness's
marker table is someone else's and is never dropped. The terminates, drops
and truncates go through ONE sender, send_destructive, which refuses unless
the census ran first on the same record.

Synthetic identities only: SteamID64s from STEAM_BASE (inside the individual
range, outside every prefix a real account carries), Discord ids from
DISCORD_BASE, names composed here.
"""

import ast
import asyncio
import copy
import hashlib
import hmac
import io
import json as _json
import os
import re
import secrets
import threading
import time as _time
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
API_DIR = BACKEND / "api"
SQL_DIR = BACKEND / "sql"
BOT_PATH = BACKEND / "discord_bot.py"

DSN_VAR = "DISCORD_COLLECTION_TEST_PG_DSN"
OPTOUT_VAR = "DISCORD_COLLECTION_TEST_PG_OPTOUT"


def run(coro):
    return asyncio.run(coro)


# -- the live-PostgreSQL gate ---------------------------------------------------

def optout(raw) -> bool:
    """Only an affirmative word opts out; "0", "false" or an unknown value do
    not, so the live rows then FAIL and name the DSN (#438)."""
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def require_pg(dsn, opted_out):
    if dsn:
        return dsn
    if opted_out:
        pytest.skip(f"{OPTOUT_VAR} is set -- the Discord collection reveal's live-PostgreSQL rows "
                    "deliberately not run in this invocation")
    pytest.fail(
        f"{DSN_VAR} is not set, so the Discord collection reveal's server and end-to-end rows were "
        f"never executed. Set {DSN_VAR}=postgresql+asyncpg://... to run them, or {OPTOUT_VAR}=1 to "
        "say out loud that this run skips them.")


# -- synthetic identities ------------------------------------------------------

MOD_SECRET = "dc-reveal-mod-secret"
ADMIN_SECRET = "dc-reveal-admin-secret"
INTERNAL_KEY = "dc-reveal-internal-key"
STEAM_BASE = 76561202100000000        # 7656120210000xxxx: SteamID64s by the pool's own range check
DISCORD_BASE = 900000000000000000     # 18 digits, synthetic
BASE_URL = "http://dc-reveal.test"


def steam_of(n: int) -> str:
    return str(STEAM_BASE + int(n))


def discord_of(n: int) -> str:
    return str(DISCORD_BASE + int(n))


def mod_sig(canon: str) -> str:
    return hmac.new(MOD_SECRET.encode(), canon.encode(), hashlib.sha256).hexdigest()


# -- the schema, its census and its one destructive sender -----------------------

SCHEMA = "dc_reveal"
DB_NAME_MARK = "discord_collection"
BUILD_TABLE = "dc_reveal_build"
OBJECTS_TABLE = "dc_reveal_objects"
SEED_PREFIX = "dcs_"
BUILD_VERSION = "dc-reveal-build-1"
FIRST_NORMAL_OID = 16384
CENSUS_TAG = "/* dc-reveal census */"
NAME_SQL = "SELECT pg_catalog.current_database() /* dc-reveal name gate */"
MIGRATION_RE = re.compile(r"^[0-9]{3}_.*\.sql$")
TEMP_SCHEMA_RE = re.compile(r"^pg_(?:toast_)?temp_[0-9]+$")
# Tables whose build-time rows are NOT carried into a case: identities and
# anything keyed on one. A case makes its own players.
SEED_DENY = frozenset({
    "players", "admin_users", "player_bans", "steam_sessions", "link_codes", "glicko_ratings",
    "glicko_ratings_2v2", "glicko_ratings_1v2", "glicko_ratings_ffa", "player_items",
    "gold_transactions", "rating_history", "matches", "ranked_series", "pc_prints", "pc_cards",
    "pc_packs", "pc_pool_snapshots", "pc_pool_members", "pc_events", "pc_delivery_leases",
    "pc_portraits", "pc_portrait_nonces", "pc_daily_claims", "pending_dms",
})

REL_CENSUS_SQL = (
    "SELECT n.nspname::text AS schema, c.relname::text AS name, c.relkind::text AS kind,"
    " COALESCE(bn.nspname::text, '') AS owner_schema"
    " FROM pg_catalog.pg_class c"
    " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
    " LEFT JOIN pg_catalog.pg_index x ON x.indexrelid = c.oid"
    " LEFT JOIN pg_catalog.pg_class t ON t.oid = x.indrelid"
    " LEFT JOIN pg_catalog.pg_class b"
    " ON b.reltoastrelid = CASE WHEN c.relkind = 't' THEN c.oid WHEN t.relkind = 't' THEN t.oid END"
    " LEFT JOIN pg_catalog.pg_namespace bn ON bn.oid = b.relnamespace"
    f" WHERE c.oid >= {FIRST_NORMAL_OID} ORDER BY 1, 2 " + CENSUS_TAG)
OTHER_CENSUS_SQL = (
    "SELECT 'function' AS kind, n.nspname::text AS schema, p.proname::text AS name"
    " FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace"
    f" WHERE p.oid >= {FIRST_NORMAL_OID}"
    " UNION ALL SELECT 'type', n.nspname::text, t.typname::text"
    " FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace"
    f" WHERE t.oid >= {FIRST_NORMAL_OID} AND t.typrelid = 0"
    " UNION ALL SELECT 'extension', n.nspname::text, e.extname::text"
    " FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace"
    f" WHERE e.oid >= {FIRST_NORMAL_OID}"
    " UNION ALL SELECT 'schema', n.nspname::text, n.nspname::text"
    f" FROM pg_catalog.pg_namespace n WHERE n.oid >= {FIRST_NORMAL_OID} " + CENSUS_TAG)
MARKER_SQL = (f"SELECT state, fingerprint, failed, seeds FROM {SCHEMA}.{BUILD_TABLE} WHERE id = 1 "
              + CENSUS_TAG)
RECORDED_SQL = f"SELECT name FROM {SCHEMA}.{OBJECTS_TABLE} " + CENSUS_TAG


def _destructive(sql: str) -> bool:
    s = " ".join(sql.split()).upper()
    return (s.startswith("DROP ") or s.startswith("TRUNCATE ") or s.startswith("CREATE SCHEMA ")
            or s.startswith("DELETE FROM ") or "PG_TERMINATE_BACKEND" in s)


class Recorded:
    """An asyncpg connection that writes each statement into `sent` before it
    sends it. A terminate, drop, truncate or schema creation it refuses: one
    reaches a connection only through send_destructive."""

    def __init__(self, conn, sent):
        self.conn, self.sent = conn, sent

    async def _send(self, method, sql, args):
        if _destructive(sql):
            raise RuntimeError("a destructive statement reached a recorded connection outside "
                               f"send_destructive: {' '.join(sql.split())[:80]!r}")
        self.sent.append(sql)
        return await getattr(self.conn, method)(sql, *args)

    async def execute(self, sql, *args):
        return await self._send("execute", sql, args)

    async def fetch(self, sql, *args):
        return await self._send("fetch", sql, args)

    async def fetchval(self, sql, *args):
        return await self._send("fetchval", sql, args)

    async def fetchrow(self, sql, *args):
        return await self._send("fetchrow", sql, args)

    async def close(self):
        await self.conn.close()


async def send_destructive(conn, sql):
    """THE one sender of terminates, drops, truncates and schema creations.
    It refuses unless a census statement is already on the same record."""
    if not _destructive(sql):
        raise RuntimeError(f"send_destructive sends destructive statements only: {sql[:80]!r}")
    if not isinstance(conn, Recorded) or not any(CENSUS_TAG in s for s in conn.sent):
        raise RuntimeError("no census on this record before a destructive statement")
    conn.sent.append(sql)
    return await conn.conn.execute(sql)


def assert_census_first(sent):
    first = next((i for i, s in enumerate(sent) if _destructive(s)), None)
    if first is None:
        return
    assert any(CENSUS_TAG in s for s in sent[:first]), "a destructive statement went out before the census"


async def connect(url, sent, **settings):
    import asyncpg
    server_settings = {"search_path": SCHEMA}
    server_settings.update(settings)
    conn = await asyncpg.connect(host=url.host, port=url.port, user=url.username,
                                 password=url.password or None, database=url.database,
                                 server_settings=server_settings)
    return Recorded(conn, sent)


def fingerprint() -> str:
    h = hashlib.sha256(BUILD_VERSION.encode())
    for p in sorted(SQL_DIR.iterdir()):
        if MIGRATION_RE.match(p.name):
            data = p.read_bytes()
            h.update(len(data).to_bytes(8, "big"))
            h.update(data)
    h.update((API_DIR / "models.py").read_bytes())
    return h.hexdigest()


async def census(conn):
    """(foreign, state): foreign is every object this harness does not own,
    as readable strings; state is the marker row (or None)."""
    rels = await conn.fetch(REL_CENSUS_SQL)
    others = await conn.fetch(OTHER_CENSUS_SQL)
    # This session's own temporary schema (a migration may make a pg_temp
    # helper function, 164 does): its objects end with the session.
    my_temp = await conn.fetchval("SELECT n.nspname::text FROM pg_catalog.pg_namespace n"
                                  " WHERE n.oid = pg_catalog.pg_my_temp_schema() " + CENSUS_TAG)
    mine = {my_temp, my_temp.replace("pg_temp_", "pg_toast_temp_")} if my_temp else set()
    rels = [r for r in rels if r["schema"] not in mine]
    others = [r for r in others if r["kind"] == "schema" or r["schema"] not in mine]
    schema_exists = any(r["kind"] == "schema" and r["name"] == SCHEMA for r in others)
    state = None
    recorded = None
    if schema_exists and any(r["schema"] == SCHEMA and r["name"] == BUILD_TABLE for r in rels):
        state = await conn.fetchrow(MARKER_SQL)
        if state is not None and state["state"] == "built":
            recorded = {r["name"] for r in await conn.fetch(RECORDED_SQL)}
    foreign = []
    for r in rels:
        if r["schema"] == SCHEMA:
            if state is None:
                foreign.append(f"{r['schema']}.{r['name']} ({r['kind']}; {SCHEMA} carries no build marker)")
            elif recorded is not None and r["name"] not in recorded:
                foreign.append(f"{r['schema']}.{r['name']} ({r['kind']}; not recorded by the build)")
        elif r["schema"] == "pg_toast" and r["owner_schema"] == SCHEMA:
            continue
        else:
            foreign.append(f"{r['schema']}.{r['name']} ({r['kind']})")
    for r in others:
        if r["kind"] == "schema":
            if r["name"] != SCHEMA and not TEMP_SCHEMA_RE.match(r["name"]):
                foreign.append(f"schema {r['name']}")
        elif r["schema"] != SCHEMA:
            foreign.append(f"{r['kind']} {r['schema']}.{r['name']}")
    missing = set()
    if recorded is not None:
        present = {r["name"] for r in rels if r["schema"] == SCHEMA}
        missing = recorded - present
    return foreign, state, schema_exists, missing


def _refusal(name, foreign, what):
    shown = "; ".join(foreign[:10]) + (f"; and {len(foreign) - 10} more" if len(foreign) > 10 else "")
    return RuntimeError(f"database {name!r} holds {len(foreign)} object(s) this harness did not create: "
                        f"{shown}. Refusing to {what}.")


def migration_files():
    return sorted(p for p in SQL_DIR.iterdir() if MIGRATION_RE.match(p.name))


async def _apply_file(conn, path):
    sql = path.read_text(encoding="utf-8")
    try:
        conn.sent.append(f"/* migration {path.name[:3]} */ " + sql[:200])
        await conn.conn.execute(sql)
        return True
    except Exception:
        try:
            await conn.conn.execute("ROLLBACK")
        except Exception:
            pass
        return False


async def _nothing_outside(conn, what):
    foreign, _state, _exists, _missing = await census(conn)
    outside = [f for f in foreign if not f.startswith(SCHEMA + ".")]
    if outside:
        raise RuntimeError(f"{what} made object(s) outside {SCHEMA}: {outside[:5]}")


async def _create_all(url):
    import models
    eng = create_async_engine(url.render_as_string(hide_password=False),
                              connect_args={"server_settings": {"search_path": SCHEMA}},
                              execution_options={"schema_translate_map": {None: SCHEMA}})
    try:
        async with eng.begin() as c:
            await c.run_sync(models.Base.metadata.create_all)
    finally:
        await eng.dispose()


async def _orm_gap(conn):
    """Every ORM column the migration chain did not add, added nullable (with
    its server default, if it has one): the tables the ORM declares and a
    migration made first keep the migration's shape and gain the rest."""
    import models
    from sqlalchemy.dialects import postgresql
    dialect = postgresql.dialect()
    rows = await conn.fetch(
        "SELECT table_name::text AS t, column_name::text AS c FROM information_schema.columns"
        " WHERE table_schema = $1", SCHEMA)
    have = {}
    for r in rows:
        have.setdefault(r["t"], set()).add(r["c"])
    added = 0
    for table in models.Base.metadata.sorted_tables:
        if table.name not in have:
            continue
        for col in table.columns:
            if col.name in have[table.name]:
                continue
            ddl = f'ALTER TABLE {SCHEMA}."{table.name}" ADD COLUMN IF NOT EXISTS "{col.name}" ' \
                  f"{col.type.compile(dialect=dialect)}"
            if col.server_default is not None and hasattr(col.server_default, "arg"):
                arg = col.server_default.arg
                ddl += f" DEFAULT {arg.text if hasattr(arg, 'text') else repr(arg)}"
            await conn.execute(ddl)
            added += 1
    return added


async def _build(conn, url, fp):
    await send_destructive(conn, f"CREATE SCHEMA {SCHEMA}")
    await conn.execute(f"CREATE TABLE {SCHEMA}.{BUILD_TABLE} (id integer PRIMARY KEY, state text NOT NULL,"
                       " fingerprint text NOT NULL, failed text NOT NULL DEFAULT '',"
                       " seeds text NOT NULL DEFAULT '', built_at timestamptz)")
    await conn.execute(f"INSERT INTO {SCHEMA}.{BUILD_TABLE} (id, state, fingerprint) VALUES (1, 'building', $1)", fp)
    await conn.execute(f"CREATE TABLE {SCHEMA}.{OBJECTS_TABLE} (name text NOT NULL, kind text NOT NULL)")
    failed = []
    for p in migration_files():
        if not await _apply_file(conn, p):
            failed.append(p)
        await _nothing_outside(conn, f"migration {p.name[:3]}")
    await _create_all(url)
    await _nothing_outside(conn, "create_all")
    await _orm_gap(conn)
    while failed:
        again = []
        for p in failed:
            if not await _apply_file(conn, p):
                again.append(p)
            await _nothing_outside(conn, f"migration {p.name[:3]}")
        if len(again) == len(failed):
            break
        failed = again
    tables = [r["t"] for r in await conn.fetch(
        "SELECT c.relname::text AS t FROM pg_catalog.pg_class c"
        " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = $1 AND c.relkind IN ('r', 'p') ORDER BY 1", SCHEMA)]
    seeds = []
    for t in tables:
        if t in (BUILD_TABLE, OBJECTS_TABLE) or t in SEED_DENY:
            continue
        n = await conn.fetchval(f'SELECT count(*) FROM {SCHEMA}."{t}"')
        if n:
            copy_name = f"{SEED_PREFIX}{len(seeds) + 1}"
            await conn.execute(f'CREATE TABLE {SCHEMA}."{copy_name}" AS SELECT * FROM {SCHEMA}."{t}"')
            seeds.append(f"{t}={copy_name}")
    await conn.execute(
        f"INSERT INTO {SCHEMA}.{OBJECTS_TABLE} (name, kind) SELECT c.relname::text, c.relkind::text"
        " FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = $1", SCHEMA)
    await conn.execute(
        f"UPDATE {SCHEMA}.{BUILD_TABLE} SET state = 'built', failed = $1, seeds = $2, built_at = now() WHERE id = 1",
        ",".join(p.name[:3] for p in failed), ";".join(seeds))


async def ensure_schema(url, sent):
    """The built schema, reused while its fingerprint holds, rebuilt otherwise.
    Returns the marker row as a dict."""
    conn = await connect(url, sent, lock_timeout="10s")
    try:
        name = await conn.fetchval(NAME_SQL)
        if DB_NAME_MARK not in (name or ""):
            raise RuntimeError(f"{DSN_VAR} points at database {name!r}; this harness builds, truncates and "
                               f"drops schema {SCHEMA} only on a database whose name carries {DB_NAME_MARK!r}.")
        foreign, state, exists, missing = await census(conn)
        if foreign:
            raise _refusal(name, foreign, f"build, reset or drop schema {SCHEMA}")
        fp = fingerprint()
        if state is not None and state["state"] == "built" and state["fingerprint"] == fp and not missing:
            return dict(state)
        if exists:
            if state is None:
                raise RuntimeError(f"schema {SCHEMA} exists without this harness's marker; refusing to drop it")
            await send_destructive(conn, f"DROP SCHEMA {SCHEMA} CASCADE")
        await _build(conn, url, fp)
        row = await conn.fetchrow(MARKER_SQL)
        return dict(row)
    finally:
        await conn.close()


async def reset_schema(url, sent, info):
    """A case's fresh state: census, every other session on the lane database
    ended, every build table emptied and the recorded seed rows copied back."""
    conn = await connect(url, sent, lock_timeout="10s")
    try:
        name = await conn.fetchval(NAME_SQL)
        if DB_NAME_MARK not in (name or ""):
            raise RuntimeError(f"database {name!r} does not carry {DB_NAME_MARK!r}")
        foreign, state, _exists, missing = await census(conn)
        if foreign:
            raise _refusal(name, foreign, f"end sessions on or truncate schema {SCHEMA}")
        if state is None or state["state"] != "built" or missing:
            raise RuntimeError(f"schema {SCHEMA} is not a complete build of this harness")
        await send_destructive(conn, "SELECT pg_catalog.pg_terminate_backend(pid) FROM pg_catalog.pg_stat_activity"
                                     " WHERE datname = pg_catalog.current_database()"
                                     " AND pid <> pg_catalog.pg_backend_pid()")
        seeds = dict(s.split("=", 1) for s in (info.get("seeds") or "").split(";") if s)
        tables = [r["t"] for r in await conn.fetch(
            "SELECT c.relname::text AS t FROM pg_catalog.pg_class c"
            " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = $1 AND c.relkind IN ('r', 'p') ORDER BY 1", SCHEMA)]
        keep = {BUILD_TABLE, OBJECTS_TABLE} | set(seeds.values())
        work = [t for t in tables if t not in keep]
        # DELETE, not TRUNCATE: a TRUNCATE of the build's 125 tables writes
        # ~500 new relation files and took 27 s here; the tables are small.
        # Replica role: no trigger and no foreign-key action fires while the
        # whole set is emptied and the seed rows go back.
        await conn.execute("SET session_replication_role = replica")
        try:
            await send_destructive(conn, " ".join(f'DELETE FROM {SCHEMA}."{t}";' for t in work))
            for t, copy_name in seeds.items():
                await conn.execute(f'INSERT INTO {SCHEMA}."{t}" SELECT * FROM {SCHEMA}."{copy_name}"')
        finally:
            await conn.execute("SET session_replication_role = DEFAULT")
    finally:
        await conn.close()


def _redirect_for(url):
    """A do_connect listener that opens the lane's connection itself, from a
    copy of the engine's connect parameters, and returns it. SQLAlchemy
    hands every listener the engine's own parameter dict, made once per
    engine, so an edit in place outlives the listener's removal: the
    lane's search_path, written there, stayed on database.py's engines for
    every later module in the process, whose tables then resolved in a
    schema their database does not have (build notes, FINDING 10). This
    listener writes nothing to that dict."""
    def redirect(dialect, conn_rec, cargs, cparams):
        params = dict(cparams, host=url.host, port=url.port, user=url.username, database=url.database)
        if url.password:
            params["password"] = url.password
        else:
            params.pop("password", None)
        params["server_settings"] = dict(params.get("server_settings") or {}, search_path=SCHEMA)
        return dialect.connect(*cargs, **params)
    return redirect


# -- the server environment ------------------------------------------------------

def _portrait_png(seed: int, *, noisy: bool = False, radius: int = 330) -> bytes:
    """A valid 1180x1180 straight-alpha RGBA upload: an opaque disc (coverage
    ~0.25) on transparency; `noisy` fills the disc with per-pixel noise."""
    from PIL import Image, ImageDraw
    size = 1180
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rnd = __import__("random").Random(seed)
    colour = (rnd.randrange(40, 255), rnd.randrange(40, 255), rnd.randrange(40, 255), 255)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((size // 2 - radius, size // 2 - radius, size // 2 + radius, size // 2 + radius),
                                 fill=255)
    if noisy:
        raw = bytearray(rnd.randbytes(size * size * 4))
        raw[3::4] = b"\xff" * (size * size)
        fill = Image.frombytes("RGBA", (size, size), bytes(raw))
    else:
        fill = Image.new("RGBA", (size, size), colour)
    img.paste(fill, (0, 0), mask)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


DESCRIPTOR = "v1|face=1000:1002:1004:1005|off=0,0;0,0;0,0;0,0|color=:|effect=|skin=0|anim=1|g=1.2.3|r=1"


class Env:
    """database.py's engines redirected to the lane database and bound to
    SCHEMA; a fresh case state there; the api's secrets, caches, gates and
    pacing windows made the case's own; the face cache in a pytest directory."""

    def __init__(self, monkeypatch, tmp_path, dsn, *, record_app_sql=False):
        self.mp = monkeypatch
        self.tmp = Path(tmp_path)
        self.dsn = dsn
        self.record_app_sql = record_app_sql

    async def __aenter__(self):
        import database
        import main
        self.database, self.main = database, main
        self.url = make_url(self.dsn)
        self.sent = []
        self.info = await ensure_schema(self.url, self.sent)
        await reset_schema(self.url, self.sent, self.info)
        assert_census_first(self.sent)
        self.seed = create_async_engine(self.dsn, pool_size=2, max_overflow=4,
                                        connect_args={"server_settings": {"search_path": SCHEMA}},
                                        execution_options={"schema_translate_map": {None: SCHEMA}})
        mp = self.mp
        mp.setenv("API_SECRET_KEY", INTERNAL_KEY)
        mp.delenv("STEAM_WEB_API_KEY", raising=False)
        mp.setattr(main, "MATCH_HMAC_SECRET", MOD_SECRET)
        mp.setattr(main, "ADMIN_HMAC_SECRET", ADMIN_SECRET)
        # A healthy box (test_pc_routes.py's own precedent): this machine's
        # Pillow lays text out with the basic engine; row 20 drives the gate.
        mp.setattr(main, "_pc_raqm", lambda: True)
        self.faces_root = self.tmp / "faces"
        self.faces_root.mkdir(parents=True, exist_ok=True)
        mp.setattr(main, "_pc_face_cache", main._pcp.FaceCache(str(self.faces_root)))
        mp.setattr(main, "_pc_reveal_windows", {})
        mp.setattr(main, "_pc_composite_gate",
                   main._PcCompositeGate(main._PC_COMPOSITE_SLOTS, main._PC_COMPOSITE_QUEUE_DEPTH))
        mp.setattr(main, "_rank_colors_cache", {"at": 0.0, "ok": False, "map": {}})
        mp.setattr(main, "_service_player_uuid_cache", None)
        mp.setattr(main, "_RL_BUCKETS", main._rl_defaultdict(main._rl_deque))
        for name in ("_RL_GLOBAL", "_RL_SENSITIVE", "_RL_PC", "_RL_PC_UPLOAD", "_RL_FACE"):
            mp.setattr(main, name, (100000, 10.0))
        mp.setitem(main._pc.PC_ECONOMY, "paid_packs_per_day", 1000)
        mp.setattr(main, "_PC_CARD_THEMES", {})
        self.prime_calls, self.prerender_calls = [], []

        async def _prime(subject_ids, *a, **k):
            self.prime_calls.append(list(subject_ids or []))

        def _prerender(print_ids, locale):
            self.prerender_calls.append((list(print_ids or []), locale))

        mp.setattr(main, "_pc_steam_prime", _prime)
        mp.setattr(main, "_pc_schedule_prerender", _prerender)
        self._plans = []
        self._real_roll = main._pc_roll_prints
        mp.setattr(main, "_pc_roll_prints", self._scripted_roll)
        self.app_sql = []
        self._redirect = _redirect_for(self.url)
        self._engines = (database.engine, database.release_engine)
        for eng in self._engines:
            await eng.dispose(close=False)
            event.listen(eng.sync_engine, "do_connect", self._redirect)
            if self.record_app_sql:
                event.listen(eng.sync_engine, "before_cursor_execute", self._record_app)
        async with database.async_session() as db:
            await main._pc_load_card_themes(db)
        assert main._PC_CARD_THEMES, "the seeded pc_card_themes did not load"
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
                                        base_url=BASE_URL, timeout=120.0)
        self._n = 0
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()
        for eng in self._engines:
            await eng.dispose()
            event.remove(eng.sync_engine, "do_connect", self._redirect)
            if self.record_app_sql:
                event.remove(eng.sync_engine, "before_cursor_execute", self._record_app)
        await self.seed.dispose()
        return False

    def _record_app(self, conn, cursor, statement, parameters, context, executemany):
        self.app_sql.append(statement)

    # -- the one substitution: which pool member each slot deals ---------------

    def plan(self, slots):
        """Queue one pack's deal: [(subject, foil, signed), ...] in slot order."""
        self._plans.append([(str(s.id if hasattr(s, "id") else s), bool(f), bool(g)) for s, f, g in slots])

    async def _scripted_roll(self, db, snap_id, owner_pid, rng=None):
        """The production roll with the deal scripted: each planned subject's
        member row of this snapshot, then the SAME subject hold and live-pool
        re-check the production roll applies per slot. With no plan queued,
        the production roll itself."""
        main = self.main
        if not self._plans:
            return await self._real_roll(db, snap_id, owner_pid, rng)
        plan = self._plans.pop(0)
        prints = []
        for slot, (pid, foil, signed) in enumerate(plan, 1):
            member = (await db.execute(text(
                f"SELECT m.player_id, m.pool_rank, m.rarity, m.rating, m.peak_rating, m.board_rank,"
                f" m.series_wins, m.series_losses, m.top_card, m.title FROM {SCHEMA}.pc_pool_members m"
                " WHERE m.snapshot_id = CAST(:sid AS integer) AND m.player_id = CAST(:pid AS uuid)"),
                {"sid": snap_id, "pid": pid})).mappings().first()
            if member is None:
                return None, "pool_changed"
            held = (await db.execute(text(main._PC_SUBJECT_HOLD_SQL), {"pid": pid})).scalar_one_or_none()
            live = (await db.execute(text(main._PC_LIVE_POOL_CHECK_SQL), {"pid": pid})).first()
            if not held or live is None:
                return None, "pool_changed"
            prints.append({
                "slot": slot, "rolled": member["rarity"], "player_id": pid,
                "pool_rank": int(member["pool_rank"]), "rarity": member["rarity"],
                "rating": main._pc_num(member["rating"]), "peak_rating": main._pc_num(member["peak_rating"]),
                "board_rank": int(member["board_rank"]) if member["board_rank"] is not None else None,
                "series_wins": int(member["series_wins"] or 0), "series_losses": int(member["series_losses"] or 0),
                "top_card": member["top_card"], "title": member["title"], "foil": foil, "signed": signed,
            })
        return prints, None

    # -- statements this harness writes itself (every one names SCHEMA) --------

    async def ex(self, sql, params=None):
        async with self.seed.begin() as conn:
            await conn.execute(text(sql), params or {})

    async def rows(self, sql, params=None):
        async with self.seed.connect() as conn:
            return [dict(r) for r in (await conn.execute(text(sql), params or {})).mappings().all()]

    async def val(self, sql, params=None):
        async with self.seed.connect() as conn:
            return (await conn.execute(text(sql), params or {})).scalar()

    # -- fixtures ------------------------------------------------------------

    async def player(self, tag, *, rating=1500.0, discord=True, public=True, shards=10000, name=None,
                     steam=None, mod_seen=True, username=None):
        """One live player: a synthetic SteamID64, a Glicko row (unless
        rating is None), a verified Steam session, optionally a Discord id."""
        import models
        self._n += 1
        n = self._n
        sid = steam if steam is not None else steam_of(n)
        did = discord_of(n) if discord is True else (discord or None)
        disp = name or f"Fixture {tag}"
        async with AsyncSession(self.seed) as s:
            p = models.Player(steam_id=sid, display_name=disp, discord_id=did, discord_username=username,
                              pc_collection_public=bool(public), pc_shards=int(shards))
            s.add(p)
            await s.flush()
            pid = p.id
            if rating is not None:
                s.add(models.GlickoRating(player_id=pid, rating=float(rating), peak_rating=float(rating)))
            await s.commit()
        if mod_seen:
            await self.ex(f"UPDATE {SCHEMA}.players SET mod_seen_at = now() WHERE id = CAST(:p AS uuid)",
                          {"p": str(pid)})
        token = secrets.token_hex(24)
        await self.ex(f"INSERT INTO {SCHEMA}.steam_sessions (steam_id, token_hash, verified, issued_at, expires_at)"
                      " VALUES (:s, :h, true, now(), now() + interval '1 day')",
                      {"s": sid, "h": hashlib.sha256(token.encode()).hexdigest()})
        return SimpleNamespace(tag=tag, id=str(pid), steam=sid, discord=did, name=disp, token=token)

    async def snapshot(self):
        async with self.database.async_session() as db:
            out = await self.main._pc_take_snapshot(db, reason="dc-reveal fixture")
            await db.commit()
        return out["snapshot_id"]

    def mod_headers(self, who=None):
        h = {"X-Mod-Version": self.main.LATEST_MOD_VERSION}
        if who is not None:
            h["X-Session-Token"] = who.token
        return h

    async def open_pack(self, owner, slots):
        """A bought pack through the production open route, its deal
        scripted: slots = [subject | (subject, foil, signed), ...]."""
        self.plan([(s, False, False) if not isinstance(s, tuple) else s for s in slots])
        nonce = secrets.token_hex(8)
        price = int(self.main._pc.PC_ECONOMY["pack_price_shards"])
        canon = self.main._pc.canon_open_purchase(owner.steam, nonce, "shards", price)
        r = await self.client.post("/api/v1/pc/packs/open", headers=self.mod_headers(owner), params={
            "steam_id": owner.steam, "sig": mod_sig(canon), "nonce": nonce, "pay": "shards",
            "expected_price": price})
        assert r.status_code == 200, (r.status_code, r.text[:400])
        return r.json()["pack_id"]

    async def pack_prints(self, pack_id):
        return await self.rows(
            f"SELECT pr.id::text AS print_id, pr.slot AS slot, c.subject_player_id::text AS subject,"
            f" pr.rarity, pr.foil, pr.signed, pr.discarded_at FROM {SCHEMA}.pc_prints pr"
            f" JOIN {SCHEMA}.pc_cards c ON c.id = pr.card_id"
            " WHERE pr.pack_id = CAST(:p AS uuid) ORDER BY pr.slot", {"p": pack_id})

    async def discard(self, owner, print_id):
        canon = self.main._pc.canon_discard(owner.steam, print_id)
        r = await self.client.post("/api/v1/pc/prints/discard", headers=self.mod_headers(owner), params={
            "steam_id": owner.steam, "sig": mod_sig(canon), "print_id": print_id})
        assert r.status_code == 200, (r.status_code, r.text[:300])
        return r.json()

    async def set_public(self, who, value):
        rev = await self.val(f"SELECT pc_settings_revision FROM {SCHEMA}.players WHERE id = CAST(:p AS uuid)",
                             {"p": who.id})
        nonce = secrets.token_hex(8)
        canon = self.main._pc.canon_settings(who.steam, nonce, int(rev), "collection_public", int(bool(value)))
        r = await self.client.post("/api/v1/pc/settings", headers=self.mod_headers(who), params={
            "steam_id": who.steam, "sig": mod_sig(canon), "nonce": nonce, "revision": int(rev),
            "key": "collection_public", "value": int(bool(value))})
        assert r.status_code == 200, (r.status_code, r.text[:300])
        return r.json()

    async def rename(self, who, new_name):
        """The production rename writer: the ranked-toggle sync that follows a
        Steam rename, with its own name signature."""
        r = await self.client.post(f"/api/v1/mod/toggle-ranked/{who.steam}", headers=self.mod_headers(who), params={
            "enabled": "true", "sig": mod_sig(f"toggle-ranked:{who.steam}:true"),
            "display_name": new_name, "name_sig": mod_sig(f"toggle-ranked-name:{who.steam}:{new_name}")})
        assert r.status_code == 200, (r.status_code, r.text[:300])
        got = await self.val(f"SELECT display_name FROM {SCHEMA}.players WHERE id = CAST(:p AS uuid)", {"p": who.id})
        assert got == new_name, got
        who.name = new_name

    async def rebind(self, discord_id, to):
        """Move a Discord id to player `to` through the production link
        route; the code is the one fixture row, as the in-game !link issues."""
        code = secrets.token_hex(3).upper()[:6]
        await self.ex(f"DELETE FROM {SCHEMA}.link_codes WHERE player_id = CAST(:p AS uuid)", {"p": to.id})
        await self.ex(f"INSERT INTO {SCHEMA}.link_codes (player_id, code, expires_at, created_at)"
                      " VALUES (CAST(:p AS uuid), :c, now() + interval '10 minutes', now())", {"p": to.id, "c": code})
        r = await self.client.post("/api/v1/players/link-discord", headers={"X-Internal-Key": INTERNAL_KEY},
                                   params={"code": code, "discord_id": str(discord_id)})
        assert r.status_code == 200, (r.status_code, r.text[:300])
        to.discord = str(discord_id)

    async def delete_data(self, who):
        """The production erasure endpoint, HMAC over delete:{steam}."""
        r = await self.client.delete(f"/api/v1/players/{who.steam}/data", headers=self.mod_headers(who),
                                     params={"sig": mod_sig(f"delete:{who.steam}")})
        assert r.status_code == 200 and r.json().get("status") == "anonymized", (r.status_code, r.text[:300])
        return r.json()

    async def admin(self):
        if getattr(self, "_admin", None) is None:
            self._admin = await self.player("admin", rating=None, discord=False, mod_seen=False)
            await self.ex(f"INSERT INTO {SCHEMA}.admin_users (steam_id, granted_at) VALUES (:s, now())",
                          {"s": self._admin.steam})
        return self._admin

    async def ban(self, who):
        """The production ban writer, admin-HMAC signed."""
        adm = await self.admin()
        canon = self.main._admin_canonical(adm.steam, "ban", who.steam)
        sig = hmac.new(ADMIN_SECRET.encode(), canon.encode(), hashlib.sha256).hexdigest()
        r = await self.client.post("/api/v1/admin/ban", headers=self.mod_headers(adm), json={
            "admin_steam_id": adm.steam, "target_steam_id": who.steam, "reason": "violation",
            "hmac_signature": sig})
        assert r.status_code == 200, (r.status_code, r.text[:300])
        return r.json()

    async def give_portrait(self, who, seed, *, noisy=False, age_s=3600, radius=330):
        """A stored game portrait for `who`, made as the writer makes one:
        the upload canonicalised by pc_face.prepare_portrait, stored under
        the canonical hash, and named on the players row."""
        canonical, info = self.main._pcf.prepare_portrait(_portrait_png(seed, noisy=noisy, radius=radius))
        await self.ex(f"INSERT INTO {SCHEMA}.pc_portraits (hash, bytes, content_type, width, height)"
                      " VALUES (:h, :b, 'image/png', :w, :hh) ON CONFLICT (hash) DO NOTHING",
                      {"h": info["sha256"], "b": canonical, "w": int(info["width"]), "hh": int(info["height"])})
        await self.ex(f"UPDATE {SCHEMA}.players SET pc_game_portrait_hash = :h, pc_game_portrait_descriptor = :d,"
                      " pc_game_portrait_at = now() - make_interval(secs => :age) WHERE id = CAST(:p AS uuid)",
                      {"h": info["sha256"], "d": DESCRIPTOR, "age": float(age_s), "p": who.id})
        return info["sha256"]

    async def upload_portrait(self, who, seed):
        """The production portrait writer (POST /api/v1/pc/portrait)."""
        body = _portrait_png(seed)
        nonce = secrets.token_hex(8)
        canon = self.main._pcp.canon_portrait(who.steam, nonce, hashlib.sha256(body).hexdigest(), DESCRIPTOR)
        headers = dict(self.mod_headers(who))
        headers["Content-Type"] = "image/png"
        r = await self.client.post("/api/v1/pc/portrait", headers=headers, content=body, params={
            "steam_id": who.steam, "sig": mod_sig(canon), "nonce": nonce, "descriptor": DESCRIPTOR})
        assert r.status_code == 200 and r.json().get("applied"), (r.status_code, r.text[:300])
        return r.json()["portrait_hash"]

    # -- the four reveal routes, as the bot calls them --------------------------

    def ihead(self):
        return {"X-Internal-Key": INTERNAL_KEY}

    async def packs_json(self, discord_id, pack_id=None, locale="en", **extra):
        params = {"discord_id": str(discord_id), "locale": locale}
        if pack_id is not None:
            params["pack_id"] = pack_id
        params.update(extra)
        return await self.client.get("/api/v1/internal/pc/packs", headers=self.ihead(), params=params)

    async def strip(self, pack_id, discord_id, locale="en"):
        return await self.client.get(f"/api/v1/internal/pc/packs/{pack_id}/strip/{locale}.png",
                                     headers=self.ihead(), params={"discord_id": str(discord_id)})

    async def binder_json(self, owner_discord, viewer_discord=None, page=1, locale="en"):
        params = {"discord_id": str(owner_discord), "page": int(page), "locale": locale}
        if viewer_discord is not None:
            params["viewer_discord_id"] = str(viewer_discord)
        return await self.client.get("/api/v1/internal/pc/binder", headers=self.ihead(), params=params)

    async def binder_page(self, owner_ref, page, viewer_discord=None, locale="en"):
        params = {} if viewer_discord is None else {"viewer_discord_id": str(viewer_discord)}
        return await self.client.get(f"/api/v1/internal/pc/binder/{owner_ref}/page/{page}/{locale}.png",
                                     headers=self.ihead(), params=params)

    def cache_keys(self, prefix=""):
        out = []
        for p in self.faces_root.rglob("*"):
            if p.is_file():
                rel = p.relative_to(self.faces_root).as_posix()
                if rel.startswith(prefix):
                    out.append(rel)
        return sorted(out)


async def pool(env, n, *, base=2000.0, step=10.0, tag="s", **kw):
    """n live pool players with strictly descending ratings (pool ranks 1..n)."""
    out = []
    for i in range(n):
        out.append(await env.player(f"{tag}{i + 1}", rating=base - step * i, **kw))
    return out


# -- pixels ---------------------------------------------------------------------

def image_of(data: bytes):
    from PIL import Image
    return Image.open(io.BytesIO(data)).convert("RGB")


def slot_rect(slot: int, cols: int = 5):
    """The paste box of grid position `slot` (1-based): design S4's formula."""
    c = (slot - 1) % cols + 1
    r = (slot - 1) // cols + 1
    x, y = 12 + (c - 1) * 387, 12 + (r - 1) * 537
    return (x, y, x + 375, y + 525)


def same_pixels(a, b) -> bool:
    from PIL import ImageChops
    return ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is None


# -- the bot, lifted ---------------------------------------------------------------

REVEAL_FUNCS = frozenset({
    "_pc_reveal_hex32", "_pc_reveal_cooldown", "_pc_reveal_say", "_pc_reveal_prints", "_pc_reveal_view",
    "_pc_reveal_drawn", "_pc_reveal_moved", "_pc_reveal_manifest", "_pc_reveal_expected",
    "_pc_reveal_check", "_pc_reveal_bytes", "_pc_reveal_revalidate", "_pc_reveal_compose",
    "_pc_reveal_pack_text", "_pc_reveal_binder_text", "_pc_reveal_run", "_pc_reveal_refusal",
    "_pc_reveal_unposted", "_pc_reveal_pack", "_pc_reveal_pack_run", "_pc_reveal_binder", "cmd_pc_pack",
    "cmd_pc_binder",
    "_pc_lease", "_pc_lease_left", "_pc_lease_live", "_pc_lease_release", "_pc_lease_release_all",
    "_pc_leases", "_pc_detail", "_pc_name", "_pc_print_line", "_pc_fit_field", "_pc_when",
    "_pc_api", "_pc_api_bytes", "_pc_not_linked", "_maybe_defer", "_pc_locale_of",
})
REVEAL_ASSIGNS = frozenset({
    "_PC_COMPOSITE_MAX_BYTES", "_PC_COMPOSITE_RETRIES", "_PC_COMPOSITE_WAIT_CAP_S", "_PC_REVEAL_SPAN_S",
    "_PC_REVEAL_SEND_S", "_PC_DRAWN_MEMBERS", "_PC_VIEW_MEMBERS", "_PC_REVEAL_BACK_REASONS",
    "_PC_REVEAL_COOLDOWN_S", "_pc_reveal_last", "_PC_REVEAL_NOTES", "_PC_COMPOSITE_RETRYABLE",
    "_PC_LEASE_RESERVE_S", "_PC_RARITY_EMOJI", "_PC_FACE_MAX_BYTES", "_PC_LINK_HINT",
})


def bot_source() -> str:
    return BOT_PATH.read_text(encoding="utf-8")


def lift(funcs, assigns, source=None):
    """The named top-level functions (decorators stripped) and assignments
    of discord_bot.py, as one module AST, in file order."""
    tree = ast.parse(source if source is not None else bot_source())
    picked, seen = [], set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in assigns:
                    picked.append(node)
                    seen.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in assigns:
            picked.append(node)
            seen.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in funcs:
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            picked.append(fn)
            seen.add(node.name)
    missing = (set(funcs) | set(assigns)) - seen
    assert not missing, f"not found at top level of discord_bot.py: {sorted(missing)}"
    return ast.Module(body=picked, type_ignores=[])


class Clock:
    """The bot's monotonic clock: it moves only when a stub, a sleep or the
    loop's own modelled work spends time. `pending` is work charged at the
    next reading."""

    def __init__(self, start=1000.0):
        self.now = float(start)
        self.pending = 0.0

    def monotonic(self):
        if self.pending:
            self.now += self.pending
            self.pending = 0.0
        return self.now

    def advance(self, s):
        self.now += float(s)


class Reply:
    """An answer the fake transport returns: status, headers, body and the
    time it takes to arrive."""

    def __init__(self, status=200, body=b"", headers=None, delay=0.0, json=None):
        if json is not None:
            body = _json.dumps(json).encode()
            headers = dict(headers or {})
            headers.setdefault("content-type", "application/json")
        self.status = int(status)
        self.body = bytes(body)
        self.headers = httpx.Headers(headers or {})
        if "content-length" not in self.headers:
            self.headers["content-length"] = str(len(self.body))
        self.delay = float(delay)


class _Stream:
    def __init__(self, body):
        self._body = body
        self._at = 0

    async def readexactly(self, n):
        if self._at + n > len(self._body):
            partial = self._body[self._at:]
            self._at = len(self._body)
            raise asyncio.IncompleteReadError(partial, n)
        out = self._body[self._at:self._at + n]
        self._at += n
        return out

    async def read(self, n=-1):
        if n is None or n < 0:
            out, self._at = self._body[self._at:], len(self._body)
            return out
        out = self._body[self._at:self._at + n]
        self._at += len(out)
        return out


class _Response:
    def __init__(self, reply):
        self.status = reply.status
        self.headers = reply.headers
        self._body = reply.body
        self.content = _Stream(reply.body)

    async def json(self, content_type=None):
        return _json.loads(self._body.decode("utf-8"))

    async def text(self):
        return self._body.decode("utf-8", "replace")


class _Call:
    def __init__(self, rig, method, url, kw):
        self.rig, self.method, self.url, self.kw = rig, method, url, kw

    async def __aenter__(self):
        return await self.rig._dispatch(self.method, self.url, self.kw)

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, rig):
        self.rig = rig

    def get(self, url, **kw):
        return _Call(self.rig, "GET", url, kw)

    def post(self, url, **kw):
        return _Call(self.rig, "POST", url, kw)

    def delete(self, url, **kw):
        return _Call(self.rig, "DELETE", url, kw)


class Sent(SimpleNamespace):
    pass


class _File:
    def __init__(self, fp, filename=None, **kw):
        self.data = fp.getvalue() if hasattr(fp, "getvalue") else fp.read()
        self.filename = filename


class _HTTPException(Exception):
    def __init__(self, status=400, text="refused"):
        super().__init__(f"HTTP {status}: {text}")
        self.status = status


class BotRig:
    """discord_bot.py's reveal path, lifted, over a fake gateway and a fake
    HTTP session. `handler(call)` answers each request with a Reply (or
    raises); a Reply whose delay exceeds the request's own ClientTimeout
    total is cut short at that total and raises asyncio.TimeoutError, as
    aiohttp's timer does; a total that is not above zero arms no timer."""

    def __init__(self, handler, *, funcs=REVEAL_FUNCS, assigns=REVEAL_ASSIGNS, clock=None, source=None,
                 extra=None):
        self.handler = handler
        self.clock = clock or Clock()
        self.calls = []
        self.sent = []
        self.logs = []
        self.sleeps = []
        self.defers = []
        rig = self
        fake_asyncio = SimpleNamespace(**{k: getattr(asyncio, k) for k in dir(asyncio) if not k.startswith("_")})

        async def _sleep(s, *a, **k):
            rig.sleeps.append(float(s))
            rig.clock.advance(float(s))
            await asyncio.sleep(0)
        fake_asyncio.sleep = _sleep
        fake_time = SimpleNamespace(**{k: getattr(_time, k) for k in dir(_time) if not k.startswith("_")})
        fake_time.monotonic = self.clock.monotonic
        discord = SimpleNamespace(
            Member=SimpleNamespace, File=_File, HTTPException=_HTTPException, Forbidden=_HTTPException,
            AllowedMentions=SimpleNamespace(none=lambda: "none"),
            utils=SimpleNamespace(escape_markdown=lambda s, **k: str(s)))
        from datetime import datetime, timezone
        ns = {"__builtins__": __builtins__, "__name__": "dc_reveal_bot",
              "asyncio": fake_asyncio, "time": fake_time, "io": io, "re": re, "json": _json,
              "datetime": datetime, "timezone": timezone, "discord": discord, "threading": threading,
              "aiohttp": SimpleNamespace(ClientTimeout=lambda total=None, **k: SimpleNamespace(total=total)),
              "http_session": _Session(self), "API_BASE_URL": BASE_URL, "API_SECRET_KEY": INTERNAL_KEY,
              "print": self._print}
        if extra:
            ns.update(extra)
        exec(compile(lift(funcs, assigns, source), str(BOT_PATH), "exec"), ns)
        self.ns = ns

    def _print(self, *args, **kw):
        line = " ".join(str(a) for a in args)
        self.logs.append(line)

    async def _dispatch(self, method, url, kw):
        path = url[len(BASE_URL) + len("/api/v1"):] if url.startswith(BASE_URL) else url
        timeout = kw.get("timeout")
        total = getattr(timeout, "total", None)
        call = SimpleNamespace(method=method, path=path, params=dict(kw.get("params") or {}),
                               payload=kw.get("json"), total=total, t_start=self.clock.monotonic(),
                               t_end=None, status=None, n=sum(1 for c in self.calls if c.path == path) + 1)
        self.calls.append(call)
        reply = await self.handler(call)
        if total is not None and total > 0 and reply.delay > total:
            self.clock.advance(total)
            call.t_end = self.clock.now
            call.status = 0
            raise asyncio.TimeoutError()
        self.clock.advance(reply.delay)
        call.t_end = self.clock.now
        call.status = reply.status
        return _Response(reply)

    def ctx(self, uid, *, name="viewer", slash=False, locale="en"):
        rig = self

        async def send(content=None, **kw):
            rig.sent.append(Sent(content=content, file=kw.get("file"), ephemeral=bool(kw.get("ephemeral")),
                                 kw={k: v for k, v in kw.items() if k not in ("file",)}))

        async def defer(**kw):
            rig.defers.append(kw)
        interaction = SimpleNamespace(locale=locale) if slash else None
        author = SimpleNamespace(id=int(uid), name=name, display_name=name, mention=f"<@{uid}>")
        return SimpleNamespace(author=author, send=send, defer=defer, interaction=interaction, guild=None)

    def member(self, uid, name="member"):
        return SimpleNamespace(id=int(uid), name=name, display_name=name, mention=f"<@{uid}>")

    async def pack(self, ctx, index=1, private=False):
        await self.ns["cmd_pc_pack"](ctx, index, private)

    async def binder(self, ctx, member=None, page=1):
        await self.ns["cmd_pc_binder"](ctx, member, page)

    def attachments(self):
        return [s for s in self.sent if s.file is not None]

    def texts(self):
        return [s.content or "" for s in self.sent]

    def acquires(self):
        return [c for c in self.calls if c.method == "POST" and c.path == "/internal/pc/lease"]

    def releases(self):
        return [c for c in self.calls if c.method == "DELETE" and c.path.startswith("/internal/pc/lease/")]

    def byte_gets(self):
        return [c for c in self.calls if c.method == "GET" and c.path.endswith(".png")]


def asgi_handler(env, hooks=None):
    """The rig's transport over the real app: every request forwarded to
    main.app with the internal key the bot's session carries. `hooks` is a
    list of (predicate(call), coroutine function(call)) run BEFORE the
    matching request is forwarded, each once."""
    hooks = list(hooks or [])

    async def handler(call):
        for i, (pred, fn) in enumerate(list(hooks)):
            if pred(call):
                hooks.remove((pred, fn))
                await fn(call)
                break
        r = await env.client.request(call.method, "/api/v1" + call.path, params=call.params or None,
                                     json=call.payload, headers={"X-Internal-Key": INTERNAL_KEY})
        headers = {k: v for k, v in r.headers.items()}
        return Reply(r.status_code, r.content, headers)
    return handler
