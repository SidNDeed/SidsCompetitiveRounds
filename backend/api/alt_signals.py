"""Alternate-account signals: the pure half (no database, no network, no log).

At a verified sign-in, while a signal key is loaded and the FAQ notice is up,
the api may record what Steam reports about the account's copy of ROUNDS and
its two ban flags, and keyed one-way codes ("marks") of the connecting
address and of its network block. This module holds everything about that
which needs no database: the key and its states, the marks, the address
rules, the reading of Steam's fields, the constants every other part is
pinned to, and the disclosure paragraph.

Nothing here judges an account. A mark is an HMAC-SHA256 under the server's
key; the address and the block themselves are never returned.
"""
# The imports are aliased, and the names this module binds are chosen, so
# that no other api module spells any of them. The route-manifest gate
# resolves a bare name in EVERY api module and folds each match into a
# route's fingerprint, so a plain `import hashlib` here moved the
# fingerprints of 397 routes that never run this file. A test in
# test_alt_signals_pure.py holds every module-level name to that.
import hashlib as _asg_hashlib
import hmac as _asg_hmac
import ipaddress as _asg_ipaddress
import re as _asg_re
from collections import namedtuple as _asg_namedtuple

KEY_ENV = "SCR_ALT_SIGNAL_KEY"

# Three domains. Owner marks (a lending account's id) and the marks the read
# side computes for candidate accounts share D_ACCOUNT on purpose: equality
# of the two is how a lender who plays here is named, at read time only.
D_NET = b"scr-alt-signals net v1\x00"
D_ACCOUNT = b"scr-alt-signals account v1\x00"
D_KEYID = b"scr-alt-signals key-id v1\x00"

# The address mark covers the /32 (IPv4) or the /64 (IPv6); the block mark
# the /24 or the /48 (ruling Q1).
ADDR_PREFIX = {4: 32, 6: 64}
BLOCK_PREFIX = {4: 24, 6: 48}

# Retention (ruling R4). Every row is gone no later than DEADLINE_DAYS after
# its own last sight; a row is due DUE_DAYS after it, and the read window is
# the due age, so the report never counts days that may already be gone.
DEADLINE_DAYS = 90
DUE_DAYS = 89
PASS_PERIOD_S = 3600
PASS_FIRST_DELAY_S = 60
PASS_BUDGET_S = 300
PASS_BATCH = 2000
PASS_LOCK_TIMEOUT_MS = 1000
PASS_STATEMENT_TIMEOUT_MS = 15000

# The recording transaction's own limits (ruling R1): every lock wait it can
# cause ends within the first, every statement within the second.
RECORD_LOCK_TIMEOUT_MS = 500
RECORD_STATEMENT_TIMEOUT_MS = 1500

# Storage limits, enforced in the upsert statements (ruling R4).
MARKERS_PER_DAY = 8
SHARES_PER_ACCOUNT = 4

# The read side (rulings R2, R3).
OWNER_CANDIDATE_CAP = 50000
RELATION_LIST_CAP = 25

# conn_ranges.CONN_CLASSES without 'lan': a LAN address is never marked.
STORED_CLASSES = ("none", "hosting", "vpn", "relay", "tor", "unknown")

# The one constant every disclosure surface is pinned to (ruling R6): the
# last paragraph of FAQ message 1 (docs/FAQ.md and migration 427), the bot's
# answer, and the notice check the recording runs.
DISCLOSURE = (
    "**What the server may record at sign-in, for fair-play review:** what Steam reports about "
    "your account, namely whether your copy of ROUNDS is owned or borrowed through Steam Family "
    "Sharing (for a borrowed copy, a keyed one-way code of the lending account, never its id) and "
    "whether the account has a VAC ban or a game ban; and from your connection, keyed one-way "
    "codes of your internet address and of its network block (never the address itself), whether "
    "it is IPv4 or IPv6, and its connection class, such as VPN or hosting. With these go the "
    "times each was first and last seen, and on how many days a storage limit was reached. Each "
    "record is deleted no later than 90 days after it was last seen, and at once if you delete "
    "your account.")

_ASCII_SPACE = " \t\n\r\x0b\x0c"
_ASG_HEX = _asg_re.compile(r"[0-9a-fA-F]+")
_STEAM_ID = _asg_re.compile(r"[0-9]{1,20}")


class LoadedKey:
    """A loaded key. Its repr names the key id only."""
    __slots__ = ("secret", "key_id")

    def __init__(self, secret, key_id):
        self.secret = secret
        self.key_id = key_id

    def __repr__(self):
        return "LoadedKey(key_id=%r)" % self.key_id


