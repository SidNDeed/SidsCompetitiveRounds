"""The title-ladder route, SERVED by main.app against a real PostgreSQL.

test_title_ladder_route_contract.py proves the route is in `app.routes` and
pins the answer's keys against a fake session. Three things it cannot show,
and this file does:

  * that main.app ANSWERS the path over HTTP, through the middleware a
    client's request crosses (version gate, rate limit, maintenance gate,
    replica write gate). A known player is a 200. An unknown steam id is the
    route's OWN 404, {"detail": "Player not found"}; a build without the
    mount answers a routing 404, {"detail": "Not Found"}, and the two are told
    apart here on the same request stack.
  * that what the route reads exists once migration 331 is RUN -- executed,
    not parsed -- on the PostgreSQL major the primary runs, and that the item
    ids the route reports are the rows 331 inserted.
  * that the route is a READ. Every statement it sends is captured at the
    cursor: each is a SELECT with no row-locking clause, and the row counts
    of every table it could touch are unchanged by the request.

The schema is the ladder suite's own live harness (LADDER_PREREQ, then the
331 file), with one widening: the route's `select(Player)` names every column
the Player model maps, and LADDER_PREREQ's `players` carries only the four the
hook needs. The rest are added nullable and default-free from the model
itself, so a column added to the model later cannot break this file silently.

Live PostgreSQL is REQUIRED, and a missing DSN FAILS, naming the variable --
the same gate, the same variable and the same polarity as the live half of
test_title_ladders.py:
    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    LADDER_TEST_PG_OPTOUT=1   waives the live cases deliberately
Optional: LADDER_ROUTE_SQL_LOG names a file each case appends the exact SQL
the route sent to, for the evidence log.
"""

import asyncio
import io
import os
import re
import sys
import uuid
from collections import defaultdict, deque

import httpx
import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import main  # noqa: E402
import title_ladders as tl  # noqa: E402
from models import Player  # noqa: E402
# Reused, not copied: the route is exercised on exactly the schema the hook's
# live tests run migration 331 on.
from test_title_ladders import LADDER_PREREQ, MIGRATION  # noqa: E402

try:
    import asyncpg as _asyncpg
except ImportError:                                    # pragma: no cover
    _asyncpg = None

DSN_VAR = "LADDER_TEST_PG_DSN"
OPTOUT_VAR = "LADDER_TEST_PG_OPTOUT"
DSN = (os.environ.get(DSN_VAR) or "").replace("postgresql+asyncpg://", "postgresql://")
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"
SQL_LOG = os.environ.get("LADDER_ROUTE_SQL_LOG")

# Synthetic ids below 76561197960265728, the first individual-account id, so
# none of them can name a real account.
KNOWN = "76561190000000201"
BARE = "76561190000000202"
UNKNOWN = "76561190000000203"

# Every table the route reads or could be mistaken for writing.
WATCHED = ("players", "player_items", "shop_items", "title_ladders",
           "title_ladder_progress", "title_ladder_credits")

_ROW_LOCK = re.compile(r"\bFOR\s+(?:NO\s+KEY\s+UPDATE|UPDATE|KEY\s+SHARE|SHARE)\b", re.I)
_TABLES = re.compile(r"\b(?:FROM|JOIN)\s+(\w+)", re.I)


def _require_live_pg():
    """Fail, not skip: a skipped live case reports exit 0 for coverage that
    did not run."""
    if DSN and _asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: the served-route coverage is "
                    "deliberately waived." % (DSN_VAR, OPTOUT_VAR))
    if _asyncpg is None:
        pytest.fail("asyncpg is not installed, so the route was never served "
                    "against migration 331's tables. Install it, or set %s=1 "
                    "to waive deliberately." % OPTOUT_VAR)
    pytest.fail(
        "%s is unset, so main.app never served the title-ladder route against "
        "a database migration 331 had actually run on. Point it at a "
        "throwaway database, or set %s=1 to waive the coverage deliberately."
        % (DSN_VAR, OPTOUT_VAR))


def _run(coro):
    return asyncio.run(coro)


# -- the schema: LADDER_PREREQ, players widened to the model, then 331 --------

async def _build(conn, schema):
    await conn.execute('CREATE SCHEMA "%s"' % schema)
    await conn.execute('SET search_path TO "%s"' % schema)
    await conn.execute(LADDER_PREREQ)
    have = {r["column_name"] for r in await conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        " WHERE table_schema = $1 AND table_name = 'players'", schema)}
    dialect = postgresql.dialect()
    for col in Player.__table__.columns:
        if col.name not in have:
            await conn.execute('ALTER TABLE players ADD COLUMN "%s" %s'
                               % (col.name, col.type.compile(dialect=dialect)))
    await conn.execute(io.open(MIGRATION, encoding="utf-8").read())


