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
the report's — and the report room id's `_rN` tail has to AGREE with it. A tail
naming a number the lobby already holds is compared against that row; any other
disagreeing tail is refused and recorded. Nothing is ever stored under a number
the report did not name, which is what keeps the already-recorded lookup able
to find a repeat: the stored number and the named number are one number. Every
test below whose name says what a misreported number "gains" answers: nothing.

Round 2 ACCEPTED an ahead tail and stored the lobby's slot anyway. The repeat
that allowed is pinned here by name
(test_an_ahead_tail_is_refused_because_accepting_it_let_one_game_settle_twice):
the row for the game the client calls K sits at slot N, so the second client of
that same game finds neither K nor N+1 and settles the same physical game
again, rated and paid twice.

THE SECOND RULE: a game played to a target the lobby did not freeze settles,
but not with the frozen target's economics — its wagers were priced by
_ffa_field_odds for the frozen race length, so they are REFUNDED, and its
Glicko weight takes the length actually played. The row records both numbers.

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

Named mutation controls, each applied to a copy-aside of the file, run RED, and
restored from the copy (never `git checkout --`, #290). Twenty-three from round
2, plus round 3's, which are marked (r3) and were run as a batch — all KILLED:

  anchor-per-row           _FFA_PACE_ANCHOR_SQL: MIN(ended_at) -> MAX(ended_at)
  anchor-includes-self     _FFA_PACE_ANCHOR_SQL: IS DISTINCT FROM CAST(:g AS
                           SMALLINT) -> IS NOT NULL
  anchor-less-than         _FFA_PACE_ANCHOR_SQL: IS DISTINCT FROM -> <
  prior-skips-invalidated  _FFA_PRIOR_GAME_SQL: add `AND invalidated_at IS NULL`
  prior-tail-only          the endpoint's _candidates: drop _expected_game
  number-from-the-tail     the endpoint: _game_number = _room_tail
  number-rule-gone         _ffa_game_number_refusal: first line -> `return None`
  tail-ahead-accepted (r3) _ffa_game_number_refusal: drop the `tail > expected`
                           arm, i.e. round 2's behaviour restored. Run against
                           the named test AND the enumeration table.
  skew-keeps-frozen-weight (r3)  the endpoint: _ffa_rating_deltas(...,
                           _score_target)
  skew-pays-its-wagers (r3)  the endpoint: settle this game's wagers on a skew
                           instead of refunding them
  skew-not-recorded (r3)   the endpoint's INSERT: drop the two target binds
  closure-reads-the-room (r3)  _reconcile_ffa_lobby_bets: back to the `_rN` LIKE
  history-reads-the-room (r3)  get_player_bets' discriminator: back to the LIKE
  conflict-is-always-already (r3)  _quarantine_report: return "already" on any
                           ON CONFLICT, without comparing the stored payload
  variant-detail-silent (r3)  _ffa_record_and_refuse: drop the variant suffix
  replay-refusal-uncaptured (r3)  _ffa_replay_echo's roster branch back to a
                           bare 409
  game-limit-uncaptured (r3)  the game-limit branch back to a bare 409
  room-race-spends-the-report (r3)  the unique-violation fallback back to 409
  closed-lobby-one-answer (r3)  the closed-lobby branch: one 409 for all three
  optout-any-nonempty (r3)  _optout -> bool(raw), i.e. "0" opts out again
  lobby-lock-no-for-update (r3)  the endpoint's lobby read: drop FOR UPDATE
  trigger-clamps-999 (r3)  327: the sequence arm back to LEAST(tail, 999)
  postcheck-sequence-only (r3)  327: the tail assertion back to
                           `AND game_number_source = 'sequence'`
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
import json
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


def test_every_surface_that_names_a_game_reads_the_column_not_the_room_string():
    """Controls: closure-reads-the-room, and the two history surfaces.

    Four places used to re-derive a game's identity from the report room id.
    Each one is a second derivation of the thing the column exists to hold, and
    each could disagree with the row it was describing: the closure reconcile
    would settle one game's stakes against another game's winner, and the two
    history surfaces would show them under the wrong game. The parse survives
    in exactly ONE place — the endpoint's own cross-check of the tail against
    the lobby's slot, which is the comparison, not a source."""
    whole = pathlib.Path(main.__file__).read_text(encoding="utf-8")
    # The terminal bet resolution for a closing lobby.
    rec = inspect.getsource(main._reconcile_ffa_lobby_bets)
    assert "photon_room_id LIKE" not in rec
    assert "game_number = CAST(:g AS SMALLINT)" in rec
    # The bet-history surface's settlement-cause discriminator.
    assert "fm2.game_number = fb.game_number" in whole
    assert "fm2.photon_room_id LIKE" not in whole
    # ...and no LIKE building an _rN suffix survives anywhere in the module.
    assert "_r' || " not in whole and "'%!_r'" not in whole
    assert "%\\\\_r" not in whole
    # The recent-matches panel keys its bet list on the row's own number.
    assert 'gno = int(r["game_number"])' in whole
    # One CALL of the room-id parse, and it is the endpoint's cross-check. (The
    # other two occurrences are the def itself and the refusal rule's docstring
    # naming its own argument.)
    calls = [ln for ln in whole.splitlines()
             if "_ffa_room_game_no(" in ln
             and not ln.lstrip().startswith(("def ", "#", "`", "-"))
             and "`tail` is" not in ln]
    assert calls == ['    _room_tail = _ffa_room_game_no(report.photon_room_id)']


def test_the_candidate_set_covers_both_the_slot_and_the_room_tail():
    """Control: prior-tail-only. The lookup has to ask about the slot this
    report would consume AND the game its own room id names — the first stops
    a report renaming its game to dodge the comparison, the second catches the
    second client of one game, whose counter still says N while the lobby has
    moved to N+1. The tail arm is only able to find that row because the row's
    number IS its tail; that is the equality _ffa_game_number_refusal keeps."""
    src = _endpoint_src()
    cand = src[src.index("_candidates = "):src.index("_prior_game = ")]
    assert "_expected_game" in cand and "_room_tail" in cand
    assert "FFA_GAME_NUMBER_MAX" in cand          # out-of-domain tails excluded
    assert '"gs": _candidates' in src


# ── what a misreported number gains: nothing ──────────────────────────────

def test_a_number_matching_the_lobbys_next_game_is_accepted():
    assert main._ffa_game_number_refusal(4, 4) is None


def test_an_ahead_tail_is_refused_because_accepting_it_let_one_game_settle_twice():
    """Control: tail-ahead-accepted.

    Round 2 accepted a tail ahead of the lobby and stored `expected` anyway.
    Walk what that bought, with the numbers: the lobby is on slot 3, a client
    whose counter has drifted to 4 reports its game, and the row for "game 4"
    is written at slot 3. games_played becomes 3, so the lobby is now on 4. The
    SECOND client of that same game reports — same physical game, its own room
    string, its own tail of 4. The lookup asks for {4, 4}; the row that holds
    this game is at 3; nothing is found; it settles as game 4. One game, two
    full settlements, two ratings, two payouts — which is the 2026-08-07 defect
    this whole file exists to close, reintroduced by the acceptance.

    Refusing is what makes the stored number and the named number one number,
    so the lookup can never miss the repeat."""
    assert main._ffa_game_number_refusal(4, 3) is not None
    assert main._ffa_game_number_refusal(9, 4) is not None
    assert main._ffa_game_number_refusal(main.FFA_GAME_NUMBER_MAX, 1) is not None
    # The refusal names the number an honest drifted client should be using.
    assert "expected_game=3" in main._ffa_game_number_refusal(4, 3)
    # ...and the one tail that is not refused is the equal one.
    assert main._ffa_game_number_refusal(3, 3) is None


def test_a_lower_number_with_no_recorded_game_is_refused():
    why = main._ffa_game_number_refusal(2, 5)
    assert why is not None and "expected_game=5" in why


@pytest.mark.parametrize("tail,expected,gains", [
    (4, 4, "the lobby's own slot, which it would have had anyway"),
    (9, 4, "nothing: refused and recorded (ahead of the sitting)"),
    (2, 5, "nothing: refused and recorded (behind, no row)"),
    (0, 1, "nothing: refused and recorded (zero)"),
    (None, 1, "nothing: refused and recorded (no tail at all)"),
    (1000, 1, "nothing: refused and recorded (over the bound)"),
    (99999, 7, "nothing: refused and recorded (over the bound)"),
])
def test_what_each_misreported_tail_gains(tail, expected, gains):
    """The enumeration the acceptance bar asks for, as one table. Every answer
    but the equality is a refusal, and a refusal settles nothing, pays nothing,
    rates nothing and moves nobody else's game.

    The two answers NOT in this table are the reused ones — a tail naming a
    number this lobby already holds, live or admin-reversed. Those never reach
    this rule at all: the already-recorded lookup finds the row first and the
    report is compared against it, which is
    test_the_candidate_set_covers_both_the_slot_and_the_room_tail and
    test_pg_a_reused_invalidated_number_cannot_widen_the_window."""
    why = main._ffa_game_number_refusal(tail, expected)
    if tail == expected:
        assert why is None, gains
    else:
        assert why is not None, gains


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
    # A roster that is not the recorded one is refused — and its payload is
    # KEPT now, like every other terminal refusal on this path. Round 2 left
    # it bare on the capture-before-binding argument, which weighed the flood
    # a capture could produce (quota-bounded) against spending a report
    # outright (unbounded loss), and weighed the wrong one (#430).
    assert 'raise HTTPException(409, "Duplicate room id")' not in src
    assert '"ffa_replay_roster_mismatch"' in src
    assert '"ffa_room_other_lobby"' in src
    assert src.count("_ffa_record_and_refuse") == 3


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
    # DISTINCT values, or this test passes with the arm deleted: the lobby froze
    # 3 and the report is a complete game to 5. (Round 2's version asked about a
    # lobby frozen at 5, where the two admissible values coincide and removing
    # the second one changed nothing.)
    assert main._ffa_score_shape_error(_report(ROW_A, S3), 3, 3) is None
    assert max(r for r, _, _ in ROW_A.values()) == 5 != 3
    # ...and the endpoint settles it, naming the skew rather than refusing.
    src = _endpoint_src()
    assert "score-target skew" in src
    assert src.index("INSERT INTO ffa_matches") > src.index("score-target skew")


# ── a skewed game is settled, but not with the frozen target's economics ──

def test_the_frozen_and_the_played_target_are_two_different_prices():
    """The fact the refund exists for. _ffa_field_odds' own docstring says race
    length changes true win probabilities, so a wager placed on a first-to-3
    field is not the same wager on a first-to-5 one — and the bettor agreed to
    the price they were shown, which was the frozen lobby's."""
    field = [(S1, 1500.0, 60.0), (S2, 1200.0, 60.0), (S3, 1800.0, 60.0)]
    short = main._ffa_field_odds(field, 3)
    long_ = main._ffa_field_odds(field, 5)
    assert short != long_
    # ...and the direction is the one that makes a mispriced payout a real
    # money move: a longer race is safer for the favourite, so their odds drop.
    assert long_[S3] < short[S3]


def test_a_skewed_game_refunds_its_wagers_instead_of_paying_frozen_prices():
    """Control: skew-pays-its-wagers. The stakes come back; they are never paid
    at a price for a race that was not run, and never kept either."""
    src = _endpoint_src()
    assert "_target_skew = _played_target != int(_score_target)" in src
    bets = src[src.index("game_no = _game_number"):src.index("UPDATE ffa_lobbies SET games_played")]
    assert "if _target_skew:" in bets
    assert '_refund_ffa_lobby_bets(db, lobby_uuid, "score_target_skew"' in bets
    assert "game_number=game_no" in bets
    # ...and this game's own settle is the branch that does NOT run.
    assert "if not _target_skew:" in bets
    settle = bets.index("_settle_ffa_bets_for_game(db, lobby_uuid, game_no")
    assert bets.index("if not _target_skew:") < settle
    # The refund is idempotent and moves gold as a DELTA (#326), so a retry,
    # the straggler pass and the closure reconcile can all cross it.
    ref = inspect.getsource(main._refund_ffa_lobby_bets)
    assert "settled_at IS NULL RETURNING id" in ref
    assert "gold_spent = GREATEST(0, COALESCE(gold_spent,0) - :amt)" in ref
    # ...and because the refund stamps settled_at, every later pass skips it:
    # both the straggler query and the closure reconcile select on IS NULL.
    assert "settled_at IS NULL AND game_number < :g" in src
    assert "settled_at IS NULL ORDER BY game_number" in \
        inspect.getsource(main._reconcile_ffa_lobby_bets)


def test_a_skewed_game_is_rated_with_the_weight_of_the_target_it_was_played_to():
    """Control: skew-keeps-frozen-weight. w(N) is the information weight of the
    result, and the result is evidence about the race that was actually run."""
    src = _endpoint_src()
    assert "_ffa_rating_deltas([p.steam_id for p in report.players]," in src
    assert "pre, _played_target)" in src
    assert "pre, _score_target)" not in src
    # The weight really does move between the two targets, or the control above
    # would redden nothing: w(3) = 0.5 against w(5) = 1.0.
    placements = {S1: 2, S2: 3, S3: 1}
    pre = {s: (1500.0, 200.0, 0.06) for s in (S1, S2, S3)}
    at3 = main._ffa_rating_deltas(list(pre), frozenset(), placements, pre, 3)
    at5 = main._ffa_rating_deltas(list(pre), frozenset(), placements, pre, 5)
    assert at3[S3][0] != at5[S3][0]
    assert abs(at5[S3][0] - 1500.0) > abs(at3[S3][0] - 1500.0)


def test_the_match_row_records_both_targets():
    src = _endpoint_src()
    cols = src[src.index("INSERT INTO ffa_matches"):src.index("VALUES", src.index("INSERT INTO ffa_matches"))]
    assert "score_target_frozen" in cols and "score_target_played" in cols
    assert '"stf": int(_score_target), "stp": _played_target,' in src
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS score_target_frozen SMALLINT" in sql
    assert "ADD COLUMN IF NOT EXISTS score_target_played SMALLINT" in sql


def test_the_played_target_is_never_a_number_the_report_chose():
    """Both admissible values are SERVER-held — the lobby's frozen target and
    the module default — so `_played_target` can only ever be one of two
    numbers the report did not pick, whatever it tallies."""
    src = _endpoint_src()
    assert "_played_target = int(max_rounds)" in src
    # max_rounds has been through the shape rule by then, which admits exactly
    # those two values and refuses everything else.
    assert src.index("_shape_error = ") < src.index("_played_target = ")
    shape = inspect.getsource(main._ffa_score_shape_error)
    assert "admissible = (int(score_target), int(FFA_ROUNDS_TO_WIN))" in shape
    assert main._ffa_score_shape_error(_report({S1: (7, 16, 3), S2: (2, 5, 1),
                                                S3: (1, 3, 0)}, S1), 8, 3) is not None


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
    block = src[src.index("_roster_bound = "):src.index('detail="Lobby is not active")')]
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

    def __init__(self, pending=0, insert_id=None, boom=False, stored=None):
        self.pending = pending
        self.insert_id = uuid.uuid4() if insert_id == "new" else insert_id
        self.boom = boom
        self.stored = stored           # what (mode, room) already holds
        self.committed = False
        self.statements = []
        self.inserts = 0

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
        if "SELECT payload FROM match_report_quarantine" in sql:
            return _FakeResult(self.stored)
        if "INSERT INTO match_report_quarantine" in sql:
            if self.boom:
                raise RuntimeError("insert failed")
            self.inserts += 1
            return _FakeResult(self.insert_id)
        return _FakeResult(None)


PAYLOAD = {"a": 1, "players": [{"steam_id": S1, "rounds_won": 5}]}
OTHER = {"a": 1, "players": [{"steam_id": S1, "rounds_won": 0}]}


def _capture(db, payload=None):
    return asyncio.run(main._quarantine_report(
        db, mode="ffa", reason="r", status_code=409,
        payload=PAYLOAD if payload is None else payload,
        group_id=uuid.uuid4(), photon_room_id="rm_r1"))


def test_the_capture_says_which_of_the_five_things_happened():
    assert _capture(_FakeDb(insert_id="new")) == "recorded"
    # ON CONFLICT fired AND the stored payload is this same report: the
    # retry-idempotency, not a drop.
    assert _capture(_FakeDb(insert_id=None,
                            stored=json.dumps(PAYLOAD))) == "already"
    assert _capture(_FakeDb(pending=50)) == "quota"
    assert _capture(_FakeDb(boom=True)) == "failed"


def test_a_distinct_account_of_a_captured_room_is_compared_and_kept():
    """Control: conflict-is-always-already.

    "Same room id" is not "same report": the report room id is
    "<photon room>_<HHmmss>_r<N>", so two clients of one game that started
    inside the same second build the SAME string. Answering "already" without
    looking dropped the second account while its reporter was told the server
    had kept the report — and a 409 is terminal, so that payload was gone."""
    db = _FakeDb(insert_id=None, stored=json.dumps(OTHER))
    assert _capture(db) == "variant"
    # It was COMPARED (the stored payload was read back)...
    assert any("SELECT payload FROM match_report_quarantine" in s
               for s in db.statements)
    # ...and RECORDED: a second insert, carrying a NULL room so the partial
    # unique index that makes an honest retry idempotent still does.
    assert db.inserts == 2
    variant = [s for s in db.statements
               if "INSERT INTO match_report_quarantine" in s][-1]
    assert ":rep, :pids, CAST(:pl AS JSONB))" in variant
    assert ":g, NULL, :rep" in variant
    # The room is not lost — the payload itself names it.
    assert "photon_room_id" in main.FfaMatchReport.model_fields


def test_a_variant_row_is_as_actionable_in_the_admin_queue_as_any_other():
    """Keeping a payload nobody can act on would be half a fix. The queue's
    three endpoints key on the row's id, its mode, its player_ids and its
    created_at — never on photon_room_id, which the list only renders."""
    listing = inspect.getsource(main.admin_list_quarantine)
    assert "q.status = 'pending'" in listing
    assert "photon_room_id = " not in listing
    for fn in (main.admin_accept_quarantine, main.admin_discard_quarantine):
        src = inspect.getsource(fn)
        assert "WHERE id=CAST(:qid AS UUID)" in src or \
               "WHERE id = CAST(:qid AS UUID)" in src
        assert "photon_room_id" not in src


def test_an_encoding_difference_is_not_a_distinct_account():
    """Compared as VALUES, not as text: key order and separator spacing are not
    two different reports, and calling them different would keep a duplicate
    row for every honest retry."""
    reordered = json.dumps({"players": PAYLOAD["players"], "a": 1},
                           separators=(", ", ": "))
    assert _capture(_FakeDb(insert_id=None, stored=reordered)) == "already"
    # A decoded object (a driver with a JSON codec) reads the same way.
    assert _capture(_FakeDb(insert_id=None, stored=dict(PAYLOAD))) == "already"


def test_an_unreadable_stored_payload_keeps_the_new_one():
    """The conservative direction: a comparison nobody could make must not be
    the reason a report is discarded."""
    assert _capture(_FakeDb(insert_id=None, stored=None)) == "variant"
    assert _capture(_FakeDb(insert_id=None, stored="{not json")) == "variant"


def _refuse(capture_result, status=409):
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
            why="w", detail="This game is already recorded", status=status))
    finally:
        main._quarantine_report = real


