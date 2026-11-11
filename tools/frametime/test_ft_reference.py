"""test_ft_reference.py: the FrameTimeRef build (B11 D3, the no-collector reference) at source level.

- The patch classes the reference never installs (Plugin.cs FtRefSkip) equal the [HarmonyPatch] classes the
  collectors' files declare, plus PoisonSync.cs's two point-evidence patch classes.
- Every named installation site sits under #if !SCR_FT_NOCOLLECTORS; a scanner mutant (one guard removed) must fail.
- The two boot lines' literals each occur exactly once in plugin/*.cs, and each under its own variant's branch.
- ft_build.sh's marker scan finds a #US entry exactly, not as a prefix of the reference's literal, and the marker
  at an odd offset.
"""
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(os.path.dirname(os.path.dirname(HERE)), "plugin")
COLLECTOR_FILES = ["CombatEvidence.cs", "HitEvidence.cs", "SeatEvidence.cs", "IdentityClockEvidence.cs",
                   "CardDrawEvidence.cs"]
FT_LIT = "[FRAME-TIME] build variant=FrameTime"
REF_LIT = "[FRAME-TIME] build variant=FrameTimeRef SCR_FT_REF=NOCOLLECTORS"
GUARD = "!SCR_FT_NOCOLLECTORS"


def src(name):
    return open(os.path.join(PLUGIN, name), encoding="utf-8-sig").read()


def patch_classes(text):
    """the classes declared right after a [HarmonyPatch...] attribute line"""
    out = set()
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if re.match(r"\s*\[HarmonyPatch", ln):
            for nxt in lines[i + 1:i + 6]:
                m = re.search(r"\bclass ([A-Za-z0-9_]+)", nxt)
                if m:
                    out.add(m.group(1))
                    break
    return out


def skip_list():
    t = src("Plugin.cs")
    m = re.search(r"FtRefSkip = new HashSet<Type>\s*\{(.*?)\};", t, re.S)
    assert m, "Plugin.cs declares no FtRefSkip"
    return re.findall(r"typeof\(([A-Za-z0-9_]+)\)", m.group(1))


def test_skip_list_equals_the_collectors_patch_classes():
    want = set()
    for f in COLLECTOR_FILES:
        want |= patch_classes(src(f))
    want |= set(c for c in re.findall(r"\bclass ([A-Za-z0-9_]+EvidencePatch)\b", src("PoisonSync.cs")))
    have = skip_list()
    assert len(have) == len(set(have)), "a class listed twice"
    assert set(have) == want, ("missing", sorted(want - set(have)), "extra", sorted(set(have) - want))
    assert len(want) == 45


def guarded_lines(text):
    """for each line: True when an enclosing active #if branch is !SCR_FT_NOCOLLECTORS"""
    stack, out = [], []
    for ln in text.split("\n"):
        s = ln.strip()
        if s.startswith("#if "):
            stack.append([s[4:].strip(), True])
        elif s.startswith("#else") or s.startswith("#elif"):
            if stack:
                stack[-1][1] = False
        elif s.startswith("#endif"):
            if stack:
                stack.pop()
        out.append(any(c == GUARD and live for c, live in stack))
    return out


# (file, call) of every installation site the reference must skip (D3, rulings of 11 Nov)
SITES = [
    ("Plugin.cs", r"PeerBuild\.StageBuildProp\(\"tick\"\)"), ("Plugin.cs", r"SeatEvidence\.CompatTick\("),
    ("Plugin.cs", r"PointEvidence\.Drain\("), ("Plugin.cs", r"SeatEvidence\.Tick\("),
    ("Plugin.cs", r"CardDrawEvidence\.Tick\("), ("Plugin.cs", r"CombatEvidence\.Tick\("),
    ("Plugin.cs", r"IdentityClockEvidence\.Tick\("), ("Plugin.cs", r"CardDrawEvidence\.EnsureCensusDump\("),
    ("Plugin.cs", r"SeatEvidence\.StartHashing\("), ("Plugin.cs", r"\.FlushOnQuit\("),
    ("Plugin.cs", r"SeatEvidence\.NoteCompat\("), ("Plugin.cs", r"IdentityClockEvidence\.BootCheck\("),
    ("Plugin.cs", r"CardDrawEvidence\.FreezeRoomFacts\("), ("Plugin.cs", r"GameStateWatcher\.SeatEvidenceOnQuit\("),
    ("GameStateWatcher.cs", r"(SeatEvidence|CombatEvidence|IdentityClockEvidence)\.BeginGame\("),
    ("NetworkReplicaDiagnostics.cs", r"SeatEvidence\.NoteView\("),
    ("PoisonSync.cs", r"HitEvidence\.Drain\("),
]


