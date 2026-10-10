"""Item 19 fix pass 1: the per-finding controls of the Codex BUILD round 1
report (ai-collab/v1410/CODEX-ITEM19-BUILD-R1-REPORT.md), one per finding, run
against ANY tree, so the same script shows each control RED on the build
round 1 tree (e76cb8f0) and GREEN on the fix tip.

Kinds of control:
  source   a structural gate over the tree's plugin/*.cs
  probe    the behaviour scenarios of probe/Probe.cs, compiled against the
           tree's own plugin/AvatarDefaultRules.cs
  suite    a mutation of the tree's production source (or of a copy of the
           local decompile) run against the tree's OWN tests: GREEN only when
           the tree's tests go red on the mutation AND stay green on its inert
           twin and on the unmutated baseline (#391, #342); since fix pass 2
           the red must be a claim failing, never only a test's own in-test
           scaffolding losing its anchor (classify_failures)
  log      the certifying evidence for the tree's commit in the lane's
           evidence folder (logs headed "commit <sha> tree clean")

Fix pass 2 (Codex BUILD round 2, ai-collab/v1410/CODEX-ITEM19-BUILD-R2-REPORT.md)
adds two kinds, and re-judges H3 H6 H9 M3 M8 M10 M11 L1 BR-M4 (the FIX2 set,
each red on the round 2 tree 49434006 and green on the fix tip):
  prodprobe  prodprobe/ compiled against the tree's PRODUCTION
             plugin/AvatarDefaults.cs and AvatarDefaultRules.cs (the fix tip's
             probe: the behaviour the tree's production code has)
  tipclaim   one of the fix tip's own source claims run over the tree's
             sources (the behaviour, where the code is Plugin.cs)
and extends "suite": every named closure's production expression is mutated
and the tree's OWN tests (its pytest, which runs its own prodprobe at S35,
and its harness) must go red, and stay green on a neighbouring twin.

Nothing is edited in the tree: every build and every mutation happens in
copies under --work. No path is hard-coded; the caller names every directory.

Subcommands:
  controls --root TREE --evidence DIR --decompiled DIR --work DIR
  binds PLUGIN_CS OUT_JSON            the Config.Bind list (M10's witness input)
  cfgwitness --root TREE --bepinex-core DIR [--managed DIR] --work DIR
             [--old-root TREE --real-cfg FILE]   the real-config upgrade (fix pass 2)
  tally PYTEST_V_LOG                  every executed node, summed against the summary
  plant DLL OUT                       a copy with a UTF-16LE local-path marker
                                      at an odd offset (the scanner's negative control)
  compare TIP_LOG BASE_LOG            the affected-set comparison (BR-M2)

Exit: 0 only when every control is GREEN (controls), or the step's own
verdict passed (the other subcommands).
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LANE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(LANE, "backend", "tests"))
from _cs_structure import mask_code, strip_comments_only  # noqa: E402

ITEMS = ["H3", "H6", "H8", "H9", "M3", "M8", "M10", "M11", "L1",
         "BR-H1", "BR-M1", "BR-M2", "BR-M3", "BR-M4", "BR-M5", "BR-L1", "BR-L2"]
# the items the round 2 review left PARTLY (fix pass 2): each must be red on
# the round 2 tree and green on the fix tip; the rest were closed and must
# stay green on the fix tip
FIX2 = ["H3", "H6", "H9", "M3", "M8", "M10", "M11", "L1", "BR-M4"]


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def read(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def sha256(path, n=16):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:n]


def block_after(text, sig, start=0):
    """(open, close+1) of the brace block after the FIRST `sig` at/after start,
    measured on the masked text (offsets are kept)."""
    m = mask_code(text)
    i = m.find(sig, start)
    if i < 0:
        return None
    ob = m.find("{", i + len(sig))
    depth = 0
    for j in range(ob, len(m)):
        if m[j] == "{":
            depth += 1
        elif m[j] == "}":
            depth -= 1
            if depth == 0:
                return ob, j + 1
    return None


def method_body(text, sig, within=None):
    base = 0
    if within is not None:
        span = block_after(text, within)
        if span is None:
            return None
        base = span[0]
        text = text[span[0]:span[1]]
    span = block_after(text, sig)
    if span is None:
        return None
    return strip_comments_only(text[span[0]:span[1]])


def run(cmd, env=None, cwd=None):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                       encoding="utf-8", errors="replace", env=env, cwd=cwd)
    return p.returncode, p.stdout


def git_head(root):
    rc, out = run(["git", "-C", root, "rev-parse", "HEAD"])
    return out.strip() if rc == 0 else None


# ---------------------------------------------------------------------------
# source gates
# ---------------------------------------------------------------------------

def src_h3(root):
    t = read(os.path.join(root, "plugin", "Plugin.cs"))
    cls = block_after(t, "internal static class FacePublisher")
    if cls is None:
        return False, "no FacePublisher class"
    seg = t[cls[0]:cls[1]]
    # fix pass 2: the body lives behind the out overload when there is one
    m = re.search(r"public static \w+ PublishLocal\(out string \w+\)", seg) or re.search(r"public static \w+ PublishLocal\(\)", seg)
    if not m:
        return False, "no PublishLocal"
    body = method_body(seg, m.group(0))
    code = mask_code(body)
    bare = len(re.findall(r"\breturn\s*;", code))
    clears = body.count("[PROP_FACE] = null;")
    sets = body.count("SetCustomProperties(")
    ok = bare == 0 and clears == 1 and sets == 2 and "CarrierAction(" in body
    return ok, ("PublishLocal: bare returns=%d, carrier clears=%d, SetCustomProperties calls=%d, "
                "central decision=%s" % (bare, clears, sets, "CarrierAction(" in body))


HOOKS = (("AvatarLoadFacesPatch", "private static void Postfix()"),
         ("AvatarSelectFacePatch", "private static void Postfix(int faceID)"),
         ("AvatarCreatePlayerPatch", "private static void Prefix()"))


def hook_is_one_boundary(text, cls, sig):
    body = method_body(text, sig, "internal static class " + cls)
    if body is None:
        return False, cls + ": not found"
    inner = body.strip()[1:-1]
    m = mask_code(inner)
    s = m.strip()
    lead = len(m) - len(m.lstrip())
    if not s.startswith("try"):
        return False, cls + ": the body does not start with try"
    span = block_after(inner, "try", lead)
    rest_m = m[span[1]:]
    rest = inner[span[1]:]
    mm = re.match(r"\s*catch\s*\(\s*Exception\s+\w+\s*\)\s*", rest_m)
    if not mm:
        return False, cls + ": no catch (Exception) right after the try block"
    cspan = block_after(rest, "catch")
    tail = rest_m[cspan[1]:].strip()
    cbody = rest[cspan[0]:cspan[1]]
    safe = "Plugin.Log." not in cbody and "AvatarDefaults.Warn(" in cbody
    if tail:
        return False, cls + ": statements after the catch"
    return safe, cls + ": one try/catch boundary, catch logger-safe=" + str(safe)


def src_brm1(root):
    t = read(os.path.join(root, "plugin", "AvatarDefaults.cs"))
    parts = [hook_is_one_boundary(t, c, s) for c, s in HOOKS]
    warn = method_body(t, "internal static void Warn(string msg)", "internal static class AvatarDefaults")
    warn_ok = warn is not None and "try" in warn and "catch" in warn
    ok = all(p[0] for p in parts) and warn_ok
    return ok, "; ".join(p[1] for p in parts) + "; Warn is guarded=" + str(warn_ok)


def src_brh1(root):
    t = read(os.path.join(root, "plugin", "AvatarDefaultRules.cs"))
    body = method_body(t, "internal virtual AvatarFacing FacingOf(AvatarFacingIn f)")
    if body is None:
        return False, "no FacingOf"
    reads = "ModIssuedRoom" in mask_code(body)
    return not reads, "FacingOf reads the room's provenance=" + str(reads)


def src_m8(root):
    t = read(os.path.join(root, "plugin", "AvatarDefaults.cs"))
    body = method_body(t, "internal static void Evaluate(string tag)", "internal static class AvatarDefaults")
    if body is None:
        return False, "no Evaluate"
    guard = body.find("rules.LogsClassification(tag)")
    ret = body.find("if (d.Apply < 0) return;")
    log = body.find("Plugin.Log.LogInfo(rules.ClassificationLine(")
    ok = guard >= 0 and log > guard and ret > log
    return ok, ("a classification line on room edges before the no-apply return: guard=%s log=%s return-after=%s"
                % (guard >= 0, log >= 0, ret > log >= 0))


# ---------------------------------------------------------------------------
# the probe
# ---------------------------------------------------------------------------

def build_probe(root, work, out):
    d = os.path.join(work, "probe")
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    for f in ("Probe.cs", "item19-probe.csproj"):
        shutil.copyfile(os.path.join(HERE, "probe", f), os.path.join(d, f))
    shutil.copyfile(os.path.join(root, "plugin", "AvatarDefaultRules.cs"), os.path.join(d, "AvatarDefaultRules.cs"))
    rc, o = run(["dotnet", "build", os.path.join(d, "item19-probe.csproj"), "-c", "Release", "-nologo", "-v", "q"])
    out.write("--- probe build exit %d ---\n%s\n" % (rc, o[-3000:]))
    if rc != 0:
        return {}
    dll = os.path.join(d, "bin", "Release", "net10.0", "item19-probe.dll")
    rc, o = run(["dotnet", dll])
    out.write("--- probe run exit %d ---\n%s\n" % (rc, o))
    res = {}
    for line in o.splitlines():
        m = re.match(r"PROBE (\S+) (PASS|FAIL) \| (.*)$", line)
        if m:
            res[m.group(1)] = (m.group(2) == "PASS", m.group(3))
    return res


# ---------------------------------------------------------------------------
# suite mutations: the tree's own harness
# ---------------------------------------------------------------------------

def harness_compile_set(root):
    proj = read(os.path.join(root, "tools", "client-rules-harness", "client-rules-harness.csproj"))
    plugin, local = [], []
    for inc in re.findall(r'<Compile Include="([^"]+)"', proj):
        inc = inc.replace("\\", "/")
        if inc.startswith("../../plugin/"):
            plugin.append(inc[len("../../plugin/"):])
        else:
            local.append(inc)
    return plugin, local + ["client-rules-harness.csproj"]


def harness_run(root, work, label, edit, out):
    # A short build directory (fix pass 2). The label-named one put the SDK's
    # apphost (obj/Release/net10.0/apphost.exe) past the Windows path limit
    # for the longest labels: H3-rule-reread-twin (247 characters) and
    # H9-rule-deferral-twin (249) failed with MSB3030, which read as "None on
    # the twin"; 244 built. The label stays in every line written.
    d = os.path.join(work, "h-" + hashlib.sha256(label.encode("utf-8")).hexdigest()[:8])
    host = os.path.join(os.path.abspath(d), "tools", "client-rules-harness", "obj", "Release", "net10.0", "apphost.exe")
    if len(host) > 240:
        out.write("--- harness %s: build path %d characters, over 240 (the apphost would not be written) ---\n"
                  % (label, len(host)))
        return None
    if os.path.isdir(d):
        shutil.rmtree(d)
    plugin, local = harness_compile_set(root)
    for f in plugin:
        dst = os.path.join(d, "plugin", f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(root, "plugin", f), dst)
    for f in local:
        dst = os.path.join(d, "tools", "client-rules-harness", f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(root, "tools", "client-rules-harness", f), dst)
    if edit is not None:
        ok, why = apply_edit(os.path.join(d, "plugin", edit[0]), edit[1], edit[2], edit[3])
        if not ok:
            out.write("--- harness %s: edit refused: %s ---\n" % (label, why))
            return None
    proj = os.path.join(d, "tools", "client-rules-harness", "client-rules-harness.csproj")
    rc, o = run(["dotnet", "build", proj, "-c", "Release", "-nologo", "-v", "q"])
    if rc != 0:
        out.write("--- harness %s build exit %d ---\n%s\n" % (label, rc, o[-3000:]))
        return None
    dll = os.path.join(d, "tools", "client-rules-harness", "bin", "Release", "net10.0", "client-rules-harness.dll")
    rc, o = run(["dotnet", dll])
    fails = [l for l in o.splitlines() if l.startswith("[avatardefaults] FAIL")]
    summ = [l for l in o.splitlines() if l.startswith("[avatardefaults] ") and " run=" in l]
    out.write("--- harness %s run exit %d: avatardefaults FAIL lines %d %s ---\n" % (label, rc, len(fails), summ[-1:] if summ else ""))
    for l in fails[:6]:
        out.write("    " + l[:300] + "\n")
    return len(fails)


def apply_edit(path, sig, anchor, replacement):
    t = read(path)
    span = block_after(t, sig)
    if span is None:
        return False, "signature %r not found" % sig
    a, b = span
    seg = t[a:b]
    if seg.count(anchor) != 1:
        return False, "anchor %r occurs %d times inside %r" % (anchor, seg.count(anchor), sig)
    nl = "\r\n" if "\r\n" in t else "\n"
    write(path, t[:a] + seg.replace(anchor, replacement.replace("\n", nl)) + t[b:])
    return True, ""


AR = "AvatarDefaultRules.cs"
LIVE = "internal virtual bool Live(AvatarLivenessIn l)"
FACING = "internal virtual AvatarFacing FacingOf(AvatarFacingIn f)"
H6_ROWS = [
    ("isPlaying", (AR, LIVE, "(l.IsPlaying || l.BattleOngoing)", "(l.BattleOngoing)")),
    ("battleOngoing", (AR, LIVE, "(l.IsPlaying || l.BattleOngoing)", "(l.IsPlaying)")),
    ("local body", (AR, LIVE, ": l.LocalBodyExists;", ": false;")),
]
H6_TWIN = (AR, LIVE, "(l.IsPlaying || l.BattleOngoing)", "(l.BattleOngoing || l.IsPlaying)")
H8_ROW = (AR, FACING, "var others = f.OtherFighterKeys;",
          "if (f.ModIssuedRoom) return AvatarFacing.Modded;\n            var others = f.OtherFighterKeys;")
H8_TWIN = (AR, FACING, "var others = f.OtherFighterKeys;",
           "if (f.ModIssuedRoom && f.OtherFighterKeys == null && f.FaceKey == null && !f.InRoom) return AvatarFacing.Modded;\n            var others = f.OtherFighterKeys;")


# ---------------------------------------------------------------------------
# suite mutations: the tree's own source claims (pytest)
# ---------------------------------------------------------------------------

DECOMPILED_FILES = ("CharacterCreatorItemLoader.cs", "CharacterCreatorItemEquipper.cs",
                    "CardChoiceVisuals.cs", "PlayerFace.cs")


def claims_run(root, work, label, edit, decompiled, out, decompile_edit=None, tests_from=None, select=None):
    """The tree's own source claims (or, with tests_from, ANOTHER tree's
    test file run over this tree's sources) against an optional mutation.
    `edit` is (file, old, new) or a list of them, each anchor exactly once.
    The tree's own prodprobe (S35) is copied when the tree has one."""
    d = os.path.join(work, "claims-" + label)
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(os.path.join(d, "plugin"))
    os.makedirs(os.path.join(d, "backend", "tests"))
    os.makedirs(os.path.join(d, "tools"))
    for f in os.listdir(os.path.join(root, "plugin")):
        if f.endswith(".cs"):
            shutil.copyfile(os.path.join(root, "plugin", f), os.path.join(d, "plugin", f))
    tests_root = tests_from or root
    for f in ("test_client_avatar_defaults.py", "_cs_structure.py"):
        shutil.copyfile(os.path.join(tests_root, "backend", "tests", f), os.path.join(d, "backend", "tests", f))
    shutil.copyfile(os.path.join(root, "tools", "i18n_source.json"), os.path.join(d, "tools", "i18n_source.json"))
    pp = os.path.join(tests_root, "tools", "item19-controls", "prodprobe")
    if os.path.isdir(pp):
        dst = os.path.join(d, "tools", "item19-controls", "prodprobe")
        os.makedirs(dst)
        for f in ("Stubs.cs", "ProdProbe.cs", "item19-prodprobe.csproj"):
            shutil.copyfile(os.path.join(pp, f), os.path.join(dst, f))
    edits = [] if edit is None else (list(edit) if isinstance(edit, list) else [edit])
    for e in edits:
        path = os.path.join(d, "plugin", e[0])
        t = read(path)
        if t.count(e[1]) != 1:
            out.write("--- claims %s: anchor occurs %d times in %s ---\n" % (label, t.count(e[1]), e[0]))
            return None
        write(path, t.replace(e[1], e[2]))
    dec = os.path.join(d, "decompiled")
    os.makedirs(dec)
    for f in DECOMPILED_FILES:
        src = os.path.join(decompiled, f)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(dec, f))
    if decompile_edit is not None:
        path = os.path.join(dec, decompile_edit[0])
        with open(path, "rb") as f:
            b = f.read()
        lines = b.split(b"\n")
        i = decompile_edit[1] - 1
        lines[i] = lines[i] + b" // changed"
        with open(path, "wb") as f:
            f.write(b"\n".join(lines))
    env = dict(os.environ)
    env["SCR_DECOMPILED_DIR"] = dec
    # --tb=short: every frame prints as "path:line: in func" plus its source
    # line, which is what classify_failures reads
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--noconftest", "--tb=short",
           os.path.join(d, "backend", "tests", "test_client_avatar_defaults.py")]
    if select:
        cmd += ["-k", select]
    rc, o = run(cmd, env=env, cwd=d)
    tail = [l for l in o.splitlines() if re.search(r"\b(passed|failed|error)", l)]
    failed = [l for l in o.splitlines() if l.startswith(("FAILED ", "ERROR "))]
    out.write("--- claims %s exit %d%s: %s ---\n" % (label, rc, (" (-k %s)" % select) if select else "",
                                                     tail[-1] if tail else "(no summary)"))
    for l in failed[:6]:
        out.write("    " + l[:400] + "\n")
    claims_run.last_failed = failed
    genuine, scaffold, unread = classify_failures(o, failed)
    claims_run.last_genuine = genuine
    if failed:
        out.write("    the claim itself failed in %d; the test's own scaffolding alone in %d%s; unread %d%s\n"
                  % (len(genuine), len(scaffold), (" (" + ", ".join(scaffold[:4]) + ")") if scaffold else "",
                     len(unread), (" (" + ", ".join(unread[:4]) + ")") if unread else ""))
    if rc == 5:
        # pytest's "no tests collected": the tree has no test that binds the
        # claim, which is neither a catch nor a pass
        out.write("    no test of this tree matches the selection: not a catch\n")
        return None
    return rc