async def _seed(conn):
    """KNOWN owns the first three rat rungs, has 30 series on rat and wears
    rung 3; BARE owns nothing and has no progress row. Returns 331's sku->id
    map and KNOWN's owned skus."""
    ids = {r["sku"]: r["id"] for r in await conn.fetch(
        "SELECT sku, id FROM shop_items WHERE sku = ANY($1::varchar[])",
        list(tl.ALL_SKUS))}
    known = await conn.fetchval(
        "INSERT INTO players (steam_id) VALUES ($1) RETURNING id", KNOWN)
    await conn.execute("INSERT INTO players (steam_id) VALUES ($1)", BARE)
    owned = [r["sku"] for r in tl.LINES["rat"]["rungs"] if r["tier"] <= 3]
    for sku in owned:
        await conn.execute(
            "INSERT INTO player_items (player_id, item_id, purchase_price) "
            "VALUES ($1, $2, 0)", known, ids[sku])
    await conn.execute(
        "INSERT INTO title_ladder_progress (player_id, line, games, tier) "
        "VALUES ($1, 'rat', 30, 3)", known)
    await conn.execute("UPDATE players SET active_title_id = $1 WHERE id = $2",
                       ids["title_ladder_rat_3"], known)
    return ids, owned


async def _counts(conn):
    return {t: await conn.fetchval('SELECT count(*) FROM "%s"' % t) for t in WATCHED}


def _log_sql(case, statements):
    if not SQL_LOG:
        return
    with io.open(SQL_LOG, "a", encoding="utf-8") as fh:
        fh.write("== %s: %d statement(s)\n" % (case, len(statements)))
        for i, s in enumerate(statements, 1):
            fh.write("-- [%d]\n%s\n" % (i, s))


async def _serve(schema, paths):
    """GET each path from main.app with the route's session bound to
    `schema`. Returns [(status, json, statements)] -- the statements are what
    that one request sent through the cursor, nothing else."""
    engine = create_async_engine(
        DSN.replace("postgresql://", "postgresql+asyncpg://"),
        connect_args={"server_settings": {"search_path": schema}},
        poolclass=NullPool)
    # The dialect's first-connect probes are not the route's SQL; take them
    # before the recorder is attached.
    async with engine.connect() as c:
        await c.exec_driver_sql("SELECT 1")
    session = async_sessionmaker(engine, expire_on_commit=False)
    captured = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        captured.append(statement)

    async def _db():
        async with session() as db:
            yield db

    out = []
    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    main.app.dependency_overrides[tl.get_db] = _db
    try:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://ladder.test") as client:
            for path in paths:
                del captured[:]
                r = await client.get(
                    path, headers={"X-Mod-Version": main.MIN_MOD_VERSION_EFFECTIVE})
                try:
                    body = r.json()
                except ValueError:
                    body = r.text
                out.append((r.status_code, body, list(captured)))
    finally:
        main.app.dependency_overrides.pop(tl.get_db, None)
        event.remove(engine.sync_engine, "before_cursor_execute", _record)
        await engine.dispose()
    return out


async def _case(paths):
    """A fresh schema, seeded; the requests; the counts either side; the
    schema dropped whatever happens."""
    schema = "ladder_route_%s" % uuid.uuid4().hex[:10]
    conn = await _asyncpg.connect(DSN)
    try:
        await _build(conn, schema)
        ids, owned = await _seed(conn)
        before = await _counts(conn)
        answers = await _serve(schema, paths)
        after = await _counts(conn)
        return ids, owned, before, after, answers
    finally:
        try:
            await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
        finally:
            await conn.close()


def _url(steam_id):
    # A literal, not url_path_for: this is the path the client calls, and a
    # path derived from the router would follow a rename silently.
    return "/api/v1/players/%s/title-ladders" % steam_id


def _assert_read_only(statements, tables):
    """Each statement a SELECT with no row lock, reading exactly `tables`,
    in the route's order."""
    assert [_TABLES.findall(s) for s in statements] == tables, statements
    for s in statements:
        assert s.lstrip().upper().startswith("SELECT"), s
        assert not _ROW_LOCK.search(s), s


def _line(answer, line):
    return [ln for ln in answer["ladders"] if ln["line"] == line][0]


@pytest.fixture(autouse=True)
def _fresh_rate_buckets(monkeypatch):
    """The rate limiter's buckets are module state keyed on the client
    address, which every ASGI test in the process shares; start this file's
    requests from an empty window rather than from whatever ran before."""
    monkeypatch.setattr(main, "_RL_BUCKETS", defaultdict(deque))


# -- the cases ----------------------------------------------------------------

