"""Bug 391 — the 1v2 abandoned-series horizon sweep.

Two halves.

The no-DSN half is structural and always runs: it pins the shape of the write
(what it may and may not set), the lock mode, the status spelling, and — the
one that matters most — that the sweep's SQL is REACHABLE from the janitor
roots, so "the arm exists" and "the arm runs" are not the same claim (#286).

The live half needs PostgreSQL, because everything this sweep is judged on is a
PostgreSQL behaviour: a row lock that actually blocks, a predicate re-checked
against the version the lock waited for, and a lock mode that does or does not
conflict with the FK check a game report takes on the same row. A fake session
can prove which statements are issued and never any of that. Point
BUG391_TEST_PG_DSN at the dedicated throwaway database:

    BUG391_TEST_PG_DSN=postgresql+asyncpg://postgres@127.0.0.1:55432/scr_bug391

An unset DSN SKIPS the live half. A skipped live half is not an acceptance —
it is an unrun test, and the lane's log has to show the executed run.

The file creates and drops its own tables and every steam id it uses is outside
the real SteamID64 space, so a misconfigured DSN cannot touch real rows.

No pytest-asyncio: the rest of this suite drives coroutines through a plain
asyncio.run helper and one opt-in file is not a reason to add a dependency the
other sixty-odd files do not have.
"""

import ast
import asyncio
import inspect
import os
import re
import textwrap
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import main


REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_PY = REPO_ROOT / "backend" / "api" / "main.py"
SCHEMA_120 = REPO_ROOT / "backend" / "sql" / "120_1v2_schema.sql"

# The settlement's reason literal. It exists for no other purpose than to be
# grepped and asserted on (#306): it is not a product string, it is never
# localised, and no other path writes it.
VOID_REASON = "abandoned_horizon_void"


# ───────────────────────── no-DSN structural pins ─────────────────────────

def _sql_literals(func) -> list:
    """Every SQL string this function hands to text().

    Deliberately NOT the raw source: a prose check would measure the
    docstring that EXPLAINS the rule instead of the SQL that keeps it, and a
    comment naming `started_at` would be indistinguishable from a query
    reading it (#441).
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    out = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "text" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            out.append(node.args[0].value)
    return out


def _code(func) -> str:
    """The function's executable code with comments and docstring dropped."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    body = tree.body[0]
    if (body.body and isinstance(body.body[0], ast.Expr)
            and isinstance(body.body[0].value, ast.Constant)):
        body.body = body.body[1:]
    return ast.unparse(body)


def _only(literals, needle: str) -> str:
    hits = [q for q in literals if needle in q]
    assert len(hits) == 1, (needle, len(hits))
    return hits[0]


def _settle_update_sql() -> str:
    return _only(_sql_literals(main._ovt_settle_horizon_row), "UPDATE ovt_series")


def test_the_settlement_writes_neither_completed_at_nor_winner_side():
    """q1's default in code: an abandoned 1v2 is VOIDED, never credited.

    A settlement that wrote completed_at/winner_side would hand the series to
    whoever happened to be ahead on games when the trio walked away.
    """
    upd = _settle_update_sql()
    assert "completed_at" not in upd
    assert "winner_side" not in upd
    assigned = set(re.findall(r"(\w+)\s*=\s*(?:NOW\(\)|'[^']*')", upd))
    assert assigned == {"status", "invalidated_at", "invalidation_reason"}, assigned
    assert VOID_REASON in upd


def test_the_settlement_status_spelling_is_the_one_every_reader_filters_on():
    """'canceled', one L.

    backend/sql/145_ovt_status_spelling.sql exists because a janitor wrote
    'cancelled' and its rows went invisible to the continuation's prior-series
    lookup. A third spelling — 'invalidated', 'void' — would reopen exactly
    that hole, so the VOID is carried by invalidation_reason.
    """
    upd = _settle_update_sql()
    assert "status = 'canceled'" in upd
    assert "cancelled" not in upd
    prior_lookup = "WHERE status IN ('completed', 'canceled', 'cancelled')"
    assert prior_lookup in MAIN_PY.read_text(encoding="utf-8")


