"""Throwing-collector harness (seat evidence contract V2, B1 / design report H1).

Copies every evidence hook class VERBATIM out of the shipped plugin files into
work/Hooks.g.cs, compiles it against Stubs.cs (every collector throws) and runs
one case per hook. Then plants mutants into COPIES of the generated text (the
tracked files are never written) and requires each mutant's target hook to
FAIL and its control hook to PASS. Also checks that every call into
SeatEvidence from another plugin file sits inside a try block, with a negative
control. Exit 0 only when everything holds.

    python tools/tests/seat-evidence-hooks/run_hooks.py
"""
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PLUGIN = os.path.join(REPO, "plugin")
PROJ = os.path.join(HERE, "HookTests.csproj")
WORK = os.path.join(HERE, "work")
SOURCES = ["HitEvidence.cs", "SeatEvidence.cs", "PoisonSync.cs"]

# Every evidence hook the build ships. A hook added or removed without this
# list changing fails the run.
EXPECTED = sorted([
    "HitEvidence_ExecuteRpcPatch", "HitEvidence_DamagePatch", "HitEvidence_ForcePatch", "HitEvidence_DotPatch",
    "HitEvidence_BlockPatch", "HitEvidence_SpawnAmmoPatch", "HitEvidence_SpawnNoAmmoPatch",
    "HitEvidence_SpawnSeparatePatch", "HitEvidence_ImpactPatch", "HitEvidence_StartGamePatch",
    "SeatEvidence_RpcSendPatch", "SeatEvidence_DoBlockPatch", "SeatEvidence_TryBlockMePatch",
    "SawPointEvidencePatch", "PointEndEvidencePatch",
])

HEADER = ("using System;\nusing System.Reflection;\nusing HarmonyLib;\nusing Photon.Pun;\nusing UnityEngine;\n\n"
          "namespace CompetitiveRounds\n{\n")

DOBLOCK = ("SeatEvidence_DoBlockPatch\n    {\n        [HarmonyFinalizer]\n        private static Exception Finalizer(Block __instance, Exception __exception)\n"
           "        {\n            ")
TRYBLOCKME = ("SeatEvidence_TryBlockMePatch\n    {\n        [HarmonyFinalizer]\n        private static Exception Finalizer(Block __instance, Exception __exception)\n"
              "        {\n            ")
UNKEYED = "try { SeatEvidence.UnkeyedReset(__instance); } catch { }"

