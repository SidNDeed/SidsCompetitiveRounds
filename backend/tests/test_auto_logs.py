"""Opt-in automatic post-match log upload — the server half (v1.41.0 Item 3).

The route is LIVE: the client half is in the v1.41.0 client lane build
46f54d4, installed on Sid's desktop, and the opt-in setting has been switched
on there — so POST /api/v1/logs/auto takes real traffic. (An earlier version
of this docstring named 323cd9c for that build, which is an unrelated vanilla
fix; an earlier one still said the opposite outright, and so did several
assertions below — "a route with no caller yet" was written into the reasoning
for what a refusal has to say.) Every bound this file checks is therefore
load-bearing from the first boot rather than a limit waiting for a client.

This file drives the handler directly against a scripted session and asserts
the POSITIVE things a real call produces — a kind='auto' row, a blob on disk
with the OS username gone, and the [AUTO-LOG] line — rather than the absence
of errors (#438/#443).

Mutation controls are explicit where the assertion would otherwise pass for
the wrong reason: the scrub test re-runs with the scrub neutered and requires
the check to FAIL, and the clamp test requires the 64-character ceiling (the
one the plan cited by mistake) to be the wrong answer.

PUBLISHED LIMITS ARE ASSERTED AS LITERALS, not read out of the constants they
are meant to pin. A test that says `== auto_logs.AUTO_LOG_PER_STEAM_PER_DAY`
agrees with any number that constant ever holds, which is the shape of a check
that cannot fail (#342). Tests that exercise BEHAVIOUR at a boundary still
read the constant -- they are about the boundary, not about which number it
is -- and `test_the_published_limits_are_what_this_release_promises` is the
one place the numbers themselves are written down.
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
import time
import unittest.mock as mock
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

# The retention sweep's read of the due rows. Distinct from COUNT_KEY, which
# is the upload path's own per-steam bucket over the same table.
DUE_KEY = "SELECT id::text AS id, log_filename"
R1 = UUID("11111111-1111-4111-8111-111111111111")
R2 = UUID("22222222-2222-4222-8222-222222222222")
COUNT_KEY = "SELECT COUNT(*) AS n, MIN(created_at) AS oldest FROM bug_reports"
PLAYER_KEY = "SELECT id FROM players WHERE steam_id = :sid"
INSERT_KEY = "INSERT INTO bug_reports"
SESSION_KEY = "FROM steam_sessions"
LOCK_KEY = "pg_advisory_xact_lock"

PID = UUID("0b7d2f8e-3c4a-4c2a-9b1e-2f3a4b5c6d7e")

# How old the oldest upload in a full bucket is, in the tests that care. Three
# hours in means the rolling window reopens in twenty-one, which is the figure
# the Retry-After assertions expect to see.
BUCKET_AGE_H = 3


def _bucket(n, oldest=None):
    """One row from `_auto_bucket`'s read: the count and the oldest timestamp.

    The upload path reads both in one statement, so a scripted bucket has to
    answer both. `oldest` defaults to something inside the window whenever the
    bucket is non-empty, because a full bucket with no oldest row is a state
    the database cannot produce and scripting one would let a Retry-After bug
    pass by taking the no-oldest fallback.
    """
    if oldest is None and n:
        oldest = datetime.now(timezone.utc) - timedelta(hours=BUCKET_AGE_H)
    return {"n": n, "oldest": oldest}


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
            if row is None:
                return None
            return next(iter(row.values())) if isinstance(row, dict) else row
        return self.value

    def scalar_one_or_none(self):
        """`select(Model).where(...)` reads land here. A scripted row that is
        NOT a mapping is handed back whole, which is how an ORM-shaped result
        (a BugReport, a Player) is modelled without a session."""
        return self.scalar()

    @property
    def rowcount(self):
        """The retention sweep reads this off its DELETE. Modelled as the
        length of whatever the script handed back, so a scripted DELETE that
        returns nothing reports zero rows removed rather than a made-up
        number."""
        return len(self._rows())


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
        self.added = []
        self.committed = 0
        self.rolled_back = 0

    def add(self, obj):
        """`_record_bug_event` writes through the session, not through SQL, so
        a refusal that reaches it is invisible in `log`. Collected here so a
        test can assert that NOTHING was written."""
        self.added.append(obj)

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


@pytest.fixture(autouse=True)
def no_rows_held_over(monkeypatch):
    """`_PRUNE_HELD` is process state that outlives one call, so without this
    a test whose unlink fails decides what the NEXT test's sweep is allowed to
    select, and the pair passes or fails on collection order."""
    monkeypatch.setattr(auto_logs, "_PRUNE_HELD", {})


def _ok_db(auto_count=0, player=True):
    return Scripted({
        COUNT_KEY: [[_bucket(auto_count)]],
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
        COUNT_KEY: [[_bucket(0)]],
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
        COUNT_KEY: [[_bucket(0)]],
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
        COUNT_KEY: [[_bucket(0)]],
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
    decoder reject the whole request. The refusal must be greppable: the
    shipped client retries in the background, so this is the refusal a real
    deployment sits on silently, and the log line is the only place it shows."""
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
    db = Scripted({COUNT_KEY: [[_bucket(0)]], PLAYER_KEY: [[{"id": PID}]]},
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

def test_the_prune_unlinks_only_auto_blobs_and_then_deletes_their_rows(logdir):
    keep = logdir / "keep.log.gz"
    drop = logdir / "drop.log.gz"
    keep.write_bytes(b"x")
    drop.write_bytes(b"x")
    db = Scripted({DUE_KEY: [[{"id": str(R1), "log_filename": "drop.log.gz"}]],
                   "DELETE FROM bug_reports": [[{"id": str(R1)}]]})

    out = _run(auto_logs.prune_auto_logs(db))

    due_sql = db.sql_for(DUE_KEY)[0]
    del_sql = db.sql_for("DELETE FROM bug_reports")[0]
    assert "kind = 'auto'" in due_sql, due_sql
    assert "kind = 'auto'" in del_sql, del_sql
    # New interval arithmetic uses make_interval from a typed CAST: #448's
    # ruling, over the parameter-typing trap #275 documents. On BOTH
    # statements: the DELETE re-checks the age predicate the SELECT chose on
    # (#208), so the typing question is asked twice and has to be answered
    # twice.
    for sql in (due_sql, del_sql):
        assert "make_interval(days => CAST(:days AS integer))" in sql, sql
    # The id list is typed too, and carries real UUIDs rather than strings:
    # `= ANY(CAST(:ids AS uuid[]))` with a list of str is the #275 shape.
    assert "ANY(CAST(:ids AS uuid[]))" in del_sql, del_sql
    ids = db.params_for("DELETE FROM bug_reports")[0]["ids"]
    assert ids == [R1] and all(isinstance(i, UUID) for i in ids), ids
    assert db.params_for(DUE_KEY)[0]["days"] == 14
    assert out == {"rows": 1, "blobs": 1, "retained": 0, "due": 1, "held": 0}
    assert keep.exists() and not drop.exists()


def test_the_prune_reads_the_due_rows_before_it_deletes_anything(logdir):
    """ORDER OF OPERATIONS, asserted directly.

    The row is the only thing that names its blob. Deleting the row first and
    unlinking afterwards -- which is what this used to do -- turns any
    filesystem error into an orphan file nothing can ever find again, because
    the retry reference went with the row.
    """
    (logdir / "a.log.gz").write_bytes(b"x")
    db = Scripted({DUE_KEY: [[{"id": str(R1), "log_filename": "a.log.gz"}]],
                   "DELETE FROM bug_reports": [[{"id": str(R1)}]]})
    _run(auto_logs.prune_auto_logs(db))

    order = [sql for sql, _p in db.log
             if DUE_KEY in sql or sql.startswith("DELETE FROM bug_reports")]
    assert len(order) == 2 and DUE_KEY in order[0], (
        "the sweep's first statement is not the read of the due rows: %r" % order)
    assert order[1].startswith("DELETE FROM bug_reports"), order


def test_a_row_whose_blob_cannot_be_removed_is_kept_as_its_own_retry(logdir, capsys):
    """The failure this order exists to make recoverable.

    An unlink that raises something other than "already gone" leaves the file
    on disk. The row must survive so the next pass finds it again; collecting
    it would strand the blob for good.
    """
    stuck = logdir / "stuck.log.gz"
    stuck.write_bytes(b"x")
    fine = logdir / "fine.log.gz"
    fine.write_bytes(b"x")
    db = Scripted({DUE_KEY: [[{"id": str(R1), "log_filename": "stuck.log.gz"},
                              {"id": str(R2), "log_filename": "fine.log.gz"}]],
                   "DELETE FROM bug_reports": [[{"id": str(R2)}]]})

    real_unlink = pathlib.Path.unlink

    def _explode(self, *a, **kw):
        if self.name == "stuck.log.gz":
            raise PermissionError("held open")
        return real_unlink(self, *a, **kw)

    with mock.patch.object(pathlib.Path, "unlink", _explode):
        out = _run(auto_logs.prune_auto_logs(db))

    assert out == {"rows": 1, "blobs": 1, "retained": 1, "due": 2, "held": 1}
    ids = db.params_for("DELETE FROM bug_reports")[0]["ids"]
    assert ids == [R2], (
        "the row whose blob could not be removed was deleted anyway -- its "
        "blob is now unnameable: %r" % (ids,))
    assert stuck.exists() and not fine.exists()
    assert "keeping row" in capsys.readouterr().out


R3 = UUID("44444444-4444-4444-8444-444444444444")


def _explode_on(*names):
    """Patch Path.unlink so the named blobs raise the error a read-only mount
    or a lost permission produces, and everything else unlinks for real."""
    real_unlink = pathlib.Path.unlink

    def _boom(self, *a, **kw):
        if self.name in names:
            raise PermissionError("read-only file system")
        return real_unlink(self, *a, **kw)
    return mock.patch.object(pathlib.Path, "unlink", _boom)


def test_a_head_of_unremovable_blobs_does_not_block_newer_rows(logdir):
    """THE STUCK HEAD. The sweep reads the OLDEST rows first and keeps the
    ones whose blob it could not remove, so without a hold those same rows are
    the whole of every future selection: the pass deletes nothing, never
    reaches a younger row, and the fourteen-day rule quietly stops being
    enforced for the entire corpus while each pass still prints a line that
    reads like a working sweep.

    Two passes. The first meets a cohort it cannot unlink; the second must
    look PAST it and collect the row behind it.
    """
    for name in ("old-a.log.gz", "old-b.log.gz", "newer.log.gz"):
        (logdir / name).write_bytes(b"x")
    db = Scripted({DUE_KEY: [
        [{"id": str(R1), "log_filename": "old-a.log.gz"},
         {"id": str(R2), "log_filename": "old-b.log.gz"}],
        [{"id": str(R3), "log_filename": "newer.log.gz"}],
    ], "DELETE FROM bug_reports": [[{"id": str(R3)}]]})

    with _explode_on("old-a.log.gz", "old-b.log.gz"):
        first = _run(auto_logs.prune_auto_logs(db))
        second = _run(auto_logs.prune_auto_logs(db))

    assert first == {"rows": 0, "blobs": 0, "retained": 2, "due": 2, "held": 2}
    due_sql = db.sql_for(DUE_KEY)[1]
    assert "NOT (id = ANY(CAST(:held AS uuid[])))" in due_sql, (
        "the second pass re-reads the rows it just failed on: %s" % due_sql)
    assert sorted(db.params_for(DUE_KEY)[1]["held"]) == sorted([R1, R2]), (
        "the stuck cohort was not held out of the second selection: %r"
        % (db.params_for(DUE_KEY)[1]["held"],))
    assert second["rows"] == 1, (
        "the second pass collected nothing -- the unremovable head is still "
        "standing in front of every younger row: %r" % (second,))
    assert db.params_for("DELETE FROM bug_reports")[0]["ids"] == [R3]
    assert not (logdir / "newer.log.gz").exists()
    assert (logdir / "old-a.log.gz").exists(), (
        "a blob that could not be unlinked was reported as collected")


def test_a_held_row_is_retried_once_its_hold_expires(logdir):
    """The hold is a COOLDOWN, not a verdict. A fault that is repaired -- the
    volume remounted read-write, the permission restored -- has to be tried
    again, or this mechanism has merely moved "never collected" from the rows
    behind the head onto the head itself."""
    (logdir / "a.log.gz").write_bytes(b"x")
    db = Scripted({DUE_KEY: [
        [{"id": str(R1), "log_filename": "a.log.gz"}],
        [{"id": str(R1), "log_filename": "a.log.gz"}],
    ], "DELETE FROM bug_reports": [[{"id": str(R1)}]]})

    with _explode_on("a.log.gz"):
        _run(auto_logs.prune_auto_logs(db))
    assert list(auto_logs._PRUNE_HELD) == [str(R1)]

    # The fault is gone and so is the cooldown: the deadline is in the past.
    auto_logs._PRUNE_HELD[str(R1)] = time.monotonic() - 1.0
    out = _run(auto_logs.prune_auto_logs(db))

    assert db.params_for(DUE_KEY)[1]["held"] == [], (
        "an expired hold was still applied to the selection")
    assert out["rows"] == 1 and out["held"] == 0, out
    assert str(R1) not in auto_logs._PRUNE_HELD, (
        "a row that was successfully collected is still on the hold list")


def test_the_hold_list_cannot_grow_without_bound(logdir, monkeypatch):
    """It is handed to the database as an array on every pass, so it is a
    query parameter and not just a dict. At the ceiling the entry nearest to
    expiring is evicted -- the one whose fault is oldest, and therefore the
    one most worth attempting again."""
    monkeypatch.setattr(auto_logs, "_PRUNE_HELD_MAX", 2)
    clock = time.monotonic()
    auto_logs._hold("oldest", clock - 100)
    auto_logs._hold("middle", clock)
    auto_logs._hold("newest", clock + 100)

    assert len(auto_logs._PRUNE_HELD) == 2
    assert "oldest" not in auto_logs._PRUNE_HELD, (
        "the ceiling dropped the NEW failure instead of the stalest hold, so "
        "the row that just failed goes straight back to the head of the next "
        "selection: %r" % (sorted(auto_logs._PRUNE_HELD),))
    assert "newest" in auto_logs._PRUNE_HELD


def test_the_ordering_docstring_names_the_hold_that_defers_the_retry(logdir):
    """The module docstring is the account an editor reads before changing
    this file, and it used to say a kept row is simply found again by the next
    pass. That is the mechanism `_PRUNE_HELD` exists to REPLACE: the next pass
    deliberately looks past it. A comment naming a mechanism the code no
    longer has is how the hold gets removed again as redundant (#432/#459).

    Asserted on the paragraph that makes the claim rather than on the file, so
    what it reads is the prose that would be wrong.
    """
    doc = auto_logs.__doc__ or ""
    start = doc.find("ORDER WITHIN A SWEEP")
    assert start >= 0, "the ordering paragraph is gone; this test reads it"
    end = doc.find("NOT A REPLICA-ROUTABLE PATH", start)
    assert end > start, "the ordering section no longer ends where this reads"
    section = doc[start:end]
    assert "_PRUNE_HELD" in section, (
        "the docstring explains what happens to a row whose unlink failed "
        "without naming the hold that defers its retry, so it describes the "
        "pre-hold behaviour -- the one that let an unremovable cohort stand "
        "in front of the whole corpus:\n%s" % section)
    assert "the next pass finds it again" not in section, (
        "the docstring still promises the unconditional retry the hold "
        "replaced:\n%s" % section)


def test_a_pass_that_writes_nothing_does_not_hold_its_transaction_open(logdir):
    """Two paths return without a commit: nothing was due, and everything due
    was retained. Both have already run the SELECT, so both are inside a
    transaction when they return.

    On the sweep's own session that would be ended by the context manager. The
    opportunistic call inside `upload_auto_log` hands over the REQUEST's
    session instead, and that one stays checked out until the request ends --
    so an uncommitted read snapshot outlives the pass that opened it and holds
    the primary's vacuum horizon back for the rest of the request. The second
    path is the one a stuck blob volume produces, i.e. the one that repeats
    every hour for as long as the fault lasts.
    """
    empty = Scripted({DUE_KEY: [[]]})
    _run(auto_logs.prune_auto_logs(empty))
    assert empty.committed == 0
    assert empty.rolled_back == 1, (
        "a pass with nothing due returned with its SELECT's transaction still "
        "open")

    (logdir / "stuck.log.gz").write_bytes(b"x")
    stuck = Scripted({DUE_KEY: [[{"id": str(R1), "log_filename": "stuck.log.gz"}]]})
    with _explode_on("stuck.log.gz"):
        out = _run(auto_logs.prune_auto_logs(stuck))
    assert out["retained"] == 1 and out["rows"] == 0, out
    assert stuck.committed == 0
    assert stuck.rolled_back == 1, (
        "a pass whose every due row was retained returned with its SELECT's "
        "transaction still open")


def test_a_prune_over_nothing_writes_nothing(logdir):
    db = Scripted({DUE_KEY: [[]]})
    assert _run(auto_logs.prune_auto_logs(db)) == {
        "rows": 0, "blobs": 0, "retained": 0, "due": 0, "held": 0}
    assert db.sql_for("DELETE FROM bug_reports") == [], (
        "a sweep with nothing due still issued a DELETE")


def test_an_already_absent_blob_is_collected_rather_than_retried_forever(logdir):
    """The state a previous half-finished pass leaves: the file is gone and
    the row is still there. "Already absent" has to count as success or that
    row is pinned for ever."""
    db = Scripted({DUE_KEY: [[
        {"id": str(R1), "log_filename": "gone.log.gz"},
        {"id": str(R2), "log_filename": None},
    ]], "DELETE FROM bug_reports": [[{"id": str(R1)}, {"id": str(R2)}]]})
    out = _run(auto_logs.prune_auto_logs(db))
    assert out == {"rows": 2, "blobs": 0, "retained": 0, "due": 2, "held": 0}
    assert sorted(db.params_for("DELETE FROM bug_reports")[0]["ids"]) == sorted([R1, R2])


def test_a_sweep_is_bounded_so_a_backlog_drains_over_ticks(logdir):
    """One pass holds a transaction open across its unlink loop, so the loop
    is bounded. Without the LIMIT a first sweep after a long outage walks the
    whole backlog in one transaction."""
    db = Scripted({DUE_KEY: [[]]})
    _run(auto_logs.prune_auto_logs(db))
    sql = db.sql_for(DUE_KEY)[0]
    assert "LIMIT :lim" in sql, sql
    assert db.params_for(DUE_KEY)[0]["lim"] == auto_logs._PRUNE_BATCH
    assert isinstance(auto_logs._PRUNE_BATCH, int) and auto_logs._PRUNE_BATCH > 0


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
    db = Scripted({DUE_KEY: [[]]})
    assert _run(auto_logs.run_auto_log_prune(x_internal_key="shh", days=30, db=db)) == {
        "rows": 0, "blobs": 0, "retained": 0, "due": 0, "held": 0}
    assert db.params_for(DUE_KEY)[0]["days"] == 30


def test_an_empty_secret_never_authorises_the_prune(logdir, monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "")
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.run_auto_log_prune(x_internal_key="", db=Scripted()))
    assert e.value.status_code == 403


