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


def test_the_release_is_evaluated_over_the_RAW_census():
    """The HIGH. The release used to be evaluated over ActiveFighters(), which
    is room.Players filtered by IsUnauthorized -- and IsUnauthorized tests the
    rejection latch FIRST. So the one actor the release is deciding about was
    removed from the evidence before the predicate could read it: a seat
    latched while the roster was thin could never be discovered by a later
    widening, whatever the roster did.

    The census the release reads must therefore apply no roster test and no
    latch test. That it is also CORRECT is executed, not read: see the
    rostercensus suite in test_client_rules_harness.py, which drives frozen
    {A,B} / raw {A,B,C} / latched C and checks C comes back released, against a
    paired case that feeds the pre-filtered census and must release nothing.
    """
    src = _plugin("RoomActors.cs")
    release = code_of(src, "private static void ReleaseLatchesTheRosterNowCovers()")
    assert "RosterCensusRules.LatchesToRelease(" in release, (
        "the release no longer goes through the rule the harness executes")
    call = release.split("RosterCensusRules.LatchesToRelease(", 1)[1]
    first_arg = call.split(",", 1)[0].strip()
    assert first_arg == "RawActorCensus()", (
        "the release is evaluated over %r, not over the raw census" % first_arg)
    for filtered in ("ActiveFighters(", "IsUnauthorized(", "IsRejected("):
        assert filtered not in release, (
            "the release reads %s -- that view already excludes the latched "
            "actor it is deciding about" % filtered)


def test_the_raw_census_filters_on_nothing_the_latch_can_move():
    """RawActorCensus is the evidence. It must be the room's own actor list,
    carrying the three facts the predicate needs, and nothing may be dropped
    from it on a ground the latch or the roster controls -- otherwise the
    circularity comes straight back one call further down."""
    body = code_of(_plugin("RoomActors.cs"),
                   "private static IList<RosterCensusRules.Actor> RawActorCensus()")
    assert "room.Players" in body, (
        "the census is no longer taken from the room's own actor list")
    for banned in ("IsUnauthorized", "IsRejected", "_rejectedActors",
                   "_fighterSteamIds", "ActiveFighters", "RosterFrozen"):
        assert banned not in body, (
            "the raw census consults %s -- it is no longer raw" % banned)
    # It carries the facts, it does not apply them: spectators and impostors
    # are excluded by the RULE (which the harness executes), not here.
    for fact in ("SteamIdOf(", "IsSpectator(", "IsImpostorReplicated("):
        assert fact in body, "the census does not carry %s" % fact
    assert body.count("continue;") == 1, (
        "the census drops actors on more grounds than a null entry: " + body)


def test_the_release_predicate_is_still_record_rejecteds_own_rule():
    """A release that admitted more than RecordRejected declines to latch
    would be a new hole, not a fix. The predicate moved into
    RosterCensusRules; the facts it decides on must still be the facts
    RecordRejected decides on."""
    src = _plugin("RoomActors.cs")
    record = code_of(src, "internal static void RecordRejected(PhotonPlayer actor)")
    rule = code_of(_plugin("RosterCensusRules.cs"),
                   "internal static List<int> LatchesToRelease(IList<Actor> raw,")
    for term in ("IsImpostorReplicated(", "_fighterSteamIds.Contains(", "SteamIdOf("):
        assert term in record, (
            "%s is no longer part of RecordRejected's own rule -- the two have "
            "drifted apart" % term)
    assert "a.IsImpostor" in rule, "the rule stopped refusing an impostor"
    assert "a.IsSpectator" in rule, "the rule stopped refusing a spectator"
    assert "string.IsNullOrEmpty(a.SteamId)" in rule, (
        "the rule stopped refusing an unreadable identity -- once the roster is "
        "frozen IsUnauthorized reads that as unauthorized, so a release there "
        "would contradict the live rule")
    assert "roster == null || !roster.Contains(a.SteamId)" in rule, (
        "the rule stopped requiring roster membership")
    # Only actors STILL IN THE ROOM take part: the rule iterates the census,
    # never the latch set. A departed actor's latch is the thing that proves
    # its leave was not a fighter's.
    assert "foreach (var a in raw)" in rule, (
        "the rule iterates something other than the room census")


