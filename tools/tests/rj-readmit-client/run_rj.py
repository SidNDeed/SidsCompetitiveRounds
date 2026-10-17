"""RJ readmission client lane (design V3): the harness runner.

Suites:
  apply   P1 twin run (T1.1, T1.2): the REAL ApplyManifestPick at the lane base
          and from the tree under test, extracted into one generated file and
          compiled against apply-trace/Stubs.cs; traces equal element by element.
  rules   the REAL plugin rule files (FfaReadmitRules.cs, FfaReportRules.cs,
          FfaLateRules.cs, FfaNumberingRules.cs) under a plain compiler: one
          named case per falsifiable sentence (rules/Cases*.cs).

Mutants are planted into COPIES of the plugin files under the work folder (the
tracked files are never written). Each mutant must turn its target case red
and leave its control case green (#391). Exit 0 only when every baseline case
passes, every mutant is caught, every control holds and the source files are
unchanged by the run.

    python tools/tests/rj-readmit-client/run_rj.py --work <dir>
        [--tree <dir>] [--wt <dir>] [--suite apply|rules|all] [--only <id>,...]

--tree DIR: the source tree to test (plugin/ and this folder), default the
repository holding this script. --wt DIR: the git worktree whose commit and
state head the log, default the tree. Every source file read is printed with
its sha256, so a log names exactly what ran.
"""
import argparse
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TREE = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BASE = "bf81f4fe"  # the lane base: the pre-split reducer is read from here
REL = os.path.join("tools", "tests", "rj-readmit-client")

APPLY_CASES = ["rolling", "local", "remote", "unknown", "quarantined", "nobody",
               "rolling_local", "throw_replay", "throw_apply", "throw_audit", "throw_rebuild",
               "bodiless", "bodiless_plain"]

# file -> MSBuild property naming its copy, per suite
SUITE_FILES = {
    "apply": {"FfaMode.cs": None, "FfaReadmitRules.cs": "RulesSource"},
    "rules": {"FfaReadmitRules.cs": "RulesSource", "FfaReportRules.cs": "ReportSource",
              "FfaLateRules.cs": "LateSource", "FfaReadmitEntryRules.cs": "EntrySource",
              "RosterCensusRules.cs": "CensusSource"},
}

