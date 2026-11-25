"""The region of an address, read from the region file by our own code.

region_of(host) answers the country's English name and the first
subdivision's English name as "Country, Subdivision", the country alone when
the record names no subdivision, or "". file_word() answers "absent",
"refused" or the file's build month (YYYY-MM, UTC). Both are plain functions
that their caller runs in a thread; neither lets an exception out, and this
module logs nothing.

The file is in the published MMDB format (MaxMind DB File Format
Specification, version 2.0), read as far as a lookup needs it: the metadata
found from the file's end, the search tree with records of 24, 28 or 32
bits, the IPv4 subtree of an IPv6 file, and the data section's types.

Every call opens the file read-only, takes the fstat of that descriptor,
does all its reads through it (lseek, then read) and closes it. The parsed
metadata is kept between calls under the key (device, inode, size,
mtime_ns) of that fstat and used only when the key is equal.

Bounds, each checked before the act it guards; a breach answers ""
("refused" for file_word) and raises nothing out:
- every read lies inside the size that the call's fstat gave, and a read
  that returns fewer bytes than asked ends the call;
- depth at most 8 (maps, arrays and pointers together);
- at most 400 values visited in one decode (the record of a lookup, or the
  metadata), the passed-over ones counted;
- a map key and each of the two returned texts at most 200 bytes.
A value the answer does not need is passed over by its length and never
decoded. Nothing of a record but the two names leaves this module.
"""
# The imports are aliased, and every module-level name but the two public
# functions begins with _rgn_, so that no other api module spells any of
# them: the route-manifest gate folds a bare name of every api module into
# the fingerprint of each route that spells it (alt_signals.py says why).
import datetime as _rgn_datetime
import ipaddress as _rgn_ipaddress
import os as _rgn_os
import stat as _rgn_stat

# The folder mounted into the api container, and the file's fixed name in it.
_rgn_DIR = "/app/private/geo"
_rgn_NAME = "region.mmdb"

# The start of the metadata, and the specification's limit for the metadata's
# size (128 KiB, the marker included).
_rgn_MARKER = b"\xab\xcd\xefMaxMind.com"
_rgn_META_MAX = 128 * 1024

_rgn_DEPTH = 8
_rgn_VALUES = 400
_rgn_BYTES = 200
_rgn_CHARS = 60

# The parts of a record the answer reads: country.names.en and
# subdivisions[0].names.en. Every other value is passed over.
_rgn_WANT = {"country": {"names": {"en": "text"}},
             "subdivisions": ("first", {"names": {"en": "text"}})}
_rgn_META_WANT = {"node_count": "int", "record_size": "int", "ip_version": "int",
                  "build_epoch": "int", "binary_format_major_version": "int"}

# Fixed payload sizes the specification gives (double, float) and the most
# bytes each integer type may hold.
_rgn_EXACT = {3: 8, 15: 4}
_rgn_MOST = {5: 2, 6: 4, 8: 4, 9: 8, 10: 16, 14: 1}

# (key, metadata) of the last file read; replaced as one object.
_rgn_kept = None


class _rgn_Breach(Exception):
    """Anything not as the format or a bound requires. It carries no text."""


class _rgn_Meta:
    __slots__ = ("nodes", "bits", "ipv", "tree", "data", "mark", "v4", "month")


class _rgn_Walk:
    """One decode: the call's descriptor, its fstat size, the section start
    that pointers count from, and the values visited so far."""
    __slots__ = ("fd", "size", "base", "count", "unique")

    def __init__(self, fd, size, base, unique):
        self.fd = fd
        self.size = size
        self.base = base
        self.count = 0
        self.unique = unique


def _rgn_read(fd, size, off, n):
    if off < 0 or n < 0 or off + n > size:
        raise _rgn_Breach()
    _rgn_os.lseek(fd, off, _rgn_os.SEEK_SET)
    got = _rgn_os.read(fd, n)
    if len(got) != n:
        raise _rgn_Breach()
    return got


