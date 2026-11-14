"""Migration 413: the two music albums delisted, removed from every owner, each
buyer refunded what that buyer paid, the artist royalty taken back, with a
ledger and an archive that prove each amount.

Static half (always runs): 413's transaction shape, and that it is the
delist that comes first.

Live half (A1_TEST_PG_DSN, the gate test_shop_min_client_version.py uses):
each case builds its own schema from the ORM tables the file touches, plants
the fixture, runs the real migration text (and, for the lock and the readers,
the real route functions) and drops the schema afterwards.

    A1_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:55432/a1test" \\
        python -m pytest backend/tests/test_music_refund_413.py

The account-deletion case runs on the connect-failure lane's full schema
(CF_TEST_PG_DSN, cf_pg.case), because delete_player_data touches most tables.
"""
import asyncio
import hashlib
import hmac
import os
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
API = ROOT / "backend" / "api"
SQL = ROOT / "backend" / "sql"
MIGRATION = SQL / "413_music_albums_delist_refund.sql"
HERE = pathlib.Path(__file__).resolve().parent

sys.path.insert(0, str(API))
sys.path.insert(0, str(HERE))

import main  # noqa: E402
import models  # noqa: E402
from fastapi import HTTPException  # noqa: E402

DSN = os.environ.get("A1_TEST_PG_DSN")
live = pytest.mark.skipif(not DSN, reason="A1_TEST_PG_DSN unset; live-Postgres check")

ROUND = "music_album_another_round"
CLAVAR = "music_album_clavar_la_bala"
FACE = "title_mr413_other"
SKUS = (ROUND, CLAVAR)
# Synthetic ids: no SteamID64 shape.
ARTIST = "mr413artist"
B1 = "mr413buyer1"          # bought both albums, and a title
B2 = "mr413buyer2"          # bought the first album
B3 = "mr413buyer3"          # bought the second album
B4 = "mr413buyer4"          # a free (gifted) copy of the first album
B5 = "mr413buyer5"          # buys the second album during the lock case
ALL_PLAYERS = (ARTIST, B1, B2, B3, B4, B5)   # every players row _FIXTURE inserts
SECRET = "mr413-secret"
NOT_SHIPPED = "This cosmetic is approved but has not shipped in the mod yet"
DELIST_MARK = "-- 413-delist\n"


def _sql():
    return MIGRATION.read_text(encoding="utf-8")


# ---------------------------------------------------------------- static

def _code_lines(text):
    return [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("--")]


def test_413_house_shape():
    lines = _code_lines(_sql())
    assert lines[:5] == [
        "BEGIN;",
        "SET LOCAL lock_timeout = '5s';",
        "SET LOCAL idle_in_transaction_session_timeout = '5s';",
        "SET LOCAL statement_timeout = '25s';",
        "SET LOCAL synchronous_commit = local;",
    ]
    assert lines[-1] == "COMMIT;"
    assert sum(1 for l in lines if l == "BEGIN;") == 1
    assert sum(1 for l in lines if l == "COMMIT;") == 1
    assert not list(SQL.glob("rollback_413*")), "413 has no rollback file by design"


def test_413_the_delist_is_the_first_data_statement():
    text = _sql()
    assert text.count(DELIST_MARK) == 1
    head = _code_lines(text[: text.index(DELIST_MARK)])
    assert all(l.startswith(("BEGIN", "SET LOCAL")) for l in head), head
    first = text[text.index(DELIST_MARK):].split(";", 1)[0]
    assert "FOR UPDATE" in first and "SET catalog_ready = FALSE" in first, first
    assert text.index(DELIST_MARK) < text.index("FROM player_items")


def _delist_moved_to_the_end(text):
    """The mutant of case c: the delist statement moved to just before the
    closing self-check."""
    i = text.index(DELIST_MARK)
    j = text.index(";", i) + 1
    stmt = text[i:j]
    rest = text[:i] + text[j:]
    k = rest.index("DO $post$")
    return rest[:k] + stmt + "\n\n" + rest[k:]


def test_the_mutant_is_well_formed():
    m = _delist_moved_to_the_end(_sql())
    assert m.count(DELIST_MARK) == 1
    assert m.index("DO $refund$") < m.index(DELIST_MARK) < m.index("DO $post$")


LOCK_MARK = ("-- 413-players-lock\n", "-- 413-players-lock-end\n")
MEMBERSHIP_MARK = ("-- 413-lock-membership\n", "-- 413-lock-membership-end\n")


def _cut(text, marks):
    i, j = text.index(marks[0]), text.index(marks[1]) + len(marks[1])
    return text[:i] + text[j:]


def test_413_the_players_lock_comes_right_after_the_delist():
    text = _sql()
    assert text.count(LOCK_MARK[0]) == 1 and text.count(LOCK_MARK[1]) == 1
    after_delist = text[text.index(";", text.index(DELIST_MARK)) + 1:]
    assert _code_lines(after_delist)[0] == "DO $lock$"
    block = text[text.index(LOCK_MARK[0]):text.index(LOCK_MARK[1])]
    assert "ORDER BY p.id" in block and "FOR NO KEY UPDATE NOWAIT" in block, block
    assert "WHEN lock_not_available" in block, block
    # the two mutants below are well formed
    m1 = _cut(text, LOCK_MARK)
    assert "DO $lock$" not in m1 and MEMBERSHIP_MARK[0] in m1
    m2 = _cut(m1, MEMBERSHIP_MARK)
    assert "scr413.locked_players" not in m2


# ---------------------------------------------------------------- live schema

def _pg_dsn():
    return DSN.replace("+asyncpg", "")


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

# The royalty columns as the primary declares them (information_schema,
# 14 Nov): the ORM deliberately does not (#346).
_ROYALTY = """
ALTER TABLE player_items
    ADD COLUMN IF NOT EXISTS royalty_paid INTEGER,
    ADD COLUMN IF NOT EXISTS royalty_rate_pct SMALLINT,
    ADD COLUMN IF NOT EXISTS royalty_artist_steam_id VARCHAR(20),
    ADD COLUMN IF NOT EXISTS royalty_resolved BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS artist_item_blocks (artist_steam_id TEXT, blocked_steam_id TEXT,
                                               created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS matches (id UUID PRIMARY KEY, is_ranked BOOLEAN);
"""

_FIXTURE = """
INSERT INTO shop_items (sku, kind, name, description, price, rarity, catalog_ready,
                        stock_limit, artist_steam_id, released_at)
VALUES ('music_album_another_round', 'music_album', 'Another Round', 'd', 1, 'rare', TRUE,
        NULL, NULL, now() - interval '30 days'),
       ('music_album_clavar_la_bala', 'music_album', 'Clavar', 'd', 1000, 'legendary', TRUE,
        NULL, 'mr413artist', now() - interval '20 days'),
       ('title_mr413_other', 'title', 'Other', 'd', 50, 'common', TRUE,
        NULL, NULL, now() - interval '40 days');
INSERT INTO players (steam_id, display_name, gold_earned, gold_spent) VALUES
       ('mr413artist', 'a', 5000, 0),
       ('mr413buyer1', 'b1', 3000, 1051),
       ('mr413buyer2', 'b2', 100, 1),
       ('mr413buyer3', 'b3', 1500, 1000),
       ('mr413buyer4', 'b4', 10, 0),
       ('mr413buyer5', 'b5', 2000, 0);
"""

# (buyer, sku, price, royalty to the artist)
_OWNED = [(B1, ROUND, 1, 0), (B1, CLAVAR, 1000, 500), (B2, ROUND, 1, 0),
          (B3, CLAVAR, 1000, 500), (B4, ROUND, 0, 0), (B1, FACE, 50, 0)]


