"""The Titles tab's client half: which 404 it believes, and what language it
renders a name in.

Two defects and one carried LOW, all visible to a passive player and none of
them visible to a screenshot of a working account.

1. EVERY 404 was read as "this server does not serve the ladder route yet".
   The route answers 404 for an UNKNOWN ACCOUNT too -- which is every account
   until it buys an entry rung -- so a new player was told the service was
   broken. The route is served: main.py calls include_router for it, a claim
   the module's own docstring denied for releases.
2. Rung and line names arrive as server data, so no call site carries them as
   a literal and the extractor cannot harvest them. They were interpolated raw
   into translated templates, so a Spanish player read "Puesto: Rat Queen"
   while the SHOP, which renders the same shop_items rows through I18n, showed
   the translated name.
3. Opening the tab built a synthetic JSON document and ran assertions over it
   on every seat. That is test work on a release path.

The 404 classification is a pure function of the response text, so it is
asserted here by READING the rule's branches -- the executed half would need
ApiClient's whole JSON helper family, which is why the parser self-check could
not move into tools/client-rules-harness either.
"""
import io
import json
import os
import re

import pytest

from _cs_structure import code_of

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def _plugin(name):
    with io.open(os.path.join(REPO, "plugin", name), encoding="utf-8") as fh:
        return fh.read()


def _server(name):
    with io.open(os.path.join(REPO, "backend", "api", name), encoding="utf-8") as fh:
        return fh.read()


# ── 1. the 404 is classified three ways ───────────────────────────────────

def test_the_failure_classifier_has_three_outcomes():
    body = code_of(_plugin("ApiClient.cs"),
                   "internal static string TitleLadderFailure(string response)")
    for outcome in ('"transport"', '"empty"', '"route"'):
        assert outcome in body, "TitleLadderFailure can never answer %s" % outcome
    # "empty" twice: the exact case (the marker) and the presumed case (a JSON
    # body without it). One occurrence means one of them was folded away.
    assert body.count('"empty"') == 2, (
        "the exact and presumed no-account cases are no longer distinct: " + body)


def test_the_marker_is_tested_before_the_body_shape():
    """The marker PROVES the route answered. The body-shape test is a
    judgement about a 404 that carries no marker. Reversing them would decide
    by the weaker signal first and never consult the stronger one."""
    body = code_of(_plugin("ApiClient.cs"),
                   "internal static string TitleLadderFailure(string response)")
    assert body.index("LadderNoAccountMarker") < body.index("IndexOf('{')"), body


def test_the_marker_is_one_constant_on_both_sides():
    """A literal on either side is how the two halves drift apart, and the
    client's would drift silently: it would simply stop matching and every new
    account would go back to reading "the service is unavailable"."""
    client = _plugin("ApiClient.cs")
    server = _server("title_ladders.py")
    m = re.search(r'LadderNoAccountMarker\s*=\s*"([^"]+)"', client)
    assert m, "the client no longer names the marker in one place"
    marker = m.group(1)
    s = re.search(r'NO_ACCOUNT_MARKER\s*=\s*"([^"]+)"', server)
    assert s, "the server no longer names the marker in one place"
    assert s.group(1) == marker, (
        "client %r != server %r" % (marker, s.group(1)))
    # And it appears in no player-facing text on either side: the value of a
    # probe is that nothing else has a reason to touch it (#306).
    assert client.count('"%s"' % marker) == 1, (
        "the client carries a second copy of the marker")
    assert server.count('"%s"' % marker) == 1, (
        "the server carries a second copy of the marker")


def test_the_route_404_carries_the_marker():
    # Read as text, not through code_of: that masker reads C#, and a Python
    # file full of apostrophes is not a C# character literal.
    body = _server("title_ladders.py")
    hit = [l for l in body.splitlines() if "status_code=404" in l]
    assert hit, "the route no longer answers 404 for an unknown account"
    window = body[body.index("status_code=404"):][:300]
    assert "NO_ACCOUNT_MARKER" in window, (
        "the route's 404 does not carry the marker the client keys on: " + window)


