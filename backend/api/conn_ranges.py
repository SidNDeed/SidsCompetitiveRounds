"""Connection class of the api path at an evidence post (B8), from an OFFLINE
range list held on the server.

What this module does, and what it never does:

  * It loads one immutable range-list revision from the mounted ranges root
    (`ranges-<rev12>/` holding exactly `ranges.txt`, `sources.txt`,
    `selftest.txt` and `REVISION`, selected by the root's `current` pointer),
    off the request path, inside explicit resource bounds, and publishes the
    compiled result in one assignment.
  * It classifies one client address, in process memory, into a closed public
    class set. The address is held only in the caller's and this module's
    local variables. Nothing here writes, logs, prints, stores or sends an
    address, and nothing here makes any network request: the list is data
    that was staged on disk.
  * The class is a NOTE for a reviewer. Nothing reads it to refuse, rate,
    rank or display anything.

Revision format (public):
  ranges.txt    `[<class>]` section headers from RANGE_CLASSES, then one CIDR
                per line (strict: no host bits set). Blank lines and lines
                starting with `#` are ignored. Any other line refuses the
                revision.
  sources.txt   one line per source: `<name>\\t<YYYY-MM-DD>\\t<sha256 hex>`
                (the date fetched and the digest of what was fetched). No
                address of any player.
  selftest.txt  one line per case: `<address>\\t<class>`. Every address is a
                documentation address (IPv4 TEST-NET-1/2/3, IPv6 2001:db8::/32),
                so the file can never carry a player address; at least one
                case must expect `none`.
  REVISION      the framed digest (64 hex) of the other three files; the
                directory is named `ranges-` + its first 12 hex.

Loader outcome (the health word `conn_ranges`): the rev12 when loaded,
`absent` when nothing is staged (`current` missing or naming `ranges-none`),
`refused` when the staged revision fails any check. The refusal class is
printed once per change as `[RANGES] refused (<class>)`; it never reaches the
health word. While absent or refused every address classifies `unknown`.

Bounds (CR_BOUNDS) are checked BEFORE parsing where they can be (inventory,
bytes) and during parsing for the rest (lines, entries, intervals after the
merge, sources, self-test cases, wall time). A revision over any bound is
refused. Same-class overlaps merge into disjoint intervals; any address
covered by two different classes refuses the revision.
"""

from __future__ import annotations

import bisect
import hashlib
import ipaddress
import os
import re
import stat
import threading
import time

import review_rules as _cr_rr

CR_BOUNDS = {
    "ranges_bytes_max": 8388608,
    "sources_bytes_max": 65536,
    "selftest_bytes_max": 65536,
    "revision_bytes_max": 65,
    "lines_max": 400000,
    "entries_max": 300000,
    "intervals_max": 300000,
    "sources_max": 256,
    "cases_max": 256,
    "deadline_s": 20,
    "rev_hex": 12,
    "pointer_bytes_max": 64,
    "frame_bytes": 8,
    "line_bytes_max": 128,
}

# The closed public class set a row may carry. `lan` comes from the fixed
# private-use ranges below; `none` is a loaded list that names nothing for the
# address; `unknown` is no loaded list, an unparsable address, or a fault.
CONN_CLASSES = ("none", "lan", "hosting", "vpn", "relay", "tor", "unknown")
RANGE_CLASSES = ("hosting", "vpn", "relay", "tor")

CR_ROOT_ENV = "SCR_RANGES_ROOT"
CR_DEFAULT_ROOT = "/app/private/ranges"
CR_POINTER = "current"
CR_NONE_TARGET = "ranges-none"
CR_FILES = ("REVISION", "ranges.txt", "selftest.txt", "sources.txt")
CR_DOMAIN = b"scr-conn-ranges-revision\n"

# Private-use and local ranges (public facts of the address plan). Checked
# only while a list is loaded (an absent list classifies everything unknown).
CR_LAN_NETS = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16",
    "100.64.0.0/10", "::1/128", "fc00::/7", "fe80::/10"))
