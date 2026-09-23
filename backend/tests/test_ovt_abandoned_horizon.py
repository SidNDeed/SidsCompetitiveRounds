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
from datetime import datetime, timezone
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
    # The guard TERM, not its spelling. A bare substring check here reds on a
    # reformat as loudly as on a removal, so a kill at this site would be
    # evidence that the text moved and not that the guard went (#342). The
    # M38 inert twin — the same guard, parenthesised — is what caught it: it
    # reddened this case twice while the guard it rewrote was still in force,
    # which is the one outcome a twin exists to make visible (#391). Both
    # accepted forms are written out rather than made optional, so an
    # unbalanced remnant is not read as a guard.
    upd_flat = " ".join(_settle_update_sql().split())
    assert re.search(r"AND\s+(?:status\s*=\s*'active'"
                     r"|\(\s*status\s*=\s*'active'\s*\))", upd_flat), upd_flat
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
    # The candidate read, the under-lock re-check, the ranked backlog count and
    # — added in round 2 — the completion-stamp decline count. All four reach
    # the loop, or one of the arm's loud gaps is silent.
    assert len(horizon) == 4, horizon
    assert len([q for q in horizon if q.startswith("SELECT COUNT(*)")]) == 2, horizon
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
def test_two_concurrent_sweeps_settle_the_row_exactly_once():
    """The experiment BUG-391-DIAG.md:730 specified, run for real.

    The diagnosis named one concurrency experiment for the sweeper: remove the
    row lock, run TWO CONCURRENT SWEEPS, and the single-settlement assertion
    must red. Round 1 shipped a lock-MODE mutation in its place and recorded no
    deviation (r1 finding 10 / B13), so the specified experiment had never been
    run. This is it: two sweeps, in two sessions, on one past-horizon row, with
    no sleep deciding the outcome.

    What it asserts is the diagnosis' own assertion — across both sweeps the
    row is settled EXACTLY once, and the void it carries is one void. What the
    experiment then MEASURED about the predicted mutation is recorded as a
    numbered deviation in the round-2 notes rather than assumed here: this test
    states the property, and the mutation log says which mutations move it.
    """
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                sid = await _make_series(conn, age_days=20)
                await _add_game(conn, sid, ended_days_ago=20)

            a, b = await asyncio.gather(_sweep(Session), _sweep(Session))
            # Exactly one of the two concurrent sweeps settles the row. Which
            # one is not determined and is not asserted — the SUM is the
            # property, because "settled twice" and "settled by neither" are
            # both defects and only the total can tell them apart (#441).
            assert a + b == 1, (a, b)

            row = await _row(engine, sid)
            assert row["status"] == "canceled", row
            assert row["invalidation_reason"] == VOID_REASON, row
            assert row["invalidated_at"] is not None, row
            # And the settlement stayed delta-free under contention too: the
            # arm that lost the race must not have written a second void over
            # the first, nor a completion.
            assert row["completed_at"] is None, row
            assert row["winner_side"] is None, row
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


# ══════════════════════ round 2 ══════════════════════════════════════════
#
# Everything below closes a round-1 finding by NUMBER. Each one is reddened by
# a mutation in bug391_mutation_controls.py and each of those mutations has an
# inert twin at the same site that must stay green, so a red proves the test is
# measuring the behaviour and not merely that the file moved (#391).


def _dominates(node, first: str, second: str) -> int:
    """How many statement LISTS inside `node` run `first` before `second`.

    Raises when any list runs them the other way round. This is the property a
    same-function text search cannot see: `a in unparse(fn) and b in
    unparse(fn)` is equally true with the two in the wrong order (r1 F7 /
    finding 9). A list where ONE statement contains both needles is an outer
    block that merely encloses the pair — it orders nothing, so it is skipped
    rather than counted or failed.
    """
    ordered = 0
    for block in _blocks_of(node):
        src = [ast.unparse(st) for st in block]
        f = [i for i, s in enumerate(src) if first in s]
        g = [i for i, s in enumerate(src) if second in s]
        if not f or not g or set(f) == set(g):
            continue
        assert max(f) < min(g), f"{first!r} does not precede {second!r}: {src}"
        ordered += 1
    return ordered


def _block_dominates(block, first_pred, second_pred) -> bool:
    """True when one statement of `block` matching `first_pred` comes strictly
    before a statement matching `second_pred`, in the SAME statement list.

    This is the control-flow property a same-function text search cannot see:
    `x in ast.unparse(fn)` is equally true when the two statements are in the
    wrong order, or in two branches that never run together (r1 F7 / finding
    9). Statement lists are straight-line, so index order IS dominance here.
    """
    idx_first = idx_second = None
    for i, st in enumerate(block):
        src = ast.unparse(st)
        if idx_first is None and first_pred(st, src):
            idx_first = i
        if second_pred(st, src):
            idx_second = i if idx_second is None else idx_second
    return (idx_first is not None and idx_second is not None
            and idx_first < idx_second)


def _assigned_in_scope(node) -> set:
    """Names `node` binds in ITS OWN scope, at any depth.

    A nested `def` contributes its NAME and nothing from its body: that body
    is a different scope, and counting its locals here would make an unrelated
    helper variable look like a binding of the enclosing function.
    """
    out: set = set()

    def walk(n):
        for st in ast.iter_child_nodes(n):
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.add(st.name)
                continue
            if isinstance(st, ast.Lambda):
                continue
            if isinstance(st, ast.Assign):
                for t in st.targets:
                    out.update(x.id for x in ast.walk(t)
                               if isinstance(x, ast.Name))
            elif isinstance(st, (ast.AugAssign, ast.AnnAssign)):
                out.update(x.id for x in ast.walk(st.target)
                           if isinstance(x, ast.Name))
            elif isinstance(st, (ast.For, ast.AsyncFor)):
                out.update(x.id for x in ast.walk(st.target)
                           if isinstance(x, ast.Name))
            elif isinstance(st, (ast.With, ast.AsyncWith)):
                for item in st.items:
                    if item.optional_vars is not None:
                        out.update(x.id for x in ast.walk(item.optional_vars)
                                   if isinstance(x, ast.Name))
            walk(st)

    walk(node)
    return out


