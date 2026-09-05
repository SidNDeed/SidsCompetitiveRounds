"""Review r8 MEDIUM 1, 2 and 4 — the client-side contracts.

M1 is a CLAIM defect, so its test is a claim test. The queue tells this seat
WHO it was paired with; it never says which Photon actor that is, and the u_id
the pairing gets compared against is a custom property the peer's own game
writes. Nothing on the client can turn that comparison into an authentication,
so the code keeps the comparison — it only ever shows LESS than the ordinary
room's path — and every artifact that described it as identity verification is
corrected. The test pins the corrected wording, in the source AND in the
CHANGELOG, because the CHANGELOG line is the one a player reads (#302/#351).

M2 is a lifecycle hole: one retained record describes one room, so a second
issuance took the first room's pairing away while this seat could still be
sitting in it, and the bare name mismatch that produced read as "never issued"
— releasing the line to the advertised id in exactly the room that was supposed
to be attested. A tombstone keeps that room suppressed until the leave edge.

M4 is the difference between a poll and a latch. The lag-notice window claimed
one opponent for its WHOLE span while only sampling the key once per frame, and
one PUN Dispatch can drain an enter, a late delivery and a leave between two
frames — after which both samples agree. A monotonic roster/identity generation
is the trace that does not revert.

These are source-shape tests: the C# has no runner here, so they are written to
fail on the specific mutation each one describes, and every one of them was run
against that mutation (scratchpad/mutate_m3.py) rather than assumed to.
"""

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugin"
H2H_RULES_CS = PLUGIN / "H2HRules.cs"
H2H_SUMMARY_CS = PLUGIN / "H2HSummary.cs"
API_CLIENT_CS = PLUGIN / "ApiClient.cs"
ROOM_ACTORS_CS = PLUGIN / "RoomActors.cs"
PLUGIN_CS = PLUGIN / "Plugin.cs"
TELEMETRY_CS = PLUGIN / "NetworkSeatTelemetry.cs"
CHANGELOG = REPO / "docs" / "CHANGELOG.md"


