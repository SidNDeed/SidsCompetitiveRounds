"""Bug 391 — mutation controls for the 1v2 abandoned-series horizon sweep.

#391: a test that has never been seen to fail is decoration. This runner
breaks the sweep one defect at a time and requires the named tests to RED;
then it makes an unrelated edit in the same file and requires every test to
stay GREEN. A suite that reds on both is measuring the file, not the
behaviour.

Run it (the live half needs the DSN or the mutations have nothing to kill):

    BUG391_TEST_PG_DSN=postgresql+asyncpg://postgres@127.0.0.1:55432/scr_bug391 \\
        python backend/tests/bug391_mutation_controls.py

It edits files in place and restores them from in-memory copies plus backup
files. It never runs `git checkout --` or `git restore`: the tree carries
uncommitted work and those commands take the whole path with them (#290 /
#401).

CERTIFICATION covers every file a run USED, not only the module under
mutation (bug 391 r2 finding 6). Round 2 mutates the suite and this runner
too — a defect can live in an assertion as easily as in a statement — so
"main.py came back byte-identical" is no longer a receipt for the harness that
produced the result. Every file in FILES is hashed before and after and every
hash is printed; the run FAILS if any of them moved.
"""

import hashlib
import io
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
MAIN_PY = BACKEND / "api" / "main.py"
TOURNAMENTS_PY = BACKEND / "api" / "tournaments.py"
TESTS = "tests/test_ovt_abandoned_horizon.py"
SUITE_PY = BACKEND / TESTS
RUNNER_PY = Path(__file__).resolve()

# Every file a run reads or edits. The keys are what a mutation edit names.
FILES = {
    "main": MAIN_PY,
    "tournaments": TOURNAMENTS_PY,
    "suite": SUITE_PY,
    "runner": RUNNER_PY,
}

ALL_GREEN = "__ALL_GREEN__"
# Hard wall-clock cap on ONE suite run. The baseline is about two minutes and
# the slowest mutation about two and a half, so this is generous; its job is
# not to be tight but to turn "the campaign stopped and nobody said why" into
# a reported no-verdict that the caller retries.
SUITE_TIMEOUT_S = 420
# The only database this runner and the suite it drives may touch.
EXPECTED_DB = "scr_bug391"

