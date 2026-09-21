"""Migration 337 EXECUTED, not read.

The post-check in 337_demon_body_color.sql is the only thing between "a row
with this sku already existed" and "the deploy reported success over an item
that is free, mislabelled, owned by an artist or born out of stock". A
post-check is also exactly the kind of code that is written once and never run
against the case it exists for -- so it is run here, against a real
PostgreSQL: once on an empty table, once on top of itself (the idempotency
the file claims), once with a pre-existing row that MATCHES (it must pass --
otherwise the checks below prove nothing but that it always raises), and once
per column a pre-existing row can differ in, where it must RAISE.

Skips without A1_TEST_PG_DSN, the gate the other live-Postgres tests use:

    A1_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:55432/scr_wavea" \\
        python -m pytest backend/tests/test_shop_migration_337.py

Each case runs in its OWN schema, dropped afterwards, so nothing here can see
or touch another test's rows.
"""
import asyncio
import os
import pathlib

import pytest

DSN = os.environ.get("A1_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(
    not DSN, reason="A1_TEST_PG_DSN unset; live-Postgres migration check")

MIGRATION = (pathlib.Path(__file__).resolve().parents[1]
             / "sql" / "337_demon_body_color.sql")

# The shop_items shape the migration writes into. NOT generated from
# models.ShopItem: the ORM's `default=True` on catalog_ready is a PYTHON-side
# default and emits no server default, and this repo has already shipped a bug
# where the SQL default and the ORM default disagreed (ranked_enabled). What
# 337 relies on is the SERVER default, so it is spelled out here, and
# test_the_harness_covers_every_model_column fails if the model grows a column
# this table does not have.
DDL = """
CREATE TABLE shop_items (
    id              BIGSERIAL PRIMARY KEY,
    sku             VARCHAR(64) UNIQUE NOT NULL,
    kind            VARCHAR(16) NOT NULL,
    name            VARCHAR(128) NOT NULL,
    description     VARCHAR(256),
    price           INTEGER NOT NULL,
    rarity          VARCHAR(16) NOT NULL DEFAULT 'common',
    rotation_pool   VARCHAR(32),
    preview_color   VARCHAR(16),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    artist_steam_id VARCHAR(20),
    stock_limit     INTEGER,
    released_at     TIMESTAMPTZ,
    catalog_ready   BOOLEAN NOT NULL DEFAULT TRUE
);
"""

GOOD = dict(sku="pcolor_demonic", kind="player_color", name="Demonic",
            description="The purple the Demonic Pact card is drawn in.",
            price=3000, rarity="rare", preview_color="#7A50D1")


def _raw_dsn():
    return DSN.replace("+asyncpg", "")


async def _run_case(pre_existing=None, applies=2):
    """Fresh schema -> optional pre-existing row -> apply the migration
    `applies` times. Returns None on success, or the error message."""
    import asyncpg
    schema = "s337_%d" % (abs(hash(repr(pre_existing))) % 10_000_000)
    conn = await asyncpg.connect(_raw_dsn())
    try:
        await conn.execute(f'DROP SCHEMA IF EXISTS {schema} CASCADE')
        await conn.execute(f'CREATE SCHEMA {schema}')
        await conn.execute(f'SET search_path TO {schema}')
        await conn.execute(DDL)
        if pre_existing is not None:
            cols = ", ".join(pre_existing)
            vals = ", ".join("$%d" % (i + 1) for i in range(len(pre_existing)))
            await conn.execute(f"INSERT INTO shop_items ({cols}) VALUES ({vals})",
                               *pre_existing.values())
        sql = MIGRATION.read_text(encoding="utf-8")
        for _ in range(applies):
            await conn.execute(sql)
        return None
    except Exception as e:                      # the RAISE EXCEPTION we are after
        return str(e)
    finally:
        await _cleanup(conn, schema)


async def _cleanup(conn, schema):
    """The migration RAISEs inside its own BEGIN, which leaves the session in
    an aborted transaction: every later statement, including the DROP, fails
    with InFailedSQLTransactionError. Rolling back first is what lets the
    refusal be reported as the refusal it is."""
    try:
        try:
            await conn.execute("ROLLBACK")
        except Exception:
            pass
        await conn.execute(f'DROP SCHEMA IF EXISTS {schema} CASCADE')
    finally:
        await conn.close()


def _apply(pre_existing=None, applies=2):
    return asyncio.run(_run_case(pre_existing, applies))


