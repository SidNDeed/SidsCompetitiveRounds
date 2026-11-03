# mut_parse.py: the parser mutants, each must turn test_ft_parse.py red (negative controls for the port tests).
# Usage: python -I -B mut_parse.py <worktree> <outdir>; writes outdir/mut-<k>/ and runs pytest in each.
# Uncontaminated by construction (round-1 MEDIUM, mut_parse.py:64): every copy mirrors the worktree layout for each
# file the suite reads (FIXTURES), mutant 0 is the unchanged copy and must be GREEN before any mutant counts, and a
# mutant counts as red only when its failures are assertion failures that include the tests named in its row (KILLS),
# never a collection error or a missing file.
import os
import re
import shutil
import subprocess
import sys

W, OUT = sys.argv[1], sys.argv[2]
src = os.path.join(W, "tools", "frametime")
# every file test_ft_parse.py reads, as worktree-relative paths; the copy keeps the same relative layout
FIXTURES = ["tools/frametime/ft_parse.py", "tools/frametime/test_ft_parse.py", "tools/frametime/gate_specs/entries.py",
            "tools/frametime/gate_specs/a3.py", "tools/frametime/SURVIVORS.md", "plugin/FtA3.cs",
            "plugin/CombatEvidence.cs", "plugin/SeatEvidence.cs", "plugin/IdentityClockEvidence.cs",
            "plugin/HitEvidence.cs", "plugin/PoisonSync.cs", "plugin/CardDrawEvidence.cs", "plugin/PeerBuild.cs"]
# round 4: test_every_emitted_kind_is_read_or_named reads the plugin sources; the copy carries every one that writes a
# FrameTime line (a source without the literal adds no kind, so the emitted set is the worktree's)
FIXTURES += sorted("plugin/" + f for f in os.listdir(os.path.join(W, "plugin"))
                   if f.endswith(".cs") and "plugin/" + f not in FIXTURES
                   and "[FRAME-TIME]" in open(os.path.join(W, "plugin", f), encoding="utf-8").read())
