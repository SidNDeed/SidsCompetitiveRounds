"""A writer of small files in the MMDB format, for the region reader's tests.

build() lays out a search tree, the 16-byte separator, a data section and
the metadata from a description: networks with their records, the record
size (24, 28 or 32), the IP version (4 or 6) and a build_epoch. Its records
hold INVENTED place names only, and its networks are the single public
resolver addresses that the lane's other tests already hold. The damaged
forms the cases need are made from what build() returns (the layout's
offsets are returned with the bytes) or by the value wrappers below.
"""
import ipaddress
import struct
from dataclasses import dataclass

MARKER = b"\xab\xcd\xefMaxMind.com"

# Published resolver service addresses (the set test_alt_signals_pure.py
# holds); the writer refuses any other network.
RESOLVERS = frozenset({"1.1.1.1", "1.0.0.1", "1.1.1.2", "1.0.0.2", "1.1.1.3", "1.0.0.3",
                       "8.8.8.8", "8.8.4.4", "9.9.9.9", "149.112.112.112",
                       "2606:4700:4700::1111", "2606:4700:4700::1001"})


# -- value wrappers -----------------------------------------------------------

class Uint:
    """An unsigned integer of a given type number (5, 6, 9 or 10)."""
    def __init__(self, value, kind=6):
        self.value, self.kind = value, kind


class Pairs:
    """A map written from (key, value) pairs in order, repeats allowed."""
    def __init__(self, pairs):
        self.pairs = list(pairs)


class Ptr:
    """The value stored once elsewhere in the data section, a pointer here.
    `size` forces the pointer's form (0 to 3)."""
    def __init__(self, value, size=None):
        self.value, self.size = value, size


class Raw:
    """Bytes written as they are. A callable receives the offset (in the
    data section) where these bytes will stand."""
    def __init__(self, data):
        self.data = data


class PtrTo:
    """A pointer with a given value (an offset in the data section), of form 3."""
    def __init__(self, value):
        self.value = value


class F32:
    def __init__(self, value):
        self.value = value


# -- encoding -----------------------------------------------------------------

def head(kind, size):
    """The control byte(s) of a field of type `kind` and payload size `size`."""
    if size < 29:
        sbits, extra = size, b""
    elif size < 285:
        sbits, extra = 29, (size - 29).to_bytes(1, "big")
    elif size < 65821:
        sbits, extra = 30, (size - 285).to_bytes(2, "big")
    else:
        sbits, extra = 31, (size - 65821).to_bytes(3, "big")
    if kind <= 7:
        return bytes([(kind << 5) | sbits]) + extra
    return bytes([sbits, kind - 7]) + extra


def pointer(value, size=None):
    """A pointer field to `value` (an offset counted from the section start)."""
    if size is None:
        size = 0 if value < 2048 else 1 if value < 526336 else 2 if value < 134744064 else 3
    if size == 3:
        return bytes([0x38]) + value.to_bytes(4, "big")
    base = (0, 2048, 526336)[size]
    v = value - base
    if v < 0 or v >= 1 << (8 * (size + 1) + 3):
        raise ValueError("the pointer's form cannot hold the value")
    return bytes([0x20 | (size << 3) | (v >> (8 * (size + 1)))]) + (v & ((1 << (8 * (size + 1))) - 1)).to_bytes(size + 1, "big")


def _uint_bytes(n):
    return n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""


class _Section:
    """A data section being written: values stored by pointer go first."""

    def __init__(self):
        self.buf = bytearray()

    def store(self, value):
        """Append `value`'s bytes; return its offset."""
        data = self.encode(value)
        at = len(self.buf)
        if isinstance(value, Raw) and callable(value.data):
            data = value.data(at)
        self.buf += data
        return at

    def encode(self, v):
        if isinstance(v, Raw):
            return b"" if callable(v.data) else bytes(v.data)
        if isinstance(v, PtrTo):
            return pointer(v.value, 3)
        if isinstance(v, Ptr):
            return pointer(self.store(v.value), v.size)
        if isinstance(v, bool):
            return head(14, int(v))
        if isinstance(v, Uint):
            b = _uint_bytes(v.value)
            return head(v.kind, len(b)) + b
        if isinstance(v, int):
            b = _uint_bytes(v)
            return head(6 if v < 2 ** 32 else 9, len(b)) + b
        if isinstance(v, F32):
            return head(15, 4) + struct.pack(">f", v.value)
        if isinstance(v, float):
            return head(3, 8) + struct.pack(">d", v)
        if isinstance(v, str):
            b = v.encode("utf-8")
            return head(2, len(b)) + b
        if isinstance(v, bytes):
            return head(4, len(v)) + v
        if isinstance(v, (dict, Pairs)):
            pairs = v.pairs if isinstance(v, Pairs) else list(v.items())
            out = bytearray(head(7, len(pairs)))
            for k, val in pairs:
                out += self.encode(k)
                out += self.encode(val)
            return bytes(out)
        if isinstance(v, list):
            out = bytearray(head(11, len(v)))
            for val in v:
                out += self.encode(val)
            return bytes(out)
        raise TypeError(type(v).__name__)


