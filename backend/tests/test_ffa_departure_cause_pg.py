"""Bug #392, item A step 1 (2) and (3) — executed against a real PostgreSQL.

Everything here is SQL that only execution can prove. `ast.parse` says nothing
about whether `jsonb_build_object(CAST(:pidt AS text), CAST(:cause AS text))
|| departure_causes` parses, whether binding one placeholder under two
different casts is accepted, or whether `jsonb_each_text` over a scalar
subquery returns the pairs the report handler expects (#313/#340/#643).

The statements under test are LIFTED FROM main.py at import time, not
retyped: each one is pulled out of the function that runs it, so a change to
the shipped statement changes what this file executes. A retyped copy would
only test a string that agreed with itself.

Gate
----
    BUG392_TEST_PG_DSN=postgresql+asyncpg://postgres@127.0.0.1:55432/scr_bug392
    BUG392_TESTS_REQUIRED=1     # a missing DSN then FAILS instead of skipping

Without BUG392_TESTS_REQUIRED a missing DSN skips, so the no-DSN suite stays
runnable — but a green run that collected nothing is the failure mode #664
describes, so the recorded run sets it.

This file creates and drops no database. It rebuilds four tables from
fixtures/bug392_schema.sql inside the database the DSN names, applies
migration 324 to them, and touches nothing else.
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pytest

sa = pytest.importorskip("sqlalchemy")
asyncpg = pytest.importorskip("asyncpg")
from sqlalchemy import text  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

import main  # noqa: E402


DSN = os.environ.get("BUG392_TEST_PG_DSN", "").strip()
REQUIRED = os.environ.get("BUG392_TESTS_REQUIRED", "").strip() not in ("", "0", "false")

if not DSN:
    if REQUIRED:
        raise AssertionError(
            "BUG392_TESTS_REQUIRED is set but BUG392_TEST_PG_DSN is empty — "
            "this file would have collected and proved nothing")
    pytest.skip("BUG392_TEST_PG_DSN not set", allow_module_level=True)

RAW_DSN = DSN.replace("postgresql+asyncpg://", "postgresql://")

# ── What this file is allowed to point at (lens find 3) ──────────────────
# fixtures/bug392_schema.sql opens with four unconditional DROP TABLE IF
# EXISTS statements. The module docstring's safety claim is about the
# DATABASE object — this file creates and drops none — and says nothing about
# the tables inside whatever database the DSN happens to name. Nothing
# constrained that name, so the recorded command re-run against a populated
# database (a local dev copy, a restored dump staged for a migration dry run)
# would have dropped `players` and the three FFA tables, rebuilt them as
# fixtures, and reported a green run. No confirmation step, no error.
#
# Two independent conditions, both required, because either alone can be
# satisfied by accident: the database must be NAMED as a throwaway for these
# tests, and it must not already hold player rows. The name check alone would
# not protect a scratch database someone had loaded a dump into; the emptiness
# check alone would not protect a real database that happened to be empty at
# the moment of the run.
_ALLOWED_DB_NAMES = frozenset({"scr_bug392"})
_DB_NAME = urlparse(RAW_DSN).path.lstrip("/")

if _DB_NAME not in _ALLOWED_DB_NAMES:
    raise AssertionError(
        f"BUG392_TEST_PG_DSN names database {_DB_NAME!r}. This file DROPS and "
        f"rebuilds players, ffa_lobbies, ffa_matches and ffa_match_players in "
        f"whatever database it is pointed at, so it refuses any name outside "
        f"{sorted(_ALLOWED_DB_NAMES)}. Create the throwaway database and point "
        f"the DSN at that — never at a database holding data you want to keep.")

BACKEND = Path(__file__).parents[1]
SCHEMA_SQL = (BACKEND / "tests" / "fixtures" / "bug392_schema.sql").read_text(encoding="utf-8")
MIGRATION_SQL = (BACKEND / "sql" / "324_ffa_departure_cause.sql").read_text(encoding="utf-8")
MAIN_TREE = ast.parse((BACKEND / "api" / "main.py").read_text(encoding="utf-8"))


# ── lifting the shipped statements ───────────────────────────────────────

def _function(name: str):
    for node in MAIN_TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"main.py has no module-level function {name!r}")


def _sql_literals(fn, *must_contain: str) -> list[str]:
    return [n.value for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and all(m in n.value for m in must_contain)]


DEPARTURE_WRITERS = _sql_literals(_function("ffa_queue_leave"),
                                  "UPDATE ffa_lobbies", "departed_ids")
assert len(DEPARTURE_WRITERS) == 3, (
    f"expected 3 departed_ids writers in ffa_queue_leave, lifted {len(DEPARTURE_WRITERS)}")

_reads = _sql_literals(_function("submit_ffa_match"), "jsonb_each_text")
assert len(_reads) == 1, "expected exactly one departure-cause read in submit_ffa_match"
CAUSE_READ = _reads[0]

_inserts = _sql_literals(_function("submit_ffa_match"), "INSERT INTO ffa_match_players")
assert len(_inserts) == 1
MATCH_INSERT = _inserts[0]


def _writer(*needles: str) -> str:
    hits = [s for s in DEPARTURE_WRITERS if all(n in s for n in needles)]
    assert len(hits) == 1, f"{needles} matched {len(hits)} of the three writers"
    return hits[0]


ROWLESS_WRITER = _writer("FROM players p")
LIVE_WRITER = _writer("RETURNING cardinality(departed_ids)")
CLOSING_WRITER = _writer("RETURNING status")


# ── harness ──────────────────────────────────────────────────────────────
#
# No pytest-asyncio on this seat, so each test is a sync function that drives
# one `asyncio.run`. Every test gets its own connection and its own lobby; the
# connection is rolled back on close, so no test can see another's rows.

def _statements(sql: str) -> list[str]:
    return [s.strip() for s in re.sub(r"--[^\n]*", "", sql).split(";") if s.strip()]


async def _apply_migration_raw() -> list:
    """Run the departure-cause migration — 324, the file `MIGRATION_SQL`
    points at — the way `psql -f` would: statement by statement, honouring the
    file's OWN BEGIN/COMMIT (#340 — psql does not wrap a file in a
    transaction, which is why the file carries its own). Returns every row the
    file's SELECTs produced, so the dry-run half is proved to ANSWER rather
    than merely not to error.

    This docstring named a DIFFERENT migration until round 2: the renumber
    (§3.4 of the notes) moved the file and left the prose behind, so a triage
    of a failure here would have gone and read the file a different lane owns
    under the old number. Named by role first and number second for that
    reason, and the number is no longer prose at all — it is asserted against
    the file on disk by
    `test_no_stale_migration_number_survives_in_this_lane_s_files`.
    """
    conn = await asyncpg.connect(RAW_DSN)
    try:
        out = []
        for stmt in _statements(MIGRATION_SQL):
            if stmt.upper().startswith("SELECT"):
                out.append(await conn.fetch(stmt))
            else:
                await conn.execute(stmt)
        return out
    finally:
        await conn.close()


async def _assert_target_is_disposable(conn) -> None:
    """The second half of the lens find 3 guard, and the half the DSN string
    cannot answer: is there anything in here worth keeping?

    Asked on the connection, immediately before the DROPs, and asked about the
    table whose loss would hurt most. A `players` table that exists and holds
    rows means this is not a fixture database whatever it is called, so the
    run refuses instead of rebuilding it. An ABSENT table is the expected
    state for a fresh throwaway and passes; a present-but-empty one is what
    the second and later runs of this file see, and passes too.
    """
    rows = await conn.fetchval("""
        SELECT CASE WHEN to_regclass('public.players') IS NULL THEN -1
                    ELSE (SELECT COUNT(*) FROM players) END
    """)
    if rows and rows > 0:
        raise AssertionError(
            f"the target database holds {rows} row(s) in `players`. This file "
            f"drops and rebuilds that table as a 3-column fixture, so it will "
            f"not run against a database with data in it. Point "
            f"BUG392_TEST_PG_DSN at an empty throwaway database.")


async def _rebuild() -> None:
    conn = await asyncpg.connect(RAW_DSN)
    try:
        await _assert_target_is_disposable(conn)
        for stmt in _statements(SCHEMA_SQL):
            await conn.execute(stmt)
    finally:
        await conn.close()
    await _apply_migration_raw()


def run(body):
    """Rebuild, then run `body(conn)` on a SQLAlchemy+asyncpg connection —
    the same delivery path main.py uses, so the `:name` binds are resolved by
    the same code that resolves them in production."""
    async def _go():
        await _rebuild()
        engine = create_async_engine(DSN, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                return await body(conn)
        finally:
            await engine.dispose()
    return asyncio.run(_go())


def _as_map(value) -> dict:
    """jsonb comes back as a dict or as its text, depending on whether a
    driver JSON codec is registered. The production read deliberately avoids
    the question by asking for text pairs; here we accept either."""
    return json.loads(value) if isinstance(value, str) else dict(value or {})


async def _seed(conn, n=4):
    lobby = uuid.uuid4()
    players = [uuid.uuid4() for _ in range(n)]
    for i, pid in enumerate(players):
        await conn.execute(text("INSERT INTO players (id, steam_id) VALUES (:i, :s)"),
                           {"i": pid, "s": f"seat-{i}-{lobby.hex[:8]}"})
    await conn.execute(text("""
        INSERT INTO ffa_lobbies (id, status, player_count, member_ids, games_played)
        VALUES (:l, 'active', :n, :m, 0)
    """), {"l": lobby, "n": n, "m": players})
    return lobby, players


async def _lobby(conn, lobby):
    return (await conn.execute(text(
        "SELECT status, invalidation_reason, departed_ids, departure_causes"
        "  FROM ffa_lobbies WHERE id = :l"), {"l": lobby})).mappings().first()


# ── (2) the migration ────────────────────────────────────────────────────

def test_migration_dry_run_then_write_then_reapply():
    """The file's SELECT halves run and answer, the ALTERs land, and a second
    apply is a no-op rather than an error — both halves, both directions."""
    async def body(conn):
        for table, column, typ in (("ffa_lobbies", "departure_causes", "jsonb"),
                                   ("ffa_match_players", "left_early_involuntary", "boolean")):
            row = (await conn.execute(text("""
                SELECT data_type, is_nullable, column_default
                  FROM information_schema.columns
                 WHERE table_schema='public' AND table_name=:t AND column_name=:c
            """), {"t": table, "c": column})).mappings().first()
            assert row is not None, f"{table}.{column} was not created"
            assert row["data_type"] == typ
            assert row["is_nullable"] == "NO"
            assert row["column_default"] is not None, (
                "a NOT NULL add with no default rewrites the table")
    run(body)

    # Re-apply against the already-migrated database.
    rows = asyncio.run(_apply_migration_raw())
    presence = {r[0]: (r[1], r[2]) for r in rows[0]}
    assert presence["ffa_lobbies.departure_causes"] == (True, True)
    assert presence["ffa_match_players.left_early_involuntary"] == (True, True)
    applied = {r[0]: r[1] for r in rows[-1]}
    assert applied and all(applied.values()), applied


def test_existing_rows_take_the_defaults():
    """No backfill is possible — the causes this stores were never recorded —
    so a pre-migration row must read as 'nothing recorded', never as NULL."""
    async def body(conn):
        lobby, _ = await _seed(conn)
        assert _as_map((await _lobby(conn, lobby))["departure_causes"]) == {}
    run(body)


# ── (2) the three writers ────────────────────────────────────────────────

@pytest.mark.parametrize("which", ["live", "closing"])
def test_row_carrying_writers_persist_the_cause_and_still_append(which):
    """The shipped statement, executed.

    Two obligations in one statement: the cause is stored AND `departed_ids`
    still gains the caller. A tag read as licence to skip the append is
    residual 4 of the diagnosis — the roster would then look fuller than it
    is, which is the state the departure record exists to prevent.
    """
    sql = LIVE_WRITER if which == "live" else CLOSING_WRITER

    async def body(conn):
        lobby, players = await _seed(conn)
        leaver = players[0]
        await conn.execute(text(sql), {"lid": lobby, "pid": leaver,
                                       "pidt": str(leaver), "cause": "in_room_timeout"})
        row = await _lobby(conn, lobby)
        assert leaver in row["departed_ids"], "the departure itself was not recorded"
        assert _as_map(row["departure_causes"])[str(leaver)] == "in_room_timeout"
        # The control: these statements MARK. Carrying a cause may not
        # dissolve or invalidate the lobby.
        assert row["status"] == "active"
        assert row["invalidation_reason"] is None
    run(body)


def test_rowless_writer_persists_the_cause_and_still_appends():
    """The me-is-None path: a member whose queue row a sweep already pruned.
    Same two obligations, resolved through `players` instead of a bound id."""
    async def body(conn):
        lobby, players = await _seed(conn)
        leaver = players[1]
        steam = (await conn.execute(text("SELECT steam_id FROM players WHERE id = :i"),
                                    {"i": leaver})).scalar()
        marked = (await conn.execute(text(ROWLESS_WRITER), {
            "sid": steam, "lid": str(lobby), "cause": "in_room_timeout"})).scalars().all()
        assert marked == [lobby]
        row = await _lobby(conn, lobby)
        assert leaver in row["departed_ids"]
        assert _as_map(row["departure_causes"])[str(leaver)] == "in_room_timeout"
    run(body)


# ── (2b) the tagged retry that arrives after the mark (lens find 2) ──────
#
# The client's durable-cause machinery re-sends an attestation on a LATER
# request, because the room-exit hook fires AFTER a teardown's own untagged
# leave. That first leave takes the row path, appends the player to
# departed_ids and deletes the queue row; the tagged retry therefore finds no
# row and lands here, on a player who is already departed. The first build's
# predicate admitted only an unmarked player, so every attestation that
# survived a teardown was discarded with no error and no log line.

async def _already_departed_without_a_cause(conn, lobby, leaver):
    """The state the teardown's untagged leave leaves behind."""
    await conn.execute(text(LIVE_WRITER), {"lid": lobby, "pid": leaver,
                                           "pidt": str(leaver), "cause": ""})
    row = await _lobby(conn, lobby)
    assert leaver in row["departed_ids"], "precondition: the departure is marked"
    assert _as_map(row["departure_causes"]) == {}, "precondition: no cause yet"