# A mutant row is (name, anchor, replacement) on ft_parse.py, or (name, anchor, replacement, fixture) on that fixture
# (its repo-relative path, one of FIXTURES): the inventory controls of ruling FRAME-TIME-ROUND-R1-A1 part 3.
MUTS = [
    ("F18 accepts a replay that did not settle", 'elif r.get("result") != "settled":', 'elif False:'),
    ("VR6 ignores a disarm", 'bad.append("disarmed: " + "; ".join(dis))', 'pass'),
    ("VR6 refused-and-sent check dropped", 'for r in sorted(refused_routes & sent_routes):', 'for r in []:'),
    ("B3 ignores heavy calls with combat live", 'ops[r["op"]] = (a + r["at_call"], e + r["edge"], o + r["off"], lv + r["live"])',
     'ops[r["op"]] = (a, e + r["edge"], o + r["off"], lv + r["live"])'),
    ("B3 overlap test inverted", 'hit = [q[2] for q in pts if a < q[1] and q[0] < b]',
     'hit = [q[2] for q in pts if a > q[1] or q[0] > b]'),
    ("dispersion floor dropped", "return max(1.0, nu * phi_hat(ks, ns) / chi2_quantile(CHI_Q, nu))",
     "return nu * phi_hat(ks, ns) / chi2_quantile(CHI_Q, nu)"),
    ("FAIL on K_ON_max", "fail = rate_lb(on_min, n_on) - rate_ub(off_max, n_off) > 0",
     "fail = rate_lb(on_max, n_on) - rate_ub(off_max, n_off) > 0"),
    ("contrast point-weighted", None, None),
    ("e_C unit without f_hat", 'unit = cp[0] * fh[g] / 1e6', 'unit = cp[0]'),
    ("planted windows counted in B2", 'return r["arm"] if r.get("plant", 0) == 0 else None', 'return r["arm"]'),
    ("VR7 sides swapped off", 'return "ON" if r.get("plant", 0) else "OFF"', 'return r["arm"]'),
    ("K_up without its half-width", "return est, hw, est + hw", "return est, hw, est"),
    ("VR5 point zero dropped", 'if r["kind"] == "p" and "span_g" in r:', 'if False:'),
    ("D_up without its largest-value floor", 'return max(m + t_q(z, j - 1) * se, max(ds)), ds, rate\n',
     'return m + t_q(z, j - 1) * se, ds, rate\n'),
    ("cal kind overwrites the line kind", '            k = "ckind"', '            k = "kind"'),
    ("zero-state voids only the failing point",
     'return set((r["game"], r["round"]) for r in recs if r["kind"] == "p" and r.get("zs", 0) != 0)',
     'return set()'),
    ("menu A/A one-sided", "aa_ok = est - hw <= 0 <= est + hw", "aa_ok = est - hw <= 0"),
    ("menu e_C without f_hat", 'ec = (p["psC"] / p["pn"] - p["sC"] / p["n"]) / (cp * m["f_hat"] / 1e6)',
     'ec = (p["psC"] / p["pn"] - p["sC"] / p["n"]) / cp'),
    ("no_cycle_counter: VR2 ignores cycle failures",
     'for k in ("missing_end", "cycle_failures", "span_depth_violations"):\n            if r.get(k, 0) != 0:',
     'for k in ("missing_end", "span_depth_violations"):\n            if r.get(k, 0) != 0:'),
    ("menu run completion ignored", 'if d.get("why") != "complete" or d.get("segs") != d.get("of"):', 'if False:'),
    ("sitting completion line ignored", 'if len(done) != 1:\n        miss.append(', 'if False:\n        miss.append('),
    ("sitting games not required", "        gone = sorted(want - have)\n", "        gone = []\n"),
    ("VR5 missing census passes", 'gone = sorted(e for e in exp if e not in seen)', 'gone = []'),
    ("VR5 opened line not required", 'bad.append("g=%d: %d opened lines (needs 1)" % (g, len(op)))', 'pass'),
    ("VR5 collector opening ignored", 'shut = [c for c in OPENED if op[0].get(c) != 1]', 'shut = []'),
    ("D_up pooled rate", 'rate[k] = max(rate.get(k, 0.0), r["on"] / on_frames[r["g"]])',
     'rate[k] = rate.get(k, 0.0) + r["on"] / sum(on_frames.values())'),
    ("VR2 calibration coverage dropped", 'gone = sorted(shapes - got)', 'gone = []'),
    ("VR2 one run per game not required", 'bad.append("game %d: %d calibration runs (needs 1)" % (g, len(runs)))\n            continue',
     'continue'),
    ("B1 not guarded by VR6", '"B1": ("VR1", "VR2", "VR3", "VR4", "VR5", "VR6", "VR8", "VR9", "F18")',
     '"B1": ("VR1", "VR2", "VR3", "VR4", "VR5", "VR8", "VR9", "F18")'),
    ("B2 not guarded by VR7", '"B2": ("VR7",)', '"B2": ()'),
    ("B3 not guarded by VR6", '"B3": ("VR5", "VR6")', '"B3": ("VR5",)'),
    ("verdicts given on an incomplete sitting", 'if miss:\n            return "withheld: sitting incomplete"', 'if False:\n            pass'),
    ("SID band dropped", 'if u <= 0.05 * tref:\n        return "SID"', 'if False:\n        return "SID"'),
    ("menu e_C band upper end dropped", 'if not (lo_b <= m_ - h_ and m_ + h_ <= hi_b):', 'if not (lo_b <= m_ - h_):'),
    ("menu e_C nearness dropped", 'if abs(m_ - 1.0) > MENU_EC_NEAR:', 'if False:'),
    ("B3 ignores edge calls", 'for op, v in sorted(ops.items()) if v[1] > 0]', 'for op, v in sorted(ops.items()) if False]'),
    ("A3 left out of U", "u = lead + ku + du + a3v", "u = lead + ku + du"),
    ("A3 per-game maximum replaced by the last game", 'rate[k] = max(rate.get(k, 0.0), rows[0]["reads_win"] / on_frames[g])',
     'rate[k] = rows[0]["reads_win"] / on_frames[g]'),
    ("A3 missing line passes", 'raise Refused("A3 structure %s: game %d has %d a3 lines (needs 1)" % (k, g, len(rows)))',
     'continue'),
    ("A3 missing calibration passes", 'raise Refused("calibration %d has no a3 line for %s" % (i, miss))', 'continue'),
    ("VR6 dispatch count ignored", 'if disp.get(r, 0) != sent.get(r, 0):', 'if False:'),
    ("A3 drained missing line passes",
     'raise Refused("A3 drained structure %s: game %d has %d a3drain lines (needs 1)" % (k, g, len(rows)))', 'continue'),
    ("A3 drained nonempty passes",
     'if r.get("starts", 0) <= 0 or r.get("nonempty", -1) != 0 or r.get("faults", -1) != 0:',
     'if r.get("starts", 0) <= 0 or r.get("faults", -1) != 0:'),
    ("A3 inventory row removed", '    ("CE_Recent", "S06", "dependent", "", "live:executed"),', '',
     "tools/frametime/gate_specs/a3.py"),
    ("A3 dependent row demoted to zero", '    ("CE_Pos", "S05", "dependent", "", "live:executed"),',
     '    ("CE_Pos", "S05", "zero", "demoted", "sweep:no-live-write"),', "tools/frametime/gate_specs/a3.py"),
    ("A3 zero row with its proof reference removed", '    ("CE_Pos", "S05", "dependent", "", "live:executed"),',
     '    ("CE_Pos", "S05", "zero", "demoted", ""),', "tools/frametime/gate_specs/a3.py"),
    ("A3 capacity typed", 'FtA3.Set(FtA3.CE_Ping, "CE_Ping", PING_BIN_CAP,', 'FtA3.Set(FtA3.CE_Ping, "CE_Ping", 2000,',
     "plugin/CombatEvidence.cs"),
    ("A3 row not registered", 'FtA3.SetDrained(FtA3.PE_Rec, "PE_Rec", () => _recCount);', '',
     "plugin/PoisonSync.cs"),
    # ruling FRAME-TIME-ROUND-R2: the kind rule, H4 and its absent-record class, the MEDIUMs' parser halves
    ("A3 per-game calibration rule removed (the old acceptance)", "    if calc:\n        cal_games = {}",
     "    if False:\n        cal_games = {}"),
    ("A3 zero row without its proof passes", r'if kind == "zero" and not re.fullmatch(r"(sweep|probe):\S+", proof):',
     "if False:"),
    ("A3 drained row without its probe passes", 'if kind == "drained" and proof != "probe:a3drain":', "if False:"),
    ("A3 drained starts not matched to the points", 'if r.get("starts", -1) != npts:', "if False:"),
    ("absent-record sweep left out of complete()", "    miss += records_missing(recs, last_game)", "    pass"),
    ("absent flushed line passes", 'miss.append("game %d: %d flushed lines (needs 1)" % (g, n))', "pass"),
    ("absent between line passes",
     'miss.append("game %d: %d between lines for %d points (needs %d)" % (g, n, len(pts), len(pts) - 1))', "pass"),
    ("absent heavy line passes the sweep", 'miss.append("game %d: %d heavy lines for %s (needs 1)" % (g, n, op))', "pass"),
    ("absent offthread line passes the sweep", 'miss.append("game %d: %d offthread lines (needs 1)" % (g, n))', "pass"),
    ("absent window line passes",
     'miss.append("point %s: %d window lines, the point line counts %s" % (q["pt"], n, q.get("windows")))', "pass"),
    ("absent refusals line passes",
     'miss.append("no refusals line after game %d (why=game%d or why=quit)" % (last_game, last_game))', "pass"),
    ("B3 passes on an absent heavy line", 'raise Refused("B3: game %d has %d heavy lines for %s (needs 1)" % (g, n, op))',
     "pass"),
    ("B3 passes on an absent offthread line", 'raise Refused("B3: game %d has %d offthread lines (needs 1)" % (g, n))',
     "pass"),
    ("records table row removed", '    "flushed": "records_missing(): one per game",\n', ""),
    ("menu segment excluded or empty passes", 'if p.get("excl", 0) != 0 or p["n"] <= 0:', "if False:"),
    ("B2 per minute not scaled by T_ref", "return ub_per_frame * 60e6 / tr", "return ub_per_frame * 1000.0"),
    ("longest frame is the last, not the largest", 'out[r["arm"]] = max(out.get(r["arm"], 0), r["maxF"])',
     'out[r["arm"]] = r["maxF"]'),
    ("dC minus dS drops dS", 'return dC_us(recs)[0] - d_key_us(recs, "sS", "ticks")[0]', "return dC_us(recs)[0]"),
    ("menu segment without its menu line passes", "if sorted(seg) != want_segs:", "if False:"),
    ("menu point line without its menu line passes", "    if orphan:\n        bad.append(", "    if False:\n        bad.append("),
    # round 4 (ruling FRAME-TIME-ROUND-R3-A1): the proof records, the withheld rows, VR2's final counters, the replay
    # and counters sweep, F18's guard, the menu cycles and terminal snapshot, the failure events, the records table
    ('zero proof naming no evidence passes', 'if kind == "zero" and proof not in ZERO_PROOFS:', 'if False:'),
    ('proof records never checked', 'proof_records(recs, spec, last_game)', 'None'),
    ('contrary live writes for a zero row pass', 'if wr:', 'if False:'),
    ('probe:a3zero evidence not required', 'if proof == "probe:a3zero":', 'if False:'),
    ('a3zero written count not checked', ' or r.get("written", -1) != 0', ''),
    ('A3 row withheld by the build passes', 'raise Refused("A3 rows withheld by the build (no executed real reader): %s" % ", ".join(held))', 'pass'),
    ('VR2 counters values not judged', 'bad.append("counters g=%d %s=%s" % (g, k, cs[0].get(k)))', 'pass'),
    ('VR2 absent counters line passes', 'bad.append("game %d: %d counters lines (needs 1, written at its flush)" % (g, len(cs)))', 'pass'),
    ('VR2 point missing_end passes', 'bad.append("point %s: missing_end=%d" % (r["pt"], r["missing_end"]))', 'pass'),
    ('absent answer_replay passes the sweep', 'miss.append("game %d: %d answer_replay lines (reading %s needs %d)" % (g, n, "/".join(sorted(map(str, readings))), want))', 'pass'),
    ('absent counters line passes the sweep', 'miss.append("game %d: %d counters lines (needs 1)" % (g, n))', 'pass'),
    ('F18 does not guard B1', '"VR8", "VR9", "F18"), "B2"', '"VR8", "VR9"), "B2"'),
    ('menu cycle calibrations not required', 'bad.append("menu calibrations %s, menu_done counts %s cycles" % (sorted(whys), cyc))', 'pass'),
    ('menu terminal snapshot read anywhere', 'post = [r for r in recs[idone + 1:] if r["kind"] == "settled"]', 'post = sett[-1:]'),
    ('menu terminal snapshot counters not judged', 'if terminal.get(k, -1) != 0:', 'if False:'),
    ("menu run's extra settled lines pass", '        if mid:\n            bad.append(', '        if False:\n            bad.append('),
    ('failure events ignored by the sweep', 'miss = failure_events(recs)', 'miss = []'),
    ('failure events ignored by the menu check', 'bad += failure_events(recs)', 'pass'),
    ('clock installed read as a failure', '("clock", "refused:",', '("clock", None,'),
    ('records table counters row removed', '"counters": "records_missing() and vr2(): one per game, written at its flush, the three counters 0",', ''),
    ('a read kind named unread', '    "spans": "FtCensus', '    "counters": "x",\n    "spans": "FtCensus'),
    ('a deletion control removed from the table', '("counters", "sitting", _g16, INCOMPLETE),', '', 'tools/frametime/test_ft_parse.py'),
    ('the build stops writing the counters line', 'Plugin.Log.LogInfo("[FRAME-TIME] counters g="', 'Plugin.Log.LogInfo("[FRAME-TIME] Counters g="', 'plugin/FtSchedule.cs'),
    # round 5 (ruling FRAME-TIME-ROUND-R4 and R4-A1): the live rows' in-game calibration, M2's two snapshots, M3's
    # failure warnings
    ('live row marker removed: its planning value passes', '    ("CE_Pos", "S05", "dependent", "", "live:executed"),',
     '    ("CE_Pos", "S05", "dependent", "", ""),', 'tools/frametime/gate_specs/a3.py'),
    ('live row planning or withheld line beside its executed line passes',
     'elif k in live:\n            raise Refused("A3 live row %s: cal i=%s carries a %s line;',
     'elif False:\n            raise Refused("A3 live row %s: cal i=%s carries a %s line;'),
    ('live row executed reads not matched to its a3 line', 'if len(a3l) != 1 or a3l[0].get("reads_on") != r["reads"]:',
     'if len(a3l) != 1:'),
    ('live row unscoped reads or unbalanced scopes pass', 'if r["unscoped"] != 0 or r["depth_err"] != 0:', 'if False:'),
    ('live row missing game line passes',
     'raise Refused("A3 live row %s: game %d has %d executed calibration lines (needs 1)" % (k, g, len(rows)))',
     'continue'),
    ('live row line not tied to its start calibration', 'if len(run) != 1 or r["i"] not in run:', 'if False:'),
    ('live row d is the last game, not the largest', 'best = v if best is None else max(best, v)', 'best = v'),
    ('live row with no executed read passes', 'if best is None:\n            raise Refused(',
     'if False:\n            raise Refused('),
    ('live line for a calibrated row passes', 'if k in names and k not in live:', 'if False:'),
    ('peer seat live lines ignored', '    if peer_recs is not None:\n        pd, _ = a3_live(',
     '    if False:\n        pd, _ = a3_live('),
    ('peer log not required on the command line form', 'if peer_recs is None and require_peer and', 'if False and'),
    ('live rows left out of A_j', '(ld[k] if k in ld else cals[i][k]) for k in dep))',
     '(cals[i][k] if k in cals[i] else 0.0) for k in dep))'),
    ('cal failure warnings unmarked', '        rec["failed"] = 1', '        pass'),
    ('VR2 failure warnings pass', '        if fails:\n            bad.append("game %d: calibration %d carries failure warnings',
     '        if False:\n            bad.append("game %d: calibration %d carries failure warnings'),
    ('VR2 f_hat value not validated', ' and isinstance(fh[0].get("f_hat"), int) and fh[0]["f_hat"] > 0', ''),
    ('menu startup snapshot not required',
     'if len(pre) != 1 or pre[0].get("g") != -1 or pre[0].get("c_plant") != -1:', 'if False:'),
    ('menu failure warnings pass', '    if mfail:\n        bad.append(', '    if False:\n        bad.append('),
]

