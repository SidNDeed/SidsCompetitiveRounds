"""The claims a round-1 review found untrue, pinned so they stay true.

None of these is a feature. Each is a sentence in the tree that described a
mechanism the code does not have, and a comment of that kind is worse than no
comment: the next reader reasons from it. Two of the findings below were
reasoned from, in this very tree -- "every 404 means the route is absent" was
written into a docstring and then into the client's behaviour, and "the strip
labels the rule from this same call" was written beside a call the strip had
stopped making.

So each test asserts the CORRECTED claim positively where it can, and only
falls back to "the false sentence is gone" where the claim is about prose.

One item in the round-1 LOW list is deliberately not here:
ai-collab/v1410/briefs/client-small-items.md:42 and :72 describe an
implementation the tree diverged from. That file is outside this worktree and
is shared scratch, so the correction is recorded in ai-collab/CLIENT-R2-NOTES.md
instead of applied.
"""
import io
import os
import re
from pathlib import Path

import pytest

from _cs_structure import code_of, cs_block, mask_code

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PLUGIN = Path(REPO) / "plugin"

# cs_block reads a Path and treats a plain str as the SOURCE ITSELF, so a
# path passed as a string silently becomes a 63-character document that
# matches nothing. Path objects only.

LOCALES = ("es", "ru", "uk", "sv")


def _read(*parts):
    with io.open(os.path.join(REPO, *parts), encoding="utf-8") as fh:
        return fh.read()


# ── the cosmetic caps are not all a mirror ───────────────────────────────

def _int_const(src, name):
    m = re.search(r"\b%s\s*=\s*([\d_]+)" % re.escape(name), src)
    assert m, "no constant named %s" % name
    return int(m.group(1).replace("_", ""))


def test_the_client_never_accepts_a_cosmetic_the_server_would_refuse():
    """The direction is the whole point. A client cap ABOVE the server's
    envelope means the artist gets a local pass and a remote rejection, with
    nothing on either side to explain the gap."""
    client = _read("plugin", "NativeUI.cs")
    server = _read("backend", "api", "main.py")

    png_client = _int_const(client, "CosmeticPngMaxBytes")
    gif_client = _int_const(client, "CosmeticGifMaxBytes")
    frames_client = _int_const(client, "CosmeticMaxFrames")

    # base64 carries 4 characters per 3 bytes, so the decoded envelope is
    # three quarters of the character cap.
    png_server = _int_const(server, "COSMETIC_MAX_B64") * 3 // 4
    gif_server = _int_const(server, "COSMETIC_GIF_MAX_B64") * 3 // 4
    frames_server = _int_const(server, "COSMETIC_MAX_FRAMES")

    assert png_client <= png_server, (png_client, png_server)
    assert gif_client <= gif_server, (gif_client, gif_server)
    assert frames_client <= frames_server, (frames_client, frames_server)


def test_the_cap_comment_states_which_caps_are_equal_and_which_are_tighter():
    """It said all three "mirror" the server's. The GIF cap never did: 3M
    base64 characters decode to 2,250,000 bytes and the client stops at
    2,200,000."""
    client = _read("plugin", "NativeUI.cs")
    window = client[client.index("CosmeticPngMaxBytes") - 1600:
                    client.index("private const int CosmeticPngMaxBytes")]
    assert "They mirror the server's COSMETIC_MAX_B64" not in window, (
        "the blanket mirror claim is back")
    server = _read("backend", "api", "main.py")
    gif_server = _int_const(server, "COSMETIC_GIF_MAX_B64") * 3 // 4
    assert "{:,}".format(gif_server) in window, (
        "the comment does not state the server's actual GIF envelope "
        "(%s): %r" % ("{:,}".format(gif_server), window[-600:]))


def test_the_server_quotes_the_cap_it_enforces():
    server = _read("backend", "api", "main.py")
    # A non-f-string detail that quotes a cap is a figure nothing can update.
    # Matched on the detail LITERAL, not on the file: prose about the old
    # defect legitimately contains the old figure, and a gate that cannot
    # tell those apart is one nobody can write the explanation beside.
    hardcoded = re.findall(r'detail="[^"]*MB max[^"]*"', server)
    assert not hardcoded, (
        "a cosmetic rejection quotes a cap it cannot keep in step: %r" % hardcoded)
    m = re.search(r'detail=f"PNG missing or too large \(\{([^}]+)\}[^"]*"', server)
    assert m, "the rejection no longer formats its figure from anything"
    assert "COSMETIC_MAX_BYTES" in m.group(1), (
        "the figure is not derived from the enforced constant: " + m.group(1))
    # And the derived constant is the enforced one, not a second opinion.
    assert re.search(
        r"COSMETIC_MAX_BYTES\s*=\s*COSMETIC_MAX_B64\s*\*\s*3\s*//\s*4", server), (
        "COSMETIC_MAX_BYTES is no longer derived from the enforced character "
        "cap, so the quoted figure is a second opinion rather than the same "
        "number said twice")


# ── the cooldown diagnostic has ONE reset edge, not two ──────────────────

