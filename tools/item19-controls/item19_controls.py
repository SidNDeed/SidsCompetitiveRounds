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
           twin and on the unmutated baseline (#391, #342)
  log      the certifying evidence for the tree's commit in the lane's
           evidence folder (logs headed "commit <sha> tree clean")

Nothing is edited in the tree: every build and every mutation happens in
copies under --work. No path is hard-coded; the caller names every directory.

Subcommands:
  controls --root TREE --evidence DIR --decompiled DIR --work DIR
  binds PLUGIN_CS OUT_JSON            the Config.Bind list (M10's witness input)
  cfgwitness --root TREE --bepinex-core DIR [--managed DIR] --work DIR
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
    m = re.search(r"public static \w+ PublishLocal\(\)", seg)
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
    d = os.path.join(work, "harness-" + label)
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


def claims_run(root, work, label, edit, decompiled, out, decompile_edit=None):
    d = os.path.join(work, "claims-" + label)
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(os.path.join(d, "plugin"))
    os.makedirs(os.path.join(d, "backend", "tests"))
    os.makedirs(os.path.join(d, "tools"))
    for f in os.listdir(os.path.join(root, "plugin")):
        if f.endswith(".cs"):
            shutil.copyfile(os.path.join(root, "plugin", f), os.path.join(d, "plugin", f))
    for f in ("test_client_avatar_defaults.py", "_cs_structure.py"):
        shutil.copyfile(os.path.join(root, "backend", "tests", f), os.path.join(d, "backend", "tests", f))
    shutil.copyfile(os.path.join(root, "tools", "i18n_source.json"), os.path.join(d, "tools", "i18n_source.json"))
    dec = os.path.join(d, "decompiled")
    os.makedirs(dec)
    for f in DECOMPILED_FILES:
        src = os.path.join(decompiled, f)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(dec, f))
    if edit is not None:
        path = os.path.join(d, "plugin", edit[0])
        t = read(path)
        if t.count(edit[1]) != 1:
            out.write("--- claims %s: anchor occurs %d times ---\n" % (label, t.count(edit[1])))
            return None
        write(path, t.replace(edit[1], edit[2]))
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
    rc, o = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--noconftest",
                 os.path.join(d, "backend", "tests", "test_client_avatar_defaults.py")], env=env, cwd=d)
    tail = [l for l in o.splitlines() if re.search(r"\b(passed|failed|error)", l)]
    failed = [l for l in o.splitlines() if l.startswith("FAILED ")]
    out.write("--- claims %s exit %d: %s ---\n" % (label, rc, tail[-1] if tail else "(no summary)"))
    for l in failed[:6]:
        out.write("    " + l[:300] + "\n")
    return rc


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
    res["H3"] = src_h3(root)
    res["BR-M1"] = src_brm1(root)
    srcm8 = src_m8(root)

    # the probe
    probe = build_probe(root, args.work, out)

    def p(k):
        return probe.get(k, (False, "probe did not report " + k))

    brh1_src = src_brh1(root)
    res["BR-H1"] = (p("BRH1")[0] and p("H8")[0] and brh1_src[0],
                    "probe: " + p("BRH1")[1] + " | " + p("H8")[1] + " | source: " + brh1_src[1])
    res["H9"] = p("H9")
    res["M3"] = p("M3")
    res["BR-M3"] = p("BRM3")
    res["BR-M4"] = p("BRM4")

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

    # the tree's own source claims against mutations
    cbase = claims_run(root, args.work, "baseline", None, args.decompiled, out)
    crow = {}
    for name, row in CLAIM_ROWS.items():
        m = claims_run(root, args.work, name, row.get("edit"), args.decompiled, out,
                       decompile_edit=row.get("decompile_edit"))
        t = claims_run(root, args.work, name + "-twin", row.get("twin"), args.decompiled, out,
                       decompile_edit=row.get("twin_decompile_edit"))
        crow[name] = (m, t)

    def claim_ok(name):
        m, t = crow[name]
        return cbase == 0 and m not in (None, 0) and t == 0

    def claim_detail(names):
        return ", ".join("%s: mutation exit %s, twin exit %s" % (n, crow[n][0], crow[n][1]) for n in names)

    m11 = ["M11-persistence", "M11-assignment", "M11-refusal"]
    l1 = ["L1-ring", "L1-hybrid", "L1-recovery", "M11-assignment"]
    res["M11"] = (all(claim_ok(n) for n in m11), "claims baseline exit %s | " % cbase + claim_detail(m11))
    res["L1"] = (all(claim_ok(n) for n in l1), "claims baseline exit %s | " % cbase + claim_detail(l1))

    # evidence gates
    ev = args.evidence
    rep = gate_m8_replay(ev, sha)
    res["M8"] = (srcm8[0] and rep[0], "source: " + srcm8[1] + " | evidence: " + rep[1])
    res["M10"] = log_gate(ev, sha, r"^CFGWITNESS verdict=PASS baseline=same-lineage", "same-lineage config witness")
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
    cmd = ["dotnet", "build", os.path.join(d, "item19-cfgwitness.csproj"), "-c", "Release", "-nologo", "-v", "q",
           "-p:BepInExCore=" + args.bepinex_core]
    if args.managed:
        cmd.append("-p:ManagedDir=" + args.managed)
    rc, o = run(cmd)
    print("witness build exit %d" % rc)
    if rc != 0:
        print(o[-3000:])
        return 1
    rc, o = run(["dotnet", os.path.join(d, "bin", "Release", "net10.0", "item19-cfgwitness.dll"),
                 os.path.join(d, "binds.json"), os.path.join(d, "out")])
    print(o.rstrip())
    print("witness exit %d" % rc)
    return rc


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