def test_the_opportunistic_prune_never_fails_an_upload(logdir, verified, monkeypatch, capsys):
    monkeypatch.setattr(auto_logs, "_LAST_PRUNE", [0.0])
    db = Scripted({COUNT_KEY: [[_bucket(0)]], PLAYER_KEY: [[{"id": PID}]],
                   INSERT_KEY: [[{"bug_number": 11}]]}, fail_on=DUE_KEY)
    out = _run(auto_logs.upload_auto_log(_request(), db))
    assert out["bug_number"] == 11
    assert db.rolled_back == 1
    assert "[AUTO-LOG] prune failed" in capsys.readouterr().out


# ── the published numbers ────────────────────────────────────────────────────

def test_the_published_limits_are_what_this_release_promises():
    """LITERALS. Every other test here reads these off the constants, which
    means every other test agrees with whatever the constants say -- widen one
    and nothing goes red.

    These are the numbers the feature was specified with, and changing any of
    them is a decision about what the server promises a shipped client, not a
    refactor. Changing one here in the same commit is the point: it forces the
    change to be stated rather than absorbed.
    """
    assert auto_logs.AUTO_LOG_PER_STEAM_PER_DAY == 12, (
        "the per-account bucket is no longer 12 uploads per rolling 24 hours")
    assert auto_logs.AUTO_LOG_RETENTION_DAYS == 14, (
        "retention is no longer 14 days -- Sid's answer (a) in the plan")
    assert auto_logs.AUTO_LOG_MAX_BODY_BYTES == 14 * 1024 * 1024, (
        "the request-body ceiling is no longer 14 MiB")
    assert schemas.BUG_REPORT_LOG_MAX_CHARS == 12_000_000, (
        "the log text clamp is no longer 12,000,000 characters")
    assert main._BUG_LOG_MAX_GZ == 8 * 1024 * 1024, (
        "the stored-blob ceiling the READER enforces is no longer 8 MiB; an "
        "upload accepted above it lands as an artifact the download endpoint "
        "refuses")


