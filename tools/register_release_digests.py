#!/usr/bin/env python3
"""register_release_digests.py -- the release step that fills the two digest
registries the evidence checks compare against.

A seat's evidence record states its own build tuple and DLL digest, and the
identity-clock record states the digests of a fixed list of game files. The
server compares them with two registries that start empty:

    mod_release_digests  (migration 368)  version, variant, commit_sha, dll_sha256, source
    game_file_digests    (migration 372)  file_id, game_version, sha256

This step reads the release DLL and the game files exactly as the client does
and registers each row through the admin routes that already exist:

    POST /api/v1/admin/release-digests    admin action release_digest
    POST /api/v1/admin/game-file-digests  admin action game_file_digest

Both are signed with ADMIN_HMAC_SECRET over admin:{steam id}:{action}:{target}
(main._admin_canonical) by an admin_users steam id, and both insert ON CONFLICT
DO NOTHING, answering "registered" or "already_registered".

What a row must hold, byte for byte, because the server compares exact tuples:

  version     Plugin.ModVersion, the third argument of the DLL's BepInPlugin
              attribute (PeerBuild.BuildValue reports the same constant)
  variant     "standalone", "thunderstore" or "g3": the build's #if branch,
              read from the DLL's SCR_BUILD_VARIANT= marker, whose #if
              branches are the same as PeerBuild's (lower case: the column's
              'STANDALONE' default is never what a client reports)
  commit      the first 12 characters after the '+' of the assembly's
              InformationalVersion attribute, or "nosha" when there is none
  dll_sha256  SHA-256 of the DLL file's bytes, 64 lowercase hex
              (SeatEvidence.Hash); the uploaded release asset is the authority
  file_id     the position in IdentityClockEvidence.FileList: GAME_FILES under
              <root>/<exe name>_Data/Managed (0..7), LOADER_FILES under
              <root>/BepInEx/core (8..15), winhttp.dll in <root> (16)
  sha256      SHA-256 of that file's bytes, 64 lowercase hex, read under the
              client survey's caps (IdentityClockCore.Survey); a file the
              client could not read to the end has no digest to register

The step refuses, with exit 3 and nothing sent: a DLL that is not the
Competitive Rounds plug-in, whose embedded version is not --version, whose
embedded commit does not start with --commit, whose variant is not --variant,
or whose tuple the client itself would not report; and a game install that does
not hold every listed file in a state the client reads as ok.

Usage (the admin secret only from the environment, never in argv or a file):

    set ADMIN_HMAC_SECRET=...
    set SCR_API_BASE=...      (the primary's API base URL; no default)
    python tools/register_release_digests.py --dll dist/CompetitiveRounds-1.41.0.dll
        --version 1.41.0 --variant standalone --commit <release sha>
        --game-root "<Steam library>/steamapps/common/ROUNDS"
        --admin <admin steam64> --dry-run

then the same without --dry-run. The game-file rows are labelled with the
game's Steam build id (steam.<buildid>, read from the library's
appmanifest_1557740.acf) unless --game-version names another label.

Exit codes: 0 done (also a dry run and an emitted file); 1 the server answered
a row with anything but a registration status, or a request failed (the rows
before it stand, and a re-run is safe); 2 a variable the real run reads is not
set (nothing sent); 3 refused input (nothing sent).

Idempotent: a second run with the same digests inserts nothing and says so.

--emit-sql FILE writes the identical inserts as a data-only migration instead
of calling the api: the migration channel the house used for admin-signed
writes from a seat whose environment does not carry the admin secret
(learnings #421, #443). It needs no secret and sends nothing.

--census FILE is a second mode with its own arguments: it registers one card
pool census, the dump file a reference seat writes when its [Debug]
CardPoolCensusDump setting is on (BepInEx/config/CompetitiveRounds.card-census.json,
plugin/CardDrawEvidence.cs EnsureCensusDump), in card_pool_registry (migration
370) through

    POST /api/v1/admin/card-pool-census    admin action card_census over the digest

whose body is the dump file. The file is judged by the server's own check,
card_measures.census_from_dump, loaded from backend/api of this checkout (never
a copy), after the route's own two steps before it (the body read as JSON, the
signed digest equal to the dump's): a file the route would answer with anything
but a registration is refused with exit 3 and nothing sent. --emit-sql writes
the one row register_census inserts as a data-only migration. Same environment,
--dry-run and exit codes as above; the api run also needs --mod-version, the
X-Mod-Version header the server's floor admits.

    python tools/register_release_digests.py --census <dump file>
        --expect-digest <64 hex> --admin <admin steam64> --mod-version 1.41.0 --dry-run
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import hmac
import importlib
import json
import os
import re
import stat
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# What the client reports. Each constant names the source it mirrors; the
# drift test in backend/tests/test_release_digests.py reads those sources and
# fails when one of them moves without this file.
# ---------------------------------------------------------------------------

PLUGIN_GUID = "com.competitiverounds.mod"                                   # Plugin.ModId
BEPINPLUGIN = ("BepInEx", "BepInPlugin")
INFORMATIONAL_VERSION = ("System.Reflection", "AssemblyInformationalVersionAttribute")
NO_COMMIT = "nosha"                                                         # PeerBuild.BuildValue
COMMIT_CHARS = 12
# ApiClient.BuildVariantMarker and PeerBuild.BuildValue: one #if chain each,
# THUNDERSTORE, then SCR_G3, then the default, in that order.
VARIANT_MARKERS = (
    ("SCR_BUILD_VARIANT=THUNDERSTORE", "thunderstore"),
    ("SCR_BUILD_VARIANT=G3", "g3"),
    ("SCR_BUILD_VARIANT=STANDALONE", "standalone"),
)

GAME_FILES = (                                                              # ids 0..7
    "Assembly-CSharp.dll", "Assembly-CSharp-firstpass.dll", "Photon3Unity3D.dll", "PhotonRealtime.dll",
    "PhotonUnityNetworking.dll", "PhotonUnityNetworking.Utilities.dll", "UnityEngine.CoreModule.dll",
    "UnityEngine.Physics2DModule.dll")
LOADER_FILES = (                                                            # ids 8..15
    "BepInEx.dll", "BepInEx.Preloader.dll", "0Harmony.dll", "BepInEx.Harmony.dll", "HarmonyXInterop.dll",
    "MonoMod.RuntimeDetour.dll", "MonoMod.Utils.dll", "Mono.Cecil.dll")
DOORSTOP_FILE = "winhttp.dll"                                               # id 16

CHUNK_BYTES = 65536                     # IdentityClockCore: one survey unit reads one chunk
FILE_BYTES_MAX = 64 * 1024 * 1024       # a file read past this is read_failed
JOB_BYTES_MAX = 192 * 1024 * 1024       # the survey job stops at this many bytes ...
JOB_UNITS_MAX = 8192                    # ... or units; files it did not reach are not_yet
GDIG_MAX = 24                           # at most this many listed files are surveyed

OK, NO_FILE, READ_FAILED, NOT_YET = "ok", "no_file", "read_failed", "not_yet"
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400

# ---------------------------------------------------------------------------
# What the server accepts (seat_evidence._BUILD_PART, _HEX64, RELEASE_SOURCES;
# identity_clock_evidence.ice_register_game_file; main's two route handlers).
# ---------------------------------------------------------------------------

BUILD_PART = re.compile(r"[A-Za-z0-9._+\-]*")
HEX64 = re.compile(r"[0-9a-f]{64}")
SOURCES = ("release", "beta")
RELEASE_ROUTE = "/api/v1/admin/release-digests"
GAME_FILE_ROUTE = "/api/v1/admin/game-file-digests"
STEAM_APP_ID = "1557740"

EXIT_OK, EXIT_SERVER, EXIT_ENV, EXIT_REFUSED = 0, 1, 2, 3


class Refused(Exception):
    """Input the step will not register; nothing is sent."""


# ---------------------------------------------------------------------------
# The DLL: a minimal ECMA-335 metadata reader (Partition II, sections 22-25).
# It reads the PE headers, the CLI header, the metadata root and the #~ table
# stream as far as the CustomAttribute table, which is all the build tuple
# needs. Anything it cannot read is refused, never guessed.
# ---------------------------------------------------------------------------

# Coded indexes (II.24.2.6): tag bits and the table each tag names.
_CODED = {
    "TypeDefOrRef": (2, (0x02, 0x01, 0x1B)),
    "HasConstant": (2, (0x04, 0x08, 0x17)),
    "HasCustomAttribute": (5, (0x06, 0x04, 0x01, 0x02, 0x08, 0x09, 0x0A, 0x00, 0x0E, 0x17, 0x14,
                               0x11, 0x1A, 0x1B, 0x20, 0x23, 0x26, 0x27, 0x28, 0x2A, 0x2C, 0x2B)),
    "MemberRefParent": (3, (0x02, 0x01, 0x1A, 0x06, 0x1B)),
    "CustomAttributeType": (3, (None, None, 0x06, 0x0A, None)),
    "ResolutionScope": (2, (0x00, 0x1A, 0x23, 0x01)),
}

# The columns of tables 0x00..0x0C (II.22), the tables that precede and make up
# the CustomAttribute table: an int is a fixed width, "s"/"g"/"b" a heap index,
# ("t", table) a simple index, ("c", name) a coded index.
_SCHEMA = {
    0x00: (2, "s", "g", "g", "g"),                                          # Module
    0x01: (("c", "ResolutionScope"), "s", "s"),                             # TypeRef
    0x02: (4, "s", "s", ("c", "TypeDefOrRef"), ("t", 0x04), ("t", 0x06)),   # TypeDef
    0x03: (("t", 0x04),),                                                   # FieldPtr
    0x04: (2, "s", "b"),                                                    # Field
    0x05: (("t", 0x06),),                                                   # MethodPtr
    0x06: (4, 2, 2, "s", "b", ("t", 0x08)),                                 # MethodDef
    0x07: (("t", 0x08),),                                                   # ParamPtr
    0x08: (2, 2, "s"),                                                      # Param
    0x09: (("t", 0x02), ("c", "TypeDefOrRef")),                             # InterfaceImpl
    0x0A: (("c", "MemberRefParent"), "s", "b"),                             # MemberRef
    0x0B: (2, ("c", "HasConstant"), "b"),                                   # Constant
    0x0C: (("c", "HasCustomAttribute"), ("c", "CustomAttributeType"), "b"),  # CustomAttribute
}
_ASSEMBLY_TABLE, _TYPEDEF, _TYPEREF, _METHODDEF, _MEMBERREF, _CUSTOMATTRIBUTE = 0x20, 0x02, 0x01, 0x06, 0x0A, 0x0C


def _compressed(buf, o):
    """An ECMA-335 compressed unsigned integer at `o` (II.23.2): (value, next)."""
    b0 = buf[o]
    if b0 & 0x80 == 0:
        return b0, o + 1
    if b0 & 0xC0 == 0x80:
        return ((b0 & 0x3F) << 8) | buf[o + 1], o + 2
    if b0 & 0xE0 == 0xC0:
        return ((b0 & 0x1F) << 24) | (buf[o + 1] << 16) | (buf[o + 2] << 8) | buf[o + 3], o + 4
    raise Refused("the DLL's metadata holds a malformed compressed integer")


class _Metadata:
    def __init__(self, data: bytes):
        self.d = data
        self._names, self._starts = {}, None
        try:
            self._parse()
        except Refused:
            raise
        except (IndexError, ValueError, struct.error, UnicodeDecodeError) as e:
            raise Refused("the DLL's metadata cannot be read (%s)" % e.__class__.__name__)

    def _u16(self, o):
        return struct.unpack_from("<H", self.d, o)[0]

    def _u32(self, o):
        return struct.unpack_from("<I", self.d, o)[0]

    def _off(self, rva):
        for vaddr, vsize, rawptr, rawsize in self._sections:
            if vaddr <= rva < vaddr + vsize and rva - vaddr < rawsize:
                return rawptr + (rva - vaddr)
        raise Refused("the DLL's metadata points outside its sections")

    def _parse(self):
        d = self.d
        if d[:2] != b"MZ":
            raise Refused("not a PE file (no MZ header)")
        pe = self._u32(0x3C)
        if d[pe:pe + 4] != b"PE\0\0":
            raise Refused("not a PE file (no PE signature)")
        coff = pe + 4
        nsections, opt_size = self._u16(coff + 2), self._u16(coff + 16)
        opt = coff + 20
        dirs = {0x10B: opt + 96, 0x20B: opt + 112}.get(self._u16(opt))
        if dirs is None:
            raise Refused("not a PE32 or PE32+ image")
        if self._u32(dirs - 4) < 15 or self._u32(dirs + 14 * 8) == 0:
            raise Refused("not a .NET assembly (no CLI header)")
        self._sections = []
        for i in range(nsections):
            vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", d, opt + opt_size + 40 * i + 8)
            self._sections.append((vaddr, max(vsize, rawsize), rawptr, rawsize))
        cli = self._off(self._u32(dirs + 14 * 8))
        md = self._off(self._u32(cli + 8))
        if self._u32(md) != 0x424A5342:
            raise Refused("not a .NET assembly (no metadata root)")
        p = md + 16 + self._u32(md + 12)
        count = self._u16(p + 2)
        p += 4
        streams = {}
        for _ in range(count):
            off, size = struct.unpack_from("<II", d, p)
            end = d.index(b"\0", p + 8)
            name = d[p + 8:end].decode("ascii")
            streams[name] = (md + off, size)
            p += 8 + (((end - (p + 8)) + 4) & ~3)
        for need in ("#~", "#Strings", "#Blob"):
            if need not in streams:
                raise Refused("the DLL's metadata has no %s stream" % need)
        self._strings, self._blobs = streams["#Strings"], streams["#Blob"]
        t = streams["#~"][0]
        heap = d[t + 6]
        if heap & ~0x07:
            raise Refused("the DLL's table stream carries heap flags this reader does not read")
        valid = struct.unpack_from("<Q", d, t + 8)[0]
        p = t + 24
        rows = [0] * 64
        for i in range(64):
            if valid >> i & 1:
                rows[i] = self._u32(p)
                p += 4
        if rows[0x03] or rows[0x05] or rows[0x07]:
            raise Refused("the DLL's metadata uses pointer tables this reader does not read")
        self._rows = rows
        widths = {"s": 4 if heap & 1 else 2, "g": 4 if heap & 2 else 2, "b": 4 if heap & 4 else 2}

        def width(kind):
            if isinstance(kind, int):
                return kind
            if isinstance(kind, str):
                return widths[kind]
            if kind[0] == "t":
                return 2 if rows[kind[1]] < 0x10000 else 4
            bits, tables = _CODED[kind[1]]
            largest = max(rows[x] for x in tables if x is not None)
            return 2 if largest < (1 << (16 - bits)) else 4

        self._tables = {}
        for tid in range(0x0D):
            sizes = tuple(width(k) for k in _SCHEMA[tid])
            self._tables[tid] = (p, sum(sizes), sizes)
            p += sum(sizes) * rows[tid]
        if p > len(d):
            raise Refused("the DLL's metadata tables run past the end of the file")

    def _row(self, tid, index):
        if not 1 <= index <= self._rows[tid]:
            raise Refused("the DLL's metadata names row %d of table 0x%02X, which has %d"
                          % (index, tid, self._rows[tid]))
        base, width, sizes = self._tables[tid]
        o = base + (index - 1) * width
        out = []
        for s in sizes:
            out.append(self._u16(o) if s == 2 else self._u32(o))
            o += s
        return out

    def _string(self, index):
        base, size = self._strings
        end = self.d.find(b"\0", base + index, base + size) if index < size else -1
        if end < 0:
            raise Refused("the DLL's metadata names a string outside its heap")
        return self.d[base + index:end].decode("utf-8")

    def blob(self, index):
        base, size = self._blobs
        if index >= size:
            raise Refused("the DLL's metadata names a blob outside its heap")
        n, o = _compressed(self.d, base + index)
        if o + n > base + size:
            raise Refused("the DLL's metadata holds a blob that runs past its heap")
        return self.d[o:o + n]

    @staticmethod
    def _decode(name, value):
        bits, tables = _CODED[name]
        tag = value & ((1 << bits) - 1)
        return (tables[tag] if tag < len(tables) else None), value >> bits

    def type_name(self, table, index):
        """(namespace, name) of a TypeRef or TypeDef row; None for any other table."""
        key = (table, index)
        if key not in self._names:
            if table == _TYPEREF:
                _scope, name, namespace = self._row(_TYPEREF, index)
                self._names[key] = (self._string(namespace), self._string(name))
            elif table == _TYPEDEF:
                row = self._row(_TYPEDEF, index)
                self._names[key] = (self._string(row[2]), self._string(row[1]))
            else:
                self._names[key] = None
        return self._names[key]

    def _method_owner(self, method):
        """The TypeDef whose method list holds this MethodDef row: the last row
        whose MethodList start is at or before it (II.22.37)."""
        if self._starts is None:
            self._starts = [self._row(_TYPEDEF, i)[5] for i in range(1, self._rows[_TYPEDEF] + 1)]
        owner = bisect.bisect_right(self._starts, method)
        return self.type_name(_TYPEDEF, owner) if owner else None

    def custom_attributes(self):
        """Each custom attribute as (parent table, parent row, (namespace,
        name) of its constructor's type, constructor name, constructor
        signature blob index, value blob index)."""
        for i in range(1, self._rows[_CUSTOMATTRIBUTE] + 1):
            parent, ctor, value = self._row(_CUSTOMATTRIBUTE, i)
            ptable, prow = self._decode("HasCustomAttribute", parent)
            ctable, crow = self._decode("CustomAttributeType", ctor)
            if ctable == _MEMBERREF:
                klass, name, sig = self._row(_MEMBERREF, crow)
                otable, orow = self._decode("MemberRefParent", klass)
                owner = self.type_name(otable, orow)
            elif ctable == _METHODDEF:
                row = self._row(_METHODDEF, crow)
                name, sig, owner = row[3], row[4], self._method_owner(crow)
            else:
                raise Refused("the DLL holds a custom attribute with no constructor")
            yield ptable, prow, owner, self._string(name), sig, value


def _string_arguments(sig, value, n):
    """The n fixed arguments of an attribute whose constructor is
    `instance void .ctor(string x n)` (II.23.3): a list holding str or None."""
    if sig != bytes([0x20, n, 0x01] + [0x0E] * n):
        raise Refused("an attribute constructor of an unexpected shape")
    if value[:2] != b"\x01\x00":
        raise Refused("an attribute value without its prolog")
    o, out = 2, []
    for _ in range(n):
        if value[o] == 0xFF:
            out.append(None)
            o += 1
            continue
        length, o = _compressed(value, o)
        if o + length > len(value):
            raise Refused("an attribute value whose string runs past its blob")
        out.append(value[o:o + length].decode("utf-8"))
        o += length
    return out


def _is_build_part(s, limit):
    """SeatEvidenceCore.IsBuildPart: at most `limit` of [A-Za-z0-9._+-]."""
    return isinstance(s, str) and len(s) <= limit and BUILD_PART.fullmatch(s) is not None


def build_identity(data: bytes) -> dict:
    """The build tuple and digest the client reports for this DLL's bytes."""
    md = _Metadata(data)
    plugins, informational = [], []
    try:
        for ptable, prow, owner, name, sig, value in md.custom_attributes():
            if name != ".ctor":
                continue
            if owner == BEPINPLUGIN:
                plugins.append((ptable, prow, _string_arguments(md.blob(sig), md.blob(value), 3)))
            elif owner == INFORMATIONAL_VERSION and ptable == _ASSEMBLY_TABLE:
                informational.append(_string_arguments(md.blob(sig), md.blob(value), 1)[0])
    except (IndexError, ValueError, struct.error, UnicodeDecodeError) as e:
        raise Refused("the DLL's custom attributes cannot be read (%s)" % e.__class__.__name__)
    if len(plugins) != 1:
        raise Refused("the DLL carries %d BepInPlugin attributes, not exactly one" % len(plugins))
    ptable, prow, (guid, plugin_name, version) = plugins[0]
    if guid != PLUGIN_GUID:
        raise Refused("the DLL is not the Competitive Rounds plug-in (BepInPlugin GUID %r)" % (guid,))
    # PeerBuild.BuildValue: Attribute.GetCustomAttribute on the assembly (more
    # than one is an AmbiguousMatchException, caught, so "nosha" stands), the
    # part after the first '+', cut to 12; "nosha" when there is none.
    commit = NO_COMMIT
    if len(informational) == 1 and informational[0] is not None:
        iv = informational[0]
        plus = iv.find("+")
        if 0 <= plus and plus + 1 < len(iv):
            commit = iv[plus + 1:][:COMMIT_CHARS]
    found = [word for marker, word in VARIANT_MARKERS if marker.encode("utf-16-le") in data]
    if len(found) != 1:
        raise Refused("the DLL carries %s; exactly one SCR_BUILD_VARIANT marker is required"
                      % (", ".join(found) + " markers" if found else "no SCR_BUILD_VARIANT marker"))
    variant = found[0]
    # SeatEvidenceCore.BuildTupleOk: a tuple outside it is reported as three
    # empty strings, which no registry row can match.
    if not (version and _is_build_part(version, 16) and _is_build_part(variant, 16)
            and _is_build_part(commit, COMMIT_CHARS)):
        raise Refused("the client would report an empty build tuple for this DLL "
                      "(version %r, commit %r)" % (version, commit))
    return {"version": version, "variant": variant, "commit": commit,
            "dll_sha256": hashlib.sha256(data).hexdigest(), "guid": guid,
            "plugin_name": plugin_name, "informational": informational[0] if len(informational) == 1 else None,
            "plugin_type": md.type_name(ptable, prow) if ptable == _TYPEDEF else None}


