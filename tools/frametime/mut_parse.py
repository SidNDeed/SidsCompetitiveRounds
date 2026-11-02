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
            "plugin/HitEvidence.cs", "plugin/PoisonSync.cs"]
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
    ("B1 not guarded by VR6", '"B1": ("VR1", "VR2", "VR3", "VR4", "VR5", "VR6", "VR8", "VR9")',
     '"B1": ("VR1", "VR2", "VR3", "VR4", "VR5", "VR8", "VR9")'),
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
    ("A3 inventory row removed", '    ("CE_Recent", "S06", "dependent", ""),\n', '',
     "tools/frametime/gate_specs/a3.py"),
    ("A3 dependent row demoted to zero", '    ("CE_Pos", "S05", "dependent", ""),',
     '    ("CE_Pos", "S05", "zero", "demoted"),', "tools/frametime/gate_specs/a3.py"),
    ("A3 capacity typed", 'FtA3.Set(FtA3.CE_Ping, "CE_Ping", PING_BIN_CAP,', 'FtA3.Set(FtA3.CE_Ping, "CE_Ping", 2000,',
     "plugin/CombatEvidence.cs"),
    ("A3 row not registered", 'FtA3.SetDrained(FtA3.PE_Rec, "PE_Rec", () => _recCount);', '',
     "plugin/PoisonSync.cs"),
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
}
t0 = open(os.path.join(src, "ft_parse.py"), encoding="utf-8", newline="").read()
DISCOVER = "--discover" in sys.argv[3:]
FAILED = re.compile(r"^FAILED \S+::(\w+)(?: - (.*))?$")
UNRELATED = ("FileNotFoundError", "ModuleNotFoundError", "ImportError", "No such file")


def make_copy(d):
    for rel in FIXTURES:
        p = os.path.join(d, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        shutil.copy(os.path.join(W, *rel.split("/")), p)
    return os.path.join(d, "tools", "frametime")


def run_suite(td):
    r = subprocess.run([sys.executable, "-I", "-B", "-m", "pytest", "test_ft_parse.py", "-q", "-rf", "-p", "no:cacheprovider"],
                       cwd=td, capture_output=True, text=True, timeout=300)
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
    rc, last, failed, out = run_suite(td)
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
