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
    window = src[src.index("TERMINAL AT ATTEMPT 1, and deliberately not queued"):][:1600]
    assert "200 with an echo when it AGREES" not in window, (
        "the comment again promises agreement-aware handling")
    # r2 LOW (ApiClient.cs:20303): the previous wording asserted score-vector
    # comparison and quarantine as FACTS about the deployed backend, and
    # neither was true of the build this client shipped against. The comment
    # may state them as REQUIRED behaviour; it may not state them as observed.
    assert "WHAT THIS CLIENT GUARANTEES" in window, (
        "the comment no longer separates what this client can promise from "
        "what the server has to do")
    assert "WHAT THE SERVER DOES" in window and "required behaviour" in window, (
        "the server half is stated as fact again rather than as the behaviour "
        "the endpoint must have")
    client_half = window[window.index("WHAT THIS CLIENT GUARANTEES"):
                         window.index("WHAT THE SERVER DOES")]
    for token in ("409", "403", "RE-KEYED"):
        assert token in client_half, (
            "the client's own guarantee no longer names %s: %r" % (token, client_half))
    assert "503" in client_half, (
        "the comment no longer says 503 is left to the retry loop")


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


# ── the four scope-F claims, asserted on BEHAVIOUR as well as prose ──────
#
# Codex r2 LOW (test_client_r2_claims.py:133): the witness, duplicate, strip
# and placement tests above pass by finding or not finding a phrase. A phrase
# is the cheapest thing in the file to change, and each of those comments
# describes a rule that lives in code the test never reads -- so all four
# stayed green while the r2 report named a concrete counterexample for three
# of them. Each test below asserts the MECHANISM its neighbour describes.


def test_the_election_being_survivable_is_a_property_of_the_key_not_the_prose():
    """The witness comment's honesty is only worth something because two
    reporters CAN be elected and the server can see the duplicate. That needs
    one key per physical game, which is what the frozen snapshot provides --
    and a seat that cannot produce the snapshot must not file at all rather
    than file under a key of its own making."""
    watcher = _read("plugin", "GameStateWatcher.cs")
    body = code_of(watcher, "public static void OnFfaGameOver(int winnerTeam)")
    assert "FfaMode.FreezeReportGameNumber()" in body, (
        "the game number is not frozen at game over, so two electors can key "
        "the same game differently and the comment above is decoration")
    assert "FfaReportRules.CanFile(" in body, (
        "nothing refuses to file when no number could be frozen")
    rules = code_of(_read("plugin", "FfaReportRules.cs"),
                    "internal static string ReportRoomId(string roomName, int frozenGame)")
    assert "return null" in rules, "an absent snapshot still mints a key"


def test_the_duplicate_comments_terminal_set_is_the_set_the_client_acts_on():
    """The comment says which refusals are terminal. The retry loop is what
    makes that true or false, and the two used to disagree: a quarantine
    refusal was re-sent under the same key until the attempts ran out."""
    api = _read("plugin", "ApiClient.cs")
    rules = code_of(_read("plugin", "FfaReportRules.cs"),
                    "internal static class FfaReportRules")
    assert "QuarantinedRefusalStatus = 403" in rules, (
        "403 is no longer named as a refusal status")
    assert "RetryableRefusalStatus = 503" in rules, (
        "503 is no longer distinguished from a terminal refusal")
    terminal = code_of(_read("plugin", "FfaReportRules.cs"),
                       "internal static bool IsTerminalRefusal(long statusCode)")
    assert "SettledRefusalStatus" in terminal and "QuarantinedRefusalStatus" in terminal, (
        "the terminal set no longer contains both refusals: " + terminal)
    assert "RetryableRefusalStatus" not in terminal, (
        "503 is being treated as terminal, which drops a report the server "
        "asked us to re-send")
    retry = code_of(api, "private static IEnumerator PostRequestWithRetry(string url, string json, Action<bool, string> callback, int maxRetries = 3, float retryDelay = 2f, bool stopOnTerminalRefusal = false)")
    assert "FfaReportRules.IsTerminalRefusal(request.responseCode)" in retry, (
        "the retry loop no longer asks the shared rule which refusals stop it")
    # ...and the FFA caller opts in, or the whole rule is unreachable.
    assert "stopOnTerminalRefusal: true" in api, (
        "no caller stops on a terminal refusal")


def test_the_strip_reads_the_state_the_latch_failure_actually_leaves():
    """The strip comment's claim is that ONE predicate drives both the rule
    and the banner. That is false the moment a path leaves the rule off
    without writing the state the banner reads -- which is exactly what the
    latch's catch did: private rolls resumed while the strip went on promising
    the same cards."""
    seq = _read("plugin", "FfaCardSequence.cs")
    tail = seq[:seq.index("the latch threw: ")]
    catch = tail[tail.rindex("catch (Exception ex)"):]
    assert "_latchedGame = game;" in catch, (
        "the latch's catch leaves _latchedGame unset, so StripState() still "
        "reads a pending same-card game: " + catch[:400])
    assert "_active = false;" in catch, (
        "the catch does not turn the rule off: " + catch[:400])
    ui = _read("plugin", "CompetitiveUI.cs")
    assert "FfaCardSequence.StripState()" in code_of(ui), (
        "the painter no longer reads StripState()")
    assert "FfaCardSequence.RuleOn()" not in code_of(ui), (
        "the painter reads RuleOn() again -- two predicates, one banner")


# ── the corrected budget and ladder prose cannot come back ───────────────

def test_the_bundle_budget_comment_states_the_figure_it_is_measured_against():
    """The comment said "~3.4M total, under 3.5M", which is arithmetic about a
    number that is not the limit. Nothing red when the old figure returned,
    because no test read the comment at all."""
    ui = _read("plugin", "CompetitiveUI.cs")
    window = ui[ui.index("That is 3.5M of LOG TEXT"):][:1200]
    assert "3.4M" not in window or "used to claim" in window, (
        "the 3.4M arithmetic is asserted again rather than recorded as wrong: "
        + window[:400])
    assert "3.5M" in window, "the budget comment no longer names the figure"


def test_the_ladder_tier_prose_does_not_return_to_the_fraction_it_had_wrong():
    """The tier-four example was corrected arithmetically; the sentence that
    produced it -- a flat "one-third" of the way up a ladder -- is what has to
    stay gone, or the next reader re-derives the same wrong number."""
    src = _read("plugin", "TitleLaddersUI.cs")
    for phrase in ("one-third", "one third", "a third of the way"):
        assert phrase not in src, (
            "the tier-four prose is back: %r" % phrase)


def test_the_auto_log_server_comment_is_a_ceiling_and_names_its_drops():
    """"Once per qualifying exit" reads as a guarantee that one upload arrives
    per exit. It is a CEILING: bundling, an in-flight transfer and the
    debounce each drop one silently, and an operator reading the old sentence
    would treat a missing bundle as a fault."""
    main = io.open(os.path.join(REPO, "backend", "api", "main.py"),
                   encoding="utf-8").read()
    i = main.index("AT MOST one request per")
    window = main[max(0, i - 900):i + 2500]
    assert "at most" in window.lower(), (
        "the comment still reads as a guarantee rather than a ceiling")
    for drop in ("still being built", "still in flight", "debounce",
                 "byte-identical"):
        assert drop in window, (
            "the ceiling does not name %r as a reason nothing arrives" % drop)
