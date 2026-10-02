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

from _cs_structure import code_of, strip_comments_only

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def _plugin(name):
    with io.open(os.path.join(REPO, "plugin", name), encoding="utf-8") as fh:
        return fh.read()


def _server(name):
    with io.open(os.path.join(REPO, "backend", "api", name), encoding="utf-8") as fh:
        return fh.read()


# ── 1. the 404 is classified three ways ───────────────────────────────────

SIG = "internal static string TitleLadderFailure(string response)"


def _marker_literal():
    src = _plugin("ApiClient.cs")
    m = re.search(r'LadderNoAccountMarker\s*=\s*"([^"]+)"', src)
    assert m, "the marker constant moved"
    return m.group(1)


def _classify(response):
    """TitleLadderFailure, driven from its OWN source.

    Not a second copy of the rule: each branch below is located in the
    production method and the OUTCOME IT RETURNS is read out of it, so
    exchanging the two 404 answers, dropping a branch or reversing a test
    changes what this function returns. Written this way because ApiClient.cs
    is a Unity type and cannot be executed here -- and because a test that
    merely checks the three literals are PRESENT passes with them swapped,
    which is the finding this closes.
    """
    body = code_of(_plugin("ApiClient.cs"), SIG)
    code = " ".join(body.split())
    m = re.search(r'if \(string\.IsNullOrEmpty\(response\)\) return "(\w+)";', code)
    assert m, "the empty-response branch is gone: " + code
    if not response:
        return m.group(1)
    m404 = re.search(r'if \(response\.IndexOf\("HTTP 404".*?\) < 0\) return (\w+);', code)
    assert m404, "the not-a-404 branch is gone: " + code
    if "HTTP 404" not in response:
        assert m404.group(1) == "response", (
            "a non-404 failure is being relabelled rather than passed through")
        return response
    mk = re.search(
        r'return response\.IndexOf\(LadderNoAccountMarker.*?(>=|<) 0 \? "(\w+)" : "(\w+)";',
        code)
    assert mk, "the marker branch is gone or no longer decides the 404: " + code
    # The comparator is read, not assumed, so that inverting it moves the
    # MAPPING rather than making this helper fail to parse its own source.
    present, absent = (mk.group(2), mk.group(3)) if mk.group(1) == ">="         else (mk.group(3), mk.group(2))
    return present if _marker_literal() in response else absent


@pytest.mark.parametrize("response,expected", [
    (None, "transport"),
    ("", "transport"),
    ('HTTP 404: {"detail":{"error":"@MARKER@"}}', "empty"),
    ('HTTP 404: {"detail":"Not Found"}', "route"),
    ("HTTP 404: Not Found", "route"),
])
def test_the_classifier_maps_each_answer_to_the_right_outcome(response, expected):
    """The MAPPING, not the vocabulary.

    The two 404 rows are the pair the tab's behaviour hangs on. A 404 carrying
    the route's own marker means "this account has no ladder yet", and the tab
    offers the entry rung. A 404 WITHOUT it means the request never reached the
    ladder route, and the tab must say the service is unavailable -- offering
    to sell an entry rung there is an offer against a server that cannot
    honour it.

    The fourth row is the one the previous round got wrong: an ordinary
    FastAPI 404 body is JSON, so a classifier that decided on the presence of
    `{` read "unavailable service" as "no account yet".
    """
    if response:
        response = response.replace("@MARKER@", _marker_literal())
    assert _classify(response) == expected


def test_the_classifier_does_not_decide_on_the_body_being_json():
    """The marker is the only thing that distinguishes the ladder route's own
    404, because it exists for no other purpose (#306). Any test on the body's
    SHAPE answers the same way for every FastAPI 404 in the stack."""
    body = code_of(_plugin("ApiClient.cs"), SIG)
    for shape in ("IndexOf('{')", 'IndexOf("{"', 'StartsWith("{"', 'Contains("{"'):
        assert shape not in body, (
            "the classifier is deciding by the body being JSON again: " + body)
    assert "LadderNoAccountMarker" in body, "the marker is no longer consulted"


