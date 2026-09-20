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

THE THIRD RULE (RJ-4 round 4): every answer this endpoint gives names the
LOBBY's progress — games_played, the number the next settlement takes, and the
number of the recorded game when the answer is about one. A refusal that says
nothing a client can realign to makes the FIRST refusal poison the rest of the
sitting, because the client's counter advances at every game start and the
lobby's advances only at a settlement. The client half of that is a contract
document (ai-collab/rejoin/RJ-CLIENT-RESYNC-CONTRACT.md), not code in this
lane; the three tests under "what a client can resync FROM" are the server half
and are what make the document checkable.

The live tests RUN the production SQL and the production migration against a
real PostgreSQL — `_FFA_PACE_ANCHOR_SQL` carries `CAST(:g AS SMALLINT)` and an
`IS DISTINCT FROM`, `_FFA_PRIOR_GAME_SQL` carries `CAST(:g AS SMALLINT)` for
the ONE number the report named, and a bind Postgres cannot type is not a
subtle bug (#275/#448/#438). They also drive production's own lock/derive/
increment functions under two live sessions, rather than rebuilding their SQL.
Point FFA_TEST_PG_DSN at a throwaway DATABASE — the schema below drops and
recreates players/ffa_*, so never at one another session is using:

    FFA_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:5432/rjtest" \\
        python -m pytest backend/tests/test_ffa_game_number_anchor.py -q

Without it they FAIL, naming the DSN. A run that means to go without a
PostgreSQL says so out loud by setting FFA_TEST_PG_OPTOUT=1, which turns them
back into skips — the point is that nobody gets a green run they did not ask
for (#438: a feature can ship inert with perfect logs).

Named mutation controls, each applied to a copy-aside of the file, run RED, and
restored from the copy (never `git checkout --`, #290).

THE TALLY, COUNTED RATHER THAN REMEMBERED. Round 3's docstring claimed nineteen
round-3 controls; the list below carries SIXTEEN marked (r3), and the r3 gate
was right to say so. A count asserted from memory next to the list that
contradicts it is the same defect class as a comment asserting a guarantee the
code does not supply, so the numbers here are the ones in the list, counted off
it: 22 unmarked and still live (rounds 1 and 2), 1 unmarked and RETIRED because
round 4 deleted the code it mutated (prior-tail-only, annotated in place), 16
marked (r3), 15 marked (r4), and one more that is a committed test rather than
a hand-run control (backfill-neutered, at the end). Round 4's are the ones
with a NEGATIVE control — an inert edit at the same site that must leave the
same test GREEN — so each test is shown to redden for the mutation and not for
any edit at all (#391); the runner, the red line of every mutant and the
negative-control result for each are in ai-collab/r4-mutation-controls.log.
All KILLED:

  prior-lookup-takes-the-earliest-of-a-set (r4)  _FFA_PRIOR_GAME_SQL: back to
                           a SET bind under ORDER BY ended_at
  prior-lookup-ignores-the-named-number (r4)  _FFA_PRIOR_GAME_SQL: the equality
                           becomes `OR TRUE`
  skew-refund-is-fail-soft (r4)  the endpoint: call _refund_ffa_lobby_bets for
                           this game's skew instead of the strict helper
  skew-refund-caps-at-one-pass (r4)  _refund_ffa_game_bets_strict: one batch
  later-pass-settles-a-recorded-skew (r4)  _ffa_recorded_game_outcome: drop the
                           refund verdict, so a leftover is paid at the frozen
                           price
  leave-not-compared (r4)  _ffa_report_contradiction: the leave decision
                           becomes empty
  kills-gate-narrowed (r4)  the field comparison back to kills_break_ties
  quota-before-idempotency (r4)  _quarantine_report: count the quota before the
                           on-file read, i.e. round 3's order
  variant-rows-are-not-deduped (r4)  _quarantine_on_file: drop the NULL-room
                           scan
  commit-between-the-lock-and-the-increment (r4)  the endpoint: commit between
                           _ffa_lock_lobby_slot and _ffa_advance_lobby_slot
  lobby-lock-no-for-update (r4)  _FFA_LOBBY_LOCK_SQL: drop FOR UPDATE. The r3
                           version of this control reddened a test that ran its
                           OWN copy of the statement; this one reddens a test
                           that calls the production function.
  refusal-carries-no-progress (r4)  the FfaReportRefusal handler: body back to
                           {"detail": ...} alone
  advisory-count-dropped (r4)  _ffa_poll_locked_payload: drop games_played
  trigger-raises-on-a-full-tail (r4)  327: the free-number fallback becomes a
                           raise, i.e. round 3's behaviour
  terminal-refusals-unenumerated (r4)  the endpoint: one terminal 409 raised
                           without a kept record

...and the twenty-four unmarked plus sixteen (r3) below, run as batches:

  anchor-per-row           _FFA_PACE_ANCHOR_SQL: MIN(ended_at) -> MAX(ended_at)
  anchor-includes-self     _FFA_PACE_ANCHOR_SQL: IS DISTINCT FROM CAST(:g AS
                           SMALLINT) -> IS NOT NULL
  anchor-less-than         _FFA_PACE_ANCHOR_SQL: IS DISTINCT FROM -> <
  prior-skips-invalidated  _FFA_PRIOR_GAME_SQL: add `AND invalidated_at IS NULL`
  prior-tail-only (retired)  the endpoint's _candidates set is gone in round 4
                           — the lookup keys on the ONE named number, so there
                           is no second candidate to drop. Replaced by the two
                           prior-lookup controls above.
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
import schemas

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


# steam -> (left_early, absent, game_points_at_leave) for the seats that left.
# Everyone else is present, which is the three-way default below.
PRESENT = (False, False, None)


def _report(vec, winner, room="rm_211531_r1", leave=None):
    """The fields the pure helpers read off a FfaMatchReport, INCLUDING the
    leave fields: _ffa_report_contradiction asks _ffa_leave_decision what this
    report says about who played, because that decision is what the settlement
    stores in ffa_match_players.absent and acts on."""
    leave = leave or {}
    return types.SimpleNamespace(
        photon_room_id=room, winner_steam_id=winner,
        reported_by_steam_id=winner,
        players=[types.SimpleNamespace(steam_id=s, rounds_won=r,
                                       points_total=p, kills=k,
                                       left_early=leave.get(s, PRESENT)[0],
                                       absent=leave.get(s, PRESENT)[1],
                                       game_points_at_leave=leave.get(s, PRESENT)[2])
                 for s, (r, p, k) in vec.items()])


def _vec(rows, leave=None):
    """One recorded game as _FFA_PRIOR_VECTOR_SQL reads it back:
    steam -> (rounds_won, points_total, kills, left_early, absent). `leave`
    names the seats whose two stored leave columns are not (False, False)."""
    leave = leave or {}
    return {s: (r, p, k) + leave.get(s, (False, False))
            for s, (r, p, k) in rows.items()}


def _code_lines(src: str) -> str:
    """`src` with its whole-line comments removed.

    A structural assertion about what the code DOES must not be answerable by
    what a comment SAYS — in either direction. Round 3's span checks ran over
    the raw text, so a sentence quoting the very call it forbade reddened the
    test, and (the direction that matters) a comment could have supplied a
    required literal that the code no longer contained."""
    return "\n".join(ln for ln in src.splitlines()
                      if not ln.strip().startswith("#"))


def _endpoint_src():
    return inspect.getsource(main.submit_ffa_match)


# ── the number: whose is it? ──────────────────────────────────────────────

def test_the_number_a_report_settles_is_the_lobbys_own_next_slot():
    src = _endpoint_src()
    # The lock and the derivation are ONE production function, so the endpoint
    # cannot hold one without the other and a test can drive both together
    # (test_pg_two_reports_for_one_lobby_cannot_settle_the_same_number).
    slot = inspect.getsource(main._ffa_lock_lobby_slot)
    assert "FOR UPDATE" in main._FFA_LOBBY_LOCK_SQL
    lock = slot.index("_FFA_LOBBY_LOCK_SQL")
    derive = slot.index('int(lobby["games_played"] or 0) + 1')
    assert lock < derive
    assert "lobby, _expected_game = await _ffa_lock_lobby_slot(db, lobby_uuid)" in src
    assert "_game_number = _expected_game" in src
    # ...and the endpoint does not re-derive it from anything else.
    assert 'int(lobby["games_played"] or 0) + 1' not in src
    # The room tail is read, but only as a cross-check: it never becomes the
    # stored number. (Control: number-from-the-tail.)
    assert "_room_tail = _ffa_room_game_no(" in src
    assert "_game_number = _room_tail" not in src
    assert "_game_number = int(_room_tail" not in src
    # The round-1 helper that took the tail as the number is gone entirely.
    assert not hasattr(main, "_ffa_report_game_number")


def test_the_stored_number_is_the_one_the_anchor_and_the_bet_settle_use():
    src = _endpoint_src()
    derive = src.index("_ffa_lock_lobby_slot(")
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
    # room string. It asks through the ONE verdict helper now, so the typed
    # read lives there; the endpoint must still hold no second derivation.
    assert "photon_room_id LIKE :sfx" not in src
    assert "_ffa_recorded_game_outcome(" in src
    assert "game_number = CAST(:g AS SMALLINT)" in \
        inspect.getsource(main._ffa_recorded_game_outcome)


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
    # It asks the row, through the one helper that decides settle-or-refund
    # for every after-the-fact resolver (round 4: a recorded config skew must
    # not be PAID by a later pass at the frozen price).
    assert "_ffa_recorded_game_outcome(db, lobby_id, int(g))" in rec
    outcome = inspect.getsource(main._ffa_recorded_game_outcome)
    assert "game_number = CAST(:g AS SMALLINT)" in outcome
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


def test_the_lookup_asks_about_the_number_the_report_named():
    """Controls: prior-lookup-takes-the-slot, prior-lookup-takes-either.

    The comparison has to be against the row that holds the number under
    discussion, or it is not a comparison of that game. Round 3 asked about a
    SET — the named number plus the lobby's next slot — and took the earliest
    row that came back, so a lobby holding a row at its next slot as well could
    have a report compared against a different game entirely (and, if that
    other game agreed, answered 200).

    Dropping the slot arm loses nothing: a report whose tail is not the lobby's
    next slot settles only where the lobby already HOLDS that number, which is
    exactly the row this lookup returns, and is otherwise refused by the one
    equality in _ffa_game_number_refusal."""
    src = _endpoint_src()
    named = src[src.index("_named_game = "):src.index("if _prior_game is not None:")]
    assert "_room_tail" in named
    assert "FFA_GAME_NUMBER_MAX" in named        # out-of-domain tails name nothing
    assert "_expected_game" not in named         # the slot is NOT a candidate
    assert '"g": _named_game' in src
    assert "game_number = CAST(:g AS SMALLINT)" in main._FFA_PRIOR_GAME_SQL
    assert "ANY(" not in main._FFA_PRIOR_GAME_SQL
    # A report that names no usable number looks nothing up; the refusal below
    # is what answers it.
    assert "if _named_game is not None:" in src


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
    why = main._ffa_report_contradiction(S3, _vec(ROW_A), _report(ROW_B, S1), False)
    assert why is not None
    assert S1 in why                      # names the winner disagreement first


def test_a_redelivery_of_the_same_report_is_not_a_contradiction():
    assert main._ffa_report_contradiction(S3, _vec(ROW_A), _report(ROW_A, S3), True) is None


def test_a_tally_that_differs_by_one_point_is_a_contradiction():
    near = dict(ROW_A, **{S2: (1, 7, 2)})
    why = main._ffa_report_contradiction(S3, _vec(ROW_A), _report(near, S3), False)
    assert why is not None and S2 in why


def test_a_kills_only_difference_is_a_contradiction_wherever_kills_are_signed():
    # Control: kills-not-compared. Signed kills decide three things - placement
    # where the lobby's FROZEN kills_tiebreak flag is set, the ffa_kills_50/100
    # achievements and their gold in EVERY lobby, and the refutation of an
    # absent or grace claim - so a kills-only difference between two accounts
    # is a settlement difference wherever the signature covers them.
    near = dict(ROW_A, **{S1: (4, 11, 99)})
    why = main._ffa_report_contradiction(S3, _vec(ROW_A), _report(near, S3), True)
    assert why is not None and "kills" in why


def test_the_comparisons_gate_is_the_signature_not_the_tie_break():
    """Control: kills-gate-narrowed (round 3's own gate, restored).

    kills_break_ties is kills_in_canonical AND the lobby's frozen flag, i.e.
    STRICTLY narrower - so using it here classified a kills difference that
    moved achievement gold, in a lobby with the flag off, as agreement."""
    src = _endpoint_src()
    assert "report, kills_break_ties)" not in src
    assert "len(report.players), kills_break_ties)" not in src
    assert "report, kills_in_canonical)" in src
    assert "len(report.players), kills_in_canonical)" in src
    # ...and the achievement those kills feed is gated on the same fact, not on
    # the tie-break flag, which is what makes them paid either way.
    grant = src.index('_grant_achievement_inline(db, _ach_pid, "ffa_kills_50")')
    ach = src[grant - 700:grant]
    assert "if kills_in_canonical:" in ach


def test_a_kills_only_difference_is_not_a_contradiction_where_they_decide_nothing():
    # An UNSIGNED (v1) kills field decides nothing at all: no placement, no
    # achievement, no refutation. Two honest clients of one game can tally
    # kills from different local observations, and a 409 for a difference that
    # changed nothing would spend an honest report (#430).
    near = dict(ROW_A, **{S1: (4, 11, 99)})
    assert main._ffa_report_contradiction(S3, _vec(ROW_A), _report(near, S3), False) is None


def test_a_leave_difference_is_a_contradiction():
    """Round 3 compared the winner and the tallies and stopped there, so two
    accounts that disagreed about who PLAYED were called agreement and the
    second got 200. left_early is stored per player, and the effective absent
    flag - _ffa_leave_decision's union of the carried ghosts and the
    early-leave graces - is what excludes a seat from rating, XP, gold, the
    payout denominator and everyone else's beaten counts."""
    zeroed = dict(ROW_A, **{S2: (0, 0, 0)})
    # Recorded: S2 played. Reported: S2 left this game and is graced out of it.
    graced = _report(zeroed, S3, leave={S2: (True, False, 1)})
    why = main._ffa_report_contradiction(S3, _vec(zeroed), graced, True)
    assert why is not None and S2 in why
    # Recorded: S2 was an absent carried ghost. Reported: the same. Agreement.
    ghost = _report(zeroed, S3, leave={S2: (True, True, None)})
    assert main._ffa_report_contradiction(
        S3, _vec(zeroed, leave={S2: (True, True)}), ghost, True) is None


def test_a_refuted_leave_claim_agrees_with_the_row_that_refuted_it():
    """The DECISION is compared, not the claim. A seat with a signed non-zero
    tally has its absent claim refuted, so the row stores absent=False; a
    second report making the same refuted claim therefore AGREES with it, and
    the comparison must not turn every honest redelivery into a 409."""
    claimed = _report(ROW_A, S3, leave={S1: (True, True, None)})
    assert main._ffa_report_contradiction(
        S3, _vec(ROW_A, leave={S1: (True, False)}), claimed, True) is None


def test_a_grace_that_only_differs_in_the_number_is_not_a_disagreement():
    """game_points_at_leave is compared only through the decision it feeds: two
    clients can read the field's running total an instant apart and still be on
    the same side of FFA_LEAVE_GRACE_POINTS."""
    zeroed = dict(ROW_A, **{S2: (0, 0, 0)})
    rec = _vec(zeroed, leave={S2: (True, True)})
    for gp in range(0, main.FFA_LEAVE_GRACE_POINTS):
        r = _report(zeroed, S3, leave={S2: (True, False, gp)})
        assert main._ffa_report_contradiction(S3, rec, r, True) is None, gp


def test_a_roster_difference_is_a_contradiction_either_way():
    short = {S1: ROW_A[S1], S3: ROW_A[S3]}
    assert main._ffa_report_contradiction(S3, _vec(ROW_A), _report(short, S3), False) is not None
    assert main._ffa_report_contradiction(S3, _vec(short), _report(ROW_A, S3), False) is not None


def test_the_detector_is_symmetric():
    # Whichever of the two verified rows had settled first, the other is a
    # contradiction: the detector reports a disagreement, it never ranks the
    # two accounts.
    assert main._ffa_report_contradiction(S3, _vec(ROW_A), _report(ROW_B, S1), False) is not None
    assert main._ffa_report_contradiction(S1, _vec(ROW_B), _report(ROW_A, S3), False) is not None


def test_the_leave_rule_has_exactly_one_definition():
    """#279/#432: the settlement and the comparison ask the same question, and
    a second copy of the rule is the one that stops being updated. The endpoint
    calls the helper and prints what it returns; it does not re-derive."""
    src = _endpoint_src()
    assert "ghosts, graced, _leave_log = _ffa_leave_decision(report, kills_in_canonical)" in src
    assert "ghosts.add(" not in src and "graced.add(" not in src
    assert "_ffa_leave_decision(" in inspect.getsource(main._ffa_report_contradiction)
    # The helper is PURE - it returns its log lines instead of printing them,
    # so the comparison path cannot emit a second copy of the endpoint's own
    # evidence about a report that is about to be refused.
    assert "print(" not in inspect.getsource(main._ffa_leave_decision)


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
    bets = src[src.index("game_no = _game_number"):src.index("await _ffa_advance_lobby_slot")]
    assert "if _target_skew:" in bets
    assert '_refund_ffa_game_bets_strict(db, lobby_uuid, game_no,' in bets
    # ...and this game's own settle is the branch that does NOT run.
    assert "if not _target_skew:" in bets
    settle = bets.index("_settle_ffa_bets_for_game(db, lobby_uuid, game_no")
    assert bets.index("if not _target_skew:") < settle
    # The refund is idempotent and moves gold as a DELTA (#326), so a retry,
    # the straggler pass and the closure reconcile can all cross it.
    ref = inspect.getsource(main._refund_ffa_game_bets_strict)
    assert "settled_at IS NULL RETURNING id" in ref
    assert "gold_spent = GREATEST(0, COALESCE(gold_spent,0) - :amt)" in ref
    # ...and because the refund stamps settled_at, every later pass skips it:
    # both the straggler query and the closure reconcile select on IS NULL.
    assert "settled_at IS NULL AND game_number < :g" in src
    assert "settled_at IS NULL ORDER BY game_number" in \
        inspect.getsource(main._reconcile_ffa_lobby_bets)


def test_the_skew_refund_is_part_of_the_settlement_and_not_a_best_effort_pass():
    """Controls: skew-refund-is-fail-soft, skew-refund-caps-at-one-pass.

    Round 3 called the SWEEP helper here, from inside the block whose except
    swallows everything. That helper also ends its pass at 200 rows. Either way
    a wager on a skewed game could still be unsettled at commit, and the next
    pass over it - the straggler loop, the closure reconcile, the janitor -
    settled it against the recorded winner at the FROZEN price, which is the
    one outcome the branch exists to prevent (#412).

    Three properties, and the file's own fail-soft refund has to keep NOT
    having them, or this test is measuring nothing."""
    strict = inspect.getsource(main._refund_ffa_game_bets_strict)
    soft = inspect.getsource(main._refund_ffa_lobby_bets)
    # 1. It does not swallow. 2. It opens no savepoint of its own, so a failure
    # takes the caller's transaction with it. 3. It loops to exhaustion and
    # RAISES at its bound rather than returning short.
    assert "except Exception" not in strict and "except Exception" in soft
    assert "begin_nested" not in strict and "begin_nested" in soft
    assert "raise RuntimeError(" in strict
    assert "for _ in range(FFA_REFUND_MAX_BATCHES)" in strict
    # The caller runs it OUTSIDE the block whose except swallows bet problems,
    # and turns a failure into a retryable answer rather than a committed row.
    src = _endpoint_src()
    swallow = src.index("[FFA-BETS] settle failed (report unaffected")
    assert src.index("_refund_ffa_game_bets_strict(") > swallow
    assert src.index("_refund_ffa_game_bets_strict(") < src.index("await _ffa_advance_lobby_slot")
    blk = src[swallow:src.index("await _ffa_advance_lobby_slot")]
    assert "FfaReportRefusal(" in blk and "503" in blk


def test_a_later_pass_refunds_a_recorded_skew_instead_of_settling_it():
    """The other half of the same guarantee, and the one a leftover needs. Every
    after-the-fact resolver asks ONE helper what a recorded game's wagers must
    do, and that helper reads the row's two target columns - so a wager that
    somehow outlives the settlement's own refund is returned, never paid at the
    price the bettor did not agree to."""
    outcome = inspect.getsource(main._ffa_recorded_game_outcome)
    assert "score_target_frozen" in outcome and "score_target_played" in outcome
    assert 'return "refund", None' in outcome
    # Both resolvers go through it, and neither settles without asking.
    rec = inspect.getsource(main._reconcile_ffa_lobby_bets)
    assert "_ffa_recorded_game_outcome(" in rec
    assert 'verdict == "settle"' in rec
    assert 'verdict == "refund"' in rec
    src = _endpoint_src()
    strag = src[src.index("stragglers = "):src.index("[FFA-BETS] settle failed")]
    assert "_ffa_recorded_game_outcome(" in strag
    assert "SELECT winner_id FROM ffa_matches" not in strag
    # NULL columns (every pre-327 row) mean "no skew recorded", which is the
    # pre-327 behaviour - a guessed skew would refund a game that was paid.
    assert "frozen is not None and played is not None" in outcome


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


def test_the_played_target_is_one_of_two_server_held_numbers():
    """The narrower claim, which is the true one. `_played_target` IS the
    report's own max tally, so the report selects which of the two branches
    runs; what it cannot do is name a third length, because the shape rule
    above admits exactly the lobby's frozen target and the module default and
    refuses everything else. Round 3 wrote "never a number the report chose",
    which reads as the stronger claim and is not what the code does."""
    src = _endpoint_src()
    assert "_played_target = int(max_rounds)" in src
    note = src[src.index("The target the game was actually played to"):
               src.index("_played_target = int(max_rounds)")]
    assert "never a number the report chose" not in note
    assert "SELECTS between two server-held numbers" in note
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
    block = src[src.index("_roster_bound = "):src.index('detail="Lobby is not active"')]
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
    def __init__(self, value=None, rows=None):
        self._value = value
        self._rows = list(rows or [])

    def scalar(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDb:
    """Enough AsyncSession for _quarantine_report: a scripted reply per
    statement, and a record of what it was asked."""

    def __init__(self, pending=0, insert_id=None, boom=False, stored=None,
                 variants=()):
        self.pending = pending
        self.insert_id = uuid.uuid4() if insert_id == "new" else insert_id
        self.boom = boom
        self.stored = stored           # what (mode, room) already holds
        self.variants = list(variants)  # the group's NULL-room rows
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
            if "photon_room_id IS NULL" in sql:
                return _FakeResult(rows=self.variants)
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
    # The room's row already holds THIS report: the retry-idempotency, not a
    # drop.
    assert _capture(_FakeDb(insert_id=None,
                            stored=json.dumps(PAYLOAD))) == "already"
    assert _capture(_FakeDb(pending=50)) == "quota"
    assert _capture(_FakeDb(boom=True)) == "failed"


def test_a_delivery_that_adds_no_row_is_not_charged_for_one():
    """Control: quota-before-idempotency (round 3's order).

    The pending bound exists to stop a flood of NEW rows. Counting it FIRST
    meant that at saturation an honest outbox retry of a payload the table
    already held was answered 503 instead of its idempotent terminal answer -
    so the bound spent the very report it exists to preserve. The read is now
    first, and neither kept answer touches the count."""
    full = _FakeDb(pending=50, stored=json.dumps(PAYLOAD))
    assert _capture(full) == "already"
    assert full.inserts == 0
    # A REPEAT of a variant is the same kind of delivery: its payload is on
    # file, so it adds nothing and costs nothing, even at saturation.
    repeat = _FakeDb(pending=50, stored=json.dumps(OTHER),
                     variants=[json.dumps(PAYLOAD)])
    assert _capture(repeat) == "variant"
    assert repeat.inserts == 0
    # ...and the order is what does it: the on-file read runs before the count.
    src = inspect.getsource(main._quarantine_report)
    assert src.index("_quarantine_on_file(") < src.index("SELECT COUNT(*)")


def test_a_variant_is_kept_once_however_often_it_is_delivered():
    """Control: variant-rows-are-not-deduped.

    A variant row carries photon_room_id NULL so it cannot take the
    (mode, room) key that makes an honest retry idempotent - which left it with
    no idempotency at all: round 3 inserted a fresh row for every redelivery,
    so one differing payload delivered four times (three immediate retries plus
    an outbox attempt) cost four rows of a 50-row bound. The group's NULL-room
    rows are compared as values too."""
    first = _FakeDb(insert_id=None, stored=json.dumps(OTHER))
    assert _capture(first) == "variant"
    assert first.inserts == 1
    again = _FakeDb(insert_id=None, stored=json.dumps(OTHER),
                    variants=[json.dumps(PAYLOAD)])
    assert _capture(again) == "variant"
    assert again.inserts == 0
    # A DIFFERENT second account is still kept - the dedupe is on the payload,
    # not on "there is already a variant".
    third = _FakeDb(insert_id=None, stored=json.dumps(OTHER),
                    variants=[json.dumps({"a": 2})])
    assert _capture(third) == "variant"
    assert third.inserts == 1


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
    # ...and RECORDED: one insert, carrying a NULL room so the partial unique
    # index that makes an honest retry idempotent still does. (Round 3 tried
    # the keyed insert first and wrote this row after the conflict came back,
    # i.e. two statements; the read above already knows the key is taken.)
    assert db.inserts == 1
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
            why="w", detail="This game is already recorded",
            progress=main._ffa_progress(3), status=status))
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
    branch = src[src.index("_named_game = "):src.index("INSERT INTO ffa_matches")]
    for forbidden in ("UPDATE ffa_matches", "UPDATE players", "invalidated_at =",
                      "DELETE FROM"):
        assert forbidden not in branch, forbidden


def _terminal_raises(src):
    """Every terminal refusal literal in a source blob, in EITHER raise form.

    The FFA report path raises FfaReportRefusal wherever it can name the
    lobby's progress and plain HTTPException where it cannot (above the lobby
    read). A regex that only saw one of them would stop seeing half the class
    the moment a site moved between the two - a check that cannot fail (#342).
    The message literal is the key; what follows it is the progress argument."""
    return re.findall(
        r"raise (?:HTTPException|FfaReportRefusal)\((4\d\d), (f?\"[^\"]*\")",
        src)


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
        '"Invalid FFA match signature"': "HMAC",
        '"Invalid lobby_id format"': "unparseable id",
        '"Need at least two distinct players"': "malformed roster",
        '"Winner is not among the players"': "malformed roster",
        '"Reporter is not a participant"': "malformed roster",
        '"photon_room_id is required"': "malformed room id",
        '"One or more players not registered"': "unknown player",
        '"Lobby not found"': "no row to bind to",
    }
    unbound = {
        '"Report must cover exactly the lobby roster"': "roster binding",
        '"Report player count does not match the lobby"': "roster binding",
    }
    seen = 0
    for status, rest in _terminal_raises(src):
        key = rest.strip()
        seen += 1
        if key in integrity or key in unbound:
            continue
        if key.startswith('f"Slot mismatch'):
            continue
        raise AssertionError(
            f"terminal HTTP {status} answered without a kept record: {key}")
    # The enumeration has to have MATCHED something, or a rename of the raise
    # form turns this whole test into a check that cannot fail (#342/#441).
    assert seen >= len(integrity) + len(unbound)
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
    assert "FfaReportRefusal(503" in blk
    assert 'HTTPException(409, "Duplicate room id")' not in blk
    # ...and the progress it answers with is RE-READ, because the rollback
    # above released the lock and the in-memory lobby row is a stale snapshot.
    assert "_race_progress = _ffa_progress(" in blk
    assert "SELECT games_played FROM ffa_lobbies WHERE id = :lid" in blk


def test_a_closed_lobbys_unbound_report_is_not_answered_as_a_lifecycle_refusal():
    """Three different answers, told apart. Round 2 gave a roster that does not
    bind, a shape that does not hold and a genuinely closed lobby the SAME
    terminal 409, and kept a record for only the third."""
    src = _endpoint_src()
    blk = src[src.index('if lobby["status"] != "active":'):
              src.index("# Roster validation")]
    assert "_roster_bound" in blk
    assert 'raise FfaReportRefusal(403, "Report must cover exactly the lobby roster"' in blk
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
    # A conflict on the key is TWO cases and the note names both: the retry,
    # compared as values rather than as text, and the second account.
    assert "compared as VALUES" in doc
    assert "a DIFFERENT account of the" in doc
    assert '"variant"' in doc
    # ...and it no longer says the quota bounds variants "exactly as it bounds
    # any other capture" without saying what makes a REDELIVERY of one free.
    assert "EVERY kept outcome is idempotent" in doc


def test_the_refusal_note_states_the_retry_budget_as_a_bound():
    """Round 3 wrote that a 503 makes the report survive "until an operator
    clears the backlog". It survives as long as the client keeps retrying, and
    that ladder is finite - so the sentence promised something no server-side
    change can deliver."""
    doc = inspect.getsource(main._ffa_record_and_refuse)
    assert "until an operator clears the backlog" not in doc
    assert "FINITE ladder" in doc


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
    # The sequence arm is described as what it computes. Round 2 called it "the
    # next free number", which it was not; round 4 added a free-number FALLBACK
    # for the one input MAX+1 cannot serve, and says which is which.
    fn = sql[sql.index("CREATE OR REPLACE FUNCTION"):sql.index("DROP TRIGGER")]
    assert 'NOT "the next free number", which this expression does not compute' in fn
    assert "falls back to the LOWEST FREE number" in fn


def test_the_migration_makes_the_column_total_and_bounded():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "SET NOT NULL" in sql
    assert "CHECK (game_number BETWEEN 1 AND 999)" in sql
    # Provenance for every backfilled row: which rule gave it its number.
    assert "game_number_source" in sql


def test_the_trigger_claims_only_the_totality_it_has():
    """Round 3's header called the derivation "a total function from a row to a
    number" while its sequence arm raised for any lobby whose HIGHEST number
    was 999 - and that exception reaches the pre-327 api as an HTTP 500. The
    arm now falls back to the lobby's lowest free number, so the only refused
    input is a lobby holding all 999, and the header says so as a bound."""
    sql = MIGRATION.read_text(encoding="utf-8")
    head = sql[sql.index("Insert-time derivation"):sql.index("CREATE OR REPLACE FUNCTION")]
    assert "A total function from a row to a number" not in head
    assert "every lobby that has a free number" in head
    fn = sql[sql.index("CREATE OR REPLACE FUNCTION"):sql.index("DROP TRIGGER")]
    assert "generate_series(1, 999)" in fn
    assert "holds every number in 1..999" in fn


# ── the control inventory, checked against itself ─────────────────────────

def test_the_control_tally_matches_the_list_it_sits_next_to():
    """Control: tally-from-memory (the round-3 LOW at line 50).

    Round 3's docstring said nineteen round-3 controls and listed sixteen. A
    number asserted beside the list that contradicts it is the same defect
    class as a comment asserting a guarantee the code does not supply, and it
    stays wrong silently because nothing counts. This counts.

    It reads the SAME docstring the inventory lives in, so the two cannot
    drift: adding a control without updating the tally reddens here."""
    doc = sys.modules[__name__].__doc__
    entries = [ln for ln in doc.splitlines()
               if re.match(r"^  [a-z0-9-]+( \((?:r3|r4|retired)\))? +\S", ln)]
    counted = {
        "r3": sum(1 for ln in entries if "(r3)" in ln),
        "r4": sum(1 for ln in entries if "(r4)" in ln),
        "retired": sum(1 for ln in entries if "(retired)" in ln),
    }
    counted["plain"] = len(entries) - sum(counted.values())
    # The committed-test one is listed in the same shape but is called out
    # separately in the prose, so it is not a hand-run control.
    assert any("backfill-neutered" in ln for ln in entries)
    counted["plain"] -= 1

    claimed = re.search(
        r"counted off\s*\n?it: (\d+) unmarked and still live .*?(\d+) unmarked and RETIRED"
        r".*?(\d+)\s*\n?marked \(r3\), (\d+) marked \(r4\)",
        doc, re.S)
    assert claimed, "the docstring no longer states a tally in a readable form"
    want_plain, want_retired, want_r3, want_r4 = (int(g) for g in claimed.groups())
    assert (want_plain, want_retired, want_r3, want_r4) == (
        counted["plain"], counted["retired"], counted["r3"], counted["r4"]), (
        "the docstring's tally and its own list disagree: claimed "
        f"{(want_plain, want_retired, want_r3, want_r4)}, listed "
        f"{(counted['plain'], counted['retired'], counted['r3'], counted['r4'])}")
    # ...and the list is not empty, or the whole check passes on nothing.
    assert counted["r4"] >= 10 and counted["plain"] >= 10


def test_every_round_four_control_names_a_test_that_exists():
    """A control whose test was renamed is a control nobody can re-run, and the
    inventory is the only place the pairing is written down. Every round-4
    control ran against a named node; those names are in the log, and the ones
    the docstring's prose points at have to still be in this module."""
    mod = sys.modules[__name__]
    for name in ("test_pg_the_prior_lookup_reads_the_row_that_holds_the_named_number",
                 "test_pg_a_tail_behind_the_slot_finds_its_own_game_not_the_next_one",
                 "test_the_skew_refund_is_part_of_the_settlement_and_not_a_best_effort_pass",
                 "test_a_later_pass_refunds_a_recorded_skew_instead_of_settling_it",
                 "test_a_leave_difference_is_a_contradiction",
                 "test_the_comparisons_gate_is_the_signature_not_the_tie_break",
                 "test_a_delivery_that_adds_no_row_is_not_charged_for_one",
                 "test_a_variant_is_kept_once_however_often_it_is_delivered",
                 "test_the_lock_the_derivation_and_the_increment_are_one_transaction",
                 "test_pg_two_reports_for_one_lobby_cannot_settle_the_same_number",
                 "test_every_report_answer_carries_the_lobbys_progress",
                 "test_the_lobby_state_advertises_the_sittings_settled_count",
                 "test_pg_the_trigger_never_hands_back_a_number_the_lobby_is_using",
                 "test_no_terminal_refusal_on_the_ffa_report_path_is_answered_over_nothing"):
        assert callable(getattr(mod, name, None)), name

# ── what a client can resync FROM ─────────────────────────────────────────
# RJ-CLIENT-RESYNC-CONTRACT.md is the client lane's side of these fields. The
# tests below are the server side of the same contract: they are what makes
# the document checkable rather than descriptive.

def test_the_lobby_state_advertises_the_sittings_settled_count():
    """Control: advisory-count-has-no-semantic-test (the round-3 LOW).

    `games_played` was added to the ready-join payload with nothing asserting
    it is EMITTED, what it is measured against, or that it names the same
    quantity the report path refuses on. A field with no test is a field that
    can be renamed, moved under a nested object or dropped, and nothing here
    would notice — which is exactly the state an unchanged client consumer
    cannot be built against (#438: acceptance is a positive signal)."""
    src = inspect.getsource(main._ffa_poll_locked_payload)
    # It is a TOP-LEVEL key of the ready-join payload, which is what the
    # client's substring JSON reader can reach.
    body = src[src.index('return {'):]
    assert '"games_played": int(lobby["games_played"] or 0),' in body
    assert '"status": "ready_join"' in body
    # ...and it is the LOBBY's count, not a member count or a queue length.
    assert "lobby[" in body[body.index('"games_played"'):
                            body.index('"games_played"') + 60]
    # The one quantity: what the payload advertises and what the report path
    # derives its slot from are the same column, read the same way.
    lock = inspect.getsource(main._ffa_lock_lobby_slot)
    assert 'int(lobby["games_played"] or 0) + 1' in lock
    # And the number a client that reads it should name is the NEXT one.
    assert main._ffa_progress(4)["expected_game"] == 5
    assert main._ffa_progress(0)["expected_game"] == 1


def test_every_report_answer_carries_the_lobbys_progress():
    """The resync fields, on all three answer shapes.

    One refusal used to poison the rest of a same-room sitting: the client's
    counter advanced at every game start, the server's did not, and no answer
    carried anything a client could realign to — so the first refusal made
    every later report of that sitting one further ahead, and all of them were
    refused (RJ-R3 HIGH, plugin/FfaMode.cs:1077). The server half is that
    EVERY answer names the lobby's authoritative progress."""
    # 1. The shape. Two keys always, and the third only when the answer is
    #    about a game the lobby has already settled.
    assert main._ffa_progress(2) == {"games_played": 2, "expected_game": 3}
    assert main._ffa_progress(2, settled_game=1) == {
        "games_played": 2, "expected_game": 3, "settled_game": 1}
    # The counter is authoritative, not a delta: a client adopts it whole.
    assert main._ffa_progress(0) == {"games_played": 0, "expected_game": 1}

    # 2. The refusals. FfaReportRefusal carries the progress to the handler,
    #    and `detail` stays a plain string so an existing client's error text
    #    is unchanged.
    ex = main.FfaReportRefusal(409, "This game is already recorded",
                               main._ffa_progress(2, settled_game=2))
    assert isinstance(ex, main.HTTPException)
    assert ex.status_code == 409 and ex.detail == "This game is already recorded"
    assert ex.progress == {"games_played": 2, "expected_game": 3,
                           "settled_game": 2}
    handler = main.app.exception_handlers[main.FfaReportRefusal]
    body = json.loads(bytes(asyncio.run(handler(None, ex)).body))
    assert body == {"detail": "This game is already recorded",
                    "games_played": 2, "expected_game": 3, "settled_game": 2}
    # Top-level integer keys: ApiClient.ExtractJsonInt is a substring reader,
    # so a nested object would not be reachable by the unchanged client.
    assert all(not isinstance(v, (dict, list)) for v in body.values())

    # 3. The success answer. The schema carries the same three names, so a
    #    client reads one vocabulary whatever the outcome.
    fields = schemas.FfaMatchResponse.model_fields
    assert {"games_played", "expected_game", "settled_game"} <= set(fields)
    src = _code_lines(_endpoint_src())
    assert "**_ffa_progress(_game_number)" in src
    # ...and the success answer's progress is the COMMITTED state: it is built
    # from the number this transaction settled, after the advance.
    assert src.index("await _ffa_advance_lobby_slot(") < \
        src.index("**_ffa_progress(_game_number)")


def test_a_refusal_the_client_can_act_on_names_the_settled_game():
    """The difference between "retry later" and "this one is done".

    An outbox entry whose game the lobby has already settled must be DROPPED,
    not retried to the end of a finite ladder — and the only way a client can
    tell is the answer. Every refusal about an already-recorded game carries
    settled_game; the ones about a game that is not settled do not."""
    src = _code_lines(_endpoint_src())
    # The already-recorded answers name the game they are about.
    assert "_ffa_with_settled(" in src
    withs = inspect.getsource(main._ffa_with_settled)
    assert '"settled_game"' in withs
    # A 503 (capture failed, room race, refund failed) is retryable and says
    # nothing about a settled game, because none is settled.
    assert main._ffa_progress(2).get("settled_game") is None

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
    score_target_frozen SMALLINT,
    score_target_played SMALLINT,
    CONSTRAINT uq_ffa_match_room UNIQUE (photon_room_id)
);
CREATE TABLE ffa_match_players (
    match_id UUID NOT NULL REFERENCES ffa_matches(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players(id),
    rounds_won SMALLINT NOT NULL DEFAULT 0,
    points_total SMALLINT NOT NULL DEFAULT 0,
    kills INTEGER NOT NULL DEFAULT 0,
    left_early BOOLEAN NOT NULL DEFAULT FALSE,
    absent BOOLEAN NOT NULL DEFAULT FALSE,
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


async def _prior(sm, g):
    """The production lookup, asked the way production asks it: about the ONE
    number the report named."""
    async with sm() as db:
        return (await db.execute(text(main._FFA_PRIOR_GAME_SQL),
                                 {"lid": LOBBY, "g": int(g)})).mappings().first()


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


def test_pg_the_prior_lookup_reads_the_row_that_holds_the_named_number():
    """Control: prior-lookup-takes-the-earliest-of-a-set (round 3's shape).

    The lookup used to bind a SET — the lobby's expected slot and the report's
    own `_rN` tail — under `game_number = ANY(...) ORDER BY ended_at LIMIT 1`.
    A set plus "earliest" is not "the row that holds the number the report
    named": with rows at BOTH numbers it returned whichever settled first, so a
    report naming the tail was compared against, and could be declared a
    duplicate of, a DIFFERENT game. The bind is now the single named number and
    the row is the one holding it; the typed cast (`CAST(:g AS SMALLINT)`)
    stays, because an untyped bind is the #275/#448 shape.

    Every gap state a live sitting can be in, enumerated against real rows."""
    require_pg()

    async def go():
        # Rows at BOTH numbers a round-3 report would have offered: the lobby's
        # expected slot 2 (settled LATER) and the tail 1 (settled first).
        engine, sm, _ = await _setup([
            ("rm_g1_r1", 1, 686, False),
            ("rm_g2_r2", 2, 1300, False),
            ("rm_dup_r3", 3, 2000, False),
            ("rm_dup2_r3", 3, 2100, False),
        ])
        try:
            return {
                "both_named_2": await _prior(sm, 2),
                "both_named_1": await _prior(sm, 1),
                "duplicate_pair": await _prior(sm, 3),
                "gap": await _prior(sm, 4),
                "above_domain": await _prior(sm, 999),
            }
        finally:
            await engine.dispose()
    got = run(go())
    # 1. Two numbers held, the report names 2: the row holding 2 comes back,
    #    though the row holding 1 is EARLIER. (Round 3 returned rm_g1_r1 here,
    #    and the caller then compared game 2's report against game 1's row.)
    assert got["both_named_2"] is not None
    assert got["both_named_2"]["photon_room_id"] == "rm_g2_r2"
    assert int(got["both_named_2"]["game_number"]) == 2
    # 2. The same table, the report names 1: the row holding 1.
    assert got["both_named_1"]["photon_room_id"] == "rm_g1_r1"
    # 3. Two rows hold ONE number (the verified-pair case that made the set
    #    ambiguous in the first place). ORDER BY ended_at makes the choice
    #    deterministic: the account that settled first. Both are live — neither
    #    was reversed — so this is a stable choice, not a claim about validity.
    assert got["duplicate_pair"]["photon_room_id"] == "rm_dup_r3"
    # 4. and 5. No row holds the named number: nothing comes back, and the
    #    refusal rule alone decides — which is the honest state for a number
    #    the lobby has not reached, and for one outside the sitting entirely.
    assert got["gap"] is None
    assert got["above_domain"] is None


def test_pg_a_tail_behind_the_slot_finds_its_own_game_not_the_next_one():
    """The finding's own failure scenario, end to end on real rows.

    A same-room sitting where the client's counter fell behind: the lobby is on
    slot 3 and the report names 2. The lookup has to hand the endpoint the row
    holding 2 — that is the game being re-reported, and comparing against it is
    what makes an honest redelivery a 409-with-evidence instead of a settlement
    of somebody else's game. The refusal rule and the lookup have to agree
    about WHICH number is in question."""
    require_pg()

    async def go():
        engine, sm, _ = await _setup([
            ("rm_g1_r1", 1, 600, False),
            ("rm_g2_r2", 2, 1300, False),
        ], games_played=2)
        try:
            async with sm() as db:
                _row, expected = await main._ffa_lock_lobby_slot(db, LOBBY)
                await db.rollback()
            return expected, await _prior(sm, 2), await _prior(sm, expected)
        finally:
            await engine.dispose()
    expected, named, at_slot = run(go())
    assert expected == 3
    # The named number is behind the slot, and the row it names is the one that
    # comes back — not game 1's, and not nothing.
    assert named is not None and int(named["game_number"]) == 2
    assert named["photon_room_id"] == "rm_g2_r2"
    # The slot itself is empty, which is what makes it the next settlement.
    assert at_slot is None
    # ...and the rule refuses the report, with the row above as its evidence.
    assert main._ffa_game_number_refusal(2, expected) is not None


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
            found = await _prior(sm, 2)
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
                        " rounds_won, points_total, kills, left_early, absent)"
                        " VALUES (:m, :p, :r, :t, :k, :le, :ab)"),
                        {"m": mid, "p": pids[s], "r": r, "t": p, "k": k,
                         "le": s == S2, "ab": False})
                await db.commit()
                rows = (await db.execute(text(main._FFA_PRIOR_VECTOR_SQL),
                                         {"m": mid})).mappings().all()
            return {r["steam_id"]: (int(r["rounds_won"]), int(r["points_total"]),
                                    int(r["kills"]), bool(r["left_early"]),
                                    bool(r["absent"])) for r in rows}
        finally:
            await engine.dispose()
    vec = run(go())
    # The five stored fields the comparison reads, off real columns — the two
    # new ones are what round 3 left out, so two accounts that disagreed about
    # who PLAYED were called agreement and the second settled (#430).
    assert vec == _vec(ROW_A, leave={S2: (True, False)})
    assert main._ffa_report_contradiction(S3, vec, _report(ROW_B, S1), True) is not None
    # The same tallies, and S2's early leave reported as it is recorded: same
    # account.
    same = _report(ROW_A, S3, leave={S2: (True, False, 99)})
    assert main._ffa_report_contradiction(S3, vec, same, True) is None
    # The same tallies with S2 reported as never having left: a different
    # account of who played, and the settlement it asks for is a different one.
    assert main._ffa_report_contradiction(S3, vec, _report(ROW_A, S3), True) is not None


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

def test_the_lock_the_derivation_and_the_increment_are_one_transaction():
    """Control: commit-between-the-lock-and-the-increment.

    The live test below proves the LOCK holds. What it cannot see is the
    endpoint deciding to commit in the middle — at which point the row unlocks
    with games_played unchanged, the waiting report reads the same number, and
    two settlements take one slot with the lock still nominally in place. So
    the transaction SCOPE is asserted here, structurally, on the production
    source: between taking the lock and consuming the slot there is no commit,
    and the advance is the last thing before the one that ends it."""
    src = _code_lines(_endpoint_src())
    lock = src.index("await _ffa_lock_lobby_slot(")
    advance = src.index("await _ffa_advance_lobby_slot(")
    commit = src.index("await db.commit()", advance)
    assert lock < advance < commit
    # Nothing commits in between. Measured on the CODE, with the comments
    # stripped — a prose mention of `await db.commit()` is not a commit, and a
    # check that a comment can redden is a check that a comment can also keep
    # green (#441). `db.commit()` inside the quarantine helper is a different
    # session-level call in a DIFFERENT function; this span is the endpoint's.
    assert "await db.commit()" not in src[lock:advance]
    # ...and the advance is not itself inside a savepoint that a later failure
    # could roll back while the settlement stands.
    assert "begin_nested" not in src[advance:commit]
    # Exactly one advance per settlement, in the whole endpoint (#330/#279).
    assert src.count("_ffa_advance_lobby_slot(") == 1
    # ...and the increment is nowhere else in the file either: one rule, one
    # place, so the slot cannot be consumed by a second writer's copy.
    whole = _code_lines(pathlib.Path(main.__file__).read_text(encoding="utf-8"))
    assert whole.count("games_played = games_played + 1") == 1


def test_pg_two_reports_for_one_lobby_cannot_settle_the_same_number():
    """The concurrency bar, on two real connections, through PRODUCTION's own
    functions.

    Report A calls `_ffa_lock_lobby_slot` and derives its slot. Report B,
    arriving while A is still open, must WAIT on that row — and when it is let
    through it must RE-READ, not reuse the value it would have seen (#208: the
    second half of a split operation working from a snapshot is how a settled
    row gets acted on twice).

    Round 3's version lifted the endpoint's SQL STRINGS out with a regex and
    ran them itself, on its own connections, in its own transaction — so it
    proved PostgreSQL's row locking and nothing about production's ordering.
    Moving the derivation above the lock, or splitting the transaction in two,
    left it green. It now calls `main._ffa_lock_lobby_slot` and
    `main._ffa_advance_lobby_slot` directly, so the derivation, the lock and
    the increment under test are the ones the endpoint runs.

    Control (hand-run): drop `FOR UPDATE` from `_FFA_LOBBY_LOCK_SQL` and B
    returns immediately with games_played = 0, deriving 1 exactly as A did."""
    require_pg()

    async def go():
        engine, sm, pids = await _setup([], games_played=0)
        # Two SEPARATE sessions: two connections, two transactions.
        a, b = sm(), sm()
        try:
            await b.execute(text("SET lock_timeout = '10s'"))
            row_a, expected_a = await main._ffa_lock_lobby_slot(a, LOBBY)

            waiting = asyncio.create_task(main._ffa_lock_lobby_slot(b, LOBBY))
            await asyncio.sleep(0.5)
            blocked = not waiting.done()

            # A settles its game and consumes the slot, in the SAME
            # transaction as its lock, exactly as the endpoint does.
            await a.execute(text(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                " winner_id, ended_at, game_number) VALUES"
                " (:i, :l, :r, :w, NOW(), CAST(:g AS SMALLINT))"),
                {"i": uuid.uuid4(), "l": LOBBY,
                 "r": f"rm_211531_r{expected_a}", "w": pids[S3],
                 "g": expected_a})
            await main._ffa_advance_lobby_slot(a, LOBBY)
            await a.commit()

            _row_b, expected_b = await asyncio.wait_for(waiting, 10)
            await b.rollback()
            # What B's own already-recorded lookup sees when its report still
            # carries A's number as its tail — production's statement, with
            # production's typed bind.
            found = await _prior(sm, expected_a)
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


def test_pg_a_refusal_carries_the_lobbys_progress_off_the_locked_row():
    """The resync half of the same lock, as a live read.

    Every refusal the report path raises answers with the lobby's authoritative
    progress, and that progress comes off the row this transaction locked — so
    what a refused client adopts is the committed counter, not a prediction of
    it. RJ-CLIENT-RESYNC-CONTRACT.md is what consumes these three fields."""
    require_pg()

    async def go():
        engine, sm, _ = await _setup([("rm_g1_r1", 1, 600, False),
                                      ("rm_g2_r2", 2, 1300, False)],
                                     games_played=2)
        try:
            async with sm() as db:
                _row, expected = await main._ffa_lock_lobby_slot(db, LOBBY)
                await db.rollback()
            return expected
        finally:
            await engine.dispose()
    expected = run(go())
    progress = main._ffa_progress(expected - 1)
    assert progress == {"games_played": 2, "expected_game": 3}
    # A refusal about a number the lobby already holds says so, and names the
    # settled game, which is what lets the client drop that outbox entry as
    # terminal rather than retry it forever.
    settled = main._ffa_progress(expected - 1, settled_game=2)
    assert settled["settled_game"] == 2
    assert settled["games_played"] == 2 and settled["expected_game"] == 3


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


def test_pg_the_trigger_never_hands_back_a_number_the_lobby_is_using():
    """Controls: trigger-clamps-999, trigger-raises-on-a-full-tail.

    `LEAST(MAX(game_number) + 1, 999)` is total against the CHECK and wrong: it
    hands back a number the lobby is already using, so a writer that supplied
    none would silently share a slot with a settled game.

    Round 3 replaced the clamp with a RAISE — correct about the collision and
    wrong about the cost (#430). MAX+1 leaves the domain for any lobby holding
    999, whatever else is free, and that lobby's next unnumbered insert then
    reaches the pre-327 api as an HTTP 500: a settled game destroyed over a
    number the lobby had 998 of. The arm now falls back to the lobby's LOWEST
    FREE number, and only a lobby with no free number at all is refused.

    Both arms, executed: the fallback lands on a free number, and the refusal
    still fires when there is genuinely nothing left."""
    require_pg()
    sql = MIGRATION.read_text(encoding="utf-8")
    # The clamp is gone from the STATEMENTS; it survives only in the note that
    # explains why (comment lines start with `--`).
    code = "\n".join(ln for ln in sql.splitlines()
                     if not ln.strip().startswith("--"))
    assert "LEAST(" not in code
    assert "NEW.game_number := tail::SMALLINT;" in code

    C3 = "00000000-0000-0000-0000-0000000000c3"
    C4 = "00000000-0000-0000-0000-0000000000c4"

    async def go():
        conn = await _raw_pg()
        try:
            await conn.execute(MIGRATION_FIXTURE)
            await conn.execute(sql)
            # Lobby c3 holds 999 and nothing else. MAX + 1 is 1000.
            await conn.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                " ended_at, game_number) VALUES (gen_random_uuid(),"
                " $1, 'c3_r999', NOW(), 999)", C3)
            await conn.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                " ended_at) VALUES (gen_random_uuid(), $1, 'c3_no_tail', NOW())",
                C3)
            fell_back = await conn.fetchrow(
                "SELECT game_number, game_number_source FROM ffa_matches"
                " WHERE photon_room_id = 'c3_no_tail'")
            # ...and it is FREE, not a reuse: c3 now holds two distinct numbers.
            distinct = await conn.fetchval(
                "SELECT COUNT(DISTINCT game_number) FROM ffa_matches"
                " WHERE lobby_id = $1", C3)
            # Lobby c4 holds every number in 1..999: there is nothing to give.
            await conn.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                " ended_at, game_number)"
                " SELECT gen_random_uuid(), $1, 'c4_r' || n, NOW(),"
                "        n::SMALLINT FROM generate_series(1, 999) AS n", C4)
            try:
                await conn.execute(
                    "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                    " ended_at) VALUES (gen_random_uuid(), $1,"
                    " 'c4_no_tail', NOW())", C4)
                why = "accepted"
            except Exception as ex:
                why = str(ex)
                await _unwedge(conn)
            landed = await conn.fetchval(
                "SELECT COUNT(*) FROM ffa_matches WHERE photon_room_id = 'c4_no_tail'")
            return fell_back, distinct, why, landed
        finally:
            await conn.close()

    fell_back, distinct, why, landed = run(go())
    # The fallback: the lobby's lowest free number, flagged as neither the
    # writer's nor the room id's.
    assert int(fell_back["game_number"]) == 1
    assert fell_back["game_number_source"] == "sequence"
    assert distinct == 2                    # 999 and 1, not 999 twice
    # The refusal, for the one input that has no answer — and it names the
    # lobby rather than failing on the CHECK, so an operator reading it knows
    # which sitting is full.
    assert "holds every number in 1..999" in why, why
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