async def _own(conn, buyer, sku, price, royalty, days=10):
    await conn.execute(
        "INSERT INTO player_items (player_id, item_id, purchase_price, purchased_at,"
        " royalty_paid, royalty_rate_pct, royalty_artist_steam_id, royalty_resolved)"
        " SELECT p.id, si.id, CAST($3 AS integer),"
        "        now() - make_interval(days => CAST($5 AS integer)), CAST($4 AS integer),"
        "        CASE WHEN CAST($4 AS integer) > 0 THEN 50 ELSE 0 END, si.artist_steam_id, TRUE"
        "   FROM players p, shop_items si"
        "  WHERE p.steam_id = CAST($1 AS text) AND si.sku = CAST($2 AS text)",
        buyer, sku, price, royalty, days)
    if price > 0:
        await conn.execute(
            "INSERT INTO gold_transactions (player_id, amount, reason, reference_id)"
            " SELECT id, -CAST($2 AS integer), 'purchase', CAST($3 AS text) FROM players"
            "  WHERE steam_id = CAST($1 AS text)",
            buyer, price, sku)
    if royalty > 0:
        await conn.execute(
            "INSERT INTO gold_transactions (player_id, amount, reason, reference_id)"
            " SELECT id, CAST($2 AS integer), 'artist_royalty', CAST($3 AS text) FROM players"
            "  WHERE steam_id = CAST($1 AS text)",
            ARTIST, royalty, sku)


async def _seed(conn):
    await conn.execute(_FIXTURE)
    for i, (b, sku, price, roy) in enumerate(_OWNED):
        await _own(conn, b, sku, price, roy, days=10 + i)
    # income rows the gold-source pie must keep counting
    await conn.execute(
        "INSERT INTO gold_transactions (player_id, amount, reason, reference_id)"
        " SELECT id, 2000, 'level_reward', 'lvl' FROM players WHERE steam_id = $1", B1)
    await conn.execute(
        "INSERT INTO gold_transactions (player_id, amount, reason, reference_id)"
        " SELECT id, 4000, 'achievement', 'ach' FROM players WHERE steam_id = $1", ARTIST)


async def _with_schema(name, body, seed=True):
    """A fresh schema with the four ORM tables, the primary's royalty columns
    and the fixture; body(conn, sessionmaker) runs with search_path set."""
    import asyncpg
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    admin = await asyncpg.connect(_pg_dsn())
    try:
        await admin.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % name)
        await admin.execute('CREATE SCHEMA "%s"' % name)
    finally:
        await admin.close()
    engine = create_async_engine(
        "postgresql+asyncpg://" + _pg_dsn().split("://", 1)[1],
        connect_args={"server_settings": {"search_path": name}})
    sm = async_sessionmaker(engine, expire_on_commit=False)
    conn = None
    try:
        async with engine.begin() as c:
            await c.run_sync(models.Base.metadata.create_all,
                             tables=[models.Player.__table__, models.ShopItem.__table__,
                                     models.PlayerItem.__table__,
                                     models.GoldTransaction.__table__])
        conn = await asyncpg.connect(_pg_dsn(), server_settings={"search_path": name})
        await conn.execute("ALTER TABLE shop_items ADD COLUMN IF NOT EXISTS "
                           "min_client_version VARCHAR(16)")
        await conn.execute(_FILL_DEFAULTS)
        await conn.execute(_ROYALTY)
        if seed:
            await _seed(conn)
        return await body(conn, sm)
    finally:
        if conn is not None:
            await conn.close()
        await engine.dispose()
        admin = await asyncpg.connect(_pg_dsn())
        try:
            await admin.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % name)
        finally:
            await admin.close()


_TABLES = ("players", "shop_items", "player_items", "gold_transactions")


async def _snapshot(conn):
    out = {}
    tables = list(_TABLES)
    if await conn.fetchval("SELECT to_regclass('music_album_refund_archive') IS NOT NULL"):
        tables.append("music_album_refund_archive")
    for t in tables:
        rows = await conn.fetch("SELECT CAST(x AS text) AS r FROM %s x" % t)
        out[t] = sorted(r["r"] for r in rows)
    return out


async def _apply(conn, sql=None):
    notices = []
    listener = (lambda _c, m: notices.append(m.message))
    conn.add_log_listener(listener)
    try:
        await conn.execute(sql or _sql())
    finally:
        conn.remove_log_listener(listener)
    return notices


async def _gold(conn, sid):
    r = await conn.fetchrow("SELECT gold_earned, gold_spent FROM players WHERE steam_id = $1", sid)
    return (r["gold_earned"], r["gold_spent"])


async def _pid(conn, sid):
    return await conn.fetchval("SELECT id FROM players WHERE steam_id = $1", sid)


async def _all_gold(conn):
    return {r["steam_id"]: (r["gold_earned"], r["gold_spent"]) for r in await conn.fetch(
        "SELECT steam_id, gold_earned, gold_spent FROM players")}


def _earned_by_sku(mine):
    return {it["sku"]: it["earned"] for it in mine["items"]}


def _earned_by_artist(board):
    assert len(set(board["artists"])) == len(board["artists"]), board
    return dict(zip(board["artists"], board["earned"]))


# ---------------------------------------------------------------- a. the fixture

