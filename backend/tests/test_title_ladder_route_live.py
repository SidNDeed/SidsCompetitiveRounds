"""The title-ladder route, SERVED by main.app against a real PostgreSQL.

test_title_ladder_route_contract.py proves the route is in `app.routes` and
pins the answer's keys against a fake session. Five things it cannot show,
and this file does:

  * that main.app ANSWERS the path over HTTP, through the middleware a
    client's request crosses (version gate, rate limit, maintenance gate,
    replica write gate). A known player is a 200. An unknown steam id is the
    route's OWN 404, {"detail": "Player not found"}; a build without the
    mount answers a routing 404, {"detail": "Not Found"}, and the two are told
    apart here on the same request stack.
  * that what the route reads exists once migrations 331 and 365 are RUN -- executed,
    not parsed -- on the PostgreSQL major the primary runs, and that the item
    ids the route reports are the rows they inserted.
  * that the route is a READ of one snapshot. Every statement it sends is
    captured at the cursor: the first is exactly the SET TRANSACTION that
    makes the request REPEATABLE READ and READ ONLY, each one after it is a
    SELECT with no row-locking clause, and the row counts of every table it
    could touch are unchanged by the request.
  * that the snapshot is what makes an answer one committed state. A request
    paused after each of its statements in turn, while a second connection
    commits a real ladder credit, answers the whole state before that commit
    or the whole state after it -- which one is fixed by where the pause
    falls -- and never a mix. The same request with SELECT 1 sent in place
    of the SET answers the mix: that is the negative control.
  * that `owned` asks the shop-owner exemption the question /shop/items and
    equip ask (main._auto_owned). The exempt account, wearing an entry rung
    it never bought, reads that rung owned and active, every entry rung
    owned and every granted-only rung unowned; an ordinary account with the
    same rows reads nothing owned.

The schema is the ladder suite's own live harness (LADDER_PREREQ, then the
331 and 365 files), with one widening: the route's `select(Player)` names every column
the Player model maps, and LADDER_PREREQ's `players` carries only the four the
hook needs. The rest are added nullable and default-free from the model
itself, so a column added to the model later cannot break this file silently.
Each case builds it in a throwaway schema of its own through ladder_pg_harness:
every connection bound to that schema, and a census before anything is
created or dropped.

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
from collections import defaultdict, deque

import httpx
import pytest
from sqlalchemy import event, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import main  # noqa: E402
import title_ladders as tl  # noqa: E402
from models import Player  # noqa: E402
# Reused, not copied: the route is exercised on exactly the schema the hook's
# live tests run migration 331 on.
from test_title_ladders import LADDER_PREREQ, MIGRATION, MIGRATION_365  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402

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
# The race's player, and D7's ordinary account.
RACER = "76561190000000204"
PLAIN = "76561190000000205"

# The statement that makes one request one snapshot (title_ladders.py, D9).
SNAPSHOT_SQL = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"

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


# -- the schema: LADDER_PREREQ, players widened to the model, then 331, 365 ---

async def _build(case):
    """Into case.schema, on case.conn (bound to it): LADDER_PREREQ, players
    widened to the model, then the 331 and 365 files as written, in that
    order (365 is the five-tier catalogue the module describes). Sealed, so
    the drop's
    census knows what the case created."""
    conn, schema = case.conn, case.schema
    await conn.execute(LADDER_PREREQ)
    have = {r["column_name"] for r in await conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        " WHERE table_schema = $1 AND table_name = 'players'", schema)}
    dialect = postgresql.dialect()
    for col in Player.__table__.columns:
        if col.name not in have:
            await conn.execute('ALTER TABLE %s.players ADD COLUMN "%s" %s'
                               % (harness.quoted(schema), col.name,
                                  col.type.compile(dialect=dialect)))
    await conn.execute(io.open(MIGRATION, encoding="utf-8").read())
    await conn.execute(io.open(MIGRATION_365, encoding="utf-8").read())
    await case.seal()


async def _seed(conn):
    """KNOWN owns the first three rat rungs, has 50 games on rat and wears
    rung 3; BARE owns nothing and has no progress row. Returns the sku->id
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
        "VALUES ($1, 'rat', 50, 3)", known)
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