def _rgn_head(w, off):
    """(type, size, offset after the head) of the field at off. For a pointer
    the size is the target's offset in the file."""
    ctrl = _rgn_read(w.fd, w.size, off, 1)[0]
    off += 1
    kind = ctrl >> 5
    if kind == 1:
        ss = (ctrl >> 3) & 3
        raw = int.from_bytes(_rgn_read(w.fd, w.size, off, ss + 1), "big")
        off += ss + 1
        if ss == 3:
            value = raw
        else:
            value = ((ctrl & 7) << (8 * (ss + 1)) | raw) + (0, 2048, 526336)[ss]
        return 1, w.base + value, off
    if kind == 0:
        kind = 7 + _rgn_read(w.fd, w.size, off, 1)[0]
        off += 1
        # Extended types are 8 to 15; 12 and 13 are deprecated and readers
        # are not expected to support them.
        if kind < 8 or kind > 15 or kind in (12, 13):
            raise _rgn_Breach()
    size = ctrl & 31
    if size >= 29:
        n = size - 28
        size = (29, 285, 65821)[n - 1] + int.from_bytes(_rgn_read(w.fd, w.size, off, n), "big")
        off += n
    if kind in _rgn_EXACT and size != _rgn_EXACT[kind]:
        raise _rgn_Breach()
    if kind in _rgn_MOST and size > _rgn_MOST[kind]:
        raise _rgn_Breach()
    return kind, size, off


def _rgn_text(w, off, size):
    if size > _rgn_BYTES:
        raise _rgn_Breach()
    raw = _rgn_read(w.fd, w.size, off, size)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _rgn_Breach() from None


def _rgn_pass(w, off, size):
    """The offset after a payload that is passed over, never read."""
    end = off + size
    if end > w.size:
        raise _rgn_Breach()
    return end


def _rgn_charge(w):
    if w.count >= _rgn_VALUES:
        raise _rgn_Breach()
    w.count += 1


def _rgn_key(w, off, depth):
    """A map key (a UTF-8 string, directly or through one pointer) and the
    offset after it."""
    _rgn_charge(w)
    kind, size, after = _rgn_head(w, off)
    if kind == 1:
        if depth + 1 > _rgn_DEPTH:
            raise _rgn_Breach()
        kind, size, at = _rgn_head(w, size)
        if kind != 2:
            raise _rgn_Breach()
        return _rgn_text(w, at, size), after
    if kind != 2:
        raise _rgn_Breach()
    return _rgn_text(w, after, size), after + size


def _rgn_value(w, off, depth, want, via=False):
    """(what `want` selects of the value at off, the offset after it).
    `want` is a dict (a map's wanted keys), ("first", want) (an array's
    first element), "text", "int" or None (passed over)."""
    if not via:
        _rgn_charge(w)
    kind, size, after = _rgn_head(w, off)
    if kind == 1:
        # A pointer to a pointer is not allowed by the specification.
        if via or depth + 1 > _rgn_DEPTH:
            raise _rgn_Breach()
        got, _ = _rgn_value(w, size, depth + 1, want, True)
        return got, after
    if kind == 7 or kind == 11:
        if depth + 1 > _rgn_DEPTH:
            raise _rgn_Breach()
        if kind == 7:
            found = {} if isinstance(want, dict) else None
            seen = set() if w.unique else None
            for _ in range(size):
                key, after = _rgn_key(w, after, depth + 1)
                if seen is not None:
                    if key in seen:
                        raise _rgn_Breach()
                    seen.add(key)
                sub = want.get(key) if found is not None else None
                got, after = _rgn_value(w, after, depth + 1, sub)
                if sub is not None:
                    found[key] = got
            return found, after
        first = None
        for i in range(size):
            sub = want[1] if (i == 0 and isinstance(want, tuple)) else None
            got, after = _rgn_value(w, after, depth + 1, sub)
            if sub is not None:
                first = got
        return first, after
    if kind == 2 and want == "text":
        return _rgn_text(w, after, size), after + size
    if kind in (5, 6, 9, 10) and want == "int":
        return int.from_bytes(_rgn_read(w.fd, w.size, after, size), "big"), after + size
    if kind == 14:
        return None, after
    return None, _rgn_pass(w, after, size)


def _rgn_node(fd, size, m, node, bit):
    width = m.bits // 4
    raw = _rgn_read(fd, size, node * width, width)
    if m.bits == 28:
        if bit:
            return (raw[3] & 0x0F) << 24 | int.from_bytes(raw[4:7], "big")
        return (raw[3] & 0xF0) << 20 | int.from_bytes(raw[0:3], "big")
    half = width // 2
    return int.from_bytes(raw[half:] if bit else raw[:half], "big")


