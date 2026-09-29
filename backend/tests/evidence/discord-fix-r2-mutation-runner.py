"""Discord fix round 2, L2: the mutation campaign, with every restore frozen
in its evidence.

Round 1's runner asserted each restore but left no record of it in its log
(Codex round 1, LOW 2). This runner records, for EVERY mutation and every
file it touches: the SHA-256 before the mutation (the pre-image), after it
(the mutant), the test outcome, the SHA-256 after the restore, and the
output of `git status --porcelain`. The campaign FAILS, and stops at once,
when a restore does not give the pre-image back byte for byte or the status
is not empty: no next mutation begins before both hold.

It re-runs round 1's nineteen mutations - two re-anchored because round 2
rewrote the code they mutate (D1c: the send count is now _PC_OPEN_SENDS;
D2f: an unconfirmed purchase is now answered in _pc_buy_and_show) - and adds
round 2's: M1 (server and bot), L1, board row 32 and the release
discriminators. Each mutation names the tests it must turn red, and every
one of them must fail under it; the unmutated control run of each test file
must pass whole before any mutation runs.

    python backend/tests/evidence/discord-fix-r2-mutation-runner.py \\
        --tree <a clean disposable worktree> --log <log file>

The tree's files are edited in place and given back from byte copies taken
here, never through git (#290, #401: git checkout -- and git restore are
forbidden on a tree carrying work). Every anchor must occur exactly once
inside its top-level def or assignment, and all of them are checked before
any test runs (#432). The database gates come from the environment, as for
the suite; the log names each gate's database, never a host path.
"""
import argparse
import ast
import datetime
import hashlib
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

PACK = "backend/tests/test_discord_pack_open.py"
PULL = "backend/tests/test_discord_pull_post.py"
RULE = "backend/tests/test_discord_tournament_start_rule.py"
MARK = "backend/tests/test_health_discord_fix_marker.py"
BOT = "backend/discord_bot.py"
MAIN = "backend/api/main.py"
GATES = ("DISCORD_COLLECTION_TEST_PG_DSN", "PC_TRADES_TEST_PG_DSN", "FFA_TEST_PG_DSN", "LADDER_TEST_PG_DSN",
         "PC_EDITION_TEST_PG_DSN", "RJ_TRIAGE_TEST_PG_DSN", "SCR_MIGRATION_TEST_PG_DSN", "TEAM_DC_TEST_PG_DSN",
         "TICKET_REDACTION_TEST_PG_DSN")


def mutation(mid, rnd, what, path, span, old, new, target, red):
    return {"id": mid, "round": rnd, "what": what, "path": path, "span": span, "old": old, "new": new,
            "target": target, "red": list(red)}


