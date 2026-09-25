"""The claims the round-3 lens found untrue, pinned so they stay true.

Same family as test_client_r2_claims.py, and the same reason for existing: a
sentence that describes a mechanism the code does not have is worse than no
sentence, because the next reader reasons from it. Three of the four MEDIUMs
in this round were exactly that -- and two of them were sentences the round's
OWN commits left standing over code they had just changed, which is the
failure mode this file exists to catch.

Where a claim has behaviour behind it, the behaviour is asserted first and the
prose second. Where a claim is only prose -- a residual, a bound -- the test
asserts the corrected wording AND the code term the wording names, so that a
rewrite which drops the mechanism reds even if it keeps the paragraph.
"""
import io
import os
import re
from pathlib import Path

from _cs_structure import code_of, cs_block, mask_code

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PLUGIN = Path(REPO) / "plugin"


def _read(*parts):
    with io.open(os.path.join(REPO, *parts), encoding="utf-8") as fh:
        return fh.read()


def _doc_before(src, signature):
    """The /// block immediately above `signature`, as text.

    Taken by walking BACK from the declaration over consecutive /// lines, so
    it cannot pick up a comment that merely sits somewhere else in the file --
    which is the whole point when the finding is "the doc attached to X says Y".
    """
    i = src.index(signature)
    lines = src[:i].splitlines()
    doc = []
    for line in reversed(lines):
        s = line.strip()
        if s.startswith("///"):
            doc.append(s)
            continue
        if s == "":
            continue
        break
    return "\n".join(reversed(doc))


# ── r3 lens MEDIUM 1: the union's doc claimed a bound the fix deleted ─────

def test_the_union_does_not_claim_a_bound_its_only_feeder_stopped_providing():
    """It said "the union only ever accumulates Steam IDs that ActiveFighters()
    returned -- i.e. seats already admitted by this room's own rules". The
    commit that wrote its only production feeder had just removed exactly that
    filtering: RefreezeFighterRosterForGameFromRoom feeds from RawActorCensus,
    which applies neither the roster test nor the latch test.

    The danger is specific and was stated by the lens: a maintainer reading
    that sentence concludes the narrowing in UnionCensus is redundant
    belt-and-braces and deletes it.
    """
    src = _read("plugin", "RoomActors.cs")
    doc = _doc_before(src, "internal static void UnionFighterRoster(")

    # The false bound is gone as a CLAIM. The sentence itself is quoted inside
    # the correction, so "the words are absent" is the wrong test -- "the words
    # are not asserted" is the right one, and that means the retraction has to
    # come FIRST.
    if "the union only ever accumulates" in doc:
        assert "used to read" in doc[:doc.index("the union only ever accumulates")], (
            "the ActiveFighters bound is stated as current rather than retracted")
    assert "RawActorCensus" in doc, (
        "the doc does not name the census its feeder actually uses")
    assert "UnionCensus" in doc, (
        "the doc does not name where the real narrowing lives")
    assert "belt-and-braces" in doc or "not redundant" in doc.lower(), (
        "nothing warns the next reader off deleting the narrowing")

    # And the mechanism the doc now names is really the one in the tree.
    feeder = code_of(PLUGIN / "RoomActors.cs",
                     "internal static List<string> RefreezeFighterRosterForGameFromRoom()")
    assert "RawActorCensus()" in feeder and "RosterCensusRules.UnionCensus(" in feeder, (
        "the feeder no longer matches the doc that was corrected to describe it")


# ── r3 lens MEDIUM 3: the discriminator's justification named one case ────

