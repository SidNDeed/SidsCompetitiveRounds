"""TICKET-REDACTION: the credential rule, its receive path, its read-back doors
and its /health marker, EXECUTED.

The rule (backend/api/log_redaction.py) replaces the value after
"Session Ticket:" -- 32 or more hex characters, either case -- with
"[redacted len=<n> sha256=<first 8 hex of SHA-256>]" and alters nothing else.
The unit cases pin that contract; the route cases run the api's own handlers,
mounted on a test app, against a real PostgreSQL:

  * POST /api/v1/bug-reports, the receive path: the stored bundle file and the
    two free-text columns carry the marker and never the value;
  * a row stored BEFORE the rule (raw file, raw columns -- the T3 choice is
    read-time redaction, so those stay raw on disk), read through each of the
    five doors that serve stored text: the detail pane, the log download, the
    admin list, the Discord feed and the reporter-DM event feed;
  * the four comment receive paths (admin comment, status change, internal
    comment, the reporter's reply the bot relays): the stored
    bug_report_events.comment carries the marker; and a comment stored before
    the rule, read through the two doors that serve it -- the bot's own feed,
    at the exact URL the bot polls, and the detail pane's timeline;
  * the rule BEFORE EVERY CUT (round 2, M2): a ticket planted across each
    clamp's boundary -- the log's 12,000,000-character tail, the description's
    and repro steps' 8000-character head, the reply's 2000-character head and
    the over-ceiling bundle read's window -- where a cut made first leaves the
    rule too little to recognise;
  * the automatic post-match upload (L6), a CONTRACT: the route is not on this
    tree, so its two cases skip here and run at merge; the same checker runs
    on this tree against a stand-in with the real route's write path;
  * /api/v1/health: `ticket_redaction` == 1 on both arms.

Every ticket value here is COMPOSED at run time from a SHA-256 of a fixture
label: no hex run of ticket length is written in this file, so a pin or a lane
folder carrying it is not itself a credential hit for the scanners.

Live PostgreSQL is REQUIRED for the test_pg_ cases, and a missing DSN FAILS,
naming the variable (the harness shape of test_ffa_quarantine_triage.py):
    TICKET_REDACTION_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    TICKET_REDACTION_TEST_PG_OPTOUT=1   says out loud that this run skips them
Each case ends every other session on that database and drops and recreates
its own tables there, so the harness REFUSES, before either, a database whose
name lacks this lane's scratch marker or that holds anything but this
harness's own synthetic fixtures (round 2, M3).
"""

import asyncio
import gzip
import hashlib
import hmac
import inspect
import os
import random
import re
import subprocess
import sys
import uuid

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import database
import log_redaction
import main
import models
import ticket_redaction_autolog_standin as standin

LOG_REDACTION_SRC = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "api", "log_redaction.py"))

# ── fixtures: composed at run time ─────────────────────────────────────────

LABEL = "Session Ticket: "
GAME_PREFIX = "Steam Login success. " + LABEL


def synthetic_hex(seed: str, n: int = 256, upper: bool = True) -> str:
    """A synthetic ticket-shaped value: SHA-256 digests of a fixture label,
    concatenated and cut to n hex characters."""
    out, i = "", 0
    while len(out) < n:
        out += hashlib.sha256(f"ticket-redaction-fixture:{seed}:{i}".encode()).hexdigest()
        i += 1
    out = out[:n]
    return out.upper() if upper else out


def expected_marker(value: str) -> str:
    """The marker, computed HERE from the brief's format, not by the module."""
    digest8 = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return "[redacted len=%d sha256=%s]" % (len(value), digest8)


def expect(sent: str, *values: str) -> str:
    """What the stored or served text must be: the input with each value
    replaced by its marker and every other character as sent."""
    for v in values:
        sent = sent.replace(v, expected_marker(v))
    return sent


def assert_redacted(sent: str, stored: str, *values: str):
    """The check every route case uses: no value survives, each marker is
    present, and nothing else moved."""
    for v in values:
        assert v not in stored, "a ticket value survived"
        assert expected_marker(v) in stored, "a marker is missing"
    assert stored == expect(sent, *values), "text other than the ticket value changed"


# ── the rule ──────────────────────────────────────────────────────────────


def test_a_ticket_at_the_end_of_a_line_becomes_its_marker():
    hx = synthetic_hex("line-end")
    text_ = "[Info   : Unity Log] boot\n" + GAME_PREFIX + hx + "\n[Info   : Unity Log] next"
    out = log_redaction.redact_credentials(text_)
    assert out == "[Info   : Unity Log] boot\n" + GAME_PREFIX + expected_marker(hx) + "\n[Info   : Unity Log] next"
    at_eof = GAME_PREFIX + hx
    assert log_redaction.redact_credentials(at_eof) == GAME_PREFIX + expected_marker(hx)
    crlf = "a\r\n" + GAME_PREFIX + hx + "\r\nb"
    assert log_redaction.redact_credentials(crlf) == "a\r\n" + GAME_PREFIX + expected_marker(hx) + "\r\nb"


def test_a_ticket_followed_by_text_keeps_the_text():
    hx = synthetic_hex("followed", 128)
    for tail in (" and more words", "\tcol2", "|next", ".", "g"):
        text_ = GAME_PREFIX + hx + tail
        assert log_redaction.redact_credentials(text_) == GAME_PREFIX + expected_marker(hx) + tail, tail


def test_two_tickets_in_one_text_get_two_markers():
    a, b = synthetic_hex("two-a", 200), synthetic_hex("two-b", 96)
    text_ = GAME_PREFIX + a + "\nmiddle line\n[Warning: x] " + LABEL + b + " end"
    out, n = log_redaction.redact_credentials_counted(text_)
    assert n == 2
    assert out == GAME_PREFIX + expected_marker(a) + "\nmiddle line\n[Warning: x] " + LABEL + expected_marker(b) + " end"
    one_line = LABEL + a + " " + LABEL + b
    assert log_redaction.redact_credentials(one_line) == LABEL + expected_marker(a) + " " + LABEL + expected_marker(b)


def test_lowercase_hex_is_a_ticket_and_is_digested_as_logged():
    upper = synthetic_hex("case", 64)
    lower = upper.lower()
    assert log_redaction.redact_credentials(LABEL + lower) == LABEL + expected_marker(lower)
    assert expected_marker(lower) != expected_marker(upper)
    mixed = upper[:32] + lower[32:]
    assert log_redaction.redact_credentials(LABEL + mixed) == LABEL + expected_marker(mixed)


def test_31_hex_characters_are_untouched():
    hx31 = synthetic_hex("short", 31)
    for text_ in (LABEL + hx31, GAME_PREFIX + hx31 + "\n", LABEL + hx31 + " tail"):
        out, n = log_redaction.redact_credentials_counted(text_)
        assert n == 0 and out is text_
    hx32 = synthetic_hex("short", 32)
    assert log_redaction.redact_credentials(LABEL + hx32) == LABEL + expected_marker(hx32)


def test_a_text_without_a_ticket_is_the_same_object_byte_for_byte():
    hash16 = hashlib.sha256(b"a plain hash").hexdigest()[:16]
    digest64 = hashlib.sha256(b"a digest with no label").hexdigest()
    texts = [
        "[Info   : Unity Log] round 3 over: p1=2 p2=1\n",
        "Session Ticket:\n",
        "Session Ticket: " + hash16 + "\n",
        "commit " + digest64 + "\n",
        "a\r\nb\r\n",
        "unicode text: café — 日本 \U0001F600\n",
        GAME_PREFIX + expected_marker(synthetic_hex("already")) + "\n",
        "Session Ticket - " + synthetic_hex("no-colon") + "\n",
        "",
    ]
    for t in texts:
        out, n = log_redaction.redact_credentials_counted(t)
        assert n == 0 and out is t, t[:40]
        assert log_redaction.count_credentials(t) == 0
    assert log_redaction.redact_credentials(None) is None


def test_the_marker_matches_the_known_answer_and_the_client_format():
    value = "0123456789ABCDEF" * 2              # 32 hex characters, composed
    assert log_redaction.ticket_marker(value) == "[redacted len=32 sha256=cd6c1f7d]"
    assert log_redaction.ticket_marker(value.lower()) == "[redacted len=32 sha256=3eb1bd43]"
    # The game's own line comes out exactly as the client's redaction writes it.
    hx = synthetic_hex("game-line", 468)
    assert (log_redaction.redact_credentials(GAME_PREFIX + hx)
            == "Steam Login success. Session Ticket: " + expected_marker(hx))


