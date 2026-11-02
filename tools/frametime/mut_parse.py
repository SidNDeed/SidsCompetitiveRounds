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
FIXTURES = ["tools/frametime/ft_parse.py", "tools/frametime/test_ft_parse.py", "plugin/CombatEvidence.cs"]
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
    ("D_up without its largest-value floor", 'return max(m + t_q(z, j - 1) * se, max(ds)), ds, rate',
     'return m + t_q(z, j - 1) * se, ds, rate'),
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
for k, (name, a, b) in enumerate(MUTS, 1):
    kills = KILLS.get(name, [])
    d = os.path.join(OUT, "mut-%d" % k)
    os.makedirs(d, exist_ok=False)
    td = make_copy(d)
    if a is not None:
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
