"""The CLIENT half of the opt-in automatic log upload (v1.41.0 item a).

`test_auto_logs.py` drives the server route. Nothing drove the client, and the
client is where the two defects a passive tester meets actually live:

* THE GAME THREAD. The room-exit handler used to read three log files whole,
  run five string passes over the result and JSON-escape up to 3.5 M characters
  inline, so leaving a room froze the game for as long as that took -- seconds,
  for a player whose LogOutput.log has grown to tens of megabytes. The gates
  below pin the split: the handler captures and hands off, a background thread
  composes, and the main thread only starts the request.

* THE CONSENT. The caption is a fixed-height label in a layout that TRUNCATES,
  so a disclosure longer than one line lost its tail in game, and it named the
  log while the POST also carried identity and match fields. The gate here
  derives the field list from `ApiClient.BuildAutoLogBody` itself, so adding a
  field to that body fails this test until the caption names it.

Everything is decided on `_cs_structure`'s mask, so a needle inside a comment,
a string or an inactive `#if` branch is not structure (#342/#431/#441). Where a
gate could pass for the wrong reason the control that reds it is named on the
assertion.
"""
from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path

import pytest

from _cs_structure import (CsParseError, cs_block, code_of, initialiser,
                           mask_code, strip_comments_only)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PLUGIN = REPO / "plugin"

AUTO_LOG = PLUGIN / "AutoLogUpload.cs"
API_CLIENT = PLUGIN / "ApiClient.cs"
COMPETITIVE_UI = PLUGIN / "CompetitiveUI.cs"
NATIVE_UI = PLUGIN / "NativeUI.cs"
NATIVE_UI_SETTINGS = PLUGIN / "NativeUI.Settings.cs"
LOG_SCRUB = PLUGIN / "LogScrub.cs"
CATALOGUES = PLUGIN / "I18nCatalogues.cs"

ON_ROOM_LEFT = "OnRoomLeft()"
COMPOSE = "ComposeLogBundle(LogBundleInputs inputs, LogBundleCore.ComposeInfo info)"
READ_TAIL = "ReadLogTail(string path, int maxChars = BUG_REPORT_LOG_CAP_CHARS)"
LOG_BUNDLE_CORE = PLUGIN / "LogBundleCore.cs"
SUBMIT_FORM = "SubmitBugReportNow()"
PUMP_FORM = "PumpBugFormBundle()"

LOCALES = ("es", "ru", "uk", "sv")


# ── the game thread ──────────────────────────────────────────────────────

# Anything whose cost scales with the size of a log file. None of these may be
# reached from the room-exit handler or the bug form's main-thread halves.
EXPENSIVE = (
    "CompetitiveUI.BuildLogBundle(",
    "CompetitiveUI.ComposeLogBundle(",
    "ComposeLogBundle(",
    "LogBundleCore.Compose(",
    "LogBundleCore.ReadCapped(",
    "ApiClient.ReadLogTail(",
    "ApiClient.BuildAutoLogBody(",
    "ApiClient.BuildBugReportBody(",
    "ApiClient.SubmitAutoLog(",
    "ApiClient.SubmitBugReport(",
    "Encoding.UTF8.GetBytes(",
)


def test_the_room_exit_handler_does_no_log_work_on_the_game_thread():
    # Control: put `CompetitiveUI.ComposeLogBundle(inputs, info);` back into
    # OnRoomLeft -> red.
    block = mask_code(cs_block(AUTO_LOG, ON_ROOM_LEFT))
    found = [needle for needle in EXPENSIVE if needle in block]
    assert not found, (
        "the room-exit handler reaches work proportional to the log: %r. That "
        "is the game thread; the bundle belongs on the worker." % found)
    # ...and it positively DOES hand off, so "found nothing" cannot mean "the
    # feature was deleted" (#438 -- acceptance is a positive signal).
    assert "CompetitiveUI.CaptureLogBundleInputs(" in block
    assert "StartBundleWorker(" in block