# (name, old, new, target, control); old must occur exactly once in Hooks.g.cs
MUTANTS = [
    ("rpc_prefix_unwrapped", "try { depth = SeatEvidence.EnterRpc(__0, __1); } catch { }", "depth = SeatEvidence.EnterRpc(__0, __1);",
     "HitEvidence_ExecuteRpcPatch", "HitEvidence_DamagePatch"),
    ("rpc_finalizer_no_restore", "HitEvidence.RpcSender = (int)(uint)(__state & 0xFFFFFFFFL);", "",
     "HitEvidence_ExecuteRpcPatch", "HitEvidence_DamagePatch"),
    ("damage_prefix_unwrapped", "try { __state = SeatEvidence.DamageGate(__instance, damage != Vector2.zero); } catch { }",
     "__state = SeatEvidence.DamageGate(__instance, damage != Vector2.zero);", "HitEvidence_DamagePatch", "HitEvidence_ForcePatch"),
    ("damage_finalizer_unwrapped", "try { SeatEvidence.DamageArrived(__instance, __state, __exception == null); } catch { }",
     "SeatEvidence.DamageArrived(__instance, __state, __exception == null);", "HitEvidence_DamagePatch", "HitEvidence_ForcePatch"),
    ("force_unwrapped", "try { HitEvidence.NoteForce(__instance, force); } catch { }", "HitEvidence.NoteForce(__instance, force);",
     "HitEvidence_ForcePatch", "HitEvidence_DotPatch"),
    ("force_calls_nothing", "try { HitEvidence.NoteForce(__instance, force); } catch { }", "",
     "HitEvidence_ForcePatch", "HitEvidence_DotPatch"),
    ("dot_unwrapped", "try { HitEvidence.NoteDot(__instance, damage, damagingPlayer, healthRemoval); } catch { }",
     "HitEvidence.NoteDot(__instance, damage, damagingPlayer, healthRemoval);", "HitEvidence_DotPatch", "HitEvidence_ForcePatch"),
    ("block_prefix_unwrapped", "try { __state = SeatEvidence.BlockEnter(__instance, __0, __2, __4); } catch { }",
     "__state = SeatEvidence.BlockEnter(__instance, __0, __2, __4);", "HitEvidence_BlockPatch", "HitEvidence_ImpactPatch"),
    ("block_finalizer_unwrapped", "try { SeatEvidence.BlockExit(__state); } catch { }", "SeatEvidence.BlockExit(__state);",
     "HitEvidence_BlockPatch", "HitEvidence_ImpactPatch"),
    ("spawn_ammo_unwrapped", "try { SeatEvidence.ShotArrived(__instance, 0); } catch { }", "SeatEvidence.ShotArrived(__instance, 0);",
     "HitEvidence_SpawnAmmoPatch", "HitEvidence_SpawnNoAmmoPatch"),
    ("spawn_noammo_unwrapped", "try { SeatEvidence.ShotArrived(__instance, 1); } catch { }", "SeatEvidence.ShotArrived(__instance, 1);",
     "HitEvidence_SpawnNoAmmoPatch", "HitEvidence_SpawnAmmoPatch"),
    ("spawn_separate_unwrapped", "try { HitEvidence.NoteSpawn(__instance, 2); } catch { }", "HitEvidence.NoteSpawn(__instance, 2);",
     "HitEvidence_SpawnSeparatePatch", "HitEvidence_SpawnAmmoPatch"),
    ("impact_prefix_unwrapped", "try { frame = SeatEvidence.HitEnter(__instance, pid, __3, __5); } catch { }",
     "frame = SeatEvidence.HitEnter(__instance, pid, __3, __5);", "HitEvidence_ImpactPatch", "HitEvidence_BlockPatch"),
    ("impact_finalizer_unwrapped", "try { SeatEvidence.HitExit((int)(__state >> 32)); } catch { }", "SeatEvidence.HitExit((int)(__state >> 32));",
     "HitEvidence_ImpactPatch", "HitEvidence_BlockPatch"),
    ("startgame_unwrapped", "try { HitEvidence.GameEnd(PointEvidence.Point); } catch { }", "HitEvidence.GameEnd(PointEvidence.Point);",
     "HitEvidence_StartGamePatch", "PointEndEvidencePatch"),
    ("startgame_swallows", "try { HitEvidence.GameEnd(PointEvidence.Point); } catch { }\n            return __exception;",
     "try { HitEvidence.GameEnd(PointEvidence.Point); } catch { }\n            return null;", "HitEvidence_StartGamePatch", "PointEndEvidencePatch"),
    ("rpcsend_unwrapped", "try { SeatEvidence.BlockSent(__0, __1, __2); } catch { }", "SeatEvidence.BlockSent(__0, __1, __2);",
     "SeatEvidence_RpcSendPatch", "SeatEvidence_DoBlockPatch"),
    ("doblock_unwrapped", DOBLOCK + UNKEYED, DOBLOCK + "SeatEvidence.UnkeyedReset(__instance);",
     "SeatEvidence_DoBlockPatch", "SeatEvidence_TryBlockMePatch"),
    ("tryblockme_unwrapped", TRYBLOCKME + UNKEYED, TRYBLOCKME + "SeatEvidence.UnkeyedReset(__instance);",
     "SeatEvidence_TryBlockMePatch", "SeatEvidence_DoBlockPatch"),
    ("saw_prefix_skips", "private static void Before() { try { PointEvidence.SawBefore(); } catch { } }",
     "private static bool Before() { try { PointEvidence.SawBefore(); } catch { } return false; }", "SawPointEvidencePatch", "PointEndEvidencePatch"),
    ("saw_finalizer_unwrapped", "try { PointEvidence.SawAfter(); } catch { }", "PointEvidence.SawAfter();",
     "SawPointEvidencePatch", "PointEndEvidencePatch"),
    ("pointend_unwrapped", "try { PointEvidence.GameOverCheck(__instance); } catch { }", "PointEvidence.GameOverCheck(__instance);",
     "PointEndEvidencePatch", "SawPointEvidencePatch"),
]


