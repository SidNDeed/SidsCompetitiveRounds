"""Opt-in automatic post-match log upload — the server half (v1.41.0 Item 3).

This file was written while the route was INERT — no client called
POST /api/v1/logs/auto — which is exactly the condition under which a feature
ships doing nothing while every log line looks clean (#438/#443). So it drives
the handler directly against a scripted session and asserts the POSITIVE things
a real call produces — a kind='auto' row, a blob on disk with the OS username
gone, and the [AUTO-LOG] line — rather than the absence of errors. It is still
worth doing that way, but the premise has changed: the CLIENT half landed in
the same release, so a player who turns the Settings toggle on does reach this
handler. `test_auto_log_client.py` is the other half.

Mutation controls are explicit where the assertion would otherwise pass for
the wrong reason: the scrub test re-runs with the scrub neutered and requires
the check to FAIL, and the clamp test requires the 64-character ceiling (the
one the plan cited by mistake) to be the wrong answer.
"""
import ast
import asyncio
import gzip
import inspect
import json
import os
import pathlib
import re
import sys
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import auto_logs  # noqa: E402
import main  # noqa: E402
import schemas  # noqa: E402

STEAM = "76561198040410653"
OTHER = "76561198720512419"
TOKEN = "a-session-token"
WINPATH = r"C:\Users\Someone\AppData\Roaming\ROUNDS\BepInEx\LogOutput.log"
BUNDLE = ("=== LogOutput.log (" + WINPATH + ") ===\n"
          "[Info   :CompetitiveRounds] round over\n"
          "discord_id: 123456789012345678\n")

COUNT_KEY = "SELECT COUNT(*) FROM bug_reports WHERE steam_id = :sid AND kind = 'auto'"
PLAYER_KEY = "SELECT id FROM players WHERE steam_id = :sid"
INSERT_KEY = "INSERT INTO bug_reports"
SESSION_KEY = "FROM steam_sessions"
PID = UUID("0b7d2f8e-3c4a-4c2a-9b1e-2f3a4b5c6d7e")


def _run(coro):
    return asyncio.run(coro)


def _code_of(fn):
    """A function's source with comment-only lines removed and whitespace
    normalised. Counting a SQL predicate in raw source counts the comment
    that explains it too, which turns "both arms are gated" into a number
    that moves when the prose does."""
    lines = [ln for ln in inspect.getsource(fn).splitlines()
             if not ln.strip().startswith("#")]
    return " ".join(" ".join(lines).split())


# ── fakes ────────────────────────────────────────────────────────────────────

class _Res:
    def __init__(self, value):
        self.value = value

    def _rows(self):
        return list(self.value) if isinstance(self.value, list) else []

    def mappings(self):
        return self

    def all(self):
        return self._rows()

    def first(self):
        rows = self._rows()
        return rows[0] if rows else None

    def scalar(self):
        if isinstance(self.value, list):
            row = self.first()
            return None if row is None else next(iter(row.values()))
        return self.value


