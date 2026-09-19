"""Who a room still counts as a fighter, and what a report is filed as.

Three defects, all of the same family: a conclusion outlived the state it was
drawn from, and nothing re-derived it when that state moved.

1. `RoomActors` latches a rejection so that an actor's DEPARTURE is provably
   not a fighter's -- the latch has to survive the actor's property teardown.
   `RecordRejected` already declines to latch a seat that is on the frozen
   roster (RJ-2), but it can only apply that rule against the roster it can
   see at rejection time. A seat rejected while the roster was thin -- loading,
   alt-tabbed, a slow rejoin, or a first game it sat out -- stayed latched
   after the next game's union added it, because `IsUnauthorized` tests the
   latch BEFORE membership and nothing re-tested membership. The latch cleared
   only on a room change, so that seat was unauthorized for the rest of the
   room on every client.

2. The FFA witness property is published once per game and the reporter
   election compares it against the game number the seat holds at game over.
   Drift adoption moves that number mid-phase. Without a re-stamp every
   adopted seat fails its own witness test, and when they have all adopted the
   electorate is empty and the election falls back to presence -- which is the
   exact hole the witness exists to close.

3. The report key itself. That one is EXECUTED, not read: see
   test_client_rules_harness.py, which drives FfaReportRules.ReportRoomId and
   compares two seats' keys. What is left here is the call site -- that the
   production path actually asks for the shared key and no longer builds one
   out of a local clock.

Spans are taken with `code_of`, which brace-counts on a mask and strips
comments, so a brace inside a literal cannot end a span early and a comment
that merely names an identifier cannot satisfy an assertion about code
(#432/#330).
"""
import io
import os
import re

import pytest

from _cs_structure import code_of


def _plugin(name):
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.abspath(os.path.join(here, "..", "..", "plugin", name))
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


# ── 1. a roster write re-evaluates the latches it invalidates ─────────────

ROSTER_WRITERS = (
    "internal static void FreezeFighterRoster(IEnumerable<string> steamIds)",
    "internal static void UnionFighterRoster(IEnumerable<string> steamIds)",
)


@pytest.mark.parametrize("signature", ROSTER_WRITERS)
def test_every_roster_writer_re_evaluates_the_latches(signature):
    body = code_of(_plugin("RoomActors.cs"), signature)
    assert "ReleaseLatchesTheRosterNowCovers()" in body, (
        "%s writes the roster without re-evaluating the rejection latches it "
        "may have just invalidated" % signature)


def test_the_freeze_re_evaluates_on_its_early_return_too():
    """`FreezeFighterRoster(null)` CLEARS the roster and returns early.

    That is a roster write like any other -- it can only ever release latches,
    since an empty roster covers nobody -- but an early return that skips the
    re-evaluation is how half a rule ships. Both exits must call it.
    """
    body = code_of(_plugin("RoomActors.cs"), ROSTER_WRITERS[0])
    assert body.count("ReleaseLatchesTheRosterNowCovers()") == 2, (
        "the null-roster early return skips the re-evaluation: " + body)


def test_the_release_predicate_is_the_one_record_rejected_uses():
    """A release that admitted more than RecordRejected declines to latch
    would be a new hole, not a fix. The two must test the same three things.
    """
    src = _plugin("RoomActors.cs")
    release = code_of(src, "private static void ReleaseLatchesTheRosterNowCovers()")
    record = code_of(src, "internal static void RecordRejected(PhotonPlayer actor)")
    for term in ("IsImpostorReplicated(", "_fighterSteamIds.Contains(", "SteamIdOf("):
        assert term in release, "the release does not test %s" % term
        assert term in record, (
            "%s is no longer part of RecordRejected's own rule -- the two have "
            "drifted apart" % term)
    # An unreadable identity must NOT be released: IsUnauthorized reads an
    # unreadable identity as unauthorized once the roster is frozen, so a
    # release there would contradict the live rule.
    assert "string.IsNullOrEmpty(sid)" in release, (
        "the release does not refuse an unreadable identity")
    # And only actors still in the room are considered -- a departed actor's
    # latch is the thing that proves its leave was not a fighter's.
    assert "room.Players" in release or "CurrentRoom" in release, (
        "the release does not scope itself to actors still in the room")


def test_the_latch_is_still_tested_before_membership():
    """The short-circuit is not the bug and must stay.

    After departure there are no properties left to test membership with, so
    the latch has to be consulted first. The fix is that a roster write
    re-evaluates it -- not that the order changed.
    """
    body = code_of(_plugin("RoomActors.cs"),
                   "internal static bool IsUnauthorized(PhotonPlayer actor)")
    assert body.index("IsRejected(actor)") < body.index("RosterFrozen"), (
        "IsUnauthorized no longer tests the latch first; a departed actor's "
        "leave can now be read as a fighter's")


