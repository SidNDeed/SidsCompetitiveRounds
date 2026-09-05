"""An observation is filed against the series for THIS room.

A queue-staged `ActiveRankedSeriesId` survives a failed join into a later room
-- that is documented at the staging site and on the binding record, and it is
why `SeriesIdForThisRoom()` exists. Ranked room NAMES are reused, so a seat that
failed into series S and then plays a different opponent in a room of the same
name still holds S. Any consumer that files an observation against a specific
series therefore has to ask which room the id was published for, not merely
whether an id exists.

AND ASKING FOR THE NAME IS NOT ASKING FOR THE ROOM (r13 HIGH). The paragraph
above describes the hazard exactly and the fence did not close it: it compared
the room's NAME, which is the one thing the two occupancies share. The binding
is now the occupancy -- H2HRules.RoomBoundSeries, stamped by the join that
matched it and retired by any later join, the same rule the queue's pairing
record has followed since r8. The rules themselves live in H2HRules so they run
under the self-test harness; this file gates the wiring around them.

Two questions, deliberately different, because the right one depends on whether
the consumer still has a room to compare against:

  * `SeriesIdForThisRoom()` -- strict. Answers "" unless this seat is in the
    room the id was published for. For anything that WRITES against a series id.
  * `ActiveSeriesContradictedByRoom()` -- weak, and has an answer in both
    states. Answers only "are we in a room this id was NOT published for". For a
    consumer that would be made WORSE by a strict "": the report route can run
    after the room has closed, and an empty answer there would drop a genuinely
    ranked game to casual.

The 2v2 live-points channel has been room-gated since review r1 find 5. This
file is the 1v1 side of the same rule, plus a sweep (learning #432: a flag names
a line, the defect is a class) that keeps a new raw consumer from being added
without a decision.
"""

from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
API_CLIENT_CS = PLUGIN / "ApiClient.cs"
WATCHER_CS = PLUGIN / "GameStateWatcher.cs"
H2H_RULES_CS = PLUGIN / "H2HRules.cs"


def _cs_method_body(path, signature):
    """The braces-matched body of one C# method, so an assertion about a method
    cannot be satisfied by a match somewhere else in the file."""
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
                return src[open_brace:i + 1]
    raise AssertionError("unbalanced braces after " + signature)


# -- the two questions -------------------------------------------------------

def test_the_strict_fence_needs_the_room_and_the_occupancy_it_was_issued_for():
    """r13 HIGH moved the decision. A room NAME does not identify a room -- code
    rooms are player-typed and reusable, ranked names recur -- so "published for
    a room called this" let a pairing whose join failed leave its id standing
    for the next occupancy of that name, with a different opponent. The rule now
    names the occupancy (H2HRules.RoomBoundSeries), which is the distinction the
    pairing record beside it has drawn since r8.

    What this test can say is that the reader delegates, and hands the rule
    everything the rule needs to decide. What the rule ANSWERS is decided by
    H2HRules.SelfTest, which runs the cases rather than reading them."""
    body = _cs_method_body(API_CLIENT_CS, "public static string SeriesIdForThisRoom()")
    assert "H2HRules.SeriesForRoom(activeSeriesBinding" in body, (
        "the reader has to ask the rule, not compare a name of its own"
    )
    for handed in ("PhotonNetwork.InRoom", "RoomIncarnation", "OpponentInRoomOrEmpty()"):
        assert handed in body, f"the rule is not handed {handed}"
    assert 'catch { return ""; }' in body, "a throw must not become a named series"

    rules = H2H_RULES_CS.read_text(encoding="utf-8")
    assert "StringComparison.Ordinal" in rules, (
        "room names are compared exactly, not case- or culture-folded"
    )
    # ...and the record is CONSTRUCTED in exactly one place, which is now
    # inside the rules component rather than at the call site: publication is
    # a transition (H2HRules.PublishSeries) and not a struct the caller
    # assembles, so the stamp cannot be decided by whoever is publishing.
    api = API_CLIENT_CS.read_text(encoding="utf-8")
    assert rules.count("bound = new RoomBoundSeries") == 1, (
        "the record is built somewhere other than the publication transition"
    )
    assert api.count("H2HRules.PublishSeries(ref activeSeriesBinding") == 1, (
        "a second publish site would answer for a series without going through "
        "the transition that decides the stamp"
    )
    # The id is DERIVED from the record and no longer stored beside it (r14
    # HIGH: a retirement nulled the binding and the field kept the id). A
    # get-only property is a stronger statement than any count of write sites:
    # there is nothing to count, and a new assignment would not compile.
    _decl = api.index("public static string ActiveRankedSeriesId")
    _window = api[_decl:_decl + 400]
    assert "get { return activeSeriesBinding.HasValue" in _window, (
        "the id is a stored field again; it can now disagree with its binding"
    )
    assert "set;" not in _window, "the id gained a setter"


