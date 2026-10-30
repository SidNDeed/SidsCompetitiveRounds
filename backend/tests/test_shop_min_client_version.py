"""The per-item minimum client version (migration 397, shop_items.min_client_version),
honoured by every surface that can put an item in a player's hands.

A face bundled into client X cannot be equipped by an older admitted client:
its Catalog has no definition for it. So once such an item is published, the
server must keep it out of an older client's reach -- not by a release note,
by the four routes that list or transfer it:

  * GET /shop/items and GET /shop/newest omit an item whose minimum is above
    the caller's X-Mod-Version (missing or unparseable version: omitted);
  * POST /shop/purchase refuses such a caller before any gold moves;
  * POST /artist/gift refuses unless the RECIPIENT's last-seen mod version
    (players.mod_version) is at or above the minimum; a recipient with no
    recorded version is refused.

Static half (always runs): the helper's decisions, the model column, each
route consulting the helper exactly once, and 397's transaction shape.

Live half (A1_TEST_PG_DSN, the gate test_release_faces_398.py uses):

    A1_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:55432/a1test" \\
        python -m pytest backend/tests/test_shop_min_client_version.py

Each case builds its own schema from the ORM metadata, calls the real route
functions against it, and drops the schema afterwards.
"""
import ast
import asyncio
import os
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
API = ROOT / "backend" / "api"
SQL = ROOT / "backend" / "sql"
MAIN_PY = API / "main.py"
MIGRATION = SQL / "397_shop_item_min_client_version.sql"
ROLLBACK = SQL / "rollback_397_shop_item_min_client_version.sql"

sys.path.insert(0, str(API))

import main  # noqa: E402
import models  # noqa: E402
from fastapi import HTTPException  # noqa: E402

DSN = os.environ.get("A1_TEST_PG_DSN")
live = pytest.mark.skipif(not DSN, reason="A1_TEST_PG_DSN unset; live-Postgres route check")

FLOORED = "face_detail_orbit"
HOUSE = "title_house_plain"
ARTIST = "76561190000000001"
BUYER = "76561190000000002"
R_OLD = "76561190000000003"
R_NONE = "76561190000000004"
R_NEW = "76561190000000005"
NEUTRAL = "requires a newer mod version"


# ---------------------------------------------------------------- static

def test_the_floor_helper_decides_by_version_not_by_string():
    meets = main._client_meets_item_floor
    v = main._music_strict_version
    assert meets(None, None) is True                       # no floor: everyone
    assert meets(None, v("1.40.3")) is True
    assert meets("1.41.0", v("1.40.3")) is False
    assert meets("1.41.0", v("1.41.0")) is True
    assert meets("1.41.0", v("1.41.1")) is True
    assert meets("1.41.0", v("1.100.0")) is True            # a string compare says False
    assert meets("1.9.0", v("1.10.0")) is True              # a string compare says False
    assert meets("1.41.0", None) is False                   # unknown caller: refused
    assert meets("TBD", v("9.9.9")) is False                # unparseable floor: closed
    assert meets("0", v("9.9.9")) is False                  # all-zero floor: closed


def test_the_caller_version_comes_from_the_header_then_the_middleware():
    req = types.SimpleNamespace(headers={"X-Mod-Version": "1.41.0"})
    assert main._shop_caller_version(req) == (1, 41, 0)
    token = main._current_mod_version.set("1.40.3")
    try:
        assert main._shop_caller_version(types.SimpleNamespace(headers={})) == (1, 40, 3)
        assert main._shop_caller_version(None) == (1, 40, 3)
    finally:
        main._current_mod_version.reset(token)
    assert main._shop_caller_version(types.SimpleNamespace(headers={})) is None
    assert main._shop_caller_version(
        types.SimpleNamespace(headers={"X-Mod-Version": "1.41.0-beta"})) is None


def test_the_model_declares_the_column():
    col = models.ShopItem.__table__.c.get("min_client_version")
    assert col is not None and col.nullable


def _function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


@pytest.mark.parametrize("route", ["list_shop_items", "newest_shop_items",
                                   "purchase_item", "artist_gift"])
def test_every_listing_and_transfer_route_consults_the_floor_once(route):
    fn = _function(ast.parse(MAIN_PY.read_text(encoding="utf-8")), route)
    assert fn is not None, route
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "_client_meets_item_floor"]
    assert len(calls) == 1, (route, len(calls))


