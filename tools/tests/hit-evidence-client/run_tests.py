"""Item D harness: build the cases over the REAL plugin/HitEvidenceCore.cs,
run them, then build mutated COPIES (work/, CoreSource override -- the
tracked file is never written) and require each mutant's target case to FAIL
and its control case to PASS. Exit 0 only when everything holds.

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
]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def build(tag, core):
    out = os.path.join(WORK, tag)
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep,
           "-p:CoreSource=" + core]
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
    print("plugin/HitEvidenceCore.cs sha256", before)
    ok = True

    dll = build("base", CORE)
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    rc, out = run(dll)
    print(out)
    ok = ok and rc == 0

    raw = open(CORE, "rb").read().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    caught = 0
    for name, old, new, target, control in MUTANTS:
        o, n = old.replace("\n", nl), new.replace("\n", nl)
        count = raw.count(o)
        if count != 1:
            print("BAD mutant %s: anchor occurs %d times" % (name, count))
            ok = False
            continue
        path = os.path.join(WORK, "mut_" + name + ".cs")
        open(path, "wb").write(raw.replace(o, n).encode("utf-8"))
        mdll = build("mut_" + name, path)
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
    print("mutants: %d of %d caught" % (caught, len(MUTANTS)))
    after = sha(CORE)
    print("tracked file unchanged:", after == before)
    ok = ok and after == before
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
