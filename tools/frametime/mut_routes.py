#!/usr/bin/env python3
"""mut_routes.py: negative controls for ft_routes_check.py. Each mutant copies plugin/*.cs into <outdir>/mut-<k>/plugin,
changes one thing, and the check must FAIL on it (and PASS on the unchanged copy, the positive control).
Usage: python -I -B mut_routes.py <worktree> <outdir>; exit 0 when every control holds."""
import os
import shutil
import subprocess
import sys

W, OUT = sys.argv[1], sys.argv[2]
CHECK = os.path.join(W, "tools", "frametime", "ft_routes_check.py")
MUTS = [
    ("unchanged copy (positive control)", None, None, None, "PASS"),
    ("the emoji refusal removed", "EmojiSprites.cs",
     'if (FtUpload.Closed) { FtUpload.RefuseQuiet("route", "GET_emoji-sheet");', "if (false) {", "FAIL"),
    ("the chat entry refusal removed", "ChatClient.cs",
     'if (FtUpload.Closed) { FtUpload.Refuse("chat", "connect"); return; }', "", "FAIL"),
    ("a new System.Net site", "BroadcastMode.cs", "namespace CompetitiveRounds\n{",
     "namespace CompetitiveRounds\n{\n    internal static class FtMutNet { internal static void Go() { new System.Net.WebClient(); } }", "FAIL"),
    ("the prefix stops calling Allow", "FtRoute.cs", "try { allowed = FtRoute.Allow(__instance.method, __instance.url, out route); }",
     "try { allowed = true; route = \"\"; }", "FAIL"),
    ("the refused request redirected and sent", "FtRoute.cs", "FtUpload.RefuseQuiet(\"route\", route);\n            return false;",
     "FtUpload.RefuseQuiet(\"route\", route);\n            __instance.url = \"http://127.0.0.1:1/x\"; return true;", "FAIL"),
    ("the dispatch postfix removed", "FtRoute.cs", "FtUpload.Count(\"dispatched\", route);", "", "FAIL"),
    ("the dispatch counted from Allow's answer", "FtRoute.cs",
     "try { route = FtRoute.Classify(__instance.method, __instance.url); }",
     "try { FtRoute.Allow(__instance.method, __instance.url, out route); }", "FAIL"),
    ("a guard outside the variant block", "MusicAssets.cs", "#if SCR_FRAMETIME\n                if (FtUpload.Closed) { FtUpload.RefuseQuiet(\"route\", \"GET_music-asset\");",
     "#if DEBUG\n                if (FtUpload.Closed) { FtUpload.RefuseQuiet(\"route\", \"GET_music-asset\");", "FAIL"),
]
bad = 0
for k, (name, f, a, b, want) in enumerate(MUTS):
    d = os.path.join(OUT, "mut-%d" % k)
    os.makedirs(os.path.join(d, "plugin"), exist_ok=False)
    for n in os.listdir(os.path.join(W, "plugin")):
        if n.endswith(".cs"):
            shutil.copy(os.path.join(W, "plugin", n), os.path.join(d, "plugin", n))
    if f is not None:
        p = os.path.join(d, "plugin", f)
        t = open(p, encoding="utf-8-sig", newline="").read()
        nl = "\r\n" if "\r\n" in t else "\n"
        a2, b2 = a.replace("\n", nl), b.replace("\n", nl)
        if t.count(a2) != 1:
            sys.exit("REFUSED: mutant %d anchor matched %d times" % (k, t.count(a2)))
        open(p, "w", encoding="utf-8", newline="").write(t.replace(a2, b2))
    r = subprocess.run([sys.executable, "-I", "-B", CHECK, d], capture_output=True, text=True, timeout=300)
    got = "PASS" if r.returncode == 0 else "FAIL"
    ok = got == want
    print("control %d (%s): check %s, wanted %s -> %s" % (k, name, got, want, "ok" if ok else "CONTROL FAILED"))
    bad += 0 if ok else 1
print("ROUTE CONTROLS %s" % ("PASS" if bad == 0 else "FAIL"))
sys.exit(0 if bad == 0 else 1)
