"""Card draw evidence (B4) hook harness.

1. Copies the six card draw evidence hook classes and the test gate class
   VERBATIM out of plugin/CardDrawEvidence.cs into work/<tag>/Hooks.g.cs,
   compiles them against Stubs.cs (every collector throws after recording its
   arguments) and runs one case per hook: attached to the target the design
   names, contained, forwarding its own arguments, never skipping or writing
   the original's flags, with the priority the design names.
2. Attachment against the game: every hook's target method exists exactly
   once in the decompiled game source and the hook's __N parameters have the
   target's parameter types (a mismatch is a "Failed to patch" at boot, #83).
   The boot line's HOOKS table names the same six (class, type, method).
3. Containment: every collector entry runs its body inside its own try and
   counts a fault into its cost row; every CardDrawEvidence call from another
   plugin file sits inside a try block (negative controls on a fixed snippet
   and on a mutated copy of the real call site); the shared-file wiring is
   present exactly once per site.
4. Finding L3: the test gate is compiled without and with
   SCR_CARD_EVIDENCE_TEST_GATE; its marker (a string that exists only to be
   probed, UTF-16LE in the #US heap, byte-scanned at any offset, #157/#306)
   must be absent from the first build and present in the second; no build
   configuration, props or targets file defines the symbol; and the plugin
   DLL named by --plugin-dll (the Debug compile) does not carry the marker.
5. Mutants on COPIES of the generated text; each must fail its target case
   and pass its control. Tracked files are never written.

    python tools/tests/card-draw-hooks/run_hooks.py --plugin-dll <dll> [--decompile DIR]
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
SOURCE = os.path.join(PLUGIN, "CardDrawEvidence.cs")
DEFAULT_DECOMPILE = os.path.join(os.path.dirname(REPO), "SidsCompetitiveRounds", "logs-snapshot", "decompiled", "full")
MARKER = "SCR_CARD_EVIDENCE_TEST_GATE_ON"
SYMBOL = "SCR_CARD_EVIDENCE_TEST_GATE"
TRACKED = ["CardDrawEvidence.cs", "GameStateWatcher.cs", "HitEvidence.cs", "Plugin.cs", "SeatEvidence.cs"]

EXPECTED = sorted([
    "CardDrawEvidence_StartPickPatch", "CardDrawEvidence_CardAwakePatch", "CardDrawEvidence_EndPickPatch",
    "CardDrawEvidence_DonePickingPatch", "CardDrawEvidence_PickPatch", "CardDrawEvidence_OfflinePickPatch",
])

# file -> [(literal call, exact count)]: the shared-file wiring
WIRING = {
    "GameStateWatcher.cs": [("CardDrawEvidence.Dispatch(", 2)],
    "HitEvidence.cs": [("CardDrawEvidence.RoomExit(", 1)],
    # fix pass 1: the card builds run on the tick (F4) above the modDisabled
    # return, and the quit hook flushes them (no later frame comes)
    "Plugin.cs": [("CardDrawEvidence.BootLine(", 1), ("CardDrawEvidence.EnsureCensusDump(", 1),
                  ("CardDrawEvidence.Tick(", 1), ("CardDrawEvidence.FlushOnQuit(", 1)],
    "SeatEvidence.cs": [('ROUTE_CARD = "/api/v1/matches/card-evidence";', 1), ('route == "k" ? ROUTE_CARD', 1),
                        ("internal static bool EnqueueCard(string body)", 1), ("CardDrawEvidence", 0)],
    # fix pass 1, the card path's repeat of the seat pattern: its one queue
    # call is checked (queued only after the durable replacement, F8), its
    # builds wait for no live combat (F3) and a completed identity (F7)
    "CardDrawEvidence.cs": [("SeatEvidence.EnqueueCard(", 1), ("if (!SeatEvidence.EnqueueCard(p.Env))", 1),
                            ("if (SeatEvidence.CombatLive()) return;", 1), ("if (!IdentityReadyOrStart(now)) return;", 1)],
}

HEADER = "using System;\nusing HarmonyLib;\n\nnamespace CompetitiveRounds\n{\n"

PICK_PRE = "private static void Prefix(ApplyCardStats __instance, int[] __0, bool __runOriginal)\n        {\n            try { CardDrawEvidence.PickApplied(__instance, __0, __runOriginal); } catch { }\n        }"
GATE_ELSE = "#else\n                return false;"

# (name, old, new, target, control); old must occur exactly once in Hooks.g.cs
MUTANTS = [
    ("startpick_unwrapped", "try { CardDrawEvidence.PhaseStarted(__instance); } catch { }", "CardDrawEvidence.PhaseStarted(__instance);",
     "CardDrawEvidence_StartPickPatch", "CardDrawEvidence_CardAwakePatch"),
    ("awake_unwrapped", "try { CardDrawEvidence.CardAwake(__instance); } catch { }", "CardDrawEvidence.CardAwake(__instance);",
     "CardDrawEvidence_CardAwakePatch", "CardDrawEvidence_StartPickPatch"),
    ("endpick_unwrapped", "try { CardDrawEvidence.EndPick(__0, __1, __2, __3); } catch { }", "CardDrawEvidence.EndPick(__0, __1, __2, __3);",
     "CardDrawEvidence_EndPickPatch", "CardDrawEvidence_DonePickingPatch"),
    ("donepicking_unwrapped", "try { CardDrawEvidence.DonePicking(); } catch { }", "CardDrawEvidence.DonePicking();",
     "CardDrawEvidence_DonePickingPatch", "CardDrawEvidence_EndPickPatch"),
    ("pick_unwrapped", "try { CardDrawEvidence.PickApplied(__instance, __0, __runOriginal); } catch { }",
     "CardDrawEvidence.PickApplied(__instance, __0, __runOriginal);", "CardDrawEvidence_PickPatch", "CardDrawEvidence_OfflinePickPatch"),
    ("offline_unwrapped", "try { CardDrawEvidence.OfflinePickApplied(__instance, __0, __runOriginal); } catch { }",
     "CardDrawEvidence.OfflinePickApplied(__instance, __0, __runOriginal);", "CardDrawEvidence_OfflinePickPatch", "CardDrawEvidence_PickPatch"),
    ("pick_skips_original", PICK_PRE,
     "private static bool Prefix(ApplyCardStats __instance, int[] __0, bool __runOriginal)\n        {\n            try { CardDrawEvidence.PickApplied(__instance, __0, __runOriginal); } catch { }\n            return false;\n        }",
     "CardDrawEvidence_PickPatch", "CardDrawEvidence_OfflinePickPatch"),
    ("pick_runoriginal_by_ref", "int[] __0, bool __runOriginal)", "int[] __0, ref bool __runOriginal)",
     "CardDrawEvidence_PickPatch", "CardDrawEvidence_OfflinePickPatch"),
    ("endpick_args_swapped", "CardDrawEvidence.EndPick(__0, __1, __2, __3)", "CardDrawEvidence.EndPick(__0, __2, __1, __3)",
     "CardDrawEvidence_EndPickPatch", "CardDrawEvidence_DonePickingPatch"),
    ("offline_flag_constant", "CardDrawEvidence.OfflinePickApplied(__instance, __0, __runOriginal)", "CardDrawEvidence.OfflinePickApplied(__instance, __0, true)",
     "CardDrawEvidence_OfflinePickPatch", "CardDrawEvidence_PickPatch"),
    ("donepicking_calls_nothing", "try { CardDrawEvidence.DonePicking(); } catch { }", "try { } catch { }",
     "CardDrawEvidence_DonePickingPatch", "CardDrawEvidence_EndPickPatch"),
    ("startpick_priority_dropped", "    [HarmonyPriority(Priority.Last)]\n    internal static class CardDrawEvidence_StartPickPatch",
     "    internal static class CardDrawEvidence_StartPickPatch", "CardDrawEvidence_StartPickPatch", "CardDrawEvidence_PickPatch"),
    ("endpick_wrong_target", '[HarmonyPatch(typeof(CardChoice), "RPCA_DoEndPick")]', '[HarmonyPatch(typeof(CardChoice), "RPCA_DonePicking")]',
     "CardDrawEvidence_EndPickPatch", "CardDrawEvidence_DonePickingPatch"),
    ("testgate_always_on", GATE_ELSE, '#else\n                Marker = "' + MARKER + '";\n                return true;',
     "testgate-off", "CardDrawEvidence_PickPatch"),
]


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
    """Every [HarmonyPatch]-attributed class (any further attribute lines
    included), from its first attribute line to its closing brace, verbatim."""
    out = []
    for m in re.finditer(r"(?m)^(    \[HarmonyPatch[^\n]*\n(?:    \[[^\n]*\n)*)    internal static class (\w+)\b", text):
        out.append((m.group(2), block_from(text, m.start(1), m.end())))
    return out


def gate_class(text):
    m = re.search(r"(?m)^    internal static class CardDrawEvidenceTestGate\b", text)
    return block_from(text, m.start(), m.end()) if m else None


def generate():
    text = read(SOURCE)
    found = classes(text)
    gate = gate_class(text)
    names = sorted(n for n, _ in found)
    return names, found, gate, HEADER + "\n\n".join(b for _, b in found) + "\n\n" + (gate or "") + "\n}\n"


def build(tag, text, define=""):
    out = os.path.join(WORK, tag)
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "Hooks.g.cs")
    open(src, "wb").write(text.encode("utf-8"))
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep, "-p:HooksSource=" + src]
    if define:
        cmd.append("-p:ExtraDefine=" + define)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-2000:])
        return None
    return os.path.join(out, "bin", "CardDrawHookTests.dll")


def run(dll, cases=()):
    r = subprocess.run(["dotnet", dll] + list(cases), capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def wide(s):
    return s.encode("utf-16-le")


def uncontained(text):
    """Calls into CardDrawEvidence (not CardDrawEvidenceCore) whose nearest
    enclosing block is not a try block. Comment lines are skipped."""
    bad = []
    for m in re.finditer(r"\bCardDrawEvidence\.\w+\(", text):
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


def param_types(sig):
    out = []
    for p in [x.strip() for x in sig.split(",") if x.strip()]:
        p = p.split("=")[0].strip()
        p = re.sub(r"^(ref|out|in|params)\s+", "", p)
        out.append(p.rsplit(None, 1)[0].replace(" ", ""))
    return out


def attachment(found, decompile):
    """Each hook against the decompiled game: the method exists exactly once
    and every __N / __instance parameter has the target's type."""
    lines, ok = [], True
    if not os.path.isdir(decompile):
        return False, ["decompile not found at %s: attachment NOT verified" % decompile]
    for name, body in sorted(found):
        m = re.search(r'\[HarmonyPatch\(typeof\((\w+)\), "(\w+)"\)\]', body)
        typ, meth = m.group(1), m.group(2)
        path = os.path.join(decompile, typ + ".cs")
        if not os.path.isfile(path):
            ok = False
            lines.append("  %s: no decompiled %s.cs" % (name, typ))
            continue
        src = read(path)
        decls = list(re.finditer(r"(?m)^[ \t]*(?:(?:public|private|protected|internal|static|virtual|override|new)\s+)+[\w\.\[\]<>]+\s+" + meth + r"\s*\(([^)]*)\)", src))
        if len(decls) != 1:
            ok = False
            lines.append("  %s: %s.%s declared %d times" % (name, typ, meth, len(decls)))
            continue
        target = param_types(decls[0].group(1))
        decl_line = src.count("\n", 0, decls[0].start()) + 1
        hm = re.search(r"private static void (?:Prefix|Postfix)\(([^)]*)\)", body)
        errs = []
        for p in [x.strip() for x in hm.group(1).split(",") if x.strip()]:
            t, n = p.rsplit(None, 1)
            t = t.replace("ref ", "").replace(" ", "")
            if n == "__instance":
                if t != typ:
                    errs.append("__instance is %s" % t)
            elif re.match(r"__\d+$", n):
                i = int(n[2:])
                if i >= len(target) or target[i] != t:
                    errs.append("%s is %s, target has %s" % (n, t, target[i] if i < len(target) else "none"))
            elif n != "__runOriginal":
                errs.append("unexpected parameter %s" % n)
        ok = ok and not errs
        lines.append("  %s -> %s.%s(%s) [%s:%d]: %s" % (name, typ, meth, ", ".join(target), os.path.basename(path),
                     decl_line, "ATTACHES" if not errs else "MISMATCH " + "; ".join(errs)))
    return ok, lines