MUTATIONS = [
    # -- round 1, re-run ---------------------------------------------------------------------------
    mutation("D1a", "r1", "cmd_pc_daily sends the old claim-only line and returns before the open",
             BOT, "cmd_pc_daily",
             '    await _pc_open_and_show(ctx, {"pack_id": str(pack_id)},\n',
             '    await ctx.send("Today\'s pack is yours - open it in-game."); return\n'
             '    await _pc_open_and_show(ctx, {"pack_id": str(pack_id)},\n',
             PACK, ["test_d1_daily_claims_opens_and_posts_the_pack_with_its_picture",
                    "test_d1_daily_opens_a_pack_claimed_earlier_and_left_unopened"]),
    mutation("D1b", "r1", "internal_pc_open_pack without _pc_bot_actor", MAIN, "internal_pc_open_pack",
             "    await _pc_bot_actor(db, player, discord_id)\n",
             "    pass   # mutation D1b: the bot's door without its identity lock and re-read\n",
             PACK, ["test_d1_the_identity_lock_is_taken_before_the_claim",
                    "test_d1_a_rebind_between_the_lookup_and_the_lock_is_refused",
                    "test_d1_the_opener_refuses_a_banned_player_and_writes_nothing",
                    "test_d2_an_erasure_between_the_lookup_and_the_lock_buys_nothing"]),
    mutation("D1c", "r1 re-anchored", "the open is sent once: _PC_OPEN_SENDS = 1", BOT, "_PC_OPEN_SENDS",
             "_PC_OPEN_SENDS = 3 ", "_PC_OPEN_SENDS = 1 ",
             PACK, ["test_d1_an_open_whose_answer_was_lost_is_sent_once_more_and_answers_the_committed_pack",
                    "test_d2_a_lost_purchase_answer_is_resent_with_the_same_nonce_and_charges_once",
                    "test_m1_every_unconfirmed_answer_is_replayed_with_the_same_key_a_bounded_number_of_times"]),
    mutation("D1d", "r1", "internal_pc_open_pack without _pc_require_renderer()", MAIN, "internal_pc_open_pack",
             "    _pc_require_renderer()\n",
             "    pass   # mutation D1d: the bot's door without the renderer gate\n",
             PACK, ["test_d1_the_renderer_gate_refuses_before_any_write"]),
    mutation("D1e", "r1", "_pc_bot_actor without its deleted re-check", MAIN, "_pc_bot_actor",
             '    if row is None or row["deleted_at"] is not None:\n',
             "    if row is None:   # mutation D1e: no deleted re-check under the lock\n",
             PACK, ["test_d2_an_erasure_between_the_lookup_and_the_lock_buys_nothing"]),
    mutation("D1f", "r1", "internal_pc_open_pack without _assert_no_service_subject", MAIN, "internal_pc_open_pack",
             "    await _assert_no_service_subject(db, affected_player_ids=[player.id], "
             "affected_steam_ids=[player.steam_id])\n",
             "    pass   # mutation D1f: no service check on the bot's door\n",
             PACK, ["test_d1_a_service_account_opens_nothing"]),
    mutation("D2a", "r1", "internal_pc_open_pack refuses every purchase", MAIN, "internal_pc_open_pack",
             "    elif not nonce or pay not in _pc.PACK_PAY:\n",
             "    elif True:   # mutation D2a: the bot's door takes no purchase\n",
             PACK, ["test_d2_a_gold_purchase_debits_the_price_as_a_delta_and_writes_the_ledger_row",
                    "test_d2_a_shards_purchase_debits_the_shards_and_no_gold"]),
    mutation("D2b", "r1", "_pc_open_for requires expected_price again (the mod's predicate)", MAIN, "_pc_open_for",
             '    if source == "bought" and expected_price is not None and int(expected_price) != price:\n',
             '    if source == "bought" and int(expected_price) != price:   # mutation D2b: the mod\'s predicate\n',
             PACK, ["test_d2_a_gold_purchase_debits_the_price_as_a_delta_and_writes_the_ledger_row"]),
    mutation("D2c", "r1", "cmd_pc_buypack without the in-flight guard", BOT, "cmd_pc_buypack",
             "    if me in _pc_buying:\n",
             "    if False:   # mutation D2c: no in-flight guard\n",
             PACK, ["test_d2_a_buypack_while_one_is_in_flight_buys_nothing_and_the_guard_always_clears"]),
    mutation("D2d", "r1", "a held pack silently takes a purchase's fields", MAIN, "internal_pc_open_pack",
             "        if nonce or pay or expected_price is not None:\n",
             "        if False:   # mutation D2d: a held pack takes a purchase's fields silently\n",
             PACK, ["test_d2_the_route_takes_a_held_pack_or_a_purchase_and_nothing_else"]),
    mutation("D2e", "r1", "an incomplete purchase reaches the open", MAIN, "internal_pc_open_pack",
             "    elif not nonce or pay not in _pc.PACK_PAY:\n",
             "    elif False:   # mutation D2e: an incomplete purchase reaches the open\n",
             PACK, ["test_d2_the_route_takes_a_held_pack_or_a_purchase_and_nothing_else"]),
    mutation("D2f", "r1 re-anchored", "an unconfirmed purchase gets a daily's line", BOT, "_pc_buy_and_show",
             "        await ctx.send(_PC_BUY_UNCONFIRMED)\n",
             "        await ctx.send(_pc_open_refusal(ctx, status, body))   # mutation D2f: a daily's line\n",
             # Re-anchored with its test: round 1's lost-answer test now gets its answer on the
             # second send, and the purchase that stays unconfirmed is M1's journal test.
             PACK, ["test_m1_a_purchase_left_unconfirmed_is_completed_by_the_next_buypack_and_never_bought_twice"]),
    mutation("D3a", "r1", "the drain's face as a loose attachment (embed None)", BOT, "poll_pc_events",
             '                    embed = discord.Embed(color=_PC_RARITY_COLOR.get(str(p.get("rarity") or ""), '
             '0x95A5A6))\n',
             "                    embed = None   # mutation D3a: the face goes as a loose attachment again\n",
             PULL, ["test_d3_the_face_rides_inside_an_embed_and_the_line_stays_the_text"]),
    mutation("D3b", "r1", "_pc_send_face never logs the receipt", BOT, "_pc_send_face",
             "        if receipt:\n",
             "        if False:   # mutation D3b: Discord's answer discarded again\n",
             PULL, ["test_d3_the_drain_logs_what_discord_stored_for_the_post"]),
    mutation("D3c", "r1", "a bodyless 200 is not retried", BOT, "poll_pc_events",
             "                    elif face is None:\n",
             "                    elif False:   # mutation D3c: a bodyless 200 posts the line text-only at once again\n",
             PULL, ["test_d3_a_200_whose_body_is_refused_is_retried_and_not_posted_text_only"]),
    mutation("D3d", "r1", "the short-body refusal is silent", BOT, "_pc_api_bytes",
             '                print(f"{where} with {len(short.partial)} of its {declared} bytes: body refused")\n',
             "                pass   # mutation D3d: the short-body refusal is silent again\n",
             # Round 1's killer too: the retry row asserts that line (the byte-reader table
             # has no short-body case).
             PULL, ["test_d3_a_200_whose_body_is_refused_is_retried_and_not_posted_text_only"]),
    mutation("D3e", "r1", "the no-Content-Length refusal is silent", BOT, "_pc_api_bytes",
             '                print(f"{where} without a Content-Length: body refused")\n',
             "                pass   # mutation D3e: a 200 without a Content-Length is refused silently again\n",
             PULL, ["test_d3_the_byte_reader_names_every_200_it_refuses"]),
    mutation("D3f", "r1", "the out-of-bounds refusal is silent", BOT, "_pc_api_bytes",
             '                print(f"{where} declaring {declared} bytes, outside 1..{max_bytes}: body refused")\n',
             "                pass   # mutation D3f: a declared size outside the bounds is refused silently again\n",
             PULL, ["test_d3_the_byte_reader_names_every_200_it_refuses"]),
    mutation("D3g", "r1", "the longer-body refusal is silent", BOT, "_pc_api_bytes",
             '                print(f"{where} longer than its {declared} bytes: body refused")\n',
             "                pass   # mutation D3g: a body longer than declared is refused silently again\n",
             PULL, ["test_d3_the_byte_reader_names_every_200_it_refuses"]),
    # -- round 2: M1, server ------------------------------------------------------------------------
    mutation("M1s-a", "r2", "a failure after the commit fails the answer again", MAIN, "_pc_open_for",
             '        print(f"[PC-OPEN] player={steam_id} pack={this_pack}: answered as built before the commit; the "\n',
             "        raise   # mutation M1s-a: a failure after the commit fails the answer\n"
             '        print(f"[PC-OPEN] player={steam_id} pack={this_pack}: answered as built before the commit; the "\n',
             PACK, ["test_m1_a_failure_after_the_purchase_committed_still_answers_the_pack_and_the_charge"]),
    mutation("M1s-b", "r2", "the answer is no longer built inside the purchase's transaction", MAIN, "_pc_open_for",
             "    answer = await _pc_pack_answer(db, row, ctx)\n",
             "    answer = None   # mutation M1s-b: nothing built before the commit\n",
             # The test that pins the answer built before the commit: a failure after the
             # commit must still answer the pack and the charge. (The in-transaction test
             # breaks the subject read, which this mutation leaves inside the transaction.)
             PACK, ["test_m1_a_failure_after_the_purchase_committed_still_answers_the_pack_and_the_charge"]),
    mutation("M1s-c", "r2", "a committed row's answer fails with its face keys", MAIN, "_pc_committed_answer",
             "        await db.rollback()\n        return await _pc_pack_answer(db, row, None)\n",
             "        raise   # mutation M1s-c: no answer without face keys\n",
             PACK, ["test_m1_the_mods_result_route_answers_the_recorded_purchase_when_its_face_keys_fail",
                    "test_m1_a_replayed_held_pack_open_answers_the_recorded_pack_when_its_face_keys_fail",
                    "test_m1_an_earned_pack_voided_at_open_answers_410_with_its_row_when_its_face_keys_fail"]),
    # -- round 2: M1, bot ---------------------------------------------------------------------------
    mutation("M1b-a", "r2", "a settled purchase is never taken out of the journal", BOT, "_pc_buy_and_show",
             '    if now is not None and (now.get(me) or {}).get("nonce") == key["nonce"]:\n',
             "    if False:   # mutation M1b-a: the journal keeps a settled nonce\n",
             PACK, ["test_m1_a_refused_purchase_is_settled_and_the_next_buypack_draws_a_fresh_nonce"]),
    mutation("M1b-b", "r2", "a pending purchase is ignored: a fresh nonce every time (round 1)", BOT,
             "_pc_buy_and_show",
             "    held = pending.get(me)\n",
             "    held = None   # mutation M1b-b: a fresh nonce even with one pending\n",
             PACK, ["test_m1_a_purchase_left_unconfirmed_is_completed_by_the_next_buypack_and_never_bought_twice",
                    "test_m1_a_purchase_left_unconfirmed_outlasts_a_restart_of_the_bot"]),
    mutation("M1b-c", "r2", "a 5xx settles the key as a refusal", BOT, "_pc_open_verdict",
             '    if err == "in_progress":\n',
             '    if status >= 500:\n        return "refused"   # mutation M1b-c: a 5xx settles the key\n'
             '    if err == "in_progress":\n',
             PACK, ["test_m1_each_answer_is_read_as_opened_refused_or_unconfirmed",
                    "test_m1_a_purchase_answered_500_after_its_commit_is_replayed_with_the_same_nonce_and_charged_once"]),
    mutation("M1b-d", "r2", "the nonce is sent before it is journalled", BOT, "_pc_buy_and_show",
             "        if not _pc_buy_pending_write({**pending, me: dict(key)}):\n",
             "        if False:   # mutation M1b-d: no write-ahead\n",
             PACK, ["test_m1_the_nonce_is_in_the_journal_before_the_purchase_is_sent",
                    "test_m1_a_journal_that_cannot_hold_the_nonce_buys_nothing"]),
    mutation("M1b-e", "r2", "a journal outside a mounted volume is accepted", BOT, "_pc_buy_pending_write",
             "    if not os.path.ismount(folder):\n",
             "    if False:   # mutation M1b-e: the container's own layer passes for durable\n",
             PACK, ["test_m1_a_journal_that_cannot_hold_the_nonce_buys_nothing"]),
    # -- round 2: L1 --------------------------------------------------------------------------------
    mutation("L1a", "r2", "a face 404 posts the line text-only again", BOT, "poll_pc_events",
             "                        gone = st == 404\n",
             "                        gone = False   # mutation L1a: a 404 is not the print gone\n",
             PULL, ["test_l1_a_face_404_posts_nothing_acks_nothing_and_releases_the_lease",
                    "test_l1_a_face_404_skips_only_its_own_group_and_the_groups_behind_it_still_post"]),
    mutation("L1b", "r2", "a face 404 keeps its lease", BOT, "poll_pc_events",
             "                    await _pc_lease_release(lease[0])\n"
             '                    print(f"[PC-EVENTS] face for {ids} answered HTTP 404 (the print is gone) - nothing posted,"\n',
             "                    pass   # mutation L1b: the lease is kept\n"
             '                    print(f"[PC-EVENTS] face for {ids} answered HTTP 404 (the print is gone) - nothing posted,"\n',
             PULL, ["test_l1_a_face_404_posts_nothing_acks_nothing_and_releases_the_lease"]),
    # -- round 2: board row 32 ----------------------------------------------------------------------
    mutation("R32-a", "r2", "the availability check goes out with no start time at 8 votes", BOT,
             "poll_tournament_notices",
             '                    if tally["votes"] < tally["min_players"]:\n',
             "                    if False:   # mutation R32-a: no hold\n",
             RULE, ["test_row32_c_no_dm_while_no_time_has_8_votes_then_the_same_notices_go_out_naming_it"]),
    mutation("R32-b", "r2", "the availability check names no time", BOT, "poll_tournament_notices",
             '                    content = ("Are you still available to play in the **Synchronized tournament** at "\n'
             "                               f\"{_tsync_times(tally['slots'])}?\")\n",
             '                    content = "Are you still available to play in the **Synchronized tournament**?"\n',
             RULE, ["test_row32_c_the_dm_names_the_time_it_asks_about_and_states_the_rule",
                    "test_row32_c_tied_times_at_8_are_both_named"]),
    mutation("R32-c", "r2", "a notice whose tournament left voting is sent anyway", BOT, "poll_tournament_notices",
             '                    if tally["tournament_id"] != str(tid) or tally["status"] != "voting":\n',
             "                    if False:   # mutation R32-c: no drop\n",
             RULE, ["test_row32_c_a_notice_whose_tournament_left_voting_is_dropped_unsent"]),
    mutation("R32-d", "r2", "the signups-open post reads no tally", BOT, "poll_tournaments",
             "                await _announce_in_channel(_tsync_signups_open_text(t, await _tsync_tally_for(t)))\n",
             "                await _announce_in_channel(_tsync_signups_open_text(t, None))   # mutation R32-d\n",
             RULE, ["test_row32_a_the_signups_open_post_states_the_rule_the_tally_and_how_to_vote",
                    "test_row32_a_a_tournament_nobody_has_joined_says_nobody_agrees_yet"]),
    mutation("R32-e", "r2", "the board reads no tally", BOT, "_publish_tournament_board",
             "    sync_tally = (await _tsync_tally_for(sync_t)\n"
             '                  if sync_t is not None and sync_t.get("status") == "voting" else None)\n',
             "    sync_tally = None   # mutation R32-e\n",
             RULE, ["test_row32_b_the_board_states_the_rule_the_tally_and_how_to_vote",
                    "test_row32_b_tied_times_are_named_together"]),
    mutation("R32-f", "r2", "the tournaments FAQ answer loses its live tally", BOT, "FAQ_ENTRIES",
             '        "handler": _faq_tournaments,\n',
             "",
             RULE, ["test_row32_d_the_faq_answer_carries_the_live_tally_in_discord"]),
    mutation("R32-g", "r2", "the rule is stated without how far the vote has got", BOT, "_tsync_rule",
             '    return f"{rule}: {_tsync_progress(tally)}." if tally is not None else f"{rule}."\n',
             '    return f"{rule}."   # mutation R32-g\n',
             RULE, ["test_row32_a_the_signups_open_post_states_the_rule_the_tally_and_how_to_vote",
                    "test_row32_b_the_board_states_the_rule_the_tally_and_how_to_vote",
                    "test_row32_c_the_dm_names_the_time_it_asks_about_and_states_the_rule",
                    "test_row32_d_the_faq_answer_carries_the_live_tally_in_discord"]),
    # -- round 2: the release discriminators --------------------------------------------------------
    mutation("X1", "r2", "discord_fix does not ask whether the route is bound", MAIN, "_discord_fix_probe",
             "    if not _DISCORD_FIX_PROBE or not _discord_fix_bound():\n",
             "    if not _DISCORD_FIX_PROBE:   # mutation X1\n",
             MARK, ["test_the_route_half_unbound_reads_0_and_its_control_reads_1"]),
    mutation("X2", "r2", "discord_fix answers 1 without running the probe", MAIN, "_discord_fix_probe",
             "        await db.execute(text(_DISCORD_FIX_PROBE), dict(_DISCORD_FIX_BINDS))\n",
             "        pass   # mutation X2\n",
             MARK, ["test_the_marker_reads_1_on_this_build_on_both_arms",
                    "test_the_schema_half_a_missing_column_or_table_reads_0_and_rolls_back",
                    "test_pg_the_probe_reads_0_while_what_it_names_is_missing_and_1_once_mended"]),
    mutation("X3", "r2", "the degraded arm answers 1 whatever the last probe said", MAIN, "health_check",
             "                              discord_fix=_DISCORD_FIX_LAST)\n",
             "                              discord_fix=1)   # mutation X3\n",
             MARK, ["test_the_marker_reads_1_on_this_build_on_both_arms"]),
    mutation("X4", "r2", "discord_fix reads every probe error as a schema answer", MAIN, "_discord_fix_probe",
             "        if not _discord_fix_schema_missing(exc):\n            raise\n",
             "",
             MARK, ["test_any_other_probe_error_is_a_database_fault_not_a_schema_answer"]),
    mutation("X5", "r2", "on_ready no longer prints the bot's witness", BOT, "on_ready",
             "    print(_pc_fix_ready_line())\n",
             "",
             MARK, ["test_on_ready_prints_the_witness_just_before_bot_ready"]),
    mutation("X6", "r2", "the witness says mounted whatever the volume", BOT, "_pc_fix_ready_line",
             "        mounted = os.path.ismount(os.path.dirname(_PC_BUY_PENDING_FILE))\n",
             "        mounted = True   # mutation X6\n",
             MARK, ["test_the_witness_says_not_mounted_when_the_volume_is_missing"]),
    mutation("X7", "r2", "a witness that cannot be built raises out of on_ready", BOT, "_pc_fix_ready_line",
             "    except Exception as ex:\n",
             "    except ZeroDivisionError as ex:   # mutation X7\n",
             MARK, ["test_the_witness_never_raises_it_says_it_failed"]),
    mutation("X8", "r2", "the probe is taken from the first of several pack reads", MAIN, "_discord_fix_read",
             "    return found[0] if len(found) == 1 else \"\"\n",
             "    return found[0] if found else \"\"   # mutation X8\n",
             MARK, ["test_the_probe_is_the_replay_read_the_open_path_runs"]),
    mutation("X9", "r2", "a schema error raised from the driver's error is not read", MAIN,
             "_discord_fix_schema_missing",
             "        todo.extend((getattr(cur, \"orig\", None), cur.__cause__))\n",
             "        todo.extend((getattr(cur, \"orig\", None),))   # mutation X9\n",
             MARK, ["test_the_schema_half_a_missing_column_or_table_reads_0_and_rolls_back"]),
]


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(tree, *args):
    return subprocess.run(["git", "-C", str(tree), *args], capture_output=True, text=True, timeout=120).stdout


