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

The database NAME is checked, not assumed. This file DROPs three tables and
terminates every other backend on whatever database the DSN names, and both of
those happen before the first row is written — so "every steam id is outside
the real SteamID64 space" protects the rows this file INSERTS and nothing
else. The DSN's database must literally be EXPECTED_DB or the fixture refuses
to touch it: sibling lanes keep their own throwaway databases on the same
local instance, and an exported DSN outlives the shell that set it.

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
import time
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
    # The candidate read, the under-lock re-check, and the ranked backlog
    # count — all three reach the loop, or the arm's loud gap is silent.
    assert len(horizon) == 3, horizon
    assert len([q for q in horizon if q.startswith("SELECT COUNT(*)")]) == 1, horizon
    locks = [q for q in sqls
             if q.startswith("SELECT status FROM ovt_series")
             and "FOR NO KEY UPDATE" in q]
    assert len(locks) == 1, locks
    voids = [q for q in sqls if VOID_REASON in q]
    assert len(voids) == 1, voids
    assert "UPDATE ovt_series" in voids[0]


def _fn_named(name: str):
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == name)


def _names_in(fn) -> set:
    return {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}


def test_the_janitor_loop_runs_the_arm_and_only_through_the_bounded_form():
    """The loop calls the bounded tick and nothing else of this arm."""
    loop = _names_in(_fn_named("queue_cleanup_loop"))
    assert "_ovt_horizon_sweep_tick_bounded" in loop
    # The unbounded body must never be reachable from the loop directly: that
    # is the call that can hold every arm behind it.
    assert "_ovt_horizon_sweep_tick" not in loop
    tick = _names_in(_fn_named("_ovt_horizon_sweep_tick"))
    assert {"_ovt_horizon_candidates", "_ovt_settle_horizon_row",
            "_ovt_horizon_ranked_backlog", "OVT_ABANDONED_HORIZON_DAYS",
            "OVT_HORIZON_SWEEP_LIMIT"} <= tick, tick


def test_the_tick_gives_the_loop_back_inside_a_bounded_budget():
    """#276/#430: this arm's unhandled case must expire, not hold the loop.

    A row lock wait raises nothing and there is no lock_timeout on the engine
    (backend/api/database.py sets no connect_args), so an arm that waits stops
    every arm behind it in the same tick with no log line at all.
    """
    bounded = _code(main._ovt_horizon_sweep_tick_bounded)
    assert "timeout=OVT_HORIZON_TICK_BUDGET_S" in bounded
    assert ".cancel()" in bounded
    # Bounded well inside the 60-second tick interval, or the budget is not a
    # budget.
    assert 0 < main.OVT_HORIZON_TICK_BUDGET_S < 60


def test_the_row_lock_declines_a_held_row_instead_of_waiting_for_it():
    """SKIP LOCKED, like every sibling sweep in the same loop.

    The rows are fourteen days old: losing one for a 60-second tick costs
    nothing, and waiting for it costs the arms behind this one.
    """
    lock = _only(_sql_literals(main._ovt_settle_horizon_row),
                 "FOR NO KEY UPDATE")
    assert "SKIP LOCKED" in lock, lock


def test_a_ranked_series_is_refused_by_both_halves_of_the_predicate():
    """Sid's 14-day ruling for a RANKED series is the opposite settlement —
    the leader takes the rating. This arm must not apply the unranked rule to
    one, and the exclusion has to survive the candidate read AND the re-check.
    """
    cand = _only(_sql_literals(main._ovt_horizon_candidates), "FROM ovt_series s")
    recheck = _only(_sql_literals(main._ovt_settle_horizon_row),
                    "SELECT 1 FROM ovt_series")
    for q in (cand, recheck):
        assert "s.is_ranked = FALSE" in q, q
    # And the rows it declines are COUNTED, so the gap is loud rather than
    # silent (#342 — the check that can fail).
    backlog = _only(_sql_literals(main._ovt_horizon_ranked_backlog), "COUNT(*)")
    assert "s.is_ranked = TRUE" in backlog
    assert "s.status = 'active'" in backlog