# Documentation ranges: the only addresses a self-test case may name.
CR_DOC_NETS = tuple(ipaddress.ip_network(n) for n in (
    "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32"))

_CR_REV_DIR = re.compile(r"ranges-[0-9a-f]{%d}" % CR_BOUNDS["rev_hex"])
_CR_SECTION = re.compile(r"\[([a-z]{1,16})\]")
_CR_SOURCE = re.compile(r"[A-Za-z0-9_.\-]{1,64}\t\d{4}-\d{2}-\d{2}\t[0-9a-f]{64}")
_CR_HEX64 = re.compile(r"[0-9a-f]{64}")


class RangesRefused(Exception):
    """A revision this loader will not use; `cls` is the reason class."""

    def __init__(self, cls: str):
        super().__init__(cls)
        self.cls = cls


def ranges_digest(files: dict) -> str:
    """sha256 over a framed manifest of the three data files: a domain tag, the
    count, then per file (name-sorted) the name length, the name, the content
    length and the content, lengths fixed-width."""
    w = CR_BOUNDS["frame_bytes"]
    h = hashlib.sha256()
    h.update(CR_DOMAIN)
    h.update(len(files).to_bytes(w, "big"))
    for name in sorted(files):
        n = name.encode("ascii")
        c = files[name]
        h.update(len(n).to_bytes(w, "big"))
        h.update(n)
        h.update(len(c).to_bytes(w, "big"))
        h.update(c)
    return h.hexdigest()


def _cr_check_time(deadline):
    if time.monotonic() > deadline:
        raise RangesRefused("deadline")


def _cr_caps():
    return {"REVISION": CR_BOUNDS["revision_bytes_max"],
            "ranges.txt": CR_BOUNDS["ranges_bytes_max"],
            "sources.txt": CR_BOUNDS["sources_bytes_max"],
            "selftest.txt": CR_BOUNDS["selftest_bytes_max"]}


def _cr_inventory(rdir: str, deadline: float) -> dict:
    """Exactly the four files, regular, no links, each under its byte cap,
    checked from lstat entry by entry before anything is read; then each read
    through the review loader's verified non-following handle."""
    try:
        st = os.lstat(rdir)
    except OSError:
        raise RangesRefused("unreadable")
    if stat.S_ISLNK(st.st_mode) or _cr_rr._reparse(st) or not stat.S_ISDIR(st.st_mode):
        raise RangesRefused("inventory")
    plan = []
    caps = _cr_caps()
    try:
        with os.scandir(rdir) as it:
            for ent in it:
                _cr_check_time(deadline)
                if ent.name not in caps or len(plan) >= len(CR_FILES):
                    raise RangesRefused("inventory")
                path = os.path.join(rdir, ent.name)
                s = os.lstat(path)
                if stat.S_ISLNK(s.st_mode) or _cr_rr._reparse(s) or not stat.S_ISREG(s.st_mode):
                    raise RangesRefused("inventory")
                if s.st_size > caps[ent.name]:
                    raise RangesRefused("bytes")
                plan.append((ent.name, path, s.st_size, (s.st_dev, s.st_ino)))
    except OSError:
        raise RangesRefused("unreadable")
    if sorted(p[0] for p in plan) != sorted(CR_FILES):
        raise RangesRefused("inventory")
    files = {}
    for name, path, size, ident in sorted(plan):
        _cr_check_time(deadline)
        try:
            files[name] = _cr_rr._read_verified(path, ident, size, caps[name])
        except _cr_rr.Refused:
            raise RangesRefused("unreadable")
    return files


def _cr_lines(raw: bytes, deadline: float):
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise RangesRefused("encoding")
    lines = text.split("\n")
    if len(lines) > CR_BOUNDS["lines_max"]:
        raise RangesRefused("lines")
    for i, ln in enumerate(lines):
        if not (i & 0x3FFF):
            _cr_check_time(deadline)
        if len(ln) > CR_BOUNDS["line_bytes_max"]:
            raise RangesRefused("line")
        yield ln.rstrip("\r")