def test_a_refusal_whose_capture_recorded_is_terminal():
    """Control: capture-always-ok."""
    for kept in ("recorded", "already", "variant"):
        with pytest.raises(main.HTTPException) as ex:
            _refuse(kept)
        assert ex.value.status_code == 409, kept
    # The one caller that refuses with 403 (a downgraded signature) gets 403,
    # not a 409 — the status is the reason, and the 503 arm below is the report.
    with pytest.raises(main.HTTPException) as ex:
        _refuse("recorded", status=403)
    assert ex.value.status_code == 403


def test_a_refusal_whose_capture_did_not_record_is_not_terminal():
    # 409 (and 403) are terminal for the client's outbox, so answering one over
    # a capture that hit the pending bound or raised would SPEND the report and
    # lose it. 503 is "could not judge this yet", which the same outbox retries.
    for kept in ("quota", "failed"):
        for status in (409, 403):
            with pytest.raises(main.HTTPException) as ex:
                _refuse(kept, status=status)
            assert ex.value.status_code == 503, (kept, status)


def test_a_refusal_over_a_variant_capture_says_which():
    """The reporter is told its account is not the one that was already on
    file, instead of being told "already recorded" about a report that said
    something else."""
    with pytest.raises(main.HTTPException) as ex:
        _refuse("variant")
    assert "different account of this room" in ex.value.detail
    with pytest.raises(main.HTTPException) as plain:
        _refuse("recorded")
    assert "different account" not in plain.value.detail


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


