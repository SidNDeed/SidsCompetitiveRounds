"""Every refusal a shop or artist action can reach, and every tournament and
series label the server composes, reaches the player through the catalogue.

Refusals. The client shows a refusal on the shop's purchase line, the title
ladders' purchase line and the artist screen's notification (ShowArtistResult).
DISPLAY lists every ApiClient method whose answer reaches one of those, with
each (verb, path) it requests; the test checks the list against ApiClient.cs
(every method of the shop/artist family is listed or exempted with a reason,
every listed path is requested by that method with that verb, and a GET keeps
the refusal body), then maps each path to its main.py route. From those
routes it enumerates every answer the server can send:

  * each HTTPException the routes and the module functions they call raise,
    and every ValueError an `except ValueError as ve` handler forwards;
  * every JSONResponse the app middleware (and the functions it calls)
    answers with: a detail sentence, or an error code alone;
  * for a listed GET, every refusal backend/api/read_gate.py can raise (a
    superset of what one route class reaches).

plugin/ServerTextRules.cs must map each: a detail by an exact row whose key
IS the detail (so English shows the server's own text), a composed detail
by a template whose holes are parsed narrowly, an object detail by its
detail.error, a middleware code by its error. Nothing returns English the
server never sent (test_no_added_english). A gap fails
test_every_reachable_refusal_is_mapped, a row the server no longer sends
fails test_no_mapping_is_stale, and the planted controls prove both can fail.

Labels. backend/api/tournaments.py composes the signup list's progress
label and the recent-tournaments popup's result label, main.py the in-game
tournament banner from _round_label and the Recent Series FFA labels
("N-player FFA", "#1 of N"). Each finite set goes through a key; each
parameterized label through I18n.TrF; all before markup is composed. Admin
rows show raw status words by design and are pinned as such.

Source only: no build, no database.
"""
import ast
import functools
import io
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]


@functools.lru_cache(maxsize=None)
def _read(rel):
    return io.open(str(ROOT / rel), encoding="utf-8").read()


def _member(src, signature):
    """The body of the C# member whose declaration contains signature."""
    assert src.count(signature) == 1, signature
    b = src.index("{", src.index(signature))
    depth = 0
    for j in range(b, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[b:j + 1]
    raise AssertionError("unbalanced member " + signature)


def _str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _fstring_variants(node, hole=None):
    """Skeletons of an f-string. Each interpolation becomes the next {k},
    unless hole(expr) returns a list of strings to splice in instead; an
    interpolation that chooses between two string constants splices both."""
    variants = [("", 0)]
    for v in node.values:
        if isinstance(v, ast.Constant):
            variants = [(s + v.value, k) for s, k in variants]
            continue
        e = v.value
        fixed = hole(e) if hole else None
        if fixed is None and isinstance(e, ast.IfExp) and _str(e.body) is not None and _str(e.orelse) is not None:
            fixed = [e.body.value, e.orelse.value]
        if fixed is not None:
            variants = [(s + f, k) for s, k in variants for f in fixed]
        else:
            variants = [(s + "{%d}" % k, k + 1) for s, k in variants]
    return [s for s, _ in variants]


@functools.lru_cache(maxsize=None)
def _module(rel):
    tree = ast.parse(_read(rel))
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _closure(funcs, roots):
    seen, stack = [], list(roots)
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.append(n)
        for node in ast.walk(funcs[n]):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in funcs:
                stack.append(node.func.id)
    return seen


# -- which routes a shown refusal can come from -------------------------------

API = "plugin/ApiClient.cs"
RULES = "plugin/ServerTextRules.cs"

# Every ApiClient method whose refusal reaches a player surface that maps it
# (ShowArtistResult, the shop row's and the title ladders' purchase lines),
# with every (verb, path) the method requests.
DISPLAY = {
    "PurchaseItem": [("post", "/api/v1/shop/purchase")],
    "ArtistBlock": [("post", "/api/v1/artist/block")],
    "ArtistGift": [("post", "/api/v1/artist/gift")],
    "ArtistSetDesc": [("post", "/api/v1/artist/set-desc")],
    "ArtistSetName": [("post", "/api/v1/artist/set-name")],
    "ArtistSetPrice": [("post", "/api/v1/artist/set-price")],
    "ArtistSetStock": [("post", "/api/v1/artist/set-stock")],
    "ArtistStartCatalogPlacementRevision": [("post", "/api/v1/artist/catalog-cosmetic-placement")],
    "ArtistSubmitCosmetic": [("post", "/api/v1/artist/submit-cosmetic")],
    "ArtistSubmitCosmeticAnimated": [("post", "/api/v1/artist/submit-cosmetic"),
                                     ("post", "/api/v1/artist/submit-cosmetic-frame"),
                                     ("post", "/api/v1/artist/submit-cosmetic-finalize")],
    "ArtistSubmitCosmeticGif": [("post", "/api/v1/artist/submit-cosmetic-gif")],
    "ArtistUpdateCosmeticPlacement": [("post", "/api/v1/artist/cosmetic-placement")],
    "FetchCosmeticSubmissionPreview": [("get", "/api/v1/artist/cosmetic-preview")],
}
# The rest of the shop/artist family, and why no player sees their refusal.
NOT_DISPLAYED = {
    "FetchArtistItems": "the artist screen's list loader: a failure is logged and the last list kept",
    "FetchArtistSales": "the artist screen's sales loader: a failure is logged and the last list kept",
    "FetchArtistsList": "an admin-only surface (admin rows show raw server text by design)",
    "FetchCosmeticFrames": "the admin cosmetic review's frame loader: a failure ends the sequence, logged",
    "FetchCosmeticSubmissionsAdmin": "an admin-only surface (the cosmetic review queue)",
    "FetchCosmeticReleaseCandidatesAdmin": "an admin-only surface (the release candidates list)",
}
FAMILY_RE = re.compile(r"public static \w+ ((?:Artist|FetchArtist|FetchCosmetic|Purchase)\w*)\(")


def _api_method(name):
    """The method's body plus the body of every coroutine it starts in
    ApiClient (an upload's frames are posted by its own coroutine)."""
    api = _read(API)
    sigs = re.findall(r"public static \w+ %s\(" % re.escape(name), api)
    assert len(sigs) == 1, (name, sigs)
    body = _member(api, sigs[0])
    for co in sorted(set(re.findall(r"StartCoroutine\((\w+)\(", body))):
        if co in ("GetRequest", "PostRequest", "PostRequestWithRetry"):
            continue
        body += _member(api, "private static IEnumerator %s(" % co)
    return body


def _route_for(funcs, verb, path):
    hits = [n for n, f in funcs.items()
            for d in f.decorator_list
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == verb
            and d.args and _str(d.args[0]) == path]
    assert len(hits) == 1, (verb, path, hits)
    return hits[0]


def display_routes(funcs=None, display=None):
    funcs = funcs or _module("backend/api/main.py")
    out = set()
    for m, reqs in (display or DISPLAY).items():
        body = _api_method(m)
        for verb, path in reqs:
            assert re.search(r'\{baseUrl\}%s["?]' % re.escape(path), body), (m, path)
            helper = "GetRequest(" if verb == "get" else "PostRequest"
            assert helper in body, (m, verb)
            out.add(_route_for(funcs, verb, path))
    return sorted(out)


def shop_routes(funcs):
    """The round-1 enumeration (mutating purchase_item and artist_* routes),
    kept as a floor the derived set must cover."""
    return sorted(n for n, f in funcs.items()
                  if (n == "purchase_item" or n.startswith("artist_"))
                  and any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                          and d.func.attr in ("post", "put", "patch", "delete")
                          for d in f.decorator_list))


