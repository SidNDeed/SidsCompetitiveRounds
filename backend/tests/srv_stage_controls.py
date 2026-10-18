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
]
for _row in ROWS:
    if "twin" not in _row:
        _row["twin"] = rc._site_twin(_row)

if __name__ == "__main__":
    rc.ROWS[:] = ROWS
    sys.exit(rc.main())