def _terminal_raises(src):
    """Every `raise HTTPException(<terminal>, ...)` literal in a source blob."""
    return re.findall(r"raise HTTPException\((4\d\d), ([^\n]*)", src)


def test_no_terminal_refusal_on_the_ffa_report_path_is_answered_over_nothing():
    """The whole class, not the two lines the last round named (#432).

    A 4xx is terminal for the client's outbox, so the report is spent either
    way. Every one of them on this path therefore has to be one of exactly
    three things: a capture that was STATUS-CHECKED (so it is a 503 when
    nothing was kept), an INTEGRITY refusal the quarantine table may not hold
    (bad signature, unknown player, malformed ids — capturing those makes the
    table an unauthenticated write primitive), or an UNBOUND payload that is
    not evidence about this lobby's game and is refused before binding.

    The list below is the whole enumeration, by message. Adding a terminal
    refusal without deciding which of the three it is fails this test."""
    src = _endpoint_src() + inspect.getsource(main._ffa_replay_echo)
    # Refusals that may not be captured, with the reason each one may not.
    integrity = {
        '"Invalid FFA match signature")': "HMAC",
        '"Invalid lobby_id format")': "unparseable id",
        '"Need at least two distinct players")': "malformed roster",
        '"Winner is not among the players")': "malformed roster",
        '"Reporter is not a participant")': "malformed roster",
        '"photon_room_id is required")': "malformed room id",
        '"One or more players not registered")': "unknown player",
        '"Lobby not found")': "no row to bind to",
    }
    unbound = {
        '"Report must cover exactly the lobby roster")': "roster binding",
        '"Report player count does not match the lobby")': "roster binding",
    }
    for status, rest in _terminal_raises(src):
        key = rest.strip()
        if key in integrity or key in unbound:
            continue
        if key.startswith('f"Slot mismatch'):
            continue
        raise AssertionError(
            f"terminal HTTP {status} answered without a kept record: {key}")
    # ...and the captures that DO stand behind a terminal answer all run
    # through the one helper that checks whether the capture happened.
    for reason in ('"ffa_room_other_lobby"', '"ffa_replay_roster_mismatch"',
                   '"ffa_lobby_no_roster"', '"lobby_game_limit"',
                   '"v1_canonical_downgrade"', 'f"lobby_{lobby[\'status\']}"'):
        i = src.index(reason)
        assert "_ffa_record_and_refuse" in src[max(0, i - 400):i], reason
    # The bare _quarantine_report call, whose answer nobody read, is gone from
    # this endpoint entirely.
    assert "_quarantine_report(" not in src


