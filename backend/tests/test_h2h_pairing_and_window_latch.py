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
The tombstone is ONE slot, so r10 found the same hole one issuance further out:
R1 -> R2 -> R3 with the seat still in R1 used to overwrite R1's tombstone with
R2's. A later supersession may now take the slot only from a room this seat has
already left, which is what the tests below pin.

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

from _cs_structure import method_spans, strip_comments_only


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
    method cannot be satisfied by a match elsewhere in the file.

    Structure is decided on a mask (`_cs_structure`), so a brace inside a
    comment, a string, a char literal or an inactive `#if` branch is not
    counted. The raw walk this replaces returned the wrong block on any file
    carrying one - `plugin/Plugin.cs` has raw brace balance +2 from a doc
    comment alone, and `plugin/ApiClient.cs` +22 from JSON inside strings.
    """
    spans = list(method_spans(path, signature))
    if not spans:
        raise AssertionError(f"signature not found: {signature}")
    open_brace, end = spans[0]
    return path.read_text(encoding="utf-8")[open_brace:end]


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
    """The line a player reads. It may promise suppression AFTER the binding —
    that is what the code does — but not that the assigned player is the only
    one who can produce the line in the first place.

    r9 corrected this: ConsultIssued binds on the FIRST actor whose advertised
    id matches, and a Steam id is public, so a game that claims the assigned
    player's id before the assigned player's own game does would be believed.
    Suppression on a seat change applies only once something is bound."""
    text = _prose(CHANGELOG)
    assert "appears only when that name matches the one the queue assigned" in text
    assert "it then follows the first game that matched" in text
    assert (
        "It is an agreement between two games about who is present, not a "
        "check of who really is." in text
    )
    # the overclaim r9 killed must not come back in either wording
    assert "if a different player takes that seat, there is no line at all" not in text


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
    assert "roomSession.SupersededIssuedRoom = previous.Value.RoomName;" in body
    # ...and only when it is a DIFFERENT room: the same room re-issued is the
    # pairing's own room, and a tombstone there would suppress the line the
    # pairing is for.
    assert "!string.Equals(previous.Value.RoomName, room ?? \"\", StringComparison.Ordinal)" in body
    # set BEFORE either path that overwrites or empties the slot
    assert body.index("roomSession.SupersededIssuedRoom =") < body.index("roomSession.IssuedPair = null;")
    assert body.index("roomSession.SupersededIssuedRoom =") < body.index("roomSession.IssuedPair = new H2HRules.IssuedPairState")


def test_a_third_issuance_cannot_take_the_tombstone_from_the_room_we_are_in():
    """r10. The slot holds one room, and it used to hold the most recent
    superseded one unconditionally: with R1 -> R2 -> R3 while the seat was
    still physically in R1, R3's supersession of R2 overwrote R1's tombstone
    and the line in R1 fell back to the room's own occupant ids — in exactly
    the room the tombstone exists for. A later supersession may take the slot
    only from a room this seat has already left."""
    body = _cs_method_body(API_CLIENT_CS, "private static void RetainIssuedPair(string room, string response)")
    assert "PhotonNetwork.InRoom ? (PhotonNetwork.CurrentRoom?.Name ?? \"\") : \"\"" in body, (
        "the guard has to ask which room this seat is actually in"
    )
    assert "bool slotHoldsOurRoom = !string.IsNullOrEmpty(roomSession.SupersededIssuedRoom)" in body
    assert "string.Equals(roomSession.SupersededIssuedRoom, here, StringComparison.Ordinal)" in body
    # the write is reached only when the slot is NOT protecting our own room
    assert body.index("slotHoldsOurRoom") < body.index("roomSession.SupersededIssuedRoom = previous.Value.RoomName;")
    assert body.count("roomSession.SupersededIssuedRoom = previous.Value.RoomName;") == 1
    # an unavailable room name must not be read as "we are in the slot's room"
    assert "!string.IsNullOrEmpty(here)" in body


# The qualifier each artifact must carry. Keyed by file, because the three say
# it in three different registers — a rule, a player-facing summary, and the
# write site — and a single shared phrase would only prove that one of them
# still contains a string.
TOMBSTONE_QUALIFIERS = {
    "H2HRules.cs": "ONE room is remembered, not every superseded room",
    "H2HSummary.cs": "the one remembered room whose pairing a later issuance replaced",
    "ApiClient.cs": "of which only one is remembered",
}

# The unqualified sentence r10 replaced. It must never appear except as part of
# the corrected one.
TOMBSTONE_OVERCLAIM = "a room whose pairing a later issuance replaced"
TOMBSTONE_CORRECTED = "the one remembered room whose pairing a later issuance replaced"


def test_no_artifact_promises_more_than_one_remembered_superseded_room():
    """The claim r10 corrected: the tombstone is ONE slot, so a statement that
    every superseded room stays suppressed is false.

    This guard used to skip any file whose prose lacked a lowercase
    `supersededRoom`/`supersededIssuedRoom` — which excluded H2HSummary.cs, the
    one file carrying the player-facing sentence r10 actually rewrote (its only
    occurrence is the method name `ClearSupersededIssuedRoom`, capital S). So
    restoring the exact overclaim there left the suite green. A conditional
    skip inside a regression guard needs an assertion that the skip did not
    fire; here the skip is gone and each file is named."""
    checked = 0
    for path in (H2H_RULES_CS, H2H_SUMMARY_CS, API_CLIENT_CS):
        prose = _prose(path)
        qualifier = TOMBSTONE_QUALIFIERS[path.name]
        assert qualifier in prose, (
            f"{path.name} no longer says the tombstone is one slot: {qualifier!r}"
        )
        # ...and the bare sentence never appears at all. The corrected phrase
        # reads "...remembered room whose pairing...", so it does not contain
        # the overclaim as a substring and this is not vacuous.
        assert TOMBSTONE_OVERCLAIM not in TOMBSTONE_CORRECTED, "the check would be vacuous"
        assert TOMBSTONE_OVERCLAIM not in prose, (
            f"{path.name} states the overclaim without the one-room qualifier"
        )
        checked += 1
    assert checked == 3, "the file list emptied itself"
    assert "review r10" in _prose(H2H_RULES_CS)


def test_the_tombstone_is_cleared_at_the_leave_edge_and_on_a_join_elsewhere():
    # Both clears are now transitions in the Unity-free component, so the rule
    # is executed by the self-test rather than only read here. What this gate
    # still owns is that the Unity edges REACH those transitions.
    invalidate = _cs_method_body(H2H_SUMMARY_CS, "internal static void Invalidate()")
    assert "ApiClient.OnPairInvalidated();" in invalidate
    rules = H2H_RULES_CS.read_text(encoding="utf-8")
    pair_invalidated = _cs_method_body(
        H2H_RULES_CS, "internal static void OnPairInvalidated(ref RoomSessionState s)")
    assert "s.SupersededIssuedRoom = null;" in pair_invalidated
    left = _cs_method_body(
        H2H_RULES_CS, "internal static void OnRoomLeftReliableEdge(ref RoomSessionState s)")
    assert "s.SupersededIssuedRoom = null;" in left
    joined = _cs_method_body(
        H2H_RULES_CS,
        "internal static void OnRoomJoined(ref RoomSessionState s, string roomName, bool roomNameKnown)")
    assert '!string.Equals(s.SupersededIssuedRoom, roomName ?? "", StringComparison.Ordinal)' in joined, (
        "a join elsewhere must drop the tombstone"
    )
    # ...and the clear is not reachable from anywhere else: one owner per fact.
    assert rules.count("SupersededIssuedRoom = null;") == 3, (
        "a fourth writer of the tombstone would be a second place this is decided"
    )
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
    # Two increment sites since the bug 389 client merge (a new room bumps the
    # generation as well as an identity change); the invariant is that EVERY
    # write is an increment, not that there is exactly one.
    assert writes and all(w == "++" for w in writes),         f"the generation is written some other way: {writes}"


# ── L1: a room name is not a room ────────────────────────────────────────────


def test_a_pairing_describes_one_join_and_not_one_room_name():
    """A code room is player-typed and reusable — the reason ApiClient keeps a
    RoomIncarnation counter at all — so "the name still matches" cannot be what
    keeps a retained pairing alive across a leave and a rejoin."""
    rule = _cs_method_body(
        H2H_RULES_CS,
        "private static bool RetireOnJoin(ref IssuedPairState? pair, string roomName, int incarnation)",
    )
    assert "p.JoinIncarnation < 0" in rule           # first matching join stamps
    assert "p.JoinIncarnation == incarnation" in rule  # the same join is idempotent
    assert rule.count("pair = null;") == 2            # another room, and a later join
    # The pairing is retired inside the join TRANSITION, against the counter
    # that same transition just moved. It used to be a Unity-side method whose
    # caller had to bump first and pass the result, and "the caller remembered"
    # is what a source-shape assertion can only ever approximate - the self-test
    # now executes the sequence (seq:join-stamps-with-the-series-counter).
    joined_rule = _cs_method_body(
        H2H_RULES_CS,
        "internal static void OnRoomJoined(ref RoomSessionState s, string roomName, bool roomNameKnown)")
    assert joined_rule.index("s.PairIncarnation++") < joined_rule.index("RetireOnJoin("), (
        "the join must be retired against the incarnation it opened"
    )
    assert "RetireOnJoin(ref s.IssuedPair, roomName, s.PairIncarnation);" in joined_rule, (
        "the pairing must be retired against the LINE's counter, not the series one"
    )
    # ...and the series half is decided after its own counter moves, which is
    # the r14 HIGH ordering stated as source: two counters, each record
    # against its own.
    assert joined_rule.index("RetireOnJoin(") < joined_rule.index("s.Incarnation++"), (
        "the series counter must move after the pairing is retired, not before"
    )
    assert joined_rule.index("s.Incarnation++") < joined_rule.index("RetireSeriesOnJoin("), (
        "the series record must be stamped against the counter its readers use"
    )


# ── L4: work nothing consumes ────────────────────────────────────────────────


def test_the_window_key_is_not_sampled_when_nothing_can_consume_it():
    """OnWindowClosed returns at its first statement with the setting off, so
    the per-frame sampling that maintains the key is pure cost on every
    eligible 1v1 frame. Skipping it must leave the window UNKEYED, not
    silently keyed on evidence nobody gathered."""
    evaluator = _cs_method_body(Path(PLUGIN / "LagNotices.cs"), "internal static void OnWindowClosed()")
    assert "if (!SettingOn()) { ResetAll(logExits: false, why: null); return; }" in evaluator
    sample = _cs_method_body(TELEMETRY_CS, "private static void NoteKeySampleInWindow()")
    assert "if (!LagNotices.WindowKeyingWanted()) { _wKeyBroken = true; return; }" in sample
    assert sample.index("WindowKeyingWanted") < sample.index("SampleEligibleKey"), (
        "the cheap predicate has to come first or it saves nothing"
    )


# ── L2/L3: the wiring, not the helpers ───────────────────────────────────────


def test_the_per_frame_sample_is_reached_from_the_tick():
    """The harness exercises the rule; only this says the rule is invoked."""
    tick = _cs_method_body(TELEMETRY_CS, "internal static void TickFrame(")
    assert "NoteKeySampleInWindow();" in tick
    assert TELEMETRY_CS.read_text(encoding="utf-8").count("NoteKeySampleInWindow();") == 1


def test_the_issued_pair_reader_hands_the_rule_the_live_record():
    """A wrapper that answered a constant would pass every self-test case."""
    body = _cs_method_body(
        API_CLIENT_CS,
        "internal static H2HRules.IssuedOpponent TryGetIssuedOpponent(string roomName, string advertisedSteamId,",
    )
    assert "H2HRules.ConsultIssued(ref roomSession.IssuedPair, roomSession.SupersededIssuedRoom, queueGen, roomName," in body
    assert "return IssuedOpponent" not in body, "the wrapper must not answer on its own"


def test_both_issuance_paths_retain_the_pairing():
    """Two sites issue a room; a pairing retained at only one of them would
    leave the other's room keyed on the advertised id with nothing to notice."""
    src = API_CLIENT_CS.read_text(encoding="utf-8")
    assert src.count("RetainIssuedPair(room, response);") == 2


def test_the_changelog_scopes_the_line_to_the_room_the_seat_is_in():
    """The tombstone is one slot, so "in a room the ranked queue issued" is a
    guarantee wider than the mechanism: a superseded room that is not the slot
    holder falls back to the room's own resolver and can show a line the queue
    did not assign. The player-facing sentence has to say which room it is
    about."""
    changelog = (Path(__file__).parents[2] / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "In the room the ranked queue most recently issued" in changelog
    assert "In a room the ranked queue issued, the line waits" not in changelog
    assert "the room you are actually sitting in keeps that" in changelog