def _terminates(block) -> bool:
    """True when this statement list cannot fall through to the next one."""
    return bool(block) and isinstance(block[-1],
                                      (ast.Raise, ast.Return, ast.Continue,
                                       ast.Break))


def _straightline(body) -> list:
    """`body` flattened into the statements that run on EVERY path through it.

    A `try:` whose every handler terminates the function — the
    validate-or-raise shape this sink opens with — does not make its body
    conditional: if the body did not complete, nothing after the `try` runs at
    all. Its statements therefore dominate whatever follows, and counting them
    as "bound only inside a branch" would flag a binding that is in fact on
    every path. Anything else (an `if`, a `for`, a handler that falls through)
    stays unexpanded, because those genuinely can be skipped.
    """
    out = []
    for st in body:
        if (isinstance(st, ast.Try)
                and all(_terminates(h.body) for h in st.handlers)
                and st.handlers):
            out.extend(_straightline(st.body))
            out.extend(_straightline(st.orelse))
            out.extend(_straightline(st.finalbody))
            continue
        out.append(st)
    return out


def _blocks_of(node):
    """Every statement LIST inside a node (a body, an orelse, a finalbody)."""
    for n in ast.walk(node):
        for field in ("body", "orelse", "finalbody"):
            seq = getattr(n, field, None)
            if isinstance(seq, list) and seq and isinstance(seq[0], ast.stmt):
                yield seq


# ── finding 1 (HIGH, B14): the horizon-won race pays the game it recorded ──


def _resolved_branch():
    """The `if series["status"] != "active":` branch of `submit_ovt_match`."""
    fn = _fn_named("submit_ovt_match")
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        test = ast.unparse(node.test)
        if "series['status'] != 'active'" in test.replace('"', "'"):
            return node
    raise AssertionError("the resolved-series re-check is gone from the sink")


def test_a_report_landing_on_a_settled_series_still_pays_that_game():
    """finding 1: the determinate path may not skip an award that was earned.

    The sweep and the report serialise on the same series row (see the lock
    test below), so a report that arrives after a void takes ONE determinate
    path — this branch. Before round 2 that path committed the match and its
    card rows and returned above the per-game award, so all three seats
    silently lost a game they played. The award call must now DOMINATE the
    return on the settled-without-play arm.
    """
    branch = _resolved_branch()
    inner = [n for n in branch.body
             if isinstance(n, ast.If)
             and "_OVT_SETTLED_WITHOUT_PLAY" in ast.unparse(n.test)]
    assert len(inner) == 1, ast.unparse(branch)[:400]
    paid = inner[0]
    assert _block_dominates(
        paid.body,
        lambda st, src: "_award_the_game()" in src,
        lambda st, src: isinstance(st, ast.Return)), ast.unparse(paid)[:600]
    # And the award is not quietly also applied to a series resolved BY play:
    # that one already paid its own completion bonus, so the outer arm pays
    # nothing — and SAYS so, because an invisible skip is the defect this
    # finding is about.
    after = [n for n in branch.body if n is not paid]
    tail = "\n".join(ast.unparse(n) for n in after)
    assert "_award_the_game" not in tail, tail[:400]
    # The needle is the whole phrase, not a bare "no" that "not" would already
    # satisfy — a filter that matches something else is not measuring the line
    # it names (#441). The arm must also NAME the status rather than assert
    # how the series was resolved: an unknown word lands here too.
    assert "no per-game" in tail and "award is granted" in tail, tail[:400]
    assert "status=" in tail, tail[:400]


