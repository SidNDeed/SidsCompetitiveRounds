"""The static patch census (L1): the classes carrying a CLASS-level
[HarmonyPatch] attribute in the plugin sources, outside any #if block whose
symbol no shipped configuration defines. An attribute may span lines (its
brackets are followed to their close), so a class whose [HarmonyPatch(...)]
continues onto a second line is counted like any other. The in-game witness
compares this count with the boot line "[HARMONY] Patches applied: N ok".

    python patch_census.py <plugin dir>            # the working files
    python patch_census.py --git <repo> <commit>   # a commit (git show)
    python patch_census.py --selftest              # the multi-line control
"""
import os
import re
import subprocess
import sys

UNDEFINED = {"SCR_CARD_EVIDENCE_TEST_DEALER", "SCR_CARD_EVIDENCE_TEST_GATE", "THUNDERSTORE"}
CLASS = re.compile(r"^\s*(?:(?:internal|public|private|static|sealed|partial|abstract)\s+)*class\s+(\w+)")


def _depth(s):
    """Bracket balance of one attribute line, string literals skipped."""
    d, q = 0, False
    for i, c in enumerate(s):
        if c == '"' and (i == 0 or s[i - 1] != "\\"):
            q = not q
        elif not q:
            d += (c == "[") - (c == "]")
    return d


def classes_in(src, name):
    out = set()
    skip, attrs, cur, depth = [], [], None, 0
    for ln in src.splitlines():
        s = ln.strip()
        if cur is not None:                      # inside an attribute that spans lines
            cur += " " + s
            depth += _depth(s)
            if depth <= 0:
                attrs.append(cur)
                cur = None
            continue
        m = re.match(r"#if\s+(!?)(\w+)", s)
        if m:
            skip.append(m.group(2) in UNDEFINED and not m.group(1))
            continue
        if s.startswith("#else"):
            if skip:
                skip[-1] = not skip[-1]
            continue
        if s.startswith("#endif"):
            if skip:
                skip.pop()
            continue
        if any(skip):
            continue
        if s.startswith("["):
            depth = _depth(s)
            if depth > 0:
                cur = s
            else:
                attrs.append(s)
            continue
        cm = CLASS.match(ln)
        if cm and any(a.startswith("[HarmonyPatch") for a in attrs):
            out.add("%s:%s" % (name, cm.group(1)))
        if s and not s.startswith("//"):
            attrs = []
    return out


def census_dir(plugin):
    out = set()
    for f in sorted(os.listdir(plugin)):
        if f.endswith(".cs"):
            out |= classes_in(open(os.path.join(plugin, f), encoding="utf-8").read(), "plugin/" + f)
    return out


def census_git(repo, commit):
    files = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", commit, "plugin/"],
                           capture_output=True, text=True).stdout.split()
    out = set()
    for f in files:
        if f.endswith(".cs"):
            src = subprocess.run(["git", "-C", repo, "show", "%s:%s" % (commit, f)],
                                 capture_output=True, text=True, encoding="utf-8").stdout
            out |= classes_in(src, f)
    return out


SELFTEST = '''
    [HarmonyPatch(typeof(A), "One")]
    internal static class OneLine { }

    [HarmonyPatch(typeof(B), "Two",
        new Type[] { typeof(int), typeof(string) })]
    internal static class TwoLines { }

    [HarmonyPatch]
    [HarmonyPriority(Priority.Last)]
    internal static class Stacked { }

#if THUNDERSTORE
    [HarmonyPatch(typeof(C), "Gated")]
    internal static class Gated { }
#endif

    [SomethingElse("x]")]
    internal static class NotAPatch { }
'''


def selftest():
    got = sorted(c.split(":")[1] for c in classes_in(SELFTEST, "t"))
    want = ["OneLine", "Stacked", "TwoLines"]
    print("patch census control (a two-line [HarmonyPatch] counted, a gated class and a non-patch not): %s %s"
          % ("PASS" if got == want else "FAIL", got))
    return got == want


if __name__ == "__main__":
    if sys.argv[1:2] == ["--selftest"]:
        sys.exit(0 if selftest() else 1)
    if sys.argv[1:2] == ["--git"]:
        s = census_git(sys.argv[2], sys.argv[3])
        print("%s: %d classes with a class-level [HarmonyPatch]" % (sys.argv[3], len(s)))
    else:
        s = census_dir(sys.argv[1])
        print("%s: %d classes with a class-level [HarmonyPatch]" % (sys.argv[1], len(s)))