class Scripted:
    """execute() answers by the first script key contained in the normalised
    SQL; each key holds a queue of results (the last one repeats)."""

    def __init__(self, script=None, fail_on=None, fail_commit=False):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        # `fail_commit` models the one failure the handler cannot resolve: the
        # INSERT succeeded, commit() raised, and whether the server committed
        # is unknowable from here.
        self.fail_commit = fail_commit
        # The route resolves the session token BEFORE reading the body, so
        # every test whose subject is post-authentication behaviour needs that
        # lookup to answer. Default it to a bound session; a test that wants an
        # unknown or mismatched token passes SESSION_KEY explicitly and wins,
        # because setdefault does not overwrite. Four tests already do exactly
        # that, and they are the ones that own the session question.
        self.script.setdefault(SESSION_KEY, [[{"steam_id": STEAM}]])
        self.fail_on = fail_on
        self.log = []
        self.committed = 0
        self.rolled_back = 0

    def begin_nested(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.log.append((sql, params))
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("scripted statement failure")
        for key, queue in self.script.items():
            if key in sql:
                if not queue:
                    return _Res([])
                return _Res(queue.pop(0) if len(queue) > 1 else queue[0])
        return _Res([])

    async def commit(self):
        if self.fail_commit:
            raise RuntimeError("scripted commit failure")
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1

    def sql_for(self, key):
        return [sql for sql, _ in self.log if key in sql]

    def params_for(self, key):
        return [p for sql, p in self.log if key in sql]


class _Req:
    """Enough Request for this handler: headers and a streamed body."""

    def __init__(self, body=b"", headers=None, explode_on_stream=False):
        self._body = body
        self.headers = _Headers(headers or {})
        self.explode_on_stream = explode_on_stream
        self.streamed = False

    async def stream(self):
        self.streamed = True
        if self.explode_on_stream:
            raise AssertionError("the body was read for a request that must be refused first")
        # Two chunks, so the running cap is exercised rather than a single
        # len() on a whole body.
        half = len(self._body) // 2
        yield self._body[:half]
        yield self._body[half:]


class _Headers:
    def __init__(self, d):
        self._d = {k.lower(): v for k, v in d.items()}

    def get(self, k, default=None):
        return self._d.get(k.lower(), default)


def _body(**over):
    payload = {"steam_id": STEAM, "display_name": "Sid", "mod_version": "1.41.0",
               "game_version": "1.0.0", "mode": "ranked_1v1", "room_name": "SCR-7788",
               "opponent_steam_id": OTHER, "series_id": "s-1", "log_text": BUNDLE}
    payload.update(over)
    return json.dumps(payload).encode("utf-8")


def _request(body=None, token=TOKEN, **kw):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Session-Token"] = token
    return _Req(body if body is not None else _body(), headers, **kw)


@pytest.fixture
def logdir(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "BUG_REPORT_LOG_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def verified(monkeypatch):
    async def _ok(request, steam_id, db):
        return True
    monkeypatch.setattr(main, "_strict_steam_session_ok", _ok)


@pytest.fixture(autouse=True)
def no_opportunistic_prune(monkeypatch):
    """The prune has its own tests; keep it out of the upload assertions."""
    monkeypatch.setattr(auto_logs, "_LAST_PRUNE", [1e12])


def _ok_db(auto_count=0, player=True):
    return Scripted({
        COUNT_KEY: [[{"count": auto_count}]],
        PLAYER_KEY: [[{"id": PID}] if player else []],
        INSERT_KEY: [[{"bug_number": 4242}]],
    })


# ── the accepted upload ──────────────────────────────────────────────────────

def test_an_accepted_upload_writes_a_kind_auto_row_and_its_blob(logdir, verified, capsys):
    db = _ok_db()
    out = _run(auto_logs.upload_auto_log(_request(), db))

    assert out["status"] == "received" and out["bug_number"] == 4242
    assert out["log_persisted"] is True and out["log_bytes"] > 0
    # The scrub RAN, which is a different fact from "the result looks clean".
    assert out["scrubbed"] == {"os_user": 1, "discord_id": 1}

    insert = db.sql_for(INSERT_KEY)
    assert len(insert) == 1, insert
    assert "'auto'" in insert[0], insert[0]
    p = db.params_for(INSERT_KEY)[0]
    assert p["sid"] == STEAM and p["pid"] == str(PID)
    assert p["descr"] == "auto-upload after ranked_1v1 in SCR-7788"
    assert "opponent: " + OTHER in p["repro"] and "series: s-1" in p["repro"]
    assert db.committed == 1

    blob = logdir / (out["id"] + ".log.gz")
    assert blob.exists() and blob.stat().st_size == out["log_bytes"] == p["fbytes"]

    # The positive signal a grep of the api log looks for.
    assert "[AUTO-LOG] #4242" in capsys.readouterr().out


def test_the_stored_blob_no_longer_carries_the_windows_username(logdir, verified):
    db = _ok_db()
    out = _run(auto_logs.upload_auto_log(_request(), db))
    stored = gzip.decompress((logdir / (out["id"] + ".log.gz")).read_bytes()).decode()

    assert "Someone" not in stored, "the OS username survived the write-time scrub"
    assert "123456789012345678" not in stored
    # ...and the diagnostic content did NOT go with it.
    assert "[os-user]" in stored and "round over" in stored


def test_the_username_check_would_fail_if_the_scrub_were_not_applied(logdir, verified, monkeypatch):
    """Negative control for the test above: with the scrub neutered the
    stored blob must still contain the username, or that test proves nothing
    (it could be passing because the fixture never had one)."""
    def _identity(body):
        return body, {"os_user": 0, "discord_id": 0}, []
    monkeypatch.setattr(main, "_scrub_pass_one", _identity)

    db = _ok_db()
    out = _run(auto_logs.upload_auto_log(_request(), db))
    stored = gzip.decompress((logdir / (out["id"] + ".log.gz")).read_bytes()).decode()
    assert "Someone" in stored


def test_the_row_carries_no_bug_report_event_so_the_dm_poll_never_sees_it(logdir, verified):
    db = _ok_db()
    _run(auto_logs.upload_auto_log(_request(), db))
    assert db.sql_for("bug_report_events") == []


# ── authentication ───────────────────────────────────────────────────────────

def test_every_refusal_on_the_upload_route_says_so_in_the_log(logdir, capsys):
    """The module docstring promises the [AUTO-LOG] prefix is on the refusal
    lines too, so that a bare [AUTO-LOG] answers "has the route been reached
    at all" and its ABSENCE means no client has ever called it.

    Six branches used to print nothing, and the silent set included the most
    likely steady-state refusal: a session that is unverified or expired.
    A deployment whose client half had a slightly wrong token lifetime would
    have produced zero rows, zero log lines, and an api log a reviewer would
    correctly read -- per the docstring -- as "never called". That is the
    inert-ship condition of #438/#443 wearing the costume of a working
    feature, and it is the exact reading the docstring licenses.

    Each case below asserts the marker, not the status code; the status codes
    already have their own tests above.

    Deliberately does NOT take the `verified` fixture. That fixture stubs
    _strict_steam_session_ok to return True, which forces case 4 to succeed
    and makes the assertion unfailable -- the first draft of this test took
    it and case 4 accepted the upload. Cases 1-3 are refused before the
    session check runs and case 5 never reaches it, so none of them need it.
    """
    # 1. no session token at all
    capsys.readouterr()
    with pytest.raises(HTTPException):
        _run(auto_logs.upload_auto_log(_request(token=None, explode_on_stream=True), Scripted()))
    assert "[AUTO-LOG]" in capsys.readouterr().out

    # 2. a body that is not JSON
    capsys.readouterr()
    with pytest.raises(HTTPException):
        _run(auto_logs.upload_auto_log(_request(body=b"{not json"), Scripted()))
    assert "[AUTO-LOG]" in capsys.readouterr().out

    # 3. a body that parses but is not an object
    capsys.readouterr()
    with pytest.raises(HTTPException):
        _run(auto_logs.upload_auto_log(_request(body=b'"a string"'), Scripted()))
    assert "[AUTO-LOG]" in capsys.readouterr().out

    # 4. a session token bound to a different account -- the one that matters
    capsys.readouterr()
    db = Scripted({
        SESSION_KEY: [[{"steam_id": OTHER, "verified": True,
                        "expires_at": datetime.now(timezone.utc) + timedelta(days=1)}]],
        COUNT_KEY: [[{"count": 0}]],
    })
    with pytest.raises(HTTPException):
        _run(auto_logs.upload_auto_log(_request(), db))
    assert "[AUTO-LOG]" in capsys.readouterr().out

    # 5. over the byte ceiling, before anything else runs
    capsys.readouterr()
    with pytest.raises(HTTPException):
        _run(auto_logs._read_capped_body(_Req(b"x" * 64, {"X-Session-Token": TOKEN}), 8))
    assert "[AUTO-LOG]" in capsys.readouterr().out


def test_no_refusal_path_on_the_upload_route_is_silent():
    """Structural guard for the class, since the test above can only cover
    the refusals that exist today.

    A future branch that raises without logging would reopen exactly the hole
    just closed, and would do it invisibly -- the suite would stay green. The
    exemption list is ONE entry and was derived by measuring the file, not
    assumed: the internal prune route's key check answers to an operator, not
    to the client grep contract this docstring is about. If that list needs to
    grow, the growth should be argued for here.
    """
    import io as _io
    src = _io.open(auto_logs.__file__, encoding="utf-8", newline="").read()

    # Per BLOCK, not per ten-line window. The window version accepted a marker
    # belonging to a DIFFERENT branch, or one merely mentioned in a comment:
    # deleting the empty-log print left this test green because the
    # session-failure print sat eight lines above it. That is the defect this
    # very test exists to catch, in the test itself.
    def _is_marker_print(node):
        return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "print"
                and "[AUTO-LOG]" in ast.dump(node.value))

    def _is_refusal(node):
        return (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
                and isinstance(node.exc.func, ast.Name)
                and node.exc.func.id == "HTTPException")

    silent = []
    for parent in ast.walk(ast.parse(src)):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(parent, field, None)
            if not isinstance(block, list):
                continue
            for i, stmt in enumerate(block):
                if _is_refusal(stmt) and not any(_is_marker_print(s) for s in block[:i]):
                    silent.append(ast.unparse(stmt))

    assert silent == [
        "raise HTTPException(status_code=403, detail='Invalid internal key')"
    ], ("a refusal path in auto_logs.py raises without printing [AUTO-LOG] "
        "first. The module docstring promises the prefix is on the refusal "
        "lines, and a silent refusal makes a fully-refused feature "
        "indistinguishable from one no client has called (#438/#443). "
        "Unexpected silent raises: %s" % silent)


def test_a_request_with_no_session_token_is_refused_before_its_body_is_read(logdir):
    db = Scripted()
    req = _request(token=None, explode_on_stream=True)
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.upload_auto_log(req, db))
    assert e.value.status_code == 401
    # The point of the assertion: FastAPI would have parsed a declared body
    # parameter before the handler ran, so "401" alone does not show that the
    # megabytes were never materialised (#388).
    assert req.streamed is False
    assert db.log == []