def _cr_parse_ranges(raw: bytes, deadline: float) -> dict:
    """Per address family, the sorted disjoint intervals [(lo, hi, class)]."""
    per = {4: [], 6: []}
    section = None
    entries = 0
    for ln in _cr_lines(raw, deadline):
        if not ln.strip() or ln.startswith("#"):
            continue
        m = _CR_SECTION.fullmatch(ln)
        if m:
            if m.group(1) not in RANGE_CLASSES:
                raise RangesRefused("section")
            section = m.group(1)
            continue
        if section is None:
            raise RangesRefused("no_section")
        try:
            net = ipaddress.ip_network(ln, strict=True)
        except ValueError:
            raise RangesRefused("cidr")
        entries += 1
        if entries > CR_BOUNDS["entries_max"]:
            raise RangesRefused("entries")
        per[net.version].append((int(net.network_address), int(net.broadcast_address), section))
    out = {}
    total = 0
    for fam, ivs in per.items():
        _cr_check_time(deadline)
        ivs.sort()
        merged = []
        for lo, hi, cls in ivs:
            if merged and lo <= merged[-1][1] + 1:
                plo, phi, pcls = merged[-1]
                if lo <= phi and pcls != cls:
                    raise RangesRefused("overlap")
                if pcls == cls:
                    merged[-1] = (plo, max(phi, hi), cls)
                    continue
            merged.append((lo, hi, cls))
        total += len(merged)
        out[fam] = merged
    if total > CR_BOUNDS["intervals_max"]:
        raise RangesRefused("intervals")
    return out


def _cr_parse_sources(raw: bytes, deadline: float) -> int:
    n = 0
    for ln in _cr_lines(raw, deadline):
        if not ln.strip():
            continue
        if not _CR_SOURCE.fullmatch(ln):
            raise RangesRefused("sources")
        n += 1
        if n > CR_BOUNDS["sources_max"]:
            raise RangesRefused("sources")
    if n == 0:
        raise RangesRefused("sources")
    return n


def _cr_parse_selftest(raw: bytes, deadline: float) -> list:
    cases = []
    for ln in _cr_lines(raw, deadline):
        if not ln.strip():
            continue
        parts = ln.split("\t")
        if len(parts) != 2 or parts[1] not in CONN_CLASSES or parts[1] == "unknown":
            raise RangesRefused("selftest")
        try:
            addr = ipaddress.ip_address(parts[0])
        except ValueError:
            raise RangesRefused("selftest")
        if not any(addr in net for net in CR_DOC_NETS):
            raise RangesRefused("selftest_address")
        cases.append((addr, parts[1]))
        if len(cases) > CR_BOUNDS["cases_max"]:
            raise RangesRefused("selftest")
    if not any(c == "none" for _a, c in cases):
        raise RangesRefused("selftest")
    return cases


class RangeTable:
    """A compiled revision: per family, parallel sorted arrays for bisect."""

    __slots__ = ("rev", "starts", "ends", "classes", "intervals", "sources")

    def __init__(self, rev, intervals, sources):
        self.rev = rev
        self.intervals = sum(len(v) for v in intervals.values())
        self.sources = sources
        self.starts = {f: [iv[0] for iv in v] for f, v in intervals.items()}
        self.ends = {f: [iv[1] for iv in v] for f, v in intervals.items()}
        self.classes = {f: [iv[2] for iv in v] for f, v in intervals.items()}

    def lookup(self, addr) -> str:
        """The class an address falls in: `lan`, a listed class, or `none`."""
        if any(addr in net for net in CR_LAN_NETS if net.version == addr.version):
            return "lan"
        fam = addr.version
        x = int(addr)
        i = bisect.bisect_right(self.starts[fam], x) - 1
        if i >= 0 and x <= self.ends[fam][i]:
            return self.classes[fam][i]
        return "none"