# (id, piece, suite, file, [(old, new), ...], target case, control case)
# Each old string occurs exactly once in the file it names.
MUTANTS = [
    # ---- C1 (P1)
    ("M1.1", "C1", "apply", "FfaMode.cs",
     [("            if (!bodiless) ApplyCardTo(player, prefab);\n",
       "            try { GameStateWatcher.RecordFfaLocalPick(cardName, RoundsTotalAll()); } catch { }\n"
       "            if (!bodiless) ApplyCardTo(player, prefab);\n")],
     "throw_apply", "unknown"),
    ("M1.2", "C1", "apply", "FfaMode.cs",
     [("                if (!bodiless)\n                {\n                    deckViewRebuilds.Add(pid);\n",
       "                deck.Clear();\n                deck.AddRange(survivors);\n"
       "                if (!bodiless)\n                {\n                    deckViewRebuilds.Add(pid);\n")],
     "rolling", "remote"),
    ("M1.3", "C1", "apply", "FfaMode.cs",
     [("                Plugin.Log.LogWarning($\"[FFA] apply skipped — player {pid} gone (card {cardName})\");\n"
       "                yield break;\n",
       "                bodiless = true;\n")],
     "nobody", "rolling"),
    ("M1.4", "C1", "apply", "FfaReadmitRules.cs",
     [("plan.Survivors = deck.Skip(count - (cardCap - 1)).ToList();",
       "plan.Survivors = deck.Take(cardCap - 1).ToList();")],
     "rolling", "remote"),
    # ---- C2 (P2)
    ("M2.1", "C2", "rules", "FfaReadmitRules.cs",
     [("                string first = held.FirstOf(pid);\n",
       "                var l1 = held.ListOf(pid);\n                string first = l1 != null && l1.Count > 1 ? l1[1] : null;\n")],
     "C2.T2.1.twin_rule_s_ledger", "C2.T2.3.opening_draw_raw_entry"),
    ("M2.2", "C2", "rules", "FfaReadmitRules.cs",
     [("(seq.UsedNoRepeatFold.Contains(cn) || ledger.Contains(cn))",
       "(seq.UsedNoRepeatFold.Contains(cn) || new HashSet<string>().Contains(cn))")],
     "C2.T2.2.ledger_substitute_never_reoffered", "C2.T2.3.opening_draw_raw_entry"),
    ("M2.3", "C2", "rules", "FfaReadmitRules.cs",
     [("                            if (pool.NoRepeat.Contains(sub.Name)) ledger.Add(sub.Name);\n", ""),
      ("        internal static void NoteApplied(SpendState spend, int pid, string card)\n        {\n",
       "        internal static void NoteApplied(SpendState spend, int pid, string card)\n        {\n"
       "            if (!spend.Ledger.Contains(card)) spend.Ledger.Add(card);\n")],
     "C2.T2.2.ledger_substitute_never_reoffered", "C2.T2.3.opening_draw_raw_entry"),
    ("M2.4", "C2", "rules", "FfaReadmitRules.cs",
     [("bool openingDraw = k <= seq.OpeningDraws;", "bool openingDraw = false;")],
     "C2.T2.3.opening_draw_raw_entry", "C2.T2.2.ledger_substitute_never_reoffered"),
    ("M2.5", "C2", "rules", "FfaReadmitRules.cs",
     [("                if (got.ContainsKey(pid)) continue;\n                string first",
       "                if (view.HasKeptBody(pid)) continue;\n                string first")],
     "C2.T2.4.walk_seat_leaves", "C2.T2.1.twin_rule_s_ledger"),
    ("M2.6", "C2", "rules", "FfaReadmitRules.cs",
     [("                if (got.ContainsKey(pid)) continue;\n                string first",
       "                if (got.ContainsKey(pid) || view.HasKeptBody(pid)) continue;\n                string first")],
     "C2.T2.5.present_missed_gets_entry0", "C2.T2.4.walk_seat_leaves"),
    ("M2.7", "C2", "rules", "FfaReadmitRules.cs",
     [("return v != null && v.Pin != null && v.Pin.Flag && !string.IsNullOrEmpty(v.Room) && v.Room == v.Pin.Room;",
       "return v != null && v.PresentAllAdvertise();")],
     "C2.T2.6.gate_pinned_at_lock", "C2.T2.1.twin_rule_s_ledger"),
    ("M2.8", "C2", "rules", "FfaReadmitRules.cs",
     [("        internal static FfaOfferRecord AfterAudit(FfaOfferRecord published, FfaOfferRecord recomputed)\n"
       "        {\n            return published;\n",
       "        internal static FfaOfferRecord AfterAudit(FfaOfferRecord published, FfaOfferRecord recomputed)\n"
       "        {\n            return recomputed ?? published;\n")],
     "C2.T2.7.master_mutation_audited", "C2.T2.1.twin_rule_s_ledger"),
    # ---- C3 (P3 client half)
    ("M3.5", "C3", "rules", "FfaReportRules.cs",
     [("            if (readmitLobby) return localSid;\n", "")],
     "C3.T3.2.lag_publication_lost_both_file", "C3.T3.6.flag_false_matrix_equals_base"),
    # ---- C4 (P4 client half)
    ("M4.12", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("return new FfaLateRules.EpochEntry(slot, actor, k, game < 0 ? -1 : game, 2,",
       "return new FfaLateRules.EpochEntry(slot, actor, 'l', -1, 2,")],
     "C4.T4.5.epoch_v2_parsed_with_kind_and_game", "C4.T4.5.every_refusal_reason_mapped"),
    ("M4.15", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("return TokenMatches(senderRdt, r) ? LateReq.Accept : LateReq.RefuseToken;",
       "return LateReq.Accept;")],
     "C4.T4.6.token_checked_at_master", "C4.T4.6.identity_duplicate_refused"),
    ("M4.16", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("            return r.Actor != actor;\n", "            return null;\n")],
     "C4.T4.6.identity_duplicate_refused", "C4.T4.6.token_checked_at_master"),
    ("M4.17", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("            if (readmitLobby && rosterCount > 0) return rosterCount;\n", "")],
     "C4.T4.7.held_highest_slot_carried", "C4.T4.11.three_way_game_agreement"),
    ("M4.18", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("            if (readmitLobby && rosterCount > 0)\n            {\n                for (int s = 0;",
       "            if (false && readmitLobby && rosterCount > 0)\n            {\n                for (int s = 0;")],
     "C4.T4.8.each_mutation_fails_the_gate", "C4.T4.11.three_way_game_agreement"),
    ("M4.19", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("if (!v.VictimPresent || v.VictimDead", "if (v.VictimPresent || v.VictimDead")],
     "C4.T4.9.departure_credits_exactly_staying", "C4.T4.11.three_way_game_agreement"),
    ("M4.20", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("            return at;\n", "            return newId;\n")],
     "C4.T4.10.same_position_any_purge_timing", "C4.T4.11.three_way_game_agreement"),
    ("M4.21", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("return tailGame > 0 && tailGame == serverGame && tailGame == cycGame;", "return tailGame > 0;")],
     "C4.T4.11.three_way_game_agreement", "C4.T4.10.same_position_any_purge_timing"),
    ("M4.22", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("            return readmitLobby;\n", "            return false;\n")],
     "C4.T4.12.kind_r_grant_releases_latch", "C4.T4.11.three_way_game_agreement"),
    # ---- C5 (P5 client rungs of the positive ladder)
    ("M5.c1", "C5", "rules", "FfaReadmitEntryRules.cs",
     [("            if (after == before) return null;\n", "")],
     "C5.T5.ladder_repeats_add_no_line", "C5.T5.ladder_each_rung_once_in_order"),
    ("M5.c2", "C5", "rules", "FfaReadmitEntryRules.cs",
     [("if (selfKept) return after == RdmState.Admitted || after == RdmState.Entered ? \"entered\" : null;",
       "if (selfKept) return \"entered\";")],
     "C5.T4.13.flag_false_no_rung", "C5.T5.ladder_each_rung_once_in_order"),
    ("M5.c3", "C5", "rules", "FfaReadmitEntryRules.cs",
     [("                case RdmState.Admitted: return \"bound\";\n", "                case RdmState.Binding: return \"bound\";\n")],
     "C5.T5.ladder_each_rung_once_in_order", "C5.T4.13.flag_false_no_rung"),
    # ---- C4z (P4.6 the capability flip)
    ("M4z.1", "C4z", "rules", "FfaReadmitEntryRules.cs",
     [('            if (asm && adm) return asmToken + "," + admToken + "," + RdmCapsToken;\n',
       '            if (asm && adm) return asmToken + "," + admToken;\n')],
     "C4z.T4.6.adm_sends_all_three", "C4z.T4.6.asm_alone_no_rdm"),
    ("M4z.2", "C4z", "rules", "FfaReadmitEntryRules.cs",
     [('            if (asm) return asmToken;\n',
       '            if (asm) return asmToken + "," + RdmCapsToken;\n')],
     "C4z.T4.6.asm_alone_no_rdm", "C4z.T4.6.adm_sends_all_three"),
    ("M4z.3", "C4z", "rules", "FfaReadmitEntryRules.cs",
     [('        internal const string RdmCapsToken = "ffa_rdm1";\n',
       '        internal const string RdmCapsToken = "ffa_rdm0";\n')],
     "C4z.T4.6.adm_sends_all_three", "C4z.T4.6.asm_alone_no_rdm"),
]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def read_text(path):
    return open(path, "rb").read().decode("utf-8")