def test_a_token_that_names_another_account_cannot_upload_for_this_one(logdir):
    """The real strict check, not a stub: a session row bound to OTHER must
    not authorise a body claiming STEAM."""
    db = Scripted({
        SESSION_KEY: [[{"steam_id": OTHER, "verified": True,
                        "expires_at": datetime.now(timezone.utc) + timedelta(days=1)}]],
        COUNT_KEY: [[{"count": 0}]],
    })
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.upload_auto_log(_request(), db))
    assert e.value.status_code == 401
    assert db.sql_for(INSERT_KEY) == []
    assert list(logdir.iterdir()) == []


def test_the_same_token_bound_to_this_account_is_accepted(logdir):
    """Positive control for the test above — otherwise a 401 from any cause
    would look like the mismatch being caught."""
    db = Scripted({
        SESSION_KEY: [[{"steam_id": STEAM, "verified": True,
                        "expires_at": datetime.now(timezone.utc) + timedelta(days=1)}]],
        COUNT_KEY: [[{"count": 0}]],
        PLAYER_KEY: [[{"id": PID}]],
        INSERT_KEY: [[{"bug_number": 7}]],
    })
    out = _run(auto_logs.upload_auto_log(_request(), db))
    assert out["bug_number"] == 7


def test_an_unverified_session_row_is_refused(logdir):
    db = Scripted({
        SESSION_KEY: [[{"steam_id": STEAM, "verified": False,
                        "expires_at": datetime.now(timezone.utc) + timedelta(days=1)}]],
    })
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.upload_auto_log(_request(), db))
    assert e.value.status_code == 401


# ── the bodies this route refuses ────────────────────────────────────────────

def test_a_body_over_the_ceiling_is_refused_while_it_streams(logdir, verified):
    monkey = b"x" * 64
    req = _Req(monkey, {"X-Session-Token": TOKEN})
    with pytest.raises(HTTPException) as e:
        _run(auto_logs._read_capped_body(req, 8))
    assert e.value.status_code == 413


def test_a_declared_content_length_over_the_ceiling_is_refused_before_the_stream(logdir):
    req = _Req(b"{}", {"X-Session-Token": TOKEN, "Content-Length": str(99 * 1024 * 1024)},
               explode_on_stream=True)
    with pytest.raises(HTTPException) as e:
        _run(auto_logs._read_capped_body(req, auto_logs.AUTO_LOG_MAX_BODY_BYTES))
    assert e.value.status_code == 413
    assert req.streamed is False


def test_malformed_json_is_a_400(logdir, verified):
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.upload_auto_log(_request(body=b"{not json"), Scripted()))
    assert e.value.status_code == 400


def test_an_unescaped_control_character_is_refused_and_says_so(logdir, verified, capsys):
    """Bug #31 / learning #100 on the bug-report path: the client builds this
    JSON by hand and a raw TAB/NUL/ESC inside the log string makes a strict
    decoder reject the whole request. The refusal must be greppable, because
    on a route with no caller yet it is the first thing anyone will look for."""
    body = b'{"steam_id": "' + STEAM.encode() + b'", "log_text": "a\x1braw escape"}'
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.upload_auto_log(_request(body=body), Scripted()))
    assert e.value.status_code == 400
    assert "[AUTO-LOG] malformed body" in capsys.readouterr().out
    # Negative control: the same body with the control char escaped is fine,
    # so the refusal is about the escaping and not about the shape.
    ok = b'{"steam_id": "' + STEAM.encode() + b'", "log_text": "a\\u001braw escape"}'
    req = auto_logs.AutoLogRequest.model_validate(json.loads(ok.decode()))
    assert req.log_text == "a\x1braw escape"


def test_an_upload_with_no_log_is_refused_rather_than_stored_empty(logdir, verified):
    db = _ok_db()
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.upload_auto_log(_request(body=_body(log_text="   ")), db))
    assert e.value.status_code == 400
    assert db.sql_for(INSERT_KEY) == []
    assert list(logdir.iterdir()) == []


# ── the two budgets ──────────────────────────────────────────────────────────

def test_the_auto_bucket_fills_at_twelve_and_counts_only_auto_rows(logdir, verified):
    db = _ok_db(auto_count=auto_logs.AUTO_LOG_PER_STEAM_PER_DAY)
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.upload_auto_log(_request(), db))
    assert e.value.status_code == 429
    count_sql = db.sql_for("FROM bug_reports")[0]
    assert "kind = 'auto'" in count_sql, count_sql
    assert db.sql_for(INSERT_KEY) == []


def test_one_below_the_cap_still_lands(logdir, verified):
    db = _ok_db(auto_count=auto_logs.AUTO_LOG_PER_STEAM_PER_DAY - 1)
    assert _run(auto_logs.upload_auto_log(_request(), db))["bug_number"] == 4242


def test_the_report_budget_no_longer_counts_automatic_uploads():
    """Bucket separation is two halves and neither works alone: this is the
    half that lives in main.submit_bug_report."""
    src = _code_of(main.submit_bug_report)
    assert "WHERE steam_id = :sid AND kind = 'report' AND created_at >= :cutoff" in src
    # The un-gated form this replaced, so the assertion above cannot be
    # satisfied by a second count sitting beside the original one.
    assert "FROM bug_reports WHERE steam_id = :sid AND created_at >= :cutoff" not in src


def test_the_discord_feed_excludes_automatic_uploads_on_both_arms():
    """recent_bug_reports is what the bot turns into #bug-reports posts. Both
    arms — the rolling window and the unposted-ack variant — must be gated, or
    a bot restart announces every auto upload of the last seven days."""
    src = _code_of(main.recent_bug_reports)
    assert src.count("kind = 'report'") == 2, src
    assert 'where = "created_at >= :cutoff"' not in src


