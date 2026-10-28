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
XT = "test_match_hold_deletion_pg.py::"

ROWS = [
    {"row": "L1.BOUND",
     "node": "test_match_hold_admission_routes_pg.py::test_l1_shared_admission_wait_is_bounded_for_every_caller",
     "tag": "L1 admission bound",
     "mutant": [(MAIN, "LEAST(COALESCE(NULLIF(milliseconds, 0), 1000), 1000)::text || 'ms'", "value", 1)],
     "twin": [(MAIN, "LEAST(COALESCE(NULLIF(milliseconds, 0), 1000), 1000)::text || 'ms'", "LEAST(COALESCE(NULLIF(milliseconds, 0), 1000), (1000))::text || 'ms'", 1)]},
    {"row": "F1.M2.ROSTER", "node": WT + "test_t1_3_ovt_start_and_poll_carry_the_latched_flag",
     "tag": "F1.M2 Start roster",
     "mutant": [(MAIN,
                 '            "hold": bool(_start_hold), **_start_roster}\n',
                 '            "hold": bool(_start_hold)}\n', 1)]},
    {"row": "MERGED.FIX1.M1.ROLLBACK",
     "node": RT + "test_merged_fix1_m1_quarantine_preserves_window_transaction",
     "tag": "M1 owner transaction",
     "mutant": [(MAIN,
                 '    try:\n        if not _window_owned:\n            await db.rollback()\n        # Flood bound, take 2',
                 '    try:\n        await db.rollback()\n        # Flood bound, take 2', 1)],
     "twin": [(MAIN,
               '    try:\n        if not _window_owned:\n            await db.rollback()\n        # Flood bound, take 2',
               '    try:\n        if not (_window_owned):\n            await db.rollback()\n        # Flood bound, take 2', 1)]},
    {"row": "MERGED.FIX1.H3.RESELECT",
     "node": RT + "test_merged_fix1_h3_two_janitors_keep_only_their_attempt",
     "tag": "H3 exact attempted row",
     "mutant": [(MAIN, '                attempt = getattr(ex, "attempted_report", None)\n', '                rows = (await db.execute(text(\n                    "SELECT reporter_id, reporter_steam, cls, payload, received_at"\n                    " FROM match_report_journal WHERE room_name = CAST(:room AS varchar)"\n                    " AND game_id = CAST(:g AS uuid) AND state = \'journaled\'"),\n                    {"room": w["room_name"], "g": str(w["game_id"])})).mappings().all()\n                current = mrw.pick(rows)\n                attempt = dict(current) if current is not None else None\n                if attempt is not None:\n                    attempt["reporter_id"] = str(attempt["reporter_id"])\n                    payload = attempt["payload"]\n                    attempt["payload"] = payload if isinstance(payload, str) else _json.dumps(payload)\n', 1)],
     "twin": [(MAIN, '                attempt = getattr(ex, "attempted_report", None)\n', '                attempt = getattr((ex), "attempted_report", None)\n', 1)]},
    {'row': 'F1.H1.NEW', 'node': 'test_match_hold_reports_pg.py::test_fix1_h1_racing_duplicate_does_not_spend_next_reporter', 'tag': 'F1.H1 new settlement only', 'mutant': [('backend/api/main.py', '    if not outcome.get("new_settlement") or outcome.get("physical_game") != physical_game:\n', '    if False:\n', 1)]},
    {"row": "F1.H1.GAME", "node": RT + "test_fix1_h1_recorded_game_never_touches_the_next_window",
     "tag": "F1.H1 physical game",
     "mutant": [(MAIN,
                 '    recorded = await _recorded_physical_report(db, mode, series_id, report, by_steam)\n    if recorded is not None:\n',
                 '    recorded = None\n    if recorded is not None:\n', 1)]},
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
    # NX4: the record of a held game is sealed. Without the seal's read in
    # update_team_live_points the post during an open hold is recorded
    # (M5.1); without the DC report's close the open hold outlives the
    # report (M5.2). The twins are the site comments.
    {"row": "M5.1", "node": RT + "test_t5_1_the_record_of_a_held_game_is_sealed",
     "tag": "T5.1b post during the hold",
     "mutant": [(MAIN,
                 '        _held = await _team_game_hold_seal(db, sid, _held_row.hold_room,\n'
                 '                                           _held_row.photon_room_id)\n',
                 '        _held = None\n', 1)]},
    {"row": "M5.2", "node": RT + "test_t5_1_the_record_of_a_held_game_is_sealed",
     "tag": "T5.1c closed with the report",
     "mutant": [(MAIN,
                 '    await _team_dc_hold_close(db, sid_uuid, s)\n',
                 '', 1)]},
    # M5.10 follows the causal receipt guard in the hold mutation runner.
    # NX6: the deletion omits one table (the player's own presence rows).
    {"row": "M6.1", "node": XT + "test_nx6_deletion_leaves_no_stage2_row_naming_the_player",
     "tag": "NX6 no identity",
     "mutant": [(MAIN,
                 '    await db.execute(text(\n'
                 '        "DELETE FROM match_seat_presence WHERE player_id = CAST(:pid AS uuid)"), ids)\n',
                 '', 1)]},
]

