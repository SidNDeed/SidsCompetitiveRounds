"""Combat evidence (B1-B3, B5) hook harness.

1. Copies the thirteen combat evidence hook classes VERBATIM out of
   plugin/CombatEvidence.cs into work/<tag>/Hooks.g.cs, compiles them against
   Stubs.cs (every collector throws after recording its arguments) and runs
   one case per hook: attached to the target the design names, contained,
   forwarding its own arguments, never skipping the original, never writing
   an argument, and a finalizer returns the original's exception unchanged.
2. Attachment against the game: every hook's target method exists exactly
   once in the decompiled game source and every parameter the hook names
   (__instance, __N, or by name) has the target's type (a mismatch is a
   "Failed to patch" at boot, #83).
3. Containment: every collector entry runs its body inside its own try,
   counts a fault into its own cost row and times itself into the same row,
   and the thirteen rows are all used; every CombatEvidence call from another
   plugin file sits inside a try block (negative controls on a fixed snippet
   and on a mutated copy of a real call site); the shared-file wiring is
   present exactly as often as designed.
4. The bound walk (seat-evidence-hooks/bound_check.py, unchanged): entries are
   the thirteen hooks plus CombatEvidence.RpcSent (the shared RPC send hook),
   Dispatch and RoomExit; nothing reachable from them logs, writes files,
   scans, sorts, budgets, hashes, builds strings, queues, or loops without a
   *_CAP bound. Negative control and bound mutants (each flagged at its
   planted method and nowhere the base walk reached).
5. The client carries no judging wording: the combat files, comments
   stripped, contain no threshold or verdict vocabulary (negative control).
6. Mutants on COPIES of the generated text; each must fail its target case
   and pass its control. Tracked files are never written.

    python tools/tests/combat-evidence-hooks/run_hooks.py [--decompile DIR]
"""
import hashlib
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PLUGIN = os.path.join(REPO, "plugin")
PROJ = os.path.join(HERE, "HookTests.csproj")
WORK = os.path.join(HERE, "work")
SOURCE = os.path.join(PLUGIN, "CombatEvidence.cs")
BOUND_DIR = os.path.join(REPO, "tools", "tests", "seat-evidence-hooks")
DEFAULT_DECOMPILE = os.path.join(os.path.dirname(REPO), "SidsCompetitiveRounds", "logs-snapshot", "decompiled", "full")
TRACKED = ["CombatEvidence.cs", "CombatEvidenceCore.cs", "CombatEvidenceWire.g.cs", "GameStateWatcher.cs", "HitEvidence.cs",
           "Plugin.cs", "SeatEvidence.cs", "SeatEvidenceCore.cs"]

EXPECTED = sorted([
    "CombatEvidence_AttackPatch", "CombatEvidence_InitAmmoPatch", "CombatEvidence_InitNoAmmoPatch",
    "CombatEvidence_InitSeparatePatch", "CombatEvidence_ReloadPatch", "CombatEvidence_HitPatch",
    "CombatEvidence_ContactPatch", "CombatEvidence_BlockPatch", "CombatEvidence_TryBlockPatch",
    "CombatEvidence_DealtPatch", "CombatEvidence_TargetBouncePatch", "CombatEvidence_EdgeBouncePatch",
    "CombatEvidence_SyncPatch",
])

# collector entry -> its cost row (design 11.2: K1..K5, N1..N7, T)
ENTRIES = {"RpcSent": "K1", "InitEnter": "K2", "InitExit": "K2", "HitEnter": "K3", "BlockDone": "K4", "Dealt": "K5",
           "AttackEnter": "N1", "AttackExit": "N1", "ReloadEnter": "N2", "TargetBounce": "N3", "EdgeBounce": "N4",
           "SyncRead": "N5", "TryBlockEnter": "N6", "TryBlockExit": "N6", "ContactEnter": "N7", "Tick": "T"}
ROWS = ["K1", "K2", "K3", "K4", "K5", "N1", "N2", "N3", "N4", "N5", "N6", "N7", "T"]

