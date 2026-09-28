"""Board rows 27 and 33a (the portal re-probe lane): the source-level half.

The secure-route decisions and every sentence they show a player are EXECUTED
by tools/client-rules-harness (suite "secureroute", wrapped by
test_client_rules_harness.py). This module holds what only the source can
show: where the scrmod.com button sits in the F5 footer row and how it opens,
and that its label and the new sentence keys are in every catalogue.
"""
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NATIVE = os.path.join(ROOT, "plugin", "NativeUI.cs")
CATALOGUES = os.path.join(ROOT, "plugin", "I18nCatalogues.cs")
SOURCE = os.path.join(ROOT, "tools", "i18n_source.json")
LOCALES = ("ES", "RU", "UK", "SV")
LINKS = ["Discord", "GitHub", "YouTube", "Twitch", "Thunderstore", "ScrMod"]
HOLE = re.compile(r"\{\d+\}")


def _read(path):
    with io.open(path, encoding="utf-8-sig") as fh:
        return fh.read().replace("\r\n", "\n")


def _footer():
    """The F5 footer row as BuildPage builds it: from the "Bottom" row's
    creation to the page-built flag, and the CreateButton calls parented to
    that row, in build order, as (object name, label, call text)."""
    src = _read(NATIVE)
    start = src.index('var bottom=new GameObject("Bottom")')
    end = src.index("pageBuilt=true;", start)
    body = src[start:end]
    calls = []
    for m in re.finditer(r'UIFactory\.CreateButton\("([^"]+)",bottom\.transform,"([^"]*)"', body):
        line_end = body.index("\n", m.start())
        calls.append((m.group(1), m.group(2), body[m.start():line_end]))
    return calls


def _dictionary(src, locale):
    """One catalogue's body, from its declaration to its closing brace."""
    head = "private static readonly Dictionary<string, string> %s = " % locale
    at = src.index(head)
    end = src.index("\n        };", at)
    return src[at:end]


def _cs_unescape(lit):
    out, i = [], 0
    while i < len(lit):
        c = lit[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        n = lit[i + 1]
        if n == "u":
            out.append(chr(int(lit[i + 2:i + 6], 16)))
            i += 6
            continue
        out.append({"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"', "0": "\0"}.get(n, n))
        i += 2
    return "".join(out)


def _entry(body, key):
    """Every value the dictionary body gives `key` (a plain ASCII key with no
    escapes), decoded from its C# literal."""
    needle = '["%s"] = "' % key
    values, at = [], body.find(needle)
    while at >= 0:
        i = at + len(needle)
        j = i
        while body[j] != '"':
            j += 2 if body[j] == "\\" else 1
        values.append(_cs_unescape(body[i:j]))
        at = body.find(needle, j)
    return values


def test_the_scrmod_button_is_built_once_directly_after_thunderstore():
    calls = _footer()
    names = [n for n, _, _ in calls]
    assert names.count("ScrMod") == 1, names
    first = names.index("Discord")
    assert names[first:first + len(LINKS)] == LINKS, (
        "the footer links must read %s, in that order; found %s" % (LINKS, names))


def test_the_scrmod_button_opens_the_site_the_way_its_siblings_open_theirs():
    by_name = {n: (label, text) for n, label, text in _footer()}
    label, text = by_name["ScrMod"]
    assert label == "scrmod.com"
    # The same factory call as its siblings: CreateButton wraps the handler in
    # the per-control ClickGuard debounce, and these buttons are the mod's own,
    # so there is no cloned ROUNDS component (QuitButton) to strip.
    assert 'Application.OpenURL("https://scrmod.com/")' in text, text
    sibling = by_name["Thunderstore"][1]
    assert "Application.OpenURL(" in sibling and "14f,Color.white," in sibling and "14f,Color.white," in text
    assert _read(NATIVE).count("https://scrmod.com/") == 1


def test_the_scrmod_label_reads_the_same_in_every_catalogue():
    src = _read(CATALOGUES)
    for locale in LOCALES:
        values = _entry(_dictionary(src, locale), "scrmod.com")
        assert values == ["scrmod.com"], "%s: %r" % (locale, values)
    assert "scrmod.com" in json.load(io.open(SOURCE, encoding="utf-8"))["strings"]


def test_every_secure_route_sentence_is_a_key_in_every_catalogue():
    contexts = json.load(io.open(SOURCE, encoding="utf-8"))["contexts"]
    keys = sorted(k for k, v in contexts.items() if "SecureRouteText" in v.get("surface", ""))
    # The ten sentences of plugin/SecureRouteText.cs, plus the sign-in toast
    # whose "until it is back" the checks made true (ApiClient.PostSteamAuth).
    keys.append("Secure connection unavailable - signed-in features are off until it is back.")
    assert len(keys) == 11, keys
    src = _read(CATALOGUES)
    for locale in LOCALES:
        body = _dictionary(src, locale)
        for key in keys:
            values = _entry(body, key)
            assert len(values) == 1, "%s: %d entries for %r" % (locale, len(values), key)
            value = values[0]
            assert value.strip() and value != key, "%s: %r is not translated" % (locale, key)
            assert sorted(HOLE.findall(value)) == sorted(HOLE.findall(key)), (
                "%s: the holes of %r moved: %r" % (locale, key, value))