def test_a_room_whose_row_is_not_visible_yet_is_retried_not_spent():
    """The unique fired, so a row exists — but the writing transaction has not
    committed, so the lookup cannot see it. That is a race, not a verdict."""
    src = _endpoint_src()
    blk = src[src.index("uq_ffa_match_room"):src.index("Pairwise Glicko")]
    assert "HTTPException(503" in blk
    assert 'HTTPException(409, "Duplicate room id")' not in blk


def test_a_closed_lobbys_unbound_report_is_not_answered_as_a_lifecycle_refusal():
    """Three different answers, told apart. Round 2 gave a roster that does not
    bind, a shape that does not hold and a genuinely closed lobby the SAME
    terminal 409, and kept a record for only the third."""
    src = _endpoint_src()
    blk = src[src.index('if lobby["status"] != "active":'):
              src.index("# Roster validation")]
    assert "_roster_bound" in blk
    assert 'raise HTTPException(403, "Report must cover exactly the lobby roster")' in blk
    assert blk.count("_ffa_record_and_refuse") == 2
    assert "score_shape_mismatch" in blk
    assert 'reason=f"lobby_{lobby[\'status\']}"' in blk


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


# ── comments that are claims ──────────────────────────────────────────────
# A comment asserting a guarantee is a claim about the whole state space, and
# it is usually written from the one state its author had in mind (#351/#277).
# Each of these was found false or overstated and is pinned here to what the
# code below it actually does.