# the tests each mutant must turn red (taken from a --discover run on a green baseline, then pinned)
KILLS = {
    'F18 accepts a replay that did not settle':
        ['test_f18_reading_a_needs_a_settled_replay_per_game'],
    'VR6 ignores a disarm':
        ['test_vr6_build_fails_on_a_disarm'],
    'VR6 refused-and-sent check dropped':
        ['test_vr6_routes_fail_a_route_refused_and_sent'],
    'B3 ignores heavy calls with combat live':
        ['test_b3_flags_heavy_work_with_combat_live'],
    'B3 overlap test inverted':
        ['test_b3_flags_a_hashing_job_overlapping_a_point', 'test_b3_passes_with_heavy_work_between_points', 'test_report_end_to_end_reaches_a_verdict'],
    'dispersion floor dropped':
        ['test_mutant_hitch_counting_planted_windows_differs', 'test_mutant_runs_kmax_for_fail_does_not_fail_on_uncertain_only', 'test_runs_stalls_fail', 'test_vr7_stalls_in_planted_windows_fail'],
    'FAIL on K_ON_max':
        ['test_mutant_runs_kmax_for_fail_does_not_fail_on_uncertain_only'],
    'contrast point-weighted':
        ['test_frame_weight_contrast_is_ratio_of_sums', 'test_mutant_point_weighted_differs'],
    'e_C unit without f_hat':
        ['test_e_c_reads_the_plant'],
    'planted windows counted in B2':
        ['test_hitch_leaves_planted_windows_out', 'test_mutant_hitch_counting_planted_windows_differs'],
    'VR7 sides swapped off':
        ['test_report_end_to_end_reaches_a_verdict', 'test_vr7_constant_plant_passes', 'test_vr7_stalls_in_planted_windows_fail'],
    'K_up without its half-width':
        ['test_k_up_reads_upkeep_per_live_frame'],
    'VR5 point zero dropped':
        ['test_vr5_flags_gated_span_time_at_a_gated_point', 'test_vr5_flags_guarded_returns_at_an_open_point'],
    'D_up without its largest-value floor':
        ['test_d_up_dispatch_never_below_its_largest_calibration'],
    'cal kind overwrites the line kind':
        ['test_cal_line_keeps_its_line_kind', 'test_menu_check_fails_a_level_with_low_exposure', 'test_menu_check_fails_an_aa_shift_either_way', 'test_menu_check_fails_an_aborted_run_and_a_wrong_gate', 'test_menu_check_fails_fhat_spread_and_an_unstamped_frame', 'test_menu_check_passes_a_clean_run', 'test_report_end_to_end_reaches_a_verdict'],
    'zero-state voids only the failing point':
        ['test_game0_mutant_must_void_every_round', 'test_report_end_to_end_reaches_a_verdict', 'test_zero_state_reports_a_game_with_no_valid_round', 'test_zero_state_voids_the_whole_round'],
    'menu A/A one-sided':
        ['test_menu_check_fails_an_aa_shift_either_way'],
    'menu e_C without f_hat':
        ['test_menu_check_fails_a_level_with_low_exposure'],
    'no_cycle_counter: VR2 ignores cycle failures':
        ['test_vr2_flags_span_depth_and_cycle_failures'],
    'menu run completion ignored':
        ['test_menu_check_fails_an_aborted_run_and_a_wrong_gate'],
    # round 1's fixes (FRAME-TIME-ROUND-R1): each mutant's named killing test, pinned from mp-discover runs
    'sitting completion line ignored':
        ['test_verdicts_need_the_complete_sitting'],
    'sitting games not required':
        ['test_verdicts_need_the_complete_sitting'],
    'VR5 missing census passes':
        ['test_vr5_needs_every_expected_record'],
    'VR5 opened line not required':
        ['test_vr5_needs_every_expected_record'],
    'VR5 collector opening ignored':
        ['test_vr5_needs_every_expected_record'],
    'D_up pooled rate':
        ['test_d_up_uses_the_largest_per_game_on_rate_not_a_pooled_off_rate'],
    'VR2 calibration coverage dropped':
        ['test_vr2_needs_every_game_start_calibration'],
    'VR2 one run per game not required':
        ['test_vr2_needs_every_game_start_calibration'],
    'B1 not guarded by VR6':
        ['test_a_failed_rule_invalidates_the_claims_it_guards'],
    'B2 not guarded by VR7':
        ['test_a_failed_rule_invalidates_the_claims_it_guards'],
    'B3 not guarded by VR6':
        ['test_a_failed_rule_invalidates_the_claims_it_guards'],
    'verdicts given on an incomplete sitting':
        ['test_verdicts_need_the_complete_sitting'],
    'SID band dropped':
        ['test_report_carries_the_specified_figures'],
    'menu e_C band upper end dropped':
        ['test_menu_check_fails_a_tenfold_exposure'],
    'menu e_C nearness dropped':
        ['test_menu_check_fails_a_tenfold_exposure'],
    'A3 left out of U':
        ['test_report_adds_a3_to_u'],
    'A3 per-game maximum replaced by the last game':
        ['test_a3_is_the_largest_per_game_window_rate_times_the_calibrated_difference'],
    'A3 missing line passes':
        ['test_a3_refuses_a_missing_line_or_calibration'],
    'A3 missing calibration passes':
        ['test_a3_refuses_a_missing_line_or_calibration'],
    'B3 ignores edge calls':
        ['test_b3_flags_heavy_work_in_a_live_frame_after_combat_ended'],
    'VR6 dispatch count ignored':
        ['test_vr6_counts_dispatches_independently'],
    'A3 drained missing line passes':
        ['test_a3_drained_rows_refuse_a_missing_line_or_a_point_that_started_holding_entries'],
    'A3 drained nonempty passes':
        ['test_a3_drained_rows_refuse_a_missing_line_or_a_point_that_started_holding_entries'],
    'A3 inventory row removed':
        ['test_a3_inventory_names_every_survivor_once_and_the_build_registers_each_row'],
    'A3 dependent row demoted to zero':
        ['test_a3_inventory_names_every_survivor_once_and_the_build_registers_each_row'],
    'A3 capacity typed':
        ['test_a3_inventory_names_every_survivor_once_and_the_build_registers_each_row'],
    'A3 row not registered':
        ['test_a3_inventory_names_every_survivor_once_and_the_build_registers_each_row'],
    'A3 zero row with its proof reference removed':
        ['test_a3_zero_row_without_its_proof_reference_fails_the_parse'],
    'A3 per-game calibration rule removed (the old acceptance)':
        ['test_a3_every_games_calibration_is_required_and_a_dropped_one_never_passes'],
    'A3 zero row without its proof passes':
        ['test_a3_zero_row_without_its_proof_reference_fails_the_parse'],
    'A3 drained row without its probe passes':
        ['test_a3_zero_row_without_its_proof_reference_fails_the_parse'],
    'A3 drained starts not matched to the points':
        ['test_a3_drained_starts_equal_the_games_point_count'],
    'absent-record sweep left out of complete()':
        ['test_each_absent_record_fails_the_run'],
    'absent flushed line passes':
        ['test_each_absent_record_fails_the_run'],
    'absent between line passes':
        ['test_each_absent_record_fails_the_run'],
    'absent heavy line passes the sweep':
        ['test_each_absent_record_fails_the_run'],
    'absent offthread line passes the sweep':
        ['test_each_absent_record_fails_the_run'],
    'absent window line passes':
        ['test_each_absent_record_fails_the_run'],
    'absent refusals line passes':
        ['test_each_absent_record_fails_the_run'],
    'B3 passes on an absent heavy line':
        ['test_b3_requires_complete_records'],
    'B3 passes on an absent offthread line':
        ['test_b3_requires_complete_records'],
    'records table row removed':
        ['test_records_table_names_every_kind_the_parser_reads'],
    'menu segment excluded or empty passes':
        ['test_menu_check_fails_an_excluded_or_empty_segment'],
    'B2 per minute not scaled by T_ref':
        ['test_report_items_per_minute_longest_frames_and_dc_minus_ds'],
    'longest frame is the last, not the largest':
        ['test_report_items_per_minute_longest_frames_and_dc_minus_ds'],
    'dC minus dS drops dS':
        ['test_report_items_per_minute_longest_frames_and_dc_minus_ds'],
    'menu segment without its menu line passes':
        ['test_menu_check_fails_a_segment_whose_menu_line_is_absent'],
    'menu point line without its menu line passes':
        ['test_menu_check_fails_a_segment_whose_menu_line_is_absent'],
    'zero proof naming no evidence passes':
        ['test_a3_probe_proofs_need_their_records_and_contrary_ones_fail'],
    'proof records never checked':
        ['test_a3_probe_proofs_need_their_records_and_contrary_ones_fail', 'test_deleting_each_record_kind_withholds'],
    'contrary live writes for a zero row pass':
        ['test_a3_probe_proofs_need_their_records_and_contrary_ones_fail'],
    'probe:a3zero evidence not required':
        ['test_a3_probe_proofs_need_their_records_and_contrary_ones_fail', 'test_deleting_each_record_kind_withholds'],
    'a3zero written count not checked':
        ['test_a3_probe_proofs_need_their_records_and_contrary_ones_fail'],
    'A3 row withheld by the build passes':
        ['test_a3_row_withheld_by_the_build_withholds_b1'],
    'VR2 counters values not judged':
        ['test_vr2_judges_the_last_games_counters_and_every_point_stamp'],
    'VR2 absent counters line passes':
        ['test_vr2_judges_the_last_games_counters_and_every_point_stamp'],
    'VR2 point missing_end passes':
        ['test_vr2_judges_the_last_games_counters_and_every_point_stamp'],
    'absent answer_replay passes the sweep':
        ['test_each_absent_record_fails_the_run', 'test_deleting_each_record_kind_withholds'],
    'absent counters line passes the sweep':
        ['test_each_absent_record_fails_the_run', 'test_deleting_each_record_kind_withholds'],
    'F18 does not guard B1':
        ['test_f18_failure_guards_b1'],
    'menu cycle calibrations not required':
        ['test_menu_check_needs_every_cycle_calibration_and_the_terminal_snapshot', 'test_deleting_each_record_kind_withholds'],
    'menu terminal snapshot read anywhere':
        ['test_menu_check_needs_every_cycle_calibration_and_the_terminal_snapshot'],
    'menu terminal snapshot counters not judged':
        ['test_menu_check_needs_every_cycle_calibration_and_the_terminal_snapshot'],
    "menu run's extra settled lines pass":
        ['test_menu_check_needs_every_cycle_calibration_and_the_terminal_snapshot'],
    'failure events ignored by the sweep':
        ['test_failure_events_make_the_run_incomplete'],
    'failure events ignored by the menu check':
        ['test_failure_events_make_the_run_incomplete'],
    'clock installed read as a failure':
        ['test_failure_events_make_the_run_incomplete'],
    'records table counters row removed':
        ['test_records_table_names_every_kind_the_parser_reads', 'test_every_record_kind_has_a_deletion_control'],
    'a read kind named unread':
        ['test_every_emitted_kind_is_read_or_named'],
    'a deletion control removed from the table':
        ['test_every_record_kind_has_a_deletion_control'],
    'the build stops writing the counters line':
        ['test_every_emitted_kind_is_read_or_named'],
    'live row marker removed: its planning value passes':
        ['test_live_row_planning_or_withheld_line_never_passes_as_executed'],
    'live row planning or withheld line beside its executed line passes':
        ['test_live_row_planning_or_withheld_line_never_passes_as_executed'],
    'live row executed reads not matched to its a3 line':
        ['test_live_row_lines_are_complete_and_consistent'],
    'live row unscoped reads or unbalanced scopes pass':
        ['test_live_row_lines_are_complete_and_consistent'],
    'live row missing game line passes':
        ['test_live_row_lines_are_complete_and_consistent', 'test_peer_seat_live_lines_are_read_and_required'],
    'live row line not tied to its start calibration':
        ['test_live_row_lines_are_complete_and_consistent'],
    'live row d is the last game, not the largest':
        ['test_live_rows_take_their_executed_in_game_calibration'],
    'live row with no executed read passes':
        ['test_live_row_lines_are_complete_and_consistent'],
    'live line for a calibrated row passes':
        ['test_live_row_lines_are_complete_and_consistent'],
    'peer seat live lines ignored':
        ['test_peer_seat_live_lines_are_read_and_required'],
    'peer log not required on the command line form':
        ['test_peer_seat_live_lines_are_read_and_required'],
    'live rows left out of A_j':
        ['test_live_rows_take_their_executed_in_game_calibration'],
    'cal failure warnings unmarked':
        ['test_vr2_needs_a_successful_fhat_and_rejects_calibration_failures'],
    'VR2 failure warnings pass':
        ['test_vr2_needs_a_successful_fhat_and_rejects_calibration_failures'],
    'VR2 f_hat value not validated':
        ['test_vr2_needs_a_successful_fhat_and_rejects_calibration_failures'],
    'menu startup snapshot not required':
        ['test_menu_check_validates_the_startup_and_the_terminal_snapshot'],
    'menu failure warnings pass':
        ['test_menu_check_validates_the_startup_and_the_terminal_snapshot'],
}
t0 = open(os.path.join(src, "ft_parse.py"), encoding="utf-8", newline="").read()
DISCOVER = "--discover" in sys.argv[3:]
# a parametrised test's id ([...]) is part of its FAILED line: read past it, or its failures are never seen
FAILED = re.compile(r"^FAILED \S+::(\w+)(?:\[[^\]]*\])?(?: - (.*))?$")
for _ln, _want in (("FAILED test_ft_parse.py::test_x - AssertionError: y", "test_x"),
                   ("FAILED test_ft_parse.py::test_each[flushed-kw0] - AssertionError: y", "test_each"),
                   ("FAILED test_ft_parse.py::test_each[heavy-kw4]", "test_each")):
    _m = FAILED.match(_ln)
    if not _m or _m.group(1) != _want:
        sys.exit("REFUSED: the FAILED reader does not read %r" % _ln)