# ── the clamp the plan got wrong ─────────────────────────────────────────────

def test_the_log_clamp_is_the_twelve_million_one_and_keeps_the_tail():
    assert schemas.BUG_REPORT_LOG_MAX_CHARS == 12_000_000
    cap = schemas.BUG_REPORT_LOG_MAX_CHARS
    req = auto_logs.AutoLogRequest(steam_id=STEAM, log_text=("A" * 10) + ("B" * cap))
    assert len(req.log_text) == cap
    assert req.log_text[0] == "B" and "A" not in req.log_text[:100]


def test_a_log_longer_than_the_short_field_ceiling_is_not_truncated_to_it():
    """The specific defect the plan's wrong anchor would have produced: the
    64-character _clamp_short applied to log_text. A 5000-character bundle
    must arrive whole."""
    body = "L" * 5000
    req = auto_logs.AutoLogRequest(steam_id=STEAM, log_text=body)
    assert req.log_text == body
    # ...while the short fields really are clamped, so the test above is not
    # passing because no clamp runs at all.
    assert len(auto_logs.AutoLogRequest(steam_id="9" * 200, log_text="x").steam_id) == 32


def test_each_short_field_is_clamped_to_its_own_column_width():
    """One width for all the short fields is how a value passes validation
    and then fails the INSERT: bug_reports.steam_id is VARCHAR(32) while
    display_name is VARCHAR(64)."""
    req = auto_logs.AutoLogRequest(steam_id="9" * 99, display_name="n" * 99,
                                   mod_version="v" * 99, game_version="g" * 99,
                                   room_name="r" * 99, opponent_steam_id="o" * 99,
                                   log_text="x")
    assert len(req.steam_id) == 32 and len(req.opponent_steam_id) == 32
    assert len(req.mod_version) == 32 and len(req.game_version) == 32
    assert len(req.display_name) == 64 and len(req.room_name) == 64


# ── failure directions ───────────────────────────────────────────────────────

def test_a_blob_that_cannot_be_written_produces_no_row(logdir, verified, monkeypatch):
    monkeypatch.setattr(main, "BUG_REPORT_LOG_DIR", str(logdir / "nope" / "\0bad"))
    db = _ok_db()
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.upload_auto_log(_request(), db))
    assert e.value.status_code == 503
    assert db.sql_for(INSERT_KEY) == []


def test_an_insert_that_fails_takes_its_blob_with_it(logdir, verified):
    """A failed INSERT is DETERMINATE: no row, so no blob, and a 503.

    This used to assert a bare `RuntimeError`, i.e. the re-raise that the stack
    renders 500. Three things disagreed: the module docstring promises 503 for
    a failed half, this test pinned 500, and
    `test_a_body_with_no_steam_id_is_a_422_and_not_a_500` immediately below
    argues in its own docstring that a 500 tells a background retry loop to
    repeat a request that cannot succeed. Only one of the three can be right
    for a client that retries, and it is not the 500.
    """
    db = Scripted({COUNT_KEY: [[{"count": 0}]], PLAYER_KEY: [[{"id": PID}]]},
                  fail_on=INSERT_KEY)
    with pytest.raises(HTTPException) as ei:
        _run(auto_logs.upload_auto_log(_request(), db))
    assert ei.value.status_code == 503, (
        "a storage-layer failure is retryable and must say so; 500 asks the "
        "client's retry loop to resend a request that just failed")
    assert list(logdir.iterdir()) == [], "a blob survived an insert that did not"
    # ...and the session is not left in an aborted transaction for whatever
    # runs next on it.
    assert db.rolled_back == 1


def test_a_body_with_no_steam_id_is_a_422_and_not_a_500(logdir, verified):
    """A ValidationError raised inside the handler is not the one FastAPI
    turns into a 422; uncaught it would be a 500 telling a background retry
    loop to send the same unacceptable body again."""
    db = Scripted()
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.upload_auto_log(_request(body=json.dumps({"log_text": "x"}).encode()), db))
    assert e.value.status_code == 422
    # The session lookup now runs BEFORE the body is parsed, deliberately: one
    # indexed row, so a token that resolves to nothing never buys a 14 MiB
    # read. That is the ONLY statement allowed to run for a body that cannot
    # be accepted -- pinned as an exact list rather than relaxed to a count,
    # so a second query appearing here is still a failure.
    assert [sql for sql, _ in db.log] == [
        "SELECT steam_id FROM steam_sessions WHERE token_hash = :th"]


def test_a_json_body_that_is_not_an_object_is_a_400(logdir, verified):
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.upload_auto_log(_request(body=b'["a list"]'), Scripted()))
    assert e.value.status_code == 400


def test_an_unknown_player_still_uploads(logdir, verified):
    db = _ok_db(player=False)
    _run(auto_logs.upload_auto_log(_request(), db))
    assert db.params_for(INSERT_KEY)[0]["pid"] is None


# ── retention ────────────────────────────────────────────────────────────────

CANDIDATES_KEY = "SELECT id::text AS id FROM bug_reports"
ROW_KEY = "DELETE FROM bug_reports WHERE id = CAST(:id AS uuid)"
BULK_KEY = "DELETE FROM bug_reports WHERE kind = 'auto'"


class _Savepoint:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        self.mark = len(self.db.pending)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            del self.db.pending[self.mark:]          # ROLLBACK TO SAVEPOINT
        return False


class PruneDb(Scripted):
    """Scripted, plus a table: every row in it is past the cutoff. A DELETE
    removes a row only while it is still there and answers its log_filename
    (RETURNING); a savepoint that exits with an exception discards the DELETEs
    made inside it; only commit() makes a DELETE durable, so anything pending
    when the call returns was never committed.

    It answers the per-row statement AND the old bulk statement, so the
    mutation control that restores the bulk DELETE-then-unlink shape is
    measured against the same table rather than against a fake that cannot
    see it."""

    def __init__(self, rows):
        super().__init__({CANDIDATES_KEY: [[{"id": rid} for rid in rows]]})
        self.table = dict(rows)
        self.pending = []

    def begin_nested(self):
        return _Savepoint(self)

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if ROW_KEY in sql:
            self.log.append((sql, params))
            rid = params["id"]
            if rid not in self.table or rid in self.pending:
                return _Res([])
            self.pending.append(rid)
            return _Res([{"log_filename": self.table[rid]}])
        if BULK_KEY in sql:
            self.log.append((sql, params))
            gone = [rid for rid in self.table if rid not in self.pending]
            self.pending.extend(gone)
            return _Res([{"id": rid, "log_filename": self.table[rid]} for rid in gone])
        return await super().execute(statement, params)

    async def commit(self):
        await super().commit()
        for rid in self.pending:
            self.table.pop(rid, None)
        self.pending = []

    async def rollback(self):
        await super().rollback()
        self.pending = []


