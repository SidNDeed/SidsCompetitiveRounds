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


async def _reset(engine, schema: str = SCHEMA):
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
        # `schema` is this file's horizon tables unless a case passes its
        # own (the round-3 report-sink cases pass _sink_schema()); either
        # way it runs HERE, behind the database-name refusal above.
        for stmt in filter(None, (s.strip() for s in schema.split(";"))):
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


# ═════════════ round 3: one game, one record, whichever seats ═════════════
#
# Bug 391 round 3 answers the round-2 HIGH by number. The report sink checks
# the three players against the series as a SET, so it accepts them in any
# seats, while the replay key on ovt_matches is ORDERED:
# UNIQUE (photon_room_id, solo_id, duo_a_id, duo_b_id). The same game reported
# again with its duo pair reversed therefore missed the key and was recorded,
# and paid, a second time. The sink now gives the pair ONE order (the players'
# Steam ids compared ordinally, the order the client builds every report in)
# before any comparison or write, and asks "is this game already on record?"
# as a SET, under a lock on the room, before anything is written.
#
# The live cases drive the REAL handler, submit_ovt_match, end to end, on the
# two 1v2 tables exactly as the production migrations build them: the ordered
# key the HIGH turned on exists only there, never in a subset written by hand.
# Every test identity is outside the real identifier space: the Steam ids are
# this file's SIDS, and the rooms carry neither the server's issued room
# prefix nor its hex body.

SINK_ROOM = "t391-sitting"
SINK_ROOM_B = "t391-sitting-b"
SINK_HMAC = "t391-test-signing-key"
# One distinct value per player for every seat-keyed field, so a field left in
# its seat when its player moves reads as the OTHER player's value.
SINK_FPS = dict(zip(SIDS, (41, 42, 43)))
SINK_TIMELINE = dict(zip(SIDS, ("1,2,3", "4,5,6", "7,8,9")))
SINK_CARD = dict(zip(SIDS, ("T391 Card One", "T391 Card Two",
                            "T391 Card Three")))
SINK_END_STATS = {s: "1|" + "|".join([str(11 + i)] + ["-"] * 20)
                  for i, s in enumerate(SIDS)}
SINK_RATING = dict(zip(SIDS, (1400.0, 1600.0, 1800.0)))

SINK_PLAYERS = """
CREATE TABLE players (
    id UUID PRIMARY KEY,
    steam_id VARCHAR(20) UNIQUE NOT NULL,
    total_xp INTEGER NOT NULL DEFAULT 0,
    gold_earned INTEGER NOT NULL DEFAULT 0
)"""

# What the sink reads or writes beside the two tables under test. NO foreign
# keys, on purpose: the horizon cases' own reset drops `players` without
# CASCADE, and a sink case must not leave behind a table that blocks it.
SINK_EXTRAS = (
    """
CREATE TABLE ovt_match_cards (
    id BIGSERIAL PRIMARY KEY,
    match_id UUID NOT NULL,
    player_id UUID NOT NULL,
    card_name VARCHAR(64) NOT NULL,
    pick_order SMALLINT NOT NULL DEFAULT 0
)""",
    """
CREATE TABLE gold_transactions (
    id BIGSERIAL PRIMARY KEY,
    player_id UUID NOT NULL,
    amount INTEGER NOT NULL,
    reason VARCHAR(64) NOT NULL,
    reference_id VARCHAR,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
    """
CREATE TABLE glicko_ratings (
    player_id UUID PRIMARY KEY,
    rating DOUBLE PRECISION NOT NULL
)""",
)


def _sink_schema() -> str:
    """The statements `_reset` runs for the report-sink cases, in order.

    The two 1v2 tables come from the production migrations: the 1v2 schema's
    CREATE TABLE blocks whole, then every later ADD COLUMN on either table, in
    file order. Their SQL comments are dropped, because `_reset` splits on ';'
    and one comment inside ovt_series carries one. Beside them go the players
    columns the award writes and the tables in SINK_EXTRAS.
    """
    schema = SCHEMA_120.read_text(encoding="utf-8")
    stmts = [f"DROP TABLE IF EXISTS {t}" for t in (
        "ovt_match_cards", "gold_transactions", "glicko_ratings",
        "ovt_matches", "ovt_series", "players")]
    stmts.append(SINK_PLAYERS)
    for table in ("ovt_series", "ovt_matches"):
        m = re.search(r"^CREATE TABLE IF NOT EXISTS " + table + r" \(.*?^\);",
                      schema, re.M | re.S)
        assert m, f"the 1v2 schema no longer creates {table}"
        stmts.append(m.group(0)[:-1])
    added = 0
    for path in sorted((REPO_ROOT / "backend" / "sql").glob("*.sql")):
        for m in re.finditer(r"^ALTER TABLE\s+ovt_(?:series|matches)\s+"
                             r"ADD COLUMN IF NOT EXISTS[^;]*;",
                             path.read_text(encoding="utf-8"), re.M):
            stmts.append(m.group(0)[:-1])
            added += 1
    # Seven today (three damage timelines, three end stats, the room rules).
    # A count of zero would build the pre-201 table and still pass (#342).
    assert added >= 7, added
    stmts.extend(SINK_EXTRAS)
    out = [re.sub(r"--[^\n]*", "", s).strip() for s in stmts]
    assert not any(";" in s for s in out), "a statement still carries a ';'"
    return ";\n".join(out) + ";"


def _game_room(token: int, room: str = SINK_ROOM) -> str:
    """A report room in the sink's grammar: "<series room>_<6 digits>_r<n>"."""
    return f"{room}_{token:06d}_r4"


async def _sink_ids(conn) -> dict:
    rows = (await conn.execute(text("SELECT steam_id, id FROM players"))).all()
    return {r.steam_id: r.id for r in rows}


async def _sink_series(conn, seats, *, room: str = SINK_ROOM,
                       status: str = "active", age_days: float = 0.0) -> str:
    """A series row storing `seats`, (solo, duo_a, duo_b) Steam ids, in THAT
    order."""
    ids = await _sink_ids(conn)
    sid = str(uuid.uuid4())
    await conn.execute(text("""
        INSERT INTO ovt_series (id, solo_id, duo_a_id, duo_b_id, status,
                                photon_room_id, created_at)
        VALUES (CAST(:id AS uuid), :s, :a, :b, :st, :room,
                NOW() - make_interval(secs => CAST(:age AS double precision)))
    """), {"id": sid, "s": ids[seats[0]], "a": ids[seats[1]],
           "b": ids[seats[2]], "st": status, "room": room,
           "age": age_days * 86400.0})
    return sid


def _sink_report(series_id: str, room: str, solo: str, duo_a: str, duo_b: str,
                 *, solo_won: bool = True):
    """A 1v2 report as the client builds it, SIGNED over the seats as given.

    Signed over THAT order, so a report whose duo pair arrives reversed passes
    the real signature check exactly as a report built in that order would.
    That is what makes the canonical form's place (after the check, never
    before it) a tested property rather than a sentence.
    """
    import hashlib
    import hmac
    import schemas
    sr, dr, ws = (4, 2, 1) if solo_won else (2, 4, 2)
    reporter = min(solo, duo_a, duo_b)

    def seat(s):
        return schemas.PlayerMatchData(
            steam_id=s, display_name="t391", end_stats=SINK_END_STATS[s],
            cards=[schemas.CardPick(card_name=SINK_CARD[s], pick_order=1,
                                    round_number=1)])

    signed = (f"{solo}:{duo_a}:{duo_b}:{sr}:{dr}:false:{reporter}:"
              f"{room}:{ws}:{series_id}")
    return schemas.OvtMatchReport(
        series_id=series_id, solo=seat(solo), duo_a=seat(duo_a),
        duo_b=seat(duo_b), solo_rounds_won=sr, duo_rounds_won=dr,
        winner_side=ws, photon_room_id=room, reported_by_steam_id=reporter,
        solo_fps=SINK_FPS[solo], duo_a_fps=SINK_FPS[duo_a],
        duo_b_fps=SINK_FPS[duo_b],
        solo_damage_timeline=SINK_TIMELINE[solo],
        duo_a_damage_timeline=SINK_TIMELINE[duo_a],
        duo_b_damage_timeline=SINK_TIMELINE[duo_b],
        hmac_signature=hmac.new(SINK_HMAC.encode(), signed.encode(),
                                hashlib.sha256).hexdigest())


def _sink_patch(monkeypatch):
    """The sink's three collaborators that are not what these cases judge.

    The session check is the ROUTE's authentication and needs a request; the
    podium is a 60-second cache over a leaderboard query; the signing key is
    a test key, so the REAL signature check runs on every report. Nothing
    that records, pays, compares or locks is replaced.
    """
    async def _no_session(request, steam_id, db):
        return None

    async def _no_podium(db):
        return []

    monkeypatch.setattr(main, "_check_steam_session", _no_session)
    monkeypatch.setattr(main, "_ovt_podium_ids", _no_podium)
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SINK_HMAC)


