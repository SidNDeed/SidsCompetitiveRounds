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
    # The expected networks are derived from the fixtures by the standard
    # library (finding R2-13): no network literal of its own.
    def masked(host, bits):
        return ipaddress.ip_network("%s/%d" % (host, bits), strict=False)
    o4 = A.observe(V4, k, _classify("none"), LAN)
    assert o4 == (4, A.net_mark(k.secret, masked(V4, 32)), A.net_mark(k.secret, masked(V4, 24)), "none")
    o6 = A.observe(V6, k, _classify("hosting"), LAN)
    assert o6 == (6, A.net_mark(k.secret, masked(V6, 64)), A.net_mark(k.secret, masked(V6, 48)), "hosting")


def test_one_slash_64_is_one_address_mark_and_one_slash_48_one_block_mark():
    k = _key()
    c = _classify("none")
    same64 = A.observe("2606:4700:4700::1001", k, c, LAN)
    # No published resolver address lies in V6's /48 outside its /64, so the
    # neighbour is derived from V6 by the standard library: the next /64.
    other64 = A.observe(str(ipaddress.ip_address(V6) + (1 << 64)), k, c, LAN)
    base = A.observe(V6, k, c, LAN)
    assert same64.addr_mark == base.addr_mark
    assert other64.addr_mark != base.addr_mark and other64.block_mark == base.block_mark
    # IPv4: one /24 is one block; an address of another /24 (a second
    # published resolver address) is another block.
    assert A.observe("1.1.1.2", k, c, LAN).block_mark == base4(k).block_mark
    assert A.observe("1.1.1.2", k, c, LAN).addr_mark != base4(k).addr_mark
    assert A.observe("1.0.0.1", k, c, LAN).block_mark != base4(k).block_mark


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


# -- every address literal of the lane (finding R2-13) ---------------------------

BACKEND = Path(__file__).resolve().parents[1]
# Published resolver service addresses the lane's tests use (Cloudflare,
# Google Public DNS, Quad9); every other literal must lie in a
# special-purpose range (not global by the standard library's reading of
# the special-purpose registries) or be multicast. Multicast (224.0.0.0/4,
# ff00::/8) is NOT in those registries: it is admitted as its own class
# because the code under test refuses it by its own rule
# (api/alt_signals.py address_refusal, the is_multicast test).
RESOLVERS = frozenset({"1.1.1.1", "1.0.0.1", "1.1.1.2", "1.0.0.2", "1.1.1.3", "1.0.0.3",
                       "8.8.8.8", "8.8.4.4", "9.9.9.9", "149.112.112.112",
                       "2606:4700:4700::1111", "2606:4700:4700::1001"})
_V4_TOKEN = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(/\d{1,2})?(?![\w.])")


def _lane_files():
    files = sorted((BACKEND / "tests").glob("test_alt_signals_*.py"))
    files += [BACKEND / "api" / "alt_signals.py", BACKEND / "sql" / "427_alt_signals.sql",
              BACKEND / "sql" / "rollback_427_alt_signals.sql",
              BACKEND / "tests" / "fixtures" / "alt_signals_disclosure.json"]
    # ALT-BAN-1: its migration, the region reader and its stand-in writer, and
    # its own test files. The reader's test file is not read: it holds an
    # unparsable address on purpose (the reader's refusal of one).
    files += sorted((BACKEND / "tests").glob("test_alt_ban_*.py"))
    files += [BACKEND / "sql" / "431_ban_links.sql", BACKEND / "sql" / "rollback_431_ban_links.sql",
              BACKEND / "api" / "geo_region.py", BACKEND / "tests" / "mmdb_standin.py"]
    return files


def _main_alt_texts(src):
    """(name, first line, text) of each top-level function definition, class
    and assignment of `src` (api/main.py's text) whose name begins with
    _alt_, alt_, _Alt or _ALT_, read by ast. Each text runs from the line
    after the end of the top-level statement before it, so the comment lines
    above it are read with it, to its own last line. At the lane's tip: 16
    functions, 2 classes and 6 assignments."""
    lines = src.split("\n")
    out = []
    prev_end = 0
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        else:
            names = []
        first = prev_end + 1
        for name in names:
            if name.startswith(("_alt_", "alt_", "_Alt", "_ALT_")):
                out.append((name, first, "\n".join(lines[first - 1:node.end_lineno])))
        prev_end = node.end_lineno
    return out