@live
def test_a_413_refunds_archives_and_reruns_as_a_no_op():
    async def body(conn, _sm):
        pre_items = {(r["steam_id"], r["sku"]): dict(r) for r in await conn.fetch(
            "SELECT p.steam_id, si.sku, pi.purchased_at, pi.purchase_price, pi.royalty_paid,"
            "       pi.royalty_rate_pct, pi.royalty_artist_steam_id, pi.royalty_resolved"
            "  FROM player_items pi JOIN players p ON p.id = pi.player_id"
            "  JOIN shop_items si ON si.id = pi.item_id")}
        face_before = await conn.fetchval(
            "SELECT CAST(pi AS text) FROM player_items pi JOIN shop_items si ON si.id = pi.item_id"
            " WHERE si.sku = $1", FACE)
        gold_before = await _all_gold(conn)
        face_shop_before = await conn.fetchval(
            "SELECT CAST(si AS text) FROM shop_items si WHERE sku = $1", FACE)
        ledger_before = await conn.fetchval("SELECT count(*) FROM gold_transactions")

        notices = await _apply(conn)

        # R8: every ownership row of the two skus is gone; the face row is untouched.
        assert await conn.fetchval(
            "SELECT count(*) FROM player_items pi JOIN shop_items si ON si.id = pi.item_id"
            " WHERE si.sku = ANY($1::text[])", list(SKUS)) == 0
        assert await conn.fetchval(
            "SELECT CAST(pi AS text) FROM player_items pi JOIN shop_items si ON si.id = pi.item_id"
            " WHERE si.sku = $1", FACE) == face_before
        assert await conn.fetchval(
            "SELECT CAST(si AS text) FROM shop_items si WHERE sku = $1", FACE) == face_shop_before
        # R2/R9: both delisted.
        assert [r["catalog_ready"] for r in await conn.fetch(
            "SELECT catalog_ready FROM shop_items WHERE sku = ANY($1::text[])", list(SKUS))] \
            == [False, False]

        # R4: one archive row per removed ownership row, holding what it held.
        arch = await conn.fetch(
            "SELECT p.steam_id, a.* FROM music_album_refund_archive a"
            "  JOIN players p ON p.id = a.player_id")
        assert len(arch) == 5
        # the archive holds exactly the removed rows: each once, none other
        assert sorted((a["steam_id"], a["sku"]) for a in arch) == \
            sorted(k for k in pre_items if k[1] in SKUS)
        artist_pid = await _pid(conn, ARTIST)
        for a in arch:
            pre = pre_items[(a["steam_id"], a["sku"])]
            assert a["purchased_at"] == pre["purchased_at"]
            assert a["purchase_price"] == pre["purchase_price"]
            assert a["royalty_paid"] == pre["royalty_paid"]
            assert a["royalty_rate_pct"] == pre["royalty_rate_pct"]
            assert a["royalty_resolved"] == pre["royalty_resolved"]
            want_artist = artist_pid if pre["royalty_artist_steam_id"] == ARTIST else None
            assert a["royalty_artist_player_id"] == want_artist
            assert a["gold_refunded"] == pre["purchase_price"]
            assert a["royalty_taken_back"] == pre["royalty_paid"]
            if pre["purchase_price"] == 0:
                assert a["refund_ledger_id"] is None
            else:
                led = await conn.fetchrow(
                    "SELECT player_id, amount, reason, reference_id FROM gold_transactions"
                    " WHERE id = $1", a["refund_ledger_id"])
                assert (led["player_id"], led["amount"], led["reason"], led["reference_id"]) == \
                    (a["player_id"], pre["purchase_price"], "music_album_refund", a["sku"])
        assert len({a["run_at"] for a in arch}) == 1

        # R5: one delta per player on gold_spent; R6: one on the artist's gold_earned.
        # Every players row, not a chosen few: a row this list did not name
        # that moved would fail the comparison.
        want_gold = dict(gold_before)
        want_gold[B1] = (gold_before[B1][0], gold_before[B1][1] - 1001)
        want_gold[B2] = (gold_before[B2][0], gold_before[B2][1] - 1)
        want_gold[B3] = (gold_before[B3][0], gold_before[B3][1] - 1000)
        want_gold[ARTIST] = (gold_before[ARTIST][0] - 1000, gold_before[ARTIST][1])
        assert await _all_gold(conn) == want_gold

        # R7: one refund row per paid row, one reversal per artist account and sku.
        refunds = await conn.fetch(
            "SELECT p.steam_id, gt.amount, gt.reference_id FROM gold_transactions gt"
            "  JOIN players p ON p.id = gt.player_id WHERE gt.reason = 'music_album_refund'")
        assert sorted((r["steam_id"], r["amount"], r["reference_id"]) for r in refunds) == \
            sorted([(B1, 1, ROUND), (B1, 1000, CLAVAR), (B2, 1, ROUND), (B3, 1000, CLAVAR)])
        rev = await conn.fetch(
            "SELECT p.steam_id, gt.amount, gt.reference_id FROM gold_transactions gt"
            "  JOIN players p ON p.id = gt.player_id WHERE gt.reason = 'music_royalty_reversal'")
        assert [(r["steam_id"], r["amount"], r["reference_id"]) for r in rev] == \
            [(ARTIST, -1000, CLAVAR)]
        assert await conn.fetchval("SELECT count(*) FROM gold_transactions") == ledger_before + 5
        assert max(len("music_album_refund"), len("music_royalty_reversal")) <= 64

        # R9: the proof in the apply log.
        joined = "\n".join(notices)
        assert ("413: archived 3 row(s) of music_album_another_round and 2 of "
                "music_album_clavar_la_bala; refunded 2002 gold to 3 player(s); took back "
                "1000 royalty gold in 1 ledger row(s)") in joined, notices
        assert "413: post-check OK" in joined, notices

        # R1: applied a second time, it changes nothing.
        before = await _snapshot(conn)
        notices2 = await _apply(conn)
        assert await _snapshot(conn) == before
        assert any("refunded 0 gold to 0 player(s)" in n for n in notices2), notices2
    asyncio.run(_with_schema("t413_apply", body))


@live
def test_a2_a_free_row_that_appears_after_a_run_is_archived_by_a_rerun_and_moves_no_gold():
    """A gift that read catalog_ready TRUE before the run commits its free row
    after it (main.artist_gift's insert, as it is written there). A second
    application removes and archives that row with gold_refunded 0, writes no
    ledger row, moves no gold, and leaves the first run's archive rows as
    they were."""
    async def body(conn, _sm):
        await _apply(conn)
        first = sorted(r["r"] for r in await conn.fetch(
            "SELECT CAST(a AS text) AS r FROM music_album_refund_archive a"))
        gold = await conn.fetch("SELECT steam_id, gold_earned, gold_spent FROM players"
                                " ORDER BY steam_id")
        ledger = await conn.fetchval("SELECT count(*) FROM gold_transactions")
        await conn.execute(
            "INSERT INTO player_items (player_id, item_id, purchase_price, "
            "        royalty_paid, royalty_rate_pct, royalty_artist_steam_id, "
            "        royalty_resolved) "
            "SELECT p.id, si.id, 0, 0, 0, $3, TRUE FROM players p, shop_items si"
            " WHERE p.steam_id = $1 AND si.sku = $2 "
            "ON CONFLICT (player_id, item_id) DO NOTHING", B5, CLAVAR, ARTIST)
        notices = await _apply(conn)
        return {
            "first": first,
            "first_after": sorted(r["r"] for r in await conn.fetch(
                "SELECT CAST(a AS text) AS r FROM music_album_refund_archive a"
                " WHERE CAST(a AS text) = ANY($1::text[])", first)),
            "new": [dict(r) for r in await conn.fetch(
                "SELECT p.steam_id, a.sku, a.purchase_price, a.gold_refunded,"
                "       a.royalty_taken_back, a.refund_ledger_id"
                "  FROM music_album_refund_archive a JOIN players p ON p.id = a.player_id"
                " WHERE CAST(a AS text) <> ALL($1::text[])", first)],
            "left": await conn.fetchval(
                "SELECT count(*) FROM player_items pi JOIN shop_items si ON si.id = pi.item_id"
                " WHERE si.sku = ANY($1::text[])", list(SKUS)),
            "gold_same": gold == await conn.fetch(
                "SELECT steam_id, gold_earned, gold_spent FROM players ORDER BY steam_id"),
            "ledger_same": ledger == await conn.fetchval("SELECT count(*) FROM gold_transactions"),
            "notices": notices,
        }
    out = asyncio.run(_with_schema("t413_rerun_gift", body))
    assert len(out["first"]) == 5 and out["first_after"] == out["first"], out
    assert out["new"] == [{"steam_id": B5, "sku": CLAVAR, "purchase_price": 0,
                           "gold_refunded": 0, "royalty_taken_back": 0,
                           "refund_ledger_id": None}], out
    assert out["left"] == 0 and out["gold_same"] and out["ledger_same"], out
    assert any("archived 0 row(s) of music_album_another_round and 1 of "
               "music_album_clavar_la_bala; refunded 0 gold to 0 player(s)" in n
               for n in out["notices"]), out["notices"]


# ---------------------------------------------------------------- b. refusals

async def _plant_third_album(conn):
    await conn.execute(
        "INSERT INTO shop_items (sku, kind, name, description, price, rarity, catalog_ready)"
        " VALUES ('music_album_third', 'music_album', 'T', 'd', 5, 'rare', TRUE)")


async def _plant_sku_absent(conn):
    await conn.execute(
        "UPDATE shop_items SET sku = 'music_album_renamed' WHERE sku = $1", CLAVAR)


async def _plant_null_price(conn):
    await conn.execute("ALTER TABLE player_items ALTER COLUMN purchase_price DROP NOT NULL")
    await conn.execute(
        "UPDATE player_items SET purchase_price = NULL WHERE player_id = $1", await _pid(conn, B4))


async def _plant_no_purchase_row(conn):
    await conn.execute(
        "DELETE FROM gold_transactions WHERE player_id = $1 AND reason = 'purchase'",
        await _pid(conn, B2))