def test_the_whitespace_after_the_colon_is_kept():
    hx = synthetic_hex("ws", 48)
    for gap in ("", " ", "  ", "\t", " \t "):
        text_ = "Session Ticket:" + gap + hx
        assert log_redaction.redact_credentials(text_) == "Session Ticket:" + gap + expected_marker(hx), repr(gap)


def test_a_second_pass_is_a_no_op():
    text_ = GAME_PREFIX + synthetic_hex("idem-a") + "\n" + LABEL + synthetic_hex("idem-b", 40)
    once = log_redaction.redact_credentials(text_)
    twice, n = log_redaction.redact_credentials_counted(once)
    assert n == 0 and twice is once


def test_file_bytes_are_counted_in_utf8_and_in_utf16_at_either_alignment():
    hx = synthetic_hex("bytes", 96)
    line = "x\n" + GAME_PREFIX + hx + "\ny"
    assert log_redaction.count_credentials_bytes(line.encode("utf-8")) == 1
    assert log_redaction.count_credentials_bytes((line + "\n" + line).encode("utf-8")) == 2
    wide = line.encode("utf-16-le")
    assert log_redaction.count_credentials_bytes(b"\xff\xfe" + wide) == 1
    assert log_redaction.count_credentials_bytes(b"\x01" + wide) == 1          # odd offset
    assert log_redaction.count_credentials_bytes(b"\x01\x02" + wide) == 1      # even offset, no mark
    hash16 = hashlib.sha256(b"a plain hash").hexdigest()[:16]
    assert log_redaction.count_credentials_bytes(("Session Ticket: " + hash16).encode()) == 0
    assert log_redaction.count_credentials_bytes(b"") == 0


def test_file_bytes_are_rewritten_with_every_other_byte_kept():
    hx = synthetic_hex("rewrite", 64)
    raw = b"head \x80\x81 not utf-8\n" + (GAME_PREFIX + hx).encode() + b"\ntail\xff"
    out, n = log_redaction.redact_credentials_bytes(raw)
    assert n == 1
    assert out == b"head \x80\x81 not utf-8\n" + (GAME_PREFIX + expected_marker(hx)).encode() + b"\ntail\xff"
    wide_text = "a\r\n" + GAME_PREFIX + hx + "\r\nb"
    wide = b"\xff\xfe" + wide_text.encode("utf-16-le")
    out_w, n_w = log_redaction.redact_credentials_bytes(wide)
    assert n_w == 1
    assert out_w == b"\xff\xfe" + expect(wide_text, hx).encode("utf-16-le")
    clean = b"nothing here\n"
    same, zero = log_redaction.redact_credentials_bytes(clean)
    assert zero == 0 and same is clean