def _log_line(line):
    if not SQL_LOG:
        return
    with io.open(SQL_LOG, "a", encoding="utf-8") as fh:
        fh.write("== %s\n" % line)


async def _serve(schema, paths, wrap=None):
    """GET each path from main.app with the route's session bound to
    `schema`. Returns [(status, json, statements)] -- the statements are what
    that one request sent through the cursor, nothing else. `wrap`, when
    given, is handed each request's real session and returns what the route
    receives in its place."""
    engine = harness.bound_engine(DSN, schema)
    # The dialect's first-connect probes are not the route's SQL; take them
    # before the recorder is attached, and check the binding while at it.
    async with engine.connect() as c:
        path = list((await c.exec_driver_sql(harness.PATH_SQL)).scalar_one())
    assert path == ["pg_catalog", schema], path
    session = async_sessionmaker(engine, expire_on_commit=False)
    captured = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        captured.append(statement)

    async def _db():
        async with session() as db:
            yield db if wrap is None else wrap(db)

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


async def _case(paths, seed_more=None):
    """A fresh schema, built and seeded (`seed_more(conn, ids)` adds rows
    after _seed's); the requests; the counts either side; the schema dropped
    under the census whatever happens."""
    async with harness.CaseSchema(DSN, "ladder_route") as case:
        await _build(case)
        ids, owned = await _seed(case.conn)
        if seed_more is not None:
            await seed_more(case.conn, ids)
        before = await _counts(case.conn)
        answers = await _serve(case.schema, paths)
        after = await _counts(case.conn)
        return ids, owned, before, after, answers


def _url(steam_id):
    # A literal, not url_path_for: this is the path the client calls, and a
    # path derived from the router would follow a rename silently.
    return "/api/v1/players/%s/title-ladders" % steam_id


def _assert_read_only(statements, tables):
    """Statement 1 exactly the SET that makes the request one REPEATABLE
    READ, READ ONLY snapshot; every statement after it a SELECT with no row
    lock, the SELECTs reading exactly `tables`, in the route's order."""
    assert statements[:1] == [SNAPSHOT_SQL], statements[:1]
    reads = statements[1:]
    assert [_TABLES.findall(s) for s in reads] == tables, reads
    for s in reads:
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

def test_pg_migrations_331_and_365_create_what_the_route_reads():
    """The route reads `title_ladder_progress` (331's, with 365's `streak`)
    and the catalogue's 160 `shop_items` rows (players and player_items
    predate them). Asserted after a fresh run of the real files, before any
    request."""
    _require_live_pg()

    async def _go():
        async with harness.CaseSchema(DSN, "ladder_route") as case:
            await _build(case)
            conn = case.conn
            regs = {t: await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", t)
                    for t in ("title_ladders", "title_ladder_progress",
                              "title_ladder_credits")}
            cols = [r["column_name"] for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                " WHERE table_schema = $1 AND table_name = 'title_ladder_progress' "
                " ORDER BY ordinal_position", case.schema)]
            skus = await conn.fetchval(
                "SELECT count(*) FROM shop_items WHERE sku = ANY($1::varchar[])",
                list(tl.ALL_SKUS))
            return regs, cols, skus

    regs, cols, skus = _run(_go())
    assert regs == {"title_ladders": True, "title_ladder_progress": True,
                    "title_ladder_credits": True}, regs
    assert cols == ["player_id", "line", "games", "tier", "updated_at", "streak"], cols
    assert skus == len(tl.ALL_SKUS) == 160, (skus, len(tl.ALL_SKUS))


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
    assert (rat["games"], rat["tier"]) == (50, 3), rat
    assert (rat["next_tier"], rat["next_threshold"], rat["games_to_next"]) == (4, 100, 50), rat
    assert rat["next_names"] == ["Rat Lord"], rat["next_names"]
    assert [r["sku"] for r in rat["rungs"] if r["owned"]] == owned
    assert [r["sku"] for r in rat["rungs"] if r["active"]] == ["title_ladder_rat_3"]
    # Every item id is the row the migrations inserted, read back through the
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
    """No titles is not an empty answer: all 32 ladders, all 160 rungs,
    games 0, tier 1, nothing owned or worn. The route never answers an empty
    `ladders` list for a player it knows."""
    _require_live_pg()
    ids, owned, before, after, answers = _run(_case([_url(BARE)]))
    status, body, sql = answers[0]
    _log_sql("player with no titles", sql)
    assert status == 200, (status, body)
    assert body["steam_id"] == BARE and body["active_line"] is None
    assert len(body["ladders"]) == 32
    assert sum(len(ln["rungs"]) for ln in body["ladders"]) == 160
    for ln in body["ladders"]:
        assert (ln["games"], ln["tier"]) == (0, 1), ln["line"]
        assert not any(r["owned"] or r["active"] for r in ln["rungs"]), ln["line"]
    # No worn title, so no fifth SELECT: the SET, then four reads.
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