BOUND_SOURCES = ["HitEvidence.cs", "SeatEvidence.cs", "PoisonSync.cs", "CardDrawEvidence.cs", "SeatEvidenceCore.cs",
                 "CardDrawEvidenceCore.cs"]

# The bound check must reach these (or it proves nothing).
BOUND_REQUIRED = ["HitEvidence.PointEnd", "HitEvidence.GameEnd", "HitEvidence.NoteDamage", "PointEvidence.PointEnd",
                  "PoisonSync.ReportUnansweredSilences", "SeatEvidence.Dispatch", "SeatEvidence.DamageGate",
                  "SeatEvidence.DamageArrived", "CardDrawEvidence.Dispatch", "CardDrawEvidence.C1",
                  "CardDrawEvidence.Push", "CardDrawEvidence.Fault", "CardDrawEvidence.FirstPhase", "SeatEvidence.Handover",
                  "SeatEvidenceCore.Block", "SeatEvidenceCore.Offer", "SeatEvidenceCore.Next"]

# (name, file, old, new, method the check must flag); old occurs once in the file
BOUND_MUTANTS = [
    ("pointend_logs", "HitEvidence.cs", "else _point.Clear();", 'else _point.Clear();\n                Plugin.Log.LogInfo("x");', "HitEvidence.PointEnd"),
    ("pointend_drains", "HitEvidence.cs", "else _point.Clear();", "else _point.Clear();\n                Drain();", "HitEvidence.Drain"),
    ("hp_line_at_hook", "PoisonSync.cs", "_sawLost.Clear(); _sawFrames = 0;\n                HitEvidence.PointEnd(_point);",
     "_sawLost.Clear(); _sawFrames = 0;\n                Drain();\n                HitEvidence.PointEnd(_point);", "PointEvidence.DrainOwn"),
    ("silence_logs_at_hook", "PoisonSync.cs", "_lateView[_lateCount] = kv.Value.ViewId;",
     'Plugin.Log.LogInfo("late"); _lateView[_lateCount] = kv.Value.ViewId;', "PoisonSync.ReportUnansweredSilences"),
    ("dispatch_saves", "SeatEvidence.cs", "_captures.Add(cap);", "Save(_queue); _captures.Add(cap);", "SeatEvidence.Dispatch"),
    ("dispatch_scans", "SeatEvidence.cs", "_captures.Add(cap);",
     "long fa0, fo0; Foreign(out fa0, out fo0); _captures.Add(cap);", "SeatEvidence.Foreign"),
    # F4: the aggregation (buckets, drift, cadence, percentiles) is the tick's
    ("dispatch_aggregates", "SeatEvidence.cs", "_captures.Add(cap);", "Aggregate(cap); _captures.Add(cap);", "SeatEvidence.Aggregate"),
    # F4: every hook-side loop is hard-capped
    ("admit_uncapped", "SeatEvidence.cs", "i < a.Count && i < C.HitWindow.PENDING_CAP", "i < a.Count", "SeatEvidence.Admit"),
    ("card_slots_uncapped", "CardDrawEvidence.cs", "for (int i = 0; i < n && i < K.SL_CAP; i++) e.Slots[i]",
     "for (int i = 0; i < n; i++) e.Slots[i]", "CardDrawEvidence.C3"),
    ("card_close_at_dispatch", "CardDrawEvidence.cs", "e.Inc = _hookInc | (_hookLost > 0 ? K.INC_LOST : 0);",
     "e.Inc = _hookInc | (_hookLost > 0 ? K.INC_LOST : 0); if (_game != null) _game.Close(-1);", "CardDrawEvidenceCore.Close"),
    ("dispatch_builds", "SeatEvidence.cs", "_nextCaptureTryMs = 0;\n            }", "_nextCaptureTryMs = 0;\n                BuildCaptures(false);\n            }",
     "SeatEvidence.BuildCaptures"),
    ("census_at_hook", "CardDrawEvidence.cs", "e.Pool = choice.cards;", "e.Pool = choice.cards; TakeCensus(e.Pool);",
     "CardDrawEvidence.TakeCensus"),
    ("card_fault_logs", "CardDrawEvidence.cs", "_faultNote[i] = ex != null ? ex.GetType().Name : \"?\";",
     "_faultNote[i] = ex != null ? ex.GetType().Name : \"?\"; Plugin.Log.LogWarning(\"f\");", "CardDrawEvidence.Fault"),
    ("card_dispatch_builds", "CardDrawEvidence.cs", "_hookTaken = true;", "_hookTaken = true; BuildPending(false);", "CardDrawEvidence.BuildPending"),
    ("card_dispatch_drains", "CardDrawEvidence.cs", "_hookTaken = true;", "_hookTaken = true; DrainEvents();", "CardDrawEvidence.DrainBegin"),
]