def test_the_module_filters_stdin_to_stdout_for_the_ops_verbs():
    hx = synthetic_hex("filter", 128)
    raw = ("line one\n" + GAME_PREFIX + hx + "\nline three\n").encode()
    proc = subprocess.run([sys.executable, LOG_REDACTION_SRC], input=raw,
                          capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ("line one\n" + GAME_PREFIX + expected_marker(hx) + "\nline three\n").encode()
    assert b"credentials redacted: 1" in proc.stderr


def test_the_module_is_standard_library_only():
    # The ops filter runs it inside the api container and the local tools load
    # it by path; neither may depend on anything the api's requirements add.
    src = inspect.getsource(log_redaction)
    imports = sorted({ln.split()[1].split(".")[0] for ln in src.splitlines()
                      if ln.startswith(("import ", "from ")) and not ln.startswith("from __future__")})
    assert imports == ["codecs", "hashlib", "re", "sys"], imports


def test_the_bundle_scrub_redacts_credentials_first_and_counts_them():
    a, b = synthetic_hex("pass-a"), synthetic_hex("pass-b", 64)
    body = "boot\n" + GAME_PREFIX + a + "\nlater " + LABEL + b + "\n"
    out, counts, ids = main._scrub_pass_one(body)
    assert counts["credential"] == 2
    assert out == expect(body, a, b)
    empty_out, empty_counts, _ = main._scrub_pass_one("")
    assert empty_counts["credential"] == 0 and empty_out == ""
    assert main._BUG_LOG_SCRUB_VERSION == "2"


# ── the rule before every cut (round 2, M2): the pieces a reader holds ─────

FILLER_LINE = "[Info   : Unity Log] [CR] round over: p1=1 p2=0 frame ok\n"
BANNER = "[scrubber: bundle exceeded the read ceiling; OLDEST lines dropped, tail kept]\n"


def filler(n: int) -> str:
    """n characters of ordinary log lines: no ticket, no path, no id."""
    return (FILLER_LINE * (n // len(FILLER_LINE) + 1))[:n]


def _gz(path, text_) -> str:
    path.write_bytes(gzip.compress(text_.encode("utf-8"), compresslevel=1))
    return str(path)


def _stream(text_, cuts):
    """The rule applied the way a reader that gets `text_` in pieces applies
    it (main._read_bug_log_sync): each piece joins what was held back, the
    settled prefix is redacted, the unfinished end waits for the next piece."""
    out, pending = [], ""
    bounds = [0] + sorted(cuts) + [len(text_)]
    for i in range(len(bounds) - 1):
        pending += text_[bounds[i]:bounds[i + 1]]
        last = i == len(bounds) - 2
        settled = len(pending) if last else log_redaction.settled_length(pending)
        out.append(log_redaction.redact_credentials(pending[:settled]))
        pending = pending[settled:]
    return "".join(out)


def test_settled_length_holds_back_only_an_unfinished_end():
    hx = synthetic_hex("settle", 40)
    head = "head line\n"
    assert log_redaction.settled_length("") == 0
    assert log_redaction.settled_length(head) == len(head)
    for tail in ("S", "Sess", "Session Ticket", "Session Ticket:", "Session Ticket: \t",
                 LABEL + hx[:10], LABEL + hx):
        assert log_redaction.settled_length(head + tail) == len(head), repr(tail)
    for done in (head + LABEL + hx + "\nnext", head + LABEL + hx[:10] + "z", "ends with s",
                 head + "Session Ticket - " + hx):
        assert log_redaction.settled_length(done) == len(done), repr(done[-20:])


def test_the_rule_over_pieces_equals_the_rule_over_the_whole():
    """settled_length's promise, differentially: over texts dense in label
    fragments, spaces, tabs and hex runs either side of 32, cut into pieces at
    random points, the piecewise rule gives exactly the whole-text rule. A
    reader that redacted each piece as it came, holding nothing back, splits a
    ticket between two pieces and leaves part of it raw."""
    rng = random.Random(20260925)
    atoms = [LABEL, "Session Ticket:", "Session Tic", "S", "Sess", " ", "\t", "\n", ":", "x",
             "Ticket: ", "Session Ticket:  \t", synthetic_hex("prop-a", 31), synthetic_hex("prop-b", 32),
             synthetic_hex("prop-c", 40, upper=False), synthetic_hex("prop-d", 5)]
    checked = with_ticket = split = 0
    for _ in range(400):
        text_ = "".join(rng.choice(atoms) for _ in range(rng.randint(1, 14)))
        whole = log_redaction.redact_credentials(text_)
        with_ticket += whole != text_
        spans = [m.span() for m in re.finditer(log_redaction.TICKET_PATTERN, text_)]
        for _ in range(6):
            k = min(len(text_) - 1, rng.randint(1, 4))
            cuts = rng.sample(range(1, len(text_)), k) if k > 0 else []
            assert _stream(text_, cuts) == whole, (text_, cuts)
            checked += 1
            split += any(start < cut < end for cut in cuts for start, end in spans)
    # With this seed, 61 of the 400 texts carry a ticket and 280 of the 2400
    # checks cut through one -- the case the hold-back exists for, and the
    # checks a reader holding nothing back gets wrong. The floors are half of
    # each, so an edit that thins the generator out fails here.
    assert checked == 2400 and with_ticket >= 30 and split >= 140, (checked, with_ticket, split)


def test_the_over_ceiling_read_holds_a_ticket_split_between_two_reads(tmp_path):
    """A bundle over the read ceiling is read in pieces; a ticket whose value
    runs across the end of one piece is held back, not redacted in halves.
    Redacting each piece as it came would turn the first 40 characters into a
    marker and serve the other 216 raw, with no label left to find them by."""
    ceiling = main._BUG_LOG_MAX_TEXT
    boundary = ceiling + 1 + (1 << 20)          # the first read, then one chunk
    hx = synthetic_hex("carry", 256)
    text_ = filler(boundary - len(LABEL) - 40) + LABEL + hx + "\n" + filler(5000)
    path = _gz(tmp_path / "carry.log.gz", text_)
    # The geometry this case rests on, read the way the reader reads.
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        first_two = f.read(ceiling + 1) + f.read(1 << 20)
    assert first_two.endswith(LABEL + hx[:40]), "the reads no longer split this ticket"
    out = main._read_bug_log_sync(path)
    assert hx[40:] not in out and hx[:40] not in out
    assert out == BANNER + expect(text_, hx)[-ceiling:]


def test_the_over_ceiling_read_refuses_an_unfinished_run_longer_than_the_carry(tmp_path):
    """The hold-back is bounded: an unfinished run after the label longer than
    _BUG_LOG_CARRY_MAX -- no ticket any client writes -- refuses the read (the
    download answers 413, the detail pane a read error) instead of holding it
    without bound or cutting it where the rule no longer sees a label."""
    ceiling = main._BUG_LOG_MAX_TEXT
    boundary = ceiling + 1 + (1 << 20)
    run_ = synthetic_hex("carry-bound", main._BUG_LOG_CARRY_MAX + (1 << 20), upper=False)
    text_ = filler(boundary - len(LABEL) - 64) + LABEL + run_ + "\n"
    path = _gz(tmp_path / "bound.log.gz", text_)
    refused = None
    try:
        main._read_bug_log_sync(path)
    except ValueError as ex:
        refused = str(ex)
    assert refused is not None, "an unfinished run longer than the hold-back bound was served"
    assert "unfinished ticket-shaped run" in refused and run_[:32] not in refused


# ── live PostgreSQL gate ──────────────────────────────────────────────────

DSN = os.environ.get("TICKET_REDACTION_TEST_PG_DSN")


def _optout(raw) -> bool:
    """Only an affirmative word opts out; "0", "false" or an unknown value do
    not, so the live checks then FAIL and name the DSN (#438)."""
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


OPTOUT = _optout(os.environ.get("TICKET_REDACTION_TEST_PG_OPTOUT"))


def require_pg():
    if DSN:
        return DSN
    if OPTOUT:
        pytest.skip("TICKET_REDACTION_TEST_PG_OPTOUT is set -- live-PostgreSQL checks deliberately "
                    "not run in this invocation")
    pytest.fail(
        "TICKET_REDACTION_TEST_PG_DSN is not set, so the bug-report receive path, the five "
        "read-back doors and the /health marker were never executed. Set "
        "TICKET_REDACTION_TEST_PG_DSN=postgresql+asyncpg://... to run them, or "
        "TICKET_REDACTION_TEST_PG_OPTOUT=1 to say out loud that this run skips them.")


@pytest.mark.parametrize("raw,opts_out", [
    ("1", True), ("true", True), (" yes ", True), ("on", True),
    ("0", False), ("false", False), ("", False), (None, False), ("maybe", False),
])
def test_only_an_affirmative_opt_out_turns_the_live_checks_into_skips(raw, opts_out):
    assert _optout(raw) is opts_out


def test_the_live_checks_cannot_be_skipped_by_a_missing_dsn_alone():
    assert "pytest.fail(" in inspect.getsource(require_pg)
    mod = sys.modules[__name__]
    for name in dir(mod):
        fn = getattr(mod, name)
        if callable(fn) and name.startswith("test_pg_"):
            marks = {m.name for m in getattr(fn, "pytestmark", [])}
            assert "skipif" not in marks and "skip" not in marks, name
    saved_dsn, saved_opt = globals()["DSN"], globals()["OPTOUT"]
    globals()["DSN"], globals()["OPTOUT"] = None, False
    try:
        with pytest.raises(BaseException) as ex:
            require_pg()
        assert "Failed" in type(ex.value).__name__
        assert "TICKET_REDACTION_TEST_PG_DSN" in str(ex.value)
        globals()["OPTOUT"] = True
        with pytest.raises(BaseException) as sk:
            require_pg()
        assert "Skipped" in type(sk.value).__name__
    finally:
        globals()["DSN"], globals()["OPTOUT"] = saved_dsn, saved_opt


def run(coro):
    return asyncio.run(coro)


# ── the harness ───────────────────────────────────────────────────────────
# bug_reports is 083's DDL plus 086's bug_number sequence, 102's
# channel_posted_at and 336's kind; bug_report_events is 085's plus 102's
# notified_at. players, the shop_items its cosmetic columns reference, and
# admin_users come from the ORM, because submit_bug_report selects every mapped
# Player column. gen_random_uuid()
# stands in for 083's uuid_generate_v4(), which needs an extension.

DROP = """
DROP TABLE IF EXISTS bug_report_events CASCADE;
DROP TABLE IF EXISTS bug_reports CASCADE;
DROP SEQUENCE IF EXISTS bug_reports_number_seq;
DROP TABLE IF EXISTS admin_users CASCADE;
DROP TABLE IF EXISTS players CASCADE;
DROP TABLE IF EXISTS shop_items CASCADE;
DROP TABLE IF EXISTS steam_sessions CASCADE
"""

BUG_DDL = """
CREATE SEQUENCE bug_reports_number_seq;
CREATE TABLE bug_reports (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id         UUID REFERENCES players(id) ON DELETE SET NULL,
    steam_id          VARCHAR(32),
    display_name      VARCHAR(64),
    mod_version       VARCHAR(32),
    game_version      VARCHAR(32),
    severity          VARCHAR(16) NOT NULL DEFAULT 'medium',
    category          VARCHAR(16) NOT NULL DEFAULT 'other',
    description       TEXT NOT NULL,
    repro_steps       TEXT,
    log_filename      VARCHAR(96),
    log_bytes         INTEGER,
    status            VARCHAR(16) NOT NULL DEFAULT 'open',
    triage_notes      TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bug_number        BIGINT NOT NULL DEFAULT nextval('bug_reports_number_seq') UNIQUE,
    channel_posted_at TIMESTAMPTZ,
    kind              VARCHAR(16) NOT NULL DEFAULT 'report' CHECK (kind IN ('report', 'auto'))
);
CREATE TABLE bug_report_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bug_report_id   UUID NOT NULL REFERENCES bug_reports(id) ON DELETE CASCADE,
    actor_steam_id  VARCHAR(32),
    actor_name      VARCHAR(96) NOT NULL,
    event_type      VARCHAR(24) NOT NULL,
    old_status      VARCHAR(16),
    new_status      VARCHAR(16),
    comment         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notified_at     TIMESTAMPTZ
)
"""

ADMIN = "900000000000000900"       # synthetic 18-digit ids, outside every real account range
REPORTER = "900000000000000901"
ADMIN_SECRET = "ticket-redaction-admin-secret"
INTERNAL_KEY = "ticket-redaction-internal-key"
REPORTER_DISCORD = "900000000000000977"    # synthetic, the linked account the reply path checks
OUTSIDER = "900000000000000999"            # synthetic, and NOT a fixture id: a row keyed on it is "someone else's"

# (path, method) in registration order: the two feeds before {report_id}.
ROUTES = (
    ("/api/v1/bug-reports", "POST"),
    ("/api/v1/bug-reports", "GET"),
    ("/api/v1/bug-reports/events/recent", "GET"),
    ("/api/v1/bug-reports/recent", "GET"),
    ("/api/v1/bug-reports/{report_id}", "GET"),
    ("/api/v1/bug-reports/{report_id}/log", "GET"),
    ("/api/v1/bug-reports/{report_id}/comment", "POST"),
    ("/api/v1/bug-reports/{report_id}/status", "POST"),
    ("/api/v1/internal/bug-reports/{report_id}/comment", "POST"),
    ("/api/v1/internal/bug-reports/by-number/{bug_number}/user-comment", "POST"),
    ("/api/v1/health", "GET"),
)


# ── M3: the refusals, before anything destructive ─────────────────────────
#
# What a case does to its database, in order: end every other session on it
# (_clean_slate, #753), then DROP the tables below and recreate them. Pointed
# at the wrong database, the first ends someone's sessions and the second
# deletes their data. So two refusals run first, on their own connection:
#
#   NAME  the database's name carries this lane's scratch marker -- the
#         scr_bug391 lane-database gate, generalised from one literal to the
#         lane's prefix, because this lane runs on more than one database
#         (scr_ticket_redaction; the whole-suite run's own);
#   ROWS  every table the DROP names holds only this harness's own synthetic
#         fixtures (rows keyed on ADMIN or REPORTER, nothing in shop_items),
#         and the database holds no table this harness does not create. A
#         database a real player's row lives in is refused whatever its name.
#
# A refusal is a RuntimeError naming the database and what it would have
# lost, raised before the first terminate or DROP is SENT. Every statement a
# case sends on the way in is written down (Env.sent), and every case checks
# from its own record that both refusals ran before its first terminate or
# DROP -- so the order is proved on every run, not only by the cases that
# point the harness at the wrong database.

SCRATCH_MARKER = "scr_ticket_redaction"
SCRATCH_DB_RE = re.compile(re.escape(SCRATCH_MARKER) + r"(?:_[a-z0-9_]+)?")
FIXTURE_IDS = (ADMIN, REPORTER)
HARNESS_TABLES = ("bug_report_events", "bug_reports", "admin_users", "players", "shop_items",
                  "steam_sessions")
# (table, the column a row's identity is, whether NULL is a fixture's): a
# fixture row is keyed on a FIXTURE_IDS value; shop_items gets no row at all.
POPULATION = (
    ("players", "steam_id", False),
    ("admin_users", "steam_id", False),
    ("bug_reports", "steam_id", False),
    ("bug_report_events", "actor_steam_id", True),    # the internal comment has no actor id
    ("steam_sessions", "steam_id", False),
    ("shop_items", None, False),
)
NAME_GATE_SQL = "SELECT current_database() /* ticket-redaction scratch-name gate */"
ROWS_GATE_TAG = "/* ticket-redaction population gate */"


def _destructive(sql: str) -> bool:
    s = " ".join(sql.split()).upper()
    return "PG_TERMINATE_BACKEND" in s or s.startswith("DROP ")


class _Recorded:
    """An asyncpg connection that writes each statement into `sent` BEFORE it
    sends it: the record the M3 checks read."""

    def __init__(self, conn, sent):
        self._conn, self._sent = conn, sent

    async def execute(self, sql, *args):
        self._sent.append(sql)
        return await self._conn.execute(sql, *args)

    async def fetchval(self, sql, *args):
        self._sent.append(sql)
        return await self._conn.fetchval(sql, *args)

    async def fetch(self, sql, *args):
        self._sent.append(sql)
        return await self._conn.fetch(sql, *args)

    async def close(self):
        await self._conn.close()


async def _connect(url, sent, database=None, **settings):
    import asyncpg
    conn = await asyncpg.connect(host=url.host, port=url.port, user=url.username,
                                 password=url.password or None, database=database or url.database,
                                 server_settings=settings or None)
    return _Recorded(conn, sent)


async def _refuse_unless_scratch(url, sent):
    """M3: the NAME and ROWS refusals (above), on their own connection, before
    _clean_slate and the DROP block. A table another session holds locked
    cannot stall them into skipping: a read that waits 5 s fails, and a read
    that fails is a refusal."""
    conn = await _connect(url, sent, lock_timeout="5s")
    try:
        name = await conn.fetchval(NAME_GATE_SQL)
        lost = ", ".join(HARNESS_TABLES)
        if not SCRATCH_DB_RE.fullmatch(name or ""):
            raise RuntimeError(
                f"TICKET_REDACTION_TEST_PG_DSN points at database {name!r}. Each case ends every "
                f"other session on its database and drops {lost}, so it runs only on a database "
                f"whose name carries the scratch marker {SCRATCH_MARKER!r}.")
        foreign = sorted(r["tablename"] for r in await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            " AND tablename <> ALL($1::text[]) " + ROWS_GATE_TAG, list(HARNESS_TABLES)))
        if foreign:
            raise RuntimeError(
                f"database {name!r} holds tables this harness never creates ({', '.join(foreign)}), "
                f"so it is not this harness's scratch database; refusing to end its sessions or "
                f"drop {lost}.")
        for table, column, null_ok in POPULATION:
            if not await conn.fetchval("SELECT to_regclass($1) IS NOT NULL " + ROWS_GATE_TAG,
                                       "public." + table):
                continue
            if column is None:
                sql, args = f"SELECT count(*) FROM {table} " + ROWS_GATE_TAG, ()
            elif null_ok:
                sql = (f"SELECT count(*) FROM {table} WHERE {column} IS NOT NULL"
                       f" AND {column} <> ALL($1::text[]) " + ROWS_GATE_TAG)
                args = (list(FIXTURE_IDS),)
            else:
                sql = (f"SELECT count(*) FROM {table} WHERE {column} IS NULL"
                       f" OR {column} <> ALL($1::text[]) " + ROWS_GATE_TAG)
                args = (list(FIXTURE_IDS),)
            try:
                n = await conn.fetchval(sql, *args)
            except Exception as ex:
                raise RuntimeError(
                    f"database {name!r}: could not read {table} ({type(ex).__name__}), so this "
                    f"harness cannot show it holds only its own fixtures; refusing to drop it.") from ex
            if n:
                raise RuntimeError(
                    f"database {name!r} holds {n} row(s) in {table} that are not this harness's "
                    f"synthetic fixtures; refusing to end its sessions or drop {lost}.")
    finally:
        await conn.close()


def _assert_the_refusals_came_first(sent):
    first = next((i for i, s in enumerate(sent) if _destructive(s)), None)
    assert first is not None, "this case sent no terminate and no DROP, so its record proves no order"
    before = sent[:first]
    assert NAME_GATE_SQL in before, "the scratch-name refusal did not run before the first terminate or DROP"
    assert any(ROWS_GATE_TAG in s for s in before), \
        "the population refusal did not run before the first terminate or DROP"


def sig(action: str, target: str) -> str:
    return hmac.new(ADMIN_SECRET.encode(), main._admin_canonical(ADMIN, action, target).encode(),
                    hashlib.sha256).hexdigest()


def _redirect_for(url):
    def redirect(dialect, conn_rec, cargs, cparams):
        cparams.update(host=url.host, port=url.port, user=url.username, database=url.database)
        if url.password:
            cparams["password"] = url.password
        else:
            cparams.pop("password", None)
    return redirect


async def _clean_slate(url, sent):
    """#753: a case starts from a slate it TAKES -- every other backend on the
    lane database is ended first, so a lock a dead case left behind cannot
    hold this one's DDL. The lane database is this file's alone, which is what
    _refuse_unless_scratch establishes before this runs (Env.__aenter__)."""
    conn = await _connect(url, sent)
    try:
        await conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                           " WHERE datname = current_database() AND pid <> pg_backend_pid()")
    finally:
        await conn.close()


def _app():
    app = FastAPI()
    for path, method in ROUTES:
        hits = [r for r in main.app.routes
                if getattr(r, "path", None) == path and method in (getattr(r, "methods", None) or ())]
        assert len(hits) == 1, (path, method, hits)
        app.add_api_route(path, hits[0].endpoint, methods=[method],
                          response_model=hits[0].response_model)
    return app


class Env:
    """database.py's own engines redirected to the lane database, fresh
    tables, the bundle directory in a pytest temporary directory."""

    def __init__(self, monkeypatch, log_dir):
        self.mp = monkeypatch
        self.log_dir = log_dir

    async def __aenter__(self):
        self.url = make_url(require_pg())
        self.sent = []     # every statement sent on the way in, in order (M3)
        # M3, before anything destructive: the scratch-name and population
        # refusals. Only then is the slate taken and are the tables dropped.
        await _refuse_unless_scratch(self.url, self.sent)
        await _clean_slate(self.url, self.sent)
        self.seed = create_async_engine(require_pg(), pool_size=2, max_overflow=4)
        event.listen(self.seed.sync_engine, "before_cursor_execute", self._record)
        try:
            async with self.seed.begin() as conn:
                await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                for stmt in [s for s in DROP.split(";") if s.strip()]:
                    await conn.execute(text(stmt))
                await conn.run_sync(models.Base.metadata.create_all,
                                    tables=[models.ShopItem.__table__, models.Player.__table__,
                                            models.AdminUser.__table__])
                for stmt in [s for s in BUG_DDL.split(";") if s.strip()]:
                    await conn.execute(text(stmt))
                await conn.execute(text("INSERT INTO admin_users (steam_id, granted_at) VALUES (:s, now())"),
                                   {"s": ADMIN})
            # This case's own proof that the refusals came first.
            _assert_the_refusals_came_first(self.sent)
        except BaseException:
            await self.seed.dispose()
            raise
        self.mp.setattr(main, "ADMIN_HMAC_SECRET", ADMIN_SECRET)
        self.mp.setattr(main, "MATCH_HMAC_SECRET", "")
        self.mp.setattr(main, "BUG_REPORT_LOG_DIR", str(self.log_dir))
        self._redirect = _redirect_for(self.url)
        for eng in (database.engine, database.release_engine):
            # These engines are module globals shared by the whole suite. An
            # earlier module can leave connections checked in that were made on
            # its own event loop, now closed (and perhaps to another database);
            # handed to a route here, such a connection fails and the route
            # answers 500. Drop the old pool untouched (close=False: its
            # connections belong to a loop that no longer runs), so every
            # connection this check uses is new and made through the redirect.
            await eng.dispose(close=False)
            event.listen(eng.sync_engine, "do_connect", self._redirect)
        self.app = _app()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
                                        base_url="http://ticket-redaction.test")
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()
        for eng in (database.engine, database.release_engine):
            await eng.dispose()
            event.remove(eng.sync_engine, "do_connect", self._redirect)
        await self.seed.dispose()
        return False

    def _record(self, conn, cursor, statement, parameters, context, executemany):
        self.sent.append(statement)

    async def ex(self, sql, params=None):
        async with self.seed.begin() as conn:
            await conn.execute(text(sql), params or {})

    async def event_comments(self, rid):
        """Every non-NULL bug_report_events.comment of a report, oldest first."""
        async with self.seed.connect() as conn:
            return [r[0] for r in (await conn.execute(text(
                "SELECT comment FROM bug_report_events WHERE bug_report_id = CAST(:i AS uuid)"
                " AND comment IS NOT NULL ORDER BY created_at, id"), {"i": str(rid)})).all()]

    async def legacy_event(self, rid, comment):
        """A comment row written the way a build before the rule wrote it: raw,
        unnotified. Returns the event id."""
        eid = str(uuid.uuid4())
        await self.ex(
            "INSERT INTO bug_report_events (id, bug_report_id, actor_steam_id, actor_name, event_type, comment)"
            " VALUES (CAST(:e AS uuid), CAST(:i AS uuid), :a, 'fixture admin', 'comment', :c)",
            {"e": eid, "i": str(rid), "a": ADMIN, "c": comment})
        return eid

    async def bug_number(self, rid):
        async with self.seed.connect() as conn:
            return (await conn.execute(text(
                "SELECT bug_number FROM bug_reports WHERE id = CAST(:i AS uuid)"), {"i": str(rid)})).scalar()

    async def linked_reporter(self):
        """The reporter's player row with REPORTER_DISCORD linked: the reply
        path's ownership check. Through the ORM, whose Python-side defaults
        fill the many NOT NULL columns a raw INSERT would have to name."""
        async with AsyncSession(self.seed) as s:
            s.add(models.Player(steam_id=REPORTER, display_name="fixture player",
                                discord_id=REPORTER_DISCORD))
            await s.commit()

    async def row(self, rid):
        async with self.seed.connect() as conn:
            return (await conn.execute(text(
                "SELECT description, repro_steps, log_filename FROM bug_reports WHERE id = CAST(:i AS uuid)"),
                {"i": str(rid)})).mappings().first()

    def stored_bundle(self, fname) -> str:
        return gzip.decompress((self.log_dir / fname).read_bytes()).decode("utf-8")

    async def legacy_report(self, log_text, description, repro_steps):
        """A row and a bundle written the way a build before the rule wrote
        them: raw file, raw columns, one unnotified event, not yet posted."""
        rid = uuid.uuid4()
        fname = f"{rid}.log.gz"
        blob = gzip.compress(log_text.encode("utf-8"), compresslevel=1)
        (self.log_dir / fname).write_bytes(blob)
        await self.ex(
            "INSERT INTO bug_reports (id, steam_id, display_name, severity, category, description,"
            " repro_steps, log_filename, log_bytes)"
            " VALUES (CAST(:i AS uuid), :s, 'fixture player', 'high', 'other', :d, :r, :f, :b)",
            {"i": str(rid), "s": REPORTER, "d": description, "r": repro_steps, "f": fname, "b": len(blob)})
        await self.ex(
            "INSERT INTO bug_report_events (bug_report_id, actor_steam_id, actor_name, event_type, comment)"
            " VALUES (CAST(:i AS uuid), :a, 'fixture admin', 'comment', 'looking into it')",
            {"i": str(rid), "a": ADMIN})
        return str(rid), fname


