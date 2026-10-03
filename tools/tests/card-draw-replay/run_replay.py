"""Card draw evidence (B4) replay harness, the Unity half.

Builds the REAL plugin/CardDrawEvidence.cs with the REAL
plugin/CardDrawEvidenceCore.cs and plugin/SeatEvidenceCore.cs, as they ship,
against Stubs.cs, and runs every scripted replay in Program.cs, each in its own
process: the seal at the dispatch (CD-M1), the room facts frozen before a reset
or NOT-RUN (CD-M2), a first-phase fault kept (CD-M3), a census per game and the
pool states (CD-M4), the quitting path's closing file and the tick's combat
hold (F3), the bounded hook-side buffer (F4); fix pass 3: the final census's
collision (CD-M4), the room predicate and the build lookup on the tick (F4).

Then mutants planted into COPIES of CardDrawEvidence.cs (the tracked file is
never written): each mutant's target case must FAIL and its control case PASS.
Exit 0 only when everything holds.

    python tools/tests/card-draw-replay/run_replay.py
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PLUGIN = os.path.join(REPO, "plugin")
PROJ = os.path.join(HERE, "CardReplayTests.csproj")
WORK = os.path.join(HERE, "work")
SOURCE = os.path.join(PLUGIN, "CardDrawEvidence.cs")
TRACKED = ["CardDrawEvidence.cs", "CardDrawEvidenceCore.cs", "SeatEvidenceCore.cs"]

CASES = ["seal", "first_fault", "orphan_fault", "freeze", "not_run", "census_per_game", "census_states",
         "quit_spools", "ring_bounded",
         # fix pass 3
         "census_final_collision", "gate_precomputed", "build_on_tick", "census_initial_collision",
         # fix pass 4
         "gate_same_game_transition"]

# (name, [(old, new), ...], target case, control case); each old occurs exactly once.
MUTANTS = [
    # CD-M1: the dispatch seals the game (the hook gate and the core seal together)
    ("unsealed", [("_hookTaken = true;\n                var e = Push(EV_SEAL);", "var e = Push(EV_SEAL);"),
                  ("            game.Seal();\n", "")], "seal", "freeze"),
    ("outcome_ignored", [("_game.Apply(e.Tgt[i], ix, e.ApKind, e.Vid, e.Outcome);", "_game.Apply(e.Tgt[i], ix, e.ApKind, e.Vid, K.APPLY_DONE);")],
     "seal", "freeze"),
    # CD-M3: a first-phase fault is kept; no later phase is the first
    ("later_phase_resets", [("if (!_hookOpen || _hookG != g || _hookRoom != room || _hookExited || _hookTaken) HookBegin(g, room);",
                             "HookBegin(g, room);")], "first_fault", "seal"),
    ("orphan_forgotten", [("_hookInc = _hookOrphan ? K.INC_FIRST : 0;", "_hookInc = 0;")], "orphan_fault", "seal"),
    # CD-M2: frozen before the reset, once; NOT-RUN when there is nothing to read
    ("freeze_noop", [("if (!_hookOpen || _hookTaken || (_frzValid && _frzRoom == _hookRoom)) return;", "return;")], "freeze", "seal"),
    ("freeze_twice", [("if (!_hookOpen || _hookTaken || (_frzValid && _frzRoom == _hookRoom)) return;", "if (!_hookOpen || _hookTaken) return;")],
     "freeze", "seal"),
    ("exited_reads_live", [("else if (!_hookExited)\n                {", "else\n                {")], "not_run", "seal"),
    # CD-M4: a census per game; collision and change in the record
    ("census_reused", [("var c = TakeCensus(e.Pool);", "var c = _dCensus != null ? _dCensus : TakeCensus(e.Pool);")], "census_per_game", "seal"),
    ("collision_dropped", [("game.PoolState = !c.Ok ? K.POOL_NOT_RUN : (c.Collision ? K.POOL_COLLISION : K.POOL_OK);",
                            "game.PoolState = !c.Ok ? K.POOL_NOT_RUN : K.POOL_OK;")], "census_initial_collision", "seal"),
    ("pool_ref_unchecked", [("else if (e.Pool != null && !ReferenceEquals(e.Pool, _dPool)) _game.PoolState = K.WorstPool(_game.PoolState, K.POOL_CHANGED);", "")],
     "census_states", "seal"),
    ("content_unchecked", [("p.Game.PoolState = K.WorstPool(p.Game.PoolState, fin);", "")], "census_states", "seal"),
    # fix pass 3, CD-M4: the final census's collision is honoured whether or not the digest moved
    ("final_collision_ignored", [(": (again.Collision ? K.POOL_COLLISION : (again.Digest != p.Game.Digest ? K.POOL_CHANGED : K.POOL_OK));",
                                  ": (again.Digest != p.Game.Digest ? K.POOL_CHANGED : K.POOL_OK);")], "census_final_collision", "seal"),
    ("final_overwrites", [("p.Game.PoolState = K.WorstPool(p.Game.PoolState, fin);", "p.Game.PoolState = fin;")], "census_states", "seal"),
    # fix pass 3, F4: the room predicate and the build lookup are the tick's
    ("gate_in_hook", [("if (!_gateOk || !string.Equals(_gateRoom, RoomName(), StringComparison.Ordinal)) { Skipped(); return; }", "if (!GateRoom()) return;")],
     "gate_precomputed", "seal"),
    ("gate_new_room_waits", [("if (now < _gateNextMs && string.Equals(room, _gateRoom, StringComparison.Ordinal)) return;",
                              "if (now < _gateNextMs) return;")], "gate_precomputed", "seal"),
    ("build_at_dispatch", [("e.Keep = rankedNow || CardDrawEvidenceTestGate.On;",
                            "e.Keep = rankedNow || CardDrawEvidenceTestGate.On; try { PeerBuild.BuildValue(); } catch { }")],
     "build_on_tick", "seal"),
    # F3: the quitting path never enters the queue; the tick waits for no combat
    ("quit_queues", [('bool persisted = now ? SeatEvidence.SpoolClosing("k", p.Env) : SeatEvidence.EnqueueCard(p.Env);',
                      "bool persisted = SeatEvidence.EnqueueCard(p.Env);")], "quit_spools", "seal"),
    ("tick_in_combat", [("if (SeatEvidence.CombatLive()) return;", "")], "quit_spools", "seal"),
    # F4: the bounded buffer counts what it lost and keeps a slot for the seal
    ("lost_uncounted", [("{ _hookLost++; return null; }", "{ return null; }")], "ring_bounded", "seal"),
    # fix pass 4, CD-M3: a skipped phase marks the rest of its own physical game, and only that game
    ("skip_unmarked", [("if (!_gateOk || !string.Equals(_gateRoom, RoomName(), StringComparison.Ordinal)) { Skipped(); return; }", "if (!_gateOk || !string.Equals(_gateRoom, RoomName(), StringComparison.Ordinal)) return;")],
     "gate_same_game_transition", "seal"),
    ("skip_dropped_by_refresh", [("if (_skipSet && !string.Equals(room, _skipRoom, StringComparison.Ordinal)) _skipSet = false;",
                                  "_skipSet = false;")], "gate_same_game_transition", "seal"),
    ("skip_marks_next_game", [("bool skipped = _skipSet && _skipG == g && ", "bool skipped = _skipSet && ")],
     "gate_same_game_transition", "seal"),
    ("skip_later_phase_first", [("_hookFirstDone = skipped;", "_hookFirstDone = false;")], "gate_same_game_transition", "seal"),
    ("seal_slot_not_kept", [("if (_evCount >= EV_CAP - (kind == EV_SEAL ? 0 : 1))", "if (_evCount >= EV_CAP)")], "ring_bounded", "seal"),
]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def build(tag, source):
    out = os.path.join(WORK, tag)
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep,
           "-p:CardSource=" + source]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-4000:], r.stderr[-2000:])
        return None
    return os.path.join(out, "bin", "CardReplayTests.dll")


def run_case(dll, case):
    r = subprocess.run(["dotnet", dll, case], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def main():
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("commit", head)
    before = {f: sha(os.path.join(PLUGIN, f)) for f in TRACKED}
    ok = True

    dll = build("base", SOURCE)
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    passed = 0
    for case in CASES:
        rc, out = run_case(dll, case)
        print(out)
        passed += rc == 0
        ok = ok and rc == 0
    print("replays: %d of %d pass" % (passed, len(CASES)))

    raw = open(SOURCE, "rb").read().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    caught = 0
    for name, edits, target, control in MUTANTS:
        text = raw
        good = True
        for old, new in edits:
            o, n = old.replace("\n", nl), new.replace("\n", nl)
            count = text.count(o)
            if count != 1:
                print("BAD mutant %s: anchor occurs %d times" % (name, count))
                good = False
                break
            text = text.replace(o, n)
        if not good:
            ok = False
            continue
        path = os.path.join(WORK, "mut_" + name + ".cs")
        open(path, "wb").write(text.encode("utf-8"))
        mdll = build("mut_" + name, path)
        if mdll is None:
            print("BAD mutant %s: does not build" % name)
            ok = False
            continue
        trc, tout = run_case(mdll, target)
        crc, _ = run_case(mdll, control)
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
