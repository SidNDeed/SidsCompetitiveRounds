# mut_parse.py: the parser mutants, each must turn test_ft_parse.py red (negative controls for the port tests).
# Usage: python -I -B mut_parse.py <worktree> <outdir>; writes outdir/mut-<k>/ and runs pytest in each.
# Uncontaminated by construction (round-1 MEDIUM, mut_parse.py:64): every copy mirrors the worktree layout for each
# file the suite reads (FIXTURES), mutant 0 is the unchanged copy and must be GREEN before any mutant counts, and a
# mutant runs exactly the node ids its row names (KILLS) and counts as red only when each of them failed in its call
# phase with no error in any phase, as the per-node record pytest writes shows (ruling R6-A3.11.95), never a
# collection error, a skip or a missing file. Options: --jobs=N, --cap=SECONDS (default 3600), --discover,
# --stub-check [--stub-refuse] [--stub-refuse-param] [--stub-slow-collect] [--stub-only=i,j] (the harness's own proof).
import json
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
    # ruling FRAME-TIME-ROUND-R6-A3.3 (2a): match_power
    ("match power not reported", '        out += match_power(recs)\n', '        pass\n'),
    ("match power margin dropped", 'per_game_se.append(margin * w *', 'per_game_se.append(w *'),
    # decision 21'' (ruling FRAME-TIME-ROUND-R6-A3.2), replacing R1-A1's band and nearness mutants
    ("menu e_C contains-1 upper end dropped", 'if not (m_ - h_ <= 1.0 <= m_ + h_):', 'if not (m_ - h_ <= 1.0):'),
    ("menu e_C excludes-0 dropped", 'if m_ - h_ <= 0.0 <= m_ + h_:', 'if False:'),
    ("menu e_C_lo bar dropped", 'if L == MENU_EC_LO_LEVEL and m_ - h_ < MENU_EC_LO_MIN:', 'if False:'),
    ("menu e_C_lo bar at every level", 'if L == MENU_EC_LO_LEVEL and m_ - h_ < MENU_EC_LO_MIN:',
     'if m_ - h_ < MENU_EC_LO_MIN:'),
    ("menu level outside the pattern admitted", '    if outside:\n', '    if False:\n'),
    ("B3 ignores edge calls", 'for op, v in sorted(ops.items()) if v[1] > 0]', 'for op, v in sorted(ops.items()) if False]'),
    ("A3 left out of U", "u = lead + ku + du + a3v", "u = lead + ku + du"),
    ("A3 per-game maximum replaced by the last game", 'rate[k] = max(rate.get(k, 0.0), rows[0]["reads_win"] / on_frames[g])',
     'rate[k] = rows[0]["reads_win"] / on_frames[g]'),
    # ruling FRAME-TIME-ROUND-R5: every dependent row is live, so a3_live's cross-check against the game's a3 line is
    # the first guard of a missing line (the rate loop's own count stays as a second guard, reached by no live row)
    ("A3 missing line passes", 'if len(a3l) != 1 or a3l[0].get("reads_on") != r["reads"]:',
     'if a3l and a3l[0].get("reads_on") != r["reads"]:'),
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
     'if bad or "live" not in r:\n            raise Refused("A3 live row %s: cal i=%s carries a %s line;',
     'if False:\n            raise Refused("A3 live row %s: cal i=%s carries a %s line;'),
    # round 6 (ruling FRAME-TIME-ROUND-R5): M1's one predicate, M2's peer requirement, the method change
    ('M1: the live marker exempts its line from the stand-in fields (the round-5 branch)', 'if bad or "live" not in r:',
     'if "live" not in r:'),
    ('M1: the failure field dropped from the stand-in predicate', 'STAND_IN = ("withheld", "failed", "u", "p", "n")',
     'STAND_IN = ("withheld", "u", "p", "n")'),
    ('M2: A3 reads one seat\'s log as both', 'if dep and peer_recs is None:\n        raise Refused(',
     'if dep and peer_recs is None:\n        peer_recs = recs\n        Refused('),
    ('M2: report gives a verdict from one seat\'s log', 'raise Refused("a verdict needs both seats\' logs:',
     'peer = text; Refused("a verdict needs both seats\' logs:'),
    # re-anchored on report's src/peer_src parameters (brief PARSER-FIX-1109); the mutation is unchanged
    # re-anchored again by V6: report's exposure parameter left with B_U (ruling R6-A3.11.146 (7)); unchanged mutation
    ('M2: report regains a bypass parameter',
     'def report(text, peer=None, src="log", peer_src="peer", ref=None, ref_src="reference"):',
     'def report(text, peer=None, src="log", peer_src="peer", ref=None, ref_src="reference", require_peer=True):'),
    ('R5: a dependent row keeps the retired scratch proof', 'if kind == "dependent" and proof != LIVE_PROOF:',
     'if kind == "dependent" and proof not in (LIVE_PROOF, ""):'),
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
    ('live line for a calibrated row passes', 'if k not in live:\n            # a drained or zero row',
     'if False:\n            # a drained or zero row'),
    ('peer seat live lines ignored', 'ld = {k: max(v, pd[k]) for k, v in ld.items()}', 'ld = dict(ld)'),
    ('live rows left out of A3', 'a3v = sum(rate[k] * ld[k] for k in dep)', 'a3v = sum(rate[k] for k in dep)'),
    ('cal failure warnings unmarked', '        rec["failed"] = 1', '        pass'),
    ('VR2 failure warnings pass', '        if fails:\n            bad.append("game %d: calibration %d carries failure warnings',
     '        if False:\n            bad.append("game %d: calibration %d carries failure warnings'),
    ('VR2 f_hat value not validated', ' and isinstance(fh[0].get("f_hat"), int) and fh[0]["f_hat"] > 0', ''),
    ('menu startup snapshot not required',
     'if len(pre) != 1 or pre[0].get("g") != -1 or pre[0].get("c_plant") != -1:', 'if False:'),
    ('menu failure warnings pass', '    if mfail:\n        bad.append(', '    if False:\n        bad.append('),
    # ruling FRAME-TIME-ROUND-R6-A1: a failed entry calibration is named by its shape in the menu check
    ('menu failure unnamed', ' if r.get("shape") else', ' if False else'),
    # ruling FRAME-TIME-ROUND-R6-A3: VR1's hold line, the named unplanted OFF segment, the menu frame-rate state
    ('VR1 hold not required', 'if not any(FPSCAP_HOLD in ln for ln in caps):', 'if False:'),
    ('VR1 other cap admitted', 'other = [ln for ln in caps if FPSCAP_HOLD not in ln]', 'other = []'),
    ('VR1 window the whole log', 'return ls[:last + 1]', 'return ls'),
    ('menu unplanted OFF segment unnamed', '    if unplanted:\n', '    if False:\n'),
    ('menu frame rate hold not required',
     'bad.append("no \'%s\' line: the hold is not proven reached" % FPSCAP_HOLD)\n    elif', 'pass\n    elif'),
    ('menu frame rate hold order unchecked', 'not (arm < hold < done)', 'False'),
    ('menu frame rate cap before the hold admitted', 'pre = [c for c in caps if arm < c[0] < hold]', 'pre = []'),
    ('menu frame rate cap after the hold admitted',
     'mid = [c for c in caps if start < c[0] < done and FPSCAP_RELEASED not in c[1]]', 'mid = []'),
    ('menu frame rate any cap line admitted as a release', 'and FPSCAP_RELEASED not in c[1]]', 'and "[FPSCAP]" not in c[1]]'),
    ('menu frame rate closing target unchecked',
     'if (o.get("target"), o.get("vsync")) != (c.get("target"), c.get("vsync")):', 'if False:'),
    ('menu frame rate segment floor dropped', 'low = [s for s in fr if fr[s] * MENU_SEG_FLOOR < fr[s0]]', 'low = []'),
    # brief PARSER-FIX-1109: the census summary as its own checked kind, and the read-time required-keys test
    ('census summary not told apart', '            kind = rec["kind"] = sub', '            pass'),
    ('read-time key test removed', '            if gone:\n                raise RecordRefused(r["kind"], src, n, gone)',
     '            if False:\n                raise RecordRefused(r["kind"], src, n, gone)'),
    ('census summary missing not tested', 'if v["missing"] != 0:', 'if False:'),
    # ruling R6-A3.11.92 (3): the churn failure event and the raw-text failure route
    ('churn freeze not a failure event',
     '    ("churn", "freeze", "FtRoomGate: the churn-timer freeze threw (\'churn freeze failed\')"),\n', ''),
    ('raw failures not read in the report', '    miss += raw_failure_events(text)\n', ''),
    ('raw failures not read in the menu check', '        ok, bad = ok and not rawf, bad + rawf\n', ''),
    # ruling R6-A3.11.92 (4): every calibration consumer skips a failed line
    ('complete counts a failed calibration line', 'and not r.get("failed"))\n    for name, have in', ')\n    for name, have in'),
    ('D_up reads a failed disp line', 'r.get("ckind") == "disp" and not r.get("failed"):', 'r.get("ckind") == "disp":'),
    ('stamp estimate reads a failed span line',
     'str(r.get("why", "")).startswith("game")\n                and not r.get("failed")):',
     'str(r.get("why", "")).startswith("game")):'),
    ('menu cycle count reads a failed fhat line', 'startswith("menu") and not r.get("failed")]', 'startswith("menu")]'),
    # Codex PARSER-FIX-R1 MEDIUM: the census summary's non-integer route
    ('census summary non-integer accepted', 'bad.append("census summary %s=%s is not an integer" % (k, r[k]))', 'pass'),
    # Codex PARSER-FIX-R1 HIGH 2 and its sweep: the peer's failure events, disarm and unreadable log
    ('peer raw failures not read', '        miss += ["peer seat: " + w for w in raw_failure_events(peer)]\n', ''),
    ('peer parsed failures not read', '            miss += ["peer seat: " + w for w in failure_events(peer_recs)]\n',
     '            pass\n'),
    ('unreadable peer not withheld', '            miss.append("peer seat: its failure events not read (%s)" % peer_err)\n',
     '            pass\n'),
    ('peer disarm ignored', '        if pdis:\n', '        if False:\n'),
    # Codex PARSER-FIX-R1 HIGH 1: the required-key rows its fixture sweep found
    ('answer_replay g not required', '    ("answer_replay", None, None, ("g",), "f18"),', ''),
    ('p span_g not required', '"span_u", "pred",\n      "span_g"),', '"span_u", "pred"),'),
    ('live calibration fields not required',
     '("reads", "scopes", "ticks", "tmax", "unscoped", "depth_err"),\n     "a3_live"),', '(),\n     "a3_live"),'),
    # ruling R6-A3.11.151 (3): the parser's list of the measuring build's patch classes held to the source's set
    ('ATTACH list short of a source class', '"FtRoute_SendPatch",\n                  "FtSockPatch")',
     '"FtRoute_SendPatch")'),
    # ruling R6-A3.11.151 (2) class C: the bare form --controls <log> is refused with the usage line (the script's
    # main path, which only a run of the script reaches)
    ('--controls bare form not refused',
     '            if _m is None:\n                raise Refused("CONTROLS-REFUSED: --controls takes one',
     '            if False:\n                raise Refused("CONTROLS-REFUSED: --controls takes one'),
]