def main():
    plugin_dll = None
    decompile = DEFAULT_DECOMPILE
    if "--plugin-dll" in sys.argv:
        plugin_dll = sys.argv[sys.argv.index("--plugin-dll") + 1]
    if "--decompile" in sys.argv:
        decompile = sys.argv[sys.argv.index("--decompile") + 1]
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("commit", head)
    before = {f: sha(os.path.join(PLUGIN, f)) for f in TRACKED}
    ok = True

    names, found, gate, text = generate()
    print("hook classes found:", len(names))
    if names != EXPECTED:
        print("BAD hook set: missing", sorted(set(EXPECTED) - set(names)), "unexpected", sorted(set(names) - set(EXPECTED)))
        ok = False
    if gate is None:
        print("BAD: CardDrawEvidenceTestGate not found")
        ok = False

    # the boot line's table names the same six hooks
    src = read(SOURCE)
    table = sorted(re.findall(r'new\[\] \{ "C\d", "(\w+)", "(\w+)", "(\w+)" \}', src))
    attrs = sorted((re.search(r'typeof\((\w+)\), "(\w+)"', b).group(1), re.search(r'typeof\((\w+)\), "(\w+)"', b).group(2), n) for n, b in found)
    table_ok = table == attrs and len(table) == 6
    print("boot line table matches the hook classes:", table_ok)
    ok = ok and table_ok

    aok, alines = attachment(found, decompile)
    print("attachment against the decompiled game (%s):" % decompile)
    print("\n".join(alines))
    ok = ok and aok

    # collector entries: the body in its own try, the fault counted in its row
    entries = re.findall(r"try \{ C(\d)\([^;]*\); \} catch \(Exception ex\) \{ Fault\((\d), ex\); \}\n\s*Cost\((\d), t0\);", src)
    entry_ok = sorted(int(c) for c, _, _ in entries) == [1, 2, 3, 4, 5, 6] and all(int(c) - 1 == int(f) == int(k) for c, f, k in entries)
    print("collector entries contained and fault-counted (C1..C6):", entry_ok)
    ok = ok and entry_ok

    # call sites in the other plugin files, plus negative controls
    sites_ok = True
    for f in sorted(os.listdir(PLUGIN)):
        if not f.endswith(".cs") or f in ("CardDrawEvidence.cs", "CardDrawEvidenceCore.cs"):
            continue
        bad = uncontained(read(os.path.join(PLUGIN, f)))
        if bad:
            print("UNCONTAINED CardDrawEvidence call in plugin/%s at lines %s" % (f, bad))
            sites_ok = False
    gsw = read(os.path.join(PLUGIN, "GameStateWatcher.cs"))
    ctrl = (len(uncontained("void F() { CardDrawEvidence.RoomExit(); }")) == 1
            and not uncontained("void F() { try { CardDrawEvidence.RoomExit(); } catch { } }")
            and len(uncontained(gsw.replace("try { CardDrawEvidence.Dispatch(", "{ CardDrawEvidence.Dispatch(", 1))) == 1)
    print("call sites contained:", sites_ok, "; negative controls flagged:", ctrl)
    ok = ok and sites_ok and ctrl

    wiring_ok = True
    for f, checks in WIRING.items():
        t = read(os.path.join(PLUGIN, f))
        for lit, n in checks:
            c = t.count(lit)
            if c != n:
                wiring_ok = False
                print("WIRING plugin/%s: %r occurs %d times, want %d" % (f, lit, c, n))
    print("shared-file wiring present exactly once per site:", wiring_ok)
    ok = ok and wiring_ok

    dll = build("base", text)
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    rc, out = run(dll)
    print(out)
    ok = ok and rc == 0

    # L3: the test gate, off by default, on only under its own symbol
    rc_off, out_off = run(dll, ["testgate-off"])
    gdll = build("gate_on", text, SYMBOL)
    rc_on, out_on = (1, "BUILD FAILED") if gdll is None else run(gdll, ["testgate-on"])
    off_bytes = open(dll, "rb").read()
    on_bytes = open(gdll, "rb").read() if gdll else b""
    l3_probe = rc_off == 0 and rc_on == 0 and wide(MARKER) not in off_bytes and wide(MARKER) in on_bytes
    print("L3 gate off by default:", out_off, "| under %s:" % SYMBOL, out_on,
          "| marker absent/present:", wide(MARKER) not in off_bytes, wide(MARKER) in on_bytes)
    defined = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in (".git", "bin", "obj", "work", "ai-collab", "node_modules")]
        for fn in files:
            if fn.endswith((".csproj", ".props", ".targets", ".rsp", ".sln")) or (fn.endswith(".cs") and os.path.dirname(os.path.join(root, fn)) == PLUGIN):
                p = os.path.join(root, fn)
                body = open(p, "rb").read().decode("utf-8", "replace")
                if (fn.endswith(".cs") and re.search(r"#define\s+" + SYMBOL, body)) or (not fn.endswith(".cs") and SYMBOL in body):
                    defined.append(os.path.relpath(p, REPO))
    print("files defining %s:" % SYMBOL, defined if defined else "none")
    l3_plugin = False
    if plugin_dll and os.path.isfile(plugin_dll):
        pb = open(plugin_dll, "rb").read()
        sanity = wide("[CARD-EV]") in pb
        l3_plugin = sanity and wide(MARKER) not in pb and MARKER.encode("ascii") not in pb
        print("plugin DLL %s (%d bytes, sha256 %s): carries the card evidence code %s; marker absent %s" % (
            plugin_dll, len(pb), hashlib.sha256(pb).hexdigest(), sanity, wide(MARKER) not in pb and MARKER.encode("ascii") not in pb))
    else:
        print("plugin DLL scan NOT RUN (pass --plugin-dll <the Debug compile's DLL>)")
    l3 = l3_probe and not defined and l3_plugin
    print("L3:", "PASS" if l3 else "FAIL")
    ok = ok and l3

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
    unchanged = all(sha(os.path.join(PLUGIN, f)) == before[f] for f in TRACKED)
    print("tracked plugin files unchanged:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
