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
LOG_SCRUB = PLUGIN / "LogScrub.cs"
CATALOGUES = PLUGIN / "I18nCatalogues.cs"

ON_ROOM_LEFT = "OnRoomLeft()"
COMPOSE = "ComposeLogBundle(LogBundleInputs inputs, out int scrubbed, out string diagnostic)"
READ_TAIL = "ReadLogTail(string path, int maxChars = BUG_REPORT_LOG_CAP_CHARS)"

LOCALES = ("es", "ru", "uk", "sv")


# ── the game thread ──────────────────────────────────────────────────────

# Anything whose cost scales with the size of a log file. None of these may be
# reached from the room-exit handler, which runs on the game thread.
EXPENSIVE = (
    "CompetitiveUI.BuildLogBundle(",
    "CompetitiveUI.ComposeLogBundle(",
    "ApiClient.ReadLogTail(",
    "ApiClient.BuildAutoLogBody(",
    "ApiClient.SubmitAutoLog(",
)


def test_the_room_exit_handler_does_no_log_work_on_the_game_thread():
    # Control: put `CompetitiveUI.ComposeLogBundle(inputs, out s, out d);`
    # back into OnRoomLeft -> red.
    block = mask_code(cs_block(AUTO_LOG, ON_ROOM_LEFT))
    found = [needle for needle in EXPENSIVE if needle in block]
    assert not found, (
        "the room-exit handler reaches work proportional to the log: %r. That "
        "is the game thread; the bundle belongs on the worker." % found)
    # ...and it positively DOES hand off, so "found nothing" cannot mean "the
    # feature was deleted" (#438 -- acceptance is a positive signal).
    assert "CompetitiveUI.CaptureLogBundleInputs(" in block
    assert "StartBundleWorker(" in block


def _worker_lambda_body() -> str:
    """The delegate passed to `new Thread(...)`, on the mask.

    Sliced rather than parsed: it is an anonymous method, so it has no
    signature `cs_block` could find. The window ends at the publish, which is
    the delegate's last statement.
    """
    masked = mask_code(AUTO_LOG.read_text(encoding="utf-8"))
    start = masked.find("new Thread(")
    assert start != -1, "no worker thread in AutoLogUpload"
    end = masked.find("lock (_gate)", start)
    assert end != -1, "the worker no longer publishes under the gate"
    return masked[start:end]


def test_the_bundle_is_composed_on_a_background_thread():
    body = code_of(AUTO_LOG)
    assert body.count("new Thread(") == 1, "expected exactly one worker thread"
    # Control: delete either of these -> red. IsBackground is not decoration:
    # a foreground thread mid-bundle holds the process open at quit.
    assert "IsBackground = true" in body
    worker = _worker_lambda_body()
    for needle in ("CompetitiveUI.ComposeLogBundle(", "ApiClient.BuildAutoLogBody(",
                   "Encoding.UTF8.GetBytes("):
        assert needle in worker, f"the worker does not do {needle} -- so something else does"


def test_the_worker_writes_nothing_to_the_log_from_its_own_thread():
    # BepInEx's sinks are not documented thread-safe, and a line written from
    # here interleaves with the game's own. Every sentence the worker wants to
    # say travels back in the result.
    # Control: insert `Plugin.Log.LogInfo("x");` inside the delegate -> red.
    worker = _worker_lambda_body()
    assert "Plugin.Log" not in worker


def test_the_thread_safe_composer_touches_no_engine_api():
    # Control: add `Plugin.Log.LogInfo(diagnostic);` to ComposeLogBundle -> red.
    body = mask_code(cs_block(COMPETITIVE_UI, COMPOSE))
    forbidden = ("Plugin.Log", "AudioSelfCheck.", "Application.", "Time.",
                 "PhotonNetwork", "UnityEngine.", "I18n.")
    hit = [n for n in forbidden if n in body]
    assert not hit, (
        "ComposeLogBundle reaches %r. It runs on a worker thread; a Unity call "
        "there is a freeze at best and a throw at worst." % hit)


def test_the_body_builder_takes_its_versions_as_parameters():
    """`Application.version` is a Unity read, so it cannot live in the body
    builder the worker calls. Control: replace the `gameVersion` parameter
    with a direct `UnityEngine.Application.version` read -> red."""
    body = mask_code(cs_block(API_CLIENT, "BuildAutoLogBody(string steamId, string displayName,"))
    assert "Application." not in body
    assert "Plugin.ModVersion" not in body


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
    """(source-with-literals, masked) slices of the `SettingsToggle` call whose
    element name is `name`.

    Two views of the SAME offsets: literals survive the first (that is how the
    element name is found and the caption read back), and are blanked in the
    second (that is what makes the paren walk safe -- this very caption
    contains a bracketed clause, and the callback body is full of semicolons).
    """
    src = NATIVE_UI.read_text(encoding="utf-8")
    with_literals = strip_comments_only(src)
    masked = mask_code(src)
    anchor = with_literals.find('SettingsToggle(consentBox.transform, "%s"' % name)
    if anchor == -1:
        raise CsParseError("no SettingsToggle call for %r" % name)
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
        raise CsParseError("unterminated SettingsToggle call for %r" % name)
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
    "display_name": "name",
    "opponent_steam_id": "the other players' Steam IDs",
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
    the first line. Control: delete `descWrap: true` from the call -> red."""
    _, call = _settings_toggle_call("SAutoLog")
    assert "descWrap: true" in call, "the consent caption is still clipped at one line"

    # ...and the option does what its name says.
    toggle = mask_code(cs_block(NATIVE_UI, "SettingsToggle(Transform parent, string name, Vector2 size,"))
    for needle in ("if (descWrap)", "SetWordWrap(d, true)", "SetTextAutoHeight(d, descH)",
                   "SetOverflowMode(d, 0)"):
        assert needle in toggle, "SettingsToggle's descWrap does not %r" % needle


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


# ── the negative control for the readers themselves ──────────────────────

def test_the_gates_read_blocks_that_exist():
    with pytest.raises(CsParseError):
        cs_block(AUTO_LOG, "OnRoomLeftButSpelledWrong()")
    with pytest.raises(CsParseError):
        _settings_toggle_literal("SNoSuchToggle")