# NX0b (fix 1 H3, the twenty main-path patches re-anchored by text): at each
# admission site, GATE skips the acquire (the gate is never reached) and
# RECHECK ignores its refusal (the route commits past it). Each is red on the
# site's route_loses node of the full-route test.
HT = "test_match_hold_admission_routes_pg.py::test_h3_full_route_gate_in_both_winner_orders"
H3_SITES = [
    ("ranked_queue_poll",
     '        if (await _lease_acquire_many(\n'
     '                db, [my_pid, opp["player_id"]], "ranked",\n'
     '                None, LEASE_TTL_POLLING)) is False:\n'),
    ("team_queue_poll",
     '    if (await _lease_acquire_many(\n'
     '            db, team1_ids + team2_ids, "team", series_id,\n'
     '            LEASE_TTL_ASSEMBLY)) is False:\n'),
    ("team_relock",
     '    if (await _lease_acquire_many(\n'
     '            db, list(member_pids), "team", srow["id"],\n'
     '            LEASE_TTL_ASSEMBLY)) is False:\n'),
    ("ovt_queue_poll",
     '    if (await _lease_acquire_many(\n'
     '            db, [r["player_id"] for r in lobby], "ovt",\n'
     '            series_id, LEASE_TTL_ASSEMBLY)) is False:\n'),
    ("lobby_enroll",
     '    if (await _lease_acquire(\n'
     '            db, player.id, cfg["lease"], lobby_id,\n'
     '            LEASE_TTL_POLLING)) is False:\n'),
    ("team_lobby_start",
     '    if (await _lease_acquire_many(\n'
     '            db, all4, "team", series_id, LEASE_TTL_ASSEMBLY,\n'
     '            allowed_group_ids=(lobby_id,))) is False:\n'),
    ("ovt_lobby_start",
     '    if (await _lease_acquire_many(\n'
     '            db, ids, "ovt", series_id, LEASE_TTL_ASSEMBLY,\n'
     '            allowed_group_ids=(lobby_id,))) is False:\n'),
    ("ffa_lobby_enroll",
     '        if (await _lease_acquire(\n'
     '                db, player.id, "ffa", lobby_id,\n'
     '                LEASE_TTL_POLLING)) is False:\n'),
    ("ffa_lock_roster",
     '    if (await _lease_acquire_many(\n'
     '            db, _pids, "ffa", lobby_id, LEASE_TTL_ASSEMBLY,\n'
     '            allowed_group_ids=(reform_of,))) is False:\n'),
    ("ffa_queue_poll",
     '    if (await _lease_acquire_many(\n'
     '            db, [r["player_id"] for r in ordered], "ffa",\n'
     '            lobby_id, LEASE_TTL_ASSEMBLY)) is False:\n'),
]
# Short row codes: the scratch copy path carries the row name, and Windows
# path limits refuse the longest sql file names under a long one.
H3_CODE = {"ranked_queue_poll": "rq", "team_queue_poll": "tq", "team_relock": "tr",
           "ovt_queue_poll": "oq", "lobby_enroll": "le", "team_lobby_start": "ts",
           "ovt_lobby_start": "os", "ffa_lobby_enroll": "fe", "ffa_lock_roster": "fl",
           "ffa_queue_poll": "fq"}