async def _submit(factory, report):
    """One report through the REAL handler, in a session of its own."""
    async with factory() as db:
        return await main.submit_ovt_match(report, None, db)


async def _ledger(engine) -> dict:
    """Everything a report can record or pay, as one comparable value."""
    queries = {
        "matches": "SELECT id, series_id, photon_room_id, solo_id, duo_a_id,"
                   " duo_b_id FROM ovt_matches",
        "cards": "SELECT match_id, player_id, card_name FROM ovt_match_cards",
        "players": "SELECT id, total_xp, gold_earned FROM players",
        "gold": "SELECT player_id, amount, reason, reference_id"
                " FROM gold_transactions",
        "series": "SELECT id, status, solo_series_wins, duo_series_wins,"
                  " solo_id, duo_a_id, duo_b_id, solo_xp_earned,"
                  " duo_a_xp_earned, duo_b_xp_earned, solo_gold_earned,"
                  " duo_a_gold_earned, duo_b_gold_earned FROM ovt_series",
    }
    out = {}
    async with engine.connect() as conn:
        for key, q in queries.items():
            out[key] = sorted(tuple(str(v) for v in r)
                              for r in (await conn.execute(text(q))).all())
    return out


async def _lock_waiters(engine, want: int, tasks, limit: float = 10.0) -> int:
    """Poll until `want` backends on this database wait on a lock; returns
    the count last seen.

    Stops early, returning what it saw, once any task has FINISHED: a report
    that finished did not wait, and that is the outcome the calling case
    exists to catch. Each poll ends its transaction, because
    pg_stat_activity is a snapshot taken once per transaction.
    """
    deadline = time.monotonic() + limit
    seen = 0
    async with engine.connect() as mon:
        while time.monotonic() < deadline and not any(t.done() for t in tasks):
            seen = (await mon.execute(text(
                "SELECT count(*) FROM pg_stat_activity"
                " WHERE datname = current_database()"
                "   AND wait_event_type = 'Lock'"))).scalar()
            await mon.rollback()
            if seen >= want:
                break
            await asyncio.sleep(0.05)
    return seen


# A duo seat by name: duo_a / duo_b as a word or a prefix (duo_a_id,
# series['duo_b_id'], report.duo_a.steam_id), and the handler's stored-slot
# names. Not duo_avg_r, duo_wins or duo_rounds_won, which name no seat.
_DUO_SLOT = re.compile(r"(?<![A-Za-z0-9])(?:duo_[ab]|slot_d[ab])(?![A-Za-z0-9])")