# Each entry: (label, what defect it models, edits, [tests that must red]).
# An edit is ("<file key>", old, new), or (old, new) for main.py.
MUTATIONS = [
    (
        "M1-horizon-off-by-one-day",
        "the horizon is 13 days, not the 14 Sid ruled",
        [("OVT_ABANDONED_HORIZON_DAYS = 14", "OVT_ABANDONED_HORIZON_DAYS = 13")],
        ["test_a_series_one_day_inside_the_horizon_is_untouched",
         "test_the_horizon_is_the_fourteen_days_sid_ruled_for_ranked"],
    ),
    (
        "M2-idleness-from-the-series-row-only",
        "games are not activity: idleness is measured from created_at alone",
        [("""           AND NOT EXISTS (
                 SELECT 1 FROM ovt_matches m
                  WHERE m.series_id = s.id
                    AND GREATEST(m.ended_at, m.created_at)
                        >= NOW() - make_interval(days => CAST(:days AS int)))
         ORDER BY s.created_at""", "         ORDER BY s.created_at"),
         ("""           AND NOT EXISTS (
                 SELECT 1 FROM ovt_matches m
                  WHERE m.series_id = s.id
                    AND GREATEST(m.ended_at, m.created_at)
                        >= NOW() - make_interval(days => CAST(:days AS int)))
    \"\"\"), {"sid": str(series_id), "days": int(days)})).first()""",
          """    \"\"\"), {"sid": str(series_id), "days": int(days)})).first()""")],
        ["test_an_old_series_whose_trio_played_yesterday_is_untouched",
         "test_the_candidate_read_alone_already_excludes_a_series_played_yesterday"],
    ),
    (
        "M2b-candidate-read-stops-filtering",
        "only the under-lock re-check carries the recency term",
        [("""           AND NOT EXISTS (
                 SELECT 1 FROM ovt_matches m
                  WHERE m.series_id = s.id
                    AND GREATEST(m.ended_at, m.created_at)
                        >= NOW() - make_interval(days => CAST(:days AS int)))
         ORDER BY s.created_at""", "         ORDER BY s.created_at")],
        ["test_the_candidate_read_alone_already_excludes_a_series_played_yesterday"],
    ),
    (
        "M3-no-predicate-recheck-in-the-transaction",
        "the candidate list is trusted: no status re-check under the lock, "
        "no status guard on the write. The live interleaving test belongs to "
        "M31 now: round 2's under-lock completion term refuses that row on "
        "its own, so removing the STATUS guard alone no longer changes it",
        [('''    if locked["status"] != "active":
        print(f"[OVT-HORIZON] Candidate already settled under the lock: "
              f"series {series_id} status={locked['status']}")
        return False
''', ""),
         ("""         WHERE id = CAST(:sid AS uuid)
           AND status = 'active'
        RETURNING id""",
          """         WHERE id = CAST(:sid AS uuid)
        RETURNING id""")],
        ["test_the_predicate_is_re_checked_inside_the_transaction"],
    ),
    (
        "M3b-status-is-not-part-of-the-predicate",
        "M3 plus a candidate read that no longer filters on status. Same "
        "note as M3: the live interleaving test is M31's",
        [('''    if locked["status"] != "active":
        print(f"[OVT-HORIZON] Candidate already settled under the lock: "
              f"series {series_id} status={locked['status']}")
        return False
''', ""),
         ("""         WHERE id = CAST(:sid AS uuid)
           AND status = 'active'
        RETURNING id""",
          """         WHERE id = CAST(:sid AS uuid)
        RETURNING id"""),
         ("""         WHERE s.status = 'active'
           AND s.is_ranked = FALSE""",
          """         WHERE s.status IS NOT NULL
           AND s.is_ranked = FALSE""")],
        ["test_sweeping_the_same_row_twice_is_a_no_op"],
    ),
    (
        "M4-lock-mode-for-update",
        "the janitor takes FOR UPDATE, which conflicts with the FK check a "
        "game report takes on the same row",
        [('        " FOR NO KEY UPDATE SKIP LOCKED"',
          '        " FOR UPDATE SKIP LOCKED"')],
        ["test_the_settlement_lock_does_not_block_a_game_reports_fk_insert",
         "test_the_row_lock_is_for_no_key_update"],
    ),
    (
        "M5-credit-the-leader",
        "the sweep completes the series for whoever was ahead instead of voiding it",
        [("""           SET status = 'canceled',
               invalidated_at = NOW(),
               invalidation_reason = 'abandoned_horizon_void'""",
          """           SET status = 'completed',
               winner_side = 1,
               completed_at = NOW(),
               invalidated_at = NOW(),
               invalidation_reason = 'abandoned_horizon_void'""")],
        ["test_the_settlement_writes_neither_completed_at_nor_winner_side",
         "test_a_past_horizon_series_is_voided_and_nobody_is_credited"],
    ),
    (
        "M6-client-stamp-counts-as-activity",
        "the client-supplied started_at is read as activity, so a future-dated "
        "report holds its own series open",
        [("GREATEST(m.ended_at, m.created_at)",
          "GREATEST(m.ended_at, m.created_at, m.started_at)")],
        ["test_a_future_dated_client_stamp_cannot_hold_a_series_open",
         "test_idleness_is_measured_from_server_clock_columns_only"],
    ),
    (
        "M7-the-row-lock-waits-instead-of-declining",
        "the settler waits on a row another transaction holds, so every "
        "janitor arm behind it in that tick stops running",
        [('        " FOR NO KEY UPDATE SKIP LOCKED"',
          '        " FOR NO KEY UPDATE"')],
        ["test_a_row_another_transaction_holds_is_declined_not_waited_for",
         "test_the_row_lock_declines_a_held_row_instead_of_waiting_for_it"],
    ),
    (
        "M8-the-tick-has-no-time-budget",
        "the arm waits out a table-level lock, holding the janitor loop",
        [("""    done, _pending = await asyncio.wait({task},
                                        timeout=OVT_HORIZON_TICK_BUDGET_S)""",
          "    done, _pending = await asyncio.wait({task})")],
        ["test_the_tick_gives_the_janitor_loop_back_when_the_table_is_locked",
         "test_the_tick_gives_the_loop_back_inside_a_bounded_budget",
         # Round 2: the single-flight cases drive the tick against a sweep
         # that never finishes, so they depend on this budget too. They carry
         # their own wall-clock bound now, which is why removing the budget
         # REDS them instead of hanging the run (a control that hangs gives no
         # verdict at all).
         "test_a_tick_declines_while_the_previous_one_is_still_in_flight",
         "test_the_single_flight_decline_says_so_on_its_own_line"],
    ),
    (
        "M9-the-sweep-stops-distinguishing-ranked",
        "a ranked 1v2 series is voided by the unranked rule instead of being "
        "left for the settlement Sid ruled (the leader takes the rating)",
        [("           AND s.is_ranked = FALSE\n", "")],
        ["test_a_ranked_series_past_the_horizon_is_left_active_and_counted",
         "test_a_ranked_series_is_refused_by_both_halves_of_the_predicate"],
    ),
    (
        "M10-the-arm-stops-announcing-itself",
        "the deploy loses its positive signal and falls back on a "
        "self-test banner that prints on any build",
        [("""    if not _ovt_horizon_armed_logged:
        _ovt_horizon_armed_logged = True
        print(f"[OVT-HORIZON] armed: horizon={OVT_ABANDONED_HORIZON_DAYS}d "
              f"cap={OVT_HORIZON_SWEEP_LIMIT} "
              f"budget={OVT_HORIZON_TICK_BUDGET_S}s reason="
              f"abandoned_horizon_void")
""", "")],
        ["test_the_arm_announces_itself_once_per_process"],
    ),
    (
        "M11-the-continuation-window-swallows-the-horizon",
        "the window is 30 days, so a voided row WOULD re-enter the "
        "continuation path — the claim the notes may not make while it is 60m",
        [("_CONTINUATION_WINDOW_MINUTES = 60  #",
          "_CONTINUATION_WINDOW_MINUTES = 60 * 24 * 30  #")],
        ["test_the_void_cannot_put_a_row_back_inside_the_continuation_window"],
    ),
    (
        "M12-earned-packs-stop-being-completion-gated",
        "the Player Cards reconciler grants for a series that is not "
        "completed, so this arm's invalidated_at starts voiding real packs",
        [("""         WHERE os.status = 'completed' AND os.invalidated_at IS NULL AND os.winner_side IN (1, 2)""",
          """         WHERE os.invalidated_at IS NULL AND os.winner_side IN (1, 2)""")],
        ["test_the_ovt_earned_pack_paths_are_completion_gated"],
    ),
    # ── round 2 ──────────────────────────────────────────────────────────
    #
    # Every entry below closes a round-1 finding and every one of them is
    # PAIRED with an inert twin at the SAME site: an edit of the same shape
    # that must stay green. A red with no green twin beside it proves only
    # that something moved (#391).
    (
        "M13-no-row-lock-at-all",
        "r2 finding 10 / B13: the concurrency experiment the diagnosis asked "
        "for — the settler takes NO row lock, so it cannot decline and its "
        "write waits on whoever holds the row",
        [('        " FOR NO KEY UPDATE SKIP LOCKED"', '        ""')],
        ["test_a_row_another_transaction_holds_is_declined_not_waited_for",
         "test_the_row_lock_is_for_no_key_update"],
    ),
    (
        "M13-TWIN-lock-clause-reflowed",
        "inert twin at the M13 site: the same clause, spaced differently",
        [('        " FOR NO KEY UPDATE SKIP LOCKED"',
          '        "  FOR NO KEY UPDATE  SKIP LOCKED"')],
        [ALL_GREEN],
    ),
    (
        "M14-the-settled-arm-stops-paying-the-game",
        "r2 finding 1 / B14: the report records the match and returns above "
        "the per-game award, so all three seats lose a game they played",
        [("            _res_a, _lbl_a = await _award_the_game()",
          "            _res_a, _lbl_a = ({}, {})")],
        ["test_a_report_landing_on_a_settled_series_still_pays_that_game"],
    ),
    (
        "M14-TWIN-settled-arm-log-wording",
        "inert twin at the M14 site: the same branch, different log wording",
        [("{series_uuid} landed on a ", "{series_uuid} arrived at a ")],
        [ALL_GREEN],
    ),
    (
        "M15-the-report-lock-declines-instead-of-waiting",
        "r2 finding 1: the report sink stops serialising with the janitor and "
        "answers on a row version it did not wait to see",
        [('"SELECT * FROM ovt_series WHERE id = :sid FOR NO KEY UPDATE"',
          '"SELECT * FROM ovt_series WHERE id = :sid FOR NO KEY UPDATE SKIP LOCKED"')],
        ["test_the_report_sinks_series_lock_waits_so_the_void_cannot_be_missed",
         "test_the_void_and_a_report_serialise_on_the_same_series_row"],
    ),
    (
        "M15-TWIN-report-lock-reflowed",
        "inert twin at the M15 site: the same statement, spaced differently",
        [('"SELECT * FROM ovt_series WHERE id = :sid FOR NO KEY UPDATE"',
          '"SELECT *  FROM ovt_series  WHERE id = :sid  FOR NO KEY UPDATE"')],
        [ALL_GREEN],
    ),
    (
        "M16-a-completion-stamp-stops-being-refused",
        "r2 finding 2 / B5: an `active` row carrying a recent completed_at is "
        "voided, and the continuation then accepts it as a prior",
        [("           AND s.completed_at IS NULL\n", "")],
        ["test_both_halves_of_the_predicate_refuse_a_completion_stamp",
         "test_an_active_row_carrying_a_completion_stamp_is_declined"],
    ),
    (
        "M16-TWIN-completion-term-parenthesised",
        "inert twin at the M16 site: the same term, written with brackets",
        [("           AND s.completed_at IS NULL\n",
          "           AND (s.completed_at IS NULL)\n")],
        [ALL_GREEN],
    ),
    (
        "M17-the-declined-rows-stop-being-counted",
        "r2 finding 2: the refusal becomes a silent filter, so the set it "
        "leaves behind is invisible",
        [("""        stamped = await _ovt_horizon_stamped_backlog(
            db, OVT_ABANDONED_HORIZON_DAYS)""", "        stamped = -1")],
        ["test_the_declined_stamp_rows_are_counted_not_silently_filtered",
         "test_an_active_row_carrying_a_completion_stamp_is_declined"],
    ),
    (
        "M17-TWIN-declined-rows-log-wording",
        "inert twin at the M17 site: the same count, different wording",
        [("horizon left ACTIVE: they carry a completed_at while ",
          "horizon still ACTIVE: they carry a completed_at while ")],
        [ALL_GREEN],
    ),
    (
        "M18-no-single-flight-guard",
        "r2 finding 3: every tick starts another sweep behind a stalled one, "
        "so pooled connections accumulate until database work starves",
        [("""    global _ovt_horizon_tick_inflight
    if _ovt_horizon_tick_inflight is not None:
        print(f"[OVT-HORIZON] tick declined: the previous tick is still in "
              f"flight (cancelled at {OVT_HORIZON_TICK_BUDGET_S}s and not yet "
              f"unwound); one sweep per process, next tick retries")
        return 0
""", "    global _ovt_horizon_tick_inflight\n")],
        ["test_a_tick_declines_while_the_previous_one_is_still_in_flight",
         "test_the_single_flight_decline_says_so_on_its_own_line"],
    ),
    (
        "M18-TWIN-single-flight-decline-wording",
        "inert twin at the M18 site: the same decline, different tail",
        [("unwound); one sweep per process, next tick retries",
          "unwound); one sweep per process; the next tick retries")],
        [ALL_GREEN],
    ),
    (
        "M19-the-census-goes-blind-to-orm-locks",
        "r2 finding 4 / B6: the lock census cannot see `.with_for_update(...)` "
        "and certifies a wait count that omits a reachable unbounded waiter",
        [('and node.func.attr == "with_for_update"):',
          'and node.func.attr == "with_for_update_unreachable"):')],
        ["test_the_janitor_lock_census_sees_orm_locks_and_not_only_sql",
         "test_a_lock_taking_path_outside_the_counted_set_reds_the_census"],
    ),
    (
        "M19-TWIN-orm-collector-local-rewritten",
        "inert twin at the M19 site: the same collector, same behaviour",
        [("            declines = False\n", "            declines = bool(0)\n")],
        [ALL_GREEN],
    ),
    (
        "M20-an-unprovable-lock-mode-is-certified-as-declining",
        "r2 finding 4: a keyword the walk cannot evaluate is counted as a "
        "decline, which is the one direction a lock census may not err in",
        [("""                    if isinstance(kw.value, _ast.Constant) and kw.value.value:
                        declines = True""",
          "                    declines = True")],
        ["test_a_lock_taking_path_outside_the_counted_set_reds_the_census"],
    ),
    (
        "M20-TWIN-lock-keyword-set-rewritten",
        "inert twin at the M20 site: the same two keywords, listed",
        [('if kw.arg in ("skip_locked", "nowait"):',
          'if kw.arg in ["skip_locked", "nowait"]:')],
        [ALL_GREEN],
    ),
    (
        "M21-the-ranked-backlog-ignores-recent-play",
        "r2 finding 7 / B3: a 20-day-old ranked series played this morning is "
        "counted past the idle horizon and warns about an unbuilt settlement",
        [("""           AND s.is_ranked = TRUE
           AND s.created_at < NOW() - make_interval(days => CAST(:days AS int))
           AND NOT EXISTS (
                 SELECT 1 FROM ovt_matches m
                  WHERE m.series_id = s.id
                    AND GREATEST(m.ended_at, m.created_at)
                        >= NOW() - make_interval(days => CAST(:days AS int)))""",
          """           AND s.is_ranked = TRUE
           AND s.created_at < NOW() - make_interval(days => CAST(:days AS int))""")],
        ["test_a_ranked_series_played_today_is_not_a_backlog_warning"],
    ),
    (
        "M21-TWIN-ranked-term-parenthesised",
        "inert twin at the M21 site: the same ranked term, with brackets",
        [("           AND s.is_ranked = TRUE\n",
          "           AND (s.is_ranked = TRUE)\n")],
        [ALL_GREEN],
    ),
    (
        "M22-the-suite-caller-loses-its-database-guard",
        "r2 finding 5 / F4: the fixture terminates and DROPs without asking "
        "which database it is pointed at; the helper's own test stays green",
        [("suite", """        # Before the terminate, not after it: the refusal has to come first or
        # it is documentation.
        await _assert_dedicated_db(conn)
""", """        # Before the terminate, not after it: the refusal has to come first or
        # it is documentation.
""")],
        ["test_the_destructive_callers_are_guarded_not_only_the_helper"],
    ),
    (
        "M22-TWIN-suite-guard-comment-reworded",
        "inert twin at the M22 site: the guard stays, the comment changes",
        [("suite",
          "        # Before the terminate, not after it: the refusal has to come first or",
          "        # Before the terminate, never after it: the refusal comes first or")],
        [ALL_GREEN],
    ),
    (
        "M23-the-runner-caller-loses-its-database-guard",
        "r2 finding 5 / F4: this runner terminates every backend on whatever "
        "database the DSN names without comparing the name",
        [("runner", "                if dbname != EXPECTED_DB:",
          "                if dbname is None:")],
        ["test_the_destructive_callers_are_guarded_not_only_the_helper"],
    ),
    (
        "M23-TWIN-runner-guard-message-reworded",
        "inert twin at the M23 site: the refusal stays, its wording changes",
        [("runner", "                        f\"this runner terminates every backend on it and the \"",
          "                        f\"this runner terminates each backend on it and the \"")],
        [ALL_GREEN],
    ),
    (
        "M24-certification-narrows-back-to-one-file",
        "r2 finding 6: the post-run receipt stops covering the harness, so a "
        "changed assertion leaves a true main.py MATCH behind it",
        [("runner", '    "suite": SUITE_PY,\n    "runner": RUNNER_PY,\n',
          '    "suite": SUITE_PY,\n')],
        ["test_the_mutation_runner_certifies_every_file_a_run_used"],
    ),
    (
        "M24-TWIN-certification-map-reordered",
        "inert twin at the M24 site: the same four files, listed in another "
        "order",
        [("runner", '    "main": MAIN_PY,\n    "tournaments": TOURNAMENTS_PY,\n',
          '    "tournaments": TOURNAMENTS_PY,\n    "main": MAIN_PY,\n')],
        [ALL_GREEN],
    ),
    (
        "M32-the-receipt-names-a-file-instead-of-walking-the-map",
        "r2 finding 6, second half: the post-run receipt stops iterating the "
        "certified set, so the files it no longer visits are reported by "
        "nobody while the one it kept still reads MATCH",
        [("runner", "    for key in FILES:\n", "    for key in (\"main\",):\n")],
        ["test_the_mutation_runner_certifies_every_file_a_run_used"],
    ),
    (
        "M32-TWIN-receipt-comparison-reordered",
        "inert twin at the M32 site: the same comparison, the two sides "
        "swapped",
        [("runner", "        ok = after == digests[key]",
          "        ok = digests[key] == after")],
        [ALL_GREEN],
    ),
    (
        "M25-a-source-citation-goes-one-line-stale",
        "r2 finding 11 / B7: a line pin reaches a neighbouring statement, so "
        "following it conceals the regression it was written to catch",
        [('PIN main.py:3844 "SELECT status FROM ovt_series '
          'WHERE id = CAST(:sid AS uuid)"',
          'PIN main.py:3845 "SELECT status FROM ovt_series '
          'WHERE id = CAST(:sid AS uuid)"')],
        ["test_every_bug391_source_citation_resolves_to_what_it_names"],
    ),
    (
        "M25-TWIN-citation-prose-reworded",
        "inert twin at the M25 site: the pin stands, the sentence around it "
        "changes",
        [("So the two can\n    # never both decide this row",
          "So they can\n    # never both decide this row")],
        [ALL_GREEN],
    ),
    (
        "M26-a-status-reader-leaves-the-census",
        "r2 finding 13 / F5: a reader of ovt_series.status disappears and the "
        "corrected census still calls itself complete",
        [("""        SELECT * FROM ovt_series
         WHERE status = 'active'
           AND (solo_id = :pid""",
          """        SELECT * FROM ovt_series
         WHERE (solo_id = :pid""")],
        ["test_the_ovt_series_status_reader_census_stays_complete"],
    ),
    (
        "M26-TWIN-status-reader-parenthesised",
        "inert twin at the M26 site: the same reader, with brackets",
        [("""        SELECT * FROM ovt_series
         WHERE status = 'active'
           AND (solo_id = :pid""",
          """        SELECT * FROM ovt_series
         WHERE (status = 'active')
           AND (solo_id = :pid""")],
        [ALL_GREEN],
    ),
    (
        "M27-the-earned-pack-grant-moves-above-the-completion-write",
        "r2 finding 9 / F7: the inline grant runs BEFORE the series is written "
        "'completed', which the round-1 same-function text check cannot see",
        [("""        await db.execute(text(
            "UPDATE ovt_series SET status='completed', winner_side=:ws, completed_at=NOW() WHERE id=:sid"
        ), {"ws": winner_side, "sid": series_uuid})
        # Player Cards (WP-D): the earned-pack roll for the completed series""",
          "        # Player Cards (WP-D): the earned-pack roll for the completed series"),
         ("""        except Exception as pcex:
            print(f"[PC-EARNED] ovt grant failed for {series_uuid}: {pcex}")""",
          """        except Exception as pcex:
            print(f"[PC-EARNED] ovt grant failed for {series_uuid}: {pcex}")
        await db.execute(text(
            "UPDATE ovt_series SET status='completed', winner_side=:ws, completed_at=NOW() WHERE id=:sid"
        ), {"ws": winner_side, "sid": series_uuid})""")],
        ["test_the_ovt_earned_pack_grant_is_dominated_by_the_completion_write"],
    ),
    (
        "M27-TWIN-grant-failure-log-reworded",
        "inert twin at the M27 site: the same two statements in the same "
        "order, one log line reworded",
        [('print(f"[PC-EARNED] ovt grant failed for {series_uuid}: {pcex}")',
          'print(f"[PC-EARNED] ovt grant did not complete for {series_uuid}: {pcex}")')],
        [ALL_GREEN],
    ),
    (
        "M28-the-settled-arm-advances-the-series-tally",
        "r2 finding 1: paying a late game also resurrects the score of a "
        "series that was already settled",
        [("""                UPDATE ovt_series SET
                    solo_xp_earned = solo_xp_earned + :sx,""",
          """                UPDATE ovt_series SET
                    solo_series_wins = solo_series_wins + 1,
                    solo_xp_earned = solo_xp_earned + :sx,""")],
        ["test_the_settled_without_play_arm_never_moves_the_series_tally"],
    ),
    (
        "M28-TWIN-settled-ledger-columns-reordered",
        "inert twin at the M28 site: the same six columns, listed in another "
        "order",
        [("""                    solo_xp_earned = solo_xp_earned + :sx,
                    duo_a_xp_earned = duo_a_xp_earned + :ax,""",
          """                    duo_a_xp_earned = duo_a_xp_earned + :ax,
                    solo_xp_earned = solo_xp_earned + :sx,""")],
        [ALL_GREEN],
    ),
    (
        "M29-the-seat-award-pays-in-slot-order",
        "r2 finding 1: the three players-row tuple locks stop following one "
        "global order across concurrent completions (#197)",
        [("    for pid in sorted([solo_id, duo_a_id, duo_b_id], key=str):",
          "    for pid in [solo_id, duo_a_id, duo_b_id]:")],
        ["test_the_seat_award_pays_all_three_seats_in_canonical_order"],
    ),
    (
        "M29-TWIN-canonical-key-rewritten",
        "inert twin at the M29 site: the same order, a different spelling of "
        "the key",
        [("    for pid in sorted([solo_id, duo_a_id, duo_b_id], key=str):",
          "    for pid in sorted([solo_id, duo_a_id, duo_b_id], key=lambda p: str(p)):")],
        [ALL_GREEN],
    ),
    (
        "M30-the-two-database-guards-stop-agreeing",
        "r2 finding 5: the runner and the suite name different databases, so "
        "one of the two guards protects nothing it is asked about",
        [("runner", 'EXPECTED_DB = "scr_bug391"', 'EXPECTED_DB = "scr_bug391_elsewhere"')],
        ["test_both_destructive_callers_name_the_same_dedicated_database"],
    ),
    (
        "M30-TWIN-runner-database-constant-recommented",
        "inert twin at the M30 site: the same constant, a different comment",
        [("runner",
          "# The only database this runner and the suite it drives may touch.",
          "# The one database this runner and the suite it drives may touch.")],
        [ALL_GREEN],
    ),
    (
        "M31-the-candidate-list-is-trusted-on-both-terms",
        "the under-lock re-check loses BOTH of its refusals at once - the "
        "status guard and the round-2 completion term - which is what 'the "
        "candidate list is trusted' has to mean now that the settle path "
        "refuses a completed row twice over",
        [('''    if locked["status"] != "active":
        print(f"[OVT-HORIZON] Candidate already settled under the lock: "
              f"series {series_id} status={locked['status']}")
        return False
''', ""),
         ("""         WHERE id = CAST(:sid AS uuid)
           AND status = 'active'
        RETURNING id""",
          """         WHERE id = CAST(:sid AS uuid)
        RETURNING id"""),
         ("""         WHERE s.id = CAST(:sid AS uuid)
           AND s.is_ranked = FALSE
           AND s.completed_at IS NULL""",
          """         WHERE s.id = CAST(:sid AS uuid)
           AND s.is_ranked = FALSE""")],
        ["test_a_report_completing_the_series_before_the_lock_wins"],
    ),
    (
        "M31-TWIN-under-lock-terms-reordered",
        "inert twin at the M31 site: the same two terms of the under-lock "
        "re-check, in the other order",
        [("""         WHERE s.id = CAST(:sid AS uuid)
           AND s.is_ranked = FALSE
           AND s.completed_at IS NULL""",
          """         WHERE s.id = CAST(:sid AS uuid)
           AND s.completed_at IS NULL
           AND s.is_ranked = FALSE""")],
        [ALL_GREEN],
    ),
    (
        "M33-the-settled-arm-drops-its-game-bound",
        "r2 finding 1, third half: the arm that pays a late game carries no "
        "bound on how many games one settled series may be paid for, while "
        "the live arm is bounded by the tally that resolves the series",
        [("""        if (series["status"] in _OVT_SETTLED_WITHOUT_PLAY
                and _within_series_bound):
""", """        if series["status"] in _OVT_SETTLED_WITHOUT_PLAY:
""")],
        ["test_the_settled_arm_pays_no_more_games_than_the_sitting_can_have"],
    ),
    (
        "M33-TWIN-game-bound-operands-reordered",
        "inert twin at the M33 site: the same two terms, other way round",
        [("""        if (series["status"] in _OVT_SETTLED_WITHOUT_PLAY
                and _within_series_bound):
""", """        if (_within_series_bound
                and series["status"] in _OVT_SETTLED_WITHOUT_PLAY):
""")],
        [ALL_GREEN],
    ),
    (
        "M34-the-two-paying-arms-stop-sharing-one-constant",
        "r2 finding 1, third half: the live arm goes back to a bare literal, "
        "so the bound the settled arm reads and the bound the live arm "
        "enforces are two numbers that must agree and nothing checks it",
        [("""    series_done = (solo_wins >= OVT_SERIES_WINS_REQUIRED
                   or duo_wins >= OVT_SERIES_WINS_REQUIRED)
""", """    series_done = solo_wins >= 2 or duo_wins >= 2
""")],
        ["test_the_settled_arm_pays_no_more_games_than_the_sitting_can_have"],
    ),
    (
        "M34-TWIN-live-bound-operands-reordered",
        "inert twin at the M34 site: same constant, operands swapped",
        [("""    series_done = (solo_wins >= OVT_SERIES_WINS_REQUIRED
                   or duo_wins >= OVT_SERIES_WINS_REQUIRED)
""", """    series_done = (duo_wins >= OVT_SERIES_WINS_REQUIRED
                   or solo_wins >= OVT_SERIES_WINS_REQUIRED)
""")],
        [ALL_GREEN],
    ),
    (
        "M35-the-bound-declines-an-award-in-silence",
        "r2 finding 1, third half: the refusal stops naming its reason on the "
        "log line, so a game that was played and not paid leaves no record "
        "distinguishing it from a status this path never pays",
        [('f"series resolved as status={series[\'status\']} ({_why_unpaid}), '
          'which this path does "',
          'f"series resolved as status={series[\'status\']}, '
          'which this path does "')],
        ["test_the_settled_arm_pays_no_more_games_than_the_sitting_can_have"],
    ),
    (
        "M35-TWIN-refusal-reason-reworded",
        "inert twin at the M35 site: the reason is still named, other wording",
        [("f\"the series already carries {_games_recorded} recorded games, \"",
          "f\"this series already carries {_games_recorded} recorded games, \"")],
        [ALL_GREEN],
    ),
    (
        "M36-a-citation-anchor-stops-being-unique",
        "r2 finding 11: the pin names a line that really does carry the "
        "anchor, but two other lines carry it too, so the citation can drift "
        "onto either of them and still resolve",
        [('PIN main.py:3844 "SELECT status FROM ovt_series '
          'WHERE id = CAST(:sid AS uuid)"',
          'PIN main.py:3845 " FOR NO KEY UPDATE SKIP LOCKED"')],
        ["test_every_bug391_source_citation_resolves_to_what_it_names"],
    ),
    (
        "M36-TWIN-citation-lead-in-reworded",
        "inert twin at the M36 site: the pin stands, its lead-in changes",
        [("# — its locking read is\n",
          "# — the janitor's locking read is\n")],
        [ALL_GREEN],
    ),
    (
        "M37-an-award-input-is-bound-only-on-the-live-path",
        "added row B16 (sibling sweep of finding 9, #432): a name the paying "
        "arm reads is bound inside a branch the settled path skips, so the "
        "arm raises NameError AFTER the match row is inserted and the game is "
        "recorded but never paid — finding 1's outcome, reintroduced",
        [("    _ovt_pod = set(await _ovt_podium_ids(db))",
          "    if series[\"status\"] == \"active\":\n"
          "        _ovt_pod = set(await _ovt_podium_ids(db))")],
        ["test_the_settled_arm_pays_with_names_that_are_bound_before_it"],
    ),
    (
        "M37-TWIN-award-input-expression-rewritten",
        "inert twin at the M37 site: the same binding on the same path, the "
        "set built by a comprehension instead of a call",
        [("    _ovt_pod = set(await _ovt_podium_ids(db))",
          "    _ovt_pod = {_p for _p in await _ovt_podium_ids(db)}")],
        [ALL_GREEN],
    ),
    (
        "M38-single-settlement-loses-BOTH-of-the-things-that-carry-it",
        "r2 finding 10 / B13: the single-settlement property the diagnosis "
        "named is carried JOINTLY by the declining row lock and the write's "
        "own status guard. Removing either alone leaves it intact (which is "
        "what the specified experiment actually measured - see the round-2 "
        "notes deviation DEV-R2-5); removing BOTH lets two concurrent sweeps "
        "settle one row twice",
        [('        " FOR NO KEY UPDATE SKIP LOCKED"', '        ""'),
         ("""         WHERE id = CAST(:sid AS uuid)
           AND status = 'active'
        RETURNING id""",
          """         WHERE id = CAST(:sid AS uuid)
        RETURNING id""")],
        ["test_two_concurrent_sweeps_settle_the_row_exactly_once"],
    ),
    (
        "M38-TWIN-both-carriers-rewritten-in-place",
        "inert twin at the two M38 sites: the same lock clause spaced "
        "differently and the same guard parenthesised - both still carry it",
        [('        " FOR NO KEY UPDATE SKIP LOCKED"',
          '        "  FOR NO KEY UPDATE  SKIP LOCKED"'),
         ("""         WHERE id = CAST(:sid AS uuid)
           AND status = 'active'
        RETURNING id""",
          """         WHERE id = CAST(:sid AS uuid)
           AND (status = 'active')
        RETURNING id""")],
        [ALL_GREEN],
    ),
    # ── round 3: the round-2 HIGH (at-most-once across the seat orders the
    # sink accepts), closed at the class. The two new controls the brief
    # names are M42 (the same-room replay after a void with the pair
    # reversed) and M40 (two inserts of one game from the two orders of the
    # pair); every other entry below covers one carrier or one sibling.
    # Every round-3 edit keeps the line count, so no source citation moves
    # and each kill set names only what the defect itself breaks (#712).
    (
        "M39-the-report-keeps-the-order-its-duo-pair-arrived-in",
        "r3 H1 (a): the sink stops putting the duo pair in canonical order, "
        "so a report whose pair arrives reversed is compared and stored in "
        "that order, and the ordered key cannot conflict with the same game "
        "stored in the other order",
        [("    report = _ovt_canonical_duo(report)\n",
          "    # report = _ovt_canonical_duo(report)\n")],
        ["test_the_report_is_canonicalised_before_any_slot_comparison_or_write",
         "test_a_report_arriving_with_its_pair_reversed_is_recorded_in_canonical_order",
         "test_a_report_that_reaches_the_insert_anyway_is_answered_as_already_recorded"],
    ),
    (
        "M39-TWIN-canonical-form-called-by-keyword",
        "inert twin at the M39 site: the same call, its argument by keyword",
        [("    report = _ovt_canonical_duo(report)\n",
          "    report = _ovt_canonical_duo(report=report)\n")],
        [ALL_GREEN],
    ),
    (
        "M40-the-canonical-form-never-reorders",
        "r3 H1 (a), the database-level control (the brief's second new "
        "control): the helper hands every report back as it arrived, so two "
        "inserts of one game built from the two orders of the pair carry two "
        "different keys and both land",
        [("    if report.duo_a.steam_id <= report.duo_b.steam_id:\n",
          "    if True:\n")],
        ["test_the_duo_pair_is_put_in_one_order_and_every_seat_field_travels_with_it",
         "test_every_slot_pair_comparison_in_the_report_and_void_paths_is_accounted_for",
         "test_a_report_arriving_with_its_pair_reversed_is_recorded_in_canonical_order",
         "test_the_key_conflicts_on_either_order_of_the_duo_pair",
         "test_a_report_that_reaches_the_insert_anyway_is_answered_as_already_recorded"],
    ),
    (
        "M40-TWIN-canonical-comparison-written-as-its-converse",
        "inert twin at the M40 site: the same order, written as the negated "
        "converse comparison",
        [("    if report.duo_a.steam_id <= report.duo_b.steam_id:\n",
          "    if not report.duo_b.steam_id < report.duo_a.steam_id:\n")],
        [ALL_GREEN],
    ),
    (
        "M40b-a-seat-field-stays-behind-when-its-player-moves",
        "r3 H1 (a): the pair is reordered but the two fps averages are not, "
        "so each duo player's stored fps is the other player's",
        [('        "duo_a_fps": report.duo_b_fps, "duo_b_fps": report.duo_a_fps,\n',
          "        # the two fps averages stay in the seats they arrived in\n")],
        ["test_the_duo_pair_is_put_in_one_order_and_every_seat_field_travels_with_it",
         "test_a_report_arriving_with_its_pair_reversed_is_recorded_in_canonical_order"],
    ),
    (
        "M40b-TWIN-seat-fields-listed-the-other-way-round",
        "inert twin at the M40b site: the same two fps entries, in the other "
        "order",
        [('        "duo_a_fps": report.duo_b_fps, "duo_b_fps": report.duo_a_fps,\n',
          '        "duo_b_fps": report.duo_a_fps, "duo_a_fps": report.duo_b_fps,\n')],
        [ALL_GREEN],
    ),
    (
        "M41-the-replay-check-compares-the-seats-in-order",
        "r3 H1 (b): the replay check asks for the three players in the SAME "
        "seats instead of as a set, so a second report of a recorded game "
        "naming another solo is recorded again (the key cannot see it "
        "either), and so is a room on record with its pair in the other order",
        [("           AND ARRAY[solo_id, duo_a_id, duo_b_id] @> CAST(:trio AS uuid[])\n"
          "           AND ARRAY[solo_id, duo_a_id, duo_b_id] <@ CAST(:trio AS uuid[])\n",
          "           AND ARRAY[solo_id, duo_a_id, duo_b_id] = CAST(:trio AS uuid[])\n"
          "           AND TRUE\n")],
        ["test_every_slot_pair_comparison_in_the_report_and_void_paths_is_accounted_for",
         "test_a_room_on_record_in_any_seat_order_is_answered_as_already_recorded",
         "test_two_reports_of_one_room_under_two_series_take_turns_on_the_room_lock"],
    ),
    (
        "M41-TWIN-set-halves-in-the-other-order",
        "inert twin at the M41 site: the two containment halves swapped",
        [("           AND ARRAY[solo_id, duo_a_id, duo_b_id] @> CAST(:trio AS uuid[])\n"
          "           AND ARRAY[solo_id, duo_a_id, duo_b_id] <@ CAST(:trio AS uuid[])\n",
          "           AND ARRAY[solo_id, duo_a_id, duo_b_id] <@ CAST(:trio AS uuid[])\n"
          "           AND ARRAY[solo_id, duo_a_id, duo_b_id] @> CAST(:trio AS uuid[])\n")],
        [ALL_GREEN],
    ),
    (
        "M42-the-HIGH-reproduced-the-canonicalisation-removed",
        "r3 H1, the round-2 HIGH itself (the brief's first new control): the "
        "canonicalisation removed from BOTH places that carry it, the "
        "canonical order before the key and the order-free form of the "
        "replay check, so after a void the same game reported again with its "
        "duo pair reversed misses both, is recorded a second time and paid a "
        "second time. Either carrier alone holds this case (M39 and M41 leave "
        "it green): the joint-carrier shape of DEV-R2-5, recorded as DEV-R3-1",
        [("    report = _ovt_canonical_duo(report)\n",
          "    # report = _ovt_canonical_duo(report)\n"),
         ("           AND ARRAY[solo_id, duo_a_id, duo_b_id] @> CAST(:trio AS uuid[])\n"
          "           AND ARRAY[solo_id, duo_a_id, duo_b_id] <@ CAST(:trio AS uuid[])\n",
          "           AND ARRAY[solo_id, duo_a_id, duo_b_id] = CAST(:trio AS uuid[])\n"
          "           AND TRUE\n")],
        ["test_a_reversed_pair_replay_after_a_void_is_recorded_and_paid_once"],
    ),
    (
        "M42-TWIN-both-carriers-rewritten-in-place",
        "inert twin at the two M42 sites: the call by keyword and the set "
        "halves swapped; both still carry it",
        [("    report = _ovt_canonical_duo(report)\n",
          "    report = _ovt_canonical_duo(report=report)\n"),
         ("           AND ARRAY[solo_id, duo_a_id, duo_b_id] @> CAST(:trio AS uuid[])\n"
          "           AND ARRAY[solo_id, duo_a_id, duo_b_id] <@ CAST(:trio AS uuid[])\n",
          "           AND ARRAY[solo_id, duo_a_id, duo_b_id] <@ CAST(:trio AS uuid[])\n"
          "           AND ARRAY[solo_id, duo_a_id, duo_b_id] @> CAST(:trio AS uuid[])\n")],
        [ALL_GREEN],
    ),
    (
        "M43-reports-of-one-room-stop-taking-turns",
        "r3 H1 (b): the room lock is no longer taken (the statement still "
        "runs, lock-free), so two reports of one room under two series ids "
        "both run the replay check before either commits and both record; "
        "with another solo named, no key order makes them conflict",
        [('"SELECT pg_advisory_xact_lock(CAST(:cls AS integer), '
          'hashtext(CAST(:room AS text)))"',
          '"SELECT CAST(:cls AS integer), hashtext(CAST(:room AS text))"')],
        ["test_the_report_is_canonicalised_before_any_slot_comparison_or_write",
         "test_two_reports_of_one_room_under_two_series_take_turns_on_the_room_lock"],
    ),
    (
        "M43-TWIN-room-lock-statement-respaced",
        "inert twin at the M43 site: the same lock, its SQL spaced differently",
        [('hashtext(CAST(:room AS text)))"', 'hashtext( CAST(:room AS text) ))"')],
        [ALL_GREEN],
    ),
    (
        "M44-the-award-reads-one-duo-seat-for-the-podium",
        "r3 sibling sweep (#432): the award asks only whether the duo_a "
        "player is on the podium, so the solo seat's multiplier depends on "
        "which duo seat a podium player arrived in",
        [("    duo_pod = (str(duo_a_id) in podium) or (str(duo_b_id) in podium)\n",
          "    duo_pod = (str(duo_a_id) in podium)\n")],
        ["test_every_slot_pair_comparison_in_the_report_and_void_paths_is_accounted_for",
         "test_the_seat_award_does_not_depend_on_which_duo_seat_a_player_arrives_in"],
    ),
    (
        "M44-TWIN-podium-operands-swapped",
        "inert twin at the M44 site: the same two memberships, in the other "
        "order",
        [("    duo_pod = (str(duo_a_id) in podium) or (str(duo_b_id) in podium)\n",
          "    duo_pod = (str(duo_b_id) in podium) or (str(duo_a_id) in podium)\n")],
        [ALL_GREEN],
    ),
    (
        "M45-an-unclassified-slot-comparison-joins-the-handler",
        "r3 sibling sweep (#432), the census's own control: a new comparison "
        "of a duo seat joins the handler (behaviour-neutral: the three "
        "distinct players check it rides on already refuses the case), and "
        "the sweep must notice it has not been classified",
        [("    if len(steams) != 3:\n",
          "    if len(steams) != 3 or report.duo_a.steam_id == report.solo.steam_id:\n")],
        ["test_every_slot_pair_comparison_in_the_report_and_void_paths_is_accounted_for"],
    ),
    (
        "M45-TWIN-a-comment-names-the-duo-seats",
        "inert twin at the M45 site: a trailing comment naming duo_a and "
        "duo_b, which the census must not count",
        [("    if len(steams) != 3:\n",
          "    if len(steams) != 3:  # solo, duo_a and duo_b must be distinct\n")],
        [ALL_GREEN],
    ),
    # ── round 4: the round-3 HIGH (a report from another room that moved
    # another of the three players into the solo seat after a recorded game
    # was logged and recorded), closed by refusing it before any write. M46
    # disables the refusal, which restores the old log-and-record branch; its
    # twin writes the same condition behind an inert conjunct. Both keep the
    # line count, as every round-3 edit does.
    (
        "M46-a-mid-series-solo-change-is-recorded-again",
        "r4 H1, the round-3 HIGH itself: the refusal of a report whose solo "
        "seat differs from the series' after a recorded game is disabled, so "
        "the report falls through to the old log-and-record branch; a report "
        "from another room moving a duo member into the solo seat then "
        "advances the tally, pays the winner's bonus to the new solo and the "
        "winner's pack to the stored one, and on a series settled without "
        "play it is paid as a late game under that split",
        [('        elif solo_id != series["solo_id"]:\n',
          '        elif False and solo_id != series["solo_id"]:\n')],
        ["test_a_report_moving_a_player_into_the_solo_seat_mid_series_is_refused",
         "test_a_settled_series_refuses_a_report_moving_the_solo_seat_too"],
    ),
    (
        "M46-TWIN-the-refusal-condition-behind-an-inert-conjunct",
        "inert twin at the M46 site: the same condition behind a conjunct "
        "that is always true",
        [('        elif solo_id != series["solo_id"]:\n',
          '        elif True and solo_id != series["solo_id"]:\n')],
        [ALL_GREEN],
    ),
    (
        "NC-unrelated-constant-in-the-same-file",
        "negative control: a 1v2 gold constant this sweep never reads",
        [("OVT_SERIES_WIN_GOLD = 40", "OVT_SERIES_WIN_GOLD = 41")],
        [ALL_GREEN],
    ),
]


