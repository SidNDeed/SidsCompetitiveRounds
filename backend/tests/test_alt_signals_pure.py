"""The pure half of the alternate-account signals (alt_signals.py): key
states, marks, address rules, Steam's fields, the constants and the
disclosure paragraph. No database. Ids are invented; the accepted addresses
are public resolver service addresses; every other address is from a
documentation, private or reserved range."""
import ast
import ipaddress
import re
from pathlib import Path

import pytest

import alt_signals as A
import conn_ranges

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
KEY_HEX = "0f1e2d3c4b5a69788796a5b4c3d2e1f00112233445566778899aabbccddeeff0"
KEY_ID = "959163f0cc32"
SID = "76561190000000001"
OTHER = "76561190000000002"
LAN = conn_ranges.CR_LAN_NETS
V4 = "1.1.1.1"
V6 = "2606:4700:4700::1111"

# HMAC-SHA256 under KEY_HEX, computed once outside this module and pinned:
# any change to a domain, the version or prefix byte, or the packing moves
# them.
NET_VECTORS = {
    "192.0.2.10/32": "4a15dbc567d5679084ff35bd6a0e9920f9793937fcac607e1ae615ec78d302d5",
    "192.0.2.10/24": "081979df8e29ecdae2bbf777d005ca8c1ab8c236b3e4500c7f946074a1e74a8a",
    "2001:db8:1:2:3:4:5:6/64": "9d3163d656ba6ffba1cc29844b76aa3ddde71718bcfa550c07d08232f3bc8b78",
    "2001:db8:1:2:3:4:5:6/48": "503510c3675270b6be11dcee84342036353222cee8b4b9af8fc7eac48f43aafb",
}
ACCOUNT_VECTOR = (SID, "3c685f6b6a1d5de457d590d0cff17bebd7c6dc22eb21027e0651e3de6caf8ed3")


def _key():
    state, k = A.load_key(KEY_HEX)
    assert state == "loaded"
    return k


def _net(text):
    return ipaddress.ip_network(text, strict=False)


def _classify(cls):
    return lambda host: (cls, "rev")


@pytest.fixture(autouse=True)
def _no_key_installed_after():
    yield
    A.install_key(None)


# -- the key -------------------------------------------------------------------

@pytest.mark.parametrize("raw", [None, "", "   ", "\t\r\n\x0b\x0c"])
def test_an_unset_or_blank_key_is_absent(raw):
    assert A.load_key(raw) == ("absent", None)


@pytest.mark.parametrize("raw", [
    "ab" * 31,                 # 62 digits: short
    "a" * 65,                  # odd
    "g" * 64,                  # not hex
    KEY_HEX * 2 + "ab",        # 130 digits: long
    "00" * 32, "ab" * 32,      # every byte equal: a placeholder
    " " + KEY_HEX,        # not ASCII whitespace, so not stripped
    b"\x01\x02" * 16, 123, ["x"], 1.5,
])
def test_a_malformed_key_is_refused(raw):
    assert A.load_key(raw) == ("refused", None)


@pytest.mark.parametrize("raw", [KEY_HEX, KEY_HEX.upper(), " \t" + KEY_HEX + "\r\n", KEY_HEX * 2])
def test_a_valid_key_loads_with_its_key_id(raw):
    state, k = A.load_key(raw)
    assert state == "loaded" and len(k.secret) in (32, 64)
    if len(k.secret) == 32:
        assert k.key_id == KEY_ID
    assert re.fullmatch(r"[0-9a-f]{12}", k.key_id)


def test_load_key_never_raises_and_the_repr_names_only_the_key_id():
    for raw in (object(), b"", {}, "x" * 10000, "\x00" * 64, "%s\x00" % KEY_HEX, float("nan")):
        assert A.load_key(raw)[0] in ("absent", "refused", "loaded")
    assert KEY_HEX not in repr(_key()) and KEY_ID in repr(_key())