def _slot_pair_comparisons(fn) -> list:
    """Every comparison in `fn` (nested defs included) that reads the duo
    pair, as (kind, source); the kind is what decides whether the result can
    depend on the order the pair arrives in.

    Two families. A Python comparison whose source names a duo seat. A WHERE
    predicate in one of the function's SQL statements that names a duo column
    or binds a parameter whose value names a duo seat, split on AND/OR so each
    predicate counts once. The database's own comparison of the pair, the
    ordered UNIQUE the INSERT relies on, lives in no function; the census case
    pins it separately.
    """
    found = []
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Compare)
                and _DUO_SLOT.search(ast.unparse(node))):
            continue
        operands = [node.left, *node.comparators]
        if all(isinstance(o, ast.Set) for o in operands):
            kind = "set"
        elif all(isinstance(o, ast.Tuple) for o in operands):
            kind = "ordered"
        elif all(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
            kind = "membership"
        else:
            kind = "scalar"
        found.append((kind, " ".join(ast.unparse(node).split())))
    for call in ast.walk(fn):
        if not (isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "execute" and call.args
                and isinstance(call.args[0], ast.Call)
                and isinstance(call.args[0].func, ast.Name)
                and call.args[0].func.id == "text" and call.args[0].args):
            continue
        lit = call.args[0].args[0]
        sql = lit.value if isinstance(lit, ast.Constant) else ast.unparse(lit)
        bound = set()
        if len(call.args) > 1 and isinstance(call.args[1], ast.Dict):
            bound = {k.value for k, v in zip(call.args[1].keys,
                                             call.args[1].values)
                     if isinstance(k, ast.Constant)
                     and _DUO_SLOT.search(ast.unparse(v))}
        for where in re.findall(
                r"\bWHERE\b(.*?)(?=\bORDER\s+BY\b|\bGROUP\s+BY\b|\bLIMIT\b"
                r"|\bRETURNING\b|\bFOR\s+(?:NO\s+KEY\s+)?UPDATE\b|\Z)",
                sql, re.S | re.I):
            for pred in re.split(r"\bAND\b|\bOR\b", where, flags=re.I):
                if not (_DUO_SLOT.search(pred) or any(
                        re.search(r"(?<!:):" + re.escape(k) + r"\b", pred)
                        for k in bound)):
                    continue
                if "@>" in pred or "<@" in pred:
                    kind = "containment"
                elif re.search(r"\bIN\s*\(", pred, re.I):
                    kind = "in-list"
                else:
                    kind = "sql-compare"
                found.append((kind, " ".join(pred.split())))
    return found


def test_the_duo_pair_is_put_in_one_order_and_every_seat_field_travels_with_it():
    """H1 (a): one canonical order for the duo pair, and nothing left behind.

    The seat-keyed fields are DERIVED from the report model rather than listed
    here, so a duo_a_* field added to the model later has to travel with its
    player too, or this reds. The order is ordinal on the Steam id string, the
    client's own sort (StringComparer.Ordinal), so the case pins it with two
    ids whose ordinal and numeric orders disagree.
    """
    import schemas
    fields = set(schemas.OvtMatchReport.model_fields)
    seat_a = sorted(f for f in fields if f.startswith("duo_a"))
    seat_b = sorted(f for f in fields if f.startswith("duo_b"))
    assert [f.replace("duo_a", "duo_b", 1) for f in seat_a] == seat_b, (
        seat_a, seat_b)
    # A check over an empty set passes forever (#342).
    assert {"duo_a", "duo_a_fps", "duo_a_damage_timeline"} <= set(seat_a), seat_a

    lo, hi = SIDS[1], SIDS[2]
    arrived = _sink_report(str(uuid.uuid4()), _game_room(1), SIDS[0], hi, lo)
    canon = main._ovt_canonical_duo(arrived)
    assert (canon.duo_a.steam_id, canon.duo_b.steam_id) == (lo, hi)
    for fa, fb in zip(seat_a, seat_b):
        assert getattr(canon, fa) == getattr(arrived, fb), fa
        assert getattr(canon, fb) == getattr(arrived, fa), fb
    for f in sorted(fields - set(seat_a) - set(seat_b)):
        assert getattr(canon, f) == getattr(arrived, f), f
    # A copy: the report as it arrived keeps its order...
    assert (arrived.duo_a.steam_id, arrived.duo_b.steam_id) == (hi, lo)
    # ...and a report already in order comes back as the SAME object.
    assert main._ovt_canonical_duo(canon) is canon

    # Ordinal, not numeric: "95..." sorts after "900..." as strings.
    short, longer = "9500000000000391", "90000000000003912"
    assert int(short) < int(longer) and longer < short
    mixed = arrived.model_copy(update={
        "duo_a": arrived.duo_a.model_copy(update={"steam_id": short}),
        "duo_b": arrived.duo_b.model_copy(update={"steam_id": longer})})
    assert main._ovt_canonical_duo(mixed).duo_a.steam_id == longer


def test_the_report_is_canonicalised_before_any_slot_comparison_or_write():
    """H1 (a): the canonical form runs BEFORE any comparison and any write,
    and AFTER the signature check.

    In the handler's straight-line body: exactly one
    `report = _ovt_canonical_duo(report)`, after `_verify_ovt_hmac(report)`
    (the signature covers the order the client sent, so canonicalising first
    would refuse every report whose pair arrives reversed) and before every
    statement that reads a duo seat or runs a database statement; nothing
    rebinds `report` after it. Then the order the answer rests on: the series
    row lock, the room lock, the replay check, the INSERT.
    """
    fn = _fn_named("submit_ovt_match")
    body = _straightline(fn.body)
    src = [ast.unparse(st) for st in body]

    def is_canonical(st) -> bool:
        if not (isinstance(st, ast.Assign) and len(st.targets) == 1
                and isinstance(st.targets[0], ast.Name)
                and st.targets[0].id == "report"
                and isinstance(st.value, ast.Call)
                and isinstance(st.value.func, ast.Name)
                and st.value.func.id == "_ovt_canonical_duo"):
            return False
        given = list(st.value.args) + [k.value for k in st.value.keywords]
        return [ast.unparse(a) for a in given] == ["report"]

    at = [i for i, st in enumerate(body) if is_canonical(st)]
    assert len(at) == 1, src[:8]
    c = at[0]
    signed = [i for i, s in enumerate(src) if "_verify_ovt_hmac(report)" in s]
    assert signed and max(signed) < c, (signed, c)
    for s in src[:c]:
        assert not _DUO_SLOT.search(s), s
        assert "db.execute" not in s and "db.add" not in s, s
    rebinds = [n for n in ast.walk(fn)
               if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign))
               and any(isinstance(t, ast.Name) and t.id == "report"
                       for t in (n.targets if isinstance(n, ast.Assign)
                                 else [n.target]))]
    assert len(rebinds) == 1, [ast.unparse(n) for n in rebinds]

    def first(needle: str) -> int:
        hits = [i for i, s in enumerate(src) if needle in s]
        assert hits, needle
        return hits[0]

    order = [first("FOR NO KEY UPDATE"), first("pg_advisory_xact_lock"),
             first("CAST(:trio AS uuid[])"), first("INSERT INTO ovt_matches")]
    assert c < order[0] and order == sorted(set(order)), (c, order)
    lock = src[order[1]]
    assert "OVT_REPORT_ROOM_LOCK_CLASS" in lock and "photon_room_id" in lock, lock