def test_the_row_lock_is_for_no_key_update():
    """FOR UPDATE would make a live game report's FK insert wait on the janitor."""
    sqls = _sql_literals(main._ovt_settle_horizon_row)
    assert len([q for q in sqls if "FOR NO KEY UPDATE" in q]) == 1
    for q in sqls:
        stripped = q.replace("FOR NO KEY UPDATE", "")
        assert not re.search(r"FOR\s+UPDATE", stripped), q


def test_the_predicate_is_re_checked_inside_the_transaction():
    """#208: the candidate list was read before any lock was held."""
    code = _code(main._ovt_settle_horizon_row)
    assert re.search(r"locked\[.status.\]\s*!=\s*.active.", code)
    assert "AND status = 'active'" in _settle_update_sql()
    # The horizon itself is re-derived under the lock, not carried over from
    # the candidate row: both of its terms are re-evaluated.
    recheck = _only(_sql_literals(main._ovt_settle_horizon_row),
                    "SELECT 1 FROM ovt_series")
    assert recheck.count("make_interval(days => CAST(:days AS int))") == 2


def test_idleness_is_measured_from_server_clock_columns_only():
    """started_at is the client's stamp; ended_at and created_at are NOW()."""
    sqls = (_sql_literals(main._ovt_horizon_candidates)
            + _sql_literals(main._ovt_settle_horizon_row))
    assert len([q for q in sqls if "GREATEST(m.ended_at, m.created_at)" in q]) == 2
    for q in sqls:
        # started_at is client-supplied; last_polled is a client saying it is
        # still there. Neither may hold a row open.
        assert "started_at" not in q, q
        assert "last_polled" not in q, q


def test_every_column_the_sweep_names_exists_in_the_1v2_schema():
    """The live half runs against a SUBSET schema; this closes that gap.

    A column name that exists only in the test's own CREATE TABLE would pass
    the live half and fail at boot on production.
    """
    schema = SCHEMA_120.read_text(encoding="utf-8")
    declared = set(re.findall(r"^\s{4}(\w+)\s+[A-Za-z]", schema, re.M))
    named = set()
    for q in (_sql_literals(main._ovt_horizon_candidates)
              + _sql_literals(main._ovt_settle_horizon_row)):
        named |= set(re.findall(r"\b[sm]\.(\w+)\b", q))
        named |= set(re.findall(r"^\s*(?:SET\s+)?(\w+)\s*=\s*(?:NOW\(\)|')",
                                q, re.M))
    named.discard("id")
    # A check that measured an empty set would pass forever (#342).
    assert named >= {"created_at", "ended_at", "status",
                     "invalidated_at", "invalidation_reason"}, named
    missing = sorted(named - declared)
    assert not missing, missing


def test_the_sweep_sql_is_reachable_from_the_janitor_roots():
    """Reachability before logic (#286).

    The janitor self-test walks the LIVE call graph from queue_cleanup_loop.
    If the arm is ever dropped from the loop, these statements leave the
    inventory and this test reds — an arm that exists but is never called is
    the failure this pin exists for.
    """
    inv = main._janitor_sql_inventory()
    assert inv["dynamic"] == []
    sqls = [" ".join(s["sql"].split()) for s in inv["statements"]]
    horizon = [q for q in sqls if "ovt_series" in q and "make_interval(days" in q]
    assert len(horizon) == 2, horizon
    locks = [q for q in sqls
             if q.startswith("SELECT status FROM ovt_series")
             and "FOR NO KEY UPDATE" in q]
    assert len(locks) == 1, locks
    voids = [q for q in sqls if VOID_REASON in q]
    assert len(voids) == 1, voids
    assert "UPDATE ovt_series" in voids[0]


def test_the_janitor_loop_calls_both_halves_of_the_sweep():
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    loop = next(n for n in ast.walk(tree)
                if isinstance(n, ast.AsyncFunctionDef)
                and n.name == "queue_cleanup_loop")
    names = {n.id for n in ast.walk(loop) if isinstance(n, ast.Name)}
    assert "_ovt_horizon_candidates" in names
    assert "_ovt_settle_horizon_row" in names
    assert "OVT_ABANDONED_HORIZON_DAYS" in names


def test_the_horizon_is_the_fourteen_days_sid_ruled_for_ranked():
    assert main.OVT_ABANDONED_HORIZON_DAYS == 14


# ───────────────────────────── live half ──────────────────────────────────

DSN = os.environ.get("BUG391_TEST_PG_DSN")
live = pytest.mark.skipif(
    not DSN, reason="BUG391_TEST_PG_DSN unset; live-PostgreSQL acceptance half")