# ---------------------------------------------------------------------------
# The game files: the client's list, its paths and its survey.
# ---------------------------------------------------------------------------

def managed_dir(root):
    """BepInEx Paths.ManagedPath: <root>/<process name>_Data/Managed, the
    process being the game's executable (ROUNDS.exe -> ROUNDS_Data)."""
    try:
        names = os.listdir(root)
    except OSError as e:
        raise Refused("the game root %s cannot be listed (%s)" % (root, e.__class__.__name__))
    games = sorted(n[:-4] for n in names
                   if n.lower().endswith(".exe") and os.path.isdir(os.path.join(root, n[:-4] + "_Data")))
    if len(games) != 1:
        raise Refused("the game root %s holds %d executables with a <name>_Data folder, not exactly one"
                      % (root, len(games)))
    return os.path.join(root, games[0] + "_Data", "Managed")


def game_targets(root):
    """[(file id, file name, path)] in IdentityClockEvidence.FileList order."""
    managed, core = managed_dir(root), os.path.join(root, "BepInEx", "core")
    out = [(i, f, os.path.join(managed, f)) for i, f in enumerate(GAME_FILES)]
    out += [(len(GAME_FILES) + i, f, os.path.join(core, f)) for i, f in enumerate(LOADER_FILES)]
    out.append((len(GAME_FILES) + len(LOADER_FILES), DOORSTOP_FILE, os.path.join(root, DOORSTOP_FILE)))
    return out