def test_the_fetch_caller_classifies_through_the_helper():
    """The helper is worth nothing if the one failure path does not use it. A
    caller that assigned the raw response, or its own literal, leaves every
    assertion above green."""
    body = code_of(_plugin("ApiClient.cs"),
                   "public static void FetchTitleLadders(string steamId, bool force = false)")
    assigns = [l.strip() for l in body.splitlines() if "TitleLaddersError =" in l]
    assert assigns, "FetchTitleLadders no longer sets the error code"
    failure = [l for l in assigns if "TitleLadderFailure(" in l]
    assert len(failure) == 1, (
        "the failure branch does not go through TitleLadderFailure: %r" % assigns)
    # Every OTHER assignment in the method is a success-path write: the clear
    # at the top of a good answer, and the one literal for a 200 that carried
    # no ladders array. A third literal here would be a second classifier
    # nobody is testing.
    others = sorted(l for l in assigns if "TitleLadderFailure(" not in l)
    assert others == ['TitleLaddersError = "parse";', "TitleLaddersError = null;"], (
        "an unclassified error code is assigned beside the helper: %r" % others)


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
    # A server name does not have to arrive as `x.name`. The equip path holds
    # it in a local first -- `string wanted = r.name;` -- precisely so the
    # "putting on" line and the success line name the same thing, and a local
    # is invisible to a scan that only knows the field. That alias is what the
    # previous round missed: reverting `LadderName(wanted)` to a bare `wanted`
    # stayed green while the success line went out untranslated.
    aliases = set(re.findall(r"\bstring\s+(\w+)\s*=\s*\w+\.name\s*;", src))
    assert aliases, (
        "no local alias of a server name was found -- either the equip path "
        "changed shape or this scan has stopped seeing it")
    bad = []
    for call in re.findall(r"I18n\.TrF\((.*?)\);", src, re.S):
        for alias in aliases:
            if re.search(r"(?<!LadderName\()\b" + alias + r"\b", call):
                bad.append(call.strip()[:90])
        for raw in re.findall(r"(?<!LadderName\()\b(\w+)\.name\b", call):
            bad.append(call.strip()[:90])
        if "next_names" in call and "LadderName(" not in call:
            bad.append(call.strip()[:90])
    assert not bad, "raw server names interpolated into a translated template: %r" % bad


def test_the_joined_next_names_are_translated_before_the_join():
    """Two rungs can share a tier (the rat line's fourth), so the popup's
    caption and footer JOIN the names of the tier the button is about. Each
    name must be translated BEFORE the join: the joined string is not a
    catalogue key and can never match one.

    Item 12 follow-up: the join left the retired tab's PaintLine for
    TierNames, which reads the rungs AT a tier instead of the answer's
    next_names -- the tier the button is about comes from ownership, and the
    answer's next tier comes from games, so reading next_names would caption
    a different tier than the button buys."""
    src = _plugin("TitleLaddersUI.cs")
    body = code_of(src, "private static string TierNames(ApiClient.TitleLadderLine ln, int tier)")
    assert "string.Join(" not in body, (
        "the tier names are joined raw; the joined string is not a "
        "catalogue key and can never be translated")
    assert re.search(r"\+\s*LadderName\(r\.name\)", body), body
    assert "next_names" not in code_of(src), (
        "a caller reads the answer's raw next_names again")


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


def _catalogue():
    """The server's ladder catalogue, IMPORTED rather than regex-read: the
    five-tier build (board row 29) writes LADDERS as data, not as _line()
    calls, and a parser of either spelling reads nothing from the other."""
    import title_ladders
    return title_ladders.LADDERS


def _ladder_names():
    """Every string the client translates from the catalogue, DERIVED from
    it rather than listed: the ladder display names, the tier names, and
    (five-tier build) each ladder's condition, which the dropdown shows."""
    names = []
    for line in _catalogue():
        names.append(line["display"])
        if line.get("condition"):
            names.append(line["condition"])
        names.extend(r["name"] for r in line["rungs"])
    return sorted(set(names))


# The catalogue's shape, keyed by its ladder count: the eight six-rung animal
# lines before the five-tier build (48 names), and the five-tier build's 32
# ladders (32 displays, 160 tiers and 19 conditions, with repeats removed).
EXPECTED_NAMES = {8: 48, 32: 192}


