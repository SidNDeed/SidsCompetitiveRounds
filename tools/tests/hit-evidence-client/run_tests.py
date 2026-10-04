"""Item D harness: build the cases over the REAL plugin/HitEvidenceCore.cs
(and, since merge pass 5, plugin/PeerBuildCore.cs: case peer), run them, then
build mutated COPIES (work/, CoreSource / PeerSource override -- the tracked
files are never written) and require each mutant's target case to FAIL and its
control case to PASS. Exit 0 only when everything holds.

    python tools/tests/hit-evidence-client/run_tests.py
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PROJ = os.path.join(HERE, "HitEvidenceTests.csproj")
CORE = os.path.join(REPO, "plugin", "HitEvidenceCore.cs")
WORK = os.path.join(HERE, "work")

# (name, old text, new text, target case, control case). Each old text must
# occur exactly once in the shipped file.
MUTANTS = [
    ("bucket_window_inclusive", "if (sinceBlock < BLOCK_WINDOW_S) return", "if (sinceBlock <= BLOCK_WINDOW_S) return", "bucket", "pair"),
    ("bucket_never_dropped", "if (!blockedThisPoint) return BlockBucket.Never;", "", "bucket", "impacts"),
    ("pair_window_exclusive", "if (Math.Abs(d - f) <= window)", "if (Math.Abs(d - f) < window)", "pair", "bucket"),
    ("pair_tail_lost", "damageAlone += damage.Count - i;", "", "pair", "tally"),
    ("impact_no_dedup", "if (Hit.Contains(projectile)) return;", "", "impacts", "bucket"),
    ("impact_blocked_consumes", "if (blocked) { ImpactsBlocked++; return; }",
     "if (blocked) { ImpactsBlocked++; Hit.Add(projectile); return; }", "impacts", "pair"),
    ("tally_cap_silent", "else Unchecked++;\n            }\n\n            internal void AddForce",
     "\n            }\n\n            internal void AddForce", "tally", "bucket"),
    # merge pass 6: G1-L1 (a duplicate or refused point broadcast ends no point), G1-L2 (the FFA game end)
    ("pointgate_ignores_transitioning", "return ranOriginal && !vanillaWasTransitioning;", "return ranOriginal;", "pointgate", "gamegate"),
    ("pointgate_ffa_any_call", "if (ffaTakenAfter != ffaTakenBefore) return true;", "if (ffaTakenAfter >= ffaTakenBefore) return true;",
     "pointgate", "gamegate"),
    ("pointgate_spectator_any_call", "if (observedAfter != observedBefore) return true;",
     "if (observedAfter >= observedBefore) return true;", "pointgate", "gamegate"),
    ("gamegate_ffa_reads_vanilla_rounds", "if (ffaEngine) return ffaGameOver;", "", "gamegate", "pointgate"),
]

# Merge pass 5: mutants of plugin/PeerBuildCore.cs (the [PEER-BUILD] line),
# same shape, built through the PeerSource override.
PEER = os.path.join(REPO, "plugin", "PeerBuildCore.cs")
PEER_MUTANTS = [
    ("peer_prints_every_value", "sb.Append(' ').Append(Values(props));",
     "sb.Append(' ').Append(Values(props)); foreach (var kv in props ?? new Dictionary<string, string>()) sb.Append(' ').Append(kv.Value);",
     "peer", "lines"),
    ("peer_no_none_fact", "ours > 0 ? ours.ToString(System.Globalization.CultureInfo.InvariantCulture) : \"none\"",
     "ours.ToString(System.Globalization.CultureInfo.InvariantCulture)", "peer", "lines"),
    ("peer_build_value_dropped", "BuildProp, \"cr_dc2\"", "\"cr_dc2\"", "peer", "lines"),
    # merge pass 6: R-L1 (a capability value dropped) and R-L2 (keys left out, long keys merged)
    ("peer_game_token_cap_dropped", "\"cr_game_token_v\", ", "", "peer", "lines"),
    ("peer_continuation_dropped", "for (int l = 1; l < lines; l++)", "for (int l = 1; l < 1; l++)", "peer", "lines"),
    ("peer_long_key_unhashed", "if (masked || s.Length > MAX_KEY)\n", "if (masked)\n", "peer", "lines"),
]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def build(tag, core, peer=None):
    out = os.path.join(WORK, tag)
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep,
           "-p:CoreSource=" + core, "-p:PeerSource=" + (peer or PEER)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-2000:])
        return None
    return os.path.join(out, "bin", "HitEvidenceTests.dll")


def run(dll, cases=()):
    r = subprocess.run(["dotnet", dll] + list(cases), capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def main():
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("commit", head)
    before = sha(CORE)
    before_peer = sha(PEER)
    print("plugin/HitEvidenceCore.cs sha256", before)
    print("plugin/PeerBuildCore.cs sha256", before_peer)
    ok = True

    dll = build("base", CORE)
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    rc, out = run(dll)
    print(out)
    ok = ok and rc == 0

    caught = 0
    total = 0
    for src, mutants in ((CORE, MUTANTS), (PEER, PEER_MUTANTS)):
        raw = open(src, "rb").read().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        for name, old, new, target, control in mutants:
            total += 1
            o, n = old.replace("\n", nl), new.replace("\n", nl)
            count = raw.count(o)
            if count != 1:
                print("BAD mutant %s: anchor occurs %d times" % (name, count))
                ok = False
                continue
            path = os.path.join(WORK, "mut_" + name + ".cs")
            open(path, "wb").write(raw.replace(o, n).encode("utf-8"))
            mdll = build("mut_" + name, path, None) if src == CORE else build("mut_" + name, CORE, path)
            if mdll is None:
                print("BAD mutant %s: does not build" % name)
                ok = False
                continue
            trc, _ = run(mdll, [target])
            crc, _ = run(mdll, [control])
            hit = trc != 0 and crc == 0
            caught += hit
            ok = ok and hit
            print("%s mutant %s: target %s=%s; control %s=%s" % (
                "CAUGHT" if hit else "MISSED", name, target, "FAIL" if trc else "PASS", control, "PASS" if crc == 0 else "FAIL"))
    print("mutants: %d of %d caught" % (caught, total))
    after = sha(CORE)
    after_peer = sha(PEER)
    print("tracked files unchanged:", after == before and after_peer == before_peer)
    ok = ok and after == before and after_peer == before_peer
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