def span(text, name):
    """(start, end) character offsets of the top-level def or assignment `name` in LF text."""
    offs = [0]
    for line in text.split("\n"):
        offs.append(offs[-1] + len(line) + 1)
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            return offs[first - 1], offs[node.end_lineno]
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                return offs[node.lineno - 1], offs[node.end_lineno]
    raise LookupError(f"no top-level {name}")


def mutant_bytes(raw, m):
    """The file's bytes with the mutation applied: its anchor must occur exactly
    once inside its span, and the result must parse. Line endings kept."""
    text = raw.decode("utf-8")
    crlf = "\r\n" in text
    norm = text.replace("\r\n", "\n")
    s, e = span(norm, m["span"])
    n = norm[s:e].count(m["old"])
    if n != 1:
        raise ValueError(f"{m['id']}: anchor occurs {n} times inside {m['span']}, expected 1")
    norm = norm[:s] + norm[s:e].replace(m["old"], m["new"], 1) + norm[e:]
    ast.parse(norm)
    return (norm.replace("\n", "\r\n") if crlf else norm).encode("utf-8")


def run_tests(tree, target, tag, jdir):
    """pytest over one test file in the tree: (outcomes {name: outcome}, summary lines)."""
    junit = Path(jdir) / f"{tag}.xml"
    proc = subprocess.run([sys.executable, "-m", "pytest", target, "-q", "-rfE", "-p", "no:cacheprovider",
                           f"--junitxml={junit}"], cwd=str(tree), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=3600)
    outcomes = {}
    if junit.exists():
        for tc in ET.parse(junit).getroot().iter("testcase"):
            kinds = {child.tag for child in tc}
            outcome = ("failed" if "failure" in kinds else "error" if "error" in kinds
                       else "skipped" if "skipped" in kinds else "passed")
            outcomes[tc.get("name")] = outcome
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(("FAILED ", "ERROR "))]
    tail = [ln for ln in proc.stdout.splitlines() if ln.strip()][-1:] or ["(no output)"]
    return outcomes, lines + tail