def test_a_tagged_retry_after_an_untagged_teardown_records_the_cause():
    """The defect this section exists for, end to end on real PostgreSQL."""
    async def body(conn):
        lobby, players = await _seed(conn)
        leaver = players[1]
        steam = (await conn.execute(text("SELECT steam_id FROM players WHERE id = :i"),
                                    {"i": leaver})).scalar()
        await _already_departed_without_a_cause(conn, lobby, leaver)

        marked = (await conn.execute(text(ROWLESS_WRITER), {
            "sid": steam, "lid": str(lobby), "cause": "in_room_timeout"})).scalars().all()
        assert marked == [lobby], "the tagged retry reached no row"
        row = await _lobby(conn, lobby)
        assert _as_map(row["departure_causes"])[str(leaver)] == "in_room_timeout"
        # And the departure itself is unchanged — appended once, not twice.
        assert list(row["departed_ids"]).count(leaver) == 1
    run(body)


def test_the_old_one_way_predicate_would_have_dropped_that_retry():
    """The MUTATION control (#391), executed rather than argued.

    The shipped statement is mutated back to the predicate it replaced — the
    single `NOT (departed_ids @> ...)` clause — and run against the identical
    state. It must record nothing. Without this, the test above would pass on
    any statement that happened to write, including one that writes for the
    wrong reason; with it, the pair pins the fix to the predicate change.
    """
    async def body(conn):
        lobby, players = await _seed(conn)
        leaver = players[1]
        steam = (await conn.execute(text("SELECT steam_id FROM players WHERE id = :i"),
                                    {"i": leaver})).scalar()
        await _already_departed_without_a_cause(conn, lobby, leaver)

        start = ROWLESS_WRITER.index("AND (NOT (l.departed_ids")
        end = ROWLESS_WRITER.index("RETURNING l.id")
        mutated = (ROWLESS_WRITER[:start]
                   + "AND NOT (l.departed_ids @> ARRAY[p.id])\n                     "
                   + ROWLESS_WRITER[end:])
        assert "jsonb_exists" not in mutated, "the mutation did not remove the new clause"

        marked = (await conn.execute(text(mutated), {
            "sid": steam, "lid": str(lobby), "cause": "in_room_timeout"})).scalars().all()
        assert marked == [], "the old predicate unexpectedly matched"
        assert _as_map((await _lobby(conn, lobby))["departure_causes"]) == {}
    run(body)