claims_run.last_failed = []
claims_run.last_genuine = []


def classify_failures(o, failed):
    """Fix pass 2 (M8, from the relaunched sitting's red dev run): which of a
    claims run's failures are the CLAIM failing on the mutated tree.

    The tree's three-way helper _check(claim, mutation, control) first runs
    claim(src) over the tree as given, then its OWN in-test mutation and
    control. A production mutation that deletes the text an in-test mutation
    anchors on fails the test inside that scaffolding (_replace: "edit anchor
    ... occurs 0 times") while the claim itself passed: the claim never read
    what was removed, so that is not a catch. Only a failure raised from
    _check's first call (claim(src)), or from a test that does not use
    _check, counts. A parse failure is never the claim's red (the helper's
    own rule). An ERROR entry (setup or collection: the tree's own probe
    fixture on the mutated tree) is kept as before. A FAILED entry whose
    block cannot be read is never counted (fail closed).
    Returns (genuine, scaffold, unread), lists of test names."""
    blocks = {}
    for sec in re.finditer(r"^=+ (?:FAILURES|ERRORS) =+[ \t]*$(.*?)(?=^=+ |\Z)", o, re.M | re.S):
        parts = re.split(r"^_{3,} (.+?) _{3,}[ \t]*$", sec.group(1), flags=re.M)
        for i in range(1, len(parts) - 1, 2):
            blocks[parts[i].strip()] = parts[i + 1]
    genuine, scaffold, unread = [], [], []
    for line in failed:
        kind, rest = line.split(" ", 1)
        name = rest.split(" - ", 1)[0].strip().split("::")[-1]
        if kind == "ERROR":
            genuine.append(name)
            continue
        b = blocks.get(name)
        if b is None:
            unread.append(name)
            continue
        elines = "\n".join(x for x in b.splitlines() if x.startswith("E "))
        m = re.search(r": in _check[ \t]*\r?\n[ \t]+(\S[^\r\n]*)", b)
        if "CsParseError" in elines or (m is not None and m.group(1).strip() != "claim(src)"):
            scaffold.append(name)
        else:
            genuine.append(name)
    return genuine, scaffold, unread