def _value_errors(funcs, names):
    out = set()
    for n in _closure(funcs, names):
        for node in ast.walk(funcs[n]):
            if (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
                    and getattr(node.exc.func, "id", None) == "ValueError" and node.exc.args):
                a = node.exc.args[0]
                if _str(a) is not None:
                    out.add(a.value)
                elif isinstance(a, ast.JoinedStr):
                    out.update(_fstring_variants(a))
                else:
                    raise AssertionError("unclassified ValueError at main.py:%d" % node.lineno)
    return out


def _kind(text):
    return "template" if re.search(r"\{\d\}", text) else "exact"


def route_refusals(funcs, routes):
    """{(status, kind, text)} the routes and their callees raise; kind is
    exact, template or dict."""
    items = set()
    for n in _closure(funcs, routes):
        fn = funcs[n]
        forwarded = {}   # id(HTTPException call) -> (variable, ValueError family)
        for t in ast.walk(fn):
            if not isinstance(t, ast.Try):
                continue
            called = {c.func.id for b in t.body for c in ast.walk(b)
                      if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in funcs}
            for h in t.handlers:
                if not h.name:
                    continue
                family = (_value_errors(funcs, called)
                          if isinstance(h.type, ast.Name) and h.type.id == "ValueError" else set())
                for b in h.body:
                    for c in ast.walk(b):
                        if isinstance(c, ast.Call) and getattr(c.func, "id", None) == "HTTPException":
                            forwarded[id(c)] = (h.name, family)
        for c in ast.walk(fn):
            if not (isinstance(c, ast.Call) and getattr(c.func, "id", None) == "HTTPException"):
                continue
            kw = {k.arg: k.value for k in c.keywords}
            code = kw.get("status_code", c.args[0] if c.args else None)
            det = kw.get("detail", c.args[1] if len(c.args) > 1 else None)
            assert isinstance(code, ast.Constant), "status at main.py:%d" % c.lineno
            status = code.value
            var, family = forwarded.get(id(c), (None, set()))
            uses_var = var is not None and any(isinstance(x, ast.Name) and x.id == var for x in ast.walk(det))
            if _str(det) is not None:
                items.add((status, "exact", det.value))
            elif isinstance(det, ast.JoinedStr):
                for s in _fstring_variants(det):
                    items.add((status, _kind(s), s))
            elif isinstance(det, ast.Dict):
                keys = [_str(k) for k in det.keys]
                items.add((status, "dict", det.values[keys.index("error")].value))
            elif not (uses_var and isinstance(det, ast.Call) and getattr(det.func, "id", None) == "str"):
                raise AssertionError("unclassified detail at main.py:%d" % c.lineno)
            if uses_var:
                for s in family:
                    items.add((status, _kind(s), s))
    return items


def middleware_refusals(funcs=None):
    """{(status, kind, text)} every JSONResponse the app middleware and the
    functions it calls answer with: kind exact (a detail sentence, which the
    client reads first), error (an error code alone) or sentinel (the version
    gate's "outdated", which the request helpers answer themselves)."""
    funcs = funcs or _module("backend/api/main.py")
    mw = [n for n, f in funcs.items()
          if any(isinstance(d, ast.Call) and getattr(d.func, "attr", None) == "middleware" for d in f.decorator_list)]
    items = set()
    for n in _closure(funcs, mw):
        for c in ast.walk(funcs[n]):
            if not (isinstance(c, ast.Call) and getattr(c.func, "id", None) == "JSONResponse"):
                continue
            kw = {k.arg: k.value for k in c.keywords}
            assert isinstance(kw.get("status_code"), ast.Constant), "middleware status at main.py:%d" % c.lineno
            status = kw["status_code"].value
            content = kw.get("content")
            assert isinstance(content, ast.Dict), "middleware body at main.py:%d" % c.lineno
            body = {_str(k): v for k, v in zip(content.keys, content.values)}
            if _str(body.get("detail")) is not None:
                items.add((status, "exact", body["detail"].value))
            elif _str(body.get("error")) == "outdated" and status == 426:
                items.add((status, "sentinel", "outdated"))
            else:
                assert _str(body.get("error")) is not None, "middleware answer without a code at main.py:%d" % c.lineno
                items.add((status, "error", body["error"].value))
    return items


def read_gate_refusals():
    tree = ast.parse(_read("backend/api/read_gate.py"))
    items = set()
    for c in ast.walk(tree):
        if isinstance(c, ast.Call) and getattr(c.func, "id", None) == "_refuse":
            assert isinstance(c.args[0], ast.Constant) and _str(c.args[1]) is not None, \
                "read_gate.py:%d" % c.lineno
            items.add((c.args[0].value, "exact", c.args[1].value))
    return items


def server_refusals(funcs=None):
    funcs = funcs or _module("backend/api/main.py")
    items = route_refusals(funcs, display_routes(funcs)) | middleware_refusals(funcs)
    if any(v == "get" for reqs in DISPLAY.values() for v, _ in reqs):
        items |= read_gate_refusals()
    return items


# -- client side: plugin/ServerTextRules.cs -----------------------------------

_LIT = r'"((?:[^"\\]|\\.)*)"'
TEMPLATE_RE = re.compile(r'if \(status == (\d{3}) && RefusalTemplate\(d, %s, (true|false), out a\)\)\s*'
                         r'return I18n\.TrF\(%s, [^;]*\);' % (_LIT, _LIT))
ROW_RE = re.compile(r'if \(k == "(\d{3})\|((?:[^"\\]|\\.)*)"\) return I18n\.Tr\(%s\);' % _LIT)


def _rows_of(body):
    rows = ROW_RE.findall(body)
    assert body.count('if (k == "') == len(rows), "a mapping line the parser does not read"
    return rows