def test_the_tab_says_something_different_for_each_outcome():
    body = code_of(_plugin("TitleLaddersUI.cs"), "private static string EmptyText()")
    for code in ('"route"', '"empty"', '"parse"'):
        assert code in body, "EmptyText has no branch for %s" % code
    texts = re.findall(r'I18n\.Tr\("([^"]+)"\)', body)
    assert len(texts) == len(set(texts)), (
        "two outcomes render the same sentence, so the player cannot tell "
        "them apart: %r" % texts)
    assert len(texts) >= 4, texts


def test_the_router_claim_in_the_module_docstring_is_true():
    """#432: the highest-risk comment names a mechanism a later change killed.
    This one told a reader the route could not be the source of a 404 they
    were looking at -- which is exactly the deduction the client made."""
    server = _server("title_ladders.py")
    doc = server[:server.index("from fastapi import")]
    assert "never calls ``include_router``" not in doc, "the false claim is back"
    assert "does not import it AT ALL" not in doc
    main = _server("main.py")
    assert "app.include_router(title_ladders.router)" in main, (
        "the route is no longer served; the docstring correction is now wrong "
        "in the other direction")


# ── 2. server-provided names are translated ───────────────────────────────

def test_every_composed_name_goes_through_the_translation_helper():
    """A name passed WHOLE to UIFactory.SetText is translated there -- SetText
    is the L10n chokepoint. A name INTERPOLATED into a template is not: the
    composed result is not a catalogue key and never matches one. So every
    `.name` / `next_names` reading that lands inside an I18n.TrF argument list
    has to be wrapped."""
    src = code_of(_plugin("TitleLaddersUI.cs"))
    bad = []
    for call in re.findall(r"I18n\.TrF\((.*?)\);", src, re.S):
        for raw in re.findall(r"(?<!LadderName\()\b(\w+)\.name\b", call):
            bad.append(call.strip()[:90])
        if "next_names" in call and "LadderName(" not in call:
            bad.append(call.strip()[:90])
    assert not bad, "raw server names interpolated into a translated template: %r" % bad


def test_the_joined_next_names_are_translated_before_the_join():
    body = code_of(_plugin("TitleLaddersUI.cs"),
                   "private static void PaintLine(LineCard card, ApiClient.TitleLadderLine ln)")
    assert 'string.Join(" / ", ln.next_names)' not in body, (
        "the next-rung names are joined raw; the joined string is not a "
        "catalogue key and can never be translated")
    assert "LadderName(ln.next_names[" in body, body


def test_the_equip_comparison_value_stays_raw():
    """`wanted` is echoed back into the success message AND is the name the
    server was asked for. Translating it at the assignment would translate it
    twice, since the echo is composed like every other site."""
    src = code_of(_plugin("TitleLaddersUI.cs"))
    assert "string wanted = r.name;" in src, (
        "the equip comparison value is no longer the raw server name")


def test_the_helper_documents_its_fallback():
    body = code_of(_plugin("TitleLaddersUI.cs"),
                   "private static string LadderName(string serverName)")
    assert "I18n.Tr(" in body
    # Null/empty in, same value out: a name the server omitted must not become
    # a lookup of the empty string.
    assert "string.IsNullOrEmpty(serverName)" in body, body
    # And a throw cannot escape into a repaint.
    assert "catch" in body, body


def _ladder_names():
    """The 48 display names, DERIVED from the catalogue rather than listed."""
    src = _server("title_ladders.py")
    block = src[src.index("LADDERS = ["):src.index("# ── Derived indexes")]
    names = []
    for _, display, body in re.findall(r'_line\("(\w+)", "([^"]+)", \[(.*?)\]\)',
                                       block, re.S):
        names.append(display)
        names.extend(m.group(1) for m in
                     re.finditer(r'\(\d+, (?:None|"\w+"), "([^"]+)",', body))
    return sorted(set(names))


def test_the_catalogue_defines_forty_eight_distinct_names():
    names = _ladder_names()
    assert len(names) == 48, "the ladder catalogue changed shape: %d names" % len(names)


