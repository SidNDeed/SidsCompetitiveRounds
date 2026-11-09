"""Bracket names: a player name holding angle brackets keeps its text.

A Steam name such as "<Name>" or "AC<DC>Fan" used to go through a blanket <.*?> strip on every name read and every
name display, so "<Name>" read as "" and the player stayed nameless. GameStateWatcher.CleanPlayerName strips only the
styling tags NametagStyler publishes and turns each remaining angle bracket into an ASCII paren; the display paths
(SpectatorHud.PlainName and SanitizeStyledName, PostSessionReport.PlainPlayerName, the FFA score strip and
NametagStyler.Wrap) keep the same rule.

Checks:
- the cleaner and the styled-name sanitiser, ported here against the tag pattern read from the C# source, with the
  C# bodies pinned statement by statement so the ports cannot drift from them;
- every tag in the styler's own table and its per-character colour runs is in that pattern and cleans back to the
  base (#279: a new tag family extends the pattern in the same commit);
- a sweep of every plugin line for a player-name read through a blanket strip, with a negative control;
- allowlists for the blanket helpers that stay: SanitizeStyled on titles and rank names, StripTags on card names,
  the tag regexes inside their own sanitisers, and NametagStyler.Clean in the renderers' nameplate match;
- the display helpers call CleanPlayerName;
- the nametag styler takes its base name only inside the guard that skips its own published string.
"""
import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
GSW = PLUGIN / "GameStateWatcher.cs"
STYLER = PLUGIN / "NametagStyler.cs"
SPH = PLUGIN / "SpectatorHud.cs"
PSR = PLUGIN / "PostSessionReport.cs"
CUI = PLUGIN / "CompetitiveUI.cs"


def _src(p):
    return p.read_text(encoding="utf-8-sig")


def _block(text, start):
    """(index of the first '{' at or after start, index just past its matching '}')."""
    j = text.index("{", start)
    depth = 0
    for k in range(j, len(text)):
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                return j, k + 1
    raise AssertionError("unbalanced block at %d" % start)


def _method_body(src, signature):
    j, k = _block(src, src.index(signature))
    return [ln.strip() for ln in src[j + 1:k - 1].splitlines() if ln.strip()]


def _known_pattern():
    m = re.search(r'KnownRichTagPattern\s*=\s*@"((?:[^"]|"")*)"', _src(GSW))
    assert m, "KnownRichTagPattern not found in GameStateWatcher.cs"
    return m.group(1).replace('""', '"')


KNOWN_PATTERN = _known_pattern()
KNOWN = re.compile(KNOWN_PATTERN)
NAME_TOKEN = re.compile("(?:" + KNOWN_PATTERN + ")|[<>]")
ALL_TAGS = re.compile(r"<[^>]*>")
KEPT = ("<b>", "</b>", "<i>", "</i>", "</color>")


def strip_known(s):
    return KNOWN.sub("", s).strip()


def clean_player_name(raw):
    if raw is None or raw == "":
        return raw
    s = strip_known(raw)
    if len(s) == 0:
        s = raw.strip()
    return s.replace("<", "(").replace(">", ")")


def sanitize_styled_name(s):
    if s is None or s == "":
        return ""
    plain = clean_player_name(s) or ""
    if not strip_known(s):
        return plain

    def tok(m):
        v = m.group(0)
        if v == "<":
            return "("
        if v == ">":
            return ")"
        if v in KEPT or v.startswith("<color="):
            return v
        return ""

    kept = NAME_TOKEN.sub(tok, s)
    color = bold = italic = 0
    for t in ALL_TAGS.findall(kept):
        if t == "</color>":
            color -= 1
        elif t.startswith("<color="):
            color += 1
        elif t == "<b>":
            bold += 1
        elif t == "</b>":
            bold -= 1
        elif t == "<i>":
            italic += 1
        elif t == "</i>":
            italic -= 1
    return kept if color == 0 and bold == 0 and italic == 0 else plain


