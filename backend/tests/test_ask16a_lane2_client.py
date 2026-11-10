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
)

FENCE_MUTANTS = (
    'MaySend ignores the handoff count',
    'MaySend ignores the epoch',
    "MaySend ignores the record's end",
    'MayResume reads the epoch only',
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
)


def _caught(names):
    return tuple("mutant (%s) is caught by its named cases" % m for m in names)


FENCE_CASES = (tuple("real: " + n for n in FENCE_RULES) + _caught(FENCE_MUTANTS)
               + _caught("the carrier drops " + f for f in CARRIER_FIELDS))


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
    assert len(set(FENCE_CASES)) == len(FENCE_CASES) == 88 + 29 + 10


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
    if _code(files[LF]).count("SetCustomProperties(") != 1:
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
    if not _in_order(_code(files["FfaMode.cs"], "private static void SpectatorCheckGameOver()"), [
            "spectatorGameOverAnnounced = true;", 'try { LimitlessFence.NoteSpectatorGameOver("ffa"); } catch { }']):
        out.append("the FFA observer's game over does not end the gid")
    return out


CLAIMS = {
    "game_start_prefix": claim_the_game_start_prefix,
    "stamp_before_join": claim_the_gid_is_stamped_before_the_join,
    "handoff_first": claim_the_handoff_count_comes_first,
    "adoption_from_relay": claim_adoption_only_from_the_relay,
    "mint_cas": claim_the_mint_is_a_compare_and_set,
    "room_edges": claim_the_room_edges_note_the_gid,
    "spectator_boundary": claim_the_spectator_boundary,
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


def _drop(fname, line):
    return [(fname, line, "")]


MUTANTS = [
    ("game_start_prefix", "the game-start prefix runs at Normal priority",
     [(LF, "        [HarmonyPriority(Priority.First)]\n", "        [HarmonyPriority(Priority.Normal)]\n")]),
    ("game_start_prefix", "the game-start prefix has no spectator gate", _drop(LF, GATE)),
    ("game_start_prefix", "the game-start prefix gates after the start", [(LF, GATE + START, START + GATE)]),
    ("stamp_before_join", "the room is created without a gid", _drop("Plugin.cs", STAMP)),
    ("stamp_before_join", "the gid is stamped after the join",
     [("Plugin.cs", STAMP, ""), ("Plugin.cs", JOIN, JOIN + STAMP)]),
    ("handoff_first", "the switch notes the handoff after the map-scale ticket",
     [("Plugin.cs", SWITCH, ""), ("Plugin.cs", MAPSCALE, MAPSCALE + SWITCH)]),
    ("handoff_first", "the switch raises no count", _drop(LF, COUNT)),
    ("handoff_first", "the count rises after the mint", [(LF, COUNT + MINT_CALL, MINT_CALL + COUNT)]),
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