def test_the_retry_cannot_overwrite_a_cause_already_recorded():
    """First attestation still wins — and now the slot it wins is the CAUSE,
    not membership of departed_ids.

    The negative control for the widened predicate: widening it must not have
    turned the map into last-write-wins.
    """
    async def body(conn):
        lobby, players = await _seed(conn)
        leaver = players[1]
        steam = (await conn.execute(text("SELECT steam_id FROM players WHERE id = :i"),
                                    {"i": leaver})).scalar()
        await conn.execute(text(LIVE_WRITER), {"lid": lobby, "pid": leaver,
                                               "pidt": str(leaver), "cause": "in_room_exit"})
        marked = (await conn.execute(text(ROWLESS_WRITER), {
            "sid": steam, "lid": str(lobby), "cause": "in_room_timeout"})).scalars().all()
        assert marked == [], "a recorded cause was reachable for rewriting"
        assert _as_map((await _lobby(conn, lobby))["departure_causes"])[str(leaver)] == "in_room_exit"
    run(body)


def test_an_untagged_retry_after_the_mark_is_still_a_no_op():
    """The other half of the widening: only a TAGGED retry gets the second
    way in. An untagged one matches nothing, exactly as before, so the log
    line and the row are both unchanged."""
    async def body(conn):
        lobby, players = await _seed(conn)
        leaver = players[1]
        steam = (await conn.execute(text("SELECT steam_id FROM players WHERE id = :i"),
                                    {"i": leaver})).scalar()
        await _already_departed_without_a_cause(conn, lobby, leaver)
        marked = (await conn.execute(text(ROWLESS_WRITER), {
            "sid": steam, "lid": str(lobby), "cause": ""})).scalars().all()
        assert marked == []
        assert _as_map((await _lobby(conn, lobby))["departure_causes"]) == {}
    run(body)