def test_install_sets_the_state_the_route_and_health_read():
    assert A.install_key(None) == "absent" and A.loaded_key() is None and A.key_word() == "absent"
    assert A.install_key("zz") == "refused" and A.loaded_key() is None and A.key_word() == "refused"
    assert A.install_key(KEY_HEX) == "loaded" and A.key_word() == KEY_ID
    assert A.loaded_key().secret == bytes.fromhex(KEY_HEX)


# -- the marks -----------------------------------------------------------------

def test_the_marks_match_their_known_answers():
    k = _key()
    for net, want in NET_VECTORS.items():
        assert A.net_mark(k.secret, _net(net)).hex() == want, net
    assert A.account_mark(k.secret, ACCOUNT_VECTOR[0]).hex() == ACCOUNT_VECTOR[1]


def test_the_three_domains_and_the_prefix_byte_separate_the_marks():
    k = _key()
    assert len({A.D_NET, A.D_ACCOUNT, A.D_KEYID}) == 3
    # Same network address, different prefix: only the prefix byte differs.
    assert A.net_mark(k.secret, _net("192.0.2.0/24")) != A.net_mark(k.secret, _net("192.0.2.0/32"))
    payload = b"76561190000000001"
    assert A._asg_mark(k.secret, A.D_NET, payload) != A._asg_mark(k.secret, A.D_ACCOUNT, payload)


# -- the address rules ---------------------------------------------------------

def _lan_examples():
    out = []
    for net in LAN:
        out.append(str(net.network_address + (1 if net.num_addresses > 1 else 0)))
    return out


@pytest.mark.parametrize("host,word", [
    (None, "type"), (b"1.1.1.1", "type"), (16843009, "type"), (["1.1.1.1"], "type"),
    ("unknown", "unparsable"), ("", "unparsable"), ("1.2.3", "unparsable"), ("::g", "unparsable"),
    ("1.1.1.1 ", "unparsable"), ("localhost", "unparsable"),
    ("224.0.0.1", "multicast"), ("239.255.255.250", "multicast"), ("ff02::1", "multicast"),
    ("ff0e::1", "multicast"), ("::ffff:224.0.0.1", "multicast"),
    ("fe80::1%eth0", "lan"),
    ("0.0.0.0", "not_global"), ("::", "not_global"), ("240.0.0.1", "not_global"),
    ("192.0.2.1", "not_global"), ("2001:db8::1", "not_global"), ("198.18.0.1", "not_global"),
    ("255.255.255.255", "not_global"),
    (V4, None), (V6, None), ("::ffff:1.1.1.1", None), (V6 + "%3", None),
])
def test_each_address_is_refused_by_its_first_rule_or_accepted(host, word):
    assert A.address_refusal(host, LAN) == word


def test_every_lan_range_is_refused_by_the_lan_rule_itself():
    """Checked directly, so the rule holds with no range list loaded and
    whatever is_global says."""
    examples = _lan_examples()
    assert len(examples) == len(LAN) >= 9
    for host in examples:
        assert A.address_refusal(host, LAN) == "lan", host


def test_observe_marks_the_masked_address_and_block():
    k = _key()
    o4 = A.observe(V4, k, _classify("none"), LAN)
    assert o4 == (4, A.net_mark(k.secret, _net("1.1.1.1/32")), A.net_mark(k.secret, _net("1.1.1.0/24")), "none")
    o6 = A.observe(V6, k, _classify("hosting"), LAN)
    assert o6 == (6, A.net_mark(k.secret, _net("2606:4700:4700::/64")),
                  A.net_mark(k.secret, _net("2606:4700:4700::/48")), "hosting")


def test_one_slash_64_is_one_address_mark_and_one_slash_48_one_block_mark():
    k = _key()
    c = _classify("none")
    same64 = A.observe("2606:4700:4700::1001", k, c, LAN)
    other64 = A.observe("2606:4700:4700:1::1", k, c, LAN)
    base = A.observe(V6, k, c, LAN)
    assert same64.addr_mark == base.addr_mark
    assert other64.addr_mark != base.addr_mark and other64.block_mark == base.block_mark
    # IPv4: one /24 is one block; a neighbour in the same /16 is another.
    assert A.observe("1.1.1.2", k, c, LAN).block_mark == base4(k).block_mark
    assert A.observe("1.1.1.2", k, c, LAN).addr_mark != base4(k).addr_mark
    assert A.observe("1.1.2.1", k, c, LAN).block_mark != base4(k).block_mark