def test_every_slot_pair_comparison_in_the_report_and_void_paths_is_accounted_for():
    """Sibling sweep of the HIGH (#432): the defect is a CLASS, so the census
    is asserted, not sampled.

    Every comparison that reads the duo pair in the report path and the void
    path, counted per function and classified by the one property that
    matters here, whether its result can depend on which duo seat a player
    arrives in:
      set, membership, containment, in-list: order-free by construction;
      ordered, scalar: order-dependent, so each must run on the canonical
        form (the dominance case above asserts that for the handler; the
        canonical form's own comparison is what defines it).
    A comparison added, removed, or turned from one kind into another reds
    here and has to be classified by hand; the notes' sweep table (section
    10) is this table. The database's own comparison of the pair, the ordered
    UNIQUE, is pinned too: exactly one UNIQUE over ovt_matches across the
    migrations, in that column order.
    """
    from collections import Counter
    census = {
        "submit_ovt_match": {"set": 1, "ordered": 1, "scalar": 1,
                             "containment": 2, "in-list": 1},
        "_ovt_canonical_duo": {"scalar": 1},
        "_ovt_award_seats": {"membership": 2},
        "_ovt_horizon_candidates": {},
        "_ovt_settle_horizon_row": {},
        "_ovt_horizon_ranked_backlog": {},
        "_ovt_horizon_stamped_backlog": {},
        "_ovt_horizon_sweep_tick": {},
        "_ovt_horizon_sweep_tick_bounded": {},
    }
    got = {name: dict(Counter(k for k, _ in
                              _slot_pair_comparisons(_fn_named(name))))
           for name in census}
    assert got == census, got
    assert sum(sum(kinds.values()) for kinds in got.values()) == 9, got

    schema = SCHEMA_120.read_text(encoding="utf-8")
    block = re.search(r"^CREATE TABLE IF NOT EXISTS ovt_matches \(.*?^\);",
                      schema, re.M | re.S)
    assert block, "the 1v2 schema no longer creates ovt_matches"
    uniques = [" ".join(u.split()) for u in re.findall(
        r"\bUNIQUE\s*\(([^)]*)\)", re.sub(r"--[^\n]*", "", block.group(0)))]
    assert uniques == ["photon_room_id, solo_id, duo_a_id, duo_b_id"], uniques
    for path in sorted((REPO_ROOT / "backend" / "sql").glob("*.sql")):
        sql = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))
        for stmt in sql.split(";"):
            if (re.search(r"\bUNIQUE\b", stmt, re.I)
                    and (re.search(r"\bON\s+ovt_matches\b", stmt, re.I)
                         or re.search(r"\bALTER\s+TABLE\s+ovt_matches\b",
                                      stmt, re.I))):
                raise AssertionError(f"{path.name}: another UNIQUE over "
                                     f"ovt_matches: {stmt.strip()[:200]}")


def test_the_seat_award_does_not_depend_on_which_duo_seat_a_player_arrives_in():
    """Sibling sweep, the award's two slot-pair comparisons (#432).

    `_ovt_award_seats` reads the duo pair to ask whether EITHER duo player is
    on the podium (that raises the solo seat's multiplier). Called with the
    same three players and the pair in both orders, with the podium holding
    only the duo_b player of the first order, it must pay every player the
    same; and the podium must actually be read (emptied, it changes the solo
    seat's result), so an equality that held because nothing was read cannot
    pass.
    """
    solo, lo, hi = (uuid.UUID(int=0x3911), uuid.UUID(int=0x3912),
                    uuid.UUID(int=0x3913))

    async def award(pid, won, mult):
        return round(1000 * mult) + (1 if won else 0), 0

    def pay(a, b, podium):
        return _run(main._ovt_award_seats(
            award, solo_id=solo, duo_a_id=a, duo_b_id=b, winner_side=2,
            extra_pick=False, solo_r=1500.0, duo_avg_r=1500.0, podium=podium))

    forward = pay(lo, hi, {str(hi)})
    reverse = pay(hi, lo, {str(hi)})
    assert forward == reverse, (forward, reverse)
    unread = pay(lo, hi, set())
    assert unread[0][solo] != forward[0][solo], (unread, forward)