# Outside the real SteamID64 space on purpose.
SIDS = ("90000000000003911", "90000000000003912", "90000000000003913")

SCHEMA = """
DROP TABLE IF EXISTS ovt_matches;
DROP TABLE IF EXISTS ovt_series;
DROP TABLE IF EXISTS players;

CREATE TABLE players (
    id UUID PRIMARY KEY,
    steam_id VARCHAR(20) UNIQUE NOT NULL
);

CREATE TABLE ovt_series (
    id UUID PRIMARY KEY,
    solo_id  UUID NOT NULL REFERENCES players(id),
    duo_a_id UUID NOT NULL REFERENCES players(id),
    duo_b_id UUID NOT NULL REFERENCES players(id),
    solo_series_wins SMALLINT NOT NULL DEFAULT 0,
    duo_series_wins  SMALLINT NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    winner_side SMALLINT,
    is_ranked BOOLEAN NOT NULL DEFAULT FALSE,
    photon_room_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    invalidated_at TIMESTAMPTZ,
    invalidation_reason VARCHAR(64)
);
CREATE INDEX idx_ovt_series_status ON ovt_series (status, created_at DESC);

CREATE TABLE ovt_matches (
    id UUID PRIMARY KEY,
    series_id UUID REFERENCES ovt_series(id) ON DELETE SET NULL,
    winner_side SMALLINT NOT NULL,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ovt_matches_series ON ovt_matches (series_id, ended_at DESC);
"""


def _run(coro):
    return asyncio.run(coro)


def _engine():
    return create_async_engine(DSN, poolclass=NullPool)


async def _shut(session):
    """Roll a session back and close it, whatever state it is in."""
    for step in (session.rollback, session.close):
        try:
            await step()
        except Exception:
            pass


async def _reset(engine):
    # Take the clean slate rather than hoping for it. A test that fails
    # mid-transaction leaves a backend holding locks on these tables, and
    # PostgreSQL does not notice its client is gone until it next writes to
    # that socket — minutes, on a default keepalive, and across process exit.
    # The DROP below would then sit behind it and the next run would red for a
    # reason that has nothing to do with the code under test. That is exactly
    # how this file's own negative control first reddened, so the fix belongs
    # here and not in a retry. This database exists for this file alone, so
    # terminating every other backend on it is bounded by construction.
    async with engine.connect() as conn:
        await conn.execute(text(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
            " WHERE datname = current_database() AND pid <> pg_backend_pid()"))
        await conn.commit()
    async with engine.begin() as conn:
        # A blocked DDL must fail loudly, not hang the suite.
        await conn.execute(text("SET LOCAL lock_timeout = '15s'"))
        for stmt in filter(None, (s.strip() for s in SCHEMA.split(";"))):
            await conn.execute(text(stmt))
        for sid in SIDS:
            await conn.execute(
                text("INSERT INTO players (id, steam_id) VALUES (:i, :s)"),
                {"i": str(uuid.uuid4()), "s": sid})


async def _make_series(conn, *, age_days: float, status: str = "active",
                       solo_wins: int = 0, duo_wins: int = 0) -> str:
    ids = (await conn.execute(
        text("SELECT id FROM players ORDER BY steam_id"))).scalars().all()
    sid = str(uuid.uuid4())
    await conn.execute(text("""
        INSERT INTO ovt_series (id, solo_id, duo_a_id, duo_b_id,
                                solo_series_wins, duo_series_wins, status, created_at)
        VALUES (CAST(:id AS uuid), :a, :b, :c, :sw, :dw, :st,
                NOW() - make_interval(secs => CAST(:age AS double precision)))
    """), {"id": sid, "a": ids[0], "b": ids[1], "c": ids[2],
           "sw": solo_wins, "dw": duo_wins, "st": status,
           "age": age_days * 86400.0})
    return sid


async def _add_game(conn, series_id: str, *, ended_days_ago: float,
                    started_days_ago: float | None = None, winner_side: int = 2):
    await conn.execute(text("""
        INSERT INTO ovt_matches (id, series_id, winner_side, started_at, ended_at, created_at)
        VALUES (CAST(:id AS uuid), CAST(:sid AS uuid), :ws,
                CASE WHEN CAST(:st AS double precision) IS NULL THEN NULL
                     ELSE NOW() - make_interval(secs => CAST(:st AS double precision)) END,
                NOW() - make_interval(secs => CAST(:en AS double precision)),
                NOW() - make_interval(secs => CAST(:en AS double precision)))
    """), {"id": str(uuid.uuid4()), "sid": series_id, "ws": winner_side,
           "st": None if started_days_ago is None else started_days_ago * 86400.0,
           "en": ended_days_ago * 86400.0})