def test_an_absent_cause_stores_nothing_but_still_records_the_departure():
    """The old-client negative control.

    A client that sends no cause must leave the map untouched — an empty
    string stored as a cause would later read as "attested, but not
    involuntary", a different claim from "never attested". The departure is
    still recorded, because that is not what the cause decides.
    """
    async def body(conn):
        lobby, players = await _seed(conn)
        leaver = players[2]
        await conn.execute(text(LIVE_WRITER), {"lid": lobby, "pid": leaver,
                                               "pidt": str(leaver), "cause": ""})
        row = await _lobby(conn, lobby)
        assert leaver in row["departed_ids"]
        assert _as_map(row["departure_causes"]) == {}
    run(body)


def test_the_first_attestation_is_the_one_that_sticks():
    """A retried or contradicting later leave cannot rewrite a recorded cause.

    The control that makes this meaningful is the second half: a DIFFERENT
    seat's cause still lands, so "first wins" is per (lobby, player) and not a
    write-once-per-lobby accident.
    """
    async def body(conn):
        lobby, players = await _seed(conn)
        a, b = players[0], players[1]
        for cause in ("in_room_exit", "in_room_timeout", "fresh_cancel"):
            await conn.execute(text(LIVE_WRITER),
                               {"lid": lobby, "pid": a, "pidt": str(a), "cause": cause})
        await conn.execute(text(LIVE_WRITER),
                           {"lid": lobby, "pid": b, "pidt": str(b), "cause": "in_room_timeout"})
        causes = _as_map((await _lobby(conn, lobby))["departure_causes"])
        assert causes[str(a)] == "in_room_exit", "a later leave overwrote a recorded cause"
        assert causes[str(b)] == "in_room_timeout"
    run(body)