def test_the_census_states_every_reason_a_seat_can_be_off_the_roster():
    """The class comment justified "was it in the room at the assembly instant"
    only for the benign case (mid-load, u_id not yet delivered, a slow rejoin),
    and its stated residual covered only the post-freeze late entrant. An actor
    that was in the room at that instant WITHOUT belonging to the lobby is
    indistinguishable from the benign case and is admitted one game later.

    That is sound -- it is the same authority the freeze itself has -- but it
    has to be written down, because the reader who needs it is the one deciding
    whether the client can be trusted about lobby membership. It cannot: the
    server holds that fact.
    """
    src = _read("plugin", "RosterCensusRules.cs")
    head = src[:src.index("internal static class RosterCensusRules")]
    # Prose wraps, so the sentences are matched on the unwrapped text: a line
    # break in the middle of a claim must not make the claim unfindable.
    flat = " ".join(head.replace("///", " ").split())

    for term in ("spectator", "impostor", "unreadable", "latched"):
        assert term in flat.lower(), (
            "the enumeration does not cover the %r case" % term)
    assert "LOBBY MEMBERSHIP IS NOT A FACT THIS CENSUS HAS" in flat, (
        "the comment still implies the census can tell a lobby member from a "
        "seat that merely had the room name")
    # The residual names the CONSEQUENCE, not just the gap: a refused report.
    assert "refused report, not a settled wrong one" in flat, (
        "the residual does not say which direction it fails in")


def test_the_narrowing_is_marked_as_load_bearing_where_it_is_written():
    """The deletion the lens described happens in UnionCensus, so the warning
    has to be there too -- not only in the caller's doc."""
    src = _read("plugin", "RosterCensusRules.cs")
    doc = _doc_before(src, "internal static List<string> UnionCensus(")
    assert "NOT BELT-AND-BRACES" in doc.upper(), (
        "nothing at the narrowing says it is load-bearing")
    body = code_of(PLUGIN / "RosterCensusRules.cs",
                   "internal static List<string> UnionCensus(IList<Actor> raw,")
    # the two terms the finding is about, still doing the narrowing
    assert "wasAtAssembly" in body and "onRoster" in body, (
        "the narrowing the doc defends is gone")
    assert "if (!onRoster && !wasAtAssembly) continue;" in " ".join(body.split()), (
        "the narrowing no longer refuses an actor that is neither")


# ── the assembly window, which the discriminator's soundness rests on ─────

def test_the_assembly_window_is_taken_once_per_room():
    """The widening's whole discriminator is "was this actor here when the
    roster was taken". If a later freeze re-takes the window, that instant
    moves forward and every actor who joined in between becomes admissible --
    the late entrant the freeze exists to refuse. First window wins, and the
    decision is a rule the harness runs rather than an `if` here.
    """
    capture = code_of(PLUGIN / "RoomActors.cs",
                      "private static void CaptureAssemblyActors()")
    flat = " ".join(capture.split())
    assert "RosterCensusRules.ShouldCaptureAssembly(_assemblyCaptured)" in flat, (
        "the capture no longer asks the rule whether it may take a window")
    assert flat.index("ShouldCaptureAssembly") < flat.index("_assemblyActors.Clear()"), (
        "the window is cleared before the rule is asked, so a refusal still "
        "destroys the window it was refusing to replace")
    assert "_assemblyCaptured = true;" in flat, (
        "nothing records that a window was taken, so every freeze takes one")

    # The flag is room-scoped: cleared exactly where the set it describes is.
    src = _read("plugin", "RoomActors.cs")
    ensure = " ".join(code_of(PLUGIN / "RoomActors.cs",
                              "private static void EnsureCacheRoom()").split())
    reset = " ".join(code_of(PLUGIN / "RoomActors.cs",
                             "internal static void Reset()").split())
    for name, body in (("EnsureCacheRoom", ensure), ("Reset", reset)):
        assert "_assemblyActors.Clear();" in body and "_assemblyCaptured = false;" in body, (
            "%s clears the window without re-arming the flag, so a new room "
            "can never take one" % name)
    # ...and nowhere else, or "once per room" is a claim about one call site.
    # Three occurrences: the declaration's initialiser and the two clears.
    code = mask_code(src)
    assert "private static bool _assemblyCaptured = false;" in code, (
        "the flag's declaration moved, so the count below means something else")
    assert code.count("_assemblyCaptured = false;") == 3, (
        "the flag is cleared somewhere other than the two room-scoped sites")
    assert code.count("_assemblyCaptured = true;") == 1, (
        "a window is recorded as taken somewhere other than the capture")