# ── wiring ───────────────────────────────────────────────────────────────────

def test_the_routes_are_mounted_where_the_client_half_looks_for_them():
    paths = {(r.path, tuple(sorted(r.methods))) for r in main.app.routes
             if isinstance(r, APIRoute) and "/logs" in r.path}
    assert paths == {("/api/v1/logs/auto", ("POST",)),
                     ("/api/v1/internal/logs/auto/prune", ("POST",))}


def test_retention_is_enforced_by_a_scheduled_sweep_on_the_primary():
    """THE THING THAT MAKES FOURTEEN DAYS A RULE RATHER THAN A HOPE.

    Every other retention test in this file INVOKES `prune_auto_logs`
    directly, so all of them pass against a sweep that nothing ever calls --
    which is what this module shipped as: pruning was reachable only
    opportunistically after an accepted upload, and from the internal route.
    A corpus collected only while it is growing is not collected at all, and
    the case that matters is exactly the one where uploads have stopped.

    Read out of `lifespan`'s AST, on the branch that runs on the primary. The
    replica must NOT start it: every pass DELETEs and a delete raises in
    recovery.
    """
    tree = ast.parse(inspect.getsource(main))
    lifespan = next(n for n in ast.walk(tree)
                    if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
                    and n.name == "lifespan")

    # The IS_REPLICA branch, split into its two arms.
    branch = next((n for n in ast.walk(lifespan)
                   if isinstance(n, ast.If) and isinstance(n.test, ast.Name)
                   and n.test.id == "IS_REPLICA"), None)
    assert branch is not None, "lifespan no longer branches on IS_REPLICA"

    def _supervised_tasks(nodes):
        """{supervised name: the expression it was handed to run}.

        The NAME is a label an editor picks; the second argument is what
        actually runs. Reading only the first of the two is a check bound to
        something correlated with the property instead of to the property
        (#732): `_supervised("auto_log_retention", _pc_steam_sweep_loop)`
        satisfies a name test perfectly while nothing enforces the rule.
        """
        out = {}
        for node in nodes:
            for call in ast.walk(node):
                if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                        and call.func.id == "_supervised" and call.args
                        and isinstance(call.args[0], ast.Constant)):
                    started = call.args[1] if len(call.args) > 1 else None
                    out[call.args[0].value] = (
                        None if started is None else ast.unparse(started))
        return out

    def _resolve(expression):
        """The live object `main` would hand `_supervised`, from its source
        expression -- so the assertion is about the callable and not about a
        spelling. Only attribute chains off a module-level name are resolved;
        anything else returns None and fails loudly below rather than being
        quietly accepted."""
        parts = expression.split(".") if expression else []
        if not parts:
            return None
        obtained = getattr(main, parts[0], None)
        for part in parts[1:]:
            obtained = getattr(obtained, part, None)
        return obtained

    primary = _supervised_tasks(branch.orelse)
    replica = _supervised_tasks(branch.body)
    assert "auto_log_retention" in primary, (
        "the primary does not start the auto-log retention sweep, so nothing "
        "enforces the %d-day rule once uploads stop. Supervised tasks on the "
        "primary branch: %r" % (auto_logs.AUTO_LOG_RETENTION_DAYS, sorted(primary)))
    assert "auto_log_retention" not in replica, (
        "the replica starts the retention sweep; every pass DELETEs and a "
        "delete raises in recovery")

    started = primary["auto_log_retention"]
    assert _resolve(started) is auto_logs.auto_log_retention_loop, (
        "the task named 'auto_log_retention' on the primary is started with "
        "%r, which is not auto_logs.auto_log_retention_loop. The name is a "
        "label; what enforces the %d-day rule is the coroutine, and this "
        "assertion is the one that reads it"
        % (started, auto_logs.AUTO_LOG_RETENTION_DAYS))


def test_the_sweep_announces_itself_at_boot_and_on_every_pass(monkeypatch, capsys):
    """The positive signal (#438/#443).

    The absence of errors cannot distinguish "nothing was old enough" from
    "the sweep is not running". One armed line at boot and one line per pass
    can, so both are asserted -- including the pass that collects nothing,
    which is the one a quiet loop would otherwise be indistinguishable from.
    """
    calls = []

    class _Session:
        async def __aenter__(self):
            return Scripted({DUE_KEY: [[]]})

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(auto_logs, "AUTO_LOG_SWEEP_BOOT_DELAY_S", 0)
    monkeypatch.setattr(auto_logs, "AUTO_LOG_SWEEP_EVERY_S", 0)

    import database
    monkeypatch.setattr(database, "async_session", lambda: _Session())

    async def _sleep(seconds):
        calls.append(seconds)
        if len(calls) >= 2:            # boot delay, then one pass
            raise asyncio.CancelledError
    monkeypatch.setattr(asyncio, "sleep", _sleep)

    with pytest.raises(asyncio.CancelledError):
        _run(auto_logs.auto_log_retention_loop())

    out = capsys.readouterr().out
    assert "[AUTO-LOG] retention sweep armed" in out, (
        "no boot line, so a primary that is not sweeping looks exactly like "
        "one that has nothing to sweep: %r" % out)
    assert "retention sweep: 0 row(s)" in out, (
        "a pass that collected nothing printed nothing: %r" % out)


def test_a_failing_sweep_says_so_and_keeps_the_loop_alive(monkeypatch, capsys):
    """A sweep that dies silently leaves retention unenforced with a clean
    log, which is the exact failure the loop was added to remove."""
    class _Session:
        async def __aenter__(self):
            raise RuntimeError("no connection")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(auto_logs, "AUTO_LOG_SWEEP_BOOT_DELAY_S", 0)
    monkeypatch.setattr(auto_logs, "AUTO_LOG_SWEEP_EVERY_S", 0)
    import database
    monkeypatch.setattr(database, "async_session", lambda: _Session())

    ticks = []

    async def _sleep(seconds):
        ticks.append(seconds)
        if len(ticks) >= 3:
            raise asyncio.CancelledError
    monkeypatch.setattr(asyncio, "sleep", _sleep)

    with pytest.raises(asyncio.CancelledError):
        _run(auto_logs.auto_log_retention_loop())

    out = capsys.readouterr().out
    assert out.count("retention sweep FAILED") >= 2, (
        "a failing pass did not report, or killed the loop: %r" % out)
    assert "(1 consecutive)" in out and "(2 consecutive)" in out, (
        "the failures are not counted, so one line an hour reads the same "
        "whether this is the first failure or a week of them: %r" % out)