def _job_delegate(source: Path, start_needle: str, end_needle: str) -> str:
    """The work delegate handed to an OffMainJob's Start, on the mask.

    Sliced rather than parsed: it is an anonymous method, so it has no
    signature `cs_block` could find. The window ends where the error
    delegate (the Start call's last argument) begins.
    """
    masked = mask_code(source.read_text(encoding="utf-8"))
    start = masked.find(start_needle)
    assert start != -1, "no %s in %s" % (start_needle, source.name)
    assert masked.find(start_needle, start + 1) == -1, \
        "more than one %s in %s" % (start_needle, source.name)
    end = masked.find(end_needle, start)
    assert end != -1, "the job start in %s lost its error delegate" % source.name
    return masked[start:end]


def _auto_log_worker() -> str:
    return _job_delegate(AUTO_LOG, "_job.Start(", "ex => new BundleResult")


def _bug_form_worker() -> str:
    return _job_delegate(COMPETITIVE_UI, "_bugFormJob.Start(", "ex => new BugFormBundle")


def test_the_bundle_is_composed_on_a_background_thread():
    # One mechanism for both producers: LogBundleCore.OffMainJob starts the
    # only thread, and it is a background one. Control: delete either of
    # these -> red. IsBackground is not decoration: a foreground thread
    # mid-bundle holds the process open at quit.
    core = code_of(LOG_BUNDLE_CORE)
    assert core.count("new Thread(") == 1, "expected exactly one worker thread in the core"
    assert "IsBackground = true" in core
    for producer in (AUTO_LOG, COMPETITIVE_UI):
        assert "new Thread(" not in code_of(producer), (
            "%s starts its own thread beside the shared job" % producer.name)
    worker = _auto_log_worker()
    for needle in ("CompetitiveUI.ComposeLogBundle(", "ApiClient.BuildAutoLogBody(",
                   "Encoding.UTF8.GetBytes("):
        assert needle in worker, f"the auto-log worker does not do {needle} -- so something else does"
    form = _bug_form_worker()
    for needle in ("ComposeLogBundle(", "ApiClient.BuildBugReportBody(",
                   "Encoding.UTF8.GetBytes(", "ApiClient.SensitiveBodyProbe("):
        assert needle in form, f"the bug-form worker does not do {needle} -- so something else does"


def test_the_bug_form_does_no_log_work_on_the_game_thread():
    """Night of 2026-10-19: the form composed a 3.3 M-char bundle inline and
    held a live game's frame for 907 ms. Its main-thread halves are the
    submit handler OUTSIDE the worker delegate and the pump. Control: put
    `string b = ComposeLogBundle(inputs, new LogBundleCore.ComposeInfo());`
    before the job start in SubmitBugReportNow -> red."""
    submit = mask_code(cs_block(COMPETITIVE_UI, SUBMIT_FORM))
    worker = _bug_form_worker()
    at = submit.find(worker)
    assert at != -1, "the bug-form worker delegate is not inside SubmitBugReportNow"
    outside = submit[:at] + submit[at + len(worker):]
    found = [n for n in EXPENSIVE if n in outside]
    assert not found, "the bug form's main thread reaches %r" % found
    assert "CaptureLogBundleInputs(" in outside, "the form no longer captures on the main thread"
    pump = mask_code(cs_block(COMPETITIVE_UI, PUMP_FORM))
    found = [n for n in EXPENSIVE if n in pump]
    assert not found, "the bug form's pump reaches %r" % found
    assert "ApiClient.SubmitBugReportBody(" in pump, "the pump no longer hands the body to the request"
    # The synchronous producer is gone, not merely unused.
    assert "BuildLogBundle(" not in code_of(COMPETITIVE_UI)


