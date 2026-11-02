#!/usr/bin/env python3
"""ft_dll_diff.py: the integrity proof's metadata dump for two DLLs that were expected equal (FORMAT-M-PLAN.md V2
part d, steps 2 and 3): sha256 and size of each, each module's version ID (MVID, read from the CLI metadata: the
Module table's single row, its Mvid index into the #GUID heap), the informational-version strings each carries
(UTF-8 and UTF-16LE, `<version>+<40 hex>` or bare), whether either holds a local users path, and the differing byte
ranges (count, first eight). It diagnoses only; the proof's verdict is the sha256 comparison.

Usage: python -I -B ft_dll_diff.py <a.dll> <b.dll>
"""
import hashlib
import re
import struct
import sys
import uuid

VER = re.compile(rb"\d+\.\d+\.\d+(?:\.\d+)?\+[0-9a-f]{40}|\d+\.\d+\.\d+(?:\.\d+)?(?=\x00)")
USERS = [b"C:\\Users", b"C:/Users", "C:\\Users".encode("utf-16-le"), "C:/Users".encode("utf-16-le")]


def info(path):
    b = open(path, "rb").read()
    u16 = b.decode("utf-16-le", errors="replace").encode("utf-8", errors="replace") if len(b) % 2 == 0 else b""
    vers = sorted(set(m.group(0).decode() for m in VER.finditer(b))
                  | set(m.group(0).decode() for m in VER.finditer(u16) if b"+" in m.group(0)))
    users = [u for u in USERS if u in b]
    return b, hashlib.sha256(b).hexdigest(), vers, users


def mvid(b):
    """The module version ID as .NET prints a Guid, from the PE's CLI header (data directory 14) -> the metadata root
    (BSJB) -> the #~ (or #-) stream's Module table row 0 -> its Mvid index (1-based) into #GUID. Raises ValueError
    on anything that does not parse."""
    def u16(o): return struct.unpack_from("<H", b, o)[0]
    def u32(o): return struct.unpack_from("<I", b, o)[0]
    try:
        pe = u32(0x3C)
        if b[pe:pe + 4] != b"PE\0\0":
            raise ValueError("no PE signature")
        nsec, opt_size = u16(pe + 6), u16(pe + 20)
        opt = pe + 24
        magic = u16(opt)
        dirs = opt + {0x10B: 96, 0x20B: 112}[magic]
        cli_rva = u32(dirs + 14 * 8)
        secs = [(u32(s + 12), max(u32(s + 8), u32(s + 16)), u32(s + 20))
                for s in (opt + opt_size + 40 * i for i in range(nsec))]

        def off(rva):
            for va, size, raw in secs:
                if va <= rva < va + size:
                    return rva - va + raw
            raise ValueError("rva 0x%x in no section" % rva)

        if not cli_rva:
            raise ValueError("no CLI header")
        md = off(u32(off(cli_rva) + 8))
        if u32(md) != 0x424A5342:
            raise ValueError("no BSJB metadata signature")
        p = md + 16 + u32(md + 12)
        nstreams = u16(p + 2)
        p += 4
        streams = {}
        for _ in range(nstreams):
            so, ss = u32(p), u32(p + 4)
            end = b.index(b"\0", p + 8)
            streams[b[p + 8:end].decode("ascii")] = (md + so, ss)
            p = p + 8 + ((end - (p + 8)) // 4 + 1) * 4
        tabs = streams.get("#~") or streams.get("#-")
        guids = streams.get("#GUID")
        if not tabs or not guids:
            raise ValueError("no #~ or #GUID stream")
        t = tabs[0]
        heap_sizes = b[t + 6]
        valid = struct.unpack_from("<Q", b, t + 8)[0]
        if not valid & 1:
            raise ValueError("no Module table")
        rows = t + 24 + 4 * bin(valid).count("1") + (4 if heap_sizes & 0x40 else 0)
        sidx = 4 if heap_sizes & 1 else 2
        gidx = 4 if heap_sizes & 2 else 2
        o = rows + 2 + sidx  # Module row 0: Generation (2), Name (string index), Mvid (guid index)
        g = u32(o) if gidx == 4 else u16(o)
        if g < 1 or g * 16 > guids[1]:
            raise ValueError("Mvid index %d outside #GUID" % g)
        return str(uuid.UUID(bytes_le=bytes(b[guids[0] + (g - 1) * 16:guids[0] + g * 16])))
    except (struct.error, KeyError, IndexError, UnicodeDecodeError) as e:
        raise ValueError("unparsable metadata: %r" % e)


def mvid_text(b):
    try:
        return mvid(b)
    except ValueError as e:
        return "unreadable (%s)" % e


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
    ma, mb = mvid_text(a), mvid_text(b)
    print("a mvid: %s" % ma)
    print("b mvid: %s" % mb)
    if ma.startswith("unreadable") or mb.startswith("unreadable"):
        print("mvids: not compared (one is unreadable)")
    else:
        print("mvids: %s" % ("equal" if ma == mb else "DIFFERENT"))
    print("a versions: %s" % ", ".join(va[:6]))
    print("b versions: %s" % ", ".join(vb[:6]))
    print("a users paths: %d; b users paths: %d" % (len(ua), len(ub)))
    r = ranges(a, b)
    print("differing ranges: %d%s" % (len(r), "" if not r else "; first: " + ", ".join("%d-%d" % x for x in r[:8])))
    print("EQUAL" if ha == hb else "DIFFERENT")
    return 0 if ha == hb else 1


if __name__ == "__main__":
    sys.exit(main())
