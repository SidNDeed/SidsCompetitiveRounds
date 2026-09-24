"""RJ-TRIAGE part 1 controls: plant each named mutation and its inert twin,
run the named checks, put the file back, record the result.

Every control of RJ-TRIAGE-DESIGN-V5 section 6.2 (K1-K19) is carried below as
DATA: the file, the exact text a plant replaces, the text it writes, the test
nodes it must turn RED (a mutant) or leave GREEN (an inert twin at the same
site, #391). Each plant is printed as a unified diff beside the run it
produced, so the evidence is the diff and the failing assertion, not a
summary line (the shape of mutation_runner.py beside this file).

Per plant, refusing rather than continuing at each step:
  1. `git status --porcelain` over the worktree must be EMPTY;
  2. `git rev-parse HEAD` is printed (and compared with --expect-head);
  3. each edit's old text must occur EXACTLY ONCE in its file (#432);
  4. each target's sha256 is printed before the write;
  5. the edits are applied and printed as unified diffs;
  6. the check runs (pytest, the named nodes only) and its outcome is read
     per node from pytest's own summary: RED means EVERY named node FAILED
     on an assertion, GREEN means every named node PASSED. A collection
     error, an ERROR node, a missing node or a K2c "NO VERDICT" is neither,
     and the plant FAILS;
  7. each target is restored from the bytes read in step 4, its sha256 must
     equal the one before, and the tree must be clean again;
  8. `RESULT <name>: RED as required | GREEN as required | FAILED (...)`.
Restoration is in a `finally`.

The live checks need RJ_TRIAGE_TEST_PG_DSN (the lane database): without it
every PostgreSQL test FAILS by design, which would read as a kill, so the
runner refuses to start when it is unset.

Usage:
    python backend/tests/rj_triage_controls.py --log <path> [--campaign N]
        [--expect-head REF] [--only NAME ...] [--sites [--parse]]
--sites checks step 3 for every plant and writes nothing; with --parse it also
parses every planted file in memory, so a plant that would not compile is
refused here instead of reading as a kill.
Exit: 0 every plant gave its required result; 1 at least one did not;
2 the runner refused to start.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
WT = HERE.parents[1]
MAIN = "backend/api/main.py"
DB = "backend/api/database.py"
BOT = "backend/discord_bot.py"

S = "test_ffa_quarantine_triage.py::"
B = "test_quarantine_digest_bot.py::"


def K2(route):
    return S + f"test_pg_k2_a_capture_commits_while_the_route_is_open[{route}]"


def K2C(case, route):
    return S + f"test_pg_k2c_relation_locks_released_within_5_5s_of_t0[{case}-{route}]"


K1 = S + "test_pg_k1_the_three_routes_write_nothing"
K2D = S + "test_k2d_each_route_enters_the_primitive_once_and_issues_no_control_statement"
K3 = S + "test_pg_k3_the_oldest_group_is_first_on_the_summary_and_in_the_digest"
K3B = S + "test_pg_k3b_equal_time_groups_both_appear_across_pages_of_one"
K4 = S + "test_pg_k4_a_group_at_quota_shows_all_fifty"
K5 = S + "test_pg_k5_pt1_counts_per_seat"
K6 = S + "test_pg_k6_pt3_lists_every_row_of_the_lobby_nearest_first"
K6B = S + "test_pg_k6b_a_tailless_key_leaves_d_distance_and_c2_undefined"
K6C = S + "test_pg_k6c_a_201_row_lobby_is_read_whole_or_labelled_partial"
K6D = S + "test_pg_k6d_the_migration_gap_shows_expected_six"
K7 = S + "test_pg_k7_pt3_compares_with_the_arms_vector_absent_included"
K8 = S + "test_pg_k8_rows_reported_by_the_captures_reporter_are_flagged"
K9 = S + "test_pg_k9_a_redelivered_variant_is_labelled_a_recapture"
K9B = S + "test_pg_k9b_a_reviewed_twin_at_position_230_is_found"
K10 = S + "test_pg_k10_a_variant_names_its_keyed_twin"
K10B = S + "test_pg_k10b_a_variant_finds_its_keyed_twin_in_another_group"
K11 = S + "test_pg_k11_age_and_the_counts_beside_pt3"
K12 = S + "test_k12_the_quarantine_table_is_written_only_by_the_capture_and_the_two_admin_routes"
K13E_S = S + "test_pg_k13e_a_d1_pass_ends_within_its_page_bound"
K14 = S + "test_pg_k14_pt1_lists_a_capture_under_its_claimed_reporter_only"
K15 = S + "test_pg_k15_no_statement_runs_after_the_commit"
K15B = S + "test_pg_k15b_the_seal_refuses_each_path_before_the_statement_is_sent"
K16 = S + "test_pg_k16_pt1_is_raw_arithmetic_with_the_fixed_statement"
K16B = S + "test_pg_k16b_pt1_counts_settlements_by_their_receipt_time"
K18 = S + "test_pg_k18_a_team_group_at_quota_is_listed_and_the_51st_keeps_no_row"
K19 = S + "test_pg_k19_a_team_group_reads_its_series_and_no_lobby"

K13A = B + "test_k13a_w19_c_is_announced_by_the_pass_that_reads_page_2"
K13B = B + "test_k13b_w20_a_late_commit_is_read_by_the_first_pass_after_it_and_posted_within_the_bound"
K13C = B + "test_k13c_w21_message_2_rejected_leaves_its_ids_and_message_3s_unannounced"
K13C2 = B + "test_k13c_w21_variant_message_1_rejected_marks_nothing_and_retries_at_the_next_pass_end"
K13D = B + "test_k13d_a_reviewed_row_leaves_the_announced_set_after_a_complete_pass"
K13E_B = B + "test_k13e_w28_the_pass_ends_within_its_page_bound"
K13F1 = B + "test_k13f_w19_cold_restart_every_line_whole_in_exactly_one_accepted_message"
K13F2 = B + "test_k13f_cold_restart_marks_exactly_the_ids_of_accepted_messages"
K13G1 = B + "test_k13g_i_one_iteration_lasts_exactly_its_pass_plus_its_posting_step"
K13G2 = B + "test_k13g_ii_w33_a_capture_committed_during_a_cold_round_is_posted_within_the_bound"
K17W = B + "test_the_digest_loop_is_a_60s_task_started_in_on_ready"
K17 = B + "test_k17_one_run_logs_the_three_health_lines_and_posts_the_online_line"

ROUTES3 = ("V1", "V2", "D1")


@dataclass
class Plant:
    name: str
    control: str
    kind: str                     # "mutant" or "twin"
    what: str                     # the plant in words
    edits: list                   # [(relpath, old, new)]
    checks: list                  # pytest node ids, relative to backend/tests
    expect: str = field(default="")

    def __post_init__(self):
        self.expect = self.expect or ("RED" if self.kind == "mutant" else "GREEN")


P: list[Plant] = []


def mutant(name, control, what, edits, checks):
    P.append(Plant(name, control, "mutant", what, edits, checks))


def twin(name, control, what, edits, checks):
    P.append(Plant(name, control, "twin", what, edits, checks))


# ── shared sites ─────────────────────────────────────────────────────────────

V1_ADMIN = '        await h.run(_require_admin, admin_steam_id, "quarantine", "triage", hmac_signature)\n'
V2_ADMIN = '        await h.run(_require_admin, admin_steam_id, "quarantine", target, hmac_signature)\n'
STMT2 = ('            "SELECT set_config(\'statement_timeout\', \'2s\', true),"\n'
         '            " set_config(\'lock_timeout\', \'1s\', true),"\n'
         '            " set_config(\'idle_in_transaction_session_timeout\', \'1s\', true)"))\n')
STMT2_TAIL = ('            " set_config(\'idle_in_transaction_session_timeout\', \'1s\', true)"))\n'
              '        h = _TriageReadHandle(db, time.monotonic())\n')
STMT1 = '        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))\n'
V2_GROUP_READ = ('        grp = await h.read(_TRIAGE_SQL_V2_LOBBY if mode == "ffa" else _TRIAGE_SQL_V2_SERIES,'
                 ' {"g": gid})\n')
V1_BUILD = ('    async def build(r):\n'
            '        fam_of = lambda row: _triage_family(row["mode"], row["reason"], row["room_held"])\n'
            '        members: dict = {}\n')
V2_BUILD = ('    async def build(r):\n'
            '        return _triage_group_view(mode, gid, r)\n')
D1_BUILD = ('    async def build(r):\n'
            '        resp = {"hw": _triage_iso(r["hw"]), "page_size": _TRIAGE_D1_PAGE,\n')
BEFORE_HANDLE_CLASS = 'class _TriageReadBudgetSpent(Exception):\n'
ROUND_LOOP = ('    for n, (content, mkeys) in enumerate(_qdigest_messages(lines, keys, header)):\n'
              '        if not await _qdigest_send(channel, content):\n'
              '            return\n'
              '        if n == 0:\n'
              '            _qdigest["round_at"] = started\n'
              '        for kind, key in mkeys:\n'
              '            (_qdigest["announced"] if kind == "id" else _qdigest["quota_named"]).add(key)\n')
NEW_IDS = '    new = [r for r in rows if r["id"] not in st["announced"]]\n'
PRUNE = '        st["announced"] &= {r["id"] for r in rows}\n'

# ── K1: the view writes nothing ──────────────────────────────────────────────

mutant("K1-update-in-V1", "K1",
       "V1 issues an UPDATE of review_note: READ ONLY refuses it, V1 answers 500",
       [(MAIN, V1_ADMIN, V1_ADMIN + "        await h.read(\"UPDATE match_report_quarantine SET review_note = 'k1'"
                                    " WHERE status = 'pending' RETURNING id\")\n")],
       [K1])
mutant("K1b-read-write-update-in-V1", "K1",
       "statement 1 without READ ONLY, and the same UPDATE in V1: it commits, and the checksum reds",
       [(MAIN, STMT1, '        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))\n'),
        (MAIN, V1_ADMIN, V1_ADMIN + "        await h.read(\"UPDATE match_report_quarantine SET review_note = 'k1'"
                                    " WHERE status = 'pending' RETURNING id\")\n")],
       [K1])
twin("K1-twin-select-in-V1", "K1",
     "the same statement as a SELECT of review_note",
     [(MAIN, V1_ADMIN, V1_ADMIN + "        await h.read(\"SELECT review_note FROM match_report_quarantine"
                                  " WHERE status = 'pending'\")\n")],
     [K1])

# ── K2: no lock of the view delays a capture, on every route ────────────────

mutant("K2a-capture-advisory-key", "K2",
       "the primitive takes the capture's own advisory key, mrq:<group>, for every group with a pending row",
       [(MAIN, STMT2_TAIL, STMT2_TAIL.replace(
           "        h = _TriageReadHandle",
           "        await db.execute(text(\"SELECT pg_advisory_xact_lock(hashtext('mrq:' || CAST(g AS text)))"
           " FROM (SELECT DISTINCT group_id AS g FROM match_report_quarantine"
           " WHERE status = 'pending' AND group_id IS NOT NULL) s\"))\n"
           "        h = _TriageReadHandle"))],
       [K2(r) for r in ROUTES3])
twin("K2a-twin-unrelated-advisory-key", "K2",
     "an advisory lock on an unrelated key at the same site",
     [(MAIN, STMT2_TAIL, STMT2_TAIL.replace(
         "        h = _TriageReadHandle",
         "        await db.execute(text(\"SELECT pg_advisory_xact_lock(hashtext('rj-triage-k2-unrelated'))\"))\n"
         "        h = _TriageReadHandle"))],
     [K2(r) for r in ROUTES3])
mutant("K2b-lock-table-share", "K2",
       "the primitive issues LOCK TABLE match_report_quarantine IN SHARE MODE",
       [(MAIN, STMT2_TAIL, STMT2_TAIL.replace(
           "        h = _TriageReadHandle",
           "        await db.execute(text(\"LOCK TABLE match_report_quarantine IN SHARE MODE\"))\n"
           "        h = _TriageReadHandle"))],
       [K2(r) for r in ROUTES3])
twin("K2b-twin-select-limit-0", "K2",
     "a SELECT of match_report_quarantine with LIMIT 0 at the same site",
     [(MAIN, STMT2_TAIL, STMT2_TAIL.replace(
         "        h = _TriageReadHandle",
         "        await db.execute(text(\"SELECT 1 FROM match_report_quarantine LIMIT 0\"))\n"
         "        h = _TriageReadHandle"))],
     [K2(r) for r in ROUTES3])
mutant("K2-lobby-through-lock-slot", "K2",
       "(design K2b) V2 reads the lobby through _ffa_lock_lobby_slot, whose SELECT ... FOR NO KEY UPDATE"
       " READ ONLY refuses",
       [(MAIN, V2_GROUP_READ, '        if mode == "ffa":\n'
                              '            await h.run(_ffa_lock_lobby_slot, group_id)\n' + V2_GROUP_READ)],
       [K2("V2")])
twin("K2-twin-plain-games-played", "K2",
     "(design K2b twin) a plain SELECT of games_played at the same site",
     [(MAIN, V2_GROUP_READ, '        if mode == "ffa":\n'
                            '            await h.read("SELECT games_played FROM ffa_lobbies WHERE id = CAST(:g AS uuid)",'
                            ' {"g": gid})\n' + V2_GROUP_READ)],
     [K2("V2")])

# ── K2c: relation-lock holding of at most 5.5 s from t0 ─────────────────────

mutant("K2c-ii-idle-timeout-dropped", "K2c",
       "idle_in_transaction_session_timeout dropped from statement 2: a 10 s stall holds the locks",
       [(MAIN, STMT2, STMT2.replace(
           "            \" set_config('lock_timeout', '1s', true),\"\n"
           "            \" set_config('idle_in_transaction_session_timeout', '1s', true)\"))\n",
           "            \" set_config('lock_timeout', '1s', true)\"))\n"))],
       [K2C("ii", r) for r in ROUTES3])
mutant("K2c-iii-statement-timeout-dropped", "K2c",
       "statement_timeout dropped from statement 2: the pg_sleep read holds the locks until it ends",
       [(MAIN, STMT2, STMT2.replace(
           "            \"SELECT set_config('statement_timeout', '2s', true),\"\n"
           "            \" set_config('lock_timeout', '1s', true),\"\n",
           "            \"SELECT set_config('lock_timeout', '1s', true),\"\n"))],
       [K2C("iii", r) for r in ROUTES3])
twin("K2c-twin-values-in-ms", "K2c",
     "the same values written as '2000ms' and '1000ms'",
     [(MAIN, STMT2, STMT2.replace("'2s'", "'2000ms'").replace("'1s'", "'1000ms'"))],
     [K2C(c, r) for c in ("ii", "iii") for r in ROUTES3])
mutant("K2c-iv-deadline-removed", "K2c",
       "the t0 + 1 s read deadline removed: ten staggered reads hold the locks about 9 s",
       [(MAIN, "        if time.monotonic() - self.t0 >= _TRIAGE_READ_BUDGET_S:\n"
               "            raise _TriageReadBudgetSpent()\n",
         "        pass\n")],
       [K2C("iv", "V2"), K2C("iv", "primitive")])
twin("K2c-twin-deadline-in-ms", "K2c",
     "the deadline written as 1000 ms",
     [(MAIN, "        if time.monotonic() - self.t0 >= _TRIAGE_READ_BUDGET_S:\n",
       "        if (time.monotonic() - self.t0) * 1000.0 >= 1000:\n")],
     [K2C("iv", "V2"), K2C("iv", "primitive")])
mutant("K2c-v-is-local-false", "K2c",
       "is_local false in statement 2: the settings leak into the pooled session",
       [(MAIN, STMT2, STMT2.replace("', true)", "', false)"))],
       [K2C("i", r) for r in ROUTES3])
twin("K2c-twin-is-local-on", "K2c",
     "is_local written as 'on'::boolean",
     [(MAIN, STMT2, STMT2.replace("', true)", "', 'on'::boolean)"))],
     [K2C("i", r) for r in ROUTES3])

# ── K2d: one primitive per route (static) ────────────────────────────────────

mutant("K2d-a-V1-db-execute", "K2d",
       "V1 issues one read by db.execute outside the handle",
       [(MAIN, V1_ADMIN, V1_ADMIN + "        await db.execute(text(_TRIAGE_SQL_PENDING_BY_MODE))\n")],
       [K2D])
mutant("K2d-b-D1-enters-twice", "K2d",
       "D1 enters the primitive twice",
       [(MAIN, "        return resp\n\n    return await _triage_read_txn(db, read, build)\n",
         "        return resp\n\n    await _triage_read_txn(db, read, build)\n"
         "    return await _triage_read_txn(db, read, build)\n")],
       [K2D])
mutant("K2d-c-V2-own-set-transaction", "K2d",
       "V2 sends its own SET TRANSACTION before entering the primitive",
       [(MAIN, V2_BUILD + "\n    return await _triage_read_txn(db, read, build)\n",
         V2_BUILD + "\n    await db.execute(text(\"SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY\"))\n"
                    "    return await _triage_read_txn(db, read, build)\n")],
       [K2D])
twin("K2d-twin-local-alias", "K2d",
     "the handle's read called through a local alias of h.read",
     [(MAIN, '        out = {\n            "by_mode": await h.read(_TRIAGE_SQL_PENDING_BY_MODE),\n',
       '        rd = h.read\n        out = {\n            "by_mode": await rd(_TRIAGE_SQL_PENDING_BY_MODE),\n')],
     [K2D])

# ── K3 / K3b: B2 ordering ────────────────────────────────────────────────────

mutant("K3-oldest-desc", "K3", "ORDER BY MIN(created_at) DESC",
       [(MAIN, "     ORDER BY oldest ASC, mode ASC, gkey ASC\n", "     ORDER BY oldest DESC, mode ASC, gkey ASC\n")],
       [K3])
twin("K3-twin-nulls-last", "K3", "ASC NULLS LAST (created_at is NOT NULL)",
     [(MAIN, "     ORDER BY oldest ASC, mode ASC, gkey ASC\n",
       "     ORDER BY oldest ASC NULLS LAST, mode ASC, gkey ASC\n")],
     [K3])
V1_KEYSET = ("        OR (oldest, mode, gkey) > (CAST(:c_oldest AS timestamptz), CAST(:c_mode AS varchar),\n"
             "                                   CAST(:c_gkey AS uuid))\n"
             "     ORDER BY oldest ASC, mode ASC, gkey ASC\n")
mutant("K3b-keyset-on-oldest-alone", "K3b",
       "ORDER BY and keyset on MIN(created_at) alone: the tied group on the page boundary is skipped",
       [(MAIN, V1_KEYSET, "        OR oldest > CAST(:c_oldest AS timestamptz)\n     ORDER BY oldest ASC\n")],
       [K3B])
twin("K3b-twin-expanded-or", "K3b", "the tuple comparison written in its expanded OR form",
     [(MAIN, V1_KEYSET,
       "        OR oldest > CAST(:c_oldest AS timestamptz)\n"
       "        OR (oldest = CAST(:c_oldest AS timestamptz) AND (mode > CAST(:c_mode AS varchar)\n"
       "            OR (mode = CAST(:c_mode AS varchar) AND gkey > CAST(:c_gkey AS uuid))))\n"
       "     ORDER BY oldest ASC, mode ASC, gkey ASC\n")],
     [K3B])

# ── K4: per-group completeness ───────────────────────────────────────────────

mutant("K4-limit-49", "K4", "the pending read with LIMIT 49",
       [(MAIN, '{"m": mode, "g": gid, "lim": _TRIAGE_QUOTA + 1}', '{"m": mode, "g": gid, "lim": 49}')], [K4])
twin("K4-twin-limit-51", "K4", "LIMIT 51",
     [(MAIN, '{"m": mode, "g": gid, "lim": _TRIAGE_QUOTA + 1}', '{"m": mode, "g": gid, "lim": 51}')], [K4])

# ── K5 / K14: PT1 per seat, the claimed reporter ─────────────────────────────

SEAT = '        seat = (row["mode"], row["group_id"], row["reporter_id"])\n'
mutant("K5-group-by-group-only", "K5", "GROUP BY group_id only (the reporter dropped from the key)",
       [(MAIN, SEAT, '        seat = (None, row["group_id"], None)\n')], [K5])
twin("K5-twin-key-reordered", "K5", "GROUP BY (group_id, reporter_id, mode)",
     [(MAIN, SEAT, '        seat = (row["group_id"], row["reporter_id"], row["mode"])\n'),
      (MAIN, "    for (mode, group, reporter), fams in seats.items():\n",
       "    for (group, reporter, mode), fams in seats.items():\n")],
     [K5])
mutant("K14-expand-to-player-ids", "K14", "PT1 expanded to player_ids",
       [(MAIN, "    for row in rows:\n" + SEAT,
         '    for row in [dict(x, reporter_id=p) for x in rows for p in (x.get("player_ids") or [x["reporter_id"]])]:\n'
         + SEAT)],
       [K14])
twin("K14-twin-reporter-as-text", "K14", "reporter_id as text",
     [(MAIN, SEAT, '        seat = (row["mode"], row["group_id"], _triage_str(row["reporter_id"]))\n')], [K14])

# ── K6, K6b, K6c, K6d: PT3's reads ───────────────────────────────────────────

PT3_LOOP = ('            for s in order:\n'
            '                if rep is None:\n')
mutant("K6-named-window-only", "K6", "rows restricted to game_number IN (named, named + 1)",
       [(MAIN, PT3_LOOP, '            for s in [x for x in order if t is not None and int(x["game_number"]) in (t, t + 1)]:\n'
                         '                if rep is None:\n')],
       [K6])
mutant("K6-one-row-per-number", "K6", "LIMIT 1 per number (the first row of each game number kept)",
       [(MAIN, PT3_LOOP, '            for s in [x for i, x in enumerate(order)\n'
                         '                      if all(int(y["game_number"]) != int(x["game_number"]) for y in order[:i])]:\n'
                         '                if rep is None:\n')],
       [K6])
twin("K6-twin-id-sort-key-twice", "K6", "id added as a final sort key twice",
     [(MAIN, '            order = sorted(rows, key=lambda s: (abs(int(s["game_number"]) - t), s["game_number"], s["id"]))\n',
       '            order = sorted(rows, key=lambda s: (abs(int(s["game_number"]) - t), s["game_number"], s["id"],'
       ' s["id"]))\n')],
     [K6])
mutant("K6b-none-as-zero", "K6b", "a None named number replaced by 0",
       [(MAIN, '        t = _triage_named(q["room"])\n', '        t = _triage_named(q["room"]) or 0\n')], [K6B])
twin("K6b-twin-isinstance", "K6b", "the None test written as not isinstance(named, int)",
     [(MAIN, '            if t is None:\n                order = sorted(rows, key=lambda s: (s["game_number"], s["id"]))\n',
       '            if not isinstance(t, int):\n                order = sorted(rows, key=lambda s: (s["game_number"], s["id"]))\n')],
     [K6B])
mutant("K6c-one-page-no-paging", "K6c", "one page of 200, no paging, the label still shown",
       [(MAIN, '                    if len(page) < _TRIAGE_PT3_PAGE:\n', '                    if True:\n')], [K6C])
twin("K6c-twin-page-199", "K6c", "page size 199",
     [(MAIN, "_TRIAGE_PT3_PAGE = 200 ", "_TRIAGE_PT3_PAGE = 199 ")], [K6C])
mutant("K6d-games-played-plus-one", "K6d", "expected = games_played + 1",
       [(MAIN, "    return max(int(games_played or 0), int(highest or 0)) + 1\n",
         "    return int(games_played or 0) + 1\n")], [K6D])
twin("K6d-twin-sql-greatest", "K6d", "the max computed by SQL GREATEST instead of in Python",
     [(MAIN, "    SELECT id, status, games_played, player_count\n      FROM ffa_lobbies\n",
       "    SELECT id, status, games_played, player_count,\n"
       "           GREATEST(games_played, COALESCE((SELECT MAX(m.game_number) FROM ffa_matches m\n"
       "                                            WHERE m.lobby_id = ffa_lobbies.id), 0)) AS gp_or_highest\n"
       "      FROM ffa_lobbies\n"),
      (MAIN, '                     "expected_game": (_triage_expected_game(grp["games_played"], highest)\n',
       '                     "expected_game": ((int(grp["gp_or_highest"]) + 1)\n')],
     [K6D])

# ── K7: PT3 vector parity with the arm ───────────────────────────────────────

PRIOR_VEC = ('    prior_vec = {v["steam_id"]: (int(v["rounds_won"] or 0), int(v["points_total"] or 0),\n'
             '                                 int(v["kills"] or 0), bool(v["left_early"]),\n'
             '                                 bool(v["absent"]))\n'
             '                 for v in row_vec}\n')
mutant("K7-vector-without-absent", "K7", "the vector built without absent",
       [(MAIN, PRIOR_VEC, PRIOR_VEC.replace('                                 bool(v["absent"]))\n',
                                            '                                 False)\n'))], [K7])
twin("K7-twin-named-fields", "K7", "the same tuple built from named fields in the same order",
     [(MAIN, PRIOR_VEC,
       '    prior_vec = {v["steam_id"]: tuple(f(v[k]) for f, k in ((lambda x: int(x or 0), "rounds_won"),\n'
       '                                                            (lambda x: int(x or 0), "points_total"),\n'
       '                                                            (lambda x: int(x or 0), "kills"),\n'
       '                                                            (bool, "left_early"), (bool, "absent")))\n'
       '                 for v in row_vec}\n')],
     [K7])

# ── K8: PT3b same reporter ───────────────────────────────────────────────────

SAME = '                    if rep_id is not None and s["reported_by"] == rep_id]\n'
mutant("K8-named-window-only", "K8", "PT3b restricted to rows at named and named + 1",
       [(MAIN, SAME, '                    if rep_id is not None and s["reported_by"] == rep_id\n'
                     '                    and t is not None and int(s["game_number"]) in (t, t + 1)]\n')], [K8])
mutant("K8-compares-the-lobby-host", "K8",
       "PT3b compared with the lobby host (ffa_lobbies.host_player_id, migration 166) instead of reported_by",
       [(MAIN, "    SELECT id, status, games_played, player_count\n      FROM ffa_lobbies\n",
         "    SELECT id, status, games_played, player_count, host_player_id\n      FROM ffa_lobbies\n"),
        (MAIN, SAME, '                    if rep_id is not None and (r["group"] or {}).get("host_player_id") == rep_id]\n')],
       [K8])
twin("K8-twin-canonical-text", "K8", "reported_by compared by canonical text",
     [(MAIN, SAME, '                    if rep_id is not None and str(s["reported_by"]) == str(rep_id)]\n')], [K8])

# ── K9 / K9b: PT4 re-capture after review ────────────────────────────────────

mutant("K9-pending-rows-only", "K9", "the reviewed read scans pending rows only",
       [(MAIN, "       AND photon_room_id IS NULL AND status <> 'pending'\n",
         "       AND photon_room_id IS NULL AND status = 'pending'\n")], [K9])
twin("K9-twin-status-in", "K9", "status IN ('accepted', 'discarded')",
     [(MAIN, "       AND photon_room_id IS NULL AND status <> 'pending'\n",
       "       AND photon_room_id IS NULL AND status IN ('accepted', 'discarded')\n")], [K9])
mutant("K9b-reviewed-one-page", "K9b", "the reviewed read capped at 200 with no paging",
       [(MAIN, '                if len(page) < _TRIAGE_PT4_PAGE:\n                    break\n'
               '                cur = (page[-1]["created_at"], page[-1]["id"])\n',
         '                break\n')], [K9B])
twin("K9b-twin-page-199", "K9b", "page size 199",
     [(MAIN, "_TRIAGE_PT4_PAGE = 200 ", "_TRIAGE_PT4_PAGE = 199 ")], [K9B])

# ── K10 / K10b: PT4 variant_of ───────────────────────────────────────────────

mutant("K10-match-on-null-column", "K10", "the keyed twin matched on the NULL column",
       [(MAIN, '            twin = r["keyed"].get(q["room"])\n', '            twin = r["keyed"].get(q["photon_room_id"])\n')],
       [K10])
twin("K10-twin-payload-path", "K10", "the same payload field read by path",
     [(MAIN, '            twin = r["keyed"].get(q["room"])\n',
       '            twin = r["keyed"].get((_json.loads(q["payload"]) or {}).get("photon_room_id"))\n')], [K10])
KEYED_SQL = "     WHERE mode = CAST(:m AS varchar)\n       AND photon_room_id = ANY(CAST(:rooms AS varchar[]))\n"
mutant("K10b-keyed-read-own-group", "K10b", "the keyed-twin read filtered by the group's own id",
       [(MAIN, KEYED_SQL, KEYED_SQL.replace("CAST(:m AS varchar)\n", "CAST(:m AS varchar) AND group_id = CAST(:g AS uuid)\n")),
        (MAIN, '_TRIAGE_SQL_V2_KEYED_TWINS, {"m": mode, "rooms": rooms}',
         '_TRIAGE_SQL_V2_KEYED_TWINS, {"m": mode, "rooms": rooms, "g": gid}')],
       [K10B])
twin("K10b-twin-mode-bind-as-text", "K10b",
     "the mode bind cast as text (the code already binds the mode as a parameter; see the notes' deviations)",
     [(MAIN, KEYED_SQL, KEYED_SQL.replace("CAST(:m AS varchar)\n", "CAST(:m AS text)\n"))], [K10B])

# ── K11: PT5 age and counts ──────────────────────────────────────────────────

AGE = "           EXTRACT(EPOCH FROM (now() - q.created_at)) AS age_s,\n"
mutant("K11a-age-from-reviewed-at", "K11", "age taken from the group's latest reviewed_at",
       [(MAIN, AGE, "           EXTRACT(EPOCH FROM (now() - COALESCE((SELECT MAX(r2.reviewed_at)"
                    " FROM match_report_quarantine r2\n"
                    "                WHERE r2.group_id = q.group_id), q.created_at))) AS age_s,\n")], [K11])
twin("K11a-twin-age-function", "K11", "age(now(), created_at)",
     [(MAIN, AGE, "           EXTRACT(EPOCH FROM age(now(), q.created_at)) AS age_s,\n")], [K11])
C2 = '                c2 = sum(1 for s in rows if int(s["game_number"]) > t)\n'
mutant("K11b-c2-received-after", "K11", "c2 counted over rows received after the capture",
       [(MAIN, C2, '                c2 = sum(1 for s in rows if s["ended_at"] > q["created_at"])\n')], [K11])
twin("K11b-twin-ge-plus-one", "K11", "c2 as game_number >= named + 1",
     [(MAIN, C2, '                c2 = sum(1 for s in rows if int(s["game_number"]) >= t + 1)\n')], [K11])

# ── K12: no automatic acceptance (static) ────────────────────────────────────

mutant("K12-update-status-in-V1", "K12", "in V1, UPDATE match_report_quarantine SET status = :st, st = 'accepted'",
       [(MAIN, V1_ADMIN, V1_ADMIN + "        await h.read(\"UPDATE match_report_quarantine SET status = :st"
                                    " WHERE false RETURNING id\", {\"st\": \"accepted\"})\n")], [K12])
mutant("K12-lower-case-two-lines", "K12",
       "the same UPDATE in lower case over two source lines, the line break between update and the table name",
       [(MAIN, V1_ADMIN, V1_ADMIN + '        await h.read("""update\n'
                                    '            match_report_quarantine set status = :st where false returning id""",'
                                    ' {"st": "accepted"})\n')], [K12])