def test_the_bug_form_pending_lifecycle_survives_reopen():
    """Every form lifecycle site drives the state exercised by the harness."""
    opened = mask_code(cs_block(COMPETITIVE_UI, "public static void OpenBugReportModal()"))
    assert "_bugSubmission.Reopen();" in opened
    assert not any(s in opened for s in (".Begin(", ".Answer(", ".BuildFailure("))
    ui = mask_code(COMPETITIVE_UI.read_text(encoding="utf-8"))
    assert "bugSubmitting" not in ui and "bugSubmitStatus" not in ui
    draw = mask_code(cs_block(COMPETITIVE_UI, "private static void DrawBugReportModal()"))
    assert "bool disabled = !_bugSubmission.CanSubmit ||" in draw
    assert "_bugSubmission.Status" in draw
    submit = mask_code(cs_block(COMPETITIVE_UI, "private static void SubmitBugReportNow()"))
    assert "if (!_bugSubmission.Begin(pendingStatus) || _bugFormJob.Busy) return;" in submit
    assert submit.index("_bugSubmission.Begin(") < submit.index("_bugFormJob.Start(")
    assert "FailBugReportBuild(" in submit
    pump = mask_code(cs_block(COMPETITIVE_UI, "internal static void PumpBugFormBundle()"))
    assert pump.count("FailBugReportBuild(") == 2
    assert "_bugSubmission.Answer(" not in pump
    assert pump.count("ApiClient.SubmitBugReportBody(") == 1
    answer = mask_code(cs_block(COMPETITIVE_UI, "private static void OnBugReportAnswer(bool ok, string resp)"))
    assert answer.count("_bugSubmission.Answer(") == 2
    failed = mask_code(cs_block(COMPETITIVE_UI, "private static void FailBugReportBuild(string reason)"))
    assert "_bugSubmission.BuildFailure(BugReportFailureStatus(reason));" in failed
    state = cs_block(LOG_BUNDLE_CORE, "internal sealed class PendingSubmission")
    reopen = mask_code(cs_block(state, "internal void Reopen()"))
    assert "if (_pending) return;" in reopen
    assert reopen.index("if (_pending) return;") < reopen.index("Status =")


def test_the_worker_writes_nothing_to_the_log_from_its_own_thread():
    # BepInEx's sinks are not documented thread-safe, and a line written from
    # here interleaves with the game's own. Every sentence the worker wants to
    # say travels back in the result.
    # Control: insert `Plugin.Log.LogInfo("x");` inside either delegate -> red.
    for worker in (_auto_log_worker(), _bug_form_worker()):
        assert "Plugin.Log" not in worker


def test_the_thread_safe_composer_touches_no_engine_api():
    # Control: add `Plugin.Log.LogInfo(diagnostic);` to ComposeLogBundle or
    # anywhere in LogBundleCore.cs -> red.
    forbidden = ("Plugin.Log", "AudioSelfCheck.", "Application.", "Time.",
                 "PhotonNetwork", "UnityEngine.", "I18n.")
    for name, body in (("ComposeLogBundle", mask_code(cs_block(COMPETITIVE_UI, COMPOSE))),
                       ("LogBundleCore.cs", code_of(LOG_BUNDLE_CORE))):
        hit = [n for n in forbidden if n in body]
        assert not hit, (
            "%s reaches %r. It runs on a worker thread; a Unity call there is a "
            "freeze at best and a throw at worst." % (name, hit))
    assert "LogBundleCore.Compose(" in mask_code(cs_block(COMPETITIVE_UI, COMPOSE))


def test_the_body_builder_takes_its_versions_as_parameters():
    """`Application.version` is a Unity read, so it cannot live in a body
    builder the worker calls. Control: replace the `gameVersion` parameter
    with a direct `UnityEngine.Application.version` read -> red."""
    for sig in ("BuildAutoLogBody(string steamId, string displayName,",
                "BuildBugReportBody(string steamId, string displayName,"):
        body = mask_code(cs_block(API_CLIENT, sig))
        assert "Application." not in body, sig
        assert "Plugin.ModVersion" not in body, sig


# ── the read is bounded before the file is read ──────────────────────────

def test_the_log_tail_seeks_before_it_reads():
    """A cap applied AFTER ReadToEnd is not a cap on the input: a 40 MB log
    still costs 40 MB of reading and decoding to keep 1.5 MB."""
    body = mask_code(cs_block(API_CLIENT, READ_TAIL))
    # Control: delete the `fs.Position = len - maxChars;` block -> red.
    assert "fs.Position = len - maxChars" in body, \
        "ReadLogTail does not seek to the tail; the whole file is still read"
    seek_at = body.index("fs.Position = len - maxChars")
    reader_at = body.index("new System.IO.StreamReader")
    assert seek_at < reader_at, \
        "the seek happens after the reader is constructed, which reads from 0"
    assert "fs.Length" in body