def base4(k):
    return A.observe(V4, k, _classify("none"), LAN)


def test_a_mapped_or_zoned_address_marks_as_its_plain_form():
    k = _key()
    c = _classify("none")
    assert A.observe("::ffff:1.1.1.1", k, c, LAN) == base4(k)
    assert A.observe(V6 + "%7", k, c, LAN) == A.observe(V6, k, c, LAN)


def test_no_key_or_a_refused_address_gives_no_marker():
    k = _key()
    assert A.observe(V4, None, _classify("none"), LAN) is None
    for host in (None, "unknown", "224.0.0.1", "10.0.0.1", "192.0.2.1"):
        assert A.observe(host, k, _classify("none"), LAN) is None, host


def test_the_class_outside_the_stored_set_or_a_fault_reads_unknown():
    k = _key()
    assert A.observe(V4, k, _classify("vpn"), LAN).conn_class == "vpn"
    assert A.observe(V4, k, _classify("lan"), LAN).conn_class == "unknown"
    assert A.observe(V4, k, _classify("other"), LAN).conn_class == "unknown"

    def boom(host):
        raise RuntimeError("fault")
    assert A.observe(V4, k, boom, LAN).conn_class == "unknown"


# -- Steam's fields ------------------------------------------------------------

def test_the_copy_state_reads_own_shared_or_unknown():
    k = _key()
    assert A.steam_fields({"ownersteamid": SID}, SID, k) == ("own", None, None, None)
    assert A.steam_fields({"ownersteamid": "0" + SID}, SID, k).copy_state == "own"
    assert A.steam_fields({"ownersteamid": OTHER}, SID, k) == ("shared", A.account_mark(k.secret, OTHER), None, None)
    assert A.steam_fields({"ownersteamid": OTHER}, SID, None) == ("shared", None, None, None)
    for owner in (None, "", "0", "00", "abc", "1" * 21, int(OTHER), "７６", " " + OTHER, [OTHER]):
        assert A.steam_fields({"ownersteamid": owner}, SID, k) == ("unknown", None, None, None), owner
    assert A.steam_fields({}, SID, k) == ("unknown", None, None, None)


def test_the_ban_flags_take_only_booleans():
    k = _key()
    for v in (True, False):
        got = A.steam_fields({"vacbanned": v, "publisherbanned": v}, SID, k)
        assert (got.vac_banned, got.publisher_banned) == (v, v)
    for v in ("true", "false", 1, 0, None, [], {}):
        got = A.steam_fields({"vacbanned": v, "publisherbanned": v}, SID, k)
        assert (got.vac_banned, got.publisher_banned) == (None, None), v


def test_steam_fields_never_raises_and_reads_exactly_three_keys():
    k = _key()
    for params in (None, [], "x", 5, {"ownersteamid": object()}, {object(): 1}):
        assert A.steam_fields(params, SID, k).copy_state in ("own", "shared", "unknown")

    class Watched(dict):
        seen = set()

        def get(self, key, default=None):
            Watched.seen.add(key)
            return dict.get(self, key, default)

        def __getitem__(self, key):
            Watched.seen.add(key)
            return dict.__getitem__(self, key)
    A.steam_fields(Watched(ownersteamid=OTHER, vacbanned=False, publisherbanned=True, steamid=SID), SID, k)
    assert Watched.seen == {"ownersteamid", "vacbanned", "publisherbanned"}


# -- the constants and the paragraph ------------------------------------------

