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
    ("m4_request_dropped_when_busy", "if (_requested && !job.Busy && dispatch()) _requested = false;", "if (_requested && (job.Busy || dispatch())) _requested = false;", "viewer_refresh", "viewer_reopen"),
    ("m3_reopen_clears", "            internal void Reopen()\n            {\n                if (_pending) return;", "            internal void Reopen()\n            {\n                _pending = false;", "pending_worker", "busy"),
    ("m2_visit_limit_removed", "visits++ < visitLimit && withinTime()", "withinTime()",
     "voice_visit_budget", "voice_counts"),
    ("m2_elapsed_limit_removed", "elapsedTicks() < elapsedLimitTicks", "true",
     "voice_elapsed_budget", "voice_counts"),
    # Head-and-tail reverted to the old tail-only window: the banner, the
    # cr_build line and the patch summary are cut again.
    ('head_tail_reverted', 'int head = Math.Max(0, Math.Min(headChars, maxChars / 2));', 'int head = 0;', 'headtail', 'atcap'),
    ('h1_head_counted_in_bytes', 'int decodedKeep = PrefixEnd(decodedHead, head);', 'int decodedKeep = utf8.GetCharCount(hb, bomSkip, Math.Max(0, Utf8BoundaryAtOrBefore(hb, Math.Min(head, hb.Length)) - bomSkip));', 'head_characters', 'atcap'),
    ('h2_fallback_restored', '            byte[] all = ReadExactly(fs, 0, (int)sampledLength, sampledLength);\n            bom = HasUtf8Bom(all, all.Length) ? 3 : 0;\n            return new UTF8Encoding(false, true).GetString(all, bom, all.Length - bom);', '            bom = 0;\n            fs.Position = 0;\n            using (var sr = new StreamReader(fs, new UTF8Encoding(false), true, 1024, true))\n            {\n                string all = sr.ReadToEnd();\n                return all.Length <= maxChars ? all : all.Substring(all.Length - maxChars);\n            }', 'snapshot', 'atcap'),
    ('m1_marker_from_request', 'if (!captured) throw new EndOfStreamException();', '// Requested intervals are accepted without verifying the captured length.', 'changing_file', 'atcap'),
    ('h3_previous_only_fitting', '        internal static string Compose(string bepPath, string bepPrevPath, string uniPath, string audioSnapshot,\n                                       int capBep, int capBepPrev, int capUni, int totalCap,\n                                       ScrubFn scrub, ComposeInfo info)\n        {\n            if (info == null) info = new ComposeInfo();\n            info.ThreadId = Thread.CurrentThread.ManagedThreadId;\n            var windows = new[] {\n                CaptureFile(bepPrevPath, capBepPrev, HEAD_KEEP_CHARS, null),\n                CaptureFile(bepPath, capBep, HEAD_KEEP_CHARS, null),\n                CaptureFile(uniPath, capUni, HEAD_KEEP_CHARS, null)\n            };\n            int initialPrevTail = windows[0].TailBudget;\n            Func<bool, string> assemble = headsOnly => Assemble(bepPath, bepPrevPath, uniPath, audioSnapshot,\n                windows[1].Render(headsOnly ? 0 : windows[1].TailBudget),\n                windows[0].Render(headsOnly ? 0 : windows[0].TailBudget),\n                windows[2].Render(headsOnly ? 0 : windows[2].TailBudget),\n                capBep, capBepPrev, capUni);\n            string cleaned = null;\n            string reserved = null;\n            int scrubbed = 0;\n            for (int attempt = 1; attempt <= 8; attempt++)\n            {\n                info.Attempts = attempt;\n                cleaned = scrub(assemble(false), out scrubbed);\n                if (cleaned == null) break;\n                info.PrevCapUsed = capBepPrev - (initialPrevTail - windows[0].TailBudget);\n                if (cleaned.Length <= totalCap) break;\n                if (reserved == null)\n                {\n                    int ignored;\n                    reserved = scrub(assemble(true), out ignored);\n                    if (reserved == null) { cleaned = null; break; }\n                }\n                if (reserved.Length > totalCap || attempt == 8)\n                {\n                    info.Scrubbed = -1;\n                    info.Diagnostic = "[LOG-SCRUB] log bundle withheld: required heads exceed the sender cap";\n                    const string unavailable = "[log bundle withheld: required heads exceed the sender cap]";\n                    return totalCap >= unavailable.Length ? unavailable : "";\n                }\n                // Compare actual scrubbed full and head-only payloads. This\n                // reserves every head and budgets the expansion of all tails.\n                double ratio = (double)(totalCap - reserved.Length) / (cleaned.Length - reserved.Length);\n                for (int i = 0; i < windows.Length; i++)\n                {\n                    int tail = windows[i].TailBudget;\n                    int next = attempt == 7 ? 0 : Math.Min(Math.Max(0, tail - 1), (int)(tail * ratio));\n                    windows[i].FitFileCap(next);\n                }\n            }\n            if (cleaned == null)\n            {\n                info.Scrubbed = -1;\n                info.Diagnostic = "[LOG-SCRUB] scrub failed — log bundle withheld rather than sent unscrubbed";\n                return "[log bundle withheld: the local-path scrub failed on this machine]";\n            }\n            info.Scrubbed = scrubbed;\n            info.Diagnostic = string.Format("[LOG-SCRUB] bundle {0:N0} chars, {1} local-identity replacement(s)",\n                                            cleaned.Length, scrubbed);\n            return cleaned;\n        }', '        internal static string Compose(string bepPath, string bepPrevPath, string uniPath, string audioSnapshot,\n                                       int capBep, int capBepPrev, int capUni, int totalCap,\n                                       ScrubFn scrub, ComposeInfo info)\n        {\n            if (info == null) info = new ComposeInfo();\n            info.ThreadId = Thread.CurrentThread.ManagedThreadId;\n            string bep = ReadCapped(bepPath, capBep);\n            string uni = ReadCapped(uniPath, capUni);\n            int prevCap = capBepPrev;\n            string cleaned = null;\n            int scrubbed = 0;\n            for (int attempt = 1; attempt <= 3; attempt++)\n            {\n                info.Attempts = attempt;\n                string bepPrev = ReadCapped(bepPrevPath, prevCap);\n                string text = Assemble(bepPath, bepPrevPath, uniPath, audioSnapshot,\n                                       bep, bepPrev, uni, capBep, capBepPrev, capUni);\n                cleaned = scrub(text, out scrubbed);\n                if (cleaned == null) break;\n                info.PrevCapUsed = prevCap;\n                if (cleaned.Length <= totalCap || string.IsNullOrEmpty(bepPrev) || prevCap <= 0) break;\n                int over = cleaned.Length - totalCap;\n                prevCap = Math.Max(0, prevCap - over - 4096);\n            }\n            if (cleaned == null)\n            {\n                info.Scrubbed = -1;\n                info.Diagnostic = "[LOG-SCRUB] scrub failed — log bundle withheld rather than sent unscrubbed";\n                return "[log bundle withheld: the local-path scrub failed on this machine]";\n            }\n            info.Scrubbed = scrubbed;\n            info.Diagnostic = string.Format("[LOG-SCRUB] bundle {0:N0} chars, {1} local-identity replacement(s)",\n                                            cleaned.Length, scrubbed);\n            return cleaned;\n        }', 'compose_real_scrub', 'atcap'),
    # The builder forced onto the caller's (main) thread: Start runs the work
    # inline instead of on the thread it created.
    ("builder_on_main_thread", "t.Start();", "body();", "offmain", "clock"),
    # The [CLOCK] line loses its Photon offset field.
    ("clock_offset_dropped", "\" photon_offset_ms=\"", "\" photon_offset=\"", "clock", "headtail"),
]