def test_the_log_tail_skips_a_partial_utf8_sequence():
    """A mid-file seek can land inside a multi-byte sequence. Control: delete
    the continuation-byte loop -> red."""
    body = mask_code(cs_block(API_CLIENT, READ_TAIL))
    assert "0xC0" in body and "0x80" in body


# ── the consent names what the POST carries ──────────────────────────────

def _settings_toggle_call(name: str):
    """(source-with-literals, masked) slices of the settings row constructor
    call whose element name is `name` -- since item 13 (the settings page
    reorganisation) a `SettingsSwitch` on the Privacy & account sub-tab, whose
    description argument is the caption.

    Two views of the SAME offsets: literals survive the first (that is how the
    element name is found and the caption read back), and are blanked in the
    second (that is what makes the paren walk safe -- this very caption
    contains a bracketed clause, and the callback body is full of semicolons).
    """
    src = NATIVE_UI.read_text(encoding="utf-8")
    with_literals = strip_comments_only(src)
    masked = mask_code(src)
    anchor = with_literals.find('SettingsSwitch(subPrivacy.transform, "%s"' % name)
    if anchor == -1:
        raise CsParseError("no SettingsSwitch call for %r" % name)
    depth, i = 0, masked.index("(", anchor)
    while i < len(masked):
        if masked[i] == "(":
            depth += 1
        elif masked[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    else:
        raise CsParseError("unterminated SettingsSwitch call for %r" % name)
    return with_literals[anchor:i], masked[anchor:i]


def _settings_toggle_literal(name: str) -> str:
    """The caption argument of that call."""
    call, _ = _settings_toggle_call(name)
    literals = re.findall(r'"((?:[^"\\]|\\.)*)"', call)
    # [0] is the element name; the caption is the longest literal in the call.
    caption = max(literals, key=len)
    if caption == name:
        raise CsParseError("no caption literal in the %r call" % name)
    return caption


def _auto_log_body_keys() -> set:
    """The JSON keys `ApiClient.BuildAutoLogBody` actually emits.

    Derived, never listed: a hand-written list is a check that cannot fail for
    the next field somebody adds to the body.
    """
    block = cs_block(API_CLIENT, "BuildAutoLogBody(string steamId, string displayName,")
    return set(re.findall(r'\\"(\w+)\\":', block))


# What the caption must SAY about each field. The keys of this map are pinned
# against the body above: a field added there and not here fails the first
# assertion, and a field named here that the caption does not mention fails the
# second. Neither can be satisfied by editing only one side.
DISCLOSED = {
    "steam_id": "your Steam ID",
    # NOT the bare word "name": "room name" contains it, so deleting the
    # personal-name disclosure entirely left this row green (r2 LOW). The
    # phrase here is the one that only the personal-name sentence can satisfy.
    "display_name": "your Steam ID and name",
    # SINGULAR. BuildAutoLogBody emits at most one optional opponent id, so a
    # caption promising "the other players' Steam IDs" disclosed a field that
    # does not exist while under-describing the one that does.
    "opponent_steam_id": "your opponent's Steam ID",
    "room_name": "the room name",
    "series_id": "the series ID",
    "mode": "the game mode",
    "mod_version": "the mod and game version",
    "game_version": "the mod and game version",
    "log_text": "logs",
}


def test_the_consent_lists_every_field_the_upload_sends():
    emitted = _auto_log_body_keys()
    assert emitted, "the body-key reader found nothing -- it stopped measuring"
    undisclosed = sorted(emitted - set(DISCLOSED))
    assert not undisclosed, (
        "POST /api/v1/logs/auto carries %r, and the consent caption has no "
        "sentence for them. Name them in the caption and add them here, or "
        "stop sending them." % undisclosed)

    caption = _settings_toggle_literal("SAutoLog")
    # Control: delete "the series ID" from the caption -> red.
    missing = sorted({DISCLOSED[k] for k in emitted if DISCLOSED[k] not in caption})
    assert not missing, "the consent caption does not mention %r" % missing


def test_the_consent_states_the_scrub_it_actually_gets():
    """The caption's three claims, each against the code that implements it.

    An overstated scrub is the failure this replaces: "local paths are removed"
    read as "every local path", which was never what the passes do.
    """
    caption = _settings_toggle_literal("SAutoLog")
    assert "Users folder" in caption, "the caption no longer names the Users-prefix rule"
    assert "profile folder" in caption, "the caption no longer names the profile-directory rule"
    # Control: change MinBareNameLength to 2 without touching the caption -> red.
    floor = int(initialiser(LOG_SCRUB, "internal static class LogScrub", "MinBareNameLength"))
    words = {2: "two", 3: "three", 4: "four"}
    assert words[floor] + " characters" in caption, (
        "the bare-name floor is %d but the caption does not say so" % floor)


def test_the_consent_promises_one_opponent_id_because_one_is_what_is_sent():
    """The body carries `opponent_steam_id` at most once, and only when the
    game had one. A plural promise is a disclosure of a field that is not
    there -- and it reads as "everyone in the room", which for FFA is the one
    place a reader would most want it to be true."""
    caption = _settings_toggle_literal("SAutoLog")
    for plural in ("opponents' Steam IDs", "the other players' Steam IDs",
                   "opponent Steam IDs", "Steam IDs of everyone"):
        assert plural not in caption, (
            "the caption promises plural opponent IDs: %r" % plural)
    block = cs_block(API_CLIENT, "BuildAutoLogBody(string steamId, string displayName,")
    assert block.count('opponent_steam_id') == 1, (
        "the body emits the opponent id %d times; the caption describes one"
        % block.count('opponent_steam_id'))
    # ...and it is optional, which the caption says with "when the game had one".
    assert "when the game had one" in caption, (
        "the caption no longer says the opponent id is conditional")


def test_the_path_claim_covers_every_separator_the_scrub_actually_handles():
    """The caption says "however the slashes are written". That is a claim
    about the PASSES, not about one of them: a Windows log carries `C:\\Users\\`,
    a Unity log carries `C:/Users/`, an escaped JSON payload carries `C:\\\\Users\\\\`
    and a URL-encoded one carries `%5CUsers%5C`. Before this round the pattern
    was a single hard-coded backslash form and the other three survived.
    """
    caption = _settings_toggle_literal("SAutoLog")
    assert "however the slashes are written" in caption, (
        "the caption no longer claims separator-independence")
    src = LOG_SCRUB.read_text(encoding="utf-8")
    forms = initialiser(LOG_SCRUB, "internal static class LogScrub", "SepForms")
    for sep in ("\\\\\\\\", "/", "%5C"):
        assert sep in forms, "the separator set does not carry %r: %s" % (sep, forms)
    body = code_of(LOG_SCRUB)
    assert "SepAny" in body, "the passes no longer share one separator alternation"
    # Both path passes read it -- a pass that kept a literal separator is the
    # half the claim would be false about.
    users = initialiser(LOG_SCRUB, "internal static class LogScrub", "UsersDirPattern")
    assert "SepAny" in users, "the Users pass hard-codes its separator: " + users
    profile = code_of(LOG_SCRUB, "private static Regex ProfilePattern(string profile)")
    assert "SepAny" in profile, "the profile pass hard-codes its separator: " + profile


def test_the_caption_does_not_promise_the_narrow_pass_removes_more():
    """The bare-name pass is deliberately NARROW: it removes the account name
    only where it stands alone. `/name/`, `\\name\\` and `name@example` used to
    satisfy the boundaries, which contradicted the caption in the safe
    direction for privacy and the unsafe one for truth -- a reader cannot tell
    which claims to trust once one is wrong.

    The caption now names the two cases that survive, and the boundary
    excludes exactly the characters that make them survive.
    """
    caption = _settings_toggle_literal("SAutoLog")
    assert "e-mail address" in caption, (
        "the caption no longer says an address is left alone")
    assert "path we did not recognise" in caption, (
        "the caption no longer says an unrecognised path is left alone")
    before = initialiser(LOG_SCRUB, "internal static class LogScrub", "NameBoundaryBefore")
    after = initialiser(LOG_SCRUB, "internal static class LogScrub", "NameBoundaryAfter")
    for name, expr in (("before", before), ("after", after)):
        for ch, why in (("/", "a forward-slash path segment"),
                        ("@", "an e-mail local part"),
                        ("%", "a percent-encoded separator")):
            assert ch in expr, (
                "the %s boundary admits %s: %s" % (name, why, expr))


def test_turning_the_setting_off_stops_a_transfer_already_running():
    """"Nothing is sent while this is off" was false for the one upload in
    flight when it was switched off: the flag was read at dispatch and never
    again, so a bundle already on the wire finished and was accepted.

    Three pieces, one assertion each: the uploader hands the request a live
    predicate, the request layer polls it and ABORTS, and the completion path
    tells a cancellation apart from a failure so a cancelled upload leaves no
    debounce and no content hash behind (which would suppress the retry the
    player is entitled to after turning it back on).
    """
    caption = _settings_toggle_literal("SAutoLog")
    assert "cuts off an upload already in progress" in caption, (
        "the caption no longer claims cancellation")
    # ...and claims only what an abort can give. Abort() tears down this end of
    # the transfer; it cannot recall bytes the server has already read, and the
    # clause used to sit beside "Nothing is sent while this is off" in a way
    # that read as a promise that it could (r3 lens LOW).
    assert "already reached the server stays there" in caption, (
        "the caption promises a cancellation stronger than Abort() gives")

    # The live predicate asks BOTH switches (round 2 finding 4): the setting
    # alone let an upload outlive a revoked data consent. It reads them
    # through the same two delegates as the dispatch gates, and those default
    # to the real setting and consent. A shape pin only: the consent sentinel
    # (AutoLogUpload.RunConsentSentinel) is what runs the predicate.
    upload = code_of(AUTO_LOG.read_text(encoding="utf-8"))
    assert upload.count("abortIf: () => !_enabledNow() || !_consentNow()") == 1, (
        "the uploader does not hand the request a live predicate over both switches")
    assert "_enabledNow = () => Enabled;" in upload and \
        "_consentNow = () => Plugin.DataConsentGranted;" in upload, (
        "the switch delegates no longer default to the real setting and consent")
    assert upload.count('if (!_consentNow()) { NoteSkip("data reporting is not consented"); return; }') == 2, (
        "a dispatch gate no longer reads the consent delegate the in-flight check reads")
    assert "Plugin.DataConsentGranted" not in upload.replace(
        "_consentNow = () => Plugin.DataConsentGranted;", "").replace(
        "realConsent() != Plugin.DataConsentGranted", ""), (
        "a consent read bypasses the delegate the in-flight check reads")

    raw = code_of(API_CLIENT.read_text(encoding="utf-8"),
                  "private static IEnumerator PostRequestRaw(string url, byte[] bodyRaw,")
    assert "abortIf" in raw and "request.Abort()" in raw, (
        "the request layer never aborts: " + raw[:300])
    assert "RequestCancelledMarker" in raw, (
        "an aborted request is not distinguishable from a failed one")

    marker = initialiser(API_CLIENT, "public static class ApiClient",
                         "RequestCancelledMarker")
    assert marker.strip('"'), "the cancellation marker is empty"
    body = code_of(AUTO_LOG.read_text(encoding="utf-8"))
    assert "ApiClient.RequestCancelledMarker" in body, (
        "the upload callback does not recognise a cancellation")
    # The cancellation branch must return BEFORE the debounce/hash writes.
    # code_of masks comments to blanks, so collapse first and then measure.
    tail = " ".join(body.split("ApiClient.RequestCancelledMarker", 1)[1].split())
    assert "return;" in tail, "the cancellation branch does not return"
    assert tail.index("return;") < 400, (
        "a cancelled upload still falls through to the debounce: " + tail[:300])
    for after in ("_lastUploadAt", "_lastHash"):
        assert after not in tail[:tail.index("return;")], (
            "a cancelled upload writes %s before it returns, which suppresses "
            "the retry the player is entitled to" % after)


def test_an_aborted_send_takes_back_its_heartbeat_mark():
    """Round 3 finding 20. A send this client aborts itself (abortIf) was
    never a question put to the server, so it must leave ApiLooksDown as it
    found it. The abort used to call NoteResult(false, 0), which records
    nothing; the false outage came from the attempt mark the send had
    already set. The abort now puts that mark back through
    WithdrawApiAttempt, guarded so that a LATER attempt keeps its own mark.
    A shape pin only: the in-game [HEARTBEAT-ABORT-SENTINEL] and the
    round-3 harness run the abort itself.

    MUTATION: put NoteResult(false, 0) back in place of the withdrawal, or
    drop the serial guard. Must fail."""
    src = API_CLIENT.read_text(encoding="utf-8")
    raw = " ".join(code_of(
        src, "private static IEnumerator PostRequestRaw(string url, byte[] bodyRaw,").split())
    assert raw.count("var attemptMark = MarkApiAttempt();") == 1, (
        "the cancellable send no longer keeps the mark it replaced: " + raw[:300])
    assert "NoteAttempt()" not in raw, (
        "the send marks an attempt it cannot take back: " + raw[:300])
    assert raw.count("if (aborted)") == 1, raw[:300]
    abort = raw.split("if (aborted)", 1)[1]
    abort = abort[:abort.index("yield break;")]
    assert abort.count("WithdrawApiAttempt(attemptMark);") == 1, (
        "the abort does not take back its attempt mark: " + abort)
    assert "NoteResult(" not in abort, (
        "the abort reports a result the server never gave: " + abort)
    withdraw = " ".join(code_of(
        src, "private static void WithdrawApiAttempt(ApiAttemptMark mark)").split())
    assert "if (mark.Serial == _apiAttemptSerial) LastApiAttemptAt = mark.Before;" in withdraw, (
        "the withdrawal can erase a later attempt's mark: " + withdraw)
    note = " ".join(code_of(src, "private static void NoteAttempt()").split())
    assert "_apiAttemptSerial++" in note, (
        "an attempt no longer moves the serial the withdrawal is guarded by: " + note)


def test_the_bare_name_pass_does_not_eat_identifiers():
    """`_`, `.` and `-` join identifiers, so an account name that is also an
    ordinary word must not rewrite `cr_admin_ready` or `map-test-3`.

    Control: put the boundary back to `(?<![A-Za-z0-9])` -> red.
    """
    src = LOG_SCRUB.read_text(encoding="utf-8")
    before = initialiser(LOG_SCRUB, "internal static class LogScrub", "NameBoundaryBefore")
    after = initialiser(LOG_SCRUB, "internal static class LogScrub", "NameBoundaryAfter")
    for name, expr in (("before", before), ("after", after)):
        for ch in ("_", ".", "\\\\-"):
            assert ch in expr, "the %s boundary does not exclude %r: %s" % (name, ch, expr)
    # ...and both users of the rule read the SAME constants, so the scrub and
    # the residue counter cannot measure different boundaries.
    body = code_of(LOG_SCRUB)
    assert body.count("NameBoundaryBefore +") == 2, \
        "expected the scrub and the residue counter to share the boundary"


def test_the_caption_is_allowed_to_wrap():
    """A fixed-height label with TMP's Truncate default drops everything past
    the first line. Since item 13 the caption is not a label on the row at
    all: it is the row's description, which the settings pane shows as the
    help body (SettingsBodyFor -> SetDetBody), a word-wrapped, auto-height
    text inside a scroll view. Control: delete the body's SetWordWrap call ->
    red."""
    call, _ = _settings_toggle_call("SAutoLog")
    assert call.startswith('SettingsSwitch(subPrivacy.transform, "SAutoLog", I18n.Tr("'), (
        "the caption is no longer the row's description argument: " + call[:120])

    chrome = mask_code(cs_block(NATIVE_UI_SETTINGS,
                                "private static Transform BuildSettingsChrome(GameObject outer)"))
    for needle in ("SetWordWrap(setDetBodyTxt, true)", "SetOverflowMode(setDetBodyTxt, 0)",
                   "SetTextAutoHeight(setDetBodyTxt, 0f)"):
        assert needle in chrome, "the settings pane's help body does not %r" % needle
    body = code_of(NATIVE_UI_SETTINGS, "private static string SettingsBodyFor(SettingsRowRec rec)")
    assert "rec.Desc" in body, "the help body no longer carries the row's description"


# ── the caption ships in every locale ────────────────────────────────────

def test_the_consent_caption_is_translated_in_every_locale():
    from test_pc_sept12 import _bundled_catalogues
    caption = _settings_toggle_literal("SAutoLog")
    # The C# literal is what the extractor keys on; unescape it the same way.
    key = (caption.replace('\\"', '"').replace("\\n", "\n")
                  .replace("\\t", "\t").replace("\\\\", "\\"))
    catalogue = _bundled_catalogues()
    bad = []
    for lang in LOCALES:
        value = catalogue.get(lang, {}).get(key)
        if value is None:
            bad.append(("missing", lang))
        elif not value.strip():
            bad.append(("empty", lang))
        elif value == key:
            # Control: set one locale's value to the English string -> red.
            bad.append(("english", lang))
    assert not bad, "the consent caption is not shipped in %r" % bad


def test_the_consent_caption_is_in_the_extracted_registry():
    caption = _settings_toggle_literal("SAutoLog")
    with io.open(REPO / "tools" / "i18n_source.json", encoding="utf-8") as fh:
        registry = set(json.load(fh)["strings"])
    assert caption in registry, (
        "the consent caption is not in tools/i18n_source.json, so the "
        "translation pipeline cannot see it")


# -- a consent revoke discards what was composed under it (round 3 finding 9) --

# An assignment to a chat field, as (field, value), read from code only.
_CHAT_WRITE = re.compile(r"\b(chat\w+)\s*=\s*([^;=][^;]*);")


def _chat_discards(signature: str) -> set:
    body = code_of(COMPETITIVE_UI, signature)
    found = {(name, value.strip()) for name, value in _CHAT_WRITE.findall(body)}
    if body.count("DropStash();") == 1:
        found.add(("DropStash()", "called"))
    return found


def test_a_consent_revoke_discards_the_open_line_as_an_account_change_does():
    """The consent-revoke path called DropChatDraftOnRevoke, which dropped
    only the held stash: a revoke that the chat loop's own guard never reached
    (a throwing draw path) left the typed line in the open box. It now
    discards everything DropChatOnAccountChange discards -- the stash, the
    open line and the resume notice -- and the two are pinned equal so
    neither can gain a field the other forgets.

    A shape pin only. The runtime proof is CompetitiveUI.RunChatRevokeSentinel
    ([Broadcast] TestChatRevokeSentinel). Reds on: the round-2 body
    `{ DropStash(); }`, either assignment removed, the call site removed.
    """
    revoke = _chat_discards("internal static void DropChatDraftOnRevoke()")
    change = _chat_discards("internal static void DropChatOnAccountChange()")
    for needed in (("DropStash()", "called"), ("chatInputText", '""'),
                   ("chatResumeNoticeUntil", "-999f")):
        assert needed in change, (
            "the account-change path no longer discards %s=%s; re-derive this "
            "pin before trusting it" % needed)
        assert needed in revoke, (
            "a consent revoke no longer discards %s=%s: %s" % (needed + (sorted(revoke),)))
    assert revoke == change, (
        "the revoke and account-change discards differ: %s vs %s" % (sorted(revoke), sorted(change)))
    api = code_of(API_CLIENT.read_text(encoding="utf-8"))
    assert api.count("CompetitiveUI.DropChatDraftOnRevoke();") == 1, (
        "the consent-revoke path no longer calls DropChatDraftOnRevoke exactly once")


# ── the negative control for the readers themselves ──────────────────────

def test_the_gates_read_blocks_that_exist():
    with pytest.raises(CsParseError):
        cs_block(AUTO_LOG, "OnRoomLeftButSpelledWrong()")
    with pytest.raises(CsParseError):
        _settings_toggle_literal("SNoSuchToggle")