mutant("K12-helper-outside-routes", "K12", "a new helper outside every route issuing that UPDATE",
       [(MAIN, BEFORE_HANDLE_CLASS,
         "async def _k12_helper(db):\n"
         "    await db.execute(text(\"UPDATE match_report_quarantine SET status = 'accepted' WHERE false\"))\n"
         "\n\n" + BEFORE_HANDLE_CLASS)], [K12])
twin("K12-twin-select-accepted", "K12", "a SELECT filtering status = 'accepted' in V1",
     [(MAIN, V1_ADMIN, V1_ADMIN + "        await h.read(\"SELECT id FROM match_report_quarantine"
                                  " WHERE status = 'accepted' LIMIT 0\")\n")], [K12])

# ── K13: the digest announces every new capture ──────────────────────────────

mutant("K13a-one-page-per-pass", "K13", "one page per pass", [(BOT, "    while len(page) >= size:\n",
                                                               "    while False:\n")], [K13A])
twin("K13a-twin-page-size-form", "K13",
     "the page-size test written as > size - 1 (the bot-side form of 'page size 499')",
     [(BOT, "    while len(page) >= size:\n", "    while len(page) > size - 1:\n")], [K13A])
mutant("K13b-created-at-cursor", "K13",
       "a created_at cursor with a 600 s overlap: a row is new only when created after the newest posted"
       " created_at less 600 s, so c (created before every announced row, committed late) is never posted",
       [(BOT, NEW_IDS,
         '    new = [r for r in rows if r["id"] not in st["announced"]\n'
         '           and datetime.fromisoformat(r["created_at"]).timestamp() > st.get("k13b_cursor", float("-inf")) - 600]\n'
         '    if new:\n'
         '        st["k13b_cursor"] = max(datetime.fromisoformat(r["created_at"]).timestamp() for r in new)\n')],
       [K13B])