def test_the_void_cannot_put_a_row_back_inside_the_continuation_window():
    """#302: no note may claim this sweep restores a sitting's continuation.

    The prior-series lookup does accept 'canceled', so a voided row enters its
    scope — and is refused two statements later. The settlement writes no
    completed_at, so the continuation's anchor is COALESCE(completed_at,
    created_at) = created_at, and created_at is past the horizon on every row
    this arm touches BY CONSTRUCTION. The acceptance of canceled priors is
    there for a lock canceled minutes after creation (assembly_timeout).
    """
    src = MAIN_PY.read_text(encoding="utf-8")
    assert "ORDER BY COALESCE(completed_at, created_at) DESC LIMIT 1" in src
    assert 'anchor = prior["completed_at"] or prior["created_at"]' in src
    assert "completed_at" not in _settle_update_sql()
    horizon_minutes = main.OVT_ABANDONED_HORIZON_DAYS * 24 * 60
    assert main._CONTINUATION_WINDOW_MINUTES < horizon_minutes, (
        main._CONTINUATION_WINDOW_MINUTES, horizon_minutes)


def test_the_ovt_earned_pack_paths_are_completion_gated():
    """What makes this write delta-free, pinned.

    `invalidated_at` is read by the Player Cards reconciler
    (`_PC_VOID_SWEEP_SQL["ovt"]` voids still-unopened earned packs on it) and
    by the open route (`_PC_SERIES_STANDING_SQL["ovt"]`). The void is harmless
    only because an `active` row can carry no earned pack: both ovt grant
    paths require a COMPLETED series. Move granting to per-game and this test
    reds before the sweep starts voiding real packs.
    """
    scan = " ".join(main._PC_RECONCILE_SQL["ovt"].split())
    assert "os.status = 'completed'" in scan, scan
    assert "os.invalidated_at IS NULL" in scan, scan

    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    parent_fn = {}

    def walk(node, fn):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = node
        for child in ast.iter_child_nodes(node):
            parent_fn[child] = fn
            walk(child, fn)

    walk(tree, None)
    sites = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "_pc_grant_earned_packs"
                and any(k.arg == "mode" and isinstance(k.value, ast.Constant)
                        and k.value.value == "ovt" for k in node.keywords)):
            sites.append(parent_fn[node])
    # A pin that measured an empty set would pass forever (#342).
    assert sites, "no ovt earned-pack grant call found — the pin lost its subject"
    for fn in sites:
        assert "UPDATE ovt_series SET status='completed'" in ast.unparse(fn), fn.name


def test_the_horizon_is_the_fourteen_days_sid_ruled_for_ranked():
    assert main.OVT_ABANDONED_HORIZON_DAYS == 14


# ───────────────────────────── live half ──────────────────────────────────

DSN = os.environ.get("BUG391_TEST_PG_DSN")
live = pytest.mark.skipif(
    not DSN, reason="BUG391_TEST_PG_DSN unset; live-PostgreSQL acceptance half")

# The only database this file may touch. Everything below DROPs tables on it
# and terminates every other backend connected to it.
EXPECTED_DB = "scr_bug391"