def _documented_signals(text):
    """Every `[TAG] ...` log line a piece of prose points an operator at.

    Backticks are the marker, and they are the marker for nothing else in
    these two texts: a signal is quoted, everything else is not (#306).
    """
    return re.findall(r"`(\[[A-Z-]+\][^`]*)`", " ".join(text.split()))


def test_every_signal_the_sweep_documents_is_one_it_actually_prints(monkeypatch, capsys):
    """A COMMENT THAT NAMES THE WRONG LINE IS WORSE THAN NO COMMENT, because
    it is the line the operator will grep for and not find.

    The loop catches its own per-pass errors, so `_supervised`'s restart line
    cannot appear for this task however badly a pass goes; prose claiming it
    restarts loudly sends the one person who is checking to look for a string
    that is never printed, and the absence reads as health.

    So both texts -- the loop's docstring and the comment in `lifespan` that
    registers it -- are read for the signals they name, and every one of them
    has to turn up in the output of a loop that is run for real: one failing
    pass, one quiet pass that recovers.
    """
    passes = []

    class _Session:
        async def __aenter__(self):
            passes.append(1)
            if len(passes) == 1:
                raise RuntimeError("no connection")
            return Scripted({DUE_KEY: [[]]})

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(auto_logs, "AUTO_LOG_SWEEP_BOOT_DELAY_S", 0)
    monkeypatch.setattr(auto_logs, "AUTO_LOG_SWEEP_EVERY_S", 0)
    import database
    monkeypatch.setattr(database, "async_session", lambda: _Session())

    ticks = []

    async def _sleep(seconds):
        ticks.append(seconds)
        if len(ticks) >= 3:                    # boot delay, then two passes
            raise asyncio.CancelledError
    monkeypatch.setattr(asyncio, "sleep", _sleep)

    with pytest.raises(asyncio.CancelledError):
        _run(auto_logs.auto_log_retention_loop())
    out = capsys.readouterr().out

    registration = _lifespan_retention_comment()
    documented = (_documented_signals(auto_logs.auto_log_retention_loop.__doc__)
                  + _documented_signals(registration))
    assert documented, (
        "neither the loop's docstring nor the lifespan comment names a single "
        "log line, so nobody reading either one knows what to grep for")
    assert _documented_signals(registration), (
        "the comment that registers this task names no signal at all")
    for signal in documented:
        assert signal in out, (
            "the sweep is documented as printing %r and a run of the loop -- "
            "one failing pass, one quiet one -- never printed it. The lines it "
            "did print were:\n%s" % (signal, out))


def _lifespan_retention_comment():
    """The contiguous comment block directly above the retention task's
    registration in `lifespan`, read out of main.py's source."""
    lines = inspect.getsource(main).splitlines()
    anchor = next(i for i, ln in enumerate(lines)
                  if '_supervised("auto_log_retention"' in ln)
    block = []
    i = anchor
    while i > 0:
        i -= 1
        stripped = lines[i].strip()
        if stripped.startswith("#"):
            block.append(stripped)
        elif stripped.startswith("tasks.append") or stripped.startswith("_supervised"):
            continue
        else:
            break
    return "\n".join(reversed(block))


def test_the_operator_prune_sits_under_the_prefix_gated_in_middleware():
    """/api/v1/internal/* is where main's rate_limit_gate checks
    X-Internal-Key before a body is read. A prune route outside it would be
    authenticated only inside its handler."""
    assert auto_logs.internal_router.prefix.startswith("/api/v1/internal/")


