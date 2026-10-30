"""Fixtures for the release digest step (tools/register_release_digests.py).

build_assembly() writes a small but complete .NET assembly image from ECMA-335
Partition II: DOS and PE headers (PE32 or PE32+), one section, the CLI header,
the metadata root, and the #~, #Strings, #US, #GUID and #Blob streams, with the
Module, TypeRef, TypeDef, MethodDef, MemberRef, CustomAttribute, Assembly and
AssemblyRef tables. It carries what the client's build tuple is read from: a
BepInPlugin attribute on a CompetitiveRounds.Plugin type, the assembly's
InformationalVersion attribute, an embedded attribute whose constructor is a
MethodDef (Roslyn emits those, so a real DLL has them), and a #US banner
holding the SCR_BUILD_VARIANT marker. It is written here, from the
specification, and shares no code with the step's reader, so the reader is
checked against an independent writer rather than against itself.

client_lists() reads the client's game-file list from the C# source, and
make_install() lays out a game install the way BepInEx and the client find it,
so the expected file ids come from the client and not from the step.
"""

import hashlib
import os
import re
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
PLUGIN_DIR = os.path.join(REPO, "plugin")

STANDALONE = "SCR_BUILD_VARIANT=STANDALONE"
THUNDERSTORE = "SCR_BUILD_VARIANT=THUNDERSTORE"
FULL_SHA = "0123456789abcdef0123456789abcdef01234567"
GUID = "com.competitiverounds.mod"
BUILD_ID = "21020021"