UNRELATED = ("FileNotFoundError", "ModuleNotFoundError", "ImportError", "No such file")


def make_copy(d):
    for rel in FIXTURES:
        p = os.path.join(d, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        shutil.copy(os.path.join(W, *rel.split("/")), p)
    return os.path.join(d, "tools", "frametime")


def run_suite(td):
    r = subprocess.run([sys.executable, "-I", "-B", "-m", "pytest", "test_ft_parse.py", "-q", "-rf", "-p", "no:cacheprovider"],
                       cwd=td, capture_output=True, text=True, timeout=1800)
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    failed = {}
    for ln in lines:
        m = FAILED.match(ln)
        if m:
            failed[m.group(1)] = m.group(2) or ""
    return r.returncode, (lines[-1] if lines else "(no output)"), failed, r.stdout


# mutant 0: the unchanged copy must be green, or no mutant below is evidence
d0 = os.path.join(OUT, "mut-0")
os.makedirs(d0, exist_ok=False)
rc0, last0, failed0, _ = run_suite(make_copy(d0))
print("baseline (unchanged copy): rc=%d %s -> %s" % (rc0, last0, "GREEN" if rc0 == 0 else "RED (baseline FAILED)"))
if rc0 != 0:
    for n, why in sorted(failed0.items()):
        print("  baseline failure: %s - %s" % (n, why))
    print("PARSER MUTANTS FAIL (no green baseline)")
    sys.exit(1)
bad = 0
jobs = []
for k, row in enumerate(MUTS, 1):
    name, a, b = row[:3]
    kills = KILLS.get(name, [])
    d = os.path.join(OUT, "mut-%d" % k)
    os.makedirs(d, exist_ok=False)
    td = make_copy(d)
    if len(row) == 4:
        if row[3] not in FIXTURES:
            sys.exit("REFUSED: mutant %d targets %s, not a fixture" % (k, row[3]))
        fp = os.path.join(d, *row[3].split("/"))
        f0 = open(fp, encoding="utf-8", newline="").read()
        if f0.count(a) != 1:
            sys.exit("REFUSED: mutant %d anchor matched %d times in %s" % (k, f0.count(a), row[3]))
        open(fp, "w", encoding="utf-8", newline="").write(f0.replace(a, b))
        t = t0
    elif a is not None:
        if t0.count(a) != 1:
            sys.exit("REFUSED: mutant %d anchor matched %d times" % (k, t0.count(a)))
        t = t0.replace(a, b)
    else:
        # replace contrast_c's body with the point-weighted mean difference
        i = t0.index("def contrast_c(points):")
        j = t0.index("\ndef ", i + 10)
        t = t0[:i] + ("def contrast_c(points):\n"
                      "    on = [p['sC'] / p['n'] for p in points if p['arm'] == 'ON' and p['n']]\n"
                      "    off = [p['sC'] / p['n'] for p in points if p['arm'] == 'OFF' and p['n']]\n"
                      "    return sum(on) / len(on) - sum(off) / len(off), sum(p['n'] for p in points)\n\n") + t0[j:]
    open(os.path.join(td, "ft_parse.py"), "w", encoding="utf-8", newline="").write(t)
    jobs.append((k, name, kills, td))
# the copies are independent directories, so their suites run side by side (--jobs N); results print in mutant order
import concurrent.futures  # noqa: E402
JOBS = int(next((x.split("=", 1)[1] for x in sys.argv[3:] if x.startswith("--jobs=")), "1"))
with concurrent.futures.ThreadPoolExecutor(max_workers=JOBS) as ex:
    results = list(ex.map(lambda j: run_suite(j[3]), jobs))
for (k, name, kills, td), (rc, last, failed, out) in zip(jobs, results):
    unrelated = sorted(n for n, why in failed.items() if any(u in why for u in UNRELATED))
    missing = sorted(set(kills) - set(failed))
    red = rc == 1 and failed and not unrelated and not missing and (kills or DISCOVER)
    why = ("RED" if red else "GREEN (control FAILED)" if rc == 0 else
           "rc=%d not a test failure (control FAILED)" % rc if rc != 1 else
           "unrelated failure %s (control FAILED)" % unrelated if unrelated else
           "named kills did not fail: %s (control FAILED)" % missing if missing else "no named kills (control FAILED)")
    print("mutant %d (%s): rc=%d %s; failed: %s -> %s" % (k, name, rc, last, " ".join(sorted(failed)), why))
    bad += 0 if red else 1
print("PARSER MUTANTS %s (%d mutants, baseline green)" % ("PASS" if bad == 0 else "FAIL", len(MUTS)))
sys.exit(0 if bad == 0 else 1)