async def _plant_spent_below_refund(conn):
    await conn.execute("UPDATE players SET gold_spent = 10 WHERE steam_id = $1", B3)


async def _plant_royalty_ledger_short(conn):
    await conn.execute(
        "DELETE FROM gold_transactions WHERE id = (SELECT min(id) FROM gold_transactions"
        " WHERE reason = 'artist_royalty')")


async def _plant_royalty_no_account(conn):
    await conn.execute("UPDATE players SET steam_id = 'mr413gone' WHERE steam_id = $1", ARTIST)


async def _plant_artist_below_zero(conn):
    await conn.execute("UPDATE players SET gold_spent = 4500 WHERE steam_id = $1", ARTIST)


REFUSALS = [
    ("third_album", _plant_third_album,
     "413 refused: 3 shop rows of kind music_album, expected 2"),
    ("sku_absent", _plant_sku_absent,
     "413 refused: shop row music_album_clavar_la_bala is absent or not a music_album"),
    ("null_price", _plant_null_price,
     "413 refused: 1 ownership row(s) have a NULL or negative purchase_price"),
    ("no_purchase_row", _plant_no_purchase_row,
     "413 refused: 1 paid ownership row(s) have no purchase ledger row of the same player, sku and amount"),
    ("spent_below_refund", _plant_spent_below_refund,
     "413 refused: 1 player(s) have gold_spent below their refund"),
    ("royalty_ledger_short", _plant_royalty_ledger_short,
     "413 refused: for 1 artist account and sku pair(s) the royalty to take back differs from the artist_royalty ledger"),
    ("royalty_no_account", _plant_royalty_no_account,
     "413 refused: 2 ownership row(s) paid a royalty to a steam id with no live account"),
    ("artist_below_zero", _plant_artist_below_zero,
     "413 refused: 1 artist account(s) would fall below a zero balance"),
]


@live
@pytest.mark.parametrize("name,plant,message", REFUSALS, ids=[r[0] for r in REFUSALS])
def test_b_each_refusal_names_its_own_state(name, plant, message):
    async def planted(conn, _sm):
        await plant(conn)
        before = await _snapshot(conn)
        sql = _sql()
        with pytest.raises(Exception) as ei:
            await conn.execute(sql)
        await conn.execute("ROLLBACK")
        after = await _snapshot(conn)
        return str(ei.value), before, after

    err, before, after = asyncio.run(_with_schema("t413_ref_" + name, planted))
    assert err.startswith(message), err
    assert after == before, "a refusal changed something"

    async def control(conn, _sm):
        await conn.execute(_sql())
        return await conn.fetchval(
            "SELECT count(*) FROM music_album_refund_archive")
    assert asyncio.run(_with_schema("t413_ctl_" + name, control)) == 5


def _psql():
    import shutil
    return os.environ.get("CF_PSQL") or os.environ.get("D2_TEST_PSQL") or shutil.which("psql")


def _apply_like_the_migrate_verb(schema):
    """The migrate verb's own command (scripts/cc-deploy-wrapper.sh): psql
    -v ON_ERROR_STOP=1 with the file on stdin. Returns (exit code, stderr)."""
    import subprocess
    env = dict(os.environ, PGOPTIONS="-c search_path=%s" % schema)
    with open(MIGRATION, "rb") as f:
        p = subprocess.run([_psql(), "-X", "-v", "ON_ERROR_STOP=1", _pg_dsn()], stdin=f,
                           capture_output=True, env=env, timeout=60)
    return p.returncode, p.stderr.decode("utf-8", "replace")


@live
@pytest.mark.parametrize("planted", [True, False], ids=["refusing", "control"])
def test_b2_applied_as_the_migrate_verb_applies_it_a_refusal_exits_non_zero(planted):
    if not _psql():
        pytest.skip("no psql client on this seat")
    schema = "t413_psql_%s" % ("ref" if planted else "ctl")

    async def body(conn, _sm):
        if planted:
            await _plant_third_album(conn)
        rc, err = _apply_like_the_migrate_verb(schema)
        listed = await conn.fetchval(
            "SELECT count(*) FROM shop_items WHERE sku = ANY($1::text[]) AND catalog_ready",
            list(SKUS))
        return rc, err, listed
    rc, err, listed = asyncio.run(_with_schema(schema, body))
    if planted:
        assert rc == 3, (rc, err)
        assert "413 refused: 3 shop rows of kind music_album, expected 2" in err, err
        assert listed == 2                      # rolled back: both still listed
    else:
        assert rc == 0, (rc, err)
        assert listed == 0


# ---------------------------------------------------------------- c. the lock

async def _wait_blocked(pid, tries=200):
    import asyncpg
    mon = await asyncpg.connect(_pg_dsn())
    try:
        for _ in range(tries):
            w = await mon.fetchval(
                "SELECT wait_event_type FROM pg_stat_activity WHERE pid = $1", pid)
            if w == "Lock":
                return True
            await asyncio.sleep(0.05)
        return False
    finally:
        await mon.close()


def _purchase_sqls(buyer, sku, price, royalty):
    """The purchase path's writes, in its order: the FOR SHARE read of the
    shop row, the debit, the ownership row, the ledger row, the royalty."""
    royalty_sqls = [] if not royalty else [
        "UPDATE players SET gold_earned = gold_earned + %d WHERE steam_id = '%s'" % (royalty, ARTIST),
        "INSERT INTO gold_transactions (player_id, amount, reason, reference_id)"
        " SELECT id, %d, 'artist_royalty', '%s' FROM players WHERE steam_id = '%s'"
        % (royalty, sku, ARTIST),
    ]
    return [
        "SELECT price, artist_steam_id, stock_limit, catalog_ready FROM shop_items"
        " WHERE sku = '%s' FOR SHARE" % sku,
        "UPDATE players SET gold_spent = gold_spent + %d WHERE steam_id = '%s'" % (price, buyer),
        "INSERT INTO player_items (player_id, item_id, purchase_price, royalty_paid,"
        " royalty_rate_pct, royalty_artist_steam_id, royalty_resolved)"
        " SELECT p.id, si.id, %d, %d, 50, si.artist_steam_id, TRUE FROM players p, shop_items si"
        " WHERE p.steam_id = '%s' AND si.sku = '%s'" % (price, royalty, buyer, sku),
        "INSERT INTO gold_transactions (player_id, amount, reason, reference_id)"
        " SELECT id, -%d, 'purchase', '%s' FROM players WHERE steam_id = '%s'" % (price, sku, buyer),
    ] + royalty_sqls