def test_pg_migration_331_creates_what_the_route_reads():
    """The route reads `title_ladder_progress` and 331's 48 `shop_items`
    rows (players and player_items predate it). Asserted after a fresh run of
    the real file, before any request."""
    _require_live_pg()
    schema = "ladder_route_%s" % uuid.uuid4().hex[:10]

    async def _go():
        conn = await _asyncpg.connect(DSN)
        try:
            await _build(conn, schema)
            regs = {t: await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", t)
                    for t in ("title_ladders", "title_ladder_progress",
                              "title_ladder_credits")}
            cols = [r["column_name"] for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                " WHERE table_schema = $1 AND table_name = 'title_ladder_progress' "
                " ORDER BY ordinal_position", schema)]
            skus = await conn.fetchval(
                "SELECT count(*) FROM shop_items WHERE sku = ANY($1::varchar[])",
                list(tl.ALL_SKUS))
            return regs, cols, skus
        finally:
            try:
                await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
            finally:
                await conn.close()

    regs, cols, skus = _run(_go())
    assert regs == {"title_ladders": True, "title_ladder_progress": True,
                    "title_ladder_credits": True}, regs
    assert cols == ["player_id", "line", "games", "tier", "updated_at"], cols
    assert skus == len(tl.ALL_SKUS) == 48, (skus, len(tl.ALL_SKUS))


def test_pg_a_known_player_is_a_200_with_their_ladder_rows():
    _require_live_pg()
    ids, owned, before, after, answers = _run(_case([_url(KNOWN)]))
    status, body, sql = answers[0]
    _log_sql("known player", sql)
    assert status == 200, (
        "%s answered %s %r -- a routing 404 here means main.app does not "
        "mount the ladder router" % (_url(KNOWN), status, body))
    assert body["steam_id"] == KNOWN
    assert body["active_line"] == "rat"
    assert [ln["line"] for ln in body["ladders"]] == [ld["line"] for ld in tl.LADDERS]
    rat = _line(body, "rat")
    assert (rat["games"], rat["tier"]) == (30, 3), rat
    assert (rat["next_tier"], rat["next_threshold"], rat["games_to_next"]) == (4, 75, 45), rat
    assert rat["next_names"] == ["Rat King", "Rat Queen"], rat["next_names"]
    assert [r["sku"] for r in rat["rungs"] if r["owned"]] == owned
    assert [r["sku"] for r in rat["rungs"] if r["active"]] == ["title_ladder_rat_3"]
    # Every item id is the row migration 331 inserted, read back through the
    # route: the answer came from this database, not from the catalogue module.
    for ln in body["ladders"]:
        for r in ln["rungs"]:
            assert r["item_id"] == ids[r["sku"]], (r["sku"], r["item_id"])
    others = [ln for ln in body["ladders"] if ln["line"] != "rat"]
    assert all(ln["games"] == 0 and not any(r["owned"] for r in ln["rungs"])
               for ln in others)
    _assert_read_only(sql, [["players"], ["shop_items", "player_items"],
                            ["shop_items"], ["title_ladder_progress"],
                            ["shop_items"]])
    assert after == before, (before, after)


def test_pg_a_player_with_no_titles_gets_every_line_with_nothing_owned():
    """No titles is not an empty answer: all eight lines, all 48 rungs,
    games 0, tier 1, nothing owned or worn. The route never answers an empty
    `ladders` list for a player it knows."""
    _require_live_pg()
    ids, owned, before, after, answers = _run(_case([_url(BARE)]))
    status, body, sql = answers[0]
    _log_sql("player with no titles", sql)
    assert status == 200, (status, body)
    assert body["steam_id"] == BARE and body["active_line"] is None
    assert len(body["ladders"]) == 8
    assert sum(len(ln["rungs"]) for ln in body["ladders"]) == 48
    for ln in body["ladders"]:
        assert (ln["games"], ln["tier"]) == (0, 1), ln["line"]
        assert not any(r["owned"] or r["active"] for r in ln["rungs"]), ln["line"]
    # No worn title, so no fifth statement.
    _assert_read_only(sql, [["players"], ["shop_items", "player_items"],
                            ["shop_items"], ["title_ladder_progress"]])
    assert after == before, (before, after)


def test_pg_an_unknown_steam_id_is_the_routes_own_404():
    """The route's 404 and a routing 404 share a status code, so the body is
    what tells them apart; both are asked here, on the same stack, so this
    assertion cannot be satisfied by a build that does not mount the route."""
    _require_live_pg()
    unmounted = _url(UNKNOWN) + "-not-a-route"
    ids, owned, before, after, answers = _run(_case([_url(UNKNOWN), unmounted]))
    (status, body, sql), (r_status, r_body, r_sql) = answers
    _log_sql("unknown steam id", sql)
    assert (status, body) == (404, {"detail": "Player not found"}), (status, body)
    _assert_read_only(sql, [["players"]])
    assert (r_status, r_body) == (404, {"detail": "Not Found"}), (r_status, r_body)
    assert r_sql == [], r_sql
    assert after == before, (before, after)
