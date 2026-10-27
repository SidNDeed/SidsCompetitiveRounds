"""G8 — the persistent in-match Same Cards indicator (client-only feature).

Three things a source test can decide, none of which a screenshot can:

1. The six room-rule strings the strip and its game-start toast render have a
   real entry in every shipped locale.  A key with no catalogue entry renders
   English with every other gate green (#578), and the artifact that RENDERS is
   the DLL-bundled catalogue, never a SQL seed (#583).
2. The strip's rule read is the card engine's own LATCHED STATE and there is
   only one of it.  A second copy is free to drift, and two copies have already
   drifted.  First `RoomRules.SameCards`, the vanilla half only, so an FFA room
   running its lobby's same-card rule showed nothing.  Then `RuleOn()`, which is
   the CONFIGURATION and stays true through every fallback in
   `FfaCardSequence.LatchForGame` -- so a seat whose dealer fell back to private
   rolls (capability adverts, seed prop, card pool, pool hash) still read "same
   cards for everyone" for the whole game.  `StripState()` is derived from the
   two fields the dealer itself reads.
3. The top-centre column is laid out in DrawUI's own call order.  That order IS
   the contract -- there is no priority table beside it to go stale -- so a
   reordering edit has to red this file.  The arithmetic under it is executed,
   not read: see test_client_rules_harness.py.

The catalogue comparison is EXACT-KEY, never a substring: an unanchored test
scores a short key as covered because a longer key contains it, and it always
fails toward the cleaner answer (#680).
"""
import io
import os
import re

import pytest

from _cs_structure import code_of
from test_pc_sept12 import _bundled_catalogues  # noqa: E402  (shared parser, one copy)

LOCALES = ("es", "ru", "uk", "sv")

# The strip's lines plus the three game-start toast variants it stands beside.
# All six are rendered from `plugin/I18nCatalogues.cs` at runtime.  The
# fell-back lines are the ones the strip shows when the dealer latched a
# fallback: an untranslated one would tell four fifths of the player base
# nothing in the one state where the strip has something to say.  Since item
# 22 the strip names friendly fire too, reusing the toast's two friendly-fire
# keys and adding the one combination the toast never says.
ROOM_RULE_KEYS = (
    "Room rule: same cards for everyone",
    "Room rule: same cards is off this game",
    "Room rules: friendly fire OFF",
    "Room rules: friendly fire OFF, same cards for everyone",
    "Room rules: friendly fire OFF, same cards is off this game",
    "Room rules: same cards for everyone",
)

# The five sentences the strip itself renders, one per non-default line
# RoomRulesStrip.Choose can return.
STRIP_KEYS = (
    "Room rule: same cards for everyone",
    "Room rule: same cards is off this game",
    "Room rules: friendly fire OFF",
    "Room rules: friendly fire OFF, same cards for everyone",
    "Room rules: friendly fire OFF, same cards is off this game",
)


def _plugin(name):
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.abspath(os.path.join(here, "..", "..", "plugin", name))
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


# The local brace-counter this file used to carry is gone: `code_of` is the
# same span, brace-counted on a MASK so a brace inside a string literal or a
# comment cannot end the span early, and it strips comments so a comment that
# merely NAMES a stray identifier cannot red an assertion about the code
# (#432/#330).


# ── 1. every locale has a real entry for every room-rule key ──────────────

@pytest.mark.parametrize("lang", LOCALES)
@pytest.mark.parametrize("key", ROOM_RULE_KEYS)
def test_room_rule_key_is_translated(lang, key):
    catalogue = _bundled_catalogues()
    assert lang in catalogue, "no {} dictionary in I18nCatalogues.cs".format(lang)
    assert key in catalogue[lang], "{}: no entry for {!r}".format(lang, key)
    value = catalogue[lang][key]
    assert value.strip(), "{}: empty translation for {!r}".format(lang, key)
    # An entry that merely echoes the English is not a translation.  This is
    # the assertion the "set one value to the English string" control fires.
    assert value != key, "{}: {!r} is still the English string".format(lang, key)


