"""FFA: which game a report is for, and what that changes (RJ-4 + RJ-3 server).

Two live defects share one missing fact — `ffa_matches` never recorded WHICH
game of a sitting a row was. Migration 327 adds `game_number`; this file pins
what the api then does with it.

  RJ-4  The pace anchor took MAX(ended_at) over every row of the lobby, so a
        second row for one game became the next game's anchor. The verified
        2026-08-07 lobby metered a full game against the 57-second gap between
        two receipts and paid about a tenth.
  RJ-3  Two clients of one game each stamp their own start time into their own
        room id, so the room-id unique never saw them as the same game and both
        settled. The two rows name different winners.

The anchor tests RUN the production SQL string against a real PostgreSQL —
`_FFA_PACE_ANCHOR_SQL` carries `CAST(:g AS SMALLINT)` and an `IS DISTINCT FROM`
over a nullable column, and a bind Postgres cannot type is not a subtle bug
(#275/#448/#438). Point FFA_TEST_PG_DSN at a throwaway cluster:

    FFA_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:55432/rjtest" \\
        python -m pytest backend/tests/test_ffa_game_number_anchor.py -q

The pure tests below need no server and always run.

Named mutation controls (each was run RED then reverted):
  anchor-per-row          _FFA_PACE_ANCHOR_SQL: MIN(ended_at) -> MAX(ended_at)
  anchor-includes-self    _FFA_PACE_ANCHOR_SQL: IS DISTINCT FROM CAST(:g AS SMALLINT)
                          -> IS NOT NULL
  anchor-less-than        _FFA_PACE_ANCHOR_SQL: IS DISTINCT FROM -> <
  prior-keeps-invalidated _FFA_PRIOR_GAME_SQL: drop `AND invalidated_at IS NULL`
  contradiction-blind     _ffa_report_contradiction: first line -> `return None`
  shape-floor-gone        _ffa_score_shape_error: drop the `max_rounds !=` arm
  headroom-hostile        FFA_PACE_HEADROOM = 0.01
  insert-unnumbered       submit_ffa_match's INSERT: drop `game_number`
"""
import asyncio
import inspect
import os
import pathlib
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import main


# ── fixtures shaped like the verified 2026-08-07 rows ─────────────────────
# lobby 0ea879a4-ff42-44c4-9473-4c58f89ef934, game 1, three players, two rows
# that disagree. Steam ids are the real ones only in shape: they are outside
# the SteamID64 space so nothing here can be mistaken for a production row.
S1, S2, S3 = "90000000000000101", "90000000000000102", "90000000000000103"

ROW_A = {S1: (4, 11), S2: (1, 6), S3: (5, 15)}      # winner S3
ROW_B = {S1: (5, 11), S2: (1, 5), S3: (3, 12)}      # winner S1


def _report(vec, winner, room="rm_211531_r1"):
    """The fields the pure helpers read off a FfaMatchReport."""
    return types.SimpleNamespace(
        photon_room_id=room, winner_steam_id=winner,
        players=[types.SimpleNamespace(steam_id=s, rounds_won=r, points_total=p)
                 for s, (r, p) in vec.items()])


# ── the number itself ─────────────────────────────────────────────────────

def test_game_number_comes_from_the_room_tail():
    assert main._ffa_report_game_number("rm_211531_r1", 0) == 1
    assert main._ffa_report_game_number("rm_212540_r2", 1) == 2
    assert main._ffa_report_game_number("rm_212540_r40", 7) == 40


def test_game_number_falls_back_to_the_lobbys_own_counter():
    # No tail, and the two forms that must not become a SMALLINT value: a tail
    # outside the column's domain, and a zero. The fallback is the lobby's own
    # counter + 1 — a plausible non-NULL number, not a claim about ordering.
    for room in (None, "", "rm_no_tail", "rm_r0", "rm_r99999", "rm_r-1"):
        assert main._ffa_report_game_number(room, 3) == 4, room
    assert main._ffa_report_game_number("rm_no_tail", None) == 1


def test_game_number_stays_inside_the_column_domain():
    assert main.FFA_GAME_NUMBER_MAX <= 32767          # SMALLINT
    assert main.FFA_GAME_NUMBER_MAX > main.FFA_MAX_GAMES_PER_LOBBY
    assert main._ffa_report_game_number(f"rm_r{main.FFA_GAME_NUMBER_MAX}", 0) \
        == main.FFA_GAME_NUMBER_MAX
    assert main._ffa_report_game_number(f"rm_r{main.FFA_GAME_NUMBER_MAX + 1}", 0) == 1