def ok(resp):
    assert resp.status_code == 200, (resp.status_code, resp.text[:2000])
    return resp


LOG_HEAD = ("[Message:   BepInEx] BepInEx 5.4.1901 - ROUNDS\n"
            "[Info   : Unity Log] Initializing Steam\n")
LOG_TAIL = ("[Info   : Unity Log] [CR] menu ready\n"
            "[Info   : Unity Log] [CR] round 1 over: p1=1 p2=0")


def legacy_texts():
    hx_log, hx_desc, hx_repro = synthetic_hex("legacy-log"), synthetic_hex("legacy-desc", 96), \
        synthetic_hex("legacy-repro", 64, upper=False)
    log_text = LOG_HEAD + GAME_PREFIX + hx_log + "\n" + LOG_TAIL
    description = "crashed after login, log line pasted below\n" + GAME_PREFIX + hx_desc
    repro = "1. launch\n2. " + LABEL + hx_repro + " then open the menu"
    return (hx_log, hx_desc, hx_repro), (log_text, description, repro)


# ── the receive path ──────────────────────────────────────────────────────


async def _submit(env):
    values, sent = legacy_texts()
    resp = ok(await env.client.post("/api/v1/bug-reports", json={
        "steam_id": REPORTER, "display_name": "fixture player", "mod_version": "1.40.3",
        "severity": "high", "category": "other",
        "description": sent[1], "repro_steps": sent[2], "log_text": sent[0]}))
    body = resp.json()
    assert body["status"] == "received" and body["log_persisted"] is True, body
    row = await env.row(body["id"])
    return values, sent, env.stored_bundle(row["log_filename"]), row