def prodprobe_run(probe_root, root, work, label, out, edit=None):
    """probe_root's prodprobe compiled against root's PRODUCTION
    AvatarDefaults.cs and AvatarDefaultRules.cs (with an optional edit).
    {id: (pass, detail)}, or None when it cannot be built or run."""
    pp = os.path.join(probe_root, "tools", "item19-controls", "prodprobe")
    if not os.path.isdir(pp):
        out.write("--- prodprobe %s: %s has no prodprobe ---\n" % (label, probe_root))
        return None
    d = os.path.join(work, "prodprobe-" + label)
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    for f in ("Stubs.cs", "ProdProbe.cs", "item19-prodprobe.csproj"):
        shutil.copyfile(os.path.join(pp, f), os.path.join(d, f))
    for f in (AD, AR):
        shutil.copyfile(os.path.join(root, "plugin", f), os.path.join(d, f))
    for e in ([] if edit is None else (edit if isinstance(edit, list) else [edit])):
        path = os.path.join(d, e[0])
        t = read(path)
        if t.count(e[1]) != 1:
            out.write("--- prodprobe %s: anchor occurs %d times ---\n" % (label, t.count(e[1])))
            return None
        write(path, t.replace(e[1], e[2]))
    rc, o = run(["dotnet", "build", os.path.join(d, "item19-prodprobe.csproj"), "-c", "Release", "-nologo", "-v", "q"])
    if rc != 0:
        out.write("--- prodprobe %s build exit %d ---\n%s\n" % (label, rc, o[-3000:]))
        return None
    rc, o = run(["dotnet", os.path.join(d, "bin", "Release", "net10.0", "item19-prodprobe.dll")])
    out.write("--- prodprobe %s run exit %d ---\n%s\n" % (label, rc, o.rstrip()))
    res = {}
    for line in o.splitlines():
        m = re.match(r"PROBE (\S+) (PASS|FAIL) \| (.*)$", line)
        if m:
            res[m.group(1)] = (m.group(2) == "PASS", m.group(3))
    return res