# ── what the anchor is worth: the meter (control: headroom-hostile) ───────

def test_a_full_game_window_pays_every_claimed_battle():
    # Row A's own numbers: 32 battles over the ~686s the game really took.
    # Under the fitted pace for three players that window is far above the
    # claim, so the ceiling does not bind and the claim is paid in full.
    assert main._ffa_paid_battles(32, 686.0, 3) == 32.0


def test_a_duplicates_receipt_gap_throttles_the_payout():
    # The same claim metered against the 57s between the two receipts — the
    # defect's signature. Nothing here asserts a policy; it asserts that the
    # window is what decides, which is why the window had to stop being
    # "since the previous ROW".
    throttled = main._ffa_paid_battles(32, 57.0, 3)
    assert throttled < 32.0
    assert throttled == pytest.approx(57.0 * main.FFA_PACE_HEADROOM
                                      / main._ffa_sec_per_battle(3))


# ── the detector (control: contradiction-blind) ───────────────────────────

def test_the_two_verified_rows_are_a_contradiction():
    why = main._ffa_report_contradiction(S3, ROW_A, _report(ROW_B, S1))
    assert why is not None
    assert S1 in why                      # names the winner disagreement first


def test_a_redelivery_of_the_same_report_is_not_a_contradiction():
    assert main._ffa_report_contradiction(S3, ROW_A, _report(ROW_A, S3)) is None


def test_a_tally_that_differs_by_one_point_is_a_contradiction():
    near = dict(ROW_A, **{S2: (1, 7)})
    why = main._ffa_report_contradiction(S3, ROW_A, _report(near, S3))
    assert why is not None and S2 in why


def test_a_roster_difference_is_a_contradiction_either_way():
    short = {S1: ROW_A[S1], S3: ROW_A[S3]}
    assert main._ffa_report_contradiction(S3, ROW_A, _report(short, S3)) is not None
    assert main._ffa_report_contradiction(S3, short, _report(ROW_A, S3)) is not None


def test_the_detector_is_symmetric():
    # Whichever of the two verified rows had settled first, the other is a
    # contradiction: the detector reports a disagreement, it never ranks the
    # two accounts.
    assert main._ffa_report_contradiction(S3, ROW_A, _report(ROW_B, S1)) is not None
    assert main._ffa_report_contradiction(S1, ROW_B, _report(ROW_A, S3)) is not None


# ── the partial-view refusal (control: shape-floor-gone) ──────────────────

def test_a_report_short_of_the_score_target_is_refused():
    # A client that did not watch the whole game cannot show anyone at the
    # target. 1/0/0 against first-to-5 is the relaunched-reporter shape.
    near_zero = {S1: (1, 2), S2: (0, 0), S3: (0, 0)}
    why = main._ffa_score_shape_error(_report(near_zero, S1), 5, 3)
    assert why == "winner must hold exactly 5 rounds"


def test_a_complete_game_passes_the_shape_rule():
    assert main._ffa_score_shape_error(_report(ROW_A, S3), 5, 3) is None
    assert main._ffa_score_shape_error(_report(ROW_B, S1), 5, 3) is None


def test_the_summed_rounds_floor_could_never_fire():
    # Recorded rather than shipped: the brief asked for sum(rounds_won) >=
    # score_target. The winner alone contributes score_target on every report
    # the rule above admits, and rounds_won is non-negative, so such a check
    # cannot fail — and a check that cannot fail is worse than none (#342).
    for vec in (ROW_A, ROW_B):
        assert main._ffa_score_shape_error(_report(vec, max(vec, key=lambda s: vec[s][0])),
                                           5, 3) is None
        assert sum(r for r, _ in vec.values()) >= 5


# ── wiring (control: insert-unnumbered) ───────────────────────────────────

def test_the_endpoint_numbers_the_row_it_writes():
    src = inspect.getsource(main.submit_ffa_match)
    derive = src.index("_ffa_report_game_number(")
    prior = src.index("_FFA_PRIOR_GAME_SQL")
    anchor = src.index("_FFA_PACE_ANCHOR_SQL")
    insert = src.index("INSERT INTO ffa_matches")
    assert derive < prior < anchor < insert
    # The INSERT's column list carries the number, or every row written from
    # here is NULL and the anchor silently degrades to the pre-327 one.
    cols = src[insert:src.index("VALUES", insert)]
    assert "game_number" in cols
    assert "CAST(:gn AS SMALLINT)" in src