def client_refusals(rules=None):
    rules = rules or _read(RULES)
    body = _member(rules, "private static string TrRefusalDetail(int status, string d)")
    exact = _rows_of(body)
    for s, d, k in exact:
        assert d == k, ("an exact row returns another key", s, d, k)
    templates = TEMPLATE_RE.findall(body)
    for s, t, text, key in templates:
        assert key == t, ("a template returns another key", t, key)
        holes = re.findall(r"\{(\d)\}", t)
        assert holes == [str(i) for i in range(len(holes))], ("holes out of order", t)
    assert body.count("RefusalTemplate(") == len(templates), "a template line the parser does not read"
    assert "case " not in body and "Refused(" not in rules and "ProtocolAnswers" not in rules
    obj = _rows_of(_member(rules, "private static string TrRefusalObject(int status, string code)"))
    mw = _rows_of(_member(rules, "private static string TrMiddleware(int status, string code)"))
    for s, c, k in mw:
        assert c == k, ("a middleware row returns another key", s, c, k)
    return {
        "exact": {(int(s), d) for s, d, _ in exact},
        "templates": {(int(s), t): text == "true" for s, t, text, _ in templates},
        "dict": {(int(s), c) for s, c, _ in obj},
        "error": {(int(s), c) for s, c, _ in mw},
        "body": body,
        "keys": {k for _, _, k in exact + obj + mw} | {t for _, t, _, _ in templates},
    }


# price_changed is answered by both purchase callbacks (ApiClient's sentinel)
# before they call the map; every other object detail is mapped in the rules.
SENTINEL_DICT = {(409, "price_changed")}

# Templates whose hole carries an exception's or a chunk's text, not a number.
TEXT_HOLES = {
    "bad frame PNG: {0}",
    "Published cosmetic source must be a transparent 512x512 PNG ({0})",
    "could not process GIF: {0}",
    "unreadable PNG: {0}",
    "malformed PNG (bad CRC on {0} chunk)",
}


def coverage_gaps(server, client):
    gaps = []
    for status, kind, text in sorted(server):
        if kind == "dict":
            ok = (status, text) in client["dict"] | SENTINEL_DICT
        elif kind == "exact":
            ok = (status, text) in client["exact"]
        elif kind == "error":
            ok = (status, text) in client["error"]
        elif kind == "sentinel":
            ok = True
        else:
            ok = (status, text) in client["templates"]
        if not ok:
            gaps.append((status, kind, text))
    return gaps


def test_every_shop_and_artist_method_is_listed_or_exempted():
    family = set(FAMILY_RE.findall(_read(API)))
    assert family == set(DISPLAY) | set(NOT_DISPLAYED), (
        sorted(family - set(DISPLAY) - set(NOT_DISPLAYED)), sorted((set(DISPLAY) | set(NOT_DISPLAYED)) - family))
    callers = _read("plugin/NativeUI.cs") + _read("plugin/TitleLaddersUI.cs")
    for m in DISPLAY:
        assert "ApiClient.%s(" % m in callers, m


def test_a_listed_get_keeps_the_refusal_body_and_no_post_redacts_it():
    for m, reqs in DISPLAY.items():
        body = _api_method(m)
        if any(v == "get" for v, _ in reqs):
            calls = re.findall(r"GetRequest\(", body)
            assert len(calls) == 1 and "detailedErrors: true" in body, m
        assert "redactErrorText: true" not in body, m
    # planted: the round-2 preview call, which dropped the body
    planted = _api_method("FetchCosmeticSubmissionPreview").replace("detailedErrors: true, ", "")
    assert "detailedErrors: true" not in planted


def test_the_enumeration_reaches_every_shop_and_artist_route():
    funcs = _module("backend/api/main.py")
    routes = display_routes(funcs)
    assert set(shop_routes(funcs)) <= set(routes), sorted(set(shop_routes(funcs)) - set(routes))
    assert "artist_cosmetic_preview" in routes and "purchase_item" in routes
    reached = _closure(funcs, routes)
    for helper in ("_artist_own_item", "_sanitize_cosmetic_png", "_png_walk_chunks", "_check_steam_session"):
        assert helper in reached, helper
    server = server_refusals(funcs)
    for item in [(402, "template", "Insufficient gold: have {0}, need {1}"),
                 (409, "exact", "Sold out"),
                 (404, "exact", "Player not found — they need to have used the mod once"),
                 (400, "exact", "malformed PNG (no IEND chunk)"),
                 (400, "template", "bad frame PNG: {0}"),
                 (404, "exact", "Cosmetic submission not found"),          # the preview GET
                 (503, "error", "maintenance"), (429, "error", "rate_limited"),
                 (503, "error", "rate_limited"), (403, "error", "forbidden"),
                 (413, "error", "payload_too_large"), (426, "sentinel", "outdated"),
                 (401, "exact", "player_session_required"),                 # the read gate
                 (503, "exact", "read_gate_unavailable")]:
        assert item in server, item
    # a GET path the read gate does not class would leave its refusals unproven
    rg = _read("backend/api/read_gate.py")
    for m, reqs in DISPLAY.items():
        for v, p in reqs:
            if v == "get":
                assert '"%s",' % p in rg, p
    # the request helpers answer the version gate's 426 themselves
    assert re.search(r'"outdated"', _member(_read(API), "private static bool HandleVersionGate("))
    assert {(s, t) for s, k, t in server if k == "dict"} == client_refusals()["dict"] | SENTINEL_DICT


def test_every_reachable_refusal_is_mapped():
    assert coverage_gaps(server_refusals(), client_refusals()) == []


def test_no_mapping_is_stale():
    server = server_refusals()
    client = client_refusals()
    have = {(s, t) for s, k, t in server}
    stale = sorted((client["exact"] | set(client["templates"]) | client["dict"] | client["error"]) - have)
    assert stale == []


def test_planted_details_are_reported_unmapped():
    server = server_refusals()
    client = client_refusals()
    planted = {(409, "exact", "Planted detail no route sends"),
               (402, "template", "Planted {0} of {1}"),
               (418, "dict", "planted_code"),
               (500, "error", "maintenance"),       # a real code at a status the middleware never uses
               (402, "exact", "Sold out")}          # a real detail at a status the client does not map
    assert set(coverage_gaps(server | planted, client)) == planted


def test_planted_middleware_and_display_routes_are_enumerated():
    # a display GET with no row for its route's own detail is a gap
    funcs = _module("backend/api/main.py")
    without = dict(DISPLAY)
    without.pop("FetchCosmeticSubmissionPreview")
    assert "artist_cosmetic_preview" not in display_routes(funcs, without)
    assert "artist_cosmetic_preview" in display_routes(funcs)
    # a middleware answer the map lacks is reported
    client = client_refusals()
    lacking = dict(client, error=client["error"] - {(503, "maintenance")})
    assert coverage_gaps(middleware_refusals(funcs), lacking) == [(503, "error", "maintenance")]


def _english_added(keys, server_texts):
    return sorted(k for k in keys if k.replace('\\' + '"', '"') not in server_texts)


