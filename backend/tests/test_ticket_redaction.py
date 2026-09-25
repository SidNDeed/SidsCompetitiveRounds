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
  * /api/v1/health: `ticket_redaction` == 1 on both arms.

Every ticket value here is COMPOSED at run time from a SHA-256 of a fixture
label: no hex run of ticket length is written in this file, so a pin or a lane
folder carrying it is not itself a credential hit for the scanners.

Live PostgreSQL is REQUIRED for the test_pg_ cases, and a missing DSN FAILS,
naming the variable (the harness shape of test_ffa_quarantine_triage.py):
    TICKET_REDACTION_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    TICKET_REDACTION_TEST_PG_OPTOUT=1   says out loud that this run skips them
Each case drops and recreates its own tables in that database.
"""

import asyncio
import gzip
import hashlib
import hmac
import inspect
import os
import subprocess
import sys
import uuid

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

import database
import log_redaction
import main
import models

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
DROP TABLE IF EXISTS shop_items CASCADE
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

# (path, method) in registration order: the two feeds before {report_id}.
ROUTES = (
    ("/api/v1/bug-reports", "POST"),
    ("/api/v1/bug-reports", "GET"),
    ("/api/v1/bug-reports/events/recent", "GET"),
    ("/api/v1/bug-reports/recent", "GET"),
    ("/api/v1/bug-reports/{report_id}", "GET"),
    ("/api/v1/bug-reports/{report_id}/log", "GET"),
    ("/api/v1/health", "GET"),
)


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


async def _clean_slate(url):
    """#753: a case starts from a slate it TAKES -- every other backend on the
    lane database is ended first, so a lock a dead case left behind cannot
    hold this one's DDL. The lane database is this file's alone."""
    import asyncpg
    conn = await asyncpg.connect(host=url.host, port=url.port, user=url.username,
                                 password=url.password or None, database=url.database)
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
        await _clean_slate(self.url)
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
        self.seed = create_async_engine(require_pg(), pool_size=2, max_overflow=4)
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

    async def ex(self, sql, params=None):
        async with self.seed.begin() as conn:
            await conn.execute(text(sql), params or {})

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
        blob = gzip.compress(log_text.encode("utf-8"))
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
