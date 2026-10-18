"""The Stage 2 server staging controls on main.py (design V3 NX pieces; lore
#391): each row's mutant and inert twin, run against the staging tests.

The machinery is rdm_controls.py's, unchanged: exact text replacements on a
scratch copy of backend/api, backend/sql and backend/tests (each edit
asserts its occurrence count first, so a stale entry fails as STALE), a
mutant counts only when its test's first failure is an AssertionError whose
first element is the row's tag, and a twin (a comment line inserted at the
mutant's own site) must stay green. Only the row registry is this file's.
Rows that mutate match_hold.py or match_report_window.py live in
evidence/match-hold-mutation-runner.py instead.

Usage (one lane database per concurrent run):
  RDM_SCRATCH_DIR=<dir> python srv_stage_controls.py check
  RDM_SCRATCH_DIR=<dir> python srv_stage_controls.py run --db <name> --out <file> [--rows M1.5]
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import rdm_controls as rc  # noqa: E402

MAIN = rc.MAIN
WT = "test_match_hold_wiring_pg.py::"
DT = "test_match_hold_discovery_pg.py::"
RT = "test_match_hold_reports_pg.py::"

ROWS = [
    # NX1: the 1v2 Start issues its room without latching the hold flag.
    {"row": "M1.5", "node": WT + "test_t1_3_ovt_start_and_poll_carry_the_latched_flag",
     "tag": "T1.3 ovt start row",
     "mutant": [(MAIN,
                 '    _start_hold = await _match_hold._hold_latch(db, "ovt", series_id, room)\n',
                 '    _start_hold = False\n', 1)]},
    # NX1: a relock keeps the flag of the room it leaves (both relocks).
    {"row": "M1.6", "node": WT + "test_t1_3_team_issue_relock_and_continuation",
     "tag": "T1.3 relock clears",
     "mutant": [(MAIN,
                 '                   hold_v2 = FALSE,\n'
                 '                   hold_room = NULL,\n',
                 '', 2)],
     # The site is inside SQL text, where a Python comment line is not
     # inert: the twin writes the same values parenthesized.
     "twin": [(MAIN,
               '                   hold_v2 = FALSE,\n'
               '                   hold_room = NULL,\n',
               '                   hold_v2 = (FALSE),\n'
               '                   hold_room = (NULL),\n', 2)]},
    # NX3: the polls answer readmissible without rdm=1.
    {"row": "M3.4", "node": DT + "test_t3_2_polls_answer_readmissible_only_with_rdm",
     "tag": "T3.2 no rdm",
     "mutant": [(MAIN,
                 '    if rdm != 1:\n'
                 '        return None\n'
                 '    pid = await _match_hold._player_id(db, steam_id)\n',
                 '    if False:\n'
                 '        return None\n'
                 '    pid = await _match_hold._player_id(db, steam_id)\n', 1)]},
    # NX3: the attest accepts a roster that omits a live fighter.
    {"row": "M3.13", "node": DT + "test_t3_6_attest_omitting_a_live_fighter_is_refused",
     "tag": "T3.6 live omitted",
     "mutant": [(MAIN,
                 '    return (steam_id in true_roster and (att | held) == true_roster\n'
                 '            and (true_roster - held) <= att)\n',
                 '    return (steam_id in true_roster and att <= true_roster)\n', 1)]},
    # NX3: H is taken from what the caller left out, not the server's rows.
    {"row": "M3.14", "node": DT + "test_t3_6_attest_without_a_server_hold_is_refused",
     "tag": "T3.6 no server hold",
     "mutant": [(MAIN,
                 '            _rdm_ok = _rdm_attest_ok(roster, true_roster, _s2_held, req.steam_id)\n',
                 '            _rdm_ok = _rdm_attest_ok(roster, true_roster,\n'
                 '                                     true_roster - set(roster), req.steam_id)\n',
                 1)]},
    # NX3: the headroom counts only the live fighters.
    {"row": "M3.15", "node": DT + "test_t3_6_attest_over_the_server_held_set",
     "tag": "T3.6 headroom",
     "mutant": [(MAIN,
                 '        _fighters = max(_fighters, _s2_r)\n',
                 '        _fighters = _fighters\n', 1)]},
    # NX4: the DC report re-evaluates the crossing instead of the frozen one.
    {"row": "M5.1", "node": RT + "test_t5_1_dc_report_reads_the_crossing_the_hold_froze",
     "tag": "T5.1 frozen",
     "mutant": [(MAIN,
                 '    if hold_crossed is not None:\n'
                 '        return hold_crossed\n'
                 '    return await _team_game_crossed_two(db, sid, s, total_points)\n',
                 '    return await _team_game_crossed_two(db, sid, s, total_points)\n', 1)]},
    # NX4: a game-over during a hold settles at its receipt.
    {"row": "M5.10",
     "node": RT + "test_t5_7_held_game_over_settles_at_entry_and_is_superseded_at_lapse",
     "tag": "T5.7 held",
     "mutant": [(MAIN, '        held=_held)\n', '        held=False)\n', 1)]},
]
for _row in ROWS:
    if "twin" not in _row:
        _row["twin"] = rc._site_twin(_row)

if __name__ == "__main__":
    rc.ROWS[:] = ROWS
    sys.exit(rc.main())