# Structural mutants use the SAME oracle as the DSN-free pytest source gate.
# Each replacement anchor occurs once; no scheduler race is needed to reject
# removal of the worker's publication and consumption locks.
STRUCTURAL_MUTANTS = [
    ("l1_publication_consumption_locks_removed", (
        ("lock (_gate) { _ready = r; _readyThreadId = id; }",
         "{ _ready = r; _readyThreadId = id; }"),
        ("lock (_gate)\n                {\n                    done = _readyThreadId != 0;",
         "{\n                    done = _readyThreadId != 0;"),
    ), "job_locks", "job_locks"),
]


def check_job_locks(source):
    from pathlib import Path
    tests = os.path.join(REPO, "backend", "tests")
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, tests)
    try:
        from test_auto_log_client import assert_offmain_job_locks
        assert_offmain_job_locks(Path(source))
        return 0, "PASS job_locks"
    except AssertionError as exc:
        return 1, "FAIL job_locks: " + str(exc)
    except Exception as exc:
        return 2, "ERROR job_locks: oracle error " + type(exc).__name__
    finally:
        sys.path.pop(0)
        sys.dont_write_bytecode = previous


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
    for name, edits, target, control in STRUCTURAL_MUTANTS:
        mutated = raw
        valid = True
        for old, new in edits:
            o, n = old.replace("\n", nl), new.replace("\n", nl)
            count = mutated.count(o)
            if count != 1:
                print("BAD mutant %s: anchor occurs %d times" % (name, count))
                ok = False
                valid = False
                break
            mutated = mutated.replace(o, n, 1)
        if not valid:
            continue
        path = os.path.join(WORK, "mut_" + name + ".cs")
        open(path, "wb").write(mutated.encode("utf-8"))
        trc, tout = check_job_locks(path)
        crc, cout = check_job_locks(CORE)
        hit = trc == 1 and crc == 0
        caught += hit
        ok = ok and hit
        print("%s mutant %s: target %s=%s; control %s=%s" % (
            "CAUGHT" if hit else "MISSED", name, target, "FAIL" if trc else "PASS",
            control, "PASS" if crc == 0 else "FAIL"))
        if trc:
            print("    " + tout)
        if crc:
            print("    " + cout)
    print("mutants: %d of %d caught" % (caught, len(MUTANTS) + len(STRUCTURAL_MUTANTS)))
    after = sha(CORE)
    print("tracked file unchanged:", after == before)
    ok = ok and after == before
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