def test_the_harness_covers_every_model_column():
    """If ShopItem grows a NOT NULL column, this table stops being the shape
    the migration really writes into and every result below is about a table
    production does not have."""
    import models
    assert set(models.ShopItem.__table__.columns.keys()) == {
        "id", "sku", "kind", "name", "description", "price", "rarity",
        "rotation_pool", "preview_color", "created_at", "artist_steam_id",
        "stock_limit", "released_at", "catalog_ready"}


def test_the_migration_applies_and_is_idempotent():
    """The ordinary deploy, and the second run the wrapper's re-apply makes
    possible. `IF NOT EXISTS`-shaped migrations are re-run by hand often
    enough that the second apply is not hypothetical."""
    assert _apply() is None


def test_a_pre_existing_row_that_already_matches_is_accepted():
    """The control for every refusal below. A post-check that raised whatever
    it found would pass all of them and mean nothing."""
    assert _apply(dict(GOOD)) is None


@pytest.mark.parametrize("field,value,expect", [
    ("price", 0, "price=0"),
    ("price", 4000, "price=4000"),
    ("name", "Demon", "name=Demon"),
    ("rarity", "common", "rarity=common"),
    ("description", None, "description="),
    ("kind", "face", "kind=face"),
    ("preview_color", "#000000", "hex=#000000"),
])
def test_a_pre_existing_row_that_differs_is_refused(field, value, expect):
    """Every column the INSERT writes. ON CONFLICT DO NOTHING makes each of
    these a silent no-op, and a post-check that reads only kind and
    preview_color reports "post-check OK" over all of them."""
    row = dict(GOOD)
    row[field] = value
    err = _apply(row)
    assert err is not None, f"a pre-existing row with {field}={value!r} was accepted"
    assert "already existed" in err and expect in err, err


@pytest.mark.parametrize("field,value,needle", [
    ("artist_steam_id", "76561198000000001", "artist_steam_id=765"),
    ("stock_limit", -1, "stock_limit=-1"),
    ("stock_limit", 5, "stock_limit=5"),
])
def test_a_pre_existing_row_that_is_not_a_house_item_is_refused(field, value, needle):
    """stock_limit = -1 is the born-out-of-stock state migration 131 stamps:
    the row exists, the shop lists it, and no one can buy it. An artist id
    routes it through the /artist stock and block rules instead of being a
    house colour."""
    row = dict(GOOD)
    row[field] = value
    err = _apply(row)
    assert err is not None, f"{field}={value!r} was accepted as a house item"
    assert "not a plain house item" in err and needle in err, err


@pytest.mark.parametrize("field,value", [
    ("catalog_ready", False),
    ("rotation_pool", "achievement"),
    ("rotation_pool", "seasonal"),
])
def test_a_pre_existing_row_that_is_hidden_is_refused(field, value):
    """catalog_ready=false hides AND blocks the purchase; a non-NULL
    rotation_pool always hides it from the list, while only the literal
    'achievement' refuses a purchase -- so 'seasonal' would leave the item
    buyable by sku with nothing listing it. NULL is the only value this row
    may carry."""
    row = dict(GOOD)
    row[field] = value
    err = _apply(row)
    assert err is not None, f"{field}={value!r} was accepted"
    assert "would be hidden from the shop" in err, err


def test_a_missing_row_is_refused():
    """The INSERT silently doing nothing is not a state this migration can
    reach on its own, but the post-check asserts the END STATE rather than
    trusting the INSERT -- so the check must exist and must be able to fire.
    Driven by making the sku unreachable to the post-check's SELECT.
    """
    import asyncpg

    async def go():
        schema = "s337_missing"
        conn = await asyncpg.connect(_raw_dsn())
        try:
            await conn.execute(f'DROP SCHEMA IF EXISTS {schema} CASCADE')
            await conn.execute(f'CREATE SCHEMA {schema}')
            await conn.execute(f'SET search_path TO {schema}')
            await conn.execute(DDL)
            # A BEFORE INSERT trigger that drops the write on the floor: the
            # INSERT reports success and the row is not there.
            await conn.execute("""
                CREATE FUNCTION swallow() RETURNS trigger AS $f$
                BEGIN RETURN NULL; END $f$ LANGUAGE plpgsql;
                CREATE TRIGGER t_swallow BEFORE INSERT ON shop_items
                FOR EACH ROW EXECUTE FUNCTION swallow();
            """)
            try:
                await conn.execute(MIGRATION.read_text(encoding="utf-8"))
                return None
            except Exception as e:
                return str(e)
        finally:
            await _cleanup(conn, schema)

    err = asyncio.run(go())
    assert err is not None and "missing after the write" in err, err