# -- one snapshot: a request racing a ladder credit (D9) ------------------------

OLD_RAT = (14, 1, ["title_ladder_rat_1"], ["title_ladder_rat_1"])
NEW_RAT = (15, 2, ["title_ladder_rat_1", "title_ladder_rat_2"], ["title_ladder_rat_2"])
# Games and tier after the credit, ownership and the worn title before it.
MIXED_RAT = (15, 2, ["title_ladder_rat_1"], ["title_ladder_rat_1"])
WORN_READS = [["players"], ["shop_items", "player_items"], ["shop_items"],
              ["title_ladder_progress"], ["shop_items"]]


async def _seed_racer(conn, ids):
    """RACER owns and wears rat rung 1 at 14 games, so the fifteenth credited
    game moves games, tier, ownership and the worn title in one commit."""
    pid = await conn.fetchval(
        "INSERT INTO players (steam_id) VALUES ($1) RETURNING id", RACER)
    await conn.execute(
        "INSERT INTO player_items (player_id, item_id, purchase_price) "
        "VALUES ($1, $2, 0)", pid, ids["title_ladder_rat_1"])
    await conn.execute(
        "INSERT INTO title_ladder_progress (player_id, line, games, tier) "
        "VALUES ($1, 'rat', 14, 1)", pid)
    await conn.execute("UPDATE players SET active_title_id = $1 WHERE id = $2",
                       ids["title_ladder_rat_1"], pid)
    return pid


class _Paused:
    """A request's real session with one change: after its k-th execute
    returns -- its rows already read, an AsyncSession result being buffered
    -- it awaits `writer()` before handing the result back to the route.
    With `control`, its first statement, which must be the SET, is sent as
    SELECT 1 instead: the request then runs READ COMMITTED with every other
    statement where it was."""

    def __init__(self, db, k, writer, control=False):
        self._db, self._k, self._writer, self._control = db, k, writer, control
        self.sent = 0
        self.paused_after = None

    def __getattr__(self, name):
        return getattr(self._db, name)

    async def execute(self, statement, *args, **kwargs):
        if self._control and self.sent == 0:
            assert str(statement) == SNAPSHOT_SQL, str(statement)
            statement = text("SELECT 1")
        result = await self._db.execute(statement, *args, **kwargs)
        self.sent += 1
        if self.sent == self._k:
            await self._writer()
            self.paused_after = self.sent
        return result


async def _credit(schema, pid, reference_id):
    """The real hook for one player, on an engine and a connection of its
    own, committed. Returns its events."""
    engine = harness.bound_engine(DSN, schema)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            events = await tl.record_completed_games(
                db, [pid], mode="1v1", reference_id=reference_id)
            await db.commit()
            return events
    finally:
        await engine.dispose()


def _rat(body):
    """What one rat credit moves in an answer: (rat games, rat tier, owned
    rat skus, every worn sku)."""
    rat = _line(body, "rat")
    return (rat["games"], rat["tier"],
            [r["sku"] for r in rat["rungs"] if r["owned"]],
            [r["sku"] for ln in body["ladders"] for r in ln["rungs"] if r["active"]])