def test_the_prune_deletes_only_auto_rows_and_then_their_blobs(logdir):
    keep = logdir / "keep.log.gz"
    drop = logdir / "drop.log.gz"
    keep.write_bytes(b"x")
    drop.write_bytes(b"x")
    db = PruneDb({"r1": "drop.log.gz"})

    out = _run(auto_logs.prune_auto_logs(db))

    # Both statements carry the whole predicate: the listing, and the DELETE
    # that claims each row (#208). New interval arithmetic uses make_interval
    # from a typed CAST: #448's ruling, over the parameter-typing trap #275
    # documents.
    for sql in (db.sql_for(CANDIDATES_KEY)[0], db.sql_for(ROW_KEY)[0]):
        assert "kind = 'auto'" in sql, sql
        assert "make_interval(days => CAST(:days AS integer))" in sql, sql
    assert db.params_for(CANDIDATES_KEY)[0] == {"days": 14}
    assert db.params_for(ROW_KEY)[0] == {"id": "r1", "days": 14}
    assert out == {"rows": 1, "blobs": 1, "kept": 0}
    assert db.table == {} and keep.exists() and not drop.exists()


def test_a_prune_over_nothing_writes_nothing(logdir):
    db = PruneDb({})
    assert _run(auto_logs.prune_auto_logs(db)) == {"rows": 0, "blobs": 0, "kept": 0}
    assert db.sql_for(ROW_KEY) == []


def test_a_missing_blob_does_not_abort_the_sweep(logdir):
    """An absent blob is a previous sweep whose unlink landed and whose commit
    did not: the row goes, and so does a row that never had a blob."""
    db = PruneDb({"r1": "gone.log.gz", "r2": None})
    assert _run(auto_logs.prune_auto_logs(db)) == {"rows": 2, "blobs": 0, "kept": 0}
    assert db.table == {}


def test_a_blob_that_will_not_unlink_keeps_its_row_for_the_next_sweep(logdir, monkeypatch, capsys):
    """Round 2 finding 5: a failed unlink must stay discoverable and retryable.

    The old sweep deleted every row first and then swallowed each unlink's
    OSError, so a blob that would not go was named by no row, and no later
    sweep (they select by row) could find it. Now the row's DELETE rolls back
    with its savepoint, the row stays past the cutoff, one line names it, and
    the next sweep collects it once the obstacle is gone.

    Control: restore the bulk DELETE-then-unlink shape -> red (the row is
    gone, the blob is orphaned, and no line names it)."""
    stuck = logdir / "stuck.log.gz"
    fine = logdir / "fine.log.gz"
    stuck.write_bytes(b"x")
    fine.write_bytes(b"x")
    real_unlink = pathlib.Path.unlink

    def unlink(self, *a, **kw):
        if self.name == "stuck.log.gz":
            raise PermissionError(13, "Permission denied", str(self))
        return real_unlink(self, *a, **kw)

    monkeypatch.setattr(pathlib.Path, "unlink", unlink)
    db = PruneDb({"r-stuck": "stuck.log.gz", "r-fine": "fine.log.gz"})
    out = _run(auto_logs.prune_auto_logs(db))

    assert db.table == {"r-stuck": "stuck.log.gz"}, (
        "the row whose blob would not unlink did not survive the sweep: %r" % db.table)
    assert stuck.exists() and not fine.exists()
    assert out == {"rows": 1, "blobs": 1, "kept": 1}
    said = [ln for ln in capsys.readouterr().out.splitlines()
            if ln.startswith("[AUTO-LOG] prune: unlink failed for row r-stuck (")]
    assert len(said) == 1, "the kept row was not named exactly once"
    assert str(stuck) in said[0] and said[0].endswith("-- left in place for retry"), said[0]

    # Still past the cutoff, so the next sweep lists it again, and with the
    # obstacle gone it goes, blob and all.
    monkeypatch.setattr(pathlib.Path, "unlink", real_unlink)
    again = PruneDb(dict(db.table))
    assert _run(auto_logs.prune_auto_logs(again)) == {"rows": 1, "blobs": 1, "kept": 0}
    assert again.table == {} and not stuck.exists()


def test_a_row_another_sweep_already_took_keeps_its_blob_out_of_this_one(logdir):
    """Listed without a lock; the DELETE ... RETURNING is the claim. A row
    that is gone by the time this sweep reaches it is another sweep's, and so
    is its blob."""
    blob = logdir / "taken.log.gz"
    blob.write_bytes(b"x")
    db = PruneDb({"r-taken": "taken.log.gz"})
    db.table.pop("r-taken")          # listed, then taken before this sweep's DELETE
    assert _run(auto_logs.prune_auto_logs(db)) == {"rows": 0, "blobs": 0, "kept": 0}
    assert blob.exists(), "a sweep unlinked a blob whose row it did not delete"


def test_the_sweep_needs_no_upload_to_run(logdir):
    """Round 2 finding 5: retention may not wait for a future upload. The
    autouse fixture has set the upload path's throttle to "just pruned", no
    upload happens here, and a direct call (what the janitor arm makes)
    still collects everything past the cutoff."""
    old = logdir / "old.log.gz"
    old.write_bytes(b"x")
    db = PruneDb({"r-old": "old.log.gz", "r-older": None})
    assert _run(auto_logs.prune_auto_logs(db)) == {"rows": 2, "blobs": 1, "kept": 0}
    assert db.table == {} and not old.exists()
    assert db.sql_for(INSERT_KEY) == [] and db.sql_for(COUNT_KEY) == []


def _innermost_try(parents, node):
    while node is not None and not isinstance(node, ast.Try):
        node = parents.get(node)
    return node