def test_the_rule_reads_the_flag_and_not_the_emptiness_of_the_window():
    """A window taken in a room whose census read nothing is an EMPTY window
    that has still been taken. "Is the set empty" would invite a re-take in
    exactly the case where the first snapshot was thin."""
    rule = code_of(PLUGIN / "RosterCensusRules.cs",
                   "internal static bool ShouldCaptureAssembly(bool alreadyCaptured)")
    assert "return !alreadyCaptured;" in " ".join(rule.split())
    doc = _doc_before(_read("plugin", "RosterCensusRules.cs"),
                      "internal static bool ShouldCaptureAssembly(")
    assert "fail-OPEN" in doc or "fail-open" in doc, (
        "the doc does not say which direction re-taking fails in")


# ── r3 lens MEDIUM 2: 403 does not mean "captured for recovery" ───────────

def test_the_refusal_constant_does_not_promise_a_capture_the_server_may_not_make():
    """It asserted as fact that a 403 from the FFA endpoint is the answer to a
    key whose tail is not games_played + 1, and that "the report is refused and
    captured for recovery". The endpoint answers 403 to an unverifiable
    signature, to a player set that is not exactly the lobby's roster, to a
    player count that disagrees with the row and to a slot that disagrees with
    the ordering -- and capture is a property of some paths, not of the code.
    """
    src = _read("plugin", "FfaReportRules.cs")
    doc = _doc_before(src, "internal const long QuarantinedRefusalStatus = 403;")
    assert "WHAT THIS CODE DOES NOT MEAN" in doc, (
        "the correction is not stated where the false claim was")
    for cause in ("signature", "roster", "count", "slot"):
        assert cause in doc.lower(), (
            "the doc does not name the %r cause of a 403" % cause)
    assert "ParkRefusedReport" in doc, (
        "the doc does not point at the local copy that replaces the promised "
        "server-side one")
    # The behaviour the constant still governs is unchanged.
    terminal = " ".join(code_of(
        PLUGIN / "FfaReportRules.cs",
        "internal static bool IsTerminalRefusal(long statusCode)").split())
    assert "QuarantinedRefusalStatus" in terminal and "SettledRefusalStatus" in terminal
    assert "RetryableRefusalStatus" not in terminal, (
        "503 has been pulled into the terminal set")


def test_the_corrected_403_doc_does_not_put_the_game_number_behind_a_403():
    """The correction's own claim, pinned against the endpoint it describes.

    The retracted sentence said 403 was the answer to a key whose tail is not
    games_played + 1. The first rewrite of it kept that cause in the list while
    retracting it in the same breath -- the same defect one layer down, because
    this endpoint has no 403 keyed on the game number at all: a tail naming a
    game the lobby already recorded gets the idempotent replay echo, and a tail
    past the lobby's limit gets 409, the settled code this client already
    treats as terminal. So the doc is asserted NOT to name the tail among the
    403 causes, and the endpoint is READ to check that this stays true, rather
    than the doc being trusted about the far side.
    """
    doc = _doc_before(_read("plugin", "FfaReportRules.cs"),
                      "internal const long QuarantinedRefusalStatus = 403;")
    flat = " ".join(doc.replace("///", " ").split())
    assert "no 403 keyed on the game number" in flat, (
        "the doc no longer states the thing its retraction turns on")
    assert "game tail" not in flat, (
        "the doc has re-acquired the cause it retracts")

    main_py = _read("backend", "api", "main.py")
    i = main_py.index("async def submit_ffa_match(")
    j = main_py.index(chr(10) + "@app.", i)
    span = main_py[i:j]
    seen = span.split("HTTPException(403")
    assert len(seen) > 1, "no 403 in the endpoint at all -- wrong span"
    refusals = [piece.split(")")[0] for piece in seen[1:]]
    # The quarantine work merged from main for the v1.41.0 beta routes this
    # endpoint's terminal refusals through _ffa_record_and_refuse, whose status
    # defaults to 409 and is 403 only where a call passes status=403. Each call
    # is read whole: its arguments carry parentheses of their own, and every
    # call in this endpoint ends at the ")" that closes its last line.
    calls = []
    k = span.find("_ffa_record_and_refuse(")
    while k >= 0:
        calls.append(span[k:span.index(")" + chr(10), k) + 1])
        k = span.find("_ffa_record_and_refuse(", k + 1)
    refusals += [c for c in calls if "status=403" in c]
    for detail in refusals:
        for word in ("game limit", "duplicate", "games_played", "game number"):
            assert word not in detail.lower(), (
                "the endpoint now answers 403 to %r; the client doc says it "
                "does not" % word)
    # The limit refusal is the settled 409: the literal the lane's backend
    # raises, or main's one helper call that leaves the default status alone.
    if 'HTTPException(409, "Lobby game limit reached")' not in span:
        limit = [c for c in calls if 'detail="Lobby game limit reached"' in c]
        assert len(limit) == 1, (
            "the limit refusal is neither the literal 409 nor one refusal-helper call")
        assert "status=" not in limit[0], (
            "the limit refusal overrides the helper's status: " + limit[0])
        helper = main_py[main_py.index("async def _ffa_record_and_refuse("):]
        assert "status: int = 409" in helper[:helper.index("):")], (
            "the refusal helper's default status is no longer the settled 409")
    assert "_ffa_replay_echo" in span, (
        "the idempotent echo the doc names is gone from the endpoint")