# -- the tree -----------------------------------------------------------------

def _bits(cidr, ip_version):
    net = ipaddress.ip_network(cidr)
    if str(net.network_address) not in RESOLVERS or net.prefixlen != net.max_prefixlen:
        raise ValueError("the stand-in holds the resolver addresses alone, each as one address")
    n = int(net.network_address)
    if net.version == 4 and ip_version == 6:
        return [0] * 96 + [(n >> (31 - i)) & 1 for i in range(32)]
    if net.version == 6 and ip_version == 4:
        raise ValueError("an IPv6 network in an IPv4 file")
    width = 32 if net.version == 4 else 128
    return [(n >> (width - 1 - i)) & 1 for i in range(width)]


def _node_bytes(left, right, record_size):
    for v in (left, right):
        if v >= 1 << record_size:
            raise ValueError("a record value does not fit the record size")
    if record_size == 24:
        return left.to_bytes(3, "big") + right.to_bytes(3, "big")
    if record_size == 28:
        mid = ((left >> 24) & 0x0F) << 4 | ((right >> 24) & 0x0F)
        return (left & 0xFFFFFF).to_bytes(3, "big") + bytes([mid]) + (right & 0xFFFFFF).to_bytes(3, "big")
    if record_size == 32:
        return left.to_bytes(4, "big") + right.to_bytes(4, "big")
    raise ValueError("record size")


@dataclass
class Built:
    data: bytes
    node_count: int
    tree_size: int
    data_start: int
    marker_at: int


def metadata_pairs(node_count, record_size, ip_version, build_epoch):
    return [("binary_format_major_version", Uint(2, 5)),
            ("binary_format_minor_version", Uint(0, 5)),
            ("build_epoch", Uint(build_epoch, 9)),
            ("database_type", "Standin-Region"),
            ("description", {"en": "A stand-in file for tests"}),
            ("ip_version", Uint(ip_version, 5)),
            ("languages", ["en", "de"]),
            ("node_count", Uint(node_count, 6)),
            ("record_size", Uint(record_size, 5))]


def build(networks, record_size=24, ip_version=6, build_epoch=1798761600,
          lead_pad=0, tail_pad=0, meta=None):
    """The bytes and layout of a file holding `networks`, a list of
    (address text, record value). `lead_pad` zero bytes stand at the data
    section's start and `tail_pad` at its end, referenced by nothing.
    `meta(pairs)` may change the metadata's pairs before they are written."""
    root = [None, None]
    leaves = []
    for cidr, record in networks:
        path = _bits(cidr, ip_version)
        node = root
        for bit in path[:-1]:
            if node[bit] is None:
                node[bit] = [None, None]
            if not isinstance(node[bit], list):
                raise ValueError("overlapping networks")
            node = node[bit]
        if node[path[-1]] is not None:
            raise ValueError("a network given twice")
        node[path[-1]] = ("leaf", len(leaves))
        leaves.append(record)
    order, index = [], {}
    queue = [root]
    while queue:
        n = queue.pop(0)
        index[id(n)] = len(order)
        order.append(n)
        queue.extend(c for c in n if isinstance(c, list))
    node_count = len(order)
    sec = _Section()
    sec.buf += bytes(lead_pad)
    offsets = [sec.store(rec) for rec in leaves]
    sec.buf += bytes(tail_pad)

    def value(c):
        if c is None:
            return node_count
        if isinstance(c, list):
            return index[id(c)]
        return node_count + 16 + offsets[c[1]]

    tree = b"".join(_node_bytes(value(n[0]), value(n[1]), record_size) for n in order)
    pairs = metadata_pairs(node_count, record_size, ip_version, build_epoch)
    if meta is not None:
        pairs = meta(pairs)
    meta_bytes = _Section().encode(Pairs(pairs))
    data_start = len(tree) + 16
    out = tree + bytes(16) + bytes(sec.buf)
    marker_at = len(out)
    out += MARKER + meta_bytes
    return Built(out, node_count, len(tree), data_start, marker_at)


def place(country=None, subdivision=None, **extra):
    """A record in the shape of a city file's, with English names only."""
    rec = {}
    if country is not None:
        rec["country"] = {"iso_code": "ZZ", "names": {"en": country}}
    if subdivision is not None:
        rec["subdivisions"] = [{"names": {"en": subdivision}}]
    rec.update(extra)
    return rec