# file -> [(literal, exact count)]
WIRING = {
    "GameStateWatcher.cs": [("CombatEvidence.BeginGame(oneVOneMatchAtStart)", 1), ("CombatEvidence.Dispatch(", 2)],
    "HitEvidence.cs": [("CombatEvidence.RoomExit(", 1)],
    "Plugin.cs": [("CombatEvidence.Tick(", 1), ("CombatEvidence.FlushOnQuit(", 1)],
    "SeatEvidence.cs": [('ROUTE_COMBAT = "/api/v1/matches/combat-evidence";', 1), ('route == "x" ? ROUTE_COMBAT', 1),
                        ("internal static bool EnqueueCombat(string body)", 1), ("try { CombatEvidence.RpcSent(__0, __1, __2); } catch { }", 1),
                        ("CombatEvidence.", 1)],
    "SeatEvidenceCore.cs": [('route != "x"', 1)],
    # the tick builds only outside combat and after the identity completed; the
    # quitting path writes its own closing file and never the queue
    "CombatEvidence.cs": [("SeatEvidence.EnqueueCombat(", 1), ("SeatEvidence.SpoolClosing(", 1),
                          ('bool persisted = quitting ? SeatEvidence.SpoolClosing("x", c.Env) : SeatEvidence.EnqueueCombat(c.Env);', 1),
                          ("if (SeatEvidence.CombatLive()) return;", 1)],
}

HEADER = "using System;\nusing HarmonyLib;\nusing Photon.Pun;\nusing UnityEngine;\n\nnamespace CompetitiveRounds\n{\n"

ATTACK_PRE = "try { CombatEvidence.AttackEnter(__instance, forceAttack, useAmmo, out __state); } catch { }"
INIT_FIN = "try { CombatEvidence.InitExit(__instance, __state); } catch { }\n            return __exception;"
BLOCK_FIN = "try { CombatEvidence.BlockDone(__instance); } catch { }\n            return __exception;"
RELOAD = "private static void Prefix(GunAmmo __instance, bool playSound)\n        {\n            try { CombatEvidence.ReloadEnter(__instance, playSound); } catch { }\n        }"
TRY_PRE = "            __state = 0;\n            try { CombatEvidence.TryBlockEnter(__instance, out __state); } catch { }"