@live
def test_a_reversed_pair_replay_after_a_void_is_recorded_and_paid_once(monkeypatch):
    """THE round-2 HIGH, executed (B9, B14; brief H1).

    After the horizon sweep voids a series, a late report of one of its games
    is recorded and paid on the settled-without-play arm: the round-2 fix,
    which must stay. The SAME game reported again, same room, with its duo
    pair in the other order (an order the sink accepts) must be answered
    "Already recorded" and change nothing at all: one match row, one XP award
    and one gold delta per player for that game. Both directions run: the
    canonical order first, and the reversed order first.
    """
    _sink_patch(monkeypatch)
    lo, hi = SIDS[1], SIDS[2]

    async def go():
        engine = _engine()
        try:
            await _reset(engine, _sink_schema())
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                ids = await _sink_ids(conn)
                first = await _sink_series(conn, (SIDS[0], lo, hi),
                                           age_days=20)
                second = await _sink_series(conn, (SIDS[0], lo, hi),
                                            room=SINK_ROOM_B, age_days=20)
            assert await _sweep(Session) == 2
            for sid in (first, second):
                row = await _row(engine, sid)
                assert (row["status"], row["invalidation_reason"]) == (
                    "canceled", VOID_REASON), row
            games = ((first, _game_room(391), (lo, hi)),
                     (second, _game_room(392, SINK_ROOM_B), (hi, lo)))
            for sid, room, pair in games:
                paid = await _submit(Session, _sink_report(
                    sid, room, SIDS[0], *pair))
                assert paid.message == "Series already resolved", paid
                assert paid.xp_gained > 0 and paid.gold_gained > 0, paid
                before = await _ledger(engine)
                again = await _submit(Session, _sink_report(
                    sid, room, SIDS[0], *pair[::-1]))
                assert again.message == "Already recorded", again
                assert (again.xp_gained, again.gold_gained) == (0, 0), again
                assert await _ledger(engine) == before, room
            async with engine.connect() as conn:
                rows = (await conn.execute(text(
                    "SELECT id, photon_room_id FROM ovt_matches"))).all()
                assert sorted(r.photon_room_id for r in rows) == sorted(
                    g[1] for g in games), rows
                for r in rows:
                    got = (await conn.execute(text(
                        "SELECT player_id FROM gold_transactions"
                        " WHERE reference_id = :m AND reason = 'ovt_xp'"),
                        {"m": str(r.id)})).scalars().all()
                    assert sorted(map(str, got)) == sorted(
                        map(str, ids.values())), got
                series = (await conn.execute(text(
                    "SELECT * FROM ovt_series"))).mappings().all()
                balances = {p.id: (p.total_xp, p.gold_earned)
                            for p in (await conn.execute(text(
                                "SELECT id, total_xp, gold_earned"
                                " FROM players"))).all()}
            # Each balance is exactly what the two series' own ledgers say
            # they paid, and neither tally moved: settled means final.
            for pid, balance in balances.items():
                owed = [(s[f"{seat}_xp_earned"], s[f"{seat}_gold_earned"])
                        for s in series for seat in ("solo", "duo_a", "duo_b")
                        if s[f"{seat}_id"] == pid]
                assert len(owed) == 2, (pid, owed)
                assert balance == tuple(map(sum, zip(*owed))), (pid, owed)
            for s in series:
                assert (s["solo_series_wins"], s["duo_series_wins"],
                        s["status"]) == (0, 0, "canceled"), dict(s)
        finally:
            await engine.dispose()
    _run(go())


@live
def test_a_report_arriving_with_its_pair_reversed_is_recorded_in_canonical_order(
        monkeypatch, capsys):
    """The canonical form, end to end (the sweep's canonical-form rows).

    Game 1 arrives with its duo pair reversed, against a series row whose
    queue-time order is ALSO the reversed one. It is stored with the pair in
    canonical order, the lower Steam id in duo_a, and every seat-keyed value
    (fps, damage timeline, end stats, card pick, rating snapshot) beside its
    own player; the game-1 realignment writes the same order into the series
    row. Game 2 then arrives in canonical order and meets that order: no drift
    warning, and every seat's per-series totals equal what its player was
    actually paid.
    """
    _sink_patch(monkeypatch)
    lo, hi = SIDS[1], SIDS[2]

    async def go():
        engine = _engine()
        try:
            await _reset(engine, _sink_schema())
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                ids = await _sink_ids(conn)
                for s in SIDS:
                    await conn.execute(text(
                        "INSERT INTO glicko_ratings (player_id, rating)"
                        " VALUES (:p, :r)"), {"p": ids[s], "r": SINK_RATING[s]})
                sid = await _sink_series(conn, (SIDS[0], hi, lo))
            one = await _submit(Session, _sink_report(
                sid, _game_room(391), SIDS[0], hi, lo))
            assert one.message == "1v2 match recorded", one
            async with engine.connect() as conn:
                m = (await conn.execute(text(
                    "SELECT * FROM ovt_matches WHERE photon_room_id = :r"),
                    {"r": _game_room(391)})).mappings().one()
                cards = dict((await conn.execute(text(
                    "SELECT player_id, card_name FROM ovt_match_cards"
                    " WHERE match_id = :m"), {"m": m["id"]})).all())
            for seat, s in (("solo", SIDS[0]), ("duo_a", lo), ("duo_b", hi)):
                assert m[f"{seat}_id"] == ids[s], (seat, dict(m))
                assert m[f"{seat}_fps_avg"] == SINK_FPS[s], (seat, dict(m))
                assert m[f"{seat}_damage_timeline"] == SINK_TIMELINE[s], seat
                assert m[f"{seat}_end_stats"] == SINK_END_STATS[s], seat
                assert m[f"{seat}_rating_at"] == SINK_RATING[s], seat
            assert cards == {ids[s]: SINK_CARD[s] for s in SIDS}, cards
            row = await _row(engine, sid)
            assert (row["solo_id"], row["duo_a_id"], row["duo_b_id"]) == (
                ids[SIDS[0]], ids[lo], ids[hi]), row

            two = await _submit(Session, _sink_report(
                sid, _game_room(392), SIDS[0], lo, hi, solo_won=False))
            assert two.message == "1v2 match recorded", two
            row = await _row(engine, sid)
            assert (row["solo_series_wins"], row["duo_series_wins"],
                    row["status"]) == (1, 1, "active"), row
            async with engine.connect() as conn:
                paid = {p.id: (p.total_xp, p.gold_earned)
                        for p in (await conn.execute(text(
                            "SELECT id, total_xp, gold_earned"
                            " FROM players"))).all()}
            for seat in ("solo", "duo_a", "duo_b"):
                assert (row[f"{seat}_xp_earned"],
                        row[f"{seat}_gold_earned"]) == paid[row[f"{seat}_id"]], seat
        finally:
            await engine.dispose()
    _run(go())
    out = capsys.readouterr().out
    assert out.count("slots realigned to report ordering") == 1, out
    assert "slot ordering differs" not in out, out