def test_the_anchor_does_not_claim_the_table_holds_no_repeat():
    """It does hold one — the 2026-08-07 pair, deliberately preserved, and the
    migration backfills historical rows from their tails rather than from a
    counter. The anchor handles that with GROUP BY instead of assuming it
    away, and the note says so."""
    src = pathlib.Path(main.__file__).read_text(encoding="utf-8")
    note = src[src.index("# ── Pace anchor:"):src.index("_FFA_PACE_ANCHOR_SQL = ")]
    assert "no gap and no repeat by construction" not in note
    assert "That is a statement about NEW rows" in note
    assert "GROUP BY game_number" in main._FFA_PACE_ANCHOR_SQL


def test_the_echo_names_the_two_helpers_that_actually_run_before_it():
    """There is no `_ffa_prior_disagreement`; the roster question and the field
    question are two helpers, kept apart on purpose."""
    doc = inspect.getsource(main._ffa_match_echo)
    assert "_ffa_prior_roster_matches" in doc
    assert "_ffa_prior_field_disagreement" in doc
    assert not hasattr(main, "_ffa_prior_disagreement")
    for caller in (main._ffa_replay_echo, _endpoint_src()):
        src = caller if isinstance(caller, str) else inspect.getsource(caller)
        assert src.index("_ffa_prior_roster_matches") < src.index("_ffa_match_echo")