def _literal_class(tok):
    """The admitted class of one address or network literal, or None."""
    host = tok.strip().split("%")[0]
    net = ipaddress.ip_network(host, strict=False)
    addr = net.network_address
    if net.version == 6 and addr.ipv4_mapped is not None and net.prefixlen == 128:
        net = ipaddress.ip_network(addr.ipv4_mapped)
        addr = net.network_address
    if net.prefixlen == net.max_prefixlen and str(addr) in RESOLVERS:
        return "published resolver"
    if net.is_multicast:
        return "multicast"
    if not addr.is_global and not net.broadcast_address.is_global:
        return "special-purpose"
    return None


# An IPv6-looking token (holder H5): hex groups and at least two colons,
# an optional dotted IPv4 tail, zone id and prefix length.
_V6_TOKEN = re.compile(r"(?<![\w:.%])((?:[0-9A-Fa-f]{0,4}:){2,7}(?:[0-9A-Fa-f]{1,4}|\d{1,3}(?:\.\d{1,3}){3})?"
                       r"(?:%\w+)?(?:/\d{1,3})?)(?![\w:.%])")


def _v6_texts(name, src):
    """(line, text) of every part of `src` the IPv6 scan reads: for a Python
    file, each comment and each string (whole constants, longer strings and
    f-string parts) by tokenize, so code such as a slice is not read as an
    address; for any other file (the SQL files, the JSON fixture), every
    line, comments included."""
    if not name.endswith(".py"):
        return list(enumerate(src.splitlines(), 1))
    import io
    import tokenize
    kinds = {tokenize.COMMENT, tokenize.STRING} | {getattr(tokenize, "FSTRING_MIDDLE", tokenize.STRING)}
    return [(t.start[0], t.string) for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type in kinds]


def _literals(name, src):
    """Every address or network literal in `src`, both families, in every
    form the lane's files hold (holder H5): each IPv4 token of every line
    (comments, strings, SQL and JSON included); each IPv6 token of every
    comment and string of a Python file and of every line of any other file.
    A token that looks like an IPv4 address and does not parse is refused by
    name (an unknown form). LIMIT: an IPv6-looking token that does not
    parse is not an address to this scan and is skipped (a clock reading
    such as 12:00:00 is such a token); an address built at run time from
    parts (as the plants below are) is not a literal and is not read."""
    out = []
    for i, line in enumerate(src.splitlines(), 1):
        for m in _V4_TOKEN.finditer(line):
            tok = m.group(1) + (m.group(2) or "")
            try:
                cls = _literal_class(tok)
            except ValueError:
                cls = "UNKNOWN FORM"
            out.append(("%s:%d" % (name, i), tok, cls))
    for start, text_ in _v6_texts(name, src):
        for m in _V6_TOKEN.finditer(text_):
            tok = m.group(1)
            if tok.count(":") < 2:
                continue
            try:
                net = ipaddress.ip_network(tok.split("%")[0], strict=False)
                cls = _literal_class(tok)
            except ValueError:
                continue
            if net.version == 6:
                out.append(("%s:%d" % (name, start + text_.count("\n", 0, m.start())), tok, cls))
    return out


def test_every_address_literal_in_the_lanes_files_and_mains_alt_code_is_special_purpose_multicast_or_a_published_resolver():
    """Each address literal _literals finds in the lane's files and in the
    lane's top-level statements of main.py (_main_alt_texts over main.py's
    text) is special-purpose, multicast or a published resolver. LIMIT: the
    rule goes by a top-level statement's name. What the lane wrote inside a
    statement of main.py that is named otherwise is not read here: the
    import of alt_signals, the call of _alt_boot, the entry in
    _JANITOR_SELFTEST_ROOTS, its lines in lifespan, health_check, steam_auth
    and delete_player_data, and the line citations it renumbered."""
    found = []
    for f in _lane_files():
        found += _literals(f.name, f.read_text(encoding="utf-8"))
    texts = _main_alt_texts((BACKEND / "api" / "main.py").read_text(encoding="utf-8"))
    kinds = [type(ast.parse(t).body[-1]) for _n, _l, t in texts]
    counts = (sum(k in (ast.FunctionDef, ast.AsyncFunctionDef) for k in kinds),
              sum(k is ast.ClassDef for k in kinds), sum(k in (ast.Assign, ast.AnnAssign) for k in kinds))
    # 17 functions since the lane's merge of main f1460a11 (2026-11-24):
    # _alt_delete_account, the three DELETEs the deletion calls at its three
    # places; 16 before it. 7 assignments since ALT-BAN-1's step 3: its build
    # marker _ALT_BAN_BUILD at the module's end.
    assert counts == (17, 2, 7), (counts, [(n, l) for n, l, _t in texts])
    for _name, first, text_ in texts:
        found += [("main.py:%d" % (first + int(w.rsplit(":", 1)[1]) - 1), t, c)
                  for w, t, c in _literals("main.py", text_)]
    refused = [x for x in found if x[2] in (None, "UNKNOWN FORM")]
    assert refused == [], refused
    assert len(found) >= 20, found