def listed_name(file_id):
    names = GAME_FILES + LOADER_FILES + (DOORSTOP_FILE,)
    return names[file_id] if 0 <= file_id < len(names) else None


def _open(path):
    """IdentityClockCore.DiskFs.Open: a stream, or None and the state the
    client reports (not found is no_file; a directory, a reparse point or any
    other failure is read_failed)."""
    if not path:
        return None, NO_FILE
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None, NO_FILE
    except OSError:
        return None, READ_FAILED
    if (stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode)
            or getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT):
        return None, READ_FAILED
    try:
        return open(path, "rb"), OK
    except FileNotFoundError:
        return None, NO_FILE
    except OSError:
        return None, READ_FAILED


def survey(targets):
    """Each target's state, digest and size as the client's survey reports it
    (IdentityClockCore.Survey phase 0): one unit opens a file, one unit reads
    one chunk, one unit finishes it; the job stops once the units or the bytes
    reach their cap, and a file read past FILE_BYTES_MAX is read_failed.
    Targets are taken in file id order; given a subset of the list, the caps
    count that subset only."""
    units = total = 0
    stopped = False
    out = []
    for file_id, name, path in targets[:GDIG_MAX]:
        entry = {"file_id": file_id, "name": name, "path": path, "state": NOT_YET, "sha256": "", "size": 0}
        out.append(entry)
        if stopped or units >= JOB_UNITS_MAX or total >= JOB_BYTES_MAX:
            stopped = True
            continue
        units += 1
        stream, state = _open(path)
        if stream is None:
            entry["state"] = state
            continue
        digest, size = hashlib.sha256(), 0
        with stream:
            while True:
                if units >= JOB_UNITS_MAX or total >= JOB_BYTES_MAX:
                    stopped = True
                    break
                units += 1
                chunk = stream.read(CHUNK_BYTES)
                if chunk:
                    digest.update(chunk)
                    size += len(chunk)
                    total += len(chunk)
                    if size > FILE_BYTES_MAX:
                        entry["state"] = READ_FAILED
                        break
                    continue
                entry.update(state=OK, sha256=digest.hexdigest(), size=size)
                break
    return out


