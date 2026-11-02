#!/usr/bin/env python3
"""ft_absent.py: a DLL-level check that no format M code or string is in a shipped build (FORMAT-M-PLAN.md V2 part d;
it complements hunk_check.py's source proof and the scan's marker needles). Needles are searched as raw bytes at any
offset (lesson 157): user strings as UTF-16LE (the #US heap), type names as UTF-8 (the #Strings heap, lesson 123).
  python -I -B ft_absent.py <dll> absent     a Release or Thunderstore DLL: every needle absent in both encodings
  python -I -B ft_absent.py <dll> present    the FrameTime DLL, the positive control: every needle present in its own
                                             encoding (so an absent result above is not a blind probe)
Exit 0 when the expectation holds, 1 otherwise."""
import sys

STRINGS = ["[FRAME-TIME]", "SCR_BUILD_VARIANT=FRAMETIME", "frametime: refused"]     # user strings: UTF-16LE
TYPES = ["FtSchedule", "FtMenu", "FtRoute_SendPatch", "FtUpload", "FtArm", "FtDrive", "FtRematch", "FtReplay", "FtA3"]


def main():
    path, want = sys.argv[1], sys.argv[2]
    if want not in ("absent", "present"):
        sys.exit("usage: ft_absent.py <dll> absent|present")
    b = open(path, "rb").read()
    bad = 0
    for n in STRINGS + TYPES:
        u16 = n.encode("utf-16-le") in b
        u8 = n.encode("utf-8") in b
        own = u16 if n in STRINGS else u8
        ok = (not u16 and not u8) if want == "absent" else own
        print("%s %-28s utf16=%s utf8=%s" % ("ok  " if ok else "FAIL", n, int(u16), int(u8)))
        bad += 0 if ok else 1
    print("FT %s %s: %s (%d bytes)" % (want.upper(), "PASS" if bad == 0 else "FAIL", path, len(b)))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