def test_the_second_report_of_a_game_is_recorded_and_not_settled():
    src = inspect.getsource(main.submit_ffa_match)
    prior = src.index("_FFA_PRIOR_GAME_SQL")
    insert = src.index("INSERT INTO ffa_matches")
    branch = src[prior:insert]
    assert "ffa_game_contradiction" in branch
    assert "_quarantine_report" in branch
    # No reversal, no claw-back, no re-pointing of a recorded row: the branch
    # that handles a second report writes nothing to any match or player row.
    for forbidden in ("UPDATE ffa_matches", "UPDATE players", "invalidated_at =",
                      "DELETE FROM"):
        assert forbidden not in branch, forbidden


def test_the_migration_declares_the_column_the_code_binds_and_no_key():
    sql = (pathlib.Path(__file__).resolve().parents[1]
           / "sql" / "327_ffa_game_number.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS game_number SMALLINT" in sql
    assert "BEGIN;" in sql and "COMMIT;" in sql          # #340
    assert "BEFORE THE CODE" in sql.upper()
    # Acceptance bar: no dedup key was added or widened. A unique on
    # (lobby_id, game_number) would fold the 2026-08-07 pair, which means
    # picking one of two unreconciled accounts (#283).
    upper = sql.upper()
    assert "CREATE UNIQUE INDEX" not in upper
    assert "ADD CONSTRAINT" not in upper
    assert "DELETE FROM" not in upper and "DROP TABLE" not in upper
    # The only write to existing rows is the new column's backfill.
    assert upper.count("UPDATE FFA_MATCHES") == 1


def test_the_bet_settle_reads_the_number_the_row_was_written_with():
    src = inspect.getsource(main.submit_ffa_match)
    assert "game_no = _game_number" in src
    # A second derivation here could pay game N's wagers against a row stored
    # as something else.
    assert src.count("_ffa_report_game_number(") == 1


# ── live PostgreSQL: the anchor, executed ─────────────────────────────────

DSN = os.environ.get("FFA_TEST_PG_DSN")
pg = pytest.mark.skipif(not DSN, reason="FFA_TEST_PG_DSN unset; live-Postgres anchor check")

SCHEMA = """
DROP TABLE IF EXISTS ffa_match_players;
DROP TABLE IF EXISTS ffa_matches;
DROP TABLE IF EXISTS players;

CREATE TABLE players (
    id UUID PRIMARY KEY,
    steam_id TEXT NOT NULL UNIQUE
);
CREATE TABLE ffa_matches (
    id UUID PRIMARY KEY,
    lobby_id UUID,
    photon_room_id VARCHAR(64) NOT NULL,
    player_count SMALLINT NOT NULL DEFAULT 3,
    winner_id UUID REFERENCES players(id),
    ended_at TIMESTAMPTZ NOT NULL,
    invalidated_at TIMESTAMPTZ,
    game_number SMALLINT,
    CONSTRAINT uq_ffa_match_room UNIQUE (photon_room_id)
);
CREATE TABLE ffa_match_players (
    match_id UUID NOT NULL REFERENCES ffa_matches(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players(id),
    rounds_won SMALLINT NOT NULL DEFAULT 0,
    points_total SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (match_id, player_id)
);
"""

LOBBY = uuid.UUID("0ea879a4-ff42-44c4-9473-4c58f89ef934")
T0 = datetime(2026, 8, 7, 21, 15, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


async def _setup(rows):
    """rows: (room, game_number, seconds_after_T0, invalidated) tuples."""
    engine = create_async_engine(DSN)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        for stmt in [s for s in SCHEMA.split(";") if s.strip()]:
            await conn.execute(text(stmt))
    pids = {}
    async with sm() as db:
        for s in (S1, S2, S3):
            pids[s] = uuid.uuid4()
            await db.execute(text("INSERT INTO players (id, steam_id) VALUES (:i, :s)"),
                             {"i": pids[s], "s": s})
        for room, gn, secs, inval in rows:
            await db.execute(text("""
                INSERT INTO ffa_matches (id, lobby_id, photon_room_id, winner_id,
                                         ended_at, invalidated_at, game_number)
                VALUES (:i, :l, :r, :w,
                        CAST(:t0 AS TIMESTAMPTZ)
                          + make_interval(secs => CAST(:s AS DOUBLE PRECISION)),
                        CASE WHEN CAST(:inv AS BOOLEAN) THEN NOW() ELSE NULL END,
                        CAST(:g AS SMALLINT))
            """), {"i": uuid.uuid4(), "l": LOBBY, "r": room, "w": pids[S3],
                   "t0": T0, "s": float(secs), "inv": bool(inval), "g": gn})
        await db.commit()
    return engine, sm, pids


async def _anchor(sm, g):
    async with sm() as db:
        return (await db.execute(text(main._FFA_PACE_ANCHOR_SQL),
                                 {"lid": LOBBY, "g": g})).scalar()


@pg
def test_pg_a_second_row_for_one_game_is_not_the_next_games_anchor():
    """Control: anchor-per-row, anchor-includes-self."""
    async def go():
        # game 1 reported at +686s, a second row for game 1 57s later.
        engine, sm, _ = await _setup([
            ("rm_211532_r1", 1, 686, False),
            ("rm_211531_r1", 1, 743, False),
        ])
        try:
            a2 = await _anchor(sm, 2)          # reporting game 2
            a1 = await _anchor(sm, 1)          # a further report OF game 1
            return a2, a1
        finally:
            await engine.dispose()
    a2, a1 = run(go())
    # The first receipt of game 1, not the second row's 57 seconds later.
    assert a2 == T0 + timedelta(seconds=686)
    assert a2 != T0 + timedelta(seconds=743)
    # And the game being reported is never its own anchor: for game 1 this
    # lobby has no OTHER game, so the endpoint falls back to lobby.created_at.
    assert a1 is None


@pg
def test_pg_a_low_number_late_in_a_sitting_cannot_widen_the_window():
    """The #283 direction. Control: anchor-less-than."""
    async def go():
        engine, sm, _ = await _setup([
            ("rm_a_r1", 1, 600, False),
            ("rm_b_r2", 2, 1300, False),
            ("rm_c_r3", 3, 2000, False),
        ])
        try:
            return await _anchor(sm, 1), await _anchor(sm, 4)
        finally:
            await engine.dispose()
    as_one, as_four = run(go())
    # A report numbered 1 still anchors on game 3's receipt, not on lobby
    # creation: choosing the number must not choose the window.
    assert as_one is not None and as_four is not None
    assert as_one == as_four


@pg
def test_pg_rows_with_no_derivable_number_still_count_as_earlier_games():
    async def go():
        engine, sm, _ = await _setup([
            ("legacy_room", None, 600, False),
            ("rm_b_r2", 2, 1300, False),
        ])
        try:
            return await _anchor(sm, 2), await _anchor(sm, 9)
        finally:
            await engine.dispose()
    as_two, as_nine = run(go())
    assert as_two is not None            # the legacy row anchors game 2
    assert as_nine > as_two              # game 2's own receipt anchors game 9


@pg
def test_pg_the_prior_game_lookup_finds_the_row_that_settled_first():
    """Control: prior-keeps-invalidated."""
    async def go():
        engine, sm, _ = await _setup([
            ("rm_void_r1", 1, 500, True),      # reversed by an admin
            ("rm_live_r1", 1, 686, False),     # the one whose rating is live
            ("rm_late_r1", 1, 743, False),
        ])
        try:
            async with sm() as db:
                row = (await db.execute(text(main._FFA_PRIOR_GAME_SQL),
                                        {"lid": LOBBY, "g": 1})).mappings().first()
                none_for_2 = (await db.execute(text(main._FFA_PRIOR_GAME_SQL),
                                               {"lid": LOBBY, "g": 2})).mappings().first()
            return row, none_for_2
        finally:
            await engine.dispose()
    row, none_for_2 = run(go())
    assert row is not None and row["photon_room_id"] == "rm_live_r1"
    assert none_for_2 is None


@pg
def test_pg_the_recorded_vector_reads_back_for_the_comparison():
    async def go():
        engine, sm, pids = await _setup([("rm_live_r1", 1, 686, False)])
        try:
            async with sm() as db:
                mid = (await db.execute(text(
                    "SELECT id FROM ffa_matches WHERE photon_room_id = 'rm_live_r1'"
                ))).scalar()
                for s, (r, p) in ROW_A.items():
                    await db.execute(text(
                        "INSERT INTO ffa_match_players (match_id, player_id,"
                        " rounds_won, points_total) VALUES (:m, :p, :r, :t)"),
                        {"m": mid, "p": pids[s], "r": r, "t": p})
                await db.commit()
                rows = (await db.execute(text(main._FFA_PRIOR_VECTOR_SQL),
                                         {"m": mid})).mappings().all()
            return {r["steam_id"]: (int(r["rounds_won"]), int(r["points_total"]))
                    for r in rows}
        finally:
            await engine.dispose()
    vec = run(go())
    assert vec == ROW_A
    assert main._ffa_report_contradiction(S3, vec, _report(ROW_B, S1)) is not None
    assert main._ffa_report_contradiction(S3, vec, _report(ROW_A, S3)) is None