def apply_all(originals: dict, edits) -> dict:
    """Apply every edit to a COPY of the source it names; returns {key: text}."""
    out = dict(originals)
    for edit in edits:
        key, old, new = edit if len(edit) == 3 else ("main", edit[0], edit[1])
        src = out[key]
        if src.count(old) == 0:
            raise SystemExit(f"anchor not found in {key}:\n{old[:200]}")
        out[key] = src.replace(old, new)
    return out


SUMMARY = re.compile(
    r"(\d+) (passed|failed|errors|error|skipped|xfailed|xpassed|deselected)")


def clean_slate() -> str:
    """Terminate every other backend on the dedicated test database.

    The suite's per-case fixture does this too, but it cannot help when the
    statement that blocks is the fixture's own DDL: the case then dies inside
    the reset and every later case in that process dies with it. Doing it here
    as well is what stops one dead case reaching across into the NEXT
    mutation's run. A cross-run leak of exactly that shape is what once put a
    false REDDENED on this runner's negative control. Bounded by construction:
    Bounded by the NAME check below, not by the belief that the DSN is the
    right one: this terminates every backend on whatever database it is
    pointed at, and the sibling lanes keep their own throwaway databases on
    the same local instance (#342).
    """
    import asyncio
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    async def go() -> int:
        engine = create_async_engine(
            os.environ["BUG391_TEST_PG_DSN"], poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                dbname = (await conn.execute(
                    text("SELECT current_database()"))).scalar()
                if dbname != EXPECTED_DB:
                    raise RuntimeError(
                        f"BUG391_TEST_PG_DSN points at database {dbname!r}; "
                        f"this runner terminates every backend on it and the "
                        f"suite drops its tables, so it runs against "
                        f"{EXPECTED_DB!r} and nothing else.")
                n = (await conn.execute(text(
                    "SELECT count(*) FROM pg_stat_activity"
                    " WHERE datname = current_database()"
                    "   AND pid <> pg_backend_pid()"))).scalar()
                await conn.execute(text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                    " WHERE datname = current_database()"
                    "   AND pid <> pg_backend_pid()"))
                await conn.commit()
                return int(n or 0)
        finally:
            await engine.dispose()

    try:
        n = asyncio.run(go())
    except Exception as exc:                      # noqa: BLE001 - reported, not raised
        return f"clean-slate probe FAILED: {exc!r}"
    return f"cleared {n} leftover backend(s)" if n else ""