def _cint(n):
    """II.23.2 compressed unsigned integer."""
    if n < 0x80:
        return bytes([n])
    if n < 0x4000:
        return bytes([0x80 | (n >> 8), n & 0xFF])
    return bytes([0xC0 | (n >> 24), (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])


def _ser(s):
    """II.23.3 SerString: 0xFF for null, else a packed length and UTF-8."""
    if s is None:
        return b"\xff"
    raw = s.encode("utf-8")
    return _cint(len(raw)) + raw


class _Strings:
    def __init__(self):
        self.buf = bytearray(b"\0")
        self.at = {"": 0}

    def __call__(self, s):
        if s not in self.at:
            self.at[s] = len(self.buf)
            self.buf += s.encode("utf-8") + b"\0"
        return self.at[s]


class _Blobs:
    def __init__(self):
        self.buf = bytearray(b"\0")

    def __call__(self, raw):
        at = len(self.buf)
        self.buf += _cint(len(raw)) + raw
        return at


def _pad4(raw):
    return bytes(raw) + b"\0" * (-len(raw) % 4)


def _pack(widths, values):
    out = bytearray()
    for w, v in zip(widths, values):
        out += struct.pack({1: "<B", 2: "<H", 4: "<I"}[w], v)
    return bytes(out)


def build_assembly(version="1.41.0", guid=GUID, plugin_name="Competitive ROUNDS",
                   informational="1.0.0+" + FULL_SHA, markers=(STANDALONE,), plugins=1, infos=1,
                   wide_heaps=False, pe32plus=False, pad_typerefs=0):
    """The bytes of a synthetic assembly. `plugins` BepInPlugin attributes (on
    as many Plugin types), `infos` InformationalVersion attributes (None as
    `informational` writes a null string), one #US banner per marker,
    `pad_typerefs` extra TypeRef rows (2048 or more widens the
    HasCustomAttribute coded index to 4 bytes), `wide_heaps` 4-byte heap
    indexes, `pe32plus` a PE32+ optional header."""
    S, B = _Strings(), _Blobs()
    us = bytearray(b"\0")
    for m in markers:
        raw = ("Competitive ROUNDS v%s loaded! [%s]" % (version, m)).encode("utf-16-le")
        us += _cint(len(raw) + 1) + raw + b"\0"
    guid_heap = bytes(range(1, 17))

    # Rows, by table. AssemblyRef: 1 netstandard, 2 BepInEx.
    assembly_refs = [("netstandard", (2, 1, 0, 0)), ("BepInEx", (5, 4, 19, 0))]
    type_refs = [(2, "BepInPlugin", "BepInEx"),
                 (1, "AssemblyInformationalVersionAttribute", "System.Reflection"),
                 (2, "BaseUnityPlugin", "BepInEx"),
                 (1, "Attribute", "System")]
    type_refs += [(1, "Pad%d" % i, "Padding") for i in range(pad_typerefs)]
    # TypeDef: 1 <Module>, 2.. the Plugin types, last the embedded attribute,
    # which owns MethodDef 1 (its .ctor); the earlier types own no method.
    type_defs = [(0, "<Module>", "", None, 1, 1)]
    for k in range(plugins):
        type_defs.append((0x00100001, "Plugin" if k == 0 else "Plugin%d" % k, "CompetitiveRounds",
                          ("ref", 3), 1, 1))
    type_defs.append((0x00100100, "EmbeddedAttribute", "Microsoft.CodeAnalysis", ("ref", 4), 1, 1))
    embedded_row = len(type_defs)
    method_defs = [(0, 0, 0x1886, ".ctor", bytes([0x20, 0x00, 0x01]), 1)]
    member_refs = [(1, ".ctor", bytes([0x20, 0x03, 0x01, 0x0E, 0x0E, 0x0E])),
                   (2, ".ctor", bytes([0x20, 0x01, 0x01, 0x0E]))]
    plugin_value = b"\x01\x00" + _ser(guid) + _ser(plugin_name) + _ser(version) + b"\x00\x00"
    info_value = b"\x01\x00" + _ser(informational) + b"\x00\x00"

    rows = {0x00: 1, 0x01: len(type_refs), 0x02: len(type_defs), 0x06: len(method_defs),
            0x0A: len(member_refs), 0x0C: infos + plugins + 1, 0x20: 1, 0x23: len(assembly_refs)}

    sw = bw = gw = 4 if wide_heaps else 2

    def coded(bits, tables):
        return 2 if max(rows.get(t, 0) for t in tables) < (1 << (16 - bits)) else 4

    hca_tables = (0x06, 0x04, 0x01, 0x02, 0x08, 0x09, 0x0A, 0x00, 0x0E, 0x17, 0x14, 0x11, 0x1A, 0x1B,
                  0x20, 0x23, 0x26, 0x27, 0x28, 0x2A, 0x2C, 0x2B)
    rs_w = coded(2, (0x00, 0x1A, 0x23, 0x01))
    tdor_w = coded(2, (0x02, 0x01, 0x1B))
    mrp_w = coded(3, (0x02, 0x01, 0x1A, 0x06, 0x1B))
    hca_w = coded(5, hca_tables)
    cat_w = coded(3, (0x06, 0x0A))

    tables = bytearray()
    tables += _pack((2, sw, gw, gw, gw), (0, S("CompetitiveRounds.dll"), 1, 0, 0))
    for scope, name, ns in type_refs:
        tables += _pack((rs_w, sw, sw), ((scope << 2) | 2, S(name), S(ns)))
    for flags, name, ns, extends, field_list, method_list in type_defs:
        ext = 0 if extends is None else (extends[1] << 2) | 1
        tables += _pack((4, sw, sw, tdor_w, 2, 2), (flags, S(name), S(ns), ext, field_list, method_list))
    for rva, impl, flags, name, sig, param_list in method_defs:
        tables += _pack((4, 2, 2, sw, bw, 2), (rva, impl, flags, S(name), B(sig), param_list))
    for parent_ref, name, sig in member_refs:
        tables += _pack((mrp_w, sw, bw), ((parent_ref << 3) | 1, S(name), B(sig)))
    # CustomAttribute, sorted by parent: the assembly (tag 14), then the
    # Plugin types (TypeDef, tag 3), then the embedded attribute's own type.
    attributes = [((1 << 5) | 14, (2 << 3) | 3, info_value)] * infos
    attributes += [(((2 + k) << 5) | 3, (1 << 3) | 3, plugin_value) for k in range(plugins)]
    attributes.append(((embedded_row << 5) | 3, (1 << 3) | 2, b"\x01\x00\x00\x00"))
    for parent, ctor, value in attributes:
        tables += _pack((hca_w, cat_w, bw), (parent, ctor, B(value)))
    tables += _pack((4, 2, 2, 2, 2, 4, bw, sw, sw), (0x8004, 1, 0, 0, 0, 0, 0, S("CompetitiveRounds"), 0))
    for name, (major, minor, build, rev) in assembly_refs:
        tables += _pack((2, 2, 2, 2, 4, bw, sw, sw, bw), (major, minor, build, rev, 0, 0, S(name), 0, 0))

    valid = sum(1 << t for t in rows)
    header = struct.pack("<IBBBBQQ", 0, 2, 0, 0x07 if wide_heaps else 0, 1, valid, 0x000016003301FA00)
    header += b"".join(struct.pack("<I", rows[t]) for t in sorted(rows))
    streams = [("#~", _pad4(header + tables)), ("#Strings", _pad4(S.buf)), ("#US", _pad4(us)),
               ("#GUID", guid_heap), ("#Blob", _pad4(B.buf))]

    version_text = b"v4.0.30319\0\0"
    names = [_pad4(name.encode("ascii") + b"\0") for name, _data in streams]
    offset = 16 + len(version_text) + 4 + sum(8 + len(n) for n in names)
    root = struct.pack("<IHHII", 0x424A5342, 1, 1, 0, len(version_text)) + version_text
    root += struct.pack("<HH", 0, len(streams))
    body = b""
    for (name, data), padded in zip(streams, names):
        root += struct.pack("<II", offset + len(body), len(data)) + padded
        body += data
    metadata = root + body

    text_rva, file_align, sect_align = 0x2000, 0x200, 0x2000
    cli = struct.pack("<IHHIIII", 72, 2, 5, text_rva + 72, len(metadata), 1, 0) + b"\0" * 48
    text = cli + metadata
    raw_size = len(text) + (-len(text) % file_align)
    image_size = text_rva + len(text) + (-len(text) % sect_align)
    directories = bytearray(16 * 8)
    struct.pack_into("<II", directories, 14 * 8, text_rva, 72)
    if pe32plus:
        optional = struct.pack("<HBBIIIII", 0x20B, 48, 0, raw_size, 0, 0, 0, text_rva)
        optional += struct.pack("<QIIHHHHHHIIIIHHQQQQII", 0x180000000, sect_align, file_align, 4, 0, 0, 0,
                                4, 0, 0, image_size, 0x200, 0, 3, 0x8540, 0x400000, 0x4000, 0x100000,
                                0x2000, 0, 16)
        machine = 0x8664
    else:
        optional = struct.pack("<HBBIIIIII", 0x10B, 48, 0, raw_size, 0, 0, 0, text_rva, 0)
        optional += struct.pack("<IIIHHHHHHIIIIHHIIIIII", 0x10000000, sect_align, file_align, 4, 0, 0, 0,
                                4, 0, 0, image_size, 0x200, 0, 3, 0x8540, 0x100000, 0x1000, 0x100000,
                                0x1000, 0, 16)
        machine = 0x14C
    optional += bytes(directories)
    coff = struct.pack("<HHIIIHH", machine, 1, 0, 0, 0, len(optional), 0x2022)
    section = struct.pack("<8sIIIIIIHHI", b".text", len(text), text_rva, raw_size, 0x200, 0, 0, 0, 0,
                          0x60000020)
    dos = bytearray(0x80)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x80)
    headers = bytes(dos) + b"PE\0\0" + coff + optional + section
    assert len(headers) <= 0x200
    return headers + b"\0" * (0x200 - len(headers)) + text + b"\0" * (raw_size - len(text))


