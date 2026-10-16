"""Migration 383 (Stage 2 design V3, NNN-A): the 2v2 and 1v2 mid-game
readmission precursor, executed on a scratch case schema.

The build is cf_pg.build step for step (replay, ORM, widen, replay, 331,
365, 355) with ONE difference: 383 is held out of both replays, so the case
runs the file this lane ships as its FIRST apply, then runs it again (the
re-run proves idempotence), on a schema that already holds a team series, a
1v2 series and their queue rows from before the file. The write half is dry
run against the new constraints.

The header test needs no database: every statement of the file is guarded,
the file is one explicit transaction (#340), and no comment carries a bind
name (#697).
"""

import asyncio
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import cf_pg  # noqa: E402

try:
    import asyncpg as _asyncpg
except ImportError:                                    # pragma: no cover
    _asyncpg = None

M383_TRACKED = os.path.join(cf_pg.SQL_DIR, "383_match_hold_stage2.sql")
# MATCH_HOLD_M383, when set, names a MUTANT copy of 383 that the cases below
# apply in place of the tracked file (the mutation runner sets it); the
# census proves which file ran (#742, #838).
M383 = os.environ.get("MATCH_HOLD_M383") or M383_TRACKED
M383_NAME = os.path.basename(M383_TRACKED)

NEW_TABLES = ("match_games", "match_seat_holds", "match_seat_presence",
              "match_hold_open_attempts", "match_hold_attempts",
              "match_report_windows", "match_report_journal")


def _run(coro):
    return asyncio.run(coro)


def _src():
    return io.open(M383, encoding="utf-8").read()


def test_m383_census():
    """The 383 these cases apply is the one this run names: the mutant copy
    when MATCH_HOLD_M383 is set (and it differs from the tracked file), the
    tracked file otherwise."""
    want = os.environ.get("MATCH_HOLD_M383")
    if want:
        assert os.path.abspath(M383) == os.path.abspath(want)
        assert _src() != io.open(M383_TRACKED, encoding="utf-8").read()
    else:
        assert M383 == M383_TRACKED


# -- the header: every statement guarded, one transaction ---------------------

_GUARDED = (
    re.compile(r"^CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\b", re.I),
    re.compile(r"^CREATE\s+(UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\b", re.I),
    re.compile(r"^ALTER\s+TABLE\s+\w+\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\b", re.I),
)


def test_383_header_every_statement_guarded():
    """Every DDL statement of 383 is IF NOT EXISTS; the only other statements
    are BEGIN, SET LOCAL, the proof block and COMMIT, in that frame; no
    comment names a bind; the file reads no NOW()."""
    stmts = cf_pg.lh._split_sql(_src())
    assert stmts[0].upper() == "BEGIN", stmts[0][:40]
    assert stmts[-1].upper() == "COMMIT", stmts[-1][:40]
    ddl = 0
    for s in stmts[1:-1]:
        head = s.lstrip()
        if re.match(r"^SET\s+LOCAL\b", head, re.I) or re.match(r"^DO\b", head, re.I):
            continue
        assert any(p.match(head) for p in _GUARDED), "unguarded statement: %r" % head[:80]
        ddl += 1
    assert ddl == 7 + 3 + 8, ddl          # seven tables, three indexes, eight columns
    for line in _src().splitlines():
        if "--" in line:
            assert not re.search(r":[a-z_]+\b", line.split("--", 1)[1]), line
    assert "NOW()" not in _src().upper().replace(" ", "")


# -- executed twice on a scratch schema ---------------------------------------

async def _build_without_383(c):
    """cf_pg.build with 383 held out of both DDL replays (module docstring)."""
    conn, schema = c.conn, c.schema
    statements = [(n, s) for n, s in cf_pg.ddl_statements() if n != M383_NAME]
    await cf_pg.lh._replay(conn, statements)
    engine = cf_pg.harness.bound_engine(cf_pg.DSN, schema)
    try:
        async with engine.begin() as e:
            await e.run_sync(cf_pg.models.Base.metadata.create_all)
    finally:
        await engine.dispose()
    await cf_pg.lh._widen(conn, schema)
    second = await cf_pg.lh._replay(conn, statements)
    unexpected = [f for f in second if f[1] not in cf_pg.lh._ALREADY
                  and (f[0], f[1]) not in cf_pg.lh.REPLAY_KNOWN]
    assert not unexpected, unexpected[:5]
    await conn.execute(io.open(cf_pg.M331, encoding="utf-8").read())
    await conn.execute(io.open(cf_pg.M365, encoding="utf-8").read())
    await cf_pg.apply_355(conn)