def load_ranges_dir(rdir: str, *, deadline: float | None = None) -> RangeTable:
    """Validate and compile one revision directory completely, or raise
    RangesRefused(cls). Runs the revision's self-test before returning."""
    if deadline is None:
        deadline = time.monotonic() + CR_BOUNDS["deadline_s"]
    base = os.path.basename(os.path.normpath(rdir))
    if not _CR_REV_DIR.fullmatch(base):
        raise RangesRefused("name")
    files = _cr_inventory(rdir, deadline)
    data = {k: v for k, v in files.items() if k != "REVISION"}
    digest = ranges_digest(data)
    stated = files["REVISION"].decode("ascii", "replace").strip()
    if not _CR_HEX64.fullmatch(stated) or stated != digest \
            or base != "ranges-" + digest[: CR_BOUNDS["rev_hex"]]:
        raise RangesRefused("digest")
    intervals = _cr_parse_ranges(files["ranges.txt"], deadline)
    sources = _cr_parse_sources(files["sources.txt"], deadline)
    cases = _cr_parse_selftest(files["selftest.txt"], deadline)
    table = RangeTable(digest[: CR_BOUNDS["rev_hex"]], intervals, sources)
    for addr, want in cases:
        if table.lookup(addr) != want:
            raise RangesRefused("selftest_failed")
    _cr_check_time(deadline)
    return table


class RangesState:
    __slots__ = ("word", "table", "reason")

    def __init__(self, word, table=None, reason=None):
        self.word = word
        self.table = table
        self.reason = reason


_CR_STATE = RangesState("absent")
_CR_KEY = None
_CR_LOCK = threading.Lock()
_CR_LOGGED = None


def ranges_root() -> str:
    return os.environ.get(CR_ROOT_ENV) or CR_DEFAULT_ROOT


def _cr_pointer_target(base):
    p = os.path.join(base, CR_POINTER)
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(st.st_mode):
        target = os.readlink(p)
    elif (stat.S_ISREG(st.st_mode) and not _cr_rr._reparse(st)
          and st.st_size <= CR_BOUNDS["pointer_bytes_max"]):
        try:
            raw = _cr_rr._read_verified(p, (st.st_dev, st.st_ino), st.st_size,
                                        CR_BOUNDS["pointer_bytes_max"])
        except _cr_rr.Refused:
            raise RangesRefused("pointer")
        target = raw.decode("ascii", "replace").strip()
    else:
        raise RangesRefused("pointer")
    if target == CR_NONE_TARGET:
        return None
    if not _CR_REV_DIR.fullmatch(target):
        raise RangesRefused("pointer")
    return target


def _cr_log(state, key):
    """One line per CHANGE (outcome and reason class only; never an address)."""
    global _CR_LOGGED
    sig = (state.word, state.reason, key)
    if sig != _CR_LOGGED:
        _CR_LOGGED = sig
        if state.word == "refused":
            print("[RANGES] refused (%s)" % state.reason, flush=True)
        else:
            print("[RANGES] %s" % state.word, flush=True)