def test_pg_submit_stores_the_marker_and_never_the_value(monkeypatch, tmp_path):
    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            return await _submit(env)

    (hx_log, hx_desc, hx_repro), (log_text, description, repro), bundle, row = run(body())
    assert_redacted(log_text, bundle, hx_log)
    assert_redacted(description, row["description"], hx_desc)
    assert_redacted(repro, row["repro_steps"], hx_repro)


def test_pg_submit_check_fails_when_the_rule_is_bypassed(monkeypatch, tmp_path):
    """Negative control for the receive path: with the rule replaced by the
    identity, the SAME check reports every field."""
    monkeypatch.setattr(log_redaction, "redact_credentials", lambda t: t)

    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            return await _submit(env)

    (hx_log, hx_desc, hx_repro), (log_text, description, repro), bundle, row = run(body())
    for sent, stored, value in ((log_text, bundle, hx_log), (description, row["description"], hx_desc),
                                (repro, row["repro_steps"], hx_repro)):
        with pytest.raises(AssertionError):
            assert_redacted(sent, stored, value)
        assert value in stored


# ── the read-back doors, over a row stored before the rule ─────────────────


async def _legacy_env_read(env, reader):
    values, sent = legacy_texts()
    rid, fname = await env.legacy_report(*sent)
    served = await reader(env, rid)
    stored = (env.stored_bundle(fname), await env.row(rid))
    return values, sent, served, stored


def _assert_still_raw_on_disk(values, sent, stored):
    """T3 is read-time redaction: the stored bundle and columns keep the text
    they were written with; only what a door SERVES changes."""
    bundle, row = stored
    assert bundle == sent[0] and values[0] in bundle
    assert row["description"] == sent[1] and row["repro_steps"] == sent[2]


def test_pg_legacy_row_detail_pane_serves_the_marker(monkeypatch, tmp_path):
    async def reader(env, rid):
        return ok(await env.client.get(f"/api/v1/bug-reports/{rid}", params={
            "admin_steam_id": ADMIN, "hmac_signature": sig("bug_reports", rid)})).json()

    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            return await _legacy_env_read(env, reader)

    (hx_log, hx_desc, hx_repro), (log_text, description, repro), served, stored = run(body())
    assert_redacted(log_text, served["log_text"], hx_log)
    assert_redacted(description, served["description"], hx_desc)
    assert_redacted(repro, served["repro_steps"], hx_repro)
    assert served["log_scrub_version"] == "2"
    _assert_still_raw_on_disk((hx_log, hx_desc, hx_repro), (log_text, description, repro), stored)


def test_pg_legacy_row_log_download_serves_the_marker(monkeypatch, tmp_path):
    async def reader(env, rid):
        resp = ok(await env.client.get(f"/api/v1/bug-reports/{rid}/log", params={
            "admin_steam_id": ADMIN, "hmac_signature": sig("bug_reports_log", rid)}))
        return resp.text, resp.headers.get("X-Scrub-Version")

    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            return await _legacy_env_read(env, reader)

    values, sent, (served, version), stored = run(body())
    assert_redacted(sent[0], served, values[0])
    assert version == "2"
    _assert_still_raw_on_disk(values, sent, stored)


