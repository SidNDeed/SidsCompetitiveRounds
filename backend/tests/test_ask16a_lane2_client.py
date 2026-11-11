"""Ask 16(a) lane 2: the continuation fence, client half.

The fence's decisions are pure (plugin/LimitlessFenceRules.cs) and run in the client
rules harness as suite `fencerules`, with a mutant per rule. This file pins that suite
by its case names, and pins the Unity- and Photon-side lines of the fence
(plugin/LimitlessFence.cs and its hooks) as source claims. Each claim has mutants that
turn it red and a control that leaves it green.

Design: ai-collab/seat-b/ASK16A-DESIGN-V4.md (md5 4283f353), sections 4 to 6.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from _cs_structure import mask_code, strip_comments_only
from test_client_rules_harness import _suites, harness_run  # noqa: F401  (the module fixture)

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugin"


def _read(path):
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


FENCE_RULES = (
    'gid: 16 lowercase hex is a gid',
    'gid: uppercase, 15 or 17 characters, a non-hex letter or null is not',
    'gid: eight bytes give their lowercase hex',
    'ledger: an ended gid is never live again',
    "ledger: a game start ends the previous gid and adopts the room's",
    'ledger: a start finds only a value it ended and holds no gid',
    'ledger: a start ends the gid it held, even while the room still names it',
    'ledger: room exit ends the current gid, and a rejoin never revives it',
    'ledger: adopting a new gid ends the one it replaces',
    'mint: the master mints over a value it has ended',
    'mint: a value this seat has not ended is adopted, not replaced',
    'mint: a room without a gid never mints (the feature does not run there)',
    'mint: never by a seat that is not master, nor before its own start',
    'mint: never while the seat holds a live gid',
    'arrival: a seat that awaits adopts a new value',
    'arrival: a fighter that holds its gid keeps it until its own start',
    'arrival: a spectator adopts a new value at any time',
    'arrival: a value this seat has ended is never adopted',
    'arrival: the value it holds, or a malformed one, changes nothing',
    'carrier: the gid round-trips',
    'carrier: the target round-trips',
    'carrier: the end flag round-trips',
    'carrier: the base winner round-trips',
    "carrier: the winner's rounds round-trip",
    "carrier: the other side's rounds round-trip",
    'carrier: the base target round-trips',
    'carrier: the spectatable flag round-trips',
    'carrier: the roster round-trips',
    "carrier: the round's arguments round-trip",
    "carrier: the send stamp round-trips",
    'carrier: a missing field refuses the whole carrier, slot by slot',
    'carrier: a mistyped field refuses the whole carrier, slot by slot',
    'carrier: a short or long carrier, or another version, is refused',
    'carrier: a target or base target below 1, or a negative count, is refused',
    'carrier: five arguments, or a roster with 0, a negative or a repeated actor, is refused',
    "carrier: the mirror's form (no roster, no arguments) decodes",
    'target: a live record plays to base + 50',
    'end target: 7-2 ends at 3',
    'end target: FFA 8, 3 and 1 ends at 2',
    'end target: no sides reads 1',
    'end target: whichever side completes the next round reaches it',
    'state: live with the end flag becomes terminating',
    'state: live without it stays live',
    'state: terminating never goes back to live',
    'state: ended stays ended',
    'MaySend: master, live gid, open record, same epoch and handoff count',
    'MaySend: a seat that is no longer master refuses',
    'MaySend: a gid that is not live refuses',
    'MaySend: an ended record refuses',
    'MaySend: a new physical game since scheduling refuses',
    'MaySend: a handoff since scheduling refuses',
    'MayResume: same epoch and the captured gid still live',
    'MayResume: a new physical game refuses',
    'MayResume: a replaced gid refuses',
    'MayResume: an ended record refuses',
    'MayResume: an item with no gid runs without one',
    'MayClean: cleanup reads the epoch only',
    'guard: an item that may continue runs every step and its end',
    'guard: a refusal before a step stops the item there',
    "guard: a stopped item's finally blocks run",
    'guard: a nested item runs under the same test',
    'guard: a value that is not an enumerator passes through',
    'guard: the test is read before the first step',
    'period: a master whose handoff count moved is in a new period',
    'period: the same handoff count is the same period',
    'period: a seat that is not master takes no path',
    'period: with no gid and no record the role alone decides (F1)',
    'pick: a seat promoted mid-cycle closes the cycle',
    'pick: a seat promoted in the manifest wait republishes',
    'pick: a seat that lost mastership is refused at the republish',
    'pick: a seat that lost mastership is refused at the close and leaves the loop cardless',
    'pick: a lost and regained mastership: the old ticket is refused, the re-captured close carries the new epoch',
    'pick: a lost and regained mastership in the manifest wait republishes under a new epoch',
    'pick: with no gid and no record, a lost and regained mastership sends as today',
    'pick: a record opened after the handoff: the next send takes the re-take first',
    'pick: a receiver drops a second close for the same game:cycle',
    'raw round: a live record refuses a call the fence did not make',
    'raw round: a terminating record refuses it too',
    "raw round: the fence's own call passes",
    'raw round: with no record, or an ended one, raw calls run as today',
    'decision: all five hold, so the game continues',
    'decision: no MaySend decides no',
    'decision: no live gid decides no',
    'decision: a seat that holds a record decides no',
    'decision: no fighters decides no',
    'decision: a fighter not opted in decides no',
    'decision: an opt-in for another gid decides no',
    'decision: a spectator at another version decides no',
    'decision: an actor without the capability decides no',
    'decision: a held seat decides no',
    'decision: a pending cut decides no',
    'decision: a following rated game decides no (D5)',
    're-read: unchanged inputs do not end',
    're-read: a handoff since the decision ends',
    're-read: a cleared opt-in ends',
    're-read: a changed capability ends',
    'handler: a valid decision on a seat with no record creates it',
    'handler: the sender test comes first',
    'handler: another gid is not covered',
    'handler: an ended record is not covered',
    'handler: the transition guard drops before the record changes',
    'handler: a seat with a record updates it',
    "handler: a roster that differs applies vanilla's round",
    'handler: no record and no roster is not covered',
    'roster: the same set in another order matches',
    'roster: a subset or a superset does not match',
    'roster: a duplicate entry never matches',
    'roster: an empty roster never matches',
    "frame: inside an RPC's frame the call sees its own, and the RPC's comes back",
    'frame: a frame nested in another restores each level',
    'frame: an exception inside the call restores the frame',
    'frame: the exception still reaches the caller',
    "decision round: the winner's round point at 4 of 5 rounds ends the game",
    'decision round: one point per round, the round that reaches the target ends it',
    'decision round: a point that completes no round ends nothing',
    'decision round: a round short of the target ends nothing',
    "decision round: a side already past the target still ends, as vanilla's test reads",
    'decision record: target base + 50, end clear, the base result at the send',
    'next send: a live record that need not end is unchanged',
    'next send: a live record that must end carries the end flag and the end target',
    'next send: a terminating record repeats itself, whatever the re-read finds',
    'series: an unrated game has no series to follow',
    'series: a rated FFA game keeps no series',
    'series: a rated game of a mode that keeps one is followed, read closed',
    "snapshot: a spectator's 18 fields stay, the late tail's place is padded, and the record takes [28]-[35]",
    "snapshot: a late snapshot's tail stays at [18]-[27], and the record follows it",
    'snapshot: the gid round-trips',
    'snapshot: the target round-trips',
    'snapshot: the end flag round-trips',
    'snapshot: the base winner round-trips',
    "snapshot: the winner's rounds round-trip",
    "snapshot: the other side's rounds round-trip",
    'snapshot: the base target round-trips',
    'snapshot: the spectatable flag round-trips',
    'snapshot: a snapshot without the record, or with a field missing or mistyped, carries none',
    "base results: team 1's 5-0 win is a victory and an ace",
    "base results: team 2's 5-3 win is a victory and no ace",
    "base results: team 1's 0-5 loss is a joker, and a 2-5 loss is nothing",
    "base results: team 2's 0-5 loss is a joker",
    'base results: the ace and the joker compare with the base target, not the raised one',
    'base results: a seat with no local team gets nothing',
    'base results: a seat on both teams gets what vanilla gives it at 5-0: a victory, an ace and a joker',
    "base results: the rounds are team 0's then team 1's, from the base winner",
    'base results: the streak restarts on a new winner and unlocks at 2, as vanilla',
)

FENCE_MUTANTS = (
    'MaySend ignores the handoff count',
    'MaySend ignores the epoch',
    "MaySend ignores the record's end",
    'MayResume reads the epoch only',
    'the guard reads its test after the step',
    'the guard does not guard nested items',
    'the guard leaves a stopped item undisposed',
    'the guard drops what the item yields',
    'the period is keyed on the role',
    'the re-take runs in every game',
    'the promotion keeps its old ticket',
    'the re-take keeps the held epoch',
    'the re-take misses a record opened after the capture',
    "a receiver reads a close without its phase's identity",
    'MayResume waits for a gid',
    'the decision ignores the capability',
    'the decision ignores the hold',
    'the decision ignores D5',
    'the decision ignores the opt-ins',
    'the re-read ignores the handoff count',
    'the handler tests the transition guard first',
    'the handler creates without the roster comparison',
    'the handler takes a message without a roster as a decision',
    "the handler applies an ended record's message",
    'the roster ignores duplicates',
    "the end target is the leader's plus one",
    'an empty side list ends at 0',
    'terminating goes back to live',
    'a terminating record lets raw calls through',
    'the mint ignores the ended test',
    'the terminal path forgets the gid',
    'a game start keeps the previous gid',
    'room exit forgets the ended gids',
    'room exit keeps the current gid',
    'adoption forgets the gid it replaces',
    'the mint runs in a room without a gid',
    'every fighter adopts on arrival',
    'a spectator waits like a fighter',
    'arrival ignores the ended set',
    'the frame is never set',
    'the frame is restored without a finally',
    'the frame is cleared, not restored',
    'the exception is swallowed',
    'a round ends the game only past the target',
    'a round ends the game without completing a round',
    'the end ignores the re-read',
    'a terminating record takes a new end target',
    'a rated game is never followed',
    'the series ignores the mode',
    "the snapshot's record skips the late tail's place",
    'the snapshot always reads a record',
    'the base results give no ace',
    'the base results give no joker',
    "the base results compare with the winner's rounds, not the base target",
    'the base results give the loser a victory',
    'the base rounds ignore the winner',
    'the streak never restarts',
)

CARRIER_FIELDS = (
    'the gid',
    'the target',
    'the end flag',
    'the base winner',
    "the winner's rounds",
    "the other side's rounds",
    'the base target',
    'the spectatable flag',
    'the roster',
    "the round's arguments",
    "the send stamp",
)


def _caught(names):
    return tuple("mutant (%s) is caught by its named cases" % m for m in names)


FENCE_CASES = (tuple("real: " + n for n in FENCE_RULES) + _caught(FENCE_MUTANTS)
               + _caught("the carrier drops " + f for f in CARRIER_FIELDS)
               + _caught("the snapshot drops " + f for f in CARRIER_FIELDS[:8]))


def test_the_fence_suite_ran_exactly_its_cases_and_passed(harness_run):
    """The suite ran exactly these cases, every one printed PASS, and each mutant
    turned its named cases red (#391)."""
    suites = _suites(harness_run)
    assert "fencerules" in suites, harness_run.stdout[-4000:]
    run, fail, verdict = suites["fencerules"]
    assert (run, fail, verdict) == (len(FENCE_CASES), 0, "PASS"), harness_run.stdout[-4000:]
    printed = re.findall(r"^\[fencerules\] (PASS|FAIL) \| case=([^|]+?) \|", harness_run.stdout, re.M)
    assert sorted(name for _, name in printed) == sorted(FENCE_CASES), printed
    assert {v for v, _ in printed} == {"PASS"}, printed


def test_the_pinned_names_are_distinct():
    assert len(set(FENCE_CASES)) == len(FENCE_CASES) == 144 + 57 + 11 + 8


# -- the fence's Unity- and Photon-side lines, as source claims --------------

FILES = {p.name: _read(p) for p in sorted(PLUGIN.glob("*.cs"))}
_MASKS = {}


def _masks(text):
    got = _MASKS.get(text)
    if got is None:
        got = _MASKS[text] = (mask_code(text), strip_comments_only(text))
        assert len(got[0]) == len(got[1]) == len(text)
    return got


def _code(text, sig=None):
    """A block (or the whole text) with comments removed, literals kept."""
    masked, stripped = _masks(text)
    if sig is None:
        return stripped
    start = masked.find(sig)
    assert start != -1 and masked.find(sig, start + 1) == -1, "one %r" % sig
    open_brace = masked.find("{", start + len(sig))
    depth = 0
    for i in range(open_brace, len(masked)):
        depth += {"{": 1, "}": -1}.get(masked[i], 0)
        if depth == 0:
            return stripped[open_brace:i + 1]
    raise AssertionError("unbalanced block after %r" % sig)


def _in_order(body, needles):
    at = -1
    for n in needles:
        if body.count(n) != 1 or body.index(n) < at:
            return False
        at = body.index(n)
    return True


def _first(body):
    return body.lstrip("{ \n").split("\n", 1)[0].strip()


LF = "LimitlessFence.cs"


def claim_the_game_start_prefix(files):
    """The fence's DoStartGame prefix runs at Priority.First and gates itself on the
    spectator suppressor's own predicate, since HarmonyX runs every prefix even when
    a sibling skips the original (#352). Only then does it note the game start."""
    out = []
    text = files[LF]
    if ('[HarmonyPatch(typeof(GM_ArmsRace), "DoStartGame")]\n    internal static class LimitlessFence_GameStart_Patch\n'
            '    {\n        [HarmonyPriority(Priority.First)]') not in _code(text):
        out.append("the prefix is not DoStartGame at Priority.First")
    body = _code(text, "private static void Prefix()")
    if not _in_order(body, ["if (SpectatorPatchSupport.Suppress) return;", "LimitlessFence.NoteOwnGameStart();"]):
        out.append("the spectator gate does not precede the start")
    return out


def claim_the_gid_is_stamped_before_the_join(files):
    """The creating seat's first gid rides the room's initial properties (v4 4.2):
    stamped into roomProps before the options take them and before JoinOrCreateRoom."""
    code = _code(files["Plugin.cs"])
    if _in_order(code, ["var roomProps = new ExitGames.Client.Photon.Hashtable",
                        "LimitlessFence.StampInitialGid(roomProps);",
                        "CustomRoomProperties = roomProps,",
                        "PhotonNetwork.JoinOrCreateRoom(capturedRoom, roomOptions, lobby)"]):
        return []
    return ["the gid is not in the room's initial properties"]


def claim_the_handoff_count_comes_first(files):
    """OnMasterClientSwitched's first statement notes the switch, and the count rises
    before the mint, so no work of the previous master period acts in this one."""
    out = []
    first = _first(_code(files["Plugin.cs"], "public void OnMasterClientSwitched(Photon.Realtime.Player newMasterClient)"))
    if first != "try { LimitlessFence.NoteMasterSwitched(newMasterClient); } catch { }":
        out.append("the switch's first statement is %r" % first)
    first = _first(_code(files[LF], "internal static void NoteMasterSwitched(Photon.Realtime.Player newMaster)"))
    if first != "_handoff++;":
        out.append("the count's first statement is %r" % first)
    return out


def claim_adoption_only_from_the_relay(files):
    """A gid becomes live only from the room's properties as the server relays them
    (lesson 428). AdoptRelayed is called once, in TryAdopt. TryAdopt's callers are
    the join, the property change and the spectator's boundary. The game start reads
    the room's relayed value. The mint adopts nothing."""
    out = []
    code = _code(files[LF])
    if code.count("AdoptRelayed(") != 1 or "_ledger.AdoptRelayed(value)" not in _code(
            files[LF], "private static void TryAdopt(string value, string why)"):
        out.append("AdoptRelayed is called outside TryAdopt")
    callers = sorted(re.findall(r"TryAdopt\(([^;]*)\);", code))
    if callers != sorted(['RoomGid(), "join"', 'RoomGid(), "spectator boundary"',
                          'changed[GidKey] as string, "arrival"']):
        out.append("TryAdopt's callers are %r" % callers)
    if code.count("AtOwnGameStart(") != 1 or "_ledger.AtOwnGameStart(RoomGid())" not in _code(
            files[LF], "internal static void NoteOwnGameStart()"):
        out.append("the start does not read the room's relayed value")
    return out


def claim_the_mint_is_a_compare_and_set(files):
    """The mint runs only on a seat that is not a spectator, only when the rule says
    so, and its write expects the value it replaces (v4 4.2, F1). It is the only
    write of the gid in a room."""
    out = []
    body = _code(files[LF], "private static void TryMint(string why)")
    if not _in_order(body, ["if (RoomActors.LocalIsSpectator) return;",
                            "if (!LimitlessFenceRules.ShouldMint(PhotonNetwork.IsMasterClient, _startedInRoom, current, _ledger)) return;",
                            "room.SetCustomProperties(",
                            "new ExitGames.Client.Photon.Hashtable { { GidKey, current } });"]):
        out.append("the mint is not gated, or does not expect the value it replaces")
    writes = re.findall(r"SetCustomProperties\(\s*new ExitGames\.Client\.Photon\.Hashtable \{ \{ (\w+),", _code(files[LF]))
    if writes.count("GidKey") != 1:
        out.append("another write of the gid")
    return out


def claim_the_room_edges_note_the_gid(files):
    """The join adopts the room's gid; room exit ends it and raises the epoch; the
    room's property change notes an arriving gid before anything else reads it."""
    out = []
    p = files["Plugin.cs"]
    if _code(p, "public void OnJoinedRoom()").count("LimitlessFence.NoteJoinedRoom();") != 1:
        out.append("the join does not adopt")
    if _code(p, "public void OnLeftRoom()").count("LimitlessFence.NoteLeftRoom();") != 1:
        out.append("room exit does not end the gid")
    first = _first(_code(p, "public void OnRoomPropertiesUpdate(ExitGames.Client.Photon.Hashtable propertiesThatChanged)"))
    if first != "try { LimitlessFence.NoteRoomProps(propertiesThatChanged); } catch { }":
        out.append("the property change's first statement is %r" % first)
    if not _in_order(_code(files[LF], "internal static void NoteLeftRoom()"), ["_epoch++;", "_ledger.ExitRoom();"]):
        out.append("room exit raises no epoch, or keeps the gid")
    return out


def claim_the_spectator_boundary(files):
    """A spectator's terminal score ends the observed gid (GM: the observer's game
    over; FFA: SpectatorCheckGameOver's first announcement), and its next call-in
    opens the next game before anything of it runs (v4 4.3, 5.3)."""
    out = []
    s = files["SpectatorSync.cs"]
    if not _in_order(_code(s, "internal static void OnGameOverObserved()"), [
            "if (!SpectatorSession.IsLocalSpectator || SpectatorSession.LeaveRequested) return;",
            'try { LimitlessFence.NoteSpectatorGameOver("gm"); } catch { }',
            "try { RoomRules.OnGameStart(); } catch { }"]):
        out.append("the GM observer's game over does not end the gid")
    if not _in_order(_code(s, "internal static void OnCallInObserved(int mapId)"), [
            "if (SpectatorSession.LeaveRequested) return;",
            "try { LimitlessFence.NoteSpectatorCallIn(); } catch { }",
            "_roundLatched = false;", "ScheduleBoundary(mapId);"]):
        out.append("the call-in does not open the next game first")
    if not _in_order(_code(files["FfaMode.cs"], "private static void SpectatorCheckGameOver("), [
            "spectatorGameOverAnnounced = true;", 'try { LimitlessFence.NoteSpectatorGameOver("ffa"); } catch { }']):
        out.append("the FFA observer's game over does not end the gid")
    return out


def _first_after(block, marker):
    """The first statement of the body that opens after `marker`."""
    at = block.index(marker)
    return _first(block[block.index("{", at):])


def claim_every_raw_round_sibling_refuses_first(files):
    """While a record is live or terminating, a call of RPCA_NextRound that the
    fence's handler did not make is refused (v4 4.4, F3). HarmonyX runs every
    sibling prefix and every postfix whatever a prefix returns (#352), so the
    refusal is the first statement of each: the fence's prefix (Priority.First),
    FFA's prefix and HandleNextRound, the spectator prefix and
    SpectatorObserveRound, and the two postfixes that move state: the stale
    projectile sweep, and PoisonSync's point boundary, where the refusal opens
    NotePointBoundary, the one guarded call its postfix makes (the poison lane's
    hook rule keeps that postfix's body guarded). Deviation from v4 recorded in
    the hand-back (integrator, 23:04Z): the sibling list is a class."""
    out = []
    lf, ffa, sp = files[LF], files["FfaMode.cs"], files["SpectatorPatches.cs"]
    if ('[HarmonyPatch(typeof(GM_ArmsRace), "RPCA_NextRound")]\n    internal static class LimitlessFence_RawRound_Patch\n'
            '    {\n        [HarmonyPriority(Priority.First)]') not in _code(lf):
        out.append("the fence's raw-round prefix is not RPCA_NextRound at Priority.First")
    sites = [
        ("the fence's prefix", _first_after(_code(lf, "internal static class LimitlessFence_RawRound_Patch"),
                                            "private static bool Prefix()"),
         'return !LimitlessFence.RawRoundRefused("gm");'),
        ("FFA's prefix", _first_after(_code(ffa, "class GMArmsRace_NextRound_Ffa_Patch"), "int p1RoundsSet, int p2RoundsSet)"),
         'if (LimitlessFence.RawRoundRefused("ffa prefix")) return false;'),
        ("HandleNextRound", _first(_code(ffa, "public static void HandleNextRound(GM_ArmsRace gm, int winnerTeam)")),
         'if (LimitlessFence.RawRoundRefused("ffa round")) return;'),
        ("the spectator prefix", _first_after(_code(sp, "internal static class Spectator_ObserveNextRound_Patch"),
                                              "int p1RoundsSet, int p2RoundsSet)"),
         'if (LimitlessFence.RawRoundRefused("spectator prefix")) return false;'),
        ("SpectatorObserveRound", _first(_code(ffa, "internal static void SpectatorObserveRound(int winnerTeam)")),
         'if (LimitlessFence.RawRoundRefused("ffa observer")) return;'),
        ("the point boundary", _first(_code(files["PoisonSync.cs"], "internal static void NotePointBoundary(GM_ArmsRace gm)")),
         'if (LimitlessFence.RawRoundRefused("point boundary")) return;'),
        ("the projectile sweep postfix", _first(_code(files["VanillaFixes.cs"], "private static void AfterNextRound()")),
         'if (LimitlessFence.RawRoundRefused("projectile sweep")) return;'),
    ]
    for name, got, want in sites:
        if got != want:
            out.append("%s's first statement is %r" % (name, got))
    if "HookGuard.Run(() => PoisonSync.NotePointBoundary(__instance));" not in _code(
            files["PoisonSync.cs"], "internal static class PoisonPointBoundaryPatch"):
        out.append("the point boundary postfix does not make its guarded call")
    body = _code(lf, "internal static bool RawRoundRefused(string site)")
    if _first(body) != "if (!LimitlessFenceRules.RefuseRawRound(_hasRecord, _state, _fenceCall)) return false;":
        out.append("the refusal does not read the record, its state and the fence's flag")
    return out


def claim_the_record_retires_at_each_boundary(files):
    """The record retires before anything of the next game runs: at the seat's own
    game start, at a spectator's boundary, when the seat adopts a new gid, at the
    join and at room exit (v4 4.3)."""
    out = []
    lf = files[LF]
    if _first(_code(lf, "internal static void NoteOwnGameStart()")) != 'RetireRecord("game start");':
        out.append("the game start does not retire the record first")
    if _first(_code(lf, "internal static void NoteJoinedRoom()")) != 'RetireRecord("join");':
        out.append("the join does not retire the record first")
    if not _in_order(_code(lf, "internal static void NoteLeftRoom()"), ["_ledger.ExitRoom();", 'RetireRecord("room exit");']):
        out.append("room exit does not retire the record")
    if not _in_order(_code(lf, "internal static void NoteSpectatorCallIn()"),
                     ["_epoch++;", 'RetireRecord("spectator boundary");', 'TryAdopt(RoomGid(), "spectator boundary");']):
        out.append("the spectator's boundary does not retire the record before it adopts")
    if not _in_order(_code(lf, "private static void TryAdopt(string value, string why)"),
                     ["if (!_ledger.AdoptRelayed(value)) return;", 'RetireRecord("new gid");']):
        out.append("a new gid does not retire the record")
    return out


APPLY_CALL = "try { PoisonRpcStampPatch.RunStamped(view, stamp, () => gm.RPCA_NextRound(a[0], a[1], a[2], a[3], a[4], a[5])); }"


def claim_the_round_applies_under_its_stamp(files):
    """Step 5: the fence applies the round by a direct call of vanilla's method,
    with its flag set, inside RunStamped under the message's stamp and the GM's
    view, so PoisonSync's point boundary records one stamp on every seat and v3
    stays on. RunStamped's frame is restored in a finally (ScopedFrame; the harness
    runs its nesting and exception cases). It is the plugin's only direct call."""
    out = []
    if not _in_order(_code(files[LF], "private static void ApplyFenceRound(GM_ArmsRace gm, int[] a, int stamp)"),
                     ["int view = gm.view != null ? gm.view.ViewID : 0;", "_fenceCall = true;", APPLY_CALL,
                      "finally { _fenceCall = false; }"]):
        out.append("the round is not applied with the flag, inside the stamp's frame")
    run = _code(files["PoisonSync.cs"], "internal static void RunStamped(int viewId, int ts, Action call)")
    if "ScopedFrame.RunInFrame<Frame>(() => _cur, f => _cur = f, new Frame { Has = true, View = viewId, Ts = ts }, call);" not in run:
        out.append("RunStamped does not run the call in a scoped frame for the view and stamp")
    direct = sorted(n for n, t in files.items() if re.search(r"\.RPCA_NextRound\(", _code(t)))
    if direct != [LF] or len(re.findall(r"\.RPCA_NextRound\(", _code(files[LF]))) != 1:
        out.append("direct calls of RPCA_NextRound: %r" % direct)
    return out


def claim_the_handler_runs_in_order(files):
    """4.7 on every seat: a message that does not decode is refused whole (F11), and
    one from the current master takes the terminal path; then the sender test, the
    rule, and an uncovered refusal's terminal path; then the record, the target and
    the master's mirror, and only then the round."""
    out = []
    body = _code(files[LF], "internal static void HandleFenceEvent(int sender, object[] data)")
    if not _in_order(body, ["out stamp)", "bool fromMaster = m != null && m.ActorNumber == sender;",
                            "if (fromMaster) TakeUncoveredPath();",
                            "SenderIsMasterNow = master != null && master.ActorNumber == sender,",
                            "var outcome = LimitlessFenceRules.HandleFenceMessage(h);"]):
        out.append("the decode, the sender test or the rule is out of order")
    case = body.split("case LimitlessFenceRules.HandlerOutcome.RefuseUncovered:", 1)[-1].split("case ", 1)[0]
    if "TakeUncoveredPath();" not in case or "return;" not in case:
        out.append("an uncovered refusal does not take the terminal path")
    if not _in_order(body, ["InstallRecord(rec, outcome == LimitlessFenceRules.HandlerOutcome.CreateRecord);",
                            "SetRecordTarget(gm, ffa, rec.TargetRounds);",
                            "if (PhotonNetwork.IsMasterClient) WriteRecordMirror(rec);"]) \
            or body.rindex("ApplyFenceRound(gm, args, stamp);") < body.index("WriteRecordMirror(rec);"):
        out.append("the round applies before the record, the target or the mirror")
    return out


def claim_the_message_is_reliable_to_all(files):
    """F9: the message goes to every seat, its sender included as the server relays
    it, reliably on channel 0, under an event code no other part of the mod uses."""
    out = []
    lf = files[LF]
    raise_body = _code(lf, "internal static bool RaiseFence(object[] payload)")
    if "Receivers = Photon.Realtime.ReceiverGroup.All" not in raise_body \
            or "ExitGames.Client.Photon.SendOptions.SendReliable" not in raise_body:
        out.append("the message is not reliable to every seat")
    if "PhotonNetwork.NetworkingClient.EventReceived += OnFenceEvent;" not in _code(lf, "internal static void HookFenceEvents()"):
        out.append("the handler is not hooked")
    if _first(_code(lf, "private static void OnFenceEvent(ExitGames.Client.Photon.EventData ev)")) \
            != "if (ev == null || ev.Code != EvtFence) return;":
        out.append("the handler does not filter its code")
    owners = sorted(n for n, t in files.items() if re.search(r"const byte \w+ = 59;", _code(t)))
    if owners != [LF] or "internal const byte EvtFence = 59;" not in _code(lf):
        out.append("event code 59 is declared in %r" % owners)
    return out


def claim_the_mirror_is_a_compare_and_set(files):
    """4.3, F2: the master's mirror write expects the record's gid and itself as the
    master (key 248), so a write made after a mint or a handoff does not land."""
    if _in_order(_code(files[LF], "private static void WriteRecordMirror(LimitlessFenceRules.FenceRecord rec)"),
                 ["room.SetCustomProperties(", "{ { RecordKey, LimitlessFenceRules.EncodeRecord(rec, null, null, 0) } }",
                  "{ GidKey, rec.Gid },", "{ Photon.Realtime.GamePropertyKey.MasterClientId, me.ActorNumber },"]):
        return []
    return ["the mirror's write does not expect the gid and the master"]


def claim_the_capability_is_staged_out_of_a_room(files):
    """cr_lim1 (the feature's version) is staged out of a room only, after both
    fence patches attached and the event hook is in, and after the compat verdict
    (#83, lesson 287). A patch counts live only when it attached without an
    exception. The tick hooks the event first, beside lane 1's deal staging; a
    compat disable revokes beside it."""
    out = []
    lf = files[LF]
    body = _code(lf, "internal static void StageFenceCapability(string source)")
    if not _in_order(body, ["if (_staged || _stageFailedPermanently) return;", "if (!GameStartLive || !RawRoundLive || !PlayerDiedLive)",
                            "if (!_hooked) return;", "if (!Plugin.compatCheckComplete) return;", "if (PhotonNetwork.InRoom)",
                            "string version = LimitlessBounds.Version;",
                            "local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable { { CapabilityProp, version } });"]):
        out.append("the staging's gates are out of order")
    elif "return;" not in body.split("if (PhotonNetwork.InRoom)", 1)[1].split("var st = ", 1)[0]:
        out.append("the staging does not stop in a room")
    for flag in ("GameStartLive", "RawRoundLive"):
        if _code(lf).count("if (exception == null) LimitlessFence.%s = true;" % flag) != 1:
            out.append("%s is not set only by a clean attach" % flag)
    p = _code(files["Plugin.cs"])
    if not _in_order(p, ['try { BoundedDeal.StageCapability("tick"); } catch { }', "try { LimitlessFence.HookFenceEvents(); } catch { }",
                         'try { LimitlessFence.StageFenceCapability("tick"); } catch { }']):
        out.append("the tick does not hook, then stage")
    if p.count("try { LimitlessFence.RevokeFenceCapability(); } catch { }") != 1:
        out.append("a compat disable does not revoke")
    return out


def claim_an_uncovered_case_leaves_once(files):
    """Table B: a case the fence does not cover is this seat's terminal path, taken
    once per room: a spectator leaves as a room-rules mismatch does (LeaveToMenu), a
    fighter through vanilla's restart, so every other seat sees a departure."""
    out = []
    lf = files[LF]
    if not _in_order(_code(lf, "private static void TakeUncoveredPath()"), [
            "if (_uncoveredLeaving) return;", "_uncoveredLeaving = true;",
            'if (RoomActors.LocalIsSpectator) SpectatorSync.LeaveToMenu("limitless: an uncovered fence message");',
            "else if (NetworkConnectionHandler.instance != null) NetworkConnectionHandler.instance.NetworkRestart();"]):
        out.append("the terminal path is not one leave by the seat's kind")
    for sig in ("internal static void NoteJoinedRoom()", "internal static void NoteLeftRoom()"):
        if "_uncoveredLeaving = false;" not in _code(lf, sig):
            out.append("%s keeps the leave latched" % sig)
    return out


def claim_the_gm_decision_prefix(files):
    """4.7, GM: the master's PlayerDied prefix runs at Priority.Last and acts only
    when vanilla's body would still run (__runOriginal). When the fence sends or
    withholds the round, vanilla's body is skipped and its slow-down runs here. A
    fault runs vanilla's body. The capability needs this patch attached."""
    out = []
    lf = files[LF]
    if ('[HarmonyPatch(typeof(GM_ArmsRace), "PlayerDied")]\n    internal static class LimitlessFence_PlayerDied_Patch\n'
            '    {\n        [HarmonyPriority(Priority.Last)]') not in _code(lf):
        out.append("the decision prefix is not PlayerDied at Priority.Last")
    pre = _code(lf, "private static bool Prefix(GM_ArmsRace __instance, bool __runOriginal)")
    if not _in_order(pre, ["if (!__runOriginal) return false;", "try { sent = LimitlessFence.GmRoundSend(__instance); }",
                           'ex.Message);\n                return true;', "if (sent == LimitlessFence.FenceSend.Vanilla) return true;",
                           "TimeHandler.instance.DoSlowDown(); } catch { }\n            return false;"]):
        out.append("the prefix does not defer, send, then skip vanilla's body with its slow-down")
    if _code(lf).count("if (exception == null) LimitlessFence.PlayerDiedLive = true;") != 1:
        out.append("PlayerDiedLive is not set only by a clean attach")
    return out


GM_SEND = [
    "if (gm == null || FfaMode.EngineActive()) return FenceSend.Vanilla;",
    "|| !PhotonNetwork.IsMasterClient) return FenceSend.Vanilla;",
    "if (pm == null || pm.TeamsAlive() >= 2) return FenceSend.Vanilla;",
    "int[] args = { pm.GetOtherTeam(winner), winner, gm.p1Points, gm.p2Points, gm.p1Rounds, gm.p2Rounds };",
    "if (RecordOpen) return SendContinuation(args, new[] { gm.p1Rounds, gm.p2Rounds }, _epoch, _handoff);",
    "if (!LimitlessFenceRules.RoundEndsGame(winner == 0 ? gm.p1Points : gm.p2Points, wRounds, ptw, gm.roundsToWinGame))",
    "return SendDecision(args, gm.roundsToWinGame, winner, wRounds, winner == 0 ? gm.p2Rounds : gm.p1Rounds, _epoch, _handoff);",
]


def claim_the_gm_round_send(files):
    """4.7, GM: on the master only, at a round end, with vanilla's own arguments
    (GM_ArmsRace:505-510). Past the base every round goes through the fence; at
    the round that would end the game at the base, the decision; otherwise
    vanilla's message."""
    if _in_order(_code(files[LF], "internal static FenceSend GmRoundSend(GM_ArmsRace gm)"), GM_SEND):
        return []
    return ["the GM send's tests or arguments are out of order"]


def claim_the_ffa_round_send(files):
    """4.4 and 4.7, FFA: the point is scheduled with the epoch and the handoff
    count before FFA's yield. At FFA's send, after the map-scale count, the fence
    sends in place of vanilla's message, MaySend at the send. When it withholds,
    nothing goes out and the latch is released; a fault sends vanilla's."""
    out = []
    ffa, lf = files["FfaMode.cs"], files[LF]
    if not _in_order(_code(ffa, "public static void HandlePlayerDied(GM_ArmsRace gm)"), [
            "if (!FfaLateEntry.MasterMaySend() || pointLatched || isTransitioning) return;",
            "LimitlessFence.NoteFfaPointScheduled();", "pointLatched = true;", 'StartCoroutine(LimitlessFence.ResumableItem(ResolvePointEndOfFrame(gm), "ffa point"));']):
        out.append("the point is not captured where it is scheduled")
    if not _in_order(_code(ffa, "private static void ResolvePointNow(GM_ArmsRace gm)"), [
            "try { FfaMapScale.MasterPublishCount(FfaLateEntry.PointK + 1); } catch { }",
            "try { fence = LimitlessFence.FfaRoundSend(winnerTeam); }", "fence = LimitlessFence.FenceSend.Vanilla;",
            "if (fence == LimitlessFence.FenceSend.Withheld) pointLatched = false;",
            "if (fence != LimitlessFence.FenceSend.Vanilla) return;",
            'gm.view.RPC("RPCA_NextRound", RpcTarget.All, winnerTeam, winnerTeam, 0, 0, 0, 0);']):
        out.append("FFA's send does not defer to the fence after the map-scale count")
    if not _in_order(_code(lf, "internal static FenceSend FfaRoundSend(int winnerTeam)"), [
            "int[] args = { winnerTeam, winnerTeam, 0, 0, 0, 0 };",
            "if (RecordOpen) return SendContinuation(args, sides, _ffaEpoch, _ffaHandoff);",
            "if (winnerTeam < 0) return FenceSend.Vanilla;",
            "if (!LimitlessFenceRules.RoundEndsGame(FfaMode.PointsFor(winnerTeam), wRounds, FfaMode.PointsToWinRound, FfaMode.RoundsToWin))",
            "return SendDecision(args, FfaMode.RoundsToWin, winnerTeam, wRounds, other, _ffaEpoch, _ffaHandoff);"]):
        out.append("the FFA fence send's tests or arguments are out of order")
    if not _in_order(_code(lf, "internal static void NoteFfaPointScheduled()"), ["_ffaEpoch = _epoch;", "_ffaHandoff = _handoff;"]):
        out.append("the capture does not take the epoch and the handoff count")
    return out


DECIDE = [
    "MaySend = LimitlessFenceRules.MaySend(PhotonNetwork.IsMasterClient, _ledger.IsLiveGid(gid), false,",
    "_epoch, epochCaptured, _handoff, handoffCaptured),", "HasRecord = _hasRecord,", "FighterOptIns = FighterOptIns(),",
    "ActorCapabilities = ActorCapabilities(),", "MasterVersion = OwnCapability(),",
    "HoldHasHeldSeat = TeamHoldLoop.FenceHolds(),", "HoldHasPendingCut = TeamHold.Cut != null,",
    "SeriesFollows = LimitlessFenceRules.SeriesFollows(GameStateWatcher.MatchIsRanked, !FfaMode.EngineActive()),",
    "var why = LimitlessFenceRules.DecideContinuation(d);", "if (why != LimitlessFenceRules.Decision.Continue)",
    'why + ")");\n                return FenceSend.Vanilla;', "GameStateWatcher.RankedCodeRoom1v1InProgress);", "var roster = ReplicatedFighters().ToArray();",
    "if (!RaiseFence(LimitlessFenceRules.EncodeRecord(rec, roster, args, PhotonNetwork.ServerTimestamp)))",
]


def claim_the_decision_reads_its_inputs(files):
    """4.7: the decision's five tests read replicated inputs and the hold writer's
    state; D5 is read closed (integrator ruling 23:45Z). The message carries the
    decision record, the decision roster, vanilla's arguments and the sender's
    ServerTimestamp. A raise that does not go out ends the game at the base."""
    if _in_order(_code(files[LF], "private static FenceSend SendDecision("), DECIDE):
        return []
    return ["the decision's inputs or its message are not as 4.7 reads them"]


CONT = [
    "bool may = LimitlessFenceRules.MaySend(PhotonNetwork.IsMasterClient,",
    "_state == LimitlessFenceRules.FencePhase.PhaseEnded, _epoch, epochCaptured, _handoff, handoffCaptured);",
    "if (!may)", 'MaySend refused");\n                return FenceSend.Withheld;',
    "|| LimitlessFenceRules.MustEnd(FighterOptIns(), _record.Gid, ActorCapabilities(), OwnCapability(),",
    "_handoff, _handoffAtRecord);", "var rec = LimitlessFenceRules.NextSendRecord(_record, mustEnd, sides);",
    "if (!RaiseFence(LimitlessFenceRules.EncodeRecord(rec, null, args, PhotonNetwork.ServerTimestamp)))",
]


def claim_every_later_round_rereads(files):
    """4.4, 4.7 and 5.1: every round past the base. MaySend runs with the
    captured epoch and handoff count. The master re-reads the opt-ins, the
    capabilities and its handoff count against the count its own handler took
    when it created the record; once an end is decided every later message
    carries the same record. The message carries the sender's stamp."""
    out = []
    lf = files[LF]
    if not _in_order(_code(lf, "private static FenceSend SendContinuation("), CONT):
        out.append("a later round's send is not MaySend, the re-read, then the record")
    if "if (create) _handoffAtRecord = _handoff;" not in _code(lf, "private static void InstallRecord("):
        out.append("the handoff count is not taken when the record is created")
    return out


def claim_the_opt_in_writer(files):
    """4.7, D4 and D6: lane 3's radio calls SetOptIn. cr_limitless holds the live
    gid only, and is written only when it differs from the relayed value. It
    clears at the seat's own game start (the radio resets to off) and at the
    join, and follows a gid change."""
    out = []
    lf = files[LF]
    if not _in_order(_code(lf, "internal static void SetOptIn(bool on)"), ["_optInWanted = on;", 'WriteOptIn("radio");']):
        out.append("the radio does not write")
    if not _in_order(_code(lf, "private static void WriteOptIn(string why)"), [
            "if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return;",
            "string want = _optInWanted && _ledger.IsLiveGid(gid) ? gid : null;",
            "if (string.Equals(have as string, want, StringComparison.Ordinal)) return;",
            "local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable { { OptInKey, want } });"]):
        out.append("the write is not the live gid, in a room, on a change")
    for sig, steps in (("internal static void NoteOwnGameStart()", ["_optInWanted = false;", 'WriteOptIn("game start");']),
                       ("internal static void NoteJoinedRoom()", ["_optInWanted = false;", 'TryAdopt(RoomGid(), "join");', 'WriteOptIn("join");']),
                       ("private static void TryAdopt(string value, string why)", ['RetireRecord("new gid");', 'WriteOptIn("new gid");']),
                       ("internal static void NoteLeftRoom()", ["_optInWanted = false;"])):
        if not _in_order(_code(lf, sig), steps):
            out.append("%s does not reset or rewrite the opt-in" % sig)
    return out


TERM = [
    "if (p == null || !RecordOpen || RoomActors.IsSpectatorReplicated(p)) return;",
    "_departed = true;", 'Terminate("fighter departure");',
]


def claim_termination_is_set(files):
    """4.6: a fighter's departure, never a spectator's, and a master change
    make a live record terminating; never back. The departure flag lasts as
    long as its record."""
    out = []
    lf = files[LF]
    if not _in_order(_code(lf, "internal static void TerminateOnDeparture("), TERM):
        out.append("a departure does not terminate the record as 4.6 reads it")
    if not _in_order(_code(lf, "private static void Terminate(string why)"),
                     ["if (!RecordOpen) return;", "_state = LimitlessFenceRules.NextState(_state, true);"]):
        out.append("termination does not move the record to terminating")
    if not _in_order(_code(lf, "internal static void NoteMasterSwitched("), ["_handoff++;", 'Terminate("master change");']):
        out.append("a master change does not terminate the record after the handoff count rises")
    if not _in_order(_code(lf, "internal static void RetireRecord("), ["_departed = false;", "if (!_hasRecord) return;"]):
        out.append("the departure flag outlives its record")
    return out


ROUTE_FIRST = "try { LimitlessFence.TerminateOnDeparture(otherPlayer); } catch { }"


def claim_every_departure_route_terminates_first(files):
    """4.6: termination is the first statement of each departure route: the
    Plugin hook (ahead of TeamHold.OnLeave), the hold's NCH prefix (ahead of
    Classify, whatever another prefix returned) and FFA's NCH prefix (ahead
    of its EngineActive branch)."""
    out = []
    routes = [
        (_code(files["Plugin.cs"], "public void OnPlayerLeftRoom(Photon.Realtime.Player p)"),
         "try { LimitlessFence.TerminateOnDeparture(p); } catch { }", "the Plugin hook"),
        (_code(_code(files["TeamHoldPatches.cs"], "internal static class NCH_OnPlayerLeftRoom_Hold_Patch"), " Prefix("),
         ROUTE_FIRST, "the hold's NCH prefix"),
        (_code(_code(files["FfaMode.cs"], "class NCH_OnPlayerLeftRoom_Ffa_Patch"), " Prefix("),
         ROUTE_FIRST, "FFA's NCH prefix"),
    ]
    for body, want, name in routes:
        if _first(body) != want:
            out.append("termination is not the first statement of " + name)
    return out


def claim_the_hold_reads_the_record_first(files):
    """4.6: the hold's inputs carry the record and its rule refuses a hold
    while a record is live or terminating. Classify, the leave callback and
    the cascade prefix read the record first, ahead of the memo and the held
    set."""
    out = []
    tw = files["TeamHoldWriter.cs"]
    if "FenceOpen = LimitlessFence.RecordOpen," not in _code(tw, "private static TeamHoldRules.GateInputs Read("):
        out.append("the gate's inputs do not carry the record")
    if not _in_order(_code(files["TeamHoldRules.cs"], "internal static bool Decide(GateInputs i)"),
                     ["if (i == null || i.Pin == null || !i.Pin.Hold) return false;", "if (i.FenceOpen) return false;",
                      "return true;"]):
        out.append("the hold rule does not refuse inside a continuation")
    if not _in_order(_code(tw, "internal static bool Classify(Photon.Realtime.Player p)"),
                     ["if (LimitlessFence.RecordOpen) return false;", "TeamHoldRules.Flagged(", "HoldGate.DecideOnce("]):
        out.append("Classify reaches the memo during a record")
    if not _in_order(_code(tw, "internal static bool OnLeave("),
                     ["if (LimitlessFence.RecordOpen) return false;", "if (_held.Contains(p.ActorNumber)) return true;"]):
        out.append("the leave callback reads the held set before the record")
    pre = _code(_code(files["TeamHoldPatches.cs"], "internal static class NCH_OnPlayerLeftRoom_Hold_Patch"), " Prefix(")
    if not _in_order(pre, ["if (!__runOriginal) return false;", "if (LimitlessFence.RecordOpen) return true;",
                           "TeamHold.Classify(otherPlayer)"]):
        out.append("the cascade prefix classifies before reading the record")
    return out


def claim_termination_reaches_the_sender(files):
    """4.6, 4.7: after a departure in 1v1, 2v2, OVT or sct the GM master sends
    nothing more for the record; a terminating record ends at the next send."""
    out = []
    lf = files[LF]
    if not _in_order(_code(lf, "internal static FenceSend GmRoundSend(GM_ArmsRace gm)"),
                     ["if (RecordOpen && _departed) return WithheldAfterDeparture();", "if (RecordOpen) return SendContinuation("]):
        out.append("the GM master sends after a departure")
    if _code(lf, "private static FenceSend WithheldAfterDeparture()").count("return FenceSend.Withheld;") != 1:
        out.append("the departure's answer is not a withheld round")
    if not _in_order(_code(lf, "private static FenceSend SendContinuation("),
                     ["bool mustEnd = _state == LimitlessFenceRules.FencePhase.PhaseTerminating",
                      "|| LimitlessFenceRules.MustEnd("]):
        out.append("a terminating record goes out without its end")
    return out


REDRIVE = [
    "if (gm == null || gameOverFired || GameManager.instance == null || !GameManager.instance.battleOngoing) return;",
    "if (FfaLateEntry.LocalSitsOut() || RoomActors.LocalIsSpectator) return;",
    "if (AlivePlayers().Count > 1) return;",
    "if (!FfaLateEntry.MasterMaySend() || pointLatched || isTransitioning) return;",
    "LimitlessFence.NoteFfaPointScheduled();", "pointLatched = true;", "ResolvePointNow(gm);",
]
SETTLED = [
    "LimitlessFence.NoteMasterSwitched(newMasterClient);", "FfaMapScale.OnMasterClientSwitched();",
    "FfaMode.OnMasterClientSwitched();", "FfaLateEntry.OnMasterSwitched(newMasterClient);",
    'SpectatorSync.LeaveToMenu("no fighter to hold master");',
    "LimitlessFence.RedriveAfterHandoff(newMasterClient);", "if (!Diag2v2.IsActive()) return;",
]


def claim_the_new_master_redrives(files):
    """4.6: FFA after a master change. Once the master is settled, the new
    master re-drives a pending point through the fence's sender while a
    record is live or terminating, with HandlePlayerDied's gates, its capture
    and its latch."""
    out = []
    if not _in_order(_code(files["Plugin.cs"], "public void OnMasterClientSwitched(Photon.Realtime.Player newMasterClient)"),
                     SETTLED):
        out.append("the re-drive does not run once the master is settled")
    if _first(_code(files[LF], "internal static void RedriveAfterHandoff(")) != \
            "if (newMaster == null || !newMaster.IsLocal || !RecordOpen || !FfaMode.EngineActive()) return;":
        out.append("the re-drive is not the new master's, in FFA, with a record open")
    if not _in_order(_code(files["FfaMode.cs"], "internal static void RedrivePendingPoint(GM_ArmsRace gm)"), REDRIVE):
        out.append("the re-drive does not keep HandlePlayerDied's gates, the capture and the latch")
    return out


ADMIT_ENTRANT = [
    ("private static IEnumerator AdmittedLateRun(", "if (body)",
     "if (LimitlessFence.RecordOpen) { LateGiveUp(); yield break; }", "LateArmed = true;", "arming"),
    ("internal static void OnBoundaryLoad(string scene)", "if (!LateArmed || _lateEntered) return;",
     "if (LimitlessFence.RecordOpen) { LateGiveUp(); return; }", "_lateLoads++;", "request"),
    ("private static IEnumerator SendLateRequest()", "yield return null;",
     "if (LimitlessFence.RecordOpen) { LateGiveUp(); yield break; }", "Raise(SpectatorSync.EVT_REQUEST,", "request's send"),
    ("private static void OnLateSnapshot(EventData e)", "S(a, 2) == LateClosed",
     "if (LimitlessFence.RecordOpen) { LateGiveUp(); return; }", "_pendingSnap = a;", "snapshot's arrival"),
    ("private static void CheckPendingSnapshot()", "if (a == null) return;",
     "if (LimitlessFence.RecordOpen) { LateGiveUp(); return; }", "string digest = SnapshotDigest(", "admission check"),
]


def claim_no_fighter_is_admitted(files):
    """4.6, F7: while a record is live or terminating no fighter is admitted,
    and every refusal is a terminal answer. The master answers a late request
    at once with the closed snapshot and closes every pending one at its
    boundary. It proposes no new epoch, so no body is kept (a slow starter
    sits out). The entrant's own arming, request and admission give up and
    leave."""
    out = []
    le = files["FfaLateEntry.cs"]
    if not _in_order(_code(le, "internal static void OnLateRequest(int sender, int seq)"),
                     ["if (!MasterMaySend() || !AdmissionRoomNow()) return;",
                      'if (LimitlessFence.RecordOpen) { Refused("limitless", sender); SendSnapshot(sender, seq, true); return; }',
                      "if (FfaAssembly.ReadmitLobby)"]):
        out.append("the master does not close a late request at once")
    flat = " ".join(_code(le, "internal static IEnumerator MasterBoundary()").split())
    if not _in_order(flat, ["_lateWaits.TryGetValue(actor, out waits);",
                            "if (LimitlessFence.RecordOpen) { SendSnapshot(actor, kv.Value, true); "
                            "_lateRequests.Remove(actor); continue; }",
                            "if (waits >= 2)"]):
        out.append("the boundary sends an open snapshot during a record")
    if ("bool proposed = FfaLateRules.MayPropose(nStar, PointEpoch, selfKindS) && MasterMaySend() "
            "&& !LimitlessFence.RecordOpen;") not in flat:
        out.append("the boundary proposes a new epoch during a record")
    for sig, before, line, after, name in ADMIT_ENTRANT:
        if not _in_order(_code(le, sig), [before, line, after]):
            out.append("the entrant's " + name + " does not give up during a record")
    return out


LATE_TAIL = [
    ("FfaLateEntry.cs", "private static void OnSelfKept(int g)",
     ["if (string.IsNullOrEmpty(AdmittedLateLobby) || _lateEntered) return;",
      "if (LimitlessFence.RecordOpen) { _pendingSelfKeptGame = 0; LateGiveUp(); return; }",
      "if (!ReadmitEnteredReady("], "the entered POST"),
    ("FfaMode.cs", "internal static ReadmitReplayOutcome ReadmitReplayAtKeep(",
     ["if (!ReadmitReplayCurrent(replay) || Plugin.Instance == null || LimitlessFence.RecordOpen)",
      "Plugin.Instance.StartCoroutine(ReadmitReplayRun(replay, cards));"], "the readmit replay's start"),
    ("FfaMode.cs", "private static IEnumerator ReadmitReplayRun(",
     ["yield return ReadmitReplaySteps(replay, () => ReadmitReplayCurrent(replay) && !LimitlessFence.RecordOpen,"],
     "the readmit replay's steps"),
    ("FfaReadmit.cs", "private static void Act(string step,",
     ["case FfaReadmitEntryRules.RdmNext.ArmLate:",
      'if (LimitlessFence.RecordOpen) { Refusal("limitless", true); break; }',
      "FfaLateEntry.PrepareReadmitEntry();"], "the readmission's arming"),
]


def claim_the_late_tail_is_refused(files):
    """4.6, F7 (Table A's X rows): the entered POST, the readmit replay's start
    and each of its steps, and a readmission's arming refuse while a record is
    live or terminating. A refused seat leaves at once: the entered POST
    through LateGiveUp, a readmission through its refusal with leave set."""
    out = []
    for fname, sig, needles, name in LATE_TAIL:
        if not _in_order(_code(files[fname], sig), needles):
            out.append(name + " is not refused during a record")
    return out


def claim_a_refused_entrant_is_no_departure(files):
    """v4 Table B: a refused entrant was never admitted, so its exit sets no
    termination. The kept-actor view decides, after the spectator test and
    before the departure flag."""
    out = []
    if not _in_order(_code(files[LF], "internal static void TerminateOnDeparture("),
                     ["if (p == null || !RecordOpen || RoomActors.IsSpectatorReplicated(p)) return;",
                      "if (FfaLateEntry.IsQuarantinedActor(p.ActorNumber)) return;",
                      "_departed = true;"]):
        out.append("a refused entrant's exit terminates the record")
    return out


RI = "LimitlessFence.ResumableItem("
RESUME_ROWS = [
    ("FfaMode.cs", ["StartCoroutine(" + RI + 'ResolvePointEndOfFrame(gm), "ffa point"))'], "FFA's point"),
    ("FfaMode.cs", ['StartCoroutine(LimitlessFence.CleanupItem(EndSittingBelowMinimum(), "ffa sitting end"))'], "the sitting's end (C)"),
    ("FfaMode.cs", ["gm.StartCoroutine(" + RI + 'FfaTransition(gm, winnerTeam, roundOver), "ffa transition"))'], "FFA's transition"),
    ("FfaMode.cs", ["gm.StartCoroutine(" + RI + 'FfaLocalPickUI(gm, localPlayer, game, cycle, phaseNonce), "ffa pick ui"))'],
     "FFA's pick UI"),
    ("FfaMode.cs", ["StartCoroutine(" + RI + 'FfaMode.CheckRoundAfterLeave(), "ffa leave"))'], "FFA's leave route"),
    ("FfaMode.cs", ["__result = " + RI + 'FfaMode.FfaDoStartGame(__instance), "ffa start");'], "FFA's start, its picks and boundary"),
    ("TeamHoldFence.cs", ["__result = " + RI + 'HoldFence.Run(__instance, TeamHoldRules.PointSteps, __0, -1), "2v2 point transition");'],
     "2v2's point transition"),
    ("TeamHoldFence.cs", ["__result = " + RI + 'HoldFence.Run(__instance, TeamHoldRules.RoundSteps, __0, __1), "2v2 round transition");'],
     "2v2's round transition"),
    ("VanillaFixes.cs", ["__result = " + RI + 'SafeRespawn(__instance, playerIDToRevive), "phoenix revive");'], "the Phoenix revive"),
    ("TeamHoldPick.cs", ["__result = " + RI + 'TeamHoldPick.WaitRecord(__result, picketIDToSet), "pick wait");'], "the pick wait"),
    ("TeamHoldReturn.cs", ["host.StartCoroutine(" + RI + "ReplayRun(work, slots, (slot, name) =>", '}), "hold replay"));'],
     "the hold's replay"),
    ("FfaLateEntry.cs", ["StartCoroutine(" + RI + 'OwnDeathAfterCallIn(), "lag-out death"))'], "the lag-out death"),
    ("FfaLateEntry.cs", ["StartCoroutine(" + RI + 'AdmittedLateRun(a), "late arming"))'], "the late arming"),
    ("Plugin.cs", ["StartCoroutine(" + RI + 'FfaAssembly.GatedSpawn(Auto2v2SpawnCoroutine), "spawn"))'], "the gated spawn"),
    ("Plugin.cs", ["StartCoroutine(" + RI + 'Auto2v2SpawnCoroutine(), "spawn"))'], "the spawn"),
]


def claim_every_table_a_row_is_guarded(files):
    """4.5, Table A: each coroutine row is scheduled through ResumableItem, so
    it captures its ticket where it is scheduled and runs MayResume before
    every step, nested items included; the sitting's end (C) goes through
    CleanupItem, which reads the epoch only."""
    out = []
    for fname, needles, name in RESUME_ROWS:
        if not _in_order(_code(files[fname]), needles):
            out.append(name + " is not scheduled under its ticket")
    return out


def claim_the_guard_reads_a_ticket_captured_at_schedule(files):
    """4.5: the guard tests before every step, nested items under the same
    test, and disposes a stopped item (the harness runs it: suite fencerules,
    the guard cases). The ticket is captured once, where the item is
    scheduled; R reads the epoch, the gid and the record's end, C the epoch."""
    out = []
    g = _code(files["LimitlessFenceRules.cs"], "internal static System.Collections.IEnumerator GuardScheduled(")
    if not _in_order(g, ["if (item == null) yield break;", "if (!mayContinue())", "if (onStop != null) onStop();",
                         "if (!item.MoveNext()) yield break;",
                         "var nested = item.Current as System.Collections.IEnumerator;",
                         "yield return nested != null ? GuardScheduled(nested, mayContinue, onStop) : item.Current;",
                         "if (d != null) d.Dispose();"]):
        out.append("the guard does not test before every step with nested items guarded and the item disposed")
    lf = files[LF]
    checks = [
        ("internal static ResumeTicket CaptureTicket()",
         ["return new ResumeTicket { Epoch = _epoch, Gid = RecordOpen ? _record.Gid : null, Handoff = _handoff };"], "the ticket"),
        ("internal static bool TicketResumes(ResumeTicket t)",
         ["bool ended = t.Gid != null",
          "(!_hasRecord || _record.Gid != t.Gid || _state == LimitlessFenceRules.FencePhase.PhaseEnded);",
          "return LimitlessFenceRules.MayResume(_epoch, t.Epoch, t.Gid, _ledger, ended);"], "R"),
        ("internal static bool TicketCleans(ResumeTicket t)", ["return LimitlessFenceRules.MayClean(_epoch, t.Epoch);"], "C"),
        ("internal static System.Collections.IEnumerator ResumableItem(",
         ["var t = CaptureTicket();",
          "return LimitlessFenceRules.GuardScheduled(item, () => TicketResumes(t), () => NoteItemStopped(name, t));"],
         "ResumableItem"),
        ("internal static System.Collections.IEnumerator CleanupItem(",
         ["var t = CaptureTicket();",
          "return LimitlessFenceRules.GuardScheduled(item, () => TicketCleans(t), () => NoteItemStopped(name, t));"],
         "CleanupItem"),
    ]
    for sig, needles, name in checks:
        if not _in_order(_code(lf, sig), needles):
            out.append(name + " does not read a ticket captured at schedule as 4.5 states")
    return out


PICK = "private static IEnumerator FfaPickPhase("
PICK_SENDS = [
    "float phaseStart = Time.realtimeSinceStartup;",
    "var sendTicket = LimitlessFence.CaptureTicket();",
    'if (WriteCycleProp($"{game}:{cycle}:{string.Join(",", pickerIds)}", phaseEpoch)) ArmTicket(game);',
    'sendTicket = PickTicket("manifest reopen");',
    'if (RetakeMasterPeriod(sendTicket)) sendTicket = PickTicket("manifest period");',
    "&& LimitlessFence.TicketSends(sendTicket, FfaLateEntry.MasterMaySend()))",
    'if (WriteCycleProp($"{game}:{cycle}:{string.Join(",", pickerIds)}", sendEpoch)) ArmTicket(game);',
    "if (wasMaster && RetakeMasterPeriod(sendTicket)) wasMaster = false;",
    "if (FfaLateEntry.MasterMaySend() && !wasMaster)",
    "adoptIdentity(game, cycle, null, true, null);",
    'sendTicket = PickTicket("promotion");',
    'sendTicket = PickTicket("pick reopen");',
    "string closeEpoch = maySend ? EpochForUse() : null;",
    "maySend = LimitlessFence.TicketSends(sendTicket, maySend);",
    "if (FfaNumberingRules.AuthoritativeClose(maySend, manifest != null,",
    "WriteResultProp(sb.ToString(), closeEpoch, grantMarker);",
]


def claim_the_pick_sends_answer_to_their_ticket(files):
    """4.4 at FFA's pick phase (integrator 01:14Z and 01:29Z): the ticket is
    captured at the phase's entry, before the entry write. The republish and
    the close are S rows and send only through TicketSends. A master in a new
    master period (its handoff count no longer its ticket's) drops its epoch,
    takes the promotion path and re-captures before the send: in the manifest
    wait before the republish, in the pick wait at the promotion (the reissue,
    then the reopen). Each reopen re-captures too. The bail sends nothing (R)."""
    body = _code(files["FfaMode.cs"], PICK)
    return [] if _in_order(body, PICK_SENDS) else ["the pick sends do not answer to a ticket re-captured at each promotion"]


def claim_a_new_master_period_issues_a_fresh_epoch(files):
    """RetakeMasterPeriod drops the held epoch for a master whose handoff count
    moved while the fence applies; the ticket carries the handoff count;
    TicketSends is MaySend with the count, and the role alone with no gid and
    no record (F1); the period reads a record opened after the capture."""
    out = []
    fm = files["FfaMode.cs"]
    if not _in_order(_code(fm, "private static bool RetakeMasterPeriod("),
                     ["if (!LimitlessFence.TicketHandoffMoved(t, FfaLateEntry.MasterMaySend())) return false;",
                      "phaseEpoch = FfaNumberingRules.HeldEpoch(phaseEpoch, null);", "phaseEpochIssuer = -1;",
                      "return true;"]):
        out.append("a new master period does not drop the held epoch")
    if not _in_order(_code(fm, "private static LimitlessFence.ResumeTicket PickTicket("),
                     ["var t = LimitlessFence.CaptureTicket();", "return t;"]):
        out.append("the pick ticket is not a fresh capture")
    lf = files[LF]
    checks = [
        ("internal static ResumeTicket CaptureTicket()",
         ["return new ResumeTicket { Epoch = _epoch, Gid = RecordOpen ? _record.Gid : null, Handoff = _handoff };"],
         "the ticket"),
        ("internal static bool TicketSends(ResumeTicket t, bool masterNow)",
         ["string gid = TicketGid(t);", "if (gid == null) return masterNow;",
          "bool live = _ledger.IsLiveGid(gid) && string.Equals(gid, _ledger.CurrentGid, StringComparison.Ordinal);",
          "bool ended = !_hasRecord || _record.Gid != gid || _state == LimitlessFenceRules.FencePhase.PhaseEnded;",
          "return LimitlessFenceRules.MaySend(masterNow, live, ended, _epoch, t.Epoch, _handoff, t.Handoff);"],
         "TicketSends"),
        ("internal static bool TicketHandoffMoved(ResumeTicket t, bool masterNow)",
         ["return LimitlessFenceRules.HandoffPeriodMoved(masterNow, TicketGid(t) != null, _handoff, t.Handoff);"],
         "TicketHandoffMoved"),
        ("private static string TicketGid(ResumeTicket t)", ["return t.Gid ?? (RecordOpen ? _record.Gid : null);"],
         "TicketGid"),
    ]
    for sig, needles, name in checks:
        if not _in_order(_code(lf, sig), needles):
            out.append(name + " does not read the ticket as 4.4 states")
    if not _in_order(_code(files["LimitlessFenceRules.cs"], "internal static bool HandoffPeriodMoved("),
                     ["return masterNow && fenceApplies && handoffNow != handoffCaptured;"]):
        out.append("the master period is not keyed on the handoff count")
    return out


RECEIVER_LEAVES = ('finalizedEpochs, game, cycle, out viaLegacy); if (result != null) { resultApplies = true; '
                   'if (viaLegacy) Plugin.Log.LogInfo($"[FFA-NUM] legacy result applied {game}:{cycle} '
                   '({result.Count} cards, older-build form)"); break; }')


def claim_a_receiver_applies_one_close_per_phase(files):
    """Today's behaviour, kept (integrator 01:14Z, test 4): each pick phase
    counts its own cycle at its entry, reads a result only for its game:cycle
    and leaves its result loop on the first answer. So a second close for the
    same game:cycle reaches no seat that applied the first (the envelope rule
    runs in the harness: suite fencerules, the receiver case)."""
    body = _code(files["FfaMode.cs"], PICK)
    out = []
    if not _in_order(body, ["cycleNumber++;", "int cycle = cycleNumber;", "var sendTicket = LimitlessFence.CaptureTicket();"]):
        out.append("the phase does not count its cycle at its entry")
    if RECEIVER_LEAVES not in " ".join(body.split()):
        out.append("a receiver does not leave its result loop on the first answer")
    return out


FLE = "FfaLateEntry.cs"


def claim_the_late_items_resume_under_their_ticket(files):
    """4.5 (R), Table A's late-entry rows that a tick resumes: the call-in hold
    captures its ticket where it is made and CallInHoldTick replays the call-in
    only under it; the pending snapshot captures its ticket where it is kept and
    CheckPendingSnapshot runs only under it. A stopped item is dropped."""
    out = []
    fle = files[FLE]
    if not _in_order(_code(fle, "private sealed class Hold"),
                     ["public float Rt;", "public LimitlessFence.ResumeTicket Ticket = LimitlessFence.CaptureTicket();"]):
        out.append("the call-in hold captures no ticket")
    if not _in_order(_code(fle, "private static void CallInHoldTick("),
                     ["var h = _hold;", "if (h == null) return;",
                      'if (!LimitlessFence.ItemResumes(h.Ticket, "call-in hold")) { _hold = null; return; }',
                      "MapManager.instance.RPCA_CallInNewMapAndMovePlayers(h.MapId);"]):
        out.append("the call-in hold is replayed without its ticket")
    if not _in_order(_code(fle), ["_pendingSnap = a;", "_pendingSnapTicket = LimitlessFence.CaptureTicket();",
                                  "_snapK = N(a, 25, -1);"]):
        out.append("the pending snapshot captures no ticket")
    if not _in_order(_code(fle, "private static void CheckPendingSnapshot("),
                     ["if (a == null) return;",
                      'if (!LimitlessFence.ItemResumes(_pendingSnapTicket, "pending snapshot")) { _pendingSnap = null; return; }',
                      "string digest = SnapshotDigest(a, g, k, level);"]):
        out.append("the pending snapshot is checked without its ticket")
    if not _in_order(_code(files[LF], "internal static bool ItemResumes("),
                     ["if (TicketResumes(t)) return true;", "NoteItemStopped(name, t);", "return false;"]):
        out.append("a retained item does not resume under TicketResumes")
    return out


def claim_the_late_sends_answer_to_their_ticket(files):
    """4.4 (S), Table A's late-entry sends: the call-in stamp, after the
    boundary's waits, sends only under the ticket MasterBoundary captured at its
    entry; a stored late request is answered at the boundary only under the
    ticket it was received under (captured past the record's closed answer),
    and the tickets clear with the requests."""
    out = []
    fle = files[FLE]
    if not _in_order(_code(fle, "internal static IEnumerator MasterBoundary("),
                     ["int g = FfaMode.GameNumber, k = PointK, self = OwnActor();",
                      "var sendTicket = LimitlessFence.CaptureTicket();", "int actor = kv.Key;",
                      "if (!LimitlessFence.TicketSends(LateTicket(actor), MasterMaySend()))",
                      "if (waits >= 2)", "if (!LimitlessFence.TicketSends(sendTicket, MasterMaySend())) yield break;",
                      "if (!MasterMaySend()) yield break;",
                      "Raise(EVT_CALLIN, new object[] { stamp.Lobby8, g, k, n, stamp.Chain, result },"]):
        out.append("the boundary's sends do not answer to their tickets")
    if not _in_order(_code(fle, "internal static void OnLateRequest(int sender, int seq)"),
                     ['if (LimitlessFence.RecordOpen) { Refused("limitless", sender); SendSnapshot(sender, seq, true); return; }',
                      "_lateTickets[sender] = LimitlessFence.CaptureTicket();",
                      "if (verdict == FfaReadmitEntryRules.LateReq.Accept) _lateRequests[sender] = seq;"]):
        out.append("a stored late request keeps no ticket")
    if not _in_order(_code(fle, "private static LimitlessFence.ResumeTicket LateTicket("),
                     ["return _lateTickets.TryGetValue(actor, out t) ? t : LimitlessFence.CaptureTicket();"]):
        out.append("a stored request is not read with its own ticket")
    if not _in_order(_code(fle), ["_lateRequests.Clear();", "_lateTickets.Clear();"]):
        out.append("the late tickets outlive their requests")
    return out


THW = "TeamHoldWriter.cs"


def claim_the_hold_acts_only_under_its_cut_ticket(files):
    """4.5, Table A's hold rows (H, and R guards them anyway): the cut captures
    its ticket where it is latched. TeamHold.Cut reads a cut whose ticket moved
    as none. The point tick, the leave and the expiry drop such a cut first,
    so the expiry's today-path never runs for an earlier game. An expired
    drop's end runs under its cut's ticket. The state read's and the end
    post's answers apply only under the ticket captured where each was issued."""
    out = []
    t = files[THW]
    if not _in_order(_code(t, "internal static bool OnLeave("),
                     ["if (CutResumes())", "if (!HoldsAnother(p)) return false;", "_cut = cut;",
                      "_cutTicket = LimitlessFence.CaptureTicket();", "_leaveAt = Time.unscaledTime;"]):
        out.append("the cut captures no ticket, or the leave keeps an earlier game's cut")
    if not _in_order(_code(t), ["internal static TeamHoldRules.DropCut Cut { get { return _cut != null"
                                " && LimitlessFence.TicketResumes(_cutTicket) ? _cut : null; } }"]):
        out.append("the cut is read without its ticket")
    if not _in_order(_code(t, "internal static bool CutResumes("),
                     ["if (_cut == null) return false;", 'if (LimitlessFence.ItemResumes(_cutTicket, "hold")) return true;',
                      "_cut = null;", "_purged = _resolved = false;"]):
        out.append("a cut whose ticket moved is kept")
    if not _in_order(_code(t, "internal static void Expire("),
                     ["if (cut == null) return;", "if (!CutResumes()) return;", "_cut = null;",
                      "TeamHoldExpiry.Run(cut, reason);"]):
        out.append("the expiry runs the today-path for an earlier game's cut")
    if not _in_order(_code(t), ["if (!CutResumes() || _resolved) return;", "char observed = ObservedState();"]):
        out.append("the point tick runs without the cut's ticket")
    loop = _code(t, "internal static class TeamHoldLoop")
    if not _in_order(loop, ["&& _writer.P == TeamHoldRules.Writer.Phase.Ending && EndingResumes())",
                            "Perform(_writer.Tick(now), _endingCut);"]):
        out.append("an expired drop's end runs without its ticket")
    if not _in_order(loop, ["_endingCut = cut;", "_endingTicket = TeamHold.CutTicket;"]):
        out.append("the ending cut keeps no ticket")
    if not _in_order(_code(t, "private static bool EndingResumes("),
                     ['if (LimitlessFence.ItemResumes(_endingTicket, "hold end")) return true;', "_endingCut = null;"]):
        out.append("a stopped end is kept")
    if not _in_order(_code(t, "private static void VerifyRead("),
                     ["int gen = _readGen;", "var rt = LimitlessFence.CaptureTicket();",
                      'if (gen != _readGen || !LimitlessFence.ItemResumes(rt, "hold read")) return;', "_server ="]):
        out.append("the state read's answer applies without its ticket")
    if not _in_order(_code(t, "private static void Perform("),
                     ["case TeamHoldRules.Writer.Op.PostEnd:", "var rt = LimitlessFence.CaptureTicket();",
                      'if (w == _writer && LimitlessFence.ItemResumes(rt, "hold end answer")) Perform(w.OnEndAnswer(Now), cut);']):
        out.append("the end post's answer applies without its ticket")
    return out


SPS = "SpectatorSync.cs"
OBS_STEP = "if (ObserverMoved(gen, attemptGen, ticket)) yield break;"
SESSION_ONLY = "if (gen != _boundaryGeneration) yield break;"


def claim_the_observer_apply_reads_its_attempt_and_epoch(files):
    """4.5, Table A's F5 rows (R): the boundary captures its ticket where it is
    scheduled and hands it to the deck apply. Every resume check inside the
    apply's loop and inside the nested reset and replay reads ObserverMoved:
    the session, the attempt (every boundary raises it) and the epoch. The
    attempt is passed down, so the nested replay stops without waiting for
    its parent. The rows read the epoch, not the gid (the game-over flush
    waits an in-flight apply out), and a stop by the epoch is a later game's
    boundary, not a failed apply."""
    out = []
    s = files[SPS]
    if not _in_order(_code(s, "private static IEnumerator BoundaryAttempt("),
                     ["var ticket = LimitlessFence.CaptureTicket();", "var prior = CurrentStage;",
                      "yield return ApplyDecks(snap, gen, attemptGen, forceReset, ticket);",
                      "if (attemptGen != _boundaryAttemptGen) { superseded = true; yield break; }",
                      "if (!LimitlessFence.TicketCleans(ticket)) { superseded = true; yield break; }",
                      "if (!_lastApplyOk)"]):
        out.append("the boundary's ticket is not captured, handed down or read after the apply")
    apply = _code(s, "private static IEnumerator ApplyDecks(")
    if apply.count(OBS_STEP) != 3 or SESSION_ONLY in apply or not _in_order(apply, [
            "if (attemptGen != _boundaryAttemptGen) yield break;",
            "yield return ResetAndReplay(body, actor, target, gen, attemptGen, ticket);"]):
        out.append("a resume inside the apply's loop reads the session alone")
    replay = _code(s, "private static IEnumerator ResetAndReplay(")
    if replay.count(OBS_STEP) != 2 or SESSION_ONLY in replay:
        out.append("a resume inside the nested replay reads the session alone")
    if not _in_order(_code(s), ["internal static bool ObserverMoved(int gen, int attemptGen, LimitlessFence.ResumeTicket ticket)",
                                '=> BoundaryFenceMoved(gen, attemptGen) || !LimitlessFence.EpochHolds(ticket, "observer deck apply");']):
        out.append("the observer's check skips the attempt or the epoch")
    if not _in_order(_code(files[LF], "internal static bool EpochHolds("),
                     ["if (TicketCleans(t)) return true;", "NoteItemStopped(name, t);"]):
        out.append("the epoch check does not stop")
    return out


def claim_the_observer_flush_reads_the_epoch(files):
    """4.5, Table A's F5 row for OnGameOverObserved (C), and FFA's twin: the
    observer's flush at the end runs as a cleanup item, which reads the epoch
    only, so it cannot act in a later game, whose call-in raises the epoch
    first. Every start of the GM flush and of its waiter is wrapped."""
    out = []
    s = files[SPS]
    if not _in_order(_code(s, "internal static void OnGameOverObserved("),
                     ['LimitlessFence.NoteSpectatorGameOver("gm");',
                      'DeferredGameOverFlush(_boundaryGeneration, _boundaryAttemptGen, _lastSeenEpoch), "observer flush wait"));',
                      'Plugin.Instance.StartCoroutine(LimitlessFence.CleanupItem(BetweenGamesFlush(_boundaryGeneration, _boundaryAttemptGen), "observer flush"));']):
        out.append("the game-over flush is not a cleanup item")
    whole = _code(s)
    if (whole.count("BetweenGamesFlush(") != 3 or whole.count("LimitlessFence.CleanupItem(BetweenGamesFlush(") != 2
            or whole.count("DeferredGameOverFlush(") != 2 or whole.count("LimitlessFence.CleanupItem(") != 3):
        out.append("a start of the observer's flush is not a cleanup item")
    if not _in_order(_code(s, "private static IEnumerator DeferredGameOverFlush("),
                     ['Plugin.Instance.StartCoroutine(LimitlessFence.CleanupItem(BetweenGamesFlush(gen, attemptGen), "observer flush"));']):
        out.append("the waiter's flush is not a cleanup item")
    f = _code(files["FfaMode.cs"])
    if f.count("SpectatorBetweenGamesFlush(") != 2 or not _in_order(f, [
            "Plugin.Instance.StartCoroutine(LimitlessFence.CleanupItem(SpectatorBetweenGamesFlush(",
            'SpectatorSync.BoundaryAttemptGeneration), "ffa observer flush")); }']):
        out.append("FFA's observer flush is not a cleanup item")
    return out


def claim_the_retirement_puts_the_base_target_back(files):
    """R1 (section 3): the record's retirement puts the target it raised back
    at the base before the record is cleared, so nothing of the next game runs
    at the continuation's target: GM's roundsToWinGame takes the record's base
    target, FFA's RoundsToWin its config writers' value. SetRecordTarget notes
    which field it wrote."""
    out = []
    lf = files[LF]
    if not _in_order(_code(lf, "internal static void RetireRecord("),
                     ["if (!_hasRecord) return;", "RestoreBaseTarget(why);", "_hasRecord = false;",
                      "_record = default(LimitlessFenceRules.FenceRecord);"]):
        out.append("the retirement does not put the base back before it clears the record")
    if not _in_order(_code(lf, "private static void RestoreBaseTarget("),
                     ["if (!_targetRaised) return;", "_targetRaised = false;",
                      "if (_targetFfa) FfaMode.RestoreConfiguredTarget();",
                      "if (gm != null) gm.roundsToWinGame = _record.BaseTarget;"]):
        out.append("the restore misses a mode or the base")
    if not _in_order(_code(lf, "private static void SetRecordTarget("),
                     ["if (ffa) FfaMode.RoundsToWin = target;", "else if (gm != null) gm.roundsToWinGame = target;",
                      "else return;", "_targetRaised = true;", "_targetFfa = ffa;"]):
        out.append("the record's target write is not noted for the restore")
    if not _in_order(_code(files["FfaMode.cs"], "internal static void RestoreConfiguredTarget("),
                     ["RoundsToWin = _configuredTarget;"]):
        out.append("FFA's restore does not apply the configured value")
    return out


def claim_ffa_config_writers_go_through_one_setter(files):
    """Table B (a), FFA's RoundsToWin writers: SetPendingConfig (the poll, the
    assembly, LatchConfigFromRoom and so the spectator latch) and
    ResetConfigToDefaults write the target only through SetConfiguredTarget.
    While a record is live or terminating, the record's target stays and the
    value waits for the next game. FfaMode writes RoundsToWin nowhere else,
    and the fence's handler is the one writer outside it."""
    out = []
    f = files["FfaMode.cs"]
    if not _in_order(_code(f, "public static void SetPendingConfig("),
                     ["SetConfiguredTarget(Mathf.Clamp(scoreTarget, 3, 10));"]):
        out.append("the pending config writes the target past the setter")
    if not _in_order(_code(f, "public static void ResetConfigToDefaults("), ["SetConfiguredTarget(5);"]):
        out.append("the defaults write the target past the setter")
    if not _in_order(_code(f, "private static void SetConfiguredTarget("),
                     ["_configuredTarget = target;", "if (LimitlessFence.HoldsFfaTarget) return;", "RoundsToWin = target;"]):
        out.append("the setter overwrites a record's target")
    if not _in_order(_code(files[LF], "internal static bool HoldsFfaTarget"),
                     ["get { return RecordOpen && _targetRaised && _targetFfa; }"]):
        out.append("the hold does not read the open record's FFA target")
    if len(re.findall(r"\bRoundsToWin\s*=(?![=>])", _code(f))) != 3:
        out.append("FfaMode writes RoundsToWin outside the setter and the restore")
    others = sum(len(re.findall(r"\bFfaMode\.RoundsToWin\s*=(?![=>])", _code(t)))
                 for n, t in files.items() if n != "FfaMode.cs")
    if others != 1:
        out.append("a writer outside FfaMode other than the fence's handler")
    return out


GIDOK = "if (!string.Equals(rec.Gid, RoomGid(), StringComparison.Ordinal) || !_ledger.IsLiveGid(rec.Gid)) return;"
TARGET_IN = "SetRecordTarget(GM_ArmsRace.instance, FfaMode.EngineActive(), rec.TargetRounds);"


def claim_the_joiner_reads_the_mirror_once_unconfirmed(files):
    """4.3, F2, Table B (a)'s join row: the spectator's join reads cr_lrec in
    the rules latch's step, once per join and before any snapshot, and only
    for the room's live gid. The record is unconfirmed: it raises the seeding
    target only, until an accepted message or the master's snapshot."""
    out = []
    lf, s = files[LF], files["SpectatorSync.cs"]
    if not _in_order(_code(s, "internal static void OnJoinedSpectatorRoom("),
                     ['rulesVerdict = RoomRules.LatchOnJoin(PhotonNetwork.CurrentRoom, "spectator");',
                      'LimitlessFence.ReadJoinRecord("spectator join");', "RoomRules.ClearPending();"]):
        out.append("the join does not read the mirror in the rules latch's step")
    if not _in_order(_code(lf, "internal static void ReadJoinRecord("),
                     ["if (_joinRecordRead) return;", "_joinRecordRead = true;", "if (_hasRecord) return;",
                      "LimitlessFenceRules.TryDecodeRecord(raw as object[]", GIDOK, "_unconfirmed = true;", TARGET_IN]):
        out.append("the mirror's read is not once, not bound to the gid or not unconfirmed")
    if not _in_order(_code(lf, "internal static void NoteJoinedRoom("), ['RetireRecord("join");', "_joinRecordRead = false;"]):
        out.append("a join does not re-arm the read")
    if not _in_order(_code(lf, "private static void InstallRecord("), ["_hasRecord = true;", "_unconfirmed = false;"]):
        out.append("an accepted message does not confirm the record")
    if not _in_order(_code(lf, "internal static void RetireRecord("), ["_hasRecord = false;", "_unconfirmed = false;"]):
        out.append("the retirement keeps the unconfirmed mark")
    return out


def claim_the_snapshot_carries_and_replaces_the_record(files):
    """5.2, Table B (a)'s spectator snapshot row: the master's answer carries
    its open, confirmed record at [28]-[35] with the seat's state. The
    receiver takes it right after the authority check, before any field,
    score or seed applies: it replaces an unconfirmed record or installs one
    for the room's live gid, an accepted message's record stays, a snapshot
    without one retires an unconfirmed record, and the mirror is then not
    read."""
    out = []
    lf, s = files[LF], files["SpectatorSync.cs"]
    if "var snap = LimitlessFence.AppendSnapshotRecord(BuildSnapshot(seq));" not in _code(s):
        out.append("the master's answer carries no record")
    if not _in_order(_code(lf, "internal static object[] AppendSnapshotRecord("),
                     ["if (snap == null || !RecordOpen || _unconfirmed) return snap;",
                      "r.EndFlag = _state == LimitlessFenceRules.FencePhase.PhaseTerminating;",
                      "return LimitlessFenceRules.SnapshotWithRecord(snap, r);"]):
        out.append("the answer carries an unconfirmed or closed record, or not the seat's state")
    if not _in_order(_code(s, "private static void HandleSnapshot("),
                     ['FfaLateEntry.Refused("authority", e.Sender)', "if (m == null || m.ActorNumber != e.Sender) return;",
                      "LimitlessFence.TakeSnapshotRecord(a);", 'WatchedMode = a[2] as string ?? "";',
                      "SpectatorViewState.RecordScore(", "FfaMode.SpectatorSeedScores(rounds, points);"]):
        out.append("the record is not taken between the authority check and the fields")
    if not _in_order(_code(lf, "internal static void TakeSnapshotRecord("),
                     ["_joinRecordRead = true;", "if (!LimitlessFenceRules.TrySnapshotRecord(snap, out rec))",
                      "if (_hasRecord && _unconfirmed) RetireRecord(", "if (_hasRecord && !_unconfirmed) return;",
                      GIDOK, "_unconfirmed = false;", TARGET_IN]):
        out.append("the snapshot's record is not taken as 5.2 says")
    return out


def claim_a_terminating_seed_never_ends_the_observer(files):
    """5.1 (F6), Table B (b)'s FFA target row: while the record is
    terminating, the FFA observer's game-over test ends it only on a round
    that completes, never from seeding, whose end target can sit below the
    lead. The seed passes false and the completed round true."""
    out = []
    f = files["FfaMode.cs"]
    if not _in_order(_code(f, "private static void SpectatorCheckGameOver("),
                     ["bool terminal = leadTeam >= 0 && leadRounds >= RoundsToWin;",
                      "if (terminal && !completedRound && LimitlessFence.RecordTerminating) return;",
                      "if (!terminal)", 'LimitlessFence.NoteSpectatorGameOver("ffa");']):
        out.append("a seed can end a terminating observer")
    if not _in_order(_code(f, "internal static void SpectatorSeedScores("),
                     ["SpectatorLatchConfigOnce();", "SpectatorCheckGameOver(false);"]):
        out.append("the seed reads as a completed round")
    if not _in_order(_code(f), ["rounds[winnerTeam] = RoundsFor(winnerTeam) + 1;\n                        points.Clear();\n"
                                "                        SpectatorCheckGameOver(true);"]):
        out.append("a completed round does not reach the test")
    if _code(f).count("SpectatorCheckGameOver(") != 3:
        out.append("another caller of the observer's test")
    if not _in_order(_code(files[LF], "internal static bool RecordTerminating"),
                     ["get { return _hasRecord && _state == LimitlessFenceRules.FencePhase.PhaseTerminating; }"]):
        out.append("the terminating test reads another state")
    return out


def claim_the_gm_observer_ends_at_the_live_target(files):
    """Table B (b)'s GM target row, the observer's half (F13): the spectator
    prefix, after the raw-round refusal, computes the terminal score against
    the live roundsToWinGame, which the fence's handler sets at step 4 before
    the round applies at step 5 (the handler's claim). It ends only on a
    round's conversion and dispatches SpectatorSync.OnGameOverObserved, which
    ends the gid (the spectator boundary's claim)."""
    out = []
    body = _code(files["SpectatorPatches.cs"], "internal static class Spectator_ObserveNextRound_Patch")
    if not _in_order(body, ['if (LimitlessFence.RawRoundRefused("spectator prefix")) return false;',
                            "int rtw = __instance.roundsToWinGame; if (rtw <= 0) rtw = 5;",
                            "bool gameOver = conversion\n                    && (winningTeamID == 0 ? p1r : p2r) >= rtw;",
                            "if (gameOver) SpectatorSync.OnGameOverObserved();"]):
        out.append("the GM observer's end does not read the live target on a conversion")
    return out


GSW = "GameStateWatcher.cs"


def claim_the_match_start_is_gated_in_a_continuation(files):
    """Section 6, finding A: OnMatchStarted returns while a record is live or
    terminating, before the per-game counters, isTracking and the report
    latch, so a continuation never re-arms the report. Both triggers, the
    poll and vanilla's MOVE PLAYERS END line, go through it. The latch's
    three reset sites stay pinned: the gated one, FFA's game start (from
    FFA's DoStartGame only) and ResetMatchState."""
    out = []
    g = files[GSW]
    if not _in_order(_code(g, "private static void OnMatchStarted("),
                     ["if (RoomActors.LocalIsSpectator) return;", "if (LimitlessFence.RecordOpen) return;",
                      "try { Keybinds.OnRoundStart(); } catch { }", "isTracking = true;", "gameOverReported = false;"]):
        out.append("the match start re-arms before the continuation gate")
    whole = _code(g)
    if not _in_order(whole, ["if (gameActive && !wasGameInProgress && !isTracking)\n            {\n                OnMatchStarted();\n            }"]):
        out.append("the poll's trigger does not go through the gate")
    if not _in_order(whole, ["if (!isTracking)\n                {\n                    try { OnMatchStarted(); } catch (Exception ex)"]):
        out.append("the log line's trigger does not go through the gate")
    if whole.count("isTracking = true;") != 2 or whole.count("gameOverReported = false;") != 4:
        out.append("a re-arm outside the gated start, FFA's start and the reset")
    if "gameOverReported = false;" not in _code(g, "public static void OnFfaMatchStarted("):
        out.append("FFA's game start does not reset the latch")
    if sum(_code(t).count("GameStateWatcher.OnFfaMatchStarted()") for t in files.values()) != 1:
        out.append("FFA's re-arm has another caller")
    return out


FFA_BASE = ("if (roundOver && !gameOver && winnerTeam >= 0 && LimitlessFence.RecordOpen\n"
            "                && rounds[winnerTeam] >= LimitlessFence.CurrentRecord.BaseTarget)")


def claim_ffa_reports_at_the_base_and_ends_at_the_real_end(files):
    """Section 6, finding B, Table C1's FFA row: a base branch reports the
    game once, when a round brings a side to the record's base target, and
    leaves gameOverFired clear, so the rounds run on. The ending branch at the
    real end sets gameOverFired and runs the ending, the sitting end's leave
    included, and OnFfaGameOver returns at its latch there."""
    out = []
    body = _code(files["FfaMode.cs"], "public static void HandleNextRound(")
    if not _in_order(body, ["gameOver = rounds[winnerTeam] >= RoundsToWin;", FFA_BASE,
                            "[FFA] base report hook", "if (gameOver)", "gameOverFired = true;",
                            "[FFA] game-over report hook",
                            'LimitlessFence.CleanupItem(EndSittingBelowMinimum(), "ffa sitting end")']):
        out.append("the base does not report, or the ending is not the real end's")
    elif any(n in body[body.index(FFA_BASE):body.index("if (gameOver)")]
             for n in ("gameOverFired", "EndSittingBelowMinimum", "isTransitioning")):
        out.append("the base branch ends the game")
    if body.count("GameStateWatcher.OnFfaGameOver(winnerTeam);") != 2:
        out.append("FFA's report has another caller in the round")
    if not _in_order(_code(files["GameStateWatcher.cs"], "public static void OnFfaGameOver("),
                     ["if (RoomActors.LocalIsSpectator) return;", "if (gameOverReported) return;",
                      "gameOverReported = true;", "isTracking = false;"]):
        out.append("FFA's report is not latched once")
    return out


LFN = "LimitlessFence.cs"
RUN_BASE = "if (outcome == LimitlessFenceRules.HandlerOutcome.CreateRecord && !ffa) RunBaseResults(gm, rec);"


def claim_the_base_runs_vanillas_results_once(files):
    """Section 6, Table C1 (H7), at the base: the seat that created the record
    runs vanilla's GameOver block once, after the creating round applied, from
    the base result and the base target, in GM only (vanilla's GameOver never
    runs in FFA). The six platform calls are vanilla's, in vanilla's order, by
    name, and the streak moves as vanilla moves it. A missing name is logged."""
    out = []
    lf = files[LFN]
    h = _code(lf, "internal static void HandleFenceEvent(")
    if h.count(RUN_BASE) != 1 or h.index(RUN_BASE) < h.rindex("ApplyFenceRound(gm, args, stamp);"):
        out.append("the base's results do not follow the creating round")
    if _code(lf).count("RunBaseResults(") != 2:
        out.append("the base's results have another caller")
    if not _in_order(_code(lf, "private static void RunBaseResults("), [
            "if (gm == null || SpectatorPatchSupport.Suppress) return;",
            "LimitlessFenceRules.BaseRounds(rec, out p1, out p2);",
            "int team = (int)gm.m_localTeam;",
            "LimitlessFenceRules.BaseGameAwards((team & 1) != 0, (team & 2) != 0, rec.BaseWinner, p1, p2, rec.BaseTarget);",
            "if (aw.BaseVictory)",
            'PlatformCall("UnlockAchievement", "Victory");',
            'PlatformCall("ProgressAchievement", "Winner");',
            'PlatformCall("ProgressAchievement", "Champion");',
            "int last = gm.m_lastWinningTeam, count = gm.m_winCount;",
            "three = LimitlessFenceRules.StreakStep(ref last, ref count, rec.BaseWinner);",
            "gm.m_lastWinningTeam = last;",
            "gm.m_winCount = count;",
            'if (three) PlatformCall("UnlockAchievement", "ThreeInARow");',
            'if (aw.BaseAce) PlatformCall("UnlockAchievement", "Ace");',
            'if (aw.BaseJoker) PlatformCall("UnlockAchievement", "Joker");']):
        out.append("the base's copy is not vanilla's block, in vanilla's order")
    if not _in_order(_code(lf, "private static void PlatformCall("), [
            "typeof(FriendlyFoe.Platform.PlatformManager).GetMethod(method, BindingFlags.Public | BindingFlags.Static);",
            "!Enum.IsDefined(p[0].ParameterType, achievement)", "Plugin.Log.LogWarning(", "return;",
            "m.Invoke(null, new[] { Enum.Parse(p[0].ParameterType, achievement) });"]):
        out.append("the platform call is not by name, or a missing name is silent")
    return out


def claim_the_reported_token_stays_ended(files):
    """Section 6, Table C1, F10: the base's report ends the team token
    (OnTokenGameOver: EndGameToken, then inGame false). At the real end the
    token's GameOverTransition prefix reaches GmVoid, which returns while
    inGame is false, so it neither restores nor reuses the reported token.
    inGame is set only by BeginGameToken, whose one caller is the watcher's
    game start, behind finding A's gate."""
    out = []
    t = files["TeamGameNumber.cs"]
    if not _in_order(_code(t, "internal string OnTokenGameOver("), ["EndGameToken();", "inGame = false;"]):
        out.append("the base's report does not end the token's game")
    if not _in_order(_code(t, "private string GmVoid("), ["if (!inGame || overSeen) return null;", "EndGameToken();"]):
        out.append("the real end's void acts on an ended game")
    if not _in_order(_code(t, "internal string OnGmGameOver("), ["return GmVoid("]):
        out.append("the real end's token step is not the void")
    whole = _code(t)
    if whole.count("inGame = true;") != 1 or "inGame = true;" not in _code(t, "private void BeginGameToken("):
        out.append("inGame is re-armed outside the game start")
    if whole.count("BeginGameToken(live);") != 1 or "BeginGameToken(live);" not in _code(t, "internal int OnGameStart("):
        out.append("the token's game begins outside the watcher's start")
    calls = sum(_code(x).count("TeamGameNumber.Live.OnGameStart(") for x in files.values())
    if calls != 1 or not _in_order(_code(files["GameStateWatcher.cs"], "private static void OnMatchStarted("),
                                   ["if (LimitlessFence.RecordOpen) return;", "TeamGameNumber.Live.OnGameStart("]):
        out.append("the token's game start is not behind the continuation gate")
    return out


def claim_the_real_end_holds_the_platform_results(files):
    """Section 6, Table C1 (H7), at the real end: while the seat holds a live
    or terminating record, a GameOver prefix saves vanilla's two streak
    counters and sets the hold. The two PlatformManager prefixes refuse every
    call while it is set. The finalizer, which runs on every exit, puts the
    counters back, clears the hold and returns the exception it was given. The
    fence stages its capability only when all three patches attached (#83)."""
    out = []
    lf = files[LFN]
    whole = _code(lf)
    if '[HarmonyPatch(typeof(GM_ArmsRace), "GameOver")]\n    internal static class LimitlessFence_RealEnd_Patch' not in whole:
        out.append("the hold is not on vanilla's GameOver")
    if not _in_order(_code(lf, "internal static class LimitlessFence_RealEnd_Patch"), [
            "private static void Prefix(GM_ArmsRace __instance, out RealEndSaved __state)",
            "__state = default(RealEndSaved);",
            "if (!LimitlessFence.RecordOpen || __instance == null) return;",
            "__state.LastWinner = __instance.m_lastWinningTeam;",
            "__state.WinCount = __instance.m_winCount;",
            "__state.Held = true;",
            "LimitlessFence.PlatformResultsHeld = true;",
            "private static Exception Finalizer(GM_ArmsRace __instance, RealEndSaved __state, Exception __exception)",
            "if (!__state.Held) return __exception;",
            "__instance.m_lastWinningTeam = __state.LastWinner;",
            "__instance.m_winCount = __state.WinCount;",
            "LimitlessFence.PlatformResultsHeld = false;",
            "if (exception == null) LimitlessFence.RealEndLive = true;"]):
        out.append("the real end's hold is not set, saved and put back")
    for m, cls, live in (("UnlockAchievement", "LimitlessFence_HeldUnlock_Patch", "HeldUnlockLive"),
                         ("ProgressAchievement", "LimitlessFence_HeldProgress_Patch", "HeldProgressLive")):
        hdr = '[HarmonyPatch(typeof(FriendlyFoe.Platform.PlatformManager), "%s")]\n    internal static class %s' % (m, cls)
        if hdr not in whole or not _in_order(_code(lf, "internal static class " + cls), [
                "private static bool Prefix() { return !LimitlessFence.PlatformResultsHeld; }",
                "if (exception == null) LimitlessFence.%s = true;" % live]):
            out.append("PlatformManager.%s is not held at the real end" % m)
    if whole.count("LimitlessFence.PlatformResultsHeld = true;") != 1 or whole.count("PlatformResultsHeld = ") != 2:
        out.append("the hold has another writer")
    if "internal static bool RealEndHoldLive { get { return RealEndLive && HeldUnlockLive && HeldProgressLive; } }" not in whole \
            or "&& PlayerDiedLive && RealEndHoldLive && _hooked" not in whole \
            or not _in_order(_code(lf, "internal static void StageFenceCapability("), [
                "if (!GameStartLive || !RawRoundLive || !PlayerDiedLive)",
                "if (!RealEndHoldLive)\n                {\n                    _stageFailedPermanently = true;",
                "if (!_hooked) return;"]):
        out.append("the capability is staged without the hold")
    return out


CLAIMS = {
    "game_start_prefix": claim_the_game_start_prefix,
    "stamp_before_join": claim_the_gid_is_stamped_before_the_join,
    "handoff_first": claim_the_handoff_count_comes_first,
    "adoption_from_relay": claim_adoption_only_from_the_relay,
    "mint_cas": claim_the_mint_is_a_compare_and_set,
    "room_edges": claim_the_room_edges_note_the_gid,
    "spectator_boundary": claim_the_spectator_boundary,
    "raw_round_refusals": claim_every_raw_round_sibling_refuses_first,
    "record_retires": claim_the_record_retires_at_each_boundary,
    "apply_under_stamp": claim_the_round_applies_under_its_stamp,
    "handler_order": claim_the_handler_runs_in_order,
    "fence_message": claim_the_message_is_reliable_to_all,
    "mirror_cas": claim_the_mirror_is_a_compare_and_set,
    "capability": claim_the_capability_is_staged_out_of_a_room,
    "uncovered_leave": claim_an_uncovered_case_leaves_once,
    "gm_prefix": claim_the_gm_decision_prefix,
    "gm_send": claim_the_gm_round_send,
    "ffa_send": claim_the_ffa_round_send,
    "decision_inputs": claim_the_decision_reads_its_inputs,
    "later_rounds": claim_every_later_round_rereads,
    "opt_in": claim_the_opt_in_writer,
    "termination": claim_termination_is_set,
    "departure_routes": claim_every_departure_route_terminates_first,
    "hold_refusal": claim_the_hold_reads_the_record_first,
    "sender_end": claim_termination_reaches_the_sender,
    "redrive": claim_the_new_master_redrives,
    "no_admission": claim_no_fighter_is_admitted,
    "late_tail": claim_the_late_tail_is_refused,
    "entrant_exit": claim_a_refused_entrant_is_no_departure,
    "resume_rows": claim_every_table_a_row_is_guarded,
    "guard_wiring": claim_the_guard_reads_a_ticket_captured_at_schedule,
    "pick_sends": claim_the_pick_sends_answer_to_their_ticket,
    "pick_period": claim_a_new_master_period_issues_a_fresh_epoch,
    "pick_receiver": claim_a_receiver_applies_one_close_per_phase,
    "late_items": claim_the_late_items_resume_under_their_ticket,
    "late_sends": claim_the_late_sends_answer_to_their_ticket,
    "hold_items": claim_the_hold_acts_only_under_its_cut_ticket,
    "observer_apply": claim_the_observer_apply_reads_its_attempt_and_epoch,
    "observer_flush": claim_the_observer_flush_reads_the_epoch,
    "base_target": claim_the_retirement_puts_the_base_target_back,
    "ffa_target_writers": claim_ffa_config_writers_go_through_one_setter,
    "join_record": claim_the_joiner_reads_the_mirror_once_unconfirmed,
    "snapshot_record": claim_the_snapshot_carries_and_replaces_the_record,
    "observer_seed": claim_a_terminating_seed_never_ends_the_observer,
    "gm_observer_end": claim_the_gm_observer_ends_at_the_live_target,
    "match_start_gate": claim_the_match_start_is_gated_in_a_continuation,
    "ffa_base_report": claim_ffa_reports_at_the_base_and_ends_at_the_real_end,
    "base_results": claim_the_base_runs_vanillas_results_once,
    "real_end_hold": claim_the_real_end_holds_the_platform_results,
    "token_real_end": claim_the_reported_token_stays_ended,
}

GATE = "                if (SpectatorPatchSupport.Suppress) return;\n"
START = "                LimitlessFence.NoteOwnGameStart();\n"
STAMP = "                LimitlessFence.StampInitialGid(roomProps);\n"
JOIN = "                bool accepted = PhotonNetwork.JoinOrCreateRoom(capturedRoom, roomOptions, lobby);\n"
SWITCH = "            try { LimitlessFence.NoteMasterSwitched(newMasterClient); } catch { }\n"
MAPSCALE = "            try { FfaMapScale.OnMasterClientSwitched(); } catch { }\n"
COUNT = "            _handoff++;\n"
MINT_CALL = '            if (newMaster != null && newMaster.IsLocal) TryMint("handoff");\n'
MINT_LOG = '                Plugin.Log.LogInfo("[LIMIT] mint (" + why + "): sent=" + sent + ", expecting " + GidPrefix(current));\n'
NOT_SPEC = "                if (RoomActors.LocalIsSpectator) return;\n"
SHOULD = ("                if (!LimitlessFenceRules.ShouldMint(PhotonNetwork.IsMasterClient, _startedInRoom, current, _ledger))"
          " return;\n")
CAS = ("                    new ExitGames.Client.Photon.Hashtable { { GidKey, NewGid() } },\n"
       "                    new ExitGames.Client.Photon.Hashtable { { GidKey, current } });\n")
EXIT = "            _epoch++;\n            _ledger.ExitRoom();\n"
GM_OVER = '                try { LimitlessFence.NoteSpectatorGameOver("gm"); } catch { }\n'
FFA_OVER = '                try { LimitlessFence.NoteSpectatorGameOver("ffa"); } catch { }\n'
CALL_IN = "            try { LimitlessFence.NoteSpectatorCallIn(); } catch { }\n"
SCHEDULE = "            _lastObservedBoundaryMapId = mapId;\n            ScheduleBoundary(mapId);\n"
REF_GM = 'return !LimitlessFence.RawRoundRefused("gm");'
REF_FFA = '            if (LimitlessFence.RawRoundRefused("ffa prefix")) return false;\n'
ENGINE = "            if (!FfaMode.EngineActive()) return true;\n"
REF_ROUND = 'if (LimitlessFence.RawRoundRefused("ffa round")) return;'
REF_SPEC = '            if (LimitlessFence.RawRoundRefused("spectator prefix")) return false;\n'
REF_OBS = 'if (LimitlessFence.RawRoundRefused("ffa observer")) return;'
REF_POINT = '            if (LimitlessFence.RawRoundRefused("point boundary")) return;\n'
REF_SWEEP = 'if (LimitlessFence.RawRoundRefused("projectile sweep")) return;'
PRED = "if (!LimitlessFenceRules.RefuseRawRound(_hasRecord, _state, _fenceCall)) return false;"
INSTALL = "            InstallRecord(rec, outcome == LimitlessFenceRules.HandlerOutcome.CreateRecord);\n"
TARGET = "            SetRecordTarget(gm, ffa, rec.TargetRounds);\n"
MIRROR = "            if (PhotonNetwork.IsMasterClient) WriteRecordMirror(rec);\n"
APPLY = "            ApplyFenceRound(gm, args, stamp);\n"
FLAG = "            _fenceCall = true;\n"
HOOK = "            try { LimitlessFence.HookFenceEvents(); } catch { }\n"
STAGE = '            try { LimitlessFence.StageFenceCapability("tick"); } catch { }\n'
OPTS = "            var opts = new Photon.Realtime.RaiseEventOptions"
ME = "                var me = PhotonNetwork.LocalPlayer;\n"
ST = "                var st = PhotonNetwork.NetworkClientState;\n"
LATCH = "            _uncoveredLeaving = true;\n"
FFA_CAPTURE = "                LimitlessFence.NoteFfaPointScheduled();   // Ask 16(a) lane 2 (v4 4.4): MaySend at the send compares with this\n"
PUBLISH = "                try { FfaMapScale.MasterPublishCount(FfaLateEntry.PointK + 1); } catch { }\n"


def _drop(fname, line):
    return [(fname, line, "")]


MUTANTS = [
    ("game_start_prefix", "the game-start prefix runs at Normal priority",
     [(LF, "    internal static class LimitlessFence_GameStart_Patch\n    {\n        [HarmonyPriority(Priority.First)]\n",
       "    internal static class LimitlessFence_GameStart_Patch\n    {\n        [HarmonyPriority(Priority.Normal)]\n")]),
    ("game_start_prefix", "the game-start prefix has no spectator gate", _drop(LF, GATE)),
    ("game_start_prefix", "the game-start prefix gates after the start", [(LF, GATE + START, START + GATE)]),
    ("stamp_before_join", "the room is created without a gid", _drop("Plugin.cs", STAMP)),
    ("stamp_before_join", "the gid is stamped after the join",
     [("Plugin.cs", STAMP, ""), ("Plugin.cs", JOIN, JOIN + STAMP)]),
    ("handoff_first", "the switch notes the handoff after the map-scale ticket",
     [("Plugin.cs", SWITCH, ""), ("Plugin.cs", MAPSCALE, MAPSCALE + SWITCH)]),
    ("handoff_first", "the switch raises no count", _drop(LF, COUNT)),
    ("handoff_first", "the count rises after the mint", [(LF, COUNT, ""), (LF, MINT_CALL, MINT_CALL + COUNT)]),
    ("adoption_from_relay", "the mint adopts its own value",
     [(LF, MINT_LOG, "                _ledger.AdoptRelayed(current);\n" + MINT_LOG)]),
    ("adoption_from_relay", "the start adopts a value it made",
     [(LF, "_ledger.AtOwnGameStart(RoomGid())", "_ledger.AtOwnGameStart(NewGid())")]),
    ("adoption_from_relay", "the join adopts nothing",
     [(LF, 'TryAdopt(RoomGid(), "join");', '// join')]),
    ("mint_cas", "the mint expects nothing",
     [(LF, CAS, "                    new ExitGames.Client.Photon.Hashtable { { GidKey, NewGid() } });\n")]),
    ("mint_cas", "the mint skips the rule", _drop(LF, SHOULD)),
    ("mint_cas", "a spectator mints", _drop(LF, NOT_SPEC)),
    ("room_edges", "the join adopts no gid", _drop("Plugin.cs", "            try { LimitlessFence.NoteJoinedRoom(); } catch { }\n")),
    ("room_edges", "room exit keeps the gid", _drop("Plugin.cs", "            try { LimitlessFence.NoteLeftRoom(); } catch { }\n")),
    ("room_edges", "the property change ignores the gid",
     _drop("Plugin.cs", "            try { LimitlessFence.NoteRoomProps(propertiesThatChanged); } catch { }\n")),
    ("room_edges", "room exit raises no epoch", [(LF, EXIT, "            _ledger.ExitRoom();\n")]),
    ("spectator_boundary", "the GM observer's game over keeps the gid", _drop("SpectatorSync.cs", GM_OVER)),
    ("spectator_boundary", "the FFA observer's game over keeps the gid", _drop("FfaMode.cs", FFA_OVER)),
    ("spectator_boundary", "the call-in opens no next game", _drop("SpectatorSync.cs", CALL_IN)),
    ("spectator_boundary", "the call-in opens the next game after the boundary work",
     [("SpectatorSync.cs", CALL_IN, ""), ("SpectatorSync.cs", SCHEDULE, SCHEDULE + CALL_IN)]),
    ("raw_round_refusals", "the fence's prefix lets raw calls through", [(LF, REF_GM, "return true;")]),
    ("raw_round_refusals", "FFA's prefix has no refusal", _drop("FfaMode.cs", REF_FFA)),
    ("raw_round_refusals", "FFA's prefix refuses after its engine return", [("FfaMode.cs", REF_FFA + ENGINE, ENGINE + REF_FFA)]),
    ("raw_round_refusals", "HandleNextRound has no refusal", [("FfaMode.cs", REF_ROUND, "")]),
    ("raw_round_refusals", "the spectator prefix has no refusal", _drop("SpectatorPatches.cs", REF_SPEC)),
    ("raw_round_refusals", "SpectatorObserveRound has no refusal", [("FfaMode.cs", REF_OBS, "")]),
    ("raw_round_refusals", "the point boundary has no refusal", _drop("PoisonSync.cs", REF_POINT)),
    ("raw_round_refusals", "the point boundary only logs its refusal",
     [("PoisonSync.cs", REF_POINT.strip(), 'LimitlessFence.RawRoundRefused("point boundary");')]),
    ("raw_round_refusals", "the point boundary postfix calls the boundary bare",
     [("PoisonSync.cs", "HookGuard.Run(() => PoisonSync.NotePointBoundary(__instance));",
       "PoisonSync.NotePointBoundary(__instance);")]),
    ("raw_round_refusals", "the projectile sweep has no refusal", [("VanillaFixes.cs", REF_SWEEP, "")]),
    ("raw_round_refusals", "the refusal ignores the fence's flag", [(LF, PRED, PRED.replace("_fenceCall)", "false)"))]),
    ("record_retires", "the game start keeps the record", _drop(LF, '            RetireRecord("game start");\n')),
    ("record_retires", "the join keeps the record", _drop(LF, '            RetireRecord("join");\n')),
    ("record_retires", "room exit keeps the record", _drop(LF, '            RetireRecord("room exit");\n')),
    ("record_retires", "the spectator's boundary keeps the record", _drop(LF, '            RetireRecord("spectator boundary");\n')),
    ("record_retires", "a new gid keeps the record", _drop(LF, '            RetireRecord("new gid");\n')),
    ("apply_under_stamp", "the round is applied outside the stamp's frame",
     [(LF, APPLY_CALL, "try { gm.RPCA_NextRound(a[0], a[1], a[2], a[3], a[4], a[5]); }")]),
    ("apply_under_stamp", "the round runs under stamp 0", [(LF, "RunStamped(view, stamp,", "RunStamped(view, 0,")]),
    ("apply_under_stamp", "the frame names no view",
     [("PoisonSync.cs", "View = viewId, Ts = ts }, call);", "View = 0, Ts = ts }, call);")]),
    ("apply_under_stamp", "the fence's flag is never set", _drop(LF, FLAG)),
    ("apply_under_stamp", "the fence's flag stays set", [(LF, "finally { _fenceCall = false; }", "finally { }")]),
    ("apply_under_stamp", "another path calls the round directly",
     [("FfaMode.cs", REF_OBS, REF_OBS + " if (false) GM_ArmsRace.instance.RPCA_NextRound(0, 0, 0, 0, 0, 0);")]),
    ("handler_order", "the sender test is always true",
     [(LF, "SenderIsMasterNow = master != null && master.ActorNumber == sender,", "SenderIsMasterNow = true,")]),
    ("handler_order", "the round applies before the record",
     [(LF, INSTALL + TARGET + MIRROR + APPLY, APPLY + INSTALL + TARGET + MIRROR)]),
    ("handler_order", "the mirror is written before the record", [(LF, INSTALL + TARGET + MIRROR, MIRROR + INSTALL + TARGET)]),
    ("handler_order", "an uncovered refusal stays in the room", _drop(LF, "                    TakeUncoveredPath();\n")),
    ("handler_order", "a master's message that does not decode stays in the room",
     [(LF, "if (fromMaster) TakeUncoveredPath();", "if (fromMaster) { }")]),
    ("fence_message", "the message skips its sender",
     [(LF, "Receivers = Photon.Realtime.ReceiverGroup.All", "Receivers = Photon.Realtime.ReceiverGroup.Others")]),
    ("fence_message", "the message may be lost",
     [(LF, "ExitGames.Client.Photon.SendOptions.SendReliable);", "ExitGames.Client.Photon.SendOptions.SendUnreliable);")]),
    ("fence_message", "the event code is another feature's",
     [(LF, "internal const byte EvtFence = 59;", "internal const byte EvtFence = 47;")]),
    ("fence_message", "the handler takes every event code",
     [(LF, "if (ev == null || ev.Code != EvtFence) return;", "if (ev == null) return;")]),
    ("mirror_cas", "the mirror does not expect the master",
     _drop(LF, "                        { Photon.Realtime.GamePropertyKey.MasterClientId, me.ActorNumber },\n")),
    ("mirror_cas", "the mirror does not expect the gid", _drop(LF, "                        { GidKey, rec.Gid },\n")),
    ("capability", "the capability is written in a room", [(LF, "                if (PhotonNetwork.InRoom)\n", "                if (false)\n")]),
    ("capability", "the capability is staged without its patches", [(LF, "if (!GameStartLive || !RawRoundLive || !PlayerDiedLive)", "if (false)")]),
    ("capability", "a failed attach counts live",
     [(LF, "if (exception == null) LimitlessFence.RawRoundLive = true;", "LimitlessFence.RawRoundLive = true;")]),
    ("capability", "the tick stages before it hooks", [("Plugin.cs", HOOK + STAGE, STAGE + HOOK)]),
    ("capability", "a compat disable keeps the capability",
     _drop("Plugin.cs", "                        try { LimitlessFence.RevokeFenceCapability(); } catch { }\n")),
    ("uncovered_leave", "the terminal path runs twice",
     _drop(LF, "            if (_uncoveredLeaving) return;   // one leave; the room exit clears this\n")),
    ("uncovered_leave", "a spectator restarts the network",
     [(LF, 'if (RoomActors.LocalIsSpectator) SpectatorSync.LeaveToMenu("limitless: an uncovered fence message");', "if (false) { }")]),
    ("uncovered_leave", "room exit keeps the leave latched",
     [(LF, '            RetireRecord("room exit");\n            _uncoveredLeaving = false;\n', '            RetireRecord("room exit");\n')]),
    ("gm_prefix", "the decision prefix runs at First",
     [(LF, "    internal static class LimitlessFence_PlayerDied_Patch\n    {\n        [HarmonyPriority(Priority.Last)]\n",
       "    internal static class LimitlessFence_PlayerDied_Patch\n    {\n        [HarmonyPriority(Priority.First)]\n")]),
    ("gm_prefix", "the prefix ignores another prefix's skip", _drop(LF, "            if (!__runOriginal) return false;\n")),
    ("gm_prefix", "vanilla's send also runs when the fence sent",
     [(LF, "if (sent == LimitlessFence.FenceSend.Vanilla) return true;", "return true;")]),
    ("gm_prefix", "a fault skips vanilla's body",
     [(LF, 'faulted: " + ex.Message);\n                return true;\n', 'faulted: " + ex.Message);\n                return false;\n')]),
    ("gm_prefix", "the take-over skips the slow-down",
     _drop(LF, "            try { if (TimeHandler.instance != null) TimeHandler.instance.DoSlowDown(); } catch { }\n")),
    ("gm_prefix", "a failed attach counts the sender live",
     [(LF, "if (exception == null) LimitlessFence.PlayerDiedLive = true;", "LimitlessFence.PlayerDiedLive = true;")]),
    ("gm_send", "the GM sender runs off the master",
     [(LF, "PhotonNetwork.OfflineMode || !PhotonNetwork.IsMasterClient) return FenceSend.Vanilla;",
       "PhotonNetwork.OfflineMode) return FenceSend.Vanilla;")]),
    ("gm_send", "a round past the base goes out as vanilla's", [(LF, GM_SEND[4], "")]),
    ("gm_send", "the GM decision skips the end test", [(LF, GM_SEND[5], "if (false)")]),
    ("gm_send", "the GM arguments swap the teams",
     [(LF, "{ pm.GetOtherTeam(winner), winner,", "{ winner, pm.GetOtherTeam(winner),")]),
    ("ffa_send", "FFA schedules without the capture", _drop("FfaMode.cs", FFA_CAPTURE)),
    ("ffa_send", "FFA's later rounds compare at the send",
     [(LF, "return SendContinuation(args, sides, _ffaEpoch, _ffaHandoff);", "return SendContinuation(args, sides, _epoch, _handoff);")]),
    ("ffa_send", "a withheld round keeps the latch",
     _drop("FfaMode.cs", "                if (fence == LimitlessFence.FenceSend.Withheld) pointLatched = false;\n")),
    ("ffa_send", "the fence's message and vanilla's both go out",
     _drop("FfaMode.cs", "                if (fence != LimitlessFence.FenceSend.Vanilla) return;\n")),
    ("ffa_send", "the fence sends before the map-scale count",
     [("FfaMode.cs", PUBLISH + "                // Ask 16(a) lane 2 (v4 4.4, 4.7)", "                // Ask 16(a) lane 2 (v4 4.4, 4.7)"),
      ("FfaMode.cs", "if (fence != LimitlessFence.FenceSend.Vanilla) return;\n", "if (fence != LimitlessFence.FenceSend.Vanilla) return;\n" + PUBLISH)]),
    ("ffa_send", "a fault withholds the round",
     [("FfaMode.cs", "fence = LimitlessFence.FenceSend.Vanilla;", "fence = LimitlessFence.FenceSend.Withheld;")]),
    ("ffa_send", "the FFA decision skips the end test",
     [(LF, "if (!LimitlessFenceRules.RoundEndsGame(FfaMode.PointsFor(winnerTeam), wRounds, FfaMode.PointsToWinRound, FfaMode.RoundsToWin))",
       "if (false)")]),
    ("decision_inputs", "the decision skips MaySend", [(LF, DECIDE[0], "MaySend = true || " + DECIDE[0][len("MaySend = "):])]),
    ("decision_inputs", "the decision ignores the cut", [(LF, DECIDE[7], "HoldHasPendingCut = false,")]),
    ("decision_inputs", "the decision ignores a held seat", [(LF, DECIDE[6], "HoldHasHeldSeat = false,")]),
    ("decision_inputs", "the decision ignores the series", [(LF, DECIDE[8], "SeriesFollows = false,")]),
    ("decision_inputs", "the decision reads only its own capability",
     [(LF, DECIDE[4], "ActorCapabilities = new[] { OwnCapability() },")]),
    ("decision_inputs", "the decision message carries no roster",
     [(LF, "EncodeRecord(rec, roster, args, PhotonNetwork.ServerTimestamp)", "EncodeRecord(rec, null, args, PhotonNetwork.ServerTimestamp)")]),
    ("decision_inputs", "the decision message is stamped 0",
     [(LF, "EncodeRecord(rec, roster, args, PhotonNetwork.ServerTimestamp)", "EncodeRecord(rec, roster, args, 0)")]),
    ("decision_inputs", "a declined decision still sends",
     [(LF, 'the base (" + why + ")");\n                return FenceSend.Vanilla;\n', 'the base (" + why + ")");\n')]),
    ("later_rounds", "a later round skips MaySend", [(LF, "            if (!may)\n", "            if (false)\n")]),
    ("later_rounds", "the re-read is skipped", [(LF, CONT[6], "var rec = _record;")]),
    ("later_rounds", "MustEnd compares the handoff count with itself", [(LF, CONT[5], "_handoff, _handoff);")]),
    ("later_rounds", "MaySend compares the epoch with itself",
     [(LF, CONT[1], CONT[1].replace("_epoch, epochCaptured,", "_epoch, _epoch,"))]),
    ("later_rounds", "the handoff count is retaken at every update",
     [(LF, "if (create) _handoffAtRecord = _handoff;", "_handoffAtRecord = _handoff;")]),
    ("later_rounds", "a later round is stamped 0",
     [(LF, "EncodeRecord(rec, null, args, PhotonNetwork.ServerTimestamp)", "EncodeRecord(rec, null, args, 0)")]),
    ("opt_in", "the opt-in names any gid",
     [(LF, "string want = _optInWanted && _ledger.IsLiveGid(gid) ? gid : null;", "string want = _optInWanted ? gid : null;")]),
    ("opt_in", "the radio survives the game start",
     _drop(LF, "            _optInWanted = false;   // D6: the radio resets to off at every game start\n")),
    ("opt_in", "a gid change keeps the old opt-in", _drop(LF, '            WriteOptIn("new gid");   // the opt-in follows a gid change\n')),
    ("opt_in", "the join keeps a carried-in value", _drop(LF, '            WriteOptIn("join");   // clears a value the join carried in\n')),
    ("opt_in", "the opt-in is written on every call",
     _drop(LF, "            if (string.Equals(have as string, want, StringComparison.Ordinal)) return;\n")),
    ("opt_in", "the radio does not write", _drop(LF, '            WriteOptIn("radio");\n')),
    ("capability", "the capability is staged without the sender's patch",
     [(LF, " || !RawRoundLive || !PlayerDiedLive)", " || !RawRoundLive)")]),
    ("termination", "a spectator's departure terminates",
     [(LF, "if (p == null || !RecordOpen || RoomActors.IsSpectatorReplicated(p)) return;", "if (p == null || !RecordOpen) return;")]),
    ("termination", "a departure leaves the flag clear", _drop(LF, "            _departed = true;\n")),
    ("termination", "termination keeps the record live",
     [(LF, "_state = LimitlessFenceRules.NextState(_state, true);", "_state = LimitlessFenceRules.NextState(_state, false);")]),
    ("termination", "a master change keeps the record live",
     _drop(LF, '            Terminate("master change");   // 4.6: a master change terminates a live record\n')),
    ("termination", "the departure flag outlives its record", _drop(LF, "            _departed = false;\n")),
    ("departure_routes", "the Plugin hook does not terminate",
     _drop("Plugin.cs", "            try { LimitlessFence.TerminateOnDeparture(p); } catch { }\n")),
    ("departure_routes", "the hold prefix terminates only when no prefix skipped",
     [("TeamHoldPatches.cs", "            " + ROUTE_FIRST + "\n            if (!__runOriginal) return false;\n",
       "            if (!__runOriginal) return false;\n            " + ROUTE_FIRST + "\n")]),
    ("departure_routes", "FFA's route terminates only in a live FFA",
     [("FfaMode.cs", "            " + ROUTE_FIRST + "\n            if (!FfaMode.EngineActive()) return true;\n",
       "            if (!FfaMode.EngineActive()) return true;\n            " + ROUTE_FIRST + "\n")]),
    ("hold_refusal", "the gate's inputs omit the record",
     _drop("TeamHoldWriter.cs", "                FenceOpen = LimitlessFence.RecordOpen,   // Ask 16(a) lane 2 (v4 4.6)\n")),
    ("hold_refusal", "the hold rule holds inside a continuation",
     _drop("TeamHoldRules.cs", "                if (i.FenceOpen) return false;   // Ask 16(a) lane 2 (v4 4.6): no hold inside a continuation\n")),
    ("hold_refusal", "Classify reaches the memo during a record",
     [("TeamHoldWriter.cs", "written.\n                if (LimitlessFence.RecordOpen) return false;\n", "written.\n")]),
    ("hold_refusal", "the leave callback reads the held set first",
     [("TeamHoldWriter.cs", "the memo.\n                if (LimitlessFence.RecordOpen) return false;\n", "the memo.\n")]),
    ("hold_refusal", "the cascade prefix classifies during a record",
     _drop("TeamHoldPatches.cs", "                if (LimitlessFence.RecordOpen) return true;\n")),
    ("sender_end", "the GM master sends after a departure",
     _drop(LF, "            if (RecordOpen && _departed) return WithheldAfterDeparture();\n")),
    ("sender_end", "the departure's answer is vanilla's",
     [(LF, 'the room tears down");\n            return FenceSend.Withheld;', 'the room tears down");\n            return FenceSend.Vanilla;')]),
    ("sender_end", "a terminating record goes out without its end",
     [(LF, "bool mustEnd = _state == LimitlessFenceRules.FencePhase.PhaseTerminating\n", "bool mustEnd = false\n")]),
    ("redrive", "no re-drive at a handoff",
     _drop("Plugin.cs", "            try { LimitlessFence.RedriveAfterHandoff(newMasterClient); } catch { }\n")),
    ("redrive", "the re-drive runs before the tickets clear",
     [("Plugin.cs", "            try { LimitlessFence.RedriveAfterHandoff(newMasterClient); } catch { }\n", ""),
      ("Plugin.cs", "            try { LimitlessFence.NoteMasterSwitched(newMasterClient); } catch { }\n",
       "            try { LimitlessFence.NoteMasterSwitched(newMasterClient); } catch { }\n"
       "            try { LimitlessFence.RedriveAfterHandoff(newMasterClient); } catch { }\n")]),
    ("redrive", "the re-drive ignores the record",
     [(LF, "!newMaster.IsLocal || !RecordOpen || !FfaMode.EngineActive()) return;", "!newMaster.IsLocal || !FfaMode.EngineActive()) return;")]),
    ("redrive", "a seat that is not the new master re-drives",
     [(LF, "if (newMaster == null || !newMaster.IsLocal || !RecordOpen", "if (newMaster == null || !RecordOpen")]),
    ("redrive", "the re-drive runs with two fighters alive",
     [("FfaMode.cs", "                if (AlivePlayers().Count > 1) return;\n", "                if (AlivePlayers().Count > 2) return;\n")]),
    ("redrive", "the re-drive sends during a transition",
     [("FfaMode.cs", "|| pointLatched || isTransitioning) return;\n                LimitlessFence.NoteFfaPointScheduled();   // the re-drive",
       "|| pointLatched) return;\n                LimitlessFence.NoteFfaPointScheduled();   // the re-drive")]),
    ("redrive", "the re-drive sends without the capture",
     _drop("FfaMode.cs", "                LimitlessFence.NoteFfaPointScheduled();   // the re-drive's capture, as HandlePlayerDied's\n")),
    ("redrive", "the re-drive leaves the latch open",
     [("FfaMode.cs", '                pointLatched = true;\n                Plugin.Log.LogInfo("[LIMIT] the new master re-drives',
       '                Plugin.Log.LogInfo("[LIMIT] the new master re-drives')]),
    ("no_admission", "the master answers a late request as before",
     _drop("FfaLateEntry.cs", '            if (LimitlessFence.RecordOpen) { Refused("limitless", sender); SendSnapshot(sender, seq, true); return; }\n')),
    ("no_admission", "the master answers a late request with an open snapshot",
     [("FfaLateEntry.cs", 'Refused("limitless", sender); SendSnapshot(sender, seq, true); return; }',
       'Refused("limitless", sender); SendSnapshot(sender, seq, false); return; }')]),
    ("no_admission", "the boundary sends open snapshots during a record",
     [("FfaLateEntry.cs", "                if (LimitlessFence.RecordOpen)   // Ask 16(a) lane 2 (v4 4.6): closed during a record\n",
       "                if (false)   // Ask 16(a) lane 2 (v4 4.6): closed during a record\n")]),
    ("no_admission", "the boundary proposes a new epoch during a record",
     [("FfaLateEntry.cs", " && MasterMaySend() && !LimitlessFence.RecordOpen;", " && MasterMaySend();")]),
    ("no_admission", "the entrant arms during a record",
     _drop("FfaLateEntry.cs", "            if (LimitlessFence.RecordOpen) { LateGiveUp(); yield break; }   // 4.6: no arming\n")),
    ("no_admission", "the entrant requests during a record",
     _drop("FfaLateEntry.cs", "            if (LimitlessFence.RecordOpen) { LateGiveUp(); return; }   // 4.6: no request\n")),
    ("no_admission", "the entrant sends its request during a record",
     _drop("FfaLateEntry.cs", "            if (LimitlessFence.RecordOpen) { LateGiveUp(); yield break; }   // 4.6: no request sent\n")),
    ("no_admission", "a snapshot admits during a record",
     _drop("FfaLateEntry.cs", "            if (LimitlessFence.RecordOpen) { LateGiveUp(); return; }   // 4.6: no admission from a snapshot\n")),
    ("no_admission", "the admission check admits during a record",
     _drop("FfaLateEntry.cs", "            if (LimitlessFence.RecordOpen) { LateGiveUp(); return; }   // 4.6: no admission\n")),
    ("no_admission", "the entrant defers instead of leaving",
     [("FfaLateEntry.cs", "            if (LimitlessFence.RecordOpen) { LateGiveUp(); return; }   // 4.6: no request\n",
       "            if (LimitlessFence.RecordOpen) return;   // 4.6: no request\n")]),
    ("late_tail", "the entered POST runs during a record",
     _drop("FfaLateEntry.cs", "            if (LimitlessFence.RecordOpen) { _pendingSelfKeptGame = 0; LateGiveUp(); return; }\n")),
    ("late_tail", "the entered POST defers instead of leaving",
     [("FfaLateEntry.cs", "if (LimitlessFence.RecordOpen) { _pendingSelfKeptGame = 0; LateGiveUp(); return; }",
       "if (LimitlessFence.RecordOpen) return;")]),
    ("late_tail", "a readmit replay starts during a record",
     [("FfaMode.cs", " || Plugin.Instance == null || LimitlessFence.RecordOpen)", " || Plugin.Instance == null)")]),
    ("late_tail", "a readmit replay's steps run on during a record",
     [("FfaMode.cs", "() => ReadmitReplayCurrent(replay) && !LimitlessFence.RecordOpen,", "() => ReadmitReplayCurrent(replay),")]),
    ("late_tail", "a readmission arms during a record",
     _drop("FfaReadmit.cs", '                    if (LimitlessFence.RecordOpen) { Refusal("limitless", true); break; }\n')),
    ("late_tail", "a refused readmission stays",
     [("FfaReadmit.cs", 'Refusal("limitless", true); break; }', 'Refusal("limitless", false); break; }')]),
    ("entrant_exit", "a refused entrant's exit terminates",
     _drop(LF, "            if (FfaLateEntry.IsQuarantinedActor(p.ActorNumber)) return;\n")),
    ("entrant_exit", "the quarantine test follows the departure flag",
     [(LF, "            if (FfaLateEntry.IsQuarantinedActor(p.ActorNumber)) return;\n", ""),
      (LF, '            _departed = true;\n            Terminate("fighter departure");\n',
       '            _departed = true;\n            if (FfaLateEntry.IsQuarantinedActor(p.ActorNumber)) return;\n'
       '            Terminate("fighter departure");\n')]),
    ("resume_rows", "FFA's point is unguarded",
     [("FfaMode.cs", 'LimitlessFence.ResumableItem(ResolvePointEndOfFrame(gm), "ffa point")', "ResolvePointEndOfFrame(gm)")]),
    ("resume_rows", "the sitting's end is unguarded",
     [("FfaMode.cs", 'LimitlessFence.CleanupItem(EndSittingBelowMinimum(), "ffa sitting end")', "EndSittingBelowMinimum()")]),
    ("resume_rows", "the sitting's end reads the record",
     [("FfaMode.cs", "LimitlessFence.CleanupItem(EndSittingBelowMinimum(),", "LimitlessFence.ResumableItem(EndSittingBelowMinimum(),")]),
    ("resume_rows", "FFA's transition is unguarded",
     [("FfaMode.cs", 'LimitlessFence.ResumableItem(FfaTransition(gm, winnerTeam, roundOver), "ffa transition")',
       "FfaTransition(gm, winnerTeam, roundOver)")]),
    ("resume_rows", "FFA's pick UI is unguarded",
     [("FfaMode.cs", 'LimitlessFence.ResumableItem(FfaLocalPickUI(gm, localPlayer, game, cycle, phaseNonce), "ffa pick ui")',
       "FfaLocalPickUI(gm, localPlayer, game, cycle, phaseNonce)")]),
    ("resume_rows", "FFA's leave route is unguarded",
     [("FfaMode.cs", 'LimitlessFence.ResumableItem(FfaMode.CheckRoundAfterLeave(), "ffa leave")', "FfaMode.CheckRoundAfterLeave()")]),
    ("resume_rows", "FFA's start is unguarded",
     [("FfaMode.cs", 'LimitlessFence.ResumableItem(FfaMode.FfaDoStartGame(__instance), "ffa start")', "FfaMode.FfaDoStartGame(__instance)")]),
    ("resume_rows", "2v2's point transition is unguarded",
     [("TeamHoldFence.cs", 'LimitlessFence.ResumableItem(HoldFence.Run(__instance, TeamHoldRules.PointSteps, __0, -1), "2v2 point transition")',
       "HoldFence.Run(__instance, TeamHoldRules.PointSteps, __0, -1)")]),
    ("resume_rows", "2v2's round transition is unguarded",
     [("TeamHoldFence.cs", 'LimitlessFence.ResumableItem(HoldFence.Run(__instance, TeamHoldRules.RoundSteps, __0, __1), "2v2 round transition")',
       "HoldFence.Run(__instance, TeamHoldRules.RoundSteps, __0, __1)")]),
    ("resume_rows", "the Phoenix revive is unguarded",
     [("VanillaFixes.cs", 'LimitlessFence.ResumableItem(SafeRespawn(__instance, playerIDToRevive), "phoenix revive")',
       "SafeRespawn(__instance, playerIDToRevive)")]),
    ("resume_rows", "the pick wait is unguarded",
     [("TeamHoldPick.cs", 'LimitlessFence.ResumableItem(TeamHoldPick.WaitRecord(__result, picketIDToSet), "pick wait")',
       "TeamHoldPick.WaitRecord(__result, picketIDToSet)")]),
    ("resume_rows", "the hold's replay is unguarded",
     [("TeamHoldReturn.cs", "host.StartCoroutine(LimitlessFence.ResumableItem(ReplayRun(", "host.StartCoroutine(ReplayRun("),
      ("TeamHoldReturn.cs", '}), "hold replay"));', "}));")]),
    ("resume_rows", "the lag-out death is unguarded",
     [("FfaLateEntry.cs", 'LimitlessFence.ResumableItem(OwnDeathAfterCallIn(), "lag-out death")', "OwnDeathAfterCallIn()")]),
    ("resume_rows", "the late arming is unguarded",
     [("FfaLateEntry.cs", 'LimitlessFence.ResumableItem(AdmittedLateRun(a), "late arming")', "AdmittedLateRun(a)")]),
    ("resume_rows", "the gated spawn is unguarded",
     [("Plugin.cs", 'LimitlessFence.ResumableItem(FfaAssembly.GatedSpawn(Auto2v2SpawnCoroutine), "spawn")',
       "FfaAssembly.GatedSpawn(Auto2v2SpawnCoroutine)")]),
    ("resume_rows", "the spawn is unguarded",
     [("Plugin.cs", 'LimitlessFence.ResumableItem(Auto2v2SpawnCoroutine(), "spawn")', "Auto2v2SpawnCoroutine()")]),
    ("guard_wiring", "the guard tests after the step",
     [("LimitlessFenceRules.cs", "                    if (!item.MoveNext()) yield break;\n", ""),
      ("LimitlessFenceRules.cs", "                    if (!mayContinue())\n",
       "                    if (!item.MoveNext()) yield break;\n                    if (!mayContinue())\n")]),
    ("guard_wiring", "a ticket captures no gid",
     [(LF, "Gid = RecordOpen ? _record.Gid : null, Handoff = _handoff };", "Gid = null, Handoff = _handoff };")]),
    ("guard_wiring", "a ticket ignores the record's end",
     [(LF, " || _state == LimitlessFenceRules.FencePhase.PhaseEnded);", ");")]),
    ("guard_wiring", "an item captures again at each step",
     [(LF, "() => TicketResumes(t)", "() => TicketResumes(CaptureTicket())")]),
    ("guard_wiring", "cleanup reads the record",
     [(LF, "() => TicketCleans(t)", "() => TicketResumes(t)")]),
    ("pick_sends", "the pick phase captures no ticket at its entry",
     [("FfaMode.cs", "            var sendTicket = LimitlessFence.CaptureTicket();\n", "")]),
    ("pick_sends", "the manifest wait's reopen keeps the old ticket",
     [("FfaMode.cs", 'sendTicket = PickTicket("manifest reopen");', "")]),
    ("pick_sends", "the manifest wait takes no re-take",
     [("FfaMode.cs", 'if (RetakeMasterPeriod(sendTicket)) sendTicket = PickTicket("manifest period");', "")]),
    ("pick_sends", "the republish sends without TicketSends",
     [("FfaMode.cs", "phaseStart > 2f\n                    && LimitlessFence.TicketSends(sendTicket, FfaLateEntry.MasterMaySend()))\n",
       "phaseStart > 2f)\n")]),
    ("pick_sends", "the pick wait's promotion is keyed on the role",
     [("FfaMode.cs", "if (wasMaster && RetakeMasterPeriod(sendTicket)) wasMaster = false;", "")]),
    ("pick_sends", "the promotion keeps its old ticket",
     [("FfaMode.cs", 'sendTicket = PickTicket("promotion");', "")]),
    ("pick_sends", "the pick wait's reopen keeps the old ticket",
     [("FfaMode.cs", 'sendTicket = PickTicket("pick reopen");', "")]),
    ("pick_sends", "the close sends without TicketSends",
     [("FfaMode.cs", "maySend = LimitlessFence.TicketSends(sendTicket, maySend);", "")]),
    ("pick_period", "the re-take keeps the held epoch",
     [("FfaMode.cs", "return false;\n            phaseEpoch = FfaNumberingRules.HeldEpoch(phaseEpoch, null);\n", "return false;\n")]),
    ("pick_period", "a ticket captures no handoff count",
     [(LF, "Handoff = _handoff };", "Handoff = 0 };")]),
    ("pick_period", "TicketSends ignores the handoff count",
     [(LF, "_epoch, t.Epoch, _handoff, t.Handoff);", "_epoch, t.Epoch, t.Handoff, t.Handoff);")]),
    ("pick_period", "the period misses a record opened after the capture",
     [(LF, "return t.Gid ?? (RecordOpen ? _record.Gid : null);", "return t.Gid;")]),
    ("pick_period", "a ticket with no gid sends without the role",
     [(LF, "if (gid == null) return masterNow;", "if (gid == null) return true;")]),
    ("pick_period", "the period is keyed on the role",
     [("LimitlessFenceRules.cs", "return masterNow && fenceApplies && handoffNow != handoffCaptured;", "return false;")]),
    ("pick_receiver", "a receiver stays in its result loop after an answer",
     [("FfaMode.cs", 'older-build form)");\n                        break;\n', 'older-build form)");\n')]),
    ("pick_receiver", "the phase does not count its cycle",
     [("FfaMode.cs", "            cycleNumber++;\n            int cycle = cycleNumber;\n", "            int cycle = cycleNumber;\n")]),
    ("late_items", "the call-in hold captures no ticket",
     [("FfaLateEntry.cs", "public LimitlessFence.ResumeTicket Ticket = LimitlessFence.CaptureTicket();",
       "public LimitlessFence.ResumeTicket Ticket;")]),
    ("late_items", "the call-in hold is replayed unguarded",
     [("FfaLateEntry.cs", 'if (!LimitlessFence.ItemResumes(h.Ticket, "call-in hold")) { _hold = null; return; }', "")]),
    ("late_items", "the pending snapshot captures no ticket",
     [("FfaLateEntry.cs", "_pendingSnapTicket = LimitlessFence.CaptureTicket();", "")]),
    ("late_items", "the pending snapshot is checked unguarded",
     [("FfaLateEntry.cs", 'if (!LimitlessFence.ItemResumes(_pendingSnapTicket, "pending snapshot")) { _pendingSnap = null; return; }', "")]),
    ("late_items", "a stopped retained item resumes",
     [(LF, "            if (TicketResumes(t)) return true;\n            NoteItemStopped(name, t);\n            return false;\n",
       "            return true;\n")]),
    ("late_sends", "the boundary captures no ticket",
     [("FfaLateEntry.cs", "            var sendTicket = LimitlessFence.CaptureTicket();   // v4 4.4: the stamp's S, after the waits\n", "")]),
    ("late_sends", "the stamp sends without the handoff test",
     [("FfaLateEntry.cs", "if (!LimitlessFence.TicketSends(sendTicket, MasterMaySend())) yield break;", "")]),
    ("late_sends", "a stored request is answered without its ticket",
     [("FfaLateEntry.cs", "if (!LimitlessFence.TicketSends(LateTicket(actor), MasterMaySend()))", "if (false)")]),
    ("late_sends", "a late request keeps no ticket",
     [("FfaLateEntry.cs", "_lateTickets[sender] = LimitlessFence.CaptureTicket();", "")]),
    ("late_sends", "the late tickets outlive their requests",
     [("FfaLateEntry.cs", "            _lateTickets.Clear();\n", "")]),
    ("hold_items", "the cut captures no ticket",
     [("TeamHoldWriter.cs", "                _cutTicket = LimitlessFence.CaptureTicket();   // v4 4.5 R\n", "")]),
    ("hold_items", "the cut is read without its ticket",
     [("TeamHoldWriter.cs", "return _cut != null && LimitlessFence.TicketResumes(_cutTicket) ? _cut : null;", "return _cut;")]),
    ("hold_items", "a cut whose ticket moved is kept",
     [("TeamHoldWriter.cs", 'if (LimitlessFence.ItemResumes(_cutTicket, "hold")) return true;', "return true;")]),
    ("hold_items", "the leave keeps an earlier game's cut",
     [("TeamHoldWriter.cs", "if (CutResumes())   // v4 4.5 R: an earlier game's cut is dropped first", "if (_cut != null)")]),
    ("hold_items", "the expiry runs the today-path for an earlier game's cut",
     [("TeamHoldWriter.cs", "            if (!CutResumes()) return;   // v4 4.5 R: no today-path for an earlier game's cut\n", "")]),
    ("hold_items", "the point tick runs without the cut's ticket",
     [("TeamHoldWriter.cs", "if (!CutResumes() || _resolved) return;", "if (_cut == null || _resolved) return;")]),
    ("hold_items", "an expired drop's end runs without its ticket",
     [("TeamHoldWriter.cs", " && EndingResumes())   // v4 4.5 R", ")")]),
    ("hold_items", "the ending cut keeps no ticket",
     [("TeamHoldWriter.cs", "                _endingTicket = TeamHold.CutTicket;   // v4 4.5 R\n", "")]),
    ("hold_items", "a stopped end is kept",
     [("TeamHoldWriter.cs", 'if (LimitlessFence.ItemResumes(_endingTicket, "hold end")) return true;\n            _endingCut = null;\n',
       'if (LimitlessFence.ItemResumes(_endingTicket, "hold end")) return true;\n')]),
    ("hold_items", "the state read's answer applies without its ticket",
     [("TeamHoldWriter.cs", 'if (gen != _readGen || !LimitlessFence.ItemResumes(rt, "hold read")) return;', "if (gen != _readGen) return;")]),
    ("hold_items", "the end post's answer applies without its ticket",
     [("TeamHoldWriter.cs", ' && LimitlessFence.ItemResumes(rt, "hold end answer")) Perform(w.OnEndAnswer(Now), cut);',
       ") Perform(w.OnEndAnswer(Now), cut);")]),
    ("observer_apply", "the observer's boundary captures no ticket",
     [("SpectatorSync.cs", "            var ticket = LimitlessFence.CaptureTicket();   // v4 4.5 R (F5): where the boundary is scheduled\n", "")]),
    ("observer_apply", "the apply is not handed the boundary's ticket",
     [("SpectatorSync.cs", "yield return ApplyDecks(snap, gen, attemptGen, forceReset, ticket);",
       "yield return ApplyDecks(snap, gen, attemptGen, forceReset, LimitlessFence.CaptureTicket());")]),
    ("observer_apply", "an epoch stop counts as a failed apply",
     [("SpectatorSync.cs", "                if (!LimitlessFence.TicketCleans(ticket)) { superseded = true; yield break; }\n", "")]),
    ("observer_apply", "the apply's loop reads the session alone",
     [("SpectatorSync.cs", "                if (ObserverMoved(gen, attemptGen, ticket)) yield break;   // v4 4.5 R (F5)\n                int actor = actors[i];\n",
       "                if (gen != _boundaryGeneration) yield break;\n                int actor = actors[i];\n")]),
    ("observer_apply", "an extension step reads the session alone",
     [("SpectatorSync.cs", "                        if (ObserverMoved(gen, attemptGen, ticket)) yield break;   // v4 4.5 R (F5)\n                        if (!ApplyOne(body, actor, target[k]))",
       "                        if (gen != _boundaryGeneration) yield break;\n                        if (!ApplyOne(body, actor, target[k]))")]),
    ("observer_apply", "the step after the nested replay reads the session alone",
     [("SpectatorSync.cs", "ticket);\n                    if (ObserverMoved(gen, attemptGen, ticket)) yield break;   // v4 4.5 R (F5)\n",
       "ticket);\n                    if (gen != _boundaryGeneration) yield break;\n")]),
    ("observer_apply", "the nested replay is not handed the attempt",
     [("SpectatorSync.cs", "yield return ResetAndReplay(body, actor, target, gen, attemptGen, ticket);",
       "yield return ResetAndReplay(body, actor, target, gen, _boundaryAttemptGen, ticket);")]),
    ("observer_apply", "the nested replay's first resume reads the session alone",
     [("SpectatorSync.cs", "            if (ObserverMoved(gen, attemptGen, ticket)) yield break;   // v4 4.5 R (F5): the attempt passed down\n",
       "            if (gen != _boundaryGeneration) yield break;\n")]),
    ("observer_apply", "the nested replay's steps read the session alone",
     [("SpectatorSync.cs", "                if (ObserverMoved(gen, attemptGen, ticket)) yield break;   // v4 4.5 R (F5)\n                if (!ApplyOne(body, actor, name)) yield break;",
       "                if (gen != _boundaryGeneration) yield break;\n                if (!ApplyOne(body, actor, name)) yield break;")]),
    ("observer_apply", "the observer's check skips the epoch",
     [("SpectatorSync.cs", '=> BoundaryFenceMoved(gen, attemptGen) || !LimitlessFence.EpochHolds(ticket, "observer deck apply");',
       "=> BoundaryFenceMoved(gen, attemptGen);")]),
    ("observer_apply", "the epoch check never stops",
     [(LF, "if (TicketCleans(t)) return true;", "return true;")]),
    ("observer_flush", "the deferred flush is not a cleanup item",
     [("SpectatorSync.cs", "Plugin.Instance.StartCoroutine(LimitlessFence.CleanupItem(   // v4 4.5 C\n"
       '                        DeferredGameOverFlush(_boundaryGeneration, _boundaryAttemptGen, _lastSeenEpoch), "observer flush wait"));',
       "Plugin.Instance.StartCoroutine(\n                        DeferredGameOverFlush(_boundaryGeneration, _boundaryAttemptGen, _lastSeenEpoch));")]),
    ("observer_flush", "the game-over flush is not a cleanup item",
     [("SpectatorSync.cs", 'Plugin.Instance.StartCoroutine(LimitlessFence.CleanupItem(BetweenGamesFlush(_boundaryGeneration, _boundaryAttemptGen), "observer flush"));',
       "Plugin.Instance.StartCoroutine(BetweenGamesFlush(_boundaryGeneration, _boundaryAttemptGen));")]),
    ("observer_flush", "the waiter's flush is not a cleanup item",
     [("SpectatorSync.cs", 'Plugin.Instance.StartCoroutine(LimitlessFence.CleanupItem(BetweenGamesFlush(gen, attemptGen), "observer flush"));',
       "Plugin.Instance.StartCoroutine(BetweenGamesFlush(gen, attemptGen));")]),
    ("observer_flush", "the game-over flush resumes as R",
     [("SpectatorSync.cs", 'LimitlessFence.CleanupItem(BetweenGamesFlush(_boundaryGeneration, _boundaryAttemptGen), "observer flush")',
       'LimitlessFence.ResumableItem(BetweenGamesFlush(_boundaryGeneration, _boundaryAttemptGen), "observer flush")')]),
    ("observer_flush", "FFA's observer flush is not a cleanup item",
     [("FfaMode.cs", "Plugin.Instance.StartCoroutine(LimitlessFence.CleanupItem(SpectatorBetweenGamesFlush(",
       "Plugin.Instance.StartCoroutine(SpectatorBetweenGamesFlush("),
      ("FfaMode.cs", 'SpectatorSync.BoundaryAttemptGeneration), "ffa observer flush")); }', "SpectatorSync.BoundaryAttemptGeneration)); }")]),
    ("base_target", "the retirement keeps the raised target",
     [(LF, "            RestoreBaseTarget(why);\n", "")]),
    ("base_target", "the restore runs after the record is cleared",
     [(LF, "            RestoreBaseTarget(why);\n            _hasRecord = false;\n", "            _hasRecord = false;\n"),
      (LF, "            _record = default(LimitlessFenceRules.FenceRecord);\n",
       "            _record = default(LimitlessFenceRules.FenceRecord);\n            RestoreBaseTarget(why);\n")]),
    ("base_target", "GM's restore keeps the record's target",
     [(LF, "if (gm != null) gm.roundsToWinGame = _record.BaseTarget;", "if (gm != null) gm.roundsToWinGame = _record.TargetRounds;")]),
    ("base_target", "the restore skips FFA",
     [(LF, "            if (_targetFfa) FfaMode.RestoreConfiguredTarget();\n            else\n", "            if (!_targetFfa)\n")]),
    ("base_target", "the record's target write is not noted",
     [(LF, "            _targetRaised = true;   // R1: the record's retirement puts the base back\n", "")]),
    ("base_target", "FFA's restore keeps the record's target",
     [("FfaMode.cs", "            RoundsToWin = _configuredTarget;\n", "")]),
    ("ffa_target_writers", "the pending config writes the target directly",
     [("FfaMode.cs", "SetConfiguredTarget(Mathf.Clamp(scoreTarget, 3, 10));", "RoundsToWin = Mathf.Clamp(scoreTarget, 3, 10);")]),
    ("ffa_target_writers", "the defaults write the target directly",
     [("FfaMode.cs", "SetConfiguredTarget(5); CardCandidates = 5;", "RoundsToWin = 5; CardCandidates = 5;")]),
    ("ffa_target_writers", "the setter overwrites the record's target",
     [("FfaMode.cs", "            if (LimitlessFence.HoldsFfaTarget) return;\n", "")]),
    ("ffa_target_writers", "the hold ignores the record's state",
     [(LF, "get { return RecordOpen && _targetRaised && _targetFfa; }", "get { return _targetRaised && _targetFfa; }")]),
    ("ffa_target_writers", "the spectator latch writes the target past the setter",
     [("FfaMode.cs", "if (LatchConfigFromRoom()) spectatorCfgRoom = rn;", "if (LatchConfigFromRoom()) { spectatorCfgRoom = rn; RoundsToWin = 5; }")]),
    ("join_record", "the join never reads the mirror",
     [("SpectatorSync.cs", '                try { LimitlessFence.ReadJoinRecord("spectator join"); }\n', "")]),
    ("join_record", "the mirror is read more than once",
     [(LF, "            _joinRecordRead = true;\n            if (_hasRecord) return;\n", "            if (_hasRecord) return;\n")]),
    ("join_record", "the mirror's read overwrites a record",
     [(LF, "            _joinRecordRead = true;\n            if (_hasRecord) return;\n", "            _joinRecordRead = true;\n")]),
    ("join_record", "the mirror's read takes any gid",
     [(LF, "out args, out stamp)) return;\n            if (!string.Equals(rec.Gid, RoomGid(), StringComparison.Ordinal) || !_ledger.IsLiveGid(rec.Gid)) return;\n",
       "out args, out stamp)) return;\n")]),
    ("join_record", "the joiner's record counts as confirmed",
     [(LF, "            _unconfirmed = true;\n", "            _unconfirmed = false;\n")]),
    ("join_record", "an accepted message leaves the record unconfirmed",
     [(LF, "            _unconfirmed = false;   // 4.3: an accepted message confirms a joiner's starting value\n", "")]),
    ("join_record", "a join keeps the read spent",
     [(LF, "            _joinRecordRead = false;\n", "")]),
    ("join_record", "the retirement keeps the unconfirmed mark",
     [(LF, "            _hasRecord = false;\n            _unconfirmed = false;\n", "            _hasRecord = false;\n")]),
    ("snapshot_record", "the master's answer carries no record",
     [("SpectatorSync.cs", "var snap = LimitlessFence.AppendSnapshotRecord(BuildSnapshot(seq));", "var snap = BuildSnapshot(seq);")]),
    ("snapshot_record", "the answer carries a joiner's unconfirmed record",
     [(LF, "if (snap == null || !RecordOpen || _unconfirmed) return snap;", "if (snap == null || !RecordOpen) return snap;")]),
    ("snapshot_record", "the answer carries the record's end flag, not the seat's state",
     [(LF, "            r.EndFlag = _state == LimitlessFenceRules.FencePhase.PhaseTerminating;\n", "")]),
    ("snapshot_record", "the receiver ignores the snapshot's record",
     [("SpectatorSync.cs", "            try { LimitlessFence.TakeSnapshotRecord(a); }\n", "")]),
    ("snapshot_record", "the record is taken after the seed",
     [("SpectatorSync.cs", "            try { LimitlessFence.TakeSnapshotRecord(a); }\n", ""),
      ("SpectatorSync.cs", "                        FfaMode.SpectatorSeedScores(rounds, points);\n",
       "                        FfaMode.SpectatorSeedScores(rounds, points);\n                    LimitlessFence.TakeSnapshotRecord(a);\n")]),
    ("snapshot_record", "a snapshot without a record keeps the mirror's",
     [(LF, "if (_hasRecord && _unconfirmed) RetireRecord(", "if (false) RetireRecord(")]),
    ("snapshot_record", "the snapshot overrides an accepted message's record",
     [(LF, "            if (_hasRecord && !_unconfirmed) return;\n", "")]),
    ("snapshot_record", "the snapshot's record takes any gid",
     [(LF, "            if (_hasRecord && !_unconfirmed) return;\n            if (!string.Equals(rec.Gid, RoomGid(), StringComparison.Ordinal) || !_ledger.IsLiveGid(rec.Gid)) return;\n",
       "            if (_hasRecord && !_unconfirmed) return;\n")]),
    ("snapshot_record", "the master's snapshot leaves the mirror readable",
     [(LF, "            _joinRecordRead = true;\n            LimitlessFenceRules.FenceRecord rec;\n", "            LimitlessFenceRules.FenceRecord rec;\n")]),
    ("snapshot_record", "the snapshot's record stays unconfirmed",
     [(LF, "            _unconfirmed = false;\n            _state = LimitlessFenceRules.NextState(LimitlessFenceRules.FencePhase.PhaseLive",
       "            _state = LimitlessFenceRules.NextState(LimitlessFenceRules.FencePhase.PhaseLive")]),
    ("observer_seed", "a terminating seed ends the observer",
     [("FfaMode.cs", "                if (terminal && !completedRound && LimitlessFence.RecordTerminating) return;\n", "")]),
    ("observer_seed", "the seed reads as a completed round",
     [("FfaMode.cs", "                SpectatorCheckGameOver(false);\n", "                SpectatorCheckGameOver(true);\n")]),
    ("observer_seed", "a completed round reads as a seed",
     [("FfaMode.cs", "                        SpectatorCheckGameOver(true);\n", "                        SpectatorCheckGameOver(false);\n")]),
    ("observer_seed", "the seed test reads an open record, not a terminating one",
     [("FfaMode.cs", "LimitlessFence.RecordTerminating) return;", "LimitlessFence.RecordOpen) return;")]),
    ("observer_seed", "the terminating test reads the record alone",
     [(LF, "get { return _hasRecord && _state == LimitlessFenceRules.FencePhase.PhaseTerminating; }", "get { return _hasRecord; }")]),
    ("gm_observer_end", "the GM observer's target is not the live field",
     [("SpectatorPatches.cs", "int rtw = __instance.roundsToWinGame; if (rtw <= 0) rtw = 5;", "int rtw = 5;")]),
    ("gm_observer_end", "the GM observer ends without a conversion",
     [("SpectatorPatches.cs", "bool gameOver = conversion\n                    && (winningTeamID == 0 ? p1r : p2r) >= rtw;",
       "bool gameOver = (winningTeamID == 0 ? p1r : p2r) >= rtw;")]),
    ("gm_observer_end", "the GM observer's game over is not dispatched",
     [("SpectatorPatches.cs", "                if (gameOver) SpectatorSync.OnGameOverObserved();\n", "")]),
    ("match_start_gate", "the match start has no continuation gate",
     [("GameStateWatcher.cs", "            if (LimitlessFence.RecordOpen) return;\n            try { Keybinds.OnRoundStart(); } catch { }",
       "            try { Keybinds.OnRoundStart(); } catch { }")]),
    ("match_start_gate", "the gate sits after the re-arm",
     [("GameStateWatcher.cs", "            if (LimitlessFence.RecordOpen) return;\n            try { Keybinds.OnRoundStart(); } catch { }",
       "            try { Keybinds.OnRoundStart(); } catch { }"),
      ("GameStateWatcher.cs", "            isTracking = true;\n            gameOverReported = false;\n",
       "            isTracking = true;\n            gameOverReported = false;\n            if (LimitlessFence.RecordOpen) return;\n")]),
    ("match_start_gate", "the poll re-arms around the gate",
     [("GameStateWatcher.cs", "if (gameActive && !wasGameInProgress && !isTracking)\n            {\n                OnMatchStarted();\n",
       "if (gameActive && !wasGameInProgress && !isTracking)\n            {\n                isTracking = true; gameOverReported = false;\n")]),
    ("match_start_gate", "the log line re-arms around the gate",
     [("GameStateWatcher.cs", '                    try { OnMatchStarted(); } catch (Exception ex) { Plugin.Log.LogWarning($"[ACH] early start hook: {ex.Message}"); }\n',
       "                    isTracking = true; gameOverReported = false;\n")]),
    ("match_start_gate", "another site resets the report latch",
     [("GameStateWatcher.cs", '                    try { OnMatchStarted(); } catch (Exception ex) { Plugin.Log.LogWarning($"[ACH] early start hook: {ex.Message}"); }\n',
       '                    try { OnMatchStarted(); } catch (Exception ex) { Plugin.Log.LogWarning($"[ACH] early start hook: {ex.Message}"); }\n'
       "                    gameOverReported = false;\n")]),
    ("ffa_base_report", "FFA has no base report",
     [("FfaMode.cs", "if (roundOver && !gameOver && winnerTeam >= 0 && LimitlessFence.RecordOpen\n                && rounds[winnerTeam] >= LimitlessFence.CurrentRecord.BaseTarget)",
       "if (false)")]),
    ("ffa_base_report", "the base report sets gameOverFired",
     [("FfaMode.cs", "                try { GameStateWatcher.OnFfaGameOver(winnerTeam); }\n                catch (Exception ex) { Plugin.Log.LogError($\"[FFA] base report hook",
       "                gameOverFired = true;\n                try { GameStateWatcher.OnFfaGameOver(winnerTeam); }\n                catch (Exception ex) { Plugin.Log.LogError($\"[FFA] base report hook")]),
    ("ffa_base_report", "the base report runs without a record",
     [("FfaMode.cs", "winnerTeam >= 0 && LimitlessFence.RecordOpen\n                && rounds[winnerTeam]", "winnerTeam >= 0\n                && rounds[winnerTeam]")]),
    ("ffa_base_report", "the base report reads the live target",
     [("FfaMode.cs", "rounds[winnerTeam] >= LimitlessFence.CurrentRecord.BaseTarget)", "rounds[winnerTeam] >= RoundsToWin)")]),
    ("ffa_base_report", "the sitting end moves to the base",
     [("FfaMode.cs", "                catch (Exception ex) { Plugin.Log.LogError($\"[FFA] base report hook: {ex.Message}\"); }\n",
       "                catch (Exception ex) { Plugin.Log.LogError($\"[FFA] base report hook: {ex.Message}\"); }\n"
       "                Plugin.Instance.StartCoroutine(LimitlessFence.CleanupItem(EndSittingBelowMinimum(), \"ffa sitting end\"));\n")]),
    ("ffa_base_report", "FFA's report latch is skipped",
     [("GameStateWatcher.cs", "            if (gameOverReported) return;\n            gameOverReported = true;\n            isTracking = false;    // the next game re-arms",
       "            gameOverReported = true;\n            isTracking = false;    // the next game re-arms")]),
    ("base_results", "the base copy drops the victory unlock",
     [("LimitlessFence.cs", '                    PlatformCall("UnlockAchievement", "Victory");\n', "")]),
    ("base_results", "the base copy drops the winner progress",
     [("LimitlessFence.cs", '                    PlatformCall("ProgressAchievement", "Winner");\n', "")]),
    ("base_results", "the base copy drops the champion progress",
     [("LimitlessFence.cs", '                    PlatformCall("ProgressAchievement", "Champion");\n', "")]),
    ("base_results", "the base copy drops the streak unlock",
     [("LimitlessFence.cs", '                    if (three) PlatformCall("UnlockAchievement", "ThreeInARow");\n', "")]),
    ("base_results", "the base copy drops the ace",
     [("LimitlessFence.cs", '                if (aw.BaseAce) PlatformCall("UnlockAchievement", "Ace");\n', "")]),
    ("base_results", "the base copy drops the joker",
     [("LimitlessFence.cs", '                if (aw.BaseJoker) PlatformCall("UnlockAchievement", "Joker");\n', "")]),
    ("base_results", "the base copy runs on every accepted message",
     [("LimitlessFence.cs", "if (outcome == LimitlessFenceRules.HandlerOutcome.CreateRecord && !ffa) RunBaseResults(gm, rec);",
       "if (!ffa) RunBaseResults(gm, rec);")]),
    ("base_results", "the base copy runs in FFA",
     [("LimitlessFence.cs", "CreateRecord && !ffa) RunBaseResults(gm, rec);", "CreateRecord) RunBaseResults(gm, rec);")]),
    ("base_results", "the base copy reads the raised target",
     [("LimitlessFence.cs", "rec.BaseWinner, p1, p2, rec.BaseTarget);", "rec.BaseWinner, p1, p2, gm.roundsToWinGame);")]),
    ("base_results", "the base copy's streak is not written back",
     [("LimitlessFence.cs", "                    gm.m_winCount = count;\n", "")]),
    ("base_results", "a platform name the game lacks is silent",
     [("LimitlessFence.cs", '                Plugin.Log.LogWarning("[LIMIT] PlatformManager." + method + "(" + achievement + ") is not in this build of the game");\n', "")]),
    ("real_end_hold", "the hold is set without a record",
     [("LimitlessFence.cs", "if (!LimitlessFence.RecordOpen || __instance == null) return;", "if (__instance == null) return;")]),
    ("real_end_hold", "the real end's unlock is not held",
     [("LimitlessFence.cs", "internal static class LimitlessFence_HeldUnlock_Patch\n    {\n        private static bool Prefix() { return !LimitlessFence.PlatformResultsHeld; }",
       "internal static class LimitlessFence_HeldUnlock_Patch\n    {\n        private static bool Prefix() { return true; }")]),
    ("real_end_hold", "the real end's progress call is not held",
     [("LimitlessFence.cs", "internal static class LimitlessFence_HeldProgress_Patch\n    {\n        private static bool Prefix() { return !LimitlessFence.PlatformResultsHeld; }",
       "internal static class LimitlessFence_HeldProgress_Patch\n    {\n        private static bool Prefix() { return true; }")]),
    ("real_end_hold", "the finalizer drops the restore",
     [("LimitlessFence.cs", "                __instance.m_lastWinningTeam = __state.LastWinner;\n                __instance.m_winCount = __state.WinCount;\n", "")]),
    ("real_end_hold", "the finalizer leaves the hold set",
     [("LimitlessFence.cs", "            LimitlessFence.PlatformResultsHeld = false;\n", "")]),
    ("real_end_hold", "the capability is staged without the hold",
     [("LimitlessFence.cs", "                if (!RealEndHoldLive)\n", "                if (false)\n")]),
    ("real_end_hold", "the hold's attach skips the progress patch",
     [("LimitlessFence.cs", "return RealEndLive && HeldUnlockLive && HeldProgressLive;", "return RealEndLive && HeldUnlockLive;")]),
    ("token_real_end", "the real end's void acts on an ended game",
     [("TeamGameNumber.cs", "if (!inGame || overSeen) return null;", "if (overSeen) return null;")]),
    ("token_real_end", "the base's report leaves the token's game armed",
     [("TeamGameNumber.cs", "                EndGameToken();\n                inGame = false;\n                overSeen = false;\n                boundaryMissed = false;\n                resetOut = false;\n",
       "                EndGameToken();\n                overSeen = false;\n                boundaryMissed = false;\n                resetOut = false;\n")]),
    ("token_real_end", "the real end re-arms the token's game",
     [("TeamGameNumber.cs", "                return GmVoid(\"the game itself ended this seat's game\");\n",
       "                inGame = true;\n                return GmVoid(\"the game itself ended this seat's game\");\n")]),
]

NEUTRAL = "            // control: a neutral line\n"
CONTROLS = [
    ("game_start_prefix", [(LF, GATE, NEUTRAL + GATE)]),
    ("stamp_before_join", [("Plugin.cs", STAMP, NEUTRAL + STAMP)]),
    ("handoff_first", [(LF, COUNT, NEUTRAL + COUNT)]),
    ("adoption_from_relay", [(LF, MINT_LOG, NEUTRAL + MINT_LOG)]),
    ("mint_cas", [(LF, SHOULD, NEUTRAL + SHOULD)]),
    ("room_edges", [(LF, EXIT, NEUTRAL + EXIT)]),
    ("spectator_boundary", [("SpectatorSync.cs", CALL_IN, NEUTRAL + CALL_IN)]),
    ("raw_round_refusals", [("FfaMode.cs", REF_FFA, NEUTRAL + REF_FFA)]),
    ("record_retires", [(LF, '            RetireRecord("room exit");\n', NEUTRAL + '            RetireRecord("room exit");\n')]),
    ("apply_under_stamp", [(LF, FLAG, NEUTRAL + FLAG)]),
    ("handler_order", [(LF, INSTALL, NEUTRAL + INSTALL)]),
    ("fence_message", [(LF, OPTS, NEUTRAL + OPTS)]),
    ("mirror_cas", [(LF, ME, NEUTRAL + ME)]),
    ("capability", [(LF, ST, NEUTRAL + ST)]),
    ("uncovered_leave", [(LF, LATCH, NEUTRAL + LATCH)]),
    ("gm_prefix", [(LF, "            if (!__runOriginal) return false;\n", NEUTRAL + "            if (!__runOriginal) return false;\n")]),
    ("gm_send", [(LF, "            if (pm == null || pm.TeamsAlive() >= 2) return FenceSend.Vanilla;\n",
                  NEUTRAL + "            if (pm == null || pm.TeamsAlive() >= 2) return FenceSend.Vanilla;\n")]),
    ("ffa_send", [("FfaMode.cs", "                LimitlessFence.FenceSend fence;\n", NEUTRAL + "                LimitlessFence.FenceSend fence;\n")]),
    ("decision_inputs", [(LF, "            var why = LimitlessFenceRules.DecideContinuation(d);\n",
                          NEUTRAL + "            var why = LimitlessFenceRules.DecideContinuation(d);\n")]),
    ("later_rounds", [(LF, "            bool mustEnd = ", NEUTRAL + "            bool mustEnd = ")]),
    ("opt_in", [(LF, "            string want = _optInWanted", NEUTRAL + "            string want = _optInWanted")]),
    ("termination", [(LF, "            _departed = true;\n", NEUTRAL + "            _departed = true;\n")]),
    ("departure_routes", [("Plugin.cs", "            try { LimitlessFence.TerminateOnDeparture(p); } catch { }\n",
                           NEUTRAL + "            try { LimitlessFence.TerminateOnDeparture(p); } catch { }\n")]),
    ("hold_refusal", [("TeamHoldPatches.cs", "                if (LimitlessFence.RecordOpen) return true;\n",
                       NEUTRAL + "                if (LimitlessFence.RecordOpen) return true;\n")]),
    ("sender_end", [(LF, "            if (RecordOpen && _departed) return WithheldAfterDeparture();\n",
                     NEUTRAL + "            if (RecordOpen && _departed) return WithheldAfterDeparture();\n")]),
    ("redrive", [("FfaMode.cs", "                if (AlivePlayers().Count > 1) return;\n",
                  NEUTRAL + "                if (AlivePlayers().Count > 1) return;\n")]),
    ("no_admission", [("FfaLateEntry.cs", "            if (LimitlessFence.RecordOpen) { LateGiveUp(); return; }   // 4.6: no admission\n",
                       NEUTRAL + "            if (LimitlessFence.RecordOpen) { LateGiveUp(); return; }   // 4.6: no admission\n")]),
    ("late_tail", [("FfaReadmit.cs", '                    if (LimitlessFence.RecordOpen) { Refusal("limitless", true); break; }\n',
                    NEUTRAL + '                    if (LimitlessFence.RecordOpen) { Refusal("limitless", true); break; }\n')]),
    ("entrant_exit", [(LF, "            if (FfaLateEntry.IsQuarantinedActor(p.ActorNumber)) return;\n",
                       NEUTRAL + "            if (FfaLateEntry.IsQuarantinedActor(p.ActorNumber)) return;\n")]),
    ("resume_rows", [("TeamHoldReturn.cs", "                // v4 4.5 R (Table A, H): the replay resumes only under its ticket.\n",
                      NEUTRAL + "                // v4 4.5 R (Table A, H): the replay resumes only under its ticket.\n")]),
    ("guard_wiring", [(LF, "            return new ResumeTicket { Epoch = _epoch, Gid = RecordOpen ? _record.Gid : null, Handoff = _handoff };\n",
                       NEUTRAL + "            return new ResumeTicket { Epoch = _epoch, Gid = RecordOpen ? _record.Gid : null, Handoff = _handoff };\n")]),
    ("pick_sends", [("FfaMode.cs", "            var sendTicket = LimitlessFence.CaptureTicket();\n",
                     NEUTRAL + "            var sendTicket = LimitlessFence.CaptureTicket();\n")]),
    ("pick_period", [("FfaMode.cs", "            if (!LimitlessFence.TicketHandoffMoved(t, FfaLateEntry.MasterMaySend())) return false;\n",
                      NEUTRAL + "            if (!LimitlessFence.TicketHandoffMoved(t, FfaLateEntry.MasterMaySend())) return false;\n")]),
    ("pick_receiver", [("FfaMode.cs", "            cycleNumber++;\n            int cycle = cycleNumber;\n",
                        NEUTRAL + "            cycleNumber++;\n            int cycle = cycleNumber;\n")]),
    ("late_items", [("FfaLateEntry.cs", "            public LimitlessFence.ResumeTicket Ticket = LimitlessFence.CaptureTicket();",
                     NEUTRAL + "            public LimitlessFence.ResumeTicket Ticket = LimitlessFence.CaptureTicket();")]),
    ("late_sends", [("FfaLateEntry.cs", "            var sendTicket = LimitlessFence.CaptureTicket();   // v4 4.4: the stamp's S",
                     NEUTRAL + "            var sendTicket = LimitlessFence.CaptureTicket();   // v4 4.4: the stamp's S")]),
    ("hold_items", [("TeamHoldWriter.cs", "                _cutTicket = LimitlessFence.CaptureTicket();   // v4 4.5 R",
                     NEUTRAL + "                _cutTicket = LimitlessFence.CaptureTicket();   // v4 4.5 R")]),
    ("observer_apply", [("SpectatorSync.cs", "            var ticket = LimitlessFence.CaptureTicket();   // v4 4.5 R (F5)",
                         NEUTRAL + "            var ticket = LimitlessFence.CaptureTicket();   // v4 4.5 R (F5)")]),
    ("observer_flush", [("SpectatorSync.cs", "                Plugin.Instance.StartCoroutine(LimitlessFence.CleanupItem(BetweenGamesFlush(_boundaryGeneration",
                         NEUTRAL + "                Plugin.Instance.StartCoroutine(LimitlessFence.CleanupItem(BetweenGamesFlush(_boundaryGeneration")]),
    ("base_target", [(LF, "            RestoreBaseTarget(why);\n", NEUTRAL + "            RestoreBaseTarget(why);\n")]),
    ("ffa_target_writers", [("FfaMode.cs", "            _configuredTarget = target;\n", NEUTRAL + "            _configuredTarget = target;\n")]),
    ("join_record", [(LF, "            _unconfirmed = true;\n", NEUTRAL + "            _unconfirmed = true;\n")]),
    ("snapshot_record", [(LF, "            if (_hasRecord && !_unconfirmed) return;\n", NEUTRAL + "            if (_hasRecord && !_unconfirmed) return;\n")]),
    ("observer_seed", [("FfaMode.cs", "                if (terminal && !completedRound", NEUTRAL + "                if (terminal && !completedRound")]),
    ("gm_observer_end", [("SpectatorPatches.cs", "                if (gameOver) SpectatorSync.OnGameOverObserved();\n",
                          NEUTRAL + "                if (gameOver) SpectatorSync.OnGameOverObserved();\n")]),
    ("match_start_gate", [("GameStateWatcher.cs", "            if (LimitlessFence.RecordOpen) return;\n            try { Keybinds",
                           NEUTRAL + "            if (LimitlessFence.RecordOpen) return;\n            try { Keybinds")]),
    ("ffa_base_report", [("FfaMode.cs", "            if (roundOver && !gameOver && winnerTeam >= 0",
                          NEUTRAL + "            if (roundOver && !gameOver && winnerTeam >= 0")]),
    ("base_results", [("LimitlessFence.cs", "            if (outcome == LimitlessFenceRules.HandlerOutcome.CreateRecord && !ffa) RunBaseResults(gm, rec);\n",
                       NEUTRAL + "            if (outcome == LimitlessFenceRules.HandlerOutcome.CreateRecord && !ffa) RunBaseResults(gm, rec);\n")]),
    ("real_end_hold", [("LimitlessFence.cs", "                LimitlessFence.PlatformResultsHeld = true;\n",
                        NEUTRAL + "                LimitlessFence.PlatformResultsHeld = true;\n")]),
    ("token_real_end", [("TeamGameNumber.cs", "                if (!inGame || overSeen) return null;\n",
                         NEUTRAL + "                if (!inGame || overSeen) return null;\n")]),
]


def _mutated(edits):
    files = dict(FILES)
    for fname, old, new in edits:
        assert files[fname].count(old) == 1, (fname, old[:90])
        files[fname] = files[fname].replace(old, new)
    return files


@pytest.mark.parametrize("name", sorted(CLAIMS))
def test_the_claim_holds_on_the_tree(name):
    assert CLAIMS[name](FILES) == []


@pytest.mark.parametrize("claim,label,edits", MUTANTS, ids=[m[1] for m in MUTANTS])
def test_each_mutant_turns_its_claim_red(claim, label, edits):
    assert CLAIMS[claim](FILES) == []
    assert CLAIMS[claim](_mutated(edits)) != [], label


@pytest.mark.parametrize("claim,edits", CONTROLS, ids=[c[0] for c in CONTROLS])
def test_each_control_leaves_its_claim_green(claim, edits):
    mutated = _mutated(edits)
    assert mutated != FILES
    assert CLAIMS[claim](mutated) == []


def test_every_claim_has_mutants_and_a_control():
    assert {m[0] for m in MUTANTS} == set(CLAIMS) == {c[0] for c in CONTROLS}
    assert len({m[1] for m in MUTANTS}) == len(MUTANTS)