async def _in_flight_purchase_case(conn, sql):
    """A purchase of the first album (no royalty, so it locks no row the file
    takes) holds its FOR SHARE read while `sql` starts on `conn`; once the
    file waits on a lock, the purchase writes its debit, ownership row and
    ledger row, and commits. Returns what a reader needs to judge the
    outcome. The purchase's own writes never wait (lock_timeout 2s, any
    error fails the case)."""
    import asyncpg
    a = await asyncpg.connect(_pg_dsn(), server_settings={
        "search_path": await conn.fetchval("SELECT current_schema()")})
    try:
        purchase = _purchase_sqls(B5, ROUND, 1, 0)
        await a.execute("BEGIN")
        await a.execute("SET LOCAL lock_timeout = '2s'")
        await a.execute(purchase[0])
        b5_before = await _gold(conn, B5)
        schema = await conn.fetchval("SELECT current_schema()")
        task = asyncio.ensure_future(conn.execute(sql))
        blocked = await _wait_blocked(conn.get_server_pid())
        # While it waits: has the migration touched player_items yet? Any
        # read or delete of an ownership row would hold a lock on the table.
        mon = await asyncpg.connect(_pg_dsn())
        try:
            items_locked = await mon.fetchval(
                "SELECT count(*) FROM pg_locks WHERE pid = $1 AND relation = to_regclass($2)",
                conn.get_server_pid(), '"%s".player_items' % schema)
        finally:
            await mon.close()
        for s in purchase[1:]:
            await a.execute(s)
        await a.execute("COMMIT")
        try:
            await task
            err = None
        except Exception as e:                       # noqa: BLE001
            err = str(e)
            await conn.execute("ROLLBACK")
        archived = await conn.fetchval(
            "SELECT count(*) FROM music_album_refund_archive a JOIN players p ON p.id = a.player_id"
            " WHERE p.steam_id = $1 AND a.sku = $2 AND a.gold_refunded = 1",
            B5, ROUND) if await conn.fetchval(
                "SELECT to_regclass('music_album_refund_archive') IS NOT NULL") else 0
        left = await conn.fetchval(
            "SELECT count(*) FROM player_items pi JOIN shop_items si ON si.id = pi.item_id"
            " WHERE si.sku = ANY($1::text[])", list(SKUS))
        return {"blocked": blocked, "items_locked": items_locked, "err": err,
                "archived": archived, "left": left,
                "b5_before": b5_before, "b5_after": await _gold(conn, B5),
                "artist": await _gold(conn, ARTIST)}
    finally:
        await a.close()


def _lock_case_holds(out):
    """The lock half of R2: the migration waited for the purchase in flight
    before it touched player_items at all, then ran to its end, and the purchase it waited for was archived and
    refunded with the rest (the buyer's gold_spent back where it was before
    the purchase's own debit, read before that debit committed)."""
    return (out["blocked"] and out["items_locked"] == 0
            and out["err"] is None and out["archived"] == 1
            and out["left"] == 0
            and out["b5_after"] == out["b5_before"])


@live
def test_c_a_purchase_holding_its_share_lock_blocks_the_delist_and_is_refunded():
    async def body(conn, _sm):
        return await _in_flight_purchase_case(conn, _sql())
    out = asyncio.run(_with_schema("t413_lock", body))
    assert _lock_case_holds(out), out
    assert out["artist"] == (4000, 0), out      # 5000 - 1000; the first album pays none


@live
def test_c_mutant_with_the_delist_at_the_end_fails_the_lock_case():
    """The mutant reads and deletes ownership rows BEFORE it delists: it is
    already holding player_items when it waits on the purchase's FOR SHARE,
    so the purchase's row commits behind its back and the closing self-check
    finds it. Any other outcome (a lock timeout, another refusal, a pass)
    fails this test."""
    async def body(conn, _sm):
        return await _in_flight_purchase_case(conn, _delist_moved_to_the_end(_sql()))
    out = asyncio.run(_with_schema("t413_lock_mut", body))
    assert out["blocked"] is True and out["items_locked"] > 0, out
    assert out["err"] is not None and out["err"].startswith(
        "413 post-check FAILED: 1 ownership row(s) of the two albums remain"), out
    assert not _lock_case_holds(out), out


# ---------------------------------------------------------------- c2. players rows: NOWAIT
#
# The cycle the lock statement prevents: B1 (a buyer in the refund set) buys
# another item of the artist (also in the set). The purchase has locked B1 at
# its debit and is about to credit the royalty to the artist's row. A file
# that waited for B1 while holding the artist would close the cycle.

LOCK_BUSY = ("413 refused: a players row this run changes is held by another transaction; "
             "nothing was changed, apply the file again")

OTHER_ITEM = "title_mr413_artist"


async def _contention_case(conn, sql):
    import asyncpg
    import time
    await conn.execute(
        "INSERT INTO shop_items (sku, kind, name, description, price, rarity, catalog_ready,"
        " artist_steam_id) VALUES ($1, 'title', 'Other', 'd', 10, 'common', TRUE, $2)",
        OTHER_ITEM, ARTIST)
    p = await asyncpg.connect(_pg_dsn(), server_settings={
        "search_path": await conn.fetchval("SELECT current_schema()")})
    try:
        await p.execute("BEGIN")
        await p.execute("SELECT price FROM shop_items WHERE sku = '%s' FOR SHARE" % OTHER_ITEM)
        await p.execute("UPDATE players SET gold_spent = gold_spent + 10 WHERE steam_id = '%s'" % B1)
        t0 = time.monotonic()
        task = asyncio.ensure_future(conn.execute(sql))
        blocked = False
        for _ in range(80):
            if task.done():
                break
            w = await p.fetchval("SELECT wait_event_type FROM pg_stat_activity WHERE pid = $1",
                                 conn.get_server_pid())
            if w == "Lock":
                blocked = True
                break
            await asyncio.sleep(0.05)
        elapsed = time.monotonic() - t0
        err = None
        p_committed = False
        if blocked:
            # the hazard: the file is waiting on a players row it never locked
            await p.execute("ROLLBACK")
            try:
                await task
            except Exception as e:                  # noqa: BLE001
                err = str(e)
        else:
            try:
                await task
            except Exception as e:                  # noqa: BLE001
                err = str(e)
            # the purchase goes on to its royalty credit and commits; a bound
            # proves it is not waiting on anything the file held
            await p.execute("SET LOCAL lock_timeout = '3s'")
            await p.execute(
                "INSERT INTO player_items (player_id, item_id, purchase_price, royalty_paid,"
                " royalty_rate_pct, royalty_artist_steam_id, royalty_resolved)"
                " SELECT p.id, si.id, 10, 3, 30, si.artist_steam_id, TRUE FROM players p,"
                " shop_items si WHERE p.steam_id = '%s' AND si.sku = '%s'" % (B1, OTHER_ITEM))
            await p.execute("UPDATE players SET gold_earned = gold_earned + 3"
                            " WHERE steam_id = '%s'" % ARTIST)
            await p.execute("COMMIT")
            p_committed = True
        if err is not None:
            await conn.execute("ROLLBACK")
        state = {
            "listed": await conn.fetchval(
                "SELECT count(*) FROM shop_items WHERE sku = ANY($1::text[]) AND catalog_ready",
                list(SKUS)),
            "owned": await conn.fetchval(
                "SELECT count(*) FROM player_items pi JOIN shop_items si ON si.id = pi.item_id"
                " WHERE si.sku = ANY($1::text[])", list(SKUS)),
            "archive": await conn.fetchval(
                "SELECT to_regclass('music_album_refund_archive') IS NOT NULL"),
        }
        return {"blocked": blocked, "elapsed": elapsed, "err": err,
                "p_committed": p_committed, **state}
    finally:
        await p.close()


@live
def test_c2_a_held_players_row_fails_the_file_at_once_and_the_purchase_completes():
    async def body(conn, _sm):
        out = await _contention_case(conn, _sql())
        # nothing was changed, so the operator applies it again, and it lands
        out["again"] = await _apply(conn)
        out["owned_after"] = await conn.fetchval(
            "SELECT count(*) FROM player_items pi JOIN shop_items si ON si.id = pi.item_id"
            " WHERE si.sku = ANY($1::text[])", list(SKUS))
        out["b1_other"] = await conn.fetchval(
            "SELECT count(*) FROM player_items pi JOIN players p ON p.id = pi.player_id"
            " JOIN shop_items si ON si.id = pi.item_id WHERE p.steam_id = $1 AND si.sku = $2",
            B1, OTHER_ITEM)
        out["artist"] = await _gold(conn, ARTIST)
        return out
    out = asyncio.run(_with_schema("t413_nowait", body))
    assert out["blocked"] is False and out["err"] == LOCK_BUSY, out
    assert out["elapsed"] < 2.0, out
    assert out["p_committed"] is True, out
    assert (out["listed"], out["owned"], out["archive"]) == (2, 5, False), out
    assert any("post-check OK" in n for n in out["again"]), out
    assert out["owned_after"] == 0 and out["b1_other"] == 1, out
    # 5000 + 3 (the purchase's royalty) - 1000 (the take-back)
    assert out["artist"] == (4003, 0), out