def steam_label(root):
    """steam.<buildid> from the Steam app manifest of the install, which sits
    at <library>/steamapps/appmanifest_1557740.acf for an install at
    <library>/steamapps/common/<installdir>."""
    root = os.path.abspath(root)
    path = os.path.join(os.path.dirname(os.path.dirname(root)), "appmanifest_%s.acf" % STEAM_APP_ID)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        raise Refused("no Steam app manifest at %s; name the label with --game-version" % path)
    installdir = re.search(r'"installdir"\s+"([^"]*)"', text)
    buildid = re.search(r'"buildid"\s+"([0-9]{1,10})"', text)
    if not installdir or installdir.group(1).lower() != os.path.basename(root).lower():
        raise Refused("the Steam app manifest at %s does not describe %s; name the label with "
                      "--game-version" % (path, root))
    if not buildid:
        raise Refused("the Steam app manifest at %s carries no build id; name the label with "
                      "--game-version" % path)
    return "steam." + buildid.group(1)


# ---------------------------------------------------------------------------
# Rows, signing, the two write paths.
# ---------------------------------------------------------------------------

def signed_target(row):
    """The target main's handlers sign: version|variant|commit|dll_sha256,
    plus |source only when it is not the default; file_id|game_version|sha256."""
    if row["kind"] == "release":
        target = "%s|%s|%s|%s" % (row["version"], row["variant"], row["commit"], row["dll_sha256"])
        return target if row["source"] == "release" else target + "|" + row["source"]
    return "%d|%s|%s" % (row["file_id"], row["game_version"], row["sha256"])


def admin_canonical(admin, row):
    """main._admin_canonical."""
    action = "release_digest" if row["kind"] == "release" else "game_file_digest"
    return "admin:%s:%s:%s" % (admin, action, signed_target(row))


def request_url(base, admin, secret, row):
    signature = hmac.new(secret.encode(), admin_canonical(admin, row).encode(), hashlib.sha256).hexdigest()
    params = [("admin_steam_id", admin), ("hmac_signature", signature)]
    if row["kind"] == "release":
        params += [("version", row["version"]), ("variant", row["variant"]), ("commit", row["commit"]),
                   ("dll_sha256", row["dll_sha256"])]
        if row["source"] != "release":
            params.append(("source", row["source"]))
        path = RELEASE_ROUTE
    else:
        params += [("file_id", str(row["file_id"])), ("game_version", row["game_version"]),
                   ("sha256", row["sha256"])]
        path = GAME_FILE_ROUTE
    return base.rstrip("/") + path + "?" + urllib.parse.urlencode(params)