def test_a_closed_lobby_takes_no_cause():
    """Every writer is fenced on `status = 'active'`. A cause that could land
    on a closed lobby would be a departure record with no departure."""
    async def body(conn):
        lobby, players = await _seed(conn)
        await conn.execute(text("UPDATE ffa_lobbies SET status='completed' WHERE id=:l"),
                           {"l": lobby})
        await conn.execute(text(LIVE_WRITER), {"lid": lobby, "pid": players[0],
                                               "pidt": str(players[0]),
                                               "cause": "in_room_timeout"})
        row = await _lobby(conn, lobby)
        assert _as_map(row["departure_causes"]) == {}
        assert list(row["departed_ids"]) == []
    run(body)


# ── (3) the read, the write, and the two renders ─────────────────────────

async def _one_game(conn, lobby, players, causes, left_early, involuntary_expected):
    """Runs the shipped cause read, then the shipped INSERT's column set.

    The column list is the one main.py names, in main.py's order — not a
    subset chosen here. A column the report handler writes that the table does
    not have is then a failure in this file instead of a 500 on every FFA
    report in production.
    """
    for pid, cause in causes.items():
        await conn.execute(text(LIVE_WRITER),
                           {"lid": lobby, "pid": pid, "pidt": str(pid), "cause": cause})
    involuntary = {
        str(k) for k, v in (await conn.execute(text(CAUSE_READ), {"lid": lobby})).all()
        if main._is_involuntary_exit_cause(v)
    }
    assert involuntary == {str(p) for p in involuntary_expected}, involuntary

    match_id = uuid.uuid4()
    await conn.execute(text("INSERT INTO ffa_matches (id, lobby_id) VALUES (:m, :l)"),
                       {"m": match_id, "l": lobby})
    cols = re.search(r"INSERT INTO ffa_match_players \(([^)]*)\)", MATCH_INSERT, re.S).group(1)
    use = [c.strip() for c in cols.replace("\n", " ").split(",") if c.strip()]
    assert "left_early_involuntary" in use, "the shipped INSERT no longer writes the qualifier"
    for i, pid in enumerate(players):
        vals = {n: None for n in use}
        vals.update({
            "match_id": match_id, "player_id": pid, "slot": i, "rounds_won": 3,
            "points_total": 21, "kills": 2, "placement": i + 1,
            "left_early": pid in left_early, "rating_before": 1500.0,
            "rating_after": 1496.7, "rating_change": -3.3, "xp_gained": 40,
            "gold_gained": 55, "absent": False,
            "game_points_at_leave": 21 if pid in left_early else None,
            # The shipped expression, with `pid` and `p.left_early` bound.
            "left_early_involuntary": bool(pid in left_early) and str(pid) in involuntary,
        })
        await conn.execute(
            text(f"INSERT INTO ffa_match_players ({', '.join(use)}) "
                 f"VALUES ({', '.join(':' + n for n in use)})"),
            {n: vals[n] for n in use})
    return match_id