def run_suite() -> dict:
    """Run the suite once and report what actually executed.

    A run that did not execute every test is not evidence about the mutation.
    Module-level and fixture errors used to be parsed into the same set as
    test failures, so a run in which NOTHING executed was scored as "the
    mutant survived" — the filter was discarding the very line it measured
    (#441). They are separate outcomes now, and the caller retries them
    instead of scoring them.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", TESTS, "-q", "--no-header",
             "-p", "no:cacheprovider"],
            cwd=str(BACKEND), capture_output=True, text=True,
            timeout=SUITE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        # A mutation that removes a BOUND can make a case wait forever instead
        # of failing, and an unbounded wait here stalls the whole campaign
        # with no line saying why. That is not a kill and not a survival: it
        # is the absence of a measurement, so it is reported as one and the
        # caller retries it (#441 — never score the run that did not happen).
        return {"failed": set(), "errored": set(), "collect_errors": [],
                "counts": {}, "ran": 0,
                "tail": f"NO RESULT: the suite exceeded {SUITE_TIMEOUT_S}s and "
                        f"was stopped; a mutation that removes a bound hangs "
                        f"rather than reds unless the case bounds itself",
                "rc": None, "timed_out": True}
    failed, errored, collect_errors = set(), set(), []
    for line in proc.stdout.splitlines():
        if line.startswith("FAILED ") or line.startswith("ERROR "):
            part = line.split(" ", 1)[1].split(" ")[0]
            if "::" in part:
                target = failed if line.startswith("FAILED ") else errored
                target.add(part.rsplit("::", 1)[-1])
            else:
                # "ERROR tests/foo.py - ..." names the MODULE, so no test in
                # it ran. It is never a test name and never a kill signal.
                collect_errors.append(part)
    lines = proc.stdout.strip().splitlines()
    tail = lines[-1] if lines else ""
    counts: dict = {}
    for n, word in SUMMARY.findall(tail):
        word = "error" if word == "errors" else word
        counts[word] = counts.get(word, 0) + int(n)
    return {
        "failed": failed,
        "errored": errored,
        "collect_errors": collect_errors,
        "counts": counts,
        "ran": counts.get("passed", 0) + counts.get("failed", 0),
        "tail": tail,
        "rc": proc.returncode,
    }


def not_a_verdict(res: dict, expected_total) -> str:
    """Empty when the run may be scored; else the reason it may not be."""
    if res.get("timed_out"):
        return res["tail"]
    if res["collect_errors"]:
        return f"module-level error, no test in it ran: {res['collect_errors']}"
    if res["errored"]:
        return f"fixture error in {sorted(res['errored'])}"
    if res["counts"].get("error"):
        return f"{res['counts']['error']} error(s) reported"
    if res["counts"].get("skipped"):
        return (f"{res['counts']['skipped']} test(s) SKIPPED — the live half "
                f"did not run, so most mutations had nothing to kill")
    if not res["ran"]:
        return f"no test accounted for at all (tail: {res['tail']!r})"
    if expected_total is not None and res["ran"] != expected_total:
        return (f"{res['ran']} test(s) accounted for, expected "
                f"{expected_total} — the suite did not run whole")
    return ""


def main() -> int:
    if not os.environ.get("BUG391_TEST_PG_DSN"):
        print("BUG391_TEST_PG_DSN unset — the live half would skip and most "
              "mutations would have nothing to kill. Refusing to run.")
        return 2
    originals = {k: io.open(p, encoding="utf-8", newline="").read()
                 for k, p in FILES.items()}
    digests = {k: hashlib.sha256(v.encode("utf-8")).hexdigest()
               for k, v in originals.items()}
    backups = {}
    for key, path in FILES.items():
        backups[key] = path.with_suffix(path.suffix + ".bug391-mutation-backup")
        backups[key].write_text(originals[key], encoding="utf-8", newline="")
        print(f"{key:12s} {path.name} sha256 {digests[key]}")
        print(f"{'':12s} backup {backups[key]}")

    def restore():
        for k, p in FILES.items():
            p.write_text(originals[k], encoding="utf-8", newline="")

    rows = []
    try:
        slate = clean_slate()
        if slate:
            print(f"[slate] {slate}")
        base = run_suite()
        print(f"[baseline] {base['tail']}  [pytest exit={base['rc']}]")
        why = not_a_verdict(base, None)
        if why or base["failed"]:
            print(f"baseline is not a green verdict: "
                  f"{why or sorted(base['failed'])}")
            return 2
        expected_total = base["ran"]
        print(f"[baseline] every run below must account for "
              f"{expected_total} tests or it is not a verdict")
        for label, defect, edits, expect in MUTATIONS:
            t0 = time.time()
            mutated = apply_all(originals, edits)
            for _k, _txt in mutated.items():
                if _txt != originals[_k]:
                    FILES[_k].write_text(_txt, encoding="utf-8", newline="")
            res, why = None, ""
            for attempt in (1, 2):
                slate = clean_slate()
                if slate:
                    print(f"           [slate] {slate}")
                res = run_suite()
                why = not_a_verdict(res, expected_total)
                if not why:
                    break
                print(f"           [no verdict, attempt {attempt}] {why}")
                print(f"           [no verdict, attempt {attempt}] "
                      f"{res['tail']}  [pytest exit={res['rc']}]")
            restore()
            if why:
                # Never ALIVE and never KILL: the run did not measure the
                # mutation, so it carries no information about it either way.
                rows.append((label, None, f"NO VERDICT: {why}", defect))
                print(f"[NOVER] {label} ({time.time() - t0:.0f}s) — "
                      f"NO VERDICT: {why}")
                print(f"           models: {defect}")
                print(f"           {res['tail']}  [pytest exit={res['rc']}]")
                continue
            failed = res["failed"]
            if expect == [ALL_GREEN]:
                ok = not failed
                detail = "all green" if ok else f"REDDENED: {sorted(failed)}"
            else:
                missing = [t for t in expect if t not in failed]
                ok = not missing
                detail = (f"killed {sorted(failed)}" if ok
                          else f"SURVIVED for {missing}")
            rows.append((label, ok, detail, defect))
            print(f"[{'KILL ' if ok else 'ALIVE'}] {label} "
                  f"({time.time() - t0:.0f}s) — {detail}")
            print(f"           models: {defect}")
            print(f"           {res['tail']}  [pytest exit={res['rc']}]")
    finally:
        restore()

    # Every file the run USED, not just the one it mutated most often: an
    # assertion that changed between the run and the commit would leave the
    # reported main.py MATCH true and the result meaningless (r2 finding 6).
    moved = []
    for key in FILES:
        after = hashlib.sha256(
            io.open(FILES[key], encoding="utf-8",
                    newline="").read().encode("utf-8")).hexdigest()
        ok = after == digests[key]
        print(f"restored {key:12s} sha256 {after} "
              f"({'MATCH' if ok else 'MISMATCH'})")
        if not ok:
            moved.append(key)
        backups[key].unlink(missing_ok=True)

    good = [r for r in rows if r[1] is True]
    nover = [r for r in rows if r[1] is None]
    bad = [r for r in rows if r[1] is False]
    print(f"\n{len(good)}/{len(rows)} controls behaved as required")
    if bad:
        print(f"{len(bad)} control(s) did NOT behave: "
              f"{[r[0] for r in bad]}")
    if nover:
        # Distinct from a misbehaving control on purpose. These runs measured
        # nothing, so the set is incomplete rather than failing, and the only
        # honest report is to say so (#342: a check that cannot fail is worse
        # than no check — one that silently did not run is the same defect).
        print(f"{len(nover)} control(s) produced NO VERDICT after a retry on a "
              f"clean slate: {[r[0] for r in nover]}")
    if moved:
        print(f"{moved} DID NOT come back byte-identical — restore by hand")
        return 3
    if nover:
        return 4
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