# (name, old, new, target, control); old must occur exactly once in Hooks.g.cs
MUTANTS = [
    ("attack_prefix_unwrapped", ATTACK_PRE, ATTACK_PRE[len("try { "):-len(" } catch { }")],
     "CombatEvidence_AttackPatch", "CombatEvidence_InitAmmoPatch"),
    ("attack_state_dropped", "CombatEvidence.AttackExit(__instance, __result, forceAttack, __state)",
     "CombatEvidence.AttackExit(__instance, __result, forceAttack, 0)", "CombatEvidence_AttackPatch", "CombatEvidence_TryBlockPatch"),
    ("init_finalizer_swallows", INIT_FIN, INIT_FIN.replace("return __exception;", "return null;"),
     "CombatEvidence_InitAmmoPatch", "CombatEvidence_BlockPatch"),
    ("init_finalizer_unwrapped", "try { CombatEvidence.InitExit(__instance, __state); } catch { }",
     "CombatEvidence.InitExit(__instance, __state);", "CombatEvidence_InitAmmoPatch", "CombatEvidence_InitNoAmmoPatch"),
    ("noammo_kind_wrong", "CombatEvidence.InitEnter(__instance, senderID, 1)", "CombatEvidence.InitEnter(__instance, senderID, 0)",
     "CombatEvidence_InitNoAmmoPatch", "CombatEvidence_InitSeparatePatch"),
    ("separate_kind_wrong", "CombatEvidence.InitEnter(__instance, senderID, 2)", "CombatEvidence.InitEnter(__instance, senderID, 1)",
     "CombatEvidence_InitSeparatePatch", "CombatEvidence_InitNoAmmoPatch"),
    ("reload_can_skip", RELOAD, RELOAD.replace("private static void Prefix", "private static bool Prefix").replace(
        "catch { }\n        }", "catch { }\n            return true;\n        }"), "CombatEvidence_ReloadPatch", "CombatEvidence_HitPatch"),
    ("hit_args_swapped", "CombatEvidence.HitEnter(__instance, hitPoint, vel, viewID, wasBlocked)",
     "CombatEvidence.HitEnter(__instance, vel, hitPoint, viewID, wasBlocked)", "CombatEvidence_HitPatch", "CombatEvidence_ContactPatch"),
    ("contact_unwrapped", "try { CombatEvidence.ContactEnter(__instance, hit); } catch { }", "CombatEvidence.ContactEnter(__instance, hit);",
     "CombatEvidence_ContactPatch", "CombatEvidence_HitPatch"),
    ("block_finalizer_swallows", BLOCK_FIN, BLOCK_FIN.replace("return __exception;", "return null;"),
     "CombatEvidence_BlockPatch", "CombatEvidence_TryBlockPatch"),
    ("tryblock_state_not_neutral", TRY_PRE, TRY_PRE.replace("__state = 0;", "__state = 7;"),
     "CombatEvidence_TryBlockPatch", "CombatEvidence_DealtPatch"),
    ("dealt_calls_nothing", "try { CombatEvidence.Dealt(__instance); } catch { }", "try { } catch { }",
     "CombatEvidence_DealtPatch", "CombatEvidence_TargetBouncePatch"),
    ("targetbounce_by_ref", "BounceEffectRetarget __instance, Vector2 newVel)", "BounceEffectRetarget __instance, ref Vector2 newVel)",
     "CombatEvidence_TargetBouncePatch", "CombatEvidence_EdgeBouncePatch"),
    ("edge_unwrapped", "try { CombatEvidence.EdgeBounce(__instance); } catch { }", "CombatEvidence.EdgeBounce(__instance);",
     "CombatEvidence_EdgeBouncePatch", "CombatEvidence_SyncPatch"),
    ("sync_wrong_target", '[HarmonyPatch(typeof(SyncProjectile), "OnPhotonSerializeView")]',
     '[HarmonyPatch(typeof(SyncProjectile), "Update")]', "CombatEvidence_SyncPatch", "CombatEvidence_EdgeBouncePatch"),
]

# (name, file, old, new, the method that must be flagged)
BOUND_MUTANTS = [
    ("rpc_logs", "CombatEvidence.cs", "            if (g == null || view == null || !view.IsMine || method == null) return;",
     '            Plugin.Log.LogInfo("rpc");\n            if (g == null || view == null || !view.IsMine || method == null) return;', "CombatEvidence.RpcSentBody"),
    ("init_builds_string", "CombatEvidence.cs", "            NoteAnchor(g, init.gameObject, pv.ViewID, stamp, own);",
     "            var sbx = new System.Text.StringBuilder();\n            NoteAnchor(g, init.gameObject, pv.ViewID, stamp, own);", "CombatEvidence.InitEnterBody"),
    ("attack_uncapped_loop", "CombatEvidence.cs", "            if (!s.AttackFirstSeen) s.Acct.AddNoInit();",
     "            for (int q = 0; q < g.PingN; q++) { }\n            if (!s.AttackFirstSeen) s.Acct.AddNoInit();", "CombatEvidence.AttackExitBody"),
    ("volleys_uncapped", "CombatEvidence.cs", "for (int n = 0; n < RING_CAP && s.RingN > 0; n++)", "for (int n = 0; s.RingN > 0; n++)",
     "CombatEvidence.DrainVolleys"),
    ("hit_sorts_ping", "CombatEvidence.cs", "                g.ALastHit[slot] = stamp; g.AHasHit[slot] = true;",
     "                g.ALastHit[slot] = stamp; g.AHasHit[slot] = true; LHatMs(g);", "CombatEvidence.LHatMs"),
    ("roomexit_builds", "CombatEvidence.cs", "                    _open = false; _frozen = true; _frozenAtMs = SwMs;",
     "                    BuildCaptures(false);\n                    _open = false; _frozen = true; _frozenAtMs = SwMs;", "CombatEvidence.BuildCaptures"),
    ("dispatch_budgets", "CombatEvidence.cs", "                _nextCaptureTryMs = 0;\n            }\n            catch { _note",
     "                _nextCaptureTryMs = 0; E.Budget(null, 0);\n            }\n            catch { _note", "CombatEvidence.Dispatch"),
    ("tryblock_writes_file", "CombatEvidence.cs", "            g.B5tot[0]++;\n            if (counterMs < cd) g.B5tot[3]++;",
     '            g.B5tot[0]++; File.AppendAllText("x", "y");\n            if (counterMs < cd) g.B5tot[3]++;', "CombatEvidence.TryBlockBody"),
    ("contact_scan_uncapped", "CombatEvidence.cs", "i >= 0 && n < RECENT_CAP; i--, n++)", "i >= 0; i--, n++)", "CombatEvidence.FillContact"),
    ("core_gaps_uncapped", "CombatEvidenceCore.cs", "for (int i = 0; i < GAP_CAP; i++) _cx[o + 8 + i]",
     "for (int i = 0; i < W.GAP_COUNT; i++) _cx[o + 8 + i]", "CombatEvidenceCore.GunAccount.CloseCycle"),
]

