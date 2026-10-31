"""The shop and artist 409 refusals that carry no machine code reach the
player translated, and so do the tournament bracket and list surfaces.

The server sends six refusals as plain English 409 details with no machine
code: the per-item client floor (migration 397) from the shop purchase route
and the artist gift route, the music album floor and the approved-but-not-
shipped cosmetic from the purchase route, and the not-yet-shipped cosmetic
from the artist gift and set-stock routes. The client recognises each by its
status and exact words in NativeUI.TrShopRefusal, the same way it recognises
the price_changed 409, and shows the catalogue row instead of the raw body.

The same lane routes the tournament bracket's "BYE" / "TBD" labels, the time
slot's "(TBD)", and the tournament page's status, deadline, countdown, room
code, signup placement and in-game indicator text through the catalogue, and
adds the live shop names "Straw Hat", "FloraBelle", "Red mouth", "Soft eyes"
and "Clavar la Bala" to the shop snapshot the extractor registers.

These tests read source only (no build, no database). They fail if the server
rewords a detail without the client following, if the helper stops matching
or translating one, if a purchase, gift or set-stock failure site stops
routing its answer through the helper, if a bracket, slot or tournament label
goes back to a raw literal, if the snapshot loses a name, or if a bundled
catalogue loses a row.
"""
import ast
import io
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]

G1 = "This item requires a newer mod version"
G2 = ("This item requires a newer mod version than the recipient has used; "
      "they need to update the mod first")
ALBUM = "This album requires a newer mod version"
UNSHIPPED_BUY = "This cosmetic is approved but has not shipped in the mod yet"
UNSHIPPED_GIFT = "This cosmetic has not shipped in the mod yet and cannot be gifted"
UNSHIPPED_STOCK = "This cosmetic has not shipped in the mod yet; stock stays closed until it does"

# detail -> the main.py route function that raises it as a 409
REFUSALS = {G1: "purchase_item", G2: "artist_gift", ALBUM: "purchase_item",
            UNSHIPPED_BUY: "purchase_item", UNSHIPPED_GIFT: "artist_gift",
            UNSHIPPED_STOCK: "artist_set_stock"}


def _read(rel):
    return io.open(str(ROOT / rel), encoding="utf-8").read()


def _server_409_details():
    """{function name: [detail constants of every HTTPException(409, ...)]}."""
    tree = ast.parse(_read("backend/api/main.py"))
    out = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "HTTPException"):
                continue
            kw = {k.arg: k.value for k in node.keywords}
            code = kw.get("status_code")
            detail = kw.get("detail")
            if (isinstance(code, ast.Constant) and code.value == 409
                    and isinstance(detail, ast.Constant) and isinstance(detail.value, str)):
                out.setdefault(fn.name, []).append(detail.value)
    return out