@live
def test_a_room_on_record_in_any_seat_order_is_answered_as_already_recorded(
        monkeypatch, capsys):
    """The replay check is a SET, so it holds the orders no key order can.

    Two members of the class the ordered key alone cannot hold, whatever
    order the duo pair is given: (1) a second report of a recorded game with
    ANOTHER of its three players in the solo seat, where the key's solo
    column differs; (2) a room recorded before this round with its duo pair in
    the other order, reported again in canonical order. Each is answered
    exactly as a key conflict is ("Already recorded") and neither writes or
    pays anything. (1) is also named in the log, once.
    """
    _sink_patch(monkeypatch)
    lo, hi = SIDS[1], SIDS[2]

    async def go():
        engine = _engine()
        try:
            await _reset(engine, _sink_schema())
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                ids = await _sink_ids(conn)
                sid = await _sink_series(conn, (SIDS[0], lo, hi))
            room = _game_room(393)
            first = await _submit(Session, _sink_report(
                sid, room, SIDS[0], lo, hi))
            assert first.message == "1v2 match recorded", first
            before = await _ledger(engine)
            relabelled = await _submit(Session, _sink_report(
                sid, room, lo, SIDS[0], hi, solo_won=False))
            assert relabelled.message == "Already recorded", relabelled
            assert await _ledger(engine) == before

            legacy = _game_room(394)
            async with engine.begin() as conn:
                await conn.execute(text("""
                    INSERT INTO ovt_matches (id, series_id, solo_id, duo_a_id,
                        duo_b_id, solo_rounds_won, duo_rounds_won, winner_side,
                        photon_room_id)
                    VALUES (:id, CAST(:sid AS uuid), :s, :a, :b, 2, 4, 2, :room)
                """), {"id": uuid.uuid4(), "sid": sid, "s": ids[SIDS[0]],
                       "a": ids[hi], "b": ids[lo], "room": legacy})
            before = await _ledger(engine)
            replay = await _submit(Session, _sink_report(
                sid, legacy, SIDS[0], lo, hi, solo_won=False))
            assert replay.message == "Already recorded", replay
            assert await _ledger(engine) == before
        finally:
            await engine.dispose()
    _run(go())
    out = capsys.readouterr().out
    assert out.count("with a different solo seat") == 1, out


@live
def test_the_key_conflicts_on_either_order_of_the_duo_pair():
    """The database-level guarantee (B9's second control; brief H1 (a), (c)).

    Two inserts of ONE game in overlapping transactions, one built from each
    order of the duo pair. After the sink's canonical form both carry the
    same (room, solo, duo_a, duo_b), so the second WAITS on the first's
    uncommitted key entry and fails with a unique violation when the first
    commits: one row. The statement is the handler's own INSERT, read out of
    submit_ovt_match, on the table the production migration builds, and that
    table's only UNIQUE is asserted to be the ordered key this rests on.
    """
    from sqlalchemy.exc import IntegrityError
    insert = _only(_sql_literals(main.submit_ovt_match), "INSERT INTO ovt_matches")
    names = set(re.findall(r"(?<!:):(\w+)", insert))
    lo, hi = SIDS[1], SIDS[2]

    async def go():
        engine = _engine()
        try:
            await _reset(engine, _sink_schema())
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                ids = await _sink_ids(conn)
                sid = await _sink_series(conn, (SIDS[0], lo, hi))
                keys = (await conn.execute(text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                    " WHERE conrelid = CAST('ovt_matches' AS regclass)"
                    "   AND contype = 'u'"))).scalars().all()
            assert keys == [
                "UNIQUE (photon_room_id, solo_id, duo_a_id, duo_b_id)"], keys
            room = _game_room(395)

            def params(pair):
                rep = main._ovt_canonical_duo(
                    _sink_report(sid, room, SIDS[0], *pair))
                p = dict.fromkeys(names)
                p.update(id=uuid.uuid4(), sid=uuid.UUID(sid), room=room,
                         solo=ids[rep.solo.steam_id],
                         da=ids[rep.duo_a.steam_id], db=ids[rep.duo_b.steam_id],
                         sr=rep.solo_rounds_won, dr=rep.duo_rounds_won,
                         sp=0, dp=0, ws=rep.winner_side)
                return p

            a, b = Session(), Session()
            try:
                await a.execute(text(insert), params((lo, hi)))
                late = asyncio.ensure_future(
                    b.execute(text(insert), params((hi, lo))))
                waited = await _lock_waiters(engine, 1, [late])
                assert waited >= 1 and not late.done(), (
                    "the reversed pair did not meet the first insert's key "
                    "entry")
                await a.commit()
                with pytest.raises(IntegrityError):
                    await asyncio.wait_for(late, timeout=10)
            finally:
                await _shut(a)
                await _shut(b)
            async with engine.connect() as conn:
                n = (await conn.execute(text(
                    "SELECT count(*) FROM ovt_matches"
                    " WHERE photon_room_id = :r"), {"r": room})).scalar()
            assert n == 1, n
        finally:
            await engine.dispose()
    _run(go())