def _rgn_parse(fd, size):
    span = min(size, _rgn_META_MAX)
    tail = _rgn_read(fd, size, size - span, span)
    at = tail.rfind(_rgn_MARKER)
    if at < 0:
        raise _rgn_Breach()
    m = _rgn_Meta()
    m.mark = size - span + at
    start = m.mark + len(_rgn_MARKER)
    got, _ = _rgn_value(_rgn_Walk(fd, size, start, True), start, 0, _rgn_META_WANT)
    if not isinstance(got, dict):
        raise _rgn_Breach()
    m.nodes = got.get("node_count")
    m.bits = got.get("record_size")
    m.ipv = got.get("ip_version")
    epoch = got.get("build_epoch")
    if (got.get("binary_format_major_version") != 2 or m.bits not in (24, 28, 32)
            or m.ipv not in (4, 6) or not isinstance(epoch, int)
            or not isinstance(m.nodes, int) or not 0 < m.nodes < 2 ** m.bits):
        raise _rgn_Breach()
    m.tree = m.bits * 2 // 8 * m.nodes
    m.data = m.tree + 16
    if m.data > m.mark:
        raise _rgn_Breach()
    # A build_epoch past the calendar's end leaves no month: file_word then
    # answers "refused", while the lookup does not need the month.
    try:
        when = (_rgn_datetime.datetime(1970, 1, 1, tzinfo=_rgn_datetime.timezone.utc)
                + _rgn_datetime.timedelta(seconds=epoch))
        m.month = "%04d-%02d" % (when.year, when.month)
    except (OverflowError, ValueError):
        m.month = None
    node = 0
    if m.ipv == 6:
        i = 0
        while i < 96 and node < m.nodes:
            node = _rgn_node(fd, size, m, node, 0)
            i += 1
    m.v4 = node
    return m


def _rgn_metadata(fd, st):
    global _rgn_kept
    key = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
    kept = _rgn_kept
    if kept is not None and kept[0] == key:
        return kept[1]
    m = _rgn_parse(fd, st.st_size)
    _rgn_kept = (key, m)
    return m


def _rgn_find(fd, size, m, packed):
    """The file offset of the address's record, or None for no record."""
    bits = len(packed) * 8
    if bits == 128 and m.ipv == 4:
        return None
    node = m.v4 if (bits == 32 and m.ipv == 6) else 0
    i = 0
    while i < bits and node < m.nodes:
        node = _rgn_node(fd, size, m, node, (packed[i >> 3] >> (7 - (i & 7))) & 1)
        i += 1
    if node == m.nodes:
        return None
    if node < m.nodes + 16:
        raise _rgn_Breach()
    off = node - m.nodes + m.tree
    if off >= m.mark:
        raise _rgn_Breach()
    return off


def _rgn_clean(text):
    if not isinstance(text, str):
        return ""
    return "".join(c for c in text if not (ord(c) < 32 or 127 <= ord(c) < 160))[:_rgn_CHARS]


def _rgn_name(part):
    if not isinstance(part, dict):
        return ""
    names = part.get("names")
    return _rgn_clean(names.get("en")) if isinstance(names, dict) else ""


def _rgn_open():
    # O_BINARY exists on Windows alone; elsewhere the flag is 0. The read
    # path itself is the same on every system.
    return _rgn_os.open(_rgn_os.path.join(_rgn_DIR, _rgn_NAME),
                        _rgn_os.O_RDONLY | getattr(_rgn_os, "O_BINARY", 0))


def _rgn_region(host):
    if not isinstance(host, str):
        return ""
    try:
        packed = _rgn_ipaddress.ip_address(host).packed
    except ValueError:
        return ""
    fd = _rgn_open()
    try:
        st = _rgn_os.fstat(fd)
        if not _rgn_stat.S_ISREG(st.st_mode):
            return ""
        m = _rgn_metadata(fd, st)
        off = _rgn_find(fd, st.st_size, m, packed)
        if off is None:
            return ""
        rec, _ = _rgn_value(_rgn_Walk(fd, st.st_size, m.data, False), off, 0, _rgn_WANT)
        if not isinstance(rec, dict):
            return ""
        country = _rgn_name(rec.get("country"))
        if not country:
            return ""
        sub = _rgn_name(rec.get("subdivisions"))
        return country + ", " + sub if sub else country
    finally:
        _rgn_os.close(fd)


def region_of(host):
    """The region of `host` as the module's head describes, or the empty
    text. Never raises."""
    try:
        return _rgn_region(host)
    except Exception:
        return ""


def file_word():
    """The word for the file: absent, refused, or its build month (YYYY-MM,
    UTC). Never raises."""
    try:
        try:
            fd = _rgn_open()
        except (FileNotFoundError, NotADirectoryError):
            return "absent"
        try:
            st = _rgn_os.fstat(fd)
            if not _rgn_stat.S_ISREG(st.st_mode):
                return "refused"
            return _rgn_metadata(fd, st).month or "refused"
        finally:
            _rgn_os.close(fd)
    except Exception:
        return "refused"