def test_397_house_shape():
    for path in (MIGRATION, ROLLBACK):
        lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.strip().startswith("--")]
        assert lines[:5] == [
            "BEGIN;",
            "SET LOCAL lock_timeout = '5s';",
            "SET LOCAL idle_in_transaction_session_timeout = '5s';",
            "SET LOCAL statement_timeout = '25s';",
            "SET LOCAL synchronous_commit = local;",
        ], path.name
        assert lines[5].startswith("DO $"), path.name
        assert lines[-1] == "COMMIT;", path.name
        assert sum(1 for l in lines if l.startswith("DO $")) == 1, path.name


# ---------------------------------------------------------------- live: 397

def _pg_dsn():
    return DSN.replace("+asyncpg", "")


async def _in_schema(name, body):
    import asyncpg
    conn = await asyncpg.connect(_pg_dsn())
    try:
        await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % name)
        await conn.execute('CREATE SCHEMA "%s"' % name)
        await conn.execute('SET search_path TO "%s"' % name)
        return await body(conn)
    finally:
        try:
            await conn.execute("ROLLBACK")
        except Exception:
            pass
        await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % name)
        await conn.close()


BARE_SHOP = """
CREATE TABLE shop_items (
    id BIGINT PRIMARY KEY, sku VARCHAR(64) UNIQUE NOT NULL, kind VARCHAR(16) NOT NULL,
    name VARCHAR(128) NOT NULL, description VARCHAR(256), price INTEGER NOT NULL,
    catalog_ready BOOLEAN NOT NULL DEFAULT TRUE);
INSERT INTO shop_items VALUES (1, 'face_detail_orbit', 'face', 'Orbit', NULL, 750, FALSE);
"""


@live
def test_397_adds_the_column_and_the_provenance_table_and_reruns_as_a_no_op():
    async def body(conn):
        await conn.execute(BARE_SHOP)
        sql = MIGRATION.read_text(encoding="utf-8")
        await conn.execute(sql)
        await conn.execute(sql)                                   # rerun
        got = await conn.fetchval(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = 'shop_items'::regclass AND attname = 'min_client_version' "
            "AND NOT attisdropped")
        assert got == "character varying(16)"
        assert await conn.fetchval("SELECT min_client_version FROM shop_items") is None
        assert await conn.fetchval(
            "SELECT to_regclass('shop_item_release_provenance') IS NOT NULL")
        await conn.execute("UPDATE shop_items SET min_client_version = '1.41.0'")
        with pytest.raises(Exception) as ei:                       # CHECK: dotted numbers only
            await conn.execute("UPDATE shop_items SET min_client_version = '1.41.0-beta'")
        assert "min_client_version" in str(ei.value)
    asyncio.run(_in_schema("t397_apply", body))


@live
def test_397_post_check_refuses_a_same_named_column_of_another_type():
    async def body(conn):
        await conn.execute(BARE_SHOP)
        await conn.execute("ALTER TABLE shop_items ADD COLUMN min_client_version INTEGER")
        sql = MIGRATION.read_text(encoding="utf-8")       # outside the raises block
        with pytest.raises(Exception) as ei:
            await conn.execute(sql)
        assert "397" in str(ei.value) and "min_client_version" in str(ei.value)
    asyncio.run(_in_schema("t397_wrongtype", body))


@live
def test_397_rollback_refuses_while_a_floor_or_provenance_is_held_then_drops():
    async def body(conn):
        await conn.execute(BARE_SHOP)
        await conn.execute(MIGRATION.read_text(encoding="utf-8"))
        rb = ROLLBACK.read_text(encoding="utf-8")
        await conn.execute("UPDATE shop_items SET min_client_version = '1.41.0'")
        with pytest.raises(Exception) as ei:
            await conn.execute(rb)
        assert "rollback 397" in str(ei.value) and "min_client_version" in str(ei.value)
        await conn.execute("ROLLBACK")
        await conn.execute("UPDATE shop_items SET min_client_version = NULL")
        await conn.execute(
            "INSERT INTO shop_item_release_provenance (migration, shop_item_id, submission_id,"
            " released_at, published_revision) VALUES ('398', 1, 70, now(), 1)")
        with pytest.raises(Exception) as ei:
            await conn.execute(rb)
        assert "rollback 397" in str(ei.value) and "provenance" in str(ei.value)
        await conn.execute("ROLLBACK")
        await conn.execute("DELETE FROM shop_item_release_provenance")
        await conn.execute(rb)
        await conn.execute(rb)                                    # rerun: no-op
        assert await conn.fetchval(
            "SELECT count(*) FROM pg_attribute WHERE attrelid = 'shop_items'::regclass "
            "AND attname = 'min_client_version' AND NOT attisdropped") == 0
        assert await conn.fetchval(
            "SELECT to_regclass('shop_item_release_provenance') IS NULL")
    asyncio.run(_in_schema("t397_rollback", body))