@live
def test_c2_mutant_without_the_lock_statement_is_refused_by_the_membership_check():
    """Mutant 1: the lock statement removed. The refund step's membership
    check refuses before it touches a players row: the rows were not locked.
    It refuses so with no contention at all, too (test a would fail)."""
    m1 = _cut(_sql(), LOCK_MARK)

    async def body(conn, _sm):
        quiet = None
        try:
            await conn.execute(m1)
        except Exception as e:                      # noqa: BLE001
            quiet = str(e)
            await conn.execute("ROLLBACK")
        return quiet, await _contention_case(conn, m1)
    quiet, out = asyncio.run(_with_schema("t413_nowait_m1", body))
    # B1, B2, B3 (paid rows) and the artist; B4's free row changes no balance
    want = "413 refused: 4 players row(s) this run would change were not taken by its lock statement"
    assert quiet is not None and quiet.startswith(want), quiet
    assert out["blocked"] is False and out["err"] is not None and out["err"].startswith(want), out


@live
def test_c2_mutant_without_the_lock_or_its_check_waits_on_the_held_row():
    """Mutant 2: the lock statement and the membership check both removed.
    The file then WAITS on the players row the purchase holds -- with the
    rows it already updated locked -- which is the cycle the lock prevents."""
    m2 = _cut(_cut(_sql(), LOCK_MARK), MEMBERSHIP_MARK)

    async def body(conn, _sm):
        return await _contention_case(conn, m2)
    out = asyncio.run(_with_schema("t413_nowait_m2", body))
    assert out["blocked"] is True, out
    assert out["err"] is None, out          # once the purchase rolls back it lands


def _request(version):
    return types.SimpleNamespace(headers={"X-Mod-Version": version},
                                 state=types.SimpleNamespace(mod_version=version))


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
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)


def _sig(steam_id, sku):
    return hmac.new(SECRET.encode(), ("buy:%s:%s" % (steam_id, sku)).encode(),
                    hashlib.sha256).hexdigest()


async def _purchase(db, buyer, sku, price):
    token = main._current_mod_version.set("1.41.0")
    try:
        await main.purchase_item(request=_request("1.41.0"), steam_id=buyer, sku=sku,
                                 sig=_sig(buyer, sku), expected_price=price, db=db)
        return "accepted"
    except HTTPException as e:
        return (e.status_code, str(e.detail))
    finally:
        main._current_mod_version.reset(token)
        await db.rollback()


@live
def test_c_a_purchase_that_starts_during_the_migration_waits_and_gets_409(monkeypatch):
    """The purchase's ORM read sees the row still listed (the migration has
    not committed), its FOR SHARE read waits on the delist's lock, and after
    the commit it reads catalog_ready FALSE under the lock: 409, no debit."""
    _patch_auth(monkeypatch)
    monkeypatch.setattr(main, "_supported_music_skus", lambda request: set(SKUS))

    async def body(conn, sm):
        from sqlalchemy import text
        sql = _sql()
        uncommitted = sql[: sql.rindex("COMMIT;")]
        b2_before = await _gold(conn, B2)
        await conn.execute(uncommitted)
        async with sm() as db:
            pid = (await db.execute(text("SELECT pg_backend_pid()"))).scalar()
            task = asyncio.ensure_future(_purchase(db, B2, CLAVAR, 1000))
            blocked = await _wait_blocked(pid)
            await conn.execute("COMMIT")
            outcome = await task
        owned = await conn.fetchval(
            "SELECT count(*) FROM player_items pi JOIN players p ON p.id = pi.player_id"
            " JOIN shop_items si ON si.id = pi.item_id WHERE p.steam_id = $1 AND si.sku = $2",
            B2, CLAVAR)
        purchase_rows = await conn.fetchval(
            "SELECT count(*) FROM gold_transactions gt JOIN players p ON p.id = gt.player_id"
            " WHERE p.steam_id = $1 AND gt.reason = 'purchase' AND gt.reference_id = $2",
            B2, CLAVAR)
        return blocked, outcome, owned, purchase_rows, b2_before, await _gold(conn, B2)

    blocked, outcome, owned, purchase_rows, before, after = asyncio.run(
        _with_schema("t413_buy_wait", body))
    assert blocked, "the purchase never waited on the delist's lock"
    assert outcome == (409, NOT_SHIPPED), outcome
    assert owned == 0 and purchase_rows == 0
    # the refund of B2's first-album copy (1 gold) is the only move
    assert after == (before[0], before[1] - 1), (before, after)


@live
@pytest.mark.parametrize("sku,price", [(ROUND, 1), (CLAVAR, 1000)])
def test_c_a_purchase_after_the_migration_gets_409_and_no_debit(monkeypatch, sku, price):
    _patch_auth(monkeypatch)

    async def body(conn, sm):
        await conn.execute(_sql())
        before = await _gold(conn, B5)
        n_before = await conn.fetchval("SELECT count(*) FROM gold_transactions")
        async with sm() as db:
            outcome = await _purchase(db, B5, sku, price)
        return (outcome, before, await _gold(conn, B5), n_before,
                await conn.fetchval("SELECT count(*) FROM gold_transactions"),
                await conn.fetchval("SELECT count(*) FROM player_items pi JOIN players p"
                                    " ON p.id = pi.player_id WHERE p.steam_id = $1", B5))

    outcome, before, after, n0, n1, owned = asyncio.run(
        _with_schema("t413_buy_after_%d" % price, body))
    assert outcome == (409, NOT_SHIPPED), outcome
    assert after == before and n1 == n0 and owned == 0


@live
def test_c_control_before_the_migration_the_same_purchase_is_accepted(monkeypatch):
    """Negative control for the two cases above: on the unmigrated fixture
    the first album is bought (so the 409 above is the delist's)."""
    _patch_auth(monkeypatch)

    async def body(conn, sm):
        monkeypatch.setattr(main, "_supported_music_skus", lambda request: set(SKUS))
        async with sm() as db:
            token = main._current_mod_version.set("1.41.0")
            try:
                out = await main.purchase_item(request=_request("1.41.0"), steam_id=B5,
                                               sku=ROUND, sig=_sig(B5, ROUND),
                                               expected_price=1, db=db)
            finally:
                main._current_mod_version.reset(token)
        return out["status"]
    assert asyncio.run(_with_schema("t413_buy_control", body)) == "purchased"


# ---------------------------------------------------------------- d. the readers

async def _pie(db, sid):
    r = await main.get_gold_sources(steam_id=sid, db=db)
    return dict(zip(r.buckets, r.amounts))