async def _seed_pre_383(conn):
    """Four players, a team series, a 1v2 series and queue rows, all from
    before 383 runs, as production's are."""
    pids = []
    for i in range(4):
        pids.append(await conn.fetchval(
            "INSERT INTO players (steam_id, display_name) VALUES ($1, $2) RETURNING id",
            "s383pre%d" % i, "pre383 %d" % i))
    tsid = await conn.fetchval(
        "INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id, t1_series_wins, "
        " t2_series_wins, status, rebalance_count, created_at, spawn_confirmations, "
        " spawn_confirmed_by, photon_room_id) "
        "VALUES (gen_random_uuid(), $1, $2, $3, $4, 0, 0, 'active', 0, clock_timestamp(), 0, "
        " '[]'::jsonb, 'team_pre383') RETURNING id", *pids)
    osid = await conn.fetchval(
        "INSERT INTO ovt_series (solo_id, duo_a_id, duo_b_id, photon_room_id) "
        "VALUES ($1, $2, $3, 'ovt_pre383') RETURNING id", *pids[:3])
    await conn.execute(
        "INSERT INTO team_queue (player_id, steam_id, display_name, rating, rating_deviation, "
        " completed_series, fallback_rating, status, ready, joined_at, queue_type, "
        " seen_settings_version) "
        "VALUES ($1, 's383pre0', 'pre383 0', 1500, 350, 0, 1500, 'searching', FALSE, "
        " clock_timestamp(), 'auto', 0)", pids[0])
    await conn.execute(
        "INSERT INTO ovt_queue (player_id, steam_id, display_name) "
        "VALUES ($1, 's383pre1', 'pre383 1')", pids[1])
    return pids, tsid, osid


_CATALOG_SQL = (
    "SELECT c.conname, c.oid::bigint FROM pg_constraint c "
    " WHERE c.conrelid = ANY(ARRAY[%s]::regclass[]) ORDER BY 1"
    % ", ".join("to_regclass('%s')" % t for t in NEW_TABLES + (
        "team_matches", "ovt_matches")))
_INDEX_SQL = ("SELECT to_regclass('uq_msh_one_open_per_room')::oid::bigint, "
              "       to_regclass('uq_match_games_first')::oid::bigint")
_COLUMNS_SQL = (
    "SELECT table_name, column_name, data_type, is_nullable, column_default "
    "  FROM information_schema.columns WHERE table_schema = current_schema() "
    "   AND table_name = ANY($1::text[]) ORDER BY 1, 2")