# B11, the window design (ruling R6-A3.11.138 as .139 amends it): (name, anchor, replacement, the check functions of
# test_ft_parse.py it must turn red). test_ft_parse.py's test_b11_mutant_turns_its_checks_red applies each row in
# process and test_b11_mutant_0_keeps_every_check_green is the negative control, so a seat's pytest run proves them;
# the rows also join MUTS, with their kills as test_b11_check's node ids.
B11_MUTS = [
    ("B11: mates take a product joint probability",
     'return (w["game"], w["round"], w["point"], w["run"], w["unit"])',
     'return (w["game"], w["round"], w["point"], w["run"], w["unit"], w["pos"])',
     ["chk_mates_have_joint_probability_0_or_half", "chk_a_pair_is_one_variance_unit",
      "chk_a_partial_mate_stays_in_its_pair"]),
    ("B11: partial windows given singleton coins",
     'return (w["game"], w["round"], w["point"], w["run"], w["unit"])',
     'return (w["game"], w["round"], w["point"], w["run"], w["unit"], w["pos"] if w["partial"] else 0)',
     ["chk_a_partial_mate_stays_in_its_pair"]),
    ("B11: the tenths summed unweighted (x10)",
     "prof = (sum(y[:TENTHS - 1]) / TENTHS - (TENTHS - 1) / TENTHS * y[TENTHS - 1]) / ff",
     "prof = (sum(y[:TENTHS - 1]) - (TENTHS - 1) * y[TENTHS - 1]) / ff",
     ["chk_c2_recovers_3_25", "chk_c3_recovers_3_0375"]),
    ("B11: no max(0, .) on the charge",
     "bu = max(ub_b, ub_j) if cub > 0 else ub_b",
     "bu = ub_j",
     ["chk_charge_never_negative"]),
    ("B11: classify without the half-width rule",
     'if hw > 0.015 * tref:\n        return "WITHHELD"',
     'if False:\n        return "WITHHELD"',
     ["chk_classify_half_width_rule"]),
    ("B11: R-COMMON against r_U D_common",
     "return total_lo > (1.0 + r_u) * d_common",
     "return total_lo > r_u * d_common",
     ["chk_r_common_comparator"]),
    ("B11: reconciliation stops at a point's first total",
     '                                % (pt, "planted" if planted else "unplanted", wk, tot, pk, p.get(pk)))',
     '                                % (pt, "planted" if planted else "unplanted", wk, tot, pk, p.get(pk)))\n'
     '                    break',
     ["chk_reconcile_reports_every_point"]),
    ("B11: OFF carryover on C-zero, R_OFF not restored",
     '        if w["partial"] == 0:\n            prof = (',
     '        if w["partial"] == 0:\n            y = [w["q"][jj] * k for jj in range(TENTHS)]\n            prof = (',
     ["chk_c3_recovers_3_0375"]),
    ("B11: the full-window profile charged to partials (.138 (5))",
     "share_f, share_p = nfull / N, npart / N",
     "share_f, share_p = 1.0, 0.0",
     ["chk_c4_recovers_3_5", "chk_full_profile_not_applied_to_partials"]),
    ("B11: VR5 ignores an OFF window's switched execution",
     'if b11_line(r) and r["arm"] == "OFF" and r["cS"] != 0:',
     'if False:',
     ["chk_vr5_window_zero"]),
    ("B11: classify without the lower-bound rule",
     'return "SID" if lb > 0.03 * tref else "WITHHELD"',
     'return "SID"',
     ["chk_classify_lower_bound_rule"]),
    # ruling R6-A3.11.140
    ("B11: the baseline centred on run q-1",
     "grun[id(v)] <= grun[id(w)] - 2",
     "grun[id(v)] <= grun[id(w)] - 1",
     ["chk_baseline_frozen_q_minus_2"]),
    ("B11: the carryover exposure drops the predecessor's coin",
     "e2 = event((coin_of(pw), coin_value(pw)), (c, v))",
     "e2 = event((c, v))",
     ["chk_h_p_cross_check", "chk_c4_recovers_3_5"]),
    # retired by V6 (rulings R6-A3.11.146 (6), (7)): B_U and its terms left the verdict, b11_bound with them, so the two
    # exposure-obligation rows ("the exposure envelope left out of B_U", "B_U computed without the exposure
    # obligation") and their check chk_exposure_hook have no code to mutate
    # the whole-line marker (P3 via the integrator): FrameTime is a prefix of FrameTimeRef
    ("B11: the marker matched as a prefix",
     "        pay = m.group(1) if m else ln\n",
     "        pay = m.group(1) if m else ln\n        pay = MARK_FT if pay.startswith(MARK_FT) else pay\n",
     ["chk_marker_whole_line"]),
    ("B11: the marker matched anywhere in the line",
     "m = re.fullmatch(r\"\\[[^\\[\\]]*\\] \\[FRAME-TIME\\] (.*?)\\s*\", ln)",
     "m = re.search(r\"\\[FRAME-TIME\\] (.*?)\\s*$\", ln)",
     ["chk_marker_whole_line"]),
    # the integrator's rulings on the hand-back (to-p2-r2.md)
    ("B11: a charge at its upper end inside the point design's lower bound",
     "hw4, u_lo = dh, de - dh",
     "hw4, u_lo = dh, de - dh + a3v",
     ["chk_v4_lower_bound_at_lower_ends"]),
    ("B11: the lower bound keeps the carryover floor",
     "    lb = j - hjl\n",
     "    lb = j - hjl if joint else b - hbl\n",
     ["chk_charge_never_negative"]),
    ("B11: D_common taken as cW alone",
     '(sum((w["cR"] + w["cW"]) * 1e6',
     '(sum((w["cW"]) * 1e6',
     ["chk_r_common_d_common_and_corrected_r_u"]),
    ("B11: r_U from the uncorrected contrast",
     "xr = J if cub > 0 else B",
     "xr = B",
     ["chk_r_common_d_common_and_corrected_r_u"]),
    ("B11: own_split does not withhold",
     '    osp = [q["pt"] for q in recs if q["kind"] == "p" and q["pt"] in pts and q.get("own_split", 1) != 0]',
     "    osp = []",
     ["chk_own_split_withholds", "chk_validity_set_withholds_sitting_v",
      "chk_sitting_v_withholds_the_counter_and_controls"]),
    # to-p2-r3.md (SHARED md5 2119eb2e)
    ("B11: recv added to the writer cost a second time",
     'WRITER_ADDED = ("log", "hash", "sock")',
     'WRITER_ADDED = ("log", "hash", "recv", "sock")',
     ["chk_writers_recv_never_added"]),
    ("B11: open1 below 0 passes",
     "            if x[6] < 0:\n",
     "            if False:\n",
     ["chk_token_open1_and_continuity"]),
    ("B11: token continuity across windows unchecked",
     "                    if t0[t][0] != t1[t][6]:\n",
     "                    if False:\n",
     ["chk_token_open1_and_continuity"]),
    # retired by V6 (ruling R6-A3.11.146 (7)): the peer-driven charge of D5 left with B_U, peer_on_share with it, so
    # "s_peer taken as 1", "the peer log missing but not withheld" and chk_peer_driven_charge have no code to mutate
    ("B11: recv_offmain and ledger_cycle_miss do not withhold",
     "        if bad:\n            why.append(\"%s nonzero",
     "        if False:\n            why.append(\"%s nonzero",
     ["chk_p_line_faults_withhold", "chk_sitting_v_withholds_the_counter_and_controls"]),
    # to-p2-r4.md (SHARED md5 3ab20794)
    ("B11: sock_main nonzero but not withheld",
     'P_LINE_FAULTS = ("recv_offmain", "ledger_cycle_miss", "sock_main", "span_class_overflow", "plant_mixed")',
     'P_LINE_FAULTS = ("recv_offmain", "ledger_cycle_miss", "span_class_overflow", "plant_mixed")',
     ["chk_p_line_faults_withhold"]),
    # ruling R6-A3.11.151 (2) class B, F3
    ("V6 class B: span_class_overflow nonzero but not withheld",
     'P_LINE_FAULTS = ("recv_offmain", "ledger_cycle_miss", "sock_main", "span_class_overflow", "plant_mixed")',
     'P_LINE_FAULTS = ("recv_offmain", "ledger_cycle_miss", "sock_main", "plant_mixed")',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    # ruling R6-A3.11.152 (2)(h): a frame whose plant state is not its window's first frame's
    ("V6 class B: plant_mixed nonzero but not withheld",
     'P_LINE_FAULTS = ("recv_offmain", "ledger_cycle_miss", "sock_main", "span_class_overflow", "plant_mixed")',
     'P_LINE_FAULTS = ("recv_offmain", "ledger_cycle_miss", "sock_main", "span_class_overflow")',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("B11: a non-Ref log with sock:NA:NA read as a Ref log",
     "for t, x in (_typed(w[\"wu\"], 2, na=True) or {}).items() if x[1] is None))",
     "for t, x in (_typed(w[\"wu\"], 2, na=True) or {}).items() if x[1] is None and x[0] is not None))",
     ["chk_ref_known_by_marker_not_by_na"]),
    # V6 (SHARED.md "V6: the direct bound", Mutants m1 to m12; rulings R6-A3.11.146 and .147), each with the routes
    # beside it; every row's control is its checks green on the unchanged parser (test_b11_mutant_0_keeps_every_check_green)
    ("V6 m1: q keeps P",
     '    if sum(w["q"]) != w["sC"] - g - w["cW"] - w["cP"]:\n',
     '    if sum(w["q"]) != w["sC"] - g - w["cW"]:\n',
     ["chk_q_leaves_p_once", "chk_report_on_hand_computed_u"]),
    ("V6 m1: q loses P twice",
     '    if sum(w["q"]) != w["sC"] - g - w["cW"] - w["cP"]:\n',
     '    if sum(w["q"]) != w["sC"] - g - w["cW"] - 2 * w["cP"]:\n',
     ["chk_q_leaves_p_once", "chk_report_on_hand_computed_u"]),
    ("V6 m1: the line invariants leave the validity set (sitting C's cross-check not stopped by them)",
     '    rows.append(("line invariants",) + _guard(lambda: _ok(window_reconcile(recs))))',
     '    rows.append(("line invariants", True, []))',
     ["chk_q_leaves_p_once", "chk_validity_set_withholds_sitting_v", "chk_validity_set_decides_sitting_c"]),
    ("V6 m2: the class sum without cP",
     'rest = w["cW"] + w["cR"] + w["cS"] + w["cP"] + w["cX"] + w["cE"]',
     'rest = w["cW"] + w["cR"] + w["cS"] + w["cX"] + w["cE"]',
     ["chk_class_sum_holds_cp_and_cx", "chk_q_leaves_p_once"]),
    ("V6 m2: the class sum without cX",
     'rest = w["cW"] + w["cR"] + w["cS"] + w["cP"] + w["cX"] + w["cE"]',
     'rest = w["cW"] + w["cR"] + w["cS"] + w["cP"] + w["cE"]',
     ["chk_class_sum_holds_cp_and_cx"]),
    ("V6 m3: U without D",
     "        u = None if gc is None else d + p + sum(s.values()) + x + gc\n",
     "        u = None if gc is None else p + sum(s.values()) + x + gc\n",
     ["chk_report_on_hand_computed_u"]),
    ("V6 m3: U without P",
     "        u = None if gc is None else d + p + sum(s.values()) + x + gc\n",
     "        u = None if gc is None else d + sum(s.values()) + x + gc\n",
     ["chk_report_on_hand_computed_u"]),
    ("V6 m3: U without S's log",
     "        u = None if gc is None else d + p + sum(s.values()) + x + gc\n",
     '        u = None if gc is None else d + p + s["hash"] + s["sock"] + x + gc\n',
     ["chk_report_on_hand_computed_u"]),
    ("V6 m3: U without S's hash",
     "        u = None if gc is None else d + p + sum(s.values()) + x + gc\n",
     '        u = None if gc is None else d + p + s["log"] + s["sock"] + x + gc\n',
     ["chk_report_on_hand_computed_u"]),
    ("V6 m3: U without S's sock",
     "        u = None if gc is None else d + p + sum(s.values()) + x + gc\n",
     '        u = None if gc is None else d + p + s["log"] + s["hash"] + x + gc\n',
     ["chk_report_on_hand_computed_u"]),
    ("V6 m3: U without X",
     "        u = None if gc is None else d + p + sum(s.values()) + x + gc\n",
     "        u = None if gc is None else d + p + sum(s.values()) + gc\n",
     ["chk_report_on_hand_computed_u"]),
    ("V6 m3: U without G_cap",
     "        u = None if gc is None else d + p + sum(s.values()) + x + gc\n",
     "        u = None if gc is None else d + p + sum(s.values()) + x\n",
     ["chk_report_on_hand_computed_u"]),
    ("V6 m4: P taken as cP alone",
     '    return max(w["cP"], _wu_cyc(w, ("recv",)))',
     '    return w["cP"]',
     ["chk_p_is_the_larger_of_cp_and_recv"]),
    ("V6 m4: L takes P's larger reading, not cP",
     'lo = sum(w["cS"] + w["cR"] + w["cW"] + w["cP"] for w in ws) * k',
     'lo = sum(w["cS"] + w["cR"] + w["cW"] + _p_cyc(w) for w in ws) * k',
     ["chk_p_is_the_larger_of_cp_and_recv"]),
    ("V6 m5: bK without wa",
     '    xs = [w["aW"], w["aR"], w["aS"], w["aP"], w["aX"]] + [wa.get(t) for t in WA_TYPES]',
     '    xs = [w["aW"], w["aR"], w["aS"], w["aP"], w["aX"]]',
     ["chk_report_on_hand_computed_u", "chk_r_gc_numbers"]),
    ("V6 m6: bE taken as aC",
     "be = None if bk is None or None in ac else sum(ac) - bk",
     "be = None if bk is None or None in ac else sum(ac)",
     ["chk_report_on_hand_computed_u", "chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m7: a forced log accepted as a contrast input",
     '    if bad:\n        raise Refused("FORCED-INPUT:',
     '    if False:\n        raise Refused("FORCED-INPUT:',
     ["chk_forced_log_is_no_contrast_input"]),
    ("V6 m7: the as-built report reads a forced log",
     "    contrast_input(recs)\n    e = b11_estimate(recs, first_game)\n",
     "    e = b11_estimate(recs, first_game)\n",
     ["chk_forced_log_is_no_contrast_input"]),
    ("V6 m7: the combining step's cross-check reads a forced log",
     "        contrast_input(recs)\n        e = b11_estimate(recs, first_game)\n",
     "        e = b11_estimate(recs, first_game)\n",
     ["chk_forced_log_is_no_contrast_input"]),
    ("V6 m8: a sitting-V window with arm=OFF accepted",
     '        off = [w for w in rr if b11_line(w) and w["arm"] != "ON"]',
     "        off = []",
     ["chk_sitting_v_is_forced_on"]),
    ("V6 m8: a game with another force= accepted",
     '        nf = [(r["g"], r.get("force")) for r in rr if r["kind"] == "settled" and r.get("force") != FORCE_V]',
     "        nf = []",
     ["chk_sitting_v_is_forced_on"]),
    ("V6 m8: the peer seat's arms and force= not read",
     '    for who, rr in (("this seat", recs), ("the peer seat", peer_recs)):',
     '    for who, rr in (("this seat", recs),):',
     ["chk_sitting_v_is_forced_on"]),
    ("V6 m8: forced mates held to opposite arms",
     "            elif ((g not in forced and len(set(coin_value(w) for w in ws)) != 1)",
     "            elif ((len(set(coin_value(w) for w in ws)) != 1)",
     ["chk_report_on_hand_computed_u", "chk_sitting_v_is_forced_on"]),
    ("V6 m9: an a* or wa NA accepted",
     '    na = [w for w in meas if any(w[a] is None for a in A_FIELDS) or None in (_wa(w["wa"]) or {}).values()]',
     "    na = []",
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: a wa type NA accepted",
     '    na = [w for w in meas if any(w[a] is None for a in A_FIELDS) or None in (_wa(w["wa"]) or {}).values()]',
     "    na = [w for w in meas if any(w[a] is None for a in A_FIELDS)]",
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: pin=differs accepted",
     '    if not bc["pin"][0]:\n',
     "    if False:\n",
     ["chk_sitting_v_withholds_the_counter_and_controls", "chk_combine_four_classes"]),
    ("V6 m9: the pin read as ok whatever it prints",
     '(a.get("pin") == "ok", "pin=%s"',
     '(a.get("pin") in ("ok", "differs"), "pin=%s"',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: ab_back above 0 accepted",
     '    back = [q["pt"] for q in pts if q.get("ab_back", 1) != 0]',
     "    back = []",
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: a control out of range accepted",
     '    for k in ("K1", "K2", "K3"):\n',
     "    for k in ():\n",
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: K1 without its upper end",
     "ask <= med <= ask + K1_ABOVE and emp == 0,",
     "ask <= med and emp == 0,",
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: K1's upper end exclusive",
     "ask <= med <= ask + K1_ABOVE and emp == 0,",
     "ask <= med < ask + K1_ABOVE and emp == 0,",
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: K1's empty median unchecked",
     "ask <= med <= ask + K1_ABOVE and emp == 0,",
     "ask <= med <= ask + K1_ABOVE,",
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: K2 always in range",
     'out["K2"] = (ask == K_PLANT_US and _within(got, K_PLANT_US),',
     'out["K2"] = (True,',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: K3 always in range",
     'out["K3"] = (ask == K_PLANT_US and all(_within(v, K_PLANT_US) for v in rd.values()),',
     'out["K3"] = (True,',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    # ruling R6-A3.11.151 (2) class C, F5: K2 (and K3, its sibling) at 2000 us, never at the log's own asked=; any other
    # asked= is out of range
    ("V6 F5: K2 judged at the log's own asked",
     'out["K2"] = (ask == K_PLANT_US and _within(got, K_PLANT_US),',
     'out["K2"] = (ask is not None and _within(got, ask),',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 F5: K2's asked unchecked",
     'out["K2"] = (ask == K_PLANT_US and _within(got, K_PLANT_US),',
     'out["K2"] = (_within(got, K_PLANT_US),',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 F5: K3 judged at the log's own asked",
     'out["K3"] = (ask == K_PLANT_US and all(_within(v, K_PLANT_US) for v in rd.values()),',
     'out["K3"] = (ask is not None and all(_within(v, ask) for v in rd.values()),',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 F5: K3's asked unchecked",
     'out["K3"] = (ask == K_PLANT_US and all(_within(v, K_PLANT_US) for v in rd.values()),',
     'out["K3"] = (all(_within(v, K_PLANT_US) for v in rd.values()),',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: the 5 percent band exclusive",
     "abs(got - asked) <= K_TOL * asked",
     "abs(got - asked) < K_TOL * asked",
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: a missing alloc line reads as the pin ok",
     'out["pin"] = (False, why) if a is None else',
     'out["pin"] = (True, why) if a is None else',
     ["chk_sitting_v_withholds_the_counter_and_controls", "chk_combine_four_classes"]),
    ("V6 m9: a missing alloc line reads as K1 in range",
     'if a is None:\n        out["K1"] = (False, why)',
     'if a is None:\n        out["K1"] = (True, why)',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: a missing scope plant line reads as K2 in range",
     'if s is None:\n        out["K2"] = (False, why)',
     'if s is None:\n        out["K2"] = (True, why)',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: a missing nest plant line reads as K3 in range",
     'if t is None:\n        out["K3"] = (False, why)',
     'if t is None:\n        out["K3"] = (True, why)',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: a missing photon patches line reads as in range",
     'if ph is None:\n        out["patches"] = (False, why)',
     'if ph is None:\n        out["patches"] = (True, why)',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: a missing scope census line reads as in range",
     'if c is None:\n        out["census"] = (False, why)',
     'if c is None:\n        out["census"] = (True, why)',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: R-SCOPE's lines out of range accepted",
     '    for k in ("patches", "census"):\n',
     "    for k in ():\n",
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: the photon patch count unchecked",
     'out["patches"] = (_num(ph.get("n", "")) == len(names) and tuple(names) == PHOTON_ENTRIES,',
     'out["patches"] = (tuple(names) == PHOTON_ENTRIES,',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: one of the ten photon entries not attached accepted",
     'out["patches"] = (_num(ph.get("n", "")) == len(names) and tuple(names) == PHOTON_ENTRIES,',
     'out["patches"] = (_num(ph.get("n", "")) == len(names) and set(names) <= set(PHOTON_ENTRIES),',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    # ruling R6-A3.11.149 (1), (6) 4: the patch line names the ten typed methods, each once
    ("V6 m9: a patched method not of the ten accepted",
     'out["patches"] = (_num(ph.get("n", "")) == len(names) and tuple(names) == PHOTON_ENTRIES,',
     'out["patches"] = (_num(ph.get("n", "")) == len(names) and set(PHOTON_ENTRIES) <= set(names),',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    # ruling R6-A3.11.153 (2), G1's class: the names as written, in the emitter's order
    ("G1 photon names: compared as a multiset, the order unchecked",
     'out["patches"] = (_num(ph.get("n", "")) == len(names) and tuple(names) == PHOTON_ENTRIES,',
     'out["patches"] = (_num(ph.get("n", "")) == len(names) and sorted(names) == sorted(PHOTON_ENTRIES),',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("G1 photon names: empty entries dropped before the comparison",
     '        names = str(ph.get("names", "")).split(",")\n',
     '        names = [x for x in str(ph.get("names", "")).split(",") if x]\n',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: an unwrapped census entry accepted",
     'out["census"] = (ent is not None and ent > 0 and wr == ent and "failed" not in c and "partial" not in c,',
     'out["census"] = (ent is not None and ent > 0 and "failed" not in c and "partial" not in c,',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m9: a census that threw (failed=) accepted",
     'out["census"] = (ent is not None and ent > 0 and wr == ent and "failed" not in c and "partial" not in c,',
     'out["census"] = (ent is not None and ent > 0 and wr == ent and "partial" not in c,',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    # the confirming round's G3 (ruling R6-A3.11.153 (2) and (3)): the census's partial=1 variant (FtCensus.cs:133, :166)
    ("G3 census: a partial census read in range",
     'out["census"] = (ent is not None and ent > 0 and wr == ent and "failed" not in c and "partial" not in c,',
     'out["census"] = (ent is not None and ent > 0 and wr == ent and "failed" not in c,',
     ["chk_census_partial_out_of_range"]),
    ("G3 census: the partial variant not a form",
     '     + r"(?: partial=1| failed=%s)?" % _FV,',
     '     + r"(?: failed=%s)?" % _FV,',
     ["chk_census_partial_out_of_range"]),
    ("G3 census: both suffixes read as a form",
     '     + r"(?: partial=1| failed=%s)?" % _FV,',
     '     + r"(?: partial=1)?(?: failed=%s)?" % _FV,',
     ["chk_census_partial_out_of_range"]),
    ("G3 census: partial of any value read as a form",
     '     + r"(?: partial=1| failed=%s)?" % _FV,',
     '     + r"(?: partial=\\d+| failed=%s)?" % _FV,',
     ["chk_census_partial_out_of_range"]),
    # ruling .153 (2), K-D: the calibration failure forms read the empty message, and only the word failed
    ("K-D cal failure: a message required after 'failed:'",
     '_CAL_FAILED = r"cal i=-?\\d+(?: [^\\s=]+=\\S*)* failed:(?: .*)?"',
     '_CAL_FAILED = r"cal i=-?\\d+(?: [^\\s=]+=\\S*)* failed: .*"',
     ["chk_emitted_variants_are_forms"]),
    ("K-D cal entries failure: a message required after 'failed:'",
     '    ("cal i=", r"cal i=-?\\d+ kind=disp entries failed:(?: .*)?", None),',
     '    ("cal i=", r"cal i=-?\\d+ kind=disp entries failed: .*", None),',
     ["chk_emitted_variants_are_forms"]),
    ("K-D cal failure: any word read as the failure word",
     '_CAL_FAILED = r"cal i=-?\\d+(?: [^\\s=]+=\\S*)* failed:(?: .*)?"',
     '_CAL_FAILED = r"cal i=-?\\d+(?: [^\\s=]+=\\S*)* \\w+:(?: .*)?"',
     ["chk_emitted_variants_are_forms"]),
    ("K-D cal entries failure: the colon not required",
     '    ("cal i=", r"cal i=-?\\d+ kind=disp entries failed:(?: .*)?", None),',
     '    ("cal i=", r"cal i=-?\\d+ kind=disp entries failed:?(?: .*)?", None),',
     ["chk_emitted_variants_are_forms"]),
    ("V6 m9: bE at 0 or below accepted",
     '    if be:\n        why.append("bE is 0',
     '    if False:\n        why.append("bE is 0',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    # retired by ruling R6-A3.11.149 (5)(a): sitting V's own reads of the p-line faults, own_split, the line invariants
    # and VR1 left for the validity set's rows, mutated below one guard at a time ("V6 validity: ...")
    ("V6 m9: a wu type with NA cycles accepted in sitting V",
     "    if wna:\n",
     "    if False:\n",
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 m10: T_ref taken as T_on",
     '            t_ref = v["T_on"] - u_hi\n',
     '            t_ref = v["T_on"]\n',
     ["chk_t_ref_is_t_on_minus_u_hi", "chk_report_on_hand_computed_u"]),
    ("V6 m11: a contrast above U_hi ignored",
     '    if e["lb"] > u_hi:\n        return "REFUTED", True',
     '    if False:\n        return "REFUTED", True',
     ["chk_combine_four_classes"]),
    ("V6 m11: the worse seat taken as seat 1",
     "    worst = max(range(len(seats)), key=lambda j: RANK[seats[j][1]])",
     "    worst = 0",
     ["chk_combine_four_classes"]),
    ("V6 m11: the combining step ignores sitting V's WITHHELD list",
     '        elif v["why"]:\n            cls, txt = "WITHHELD", "WITHHELD: %s"',
     '        elif False:\n            cls, txt = "WITHHELD", "WITHHELD: %s"',
     ["chk_combine_four_classes"]),
    ("V6 m12: 5 games accepted",
     "    if len(ug) < MIN_GAMES_V:",
     "    if len(ug) < MIN_GAMES_V - 1:",
     ["chk_six_games_at_least"]),
    # R-GC's and R-WORK's numbers (SHARED.md V6)
    ("V6 R-GC: collections per MB not per MB",
     '        out[arm] = sum(w["gcn"] for w in xs) * 1e6 / b if b else None',
     '        out[arm] = sum(w["gcn"] for w in xs) if b else None',
     ["chk_r_gc_numbers"]),
    ("V6 R-WORK: sitting C's u_g over both arms",
     '            ugc, _ = u_games(crecs[n], first_game, arm="ON")',
     "            ugc, _ = u_games(crecs[n], first_game)",
     ["chk_r_gc_numbers"]),
    ("V6 R-WORK: u_games ignores its arm",
     '                and (arm is None or w["arm"] == arm)):',
     "                and True):",
     ["chk_r_gc_numbers"]),
    # P1's V6 emitter (via the integrator, 12 Nov): the counters line's span_leave_mismatch and photon_offmain, and the
    # boot's controls k_mutant line
    ("V6 counters: a nonzero span_leave_mismatch accepted",
     '            if cs[0].get("span_leave_mismatch", 0) != 0:',
     "            if False:",
     ["chk_counters_line_v6_keys"]),
    ("V6 counters: a counters line without span_leave_mismatch accepted",
     "            for k in COUNTER_KEYS_V6 + COUNTER_REPORTED_V6:",
     "            for k in COUNTER_REPORTED_V6:",
     ["chk_counters_line_v6_keys"]),
    ("V6 counters: a counters line without photon_offmain accepted",
     "            for k in COUNTER_KEYS_V6 + COUNTER_REPORTED_V6:",
     "            for k in COUNTER_KEYS_V6:",
     ["chk_counters_line_v6_keys"]),
    ("V6 counters: VR2 leaves the counters line out",
     "    bad += counters_faults(recs, games)\n",
     "",
     ["chk_counters_line_v6_keys"]),
    # "sitting V leaves the counters line out" is "V6 validity: the counters line not applied to sitting V" below
    ("V6 k_mutant: a sitting log with k_mutant not none accepted",
     '    if km != "none":\n        raise Refused("K-MUTANT',
     '    if False:\n        raise Refused("K-MUTANT',
     ["chk_k_mutant_sitting_refused_and_controls_proof"]),
    ("V6 k_mutant: a sitting input of report_on or combine not checked",
     "    refuse_k_mutant(recs, src)                  # a sitting input of either sitting\n",
     "",
     ["chk_k_mutant_sitting_refused_and_controls_proof"]),
    ("V6 k_mutant: the as-built report's inputs not checked",
     "    refuse_k_mutant(recs, src)\n    if peer_recs is not None:\n        refuse_k_mutant(peer_recs, peer_src)\n",
     "",
     ["chk_k_mutant_sitting_refused_and_controls_proof"]),
    ("V6 k_mutant: a control read out of range from k_mutant's name",
     '    got = set(k for k in ("K1", "K2", "K3") if not bc[k][0])',
     '    got = set() if km == "none" else {K_MUTANTS[km]}',
     ["chk_k_mutant_sitting_refused_and_controls_proof"]),
    ("V6 k_mutant: another control out of range beside the named one accepted",
     "    ok = got == want and not scope and not unk\n",
     "    ok = want <= got and not scope and not unk\n",
     ["chk_k_mutant_sitting_refused_and_controls_proof"]),
    # ruling R6-A3.11.151 (2) class C (F4, F5): the control read, one mutant per refusal and per term of the proof
    ("V6 controls: a profile not of the four read",
     "    if profile not in CONTROL_PROFILES:\n        raise Refused(",
     "    if False:\n        raise Refused(",
     ["chk_k_mutant_sitting_refused_and_controls_proof"]),
    ("V6 controls: a boot whose k_mutant is not the profile's read",
     "    if km != want_km:\n        raise Refused(",
     "    if False:\n        raise Refused(",
     ["chk_k_mutant_sitting_refused_and_controls_proof"]),
    ("V6 controls: the ruled lines unchecked",
     "    bad = control_records(text)\n",
     "    bad = []\n",
     ["chk_controls_ruled_lines_refused"]),
    ("V6 controls: an absent ruled line accepted",
     "        if len(ls) != 1:\n            bad.append(\"%d '%s' lines (needs exactly 1)\" % (len(ls), lead))",
     "        if not ls:\n            continue\n        if len(ls) != 1:\n"
     "            bad.append(\"%d '%s' lines (needs exactly 1)\" % (len(ls), lead))",
     ["chk_controls_ruled_lines_refused"]),
    ("V6 controls: a ruled line twice accepted",
     "        if len(ls) != 1:\n            bad.append(\"%d '%s' lines (needs exactly 1)\" % (len(ls), lead))",
     "        if len(ls) < 1:\n            bad.append(\"%d '%s' lines (needs exactly 1)\" % (len(ls), lead))",
     ["chk_controls_ruled_lines_refused"]),
    ("V6 controls: a ruled line out of its form accepted",
     "        elif pat[lead].fullmatch(ls[0]) is None:",
     "        elif False:",
     ["chk_controls_ruled_lines_refused"]),
    ("V6 controls: a plant's asked unchecked",
     "        if len(asked) == 1 and asked[0] != K_PLANT_US:",
     "        if False:",
     ["chk_controls_ruled_lines_refused"]),
    ("V6 controls: ATTACH not applied to a control boot",
     '    bad += ["ATTACH: " + w for w in attach_guard(text)]\n',
     "",
     ["chk_controls_ruled_lines_refused", "chk_controls_forms_and_failed_to_patch"]),
    ("V6 controls: the census summary not applied to a control boot",
     '    bad += ["census summary: " + w for w in census_summary(recs)[2]]\n',
     "",
     ["chk_controls_ruled_lines_refused"]),
    ("V6 controls: the arm file not applied to a control boot",
     "    bad += arm_problems(recs)\n    if bad:\n        raise Refused(\"CONTROLS-REFUSED",
     "    if bad:\n        raise Refused(\"CONTROLS-REFUSED",
     ["chk_controls_ruled_lines_refused"]),
    ("V6 controls: R-SCOPE out of range does not fail the proof",
     "    ok = got == want and not scope and not unk\n",
     "    ok = got == want and not unk\n",
     ["chk_controls_ruled_lines_refused"]),
    # ruling R6-A3.11.149 (7): one mutant per validity guard not applied to sitting V (its row fails, B1 is not
    # withheld for it), each killed by its own spoil in chk_validity_set_withholds_sitting_v
    ("V6 validity: the complete sitting not applied to sitting V",
     '        if not ok:\n            why.append("%s: %s" % (name, _reasons(w)))',
     '        if not ok and name != "complete sitting":\n            why.append("%s: %s" % (name, _reasons(w)))',
     ["chk_validity_set_withholds_sitting_v"]),
    ("V6 validity: the census summary not applied to sitting V",
     '        if not ok:\n            why.append("%s: %s" % (name, _reasons(w)))',
     '        if not ok and name != "census summary":\n            why.append("%s: %s" % (name, _reasons(w)))',
     ["chk_validity_set_withholds_sitting_v"]),
    ("V6 validity: VR1 not applied to sitting V",
     '        if not ok:\n            why.append("%s: %s" % (name, _reasons(w)))',
     '        if not ok and name != "VR1":\n            why.append("%s: %s" % (name, _reasons(w)))',
     ["chk_validity_set_withholds_sitting_v", "chk_vr1_reads_t_on", "chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 validity: VR2's instrument half not applied to sitting V",
     '        if not ok:\n            why.append("%s: %s" % (name, _reasons(w)))',
     '        if not ok and name != "VR2 instrument":\n            why.append("%s: %s" % (name, _reasons(w)))',
     ["chk_validity_set_withholds_sitting_v"]),
    ("V6 validity: VR5's records half not applied to sitting V",
     '        if not ok:\n            why.append("%s: %s" % (name, _reasons(w)))',
     '        if not ok and name != "VR5 records":\n            why.append("%s: %s" % (name, _reasons(w)))',
     ["chk_validity_set_withholds_sitting_v"]),
    ("V6 validity: VR6's build half not applied to sitting V",
     '        if not ok:\n            why.append("%s: %s" % (name, _reasons(w)))',
     '        if not ok and name != "VR6 build":\n            why.append("%s: %s" % (name, _reasons(w)))',
     ["chk_validity_set_withholds_sitting_v"]),
    ("V6 validity: F18 not applied to sitting V",
     '        if not ok:\n            why.append("%s: %s" % (name, _reasons(w)))',
     '        if not ok and name != "F18":\n            why.append("%s: %s" % (name, _reasons(w)))',
     ["chk_validity_set_withholds_sitting_v"]),
    ("V6 validity: the counters line not applied to sitting V",
     '        if not ok:\n            why.append("%s: %s" % (name, _reasons(w)))',
     '        if not ok and name != "counters line":\n            why.append("%s: %s" % (name, _reasons(w)))',
     ["chk_validity_set_withholds_sitting_v", "chk_counters_line_v6_keys"]),
    ("V6 validity: the line invariants not applied to sitting V",
     '        if not ok:\n            why.append("%s: %s" % (name, _reasons(w)))',
     '        if not ok and name != "line invariants":\n            why.append("%s: %s" % (name, _reasons(w)))',
     ["chk_validity_set_withholds_sitting_v", "chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 validity: the p-line faults not applied to sitting V",
     '        if not ok:\n            why.append("%s: %s" % (name, _reasons(w)))',
     '        if not ok and name != "p-line faults":\n            why.append("%s: %s" % (name, _reasons(w)))',
     ["chk_validity_set_withholds_sitting_v", "chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 validity: own_split not applied to sitting V",
     '        if not ok:\n            why.append("%s: %s" % (name, _reasons(w)))',
     '        if not ok and name != "own_split":\n            why.append("%s: %s" % (name, _reasons(w)))',
     ["chk_validity_set_withholds_sitting_v", "chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 validity: the build marker not applied to sitting V",
     '        if not ok:\n            why.append("%s: %s" % (name, _reasons(w)))',
     '        if not ok and name != "build marker":\n            why.append("%s: %s" % (name, _reasons(w)))',
     ["chk_validity_set_withholds_sitting_v"]),
    # ruling R6-A3.11.149 (6) 3: VR1 in sitting V reads T_on
    ("V6 VR1: sitting V's VR1 fed T_on - U_hi",
     '    t_vr1 = v["T_on"]                   # ruling R6-A3.11.149 (6) 3: VR1 reads T_on, the frames\' observed mean',
     '    t_vr1 = v["T_on"] - v["U_hi"] if v["U_hi"] is not None else v["T_on"]',
     ["chk_vr1_reads_t_on"]),
    # ruling R6-A3.11.149 (5)(c): a sitting-C log failing a validity guard gives no cross-check
    ("V6 sitting C: a log failing a validity guard taken as not refuted",
     "    unavail = [n for n, ok, _ in rows if not ok]",
     "    unavail = []",
     ["chk_validity_set_decides_sitting_c", "chk_q_leaves_p_once"]),
    ("V6 cross-check: the unavailable state read as not refuted",
     '    if unavail:\n        return "unavailable (%s)" % ", ".join(unavail), True',
     '    if False:\n        return "unavailable (%s)" % ", ".join(unavail), True',
     ["chk_validity_set_decides_sitting_c"]),
    # ruling R6-A3.11.149 (5)(d), (e): every failing two-arm guard named on the verdict line
    ("V6 two-arm: a failing guard not named on the verdict line",
     '        weak = _weak(sc["two"])',
     "        weak = []",
     ["chk_two_arm_guards_named_on_the_verdict_line", "chk_two_arm_three_words"]),
    ("V6 cross-check: the weakened state dropped",
     '    if weak:\n        return "not refuted, weakened by %s"',
     '    if False:\n        return "not refuted, weakened by %s"',
     ["chk_two_arm_guards_named_on_the_verdict_line", "chk_two_arm_three_words"]),
    # the integrator's follow-up to ruling .149, C: three words, PASS, FAIL and NOT TESTED; FAIL and NOT TESTED weaken
    ("V6 two-arm: R-COMMON without a reference read as FAIL",
     '    return name, "NOT TESTED" if ok is None else ("PASS" if ok else "FAIL"), det',
     '    return name, "FAIL" if ok is None else ("PASS" if ok else "FAIL"), det',
     ["chk_two_arm_three_words", "chk_two_arm_guards_named_on_the_verdict_line"]),
    ("V6 two-arm: NOT TESTED does not weaken the cross-check",
     '    return [(nm, w, d) for nm, w, d in two if w != "PASS"]',
     '    return [(nm, w, d) for nm, w, d in two if w == "FAIL"]',
     ["chk_two_arm_three_words", "chk_two_arm_guards_named_on_the_verdict_line"]),
    ("V6 two-arm: the words dropped from the verdict line",
     '    return ", ".join("%s (%s)" % (nm, "not tested: %s" % d if w == "NOT TESTED" else "fail") for nm, w, d in weak)',
     '    return ", ".join(nm for nm, w, d in weak)',
     ["chk_two_arm_three_words", "chk_two_arm_guards_named_on_the_verdict_line"]),
    ("V6 two-arm: a guard that cannot be computed read as NOT TESTED",
     '        return name, "FAIL", "not computable: %s" % x',
     '        return name, "NOT TESTED", "not computable: %s" % x',
     ["chk_two_arm_three_words"]),
    ("V6 two-arm: R-COMMON's reference asked for after the contrast",
     '    if ref_recs is None:\n        return None, "no reference log"            # the follow-up to ruling .149, C: its'
     ' input is absent\n    e = _need_e(e)\n',
     '    e = _need_e(e)\n    if ref_recs is None:\n        return None, "no reference log"\n',
     ["chk_two_arm_three_words"]),
    ("V6 two-arm: the combining step's TWO-ARM line prints PASS or FAIL",
     '        out += ["V6 TWO-ARM seat %s %s %s: %s" % (n, nm, w, d) for nm, w, d in sc["two"]]',
     '        out += ["V6 TWO-ARM seat %s %s %s: %s" % (n, nm, "PASS" if w == "PASS" else "FAIL", d)'
     ' for nm, w, d in sc["two"]]',
     ["chk_two_arm_three_words", "chk_two_arm_guards_named_on_the_verdict_line"]),
    # ruling R6-A3.11.149 (5)(g): B3 on both sittings
    ("V6 B3: judged on sitting V only",
     '        b3s = (("V", v["b3"]), ("C", sc["b3"]))         # ruling .149 (5)(g): judged on both sittings',
     '        b3s = (("V", v["b3"]),)',
     ["chk_b3_on_both_sittings"]),
    ("V6 B3: judged on sitting C only",
     '        b3s = (("V", v["b3"]), ("C", sc["b3"]))         # ruling .149 (5)(g): judged on both sittings',
     '        b3s = (("C", sc["b3"]),)',
     ["chk_b3_on_both_sittings"]),
    # ruling R6-A3.11.149 (6) 6: the seats paired by name and checked by f_hat
    ("V6 pairing: the seats paired by position",
     "    pair = dict((n, c_logs[n]) for n in names)          # ruling .149 (6) 6: by name, never by position",
     "    pair = dict(zip(names, c_logs.values()))",
     ["chk_seats_paired_by_name"]),
    ("V6 pairing: the f_hat check skipped",
     '        paired[n] = fv is not None and fc[n] is not None and abs(fc[n] - fv) <= FHAT_PAIR * fv',
     "        paired[n] = True",
     ["chk_seats_paired_by_name"]),
    ("V6 pairing: a failed f_hat check does not withhold",
     "        if not paired[n]:\n",
     "        if False:\n",
     ["chk_seats_paired_by_name"]),
    # ruling R6-A3.11.149 (5)(f): void rounds stay in sitting V's population, and VR8's zero-state half is reported
    ("V6 VR8: void rounds dropped from sitting V's population",
     '    byg = {}\n    for w in recs:\n        if (b11_line(w) and w["game"] >= first_game and w["plant"] == 0 and w["res"] == 0\n',
     '    byg = {}\n    _vr = void_rounds(recs)\n    for w in recs:\n        if (b11_line(w) and w["game"] >= first_game and w["plant"] == 0'
     ' and w["res"] == 0 and (w["game"], int(w["pt"].split(".")[1])) not in _vr\n',
     ["chk_void_rounds_stay_in_sitting_v"]),
    ("V6 VR8: the zero-state half not reported in sitting V",
     "    v.update(validity=rows, zero=_zero(recs), b3=_b3(recs), fhat=seat_fhat(recs, first_game))",
     "    v.update(validity=rows, zero=(True, 0, 0, [], []), b3=_b3(recs), fhat=seat_fhat(recs, first_game))",
     ["chk_void_rounds_stay_in_sitting_v"]),
    # the integrator's follow-up to ruling .149, A: the writer ledger's disk-log tap, read in sitting V (withholds) and
    # reported beside sitting C's R-WORK line (decides nothing there)
    ("V6 ledger: an absent ledger line accepted",
     "    if len(ls) != 1:\n        return False, [\"%d 'ledger' lines",
     "    if not ls:\n        return True, [], \"not read\"\n    if len(ls) != 1:\n        return False, [\"%d 'ledger' lines",
     ["chk_ledger_tap_withholds_sitting_v"]),
    ("V6 ledger: two ledger lines accepted",
     "    if len(ls) != 1:\n        return False, [\"%d 'ledger' lines",
     "    if len(ls) < 1:\n        return False, [\"%d 'ledger' lines",
     ["chk_ledger_tap_withholds_sitting_v"]),
    ("V6 ledger: log=0 accepted",
     '    if log != "1":\n        bad.append("ledger log=%s why=%s',
     '    if False:\n        bad.append("ledger log=%s why=%s',
     ["chk_ledger_tap_withholds_sitting_v", "chk_instruments_not_attached_withhold"]),
    ("V6 ledger: the writer list not compared",
     "    if listed != WRITER_TYPES:\n",
     "    if False:\n",
     ["chk_ledger_tap_withholds_sitting_v", "chk_ledger_types_judged_as_written"]),
    # the confirming round's G1 (ruling R6-A3.11.153 (2)): the list as written, one mutant per route back to the defect
    ("G1 ledger: the writer list compared by membership",
     "    if listed != WRITER_TYPES:\n",
     "    if set(listed) - {\"\"} != set(WRITER_TYPES):\n",
     ["chk_ledger_types_judged_as_written"]),
    ("G1 ledger: empty entries dropped before the comparison",
     '    listed = tuple(types.split(","))\n',
     '    listed = tuple(t for t in types.split(",") if t)\n',
     ["chk_ledger_types_judged_as_written"]),
    # ruling R6-A3.11.154: the refusals line of its form, or refused as written; one mutant per route
    ("154 refusals: a repeated key admitted again",
     '            if k in seen:\n                if ("%s printed twice" % k) not in form:',
     '            if False:\n                if ("%s printed twice" % k) not in form:',
     ["chk_refusals_line_judged_as_written"]),
    ("154 refusals: pairs= not compared with the pairs listed",
     '        elif rec["pairs"] != listed:',
     "        elif False:",
     ["chk_refusals_line_judged_as_written"]),
    ("154 refusals: a token not key=value dropped",
     '            if not k:\n                form.append("%s is not <key>=<value>" % tok)\n                continue',
     "            if not k:\n                continue",
     ["chk_refusals_line_judged_as_written"]),
    # ruling R6-A3.11.154: FT-GATE excluded= held to the design's names (membership, no count per name)
    ("154 FT-GATE: a name outside the design admitted",
     "    for n in sorted(set(x for x in names if x not in GATE_EXCLUDED_DESIGN)):",
     "    for n in []:",
     ["chk_gate_excluded_held_to_the_design", "chk_attach_guard"]),
    ("154 FT-GATE: an empty entry in excluded= admitted",
     '    if "" in names:\n        return ["the FT-GATE patched line is not in its form (an empty entry',
     '    if False:\n        return ["the FT-GATE patched line is not in its form (an empty entry',
     ["chk_gate_excluded_held_to_the_design", "chk_attach_guard"]),
    ("154 FT-GATE: a design name printed twice made a fault",
     "    for n in sorted(set(x for x in names if x not in GATE_EXCLUDED_DESIGN)):",
     "    for n in sorted(set(x for x in names if x not in GATE_EXCLUDED_DESIGN or names.count(x) > 1)):",
     ["chk_gate_excluded_held_to_the_design", "chk_attach_guard"]),
    ("154 FT-GATE: the design's names not the plugin's NotRoomEntry",
     'GATE_EXCLUDED_DESIGN = ("JoinLobby", "LoadOrCreateSettings")',
     'GATE_EXCLUDED_DESIGN = ("JoinLobby", "LoadOrCreateSettings", "JoinRoomAsync")',
     ["chk_gate_excluded_held_to_the_design"]),
    # ruling R6-A3.11.154: an empty entry in cal u= or p= refused as written
    ("154 cal lists: an empty entry admitted (d_up's ValueError again)",
     '            if not re.fullmatch(r"-?\\d+(?:,-?\\d+)*", v):\n                raise Refused("the cal line',
     '            if False:\n                raise Refused("the cal line',
     ["chk_cal_lists_refused_as_written"]),
    ("154 cal lists: empty entries dropped before the check",
     '            if not re.fullmatch(r"-?\\d+(?:,-?\\d+)*", v):\n                raise Refused("the cal line',
     '            if not re.fullmatch(r"-?\\d+(?:,-?\\d+)*", ",".join(x for x in v.split(",") if x)):\n'
     '                raise Refused("the cal line',
     ["chk_cal_lists_refused_as_written"]),
    # the J3 follow-up to ruling .154: one mutant per FREE_TEXT row (the free text scanned as fields again)
    ("J3 free text: a failure message read as fields",
     '    (None, r"(?:^|\\s)failed:",', '    (None, r"(?!)",', ["chk_free_text_never_read_as_fields"]),
    ("J3 free text: the room line's name read as fields",
     '    ("room", r"(?:^|\\s)name=",', '    ("room", r"(?!)",', ["chk_free_text_never_read_as_fields"]),
    ("J3 free text: the armed line's room name read as fields",
     '    ("armed", r"(?:^|\\s)room=",', '    ("armed", r"(?!)",', ["chk_free_text_never_read_as_fields"]),
    ("J3 free text: the churn line's room name read as fields",
     '    ("churn", r"(?:^|\\s)room=",', '    ("churn", r"(?!)",', ["chk_free_text_never_read_as_fields"]),
    ("J3 free text: the room options line's room name read as fields",
     '    ("ft", r"(?:^|\\s)room=",', '    ("ft", r"(?!)",', ["chk_free_text_never_read_as_fields"]),
    # the J4 follow-up to ruling .154 (2)(g): an empty value skipped again
    ("J4 empty value: a key printed empty skipped",
     "        if (kind, k) not in EMPTY_OK:\n            raise Refused(",
     "        if False:\n            raise Refused(",
     ["chk_empty_values_refused_as_written"]),
    # the J1 follow-up to ruling .154: the NCH. names held to the plugin's arrays
    ("J1 NCH names: a name of the arrays missing",
     'NCH_ENTRIES = ("QuickMatch", "JoinRandomRoom", "PlayOnBestActiveRegion", "DoRetry")',
     'NCH_ENTRIES = ("QuickMatch", "JoinRandomRoom", "PlayOnBestActiveRegion")',
     ["chk_nch_room_calls_held_to_the_source", "chk_emitted_variants_are_forms"]),
    ("J1 NCH names: any NCH. op admitted",
     "(?!NCH\\.)\\S+) name=", "\\S+) name=",
     ["chk_nch_room_calls_held_to_the_source", "chk_emitted_variants_are_forms"]),
    ("plant from: the sentinel's plant line is no form",
     '("plant c_plant=", _star("plant"), None)', '("plant c_plant=", r"plant c_plant=\\d+ ticks=\\d+ from=\\d+\\.\\d+\\.\\d+", None)',
     ["chk_plant_from_held_to_the_source", "chk_emitted_variants_are_forms"]),
    ("J1 NCH names: the room line's form admits every room line again",
     '("room name=", r"room name=.*", None)', '("room name=", _msg("room"), None)',
     ["chk_nch_room_calls_held_to_the_source", "chk_emitted_variants_are_forms"]),
    ("154 refusals: VR6 reads the pairs of a line out of its form",
     '    if bad:\n        return False, bad + (["disarmed: "',
     '    if False:\n        return False, bad + (["disarmed: "',
     ["chk_refusals_line_judged_as_written"]),
    ("V6 ledger: sitting V ignores the disk-log tap",
     '    why += ["the disk-log tap: %s" % w for w in lwhy]',
     "    why += []",
     ["chk_ledger_tap_withholds_sitting_v", "chk_instruments_not_attached_withhold"]),
    ("V6 ledger: the peer's tap judged for this seat",
     "    lok, lwhy, _ = ledger_state(recs)",
     "    lok, lwhy, _ = ledger_state(peer_recs)",
     ["chk_ledger_tap_withholds_sitting_v"]),
    ("V6 ledger: sitting C's R-WORK line without the tap's state",
     "        lok, lwhy, lst = ledger_state(crecs[n])",
     '        lok, lwhy, lst = True, [], ""',
     ["chk_ledger_tap_withholds_sitting_v"]),
    ("V6 ledger: sitting C's tap decides the cross-check",
     "    unavail = [n for n, ok, _ in rows if not ok]",
     "    unavail = [n for n, ok, _ in rows if not ok] + ledger_state(recs)[1]",
     ["chk_ledger_tap_withholds_sitting_v"]),
    # ruling R6-A3.11.151 (3), ATTACH (it folds the follow-up to ruling .149, B's patches attached and room gate rows):
    # one mutant per rule of each part, the peer's sweep, the sitting V and sitting C routes and the reference's list
    ("V6 ATTACH: a 'Failed to patch' line accepted",
     '        if FAILED_PATCH in ln and ln.strip() != "slice class %s: 0 lines" % FAILED_PATCH:\n            ln = ln.strip()',
     "        if False:\n            ln = ln.strip()",
     ["chk_attach_guard", "chk_instruments_not_attached_withhold", "chk_controls_forms_and_failed_to_patch"]),
    ("V6 ATTACH: the laptop slice's withheld form missed",
     '        if FAILED_PATCH in ln and ln.strip() != "slice class %s: 0 lines" % FAILED_PATCH:\n            ln = ln.strip()',
     '        if "[HARMONY] " + FAILED_PATCH in ln:\n            ln = ln.strip()',
     ["chk_attach_guard"]),
    ("V6 ATTACH: the peer seat's log not swept",
     '    if peer_text is not None:\n        bad += ["peer seat: " + w for w in attach_guard(peer_text)]',
     '    if False:\n        bad += ["peer seat: " + w for w in attach_guard(peer_text)]',
     ["chk_attach_guard"]),
    ("V6 ATTACH: an absent attach line accepted",
     "    if len(lines) != 1:\n        return [\"%d 'attach' lines",
     "    if not lines:\n        return bad\n    if len(lines) != 1:\n        return [\"%d 'attach' lines",
     ["chk_attach_guard"]),
    ("V6 ATTACH: two attach lines accepted",
     "    if len(lines) != 1:\n        return [\"%d 'attach' lines",
     "    if len(lines) < 1:\n        return [\"%d 'attach' lines",
     ["chk_attach_guard"]),
    ("V6 ATTACH: 'attach report failed' accepted",
     '        if r["kind"] == "attach_failed":\n            bad.append(',
     '        if False:\n            bad.append(',
     ["chk_attach_guard"]),
    ("V6 ATTACH: an attach line out of its form accepted",
     "    if _ATTACH_PAYLOAD.fullmatch(pay) is None:\n        return [",
     "    if False:\n        return [",
     ["chk_attach_guard"]),
    ("V6 ATTACH: an entry of want 0 accepted",
     "        if int(want) == 0:\n            bad.append(",
     "        if False:\n            bad.append(",
     ["chk_attach_guard"]),
    ("V6 ATTACH: an entry of got unlike want accepted",
     "        elif int(got) != int(want):\n            bad.append(",
     "        elif False:\n            bad.append(",
     ["chk_attach_guard", "chk_controls_ruled_lines_refused"]),
    ("V6 ATTACH: a class of the build not named accepted",
     '    if gone:\n        bad.append("attach names lack',
     '    if False:\n        bad.append("attach names lack',
     ["chk_attach_guard"]),
    ("V6 ATTACH: a class not of the build accepted",
     '    if alien:\n        bad.append("attach names %s, not a patch class',
     '    if False:\n        bad.append("attach names %s, not a patch class',
     ["chk_attach_guard"]),
    ("V6 ATTACH: a class named twice accepted",
     '    if dup:\n        bad.append("attach names %s twice"',
     '    if False:\n        bad.append("attach names %s twice"',
     ["chk_attach_guard"]),
    ("V6 ATTACH: entries out of order accepted",
     "    if names != sorted(names):\n",
     "    if False:\n",
     ["chk_attach_guard"]),
    ("V6 ATTACH: of unlike the entries' count accepted",
     "    if of != len(ents):\n",
     "    if False:\n",
     ["chk_attach_guard"]),
    ("V6 ATTACH: n unlike the attached entries accepted",
     "    if n != ok:\n",
     "    if False:\n",
     ["chk_attach_guard"]),
    ("V6 ATTACH: n unlike of accepted",
     "    if n != of:\n",
     "    if False:\n",
     ["chk_attach_guard"]),
    ("V6 ATTACH: missing= not none accepted",
     '    if missing != "none":\n',
     "    if False:\n",
     ["chk_attach_guard"]),
    ("V6 ATTACH: the attach line's part left out",
     "    return attach_faults(text, classes) + attach_patch_faults(text) + attach_gate_faults(text)",
     "    return attach_patch_faults(text) + attach_gate_faults(text)",
     ["chk_attach_guard"]),
    ("V6 ATTACH: the 'Failed to patch' part left out",
     "    return attach_faults(text, classes) + attach_patch_faults(text) + attach_gate_faults(text)",
     "    return attach_faults(text, classes) + attach_gate_faults(text)",
     ["chk_attach_guard", "chk_instruments_not_attached_withhold"]),
    ("V6 ATTACH: the room gate's part left out (F17)",
     "    return attach_faults(text, classes) + attach_patch_faults(text) + attach_gate_faults(text)",
     "    return attach_faults(text, classes) + attach_patch_faults(text)",
     ["chk_attach_guard", "chk_instruments_not_attached_withhold"]),
    ("V6 room gate: a count short of the expected accepted",
     "    if m.group(1) != m.group(2) or int(m.group(2)) == 0 or m.group(4) is not None:",
     "    if int(m.group(2)) == 0 or m.group(4) is not None:",
     ["chk_attach_guard", "chk_instruments_not_attached_withhold", "chk_controls_ruled_lines_refused"]),
    ("V6 room gate: a missing= list accepted",
     "    if m.group(1) != m.group(2) or int(m.group(2)) == 0 or m.group(4) is not None:",
     "    if m.group(1) != m.group(2) or int(m.group(2)) == 0:",
     ["chk_attach_guard"]),
    ("V6 room gate: no entry point expected accepted",
     "    if m.group(1) != m.group(2) or int(m.group(2)) == 0 or m.group(4) is not None:",
     "    if m.group(1) != m.group(2) or m.group(4) is not None:",
     ["chk_attach_guard"]),
    ("V6 room gate: an absent FT-GATE patched line accepted",
     "    if len(ls) != 1:\n        return [\"%d 'FT-GATE patched' lines",
     "    if not ls:\n        return []\n    if len(ls) != 1:\n        return [\"%d 'FT-GATE patched' lines",
     ["chk_attach_guard"]),
    ("V6 room gate: two FT-GATE patched lines accepted",
     "    if len(ls) != 1:\n        return [\"%d 'FT-GATE patched' lines",
     "    if len(ls) < 1:\n        return [\"%d 'FT-GATE patched' lines",
     ["chk_attach_guard"]),
    ("V6 room gate: a line not in its form accepted",
     '    if m is None:\n        return ["the FT-GATE patched line is not in its form',
     '    if m is None:\n        return []\n        return ["the FT-GATE patched line is not in its form',
     ["chk_attach_guard"]),
    ("V6 validity: ATTACH not applied to sitting V",
     '        if not ok:\n            why.append("%s: %s" % (name, _reasons(w)))',
     '        if not ok and name != "ATTACH":\n            why.append("%s: %s" % (name, _reasons(w)))',
     ["chk_attach_guard", "chk_instruments_not_attached_withhold"]),
    ("V6 validity: ATTACH not applied to sitting C",
     "    unavail = [n for n, ok, _ in rows if not ok]",
     '    unavail = [n for n, ok, _ in rows if not ok and n != "ATTACH"]',
     ["chk_attach_guard"]),
    ("V6 ATTACH: a reference read against the measuring build's list",
     "    bad = attach_guard(text, ATTACH_CLASSES_REF)",
     "    bad = attach_guard(text, ATTACH_CLASSES)",
     ["chk_attach_guard"]),
    ("V6 ATTACH: a reference's ATTACH unchecked",
     "    bad = attach_guard(text, ATTACH_CLASSES_REF)",
     "    bad = []",
     ["chk_attach_guard"]),
    ("V6 ATTACH: the reference build's list holds FtSockPatch",
     'ATTACH_CLASSES_REF = tuple(c for c in ATTACH_CLASSES if c != "FtSockPatch")',
     "ATTACH_CLASSES_REF = ATTACH_CLASSES",
     ["chk_attach_guard"]),
    # ruling R6-A3.11.151 (2) class B: the fault fields given a rule
    ("V6 class B: ab_retry above 0 not withheld",
     '    if retry:\n        why.append("ab_retry above 0',
     '    if False:\n        why.append("ab_retry above 0',
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 class B: the gate counters not withheld in sitting V",
     '    why += ["VR5\'s window counters: %s" % w for w in gate_counter_faults(recs, set(q["pt"] for q in pts))]',
     "    why += []",
     ["chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 class B: the gate counters not read by VR5",
     "    bad = gate_counter_faults(recs, None) if any(b11_line(r) for r in recs) else []",
     "    bad = []",
     ["chk_gate_counters_rule_vr5_in_sitting_c"]),
    ("V6 class B: an unprinted gate counter read as 0",
     '(valid is None or q["pt"] in valid) and q.get(k, 1) != 0]',
     '(valid is None or q["pt"] in valid) and q.get(k, 0) != 0]',
     ["chk_gate_counters_rule_vr5_in_sitting_c"]),
    ("V6 class B: this seat's arm file problems not in the complete sitting",
     "    bad = complete(recs) + raw_failure_events(text) + arm_problems(recs)",
     "    bad = complete(recs) + raw_failure_events(text)",
     ["chk_arm_problems_fail_the_complete_sitting", "chk_sitting_v_withholds_the_counter_and_controls"]),
    ("V6 class B: the peer seat's arm file problems not in the complete sitting",
     "                + arm_problems(peer_recs)]",
     "                ]",
     ["chk_arm_problems_fail_the_complete_sitting"]),
    # ruling R6-A3.11.151 (2) class D (F8, F9, F16)
    ("V6 F8: U_hi's percent of T_ref divides by a T_ref not above 0",
     '    return "%.3f percent" % (100 * u / t) if t > 0 else "not computable: T_ref %.1f us is not above 0" % t',
     '    return "%.3f percent" % (100 * u / t)',
     ["chk_reported_values_not_computable"]),
    ("V6 F8: R-GC's share divides by heap=0",
     '    elif v["heap"] <= 0:\n        share = ',
     '    elif False:\n        share = ',
     ["chk_reported_values_not_computable"]),
    ("V6 F8: R-GC's total read with an NA byte count",
     '    if v["bK_all"] is None:\n        tot = ',
     '    if False:\n        tot = ',
     ["chk_reported_values_not_computable"]),
    ("V6 F9: R-GC's total over the estimator's windows",
     "    bs = [_bytes_k(w) for w in meas]",
     '    bs = [_bytes_k(w) for w in meas if w["plant"] == 0 and w["res"] == 0]',
     ["chk_r_gc_total_reads_every_measured_window"]),
    ("V6 F9: R-GC's window count over the estimator's windows",
     '    v["bK_windows"] = len(meas)',
     '    v["bK_windows"] = len([w for w in meas if w["plant"] == 0 and w["res"] == 0])',
     ["chk_r_gc_total_reads_every_measured_window"]),
    ("V6 F16: the cross-check's residual statements not beside the interval",
     '        out += ["  " + x for x in CROSS_RISKS]\n        # the follow-up to ruling .149, D',
     "        # the follow-up to ruling .149, D",
     ["chk_cross_risks_beside_the_interval"]),
    # the integrator's points H, I and J
    ("H: the calibration entries failure form unknown",
     '    ("cal i=", r"cal i=-?\\d+ kind=disp entries failed:(?: .*)?", None),\n',
     "",
     ["chk_cal_entries_failure_form"]),
    ("I: window_faults indexes a window that lacks a key",
     '    gone = lacks_keys(w) if b11_line(w) else ["the B11 fields"]\n',
     "    gone = []\n",
     ["chk_malformed_lines_are_refusals"]),
    ("I: a pt of another form read",
     '        if not re.fullmatch(r"-?\\d+\\.\\d+\\.\\d+", rec["pt"]):\n            raise Refused(',
     "        if False:\n            raise Refused(",
     ["chk_malformed_lines_are_refusals"]),
    ("I: an e<H> value of another form read",
     '            if v.count(",") != 1:\n                raise Refused(',
     "            if False:\n                raise Refused(",
     ["chk_malformed_lines_are_refusals"]),
    ("J: a3 ref=NA admitted in a measuring build's log",
     '            gone = [] if ref_log else ["reads_win"]',
     "            gone = []",
     ["chk_reference_a3_form"]),
    ("J: a3 ref=NA refused in a reference log",
     '            gone = [] if ref_log else ["reads_win"]',
     '            gone = ["reads_win"]',
     ["chk_reference_a3_form"]),
    ("J: the reference a3 form without g read",
     '    ("a3", None, None, ("g",), "proof_records, a3"),\n',
     "",
     ["chk_reference_a3_form"]),
    # the integrator's follow-up to ruling .149, D: a reported value that cannot be computed never ends the verdict
    ("V6 R-WORK: a sitting-C u_g that cannot be computed ends the combining step",
     '        except NOT_COMPUTABLE as x:\n            ct = "not computable: %s" % x',
     '        except ZeroDivisionError as x:\n            ct = "not computable: %s" % x',
     ["chk_reported_lines_never_end_the_verdict"]),
    # ruling R6-A3.11.149 (8): --controls needs 0 unknown line forms and no "Failed to patch"
    ("V6 controls: unknown line forms do not fail the proof",
     "    ok = got == want and not scope and not unk\n",
     "    ok = got == want and not scope\n",
     ["chk_controls_forms_and_failed_to_patch"]),
    # ruling R6-A3.11.172: run and wi from 0 and the res mark, each as the build prints it (FtSchedule.OpenWindow), the
    # seat script's count line at 0 (frame_time_seat.ps1's step 4), and a window the closing frame opened without a
    # line (FtSchedule.cs:124, FtFrames.cs:136); the earlier readings are the first mutants
    ("B11 .172: the ordinal relation takes run and wi from 1 (the earlier reading)",
     'if w["run"] < 0 or w["wi"] != 4 * w["run"] + w["pos"] - 1:',
     'if w["run"] < 1 or w["wi"] != 4 * (w["run"] - 1) + w["pos"]:',
     ["chk_run_and_ordinal_count_from_zero"]),
    ("B11 .172: the ordinal relation dropped",
     'if w["run"] < 0 or w["wi"] != 4 * w["run"] + w["pos"] - 1:',
     'if w["run"] < 0:',
     ["chk_run_and_ordinal_count_from_zero"]),
    ("B11 .172: a point's ordinals taken from 1 (the earlier reading)",
     "if wis != list(range(len(bw))):",
     "if wis != list(range(1, len(bw) + 1)):",
     ["chk_run_and_ordinal_count_from_zero"]),
    ("B11 .172: a point's ordinals unchecked",
     "if wis != list(range(len(bw))):",
     "if False:",
     ["chk_run_and_ordinal_count_from_zero"]),
    ("B11 .172: res wanted only before an ordinary run (the earlier reading)",
     'and w["pos"] == 1 else 0',
     'and w["prun"] == 0 else 0',
     ["chk_res_marks_a_runs_first_window_after_a_plant_run_window"]),
    ("B11 .172: res wanted on every window after a plant-run window",
     ' and w["pos"] == 1 else 0',
     ' else 0',
     ["chk_res_marks_a_runs_first_window_after_a_plant_run_window"]),
    ("B11 .172: res never checked",
     '            if w["res"] != res and not (',
     '            if False and not (',
     ["chk_res_marks_a_runs_first_window_after_a_plant_run_window"]),
    ("B11 .172: res unchecked on every run's first window",
     'prev[1] is None and w["pos"] == 1):',
     'w["pos"] == 1):',
     ["chk_res_marks_a_runs_first_window_after_a_plant_run_window"]),
    ("B11 .172: an unprinted window is never read off live_frames",
     '// WINDOW_FRAMES == len(bw):',
     '// WINDOW_FRAMES == len(bw) + 99:',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: every point is taken to have opened one window more",
     ' and (lf - 2) // WINDOW_FRAMES == len(bw):',
     ':',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: the closing frame counted one frame early",
     '(lf - 2) // WINDOW_FRAMES',
     '(lf - 1) // WINDOW_FRAMES',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: a menu segment read as if the schedule had opened its windows",
     'if p["game"] >= 0 and isinstance(lf, int)',
     'if isinstance(lf, int)',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: a menu segment without a window line read as a point's window 0",
     'r["kind"] == "p" and r["game"] >= 0 and r["pt"] not in wins',
     'r["kind"] == "p" and r["pt"] not in wins',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: the mate read off the wrong window",
     'bw[-2]["arm"] == "OFF"',
     'bw[-1]["arm"] == "OFF"',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: the mate's own arm given to the unprinted window",
     '"ON" if bw[-2]["arm"] == "OFF" else "OFF"',
     '"OFF" if bw[-2]["arm"] == "OFF" else "ON"',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: position 3 taken as one the lines do not fix",
     'len(bw) % 4 < 2 else',
     'len(bw) % 4 < 3 else',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: position 2 read off a window that is not its mate",
     'len(bw) % 4 < 2 else',
     'len(bw) % 4 < 1 else',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: the forced arm not given to the unprinted window",
     'forced.get(bw[-1]["game"], mate)',
     'mate',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: the run's plant state dropped",
     'bw[-1]["prun"] if len(bw) % 4 else None)',
     'None)',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: the plant state of the run before given to a window that began a run",
     'bw[-1]["prun"] if len(bw) % 4 else None)',
     'bw[-1]["prun"])',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: a point without a window line is passed over",
     '                prev = (forced.get(g), None)\n',
     '                prev = prev\n',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: the forced arm not given to a point without a window line",
     'prev = (forced.get(g), None)',
     'prev = (None, None)',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: pred held to an arm the lines do not fix",
     'if (want is not None and w["pred"] != want) or (want is None and w["pred"] == "none"):',
     'if w["pred"] != want:',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: res held to a plant state the lines do not fix",
     ' and not (prev is not None and prev[1] is None and w["pos"] == 1):',
     ':',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("B11 .172: the unprinted window forgotten at the next window",
     'after.get(id(w), (w["arm"], w["prun"]))',
     '(w["arm"], w["prun"])',
     ["chk_an_opened_window_without_a_line_is_the_predecessor"]),
    ("ATTACH .172: the count line at 0 is a fault again",
     ' and ln.strip() != "slice class %s: 0 lines" % FAILED_PATCH:',
     ':',
     ["chk_attach_guard"]),
    ("ATTACH .172: every count line of the class passes",
     'ln.strip() != "slice class %s: 0 lines" % FAILED_PATCH:',
     'not ln.strip().startswith("slice class %s: " % FAILED_PATCH):',
     ["chk_attach_guard"]),
    ("ATTACH .172: the count line at 0 passes inside a longer line",
     'ln.strip() != "slice class %s: 0 lines" % FAILED_PATCH:',
     '("slice class %s: 0 lines" % FAILED_PATCH) not in ln:',
     ["chk_attach_guard"]),
    # ruling R6-A3.11.172 (5) a: the token level is held between two windows of one point (FtFrames.cs:346) and may
    # move between two points (FtFrames.cs:133, :161, :248); the earlier reading is the first mutant
    ("B11 .172 (5) a: the token level held across two points (the earlier reading)",
     'if last is not None and last["pt"] == w["pt"]:',
     'if last is not None:',
     ["chk_token_level_may_move_between_two_points"]),
    ("B11 .172 (5) a: the token level held between two points and not inside one",
     'if last is not None and last["pt"] == w["pt"]:',
     'if last is not None and last["pt"] != w["pt"]:',
     ["chk_token_level_may_move_between_two_points", "chk_token_open1_and_continuity"]),
    # ruling R6-A3.11.172 (5) b: VR2's spread reads the measured games; its callers pass their first game on
    ("VR2 .172 (5) b: the spread reads game 0 (the earlier reading)",
     'for r in sett if r["g"] >= first_game and r.get("f_hat", 0) > 0]',
     'for r in sett if r["g"] >= 0 and r.get("f_hat", 0) > 0]',
     ["chk_vr2_spread_reads_the_measured_games"]),
    ("VR2 .172 (5) b: the spread leaves the first measured game out",
     'for r in sett if r["g"] >= first_game and r.get("f_hat", 0) > 0]',
     'for r in sett if r["g"] > first_game and r.get("f_hat", 0) > 0]',
     ["chk_vr2_spread_reads_the_measured_games"]),
    ("VR2 .172 (5) b: the spread's limit at 20 percent",
     'if fh and (max(fh) - min(fh)) > 0.02 * min(fh):',
     'if fh and (max(fh) - min(fh)) > 0.2 * min(fh):',
     ["chk_vr2_spread_reads_the_measured_games"]),
    ("VR2 .172 (5) b: the validity set passes no first game on",
     'vr2(recs, LAST_GAME, first_game)',
     'vr2(recs, LAST_GAME)',
     ["chk_vr2_spread_reads_the_measured_games"]),
    ("VR2 .172 (5) b: sitting C's as-built line reads game 0",
     'ok2, why2 = vr2(recs, LAST_GAME, 1)',
     'ok2, why2 = vr2(recs, LAST_GAME)',
     ["chk_vr2_spread_reads_the_measured_games"]),
    # ruling R6-A3.11.172 (5) c: the completed sitting's own end line is no disarm of VR6; one mutant per condition
    ("VR6 .172 (5) c: no end line is exempt (the earlier reading)",
     'if r["kind"] == "disarmed" and (i in own) == end]',
     'if r["kind"] == "disarmed" and not end]',
     ["chk_the_completed_sittings_own_end_line"]),
    ("VR6 .172 (5) c: every disarm line is taken for the end line",
     'if r["kind"] == "disarmed" and (i in own) == end]',
     'if r["kind"] == "disarmed" and end]',
     ["chk_the_completed_sittings_own_end_line"]),
    ("VR6 .172 (5) c: the end line's input is not read",
     'if r["kind"] == "disarmed" and r.get("input") == "fighters"',
     'if r["kind"] == "disarmed"',
     ["chk_the_completed_sittings_own_end_line"]),
    ("VR6 .172 (5) c: the newest point line's pt is not read",
     '[(q["game"], q["pt"]) for q in recs[:i] if q["kind"] == "p"][-1:] == [(LAST_GAME, r.get("pt"))]',
     '[q["game"] for q in recs[:i] if q["kind"] == "p"][-1:] == [LAST_GAME]',
     ["chk_the_completed_sittings_own_end_line"]),
    ("VR6 .172 (5) c: the newest point line's game is not read",
     '[(q["game"], q["pt"]) for q in recs[:i] if q["kind"] == "p"][-1:] == [(LAST_GAME, r.get("pt"))]',
     '[q["pt"] for q in recs[:i] if q["kind"] == "p"][-1:] == [r.get("pt")]',
     ["chk_the_completed_sittings_own_end_line"]),
    ("VR6 .172 (5) c: any earlier point line stands for the newest",
     '[(q["game"], q["pt"]) for q in recs[:i] if q["kind"] == "p"][-1:] == [(LAST_GAME, r.get("pt"))]',
     '(LAST_GAME, r.get("pt")) in [(q["game"], q["pt"]) for q in recs[:i] if q["kind"] == "p"]',
     ["chk_the_completed_sittings_own_end_line"]),
    ("VR6 .172 (5) c: a point line after the end line is not looked for",
     'and not any(q["kind"] in ("p", "w") for q in recs[i:])',
     'and not any(q["kind"] in ("w",) for q in recs[i:])',
     ["chk_the_completed_sittings_own_end_line"]),
    ("VR6 .172 (5) c: a window line after the end line is not looked for",
     'and not any(q["kind"] in ("p", "w") for q in recs[i:])',
     'and not any(q["kind"] in ("p",) for q in recs[i:])',
     ["chk_the_completed_sittings_own_end_line"]),
    ("VR6 .172 (5) c: the sitting's completion line is not required",
     'and any(q["kind"] == "sitting" and q.get("g") == LAST_GAME for q in recs[i:])]',
     ']',
     ["chk_the_completed_sittings_own_end_line"]),
    ("VR6 .172 (5) c: the completion line may stand before the end line",
     'and any(q["kind"] == "sitting" and q.get("g") == LAST_GAME for q in recs[i:])]',
     'and any(q["kind"] == "sitting" and q.get("g") == LAST_GAME for q in recs)]',
     ["chk_the_completed_sittings_own_end_line"]),
    ("VR6 .172 (5) c: a completion line of another game stands for the sitting's",
     'and any(q["kind"] == "sitting" and q.get("g") == LAST_GAME for q in recs[i:])]',
     'and any(q["kind"] == "sitting" for q in recs[i:])]',
     ["chk_the_completed_sittings_own_end_line"]),
    ("V6 .173: a log with window lines read as one without them (a point's totals judged)",
     '    per_w = any(b11_line(r) for r in recs)',
     '    per_w = False',
     ["chk_a_points_totals_hold_both_arms"]),
    ("V6 .173: a log without window lines read as one that switches arms per window",
     '    per_w = any(b11_line(r) for r in recs)',
     '    per_w = True',
     ["chk_a_points_totals_hold_both_arms"]),
    ("V6 .173: a gated point's totals judged in a log that switches arms per window",
     'if not per_w and r["gate"] == 1 and (r["span_g"] or r["span_gn"] or r["on_calls"]):',
     'if r["gate"] == 1 and (r["span_g"] or r["span_gn"] or r["on_calls"]):',
     ["chk_a_points_totals_hold_both_arms"]),
    ("V6 .173: an open point's guarded returns judged in a log that switches arms per window",
     'if not per_w and r["gate"] == 0 and r["guarded"]:',
     'if r["gate"] == 0 and r["guarded"]:',
     ["chk_a_points_totals_hold_both_arms"]),
    # review .173 HIGH 1: the estimator's predecessor is the window opened before, printed or not (b11_terms reads
    # window_reconcile's map); pred=none after an opened window that printed no line is a miss
    ("B11 .174: the estimator takes the previous printed window",
     'if pw[3] else pw[2]',
     'if False else pw[2]',
     ["chk_an_unprinted_predecessor_gives_its_arm_and_coin_to_the_carryover"]),
    ("B11 .174: an unprinted predecessor takes the following window's own arm",
     'arm=w["pred"], run=o // 4,',
     'arm=w["arm"], run=o // 4,',
     ["chk_an_unprinted_predecessor_gives_its_arm_and_coin_to_the_carryover"]),
    ("B11 .174: an unprinted predecessor takes the printed window's ordinal",
     'else pw[2]["wi"] + 1',
     'else pw[2]["wi"]',
     ["chk_an_unprinted_predecessor_gives_its_arm_and_coin_to_the_carryover"]),
    ("B11 .174: an unprinted predecessor's run one too high",
     'run=o // 4,',
     'run=o // 4 + 1,',
     ["chk_an_unprinted_predecessor_gives_its_arm_and_coin_to_the_carryover"]),
    ("B11 .174: an unprinted predecessor's position shifted by one",
     'pos=o % 4 + 1,',
     'pos=(o + 1) % 4 + 1,',
     ["chk_an_unprinted_predecessor_gives_its_arm_and_coin_to_the_carryover"]),
    ("B11 .174: an unprinted predecessor's unit shifted by one position",
     'unit=UNIT_OF_POS[o % 4 + 1]',
     'unit=UNIT_OF_POS[(o + 1) % 4 + 1]',
     ["chk_an_unprinted_predecessor_gives_its_arm_and_coin_to_the_carryover"]),
    ("B11 .174: no predecessor marked as printing no line",
     'prev + (was, was["kind"] == "p" or id(was) in after)',
     'prev + (was, False)',
     ["chk_an_unprinted_predecessor_gives_its_arm_and_coin_to_the_carryover"]),
    ("B11 .174: only a point that printed no window marks its window 0",
     'prev + (was, was["kind"] == "p" or id(was) in after)',
     'prev + (was, was["kind"] == "p")',
     ["chk_an_unprinted_predecessor_gives_its_arm_and_coin_to_the_carryover"]),
    ("B11 .174: only a closing frame's window marks itself",
     'prev + (was, was["kind"] == "p" or id(was) in after)',
     'prev + (was, id(was) in after)',
     ["chk_an_unprinted_predecessor_gives_its_arm_and_coin_to_the_carryover"]),
    ("B11 .174: pred=none accepted after an opened window that printed no line",
     'if (want is not None and w["pred"] != want) or (want is None and w["pred"] == "none"):',
     'if want is not None and w["pred"] != want:',
     ["chk_pred_none_after_an_unprinted_window_is_a_miss"]),
    # review .173 HIGH 2: VR9 in a window log divides by the frames of the ON windows and weights by them
    ("VR9 .174: a window log's divisor takes both arms' window frames",
     'w["arm"] == "ON" and w["pt"] in pts',
     'w["pt"] in pts',
     ["chk_vr9_reads_on_window_frames_in_a_window_log"]),
    ("VR9 .174: the points read by first-window arm in a window log and all points without",
     'on = g[k] if ws else [q for q in g[k] if q["arm"] == "ON"]',
     'on = [q for q in g[k] if q["arm"] == "ON"] if ws else g[k]',
     ["chk_vr9_reads_on_window_frames_in_a_window_log"]),
    ("VR9 .174: the divisor choice inverted (live frames in a window log, window frames without)",
     'lf = (sum(w["n"] for w in ws if w["arm"] == "ON" and w["pt"] in pts) if ws\n                  else sum(q["live_frames"] for q in on))',
     'lf = sum(q["live_frames"] for q in on) if ws else sum(w["n"] for w in ws if w["arm"] == "ON" and w["pt"] in pts)',
     ["chk_vr9_reads_on_window_frames_in_a_window_log"]),
    ("VR9 .174: the weight choice inverted (point frames in a window log, the divisor without)",
     'lf if ws else sum(q["n"] for q in on)',
     'sum(q["n"] for q in on) if ws else lf',
     ["chk_vr9_reads_on_window_frames_in_a_window_log"]),
    ("VR9 .174: the weight the divisor in either log",
     'lf if ws else sum(q["n"] for q in on)',
     'lf if ws else lf',
     ["chk_vr9_reads_on_window_frames_in_a_window_log"]),
    # review .173 (report lines 5, 6, 7, 21): the new report texts, each removed
    ("VR9 .174: the floor sentence never printed",
     '"" if elo > 0 else " (e_C_lo %.4f is not above 0: floored at 1e-9, the bound binds nothing)" % elo)',
     '"")',
     ["chk_vr9_floor_sentence_when_e_c_lo_is_not_above_0"]),
    ("VR9 .174: the floor sentence printed when e_C_lo is above 0",
     '"" if elo > 0 else " (e_C_lo',
     '"" if elo <= 0 else " (e_C_lo',
     ["chk_vr9_floor_sentence_when_e_c_lo_is_not_above_0"]),
    ("U .174: the U line hides the floor",
     '/ min(1, max(e_C_lo %.4f, 1e-9)) + K_up',
     '/ min(1, e_C_lo %.4f) + K_up',
     ["chk_single_parse_texts_of_review_173"]),
    ("NOTE .174: the window log's NOTE not printed",
     'if any(b11_line(r) for r in recs):\n        out.append("NOTE window log',
     'if False:\n        out.append("NOTE window log',
     ["chk_single_parse_texts_of_review_173"]),
    ("NOTE .174: the NOTE printed without window lines",
     'if any(b11_line(r) for r in recs):\n        out.append("NOTE window log',
     'if True:\n        out.append("NOTE window log',
     ["chk_single_parse_texts_of_review_173"]),
    ("TWO-ARM .174: e_C's detail without its grouping",
     '(needs at least 0.5; OFF points by first-window arm)',
     '(needs at least 0.5)',
     ["chk_single_parse_texts_of_review_173"]),
    ("TWO-ARM .174: VR3's detail without its grouping",
     "(max %.3f; dC's points by first-window arm)",
     '(max %.3f)',
     ["chk_single_parse_texts_of_review_173"]),
    ("TWO-ARM .174: VR8's detail without its grouping",
     'after OFF %d; points by first-window arm)',
     'after OFF %d)',
     ["chk_single_parse_texts_of_review_173"]),
    ("BETWEEN .174: the between-point line in its earlier wording",
     '"between-point spans after points whose last measured window was ON %.1f us per transition over %d "',
     '"between-point spans after ON points %.1f us per transition over %d "',
     ["chk_single_parse_texts_of_review_173"]),
    # review .173 MEDIUMs (report lines 8 to 17): each condition its own removal or change
    ("B11 .174: a negative run accepted when wi follows from it",
     'if w["run"] < 0 or w["wi"] != 4 * w["run"] + w["pos"] - 1:',
     'if w["wi"] != 4 * w["run"] + w["pos"] - 1:',
     ["chk_a_negative_run_is_not_ordinal"]),
    ("B11 .174: no closing frame's window in game 0",
     'if p["game"] >= 0 and isinstance(lf, int)',
     'if p["game"] > 0 and isinstance(lf, int)',
     ["chk_unprinted_window_in_game_0_at_position_4_and_forced_off"]),
    ("B11 .174: game 0's point without a window stands for no window",
     '(r["kind"] == "p" and r["game"] >= 0 and r["pt"] not in wins)',
     '(r["kind"] == "p" and r["game"] > 0 and r["pt"] not in wins)',
     ["chk_unprinted_window_in_game_0_at_position_4_and_forced_off"]),
    ("B11 .174: position 4's arm not inferred from its mate",
     'mate = None if len(bw) % 4 < 2 else',
     'mate = None if len(bw) % 4 != 2 else',
     ["chk_unprinted_window_in_game_0_at_position_4_and_forced_off"]),
    ("B11 .174: force=OFF not read as a forced arm",
     'r.get("force") in ("ON", "OFF")',
     'r.get("force") in ("ON",)',
     ["chk_unprinted_window_in_game_0_at_position_4_and_forced_off"]),
    ("B11 .174: a point of one live frame stands for no window",
     '(r["kind"] == "p" and r["game"] >= 0 and r["pt"] not in wins)',
     '(r["kind"] == "p" and r["game"] >= 0 and r["pt"] not in wins and r.get("live_frames", 0) > 1)',
     ["chk_unprinted_window_boundaries_one_live_frame_and_partial"]),
    ("B11 .174: a partial terminal window read as filling its window",
     '(lf - 2) // WINDOW_FRAMES == len(bw)',
     '-(-(lf - 2) // WINDOW_FRAMES) == len(bw)',
     ["chk_unprinted_window_boundaries_one_live_frame_and_partial"]),
    ("B11 .174: an unknown predecessor arm kept past its successor",
     'last, prev = w, after.get(id(w), (w["arm"], w["prun"]))',
     'last, prev = w, after.get(id(w), (w["arm"] if prev is None or prev[0] else None, w["prun"]))',
     ["chk_the_relaxation_expires_after_one_successor"]),
    ("B11 .174: an unknown predecessor plant state kept past its successor",
     'last, prev = w, after.get(id(w), (w["arm"], w["prun"]))',
     'last, prev = w, after.get(id(w), (w["arm"], w["prun"] if prev is None or prev[1] is not None else None))',
     ["chk_the_relaxation_expires_after_one_successor"]),
    ("VR2 .174: validity_set reads the spread from game 1 whatever its first_game",
     '_guard(lambda: vr2(recs, LAST_GAME, first_game))',
     '_guard(lambda: vr2(recs, LAST_GAME, 1))',
     ["chk_vr2_caller_passes_a_first_game_other_than_1"]),
    ("B11 .174: res wanted after any window, plant run or not",
     'res = 1 if prev is not None and prev[1] == 1 and w["pos"] == 1 else 0',
     'res = 1 if prev is not None and w["pos"] == 1 else 0',
     ["chk_res_marks_a_runs_first_window_after_a_plant_run_window"]),
    ("ATTACH .174: the zero-count line compared unstripped",
     'and ln.strip() != "slice class %s: 0 lines" % FAILED_PATCH:',
     'and ln != "slice class %s: 0 lines" % FAILED_PATCH:',
     ["chk_attach_guard"]),
    ("VR2 .174: vr2's default spread from game 1",
     'def vr2(recs, last_game=None, first_game=0):',
     'def vr2(recs, last_game=None, first_game=1):',
     ["chk_vr2_spread_reads_the_measured_games"]),
    ("V6 .174: off_g not a gate counter",
     'GATE_COUNTERS = ("off_g", "off_gn", "off_on", "on_guarded")',
     'GATE_COUNTERS = ("off_gn", "off_on", "on_guarded")',
     ["chk_gate_counters_rule_vr5_in_sitting_c"]),
    ("V6 .174: off_gn not a gate counter",
     'GATE_COUNTERS = ("off_g", "off_gn", "off_on", "on_guarded")',
     'GATE_COUNTERS = ("off_g", "off_on", "on_guarded")',
     ["chk_gate_counters_rule_vr5_in_sitting_c"]),
    ("V6 .174: off_on not a gate counter",
     'GATE_COUNTERS = ("off_g", "off_gn", "off_on", "on_guarded")',
     'GATE_COUNTERS = ("off_g", "off_gn", "on_guarded")',
     ["chk_gate_counters_rule_vr5_in_sitting_c"]),
    ("V6 .174: on_guarded not a gate counter",
     'GATE_COUNTERS = ("off_g", "off_gn", "off_on", "on_guarded")',
     'GATE_COUNTERS = ("off_g", "off_gn", "off_on")',
     ["chk_gate_counters_rule_vr5_in_sitting_c"]),
    # review .174 HIGH (ruling R6-A3.11.175 (a), (b)): VR9's divisor counts each window's live frames by fact (ii)
    ("VR9 .175: the opening frame left out of window 0",
     'min(lf, WINDOW_FRAMES + 1) if j == 0',
     'min(lf - 1, WINDOW_FRAMES) if j == 0',
     ["chk_vr9_counts_a_points_opening_and_closing_frames", "chk_vr9_window_frames_by_live_frame"]),
    ("VR9 .175: the closing frame left out of every count",
     'lf, p = q["live_frames"], pr.get(q["pt"], {})',
     'lf, p = q["live_frames"] - 1, pr.get(q["pt"], {})',
     ["chk_vr9_counts_a_points_opening_and_closing_frames", "chk_vr9_window_frames_by_live_frame"]),
    ("VR9 .175: the window a closing frame opens never counted",
     'range(max(lf - 2, 0) // WINDOW_FRAMES + 1',
     'range(max(lf - 3, 0) // WINDOW_FRAMES + 1',
     ["chk_vr9_window_frames_by_live_frame", "chk_vr9_closing_window_arm_by_its_successor_and_its_mate"]),
    ("VR9 .175: window j's frames one too many",
     'min(lf - WINDOW_FRAMES * j - 1, WINDOW_FRAMES)',
     'min(lf - WINDOW_FRAMES * j, WINDOW_FRAMES)',
     ["chk_vr9_window_frames_by_live_frame"]),
    ("VR9 .175: a window log's weight taken from the points' n",
     'lf if ws else sum(q["n"] for q in on)',
     'sum(q["n"] for q in on) if ws else sum(q["n"] for q in on)',
     ["chk_vr9_window_frames_by_live_frame", "chk_vr9_reads_on_window_frames_in_a_window_log"]),
    ("VR9 .175: the successor's pred= not read for the closing frame's window",
     'nxt.get((q["pt"], j)) or m and (',
     'm and (',
     ["chk_vr9_closing_window_arm_by_its_successor_and_its_mate", "chk_vr9_window_frames_by_live_frame"]),
    ("VR9 .175: the mate's coin read without its complement",
     'm["coin"] ^ (j % 4 > 1)',
     'm["coin"]',
     ["chk_vr9_closing_window_arm_by_its_successor_and_its_mate", "chk_vr9_window_frames_by_live_frame"]),
    ("VR9 .175: the mate read off the window before",
     'm = p.get(j - 2) if j % 4 > 1 else None',
     'm = p.get(j - 1) if j % 4 > 1 else None',
     ["chk_vr9_closing_window_arm_by_its_successor_and_its_mate"]),
    ("VR9 .175: another window without a line read as one of unknown arm",
     'if j not in p and (p or j) and (j == 0 or lf != WINDOW_FRAMES * j + 2):',
     'if False:',
     ["chk_vr9_window_frames_by_live_frame"]),
    # ruling R6-A3.11.175 (c): unknown arms, ON and OFF in turn, the largest lower end judged, and the reports' text
    ("VR9 .175: an unknown arm always OFF",
     '"ON" if bits >> i & 1 else "OFF"',
     '"OFF"',
     ["chk_vr9_unknown_arms_take_the_largest_lower_end"]),
    ("VR9 .175: an unknown arm always ON",
     '"ON" if bits >> i & 1 else "OFF"',
     '"ON"',
     ["chk_vr9_unknown_arms_take_the_largest_lower_end"]),
    ("VR9 .175: the smallest lower end over the unknown arms",
     'max(lo, est - hw)',
     'min(lo, est - hw)',
     ["chk_vr9_unknown_arms_take_the_largest_lower_end"]),
    ("VR9 .175: thirteen unknown arms evaluated",
     'if len(u) > 12:',
     'if len(u) > 13:',
     ["chk_vr9_unknown_arms_take_the_largest_lower_end"]),
    ("VR9 .175: twelve unknown arms refused",
     'if len(u) > 12:',
     'if len(u) > 11:',
     ["chk_vr9_unknown_arms_take_the_largest_lower_end"]),
    ("VR9 .175: the unknown arms' text never given",
     '" (the largest over %d windows of unknown arm)" % len(u) if u else ""',
     '""',
     ["chk_vr9_unknown_arms_take_the_largest_lower_end", "chk_vr9_texts_name_the_windows_of_unknown_arm"]),
    ("VR9 .175: the single parse's VR9 line without the unknown arms' text",
     '% ("PASS" if vr["VR9"] else "FAIL", lo9, u9[0]))',
     '% ("PASS" if vr["VR9"] else "FAIL", lo9, ""))',
     ["chk_vr9_texts_name_the_windows_of_unknown_arm"]),
    ("VR9 .175: the TWO-ARM VR9 detail without the unknown arms' text",
     '% (lo, u[0], bound, (',
     '% (lo, "", bound, (',
     ["chk_vr9_texts_name_the_windows_of_unknown_arm"]),
    # review .174 MEDIUM 7: void rounds in neither side of VR9
    ("VR9 .175: the windows read off every point of the measured games, void rounds too",
     'vr9_windows(recs, [q for k in sorted(g) for q in g[k]])',
     'vr9_windows(recs, [r for r in recs if r["kind"] == "p" and r["game"] in g])',
     ["chk_vr9_leaves_void_rounds_out_of_both_sides"]),
    ("VR9 .175: the divisor over every point's ON windows",
     'w["arm"] == "ON" and w["pt"] in pts) if ws',
     'w["arm"] == "ON") if ws',
     ["chk_vr9_leaves_void_rounds_out_of_both_sides", "chk_vr9_window_frames_by_live_frame"]),
    ("VR9 .175: the numerator over the game's void rounds too",
     'on = g[k] if ws else',
     'on = [q for q in recs if q["kind"] == "p" and q["game"] == k] if ws else',
     ["chk_vr9_leaves_void_rounds_out_of_both_sides"]),
    # review .174 MEDIUM 2: the TWO-ARM VR9 detail when max(0, dC_up) is 0
    ("VR9 .175: the zero bound's sentence never printed",
     'if e["bu"] <= 0 else',
     'if False else',
     ["chk_vr9_floor_sentence_when_e_c_lo_is_not_above_0"]),
    ("VR9 .175: the zero bound's sentence only below 0",
     'if e["bu"] <= 0 else',
     'if e["bu"] < 0 else',
     ["chk_vr9_floor_sentence_when_e_c_lo_is_not_above_0"]),
    ("VR9 .175: the zero bound's sentence only when e_C_lo is above 0",
     'if e["bu"] <= 0 else',
     'if e["bu"] <= 0 and elo > 0 else',
     ["chk_vr9_floor_sentence_when_e_c_lo_is_not_above_0"]),
    # review .174 MEDIUM 3: the between line names the emitter's fallback (FtFrames.cs:246)
    ("between .175: the fallback for a point without a measured window not named",
     '(after OFF: %d, not used; a point without a measured window counts by its arm)',
     '(after OFF: %d, not used)',
     ["chk_single_parse_texts_of_review_173"]),
    # review .174 MEDIUM 5: the estimator's predecessor that printed no line, every shape
    ("B11 .175: the estimator takes the printed window before a position-3 window without a line",
     'if pw[3] else pw[2]',
     'if pw[3] and o % 4 != 2 else pw[2]',
     ["chk_the_carryover_reads_every_unprinted_predecessor_shape"]),
    ("B11 .175: the estimator reads a predecessor without a line before full windows only",
     'if pw[3] else pw[2]',
     'if pw[3] and w["partial"] == 0 else pw[2]',
     ["chk_the_carryover_reads_every_unprinted_predecessor_shape"]),
    ("B11 .175: game 0's closing-frame window not read off live_frames",
     'if p["game"] >= 0 and isinstance(lf, int)',
     'if p["game"] >= 1 and isinstance(lf, int)',
     ["chk_the_carryover_reads_every_unprinted_predecessor_shape"]),
    ("B11 .175: game 0's point without a window line not in the order",
     'r["kind"] == "p" and r["game"] >= 0 and r["pt"] not in wins',
     'r["kind"] == "p" and r["game"] >= 1 and r["pt"] not in wins',
     ["chk_the_carryover_reads_every_unprinted_predecessor_shape"]),
    # review .174 MEDIUM 6: pred=none accepted after one shape of an opened window without a line
    ("B11 .175: pred=none accepted after the closing frame's window at position 1",
     'if (want is not None and w["pred"] != want) or (want is None and w["pred"] == "none"):',
     'if (want is not None and w["pred"] != want) or (want is None and w["pred"] == "none" and not (was["kind"] == "w" and was["wi"] % 4 == 3)):',
     ["chk_pred_none_after_an_unprinted_window_is_a_miss"]),
    ("B11 .175: pred=none accepted after a point of one live frame",
     'if (want is not None and w["pred"] != want) or (want is None and w["pred"] == "none"):',
     'if (want is not None and w["pred"] != want) or (want is None and w["pred"] == "none" and not (was["kind"] == "p" and was["live_frames"] == 1)):',
     ["chk_pred_none_after_an_unprinted_window_is_a_miss"]),
]
MUTS += [r[:3] for r in B11_MUTS]

def _ids(test, *params):
    """Exact node ids of a parametrised test's cases (ruling R6-A3.11.95 (4)(f)): a kill names the cases its
    mutant's code reaches, never the bare name, which resolves to several ids and is refused."""
    return ["test_ft_parse.py::%s[%s]" % (test, p) for p in params]


ABS = "test_each_absent_record_fails_the_run"
DEL = "test_deleting_each_record_kind_withholds"
DEL_SITTING = "-sitting-_g16-^VERDICT B1 withheld: sitting incomplete"


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
    'match power not reported':
        ['test_report_carries_the_match_power_lines'],
    'match power margin dropped':
        ['test_match_power_reports_w_the_model_and_g_needed'],
    'menu e_C contains-1 upper end dropped':
        ['test_menu_check_fails_a_level_with_low_exposure'],
    'menu e_C excludes-0 dropped':
        ['test_menu_check_e_c_lo_bar_at_3_percent_only'],
    'menu e_C_lo bar dropped':
        ['test_menu_check_e_c_lo_bar_at_3_percent_only'],
    'menu e_C_lo bar at every level':
        ['test_menu_check_e_c_lo_bar_at_3_percent_only'],
    'menu level outside the pattern admitted':
        ['test_menu_check_names_a_level_outside_the_pattern'],
    'A3 left out of U':
        ['test_report_adds_a3_to_u'],
    'A3 per-game maximum replaced by the last game':
        ['test_a3_is_the_largest_per_game_window_rate_times_the_calibrated_difference'],
    'A3 missing line passes':
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
    'A3 zero row without its proof passes':
        ['test_a3_zero_row_without_its_proof_reference_fails_the_parse'],
    'A3 drained row without its probe passes':
        ['test_a3_zero_row_without_its_proof_reference_fails_the_parse'],
    'A3 drained starts not matched to the points':
        ['test_a3_drained_starts_equal_the_games_point_count'],
    'absent-record sweep left out of complete()':
        _ids(ABS, "flushed-kw0", "flushed-kw1", "between-kw2", "between-kw3", "heavy-kw4", "heavy-kw5", "offthread-kw6",
             "window-kw7", "refusals-kw8", "between-kw9", "answer_replay-kw10", "answer_replay-kw11", "counters-kw12",
             "counters-kw13"),
    'absent flushed line passes':
        _ids(ABS, "flushed-kw0", "flushed-kw1"),
    'absent between line passes':
        _ids(ABS, "between-kw2", "between-kw3", "between-kw9"),
    'absent heavy line passes the sweep':
        _ids(ABS, "heavy-kw4", "heavy-kw5"),
    'absent offthread line passes the sweep':
        _ids(ABS, "offthread-kw6"),
    'absent window line passes':
        _ids(ABS, "window-kw7"),
    'absent refusals line passes':
        _ids(ABS, "refusals-kw8"),
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
        ['test_a3_probe_proofs_need_their_records_and_contrary_ones_fail']
        + _ids(DEL, "a3zero-a3zero-_g16-probe:a3zero needs one a3zero line in game 16"),
    'contrary live writes for a zero row pass':
        ['test_a3_probe_proofs_need_their_records_and_contrary_ones_fail'],
    'probe:a3zero evidence not required':
        ['test_a3_probe_proofs_need_their_records_and_contrary_ones_fail']
        + _ids(DEL, "a3zero-a3zero-_g16-probe:a3zero needs one a3zero line in game 16"),
    'a3zero written count not checked':
        ['test_a3_probe_proofs_need_their_records_and_contrary_ones_fail'],
    'VR2 counters values not judged':
        ['test_vr2_judges_the_last_games_counters_and_every_point_stamp'],
    'VR2 absent counters line passes':
        ['test_vr2_judges_the_last_games_counters_and_every_point_stamp'],
    'VR2 point missing_end passes':
        ['test_vr2_judges_the_last_games_counters_and_every_point_stamp'],
    'absent answer_replay passes the sweep':
        _ids(ABS, "answer_replay-kw10", "answer_replay-kw11") + _ids(DEL, "answer_replay" + DEL_SITTING),
    'absent counters line passes the sweep':
        _ids(ABS, "counters-kw12", "counters-kw13") + _ids(DEL, "counters" + DEL_SITTING),
    'F18 does not guard B1':
        ['test_f18_failure_guards_b1'],
    'menu cycle calibrations not required':
        ['test_menu_check_needs_every_cycle_calibration_and_the_terminal_snapshot']
        + _ids(DEL, "cal-menu-<lambda>-menu"),
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
        ['test_live_row_planning_or_withheld_line_never_passes_as_executed', 'test_a3_row_withheld_by_the_build_withholds_b1',
         'test_live_marked_stand_in_line_is_refused_in_either_seat'],
    'M1: the live marker exempts its line from the stand-in fields (the round-5 branch)':
        ['test_live_marked_stand_in_line_is_refused_in_either_seat'],
    'M1: the failure field dropped from the stand-in predicate':
        ['test_live_marked_stand_in_line_is_refused_in_either_seat'],
    "M2: A3 reads one seat's log as both":
        ['test_peer_seat_live_lines_are_read_and_required'],
    "M2: report gives a verdict from one seat's log":
        ['test_peer_seat_live_lines_are_read_and_required'],
    'M2: report regains a bypass parameter':
        ['test_peer_seat_live_lines_are_read_and_required'],
    'R5: a dependent row keeps the retired scratch proof':
        ['test_a_dependent_row_is_calibrated_only_by_its_in_game_lines'],
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
    'live rows left out of A3':
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
    'menu failure unnamed':
        ['test_menu_check_names_an_entry_patch_that_did_not_attach'],
    'VR1 hold not required': ['test_vr1_flags_a_cap'],
    'VR1 other cap admitted': ['test_vr1_flags_a_cap'],
    'VR1 window the whole log': ['test_vr1_flags_a_cap'],
    'menu unplanted OFF segment unnamed': ['test_menu_check_names_an_off_segment_with_no_planted_window'],
    'menu frame rate hold not required': ['test_menu_framerate_c5_shape_fails_on_each_named_reason'],
    'menu frame rate hold order unchecked': ['test_menu_framerate_c5_shape_fails_on_each_named_reason'],
    'menu frame rate cap before the hold admitted': ['test_menu_framerate_c5_shape_fails_on_each_named_reason'],
    'menu frame rate cap after the hold admitted': ['test_menu_framerate_c5_shape_fails_on_each_named_reason'],
    'menu frame rate any cap line admitted as a release': ['test_menu_framerate_c5_shape_fails_on_each_named_reason'],
    'menu frame rate closing target unchecked': ['test_menu_framerate_c5_shape_fails_on_each_named_reason'],
    'menu frame rate segment floor dropped': ['test_menu_framerate_c5_shape_fails_on_each_named_reason'],
    'census summary not told apart': ['test_census_summary_is_its_own_kind_and_passes_beside_census_lines']
                                     + _ids("test_census_summary_failing_forms_fail_the_check", "registered_not_expected",
                                            "expected_not_derived", "missing_1", "duplicates_1", "two_lines")
                                     + ['test_census_summary_failure_withholds_the_verdicts_on_either_seat'],
    'read-time key test removed': _ids("test_record_lacking_a_required_key_is_a_named_refusal",
                                       "p_None_pt", "p_None_arm", "p_None_gate", "p_None_n", "p_None_sF", "p_None_sS",
                                       "p_None_sC", "p_None_maxF", "p_None_pn", "p_None_psF", "p_None_psS", "p_None_psC",
                                       "p_None_live_frames", "p_None_span_u", "p_None_pred", "p_None_span_g",
                                       "p_span_g_present_span_gn", "p_span_g_present_on_calls",
                                       "p_span_g_present_guarded", "p_t0_present_t1", "w_None_pt", "w_None_arm",
                                       "w_None_n", "w_None_sC", "w_partial_0_e4", "w_partial_0_e8", "w_partial_0_e16",
                                       "settled_None_g", "settled_None_freq", "settled_None_f_hat", "census_None_g",
                                       "census_None_entry", "census_None_shape", "census_None_on", "census_None_guarded",
                                       "census_summary_None_registered", "census_summary_None_expected",
                                       "census_summary_None_missing", "census_summary_None_duplicates", "cal_None_i",
                                       "cal_kind_disp_span__not_failed_shape", "cal_kind_disp_span__not_failed_n",
                                       "cal_kind_disp_span__not_failed_u", "cal_kind_disp_span__not_failed_p",
                                       "cal_kind_fhat__not_failed_f_hat", "cal_live_present_reads",
                                       "cal_live_present_scopes", "cal_live_present_ticks", "cal_live_present_tmax",
                                       "cal_live_present_unscoped", "cal_live_present_depth_err", "heavy_None_op",
                                       "heavy_None_at_call", "heavy_None_edge", "heavy_None_off", "heavy_None_live",
                                       "offthread_None_span_off", "offthread_None_hash_t0", "offthread_None_hash_t1",
                                       "plant_None_c_plant", "a3_None_g", "a3_None_reads_win", "answer_replay_None_g",
                                       "answer_replay_result_settled_ticks", "between_after_ON_ticks", "menu_None_seg",
                                       "menu_None_pair", "menu_None_arm", "menu_None_gate", "menu_c_plant_0_level")
                                  + ['test_census_line_without_g_is_a_named_refusal',
                                   'test_refusals_through_the_script_main_path'],
    'churn freeze not a failure event': ['test_failure_events_make_the_run_incomplete',
                                         'test_churn_freeze_failed_withholds_the_verdicts_and_its_trace_does_not'],
    'raw failures not read in the report': ['test_raw_failure_lines_withhold_the_verdicts_and_their_traces_do_not'],
    'raw failures not read in the menu check': ['test_raw_failure_lines_withhold_the_verdicts_and_their_traces_do_not'],
    'complete counts a failed calibration line': ['test_failed_cal_lines_are_skipped_by_the_calibration_consumers'],
    'D_up reads a failed disp line': ['test_failed_cal_lines_are_skipped_by_the_calibration_consumers'],
    'stamp estimate reads a failed span line': ['test_failed_cal_lines_are_skipped_by_the_calibration_consumers'],
    'menu cycle count reads a failed fhat line': ['test_failed_cal_lines_are_skipped_by_the_calibration_consumers'],
    'census summary missing not tested': _ids("test_census_summary_failing_forms_fail_the_check", "missing_1")
                                         + ['test_census_summary_failure_withholds_the_verdicts_on_either_seat'],
    'census summary non-integer accepted': ['test_census_summary_non_integer_value_fails_the_check'],
    'peer raw failures not read': _ids("test_a_failure_line_in_the_peer_log_alone_withholds_the_verdicts",
                                       "ft_room", "ft_gate"),
    'peer parsed failures not read': _ids("test_a_failure_line_in_the_peer_log_alone_withholds_the_verdicts", "churn"),
    'unreadable peer not withheld': ['test_an_unreadable_peer_log_withholds_the_verdicts'],
    'peer disarm ignored': ['test_a_disarm_in_the_peer_log_alone_fails_vr6'],
    'answer_replay g not required': _ids("test_every_fixture_key_dropped_ends_in_the_report_or_a_named_refusal",
                                         "answer_replay-g"),
    'p span_g not required': _ids("test_every_fixture_key_dropped_ends_in_the_report_or_a_named_refusal", "p-span_g"),
    'live calibration fields not required': _ids("test_a_live_calibration_line_lacking_a_field_is_refused_when_read",
                                                 "reads", "scopes", "ticks", "tmax", "unscoped", "depth_err"),
    'ATTACH list short of a source class': ['test_attach_lists_are_the_source_sets'],
    '--controls bare form not refused': ['test_v6_report_on_and_combine_through_the_script'],
}
KILLS.update((r[0], _ids("test_b11_check", *r[3])) for r in B11_MUTS)
t0 = open(os.path.join(src, "ft_parse.py"), encoding="utf-8", newline="").read()
DISCOVER = "--discover" in sys.argv[3:]
# each pytest run is capped at --cap=N seconds (default 3600); a run past it is a TIMEOUT verdict, never red
CAP = int(next((x.split("=", 1)[1] for x in sys.argv[3:] if x.startswith("--cap=")), "3600"))
# --stub-check proves the harness itself: stub rows against a stub suite instead of the parser's rows
STUB = "--stub-check" in sys.argv[3:]
STUB_FILE = "tools/frametime/test_harness_stub.py"
STUB_SRC = ("import sys\nimport time\n\nimport pytest\n\n"
            "SLEEP = 0\nFAIL = False\nBREAK = ''\nSETUP_BREAK = False\nTEARDOWN_BREAK = False\nCOLLECT_SLEEP = 0\n"
            "if COLLECT_SLEEP and '--collect-only' in sys.argv:\n    time.sleep(COLLECT_SLEEP)\n\n\n"
            "def test_stub_sleeps():\n    time.sleep(SLEEP)\n\n\n"
            "def test_stub_fails():\n    assert not FAIL, 'stub failure'\n\n\n"
            "def test_stub_named():\n    pass\n\n\n"
            "@pytest.mark.parametrize('case', ['a', 'b', 'c'])\n"
            "def test_stub_param(case):\n    assert case != BREAK, 'stub case broken'\n\n\n"
            "@pytest.fixture\ndef stub_teardown():\n    yield\n    if TEARDOWN_BREAK:\n"
            "        raise RuntimeError('stub teardown broke')\n\n\n"
            "@pytest.fixture\ndef stub_setup():\n    if SETUP_BREAK:\n        raise RuntimeError('stub setup broke')\n"
            "    yield\n\n\n"
            "def test_stub_teardown(stub_teardown):\n    assert not TEARDOWN_BREAK, 'stub failure'\n\n\n"
            "def test_stub_setup(stub_setup):\n    pass\n")
if "--stub-slow-collect" in sys.argv[3:]:
    # the baseline's whole-suite run is quick, its --collect-only sleeps past the cap (Codex PARSER-FIX-R2 MEDIUM)
    STUB_SRC = STUB_SRC.replace("COLLECT_SLEEP = 0", "COLLECT_SLEEP = 30")
SUITE = "test_harness_stub.py" if STUB else "test_ft_parse.py"
if STUB:
    _P = "test_harness_stub.py::test_stub_param[%s]"
    STUB_ROWS = [
        ("stub: sleeps past the cap", "\nSLEEP = 0\n", "\nSLEEP = 30\n", ["test_stub_sleeps"]),          # TIMEOUT
        ("stub: fails at once", "FAIL = False", "FAIL = True", ["test_stub_fails"]),                      # RED
        ("stub: its kill renamed away", "def test_stub_named():", "def test_stub_other():",
         ["test_stub_named"]),                                                                           # ERROR
        ("stub: one case broken, its id named", "BREAK = ''", "BREAK = 'b'", [_P % "b"]),                 # RED
        ("stub: one case broken, all three ids named", "BREAK = ''", "BREAK = 'b'",
         [_P % "a", _P % "b", _P % "c"]),                                                                # SURVIVED
        ("stub: an explicit node id", "FAIL = False", "FAIL = True",
         ["test_harness_stub.py::test_stub_fails"]),                                                     # RED
        ("stub: a failing kill with a teardown error", "TEARDOWN_BREAK = False", "TEARDOWN_BREAK = True",
         ["test_stub_teardown"]),                                                                        # ERROR
        ("stub: a setup error on a named kill", "SETUP_BREAK = False", "SETUP_BREAK = True",
         ["test_stub_setup"]),                                                                           # ERROR
    ]
    if "--stub-refuse" in sys.argv[3:]:
        # a kill the baseline never collects: its row is refused by name before any mutant runs
        STUB_ROWS.append(("stub: its kill never collected", "\nSLEEP = 0\n", "\nSLEEP = 0 \n", ["test_stub_absent"]))
    if "--stub-refuse-param" in sys.argv[3:]:
        # the bare name of a parametrised test maps to three ids: its row is refused by name
        STUB_ROWS.append(("stub: a parametrised test's bare name", "BREAK = ''", "BREAK = 'b'", ["test_stub_param"]))
    _only = next((x.split("=", 1)[1] for x in sys.argv[3:] if x.startswith("--stub-only=")), None)
    if _only:
        STUB_ROWS = [STUB_ROWS[int(n) - 1] for n in _only.split(",")]
    MUTS = [(n, a, b, STUB_FILE) for n, a, b, _ in STUB_ROWS]
    KILLS = {n: ks for n, _, _, ks in STUB_ROWS}
UNRELATED = ("FileNotFoundError", "ModuleNotFoundError", "ImportError", "No such file")
# Outcomes are read per exact node id and per phase from a record pytest writes (ruling R6-A3.11.95 (4)(c)), never
# from summary text: every copy carries this conftest.py, which appends one JSON row per collected node, per failed
# collector and per setup, call and teardown report to the file SCR_MUT_RECORD names.
RECORD_ENV = "SCR_MUT_RECORD"
RECORD_SRC = '''import json
import os

_PATH = os.environ.get("SCR_MUT_RECORD")


def _put(row):
    if _PATH:
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\\n")


def pytest_collection_finish(session):
    for item in session.items:
        _put({"collected": item.nodeid})


def pytest_collectreport(report):
    if report.failed:
        _put({"collect_error": report.nodeid})


def pytest_runtest_logreport(report):
    crash = getattr(report.longrepr, "reprcrash", None)
    _put({"node": report.nodeid, "when": report.when, "outcome": report.outcome,
          "xfail": hasattr(report, "wasxfail"), "msg": getattr(crash, "message", "") or ""})
'''


def make_copy(d):
    for rel in FIXTURES:
        p = os.path.join(d, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        shutil.copy(os.path.join(W, *rel.split("/")), p)
    td = os.path.join(d, "tools", "frametime")
    open(os.path.join(td, "conftest.py"), "w", encoding="utf-8", newline="").write(RECORD_SRC)
    if STUB:
        open(os.path.join(d, *STUB_FILE.split("/")), "w", encoding="utf-8", newline="").write(STUB_SRC)
    return td


def say(s):
    print(s, flush=True)


def pytest_run(td, args, tag):
    """One capped pytest run: (returncode or None past CAP seconds, stdout, the per-node record rows). The record is
    <copy>/record-<tag>.jsonl, beside the copy's tools folder, so no test reads it."""
    path = os.path.join(os.path.dirname(os.path.dirname(td)), "record-%s.jsonl" % tag)
    if os.path.exists(path):
        os.remove(path)
    env = dict(os.environ)
    env[RECORD_ENV] = path
    try:
        r = subprocess.run([sys.executable, "-I", "-B", "-u", "-m", "pytest", "-p", "no:cacheprovider"] + args,
                           cwd=td, capture_output=True, text=True, timeout=CAP, env=env)
        rc, out = r.returncode, r.stdout
    except subprocess.TimeoutExpired as e:
        rc = None
        out = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
    rows = []
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            try:
                rows.append(json.loads(ln))
            except ValueError:
                if rc is not None:
                    raise           # a torn row is possible only from a run stopped at the cap
    return rc, out, rows


def ident(nodeid):
    """Route 1 (Codex PARSER-FIX-R2 HIGH 1): a node is its exact id, parameter suffix kept."""
    return nodeid


def out_key(nodeid):
    """The key a record row is read under: the exact node id (route 1)."""
    return nodeid


def want_key(kill, nid):
    """The key a named kill is looked up under: its resolved exact node id (route 1)."""
    return nid


def failed_in_call(calls):
    """A named id is killed only when its one call report failed (route 1: one node, one outcome)."""
    return calls == ["failed"]


def read_outcomes(rows, out, ids):
    """Route 2 (Codex PARSER-FIX-R2 HIGH 2): each node's setup, call and teardown outcomes from the record, and every
    error in any phase: a failed collector, a failed setup or teardown, a skip, an xfail."""
    by, errs = {}, []
    for r in rows:
        if "collect_error" in r:
            errs.append("collection error in %s" % (r["collect_error"] or "(session)"))
        if "node" not in r:
            continue
        o = by.setdefault(out_key(r["node"]), {"setup": [], "call": [], "teardown": [], "xfail": False, "msg": []})
        o[r["when"]].append(r["outcome"])
        o["xfail"] = o["xfail"] or r["xfail"]
        if r["msg"]:
            o["msg"].append(r["msg"])
        if r["when"] != "call" and r["outcome"] == "failed":
            errs.append("error in %s of %s" % (r["when"], r["node"]))
        if r["outcome"] == "skipped":
            errs.append("%s skipped in %s" % (r["node"], r["when"]))
        if r["xfail"]:
            errs.append("%s xfailed in %s" % (r["node"], r["when"]))
    return by, errs


def last_line(out):
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def fail_baseline(line):
    say(line)
    say("PARSER MUTANTS FAIL (no green baseline)")
    sys.exit(1)


# mutant 0: the unchanged copy must be green, or no mutant below is evidence; it keeps the whole suite. GREEN is exit
# 0, every collected node passed in setup, call and teardown, no error in any phase, and its collection complete
d0 = os.path.join(OUT, "mut-0")
os.makedirs(d0, exist_ok=False)
td0 = make_copy(d0)
rc0, out0, rows0 = pytest_run(td0, [SUITE, "-q", "-rf"], "run")
if rc0 is None:
    fail_baseline("baseline (unchanged copy): TIMEOUT %ds (not proven green: control FAILED)" % CAP)
run_ids = [r["collected"] for r in rows0 if "collected" in r]
by0, errs0 = read_outcomes(rows0, out0, run_ids)
bad0 = list(errs0) + ([] if rc0 == 0 else ["pytest exit %d" % rc0]) + ([] if run_ids else ["no node collected"])
bad0 += ["%s did not pass (%s)" % (i, by0.get(out_key(i))) for i in run_ids
         if {p: v for p, v in by0.get(out_key(i), {}).items() if p in ("setup", "call", "teardown")}
         != {"setup": ["passed"], "call": ["passed"], "teardown": ["passed"]}]
# the listing every kill resolves against: the baseline's --collect-only, which must be the run's own collection
rcc, outc, rowsc = pytest_run(td0, [SUITE, "--collect-only", "-q"], "collect")
if rcc is None:
    fail_baseline("baseline collection (unchanged copy): TIMEOUT %ds (not proven complete: control FAILED)" % CAP)
listing = [r["collected"] for r in rowsc if "collected" in r]
_, errsc = read_outcomes(rowsc, outc, [])
bad0 += errsc + ([] if rcc == 0 else ["--collect-only exit %d" % rcc])
if sorted(listing) != sorted(run_ids):
    bad0.append("--collect-only lists %d ids, the run collected %d" % (len(listing), len(run_ids)))
if bad0:
    for why in bad0[:20]:
        say("  baseline problem: %s" % why)
    fail_baseline("baseline (unchanged copy): rc=%d %s -> RED (baseline FAILED, %d problems)"
                  % (rc0, last_line(out0), len(bad0)))
say("baseline (unchanged copy): rc=%d %s; %d nodes passed in every phase, collection complete -> GREEN"
    % (rc0, last_line(out0), len(run_ids)))
base_ids = {ident(i) for i in listing}


def resolve(k, name, kill):
    """(4)(a): an entry with "::" equals one listed id exactly; a bare name is the one id whose test it names
    (parameter suffix aside); zero ids or several refuse the table by row name before any mutant runs."""
    if "::" in kill:
        hits = sorted(i for i in base_ids if i == kill)
    else:
        hits = sorted(i for i in base_ids if i.split("::")[-1].split("[", 1)[0] == kill)
    if len(hits) != 1:
        sys.exit("REFUSED: mutant %d (%s) kill %s maps to %d node ids %s" % (k, name, kill, len(hits), hits[:6]))
    return hits[0]


bad = 0
jobs = []
for k, row in enumerate(MUTS, 1):
    name, a, b = row[:3]
    kills = KILLS.get(name, [])
    d = os.path.join(OUT, "mut-%d" % k)
    os.makedirs(d, exist_ok=False)
    td = make_copy(d)
    ids = [resolve(k, name, x) for x in kills]
    if len(row) == 4:
        if row[3] not in FIXTURES + ([STUB_FILE] if STUB else []):
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
    jobs.append((k, name, kills, td, d, ids))


def run_mutant(job):
    """(4)(b): a mutant's pytest gets exactly its resolved node ids, each first proven collected under the mutant
    (its own --collect-only record). A row with no kills (--discover) keeps the whole suite.
    Returns (not-collected ids, (rc or None, stdout, record rows))."""
    k, name, kills, td, d, ids = job
    if not ids:
        res = pytest_run(td, [SUITE, "-q", "-rf"], "run")
    else:
        rcc, outc, rowsc = pytest_run(td, [SUITE, "--collect-only", "-q"], "collect")
        if rcc is None:
            res = (None, outc, [])
        else:
            have = {ident(r["collected"]) for r in rowsc if "collected" in r}
            gone = [i for i in ids if i not in have]
            if gone:
                return gone, None
            res = pytest_run(td, ids + ["-q", "-rf"], "run")
    if res[0] is None:
        open(os.path.join(d, "timeout-stdout.txt"), "w", encoding="utf-8").write(res[1])
    return [], res


def verdict(kills, ids, rc, out, rows):
    """(4)(d), after TIMEOUT and KILL-NOT-COLLECTED: ERROR when a named id was skipped, xfailed or not run, when any
    node errored in any phase, when pytest's exit is neither 0 nor 1, or when a named failure is UNRELATED (a file or
    import failure); otherwise RED when every named id failed in its call phase; SURVIVED in every other case."""
    by, errs = read_outcomes(rows, out, ids)
    why = list(errs)
    if rc not in (0, 1):
        why.append("pytest exit %d is neither 0 nor 1" % rc)
    calls = []
    for kill, i in zip(kills, ids):
        o = by.get(want_key(kill, i))
        if not o or not o["call"]:
            why.append("%s not run" % i)
            continue
        calls.append(o["call"])
        if failed_in_call(o["call"]) and any(u in m for m in o["msg"] for u in UNRELATED):
            why.append("%s failed on an unrelated error: %s" % (i, o["msg"][-1]))
    if not ids:
        if not DISCOVER:
            why.append("no named kills")
        elif not any("failed" in o["call"] for o in by.values()):
            return "SURVIVED", "nothing failed"
    if why:
        return "ERROR", "; ".join(why[:6])
    if all(failed_in_call(c) for c in calls):
        return "RED", "every named id failed in its call phase"
    return "SURVIVED", "named ids whose call did not fail: %s" % [i for i, c in zip(ids, calls) if not failed_in_call(c)]


# the copies are independent directories, so their runs go side by side (--jobs N); results print in mutant order
import concurrent.futures  # noqa: E402
import time  # noqa: E402
JOBS = int(next((x.split("=", 1)[1] for x in sys.argv[3:] if x.startswith("--jobs=")), "1"))
results = {}
with concurrent.futures.ThreadPoolExecutor(max_workers=JOBS) as ex:
    futs = {ex.submit(run_mutant, j): j[0] for j in jobs}
    for f in concurrent.futures.as_completed(futs):
        results[futs[f]] = f.result()
        say("progress: mutant %d finished (%d/%d) at %s" % (futs[f], len(results), len(jobs),
                                                              time.strftime("%H:%M:%SZ", time.gmtime())))
count = dict.fromkeys(("RED", "SURVIVED", "TIMEOUT", "ERROR"), 0)
for (k, name, kills, td, d, ids) in jobs:
    gone, res = results[k]
    if gone:
        for i in gone:
            say("KILL-NOT-COLLECTED %s" % i)
        say("mutant %d (%s): -> ERROR (a named kill is not collected under the mutant: control FAILED)" % (k, name))
        count["ERROR"] += 1
        continue
    rc, out, rows = res
    if rc is None:
        say("mutant %d (%s): TIMEOUT %ds (not proven red: control FAILED)" % (k, name, CAP))
        say("  output read before the cap: %s; its last line: %s"
            % (os.path.join(d, "timeout-stdout.txt"), last_line(out)))
        count["TIMEOUT"] += 1
        continue
    v, why = verdict(kills, ids, rc, out, rows)
    say("mutant %d (%s): rc=%d %s; %d named ids -> %s (%s)%s" % (k, name, rc, last_line(out), len(ids), v, why,
                                                               "" if v == "RED" else ": control FAILED"))
    count[v] += 1
bad = len(jobs) - count["RED"]
say("PARSER MUTANTS %s (%d mutants: red %d, survived %d, TIMEOUT %d, ERROR %d; baseline green)"
    % ("PASS" if bad == 0 else "FAIL", len(jobs), count["RED"], count["SURVIVED"], count["TIMEOUT"], count["ERROR"]))
sys.exit(0 if bad == 0 else 1)