def test_pg_legacy_row_admin_list_serves_the_marker(monkeypatch, tmp_path):
    async def reader(env, rid):
        reports = ok(await env.client.get("/api/v1/bug-reports", params={
            "admin_steam_id": ADMIN, "hmac_signature": sig("bug_reports", "list")})).json()["reports"]
        return [r for r in reports if r["id"] == rid]

    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            return await _legacy_env_read(env, reader)

    values, sent, served, stored = run(body())
    assert len(served) == 1, served
    assert_redacted(sent[1], served[0]["description"], values[1])
    _assert_still_raw_on_disk(values, sent, stored)


def test_pg_legacy_row_discord_feed_serves_the_marker(monkeypatch, tmp_path):
    async def reader(env, rid):
        reports = ok(await env.client.get("/api/v1/bug-reports/recent",
                                          params={"unposted": "true"})).json()["reports"]
        return [r for r in reports if r["id"] == rid]

    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            return await _legacy_env_read(env, reader)

    values, sent, served, stored = run(body())
    assert len(served) == 1, served
    assert_redacted(sent[1], served[0]["description"], values[1])
    _assert_still_raw_on_disk(values, sent, stored)


def test_pg_legacy_row_event_feed_redacts_before_the_140_character_cut(monkeypatch, tmp_path):
    async def reader(env, rid):
        events = ok(await env.client.get("/api/v1/bug-reports/events/recent",
                                         params={"unnotified": "true"})).json()["events"]
        return [e for e in events if e["bug_report_id"] == rid]

    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            values, sent = legacy_texts()
            # A second row whose ticket starts at character 116, so a cut at 140
            # made BEFORE the rule would leave 24 hex characters of it -- under
            # the rule's 32 -- in the snippet, unredacted.
            hx_cut = synthetic_hex("legacy-cut", 96)
            straddle = "x" * 100 + LABEL + hx_cut + " end"
            assert straddle.index(hx_cut) == 116
            rid_a, _ = await env.legacy_report(sent[0], sent[1], sent[2])
            rid_b, _ = await env.legacy_report(sent[0], straddle, None)
            return values, sent, (hx_cut, straddle), await reader(env, rid_a), await reader(env, rid_b)

    values, sent, (hx_cut, straddle), served_a, served_b = run(body())
    assert len(served_a) == 1 and len(served_b) == 1, (served_a, served_b)
    snippet_a, snippet_b = served_a[0]["description_snippet"], served_b[0]["description_snippet"]
    assert snippet_a == expect(sent[1], values[1])[:140]
    assert values[1][:24] not in snippet_a
    assert snippet_b == expect(straddle, hx_cut)[:140]
    assert hx_cut[:24] not in snippet_b


def test_pg_legacy_check_fails_when_the_rule_is_bypassed(monkeypatch, tmp_path):
    """Negative control for the read-back doors: with both entry points of the
    rule replaced by the identity, the SAME check reports the detail pane's
    three fields."""
    monkeypatch.setattr(log_redaction, "redact_credentials", lambda t: t)
    monkeypatch.setattr(log_redaction, "redact_credentials_counted", lambda t: (t, 0))

    async def reader(env, rid):
        return ok(await env.client.get(f"/api/v1/bug-reports/{rid}", params={
            "admin_steam_id": ADMIN, "hmac_signature": sig("bug_reports", rid)})).json()

    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            return await _legacy_env_read(env, reader)

    (hx_log, hx_desc, hx_repro), (log_text, description, repro), served, _stored = run(body())
    for sent, got, value in ((log_text, served["log_text"], hx_log),
                             (description, served["description"], hx_desc),
                             (repro, served["repro_steps"], hx_repro)):
        with pytest.raises(AssertionError):
            assert_redacted(sent, got, value)
        assert value in got


# ── the /health marker (the train's build discriminator) ──────────────────


class _Unreachable:
    """A session whose first statement fails, as an unreachable database's does."""

    async def execute(self, *a, **k):
        raise OSError("database unreachable")


def test_pg_ticket_redaction_health_carries_the_marker_on_both_arms(monkeypatch, tmp_path):
    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            api = [r for r in main.app.routes if getattr(r, "path", None) == "/api/v1/health"]
            assert len(api) == 1 and api[0].endpoint is main.health_check, api
            up = await env.client.get("/api/v1/health")
            env.app.dependency_overrides[main.get_db] = lambda: _Unreachable()
            down = await env.client.get("/api/v1/health")
            return up, down

    up, down = run(body())
    assert (up.status_code, down.status_code) == (200, 200), (up.text[:500], down.text[:500])
    up, down = up.json(), down.json()
    assert (up["status"], up["database"]) == ("ok", "connected"), up
    assert (down["status"], down["database"]) == ("degraded", "disconnected"), down
    assert up.get("ticket_redaction") == 1, up
    assert down.get("ticket_redaction") == 1, down


# ── M1: the comment receive paths, the comment store, its two read doors ───
#
# All four receive paths reach bug_report_events.comment through ONE write,
# main._record_bug_event, which applies the rule; the reporter's reply path
# also applies it before its own 2000-character cut (M2). Each case below
# reads the STORED row, which is what a read-time rule cannot fix.

LEGACY_EVENT_COMMENT = "looking into it"     # legacy_report's own event
COMMENT_HEAD = "tried it again, same crash; the log line:\n"


def _comment_with_ticket(seed, n=256):
    hx = synthetic_hex(seed, n)
    return hx, COMMENT_HEAD + GAME_PREFIX + hx + "\nthen the menu froze"


def _new_comments(stored):
    return [c for c in stored if c != LEGACY_EVENT_COMMENT]


def test_pg_admin_comment_stores_the_marker_and_never_the_value(monkeypatch, tmp_path):
    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            rid, _ = await env.legacy_report(*legacy_texts()[1])
            hx, sent = _comment_with_ticket("admin-comment")
            ok(await env.client.post(f"/api/v1/bug-reports/{rid}/comment", json={
                "admin_steam_id": ADMIN, "hmac_signature": sig("bug_reports_comment", rid),
                "comment": sent}))
            return hx, sent, await env.event_comments(rid)

    hx, sent, stored = run(body())
    new = _new_comments(stored)
    assert len(new) == 1, stored
    assert_redacted(sent, new[0], hx)


def test_pg_status_change_comments_store_the_marker_and_never_the_value(monkeypatch, tmp_path):
    """Both of the status route's writes: the comment riding a status change,
    and a comment sent with the status unchanged (the comment arm)."""
    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            rid, _ = await env.legacy_report(*legacy_texts()[1])
            (hx1, sent1), (hx2, sent2) = _comment_with_ticket("status-change"), \
                _comment_with_ticket("status-same", 96)
            for sent in (sent1, sent2):
                ok(await env.client.post(f"/api/v1/bug-reports/{rid}/status", json={
                    "admin_steam_id": ADMIN, "hmac_signature": sig("bug_reports_status", rid),
                    "new_status": "triaged", "comment": sent}))
            return (hx1, sent1, hx2, sent2), await env.event_comments(rid)

    (hx1, sent1, hx2, sent2), stored = run(body())
    new = _new_comments(stored)
    assert len(new) == 2, stored
    assert_redacted(sent1, new[0], hx1)
    assert_redacted(sent2, new[1], hx2)


def test_pg_internal_comment_stores_the_marker_and_never_the_value(monkeypatch, tmp_path):
    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            monkeypatch.setenv("API_SECRET_KEY", INTERNAL_KEY)
            rid, _ = await env.legacy_report(*legacy_texts()[1])
            hx, sent = _comment_with_ticket("internal-comment", 128)
            ok(await env.client.post(f"/api/v1/internal/bug-reports/{rid}/comment",
                                     json={"actor_name": "fixture assistant", "comment": sent},
                                     headers={"X-Internal-Key": INTERNAL_KEY}))
            return hx, sent, await env.event_comments(rid)

    hx, sent, stored = run(body())
    new = _new_comments(stored)
    assert len(new) == 1, stored
    assert_redacted(sent, new[0], hx)