def urllib_post(url, headers, timeout=30, body=b""):
    """POST with `body` (empty for the digest routes): (status, body text)."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _row_text(row):
    if row["kind"] == "release":
        return "release   version=%s variant=%s commit=%s dll_sha256=%s source=%s" % (
            row["version"], row["variant"], row["commit"], row["dll_sha256"], row["source"])
    return "game_file id=%-2d game_version=%s sha256=%s  %s (%d bytes)" % (
        row["file_id"], row["game_version"], row["sha256"], row["name"], row["size"])


def _sql_text(value):
    """A literal for a value already held to [A-Za-z0-9._+-] or hex."""
    if not BUILD_PART.fullmatch(value):
        raise Refused("a value outside the registry's character set reached the SQL writer")
    return "'%s'" % value


_MIGRATION_NAME = re.compile(r"[A-Za-z0-9_]{1,80}\.sql")


def _sql_target(path):
    """argparse type for --emit-sql. The base name goes verbatim into the file's header comment and its
    RAISE literals, so it is restricted to letters, digits and underscores plus the .sql suffix: a
    quote in the name was an SQL injection and a percent sign a broken RAISE placeholder (DIGESTS-R2
    H1). Refused before the DLL is read or anything is written."""
    base = os.path.basename(path)
    if not _MIGRATION_NAME.fullmatch(base):
        raise argparse.ArgumentTypeError("the migration file name may use letters, digits and underscores "
                                         "and must end in .sql: %r" % base)
    return path


def migration_text(name, rows):
    """The identical inserts as a data-only migration of the house shape."""
    if not _MIGRATION_NAME.fullmatch(name):
        raise ValueError("migration name %r cannot be embedded in the migration text" % name)
    rel = [r for r in rows if r["kind"] == "release"]
    games = [r for r in rows if r["kind"] == "game_file"]
    what = []
    if rel:
        what.append("v%s %s commit %s" % (rel[0]["version"], rel[0]["variant"], rel[0]["commit"]))
    if games:
        what.append("%d game-file digests under %s" % (len(games), games[0]["game_version"]))
    lines = [
        "-- %s: digest registry rows: %s." % (name, "; ".join(what)),
        "--",
        "-- Generated by tools/register_release_digests.py from the release DLL and the",
        "-- game install; re-generate rather than edit. POST /api/v1/admin/release-digests",
        "-- and POST /api/v1/admin/game-file-digests insert these rows ON CONFLICT DO",
        "-- NOTHING; this file performs the identical inserts through the migration",
        "-- channel (learnings #421, #443). Data only: requires 368 (mod_release_digests)",
        "-- and 372 (game_file_digests) and writes no other table. A re-run inserts",
        "-- nothing (INSERT 0 0). Explicit BEGIN/COMMIT (#340).",
        "BEGIN;",
    ]
    for r in rel:
        lines += ["", "INSERT INTO mod_release_digests (version, variant, commit_sha, dll_sha256, source) VALUES",
                  "    (%s, %s, %s, %s, %s)" % (_sql_text(r["version"]), _sql_text(r["variant"]),
                                                _sql_text(r["commit"]), _sql_text(r["dll_sha256"]),
                                                _sql_text(r["source"])),
                  "ON CONFLICT DO NOTHING;"]
    if games:
        lines += ["", "INSERT INTO game_file_digests (file_id, game_version, sha256) VALUES"]
        for i, r in enumerate(games):
            lines.append("    (%d, %s, %s)%s  -- %s" % (r["file_id"], _sql_text(r["game_version"]),
                                                       _sql_text(r["sha256"]),
                                                       "," if i + 1 < len(games) else "", r["name"]))
        lines.append("ON CONFLICT DO NOTHING;")
    # The post-check in 376's form: every row above must now be present as the exact tuple.
    # Both primary keys are the whole tuple (368:110, 372:108), so ON CONFLICT DO NOTHING
    # skips only an identical row and the count after the inserts must be complete: the
    # NOTICE is the operator's acceptance line; the raise is a guard that should never fire
    # (a tuple absent after its own insert means the inserts did not run here).
    lines += ["", "DO $$", "DECLARE", "  rel_missing integer := 0;", "  game_missing integer := 0;", "BEGIN"]
    if rel:
        lines += ["  SELECT count(*) INTO rel_missing FROM (VALUES %s)" % ", ".join(
                      "(%s, %s, %s, %s)" % (_sql_text(r["version"]), _sql_text(r["variant"]),
                                            _sql_text(r["commit"]), _sql_text(r["dll_sha256"])) for r in rel),
                  "    AS want(version, variant, commit_sha, dll_sha256)",
                  "   WHERE NOT EXISTS (SELECT 1 FROM mod_release_digests r WHERE r.version = want.version",
                  "                     AND r.variant = want.variant AND r.commit_sha = want.commit_sha",
                  "                     AND r.dll_sha256 = want.dll_sha256);"]
    if games:
        lines += ["  SELECT count(*) INTO game_missing FROM (VALUES %s)" % ", ".join(
                      "(%d, %s, %s)" % (r["file_id"], _sql_text(r["game_version"]), _sql_text(r["sha256"]))
                      for r in games),
                  "    AS want(file_id, game_version, sha256)",
                  "   WHERE NOT EXISTS (SELECT 1 FROM game_file_digests g WHERE g.file_id = want.file_id",
                  "                     AND g.game_version = want.game_version AND g.sha256 = want.sha256);"]
    lines += ["  IF rel_missing > 0 OR game_missing > 0 THEN",
              "    RAISE EXCEPTION 'migration %s: %% release row(s) and %% game-file row(s) did not land"
              " after their own inserts; nothing was committed', rel_missing, game_missing;" % name,
              "  END IF;",
              "  RAISE NOTICE 'migration %s: %d release row(s) and %d game-file row(s) present';"
              % (name, len(rel), len(games)),
              "END $$;", "", "COMMIT;", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# --census: one card pool census into card_pool_registry (migration 370).
# ---------------------------------------------------------------------------

CENSUS_ROUTE = "/api/v1/admin/card-pool-census"
CENSUS_ACTION = "card_census"
CENSUS_DIGEST_MAX = 64                  # main.admin_register_card_census: digest Query(..., max_length=64)
CENSUS_STATUSES = ("registered", "already_registered")
API_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", "api"))
_NAME_RESOLUTION = re.compile(r"search_path|set_config", re.I)


def _same_file(got, want):
    return bool(got) and os.path.normcase(os.path.abspath(got)) == os.path.normcase(os.path.abspath(want))


def server_census_check():
    """backend/api/card_measures.py of this checkout, the module whose
    census_from_dump card_evidence.register_census applies, and its import
    review_measures beside it. Raises Refused when either cannot be loaded or
    a module of that name from anywhere else is the one loaded."""
    want = os.path.join(API_DIR, "card_measures.py")
    if not os.path.isfile(want):
        raise Refused("the server's census check %s is not in this checkout" % want)
    if not any(_same_file(p, API_DIR) for p in sys.path if p):
        sys.path.append(API_DIR)
    try:
        cm = importlib.import_module("card_measures")
    except Exception as e:  # noqa: BLE001 - any failure to load is a refusal
        raise Refused("the server's census check cannot be loaded (%s)" % e.__class__.__name__)
    rm = getattr(cm, "rm", None)
    if not _same_file(getattr(cm, "__file__", None), want) or not _same_file(
            getattr(rm, "__file__", None), os.path.join(API_DIR, "review_measures.py")):
        raise Refused("the loaded census check is %s, not the server's %s"
                      % (getattr(cm, "__file__", None), want))
    return cm


def census_plan(path, expect_digest=None):
    """(the file's bytes, the one card_pool_registry row the census route would
    insert for them). Raises Refused for any file the route would answer with
    anything but a registration."""
    cm = server_census_check()
    try:
        with open(path, "rb") as f:
            body = f.read()
    except OSError as e:
        raise Refused("the census dump %s cannot be read (%s)" % (path, e.__class__.__name__))
    # main.admin_register_card_census after its admin check: the raw body through json.loads
    # (any failure: 400 "body"), then a dict whose "digest" equals the signed digest query value
    # (else 422 "digest"), that query value being a string of at most 64 characters (FastAPI 422).
    # This step signs and sends the file's own "digest", so the two agree exactly when it is such
    # a string. The same json.loads is used here, over the same bytes.
    try:
        doc = json.loads(body)
    except Exception:  # noqa: BLE001 - the route catches everything here too
        raise Refused("the census dump is not JSON the route reads (the route would answer 400 body)")
    if not isinstance(doc, dict):
        raise Refused("the census dump is not a JSON object (the route would answer 422 digest)")
    digest = doc.get("digest")
    if not isinstance(digest, str):
        raise Refused("the census dump states no digest string to sign (the route would answer 422 digest)")
    if len(digest) > CENSUS_DIGEST_MAX:
        raise Refused("the census dump's digest is longer than the route's %d-character query cap "
                      "(the route would answer 422)" % CENSUS_DIGEST_MAX)
    # card_evidence.register_census: census_from_dump, any Refusal answered 422 <field>; any other
    # exception is a 500, which registers nothing either.
    try:
        c = cm.census_from_dump(doc)
    except cm.Refusal as r:
        raise Refused("the server's census check refuses the dump: %s (the route would answer 422 %s)"
                      % (r.field, r.field))
    except Exception as e:  # noqa: BLE001
        raise Refused("the server's census check fails on the dump with %s (the route would answer 500)"
                      % e.__class__.__name__)
    if expect_digest is not None and c.digest != expect_digest:
        raise Refused("the dump's census digest is %s, not --expect-digest %s" % (c.digest, expect_digest))
    # register_census's insert: (digest, CAST(dumps(doc) AS jsonb), count, slots, game sha).
    # census_from_dump has held the digest and the game sha to 64 lowercase hex; the SQL writer
    # re-checks every value it embeds.
    row = {"digest": c.digest, "census": cm.dumps(doc), "card_count": c.count, "slot_count": c.slots,
           "game_dll_sha256": c.game_sha}
    return body, row


def _census_row_text(row):
    return "census    digest=%s cards=%d slots=%d game_dll_sha256=%s" % (
        row["digest"], row["card_count"], row["slot_count"], row["game_dll_sha256"])


def _sql_int(v):
    if not isinstance(v, int) or isinstance(v, bool):
        raise Refused("a non-integer count reached the SQL writer")
    return "%d" % v


def census_migration_text(name, row):
    """The one insert register_census performs, as a data-only migration of the house shape."""
    if not _MIGRATION_NAME.fullmatch(name):
        raise ValueError("migration name %r cannot be embedded in the migration text" % name)
    d, g = row["digest"], row["game_dll_sha256"]
    if not (HEX64.fullmatch(d) and HEX64.fullmatch(g)):
        raise Refused("a value outside the registry's character set reached the SQL writer")
    census = row["census"]
    if not census.isascii() or any(ord(ch) < 32 or ord(ch) == 127 for ch in census):
        raise Refused("the census text holds a byte the SQL writer does not embed")
    if _NAME_RESOLUTION.search(census):
        raise Refused("the census names search_path or set_config, which the data-only landing refuses "
                      "wherever it appears; register it through the api instead")
    n, s = _sql_int(row["card_count"]), _sql_int(row["slot_count"])
    lines = [
        "-- %s: card pool census registry row: digest %s, %s cards, %s slots, game dll %s." % (name, d, n, s, g),
        "--",
        "-- Generated by tools/register_release_digests.py --census from the census dump a",
        "-- reference seat wrote (CompetitiveRounds.card-census.json); re-generate rather than",
        "-- edit. POST /api/v1/admin/card-pool-census inserts this row ON CONFLICT (digest) DO",
        "-- NOTHING (card_evidence.register_census); this file performs the identical insert",
        "-- through the migration channel (learnings #421, #443). Data only: requires 370",
        "-- (card_pool_registry) and writes no other table. A re-run inserts nothing",
        "-- (INSERT 0 0). Explicit BEGIN/COMMIT (#340).",
        "BEGIN;",
        "",
        "INSERT INTO card_pool_registry (digest, census, card_count, slot_count, game_dll_sha256) VALUES",
        "    ('%s', CAST('%s' AS jsonb), %s, %s, '%s')" % (d, census.replace("'", "''"), n, s, g),
        "ON CONFLICT (digest) DO NOTHING;",
        "",
        # The post-check: the digest is the primary key (370:88), so ON CONFLICT DO NOTHING keeps a row
        # registered earlier from another dump of the same pool. The census text is fixed by the digest;
        # the rest of the stored dump is the card count, the slot count and the game build, compared here.
        # A row absent, or held for another game build, raises and nothing commits: records on this
        # build match a census only when its game build is theirs (card_measures.RecFacts).
        "DO $$",
        "DECLARE",
        "  missing integer := 0;",
        "BEGIN",
        "  SELECT count(*) INTO missing FROM (VALUES ('%s', %s, %s, '%s'))" % (d, n, s, g),
        "    AS want(digest, card_count, slot_count, game_dll_sha256)",
        "   WHERE NOT EXISTS (SELECT 1 FROM card_pool_registry p WHERE p.digest = want.digest",
        "                     AND p.card_count = want.card_count AND p.slot_count = want.slot_count",
        "                     AND p.game_dll_sha256 = want.game_dll_sha256);",
        "  IF missing > 0 THEN",
        "    RAISE EXCEPTION 'migration %s: the registry row for census %s is absent or holds another card count, "
        "slot count or game build; nothing was committed';" % (name, d),
        "  END IF;",
        "  RAISE NOTICE 'migration %s: census %s present (%s cards, %s slots)';" % (name, d, n, s),
        "END $$;",
        "",
        "COMMIT;",
        "",
    ]
    return "\n".join(lines)


def census_url(base, admin, secret, digest):
    canonical = "admin:%s:%s:%s" % (admin, CENSUS_ACTION, digest)         # main._admin_canonical
    signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    params = [("admin_steam_id", admin), ("hmac_signature", signature), ("digest", digest)]
    return base.rstrip("/") + CENSUS_ROUTE + "?" + urllib.parse.urlencode(params)


def _census_parser():
    ap = argparse.ArgumentParser(description="Register one card pool census (the dump file a reference seat "
                                             "wrote) in card_pool_registry.")
    ap.add_argument("--census", required=True, metavar="FILE",
                    help="the census dump, CompetitiveRounds.card-census.json from the seat's BepInEx/config")
    ap.add_argument("--expect-digest", help="refuse unless the dump's census digest is this 64-hex value")
    ap.add_argument("--admin", help="an admin_users steam id (the real api run)")
    ap.add_argument("--mod-version", help="the X-Mod-Version header of the api run")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print what would be registered; send nothing")
    mode.add_argument("--emit-sql", metavar="FILE", type=_sql_target,
                      help="write the insert as a data-only migration instead of calling the api")
    return ap


def census_main(argv, environ=None, transport=None):
    args = _census_parser().parse_args(argv)
    env = os.environ if environ is None else environ
    post = urllib_post if transport is None else transport
    if args.expect_digest is not None and not HEX64.fullmatch(args.expect_digest):
        print("REFUSED: --expect-digest %r is not 64 lowercase hex. Nothing registered." % (args.expect_digest,))
        return EXIT_REFUSED
    try:
        body, row = census_plan(args.census, args.expect_digest)
    except Refused as r:
        print("REFUSED: %s. Nothing registered." % r)
        return EXIT_REFUSED
    print("CENSUS   %s (%d bytes)" % (os.path.abspath(args.census), len(body)))
    print("  check  card_measures.census_from_dump, the server's own, from %s" % API_DIR)
    print("  row    " + _census_row_text(row))

    if args.emit_sql:
        path = args.emit_sql
        if os.path.exists(path):
            print("REFUSED: %s exists; the writer never replaces a file. Nothing written." % path)
            return EXIT_REFUSED
        try:
            text = census_migration_text(os.path.basename(path), row)
        except Refused as r:
            print("REFUSED: %s. Nothing written." % r)
            return EXIT_REFUSED
        print("SQL      " + _census_row_text(row))
        with open(path, "w", encoding="ascii", newline="\n") as f:
            f.write(text)
        print("WROTE    %s: 1 row, data only; apply it as a migration (a re-run inserts nothing)." % path)
        return EXIT_OK

    secret = env.get("ADMIN_HMAC_SECRET", "")
    base = env.get("SCR_API_BASE", "")
    missing = []
    print("ENV      ADMIN_HMAC_SECRET is %s" % ("set (value not printed)" if secret else "NOT SET"))
    if not secret:
        missing.append("ADMIN_HMAC_SECRET")
    if base:
        print("ENV      API base %s" % base)
    else:
        print("ENV      SCR_API_BASE is NOT SET")
        missing.append("SCR_API_BASE")
    if not args.admin:
        print("ARG      --admin is not given")
        missing.append("--admin")
    elif not re.fullmatch(r"[0-9]{17}", args.admin):
        print("REFUSED: --admin %r is not a 17-digit steam id. Nothing registered." % (args.admin,))
        return EXIT_REFUSED
    if args.mod_version is None:
        print("ARG      --mod-version is not given")
        missing.append("--mod-version")
    elif not (args.mod_version and _is_build_part(args.mod_version, 16)):
        print("REFUSED: --mod-version %r is not a mod version. Nothing registered." % (args.mod_version,))
        return EXIT_REFUSED

    if args.dry_run:
        print("WOULD    " + _census_row_text(row))
        print("         signs target %s (action %s), body the %d bytes of the file" % (row["digest"], CENSUS_ACTION,
                                                                                     len(body)))
        print("DRY RUN  1 row would be registered; nothing was sent.%s"
              % (" The real run also needs: " + ", ".join(missing) + "." if missing else ""))
        return EXIT_OK
    if missing:
        print("NOT SENT %s missing; nothing was sent." % ", ".join(missing))
        return EXIT_ENV

    headers = {"X-Mod-Version": args.mod_version, "Accept": "application/json",
               "Content-Type": "application/json"}
    url = census_url(base, args.admin, secret, row["digest"])
    try:
        status, text = post(url, headers, body=body)
    except Exception as e:  # noqa: BLE001 - reported, the run stops
        print("FAILED   %s: %s. Nothing is known to be registered; a re-run is safe."
              % (_census_row_text(row), e.__class__.__name__))
        return EXIT_SERVER
    answer = None
    if status == 200:
        try:
            answer = json.loads(text)
        except ValueError:
            answer = None
    want = {"digest": row["digest"], "card_count": row["card_count"], "slot_count": row["slot_count"]}
    if not (isinstance(answer, dict) and answer.get("status") in CENSUS_STATUSES
            and set(answer) == {"status"} | set(want) and all(answer[k] == v for k, v in want.items())):
        print("FAILED   %s: HTTP %s %s. A re-run is safe." % (_census_row_text(row), status, text[:200]))
        return EXIT_SERVER
    if answer["status"] == "registered":
        print("INSERTED " + _census_row_text(row))
        print("DONE     1 row: 1 inserted.")
    else:
        print("HELD     " + _census_row_text(row) + " (already registered)")
        print("DONE     1 row: nothing inserted; the registry already holds this digest. It keeps the first row "
              "registered for a digest, so read its game_dll_sha256 back to confirm it is this game build.")
    return EXIT_OK


# ---------------------------------------------------------------------------
# The step.
# ---------------------------------------------------------------------------

def _parser():
    ap = argparse.ArgumentParser(description="Register one release's build tuple and the game-file "
                                             "digests in the evidence registries.")
    ap.add_argument("--dll", required=True, help="the release DLL (the bytes of the uploaded asset)")
    ap.add_argument("--version", required=True, help="the release's mod version; must equal the DLL's own")
    ap.add_argument("--variant", choices=[w for _m, w in VARIANT_MARKERS],
                    help="refuse unless the DLL is this variant")
    ap.add_argument("--commit", help="refuse unless the DLL's embedded commit starts with this sha")
    ap.add_argument("--source", choices=SOURCES, default="release",
                    help="release (the default) or beta, a tester build the maintainer names")
    games = ap.add_mutually_exclusive_group(required=True)
    games.add_argument("--game-root", help="the ROUNDS install whose files the client hashes")
    games.add_argument("--game-file", action="append", metavar="ID=PATH",
                       help="one listed file by its client file id (repeat for each)")
    games.add_argument("--skip-game-files", action="store_true", help="register the release row only")
    ap.add_argument("--game-version", help="the game-file rows' label (default steam.<buildid> of the "
                                           "install's Steam app manifest)")
    ap.add_argument("--admin", help="an admin_users steam id (the real api run)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print what would be registered; send nothing")
    mode.add_argument("--emit-sql", metavar="FILE", type=_sql_target,
                      help="write the inserts as a data-only migration instead of calling the api")
    return ap


def plan(args):
    """Every row the step would register; raises Refused."""
    if not (args.version and _is_build_part(args.version, 16)):
        raise Refused("--version %r is not a version the registry accepts" % (args.version,))
    if args.commit is not None and not re.fullmatch(r"[0-9a-fA-F]{7,40}", args.commit):
        raise Refused("--commit %r is not a 7 to 40 character hex sha" % (args.commit,))
    try:
        with open(args.dll, "rb") as f:
            data = f.read()
    except OSError as e:
        raise Refused("the DLL %s cannot be read (%s)" % (args.dll, e.__class__.__name__))
    ident = build_identity(data)
    if ident["version"] != args.version:
        raise Refused("the DLL's embedded version is %s, not %s" % (ident["version"], args.version))
    if args.variant and ident["variant"] != args.variant:
        raise Refused("the DLL is the %s variant, not %s" % (ident["variant"], args.variant))
    if args.commit is not None:
        want, have = args.commit.lower(), ident["commit"]
        n = min(len(want), len(have))
        if have == NO_COMMIT or n < 7 or want[:n] != have[:n]:
            raise Refused("the DLL's embedded commit is %s, which is not %s" % (have, args.commit))
    rows = [{"kind": "release", "version": ident["version"], "variant": ident["variant"],
             "commit": ident["commit"], "dll_sha256": ident["dll_sha256"], "source": args.source}]
    targets = []
    if args.game_root:
        targets = game_targets(args.game_root)
    elif args.game_file:
        seen = set()
        for item in args.game_file:
            fid, sep, path = item.partition("=")
            if not sep or not fid.isdigit() or listed_name(int(fid)) is None:
                raise Refused("--game-file %r is not ID=PATH with a listed file id (0 to %d)"
                              % (item, len(GAME_FILES) + len(LOADER_FILES)))
            fid = int(fid)
            if fid in seen:
                raise Refused("--game-file names file id %d twice" % fid)
            if os.path.basename(path).lower() != listed_name(fid).lower():
                raise Refused("--game-file %d is %s in the client's list, not %s"
                              % (fid, listed_name(fid), os.path.basename(path)))
            seen.add(fid)
            targets.append((fid, listed_name(fid), path))
        targets.sort()
    if targets:
        label = args.game_version
        if label is None:
            if not args.game_root:
                raise Refused("--game-file needs --game-version (there is no install to read a label from)")
            label = steam_label(args.game_root)
        if not (label and _is_build_part(label, 16)):
            raise Refused("the game version label %r is not one the registry accepts" % (label,))
        read = survey(targets)
        bad = [e for e in read if e["state"] != OK]
        if bad:
            raise Refused("the client would report no digest for %s"
                          % ", ".join("%d %s (%s)" % (e["file_id"], e["name"], e["state"]) for e in bad))
        rows += [{"kind": "game_file", "file_id": e["file_id"], "game_version": label,
                  "sha256": e["sha256"], "name": e["name"], "size": e["size"]} for e in read]
    for r in rows:
        values = ([r["version"], r["variant"], r["commit"], r["source"]] if r["kind"] == "release"
                  else [r["game_version"]])
        digest = r["dll_sha256"] if r["kind"] == "release" else r["sha256"]
        if not HEX64.fullmatch(digest) or not all(BUILD_PART.fullmatch(v) for v in values):
            raise Refused("a computed row is outside the registry's rules")
    return ident, rows


def main(argv=None, environ=None, transport=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if any(a == "--census" or a.startswith("--census=") for a in argv):
        return census_main(argv, environ, transport)
    args = _parser().parse_args(argv)
    env = os.environ if environ is None else environ
    post = urllib_post if transport is None else transport
    try:
        ident, rows = plan(args)
    except Refused as r:
        print("REFUSED: %s. Nothing registered." % r)
        return EXIT_REFUSED

    print("DLL      %s" % os.path.abspath(args.dll))
    print("  build  version %s, variant %s, commit %s (BepInPlugin %s, InformationalVersion %s)"
          % (ident["version"], ident["variant"], ident["commit"], ident["guid"], ident["informational"]))
    print("  sha256 %s" % ident["dll_sha256"])
    games = [r for r in rows if r["kind"] == "game_file"]
    if games:
        print("GAME     %s files under %s, label %s"
              % (len(games), os.path.abspath(args.game_root) if args.game_root else "the listed paths",
                 games[0]["game_version"]))
    else:
        print("GAME     no game-file rows (--skip-game-files)")

    if args.emit_sql:
        path = args.emit_sql
        if not path.endswith(".sql"):
            print("REFUSED: --emit-sql %s does not name a .sql file. Nothing written." % path)
            return EXIT_REFUSED
        if os.path.exists(path):
            print("REFUSED: %s exists; the writer never replaces a file. Nothing written." % path)
            return EXIT_REFUSED
        for r in rows:
            print("SQL      " + _row_text(r))
        with open(path, "w", encoding="ascii", newline="\n") as f:
            f.write(migration_text(os.path.basename(path), rows))
        print("WROTE    %s: %d rows, data only; apply it as a migration (a re-run inserts nothing)."
              % (path, len(rows)))
        return EXIT_OK

    secret = env.get("ADMIN_HMAC_SECRET", "")
    base = env.get("SCR_API_BASE", "")
    missing = []
    print("ENV      ADMIN_HMAC_SECRET is %s" % ("set (value not printed)" if secret else "NOT SET"))
    if not secret:
        missing.append("ADMIN_HMAC_SECRET")
    if base:
        print("ENV      API base %s" % base)
    else:
        print("ENV      SCR_API_BASE is NOT SET")
        missing.append("SCR_API_BASE")
    if not args.admin:
        print("ARG      --admin is not given")
        missing.append("--admin")
    elif not re.fullmatch(r"[0-9]{17}", args.admin):
        print("REFUSED: --admin %r is not a 17-digit steam id. Nothing registered." % (args.admin,))
        return EXIT_REFUSED

    if args.dry_run:
        for r in rows:
            print("WOULD    " + _row_text(r))
            print("         signs target " + signed_target(r))
        print("DRY RUN  %d rows would be registered; nothing was sent.%s"
              % (len(rows), " The real run also needs: " + ", ".join(missing) + "." if missing else ""))
        return EXIT_OK
    if missing:
        print("NOT SENT %s missing; nothing was sent." % ", ".join(missing))
        return EXIT_ENV

    headers = {"X-Mod-Version": ident["version"], "Accept": "application/json"}
    inserted = already = 0
    for r in rows:
        url = request_url(base, args.admin, secret, r)
        try:
            status, body = post(url, headers)
        except Exception as e:  # noqa: BLE001 - reported, the run stops
            print("FAILED   %s: %s. Stopped; rows before it stand, a re-run is safe."
                  % (_row_text(r), e.__class__.__name__))
            return EXIT_SERVER
        word = None
        if status == 200:
            m = re.fullmatch(r'\s*\{\s*"status"\s*:\s*"(registered|already_registered)"\s*\}\s*', body)
            word = m.group(1) if m else None
        if word is None:
            print("FAILED   %s: HTTP %s %s. Stopped; rows before it stand, a re-run is safe."
                  % (_row_text(r), status, body[:200]))
            return EXIT_SERVER
        if word == "registered":
            inserted += 1
            print("INSERTED " + _row_text(r))
        else:
            already += 1
            print("HELD     " + _row_text(r) + " (already registered)")
    if inserted:
        print("DONE     %d rows: %d inserted, %d already registered." % (len(rows), inserted, already))
    else:
        print("DONE     %d rows: nothing inserted, every row was already registered." % len(rows))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
