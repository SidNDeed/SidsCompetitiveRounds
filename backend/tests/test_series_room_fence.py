"""An observation is filed against the series for THIS room.

A queue-staged `ActiveRankedSeriesId` survives a failed join into a later room
-- that is documented at the staging site and on `ActiveRankedSeriesRoom`, and
it is why `SeriesIdForThisRoom()` exists. Ranked room NAMES are reused, so a
seat that failed into series S and then plays a different opponent in a room of
the same name still holds S. Any consumer that files an observation against a
specific series therefore has to ask which room the id was published for, not
merely whether an id exists.

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

def test_the_strict_fence_needs_the_room_and_an_exact_name():
    body = _cs_method_body(API_CLIENT_CS, "public static string SeriesIdForThisRoom()")
    assert 'if (!PhotonNetwork.InRoom) return "";' in body, (
        "outside a room there is no room to have been published for"
    )
    assert "StringComparison.Ordinal" in body, (
        "room names are compared exactly, not case- or culture-folded"
    )
    assert ('return string.Equals(ActiveRankedSeriesRoom, here, '
            'StringComparison.Ordinal) ? sid : "";') in body


def test_the_weak_question_is_false_when_there_is_nothing_to_compare():
    """This is the whole reason it is a second method. A consumer that runs
    after the room has closed must not read "no room" as "wrong room" -- that
    would drop a genuinely ranked game to casual, which is a worse error than
    the one the fence exists to prevent."""
    body = _cs_method_body(
        API_CLIENT_CS, "public static bool ActiveSeriesContradictedByRoom()")
    assert "if (!PhotonNetwork.InRoom) return false;" in body
    assert "if (string.IsNullOrEmpty(ActiveRankedSeriesId)) return false;" in body
    assert "if (string.IsNullOrEmpty(here)) return false;" in body
    assert ("return !string.Equals(ActiveRankedSeriesRoom, here, "
            "StringComparison.Ordinal);") in body
    assert "catch { return false; }" in body, "a throw is not evidence of a wrong room"
    # every early exit is false: the method only ever answers true from the
    # comparison itself
    assert body.count("return true") == 0


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