def test_a_terminally_refused_report_is_kept_by_the_seat_that_filed_it():
    """The behaviour half. The client stopped queueing 409/403 (correctly -- a
    resend is refused identically and a re-key is a second settlement), which
    left one warning line as the entire record of a game whose rating, XP, gold
    and wagers will never settle. Whether the server kept a copy is a property
    of that backend, so the seat keeps its own."""
    src = _read("plugin", "ApiClient.cs")
    # The park lives in the TERMINAL branch, not in the failure branch. The
    # span is the submit method's, so a call somewhere else in the file cannot
    # satisfy this.
    submit = code_of(PLUGIN / "ApiClient.cs", "public static void ReportFfaMatch(")
    terminal = submit[submit.index("IsTerminalRefusalResponse(resp)"):]
    terminal = terminal[:terminal.index("else")]
    assert "ParkRefusedReport(" in terminal, (
        "a terminal refusal leaves nothing but a log line")
    assert "EnqueueFailedReport(" not in terminal, (
        "the terminal branch queues a retry again")
    # ...and the retryable branch still queues, or "not queued" has become the
    # answer to every failure rather than to the terminal ones.
    retryable = submit[submit.index("IsTerminalRefusalResponse(resp)"):]
    retryable = retryable[retryable.index("else"):]
    assert "EnqueueFailedReport(" in retryable, (
        "a non-terminal failure stopped being queued")

    park = code_of(PLUGIN / "ApiClient.cs",
                   "internal static void ParkRefusedReport(string url, string json, string response)")
    flat = " ".join(park.split())
    assert "REFUSED_REPORTS_KEPT" in flat, "the parked file is unbounded"
    assert "kept.RemoveAt(0)" in flat, "the bound is declared and never applied"
    # An unreadable file is APPENDED to, never rewritten: rewriting would
    # destroy entries this code cannot even see, to enforce a bound that is
    # only diagnostic (#276 -- which direction does the unhandled case fail).
    assert "File.AppendAllText(RefusedReportsPath" in flat, (
        "an unreadable parked file is rewritten, so its contents are lost to "
        "the cap")
    # It is NOT a queue: every reference to the file lives in the park itself
    # or in the property that names it, so nothing in the send path can read
    # it back. Counted on masked code, so a comment naming it does not count.
    code = mask_code(src)
    assert code.count("RefusedReportsPath") == 5, (
        "the refused-report file is referenced outside the park and its own "
        "property -- found %d references" % code.count("RefusedReportsPath"))
    assert flat.count("RefusedReportsPath") == 4, (
        "the park's own references moved, so the count above no longer proves "
        "where they are")


def test_the_parked_file_is_named_apart_from_the_outbox():
    """Two files that mean opposite things must not be told apart by a comment.
    The outbox is "send this again"; the park is "this will never be sent"."""
    src = _read("plugin", "ApiClient.cs")
    assert '"CompetitiveRounds.pending-reports.jsonl"' in src
    assert '"CompetitiveRounds.refused-reports.jsonl"' in src


# ── r3 lens LOW: the consent's abort clause ──────────────────────────────

