"""Night 2026-10-19 calibration lane harness: build the controls over the REAL
plugin files (InboundStallCore.cs, NetJitterBudgetCore.cs, PoisonLedgerCore.cs,
LagNotices.cs, FpsFocusCore.cs, DecimatedList.cs), run every case, then build
mutated COPIES (work/, the *Source overrides; the tracked files are never
written) and require each mutant's target case to FAIL and its control case to
PASS. Exit 0 only when everything holds.

    python tools/tests/net-stall-detect/run_tests.py [mutant names...]
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PROJ = os.path.join(HERE, "NetStallTests.csproj")
WORK = os.path.join(HERE, "work")
PLUGIN = os.path.join(REPO, "plugin")

SOURCES = {
    "StallSource": "InboundStallCore.cs",
    "JitterSource": "NetJitterBudgetCore.cs",
    "PoisonSource": "PoisonLedgerCore.cs",
    "LagSource": "LagNotices.cs",
    "FocusSource": "FpsFocusCore.cs",
    "DecimatedSource": "DecimatedList.cs",
}

# (name, source key, [(old, new), ...], target case, control case). Each old
# text must occur exactly once in the shipped file.
MUTANTS = [
    # required: the detector threshold removed
    ("stall_threshold_removed", "StallSource",
     [("            if (depth > QUEUE_BOUND)\n", "            if (depth > 0)\n")],
     "stall_night", "stall_frames_hitch"),
    ("stall_min_duration_removed", "StallSource",
     [("            if (dur <= MIN_STALL_MS) return null;\n", "")],
     "stall_ordinary_spikes", "stall_night"),
    ("stall_frames_ignored", "StallSource",
     [("            if (_worstFrameMs >= FRAME_OK_MS)\n", "            if (false)\n")],
     "stall_frames_hitch", "stall_night"),
    ("stall_cap_removed", "StallSource",
     [("            if (_roomLines >= MAX_LINES_PER_ROOM) { RoomSuppressed++; return null; }\n", "")],
     "stall_cap", "stall_night"),
    ("stall_streams_always_stopped", "StallSource",
     [("                    if (!advanced) stopped++;\n", "                    stopped++;\n")],
     "stall_streams_flowing", "stall_night"),
    # required: the reserve removed
    ("jitter_reserve_removed", "JitterSource",
     [("            if (big && _reserveUsed < RESERVE) { _reserveUsed++; isReserve = true; return true; }\n", "")],
     "jitter_reserve", "jitter_top"),
    ("jitter_top_only_logged", "JitterSource",
     [("            _qualifying++;\n            NoteTop(actor, arrivalMs, senderMs, excessMs, game);\n", "            _qualifying++;\n"),
      ("            if (_routineUsed < TOTAL - RESERVE) { _routineUsed++; return true; }\n",
       "            if (_routineUsed < TOTAL - RESERVE) { _routineUsed++; NoteTop(actor, arrivalMs, senderMs, excessMs, game); return true; }\n")],
     "jitter_top", "jitter_reserve"),
    # required: the poison fix reverted (the per-room 24-line cap, no reset at the boundary)
    ("poison_fix_reverted", "PoisonSource",
     [("        internal const int PER_POINT = 12;\n", "        internal const int PER_POINT = 24;\n"),
      ("        internal void OnPoint() { _point = 0; _cutMarked = false; }\n", "        internal void OnPoint() { }\n")],
     "poison_kill_every_epoch", "poison_cut_marker"),
    ("poison_marker_repeats", "PoisonSource",
     [("            if (_cutMarked) return null;\n", "")],
     "poison_cut_marker", "poison_kill_every_epoch"),
    ("lag_gate_not_counted", "LagSource",
     [("                if (!SeatEligible()) { _gNotPlain1v1++; ResetAll(logExits: true, why: \"seat\"); return; }\n",
       "                if (!SeatEligible()) { ResetAll(logExits: true, why: \"seat\"); return; }\n")],
     "lag_1v2_gate", "lag_1v1_fires"),
    ("lag_gate_line_dropped", "LagSource",
     [("            try { string g = GateLine(); if (g != null) Plugin.Log?.LogInfo(g); } catch { }\n", "")],
     "lag_1v1_setting_off", "lag_bar_met_1v2"),
    ("lag_opp_stream_bar_off_by_one", "LagSource",
     [("        internal const int OPP_STREAM_MIN_WINDOWS = 2;", "        internal const int OPP_STREAM_MIN_WINDOWS = 3;")],
     "lag_bar_met_1v2", "lag_1v2_gate"),
    ("focus_flag_inverted", "FocusSource",
     [("        internal static int BucketFlag(bool anyUnfocusedFrame) { return anyUnfocusedFrame ? 0 : 1; }",
       "        internal static int BucketFlag(bool anyUnfocusedFrame) { return anyUnfocusedFrame ? 1 : 0; }")],
     "focus_lockstep", "lag_1v2_gate"),
]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def build(tag, overrides):
    out = os.path.join(WORK, tag)
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep]
    for k, v in overrides.items():
        cmd.append("-p:%s=%s" % (k, v))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-2000:])
        return None
    return os.path.join(out, "bin", "NetStallTests.dll")


def run(dll, cases=()):
    r = subprocess.run(["dotnet", dll] + list(cases), capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def main():
    only = sys.argv[1:]
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("commit", head)
    before = {k: sha(os.path.join(PLUGIN, f)) for k, f in SOURCES.items()}
    for k, f in SOURCES.items():
        print("plugin/%s sha256 %s" % (f, before[k]))
    ok = True

    names = [m[0] for m in MUTANTS]
    if len(set(names)) != len(names):
        print("BAD mutant table: a name appears twice")
        ok = False

    dll = build("base", {})
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    rc, out = run(dll)
    print(out)
    ok = ok and rc == 0
    cases = [l.split()[1] for l in out.splitlines() if l.startswith(("PASS ", "FAIL "))]
    targeted = set(m[3] for m in MUTANTS)
    missing = sorted(set(cases) - targeted)
    if missing:
        print("BAD: cases without a mutant:", ", ".join(missing))
        ok = False

    caught = 0
    run_set = [m for m in MUTANTS if not only or m[0] in only]
    for name, key, edits, target, control in run_set:
        src = os.path.join(PLUGIN, SOURCES[key])
        raw = open(src, "rb").read().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        bad = False
        for old, new in edits:
            o, n = old.replace("\n", nl), new.replace("\n", nl)
            count = raw.count(o)
            if count != 1:
                print("BAD mutant %s: anchor occurs %d times: %r" % (name, count, old[:70]))
                bad = True
                break
            raw = raw.replace(o, n)
        if bad:
            ok = False
            continue
        path = os.path.join(WORK, "mut_" + name + "_" + SOURCES[key])
        open(path, "wb").write(raw.encode("utf-8"))
        mdll = build("mut_" + name, {key: path})
        if mdll is None:
            print("BAD mutant %s: does not build" % name)
            ok = False
            continue
        trc, tout = run(mdll, [target])
        crc, cout = run(mdll, [control])
        hit = trc != 0 and crc == 0
        caught += hit
        ok = ok and hit
        print("%s mutant %s: target %s=%s; control %s=%s" % (
            "CAUGHT" if hit else "MISSED", name, target, "FAIL" if trc else "PASS", control, "PASS" if crc == 0 else "FAIL"))
        for l in tout.splitlines():
            if l.startswith("FAIL "):
                print("    " + l[:300])
    print("mutants: %d of %d caught" % (caught, len(run_set)))
    after = {k: sha(os.path.join(PLUGIN, f)) for k, f in SOURCES.items()}
    same = after == before
    print("tracked files unchanged:", same)
    ok = ok and same
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