@live
def test_d_the_pie_never_counts_the_refund_and_nets_the_royalty(monkeypatch):
    _patch_auth(monkeypatch)

    async def body(conn, sm):
        async with sm() as db:
            buyer_before, artist_before = await _pie(db, B1), await _pie(db, ARTIST)
            board_before = await main.shop_sales_board(db=db)
            mine_before = await main.artist_items(steam_id=ARTIST, request=_request("1.41.0"),
                                                  db=db)
        await conn.execute(_sql())
        async with sm() as db:
            buyer_after, artist_after = await _pie(db, B1), await _pie(db, ARTIST)
            board = await main.shop_sales_board(db=db)
            mine = await main.artist_items(steam_id=ARTIST, request=_request("1.41.0"), db=db)
        return (buyer_before, artist_before, buyer_after, artist_after,
                board_before, board, mine_before, mine)

    bb, ab, ba, aa, board0, board, mine0, mine = asyncio.run(_with_schema("t413_pie", body))
    assert bb == {"level_ups": 2000} and ab == {"achievements": 4000, "shop_sales": 1000}
    assert ba == {"level_ups": 2000}, ba            # the 1001 refund is not income
    assert aa == {"achievements": 4000}, aa          # 1000 royalty minus 1000 reversal
    # sales board: 1000 earned before; after, nothing on sale, sold or earned, so
    # the artist row is dropped (a gross figure would have kept it at 1000)
    assert _earned_by_artist(board0) == {"a": 1000}, board0
    assert _earned_by_artist(board) == {}, board
    # the artist's own item list: earned is net of the reversal
    assert _earned_by_sku(mine0) == {CLAVAR: 1000}, mine0
    assert _earned_by_sku(mine) == {CLAVAR: 0}, mine


# The three readers' SQL as it was before this lane (main at d2d0b93c), to
# prove the code half can land before 413 runs: on data holding neither new
# reason the new readers answer exactly what the old ones answer.
_OLD_PIE = """
        SELECT CASE
                 WHEN gt.reason = 'artist_royalty' THEN 'shop_sales'
                 WHEN gt.reason IN ('bet_win', 'team_bet_payout', 'ffa_bet_win') THEN 'betting'
                 WHEN gt.reason IN ('series_win', 'series_loss', 'bet_tax') THEN 'ranked_1v1'
                 WHEN gt.reason = 'xp' AND m.is_ranked IS TRUE THEN 'ranked_1v1'
                 WHEN gt.reason = 'xp' AND m.is_ranked IS FALSE THEN 'casual_1v1'
                 WHEN gt.reason = 'level_reward' THEN 'level_ups'
                 WHEN gt.reason IN ('team_xp', 'team_series_win', 'team_series_loss', 'team_bet_tax') THEN 'team_2v2'
                 WHEN gt.reason IN ('ovt_xp', 'ovt_series_win', 'ovt_series_loss') THEN 'ovt_1v2'
                 WHEN gt.reason IN ('ffa_xp', 'ffa_placement', 'ffa_bet_tax') THEN 'ffa'
                 WHEN gt.reason = 'booster_monthly' THEN 'boosters'
                 WHEN gt.reason = 'achievement' THEN 'achievements'
                 ELSE 'other'
               END AS bucket,
               SUM(gt.amount) AS total
          FROM gold_transactions gt
          LEFT JOIN matches m ON gt.reason = 'xp' AND m.id::text = gt.reference_id
         WHERE gt.player_id = $1
           AND gt.amount > 0
           AND gt.reason NOT IN ('refund_abandoned', 'team_bet_refund', 'ffa_bet_refund',
                                 'admin_reverse', 'lobby_bet_refund',
                                 'refund_tournament_forfeit')
         GROUP BY 1
"""
# The whole old board and the whole old item list, not their earned figures
# alone: which artists and which items appear is part of the old answer, and
# the comparison below is between complete maps (artist -> earned, sku ->
# earned), so an entry on either side that the other lacks fails it.
_OLD_BOARD = """
        WITH per_item AS (
            SELECT si.artist_steam_id, si.sku, si.name,
                   COUNT(pi.player_id) FILTER (WHERE pi.purchase_price > 0) AS sold,
                   COUNT(pi.player_id) FILTER (WHERE pi.purchase_price = 0) AS gifted,
                   COALESCE(SUM(pi.purchase_price), 0)::bigint AS revenue,
                   ROW_NUMBER() OVER (
                       PARTITION BY si.artist_steam_id
                       ORDER BY COALESCE(SUM(pi.purchase_price), 0) DESC,
                                COUNT(pi.player_id) FILTER (WHERE pi.purchase_price > 0) DESC,
                                si.sku) AS rn,
                   (si.catalog_ready AND COALESCE(si.stock_limit, 0) >= 0) AS on_sale
              FROM shop_items si
              LEFT JOIN player_items pi ON pi.item_id = si.id
             WHERE si.artist_steam_id IS NOT NULL
               AND si.rotation_pool IS DISTINCT FROM 'achievement'
             GROUP BY si.artist_steam_id, si.sku, si.name, si.catalog_ready, si.stock_limit
        ),
        per_artist AS (
            SELECT artist_steam_id,
                   COUNT(*) AS items_total,
                   COUNT(*) FILTER (WHERE on_sale) AS items_on_sale,
                   SUM(sold)::bigint AS sold,
                   SUM(gifted)::bigint AS gifted,
                   SUM(revenue)::bigint AS revenue
              FROM per_item
             GROUP BY artist_steam_id
        ),
        royalties AS (
            SELECT p.steam_id, COALESCE(SUM(gt.amount), 0)::bigint AS earned
              FROM gold_transactions gt
              JOIN players p ON p.id = gt.player_id
             WHERE gt.reason = 'artist_royalty' AND gt.amount > 0
             GROUP BY p.steam_id
        )
        SELECT ap.display_name AS artist,
               pa.items_on_sale, pa.items_total, pa.sold, pa.gifted, pa.revenue,
               COALESCE(ro.earned, 0) AS earned,
               COALESCE(ti.name, '') AS top_name,
               COALESCE(ti.sold, 0)  AS top_sold
          FROM per_artist pa
          JOIN players ap ON ap.steam_id = pa.artist_steam_id
                         AND ap.deleted_at IS NULL
          LEFT JOIN royalties ro ON ro.steam_id = pa.artist_steam_id
          LEFT JOIN per_item ti ON ti.artist_steam_id = pa.artist_steam_id
                               AND ti.rn = 1
         WHERE pa.items_on_sale > 0 OR pa.sold > 0 OR pa.gifted > 0
            OR COALESCE(ro.earned, 0) > 0
         ORDER BY earned DESC, pa.revenue DESC, ap.display_name
         LIMIT 60
"""
_OLD_ITEMS = """
SELECT si.sku, COALESCE(roy.earned, 0) AS earned
  FROM shop_items si
  LEFT JOIN (SELECT gt.reference_id AS sku, SUM(gt.amount) AS earned
               FROM gold_transactions gt
               JOIN players ap ON ap.id = gt.player_id
              WHERE gt.reason = 'artist_royalty' AND ap.steam_id = $1
              GROUP BY gt.reference_id) roy ON roy.sku = si.sku
 WHERE si.artist_steam_id = $1
 ORDER BY si.created_at, si.id
"""

# The reviewer's wrong answer: the album's right earnings plus an unrelated
# title's earnings the old reader never reported.
_PLANTED_SKU, _PLANTED_EARNED = "title_mr413_unrelated", 12345


class _Mismatch(AssertionError):
    """Raised by _step1_compare with (entry, old answer, new answer); a plain
    assert would have its message rewritten into a string by pytest."""


def _step1_compare(out):
    """Complete maps on both sides, compared whole: no filtering to the keys
    the two answers share, and no walk over one side's keys."""
    assert set(out) == {"board", "items"} | {"pie " + s for s in ALL_PLAYERS}, sorted(out)
    for k, (old, new) in out.items():
        if old != new:
            raise _Mismatch(k, old, new)


def _shared_keys_compare(out):
    """The comparison as it was at f3fb3c14, kept only for the negative
    control: it filters both item maps to the keys they share."""
    old_items, listed = out["items"]
    return ({k: v for k, v in old_items.items() if k in listed},
            {k: v for k, v in listed.items() if k in old_items})


