"""The FFA readmission controls (design V3, server half; lore #391): each
row's mutant and inert twin, run against this lane's tests.

A MUTANT must turn its test red on the assertion the row names: the test's
first failure is an AssertionError whose message's first element is that
tag. Anything else - a pass, another assertion, an exception, an error in
setup - is recorded as what it is and never counted. A TWIN is an inert
edit at the mutated site; its test must stay green (the negative
control: the copy-and-edit machinery alone turns nothing red).

Every edit is an exact text replacement on a scratch copy of backend/api,
backend/sql and backend/tests; each asserts how many times its old text
occurs before it applies, so a stale entry fails as STALE instead of
running an unmutated copy. Scratch copies are made under RDM_SCRATCH_DIR
(required) and removed after their run; a tracked file is never written.

With RDM_SEAT_LOCK set (the suite seat's lock file), each pytest run takes
the seat by an exclusive create just before it and releases it the moment
the run exits (a per-run hold); the copy is made outside the hold.

Usage (one lane database per concurrent run):
  RDM_SCRATCH_DIR=<dir> python rdm_controls.py check
  RDM_SCRATCH_DIR=<dir> python rdm_controls.py run --db <name> --out <file> [--rows M4.1,M4.2]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
HOST = "postgresql+asyncpg://postgres@127.0.0.1:55432/"
COPY = ("backend/api", "backend/sql", "backend/tests")
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".env", "*.env")
TIMEOUT_S = 900
MAIN = "backend/api/main.py"
RP = "test_ffa_readmit_pg.py::"
RJ = "test_ffa_report_journal_pg.py::"


class Stale(Exception):
    pass


def _site_twin(row):
    """The inert edit at the SAME site as the row's mutant: a comment line,
    at the site's own indentation, inserted right before the mutant's first
    anchor (a comment is legal inside brackets too, so a site within a
    multi-line call or string concatenation keeps its meaning)."""
    rel, old, _new, count = row["mutant"][0]
    if "twin_at" in row:
        old = row["twin_at"]
    indent = old[:len(old) - len(old.lstrip(" "))]
    if not indent and not old.startswith(("async def", "def ")):
        raise Stale("%s: twin anchor does not start a line" % row["row"])
    return [(rel, old, indent + "# rdm control twin: inert\n" + old, count)]


ROWS = [
    {"row": "M2.7", "node": RP + "test_t2_6_the_flag_is_written_at_lock_and_never_rederived",
     "tag": "T2.6 after drop",
     "mutant": [(MAIN,
                 '    return bool(lobby is not None and lobby.get("readmit_v1"))\n',
                 '    if lobby is None:\n'
                 '        return False\n'
                 '    live = [m for m in (lobby.get("member_ids") or [])\n'
                 '            if m not in (lobby.get("departed_ids") or [])]\n'
                 '    return bool((await _ffa_asm_gates(db, live))[2])\n', 1)]},
    {"row": "M3.1", "node": RJ + "test_t3_1_the_class_matrix", "tag": "T3.1 journaled",
     "mutant": [(MAIN,
                 '    if mine == "c" and int(getattr(report, "self_lag", 0) or 0) == 0 \\\n'
                 '            and _rdm_elected(classes, now) == sid:\n'
                 '        return {"mode": "settle", "cls": "c"}\n',
                 '    if True:\n'
                 '        return {"mode": "settle", "cls": mine}\n', 1)]},
    {"row": "M3.2", "node": RJ + "test_t3_1_the_class_matrix", "tag": "T3.1 g1",
     "mutant": [(MAIN,
                 '        if not journaled and g in [int(x) for x in (rep["lag_games"] or [])]:\n',
                 '        if g in [int(x) for x in (rep["lag_games"] or [])]:\n', 1)]},
    {"row": "M3.3", "node": RJ + "test_t3_1_the_class_matrix", "tag": "T3.1 l over g",
     "mutant": [(MAIN,
                 '        if not journaled and (rep["late_admitted_at"] is not None\n',
                 '        if (rep["late_admitted_at"] is not None\n', 1)]},
    {"row": "M3.4", "node": RJ + "test_t3_1_the_class_matrix", "tag": "T3.1 g1",
     "mutant": [(MAIN,
                 '    if _rdm_settle == "g1":\n        rated = False\n',
                 '    if False:\n        rated = False\n', 1)]},
    {"row": "M3.5",
     "node": RJ + "test_t3_2_server_lag_without_client_publication_cannot_win_election",
     "tag": "T3.2 class C settles",
     "mutant": [(MAIN,
                 '             if v["cls"] == "c" and v["census_at"] is not None'
                 ' and v["census_at"] >= horizon]\n',
                 '             if v["census_at"] is not None and v["census_at"] >= horizon]\n',
                 1)]},
    {"row": "M3.6", "node": RJ + "test_t3_3_edge_races", "tag": "T3.3 r waits",
     "mutant": [(MAIN,
                 '    if mine == "c" and int(getattr(report, "self_lag", 0) or 0) == 0 \\\n',
                 '    if mine == "r":\n'
                 '        return {"mode": "settle", "cls": "r"}\n'
                 '    if mine == "c" and int(getattr(report, "self_lag", 0) or 0) == 0 \\\n',
                 1)]},
    {"row": "M3.7", "node": RJ + "test_t3_3_edge_races", "tag": "T3.3 r waits",
     "mutant": [(MAIN,
                 '    if mine == "c" and int(getattr(report, "self_lag", 0) or 0) == 0 \\\n',
                 '    if mine == "r":\n'
                 '        raise FfaReportRefusal(409, "This seat may not report", progress)\n'
                 '    if mine == "c" and int(getattr(report, "self_lag", 0) or 0) == 0 \\\n',
                 1)]},
    {"row": "M3.8", "node": RJ + "test_t3_4_one_settlement_under_a_race",
     "tag": "T3.4 one settlement",
     "mutant": [(MAIN,
                 '    if _rdm_journal is not None:\n'
                 '        await _rdm_journal_recheck(db, lobby, lobby_uuid, report, _rdm_journal)\n',
                 '', 1)]},
    {"row": "M3.9", "node": RP + "test_t4_5_claim_bind_entered_and_a_second_drop",
     "tag": "T4.5 moved",
     "mutant": [(MAIN,
                 '        "       gone_game = NULL, gone_path = NULL, left_at = NULL, left_cause = NULL,"\n'
                 '        "       left_label = NULL, left_path = NULL,"\n'
                 '        "       hold_n = NULL',
                 '        "       hold_n = NULL', 1)]},
    {"row": "M4.1", "node": RP + "test_t4_1_the_hold_writer_and_its_predicates",
     "tag": "T4.1 in_room_exit",
     "mutant": [(MAIN, '    if _rdm_chosen_exit(seat["left_cause"]):\n',
                 '    if False:\n', 1)]},
    {"row": "M4.2", "node": RP + "test_t4_1_the_hold_writer_and_its_predicates",
     "tag": "T4.1 departed",
     "mutant": [(MAIN,
                 '    pid = subject["player_id"]\n'
                 '    if pid in list(lob["departed_ids"] or []):\n        return False\n',
                 '    pid = subject["player_id"]\n', 1)]},
    # The flag predicate of the hold has two sites: the caller's short-circuit
    # in _asm_gone_write and the writer's own re-read under the lobby lock.
    # Either alone is masked by the other (run2: a writer-only mutant stayed
    # GREEN), so the mutant removes the predicate at both: the hold path
    # ignores the flag.
    {"row": "M4.3", "node": RP + "test_t4_1_the_hold_writer_and_its_predicates",
     "tag": "T4.1 flag false",
     "mutant": [(MAIN,
                 '    if lob is None or not await _asm_readmit_on(ctx.db, lob):\n        return False\n'
                 '    if lob["status"] != "active"',
                 '    if lob is None:\n        return False\n'
                 '    if lob["status"] != "active"', 1),
                (MAIN,
                 '    held = await _asm_readmit_on(ctx.db, ctx.lobby) and await _asm_hold_after_gone(ctx, subject)\n',
                 '    held = await _asm_hold_after_gone(ctx, subject)\n', 1)]},
    {"row": "M4.4", "node": RP + "test_t4_1_the_hold_writer_and_its_predicates",
     "tag": "T4.1 window",
     "mutant": [(MAIN, '    if left_s < RDM_MIN_WINDOW_S:\n', '    if left_s < 0:\n', 1)]},
    {"row": "M4.5", "node": RP + "test_t4_2_the_anchor_is_the_last_presence",
     "tag": "T4.2 anchor",
     "mutant": [(MAIN,
                 '    anchor = seat["present_at"] if seat["present_at"] is not None'
                 ' else seat["verdict_at"]\n',
                 '    anchor = ctx.now\n', 1)]},
    {"row": "M4.6", "node": RP + "test_t4_2_the_anchor_is_the_last_presence",
     "tag": "T4.2 clock",
     "mutant": [(MAIN, '    left_s = (until - ctx.now).total_seconds()\n',
                 '    left_s = (until - (ctx.now - timedelta(seconds=60))).total_seconds()\n', 1)]},
    {"row": "M4.7", "node": RP + "test_t4_2_the_anchor_is_the_last_presence",
     "tag": "T4.2 held_at",
     "mutant": [(MAIN,
                 '        "         CAST(:now AS timestamptz), CAST(:until AS timestamptz))"),\n'
                 '        {"lid": ctx.lid, "pid": pid, "n": n, "anchor": anchor, "now": ctx.now,',
                 '        "         now(), CAST(:until AS timestamptz))"),\n'
                 '        {"lid": ctx.lid, "pid": pid, "n": n, "anchor": anchor, "now": ctx.now,',
                 1)]},
    {"row": "M4.8", "node": RP + "test_t4_3_old_clears_leave_the_hold",
     "tag": "T4.3 queue mirror",
     "mutant": [(MAIN,
                 '    subject.update({"hold_n": n, "hold_anchor_at": anchor, "hold_until": until})\n',
                 '    await ctx.db.execute(text(\n'
                 '        "UPDATE ffa_queue SET held_until = CAST(:until AS timestamptz),"\n'
                 '        "       held_lobby = :lid WHERE player_id = :pid"),\n'
                 '        {"until": until, "lid": ctx.lid, "pid": pid})\n'
                 '    subject.update({"hold_n": n, "hold_anchor_at": anchor, "hold_until": until})\n',
                 1)]},
    {"row": "M4.9", "node": RP + "test_t4_4_the_lapse_order_and_one_commit", "tag": "T4.4 order",
     "mutant": [(MAIN,
                 '        ctx = await _asm_ctx_slot(db, lid, route="readmit_lapse", trigger="lapse")\n'
                 '        qids = (await db.execute(text("SELECT player_id FROM ffa_queue'
                 ' WHERE series_id = :lid"),\n'
                 '                                 {"lid": lid})).scalars().all()\n'
                 '        await _ffa_lock_queue_rows(db, qids)\n',
                 '        qids = (await db.execute(text("SELECT player_id FROM ffa_queue'
                 ' WHERE series_id = :lid"),\n'
                 '                                 {"lid": lid})).scalars().all()\n'
                 '        await _ffa_lock_queue_rows(db, qids)\n'
                 '        ctx = await _asm_ctx_slot(db, lid, route="readmit_lapse", trigger="lapse")\n',
                 1)]},
    {"row": "M4.10", "node": RP + "test_t4_4_the_lapse_order_and_one_commit",
     "tag": "T4.4 one commit",
     "mutant": [(MAIN,
                 '    if depart and row["left_at"] is not None:\n',
                 '    await ctx.db.commit()\n'
                 '    if depart and row["left_at"] is not None:\n', 1)]},
    {"row": "M4.11", "node": RP + "test_t4_5_claim_bind_entered_and_a_second_drop",
     "tag": "T4.5 rebound",
     "mutant": [(MAIN,
                 '        "   SET actor_nr = CAST(:x AS smallint), actor_region = CAST(:r AS varchar),"\n'
                 '        "       actor_claim = CAST(:x AS smallint), claim_region = CAST(:r AS varchar),"\n'
                 '        "       gone_game = NULL',
                 '        "   SET gone_game = NULL', 1)]},
    {"row": "M4.12", "node": RP + "test_t4_5_claim_bind_entered_and_a_second_drop",
     "tag": "T4.5 serializer",
     "mutant": [(MAIN,
                 '"actor": int(r["actor_nr"]), "kind": r["kind"],\n'
                 '                 "game": None if r["game"] is None else int(r["game"]),\n',
                 '"actor": int(r["actor_nr"]),\n', 1)],
     "twin_at": '            e = {"slot": int(r["slot"]), "actor": int(r["actor_nr"]),'
                ' "kind": r["kind"],\n'},
    {"row": "M4.13", "node": RP + "test_t4_5_claim_bind_entered_and_a_second_drop",
     "tag": "T4.5 row",
     "mutant": [(MAIN,
                 '        "       game = CAST(:g AS smallint),"\n'
                 '        "       gone_game = s.gone_game, gone_path = s.gone_path, left_at = s.left_at,"\n'
                 '        "       left_cause = s.left_cause, left_label = s.left_label,'
                 ' left_path = s.left_path"\n',
                 '        "       game = CAST(:g AS smallint)"\n', 1)]},
    {"row": "M4.14", "node": RP + "test_t4_5_every_refusal_reason", "tag": "T4.5 departed",
     "mutant": [(MAIN,
                 '    if pid in list(ctx.lobby["departed_ids"] or []) or me["released_at"]'
                 ' is not None:\n',
                 '    if me["released_at"] is not None:\n', 1)]},
    {"row": "M4.23", "node": RP + "test_t4_14_headroom_reserves_the_held_place",
     "tag": "T4.14 headroom",
     "mutant": [(MAIN, '        _fighters = _rdm_r\n',
                 '        _fighters = int(game["fighter_target"] or 0)\n', 1)]},
    {"row": "M4.24", "node": RP + "test_t4_15_attest_counts_a_held_seat_present",
     "tag": "T4.15 omit a live fighter",
     "mutant": [(MAIN,
                 '    return (steam_id in true_roster and (att | held) == true_roster\n'
                 '            and (true_roster - held) <= att)\n',
                 '    return steam_id in true_roster and att <= true_roster\n', 1)]},
    {"row": "M4.25", "node": RP + "test_t4_15_attest_counts_a_held_seat_present",
     "tag": "T4.15 omit a live fighter",
     "mutant": [(MAIN,
                 '    return _rdm_attest_ok(roster, true_roster, held, steam_id)\n',
                 '    return _rdm_attest_ok(roster, true_roster,\n'
                 '                          set(true_roster) - set(roster), steam_id)\n', 1)]},
    {"row": "M5.1", "node": RP + "test_t5_1_a_rolled_back_hold_leaves_no_row",
     "tag": "T5.1 rollback",
     "mutant": [(MAIN,
                 '    await ctx.db.execute(text(\n'
                 '        "DELETE FROM queue_leases WHERE player_id = :pid AND mode = \'ffa\''
                 ' AND group_id = :lid"),\n',
                 '    await ctx.db.commit()\n'
                 '    await ctx.db.execute(text(\n'
                  '        "DELETE FROM queue_leases WHERE player_id = :pid AND mode = \'ffa\''
                  ' AND group_id = :lid"),\n', 1)]},
    {"row": "F1.H1", "node": RJ + "test_h1_readmit_economics_use_only_server_absence",
     "tag": "H1 present economics",
     "mutant": [(MAIN,
                  '    if _rdm_on:\n'
                  '        ghosts, graced, _leave_log = set(), set(), []\n'
                  '    else:\n'
                  '        ghosts, graced, _leave_log = _ffa_leave_decision(report, kills_in_canonical)\n',
                  '    if False:\n'
                  '        ghosts, graced, _leave_log = set(), set(), []\n'
                  '    else:\n'
                  '        ghosts, graced, _leave_log = _ffa_leave_decision(report, kills_in_canonical)\n',
                  1),
                 (MAIN,
                  '    if lobby.get("readmit_v1"):\n'
                  '        unrated = set()\n',
                  '    if False:\n'
                  '        unrated = set()\n', 1)]},
    {"row": "F1.H2", "node": RJ + "test_h2_bound_but_unentered_returner_is_u",
     "tag": "H2 bound unentered",
     "mutant": [(MAIN,
                  '        elif r["player_id"] in all_rdm:\n'
                  '            c = "u"\n',
                  '        elif False:\n'
                  '            c = "u"\n', 1)]},
    {"row": "F1.H3", "node": RJ + "test_h3_delayed_choice_uses_the_stored_receipt_class",
     "tag": "H3 stored class",
     "mutant": [(MAIN,
                  '        c = jr.get("cls") or "u"\n',
                  '        sid = jr["steam_id"]\n'
                  '        c = classes.get(sid, {}).get("cls", "u")\n'
                  '        if jr["self_lag"] and c == "c":\n'
                  '            c = "g"\n', 1)]},
    {"row": "F1.H4", "node": RJ + "test_h4_retryable_failures_keep_the_chosen_receipt",
     "tag": "H4 retryable held",
     "mutant": [(MAIN,
                  '        if ex.status_code >= 500:\n'
                  '            return False\n',
                  '', 1)]},
    {"row": "F1.H5.ACTIVE",
     "node": RP + "test_h5_deletion_locks_an_active_seat_before_hold_creation",
     "tag": "H5 active lobby",
     "mutant": [(MAIN,
                  '        "SELECT s.lobby_id FROM ffa_assembly_seats s"\n'
                  '        "  JOIN ffa_lobbies l ON l.id = s.lobby_id"\n'
                  '        " WHERE s.player_id = :pid AND l.status = \'active\' AND l.readmit_v1"),\n',
                  '        "SELECT lobby_id FROM ffa_assembly_seats"\n'
                  '        " WHERE player_id = :pid AND hold_n IS NOT NULL"),\n', 1)]},
    {"row": "F1.H5.READMIT",
     "node": RP + "test_h5_readmit_revalidates_identity_below_the_lobby_lock",
     "tag": "H5 readmit identity",
     "mutant": [(MAIN,
                  '        " WHERE s.lobby_id = :lid AND p.steam_id = :sid AND p.deleted_at IS NULL"),\n',
                  '        " WHERE s.lobby_id = :lid"\n'
                  '        "   AND (p.steam_id = :sid OR p.deleted_at IS NOT NULL)"),\n', 1)]},
    {"row": "F1.H5.OFFER",
     "node": RP + "test_h5_offer_holds_the_shared_identity_key_through_commit",
     "tag": "H5 offer identity",
     "mutant": [(MAIN,
                  '    await db.execute(text("SELECT pg_advisory_xact_lock_shared(hashtext(:sid))"),\n'
                  '                     {"sid": steam_id})\n'
                  '    await _check_steam_session(request, steam_id, db)\n',
                  '', 1)]},
    {"row": "F1.H5.REPORT",
     "node": RP + "test_h5_report_repeats_participant_lookup_below_the_lobby_lock",
     "tag": "H5 report identity",
     "mutant": [(MAIN,
                  '    prows = (await db.execute(\n'
                  '        select(Player.id, Player.steam_id).where(\n'
                  '            Player.steam_id.in_(steams), Player.deleted_at.is_(None))\n'
                  '    )).all()\n'
                  '    id_by_steam = {r.steam_id: r.id for r in prows}\n'
                  '    if len(id_by_steam) != len(steams):\n'
                  '        raise HTTPException(404, "One or more players not registered")\n',
                  '', 1)]},
    {"row": "F1.M1", "node": RP + "test_m1_started_readmit_uses_cadence_and_per_hold_caps",
     "tag": "M1 post-start census",
     "mutant": [(MAIN,
                  '    if not started_readmit:\n'
                  '        if cap and int(seat["writes"] or 0) >= ASM_WRITES_CAP:\n',
                  '    if True:\n'
                  '        if cap and int(seat["writes"] or 0) >= ASM_WRITES_CAP:\n', 1)]},
    {"row": "F1.M2.ATTEMPT",
     "node": RP + "test_t4_3b_the_trailing_timeout_leave_reaches_the_leave_guard",
     "tag": "M2 implicit decline row",
     "mutant": [(MAIN,
                  '        await _rdm_attempt(ctx.db, ctx.lid, seat["player_id"], int(n),\n'
                  '                           "decline", ctx.now, "ok")\n',
                  '', 1)]},
    {"row": "F1.M2.LIFECYCLE",
     "node": RP + "test_m2_decline_checks_lifecycle_and_writes_one_success",
     "tag": "M2 expired decline",
     "mutant": [(MAIN,
                  '    refused = await _rdm_live_or_lapse(ctx, pid, me, "decline", n)\n'
                  '    if refused is not None:\n'
                  '        return refused\n',
                  '    if me.get("hold_n") is None or int(me["hold_n"]) != n:\n'
                  '        return await _rdm_refuse(ctx, pid, me, "decline", n, "not_held")\n',
                  1)]},
    {"row": "F1.L1", "node": RP + "test_t4_4_the_lapse_order_and_one_commit",
     "tag": "T4.4 caller sorted",
     "mutant": [(MAIN,
                  '    if route == "readmit":\n'
                  '        qids.append(pid)\n',
                  '', 1)]},
    {"row": "F1.L2", "node": RP + "test_l2_attest_held_snapshot_has_an_active_lobby_fence",
     "tag": "T4.15 close fence",
     "mutant": [(MAIN,
                  '        " WHERE l.id = :lid AND l.status = \'active\'"),\n',
                  '        " WHERE l.id = :lid"),\n', 1)]},
    {"row": "H1", "node": RP + "test_health_marker_counts_every_site", "tag": "health ffa_readmit",
     "mutant": [(MAIN, '            await _ffa_readmit_janitor(async_session)\n',
                 '            pass\n', 1)]},
    {"row": "S8.1", "node": RP + "test_s8_deletion_clears_the_readmission_tables",
     "tag": "S8 ffa_report_journal",
     "mutant": [(MAIN,
                 '    await db.execute(text("DELETE FROM ffa_report_journal WHERE reporter_id = :pid"),\n'
                 '                     {"pid": pid})\n', '', 1)]},
    # The leave-cause helpers (r1b F3): the trailing timeout leave keeps a hold.
    # Run 16:3xZ: on T4.3 this mutant stayed GREEN (T4.3 never checks that the
    # guard is reached), so the row names T4.3b, which does.
    {"row": "B10", "node": RP + "test_t4_3b_the_trailing_timeout_leave_reaches_the_leave_guard",
     "tag": "T4.3b hold kept",
     "mutant": [(MAIN, '                elif not _rdm_trailing_drop(cause):\n',
                 '                elif True:\n', 1)]},
    # The janitor bound (the round 1 census ruling): one row per route of it.
    {"row": "B1", "node": RP + "test_t4_16_the_lapse_entry_declines_a_held_lobby",
     "tag": "T4.16 busy",
     "mutant": [(MAIN,
                 '    "SELECT id FROM ffa_lobbies WHERE id = :lid FOR NO KEY UPDATE SKIP LOCKED")\n',
                 '    "SELECT id FROM ffa_lobbies WHERE id = :lid FOR NO KEY UPDATE")\n', 1)]},
    {"row": "B2", "node": RP + "test_t4_16_the_lapse_entry_declines_a_held_lobby",
     "tag": "T4.16 gone",
     "mutant": [(MAIN, '            outcome = "busy" if there is not None else "gone"\n',
                 '            outcome = "busy"\n', 1)]},
    {"row": "B3", "node": RP + "test_t4_17_a_held_queue_row_bounds_the_lapse",
     "tag": "T4.17 bounded",
     "mutant": [(MAIN, '        _rdm_janitor_bound(db)\n        await _rdm_lapse_sweep(db)\n',
                 '        await _rdm_lapse_sweep(db)\n', 1)]},
    {"row": "B4", "node": RP + "test_t4_17_a_held_queue_row_bounds_the_lapse",
     "tag": "T4.17 bound line",
     "mutant": [(MAIN,
                 '        stage = _rdm_bound_stage(ex)\n'
                 '        if stage is not None:\n'
                 '            print(f"[FFA-RDM] lapse lobby',
                 '        stage = None\n'
                 '        if stage is not None:\n'
                 '            print(f"[FFA-RDM] lapse lobby', 1)]},
    {"row": "B5", "node": RP + "test_t4_18_the_bound_arms_every_janitor_transaction",
     "tag": "T4.18 every transaction",
     "mutant": [(MAIN, '    _sa_event.listen(db.sync_session, "after_begin", _arm)\n',
                 '    _sa_event.listen(db.sync_session, "after_begin", _arm, once=True)\n', 1)]},
    {"row": "B6", "node": RJ + "test_t3_7_a_held_window_bounds_settle_phase_one",
     "tag": "T3.7 bounded",
     "mutant": [(MAIN, '        _rdm_janitor_bound(db)\n        await _ffa_settle_due_windows(db)\n',
                 '        await _ffa_settle_due_windows(db)\n', 1)]},
    {"row": "B7", "node": RJ + "test_t3_8_a_bound_refusal_is_not_a_supersede",
     "tag": "T3.8 bound line",
     "mutant": [(MAIN,
                 '        todo.extend((getattr(e, "orig", None), e.__cause__, e.__context__))\n',
                 '        todo.extend((getattr(e, "orig", None), e.__cause__))\n', 1)]},
    {"row": "B8", "node": RJ + "test_t3_8_a_bound_refusal_is_not_a_supersede",
     "tag": "T3.8 bound line",
     "mutant": [(MAIN,
                 '        stage = _rdm_bound_stage(ex)\n'
                 '        if stage is not None:\n'
                 '            # The body turned',
                 '        stage = None\n'
                 '        if stage is not None:\n'
                 '            # The body turned', 1)]},
    {"row": "B9", "node": RJ + "test_t3_9_a_held_reporter_row_bounds_settle_phase_two",
     "tag": "T3.9 bound line",
     "mutant": [(MAIN,
                 '        stage = _rdm_bound_stage(ex)\n'
                 '        if stage is not None:\n'
                 '            print(f"[FFA-REPORT] journal window',
                 '        stage = None\n'
                 '        if stage is not None:\n'
                 '            print(f"[FFA-REPORT] journal window', 1)]},
]
for _row in ROWS:
    _row["twin"] = _site_twin(_row)


def scratch_root():
    d = os.environ.get("RDM_SCRATCH_DIR")
    if not d:
        raise SystemExit("RDM_SCRATCH_DIR is required (scratch copies go there)")
    os.makedirs(d, exist_ok=True)
    return d


def apply_edits(base, edits):
    for rel, old, new, count in edits:
        path = os.path.join(base, rel)
        with open(path, "rb") as fh:
            data = fh.read().decode("utf-8")
        if "\r\n" in data:
            # A checkout with CRLF line ends: the registry is written in LF.
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        found = data.count(old)
        if found != count:
            raise Stale("%s: %d occurrence(s) of %r, want %d" % (rel, found, old[:80], count))
        with open(path, "wb") as fh:
            fh.write(data.replace(old, new).encode("utf-8"))


def make_copy(edits, tag):
    d = tempfile.mkdtemp(prefix="rdm_%s_" % re.sub(r"[^A-Za-z0-9]", "_", tag),
                         dir=scratch_root())
    for rel in COPY:
        shutil.copytree(os.path.join(ROOT, rel), os.path.join(d, rel), ignore=IGNORE)
    apply_edits(d, edits)
    return d


def _quiet(minutes_before):
    t = time.gmtime()
    m = t.tm_hour * 60 + t.tm_min
    return any(q - minutes_before <= m < q + 30 for q in (300, 720))


def take_seat(holder, wait_s=9000):
    """With RDM_SEAT_LOCK set, take the seat for one run: on seeing the lock
    absent wait 15 s and re-check (a lane not first in the queue), then an
    atomic exclusive create; never inside a quiet window or within 4 minutes
    of one; also stand aside while RDM_SEAT_PRIORITY names a file that
    exists. Returns the lock path taken, or None when no lock is configured."""
    lock = os.environ.get("RDM_SEAT_LOCK")
    if not lock:
        return None
    prio = os.environ.get("RDM_SEAT_PRIORITY")
    t0 = time.time()
    while time.time() - t0 < wait_s:
        if (prio and os.path.exists(prio)) or _quiet(4) or os.path.exists(lock):
            time.sleep(5)
            continue
        time.sleep(15)
        if (prio and os.path.exists(prio)) or _quiet(4) or os.path.exists(lock):
            continue
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as fh:
            fh.write("%s %s\n" % (holder, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        return lock
    raise SystemExit("seat not taken within %d s" % wait_s)


def release_seat(lock):
    if lock:
        os.remove(lock)


def run_pytest(base, node, db):
    junit = os.path.join(base, "junit.xml")
    env = dict(os.environ)
    env["CF_TEST_PG_DSN"] = HOST + db
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    target = os.path.join(base, "backend", "tests", node)
    try:
        p = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q",
                            "-o", "junit_family=xunit1", "--junitxml", junit, target],
                           cwd=base, env=env, capture_output=True, text=True,
                           timeout=TIMEOUT_S)
        tail = (p.stdout or "")[-1500:]
    except subprocess.TimeoutExpired:
        return ("timeout", ""), "timeout"
    res = ("error", "no junit")
    if os.path.exists(junit):
        for tc in ET.parse(junit).getroot().iter("testcase"):
            kind, msg = "passed", ""
            for child in tc:
                if child.tag in ("failure", "error"):
                    kind = "failed" if child.tag == "failure" else "error"
                    msg = child.get("message") or ""
                elif child.tag == "skipped":
                    kind, msg = "skipped", child.get("message") or ""
            res = (kind, msg)
    return res, tail


_TUPLE_TAG = re.compile(r"^AssertionError: \((['\"])(.*?)\1[,)]", re.S)
_PLAIN_TAG = re.compile(r"^AssertionError: ([^\n]*)")


def first_tag(msg):
    m = _TUPLE_TAG.match(msg or "")
    if m:
        return m.group(2)
    m = _PLAIN_TAG.match(msg or "")
    return m.group(1).strip() if m else None


def verdict_mutant(result, want):
    kind, msg = result
    if kind == "passed":
        return "GREEN", None
    if kind != "failed":
        return kind.upper(), (msg or "")[:300]
    tag = first_tag(msg)
    if tag is None:
        return "RED-EXCEPTION", (msg or "")[:300]
    return ("RED-NAMED" if tag == want else "RED-OTHER"), tag


def selected(rows_arg):
    rows = ROWS
    if rows_arg:
        want = set(rows_arg.split(","))
        rows = [r for r in rows if r["row"] in want]
        missing = want - {r["row"] for r in rows}
        if missing:
            raise SystemExit("unknown rows: %s" % sorted(missing))
    return rows


def record(out, line):
    with open(out, "a", encoding="ascii", newline="\n") as fh:
        fh.write(json.dumps(line, sort_keys=True) + "\n")
    print(json.dumps(line, sort_keys=True), flush=True)


def cmd_check(args):
    """Every edit set applies to a scratch copy and the edited main.py compiles."""
    bad = 0
    for r in selected(args.rows):
        for kind in ("mutant", "twin"):
            d = None
            try:
                d = make_copy(r[kind], r["row"] + "_" + kind)
                with open(os.path.join(d, MAIN), "rb") as fh:
                    compile(fh.read(), MAIN, "exec")
                print("%s %s OK" % (r["row"], kind))
            except (Stale, SyntaxError) as exc:
                bad += 1
                print("%s %s %s: %s" % (r["row"], kind, type(exc).__name__, exc))
            finally:
                if d:
                    shutil.rmtree(d, ignore_errors=True)
    print("CHECK %s" % ("OK" if bad == 0 else "FAILED %d" % bad))
    return 0 if bad == 0 else 1


def _stamp():
    return time.strftime("%H:%M:%SZ", time.gmtime())


def cmd_run(args):
    """One scratch tree for the whole set: every control's edits touch only
    main.py, so before each run the pristine main.py is written back and that
    control's edits applied to it (anchors pre-checked for every control
    before the seat is taken). --hold set takes the seat once for the set
    and releases it when the set ends; --hold run takes it per pytest run."""
    bad = 0
    todo = [(r, kind) for r in selected(args.rows) for kind in ("mutant", "twin")
            if not args.only or kind == args.only.rstrip("s")]
    for r, kind in todo:
        if any(rel != MAIN for rel, _o, _n, _c in r[kind]):
            raise SystemExit("%s %s edits a file other than main.py" % (r["row"], kind))
    base = make_copy([], "set")
    main_path = os.path.join(base, MAIN)
    with open(main_path, "rb") as fh:
        pristine = fh.read()
    set_lock = None
    try:
        stale = {}
        for r, kind in todo:
            try:
                apply_edits(base, r[kind])
            except Stale as exc:
                stale[(r["row"], kind)] = str(exc)
            with open(main_path, "wb") as fh:
                fh.write(pristine)
        set_lock = take_seat(args.holder) if args.hold == "set" else None
        record(args.out, {"seat_taken": _stamp(), "hold": args.hold})
        for r, kind in todo:
            t0 = time.time()
            if (r["row"], kind) in stale:
                record(args.out, {"row": r["row"], "kind": kind, "verdict": "STALE",
                                  "detail": stale[(r["row"], kind)], "ok": False})
                bad += 1
                continue
            with open(main_path, "wb") as fh:
                fh.write(pristine)
            apply_edits(base, r[kind])
            lock = take_seat(args.holder) if args.hold == "run" else None
            t_take = _stamp()
            try:
                res, tail = run_pytest(base, r["node"], args.db)
            finally:
                release_seat(lock)
            t_rel = _stamp()
            bad += 0 if _finish(args, r, kind, res, tail, t0, t_take, t_rel) else 1
    finally:
        release_seat(set_lock)
        if set_lock:
            record(args.out, {"seat_released": _stamp()})
        shutil.rmtree(base, ignore_errors=True)
    record(args.out, {"summary": "OK" if bad == 0 else "FAILED", "bad": bad})
    return 0 if bad == 0 else 1


def _finish(args, r, kind, res, tail, t0, t_take, t_rel) -> bool:
    """Record one control's verdict; True when it counts (a mutant RED on its
    named assertion, a twin GREEN)."""
    if kind == "mutant":
        verdict, detail = verdict_mutant(res, r["tag"])
        ok = verdict == "RED-NAMED"
    else:
        verdict, detail = ("GREEN", None) if res[0] == "passed" else \
            (res[0].upper(), (res[1] or "")[:300])
        ok = verdict == "GREEN"
    record(args.out, {"row": r["row"], "kind": kind, "node": r["node"],
                      "want": r["tag"] if kind == "mutant" else "GREEN",
                      "verdict": verdict, "detail": detail, "ok": ok,
                      "secs": round(time.time() - t0, 1),
                      "run": "%s-%s" % (t_take, t_rel),
                      "tail": None if ok else tail[-600:]})
    return ok


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--rows")
    r = sub.add_parser("run")
    r.add_argument("--db", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--rows")
    r.add_argument("--only", choices=("mutants", "twins"))
    r.add_argument("--holder", default="rdm-controls")
    r.add_argument("--hold", choices=("set", "run"), default="set")
    args = ap.parse_args()
    return cmd_check(args) if args.cmd == "check" else cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