def test_the_weak_question_is_false_when_there_is_nothing_to_compare():
    """This is the whole reason it is a second method. A consumer that runs
    after the room has closed must not read "no room" as "wrong room" -- that
    would drop a genuinely ranked game to casual, which is a worse error than
    the one the fence exists to prevent."""
    body = _cs_method_body(
        API_CLIENT_CS, "public static bool ActiveSeriesContradictedByRoom()")
    assert "H2HRules.SeriesContradictedByRoom(activeSeriesBinding" in body
    assert "catch { return false; }" in body, "a throw is not evidence of a wrong room"
    assert body.count("return true") == 0, (
        "the reader answers true only through the rule"
    )

    # The rule keeps the polarity: every one of its exits for "nothing to
    # compare" is false, and it says true only from evidence.
    rule = _cs_method_body(
        H2H_RULES_CS,
        "internal static bool SeriesContradictedByRoom(RoomBoundSeries? bound, bool inRoom, string roomHere,")
    assert "if (bound == null) return false;" in rule
    assert "if (!inRoom) return false;" in rule
    assert "if (string.IsNullOrEmpty(roomHere)) return false;" in rule
    assert "if (string.IsNullOrEmpty(b.SeriesId)) return false;" in rule

    # ...with one exception, and it is r13 HIGH's other half. A leave that
    # produced no OnLeftRoom leaves this seat believing it is nowhere, and the
    # old rule read that as "nothing to compare against" and kept the id. A
    # join stamp that no longer matches the current incarnation is evidence on
    # its own, so it is asked BEFORE the in-room question.
    assert rule.index("b.JoinIncarnation != incarnation") < rule.index("if (!inRoom) return false;"), (
        "the stale-occupancy evidence is behind the fail-open it exists to close"
    )


# -- the consumers -----------------------------------------------------------

def test_live_points_are_filed_against_this_rooms_series():
    body = _cs_method_body(WATCHER_CS, "private static void MaybeSendLivePoints()")
    assert "ApiClient.SeriesIdForThisRoom()" in body
    assert "ApiClient.PostLivePoints(liveSeriesId, LocalSteamId, sp1, sp2);" in body
    assert "PostLivePoints(ApiClient.ActiveRankedSeriesId" not in body, (
        "the raw field must not reach the 1v1 live-points channel"
    )
    # the 1v1 branch is gated on the fenced id, not on the raw one
    assert "if (matchIsRanked && !string.IsNullOrEmpty(liveSeriesId)" in body
    # and the 2v2 branch keeps its own room gate (r1 find 5)
    assert 'rp.ContainsKey("cr_ff")' in body


def test_the_attestations_source_reference_is_this_rooms_series():
    """An attestation describes THIS room -- it carries this room's region and
    this seat's actor number -- so the series it names has to be the one
    published for this room. Empty is already a legal sourceRef for the other
    modes."""
    src = WATCHER_CS.read_text(encoding="utf-8")
    assert 'mode == "1v1" ? ApiClient.SeriesIdForThisRoom()' in src
    assert 'mode == "1v1" ? (ApiClient.ActiveRankedSeriesId ?? "")' not in src


def test_the_ranked_upgrade_refuses_an_id_from_another_room():
    src = WATCHER_CS.read_text(encoding="utf-8")
    marker = "[REPORT-ROUTE] forcing isRanked=true"
    upgrade = src[src.index(marker) - 1200:src.index(marker)]
    assert "&& !ApiClient.ActiveSeriesContradictedByRoom()" in upgrade
    # ...and NOT the strict fence, which would answer "" after the room closed
    assert "SeriesIdForThisRoom" not in upgrade


# -- the sweep ---------------------------------------------------------------

# Every read of the raw field outside ApiClient.cs, and what makes it safe. A
# read that is none of these is a new consumer that has not been decided about
# -- which is the state this file exists to make loud.
ALLOWED_RAW_READS = (
    # cleared: a write, not a read
    "ApiClient.ActiveRankedSeriesId = null;",
    # an ABSENCE gate. A stale non-empty id makes these stricter, never looser:
    # they act only when there is no id at all.
    "string.IsNullOrEmpty(ApiClient.ActiveRankedSeriesId)",
    # EscLeaveRow's display key. The key already carries the room name and the
    # room generation, so a stale id cannot make one room's row match another's,
    # and nothing is filed against it.
    'ctxId = ApiClient.ActiveRankedSeriesId ?? "";',
    # the upgrade's own log line, beneath the contradiction guard above it
    "live series {ApiClient.ActiveRankedSeriesId} exists for this pairing",
)


def test_no_undecided_consumer_of_the_raw_series_id():
    offenders = []
    for path in sorted(PLUGIN.glob("*.cs")):
        if path.name == "ApiClient.cs":
            continue  # the field's own file: declaration, publish, clear
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "ApiClient.ActiveRankedSeriesId" not in line:
                continue
            if line.strip().startswith("//"):
                continue
            if any(a in line for a in ALLOWED_RAW_READS):
                continue
            offenders.append("%s:%d: %s" % (path.name, n, line.strip()))
    assert offenders == [], (
        "a raw ActiveRankedSeriesId consumer with no room fence and no reason:\n"
        + "\n".join(offenders)
    )


def test_the_sweep_can_actually_fail():
    """Negative control for the sweep: the allowlist must not be so broad that a
    plainly wrong consumer passes it."""
    bad = "    ApiClient.PostLivePoints(ApiClient.ActiveRankedSeriesId, sid, 1, 1);"
    assert not any(a in bad for a in ALLOWED_RAW_READS)
    assert "ApiClient.ActiveRankedSeriesId" in bad
    assert not bad.strip().startswith("//")