twin("K13b-twin-list-call", "K13", "(added) the new-id list built by list() over a generator",
     [(BOT, NEW_IDS, '    new = list(r for r in rows if r["id"] not in st["announced"])\n')], [K13B])
mutant("K13c-mark-before-post", "K13", "mark before the post",
       [(BOT, ROUND_LOOP,
         '    for n, (content, mkeys) in enumerate(_qdigest_messages(lines, keys, header)):\n'
         '        for kind, key in mkeys:\n'
         '            (_qdigest["announced"] if kind == "id" else _qdigest["quota_named"]).add(key)\n'
         '        if not await _qdigest_send(channel, content):\n'
         '            return\n'
         '        if n == 0:\n'
         '            _qdigest["round_at"] = started\n')],
       [K13C, K13C2])
twin("K13c-twin-if-else-marking", "K13", "(added) the marking written as an explicit if/else",
     [(BOT, '        for kind, key in mkeys:\n'
            '            (_qdigest["announced"] if kind == "id" else _qdigest["quota_named"]).add(key)\n',
       '        for kind, key in mkeys:\n'
       '            if kind == "id":\n'
       '                _qdigest["announced"].add(key)\n'
       '            else:\n'
       '                _qdigest["quota_named"].add(key)\n')],
     [K13C, K13C2])