def test_the_inertness_comment_names_the_freeze_call_sites_that_exist():
    """#432: the highest-risk comment is one asserting a mechanism a later
    change killed. This file's header claimed nothing freezes a roster, which
    stopped being true releases ago -- and the claim is what a reader uses to
    decide the helpers are a no-op."""
    src = _plugin("RoomActors.cs")
    header = src[:src.index("internal static class RoomActors")]
    assert "Nothing calls FreezeFighterRoster in the shipped build" not in header, (
        "the inertness claim is back")
    watcher = _plugin("GameStateWatcher.cs")
    sites = len(re.findall(r"RoomActors\.(?:Re)?[Ff]reezeFighterRoster", watcher))
    assert sites >= 3, "expected at least three freeze call sites, found %d" % sites


# ── 2. every drift adoption re-stamps the witness ─────────────────────────

def test_both_adoption_sites_republish_the_witness():
    """Two sites move (game, cycle) and only one of them goes through the
    adoptIdentity funnel -- the manifest-wait site bypasses it by design, with
    a comment saying so. A re-stamp in the funnel alone covers one of the two.
    """
    body = code_of(_plugin("FfaMode.cs"),
                   "private static IEnumerator FfaPickPhase(GM_ArmsRace gm, int roundWinnerTeam)")
    calls = body.count("RepublishGameWitness(")
    assert calls == 2, (
        "expected a witness re-stamp at both adoption sites, found %d" % calls)
    # Each one sits with the gameNumber assignment it belongs to: a re-stamp
    # that ran before the assignment would publish the number being left.
    for chunk in body.split("RepublishGameWitness(")[:-1]:
        assert "gameNumber = " in chunk, (
            "a witness re-stamp is not preceded by a gameNumber assignment")


def test_the_witness_republisher_reads_the_counter_live():
    """A parameter would be a second copy of the game number with nothing
    forcing it to agree with the one the adoption just assigned."""
    body = code_of(_plugin("FfaMode.cs"),
                   "internal static void RepublishGameWitness(string why)")
    assert "h[PropGameWitness] = gameNumber;" in body, body
    assert "PropGameWitness" in body and "SetCustomProperties" in body


def test_the_witness_property_has_one_key_and_two_writers():
    """The first publish batches the witness with the card clear so the two
    cannot disagree; the re-stamp is the second writer. Both must name the
    same constant -- a literal in either place is how the two halves drift."""
    watcher = _plugin("GameStateWatcher.cs")
    ffa = _plugin("FfaMode.cs")
    assert 'clearProps[FfaMode.PropGameWitness] = FfaMode.GameNumber;' in watcher
    assert ffa.count('PropGameWitness = "cr_ffa_gw"') == 1
    for src, name in ((watcher, "GameStateWatcher.cs"), (ffa, "FfaMode.cs")):
        body = code_of(src)
        stray = [m for m in re.findall(r'"cr_ffa_gw"', body)]
        limit = 1 if name == "FfaMode.cs" else 0
        assert len(stray) <= limit, (
            "%s carries a literal copy of the witness key" % name)


# ── 3. the report call site asks for the shared key ───────────────────────

def test_the_report_key_comes_from_the_shared_rule():
    src = _plugin("GameStateWatcher.cs")
    body = code_of(src, "private static void OnFfaMatchOver(int winnerTeam)") \
        if "private static void OnFfaMatchOver(int winnerTeam)" in src else code_of(src)
    assert "FfaReportRules.ReportRoomId(" in body, (
        "the FFA report no longer builds its key through the shared rule")
    assert "FfaMode.PublishedGameNumber()" in body, (
        "the key is not derived from the number the host published")


def test_no_local_clock_reaches_the_report_key():
    """matchStartTime is DateTime.UtcNow, read when THIS seat's match-start
    hook ran. Two seats a second apart stamp different clocks, which is how
    two electors filed under two keys and both settled."""
    src = code_of(_plugin("GameStateWatcher.cs"))
    assert "reportRoomId = $\"{photonRoomId}_{matchStartTime:HHmmss}" not in src, (
        "the local clock is back in the report key")
    assign = [l for l in src.splitlines() if "string reportRoomId =" in l]
    assert assign, "the report key assignment moved"
    for line in assign:
        assert "matchStartTime" not in line, (
            "a report key is still built from a local clock: " + line.strip())


def test_the_published_game_number_reads_the_room_property():
    body = code_of(_plugin("FfaMode.cs"), "internal static int PublishedGameNumber()")
    assert "PropCycle" in body, (
        "PublishedGameNumber does not read the room property the host writes")
    assert "gameNumber" not in body, (
        "PublishedGameNumber falls back to the local counter internally -- the "
        "caller decides that, so the two are distinguishable")
    assert "return -1" in body, "an unreadable property must be distinguishable"


def test_the_report_rules_file_stays_free_of_the_engine():
    """It is compiled into tools/client-rules-harness, which has no Unity, no
    Photon and no BepInEx. A single engine reference there turns an executed
    rule back into a source-shape assertion."""
    # code_of, not cs_block: the prose in this file legitimately NAMES
    # Photon and the engine, and a check that reds on a comment is a check
    # whose next fix is to reword the comment.
    src = code_of(_plugin("FfaReportRules.cs"),
                  "internal static class FfaReportRules")
    for banned in ("UnityEngine", "Photon", "BepInEx", "PhotonNetwork",
                   "Plugin.Log", "MonoBehaviour"):
        assert banned not in src, (
            "FfaReportRules references %s and can no longer be executed by the "
            "harness" % banned)