def _member(src, signature):
    """The body of the C# member whose declaration line contains signature,
    by brace matching from the first '{' after it."""
    i = src.index(signature)
    assert src.count(signature) == 1, signature
    b = src.index("{", i)
    depth = 0
    for j in range(b, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[b:j + 1]
    raise AssertionError("unbalanced member " + signature)


def _helper():
    return _member(_read("plugin/NativeUI.cs"), "internal static string TrShopRefusal(string resp)")


def test_server_still_sends_every_detail_as_409():
    details = _server_409_details()
    for s, fn in REFUSALS.items():
        assert s in details.get(fn, []), (fn, s, details.get(fn))


def test_helper_matches_each_detail_and_returns_its_catalogue_row():
    body = _helper()
    assert 'resp.StartsWith("HTTP 409", StringComparison.Ordinal)' in body
    assert "string detail = ExtractServerDetail(resp);" in body
    assert body.count("if (detail == ") == len(REFUSALS)
    for s in REFUSALS:
        lit = '"%s"' % s
        assert body.count('if (detail == %s)' % lit) == 1, s
        assert body.count('return I18n.Tr(%s);' % lit) == 1, s
        # the Tr follows its own comparison, not another one's
        cmp_at = body.index('if (detail == %s)' % lit)
        tr_at = body.index('return I18n.Tr(%s);' % lit)
        assert 0 < tr_at - cmp_at < len(lit) + 40, s


def test_every_purchase_gift_and_stock_failure_routes_through_the_helper():
    native = _read("plugin/NativeUI.cs")
    ladders = _read("plugin/TitleLaddersUI.cs")
    frame = 'I18n.TrF("<color=#FF8888>Purchase failed: {0}</color>", '
    assert native.count(frame + "TrShopRefusal(resp) ?? resp)") == 1
    assert native.count(frame) == 1, "a Shop purchase failure site does not use the helper"
    assert ladders.count(frame + "NativeUI.TrShopRefusal(resp) ?? resp)") == 1
    assert ladders.count(frame) == 1, "a ladder purchase failure site does not use the helper"
    # every client purchase goes through one of those two callbacks
    assert len(re.findall(r"ApiClient\.PurchaseItem\(", native)) == 2
    assert len(re.findall(r"ApiClient\.PurchaseItem\(", ladders)) == 1
    show = _member(native, "private static void ShowArtistResult(bool ok, string msg)")
    assert "string known = ok ? null : TrShopRefusal(msg);" in show
    assert 'known != null ? I18n.TrF("Failed: {0}", known)' in show
    # the gift and set-stock answers reach ShowArtistResult unchanged on failure
    for call in ("ArtistGift", "ArtistSetStock"):
        sites = re.findall(r"ApiClient\.%s\(" % call, native)
        assert len(sites) == 1, call
        assert re.search(r"ApiClient\.%s\([^;]*ShowArtistResult\(ok, ok \? [^;]* : resp\)\)" % call, native, re.S), call


# -- the tournament surfaces --------------------------------------------------

# keys this lane added that a tournament site shows through I18n.Tr / TrF
TOURNAMENT_KEYS = [
    "Reconnecting to {0} (region {1})", "default",
    " starts in <color=#FFDE88>{0}:{1:00}</color>",
    "  <color=#7FE8C3>(Play Now sent - waiting on opponent)</color>",
    "  <color=#888>(both press Play Now to skip the break)</color>",
    "Next match (R{0}{1}): vs <color=#FFDE88>{2}</color> -{3}{4}",
    "<color=#60FF80>both ready - connecting...</color>",
    "<color=#FFD94D>waiting on opponent to ready</color>",
    "<color=#FF9060>press Ready Up</color>",
    "Tournament match starting vs {0}",
    "Room code: <color=#C0E0FF>{0}</color>{1}  <color=#888>(if auto-connect fails, "
    "Reconnect or join via Private Lobby)</color>",
    "<color=#FFD850>1st</color>", "<color=#C0C0C0>2nd</color>", "<color=#CD7F32>3rd</color>",
    "<color=#FFD850>CHAMPION</color>", "<color=#FF6060>FORFEIT</color>",
    "<color=#60FF60>ready</color>",
    "<i>Bracket revealed when the tournament starts ({0}).</i>",
    "<color=#FFD94D>{0}/{1}</color> <color=#888>({2} live)</color>",
    "forfeit", "double forfeit",
    "<color=#FFD94D>* {0} TOURNAMENT GAME - vs {1}  (results auto-recorded)</color>",
    "SYNC", "ASYNC",
]
# existing keys the tournament sites now reuse
REUSED_KEYS = [
    "vs {0}", " 3rd Place", "opponent",
    "Your match (R{0}{1}): vs <color=#FFDE88>{2}</color>",
    "<color=#FFAA44>deadline: {0}d {1}h left</color>",
    "<color=#FF6060>deadline: {0}h {1}m left</color>",
    "<color=#FF4040>deadline passed</color>",
]


def test_every_tournament_key_is_shown_through_the_catalogue():
    native = _read("plugin/NativeUI.cs")
    for s in TOURNAMENT_KEYS:
        lit = '"%s"' % s
        # each new key has exactly one site, so losing its Tr loses the count
        n = native.count("I18n.Tr(%s)" % lit) + native.count("I18n.TrF(%s," % lit)
        assert n == 1, (s, n)


def test_the_tournament_sites_that_reuse_existing_keys_keep_them():
    native = _read("plugin/NativeUI.cs")
    sites = [
        # the async next-match line and the sync my-match line
        r'I18n\.TrF\("Next match \(R\{0\}\{1\}\): vs <color=#FFDE88>\{2\}</color> -\{3\}\{4\}",\s+'
        r'm\.round, m\.bracket_side == "TP" \? I18n\.Tr\(" 3rd Place"\) : "",\s+'
        r'opp2 \?\? "\?", cdown, earlyState\);',
        r'I18n\.TrF\("Your match \(R\{0\}\{1\}\): vs <color=#FFDE88>\{2\}</color>",\s+'
        r'm\.round, m\.bracket_side == "TP" \? I18n\.Tr\(" 3rd Place"\) : "",\s+'
        r'opp \?\? "\?"\)\s+\+ "  -  " \+ readyState;',
        # the in-game indicator's opponent fallback
        r'kindTag, m\.opponent_display_name \?\? I18n\.Tr\("opponent"\)\)\);',
        # the bracket list row's deadline tails
        r'deadlineLine = remaining\.TotalDays >= 1\s+'
        r'\? "   " \+ I18n\.TrF\("<color=#FFAA44>deadline: \{0\}d \{1\}h left</color>", '
        r'\(int\)remaining\.TotalDays, remaining\.Hours\)\s+'
        r': "   " \+ I18n\.TrF\("<color=#FF6060>deadline: \{0\}h \{1\}m left</color>", '
        r'remaining\.Hours, remaining\.Minutes\);',
    ]
    for pat in sites:
        assert len(re.findall(pat, native)) == 1, pat


def test_the_bracket_list_row_status_and_deadline_are_translated():
    native = _read("plugin/NativeUI.cs")
    assert native.count('UIFactory.SetText(txt, "        " + p1 + "  " + I18n.TrF("vs {0}", p2) + scoreLine + deadlineLine);') == 1
    assert native.count('m.status == "forfeit" ? I18n.Tr("forfeit")') == 1
    assert native.count('m.status == "double_forfeit" ? I18n.Tr("double forfeit")') == 1
    assert native.count('else deadlineLine = "   " + I18n.Tr("<color=#FF4040>deadline passed</color>");') == 1


# raw tournament-surface literals this lane replaced; none may come back
RAW_TOURNAMENT_LITERALS = [
    '$"        {p1}  vs  {p2}',
    '$" ({m.status.Replace',
    '$"   <color=#FFAA44>deadline:',
    '$"   <color=#FF6060>deadline:',
    '"   <color=#FF4040>deadline passed</color>"',
    '$"Reconnecting to ',
    '$" starts in ',
    '$"Next match (R',
    '$"Your match (R',
    '$"Tournament match starting vs ',
    '$"Room code: ',
    '$"<i>Bracket revealed',
    '$"<color=#FFD94D>{completed}/',
    'TOURNAMENT GAME - vs {m.',
    'status = "<color=',
    ': "  <color=#888>(both press Play Now',
    '? "<color=#60FF80>both ready',
    ': "<color=#FFD94D>waiting on opponent',
    ': "<color=#FF9060>press Ready Up',
]


def test_no_replaced_tournament_literal_is_left():
    native = _read("plugin/NativeUI.cs")
    left = [s for s in RAW_TOURNAMENT_LITERALS if s in native]
    assert not left, left


# Keys this lane added, and whether the row may equal the English: FloraBelle
# and the album title Clavar la Bala are proper names and are kept as-is in
# every catalogue (the convention the "Pumpking Hat" rows follow); SYNC and
# ASYNC keep the English mode names the "Sync (weekly)" rows keep; every other
# row must be a real translation.
LANE_KEYS = dict({s: False for s in REFUSALS},
                 **{"BYE": False, "TBD": False, "(TBD)": False,
                    "Straw Hat": False, "FloraBelle": True,
                    "Red mouth": False, "Soft eyes": False, "Clavar la Bala": True})
LANE_KEYS.update({s: s in ("SYNC", "ASYNC") for s in TOURNAMENT_KEYS})


def _catalogue_blocks():
    cs = _read("plugin/I18nCatalogues.cs")
    blocks = cs.split("private static readonly Dictionary<string, string> ")[1:]
    assert [b[:2] for b in blocks] == ["ES", "RU", "UK", "SV"]
    return [(b[:2], b[:b.index("\n        };")]) for b in blocks]


def _rows(body, s):
    return re.findall(r'^\s+\["%s"\] = "((?:[^"\\]|\\.)*)",$' % re.escape(s), body, re.M)


def test_every_lane_key_ships_in_every_bundled_catalogue():
    for lang, body in _catalogue_blocks():
        for s, identity_ok in LANE_KEYS.items():
            rows = _rows(body, s)
            assert len(rows) == 1, (lang, s)
            assert rows[0] and (identity_ok or rows[0] != s), (lang, s)
        for s in REUSED_KEYS:
            assert len(_rows(body, s)) == 1, (lang, s)
    keys = _read("plugin/I18nSourceKeys.g.cs")
    for s in list(LANE_KEYS) + REUSED_KEYS:
        assert keys.count('"%s",' % s) == 1, s


# -- the bracket's BYE / TBD labels and the slot's (TBD) ----------------------

def test_bracket_labels_go_through_the_catalogue():
    native = _read("plugin/NativeUI.cs")
    pair = '(m.is_bye ? I18n.Tr("BYE") : I18n.Tr("TBD"))'
    for n in ("1", "2"):
        # The graphical bracket keeps its blankNames "?" path unchanged. The
        # fence lane wraps the same fallback in its fully-vacant-bye dash,
        # (vacantBye ? "-" : <pair>); either form must route BYE/TBD through
        # the catalogue, and exactly one p<n>Name declaration may exist.
        plain = 'string p%sName = blankNames ? "?" : (m.p%s_display_name ?? %s);' % (n, n, pair)
        fenced = ('string p%sName = blankNames ? "?" : (m.p%s_display_name ?? (vacantBye ? "-" : %s));'
                  % (n, n, pair))
        assert native.count(plain) + native.count(fenced) == 1, n
        assert native.count("string p%sName = " % n) == 1, n
        # the list bracket
        assert native.count('string p%s = m.p%s_display_name ?? %s;' % (n, n, pair)) == 1
    slot = _member(native, "private static string _FmtSlot(string iso, bool includeTz = true)")
    assert 'if (string.IsNullOrEmpty(iso)) return I18n.Tr("(TBD)");' in slot


def test_no_raw_bye_or_tbd_display_literal_is_left_in_the_plugin():
    raw = re.compile(r'(?<!I18n\.Tr\()"\(?(?:BYE|TBD)\)?"')
    left = []
    for path in sorted((ROOT / "plugin").rglob("*.cs")):
        if path.name in ("I18nCatalogues.cs", "I18nSourceKeys.g.cs"):
            continue
        for k, line in enumerate(io.open(str(path), encoding="utf-8").read().splitlines(), 1):
            if line.lstrip().startswith("//"):
                continue
            if raw.search(line):
                left.append("%s:%d %s" % (path.name, k, line.strip()[:100]))
    assert not left, left


# -- the shop names -----------------------------------------------------------

def test_the_shop_snapshot_carries_every_lane_name():
    import json
    snap = json.loads(_read("tools/shop_strings.json"))["strings"]
    assert snap == sorted(snap)
    for s in ("Straw Hat", "FloraBelle", "Red mouth", "Soft eyes", "Clavar la Bala"):
        assert snap.count(s) == 1, s