def test_pg_reporter_reply_redacts_before_the_2000_character_cut(monkeypatch, tmp_path):
    """The reply the bot relays from a reporter's Discord DM. Its value starts
    at character 1976, so a cut at 2000 made BEFORE the rule would keep 24 hex
    characters of it -- under the rule's 32 -- and the store would take them."""
    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            monkeypatch.setenv("API_SECRET_KEY", INTERNAL_KEY)
            await env.linked_reporter()
            rid, _ = await env.legacy_report(*legacy_texts()[1])
            number = await env.bug_number(rid)
            hx, plain = _comment_with_ticket("reply", 64)
            hx_cut = synthetic_hex("reply-cut", 256)
            straddle = ("still happening after a relaunch. " * 60)[:1960] + LABEL + hx_cut + " end"
            assert straddle.index(hx_cut) == 1976
            for sent in (plain, straddle):
                ok(await env.client.post(
                    f"/api/v1/internal/bug-reports/by-number/{number}/user-comment",
                    json={"discord_id": REPORTER_DISCORD, "comment": sent},
                    headers={"X-Internal-Key": INTERNAL_KEY}))
            return (hx, plain, hx_cut, straddle), await env.event_comments(rid)

    (hx, plain, hx_cut, straddle), stored = run(body())
    new = _new_comments(stored)
    assert len(new) == 2, stored
    assert_redacted(plain, new[0], hx)
    assert hx_cut[:24] not in new[1], "the head of the ticket survived the cut"
    assert new[1] == expect(straddle, hx_cut)[:2000]


def test_pg_legacy_comment_is_served_redacted_on_the_bots_own_feed(monkeypatch, tmp_path):
    """THE BOT PATH. discord_bot.poll_bug_report_events polls exactly this URL
    and republishes `comment` verbatim into the reporter's DM and the bug
    thread mirror; a comment stored before the rule must leave this door
    redacted, which is what keeps the bot itself unchanged."""
    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            rid, _ = await env.legacy_report(*legacy_texts()[1])
            hx, sent = _comment_with_ticket("legacy-feed-comment")
            eid = await env.legacy_event(rid, sent)
            events = ok(await env.client.get(
                "/api/v1/bug-reports/events/recent?unnotified=true")).json()["events"]
            return hx, sent, [e for e in events if e["event_id"] == eid], await env.event_comments(rid)

    hx, sent, served, stored = run(body())
    assert len(served) == 1, served
    assert_redacted(sent, served[0]["comment"], hx)
    assert sent in stored, "the stored row changed: T3 is read-time redaction"


def test_pg_legacy_comment_is_served_redacted_in_the_detail_timeline(monkeypatch, tmp_path):
    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            rid, _ = await env.legacy_report(*legacy_texts()[1])
            hx, sent = _comment_with_ticket("legacy-detail-comment", 200)
            eid = await env.legacy_event(rid, sent)
            detail = ok(await env.client.get(f"/api/v1/bug-reports/{rid}", params={
                "admin_steam_id": ADMIN, "hmac_signature": sig("bug_reports", rid)})).json()
            return hx, sent, [e for e in detail["events"] if e["id"] == eid], await env.event_comments(rid)

    hx, sent, served, stored = run(body())
    assert len(served) == 1, served
    assert_redacted(sent, served[0]["comment"], hx)
    assert sent in stored, "the stored row changed: T3 is read-time redaction"


# ── M2: the rule before every cut, at each cut's own boundary ──────────────


def test_pg_submit_redacts_before_every_clamp(monkeypatch, tmp_path):
    """BugReportRequest's clamps. The log keeps its TAIL: its value ends 24
    characters past the 12,000,000-character cut, so a cut made first keeps
    those 24 and not the label. The description and the repro steps keep
    their HEAD: their values start at 7976, so a cut at 8000 made first keeps
    24 characters after the label -- under the rule's 32."""
    ceiling = 12_000_000
    hx_log, hx_desc = synthetic_hex("clamp-log"), synthetic_hex("clamp-desc")
    hx_repro = synthetic_hex("clamp-repro", upper=False)
    log_text = LOG_HEAD + LABEL + hx_log + filler(ceiling - 24)
    assert len(log_text) - ceiling == log_text.index(hx_log) + len(hx_log) - 24
    description = ("the menu froze right after login. " * 300)[:7960] + LABEL + hx_desc + " end"
    repro = ("1. launch 2. open the menu 3. wait " * 300)[:7960] + LABEL + hx_repro + " then quit"
    assert description.index(hx_desc) == repro.index(hx_repro) == 7976

    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            resp = ok(await env.client.post("/api/v1/bug-reports", json={
                "steam_id": REPORTER, "display_name": "fixture player", "mod_version": "1.40.3",
                "severity": "high", "category": "other",
                "description": description, "repro_steps": repro, "log_text": log_text}))
            row = await env.row(resp.json()["id"])
            return env.stored_bundle(row["log_filename"]), row

    bundle, row = run(body())
    assert hx_log[-24:] not in bundle, "the tail of the log's ticket survived the cut"
    assert bundle == expect(log_text, hx_log)[-ceiling:].strip()
    assert hx_desc[:24] not in row["description"], "the head of the description's ticket survived the cut"
    assert row["description"] == expect(description, hx_desc)[:8000].strip()
    assert hx_repro[:24] not in row["repro_steps"], "the head of the repro steps' ticket survived the cut"
    assert row["repro_steps"] == expect(repro, hx_repro)[:8000].strip()


def test_pg_legacy_bundle_over_the_read_ceiling_is_redacted_before_the_window(monkeypatch, tmp_path):
    """A stored bundle over the read ceiling, served by both doors. Its value
    ends 24 characters past where the window's tail cut falls, so a window
    cut first keeps those 24 without their label and the scrub after it
    cannot see them."""
    ceiling = main._BUG_LOG_MAX_TEXT
    hx = synthetic_hex("window", 256)
    log_text = LOG_HEAD + LABEL + hx + filler(ceiling - 24)
    assert len(log_text) - ceiling == log_text.index(hx) + len(hx) - 24

    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            rid, _ = await env.legacy_report(log_text, "window case", None)
            dl = ok(await env.client.get(f"/api/v1/bug-reports/{rid}/log", params={
                "admin_steam_id": ADMIN, "hmac_signature": sig("bug_reports_log", rid)}))
            detail = ok(await env.client.get(f"/api/v1/bug-reports/{rid}", params={
                "admin_steam_id": ADMIN, "hmac_signature": sig("bug_reports", rid)})).json()
            return dl.text, detail["log_text"]

    served_download, served_detail = run(body())
    want = BANNER + expect(log_text, hx)[-ceiling:]
    for door, served in (("download", served_download), ("detail", served_detail)):
        assert hx[-24:] not in served, f"the {door} door served the tail of the ticket"
        assert served == want, door


# ── M3: the harness refuses a wrong or populated database ─────────────────


def _drive_env_against(monkeypatch, tmp_path, probe, setup_sql, count_sql):
    """Point the harness at a sacrificial database `probe` holding what
    `setup_sql` puts there, with one canary session open on it, and enter it
    exactly as every case does. Returns what __aenter__ raised (None if it
    entered), every statement it sent, whether the canary session survived,
    and what `count_sql` reads afterwards. The database is dropped after."""
    async def body():
        lane = make_url(require_pg())
        admin = await _connect(lane, [])
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{probe}" WITH (FORCE)')
            await admin.execute(f'CREATE DATABASE "{probe}"')
        finally:
            await admin.close()
        canary = None
        try:
            canary = await _connect(lane, [], database=probe)
            await canary.execute(setup_sql)
            monkeypatch.setattr(sys.modules[__name__], "DSN",
                                lane.set(database=probe).render_as_string(hide_password=False))
            env = Env(monkeypatch, tmp_path)
            raised, entered = None, False
            try:
                await env.__aenter__()
                entered = True
            except Exception as ex:
                raised = ex
            if entered:
                await env.__aexit__(None, None, None)
            try:
                alive, rows = True, await canary.fetchval(count_sql)
            except Exception:
                alive, rows = False, None
            return raised, list(getattr(env, "sent", [])), alive, rows
        finally:
            if canary is not None:
                try:
                    await canary.close()
                except Exception:
                    pass
            admin = await _connect(lane, [])
            try:
                await admin.execute(f'DROP DATABASE IF EXISTS "{probe}" WITH (FORCE)')
            finally:
                await admin.close()

    return run(body())


def test_pg_the_harness_refuses_a_database_without_the_scratch_marker(monkeypatch, tmp_path):
    """The NAME refusal alone: the database holds only a fixture row, which
    the ROWS refusal would accept, so the name is all that stands between its
    sessions and tables and the terminate and DROP."""
    probe = f"ticket_redaction_gate_probe_{os.getpid()}"
    assert not SCRATCH_DB_RE.fullmatch(probe)
    raised, sent, alive, rows = _drive_env_against(
        monkeypatch, tmp_path, probe,
        f"CREATE TABLE players (steam_id varchar(32)); INSERT INTO players VALUES ('{REPORTER}')",
        "SELECT count(*) FROM players")
    assert isinstance(raised, RuntimeError), f"the harness entered {probe!r}: {raised!r}"
    assert repr(probe) in str(raised) and SCRATCH_MARKER in str(raised), str(raised)
    assert NAME_GATE_SQL in sent, sent
    assert [s for s in sent if _destructive(s)] == [], "a terminate or DROP was sent before the refusal"
    assert alive and rows == 1, "the canary session or its table did not survive the refusal"