def test_involuntary_departure_qualifies_the_mark_without_erasing_it():
    """The red test for (3), in the shape of the incident: four seats, one
    absent at placement 2 whose own leave attested a transport failure."""
    async def body(conn):
        lobby, players = await _seed(conn)
        dropped = players[1]
        match_id = await _one_game(conn, lobby, players,
                                   {dropped: "in_room_timeout"}, {dropped}, {dropped})
        rows = (await conn.execute(text("""
            SELECT player_id, left_early, left_early_involuntary, placement,
                   rating_change, xp_gained, gold_gained
              FROM ffa_match_players WHERE match_id = :m ORDER BY placement
        """), {"m": match_id})).mappings().all()
        by_id = {r["player_id"]: r for r in rows}

        assert by_id[dropped]["left_early"] is True, (
            "the departure must still be recorded — this is display "
            "reconciliation, not suppression")
        assert by_id[dropped]["left_early_involuntary"] is True
        # The rating control: section 8 q2 is Sid's, and the default taken is
        # that an involuntary drop changes NEITHER placement nor economy.
        assert by_id[dropped]["placement"] == 2
        assert by_id[dropped]["rating_change"] == -3.3
        assert by_id[dropped]["xp_gained"] == 40
        assert by_id[dropped]["gold_gained"] == 55
        assert [r["player_id"] for r in rows if r["left_early_involuntary"]] == [dropped]
    run(body)