async def _sweep(session_factory, days: int | None = None) -> int:
    """Drive the REAL helpers exactly as queue_cleanup_loop drives them."""
    days = main.OVT_ABANDONED_HORIZON_DAYS if days is None else days
    settled = 0
    async with session_factory() as db:
        cands = await main._ovt_horizon_candidates(
            db, days, main.OVT_HORIZON_SWEEP_LIMIT)
        for c in cands:
            if await main._ovt_settle_horizon_row(db, c["id"], days):
                await db.commit()
                settled += 1
            else:
                await db.rollback()
    return settled


async def _row(engine, series_id: str) -> dict:
    async with engine.connect() as conn:
        r = (await conn.execute(
            text("SELECT * FROM ovt_series WHERE id = CAST(:i AS uuid)"),
            {"i": series_id})).mappings().first()
    return dict(r)


@live
def test_a_past_horizon_series_is_voided_and_nobody_is_credited():
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                sid = await _make_series(conn, age_days=20, solo_wins=1, duo_wins=0)
                await _add_game(conn, sid, ended_days_ago=20, winner_side=1)
            assert await _sweep(Session) == 1
            row = await _row(engine, sid)
            assert row["status"] == "canceled"
            assert row["invalidated_at"] is not None
            assert row["invalidation_reason"] == VOID_REASON
            # The leader is NOT credited: no completion, no winner side, and
            # the tally is left exactly as the last report wrote it.
            assert row["completed_at"] is None
            assert row["winner_side"] is None
            assert (row["solo_series_wins"], row["duo_series_wins"]) == (1, 0)
        finally:
            await engine.dispose()
    _run(go())


@live
def test_a_zero_game_series_past_the_horizon_is_voided_too():
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                sid = await _make_series(conn, age_days=30)
            assert await _sweep(Session) == 1
            assert (await _row(engine, sid))["invalidation_reason"] == VOID_REASON
        finally:
            await engine.dispose()
    _run(go())


@live
def test_a_series_one_day_inside_the_horizon_is_untouched():
    """The horizon-off-by-a-day control."""
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                sid = await _make_series(conn, age_days=13)
                await _add_game(conn, sid, ended_days_ago=13)
            assert await _sweep(Session) == 0
            row = await _row(engine, sid)
            assert row["status"] == "active"
            assert row["invalidated_at"] is None
            assert row["invalidation_reason"] is None
        finally:
            await engine.dispose()
    _run(go())


@live
def test_an_old_series_whose_trio_played_yesterday_is_untouched():
    """Idleness is measured from the newest GAME, not from the series row."""
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                sid = await _make_series(conn, age_days=60)
                await _add_game(conn, sid, ended_days_ago=40)
                await _add_game(conn, sid, ended_days_ago=1)
            assert await _sweep(Session) == 0
            assert (await _row(engine, sid))["status"] == "active"
        finally:
            await engine.dispose()
    _run(go())


@live
def test_the_candidate_read_alone_already_excludes_a_series_played_yesterday():
    """The candidate query carries the recency term in its own right.

    Without this, a candidate list that ignored games would still produce the
    right final state — the under-lock re-check would decline every row — and
    nothing would show that the first half stopped filtering.
    """
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                stale = await _make_series(conn, age_days=60)
                await _add_game(conn, stale, ended_days_ago=40)
                fresh = await _make_series(conn, age_days=60)
                await _add_game(conn, fresh, ended_days_ago=1)
            async with Session() as db:
                cands = await main._ovt_horizon_candidates(
                    db, main.OVT_ABANDONED_HORIZON_DAYS,
                    main.OVT_HORIZON_SWEEP_LIMIT)
            assert [str(c["id"]) for c in cands] == [stale]
        finally:
            await engine.dispose()
    _run(go())