def test_the_capture_note_no_longer_calls_every_conflict_a_retry():
    doc = inspect.getsource(main._quarantine_report)
    assert "the same report under the same room id is the same report" not in doc
    assert "byte-identical" in doc or "says something DIFFERENT" in doc
    assert '"variant"' in doc


def test_the_shutout_note_no_longer_infers_the_target_from_the_tally():
    """The shape rule admits a game played to the module default in a lobby
    frozen at something else, so `winner.rounds_won == 5` and
    `_score_target == 5` are two different claims."""
    src = _endpoint_src()
    i = src.index("ffa_shutout_3")
    note = src[max(0, i - 1400):i]
    assert "is equivalent to" not in note
    assert "NOT the same claim" in note


def test_the_migration_header_says_the_tail_has_to_agree():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "HAS TO AGREE" in sql
    assert "refused and kept for review" in sql.replace("\n-- ", " ")
    # Provenance documentation covers the writer rows and states what the
    # trigger's sequence arm actually computes.
    assert "writer = the inserting statement supplied it" in sql
    assert "one above the lobby''s highest number for the trigger" in sql
    assert "next free number" not in sql


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


def _optout(raw) -> bool:
    """Is FFA_TEST_PG_OPTOUT an actual opt-out?

    `if os.environ.get(...)` is true for "0", "false", "no" and "off" — so a
    run that meant to SAY it was not opting out would have opted out silently,
    which is the whole failure mode this gate exists to prevent (#438). Only
    an affirmative word counts, and an unrecognised value is not an opt-out
    either: the live checks then FAIL and name the DSN, which is the direction
    that cannot hide."""
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


OPTOUT = _optout(os.environ.get("FFA_TEST_PG_OPTOUT"))


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


@pytest.mark.parametrize("raw,opts_out", [
    ("1", True), ("true", True), ("TRUE", True), (" yes ", True), ("on", True),
    ("0", False), ("false", False), ("no", False), ("off", False),
    ("", False), (None, False), ("maybe", False),
])
def test_only_an_affirmative_opt_out_turns_the_live_checks_into_skips(raw, opts_out):
    """A meta-test on the gate itself: `if os.environ.get(...)` treated "0" and
    "false" as opt-outs, so a run that said it was NOT skipping skipped. An
    unrecognised value is not an opt-out either — the live checks fail and name
    the DSN, which is the direction that cannot pass unnoticed."""
    assert _optout(raw) is opts_out