def test_every_ladder_name_is_registered_for_extraction():
    """Server-data display strings are unharvestable from a call site, so they
    are ingested from tools/shop_strings.json. A name missing there is a name
    the translation pipeline never sees (#357)."""
    with io.open(os.path.join(REPO, "tools", "shop_strings.json"),
                 encoding="utf-8") as fh:
        registered = set(json.load(fh)["strings"])
    missing = [n for n in _ladder_names() if n not in registered]
    assert not missing, "%d ladder name(s) not in shop_strings.json: %r" % (
        len(missing), missing[:5])
    with io.open(os.path.join(REPO, "tools", "i18n_source.json"),
                 encoding="utf-8") as fh:
        extracted = set(json.load(fh)["strings"])
    missing = [n for n in _ladder_names() if n not in extracted]
    assert not missing, (
        "%d ladder name(s) did not survive extraction -- re-run "
        "tools/i18n_extract.py: %r" % (len(missing), missing[:5]))


LOCALES = ("es", "ru", "uk", "sv")

# A handful of these names are loanwords that are spelled the same in the
# target language, so their catalogue entry legitimately equals the English
# key. The allowance is PER LOCALE and exhaustive: a locale-blind allowance
# would also excuse a Russian entry that had quietly become an echo, which is
# the exact failure this test exists to catch (#342).
SAME_WORD = {
    "es": ("Grizzly",),
    "ru": (),
    "uk": (),
    "sv": ("Grizzly", "Megalodon"),
}


@pytest.mark.parametrize("lang", LOCALES)
def test_every_ladder_name_is_translated_in_every_locale(lang):
    """The artifact that RENDERS is the DLL-bundled catalogue, never a SQL
    seed (#583). A key with no entry renders English with every other gate
    green (#578)."""
    from test_pc_sept12 import _bundled_catalogues
    catalogue = _bundled_catalogues()
    assert lang in catalogue, "no %s dictionary in I18nCatalogues.cs" % lang
    missing, echoed = [], []
    for name in _ladder_names():
        value = catalogue[lang].get(name)
        if not value or not value.strip():
            missing.append(name)
        elif value == name and name not in SAME_WORD[lang]:
            # Every echo outside the allowance is an untranslated key wearing
            # a translation's clothes.
            echoed.append(name)
    assert not missing, "%s: no entry for %r" % (lang, missing[:5])
    assert not echoed, "%s: still the English string for %r" % (lang, echoed[:5])
    stale = [n for n in SAME_WORD[lang] if catalogue[lang].get(n) != n]
    assert not stale, (
        "%s: %r is in the same-word allowance but now HAS a distinct "
        "translation -- drop it from SAME_WORD so the allowance keeps "
        "excusing nothing it does not have to" % (lang, stale))


# ── 3. the parser self-check is off the release path ──────────────────────

def test_the_parser_self_check_is_behind_a_lever():
    body = code_of(_plugin("TitleLaddersUI.cs"), "internal static void OnTabEntered()")
    assert "SelfCheckOnce()" in body, "the self-check was deleted rather than gated"
    assert "SelfCheckLever()" in body, (
        "opening the Titles tab still runs the parser self-check unconditionally")
    call = body[body.index("SelfCheckOnce()") - 60:body.index("SelfCheckOnce()")]
    assert "if (" in call and "SelfCheckLever()" in call, (
        "the lever is read but does not gate the call: " + call)


def test_the_lever_defaults_to_off_and_fails_closed():
    body = code_of(_plugin("TitleLaddersUI.cs"), "private static bool SelfCheckLever()")
    assert '"Debug", "TitleLadderParserSelfCheck"' in body, body
    # The default sits immediately after the key, and it must be false.
    after = body[body.index('"TitleLadderParserSelfCheck"'):][:120]
    assert re.search(r'"TitleLadderParserSelfCheck",\s*\n?\s*false', after), after
    assert "catch { return false; }" in body, (
        "an unreadable lever must not enable the check")
    # Bound once: retrying the bind on every tab entry puts the failure back
    # on the path a player touches.
    assert "selfCheckLeverBound" in body, body