def test_383_first_apply_rerun_defaults_and_constraints():
    """383 runs whole as the first apply on a schema holding series and
    queue rows from before it, then again; the re-run replaces no constraint
    or index and changes no column; every pre-existing series reads hold_v2
    FALSE and hold_room NULL, every pre-existing queue row reads caps '';
    every new BOOLEAN default reads back FALSE on a fresh insert; and each
    new constraint refuses its bad row and admits the good one."""
    cf_pg.require_live_pg()

    async def go():
        async with cf_pg.harness.CaseSchema(cf_pg.DSN, "rjs2_mig") as c:
            conn = c.conn
            await _build_without_383(c)
            for t in NEW_TABLES:
                assert await conn.fetchval("SELECT to_regclass($1)", t) is None, t
            pids, tsid, osid = await _seed_pre_383(conn)
            await conn.execute(_src())
            first = [tuple(r) for r in await conn.fetch(_CATALOG_SQL)]
            idx = tuple(await conn.fetchrow(_INDEX_SQL))
            cols = [tuple(r) for r in await conn.fetch(
                _COLUMNS_SQL, list(NEW_TABLES) + ["team_queue", "ovt_queue", "team_series",
                                                   "ovt_series", "team_matches", "ovt_matches"])]
            await conn.execute(_src())
            assert [tuple(r) for r in await conn.fetch(_CATALOG_SQL)] == first, \
                "a re-run replaced a constraint"
            assert tuple(await conn.fetchrow(_INDEX_SQL)) == idx, "a re-run rebuilt an index"
            assert [tuple(r) for r in await conn.fetch(
                _COLUMNS_SQL, list(NEW_TABLES) + ["team_queue", "ovt_queue", "team_series",
                                                   "ovt_series", "team_matches", "ovt_matches"])
                    ] == cols, "a re-run changed a column"
            await c.seal()

            # pre-existing rows read unflagged
            for tbl, sid in (("team_series", tsid), ("ovt_series", osid)):
                row = await conn.fetchrow(
                    "SELECT hold_v2, hold_room FROM %s WHERE id = $1" % tbl, sid)
                assert (row["hold_v2"], row["hold_room"]) == (False, None), tbl
            assert await conn.fetchval("SELECT caps FROM team_queue WHERE player_id = $1",
                                       pids[0]) == ""
            assert await conn.fetchval("SELECT caps FROM ovt_queue WHERE player_id = $1",
                                       pids[1]) == ""

            # every new BOOLEAN default reads back false on a fresh insert
            tsid2 = await conn.fetchval(
                "INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id, t1_series_wins, "
                " t2_series_wins, status, rebalance_count, created_at, spawn_confirmations, "
                " spawn_confirmed_by) VALUES (gen_random_uuid(), $1, $2, $3, $4, 0, 0, "
                " 'active', 0, clock_timestamp(), 0, '[]'::jsonb) RETURNING id", *pids)
            assert await conn.fetchval(
                "SELECT hold_v2 FROM team_series WHERE id = $1", tsid2) is False
            osid2 = await conn.fetchval(
                "INSERT INTO ovt_series (solo_id, duo_a_id, duo_b_id) VALUES ($1, $2, $3) "
                "RETURNING id", *pids[:3])
            assert await conn.fetchval(
                "SELECT hold_v2 FROM ovt_series WHERE id = $1", osid2) is False
            booleans = await conn.fetch(
                "SELECT table_name, column_name, is_nullable, column_default "
                "  FROM information_schema.columns WHERE table_schema = current_schema() "
                "   AND data_type = 'boolean' AND ((table_name = ANY($1::text[])) "
                "    OR (table_name IN ('team_series', 'ovt_series') AND column_name = 'hold_v2'))",
                list(NEW_TABLES))
            assert {(r["table_name"], r["column_name"]) for r in booleans} == {
                ("match_seat_holds", "crossed_at_hold"), ("team_series", "hold_v2"),
                ("ovt_series", "hold_v2")}
            for r in booleans:
                assert (r["is_nullable"], r["column_default"]) == ("NO", "false"), dict(r)

            # the write half: each constraint refuses its bad row, admits the good one
            async def refused(sql, *args):
                tr = conn.transaction()
                await tr.start()
                try:
                    await conn.execute(sql, *args)
                except (_asyncpg.CheckViolationError, _asyncpg.UniqueViolationError):
                    await tr.rollback()
                    return True
                await tr.rollback()
                return False

            g1 = await conn.fetchval(
                "INSERT INTO match_games (mode, series_id, room_name, seq) "
                "VALUES ('team', $1, 'team_pre383', 1) RETURNING id", tsid)
            assert await refused(
                "INSERT INTO match_games (mode, series_id, room_name, seq) "
                "VALUES ('team', $1, 'team_pre383', 2)", tsid), "a second first game"
            assert await refused(
                "INSERT INTO match_games (mode, series_id, room_name, seq, prev_game) "
                "VALUES ('team', $1, 'team_pre383', 1, $2)", tsid, g1), "a repeated seq"
            assert await refused(
                "INSERT INTO match_games (mode, series_id, room_name, seq) "
                "VALUES ('duel', $1, 'x', 1)", tsid), "a mode outside team and ovt"
            g2 = await conn.fetchval(
                "INSERT INTO match_games (mode, series_id, room_name, seq, prev_game) "
                "VALUES ('team', $1, 'team_pre383', 2, $2) RETURNING id", tsid, g1)
            assert await refused(
                "INSERT INTO match_games (mode, series_id, room_name, seq, prev_game) "
                "VALUES ('team', $1, 'team_pre383', 3, $2)", tsid, g1), "a forked chain"

            hold = ("INSERT INTO match_seat_holds (mode, room_name, series_id, game_id, "
                    " player_id, n, slot, team, opener_player_id, held_anchor_at, held_at, "
                    " held_until%s) VALUES ('team', $1, $2, $3, $4, $5, 0, 0, $6, "
                    " clock_timestamp(), clock_timestamp(), clock_timestamp() + "
                    " make_interval(secs => 120)%s) RETURNING id")
            h1 = await conn.fetchval(hold % ("", ""), "team_pre383", tsid, g1, pids[0], 1,
                                     pids[1])
            assert await conn.fetchval(
                "SELECT crossed_at_hold FROM match_seat_holds WHERE id = $1", h1) is False
            assert await refused(hold % ("", ""), "team_pre383", tsid, g2, pids[2], 1,
                                 pids[1]), "two open holds in one room"
            assert await refused(hold % (", closed_at", ", clock_timestamp()"),
                                 "team_pre383", tsid, g2, pids[2], 1, pids[1]), \
                "a closure without a reason"
            await conn.execute(
                "UPDATE match_seat_holds SET closed_at = clock_timestamp(), "
                " closed_reason = 'lapsed' WHERE id = $1", h1)
            assert await refused(hold % ("", ""), "team_pre383", tsid, g1, pids[0], 2,
                                 pids[1]), "a second hold of one seat in one game"
            assert await refused(hold % ("", ""), "team_pre383", tsid, g2, pids[0], 1,
                                 pids[1]), "a repeated n for one player in one room"
            h2 = await conn.fetchval(hold % ("", ""), "team_pre383", tsid, g2, pids[0], 2,
                                     pids[1])
            assert h2 is not None

            assert await refused(
                "INSERT INTO match_hold_open_attempts (request_id, room_name, at, outcome) "
                "VALUES ('r1', 'x', clock_timestamp(), 'opened')"), "opened without a hold"
            await conn.execute(
                "INSERT INTO match_hold_open_attempts (request_id, room_name, at, outcome, "
                " reason) VALUES ('r2', 'x', clock_timestamp(), 'refused', 'no_presence')")
            assert await refused(
                "INSERT INTO match_hold_attempts (hold_id, attempt_no, kind, at, outcome) "
                "VALUES ($1, 1, 'claim', clock_timestamp(), 'refused')", h2), \
                "a refusal without a reason"
            assert await refused(
                "INSERT INTO match_hold_attempts (hold_id, attempt_no, kind, at, outcome) "
                "VALUES ($1, 1, 'decline', clock_timestamp(), 'ok')", h2), "an unknown kind"
            await conn.execute(
                "INSERT INTO match_hold_attempts (hold_id, attempt_no, kind, at, outcome) "
                "VALUES ($1, 1, 'offered', clock_timestamp(), 'ok')", h2)

            assert await refused(
                "INSERT INTO match_report_windows (room_name, game_id, mode, opened_at, "
                " settle_after, settled_at) VALUES ('team_pre383', $1, 'team', "
                " clock_timestamp(), clock_timestamp(), clock_timestamp())", g1), \
                "settled without a class"
            assert await refused(
                "INSERT INTO match_report_journal (room_name, game_id, reporter_id, mode, "
                " reporter_steam, cls, payload, received_at) VALUES ('team_pre383', $1, $2, "
                " 'team', 's', 'x', '{}'::jsonb, clock_timestamp())", g1, pids[0]), \
                "an unknown class"
            for tbl in ("team_matches", "ovt_matches"):
                con = await conn.fetchval(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    " WHERE conname = $1", "ck_%s_fallback_cls" % tbl)
                assert "'r'" in con and "'c'" in con and "'u'" in con, con
                assert await conn.fetchval(
                    "SELECT is_nullable FROM information_schema.columns "
                    " WHERE table_schema = current_schema() AND table_name = $1 "
                    "   AND column_name = 'fallback_cls'", tbl) == "YES"

            # leave the sealed schema with only what the census admits
            for t in ("match_hold_attempts", "match_hold_open_attempts",
                      "match_seat_holds", "match_games"):
                await conn.execute("DELETE FROM %s" % t)
    _run(go())