def test_the_cooldown_diagnostic_comment_matches_its_one_reset_site():
    plugin = _read("plugin", "Plugin.cs")

    resets = re.findall(r"ResetDiag\(WeaponCooldownReset\.DiagKey\)", plugin)
    assert len(resets) == 1, (
        "the cooldown diagnostic is reset from %d sites; the doc describes "
        "one" % len(resets))

    doc = cs_block(PLUGIN / "VanillaFixes.cs",
                   "internal static class WeaponCooldownReset")
    head = doc[:doc.index("DiagKey =")]
    assert "reset from\n        /// both room-exit edges" not in head, (
        "the two-edges claim is back")
    assert "RELIABLE" in head, (
        "the doc no longer says which edge does the reset: " + head[-400:])


# ── the witness set is not identical on every client ─────────────────────

def test_the_witness_comment_admits_the_seat_that_falls_back_alone():
    src = _read("plugin", "GameStateWatcher.cs")
    assert "it is the same set on every client" not in src, (
        "the comment claims an identity the election explicitly does not "
        "provide, which is the claim that made two reporters look impossible")
    window = src[src.index("RJ-3: present fighters"):][:1400]
    assert "ElectReporter" in window, (
        "the corrected comment does not point at the rule that chooses this")


# ── the settled-conflict comment describes the server's real test ────────

def test_the_duplicate_comment_names_what_the_server_compares():
    src = _read("plugin", "ApiClient.cs")
    window = src[src.index("TERMINAL, and deliberately not queued"):][:1200]
    assert "200 with an echo when it AGREES" not in window, (
        "the comment again promises agreement-aware handling")
    for token in ("room id", "lobby", "roster"):
        assert token in window, (
            "the comment does not say the echo is a %s match: %r" % (token, window))


# ── the rule predicate does not label the strip ──────────────────────────

def test_the_rule_predicate_no_longer_claims_to_label_the_strip():
    src = _read("plugin", "FfaCardSequence.cs")
    assert "labels the rule from this\n        /// same call" not in src, (
        "RuleOn again claims the banner reads it, which is how a fallen-back "
        "game went on announcing the rule")
    window = src[:src.index("internal static bool RuleOn()")]
    assert "StripState()" in window[-1400:], (
        "the doc does not point at the call the banner actually makes")


# ── the ladder error codes are documented where they are declared ────────

def test_the_error_code_doc_lists_every_code_the_tab_branches_on():
    api = _read("plugin", "ApiClient.cs")
    doc = api[api.index("/// <summary>Why the last attempt produced no board"):
              api.index("public static string TitleLaddersError")]
    branched = set(re.findall(
        r'e == "(\w+)"',
        code_of(_read("plugin", "TitleLaddersUI.cs"), "private static string EmptyText()")))
    assert branched, "EmptyText branches on nothing"
    missing = sorted(c for c in branched if '"%s"' % c not in doc)
    assert not missing, (
        "TitleLaddersError's doc does not mention %r, so a reader learns the "
        "code list from a comment that is missing the common case" % missing)


def test_the_titles_header_names_the_unknown_account_case():
    src = _read("plugin", "TitleLaddersUI.cs")
    head = src[:src.index("internal static class TitleLaddersUI")]
    assert "until it\n    /// is live every player reads back games=0" not in head, (
        "the header again describes only the known-account zero")
    # The header already mentioned a 404 -- the one a server WITHOUT the route
    # answers -- so "404 appears somewhere above" is a check that cannot fail.
    # The claim is about the OTHER 404, so it is read inside the bullet that
    # makes it.
    # Cut at the paragraph break: a bullet slice that runs to the end of the
    # header swallows the header's OTHER 404 -- the one a server without the
    # route answers -- and the gate stops being able to fail.
    bullets = [b.split("\n    ///\n")[0] for b in head.split("///   * ")]
    unknown = [b for b in bullets if "does not know" in b]
    assert unknown, (
        "the header does not describe the account the route has never seen, "
        "which is every account until it buys an entry rung")
    assert "404" in unknown[0], (
        "the header describes that account without saying it gets a 404, "
        "which is the whole reason the tab used to call the service broken: "
        + unknown[0][:300])


# ── the FFA placement toast is formatted from a key ──────────────────────

PLACEMENT_KEY = "FFA over - you placed #{0}"


def test_the_placement_toast_is_not_composed_before_the_lookup():
    code = mask_code(cs_block(PLUGIN / "GameStateWatcher.cs",
                              "public static void OnFfaGameOver(int winnerTeam)"))
    assert "I18n.TrF(" in code, (
        "the placement is interpolated before ShowNotification's own I18n.Tr, "
        "so the composed sentence is not a catalogue key and never matches one")


def test_the_placement_key_survived_extraction():
    import json
    with io.open(os.path.join(REPO, "tools", "i18n_source.json"),
                 encoding="utf-8") as fh:
        assert PLACEMENT_KEY in set(json.load(fh)["strings"]), (
            "re-run tools/i18n_extract.py: the key is not in the source list")


@pytest.mark.parametrize("lang", LOCALES)
def test_the_placement_toast_is_translated_and_keeps_its_number(lang):
    from test_pc_sept12 import _bundled_catalogues
    value = _bundled_catalogues()[lang].get(PLACEMENT_KEY)
    assert value and value.strip(), "%s: no entry for the placement toast" % lang
    assert value != PLACEMENT_KEY, "%s: still the English string" % lang
    assert "{0}" in value, (
        "%s: the translation dropped the placeholder, so the toast states no "
        "placement at all: %r" % (lang, value))