@pytest.mark.parametrize("setup_sql,table", [
    (f"CREATE TABLE players (steam_id varchar(32)); INSERT INTO players VALUES ('{OUTSIDER}')",
     "players"),
    ("CREATE TABLE bug_report_events (actor_steam_id varchar(32));"
     f" INSERT INTO bug_report_events VALUES ('{OUTSIDER}')", "bug_report_events"),
    ("CREATE TABLE shop_items (id int); INSERT INTO shop_items VALUES (1)", "shop_items"),
    ("CREATE TABLE matches (id int); INSERT INTO matches VALUES (1)", "matches"),
], ids=["players", "events", "shop_items", "foreign_table"])
def test_pg_the_harness_refuses_a_populated_scratch_database(monkeypatch, tmp_path, setup_sql, table):
    """The ROWS refusal: a database named with the marker, holding a row keyed
    on someone other than this harness's fixtures, a shop item, or a table the
    harness never creates."""
    probe = f"{SCRATCH_MARKER}_gate_populated_{os.getpid()}"
    assert SCRATCH_DB_RE.fullmatch(probe)
    raised, sent, alive, rows = _drive_env_against(
        monkeypatch, tmp_path, probe, setup_sql, f"SELECT count(*) FROM {table}")
    assert isinstance(raised, RuntimeError), f"the harness entered a populated {probe!r}: {raised!r}"
    assert repr(probe) in str(raised) and table in str(raised), str(raised)
    assert NAME_GATE_SQL in sent and any(ROWS_GATE_TAG in s for s in sent), sent
    assert [s for s in sent if _destructive(s)] == [], "a terminate or DROP was sent before the refusal"
    assert alive and rows == 1, "the canary session or its row did not survive the refusal"


# ── L6: the automatic post-match upload, as a CONTRACT ────────────────────
#
# POST /api/v1/logs/auto (backend/api/auto_logs.py on the v1.41.0 branches)
# is not on this tree. The contract every tree where it exists must meet:
# the shared scrub, main._scrub_pass_one -- which carries the credential rule
# -- runs on the upload BEFORE its bundle is written, and a ticket straddling
# the upload's own clamp is not stored in part. The two cases against the
# real route skip here and run at merge; the third runs the same checker here
# against ticket_redaction_autolog_standin, which carries the real route's
# write path, and the controls plant the defects in it.

AUTO_ROUTE = "/api/v1/logs/auto"
STANDIN_ROUTE = "/api/v1/ticket-redaction-standin/logs/auto"
AUTO_TOKEN = "ticket-redaction-session-token"


def _auto_log_route():
    hits = [r for r in main.app.routes
            if getattr(r, "path", None) == AUTO_ROUTE and "POST" in (getattr(r, "methods", None) or ())]
    return hits[0] if hits else None


def _auto_log_ceiling():
    import schemas
    return getattr(schemas, "BUG_REPORT_LOG_MAX_CHARS", 12_000_000)


def _require_auto_log_route():
    route = _auto_log_route()
    if route is None:
        pytest.skip("POST /api/v1/logs/auto is not on this tree (backend/api/auto_logs.py lives on the "
                    "v1.41.0 branches): this case runs at merge, when the route lands. The same checker "
                    "runs here against the stand-in (test_pg_auto_log_contract_holds_on_the_stand_in).")
    return route


class _ScrubSpy:
    """main._scrub_pass_one for one case, writing down at each call which
    files the bundle directory held when the call began."""

    def __init__(self, monkeypatch, log_dir):
        self.real, self.log_dir, self.calls = main._scrub_pass_one, log_dir, []
        monkeypatch.setattr(main, "_scrub_pass_one", self)

    def __call__(self, body):
        self.calls.append(set(os.listdir(self.log_dir)))
        return self.real(body)


async def _auto_upload(env, spy, path, log_text):
    """POST one automatic upload; (the scrub calls it made, its bundle file
    name, the bundle it stored)."""
    before = len(spy.calls)
    resp = ok(await env.client.post(path, json={"steam_id": REPORTER, "log_text": log_text},
                                    headers={"X-Session-Token": AUTO_TOKEN}))
    fname = f"{resp.json()['id']}.log.gz"
    return spy.calls[before:], fname, env.stored_bundle(fname)


def _assert_scrubbed_before_the_write(calls, fname):
    assert calls, "the shared scrub, main._scrub_pass_one, never ran on this upload"
    assert any(fname not in listing for listing in calls), \
        "the shared scrub ran only after this upload's bundle was written"


async def _arm_the_real_auto_route(env, monkeypatch):
    """What the real route reads before its body: a session row for the token,
    and the strict session check (satisfied for REPORTER only)."""
    await env.ex("CREATE TABLE steam_sessions (token_hash text PRIMARY KEY, steam_id varchar(32) NOT NULL)")
    await env.ex("INSERT INTO steam_sessions (token_hash, steam_id) VALUES (:h, :s)",
                 {"h": hashlib.sha256(AUTO_TOKEN.encode()).hexdigest(), "s": REPORTER})

    async def session_ok(request, steam_id, db):
        return steam_id == REPORTER

    monkeypatch.setattr(main, "_strict_steam_session_ok", session_ok)
    route = _auto_log_route()
    env.app.add_api_route(route.path, route.endpoint, methods=["POST"])


def test_pg_auto_log_route_scrubs_before_it_writes(monkeypatch, tmp_path):
    _require_auto_log_route()

    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            await _arm_the_real_auto_route(env, monkeypatch)
            spy = _ScrubSpy(monkeypatch, tmp_path)
            hx = synthetic_hex("auto-real", 256)
            sent = LOG_HEAD + GAME_PREFIX + hx + "\n" + LOG_TAIL
            return (hx, sent), await _auto_upload(env, spy, AUTO_ROUTE, sent)

    (hx, sent), (calls, fname, stored) = run(body())
    _assert_scrubbed_before_the_write(calls, fname)
    assert_redacted(sent.strip(), stored, hx)


def test_pg_auto_log_route_redacts_before_its_clamp(monkeypatch, tmp_path):
    _require_auto_log_route()
    ceiling = _auto_log_ceiling()

    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            await _arm_the_real_auto_route(env, monkeypatch)
            spy = _ScrubSpy(monkeypatch, tmp_path)
            hx = synthetic_hex("auto-real-cut", 256)
            sent = LOG_HEAD + LABEL + hx + filler(ceiling - 24)
            return hx, await _auto_upload(env, spy, AUTO_ROUTE, sent)

    hx, (calls, fname, stored) = run(body())
    _assert_scrubbed_before_the_write(calls, fname)
    assert hx[-24:] not in stored, "the upload stored the tail of a ticket its clamp cut from its label"


def test_pg_auto_log_contract_holds_on_the_stand_in(monkeypatch, tmp_path):
    """L6 on this tree: both checks above, run against the stand-in. The
    controls turn this RED with no scrub, with the scrub after the write and
    with the clamp before the rule, and keep it GREEN with an extra inert
    scrub call after the write -- the contract asks for a scrub BEFORE the
    write, not for exactly one."""
    ceiling = standin.LOG_MAX_CHARS

    async def body():
        async with Env(monkeypatch, tmp_path) as env:
            env.app.include_router(standin.router)
            spy = _ScrubSpy(monkeypatch, tmp_path)
            hx = synthetic_hex("auto-standin", 256)
            plain = LOG_HEAD + GAME_PREFIX + hx + "\n" + LOG_TAIL
            hx_cut = synthetic_hex("auto-standin-cut", 256)
            straddle = LOG_HEAD + LABEL + hx_cut + filler(ceiling - 24)
            return ((hx, plain, await _auto_upload(env, spy, STANDIN_ROUTE, plain)),
                    (hx_cut, straddle, await _auto_upload(env, spy, STANDIN_ROUTE, straddle)))

    (hx, plain, (calls, fname, stored)), (hx_cut, straddle, (calls2, fname2, stored2)) = run(body())
    _assert_scrubbed_before_the_write(calls, fname)
    assert_redacted(plain.strip(), stored, hx)
    _assert_scrubbed_before_the_write(calls2, fname2)
    assert hx_cut[-24:] not in stored2, "the upload stored the tail of a ticket its clamp cut from its label"
    assert stored2 == expect(straddle, hx_cut)[-ceiling:].strip()