mutant("K13d-no-pruning", "K13", "(added, for K13 (d)) the complete pass prunes nothing",
       [(BOT, PRUNE, "        pass\n")], [K13D])
twin("K13d-twin-prune-twice", "K13", "pruning run twice per pass",
     [(BOT, PRUNE, PRUNE + PRUNE)], [K13D])

# ── K13e: the pass is finite ─────────────────────────────────────────────────

mutant("K13e-no-hw-bound-server", "K13e", "no hw bound in D1's page read",
       [(MAIN, "       AND q.created_at <= CAST(:hw AS timestamptz)\n", "")], [K13E_S])
twin("K13e-twin-transaction-timestamp", "K13e", "hw read as transaction_timestamp() instead of now()",
     [(MAIN, '_TRIAGE_SQL_D1_HW = "SELECT now() AS hw"', '_TRIAGE_SQL_D1_HW = "SELECT transaction_timestamp() AS hw"')],
     [K13E_S])
mutant("K13e-no-hw-bound-bot", "K13e", "the bot sends an unbounded hw on later pages",
       [(BOT, '        nxt = await _qdigest_page({"hw": first.get("hw"), "after_at": last["created_at"],\n',
         '        nxt = await _qdigest_page({"hw": "9999-12-31T00:00:00+00:00", "after_at": last["created_at"],\n')],
       [K13E_B])