def test_the_settled_arm_pays_with_names_that_are_bound_before_it():
    """ADDED ROW B16: the paying arm's inputs are bound on every path to it.

    Sibling sweep of finding 9 (#432). Finding 9 is about one grant whose
    ORDER a same-function text search could not see; the defect CLASS is "a
    statement that reads a name the control flow does not guarantee is bound
    yet". The settled-without-play arm is the other member of that class and
    the more expensive one, because it is the arm finding 1 added in order to
    PAY: it calls `_award_the_game()` and reads `id_by_steam`, and that helper
    in turn reads `_award`, `_ovt_pod`, `_solo_r` and `_duo_avg_r`. If a later
    refactor moves any of those bindings inside a branch this path can skip,
    the arm raises `NameError` AFTER the match row is inserted — the game is
    recorded and never paid, which is precisely the outcome finding 1 exists
    to remove, reintroduced silently.

    DOMINANCE, not presence: every such name must be bound in the function's
    own top-level statement list STRICTLY BEFORE the arm. That list is
    straight-line, so index order is dominance (the property
    `_block_dominates` checks). A name bound only inside some other `if` would
    still satisfy `"id_by_steam" in ast.unparse(fn)` — the check this one
    exists to replace (#306).

    The name set is DERIVED from the arm and from the helper it calls, never
    listed here: a hardcoded list stops measuring the moment the arm gains a
    dependency (#342).
    """
    fn = _fn_named("submit_ovt_match")
    flat = _straightline(fn.body)
    arm_idx = None
    bound: dict = {}
    for i, st in enumerate(flat):
        if isinstance(st, ast.Assign):
            for t in st.targets:
                for nn in ast.walk(t):
                    if isinstance(nn, ast.Name):
                        bound.setdefault(nn.id, i)
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bound.setdefault(st.name, i)
        if (arm_idx is None and isinstance(st, ast.If)
                and "series['status'] != 'active'"
                in ast.unparse(st.test).replace('"', "'")):
            arm_idx = i
    assert arm_idx is not None, "the resolved-series arm is no longer top level"

    used = {n.id for n in ast.walk(flat[arm_idx]) if isinstance(n, ast.Name)}
    # The arm calls the helper, so the helper's own free names are the arm's
    # dependencies too — that indirection is where a NameError would hide.
    if "_award_the_game" in bound:
        helper = flat[bound["_award_the_game"]]
        used |= {n.id for n in ast.walk(helper) if isinstance(n, ast.Name)}
    # Sanity: the two names the arm cannot pay without must be in the derived
    # set, or this test is measuring an arm that no longer pays (#441).
    assert {"_award_the_game", "id_by_steam"} <= used, sorted(used)

    # Every name this function assigns ITSELF, at any depth, but not the
    # locals of the helpers nested in it — those are their own scope. A name
    # in this set is a local of `submit_ovt_match`, so reading it before it is
    # bound is a NameError and not a module lookup.
    local_assigned = _assigned_in_scope(fn)
    # Names the arm binds for itself before using them are not dependencies
    # of the arm — they are its own locals.
    used -= _assigned_in_scope(flat[arm_idx])

    # A dependency the arm reads that this function binds must be bound at the
    # function's TOP level and before the arm. Binding it only inside some
    # other branch removes it from `bound` while leaving it in
    # `local_assigned` — which is the regression this row exists to catch, so
    # that case must FAIL here rather than pass for want of an entry.
    late = {}
    for name in sorted(used & local_assigned):
        if name not in bound:
            late[name] = "bound only inside a branch, not on every path"
        elif bound[name] >= arm_idx:
            late[name] = f"bound at index {bound[name]}, arm at {arm_idx}"
    assert not late, late


def test_the_settled_without_play_arm_never_moves_the_series_tally():
    """finding 1, the other half: paying a game must not resurrect a score."""
    branch = _resolved_branch()
    paid = next(n for n in branch.body
                if isinstance(n, ast.If)
                and "_OVT_SETTLED_WITHOUT_PLAY" in ast.unparse(n.test))
    src = ast.unparse(paid)
    assert "solo_series_wins =" not in src.replace("  ", " ")
    assert "duo_series_wins =" not in src.replace("  ", " ")
    # It does keep the per-slot ledger truthful about what it paid.
    for col in ("solo_xp_earned", "duo_a_xp_earned", "duo_b_xp_earned",
                "solo_gold_earned", "duo_a_gold_earned", "duo_b_gold_earned"):
        assert col in src, col


def test_the_settled_arm_pays_no_more_games_than_the_sitting_can_have():
    """finding 1, third half: the live arm is bounded and this one must be too.

    "At most once per match row" bounds a REPLAY, not a SERIES. The live arm
    stops paying because the tally resolves the series at
    `OVT_SERIES_WINS_REQUIRED` wins, after which every report is refused an
    award; this arm deliberately never advances the tally (see the test
    above), so it cannot inherit that bound. Without one of its own, one
    settled series keeps paying a per-game award for as long as reports arrive
    against it — bounded on the live path, unbounded here, which is not a
    difference two paths into the same XP and gold may have.

    Found by re-reading the comments this round's own fix wrote (#351).
    """
    branch = _resolved_branch()
    paid = next(n for n in branch.body if isinstance(n, ast.If)
                and "_OVT_SETTLED_WITHOUT_PLAY" in ast.unparse(n.test))

    # The count is READ, from the match table, BEFORE the branch that pays and
    # in the same statement list. A bound computed after the award is not a
    # bound, and one derived from the tally would be circular: the tally is
    # exactly what this arm does not move.
    assert _block_dominates(
        branch.body,
        lambda st, src: "_games_recorded =" in src and "ovt_matches" in src,
        lambda st, src: st is paid), ast.unparse(branch)[:800]
    # ...and the paying condition actually consults it.
    assert "_within_series_bound" in ast.unparse(paid.test), ast.unparse(paid.test)
    assert "OVT_SERIES_MAX_GAMES" in ast.unparse(branch), ast.unparse(branch)[:500]

    # ONE constant, read by BOTH arms. Two literals that happen to agree today
    # are a check that cannot fail (#342), so the live arm's own comparison
    # must read the same name rather than a bare number.
    assert main.OVT_SERIES_MAX_GAMES == main.OVT_SERIES_WINS_REQUIRED * 2 - 1
    live = ast.unparse(_fn_named("submit_ovt_match"))
    assert "series_done = solo_wins >= 2" not in live.replace("  ", " "), live[:200]
    assert live.count("OVT_SERIES_WINS_REQUIRED") >= 2, (
        live.count("OVT_SERIES_WINS_REQUIRED"))

    # The refusal is NAMED on the log line itself, not merely computed into a
    # variable: a bound that declines an award in silence is the same defect
    # as the skip this finding exists to remove. The needle is asserted on the
    # PRINT, because the assignment would satisfy a search of the whole branch
    # and that search could then never fail (#342 / #441).
    prints = [n for n in branch.body
              if isinstance(n, ast.Expr) and "print(" in ast.unparse(n)]
    assert prints, ast.unparse(branch)[:400]
    assert any("_why_unpaid" in ast.unparse(n) for n in prints), (
        [ast.unparse(n)[:200] for n in prints])
    tail = "\n".join(ast.unparse(n) for n in branch.body if n is not paid)
    assert "recorded games" in tail, tail[:500]