def test_the_literal_scan_refuses_an_unlisted_public_address_a_public_network_and_an_unknown_form():
    # The planted literals are built from parts, so this file holds none.
    v4 = ".".join(("1", "1", "2", "1"))
    net = ".".join(("1", "1", "1", "0")) + "/24"
    bad = ".".join(("300", "1", "1", "1"))
    v6 = ":".join(("2606", "4700", "4700", "1", "", "1"))
    doc = ".".join(("192", "0", "2", "7"))
    planted = 'A = "%s"\nB = "%s"\n# %s\nC = "%s"\nD = "%s"\n' % (v4, net, bad, v6, doc)
    got = {(tok, cls) for _where, tok, cls in _literals("plant.py", planted)}
    assert got == {(v4, None), (net, None), (bad, "UNKNOWN FORM"), (v6, None),
                   (doc, "special-purpose")}, got
    # Holder H5: every form the lane's files hold, both families, each with
    # its line: a Python comment, a longer string, an f-string part, an SQL
    # line and comment, a JSON value; a slice in code is not an address.
    step = ":" * 2 + "2"   # a slice step, built so that this file's own strings hold no such token
    forms = {
        "plant.py": ('x = [1, 2][%s]\n# resolver %s and %s\nE = "seen at %s today"\n'
                     'F = f"{x} from %s"\n' % (step, v4, v6, v6, v6), {(2, v4), (2, v6), (3, v6), (4, v6)}),
        "plant.sql": ("-- the lender %s\nSELECT '%s'::inet;\nSELECT '%s';\n" % (v6, v6, v4),
                      {(1, v6), (2, v6), (3, v4)}),
        "plant.json": ('{"a": "%s", "b": ["%s"]}\n' % (v6, v4), {(1, v6), (1, v4)}),
    }
    for name, (src, want) in forms.items():
        got = _literals(name, src)
        assert {(int(w.rsplit(":", 1)[1]), t) for w, t, _c in got} == want, (name, got)
        assert all(c is None for _w, _t, c in got), (name, got)


def _mains_alt_plants(src, v4):
    """(place, copy of `src` with `v4` planted there, whether the scan must
    read it) for each place test_the_literal_scan_reads_mains_alt_code
    plants in; each anchor stands once in `src`."""
    def at(anchor, planted):
        assert src.count(anchor) == 1, anchor
        return src.replace(anchor, planted, 1)
    seen = "# seen at %s\n" % v4
    boot = "\ndef _alt_boot() -> None:\n"
    rel = "\nasync def alt_relations(db: AsyncSession, steam_id: str, days: int = None) -> dict:\n"
    sql = "\n_ALT_RELATION_SQL = (\n"
    cls = "\nclass _AltNotRecorded(Exception):\n"
    faq = "\n_ALT_FAQ_CHANNEL = "
    health = "\nasync def health_check(db: AsyncSession = Depends(get_db)):\n"
    return (("inside _alt_boot", at(boot, boot + "    " + seen), True),
            ("a comment line inside alt_relations", at(rel, rel + "    " + seen), True),
            ("the text of _ALT_RELATION_SQL", at(sql, sql + '    " /* seen at %s */"\n' % v4), True),
            ("a comment line inside _AltNotRecorded", at(cls, cls + "    " + seen), True),
            ("a comment line directly above _ALT_FAQ_CHANNEL", at(faq, "\n" + seen + faq[1:]), True),
            ("the file's first line", seen + src, False),
            ("a comment line inside health_check", at(health, health + "    " + seen), False))


def test_the_literal_scan_reads_mains_alt_code():
    """A public address planted in a copy of main.py's text is found by
    _main_alt_texts(copy) and refused in each lane statement it is planted
    in: inside _alt_boot, in a comment line inside alt_relations, inside the
    string _ALT_RELATION_SQL holds, in a comment line inside _AltNotRecorded,
    and in a comment line directly above _ALT_FAQ_CHANNEL (read with the
    statement below it). Planted as the file's first line, or in a comment
    line inside health_check (a statement named otherwise: E2's LIMIT), it
    is not read. Each anchor stands once in main.py."""
    v4 = ".".join(("1", "1", "2", "1"))
    src = (BACKEND / "api" / "main.py").read_text(encoding="utf-8")

    def scan(copy):
        return [(t, c) for _n, _l, text_ in _main_alt_texts(copy) for _w, t, c in _literals("main.py", text_)]
    for place, copy, read in _mains_alt_plants(src, v4):
        got = scan(copy)
        if read:
            assert (v4, None) in got, (place, [x for x in got if x[1] is None])
        else:
            assert all(t != v4 for t, _c in got), place