def test_the_janitor_runs_the_retention_sweep_on_its_own_cadence():
    """Round 2 finding 5: the sweep runs from the 60 s janitor loop, hourly,
    whether or not anything is uploaded. Structural, because the arm sits in
    an endless loop a test cannot enter: exactly one call to
    auto_logs.prune_auto_logs in queue_cleanup_loop, inside its OWN try whose
    handler names the sweep (one arm's failure never skips the next, #228),
    gated on the module-level cadence state, and placed right after the Mail
    retention arm."""
    src = open(main.__file__, encoding="utf-8").read()
    loop = _named_function(ast.parse(src), "queue_cleanup_loop")
    assert loop is not None, "queue_cleanup_loop not found in main.py"
    parents = {}
    for p in ast.walk(loop):
        for ch in ast.iter_child_nodes(p):
            parents[ch] = p

    def calls(dotted):
        return [n for n in ast.walk(loop)
                if isinstance(n, ast.Call) and ast.unparse(n.func) == dotted]

    sites = calls("auto_logs.prune_auto_logs")
    assert len(sites) == 1, "expected one janitor call to the sweep, found %d" % len(sites)
    arm = _innermost_try(parents, sites[0])
    assert arm is not None, "the sweep's janitor call is not inside its own try"
    body = "\n".join(ast.unparse(s) for s in arm.body)
    assert "_AUTO_LOG_PRUNE_STATE['next']" in body and "time.monotonic() + 3600" in body, body
    assert arm.handlers and all("[AUTO-LOG] janitor sweep error" in ast.unparse(h)
                                for h in arm.handlers), "the arm's handler does not name the sweep"

    mail = _innermost_try(parents, calls("_mail_retention_sweep")[0])
    holder = parents[arm]
    assert parents[mail] is holder, "the two retention arms are not siblings in the loop"
    assert holder.body.index(arm) == holder.body.index(mail) + 1, (
        "the auto-log arm is not the one right after the Mail retention arm")
    assert isinstance(main._AUTO_LOG_PRUNE_STATE, dict) and "next" in main._AUTO_LOG_PRUNE_STATE


def test_the_janitor_self_test_sees_the_retention_sweep_sql():
    """The boot-time EXPLAIN self-test walks the janitor's call graph from its
    roots. The sweep's two statements must be in that inventory, reached from
    queue_cleanup_loop, and nothing in it may be unresolvable -- a module the
    inventory does not read is janitor SQL the self-test never plans."""
    inv = main._janitor_sql_inventory()
    assert inv["dynamic"] == [], inv["dynamic"]
    mine = [s for s in inv["statements"]
            if s["module"] == "auto_logs" and s["func"] == "prune_auto_logs"]
    sqls = sorted(" ".join(s["sql"].split()) for s in mine)
    assert len(sqls) == 2, sqls
    assert sqls[0].startswith(ROW_KEY), sqls
    assert sqls[1].startswith(CANDIDATES_KEY), sqls
    for s in mine:
        assert "queue_cleanup_loop" in s["roots"], s["roots"]


def test_the_prune_endpoint_needs_the_internal_key(logdir, monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "shh")
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.run_auto_log_prune(x_internal_key="wrong", db=Scripted()))
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.run_auto_log_prune(x_internal_key=None, db=Scripted()))
    assert e.value.status_code == 403


def test_the_prune_endpoint_runs_with_the_internal_key(logdir, monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "shh")
    db = PruneDb({})
    assert _run(auto_logs.run_auto_log_prune(x_internal_key="shh", days=30, db=db)) == {
        "rows": 0, "blobs": 0, "kept": 0}
    assert db.params_for(CANDIDATES_KEY)[0] == {"days": 30}


def test_an_empty_secret_never_authorises_the_prune(logdir, monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "")
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.run_auto_log_prune(x_internal_key="", db=Scripted()))
    assert e.value.status_code == 403


def test_the_opportunistic_prune_never_fails_an_upload(logdir, verified, monkeypatch, capsys):
    monkeypatch.setattr(auto_logs, "_LAST_PRUNE", [0.0])
    db = Scripted({COUNT_KEY: [[{"count": 0}]], PLAYER_KEY: [[{"id": PID}]],
                   INSERT_KEY: [[{"bug_number": 11}]]}, fail_on=CANDIDATES_KEY)
    out = _run(auto_logs.upload_auto_log(_request(), db))
    assert out["bug_number"] == 11
    assert db.rolled_back == 1
    assert "[AUTO-LOG] prune failed" in capsys.readouterr().out


# ── wiring ───────────────────────────────────────────────────────────────────

def test_the_routes_are_mounted_where_the_client_half_will_look_for_them():
    paths = {(r.path, tuple(sorted(r.methods))) for r in main.app.routes
             if isinstance(r, APIRoute) and "/logs" in r.path}
    assert paths == {("/api/v1/logs/auto", ("POST",)),
                     ("/api/v1/internal/logs/auto/prune", ("POST",))}


def test_the_operator_prune_sits_under_the_prefix_gated_in_middleware():
    """/api/v1/internal/* is where main's rate_limit_gate checks
    X-Internal-Key before a body is read. A prune route outside it would be
    authenticated only inside its handler."""
    assert auto_logs.internal_router.prefix.startswith("/api/v1/internal/")


def _assert_336_adds_kind(sql):
    """What this module needs from migration 336, stated over the file's
    statements rather than over one spelling of them.

    336 is the text production applied (main's file, not the lane's draft).
    It adds the column under a CATALOG GUARD -- a plain ADD COLUMN inside a
    DO block that first asks pg_attribute whether bug_reports.kind exists --
    where the draft this test was first written against said ADD COLUMN IF
    NOT EXISTS. Both are an add that a re-run survives. An unguarded ADD
    COLUMN is not, and neither is a guard that asks about another column or
    another table, or one whose END IF comes before the ADD. Comments are
    stripped first, so prose that mentions the statement cannot stand in for
    it.
    """
    code = re.sub(r"--[^\n]*", "", sql)
    adds = list(re.finditer(
        r"\bALTER\s+TABLE\s+bug_reports\s+ADD\s+COLUMN\s+(IF\s+NOT\s+EXISTS\s+)?kind\b",
        code, re.IGNORECASE))
    assert len(adds) == 1, (
        "336 must add bug_reports.kind exactly once, not %d times" % len(adds))
    add = adds[0]
    if not add.group(1):
        guard = None
        for blk in re.finditer(r"\bDO\s+(\$\w*\$)(.*?)\1", code,
                               re.DOTALL | re.IGNORECASE):
            if blk.start(2) <= add.start() < blk.end(2):
                head = code[blk.start(2):add.start()]
                found = list(re.finditer(r"\bIF\s+NOT\s+EXISTS\s*\((.*?)\)\s*THEN\b",
                                         head, re.DOTALL | re.IGNORECASE))
                if found and not re.search(r"\bEND\s+IF\b", head[found[-1].end():],
                                           re.IGNORECASE):
                    guard = found[-1]
        assert guard is not None, (
            "336 adds bug_reports.kind with neither IF NOT EXISTS nor a catalog "
            "guard around it, so a re-run of the file fails on the second ADD")
        cond = guard.group(1)
        assert re.search(r"\bpg_attribute\b", cond, re.IGNORECASE), cond
        assert re.search(r"'bug_reports'::regclass", cond, re.IGNORECASE), cond
        assert re.search(r"\battname\s*=\s*'kind'", cond, re.IGNORECASE), cond
    assert "BEGIN;" in code and "COMMIT;" in code        # #340: psql -f wraps nothing
    assert "CHECK (kind IN ('report', 'auto'))" in code  # the two kinds written here
    assert "RAISE EXCEPTION" in code                     # a post-check that can fail


