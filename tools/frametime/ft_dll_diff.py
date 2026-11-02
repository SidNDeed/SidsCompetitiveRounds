#!/usr/bin/env python3
"""ft_dll_diff.py: the integrity proof's metadata dump for two DLLs that were expected equal (FORMAT-M-PLAN.md V2
part d, steps 2 and 3): sha256 and size of each, the informational-version strings each carries (UTF-8 and
UTF-16LE, `<version>+<40 hex>` or bare), whether either holds a local users path, and the differing byte ranges
(count, first eight). It diagnoses only; the proof's verdict is the sha256 comparison.

Usage: python -I -B ft_dll_diff.py <a.dll> <b.dll>
"""
import hashlib
import re
import sys

VER = re.compile(rb"\d+\.\d+\.\d+(?:\.\d+)?\+[0-9a-f]{40}|\d+\.\d+\.\d+(?:\.\d+)?(?=\x00)")
USERS = [b"C:\\Users", b"C:/Users", "C:\\Users".encode("utf-16-le"), "C:/Users".encode("utf-16-le")]


def info(path):
    b = open(path, "rb").read()
    u16 = b.decode("utf-16-le", errors="replace").encode("utf-8", errors="replace") if len(b) % 2 == 0 else b""
    vers = sorted(set(m.group(0).decode() for m in VER.finditer(b))
                  | set(m.group(0).decode() for m in VER.finditer(u16) if b"+" in m.group(0)))
    users = [u for u in USERS if u in b]
    return b, hashlib.sha256(b).hexdigest(), vers, users


def ranges(a, b):
    out = []
    n = min(len(a), len(b))
    i = 0
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    if len(a) != len(b):
        out.append((n, max(len(a), len(b))))
    return out


def main():
    pa, pb = sys.argv[1], sys.argv[2]
    a, ha, va, ua = info(pa)
    b, hb, vb, ub = info(pb)
    print("a: %s sha256 %s bytes %d" % (pa, ha, len(a)))
    print("b: %s sha256 %s bytes %d" % (pb, hb, len(b)))
    print("a versions: %s" % ", ".join(va[:6]))
    print("b versions: %s" % ", ".join(vb[:6]))
    print("a users paths: %d; b users paths: %d" % (len(ua), len(ub)))
    r = ranges(a, b)
    print("differing ranges: %d%s" % (len(r), "" if not r else "; first: " + ", ".join("%d-%d" % x for x in r[:8])))
    print("EQUAL" if ha == hb else "DIFFERENT")
    return 0 if ha == hb else 1


if __name__ == "__main__":
    sys.exit(main())