def test_the_report_sinks_series_lock_waits_so_the_void_cannot_be_missed():
    """finding 1's mechanism, stated as the property it rests on.

    `FOR NO KEY UPDATE` with NO `SKIP LOCKED` and no `NOWAIT`: the report sink
    WAITS for the janitor's lock. That is what makes the two paths serialise
    — the janitor declines a row this sink holds, and this sink blocks until a
    committing janitor releases one, then reads the committed row. A declining
    read here would answer on a row version it did not wait to see.
    """
    lock = _only(_sql_literals(main.submit_ovt_match), "FOR NO KEY UPDATE")
    up = " ".join(lock.split()).upper()
    assert "FOR NO KEY UPDATE" in up, lock
    assert "SKIP LOCKED" not in up, lock
    assert "NOWAIT" not in up, lock
    # The janitor's half of the same meeting declines rather than waits.
    settle = _only(_sql_literals(main._ovt_settle_horizon_row),
                   "FOR NO KEY UPDATE")
    assert "SKIP LOCKED" in " ".join(settle.split()).upper(), settle


def test_the_seat_award_pays_all_three_seats_in_canonical_order():
    """finding 1: the loop both callers share, exercised without a route.

    `_ovt_award_seats` is module level precisely so this can run: it proves
    all three seats are paid, in canonical `str(pid)` order (#197), with each
    seat's multiplier reading the OPPOSING side's rating and podium standing.
    """
    seen = []

    async def _fake_award(pid, won, mult):
        seen.append((pid, won, round(float(mult), 4)))
        return (100, 1)

    solo, duo_a, duo_b = "ccc", "aaa", "bbb"

    async def go():
        return await main._ovt_award_seats(
            _fake_award, solo_id=solo, duo_a_id=duo_a, duo_b_id=duo_b,
            winner_side=1, extra_pick=False,
            solo_r=1500.0, duo_avg_r=1500.0, podium=set())

    results, labels = _run(go())
    assert [p for p, _, _ in seen] == ["aaa", "bbb", "ccc"], seen
    assert set(results) == {solo, duo_a, duo_b}
    assert set(labels) == {solo, duo_a, duo_b}
    won_by = {p: w for p, w, _ in seen}
    assert won_by[solo] is True and won_by[duo_a] is False
    assert won_by[duo_b] is False
    # The opposing-side read: put the DUO on the podium and only the solo's
    # multiplier may move.
    async def go2():
        return await main._ovt_award_seats(
            _fake_award, solo_id=solo, duo_a_id=duo_a, duo_b_id=duo_b,
            winner_side=1, extra_pick=False,
            solo_r=1500.0, duo_avg_r=1500.0, podium={duo_a})
    seen.clear()
    _run(go2())
    mult_by = {p: m for p, _, m in seen}
    base_solo, _ = main._ovt_difficulty_mult(True, False, 1500.0, False)
    assert mult_by[solo] != round(float(base_solo), 4), seen
    base_duo, _ = main._ovt_difficulty_mult(False, False, 1500.0, False)
    assert mult_by[duo_a] == round(float(base_duo), 4), seen


# ── finding 2 (MEDIUM, B5/F1): an existing completion stamp is declined ────


def test_both_halves_of_the_predicate_refuse_a_completion_stamp():
    """finding 2: the post-void continuation refusal rests on the anchor.

    The continuation window anchors on `COALESCE(completed_at, created_at)`.
    That anchor is only the 14-day-old `created_at` while the row carries NO
    completion stamp, so a row that already has one must never be voided into
    the prior-series lookup's scope.
    """
    cand = _only(_sql_literals(main._ovt_horizon_candidates), "FROM ovt_series")
    lock_half = _only(_sql_literals(main._ovt_settle_horizon_row),
                      "SELECT 1 FROM ovt_series")
    for sql in (cand, lock_half):
        assert "completed_at IS NULL" in " ".join(sql.split()), sql
    # And the write still clears nothing: the refusal is in the predicate, so
    # the settlement stays two invalidation columns wide (B2).
    upd = " ".join(_settle_update_sql().split())
    assert "completed_at" not in upd, upd


def test_the_declined_stamp_rows_are_counted_not_silently_filtered():
    """finding 2: a filter whose declines nobody can see is the same defect."""
    counter = _only(_sql_literals(main._ovt_horizon_stamped_backlog),
                    "COUNT(*)")
    flat = " ".join(counter.split())
    assert "completed_at IS NOT NULL" in flat, flat
    assert "is_ranked = FALSE" in flat, flat
    assert "NOT EXISTS" in flat, flat
    tick = _names_in(_fn_named("_ovt_horizon_sweep_tick"))
    assert "_ovt_horizon_stamped_backlog" in tick, sorted(tick)


# ── finding 3 (MEDIUM): one sweep per process ─────────────────────────────


async def _tick_bounded_or_fail(factory, *, limit=10.0):
    """`_ovt_horizon_sweep_tick_bounded`, with the test's own bound on it.

    These cases drive the tick against a sweep that never finishes, so they
    depend on the ARM's budget to hand control back. A test that depends on
    the thing it is testing must carry its own bound, or the mutation that
    removes that budget does not RED — it HANGS, and a control that hangs
    produces no verdict at all rather than a wrong one. The table-lock case
    already bounds itself this way; this is the same bound applied to its
    siblings (#432: the defect is a class, sweep the siblings).
    """
    try:
        return await asyncio.wait_for(
            main._ovt_horizon_sweep_tick_bounded(factory), timeout=limit)
    except asyncio.TimeoutError:
        pytest.fail(
            f"the horizon tick never gave the loop back: still waiting after "
            f"{limit}s with a budget of {main.OVT_HORIZON_TICK_BUDGET_S}s, so "
            f"every arm behind it in that tick was skipped")