def _step1_answers(monkeypatch, plant=False):
    _patch_auth(monkeypatch)

    async def body(conn, sm):
        # edge rows the old readers saw: a negative artist_royalty correction,
        # a zero row, an unlisted positive reason, and match xp of both kinds
        art, b1 = await _pid(conn, ARTIST), await _pid(conn, B1)
        ranked, casual = await conn.fetchval("SELECT gen_random_uuid()"), \
            await conn.fetchval("SELECT gen_random_uuid()")
        await conn.execute("INSERT INTO matches (id, is_ranked) VALUES ($1, TRUE), ($2, FALSE)",
                           ranked, casual)
        await conn.executemany(
            "INSERT INTO gold_transactions (player_id, amount, reason, reference_id)"
            " VALUES ($1, $2, $3, $4)",
            [(art, -7, "artist_royalty", CLAVAR), (art, 0, "artist_royalty", ROUND),
             (b1, 12, "title_refunded", "t"), (b1, 30, "xp", str(ranked)),
             (b1, 40, "xp", str(casual)), (b1, 25, "refund_abandoned", "x")])
        assert await conn.fetchval(
            "SELECT count(*) FROM gold_transactions"
            " WHERE reason IN ('music_album_refund', 'music_royalty_reversal')") == 0
        assert sorted(r["steam_id"] for r in await conn.fetch(
            "SELECT steam_id FROM players")) == sorted(ALL_PLAYERS)
        out = {}
        async with sm() as db:
            for sid in ALL_PLAYERS:
                pid = await _pid(conn, sid)
                old = {r["bucket"]: int(r["total"]) for r in await conn.fetch(_OLD_PIE, pid)}
                out["pie " + sid] = (old, await _pie(db, sid))
            board = await main.shop_sales_board(db=db)
            mine = await main.artist_items(steam_id=ARTIST, request=_request("1.41.0"), db=db)
        if plant:
            mine["items"].append({"sku": _PLANTED_SKU, "earned": _PLANTED_EARNED})
        old_board = {r["artist"]: int(r["earned"]) for r in await conn.fetch(_OLD_BOARD)}
        out["board"] = (old_board, _earned_by_artist(board))
        old_items = {r["sku"]: int(r["earned"]) for r in await conn.fetch(_OLD_ITEMS, ARTIST)}
        out["items"] = (old_items, _earned_by_sku(mine))
        return out

    return asyncio.run(_with_schema("t413_step1", body))


@live
def test_step1_the_readers_answer_as_before_on_data_without_the_new_reasons(monkeypatch):
    out = _step1_answers(monkeypatch)
    _step1_compare(out)
    assert out["board"][0] == {"a": 1000} and out["items"][0] == {CLAVAR: 993}, out
    assert out["pie " + B1][0] == {"level_ups": 2000, "other": 12, "ranked_1v1": 30,
                                   "casual_1v1": 40}, out


@live
def test_step1_negative_control_an_extra_unrelated_title_fails_the_comparison(monkeypatch):
    out = _step1_answers(monkeypatch, plant=True)
    old_items, new_items = out["items"]
    # the plant landed beside the right figure, and the old reader never had it
    assert new_items == {CLAVAR: 993, _PLANTED_SKU: _PLANTED_EARNED}, out
    assert old_items == {CLAVAR: 993}, out
    # the comparison catches it, on the items entry and for that reason
    with pytest.raises(_Mismatch) as caught:
        _step1_compare(out)
    assert caught.value.args == ("items", {CLAVAR: 993},
                                 {CLAVAR: 993, _PLANTED_SKU: _PLANTED_EARNED}), caught.value.args
    # and the shared-key comparison it replaces lets the same answer through
    old_shared, new_shared = _shared_keys_compare(out)
    assert old_shared == new_shared == {CLAVAR: 993}


async def _listed_skus(db, sid):
    token = main._current_mod_version.set("1.41.0")
    try:
        items = (await main.list_shop_items(request=_request("1.41.0"), steam_id=sid,
                                            db=db))["items"]
    finally:
        main._current_mod_version.reset(token)
    return {i["sku"]: i.get("owned") for i in items}


@live
def test_d_the_listing_for_a_former_owner_no_longer_lists_either_album(monkeypatch):
    async def body(conn, sm):
        monkeypatch.setattr(main, "_supported_music_skus", lambda request: set(SKUS))
        async with sm() as db:
            before = await _listed_skus(db, B1)
        await conn.execute(_sql())
        async with sm() as db:
            after = await _listed_skus(db, B1)
        return before, after
    before, after = asyncio.run(_with_schema("t413_listing", body))
    assert before.get(ROUND) is True and before.get(CLAVAR) is True, before   # control
    assert after.get(FACE) is True, after
    # the whole listing: the two albums gone, every other entry as it was
    assert after == {k: v for k, v in before.items() if k not in SKUS}, (before, after)


# ---------------------------------------------------------------- R4: account deletion

def test_r4_account_deletion_leaves_the_archive_keyed_to_the_anonymised_row(monkeypatch):
    """On the full replayed schema: 413 archives a buyer's rows, then
    delete_player_data anonymises that buyer. The archive holds no steam id
    of anyone, its rows still resolve to the buyer's players row, and that
    row is now the anonymised one (deleted_at set, steam_id replaced), as the
    deletion path leaves the ledger."""
    import cf_asm
    import cf_pg
    cf_pg.require_live_pg()
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)

    async def inside():
        async with cf_pg.case("mr413del") as (c, sm):
            conn = c.conn
            assert await conn.fetchval(
                "SELECT count(*) FROM shop_items WHERE kind = 'music_album'") == 0
            await _seed(conn)
            released = await conn.fetchval(
                "SELECT array_agg(released_at ORDER BY sku) FROM shop_items"
                " WHERE sku = ANY($1::text[])", list(SKUS))
            trig = await conn.fetchval(
                "SELECT count(*) FROM pg_trigger WHERE tgrelid = 'shop_items'::regclass"
                " AND tgname = 'trg_shop_item_catalog_release'")
            await conn.execute(_sql())
            pid = await _pid(conn, B1)
            sig = hmac.new(SECRET.encode(), ("delete:%s" % B1).encode(),
                           hashlib.sha256).hexdigest()
            async with sm() as db:
                await main.delete_player_data(B1, cf_asm.FakeRequest(), sig=sig, _slot=None, db=db)
            row = await conn.fetchrow(
                "SELECT steam_id, deleted_at FROM players WHERE id = $1", pid)
            kept = await conn.fetchval(
                "SELECT count(*) FROM music_album_refund_archive WHERE player_id = $1", pid)
            ledger = await conn.fetchval(
                "SELECT count(*) FROM gold_transactions WHERE player_id = $1"
                " AND reason = 'music_album_refund'", pid)
            naming = {}
            for sid in ALL_PLAYERS:
                naming[sid] = await conn.fetchval(
                    "SELECT count(*) FROM music_album_refund_archive x"
                    " WHERE strpos(CAST(x AS text), $1) > 0", sid)
            released_after = await conn.fetchval(
                "SELECT array_agg(released_at ORDER BY sku) FROM shop_items"
                " WHERE sku = ANY($1::text[])", list(SKUS))
            return row, kept, ledger, naming, trig, released, released_after

    row, kept, ledger, naming, trig, released, released_after = asyncio.run(inside())
    assert row["deleted_at"] is not None and row["steam_id"].startswith("deleted_"), dict(row)
    assert row["steam_id"] != B1
    assert kept == 2 and ledger == 2, (kept, ledger)
    assert naming == {s: 0 for s in ALL_PLAYERS}, naming
    # the publish trigger exists on this schema and stayed inert on TRUE -> FALSE
    assert trig == 1 and released_after == released
