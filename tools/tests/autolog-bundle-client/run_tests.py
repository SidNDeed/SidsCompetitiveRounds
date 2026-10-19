"""Lane autolog-bundle harness: build the cases over the REAL
plugin/LogBundleCore.cs, run them, then build mutated COPIES (work/,
CoreSource override -- the tracked file is never written) and require each
mutant's target case to FAIL and its control case to PASS. Exit 0 only when
everything holds. DSN-free: no database and no network.

    python tools/tests/autolog-bundle-client/run_tests.py
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PROJ = os.path.join(HERE, "AutologBundleTests.csproj")
CORE = os.path.join(REPO, "plugin", "LogBundleCore.cs")
WORK = os.path.join(HERE, "work")

# (name, old text, new text, target case, control case). Each old text must
# occur exactly once in the shipped file.
MUTANTS = [
    # Head-and-tail reverted to the old tail-only window: the banner, the
    # cr_build line and the patch summary are cut again.
    ("head_tail_reverted", "int head = Math.Min(headChars, maxChars / 2);", "int head = 0;",
     "headtail", "atcap"),
    # The builder forced onto the caller's (main) thread: Start runs the work
    # inline instead of on the thread it created.
    ("builder_on_main_thread", "t.Start();", "body();", "offmain", "clock"),
    # The [CLOCK] line loses its Photon offset field.
    ("clock_offset_dropped", "\" photon_offset_ms=\"", "\" photon_offset=\"", "clock", "headtail"),
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
    return os.path.join(out, "bin", "AutologBundleTests.dll")


def run(dll, cases=()):
    r = subprocess.run(["dotnet", dll] + list(cases), capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout.strip()


def main():
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True).stdout
    print("commit", head)
    print("tree status lines", len([l for l in status.splitlines() if l.strip()]))
    before = sha(CORE)
    print("plugin/LogBundleCore.cs sha256", before)
    ok = True

    dll = build("base", CORE)
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    rc, out = run(dll)
    print(out)
    ok = ok and rc == 0

    caught = 0
    raw = open(CORE, "rb").read().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
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
        trc, tout = run(mdll, [target])
        crc, _ = run(mdll, [control])
        hit = trc != 0 and crc == 0
        caught += hit
        ok = ok and hit
        print("%s mutant %s: target %s=%s; control %s=%s" % (
            "CAUGHT" if hit else "MISSED", name, target, "FAIL" if trc else "PASS", control, "PASS" if crc == 0 else "FAIL"))
        for line in tout.splitlines():
            if "FAIL" in line:
                print("    " + line.strip())
    print("mutants: %d of %d caught" % (caught, len(MUTANTS)))
    after = sha(CORE)
    print("tracked file unchanged:", after == before)
    ok = ok and after == before
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