def extract(text, sig):
    """The member whose declaration line starts with sig, through the first
    following line that is exactly the class-member closing brace."""
    lines = text.splitlines(keepends=True)
    starts = [i for i, l in enumerate(lines) if l.lstrip().startswith(sig)]
    if len(starts) != 1:
        raise RuntimeError("signature %r occurs %d times" % (sig, len(starts)))
    s = starts[0]
    for j in range(s + 1, len(lines)):
        if lines[j].rstrip("\r\n") == "        }":
            return "".join(lines[s:j + 1])
    raise RuntimeError("no end for %r" % sig)


def gen_reducers(wt, new_mode_text, out_dir):
    base = subprocess.run(["git", "-C", wt, "show", BASE + ":plugin/FfaMode.cs"],
                          capture_output=True).stdout.decode("utf-8")
    if not base:
        raise RuntimeError("cannot read the base reducer at " + BASE)
    amp = "private static IEnumerator ApplyManifestPick("
    rc = "private static CardInfo ResolveCard("
    rd = "private static string RosterDisplayName("
    parts = [
        "using System;\nusing System.Collections;\nusing System.Collections.Generic;\nusing System.Linq;\n\n",
        "namespace CompetitiveRounds\n{\n",
        "    internal sealed class OldReducer : ReducerBase\n    {\n",
        "        internal static IEnumerator Run(int pid, string card, int cycle, bool bodiless) "
        "{ return ApplyManifestPick(pid, card, cycle); }\n\n",
        extract(base, amp), "\n", extract(base, rc), "\n    }\n\n",
        "    internal sealed class NewReducer : ReducerBase\n    {\n",
        "        internal static IEnumerator Run(int pid, string card, int cycle, bool bodiless) "
        "{ return ApplyManifestPick(pid, card, cycle, bodiless); }\n\n",
        extract(new_mode_text, amp), "\n", extract(new_mode_text, rc), "\n", extract(new_mode_text, rd),
        "\n    }\n}\n",
    ]
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, "Reducers.cs"), "wb").write("".join(parts).encode("utf-8"))


def build(proj, out, props):
    cmd = ["dotnet", "build", proj, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep]
    cmd += ["-p:%s=%s" % kv for kv in props.items()]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-6000:], r.stderr[-2000:])
        return None
    name = os.path.splitext(os.path.basename(proj))[0]
    return os.path.join(out, "bin", name + ".dll")