# ---------------------------------------------------------------- live: routes

_FILL_DEFAULTS = """
DO $fill$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT table_name AS t, column_name AS c, data_type AS d
             FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND is_nullable = 'NO' AND column_default IS NULL
  LOOP
    EXECUTE format('ALTER TABLE %I ALTER COLUMN %I SET DEFAULT %s', r.t, r.c,
      CASE WHEN r.d LIKE 'timestamp%' THEN 'NOW()'
           WHEN r.d = 'boolean' THEN 'FALSE'
           WHEN r.d IN ('integer','bigint','smallint','numeric','double precision','real') THEN '0'
           WHEN r.d = 'uuid' THEN 'gen_random_uuid()'
           WHEN r.d = 'ARRAY' THEN quote_literal('{}')
           ELSE quote_literal('') END);
  END LOOP;
END $fill$;
"""

# The columns the gift's raw INSERT names and the ORM deliberately omits (#346).
_ROYALTY = """
ALTER TABLE player_items
    ADD COLUMN IF NOT EXISTS royalty_paid INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS royalty_rate_pct INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS royalty_artist_steam_id TEXT,
    ADD COLUMN IF NOT EXISTS royalty_resolved BOOLEAN NOT NULL DEFAULT FALSE;
"""


def _request(version):
    headers = {"X-Mod-Version": version} if version else {}
    return types.SimpleNamespace(headers=headers,
                                 state=types.SimpleNamespace(mod_version=version))


async def _routes(schema, body):
    import asyncpg
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    conn = await asyncpg.connect(_pg_dsn())
    try:
        await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
        await conn.execute('CREATE SCHEMA "%s"' % schema)
    finally:
        await conn.close()
    engine = create_async_engine(
        "postgresql+asyncpg://" + _pg_dsn().split("://", 1)[1],
        connect_args={"server_settings": {"search_path": schema}})
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as c:
            await c.run_sync(models.Base.metadata.create_all,
                             tables=[models.Player.__table__,
                                     models.ShopItem.__table__,
                                     models.PlayerItem.__table__])
        conn = await asyncpg.connect(_pg_dsn())
        try:
            await conn.execute('SET search_path TO "%s"' % schema)
            # The column 397 adds; IF NOT EXISTS because the model declares it.
            await conn.execute("ALTER TABLE shop_items ADD COLUMN IF NOT EXISTS "
                               "min_client_version VARCHAR(16)")
            await conn.execute(_FILL_DEFAULTS)
            await conn.execute(_ROYALTY)
            await conn.execute("CREATE TABLE artist_item_blocks (artist_steam_id TEXT,"
                               " blocked_steam_id TEXT)")
            await conn.execute(
                "INSERT INTO shop_items (sku, kind, name, description, price, rarity,"
                " catalog_ready, stock_limit, artist_steam_id, min_client_version, released_at)"
                " VALUES ($1, 'face', 'Orbit', 'd', 750, 'rare', TRUE, -1, $2, '1.41.0', now()),"
                "        ($3, 'title', 'Plain', 'd', 10, 'common', TRUE, NULL, NULL, NULL, now())",
                FLOORED, ARTIST, HOUSE)
            for sid, ver in ((ARTIST, "1.41.0"), (BUYER, "1.40.3"), (R_OLD, "1.40.3"),
                             (R_NONE, None), (R_NEW, "1.41.0")):
                await conn.execute(
                    "INSERT INTO players (steam_id, display_name, mod_version, gold_earned)"
                    " VALUES ($1, $1, $2, 100000)", sid, ver)
        finally:
            await conn.close()
        async with session() as db:
            return await body(db)
    finally:
        await engine.dispose()
        conn = await asyncpg.connect(_pg_dsn())
        try:
            await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
        finally:
            await conn.close()


async def _listed(db, version):
    token = main._current_mod_version.set(version)
    try:
        items = (await main.list_shop_items(request=_request(version), steam_id=None, db=db))["items"]
        newest = (await main.newest_shop_items(request=_request(version), limit=24,
                                               batches=0, db=db))["items"]
    finally:
        main._current_mod_version.reset(token)
    return {i["sku"] for i in items}, {i["sku"] for i in newest}