AD = "AvatarDefaults.cs"
CLAIM_ROWS = {
    # M11: the persistence proof (the decompiled PlayerFace persistence body)
    "M11-persistence": dict(decompile_edit=("PlayerFace.cs", 25), twin_decompile_edit=("PlayerFace.cs", 20)),
    # M11 / L1: the exact assignment the nametag citation names (line-bound)
    "M11-assignment": dict(edit=("NametagStyler.cs", "                string styled = Wrap(_baseName, skus);",
                                 "\n                string styled = Wrap(_baseName, skus);"),
                           # the twin must not touch the claim's own control anchor
                           # (S30's control edits the "keep fresh" comment)
                           twin=("NametagStyler.cs", "// leaked artifacts. Batch both into one SetCustomProperties call",
                                 "// leaked artifacts. Batch the two into one SetCustomProperties call")),
    # M11: the refusal citation (the 2v2 patch's already-spawned refusal)
    "M11-refusal": dict(edit=("Plugin.cs", "if (__instance.hasCreatedLocalPlayer) return false;     // already done",
                              "// already done"),
                        # the twin must not touch the claim's own control anchor
                        # (S31's control edits the refusal's comment)
                        twin=("Plugin.cs", "// not a team-mode spawn", "// not a team spawn")),
    # L1: the dual ring (two bands)
    "L1-ring": dict(edit=(AD, "edge < 6 ? inner : clear", "edge < 6 ? outer : clear"),
                    twin=(AD, "            const int size = 64;", "            // two bands, outer then inner\n            const int size = 64;")),
    # L1: the hybrid (both-defaults) ring
    "L1-hybrid": dict(edit=(AD, 'RingSprite("CR_AvRingBoth", gold, blue)', 'RingSprite("CR_AvRingBoth", gold, gold)'),
                      twin=(AD, "            ringsBuilt = true;", "            // all four built\n            ringsBuilt = true;")),
    # L1: the recovery text carried with every refusal
    "L1-recovery": dict(edit=(AD, 'return first + "\\n" + RecoveryInstruction();', "return first;"),
                        twin=(AD, '            return first + "\\n" + RecoveryInstruction();',
                              '            // the recovery instruction rides with it\n            return first + "\\n" + RecoveryInstruction();')),

    # ---- fix pass 2: every named closure mutated at its PRODUCTION expression;
    # the tree's own tests (pytest, with its prodprobe at S35) must go red, and
    # stay green on the neighbouring twin. Single-line anchors (Plugin.cs is CRLF).
    # H3: restore the reread of the cache the pass has just published to
    "H3-reread": dict(edit=("Plugin.cs", "string popupFace = new AvatarRules().PopupFace(picker.IsLocal, carrier, freshFace,",
                            "string popupFace = FacePublisher.ReadCarrier(pickerActor); string unusedFace = new AvatarRules().PopupFace(picker.IsLocal, carrier, freshFace,"),
                      twin=("Plugin.cs", '"the value this pass published"', '"the value published this pass"')),
    # H6: each production liveness assignment (AvatarDefaults.ReadLiveness)
    "H6-isPlaying": dict(edit=(AD, "{ l.IsPlaying = gm.isPlaying; l.BattleOngoing = gm.battleOngoing; }",
                               "{ l.BattleOngoing = gm.battleOngoing; }"),
                         twin=(AD, "{ l.IsPlaying = gm.isPlaying; l.BattleOngoing = gm.battleOngoing; }",
                               "{ l.BattleOngoing = gm.battleOngoing; l.IsPlaying = gm.isPlaying; }")),
    "H6-battleOngoing": dict(edit=(AD, "{ l.IsPlaying = gm.isPlaying; l.BattleOngoing = gm.battleOngoing; }",
                                   "{ l.IsPlaying = gm.isPlaying; }"),
                             twin=(AD, "{ l.IsPlaying = gm.isPlaying; l.BattleOngoing = gm.battleOngoing; }",
                                   "{ l.IsPlaying = gm.isPlaying == true; l.BattleOngoing = gm.battleOngoing == true; }")),
    # H9: the round 2 early return, before the rules see the debt
    "H9-early-return": dict(edit=(AD, "var d = rules.Evaluate(x);",
                                  "if (cch == null || cch.selectedFaceID == null || cch.selectedFaceID.Length == 0 || cch.playerFaces == null) return; var d = rules.Evaluate(x);"),
                            twin=(AD, "var d = rules.Evaluate(x);", "if (tag == null) return; var d = rules.Evaluate(x);")),
    # M3: the deferred-restoration edge removed from the tick
    "M3-deferred-edge": dict(edit=(AD, "try { DeferredRestoration(); } catch { }", ""),
                             twin=(AD, "try { DeferredRestoration(); } catch { }", "try { DeferredRestoration(); } catch (Exception) { }")),
    # M8: each arm of the classification-line guard
    "M8-apply-arm": dict(edit=(AD, "if (d.Apply >= 0 || rules.LogsClassification(tag))", "if (rules.LogsClassification(tag))"),
                         twin=(AD, "                if (d.Apply >= 0 || rules.LogsClassification(tag))",
                               "                // the line's guard: an applied change, or a room edge\n                if (d.Apply >= 0 || rules.LogsClassification(tag))")),
    "M8-room-arm": dict(edit=(AD, "if (d.Apply >= 0 || rules.LogsClassification(tag))", "if (d.Apply >= 0)"),
                        twin=(AD, "                Plugin.Log.LogInfo(rules.ClassificationLine(",
                              "                    // one line per classification\n                    Plugin.Log.LogInfo(rules.ClassificationLine(")),
    # BR-M4: partial assignment in ReadFacing (the first getter committed
    # before the second runs, and the catch no longer resets it)
    "BR-M4-partial": dict(edit=[(AD, "bool inRoom = PhotonNetwork.InRoom;", "f.InRoom = PhotonNetwork.InRoom; bool inRoom = f.InRoom;"),
                                (AD, "catch { f.InRoom = false; f.OfflineMode = false; f.Unreadable = true; return f; }",
                                 "catch { f.Unreadable = true; return f; }")],
                          twin=(AD, "bool inRoom = PhotonNetwork.InRoom;", "bool inRoom = PhotonNetwork.InRoom == true;")),
    # L1: each sink deleted in turn
    "L1-sprite-sink": dict(edit=(AD, "UIFactory.SetImageSprite(ring, spr);", ""),
                           twin=(AD, "ring.transform.SetAsLastSibling();", "ring.transform.SetAsLastSibling(); ring.SetActive(true);")),
    "L1-announce-sink": dict(edit=(AD, "if (d.Unusable != AvatarUnusable.None) Announce(UnusableMessage(d.Unusable));", ""),
                             twin=(AD, "if (d.Unusable != AvatarUnusable.None) Announce(UnusableMessage(d.Unusable));",
                                   "if (AvatarUnusable.None != d.Unusable) Announce(UnusableMessage(d.Unusable));")),
}