def _cs_method_body(path, signature):
    """The braces-matched body of one C# member, so an assertion about a
    method cannot be satisfied by a match elsewhere in the file."""
    src = path.read_text(encoding="utf-8")
    start = src.index(signature)
    open_brace = src.index("{", start)
    depth = 0
    for i in range(open_brace, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[open_brace : i + 1]
    raise AssertionError(f"unbalanced braces after {signature}")


# ── M1: the claim ────────────────────────────────────────────────────────────

def _prose(path):
    """One line of running text: comment markers dropped and whitespace
    collapsed, so a phrase is found however the source happens to wrap."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^\s*///?", " ", text, flags=re.MULTILINE)
    return " ".join(text.split())


# Each of these described the comparison as establishing who the other fighter
# IS. None of them can be true while u_id is peer-authored.
OVERSTATEMENTS = (
    "the queue assigned and nobody else",
    "the attestation verifies an identity",
    "attestation the fighter's advertised id does not match",
    "server-attested opponent",
)


def test_no_artifact_describes_the_pairing_as_authenticating_the_fighter():
    for path in (H2H_RULES_CS, H2H_SUMMARY_CS, API_CLIENT_CS, CHANGELOG):
        text = _prose(path).lower()
        for claim in OVERSTATEMENTS:
            assert claim not in text, f"{path.name} still claims: {claim}"


def test_the_changelog_states_what_the_line_actually_rests_on():
    """The line a player reads. It may promise suppression — that is what the
    code does — but not that the assigned player is the only one who can
    produce the line."""
    text = _prose(CHANGELOG)
    assert (
        "the line is shown only while the other player's game says it is the "
        "opponent the queue assigned" in text
    )
    assert "there is no line at all rather than the assigned player's name and record" in text


def test_the_source_says_the_pairing_is_compared_never_handed_out():
    rules = _prose(H2H_RULES_CS)
    assert "AGREEMENT check" in rules
    assert "not an authentication of the peer" in rules
    assert "bind a Photon actor to a Steam identity" in rules
    summary = _prose(H2H_SUMMARY_CS)
    assert "u_id is a Photon custom property the peer's own game writes" in summary
    assert "nothing on this client can bind a Photon actor to a Steam identity" in summary


# ── M2: the superseded-room tombstone ────────────────────────────────────────


def test_the_tombstone_is_consulted_before_the_record_can_read_as_never_issued():
    """Order is the whole fix: a later issuance can EMPTY the record as well as
    replace it, so a check that ran after `pair == null` would miss the case it
    exists for."""
    body = _cs_method_body(H2H_RULES_CS, "internal static IssuedOpponent ConsultIssued(")
    assert "supersededRoom" in body
    superseded = body.index("supersededRoom ?? \"\"")
    record_absent = body.index("if (pair == null) return IssuedOpponent.NotIssued;")
    assert superseded < record_absent
    # and it suppresses rather than falling through to the advertised id
    tail = body[superseded : superseded + 200]
    assert "return IssuedOpponent.Suppressed;" in tail


def test_a_second_issuance_tombstones_the_room_it_took_the_pairing_from():
    body = _cs_method_body(API_CLIENT_CS, "private static void RetainIssuedPair(string room, string response)")
    assert "supersededIssuedRoom = previous.Value.RoomName;" in body
    # ...and only when it is a DIFFERENT room: the same room re-issued is the
    # pairing's own room, and a tombstone there would suppress the line the
    # pairing is for.
    assert "!string.Equals(previous.Value.RoomName, room ?? \"\", StringComparison.Ordinal)" in body
    # set BEFORE either path that overwrites or empties the slot
    assert body.index("supersededIssuedRoom =") < body.index("issuedPair = null;")
    assert body.index("supersededIssuedRoom =") < body.index("issuedPair = new H2HRules.IssuedPairState")


def test_the_tombstone_is_cleared_at_the_leave_edge_and_on_a_join_elsewhere():
    invalidate = _cs_method_body(H2H_SUMMARY_CS, "internal static void Invalidate()")
    assert "ApiClient.ClearSupersededIssuedRoom();" in invalidate
    retire = _cs_method_body(API_CLIENT_CS, "internal static void RetireIssuedPairUnless(string roomName)")
    assert "supersededIssuedRoom = null;" in retire
    assert "!string.Equals(supersededIssuedRoom, roomName ?? \"\", StringComparison.Ordinal)" in retire
    # Invalidate is Photon's own leave/disconnect callback, not a polled edge
    plugin_src = PLUGIN_CS.read_text(encoding="utf-8")
    assert plugin_src.count("H2HSummary.Invalidate();") == 2


def test_the_self_test_case_count_matches_the_cases_that_exist():
    """The in-game harness passes only on run == SELFTEST_CASES, so a case
    added without the constant reads as a FAILING run on a correct build."""
    src = H2H_RULES_CS.read_text(encoding="utf-8")
    body = src[src.index("internal static int SelfTest(") : src.index("private static string Consult(")]
    declared = int(re.search(r"internal const int SELFTEST_CASES = (\d+);", src).group(1))
    assert len(re.findall(r'Check\("', body)) == declared


# ── M4: the window's generation latch ────────────────────────────────────────


def test_the_window_latches_a_generation_change_and_not_only_a_key_difference():
    sample = _cs_method_body(TELEMETRY_CS, "private static void NoteKeySampleInWindow()")
    assert "RoomActors.RosterGeneration != _wOpenRosterGen" in sample
    # before the key comparison: the key is the thing that can revert
    assert sample.index("RosterGeneration") < sample.index("SampleEligibleKey")
    close = _cs_method_body(TELEMETRY_CS, "private static void CloseWindow(bool force)")
    assert "if (RoomActors.RosterGeneration != _wOpenRosterGen) _wKeyBroken = true;" in close
    assert close.index("RosterGeneration != _wOpenRosterGen") < close.index("LagNotices.WindowKeyed(")


def test_every_window_open_records_the_generation_it_opened_under():
    src = TELEMETRY_CS.read_text(encoding="utf-8")
    opens = re.findall(r"_wOpenRosterGen = RoomActors\.RosterGeneration;", src)
    # the game reset, the first window of a game, and the boundary that opens
    # the next one
    assert len(opens) == 3
    assert src.count("private static int _wOpenRosterGen;") == 1


def test_both_the_roster_and_the_identity_callbacks_move_the_generation():
    invalidate = _cs_method_body(ROOM_ACTORS_CS, "internal static void InvalidateFighterCache()")
    assert "NoteRosterIdentityChange();" in invalidate
    props = _cs_method_body(
        PLUGIN_CS,
        "public void OnPlayerPropertiesUpdate(Photon.Realtime.Player target, "
        "ExitGames.Client.Photon.Hashtable changedProps)",
    )
    assert "RoomActors.NoteRosterIdentityChange();" in props
    for key in ('"u_id"', "RoomActors.SPEC_PROP", "RoomActors.SPEC_LEASE_PROP"):
        assert key in props, f"a property that decides the key is not watched: {key}"
    # the roster callbacks are the only callers of the cache invalidation, so
    # bumping inside it IS "the roster callbacks bump the generation"
    plugin_src = PLUGIN_CS.read_text(encoding="utf-8")
    assert plugin_src.count("RoomActors.InvalidateFighterCache();") == 2


def test_the_generation_only_ever_goes_up():
    """A reset would make it exactly as blind as the key it replaces."""
    src = ROOM_ACTORS_CS.read_text(encoding="utf-8")
    writes = re.findall(r"_rosterGeneration\s*(\+\+|--|=[^=])", src)
    assert writes == ["++"], f"the generation is written some other way: {writes}"