twin("K13e-twin-hw-subscript", "K13e", "(added) hw read by subscript instead of get()",
     [(BOT, '        nxt = await _qdigest_page({"hw": first.get("hw"), "after_at": last["created_at"],\n',
       '        nxt = await _qdigest_page({"hw": first["hw"], "after_at": last["created_at"],\n')],
     [K13E_B])

# ── K13f: chunking and per-message marking ───────────────────────────────────

mutant("K13f-i-one-sliced-message", "K13f", "one joined message sliced to [:2000], every id marked",
       [(BOT, ROUND_LOOP,
         '    content = "\\n".join([header] + lines)[:2000]\n'
         '    if not await _qdigest_send(channel, content):\n'
         '        return\n'
         '    _qdigest["round_at"] = started\n'
         '    for kind, key in keys:\n'
         '        (_qdigest["announced"] if kind == "id" else _qdigest["quota_named"]).add(key)\n')],
       [K13F1])
mutant("K13f-ii-whole-round-marked", "K13f", "the whole round's ids marked after the first accepted message",
       [(BOT, ROUND_LOOP,
         '    msgs = _qdigest_messages(lines, keys, header)\n'
         '    for n, (content, mkeys) in enumerate(msgs):\n'
         '        if not await _qdigest_send(channel, content):\n'
         '            return\n'
         '        if n == 0:\n'
         '            _qdigest["round_at"] = started\n'
         '            for _, allkeys in msgs:\n'
         '                for kind, key in allkeys:\n'
         '                    (_qdigest["announced"] if kind == "id" else _qdigest["quota_named"]).add(key)\n')],
       [K13F2, K13C])
twin("K13f-twin-literal-limit", "K13f",
     "the limit written as the literal 2000 (the code already holds it in a named constant)",
     [(BOT, "        if cur_keys and size + 1 + len(line) > QDIGEST_MESSAGE_LIMIT:\n",
       "        if cur_keys and size + 1 + len(line) > 2000:\n")],
     [K13F1, K13F2])

# ── K13g: the loop premise, and a capture during a posting round ─────────────

REMINDER_TAIL = ('    if reminder_due and await _qdigest_send(channel, _qdigest_totals_line(totals, "quarantine digest'
                 ' reminder")):\n        st["reminder_at"] = time.monotonic()\n')
mutant("K13g-i-sleep-60-cooldown", "K13g", "an await asyncio.sleep(60) cooldown after the posting step",
       [(BOT, REMINDER_TAIL, REMINDER_TAIL + "    await asyncio.sleep(60)\n")], [K13G1])
twin("K13g-i-twin-sleep-0", "K13g", "await asyncio.sleep(0) at the same site",
     [(BOT, REMINDER_TAIL, REMINDER_TAIL + "    await asyncio.sleep(0)\n")], [K13G1])
ROUND_CALL = "    if round_due:\n        await _qdigest_round(channel, new, quota)\n"
mutant("K13g-ii-created-at-watermark", "K13g",
       "a created_at watermark set at each round's end; later passes post only rows created after it",
       [(BOT, ROUND_CALL, ROUND_CALL + '        st["k13g_wm"] = datetime.now(timezone.utc).timestamp()\n'),
        (BOT, NEW_IDS, '    new = [r for r in rows if r["id"] not in st["announced"]\n'
                       '           and datetime.fromisoformat(r["created_at"]).timestamp() > st.get("k13g_wm", float("-inf"))]\n')],
       [K13G2])
twin("K13g-ii-twin-round-end-for-log", "K13g", "the round's end time kept for the health log only",
     [(BOT, ROUND_CALL, ROUND_CALL + '        st["round_end"] = time.monotonic()\n')], [K13G2])

# ── K15: no SQL after the COMMIT, on the production path ─────────────────────

K15_HELPER = (
    "async def _k15_post_commit_write(db, path, stmt):\n"
    "    if path == \"session\":\n"
    "        await db.execute(text(stmt))\n"
    "        await db.commit()\n"
    "        return\n"
    "    from database import async_session as _own, release_session as _rel\n"
    "    async with (_own if path == \"own\" else _rel)() as s2:\n"
    "        await s2.execute(text(stmt))\n"
    "        await s2.commit()\n"
    "\n\n")