# -- the client's game-file list, read from its source ---------------------------------

def _source(name):
    with open(os.path.join(PLUGIN_DIR, name), encoding="utf-8") as f:
        return f.read()


def client_lists():
    """(GAME_FILES, LOADER_FILES, DOORSTOP_FILE) as plugin/IdentityClockEvidence.cs declares them."""
    src = _source("IdentityClockEvidence.cs")

    def array(name):
        m = re.search(r"internal static readonly string\[\] %s = \{(.*?)\};" % name, src, re.S)
        return tuple(re.findall(r'"([^"]+)"', m.group(1)))

    door = re.search(r'internal const string DOORSTOP_FILE = "([^"]+)";', src).group(1)
    return array("GAME_FILES"), array("LOADER_FILES"), door


def _content(i, size):
    seed = hashlib.sha256(b"release-digests-fixture-%d" % i).digest()
    return (seed * (size // len(seed) + 1))[:size]


# File sizes by client file id: an empty file, one exactly one read unit,
# several more than one unit, the rest small.
SIZES = {0: 200_003, 1: 65_536, 2: 0, 3: 131_072, 6: 70_001}


def make_install(base, build_id=BUILD_ID, installdir="ROUNDS"):
    """A Steam library under `base` holding a game install laid out as BepInEx
    resolves it (<root>/ROUNDS_Data/Managed, <root>/BepInEx/core, the root),
    with the library's app manifest. Returns (root, {file id: (name, sha256)})."""
    game, loader, door = client_lists()
    steamapps = os.path.join(base, "steamapps")
    root = os.path.join(steamapps, "common", installdir)
    managed = os.path.join(root, "ROUNDS_Data", "Managed")
    core = os.path.join(root, "BepInEx", "core")
    for d in (managed, core):
        os.makedirs(d)
    for exe in ("ROUNDS.exe", "UnityCrashHandler64.exe"):
        with open(os.path.join(root, exe), "wb") as f:
            f.write(b"MZ fixture executable")
    paths = [os.path.join(managed, n) for n in game] + [os.path.join(core, n) for n in loader]
    paths.append(os.path.join(root, door))
    expected = {}
    for i, path in enumerate(paths):
        data = _content(i, SIZES.get(i, 1_000 + 37 * i))
        with open(path, "wb") as f:
            f.write(data)
        expected[i] = (os.path.basename(path), hashlib.sha256(data).hexdigest())
    with open(os.path.join(steamapps, "appmanifest_1557740.acf"), "w", encoding="utf-8") as f:
        f.write('"AppState"\n{\n\t"appid"\t\t"1557740"\n\t"name"\t\t"ROUNDS"\n'
                '\t"installdir"\t\t"%s"\n\t"buildid"\t\t"%s"\n}\n' % (installdir, build_id))
    return root, expected