def bound_filter(f, cls):
    # PoisonSync.cs also holds gameplay patches; only its evidence hooks are entries
    return not (f == "PoisonSync.cs" and not cls.endswith("EvidencePatch"))


def bound_section():
    """F4: no forbidden operation is reachable from an evidence hook or a
    game-over dispatch. Base clean and non-vacuous; a comment naming a token
    is not a finding (negative control); every mutant is flagged at its
    planted method and nowhere else."""
    sys.path.insert(0, HERE)
    import bound_check
    texts = {f: read(os.path.join(PLUGIN, f)) for f in BOUND_SOURCES}
    ok = True
    findings, closure = bound_check.check(texts, bound_filter)
    missing = [m for m in BOUND_REQUIRED if m not in closure]
    print("bound check: %d methods reachable from the hooks and dispatches; findings %d; required reached %s"
          % (len(closure), len(findings), "all" if not missing else "MISSING " + ",".join(missing)))
    for f in findings:
        print("  FORBIDDEN in hook-time code: plugin/%s %s uses %s" % f)
    ok = ok and not findings and not missing
    ctrl = dict(texts)
    ctrl["HitEvidence.cs"] = ctrl["HitEvidence.cs"].replace("else _point.Clear();", 'else _point.Clear();\n                // Plugin.Log.LogInfo("x"); File.WriteAllText', 1)
    cf, _ = bound_check.check(ctrl, bound_filter)
    print("bound negative control (a token in a comment is not a finding):", "PASS" if not cf else "FAIL %s" % cf)
    ok = ok and not cf
    caught = 0
    for name, f, old, new, want in BOUND_MUTANTS:
        n = texts[f].count(old)
        if n != 1:
            print("BAD bound mutant %s: anchor occurs %d times in %s" % (name, n, f))
            ok = False
            continue
        mt = dict(texts)
        mt[f] = texts[f].replace(old, new)
        mf, mclosure = bound_check.check(mt, bound_filter)
        target = any(x[1] == want for x in mf)
        # control: nothing the base already reached is flagged except the planted method
        control = all(x[1] == want or x[1] not in closure for x in mf)
        hit = target and control
        caught += hit
        ok = ok and hit
        print("%s bound mutant %s: %s flagged=%s; no other base-reached method flagged=%s" % ("CAUGHT" if hit else "MISSED", name, want, target, control))
    print("bound mutants: %d of %d caught" % (caught, len(BOUND_MUTANTS)))
    return ok


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def read(path):
    return open(path, "rb").read().decode("utf-8").replace("\r\n", "\n")