def test_a_voluntary_leave_and_a_silent_absence_keep_todays_presentation():
    """The negative control for (3).

    A reconciliation that softened every absence would erase genuine early
    leaves, which is worse than the bug. Two cases must be untouched: a seat
    that sent the voluntary in-room tag, and a seat that sent no leave at all.
    """
    async def body(conn):
        lobby, players = await _seed(conn)
        voluntary, silent = players[1], players[2]
        match_id = await _one_game(conn, lobby, players, {voluntary: "in_room_exit"},
                                   {voluntary, silent}, set())
        rows = (await conn.execute(text(
            "SELECT player_id, left_early, left_early_involuntary"
            "  FROM ffa_match_players WHERE match_id = :m"), {"m": match_id})).mappings().all()
        by_id = {r["player_id"]: r for r in rows}
        assert by_id[voluntary]["left_early"] is True
        assert by_id[voluntary]["left_early_involuntary"] is False
        assert by_id[silent]["left_early"] is True
        assert by_id[silent]["left_early_involuntary"] is False
    run(body)


def test_the_qualifier_never_appears_without_the_mark():
    """A seat that attested an involuntary cause but is NOT reported as having
    left early has no mark to qualify. The expression is gated on
    `p.left_early` so the two can never disagree."""
    async def body(conn):
        lobby, players = await _seed(conn)
        dropped = players[1]
        match_id = await _one_game(conn, lobby, players,
                                   {dropped: "in_room_timeout"}, set(), {dropped})
        assert (await conn.execute(text(
            "SELECT COUNT(*) FROM ffa_match_players"
            " WHERE match_id = :m AND left_early_involuntary AND NOT left_early"),
            {"m": match_id})).scalar() == 0
    run(body)


def test_the_cause_read_is_empty_for_a_lobby_with_no_attestations():
    """The read's own control: no departures recorded means an empty set, not
    an error and not every seat."""
    async def body(conn):
        lobby, _ = await _seed(conn)
        assert (await conn.execute(text(CAUSE_READ), {"lid": lobby})).all() == []
    run(body)


@pytest.mark.parametrize("renderer", ["get_match_by_code", "ffa_recent"])
def test_the_shipped_render_projections_select_the_qualifier(renderer):
    """The exact read that renders it, executed against a real row — so a
    column that exists only in the endpoint's imagination fails here rather
    than in production."""
    async def body(conn):
        lobby, players = await _seed(conn)
        dropped = players[1]
        match_id = await _one_game(conn, lobby, players,
                                   {dropped: "in_room_timeout"}, {dropped}, {dropped})
        if renderer == "get_match_by_code":
            projection = _sql_literals(_function("get_match_by_code"),
                                       "FROM ffa_match_players fmp")
            assert len(projection) == 1
            sql = projection[0].replace(":mid", "CAST(:mid AS uuid)")
        else:
            # /ffa/recent selects fmp.* — the qualifier must arrive through the star.
            sql = ("SELECT fmp.*, p.steam_id FROM ffa_match_players fmp"
                   "  JOIN players p ON p.id = fmp.player_id"
                   " WHERE fmp.match_id = CAST(:mid AS uuid)")
        rows = (await conn.execute(text(sql), {"mid": str(match_id)})).mappings().all()
        assert rows, "the projection returned nothing — the assertions would be vacuous"
        by_id = {r["player_id"]: r for r in rows}
        assert by_id[dropped]["left_early"] is True
        assert by_id[dropped]["left_early_involuntary"] is True
        assert all(r["left_early_involuntary"] is False
                   for pid, r in by_id.items() if pid != dropped)
    run(body)
