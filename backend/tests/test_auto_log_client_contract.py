"""The automatic log upload's wire contract with the client that calls it.

The caller is the v1.41.0 client lane (branch claude/v1410-client, read at
32e9d5ac): plugin/ApiClient.cs `BuildAutoLogBody` builds the JSON by hand and
`SubmitAutoLogBody` POSTs it once to /api/v1/logs/auto through
`PostRequestRaw` -- Content-Type application/json, X-Mod-Version, X-Locale and,
on credentialed transport, X-Session-Token; a 20 s timeout; ONE attempt.
plugin/AutoLogUpload.cs reads the answer: 200 -> `log_bytes` and `bug_number`
out of the body; 404 -> uploads latched off for the session; 429/409/413 ->
terminal; anything else (and no response) -> one warning, never retried, the
next qualifying room exit (at least 300 s later, the debounce every arm but a
cancel consumes) tries again. A 401 whose body says `session_required` also
drops the stale token (ApiClient.HandleSessionReject ->
SecureRouteRules.IsSessionRefusal).

Each case below holds ONE thing the server must accept or say exactly as that
client sends or reads it. `_client_body` is a line-for-line port of
BuildAutoLogBody and `_client_escape` of JsonEscapeFull, so a field the client
adds, renames or drops is a change these must be re-read against.
"""
import ast
import inspect
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import auto_logs                                                 # noqa: E402

CLIENT_LOG_CAP_CHARS = 3_500_000      # ApiClient.BUG_REPORT_LOG_CAP_CHARS
SYNTH_STEAM = "76561198000000001"     # synthetic, the suite's own
SYNTH_OPP = "76561198000000002"


def _client_escape(s):
    """ApiClient.JsonEscapeFull, ported."""
    if not s:
        return ""
    out = []
    for c in s:
        if c == "\\":
            out.append("\\\\")
        elif c == '"':
            out.append('\\"')
        elif c == "\n":
            out.append("\\n")
        elif c == "\r":
            out.append("\\r")
        elif c == "\t":
            out.append("\\t")
        elif ord(c) < 0x20 or ord(c) == 0x7F:
            out.append("\\u%04x" % ord(c))
        else:
            out.append(c)
    return "".join(out)


def _client_body(steam_id=SYNTH_STEAM, display_name="Player", mod_version="1.41.0",
                 game_version="1.0", mode="ranked1v1", room_name="CR_RANKED_abc",
                 opponent_steam_id=SYNTH_OPP, series_id="s-1", log_text="line one\nline two"):
    """ApiClient.BuildAutoLogBody, ported: the exact bytes the client POSTs."""
    if log_text is not None and len(log_text) > CLIENT_LOG_CAP_CHARS:
        log_text = log_text[-CLIENT_LOG_CAP_CHARS:]
    e = _client_escape
    s = "{"
    s += '"steam_id":"%s"' % e(steam_id)
    s += ',"display_name":"%s"' % e(display_name or "")
    s += ',"mod_version":"%s"' % e(mod_version or "")
    s += ',"game_version":"%s"' % e(game_version or "")
    s += ',"mode":"%s"' % e(mode or "")
    s += ',"room_name":"%s"' % e(room_name or "")
    if opponent_steam_id:
        s += ',"opponent_steam_id":"%s"' % e(opponent_steam_id)
    if series_id:
        s += ',"series_id":"%s"' % e(series_id)
    s += ',"log_text":"%s"' % e(log_text or "")
    s += "}"
    return s.encode("utf-8")


def _accept(body: bytes):
    """What the route does with the bytes before any database work: the byte
    ceiling, the strict JSON parse, the object check and the model."""
    assert len(body) <= auto_logs.AUTO_LOG_MAX_BODY_BYTES
    payload = json.loads(body.decode("utf-8", errors="replace"))
    assert isinstance(payload, dict)
    return auto_logs.AutoLogRequest.model_validate(payload)


# ── one case per field the client sends ─────────────────────────────────────