def refresh_ranges() -> RangesState:
    """Re-read the pointer; when it or its target changed, validate and compile
    the new target completely and publish the outcome in one assignment.
    Called only from the background refresh loop (off the request path); a
    load in progress elsewhere answers the state already published."""
    global _CR_STATE, _CR_KEY
    if not _CR_LOCK.acquire(blocking=False):
        return _CR_STATE
    try:
        base = ranges_root()
        try:
            target = _cr_pointer_target(base)
            if target is None:
                key = ("absent",)
            else:
                st = os.lstat(os.path.join(base, target))
                key = (target, st.st_mtime_ns, st.st_ino)
        except FileNotFoundError:
            key, target = ("missing",), ""
        except (RangesRefused, OSError) as e:
            key, target = ("pointer", type(e).__name__), ""
        if key == _CR_KEY:
            return _CR_STATE
        if key == ("absent",):
            new = RangesState("absent")
        elif key[0] in ("missing", "pointer"):
            new = RangesState("refused", reason="pointer")
        else:
            try:
                table = load_ranges_dir(os.path.join(base, target))
                new = RangesState(table.rev, table)
            except RangesRefused as e:
                new = RangesState("refused", reason=e.cls)
            except Exception as e:            # noqa: BLE001 -- any other failure refuses
                new = RangesState("refused", reason="error:" + type(e).__name__)
        _CR_STATE = new
        _CR_KEY = key
        _cr_log(new, key)
        return new
    finally:
        _CR_LOCK.release()


def ranges_health_word() -> str:
    return _CR_STATE.word


def classify_address(host) -> tuple:
    """(class, ranges word) for one client address string, against the state
    already published (never a load). Any fault, an unparsable address, the
    limiter's own `unknown`, or no loaded list yields `unknown`. Prints and
    raises nothing; the address never leaves this call."""
    state = _CR_STATE
    word = state.word if state.word in ("absent", "refused") else state.table.rev
    try:
        if state.table is None or not isinstance(host, str):
            return "unknown", word
        addr = ipaddress.ip_address(host.split("%", 1)[0])
        if addr.version == 6 and addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        cls = state.table.lookup(addr)
        return (cls if cls in CONN_CLASSES else "unknown"), word
    except Exception:                         # noqa: BLE001 -- a fault is unknown, silently
        return "unknown", word


# -- the integrator's build tool (seat side; never run by the api) -------------

def build_ranges_revision(draft: str, store: str) -> str:
    """Seal a draft directory holding ranges.txt, sources.txt and selftest.txt
    into `store/ranges-<rev12>/` (REVISION written), validate it with the
    loader, and return the rev12. Refuses to overwrite. The revision is sealed
    and validated under a staging directory first and moved into the store only
    when the loader accepts it, so a refused draft (RangesRefused raised)
    leaves nothing in the store."""
    data = {}
    for name in ("ranges.txt", "sources.txt", "selftest.txt"):
        with open(os.path.join(draft, name), "rb") as f:
            data[name] = f.read()
    digest = ranges_digest(data)
    rev = digest[: CR_BOUNDS["rev_hex"]]
    final = os.path.join(store, "ranges-" + rev)
    if os.path.exists(final):
        raise FileExistsError(final)
    staging = os.path.join(store, ".staging-" + rev)
    sealed = os.path.join(staging, "ranges-" + rev)
    os.makedirs(sealed)
    try:
        try:
            for name, raw in data.items():
                with open(os.path.join(sealed, name), "wb") as f:
                    f.write(raw)
            with open(os.path.join(sealed, "REVISION"), "wb") as f:
                f.write((digest + "\n").encode("ascii"))
            load_ranges_dir(sealed)
            os.rename(sealed, final)
        except BaseException:
            for name in list(data) + ["REVISION"]:
                try:
                    os.remove(os.path.join(sealed, name))
                except FileNotFoundError:
                    pass
            os.rmdir(sealed)
            raise
    finally:
        os.rmdir(staging)
    return rev


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "validate":
        try:
            t = load_ranges_dir(sys.argv[2])
            print("verdict: loaded rev=%s intervals=%d sources=%d" % (t.rev, t.intervals, t.sources))
            sys.exit(0)
        except RangesRefused as e:
            print("verdict: refused (%s)" % e.cls)
            sys.exit(1)
    if len(sys.argv) == 4 and sys.argv[1] == "build":
        print(build_ranges_revision(sys.argv[2], sys.argv[3]))
        sys.exit(0)
    print("usage: python conn_ranges.py validate <dir> | build <draft> <store>")
    sys.exit(2)