K15_STMTS = [
    ("gold_earned", "UPDATE players SET gold_earned = gold_earned + 1"),
    ("total_xp", "UPDATE players SET total_xp = total_xp + 1"),
    ("glicko", "INSERT INTO glicko_ratings_ffa (player_id) VALUES (gen_random_uuid())"),
    ("rating_history", "INSERT INTO rating_history (player_id, rating) VALUES (gen_random_uuid(), 1500)"),
    ("gold_tx", "INSERT INTO gold_transactions (player_id, amount, reason) VALUES (gen_random_uuid(), 1, 'k15')"),
    ("pc_packs", "INSERT INTO pc_packs (id, player_id) VALUES (gen_random_uuid(), gen_random_uuid())"),
    ("ffa_bets", "UPDATE ffa_bets SET amount = amount + 1"),
]
K15_PATHS = [("session", "the request's session"), ("own", "its own async_session"),
             ("release", "release_engine's session")]
BUILDS = {"V1": V1_BUILD, "V2": V2_BUILD, "D1": D1_BUILD}


def _k15(route, label, stmt, path, path_words):
    site = BUILDS[route]
    first, rest = site.split("\n", 1)
    mutant(f"K15-{route}-{label}-{path}", "K15",
           f"{route}'s build, after the COMMIT, calls a helper that issues {stmt!r} through {path_words} and commits",
           [(MAIN, BEFORE_HANDLE_CLASS, K15_HELPER + BEFORE_HANDLE_CLASS),
            (MAIN, site, first + "\n" + f"        await _k15_post_commit_write(db, {path!r}, {stmt!r})\n" + rest)],
           [K15])


for _label, _stmt in K15_STMTS:
    for _path, _words in K15_PATHS:
        _k15("V2", _label, _stmt, _path, _words)
for _route in ("V1", "D1"):
    for _path, _words in K15_PATHS:
        _k15(_route, "gold_earned", K15_STMTS[0][1], _path, _words)
twin("K15-twin-select-before-commit", "K15", "the same SELECT issued before the COMMIT, inside READ ONLY",
     [(MAIN, V2_ADMIN, V2_ADMIN + '        await h.read("SELECT gold_earned FROM players LIMIT 1")\n')], [K15])

# ── K15b: the seal itself ────────────────────────────────────────────────────

LISTEN = ('for _sealed_engine in (engine, release_engine):\n'
          '    event.listen(_sealed_engine.sync_engine, "before_cursor_execute", _refuse_sealed_statement)\n')
mutant("K15b-listener-removed", "K15b", "the listener removed",
       [(DB, LISTEN, "for _sealed_engine in (engine, release_engine):\n    pass\n")], [K15B])
mutant("K15b-engine-only", "K15b", "the listener attached to engine only (the release_engine path writes)",
       [(DB, LISTEN, LISTEN.replace("(engine, release_engine)", "(engine,)"))], [K15B])
mutant("K15b-reset-before-build", "K15b", "the variable reset before the response is built",
       [(MAIN, '    with _triage_post_commit_seal("quarantine triage"):\n        return await build(rows)\n',
         '    with _triage_post_commit_seal("quarantine triage"):\n        pass\n    return await build(rows)\n')],
       [K15B])
twin("K15b-twin-nested-try", "K15b",
     "the variable reset through its token in the same finally block, written as a nested try",
     [(DB, "    token = _post_commit_seal.set(owner)\n    try:\n        yield\n    finally:\n"
           "        _post_commit_seal.reset(token)\n",
       "    token = _post_commit_seal.set(owner)\n    try:\n        try:\n            yield\n        finally:\n"
       "            pass\n    finally:\n        _post_commit_seal.reset(token)\n")],
     [K15B])

# ── K16 / K16b: PT1's wording and receipt order ──────────────────────────────

PT1_TAIL = '        "statement": _TRIAGE_PT1_STATEMENT,\n    }\n'
mutant("K16a-label-restored", "K16", "V1's label 'counter one side of the sitting' restored",
       [(MAIN, PT1_TAIL, '        "statement": _TRIAGE_PT1_STATEMENT,\n'
                         '        "label": "counter one side of the sitting",\n    }\n')], [K16])
mutant("K16b-suggested-action-on-d", "K16", "a suggested-action field keyed on d != 0",
       [(MAIN, PT1_TAIL, '        "statement": _TRIAGE_PT1_STATEMENT,\n'
                         '        "suggested_action": ("review" if (isinstance(d, int) and d != 0) else "none"),\n    }\n')],
       [K16])
mutant("K16c-statement-dropped", "K16", "the fixed statement dropped",
       [(MAIN, PT1_TAIL, '        "statement": "",\n    }\n')], [K16])
twin("K16-twin-concatenated-literals", "K16", "the fixed statement assembled from two concatenated literals",
     [(MAIN, '    "Receipt order and the report\'s own number. The same values arise when this capture is a "\n',
       '    "Receipt order and the report\'s own number. " + "The same values arise when this capture is a "\n')],
     [K16])
RCOUNT = ('            r_count = (sum(1 for s in rows if s["ended_at"] < q["created_at"]) if complete else None)\n')
mutant("K16b-r-by-created-at", "K16b", "r counted over s.created_at < q.created_at",
       [(MAIN, RCOUNT, RCOUNT.replace('s["ended_at"] < q["created_at"]', 's["created_at"] < q["created_at"]'))], [K16B])
twin("K16b-twin-operands-swapped", "K16b", "the comparison written with its operands swapped",
     [(MAIN, RCOUNT, RCOUNT.replace('s["ended_at"] < q["created_at"]', 'q["created_at"] > s["ended_at"]'))], [K16B])

# ── K17: the digest loop starts ──────────────────────────────────────────────

START = "    if not poll_quarantine_digest.is_running(): poll_quarantine_digest.start()\n"
mutant("K17-start-line-deleted", "K17", "the start line deleted from on_ready", [(BOT, START, "")], [K17W])
mutant("K17-first-post-log-deleted", "K17", "the first-post log line deleted",
       [(BOT, '        print("[QDIGEST] first post accepted")\n', "        pass\n")], [K17])
twin("K17-twin-start-line-moved", "K17", "the start line moved to another position in on_ready's start list",
     [(BOT, START + "    if not poll_new_bans.is_running(): poll_new_bans.start()\n",
       "    if not poll_new_bans.is_running(): poll_new_bans.start()\n" + START)],
     [K17W, K17])

# ── K18: the team quota view ─────────────────────────────────────────────────

QUOTA_SQL = ("     WHERE status = 'pending' AND group_id IS NOT NULL\n"
             "     GROUP BY mode, group_id\n"
             "    HAVING COUNT(*) >= CAST(:quota AS integer)\n")
mutant("K18-ffa-only", "K18", "at-quota computed for mode 'ffa' only",
       [(MAIN, QUOTA_SQL, QUOTA_SQL.replace("group_id IS NOT NULL\n", "group_id IS NOT NULL AND mode = 'ffa'\n"))],
       [K18])
twin("K18-twin-gt-49", "K18", "the quota test written as > 49",
     [(MAIN, QUOTA_SQL, QUOTA_SQL.replace(">= CAST(:quota AS integer)", "> CAST(:quota AS integer) - 1"))], [K18])

# ── K19: team PT2 by mode ────────────────────────────────────────────────────

mutant("K19-pt2-from-ffa-lobbies", "K19", "PT2 read from ffa_lobbies by the group id",
       [(MAIN, V2_GROUP_READ, '        grp = await h.read(_TRIAGE_SQL_V2_LOBBY, {"g": gid})\n')], [K19])
twin("K19-twin-columns-reordered", "K19", "the team_series columns read in another order",
     [(MAIN, "    SELECT id, status, t1_series_wins, t2_series_wins, created_at, completed_at, invalidated_at\n",
       "    SELECT invalidated_at, completed_at, created_at, t2_series_wins, t1_series_wins, status, id\n")],
     [K19])


# ── same-site twins added after campaign 1 ───────────────────────────────────
# Campaign 1 (e1907c7) ran V5's twins as V5 words them. Several sit away from
# their mutants' site (another line, a constant, another route), so for those
# mutants no twin showed that editing the site itself leaves the check GREEN.
# Each twin below rewrites a mutated site another inert way, so every mutated
# site now has a twin of its own (#391). Appended after the first 124 plants,
# which keep their order.