def unguarded(text, pat):
    g = guarded_lines(text)
    hits = [i for i, ln in enumerate(text.split("\n")) if re.search(pat, ln) and not ln.strip().startswith("//")]
    return hits, [i + 1 for i in hits if not g[i]]


def test_every_installation_site_is_guarded():
    for f, pat in SITES:
        hits, bad = unguarded(src(f), pat)
        assert hits, "%s: no line matches %s" % (f, pat)
        assert not bad, "%s: %s unguarded at lines %s" % (f, pat, bad)


def test_the_guard_scanner_catches_a_removed_guard():
    # negative control: the tick block with its guard removed reads unguarded; with it, guarded
    t = src("Plugin.cs")
    block = "#if !SCR_FT_NOCOLLECTORS\n            try { PointEvidence.Drain(); } catch { }"
    t = t.replace("\r\n", "\n")
    assert t.count(block) == 1
    assert not unguarded(t, r"PointEvidence\.Drain\(")[1]
    assert unguarded(t.replace(block, "#if SCR_OTHER\n#else\n            try { PointEvidence.Drain(); } catch { }"),
                     r"PointEvidence\.Drain\(")[1]
    assert unguarded(t.replace(block, "            try { PointEvidence.Drain(); } catch { }\n#if !SCR_FT_NOCOLLECTORS"),
                     r"PointEvidence\.Drain\(")[1]


def test_boot_literals_once_each_under_their_branch():
    every = "".join(open(f, encoding="utf-8-sig").read() for f in glob.glob(os.path.join(PLUGIN, "*.cs")))
    assert every.count('"' + REF_LIT + '"') == 1
    assert every.count('"' + FT_LIT + '"') == 1
    t = src("Plugin.cs").replace("\r\n", "\n")
    m = re.search(r"#if SCR_FT_NOCOLLECTORS\n\s*Log\.LogInfo\(\"(.*?)\"\);\n#else\n\s*Log\.LogInfo\(\"(.*?)\"\);\n#endif", t)
    assert m and m.group(1) == REF_LIT and m.group(2) == FT_LIT, m and m.groups()


def scan_block():
    t = open(os.path.join(HERE, "ft_build.sh"), encoding="utf-8").read()
    m = re.search(r"python -I -B - \"\$1\" <<'PY'\n(.*?)\nPY\n", t, re.S)
    assert m, "ft_build.sh holds no marker scan"
    return m.group(1)


def us_entry(s, flag=b"\x01"):
    n = 2 * len(s) + 1
    head = bytes([n]) if n < 0x80 else bytes([0x80 | (n >> 8), n & 0xFF])
    return head + s.encode("utf-16-le") + flag


def scan(tmp_path, data):
    p = tmp_path / "x.dll"
    p.write_bytes(data)
    r = subprocess.run([sys.executable, "-I", "-B", "-", str(p)], input=scan_block(), stdout=subprocess.PIPE,
                       universal_newlines=True)
    return r.stdout.strip()


def test_marker_scan(tmp_path):
    pad = b"MZ\x90" + bytes(101)
    assert scan(tmp_path, pad + us_entry(FT_LIT)) == "ft=1 ref=0 marker=0"
    # the reference's literal holds FrameTime's as a prefix: as a #US entry it is the reference's only
    assert scan(tmp_path, pad + us_entry(REF_LIT)) == "ft=0 ref=1 marker=1"
    # odd offset, flag byte 0
    assert scan(tmp_path, pad + b"\x07" + us_entry(REF_LIT, b"\x00")) == "ft=0 ref=1 marker=1"
    assert scan(tmp_path, pad + us_entry(FT_LIT) + us_entry(REF_LIT)) == "ft=1 ref=1 marker=1"
    # the text without its #US framing (another heap, or a different length byte) is no entry
    assert scan(tmp_path, pad + FT_LIT.encode("utf-16-le") + b"\x01") == "ft=0 ref=0 marker=0"
    assert scan(tmp_path, pad) == "ft=0 ref=0 marker=0"