def test_short_key_control():
    """#680's short-key control: prove the lookup above is EXACT-key.

    The shortest room-rule key is a strict prefix of two of the others, so an
    unanchored `key in text` test would score it as covered by its neighbours
    alone.  If this ever fails, the coverage numbers above are inflated.
    """
    shortest = min(ROOM_RULE_KEYS, key=len)
    longer = [k for k in ROOM_RULE_KEYS if k != shortest and shortest in k]
    assert longer, "no longer key contains {!r} — pick a different control".format(shortest)
    catalogue = _bundled_catalogues()
    for lang in LOCALES:
        assert shortest in catalogue[lang], "{}: exact-key lookup lost {!r}".format(lang, shortest)


# ── 2. one predicate decides both the label and the deal ──────────────────

def test_indicator_reads_the_card_engines_latched_state():
    """`RuleOn()` is the CONFIGURATION, not the verdict.

    `LatchForGame` leaves it true through all four of its fallbacks, so a strip
    drawn from it kept promising shared hands for a whole game in which the
    seat was rolling privately.  `StripState()` is derived from `_latchedGame`
    and `_active` -- the same two fields the dealer reads.
    """
    body = code_of(_plugin("CompetitiveUI.cs"),
                   "private static void DrawRoomRulesBanner()")
    assert body.count("FfaCardSequence.StripState()") == 1, \
        "the indicator must read the latched state exactly once, through StripState()"
    # No second source of truth inside the same function.  RuleOn() is on this
    # list too now: reading the configuration here is precisely the defect.
    for stray in ("RoomRules.SameCards", "FfaMode.SameCardRule",
                  "FfaCardSequence.RuleOn()", "ActiveThisGame"):
        assert stray not in body, \
            "DrawRoomRulesBanner reads {} directly — StripState() is the one read".format(stray)


def test_the_strip_says_something_different_when_the_dealer_fell_back():
    """A tri-state that renders one string is a tri-state in name only.

    The FellBack branch has to reach a DIFFERENT catalogue key, or the fix is
    an accessor rename.  Pending renders the configured rule on purpose (a room
    lobby should show its own rule) and shares the key with Active.
    """
    body = code_of(_plugin("CompetitiveUI.cs"),
                   "private static void DrawRoomRulesBanner()")
    assert "FellBack" in body, "the strip does not distinguish the fallback state"
    for key in ("Room rule: same cards for everyone",
                "Room rule: same cards is off this game"):
        assert body.count('I18n.Tr("%s")' % key) == 1, \
            "the strip does not render {!r} exactly once".format(key)
    # And the FellBack test is what chooses between them.
    chooser = body[body.index("FellBack"):]
    assert "Room rule: same cards is off this game" in chooser


def test_strip_state_is_derived_from_the_dealers_own_fields():
    """StripState must read the latch, not the flags.

    `RuleOn()` appears exactly once, as the Off test; everything after it is
    `_latchedGame` and `_active`.  A StripState that consulted the rule flags a
    second time would be free to disagree with the deal all over again.
    """
    body = code_of(_plugin("FfaCardSequence.cs"),
                   "internal static RuleDisplayState StripState()")
    assert body.count("RuleOn()") == 1, body
    for field in ("_latchedGame", "_active"):
        assert field in body, "StripState does not read {}".format(field)
    for stray in ("RoomRules.SameCards", "FfaMode.SameCardRule"):
        assert stray not in body, \
            "StripState reads {} directly instead of through RuleOn()".format(stray)
    # Each of the four states is reachable from this body.  A tri-state that
    # can only ever answer two of its values is a bool with extra names.
    for state in ("Off", "Pending", "Active", "FellBack"):
        assert state in body, "StripState can never return {}".format(state)


def test_rule_predicate_has_exactly_one_definition():
    src = _plugin("FfaCardSequence.cs")
    defs = re.findall(r"^\s*(?:internal|private|public|protected)\s+static\s+bool\s+RuleOn\s*\(",
                      src, re.M)
    assert len(defs) == 1, "expected one RuleOn definition, found {}".format(len(defs))
    assert re.search(r"^\s*internal\s+static\s+bool\s+RuleOn\s*\(", src, re.M), \
        "RuleOn must be internal for CompetitiveUI to label the rule from it"
    # It still answers for BOTH hosts — promoting it must not have narrowed it
    # to one mode, which is exactly the drift the single predicate exists to
    # prevent.  Expression-bodied, so the definition is its one line.
    line = src[src.index("internal static bool RuleOn()"):].split("\n", 1)[0]
    assert "RoomRules.SameCards" in line and "FfaMode.SameCardRule" in line, \
        "RuleOn no longer chooses between the vanilla and FFA flags: " + line