@live
def test_a_future_dated_client_stamp_cannot_hold_a_series_open():
    """#283: a client-attested value may only move the server toward the
    conservative outcome. started_at is the report's own claim."""
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                sid = await _make_series(conn, age_days=20)
                await _add_game(conn, sid, ended_days_ago=20,
                                started_days_ago=-3650)   # dated ten years ahead
            assert await _sweep(Session) == 1
            assert (await _row(engine, sid))["invalidation_reason"] == VOID_REASON
        finally:
            await engine.dispose()
    _run(go())


@live
def test_sweeping_the_same_row_twice_is_a_no_op():
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                sid = await _make_series(conn, age_days=20)
                await _add_game(conn, sid, ended_days_ago=20)
            assert await _sweep(Session) == 1
            first = await _row(engine, sid)
            assert await _sweep(Session) == 0
            second = await _row(engine, sid)
            assert second["invalidated_at"] == first["invalidated_at"]
            assert second["invalidation_reason"] == VOID_REASON
            assert second["status"] == "canceled"
        finally:
            await engine.dispose()
    _run(go())


@live
def test_a_report_completing_the_series_under_the_lock_wins():
    """The candidate was read before any lock was held; the settlement must
    lose to the report that commits while it waits (#208)."""
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                sid = await _make_series(conn, age_days=20, solo_wins=1, duo_wins=1)
                await _add_game(conn, sid, ended_days_ago=20)

            reporter = Session()
            sweeper = Session()
            task = None
            try:
                await reporter.execute(
                    text("SELECT status FROM ovt_series WHERE id = CAST(:i AS uuid)"
                         " FOR NO KEY UPDATE"), {"i": sid})

                cands = await main._ovt_horizon_candidates(
                    sweeper, main.OVT_ABANDONED_HORIZON_DAYS,
                    main.OVT_HORIZON_SWEEP_LIMIT)
                assert [str(c["id"]) for c in cands] == [sid]

                task = asyncio.create_task(main._ovt_settle_horizon_row(
                    sweeper, sid, main.OVT_ABANDONED_HORIZON_DAYS))
                await asyncio.sleep(0.4)

                await reporter.execute(text("""
                    UPDATE ovt_series
                       SET status = 'completed', winner_side = 1,
                           solo_series_wins = 2, completed_at = NOW()
                     WHERE id = CAST(:i AS uuid)
                """), {"i": sid})
                await reporter.commit()

                wrote = await asyncio.wait_for(task, timeout=20)
                task = None
                if wrote:
                    await sweeper.commit()
                else:
                    await sweeper.rollback()
            finally:
                # An assertion that fires mid-interleaving must not leave a
                # session holding a row lock — see _reset's comment.
                if task is not None:
                    task.cancel()
                await _shut(reporter)
                await _shut(sweeper)

            assert wrote is False
            row = await _row(engine, sid)
            assert row["status"] == "completed"
            assert row["winner_side"] == 1
            assert row["completed_at"] is not None
            assert row["invalidated_at"] is None
            assert row["invalidation_reason"] is None
        finally:
            await engine.dispose()
    _run(go())


@live
def test_the_settlement_lock_does_not_block_a_game_reports_fk_insert():
    """#202/#207: ovt_matches.series_id is an FK to this row, so a report's
    INSERT takes FOR KEY SHARE on it. FOR UPDATE would conflict; the NO KEY
    variant is the weakest mode that still self-conflicts."""
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                sid = await _make_series(conn, age_days=20)
                await _add_game(conn, sid, ended_days_ago=20)

            sweeper = Session()
            try:
                wrote = await main._ovt_settle_horizon_row(
                    sweeper, sid, main.OVT_ABANDONED_HORIZON_DAYS)
                assert wrote is True   # lock + write held, NOT yet committed

                async with engine.connect() as conn:
                    await conn.execute(text("SET lock_timeout = '3s'"))
                    await conn.execute(text("""
                        INSERT INTO ovt_matches (id, series_id, winner_side, ended_at, created_at)
                        VALUES (CAST(:id AS uuid), CAST(:sid AS uuid), 2, NOW(), NOW())
                    """), {"id": str(uuid.uuid4()), "sid": sid})
                    await conn.commit()
            finally:
                # Under the FOR UPDATE mutation the INSERT above times out, and
                # without this the sweeper's session keeps the row locked for
                # every later test in the run AND for the next process — see
                # _reset's comment.
                await _shut(sweeper)
        finally:
            await engine.dispose()
    _run(go())