def test_migration_336_is_the_one_that_adds_the_column_this_module_writes():
    sql = open(os.path.join(HERE, "..", "sql", "336_bug_reports_kind.sql"),
               encoding="utf-8").read()
    _assert_336_adds_kind(sql)


def _named_function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def test_the_event_feed_never_offers_an_automatic_row_to_the_player_dm_path():
    """Every arm of `recent_bug_report_events` must filter kind = 'report'.

    An automatic post-match upload is not a ticket the player filed. It
    creates no initial event, so it never reaches this feed by itself -- but
    an admin comment or status change on one DOES write a bug_report_events
    row, and this endpoint hands events to the bot with the linked player's
    discord_id already joined on. Unfiltered, that DMs a player that staff
    acted on "your report" for something they never filed and cannot open.

    Checked structurally rather than by substring: the handler builds `where`
    in branches, and a substring test passes as long as ONE branch carries the
    filter. This walks every assignment to `where` inside the function, so
    adding a third arm without the predicate fails too.
    """
    src = open(main.__file__, encoding="utf-8").read()
    fn = _named_function(ast.parse(src), "recent_bug_report_events")
    assert fn is not None, "recent_bug_report_events not found in main.py"

    values = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "where":
                    values.append(node.value)
    assert values, "no assignment to `where` found -- the handler was restructured"
    assert len(values) >= 2, "expected at least the unnotified and window arms, got %d" % len(values)

    for i, v in enumerate(values):
        assert isinstance(v, ast.Constant) and isinstance(v.value, str), (
            "arm %d builds `where` dynamically; this test can no longer prove the "
            "filter is present and must be replaced, not deleted" % i)
        assert "br.kind = 'report'" in v.value, (
            "arm %d of recent_bug_report_events does not filter kind: %r" % (i, v.value))
def test_an_unknown_token_is_refused_before_a_byte_of_the_body_is_read():
    """The pre-body gate is the REAL session lookup, not a presence test.

    `explode_on_stream` makes reading the body raise, so a clean 401 here can
    only happen if the route refused BEFORE streaming, joining, decoding and
    JSON-parsing up to 14 MiB for a caller it was always going to refuse. The
    old gate only asked whether the header was non-empty, so any string at all
    bought the full cost of that work.
    """
    db = Scripted({SESSION_KEY: [[]]})        # the token resolves to nothing
    with pytest.raises(HTTPException) as ei:
        _run(auto_logs.upload_auto_log(_request(explode_on_stream=True), db))
    assert ei.value.status_code == 401
    assert db.sql_for(SESSION_KEY), "the session was never looked up at all"


def test_the_body_IS_read_when_the_token_resolves(logdir, verified):
    """Control for the test above.

    If the route refused everything, or never reached the body, the test above
    would pass for the wrong reason. With a token that resolves, the same
    exploding stream must actually be reached -- so the explosion escapes
    rather than being converted into a 401.
    """
    with pytest.raises(AssertionError, match="the body was read"):
        _run(auto_logs.upload_auto_log(_request(explode_on_stream=True), _ok_db()))
def test_the_upload_route_sits_in_the_tighter_rate_limit_bucket():
    """One accepted upload can carry 14 MiB and writes a disk artifact, so the
    route belongs in the 20/10s sensitive bucket, not the 150/10s default it
    inherited by being a path nobody listed.

    Asserted through the same predicate the limiter uses (startswith over
    _RL_SENSITIVE_PREFIXES) rather than by looking for the literal in the
    tuple, so a prefix that is present but does not actually match the route
    still fails. The internal prune route must NOT be caught: its callers
    carry X-Internal-Key and bypass the limiter anyway.
    """
    def sensitive(path):
        return any(path.startswith(p) for p in main._RL_SENSITIVE_PREFIXES)

    assert sensitive("/api/v1/logs/auto"), (
        "the auto-log upload is on the loose bucket")
    assert not sensitive("/api/v1/internal/logs"), (
        "the internal prune route was swept into the sensitive bucket")
    assert main._RL_SENSITIVE == (20, 10.0) and main._RL_GLOBAL == (150, 10.0), (
        "the bucket sizes moved; this test names them so the claim above stays true")



# ── the three artifact-cleanup arms (Codex I3-MEDIUM) ───────────────────────
#
# The module's FAILURE DIRECTION paragraph makes a claim per arm. These bind
# each arm separately, because the arms disagree on purpose: two clean up, one
# deliberately does not, and a test that only checked "503 and no file" would
# pass while the indeterminate arm destroyed a committed row's log.


def _blobs(logdir):
    return sorted(p.name for p in logdir.iterdir() if p.is_file())


def test_a_failed_blob_write_leaves_no_file_behind(logdir, verified):
    """open() succeeds, write() fails: the partial file must not survive.

    Nothing can ever find it -- its id is never inserted, and prune_auto_logs
    unlinks only files named by rows it deletes -- so this is a permanent leak
    under an id nobody holds, which is precisely the orphan the docstring
    promises cannot exist.
    """
    import builtins
    real_open = builtins.open

    def exploding_open(*a, **kw):
        fh = real_open(*a, **kw)
        if len(a) > 1 and "w" in str(a[1]):
            class _Boom:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *e):
                    fh.close()
                    return False

                def write(self_inner, _data):
                    raise OSError("no space left on device")
            return _Boom()
        return fh

    builtins.open = exploding_open
    try:
        with pytest.raises(HTTPException) as ei:
            _run(auto_logs.upload_auto_log(_request(), _ok_db()))
    finally:
        builtins.open = real_open

    assert ei.value.status_code == 503, "a storage failure is retryable, not a 500"
    assert _blobs(logdir) == [], (
        "a partial blob survived a failed write: %s" % _blobs(logdir))


