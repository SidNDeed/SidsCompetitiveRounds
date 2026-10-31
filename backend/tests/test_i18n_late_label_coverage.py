"""Every refusal the shop and artist routes can send, and every tournament
label the server composes, reaches the player through the catalogue.

Refusals. The server's answer to a purchase, gift, set-stock, rename,
placement or upload is an HTTP status plus a detail. This file enumerates
every detail those routes can return by reading backend/api/main.py: each
POST/PUT/PATCH/DELETE route named purchase_item or artist_*, every module
function they call (transitively), every HTTPException those raise, and
every ValueError message an `except ValueError as ve` handler forwards in
its detail. NativeUI.TrRefusalDetail must map each (status, detail) pair:
a fixed detail by an exact case, a composed detail by a template whose
holes are parsed narrowly (numbers only, unless the hole carries an
exception's text), and a protocol answer (a field the mod itself signs or
sends) by one generic catalogue sentence that keeps the code. The two
detail payloads that are objects, not strings, are answered elsewhere and
pinned here. A detail the server can send that the client does not map
fails test_every_reachable_refusal_is_mapped; a mapping the server no
longer sends fails test_no_mapping_is_stale; the planted controls prove
the comparison can fail.

Labels. backend/api/tournaments.py composes the signup list's progress
label and the recent-tournaments popup's result label (a few fixed words
plus "<tag> R<n>" and "eliminated <tag> R<n>" over the bracket tags), and
main.py composes the in-game tournament banner from _round_label. The team
queue list shows the queue row's status. Each finite set goes through a
key; each parameterized label through I18n.TrF; all before markup is
composed. Admin-only rows (the admin series list and the bug-report
detail) show raw status words by design and are pinned as such.

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


def shop_routes(funcs):
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


def server_refusals(funcs=None):
    """{(status, kind, text)}: kind is exact, template or dict."""
    funcs = funcs or _module("backend/api/main.py")
    items = set()
    for n in _closure(funcs, shop_routes(funcs)):
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


# -- client side: NativeUI.TrRefusalDetail ------------------------------------

_LIT = r'"((?:[^"\\]|\\.)*)"'
TEMPLATE_RE = re.compile(r'if \(status == (\d{3}) && RefusalTemplate\(d, %s, (true|false), out a\)\)\s*'
                         r'return (?:I18n\.TrF\(%s, [^;]*\)|(Refused)\(status, d\));' % (_LIT, _LIT))


def client_refusals(native=None):
    native = native or _read("plugin/NativeUI.cs")
    body = _member(native, "internal static string TrRefusalDetail(int status, string d)")
    exact = re.findall(r'if \(k == "(\d{3})\|((?:[^"\\]|\\.)*)"\) return I18n\.Tr\(%s\);' % _LIT, body)
    for s, d, k in exact:
        assert d == k, ("an exact case returns another key", s, d, k)
    assert body.count("if (Array.IndexOf(ProtocolAnswers, k) >= 0) return Refused(status, d);") == 1
    table = _member(native, "private static readonly string[] ProtocolAnswers")
    protocol = re.findall(r'^\s*"(\d{3})\|((?:[^"\\]|\\.)*)",\s*$', table, re.M)
    assert len(protocol) == table.count('"') // 2, "a protocol entry the parser does not read"
    templates = TEMPLATE_RE.findall(body)
    for s, t, text, key, refused in templates:
        assert refused or key == t, ("a template returns another key", t, key)
        holes = re.findall(r"\{(\d)\}", t)
        assert holes == [str(i) for i in range(len(holes))], ("holes out of order", t)
    n_case = body.count('if (k == "')
    n_tmpl = body.count("RefusalTemplate(")
    assert n_case == len(exact) and "case " not in body, "a mapping line the parser does not read"
    assert n_tmpl == len(templates), "a template line the parser does not read"
    return {
        "exact": {(int(s), d) for s, d, _ in exact},
        "protocol": {(int(s), d) for s, d in protocol},
        "templates": {(int(s), t): (text == "true", bool(refused)) for s, t, text, _, refused in templates},
        "body": body,
    }


# The two object-shaped details. price_changed is answered by both purchase
# callbacks before they call TrShopRefusal; the album floor's object answer
# is mapped in TrShopRefusal itself.
DICT_ANSWERED = {(409, "price_changed"), (426, "music_purchase_requires_update")}

# Templates whose hole carries an exception's or a chunk's text, not a number.
TEXT_HOLES = {
    "bad frame PNG: {0}",
    "Published cosmetic source must be a transparent 512x512 PNG ({0})",
    "could not process GIF: {0}",
    "unreadable PNG: {0}",
    "malformed PNG (bad CRC on {0} chunk)",
}


def coverage_gaps(server, client):
    mapped = client["exact"] | client["protocol"]
    gaps = []
    for status, kind, text in sorted(server):
        if kind == "dict":
            ok = (status, text) in DICT_ANSWERED
        elif kind == "exact":
            ok = (status, text) in mapped
        else:
            ok = (status, text) in client["templates"]
        if not ok:
            gaps.append((status, kind, text))
    return gaps


def test_the_enumeration_reaches_every_shop_and_artist_route():
    funcs = _module("backend/api/main.py")
    routes = shop_routes(funcs)
    assert "purchase_item" in routes and "artist_gift" in routes and "artist_set_stock" in routes
    assert "artist_submit_cosmetic_gif" in routes and "artist_catalog_cosmetic_placement" in routes
    assert len(routes) >= 13, routes
    reached = _closure(funcs, routes)
    for helper in ("_artist_own_item", "_sanitize_cosmetic_png", "_png_walk_chunks", "_check_steam_session"):
        assert helper in reached, helper
    server = server_refusals(funcs)
    # anchors from each route family, including a forwarded ValueError
    for item in [(402, "template", "Insufficient gold: have {0}, need {1}"),
                 (409, "exact", "Sold out"),
                 (404, "exact", "Player not found — they need to have used the mod once"),
                 (400, "exact", "malformed PNG (no IEND chunk)"),
                 (400, "template", "bad frame PNG: {0}")]:
        assert item in server, item
    assert {(s, t) for s, k, t in server if k == "dict"} == DICT_ANSWERED


def test_every_reachable_refusal_is_mapped():
    assert coverage_gaps(server_refusals(), client_refusals()) == []


def test_no_mapping_is_stale():
    server = {(s, t) for s, _, t in server_refusals()}
    client = client_refusals()
    stale = sorted((client["exact"] | client["protocol"] | set(client["templates"])) - server)
    assert stale == []


def test_planted_details_are_reported_unmapped():
    server = server_refusals()
    client = client_refusals()
    planted = {(409, "exact", "Planted detail no route sends"),
               (402, "template", "Planted {0} of {1}"),
               (418, "dict", "planted_code"),
               (402, "exact", "Sold out")}     # a real detail at a status the client does not map
    assert set(coverage_gaps(server | planted, client)) == planted


def test_template_holes_are_numeric_unless_they_carry_text():
    client = client_refusals()
    text = {t for (_, t), (is_text, _) in client["templates"].items() if is_text}
    assert text == TEXT_HOLES
    assert client["templates"][(402, "Insufficient gold: have {0}, need {1}")] == (False, False)
    native = _read("plugin/NativeUI.cs")
    tmpl = _member(native, "private static bool RefusalTemplate(string d, string template, bool textHoles, out string[] args)")
    assert '"(-?[0-9]+(?:\\\\.[0-9]+)?)"' in tmpl
    assert '"(.+?)"' in tmpl and "Regex.Escape" in tmpl and "sb.Append('$');" in tmpl


def test_text_holes_that_carry_a_forwarded_refusal_translate_it_too():
    body = client_refusals()["body"]
    for t in ("bad frame PNG: {0}", "Published cosmetic source must be a transparent 512x512 PNG ({0})"):
        assert re.search(r'RefusalTemplate\(d, "%s", true, out a\)\)\s*return I18n\.TrF\("%s", '
                         r'TrRefusalDetail\(status, a\[0\]\) \?\? a\[0\]\);' % (re.escape(t), re.escape(t)), body), t


def test_the_refusal_helpers_are_wired():
    native = _read("plugin/NativeUI.cs")
    shop = _member(native, "internal static string TrShopRefusal(string resp)")
    assert "if (!RefusalStatus(resp, out status)) return null;" in shop
    assert 'status == 426 && resp.Contains("\\"music_purchase_requires_update\\"")' in shop
    assert 'return I18n.Tr("This album requires a newer mod version");' in shop
    assert "return TrRefusalDetail(status, ExtractServerDetail(resp));" in shop
    st = _member(native, "private static bool RefusalStatus(string resp, out int status)")
    assert 'resp.StartsWith("HTTP ", StringComparison.Ordinal)' in st and "status >= 400" in st
    body = client_refusals(native)["body"]
    # the protocol table's lookup and the two protocol templates
    assert body.count("return Refused(status, d);") == 3
    refused = _member(native, "private static string Refused(int status, string d)")
    assert "I18n.TrF(" in refused and "{0}" in refused
    # the two price_changed callbacks answer it before the helper
    assert native.count('if (!ok && resp != null && resp.Contains("price_changed"))') == 1
    assert _read("plugin/TitleLaddersUI.cs").count('if (!ok && resp != null && resp.Contains("price_changed"))') == 1


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
    assert "char.ToUpper(s.tournament_kind[0])" not in native
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


# -- every key above ships in every bundled catalogue -------------------------

def lane_keys():
    native = _read("plugin/NativeUI.cs")
    keys = set()
    client = client_refusals(native)
    keys |= {d for _, d in client["exact"]}
    keys |= {t for (_, t), (_, refused) in client["templates"].items() if not refused}
    keys |= set(re.findall(r'I18n\.TrF\(%s, d\)' % _LIT, _member(native, "private static string Refused(int status, string d)")))
    keys |= _cases(_member(native, "internal static string TrBracketProgress(string label)"), "label")
    keys |= _cases(_member(native, "private static string TrRoundLabel(string r)"), "r")
    keys |= {"Sync Tournament - {0}", "Async Tournament - {0}", "TOURNAMENT Async", "TOURNAMENT Sync",
             "TOURNAMENT", "PRIVATE", "<color=#66CCFF>searching</color>",
             "<color=#FFD94D>matched</color>", "<color=#88FF88>ready</color>"}
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