def test_csharp_bodies_match_these_ports():
    src = _src(GSW)
    assert _method_body(src, "internal static string CleanPlayerName(string raw)") == [
        "if (string.IsNullOrEmpty(raw)) return raw;",
        "string s = StripKnownRichTags(raw);",
        "if (s.Length == 0) s = raw.Trim();",
        'return s.Replace("<", "(").Replace(">", ")");',
    ]
    assert _method_body(src, "internal static string StripKnownRichTags(string input)") == [
        "if (string.IsNullOrEmpty(input)) return input;",
        'return KnownRichTags.Replace(input, "").Trim();',
    ]
    assert "private static readonly Regex KnownRichTags = new Regex(KnownRichTagPattern, RegexOptions.Compiled);" in src
    sph = _src(SPH)
    assert _method_body(sph, "internal static string SanitizeStyledName(string s)") == [
        'if (string.IsNullOrEmpty(s)) return "";',
        'string plain = GameStateWatcher.CleanPlayerName(s) ?? "";',
        "try",
        "{",
        "if (string.IsNullOrEmpty(GameStateWatcher.StripKnownRichTags(s))) return plain;",
        "string kept = System.Text.RegularExpressions.Regex.Replace(s,",
        '"(?:" + GameStateWatcher.KnownRichTagPattern + ")|[<>]", tok =>',
        "{",
        "string v = tok.Value;",
        'if (v == "<") return "(";',
        'if (v == ">") return ")";',
        'if (v == "<b>" || v == "</b>" || v == "<i>" || v == "</i>" || v == "</color>"',
        '|| v.StartsWith("<color=", StringComparison.Ordinal)) return v;',
        'return "";',
        "});",
        "int color = 0, bold = 0, italic = 0;",
        "foreach (System.Text.RegularExpressions.Match m in _allTagStrip.Matches(kept))",
        "{",
        "string t = m.Value;",
        'if (t == "</color>") color--;',
        'else if (t.StartsWith("<color=", StringComparison.Ordinal)) color++;',
        'else if (t == "<b>") bold++;',
        'else if (t == "</b>") bold--;',
        'else if (t == "<i>") italic++;',
        'else if (t == "</i>") italic--;',
        "}",
        "return color == 0 && bold == 0 && italic == 0 ? kept : plain;",
        "}",
        "catch { return plain; }",
    ]
    # The token pattern NAME_TOKEN ports is the body's own argument, held in no field.
    assert sph.count('"(?:" + GameStateWatcher.KnownRichTagPattern + ")|[<>]"') == 1
    assert "_nameToken" not in sph
    assert re.search(r'_allTagStrip =\s*new System\.Text\.RegularExpressions\.Regex\("<\[\^>\]\*>"', sph)


CASES = [
    ("<Name>", "(Name)"),
    ("AC<DC>Fan", "AC(DC)Fan"),
    ("I <3 U", "I (3 U"),
    ("<color=#55CCFF><b>Bob</b></color>", "Bob"),
    ("<size=130%><i>Bob</i></size>", "Bob"),
    ("<cspace=0.4em><smallcaps>Bob</smallcaps></cspace>", "Bob"),
    ("<b>", "(b)"),
    ("<color=red>Bob</color>", "(color=red)Bob"),
    ("<size=500>X", "(size=500)X"),
    ("   ", ""),
    ("", ""),
    (None, None),
]


def test_clean_player_name_cases():
    for raw, want in CASES:
        assert clean_player_name(raw) == want, (raw, clean_player_name(raw), want)


def test_clean_player_name_is_idempotent_and_holds_no_angle_bracket():
    for raw, _ in CASES:
        once = clean_player_name(raw)
        assert clean_player_name(once) == once, raw
        assert once is None or ("<" not in once and ">" not in once), raw


STYLED_CASES = [
    ("<Name>", "(Name)"),
    ("AC<DC>Fan", "AC(DC)Fan"),
    ("I <3 U", "I (3 U"),
    ("<size=130%><b>Bob</b></size>", "<b>Bob</b>"),
    ("<color=#55CCFF><i>Bob</i></color>", "<color=#55CCFF><i>Bob</i></color>"),
    ("<color=red>Bob</color>", "(color=red)Bob"),
    ("<b></b>", "(b)(/b)"),
    ("<b>Bob", "Bob"),
    ("<voffset=0.2em>(Name)</voffset>", "(Name)"),
    ("   ", ""),
    ("", ""),
]


def test_sanitize_styled_name_cases_and_invariants():
    for raw, want in STYLED_CASES:
        got = sanitize_styled_name(raw)
        assert got == want, (raw, got, want)
        # Visible text is the plain name; only the styler's <b>, <i> and <color=#RRGGBB> runs survive as tags.
        assert strip_known(got) == (clean_player_name(raw) or ""), raw
        assert "<" not in ALL_TAGS.sub("", got) and ">" not in ALL_TAGS.sub("", got), raw
        for t in ALL_TAGS.findall(got):
            assert t in KEPT or re.fullmatch(r"<color=#[0-9A-Fa-f]{6}>", t), (raw, t)


