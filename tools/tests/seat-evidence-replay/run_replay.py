"""Seat evidence replay harness (client half, contract V2).

Builds the REAL plugin/SeatEvidence.cs and plugin/SeatEvidenceCore.cs, as they
ship, against Stubs.cs and runs every scripted replay in Program.cs, each in its
own process and its own empty queue directory: the Unity-side classification
(block kinds, keys, started, faults, last_*, hit paths, dmg, unpaired counts),
the frozen window and the end kinds of a game cut short, the queue across a
launch, and the compat sender of a disabled seat.

Then source checks of the wiring the replays cannot reach (GameStateWatcher's
room-exit and DC paths, the quit hook), each with a negative control, and
mutants planted into COPIES of SeatEvidence.cs (the tracked file is never
written): each mutant's target case must FAIL and its control case PASS.
Exit 0 only when everything holds.

    python tools/tests/seat-evidence-replay/run_replay.py
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PLUGIN = os.path.join(REPO, "plugin")
PROJ = os.path.join(HERE, "ReplayTests.csproj")
WORK = os.path.join(HERE, "work")
SE = os.path.join(PLUGIN, "SeatEvidence.cs")
TRACKED = ["SeatEvidence.cs", "SeatEvidenceCore.cs", "GameStateWatcher.cs", "Plugin.cs"]

CASES = ["victim_block_hit", "shooter_paths", "unkeyed_and_nesting", "cut_left", "cut_guards",
         "closing_next_boot", "compat_sender", "compat_bounds", "cut_422_kept"]

# (name, old text, new text, target case, control case); old occurs exactly once.
MUTANTS = [
    ("echo_kind2", "f.Keyed = true; f.Tb = copy.RootTb; f.Kind = 3;", "f.Keyed = true; f.Tb = copy.RootTb; f.Kind = 2;",
     "shooter_paths", "victim_block_hit"),
    ("started_inverted", "bool started = !f.OnlyEffects && f.B.sinceBlock == 0f;",
     "bool started = !f.OnlyEffects && f.B.sinceBlock != 0f;", "shooter_paths", "compat_sender"),
    ("fault_uncounted", "if (f.Kind == 0 && !started) _blkFaults++;", "", "shooter_paths", "victim_block_hit"),
    ("unkeyed_keeps_last", "copy.EverReset = true; copy.HasLast = false;", "copy.EverReset = true;",
     "shooter_paths", "victim_block_hit"),
    ("own_block_any_target", "target != RpcTarget.Others || ", "", "victim_block_hit", "shooter_paths"),
    ("victim_dmg_unmarked", "_awaitDamage[6] = gate ? 1 : 0;", "_awaitDamage[6] = 0;", "victim_block_hit", "shooter_paths"),
    ("path1_unstamped_listed", "if (!f.HasStamp) { _unpairHits++; return; }", "if (!f.HasStamp) { _unpairHits++; }",
     "shooter_paths", "victim_block_hit"),
    ("victim_lists_path1", "else _unpairHits++;",
     "else _hitRecv.Add(C.HitRecvEntry(1, c.Stamp, 0, 0, ServerNow(), false, gate, -1));", "victim_block_hit", "shooter_paths"),
    ("nesting_no_restore", "if (before >= 0) _ctxDepth = before;", "", "unkeyed_and_nesting", "victim_block_hit"),
    ("roomexit_discards", "if (_open) { _open = false; _frozen = true; _frozenAtMs = SwMs; }", "_open = false;",
     "cut_left", "victim_block_hit"),
    ("frozen_not_taken", "bool frozen = !live && _frozen", "bool frozen = !live && false && _frozen", "cut_left", "victim_block_hit"),
    ("frozen_any_room", '&& _room.Length > 0 && attach != null && attach.StartsWith(_room + "_", StringComparison.Ordinal)', "",
     "cut_guards", "cut_left"),
    ("frozen_no_expiry", "&& SwMs - _frozenAtMs <= FROZEN_MS", "", "cut_guards", "cut_left"),
    ("end_dropped", "End = _end,", "End = null,", "cut_left", "victim_block_hit"),
    ("end_last_wins", "&& _end == null && C.IsEndKind(kind)", "&& C.IsEndKind(kind)", "cut_guards", "cut_left"),
    ("clear_end_noop", "try { if (_open) _end = null; } catch { }", "", "cut_guards", "cut_left"),
    ("closing_not_persisted", "_queue.Add(new C.Pending { Route = route, Body = body, FirstUnix = UnixNow() });\n            Save();",
     "_queue.Add(new C.Pending { Route = route, Body = body, FirstUnix = UnixNow() });", "closing_next_boot", "cut_left"),
    ("sender_sends_records", "(onlyRoute == null || q.Route == onlyRoute) && ", "", "compat_sender", "closing_next_boot"),
    ("sender_never_auths", "if (SwMs >= _nextAuthMs) { _nextAuthMs = SwMs + 1000; SteamAuth.MaybeRefresh(); }", "",
     "compat_sender", "closing_next_boot"),
    ("sender_no_identity", "try { SteamAuth.FallbackIdentity = OwnSteamId(); } catch { }", "", "compat_sender", "compat_bounds"),
    ("sender_base_without_consent", "if (Plugin.DataConsentGranted)\n                {\n                    try { ApiClient.SeatEvidenceCompatBase",
     "{\n                    try { ApiClient.SeatEvidenceCompatBase", "compat_bounds", "compat_sender"),
    ("held_not_set", "p.HoldUntilNextLaunch = true;", "", "cut_422_kept", "closing_next_boot"),
]

# Wiring the replays cannot reach: (file, what, anchors that must each occur
# exactly once, in this order). The negative control deletes the first
# anchor's text and requires the check to fail.
WIRING = [
    ("GameStateWatcher.cs", "the other seat's departure notes other_left",
     [r'opponentDCReported = true;\s*try \{ SeatEvidence\.NoteEnd\("other_left"\); \} catch \{ \}']),
    ("GameStateWatcher.cs", "the other seat's return clears the noted end",
     [r'opponentDCReported = false;\s*try \{ SeatEvidence\.ClearEnd\(\); \} catch \{ \}']),
    ("GameStateWatcher.cs", "the room-exit branch notes the end, then dispatches a game with no game over",
     [r"// Someone disconnected mid-match", r"SeatEvidence\.NoteEnd\(seEnd\);",
      r"if \(!gameOverReported\) SeatEvidenceCut\(localRounds, oppRounds\);", r'"\[POLL\] Left room"']),
    ("GameStateWatcher.cs", "the cut dispatch follows the report's score",
     [r"int\[\] s = SeatEvidenceCore\.CutScore\(localRounds, oppRounds, opponentDCReported\);",
      r"SeatEvidence\.Dispatch\(localSteamId, opponentSteamId, BuildReportRoomId\(s\[0\], s\[1\]\), s\[0\], s\[1\],"]),
    ("GameStateWatcher.cs", "the quit hook notes closing and dispatches a live game",
     [r"internal static void SeatEvidenceOnQuit\(\)", r"if \(!isTracking \|\| gameOverReported\) return;",
      r'SeatEvidence\.NoteEnd\("closing"\);', r"SeatEvidenceCut\(localTeamId == 0 \? p1Rounds : p2Rounds"]),
    ("Plugin.cs", "the quit hook is registered",
     [r"Application\.quitting \+= \(\) =>\s*\{\s*try \{ GameStateWatcher\.SeatEvidenceOnQuit\(\); \} catch \{ \}"]),
]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def read(path):
    return open(path, "rb").read().decode("utf-8-sig")


def build(tag, source):
    out = os.path.join(WORK, tag)
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep,
           "-p:SeatEvidenceSource=" + source]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-4000:], r.stderr[-2000:])
        return None
    return os.path.join(out, "bin", "ReplayTests.dll")


def run_case(dll, tag, case):
    d = os.path.join(WORK, tag, "cases", case)
    if os.path.isdir(d):
        shutil.rmtree(d)
    r = subprocess.run(["dotnet", dll, case, d], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def wiring_ok(text, anchors):
    pos = -1
    for a in anchors:
        found = list(re.finditer(a, text))
        if len(found) != 1 or found[0].start() <= pos:
            return False
        pos = found[0].start()
    return True


def main():
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("commit", head)
    before = {f: sha(os.path.join(PLUGIN, f)) for f in TRACKED}
    ok = True

    dll = build("base", SE)
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    passed = 0
    for case in CASES:
        rc, out = run_case(dll, "base", case)
        print(out)
        passed += rc == 0
        ok = ok and rc == 0
    print("replays: %d of %d pass" % (passed, len(CASES)))

    wired = 0
    for f, what, anchors in WIRING:
        text = read(os.path.join(PLUGIN, f))
        good = wiring_ok(text, anchors)
        m = re.search(anchors[0], text)
        neg = text[:m.start()] + text[m.end():] if m else text
        control = not wiring_ok(neg, anchors)
        wired += good and control
        ok = ok and good and control
        print("%s wiring %s: %s; negative control flagged=%s" % ("OK " if good and control else "BAD", f, what, control))
    print("wiring checks: %d of %d" % (wired, len(WIRING)))

    raw = open(SE, "rb").read().decode("utf-8")
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
        trc, tout = run_case(mdll, "mut_" + name, target)
        crc, _ = run_case(mdll, "mut_" + name, control)
        hit = trc != 0 and crc == 0
        caught += hit
        ok = ok and hit
        print("%s mutant %s: target %s=%s; control %s=%s%s" % (
            "CAUGHT" if hit else "MISSED", name, target, "FAIL" if trc else "PASS", control,
            "PASS" if crc == 0 else "FAIL", "" if hit else " (" + tout[-200:] + ")"))
    print("mutants: %d of %d caught" % (caught, len(MUTANTS)))

    unchanged = all(sha(os.path.join(PLUGIN, f)) == before[f] for f in TRACKED)
    print("tracked plugin files unchanged:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