def test_383_proof_block_raises_on_a_gap():
    """The proof block is enforcing: with one proved column renamed away and
    one proved default changed before a re-run (and the statement that would
    restore the column taken out of the re-run), the file raises naming both
    gaps, and its transaction rolls back (a table it re-created is gone)."""
    cf_pg.require_live_pg()

    async def go():
        async with cf_pg.harness.CaseSchema(cf_pg.DSN, "rjs2_migneg") as c:
            conn = c.conn
            await _build_without_383(c)
            await conn.execute(_src())
            await conn.execute("ALTER TABLE ovt_series RENAME COLUMN hold_room TO hold_room_x")
            await conn.execute("ALTER TABLE ovt_series ALTER COLUMN hold_v2 SET DEFAULT TRUE")
            await conn.execute("DROP TABLE match_report_journal")
            gap = "ALTER TABLE ovt_series   ADD COLUMN IF NOT EXISTS hold_room VARCHAR(64);"
            assert _src().count(gap) == 1
            msg = ""
            try:
                await conn.execute(_src().replace(gap, ""))
            except _asyncpg.RaiseError as e:
                msg = str(e)
            if conn.is_in_transaction():
                await conn.execute("ROLLBACK")
            assert "column ovt_series.hold_room" in msg, msg
            assert "default ovt_series.hold_v2" in msg, msg
            assert await conn.fetchval("SELECT to_regclass('match_report_journal')") is None
    _run(go())