@live
def test_a_report_that_reaches_the_insert_anyway_is_answered_as_already_recorded(
        monkeypatch):
    """Brief H1 (c): the key-conflict arm, through the handler.

    A row for this game is being inserted by another transaction and is not
    committed, so the replay check cannot see it. The sink's report of the
    SAME game with the duo pair reversed therefore reaches its INSERT, whose
    canonical key is the other row's, waits on that key entry, and when the
    other transaction commits it gets the conflict, which it answers exactly
    as the replay check does: "Already recorded", no second row, no XP, no
    gold.
    """
    _sink_patch(monkeypatch)
    insert = _only(_sql_literals(main.submit_ovt_match), "INSERT INTO ovt_matches")
    names = set(re.findall(r"(?<!:):(\w+)", insert))
    lo, hi = SIDS[1], SIDS[2]

    async def go():
        engine = _engine()
        try:
            await _reset(engine, _sink_schema())
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                ids = await _sink_ids(conn)
                sid = await _sink_series(conn, (SIDS[0], lo, hi))
            room = _game_room(396)
            p = dict.fromkeys(names)
            p.update(id=uuid.uuid4(), sid=uuid.UUID(sid), room=room,
                     solo=ids[SIDS[0]], da=ids[lo], db=ids[hi],
                     sr=4, dr=2, sp=0, dp=0, ws=1)
            other = Session()
            try:
                await other.execute(text(insert), p)
                before = await _ledger(engine)
                report = asyncio.ensure_future(_submit(Session, _sink_report(
                    sid, room, SIDS[0], hi, lo)))
                waited = await _lock_waiters(engine, 1, [report])
                assert waited >= 1 and not report.done(), (
                    "the reversed report did not reach the other row's key "
                    "entry")
                await other.commit()
                answer = await asyncio.wait_for(report, timeout=10)
            finally:
                await _shut(other)
            assert answer.message == "Already recorded", answer
            assert (answer.xp_gained, answer.gold_gained) == (0, 0), answer
            after = await _ledger(engine)
            assert [m for m in after["matches"] if m[2] == room] == [(
                str(p["id"]), sid, room, str(ids[SIDS[0]]), str(ids[lo]),
                str(ids[hi]))], after["matches"]
            for key in ("cards", "players", "gold", "series"):
                assert after[key] == before[key], key
        finally:
            await engine.dispose()
    _run(go())


@live
def test_two_reports_of_one_room_under_two_series_take_turns_on_the_room_lock(
        monkeypatch):
    """The room lock (brief H1 (b)), in the race it must not lose.

    One room's reports can arrive under two series ids (a continuation series
    keeps the sitting's room), and neither series row lock serialises them.
    Here the first report, under the voided series, is held mid-award by a
    lock on a player row, with its match row inserted and uncommitted; the
    second, under the continuation and naming ANOTHER solo so that no key
    order can make the two conflict, must queue on the ROOM, and once the
    first commits it must find that game on record: one row, the second
    answered "Already recorded", the continuation's tally untouched.
    """
    _sink_patch(monkeypatch)
    lo, hi = SIDS[1], SIDS[2]

    async def go():
        engine = _engine()
        try:
            await _reset(engine, _sink_schema())
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                ids = await _sink_ids(conn)
                voided = await _sink_series(conn, (SIDS[0], lo, hi),
                                            status="canceled")
                cont = await _sink_series(conn, (SIDS[0], lo, hi))
            room = _game_room(397)
            gate = min(ids.values(), key=str)
            holder = Session()
            tasks = []
            try:
                await holder.execute(text(
                    "SELECT 1 FROM players WHERE id = :p FOR NO KEY UPDATE"),
                    {"p": gate})
                tasks.append(asyncio.ensure_future(_submit(
                    Session, _sink_report(voided, room, SIDS[0], lo, hi))))
                assert await _lock_waiters(engine, 1, tasks) >= 1
                tasks.append(asyncio.ensure_future(_submit(
                    Session, _sink_report(cont, room, lo, SIDS[0], hi))))
                assert await _lock_waiters(engine, 2, tasks) >= 2, (
                    "the second report of the room did not queue behind "
                    "the first")
                await holder.rollback()
                first = await asyncio.wait_for(tasks[0], timeout=15)
                second = await asyncio.wait_for(tasks[1], timeout=15)
            finally:
                await _shut(holder)
                for t in tasks:
                    t.cancel()
            assert first.message == "Series already resolved", first
            assert second.message == "Already recorded", second
            async with engine.connect() as conn:
                n = (await conn.execute(text(
                    "SELECT count(*) FROM ovt_matches"
                    " WHERE photon_room_id = :r"), {"r": room})).scalar()
            assert n == 1, n
            row = await _row(engine, cont)
            assert (row["solo_series_wins"], row["duo_series_wins"]) == (
                0, 0), row
        finally:
            await engine.dispose()
    _run(go())


# ═════════════ round 4: one solo-versus-duo split per series ═════════════
#
# Bug 391 round 4 answers the round-3 HIGH by number. A series' first
# recorded game fixes who plays alone: the realignment that adopts a report's
# seats runs only while the series has no game on record, and nothing moves
# the seats after it. A later report from ANOTHER room that put another of
# the three players in the solo seat used to be logged and recorded anyway,
# so the tally, the awards and the pack recipients each read a different
# split. The sink now refuses that report, with the handler's own 403 shape,
# before anything is written. (A room already on record for these three
# players is the replay check's, round 3: it never reaches the refusal.)
#
# A case that completes a series needs the two tables a completion writes
# beside the sink's own: glicko_ratings_1v2 (per-player series counts) and
# ovt_queue (whose rows the completion locks and clears). Both come whole
# from the production 1v2 migration, minus their comments and their foreign
# key to players, which is dropped for the reason SINK_EXTRAS carries none:
# the horizon cases' reset drops players without CASCADE.

SINK_COMPLETION_TABLES = ("glicko_ratings_1v2", "ovt_queue")


def _sink_schema_to_completion() -> str:
    """`_sink_schema()` plus the two tables a series completion writes.

    Their DROPs run first, so a leftover copy of either can never hold
    `players` in place when the sink schema drops it.
    """
    schema = re.sub(r"--[^\n]*", "", SCHEMA_120.read_text(encoding="utf-8"))
    creates = []
    for table in SINK_COMPLETION_TABLES:
        m = re.search(r"^CREATE TABLE IF NOT EXISTS " + table + r" \(.*?^\);",
                      schema, re.M | re.S)
        assert m, f"the 1v2 schema no longer creates {table}"
        block, n = re.subn(
            r"\s+REFERENCES\s+players\(id\)\s+ON\s+DELETE\s+CASCADE", "",
            m.group(0)[:-1])
        # Exactly the one key to players, gone: a count of zero would mean the
        # migration changed and this copy silently kept its key (#342).
        assert n == 1 and "REFERENCES" not in block, (table, n)
        creates.append(block.strip())
    drops = [f"DROP TABLE IF EXISTS {t}" for t in SINK_COMPLETION_TABLES]
    return (";\n".join(drops) + ";\n" + _sink_schema() + "\n"
            + ";\n".join(creates) + ";")


