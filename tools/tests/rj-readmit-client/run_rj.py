"""RJ readmission client lane (design V3): the harness runner.

Suites:
  apply   P1 twin run (T1.1, T1.2): the REAL ApplyManifestPick at the lane base
          and from the tree under test, extracted into one generated file and
          compiled against apply-trace/Stubs.cs; traces equal element by element.
  rules   the REAL plugin/FfaReadmitRules.cs under a plain compiler (P2 to P5
          rules: the offer record, the ledger, the grant, the digest, the
          tail, departure as death, registration, the readmit flows).

Mutants are planted into COPIES of the plugin files under the work folder (the
tracked files are never written). Each mutant must turn its target case red
and leave its control case green (#391). Exit 0 only when every baseline case
passes, every mutant is caught, every control holds and the tracked plugin
files are unchanged.

    python tools/tests/rj-readmit-client/run_rj.py --work <dir> [--suite apply|rules|all]
        [--only <mutant id>,...] [--overlay <dir>]

--overlay DIR: a file DIR/plugin/X is read in place of plugin/X (a piece
snapshot); its sha256 is printed so a log names exactly what ran.
"""
import argparse
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PLUGIN = os.path.join(REPO, "plugin")
BASE = "bf81f4fe"  # the lane base: the pre-split reducer is read from here
TRACKED = ["FfaMode.cs", "FfaReadmitRules.cs"]

APPLY_CASES = ["rolling", "local", "remote", "unknown", "quarantined", "nobody",
               "rolling_local", "throw_replay", "throw_apply", "throw_audit", "throw_rebuild",
               "bodiless", "bodiless_plain"]

# (id, suite, file, [(old, new), ...], target case, control case)
# Each old string occurs exactly once in the file it names.
MUTANTS = [
    # M1.1 publish cr_cards before the physical apply
    ("M1.1", "apply", "FfaMode.cs",
     [("            if (!bodiless) ApplyCardTo(player, prefab);\n",
       "            try { GameStateWatcher.RecordFfaLocalPick(cardName, RoundsTotalAll()); } catch { }\n"
       "            if (!bodiless) ApplyCardTo(player, prefab);\n")],
     "throw_apply", "unknown"),
    # M1.2 rewrite the deck before the replay
    ("M1.2", "apply", "FfaMode.cs",
     [("                if (!bodiless)\n                {\n                    deckViewRebuilds.Add(pid);\n",
       "                deck.Clear();\n                deck.AddRange(survivors);\n"
       "                if (!bodiless)\n                {\n                    deckViewRebuilds.Add(pid);\n")],
     "rolling", "remote"),
    # M1.3 run the logical statements when bodiless is false and there is no body
    ("M1.3", "apply", "FfaMode.cs",
     [("                Plugin.Log.LogWarning($\"[FFA] apply skipped — player {pid} gone (card {cardName})\");\n"
       "                yield break;\n",
       "                bodiless = true;\n")],
     "nobody", "rolling"),
    # M1.4 survivors as the first CardCap - 1 entries
    ("M1.4", "apply", "FfaReadmitRules.cs",
     [("plan.Survivors = deck.Skip(count - (cardCap - 1)).ToList();",
       "plan.Survivors = deck.Take(cardCap - 1).ToList();")],
     "rolling", "remote"),
]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def read_text(path):
    return open(path, "rb").read().decode("utf-8")


def source_path(name, overlay):
    if overlay:
        p = os.path.join(overlay, "plugin", name)
        if os.path.exists(p):
            return p
    return os.path.join(PLUGIN, name)


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


def gen_reducers(new_mode_text, out_dir):
    base = subprocess.run(["git", "-C", REPO, "show", BASE + ":plugin/FfaMode.cs"],
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


SUITES = {
    "apply": {"proj": os.path.join(HERE, "apply-trace", "ApplyTrace.csproj"), "cases": APPLY_CASES},
    "rules": {"proj": os.path.join(HERE, "rules", "RjRules.csproj"), "cases": None},
}


def prepare(suite, work, tag, texts):
    """Writes this variant's sources and builds it; returns the dll."""
    out = os.path.join(work, suite + "_" + tag)
    os.makedirs(out, exist_ok=True)
    rules = os.path.join(out, "FfaReadmitRules.cs")
    open(rules, "wb").write(texts["FfaReadmitRules.cs"].encode("utf-8"))
    props = {"RulesSource": rules}
    if suite == "apply":
        gen_reducers(texts["FfaMode.cs"], os.path.join(out, "gen"))
        props["GenDir"] = os.path.join(out, "gen")
    return build(SUITES[suite]["proj"], out, props)


def suite_cases(suite, dll):
    if SUITES[suite]["cases"] is not None:
        return SUITES[suite]["cases"]
    r = subprocess.run(["dotnet", dll, "--list"], capture_output=True, text=True)
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--suite", default="all")
    ap.add_argument("--only", default="")
    ap.add_argument("--overlay", default="")
    a = ap.parse_args()
    work = os.path.abspath(a.work)
    os.makedirs(work, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True).stdout
    print("commit", head)
    print("tree", "clean" if not status.strip() else "dirty:\n" + status.rstrip())
    srcs = {f: source_path(f, a.overlay) for f in TRACKED}
    for f in TRACKED:
        print("source %s sha256 %s%s" % (f, sha(srcs[f]), " (overlay)" if srcs[f] != os.path.join(PLUGIN, f) else ""))
    before = {f: sha(os.path.join(PLUGIN, f)) for f in TRACKED}
    texts = {f: read_text(srcs[f]) for f in TRACKED}
    suites = list(SUITES) if a.suite == "all" else a.suite.split(",")
    only = set(x for x in a.only.split(",") if x)
    ok = True
    for suite in suites:
        if not os.path.exists(SUITES[suite]["proj"]):
            print("SUITE %s: project absent" % suite)
            ok = False
            continue
        dll = prepare(suite, work, "base", texts)
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
        for mid, msuite, mfile, edits, target, control in MUTANTS:
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
            mdll = prepare(suite, work, "mut_" + mid.replace(".", "_"), mtexts)
            if mdll is None:
                print("BAD mutant %s: does not build" % mid)
                ok = False
                continue
            trc, tout = run_case(mdll, target)
            crc, cout = run_case(mdll, control)
            hit = trc != 0 and crc == 0
            caught += hit
            ok = ok and hit
            print("%s mutant %s: target %s=%s; control %s=%s" % (
                "CAUGHT" if hit else "MISSED", mid, target, "RED" if trc else "GREEN", control,
                "GREEN" if crc == 0 else "RED"))
            if trc:
                print("   " + "\n   ".join(tout.splitlines()[:4]))
            if not hit:
                print("   " + tout[-600:])
                print("   control: " + cout[-600:])
        print("suite %s: mutants %d of %d caught" % (suite, caught, total))
    unchanged = all(sha(os.path.join(PLUGIN, f)) == before[f] for f in TRACKED)
    print("tracked plugin files unchanged:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