for _name, _site in H3_SITES:
    _node = "%s[%s-route_loses]" % (HT, _name)
    ROWS.append({"row": "H3.%s.G" % H3_CODE[_name], "node": _node, "tag": "H3 route gate",
                 "mutant": [(MAIN, _site, _site.replace("if (await", "if False and (await", 1),
                             1)]})
    ROWS.append({"row": "H3.%s.R" % H3_CODE[_name], "node": _node, "tag": "H3 route refused",
                 "mutant": [(MAIN, _site, _site.replace(")) is False:", ")) is False and False:",
                                                        1), 1)]})

ROWS.append({'row': 'F1.H4.RECEIPT',
 'node': 'test_match_hold_deletion_pg.py::test_fix1_h4_report_writers_guard_before_their_first_lock[route]',
 'tag': 'FIX1 H4 report guard',
 'mutant': [('backend/api/main.py',
             '        by_steam = await _match_hold._guard_identities(db, keys)\n',
             '        by_steam = {key: pid for key in keys if (pid := await _match_hold._player_id(db, '
             'key)) is not None}\n',
             1)],
 'twin': [('backend/api/main.py',
           '        by_steam = await _match_hold._guard_identities(db, keys)\n',
           '        by_steam = await _match_hold._guard_identities(db, (keys))\n',
           1)]})
ROWS.append({'row': 'F1.H4.DELETE_WINDOW',
 'node': 'test_match_hold_deletion_pg.py::test_fix1_h4_deletion_terminalizes_hold_without_journal[team]',
 'tag': 'FIX1 H4 deleted hold terminal',
 'mutant': [('backend/api/main.py',
             '        if row["close_hold"] and not mrw._window_terminal(window):\n',
             '        if False and row["close_hold"] and not mrw._window_terminal(window):\n',
             1)],
 'twin': [('backend/api/main.py',
           '        if row["close_hold"] and not mrw._window_terminal(window):\n',
           '        if (row["close_hold"]) and not mrw._window_terminal(window):\n',
           1)]})
ROWS.append({'row': 'F1.H4.RETRY',
 'node': 'test_match_hold_deletion_pg.py::test_fix1_h4_janitor_retry_reacquires_identity_guards',
 'tag': 'FIX1 H4 retry guard',
 'mutant': [('backend/api/main.py',
             '                await mrw._guard_window_identities(\n'
             '                    db, mode=w["mode"], room=w["room_name"], game_id=w["game_id"],\n'
             '                    payload=attempt["payload"], reporter_id=attempt["reporter_id"],\n'
             '                    reporter_steam=attempt["reporter_steam"])\n',
             '                pass\n',
             1)],
 'twin': [('backend/api/main.py',
           '                await mrw._guard_window_identities(\n'
           '                    db, mode=w["mode"], room=w["room_name"], game_id=w["game_id"],\n'
           '                    payload=attempt["payload"], reporter_id=attempt["reporter_id"],\n'
           '                    reporter_steam=attempt["reporter_steam"])\n',
           '                await mrw._guard_window_identities(\n'
           '                    db, mode=w["mode"], room=w["room_name"], game_id=w["game_id"],\n'
           '                    payload=(attempt["payload"]), reporter_id=attempt["reporter_id"],\n'
           '                    reporter_steam=attempt["reporter_steam"])\n',
           1)]})