# fix pass 2: the tests each row runs (pytest -k). The source-claim rows
# skip S35, whose production probe is a dotnet build per run; the rows whose
# claim lives in the production probe run S35 alone; M8's arms run S22 (the
# production guard expression) and S35 (the production log sink).
CLAIM_SELECT = {n: "not s35" for n in ("M11-persistence", "M11-assignment", "M11-refusal", "L1-ring",
                                       "L1-hybrid", "L1-recovery", "H3-reread")}
CLAIM_SELECT.update({n: "s35" for n in ("H6-isPlaying", "H6-battleOngoing", "H9-early-return",
                                         "M3-deferred-edge", "BR-M4-partial", "L1-sprite-sink",
                                         "L1-announce-sink")})
CLAIM_SELECT.update({n: "s22 or s35" for n in ("M8-apply-arm", "M8-room-arm")})

# fix pass 2: the closures M11 names, by the rows that bind them
M11_CLOSURES = {"H6": ["H6-isPlaying", "H6-battleOngoing"], "M8": ["M8-apply-arm", "M8-room-arm"],
                "BR-M4": ["BR-M4-partial"], "L1": ["L1-sprite-sink", "L1-announce-sink"]}

# fix pass 2: rule-level mutations the tree's own HARNESS must catch
HARNESS2_ROWS = {
    "H3-rule-reread": ((AR, "internal virtual string PopupFace(",
                        "if (pickerIsLocal) return published == FaceCarrierAction.Publish ? publishedValue : null;",
                        "if (pickerIsLocal) return readCarrier != null ? readCarrier() : null;"),
                       (AR, "internal virtual string PopupFace(",
                        "return readCarrier != null ? readCarrier() : null;",
                        "return readCarrier == null ? null : readCarrier();")),
    "H9-rule-deferral": ((AR, "internal virtual AvatarDecision Evaluate(AvatarEvalIn x)",
                          "d.RestorationDeferred = RestorationOwed(", "d.RestorationDeferred = false && RestorationOwed("),
                         (AR, "internal virtual AvatarDecision Evaluate(AvatarEvalIn x)",
                          "d.NothingToRead = true;", "d.NothingToRead = !false;")),
}


# ---------------------------------------------------------------------------
# log gates over the evidence folder
# ---------------------------------------------------------------------------

def logs_for(evidence, sha):
    out = []
    for f in sorted(os.listdir(evidence)):
        if not f.endswith(".log"):
            continue
        p = os.path.join(evidence, f)
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                first = fh.readline().strip()
        except OSError:
            continue
        if first == "commit %s tree clean" % sha:
            out.append(p)
    return out