async def _assert_dedicated_db(conn) -> str:
    """Refuse any database but the dedicated one (#342).

    The docstring that used to carry this rule was a claim about the DSN's
    VALUE that nothing read. The local instance also carries the 389 and 392
    lanes' throwaway databases, `players` is the root identity table in all of
    them, and the DROP runs before the first insert — so the guard has to be a
    statement, not a sentence.
    """
    name = (await conn.execute(text("SELECT current_database()"))).scalar()
    if name != EXPECTED_DB:
        raise RuntimeError(
            f"BUG391_TEST_PG_DSN points at database {name!r}. This file drops "
            f"ovt_matches, ovt_series and players and terminates every other "
            f"backend on it, so it runs against {EXPECTED_DB!r} and nothing "
            f"else.")
    return name

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
    # here and not in a retry. Terminating every other backend is bounded by
    # the name check below, not by the belief that the DSN is the right one.
    async with engine.connect() as conn:
        # Before the terminate, not after it: the refusal has to come first or
        # it is documentation.
        await _assert_dedicated_db(conn)
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
                       solo_wins: int = 0, duo_wins: int = 0,
                       is_ranked: bool = False) -> str:
    ids = (await conn.execute(
        text("SELECT id FROM players ORDER BY steam_id"))).scalars().all()
    sid = str(uuid.uuid4())
    await conn.execute(text("""
        INSERT INTO ovt_series (id, solo_id, duo_a_id, duo_b_id,
                                solo_series_wins, duo_series_wins, status,
                                is_ranked, created_at)
        VALUES (CAST(:id AS uuid), :a, :b, :c, :sw, :dw, :st, :rk,
                NOW() - make_interval(secs => CAST(:age AS double precision)))
    """), {"id": sid, "a": ids[0], "b": ids[1], "c": ids[2],
           "sw": solo_wins, "dw": duo_wins, "st": status, "rk": is_ranked,
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
def test_a_report_completing_the_series_before_the_lock_wins():
    """The candidate was read before any lock was held (#208).

    The interleaving that matters is the one the sweep cannot see: the
    candidate list is built, a report completes the series and COMMITS, and
    only then does the settler take the row lock. It must read the row version
    the lock gives it — not the candidate's — and decline. Deterministic on
    purpose: no sleep decides the outcome.
    """
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
            try:
                cands = await main._ovt_horizon_candidates(
                    sweeper, main.OVT_ABANDONED_HORIZON_DAYS,
                    main.OVT_HORIZON_SWEEP_LIMIT)
                assert [str(c["id"]) for c in cands] == [sid]

                await reporter.execute(
                    text("SELECT status FROM ovt_series WHERE id = CAST(:i AS uuid)"
                         " FOR NO KEY UPDATE"), {"i": sid})
                await reporter.execute(text("""
                    UPDATE ovt_series
                       SET status = 'completed', winner_side = 1,
                           solo_series_wins = 2, completed_at = NOW()
                     WHERE id = CAST(:i AS uuid)
                """), {"i": sid})
                await reporter.commit()

                wrote = await asyncio.wait_for(
                    main._ovt_settle_horizon_row(
                        sweeper, sid, main.OVT_ABANDONED_HORIZON_DAYS),
                    timeout=20)
                if wrote:
                    await sweeper.commit()
                else:
                    await sweeper.rollback()
            finally:
                # An assertion that fires mid-interleaving must not leave a
                # session holding a row lock — see _reset's comment.
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


@live
def test_a_row_another_transaction_holds_is_declined_not_waited_for():
    """SKIP LOCKED: the janitor arm never waits on a row lock.

    A report transaction holds the same series row and is slow (a pinned pool
    connection, a client socket that died without the server noticing). With
    an unbounded wait, THIS call would not return — and the FFA janitor and
    the lease expiry behind it in the same tick would not run, with no log
    line to say why.
    """
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                sid = await _make_series(conn, age_days=20)
                await _add_game(conn, sid, ended_days_ago=20)

            holder = Session()
            sweeper = Session()
            try:
                await holder.execute(
                    text("SELECT status FROM ovt_series WHERE id = CAST(:i AS uuid)"
                         " FOR NO KEY UPDATE"), {"i": sid})
                t0 = time.monotonic()
                try:
                    wrote = await asyncio.wait_for(
                        main._ovt_settle_horizon_row(
                            sweeper, sid, main.OVT_ABANDONED_HORIZON_DAYS),
                        timeout=10)
                except asyncio.TimeoutError:
                    pytest.fail(
                        "the settler waited on a row another transaction held; "
                        "a janitor arm that waits holds every arm behind it")
                elapsed = time.monotonic() - t0
                await sweeper.rollback()
                # Declined, not written, and it did not sit there to find out.
                assert wrote is False
                assert elapsed < 5, elapsed
                # The holder still holds it, so read the row on its own
                # connection: FOR NO KEY UPDATE does not block a plain read.
                async with engine.connect() as conn:
                    st = (await conn.execute(
                        text("SELECT status, invalidated_at FROM ovt_series"
                             " WHERE id = CAST(:i AS uuid)"),
                        {"i": sid})).mappings().first()
                assert st["status"] == "active"
                assert st["invalidated_at"] is None
            finally:
                await _shut(holder)
                await _shut(sweeper)
        finally:
            await engine.dispose()
    _run(go())


@live
def test_the_tick_gives_the_janitor_loop_back_when_the_table_is_locked():
    """#276/#430, one level up: SKIP LOCKED bounds the ROW wait, and the
    tick's own budget bounds everything else.

    A migration holding ACCESS EXCLUSIVE on ovt_series blocks even the
    candidate read, which takes only ACCESS SHARE. Nothing on this engine sets
    lock_timeout or statement_timeout, so without the budget this arm holds
    the janitor tick for as long as the DDL runs.
    """
    async def go():
        engine = _engine()
        prev_budget = main.OVT_HORIZON_TICK_BUDGET_S
        main.OVT_HORIZON_TICK_BUDGET_S = 2
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                sid = await _make_series(conn, age_days=20)
                await _add_game(conn, sid, ended_days_ago=20)

            blocker = Session()
            try:
                await blocker.execute(
                    text("LOCK TABLE ovt_series IN ACCESS EXCLUSIVE MODE"))
                t0 = time.monotonic()
                try:
                    settled = await asyncio.wait_for(
                        main._ovt_horizon_sweep_tick_bounded(Session),
                        timeout=15)
                except asyncio.TimeoutError:
                    pytest.fail(
                        "the horizon tick never gave the loop back: it was "
                        "still waiting on the table lock after 15s, so every "
                        "arm behind it in that tick was skipped")
                elapsed = time.monotonic() - t0
                assert settled == 0
                assert elapsed < 10, elapsed
            finally:
                # Releasing the DDL lock lets the cancelled tick's connection
                # unwind; _reset in the next case clears whatever it leaves.
                await _shut(blocker)
        finally:
            main.OVT_HORIZON_TICK_BUDGET_S = prev_budget
            await engine.dispose()
    _run(go())


@live
def test_a_ranked_series_past_the_horizon_is_left_active_and_counted(capsys):
    """Sid's ruling for a ranked series idle 14 days is that the LEADER takes
    the rating — the opposite settlement. Until that is built, a ranked 1v2
    row is left alone and NAMED, never voided by the unranked rule.
    """
    async def go():
        engine = _engine()
        main._ovt_horizon_ranked_last_seen = -1
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                unranked = await _make_series(conn, age_days=20)
                await _add_game(conn, unranked, ended_days_ago=20)
                ranked = await _make_series(conn, age_days=20, is_ranked=True)
                await _add_game(conn, ranked, ended_days_ago=20)
            settled = await main._ovt_horizon_sweep_tick(Session)
            return unranked, ranked, settled
        finally:
            await engine.dispose()

    unranked, ranked, settled = _run(go())
    out = capsys.readouterr().out
    assert settled == 1, out

    async def read_rows():
        engine = _engine()
        try:
            return await _row(engine, unranked), await _row(engine, ranked)
        finally:
            await engine.dispose()

    u, r = _run(read_rows())
    assert u["status"] == "canceled" and u["invalidation_reason"] == VOID_REASON
    assert r["status"] == "active", r
    assert r["invalidated_at"] is None and r["invalidation_reason"] is None
    named = [ln for ln in out.splitlines()
             if "RANKED 1v2 series past the horizon" in ln]
    assert len(named) == 1, out
    assert named[0].startswith("[OVT-HORIZON] 1 RANKED"), named[0]


@live
def test_the_arm_announces_itself_once_per_process(capsys):
    """The deploy's positive signal (#438/#443, #306).

    '[JANITOR-SELFTEST] all janitor queries plan clean' prints on any build
    whose janitor statements EXPLAIN — including a build with no horizon arm
    at all — so it cannot be the acceptance line for THIS arm. This one is
    printed by the arm itself, on its first tick, and by nothing else.
    """
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            main._ovt_horizon_armed_logged = False
            await main._ovt_horizon_sweep_tick(Session)
            await main._ovt_horizon_sweep_tick(Session)
        finally:
            await engine.dispose()
    _run(go())
    out = capsys.readouterr().out
    armed = [ln for ln in out.splitlines() if "[OVT-HORIZON] armed" in ln]
    assert len(armed) == 1, out
    assert f"horizon={main.OVT_ABANDONED_HORIZON_DAYS}d" in armed[0]
    assert f"cap={main.OVT_HORIZON_SWEEP_LIMIT}" in armed[0]
    assert VOID_REASON in armed[0]


@live
def test_the_live_half_refuses_any_database_but_the_dedicated_one():
    """The negative control for the fixture's own guard.

    This file DROPs three tables — `players` among them — and terminates every
    backend on the database the DSN names, both before it writes a single row.
    Point it at a different database on the same instance and it must refuse.
    Nothing here writes: the wrong-database connection only asks its own name.
    """
    other = "postgres" if not DSN.rstrip("/").endswith("/postgres") else "template1"
    wrong_dsn = DSN.rsplit("/", 1)[0] + "/" + other

    async def go():
        engine = create_async_engine(wrong_dsn, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                with pytest.raises(RuntimeError) as exc:
                    await _assert_dedicated_db(conn)
            assert other in str(exc.value)
            assert EXPECTED_DB in str(exc.value)
        finally:
            await engine.dispose()
        ok = _engine()
        try:
            async with ok.connect() as conn:
                assert await _assert_dedicated_db(conn) == EXPECTED_DB
        finally:
            await ok.dispose()
    _run(go())