def test_migration_336_is_the_one_that_adds_the_column_this_module_writes():
    sql = open(os.path.join(HERE, "..", "sql", "336_bug_reports_kind.sql"),
               encoding="utf-8").read()
    assert "ADD COLUMN kind VARCHAR(16) NOT NULL DEFAULT 'report'" in sql
    assert "ADD COLUMN IF NOT EXISTS kind" not in sql, (
        "336 is back to the IF NOT EXISTS spelling, which takes ACCESS "
        "EXCLUSIVE on bug_reports before it evaluates the existence test -- "
        "see test_a_second_run_takes_no_blocking_lock")
    assert "BEGIN;" in sql and "COMMIT;" in sql          # #340: psql -f wraps nothing
    assert "CHECK (kind IN ('report', 'auto'))" in sql
    assert "RAISE EXCEPTION" in sql                       # a post-check that can fail
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
    db = Scripted({DUE_KEY: [[]]})
    out = _run(auto_logs.run_auto_log_prune(x_internal_key="shh", db=db))
    assert out == {"rows": 0, "blobs": 0, "retained": 0, "due": 0, "held": 0}
    assert db.params_for(DUE_KEY)[0]["days"] == auto_logs.AUTO_LOG_RETENTION_DAYS, (
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






def test_the_count_that_decides_the_cap_is_taken_under_the_lock(logdir, verified):
    """The 12/24h cap is count-then-insert, so the DECIDING count needs the
    lock -- and the INSERT has to be inside the same hold.

    Without it, two uploads from one account that both see 11 rows both commit
    and the account ends the day on 13. There is no row to take FOR UPDATE --
    the row being counted is the one about to be written -- so the lock is
    keyed on the steam_id VALUE (#202/#203/#207).

    ASSERTED AS A SANDWICH, not as "a lock appears before a count". The route
    now reads the bucket TWICE: once cheaply and unlocked, only to refuse
    early and save the scrub and the gzip, and once under the lock, which is
    the read the cap is actually made of. An assertion that the FIRST count
    follows the lock would now demand the expensive thing this design exists
    to avoid; one that merely found a lock and a count in that order would be
    satisfied by the unlocked read alone. So what is checked is that between
    the lock and the INSERT there is a count -- which is the property #207
    names, and the only one that survives both reads existing.
    """
    db = _ok_db()
    _run(auto_logs.upload_auto_log(_request(), db))

    order = [sql for sql, _ in db.log]
    lock_at = next((i for i, s in enumerate(order) if LOCK_KEY in s), None)
    insert_at = next((i for i, s in enumerate(order) if INSERT_KEY in s), None)
    assert lock_at is not None, (
        "no advisory lock on the upload path; the cap is a bare "
        "count-then-insert and two concurrent uploads can exceed it")
    assert insert_at is not None, "the upload no longer inserts a row"
    assert lock_at < insert_at, (
        "the lock is taken AFTER the INSERT (%d vs %d), so it serialises "
        "nothing" % (lock_at, insert_at))

    counts_under_lock = [i for i, s in enumerate(order)
                         if COUNT_KEY in s and lock_at < i < insert_at]
    assert counts_under_lock, (
        "the cap is counted only OUTSIDE the lock (lock at %d, insert at %d, "
        "counts at %r). An unlocked count proves nothing about the moment of "
        "the INSERT -- #207 refuted exactly that shape -- so the deciding "
        "read has to be re-taken under the hold"
        % (lock_at, insert_at,
           [i for i, s in enumerate(order) if COUNT_KEY in s]))

    params = [p for sql, p in db.log if LOCK_KEY in sql][0]
    assert params == {"cls": auto_logs.AUTO_LOG_LOCK_CLASS, "h": STEAM}, (
        "the lock must be keyed on the account it is protecting, in this "
        "route's own class, got %r" % (params,))


def test_the_upload_lock_is_not_in_the_applications_identity_namespace(logdir, verified):
    """The bare `pg_advisory_xact_lock(hashtext(steam_id))` expression is this
    application's IDENTITY lock: match reporting, queue join, session refresh
    and account deletion all take it on that same key.

    An automatic log upload taken on that key makes a seat's own match report
    wait behind its own log upload. The two-argument overload is a separate
    lock space, and this route may use it only because it is the sole writer
    AND the sole counter of kind='auto' rows -- the question #707 says to ask
    is never "which keyspace" but "which other sites must exclude this one".

    The class value is asserted to DIFFER from the other class in the tree
    rather than to equal a number written here twice: two classes that
    collide are one namespace again, which is the whole defect back.
    """
    db = _ok_db()
    _run(auto_logs.upload_auto_log(_request(), db))

    lock_sql = [sql for sql, _ in db.log if LOCK_KEY in sql]
    assert lock_sql, "no advisory lock taken at all"
    for sql in lock_sql:
        assert "CAST(:cls AS integer)" in sql, (
            "the upload lock is the one-argument identity form (%s); a seat "
            "leaving a match would queue its own match report behind this "
            "upload's compression and blob write" % sql)

    import pc_portrait
    assert auto_logs.AUTO_LOG_LOCK_CLASS != pc_portrait.PC_P_LOCK_CLASS, (
        "AUTO_LOG_LOCK_CLASS collides with PC_P_LOCK_CLASS (%d); a shared "
        "class is a shared namespace and the separation is gone"
        % auto_logs.AUTO_LOG_LOCK_CLASS)


def test_the_expensive_work_is_not_done_inside_the_lock(logdir, verified):
    """The scrub, the gzip and the blob write happen BEFORE the lock is taken.

    They are work on this request's own bundle: they touch no shared row and
    need no exclusion, so a hold across them buys nothing and costs the next
    caller all of it -- by main's own measurement the scrub alone reaches
    ~2.4 s on a large bundle, and the api runs one worker.

    Measured by where the blob appears relative to the lock: the write is the
    last of the three, so a blob on disk before the lock statement is proof
    that all of it ran outside.
    """
    seen = {}
    real_write = auto_logs._write_blob

    def note_write(path, data):
        seen["blob_at"] = len(db.log)
        return real_write(path, data)

    db = _ok_db()
    auto_logs._write_blob = note_write
    try:
        _run(auto_logs.upload_auto_log(_request(), db))
    finally:
        auto_logs._write_blob = real_write

    order = [sql for sql, _ in db.log]
    lock_at = next((i for i, s in enumerate(order) if LOCK_KEY in s), None)
    assert lock_at is not None, "no advisory lock taken at all"
    assert "blob_at" in seen, "the blob was never written"
    assert seen["blob_at"] <= lock_at, (
        "the blob was written at statement %d, AFTER the lock at %d -- the "
        "scrub, the compression and a multi-megabyte write are all being "
        "held inside one account's advisory lock"
        % (seen["blob_at"], lock_at))


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


# ── the kind discriminator on the admin and reporter surfaces ────────────────
#
# Migration 336 gave bug_reports a `kind` ('report' | 'auto'). These exercise
# the three API doors that have to act on it: the admin list, the admin detail
# pane, and the reporter's DM comment relay. The Discord bot's own half is out
# of scope for this file by ownership, not by accident.

LIST_KEY = "log_filename, log_bytes, kind FROM bug_reports"
DETAIL_KEY = "status, triage_notes, created_at, updated_at, kind"
EVENTS_KEY = "FROM bug_report_events"
KIND_KEY = "SELECT kind FROM bug_reports WHERE id = :rid"
BY_NUMBER_KEY = "WHERE bug_reports.bug_number"
OWNER_KEY = "FROM players WHERE players.steam_id"
TOUCH_KEY = "UPDATE bug_reports SET updated_at"

RID = UUID("33333333-3333-4333-8333-333333333333")
DISCORD = "123456789012345678"


class _Obj:
    """An ORM row stand-in: attributes only, which is all these handlers read."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


@pytest.fixture
def admin(monkeypatch):
    """Past the admin gate. The gate has its own tests; the subject here is
    what the handler does with `kind` once it is through."""
    async def _yes(db, steam_id):
        return True
    monkeypatch.setattr(main, "_is_admin", _yes)
    monkeypatch.setattr(main, "_verify_admin_hmac", lambda *a, **k: True)


def _summary_row(**over):
    row = {"id": RID, "bug_number": 41, "created_at": datetime(2026, 9, 19, tzinfo=timezone.utc),
           "steam_id": STEAM, "display_name": "Player", "mod_version": "1.41.0",
           "severity": "medium", "category": "gameplay", "status": "open",
           "description": "d", "log_filename": "x.gz", "log_bytes": 10, "kind": "report"}
    row.update(over)
    return row


def test_the_admin_list_says_which_rows_are_an_automatic_upload(admin):
    """Both kinds are listed -- an admin should SEE automatic uploads -- but
    the list has to say which is which, because the triage affordances beside
    a row (status, comment) reach a waiting player for one and nobody for the
    other."""
    db = Scripted({LIST_KEY: [[_summary_row(kind="auto", bug_number=41),
                               _summary_row(kind="report", bug_number=42)]]})
    out = _run(main.list_bug_reports(admin_steam_id=STEAM, hmac_signature="s", status=None,
                                  severity=None, kind=None, limit=50, offset=0, db=db))
    got = {r["bug_number"]: r["kind"] for r in out["reports"]}
    assert got == {41: "auto", 42: "report"}, got


def test_a_listed_row_with_no_kind_reads_as_a_player_filed_report(admin):
    """A row written before 336's backfill has kind NULL. The list must not
    hand a null out into a `str` field -- 'report' is the conservative
    reading, and it is what such a row actually is."""
    db = Scripted({LIST_KEY: [[_summary_row(kind=None)]]})
    out = _run(main.list_bug_reports(admin_steam_id=STEAM, hmac_signature="s", status=None,
                                  severity=None, kind=None, limit=50, offset=0, db=db))
    assert out["reports"][0]["kind"] == "report"


def test_the_detail_pane_is_told_the_kind(admin):
    """The pane is where the decision to comment or change a status is taken,
    so it needs the same field the list has."""
    db = Scripted({DETAIL_KEY: [[{"id": RID, "bug_number": 41, "player_id": None,
                                  "steam_id": STEAM, "display_name": "Player",
                                  "mod_version": "1.41.0", "game_version": "1.0.0",
                                  "severity": "medium", "category": "gameplay",
                                  "description": "d", "repro_steps": None,
                                  "log_filename": None, "log_bytes": None,
                                  "status": "open", "triage_notes": None,
                                  "created_at": datetime(2026, 9, 19, tzinfo=timezone.utc),
                                  "updated_at": None, "kind": "auto"}]],
                   EVENTS_KEY: [[]]})
    out = _run(main.get_bug_report(report_id=str(RID), admin_steam_id=STEAM,
                                   hmac_signature="s", include_log=False, db=db))
    assert out["kind"] == "auto"


def _comment_db(kind, *, linked=DISCORD):
    return Scripted({
        BY_NUMBER_KEY: [[_Obj(id=RID, bug_number=41, steam_id=STEAM, display_name="Player")]],
        KIND_KEY: [[{"kind": kind}] if kind is not None else []],
        OWNER_KEY: [[_Obj(id=PID, steam_id=STEAM, discord_id=linked, display_name="Player")]],
    })


def _user_comment(db, monkeypatch, key="internal-key"):
    monkeypatch.setenv("API_SECRET_KEY", key)
    req = schemas.BugReportUserCommentRequest(discord_id=DISCORD, comment="any news?")
    return _run(main.user_comment_on_bug_report(
        bug_number=41, req=req, request=_Req(), x_internal_key=key, db=db))


def test_a_reporter_dm_cannot_comment_on_an_automatic_upload(monkeypatch):
    """An automatic upload carries the uploader's steam_id, so the ownership
    match below the refusal PASSES for it. Without the kind check a DM would
    write a comment event onto a row the player never filed and cannot see --
    and that event table is the feed the bot answers from. Refused, and
    nothing written: no event, no parent touch, no commit."""
    db = _comment_db("auto")
    with pytest.raises(HTTPException) as ex:
        _user_comment(db, monkeypatch)
    assert ex.value.status_code == 404
    assert db.added == [], db.added
    assert db.sql_for(TOUCH_KEY) == []
    assert db.committed == 0


def test_a_row_whose_kind_is_null_is_refused_by_the_reporter_door(monkeypatch):
    """The same door, fail-closed on absence: a row predating the backfill is
    not demonstrably a ticket, so it is not treated as one."""
    db = _comment_db(None)
    with pytest.raises(HTTPException) as ex:
        _user_comment(db, monkeypatch)
    assert ex.value.status_code == 404
    assert db.added == []


def test_the_same_dm_still_reaches_the_players_own_ticket(monkeypatch):
    """The positive half, without which the two refusals above would also
    pass on a door that refused everything: a kind='report' row owned by this
    Discord account still takes the comment."""
    db = _comment_db("report")
    out = _user_comment(db, monkeypatch)
    assert out == {"status": "ok", "bug_number": 41}
    assert len(db.added) == 1
    assert getattr(db.added[0], "comment", None) == "any news?"
    assert db.sql_for(TOUCH_KEY), "the parent row is touched"
    assert db.committed == 1


def test_the_kind_is_read_before_the_ownership_test(monkeypatch):
    """Order matters for what the refusal says. An automatic row whose
    uploader has NO Discord link must still answer 404 -- 'no such ticket' --
    rather than 403 'not yours', which would confirm the row exists."""
    db = _comment_db("auto", linked=None)
    with pytest.raises(HTTPException) as ex:
        _user_comment(db, monkeypatch)
    assert ex.value.status_code == 404


_SQL_PREDICATE_WORDS = ("is distinct from", "is not distinct from", "where ",
                        " and ", " or ", "not in", "in (", "coalesce")


def test_the_reporter_door_comment_describes_the_statement_beneath_it(monkeypatch):
    """A PARAGRAPH THAT NAMES A MECHANISM THE CODE DOES NOT CONTAIN is the
    thing a later editor will restore.

    This comment used to say the kind was tested with `is distinct from
    'report'`. The statement is a bare SELECT and the test is made in Python,
    so anyone who "fixed" the code to match the prose would have added the
    predicate to the WHERE clause -- at which point a genuine kind='report'
    ticket returns no row, `row_kind is None` fires, and every reporter DM
    comment on a real ticket 404s. The door inverted by following its own
    documentation.

    So every SQL predicate the comment quotes has to be one the statement
    beneath it actually issues, and the executed half below proves the two
    descriptions are of a door that still opens.
    """
    source = inspect.getsource(main.user_comment_on_bug_report)
    marker = 'text("SELECT kind FROM bug_reports'
    assert marker in source, (
        "the reporter door no longer reads kind with the statement this test "
        "pins the comment against")
    head, _sep, tail = source.partition(marker)
    # The `#` markers come off before the quoted spans are read: a fragment
    # that wraps onto a second comment line would otherwise carry one into the
    # middle of itself and match nothing, which is a test that cannot fail.
    comment = " ".join(ln.strip().lstrip("#").strip()
                       for ln in head.splitlines()[-24:]
                       if ln.strip().startswith("#"))
    statement = " ".join((marker + tail.split(")).scalar_one_or_none()")[0]).split())

    quoted = re.findall(r"`([^`]+)`", comment)
    assert quoted, "the reporter-door comment quotes nothing it can be held to"
    checked = 0
    for fragment in quoted:
        flat = " ".join(fragment.split())
        if not any(word in flat.lower() for word in _SQL_PREDICATE_WORDS):
            continue
        checked += 1
        assert flat in statement, (
            "the comment above the reporter door describes the SQL predicate "
            "%r, and the statement it sits above is %r. One of the two is "
            "wrong, and it is the one that never runs." % (flat, statement))
    assert checked, (
        "no quoted fragment in the comment looks like a SQL predicate, so "
        "this test asserted nothing about it: %r" % (quoted,))
    # The executed half. A comment test that passes over a broken door is a
    # comment test, not a door test.
    assert _user_comment(_comment_db("report"), monkeypatch) == {
        "status": "ok", "bug_number": 41}


# ── the kind-scoped readers: one mutation control per site ──────────────────
#
# Every check above that proves a reader is scoped to kind = 'report' does it
# by reading source text. A source-text assertion is exactly the shape that
# can stop testing anything without anyone noticing -- the handler is
# restructured, the literal survives in a comment or in a sibling statement,
# and the check goes on passing over an ungated reader. So each site gets a
# MUTATION and a CONTROL here (#391): the predicate is deleted from that one
# function's source, the site's own check is re-run against the mutant and
# must FAIL, and the same check against the UNMUTATED source must pass. A
# check that passes on both is decoration and this test says so by name.
#
# The mutation is applied to a COPY of the function's source text. Nothing on
# disk is touched and main is never reloaded.

_KIND_SITES = {
    # name -> (the predicate to delete, how many times it must appear)
    "submit_bug_report": ("kind = 'report' AND ", 1),
    "recent_bug_reports": ("kind = 'report' AND ", 2),
    "recent_bug_report_events": ("br.kind = 'report' AND ", 2),
}

# The two readers that CARRY the column out rather than filtering on it. The
# predicate is a selected column, so the mutation is its removal from the
# select list.
_KIND_CARRIERS = {
    "list_bug_reports": ("log_filename, log_bytes, kind", "log_filename, log_bytes"),
    "get_bug_report": ("created_at, updated_at, kind", "created_at, updated_at"),
}


def _fn_source(name):
    return inspect.getsource(getattr(main, name))


def _normalise(text):
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("#")]
    return " ".join(" ".join(lines).split())


@pytest.mark.parametrize("name", sorted(_KIND_SITES))
def test_each_kind_scoped_filter_has_a_mutation_that_reddens_it(name):
    """Delete the predicate from this reader and its own check must fail."""
    predicate, expected = _KIND_SITES[name]
    live = _normalise(_fn_source(name))

    def check(src):
        # The site's own rule, stated once: the predicate appears exactly as
        # many times as the reader has arms, in code and not in a comment.
        return src.count(predicate.strip().rstrip("AND").strip()) == expected

    # CONTROL: the real source passes. Without this the test below would also
    # pass for a reader whose check was broken in some other way.
    assert check(live), (
        "%s: the live source does not carry %r %d time(s) -- the reader was "
        "restructured and this control must be rewritten, not deleted"
        % (name, predicate, expected))

    # MUTATION: drop the predicate everywhere it appears.
    mutant = live.replace(predicate.strip().rstrip("AND").strip(), "")
    assert mutant != live, "%s: the mutation changed nothing" % name
    assert not check(mutant), (
        "%s: the check passes with the kind predicate deleted, so it proves "
        "nothing about the reader" % name)


@pytest.mark.parametrize("name", sorted(_KIND_CARRIERS))
def test_each_kind_carrying_reader_has_a_mutation_that_reddens_it(name):
    """The two readers that SELECT kind rather than filtering on it."""
    present, absent = _KIND_CARRIERS[name]
    live = _normalise(_fn_source(name))

    def check(src):
        return present in src

    assert check(live), (
        "%s: the select list no longer reads %r; the admin surface cannot "
        "tell an automatic upload from a ticket" % (name, present))
    mutant = live.replace(present, absent)
    assert mutant != live, "%s: the mutation changed nothing" % name
    assert not check(mutant), (
        "%s: the check passes with kind dropped from the select list" % name)


def test_the_reporter_door_mutation_reddens_the_refusal_itself(monkeypatch):
    """The sixth site is BEHAVIOUR, not source text, so its mutation is too.

    `user_comment_on_bug_report` refuses a kind='auto' row. The mutation
    deletes the refusal's effect by answering 'report' for every row, and the
    door must then let an automatic upload through -- which is the failure the
    gate exists to prevent. The control is the same call against a row that
    really is a report, which must still succeed."""
    src = _normalise(_fn_source("user_comment_on_bug_report"))
    # The executed guard, named so a restructure cannot leave this passing.
    assert 'SELECT kind FROM bug_reports WHERE id = :rid' in src, (
        "the reporter door no longer reads kind in raw SQL")
    assert 'row_kind is None or row_kind != "report"' in src, (
        "the reporter door no longer refuses a non-report row")

    # MUTATION + CONTROL through the real handler: an auto row is refused,
    # a report row is not. If the first stopped refusing, this reddens.
    with pytest.raises(HTTPException) as refused:
        _user_comment(_comment_db("auto"), monkeypatch)
    assert refused.value.status_code == 404
    with pytest.raises(HTTPException) as refused_null:
        _user_comment(_comment_db(None), monkeypatch)
    assert refused_null.value.status_code == 404
    assert _user_comment(_comment_db("report"), monkeypatch) == {
        "status": "ok", "bug_number": 41}


# ── the lens findings, one reddening test each ───────────────────────────────
#
# Every test below fails against the code as it stood before the lens pass.
# Where the assertion could pass for the wrong reason it is paired with a
# control that must give the opposite answer (#391).


def _client_drops_its_token(body: str) -> bool:
    """`ApiClient.HandleSessionReject`, as it is actually written.

    plugin/ApiClient.cs:20916 is `if (body == null ||
    !body.Contains("session_required")) return;` -- a substring test on the
    raw response body, and the only gate in front of
    `SteamAuth.InvalidateSessionIf`. Modelled here rather than described,
    because the point of the test is that the server's wording either
    satisfies this exact test or it does not.
    """
    return body is not None and "session_required" in body


def test_the_401_detail_is_the_literal_the_client_matches(logdir, capsys):
    """THE SPELLING IS THE CONTRACT, and this route had it wrong at all three
    of its refusals.

    Every strict-session refusal in production answers `session_required`,
    with an underscore, and three of those sites carry a comment saying the
    literal is load-bearing. This module answered `session required`, with a
    space. `HandleSessionReject` would have tested false, kept the stale
    token, and the client's ONE session-repair path would never have run for
    this route -- while every other route the seat talks to kept working,
    because a session minted unverified is refused only by the strict check
    and this route is the only place the client meets it.

    The visible result is a seat that, at every qualifying room exit for the
    rest of the game session, reads three log files, scrubs up to 3.5 M
    characters, uploads several megabytes and is refused 401, forever.

    Asserted through the REAL refusals rather than by reading the source, and
    with the control that the old wording does NOT satisfy the client's test
    -- without that pair the assertion is just a restatement of the string.
    """
    assert auto_logs._SESSION_REJECT == "session_required"
    assert _client_drops_its_token(auto_logs._SESSION_REJECT), (
        "the constant does not satisfy the client's own substring test")
    # THE CONTROL: the probe can tell the two spellings apart, so a pass above
    # means something. If this ever holds, the test below proves nothing.
    assert not _client_drops_its_token("session required"), (
        "the modelled client gate accepts the space spelling too, so it "
        "cannot distinguish the defect from the fix")

    # 1. no token at all
    with pytest.raises(HTTPException) as no_token:
        _run(auto_logs.upload_auto_log(
            _request(token=None, explode_on_stream=True), Scripted()))
    # 2. a token that resolves to another account
    other = Scripted({SESSION_KEY: [[{"steam_id": OTHER}]], COUNT_KEY: [[_bucket(0)]]})
    with pytest.raises(HTTPException) as wrong_token:
        _run(auto_logs.upload_auto_log(_request(), other))
    # 3. the body's own id fails the strict check after the body is parsed
    with pytest.raises(HTTPException) as unverified:
        _run(auto_logs.upload_auto_log(_request(), _ok_db()))

    for name, ei in (("no token", no_token), ("token names another account", wrong_token),
                     ("strict check failed", unverified)):
        assert ei.value.status_code == 401, name
        assert _client_drops_its_token(str(ei.value.detail)), (
            "the %s refusal answers %r, which HandleSessionReject does not "
            "match -- the client keeps the stale token and re-uploads a "
            "multi-megabyte bundle at every room exit for the rest of the "
            "session" % (name, ei.value.detail))


def test_no_refusal_on_this_route_spells_the_session_literal_any_other_way():
    """The class, not the three lines (#432).

    Three copies of one cross-process contract are three chances to drift,
    which is how they drifted in the first place. The source must carry the
    space spelling nowhere at all, and the constant must be what the raises
    use.
    """
    import io as _io
    src = _io.open(auto_logs.__file__, encoding="utf-8", newline="").read()
    tree = ast.parse(src)

    # STRING VALUES ONLY, never the raw file. Comments and docstrings in this
    # module QUOTE the old spelling deliberately -- that is what the note
    # explaining the defect is for -- so a grep over the source would either
    # fail on its own explanation or force the explanation to go vague. A
    # predicate's literals are not its prose; 336 reached the same conclusion
    # about reading a constraint's rendered text.
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in docstrings:
                continue
            assert "session required" not in node.value, (
                "a string VALUE in auto_logs.py carries the space spelling "
                "(line %d): %r" % (node.lineno, node.value))
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        call = node.exc
        if not isinstance(call, ast.Call):
            continue
        kw = {k.arg: k.value for k in call.keywords}
        code = kw.get("status_code")
        if isinstance(code, ast.Constant) and code.value == 401:
            sites.append(kw.get("detail"))
    assert len(sites) == 3, (
        "expected the three strict-session refusals this route has, found %d"
        % len(sites))
    for detail in sites:
        assert isinstance(detail, ast.Name) and detail.id == "_SESSION_REJECT", (
            "a 401 on this route spells its detail inline instead of using "
            "the shared constant; that is exactly how the three sites drifted")


def test_the_cap_refusal_carries_a_retry_after_the_client_can_read(logdir, verified):
    """The bucket is twelve per 24 HOURS and nothing on the wire said so.

    The client's whole memory of a refusal is its 300-second debounce, and its
    comment calls a 429 "terminal, never retried" -- true of one bundle, not
    of the bucket. So the next qualifying exit built and sent a full bundle
    again: over a long sitting, twenty-odd further uploads of several
    megabytes, every one read, scrubbed, escaped, sent and discarded.

    The limiter's own 429 in main already sets this header and the client
    already parses it (`ApiClient.FormatRequestError` appends it,
    `MailClient.RetryAfterSeconds` reads it), so this is the server half of a
    mechanism that exists at both ends.
    """
    db = _ok_db(auto_count=auto_logs.AUTO_LOG_PER_STEAM_PER_DAY)
    with pytest.raises(HTTPException) as ei:
        _run(auto_logs.upload_auto_log(_request(), db))

    assert ei.value.status_code == 429
    headers = ei.value.headers or {}
    assert "Retry-After" in headers, (
        "the cap refusal carries no Retry-After, so nothing on the wire says "
        "the refusal lasts the better part of a day: headers=%r" % (headers,))
    assert headers["Retry-After"].isdigit(), headers["Retry-After"]


def test_the_retry_after_is_the_rolling_windows_reopening(logdir, verified):
    """And it is the REAL reopening, not a flat 24 hours.

    The window rolls, so the bucket reopens when its oldest row turns 24 --
    a seat three hours in should be told twenty-one hours, not a day. The
    control is a bucket whose oldest row is nearly a day old: it must come
    back with a much SMALLER number, which a hardcoded window cannot do.
    """
    def _retry_after(hours_old):
        db = Scripted({
            COUNT_KEY: [[_bucket(auto_logs.AUTO_LOG_PER_STEAM_PER_DAY,
                                 datetime.now(timezone.utc) - timedelta(hours=hours_old))]],
            PLAYER_KEY: [[{"id": PID}]],
        })
        with pytest.raises(HTTPException) as ei:
            _run(auto_logs.upload_auto_log(_request(), db))
        return int((ei.value.headers or {})["Retry-After"])

    fresh = _retry_after(3)
    stale = _retry_after(23)

    assert 20 * 3600 <= fresh <= 21 * 3600 + 60, (
        "a bucket whose oldest upload is three hours old should reopen in "
        "about twenty-one hours, got %ds" % fresh)
    # THE CONTROL: a fixed figure would answer the same for both.
    assert stale < fresh, (
        "the Retry-After does not move with the oldest row (%ds for a 3h-old "
        "bucket, %ds for a 23h-old one), so it is a constant wearing the "
        "header's name" % (fresh, stale))
    assert stale <= 3600 + 60, (
        "a bucket about to roll should reopen within the hour, got %ds" % stale)


def test_a_full_bucket_is_refused_before_the_bundle_is_processed(logdir, verified):
    """The refusal must be the CHEAP answer, not the expensive one.

    A seat that reached its cap two hours into a long sitting is refused at
    every remaining room exit. If that refusal came after the scrub, the gzip
    and the blob write, the capped seat would pay the full cost of an upload
    to be told no -- which is the state the cap exists to prevent.
    """
    calls = []
    real = auto_logs._compress_blob
    auto_logs._compress_blob = lambda s: (calls.append(1), real(s))[1]
    try:
        db = _ok_db(auto_count=auto_logs.AUTO_LOG_PER_STEAM_PER_DAY)
        with pytest.raises(HTTPException) as ei:
            _run(auto_logs.upload_auto_log(_request(), db))
    finally:
        auto_logs._compress_blob = real

    assert ei.value.status_code == 429
    assert calls == [], (
        "the bundle was compressed before the cap refused it; a capped seat "
        "pays for an upload it is never allowed to make")
    assert _blobs(logdir) == [], "a blob was written for a refused upload"
    # CONTROL: the same instrumentation DOES fire when the upload is allowed,
    # so the empty list above is evidence and not a broken probe.
    calls2 = []
    real2 = auto_logs._compress_blob
    auto_logs._compress_blob = lambda s: (calls2.append(1), real2(s))[1]
    try:
        _run(auto_logs.upload_auto_log(_request(), _ok_db()))
    finally:
        auto_logs._compress_blob = real2
    assert calls2 == [1], "the probe never fires at all, so it proves nothing"


@pytest.mark.parametrize("stage", ["compress", "write"])
def test_the_cpu_and_io_work_does_not_block_the_event_loop(logdir, verified, stage):
    """Both halves of the storage path run off the loop, and this measures it.

    The scrub was already moved to a worker thread. The compression on the
    next line and the blob write below it were not, and they cost the same
    order of magnitude: gzip over a multi-megabyte bundle is hundreds of
    milliseconds of uninterruptible CPU, and the api runs ONE uvicorn worker
    by design. On the loop, that is time in which no queue join, match report,
    bet or chat poll on the box makes any progress.

    Measured by whether a 5 ms ticker keeps ticking while the stage runs --
    with the control below proving the ticker registers nothing when the same
    delay is taken ON the loop, so a pass means the work moved rather than the
    probe being blind.
    """
    DELAY = 0.3
    real_compress, real_write = auto_logs._compress_blob, auto_logs._write_blob

    def slow_compress(s):
        time.sleep(DELAY)
        return real_compress(s)

    def slow_write(path, data):
        time.sleep(DELAY)
        return real_write(path, data)

    async def _ticks_during(body):
        ticks = [0]
        stop = asyncio.Event()

        async def ticker():
            while not stop.is_set():
                ticks[0] += 1
                await asyncio.sleep(0.005)

        task = asyncio.create_task(ticker())
        await asyncio.sleep(0.02)          # let the ticker get going
        before = ticks[0]
        await body()
        during = ticks[0] - before
        stop.set()
        await task
        return during

    async def upload():
        await auto_logs.upload_auto_log(_request(), _ok_db())

    async def block_on_the_loop():
        time.sleep(DELAY)

    if stage == "compress":
        auto_logs._compress_blob = slow_compress
    else:
        auto_logs._write_blob = slow_write
    try:
        during = asyncio.run(_ticks_during(upload))
    finally:
        auto_logs._compress_blob = real_compress
        auto_logs._write_blob = real_write

    # THE CONTROL, first: the same probe against the same delay taken on the
    # event loop must see nothing. Without it, a green result above could
    # simply mean the ticker never ran.
    blocked = asyncio.run(_ticks_during(block_on_the_loop))
    assert blocked <= 1, (
        "the probe counted %d ticks through a %ss block ON the loop, so it "
        "cannot tell blocking from non-blocking" % (blocked, DELAY))
    assert during >= 5, (
        "only %d ticks got through while the %s stage ran, against %d for a "
        "deliberate block -- the work is still on the event loop and every "
        "other request on this worker waits for it" % (during, stage, blocked))


def test_an_automatic_upload_does_not_spend_a_human_bug_number(logdir, verified):
    """`bug_number` is the counter a player is quoted, and automatic uploads
    were drawing from it.

    The column is `NOT NULL DEFAULT nextval('bug_reports_number_seq')` with a
    unique index. The automatic INSERT did not supply it, so every upload took
    the next number that names a ticket in #bug-reports, in admin triage and
    in the ops `bug-log:N` verb -- and retention then deleted the row while
    the sequence stayed where it was. One opted-in seat at the cap takes ~168
    numbers a fortnight; the player who files next is told #1,247 with nine
    hundred numbers behind them naming nothing, which reads as data loss and
    cannot be undone.
    """
    db = _ok_db()
    _run(auto_logs.upload_auto_log(_request(), db))
    insert = db.sql_for(INSERT_KEY)[0]

    assert "nextval('bug_reports_auto_number_seq')" in insert, (
        "the automatic INSERT does not supply bug_number, so the column "
        "default fires and each upload spends a human bug number: %s" % insert)
    # THE CONTROL: it must be the SEPARATE sequence and not the human one
    # named explicitly, which would be the same defect spelled out.
    assert "bug_reports_number_seq'" not in insert.replace(
        "bug_reports_auto_number_seq'", ""), (
        "the automatic INSERT names the human bug-number sequence: %s" % insert)


def test_migration_350_gives_automatic_rows_their_own_descending_numbers():
    """The schema half of the same defect, read from the file that ships.

    A comment claiming automatic rows cannot take a human number is a claim
    about the whole state space (#302); the CHECK is what makes it true of
    every writer, including one nobody has written yet.
    """
    path = os.path.join(HERE, "..", "sql", "350_bug_reports_auto_number.sql")
    sql = open(path, encoding="utf-8").read()
    flat = " ".join(sql.split())

    assert "CREATE SEQUENCE IF NOT EXISTS bug_reports_auto_number_seq" in flat
    assert "INCREMENT BY -1" in flat, "the automatic sequence does not descend"
    assert "MAXVALUE -1" in flat, (
        "the automatic sequence is not capped below zero, so it can reach the "
        "human range")
    assert "CHECK (kind <> 'auto' OR bug_number < 0)" in flat, (
        "nothing at the schema level stops an automatic row from holding a "
        "human bug number")
    # One-directional by construction: it must say nothing about report rows,
    # or it becomes a second, weaker copy of what 086 already guarantees and
    # can refuse a row the bug form writes.
    assert "kind <> 'report'" not in flat and "kind = 'report' AND" not in flat, (
        "the CHECK constrains the player-filed side too; it must not be able "
        "to refuse anything the bug form writes")
    # The post-check has to be able to FAIL, and to have a control (#391).
    assert "'auto', 999000001" in flat, "no probe offers the defect to the CHECK"
    assert "'auto', -999000001" in flat and "'report', 999000002" in flat, (
        "the post-check has no control, so a CHECK that refused everything "
        "would pass it")


def test_the_admin_list_can_be_filtered_to_player_filed_reports(admin):
    """One opted-in seat writes more rows in a day than the bug form does in a
    month, and they are written 'open'/'low'/'other' -- which is what an
    untriaged player report looks like too.

    So neither status nor severity separates them, and page one of the triage
    list is fifty machine rows with a player's two-day-old ticket on page
    three. Carrying `kind` on the row lets an admin SEE which is which; this
    is what lets them ASK.
    """
    db = Scripted({LIST_KEY: [[_summary_row()]]})
    _run(main.list_bug_reports(admin_steam_id=STEAM, hmac_signature="s", status=None,
                               severity=None, kind="report", limit=50, offset=0, db=db))
    sql = db.sql_for(LIST_KEY)[0]
    params = db.params_for(LIST_KEY)[0]
    assert "kind = :kind" in sql, (
        "?kind is accepted and then ignored, which is the shape of a filter "
        "that silently returns everything: %s" % sql)
    assert params.get("kind") == "report", params

    # THE CONTROL: omitted, the list is unchanged and shows both kinds. A
    # predicate that appeared unconditionally would hide automatic uploads
    # from an admin who did not ask, which is the opposite mistake.
    plain = Scripted({LIST_KEY: [[_summary_row()]]})
    _run(main.list_bug_reports(admin_steam_id=STEAM, hmac_signature="s", status=None,
                               severity=None, kind=None, limit=50, offset=0, db=plain))
    assert "kind = :kind" not in plain.sql_for(LIST_KEY)[0], (
        "the list now filters by kind even when no kind was asked for")


def test_an_upload_stops_before_it_eats_the_reserve_the_bug_form_needs(logdir, verified,
                                                                       monkeypatch):
    """This corpus shares its volume with player-filed bug-report attachments,
    and it is the half that grows on its own.

    When the volume fills, THIS route is correct: it unlinks, answers 503, and
    the client retries after the next match. The player-filed path is not --
    its write failure is caught and fallen through, so the report commits with
    no attachment and the player is answered 200. So the path that can back
    off does, while there is still room for the one that cannot (#276/#430).
    """
    monkeypatch.setattr(auto_logs, "_free_bytes",
                        lambda d: auto_logs.AUTO_LOG_FREE_SPACE_RESERVE_BYTES)
    with pytest.raises(HTTPException) as ei:
        _run(auto_logs.upload_auto_log(_request(), _ok_db()))
    assert ei.value.status_code == 503, (
        "a volume too full to store this without eating the reserve must be "
        "retryable, got %s" % ei.value.status_code)
    assert _blobs(logdir) == [], (
        "a blob was written on a volume the guard had already refused")

    # CONTROL 1: with room to spare the same upload lands, so the refusal
    # above is about the space and not about the guard refusing everything.
    monkeypatch.setattr(auto_logs, "_free_bytes", lambda d: 10 ** 12)
    assert _run(auto_logs.upload_auto_log(_request(), _ok_db()))["log_persisted"] is True

    # CONTROL 2: a volume that will not report its free space must not become
    # a refusal. An unknown figure is no reason to drop a log.
    monkeypatch.setattr(auto_logs, "_free_bytes", lambda d: -1)
    assert _run(auto_logs.upload_auto_log(_request(), _ok_db()))["log_persisted"] is True


# ── the player-filed path's own half of the shared volume ────────────────────

class _ReportSession(Scripted):
    """Scripted, plus the two session calls submit_bug_report makes."""

    async def flush(self):
        from uuid import uuid4 as _uuid4
        # What a real flush does that this handler depends on: the row gets
        # its id, which is what names the blob file.
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = _uuid4()

    async def refresh(self, obj):
        return None


def _file_a_report(db, monkeypatch, log_text="a log", explode=False):
    monkeypatch.setattr(main, "_is_admin", _no_admin)
    monkeypatch.setattr(main, "_mark_mod_seen", _noop_mark)
    if explode:
        import builtins
        real_open = builtins.open

        def exploding_open(*a, **kw):
            if len(a) > 1 and "w" in str(a[1]):
                raise OSError("no space left on device")
            return real_open(*a, **kw)

        monkeypatch.setattr(builtins, "open", exploding_open)
    req = schemas.BugReportRequest(steam_id=STEAM, description="it broke",
                                   log_text=log_text)
    return _run(main.submit_bug_report(req, _request(), db)), db


async def _no_admin(db, steam_id):
    return False


async def _noop_mark(db, player):
    return None


def test_a_bug_report_whose_log_could_not_be_stored_says_so_on_the_row(logdir,
                                                                       monkeypatch):
    """A log was attached and it is gone, and the row has to record that.

    Falling through left `log_filename` NULL, which is the SAME state as a
    report filed with no log at all. An admin opening the row a week later
    sees "no attachment" and cannot tell that one was sent -- so a player who
    attached their log and described a crash looks like a player who did not
    bother, and the only record is one api-log line thirty thousand lines
    away.

    `log_bytes = 0` is the marker and needs no schema change: it is
    unreachable for a stored blob, because this arm runs only when a
    non-empty log was sent and gzip of anything is never zero bytes.
    """
    db = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
    out, db = _file_a_report(db, monkeypatch, explode=True)
    row = db.added[0]

    assert out["log_persisted"] is False
    assert row.log_filename is None, "a filename was kept for a blob that is not there"
    assert row.log_bytes == 0, (
        "the row records nothing about the log that was attached and lost; it "
        "is indistinguishable from a report filed with no log at all, got %r"
        % (row.log_bytes,))


def test_a_bug_report_filed_with_no_log_is_still_distinguishable(logdir, monkeypatch):
    """THE CONTROL for the marker above, on both sides.

    A report with no log attached must leave log_bytes NULL -- if it were
    also 0, the marker would mean nothing -- and a report whose log DID store
    must carry its real size.
    """
    none_attached = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
    _file_a_report(none_attached, monkeypatch, log_text="")
    row = none_attached.added[0]
    assert row.log_bytes is None, (
        "a report with no log attached records log_bytes=%r, so the 'attached "
        "and lost' marker cannot be told from 'never attached'" % (row.log_bytes,))

    stored = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
    out, stored = _file_a_report(stored, monkeypatch, log_text="a real log body")
    kept = stored.added[0]
    assert out["log_persisted"] is True
    assert kept.log_bytes and kept.log_bytes > 0, (
        "a stored log records %r bytes" % (kept.log_bytes,))