def test_the_live_checks_cannot_be_skipped_by_a_missing_dsn_alone():
    """Control: the round-1 finding that no meta-test reddens if silent
    skipping comes back. require_pg's own source must fail, not skip, when the
    DSN is unset and nobody asked to go without one."""
    src = inspect.getsource(require_pg)
    assert "pytest.fail(" in src
    # No decorator can quietly take the live tests out of a run: pytest's own
    # marker registry for this module carries no skip mark.
    mod = sys.modules[__name__]
    for name in dir(mod):
        fn = getattr(mod, name)
        if callable(fn) and name.startswith("test_pg_"):
            marks = {m.name for m in getattr(fn, "pytestmark", [])}
            assert "skipif" not in marks and "skip" not in marks, name
    # ...and it really does fail: run it with both variables cleared.
    saved_dsn, saved_opt = globals()["DSN"], globals()["OPTOUT"]
    globals()["DSN"], globals()["OPTOUT"] = None, False
    try:
        with pytest.raises(BaseException) as ex:
            require_pg()
        assert "Failed" in type(ex.value).__name__
        assert "FFA_TEST_PG_DSN" in str(ex.value)
        # And with the opt-out set it is a Skipped, not a Failed.
        globals()["OPTOUT"] = True
        with pytest.raises(BaseException) as sk:
            require_pg()
        assert "Skipped" in type(sk.value).__name__
    finally:
        globals()["DSN"], globals()["OPTOUT"] = saved_dsn, saved_opt