def test_the_per_game_roster_write_owns_its_own_census():
    """The call site used to build the census and hand it in, which is how a
    correct roster rule shipped with a census that had already dropped the
    seat. The census and the write are now one call."""
    watcher = _plugin("GameStateWatcher.cs")
    started = code_of(watcher, "public static void OnFfaMatchStarted()")
    assert "RoomActors.RefreezeFighterRosterForGameFromRoom()" in started, (
        "the match-start roster write no longer takes its own census")
    assert "ActiveFighters()" not in started, (
        "the call site is building the census out of the filtered view again")
    body = code_of(_plugin("RoomActors.cs"),
                   "internal static List<string> RefreezeFighterRosterForGameFromRoom()")
    assert "RosterCensusRules.UnionCensus(" in body, (
        "the per-game write no longer goes through the executed census rule")
    assert "RawActorCensus()" in body, "the per-game write does not read the raw census"


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

GAME_OVER = "public static void OnFfaGameOver(int winnerTeam)"


def test_the_report_key_comes_from_a_number_frozen_before_any_election():
    """The HIGH. Two electors could key the SAME physical game differently:
    each read the published game number when its own report ran, and the host
    rolls that number over at the start of the next game. A seat that ran late
    keyed one number while its peer keyed the next, the server's anchored
    suffix parser recovered two different games, and one physical game settled
    twice.

    The number is therefore frozen ONCE, into a per-seat snapshot, at the
    moment the game ends -- before the election runs and before any rollover
    can reach it -- and every elector keys from the snapshot.
    """
    body = code_of(_plugin("GameStateWatcher.cs"), GAME_OVER)
    assert "FfaMode.FreezeReportGameNumber()" in body, (
        "the game number is no longer frozen at game over")
    assert "FfaReportRules.ReportRoomId(" in body, (
        "the FFA report no longer builds its key through the shared rule")
    key = [l for l in body.splitlines() if "FfaReportRules.ReportRoomId(" in l]
    assert len(key) == 1, "expected one key assignment, found %d" % len(key)
    args = key[0].split("FfaReportRules.ReportRoomId(", 1)[1].rsplit(")", 1)[0]
    assert args.split(",")[1].strip() == "frozenGame", (
        "the key is built from %r rather than from the frozen snapshot" % args)
    # ORDER. A freeze that ran after the election would snapshot a number the
    # rollover may already have moved -- the defect with one more step.
    assert body.count("FreezeReportGameNumber()") == 1, (
        "the freeze happens %d times in this span; one of them is later than "
        "the game-over edge by definition"
        % body.count("FreezeReportGameNumber()"))
    assert body.index("FreezeReportGameNumber()") < body.index("ReportRoomId("), (
        "the snapshot is taken after the key is built")
    # THE ELECTION, pinned where it actually is. This used to read
    # `if "ElectReporter" in body:` -- and ElectReporter is NOT in this span,
    # it is in the filing path this span calls, so that assertion never ran at
    # all. A guard whose condition is false is an assertion that deleted
    # itself (#342/#441), which is the class this round is closing.
    #
    # The real ordering is by CALL: the freeze happens here, before the call
    # that elects and files, so no election can precede it.
    assert "ElectReporter" not in body, (
        "the election moved into the game-over span; this test now measures "
        "the wrong ordering")
    assert "TryReportFfaMatch(" in body, (
        "the game-over edge no longer calls the filing path")
    assert body.index("FreezeReportGameNumber()") < body.index("TryReportFfaMatch("), (
        "the snapshot is taken after the filing path has already run")
    filing = code_of(_plugin("GameStateWatcher.cs"),
                     "private static bool TryReportFfaMatch(string reportRoomId, int duration, int winnerTeam)")
    assert "ElectReporter" in filing, (
        "the election is in neither the game-over span nor the filing path, "
        "so nothing pins it as happening after the freeze")