BOUND_REQUIRED = [
    "CombatEvidence.RpcSent", "CombatEvidence.RpcSentBody", "CombatEvidence.OwnBlockKeyed", "CombatEvidence.AttackEnterBody",
    "CombatEvidence.AttackExitBody", "CombatEvidence.InitEnterBody", "CombatEvidence.InitExit", "CombatEvidence.NoteAnchor",
    "CombatEvidence.Reconcile", "CombatEvidence.ReloadBody", "CombatEvidence.HitBody", "CombatEvidence.FillContact",
    "CombatEvidence.ContactBody", "CombatEvidence.BlockBody", "CombatEvidence.TryBlockEnter", "CombatEvidence.TryBlockBody",
    "CombatEvidence.Dealt", "CombatEvidence.TargetBounceBody", "CombatEvidence.EdgeBounce", "CombatEvidence.SyncRead",
    "CombatEvidence.Dispatch", "CombatEvidence.RoomExit", "CombatEvidence.PointEnd", "CombatEvidence.DrainVolleys",
    "CombatEvidence.PointClose", "CombatEvidenceCore.GunAccount.AddShot", "CombatEvidenceCore.GunAccount.AddRegen",
    "CombatEvidenceCore.GunAccount.CloseCycle", "CombatEvidenceCore.FixedRows.NextSlot", "CombatEvidence.Ring.PushRow",
]

# judging vocabulary the public client must not carry (code and strings; comments stripped)
JUDGING = ["threshold", "suspic", "cheat", "aimbot", "triggerbot", "macro", "verdict", "penal", "judg", "anomal", "violat"]
JUDGING_FILES = ["CombatEvidence.cs", "CombatEvidenceCore.cs", "CombatEvidenceWire.g.cs"]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def read(path):
    return open(path, "rb").read().decode("utf-8").replace("\r\n", "\n")


def block_from(text, start, after):
    i = text.index("{", after)
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[start:j + 1]
    raise ValueError("unbalanced braces")


def classes(text):
    out = []
    for m in re.finditer(r"(?m)^(    \[HarmonyPatch[^\n]*\n(?:    \[[^\n]*\n)*)    internal static class (\w+)\b", text):
        out.append((m.group(2), block_from(text, m.start(1), m.end())))
    return out


def generate():
    found = classes(read(SOURCE))
    return sorted(n for n, _ in found), found, HEADER + "\n\n".join(b for _, b in found) + "\n}\n"


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
    return os.path.join(out, "bin", "CombatHookTests.dll")


def run(dll, cases=()):
    r = subprocess.run(["dotnet", dll] + list(cases), capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)//[^\n]*", "", text)