def test_a_tick_declines_while_the_previous_one_is_still_in_flight():
    """finding 3: a cancelled tick can outlive the tick that cancelled it.

    `task.cancel()` REQUESTS cancellation. A task wedged in a server-side wait
    unwinds when that wait ends, so without a single-flight guard every 60
    seconds starts another sweep behind the same stuck connection. The second
    tick must decline, on its own line, and the slot must come back.
    """
    started = []

    async def go():
        main._ovt_horizon_tick_inflight = None
        gate = asyncio.Event()

        async def _slow(_factory):
            started.append(1)
            await gate.wait()
            return 0

        real, budget = main._ovt_horizon_sweep_tick, main.OVT_HORIZON_TICK_BUDGET_S
        main._ovt_horizon_sweep_tick = _slow
        main.OVT_HORIZON_TICK_BUDGET_S = 0.25
        try:
            first = await _tick_bounded_or_fail(None)
            assert first == 0                      # abandoned at the budget
            assert main._ovt_horizon_tick_inflight is not None
            second = await _tick_bounded_or_fail(None)
            assert second == 0
            assert started == [1], started          # the second never started
            gate.set()
            for _ in range(200):
                await asyncio.sleep(0.01)
                if main._ovt_horizon_tick_inflight is None:
                    break
            assert main._ovt_horizon_tick_inflight is None
            third = await _tick_bounded_or_fail(None)
            assert third == 0
            assert started == [1, 1], started       # the slot came back
        finally:
            main._ovt_horizon_sweep_tick = real
            main.OVT_HORIZON_TICK_BUDGET_S = budget
            main._ovt_horizon_tick_inflight = None
    _run(go())


def test_the_single_flight_decline_says_so_on_its_own_line(capsys):
    """finding 3: the decline is named, or the pool drains silently."""
    async def go():
        main._ovt_horizon_tick_inflight = None
        gate = asyncio.Event()

        async def _slow(_factory):
            await gate.wait()
            return 0

        real, budget = main._ovt_horizon_sweep_tick, main.OVT_HORIZON_TICK_BUDGET_S
        main._ovt_horizon_sweep_tick = _slow
        main.OVT_HORIZON_TICK_BUDGET_S = 0.25
        try:
            await _tick_bounded_or_fail(None)
            await _tick_bounded_or_fail(None)
        finally:
            gate.set()
            await asyncio.sleep(0.05)
            main._ovt_horizon_sweep_tick = real
            main.OVT_HORIZON_TICK_BUDGET_S = budget
            main._ovt_horizon_tick_inflight = None
    _run(go())
    out = capsys.readouterr().out
    declined = [ln for ln in out.splitlines() if "tick declined" in ln]
    assert len(declined) == 1, out
    assert "still in flight" in declined[0], declined


# ── finding 4 (MEDIUM, B6): the lock census is derived, not authored ───────


def test_the_janitor_lock_census_sees_orm_locks_and_not_only_sql():
    """finding 4: a census that cannot see a whole lock family is not a check.

    The SQL half of the walker sees `text(<literal>)` only, so a census built
    from it alone reports a WAIT count that is wrong in the one direction that
    matters — too low — while calling itself exhaustive (#342). The census is
    now derived from the same live call graph in BOTH families.
    """
    census = main._janitor_lock_census()
    orm = [r for r in census["declines"] + census["waits"] if r["kind"] == "orm"]
    # The set that must never be empty: an ORM-blind census would report zero
    # here and every count below would still look plausible.
    assert census["orm_total"] == len(orm) >= 1, census["orm_total"]
    waits_orm = [r for r in census["waits"] if r["kind"] == "orm"]
    # The unbounded waiter the round-1 census omitted: an overdue-match row
    # held elsewhere stalls the tournament tick behind it.
    assert any(r["module"] == "tournaments"
               and r["func"] == "_apply_no_show_forfeits"
               for r in waits_orm), waits_orm
    # Both counts, because one source line can expand into several statements
    # and reporting only one number is how two counts get reconciled instead
    # of explained (#431).
    assert len(census["declines"]) == 23, census["declines"]
    assert len(census["waits"]) == 13, census["waits"]
    assert len(census["decline_sites"]) == 20, census["decline_sites"]
    assert len(census["wait_sites"]) == 10, census["wait_sites"]


def test_a_lock_taking_path_outside_the_counted_set_reds_the_census():
    """finding 4's control: the census must NOTICE a new lock-taking path.

    A census asserted against numbers nobody can move is decoration. This
    feeds the walker a source of its own in which one reachable helper grows
    an ORM lock, and requires the census to count it.
    """
    src = textwrap.dedent('''
        from sqlalchemy import select, text

        async def _helper(db):
            await db.execute(text("SELECT 1 FROM players FOR UPDATE"))

        async def queue_cleanup_loop():
            await _helper(None)
    ''').lstrip("\n")
    inv = main._janitor_sql_from_sources(
        {"main": src}, (("main", "queue_cleanup_loop"),))
    assert inv["orm_locks"] == [], inv["orm_locks"]
    grown = src.replace(
        "    await _helper(None)",
        "    await _helper(None)\n"
        "    q = select(1).with_for_update()\n"
        "    r = select(1).with_for_update(skip_locked=True)\n")
    inv2 = main._janitor_sql_from_sources(
        {"main": grown}, (("main", "queue_cleanup_loop"),))
    modes = sorted(r["mode"] for r in inv2["orm_locks"])
    assert modes == ["DECLINES", "WAITS"], inv2["orm_locks"]
    # A mode the walk cannot PROVE is not a mode it may certify as declining:
    # an unresolvable keyword counts as a waiter, which is the safe direction
    # for a number whose job is an upper bound on surprise (#342).
    unproven = src.replace(
        "    await _helper(None)",
        "    await _helper(None)\n"
        "    s = select(1).with_for_update(skip_locked=_runtime_flag)\n")
    inv3 = main._janitor_sql_from_sources(
        {"main": unproven}, (("main", "queue_cleanup_loop"),))
    assert [r["mode"] for r in inv3["orm_locks"]] == ["WAITS"], inv3["orm_locks"]