ROWS.append({'row': 'F1.H4.RECEIPT_BOUND', 'node': 'test_match_hold_deletion_pg.py::test_fix1_h4_receipt_identity_wait_is_bounded', 'tag': 'FIX1 H4 receipt bound', 'mutant': [('backend/api/main.py', '    async with _match_hold.database_deadline(db):\n        by_steam = await _match_hold._guard_identities(db, keys)\n', '    by_steam = await _match_hold._guard_identities(db, keys)\n', 1)], 'twin': [('backend/api/main.py', '    async with _match_hold.database_deadline(db):\n        by_steam = await _match_hold._guard_identities(db, keys)\n', '    async with _match_hold.database_deadline((db)):\n        by_steam = await _match_hold._guard_identities(db, keys)\n', 1)]})

ROWS.extend([{'row': 'FIX2.M3.MEMBER',
  'node': 'test_match_hold_wiring_pg.py::test_t1_3_team_issue_relock_and_continuation',
  'tag': 'F1.M2 team roster',
  'mutant': [('backend/api/main.py',
              '            return TeamQueueMember(\n                steam_id=row["steam_id"],\n',
              '            return TeamQueueMember(\n                steam_id=me["steam_id"],\n',
              1)],
  'twin': [('backend/api/main.py',
            '            return TeamQueueMember(\n                steam_id=row["steam_id"],\n',
            '            return TeamQueueMember(\n                steam_id=(row["steam_id"]),\n',
            1)]},
 {'row': 'FIX2.M3.SIDE',
  'node': 'test_match_hold_wiring_pg.py::test_t1_3_team_issue_relock_and_continuation',
  'tag': 'F1.M2 team roster',
  'mutant': [('backend/api/main.py',
              '                team_assigned=row["team_assigned"],\n',
              '                team_assigned=3 - row["team_assigned"],\n',
              1)],
  'twin': [('backend/api/main.py',
            '                team_assigned=row["team_assigned"],\n',
            '                team_assigned=(row["team_assigned"]),\n',
            1)]},
 {'row': 'FIX2.M3.OVT',
  'node': 'test_match_hold_wiring_pg.py::test_t1_3_ovt_start_and_poll_carry_the_latched_flag',
  'tag': 'F1.M2 Start roster',
  'mutant': [('backend/api/main.py',
              '            "hold": bool(_start_hold), **_start_roster}\n',
              '            "hold": bool(_start_hold)}\n',
              1)],
  'twin': [('backend/api/main.py',
            '            "hold": bool(_start_hold), **_start_roster}\n',
            '            "hold": bool((_start_hold)), **_start_roster}\n',
            1)]}])

# Fix 2 M5: each route must leave the capture's advisory key available.
# Each row's one anchor is inside _triage_read_txn; a READ ONLY transaction
# can take this advisory lock, so the mutant reaches the observed hold.
_M5_HANDLE = "        h = _TriageReadHandle(db, time.monotonic())\n"
_M5_BLOCK = (
    "        await db.execute(text(\"SELECT pg_advisory_xact_lock(hashtext('mrq:' || CAST(g AS text)))\"\n"
    "                              \" FROM (SELECT DISTINCT group_id AS g FROM match_report_quarantine\"\n"
    "                              \" WHERE status = 'pending' AND group_id IS NOT NULL) s\"))\n")
_M5_TWIN = (
    "        await db.execute(text(\"SELECT pg_advisory_xact_lock(hashtext('rj-triage-k2-unrelated'))\"))\n")
for _route in ("V1", "V2", "D1"):
    ROWS.append({
        "row": "FIX2.M5.BLOCK." + _route,
        "node": "test_ffa_quarantine_triage.py::test_pg_k2_a_capture_commits_while_the_route_is_open[" + _route + "]",
        "tag": "FIX2 M5 capture during route",
        "mutant": [(MAIN, _M5_HANDLE, _M5_BLOCK + _M5_HANDLE, 1)],
        "twin": [(MAIN, _M5_HANDLE, _M5_TWIN + _M5_HANDLE, 1)],
    })

for _row in ROWS:
    if "twin" not in _row:
        _row["twin"] = rc._site_twin(_row)

if __name__ == "__main__":
    rc.ROWS[:] = ROWS
    sys.exit(rc.main())