D1_ENTRY = "        return resp\n\n    return await _triage_read_txn(db, read, build)\n"
twin("K2d-twin-D1-entry-assigned", "K2d",
     "(added; K2d-b's site) D1 enters the primitive once, its result assigned, then returned",
     [(MAIN, D1_ENTRY, "        return resp\n\n    result = await _triage_read_txn(db, read, build)\n"
                       "    return result\n")],
     [K2D])
twin("K2d-twin-V2-entry-assigned", "K2d",
     "(added; K2d-c's site) V2 enters the primitive once, its result assigned, then returned",
     [(MAIN, V2_BUILD + "\n    return await _triage_read_txn(db, read, build)\n",
       V2_BUILD + "\n    result = await _triage_read_txn(db, read, build)\n    return result\n")],
     [K2D])
twin("K6b-twin-get", "K6b", "(added; K6b-none-as-zero's site) the capture's room read with get()",
     [(MAIN, '        t = _triage_named(q["room"])\n', '        t = _triage_named(q.get("room"))\n')], [K6B])
twin("K6c-twin-not-ge", "K6c", "(added; K6c-one-page-no-paging's site) the short-page test written as not >=",
     [(MAIN, '                    if len(page) < _TRIAGE_PT3_PAGE:\n',
       '                    if not len(page) >= _TRIAGE_PT3_PAGE:\n')], [K6C])
twin("K6d-twin-terms-reordered", "K6d",
     "(added; K6d-games-played-plus-one's site) the + 1 and the max's arguments written in the other order",
     [(MAIN, "    return max(int(games_played or 0), int(highest or 0)) + 1\n",
       "    return 1 + max(int(highest or 0), int(games_played or 0))\n")], [K6D])
twin("K9b-twin-not-ge", "K9b", "(added; K9b-reviewed-one-page's site) the short-page test written as not >=",
     [(MAIN, '                if len(page) < _TRIAGE_PT4_PAGE:\n                    break\n',
       '                if not len(page) >= _TRIAGE_PT4_PAGE:\n                    break\n')], [K9B])
twin("K12-twin-helper-select", "K12",
     "(added; K12-helper-outside-routes's site) a new helper outside every route issuing a SELECT of the table",
     [(MAIN, BEFORE_HANDLE_CLASS,
       "async def _k12_helper(db):\n"
       "    await db.execute(text(\"SELECT id FROM match_report_quarantine WHERE status = 'accepted' LIMIT 0\"))\n"
       "\n\n" + BEFORE_HANDLE_CLASS)], [K12])
twin("K13e-twin-bound-operands-swapped", "K13e",
     "(added; K13e-no-hw-bound-server's site) D1's hw bound written with its operands swapped",
     [(MAIN, "       AND q.created_at <= CAST(:hw AS timestamptz)\n",
       "       AND CAST(:hw AS timestamptz) >= q.created_at\n")], [K13E_S])
twin("K13f-twin-item-unpacked", "K13f",
     "(added; the site of K13f i and ii) each message unpacked inside the loop body",
     [(BOT, ROUND_LOOP, ROUND_LOOP.replace(
         "    for n, (content, mkeys) in enumerate(_qdigest_messages(lines, keys, header)):\n",
         "    for n, item in enumerate(_qdigest_messages(lines, keys, header)):\n"
         "        content, mkeys = item\n"))],
     [K13F1, K13F2, K13C])


def _k15_twin(route):
    site = BUILDS[route]
    first, rest = site.split("\n", 1)
    twin(f"K15-twin-{route}-helper-not-called", "K15",
         f"(added; the K15-{route} mutants' site) the same helper planted; {route}'s build after the COMMIT "
         "holds the helper and the statement without calling it",
         [(MAIN, BEFORE_HANDLE_CLASS, K15_HELPER + BEFORE_HANDLE_CLASS),
          (MAIN, site, first + "\n"
           + f"        _k15_unused = (_k15_post_commit_write, 'session', {K15_STMTS[0][1]!r})\n" + rest)],
         [K15])


for _route in ("V2", "V1", "D1"):
    _k15_twin(_route)
twin("K15b-twin-engines-reversed", "K15b",
     "(added; the site of the two listener mutants) the listener attached to both engines, in the other order",
     [(DB, LISTEN, LISTEN.replace("(engine, release_engine)", "(release_engine, engine)"))], [K15B])
SEAL_BUILD = '    with _triage_post_commit_seal("quarantine triage"):\n        return await build(rows)\n'
twin("K15b-twin-built-then-returned", "K15b",
     "(added; K15b-reset-before-build's site) the response built inside the sealed block, returned after it",
     [(MAIN, SEAL_BUILD, '    with _triage_post_commit_seal("quarantine triage"):\n'
                         '        built = await build(rows)\n    return built\n')],
     [K15B])
twin("K16-twin-statement-through-str", "K16",
     "(added; the three K16 mutants' site) the fixed statement passed through str()",
     [(MAIN, PT1_TAIL, '        "statement": str(_TRIAGE_PT1_STATEMENT),\n    }\n')], [K16])
twin("K17-twin-first-post-concatenated", "K17",
     "(added; K17-first-post-log-deleted's site) the first-post line written as two concatenated literals",
     [(BOT, '        print("[QDIGEST] first post accepted")\n',
       '        print("[QDIGEST] first post " + "accepted")\n')], [K17])
twin("K19-twin-test-inverted", "K19",
     "(added; K19-pt2-from-ffa-lobbies's site) the mode test inverted and its branches swapped",
     [(MAIN, V2_GROUP_READ, '        grp = await h.read(_TRIAGE_SQL_V2_SERIES if mode != "ffa" else _TRIAGE_SQL_V2_LOBBY,'
                            ' {"g": gid})\n')], [K19])

# ── the runner ───────────────────────────────────────────────────────────────

class Refused(Exception):
    pass


def git(*args) -> str:
    return subprocess.run(["git", "-C", str(WT), *args], capture_output=True, text=True, check=True).stdout


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render(text_: str, crlf: bool) -> str:
    return text_.replace("\n", "\r\n") if crlf else text_


def plan(plant: Plant):
    """[(path, original bytes, new bytes)], refusing unless every old text
    occurs exactly once (edits to one file apply in order)."""
    files: dict = {}
    for rel, old, new in plant.edits:
        path = WT / rel
        if rel not in files:
            files[rel] = [path, path.read_bytes(), None]
        cur = files[rel][2] if files[rel][2] is not None else files[rel][1].decode("utf-8")
        crlf = "\r\n" in files[rel][1].decode("utf-8")
        o, n = render(old, crlf), render(new, crlf)
        count = cur.count(o)
        if count != 1:
            raise Refused(f"{plant.name}: old text occurs {count} times in {rel}, not exactly once:\n{old}")
        files[rel][2] = cur.replace(o, n, 1)
    return [(rel, p, orig, cur.encode("utf-8")) for rel, (p, orig, cur) in files.items()]


def node_outcomes(output: str, checks):
    """Each node's status from pytest's own short summary (-rA). The summary
    carries the failure message in full under -vv; a K2c node is also read
    from its K2C-VERDICT line, so a NO_VERDICT is never counted as a kill
    whatever the summary shows."""
    verdicts = {}
    for ln in output.splitlines():
        m = re.search(r"K2C-VERDICT case=(\S+) route=(\S+) .* verdict=(PASS|FAIL|NO_VERDICT)", ln)
        if m:
            verdicts.setdefault((m.group(1), m.group(2)), set()).add(m.group(3))
    out = {}
    for node in checks:
        tail = node.split("::", 1)[1]
        status = None
        for ln in output.splitlines():
            m = re.match(r"^(PASSED|FAILED|ERROR)\s+(\S+)(.*)$", ln)
            if m and m.group(2).endswith("::" + tail):
                status = m.group(1)
                if status == "FAILED" and "NO VERDICT" in m.group(3):
                    status = "NOVERDICT"
        k = re.search(r"\[(i|ii|iii|iv)-(V1|V2|D1|primitive)\]$", tail)
        if k and "k2c" in tail:
            seen = verdicts.get((k.group(1), k.group(2)), set())
            if "NO_VERDICT" in seen:
                status = "NOVERDICT"
            elif not seen and status in ("PASSED", "FAILED"):
                status = "NOLINE"      # a K2c node that printed no verdict line is not evidence
        out[node] = status or "MISSING"
    return out