async def _race(k, control=False):
    """On one fresh schema: a request before the credit (OLD), a request
    paused after its statement k while _credit commits, a request after
    (NEW). Returns the three answers, the writer's events, the paused
    sessions and RACER's credit rows."""
    async with harness.CaseSchema(DSN, "ladder_route") as case:
        await _build(case)
        ids, _owned = await _seed(case.conn)
        pid = await _seed_racer(case.conn, ids)
        events, sessions = [], []

        async def _writer():
            events.append(await _credit(case.schema, pid, "race-k%d" % k))

        def _wrap(db):
            sessions.append(_Paused(db, k, _writer, control))
            return sessions[-1]

        (old,) = await _serve(case.schema, [_url(RACER)])
        (paused,) = await _serve(case.schema, [_url(RACER)], wrap=_wrap)
        (new,) = await _serve(case.schema, [_url(RACER)])
        credits = await case.conn.fetchval(
            "SELECT count(*) FROM title_ladder_credits WHERE player_id = $1", pid)
        return old, paused, new, events, sessions, credits


@pytest.mark.parametrize("k", [1, 2, 3, 4, 5])
def test_pg_a_request_racing_a_credit_answers_one_committed_state(k):
    """D9 (design V3 section 7a, test 1). RACER wears rat rung 1 at 14 games.
    A request pauses after its statement k while a second connection runs
    the real record_completed_games for RACER and commits: games 15, tier 2,
    rung 2 granted and worn. The paused answer must equal the answer before
    that commit (OLD) or the one after it (NEW), whole -- and which one is
    fixed. k = 1 pauses after the SET, before any SELECT has taken the
    snapshot, so it reads NEW; k = 2..5 pause after the snapshot was taken,
    so they read OLD."""
    _require_live_pg()
    old, paused, new, events, sessions, credits = _run(_race(k))
    (o_status, o_body, o_sql), (p_status, p_body, p_sql), (n_status, n_body, n_sql) = (
        old, paused, new)
    _log_sql("race, paused after statement %d" % k, p_sql)
    assert (o_status, p_status, n_status) == (200, 200, 200), (o_status, p_status, n_status)
    # The writer ran where it was put, once, and its commit landed.
    assert [s.paused_after for s in sessions] == [k], [s.paused_after for s in sessions]
    assert [[e["to_tier"] for e in ev] for ev in events] == [[2]], events
    assert credits == 1, credits
    # OLD and NEW are the two committed states, and one credit tells them apart.
    assert _rat(o_body) == OLD_RAT, _rat(o_body)
    assert _rat(n_body) == NEW_RAT, _rat(n_body)
    assert o_body != n_body
    want, name = (n_body, "NEW") if k == 1 else (o_body, "OLD")
    assert p_body == want, (
        "paused after statement %d the route answered %r; its snapshot makes "
        "that %s %r, whole" % (k, _rat(p_body), name, _rat(want)))
    for sql in (o_sql, p_sql, n_sql):
        _assert_read_only(sql, WORN_READS)


def test_pg_without_the_snapshot_the_same_race_reads_a_mixed_state():
    """#391's negative control for the race above (design V3 section 7a,
    test 2): the same race paused after statement 3, with SELECT 1 sent in
    place of the SET, so the request runs READ COMMITTED with every other
    statement where it was. It must read the state no commit had -- games 15
    and tier 2 from after the credit, the ownership and the worn title from
    before it -- which is neither OLD nor NEW. An OLD or NEW answer here
    means the race is not interleaving at all, and this fails."""
    _require_live_pg()
    old, paused, new, events, sessions, credits = _run(_race(3, control=True))
    (o_status, o_body), (n_status, n_body) = old[:2], new[:2]
    p_status, p_body, p_sql = paused
    _log_sql("race control: SELECT 1 in place of the SET, paused after statement 3", p_sql)
    _log_line("race control answer (rat games, rat tier, owned rat rungs, worn): %r "
              "-- OLD %r, NEW %r" % (_rat(p_body), _rat(o_body), _rat(n_body)))
    assert (o_status, p_status, n_status) == (200, 200, 200), (o_status, p_status, n_status)
    assert [s.paused_after for s in sessions] == [3], [s.paused_after for s in sessions]
    assert p_sql[:1] == ["SELECT 1"], p_sql[:1]
    assert credits == 1, credits
    assert _rat(p_body) == MIXED_RAT, _rat(p_body)
    assert p_body != o_body and p_body != n_body