def text_of(p):
    with open(p, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def log_gate(evidence, sha, needle_re, label):
    hits = [p for p in logs_for(evidence, sha) if re.search(needle_re, text_of(p), re.M)]
    complete = [p for p in hits if re.search(r"^EXIT 0\s*$", text_of(p), re.M)]
    return bool(complete), "%s: %d log(s) for %s carry it, %d complete with EXIT 0 (%s)" % (
        label, len(hits), sha[:8], len(complete), ", ".join(os.path.basename(p) for p in complete) or "none")


def gate_brm5(evidence, sha):
    logs = logs_for(evidence, sha)
    bad, good = [], []
    for p in logs:
        t = text_of(p)
        m = re.search(r"^runner: (\S+) sha256 ([0-9a-f]{16})", t, re.M)
        if not m:
            bad.append(os.path.basename(p) + " (no runner digest)")
            continue
        carried = os.path.join(evidence, m.group(1))
        if not os.path.exists(carried):
            bad.append(os.path.basename(p) + " (runner %s not carried)" % m.group(1))
        elif sha256(carried) != m.group(2):
            bad.append(os.path.basename(p) + " (runner digest differs)")
        else:
            good.append(os.path.basename(p))
    ok = len(logs) > 0 and not bad and len(good) >= 5
    return ok, "%d certifying log(s) for %s; digest-matched %d; refused: %s" % (
        len(logs), sha[:8], len(good), "; ".join(bad[:6]) or "none")


def gate_brl1(evidence, sha):
    for p in logs_for(evidence, sha):
        t = text_of(p)
        m = re.search(r"^TALLY total=(\d+) summed=(\d+) .*verdict=PASS", t, re.M)
        if not m:
            continue
        mine = tally_text(t)
        ok = mine is not None and mine[0] == mine[1] == int(m.group(1)) == int(m.group(2))
        return ok, "%s: recorded total=%s summed=%s, re-tallied here %s" % (
            os.path.basename(p), m.group(1), m.group(2), mine)
    return False, "no log for %s records a per-node tally" % sha[:8]


def gate_brl2(evidence, sha):
    for p in logs_for(evidence, sha):
        t = text_of(p)
        m = re.search(r"^PLANTED .* hits=(\d+).*$", t, re.M)
        e = re.search(r"^planted scan exit (\d+)", t, re.M)
        if m and e:
            ok = int(m.group(1)) >= 1 and int(e.group(1)) != 0 and re.search(r"^EXIT 0\s*$", t, re.M) is not None
            return ok, "%s: planted hits=%s, planted scan exit %s" % (os.path.basename(p), m.group(1), e.group(1))
    return False, "no log for %s carries the planted negative control" % sha[:8]


def gate_m10(evidence, sha):
    """Fix pass 2 (M10): the real-config upgrade witness for this commit,
    complete, with its three negative controls each DETECTED."""
    for p in logs_for(evidence, sha):
        t = text_of(p)
        if not re.search(r"^CFGWITNESS-REAL verdict=PASS baseline=real-config", t, re.M):
            continue
        neg = re.search(r"^CFGWITNESS-REAL negative-control retype bool->string detected=True \| retype int->bool detected=True"
                        r" \| description edit detected=True", t, re.M)
        cnt = re.search(r"^CFGWITNESS-REAL pre-existing keys=(\d+) value kept=(\d+) type kept=(\d+)", t, re.M)
        done = re.search(r"^EXIT 0\s*$", t, re.M)
        ok = bool(neg and cnt and done and int(cnt.group(1)) > 0 and cnt.group(1) == cnt.group(2) == cnt.group(3))
        return ok, "%s: %s | negative controls detected=%s | EXIT 0=%s" % (
            os.path.basename(p), cnt.group(0) if cnt else "no key counts", bool(neg), bool(done))
    return False, "no log for %s carries the real-config upgrade witness (old and new bind lists over the same backed-up real file)" % sha[:8]


def gate_m8_replay(evidence, sha):
    for p in logs_for(evidence, sha):
        t = text_of(p)
        line = [l for l in t.splitlines() if l.startswith("[avatardefaults] PASS | case=M8 ")]
        if line and "[AVATAR] E3-entered" in line[0] and "[AVATAR] E11-left" in line[0]:
            return True, os.path.basename(p) + ": the five-case capture replay is carried"
    return False, "no harness log for %s carries the classification replay" % sha[:8]


# ---------------------------------------------------------------------------
# the controls
# ---------------------------------------------------------------------------

def controls(args):
    root = os.path.abspath(args.root)
    sha = git_head(root)
    out = sys.stdout
    out.write("controls root=%s commit=%s\n" % (root, sha))
    os.makedirs(args.work, exist_ok=True)
    res = {}

    # source gates
    srch3 = src_h3(root)
    res["BR-M1"] = src_brm1(root)
    srcm8 = src_m8(root)

    # fix pass 2, behaviour: the fix tip's production probe over THIS tree's
    # production files, and the fix tip's S33 over this tree's sources
    tipprobe = prodprobe_run(LANE, root, args.work, "tip-over-tree", out) or {}

    def tp(k):
        return tipprobe.get(k, (False, "the tip's production probe did not report " + k))

    s33rc = claims_run(root, args.work, "tip-s33", None, args.decompiled, out, tests_from=LANE,
                       select="s33_no_pass_rereads")
    s33why = "; ".join(l.split(" - ", 1)[-1][:300] for l in claims_run.last_failed) or "no reread after a publish"

    # the probe
    probe = build_probe(root, args.work, out)

    def p(k):
        return probe.get(k, (False, "probe did not report " + k))

    brh1_src = src_brh1(root)
    res["BR-H1"] = (p("BRH1")[0] and p("H8")[0] and brh1_src[0],
                    "probe: " + p("BRH1")[1] + " | " + p("H8")[1] + " | source: " + brh1_src[1])
    res["BR-M3"] = p("BRM3")

    # the tree's own harness against mutations
    base = harness_run(root, args.work, "baseline", None, out)
    twin6 = harness_run(root, args.work, "h6-twin", H6_TWIN, out)
    h6 = []
    for name, edit in H6_ROWS:
        n = harness_run(root, args.work, "h6-" + name.replace(" ", "-"), edit, out)
        h6.append((name, n))
    ok6 = base == 0 and twin6 == 0 and all(n is not None and n > 0 for _, n in h6)
    res["H6"] = (ok6, "baseline fails=%s twin fails=%s | " % (base, twin6)
                 + ", ".join("drop %s -> the tree's harness fails %s" % (nm, n) for nm, n in h6))
    n8 = harness_run(root, args.work, "h8-provenance", H8_ROW, out)
    t8 = harness_run(root, args.work, "h8-twin", H8_TWIN, out)
    ok8 = base == 0 and t8 == 0 and n8 is not None and n8 > 0 and p("H8")[0]
    res["H8"] = (ok8, "provenance-decides mutation -> the tree's harness fails %s, twin fails %s | probe: %s"
                 % (n8, t8, p("H8")[1]))
    hrow = {}
    for name, (edit, twin) in HARNESS2_ROWS.items():
        hrow[name] = (harness_run(root, args.work, name, edit, out), harness_run(root, args.work, name + "-twin", twin, out))

    def harness_ok(name):
        m, t = hrow[name]
        return base == 0 and m is not None and m > 0 and t == 0

    def harness_detail(name):
        return "%s: the tree's harness fails %s on the mutation, %s on the twin" % (name, hrow[name][0], hrow[name][1])

    # the tree's own source claims against mutations
    cbase = claims_run(root, args.work, "baseline", None, args.decompiled, out)
    crow = {}
    for name, row in CLAIM_ROWS.items():
        # a row names the tests that bind its claim (pytest -k); the mutation
        # and its twin run the SAME selection, and the baseline runs them all
        sel = CLAIM_SELECT.get(name)
        m = claims_run(root, args.work, name, row.get("edit"), args.decompiled, out,
                       decompile_edit=row.get("decompile_edit"), select=sel)
        if m not in (None, 0) and not claims_run.last_genuine:
            # every failure is the tests' own scaffolding: the tree's claims
            # never read the mutated expression (classify_failures)
            out.write("    no failure is the claim itself: not a catch\n")
            m = None
        t = claims_run(root, args.work, name + "-twin", row.get("twin"), args.decompiled, out,
                       decompile_edit=row.get("twin_decompile_edit"), select=sel)
        crow[name] = (m, t)

    def claim_ok(name):
        m, t = crow[name]
        return cbase == 0 and m not in (None, 0) and t == 0

    def claim_detail(names):
        return ", ".join("%s: mutation exit %s, twin exit %s" % (n, crow[n][0], crow[n][1]) for n in names)

    def rows_ok(names):
        return all(claim_ok(n) for n in names)

    def probe_ok(ids):
        return all(tp(i)[0] for i in ids)

    def probe_detail(ids):
        return " | ".join("tip probe %s %s: %s" % (i, "PASS" if tp(i)[0] else "FAIL", tp(i)[1]) for i in ids)

    m11 = ["M11-persistence", "M11-assignment", "M11-refusal"]
    l1 = ["L1-ring", "L1-hybrid", "L1-recovery", "M11-assignment", "L1-sprite-sink", "L1-announce-sink"]
    closures = [n for k in ("H6", "M8", "BR-M4", "L1") for n in M11_CLOSURES[k]]
    res["M11"] = (rows_ok(m11) and rows_ok(closures),
                  "claims baseline exit %s | round 1 rows: " % cbase + claim_detail(m11)
                  + " | the four closures (H6, M8, BR-M4, L1): " + claim_detail(closures))
    res["L1"] = (rows_ok(l1) and probe_ok(["L1sprite", "L1announce"]),
                 "claims baseline exit %s | " % cbase + claim_detail(l1) + " | " + probe_detail(["L1sprite", "L1announce"]))

    # fix pass 2: the PARTLY items, behaviour on this tree AND binding by the tree's own tests
    res["H3"] = (srch3[0] and s33rc == 0 and rows_ok(["H3-reread"]) and harness_ok("H3-rule-reread"),
                 "source: " + srch3[1] + " | the tip's S33 over this tree exit %s: %s | " % (s33rc, s33why)
                 + claim_detail(["H3-reread"]) + " | " + harness_detail("H3-rule-reread"))
    ok6b = res["H6"][0] and rows_ok(M11_CLOSURES["H6"]) and probe_ok(["H6a", "H6b", "H6c"])
    res["H6"] = (ok6b, res["H6"][1] + " | production: " + claim_detail(M11_CLOSURES["H6"]) + " | " + probe_detail(["H6a", "H6b", "H6c"]))
    res["H9"] = (p("H9")[0] and probe_ok(["H9c", "H9s"]) and rows_ok(["H9-early-return"]) and harness_ok("H9-rule-deferral"),
                 "rules probe: " + p("H9")[1] + " | " + probe_detail(["H9c", "H9s"]) + " | "
                 + claim_detail(["H9-early-return"]) + " | " + harness_detail("H9-rule-deferral"))
    res["M3"] = (p("M3")[0] and probe_ok(["M3t"]) and rows_ok(["M3-deferred-edge"]),
                 "rules probe: " + p("M3")[1] + " | " + probe_detail(["M3t"]) + " | " + claim_detail(["M3-deferred-edge"]))
    res["BR-M4"] = (p("BRM4")[0] and probe_ok(["BRM4"]) and rows_ok(M11_CLOSURES["BR-M4"]),
                    "rules probe: " + p("BRM4")[1] + " | " + probe_detail(["BRM4"]) + " | " + claim_detail(M11_CLOSURES["BR-M4"]))

    # evidence gates
    ev = args.evidence
    rep = gate_m8_replay(ev, sha)
    res["M8"] = (srcm8[0] and rep[0] and rows_ok(M11_CLOSURES["M8"]) and probe_ok(["M8apply", "M8room"]),
                 "source: " + srcm8[1] + " | evidence: " + rep[1] + " | production: " + claim_detail(M11_CLOSURES["M8"])
                 + " | " + probe_detail(["M8apply", "M8room"]))
    res["M10"] = gate_m10(ev, sha)
    res["BR-M2"] = log_gate(ev, sha, r"^AFFECTED-COMPARE verdict=PASS", "final-tip affected-set comparison")
    res["BR-M5"] = gate_brm5(ev, sha)
    res["BR-L1"] = gate_brl1(ev, sha)
    res["BR-L2"] = gate_brl2(ev, sha)

    green = 0
    for k in ITEMS:
        ok, why = res[k]
        green += 1 if ok else 0
        out.write("CONTROL %-6s %s | %s\n" % (k, "GREEN" if ok else "RED", why))
    out.write("CONTROLS commit=%s green=%d red=%d of %d\n" % (sha, green, len(ITEMS) - green, len(ITEMS)))
    f2red = [k for k in FIX2 if not res[k][0]]
    out.write("CONTROLS-FIX2 commit=%s red=%d green=%d of %d (red: %s)\n"
              % (sha, len(f2red), len(FIX2) - len(f2red), len(FIX2), " ".join(f2red) or "none"))
    return 0 if green == len(ITEMS) else 1


# ---------------------------------------------------------------------------
# M10: the bind list and the witness
# ---------------------------------------------------------------------------

def split_args(s):
    out, depth, cur, i, n = [], 0, [], 0, len(s)
    while i < n:
        ch = s[i]
        if ch == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            cur.append(s[i:j + 1])
            i = j + 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    out.append("".join(cur).strip())
    return out


def lit(s):
    """A C# string literal or a +-concatenation of them, else None."""
    if not s.strip().startswith('"') or not s.strip().endswith('"'):
        return None
    txt = s.strip()[1:-1]
    txt = re.sub(r'"\s*\+\s*"', "", txt)
    try:
        return json.loads('"' + txt + '"')
    except ValueError:
        return txt


def const_decl(folder, name):
    """(type, literal) of `const <type> <name> = <literal>;` declared once in
    the folder's .cs files, or (None, None)."""
    found = []
    for f in sorted(os.listdir(folder)):
        if f.endswith(".cs"):
            for m in re.finditer(r"\bconst\s+(int|bool|float|string)\s+" + re.escape(name) + r"\s*=\s*([^;]+);",
                                 read(os.path.join(folder, f))):
                found.append((m.group(1), m.group(2).strip()))
    return found[0] if len(set(found)) == 1 else (None, None)


def binds(plugin_cs):
    t = read(plugin_cs)
    code = strip_comments_only(t)
    rows = []
    for m in re.finditer(r"\bConfig\.Bind\(", code):
        i = m.end()
        depth = 1
        j = i
        while depth and j < len(code):
            if code[j] == '"':
                j += 1
                while code[j] != '"':
                    j += 2 if code[j] == "\\" else 1
            elif code[j] == "(":
                depth += 1
            elif code[j] == ")":
                depth -= 1
            j += 1
        a = split_args(code[i:j - 1])
        if len(a) != 4:
            continue
        sec, key, dv, desc = lit(a[0]), lit(a[1]), a[2].strip(), lit(a[3])
        # a named constant default (MusicLevels.DEFAULT_PERCENT): resolve it
        # from its declaration in the same plugin folder, so the bind's TYPE
        # is the declared one (fix pass 2, M10: an int const read as a string
        # retyped MusicVolume in the real-config witness)
        if re.fullmatch(r"[A-Za-z_][\w.]*", dv) and dv not in ("true", "false"):
            ctype, cval = const_decl(os.path.dirname(plugin_cs), dv.split(".")[-1])
            if ctype == "string":
                dv = cval
            elif ctype in ("int", "bool"):
                dv = cval
            elif ctype == "float":
                dv = cval if cval.endswith("f") else cval + "f"
        if dv in ("true", "false"):
            kind, val = "bool", dv
        elif re.fullmatch(r"-?\d+", dv):
            kind, val = "int", dv
        elif re.fullmatch(r"-?\d+(\.\d+)?f", dv):
            kind, val = "float", dv[:-1]
        else:
            s = lit(dv)
            kind, val = "string", (s if s is not None else dv)
        rows.append(dict(section=sec, key=key, kind=kind, value=val,
                         description=desc if desc is not None else "(non-literal description)"))
    return rows


AVATAR_KEYS = ["AvatarAutoSwitch", "AvatarModdedPreset", "AvatarVanillaPreset", "AvatarHomeSlot"]


def cfgwitness(args):
    root = os.path.abspath(args.root)
    rows = binds(os.path.join(root, "plugin", "Plugin.cs"))
    keys = [r["key"] for r in rows]
    missing = [k for k in AVATAR_KEYS if k not in keys]
    print("binds extracted=%d, the four item 19 keys present=%s" % (len(rows), not missing))
    if missing:
        return 1
    d = os.path.join(args.work, "cfgwitness")
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    for f in ("CfgWitness.cs", "item19-cfgwitness.csproj"):
        shutil.copyfile(os.path.join(HERE, "cfgwitness", f), os.path.join(d, f))
    with open(os.path.join(d, "binds.json"), "w", encoding="utf-8") as f:
        json.dump({"binds": rows, "avatar": AVATAR_KEYS}, f)
    real = getattr(args, "real_cfg", None)
    if real:
        # fix pass 2 (M10): the OLD same-lineage build's bind list (the tree
        # this lane branched from) and the NEW one (this tree), each applied
        # by BepInEx's own ConfigFile to its own copy of ONE backed-up real
        # configuration file; the original is never opened by the witness
        old_root = os.path.abspath(args.old_root)
        old_rows = binds(os.path.join(old_root, "plugin", "Plugin.cs"))
        print("old tree %s commit %s: binds extracted=%d, item 19 keys present=%s" % (
            old_root, (git_head(old_root) or "?")[:8], len(old_rows), any(r["key"] in AVATAR_KEYS for r in old_rows)))
        print("new tree %s commit %s: binds extracted=%d" % (root, (git_head(root) or "?")[:8], len(rows)))
        old_keys = [(r["section"], r["key"]) for r in old_rows]
        new_keys = [(r["section"], r["key"]) for r in rows if r["key"] not in AVATAR_KEYS]
        print("non-avatar bind lists identical (section, key, kind, default, description)=%s" % (
            [r for r in old_rows] == [r for r in rows if r["key"] not in AVATAR_KEYS]))
        print("non-avatar bind keys identical=%s" % (old_keys == new_keys))
        with open(os.path.join(d, "old-binds.json"), "w", encoding="utf-8") as f:
            json.dump({"binds": old_rows, "avatar": AVATAR_KEYS}, f)
        shutil.copyfile(real, os.path.join(d, "real-backup.cfg"))
        print("real config backup %s sha256 %s (copied for the witness: %s)" % (
            os.path.basename(real), sha256(real), sha256(os.path.join(d, "real-backup.cfg"))))
    cmd = ["dotnet", "build", os.path.join(d, "item19-cfgwitness.csproj"), "-c", "Release", "-nologo", "-v", "q",
           "-p:BepInExCore=" + args.bepinex_core]
    if args.managed:
        cmd.append("-p:ManagedDir=" + args.managed)
    rc, o = run(cmd)
    print("witness build exit %d" % rc)
    if rc != 0:
        print(o[-3000:])
        return 1
    dll = os.path.join(d, "bin", "Release", "net10.0", "item19-cfgwitness.dll")
    rc, o = run(["dotnet", dll, os.path.join(d, "binds.json"), os.path.join(d, "out")])
    print(o.rstrip())
    print("witness exit %d" % rc)
    if not real:
        return rc
    rc2, o = run(["dotnet", dll, "--real", os.path.join(d, "old-binds.json"), os.path.join(d, "binds.json"),
                  os.path.join(d, "real-backup.cfg"), os.path.join(d, "real")])
    print(o.rstrip())
    print("real-config witness exit %d" % rc2)
    return rc | rc2


# ---------------------------------------------------------------------------
# BR-L1: the per-node tally
# ---------------------------------------------------------------------------

NODE = re.compile(r"^(?P<node>\S.*?::.*?) (?P<v>PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)(?: |$)")
SUMMARY = re.compile(r"^=+ (?P<body>.*?) in [\d.]+s")


def tally_text(t):
    nodes = {}
    for line in t.splitlines():
        m = NODE.match(line)
        if m:
            nodes[m.group("node")] = m.group("v")
    total = None
    for line in t.splitlines():
        s = SUMMARY.match(line)
        if s:
            total = sum(int(n) for n in re.findall(r"(\d+) (?:passed|failed|skipped|errors?|xfailed|xpassed)", s.group("body")))
    if total is None:
        return None
    return len(nodes), total, nodes


def tally(path):
    t = text_of(path)
    r = tally_text(t)
    if r is None:
        print("TALLY no pytest summary line in %s" % path)
        return 1
    n, total, nodes = r
    per = {}
    for node in nodes:
        f = node.split("::", 1)[0].replace("\\", "/").rsplit("/", 1)[-1]
        per[f] = per.get(f, 0) + 1
    for f in sorted(per):
        print("TALLY file %s nodes=%d" % (f, per[f]))
    spaced = sum(1 for node in nodes if " " in node)
    s = sum(per.values())
    ok = s == total == n
    print("TALLY total=%d summed=%d files=%d nodes-with-spaces=%d verdict=%s" % (total, s, len(per), spaced, "PASS" if ok else "FAIL"))
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# BR-L2: the planted copy, and BR-M2: the comparison
# ---------------------------------------------------------------------------

def plant(dll, out):
    with open(dll, "rb") as f:
        b = bytearray(f.read())
    marker = "c:\\users\\planted".encode("utf-16-le")
    at = len(b) // 2 | 1                          # an odd offset
    b[at:at] = marker
    with open(out, "wb") as f:
        f.write(bytes(b))
    print("planted a UTF-16LE local-path marker at odd offset %d in %s" % (at, out))
    return 0


def failed_nodes(t):
    out = set()
    for line in t.splitlines():
        m = re.match(r"^(FAILED|ERROR) (\S+)", line)
        if m:
            out.add(m.group(2).replace("\\", "/").split("backend/tests/", 1)[-1])
    return out


def compare(tip, base):
    tt, bt = text_of(tip), text_of(base)
    tf, bf = failed_nodes(tt), failed_nodes(bt)
    # -q prints the closing summary without the ===== banner; -v prints it with one
    summ = r"^(?:=+ )?(\d+ (?:failed|passed|skipped|errors?|deselected|xfailed|xpassed|warnings?)\b.*?) in [\d.]+s"
    ts, bs = [re.findall(summ, x, re.M) for x in (tt, bt)]
    new = sorted(tf - bf)
    item19 = sorted(n for n in tf if n.startswith(("test_client_avatar_defaults", "test_client_rules_harness")))
    print("AFFECTED-COMPARE tip summary: %s" % (ts[-1] if ts else "none"))
    print("AFFECTED-COMPARE base summary: %s" % (bs[-1] if bs else "none"))
    print("AFFECTED-COMPARE tip failing/erroring nodes=%d base=%d fixed-at-tip=%d new-at-tip=%d item19-file failures=%d"
          % (len(tf), len(bf), len(bf - tf), len(new), len(item19)))
    for n in new[:40]:
        print("AFFECTED-COMPARE new at tip: " + n)
    ok = bool(ts) and bool(bs) and not item19 and not new
    print("AFFECTED-COMPARE verdict=%s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("controls")
    c.add_argument("--root", required=True)
    c.add_argument("--evidence", required=True)
    c.add_argument("--decompiled", required=True)
    c.add_argument("--work", required=True)
    b = sub.add_parser("binds")
    b.add_argument("plugin_cs")
    b.add_argument("out")
    w = sub.add_parser("cfgwitness")
    w.add_argument("--root", required=True)
    w.add_argument("--bepinex-core", required=True)
    w.add_argument("--managed", default=None)
    w.add_argument("--work", required=True)
    w.add_argument("--old-root", default=None)
    w.add_argument("--real-cfg", default=None)
    t = sub.add_parser("tally")
    t.add_argument("log")
    p = sub.add_parser("plant")
    p.add_argument("dll")
    p.add_argument("out")
    k = sub.add_parser("compare")
    k.add_argument("tip")
    k.add_argument("base")
    a = ap.parse_args()
    if a.cmd == "controls":
        return controls(a)
    if a.cmd == "binds":
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(binds(a.plugin_cs), f, indent=1)
        return 0
    if a.cmd == "cfgwitness":
        return cfgwitness(a)
    if a.cmd == "tally":
        return tally(a.log)
    if a.cmd == "plant":
        return plant(a.dll, a.out)
    return compare(a.tip, a.base)


if __name__ == "__main__":
    sys.exit(main())