def run_checks(checks, timeout_s):
    cmd = [sys.executable, "-m", "pytest", *checks, "-vv", "-rA", "-p", "no:cacheprovider",
           f"--rootdir={HERE}", "--tb=short"]
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"   # no .pyc from a planted file can outlive its plant
    env["PYTHONIOENCODING"] = "utf-8"
    t = time.monotonic()
    try:
        cp = subprocess.run(cmd, cwd=str(HERE), capture_output=True, timeout=timeout_s, env=env)
        code = cp.returncode
        out = (cp.stdout or b"").decode("utf-8", "replace") + (cp.stderr or b"").decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        code = -1
        out = ((e.stdout or b"").decode("utf-8", "replace") + (e.stderr or b"").decode("utf-8", "replace")
               + f"\nTIMEOUT after {timeout_s}s")
    return code, out, time.monotonic() - t


def verdict(plant, code, outcomes):
    vals = set(outcomes.values())
    if plant.expect == "RED":
        if code == 1 and vals == {"FAILED"}:
            return "RED as required", True
    else:
        if code == 0 and vals == {"PASSED"}:
            return "GREEN as required", True
    return f"FAILED (expected {plant.expect}; pytest exit {code}; nodes {sorted(vals)})", False


def evidence_lines(output: str, limit=14):
    keep = []
    for ln in output.splitlines():
        s = ln.rstrip()
        if (s.startswith("E ") or "K2C-VERDICT" in s or re.match(r"^(PASSED|FAILED|ERROR) ", s)
                or re.match(r"^=+ .*(passed|failed|error).* =+$", s) or "TIMEOUT after" in s):
            keep.append(s[:600])
    return keep[:limit] + ([f"... ({len(keep) - limit} more evidence lines)"] if len(keep) > limit else [])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--campaign", default="1")
    ap.add_argument("--expect-head")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--sites", action="store_true")
    ap.add_argument("--parse", action="store_true", help="with --sites: also parse every planted file")
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # diffs carry the files' own characters
    log = open(a.log, "a", encoding="utf-8")

    def say(s=""):
        print(s, flush=True)
        log.write(s + "\n")
        log.flush()

    names = [p.name for p in P]
    assert len(names) == len(set(names)), "duplicate plant names"
    todo = [p for p in P if not a.only or p.name in a.only or p.control in a.only]
    if a.only and not todo:
        say(f"REFUSED: --only matched no plant: {a.only}")
        return 2
    if a.sites:
        bad = 0
        for p in todo:
            try:
                edits = plan(p)
                parsed = ""
                if a.parse:
                    for rel, _path, _orig, new in edits:
                        try:
                            ast.parse(new.decode("utf-8"))
                        except SyntaxError as e:
                            raise Refused(f"{p.name}: the planted {rel} does not parse: {e}")
                    parsed = ", every planted file parses"
                say(f"SITE OK {p.name}: {len(p.edits)} edit(s), each old text exactly once{parsed}")
            except Refused as e:
                bad += 1
                say(f"SITE REFUSED {e}")
        say(f"SITES: {len(todo) - bad} ok, {bad} refused, of {len(todo)} plants")
        return 1 if bad else 0
    if not os.environ.get("RJ_TRIAGE_TEST_PG_DSN"):
        say("REFUSED: RJ_TRIAGE_TEST_PG_DSN is unset; every live check would FAIL and read as a kill")
        return 2
    head = git("rev-parse", "HEAD").strip()
    if a.expect_head and not head.startswith(a.expect_head):
        say(f"REFUSED: HEAD {head} is not --expect-head {a.expect_head}")
        return 2
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    say(f"==== RJ-TRIAGE controls, campaign {a.campaign}: start {started}, HEAD {head}, {len(todo)} plants "
        f"({sum(p.kind == 'mutant' for p in todo)} mutants, {sum(p.kind == 'twin' for p in todo)} twins)")
    results = []
    pg_log = os.environ.get("RJ_TRIAGE_PG_LOG")
    for i, p in enumerate(todo, 1):
        say("")
        say(f"---- [{i}/{len(todo)}] {p.name} ({p.control} {p.kind}, expect {p.expect}): {p.what}")
        status = git("status", "--porcelain")
        say(f"git status --porcelain before: {'EMPTY' if not status.strip() else 'NOT EMPTY'}")
        if status.strip():
            say("REFUSED: the tree is not clean\n" + status)
            return 2
        say(f"HEAD {git('rev-parse', 'HEAD').strip()}")
        try:
            edits = plan(p)
        except Refused as e:
            say(f"REFUSED: {e}")
            results.append((p, "FAILED (site refused)", False))
            continue
        ok = False
        res = "FAILED (not run)"
        try:
            for rel, path, orig, new in edits:
                say(f"sha256 before {rel}: {sha(orig)}")
                path.write_bytes(new)
                diff = difflib.unified_diff(orig.decode("utf-8").splitlines(), new.decode("utf-8").splitlines(),
                                            f"a/{rel}", f"b/{rel}", n=1, lineterm="")
                for ln in diff:
                    say("    " + ln)
            if pg_log and any("k2c" in c for c in p.checks):
                with open(pg_log, "a", encoding="utf-8") as fh:
                    fh.write(f"\n== controls campaign {a.campaign}, plant {p.name} ({p.kind}, expect {p.expect}), "
                             f"HEAD {head[:7]}, {time.strftime('%H:%M:%SZ', time.gmtime())}\n")
            code, output, secs_ = run_checks(p.checks, a.timeout)
            outcomes = node_outcomes(output, p.checks)
            res, ok = verdict(p, code, outcomes)
            say(f"check: {len(p.checks)} node(s), pytest exit {code}, {secs_:.1f}s")
            for node, st in outcomes.items():
                say(f"    {st:9} {node}")
            for ln in evidence_lines(output):
                say("    | " + ln)
        finally:
            for rel, path, orig, new in edits:
                path.write_bytes(orig)
                after = sha(path.read_bytes())
                say(f"sha256 after  {rel}: {after} {'(restored)' if after == sha(orig) else '(NOT RESTORED)'}")
                if after != sha(orig):
                    ok, res = False, "FAILED (restore mismatch)"
            status = git("status", "--porcelain")
            say(f"git status --porcelain after: {'EMPTY' if not status.strip() else 'NOT EMPTY'}")
            if status.strip():
                ok, res = False, "FAILED (tree not clean after restore)"
        say(f"RESULT {p.name}: {res}")
        results.append((p, res, ok))
        if res.startswith("FAILED (tree not clean") or res.startswith("FAILED (restore"):
            say("STOPPING: the tree could not be put back")
            break
    say("")
    red = [p.name for p, r, ok in results if ok and p.kind == "mutant"]
    green = [p.name for p, r, ok in results if ok and p.kind == "twin"]
    bad = [(p.name, r) for p, r, ok in results if not ok]
    say(f"==== campaign {a.campaign} summary: end {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}, HEAD {head}")
    say(f"mutants RED as required: {len(red)} of {sum(p.kind == 'mutant' for p in todo)}")
    say(f"twins GREEN as required: {len(green)} of {sum(p.kind == 'twin' for p in todo)}")
    say(f"not as required: {len(bad)}")
    for n, r in bad:
        say(f"    {n}: {r}")
    say("KILL SET " + ",".join(sorted(red)))
    say("KILL SET sha256 " + hashlib.sha256(",".join(sorted(red)).encode()).hexdigest())
    say("GREEN SET sha256 " + hashlib.sha256(",".join(sorted(green)).encode()).hexdigest())
    by_control: dict = {}
    for p, r, ok in results:
        c = by_control.setdefault(p.control, [0, 0, 0, 0])
        c[0 if p.kind == "mutant" else 2] += 1
        if ok:
            c[1 if p.kind == "mutant" else 3] += 1
    for ctl, (m, mr, t_, tg) in sorted(by_control.items(), key=lambda kv: (len(kv[0]), kv[0])):
        say(f"    {ctl:5} mutants {mr}/{m} RED, twins {tg}/{t_} GREEN")
    log.close()
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
