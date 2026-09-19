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

THE RULE THIS FILE EXISTS TO PIN: the number a report settles is the LOBBY's
(`ffa_lobbies.games_played + 1`, read under the lobby row's FOR UPDATE), never
the report's. The report room id's `_rN` tail is a cross-check. Every test
below whose name says what a misreported number "gains" answers: nothing.

The live tests RUN the production SQL and the production migration against a
real PostgreSQL — `_FFA_PACE_ANCHOR_SQL` carries `CAST(:g AS SMALLINT)` and an
`IS DISTINCT FROM`, `_FFA_PRIOR_GAME_SQL` carries `ANY(CAST(:gs AS SMALLINT[]))`,
and a bind Postgres cannot type is not a subtle bug (#275/#448/#438). Point
FFA_TEST_PG_DSN at a throwaway cluster:

    FFA_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:55432/rjtest" \\
        python -m pytest backend/tests/test_ffa_game_number_anchor.py -q

Without it they FAIL, naming the DSN. A run that means to go without a
PostgreSQL says so out loud by setting FFA_TEST_PG_OPTOUT=1, which turns them
back into skips — the point is that nobody gets a green run they did not ask
for (#438: a feature can ship inert with perfect logs).

Named mutation controls. Twenty-three, each applied to a copy-aside of the
file, run RED, and restored from the copy (never `git checkout --`, #290):

  anchor-per-row           _FFA_PACE_ANCHOR_SQL: MIN(ended_at) -> MAX(ended_at)
  anchor-includes-self     _FFA_PACE_ANCHOR_SQL: IS DISTINCT FROM CAST(:g AS
                           SMALLINT) -> IS NOT NULL
  anchor-less-than         _FFA_PACE_ANCHOR_SQL: IS DISTINCT FROM -> <
  prior-skips-invalidated  _FFA_PRIOR_GAME_SQL: add `AND invalidated_at IS NULL`
  prior-tail-only          the endpoint's _candidates: drop _expected_game
  number-from-the-tail     the endpoint: _game_number = _room_tail
  number-rule-gone         _ffa_game_number_refusal: first line -> `return None`
  contradiction-blind      _ffa_report_contradiction: first line -> `return None`
  kills-not-compared       _ffa_report_contradiction: drop the compare_kills arm
  shape-winner-gone        _ffa_score_shape_error: drop the unique-maximum arm
  shape-target-gone        _ffa_score_shape_error: never take the target arm
  shape-skew-refused       _ffa_score_shape_error: admissible -> (score_target,)
  bound-gate-open-coded    the closed-lobby capture gate: back to its own copy
                           of `max_rounds == _score_target`
  replay-after-the-status-gate   the endpoint: drop the replay-echo call
  capture-always-ok        _ffa_record_and_refuse: drop the `_kept not in` arm
  capture-quota-silent     _quarantine_report: the quota arm returns "recorded"
  headroom-hostile         FFA_PACE_HEADROOM = 0.01
  insert-unnumbered        submit_ffa_match's INSERT: drop `game_number`
  bets-reparse-the-room    the bet settle: re-derive game_no from the room id
  migration-no-trigger     327: the BEFORE INSERT trigger never attaches
  migration-no-not-null    327: drop `SET NOT NULL`
  migration-no-check       327: the CHECK becomes `IS NOT NULL`
  postcheck-nulls-only     327: drop the post-check's derivable-tail assertion,
                           which is the control ON the backfill-neutered test

...and one more that is a COMMITTED TEST rather than a hand-run control:
  backfill-neutered        327's room_tail backfill: WHERE FALSE. See
                           test_pg_migration_327_post_check_fails_when_the_
                           backfill_is_neutered, and the negative control
                           asserting that mutation is exactly one predicate.

One control was initially LIVE and the CONTROL was the defect:
migration-no-not-null first replaced the ALTER with a comment that still
contained the words "SET NOT NULL", so the text assertion it aimed at kept
passing — it was measuring its own replacement string. Rebuilt to remove the
line, and the assertion it now reddens is an EXECUTED insert against a
disabled trigger.
"""
import asyncio
import inspect
import os
import pathlib
import re
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import main

MIGRATION = (pathlib.Path(__file__).resolve().parents[1]
             / "sql" / "327_ffa_game_number.sql")


# ── fixtures shaped like the verified 2026-08-07 rows ─────────────────────
# lobby 0ea879a4-ff42-44c4-9473-4c58f89ef934, game 1, three players, two rows
# that disagree. Steam ids are the real ones only in shape: they are outside
# the SteamID64 space so nothing here can be mistaken for a production row.
S1, S2, S3 = "90000000000000101", "90000000000000102", "90000000000000103"

# steam -> (rounds_won, points_total, kills)
ROW_A = {S1: (4, 11, 6), S2: (1, 6, 2), S3: (5, 15, 9)}      # winner S3
ROW_B = {S1: (5, 11, 6), S2: (1, 5, 2), S3: (3, 12, 9)}      # winner S1


def _report(vec, winner, room="rm_211531_r1"):
    """The fields the pure helpers read off a FfaMatchReport."""
    return types.SimpleNamespace(
        photon_room_id=room, winner_steam_id=winner,
        players=[types.SimpleNamespace(steam_id=s, rounds_won=r,
                                       points_total=p, kills=k)
                 for s, (r, p, k) in vec.items()])


def _endpoint_src():
    return inspect.getsource(main.submit_ffa_match)


# ── the number: whose is it? ──────────────────────────────────────────────

def test_the_number_a_report_settles_is_the_lobbys_own_next_slot():
    src = _endpoint_src()
    # Read from the lobby row, under the FOR UPDATE taken above it.
    assert 'int(lobby["games_played"] or 0) + 1' in src
    assert "_game_number = _expected_game" in src
    lock = src.index("FROM ffa_lobbies WHERE id = :lid FOR UPDATE")
    derive = src.index("_expected_game = ")
    assert lock < derive
    # The room tail is read, but only as a cross-check: it never becomes the
    # stored number. (Control: number-from-the-tail.)
    assert "_room_tail = _ffa_room_game_no(" in src
    assert "_game_number = _room_tail" not in src
    assert "_game_number = int(_room_tail" not in src
    # The round-1 helper that took the tail as the number is gone entirely.
    assert not hasattr(main, "_ffa_report_game_number")


def test_the_stored_number_is_the_one_the_anchor_and_the_bet_settle_use():
    src = _endpoint_src()
    derive = src.index("_expected_game = ")
    prior = src.index("_FFA_PRIOR_GAME_SQL")
    anchor = src.index("_FFA_PACE_ANCHOR_SQL")
    insert = src.index("INSERT INTO ffa_matches")
    bets = src.index("game_no = _game_number")
    assert derive < prior < anchor < insert < bets
    # The INSERT's column list carries the number, or every row written from
    # here is NULL — which migration 327's NOT NULL now rejects outright.
    # (Control: insert-unnumbered.)
    cols = src[insert:src.index("VALUES", insert)]
    assert "game_number" in cols
    assert "CAST(:gn AS SMALLINT)" in src
    # One derivation, not two: a bet settle that re-parsed the room id is how
    # game N's wagers get paid against a row stored as something else.
    assert src.count("_ffa_room_game_no(") == 1
    # ...and the straggler catch-up reads the column too, not a LIKE on the
    # room string.
    assert "photon_room_id LIKE :sfx" not in src
    assert "game_number = CAST(:sg AS SMALLINT)" in src


def test_the_candidate_set_covers_both_the_slot_and_the_room_tail():
    """Control: prior-tail-only. The lookup has to ask about the slot this
    report would consume AND the game its own room id names — the first stops
    a report renaming its game to dodge the comparison, the second catches the
    second client of one game, whose counter still says N."""
    src = _endpoint_src()
    cand = src[src.index("_candidates = "):src.index("_prior_game = ")]
    assert "_expected_game" in cand and "_room_tail" in cand
    assert "FFA_GAME_NUMBER_MAX" in cand          # out-of-domain tails excluded
    assert '"gs": _candidates' in src


# ── what a misreported number gains: nothing ──────────────────────────────

def test_a_number_matching_the_lobbys_next_game_is_accepted():
    assert main._ffa_game_number_refusal(4, 4) is None


def test_a_higher_number_than_the_lobbys_next_game_gains_no_slot_of_its_own():
    # Accepted, but it settles the LOBBY's slot, not the one it named. A
    # counter ahead of the server is what one lost report leaves behind, and
    # refusing every later game of that sitting would cost the honest players
    # more than the report it was easing (#430).
    assert main._ffa_game_number_refusal(9, 4) is None
    assert main._ffa_game_number_refusal(main.FFA_GAME_NUMBER_MAX, 1) is None
    # ...and the endpoint stores the slot regardless of which came back.
    assert "_game_number = _expected_game" in _endpoint_src()


def test_a_lower_number_with_no_recorded_game_is_refused():
    why = main._ffa_game_number_refusal(2, 5)
    assert why is not None and "expected_game=5" in why


def test_a_missing_game_number_is_refused():
    assert main._ffa_room_game_no("rm_no_tail_at_all") is None
    why = main._ffa_game_number_refusal(None, 1)
    assert why is not None and "no game number" in why


def test_a_zero_game_number_is_refused():
    # The counter a seat carries before it has run this game's start: exactly
    # the partial-view reporter RJ-3 keeps out.
    assert main._ffa_room_game_no("rm_101000_r0") == 0
    why = main._ffa_game_number_refusal(0, 1)
    assert why is not None and "outside 1..999" in why


def test_a_game_number_over_the_bound_is_refused():
    assert main._ffa_room_game_no("rm_102000_r99999") == 99999
    why = main._ffa_game_number_refusal(99999, 1)
    assert why is not None and "outside 1..999" in why


def test_every_refusal_this_rule_can_return_is_recorded_before_it_answers():
    """Control: number-rule-gone. A 409 is terminal for the client's outbox
    precisely because the server keeps what it refuses."""
    src = _endpoint_src()
    block = src[src.index("_number_error = "):src.index("# Players pass:")]
    assert "_ffa_record_and_refuse" in block
    assert "ffa_game_number_mismatch" in block
    # ...and the refusal names the number an honest drifted client should use.
    assert "expected_game={_expected_game}" in block


def test_the_number_rule_stays_inside_the_column_domain():
    assert main.FFA_GAME_NUMBER_MAX <= 32767          # SMALLINT width
    assert main.FFA_GAME_NUMBER_MAX > main.FFA_MAX_GAMES_PER_LOBBY
    # The bound is the CHECK's, not the width's (a SMALLINT accepts 32767).
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CHECK (game_number BETWEEN 1 AND 999)" in sql
    assert str(main.FFA_GAME_NUMBER_MAX) in sql


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


def test_the_anchor_and_the_prior_lookup_treat_a_reversal_the_same_way():
    """Control: prior-skips-invalidated. Both INCLUDE invalidated rows. A
    lookup that skipped them while the anchor kept excluding their number would
    let a report reusing a reversed game's number settle a second time AND be
    metered against a window that row had been removed from — a wider window
    and a larger payout than the honest game got."""
    assert "invalidated_at IS NULL" not in main._FFA_PRIOR_GAME_SQL
    assert "invalidated_at" not in main._FFA_PACE_ANCHOR_SQL


# ── the detector (controls: contradiction-blind, kills-not-compared) ──────

def test_the_two_verified_rows_are_a_contradiction():
    why = main._ffa_report_contradiction(S3, ROW_A, _report(ROW_B, S1), False)
    assert why is not None
    assert S1 in why                      # names the winner disagreement first


def test_a_redelivery_of_the_same_report_is_not_a_contradiction():
    assert main._ffa_report_contradiction(S3, ROW_A, _report(ROW_A, S3), True) is None


def test_a_tally_that_differs_by_one_point_is_a_contradiction():
    near = dict(ROW_A, **{S2: (1, 7, 2)})
    why = main._ffa_report_contradiction(S3, ROW_A, _report(near, S3), False)
    assert why is not None and S2 in why


def test_a_kills_only_difference_is_a_contradiction_where_kills_place_players():
    # kills are the third placement key, so where the lobby's FROZEN
    # kills_tiebreak flag is set a kills-only difference moves a placement, and
    # with it a rating change, an XP award and a gold award.
    near = dict(ROW_A, **{S1: (4, 11, 99)})
    why = main._ffa_report_contradiction(S3, ROW_A, _report(near, S3), True)
    assert why is not None and "kills" in why


def test_a_kills_only_difference_is_not_a_contradiction_where_they_decide_nothing():
    # Two honest clients of one game can tally kills from different local
    # observations; a 409 for a difference that changed nothing would spend an
    # honest report.
    near = dict(ROW_A, **{S1: (4, 11, 99)})
    assert main._ffa_report_contradiction(S3, ROW_A, _report(near, S3), False) is None


def test_a_roster_difference_is_a_contradiction_either_way():
    short = {S1: ROW_A[S1], S3: ROW_A[S3]}
    assert main._ffa_report_contradiction(S3, ROW_A, _report(short, S3), False) is not None
    assert main._ffa_report_contradiction(S3, short, _report(ROW_A, S3), False) is not None


def test_the_detector_is_symmetric():
    # Whichever of the two verified rows had settled first, the other is a
    # contradiction: the detector reports a disagreement, it never ranks the
    # two accounts.
    assert main._ffa_report_contradiction(S3, ROW_A, _report(ROW_B, S1), False) is not None
    assert main._ffa_report_contradiction(S1, ROW_B, _report(ROW_A, S3), False) is not None


def test_a_same_room_second_report_is_compared_before_it_is_echoed():
    """The room id is "<photon room>_<HHmmss>_r<N>", so two clients of one game
    that started inside the same second build the SAME string. That report used
    to receive 200 with the stored result, uncompared."""
    src = inspect.getsource(main._ffa_replay_echo)
    compare = src.index("_ffa_prior_field_disagreement")
    echo = src.index("return await _ffa_match_echo")
    assert compare < echo
    assert "_ffa_record_and_refuse" in src
    # A roster that is not the recorded one is still refused WITHOUT a capture:
    # this runs above the endpoint's own roster validation, so capturing there
    # would be a write primitive for anyone holding the report secret.
    assert 'raise HTTPException(409, "Duplicate room id")' in src


# ── the partial-view refusal, and the skew it must not catch ──────────────

def test_an_all_zero_scoreboard_has_no_unique_round_maximum():
    """Control: shape-winner-gone. The shape a seat with empty per-game tables
    reports. It used to be a bare 400 above the lobby read — refused with
    nothing kept, which is the one outcome the July-30 rule exists to stop."""
    zeros = {S1: (0, 0, 0), S2: (0, 0, 0), S3: (0, 0, 0)}
    why = main._ffa_score_shape_error(_report(zeros, S1), 5, 3)
    assert why == "winner disagrees with the round tallies"


def test_a_report_short_of_the_score_target_is_refused():
    # 1/0/0 against first-to-5 is the relaunched-reporter shape: it HAS a
    # unique maximum, and is still not a complete game at either target.
    near_zero = {S1: (1, 2, 0), S2: (0, 0, 0), S3: (0, 0, 0)}
    why = main._ffa_score_shape_error(_report(near_zero, S1), 5, 3)
    assert why is not None and "complete game" in why


def test_a_complete_game_at_the_lobbys_frozen_target_is_accepted():
    assert main._ffa_score_shape_error(_report(ROW_A, S3), 5, 3) is None
    assert main._ffa_score_shape_error(_report(ROW_B, S1), 5, 3) is None


def test_a_complete_game_at_the_module_default_is_settled_in_a_skewed_lobby():
    """Control: shape-skew-refused. A client that missed the score-target room
    property plays to the module default and reports a REAL completed game.
    Refusing it left that player with the local result and no server match, no
    rating, no XP and no gold — a refusal costing more than the report it was
    easing (#430)."""
    assert main.FFA_ROUNDS_TO_WIN == 5
    # lobby froze 3; the report is a complete game to 5.
    assert main._ffa_score_shape_error(_report(ROW_A, S3), 3, 3) is None
    # ...and the endpoint settles it, naming the skew rather than refusing.
    src = _endpoint_src()
    assert "score-target skew" in src
    assert src.index("INSERT INTO ffa_matches") > src.index("score-target skew")


def test_a_game_at_neither_target_is_refused():
    # A lobby frozen at 8: seven rounds is neither its target nor the default.
    seven = {S1: (7, 16, 3), S2: (2, 5, 1), S3: (1, 3, 0)}
    why = main._ffa_score_shape_error(_report(seven, S1), 8, 3)
    assert why is not None and "ends at 8" in why


def test_the_points_ceiling_follows_the_target_the_game_ran_to():
    # A longer game honestly banks more; the ceiling is one of two SERVER-held
    # numbers (the frozen target, the module default) and never one the report
    # names.
    fat = dict(ROW_A, **{S1: (4, main._ffa_max_points(3, 5) + 1, 0)})
    assert main._ffa_score_shape_error(_report(fat, S3), 5, 3) == \
        "point tally above the game limit"
    assert main._ffa_score_shape_error(_report(ROW_A, S3), 3, 3) is None


def test_a_report_whose_accepted_response_was_lost_gets_the_stored_result():
    """The outbox retries a committed report under the SAME room id. It reaches
    the replay echo, the comparison finds its own stored values, and it gets
    200 with the recorded result — no second settlement, and nothing written.
    The comparison is what makes this safe to answer 200: the same client's
    retry agrees with itself by construction."""
    src = inspect.getsource(main._ffa_replay_echo)
    assert "photon_room_id = :room" in src
    assert "_ffa_match_echo" in src
    assert 'message="Already recorded"' in inspect.getsource(main._ffa_match_echo)
    # The retry runs above every quarantine branch of the endpoint, so a
    # committed report arriving after its lobby closed is echoed, not captured.
    esrc = _endpoint_src()
    assert esrc.index("_ffa_replay_echo") < esrc.index('lobby["status"] != "active"')


def test_the_closed_lobby_capture_gate_reads_the_same_win_invariant():
    """One definition of "this is a complete game", not two. An open-coded
    `max_rounds == _score_target` here would refuse to KEEP exactly the
    config-skew report the shape rule now settles (#279/#432)."""
    src = _endpoint_src()
    block = src[src.index("_bound = "):src.index('raise HTTPException(409, "Lobby is not active")')]
    assert "_ffa_score_shape_error" in block
    assert "max_rounds == _score_target" not in block


def test_the_shape_refusal_is_recorded_before_it_is_refused():
    src = _endpoint_src()
    block = src[src.index("_shape_error = "):src.index("# Rate ceiling:")]
    assert "_ffa_record_and_refuse" in block
    assert "score_shape_mismatch" in block
    # The bare 400 that ran above the lobby read is gone.
    assert 'HTTPException(400, "winner disagrees' not in src


def test_the_summed_rounds_floor_could_never_fire():
    # Recorded rather than shipped: the brief asked for sum(rounds_won) >=
    # score_target. The winner alone contributes the target on every report the
    # rule above admits, and rounds_won is non-negative, so such a check cannot
    # fail — and a check that cannot fail is worse than none (#342).
    for vec in (ROW_A, ROW_B):
        winner = max(vec, key=lambda s: vec[s][0])
        assert main._ffa_score_shape_error(_report(vec, winner), 5, 3) is None
        assert sum(r for r, _, _ in vec.values()) >= 5


def test_the_two_rules_that_could_not_fire_are_gone():
    src = inspect.getsource(main._ffa_score_shape_error)
    assert "rounds_won > score_target" not in src
    assert "round tally above the game limit" not in src


# ── a refusal that says "recorded" must have recorded ─────────────────────

class _FakeResult:
    def __init__(self, value=None):
        self._value = value

    def scalar(self):
        return self._value


class _FakeDb:
    """Enough AsyncSession for _quarantine_report: a scripted reply per
    statement, and a record of what it was asked."""

    def __init__(self, pending=0, insert_id=None, boom=False):
        self.pending = pending
        self.insert_id = uuid.uuid4() if insert_id == "new" else insert_id
        self.boom = boom
        self.committed = False
        self.statements = []

    async def rollback(self):
        return None

    async def commit(self):
        self.committed = True

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append(sql)
        if "pg_advisory_xact_lock" in sql:
            return _FakeResult(1)
        if "SELECT COUNT(*)" in sql:
            return _FakeResult(self.pending)
        if "INSERT INTO match_report_quarantine" in sql:
            if self.boom:
                raise RuntimeError("insert failed")
            return _FakeResult(self.insert_id)
        return _FakeResult(None)


def _capture(db):
    return asyncio.run(main._quarantine_report(
        db, mode="ffa", reason="r", status_code=409, payload={"a": 1},
        group_id=uuid.uuid4(), photon_room_id="rm_r1"))


def test_the_capture_says_which_of_the_four_things_happened():
    assert _capture(_FakeDb(insert_id="new")) == "recorded"
    # ON CONFLICT fired: this room's payload is already in the table. That is
    # the retry-idempotency, not a drop.
    assert _capture(_FakeDb(insert_id=None)) == "already"
    assert _capture(_FakeDb(pending=50)) == "quota"
    assert _capture(_FakeDb(boom=True)) == "failed"


def _refuse(capture_result):
    """_ffa_record_and_refuse with the capture's answer scripted."""
    async def fake_quarantine(db, **kw):
        return capture_result

    real = main._quarantine_report
    main._quarantine_report = fake_quarantine
    try:
        rep = types.SimpleNamespace(
            photon_room_id="rm_r1", reported_by_steam_id=S1,
            model_dump=lambda: {"a": 1})
        asyncio.run(main._ffa_record_and_refuse(
            None, report=rep, lobby_uuid=uuid.uuid4(),
            id_by_steam={S1: uuid.uuid4()}, reason="ffa_game_contradiction",
            why="w", detail="This game is already recorded"))
    finally:
        main._quarantine_report = real


def test_a_refusal_whose_capture_recorded_is_a_409():
    """Control: capture-always-ok."""
    for kept in ("recorded", "already"):
        with pytest.raises(main.HTTPException) as ex:
            _refuse(kept)
        assert ex.value.status_code == 409, kept


def test_a_refusal_whose_capture_did_not_record_is_not_a_409():
    # 409 is terminal for the client's outbox, so answering one over a capture
    # that hit the pending bound or raised would SPEND the report and lose it.
    # 503 is "could not judge this yet", which the same outbox retries.
    for kept in ("quota", "failed"):
        with pytest.raises(main.HTTPException) as ex:
            _refuse(kept)
        assert ex.value.status_code == 503, kept


def test_the_rj3_branches_never_answer_409_without_asking_the_capture():
    src = _endpoint_src()
    for reason in ("ffa_game_contradiction", "ffa_game_number_mismatch",
                   "score_shape_mismatch"):
        i = src.index(reason)
        window = src[max(0, i - 400):i + 400]
        assert "_ffa_record_and_refuse" in window, reason
    # ...and no branch of the endpoint writes a match or player row while
    # refusing.
    branch = src[src.index("_candidates = "):src.index("INSERT INTO ffa_matches")]
    for forbidden in ("UPDATE ffa_matches", "UPDATE players", "invalidated_at =",
                      "DELETE FROM"):
        assert forbidden not in branch, forbidden


# ── the migration, as text ────────────────────────────────────────────────

def test_the_migration_declares_the_column_the_code_binds_and_no_key():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS game_number SMALLINT" in sql
    assert "BEGIN;" in sql and "COMMIT;" in sql          # #340
    assert "BEFORE THE CODE" in sql.upper()
    # Acceptance bar: no dedup key was added or widened. A unique on
    # (lobby_id, game_number) would fold the 2026-08-07 pair, which means
    # picking one of two unreconciled accounts (#283).
    upper = sql.upper()
    assert "CREATE UNIQUE INDEX" not in upper
    assert "UNIQUE (" not in upper
    assert "DELETE FROM" not in upper and "DROP TABLE" not in upper


def test_the_migration_states_what_the_old_code_does_during_the_window():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "BEFORE INSERT" in sql
    assert "ffa_matches_derive_game_number" in sql
    # The claim the header makes has to be the one the trigger implements: a
    # writer that supplies no number still lands, numbered.
    fn = sql[sql.index("CREATE OR REPLACE FUNCTION"):sql.index("DROP TRIGGER")]
    assert "IF NEW.game_number IS NOT NULL THEN" in fn        # never overrides
    assert "room_tail" in fn and "sequence" in fn


def test_the_migration_makes_the_column_total_and_bounded():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "SET NOT NULL" in sql
    assert "CHECK (game_number BETWEEN 1 AND 999)" in sql
    # Provenance for every backfilled row: which rule gave it its number.
    assert "game_number_source" in sql


# ── live PostgreSQL ───────────────────────────────────────────────────────
# No silent skip. Unset DSN FAILS with the reason; FFA_TEST_PG_OPTOUT=1 is the
# explicit, visible way to run this file without a PostgreSQL.

DSN = os.environ.get("FFA_TEST_PG_DSN")
OPTOUT = os.environ.get("FFA_TEST_PG_OPTOUT")


def require_pg():
    if DSN:
        return DSN
    if OPTOUT:
        pytest.skip("FFA_TEST_PG_OPTOUT is set — live-PostgreSQL checks "
                    "deliberately not run in this invocation")
    pytest.fail(
        "FFA_TEST_PG_DSN is not set, so the production SQL in this file was "
        "never executed: the typed binds (SMALLINT, SMALLINT[]), the anchor's "
        "grouping, the prior-game lookup and migration 327 itself are all "
        "unverified. Set FFA_TEST_PG_DSN=postgresql+asyncpg://... to run them, "
        "or FFA_TEST_PG_OPTOUT=1 to say out loud that this run skips them.")


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
    kills INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (match_id, player_id)
);
"""

LOBBY = uuid.UUID("0ea879a4-ff42-44c4-9473-4c58f89ef934")
T0 = datetime(2026, 8, 7, 21, 15, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


async def _setup(rows):
    """rows: (room, game_number, seconds_after_T0, invalidated) tuples."""
    engine = create_async_engine(require_pg())
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


async def _prior(sm, gs):
    async with sm() as db:
        return (await db.execute(text(main._FFA_PRIOR_GAME_SQL),
                                 {"lid": LOBBY, "gs": list(gs)})).mappings().first()


def test_pg_a_second_row_for_one_game_is_not_the_next_games_anchor():
    """Control: anchor-per-row, anchor-includes-self."""
    require_pg()

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


def test_pg_a_low_number_late_in_a_sitting_cannot_widen_the_window():
    """The #283 direction. Control: anchor-less-than."""
    require_pg()

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


def test_pg_rows_with_no_derivable_number_still_count_as_earlier_games():
    """Migration 327 leaves no NULL behind, so this arm covers only a reader
    running ahead of the migration — and a row it cannot group must not fall
    out of the window entirely."""
    require_pg()

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


def test_pg_the_prior_lookup_asks_about_every_candidate_number():
    """The array bind is typed (`ANY(CAST(:gs AS SMALLINT[]))`) — an untyped
    list is the #275/#448 shape and aborts the transaction."""
    require_pg()

    async def go():
        engine, sm, _ = await _setup([
            ("rm_live_r1", 1, 686, False),
            ("rm_late_r1", 1, 743, False),
        ])
        try:
            return (await _prior(sm, [1]), await _prior(sm, [1, 2]),
                    await _prior(sm, [2, 3]))
        finally:
            await engine.dispose()
    one, one_and_two, neither = run(go())
    # ORDER BY ended_at: the row that settled first, deterministically. Both of
    # the verified pair are live — both settled, neither was reversed — so this
    # is a stable choice, not a claim that the later one is not live.
    assert one is not None and one["photon_room_id"] == "rm_live_r1"
    assert one_and_two is not None and one_and_two["photon_room_id"] == "rm_live_r1"
    assert neither is None


def test_pg_a_reused_invalidated_number_cannot_widen_the_window():
    """Control: prior-skips-invalidated. Game 2 was reversed by an admin. A
    report reusing number 2 must still FIND that row, because the anchor keeps
    excluding number 2 — a lookup that skipped it plus an anchor that excluded
    it removes the 700s that game consumed and meters the second report against
    the wider window."""
    require_pg()

    async def go():
        engine, sm, _ = await _setup([
            ("rm_a_r1", 1, 600, False),
            ("rm_b_r2", 2, 1300, True),          # reversed by an admin
        ])
        try:
            found = await _prior(sm, [2, 3])
            widened = await _anchor(sm, 2)       # if that report DID settle
            honest = await _anchor(sm, 3)
            return found, widened, honest
        finally:
            await engine.dispose()
    found, widened, honest = run(go())
    assert found is not None and found["photon_room_id"] == "rm_b_r2"
    assert found["invalidated_at"] is not None
    # The window the refusal protects: 700 seconds wider, and a wider window is
    # a larger paid_battles ceiling.
    assert honest - widened == timedelta(seconds=700)
    assert (main._ffa_paid_battles(400, (honest - T0).total_seconds(), 3)
            < main._ffa_paid_battles(400, (honest - widened).total_seconds()
                                     + (honest - T0).total_seconds(), 3))


def test_pg_the_recorded_vector_reads_back_for_the_comparison():
    require_pg()

    async def go():
        engine, sm, pids = await _setup([("rm_live_r1", 1, 686, False)])
        try:
            async with sm() as db:
                mid = (await db.execute(text(
                    "SELECT id FROM ffa_matches WHERE photon_room_id = 'rm_live_r1'"
                ))).scalar()
                for s, (r, p, k) in ROW_A.items():
                    await db.execute(text(
                        "INSERT INTO ffa_match_players (match_id, player_id,"
                        " rounds_won, points_total, kills)"
                        " VALUES (:m, :p, :r, :t, :k)"),
                        {"m": mid, "p": pids[s], "r": r, "t": p, "k": k})
                await db.commit()
                rows = (await db.execute(text(main._FFA_PRIOR_VECTOR_SQL),
                                         {"m": mid})).mappings().all()
            return {r["steam_id"]: (int(r["rounds_won"]), int(r["points_total"]),
                                    int(r["kills"])) for r in rows}
        finally:
            await engine.dispose()
    vec = run(go())
    assert vec == ROW_A
    assert main._ffa_report_contradiction(S3, vec, _report(ROW_B, S1), True) is not None
    assert main._ffa_report_contradiction(S3, vec, _report(ROW_A, S3), True) is None


# ── migration 327, EXECUTED ───────────────────────────────────────────────
# asyncpg's simple-query path runs a whole file (BEGIN/COMMIT and DO blocks
# included) in one call, which is what `psql -f` does on the box.

MIGRATION_FIXTURE = """
DROP TABLE IF EXISTS ffa_matches CASCADE;
CREATE TABLE ffa_matches (
    id UUID PRIMARY KEY,
    lobby_id UUID,
    photon_room_id VARCHAR(64) NOT NULL,
    player_count SMALLINT NOT NULL DEFAULT 3,
    ended_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    invalidated_at TIMESTAMPTZ,
    CONSTRAINT uq_ffa_match_room UNIQUE (photon_room_id)
);
INSERT INTO ffa_matches (id, lobby_id, photon_room_id, ended_at) VALUES
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000a1', 'rmA_211531_r1', '2026-08-07 21:15:31Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000a1', 'rmA_211532_r1', '2026-08-07 21:16:28Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000a1', 'rmA_212540_r2', '2026-08-07 21:25:40Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000b2', 'rmB_100000_r4', '2026-08-08 10:00:00Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000b2', 'rmB_101000_r0', '2026-08-08 10:10:00Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000b2', 'rmB_102000_r99999', '2026-08-08 10:20:00Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000b2', 'rmB_no_tail_here', '2026-08-08 10:30:00Z'),
  (gen_random_uuid(), NULL, 'orphan_room_no_tail', '2026-08-09 09:00:00Z');
"""

# The one edit that neuters the tail backfill without touching anything else:
# its own SET clause is the unique anchor.
_BACKFILL_ANCHOR = "       game_number_source = 'room_tail'\n WHERE game_number IS NULL"
_BACKFILL_NEUTERED = ("       game_number_source = 'room_tail'\n"
                      " WHERE FALSE AND game_number IS NULL")


async def _raw_pg():
    import asyncpg
    return await asyncpg.connect(require_pg().replace("+asyncpg", ""))


def test_pg_migration_327_numbers_every_row_and_rerunning_changes_nothing():
    require_pg()
    sql = MIGRATION.read_text(encoding="utf-8")

    async def go():
        conn = await _raw_pg()
        try:
            await conn.execute(MIGRATION_FIXTURE)
            await conn.execute(sql)
            first = await conn.fetch(
                "SELECT photon_room_id, game_number, game_number_source"
                "  FROM ffa_matches ORDER BY photon_room_id")
            await conn.execute(sql)                       # idempotence
            second = await conn.fetch(
                "SELECT photon_room_id, game_number, game_number_source"
                "  FROM ffa_matches ORDER BY photon_room_id")
            # The migration-first window: the OLD api's INSERT names no
            # game_number and must still land, numbered by the trigger.
            await conn.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id, ended_at)"
                " VALUES (gen_random_uuid(),"
                " '00000000-0000-0000-0000-0000000000a1', 'rmA_215000_r3',"
                " '2026-08-07 21:50:00Z')")
            await conn.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id, ended_at)"
                " VALUES (gen_random_uuid(),"
                " '00000000-0000-0000-0000-0000000000a1', 'rmA_no_tail',"
                " '2026-08-07 21:55:00Z')")
            old_api = await conn.fetch(
                "SELECT photon_room_id, game_number, game_number_source"
                "  FROM ffa_matches"
                " WHERE photon_room_id IN ('rmA_215000_r3', 'rmA_no_tail')"
                " ORDER BY photon_room_id")
            try:
                await conn.execute(
                    "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                    " ended_at, game_number) VALUES (gen_random_uuid(), NULL,"
                    " 'over_bound', NOW(), 1000)")
                over = "accepted"
            except Exception as ex:
                over = type(ex).__name__
            # NOT NULL, executed rather than grepped: with the trigger out of
            # the way there is nothing left to supply a number, and the column
            # itself has to be what refuses.
            await conn.execute("ALTER TABLE ffa_matches"
                               " DISABLE TRIGGER trg_ffa_matches_game_number")
            try:
                await conn.execute(
                    "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                    " ended_at) VALUES (gen_random_uuid(), NULL,"
                    " 'unnumbered', NOW())")
                unnumbered = "accepted"
            except Exception as ex:
                unnumbered = type(ex).__name__
            return first, second, old_api, over, unnumbered
        finally:
            await conn.close()

    first, second, old_api, over, unnumbered = run(go())
    by_room = {r["photon_room_id"]: (r["game_number"], r["game_number_source"])
               for r in first}
    # Usable tails taken as-is, including the two rows that share game 1.
    assert by_room["rmA_211531_r1"] == (1, "room_tail")
    assert by_room["rmA_211532_r1"] == (1, "room_tail")
    assert by_room["rmA_212540_r2"] == (2, "room_tail")
    assert by_room["rmB_100000_r4"] == (4, "room_tail")
    # Zero, over-domain and absent tails: the lobby's own ended_at sequence,
    # above the highest tail that lobby carries, so they cannot collide with it.
    assert by_room["rmB_101000_r0"] == (5, "sequence")
    assert by_room["rmB_102000_r99999"] == (6, "sequence")
    assert by_room["rmB_no_tail_here"] == (7, "sequence")
    # A row whose lobby row is gone (lobby_id NULL) still gets a number.
    assert by_room["orphan_room_no_tail"] == (1, "sequence")
    assert all(1 <= v[0] <= 999 for v in by_room.values())
    # Re-running is a no-op, row for row.
    assert [tuple(r) for r in first] == [tuple(r) for r in second]
    # The old api's unnumbered INSERT lands, numbered by both rules.
    got = {r["photon_room_id"]: (r["game_number"], r["game_number_source"])
           for r in old_api}
    assert got["rmA_215000_r3"] == (3, "room_tail")
    # ...and one without a tail takes the lobby's next free number, above the
    # 3 the row inserted just before it took from its own tail.
    assert got["rmA_no_tail"] == (4, "sequence")
    # The bound is the CHECK's, not SMALLINT's width.
    assert over == "CheckViolationError"
    # ...and the column is total, so no writer can leave a row unnumbered.
    assert unnumbered == "NotNullViolationError"