def test_the_stored_class_set_is_conn_classes_without_lan_and_427s_check():
    assert set(A.STORED_CLASSES) == set(conn_ranges.CONN_CLASSES) - {"lan"}
    text = (SQL_DIR / "427_alt_signals.sql").read_text(encoding="utf-8")
    m = re.findall(r"CHECK \(conn_class IN \(([^)]*)\)\)", text)
    assert len(m) == 1 and tuple(re.findall(r"'([a-z]+)'", m[0])) == A.STORED_CLASSES


def test_the_retention_constants_keep_their_margins():
    assert A.DUE_DAYS == A.DEADLINE_DAYS - 1 and A.DUE_DAYS < A.DEADLINE_DAYS
    assert 86400 >= 2 * A.PASS_PERIOD_S + A.PASS_BUDGET_S
    assert A.PASS_FIRST_DELAY_S < A.PASS_PERIOD_S <= 3600
    assert A.RECORD_LOCK_TIMEOUT_MS < A.RECORD_STATEMENT_TIMEOUT_MS
    assert A.PASS_LOCK_TIMEOUT_MS < A.PASS_STATEMENT_TIMEOUT_MS < A.PASS_BUDGET_S * 1000
    assert A.ADDR_PREFIX == {4: 32, 6: 64} and A.BLOCK_PREFIX == {4: 24, 6: 48}


def test_the_disclosure_is_the_paragraph_427_adds_and_names_the_deadline():
    s338 = (SQL_DIR / "338_faq_channel_post_revisions.sql").read_text(encoding="utf-8")
    s427 = (SQL_DIR / "427_alt_signals.sql").read_text(encoding="utf-8")
    was = re.findall(r"\$faq1\$(.*?)\$faq1\$", s338, re.S)
    new = re.findall(r"\$faq1\$(.*?)\$faq1\$", s427, re.S)
    assert len(was) == 1 and len(new) == 1
    assert new[0] == was[0] + "\n\n" + A.DISCLOSURE
    assert ("no later than %d days after it was last seen" % A.DEADLINE_DAYS) in A.DISCLOSURE


# -- The route manifest's fold by name ----------------------------------------
# The gate (test_route_manifest_net_seat.py) resolves a bare name in every api
# module and folds each match into a route's fingerprint. A name this module
# binds that another api module also spells therefore enters the fingerprints
# of routes that never run this file, and every change here would move them.

API_DIR = Path(__file__).resolve().parents[1] / "api"


def _module_level_names(source):
    """The names a module binds at its top level: defs, classes, assigned
    names and import aliases."""
    names = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
    return names


def _spelled_names(source):
    """Every name a module spells bare anywhere: a Name, a def or class name,
    an import alias or a parameter."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


def _clashes(mine, others):
    return {name: sorted(fn for fn, spelled in others.items() if name in spelled)
            for name in sorted(mine) if any(name in spelled for spelled in others.values())}


def test_no_module_level_name_is_spelled_by_another_api_module():
    mine = _module_level_names((API_DIR / "alt_signals.py").read_text(encoding="utf-8"))
    # The reader sees the aliased imports and the renamed names, so the check
    # runs over what the module really binds.
    assert {"_asg_hashlib", "_asg_hmac", "_asg_ipaddress", "_asg_re", "_asg_namedtuple",
            "install_key", "RELATION_LIST_CAP", "DISCLOSURE"} <= mine, sorted(mine)
    others = {p.name: _spelled_names(p.read_text(encoding="utf-8"))
              for p in sorted(API_DIR.glob("*.py")) if p.name != "alt_signals.py"}
    assert len(others) >= 30, sorted(others)
    assert _clashes(mine, others) == {}


def test_the_spelling_check_finds_a_plain_import_and_a_shared_name():
    others = {"x.py": _spelled_names("import re\nimport hashlib\n\ndef install(a):\n    return re.sub('a', '', a)\n")}
    mine = _module_level_names("import re\nimport hashlib as _h\nLIST = 1\n\ndef install(raw):\n    return raw\n")
    assert _clashes(mine, others) == {"install": ["x.py"], "re": ["x.py"]}