def test_an_indeterminate_commit_keeps_the_blob(logdir, verified, capsys):
    """The one arm that must NOT clean up.

    A commit that raises may still have committed -- the acknowledgement can be
    lost after the server durably wrote. Unlinking here destroys the only copy
    of the log a live row promises, which reads as corruption. Keeping it costs
    disk. The cheap reversible error is the right one (#276).

    This is the exact inverse of the two tests above, and it is why the cleanup
    cannot simply be hoisted into one `finally`.
    """
    db = _ok_db()
    db.fail_commit = True

    with pytest.raises(HTTPException) as ei:
        _run(auto_logs.upload_auto_log(_request(), db))

    assert ei.value.status_code == 503
    kept = _blobs(logdir)
    assert len(kept) == 1, (
        "the blob was discarded on an INDETERMINATE commit -- if the row did "
        "commit, that row now points at a log that no longer exists")
    out = capsys.readouterr().out
    assert "INDETERMINATE" in out and kept[0] in out, (
        "nothing collects this blob, so the id must be printed or it is "
        "unrecoverable by construction; got: %r" % out)



def test_the_prune_route_is_callable_in_process_without_a_days_argument(monkeypatch):
    """The in-process caller the `days` clamp was written for.

    Every other test of this route passes days= explicitly, which is exactly
    why a `Query(...)` default survived here: outside FastAPI nothing resolves
    it, so the parameter arrives as the descriptor object and `int()` on it
    raises TypeError. A janitor hook calling this the obvious way would have
    failed on its first run.
    """
    monkeypatch.setenv("API_SECRET_KEY", "shh")
    db = PruneDb({})
    out = _run(auto_logs.run_auto_log_prune(x_internal_key="shh", db=db))
    assert out == {"rows": 0, "blobs": 0, "kept": 0}
    assert db.params_for(CANDIDATES_KEY)[0] == {
        "days": auto_logs.AUTO_LOG_RETENTION_DAYS}, (
        "an omitted days must resolve to the retention default, not to a "
        "Query descriptor")


def test_the_kind_column_makes_migration_336_a_hard_precondition():
    """Deploy order for `kind` is decided by RAW SQL, not by the ORM mapping.

    `bug_reports.kind` is deliberately absent from the ORM model, and it is
    tempting to conclude from that that code may safely precede migration 336.
    It may not: submit_bug_report's own rate-limit COUNT reads the column, so
    on a box without 336 that SELECT raises UndefinedColumn and bug reporting
    stops entirely for every player.

    This test exists so that conclusion cannot be quietly re-adopted. If the
    raw reads genuinely go away, it fails and whoever removed them can relax
    the ordering deliberately -- rather than someone inferring it from the
    model file, which is what happened once already.
    """
    src = open(main.__file__, encoding="utf-8").read()
    reads = [ln.strip() for ln in src.splitlines()
             if "kind = 'report'" in ln and not ln.strip().startswith("#")]
    assert reads, (
        "no raw SQL reads bug_reports.kind any more -- if that is real, the "
        "migration-before-code requirement in models.py can be relaxed, but "
        "do it on purpose")

    model_src = open(os.path.join(os.path.dirname(main.__file__), "models.py"),
                     encoding="utf-8").read()
    assert "MIGRATION 336 MUST BE APPLIED BEFORE" in model_src, (
        "models.py no longer states the ordering requirement; an unmapped "
        "column reads as 'safe either way' and it is not")



LOCK_KEY = "pg_advisory_xact_lock"


def test_one_accounts_uploads_are_serialised_before_the_cap_is_counted(logdir, verified):
    """The 12/24h cap is count-then-insert, so it needs the count serialised.

    Without a lock, two uploads from one account that both see 11 rows both
    commit and the account ends the day on 13. There is no row to take FOR
    UPDATE -- the row being counted is the one about to be written -- so the
    lock is keyed on the steam_id VALUE (#202/#203/#207).

    Asserted by ORDER, not presence: a lock taken after the COUNT protects
    nothing, because the second caller has already read the stale number. A
    test that only checked the statement appeared would pass for that.
    """
    db = _ok_db()
    _run(auto_logs.upload_auto_log(_request(), db))

    order = [sql for sql, _ in db.log]
    lock_at = next((i for i, s in enumerate(order) if LOCK_KEY in s), None)
    count_at = next((i for i, s in enumerate(order) if COUNT_KEY in s), None)
    assert lock_at is not None, (
        "no advisory lock on the upload path; the cap is a bare "
        "count-then-insert and two concurrent uploads can exceed it")
    assert count_at is not None, "the cap is no longer counted at all"
    assert lock_at < count_at, (
        "the lock is taken AFTER the count (%d vs %d), which serialises "
        "nothing -- the racing caller has already read its number"
        % (lock_at, count_at))

    params = [p for sql, p in db.log if LOCK_KEY in sql][0]
    assert params == {"sid": STEAM}, (
        "the lock must be keyed on the account it is protecting, got %r" % (params,))


def test_a_log_that_compresses_past_the_readers_ceiling_is_refused(logdir, verified,
                                                                   monkeypatch):
    """Accepting a blob the reader will not serve is not an acceptance.

    The request cap and the stored-blob cap are different numbers against
    different things, and a high-entropy log can sit under the first and over
    the second. Stored, it yields a row whose detail view errors and whose
    download is a 413 -- so the upload has to refuse instead.

    The ceiling is moved rather than a real 8 MiB of incompressible text being
    generated: the property is "this path honours the reader's limit", and
    binding it to the reader's own constant is what the test is for.
    """
    monkeypatch.setattr(main, "_BUG_LOG_MAX_GZ", 8, raising=True)

    with pytest.raises(HTTPException) as ei:
        _run(auto_logs.upload_auto_log(_request(), _ok_db()))

    assert ei.value.status_code == 413, (
        "expected a refusal at the door, got %s" % ei.value.status_code)
    assert list(logdir.iterdir()) == [], "a blob it refused to accept was written anyway"


def test_the_upload_ceiling_is_the_readers_constant_and_not_a_copy(logdir, verified,
                                                                   monkeypatch):
    """Moving the reader's ceiling must move this route's behaviour.

    A hand-copied 8 MiB literal here would satisfy the test above on the day it
    was written and then silently disagree the first time the reader's limit
    changed -- the exact drift the module avoids for the scrub by importing it.
    So: raise the ceiling and the same upload must now succeed.
    """
    monkeypatch.setattr(main, "_BUG_LOG_MAX_GZ", 8, raising=True)
    with pytest.raises(HTTPException):
        _run(auto_logs.upload_auto_log(_request(), _ok_db()))

    monkeypatch.setattr(main, "_BUG_LOG_MAX_GZ", 8 * 1024 * 1024, raising=True)
    out = _run(auto_logs.upload_auto_log(_request(), _ok_db()))
    assert out["status"] == "received", (
        "the route did not follow the reader's constant back up, so it is "
        "reading a copy of the limit rather than the limit")