def test_pg_migration_327_post_check_fails_when_the_backfill_is_neutered():
    """The migration's own mutation control, as a test rather than a note in a
    handover file. Neuter the tail backfill and the post-check must RAISE and
    take the whole file down with it — a post-check that only counted NULLs
    would pass here, because the sequence arm fills them all in."""
    require_pg()
    sql = MIGRATION.read_text(encoding="utf-8")
    assert sql.count(_BACKFILL_ANCHOR) == 1
    neutered = sql.replace(_BACKFILL_ANCHOR, _BACKFILL_NEUTERED)

    async def go():
        conn = await _raw_pg()
        try:
            await conn.execute(MIGRATION_FIXTURE)
            try:
                await conn.execute(neutered)
                return "accepted"
            except Exception as ex:
                return str(ex)
        finally:
            await conn.close()

    why = run(go())
    assert "derivable _rN tail" in why, why


def test_the_neutered_control_is_exactly_one_predicate_away():
    """Negative control on the control (#391): the mutation must be the ONE
    edit, or a red result proves nothing about the post-check."""
    sql = MIGRATION.read_text(encoding="utf-8")
    neutered = sql.replace(_BACKFILL_ANCHOR, _BACKFILL_NEUTERED)
    diff = [(a, b) for a, b in zip(sql.splitlines(), neutered.splitlines())
            if a != b]
    assert len(diff) == 1
    assert re.match(r"^ WHERE game_number IS NULL$", diff[0][0])
    assert len(sql.splitlines()) == len(neutered.splitlines())