def test_indicator_is_called_from_the_draw_pass():
    src = _plugin("CompetitiveUI.cs")
    assert src.count("DrawRoomRulesBanner();") == 1, \
        "the indicator must be invoked exactly once from DrawUI"


# -- 2b. item 22: the strip names friendly fire, and one key can hide it ----
# Which line each (friendly fire, same cards) pair gets is EXECUTED by the
# client-rules harness (RoomRulesStrip.SelfTest, the "roomrules" suite in
# test_client_rules_harness.py); what a source test decides is that the painter
# feeds the chooser the LATCHED rule and renders every line it can return.

def test_the_strip_names_friendly_fire_from_the_latched_rule():
    body = code_of(_plugin("CompetitiveUI.cs"),
                   "private static void DrawRoomRulesBanner()")
    assert body.count("RoomRules.FriendlyFireOff") == 1, \
        "the strip must read the latched friendly-fire rule exactly once"
    assert body.count("RoomRulesStrip.Choose(") == 1
    # The raw flag is not a second source: it reads TRUE outside a latched
    # room only because ResetLatched sets it, and FriendlyFireOff carries the
    # Latched term itself.
    for stray in ("RoomRules.FriendlyFire;", "!RoomRules.FriendlyFire", "RoomRules.NonDefault"):
        assert stray not in body, stray
    for key in STRIP_KEYS:
        assert body.count('I18n.Tr("%s")' % key) == 1, \
            "the strip does not render {!r} exactly once".format(key)
    for member in ("SameCards", "SameCardsOff", "FriendlyFireOff", "FriendlyFireOffSameCards"):
        assert body.count("case RoomRulesStrip.Line.%s:" % member) == 1, member


def test_friendly_fire_off_is_the_latched_rule():
    lines = [ln for ln in code_of(_plugin("RoomRules.cs")).splitlines()
             if "public static bool FriendlyFireOff" in ln]
    assert len(lines) == 1, lines
    assert "Latched && !FriendlyFire" in lines[0], lines[0]


def test_one_cfg_key_hides_the_strip_and_it_defaults_to_shown():
    code = code_of(_plugin("Plugin.cs"))
    m = re.search(r'ShowRoomRulesIndicator\s*=\s*Config\.Bind\(\s*"UI",\s*'
                  r'"ShowRoomRulesIndicator",\s*(\w+),', code)
    assert m, "no [UI] ShowRoomRulesIndicator binding"
    assert m.group(1) == "true", "the strip must default to shown"
    body = code_of(_plugin("CompetitiveUI.cs"),
                   "private static void DrawRoomRulesBanner()")
    assert "Plugin.ShowRoomRulesIndicator" in body
    assert body.count("RoomRulesStrip.Paints(") == 1
    # The key's VALUE is what the gate is handed, and the gate returns before
    # the strip claims its band: a Paints call fed a constant, or one whose
    # refusal falls through to the paint, reads the key and ignores it (the
    # mutation Paints(true, line) passed every assertion above).
    m = re.search(r"(\w+)\s*=\s*Plugin\.ShowRoomRulesIndicator\s*==\s*null\s*"
                  r"\|\|\s*Plugin\.ShowRoomRulesIndicator\.Value\s*;", body)
    assert m, "the cfg value is not read into a local the gate can be handed"
    gate = "if (!RoomRulesStrip.Paints(%s, line))" % m.group(1)
    assert body.count(gate) == 1, "the gate is not handed the key's value: " + gate
    refusal = body.split(gate, 1)[1]
    refusal = refusal[:refusal.index("roomRuleSuppressed = RoomRulesStrip.Line.None;")]
    assert "return;" in refusal, "a refused strip falls through to the paint"
    assert body.index(gate) < body.index("ClaimTopStrip("), \
        "the strip claims its band before the key is consulted"
    # The key hides the strip only: the game-start toast is not behind it.
    toast = code_of(_plugin("RoomRules.cs"), "public static void OnGameStart()")
    assert "ShowRoomRulesIndicator" not in toast
    assert "CompetitiveUI.ShowNotification(" in toast


def test_the_chooser_file_holds_no_catalogue_string():
    """RoomRulesStrip.cs is not in tools/i18n_extract.py's FILES list (#464):
    a string moved into it would be silently unharvestable."""
    assert "I18n.Tr(" not in code_of(_plugin("RoomRulesStrip.cs"))