# ── finding 5 (MEDIUM, B9/F4): the CALLERS carry the database guard ────────


THIS_FILE = Path(__file__).resolve()
RUNNER_PY = THIS_FILE.with_name("bug391_mutation_controls.py")


def _fn_in_source(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == name)


def test_the_destructive_callers_are_guarded_not_only_the_helper():
    """finding 5: testing the helper leaves the WIRING untested.

    `test_the_live_half_refuses_any_database_but_the_dedicated_one` calls
    `_assert_dedicated_db` directly, so it stays green with either caller's
    guard deleted — and a wrong database then reaches a DROP. These are the
    two destructive callers, and each must run the guard BEFORE its
    destructive statement, at the top level of the function rather than under
    a branch that can be skipped.
    """
    reset = _fn_in_source(THIS_FILE, "_reset")
    assert _dominates(reset, "_assert_dedicated_db(conn)",
                      "pg_terminate_backend") == 1, ast.unparse(reset)[:600]
    # ...and on the UNCONDITIONAL path: a guard under a branch, a loop or an
    # except handler is a guard that some run does not execute.
    assert not any(isinstance(n, (ast.If, ast.Try, ast.While, ast.For))
                   and "_assert_dedicated_db(conn)" in ast.unparse(n)
                   for n in ast.walk(reset)), ast.unparse(reset)[:600]

    # The runner's own guard. The needle is the COMPARISON, not
    # `current_database()` — that call also appears inside the terminate
    # statement itself, so a needle matching both would be measuring the line
    # it is meant to order against (#441).
    slate = _fn_in_source(RUNNER_PY, "clean_slate")
    assert _dominates(slate, "dbname != EXPECTED_DB",
                      "pg_terminate_backend") == 1, ast.unparse(slate)[:800]
    raises = [s for s in ast.walk(slate) if isinstance(s, ast.Raise)]
    assert raises, "the runner's name check no longer refuses anything"


