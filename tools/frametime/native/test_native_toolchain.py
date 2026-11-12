"""B11 D2 feasibility probe: can this seat build a Windows x64 DLL that exports one C function?

It names every compiler it finds, and passes only when a mingw-w64 cross compiler builds a DLL whose PE export table
(read as data) names the function. The failure message lists what the seat has, so a red run is the evidence.
"""
import os
import shutil
import struct
import subprocess
import tempfile

TOOLS = ["x86_64-w64-mingw32-gcc", "x86_64-w64-mingw32-gcc-win32", "x86_64-w64-mingw32-gcc-posix", "gcc", "cc",
         "clang", "zig", "tcc", "x86_64-w64-mingw32-objdump", "llvm-objdump"]
SRC = r"""
#include <stdint.h>
__declspec(dllexport) void ft_probe(void *prof, int ev, uint32_t gen, int serial) { (void)prof; (void)ev; (void)gen; (void)serial; }
"""


def pe_exports(path):
    b = open(path, "rb").read()
    pe = struct.unpack_from("<I", b, 0x3C)[0]
    assert b[pe:pe + 4] == b"PE\0\0"
    machine, nsec = struct.unpack_from("<HH", b, pe + 4)
    optsz = struct.unpack_from("<H", b, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", b, opt)[0]
    exp_rva = struct.unpack_from("<I", b, opt + (96 if magic == 0x10B else 112))[0]
    secs = [struct.unpack_from("<8sIIII", b, opt + optsz + 40 * i)[1:] for i in range(nsec)]

    def off(rva):
        for vsz, va, rsz, rptr in secs:
            if va <= rva < va + max(vsz, rsz):
                return rva - va + rptr
        raise ValueError(hex(rva))
    e = off(exp_rva)
    nnames, anames = struct.unpack_from("<I", b, e + 24)[0], struct.unpack_from("<I", b, e + 32)[0]
    names = []
    for i in range(nnames):
        o = off(struct.unpack_from("<I", b, off(anames) + 4 * i)[0])
        names.append(b[o:b.index(b"\0", o)].decode("ascii"))
    return machine, names


def test_seat_builds_a_windows_x64_dll():
    have = {t: shutil.which(t) for t in TOOLS}
    found = ", ".join("%s=%s" % (t, p) for t, p in have.items() if p) or "none"
    cc = have["x86_64-w64-mingw32-gcc"] or have["x86_64-w64-mingw32-gcc-win32"] or have["x86_64-w64-mingw32-gcc-posix"]
    assert cc, "no mingw-w64 cross compiler on this seat; compilers found: %s" % found
    d = tempfile.mkdtemp()
    c, dll = os.path.join(d, "p.c"), os.path.join(d, "p.dll")
    open(c, "w").write(SRC)
    p = subprocess.run([cc, "-O2", "-shared", "-s", "-o", dll, c], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert p.returncode == 0, "%s failed: %s (found: %s)" % (cc, p.stderr.decode("utf-8", "replace")[:400], found)
    machine, names = pe_exports(dll)
    assert machine == 0x8664 and "ft_probe" in names, "machine 0x%x exports %s (found: %s)" % (machine, names, found)
    print("TOOLCHAIN %s builds an x64 DLL exporting ft_probe; found: %s" % (cc, found))
