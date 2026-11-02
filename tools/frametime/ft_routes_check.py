#!/usr/bin/env python3
"""ft_routes_check.py: F02's static check (FORMAT-M-PLAN.md V2 part b item 5; build decision 11). Every network
transport site in plugin/*.cs must be covered in the FrameTime variant:

  - every UnityWebRequest send (`.SendWebRequest(`) by the one prefix on UnityWebRequest.SendWebRequest in
    plugin/FtRoute.cs, which calls FtRoute.Allow before anything is sent and is applied by Plugin.cs's
    attribute loop (every [HarmonyPatch] class in the assembly);
  - every System.Net transport (WebClient, WebRequest.Create, HttpClient, ClientWebSocket, TcpClient) by a refusal
    in an `#if SCR_FRAMETIME` block, either just before the site in the same method or at the entry of the one
    method that starts the site's loop (ChatClient.Connect for its socket);
  - the one exemption, RegionPingSweep's UDP region pings (decision 12), named here.

The site counts per file must equal the table below, so a new transport site fails the check until it is
classified. Usage: python -I -B ft_routes_check.py <worktree>; exit 0 PASS, 1 FAIL.
"""
import os
import re
import sys

TRANSPORTS = re.compile(r"\.SendWebRequest\(|new (?:System\.Net\.)?WebClient\(|WebRequest\.Create\("
                        r"|new (?:System\.Net\.Http\.)?HttpClient\(|new (?:System\.Net\.WebSockets\.)?ClientWebSocket\("
                        r"|new (?:System\.Net\.Sockets\.)?(?:TcpClient|UdpClient|Socket)\(")

# file -> (kind, count): kind "uwr" = covered by the SendWebRequest prefix; "guard:<text>" = a refusal containing
# <text> within GUARD_SPAN lines before each site; "entry:<method>:<loop>" = the refusal at <method>'s entry and
# <loop> started only from <method>; "exempt:<why>".
SITES = {
    "ApiClient.cs": ("uwr", 17),
    "MusicEngine.cs": ("uwr", 1),
    "MusicStreamProbe.cs": ("uwr", 1),
    "CustomCosmetics.cs": ("guard:GET_cosmetics-zip", 1),
    "EmojiSprites.cs": ("guard:GET_emoji-sheet", 1),
    "MusicAssets.cs": ("guard:GET_music-asset", 1),
    "ChatClient.cs": ("entry:Connect:RunLoop", 1),
    "RegionPingSweep.cs": ("exempt:Photon region pings, UDP, nothing the sitting builds (decision 12)", 1),
}
GUARD_SPAN = 8


def frametime_blocks(lines):
    """Line indexes inside `#if SCR_FRAMETIME` ... `#endif` (or `#else`) blocks."""
    inside, out = False, set()
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s == "#if SCR_FRAMETIME":
            inside = True
            continue
        if inside and (s.startswith("#endif") or s.startswith("#else") or s.startswith("#elif")):
            inside = False
            continue
        if inside:
            out.add(i)
    return out


def main():
    w = sys.argv[1]
    pdir = os.path.join(w, "plugin")
    bad, found = [], {}
    for name in sorted(os.listdir(pdir)):
        if not name.endswith(".cs"):
            continue
        lines = open(os.path.join(pdir, name), encoding="utf-8-sig", errors="replace").read().splitlines()
        hits = [i for i, ln in enumerate(lines) if TRANSPORTS.search(ln) and not ln.lstrip().startswith("//")]
        if hits:
            found[name] = (lines, hits)
    for name in sorted(set(found) | set(SITES)):
        if name not in SITES:
            bad.append("%s: %d transport site(s) not in the table (classify them)" % (name, len(found[name][1])))
            continue
        kind, want = SITES[name]
        lines, hits = found.get(name, ([], []))
        if len(hits) != want:
            bad.append("%s: %d transport sites, the table says %d" % (name, len(hits), want))
        ft = frametime_blocks(lines)
        for i in hits:
            if kind == "uwr":
                ok = ".SendWebRequest(" in lines[i]
                why = "SendWebRequest prefix"
            elif kind.startswith("guard:"):
                text = kind[6:]
                ok = any(j in ft and "FtUpload.Closed" in lines[j] and text in lines[j]
                         for j in range(max(0, i - GUARD_SPAN), i))
                why = "refusal %s within %d lines before" % (text, GUARD_SPAN)
            elif kind.startswith("entry:"):
                _, meth, loop = kind.split(":")
                src = "\n".join(lines)
                m = re.search(r"static void " + meth + r"\(\)\s*\{", src)
                ok = False
                if m:
                    body = src[m.end():m.end() + 400]
                    first = body.lstrip().splitlines()[:2]
                    ok = (len(first) == 2 and first[0].strip() == "#if SCR_FRAMETIME"
                          and "FtUpload.Closed" in first[1] and "return;" in first[1])
                    calls = [k for k, ln in enumerate(lines) if (loop + "(") in ln and "static" not in ln]
                    starts = [k for k in calls if "Task.Run" in lines[k]]
                    ok = ok and len(calls) == 1 and len(starts) == 1 and k_in_method(lines, starts[0], meth)
                why = "refusal at %s's entry; %s started only there" % (meth, loop)
            else:
                ok, why = True, kind
            print("%s %s:%d %s (%s)" % ("ok  " if ok else "FAIL", name, i + 1, lines[i].strip()[:80], why))
            if not ok:
                bad.append("%s:%d not covered (%s)" % (name, i + 1, why))
    fr = open(os.path.join(pdir, "FtRoute.cs"), encoding="utf-8-sig").read()
    pre = re.search(r"\[HarmonyPatch\(typeof\(UnityWebRequest\), nameof\(UnityWebRequest\.SendWebRequest\)\)\]\s*"
                    r"internal static class FtRoute_SendPatch\s*\{(.*?)\n    \}", fr, re.S)
    if not pre or "FtRoute.Allow(" not in pre.group(1) or "[HarmonyPrefix]" not in pre.group(1):
        bad.append("FtRoute.cs: the SendWebRequest prefix calling FtRoute.Allow is missing")
    pl = open(os.path.join(pdir, "Plugin.cs"), encoding="utf-8-sig").read()
    if "GetCustomAttributes(typeof(HarmonyPatch), true)" not in pl or "CreateClassProcessor(type).Patch()" not in pl:
        bad.append("Plugin.cs: the attribute loop that applies every [HarmonyPatch] class is missing")
    total = sum(len(h) for _, h in found.values())
    print("transport sites %d in %d files; table %d" % (total, len(found), sum(c for _, c in SITES.values())))
    for b in bad:
        print("FAIL: " + b)
    print("ROUTES CHECK %s" % ("PASS" if not bad else "FAIL"))
    return 0 if not bad else 1


def k_in_method(lines, k, meth):
    """Whether line k lies in the method named meth: the nearest method header above it names meth."""
    for j in range(k, -1, -1):
        m = re.search(r"\b(?:private|internal|public)\s+static\s+[\w<>\[\]]+\s+(\w+)\(", lines[j])
        if m:
            return m.group(1) == meth
    return False


if __name__ == "__main__":
    sys.exit(main())
