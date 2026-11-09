"""Bracket names: a player name holding angle brackets keeps its text.

A Steam name such as "<Name>" or "AC<DC>Fan" used to go through a blanket <.*?> strip on every name read, so
"<Name>" read as "" and the player stayed nameless. GameStateWatcher.CleanPlayerName now strips only the styling
tags NametagStyler publishes and turns each remaining angle bracket into an ASCII paren.

Three checks:
- the cleaner's behaviour, run here against the KnownRichTags pattern read from the C# source, with the C# method
  bodies pinned statement by statement so this port cannot drift from them;
- a sweep of every plugin line for a player-name read that still goes through a blanket strip, with a negative
  control proving the sweep's matcher flags such a line;
- the nametag styler never parses its own published string back into its base name.
"""
import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
GSW = PLUGIN / "GameStateWatcher.cs"
STYLER = PLUGIN / "NametagStyler.cs"


def _src(p):
    return p.read_text(encoding="utf-8-sig")


def _method_body(src, signature):
    i = src.index(signature)
    j = src.index("{", i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return [ln.strip() for ln in src[j + 1:k].splitlines() if ln.strip()]
    raise AssertionError("unbalanced body: " + signature)


def _known_tags_regex():
    m = re.search(r'KnownRichTags\s*=\s*new Regex\(\s*@"((?:[^"]|"")*)"', _src(GSW))
    assert m, "KnownRichTags pattern not found in GameStateWatcher.cs"
    return re.compile(m.group(1).replace('""', '"'))


KNOWN = _known_tags_regex()


def strip_known(s):
    return KNOWN.sub("", s).strip()


def clean_player_name(raw):
    if raw is None or raw == "":
        return raw
    s = strip_known(raw)
    if len(s) == 0:
        s = raw.strip()
    return s.replace("<", "(").replace(">", ")")


def test_csharp_bodies_match_this_port():
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


RAINBOW = ["#FF5566", "#FFB347", "#FFEE55", "#88FF99", "#55CCFF", "#BB88FF"]


def _rainbow(base):
    return "".join("<color=%s>%s</color>" % (RAINBOW[i % 6], ch) for i, ch in enumerate(base))


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


def test_styled_publish_round_trips_to_its_base():
    # The styler builds from an already-cleaned base; cleaning what it publishes returns that base.
    for raw in ["<Name>", "AC<DC>Fan", "Bob", "<b>"]:
        base = clean_player_name(raw)
        for styled in (_rainbow(base), "<color=#FFCC44><u>%s</u></color>" % base):
            assert clean_player_name(styled) == base, (raw, styled)


# Matched case-insensitively against the call's argument text. The sweep's reach is the argument's own text: a call
# whose argument is a bare local holding a name (`nm`, `raw`) is outside it, so those sites are held by review.
NAME_TOKENS = ("nick", "personaname", "persona", "display_name", "displayname", "names[", "seatname")
BLANKET = re.compile(r"(?:\bStripRichText|\bNametagStyler\.Clean|\bStripRichTags|(?<![\w.])Clean)\(([^;]*)")
# Renderer matching compares Clean(NickName) with Clean(the nameplate's own text): both sides use the same blanket
# function by design, so these two lines per renderer are exempt.
EXEMPT = {
    ("NametagGlowRenderer.cs", 'string cleanNick = NametagStyler.Clean(pp.NickName ?? "");'),
    ("NametagFontRenderer.cs", 'string cleanNick = NametagStyler.Clean(pp.NickName ?? "");'),
}


def _blanket_name_read(line):
    t = line.strip()
    if t.startswith("//") or t.startswith("*") or t.startswith("/*"):
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


def test_no_player_name_read_goes_through_a_blanket_strip():
    hits = []
    files = sorted(PLUGIN.glob("*.cs"))
    assert len(files) > 50, "plugin sources not found"
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8-sig").splitlines(), 1):
            if _blanket_name_read(line) and (f.name, line.strip()) not in EXEMPT:
                hits.append("%s:%d %s" % (f.name, n, line.strip()[:120]))
    assert hits == [], "\n".join(hits)


def test_styler_never_parses_its_own_published_string():
    body = "\n".join(_method_body(_src(STYLER), "public static void PublishToPhoton()"))
    guard = body.index("if (nick != _lastPublished)")
    read = body.index("GameStateWatcher.CleanPlayerName(nick")
    publish = body.index("PhotonNetwork.LocalPlayer.NickName = styled;")
    record = body.index("_lastPublished = styled;")
    assert guard < read < publish < record
    assert body.count("_lastPublished = styled;") == 1
    assert "Clean(PhotonNetwork.LocalPlayer.NickName)" not in body