# -- owned asks the shared predicate (D7) ---------------------------------------

ENTRY_SKUS = sorted(r["sku"] for ld in tl.LADDERS for r in ld["rungs"] if r["tier"] == 1)


def _owner():
    """The exemption's account, read from main: never spelled in a test."""
    owners = sorted(main.SHOP_OWNER_STEAM_IDS)
    assert owners, "main.SHOP_OWNER_STEAM_IDS is empty: no exempt account to read"
    return owners[0]


async def _seed_worn_entry(conn, ids):
    """The exempt account and PLAIN each wear rat rung 1 with no
    player_items row -- what an exempt equip writes, since equip skips the
    ownership read for that account."""
    for steam_id in (_owner(), PLAIN):
        await conn.execute(
            "INSERT INTO players (steam_id, active_title_id) VALUES ($1, $2)",
            steam_id, ids["title_ladder_rat_1"])


def _owned_skus(body):
    return sorted(r["sku"] for ln in body["ladders"] for r in ln["rungs"] if r["owned"])


def _active_skus(body):
    return sorted(r["sku"] for ln in body["ladders"] for r in ln["rungs"] if r["active"])


def _ownership(body):
    """(owned skus, worn skus, active_line): an answer with its steam_id left
    out. The D7 cases assert on this alone, so a failing assertion's output
    -- which pytest expands into the values an expression was built from --
    never carries the exempt account's id into a log."""
    return _owned_skus(body), _active_skus(body), body["active_line"]


def test_pg_the_exempt_account_reads_its_worn_entry_rung_as_owned():
    """D7 (design V3 section 7). The exempt account wears rat rung 1 with no
    player_items row. Its answer reads that rung owned AND active, as
    /shop/items reports it; every entry rung owned; and all 128
    granted-only rungs unowned, because the exemption stops at them. PLAIN,
    with the same rows under an ordinary id, reads nothing owned: the
    exemption, not a row, is what answers owned here."""
    _require_live_pg()
    ids, owned, before, after, answers = _run(_case(
        [_url(_owner()), _url(PLAIN)], seed_more=_seed_worn_entry))
    (x_status, x_body, x_sql), (p_status, p_body, _p) = answers
    _log_sql("exempt account wearing an entry rung", x_sql)
    assert (x_status, p_status) == (200, 200), (x_status, p_status)
    exempt, ordinary = _ownership(x_body), _ownership(p_body)
    del x_body, p_body
    assert len(ENTRY_SKUS) == 32 and len(tl.GRANTED_ONLY_SKUS) == 128
    assert sorted(ENTRY_SKUS + sorted(tl.GRANTED_ONLY_SKUS)) == sorted(tl.ALL_SKUS)
    assert exempt == (ENTRY_SKUS, ["title_ladder_rat_1"], "rat"), exempt
    assert ordinary == ([], ["title_ladder_rat_1"], "rat"), ordinary
    _assert_read_only(x_sql, WORN_READS)
    assert after == before, (before, after)


def test_pg_the_exempt_reading_comes_from_the_shared_predicate(monkeypatch):
    """Control for the case above: the same rows, with main._auto_owned made
    to answer False, read nothing owned for the exempt account either. So
    the owned rungs above came through the shared predicate, which the route
    consulted for every rung neither account holds a row for: 160 each."""
    _require_live_pg()
    asked = []

    def _never(steam_id, sku):
        asked.append(sku)
        return False

    monkeypatch.setattr(main, "_auto_owned", _never)
    ids, owned, before, after, answers = _run(_case(
        [_url(_owner()), _url(PLAIN)], seed_more=_seed_worn_entry))
    (x_status, x_body, _x), (p_status, p_body, _p) = answers
    assert (x_status, p_status) == (200, 200), (x_status, p_status)
    exempt, ordinary = _ownership(x_body), _ownership(p_body)
    del x_body, p_body
    assert exempt == ([], ["title_ladder_rat_1"], "rat"), exempt
    assert ordinary == ([], ["title_ladder_rat_1"], "rat"), ordinary
    assert sorted(asked) == sorted(list(tl.ALL_SKUS) * 2), len(asked)