def test_the_freeze_does_not_live_in_the_path_that_files_the_report():
    """The other half of the placement, and the one no pure function can see.

    The r3 lens is right that the executed suite cannot observe WHERE the
    number was obtained -- so this is structural on purpose, and it asks the
    question the executed cases cannot: the freeze belongs to the game-over
    edge, and the reporting path must only READ what that edge took. A freeze
    that drifted into TryReportFfaMatch would snapshot a number the host may
    already have rolled over, which is the r2 HIGH restored.

    The snapshot object refuses a second freeze as well (first write wins,
    ffareport case 3c), so this is defence in depth rather than the only
    guard -- but a freeze in the wrong place with no earlier one to lose to
    would still take the wrong number.
    """
    watcher = _plugin("GameStateWatcher.cs")
    filing = code_of(watcher,
                     "private static bool TryReportFfaMatch(string reportRoomId, int duration, int winnerTeam)")
    assert "FreezeReportGameNumber" not in filing, (
        "the freeze moved into the filing path, where the host may already "
        "have rolled the number over")
    assert "ReportGameSnapshot" in filing or "reportRoomId" in filing, (
        "the filing path no longer reads the frozen key at all")
    # And exactly one site in the whole client freezes it.
    whole = code_of(watcher)
    assert whole.count("FfaMode.FreezeReportGameNumber()") == 1, (
        "the client freezes the report number in %d places"
        % whole.count("FfaMode.FreezeReportGameNumber()"))
    # The clear belongs to the game-START hook, so game N cannot key N+1.
    start = code_of(watcher, "public static void OnFfaMatchStarted()")
    assert "FfaMode.ClearReportGameNumber()" in start, (
        "nothing re-arms the write-once snapshot at the start of a game")


def test_an_unreadable_number_makes_the_seat_ineligible_and_mints_nothing():
    """FAIL CLOSED. A local fallback is exactly the per-seat value the shared
    key exists to escape: substituting it manufactures the disagreement the
    freeze was added to remove, and a minted number settles a game that has
    already paid out."""
    rules = code_of(_plugin("FfaReportRules.cs"),
                    "internal static string ReportRoomId(string roomName, int frozenGame)")
    assert "if (frozenGame < 0) return null;" in rules, (
        "an absent snapshot no longer yields a null key")
    body = code_of(_plugin("GameStateWatcher.cs"), GAME_OVER)
    assert "FfaReportRules.CanFile(" in body, (
        "nothing gates the submit on the key being fileable")
    # code_of masks comments to blanks, so measure on the collapsed text:
    # the refusal must RETURN, and it must return before anything is posted.
    gate = " ".join(body.split("FfaReportRules.CanFile(", 1)[1].split())
    assert "return;" in gate, (
        "an unfileable key does not stop the report: " + gate[:200])
    assert gate.index("return;") < 200, (
        "the refusal is not the first thing the guard does: " + gate[:200])
    for minted in ("sessionMatchCount", "FfaMode.GameNumber", "matchStartTime"):
        assert not any(minted in l for l in body.splitlines()
                       if "ReportRoomId(" in l), (
            "%s reaches the report key" % minted)


def test_the_snapshot_is_the_hosts_published_number_and_is_cleared_per_match():
    body = code_of(_plugin("FfaMode.cs"), "internal static int FreezeReportGameNumber()")
    assert "PublishedGameNumber()" in body, (
        "the snapshot is not taken from the number the host published")
    assert "gameNumber" not in body, (
        "the snapshot falls back to this seat's local counter")
    started = code_of(_plugin("GameStateWatcher.cs"),
                      "public static void OnFfaMatchStarted()")
    assert "FfaMode.ClearReportGameNumber()" in started, (
        "a stale snapshot from the previous match survives into the next one")


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
