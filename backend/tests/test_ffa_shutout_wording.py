"""The three ranked-FFA shutout tiers count the players who FINISHED the game
(the ffa-trophies rule on main: a player who left early or never showed up is
not counted). Their descriptions say so in both places a player reads them --
the client's AchievementDefs (plugin/ApiClient.cs) and the server's
ACHIEVEMENT_DEFS (backend/api/main.py) -- identically, and every shipped
language carries a draft for each new English key (the old keys' drafts were
replaced, since they described the seated-roster rule).

Source-reading only: nothing here needs a database or the game. The negative
control runs the same predicate over the pre-rule wording and must reject it.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "plugin" / "ApiClient.cs"
MAIN = ROOT / "backend" / "api" / "main.py"
CATS = ROOT / "plugin" / "I18nCatalogues.cs"
KEYS = ("ffa_shutout_3", "ffa_shutout_4", "ffa_shutout_5")
OLD = "Win a ranked FFA 5-0 with %d or more players (nobody else takes a point)"


def _client_desc(src, key):
    m = re.findall(r'\{"%s",\s*new\[\]\{"[^"]*",\s*"([^"]*)"\}\}' % key, src)
    assert len(m) == 1, "%s occurs %d times in AchievementDefs" % (key, len(m))
    return m[0]


def _server_desc(src, key):
    m = re.findall(r'"%s":\s*\{"name": "[^"]*",\s*"desc": "([^"]*)"\}' % key, src)
    assert len(m) == 1, "%s occurs %d times in ACHIEVEMENT_DEFS" % (key, len(m))
    return m[0]


def _says_finished(desc, n):
    return ("with %d or more players who finished the game" % n) in desc and "nobody else takes a point" in desc


def test_both_sides_say_the_players_finished_and_agree():
    api = API.read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")
    for n, key in zip((3, 4, 5), KEYS):
        c, s = _client_desc(api, key), _server_desc(main, key)
        assert c == s, "%s: the client says %r, the server %r" % (key, c, s)
        assert _says_finished(c, n), "%s does not say the players finished: %r" % (key, c)
        assert all(ord(ch) < 128 for ch in c), "%s: ROUNDS' SDF font has no glyph for a non-ASCII character" % key


def test_the_pre_rule_wording_fails_the_same_predicate():
    for n in (3, 4, 5):
        assert not _says_finished(OLD % n, n)


@pytest.mark.parametrize("lang", ["ES", "RU", "UK", "SV"])
def test_every_language_has_a_draft_for_each_new_key_and_none_for_the_old(lang):
    src = CATS.read_text(encoding="utf-8")
    decl = "private static readonly Dictionary<string, string> %s = new Dictionary<string, string>" % lang
    assert src.count(decl) == 1
    body = src[src.index(decl):]
    nxt = re.search(r"private static readonly Dictionary<string, string> \w+ = ", body[len(decl):])
    body = body[:len(decl) + nxt.start()] if nxt else body
    api = API.read_text(encoding="utf-8")
    for n, key in zip((3, 4, 5), KEYS):
        new = _client_desc(api, key)
        m = re.findall(r'\["%s"\] = "([^"]+)",' % re.escape(new), body)
        assert len(m) == 1 and m[0].strip(), "%s has no single draft for %r" % (lang, new)
        assert ('["%s"]' % (OLD % n)) not in body, "%s still carries the seated-roster draft for %s" % (lang, key)