def test_spectator_bar_claims_its_own_band_and_paints_inside_it():
    """On a spectator seat the live bar is usually the only claimant and
    nothing else can claim for it.

    Three assertions, because the first two alone passed a mutation that made
    the claim a no-op: the call must be there, its height must be DERIVED from
    the rects it is about (a constant, a zero or a literal claims a band that
    does not describe what paints), and the y the column hands back must be
    applied to BOTH rects -- a claim whose return value is discarded reserves
    space and then paints somewhere else.
    """
    body = code_of(_plugin("SpectatorHud.cs"), "private static void DrawLiveBar()")
    assert "CompetitiveUI.ClaimTopStrip(" in body, \
        "the spectator bar no longer claims a band in the top-centre column"
    call = body.split("CompetitiveUI.ClaimTopStrip(", 1)[1]
    argument = call[:call.index(")") + 1]
    for measured in ("rect.yMax", "barBackdrop.yMax"):
        assert measured in argument, (
            "the claimed height is not derived from {}: {!r}".format(measured, argument))
    for target in ("rect.y +=", "barBackdrop.y +="):
        assert target in body, (
            "the claimed y is never applied to {} — the bar paints outside its own band"
            .format(target.split(".")[0]))


# ── 3. the column is laid out in DrawUI's call order ──────────────────────

# Every surface that claims a band in the top-centre column, in the order the
# column places them.  This list is not a priority table the allocator reads --
# the allocator has none, by design.  It is the order DrawUI calls them in, and
# the test below is what stops an edit from reordering the calls without
# reordering the layout.
TOP_STRIP_CLAIMANTS = (
    "SpectatorHud.Draw();",
    "DrawFfaScoreStrip();",
    "DrawMatchStatus();",
    "DrawLeaverBanner();",
    "DrawTournamentBanner();",
    "DrawRoomRulesBanner();",
)


def test_the_column_is_claimed_in_draw_order():
    body = code_of(_plugin("CompetitiveUI.cs"), "public static void DrawUI()")
    positions = []
    for call in TOP_STRIP_CLAIMANTS:
        assert body.count(call) == 1, \
            "expected exactly one {} in DrawUI, found {}".format(call, body.count(call))
        positions.append(body.index(call))
    assert positions == sorted(positions), (
        "DrawUI no longer calls the top-centre claimants in layout order; the "
        "column would place them in the new order and the comment above "
        "ClaimTopStrip would be false: " + repr(list(zip(TOP_STRIP_CLAIMANTS, positions))))


def test_every_claimant_opens_and_closes_its_band():
    """The two claimants that lay themselves out downward must close what they
    open.  An open band that is never closed leaves the column's open marker
    set for the rest of the frame, and the next claimant's close would then
    land on someone else's origin."""
    src = _plugin("CompetitiveUI.cs")
    for signature in ("private static void DrawMatchStatus()",
                      "private static void DrawFfaScoreStrip()"):
        body = code_of(src, signature)
        assert body.count("OpenTopStrip()") == 1, signature
        assert body.count("CloseTopStrip(") == 1, signature
        assert body.index("OpenTopStrip()") < body.index("CloseTopStrip("), signature
    # File-wide the two must still balance: a third opener with no closer is
    # the shape this pairing exists to prevent.
    whole = code_of(src)
    assert whole.count("OpenTopStrip()") == whole.count("CloseTopStrip("), \
        "OpenTopStrip and CloseTopStrip are no longer paired in CompetitiveUI.cs"


def test_the_full_width_bars_no_longer_assume_the_top_of_the_screen():
    """The leaver and tournament bars painted at y=0 and claimed only a bottom
    edge, so they covered the match status lines and the FFA banners whenever
    those were live.  Both now paint at the y the column hands back."""
    src = _plugin("CompetitiveUI.cs")
    for signature in ("private static void DrawLeaverBanner()",
                      "private static void DrawTournamentBanner()"):
        body = code_of(src, signature)
        assert body.count("ClaimTopStrip(barH)") == 1, signature
        assert "new Rect(0, 0, Screen.width, barH)" not in body, (
            "{} still paints at y=0 regardless of what else claimed the column"
            .format(signature))
        assert body.count("new Rect(0, barY, Screen.width, barH)") == 2, (
            "{}: both the backdrop and the label must sit in the claimed band"
            .format(signature))