@pytest.mark.parametrize("field,value", [
    ("steam_id", SYNTH_STEAM),
    ("display_name", "Ünïcødé name ☃"),
    ("mod_version", "1.41.0"),
    ("game_version", "2021.3.16f1"),
    ("mode", "ranked2v2"),
    ("room_name", "CR_RANKED_" + "x" * 40),
    ("opponent_steam_id", SYNTH_OPP),
    ("series_id", "0b9c6a2e-4c1f-4f7a-9d55-2f5a8f9f6e01"),
])
def test_each_short_field_the_client_sends_is_accepted_and_kept(field, value):
    got = _accept(_client_body(**{field: value}))
    assert getattr(got, field) == value


@pytest.mark.parametrize("field", ["display_name", "mod_version", "game_version",
                                   "mode", "room_name"])
def test_each_always_sent_field_is_accepted_empty(field):
    """BuildAutoLogBody writes `?? ""` for these: an empty string, never null."""
    got = _accept(_client_body(**{field: ""}))
    assert getattr(got, field) == ""


@pytest.mark.parametrize("field", ["opponent_steam_id", "series_id"])
def test_each_conditional_field_is_accepted_absent(field):
    """The client omits these two keys entirely when it has no value."""
    body = _client_body(**{field: None})
    assert ('"%s"' % field).encode() not in body
    assert getattr(_accept(body), field) is None


def test_the_log_text_is_accepted_with_every_escape_the_client_writes():
    log = "tab\there\r\nquote\"back\\slash\x00nul\x1besc\x7fdel end"
    got = _accept(_client_body(log_text=log))
    # the credential rule leaves a log with no ticket as sent
    assert got.log_text == log