def test_the_catalogue_has_the_expected_number_of_distinct_names():
    ladders = len(_catalogue())
    names = _ladder_names()
    assert ladders in EXPECTED_NAMES, "the ladder catalogue changed shape: %d ladders" % ladders
    assert len(names) == EXPECTED_NAMES[ladders], (
        "the ladder catalogue changed shape: %d names for %d ladders" % (len(names), ladders))


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
#
# Five-tier build (board row 29): the catalogue reuses words the bundled
# catalogues ALREADY carry as echoes, and I18n.Tr is one flat dictionary, so
# the ladder renders whatever that entry says. Card names (Poison, Toxic
# Cloud, Huge, Bouncy, Echo, Tank) are kept English everywhere, as ROUNDS
# shows them; Windup and the older shop titles (Sniper, Berserker, Blitz,
# Phoenix, Apex, Clown, Idiot, Midas, Noobie, Tryhard) kept the English word
# in these locales before this build. Re-translating one here would change
# every other surface that shows it, so they are listed, per locale.
ALL_LOCALE_ECHOES = ("Poison", "Toxic Cloud", "Huge", "Bouncy", "Echo", "Windup")
SAME_WORD = {
    "es": ("Grizzly", "Supernova") + ALL_LOCALE_ECHOES + (
        "Sniper", "Berserker", "Blitz", "Phoenix", "Apex", "Midas", "Noobie", "Tryhard"),
    "ru": ALL_LOCALE_ECHOES,
    "uk": ALL_LOCALE_ECHOES,
    "sv": ("Grizzly", "Megalodon", "Supernova", "Tank") + ALL_LOCALE_ECHOES + (
        "Blitz", "Apex", "Clown", "Idiot", "Midas", "Tryhard"),
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

SELF_CHECK_NAMES = ("SelfCheckOnce", "SelfCheckLever", "selfChecked",
                    "selfCheckLever", "selfCheckLeverBound",
                    "TitleLadderParserSelfCheck")


def test_the_parser_self_check_is_not_in_the_shipped_type_at_all():
    """Round two gated it behind a default-off Debug lever. That still ships
    the fixture, the parser driver and the config entry in every player's DLL,
    and a lever is one config edit away from running a developer harness on a
    player's machine. The disposition here is deletion: the parser is
    exercised by tests that run on a build machine, which is where a fixture
    belongs.

    Names AND the fixture's own sku, because removing the methods while
    leaving the canned body behind would keep the payload in the binary. The
    same sku is scanned for in the built DLL -- see ai-collab/CLIENT-R3-NOTES.md.
    """
    src = _plugin("TitleLaddersUI.cs")
    code = code_of(src)
    for name in SELF_CHECK_NAMES:
        assert name not in code, (
            "%s is back in the shipped type -- the self-check fixture ships "
            "again" % name)
    # Comments stripped, literals kept: the sku appears in the note recording
    # the removal (and in the DLL scan that pins it), and a check that reds on
    # its own explanation is a check whose next fix is to delete the
    # explanation.
    literals = strip_comments_only(src)
    for literal in ("title_ladder_rat_4_queen", "active_line"):
        assert literal not in literals, (
            "the self-check's canned response is still in the source: %s" % literal)
    # Item 12 follow-up: the Titles tab is gone; entering the Shop is what
    # asks for a board now.
    entered = code_of(src, "internal static void OnShopEntered()")
    for name in SELF_CHECK_NAMES:
        assert name not in entered, (
            "entering the Shop still reaches %s" % name)


def test_every_parsed_field_is_read_from_its_own_object_slice():
    """The adversarial property the deleted fixture existed to probe, pinned
    by a test that runs on every build machine instead of on a developer's.

    The server's answer nests a rung inside a line, and BOTH carry `name` and
    `tier`. A reader that searches the whole body -- or the enclosing line --
    answers every rung with the LINE's name and the LINE's tier, and the board
    renders eight identical rows that all look plausible. So each parser may
    read only the slice it was handed.
    """
    src = _plugin("ApiClient.cs")
    rung = code_of(src, "internal static TitleLadderRung ParseTitleLadderRung(string obj)")
    subjects = set(re.findall(r"PcTopLevel\((\w+),", rung))
    assert subjects == {"obj"}, (
        "the rung parser reads fields out of %r -- anything but its own slice "
        "lets the enclosing line answer for the rung" % sorted(subjects))

    outer = code_of(src, "internal static TitleLadders ParseTitleLadders(string json)")
    # Inside the per-line loop, nothing may be read from the whole body.
    loop = outer[outer.index("foreach (var obj in SliceTopLevelObjects(arr))"):]
    assert "PcTopLevel(json," not in loop, (
        "a line's field is being read from the whole response: " + loop[:200])
    # And the rung parser is fed a slice of that line's own rungs array.
    call = [l.strip() for l in outer.splitlines() if "ParseTitleLadderRung(" in l]
    assert call == ["var r = ParseTitleLadderRung(ro);"], (
        "the rung parser is called with something other than a rung slice: %r"
        % call)
    assert "foreach (var ro in SliceTopLevelObjects(rungs))" in outer, (
        "the rungs array is no longer sliced before it is parsed")