TAG_ROW = re.compile(r'\{\s*"(nametag_[a-z_]+)",\s*\("([^"]*)",\s*"([^"]*)"\)\s*\}')
BASES = ["(Name)", "AC(DC)Fan", "Bob", "(b)"]


def test_every_tag_the_styler_emits_is_known_and_cleans_back():
    sty = _src(STYLER)
    rows = TAG_ROW.findall(sty)
    assert len(rows) >= 25, len(rows)
    for sku, opn, cls in rows:
        assert KNOWN.fullmatch(opn), (sku, opn)
        assert KNOWN.fullmatch(cls), (sku, cls)
        for base in BASES:
            styled = opn + base + cls
            assert clean_player_name(styled) == base, (sku, styled)
            assert strip_known(sanitize_styled_name(styled)) == base, (sku, styled)
    # The per-character builders emit <color=#RRGGBB> runs from ToHtmlStringRGB, six hex digits.
    assert 'sb.Append("<color=#")' in sty
    assert "ToHtmlStringRGB(" in sty and "ToHtmlStringRGBA(" not in sty
    hexes = re.findall(r'"#([0-9A-Fa-f]{6})"', sty)
    assert len(hexes) >= 6
    for base in BASES:
        run = "".join("<color=#%s>%s</color>" % (hexes[i % len(hexes)], ch) for i, ch in enumerate(base))
        assert clean_player_name(run) == base, run
        assert sanitize_styled_name(run) == run, run


# Matched case-insensitively against the call's argument text. The sweep's reach is the argument's own text: a call
# whose argument is a bare local holding a name (`nm`, `raw`) is outside it; the allowlists below hold those helpers.
NAME_TOKENS = ("nick", "personaname", "persona", "display_name", "displayname", "names[", "seatname")
BLANKET = re.compile(r"(?:\bStripRichText|\bNametagStyler\.Clean|\bStripRichTags|(?<![\w.])Clean)\(([^;]*)")
# Renderer matching compares Clean(NickName) with Clean(the nameplate's own text): both sides use the same blanket
# function by design, so these lines are exempt.
EXEMPT = {
    ("NametagGlowRenderer.cs", 'string cleanNick = NametagStyler.Clean(pp.NickName ?? "");'),
    ("NametagFontRenderer.cs", 'string cleanNick = NametagStyler.Clean(pp.NickName ?? "");'),
}


def _comment(t):
    return t.startswith("//") or t.startswith("*") or t.startswith("/*")


def _blanket_name_read(line):
    t = line.strip()
    if _comment(t):
        return False
    for m in BLANKET.finditer(t):
        arg = m.group(1).lower()
        if any(tok in arg for tok in NAME_TOKENS):
            return True
    return False


def test_sweep_matcher_negative_control():
    assert _blanket_name_read('try { name = StripRichText(p.NickName ?? ""); } catch { }')
    assert _blanket_name_read("ownerName = NametagStyler.Clean(pv.Owner.NickName);")
    assert _blanket_name_read("_baseName = Clean(PhotonNetwork.LocalPlayer.NickName);")
    assert _blanket_name_read('string persona = StripRichText(SteamFriends.GetPersonaName() ?? "");')
    assert _blanket_name_read("&& name == StripRichText(opponentDisplayName));")
    assert _blanket_name_read("string clean = NametagStyler.Clean(nickname);")
    assert not _blanket_name_read("try { tc = GameStateWatcher.StripRichText(tc); } catch { }")
    assert not _blanket_name_read('string n = GameStateWatcher.CleanPlayerName(p.NickName ?? "");')


def _plugin_files():
    files = sorted(PLUGIN.glob("*.cs"))
    assert len(files) > 50, "plugin sources not found"
    return files


def test_no_player_name_read_goes_through_a_blanket_strip():
    hits = []
    for f in _plugin_files():
        for n, line in enumerate(_src(f).splitlines(), 1):
            if _blanket_name_read(line) and (f.name, line.strip()) not in EXEMPT:
                hits.append("%s:%d %s" % (f.name, n, line.strip()[:120]))
    assert hits == [], "\n".join(hits)


