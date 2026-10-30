"""The per-item client floor refusals (migration 397) reach the player
translated.

The server sends both refusals as plain English 409 details with no machine
code: "This item requires a newer mod version" from the shop purchase route,
and "... than the recipient has used; they need to update the mod first" from
the artist gift route. The client recognises each by its status and exact
words in NativeUI.TrItemFloorRefusal, the same way it recognises the
price_changed 409, and shows the catalogue row instead of the raw body.

The same lane routes the tournament bracket's "BYE" / "TBD" labels and the
time slot's "(TBD)" through the catalogue, and adds the shop names "Straw Hat"
and "FloraBelle" to the shop snapshot the extractor registers.

These tests read source only (no build, no database). They fail if the server
rewords either detail without the client following, if the helper stops
matching or translating either one, if any purchase or gift failure site stops
routing its answer through the helper, if a bracket or slot label goes back to
a raw literal, if the snapshot loses a name, or if a bundled catalogue loses a
row.
"""
import ast
import io
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]

G1 = "This item requires a newer mod version"
G2 = ("This item requires a newer mod version than the recipient has used; "
      "they need to update the mod first")


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
    return _member(_read("plugin/NativeUI.cs"), "internal static string TrItemFloorRefusal(string resp)")


def test_server_still_sends_both_details_as_409():
    details = _server_409_details()
    assert G1 in details.get("purchase_item", []), details.get("purchase_item")
    assert G2 in details.get("artist_gift", []), details.get("artist_gift")


def test_helper_matches_each_detail_and_returns_its_catalogue_row():
    body = _helper()
    assert 'resp.StartsWith("HTTP 409", StringComparison.Ordinal)' in body
    assert "string detail = ExtractServerDetail(resp);" in body
    for s in (G1, G2):
        lit = '"%s"' % s
        assert body.count('if (detail == %s)' % lit) == 1, s
        assert body.count('return I18n.Tr(%s);' % lit) == 1, s
        # the Tr follows its own comparison, not the other one's
        cmp_at = body.index('if (detail == %s)' % lit)
        tr_at = body.index('return I18n.Tr(%s);' % lit)
        assert 0 < tr_at - cmp_at < len(lit) + 40, s


def test_every_purchase_and_gift_failure_routes_through_the_helper():
    native = _read("plugin/NativeUI.cs")
    ladders = _read("plugin/TitleLaddersUI.cs")
    frame = 'I18n.TrF("<color=#FF8888>Purchase failed: {0}</color>", '
    assert native.count(frame + "TrItemFloorRefusal(resp) ?? resp)") == 1
    assert native.count(frame) == 1, "a Shop purchase failure site does not use the helper"
    assert ladders.count(frame + "NativeUI.TrItemFloorRefusal(resp) ?? resp)") == 1
    assert ladders.count(frame) == 1, "a ladder purchase failure site does not use the helper"
    show = _member(native, "private static void ShowArtistResult(bool ok, string msg)")
    assert "string floor = ok ? null : TrItemFloorRefusal(msg);" in show
    assert 'floor != null ? I18n.TrF("Failed: {0}", floor)' in show
    # the gift answer reaches ShowArtistResult unchanged on failure
    assert re.search(r"ApiClient\.ArtistGift\([^;]*ShowArtistResult\(ok, ok \? [^;]* : resp\)\)", native, re.S)


# Keys this lane added, and whether the row may equal the English: FloraBelle
# is a proper name and is kept as-is in every catalogue (the convention the
# "Pumpking Hat" rows follow); every other row must be a real translation.
LANE_KEYS = {G1: False, G2: False, "BYE": False, "TBD": False, "(TBD)": False,
             "Straw Hat": False, "FloraBelle": True}


def test_every_lane_key_ships_in_every_bundled_catalogue():
    cs = _read("plugin/I18nCatalogues.cs")
    blocks = cs.split("private static readonly Dictionary<string, string> ")[1:]
    assert [b[:2] for b in blocks] == ["ES", "RU", "UK", "SV"]
    for b in blocks:
        body = b[:b.index("\n        };")]
        for s, identity_ok in LANE_KEYS.items():
            rows = re.findall(r'^\s+\["%s"\] = "((?:[^"\\]|\\.)*)",$' % re.escape(s), body, re.M)
            assert len(rows) == 1, (b[:2], s)
            assert rows[0] and (identity_ok or rows[0] != s), (b[:2], s)
    keys = _read("plugin/I18nSourceKeys.g.cs")
    for s in LANE_KEYS:
        assert keys.count('"%s",' % s) == 1, s


# -- the bracket's BYE / TBD labels and the slot's (TBD) ----------------------

def test_bracket_labels_go_through_the_catalogue():
    native = _read("plugin/NativeUI.cs")
    pair = '(m.is_bye ? I18n.Tr("BYE") : I18n.Tr("TBD"))'
    for n in ("1", "2"):
        # the graphical bracket keeps its blankNames "?" path unchanged
        assert native.count('string p%sName = blankNames ? "?" : (m.p%s_display_name ?? %s);' % (n, n, pair)) == 1
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


# -- the two shop names -------------------------------------------------------

def test_the_shop_snapshot_carries_both_names():
    import json
    snap = json.loads(_read("tools/shop_strings.json"))["strings"]
    assert snap == sorted(snap)
    for s in ("Straw Hat", "FloraBelle"):
        assert snap.count(s) == 1, s