SCHEMA = """
DROP TABLE IF EXISTS ffa_match_players;
DROP TABLE IF EXISTS ffa_matches;
DROP TABLE IF EXISTS ffa_lobbies;
DROP TABLE IF EXISTS players;

CREATE TABLE players (
    id UUID PRIMARY KEY,
    steam_id TEXT NOT NULL UNIQUE
);
CREATE TABLE ffa_lobbies (
    id UUID PRIMARY KEY,
    games_played SMALLINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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


async def _setup(rows, games_played=None):
    """rows: (room, game_number, seconds_after_T0, invalidated) tuples."""
    engine = create_async_engine(require_pg())
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        for stmt in [s for s in SCHEMA.split(";") if s.strip()]:
            await conn.execute(text(stmt))
        if games_played is not None:
            await conn.execute(text(
                "INSERT INTO ffa_lobbies (id, games_played, created_at)"
                " VALUES (:i, :g, CAST(:t AS TIMESTAMPTZ))"),
                {"i": LOBBY, "g": int(games_played), "t": T0})
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


async def _unwedge(conn):
    """A migration that RAISES does so inside its own BEGIN, so the connection
    is left in an aborted transaction block and every later statement is
    ignored. The tests that assert on a refusal keep using the connection
    afterwards, so they end that block first."""
    try:
        await conn.execute("ROLLBACK")
    except Exception:
        pass


# ── two sessions, one lobby ───────────────────────────────────────────────

def _production_sql(pattern: str) -> str:
    """One of submit_ffa_match's OWN statement literals, with its named bind
    rewritten for asyncpg's positional form.

    The point of lifting it rather than retyping it (#391): the test below then
    executes the real lock, so deleting `FOR UPDATE` from the endpoint reddens
    it. A test carrying its own copy of the SQL measures its own copy."""
    m = re.search(pattern, _endpoint_src())
    assert m, f"the endpoint no longer carries a statement matching {pattern}"
    return m.group(1).replace(":lid", "$1")


def test_pg_two_reports_for_one_lobby_cannot_settle_the_same_number():
    """The concurrency bar, on two real connections against real rows.

    Report A takes the lobby row FOR UPDATE and derives `games_played + 1`.
    Report B, arriving while A is still open, must WAIT on that row — and when
    it is let through it must RE-READ, not reuse the value it would have seen
    (#208: the second half of a split operation working from a snapshot is how
    a settled row gets acted on twice). The three things asserted are that B
    blocked, that B's derived number moved, and that B cannot settle A's number
    even if it tries: the endpoint's own already-recorded lookup finds A's row
    for it, which is the comparison path, not a second settlement.

    Control (hand-run): delete `FOR UPDATE` from the endpoint's lobby read and
    B returns immediately with games_played = 0, deriving 1 exactly as A did."""
    require_pg()
    lock_sql = _production_sql(r'"(SELECT \* FROM ffa_lobbies WHERE id = :lid[^"]*)"')
    incr_sql = _production_sql(
        r'"(UPDATE ffa_lobbies SET games_played = games_played \+ 1[^"]*)"')

    async def go():
        engine, sm, pids = await _setup([], games_played=0)
        a = await _raw_pg()
        b = await _raw_pg()
        try:
            await b.execute("SET lock_timeout = '10s'")
            tx_a = a.transaction()
            await tx_a.start()
            row_a = await a.fetchrow(lock_sql, LOBBY)
            expected_a = int(row_a["games_played"]) + 1

            tx_b = b.transaction()
            await tx_b.start()
            waiting = asyncio.create_task(b.fetchrow(lock_sql, LOBBY))
            await asyncio.sleep(0.5)
            blocked = not waiting.done()

            # A settles its game and advances the sitting, in its own
            # transaction, exactly as the endpoint does.
            await a.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                " winner_id, ended_at, game_number) VALUES"
                " ($1, $2, $3, $4, NOW(), $5)",
                uuid.uuid4(), LOBBY, f"rm_211531_r{expected_a}", pids[S3],
                expected_a)
            await a.execute(incr_sql, LOBBY)
            await tx_a.commit()

            row_b = await asyncio.wait_for(waiting, 10)
            expected_b = int(row_b["games_played"]) + 1
            await tx_b.rollback()
            # What B's own already-recorded lookup sees when its report still
            # carries A's number as its tail — production's statement, with
            # production's typed binds.
            found = await _prior(sm, [expected_b, expected_a])
            return blocked, expected_a, expected_b, found
        finally:
            await a.close()
            await b.close()
            await engine.dispose()

    blocked, expected_a, expected_b, found = run(go())
    assert blocked, ("the second report did not wait on the lobby row, so both "
                     "derived the same number from the same snapshot")
    assert expected_a == 1
    assert expected_b == 2, "the second report reused a stale games_played"
    # ...and A's game is found rather than settled again.
    assert found is not None
    assert int(found["game_number"]) == expected_a
    assert found["photon_room_id"] == f"rm_211531_r{expected_a}"
    # The tail B would have carried for that same game is now behind its own
    # slot, and the rule refuses it outright when no row is there to compare.
    assert main._ffa_game_number_refusal(expected_a, expected_b) is not None


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


def test_pg_the_insert_trigger_refuses_rather_than_reusing_an_occupied_999():
    """Control: trigger-clamps-999.

    `LEAST(MAX(game_number) + 1, 999)` is total against the CHECK and wrong:
    it hands back a number the lobby is already using, so a writer that
    supplied none would silently share a slot with a settled game. One above
    the highest, and a named refusal when that leaves the domain."""
    require_pg()
    sql = MIGRATION.read_text(encoding="utf-8")
    # The clamp is gone from the STATEMENTS; it survives only in the note that
    # explains why (comment lines start with `--`).
    code = "\n".join(ln for ln in sql.splitlines()
                     if not ln.strip().startswith("--"))
    assert "LEAST(" not in code
    assert "NEW.game_number := tail::SMALLINT;" in code

    async def go():
        conn = await _raw_pg()
        try:
            await conn.execute(MIGRATION_FIXTURE)
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                " ended_at, game_number) VALUES (gen_random_uuid(),"
                " '00000000-0000-0000-0000-0000000000c3', 'c3_r999', NOW(), 999)")
            try:
                await conn.execute(
                    "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                    " ended_at) VALUES (gen_random_uuid(),"
                    " '00000000-0000-0000-0000-0000000000c3', 'c3_no_tail', NOW())")
                why = "accepted"
            except Exception as ex:
                why = str(ex)
                await _unwedge(conn)
            landed = await conn.fetchval(
                "SELECT COUNT(*) FROM ffa_matches WHERE photon_room_id = 'c3_no_tail'")
            return why, landed
        finally:
            await conn.close()

    why, landed = run(go())
    assert "no number left inside 1..999" in why, why
    assert landed == 0                      # refused, not clamped onto 999


def test_pg_the_post_check_covers_a_writer_row_that_stored_another_number():
    """Control: postcheck-sequence-only.

    The assertion used to end `AND game_number_source = 'sequence'`, which made
    it blind to exactly the rows a RE-RUN would be checking: rows a writer
    supplied. Since the api refuses any report whose `_rN` tail is not the
    number it stores, such a row is a real fault — and the migration is where
    it gets caught rather than lived with."""
    require_pg()
    sql = MIGRATION.read_text(encoding="utf-8")

    async def go():
        conn = await _raw_pg()
        try:
            await conn.execute(MIGRATION_FIXTURE)
            await conn.execute(sql)
            # A writer row whose stored number is not the number its room names.
            await conn.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                " ended_at, game_number) VALUES (gen_random_uuid(),"
                " '00000000-0000-0000-0000-0000000000d4', 'd4_120000_r7',"
                " NOW(), 2)")
            src = await conn.fetchval(
                "SELECT game_number_source FROM ffa_matches"
                " WHERE photon_room_id = 'd4_120000_r7'")
            try:
                await conn.execute(sql)
                why = "accepted"
            except Exception as ex:
                why = str(ex)
                await _unwedge(conn)
            # ...and with that row gone the file passes again, so the assertion
            # is about the row and not about the re-run.
            await conn.execute(
                "DELETE FROM ffa_matches WHERE photon_room_id = 'd4_120000_r7'")
            await conn.execute(sql)
            return src, why
        finally:
            await conn.close()

    src, why = run(go())
    assert src == "writer"
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