def classes(text):
    """Every [HarmonyPatch]-attributed class, from its first attribute line to
    its closing brace, verbatim."""
    out = []
    for m in re.finditer(r"(?m)^(    \[HarmonyPatch[^\n]*\n)    internal static class (\w+)\b", text):
        start, name = m.start(1), m.group(2)
        i = text.index("{", m.end())
        depth = 0
        for j in range(i, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    out.append((name, text[start:j + 1]))
                    break
    return out


def generate():
    found = []
    for f in SOURCES:
        for name, body in classes(read(os.path.join(PLUGIN, f))):
            # PoisonSync.cs also holds gameplay patches; only its evidence hooks belong here
            if f == "PoisonSync.cs" and not name.endswith("EvidencePatch"):
                continue
            found.append((name, body))
    names = sorted(n for n, _ in found)
    return names, HEADER + "\n\n".join(body for _, body in found) + "\n}\n"


def build(tag, text):
    out = os.path.join(WORK, tag)
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "Hooks.g.cs")
    open(src, "wb").write(text.encode("utf-8"))
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep, "-p:HooksSource=" + src]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-2000:])
        return None
    return os.path.join(out, "bin", "HookTests.dll")


def run(dll, cases=()):
    r = subprocess.run(["dotnet", dll] + list(cases), capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def uncontained(text):
    """Calls into SeatEvidence (not SeatEvidenceCore) whose nearest enclosing
    block is not a try block. Comment lines are skipped."""
    bad = []
    for m in re.finditer(r"\bSeatEvidence\.\w+\(", text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        if text[line_start:m.start()].lstrip().startswith("//"):
            continue
        depth, k = 0, m.start() - 1
        while k >= 0:
            c = text[k]
            if c == "}":
                depth += 1
            elif c == "{":
                if depth == 0:
                    break
                depth -= 1
            k -= 1
        if k < 0 or not text[:k].rstrip().endswith("try"):
            bad.append(text.count("\n", 0, m.start()) + 1)
    return bad


def main():
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("commit", head)
    before = {f: sha(os.path.join(PLUGIN, f)) for f in sorted(set(SOURCES + BOUND_SOURCES))}
    ok = True

    ok = bound_section() and ok

    names, text = generate()
    print("hook classes found:", len(names))
    if names != EXPECTED:
        print("BAD hook set: missing", sorted(set(EXPECTED) - set(names)), "unexpected", sorted(set(names) - set(EXPECTED)))
        ok = False

    # call sites in the other plugin files, plus a negative control
    sites_ok = True
    for f in sorted(os.listdir(PLUGIN)):
        if not f.endswith(".cs") or f in ("SeatEvidence.cs", "SeatEvidenceCore.cs"):
            continue
        bad = uncontained(read(os.path.join(PLUGIN, f)))
        if bad:
            print("UNCONTAINED SeatEvidence call in plugin/%s at lines %s" % (f, bad))
            sites_ok = False
    ctrl_bad = uncontained("void F() { SeatEvidence.Tick(); }")
    ctrl_good = uncontained("void F() { try { SeatEvidence.Tick(); } catch { } }")
    control_ok = len(ctrl_bad) == 1 and not ctrl_good
    print("call sites contained:", sites_ok, "; negative control flagged:", control_ok)
    ok = ok and sites_ok and control_ok

    dll = build("base", text)
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    rc, out = run(dll)
    print(out)
    ok = ok and rc == 0

    caught = 0
    for name, old, new, target, control in MUTANTS:
        n = text.count(old)
        if n != 1:
            print("BAD mutant %s: anchor occurs %d times" % (name, n))
            ok = False
            continue
        mdll = build("mut_" + name, text.replace(old, new))
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
    unchanged = all(sha(os.path.join(PLUGIN, f)) == before[f] for f in before)
    print("tracked plugin files unchanged:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