def test_no_added_english():
    """Every key ServerTextRules returns is text the server sends: a route
    or middleware detail, a detail skeleton, a code, or one of the labels
    main.py composes (the two FFA series labels and the bets ledger's three,
    pinned in the tests below). A wrapper that adds advice ("Try again in a
    few minutes") fails here."""
    rules = _read(RULES)
    keys = set(re.findall(r'I18n\.Tr\(%s\)' % _LIT, rules)) | set(re.findall(r'I18n\.TrF\(%s,' % _LIT, rules))
    assert len(keys) >= 100, len(keys)
    server_texts = {t for _, _, t in server_refusals()} | {"{0}-player FFA", "#1 of {0}", "Team {0}", "game {0}"}
    assert _english_added(keys, server_texts) == []
    # planted: the round-2 wrapper sentences are caught
    planted = {"The server cannot do this right now ({0}). Try again in a few minutes.",
               "The server refused this request ({0}). Restart the game; if it keeps happening, send a bug report."}
    assert _english_added(keys | planted, server_texts) == sorted(planted)


def test_template_holes_are_numeric_unless_they_carry_text():
    client = client_refusals()
    text = {t for (_, t), is_text in client["templates"].items() if is_text}
    assert text == TEXT_HOLES
    assert client["templates"][(402, "Insufficient gold: have {0}, need {1}")] is False
    tmpl = _member(_read(RULES), "private static bool RefusalTemplate(string d, string template, bool textHoles, out string[] args)")
    assert '"(-?[0-9]+(?:\\\\.[0-9]+)?)"' in tmpl
    assert '"([^\\\\r\\\\n]+?)"' in tmpl and "Regex.Escape" in tmpl
    assert 'new StringBuilder("\\\\A")' in tmpl and 'sb.Append("\\\\z");' in tmpl
    assert "m.Index != 0 || m.Length != d.Length" in tmpl


def test_text_holes_that_carry_a_forwarded_refusal_translate_it_too():
    body = client_refusals()["body"]
    for t in ("bad frame PNG: {0}", "Published cosmetic source must be a transparent 512x512 PNG ({0})"):
        assert re.search(r'RefusalTemplate\(d, "%s", true, out a\)\)\s*return I18n\.TrF\("%s", '
                         r'TrRefusalDetail\(status, a\[0\]\) \?\? a\[0\]\);' % (re.escape(t), re.escape(t)), body), t


def test_the_refusal_helpers_are_wired():
    rules = _read(RULES)
    tr = _member(rules, "internal static string TrRefusal(string resp)")
    assert "if (r.Detail != null) return TrRefusalDetail(r.Status, r.Detail);" in tr
    assert "if (r.DetailError != null) return TrRefusalObject(r.Status, r.DetailError);" in tr
    assert "if (r.Error != null) return TrMiddleware(r.Status, r.Error);" in tr
    native = _read("plugin/NativeUI.cs")
    assert "internal static string TrShopRefusal(string resp) => ServerTextRules.TrRefusal(resp);" in native
    for gone in ("ExtractServerDetail(resp)", "RefusalStatus(", "TrRefusalDetail(", "ProtocolAnswers", "Refused("):
        assert gone not in _member(native, "private static void ShowArtistResult(bool ok, string msg)"), gone
    # no response recognition by substring on these surfaces (H1 class)
    for rel in ("plugin/NativeUI.cs", "plugin/TitleLaddersUI.cs"):
        src = _read(rel)
        assert 'resp.Contains("price_changed")' not in src, rel
        assert src.count("resp == ApiClient.PriceChangedSentinel") == 1, rel
    purchase = _api_method("PurchaseItem")
    assert 'ServerTextRules.IsDetailError(resp, 409, "price_changed")' in purchase
    assert 'IndexOf("price_changed"' not in purchase and 'Contains("price_changed")' not in purchase
    assert 'internal const string PriceChangedSentinel = "price_changed";' in _read(API)


# -- every English label the server composes into an answer -------------------

_WORD = re.compile(r"[A-Za-z]{2,}")
# a value concatenated inside SQL text: || 'words' or 'words' ||
_SQL_CAT = re.compile(r"(?:\|\|\s*'([^']*)'|'([^']*)'\s*\|\|)")