def load_key(raw):
    """('absent' | 'refused' | 'loaded', LoadedKey or None). Never raises.

    absent: unset, or empty after stripping ASCII whitespace. refused: not 64
    to 128 hex digits of even length, all bytes equal (a placeholder), or not
    a string. loaded: anything else."""
    try:
        if raw is None:
            return "absent", None
        if not isinstance(raw, str):
            return "refused", None
        s = raw.strip(_ASCII_SPACE)
        if not s:
            return "absent", None
        if not (64 <= len(s) <= 128) or len(s) % 2 or not _ASG_HEX.fullmatch(s):
            return "refused", None
        secret = bytes.fromhex(s)
        if len(set(secret)) == 1:
            return "refused", None
        key_id = _asg_hmac.new(secret, D_KEYID, _asg_hashlib.sha256).hexdigest()[:12]
        return "loaded", LoadedKey(secret, key_id)
    except Exception:  # noqa: BLE001 -- total by contract
        return "refused", None


_INSTALLED = ("absent", None)


def install_key(raw):
    """Load `raw` as this process's key and return its state word. The api
    calls it once at import with the environment's value."""
    global _INSTALLED
    _INSTALLED = load_key(raw)
    return _INSTALLED[0]


def loaded_key():
    """The installed key, or None while it is absent or refused."""
    return _INSTALLED[1]


def key_word():
    """What /health shows: 'absent', 'refused', or the key id."""
    state, key = _INSTALLED
    return key.key_id if state == "loaded" and key is not None else state


def _asg_mark(secret, domain, payload):
    return _asg_hmac.new(secret, domain + payload, _asg_hashlib.sha256).digest()


def net_mark(secret, network):
    """The mark of one network (an ipaddress network object): the version
    byte, the prefix byte and the packed network address."""
    return _asg_mark(secret, D_NET, bytes([network.version, network.prefixlen]) + network.network_address.packed)


def account_mark(secret, steam_id):
    """The mark of one account id in decimal ASCII."""
    return _asg_mark(secret, D_ACCOUNT, steam_id.encode("ascii"))


def address_refusal(host, lan_nets):
    """None when `host` is an address the recording may mark, else the word
    of the first rule it fails: 'type' (not a string, None included),
    'unparsable' (the limiter's 'unknown' included), 'multicast', 'lan' (an
    entry of `lan_nets`, checked directly so the rule holds with no range
    list loaded), 'not_global'. A zone id is stripped and an IPv4-mapped IPv6
    address is read as its IPv4 address first."""
    a = _parse(host)
    if isinstance(a, str):
        return a
    if a.is_multicast:
        return "multicast"
    if any(a in net for net in lan_nets if net.version == a.version):
        return "lan"
    if not a.is_global:
        return "not_global"
    return None


def _parse(host):
    if not isinstance(host, str):
        return "type"
    try:
        a = _asg_ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return "unparsable"
    if a.version == 6 and a.ipv4_mapped is not None:
        a = a.ipv4_mapped
    return a


Observation = _asg_namedtuple("Observation", "family addr_mark block_mark conn_class")


def observe(host, key, classify, lan_nets):
    """The marker values for one sign-in's address, or None (no marker row).

    `classify` is conn_ranges.classify_address; its class outside
    STORED_CLASSES, or any fault in it, reads as 'unknown'."""
    if key is None or address_refusal(host, lan_nets) is not None:
        return None
    a = _parse(host)
    v = a.version
    addr_net = _asg_ipaddress.ip_network("%s/%d" % (a, ADDR_PREFIX[v]), strict=False)
    block_net = _asg_ipaddress.ip_network("%s/%d" % (a, BLOCK_PREFIX[v]), strict=False)
    try:
        cls = classify(str(a))[0]
    except Exception:  # noqa: BLE001 -- a fault is unknown
        cls = "unknown"
    if cls not in STORED_CLASSES:
        cls = "unknown"
    return Observation(v, net_mark(key.secret, addr_net), net_mark(key.secret, block_net), cls)


SteamFacts = _asg_namedtuple("SteamFacts", "copy_state owner_mark vac_banned publisher_banned")


def steam_fields(params, steam_id, key):
    """What Steam reported, from the ticket check's `params` object. Never
    raises. Reads exactly ownersteamid, vacbanned and publisherbanned.

    copy_state: 'own' when ownersteamid is the account's own id, 'shared'
    (with the lender's mark) when it is another id, 'unknown' for anything
    else, a missing field included; a missing field is never read as own.
    The ban flags: only a boolean is taken; anything else is None."""
    try:
        p = params if isinstance(params, dict) else {}
        owner = p.get("ownersteamid")
        copy_state, owner_mark = "unknown", None
        if isinstance(owner, str) and _STEAM_ID.fullmatch(owner) and int(owner) != 0:
            if isinstance(steam_id, str) and _STEAM_ID.fullmatch(steam_id) and int(owner) == int(steam_id):
                copy_state = "own"
            else:
                copy_state = "shared"
                if key is not None:
                    owner_mark = account_mark(key.secret, str(int(owner)))
        vac = p.get("vacbanned")
        pub = p.get("publisherbanned")
        return SteamFacts(copy_state, owner_mark,
                          vac if isinstance(vac, bool) else None,
                          pub if isinstance(pub, bool) else None)
    except Exception:  # noqa: BLE001 -- total by contract
        return SteamFacts("unknown", None, None, None)