def test_the_largest_log_the_client_sends_is_accepted_whole():
    """3.5 M characters is the client's own cap; the server's character clamp
    is the bug-report ceiling (12 M) and its byte ceiling 14 MiB, so the
    client's largest ASCII bundle passes both untouched."""
    log = ("0123456789abcdef" * (CLIENT_LOG_CAP_CHARS // 16 + 1))[:CLIENT_LOG_CAP_CHARS]
    body = _client_body(log_text=log + "TAIL")   # the client keeps the tail
    got = _accept(body)
    assert len(got.log_text) == CLIENT_LOG_CAP_CHARS
    assert got.log_text.endswith("TAIL")
    assert auto_logs.BUG_REPORT_LOG_MAX_CHARS >= CLIENT_LOG_CAP_CHARS


def test_the_largest_non_latin_log_the_client_sends_fits_the_byte_ceiling():
    """Three UTF-8 bytes per character is the most a BMP character costs; a
    full-cap bundle of them is still under the 14 MiB read ceiling."""
    body = _client_body(log_text="中" * CLIENT_LOG_CAP_CHARS)
    assert len(body) <= auto_logs.AUTO_LOG_MAX_BODY_BYTES
    assert len(_accept(body).log_text) == CLIENT_LOG_CAP_CHARS


def test_a_body_past_the_byte_ceiling_is_refused_413_which_the_client_treats_as_terminal():
    """Control characters cost six bytes each once escaped, so a full-cap
    bundle of them exceeds the ceiling. The route reads the body through
    _read_capped_body, whose refusal is 413 -- one of the three codes
    AutoLogUpload names terminal."""
    body = _client_body(log_text="\x01" * CLIENT_LOG_CAP_CHARS)
    assert len(body) > auto_logs.AUTO_LOG_MAX_BODY_BYTES
    src = inspect.getsource(auto_logs._read_capped_body)
    assert "status_code=413" in src


# ── what the client reads back ──────────────────────────────────────────────

def test_the_session_refusal_says_the_word_the_client_repairs_on():
    """SecureRouteRules.IsSessionRefusal: `session_required` or
    `steam session required`. Every 401 the route raises carries the former."""
    assert auto_logs._SESSION_REJECT == "session_required"
    src = inspect.getsource(auto_logs.upload_auto_log)
    assert src.count("status_code=401, detail=_SESSION_REJECT") == src.count("status_code=401")
    assert src.count("status_code=401") == 3


def test_the_success_body_carries_the_two_numbers_the_client_extracts():
    """AutoLogUpload reads `log_bytes` and `bug_number` with
    ExtractJsonInt, which accepts a leading '-' (an automatic number is
    negative, migration 373). Both keys must be in the returned object."""
    tree = ast.parse(inspect.getsource(auto_logs.upload_auto_log).lstrip())
    keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            keys |= {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    assert {"log_bytes", "bug_number", "id", "status"} <= keys, keys
    # Starlette renders JSON compactly, so the client's `"key":` search hits.
    from starlette.responses import JSONResponse
    rendered = JSONResponse({"log_bytes": 12, "bug_number": -7}).body.decode()
    assert '"bug_number":-7' in rendered and '"log_bytes":12' in rendered


# The codes AutoLogUpload handles without retrying: 404 latches uploads off for
# the session; 429/409/413 log terminal; the rest log one warning.
CLIENT_HANDLED = {400, 401, 404, 413, 422, 429, 503}
# MDPL-GATE-REREAD-1: the route's one 404, the arm's own literal for a player
# whose row, read again by id in the writing transaction, is deleted.
DELETED_PLAYER_404 = 'raise HTTPException(status_code=404, detail="Player not found")'


def _refusal_census(src, helper_src, module_src, prune_src):
    """The census of the codes, over the route's, the capped reader's, the
    module's and the prune route's source. Raises AssertionError at the first
    check that fails (the mutant below reads which one)."""
    codes = {int(c) for c in re.findall(r"status_code=(\d+)", src)}
    # the per-day bucket's 429 is raised by a helper the route calls
    helper_codes = {int(c) for c in re.findall(r"status_code=(\d+)", helper_src)}
    assert codes | helper_codes <= CLIENT_HANDLED, codes | helper_codes
    assert all(400 <= c < 600 for c in codes | helper_codes)
    # The deleted player's refusal is read here, where the others are: the
    # arm answers with its own literal 404, once (the helper's refusal it
    # catches to discard the blob is not raised again).
    assert src.count("status_code=404") == 1, ("404 literals in the route", src.count("status_code=404"))
    module_codes = {int(c) for c in re.findall(r"status_code=(\d+)", module_src)}
    # The internal prune route's own answers -- 403 (the key), 409 (a pass is
    # already running) and 503 (its unlink pass past the ceiling) -- belong to
    # it alone; the client never calls it, and no code the client can meet is
    # admitted by this exception.
    prune_codes = {int(c) for c in re.findall(r"status_code=(\d+)", prune_src)}
    assert prune_codes == {403, 409, 503}, prune_codes
    for code in (403, 409):
        assert module_src.count("status_code=%d" % code) == prune_src.count("status_code=%d" % code), (
            "status %d is raised outside the internal prune route" % code)
    assert module_codes - {403, 409} <= CLIENT_HANDLED, module_codes


def _census_sources():
    return (inspect.getsource(auto_logs.upload_auto_log),
            inspect.getsource(auto_logs._read_capped_body),
            inspect.getsource(auto_logs),
            inspect.getsource(auto_logs.run_auto_log_prune))


def test_every_refusal_the_route_can_raise_is_one_the_client_handles_without_retrying():
    """The upload route's own codes, read from its source: every one is a 4xx
    or a 503, never a redirect and never a 2xx carrying an error. The client
    makes ONE attempt per qualifying room exit whatever comes back (404
    latches off for the session; 429/409/413 log terminal; the rest log one
    warning), so no code below can start a loop. A new code fails this case
    and must be read against AutoLogUpload before it is admitted. The 404 is
    the route's since MDPL-GATE-REREAD-1 (a deleted player's upload, refused
    after the re-read by id); its literal is counted, once."""
    _refusal_census(*_census_sources())


def test_the_census_is_red_when_the_deleted_players_404_is_no_literal():
    """THE MUTANT: the literal taken out, the arm raising the helper's refusal
    again as it did before. The route still answers 404, but the census can
    no longer read it, and is red at the 404 count, its first failing line."""
    src, helper_src, module_src, prune_src = _census_sources()
    assert src.count(DELETED_PLAYER_404) == 1, src.count(DELETED_PLAYER_404)
    assert module_src.count(DELETED_PLAYER_404) == 1, module_src.count(DELETED_PLAYER_404)
    with pytest.raises(AssertionError) as red:
        _refusal_census(src.replace(DELETED_PLAYER_404, "raise"), helper_src,
                        module_src.replace(DELETED_PLAYER_404, "raise"), prune_src)
    assert str(red.value).splitlines()[0] == "('404 literals in the route', 0)", str(red.value)