def _call_args(name_re, define_name=None):
    """(file, line, argument text) for every call matched by name_re (which ends in an open paren)."""
    out = []
    for f in _plugin_files():
        for n, line in enumerate(_src(f).splitlines(), 1):
            t = line.strip()
            if _comment(t):
                continue
            if define_name and re.search(r"static\s+\w+\s+" + define_name + r"\(", t):
                continue
            for m in re.finditer(name_re, t):
                i = k = m.end()
                depth = 1
                while k < len(t) and depth:
                    if t[k] == "(":
                        depth += 1
                    elif t[k] == ")":
                        depth -= 1
                    k += 1
                out.append((f.name, n, t[i:k - 1]))
    return out


def _outside(calls, allowed):
    return ["%s:%d %s" % c for c in calls if (c[2] if isinstance(next(iter(allowed)), str) else (c[0], c[2])) not in allowed]


def test_blanket_helpers_stay_on_their_allowlisted_inputs():
    bad = []
    # SanitizeStyled keeps any <color...> tag and deletes other bracket text: titles and rank names only.
    bad += _outside(_call_args(r"(?<![\w.])SanitizeStyled\(|SpectatorHud\.SanitizeStyled\(", "SanitizeStyled"),
                    {"title", "s.rank_name"})
    # StripTags deletes all bracket text: card names only.
    bad += _outside(_call_args(r"(?<![\w.])StripTags\(", "StripTags"), {"disp"})
    # The tag regexes run only inside their own sanitisers.
    bad += _outside(_call_args(r"\b_allTagStrip\.Replace\(|\b_tagStrip\.Replace\("), {'s, ""', 'kept, ""'})
    # NametagStyler.Clean: the two renderers' nameplate match, both sides.
    bad += _outside(_call_args(r"\bNametagStyler\.Clean\("), {
        ("NametagGlowRenderer.cs", 'pp.NickName ?? ""'), ("NametagGlowRenderer.cs", "rawText"),
        ("NametagFontRenderer.cs", 'pp.NickName ?? ""'), ("NametagFontRenderer.cs", "rawText"),
    })
    bad += ["%s:%d %s" % c for c in _call_args(r"(?<![\w.])Clean\(", "Clean") if c[0] == "NametagStyler.cs"]
    assert bad == [], "\n".join(bad)


def test_display_helpers_use_the_name_rule():
    ffa = "\n".join(_method_body(_src(CUI), "private static string StripFfaHudName(string input, int slot)"))
    assert "string clean = GameStateWatcher.CleanPlayerName(input);" in ffa and "'<'" not in ffa
    plain = "\n".join(_method_body(_src(SPH), "internal static string PlainName(string styled)"))
    assert "GameStateWatcher.CleanPlayerName(styled)" in plain and "_allTagStrip" not in plain
    ppn = "\n".join(_method_body(_src(PSR), "private static string PlainPlayerName(string s)"))
    assert "GameStateWatcher.CleanPlayerName(s)" in ppn and "_allTagStrip" not in ppn
    wrap = "\n".join(_method_body(_src(STYLER), "public static string Wrap(string name, List<string> activeSkus)"))
    assert "string clean = GameStateWatcher.CleanPlayerName(name);" in wrap
    assert "SpectatorHud.SanitizeStyledName(NametagStyler.Wrap(display," in _src(PSR)
    assert "_sb.Append(SanitizeStyledName(names[i]));" in _src(SPH)
    assert "SpectatorHud.SanitizeStyledName(sb.ToString())" in _src(CUI)


def test_styler_takes_its_base_only_inside_the_guard():
    body = "\n".join(_method_body(_src(STYLER), "public static void PublishToPhoton()"))
    g = body.index("if (nick != _lastPublished)")
    j, k = _block(body, g)
    assert body[g:j].strip() == "if (nick != _lastPublished)", "the guard's block must follow it directly"
    block, outside = body[j:k], body[:j] + body[k:]
    assert "GameStateWatcher.CleanPlayerName(nick" in block
    assert "_baseName = cleanBase;" in block
    assert "_baseName =" not in outside and "CleanPlayerName(" not in outside
    publish = body.index("PhotonNetwork.LocalPlayer.NickName = styled;")
    record = body.index("_lastPublished = styled;")
    assert k <= publish < record
    assert body.count("_lastPublished = styled;") == 1
