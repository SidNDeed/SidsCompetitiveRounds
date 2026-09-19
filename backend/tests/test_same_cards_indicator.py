"""G8 — the persistent in-match Same Cards indicator (client-only feature).

Two things a source test can decide, both of which a screenshot cannot:

1. The four room-rule strings the strip and its game-start toast render have a
   real entry in every shipped locale.  A key with no catalogue entry renders
   English with every other gate green (#578), and the artifact that RENDERS is
   the DLL-bundled catalogue, never a SQL seed (#583).
2. The strip's rule read is the card engine's own predicate and there is only
   one of it.  A second copy is free to drift, and the first copy had already
   drifted: `RoomRules.SameCards` is the vanilla half only, so an FFA room
   running its lobby's same-card rule showed nothing.

The catalogue comparison is EXACT-KEY, never a substring: an unanchored test
scores a short key as covered because a longer key contains it, and it always
fails toward the cleaner answer (#680).
"""
import io
import os
import re

import pytest

from test_pc_sept12 import _bundled_catalogues  # noqa: E402  (shared parser, one copy)

LOCALES = ("es", "ru", "uk", "sv")

# The strip's own line plus the three game-start toast variants it stands
# beside.  All four are rendered from `plugin/I18nCatalogues.cs` at runtime.
ROOM_RULE_KEYS = (
    "Room rule: same cards for everyone",
    "Room rules: friendly fire OFF",
    "Room rules: friendly fire OFF, same cards for everyone",
    "Room rules: same cards for everyone",
)


def _plugin(name):
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.abspath(os.path.join(here, "..", "..", "plugin", name))
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def _function_body(src, signature):
    """The text of one method, from its signature to the matching close brace.

    Brace-counted rather than line-counted, so the span is the FUNCTION and an
    assertion over it cannot quietly widen to the file (#432/#330).
    """
    start = src.index(signature)
    open_brace = src.index("{", start + len(signature))
    depth = 0
    for i in range(open_brace, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[open_brace:i + 1]
    raise AssertionError("unbalanced braces after " + signature)


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

def test_indicator_reads_the_card_engines_own_predicate():
    body = _function_body(_plugin("CompetitiveUI.cs"),
                          "private static void DrawRoomRulesBanner()")
    assert body.count("FfaCardSequence.RuleOn()") == 1, \
        "the indicator must read the rule exactly once, through RuleOn()"
    # No second source of truth inside the same function: a direct read of
    # either mode's flag would be free to disagree with what is dealt.
    for stray in ("RoomRules.SameCards", "FfaMode.SameCardRule"):
        assert stray not in body, \
            "DrawRoomRulesBanner reads {} directly — RuleOn() is the one predicate".format(stray)


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


def test_spectator_bar_reserves_its_own_edge():
    """The strip docks under whatever else claimed the top-centre band; on a
    spectator seat the live bar is usually the only claimant and nothing else
    can reserve for it."""
    body = _function_body(_plugin("SpectatorHud.cs"), "private static void DrawLiveBar()")
    assert "CompetitiveUI.ReserveTopStrip(" in body