def _module_binding(path: Path, name: str):
    """The VALUE node of a module-level `name = ...` in `path`.

    Parsed, never grepped. Every constant these two tests judge is also QUOTED
    inside the mutation entry that edits it, so a substring search over the
    whole text is satisfied by the control's own literal and can no longer
    fail (#342) — it matches the line it was meant to measure (#441). The
    screen caught exactly that: M24 deleted the real map entry and the test
    stayed green on the copy inside M24 itself.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
    raise AssertionError(f"{path.name} has no module-level {name}")


def test_the_mutation_runner_certifies_every_file_a_run_used():
    """finding 6: hashing only the module under mutation is a partial receipt.

    The runner edits `main.py` and reports it came back byte-identical. It also
    READS the suite it drives and its own assertions, and round 2 lets it edit
    those too — so a harness file could change between the run and the commit
    while the reported `main.py MATCH` stayed true. Every file a run touches is
    hashed and every hash is printed.
    """
    files = _module_binding(RUNNER_PY, "FILES")
    assert isinstance(files, ast.Dict), ast.unparse(files)[:200]
    keys = [k.value for k in files.keys if isinstance(k, ast.Constant)]
    assert len(keys) == len(files.keys), ast.unparse(files)[:200]
    assert set(keys) == {"main", "tournaments", "suite", "runner"}, keys

    # ...and the receipt must WALK that map. One loop over FILES hashes each
    # file and reports it; a body that named a file instead would print a true
    # MATCH for that one while the rest moved. Exactly one such loop, so a
    # pin that had come to measure an empty set would be a failure (#342).
    runner = _fn_in_source(RUNNER_PY, "main")
    over_files = [n for n in ast.walk(runner)
                  if isinstance(n, ast.For) and "FILES" in ast.unparse(n.iter)]
    receipts = [n for n in over_files
                if "sha256" in ast.unparse(n) and "MISMATCH" in ast.unparse(n)]
    assert len(receipts) == 1, [ast.unparse(n.iter) for n in over_files]


def test_both_destructive_callers_name_the_same_dedicated_database():
    """finding 5: two guards that disagree protect nothing."""
    named = _module_binding(RUNNER_PY, "EXPECTED_DB")
    assert isinstance(named, ast.Constant), ast.unparse(named)
    assert named.value == EXPECTED_DB, named.value


# ── finding 9 (LOW, F7): the earned-pack grant is DOMINATED, not co-located ─


def test_the_ovt_earned_pack_grant_is_dominated_by_the_completion_write():
    """finding 9: `x in ast.unparse(fn)` cannot see order.

    The inline grant is safe only because the series is ALREADY being written
    `status='completed'` when it runs. Same-function text is equally true with
    the grant moved above that write, which is precisely the move that would
    turn this arm's `invalidated_at` into a pack reversal.
    """
    fn = _fn_named("submit_ovt_match")
    # A pin that measured an empty set would pass forever (#342): exactly one
    # statement list must order the completion write ahead of the grant.
    assert _dominates(fn, "UPDATE ovt_series SET status='completed'",
                      "_pc_grant_earned_packs") == 1


# ── finding 11 (LOW, B7): every source citation resolves after the last edit ─


PIN_RE = re.compile(r'PIN main\.py:(\d+) "([^"]+)"')

# The size of the census derived below, recorded so a reader that is added or
# removed cannot pass unnoticed. A SUPERSET by construction — every SQL
# statement in main.py naming `ovt_series` and the word `status` — which is
# what makes it derived from the tree rather than authored from the notes.
OVT_SERIES_STATUS_STATEMENTS = 31


def test_every_bug391_source_citation_resolves_to_what_it_names():
    """finding 11: a stale line pin conceals the regression it was written for.

    A citation written as a bare line number is unfalsifiable prose the moment
    anything above it moves. `PIN main.py:<line> "<anchor>"` exists for no
    other purpose than to be checked (#306): the anchor must appear on that
    exact line, so any edit that shifts it reds here instead of quietly
    pointing a future reader at an unrelated statement (#752).

    The anchor must also be UNIQUE in the file, and that half is not
    decoration: an anchor carried by three different lines lets the pin drift
    onto any of them and still resolve, which is a check that cannot fail
    (#342). Its own PIN comments are excluded from the count, or an anchor
    would be satisfied by the citation quoting it and measure the line it was
    meant to check (#441).
    """
    lines = MAIN_PY.read_text(encoding="utf-8").splitlines()
    pins = PIN_RE.findall("\n".join(lines))
    assert len(pins) >= 2, pins
    for num, anchor in pins:
        n = int(num)
        assert 1 <= n <= len(lines), (num, anchor)
        assert anchor in lines[n - 1], (num, anchor, lines[n - 1])
        carriers = [i + 1 for i, ln in enumerate(lines)
                    if anchor in ln and "PIN main.py:" not in ln]
        assert carriers == [n], (num, anchor, carriers)


# ── finding 13 (LOW, F5): the status-reader census has a revert-red control ─


def _ovt_series_status_statements() -> list:
    """Every SQL literal in main.py that names `ovt_series` and `status`.

    `ovt_series` has no ORM class on this tree, so string literals are the
    whole reader set — which is what makes this census derivable rather than
    authored.
    """
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        flat = " ".join(node.value.split())
        # Prose is not a reader. A filter that kept the docstring EXPLAINING
        # the rule would measure the comment instead of the statement it
        # describes (#441).
        if not re.match(r"^(SELECT|INSERT|UPDATE|DELETE|WITH)\b", flat, re.I):
            continue
        if "ovt_series" in flat and re.search(r"\bstatus\b", flat):
            out.append((node.lineno, flat))
    return sorted(set(out))


def test_the_ovt_series_status_reader_census_stays_complete():
    """finding 13: the corrected census needs a control that can RED.

    The lane notes enumerate every reader of `ovt_series.status` and state
    what a 14-day-stuck row does to each. Re-removing one, or adding a reader
    nobody adds to the census, must not leave every test green — so the set is
    derived from the tree here and its size is pinned.
    """
    stmts = _ovt_series_status_statements()
    assert len(stmts) == OVT_SERIES_STATUS_STATEMENTS, [s[0] for s in stmts]
    # There is no ORM class to read the column behind the census's back.
    src = MAIN_PY.read_text(encoding="utf-8")
    assert "class OvtSeries" not in src
    # The readers the census's verdict rests on, by the text that identifies
    # them: drop one from main.py and this reds.
    for needle in (
            "status IN ('completed', 'canceled', 'cancelled')",   # prior lookup
            "status IN ('active', 'dc_paused', 'dc_incomplete')",  # live arm
            "s.status = 'active'",                                # this sweep
    ):
        assert any(needle in flat for _, flat in stmts), needle


# ───────────────────── round 2, live half ─────────────────────────────────


async def _stamp(conn, series_id: str, *, minutes_ago: float) -> None:
    """Give an `active` row a completion stamp — schema-valid, status-free."""
    await conn.execute(text("""
        UPDATE ovt_series
           SET completed_at = NOW() - make_interval(secs => CAST(:s AS double precision))
         WHERE id = CAST(:i AS uuid)
    """), {"i": series_id, "s": minutes_ago * 60.0})


@live
def test_an_active_row_carrying_a_completion_stamp_is_declined(capsys):
    """finding 2: the post-void continuation refusal rests on the anchor.

    The continuation window anchors on `COALESCE(completed_at, created_at)`.
    Void a 20-day-old `active` row that already carries a stamp from ten
    minutes ago and the prior-series lookup accepts it — the row is now
    'canceled', so it is in scope, and the anchor is inside the 60-minute
    window. The arm therefore declines the row, counts it and names it.
    """
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                plain = await _make_series(conn, age_days=20)
                await _add_game(conn, plain, ended_days_ago=20)
                stamped = await _make_series(conn, age_days=20)
                await _add_game(conn, stamped, ended_days_ago=20)
                await _stamp(conn, stamped, minutes_ago=10)
            main._ovt_horizon_stamped_last_seen = -1
            main._ovt_horizon_ranked_last_seen = -1
            settled = await main._ovt_horizon_sweep_tick(Session)
            assert settled == 1, settled
            assert (await _row(engine, plain))["status"] == "canceled"
            held = await _row(engine, stamped)
            assert held["status"] == "active", held
            assert held["invalidated_at"] is None, held
        finally:
            await engine.dispose()
    _run(go())
    out = capsys.readouterr().out
    named = [ln for ln in out.splitlines()
             if "carry a completed_at" in ln]
    assert len(named) == 1, out
    assert named[0].strip().startswith("[OVT-HORIZON] 1 idle"), named


@live
def test_a_stamped_row_would_be_continuable_if_this_arm_voided_it():
    """finding 2, the player-visible consequence the decline exists to avoid.

    Nothing here calls the sweep: it voids the stamped row BY HAND and shows
    the continuation's own two statements then accept it. That is the outcome
    the predicate's `completed_at IS NULL` refuses, stated as the behaviour
    rather than as a claim about the behaviour (#302).
    """
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            async with engine.begin() as conn:
                sid = await _make_series(conn, age_days=20)
                await _add_game(conn, sid, ended_days_ago=20)
                await _stamp(conn, sid, minutes_ago=10)
                await conn.execute(text("""
                    UPDATE ovt_series SET status = 'canceled',
                           invalidated_at = NOW(),
                           invalidation_reason = :r
                     WHERE id = CAST(:i AS uuid)
                """), {"i": sid, "r": VOID_REASON})
            async with engine.connect() as conn:
                prior = (await conn.execute(text("""
                    SELECT completed_at, created_at FROM ovt_series
                     WHERE status IN ('completed', 'canceled', 'cancelled')
                       AND id = CAST(:i AS uuid)
                """), {"i": sid})).mappings().first()
            assert prior is not None, "the void put the row in the lookup's scope"
            anchor = prior["completed_at"] or prior["created_at"]
            age_min = (datetime.now(timezone.utc) - anchor).total_seconds() / 60.0
            # INSIDE the window — which is why the arm must never create it.
            assert age_min < main._CONTINUATION_WINDOW_MINUTES, age_min
        finally:
            await engine.dispose()
    _run(go())


@live
def test_a_ranked_series_played_today_is_not_a_backlog_warning(capsys):
    """finding 7: idle means the same thing in both halves of the arm.

    A ranked series created twenty days ago whose trio played this morning is
    live. Counting it emits a warning about an unbuilt settlement for a
    sitting that needs none — and a warning that fires when nothing is wrong
    is how a real one stops being read.
    """
    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                played = await _make_series(conn, age_days=20, is_ranked=True)
                await _add_game(conn, played, ended_days_ago=0.02)
            main._ovt_horizon_ranked_last_seen = -1
            main._ovt_horizon_stamped_last_seen = -1
            async with Session() as db:
                n = await main._ovt_horizon_ranked_backlog(
                    db, main.OVT_ABANDONED_HORIZON_DAYS)
                await db.rollback()
            assert n == 0, n
            await main._ovt_horizon_sweep_tick(Session)
            # ...and a genuinely idle ranked row still IS counted.
            async with engine.begin() as conn:
                idle = await _make_series(conn, age_days=20, is_ranked=True)
                await _add_game(conn, idle, ended_days_ago=20)
            async with Session() as db:
                n2 = await main._ovt_horizon_ranked_backlog(
                    db, main.OVT_ABANDONED_HORIZON_DAYS)
                await db.rollback()
            assert n2 == 1, n2
            assert (await _row(engine, played))["status"] == "active"
        finally:
            await engine.dispose()
    _run(go())
    out = capsys.readouterr().out
    assert "RANKED 1v2 series past the" not in out, out


@live
def test_the_void_and_a_report_serialise_on_the_same_series_row():
    """finding 1's mechanism, executed.

    The janitor holds the row and writes the void; the report sink's own lock
    statement — `FOR NO KEY UPDATE`, no SKIP LOCKED — must BLOCK rather than
    read the pre-void version, and must observe `canceled` once the janitor
    commits. That is what makes "whichever commits second sees the first" a
    property of the tree rather than a sentence about it.
    """
    report_lock = _only(_sql_literals(main.submit_ovt_match),
                        "FOR NO KEY UPDATE")

    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                sid = await _make_series(conn, age_days=20)
                await _add_game(conn, sid, ended_days_ago=20)

            sweeper = Session()
            reporter = Session()
            try:
                wrote = await main._ovt_settle_horizon_row(
                    sweeper, sid, main.OVT_ABANDONED_HORIZON_DAYS)
                assert wrote is True
                # Uncommitted. The report sink's lock must not get past it.
                task = asyncio.ensure_future(
                    reporter.execute(text(report_lock),
                                     {"sid": uuid.UUID(sid)}))
                await asyncio.sleep(1.0)
                assert not task.done(), (
                    "the report sink's series lock did not wait for the "
                    "janitor's uncommitted void")
                await sweeper.commit()
                rows = (await asyncio.wait_for(task, timeout=10)).mappings().first()
                assert rows["status"] == "canceled", dict(rows)
                assert rows["invalidation_reason"] == VOID_REASON, dict(rows)
                await reporter.rollback()
            finally:
                await _shut(sweeper)
                await _shut(reporter)
        finally:
            await engine.dispose()
    _run(go())


@live
def test_the_janitor_declines_a_row_the_report_sink_is_holding():
    """finding 1, the other direction of the same meeting.

    With the report sink holding its lock first, the janitor's `SKIP LOCKED`
    read declines and the row is left `active` for the next tick — so the two
    can never both decide this row, whichever arrives first.
    """
    report_lock = _only(_sql_literals(main.submit_ovt_match),
                        "FOR NO KEY UPDATE")

    async def go():
        engine = _engine()
        try:
            await _reset(engine)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                sid = await _make_series(conn, age_days=20)
                await _add_game(conn, sid, ended_days_ago=20)

            reporter = Session()
            sweeper = Session()
            try:
                await reporter.execute(text(report_lock),
                                       {"sid": uuid.UUID(sid)})
                wrote = await asyncio.wait_for(
                    main._ovt_settle_horizon_row(
                        sweeper, sid, main.OVT_ABANDONED_HORIZON_DAYS),
                    timeout=10)
                assert wrote is False
                await sweeper.rollback()
                await reporter.rollback()
                assert (await _row(engine, sid))["status"] == "active"
            finally:
                await _shut(reporter)
                await _shut(sweeper)
        finally:
            await engine.dispose()
    _run(go())