@live
@pytest.mark.parametrize("version,shown", [("1.40.3", False), ("1.41.0", True),
                                           ("1.41.2", True), (None, False)])
def test_the_listings_hide_a_floored_item_from_an_older_caller(version, shown):
    async def body(db):
        return await _listed(db, version)
    items, newest = asyncio.run(_routes("tfloor_list_%s" % (version or "none").replace(".", "_"),
                                        body))
    assert HOUSE in items                                  # unfloored row: always listed
    assert (FLOORED in items) is shown, (version, sorted(items))
    assert (FLOORED in newest) is shown, (version, sorted(newest))


def _patch_auth(monkeypatch):
    async def _none(*a, **k):
        return None

    async def _true(*a, **k):
        return True
    monkeypatch.setattr(main, "_check_steam_session", _none)
    monkeypatch.setattr(main, "_assert_no_service_subject", _none)
    monkeypatch.setattr(main, "_strict_steam_session_ok", _true)
    monkeypatch.setattr(main, "_artist_hmac_ok", lambda *a, **k: True)
    monkeypatch.setattr(main, "_is_artist", _true)
    monkeypatch.setattr(main, "_artist_audit", _none)
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "test-secret")


def _buy_sig(steam_id, sku):
    import hashlib
    import hmac
    return hmac.new(b"test-secret", ("buy:%s:%s" % (steam_id, sku)).encode(),
                    hashlib.sha256).hexdigest()


async def _buy(db, version):
    from sqlalchemy import text
    token = main._current_mod_version.set(version)
    try:
        try:
            await main.purchase_item(request=_request(version), steam_id=BUYER, sku=FLOORED,
                                     sig=_buy_sig(BUYER, FLOORED), expected_price=None, db=db)
            outcome = "accepted"
        except HTTPException as e:
            outcome = (e.status_code, str(e.detail))
    finally:
        main._current_mod_version.reset(token)
    await db.rollback()
    owned = (await db.execute(text("SELECT count(*) FROM player_items"))).scalar()
    gold = (await db.execute(text("SELECT gold_earned - gold_spent FROM players WHERE steam_id = :s"),
                             {"s": BUYER})).scalar()
    return outcome, owned, gold


@live
def test_a_purchase_below_the_floor_is_refused_before_anything_moves(monkeypatch):
    _patch_auth(monkeypatch)
    outcome, owned, gold = asyncio.run(_routes("tfloor_buy_old",
                                               lambda db: _buy(db, "1.40.3")))
    assert outcome == (409, "This item " + NEUTRAL), outcome
    assert owned == 0 and gold == 100000


@live
def test_a_purchase_at_the_floor_passes_the_floor(monkeypatch):
    """Control: at 1.41.0 the floor admits, and the next gate in line (the
    artist has not opened sales: stock -1) is the one that answers."""
    _patch_auth(monkeypatch)
    outcome, owned, gold = asyncio.run(_routes("tfloor_buy_new",
                                               lambda db: _buy(db, "1.41.0")))
    assert outcome[0] == 409 and "Not for sale yet" in outcome[1], outcome
    assert owned == 0 and gold == 100000


async def _gift(db, target):
    from sqlalchemy import text
    try:
        out = await main.artist_gift(request=_request("1.41.0"), steam_id=ARTIST, sku=FLOORED,
                                     target_steam_id=target, sig="x", db=db)
        outcome = out["status"]
    except HTTPException as e:
        outcome = (e.status_code, str(e.detail))
        await db.rollback()
    owned = (await db.execute(text(
        "SELECT count(*) FROM player_items pi JOIN players p ON p.id = pi.player_id "
        "WHERE p.steam_id = :s"), {"s": target})).scalar()
    return outcome, owned


@live
@pytest.mark.parametrize("target", [R_OLD, R_NONE])
def test_a_gift_to_a_recipient_below_the_floor_or_unknown_is_refused(monkeypatch, target):
    _patch_auth(monkeypatch)
    outcome, owned = asyncio.run(_routes("tfloor_gift_%s" % target[-1],
                                         lambda db: _gift(db, target)))
    assert outcome[0] == 409 and NEUTRAL.split(" ", 1)[1] in outcome[1], outcome
    assert owned == 0


@live
def test_a_gift_to_a_recipient_at_the_floor_lands(monkeypatch):
    _patch_auth(monkeypatch)
    outcome, owned = asyncio.run(_routes("tfloor_gift_new", lambda db: _gift(db, R_NEW)))
    assert outcome == "gifted" and owned == 1, outcome