def _record_pack_grants(monkeypatch) -> list:
    """The earned-pack grant, RECORDED rather than run.

    What these cases judge is whether the grant is called and for whom. Its
    own tables are not in this schema, and the handler runs it in a savepoint
    that prints a failure and carries on, which would hide a call rather than
    show one. Everything that records, pays, compares or locks still runs.
    """
    grants = []

    async def _grant(db, **kw):
        grants.append((kw["mode"], str(kw["series_id"]),
                       sorted(str(p) for p in kw["winner_ids"])))
        return []

    monkeypatch.setattr(main, "_pc_grant_earned_packs", _grant)
    return grants


@live
def test_a_report_moving_a_player_into_the_solo_seat_mid_series_is_refused(
        monkeypatch, capsys):
    """THE round-3 HIGH, executed (B9, B14; brief H1).

    Game 1 is recorded with the stored solo winning, 1-0. A report from ANOTHER
    room then puts a duo member in the solo seat and reports another solo win.
    Recorded, it would complete the series 2-0 as the stored solo's win, pay
    the winner's series bonus to the new solo and give the winner's pack to
    the stored one. It must be refused with the handler's own 403 before
    anything is written: the same match rows, cards, tallies, seat ledger,
    balances and gold rows, and no pack grant, named once in the log with both
    splits. The refusal does not block the series: the same room reported with
    the series' own split is then recorded, completes it 2-0, and pays the
    winner's bonus and pack to the stored solo alone.
    """
    _sink_patch(monkeypatch)
    grants = _record_pack_grants(monkeypatch)
    solo, lo, hi = SIDS

    async def go():
        engine = _engine()
        try:
            await _reset(engine, _sink_schema_to_completion())
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                ids = await _sink_ids(conn)
                sid = await _sink_series(conn, (solo, lo, hi))
            one = await _submit(Session, _sink_report(
                sid, _game_room(401), solo, lo, hi))
            assert one.message == "1v2 match recorded", one
            row = await _row(engine, sid)
            assert (row["solo_series_wins"], row["duo_series_wins"],
                    row["status"]) == (1, 0, "active"), row

            before = await _ledger(engine)
            with pytest.raises(main.HTTPException) as refused:
                await _submit(Session, _sink_report(
                    sid, _game_room(402), lo, solo, hi))
            assert refused.value.status_code == 403, refused.value
            assert refused.value.detail == (
                "Reported solo seat does not match the series"), refused.value
            assert await _ledger(engine) == before
            assert grants == [], grants

            two = await _submit(Session, _sink_report(
                sid, _game_room(402), solo, lo, hi))
            assert two.series_status == "completed", two
            row = await _row(engine, sid)
            assert (row["solo_series_wins"], row["duo_series_wins"],
                    row["status"], row["winner_side"]) == (
                2, 0, "completed", 1), row
            assert grants == [("ovt", sid, [str(ids[solo])])], grants
            async with engine.connect() as conn:
                bonus = (await conn.execute(text(
                    "SELECT reason, player_id FROM gold_transactions"
                    " WHERE reference_id = :s"), {"s": sid})).all()
            assert sorted((r.reason, str(r.player_id)) for r in bonus) == sorted(
                [("ovt_series_win", str(ids[solo])),
                 ("ovt_series_loss", str(ids[lo])),
                 ("ovt_series_loss", str(ids[hi]))]), bonus
            return ids
        finally:
            await engine.dispose()
    ids = _run(go())
    out = capsys.readouterr().out
    refusals = [ln for ln in out.splitlines()
                if "report refused, nothing written" in ln]
    assert len(refusals) == 1, out
    assert f"it names solo {ids[lo]} with duo " in refusals[0], refusals
    assert f"the series holds solo {ids[solo]} with duo " in refusals[0], refusals
    assert "leaving as-is" not in out, out


@live
def test_a_settled_series_refuses_a_report_moving_the_solo_seat_too(
        monkeypatch, capsys):
    """The same refusal on the other arm that pays a game (#432: the class).

    A series settled without play still records and pays each late game (the
    round-2 fix). Once it holds a recorded game, a report from another room
    naming another solo would be paid there under a split the series never
    had. The refusal sits before the status branch, so it holds on this arm
    too: 403, nothing written, no pack grant. The series' own split from the
    same room is then recorded and paid as a late game, the tally untouched.
    """
    _sink_patch(monkeypatch)
    grants = _record_pack_grants(monkeypatch)
    solo, lo, hi = SIDS

    async def go():
        engine = _engine()
        try:
            await _reset(engine, _sink_schema_to_completion())
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                sid = await _sink_series(conn, (solo, lo, hi),
                                         status="canceled")
            one = await _submit(Session, _sink_report(
                sid, _game_room(403), solo, lo, hi))
            assert one.message == "Series already resolved", one
            assert one.xp_gained > 0 and one.gold_gained > 0, one

            before = await _ledger(engine)
            with pytest.raises(main.HTTPException) as refused:
                await _submit(Session, _sink_report(
                    sid, _game_room(404), hi, solo, lo, solo_won=False))
            assert refused.value.status_code == 403, refused.value
            assert refused.value.detail == (
                "Reported solo seat does not match the series"), refused.value
            assert await _ledger(engine) == before

            two = await _submit(Session, _sink_report(
                sid, _game_room(404), solo, lo, hi, solo_won=False))
            assert two.message == "Series already resolved", two
            assert two.xp_gained > 0, two
            row = await _row(engine, sid)
            assert (row["solo_series_wins"], row["duo_series_wins"],
                    row["status"]) == (0, 0, "canceled"), row
            assert grants == [], grants
        finally:
            await engine.dispose()
    _run(go())
    out = capsys.readouterr().out
    assert sum("report refused, nothing written" in ln
               for ln in out.splitlines()) == 1, out