def counts(outcomes):
    out = {}
    for o in outcomes.values():
        out[o] = out.get(o, 0) + 1
    return ", ".join(f"{k} {out[k]}" for k in sorted(out)) or "no tests"


def reddened(outcomes, name):
    return any(o in ("failed", "error") and (t == name or t.startswith(name + "["))
               for t, o in outcomes.items())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--only", nargs="*", default=None, help="mutation ids (a partial run says so in the log)")
    args = ap.parse_args()
    tree = Path(args.tree).resolve()
    chosen = [m for m in MUTATIONS if args.only is None or m["id"] in args.only]
    log = open(args.log, "a", encoding="utf-8", newline="\n")

    def w(line=""):
        text = "".join(ch if ord(ch) < 128 else "?" for ch in line)
        print(text)
        log.write(text + "\n")
        log.flush()

    me = Path(__file__).read_bytes()
    w(f"=== discord-fix round 2 mutation campaign, start {now()}")
    w(f"=== runner sha256 {sha(me)}")
    w(f"=== tree <tree> at {git(tree, 'rev-parse', 'HEAD').strip()}")
    w(f"=== python {sys.version.split()[0]}; mutations chosen {len(chosen)} of {len(MUTATIONS)}"
      + ("" if args.only is None else " (a PARTIAL run: --only)"))
    for g in GATES:
        v = os.environ.get(g)
        w(f"=== gate {g} = {'database ' + v.rsplit('/', 1)[-1] if v else 'NOT SET'}")
    fonts = sorted(p.name for p in (tree / "backend/api/assets/fonts").glob("*") if p.suffix in (".ttf", ".otf"))
    w(f"=== font binaries present {len(fonts)}")
    start = git(tree, "status", "--porcelain")
    w(f"=== porcelain before anything: {start.strip()!r}")
    if start.strip():
        w("=== CAMPAIGN REFUSED: the tree is not clean")
        return 2
    # Every anchor, before any test runs.
    bad = []
    for m in chosen:
        try:
            mutant_bytes((tree / m["path"]).read_bytes(), m)
        except Exception as ex:
            bad.append(f"{m['id']}: {type(ex).__name__}: {ex}")
    w(f"=== anchors checked {len(chosen)}, unresolved {len(bad)}")
    for b in bad:
        w(f"    {b}")
    if bad:
        w("=== CAMPAIGN REFUSED: an anchor does not resolve exactly once")
        return 2
    jdir = tempfile.mkdtemp(prefix="dfr2-mut-")
    # The controls: every target file, unmutated, must pass whole.
    ok_controls = 0
    targets = sorted({m["target"] for m in chosen})
    for t in targets:
        outcomes, lines = run_tests(tree, t, "control-" + Path(t).stem, jdir)
        good = bool(outcomes) and all(o in ("passed", "skipped") for o in outcomes.values()) and \
            any(o == "passed" for o in outcomes.values())
        ok_controls += good
        digest = sha("\n".join(f"{k} {outcomes[k]}" for k in sorted(outcomes)).encode())
        w(f"--- control {t}: {counts(outcomes)}; sorted outcomes sha256 {digest}; {'PASS' if good else 'FAIL'}")
        for ln in lines:
            w(f"    {ln}")
    if ok_controls != len(targets):
        w(f"=== CAMPAIGN FAILED: {len(targets) - ok_controls} control run(s) did not pass whole")
        return 1
    n_equal = n_clean = n_caught = 0
    for m in chosen:
        path = tree / m["path"]
        pre = path.read_bytes()
        mutated = mutant_bytes(pre, m)
        w(f"--- {m['id']} ({m['round']}): {m['what']}  [{m['path']} :: {m['span']}]  {now()}")
        try:
            path.write_bytes(mutated)
            outcomes, lines = run_tests(tree, m["target"], m["id"], jdir)
        finally:
            path.write_bytes(pre)
        restored = path.read_bytes()
        porcelain = git(tree, "status", "--porcelain")
        equal = sha(restored) == sha(pre)
        clean = not porcelain.strip()
        missing = [r for r in m["red"] if not reddened(outcomes, r)]
        caught = bool(m["red"]) and not missing
        n_equal += equal
        n_clean += clean
        n_caught += caught
        w(f"    pre-image sha256 {sha(pre)}")
        w(f"    mutated   sha256 {sha(mutated)}")
        w(f"    restored  sha256 {sha(restored)}  equal to the pre-image: {'yes' if equal else 'NO'}")
        w(f"    porcelain after the restore: {porcelain.strip()!r}  clean: {'yes' if clean else 'NO'}")
        w(f"    {m['target']}: {counts(outcomes)}")
        for ln in lines:
            w(f"    {ln}")
        w(f"    named red {len(m['red'])}, red {len(m['red']) - len(missing)}: {'CAUGHT' if caught else 'NOT CAUGHT'}"
          + (f"; still green: {missing}" if missing else ""))
        if not (equal and clean):
            w(f"=== CAMPAIGN FAILED at {m['id']}: a restore was unequal or the status dirty; nothing further runs")
            return 1
    verdict = n_equal == n_clean == n_caught == len(chosen)
    w(f"=== SUMMARY {now()}: {len(chosen)} mutations, {n_equal} restores equal, {n_clean} statuses clean, "
      f"{n_caught} caught (every named test red); controls {ok_controls} of {len(targets)} passed whole; "
      f"{'CAMPAIGN PASSED' if verdict else 'CAMPAIGN FAILED'}")
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