def _lits(node):
    """The literal text parts of a composed value: a JoinedStr's constant
    parts, the str constants a +/% chain is built from, a format/join
    receiver; never a subscript key or a call argument inside a part."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return [v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
    if isinstance(node, ast.BinOp):
        return _lits(node.left) + _lits(node.right)
    if isinstance(node, ast.IfExp):
        return _lits(node.body) + _lits(node.orelse)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return _lits(node.func.value)
    return []


def _composed(v):
    if isinstance(v, ast.JoinedStr):
        return True
    if isinstance(v, ast.BinOp) and isinstance(v.op, (ast.Add, ast.Mod)):
        return True
    if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr in ("format", "join"):
        return True
    if isinstance(v, ast.IfExp):
        return _composed(v.body) or _composed(v.orelse)
    return False


def composed_labels(extra=None):
    """{(file, dict key, words)} for every dict value in backend/api/*.py
    composed from English words (an f-string, a + or % chain, a format), and
    {(file, "sql", words)} for every English literal SQL text concatenates
    into a value (|| 'words')."""
    out = set()
    sources = [(p.name, p.read_text(encoding="utf-8")) for p in sorted((ROOT / "backend" / "api").glob("*.py"))]
    for name, src in sources + list(extra or []):
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for d in ast.walk(tree):
            if not isinstance(d, ast.Dict):
                continue
            for k, v in zip(d.keys, d.values):
                if _str(k) is None or v is None or not _composed(v):
                    continue
                words = [w for s in _lits(v) for w in _WORD.findall(s)]
                if words:
                    out.add((name, k.value, " ".join(words)[:70]))
        for c in ast.walk(tree):
            if isinstance(c, ast.Constant) and isinstance(c.value, str):
                for m in _SQL_CAT.finditer(c.value):
                    lit = m.group(1) if m.group(1) is not None else m.group(2)
                    words = " ".join(_WORD.findall(lit))
                    if words:
                        out.add((name, "sql", words[:70]))
    return out



COMPOSED = {
    # SQL concatenations (|| 'words')
    ('auto_logs.py', 'sql', 'minutes'): 'a SQL interval or setting unit, not a label',
    ('main.py', 'sql', 'minutes'): 'a SQL interval or setting unit, not a label',
    ('main.py', 'sql', 'seconds'): 'a SQL interval or setting unit, not a label',
    ('main.py', 'sql', 'ms'): 'a SQL interval or setting unit, not a label',
    ('main.py', 'sql', 'ban rate'): 'a SQL advisory-lock key, never shown',
    ('main.py', 'sql', 'dcpair'): 'a SQL advisory-lock key, never shown',
    ('main.py', 'sql', 'macro evidence match'): 'a SQL advisory-lock key, never shown',
    ('main.py', 'sql', 'mail'): 'a SQL advisory-lock key, never shown',
    ('main.py', 'sql', 'mrq'): 'a SQL advisory-lock key, never shown',
    ('tournaments.py', 'sql', 'tournament match'): 'a SQL advisory-lock key, never shown',
    ('main.py', 'sql', 'sct'): 'an internal cache, limit or room key, never shown',
    ('main.py', 'sql', 'Edition'):
        'pc_editions.name, which no route selects; never sent to the client',
    ('main.py', 'sql', 'begins Edition'): 'a Discord message or admin alert, not a client surface',
    ('main.py', 'sql', 'prints are out of print'): 'a Discord message or admin alert, not a client surface',
    ('main.py', 'sql', 'player FFA'):
        'MAPPED bets ledger, FFA arm vs_name: ServerTextRules.BetVsName -> "{0}-player FFA"',
    ('main.py', 'sql', 'game'):
        'MAPPED bets ledger, FFA arm series_score: ServerTextRules.BetScore -> "game {0}"',
    ('main.py', 'sql', 'Team'):
        'MAPPED bets ledger, team arm bet_on_name: ServerTextRules.BetOnName -> "Team {0}"',
    ('admin_evidence.py', 'branches', 'UNION ALL'):
        'query text, not a label',
    ('card_evidence.py', 'k', 'card daily'):
        'an internal cache, limit or room key, never shown',
    ('card_evidence.py', 'k', 'card evidence'):
        'an internal cache, limit or room key, never shown',
    ('combat_evidence.py', 'k', 'combat daily'):
        'an internal cache, limit or room key, never shown',
    ('combat_evidence.py', 'k', 'combat evidence'):
        'an internal cache, limit or room key, never shown',
    ('flag_evidence.py', 'match_context', 'Reporter mod game region room'):
        'an admin, portal or evidence surface, not a player label',
    ('flag_evidence.py', 'suspect_steam_text', 'not attributable'):
        'an admin, portal or evidence surface, not a player label',
    ('identity_clock_evidence.py', 'k', 'identity clock'):
        'an internal cache, limit or room key, never shown',
    ('main.py', 'Content-Disposition', 'attachment filename bug log'):
        'a download header',
    ('main.py', 'assumption', 'each delta fixes one player place the others finish in rating order no'):
        'an admin, portal or evidence surface, not a player label',
    ('main.py', 'c', 'Auto mod removed message from in and muted them for min offense matche'):
        'a Discord message or admin alert, not a client surface',
    ('main.py', 'c', 'Ban rate flag admin hit bans in minutes further bans are blocked until'):
        'a Discord message or admin alert, not a client surface',
    ('main.py', 'c', 'MIN MOD VERSION auto raised to players adopted and no older version pl'):
        'a Discord message or admin alert, not a client surface',
    ('main.py', 'c', 'Server alert by'):
        'a Discord message or admin alert, not a client surface',
    ('main.py', 'c1_label', 'Rated results for these players RECEIVED after this capture This is wh'):
        'an admin, portal or evidence surface, not a player label',
    ('main.py', 'd', 'for'):
        'an admin, portal or evidence surface, not a player label',
    ('main.py', 'd', 'keys retired superseded superseded retired'):
        'an admin, portal or evidence surface, not a player label',
    ('main.py', 'd', 'proposal'):
        'an admin, portal or evidence surface, not a player label',
    ('main.py', 'd', 'proposal self approved'):
        'an admin, portal or evidence surface, not a player label',
    ('main.py', 'description', 'fully observed game in server wall time below game floor'):
        'an admin, portal or evidence surface, not a player label',
    ('main.py', 'detail', 'team series is'):
        'a status answer the client logs and does not show',
    ('main.py', 'forfeit_room', 'dc leadforfeit'):
        'an internal cache, limit or room key, never shown',
    ('main.py', 'k', 'casualdc'):
        'an internal cache, limit or room key, never shown',
    ('main.py', 'k', 'opkey'):
        'an internal cache, limit or room key, never shown',
    ('main.py', 'k', 'pc shard key'):
        'an internal cache, limit or room key, never shown',
    ('main.py', 'k', 'spectate'):
        'an internal cache, limit or room key, never shown',
    ('main.py', 'line', 'rows received before this capture this report own game number'):
        'an admin, portal or evidence surface, not a player label',
    ('main.py', 'lv', 'dms'):
        'a number with its unit symbol',
    ('main.py', 'lv', 'ms'):
        'a number with its unit symbol',
    ('main.py', 'message', 'Blocked from ranked matchmaking'):
        'a status answer the client logs and does not show',
    ('main.py', 'message', 'Declined match Blocked for minutes'):
        'a status answer the client logs and does not show',
    ('main.py', 'message', 'Joined queue'):
        'a status answer the client logs and does not show',
    ('main.py', 'message', 'Unblocked'):
        'a status answer the client logs and does not show',
    ('main.py', 'muted', 'discord'):
        'an internal cache, limit or room key, never shown',
    ('main.py', 'muted', 'steam'):
        'an internal cache, limit or room key, never shown',
    ('main.py', 'reason', 'already'):
        'a status answer the client logs and does not show',
    ('main.py', 'reason', 'auto slur filter offense'):
        'a status answer the client logs and does not show',
    ('main.py', 'reason', 'series is not completed'):
        'a status answer the client logs and does not show',
    ('main.py', 'right_label', 'player FFA'):
        'MAPPED ServerTextRules.SeriesRightLabel',
    ('main.py', 'score', 'of'):
        'MAPPED ServerTextRules.SeriesScore',
    ('main.py', 'sitting', 'id IN WITH anchor AS SELECT player id player id ended at FROM matches '):
        'query text, not a label',
    ('main.py', 'sv', 'dms'):
        'a number with its unit symbol',
    ('main.py', 'v', 'ms'):
        'a number with its unit symbol',
    ('main.py', 'via', 'event'):
        'an internal cache, limit or room key, never shown',
    ('match_hold.py', 'lock_ms', 'ms'):
        'query text, not a label',
    ('match_hold.py', 'statement_ms', 'ms'):
        'query text, not a label',
    ('pc_face.py', 'file', 'png'):
        "a developer tool's report, not a client surface",
    ('pc_face.py', 'reason', 'face rect differs'):
        "a developer tool's report, not a client surface",
    ('pc_face.py', 'reason', 'negative carries the art'):
        "a developer tool's report, not a client surface",
    ('pc_face.py', 'reason', 'not drawn'):
        "a developer tool's report, not a client surface",
    ('pc_face.py', 'reason', 'rect differs'):
        "a developer tool's report, not a client surface",
    ('seat_evidence.py', 'k', 'seat evidence'):
        'an internal cache, limit or room key, never shown',
    ('tournaments.py', 'c', 'The Synchronized tournament locked for time you didn mark as available'):
        'a Discord message or admin alert, not a client surface',
    ('tournaments.py', 'label', 'tournament'):
        'an internal cache, limit or room key, never shown',
    ('tournaments.py', 'reason', 'tournament rank'):
        'an internal cache, limit or room key, never shown',
}


def test_every_composed_server_label_is_classified():
    found = composed_labels()
    assert found == set(COMPOSED), (sorted(found - set(COMPOSED)), sorted(set(COMPOSED) - found))
    mapped = {k: v for k, v in COMPOSED.items() if v.startswith("MAPPED ")}
    assert set(mapped) == {("main.py", "right_label", "player FFA"), ("main.py", "score", "of"),
                           ("main.py", "sql", "player FFA"), ("main.py", "sql", "game"),
                           ("main.py", "sql", "Team")}
    # planted: a new composed label in any module is reported unclassified,
    # a dict value and a SQL concatenation alike
    planted = composed_labels([("planted.py", 'x = {"status_label": f"{n} players waiting"}'),
                               ("planted2.py", 'q = "SELECT (l.n || \' players waiting\') AS label"')])
    assert planted - set(COMPOSED) == {("planted.py", "status_label", "players waiting"),
                                       ("planted2.py", "sql", "players waiting")}


BET_KEYS = ["Bet {0} gold on {1} vs {2}", "- in play, score {0}",
            "Bet {0} gold on {1} vs {2} - refunded, series never finished",
            "Bet {0} gold on {1} vs {2} - WON {3} gold", "Bet {0} gold on {1} vs {2} - LOST"]


def test_the_bets_ledger_maps_each_arms_labels_before_markup():
    """GET /players/{id}/bets is a UNION of three arms; the FFA arm composes
    "N-player FFA" (vs_name) and "game N" (series_score), the team arm "Team N"
    (bet_on_name) and sends no bet_on_steam_id. The ledger tells the arms
    apart by those shapes and maps each composed value by arm; names and the
    ranked arm's values are shown as sent."""
    main_src = _read("backend/api/main.py")
    route = main_src[main_src.index('@app.get("/api/v1/players/{steam_id}/bets"'):]
    route = route[:route.index("\n@app.")]
    assert "(l.player_count || '-player FFA') AS vs_name" in route
    assert "('game ' || fb.game_number) AS series_score" in route
    assert "NULL, ('Team ' || tb.bet_on_team)," in route
    assert "bo.steam_id      AS bet_on_steam_id" in route
    rules = _read(RULES)
    arm = _member(rules, "internal static string BetArm(string betOnSteamId, string seriesScore)")
    assert 'if (string.IsNullOrEmpty(betOnSteamId)) return "team";' in arm
    assert 'seriesScore.StartsWith("game ", StringComparison.Ordinal)' in arm and 'return "ffa";' in arm
    on = _member(rules, "internal static string BetOnName(string arm, string name)")
    sc = _member(rules, "internal static string BetScore(string arm, string score)")
    # each value is mapped in its own arm only; a name in another arm is shown as sent
    assert 'if (arm == "team" && name != null' in on and 'return I18n.TrF("Team {0}", n);' in on and "return name;" in on
    assert 'if (arm == "ffa" && score != null' in sc and 'return I18n.TrF("game {0}", n);' in sc and "return score;" in sc
    assert 'SeriesRightLabel(arm == "ffa" ? "ffa" : null, name)' in rules
    ui = _read("plugin/NativeUI.cs")
    assert "Bet {b.amount:N0} gold on" not in ui
    assert "{Nm(b.vs_name)}" not in ui and "{Nm(b.bet_on_name)}" not in ui and "{b.series_score}" not in ui
    assert ui.count("ServerTextRules.BetArm(b.bet_on_steam_id, b.series_score)") == 2
    assert "Nm(ServerTextRules.BetOnName(arm, b.bet_on_name))" in ui
    assert "Nm(ServerTextRules.BetVsName(arm, b.vs_name))" in ui
    assert "Nm(ServerTextRules.BetOnName(sArm, b.bet_on_name))" in ui
    assert "Nm(ServerTextRules.BetVsName(sArm, b.vs_name))" in ui
    assert 'I18n.TrF("- in play, score {0}", ServerTextRules.BetScore(arm, b.series_score))' in ui
    for k in BET_KEYS:
        assert ui.count('I18n.TrF("%s",' % k) == 1, k


def test_the_ffa_series_labels_are_mapped_before_fitting_and_markup():
    main = _read("backend/api/main.py")
    assert main.count('"mode": "ffa", "id": str(r["id"]),') == 1
    assert main.count('"right_label": str(r["player_count"]) + "-player FFA",') == 1
    assert main.count('"score": "#1 of " + str(r["player_count"]),') == 1
    native = _read("plugin/NativeUI.cs")
    line = _member(native, "private static string BuildMultimodeSeriesLine(ApiClient.MultimodeSeriesEntry m,string myName)")
    assert "ServerTextRules.SeriesRightLabel(m.mode,m.right_label)??\"?\",budget" in line
    assert "<b>{ServerTextRules.SeriesScore(m.mode,m.score)}</b>" in line
    assert "{m.score}" not in line and "m.right_label??" not in line
    rules = _read(RULES)
    right = _member(rules, "internal static string SeriesRightLabel(string mode, string label)")
    score = _member(rules, "internal static string SeriesScore(string mode, string score)")
    assert 'mode == "ffa"' in right and 'I18n.TrF("{0}-player FFA", n)' in right and "return label;" in right
    assert 'mode == "ffa"' in score and 'I18n.TrF("#1 of {0}", n)' in score and "return score;" in score


# -- tournament labels --------------------------------------------------------

def _bracket_tags(funcs):
    fn = funcs["_bracket_tag"]
    d = [n for n in ast.walk(fn) if isinstance(n, ast.Dict)]
    assert len(d) == 1
    return [v.value for v in d[0].values]


def server_progress_labels():
    funcs = _module("backend/api/tournaments.py")
    tags = _bracket_tags(funcs)
    out = set()

    def hole(e):
        if isinstance(e, ast.Call) and getattr(e.func, "id", None) == "_bracket_tag":
            return tags
        return None

    def add(e):
        if _str(e) is not None:
            out.add(e.value)
        elif isinstance(e, ast.IfExp):
            add(e.body)
            add(e.orelse)
        elif isinstance(e, ast.JoinedStr):
            out.update(_fstring_variants(e, hole))
        else:
            raise AssertionError("unclassified label at tournaments.py:%d" % e.lineno)

    for node in ast.walk(funcs["_compute_progress_labels"]):
        if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Subscript)
                and getattr(node.targets[0].value, "id", None) == "labels"):
            add(node.value)
    history = [f for f in funcs.values()
               if any(isinstance(d, ast.Dict) and "result_label" in [_str(k) for k in d.keys]
                      for d in ast.walk(f))]
    assert len(history) == 1
    for node in ast.walk(history[0]):
        if (isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "_label"
                and _str(node.value) is not None):
            add(node.value)
    return out


def server_round_labels():
    funcs = _module("backend/api/tournaments.py")
    out = set()
    for node in ast.walk(funcs["_round_label"]):
        if isinstance(node, ast.Return):
            out.update([node.value.value] if _str(node.value) is not None else _fstring_variants(node.value))
    return out


def _cases(body, var):
    cases = re.findall(r'if \(%s == %s\) return I18n\.Tr\(%s\);' % (var, _LIT, _LIT), body)
    for a, b in cases:
        assert a == b, (a, b)
    rounds = re.findall(r'LabelRound\(%s, %s, out n\)\) return I18n\.TrF\(%s, n\);' % (var, _LIT, _LIT), body)
    for p, k in rounds:
        assert k == p + "{0}", (p, k)
    assert body.count('if (%s == "' % var) == len(cases) and "case " not in body
    assert body.count("LabelRound(") == len(rounds)
    return {a for a, _ in cases} | {k for _, k in rounds}


def label_gaps(server, client):
    return sorted(server - client)


def test_every_progress_and_result_label_is_mapped():
    server = server_progress_labels()
    assert {"signed up", "mutual forfeit", "CHAMPION", "won by forfeit", "advanced", "3rd place",
            "WB R{0}", "eliminated GF Reset R{0}"} <= server
    client = _cases(_member(_read("plugin/NativeUI.cs"), "internal static string TrBracketProgress(string label)"), "label")
    assert label_gaps(server, client) == []
    assert sorted(client - server) == []
    planted = {"withdrew", "eliminated QF R{0}"}
    assert label_gaps(server | planted, client) == sorted(planted)


def test_every_round_label_in_the_banner_is_mapped():
    server = server_round_labels()
    assert server == {"Grand Final", "Grand Final Reset", "Third-Place Match", "Losers R{0}", "Winners R{0}"}
    native = _read("plugin/NativeUI.cs")
    client = _cases(_member(native, "private static string TrRoundLabel(string r)"), "r")
    assert label_gaps(server, client) == [] and sorted(client - server) == []
    assert label_gaps(server | {"Quarter Final"}, client) == ["Quarter Final"]
    main = _read("backend/api/main.py")
    composers = re.findall(r'\("Async" if [^\n]*? else "Sync"\)\s*\+ " Tournament - "\s*\+ _round_label\(', main)
    assert len(composers) == main.count('" Tournament - "') == 3
    banner = _member(native, "internal static string TrTournamentBanner(string label)")
    for kind in ("Sync", "Async"):
        assert '"%s Tournament - "' % kind in banner
        assert 'I18n.TrF("%s Tournament - {0}", round)' % kind in banner
    gsw = _member(_read("plugin/GameStateWatcher.cs"), "public static void SetTournamentContext(bool isTournament, string label)")
    tr = gsw.index("lbl = NativeUI.TrTournamentBanner(lbl);")
    assert gsw.index("lbl = lbl.Replace(") < tr < gsw.index("if (lbl.Length > 52)")


def test_label_sites_map_before_composing_markup():
    native = _read("plugin/NativeUI.cs")
    assert "{s.progress_label}" not in native and "{p.result_label}" not in native
    assert native.count('status = "<color=#A86060>" + TrBracketProgress(s.progress_label) + "</color>";') == 1
    assert native.count('status = "<color=#AACCFF>" + TrBracketProgress(s.progress_label) + "</color>";') == 1
    assert native.count('label = $"   <color={lc}>{TrBracketProgress(p.result_label)}</color>";') == 1
    # the in-game banner's kind tag in the series list
    # an unknown kind keeps its own word, through a template
    assert native.count('I18n.TrF("TOURNAMENT {0}", char.ToUpper(s.tournament_kind[0]) + s.tournament_kind.Substring(1))') == 1
    assert native.count("[TOURNAMENT{kindSuffix}]") == 0
    for k in ("TOURNAMENT Async", "TOURNAMENT Sync", "TOURNAMENT", "PRIVATE"):
        assert native.count('I18n.Tr("%s")' % k) == 1, k


def test_team_queue_status_words_are_keys():
    main = _read("backend/api/main.py")
    m = re.findall(r"WHERE tq\.status IN \(([^)]*)\)", main)
    assert len(m) == 1
    server = set(re.findall(r"'(\w+)'", m[0]))
    assert server == {"searching", "matched", "ready"}
    native = _read("plugin/NativeUI.cs")
    colors = {"searching": "#66CCFF", "matched": "#FFD94D", "ready": "#88FF88"}
    for s in server:
        key = "<color=%s>%s</color>" % (colors[s], s)
        assert native.count('q.status == "%s"' % s) == 1, s
        assert native.count('I18n.Tr("%s")' % key) == 1, s
    assert native.count('$"<color=#88FF88>{q.status}</color>"') == 1   # an unknown status only


def test_admin_rows_keep_raw_status_words():
    # admin-only surfaces, exempt by design: the admin series list and the
    # bug-report detail popup show the database's own status words
    native = _read("plugin/NativeUI.cs")
    admin = _member(native, "private static void FillAdminSeriesRow(GameObject row, ApiClient.AdminSeriesEntry e)")
    assert "{e.status}" in admin
    assert "<b>status:</b> {d.status}" in _read("plugin/CompetitiveUI.cs")


# -- outcome words name no cause the server does not assert -------------------

# Match status "forfeit" covers an explicit concession and the absence sweep;
# "double_forfeit" a mutual concession and a mutual no-show; a signup's
# forfeited flag a concession, a no-show or a ban. Each rendering must stay
# cause-neutral: none may say "no-show", "surrendered", "gave up" or "left".
OUTCOME_KEYS = [
    "forfeit", "double forfeit", "<color=#FF6060>FORFEIT</color>",
    "mutual forfeit", "won by forfeit", "Deadlines & forfeits",
    "Play a tournament through to the end without forfeiting a single match",
    "1v2: leaving ends your sitting; there is no automatic forfeit.",
    "Leave this competitive match? Click again to confirm. Standard disconnect and "
    "early-leave rules apply - this is not a guaranteed forfeit.",
]
CAUSE_WORDS = {
    "ES": ["incomparec", "rendi", "abandon", "ausen"],
    "RU": ["неявк", "сдал", "сдач", "отсутств"],
    "UK": ["неявк", "здав", "здач", "відсутн"],
    "SV": ["gav upp", "lämna en", "uppgiv", "utebl", "frånvar"],
}


def _catalogue_blocks():
    cs = _read("plugin/I18nCatalogues.cs")
    blocks = cs.split("private static readonly Dictionary<string, string> ")[1:]
    assert [b[:2] for b in blocks] == ["ES", "RU", "UK", "SV"]
    return [(b[:2], b[:b.index("\n        };")]) for b in blocks]


def _rows(body, s):
    return re.findall(r'^\s+\["%s"\] = "((?:[^"\\]|\\.)*)",$' % re.escape(s), body, re.M)


def test_outcome_words_are_cause_neutral_in_every_locale():
    for lang, body in _catalogue_blocks():
        for k in OUTCOME_KEYS:
            rows = _rows(body, k)
            assert len(rows) == 1, (lang, k)
            low = rows[0].lower()
            for w in CAUSE_WORDS[lang]:
                assert w not in low, (lang, k, w, rows[0])


# Round 3 (H3): the forfeit, bye and walkover rows of the FAQ named a cause
# the server does not assert. A match forfeit (tournaments.py) is a
# concession, an absence or a ban; the 2v2 lead forfeit is the other team's
# disconnect. Each fixed phrase: (locale, English key start, the narrowing
# phrase that must be gone, the neutral phrase now there). The words swept
# per locale are listed in the lane's notes.
FORFEIT_FIXES = [
    ('ES', '<color=#FFD94D><b>HOW THE BALA',
     'Rendición con ventaja:',
     'Forfait por ventaja:'),
    ('ES', 'Every finished game pays XP, X',
     'Plazos e incomparecencias',
     'Plazos y forfaits'),
    ('ES', 'Every tournament runs through ',
     'Plazos e incomparecencias',
     'Plazos y forfaits'),
    ('ES', 'Every tournament runs through ',
     "una incomparecencia dice 'Avanzas - tu rival se rindió'",
     "un forfait dice 'Avanzas - tu rival perdió por forfait'"),
    ('ES', 'Every tournament runs through ',
     'Una incomparecencia nunca se disfraza',
     'Un forfait nunca se disfraza'),
    ('ES', 'The rule book for what gets recorded and what gets thrown away: games, series, disconnects, bets. If a result looks missing, the reason is almost always on this page.\\n\\n<color=#FFD94D><b>NEVER RECORDED AT ALL</b></color>\\n\\n- Data consent off: the mod runs fully offline. Nothing is ever sent except a version check.\\n- Offline, practice and sandbox games: never reported by the client, and refused by the server as a backstop.\\n- Spectator seats tr',
     'decidida por incomparecencia no puede apostarse',
     'decidida por forfait no puede apostarse'),
    ('ES', 'The rule book for what gets recorded and what gets thrown away: games, series, disconnects, bets. If a result looks missing, the reason is almost always on this page.\\n\\n<color=#FFD94D><b>NEVER RECORDED AT ALL</b></color>\\n\\n- Data consent off: the mod runs fully offline. Nothing is ever sent except a version check.\\n- Offline, practice and sandbox games: never reported by the client, and refused by the server as a backstop.\\n- Spectator seats su',
     'decidida por incomparecencia no puede apostarse',
     'decidida por forfait no puede apostarse'),
    ('ES', 'Tournaments are 8-16 player do',
     'no presentarse es incomparecencia',
     'no presentarse es un forfait'),
    ('ES', 'Tournaments are 8-16 player do',
     'Plazos e incomparecencias',
     'Plazos y forfaits'),
    ('ES', 'What happens when someone does',
     'las victorias por incomparecencia nunca pagan',
     'las victorias por forfait nunca pagan'),
    ('ES', 'What happens when someone does',
     'no puede dar por incomparecencia a nadie',
     'no puede imponer un forfait a nadie'),
    ('ES', 'What happens when someone does',
     'un asiento baneado pierde por incomparecencia esté presente o no',
     'un asiento baneado pierde por forfait esté presente o no'),
    ('ES', 'What happens when someone does',
     'QUÉ HACE UNA INCOMPARECENCIA - Y QUÉ NO',
     'QUÉ HACE UN FORFAIT - Y QUÉ NO'),
    ('ES', 'What happens when someone does',
     'Una incomparecencia no acuña nada.',
     'Un forfait no acuña nada.'),
    ('ES', 'What happens when someone does',
     'un puesto de podio decidido por incomparecencia no paga premio',
     'un puesto de podio decidido por forfait no paga premio'),
    ('ES', 'What happens when someone does',
     'la serie de una partida por incomparecencia simplemente',
     'la serie de una partida perdida por forfait simplemente'),
    ('ES', 'What happens when someone does',
     'la serie de una partida por incomparecencia no puede apostarse',
     'la serie de una partida perdida por forfait no puede apostarse'),
    ('ES', 'What happens when someone does',
     'Un puesto decidido por incomparecencia se salta',
     'Un puesto decidido por forfait se salta'),
    ('ES', 'What happens when someone does',
     'sin dar nunca por incomparecencia desbloquea',
     'sin perder nunca por forfait desbloquea'),
    ('ES', '<b><color=#FFD94D>HOW IT WORKS (Async)</',
     'pierdes esa partida por incomparecencia',
     'pierdes esa partida por forfait'),
    ('RU', 'Every tournament runs through ',
     'соперник сдал матч',
     'сопернику засчитано техпоражение'),
    ('UK', 'Every tournament runs through ',
     'суперник здався',
     'супернику зараховано технічну поразку'),
    ('SV', 'Every tournament runs through ',
     'din motståndare lämnade walkover',
     'din motståndare förlorade på walkover'),
]
# The outcome sentence a forfeit win sends ("You advance - your opponent
# forfeited") quoted as a concession, in any row.
CONCESSION_QUOTES = {"ES": "tu rival se rindió", "RU": "соперник сдал матч",
                     "UK": "суперник здався", "SV": "motståndare lämnade walkover"}


def _rows_starting(body, start):
    pat = r'^\s+\["%s(?:[^"\\]|\\.)*"\] = "((?:[^"\\]|\\.)*)",$' % re.escape(start)
    return re.findall(pat, body, re.M)


def test_forfeit_rows_name_no_cause_the_server_does_not_assert():
    blocks = dict(_catalogue_blocks())
    for lang, start, gone, now in FORFEIT_FIXES:
        rows = _rows_starting(blocks[lang], start)
        assert rows, (lang, start)
        for v in rows:
            assert gone not in v and now in v, (lang, start[:40], gone)
    for lang, body in blocks.items():
        assert CONCESSION_QUOTES[lang] not in body, lang
    # planted: the round-2 Spanish row is caught
    es = blocks["ES"].replace("Avanzas - tu rival perdió por forfait", "Avanzas - tu rival se rindió")
    assert CONCESSION_QUOTES["ES"] in es


# -- every key above ships in every bundled catalogue -------------------------

def lane_keys():
    native = _read("plugin/NativeUI.cs")
    keys = set(client_refusals()["keys"]) | {"{0}-player FFA", "#1 of {0}", "TOURNAMENT {0}"}
    keys |= _cases(_member(native, "internal static string TrBracketProgress(string label)"), "label")
    keys |= _cases(_member(native, "private static string TrRoundLabel(string r)"), "r")
    keys |= {"Sync Tournament - {0}", "Async Tournament - {0}", "TOURNAMENT Async", "TOURNAMENT Sync",
             "TOURNAMENT", "PRIVATE", "<color=#66CCFF>searching</color>",
             "<color=#FFD94D>matched</color>", "<color=#88FF88>ready</color>"}
    keys |= set(BET_KEYS) | {"Team {0}", "game {0}"}
    return keys


def test_every_label_and_refusal_key_ships_in_every_bundled_catalogue():
    keys = lane_keys()
    assert len(keys) > 80
    for lang, body in _catalogue_blocks():
        for s in sorted(keys):
            rows = _rows(body, s.replace("\\", "\\\\").replace('"', '\\"'))
            assert len(rows) == 1, (lang, s)
            assert rows[0] and rows[0] != s, (lang, s)
    reg = _read("plugin/I18nSourceKeys.g.cs")
    for s in sorted(keys):
        assert reg.count('"%s",' % s) == 1, s