def uncontained(text):
    """Calls into CombatEvidence (not CombatEvidenceCore/Wire) whose nearest
    enclosing block is not a try block. Comment lines are skipped."""
    bad = []
    for m in re.finditer(r"\bCombatEvidence\.\w+\(", text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        if text[line_start:m.start()].lstrip().startswith(("//", "///", "*")):
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


def param_list(sig):
    out = []
    for p in [x.strip() for x in sig.split(",") if x.strip()]:
        p = p.split("=")[0].strip()
        p = re.sub(r"^(ref|out|in|params)\s+", "", p)
        t, n = p.rsplit(None, 1)
        out.append((t.replace(" ", ""), n))
    return out


def find_decl_file(decompile, typ):
    hits = []
    for root, _dirs, files in os.walk(decompile):
        if typ + ".cs" in files:
            hits.append(os.path.join(root, typ + ".cs"))
    return hits


def attachment(found, decompile):
    lines, ok = [], True
    if not os.path.isdir(decompile):
        return False, ["decompile not found at %s: attachment NOT verified" % decompile]
    for name, body in sorted(found):
        m = re.search(r'\[HarmonyPatch\(typeof\((\w+)\), "(\w+)"\)\]', body)
        typ, meth = m.group(1), m.group(2)
        paths = find_decl_file(decompile, typ)
        if len(paths) != 1:
            ok = False
            lines.append("  %s: %d decompiled %s.cs files" % (name, len(paths), typ))
            continue
        path = paths[0]
        src = read(path)
        decls = list(re.finditer(r"(?m)^[ \t]*(?:(?:public|private|protected|internal|static|virtual|override|new)\s+)+([\w\.\[\]<>]+)\s+"
                                 + meth + r"\s*\(([^)]*)\)", src))
        if len(decls) != 1:
            ok = False
            lines.append("  %s: %s.%s declared %d times" % (name, typ, meth, len(decls)))
            continue
        ret = decls[0].group(1)
        target = param_list(decls[0].group(2))
        decl_line = src.count("\n", 0, decls[0].start()) + 1
        hms = list(re.finditer(r"private static (?:void|bool|Exception) (?:Prefix|Postfix|Finalizer)\(([^)]*)\)", body))
        errs = [] if hms else ["no patch method"]
        for hm in hms:
            for p in [x.strip() for x in hm.group(1).split(",") if x.strip()]:
                byref = p.startswith(("ref ", "out "))
                t, n = re.sub(r"^(ref|out)\s+", "", p).rsplit(None, 1)
                t = t.replace(" ", "")
                if n == "__exception":
                    continue
                if n == "__state":
                    if byref and not p.startswith("out "):
                        errs.append("__state by ref")
                    continue
                if byref:
                    errs.append("%s by reference" % n)
                if n == "__instance":
                    if t != typ:
                        errs.append("__instance is %s" % t)
                elif n == "__result":
                    if t != ret:
                        errs.append("__result is %s, target returns %s" % (t, ret))
                elif re.match(r"__\d+$", n):
                    i = int(n[2:])
                    if i >= len(target) or target[i][0] != t:
                        errs.append("%s is %s" % (n, t))
                else:
                    named = [tt for tt, nn in target if nn == n]
                    if len(named) != 1 or named[0] != t:
                        errs.append("%s %s is not a parameter of the target" % (t, n))
        ok = ok and not errs
        lines.append("  %s -> %s.%s(%s) [%s:%d]: %s" % (name, typ, meth, ", ".join(t + " " + n for t, n in target),
                     os.path.relpath(path, decompile), decl_line, "ATTACHES" if not errs else "MISMATCH " + "; ".join(errs)))
    return ok, lines


def method_body(text, name):
    m = re.search(r"(?m)^        internal static \w+ " + name + r"\(", text)
    if not m:
        return None
    return block_from(text, m.start(), m.end())


def entries_section(src):
    ok, used = True, set()
    for name, row in sorted(ENTRIES.items()):
        body = method_body(src, name)
        if body is None:
            print("  ENTRY %s not found" % name)
            ok = False
            continue
        faults = re.findall(r"catch \(Exception ex\) \{ Fault\((\w+), ex\); \}", body)
        costs = re.findall(r"\bCost\((\w+), t0\);", body)
        stamps = body.count("long t0 = Stamp();")
        # only the window guard (and an out parameter's neutral value) runs before the timed, contained body
        head = body[body.index("{") + 1:body.index("long t0 = Stamp();")] if stamps == 1 else ""
        head_ok = all(re.match(r"^\s*(?:state = 0;|if \([^;{}]*\) return(?: \w+)?;|if \([^;{}]*\)|\{|)$", ln) for ln in head.split("\n"))
        try_ok = re.search(r"long t0 = Stamp\(\);\s*(?:\w+ \w+ = [^;]*;\s*)?try\b", body) is not None
        good = faults == [row] and costs == [row] and stamps == 1 and head_ok and try_ok and body.rindex("Cost(") > body.rindex("Fault(")
        used.add(row) if good else None
        ok = ok and good
        print("  %s %s: row %s, fault %s, cost %s, guard-only head %s, try after the stamp %s" % (
            "OK " if good else "BAD", name, row, faults, costs, head_ok, try_ok))
    every = sorted(used) == sorted(ROWS)
    print("  cost rows used by the entries: %d of %d" % (len(used), len(ROWS)))
    return ok and every


def judging_section(texts):
    bad = []
    for f in JUDGING_FILES:
        code = strip_comments(texts[f]).lower()
        for w in JUDGING:
            if w in code:
                bad.append((f, w))
    ctrl = strip_comments(texts["CombatEvidence.cs"] + "\nconst int AIM_THRESHOLD = 5;\n").lower()
    flagged = "threshold" in ctrl
    ctrl2 = strip_comments(texts["CombatEvidence.cs"] + "\n// a threshold named in prose\n").lower()
    prose = not any(w in ctrl2 for w in JUDGING)
    print("no judging vocabulary in the combat files (comments stripped): %s; negative control (a constant named THRESHOLD) flagged: %s;"
          " a word in a comment is not a finding: %s" % ("PASS" if not bad else "FAIL %s" % bad, flagged, prose))
    return not bad and flagged and prose


def bound_section(texts):
    sys.path.insert(0, BOUND_DIR)
    import bound_check
    for e in [("CombatEvidence", "RpcSent"), ("CombatEvidence", "Dispatch"), ("CombatEvidence", "RoomExit")]:
        if e not in bound_check.EXTRA_ENTRIES:
            bound_check.EXTRA_ENTRIES.append(e)
    # F5: the walker itself follows a member use at any receiver depth (a two-level receiver such as
    # `s.Acct.AddShot(` used to stop it); BOUND_REQUIRED lists methods reached only that way

    def filt(f, cls):
        return f == "CombatEvidence.cs"

    ok = True
    findings, closure = bound_check.check(texts, filt)
    missing = [m for m in BOUND_REQUIRED if m not in closure]
    combat = sorted(c for c in closure if c.startswith(("CombatEvidence.", "CombatEvidenceCore.", "CombatEvidence_")))
    print("bound walk: %d plugin files; %d methods reachable from the combat hooks, RpcSent, Dispatch and RoomExit (%d in the combat files);"
          " findings %d; required reached %s" % (len(texts), len(closure), len(combat), len(findings),
                                                 "all %d" % len(BOUND_REQUIRED) if not missing else "MISSING " + ",".join(missing)))
    print("  reached outside the combat files:", ", ".join(sorted(c for c in closure if c not in combat)))
    print("  hook-owned collection sweep (file, field, reached operations, insert sites, insert sites guarded by a cap):")
    for row in bound_check.LAST_SWEEP:
        print("    plugin/%s %s: %d, %d, %d" % row)
    if any(r[3] != r[4] for r in bound_check.LAST_SWEEP):
        ok = False
    for f in findings:
        print("  FORBIDDEN in hook-time code: plugin/%s %s uses %s" % f)
    ok = ok and not findings and not missing
    ctrl = dict(texts)
    ctrl["CombatEvidence.cs"] = ctrl["CombatEvidence.cs"].replace(
        "            g.B5tot[0]++;\n", '            g.B5tot[0]++; /* Plugin.Log.LogInfo("x"); File.WriteAllText; while (true) { } */\n', 1)
    cf, _ = bound_check.check(ctrl, filt)
    print("bound negative control (a token in a comment is not a finding):", "PASS" if not cf else "FAIL %s" % cf)
    ok = ok and not cf
    caught = 0
    for name, f, old, new, want in BOUND_MUTANTS:
        mt = dict(texts)
        n = mt[f].count(old)
        if n != 1:
            print("BAD bound mutant %s: anchor occurs %d times in %s" % (name, n, f))
            ok = False
            continue
        mt[f] = mt[f].replace(old, new)
        mf, _ = bound_check.check(mt, filt)
        target = any(x[1] == want for x in mf)
        control = all(x[1] == want or x[1] not in closure for x in mf)
        hit = target and control
        caught += hit
        ok = ok and hit
        print("%s bound mutant %s: %s flagged=%s; no other base-reached method flagged=%s" % (
            "CAUGHT" if hit else "MISSED", name, want, target, control))
    print("bound mutants: %d of %d caught" % (caught, len(BOUND_MUTANTS)))
    return ok


def main():
    decompile = DEFAULT_DECOMPILE
    if "--decompile" in sys.argv:
        decompile = sys.argv[sys.argv.index("--decompile") + 1]
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("commit", head)
    before = {f: sha(os.path.join(PLUGIN, f)) for f in TRACKED}
    texts = {f: read(os.path.join(PLUGIN, f)) for f in sorted(os.listdir(PLUGIN)) if f.endswith(".cs")}
    src = texts["CombatEvidence.cs"]
    ok = True

    names, found, text = generate()
    print("hook classes found:", len(names))
    if names != EXPECTED:
        print("BAD hook set: missing", sorted(set(EXPECTED) - set(names)), "unexpected", sorted(set(names) - set(EXPECTED)))
        ok = False

    aok, alines = attachment(found, decompile)
    print("attachment against the decompiled game (%s):" % decompile)
    print("\n".join(alines))
    ok = ok and aok

    print("collector entries (contained, fault-counted and timed in their own row):")
    eok = entries_section(src)
    print("collector entries:", "PASS" if eok else "FAIL")
    ok = ok and eok

    sites_ok = True
    for f in sorted(texts):
        if f.startswith("CombatEvidence"):
            continue
        bad = uncontained(texts[f])
        if bad:
            print("UNCONTAINED CombatEvidence call in plugin/%s at lines %s" % (f, bad))
            sites_ok = False
    gsw = texts["GameStateWatcher.cs"]
    ctrl = (len(uncontained("void F() { CombatEvidence.RoomExit(); }")) == 1
            and not uncontained("void F() { try { CombatEvidence.RoomExit(); } catch { } }")
            and len(uncontained(gsw.replace("try { CombatEvidence.Dispatch(", "{ CombatEvidence.Dispatch(", 1))) == 1)
    print("call sites contained:", sites_ok, "; negative controls flagged:", ctrl)
    ok = ok and sites_ok and ctrl

    wiring_ok = True
    for f, checks in WIRING.items():
        t = texts[f]
        for lit, n in checks:
            c = t.count(lit)
            if c != n:
                wiring_ok = False
                print("WIRING plugin/%s: %r occurs %d times, want %d" % (f, lit, c, n))
    print("shared-file wiring present exactly as designed:", wiring_ok)
    ok = ok and wiring_ok

    ok = judging_section(texts) and ok
    ok = bound_section(texts) and ok

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
        trc, tout = run(mdll, [target])
        crc, _ = run(mdll, [control])
        hit = trc != 0 and crc == 0
        caught += hit
        ok = ok and hit
        print("%s mutant %s: target %s=%s; control %s=%s" % (
            "CAUGHT" if hit else "MISSED", name, target, "FAIL" if trc else "PASS", control, "PASS" if crc == 0 else "FAIL"))
        if not hit:
            print("   ", tout.replace("\n", "\n    "))
    print("mutants: %d of %d caught" % (caught, len(MUTANTS)))
    unchanged = all(sha(os.path.join(PLUGIN, f)) == before[f] for f in TRACKED)
    print("tracked plugin files unchanged:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