def test_the_consent_does_not_promise_that_turning_it_off_unsends_anything():
    """UnityWebRequest.Abort() tears down this end of a transfer. It cannot
    recall bytes the server has already read, and next to "Nothing is sent
    while this is off" the old clause read as a promise that withdrawing
    permission mid-transfer keeps the data off the server."""
    src = _read("plugin", "NativeUI.cs")
    caption = [l for l in src.splitlines()
               if "At most one upload every five minutes" in l]
    assert len(caption) == 1, "expected exactly one consent caption"
    caption = caption[0]
    assert "stops an upload that is already running" not in caption, (
        "the overstated clause is back")
    assert "Nothing new is sent while this is off" in caption, (
        "the caption no longer scopes its promise to what has not been sent")
    assert "cuts off an upload already in progress" in caption, (
        "the caption no longer says the off switch reaches a live upload")
    assert "already reached the server stays there" in caption, (
        "the caption does not say what an abort cannot undo")

    # The mechanism doc says the same thing at the mechanism.
    doc = _doc_before(_read("plugin", "ApiClient.cs"),
                      "private static IEnumerator PostRequestRaw(string url, byte[] bodyRaw,")
    assert "abortIf" in doc and "cannot recall bytes" in doc, (
        "the abort parameter does not state its own limit")


def test_every_locale_carries_the_corrected_caption():
    """The English string IS the catalogue key, so a reworded caption that was
    not re-keyed silently drops the line from every translation."""
    cat = _read("plugin", "I18nCatalogues.cs")
    assert cat.count("cuts off an upload already in progress") == 4, (
        "the caption was not re-keyed in all four bundled locales")
    assert "stops an upload that is already running" not in cat, (
        "a locale still carries the old key")
    source = _read("tools", "i18n_source.json")
    assert "cuts off an upload already in progress" in source, (
        "the extractor was not re-run, so the key set does not carry the "
        "caption the client will look up")


# ── r3 lens LOW: a param doc attached to a constant ───────────────────────

def test_the_post_helpers_parameter_docs_are_attached_to_the_method():
    """Inserting RequestCancelledMarker between the <param> block and
    PostRequestRaw left that block documenting a const, which is invalid and
    leaves the method's own parameters undocumented at the declaration."""
    src = _read("plugin", "ApiClient.cs")
    const_doc = _doc_before(src, "internal const string RequestCancelledMarker")
    assert "<param" not in const_doc, (
        "a <param> element is attached to a constant")
    assert "<summary>" in const_doc, "the constant lost its own summary"

    method_doc = _doc_before(src, "private static IEnumerator PostRequestRaw(string url, byte[] bodyRaw,")
    for name in ("sensitiveProbe", "abortIf"):
        assert ('<param name="%s">' % name) in method_doc, (
            "PostRequestRaw's %s is undocumented at its declaration" % name)


# ── r3 lens LOW: the rollover case could not fail ─────────────────────────

def test_the_report_number_snapshot_is_the_object_the_harness_runs():
    """The executed case for the r2 HIGH compared ReportRoomId(room, 7) with
    ReportRoomId(room, 7). The defect lives in WHERE the number comes from, so
    the snapshot itself is now a rule object: production holds it, the harness
    drives it, and a second freeze after a rollover cannot move a key already
    taken."""
    ffa = _read("plugin", "FfaMode.cs")
    assert "FfaReportRules.GameKeySnapshot" in ffa, (
        "FfaMode keeps its own int again, so no executed case can observe the "
        "freeze")
    freeze = " ".join(code_of(PLUGIN / "FfaMode.cs",
                              "internal static int FreezeReportGameNumber()").split())
    assert "_reportGame.Freeze(PublishedGameNumber())" in freeze, (
        "the freeze no longer goes through the snapshot object")
    clear = " ".join(code_of(PLUGIN / "FfaMode.cs",
                             "internal static void ClearReportGameNumber()").split())
    assert "_reportGame.Clear()" in clear

    snap = code_of(PLUGIN / "FfaReportRules.cs",
                   "internal int Freeze(int publishedNow)")
    flat = " ".join(snap.split())
    assert "if (_frozen >= 0) return _frozen;" in flat, (
        "first-write-wins is gone: a second freeze after the host rolls over "
        "would move a key that has already been taken")
    assert "if (publishedNow >= 0) _frozen = publishedNow;" in flat, (
        "an unreadable number is being stored as if it were one")