def run_case(dll, case):
    r = subprocess.run(["dotnet", dll, case], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def project(tree, suite):
    return os.path.join(tree, REL, {"apply": os.path.join("apply-trace", "ApplyTrace.csproj"),
                                    "rules": os.path.join("rules", "RjRules.csproj")}[suite])


def prepare(tree, wt, suite, work, tag, texts):
    """Writes this variant's copies and builds it; returns the dll."""
    out = os.path.join(work, suite + "_" + tag)
    os.makedirs(out, exist_ok=True)
    props = {}
    for f, prop in SUITE_FILES[suite].items():
        if prop is None:
            continue
        p = os.path.join(out, f)
        open(p, "wb").write(texts[f].encode("utf-8"))
        props[prop] = p
    if suite == "apply":
        gen_reducers(wt, texts["FfaMode.cs"], os.path.join(out, "gen"))
        props["GenDir"] = os.path.join(out, "gen")
    return build(project(tree, suite), out, props)


def suite_cases(suite, dll):
    if suite == "apply":
        return APPLY_CASES
    r = subprocess.run(["dotnet", dll, "--list"], capture_output=True, text=True)
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--tree", default=DEFAULT_TREE)
    ap.add_argument("--wt", default="")
    ap.add_argument("--suite", default="all")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    tree = os.path.abspath(a.tree)
    wt = os.path.abspath(a.wt) if a.wt else tree
    work = os.path.abspath(a.work)
    os.makedirs(work, exist_ok=True)
    head = subprocess.run(["git", "-C", wt, "log", "--oneline", "-1"], capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", wt, "status", "--porcelain"], capture_output=True, text=True).stdout
    print("worktree", wt)
    print("commit", head)
    print("worktree state", "clean" if not status.strip() else "dirty:\n" + status.rstrip())
    print("tree under test", tree)
    files = sorted(set(f for s in SUITE_FILES.values() for f in s))
    srcs = {f: os.path.join(tree, "plugin", f) for f in files}
    for f in files:
        print("source plugin/%s sha256 %s" % (f, sha(srcs[f])))
    for root, _, names in sorted(os.walk(os.path.join(tree, REL))):
        for n in sorted(names):
            if n.endswith((".cs", ".csproj", ".py")) and os.sep + "bin" not in root and os.sep + "obj" not in root:
                p = os.path.join(root, n)
                print("source %s sha256 %s" % (os.path.relpath(p, tree).replace(os.sep, "/"), sha(p)))
    before = {f: sha(srcs[f]) for f in files}
    texts = {f: read_text(srcs[f]) for f in files}
    suites = ["apply", "rules"] if a.suite == "all" else a.suite.split(",")
    only = set(x for x in a.only.split(",") if x)
    ok = True
    for suite in suites:
        dll = prepare(tree, wt, suite, work, "base", texts)
        if dll is None:
            print("BUILD FAILED (%s base)" % suite)
            ok = False
            continue
        cases = suite_cases(suite, dll)
        passed = 0
        for case in cases:
            rc, out = run_case(dll, case)
            print(out)
            passed += rc == 0
            ok = ok and rc == 0
        print("suite %s: %d of %d cases pass" % (suite, passed, len(cases)))
        if not cases:
            ok = False
        caught = total = 0
        for mid, piece, msuite, mfile, edits, target, control in MUTANTS:
            if msuite != suite or (only and mid not in only):
                continue
            total += 1
            raw = texts[mfile]
            nl = "\r\n" if "\r\n" in raw else "\n"
            text = raw
            good = True
            for old, new in edits:
                o, n = old.replace("\n", nl), new.replace("\n", nl)
                count = text.count(o)
                if count != 1:
                    print("BAD mutant %s: anchor occurs %d times" % (mid, count))
                    good = False
                    break
                text = text.replace(o, n)
            if not good:
                ok = False
                continue
            mtexts = dict(texts)
            mtexts[mfile] = text
            mdll = prepare(tree, wt, suite, work, "mut_" + mid.replace(".", "_"), mtexts)
            if mdll is None:
                print("BAD mutant %s: does not build" % mid)
                ok = False
                continue
            trc, tout = run_case(mdll, target)
            crc, cout = run_case(mdll, control)
            hit = trc != 0 and crc == 0
            caught += hit
            ok = ok and hit
            print("%s mutant %s (%s): target %s=%s; control %s=%s" % (
                "CAUGHT" if hit else "MISSED", mid, piece, target, "RED" if trc else "GREEN", control,
                "GREEN" if crc == 0 else "RED"))
            if trc:
                print("   " + "\n   ".join(tout.splitlines()[:4]))
            if not hit:
                print("   " + tout[-600:])
                print("   control: " + cout[-600:])
        print("suite %s: mutants %d of %d caught" % (suite, caught, total))
    unchanged = all(sha(srcs[f]) == before[f] for f in files)
    print("source plugin files unchanged by the run:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
