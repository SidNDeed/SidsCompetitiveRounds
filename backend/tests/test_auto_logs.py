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
import textwrap
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

# SYNTHETIC ACCOUNT IDS, and the fixture needs them to be.
#
# These two were the maintainer's own real test accounts. Nothing here reads
# an account's history, so a fixture never needed a real one -- and this is a
# public tree, where a value like that is republished on every clone and
# permanently links a stable identifier to a file. `76561198000000001` and
# `...002` are the shape the rest of the suite already uses: a valid 17-digit
# Steam64 with a filler account part that resolves to nobody.
#
# `test_this_branchs_files_name_no_real_account` below is what keeps them that
# way. It names no real id -- a test that asserted "the real one is absent"
# would have to write the real one down -- and instead requires every Steam
# -shaped literal in the files THIS BRANCH owns to come from _SYNTHETIC_IDS.
# (This line used to cite a test_this_files_account_ids_are_synthetic, which
# is not a test in this file or any other -- backticks deliberately omitted
# there, because a citation in this file's convention is a claim that the name
# resolves. Someone checking it would have found nothing and concluded the
# allow-list guard had been removed: a comment naming a mechanism the tree
# does not carry, #432/#459. The guard below now holds every backticked
# citation in this file to a test that exists.)
STEAM = "76561198000000001"
OTHER = "76561198000000002"
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

    def scalars(self):
        """`.scalars().all()`: the first column of every scripted row."""
        return _Res([next(iter(r.values())) if isinstance(r, dict) else r
                     for r in self._rows()])

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
        # EVERY STATEMENT AND EVERY END OF A TRANSACTION, IN ORDER. `log` is
        # statements only, and several cases pin it exactly; since round 8 a
        # request is several short transactions (R7-M4), and whether one was
        # ENDED before a wait is a question about the order of the two.
        self.events = []
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
        self.events.append(sql)
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
            self.events.append("COMMIT-FAILED")
            raise RuntimeError("scripted commit failure")
        self.events.append("COMMIT")
        self.committed += 1

    async def rollback(self):
        self.events.append("ROLLBACK")
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


@pytest.fixture(autouse=True)
def no_markers_held_over(monkeypatch):
    """`_ORPHAN_HELD` is the same kind of process state for the orphan sweep,
    and leaks the same way: a test whose marker unlink fails would otherwise
    decide which candidates the NEXT test's sweep is allowed to look at."""
    monkeypatch.setattr(auto_logs, "_ORPHAN_HELD", {})


@pytest.fixture(autouse=True)
def no_cursor_carried_over(monkeypatch):
    """`_ORPHAN_CURSOR` is the third piece of that same process state, and it
    leaks worse than the other two: it decides which NAMES the next pass's
    window starts at, so without this a case would inherit a position in a
    name space that belongs to a different directory entirely and read an
    empty window as a correct one."""
    monkeypatch.setattr(auto_logs, "_ORPHAN_CURSOR", [""])


@pytest.fixture(autouse=True)
def no_reserve_lock_carried_over(monkeypatch):
    """`_BLOB_RESERVE_LOCK` and `_BLOB_WRITE_STARTED` are the fourth and fifth,
    and they leak ACROSS EVENT LOOPS: every case here runs on its own
    (`_run` is asyncio.run). A contended asyncio.Lock is bound to the loop it
    was contended on, and a section abandoned as its loop closed never runs
    the hand-on that releases the lock and clears the stamp. Without this, a
    case that leaves the module's own lock held hands that state to every
    later case in the process that uses it, here or in another file; a case
    meeting it on a new loop gets RuntimeError from the acquire, which the
    route answers 503 "log storage unavailable" (the signature of the two
    real-route cases of test_ticket_redaction.py in the whole-suite run at
    603fdcd7). Cases that install their own lock still do; this only means
    none of them ever touches the import-time one."""
    monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
    monkeypatch.setattr(auto_logs, "_BLOB_WRITE_STARTED", [0.0])


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
    #
    # FOUR TRANSACTIONS SINCE ROUND 8 (R7-M4), EVERY ONE OF THEM ENDED. T0
    # (the token), T1a (the session check and the cheap count) and T1 (the
    # lock and the count that admits) each end in a rollback before the wait
    # that follows them; T2 is the one this case fails, and the INSERT arm
    # rolls it back itself -- BEFORE its cleanup, which is R7-L1's order. So
    # four rollbacks, no commit, and the one thing done on the session after
    # the failed INSERT is that rollback.
    assert db.rolled_back == 4 and db.committed == 0, (
        db.rolled_back, db.committed)
    insert_at = max(i for i, e in enumerate(db.events) if INSERT_KEY in e)
    assert db.events[insert_at + 1:] == ["ROLLBACK"], db.events[insert_at:]


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
    assert out == {"rows": 1, "blobs": 1, "retained": 0, "undurable": 0,
                   "due": 1, "held": 0}
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

    with _explode_on("stuck.log.gz"):
        out = _run(auto_logs.prune_auto_logs(db))

    assert out == {"rows": 1, "blobs": 1, "retained": 1, "undurable": 0,
                   "due": 2, "held": 1}
    ids = db.params_for("DELETE FROM bug_reports")[0]["ids"]
    assert ids == [R2], (
        "the row whose blob could not be removed was deleted anyway -- its "
        "blob is now unnameable: %r" % (ids,))
    assert stuck.exists() and not fine.exists()
    assert "keeping row" in capsys.readouterr().out


R3 = UUID("44444444-4444-4444-8444-444444444444")


def _explode_on(*names):
    """Replace the module's own `os` so the named blobs raise the error a
    read-only mount or a lost permission produces, and everything else
    unlinks for real.

    THROUGH `auto_logs.os` AND NOT THROUGH `pathlib`. Every filesystem call
    on this path goes through the module's `os` binding -- which is what
    makes the crash simulation possible at all -- and retention's unlink is
    `_unlink_existing`, the same three-way helper the sweep's deletion uses.
    A patch of `pathlib.Path.unlink` would no longer reach it, and would
    reach pytest's own machinery besides.
    """
    real_unlink = os.unlink

    def _boom(path, *a, **kw):
        if os.path.basename(str(path)) in names:
            raise PermissionError("read-only file system")
        return real_unlink(path, *a, **kw)
    return mock.patch.object(auto_logs, "os", _OsProxy(unlink=_boom))


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

    assert first == {"rows": 0, "blobs": 0, "retained": 2, "undurable": 0,
                     "due": 2, "held": 2}
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
        "rows": 0, "blobs": 0, "retained": 0, "undurable": 0, "due": 0,
        "held": 0}
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
    assert out == {"rows": 2, "blobs": 0, "retained": 0, "undurable": 0,
                   "due": 2, "held": 0}
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
        "rows": 0, "blobs": 0, "retained": 0, "undurable": 0, "due": 0,
        "held": 0}
    assert db.params_for(DUE_KEY)[0]["days"] == 30


def test_an_empty_secret_never_authorises_the_prune(logdir, monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "")
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.run_auto_log_prune(x_internal_key="", db=Scripted()))
    assert e.value.status_code == 403


def test_the_opportunistic_prune_never_fails_an_upload(logdir, verified, monkeypatch, capsys):
    # `[0.0]` -- which is what this line used to say -- makes the prune due
    # only on a machine whose UPTIME already exceeds _PRUNE_MIN_INTERVAL_S,
    # because the throttle reads `time.monotonic()`. On a box booted within the
    # last hour the throttle fired, `_maybe_prune` returned immediately, and
    # this test passed its first assertion while exercising nothing at all
    # (#342). A NEGATIVE stamp is due regardless of uptime.
    monkeypatch.setattr(auto_logs, "_LAST_PRUNE", [-1e12])
    # SINCE ROUND 8 THE PASS IS A TASK OF ITS OWN ON A SESSION OF ITS OWN
    # (R7-M4, #607): it holds its connection across its unlink pass by
    # design, so it must not run on -- or be awaited by -- the request. The
    # session factory it reaches is replaced here by one whose due-row read
    # fails, and a fresh task set keeps this case's pass apart from any other.
    prune_db = Scripted({}, fail_on=DUE_KEY)

    class _Session:
        async def __aenter__(self):
            return prune_db

        async def __aexit__(self, *exc):
            return False

    import database
    monkeypatch.setattr(database, "async_session", lambda: _Session())
    monkeypatch.setattr(auto_logs, "_BACKGROUND", set())
    db = Scripted({COUNT_KEY: [[_bucket(0)]], PLAYER_KEY: [[{"id": PID}]],
                   INSERT_KEY: [[{"bug_number": 11}]]})
    seen = {}

    async def go():
        out = await auto_logs.upload_auto_log(_request(), db)
        # WHAT THE PASS HAD ASKED WHEN THE UPLOAD ANSWERED: nothing. It is
        # started by the upload and never waited for by it.
        seen["asked"] = list(prune_db.log)
        seen["tasks"] = len(auto_logs._BACKGROUND)
        await asyncio.gather(*list(auto_logs._BACKGROUND))
        return out

    out = _run(go())
    assert out["bug_number"] == 11
    # The positive signal that the prune RAN, read before the count it implies:
    # a missing line here means the throttle swallowed the pass, which is the
    # failure the stamp above exists to prevent.
    assert "[AUTO-LOG] prune failed" in capsys.readouterr().out, (
        "the opportunistic prune did not run at all, so this test asserts "
        "nothing about what an upload does when it fails")
    assert seen["tasks"] == 1 and seen["asked"] == [], (
        "the upload answered with %d pass(es) in flight, after the pass had "
        "asked %r -- it waited on the pass instead of answering first"
        % (seen["tasks"], seen["asked"]))
    assert prune_db.sql_for(DUE_KEY) and db.sql_for(DUE_KEY) == [], (
        "the pass did not run on a session of its own: its due-row read went "
        "to %s" % ("the request's session" if db.sql_for(DUE_KEY) else "nowhere"))
    # The upload's own session: three transactions ended before their waits
    # (T0, T1a, T1) and T2 committed; the pass's failure touched none of it.
    assert db.committed == 1 and db.rolled_back == 3, (
        db.committed, db.rolled_back)


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
    """The BLOBS in the directory, never the markers beside them.

    Every blob is written with an `<id>.orphan-candidate` sidecar in place from
    before its first byte, so a bare directory listing counts two files per
    upload. The tests below that ask "did a blob survive" mean the blob; the
    marker is a separate question and `_markers` asks it.
    """
    return sorted(p.name for p in logdir.iterdir()
                  if p.is_file()
                  and not p.name.endswith(auto_logs._ORPHAN_MARKER_SUFFIX))


def _markers(logdir):
    return sorted(p.name for p in logdir.iterdir()
                  if p.name.endswith(auto_logs._ORPHAN_MARKER_SUFFIX))


class _OsProxy:
    """The real `os` with named calls replaced, for the module to use in
    place of it.

    WHY A PROXY AND NOT `monkeypatch.setattr(os, "write", ...)`. Every
    filesystem call on the blob path goes through `auto_logs.os` -- the
    open, the writes, both fsyncs, the unlinks -- so replacing the module's
    binding reaches exactly this module and nothing else. Patching the real
    `os` module would reach pytest's own capture, which writes to descriptors
    with the same call.

    A name this proxy does not override is delegated, INCLUDING the ones read
    by capability test: `getattr(os, "O_DIRECTORY", None)` finds whatever the
    platform has, unless a test deliberately supplies one (the crash
    simulation does, so the directory barrier the api container takes is
    exercised on a seat whose own `os` has no directory handle to open).
    """

    def __init__(self, **over):
        self._over = over

    def __getattr__(self, name):
        try:
            return self._over[name]
        except KeyError:
            return getattr(os, name)


def test_a_failed_blob_write_leaves_no_file_behind(logdir, verified):
    """open() succeeds, write() fails: the partial file must not survive, and
    neither must its marker.

    THIS IS THE DETERMINATE ARM, and its whole point is that the collector
    never has to be involved. `prune_auto_logs` walks ROWS and this id is never
    inserted, so that sweep cannot see the file; `prune_orphan_blobs` walks
    MARKERS and would collect it one age gate later, which is a fortnight of a
    shared volume spent on a failure this arm can resolve in a millisecond.
    Both halves are asserted: the blob is gone, and the marker that would have
    named it to the sweep is gone with it.

    (An earlier version of this docstring said nothing could ever find the file
    and called it a permanent leak. That was true of the tree it was written
    against and stopped being true when the marker and the sweep landed; the
    prose is the claim, so it moves with the mechanism.)
    """
    # THE INJECTION MOVED TO `os.write`, because `_write_blob` no longer goes
    # through the builtin `open`: it opens a descriptor so that it can fsync
    # the CONTENTS and then the directory ENTRY before the row naming them is
    # inserted (R3-M2). The state this test needs is unchanged and is still
    # produced for real -- a prefix of the blob lands on the volume and then
    # the write raises.
    def exploding_write(fd, data):
        os.write(fd, bytes(data)[:8])
        raise OSError("no space left on device")

    real_os = auto_logs.os
    auto_logs.os = _OsProxy(write=exploding_write)
    try:
        with pytest.raises(HTTPException) as ei:
            _run(auto_logs.upload_auto_log(_request(), _ok_db()))
    finally:
        auto_logs.os = real_os

    assert ei.value.status_code == 503, "a storage failure is retryable, not a 500"
    assert _blobs(logdir) == [], (
        "a partial blob survived a failed write: %s" % _blobs(logdir))
    assert _markers(logdir) == [], (
        "the blob went and its marker stayed: %s. A marker with no blob is "
        "harmless, but leaving one here means the determinate arm is relying "
        "on the sweep to finish its cleanup" % _markers(logdir))


def test_an_indeterminate_commit_keeps_the_blob(logdir, verified, capsys):
    """The one arm that must NOT clean up.

    A commit that raises may still have committed -- the acknowledgement can be
    lost after the server durably wrote. Unlinking here destroys the only copy
    of the log a live row promises, which reads as corruption. Keeping it costs
    disk. The cheap reversible error is the right one (#276).

    This is the exact inverse of the two tests above, and it is why the cleanup
    cannot simply be hoisted into one `finally`.

    WHAT COLLECTS IT, because "keeping it costs disk" is only true if something
    eventually spends that disk back. The marker stamped before the blob's
    first byte is LEFT IN PLACE on this arm, and `prune_orphan_blobs` -- the
    orphan sweep the retention loop runs -- resolves it: a row naming the blob
    means the commit landed, so the marker is cleared and the file kept for
    ever; no row naming it means the blob and its marker go, one age gate
    later. So both halves are asserted here: the blob survives, and the marker
    that hands it to the sweep survives with it.
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
    assert _markers(logdir) == [kept[0] + auto_logs._ORPHAN_MARKER_SUFFIX], (
        "the marker was cleared on the arm that keeps its blob. The marker is "
        "the ONLY thing that offers this file to the sweep, so clearing it "
        "here is what makes the kept blob permanent: %r" % (_markers(logdir),))
    assert kept[0] not in auto_logs._MARKERS_IN_FLIGHT, (
        "the finished request still owns the marker, so the sweep will skip "
        "it for the life of the process")
    out = capsys.readouterr().out
    assert "INDETERMINATE" in out and kept[0] in out, (
        "the id must be printed, because an operator reading this line is the "
        "fast path to the same file the sweep reaches an age gate later; "
        "got: %r" % out)



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
    assert out == {"rows": 0, "blobs": 0, "retained": 0, "undurable": 0,
                   "due": 0, "held": 0}
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


def test_the_scrub_and_the_compression_are_not_done_inside_the_lock(logdir, verified):
    """The SCRUB and the GZIP happen before the lock. The blob write does not,
    and that is deliberate.

    THIS TEST CHANGED DIRECTION FOR ONE HALF OF ITS SUBJECT, so it says which
    half and why. It used to require the blob write outside the lock too. That
    ordering had a cost the earlier round did not price: a lock wait or a count
    that raised, AFTER the write, left a file on disk that no row would ever
    name -- invisible to `prune_auto_logs`, which walks rows -- and answered
    500, which the client half retries. The admission decision now comes first,
    so a blob exists only for an upload the cap has already accepted.

    What must stay outside is the expensive part, and it is the part that was
    always the point: the scrub reaches ~2.4 s on a large bundle by main's own
    measurement and the gzip is the same order. The write is neither -- it is
    bounded by `_BUG_LOG_MAX_GZ` (8 MiB), it runs on a worker thread, and the
    exclusion it sits inside is keyed on ONE account, so the only request that
    can wait on it is the same seat uploading twice inside its own 300 s
    client debounce.

    Measured on the two call sites, not on the prose: the scrub and the
    compression must both record a statement index at or before the lock's.
    """
    seen = {}
    real_scrub = main._scrub_pass_one
    real_compress = auto_logs._compress_blob
    real_write = auto_logs._write_blob

    def note_scrub(text):
        seen["scrub_at"] = len(db.log)
        return real_scrub(text)

    def note_compress(scrubbed):
        seen["gzip_at"] = len(db.log)
        return real_compress(scrubbed)

    def note_write(path, data):
        seen["blob_at"] = len(db.log)
        return real_write(path, data)

    db = _ok_db()
    main._scrub_pass_one = note_scrub
    auto_logs._compress_blob = note_compress
    auto_logs._write_blob = note_write
    try:
        _run(auto_logs.upload_auto_log(_request(), db))
    finally:
        main._scrub_pass_one = real_scrub
        auto_logs._compress_blob = real_compress
        auto_logs._write_blob = real_write

    order = [sql for sql, _ in db.log]
    lock_at = next((i for i, s in enumerate(order) if LOCK_KEY in s), None)
    assert lock_at is not None, "no advisory lock taken at all"
    for label, key in (("scrub", "scrub_at"), ("compression", "gzip_at")):
        assert key in seen, "the %s never ran, so this test measured nothing" % label
        assert seen[key] <= lock_at, (
            "the %s ran at statement %d, AFTER the lock at %d -- the expensive "
            "pass over the whole bundle is being held inside one account's "
            "advisory lock" % (label, seen[key], lock_at))

    # THE OTHER HALF, ASSERTED POSITIVELY so the new ordering cannot quietly
    # revert: the write is INSIDE the hold, which is what makes the admitted
    # -upload-only property true.
    assert "blob_at" in seen, "the blob was never written"
    assert seen["blob_at"] > lock_at, (
        "the blob was written at statement %d, BEFORE the lock at %d -- a "
        "failure of the lock or the count would then leave a file no row "
        "names and nothing collects" % (seen["blob_at"], lock_at))


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

# ── the readers left UNSCOPED ON PURPOSE, each with its own control ──────────
#
# THE MATRIX ABOVE COVERED ONLY THE SITES THAT WERE CHANGED, which made the
# sweep it claims to be a sweep of one direction. Three of the nine
# `bug_reports` readers were dispositioned "unscoped on purpose" in the notes
# (§1) and NOTHING held them to it: a later change that added `kind =
# 'report'` to the log download would make every automatic upload
# undownloadable -- the admin opens an auto row, clicks the log, gets a 404 --
# and every test in this file would still be green, because a sweep that only
# checks the scoped sites cannot see a site becoming scoped.
#
# So each one is pinned by its own statement, with the mutation being the
# ADDITION of a kind predicate rather than its removal. Log download first:
# it is the one whose accidental scoping costs the most, because serving an
# automatic log to an admin is the entire point of storing one.
#
# name -> (anchor that must appear, the scoped version that must NOT, why)
_KIND_UNSCOPED = {
    "download_bug_report_log": (
        "FROM bug_reports WHERE id = :rid",
        "FROM bug_reports WHERE kind = 'report' AND id = :rid",
        "downloading an automatic log is the whole reason one is stored; a "
        "kind predicate here 404s every auto row's log in admin triage"),
    "ack_bug_report_posted": (
        "UPDATE bug_reports SET channel_posted_at = NOW() ",
        "UPDATE bug_reports SET channel_posted_at = NOW() WHERE kind = 'report' ",
        "an id-targeted ack of a row the feed never emits; scoping it would "
        "make the bot's at-least-once ack silently stop acking"),
    "_record_bug_event": (
        "UPDATE bug_reports SET updated_at = NOW() WHERE id = :rid",
        "UPDATE bug_reports SET updated_at = NOW() WHERE kind = 'report' AND id = :rid",
        "an id-targeted touch reached only through gated callers; scoping it "
        "would stop an automatic row's activity timestamp moving at all"),

    # THE THREE ORM READERS THE MATRIX OMITTED (R2-L1). The sweep above was
    # derived by grepping for raw `bug_reports` SQL, so three readers that
    # reach the same table through `select(BugReport...)` were dispositioned in
    # the notes and held to it by nothing -- a sweep of one SPELLING rather
    # than of the OPERATION (#432/#330). Each gets its own add-a-kind-predicate
    # mutation here, on its own statement, for the same reason the raw-SQL ones
    # do: a later "consistency" pass that scoped them would change what an
    # automatic row can do in admin triage while every claimed reader control
    # stayed green.
    #
    # `kind` is deliberately UNMAPPED on the ORM model (models.py), so the
    # scoped spelling a consistency pass would reach for is a `text()`
    # predicate beside the id.
    "admin_comment_on_bug_report": (
        "select(BugReport.id).where(BugReport.id == rid)",
        "select(BugReport.id).where(text(\"kind = 'report'\"), BugReport.id == rid)",
        "the existence check an admin's comment goes through; scoping it 404s "
        "every attempt to comment on an automatic upload in triage"),
    "admin_change_bug_report_status": (
        "select(BugReport).where(BugReport.id == rid)",
        "select(BugReport).where(text(\"kind = 'report'\"), BugReport.id == rid)",
        "the row an admin's status change loads; scoping it makes an automatic "
        "upload impossible to triage, resolve or close"),
    "internal_comment_on_bug_report": (
        "select(BugReport.id).where(BugReport.id == rid)",
        "select(BugReport.id).where(text(\"kind = 'report'\"), BugReport.id == rid)",
        "the existence check behind the internal comment verb; scoping it "
        "stops the ops `bug-comment:` trail landing on an automatic row"),
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


@pytest.mark.parametrize("name", sorted(_KIND_UNSCOPED))
def test_each_deliberately_unscoped_reader_stays_unscoped(name):
    """The three readers §1 dispositioned "unscoped on purpose".

    A disposition nothing enforces is a comment. The mutation here runs the
    other way round from the two matrices above: the predicate is ADDED, and
    the check must fail -- so the day someone "completes the sweep" by scoping
    the log download, this reddens and says what it costs.

    Anchored on the statement rather than on the function, and the anchor is
    asserted to occur EXACTLY ONCE inside that function's span before anything
    is concluded from it (#432/#279): a handler holding two `UPDATE
    bug_reports` statements would otherwise let a check pass on the one nobody
    asked about.
    """
    anchor, scoped, why = _KIND_UNSCOPED[name]
    live = _normalise(_fn_source(name))

    assert live.count(anchor) == 1, (
        "%s: the statement this control is anchored on occurs %d time(s) in "
        "the function, not once -- the anchor has to be re-derived before the "
        "result below means anything (%r)" % (name, live.count(anchor), anchor))

    def check(src):
        # The property: this reader reads/writes by id, and says nothing about
        # kind. Two halves, because either alone can pass for the wrong
        # reason -- the anchor alone would survive a second scoped copy, and
        # "no kind" alone would survive the statement being deleted outright.
        return anchor in src and "kind" not in src.split(anchor)[1][:120]

    # CONTROL: the live source is unscoped, which is the disposition §1 records.
    assert check(live), (
        "%s is no longer unscoped, and the note says it must be: %s"
        % (name, why))

    # MUTATION: scope it, the way a later "consistency" pass would.
    mutant = live.replace(anchor, scoped)
    assert mutant != live, "%s: the mutation changed nothing" % name
    assert not check(mutant), (
        "%s: the check still passes with a kind predicate added to the "
        "statement, so it proves nothing about the reader staying unscoped "
        "(%s)" % (name, why))


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

    The client lane's plugin/ApiClient.cs:20916 is `if (body == null ||
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


def test_migration_373_gives_automatic_rows_their_own_descending_numbers():
    """The schema half of the same defect, read from the file that ships.

    A comment claiming automatic rows cannot take a human number is a claim
    about the whole state space (#302); the CHECK is what makes it true of
    every writer, including one nobody has written yet.
    """
    path = os.path.join(HERE, "..", "sql", "373_bug_reports_auto_number.sql")
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

    # CONTROL 2 -- AND ITS DIRECTION IS NOW THE OPPOSITE OF WHAT IT WAS.
    # This block used to assert that an unmeasurable volume "must not become a
    # refusal". That made the reserve evaporate in exactly the conditions that
    # stop a volume answering: a guard at its weakest when it matters most
    # (#276). Unknown is a refusal, and the whole cost of that choice is one
    # 503 and one retry after the next match.
    monkeypatch.setattr(auto_logs, "_free_bytes", lambda d: -1)
    # Against the directory as CONTROL 1 left it, not against empty: control 1
    # deliberately landed a blob, and asserting `== []` here would fail for
    # that blob rather than for anything this arm did.
    before = sorted(_blobs(logdir))
    with pytest.raises(HTTPException) as ei:
        _run(auto_logs.upload_auto_log(_request(), _ok_db()))
    assert ei.value.status_code == 503, (
        "an unmeasurable volume must refuse retryably, got %s"
        % ei.value.status_code)
    assert sorted(_blobs(logdir)) == before, (
        "a blob was written on a volume whose free space could not be read")


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


# ── ROUND 2: the admission order, the reserve's serialisation, the collector ──


def test_an_admission_failure_leaves_no_blob_and_is_retryable(logdir, verified):
    """A lock or a count that raises must answer 503 and leave nothing behind.

    THE DEFECT THIS PINS. The advisory lock and the deciding count used to sit
    AFTER the blob write, outside any try. A lost connection, a lock wait
    killed by `idle_in_transaction_session_timeout`, a deadlock detector --
    each of them propagated as a 500 and left a file on disk that no row would
    ever name. `prune_auto_logs` walks ROWS, so nothing could ever find it, and
    500 is a code the client half retries, so the next match wrote another one.

    Two arms, because the two statements fail independently, plus a control so
    the refusals are about the failure and not about the route refusing
    everything.
    """
    # ARM 1: the lock statement itself raises.
    db = _ok_db()
    db.fail_on = LOCK_KEY
    with pytest.raises(HTTPException) as ei:
        _run(auto_logs.upload_auto_log(_request(), db))
    assert ei.value.status_code == 503, (
        "a failed advisory lock must be retryable (503), not a 500 the client "
        "retries against a server that has already written a file, got %s"
        % ei.value.status_code)
    assert _blobs(logdir) == [], (
        "the lock failed and a blob was left behind: %r" % (_blobs(logdir),))

    # ARM 2: the DECIDING count raises -- the second read, not the cheap one.
    calls = {"n": 0}
    real_bucket = auto_logs._auto_bucket

    async def flaky_bucket(db_, steam_id):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("scripted failure of the count under the lock")
        return await real_bucket(db_, steam_id)

    auto_logs._auto_bucket = flaky_bucket
    try:
        with pytest.raises(HTTPException) as ei:
            _run(auto_logs.upload_auto_log(_request(), _ok_db()))
    finally:
        auto_logs._auto_bucket = real_bucket
    assert ei.value.status_code == 503, (
        "a failed authoritative count must be retryable, got %s"
        % ei.value.status_code)
    assert calls["n"] == 2, (
        "the route made %d bucket read(s); this arm is only about the LOCKED "
        "one, so a run that never reached it proves nothing" % calls["n"])
    assert _blobs(logdir) == [], (
        "the count failed and a blob was left behind: %r" % (_blobs(logdir),))

    # CONTROL: the same request with neither failure lands, so the two
    # emptiness assertions above are not satisfied by a route that never
    # writes at all.
    assert _run(auto_logs.upload_auto_log(_request(), _ok_db()))["log_persisted"] is True
    assert len(_blobs(logdir)) == 1, (
        "the control upload did not store its blob")


def test_the_bucket_refusal_now_happens_before_anything_is_written(logdir, verified):
    """The 429 on the locked re-check has no blob to discard.

    It used to. The write came first, so a seat that filled its bucket in the
    window between the cheap read and the locked one paid a full scrub, a gzip
    and a multi-megabyte write and then had it unlinked again. The count
    decides first now, and the write never happens.
    """
    seen = {}
    real_write = auto_logs._write_blob

    def note_write(path, data):
        seen["wrote"] = True
        return real_write(path, data)

    # The cheap read passes; the locked read finds a full bucket.
    db = Scripted({
        COUNT_KEY: [[_bucket(0)], [_bucket(auto_logs.AUTO_LOG_PER_STEAM_PER_DAY)]],
        PLAYER_KEY: [[{"id": PID}]],
        INSERT_KEY: [[{"bug_number": 1}]],
    })
    auto_logs._write_blob = note_write
    try:
        with pytest.raises(HTTPException) as ei:
            _run(auto_logs.upload_auto_log(_request(), db))
    finally:
        auto_logs._write_blob = real_write

    assert ei.value.status_code == 429, (
        "a bucket full on the locked re-check must be the cap refusal, got %s"
        % ei.value.status_code)
    assert "wrote" not in seen, (
        "the blob was written before the cap refused; a write is supposed to "
        "happen only for an upload the count has already admitted")
    assert _blobs(logdir) == [], (
        "a blob survives a 429: %r" % (_blobs(logdir),))


def test_an_indeterminate_commit_names_a_blob_the_sweep_can_collect(logdir, verified,
                                                                    capsys):
    """The one arm that deliberately keeps a file says WHICH file, and the
    retention loop's orphan sweep is what removes it.

    Keeping the blob is right: PostgreSQL may have committed and lost only the
    acknowledgement, and deleting the log a committed row promises reads as
    corruption. What was missing is the other half -- nothing collected it, on
    a volume shared with player-filed attachments.
    """
    db = _ok_db()
    db.fail_commit = True
    with pytest.raises(HTTPException) as ei:
        _run(auto_logs.upload_auto_log(_request(), db))
    assert ei.value.status_code == 503
    kept = _blobs(logdir)
    assert len(kept) == 1, (
        "the indeterminate arm must KEEP its blob; found %r" % (kept,))

    out = capsys.readouterr().out
    assert ("%s=%s" % (auto_logs._ORPHAN_MARKER, kept[0])) in out, (
        "the indeterminate line does not name the file it kept, so the "
        "recovery identifier the sweep matches on is missing. Printed: %r"
        % (out,))


def _mark(logdir, name, age_s=None):
    """Put an orphan-candidate marker beside `name`, optionally aged.

    The sweep reads the MARKER's mtime, never the blob's, so a test that means
    "this candidate is old enough" has to age the marker.
    """
    marker = logdir / (name + auto_logs._ORPHAN_MARKER_SUFFIX)
    marker.write_bytes(name.encode("utf-8") + b"\n")
    if age_s is not None:
        stamp = time.time() - age_s
        os.utime(marker, (stamp, stamp))
    return marker


def _marker_names(logdir):
    return sorted(p.name for p in logdir.iterdir()
                  if p.name.endswith(auto_logs._ORPHAN_MARKER_SUFFIX))


class KindRows:
    """A `bug_reports` stand-in that EVALUATES the kind predicate instead of
    answering the same rows whatever the statement says.

    WHY THIS EXISTS. The control that is supposed to hold the sweep's all-kind
    lookup honest used to assert a SQL SUBSTRING against a fake whose script
    was keyed on a fragment of the statement. Adding `kind = 'auto'` to the
    predicate changed the statement and not the answer, so the named mutation
    left the test green while a real database would have stopped naming every
    player-filed attachment (#342/#431: a check that cannot fail is worse than
    no check).

    So this fake holds `(log_filename, kind)` rows and applies whatever
    predicate the statement actually carries: a `kind` mention filters the
    rows, and the COUNT arm filters the same way. The mutation the control
    names is then visible in the ANSWER.
    """

    def __init__(self, rows):
        self.rows = list(rows)
        self.log = []
        self.rolled_back = 0

    def _scoped(self, sql):
        flat = " ".join(sql.split())
        for kind in ("'auto'", '"auto"'):
            if "kind" in flat and kind in flat:
                return [r for r in self.rows if r[1] == "auto"]
        return list(self.rows)

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.log.append((sql, params))
        rows = self._scoped(sql)
        if "COUNT(*) AS n FROM bug_reports" in sql:
            return _Res([{"n": len([r for r in rows if r[0]])}])
        if "SELECT log_filename FROM bug_reports" in sql:
            wanted = set((params or {}).get("names") or [])
            return _Res([{"log_filename": r[0]} for r in rows if r[0] in wanted])
        return _Res([])

    async def rollback(self):
        self.rolled_back += 1

    def sql_for(self, key):
        return [sql for sql, _ in self.log if key in sql]


def _exec_mutant_pairs(fn, pairs):
    """`fn`'s source with every (anchor, replacement) applied, compiled against
    a COPY of the module's globals so the module itself is untouched.

    Each anchor is asserted to occur exactly once inside the function's own
    span before anything is concluded from the result (#432/#279): a mutation
    that silently matched two sites, or none, would make the red below mean
    something other than what the test says it means.
    """
    src = textwrap.dedent(inspect.getsource(fn))
    for anchor, replacement in pairs:
        assert src.count(anchor) == 1, (
            "the mutation anchor occurs %d time(s) in %s, not once -- re-derive "
            "it before reading anything into the result (%r)"
            % (src.count(anchor), fn.__name__, anchor))
        mutant_src = src.replace(anchor, replacement)
        assert mutant_src != src, "the mutation changed nothing"
        src = mutant_src
    namespace = dict(vars(auto_logs))
    exec(compile(src, "<mutant:%s>" % fn.__name__, "exec"), namespace)
    return namespace[fn.__name__]


def _exec_mutant(fn, anchor, replacement):
    return _exec_mutant_pairs(fn, [(anchor, replacement)])


# THE DELETED MECHANISM, as a mutation. Round 2's sweep took the attachment
# HEAP as its population: every file under the directory was a candidate and
# the pass was bounded at 10,000 examinations. These two edits put that
# population back -- the marker filter stops excluding anything and the name
# stops being derived from the marker's -- and every control below that claims
# the population is the marker set has to RED under them.
_HEAP_POPULATION = [
    ("            if not e.name.endswith(_ORPHAN_MARKER_SUFFIX):\n"
     "                continue\n",
     "            if False:\n"
     "                continue\n"),
    ("            blob = e.name[:-len(_ORPHAN_MARKER_SUFFIX)]\n",
     "            blob = e.name\n"),
]

# THE INERT TWIN: the same two sites, edited in the same shape, meaning the
# same thing. A control that reds under this is reacting to the site being
# touched rather than to the population changing (#342/#431).
_INERT_TWIN = [
    ("            if not e.name.endswith(_ORPHAN_MARKER_SUFFIX):\n"
     "                continue\n",
     "            if not str(e.name).endswith(_ORPHAN_MARKER_SUFFIX):\n"
     "                continue\n"),
    ("            blob = e.name[:-len(_ORPHAN_MARKER_SUFFIX)]\n",
     "            blob = e.name[:len(e.name) - len(_ORPHAN_MARKER_SUFFIX)]\n"),
]


def test_the_orphan_sweep_collects_a_marked_unreferenced_blob_and_only_that(logdir):
    """Four files, one sweep, four dispositions.

    The referenced control is a PLAYER-FILED row, not an automatic one. This
    sweep decides the fate of FILES on a shared volume, so what protects a file
    is a row of ANY kind naming it -- a `kind = 'auto'` predicate here would
    read a player-filed attachment as unreferenced.
    """
    orphan = "aaaaaaaa-0000-4000-8000-000000000001.log.gz"
    owned = "bbbbbbbb-0000-4000-8000-000000000002.log.gz"
    fresh = "cccccccc-0000-4000-8000-000000000003.log.gz"
    plain = "dddddddd-0000-4000-8000-000000000004.log.gz"
    for n in (orphan, owned, fresh, plain):
        (logdir / n).write_bytes(b"x")
    old = time.time() - 10_000
    for n in (orphan, owned, fresh, plain):
        os.utime(logdir / n, (old, old))
    _mark(logdir, orphan, age_s=10_000)
    _mark(logdir, owned, age_s=10_000)
    _mark(logdir, fresh)                       # marked, but young

    db = Scripted({
        "COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
        "SELECT log_filename FROM bug_reports": [[{"log_filename": owned}]],
    })
    out = _run(auto_logs.prune_orphan_blobs(db, min_age_s=3600))

    assert out["refused"] is False
    assert out["unlinked"] == 1, out
    assert out["cleared"] == 1, out
    assert not (logdir / orphan).exists(), "the marked unreferenced blob was not collected"
    assert not (logdir / (orphan + auto_logs._ORPHAN_MARKER_SUFFIX)).exists(), (
        "the blob went and its marker stayed; the next pass would keep asking "
        "about a file that no longer exists")
    assert (logdir / owned).exists(), (
        "a blob a bug_reports row names was deleted -- on a volume shared with "
        "player-filed attachments that is the report's only copy")
    assert not (logdir / (owned + auto_logs._ORPHAN_MARKER_SUFFIX)).exists(), (
        "the marker over a committed row was not cleared, so the sweep will "
        "re-ask the database about it for ever")
    assert (logdir / fresh).exists(), (
        "a blob whose marker is younger than the gate was collected; the row "
        "for it may still be in flight")
    assert (logdir / plain).exists() and out["candidates"] == 2, (
        "an UNMARKED file was examined. Nothing offers a referenced "
        "attachment to this sweep: %r" % (out,))

    names = db.params_for("SELECT log_filename FROM bug_reports")[0]["names"]
    assert plain not in names and fresh not in names, (
        "a file that is not a candidate was still offered to the database: %r"
        % (names,))


def test_the_sweep_population_is_the_marker_set_and_not_the_attachment_heap(logdir):
    """R2-H1, AND IT IS A METHOD CHANGE RATHER THAN A BIGGER NUMBER.

    The old pass enumerated the directory and bounded what it examined. That
    directory holds every player-filed attachment permanently and nothing in
    this tree deletes a referenced one, so the budget was spent on files the
    pass is REQUIRED to keep: past enough older referenced attachments, a newer
    orphan was never offered to the database at all.

    Here the heap is an order of magnitude larger than the old removal batch
    and the orphan is the NEWEST file in the directory -- the position the old
    ceiling excluded first. The live sweep offers exactly one name, because
    exactly one file carries a marker.
    """
    heap = []
    base = time.time() - 500_000
    for i in range(auto_logs._ORPHAN_BATCH * 3):
        name = "%08x-0000-4000-8000-000000000000.log.gz" % i
        (logdir / name).write_bytes(b"x")
        os.utime(logdir / name, (base + i, base + i))
        heap.append(name)
    orphan = "ffffffff-0000-4000-8000-00000000ffff.log.gz"
    (logdir / orphan).write_bytes(b"x")
    newest = time.time() - 10_000
    os.utime(logdir / orphan, (newest, newest))
    _mark(logdir, orphan, age_s=10_000)

    def _db():
        # The table names a blob, so the "this database does not own the
        # directory" refusal does not fire, and it names none of the heap --
        # which is the point: the heap must not be ASKED about at all.
        return Scripted({
            "COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
            "SELECT log_filename FROM bug_reports": [
                [{"log_filename": "a-blob-that-is-not-in-this-directory.log.gz"}]],
        })

    # MUTATION FIRST, so the control runs on a directory the mutant has
    # demonstrably not touched: the population becomes the heap again.
    mutant = _exec_mutant_pairs(auto_logs._marker_candidates, _HEAP_POPULATION)
    names, markers_total, owned, young, held, _ex, _cur, _un = mutant(
        logdir, time.time() - 3600, set(), set())
    assert len(names) > auto_logs._ORPHAN_BATCH, (
        "the heap-population mutant examined %d name(s); it is supposed to "
        "take the whole directory, so this control proves nothing" % len(names))

    # INERT TWIN at the same two sites: same shape, same meaning. The control
    # below must stay GREEN under it, or it is reacting to the site being
    # edited rather than to the population changing (#342/#431).
    twin = _exec_mutant_pairs(auto_logs._marker_candidates, _INERT_TWIN)
    t_names, t_total, t_owned, t_young, t_held, _tex, _tcur, _tun = twin(
        logdir, time.time() - 3600, set(), set())
    assert t_names == [orphan] and t_total == 1, (
        "the inert twin changed the population (%r); it is supposed to be the "
        "same filter spelled differently" % (t_names,))

    # CONTROL: the live sweep. One marker, one candidate, one removal, and the
    # heap is neither examined nor offered to the database.
    out = _run(auto_logs.prune_orphan_blobs(_db(), min_age_s=3600))
    assert out["candidates"] == 1 and out["markers"] == 1, out
    assert out["unlinked"] == 1 and not (logdir / orphan).exists(), (
        "the newest file in the directory was the orphan and it survived a "
        "pass with no examination ceiling: %r" % (out,))
    assert all((logdir / n).exists() for n in heap), (
        "an unmarked attachment was removed")
    assert not hasattr(auto_logs, "_ORPHAN_SCAN_MAX"), (
        "the examination ceiling is back. A cap over the attachment heap is a "
        "starvation class, which is why it was deleted rather than raised")


def test_a_marker_a_live_upload_owns_is_never_swept(logdir):
    """R2-M2, closed BY CONSTRUCTION rather than by an age.

    A final-path write that stalls for a whole tick used to be unlinkable
    before its INSERT, because a blob became a candidate the moment its bytes
    existed. The retention loop runs in the SAME process as the handler, so
    "is a request still working on this blob" is a question this process
    answers exactly: a name in `_MARKERS_IN_FLIGHT` is skipped whatever its
    age. The age gate below is the second line, for a marker left by a process
    life that has ended.
    """
    live = "aaaaaaaa-0000-4000-8000-00000000beef.log.gz"
    (logdir / live).write_bytes(b"x")
    _mark(logdir, live, age_s=10 ** 6)          # far past any gate

    db = Scripted({
        "COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
        "SELECT log_filename FROM bug_reports": [[]],
    })
    auto_logs._MARKERS_IN_FLIGHT.add(live)
    try:
        out = _run(auto_logs.prune_orphan_blobs(db, min_age_s=1))
    finally:
        auto_logs._MARKERS_IN_FLIGHT.discard(live)
    assert out["in_flight"] == 1 and out["candidates"] == 0, out
    assert (logdir / live).exists(), (
        "a blob a live upload was still writing was taken from under it")
    assert db.sql_for("SELECT log_filename FROM bug_reports") == [], (
        "the sweep asked the database about a blob it already knew was owned")

    # CONTROL: the same marker, same age, with nothing owning it -- collected.
    # So the survival above is about the registry and not about the file.
    out = _run(auto_logs.prune_orphan_blobs(
        Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                  "SELECT log_filename FROM bug_reports": [[]]}), min_age_s=1))
    assert out["unlinked"] == 1 and not (logdir / live).exists(), out


def test_the_marker_age_gate_is_bounded_by_the_handlers_own_deadline(logdir):
    """THE ARITHMETIC HALF OF THE BOUND, AND WHERE THE BUDGET IS SPENT.

    What T bounds is the interval between a marker's creation and the last
    instant at which a row naming its blob could still be INSERTED, and the
    gate is derived from it. This test holds the arithmetic (`gate > T + one
    tick`) and the three sites that spend the budget. The SPAN ITSELF is
    measured in `test_the_marked_span_deadline_covers_the_insert_and_the_commit`
    below, because a substring is not a measurement: an earlier version of
    this test asserted only this arithmetic and the presence of one `wait_for`
    call, and both stayed true while the INSERT and the commit ran under no
    ceiling at all (#342/#431).
    """
    T = auto_logs.AUTO_LOG_MARKED_SPAN_DEADLINE_S
    assert auto_logs._ORPHAN_MIN_AGE_S > T + auto_logs.AUTO_LOG_SWEEP_EVERY_S, (
        "the gate (%s s) is not strictly greater than T (%s s) plus one "
        "retention tick (%s s), so a write inside its own deadline can be "
        "swept" % (auto_logs._ORPHAN_MIN_AGE_S, T, auto_logs.AUTO_LOG_SWEEP_EVERY_S))

    handler = _normalise(inspect.getsource(auto_logs.upload_auto_log))
    assert handler.count("_span_budget(span_deadline)") == 4, (
        "the span's one deadline is spent at %d await(s) in the handler. The "
        "span has four -- the shielded section, T2's re-check under the lock "
        "(round 8), the INSERT and the commit -- and an await that does not "
        "take the budget is outside the bound"
        % handler.count("_span_budget(span_deadline)"))
    assert "asyncio.wait_for(asyncio.shield(section)" in handler, (
        "the deadline is no longer the wait_for around the SHIELDED section. "
        "Anchored on the prefix rather than the whole call, so a respelling of "
        "the timeout argument is not read as the shield going away")
    assert ("await asyncio.wait_for( _lock_and_count(db, req.steam_id), "
            "_span_budget(span_deadline))") in handler, (
        "T2's re-check under the lock is awaited outside the span's deadline")
    assert "row = (await asyncio.wait_for(db.execute(" in handler, (
        "the INSERT is awaited outside the span's deadline")
    assert "await asyncio.wait_for(db.commit(), left)" in handler, (
        "the commit is awaited outside the span's deadline")

    # MUTATION: the gate lowered below T. A blob whose marker is younger than
    # the deadline the handler is still inside becomes collectable, which is
    # the state the derivation exists to make unreachable.
    name = "aaaaaaaa-0000-4000-8000-0000000000aa.log.gz"
    (logdir / name).write_bytes(b"x")
    _mark(logdir, name, age_s=T / 2.0)

    def _db():
        return Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                         "SELECT log_filename FROM bug_reports": [[]]})

    lowered = _run(auto_logs.prune_orphan_blobs(_db(), min_age_s=T / 4.0))
    assert lowered["unlinked"] == 1 and not (logdir / name).exists(), (
        "with the gate below T the mid-deadline blob was NOT collected, so "
        "this control says nothing about the gate: %r" % (lowered,))

    # CONTROL: the live gate leaves the same blob alone.
    (logdir / name).write_bytes(b"x")
    _mark(logdir, name, age_s=T / 2.0)
    kept = _run(auto_logs.prune_orphan_blobs(_db()))
    assert kept["candidates"] == 0 and (logdir / name).exists(), (
        "the shipped gate collected a blob younger than the handler's own "
        "deadline: %r" % (kept,))


def test_the_orphan_sweep_refuses_a_database_that_knows_no_blobs(logdir, capsys):
    """`bug_reports` naming no blob AT ALL does not read as a directory full
    of orphans. It reads as a process talking to a database that does not own
    the directory -- a restored volume, a mis-set BUG_REPORT_LOG_DIR, a
    scratch database -- and the honest answer to that is to delete nothing
    (#276).
    """
    stale = "dddddddd-0000-4000-8000-000000000004.log.gz"
    (logdir / stale).write_bytes(b"x")
    _mark(logdir, stale, age_s=10_000)

    db = Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 0}]]})
    out = _run(auto_logs.prune_orphan_blobs(db, min_age_s=3600))
    assert out["refused"] is True
    assert (logdir / stale).exists(), "the sweep deleted a file on a database that names none"
    assert _marker_names(logdir), "the sweep cleared a marker it refused to act on"
    assert "orphan sweep REFUSED" in capsys.readouterr().out
    assert db.sql_for("SELECT log_filename FROM bug_reports") == [], (
        "the sweep went on to ask which files are known after deciding the "
        "database does not own this directory")


def test_the_sweeps_lookup_is_executed_against_rows_of_every_kind(logdir, capsys):
    """R2-M4: THE ALL-KIND LOOKUP, EXECUTED, NOT ASSERTED AS A SUBSTRING.

    The previous control scripted a fake on a fragment of the statement, so
    adding `kind = 'auto'` to the predicate changed the statement and not the
    answer and the named mutation stayed green. `KindRows` applies the
    predicate the statement actually carries, so the mutation is visible in
    what comes back.

    Both halves of the all-kind property are exercised here: the REFUSAL arm,
    whose count must see rows of every kind, and the naming arm, where a marked
    blob a PLAYER-FILED row names must be cleared rather than removed.
    """
    player = "aaaaaaaa-0000-4000-8000-0000000000a1.log.gz"
    auto = "bbbbbbbb-0000-4000-8000-0000000000b1.log.gz"
    gone = "cccccccc-0000-4000-8000-0000000000c1.log.gz"
    plain = "dddddddd-0000-4000-8000-0000000000d1.log.gz"

    def _plant():
        for n in (player, auto, gone, plain):
            (logdir / n).write_bytes(b"x")
            old = time.time() - 10_000
            os.utime(logdir / n, (old, old))
        for n in (player, auto, gone):
            _mark(logdir, n, age_s=10_000)

    def _rows():
        return KindRows([(player, "report"), (auto, "auto")])

    # REFUSAL ARM, all-kind: a database whose ONLY rows naming a blob are
    # player-filed still owns this directory, so the pass proceeds.
    _plant()
    db = KindRows([(player, "report")])
    out = _run(auto_logs.prune_orphan_blobs(db, min_age_s=3600))
    assert out["refused"] is False, (
        "a database naming only player-filed attachments was read as one that "
        "does not own this directory: %r" % (out,))
    assert (logdir / player).exists(), "a player-filed attachment was removed"
    assert (logdir / plain).exists(), "an unmarked file was removed"

    # MUTATION: the lookup scoped to kind='auto'. The player-filed row stops
    # naming its attachment, so a marked player attachment is read as
    # unreferenced and taken.
    _plant()
    mutant = _exec_mutant(
        auto_logs.prune_orphan_blobs,
        "WHERE log_filename = ANY(CAST(:names AS text[]))",
        "WHERE kind = 'auto' AND log_filename = ANY(CAST(:names AS text[]))")
    out = _run(mutant(_rows(), min_age_s=3600))
    assert not (logdir / player).exists(), (
        "the kind='auto' mutation left the player-filed attachment in place, "
        "so this control cannot see the defect it is named for: %r" % (out,))

    # INERT TWIN at the same site: the same predicate, spelled with the cast
    # written out. The control below must stay GREEN under it.
    _plant()
    twin = _exec_mutant(
        auto_logs.prune_orphan_blobs,
        "WHERE log_filename = ANY(CAST(:names AS text[]))",
        "WHERE log_filename = ANY(CAST(:names AS text [ ]))")
    out = _run(twin(_rows(), min_age_s=3600))
    assert (logdir / player).exists() and (logdir / auto).exists(), (
        "the inert twin changed behaviour; it is the same predicate respelled")
    assert not (logdir / gone).exists(), out

    # CONTROL: the live sweep. Both referenced blobs keep their bytes and lose
    # their markers; only the blob no row of any kind names is removed.
    _plant()
    out = _run(auto_logs.prune_orphan_blobs(_rows(), min_age_s=3600))
    assert (logdir / player).exists() and (logdir / auto).exists(), (
        "a referenced blob was removed: %r" % (out,))
    assert out["cleared"] == 2, out
    assert not (logdir / gone).exists() and out["unlinked"] == 1, out
    assert (logdir / plain).exists(), "an unmarked file was removed"


def _aged_corpus(logdir, count, first_mtime):
    """`count` aged, MARKED blobs, one second apart, OLDEST first.

    Returns the names in age order, so a test can say "the newest of them" and
    mean it whatever order the filesystem lists the directory in.
    """
    names = []
    for i in range(count):
        p = logdir / ("%08x-0000-4000-8000-00000000000%1d.log.gz" % (i, i % 10))
        p.write_bytes(b"x")
        stamp = first_mtime + i
        os.utime(p, (stamp, stamp))
        marker = _mark(logdir, p.name)
        os.utime(marker, (stamp, stamp))
        names.append(p.name)
    return names


def test_an_orphan_backlog_larger_than_one_batch_drains_over_ticks(logdir):
    """The bound that remains is on REMOVALS, and the docstring says a backlog
    drains across ticks. It does, because the files taken are gone by the next
    pass and the candidates are ordered oldest-first -- so the remainder is a
    backlog and not a set that keeps being skipped."""
    size = auto_logs._ORPHAN_BATCH + 3
    names = _aged_corpus(logdir, size, time.time() - 100_000)

    def _db():
        # The table names a blob (so the "this database does not own the
        # directory" refusal does not fire) and names none of THESE.
        return Scripted({
            "COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
            "SELECT log_filename FROM bug_reports": [
                [{"log_filename": "a-blob-that-is-not-in-this-directory.log.gz"}]],
        })

    first = _run(auto_logs.prune_orphan_blobs(_db(), min_age_s=3600))
    assert first["unlinked"] == auto_logs._ORPHAN_BATCH, first
    assert first["deferred"] == 3, (
        "the pass did not report what it left behind: %r" % (first,))
    assert [n for n in names if (logdir / n).exists()] == names[-3:], (
        "the pass removed something other than the oldest batch")

    second = _run(auto_logs.prune_orphan_blobs(_db(), min_age_s=3600))
    assert second["unlinked"] == 3 and second["deferred"] == 0, second
    assert not any((logdir / n).exists() for n in names), (
        "the backlog did not drain on the following tick")
    assert _marker_names(logdir) == [], (
        "every blob was collected and markers were left behind; the next pass "
        "would ask the database about files that no longer exist")


def test_a_marker_whose_blob_is_already_gone_is_cleared(logdir):
    """The state a crash between the two unlinks leaves, and it costs nothing.

    The blob goes before its marker, so the only thing an interrupted cleanup
    can leave is a marker naming a file that is absent. The marker is cleared,
    and the pass reports it as `marker_only` rather than as a removal: nothing
    was reclaimed, and a counter that says otherwise is what an operator reads
    when deciding whether a leak is draining (#304).
    """
    name = "aaaaaaaa-0000-4000-8000-0000000000cc.log.gz"
    _mark(logdir, name, age_s=10_000)          # marker, no blob
    db = Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                   "SELECT log_filename FROM bug_reports": [[]]})
    out = _run(auto_logs.prune_orphan_blobs(db, min_age_s=3600))
    assert out["marker_only"] == 1 and out["unlinked"] == 0, (
        "a marker whose blob was never on the volume was counted as a blob "
        "removed: %r" % (out,))
    assert _marker_names(logdir) == [], (
        "the marker for an absent blob survived, so this pass would re-ask the "
        "database about it on every tick for ever")


def test_the_retention_loop_runs_the_orphan_sweep():
    """The collector has to be WIRED, not merely written: a sweep nothing
    calls is the same leak with more code in it (#438/#443)."""
    src = _normalise(inspect.getsource(auto_logs.auto_log_retention_loop))
    assert "await prune_orphan_blobs(db)" in src, (
        "the retention loop does not call prune_orphan_blobs, so the blob the "
        "indeterminate-commit arm keeps is still permanent")
    assert "prune_orphan_blobs" not in _normalise(
        inspect.getsource(auto_logs._maybe_prune)), (
        "the opportunistic per-request prune calls the orphan sweep; a "
        "directory listing does not belong on a request")


def test_two_concurrent_uploads_cannot_both_spend_the_same_reserve(logdir, verified,
                                                                   monkeypatch):
    """THE BOUND: at most ONE automatic blob is written per free-space reading.

    `disk_usage().free` is a reading of the past. Two seats that both measure
    before either writes both pass, and the reserve held for player-filed
    reports is short by whatever the second one stores. The per-account
    advisory lock cannot close that -- two seats are two keys -- so the
    measure-and-write pair is taken under one process-wide asyncio lock, which
    is box-wide because the api runs a single uvicorn worker by design
    (#125/#651).

    Driven deterministically rather than hopefully: the first upload's write is
    HELD inside its worker thread until the second upload has had every chance
    to reach its own measurement. With the lock, the second cannot measure
    until the first has finished writing; without it, both read the same
    number and both land.

    TWO DIFFERENT ACCOUNTS, and that is the whole case. This control used to
    send the SAME steam id twice, which is a case the per-account advisory lock
    already excludes on a real database -- so removing the process-wide lock
    reddened it only because the scripted session here does not implement that
    advisory lock. The regression it claims to hold is the CROSS-ACCOUNT one:
    two seats are two advisory-lock keys and one volume, which is precisely the
    gap `_BLOB_RESERVE_LOCK` exists to close.
    """
    import threading

    blob_size = {"n": 0}
    writes_done = {"n": 0}
    room = {"n": 0}
    readings = []
    started = threading.Event()
    release = threading.Event()
    real_write = auto_logs._write_blob

    def held_write(path, data):
        blob_size["n"] = len(data)
        if not started.is_set():
            started.set()
            release.wait(10.0)
        real_write(path, data)
        writes_done["n"] += 1

    def fake_free(d):
        readings.append(writes_done["n"])
        return (auto_logs.AUTO_LOG_FREE_SPACE_RESERVE_BYTES
                + room["n"] - writes_done["n"] * blob_size["n"])

    def _seat(steam_id):
        """One upload from a named account, with the id in the BODY -- which is
        what the per-account advisory lock is keyed on."""
        return auto_logs.upload_auto_log(
            _request(_body(steam_id=steam_id)), _ok_db())

    async def drive():
        first = asyncio.create_task(_seat(STEAM))
        for _ in range(1000):
            if started.is_set():
                break
            await asyncio.sleep(0.005)
        assert started.is_set(), "the first upload never reached its write"
        second = asyncio.create_task(_seat(OTHER))
        # Every chance for the second to reach its own measurement while the
        # first is still inside its write.
        await asyncio.sleep(0.25)
        release.set()
        return await asyncio.gather(first, second, return_exceptions=True)

    # One preliminary upload, only to learn the blob size this bundle makes --
    # so the "room for exactly one" figure is DERIVED and cannot drift when
    # the fixture bundle changes.
    monkeypatch.setattr(auto_logs, "_free_bytes", lambda d: 10 ** 12)
    auto_logs._write_blob = held_write
    try:
        _run(_seat(STEAM))
        release.set()
        assert blob_size["n"] > 0
        room["n"] = blob_size["n"] + 16
        started.clear()
        release.clear()
        writes_done["n"] = 0
        readings.clear()
        for p in list(logdir.iterdir()):
            p.unlink()
        monkeypatch.setattr(auto_logs, "_free_bytes", fake_free)
        results = _run(drive())
    finally:
        auto_logs._write_blob = real_write
        release.set()

    codes = [r.status_code if isinstance(r, HTTPException) else 200 for r in results]
    assert sorted(codes) == [200, 503], (
        "with room above the reserve for exactly one blob the two uploads "
        "answered %r. Both landing means both measured the same free space "
        "and the reserve was spent twice." % (codes,))
    assert len(_blobs(logdir)) == 1, (
        "%d blob(s) on disk; the volume had room above the reserve for one"
        % len(_blobs(logdir)))
    assert STEAM != OTHER, (
        "the two seats have to be two accounts, or the per-account advisory "
        "lock is what the red below is measuring")
    assert sorted(readings) == [0, 1], (
        "the two measurements saw %r completed writes. They have to see "
        "different numbers, or the second measured a volume the first had not "
        "finished writing to." % (readings,))


def test_a_seat_that_cannot_take_the_blob_lock_in_time_refuses(logdir, verified,
                                                               monkeypatch):
    """The wait is BOUNDED, and running out of it is a refusal.

    A wedged volume blocks `_write_blob` inside its worker thread with the lock
    held. Without a ceiling every later upload would await it for ever and the
    route would stop answering at all -- the unhandled case failing in the
    worst available direction (#276/#430). With one, the seat is told 503 and
    tries after its next match.
    """
    monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK_WAIT_S", 0.05)

    async def blocked():
        async with auto_logs._BLOB_RESERVE_LOCK:
            return await asyncio.gather(
                auto_logs.upload_auto_log(_request(), _ok_db()),
                return_exceptions=True)

    (result,) = _run(blocked())
    assert isinstance(result, HTTPException), (
        "the upload returned %r instead of refusing while the blob lock was "
        "held by somebody else" % (result,))
    assert result.status_code == 503, result.status_code
    assert _blobs(logdir) == [], "a blob was written without the lock"

    # CONTROL: with the lock free the same upload lands, so the refusal above
    # is about the wait and not about the route.
    assert _run(auto_logs.upload_auto_log(_request(), _ok_db()))["log_persisted"] is True


def test_a_volume_already_stalled_refuses_now_instead_of_queueing(logdir, verified,
                                                                  monkeypatch,
                                                                  capsys):
    """WHAT THE BOUNDED WAIT IS PAID WITH.

    Until round 8 the wait for the blob-volume lock was served inside this
    request's open database transaction, so every second of it was a pooled
    connection checked out and idle. Since round 8 (R7-M4) the handler ends
    its transaction before the section starts and the wait costs no
    connection -- `test_thirty_concurrent_uploads_cannot_retain_the_pool`
    holds that. What it still costs is the request and the seconds: every
    arriving request, because the holder is stuck on a volume that is not
    answering, sits out the whole lock wait and ends in the same 503 it could
    have been given at once.

    So a pass STAMPS when its measure-and-write began, and an arriving request
    that finds one in flight past the ceiling refuses immediately. Both arms
    refuse; the test is about what the refusal COSTS (#430).

    THE SECOND UPLOAD IS ANOTHER ACCOUNT'S. Since round 8 a second upload for
    the SAME account waits for that account's turn (`_account_turn`) before
    it reaches the volume at all, which is a different wait with its own
    ceiling and its own test
    (`test_a_second_upload_for_one_account_waits_its_turn_and_no_longer`).

    Driven by a real held write rather than by a stamp set from here, so both
    halves are under test: the stamp a pass takes, and the pre-check that
    reads it.
    """
    # THE ANCHORS, asserted before anything is read into the results below:
    # each of the two lines this test's mutations target is ONE site inside
    # this handler's span (#432/#279).
    section = _normalise(inspect.getsource(auto_logs._reserve_stamp_and_write))
    assert section.count("if stalled_for >= _BLOB_WRITE_STALL_S:") == 1, (
        "the pre-check this test mutates is not a single site in the section")
    assert section.count("_BLOB_WRITE_STARTED[0] = time.monotonic()") == 1, (
        "the in-flight stamp is set at %d site(s), not one"
        % section.count("_BLOB_WRITE_STARTED[0] = time.monotonic()"))

    import threading

    monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK_WAIT_S", 1.0)
    real_write = auto_logs._write_blob
    started = threading.Event()
    release = threading.Event()

    def held_write(path, data):
        if not started.is_set():
            started.set()
            release.wait(10.0)
        real_write(path, data)

    async def drive():
        """One upload holds the volume; a second arrives after the ceiling."""
        first = asyncio.create_task(auto_logs.upload_auto_log(_request(), _ok_db()))
        for _ in range(2000):
            if started.is_set():
                break
            await asyncio.sleep(0.005)
        assert started.is_set(), "the first upload never reached its write"
        # Past the stall ceiling, with the first still inside its write.
        await asyncio.sleep(0.15)
        at = time.monotonic()
        second = await asyncio.gather(
            auto_logs.upload_auto_log(_request(_body(steam_id=OTHER)),
                                      _ok_db()),
            return_exceptions=True)
        waited = time.monotonic() - at
        release.set()
        await asyncio.gather(first, return_exceptions=True)
        return second[0], waited

    def run_drive():
        # A FRESH LOCK PER RUN. `asyncio.Lock` binds to the loop its first
        # CONTENDED acquire happens on and refuses a second one; each `_run`
        # here is its own loop. That is a property of this harness -- the api
        # has one loop for the life of the process -- so the lock is renewed
        # rather than the two phases being merged, which would stop them being
        # two independent measurements.
        monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
        started.clear()
        release.clear()
        for p in list(logdir.iterdir()):
            p.unlink()
        return _run(drive())

    monkeypatch.setattr(auto_logs, "_write_blob", held_write)
    monkeypatch.setattr(auto_logs, "_BLOB_WRITE_STALL_S", 0.05)
    result, waited = run_drive()
    assert isinstance(result, HTTPException) and result.status_code == 503, result
    assert waited < auto_logs._BLOB_RESERVE_LOCK_WAIT_S / 2, (
        "the second upload spent %.2fs queued before refusing, against a "
        "%.2fs lock wait -- it queued behind a volume already known to be "
        "stalled" % (waited, auto_logs._BLOB_RESERVE_LOCK_WAIT_S))
    assert "write in flight" in capsys.readouterr().out, (
        "the refusal does not say the volume was already stalled, so an "
        "operator cannot tell it from the ordinary lock-wait refusal")

    # NEGATIVE CONTROL: with the stall ceiling out of reach the same second
    # upload goes back to queueing for the full wait. Same held write, same
    # 503 -- so the measurement above is about the pre-check reading the
    # stamp, and not about the lock being held.
    monkeypatch.setattr(auto_logs, "_BLOB_WRITE_STALL_S", 10 ** 9)
    result, waited = run_drive()
    assert isinstance(result, HTTPException) and result.status_code == 503, result
    assert waited >= auto_logs._BLOB_RESERVE_LOCK_WAIT_S, (
        "without the stall pre-check the second upload refused after %.2fs, "
        "which is less than the %.2fs wait it was supposed to sit through -- "
        "the control is not exercising the queueing path"
        % (waited, auto_logs._BLOB_RESERVE_LOCK_WAIT_S))


def test_the_hold_on_the_open_transaction_is_measured_and_reported(logdir, verified,
                                                                   monkeypatch,
                                                                   capsys):
    """AN UNMEASURED HOLD IS THE ONE NOBODY CAN ARGUE ABOUT AFTERWARDS.

    The span this route added when admission moved ahead of the write -- the
    wait for the volume lock plus the measure-and-write under it -- is
    reported past a ceiling. Without the line, "the volume was slow" and "the
    route was slow" are the same log (#438/#443).

    THE NAME IS ROUND 7'S. Until round 8 that span ran inside an open
    transaction holding the per-account advisory lock, which is what the name
    says; since R7-M4 the transaction is ended before the section starts and
    the span holds the account's TURN and no connection, and the line says
    that. The test is kept under its name because earlier rounds' records
    cite it.
    """
    section = _normalise(inspect.getsource(auto_logs._reserve_stamp_and_write))
    assert section.count("if held >= _BLOB_HOLD_REPORT_S:") == 1, (
        "the report this test mutates is not a single site in the section")
    assert section.count("hold_started = time.monotonic()") == 1, (
        "the span's start is stamped %d time(s); the measurement below is "
        "anchored on one" % section.count("hold_started = time.monotonic()"))

    real_write = auto_logs._write_blob

    def slow_write(path, data):
        time.sleep(0.05)
        real_write(path, data)

    monkeypatch.setattr(auto_logs, "_write_blob", slow_write)
    monkeypatch.setattr(auto_logs, "_BLOB_HOLD_REPORT_S", 0.01)
    assert _run(auto_logs.upload_auto_log(_request(), _ok_db()))["log_persisted"] is True
    out = capsys.readouterr().out
    assert "slow blob volume" in out, (
        "an upload that held the volume lock past the report ceiling printed "
        "no measurement of it. Printed: %r" % (out,))
    measured = out.split("slow blob volume")[1][:200]
    assert STEAM in measured, (
        "the measurement does not name the account whose turn was held")
    assert "no database connection" in measured, (
        "the measurement no longer says the span held no connection, which "
        "is the R7-M4 fact an operator reading it needs: %r" % (measured,))

    # CONTROL: the same upload under a ceiling it cannot reach prints no such
    # line, so the assertion above is about the span and not about a line this
    # route emits on every request.
    for p in list(logdir.iterdir()):
        p.unlink()
    monkeypatch.setattr(auto_logs, "_BLOB_HOLD_REPORT_S", 10 ** 9)
    assert _run(auto_logs.upload_auto_log(_request(), _ok_db()))["log_persisted"] is True
    assert "slow blob volume" not in capsys.readouterr().out, (
        "the measurement is printed on every upload; past the ceiling is the "
        "only time it says anything")


# ── privacy: the fixtures name no real account ───────────────────────────────

_SYNTHETIC_IDS = {"76561198000000001", "76561198000000002"}

# The files THIS BRANCH owns. A tree-wide rule cannot be enforced against
# migrations that ran years ago against real accounts on purpose, and pinning
# the whole tree here would be a check that fails for reasons this branch
# cannot fix.
_BRANCH_FILES = (
    "api/auto_logs.py",
    "tests/test_auto_logs.py",
    "sql/336_bug_reports_kind.sql",
    "sql/373_bug_reports_auto_number.sql",
)


# EVERY 17-DIGIT STEAM IDENTIFIER, not one prefix of them (R2-L4).
#
# The pattern used to be `7656119\d{10}`, which covers the individual-account
# range this project's own accounts sit in and nothing else. The claim above
# the check was "every 17-digit Steam64 literal", and the gap between the two
# is a check that cannot fail for whole shapes of real identifier (#342/#431):
# a SteamID64 is a 64-bit value whose universe/type/instance bits decide its
# leading digits, so an individual account minted outside that block, a clan or
# group id (`7656119...` is individual; group ids begin `10358279...`), or a
# game-server id all read as ordinary numbers to the old pattern.
#
# So the shape is now "any 17-digit run that is not part of a longer number",
# which is the shape of every SteamID64 there is. The boundaries matter: an
# 18-digit Discord snowflake, or 17 digits inside a longer literal, must not be
# read as a Steam id and turned into a finding nobody can act on.
_STEAM64_SHAPE = re.compile(r"(?<!\d)\d{17}(?!\d)")

# The shapes the pattern is REQUIRED to catch, one case per shape, with the
# leading block that produces each. None of these is a real account: every one
# is a synthetic value built to exercise the pattern.
_STEAM64_SHAPE_CASES = {
    "individual, this project's block": "76561198000000001",
    "individual, a different instance": "76561202000000001",
    "clan/group": "10358279000000001",
    "game server": "90071992500000001",
}
_NOT_STEAM64_CASES = {
    "an 18-digit Discord snowflake": "123456789012345678",
    "16 digits": "1234567890123456",
    "17 digits inside a longer number": "x123456789012345678901",
}


def test_the_steam_identifier_pattern_catches_every_shape_it_claims():
    """The allow-list below is only as wide as the pattern that feeds it.

    One case per shape, plus the negative cases, because a pattern that matches
    one prefix while the prose says "every 17-digit Steam identifier" passes
    every test that exists at the time and stops meaning what its name says.
    """
    for why, value in _STEAM64_SHAPE_CASES.items():
        assert _STEAM64_SHAPE.findall(value) == [value], (
            "the pattern does not catch a %s identifier (%s), so an id of that "
            "shape pasted into a fixture would not redden the check below"
            % (why, value))
    for why, value in _NOT_STEAM64_CASES.items():
        assert _STEAM64_SHAPE.findall(value) == [], (
            "the pattern reads %s (%s) as a Steam identifier, which turns the "
            "check below into a finding nobody can act on" % (why, value))

    # CONTROL, in the direction that matters: the OLD prefix-only pattern
    # misses shapes this one catches, so the widening is a real change and not
    # a rewritten comment.
    old = re.compile(r"7656119\d{10}")
    missed = [v for v in _STEAM64_SHAPE_CASES.values() if not old.findall(v)]
    assert missed, (
        "the old prefix pattern caught every shape listed here, so this file "
        "is not testing the widening it claims")


def test_this_branchs_files_name_no_real_account():
    """Every Steam-shaped literal in the files this branch adds is synthetic.

    STATED AS AN ALLOW-LIST, NOT A DENY-LIST, and that is the point: a test
    asserting "the maintainer's id is absent" would have to write that id down,
    in a public tree, for ever. This names only the synthetic values and
    requires every 17-digit Steam identifier literal in these files -- of ANY
    shape, see `_STEAM64_SHAPE` -- to be one of them, so a real id pasted into
    a fixture reddens without a real id ever appearing here.
    """
    backend = pathlib.Path(HERE).parent
    found = {}
    for rel in _BRANCH_FILES:
        path = backend / rel
        assert path.exists(), "%s is missing; this check pins a file that moved" % rel
        text_of = path.read_text(encoding="utf-8")
        for hit in _STEAM64_SHAPE.findall(text_of):
            if hit in _STEAM64_SHAPE_CASES.values() and rel.endswith("test_auto_logs.py"):
                # The pattern's own shape cases live in this file by necessity.
                continue
            found.setdefault(hit, []).append(rel)

    # The control: this check is worthless if the files carry no such literal
    # at all, because then it passes over anything.
    assert found, (
        "no Steam64 literal was found in %r, so this test asserted nothing. "
        "Either the fixtures stopped using one or the file list is stale."
        % (list(_BRANCH_FILES),))

    stray = {k: v for k, v in found.items() if k not in _SYNTHETIC_IDS}
    assert not stray, (
        "account ids outside the synthetic set appear in this branch's files: "
        "%r. Use a filler id (7656119800000000N); a real one is republished on "
        "every clone of a public tree." % (stray,))


def _cited_test_names(source):
    """Every `test_...` this file's prose names in backticks."""
    return sorted(set(re.findall(r"`(test_[A-Za-z0-9_]+)`", source)))


def test_every_test_this_files_prose_cites_actually_exists():
    """A backticked test name in this file's prose is a claim about this
    file, and one such claim was false: the synthetic-ids note at the top
    cited a test that is not defined here or anywhere else. Someone checking
    what holds those ids synthetic would have found nothing and concluded the
    guard had been deleted -- the class this branch is closing elsewhere, a
    comment naming a mechanism the code beneath it does not carry
    (#432/#459).

    The names themselves are the anchor: each one is a module-level function
    in this file or it is not, which is a question with an answer. Names that
    this file deliberately discusses as ABSENT are written without backticks,
    which is why the mutation below has to assemble its citation at run time
    rather than spell one out in the source this check reads.
    """
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    defined = {name for name, obj in globals().items()
               if name.startswith("test_") and callable(obj)}

    # THE ANCHOR: the note this finding corrected cites exactly one test, and
    # it is the guard it claims to be about. Two citations there, or none,
    # and the correction has moved and this control has to be re-derived.
    note = source.split("# SYNTHETIC ACCOUNT IDS")[1].split("STEAM = ")[0]
    assert _cited_test_names(note) == ["test_this_branchs_files_name_no_real_account"], (
        "the synthetic-ids note cites %r; it is supposed to cite the one "
        "guard that holds those ids synthetic" % (_cited_test_names(note),))

    def check(text):
        cited = _cited_test_names(text)
        # Two halves. "every citation resolves" alone passes vacuously on a
        # file that cites nothing, which is also what a bad regex produces.
        return bool(cited) and all(c in defined for c in cited)

    # CONTROL: the live file passes, and it passes on a non-empty set.
    cited = _cited_test_names(source)
    assert cited, (
        "no `test_...` citation was found in this file, so this check "
        "asserted nothing -- the prose stopped naming tests, or the pattern "
        "stopped matching them")
    missing = [c for c in cited if c not in defined]
    assert not missing, (
        "this file's comments name %r, which no function here defines. A "
        "comment naming a test that does not exist reads as a guard that was "
        "removed (#432/#459)" % (missing,))

    # MUTATION: one more citation, of a test that does not exist -- which is
    # exactly the defect this closes. The name is ASSEMBLED, so the literal
    # never appears in the file this check reads and the mutation cannot
    # redden the control above.
    bogus = "test_" + "a_guard_nothing_defines"
    assert bogus not in source, "the mutation's name leaked into the file"
    mutant = source + "\n# see " + chr(96) + bogus + chr(96) + " for this\n"
    assert mutant != source
    assert not check(mutant), (
        "the check still passes with a citation of a test nothing defines, so "
        "it proves nothing about this file's prose")


# ── migration 373 does not depend on WHICH copy of 336 ran ───────────────────

def _sql_373():
    return (pathlib.Path(HERE).parent / "sql"
            / "373_bug_reports_auto_number.sql").read_text(encoding="utf-8")


def test_373_preconditions_on_the_objects_336_creates_not_on_its_bytes():
    """336 exists in two copies and they are NOT byte-identical.

    The hotfix copy is a superset: its post-check was rebuilt to OFFER rows to
    the constraint instead of reading the constraint's rendered text. The
    wrapper applies a migration once by FILE NAME, so whichever copy reaches a
    database first is the only one that ever runs there -- which means 373 has
    to be correct after EITHER, and has to say so by checking the objects 336
    leaves behind rather than assuming which file produced them.

    The three objects, by name: the `kind` column, its `bug_reports_kind_known`
    CHECK, and its `'report'` default. Both copies create all three; neither
    copy's identity is a premise of anything here.
    """
    sql = _sql_373()

    # THE COMMENTS COME OFF FIRST, and that is the whole difference between
    # this check and one that cannot fail. Every name below also appears in
    # 373's header prose, so searching the raw file would go on passing after
    # the guard stopped asking for the object -- the first cut of this test did
    # exactly that and a mutation proved it (#342). What is searched is the
    # EXECUTABLE text.
    executable = "\n".join(ln for ln in sql.splitlines()
                           if not ln.lstrip().startswith("--"))
    assert "RAISE EXCEPTION" in executable, (
        "the comment stripper removed the statements too; this check is "
        "searching nothing")

    for needle, why in (
        ("column_name = 'kind'", "the column 373's CHECK is written against"),
        ("bug_reports_kind_known",
         "the CHECK 336 installs -- without it `kind` is a free-text column "
         "and 'auto' means nothing"),
        ("column_default", "the 'report' default every pre-336 row relies on"),
    ):
        assert needle in executable, (
            "373's precondition does not name %s in any statement (%s), so it "
            "can apply on a database where 336 left a partial shape"
            % (needle, why))

    assert "byte-identical" not in sql, (
        "373 still claims the two copies of 336 are byte-identical. They are "
        "not -- the hotfix copy is 22,384 bytes against the lane's 19,445, "
        "diverging at line 217 where the post-check was rebuilt -- and a "
        "migration whose header states a guarantee the tree refutes is a "
        "finding (#302/#351)")


# ── round 3: the method change, one control per finding ─────────────────────


def test_the_reserve_section_is_not_separable_by_cancellation(logdir, verified,
                                                              monkeypatch, capsys):
    """R2-M1: MEASURE, STAMP AND WRITE RUN TO COMPLETION OR NOT AT ALL.

    The section used to be an inline block the handler awaited, with the lock
    released in the handler's own `finally`. Cancelling that await -- a client
    disconnect, a shutdown, the deadline -- ran the `finally` and released the
    lock while `asyncio.to_thread` went on writing, because nothing cancels a
    thread. A second upload could then measure a volume the first had not
    finished writing to, and the cancelled request could leave bytes behind
    with nobody left to account for them.

    Three things are asserted about a handler cancelled mid-section, and all
    three are what the shielded task buys:

    * NO CONCURRENT MEASURE -- the second seat's `_free_bytes` call does not
      happen until the first section's write has returned;
    * NO CONCURRENT WRITE -- the second `_write_blob` does not start inside
      the first;
    * NO UNMARKED ORPHAN -- at every instant between the first byte and the
      cleanup there is a marker naming the file, and afterwards neither
      survives.
    """
    import threading

    order = []
    writing = {"n": 0}
    started = threading.Event()
    release = threading.Event()
    real_write = auto_logs._write_blob

    def held_write(path, data):
        order.append("write-start")
        writing["n"] += 1
        assert writing["n"] == 1, (
            "two writes were inside the reserve section at once: %r" % (order,))
        if not started.is_set():
            started.set()
            release.wait(10.0)
        real_write(path, data)
        writing["n"] -= 1
        order.append("write-end")

    def watched_free(directory):
        order.append("measure")
        assert writing["n"] == 0, (
            "a second seat measured the volume while a write was still in "
            "flight inside the section: %r" % (order,))
        return 10 ** 12

    monkeypatch.setattr(auto_logs, "_write_blob", held_write)
    monkeypatch.setattr(auto_logs, "_free_bytes", watched_free)
    monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())

    seen_marked = {"n": 0}

    async def drive():
        first = asyncio.create_task(auto_logs.upload_auto_log(
            _request(_body(steam_id=STEAM)), _ok_db()))
        for _ in range(2000):
            if started.is_set():
                break
            await asyncio.sleep(0.005)
        assert started.is_set(), "the first upload never reached its write"

        # The blob's bytes are being written RIGHT NOW, and a marker already
        # names it. That is the invariant the whole design rests on.
        seen_marked["n"] = len(_markers(logdir))

        # CANCEL IT. The section keeps the lock and its worker thread; the
        # handler stops waiting.
        first.cancel()
        await asyncio.sleep(0.05)

        second = asyncio.create_task(auto_logs.upload_auto_log(
            _request(_body(steam_id=OTHER)), _ok_db()))
        await asyncio.sleep(0.05)
        release.set()
        return await asyncio.gather(first, second, return_exceptions=True)

    try:
        results = _run(drive())
    finally:
        release.set()
        auto_logs._write_blob = real_write

    assert seen_marked["n"] == 1, (
        "the blob was being written with no marker naming it -- an unmarked "
        "orphan is exactly what a cancellation here used to leave")
    assert isinstance(results[0], asyncio.CancelledError), results[0]
    assert not isinstance(results[1], BaseException), (
        "the second seat did not complete after the cancelled one released "
        "the volume: %r" % (results[1],))

    # The cancelled upload's own blob and marker are gone, and the second
    # seat's blob is the only thing left.
    assert len(_blobs(logdir)) == 1, (
        "the cancelled upload left its blob behind: %r" % (_blobs(logdir),))
    assert _markers(logdir) == [], (
        "a marker survived a completed pair of uploads: %r" % (_markers(logdir),))
    assert auto_logs._MARKERS_IN_FLIGHT == set(), (
        "a finished request still owns a marker, so the sweep would skip it "
        "for the life of the process: %r" % (auto_logs._MARKERS_IN_FLIGHT,))

    # THE ORDERING, stated: the second seat's measure comes after the first
    # write ended. Without the shield it comes between write-start and
    # write-end, which is the bound being broken.
    assert order.index("write-end") < order.index("measure", order.index("write-end")), (
        "the second seat measured before the cancelled section finished "
        "writing: %r" % (order,))

    # CONTROL, structural: the lock is released inside the SECTION and not by
    # the handler. A release in the handler is the mechanism this test deletes.
    section = _normalise(inspect.getsource(auto_logs._reserve_stamp_and_write))
    handler = _normalise(inspect.getsource(auto_logs.upload_auto_log))
    assert section.count("_BLOB_RESERVE_LOCK.release()") == 1, section
    assert "_BLOB_RESERVE_LOCK.release()" not in handler, (
        "the handler releases the reserve lock again; a cancelled await would "
        "hand the volume on while its worker is still writing")
    assert "asyncio.shield(section)" in handler, (
        "the handler awaits the section unshielded, so cancelling it cancels "
        "the section's own cleanup")


def test_an_unlink_failure_after_a_failed_insert_is_not_reported_as_discarded(
        logdir, verified, capsys, monkeypatch):
    """R2-L3: A CLEANUP RECORD MUST NOT BE ABLE TO BE WRONG ABOUT ITS FILE.

    `_discard_blob` used to swallow an unlink failure and the arm printed
    "blob discarded" regardless, so an INSERT failure plus an unlink failure
    left an unreferenced file on the volume and a line saying it had been
    cleaned up. Nobody goes looking for a file a log says is gone.

    Now the blob's survival is REPORTED, and the marker is kept so the sweep
    has it: the record names the file rather than claiming it away.
    """
    real_unlink = os.unlink

    def refusing_unlink(path, *a, **kw):
        if str(path).endswith(".log.gz"):
            raise OSError("device or resource busy")
        return real_unlink(path, *a, **kw)

    db = _ok_db()
    db.fail_on = "INSERT INTO bug_reports"
    # RESTORED BY HAND, never `monkeypatch.undo()`: undo() rolls back every
    # patch this test's fixtures made, including the `verified` fixture's
    # session stub, and the control below would then be refused 401 and prove
    # nothing (#594 -- a restore has to name what it is restoring).
    os.unlink = refusing_unlink
    try:
        with pytest.raises(HTTPException) as ei:
            _run(auto_logs.upload_auto_log(_request(), db))
    finally:
        os.unlink = real_unlink

    assert ei.value.status_code == 503
    survivors = _blobs(logdir)
    assert len(survivors) == 1, (
        "the unlink was refused, so the blob has to still be here for this "
        "control to say anything: %r" % (survivors,))
    out = capsys.readouterr().out
    assert "blob discarded" not in out, (
        "the arm reported a discard it did not perform. Printed: %r" % (out,))
    assert "SURVIVES as %s" % survivors[0] in out, (
        "the record does not say the blob survived, or does not name it. "
        "Printed: %r" % (out,))
    assert "%s=%s" % (auto_logs._ORPHAN_MARKER, survivors[0]) in out, (
        "the surviving blob is not named for the sweep. Printed: %r" % (out,))
    assert _markers(logdir) == [survivors[0] + auto_logs._ORPHAN_MARKER_SUFFIX], (
        "the marker was dropped while its blob survived, which is the one "
        "state that leaves a file nothing can collect: %r" % (_markers(logdir),))

    # CONTROL: the same failed INSERT with the unlink working reports a
    # discard and leaves neither artifact -- so the wording above is about the
    # unlink and not about the arm always saying "SURVIVES".
    for p in list(logdir.iterdir()):
        p.unlink()
    db = _ok_db()
    db.fail_on = "INSERT INTO bug_reports"
    with pytest.raises(HTTPException):
        _run(auto_logs.upload_auto_log(_request(), db))
    out = capsys.readouterr().out
    assert "blob discarded" in out and "SURVIVES" not in out, out
    assert _blobs(logdir) == [] and _markers(logdir) == [], (
        "%r / %r" % (_blobs(logdir), _markers(logdir)))


def test_a_marker_that_cannot_be_made_durable_refuses_the_upload(logdir, verified,
                                                                 monkeypatch, capsys):
    """THE STAMP IS NOT BEST-EFFORT.

    The marker is the only thing that offers a blob to the sweep, so a volume
    on which it cannot be made durable is a volume this route refuses rather
    than one it writes an uncollectable blob onto. The failure direction is the
    same as every other refusal here: 503, and the client tries after the next
    match (#276/#430).

    The negative case that matters is the one this asserts LAST: no blob, and
    no marker, left behind.
    """
    real_stamp = auto_logs._stamp_marker

    def exploding_stamp(blob_path):
        raise OSError("no space left on device")

    monkeypatch.setattr(auto_logs, "_stamp_marker", exploding_stamp)
    with pytest.raises(HTTPException) as ei:
        _run(auto_logs.upload_auto_log(_request(), _ok_db()))
    assert ei.value.status_code == 503, "an unstampable volume is retryable"
    assert _blobs(logdir) == [], (
        "a blob was written after the marker could not be stamped: %r"
        % (_blobs(logdir),))
    assert _markers(logdir) == [] and auto_logs._MARKERS_IN_FLIGHT == set()
    assert "blob write failed" in capsys.readouterr().out

    # CONTROL: the same upload with the stamp working lands, so the refusal is
    # about the stamp and not about the fixture. Restored BY NAME rather than
    # with `monkeypatch.undo()`, which would also roll back the `verified`
    # fixture's session stub and answer 401 here (#594).
    monkeypatch.setattr(auto_logs, "_stamp_marker", real_stamp)
    assert _run(auto_logs.upload_auto_log(_request(), _ok_db()))["log_persisted"] is True

    # AND THE STAMP IS A DURABILITY CALL, not a touch: it fsyncs the marker and
    # then its directory entry. A `write_bytes` here would leave the marker in
    # the page cache, which is exactly the state a host incident loses.
    src = _normalise(inspect.getsource(auto_logs._stamp_marker))
    assert ("os.fsync(fd)" in src
            and "_fsync_dir(pathlib.Path(blob_path).parent)" in src), (
        "the stamp no longer makes the marker durable: %r" % (src,))
    assert "_fsync_dir" in _normalise(inspect.getsource(auto_logs._stamp_marker))
    dirsrc = _normalise(inspect.getsource(auto_logs._fsync_dir))
    assert "except" not in dirsrc, (
        "the directory flush swallows its own failure, so a volume that cannot "
        "record the marker would be read as one that did")


def test_the_marker_exists_before_the_blobs_first_byte(logdir, verified, monkeypatch):
    """THE WRITE ORDER, ASSERTED RATHER THAN REASONED ABOUT.

    Everything this design claims rests on one ordering: the marker is durable
    before `open()` is called on the blob, and the blob is removed before its
    marker is. The first makes an unmarked orphan unreachable; the second makes
    a marker outlive every blob it names.
    """
    seen = []
    real_write = auto_logs._write_blob
    real_stamp = auto_logs._stamp_marker

    def watched_stamp(blob_path):
        seen.append(("stamp", blob_path.exists()))
        return real_stamp(blob_path)

    def watched_write(path, data):
        seen.append(("write", (auto_logs._marker_path(path)).exists()))
        return real_write(path, data)

    monkeypatch.setattr(auto_logs, "_stamp_marker", watched_stamp)
    monkeypatch.setattr(auto_logs, "_write_blob", watched_write)
    assert _run(auto_logs.upload_auto_log(_request(), _ok_db()))["log_persisted"] is True

    assert [s for s, _ in seen] == ["stamp", "write"], (
        "the blob was written before its marker was stamped: %r" % (seen,))
    assert seen[0][1] is False, "the blob already existed when the marker was stamped"
    assert seen[1][1] is True, (
        "the blob's first byte was written with no marker naming it, which is "
        "the unmarked-orphan window this design exists to close")


def test_the_indeterminate_arm_names_a_mutation_that_exists(logdir, verified):
    """R2-L8: THE COMMENT'S NAMED MUTATION HAS TO BE ONE THIS TREE CAN RUN.

    The arm's comment used to tell a reader to remove a `_discard_blob` call
    that is not there -- an instruction that cannot be followed, and whose
    nearest reading is to ADD a destructive cleanup to the one arm that must
    keep its blob. The mutation it names now is deleting the
    `_MARKERS_IN_FLIGHT.discard` beside it, which is code that exists.
    """
    src = inspect.getsource(auto_logs.upload_auto_log)
    head = src.split("INDETERMINATE -- see FAILURE DIRECTION")[1]
    comment = head.split('raise HTTPException(status_code=503')[0]
    named = "_MARKERS_IN_FLIGHT.discard"
    assert named in comment, (
        "the indeterminate arm's comment names no mutation of existing code")
    assert "_discard_blob" not in comment and "adding a discard" not in comment, (
        "the comment still names a discard on the arm whose whole job is to "
        "KEEP its blob")
    body = comment.split("#")[-1] + head.split(comment)[-1]
    assert src.count("_MARKERS_IN_FLIGHT.discard(path.name)") == 2, (
        "the named line occurs %d time(s) in the handler; the mutation below "
        "is anchored on the arm's own copy plus the finally"
        % src.count("_MARKERS_IN_FLIGHT.discard(path.name)"))

    # THE MUTATION, EXECUTED. Both copies of the line removed: the request
    # finishes still owning its marker, and the sweep skips it for ever.
    mutant = _exec_mutant(
        auto_logs.prune_orphan_blobs,
        "    live = set(_MARKERS_IN_FLIGHT)",
        "    live = set(_MARKERS_IN_FLIGHT) | {'held-by-a-finished-request'}")
    db = _ok_db()
    db.fail_commit = True
    with pytest.raises(HTTPException):
        _run(auto_logs.upload_auto_log(_request(), db))
    kept = _blobs(logdir)
    assert len(kept) == 1
    marker = logdir / (kept[0] + auto_logs._ORPHAN_MARKER_SUFFIX)
    old = time.time() - 10 ** 6
    os.utime(marker, (old, old))

    sweep_db = Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                         "SELECT log_filename FROM bug_reports": [[]]})
    auto_logs._MARKERS_IN_FLIGHT.add(kept[0])       # the state the deletion leaves
    try:
        out = _run(auto_logs.prune_orphan_blobs(sweep_db, min_age_s=1))
        assert out["unlinked"] == 0 and (logdir / kept[0]).exists(), (
            "a marker still owned by a finished request was collected, so the "
            "line the comment names is not load-bearing: %r" % (out,))
    finally:
        auto_logs._MARKERS_IN_FLIGHT.discard(kept[0])

    # CONTROL: with the line's effect in place -- the name dropped -- the same
    # blob is collected on the next pass.
    sweep_db = Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                         "SELECT log_filename FROM bug_reports": [[]]})
    out = _run(auto_logs.prune_orphan_blobs(sweep_db, min_age_s=1))
    assert out["unlinked"] == 1 and not (logdir / kept[0]).exists(), out
    assert mutant is not None


def test_the_cleanup_tests_prose_names_the_collector_that_exists():
    """R2-L9: the prose above a control is a claim, and it traces or it is a
    finding (#302/#351).

    Two docstrings in this file used to say that nothing could ever find a
    leaked blob. That was true of the tree they were written against; the
    marker and `prune_orphan_blobs` landed underneath them and the sentences
    stayed. So both are held to naming the mechanism that is actually there.
    """
    for name in ("test_a_failed_blob_write_leaves_no_file_behind",
                 "test_an_indeterminate_commit_keeps_the_blob"):
        doc = globals()[name].__doc__ or ""
        assert "prune_orphan_blobs" in doc or "marker" in doc or "sweep" in doc, (
            "%s explains itself without naming the collector that exists "
            "beneath it" % name)
        for stale in ("Nothing can ever find it",
                      "nothing collects this blob",
                      "unrecoverable by construction"):
            assert stale not in doc, (
                "%s still says %r, which the orphan sweep refutes" % (name, stale))


def test_373_preconditions_on_the_exact_336_default_not_a_substring():
    """R2-M3: THE GUARD ASKS FOR 336's DEFAULT, NOT FOR SOMETHING REPORTISH.

    The test used to be `column_default NOT LIKE '%report%'`, which any
    default merely CONTAINING that word satisfies. A drifted default of that
    shape passed the guard and every old-code bug-form INSERT during the
    migration-before-code window then landed a `kind` this file's CHECK was not
    written against.

    The executed half of this row is the rehearsal
    (`ai-collab/autolog/autolog-hotfix-r3-migration.log`), which applies the
    file to a database whose default is `'auto_report'::character varying` and
    watches it refuse by name, and to one carrying 336's exact default and
    watches it pass. This is the source half: the substring test is GONE and
    the equality names the value.
    """
    sql = _sql_373()
    executable = "\n".join(ln for ln in sql.splitlines()
                           if not ln.lstrip().startswith("--"))
    assert "RAISE EXCEPTION" in executable, (
        "the comment stripper removed the statements too; this check is "
        "searching nothing")
    assert "NOT LIKE '%report%'" not in executable, (
        "373 still accepts any rendered default containing 'report'")
    assert "v_default IS DISTINCT FROM c_336_default" in executable, (
        "373's default guard is no longer an equality against the value 336 "
        "installs")
    assert "c_336_default CONSTANT text := '''report''::character varying'" in executable, (
        "the expected default is not named in the file, so the guard cannot "
        "say WHICH value it wanted")

    # The refusal has to name both halves, or an operator reading it cannot
    # tell a drifted default from a missing one.
    refusal = [ln for ln in executable.splitlines()
               if "373: bug_reports.kind must carry exactly" in ln]
    assert len(refusal) == 1, refusal
    assert refusal[0].count("%") >= 2, (
        "the refusal prints fewer than two values; it has to say what it "
        "wanted and what it read: %r" % (refusal[0],))


# ── the marked span's deadline, and the two awaits it used not to cover ──────


def _handler_mutant(pairs):
    """`upload_auto_log`'s body with `pairs` applied, compiled WITHOUT its
    route decorator.

    The decorator is dropped on purpose: executing `@router.post("/auto")`
    would register a SECOND copy of the route on the module's real router, so
    a harness meant to measure the application would have changed it. Every
    anchor is still asserted to occur exactly once inside the function's own
    span before anything is read from the result (#432/#279).
    """
    src = textwrap.dedent(inspect.getsource(auto_logs.upload_auto_log))
    head, _, rest = src.partition("\n")
    assert head.startswith("@router.post("), (
        "upload_auto_log no longer starts with its route decorator, so this "
        "harness is stripping the wrong line: %r" % (head,))
    src = rest
    for anchor, replacement in pairs:
        assert src.count(anchor) == 1, (
            "the mutation anchor occurs %d time(s) in upload_auto_log, not "
            "once -- re-derive it before reading anything into the result "
            "(%r)" % (src.count(anchor), anchor))
        mutant = src.replace(anchor, replacement)
        assert mutant != src, "the mutation changed nothing"
        src = mutant
    namespace = dict(vars(auto_logs))
    exec(compile(src, "<mutant:upload_auto_log>", "exec"), namespace)
    return namespace["upload_auto_log"]


class _SlowInsert(Scripted):
    """A session whose INSERT does not answer inside the span's deadline."""

    def __init__(self, stall, **kw):
        super().__init__(**kw)
        self.stall = stall

    async def execute(self, statement, params=None):
        if "INSERT INTO bug_reports" in " ".join(str(statement).split()):
            await asyncio.sleep(self.stall)
        return await super().execute(statement, params)


class _SlowCommit(Scripted):
    """A session whose COMMIT does not answer inside the span's deadline.

    The state it models is the one the bound exists for: the bytes are on the
    volume, a marker names them, and the database has stopped answering. No
    `statement_timeout` applies to COMMIT, so nothing else in the stack ends
    this wait.
    """

    def __init__(self, stall, **kw):
        super().__init__(**kw)
        self.stall = stall
        self.name_held_during_rollback = None

    async def commit(self):
        await asyncio.sleep(self.stall)
        self.committed += 1

    async def rollback(self):
        self.name_held_during_rollback = set(auto_logs._MARKERS_IN_FLIGHT)
        self.rolled_back += 1


def _slow_insert_db(stall):
    return _SlowInsert(stall, script={
        COUNT_KEY: [[_bucket(0)]],
        PLAYER_KEY: [[{"id": PID}]],
        INSERT_KEY: [[{"bug_number": 4242}]],
    })


def _slow_commit_db(stall):
    return _SlowCommit(stall, script={
        COUNT_KEY: [[_bucket(0)]],
        PLAYER_KEY: [[{"id": PID}]],
        INSERT_KEY: [[{"bug_number": 4242}]],
    })


def test_the_marked_span_deadline_covers_the_insert_and_the_commit(
        logdir, verified, monkeypatch, capsys):
    """LENS-R3-1: T BOUNDS THE WHOLE SPAN, MEASURED RATHER THAN ASSERTED.

    The deadline used to be one `wait_for` around the shielded section, which
    ends when the write returns. The INSERT and the `commit()` after it ran
    under no ceiling, so `_ORPHAN_MIN_AGE_S`'s derivation -- "a stalled write
    cannot reach the gate" -- was a sentence about code that did not exist.
    What kept a live upload's marker out of the sweep for that half was the
    in-process registry, not the deadline.

    Both halves are MEASURED here: a database that will not answer the INSERT,
    and one that will not answer the COMMIT, each stalling well past T. The
    handler has to refuse inside T in both cases, and the two dispositions
    differ because what is knowable differs -- an uncommitted INSERT cannot
    become visible, so its blob goes; a cancelled COMMIT may have landed, so
    its blob and marker STAY for the sweep to resolve against the database.
    """
    # T HAS HEADROOM OVER THE BARRIERS THE SPAN NOW PAYS FOR. The stamp and
    # the blob write each fsync the file and then its directory entry, and on
    # this seat a single flush of a temporary volume is 60-200 ms; those are
    # charged to the same deadline (R3-M2), which is the point. A quarter of
    # a second left the barriers themselves expiring the span, so this case
    # would have measured the flush rather than the stalled statement it is
    # about. `test_the_durability_barrier_is_charged_to_the_marked_span` is
    # where the barrier's own cost is the subject.
    T = 1.5
    monkeypatch.setattr(auto_logs, "AUTO_LOG_MARKED_SPAN_DEADLINE_S", T)
    stall = 5.0

    # ── the INSERT half ──────────────────────────────────────────────────
    started = time.monotonic()
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.upload_auto_log(_request(), _slow_insert_db(stall)))
    took = time.monotonic() - started
    assert e.value.status_code == 503, e.value.status_code
    assert took < stall / 2.0, (
        "the handler waited %.2fs on an INSERT that never answered; the span's "
        "deadline is %.2fs, so the INSERT is outside the bound" % (took, T))
    assert _blobs(logdir) == [] and _markers(logdir) == [], (
        "an INSERT that never committed left its blob behind: blobs=%r "
        "markers=%r" % (_blobs(logdir), _markers(logdir)))
    out = capsys.readouterr().out
    assert "marked-span" in out and "blob discarded" in out, out

    # ── the COMMIT half ──────────────────────────────────────────────────
    db = _slow_commit_db(stall)
    started = time.monotonic()
    with pytest.raises(HTTPException) as e:
        _run(auto_logs.upload_auto_log(_request(), db))
    took = time.monotonic() - started
    assert e.value.status_code == 503, e.value.status_code
    assert took < stall / 2.0, (
        "the handler waited %.2fs on a commit that never answered; the span's "
        "deadline is %.2fs, so the commit is outside the bound" % (took, T))
    kept = _blobs(logdir)
    assert len(kept) == 1, (
        "the indeterminate commit discarded its blob: %r" % (kept,))
    assert _markers(logdir) == [kept[0] + auto_logs._ORPHAN_MARKER_SUFFIX], (
        "the blob a commit of unknown outcome kept is not marked, so nothing "
        "offers it to the sweep: %r" % (_markers(logdir),))
    assert auto_logs._MARKERS_IN_FLIGHT == set(), (
        "the finished request still owns its marker, so the sweep would skip "
        "it for the life of the process: %r" % (auto_logs._MARKERS_IN_FLIGHT,))
    out = capsys.readouterr().out
    assert "INDETERMINATE" in out and "marked-span" in out, out

    # THE NAME IS DROPPED BEFORE THE ROLLBACK, not after it. A rollback that
    # never returns -- on the database that has just stopped answering -- must
    # not hold the name, because a held name makes the marker permanent.
    assert db.name_held_during_rollback == set(), (
        "the request still owned its marker while its rollback was in flight: "
        "%r" % (db.name_held_during_rollback,))


def test_the_span_deadline_reds_when_an_await_inside_it_loses_the_budget(
        logdir, verified, monkeypatch):
    """THE MUTANTS AND THEIR INERT TWINS, for the bound above.

    Three sites, three mutants: the commit unwrapped, the INSERT unwrapped,
    and the budget itself stopped being the remaining span. Each has a twin at
    the SAME site that re-spells the line without changing what it means, and
    each twin must leave the case GREEN -- otherwise the control is reacting
    to the site being touched rather than to the bound going away (#342/#431).
    """
    # Same headroom as the case above, and for the same reason: the span now
    # pays for four fsyncs, so a T below them would be expired by the
    # barriers rather than by the site each mutant unwraps.
    T = 1.5
    monkeypatch.setattr(auto_logs, "AUTO_LOG_MARKED_SPAN_DEADLINE_S", T)
    stall = 5.0

    COMMIT_SITE = ("                left = _span_budget(span_deadline)\n"
                   "                await asyncio.wait_for(db.commit(), left)\n")
    INSERT_HEAD = ("                left = _span_budget(span_deadline)\n"
                   "                row = (await asyncio.wait_for(db.execute(\n")
    INSERT_TAIL = "                ), left)).mappings().first()\n"

    def _refuses_in_time(handler, db):
        """Whether `handler` refused, and inside the deadline."""
        started = time.monotonic()
        try:
            _run(handler(_request(), db))
            refused = False
        except HTTPException:
            refused = True
        return refused and (time.monotonic() - started) < stall / 2.0

    # MUTANT 1: the commit is awaited with no ceiling.
    assert not _refuses_in_time(
        _handler_mutant([(COMMIT_SITE, "                await db.commit()\n")]),
        _slow_commit_db(stall)), (
        "with the commit unwrapped the handler still refused inside the "
        "deadline, so this control says nothing about the bound")

    # INERT TWIN 1: the same call, the timeout passed by keyword.
    assert _refuses_in_time(
        _handler_mutant([(COMMIT_SITE,
                          "                left = _span_budget(span_deadline)\n"
                          "                await asyncio.wait_for(db.commit(), "
                          "timeout=left)\n")]),
        _slow_commit_db(stall)), (
        "the inert twin reds, so the control above is reacting to the site "
        "being edited rather than to the bound")

    # MUTANT 2: the INSERT is awaited with no ceiling.
    assert not _refuses_in_time(
        _handler_mutant([
            (INSERT_HEAD, "                row = (await (db.execute(\n"),
            (INSERT_TAIL, "                ))).mappings().first()\n")]),
        _slow_insert_db(stall)), (
        "with the INSERT unwrapped the handler still refused inside the "
        "deadline, so this control says nothing about the bound")

    # INERT TWIN 2: the same wrap, the budget bound to a differently-named
    # local.
    assert _refuses_in_time(
        _handler_mutant([
            (INSERT_HEAD,
             "                budget = _span_budget(span_deadline)\n"
             "                row = (await asyncio.wait_for(db.execute(\n"),
            (INSERT_TAIL, "                ), budget)).mappings().first()\n")]),
        _slow_insert_db(stall)), (
        "the inert twin reds, so the control above is reacting to the site "
        "being edited rather than to the bound")

    # MUTANT 3: the budget stops being what is LEFT of the span. The real
    # function is captured FIRST -- once it is monkeypatched the module
    # holds a function compiled from a string, and `inspect.getsource`
    # cannot read one, so the twin below would error instead of running.
    real_budget = auto_logs._span_budget
    budget_site = "    left = deadline - time.monotonic()\n"
    monkeypatch.setattr(auto_logs, "_span_budget", _exec_mutant(
        real_budget, budget_site, "    left = 10 ** 6\n"))
    assert not _refuses_in_time(auto_logs.upload_auto_log,
                                _slow_commit_db(stall)), (
        "with the budget no longer derived from the deadline the handler "
        "still refused in time")

    # INERT TWIN 3: the same arithmetic, spelled with an explicit float.
    monkeypatch.setattr(auto_logs, "_span_budget", _exec_mutant(
        real_budget, budget_site,
        "    left = float(deadline) - time.monotonic()\n"))
    assert _refuses_in_time(auto_logs.upload_auto_log,
                            _slow_commit_db(stall)), (
        "the inert twin reds, so the control above is reacting to the site "
        "being edited rather than to the budget")


def test_cancelling_the_section_task_cannot_leave_a_blob_with_no_marker(
        logdir, verified, monkeypatch):
    """LENS-R3-2: THE SECTION'S OWN CANCELLATION, NOT THE HANDLER'S.

    The handler being cancelled is covered above: it is shielded, so the
    section runs on. The case the failure table did not have a row for is the
    SECTION TASK itself being cancelled -- container SIGTERM during a rebuild,
    or `asyncio.run`'s task cancellation at loop close. `asyncio.to_thread`
    does not stop the worker, so the section's `finally` could run its cleanup
    while the thread had not yet reached `open()`: the blob unlink answered
    True on a file that did not exist, the marker was removed, and the thread
    then created the blob. That is a blob with no marker -- invisible to the
    orphan sweep, whose population is the marker set, and invisible to the
    row-walking prune, so permanent on a volume shared with player-filed
    attachments.

    The construction that closes it is the blob's own lock plus a `discarded`
    flag checked inside it, so the two orders that remain are both safe. The
    window is driven deterministically here by holding the worker before it
    takes the lock.
    """
    import threading

    name_of = {}
    entered, proceed, finished = (threading.Event(), threading.Event(),
                                  threading.Event())
    real_guarded = auto_logs._guarded_write

    def make_delayed(target):
        def delayed(own, data):
            name_of["blob"] = own.path.name
            entered.set()
            proceed.wait(10.0)
            try:
                target(own, data)
            finally:
                finished.set()
        return delayed

    def drive(guarded):
        monkeypatch.setattr(auto_logs, "_guarded_write", make_delayed(guarded))
        monkeypatch.setattr(auto_logs, "_free_bytes", lambda d: 10 ** 12)
        monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
        for ev in (entered, proceed, finished):
            ev.clear()

        async def run():
            own = auto_logs._MarkedBlob(
                pathlib.Path(str(logdir)) / "bbbbbbbb-0000-4000-8000-0000000000dd.log.gz")
            task = asyncio.ensure_future(
                auto_logs._reserve_stamp_and_write(
                    own, b"payload", STEAM,
                    # The section spends the handler's one deadline at every
                    # hop inside it, so driving it directly has to supply one.
                    time.monotonic() + auto_logs.AUTO_LOG_MARKED_SPAN_DEADLINE_S))
            for _ in range(2000):
                if entered.is_set():
                    break
                await asyncio.sleep(0.005)
            assert entered.is_set(), "the section never reached its write"

            # CANCEL THE SECTION ITSELF. The worker is still queued in front
            # of the blob's lock, which is the window this test exists for.
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            proceed.set()
            for _ in range(2000):
                if finished.is_set():
                    break
                await asyncio.sleep(0.005)
            assert finished.is_set(), "the worker thread never finished"

        try:
            _run(run())
        finally:
            proceed.set()
            finished.wait(10.0)
        return sorted(_blobs(logdir)), _markers(logdir)

    # LIVE: the cleanup wins the lock, the worker creates nothing.
    blobs, markers = drive(real_guarded)
    assert blobs == [] and markers == [], (
        "a cancelled section left a file behind: blobs=%r markers=%r"
        % (blobs, markers))
    assert auto_logs._MARKERS_IN_FLIGHT == set(), auto_logs._MARKERS_IN_FLIGHT

    # MUTANT: the worker stops asking whether the blob has been discarded --
    # exactly the tree before this fix. It writes after the cleanup, and what
    # is left is an unreferenced blob with no marker naming it.
    guard_site = "        if own.discarded:\n            return\n"
    blobs, markers = drive(_exec_mutant(
        real_guarded, guard_site, "        if False:\n            return\n"))
    assert blobs and markers == [], (
        "the mutant did not produce the unmarked orphan this case is about, "
        "so the live assertion above proves nothing: blobs=%r markers=%r"
        % (blobs, markers))
    for stale in blobs:
        (pathlib.Path(str(logdir)) / stale).unlink()

    # INERT TWIN at the same site: the same condition, spelled differently.
    blobs, markers = drive(_exec_mutant(
        real_guarded, guard_site,
        "        if own.discarded is True:\n            return\n"))
    assert blobs == [] and markers == [], (
        "the inert twin left a file behind, so the mutant above is reacting "
        "to the site being edited rather than to the guard: blobs=%r "
        "markers=%r" % (blobs, markers))


def test_a_marker_with_no_blob_is_never_reported_as_a_removal(logdir,
                                                              monkeypatch):
    """LENS-R3-3: AN ABSENT BLOB IS NOT A REMOVAL, AND THE LINE SAYS SO.

    `_unlink_if_present` answers True for a file that was never there, by
    design -- the caller asked for it to be gone and it is. The sweep used to
    read that answer as a removal: it incremented `unlinked` and printed
    "removed" over a pass that had not reclaimed a byte, so the number an
    operator reads as the drain rate was the number of candidates seen (#304).
    `_unlink_existing`'s three-way answer is what separates them.

    WHAT ROUND 6 PUT BACK. LENS-3 also spent the pass's budget on removals
    alone, which kept a marker-only cohort from consuming the slots a real
    orphan needed. Round 5 replaced that with a budget every arm spent; round
    6 restores it (`test_the_removal_budget_is_spent_by_removals_only`) and
    bounds the pass's WORK with a separate scan bound. This case holds
    LENS-3's other half, the counting -- and with the budget back to removals
    only it can hold it at the budget the real orphans need and no more.

    Here: eight marker-only leftovers, OLDER than four real orphans, and a
    budget of FOUR. The leftovers are reached first; if clearing one spent a
    slot, or counted as a removal, the four real orphans behind them would be
    deferred. So what is under test is which term each candidate lands in,
    and that landing in `marker_only` costs nothing.
    """
    blanks = ["aaaaaaaa-0000-4000-8000-%012d.log.gz" % i for i in range(8)]
    reals = ["bbbbbbbb-0000-4000-8000-%012d.log.gz" % i for i in range(4)]

    def _plant():
        for i, nm in enumerate(blanks):
            _mark(logdir, nm, age_s=90_000 - i)        # oldest: no blob at all
        for i, nm in enumerate(reals):
            (logdir / nm).write_bytes(b"x" * 16)
            _mark(logdir, nm, age_s=50_000 - i)

    def _db():
        return Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                         "SELECT log_filename FROM bug_reports": [[]]})

    _plant()
    out = _run(auto_logs.prune_orphan_blobs(_db(), min_age_s=3600, limit=4))
    assert out["unlinked"] == 4 and out["marker_only"] == 8, (
        "the marker-only leftovers were counted as removals: %r" % (out,))
    assert out["deferred"] == 0, (
        "a pass with budget for exactly its four real orphans deferred some "
        "of them, so clearing a leftover spent a slot: %r" % (out,))
    assert sorted(_blobs(logdir)) == [], (
        "a real orphan survived a pass whose budget covered every removal: %r"
        % (_blobs(logdir),))
    assert _marker_names(logdir) == [], _marker_names(logdir)

    # MUTANT: the collapsed answer restored -- an absent file reads as a
    # removal again, so the line reports twelve removals over four reclaimed
    # blobs. The site is the resolver's, which is where the two unlinks live
    # now that the pass's filesystem work runs off the event loop.
    site = "        state, marker_gone = _delete_blob_then_marker(base / name)\n"
    # BOTH copies are compiled from the LIVE resolver, read once. Building the
    # twin from `auto_logs._resolve_marker_candidates` after the mutant is
    # installed reads the mutant, which has no source on disk at all.
    live_resolver = auto_logs._resolve_marker_candidates
    _plant()
    mutant = _exec_mutant(
        live_resolver, site,
        '        state, marker_gone = ("removed" if _unlink_if_present(base / name)\n'
        '                               else "failed"), _unlink_if_present(\n'
        '                                   base / (name + _ORPHAN_MARKER_SUFFIX))\n')
    monkeypatch.setattr(auto_logs, "_resolve_marker_candidates", mutant)
    out = _run(auto_logs.prune_orphan_blobs(_db(), min_age_s=3600, limit=4))
    # The leftovers are oldest, so under the collapsed answer the first four
    # of them read as removals, spend the whole budget, and the four real
    # orphans are deferred behind them.
    assert out["marker_only"] == 0 and out["deferred"] == 8 and _blobs(logdir), (
        "the mutant still separated the two answers, so the live assertion "
        "above proves nothing: %r" % (out,))

    # INERT TWIN at the same site: the same call, the path built explicitly.
    _plant()
    twin = _exec_mutant(
        live_resolver, site,
        "        state, marker_gone = _delete_blob_then_marker(\n"
        "            pathlib.Path(base) / name)\n")
    monkeypatch.setattr(auto_logs, "_resolve_marker_candidates", twin)
    out = _run(auto_logs.prune_orphan_blobs(_db(), min_age_s=3600, limit=4))
    assert out["unlinked"] == 4 and out["marker_only"] == 8 and _blobs(logdir) == [], (
        "the inert twin changed the outcome, so the mutant above is reacting "
        "to the site being edited rather than to the collapsed answer: %r"
        % (out,))


def _due_lock_findings(sql):
    """What is WRONG with a due-selection statement, as a list.

    The assertions live here rather than in the case so the mutants below can
    be measured by the same sentence the live code is measured by. A control
    whose red is produced by a differently worded check is a control that
    proves the wording (#342/#441).
    """
    bad = []
    if "FOR NO KEY UPDATE" not in sql:
        bad.append("no row lock, so two overlapping passes read the same rows "
                   "and the second reads the first's pending unlink as absent")
    if "SKIP LOCKED" not in sql:
        bad.append("waits on a locked row instead of taking the next")
    # `FOR UPDATE` is the stronger mode and a different sentence: it conflicts
    # with the `FOR KEY SHARE` that every foreign-key insert referencing a
    # bug_reports row takes, so it enrols writers with no part in retention.
    # Spelled as a word test, because "FOR NO KEY UPDATE" contains neither
    # " FOR UPDATE" nor "FOR UPDATE SKIP".
    if " FOR UPDATE" in sql or "FOR UPDATE SKIP" in sql:
        bad.append("takes FOR UPDATE, which conflicts with FOR KEY SHARE")
    return bad


#: M1(a). The lock clause deleted at its own site -- the state round 5 left,
#: where two passes select the same rows.
_NO_ROW_LOCK = (
    '                 LIMIT :lim\n'
    '                   FOR NO KEY UPDATE SKIP LOCKED"""),\n',
    '                 LIMIT :lim"""),\n')
#: THE INERT TWIN at the same site: the same clause, wrapped differently. SQL
#: does not care where the line breaks fall, so a control that reds here is
#: reacting to the site being edited rather than to the lock going.
_ROW_LOCK_REWRAPPED = (
    '                 LIMIT :lim\n'
    '                   FOR NO KEY UPDATE SKIP LOCKED"""),\n',
    '                 LIMIT :lim\n'
    '                   FOR NO KEY UPDATE\n'
    '                   SKIP LOCKED"""),\n')


def _due_sql_of(fn, logdir):
    """Run `fn` over one due row and hand back the statement it selected with."""
    (logdir / "a.log.gz").write_bytes(b"x")
    db = Scripted({DUE_KEY: [[{"id": str(R1), "log_filename": "a.log.gz"}]],
                   "DELETE FROM bug_reports": [[{"id": str(R1)}]]})
    _run(fn(db))
    return db.sql_for(DUE_KEY)[0]


def test_the_due_selection_takes_the_row_lock_that_conflicts_with_its_own_delete(
        logdir):
    """M1(a): TWO RETENTION PASSES MUST NOT HOLD THE SAME ROW.

    The pass selects its due rows, hands them to a worker thread that unlinks
    up to two hundred blobs, and only then DELETEs. Between the SELECT and
    the DELETE a second pass -- the hourly loop and an upload's opportunistic
    call, in this process or in another worker -- could select the same rows,
    see the first pass's unlink as `absent`, and commit the DELETE over a
    removal that is still only in the directory cache.

    `FOR NO KEY UPDATE SKIP LOCKED` closes that from the other side: the
    second pass takes the rows the first one did not.

    THE MODE IS THE WEAKEST ONE THAT STILL CONFLICTS WITH THIS PASS'S OWN
    LATER WRITE (#202). `FOR UPDATE` conflicts with the `FOR KEY SHARE` that
    every foreign-key insert referencing a `bug_reports` row takes, which
    enrols writers that have nothing to do with retention in this sweep's
    lock graph; `FOR NO KEY UPDATE` self-conflicts, so two passes still
    serialize, and is KEY-SHARE compatible. `SKIP LOCKED` rather than a wait,
    because the rows are interchangeable work and a pass behind a slow volume
    should drain the rest rather than queue.

    It gates on rows that EXIST by construction (#203/#207): they are the
    SELECT's own answer, so there is no lock-nothing window and no advisory
    key standing in for a row that may not be there.
    """
    (logdir / "a.log.gz").write_bytes(b"x")
    db = Scripted({DUE_KEY: [[{"id": str(R1), "log_filename": "a.log.gz"}]],
                   "DELETE FROM bug_reports": [[{"id": str(R1)}]]})
    _run(auto_logs.prune_auto_logs(db))

    due_sql = db.sql_for(DUE_KEY)[0]
    assert _due_lock_findings(due_sql) == [], (
        "the due selection %s: %s" % (_due_lock_findings(due_sql), due_sql))
    # AND THE SECOND STATEMENT RE-CHECKS THE PREDICATE THE FIRST CHOSE ON
    # (#208), so the lock is not carrying a decision the DELETE should be
    # making for itself.
    assert "kind = 'auto'" in db.sql_for("DELETE FROM bug_reports")[0]

    # -- MUTANT (a): the lock clause deleted -------------------------------
    auto_logs._PRUNE_HELD.clear()
    mutant = _exec_mutant(auto_logs.prune_auto_logs, *_NO_ROW_LOCK)
    found = _due_lock_findings(_due_sql_of(mutant, logdir))
    assert found, (
        "the due selection with its lock clause removed produced no finding, "
        "so this case cannot tell a locked selection from an unlocked one")

    # -- THE INERT TWIN at the same site -----------------------------------
    auto_logs._PRUNE_HELD.clear()
    twin = _exec_mutant(auto_logs.prune_auto_logs, *_ROW_LOCK_REWRAPPED)
    assert _due_lock_findings(_due_sql_of(twin, logdir)) == [], (
        "the inert twin reds, so the mutation above is reacting to the site "
        "being edited rather than to the lock clause")
    auto_logs._PRUNE_HELD.clear()


def test_an_absent_blob_is_collectable_only_once_the_pass_barrier_has_succeeded(
        logdir, capsys):
    """M1(b): `absent` IS USUALLY ANOTHER PASS'S UNLINK, NOT A FACT.

    A row whose blob is observed absent used to be collectable with no
    barrier at all, on the reading that "nothing of ours is on the volume".
    That reading is wrong about WHOSE removal it is. The state is produced by
    a pass that unlinked and did not reach its commit, and that pass's entry
    change may still be only in the directory cache -- so a second pass that
    deletes the row over it leaves a volume which, after a host stop, carries
    an unmarked blob whose only reference is durably gone. `prune_auto_logs`
    selects ROWS and the orphan sweep walks MARKERS, so nothing collects it.

    The flush this pass issues is what makes the earlier unlink durable: a
    directory flush promises every entry change issued in that directory, not
    only the ones this process issued. So `absent` takes the `removed` arm's
    barrier, and when the barrier refuses the row is retained and held in
    exactly the same way.
    """
    # NO blob on the volume for either row, so `_unlink_existing` answers
    # `absent` for both -- the state a previous pass leaves behind.
    db = Scripted({DUE_KEY: [[{"id": str(R1), "log_filename": "gone-a.log.gz"},
                              {"id": str(R2), "log_filename": "gone-b.log.gz"}]],
                   "DELETE FROM bug_reports": [[]]})

    def _refuse(directory):
        raise OSError("the directory would not flush")

    capsys.readouterr()
    real_fsync_dir = auto_logs._fsync_dir
    auto_logs._fsync_dir = _refuse
    try:
        out = _run(auto_logs.prune_auto_logs(db))
    finally:
        auto_logs._fsync_dir = real_fsync_dir
    printed = capsys.readouterr().out

    assert out["undurable"] == 2 and out["rows"] == 0, (
        "the rows whose blobs were observed absent were collected over a "
        "flush that refused: %r" % (out,))
    assert db.sql_for("DELETE FROM bug_reports") == [], (
        "a DELETE ran although no removal on this volume can be proved")
    assert out["held"] == 2, (
        "an `absent` row kept over an unprovable removal was not held out of "
        "the next selection, so the same pass repeats immediately: %r" % (out,))
    assert "found already gone" in printed, printed

    # CONTROL: the same two rows and the same absent blobs, with a directory
    # that flushes. Without it the refusal above is equally well explained by
    # a pass that never collects an `absent` row at all (#391).
    auto_logs._PRUNE_HELD.clear()
    db2 = Scripted({DUE_KEY: [[{"id": str(R1), "log_filename": "gone-a.log.gz"},
                               {"id": str(R2), "log_filename": "gone-b.log.gz"}]],
                    "DELETE FROM bug_reports": [[{"id": str(R1)},
                                                 {"id": str(R2)}]]})
    ok = _run(auto_logs.prune_auto_logs(db2))
    assert ok["undurable"] == 0 and ok["rows"] == 2, (
        "the control pass did not collect its absent rows, so the refusal "
        "above is not about the flush: %r" % (ok,))

    # -- MUTANT (b): `absent` collected without the barrier -----------------
    #
    # Round 5's reading, put back at its own site: the row becomes collectable
    # because nothing of ours is on the volume, without asking whether the
    # removal that made that true was ever promised.
    auto_logs._PRUNE_HELD.clear()
    mutant = _exec_mutant(
        auto_logs.prune_auto_logs,
        "            if barrier is None:\n",
        "            if barrier is None or state == \"absent\":\n")
    assert _absent_rows_deleted(mutant) == 2, (
        "with `absent` collected regardless of the barrier the pass still "
        "kept its rows, so this case is not measuring the barrier")

    # -- THE INERT TWIN at the same site -----------------------------------
    auto_logs._PRUNE_HELD.clear()
    twin = _exec_mutant(
        auto_logs.prune_auto_logs,
        "            if barrier is None:\n",
        "            if not (barrier is not None):\n")
    assert _absent_rows_deleted(twin) == 0, (
        "the inert twin reds, so the mutation above is reacting to the "
        "predicate being rewritten rather than to the barrier being dropped")
    auto_logs._PRUNE_HELD.clear()


def _absent_rows_deleted(fn):
    """`fn` over two absent blobs and a directory that REFUSES to flush; the
    number of rows it deleted anyway."""
    def _refuse(directory):
        raise OSError("the directory would not flush")

    db = Scripted({DUE_KEY: [[{"id": str(R1), "log_filename": "gone-a.log.gz"},
                              {"id": str(R2), "log_filename": "gone-b.log.gz"}]],
                   "DELETE FROM bug_reports": [[{"id": str(R1)},
                                                {"id": str(R2)}]]})
    real = auto_logs._fsync_dir
    auto_logs._fsync_dir = _refuse
    try:
        return _run(fn(db))["rows"]
    finally:
        auto_logs._fsync_dir = real


def test_the_pass_takes_its_barrier_for_an_absent_observation_as_well(logdir):
    """The half of M1(b) one level down, asserted where the charge is made.

    `_unlink_due_blobs` takes the barrier when the pass removed anything OR
    saw anything already gone. A pass that only observed absences used to
    issue no flush at all, so `barrier is None` meant "nothing was attempted"
    on one path and "everything was promised" on another -- one value for two
    facts, which is the shape #430 is about.
    """
    flushed = []
    real = auto_logs._fsync_dir
    auto_logs._fsync_dir = lambda d: flushed.append(str(d))
    try:
        outcomes, barrier = auto_logs._unlink_due_blobs(
            logdir, [(str(R1), "not-there.log.gz")])
    finally:
        auto_logs._fsync_dir = real
    assert [s for _i, s, _d in outcomes] == ["absent"], outcomes
    assert flushed == [str(logdir)], (
        "a pass that observed an absence issued no flush, so an earlier "
        "pass's unlink is still unpromised when this one drops the row: %r"
        % (flushed,))
    assert barrier is None

    # AND THE ROW THAT NAMES NOTHING IS STILL FREE. `no-blob` is the one arm
    # with no removal behind it anywhere, so charging it a barrier would be a
    # directory flush per empty pass.
    flushed.clear()
    auto_logs._fsync_dir = lambda d: flushed.append(str(d))
    try:
        outcomes, barrier = auto_logs._unlink_due_blobs(
            logdir, [(str(R1), None)])
    finally:
        auto_logs._fsync_dir = real
    assert [s for _i, s, _d in outcomes] == ["no-blob"], outcomes
    assert flushed == [], (
        "a row naming no blob charged the pass a directory flush: %r"
        % (flushed,))


def test_the_removal_budget_is_spent_by_removals_only(logdir):
    """B0f / LENS-3, RESTORED. `_ORPHAN_BATCH` buys REMOVALS and nothing else.

    Round 5 spent a slot of this budget on every arm that touches the volume,
    on the reasoning that every arm costs a filesystem call. The reasoning is
    right about the cost and wrong about the instrument: with a clear over a
    committed row spending a slot, a cohort of referenced markers consumes the
    pass while an unreferenced blob behind them waits, and the number an
    operator reads as the drain rate stops bounding the drain. The pass's COST
    is bounded by `_ORPHAN_SCAN_BOUND` instead, which is the question that was
    actually being asked.

    The population here is exactly the shape that tells the two apart: as many
    referenced markers as the whole budget, and one unreferenced blob behind
    them. Removals-only takes the orphan in this pass; every-arm defers it.
    """
    referenced = ["aaaaaaaa-0000-4000-8000-%012d.log.gz" % i for i in range(2)]
    orphan = "bbbbbbbb-0000-4000-8000-0000000000ff.log.gz"
    for i, nm in enumerate(referenced):
        (logdir / nm).write_bytes(b"x" * 8)
        _mark(logdir, nm, age_s=90_000 - i)
    (logdir / orphan).write_bytes(b"x" * 8)
    _mark(logdir, orphan, age_s=50_000)

    db = Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                   "SELECT log_filename FROM bug_reports":
                       [[{"log_filename": n} for n in referenced]]})
    out = _run(auto_logs.prune_orphan_blobs(db, min_age_s=3600, limit=2))

    assert out["cleared"] == 2, out
    assert out["unlinked"] == 1 and out["deferred"] == 0, (
        "two referenced-marker clears spent a removal budget of two, so the "
        "orphan behind them waited for a later tick: %r" % (out,))
    assert not (logdir / orphan).exists(), (
        "the unreferenced blob is still on the volume: %r" % (out,))
    assert all((logdir / n).exists() for n in referenced), (
        "a blob a bug_reports row names was removed")
    # AND BOTH SUMS CLOSE, each over its own population.
    assert out["cleared"] + out["uncleared"] == 2, out
    assert (out["unlinked"] + out["marker_only"] + out["unremovable"]
            + out["deferred"]) == out["orphans"], out


def test_the_sweeps_work_is_bounded_by_the_scan_bound_and_not_by_the_backlog(
        logdir, monkeypatch):
    """R5-LOW at `auto_logs.py:2578`: the WHOLE pass is bounded, not only its
    resolver.

    Before round 6 the listing, the `stat` per marker, the sort and the
    500-name reference queries all ran over the ENTIRE marker population
    before the removal budget was applied to the tail of it. So a backlog of
    any size cost that many `stat` calls and that many rows of database work
    on every tick, on the api's single worker, however little the pass was
    allowed to remove.

    Here the population is well above the bound, and what is measured is the
    three things that used to grow with it: names examined, `stat` calls
    issued, and names offered to the database. The `stat` calls are counted
    at the directory entries `scandir` hands back, which is where the window
    reads each candidate's age.

    Its mutant and inert twin are in
    `test_every_round_six_sweep_and_lock_bound_reds_when_it_is_removed`.
    """
    monkeypatch.setattr(auto_logs, "_ORPHAN_SCAN_BOUND", 8)
    monkeypatch.setattr(auto_logs, "_ORPHAN_CURSOR", [""])
    out, stats, db = _scan_pass(logdir)

    assert out["markers"] == 40, out
    assert out["examined"] == 8, (
        "the pass examined %d of 40 markers with a scan bound of 8, so the "
        "listing is still the population: %r" % (out["examined"], out))
    assert stats == 8, (
        "the pass issued %d stat call(s) over 40 markers with a scan bound of "
        "8, so the age question is still asked of the population" % stats)
    assert out["candidates"] == 8, out
    offered = db.params_for("SELECT log_filename FROM bug_reports")
    assert len(offered) == 1 and len(offered[0]["names"]) == 8, (
        "the reference lookup was asked about %r name(s), not the window's 8"
        % ([len(p["names"]) for p in offered],))
    assert len(_marker_names(logdir)) == 32, (
        "the pass resolved more than its window: %r" % (out,))


def test_a_stuck_cohort_is_held_so_the_orphans_behind_it_are_reached(logdir,
                                                                     monkeypatch):
    """THE STUCK HEAD, ON THE SWEEP THIS TIME -- AND RE-SCOPED IN ROUND 6.

    A cohort whose unlink raises is NOT consumed by being worked: it is on the
    volume again on the next tick. What it can therefore occupy has changed
    with the budget. When every arm spent the removal budget, a stuck cohort
    took the whole of it and a real orphan behind it was never reached. With
    the budget back to removals only, a stuck candidate costs no slot -- so
    what it can still occupy is a WINDOW slot, and that is what the hold is
    measured against here.

    THE CURSOR IS HELD STILL FOR THIS CASE, deliberately. It is the other
    progress mechanism and it would reach the orphans on its own, which would
    make the mutant below green for a reason that has nothing to do with the
    hold. Pinned at the start of every pass, the window is the same window
    each time and the only thing that can move it is the park.

    Four stuck markers, two real orphans behind them, a window of two. Pass
    one meets two stuck candidates and parks them; pass two meets the other
    two and parks them; pass three reaches the orphans.
    """
    monkeypatch.setattr(auto_logs, "_ORPHAN_SCAN_BOUND", 2)
    stuck = ["dddddddd-0000-4000-8000-%012d.log.gz" % i for i in range(4)]
    reals = ["eeeeeeee-0000-4000-8000-%012d.log.gz" % i for i in range(2)]
    for i, nm in enumerate(stuck):
        (logdir / nm).write_bytes(b"x" * 16)
        _mark(logdir, nm, age_s=90_000 - i)
    for i, nm in enumerate(reals):
        (logdir / nm).write_bytes(b"x" * 16)
        _mark(logdir, nm, age_s=50_000 - i)

    real_unlink = os.unlink

    def _boom(path, *a, **kw):
        if os.path.basename(str(path)).split(".orphan")[0] in stuck:
            raise PermissionError("read-only file system")
        return real_unlink(path, *a, **kw)

    def _db():
        return Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                         "SELECT log_filename FROM bug_reports": [[]]})

    def _pinned():
        """One pass with the cursor put back where it started."""
        auto_logs._ORPHAN_CURSOR[0] = ""
        return _run(auto_logs.prune_orphan_blobs(_db(), min_age_s=3600,
                                                 limit=2))

    proxy = _OsProxy(unlink=_boom)
    saved = auto_logs.os
    saved_cursor = auto_logs._ORPHAN_CURSOR[0]
    auto_logs.os = proxy
    try:
        passes = [_pinned() for _ in range(3)]
    finally:
        auto_logs.os = saved
        auto_logs._ORPHAN_CURSOR[0] = saved_cursor

    assert passes[0]["unremovable"] == 2 and passes[0]["examined"] == 2, passes[0]
    assert passes[1]["held"] == 2 and passes[1]["unremovable"] == 2, (
        "the first pass's stuck pair was offered to the second pass again: %r"
        % (passes[1],))
    assert passes[2]["held"] == 4 and passes[2]["unlinked"] == 2, (
        "the real orphans were still standing behind the stuck cohort on the "
        "third pass: %r" % (passes[2],))
    assert sorted(_blobs(logdir)) == sorted(stuck), (
        "a real orphan survived, or a stuck blob was reported removed: %r"
        % (_blobs(logdir),))

    # MUTANT: the hold neutered. The stuck pair is offered again on every
    # pass, takes the budget every time, and the orphans behind it are never
    # reached however many ticks run. The corpus is re-planted first, because
    # the live run above took the real orphans off the volume.
    for i, nm in enumerate(reals):
        (logdir / nm).write_bytes(b"x" * 16)
        _mark(logdir, nm, age_s=50_000 - i)
    for name in list(auto_logs._ORPHAN_HELD):
        auto_logs._ORPHAN_HELD.pop(name, None)
    live_hold = auto_logs._hold_marker
    try:
        auto_logs._hold_marker = lambda name, clock: None
        auto_logs.os = proxy
        blind = [_pinned() for _ in range(3)]
    finally:
        auto_logs.os = saved
        auto_logs._hold_marker = live_hold
        auto_logs._ORPHAN_CURSOR[0] = saved_cursor
    assert all(p["unlinked"] == 0 for p in blind), (
        "the mutant still reached the orphans, so the live assertion above "
        "proves nothing: %r" % (blind,))
    assert sorted(_blobs(logdir)) == sorted(stuck + reals), (
        "the mutant reclaimed a blob: %r" % (_blobs(logdir),))


def test_the_cursor_reaches_an_orphan_behind_a_backlog_larger_than_the_window(
        logdir, monkeypatch):
    """THE OTHER HALF OF L2, and the hold is held still for it.

    A scan bound with no cursor is the attachment heap's cap with a new
    number: a pass that always takes the FIRST `_ORPHAN_SCAN_BOUND` names
    re-walks the same window for ever, so a cohort that will not resolve hides
    everything behind it permanently. The cursor makes the window advance
    whatever the window contained, so the wait is arithmetic --
    ceil(N / bound) + 1 passes -- rather than a hope about which names sort
    first.

    THE HOLD IS NEUTRALISED HERE (`_ORPHAN_HOLD_S = 0`, so every park has
    expired by the time the next pass reads it) for the reason the case above
    pins the cursor: two mechanisms answer nearby questions and a case that
    leaves both live measures neither.

    A backlog of six markers that will not unlink, a window of two, and one
    real orphan sorting LAST. Four passes at most: three to walk past the
    backlog and one to take the orphan.
    """
    monkeypatch.setattr(auto_logs, "_ORPHAN_SCAN_BOUND", 2)
    monkeypatch.setattr(auto_logs, "_ORPHAN_HOLD_S", 0.0)
    monkeypatch.setattr(auto_logs, "_ORPHAN_CURSOR", [""])
    stuck = ["11111111-0000-4000-8000-%012d.log.gz" % i for i in range(6)]
    orphan = "99999999-0000-4000-8000-0000000000ff.log.gz"
    for i, nm in enumerate(stuck):
        (logdir / nm).write_bytes(b"x" * 16)
        _mark(logdir, nm, age_s=90_000 - i)
    (logdir / orphan).write_bytes(b"x" * 16)
    _mark(logdir, orphan, age_s=50_000)

    real_unlink = os.unlink

    def _boom(path, *a, **kw):
        if os.path.basename(str(path)).split(".orphan")[0] in stuck:
            raise PermissionError("read-only file system")
        return real_unlink(path, *a, **kw)

    def _db():
        return Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                         "SELECT log_filename FROM bug_reports": [[]]})

    proxy = _OsProxy(unlink=_boom)
    saved = auto_logs.os
    auto_logs.os = proxy
    try:
        passes = [_run(auto_logs.prune_orphan_blobs(_db(), min_age_s=3600,
                                                    limit=2))
                  for _ in range(4)]
    finally:
        auto_logs.os = saved

    assert sum(p["unlinked"] for p in passes) == 1, (
        "the orphan behind a backlog larger than the window was not reached "
        "in four passes: %r" % (passes,))
    assert not (logdir / orphan).exists()
    assert all(p["examined"] <= 2 for p in passes), (
        "a pass examined more than the window: %r" % (passes,))
    assert sorted(_blobs(logdir)) == sorted(stuck), (
        "a stuck blob was reclaimed: %r" % (_blobs(logdir),))

    # MUTANT: the cursor never advances. Every pass takes the same first two
    # names, both of which are stuck, and the orphan is unreachable however
    # many ticks run.
    (logdir / orphan).write_bytes(b"x" * 16)
    _mark(logdir, orphan, age_s=50_000)
    live = auto_logs._marker_candidates

    def _blind(base, cutoff, live_set, held=None, scan_bound=None, cursor=""):
        """The same selection with the cursor never applied: every pass takes
        the window from the start of the name space."""
        return live(base, cutoff, live_set, held, scan_bound, "")

    auto_logs.os = proxy
    auto_logs._marker_candidates = _blind
    try:
        blind = [_run(auto_logs.prune_orphan_blobs(_db(), min_age_s=3600,
                                                   limit=2))
                 for _ in range(4)]
    finally:
        auto_logs.os = saved
        auto_logs._marker_candidates = live

    assert all(p["unlinked"] == 0 for p in blind), (
        "the mutant still reached the orphan, so the live assertion above "
        "proves nothing: %r" % (blind,))
    assert (logdir / orphan).exists(), (
        "the mutant reclaimed the orphan: %r" % (_blobs(logdir),))



class _CountingDir:
    """`os.scandir` over the real directory, counting `stat` calls made on
    the entries it hands back."""

    def __init__(self, it, count):
        self._it = it
        self._count = count

    def __enter__(self):
        self._it.__enter__()
        return self

    def __exit__(self, *exc):
        return self._it.__exit__(*exc)

    def __iter__(self):
        for entry in self._it:
            yield _CountingEntry(entry, self._count)


class _CountingEntry:
    def __init__(self, entry, count):
        self._entry = entry
        self._count = count
        self.name = entry.name

    def is_file(self, *a, **kw):
        return self._entry.is_file(*a, **kw)

    def stat(self, *a, **kw):
        self._count[0] += 1
        return self._entry.stat(*a, **kw)


def _clean_dir(logdir):
    for stale in list(logdir.iterdir()):
        if stale.is_file():
            stale.unlink()
    auto_logs._ORPHAN_HELD.clear()


def _scan_pass(logdir, candidates=None):
    """L3's population -- forty aged markers with no blob and no row -- swept
    once with `_ORPHAN_SCAN_BOUND` as the caller set it. Answers the pass's
    dict, the number of `stat` calls, and the session."""
    _clean_dir(logdir)
    for i, nm in enumerate("cccccccc-0000-4000-8000-%012d.log.gz" % i
                           for i in range(40)):
        _mark(logdir, nm, age_s=90_000 - i)
    count = [0]
    proxy = _OsProxy(scandir=lambda p: _CountingDir(os.scandir(p), count))
    db = Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                   "SELECT log_filename FROM bug_reports": [[]]})
    saved_os, saved_mc = auto_logs.os, auto_logs._marker_candidates
    auto_logs.os = proxy
    if candidates is not None:
        auto_logs._marker_candidates = _point_at(candidates, proxy)
    try:
        out = _run(auto_logs.prune_orphan_blobs(db, min_age_s=3600, limit=200))
    finally:
        auto_logs.os = saved_os
        auto_logs._marker_candidates = saved_mc
        auto_logs._ORPHAN_HELD.clear()
    return out, count[0], db


def _budget_pass(logdir, resolver=None):
    """L2(i)'s population -- as many referenced markers as the whole removal
    budget, and one orphan behind them -- swept once with a budget of two."""
    _clean_dir(logdir)
    referenced = ["aaaaaaaa-0000-4000-8000-%012d.log.gz" % i for i in range(2)]
    orphan = "bbbbbbbb-0000-4000-8000-0000000000ff.log.gz"
    for i, nm in enumerate(referenced):
        (logdir / nm).write_bytes(b"x" * 8)
        _mark(logdir, nm, age_s=90_000 - i)
    (logdir / orphan).write_bytes(b"x" * 8)
    _mark(logdir, orphan, age_s=50_000)
    db = Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                   "SELECT log_filename FROM bug_reports":
                       [[{"log_filename": n} for n in referenced]]})
    saved = auto_logs._resolve_marker_candidates
    if resolver is not None:
        auto_logs._resolve_marker_candidates = resolver
    try:
        return _run(auto_logs.prune_orphan_blobs(db, min_age_s=3600, limit=2))
    finally:
        auto_logs._resolve_marker_candidates = saved
        auto_logs._ORPHAN_HELD.clear()


def _cursor_passes(logdir, prune):
    """L2(ii)'s population -- six markers whose blobs will not unlink and one
    real orphan sorting last -- swept four times by `prune`. Answers how
    many blobs the four passes reclaimed."""
    _clean_dir(logdir)
    stuck = ["11111111-0000-4000-8000-%012d.log.gz" % i for i in range(6)]
    orphan = "99999999-0000-4000-8000-0000000000ff.log.gz"
    for i, nm in enumerate(stuck):
        (logdir / nm).write_bytes(b"x" * 16)
        _mark(logdir, nm, age_s=90_000 - i)
    (logdir / orphan).write_bytes(b"x" * 16)
    _mark(logdir, orphan, age_s=50_000)
    real_unlink = os.unlink

    def _boom(path, *a, **kw):
        if os.path.basename(str(path)).split(".orphan")[0] in stuck:
            raise PermissionError("read-only file system")
        return real_unlink(path, *a, **kw)

    proxy = _OsProxy(unlink=_boom)
    saved = auto_logs.os
    auto_logs.os = proxy
    _point_at(prune, proxy)
    try:
        passes = [_run(prune(Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                                       "SELECT log_filename FROM bug_reports": [[]]}),
                             min_age_s=3600, limit=2))
                  for _ in range(4)]
    finally:
        auto_logs.os = saved
        auto_logs._ORPHAN_HELD.clear()
    return sum(p["unlinked"] for p in passes)


def test_every_round_six_sweep_and_lock_bound_reds_when_it_is_removed(
        logdir, monkeypatch):
    """THE CONTROLS FOR M1(a)'s SPAN, L2 AND L3: one on-site mutation per
    bound, each paired with an INERT TWIN at the same site (#391/#342).

    Kept apart from the behaviour cases they control, so those cases carry
    no mutation anchor and an on-disk inert twin can re-spell the very line
    they guard without the case failing to find its own anchor.
    """
    # -- M1(a): the transaction ended between the SELECT and the DELETE ----
    mutant = _exec_mutant(
        auto_logs.prune_auto_logs, _LOCK_SPAN_SITE,
        "    )).mappings().all()\n    await db.commit()\n    if not due:\n")
    assert _lock_span_findings(_lock_span_events(mutant, logdir)), (
        "a pass that commits between its SELECT and its DELETE produced no "
        "finding, so the lock-span case cannot see the lock end early")
    twin = _exec_mutant(
        auto_logs.prune_auto_logs, _LOCK_SPAN_SITE,
        "    )).mappings().all()\n    await asyncio.sleep(0)\n    if not due:\n")
    assert _lock_span_findings(_lock_span_events(twin, logdir)) == [], (
        "the inert twin reds at the lock span, so the mutant above is "
        "reacting to the site being edited rather than to the transaction "
        "ending")

    # -- L2(i): a referenced marker's clear spends the removal budget ------
    site = "            cleared += 1\n"
    out = _budget_pass(logdir, _exec_mutant(
        auto_logs._resolve_marker_candidates, site,
        site + "            removed += 1\n"))
    assert out["unlinked"] == 0 and out["deferred"] == 1, (
        "with every clear spending a slot, the orphan behind two referenced "
        "markers was still reached on a budget of two: %r" % (out,))
    out = _budget_pass(logdir, _exec_mutant(
        auto_logs._resolve_marker_candidates, site,
        site + "            removed += 0\n"))
    assert out["unlinked"] == 1 and out["deferred"] == 0, (
        "the inert twin reds at the budget: %r" % (out,))

    # -- L2(ii): the cursor never advances ---------------------------------
    # COMPILED AFTER THE PATCHES, because the copy's globals are a snapshot:
    # it has to carry this case's window and this case's cursor list.
    monkeypatch.setattr(auto_logs, "_ORPHAN_SCAN_BOUND", 2)
    monkeypatch.setattr(auto_logs, "_ORPHAN_HOLD_S", 0.0)
    site = "    _ORPHAN_CURSOR[0] = next_cursor\n"
    monkeypatch.setattr(auto_logs, "_ORPHAN_CURSOR", [""])
    reclaimed = _cursor_passes(logdir, _exec_mutant(
        auto_logs.prune_orphan_blobs, site, '    _ORPHAN_CURSOR[0] = ""\n'))
    assert reclaimed == 0, (
        "with a cursor that never advances, four passes over a window of two "
        "still reached the orphan behind six stuck markers (%d)" % reclaimed)
    monkeypatch.setattr(auto_logs, "_ORPHAN_CURSOR", [""])
    reclaimed = _cursor_passes(logdir, _exec_mutant(
        auto_logs.prune_orphan_blobs, site,
        "    _ORPHAN_CURSOR[0] = str(next_cursor)\n"))
    assert reclaimed == 1, (
        "the inert twin reds at the cursor: %d reclaimed" % reclaimed)

    # -- L3: the scan bound not applied to the listing ---------------------
    monkeypatch.setattr(auto_logs, "_ORPHAN_SCAN_BOUND", 8)
    monkeypatch.setattr(auto_logs, "_ORPHAN_CURSOR", [""])
    site = "        window = heapq.nsmallest(bound, _keys(entries))\n"
    out, stats, db = _scan_pass(logdir, _exec_mutant(
        auto_logs._marker_candidates, site,
        "        window = sorted(_keys(entries))\n"))
    offered = [len(p["names"]) for p in
               db.params_for("SELECT log_filename FROM bug_reports")]
    assert out["examined"] == 40 and stats == 40 and sum(offered) == 40, (
        "with the whole listing taken as the window, the pass still examined, "
        "stat-ed and offered only the bound: %r stats=%d offered=%r"
        % (out, stats, offered))
    monkeypatch.setattr(auto_logs, "_ORPHAN_CURSOR", [""])
    out, stats, db = _scan_pass(logdir, _exec_mutant(
        auto_logs._marker_candidates, site,
        "        window = heapq.nsmallest(int(bound), _keys(entries))\n"))
    offered = [len(p["names"]) for p in
               db.params_for("SELECT log_filename FROM bug_reports")]
    assert out["examined"] == 8 and stats == 8 and offered == [8], (
        "the inert twin reds at the listing bound: %r stats=%d offered=%r"
        % (out, stats, offered))


def test_the_sweep_line_does_not_report_bytes_it_never_reclaimed(logdir, capsys):
    """The COUNTER and the LINE agree with each other and with the volume.

    The operator-facing half of the case above: a pass that clears markers and
    reclaims nothing must not print "removed", because that line is what an
    hourly reading of "is the leak draining" is made of.
    """
    name = "aaaaaaaa-0000-4000-8000-0000000000ee.log.gz"
    _mark(logdir, name, age_s=90_000)
    db = Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                   "SELECT log_filename FROM bug_reports": [[]]})
    capsys.readouterr()
    out = _run(auto_logs.prune_orphan_blobs(db, min_age_s=3600))
    printed = capsys.readouterr().out
    assert "removed %s=%s" % (auto_logs._ORPHAN_MARKER, name) not in printed, (
        "a marker whose blob was never on the volume was reported as removed:"
        "\n%s" % printed)
    assert "NO BLOB on the volume" in printed, printed
    assert "%d marker-only" % out["marker_only"] in printed, (
        "the summary line does not carry the marker-only count it returns:"
        "\n%s" % printed)


def test_the_sweep_line_accounts_for_every_unreferenced_candidate(logdir, capsys,
                                                                  monkeypatch):
    """LENS-R3-3, SIBLING SWEEP: the four terms after "unreferenced" SUM to it.

    The finding was that an absent blob was counted as a removal. Answering it
    added a `marker_only` term -- and left a candidate the pass had ATTEMPTED
    and could NOT remove in none of the counters at all: not removed, not
    marker-only, not deferred. The line an operator reads as "how much of the
    leak drained this hour" therefore still did not add up to the population it
    came out of, which is the same reading defect one level down (#304, and
    #430: the arm that fails must say so rather than vanish).

    Here: two marker-only leftovers, one blob the volume will not give up, and
    two ordinary orphans. `orphans` is five and the four terms must sum to it.
    """
    blanks = ["cccccccc-0000-4000-8000-%012d.log.gz" % i for i in range(2)]
    stuck = "cccccccc-0000-4000-8000-0000000000ff.log.gz"
    reals = ["dddddddd-0000-4000-8000-%012d.log.gz" % i for i in range(2)]
    for nm in blanks:
        _mark(logdir, nm, age_s=90_000)
    # A DIRECTORY under the blob's name: `os.unlink` refuses it with an OSError,
    # which is the real "the volume will not give this up" answer rather than a
    # patched-out one. The marker beside it is an ordinary file, so the scan
    # still offers the candidate.
    (logdir / stuck).mkdir()
    (logdir / stuck / "held-open").write_bytes(b"x")
    _mark(logdir, stuck, age_s=90_000)
    for nm in reals:
        (logdir / nm).write_bytes(b"x" * 16)
        _mark(logdir, nm, age_s=90_000)

    def _db():
        return Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                         "SELECT log_filename FROM bug_reports": [[]]})

    capsys.readouterr()
    out = _run(auto_logs.prune_orphan_blobs(_db(), min_age_s=3600))
    printed = capsys.readouterr().out
    assert out["orphans"] == 5, out
    assert out["unlinked"] == 2 and out["marker_only"] == 2, out
    assert out["unremovable"] == 1, (
        "the candidate the pass could not remove is in none of the counters: "
        "%r" % (out,))
    assert out["deferred"] == 0, out
    assert (out["unlinked"] + out["marker_only"] + out["unremovable"]
            + out["deferred"]) == out["orphans"], (
        "the four terms do not sum to the unreferenced population, so the "
        "line cannot be checked against what it came out of: %r" % (out,))
    assert "%d that could not be removed" % out["unremovable"] in printed, (
        "the summary line does not carry the unremovable count it returns:"
        "\n%s" % printed)
    # The one it could not take keeps BOTH its blob and its marker, so the next
    # tick retries it; the other four candidates are resolved.
    assert _marker_names(logdir) == [stuck + auto_logs._ORPHAN_MARKER_SUFFIX], (
        _marker_names(logdir))

    # MUTANT at the counting site: the arm runs and counts nothing, which is
    # exactly the state before this sweep. The sum assertion above reds.
    site = "            unremovable += 1\n"
    # Read the LIVE resolver once: the twin below is compiled from the same
    # source, and an installed mutant has no source on disk to read.
    live_resolver = auto_logs._resolve_marker_candidates
    mutant = _exec_mutant(live_resolver, site,
                          "            unremovable += 0\n")
    monkeypatch.setattr(auto_logs, "_resolve_marker_candidates", mutant)
    for nm in blanks:
        _mark(logdir, nm, age_s=90_000)
    for nm in reals:
        (logdir / nm).write_bytes(b"x" * 16)
        _mark(logdir, nm, age_s=90_000)
    # The live pass above parked the candidate it could not resolve; this run
    # is over the same planted population, so the hold is cleared with it.
    auto_logs._ORPHAN_HELD.clear()
    out = _run(auto_logs.prune_orphan_blobs(_db(), min_age_s=3600))
    assert out["unremovable"] == 0 and out["orphans"] == 5, (
        "the mutant did not drop the count, so the live assertion above "
        "proves nothing: %r" % (out,))
    assert (out["unlinked"] + out["marker_only"] + out["unremovable"]
            + out["deferred"]) != out["orphans"], (
        "the mutant left the sum closing, so the sum is not what holds this "
        "counter honest: %r" % (out,))

    # INERT TWIN at the SAME site: the same increment, spelled out.
    twin = _exec_mutant(live_resolver, site,
                        "            unremovable = unremovable + 1\n")
    monkeypatch.setattr(auto_logs, "_resolve_marker_candidates", twin)
    for nm in blanks:
        _mark(logdir, nm, age_s=90_000)
    for nm in reals:
        (logdir / nm).write_bytes(b"x" * 16)
        _mark(logdir, nm, age_s=90_000)
    auto_logs._ORPHAN_HELD.clear()
    out = _run(auto_logs.prune_orphan_blobs(_db(), min_age_s=3600))
    assert out["unremovable"] == 1 and (
        out["unlinked"] + out["marker_only"] + out["unremovable"]
        + out["deferred"]) == out["orphans"], (
        "the inert twin changed the outcome, so the mutant above is reacting "
        "to the site being edited rather than to the counting: %r" % (out,))


# ── ROUND 4: PERSISTENCE, NOT CALL ORDER ─────────────────────────────────────
#
# Round 3 proved both of this module's write orders at the SYSCALL level: the
# marker is created before the blob's first byte, and the blob is unlinked
# before its marker. Neither sentence survives a HOST crash on its own. A
# filesystem promises nothing about un-synced data, and nothing about the
# order in which two un-synced changes to one directory reach the disk -- so
# "X happens before Y" is a statement about this process, while the guarantee
# the sweep and the row both rest on is a statement about the disk.
#
# The cases below re-derive the failure table over CRASH POINTS rather than
# over statement order, against a filesystem model that DISCARDS what was not
# flushed and replays what was, so a barrier that is removed shows up as a
# forbidden state rather than as an argument.


class _Crashed(BaseException):
    """The host stopped at this point.

    A BaseException on purpose: a power loss is not something a process gets
    to handle, so this must not be caught by an `except Exception` on the path
    under test -- otherwise the simulation would be measuring an error path
    instead of a crash.
    """


class CrashFS:
    """A filesystem with a DURABLE state and a VOLATILE one.

    THE MODEL, which is the conservative reading of what POSIX promises:

    * `write()` changes only what a running process sees.
    * `fsync(file)` promises that file's CONTENTS -- and says nothing about
      the directory ENTRY that names them.
    * `fsync(dir)` promises every directory change issued so far, creations
      and removals alike.
    * A crash discards everything not yet promised. Directory changes that
      were issued and not flushed may reach the disk in ANY combination,
      because there is no ordering between two un-synced entry changes -- so
      a recovery is checked over EVERY subset of them and not only over the
      "nothing persisted" one. That enumeration is what turns a missing
      barrier into a demonstrable state rather than an unlikely one.

    IT SUPPLIES `O_DIRECTORY`, WHICH THIS SEAT'S OWN `os` DOES NOT.
    `_fsync_dir` decides by capability test, so on this development seat the
    directory flush is a no-op and the file handle's own flush commits the
    entry with it. The api container runs Linux, where that is not true; this
    simulation is what exercises that path here, and a barrier removed from it
    reds below even though removing it changes nothing on this seat.
    """

    O_RDONLY = 0
    O_WRONLY = 1
    O_CREAT = 0o100
    O_TRUNC = 0o1000
    O_DIRECTORY = 0o200000
    O_BINARY = 0

    #: bytes accepted per `write`, so a blob takes several calls and a crash
    #: can land BETWEEN two of them.
    CHUNK = 64

    def __init__(self):
        self.live = {}            # name -> bytes, what a running process sees
        self.durable_data = {}    # name -> bytes the filesystem has promised
        self.durable_entry = set()
        self.pending = []         # ("create"|"unlink", name), in issue order
        self._fds = {}
        self._next_fd = 17
        self.ops = []             # one label per intercepted call
        self.crash_before = None  # 1-based index of the op that never happens
        # ONCE THE HOST HAS STOPPED, NOTHING ELSE HAPPENS. `_Crashed` unwinds
        # through the code under test, and a `finally` on that path may reach
        # for the filesystem again; without this flag the model would record
        # effects that no stopped host can produce.
        self.crashed = False
        # FAULTS, which are not crashes: an operation that RAISES and leaves
        # the model untouched, so an error arm can be driven through every
        # crash point after it. Each is [predicate(label), nth, exception,
        # seen]; the nth matching operation raises instead of happening.
        self.faults = []

    # -- the model's own API ------------------------------------------------
    def preload(self, files):
        """Start from a state that is already on the disk."""
        for name, body in files.items():
            self.live[name] = body
            self.durable_data[name] = body
            self.durable_entry.add(name)

    def mark(self, label):
        """A step that is not a filesystem call -- the INSERT, the commit --
        so a crash point can land between them."""
        self._step(label)

    def recover(self, persist):
        """The volume a process would find after a crash here, given that
        `persist` (indices into the still-pending directory operations)
        happened to reach the disk."""
        names = set(self.durable_entry)
        for i, (op, name) in enumerate(self.pending):
            if i not in persist:
                continue
            if op == "create":
                names.add(name)
            else:
                names.discard(name)
        return {n: self.durable_data.get(n, b"") for n in sorted(names)}

    def every_recovery(self):
        """Every resolution of the pending set, worst case included."""
        out = []
        for bits in range(1 << len(self.pending)):
            persist = {i for i in range(len(self.pending)) if bits & (1 << i)}
            out.append((persist, self.recover(persist)))
        return out

    def _step(self, label):
        if self.crashed:
            raise _Crashed("after the crash: %s" % label)
        self.ops.append(label)
        if self.crash_before is not None and len(self.ops) == self.crash_before:
            self.crashed = True
            raise _Crashed(label)
        for fault in self.faults:
            if fault[0](label):
                fault[3] += 1
                if fault[3] == fault[1]:
                    raise fault[2]

    def builtin_open(self, real_open, directory):
        """The builtin `open`, for writes into `directory` only.

        The player-attachment path writes its blob with `open(path, "wb")`
        rather than `os.open`, so a model that did not see that write would
        be checking a different order from the one the handler performs.
        Everything else -- reads, and any file outside the blob directory --
        goes to the real `open`.
        """
        home = os.path.normcase(os.path.abspath(str(directory)))
        fs = self

        def opener(file, mode="r", *a, **kw):
            where = os.path.normcase(os.path.abspath(os.path.dirname(str(file))))
            if where != home or "w" not in mode:
                return real_open(file, mode, *a, **kw)
            return _CrashFile(fs, fs.open(file, fs.O_WRONLY | fs.O_CREAT
                                          | fs.O_TRUNC))
        return opener

    # -- the `os` surface this module uses ----------------------------------
    def open(self, path, flags, mode=0o666):
        if flags & self.O_DIRECTORY:
            self._step("open-dir")
            fd = self._next_fd
            self._next_fd += 1
            self._fds[fd] = None
            return fd
        name = os.path.basename(str(path))
        self._step("open %s" % name)
        if flags & self.O_CREAT:
            if name not in self.live:
                self.pending.append(("create", name))
            self.live[name] = b""
        fd = self._next_fd
        self._next_fd += 1
        self._fds[fd] = name
        return fd

    def write(self, fd, data):
        name = self._fds[fd]
        self._step("write %s" % name)
        chunk = bytes(data)[:self.CHUNK]
        self.live[name] = self.live.get(name, b"") + chunk
        return len(chunk)

    def fsync(self, fd):
        name = self._fds[fd]
        if name is None:
            self._step("fsync-dir")
            for op, entry in self.pending:
                if op == "create":
                    self.durable_entry.add(entry)
                else:
                    self.durable_entry.discard(entry)
            self.pending = []
            return
        self._step("fsync %s" % name)
        self.durable_data[name] = self.live[name]

    def close(self, fd):
        self._fds.pop(fd, None)

    def unlink(self, path):
        name = os.path.basename(str(path))
        self._step("unlink %s" % name)
        if name not in self.live:
            raise FileNotFoundError(name)
        del self.live[name]
        self.pending.append(("unlink", name))

    def __getattr__(self, item):          # path, scandir, stat, everything else
        return getattr(os, item)


class _CrashFile:
    """What `open(path, "wb")` hands back, over a `CrashFS` descriptor.

    `write` takes every byte or raises, as a buffered file does, so a
    failure lands between two of the model's chunked writes. `flush`
    promises nothing -- to a crash, a userspace buffer and the page cache
    are the same thing -- and `fileno` hands out the descriptor, so an
    `os.fsync` on it reaches the model.
    """

    def __init__(self, fs, fd):
        self._fs = fs
        self._fd = fd

    def write(self, data):
        view = bytes(data)
        while view:
            view = view[self._fs.write(self._fd, view):]
        return len(data)

    def flush(self):
        return None

    def fileno(self):
        return self._fd

    def close(self):
        self._fs.close(self._fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


CRASH_BLOB = "eeeeeeee-0000-4000-8000-00000000cafe.log.gz"
CRASH_MARK = CRASH_BLOB + auto_logs._ORPHAN_MARKER_SUFFIX
CRASH_PAYLOAD = b"crash-simulation payload " * 9        # several write() calls
#: WHAT A WHOLE MARKER HOLDS: the blob's own name and a newline, which
#: is the content `_stamp_marker`'s own prose and the notes' disk bound
#: both claim. INV-M below is the invariant that makes that claim
#: falsifiable instead of decorative.
CRASH_MARK_BODY = CRASH_BLOB.encode() + b"\n"


def _point_at(fn, fs):
    """Point a COMPILED COPY's own `os` at the crash filesystem.

    A mutant produced by `_exec_mutant` carries a snapshot of the module's
    globals taken when it was compiled, so patching `auto_logs.os` afterwards
    does not reach it -- and a barrier mutation that quietly ran against the
    real filesystem would make every control below pass for the wrong reason
    (#342). The module's own functions are left alone: their globals ARE the
    module's, so the patch already reaches them.
    """
    if fn is not None and getattr(fn, "__globals__", None) is not vars(auto_logs):
        fn.__globals__["os"] = fs
    return fn


def _drive_upload(crash_before, *, stamp=None, write_blob=None, logdir=None):
    """The upload's write order, run against a fresh `CrashFS`.

    marker -> blob -> INSERT -> commit -> clear the marker, with every
    operation a crash point of its own. The database is modelled by one flag,
    because what is being checked is the JOINT state: what the row claims,
    against what the volume kept.
    """
    fs = CrashFS()
    fs.crash_before = crash_before
    path = pathlib.Path(str(logdir)) / CRASH_BLOB
    own = auto_logs._MarkedBlob(path)
    committed = False
    stamped = False
    real_os = auto_logs.os
    auto_logs.os = fs
    _point_at(stamp, fs)
    _point_at(write_blob, fs)
    try:
        try:
            (stamp or auto_logs._stamp_marker)(path)
            # THE STAMP RETURNED, which is the condition INV-M is stated
            # under. A crash INSIDE the stamp can leave a created-but-empty
            # marker on the volume legitimately -- the entry reached the disk
            # and the contents had not been promised yet -- so an invariant
            # that demanded whole contents there would be demanding a bug.
            # Once this line runs, both of the stamp's barriers have been
            # taken and there is no crash after it that may produce a short
            # marker.
            stamped = True
            own.marked = True
            (write_blob or auto_logs._write_blob)(path, CRASH_PAYLOAD)
            own.written = True
            fs.mark("INSERT")
            fs.mark("COMMIT")
            committed = True
            auto_logs._clear_marker(own)
        except _Crashed:
            pass
    finally:
        auto_logs.os = real_os
        auto_logs._MARKERS_IN_FLIGHT.discard(path.name)
    return fs, committed, stamped


def _drive_delete(crash_before, *, delete=None, logdir=None):
    """The deletion order -- blob, then marker -- from a durable pair."""
    fs = CrashFS()
    fs.preload({CRASH_BLOB: CRASH_PAYLOAD,
                CRASH_MARK: CRASH_BLOB.encode() + b"\n"})
    fs.crash_before = crash_before
    path = pathlib.Path(str(logdir)) / CRASH_BLOB
    real_os = auto_logs.os
    auto_logs.os = fs
    _point_at(delete, fs)
    try:
        try:
            (delete or auto_logs._delete_blob_then_marker)(path)
        except _Crashed:
            pass
    finally:
        auto_logs.os = real_os
    return fs


def _upload_violations(stamp=None, write_blob=None, logdir=None):
    """Every (crash point, recovery) of the upload order that breaks one of
    the THREE invariants.

    INV-A  a blob on the recovered volume is named by a committed row, or
           carries a marker. Anything else is a file nothing in this tree will
           ever collect, on a volume shared with player-filed attachments.
    INV-B  a committed row's blob is on the recovered volume with ALL of its
           bytes. A row naming bytes the filesystem never promised is a
           download that answers a read error over a file the database says
           exists.
    INV-M  once the stamp has RETURNED, a marker on the recovered volume holds
           the whole of its content.

    INV-M IS WHY BARRIER 1 IS NO LONGER DECLINED. Round 5 left the marker's
    CONTENTS flush without a control, on the reading that no reader in this
    tree opens a marker -- true, and not a reason. The flush is performed, the
    function's prose states what it makes durable, and the notes derive a disk
    bound from that content; an assertion nothing can falsify is the shape
    #342 and #441 are about, and a barrier with no control is one refactor
    away from being dropped as dead work.

    So the property is stated where it is actually made rather than where it
    would be convenient. INV-A asks only whether the marker EXISTS, and a
    marker created without its contents flushed exists -- as a zero-byte file
    -- so INV-A cannot see barrier 1 go. INV-M asks what is IN it, under the
    one condition that makes the question answerable: the stamp returned, so
    both of its barriers were taken, so no crash after that point may produce
    a short marker. A crash INSIDE the stamp is excluded because a
    created-but-unflushed file reaching the disk empty is the model behaving
    correctly, not the code failing.
    """
    bad = []
    probe, _, _ = _drive_upload(None, stamp=stamp, write_blob=write_blob,
                                logdir=logdir)
    for point in range(1, len(probe.ops) + 2):
        fs, committed, stamped = _drive_upload(
            point, stamp=stamp, write_blob=write_blob, logdir=logdir)
        for _persist, image in fs.every_recovery():
            if committed and image.get(CRASH_BLOB) != CRASH_PAYLOAD:
                bad.append(("INV-B", point, fs.ops[-1], sorted(image)))
            if (CRASH_BLOB in image and CRASH_MARK not in image
                    and not committed):
                bad.append(("INV-A", point, fs.ops[-1], sorted(image)))
            if (stamped and CRASH_MARK in image
                    and image[CRASH_MARK] != CRASH_MARK_BODY):
                bad.append(("INV-M", point, fs.ops[-1],
                            image[CRASH_MARK]))
    return bad, len(probe.ops)


def _delete_violations(delete=None, logdir=None):
    """The deletion order's invariant: nothing this pass does may leave the
    blob on the volume with its marker gone."""
    bad = []
    probe = _drive_delete(None, delete=delete, logdir=logdir)
    for point in range(1, len(probe.ops) + 2):
        fs = _drive_delete(point, delete=delete, logdir=logdir)
        for _persist, image in fs.every_recovery():
            if CRASH_BLOB in image and CRASH_MARK not in image:
                bad.append(("INV-A", point, fs.ops[-1], sorted(image)))
    return bad, len(probe.ops)


CRASH_ROW = "99999999-0000-4000-8000-0000000000aa"


def _drive_retention(crash_before, *, unlink_due=None, logdir=None):
    """RETENTION's order -- unlink the blob, flush the directory, DELETE the
    row, commit -- run against a fresh `CrashFS`.

    It starts from a durable blob with NO MARKER, which is what an ordinary
    automatic attachment is once its row has committed. The reference being
    dropped here is that ROW, so the database side is modelled by one flag in
    the same way the upload order models its INSERT.
    """
    fs = CrashFS()
    fs.preload({CRASH_BLOB: CRASH_PAYLOAD})
    fs.crash_before = crash_before
    base = pathlib.Path(str(logdir))
    deleted = False
    real_os = auto_logs.os
    auto_logs.os = fs
    _point_at(unlink_due, fs)
    try:
        try:
            (unlink_due or auto_logs._unlink_due_blobs)(
                base, [(CRASH_ROW, CRASH_BLOB)])
            fs.mark("DELETE")
            fs.mark("COMMIT")
            deleted = True
        except _Crashed:
            pass
    finally:
        auto_logs.os = real_os
    return fs, deleted


def _retention_violations(unlink_due=None, logdir=None):
    """Retention's invariant.

    INV-R  once the row that names a blob is durably DELETED, that blob is not
           on the recovered volume. It never had a marker, so the orphan sweep
           cannot name it, and `prune_auto_logs` selects ROWS -- the row it
           would have selected on is the one that has just gone. A blob
           recovered here is outside both collectors for good.
    """
    bad = []
    probe, _ = _drive_retention(None, unlink_due=unlink_due, logdir=logdir)
    for point in range(1, len(probe.ops) + 2):
        fs, deleted = _drive_retention(point, unlink_due=unlink_due,
                                       logdir=logdir)
        for _persist, image in fs.every_recovery():
            if deleted and CRASH_BLOB in image:
                bad.append(("INV-R", point, fs.ops[-1], sorted(image)))
    return bad, len(probe.ops)


def test_the_crash_simulation_finds_no_uncollectable_state_in_either_order(logdir):
    """R3-M2 / R3-M3 / prior H2: THE THREE ORDERS, RE-DERIVED OVER CRASH POINTS.

    The name keeps round 4's "either order"; round 5 added retention's as the
    third. Every point between two operations is taken as a crash, and every
    resolution of the directory changes that had not been flushed is checked
    -- including the worst, where a later removal persists and an earlier one
    does not. What has to hold at each of them is small enough to state: no
    blob that nothing names (INV-A), no committed row over bytes the
    filesystem never promised (INV-B), no marker short of its whole content
    once the stamp has returned (INV-M), and, in retention's order, no blob
    left behind a row that is durably deleted (INV-R).

    The points the upload order enumerates, in the order they occur: before
    the marker's first byte; before its contents are flushed; before its
    directory entry is; before the blob's first byte; BETWEEN two of the
    blob's writes; after its last byte and before the contents flush; after
    the contents flush and before the directory flush; after the directory
    flush and before the INSERT; between the INSERT and the commit; after the
    commit and before the marker is cleared; and after the clear. The deletion
    order enumerates: before the blob's unlink; after it and before the
    directory flush; after the flush and before the marker's unlink; and after
    both.
    """
    # IN EACH ORDER THE INVARIANTS ARE JUDGED BEFORE THE STEP COUNT. The count
    # guards against an enumeration that drove too little to mean anything,
    # and it is still asserted; judged first, it answered the removal of the
    # deletion order's and the retention order's barriers with "too few
    # operations" -- which names the barrier, but not what its absence lets a
    # crash leave on the volume, and that is the question this case asks.
    bad, steps = _upload_violations(logdir=logdir)
    assert bad == [], (
        "the upload order leaves a state nothing can collect, a row over "
        "bytes that were never promised, or a marker whose content the stamp "
        "claimed to have made durable: %r" % (bad[:4],))
    assert steps >= 14, (
        "the upload order produced only %d operations, so the crash points "
        "this case claims to enumerate are not the ones it drove" % steps)

    bad, steps = _delete_violations(logdir=logdir)
    assert bad == [], (
        "the deletion order can leave a blob with no marker: %r" % (bad[:4],))
    assert steps >= 4, (
        "the deletion order produced only %d operations; the barrier between "
        "the two unlinks is one of them" % steps)

    # THE THIRD ORDER, and the one round 4 did not enumerate: retention's.
    # The points it takes are the unlink, the directory flush that makes it
    # durable, the DELETE of the row that names the blob, and the commit. The
    # blob has no marker, so a recovery that finds it after the row is durably
    # gone is outside BOTH collectors rather than merely untidy.
    bad, steps = _retention_violations(logdir=logdir)
    assert bad == [], (
        "the retention order can strand a blob whose row is durably deleted: "
        "%r" % (bad[:4],))
    assert steps >= 4, (
        "the retention order produced only %d operations; the barrier between "
        "the last unlink and the DELETE is one of them" % steps)


def test_every_durability_barrier_reds_the_crash_simulation_when_it_is_removed(
        logdir):
    """THE CONTROL FOR THE CASE ABOVE, one mutation per barrier (#391/#342).

    A simulation that passes with a barrier deleted is decoration. Each of the
    six barriers the upload, deletion and retention orders rest on is removed
    in turn -- at its own site, in a compiled copy, so the module itself is
    untouched -- and each removal has to produce a forbidden state. Each is
    then paired with an INERT TWIN at the SAME site: the same barrier, spelled
    differently, which must leave the simulation clean.
    """
    real_stamp, real_write = auto_logs._stamp_marker, auto_logs._write_blob
    real_delete = auto_logs._delete_blob_then_marker

    # -- BARRIER 1: the MARKER's CONTENTS (_stamp_marker) -------------------
    #
    # The barrier round 5 declined, and the reason it was declinable was that
    # the only invariants on the table asked whether the marker EXISTED. A
    # marker created and never flushed exists -- empty -- so INV-A passed
    # over the mutation and the barrier had no control at all. INV-M asks
    # what is in it once the stamp has returned, which is the claim the
    # function's own prose makes, and that claim is now falsifiable.
    site = "        os.fsync(fd)\n"
    bad, _ = _upload_violations(
        stamp=_exec_mutant(real_stamp, site, "        pass\n"), logdir=logdir)
    assert any(kind == "INV-M" for kind, *_ in bad), (
        "with the marker's contents never flushed the simulation still "
        "recovered a whole marker at every crash point, so barrier 1 is "
        "being asserted by nothing: %r" % (bad[:3],))
    assert all(kind == "INV-M" for kind, *_ in bad), (
        "dropping the marker's CONTENTS flush also broke an invariant about "
        "the blob or the row, which means the mutation is not isolated to "
        "the barrier it names: %r" % (bad[:3],))
    bad, _ = _upload_violations(
        stamp=_exec_mutant(real_stamp, site, "        os.fsync(int(fd))\n"),
        logdir=logdir)
    assert bad == [], (
        "the inert twin reds at the marker's contents barrier, so the "
        "mutation above is reacting to the site being edited rather than to "
        "the barrier: %r" % (bad[:3],))

    # -- BARRIER: the blob's CONTENTS (_write_blob) -------------------------
    site = "        os.fsync(fd)\n"
    bad, _ = _upload_violations(
        write_blob=_exec_mutant(real_write, site, "        pass\n"),
        logdir=logdir)
    assert any(kind == "INV-B" for kind, *_ in bad), (
        "with the blob's contents never flushed the simulation still found no "
        "committed row over unpromised bytes: %r" % (bad[:3],))
    bad, _ = _upload_violations(
        write_blob=_exec_mutant(real_write, site, "        os.fsync(int(fd))\n"),
        logdir=logdir)
    assert bad == [], (
        "the inert twin reds, so the mutation above is reacting to the site "
        "being edited rather than to the barrier: %r" % (bad[:3],))

    # THE INERT TWINS ON THE THREE DIRECTORY BARRIERS re-spell the argument
    # rather than the call, because the call is what the barrier IS. Every one
    # of the three sites now reads `_fsync_dir(pathlib.Path(x).parent)`, so a
    # twin that merely added the coercion would be the live line and would
    # prove nothing (#342); `pathlib.Path(str(x))` is the same location
    # reached by a different spelling.

    # -- BARRIER: the blob's directory ENTRY --------------------------------
    site = "    _fsync_dir(pathlib.Path(path).parent)\n"
    bad, _ = _upload_violations(
        write_blob=_exec_mutant(real_write, site, "    pass\n"), logdir=logdir)
    assert any(kind == "INV-B" for kind, *_ in bad), (
        "with the blob's directory entry never flushed, a crash after the "
        "commit still recovered the file every time: %r" % (bad[:3],))
    bad, _ = _upload_violations(
        write_blob=_exec_mutant(
            real_write, site,
            "    _fsync_dir(pathlib.Path(str(path)).parent)\n"),
        logdir=logdir)
    assert bad == [], (
        "the inert twin reds at the blob's directory barrier: %r" % (bad[:3],))

    # -- BARRIER: the marker's directory ENTRY, before the blob exists ------
    site = "    _fsync_dir(pathlib.Path(blob_path).parent)\n"
    bad, _ = _upload_violations(
        stamp=_exec_mutant(real_stamp, site, "    pass\n"), logdir=logdir)
    assert any(kind == "INV-A" for kind, *_ in bad), (
        "with the marker's entry never flushed, the blob's own entry could "
        "still not outlive it: %r" % (bad[:3],))
    bad, _ = _upload_violations(
        stamp=_exec_mutant(
            real_stamp, site,
            "    _fsync_dir(pathlib.Path(str(blob_path)).parent)\n"),
        logdir=logdir)
    assert bad == [], (
        "the inert twin reds at the marker's directory barrier: %r" % (bad[:3],))

    # -- BARRIER: between the two unlinks -----------------------------------
    # The same anchor: the deletion helper spells its barrier exactly as the
    # stamp does, and `_exec_mutant_pairs` asserts it occurs once inside THIS
    # function's span, so the two mutations cannot reach each other's site.
    bad, _ = _delete_violations(
        delete=_exec_mutant(real_delete, site, "    pass\n"), logdir=logdir)
    assert any(kind == "INV-A" for kind, *_ in bad), (
        "with no flush between the two unlinks the simulation still could not "
        "persist the marker's removal ahead of the blob's: %r" % (bad[:3],))
    bad, _ = _delete_violations(
        delete=_exec_mutant(
            real_delete, site,
            "    _fsync_dir(pathlib.Path(str(blob_path)).parent)\n"),
        logdir=logdir)
    assert bad == [], (
        "the inert twin reds at the deletion barrier: %r" % (bad[:3],))

    # -- BARRIER: retention's unlink pass, before the rows are DELETEd ------
    #
    # The sibling order round 4 did not reach. The reference being dropped is
    # a committed row rather than a marker, and the blob carries no marker at
    # all, so the state a missing barrier leaves is not collectable by
    # anything in this tree.
    real_due = auto_logs._unlink_due_blobs
    site = "            _fsync_dir(pathlib.Path(base))\n"
    bad, _ = _retention_violations(
        unlink_due=_exec_mutant(real_due, site, "            pass\n"),
        logdir=logdir)
    assert any(kind == "INV-R" for kind, *_ in bad), (
        "with retention's removals never flushed, a crash after the row "
        "DELETE committed still could not recover the blob: %r" % (bad[:3],))
    bad, _ = _retention_violations(
        unlink_due=_exec_mutant(
            real_due, site, "            _fsync_dir(pathlib.Path(str(base)))\n"),
        logdir=logdir)
    assert bad == [], (
        "the inert twin reds at retention's barrier: %r" % (bad[:3],))


# ── ROUND 6: THE LATER PASS, AND THE PLAYER ATTACHMENT ──────────────────────
#
# Two orders the round-5 simulation did not drive. M1's is retention's, one
# pass later: a pass that unlinked and never reached its flush or its commit
# leaves the removal ISSUED and unpromised -- its process ended, the host did
# not -- and the next pass to select the row reads `absent` off it. L4's and
# L5's are the player attachment's: the handler writes a player's log with
# the builtin `open()` and commits the row that names it, and the model sees
# that write through `CrashFS.builtin_open`.


class _CrashRetentionDB(Scripted):
    """Retention's session over a `CrashFS`. The DELETE and the COMMIT are
    crash points of their own, and `deleted` becomes true only once a commit
    has carried a DELETE -- which is the moment the blob's only reference is
    durably gone."""

    def __init__(self, fs):
        super().__init__({DUE_KEY: [[{"id": CRASH_ROW,
                                      "log_filename": CRASH_BLOB}]],
                          "DELETE FROM bug_reports": [[{"id": CRASH_ROW}]]})
        self._crash_fs = fs
        self.deleting = False
        self.deleted = False

    async def execute(self, statement, params=None):
        if " ".join(str(statement).split()).startswith("DELETE FROM bug_reports"):
            self._crash_fs.mark("DELETE")
            self.deleting = True
        return await super().execute(statement, params)

    async def commit(self):
        self._crash_fs.mark("COMMIT")
        await super().commit()
        if self.deleting:
            self.deleted = True


def _faults(spec):
    """Fresh fault records for one drive: `(predicate, nth, type, message)`
    becomes `[predicate, nth, exception, seen]`, so no drive inherits another
    one's count or traceback."""
    return [[pred, nth, exc(msg), 0] for pred, nth, exc, msg in spec]


def _is_dir_flush(label):
    return label == "fsync-dir"


def _is_blob_write(label):
    return label.startswith("write ") and label.endswith(".log.gz")


def _is_blob_unlink(label):
    return label.startswith("unlink ") and label.endswith(".log.gz")


#: The later pass's own barrier refuses. What the pass may do then is keep
#: the row -- and nothing else.
_LATER_REFUSES = ((_is_dir_flush, 1, OSError, "the directory would not flush"),)


def _drive_later_pass(crash_before, *, prune=None, unlink_due=None, faults=(),
                      logdir=None):
    """M1's order, from a durable blob whose row is due.

    The EARLIER pass is one unlink and nothing more: it issued the removal
    and its process ended before the flush and before the commit, so the
    entry change is in the directory cache and the row is still there. The
    LATER pass is the real `prune_auto_logs` over the same row: it observes
    `absent`, and what it may do about that is what this order measures.
    """
    fs = CrashFS()
    fs.preload({CRASH_BLOB: CRASH_PAYLOAD})
    fs.crash_before = crash_before
    fs.faults = _faults(faults)
    base = pathlib.Path(str(logdir))
    db = _CrashRetentionDB(fs)
    real_os = auto_logs.os
    real_due = auto_logs._unlink_due_blobs
    auto_logs.os = fs
    if unlink_due is not None:
        auto_logs._unlink_due_blobs = _point_at(unlink_due, fs)
    auto_logs._PRUNE_HELD.clear()
    try:
        try:
            auto_logs._unlink_existing(base / CRASH_BLOB)   # the earlier pass
            _run((prune or auto_logs.prune_auto_logs)(db))
        except _Crashed:
            pass
    finally:
        auto_logs.os = real_os
        auto_logs._unlink_due_blobs = real_due
        auto_logs._PRUNE_HELD.clear()
    return fs, db


def _later_pass_violations(*, prune=None, unlink_due=None, faults=(),
                           logdir=None):
    """INV-R over every crash point of the later pass: once a commit has
    carried the DELETE, the blob is on no recovered volume."""
    bad = []
    probe, probe_db = _drive_later_pass(None, prune=prune,
                                        unlink_due=unlink_due, faults=faults,
                                        logdir=logdir)
    for point in range(1, len(probe.ops) + 2):
        fs, db = _drive_later_pass(point, prune=prune, unlink_due=unlink_due,
                                   faults=faults, logdir=logdir)
        for _persist, image in fs.every_recovery():
            if db.deleted and CRASH_BLOB in image:
                bad.append(("INV-R", point, fs.ops[-1], sorted(image)))
    return bad, probe, probe_db


def test_a_later_retention_pass_keeps_the_row_until_the_earlier_unlink_is_durable(
        logdir):
    """M1, THE WITNESS SHAPE: the later `absent` pass keeps the row until the
    earlier unlink is PROVEN durable.

    "The file is not there" is usually a fact about an EARLIER pass -- one
    that unlinked and did not reach its flush or its commit -- and that
    pass's removal may still be only in the directory cache. The later pass
    is entitled to drop the row only once a directory flush has promised the
    removal, and a flush it issues itself is enough, because a directory
    flush promises every entry change issued in that directory and not only
    the ones this process issued (#507).

    Two readings, over every crash point and every resolution of what was
    pending. Where the later pass's flush succeeds it DELETES the row, after
    the barrier -- so the case is not satisfied by a pass that never
    collects an absent row. Where its flush refuses it keeps the row and
    deletes nothing, so no crash anywhere can recover the blob after its
    reference is durably gone.

    The mutants that red this order live in
    `test_every_round_six_crash_point_reds_when_its_mechanism_is_removed`:
    this case carries no mutation anchor of its own, so an on-disk inert
    twin can re-spell the line it guards and still leave it green.
    """
    bad, probe, db = _later_pass_violations(logdir=logdir)
    assert bad == [], (
        "a later pass dropped the row over an earlier unlink no flush had "
        "promised: %r" % (bad[:3],))
    assert db.deleted, (
        "the later pass never collected the absent row, so the clean reading "
        "above is the reading of a pass that does nothing: %r" % (probe.ops,))
    assert probe.ops[:1] == ["unlink " + CRASH_BLOB], probe.ops
    assert probe.ops.index("fsync-dir") < probe.ops.index("DELETE"), (
        "the later pass deleted the row before its own directory flush: %r"
        % (probe.ops,))
    assert len(probe.ops) >= 5, (
        "the later pass produced only %d operations -- the earlier unlink, "
        "the barrier's open and flush, the DELETE and the COMMIT are five"
        % len(probe.ops))

    bad, probe, db = _later_pass_violations(faults=_LATER_REFUSES,
                                            logdir=logdir)
    assert bad == [], (
        "a later pass whose own barrier REFUSED still dropped the row: %r"
        % (bad[:3],))
    assert not db.deleted and "DELETE" not in probe.ops, (
        "the row was deleted although no removal on the volume could be "
        "proved: %r" % (probe.ops,))


#: What a player attaches in the crash simulation: short enough to drive
#: quickly, and varied enough that its gzip stream still takes several of
#: the model's 64-byte writes, so a failure and a crash can both land
#: BETWEEN two of them.
CRASH_REPORT_LOG = "".join(
    "line %02d %08x %08x %08x %08x\n"
    % (i, (i * 2654435761) & 0xFFFFFFFF, (i * 40503 + 7) ** 3 & 0xFFFFFFFF,
       (i * 7919 + 3) ** 2 & 0xFFFFFFFF, (i * 97 + 13) ** 5 & 0xFFFFFFFF)
    for i in range(12))


class _CrashReportSession(_ReportSession):
    """`_ReportSession` whose COMMIT is a crash point, remembering what the
    row said and what the volume held for that name at the instant it
    committed."""

    def __init__(self, fs, *a, **kw):
        super().__init__(*a, **kw)
        self._crash_fs = fs
        self.row_at_commit = None

    async def commit(self):
        self._crash_fs.mark("COMMIT")
        await super().commit()
        report = self.added[0]
        name = report.log_filename
        self.row_at_commit = (name, report.log_bytes,
                              self._crash_fs.live.get(name) if name else None)


#: THE PLAYER ATTACHMENT'S ORDERS: the stored attachment, and every arm the
#: handler takes when the volume answers badly -- a write that fails partway,
#: that failure's cleanup flush answering FileNotFoundError (L5's arm), the
#: cleanup's unlink refusing, and a commit that raises.
_PLAYER_ORDERS = (
    ("stored", (), False),
    ("write-fails",
     ((_is_blob_write, 2, OSError, "no space left on device"),), False),
    ("flush-vanishes",
     ((_is_blob_write, 2, OSError, "no space left on device"),
      (_is_dir_flush, 2, FileNotFoundError, "the directory went away")), False),
    ("unlink-refuses",
     ((_is_blob_write, 2, OSError, "no space left on device"),
      (_is_blob_unlink, 1, PermissionError, "the file would not unlink")),
     False),
    ("commit-raises", (), True),
)


def _drive_report(crash_before, *, handler=None, faults=(), commit_fails=False,
                  logdir=None):
    """`submit_bug_report` with one attached log, over a fresh `CrashFS`.

    The handler's OWN globals are pointed at the model -- the live module's
    for the live handler, the private copy's for a mutant -- so a mutation
    cannot quietly run against the real filesystem (#342). `auto_logs.os`
    is pointed too, because the marker, the flushes and the marker clear
    are that module's functions.
    """
    import builtins

    # THE WALK POINTS THE HANDLER AT THE DIRECTORY IT MODELS, ITSELF (round-6
    # LOW 1). The attachment's path comes from `BUG_REPORT_LOG_DIR`, and the
    # model sees a write only inside `logdir`. A walk driven without the
    # `logdir` fixture -- the round-6 evidence script was one -- therefore
    # wrote its blob to whatever directory that global named, and its record
    # labelled "stored" never showed the blob's write, its flushes or its
    # commit. Both names the lookup can resolve through are pointed: a mutant
    # runs in a COPY of the module's globals, but `_bug_report_log_path`
    # reads the live module's.
    assert logdir is not None, (
        "a player-attachment walk needs a directory to model; without one the "
        "attachment is written wherever BUG_REPORT_LOG_DIR points")
    fs = CrashFS()
    fs.crash_before = crash_before
    fs.faults = _faults(faults)
    handler = handler or main.submit_bug_report
    g = handler.__globals__
    saved = {k: g[k] for k in ("os", "_is_admin", "_mark_mod_seen",
                               "BUG_REPORT_LOG_DIR")}
    saved_live_dir = main.BUG_REPORT_LOG_DIR
    real_open = builtins.open
    real_auto_os = auto_logs.os
    db = _CrashReportSession(fs, {"FROM bug_reports": [[{"count": 0}]]},
                             fail_commit=commit_fails)
    req = schemas.BugReportRequest(steam_id=STEAM, description="it broke",
                                   log_text=CRASH_REPORT_LOG)
    outcome = None
    g["os"] = fs
    g["_is_admin"] = _no_admin
    g["_mark_mod_seen"] = _noop_mark
    g["BUG_REPORT_LOG_DIR"] = main.BUG_REPORT_LOG_DIR = str(logdir)
    auto_logs.os = fs
    builtins.open = fs.builtin_open(real_open, logdir)
    try:
        try:
            outcome = _run(handler(req, _request(), db))
        except _Crashed:
            outcome = "crashed"
        except Exception as ex:          # the request FAILED; not a crash
            outcome = "raised %s" % type(ex).__name__
    finally:
        builtins.open = real_open
        auto_logs.os = real_auto_os
        g.update(saved)
        main.BUG_REPORT_LOG_DIR = saved_live_dir
        for obj in db.added[:1]:
            auto_logs._MARKERS_IN_FLIGHT.discard("%s.log.gz" % (obj.id,))
    return fs, db, outcome


def _report_violations(order, *, handler=None, logdir=None):
    """Every (crash point, recovery) of one player-attachment order that
    breaks an invariant.

    INV-A  a blob on the recovered volume is named by the committed row or
           carries a marker. Anything else is a file nothing in this tree
           will ever collect.
    INV-B  a committed row that claims a STORED attachment (log_bytes set)
           names a blob the recovered volume holds whole. A row that keeps a
           reference with log_bytes NULL claims no bytes -- the arm that
           writes it says the file may be truncated -- so it is held to
           INV-A only.
    """
    name, faults, commit_fails = order
    bad = []
    probe, probe_db, outcome = _drive_report(
        None, handler=handler, faults=faults, commit_fails=commit_fails,
        logdir=logdir)
    suffix = auto_logs._ORPHAN_MARKER_SUFFIX
    for point in range(1, len(probe.ops) + 2):
        fs, db, _ = _drive_report(point, handler=handler, faults=faults,
                                  commit_fails=commit_fails, logdir=logdir)
        row = db.row_at_commit
        where = fs.ops[-1] if fs.ops else None
        for _persist, image in fs.every_recovery():
            for blob in image:
                if blob.endswith(suffix):
                    continue
                if row is not None and row[0] == blob:
                    continue
                if blob + suffix in image:
                    continue
                bad.append(("INV-A", name, point, where, sorted(image)))
            if row is not None and row[1]:
                if (image.get(row[0]) != row[2]
                        or len(row[2] or b"") != row[1]):
                    bad.append(("INV-B", name, point, where, sorted(image)))
    return bad, probe, probe_db, outcome


def test_the_player_attachment_order_leaves_nothing_uncollectable_at_any_crash_point(
        logdir):
    """L4 AND L5, RE-DERIVED OVER CRASH POINTS rather than argued.

    The handler stamps a marker, durably, before the attachment's first
    byte; writes the attachment and makes it durable; commits the row that
    names it; and clears the marker. Every operation is a crash point, every
    resolution of the directory changes still pending is a recovery, and
    five orders are driven: the stored attachment, a write that fails
    partway, that failure's cleanup flush answering FileNotFoundError, the
    cleanup's unlink refusing, and a commit that raises.

    What has to hold at each of them is INV-A and INV-B (see
    `_report_violations`): no file that nothing names, and no stored
    attachment whose bytes the filesystem never promised. The first is L4's
    crash point -- between the first byte and the cleanup arm -- and L5's --
    a removal that was never proved, disclaimed by the row; the second is
    the durability of the stored attachment itself.

    Like the later-pass case above, this carries no mutation anchor; the
    matrix case below is where each mechanism is removed.
    """
    seen = {}
    for order in _PLAYER_ORDERS:
        bad, probe, db, outcome = _report_violations(order, logdir=logdir)
        assert bad == [], (
            "the player attachment's %r order leaves a state nothing can "
            "collect, or a stored row over bytes never promised: %r"
            % (order[0], bad[:3]))
        seen[order[0]] = (probe, db, outcome)

    # EACH ORDER DROVE THE ARM IT NAMES -- otherwise a clean reading could be
    # the reading of five copies of the same path.
    probe, db, outcome = seen["stored"]
    assert outcome["log_persisted"] is True, outcome
    writes = [op for op in probe.ops if _is_blob_write(op)]
    assert len(writes) >= 2, (
        "the attachment took %d write(s), so no crash point falls BETWEEN two "
        "of them: %r" % (len(writes), probe.ops))
    first_blob_op = next(i for i, op in enumerate(probe.ops)
                         if op.endswith(".log.gz") and op.startswith("open "))
    first_marker_flush = probe.ops.index("fsync-dir")
    assert first_marker_flush < first_blob_op, (
        "the attachment was opened before its marker's entry was flushed: %r"
        % (probe.ops,))
    assert db.row_at_commit[1] == len(db.row_at_commit[2]), db.row_at_commit

    probe, db, _ = seen["write-fails"]
    assert db.row_at_commit[0] is None and db.row_at_commit[1] == 0, (
        "the failed write did not disclaim the attachment: %r"
        % (db.row_at_commit,))
    assert any(_is_blob_unlink(op) for op in probe.ops), probe.ops

    for arm in ("flush-vanishes", "unlink-refuses"):
        probe, db, _ = seen[arm]
        assert db.row_at_commit[0] is not None and db.row_at_commit[1] is None, (
            "the %r arm did not keep the reference: %r"
            % (arm, db.row_at_commit))

    probe, db, outcome = seen["commit-raises"]
    assert outcome == "raised RuntimeError" and db.row_at_commit is None, (
        outcome, db.row_at_commit)
    assert any(n.endswith(auto_logs._ORPHAN_MARKER_SUFFIX)
               for n in probe.live), (
        "the commit that raised took the attachment's marker with it: %r"
        % (sorted(probe.live),))


class _OrderedRetentionDB(Scripted):
    """`Scripted` keeping ONE ordered record of the due SELECT, the unlink
    pass, the DELETE and every transaction boundary -- so what is asserted is
    WHEN the row lock ends, rather than the words that take it (#732)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.events = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.events.append("SELECT-DUE" if DUE_KEY in sql else
                           "DELETE" if sql.startswith("DELETE FROM bug_reports")
                           else "SQL")
        return await super().execute(statement, params)

    async def commit(self):
        self.events.append("COMMIT")
        await super().commit()

    async def rollback(self):
        self.events.append("ROLLBACK")
        await super().rollback()


def _lock_span_events(prune, logdir):
    """`prune` over one due row whose blob is present: the ordered events."""
    (logdir / "a.log.gz").write_bytes(b"x")
    db = _OrderedRetentionDB(
        {DUE_KEY: [[{"id": str(R1), "log_filename": "a.log.gz"}]],
         "DELETE FROM bug_reports": [[{"id": str(R1)}]]})
    g = prune.__globals__
    real = g["_unlink_due_blobs"]

    def _recording(base, plan):
        db.events.append("UNLINK-PASS")
        return real(base, plan)

    g["_unlink_due_blobs"] = _recording
    auto_logs._PRUNE_HELD.clear()
    try:
        _run(prune(db))
    finally:
        g["_unlink_due_blobs"] = real
        auto_logs._PRUNE_HELD.clear()
    return db.events


def _lock_span_findings(events):
    """What is wrong with one retention pass's order, as a list."""
    try:
        s = events.index("SELECT-DUE")
        u = events.index("UNLINK-PASS")
        d = events.index("DELETE")
    except ValueError:
        return ["the pass did not select, unlink and delete: %r" % (events,)]
    bad = []
    if not s < u < d:
        bad.append("out of order: %r" % (events,))
    ends = [i for i, e in enumerate(events) if e in ("COMMIT", "ROLLBACK")]
    if any(s < i < d for i in ends):
        bad.append("a transaction ends between the SELECT and the DELETE, "
                   "which releases the row lock before the DELETE it "
                   "protects: %r" % (events,))
    if not any(i > d and events[i] == "COMMIT" for i in ends):
        bad.append("no COMMIT after the DELETE: %r" % (events,))
    return bad


#: M1(a)'s span, cut: a commit straight after the due SELECT ends the
#: transaction -- and the row lock with it -- before the unlink pass runs.
_LOCK_SPAN_SITE = "    )).mappings().all()\n    if not due:\n"


def test_the_due_rows_stay_locked_from_the_select_through_the_delete_commit(
        logdir):
    """M1(a), MEASURED AS AN ORDER rather than as a clause.

    `FOR NO KEY UPDATE SKIP LOCKED` keeps an overlapping pass off this pass's
    rows only for as long as the transaction that took the lock is open. The
    window the lock exists to close runs from the SELECT, through the unlink
    pass on the worker thread, to the DELETE and its commit -- so the
    property is that no transaction boundary falls inside that span. The
    clause itself is asserted beside this
    (`test_the_due_selection_takes_the_row_lock_that_conflicts_with_its_own_delete`)
    and its behaviour against a real server is the lock harness in the
    round-6 evidence; this is the half a statement's text cannot show.

    Its mutant and inert twin are in
    `test_every_round_six_sweep_and_lock_bound_reds_when_it_is_removed`, so
    this case carries no mutation anchor of its own.
    """
    events = _lock_span_events(auto_logs.prune_auto_logs, logdir)
    assert _lock_span_findings(events) == [], (
        "the retention pass: %r" % (_lock_span_findings(events),))


def _report_mutant_pairs(pairs):
    """`_report_mutant` for an edit that MOVES a statement: every anchor is
    asserted to be one site inside the handler's own span, applied in order,
    and compiled without the route decorator (#432/#279)."""
    src = textwrap.dedent(inspect.getsource(main.submit_bug_report))
    head, _, rest = src.partition("\n")
    assert head.startswith("@app.post("), (
        "submit_bug_report no longer starts with its route decorator: %r"
        % (head,))
    for anchor, replacement in pairs:
        assert rest.count(anchor) == 1, (
            "the mutation anchor occurs %d time(s) in submit_bug_report, not "
            "once: %r" % (rest.count(anchor), anchor))
        rest = rest.replace(anchor, replacement)
    namespace = dict(vars(main))
    exec(compile(rest, "<mutant:submit_bug_report>", "exec"), namespace)
    return namespace["submit_bug_report"]


def _player_orders(*names):
    return [o for o in _PLAYER_ORDERS if o[0] in names]


def test_every_round_six_crash_point_reds_when_its_mechanism_is_removed(logdir):
    """THE CONTROL FOR THE TWO ROUND-6 ORDERS, one mutation per mechanism.

    Each is removed at its own site, in a compiled copy, and each removal
    has to produce the forbidden state its crash point names; each is then
    paired with an INERT TWIN at the SAME site that must leave every order
    clean (#391/#342).
    """
    # -- M1(b), CALLEE: an absence charged no barrier ----------------------
    real_due = auto_logs._unlink_due_blobs
    site = "    if unlinked or observed_absent:\n"
    bad, _, _ = _later_pass_violations(
        unlink_due=_exec_mutant(real_due, site, "    if unlinked:\n"),
        logdir=logdir)
    assert any(kind == "INV-R" for kind, *_ in bad), (
        "with an absence charged no barrier, a later pass still could not "
        "drop the row over the earlier unlink: %r" % (bad[:3],))
    twin = _exec_mutant(real_due, site, "    if observed_absent or unlinked:\n")
    for faults in ((), _LATER_REFUSES):
        bad, _, _ = _later_pass_violations(unlink_due=twin, faults=faults,
                                           logdir=logdir)
        assert bad == [], (
            "the inert twin reds at the absence's barrier: %r" % (bad[:3],))

    # -- M1(b), CALLER: an absent row collected over a refused barrier -----
    real_prune = auto_logs.prune_auto_logs
    site = "            if barrier is None:\n"
    bad, _, _ = _later_pass_violations(
        prune=_exec_mutant(real_prune, site,
                           '            if barrier is None or state == "absent":\n'),
        faults=_LATER_REFUSES, logdir=logdir)
    assert any(kind == "INV-R" for kind, *_ in bad), (
        "with `absent` collected whatever the barrier said, a later pass "
        "whose flush refused still could not drop the row: %r" % (bad[:3],))
    twin = _exec_mutant(real_prune, site, "            if not (barrier is not None):\n")
    for faults in ((), _LATER_REFUSES):
        bad, _, _ = _later_pass_violations(prune=twin, faults=faults,
                                           logdir=logdir)
        assert bad == [], (
            "the inert twin reds at the caller's barrier test: %r" % (bad[:3],))

    def _reds(handler, orders, kind):
        found = []
        for order in orders:
            found += _report_violations(order, handler=handler,
                                        logdir=logdir)[0]
        return found, any(k == kind for k, *_ in found)

    def _clean(handler):
        found = []
        for order in _PLAYER_ORDERS:
            found += _report_violations(order, handler=handler,
                                        logdir=logdir)[0]
        return found

    # -- L4: the marker stamped AFTER the attachment's bytes ---------------
    # Since round 7 the durable sequence is the body of `_store_attachment`,
    # the worker the handler hands it to; since round 8 that body runs under
    # the claim's lock (`with own.lock:`), so every anchor below sits four
    # columns deeper again, and the stamp's flag is the claim's own
    # `own.marked`. The stamp moves to the end of the durable sequence --
    # after the entry flush, before the store records itself written --
    # which is the same "after the attachment's bytes" it always meant.
    stamp = ("                        _auto_logs._stamp_marker(path)\n"
             "                        own.marked = True\n")
    entry_then_written = (
        "                        _auto_logs._fsync_dir(_pathlib.Path(path).parent)\n"
        "                        own.written = True\n")
    mutant = _report_mutant_pairs([
        (stamp, ""),
        (entry_then_written,
         "                        _auto_logs._fsync_dir(_pathlib.Path(path).parent)\n"
         + stamp + "                        own.written = True\n")])
    found, red = _reds(mutant, _player_orders("stored", "write-fails"), "INV-A")
    assert red, (
        "with the marker stamped after the attachment's bytes, no crash "
        "between the first byte and the cleanup arm left an unmarked file: "
        "%r" % (found[:3],))
    twin = _report_mutant_pairs([(stamp,
        "                        _auto_logs._stamp_marker(_pathlib.Path(str(path)))\n"
        "                        own.marked = True\n")])
    assert _clean(twin) == [], "the inert twin reds at the marker's order"

    # -- L5: the flush's FileNotFoundError read as the unlink's ------------
    arms = ("                            try:\n"
            "                                os.unlink(str(attempted_path))\n"
            "                            except FileNotFoundError:\n")
    mutant = _report_mutant_pairs([(arms,
        "                            try:\n"
        "                                os.unlink(str(attempted_path))\n"
        "                                _auto_logs._fsync_dir(\n"
        "                                    _pathlib.Path(attempted_path).parent)\n"
        "                            except FileNotFoundError:\n")])
    found, red = _reds(mutant, _player_orders("flush-vanishes"), "INV-A")
    assert red, (
        "with the flush folded back under the unlink's own arm, a flush that "
        "answered FileNotFoundError still did not leave an unreferenced, "
        "unmarked file: %r" % (found[:3],))
    twin = _report_mutant_pairs([(arms,
        "                            try:\n"
        "                                os.unlink(\"%s\" % (attempted_path,))\n"
        "                            except FileNotFoundError:\n")])
    assert _clean(twin) == [], "the inert twin reds at the two arms"

    # -- the cleanup's removal, made durable (round 5's barrier) -----------
    cleanup = ("                                    _auto_logs._fsync_dir(\n"
               "                                        _pathlib.Path(attempted_path).parent)\n")
    mutant = _report_mutant_pairs([(cleanup, "                                    pass\n")])
    found, red = _reds(mutant, _player_orders("write-fails"), "INV-A")
    assert red, (
        "with the cleanup's removal never flushed, the marker's clear still "
        "could not persist ahead of the blob's removal: %r" % (found[:3],))
    twin = _report_mutant_pairs([(cleanup,
        "                                    _auto_logs._fsync_dir(\n"
        "                                        _pathlib.Path(str(attempted_path)).parent)\n")])
    assert _clean(twin) == [], "the inert twin reds at the cleanup's barrier"

    # -- the stored attachment's CONTENTS ----------------------------------
    contents = "                            os.fsync(f.fileno())\n"
    mutant = _report_mutant_pairs([(contents, "                            pass\n")])
    found, red = _reds(mutant, _player_orders("stored"), "INV-B")
    assert red and all(k == "INV-B" for k, *_ in found), (
        "with the attachment's contents never flushed, no committed row named "
        "bytes the filesystem had not promised -- or the removal broke "
        "something other than the barrier it names: %r" % (found[:3],))
    twin = _report_mutant_pairs([(contents,
                                  "                            os.fsync(int(f.fileno()))\n")])
    assert _clean(twin) == [], "the inert twin reds at the contents barrier"

    # -- the stored attachment's directory ENTRY ---------------------------
    entry = "                        _auto_logs._fsync_dir(_pathlib.Path(path).parent)\n"
    mutant = _report_mutant_pairs([(entry, "                        pass\n")])
    found, red = _reds(mutant, _player_orders("stored"), "INV-B")
    assert red and all(k == "INV-B" for k, *_ in found), (
        "with the attachment's entry never flushed, a crash after the commit "
        "still recovered the file every time -- or the removal broke "
        "something other than the barrier it names: %r" % (found[:3],))
    twin = _report_mutant_pairs([(entry,
        "                        _auto_logs._fsync_dir(_pathlib.Path(str(path)).parent)\n")])
    assert _clean(twin) == [], "the inert twin reds at the entry barrier"


def test_one_site_performs_the_blob_before_marker_deletion():
    """#432: THE FLAG NAMED A LINE AND THE DEFECT IS A CLASS.

    A barrier between the two unlinks is worth nothing if a second site
    performs the same pair without it -- and the round-3 report flagged the
    determinate cleanup, while the orphan sweep performed the identical pair.
    There is now ONE function that deletes a blob and then its marker, and
    both callers go through it.
    """
    src = inspect.getsource(auto_logs)
    helper = inspect.getsource(auto_logs._delete_blob_then_marker)

    # WHO ASKS THE THREE-WAY QUESTION, BY NAME. Counting the calls is the
    # weaker check: it says how many there are and not which. Two callers
    # need all three answers -- the deletion pair, and retention, whose three
    # outcomes decide three different things about the ROW -- and a third
    # that appeared without this list moving is what has to red here.
    askers = sorted(name for name, obj in vars(auto_logs).items()
                    if inspect.isfunction(obj)
                    and name != "_unlink_existing"
                    and "_unlink_existing(" in inspect.getsource(obj))
    assert askers == ["_delete_blob_then_marker", "_unlink_due_blobs"], (
        "the three-way unlink is asked by %r; the two that own it are the "
        "deletion pair and retention's own pass" % (askers,))
    assert "_unlink_existing(blob_path)" in helper and "_fsync_dir(" in helper, (
        "the one deletion site no longer removes the blob and then takes the "
        "barrier before the marker")

    callers = [name for name in ("_release_marked_blob",
                                 "_resolve_marker_candidates")
               if "_delete_blob_then_marker(" in inspect.getsource(
                   getattr(auto_logs, name))]
    assert callers == ["_release_marked_blob", "_resolve_marker_candidates"], (
        "a deletion path does not go through the barriered helper: %r"
        % (callers,))

    # AND THE SWEEP REACHES IT THROUGH THAT RESOLVER AND NOWHERE ELSE, so the
    # move off the event loop did not leave a second unlink pair behind on it.
    sweep = inspect.getsource(auto_logs.prune_orphan_blobs)
    assert "_delete_blob_then_marker(" not in sweep, (
        "prune_orphan_blobs performs a deletion of its own again; the one "
        "site is _resolve_marker_candidates, on the worker thread")

    call_sites = [ln for ln in src.splitlines()
                  if ln.strip().startswith("_fsync_dir(")]
    assert len(call_sites) == 4, (
        "a directory flush is performed at %d site(s); the four that own one "
        "are the marker's stamp, the blob's write, the deletion helper and "
        "retention's unlink pass: %r" % (len(call_sites), call_sites))

    # AND EVERY SITE COERCES ITS ARGUMENT. The coercion was applied to one
    # site first and its siblings left alone, which is the half-applied shape
    # #432 names: the barrier that matters is whichever one a later reader
    # copies. Counting the SPELLING rather than naming a line means a fifth
    # site, or an uncoerced one, reds here instead of being inherited.
    #
    # `.parent` is NOT part of the invariant and this counts the two shapes
    # apart rather than pretending it is. Three sites are handed a FILE and
    # derive its directory; retention's is handed the directory itself. A
    # test that demanded `.parent` at all four would be demanding a bug at
    # the fourth (#342).
    coerced = [ln for ln in call_sites
               if ln.strip().startswith("_fsync_dir(pathlib.Path(")]
    assert len(coerced) == 4, (
        "%d of the 4 directory-flush sites coerce their argument to a Path; a "
        "site that does not is one whose barrier depends on what its caller "
        "happened to hold: %r" % (len(coerced), call_sites))
    parents = [ln for ln in coerced if ln.strip().endswith(").parent)")]
    assert len(parents) == 3, (
        "%d of the 4 sites derive a directory from a file; the three that do "
        "are the marker's stamp, the blob's write and the deletion helper, "
        "and retention's is handed the directory: %r" % (len(parents),
                                                         call_sites))

    # AND THE TWO SITES OUTSIDE THIS MODULE. `submit_bug_report` reaches the
    # same barrier twice since round 6 -- the attachment's own entry before
    # its row commits, and the cleanup arm's removal -- through `main.py`'s
    # `_pathlib` alias. Both coerce, and a third would be a site this sweep
    # has not read (#432). Comment lines are dropped first, so prose that
    # names the call is not counted as a call.
    handler = _code_of(main.submit_bug_report)
    sites = handler.count("_auto_logs._fsync_dir(")
    coerced = (handler.count("_auto_logs._fsync_dir(_pathlib.Path(")
               + handler.count("_auto_logs._fsync_dir( _pathlib.Path("))
    assert sites == 2 and coerced == 2, (
        "submit_bug_report flushes the blob directory at %d site(s), %d of "
        "them coerced; the two that own one are the attachment's entry and "
        "the cleanup's removal" % (sites, coerced))


def test_the_durability_barrier_is_charged_to_the_marked_span(logdir, verified,
                                                              monkeypatch, capsys):
    """THE BARRIER IS INSIDE THE BUDGET, AND THE CASE REDS WHEN IT IS NOT.

    A flush is not free, and on a contended volume it is not fast. Performed
    outside the marked span it would make the interval in which a row naming
    that blob can still be inserted LONGER than the T the sweep's age gate is
    derived from -- the bound would be true of the code and false of the disk.

    So both of `_write_blob`'s barriers run inside `_guarded_write`, inside
    the reserve section, and that section is awaited under the span's own
    remaining budget; the section's thread hops -- three since round 7, the
    free-space reading being the third -- spend the same budget, so a
    stalled flush ends the section's wait rather than outliving it.

    Here the blob's contents flush does not return inside T. The handler must
    REFUSE 503 inside T and commit nothing. The mutant takes the ceiling off
    the await that covers the barrier, and the request outlives T instead.
    """
    T, stall = 1.0, 4.0
    monkeypatch.setattr(auto_logs, "AUTO_LOG_MARKED_SPAN_DEADLINE_S", T)

    # STRUCTURAL FIRST: the two barriers on the write path are reached only
    # through the section's own budgeted hops. A flush performed anywhere else
    # would be outside the span whatever this case measures.
    section = _normalise(inspect.getsource(auto_logs._reserve_stamp_and_write))
    # THREE HOPS SINCE ROUND 7: the free-space reading joined the stamp and
    # the write on a worker thread (M3's class), and it spends the span the
    # same way, so the count is one per hop rather than the two barriers'.
    # Since round 8 each is a `_hop` on the module's volume pool (R7-M4), and
    # the ceiling it is given is the span's own remaining budget.
    hops = ("_free_bytes", "_guarded_stamp", "_guarded_write")
    for hop in hops:
        assert ("_hop(_VOLUME_POOL, _span_budget(span_deadline), %s," % hop
                ) in section, (
            "the %s hop is not awaited under the span's ceiling on the volume "
            "pool, so the call it makes on the volume is not charged to the "
            "span" % hop)
    assert section.count("_span_budget(span_deadline)") == len(hops), (
        "the section's hops do not each spend the span's own deadline")
    assert "_fsync_dir(" in inspect.getsource(auto_logs._write_blob), (
        "the blob's directory barrier is no longer inside the function the "
        "section's write hop calls")

    opened = {}
    stalled = []

    def rec_open(path, flags, mode=0o666):
        fd = os.open(str(path), flags, mode)
        opened[fd] = str(path)
        return fd

    def slow_fsync(fd):
        """The BLOB's flush is the one that does not return; every other
        flush on this path costs nothing.

        Neither arm performs a real `os.fsync`. What this case measures is
        where a flush's cost is CHARGED, and a real flush of a temporary
        volume on this seat has been measured at whole seconds under load --
        which would put the marker's own two flushes inside T and leave the
        case timing those instead of the one it stalls. Whether the flushes
        actually make anything durable is the crash simulation's question,
        not this one's.
        """
        if opened.get(fd, "").endswith(".log.gz"):
            stalled.append(opened[fd])
            time.sleep(stall)

    def _attempt(db, handler=None):
        """What the HANDLER took, not what the loop took to drain.

        A stalled flush leaves a worker thread running after the handler has
        answered, and nothing takes a thread back once it has picked the
        work up. Round 7's hops ran on the loop's default executor, which
        `asyncio.run` waits for on its way to closing the loop, so timing the
        run measured that teardown and reported a deadline as missed on a
        request that met it; since round 8 they run on the module's volume
        pool, which the loop does not wait for, and the timing rule is kept
        anyway. The clock starts and stops inside the loop, around the
        handler's own await, so what it reads is the request's answer and
        nothing else.
        """
        monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
        auto_logs._BLOB_WRITE_STARTED[0] = 0.0
        opened.clear()
        seen = {}

        async def call():
            started = time.monotonic()
            try:
                await (handler or auto_logs.upload_auto_log)(_request(), db)
                seen["refused"] = False
            except HTTPException:
                seen["refused"] = True
            seen["took"] = time.monotonic() - started

        real_os = auto_logs.os
        auto_logs.os = _OsProxy(open=rec_open, fsync=slow_fsync)
        try:
            _run(call())
        finally:
            auto_logs.os = real_os
        return seen["refused"], seen["took"]

    # LIVE: a flush that does not return inside T ends the span.
    db = _ok_db()
    refused, took = _attempt(db)
    assert stalled, (
        "the blob's flush was never reached, so this case refused for some "
        "other reason and says nothing about the barrier's cost")
    assert refused and took < stall / 2.0, (
        "a blob flush that does not return inside T did not end the span: "
        "refused=%r after %.2fs (deadline %.2fs)" % (refused, took, T))
    assert db.committed == 0, (
        "the row committed over a blob whose bytes the filesystem had not "
        "promised")
    out = capsys.readouterr().out
    assert "the measure-and-write for" in out and "deadline" in out, out

    # MUTANT at the handler's own site: the section -- which is where both of
    # the write path's barriers are performed -- is awaited with no ceiling,
    # so the flush's cost is no longer charged to T and the request outlives
    # the bound the sweep's age gate is derived from.
    SPAN_SITE = ("            await asyncio.wait_for(asyncio.shield(section),\n"
                 "                                   _span_budget(span_deadline))\n")
    db = _ok_db()
    _refused, took = _attempt(db, _handler_mutant(
        [(SPAN_SITE, "            await asyncio.shield(section)\n")]))
    assert took >= stall / 2.0, (
        "with the ceiling off the await that covers the barrier the handler "
        "still answered in %.2fs, so the case above says nothing about where "
        "the flush is charged" % (took,))

    # INERT TWIN at the SAME site: the same ceiling, the same budget, spelled
    # differently.
    db = _ok_db()
    refused, took = _attempt(db, _handler_mutant([(
        SPAN_SITE,
        "            await asyncio.wait_for(asyncio.shield(section),\n"
        "                                   _span_budget(float(span_deadline)))\n")]))
    assert refused and took < stall / 2.0, (
        "the inert twin changed the outcome (%.2fs), so the mutant above is "
        "reacting to the site being edited rather than to the ceiling"
        % (took,))
    auto_logs._MARKERS_IN_FLIGHT.clear()


def test_a_cancelled_sections_cleanup_does_not_block_the_event_loop(
        logdir, verified, monkeypatch):
    """R3-L2: THE CLEANUP WAITS IN A THREAD, NOT ON THE LOOP.

    The section's cleanup takes the blob's lock, and a worker can hold that
    lock through the write and its two flushes. Taken on the event loop, that
    wait stops every other request this worker is serving -- and the one
    caller that reaches it while a write may still be in flight is a CANCELLED
    section: loop close, or the container's SIGTERM during a rebuild, which is
    when the loop can least afford to stop.

    Measured rather than reasoned about: a heartbeat coroutine runs on the
    same loop and has to keep ticking while the cleanup waits out a write that
    holds the lock.
    """
    import threading

    hold = 1.0
    inside = threading.Event()

    def slow_guarded_write(own, data):
        with own.lock:
            inside.set()
            time.sleep(hold)

    real_section = auto_logs._reserve_stamp_and_write

    def drive(mutation=None, label="live"):
        # THE STAMP IS STUBBED, AND ONLY BECAUSE OF WHAT IT COSTS HERE. This
        # case is about which thread waits for the blob's lock, not about the
        # marker; and a real `_stamp_marker` fsyncs the marker and then its
        # directory on a temporary volume, which on this seat has been
        # measured at whole seconds under load. That would make the section
        # spend its wait inside the stamp and this case would time a flush
        # rather than the cleanup it is about. The crash simulation is where
        # the stamp's own barriers are the subject.
        monkeypatch.setattr(auto_logs, "_guarded_stamp", lambda own: None)
        monkeypatch.setattr(auto_logs, "_guarded_write", slow_guarded_write)
        monkeypatch.setattr(auto_logs, "_free_bytes", lambda d: 10 ** 12)
        monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
        auto_logs._BLOB_WRITE_STARTED[0] = 0.0
        # COMPILED AFTER THE PATCHES, so the copy's globals carry this
        # section's own lock and stubbed worker rather than the module's.
        fn = (real_section if mutation is None
              else _exec_mutant(real_section, *mutation))
        inside.clear()
        beats = [0]

        async def run():
            stop = asyncio.Event()

            async def heartbeat():
                while not stop.is_set():
                    beats[0] += 1
                    await asyncio.sleep(0.01)

            own = auto_logs._MarkedBlob(
                pathlib.Path(str(logdir)) /
                "ffffffff-0000-4000-8000-00000000ab1e.log.gz")
            beat = asyncio.ensure_future(heartbeat())
            task = asyncio.ensure_future(fn(
                own, b"payload", STEAM,
                time.monotonic() + auto_logs.AUTO_LOG_MARKED_SPAN_DEADLINE_S))
            # THE WAIT FOR THE WORKER IS BOUNDED BY THE CLOCK, NOT BY A COUNT
            # OF SLEEPS. Two thread hops lie between the task's start and the
            # worker taking the blob's lock (the stubbed stamp, then the
            # write), and a count of 400 five-millisecond sleeps ran out in 2
            # of 4 full suite runs on this seat while other suites ran beside
            # it, with the worker not yet at the lock -- and passed 3 of 3
            # runs on its own. Nothing this case measures happens inside this
            # wait: the heartbeat is sampled only after it, so a longer bound
            # changes how long a loaded machine is given, never what is
            # asserted. A section that refuses early still ends it at once.
            reach_by = time.monotonic() + 30.0
            while time.monotonic() < reach_by:
                if inside.is_set() or task.done():
                    break
                await asyncio.sleep(0.005)
            if not inside.is_set() and task.done():
                # SURFACE IT. A section that refused before reaching the write
                # would leave this case asserting about a loop that had
                # nothing to be blocked by, which is a control that cannot
                # fail rather than one that passed (#342).
                task.result()
            assert inside.is_set(), (
                "the worker never reached the blob's lock (%s)" % (label,))
            before = beats[0]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            during = beats[0] - before
            stop.set()
            await beat
            auto_logs._MARKERS_IN_FLIGHT.clear()
            return during

        return _run(run())

    # LIVE: the cleanup waits out the write in a thread and the loop keeps
    # answering.
    during = drive()
    assert during >= 10, (
        "the event loop ticked %d times while a cancelled section's cleanup "
        "waited out a %.1fs write; it was blocked on the worker's lock"
        % (during, hold))

    # MUTANT at the cleanup's own site: taken on the loop, which is the tree
    # before this fix, with the volume handed on straight after it -- the
    # order the live code keeps by chaining the hand-on to the cleanup. The
    # heartbeat stops.
    site = ("                gone = await _release_marked_blob_off_loop("
            "own, then=_hand_on)\n")
    during = drive((site, "                gone = _release_marked_blob(own)\n"
                          "                _hand_on()\n"),
                   label="mutant")
    assert during <= 2, (
        "the loop kept ticking (%d) with the cleanup taken synchronously, so "
        "the live assertion above proves nothing" % (during,))

    # INERT TWIN at the SAME site: the same await, parenthesised.
    during = drive(
        (site,
         "                gone = (await _release_marked_blob_off_loop("
         "own, then=_hand_on))\n"),
        label="inert twin")
    assert during >= 10, (
        "the inert twin blocked the loop, so the mutant above is reacting to "
        "the site being edited rather than to where the wait happens: %d"
        % (during,))


def test_the_sweep_reports_cleared_only_when_the_marker_unlink_succeeded(
        logdir, capsys):
    """R3-L3: A DISPOSITION IS WHAT HAPPENED, NOT WHAT WAS ATTEMPTED.

    Three arms discarded the unlink's answer about a marker: the one that
    clears it over a committed row, and the two that clear it after resolving
    the blob. A marker a permission or I/O fault leaves on the volume then
    came back every tick under a line saying it had been cleared -- and "is
    the leak draining" is exactly the reading an operator takes from that line
    (#304).

    Three candidates, one unlink fault, three dispositions: referenced ->
    `uncleared`; blob removed and the marker kept -> still `removed`, with the
    surviving marker counted; no blob and no clearable marker -> nothing
    reclaimed OR cleared, so `unremovable`.
    """
    referenced = "11111111-0000-4000-8000-000000000001.log.gz"
    removable = "11111111-0000-4000-8000-000000000002.log.gz"
    blankonly = "11111111-0000-4000-8000-000000000003.log.gz"

    def _plant():
        for nm in (referenced, removable):
            (logdir / nm).write_bytes(b"x" * 16)
        for nm in (referenced, removable, blankonly):
            _mark(logdir, nm, age_s=90_000)
        # A pass that cannot resolve a candidate now PARKS it, so the three
        # runs below would otherwise each see a smaller population than the
        # one this case plants.
        auto_logs._ORPHAN_HELD.clear()

    def refusing_unlink(path):
        if str(path).endswith(auto_logs._ORPHAN_MARKER_SUFFIX):
            raise PermissionError("the volume will not give this up")
        return os.unlink(str(path))

    def _sweep(mutation=None):
        real_os = auto_logs.os
        real_resolver = auto_logs._resolve_marker_candidates
        auto_logs.os = _OsProxy(unlink=refusing_unlink)
        if mutation is not None:
            # The two unlinks moved onto the worker thread with the rest of
            # the pass's filesystem work, so the arm this case mutates lives
            # in the resolver and the sweep reaches it by module attribute.
            auto_logs._resolve_marker_candidates = _point_at(
                _exec_mutant(real_resolver, *mutation), auto_logs.os)
        try:
            return _run(auto_logs.prune_orphan_blobs(
                KindRows([(referenced, "report")]), min_age_s=3600))
        finally:
            auto_logs.os = real_os
            auto_logs._resolve_marker_candidates = real_resolver

    _plant()
    capsys.readouterr()
    out = _sweep()
    printed = capsys.readouterr().out
    assert out["cleared"] == 0 and out["uncleared"] == 1, (
        "a marker over a committed row that would not unlink was reported as "
        "cleared: %r" % (out,))
    assert out["unlinked"] == 1 and out["markers_kept"] == 1, (
        "the blob was reclaimed and its surviving marker is not reported: %r"
        % (out,))
    assert out["marker_only"] == 0 and out["unremovable"] == 1, (
        "a candidate whose marker would not unlink and whose blob was never "
        "there was reported as cleared: %r" % (out,))
    assert (out["unlinked"] + out["marker_only"] + out["unremovable"]
            + out["deferred"]) == out["orphans"], out
    assert "could NOT be removed and SURVIVES" in printed, printed
    assert "nothing was reclaimed or cleared" in printed, printed
    assert ("cleared %s=%s" % (auto_logs._ORPHAN_MARKER, blankonly)
            not in printed), (
        "a marker that is still on the volume was reported as cleared:\n%s"
        % printed)

    # MUTANT: the marker-only arm stops reading the unlink result, which is
    # the tree before this fix -- a marker that survived reads as cleared.
    site = ('        stuck = (state == "failed") or '
            '(state == "absent" and not marker_gone)\n')
    _plant()
    out = _sweep((site, '        stuck = (state == "failed")\n'))
    assert out["marker_only"] == 1 and out["unremovable"] == 0, (
        "the mutant did not report the surviving marker as cleared, so the "
        "live assertion above proves nothing: %r" % (out,))

    # INERT TWIN at the SAME site: the same condition, spelled out.
    _plant()
    out = _sweep((site, '        stuck = state == "failed" or '
                        '(state == "absent" and marker_gone is False)\n'))
    assert out["marker_only"] == 0 and out["unremovable"] == 1, (
        "the inert twin changed the outcome, so the mutant above is reacting "
        "to the site being edited rather than to the unlink result: %r"
        % (out,))


def test_a_player_attachment_is_marked_before_its_first_byte(logdir,
                                                             monkeypatch):
    """L4: THE PLAYER-FILED ATTACHMENT TAKES THE UPLOAD PATH'S OWN ORDER.

    `open()` can succeed and the write fail, and a process or host stop
    between the two leaves a prefix of the gzip stream on the volume. Before
    round 6 that prefix carried no marker and no row named it, and the orphan
    sweep -- which walks the marker set -- and `prune_auto_logs` -- which
    walks kind='auto' rows -- were both blind to it. Permanent, on the volume
    this route is most protective of.

    What is measured is the ORDER: the marker's own file is on the volume
    before the attachment is opened, and it is gone once the row naming the
    file has committed.
    """
    import builtins
    real_open = builtins.open
    seen = {}

    def watching_open(*a, **kw):
        if len(a) > 1 and "w" in str(a[1]) and str(a[0]).endswith(".log.gz"):
            seen["markers_at_open"] = _markers(logdir)
            seen["blobs_at_open"] = _blobs(logdir)
        return real_open(*a, **kw)

    monkeypatch.setattr(main, "_is_admin", _no_admin)
    monkeypatch.setattr(main, "_mark_mod_seen", _noop_mark)
    monkeypatch.setattr(builtins, "open", watching_open)
    db = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
    req = schemas.BugReportRequest(steam_id=STEAM, description="it broke",
                                   log_text="a log worth keeping")
    out = _run(main.submit_bug_report(req, _request(), db))
    monkeypatch.setattr(builtins, "open", real_open)

    assert out["log_persisted"] is True
    blob = db.added[0].log_filename
    assert seen.get("blobs_at_open") == [], (
        "the attachment already had bytes when the order was sampled, so "
        "this case is not looking at the window it claims to: %r" % (seen,))
    assert seen.get("markers_at_open") == [
        blob + auto_logs._ORPHAN_MARKER_SUFFIX], (
        "the attachment was opened before anything named it, so a stop "
        "between the first byte and the cleanup arm leaves a file no sweep "
        "in this tree can find: %r" % (seen,))
    assert _markers(logdir) == [], (
        "the marker outlived the committed row: %r" % (_markers(logdir),))
    assert _blobs(logdir) == [blob]
    # AND THE NAME IS NOT LEFT IN THE IN-FLIGHT SET. It is registered for the
    # span between the stamp and the commit, in a `finally`, so a handler
    # that raises cannot leave the sweep skipping the name for the life of
    # the process.
    assert blob not in auto_logs._MARKERS_IN_FLIGHT, (
        "the attachment is still registered as in flight after the request "
        "finished")


def test_a_player_attachment_whose_commit_fails_keeps_its_marker(logdir,
                                                                 monkeypatch):
    """L4's other side: the marker is cleared AFTER the reference commits.

    Clearing it before would reopen the window it exists to close. A commit
    that raises leaves an attachment on the volume with no row naming it, and
    the marker is the only thing that will ever offer it to a collector -- so
    that path drops the in-flight registration and KEEPS the marker.
    """
    class _FailingCommit(_ReportSession):
        async def commit(self):
            raise RuntimeError("the transaction could not be committed")

    monkeypatch.setattr(main, "_is_admin", _no_admin)
    monkeypatch.setattr(main, "_mark_mod_seen", _noop_mark)
    db = _FailingCommit({"FROM bug_reports": [[{"count": 0}]]})
    req = schemas.BugReportRequest(steam_id=STEAM, description="it broke",
                                   log_text="a log worth keeping")
    with pytest.raises(RuntimeError):
        _run(main.submit_bug_report(req, _request(), db))

    blobs = _blobs(logdir)
    assert len(blobs) == 1, blobs
    assert _markers(logdir) == [blobs[0] + auto_logs._ORPHAN_MARKER_SUFFIX], (
        "the attachment's marker was cleared although no row names the file, "
        "so nothing will ever collect it: %r" % (_markers(logdir),))
    assert blobs[0] not in auto_logs._MARKERS_IN_FLIGHT, (
        "the blob is still owned by a request that is over, so the sweep "
        "skips it for the life of the process")


def _partial_write_open(real_open):
    """An `open` whose blob handle takes eight bytes and then refuses.

    The failure the cleanup arm exists for: `open()` returned, some of the
    gzip stream is on the volume, and the write did not finish.
    """
    def opener(*a, **kw):
        if len(a) > 1 and "w" in str(a[1]) and str(a[0]).endswith(".log.gz"):
            fh = real_open(*a, **kw)

            class _Partial:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *e):
                    fh.close()
                    return False

                def write(self_inner, data):
                    fh.write(data[:8])
                    fh.flush()
                    raise OSError("no space left on device")

            return _Partial()
        return real_open(*a, **kw)
    return opener


def test_a_flush_that_refuses_after_the_unlink_keeps_the_attachments_reference(
        logdir, monkeypatch, capsys):
    """L5: `FileNotFoundError` FROM THE FLUSH IS NOT `FileNotFoundError` FROM
    THE UNLINK.

    Both statements used to sit under one `except FileNotFoundError`, which
    reads the first as "no file was created". `FileNotFoundError` is an
    `OSError`, so a directory flush raising it AFTER a successful unlink --
    the subtree replaced under a recovering mount, the container losing it --
    landed in that arm and committed `log_bytes = 0`: the claim that nothing
    is on the volume, made over a removal the filesystem never promised and a
    recovery can undo.

    Read separately the two say opposite things. The unlink's own
    FileNotFoundError means the file never existed and the reference may
    drop; a flush failure of ANY kind means the removal cannot be proved and
    the reference STAYS (#430/#276).
    """
    import builtins
    real_open = builtins.open
    calls = []

    def flush_vanishes(directory):
        calls.append(str(directory))
        if len(calls) > 1:          # the first is the marker's own stamp
            raise FileNotFoundError(str(directory))

    monkeypatch.setattr(main, "_is_admin", _no_admin)
    monkeypatch.setattr(main, "_mark_mod_seen", _noop_mark)
    monkeypatch.setattr(auto_logs, "_fsync_dir", flush_vanishes)
    monkeypatch.setattr(builtins, "open", _partial_write_open(real_open))
    db = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
    req = schemas.BugReportRequest(steam_id=STEAM, description="it broke",
                                   log_text="a log worth keeping")
    capsys.readouterr()
    out = _run(main.submit_bug_report(req, _request(), db))
    printed = capsys.readouterr().out
    monkeypatch.setattr(builtins, "open", real_open)
    row = db.added[0]

    assert out["log_persisted"] is False
    assert row.log_filename is not None, (
        "a FileNotFoundError from the DIRECTORY FLUSH was read as `no file "
        "was created`, so the row disclaims a removal nothing promised")
    assert row.log_bytes is None, (
        "log_bytes = %r claims the volume is clean over a removal that could "
        "not be proved" % (row.log_bytes,))
    assert "would NOT flush" in printed, printed

    # CONTROL: the same arm with a flush that SUCCEEDS. The reference drops
    # and log_bytes is 0, which is the reading the case above must not give
    # -- without this, a handler that never drops a reference at all would
    # satisfy every assertion so far.
    monkeypatch.setattr(auto_logs, "_fsync_dir", lambda d: None)
    monkeypatch.setattr(builtins, "open", _partial_write_open(real_open))
    db2 = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
    _run(main.submit_bug_report(req, _request(), db2))
    monkeypatch.setattr(builtins, "open", real_open)
    row2 = db2.added[0]
    assert row2.log_filename is None and row2.log_bytes == 0, (
        "the control did not drop the reference, so the case above is not "
        "about the flush: filename=%r bytes=%r"
        % (row2.log_filename, row2.log_bytes))

    # AND THE MUTANT THAT COLLAPSES THE TWO ARMS REDS. The `else:` is what
    # separates them; folding the flush back under the unlink's own `try`
    # puts its FileNotFoundError into the "no file was created" arm again.
    #
    # Four columns deeper since round 8: the removal is the body of
    # `_discard_partial`, under the claim's lock.
    src = inspect.getsource(main.submit_bug_report)
    assert src.count("\n                            except FileNotFoundError:\n") == 1, (
        "the unlink's FileNotFoundError arm is not where this case thinks "
        "it is")
    assert "\n                                except OSError as fx:\n" in src, (
        "the flush no longer has an except arm of its own, so a flush that "
        "refuses is being read as an unlink that found nothing")


def _worker_wait_findings(doc):
    """Which of the worker-wait facts the prose does NOT state.

    A list rather than a bare assertion, so the case below can run it over a
    PLANTED regression as well as over the live docstring: a prose control
    that has never been shown to fail is decoration (#391).
    """
    # NORMALISED FIRST. Every phrase below is a sentence fragment and the
    # prose wraps at seventy-odd columns, so a raw substring test would be
    # asking where the line breaks fall rather than what the prose says --
    # a check that fails on a reflow and passes on a deletion.
    flat = " ".join(doc.split())
    missing = []
    if not ("bounds the WAITER and never the work" in flat
            and "cannot take a thread back" in flat):
        missing.append("the ceiling bounds the waiter and never the work")
    if "handed on only when the cleanup has actually run" not in flat:
        missing.append("the volume is handed on when the cleanup has run")
    if "does not depend on a time bound" not in flat:
        missing.append("the safety property needs no time bound")
    lower = flat.lower()
    if any(claim in lower for claim in ("bounds the work", "bounds the cleanup",
                                        "stops the cleanup",
                                        "cancels the cleanup")):
        missing.append("the prose claims the ceiling bounds the work")
    return missing


def test_the_worker_wait_prose_states_its_facts_and_the_code_agrees():
    """R4-L7, NAMED AT THE PROSE IT IS ABOUT -- RE-DERIVED IN ROUND 8.

    Round 5 recorded this closure against a case that reads the retention
    loop's signals, which is a different docstring; the prose in question is
    `_release_marked_blob_off_loop`'s, where one sentence claiming a bound
    that did not exist was replaced by separate facts. Each is checked
    against the prose AND against the code beneath it, because a docstring
    that agrees with nothing is the claim #351 is about.

    ROUND 8 CHANGED ONE OF THE FACTS, SO THE CHECK CHANGED WITH IT. Until
    R7-M4 the wait had no ceiling and the prose's facts were that nothing
    bounded it and the stall ceiling refused only LATER arrivals. Since R7-M4
    the WAIT has a ceiling of its own, and the facts the prose must now
    state are the ones that stay true under it: the ceiling bounds the
    waiter and never the work, the volume is handed on when the cleanup has
    actually run and not when the wait gave up, and the safety property
    needs no time bound at all. What it must never claim is the round-4
    mistake in its new form -- that the ceiling bounds the WORK.
    """
    doc = inspect.getdoc(auto_logs._release_marked_blob_off_loop) or ""
    assert _worker_wait_findings(doc) == [], (
        "the worker-wait prose no longer states: %r"
        % (_worker_wait_findings(doc),))

    # THE REDDENING CONTROL: the kind of sentence this prose replaced,
    # planted back in its round-8 form -- a bound claimed for the work.
    planted = " ".join(doc.split()).replace(
        "does not depend on a time bound at all",
        "is held by the ceiling, which bounds the cleanup")
    assert planted != " ".join(doc.split()), (
        "the planted regression changed nothing")
    assert len(_worker_wait_findings(planted)) == 2, (
        "the check does not see a docstring that claims the bound it exists "
        "to deny, so it cannot fail: %r" % (_worker_wait_findings(planted),))

    # AND THE CODE AGREES WITH EACH FACT. The cleanup runs on a thread of the
    # volume pool; the wait for it is shielded, so its ceiling cannot cancel
    # the work; the caller's `then` is chained to the cleanup's own end; and
    # the stall ceiling is not read here, because it decides whether LATER
    # arrivals queue, which is the section's question.
    body = inspect.getsource(auto_logs._release_marked_blob_off_loop
                             ).split('"""')[-1]
    assert "_start(_VOLUME_POOL, _release_marked_blob, own)" in body, (
        "the function no longer performs the cleanup on a thread of the "
        "volume pool, so the prose is about a mechanism that is gone: %s"
        % body)
    assert "asyncio.shield(cleanup)" in body and "wait_for" in body, (
        "the wait is no longer a ceiling over the SHIELDED cleanup, so "
        "either the wait is unbounded again or the ceiling can cancel the "
        "work the prose says it never touches: %s" % body)
    assert "cleanup.add_done_callback(then)" in body, (
        "the caller's hand-on is no longer chained to the cleanup's own end: "
        "%s" % body)
    assert "_BLOB_WRITE_STALL_S" not in body, (
        "the stall ceiling is read here; it decides whether LATER arrivals "
        "queue, which is the section's question and not this wait's: %s"
        % body)
    # THE SAFETY PROPERTY THE PROSE RESTS ON, at the function that holds it.
    inner = inspect.getsource(auto_logs._release_marked_blob)
    assert "with own.lock:" in inner and "own.discarded = True" in inner, (
        "the lock and the discarded flag are what make the wait's length a "
        "cost rather than a state, and the cleanup no longer takes them")


def _report_mutant(anchor, replacement):
    """`main.submit_bug_report`'s body with one edit, compiled WITHOUT its
    route decorator -- executing it would register a second copy of the route
    on the live application. The anchor is asserted to be one site inside the
    handler's own span first (#432/#279)."""
    src = textwrap.dedent(inspect.getsource(main.submit_bug_report))
    head, _, rest = src.partition("\n")
    assert head.startswith("@app.post("), (
        "submit_bug_report no longer starts with its route decorator, so this "
        "harness is stripping the wrong line: %r" % (head,))
    assert rest.count(anchor) == 1, (
        "the mutation anchor occurs %d time(s) in submit_bug_report, not once"
        % rest.count(anchor))
    namespace = dict(vars(main))
    exec(compile(rest.replace(anchor, replacement),
                 "<mutant:submit_bug_report>", "exec"), namespace)
    return namespace["submit_bug_report"]


def test_a_failed_player_attachment_write_leaves_nothing_on_the_volume(
        logdir, monkeypatch, capsys):
    """R3-L4: THE PARTIAL FILE GOES BEFORE THE ROW COMMITS.

    `submit_bug_report` opens the attachment, writes it, and records
    `log_bytes = 0` when that fails -- with `log_filename` deliberately NULL,
    because there is genuinely nothing to download. A write that fails AFTER
    creating the file therefore left a prefix of the gzip stream on the volume
    under a name no row carries.

    Nothing in this tree collected that. A player-filed attachment used to
    receive no orphan-candidate marker, which is what the automatic path's
    sweep takes as its population, and `prune_auto_logs` walks kind='auto'
    ROWS. So the file was permanent, on the volume this route is most
    protective of -- and the row still has to say a log was attached and lost,
    which is the other half this arm exists for.

    SINCE ROUND 6 THE MARKER IS THE FLOOR UNDER THIS ARM and this arm is
    still the plan: the marker makes a prefix DISCOVERABLE after an hour, the
    arm removes it now and decides what the row claims. The marker assertion
    below is therefore no longer "none was given" but "the one that was given
    is cleared once the row has committed" -- if it survived, every sweep for
    the next six hours would re-ask the database about a file that is gone.
    """
    import builtins
    real_open = builtins.open

    def partial_then_fail(*a, **kw):
        if len(a) > 1 and "w" in str(a[1]):
            fh = real_open(*a, **kw)

            class _Partial:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *e):
                    fh.close()
                    return False

                def write(self_inner, data):
                    fh.write(data[:8])
                    fh.flush()
                    raise OSError("no space left on device")

            return _Partial()
        return real_open(*a, **kw)

    def _file(handler=None):
        monkeypatch.setattr(main, "_is_admin", _no_admin)
        monkeypatch.setattr(main, "_mark_mod_seen", _noop_mark)
        monkeypatch.setattr(builtins, "open", partial_then_fail)
        db = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
        req = schemas.BugReportRequest(steam_id=STEAM, description="it broke",
                                       log_text="a log worth keeping")
        try:
            return _run((handler or main.submit_bug_report)(
                req, _request(), db)), db
        finally:
            monkeypatch.setattr(builtins, "open", real_open)

    capsys.readouterr()
    out, db = _file()
    printed = capsys.readouterr().out
    row = db.added[0]

    assert out["log_persisted"] is False
    assert row.log_filename is None and row.log_bytes == 0, (
        "the row no longer records that a log was attached and lost: "
        "filename=%r bytes=%r" % (row.log_filename, row.log_bytes))
    assert _blobs(logdir) == [], (
        "a partial player-filed attachment survived its own failed write. It "
        "carries no marker, so no sweep in this tree would ever name it: %r"
        % (_blobs(logdir),))
    assert _markers(logdir) == [], (
        "the attachment's marker outlived the committed row, so every sweep "
        "for the next hours re-asks the database about a file that is gone: "
        "%r" % (_markers(logdir),))
    assert "the partial file was removed" in printed, printed

    # MUTANT at the unlink's own site: dropped, which is the tree before this
    # fix. The prefix stays on the volume with nothing naming it.
    #
    # Four columns deeper since round 8: the removal is the body of
    # `_discard_partial`, under the claim's lock.
    site = "\n                                os.unlink(str(attempted_path))\n"
    _file(_report_mutant(site, "\n                                pass\n"))
    left = _blobs(logdir)
    assert left, (
        "the mutant left nothing behind, so the live assertion above proves "
        "nothing about the unlink")
    for stale in left:
        (logdir / stale).unlink()

    # INERT TWIN at the SAME site: the same unlink, the path spelled out.
    _file(_report_mutant(site,
                         '\n                                os.unlink("%s" % '
                         '(attempted_path,))\n'))
    assert _blobs(logdir) == [], (
        "the inert twin left the partial file behind, so the mutant above is "
        "reacting to the site being edited: %r" % (_blobs(logdir),))


def test_a_player_attachment_whose_partial_cannot_be_removed_keeps_the_reference(
        logdir, monkeypatch, capsys):
    """R3-L4, THE ARM THAT WAS LEFT AS A RESIDUE.

    The removal above can itself fail -- a permission fault, a volume error.
    The row used to drop the name anyway and commit `log_bytes = 0`, which
    says "a log was attached and nothing is on the volume" over a file that
    is still there. A player-filed attachment carries no orphan-candidate
    marker and `prune_auto_logs` walks kind='auto' rows, so that file was
    outside every collector in this tree, for good.

    What closes it is not another collector: it is not dropping the
    reference. The row NAMES the file, so it is an ordinary attachment of
    this report -- an admin sees it, the report's own lifecycle governs it --
    and `log_bytes` stays NULL rather than 0, because 0 is the claim this arm
    cannot make. The client is still told `log_persisted: false`, because
    what is on the volume is a truncated gzip.
    """
    import builtins
    real_open = builtins.open

    def partial_then_fail(*a, **kw):
        if len(a) > 1 and "w" in str(a[1]):
            fh = real_open(*a, **kw)

            class _Partial:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *e):
                    fh.close()
                    return False

                def write(self_inner, data):
                    fh.write(data[:8])
                    fh.flush()
                    raise OSError("no space left on device")

            return _Partial()
        return real_open(*a, **kw)

    real_unlink = os.unlink

    def refusing_unlink(path, *a, **kw):
        if str(path).endswith(".log.gz"):
            raise PermissionError("read-only file system")
        return real_unlink(path, *a, **kw)

    monkeypatch.setattr(main, "_is_admin", _no_admin)
    monkeypatch.setattr(main, "_mark_mod_seen", _noop_mark)
    monkeypatch.setattr(builtins, "open", partial_then_fail)
    monkeypatch.setattr(main, "os", _OsProxy(unlink=refusing_unlink))
    db = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
    req = schemas.BugReportRequest(steam_id=STEAM, description="it broke",
                                   log_text="a log worth keeping")
    capsys.readouterr()
    out = _run(main.submit_bug_report(req, _request(), db))
    printed = capsys.readouterr().out
    monkeypatch.setattr(builtins, "open", real_open)
    row = db.added[0]

    left = _blobs(logdir)
    assert len(left) == 1, (
        "the unlink was supposed to refuse, so the partial file should still "
        "be on the volume: %r" % (left,))
    assert row.log_filename == left[0], (
        "the row dropped the name of a file that is still on the volume, "
        "which is the residue no tick in this tree can reach: filename=%r "
        "volume=%r" % (row.log_filename, left))
    assert row.log_bytes is None, (
        "log_bytes = %r claims nothing is on the volume, over a file that is"
        % (row.log_bytes,))
    assert out["log_persisted"] is False, (
        "the client was told the log persisted over a truncated gzip: %r"
        % (out,))
    assert "NOT be removed" in printed and "NAMES it" in printed, printed

    # MUTANT at the decision's own site: the reference is dropped again, which
    # is the tree before this fix.
    #
    # THE ANCHOR CARRIES THE LINE UNDER IT. Since round 6 the flush arm has
    # its own `keep_reference = True` one level deeper, and this one's
    # thirty-two spaces (inside `_discard_partial` since round 7, under
    # its claim's lock since round 8) are a SUBSTRING of that one's
    # thirty-six -- so the bare assignment matches two sites and
    # `_report_mutant` refuses it. The message line that follows is what
    # makes it the unlink's arm and not the flush's (#432/#279).
    for stale in _blobs(logdir):
        real_unlink(str(logdir / stale))
    monkeypatch.setattr(builtins, "open", partial_then_fail)
    site = ("                                keep_reference = True\n"
            "                                removed = (f\"the partial file "
            "{attempted_path.name} could \"\n")
    mutant = _report_mutant(
        site,
        "                                keep_reference = False\n"
        "                                removed = (f\"the partial file "
        "{attempted_path.name} could \"\n")
    db2 = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
    _run(mutant(req, _request(), db2))
    monkeypatch.setattr(builtins, "open", real_open)
    row2 = db2.added[0]
    assert row2.log_filename is None and row2.log_bytes == 0, (
        "the mutant did not drop the reference, so the live assertion above "
        "proves nothing: filename=%r bytes=%r"
        % (row2.log_filename, row2.log_bytes))
    assert _blobs(logdir), (
        "the mutant left nothing on the volume, so there was no reference to "
        "keep in the first place")

    # INERT TWIN at the SAME site: the same decision, spelled differently.
    for stale in _blobs(logdir):
        real_unlink(str(logdir / stale))
    monkeypatch.setattr(builtins, "open", partial_then_fail)
    twin = _report_mutant(
        site,
        "                                keep_reference = bool(1)\n"
        "                                removed = (f\"the partial file "
        "{attempted_path.name} could \"\n")
    db3 = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
    _run(twin(req, _request(), db3))
    monkeypatch.setattr(builtins, "open", real_open)
    row3 = db3.added[0]
    assert row3.log_filename is not None and row3.log_bytes is None, (
        "the inert twin changed the outcome, so the mutant above is reacting "
        "to the site being edited rather than to the decision: filename=%r "
        "bytes=%r" % (row3.log_filename, row3.log_bytes))


def test_the_player_attachment_cleanup_makes_its_removal_durable(
        logdir, monkeypatch, capsys):
    """R3-L4's OTHER half: the removal is a PERSISTENCE order too.

    Unlinking the partial file before the row commits is a call order. An
    entry removal is not durable until the directory is flushed, so a host
    that stops after the commit can recover the file with the row already
    saying `log_bytes = 0` over it -- the same unreferenced prefix, one step
    later (#507). The barrier is the same `_fsync_dir` the automatic path
    uses, taken on the blob directory before the row is decided.
    """
    import builtins
    real_open = builtins.open

    def partial_then_fail(*a, **kw):
        if len(a) > 1 and "w" in str(a[1]):
            fh = real_open(*a, **kw)

            class _Partial:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *e):
                    fh.close()
                    return False

                def write(self_inner, data):
                    fh.write(data[:8])
                    fh.flush()
                    raise OSError("no space left on device")

            return _Partial()
        return real_open(*a, **kw)

    flushed = []
    monkeypatch.setattr(auto_logs, "_fsync_dir",
                        lambda d: flushed.append(str(d)))

    def _file(handler=None):
        monkeypatch.setattr(main, "_is_admin", _no_admin)
        monkeypatch.setattr(main, "_mark_mod_seen", _noop_mark)
        monkeypatch.setattr(builtins, "open", partial_then_fail)
        db = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
        req = schemas.BugReportRequest(steam_id=STEAM, description="it broke",
                                       log_text="a log worth keeping")
        try:
            return _run((handler or main.submit_bug_report)(
                req, _request(), db)), db
        finally:
            monkeypatch.setattr(builtins, "open", real_open)

    capsys.readouterr()
    _file()
    # TWO FLUSHES SINCE ROUND 6, AND THEY ARE DIFFERENT BARRIERS. The first
    # is the MARKER's directory entry, taken by `_stamp_marker` before the
    # attachment's first byte (L4); the second is the cleanup's. Counting one
    # would now pass with either of them missing, which is why the case reads
    # the whole list.
    assert flushed == [str(logdir), str(logdir)], (
        "the partial file's removal was never made durable before the row "
        "committed, or the marker's entry was not: flushes=%r" % (flushed,))
    assert "removed durably" in capsys.readouterr().out

    # MUTANT at the barrier's own site: dropped. Nothing flushes, so a crash
    # after the commit can recover the file the row says is gone.
    flushed.clear()
    site = ("                                    _auto_logs._fsync_dir(\n"
            "                                        _pathlib.Path(attempted_path).parent)\n")
    _file(_report_mutant(site, "                                    pass\n"))
    assert flushed == [str(logdir)], (
        "the mutant still took the cleanup's flush, so the live assertion "
        "above proves nothing: %r" % (flushed,))

    # INERT TWIN at the SAME site: the same flush, the path spelled out.
    flushed.clear()
    _file(_report_mutant(
        site,
        "                                    _auto_logs._fsync_dir(\n"
        "                                        _pathlib.Path(str(attempted_path)).parent)\n"))
    assert flushed == [str(logdir), str(logdir)], (
        "the inert twin changed the outcome, so the mutant above is reacting "
        "to the site being edited rather than to the barrier: %r" % (flushed,))


def test_a_short_write_still_stamps_the_whole_marker(logdir):
    """R3-L5: `os.write` MAY TAKE FEWER BYTES THAN IT IS GIVEN.

    A short write raises nothing -- it returns what it took -- so one
    unchecked call followed by `fsync` makes a TRUNCATED marker durable, and
    the failure table's "a whole marker" was a claim about the usual case.
    Collection is safe either way, because the sweep reads the marker's NAME,
    but a claim in the notes is a claim (#351).

    The volume here takes one byte per call.
    """
    name = "77777777-0000-4000-8000-0000000000a1.log.gz"
    real_write = os.write

    def one_byte(fd, data):
        return real_write(fd, bytes(data)[:1])

    marker = logdir / (name + auto_logs._ORPHAN_MARKER_SUFFIX)
    saved = auto_logs.os
    auto_logs.os = _OsProxy(write=one_byte)
    try:
        auto_logs._stamp_marker(logdir / name)
        whole = marker.read_bytes()
        # THE LIVE PROPERTY IS JUDGED FIRST, before either compiled copy is
        # built. Each copy is built from the source's own anchor, so a tree
        # whose write loop is gone used to red on the missing anchor -- a
        # fail-closed red that says nothing about the marker it wrote.
        assert whole == name.encode("utf-8") + b"\n", (
            "the marker a one-byte-per-call volume produced is not the whole "
            "filename plus a newline: %r" % (whole,))

        # MUTANT at the loop's own site: one unchecked call, which is the
        # tree before this fix. The marker is one byte long and durable.
        marker.unlink()
        mutant = _point_at(
            _exec_mutant(auto_logs._stamp_marker,
                         '        _write_all(fd, blob_path.name.encode("utf-8") + b"\\n")\n',
                         '        os.write(fd, blob_path.name.encode("utf-8") + b"\\n")\n'),
            auto_logs.os)
        mutant(logdir / name)
        short = marker.read_bytes()

        # INERT TWIN at the SAME site: the same loop, the body built first.
        marker.unlink()
        twin = _point_at(
            _exec_mutant(auto_logs._stamp_marker,
                         '        _write_all(fd, blob_path.name.encode("utf-8") + b"\\n")\n',
                         '        _write_all(fd, bytes(blob_path.name.encode("utf-8")) + b"\\n")\n'),
            auto_logs.os)
        twin(logdir / name)
        twin_body = marker.read_bytes()
    finally:
        auto_logs.os = saved
        auto_logs._MARKERS_IN_FLIGHT.discard(name)

    assert short == name.encode("utf-8")[:1], (
        "the mutant did not truncate the marker, so the live assertion above "
        "proves nothing: %r" % (short,))
    assert twin_body == whole, (
        "the inert twin changed the marker, so the mutant above is reacting "
        "to the site being edited rather than to the loop: %r" % (twin_body,))


def test_a_retention_pass_whose_directory_will_not_flush_deletes_no_row(
        logdir, capsys):
    """WHICH DIRECTION THE UNHANDLED CASE FAILS IN (#276/#430).

    `_fsync_dir` does not swallow, and on the write path the answer to a
    volume that will not flush is to REFUSE the upload. Retention cannot take
    that answer: it has already unlinked, and raising would lose which rows
    those were. So the flush failure is ANSWERED, and the conservative move is
    to delete no row whose blob this pass removed -- the row is the only name
    that blob has, and an unprovable removal must not be followed by dropping
    it.
    """
    for nm in ("keep-a.log.gz", "keep-b.log.gz"):
        (logdir / nm).write_bytes(b"x")
    db = Scripted({DUE_KEY: [[{"id": str(R1), "log_filename": "keep-a.log.gz"},
                              {"id": str(R2), "log_filename": "keep-b.log.gz"}]]})

    def refusing_open(path, flags, *a, **kw):
        if flags & getattr(os, "O_DIRECTORY", 0o200000):
            raise OSError("the directory will not flush")
        return os.open(path, flags, *a, **kw)

    saved = auto_logs.os
    auto_logs.os = _OsProxy(O_DIRECTORY=0o200000, open=refusing_open)
    capsys.readouterr()
    try:
        out = _run(auto_logs.prune_auto_logs(db))
    finally:
        auto_logs.os = saved
    printed = capsys.readouterr().out

    assert out["blobs"] == 2 and out["undurable"] == 2 and out["rows"] == 0, (
        "a pass whose removals cannot be proved still deleted rows: %r"
        % (out,))
    assert db.sql_for("DELETE FROM bug_reports") == [], (
        "the DELETE ran over unlinks the filesystem never promised")
    assert out["held"] == 2, (
        "the rows kept over an unprovable removal were not held out of the "
        "next selection: %r" % (out,))
    assert "not durable" in printed, printed

    # CONTROL: the same pass with a directory that flushes. The rows go.
    for nm in ("keep-a.log.gz", "keep-b.log.gz"):
        (logdir / nm).write_bytes(b"x")
    auto_logs._PRUNE_HELD.clear()
    db2 = Scripted({DUE_KEY: [[{"id": str(R1), "log_filename": "keep-a.log.gz"},
                               {"id": str(R2), "log_filename": "keep-b.log.gz"}]],
                    "DELETE FROM bug_reports": [[{"id": str(R1)},
                                                 {"id": str(R2)}]]})
    ok = _run(auto_logs.prune_auto_logs(db2))
    assert ok["undurable"] == 0 and ok["rows"] == 2, (
        "the control pass did not delete its rows, so the refusal above is "
        "not about the flush: %r" % (ok,))
    assert sorted(db2.params_for("DELETE FROM bug_reports")[0]["ids"]) == \
        sorted([R1, R2]), (
        "the control pass deleted a different set of rows: %r"
        % (db2.params_for("DELETE FROM bug_reports")[0]["ids"],))


@pytest.mark.parametrize("pass_name", ["retention", "orphan"])
def test_the_sweeps_filesystem_work_does_not_block_the_event_loop(logdir,
                                                                  pass_name):
    """BOTH PASSES DO THEIR UNLINKS OFF THE LOOP, and this measures it.

    Each pass issues up to two hundred unlinks, and the removal arm a
    directory flush between each pair -- 60-200 ms apiece on this seat, more
    on a contended or recovering volume. The api runs ONE uvicorn worker by
    design, so on the loop that is time in which no queue join, match report
    or chat poll on the box makes any progress.

    Measured the same way the upload path's stages are: a 5 ms ticker, with
    the control proving it registers nothing when the same delay is taken ON
    the loop, so a pass means the work moved rather than the probe being
    blind.
    """
    DELAY = 0.3
    real_existing = auto_logs._unlink_existing
    real_delete = auto_logs._delete_blob_then_marker

    def slow_existing(path):
        time.sleep(DELAY)
        return real_existing(path)

    def slow_delete(path):
        time.sleep(DELAY)
        return real_delete(path)

    async def _ticks_during(body):
        ticks = [0]
        stop = asyncio.Event()

        async def ticker():
            while not stop.is_set():
                ticks[0] += 1
                await asyncio.sleep(0.005)

        task = asyncio.create_task(ticker())
        await asyncio.sleep(0.02)
        before = ticks[0]
        await body()
        during = ticks[0] - before
        stop.set()
        await task
        return during

    if pass_name == "retention":
        (logdir / "slow.log.gz").write_bytes(b"x")
        db = Scripted({DUE_KEY: [[{"id": str(R1),
                                   "log_filename": "slow.log.gz"}]],
                       "DELETE FROM bug_reports": [[{"id": str(R1)}]]})

        async def run_pass():
            await auto_logs.prune_auto_logs(db)
    else:
        name = "88888888-0000-4000-8000-0000000000b1.log.gz"
        (logdir / name).write_bytes(b"x")
        _mark(logdir, name, age_s=90_000)
        db = Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                       "SELECT log_filename FROM bug_reports": [[]]})

        async def run_pass():
            await auto_logs.prune_orphan_blobs(db, min_age_s=3600)

    async def block_on_the_loop():
        time.sleep(DELAY)

    auto_logs._unlink_existing = slow_existing
    auto_logs._delete_blob_then_marker = slow_delete
    try:
        during = asyncio.run(_ticks_during(run_pass))
    finally:
        auto_logs._unlink_existing = real_existing
        auto_logs._delete_blob_then_marker = real_delete

    blocked = asyncio.run(_ticks_during(block_on_the_loop))
    assert blocked <= 1, (
        "the probe counted %d ticks through a %ss block ON the loop, so it "
        "cannot tell blocking from non-blocking" % (blocked, DELAY))
    assert during >= 5, (
        "only %d ticks got through while the %s pass did its unlinks, against "
        "%d for a deliberate block -- the work is still on the event loop"
        % (during, pass_name, blocked))


def test_373_asserts_the_whole_shape_of_an_adopted_sequence():
    """R4's MEDIUM: A DESCENDING SEQUENCE IS NOT THE SAME AS THE RIGHT ONE.

    `CREATE SEQUENCE IF NOT EXISTS` keeps a pre-existing sequence silently, so
    a block of this file is the only thing that decides whether it may adopt
    one. Checking the increment and then spending two draws admits
    `START -1 INCREMENT -1 MINVALUE -2 MAXVALUE -1 NO CYCLE`: it descends, the
    two draws spend -1 and -2, and then every real upload fails at `nextval`
    and answers 503 with nothing in the log naming this file.

    IN RANGE IS NOT THE CONFIGURED START, which is round 6's addition. A
    sequence that is exact in every other attribute and starts at
    `MINVALUE + 1` is in range, survives `OWNED BY`, and spends the only two
    values it holds on the post-check's two draws: it is exhausted the moment
    this file reports success. So the start is asked twice: once for the
    range, once by identity.

    AND WHERE IT SITS IS PART OF THE FACT. The round-5 draft put these
    refusals in the post-check, and the rehearsal showed `ALTER SEQUENCE ...
    OWNED BY` re-validates the whole sequence: a catalogue row whose START is
    outside its own range was refused there, by PostgreSQL, naming neither the
    file nor the repair, so that arm could not fire at all. The others were
    reached only after this file had added a CHECK constraint over a
    sequence it was about to refuse. So the block is asserted to come BEFORE
    the OWNED BY, which is what makes every refusal this file's own.

    The rehearsal drives one fixture per attribute against a real server;
    this case holds the file to the shape that makes that possible.
    """
    sql = _sql_373()
    body = sql.split("-- \u2500\u2500 1b. the shape this file is willing to adopt", 1)
    assert len(body) == 2, (
        "373's sequence-shape block is no longer where this case looks for it")
    check = body[1].split("END $m373s$;", 1)[0]
    assert "DO $m373s$" in body[1][:len(body[1]) - len(check)] + check, (
        "the shape block is not a DO block of its own")

    # BEFORE THE OWNED BY, and before the CHECK constraint. Both re-validate
    # or write against a sequence this file has not yet agreed to adopt.
    owned_by = sql.index(
        "ALTER SEQUENCE bug_reports_auto_number_seq OWNED BY")
    shape_end = sql.index("END $m373s$;")
    assert shape_end < owned_by, (
        "the shape block runs after the OWNED BY, which re-validates the "
        "sequence itself -- the seqstart refusal below can never fire")
    assert shape_end < sql.index("ADD CONSTRAINT bug_reports_auto_number_negative"), (
        "the shape block runs after the CHECK is added, so this file writes "
        "against a sequence it is about to refuse")

    # EVERY COLUMN OF pg_sequence, AS A COUNTED DECLARATION (R7-M2). Round 7
    # read six of the eight and called it the whole shape; the one it left
    # out, `seqcache`, is what let a sequence whose stored position runs ahead
    # of every value it hands out through. The list is declared, the
    # catalogue's own list is read against it, and the SELECT reads every
    # attribute the declaration names but the key it selects by.
    declared = re.search(r"c_pg_sequence_columns CONSTANT text\[\] := ARRAY\[(.*?)\];",
                         check, re.S)
    assert declared, "the shape block declares no column list for pg_sequence"
    names = re.findall(r"'([a-z]+)'", declared.group(1))
    assert names == ["seqrelid", "seqtypid", "seqstart", "seqincrement",
                     "seqmax", "seqmin", "seqcache", "seqcycle"], (
        "the declared pg_sequence columns are %r, not the catalogue's eight "
        "in its own order" % (names,))
    assert "WHERE attrelid = 'pg_catalog.pg_sequence'::regclass" in check, (
        "the shape block never reads the catalogue's column list against "
        "its declaration")
    assert "IF v_columns IS DISTINCT FROM c_pg_sequence_columns THEN" in check
    select = re.search(r"SELECT (seqtypid[^\n]*)\n\s*INTO", check)
    assert select, "the shape block's pg_sequence SELECT moved"
    read = [c.strip() for c in select.group(1).split(",")]
    assert read == names[1:], (
        "the shape block reads %r from pg_sequence; the declaration names %r "
        "after the key" % (read, names[1:]))
    for attribute in names[1:]:
        assert attribute in check, (
            "the shape block never reads %s, so a sequence that differs in it "
            "is adopted silently" % attribute)

    # AND THE RELATION'S PERSISTENCE, which pg_sequence does not carry
    # (R7-M3): only a logged sequence keeps its position through crash
    # recovery and reaches a standby.
    assert "SELECT relpersistence INTO v_persistence" in check
    assert "c_logged         CONSTANT \"char\" := 'p';" in check
    assert "IF v_persistence IS DISTINCT FROM c_logged THEN" in check

    # ONE REFUSAL PER ATTRIBUTE, each naming it. A single "the sequence is
    # wrong" is a refusal nobody can act on (#430).
    for phrase in ("data type", "increment", "MAXVALUE", "MINVALUE",
                   "CYCLES", "outside its own range", "starting at %, not %",
                   "with CACHE %, not %", "with relpersistence %, not %",
                   "column(s)"):
        assert phrase in check, (
            "no refusal in the shape block names %r, so that attribute is "
            "read and not judged" % (phrase,))
    assert check.count("RAISE EXCEPTION") == 11, (
        "the shape block holds %d refusal(s): one per attribute (the cache "
        "included), the START by IDENTITY as well as by range, the "
        "persistence, the column declaration, plus the missing-sequence arm"
        % check.count("RAISE EXCEPTION"))
    assert "    CACHE 1\n" in sql, (
        "the CREATE SEQUENCE does not state the cache the shape block "
        "asserts")

    # THE START IS ASKED TWICE AND THE ORDER IS THE FACT. `IN RANGE` and `IS
    # THE CONFIGURED START` differ over every value strictly inside the range,
    # and the range test is the one whose message can name the range -- so it
    # has to come first, or a start outside the range would be refused by the
    # identity arm and the range refusal could never fire (#342).
    assert check.index("outside its own range") < check.index("starting at %, not %"), (
        "the identity test for the start runs before the range test, so the "
        "range refusal is unreachable")
    assert "c_auto_start     CONSTANT bigint := -1;" in check, (
        "the start is judged against a literal rather than the constant that "
        "restates the DDL")

    # AND THE CONFIGURED VALUES ARE THE ONES THE DDL INSTALLS. A check written
    # against a different literal is a check that refuses this file's own
    # sequence.
    assert "MINVALUE -9223372036854775807" in sql, (
        "the DDL's floor moved; the shape block's constant has to move with it")
    assert "c_auto_min       CONSTANT bigint := -9223372036854775807;" in sql, (
        "the shape block's floor constant is not the value the DDL configures")
    # THE BIGINT FLOOR MAY BE NAMED, BUT ONLY IN PROSE. The comment that says
    # what the configured floor is NOT is the correction #302 is about; a
    # value one below the DDL's in an EXECUTABLE line would be a check that
    # refuses this file's own sequence.
    executable = [ln for ln in sql.splitlines()
                  if "-9223372036854775808" in ln
                  and not ln.strip().startswith("--")]
    assert executable == [], (
        "an executable line names the bigint floor, which is one below the "
        "value this file configures: %r" % (executable,))


def test_373_scopes_every_guard_to_the_relation_it_alters():
    """R3-M1: THE GUARDS AND THE DDL LOOK AT ONE RELATION.

    `information_schema.columns` with no `table_schema` predicate answers
    about whichever `bug_reports.kind` the catalogue returns, which on a
    database carrying a second accessible schema is not necessarily the column
    this file's ALTER statements constrain: a drifted target passes because
    the other schema is correct, and a correct target is refused because the
    other has drifted. The rehearsal drives both directions against a database
    carrying two such schemas; this case holds the file to the shape that
    makes that possible.
    """
    sql = _sql_373()
    lookups = [ln for ln in sql.splitlines()
               if "information_schema.columns" in ln
               and not ln.strip().startswith("--")]
    assert len(lookups) == 2, (
        "373 reads information_schema.columns at %d executable site(s); each "
        "one has to carry its own schema predicate: %r"
        % (len(lookups), lookups))
    for site in lookups:
        block = sql.split(site, 1)[1][:400]
        assert "table_schema = current_schema()" in block, (
            "an information_schema lookup is not scoped to current_schema(): "
            "%r" % (site,))

    assert "to_regclass('bug_reports')" in sql, (
        "the file no longer resolves the unqualified name its own DDL uses")
    assert "v_schema IS DISTINCT FROM current_schema()" in sql, (
        "nothing requires the relation the DDL will alter to be the one the "
        "guards inspect")
    assert "conrelid = 'bug_reports'::regclass" not in sql, (
        "a constraint lookup still re-resolves the bare name instead of using "
        "the resolved target")
    assert sql.count("quote_ident(current_schema())") >= 3, (
        "the second and third blocks do not bind their own names to "
        "current_schema()")
    assert "CREATE TEMP TABLE m373_number_probe (LIKE bug_reports" not in sql, (
        "the post-check's probe table is still copied from whichever "
        "bug_reports the search_path resolves")


# ── round 7: one control per finding ────────────────────────────────────────


def _test_helper_mutant(fn, anchor, replacement):
    """A helper of THIS module with one edit, compiled against a COPY of this
    module's globals. The anchor is asserted to be one site inside the
    helper's own span first (#432/#279)."""
    src = textwrap.dedent(inspect.getsource(fn))
    assert src.count(anchor) == 1, (
        "the mutation anchor occurs %d time(s) in %s, not once: %r"
        % (src.count(anchor), fn.__name__, anchor))
    namespace = dict(globals())
    exec(compile(src.replace(anchor, replacement),
                 "<mutant:%s>" % fn.__name__, "exec"), namespace)
    return namespace[fn.__name__]


def test_the_stored_walk_models_its_attachment_whoever_drives_it(tmp_path,
                                                                 monkeypatch):
    """R6-L1: THE WALK LABELLED "stored" PERSISTS THE ATTACHMENT.

    The round-6 evidence script drove `_drive_report` without the `logdir`
    fixture, so `BUG_REPORT_LOG_DIR` still named a real directory: the model
    saw the marker (the walk patches the auto module's `os`) and never saw
    the blob, whose `open` went to that directory. The record it published
    as the stored order returned `log_persisted: False` and went from the
    marker's flushes straight to the cleanup arm. The helper now points the
    handler at the directory it models, itself.

    Driven here with the live global pointing SOMEWHERE ELSE on purpose --
    the state the script was in -- the walk must still show the whole stored
    order: the blob's open and first write, its contents flush, the entry
    flush, the commit and the marker's clear, in that order, with nothing
    landing in the other directory. THE CONTROL removes the helper's
    pointing and must reproduce the round-6 record; the INERT TWIN spells it
    differently and must not.
    """
    elsewhere = tmp_path / "elsewhere"
    modelled = tmp_path / "modelled"
    elsewhere.mkdir()
    modelled.mkdir()
    monkeypatch.setattr(main, "BUG_REPORT_LOG_DIR", str(elsewhere))
    suffix = auto_logs._ORPHAN_MARKER_SUFFIX

    def walk(drive):
        fs, db, outcome = drive(None, logdir=modelled)
        landed = sorted(os.listdir(str(elsewhere)))
        for stray in landed:
            os.unlink(str(elsewhere / stray))
        return fs, db, outcome, landed

    fs, db, outcome, landed = walk(_drive_report)
    assert outcome["log_persisted"] is True, outcome
    assert landed == [], (
        "the walk wrote %r outside the directory it models" % (landed,))
    blob = db.row_at_commit[0]
    ops = fs.ops
    order = [ops.index("open " + blob), ops.index("write " + blob),
             ops.index("fsync " + blob)]
    order.append(ops.index("fsync-dir", order[-1]))
    order.append(ops.index("COMMIT"))
    order.append(ops.index("unlink " + blob + suffix))
    assert order == sorted(order) and len(set(order)) == len(order), (
        "the stored walk does not run the blob's write, its contents flush, "
        "its entry flush, the commit and the marker's clear in that order: "
        "%r" % (ops,))
    assert db.row_at_commit[1] == len(db.row_at_commit[2] or b""), (
        db.row_at_commit)

    # THE CONTROL: the pointing removed, which is the round-6 helper.
    site = ('    g["BUG_REPORT_LOG_DIR"] = main.BUG_REPORT_LOG_DIR = '
            'str(logdir)\n')
    fs, db, outcome, landed = walk(
        _test_helper_mutant(_drive_report, site, "    pass\n"))
    assert landed, (
        "with the pointing removed nothing landed outside the modelled "
        "directory, so the GREEN above is not about the pointing: %r"
        % (outcome,))
    assert not any(_is_blob_write(op) for op in fs.ops), (
        "with the pointing removed the model still saw the blob's writes: %r"
        % (fs.ops,))

    # THE INERT TWIN at the same site: the same directory, spelled otherwise.
    fs, db, outcome, landed = walk(_test_helper_mutant(
        _drive_report, site,
        '    g["BUG_REPORT_LOG_DIR"] = main.BUG_REPORT_LOG_DIR = '
        'os.fspath(logdir)\n'))
    assert outcome["log_persisted"] is True and landed == [], (
        "the inert twin changed the walk, so the control above is reacting "
        "to the edit rather than to the pointing: %r %r" % (outcome, landed))


def test_a_failed_automatic_cleanup_releases_its_name_when_the_barrier_refuses(
        logdir, monkeypatch):
    """R6-L2: THE CLEANUP RELEASES THE IN-FLIGHT NAME ON EVERY EXIT.

    `_release_marked_blob` removes the blob, flushes the directory, then
    removes the marker (`_delete_blob_then_marker`), and `_fsync_dir` raises
    rather than swallowing. A volume that refuses that flush therefore ends
    the function between its two unlinks -- with the marker still on the
    volume, which is what keeps the blob collectable -- and before round 7 it
    also ended it before the line that released the blob's name, so every
    sweep of the process skipped that marker until a restart. The release is
    now in a `finally`.

    THE CONTROL puts the release back on the normal exit only and must leave
    the name registered; the INERT TWIN spells the release differently and
    must not.
    """
    name = "77777777-0000-4000-8000-0000000000c2.log.gz"
    blob = logdir / name
    marker = auto_logs._marker_path(blob)

    def refuse(directory):
        raise OSError("the directory would not flush")

    def run(release):
        blob.write_bytes(b"a partial gzip stream")
        marker.write_bytes(name.encode("utf-8") + b"\n")
        own = auto_logs._MarkedBlob(blob)
        own.marked = own.written = True
        auto_logs._MARKERS_IN_FLIGHT.add(name)
        with monkeypatch.context() as m:
            m.setattr(auto_logs, "_fsync_dir", refuse)
            with pytest.raises(OSError):
                release(own)
        held = name in auto_logs._MARKERS_IN_FLIGHT
        auto_logs._MARKERS_IN_FLIGHT.discard(name)
        return held

    assert not run(auto_logs._release_marked_blob), (
        "the directory flush between the two unlinks refused, and the blob's "
        "name is still registered as in flight: every sweep of this process "
        "would skip its marker")
    assert marker.exists() and not blob.exists(), (
        "the refused flush did not stop the cleanup between its two unlinks, "
        "so this case is not driving the arm it names: marker=%r blob=%r"
        % (marker.exists(), blob.exists()))

    mutant = _exec_mutant(
        auto_logs._release_marked_blob, "    finally:\n",
        "    except BaseException:\n"
        "        raise\n"
        "    else:\n"
        "        pass\n"
        "    if True:\n")
    assert run(mutant), (
        "with the release on the normal exit only, the refused flush still "
        "released the name, so the GREEN above is not about the `finally`")

    twin = _exec_mutant(
        auto_logs._release_marked_blob,
        "        _MARKERS_IN_FLIGHT.discard(own.path.name)\n",
        "        _MARKERS_IN_FLIGHT.discard(str(own.path.name))\n")
    assert not run(twin), (
        "the inert twin left the name registered, so the control above is "
        "reacting to the edit rather than to the release")


@pytest.mark.parametrize("raise_at", ["event-add", "diagnostic"])
def test_a_raise_before_the_commit_releases_the_attachments_in_flight_name(
        logdir, monkeypatch, raise_at):
    """R6-L3: ONE `finally` SPANS EVERY STATEMENT FROM THE REGISTRATION TO
    THE COMMIT.

    The attachment's name is registered in `_MARKERS_IN_FLIGHT` before its
    marker is stamped, and the sweep skips a registered name at any age.
    Round 6 released it in a `finally` around the commit alone, so a
    statement between the two that raised -- the event row's `db.add`, or
    the failure arm's own diagnostic line -- ended the request with the name
    still registered, and every sweep of the process skipped a marked,
    unreferenced attachment until a restart.

    One raise point per kind the finding names. THE CONTROL narrows the
    release back to requests that reached the commit, which is the round-6
    span, and must leave the name registered; the INERT TWIN makes the same
    three edits with the new condition always true and must not.
    """
    monkeypatch.setattr(main, "_is_admin", _no_admin)
    monkeypatch.setattr(main, "_mark_mod_seen", _noop_mark)

    class _Session(_ReportSession):
        def add(self, obj):
            if (raise_at == "event-add"
                    and type(obj).__name__ == "BugReportEvent"):
                raise RuntimeError("the event row could not be added")
            return super().add(obj)

    if raise_at == "diagnostic":
        import builtins
        real_open = builtins.open

        def refusing_open(*a, **kw):
            if (len(a) > 1 and "w" in str(a[1])
                    and str(a[0]).endswith(".log.gz")):
                raise OSError("no space left on device")
            return real_open(*a, **kw)

        def failing_line(*a, **kw):
            raise RuntimeError("the diagnostic line could not be written")

        monkeypatch.setattr(builtins, "open", refusing_open)
        monkeypatch.setattr(main, "print", failing_line, raising=False)

    req = schemas.BugReportRequest(steam_id=STEAM, description="it broke",
                                   log_text="a log")
    suffix = auto_logs._ORPHAN_MARKER_SUFFIX

    def _file(handler):
        # THE NAME IS READ OFF THE MARKER THIS REQUEST STAMPED. Since round
        # 8 the row is added in T2, after the attachment, so a raise in the
        # failure arm's diagnostic leaves no row to read the id from; the
        # marker is stamped before the attachment's first byte either way,
        # and exactly one new one is required.
        before = set(_markers(logdir))
        db = _Session({"FROM bug_reports": [[{"count": 0}]]})
        with pytest.raises(RuntimeError):
            _run(handler(req, _request(), db))
        new = sorted(set(_markers(logdir)) - before)
        assert len(new) == 1, (
            "the request stamped %d marker(s), not one: %r" % (len(new), new))
        name = new[0][:-len(suffix)]
        held = name in auto_logs._MARKERS_IN_FLIGHT
        auto_logs._MARKERS_IN_FLIGHT.discard(name)
        return name, held, db

    name, held, db = _file(main.submit_bug_report)
    assert (logdir / (name + suffix)).exists(), (
        "no marker was stamped, so the request raised before it registered "
        "anything and this case proves nothing about the release")
    assert db.committed == 0, "the request committed; it was meant to raise first"
    assert not held, (
        "the request raised at the %s -- after the attachment's name was "
        "registered, before the commit -- and the name is still registered: "
        "every sweep of this process would skip its marker" % raise_at)

    def _span(initial):
        return _report_mutant_pairs([
            ("    hops: list = []\n    committed = False\n",
             "    hops: list = []\n    committed = False\n"
             "    reached_commit = " + initial + "\n"),
            ("        await db.commit()\n        committed = True\n",
             "        reached_commit = True\n        await db.commit()\n"
             "        committed = True\n"),
            ("    finally:\n        if own is not None:\n",
             "    finally:\n"
             "        if own is not None and reached_commit:\n"),
        ])

    name, held, _ = _file(_span("False"))
    assert held, (
        "with the release narrowed to requests that reached the commit -- the "
        "round-6 span -- the raise at the %s still released the name, so the "
        "GREEN above is not about the span" % raise_at)
    name, held, _ = _file(_span("True"))
    assert not held, (
        "the inert twin (the same three edits, the new condition always "
        "true) left the name registered, so the control above is reacting to "
        "the edit rather than to the span")


def _slow_volume(monkeypatch, delay):
    """Every call either writer makes on the volume, each held for `delay`
    seconds IN THE THREAD THAT ISSUES IT: the directory's creation, the
    automatic reserve's free-space reading, the marker's stamp, every
    directory flush, the player blob's contents flush, and every unlink --
    the partial file's and the marker's clear.

    Blocking sleeps, on purpose. A volume that stalls a call stalls the
    thread that made it, and whether that thread is the event loop's is the
    whole question this fixture exists to ask.
    """
    def held(real):
        def slow(*a, **kw):
            time.sleep(delay)
            return real(*a, **kw)
        return slow

    class _SlowOS:
        """`os`, with a contents flush and an unlink that take `delay`."""

        def __getattr__(self, item):
            return getattr(os, item)

        @staticmethod
        def fsync(fd):
            time.sleep(delay)
            return os.fsync(fd)

        @staticmethod
        def unlink(path):
            time.sleep(delay)
            return os.unlink(path)

    for name in ("_stamp_marker", "_fsync_dir", "_unlink_if_present",
                 "_free_bytes"):
        monkeypatch.setattr(auto_logs, name, held(getattr(auto_logs, name)))
    monkeypatch.setattr(main, "_bug_report_log_path",
                        held(main._bug_report_log_path))
    monkeypatch.setattr(main, "os", _SlowOS())

async def _unrelated_waits_while(filing, period=0.01):
    """The worst lateness of an unrelated request while `filing` ran.

    The unrelated request is `get_mod_version`, the route every client polls,
    issued every `period` seconds on the same loop. Each issue records how
    far past its `period` it finished; the worst of them is what one
    player's attachment cost everyone else.
    """
    waits = []
    done = asyncio.Event()

    async def unrelated():
        while not done.is_set():
            t0 = time.perf_counter()
            await asyncio.sleep(period)
            await main.get_mod_version()
            waits.append(time.perf_counter() - t0 - period)

    probe = asyncio.create_task(unrelated())
    await asyncio.sleep(0.05)
    try:
        out = await filing()
    finally:
        done.set()
        await probe
    return out, max(waits)


# THE PLAYER ATTACHMENT'S CALLS ON THE VOLUME: each hop's site in
# `submit_bug_report`, the edit that makes the same call ON the loop, and an
# inert twin at the same site. The ORDER decides which arm runs; the
# directory and the marker's clear run in both, so they ride the stored one.
# Since round 8 every site is a call on the auto-log module's volume pool
# (`_hop`, or `_start` where the request must know when the WORK ends), and
# the on-loop edit makes the same call synchronously inside a finished
# future, so the code around the site is unchanged.
_PLAYER_HOPS = {
    "stored": (
        "stored",
        "                hop = _auto_logs._start(_auto_logs._VOLUME_POOL,\n"
        "                                        _store_attachment)\n",
        "                hop = asyncio.ensure_future(\n"
        "                    asyncio.sleep(0, _store_attachment()))\n",
        "                hop = _auto_logs._start(_auto_logs._VOLUME_POOL,\n"
        "                                        _store_attachment, *())\n"),
    "write-fails": (
        "write-fails",
        "                    hop = _auto_logs._start(_auto_logs._VOLUME_POOL,\n"
        "                                            _discard_partial)\n",
        "                    hop = asyncio.ensure_future(\n"
        "                        asyncio.sleep(0, _discard_partial()))\n",
        "                    hop = _auto_logs._start(_auto_logs._VOLUME_POOL,\n"
        "                                            _discard_partial, *())\n"),
    "directory": (
        "stored",
        "                path = await _auto_logs._hop(\n"
        "                    _auto_logs._VOLUME_POOL,\n"
        "                    _auto_logs._span_budget(attach_deadline),\n"
        "                    _bug_report_log_path, str(report_id))\n",
        "                path = _bug_report_log_path(\n"
        "                    str(report_id))\n",
        "                path = await _auto_logs._hop(\n"
        "                    _auto_logs._VOLUME_POOL,\n"
        "                    _auto_logs._span_budget(attach_deadline),\n"
        "                    _bug_report_log_path, \"%s\" % (report_id,))\n"),
    "marker-clear": (
        "stored",
        "                hops.append(_auto_logs._start(_auto_logs._VOLUME_POOL,\n"
        "                                              _auto_logs._clear_marker, own,\n"
        "                                              False))\n",
        "                hops.append(asyncio.ensure_future(asyncio.sleep(\n"
        "                    0, _auto_logs._clear_marker(own, False))))\n",
        "                hops.append(_auto_logs._start(_auto_logs._VOLUME_POOL,\n"
        "                                              _auto_logs._clear_marker,\n"
        "                                              *(own, False)))\n"),
}


@pytest.mark.parametrize("hop", ["stored", "write-fails", "directory",
                                 "marker-clear"])
def test_a_player_attachment_on_a_slow_volume_does_not_stall_other_requests(
        logdir, monkeypatch, hop):
    """R6-M3: EVERY CALL THE PLAYER ATTACHMENT MAKES ON THE VOLUME RUNS OFF
    THE EVENT LOOP.

    The api runs one asynchronous worker (#125). Round 6 left the player
    attachment's stamp, write, contents flush and directory flush -- and the
    failure arm's unlink and flush -- inline in the handler, so a contended
    volume held every other request in the process for as long as those
    took. Both now run on worker threads (`_store_attachment`,
    `_discard_partial`), and so do the two calls round 7's sweep of the
    class found still on the loop: the directory's creation in
    `_bug_report_log_path`, and the marker's clear after the commit
    (`_drop_marker`).

    THE WITNESS is an unrelated request issued every 10 ms on the same loop
    while one attachment is filed over a volume whose every call takes
    `DELAY`. THE BOUND is half of one such call: work on the loop blocks it
    for at least one whole call, so it cannot pass, and work off the loop
    costs the probe only scheduling noise. Each parameter is one hop: THE
    CONTROL makes that hop's call on the loop at its own site and must break
    the bound; the INERT TWIN at the same site must stay under it. Moving the
    work is not a durability change, so what holds the ORDER is the crash
    matrix above, whose controls are unchanged.
    """
    import builtins

    DELAY, BOUND = 0.5, 0.25
    order, site, on_loop, twin = _PLAYER_HOPS[hop]
    monkeypatch.setattr(main, "_is_admin", _no_admin)
    monkeypatch.setattr(main, "_mark_mod_seen", _noop_mark)
    req = schemas.BugReportRequest(steam_id=STEAM, description="it broke",
                                   log_text="a log")
    if order == "write-fails":
        monkeypatch.setattr(builtins, "open",
                            _partial_write_open(builtins.open))
    # THE SLOW VOLUME GOES IN FIRST. A mutant runs in a copy of the module's
    # globals taken when it is built, so every handler below is built after
    # the volume is slowed and sees the same volume the live one does.
    _slow_volume(monkeypatch, DELAY)

    def _file(handler):
        db = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
        return asyncio.run(_unrelated_waits_while(
            lambda: handler(req, _request(), db)))

    out, worst = _file(main.submit_bug_report)
    live = worst
    assert out["log_persisted"] is (order == "stored"), out
    assert worst < BOUND, (
        "an unrelated request finished %.3fs late while one player's "
        "attachment was filed over a volume taking %.1fs per call; the bound "
        "is %.2fs, so a call of the %s order is still on the event loop"
        % (worst, DELAY, BOUND, order))

    # THE CONTROL: this hop's call made on the loop, at its own site.
    out, worst = _file(_report_mutant(site, on_loop))
    control = worst
    assert out["log_persisted"] is (order == "stored"), out
    assert worst >= BOUND, (
        "with the %s hop put back on the event loop the unrelated request "
        "was only %.3fs late, inside the %.2fs bound although one call "
        "takes %.1fs -- the witness cannot see a stall, so its GREEN above "
        "means nothing" % (hop, worst, BOUND, DELAY))

    # THE INERT TWIN at the same site: the same hop, spelled differently.
    out, worst = _file(_report_mutant(site, twin))
    assert out["log_persisted"] is (order == "stored"), out
    assert worst < BOUND, (
        "the inert twin of the %s hop stalled the unrelated request %.3fs, so "
        "the control above is reacting to the edit rather than to the hop"
        % (hop, worst))
    print("WITNESS player %s: live %.3fs, on-loop control %.3fs, inert twin "
          "%.3fs -- bound %.2fs, one call %.1fs"
          % (hop, live, control, worst, BOUND, DELAY))

def test_373_reads_where_the_sequence_is_under_the_lock_it_adopts_it_under():
    """R6-M1: BLOCK 1c JUDGES THE POSITION, NOT ONLY THE CONFIGURATION.

    Block 1b reads six attributes and every one of them is configuration: a
    RESTART or a setval moves where the sequence IS without touching any of
    them, so a sequence restarted one step above its MINVALUE passed every
    check, was adopted, and would answer 503 within a few uploads. Block 1c
    reads `last_value` and `is_called` under the lock the OWNED BY takes --
    a lock nextval cannot pass -- and refuses a next value below the floor,
    or at or below a bug number already held; the post-check then binds the
    first draw to the value 1c read.

    The rehearsal drives each refusal against a real server, one fixture per
    arm and a mutant per mechanism; this case holds the file to the shape
    that makes those readings mean what they say. Searched in the EXECUTABLE
    text, because every needle below also appears in the prose (#342).
    """
    sql = _sql_373()
    executable = "\n".join(ln for ln in sql.splitlines()
                           if not ln.lstrip().startswith("--"))
    assert executable.count("DO $m373n$") == 1, (
        "373 carries %d position block(s), not one"
        % executable.count("DO $m373n$"))
    owned_by = executable.index(
        "ALTER SEQUENCE bug_reports_auto_number_seq OWNED BY")
    start = executable.index("DO $m373n$")
    end = executable.index("END $m373n$;")
    post = executable.index("DO $m373p$")
    assert owned_by < start < end < post, (
        "block 1c does not sit between the OWNED BY, whose lock it reads "
        "under, and the post-check that draws")
    block = executable[start:end]

    # THE LOCK IS PROVEN, NOT ASSUMED: held by this backend, granted, and of
    # a mode nextval's RowExclusiveLock conflicts with.
    for needle in ("FROM pg_locks", "pid = pg_backend_pid()", "AND granted",
                   "'ShareRowExclusiveLock'"):
        assert needle in block, (
            "block 1c does not prove the lock it reads under (%r)" % needle)
    for mode in ("'RowExclusiveLock'", "'RowShareLock'", "'AccessShareLock'",
                 "'ShareUpdateExclusiveLock'"):
        assert mode not in block, (
            "block 1c accepts %s, which nextval can pass" % mode)

    # THE SEQUENCE IT JUDGES IS THE ONE 1b CHECKED.
    assert "PERFORM set_config('m373.shape_1b'," in executable[:owned_by], (
        "block 1b no longer records the shape it judged")
    assert "current_setting('m373.shape_1b', true)" in block, (
        "block 1c does not compare the shape under the lock with 1b's")

    # THE POSITION, and the next value it implies.
    assert ("SELECT last_value, is_called FROM %I.bug_reports_auto_number_seq"
            in block), "block 1c does not read the sequence's position"
    assert ("v_next := CASE WHEN v_called THEN v_last + v_increment "
            "ELSE v_last END;" in block), (
        "block 1c does not derive the next value from is_called")

    # THE UNDER-LOCK READING IS THE WHOLE SHAPE TOO, refused by name here as
    # well as in 1b (R7-M2, R7-M3): the declared column list, the cache and
    # the persistence, and a shape string carrying all eight readings.
    assert "IF v_columns IS DISTINCT FROM c_pg_sequence_columns THEN" in block
    assert "IF v_persistence IS DISTINCT FROM c_logged THEN" in block
    assert "IF v_cache IS DISTINCT FROM c_auto_cache THEN" in block
    assert ("v_shape := format('%s/%s/%s/%s/%s/%s/%s/%s', v_typid, v_start, "
            "v_increment," in block), (
        "block 1c's shape string does not carry every column 1b judged")

    # THE FLOOR: -2^62, so at least half the range remains -- judged on the
    # ACCOUNTED value, the position this file leaves once its post-check has
    # drawn (R7-M1), not on the one it finds.
    assert "c_floor CONSTANT bigint := %d;" % (-(2 ** 62)) in block, (
        "the adoption floor is not -2^62")
    assert "c_postcheck_draws CONSTANT bigint := 2;" in block
    assert ("v_accounted := v_next::numeric + c_postcheck_draws * v_increment;"
            in block and "v_accounted numeric;" in block), (
        "block 1c does not account for the post-check's draws in numeric (R8-X1)")
    assert "IF v_accounted < c_floor THEN" in block, (
        "the floor is not applied to the accounted value")
    assert "IF v_next < c_floor THEN" not in block, (
        "the floor is still applied to the value found, which the post-check "
        "then moves two below it")

    # A NUMBER ALREADY HELD, at or below the next value, on a descending
    # sequence whose bug_number is UNIQUE.
    assert ("SELECT max(bug_number) FROM %I.bug_reports WHERE bug_number <= $1"
            in block), "block 1c does not ask whether the next value is taken"
    assert "IF v_held IS NOT NULL THEN" in block

    # ONE READING, CARRIED TO THE DRAW.
    assert "PERFORM set_config('m373.next_1c', v_next::text, true);" in block
    post_block = executable[post:executable.index("END $m373p$;")]
    assert ("IF v_a IS DISTINCT FROM current_setting('m373.next_1c', "
            "true)::bigint THEN" in post_block), (
        "the post-check does not bind the first draw to 1c's reading")


def test_373_leaves_the_position_it_accounted_for_and_states_its_policy_once():
    """R7-M1: ONE ADOPTION-FLOOR POLICY, READ AT ONE POINT OF CONSUMPTION.

    Round 7 applied the floor to the next value block 1c FOUND and then spent
    two values in the post-check, so a next value exactly at the floor was
    adopted, committed two below it, and refused by the release train's
    reading of the same floor straight after. The value judged is now the
    ACCOUNTED one -- the position once the post-check has drawn -- and three
    things make that the value every later reader sees:

      * the accounting counts the post-check's draws, and the post-check
        makes exactly that many (a third draw added to the post-check, or a
        count edited on its own, reds here);
      * the post-check pins the position with `setval` to its second draw, so
        the reading a standby replays is not up to 32 values past it (the
        WAL pre-log), and reads it back through the policy's own text,
        refusing unless it is 1c's accounted value;
      * the policy -- the floor and the accounted-value query -- is stated
        exactly ONCE, each declaration on one line, because the release train
        reads those two lines out of this file at the reviewed commit and
        applies them to each box. A second copy anywhere in the file would be
        a second policy for the train to disagree with.
    """
    sql = _sql_373()
    executable = "\n".join(ln for ln in sql.splitlines()
                           if not ln.lstrip().startswith("--"))
    floor_lines = [ln for ln in executable.splitlines()
                   if re.match(r"^\s*c_floor CONSTANT bigint := (-?[0-9]+);\s*$", ln)]
    assert floor_lines == ["    c_floor CONSTANT bigint := %d;" % (-(2 ** 62))], (
        "the floor is declared %r -- the train reads exactly one such line"
        % (floor_lines,))
    policy_lines = [ln for ln in executable.splitlines()
                    if re.match(r"^\s*c_accounted_sql CONSTANT text :=\s*'((?:[^']|'')*)';\s*$", ln)]
    assert len(policy_lines) == 1, (
        "the accounted-value query is declared %d time(s); the train reads "
        "exactly one line" % len(policy_lines))
    policy = re.match(r"^\s*c_accounted_sql CONSTANT text :=\s*'((?:[^']|'')*)';\s*$",
                      policy_lines[0]).group(1).replace("''", "'")
    assert policy == ("SELECT (CASE WHEN is_called THEN last_value + "
                      "(log_cnt + 1) * -1 ELSE last_value END)::text AS "
                      "accounted_next FROM %s"), (
        "the accounted-value query changed: %r" % policy)
    assert policy.count("%") == 1, (
        "the query must carry exactly one placeholder, the relation")
    for word in ("DROP", "TRUNCATE", "DELETE", "UPDATE", "INSERT", "ALTER",
                 "GRANT", "REVOKE", "CREATE", "COPY"):
        assert word not in policy.upper(), (
            "the policy query carries %s, which the read-only wrapper the "
            "train sends it through refuses" % word)

    post = executable[executable.index("DO $m373p$"):executable.index("END $m373p$;")]
    draws = post.count("nextval(v_autoseq)")
    declared = int(re.search(r"c_postcheck_draws CONSTANT bigint := ([0-9]+);",
                             executable).group(1))
    assert draws == declared == 2, (
        "the post-check draws %d value(s) and block 1c accounts for %d"
        % (draws, declared))
    pin = post.index("PERFORM setval(v_autoseq, v_b, true);")
    assert pin > post.index("v_b := nextval(v_autoseq);"), (
        "the position is pinned before the second draw, so the draw after it "
        "logs ahead again")
    back = post.index("EXECUTE format(current_setting('m373.accounted_sql', true),")
    assert pin < back, "the policy reads the position before it is pinned"
    assert ("IF v_left IS DISTINCT FROM current_setting('m373.accounted_1c', "
            "true) THEN" in post), (
        "the post-check does not refuse a position other than 1c's accounted "
        "value")
    assert ("IF v_left::bigint < current_setting('m373.floor', true)::bigint "
            "THEN" in post), "the post-check never applies the floor it was handed"
    assert back < post.index("CREATE TEMP TABLE m373_number_probe"), (
        "the read-back runs after the probes, so a refusal there follows "
        "writes this file then has to explain")


def _on_loop_release_calls(source):
    """Every call of `_release_marked_blob` made directly by a coroutine of
    `source` -- a nested plain function is a worker's body, run wherever its
    caller sends it, so the walk does not descend into one."""
    found = []

    def visit(node, owner):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.AsyncFunctionDef):
                visit(child, child.name)
                continue
            if (owner and isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Name)
                    and child.func.id == "_release_marked_blob"):
                found.append((owner, child.lineno))
            visit(child, owner)

    visit(ast.parse(source), None)
    return found


def test_every_automatic_cleanup_waits_on_a_worker_thread():
    """ROUND 7'S SIBLING SWEEP OF M3 (#432): A FLAG NAMES A LINE, THE DEFECT
    IS A CLASS.

    M3 moved the player attachment's durable sequence off the event loop.
    The automatic path's cleanup is the same class: `_release_marked_blob`
    takes the blob's own lock, which a write in progress holds, and then
    unlinks and flushes the directory. Round 6 sent ONE of its four
    coroutine call sites -- the cancelled section's -- through
    `_release_marked_blob_off_loop`; the deadline arm, the cancellation arm
    and the failed INSERT's arm in `upload_auto_log` still called it on the
    loop. Every coroutine call site now goes through the worker-thread
    helper, and the synchronous function is called by no coroutine at all.

    SINCE ROUND 8 THE HANDLER'S ARMS REACH IT THROUGH ONE MORE LAYER.
    Every refusal that cleans up -- the deadline, the cancellation, the
    re-check under the lock, the cap at the re-check, the failed INSERT --
    calls `_discard_for_refusal`, which awaits the worker-thread helper
    and answers every outcome as a sentence (R7-L1). So the helper's
    coroutine call sites are the section's and that one's, and the
    handler's five arms are counted at `_discard_for_refusal` instead.

    Where the wait happens is proven BEHAVIOURALLY at the cancelled section's
    site (`test_a_cancelled_sections_cleanup_does_not_block_the_event_loop`,
    whose mutant stops the heartbeat); this is the class half, read from the
    module's own syntax tree. THE CONTROL puts the refusals' cleanup back
    on the loop -- at `_discard_for_refusal` since round 8 -- and must be
    found; the INERT TWIN parenthesises the same await and must not.
    """
    src = inspect.getsource(auto_logs)
    assert _on_loop_release_calls(src) == [], (
        "a coroutine calls _release_marked_blob on the event loop: %r"
        % (_on_loop_release_calls(src),))

    awaited = {}
    for fn in ast.walk(ast.parse(src)):
        if isinstance(fn, ast.AsyncFunctionDef):
            for node in ast.walk(fn):
                if (isinstance(node, ast.Await)
                        and isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Name)
                        and node.value.func.id == "_release_marked_blob_off_loop"):
                    awaited[fn.name] = awaited.get(fn.name, 0) + 1
    assert awaited == {"_reserve_stamp_and_write": 1,
                       "_discard_for_refusal": 1}, (
        "the automatic cleanup's coroutine call sites moved: %r -- re-derive "
        "the class before changing this count" % (awaited,))
    refusals = {}
    for fn in ast.walk(ast.parse(src)):
        if isinstance(fn, ast.AsyncFunctionDef):
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "_discard_for_refusal"):
                    refusals[fn.name] = refusals.get(fn.name, 0) + 1
    assert refusals == {"upload_auto_log": 5}, (
        "the handler's refusal arms that clean up moved: %r -- the five are "
        "the deadline, the cancellation, the re-check, the cap at the "
        "re-check and the failed INSERT" % (refusals,))

    site = "        gone = await _release_marked_blob_off_loop(own)\n"
    assert src.count(site) == 1, src.count(site)
    mutant = src.replace(site, "        gone = _release_marked_blob(own)\n")
    assert [owner for owner, _line in _on_loop_release_calls(mutant)] == [
        "_discard_for_refusal"], (
        "the refusals' cleanup taken on the loop was not found, so the "
        "empty result above proves nothing")
    twin = src.replace(
        site, "        gone = (await _release_marked_blob_off_loop(own))\n")
    assert _on_loop_release_calls(twin) == [], (
        "the inert twin was reported, so the control above is reacting to the "
        "edit rather than to where the call runs")


# THE AUTOMATIC UPLOAD'S HOPS THAT ROUND 7'S SWEEP MOVED: the coroutine each
# is in, its site, the edit that makes the same call on the loop, and an
# inert twin. The free-space reading is in the reserve section, which the
# live handler calls by name; the other two are in the handler itself --
# inside the account's turn since round 8, so four columns deeper, and on
# the module's volume pool with a ceiling (R7-M4).
_AUTO_HOPS = {
    "directory": (
        "upload_auto_log",
        "            path = await _hop(_VOLUME_POOL, AUTO_LOG_VOLUME_WAIT_S,\n"
        "                              _bug_report_log_path, str(report_id))\n",
        "            path = _bug_report_log_path(str(report_id))\n",
        "            path = await _hop(_VOLUME_POOL, AUTO_LOG_VOLUME_WAIT_S,\n"
        "                              _bug_report_log_path, \"%s\" % (report_id,))\n"),
    "free-space": (
        "_reserve_stamp_and_write",
        "        free = await _hop(_VOLUME_POOL, _span_budget(span_deadline),\n"
        "                          _free_bytes, volume)\n",
        "        free = _free_bytes(volume)\n",
        "        free = await _hop(_VOLUME_POOL, _span_budget(span_deadline),\n"
        "                          _free_bytes, *(volume,))\n"),
    "marker-clear": (
        "upload_auto_log",
        "                await _hop_through(_VOLUME_POOL, AUTO_LOG_VOLUME_WAIT_S,\n"
        "                                   _clear_marker, own)\n",
        "                _clear_marker(own)\n",
        "                await _hop_through(_VOLUME_POOL, AUTO_LOG_VOLUME_WAIT_S,\n"
        "                                   _clear_marker, *(own,))\n"),
}


@pytest.mark.parametrize("hop", ["directory", "free-space", "marker-clear"])
def test_an_automatic_upload_on_a_slow_volume_does_not_stall_other_requests(
        logdir, verified, monkeypatch, hop):
    """R6-M3'S CLASS IN THE AUTOMATIC PATH: EVERY CALL IT MAKES ON THE VOLUME
    RUNS OFF THE EVENT LOOP.

    The automatic upload's stamp, write and cleanups already ran on worker
    threads. Round 7's sweep of the class found three calls that did not:
    the directory's creation (`_bug_report_log_path`), the reserve's
    free-space reading (`_free_bytes`, a `statvfs` on the volume) and the
    marker's clear after the commit (`_clear_marker`). The free-space
    reading was found only by the class test's derived reading below, which
    follows the modules' own call graph rather than a list of names.

    The player attachment's witness, over this path: an unrelated request
    every 10 ms on the same loop, a volume whose every call takes `DELAY`,
    and a bound of half of one call. THE CONTROL makes the hop's call on the
    loop at its own site and must break the bound; the INERT TWIN must not.
    """
    DELAY, BOUND = 0.5, 0.25
    owner, site, on_loop, twin = _AUTO_HOPS[hop]
    # This case's own free-space figure rather than the seat's disk, and a
    # reserve lock of its own, both BEFORE the volume is slowed: a mutant
    # runs in a copy of the module's globals taken when it is built.
    monkeypatch.setattr(auto_logs, "_free_bytes", lambda d: 10 ** 12)
    monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
    _slow_volume(monkeypatch, DELAY)
    live_section = auto_logs._reserve_stamp_and_write

    def _upload(handler):
        return asyncio.run(_unrelated_waits_while(
            lambda: handler(_request(), _ok_db())))

    def _with(replacement):
        """The handler with this hop's site replaced: in `upload_auto_log`
        itself, or in the section the live handler calls by name."""
        if owner == "upload_auto_log":
            return _handler_mutant([(site, replacement)])
        monkeypatch.setattr(auto_logs, owner,
                            _exec_mutant(live_section, site, replacement))
        return auto_logs.upload_auto_log

    out, worst = _upload(auto_logs.upload_auto_log)
    live = worst
    assert out["log_persisted"] is True, out
    assert worst < BOUND, (
        "an unrelated request finished %.3fs late while one automatic upload "
        "was stored over a volume taking %.1fs per call; the bound is %.2fs, "
        "so a call of this path is still on the event loop"
        % (worst, DELAY, BOUND))

    out, worst = _upload(_with(on_loop))
    control = worst
    assert out["log_persisted"] is True, out
    assert worst >= BOUND, (
        "with the %s hop put back on the event loop the unrelated request "
        "was only %.3fs late, inside the %.2fs bound although one call takes "
        "%.1fs -- the witness cannot see a stall, so its GREEN above means "
        "nothing" % (hop, worst, BOUND, DELAY))

    out, worst = _upload(_with(twin))
    assert out["log_persisted"] is True, out
    assert worst < BOUND, (
        "the inert twin of the %s hop stalled the unrelated request %.3fs, so "
        "the control above is reacting to the edit rather than to the hop"
        % (hop, worst))
    print("WITNESS automatic %s: live %.3fs, on-loop control %.3fs, inert "
          "twin %.3fs -- bound %.2fs, one call %.1fs"
          % (hop, live, control, worst, BOUND, DELAY))


# THE VOLUME, AS THE CLASS TEST BELOW READS IT. A call reaches the volume
# when it is one of these primitives, or a call of a plain function -- of
# either module, at any depth -- whose own body reaches it, followed through
# the modules' call graph to a fixed point. DERIVED, not listed: a helper
# added later that unlinks, flushes, measures or creates a directory joins
# the class without this test being edited, which is how the reserve's
# free-space reading was found after a list of names had missed it.
_OS_ON_THE_VOLUME = frozenset({
    "open", "fsync", "fdatasync", "unlink", "remove", "rename", "replace",
    "mkdir", "makedirs", "rmdir", "removedirs", "stat", "lstat", "scandir",
    "listdir", "walk", "statvfs", "chmod", "utime", "link", "symlink",
    "truncate", "ftruncate"})
_PATH_ON_THE_VOLUME = frozenset({
    "mkdir", "unlink", "rmdir", "touch", "iterdir", "read_bytes",
    "write_bytes", "read_text", "write_text", "is_file", "is_dir", "lstat",
    # Round 8: the admin log readers' helper reaches the volume through
    # these three, which the list above did not know -- `Path.exists`,
    # `Path.stat` and `gzip.open` (any `X.open`) -- so the derivation could
    # not see it. Each is a call on the volume wherever it appears.
    "exists", "stat", "open"})


def _calls_in(node):
    """Every call `node` makes ITSELF. A nested function or lambda runs only
    when something calls it, and the call graph follows that call."""
    out, stack = [], list(ast.iter_child_nodes(node))
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(n, ast.Call):
            out.append(n)
        stack.extend(ast.iter_child_nodes(n))
    return out


def _is_volume_primitive(call):
    f = call.func
    if isinstance(f, ast.Name):
        return f.id == "open"
    if not isinstance(f, ast.Attribute):
        return False
    if isinstance(f.value, ast.Name) and f.value.id == "os":
        return f.attr in _OS_ON_THE_VOLUME
    if isinstance(f.value, ast.Name) and f.value.id == "shutil":
        return True
    return f.attr in _PATH_ON_THE_VOLUME


def _callee_name(call):
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
            and f.value.id in ("_auto_logs", "auto_logs")):
        return f.attr
    return None


def _volume_functions(*trees):
    """The name of every plain function, at any depth of these modules,
    whose own body reaches the volume -- computed to a fixed point."""
    defs = {}
    for tree in trees:
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef):
                defs.setdefault(n.name, []).append(n)
    touching, grew = set(), True
    while grew:
        grew = False
        for name, nodes in defs.items():
            if name not in touching and any(
                    _is_volume_primitive(c) or _callee_name(c) in touching
                    for d in nodes for c in _calls_in(d)):
                touching.add(name)
                grew = True
    return touching


def _volume_calls_on_the_loop(source, touching):
    """(coroutine, line, call) for every call a coroutine of `source` makes
    ITSELF that reaches the volume."""
    found = []
    for n in ast.walk(ast.parse(source)):
        if isinstance(n, ast.AsyncFunctionDef):
            for c in _calls_in(n):
                if _is_volume_primitive(c) or _callee_name(c) in touching:
                    found.append((n.name, c.lineno, ast.unparse(c)))
    return sorted(found)


def test_no_writer_makes_a_call_on_the_volume_from_the_event_loop():
    """ROUND 7: M3'S CLASS IN BOTH WRITERS, READ FROM THE SOURCE (#432).

    The api runs one asynchronous worker (#125), so a call on the volume made
    by a coroutine ITSELF blocks every other request for as long as the
    volume takes. M3 flagged the player attachment's durable sequence; the
    class is every call either writer makes on the volume. Round 7 moved
    five more onto worker threads: the directory's creation and the marker's
    clear after the commit, in both writers, and the automatic reserve's
    free-space reading. Round 8 swept the class once more (R7-M4, #432):
    the two admin log readers, which read the same volume, and the three
    primitives through which they reach it and the derivation had not
    known.

    THE READING covers every coroutine in `auto_logs` -- the automatic
    upload, its section, the cleanup helpers, the retention pass and the
    orphan sweep -- the player handler and the two admin log readers, and
    it must find nothing. What
    reaches the volume is DERIVED (`_volume_functions`), so the derivation
    is checked first: every helper a hop hands to a thread must be in it,
    or an empty reading could be an unread call. THE CONTROLS put each moved
    call, and each earlier hop, back on the loop at its own site, and each
    must be found in the coroutine it was put in; the INERT TWIN at every
    site must not be found. The runtime witnesses above are the behavioural
    half of the same claim.
    """
    main_src = inspect.getsource(main)
    auto_src = inspect.getsource(auto_logs)
    touching = _volume_functions(ast.parse(main_src), ast.parse(auto_src))
    handler_src = textwrap.dedent(inspect.getsource(main.submit_bug_report))

    must = {"_bug_report_log_path", "_free_bytes", "_clear_marker",
            "_release_marked_blob", "_guarded_stamp", "_guarded_write",
            "_unlink_if_present", "_store_attachment", "_discard_partial",
            "_read_bug_log_sync", "_unlink_due_blobs",
            "_marker_candidates", "_resolve_marker_candidates"}
    assert must <= touching, (
        "the derived reading no longer knows that %r reach the volume, so an "
        "empty result below could be an unread call" % sorted(must - touching))

    # THE TWO ADMIN LOG READERS, SINCE ROUND 8. They read the same volume
    # the writers write, so R7-M4's sweep moved them onto the volume pool
    # (#432), and the reading covers them like the writers.
    readers = {name: textwrap.dedent(inspect.getsource(getattr(main, name)))
               for name in ("get_bug_report", "download_bug_report_log")}
    for label, src in (("auto_logs", auto_src), ("submit_bug_report", handler_src),
                       *readers.items()):
        assert _volume_calls_on_the_loop(src, touching) == [], (
            "a coroutine in %s makes a call on the volume itself, on the event "
            "loop: %r" % (label, _volume_calls_on_the_loop(src, touching)))

    controls = [(auto_src, owner, site, on_loop, twin)
                for owner, site, on_loop, twin in _AUTO_HOPS.values()]
    controls.append((
        auto_src, "_discard_for_refusal",
        "        gone = await _release_marked_blob_off_loop(own)\n",
        "        gone = _release_marked_blob(own)\n",
        "        gone = (await _release_marked_blob_off_loop(own))\n"))
    controls += [(handler_src, "submit_bug_report", site, on_loop, twin)
                 for _order, site, on_loop, twin in _PLAYER_HOPS.values()]
    for reader, pad in (("get_bug_report", " " * 12),
                        ("download_bug_report_log", " " * 8)):
        site = (pad + "raw = await _auto_logs._hop(\n"
                + pad + "    _auto_logs._VOLUME_POOL, "
                "_auto_logs.AUTO_LOG_VOLUME_WAIT_S,\n"
                + pad + "    _read_bug_log_sync, str(path))\n")
        controls.append((
            readers[reader], reader, site,
            pad + "raw = _read_bug_log_sync(str(path))\n",
            site.replace("str(path))", "\"%s\" % (path,))")))
    assert len(controls) == 10, len(controls)
    for src, owner, site, on_loop, twin in controls:
        own_src = inspect.getsource(getattr(
            auto_logs if src is auto_src else main, owner))
        assert own_src.count(site) == 1 and src.count(site) == 1, (
            "the site occurs %d time(s) in %s and %d in the source read, not "
            "once each -- re-derive it: %r"
            % (own_src.count(site), owner, src.count(site), site))
        found = _volume_calls_on_the_loop(src.replace(site, on_loop), touching)
        assert [f[0] for f in found] == [owner], (
            "the call put back on the loop at %r was not found in %s (%r), so "
            "the empty reading above proves nothing about that site"
            % (site.strip(), owner, found))
        assert _volume_calls_on_the_loop(src.replace(site, twin), touching) == [], (
            "the inert twin at %r was reported, so the control is reacting to "
            "the edit rather than to where the call runs" % (site.strip(),))


# ── ROUND 8: NO WAIT HOLDS A POOLED CONNECTION, AND EVERY WAIT HAS A CEILING ──
#
# R7-M4 found that thirty legitimate concurrent uploads could retain all
# 20 + 10 connections of the main pool: both writers kept one transaction open
# across every wait on the volume, and none of those waits had a ceiling. The
# tests below hold the three halves of the fix, each with a control that puts
# the round-7 shape back at one site and an inert twin at the same site
# (#342/#391): the session's transaction is ENDED before each wait (the pool
# witness); every wait has a CEILING and answers the promised status past it;
# and the exclusion the open transaction used to carry across the wait -- one
# upload per account at a time -- is carried by the account's turn, which has
# a ceiling of its own.
#
# THE POOL HERE IS A MODEL, AND WHAT IT MODELS IS STATED. `AsyncSession` takes
# a connection at the first statement of a transaction and gives it back when
# the transaction ends or the session closes; `_ModelPool` is a pool of the
# production size whose checkout waits a bounded time and then raises. This
# suite runs with no database, so that `_end_transaction` returns a REAL
# session's connection to a REAL pool is witnessed separately, against the
# local PostgreSQL, in the round's evidence log.


class _ModelPool:
    """The application's pool as the two writers meet it: `size` connections
    (`pool_size=20` + `max_overflow=10` in database.py) and a checkout that
    waits at most `timeout` seconds for one and then raises, which is what
    QueuePool's `pool_timeout` does. `out` is how many are checked out now."""

    def __init__(self, size=30, timeout=0.5):
        self.size = size
        self.timeout = timeout
        self.out = 0
        self._free = None

    async def checkout(self):
        if self._free is None:          # made inside the loop that uses it
            self._free = asyncio.Semaphore(self.size)
        try:
            await asyncio.wait_for(self._free.acquire(), self.timeout)
        except (asyncio.TimeoutError, TimeoutError):
            raise TimeoutError("QueuePool limit of size %d reached, "
                               "connection timed out" % self.size) from None
        self.out += 1

    def checkin(self):
        self.out -= 1
        self._free.release()


class _Pooled:
    """A session that holds a connection the way `AsyncSession` does: taken
    by the first statement of a transaction, given back when the transaction
    ends -- a commit, a rollback -- or the session closes. A commit that
    raises keeps it until the rollback that follows, as the real one does."""

    pool = None
    held = False

    async def _take(self):
        if not self.held:
            await self.pool.checkout()
            self.held = True

    def _give(self):
        if self.held:
            self.held = False
            self.pool.checkin()

    async def execute(self, statement, params=None):
        await self._take()
        return await super().execute(statement, params)

    async def commit(self):
        await super().commit()
        self._give()

    async def rollback(self):
        try:
            await super().rollback()
        finally:
            self._give()

    async def close(self):
        self._give()


class _PooledScripted(_Pooled, Scripted):
    """`Scripted`, holding one of `pool`'s connections while a transaction
    is open."""


class _PooledReportSession(_Pooled, _ReportSession):
    """`_ReportSession`, holding one of `pool`'s connections while a
    transaction is open; its flush and its refresh are statements too."""

    async def flush(self):
        await self._take()
        return await super().flush()

    async def refresh(self, obj):
        await self._take()
        return await super().refresh(obj)


async def _until(predicate, cap_s=10.0, step=0.01):
    """Poll `predicate` on the loop for at most `cap_s` seconds -- never a
    bare wait (#361) -- and answer whether it came true."""
    for _ in range(max(1, int(cap_s / step))):
        if predicate():
            return True
        await asyncio.sleep(step)
    return bool(predicate())


class _Held:
    """`fn`, held IN THE THREAD THAT CALLS IT until `release()`: a volume (or
    a CPU) that is not answering, as the worker that made the call meets it.
    With `first_only`, only the first call is held.

    It counts the calls that entered and the ones that have finished, so a
    test can let the held thread END before its event loop closes
    (`drained`): a worker that finishes after its loop has closed cannot
    hand its result back, and a ceiling that ended the WAIT never ended the
    work. The hold itself is bounded, so a failing test cannot leave a
    thread parked for ever."""

    def __init__(self, fn, *, first_only=False):
        import threading
        self._threading = threading
        self.fn = fn
        self.first_only = first_only
        self.reset()

    def reset(self):
        self.gate = self._threading.Event()
        self.count_lock = self._threading.Lock()
        self.entered = 0
        self.finished = 0

    def __call__(self, *a, **kw):
        with self.count_lock:
            self.entered += 1
            nth = self.entered
        try:
            if nth == 1 or not self.first_only:
                self.gate.wait(30.0)
            return self.fn(*a, **kw)
        finally:
            with self.count_lock:
                self.finished += 1

    def release(self):
        self.gate.set()

    async def drained(self, cap_s=10.0):
        self.release()
        done = await _until(lambda: self.finished >= self.entered, cap_s)
        await asyncio.sleep(0.05)       # the worker's hand-back to the loop
        return done


def _main_mutant(name, pairs):
    """`main.<name>` with every (anchor, replacement) applied, compiled
    WITHOUT its route decorator -- executing it would register a second copy
    of the route on the live application -- against a COPY of main's
    globals. Each anchor is asserted to be one site inside the function's own
    span first (#432/#279)."""
    src = textwrap.dedent(inspect.getsource(getattr(main, name)))
    head, _, rest = src.partition("\n")
    assert head.startswith("@app."), (
        "%s no longer starts with its route decorator, so this harness is "
        "stripping the wrong line: %r" % (name, head))
    for anchor, replacement in pairs:
        assert rest.count(anchor) == 1, (
            "the mutation anchor occurs %d time(s) in %s, not once: %r"
            % (rest.count(anchor), name, anchor))
        rest = rest.replace(anchor, replacement)
    namespace = dict(vars(main))
    exec(compile(rest, "<mutant:%s>" % name, "exec"), namespace)
    return namespace[name]


# The line that ends T1 in each writer, with the line after it as context so
# each anchor is one site.
_AUTO_T1_END = ("        await _end_transaction(db)\n\n"
                "        if count >= AUTO_LOG_PER_STEAM_PER_DAY:\n")
_PLAYER_T1_END = ("    await _auto_logs._end_transaction(db)\n\n"
                  "    log_filename: str | None = None\n")


def test_thirty_concurrent_uploads_cannot_retain_the_pool(logdir, verified,
                                                          monkeypatch):
    """R7-M4 / B15: THIRTY UPLOADS WAITING ON THE VOLUME HOLD NO CONNECTION.

    Fifteen automatic uploads and fifteen player reports, each for a
    different account, arrive together while the volume does not answer:
    the blob directory's resolution -- the first call either writer makes on
    the volume, and the hop R7-M4 named -- is held in its worker thread until
    this test lets it go. Thirty is the production pool's size exactly, so a
    writer that kept its transaction open across that wait would hold every
    connection the box has, and anything else that needs one -- a queue
    join, a match report -- would wait out the pool's timeout and fail.

    Read while all thirty are at the volume (its four threads inside the
    held call, the other twenty-six queued behind them):
      * the pool: how many connections are checked out -- none may be;
      * each session's last event: its transaction was ENDED (all thirty),
        not merely idle;
      * an unrelated checkout: served at once.
    Then the volume answers and all thirty land: the waits QUEUED, they were
    not refused.

    CONTROL: the two lines that end T1 -- the automatic upload's and the
    player report's -- removed, which is the round-7 shape: the same thirty
    then hold all thirty connections and the unrelated checkout times out.
    TWIN: the same two lines spelled differently, which changes nothing.
    """
    monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
    monkeypatch.setattr(auto_logs, "_BLOB_WRITE_STARTED", [0.0])
    monkeypatch.setattr(auto_logs, "_free_bytes", lambda directory: 10 ** 12)
    monkeypatch.setattr(main, "_is_admin", _no_admin)
    monkeypatch.setattr(main, "_mark_mod_seen", _noop_mark)
    held = _Held(main._bug_report_log_path)
    monkeypatch.setattr(main, "_bug_report_log_path", held)
    # Thirty synthetic accounts, derived rather than written out: every
    # Steam-shaped literal in this file must be one of `_SYNTHETIC_IDS`.
    accounts = [str(int(STEAM) + 100 + i) for i in range(30)]
    volume = auto_logs._VOLUME_POOL

    async def drive(auto_handler, report_handler):
        held.reset()
        # ONE RESERVE LOCK PER EVENT LOOP. Fifteen sections contend for
        # it, and a contended asyncio.Lock is bound to the loop it was
        # contended on; the next drive's loop would meet it as 'bound to
        # a different event loop'.
        monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
        pool = _ModelPool(size=30, timeout=0.5)
        autos, reports, tasks = [], [], []
        for sid in accounts[:15]:
            db = _PooledScripted({SESSION_KEY: [[{"steam_id": sid}]],
                                  COUNT_KEY: [[_bucket(0)]],
                                  PLAYER_KEY: [[{"id": PID}]],
                                  INSERT_KEY: [[{"bug_number": 4242}]]})
            db.pool = pool
            autos.append(db)
            tasks.append(asyncio.create_task(
                auto_handler(_request(_body(steam_id=sid)), db)))
        for sid in accounts[15:]:
            db = _PooledReportSession({"FROM bug_reports": [[{"count": 0}]]})
            db.pool = pool
            reports.append(db)
            tasks.append(asyncio.create_task(report_handler(
                schemas.BugReportRequest(steam_id=sid, description="it broke",
                                         log_text="a log"),
                _request(), db)))
        try:
            # ALL THIRTY AT THE VOLUME: its four threads inside the held
            # call and twenty-six calls queued behind them (the executor's
            # own queue, read directly -- nothing else submits to this pool
            # during the test).
            await _until(lambda: held.entered == 4
                         and volume._work_queue.qsize() == 26)
            seen = {"inside": held.entered,
                    "queued": volume._work_queue.qsize(),
                    "out": pool.out,
                    "ended": sum(1 for d in autos + reports
                                 if d.events and d.events[-1] == "ROLLBACK")}
            try:
                await pool.checkout()
            except TimeoutError:
                seen["unrelated"] = "timed out"
            else:
                pool.checkin()
                seen["unrelated"] = "served"
        finally:
            held.release()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for d in autos + reports:
            await d.close()             # get_db's close, at the request's end
        await held.drained()
        seen["landed"] = sum(1 for r in results if isinstance(r, dict)
                             and r.get("log_persisted") is True)
        seen["failed"] = [repr(r) for r in results if not isinstance(r, dict)]
        seen["after"] = pool.out
        return seen

    live = _run(drive(auto_logs.upload_auto_log, main.submit_bug_report))
    assert (live["inside"], live["queued"]) == (4, 26), (
        "the thirty uploads were not all waiting at the volume when it was "
        "read (%r), so what follows would describe some other moment"
        % (live,))
    assert live["out"] == 0 and live["ended"] == 30, (
        "%d connection(s) checked out and %d of 30 transactions ended while "
        "thirty uploads waited on the volume; every writer ends its "
        "transaction before the wait (R7-M4)" % (live["out"], live["ended"]))
    assert live["unrelated"] == "served", live
    assert live["landed"] == 30 and live["failed"] == [], (
        "the waits were meant to queue and land once the volume answered: %r"
        % (live,))
    assert live["after"] == 0, live

    control = _run(drive(
        _handler_mutant([(_AUTO_T1_END,
                          "\n        if count >= AUTO_LOG_PER_STEAM_PER_DAY:\n")]),
        _report_mutant(_PLAYER_T1_END,
                       "\n    log_filename: str | None = None\n")))
    assert (control["inside"], control["queued"]) == (4, 26), control
    assert control["out"] == 30 and control["ended"] == 0, (
        "with T1 left open across the wait the thirty were expected to hold "
        "the whole pool; they held %d with %d transaction(s) ended, so the "
        "reading above is not measuring retention" % (control["out"],
                                                      control["ended"]))
    assert control["unrelated"] == "timed out", (
        "the round-7 shape was expected to starve an unrelated request of a "
        "connection: %r" % (control,))
    assert control["landed"] == 30, control

    twin = _run(drive(
        _handler_mutant([(_AUTO_T1_END,
                          "        await _end_transaction(*(db,))\n\n"
                          "        if count >= AUTO_LOG_PER_STEAM_PER_DAY:\n")]),
        _report_mutant(_PLAYER_T1_END,
                       "    await _auto_logs._end_transaction(*(db,))\n\n"
                       "    log_filename: str | None = None\n")))
    assert (twin["out"], twin["ended"], twin["unrelated"], twin["landed"]) == (
        0, 30, "served", 30), (
        "the inert twin moved the reading, so the control is reacting to the "
        "edit rather than to the transaction being left open: %r" % (twin,))


def test_a_second_upload_for_one_account_waits_its_turn_and_no_longer(
        logdir, verified, monkeypatch, capsys):
    """THE EXCLUSION THE TRANSACTION USED TO CARRY, CARRIED WITHOUT ONE.

    Until round 8 the per-account advisory lock was held from the count that
    admits an upload to its commit, inside one transaction, so a second
    upload for the same account waited on the DATABASE -- holding a
    connection of its own while it did. Since round 8 (R7-M4) T1 ends before
    the volume work and the exclusion across the span is the account's TURN
    (`_account_turn`): an asyncio lock that costs no connection, waited for
    at most `AUTO_LOG_ACCOUNT_WAIT_S` and refused 503 past it.

    Driven: the first upload is held in its directory hop, so its turn is
    held; a second for the same account arrives. It is refused within the
    ceiling -- not after the first has finished -- without having taken the
    advisory lock, and with its last transaction ended before it waited.

    CONTROL: the ceiling removed from the turn's wait, and the second waits
    for as long as the first holds the volume. TWIN: the same wait with its
    ceiling passed by keyword.
    """
    WAIT, HOLD = 0.3, 1.5
    monkeypatch.setattr(auto_logs, "AUTO_LOG_ACCOUNT_WAIT_S", WAIT)
    monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
    monkeypatch.setattr(auto_logs, "_BLOB_WRITE_STARTED", [0.0])
    monkeypatch.setattr(auto_logs, "_free_bytes", lambda directory: 10 ** 12)
    held = _Held(main._bug_report_log_path, first_only=True)
    monkeypatch.setattr(main, "_bug_report_log_path", held)
    site = ("            await asyncio.wait_for(turn.lock.acquire(),\n"
            "                                   AUTO_LOG_ACCOUNT_WAIT_S)\n")
    real_turn = auto_logs._account_turn

    async def drive():
        held.reset()
        monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
        first_db, second_db = _ok_db(), _ok_db()
        first = asyncio.create_task(
            auto_logs.upload_auto_log(_request(), first_db))
        assert await _until(lambda: held.entered == 1), (
            "the first upload never reached the volume")
        asyncio.get_running_loop().call_later(HOLD, held.release)
        at = time.monotonic()
        try:
            second = await auto_logs.upload_auto_log(_request(), second_db)
        except HTTPException as ex:
            second = ex
        waited = time.monotonic() - at
        first = await first
        await held.drained()
        return first, second, waited, second_db

    first, second, waited, second_db = _run(drive())
    assert first["log_persisted"] is True, first
    assert isinstance(second, HTTPException) and second.status_code == 503, (
        "the second upload for the same account was answered %r" % (second,))
    assert waited < HOLD - 0.5, (
        "the second upload waited %.2fs: past its %ss ceiling and on into the "
        "first upload's %ss hold" % (waited, WAIT, HOLD))
    assert not second_db.sql_for(LOCK_KEY), (
        "the refused upload took the advisory lock, which it must not reach "
        "before its turn")
    assert second_db.events[-1] == "ROLLBACK", (
        "the refused upload waited with a transaction open: %r"
        % (second_db.events,))
    out = capsys.readouterr().out
    assert ("already has an upload in flight that did not decide within "
            "%ss" % WAIT) in out, out

    monkeypatch.setattr(auto_logs, "_account_turn", _exec_mutant(
        real_turn, site, "            await turn.lock.acquire()\n"))
    first, second, waited, _db = _run(drive())
    assert isinstance(second, dict) and second["log_persisted"] is True, second
    assert waited >= HOLD - 0.1, (
        "with no ceiling on the turn the second upload was expected to wait "
        "out the first's hold; it waited %.2fs, so the red above is not about "
        "the ceiling" % (waited,))

    monkeypatch.setattr(auto_logs, "_account_turn", _exec_mutant(
        real_turn, site,
        "            await asyncio.wait_for(turn.lock.acquire(),\n"
        "                                   timeout=AUTO_LOG_ACCOUNT_WAIT_S)\n"))
    first, second, waited, _db = _run(drive())
    assert isinstance(second, HTTPException) and second.status_code == 503, second
    assert waited < HOLD - 0.5, waited


# EVERY HOP BEFORE THE MARKED SPAN, with its ceiling: who owns the held call,
# the ceiling's name, the site, the site with the ceiling lifted, the inert
# twin, and the line its refusal prints (`%s` is the ceiling).
_AUTO_PRE_SPAN_HOPS = {
    "directory": (
        "main", "_bug_report_log_path", "AUTO_LOG_VOLUME_WAIT_S",
        "            path = await _hop(_VOLUME_POOL, AUTO_LOG_VOLUME_WAIT_S,\n",
        "            path = await _hop(_VOLUME_POOL, 10 ** 6,\n",
        "            path = await _hop(_VOLUME_POOL, float(AUTO_LOG_VOLUME_WAIT_S),\n",
        "the blob directory could not be resolved within %ss for "),
    "scrub": (
        "main", "_scrub_pass_one", "AUTO_LOG_CPU_WAIT_S",
        "            _CPU_POOL, AUTO_LOG_CPU_WAIT_S, _scrub_pass_one, log_blob)\n",
        "            _CPU_POOL, 10 ** 6, _scrub_pass_one, log_blob)\n",
        "            _CPU_POOL, float(AUTO_LOG_CPU_WAIT_S), _scrub_pass_one, log_blob)\n",
        "did not finish within %ss a pass; nothing was written"),
    "gzip": (
        "auto_logs", "_compress_blob", "AUTO_LOG_CPU_WAIT_S",
        "        data = await _hop(_CPU_POOL, AUTO_LOG_CPU_WAIT_S, _compress_blob,\n",
        "        data = await _hop(_CPU_POOL, 10 ** 6, _compress_blob,\n",
        "        data = await _hop(_CPU_POOL, float(AUTO_LOG_CPU_WAIT_S), _compress_blob,\n",
        "did not finish within %ss a pass; nothing was written"),
}


@pytest.mark.parametrize("hop", sorted(_AUTO_PRE_SPAN_HOPS))
def test_an_automatic_upload_refuses_503_when_a_hop_before_its_span_does_not_return(
        logdir, verified, monkeypatch, capsys, hop):
    """R7-M4: EVERY WAIT BEFORE THE MARKED SPAN HAS A CEILING, AND PAST IT
    THE ANSWER IS THE PROMISED 503 -- not a request that never answers.

    Three hops precede the span: the scrub and the gzip on the CPU pool, and
    the blob directory's resolution on the volume pool (the hop R7-M4 named).
    Each is held in its thread past its ceiling. The upload must answer 503
    within the ceiling, having written nothing -- no row, no blob, no marker
    -- and with its transaction ENDED before the wait: the last thing its
    session did was a rollback. The two CPU hops come before admission, so
    their refusal has not taken the advisory lock either.

    CONTROL: the ceiling lifted at that one site, and the upload waits for
    as long as the call is held and then lands. TWIN: the same ceiling
    spelled `float(...)`.
    """
    owner_name, attr, ceiling, site, lifted, twin, line = _AUTO_PRE_SPAN_HOPS[hop]
    owner = main if owner_name == "main" else auto_logs
    HOLD, CEILING = 1.0, 0.2
    monkeypatch.setattr(auto_logs, ceiling, CEILING)
    monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
    monkeypatch.setattr(auto_logs, "_BLOB_WRITE_STARTED", [0.0])
    held = _Held(getattr(owner, attr))
    monkeypatch.setattr(owner, attr, held)

    async def drive(handler):
        held.reset()
        asyncio.get_running_loop().call_later(HOLD, held.release)
        db = _ok_db()
        at = time.monotonic()
        try:
            out = await handler(_request(), db)
        except HTTPException as ex:
            out = ex
        took = time.monotonic() - at
        await held.drained()
        return out, took, db

    out, took, db = _run(drive(auto_logs.upload_auto_log))
    assert isinstance(out, HTTPException) and out.status_code == 503, out
    assert took < HOLD, (
        "the %s hop's refusal took %.2fs, past the %ss hold it was meant to "
        "refuse inside" % (hop, took, HOLD))
    assert line % CEILING in capsys.readouterr().out
    assert not db.sql_for(INSERT_KEY), "a refused upload INSERTed a row"
    assert _blobs(logdir) == [] and _markers(logdir) == [], (
        _blobs(logdir), _markers(logdir))
    assert db.events[-1] == "ROLLBACK", (
        "the %s hop was waited for with a transaction open: %r"
        % (hop, db.events))
    if hop != "directory":
        assert not db.sql_for(LOCK_KEY), (
            "a refusal before admission took the advisory lock")

    out, took, db = _run(drive(_handler_mutant([(site, lifted)])))
    assert isinstance(out, dict) and out["log_persisted"] is True, (
        "with the %s hop's ceiling lifted the upload was expected to wait and "
        "land; it answered %r, so the refusal above is not about the ceiling"
        % (hop, out))
    assert took >= HOLD - 0.05, took

    out, took, db = _run(drive(_handler_mutant([(site, twin)])))
    assert isinstance(out, HTTPException) and out.status_code == 503, out
    assert took < HOLD, took


def test_a_player_attachment_that_does_not_store_in_time_is_filed_without_it(
        logdir, monkeypatch, capsys):
    """R7-M4 ON THE PLAYER'S HALF: the store's wait has a ceiling, the report
    is still FILED, and the in-flight name outlives the answer until the last
    worker the request started has ENDED.

    The marker's stamp is held in its thread past `AUTO_LOG_VOLUME_WAIT_S`,
    under the claim's lock -- so the removal that follows the timeout, and
    the clear after the commit, both queue behind it and pass their own
    ceilings too. The report must be answered with `log_persisted` false and
    a row that NAMES the file with `log_bytes` NULL (nothing could prove the
    file gone before the row committed); the name must still be registered
    at the answer, because a worker of this request may yet create the
    marker; and once the stamp is let go, the three workers finish in their
    threads, nothing is left on the volume, and the name is released.

    CONTROL: the name released at the answer whatever is still running --
    the `if _running:` deferral removed -- and it is gone while the store is
    still held. TWIN: the same test spelled `len(...) > 0`.
    """
    monkeypatch.setattr(auto_logs, "AUTO_LOG_VOLUME_WAIT_S", 0.2)
    monkeypatch.setattr(main, "_is_admin", _no_admin)
    monkeypatch.setattr(main, "_mark_mod_seen", _noop_mark)
    held = _Held(auto_logs._stamp_marker)
    monkeypatch.setattr(auto_logs, "_stamp_marker", held)

    async def drive(handler):
        held.reset()
        db = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
        req = schemas.BugReportRequest(steam_id=STEAM, description="it broke",
                                       log_text="a log")
        out = await handler(req, _request(), db)
        report = db.added[0]
        name = report.log_filename
        registered_at_answer = name in auto_logs._MARKERS_IN_FLIGHT
        drained = await held.drained()
        released = await _until(
            lambda: name not in auto_logs._MARKERS_IN_FLIGHT, 5.0)
        return out, report, registered_at_answer, drained, released

    out, report, registered, drained, released = _run(
        drive(main.submit_bug_report))
    assert out["log_persisted"] is False, out
    assert report.log_filename and report.log_bytes is None, (
        report.log_filename, report.log_bytes)
    assert registered is True, (
        "the in-flight name was released at the answer while a worker of "
        "this request could still create its marker")
    assert drained and released, (drained, released)
    assert _blobs(logdir) == [] and _markers(logdir) == [], (
        _blobs(logdir), _markers(logdir))
    printed = capsys.readouterr().out
    assert ("did not finish within %ss" % 0.2) in printed, printed
    assert "was not cleared (TimeoutError)" in printed, printed

    out, report, registered, drained, released = _run(drive(_report_mutant(
        "            if _running:\n", "            if False:\n")))
    assert registered is False, (
        "with the deferral removed the name was expected to be released at "
        "the answer, so the reading above is not about the deferral")
    assert drained, drained

    out, report, registered, drained, released = _run(drive(_report_mutant(
        "            if _running:\n", "            if len(_running) > 0:\n")))
    assert registered is True and drained and released, (
        registered, drained, released)


def test_a_player_attachment_whose_directory_does_not_resolve_is_filed_as_lost(
        logdir, monkeypatch, capsys):
    """The player's directory hop spends the ATTACHMENT'S deadline -- one
    deadline of `AUTO_LOG_VOLUME_WAIT_S` for the directory and the store
    together -- and past it the report is filed with the attachment
    recorded as LOST: `log_bytes = 0`, no file named, nothing on the
    volume, rather than the request waiting on a volume that does not
    answer.

    CONTROL: the attachment's deadline lifted, and the report waits the
    hold out and lands with its log. (Lifting only the directory hop's
    budget is not the control: the store after it spends the same
    deadline, and meets it expired.) TWIN: the same deadline spelled
    `float(...)`.
    """
    HOLD = 1.0
    site = ("                attach_deadline = (time.monotonic()\n"
            "                                   + _auto_logs.AUTO_LOG_VOLUME_WAIT_S)\n")
    monkeypatch.setattr(auto_logs, "AUTO_LOG_VOLUME_WAIT_S", 0.2)
    monkeypatch.setattr(main, "_is_admin", _no_admin)
    monkeypatch.setattr(main, "_mark_mod_seen", _noop_mark)
    held = _Held(main._bug_report_log_path)
    monkeypatch.setattr(main, "_bug_report_log_path", held)

    async def drive(handler):
        held.reset()
        asyncio.get_running_loop().call_later(HOLD, held.release)
        db = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
        req = schemas.BugReportRequest(steam_id=STEAM, description="it broke",
                                       log_text="a log")
        at = time.monotonic()
        out = await handler(req, _request(), db)
        took = time.monotonic() - at
        await held.drained()
        return out, db.added[0], took

    out, report, took = _run(drive(main.submit_bug_report))
    assert out["log_persisted"] is False, out
    assert (report.log_filename, report.log_bytes) == (None, 0), (
        report.log_filename, report.log_bytes)
    assert took < HOLD, took
    assert _blobs(logdir) == [] and _markers(logdir) == []
    assert "log persistence FAILED" in capsys.readouterr().out

    out, report, took = _run(drive(_report_mutant(
        site, "                attach_deadline = (time.monotonic()\n"
              "                                   + 10 ** 6)\n")))
    assert out["log_persisted"] is True and took >= HOLD - 0.05, (out, took)

    out, report, took = _run(drive(_report_mutant(
        site, "                attach_deadline = (time.monotonic()\n"
              "                                   + float(_auto_logs.AUTO_LOG_VOLUME_WAIT_S))\n")))
    assert out["log_persisted"] is False and took < HOLD, (out, took)


def test_a_player_attachment_whose_gzip_does_not_finish_is_filed_as_lost(
        logdir, monkeypatch, capsys):
    """The player's gzip is a wait on the CPU pool with its own ceiling
    (`AUTO_LOG_CPU_WAIT_S`), and past it the report is FILED with the
    attachment recorded as lost -- `log_bytes = 0`, no file named, nothing on
    the volume and nothing registered -- instead of the request waiting on a
    pass that does not finish. The gzip runs before the attachment has a
    path, so there is nothing to remove: the line says no file was created.

    The compression is held in its thread past the ceiling, and let go
    afterwards so the worker ends before its loop closes.

    CONTROL: the ceiling lifted at that one site, and the report waits the
    hold out and lands with its log. TWIN: the same ceiling spelled
    `float(...)`.
    """
    HOLD, CEILING = 1.0, 0.2
    site = "                    _auto_logs._CPU_POOL, _auto_logs.AUTO_LOG_CPU_WAIT_S,\n"
    monkeypatch.setattr(auto_logs, "AUTO_LOG_CPU_WAIT_S", CEILING)
    monkeypatch.setattr(main, "_is_admin", _no_admin)
    monkeypatch.setattr(main, "_mark_mod_seen", _noop_mark)
    held = _Held(gzip.compress)

    class _HeldGzip:
        compress = staticmethod(held)
        open = staticmethod(gzip.open)

    monkeypatch.setattr(main, "_gzip", _HeldGzip)

    async def drive(handler):
        held.reset()
        asyncio.get_running_loop().call_later(HOLD, held.release)
        db = _ReportSession({"FROM bug_reports": [[{"count": 0}]]})
        req = schemas.BugReportRequest(steam_id=STEAM, description="it broke",
                                       log_text="a log")
        at = time.monotonic()
        out = await handler(req, _request(), db)
        took = time.monotonic() - at
        await held.drained()
        return out, db.added[0], took

    out, report, took = _run(drive(main.submit_bug_report))
    assert held.entered == 1, held.entered
    assert out["log_persisted"] is False, out
    assert (report.log_filename, report.log_bytes) == (None, 0), (
        report.log_filename, report.log_bytes)
    assert took < HOLD, (
        "the gzip's refusal took %.2fs, past the %ss hold it was meant to "
        "refuse inside" % (took, HOLD))
    assert _blobs(logdir) == [] and _markers(logdir) == [], (
        _blobs(logdir), _markers(logdir))
    assert not auto_logs._MARKERS_IN_FLIGHT, auto_logs._MARKERS_IN_FLIGHT
    printed = capsys.readouterr().out
    assert "log persistence FAILED" in printed and "no file was created" in printed, (
        printed)

    out, report, took = _run(drive(_report_mutant(
        site, "                    _auto_logs._CPU_POOL, 10 ** 6,\n")))
    assert out["log_persisted"] is True and took >= HOLD - 0.05, (
        "with the gzip's ceiling lifted the report was expected to wait the "
        "hold out and land with its log: %r after %.2fs, so the refusal above "
        "is not about the ceiling" % (out, took))
    assert report.log_filename and report.log_bytes, (
        report.log_filename, report.log_bytes)
    for p in list(logdir.iterdir()):
        p.unlink()

    out, report, took = _run(drive(_report_mutant(
        site, "                    _auto_logs._CPU_POOL, "
              "float(_auto_logs.AUTO_LOG_CPU_WAIT_S),\n")))
    assert out["log_persisted"] is False and took < HOLD, (out, took)
    assert (report.log_filename, report.log_bytes) == (None, 0), (
        report.log_filename, report.log_bytes)


def test_the_admin_log_readers_answer_when_the_volume_does_not(logdir, admin,
                                                               monkeypatch,
                                                               capsys):
    """Both admin readers read the blob on the auto-log module's VOLUME pool,
    since round 8, with a ceiling on the wait and their transaction ended
    first: a volume that does not answer is a 503 on the download and a read
    error on the detail pane, never a request that waits on it -- and never
    one that waits holding a connection.

    CONTROL: the ceiling lifted at each reader's site, and both wait the hold
    out and serve the log. TWIN: the same ceiling spelled `float(...)`.
    """
    HOLD = 1.0
    monkeypatch.setattr(auto_logs, "AUTO_LOG_VOLUME_WAIT_S", 0.2)
    name = "%s.log.gz" % (RID,)
    (logdir / name).write_bytes(gzip.compress(b"a stored log line"))
    held = _Held(main._read_bug_log_sync)
    monkeypatch.setattr(main, "_read_bug_log_sync", held)
    row_key = "SELECT id, bug_number, log_filename, log_bytes, created_at FROM bug_reports"
    when = datetime(2026, 9, 19, tzinfo=timezone.utc)
    detail_row = {"id": RID, "bug_number": 41, "player_id": None,
                  "steam_id": STEAM, "display_name": "Player",
                  "mod_version": "1.41.0", "game_version": "1.0.0",
                  "severity": "medium", "category": "gameplay",
                  "description": "d", "repro_steps": None,
                  "log_filename": name, "log_bytes": 10, "status": "open",
                  "triage_notes": None, "created_at": when,
                  "updated_at": None, "kind": "auto"}
    sites = {
        "download_bug_report_log": " " * 12,
        "get_bug_report": " " * 16,
    }

    def site_of(reader):
        return (sites[reader] + "_auto_logs._VOLUME_POOL, "
                "_auto_logs.AUTO_LOG_VOLUME_WAIT_S,\n")

    def edit(reader, ceiling):
        return (sites[reader] + "_auto_logs._VOLUME_POOL, %s,\n" % ceiling)

    async def drive(download, detail):
        held.reset()
        loop = asyncio.get_running_loop()
        loop.call_later(HOLD, held.release)
        ddb = Scripted({row_key: [[{"id": RID, "bug_number": 41,
                                    "log_filename": name, "log_bytes": 10,
                                    "created_at": when}]]})
        at = time.monotonic()
        try:
            got = await download(report_id=str(RID), admin_steam_id=STEAM,
                                 hmac_signature="s", db=ddb)
        except HTTPException as ex:
            got = ex
        d_took = time.monotonic() - at
        await held.drained()
        held.reset()
        loop.call_later(HOLD, held.release)
        pdb = Scripted({DETAIL_KEY: [[detail_row]], EVENTS_KEY: [[]]})
        at = time.monotonic()
        pane = await detail(report_id=str(RID), admin_steam_id=STEAM,
                            hmac_signature="s", include_log=True, db=pdb)
        p_took = time.monotonic() - at
        await held.drained()
        return got, d_took, ddb, pane, p_took, pdb

    got, d_took, ddb, pane, p_took, pdb = _run(drive(
        main.download_bug_report_log, main.get_bug_report))
    assert isinstance(got, HTTPException) and got.status_code == 503, got
    assert d_took < HOLD and p_took < HOLD, (d_took, p_took)
    assert ddb.events[-1] == "ROLLBACK" and len(ddb.events) == 2, (
        "the download read its row and then waited with the transaction "
        "open: %r" % (ddb.events,))
    assert pane["log_text"] == "[log read error: TimeoutError]", pane["log_text"]
    assert pdb.events[1] == "ROLLBACK" and DETAIL_KEY in pdb.events[0], (
        "the detail pane waited with its transaction open: %r" % (pdb.events,))
    assert ("did not return within %ss" % 0.2) in capsys.readouterr().out

    got, d_took, ddb, pane, p_took, pdb = _run(drive(
        _main_mutant("download_bug_report_log",
                     [(site_of("download_bug_report_log"),
                       edit("download_bug_report_log", "10 ** 6"))]),
        _main_mutant("get_bug_report",
                     [(site_of("get_bug_report"),
                       edit("get_bug_report", "10 ** 6"))])))
    assert not isinstance(got, HTTPException), got
    assert b"a stored log line" in got.body and d_took >= HOLD - 0.05, (
        got.body, d_took)
    assert pane["log_text"] == "a stored log line" and p_took >= HOLD - 0.05, (
        pane["log_text"], p_took)

    got, d_took, ddb, pane, p_took, pdb = _run(drive(
        _main_mutant("download_bug_report_log",
                     [(site_of("download_bug_report_log"),
                       edit("download_bug_report_log",
                            "float(_auto_logs.AUTO_LOG_VOLUME_WAIT_S)"))]),
        _main_mutant("get_bug_report",
                     [(site_of("get_bug_report"),
                       edit("get_bug_report",
                            "float(_auto_logs.AUTO_LOG_VOLUME_WAIT_S)"))])))
    assert isinstance(got, HTTPException) and got.status_code == 503, got
    assert pane["log_text"] == "[log read error: TimeoutError]", pane["log_text"]


class _InsertRefused(Scripted):
    """The INSERT raises (`fail_on`), and the session remembers that it was
    tried -- so a volume stub can refuse only what comes AFTER it."""

    insert_tried = False

    async def execute(self, statement, params=None):
        if INSERT_KEY in " ".join(str(statement).split()):
            self.insert_tried = True
        return await super().execute(statement, params)


_INSERT_ARM_CLEANUP = ("                await _end_transaction(db)\n"
                       "                outcome = await _discard_for_refusal(own)\n"
                       "                # ONE print statement, every outcome.")


def test_the_admin_log_scrub_holds_no_connection_and_answers_past_its_ceiling(
        logdir, admin, monkeypatch, capsys):
    """R7-M4'S CLASS IN THE READERS' SCRUB. Both admin readers pass the log
    through `_scrub_bug_log`: a regex pass, a purge probe against the
    database, a second regex pass. Since round 8 both passes run on the CPU
    pool under `AUTO_LOG_CPU_WAIT_S`, and the probe's transaction is ENDED
    before pass two -- so neither reader waits on a pass with a pooled
    connection checked out, and neither waits past the ceiling.

    Pass two is held in its thread. Read while it is held, on a model of the
    pool: NO connection is checked out by either reader, although the probe
    ran a statement just before. Past the ceiling the download answers 503
    and the pane reads a log read error, each well inside the hold.

    CONTROL (a): the probe's `_end_transaction` removed -- the probe's
    connection is then held across pass two, one checked out per reader.
    CONTROL (b): the ceiling lifted at pass two -- both readers wait the hold
    out and serve the scrubbed log. TWIN: the same two lines re-spelled.
    """
    HOLD, CEILING = 1.0, 0.2
    end_site = ("    await _auto_logs._end_transaction(db)\n"
                "    body = await _auto_logs._hop(\n")
    pass_two = ("        _auto_logs._CPU_POOL, _auto_logs.AUTO_LOG_CPU_WAIT_S,\n"
                "        _scrub_pass_two, body, purged, counts)\n")
    monkeypatch.setattr(auto_logs, "AUTO_LOG_CPU_WAIT_S", CEILING)
    # The probe only asks the database when it has something to hash with;
    # the log names the synthetic account so it has an id to ask about.
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "a-test-secret")
    name = "%s.log.gz" % (RID,)
    (logdir / name).write_bytes(gzip.compress(
        ("a stored log line for %s" % STEAM).encode("utf-8")))
    held = _Held(main._scrub_pass_two)
    monkeypatch.setattr(main, "_scrub_pass_two", held)
    row_key = "SELECT id, bug_number, log_filename, log_bytes, created_at FROM bug_reports"
    when = datetime(2026, 9, 19, tzinfo=timezone.utc)
    detail_row = {"id": RID, "bug_number": 41, "player_id": None,
                  "steam_id": STEAM, "display_name": "Player",
                  "mod_version": "1.41.0", "game_version": "1.0.0",
                  "severity": "medium", "category": "gameplay",
                  "description": "d", "repro_steps": None,
                  "log_filename": name, "log_bytes": 10, "status": "open",
                  "triage_notes": None, "created_at": when,
                  "updated_at": None, "kind": "auto"}

    def mutant(pairs):
        """`_scrub_bug_log` with the edits, bound into main for this drive
        (monkeypatch undoes it at the test's end)."""
        body = textwrap.dedent(inspect.getsource(real_scrub))
        for anchor, replacement in pairs:
            assert body.count(anchor) == 1, (body.count(anchor), anchor)
            body = body.replace(anchor, replacement)
        namespace = dict(vars(main))
        exec(compile(body, "<mutant:_scrub_bug_log>", "exec"), namespace)
        return namespace["_scrub_bug_log"]

    real_scrub = main._scrub_bug_log

    async def one(reader, db, pool, **kw):
        held.reset()
        task = asyncio.ensure_future(reader(report_id=str(RID),
                                            admin_steam_id=STEAM,
                                            hmac_signature="s", db=db, **kw))
        at = time.monotonic()
        entered = await _until(lambda: held.entered == 1, 5.0)
        out_at_pass_two = pool.out
        asyncio.get_running_loop().call_later(HOLD, held.release)
        try:
            got = await task
        except HTTPException as ex:
            got = ex
        took = time.monotonic() - at
        await held.drained()
        await db.close()
        return entered, out_at_pass_two, got, took

    async def drive(scrub):
        monkeypatch.setattr(main, "_scrub_bug_log", scrub)
        pool = _ModelPool(size=2, timeout=0.5)
        ddb = _PooledScripted({row_key: [[{"id": RID, "bug_number": 41,
                                            "log_filename": name,
                                            "log_bytes": 10,
                                            "created_at": when}]]})
        ddb.pool = pool
        down = await one(main.download_bug_report_log, ddb, pool)
        pdb = _PooledScripted({DETAIL_KEY: [[detail_row]], EVENTS_KEY: [[]]})
        pdb.pool = pool
        pane = await one(main.get_bug_report, pdb, pool, include_log=True)
        return down, ddb, pane, pdb, pool.out

    (d_in, d_out, got, d_took), ddb, (p_in, p_out, pane, p_took), pdb, after = \
        _run(drive(real_scrub))
    assert d_in and p_in, "pass two was never reached"
    assert ddb.sql_for("deleted_steam_ids") and pdb.sql_for("deleted_steam_ids"), (
        "the purge probe asked nothing, so the reading below would not be "
        "about the probe's transaction")
    assert (d_out, p_out) == (0, 0), (
        "%d / %d connection(s) checked out while the download / the pane "
        "waited on the scrub's second pass" % (d_out, p_out))
    assert isinstance(got, HTTPException) and got.status_code == 503, got
    assert pane["log_text"] == "[log read error: TimeoutError]", pane["log_text"]
    assert d_took < HOLD and p_took < HOLD, (d_took, p_took)
    assert after == 0, after
    assert ("did not finish within %ss" % CEILING) in capsys.readouterr().out

    (d_in, d_out, got, d_took), ddb, (p_in, p_out, pane, p_took), pdb, after = \
        _run(drive(mutant([(end_site, "    body = await _auto_logs._hop(\n")])))
    assert (d_out, p_out) == (1, 1), (
        "with the probe's transaction left open the readers were expected to "
        "hold its connection across pass two; they held %d / %d, so the "
        "reading above is not about the ending" % (d_out, p_out))

    (d_in, d_out, got, d_took), ddb, (p_in, p_out, pane, p_took), pdb, after = \
        _run(drive(mutant([(pass_two, pass_two.replace(
            "_auto_logs.AUTO_LOG_CPU_WAIT_S", "10 ** 6"))])))
    assert not isinstance(got, HTTPException), got
    assert b"a stored log line" in got.body and d_took >= HOLD - 0.05, (
        got.body, d_took)
    assert pane["log_text"].startswith("a stored log line") and p_took >= HOLD - 0.05, (
        pane["log_text"], p_took)

    (d_in, d_out, got, d_took), ddb, (p_in, p_out, pane, p_took), pdb, after = \
        _run(drive(mutant([
            (end_site, "    await _auto_logs._end_transaction(*(db,))\n"
                       "    body = await _auto_logs._hop(\n"),
            (pass_two, pass_two.replace(
                "_auto_logs.AUTO_LOG_CPU_WAIT_S",
                "float(_auto_logs.AUTO_LOG_CPU_WAIT_S)"))])))
    assert (d_out, p_out) == (0, 0), (d_out, p_out)
    assert isinstance(got, HTTPException) and got.status_code == 503, got
    assert pane["log_text"] == "[log read error: TimeoutError]", pane["log_text"]


def test_the_admin_log_scrub_answers_when_its_first_pass_does_not_finish(
        logdir, admin, monkeypatch, capsys):
    """THE SCRUB'S FIRST PASS HAS THE SAME CEILING AS ITS SECOND, and it too
    is waited for with no connection checked out: both readers end their
    read before the volume hop that comes before it, and the scrub asks the
    database nothing until pass one has returned.

    Pass one is held in its thread past `AUTO_LOG_CPU_WAIT_S`, read on a
    model of the pool: NO connection is checked out by either reader while
    it waits, the download answers 503 and the pane reads a log read error,
    each well inside the hold.

    CONTROL: pass one's ceiling lifted -- both readers wait the hold out and
    serve the log. TWIN: the same ceiling spelled `float(...)`.
    """
    HOLD, CEILING = 1.0, 0.2
    pass_one = ("        _auto_logs._CPU_POOL, _auto_logs.AUTO_LOG_CPU_WAIT_S,\n"
                "        _scrub_pass_one, body)\n")
    monkeypatch.setattr(auto_logs, "AUTO_LOG_CPU_WAIT_S", CEILING)
    name = "%s.log.gz" % (RID,)
    (logdir / name).write_bytes(gzip.compress(b"a stored log line"))
    held = _Held(main._scrub_pass_one)
    monkeypatch.setattr(main, "_scrub_pass_one", held)
    row_key = "SELECT id, bug_number, log_filename, log_bytes, created_at FROM bug_reports"
    when = datetime(2026, 9, 19, tzinfo=timezone.utc)
    detail_row = {"id": RID, "bug_number": 41, "player_id": None,
                  "steam_id": STEAM, "display_name": "Player",
                  "mod_version": "1.41.0", "game_version": "1.0.0",
                  "severity": "medium", "category": "gameplay",
                  "description": "d", "repro_steps": None,
                  "log_filename": name, "log_bytes": 10, "status": "open",
                  "triage_notes": None, "created_at": when,
                  "updated_at": None, "kind": "auto"}
    real_scrub = main._scrub_bug_log

    def mutant(ceiling):
        """`_scrub_bug_log` with pass one's ceiling re-spelled, bound into
        main for this drive (monkeypatch undoes it at the test's end)."""
        body = textwrap.dedent(inspect.getsource(real_scrub))
        assert body.count(pass_one) == 1, body.count(pass_one)
        body = body.replace(pass_one, pass_one.replace(
            "_auto_logs.AUTO_LOG_CPU_WAIT_S", ceiling))
        namespace = dict(vars(main))
        exec(compile(body, "<mutant:_scrub_bug_log>", "exec"), namespace)
        return namespace["_scrub_bug_log"]

    async def one(reader, db, pool, **kw):
        held.reset()
        task = asyncio.ensure_future(reader(report_id=str(RID),
                                            admin_steam_id=STEAM,
                                            hmac_signature="s", db=db, **kw))
        at = time.monotonic()
        entered = await _until(lambda: held.entered == 1, 5.0)
        out_at_pass_one = pool.out
        asyncio.get_running_loop().call_later(HOLD, held.release)
        try:
            got = await task
        except HTTPException as ex:
            got = ex
        took = time.monotonic() - at
        await held.drained()
        await db.close()
        return entered, out_at_pass_one, got, took

    async def drive(scrub):
        monkeypatch.setattr(main, "_scrub_bug_log", scrub)
        pool = _ModelPool(size=2, timeout=0.5)
        ddb = _PooledScripted({row_key: [[{"id": RID, "bug_number": 41,
                                            "log_filename": name,
                                            "log_bytes": 10,
                                            "created_at": when}]]})
        ddb.pool = pool
        down = await one(main.download_bug_report_log, ddb, pool)
        pdb = _PooledScripted({DETAIL_KEY: [[detail_row]], EVENTS_KEY: [[]]})
        pdb.pool = pool
        pane = await one(main.get_bug_report, pdb, pool, include_log=True)
        return down, pane, pool.out

    (d_in, d_out, got, d_took), (p_in, p_out, pane, p_took), after = _run(
        drive(real_scrub))
    assert d_in and p_in, "pass one was never reached"
    assert (d_out, p_out) == (0, 0), (
        "%d / %d connection(s) checked out while the download / the pane "
        "waited on the scrub's first pass" % (d_out, p_out))
    assert isinstance(got, HTTPException) and got.status_code == 503, got
    assert pane["log_text"] == "[log read error: TimeoutError]", pane["log_text"]
    assert d_took < HOLD and p_took < HOLD, (d_took, p_took)
    assert after == 0, after
    assert ("did not finish within %ss" % CEILING) in capsys.readouterr().out

    (d_in, d_out, got, d_took), (p_in, p_out, pane, p_took), after = _run(
        drive(mutant("10 ** 6")))
    assert not isinstance(got, HTTPException), (
        "with pass one's ceiling lifted the download was expected to wait "
        "the hold out and serve the log; it answered %r, so the refusal "
        "above is not about the ceiling" % (got,))
    assert b"a stored log line" in got.body and d_took >= HOLD - 0.05, (
        got.body, d_took)
    assert pane["log_text"].startswith("a stored log line") and p_took >= HOLD - 0.05, (
        pane["log_text"], p_took)

    (d_in, d_out, got, d_took), (p_in, p_out, pane, p_took), after = _run(
        drive(mutant("float(_auto_logs.AUTO_LOG_CPU_WAIT_S)")))
    assert (d_out, p_out) == (0, 0), (d_out, p_out)
    assert isinstance(got, HTTPException) and got.status_code == 503, got
    assert pane["log_text"] == "[log read error: TimeoutError]", pane["log_text"]


def test_an_insert_whose_cleanup_barrier_refuses_still_answers_503(
        logdir, verified, monkeypatch, capsys):
    """R7-L1: THE CLEANUP'S OWN FAILURE CANNOT TURN THE INSERT ARM INTO A 500.

    The INSERT raises, and then the cleanup's directory flush -- the barrier
    between the blob's unlink and the marker's -- refuses. In round 7 that
    raise left the arm ahead of its rollback, its line and its 503, and the
    client was answered 500. Now the transaction is ended FIRST and the
    cleanup's outcome is a sentence: the answer is 503; the rollback had
    already happened when the flush refused (four transactions ended by
    then: T0, T1a, T1 and this arm's); the line says the removal cannot be
    proved and names the marker the sweep will use; and the files are in
    exactly the state that line describes -- the blob unlinked, its marker
    kept, the in-flight name released.

    CONTROL: the round-7 order -- the cleanup awaited bare, before the
    rollback -- and the flush's OSError escapes the handler with the
    rollback not yet taken. TWIN: the same call, parenthesised.

    PART TWO: the cleanup held past its ceiling. The answer is still 503
    within the ceiling, the line says the blob may survive, and once the
    cleanup is let go it finishes in its thread and leaves nothing behind.
    """
    monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
    monkeypatch.setattr(auto_logs, "_BLOB_WRITE_STARTED", [0.0])
    monkeypatch.setattr(auto_logs, "_free_bytes", lambda directory: 10 ** 12)
    real_flush = auto_logs._fsync_dir
    state = {}

    def refusing_flush(directory):
        db = state["db"]
        if db.insert_tried:
            state["rolled_back_at_refusal"] = db.rolled_back
            raise OSError("the directory would not flush")
        return real_flush(directory)

    monkeypatch.setattr(auto_logs, "_fsync_dir", refusing_flush)

    def drive(handler):
        db = state["db"] = _InsertRefused({COUNT_KEY: [[_bucket(0)]],
                                           PLAYER_KEY: [[{"id": PID}]]},
                                          fail_on=INSERT_KEY)
        state["rolled_back_at_refusal"] = None
        before = set(_markers(logdir))
        try:
            out = _run(handler(_request(), db))
        except Exception as ex:          # noqa: BLE001 -- the control's 500
            out = ex
        return out, db, sorted(set(_markers(logdir)) - before)

    out, db, kept = drive(auto_logs.upload_auto_log)
    assert isinstance(out, HTTPException) and out.status_code == 503, (
        "the INSERT arm answered %r when its cleanup barrier refused; the "
        "promised answer is 503" % (out,))
    assert state["rolled_back_at_refusal"] == 4, (
        "the flush refused with %r transaction(s) ended; this arm's rollback "
        "has to come BEFORE its cleanup" % (state["rolled_back_at_refusal"],))
    assert _blobs(logdir) == [], "the blob's unlink came before the barrier"
    assert len(kept) == 1, (
        "the marker is what offers the unproved removal to the sweep, and "
        "exactly this upload's one is kept: %r" % (kept,))
    blob = kept[0][:-len(auto_logs._ORPHAN_MARKER_SUFFIX)]
    assert blob not in auto_logs._MARKERS_IN_FLIGHT
    printed = capsys.readouterr().out
    assert ("RuntimeError; the cleanup raised OSError, so the removal cannot "
            "be proved and the blob may SURVIVE as %s -- %s=%s"
            % (blob, auto_logs._ORPHAN_MARKER, blob)) in printed, printed
    (logdir / kept[0]).unlink()

    out, db, kept = drive(_handler_mutant([(
        _INSERT_ARM_CLEANUP,
        "                gone = await _release_marked_blob_off_loop(own)\n"
        "                await _end_transaction(db)\n"
        "                outcome = 'blob discarded' if gone else 'kept'\n"
        "                # ONE print statement, every outcome.")]))
    assert isinstance(out, OSError), (
        "the round-7 order was expected to let the barrier's OSError escape "
        "as a 500; the handler answered %r, so the red above is not about "
        "the order" % (out,))
    assert state["rolled_back_at_refusal"] == 3, state
    for m in kept:
        (logdir / m).unlink()

    out, db, kept = drive(_handler_mutant([(
        _INSERT_ARM_CLEANUP,
        "                await _end_transaction(db)\n"
        "                outcome = await (_discard_for_refusal)(own)\n"
        "                # ONE print statement, every outcome.")]))
    assert isinstance(out, HTTPException) and out.status_code == 503, out
    assert state["rolled_back_at_refusal"] == 4, state
    for m in kept:
        (logdir / m).unlink()
    capsys.readouterr()

    # PART TWO: the cleanup's wait passes its ceiling.
    monkeypatch.setattr(auto_logs, "_fsync_dir", real_flush)
    monkeypatch.setattr(auto_logs, "AUTO_LOG_VOLUME_WAIT_S", 0.2)
    held = _Held(auto_logs._release_marked_blob)
    monkeypatch.setattr(auto_logs, "_release_marked_blob", held)

    async def ceiling():
        db = _InsertRefused({COUNT_KEY: [[_bucket(0)]],
                             PLAYER_KEY: [[{"id": PID}]]}, fail_on=INSERT_KEY)
        at = time.monotonic()
        try:
            out = await auto_logs.upload_auto_log(_request(), db)
        except HTTPException as ex:
            out = ex
        took = time.monotonic() - at
        drained = await held.drained()
        return out, took, drained

    out, took, drained = _run(ceiling())
    assert isinstance(out, HTTPException) and out.status_code == 503, out
    assert took < 5.0 and drained, (took, drained)
    printed = capsys.readouterr().out
    assert ("the cleanup had not finished after 0.2s and goes on in its "
            "thread, so the blob may SURVIVE as ") in printed, printed
    assert _blobs(logdir) == [] and _markers(logdir) == [], (
        "the cleanup that outlived its wait did not finish its work: %r %r"
        % (_blobs(logdir), _markers(logdir)))


def test_a_cleanup_past_its_ceiling_hands_the_volume_on_only_when_it_ends(
        logdir, verified, monkeypatch, capsys):
    """THE RESERVE LOCK IS RELEASED BY THE CLEANUP'S COMPLETION, NOT BY THE
    END OF SOMEBODY'S WAIT FOR IT (round 8).

    The write fails, so the section cleans up after itself -- and that
    cleanup is held past its ceiling. The upload is answered 503 when the
    ceiling passes, but the volume is NOT handed on then: a ceiling is not
    evidence that the cleanup ran, and handing the lock on at the ceiling
    would let the next upload measure a volume this one may still be
    removing from (R2-M1's class, made by a timer). The lock is released
    when the cleanup itself ends, and then without anybody waiting.

    CONTROL: the release made at the end of the WAIT (`try`/`finally`), and
    the lock is free while the cleanup is still held. TWIN: the chained
    release with its argument parenthesised.
    """
    lock = asyncio.Lock()
    monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", lock)
    monkeypatch.setattr(auto_logs, "_BLOB_WRITE_STARTED", [0.0])
    monkeypatch.setattr(auto_logs, "_free_bytes", lambda directory: 10 ** 12)
    monkeypatch.setattr(auto_logs, "AUTO_LOG_VOLUME_WAIT_S", 0.2)

    def refused_write(own, data):
        raise OSError("the volume refused the write")

    monkeypatch.setattr(auto_logs, "_guarded_write", refused_write)
    held = _Held(auto_logs._release_marked_blob)
    monkeypatch.setattr(auto_logs, "_release_marked_blob", held)
    real_section = auto_logs._reserve_stamp_and_write
    site = ("                gone = await _release_marked_blob_off_loop("
            "own, then=_hand_on)\n")

    async def drive(section):
        held.reset()
        monkeypatch.setattr(auto_logs, "_reserve_stamp_and_write", section)
        try:
            out = await auto_logs.upload_auto_log(_request(), _ok_db())
        except HTTPException as ex:
            out = ex
        locked_at_answer = lock.locked()
        drained = await held.drained()
        freed = await _until(lambda: not lock.locked(), 5.0)
        return out, locked_at_answer, drained, freed

    out, locked_at_answer, drained, freed = _run(drive(real_section))
    assert isinstance(out, HTTPException) and out.status_code == 503, out
    assert locked_at_answer is True, (
        "the volume was handed on while the cleanup of a failed write was "
        "still held")
    assert drained and freed, (
        "the volume was never handed on after the cleanup ended")
    assert _blobs(logdir) == [] and _markers(logdir) == []
    printed = capsys.readouterr().out
    assert "the volume is handed on when it ends" in printed, printed

    out, locked_at_answer, drained, freed = _run(drive(_exec_mutant(
        real_section, site,
        "                try:\n"
        "                    gone = await _release_marked_blob_off_loop(own)\n"
        "                finally:\n"
        "                    _hand_on()\n")))
    assert locked_at_answer is False, (
        "with the release made at the end of the wait the lock was expected "
        "to be free at the answer, so the reading above is not about the "
        "chaining")
    assert drained and freed

    out, locked_at_answer, drained, freed = _run(drive(_exec_mutant(
        real_section, site,
        "                gone = await _release_marked_blob_off_loop("
        "own, then=(_hand_on))\n")))
    assert locked_at_answer is True and drained and freed, (
        locked_at_answer, drained, freed)


def test_a_count_that_reached_the_cap_before_the_insert_refuses_and_discards(
        logdir, verified, monkeypatch, capsys):
    """T2 RE-READS THE COUNT UNDER THE LOCK BEFORE IT INSERTS (#208).

    T1 released the advisory lock when it ended, so T2 takes it again and
    reads the count again: the cap is a property of what the database holds
    at the INSERT. Here the count admitted the upload in T1 and reads full
    in T2 -- which in one process the account's turn makes impossible, and
    across processes is exactly what this arm is for. The answer is the 429
    with its Retry-After, no row is written, and the blob written in between
    is discarded with its marker.

    CONTROL: the re-check disabled, and the same upload is INSERTed past the
    cap. TWIN: the same comparison, negated twice.
    """
    monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
    monkeypatch.setattr(auto_logs, "_BLOB_WRITE_STARTED", [0.0])
    monkeypatch.setattr(auto_logs, "_free_bytes", lambda directory: 10 ** 12)
    site = ("            if count >= AUTO_LOG_PER_STEAM_PER_DAY:\n"
            "                await _end_transaction(db)\n")
    cap = auto_logs.AUTO_LOG_PER_STEAM_PER_DAY

    def drive(handler):
        db = Scripted({COUNT_KEY: [[_bucket(0)], [_bucket(0)], [_bucket(cap)]],
                       PLAYER_KEY: [[{"id": PID}]],
                       INSERT_KEY: [[{"bug_number": 4242}]]})
        try:
            out = _run(handler(_request(), db))
        except HTTPException as ex:
            out = ex
        return out, db

    out, db = drive(auto_logs.upload_auto_log)
    assert isinstance(out, HTTPException) and out.status_code == 429, out
    assert out.headers.get("Retry-After"), out.headers
    assert not db.sql_for(INSERT_KEY), "the upload was INSERTed past the cap"
    assert len(db.sql_for(LOCK_KEY)) == 2, (
        "the lock was taken %d time(s); T1 and T2 each take it"
        % len(db.sql_for(LOCK_KEY)))
    assert _blobs(logdir) == [] and _markers(logdir) == []
    printed = capsys.readouterr().out
    assert "on the re-check before the INSERT" in printed, printed
    assert "and its INSERT; blob discarded" in printed, printed

    out, db = drive(_handler_mutant([(site, "            if False:\n"
                                            "                await _end_transaction(db)\n")]))
    assert isinstance(out, dict) and db.sql_for(INSERT_KEY), (
        "with the re-check disabled the upload was expected to be INSERTed "
        "past the cap: %r" % (out,))
    for p in list(logdir.iterdir()):
        p.unlink()

    out, db = drive(_handler_mutant([(
        site, "            if not count < AUTO_LOG_PER_STEAM_PER_DAY:\n"
              "                await _end_transaction(db)\n")]))
    assert isinstance(out, HTTPException) and out.status_code == 429, out


def test_a_marker_clear_that_does_not_return_in_time_leaves_the_upload_accepted(
        logdir, verified, monkeypatch, capsys):
    """THE CLEAR AFTER THE COMMIT HAS A CEILING, AND PAST IT THE UPLOAD STILL
    STANDS.

    The row is committed when the clear starts, so the connection has gone
    back and the marker is only disposition 2 of the sweep -- a marker over
    a blob a row names, cleared on the next pass that reaches it. A 503 here
    would tell the client to resend a log that has landed; waiting without
    a ceiling would hold the request on a volume that does not answer. So
    the answer is the accepted one, within the ceiling, and the line says
    the marker was not cleared. The clear still happens, in its thread, once
    the volume answers.

    CONTROL: the ceiling lifted at the site, and the upload waits the hold
    out. TWIN: the same ceiling spelled `float(...)`.
    """
    HOLD = 1.0
    monkeypatch.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
    monkeypatch.setattr(auto_logs, "_BLOB_WRITE_STARTED", [0.0])
    monkeypatch.setattr(auto_logs, "_free_bytes", lambda directory: 10 ** 12)
    monkeypatch.setattr(auto_logs, "AUTO_LOG_VOLUME_WAIT_S", 0.2)
    held = _Held(auto_logs._clear_marker)
    monkeypatch.setattr(auto_logs, "_clear_marker", held)
    site = ("                await _hop_through(_VOLUME_POOL, "
            "AUTO_LOG_VOLUME_WAIT_S,\n")

    async def drive(handler):
        held.reset()
        asyncio.get_running_loop().call_later(HOLD, held.release)
        at = time.monotonic()
        out = await handler(_request(), _ok_db())
        took = time.monotonic() - at
        marked_at_answer = list(_markers(logdir))
        await held.drained()
        return out, took, marked_at_answer

    out, took, marked = _run(drive(auto_logs.upload_auto_log))
    assert out["log_persisted"] is True, out
    assert took < HOLD, took
    assert len(marked) == 1, marked
    assert _markers(logdir) == [] and len(_blobs(logdir)) == 1, (
        "the clear that outlived its wait did not finish, or took the blob: "
        "%r %r" % (_markers(logdir), _blobs(logdir)))
    assert "was not cleared (TimeoutError); the upload stands" in (
        capsys.readouterr().out)

    out, took, marked = _run(drive(_handler_mutant([(
        site, "                await _hop_through(_VOLUME_POOL, 10 ** 6,\n")])))
    assert out["log_persisted"] is True and took >= HOLD - 0.05, (out, took)
    assert "was not cleared" not in capsys.readouterr().out

    out, took, marked = _run(drive(_handler_mutant([(
        site, "                await _hop_through(_VOLUME_POOL, "
              "float(AUTO_LOG_VOLUME_WAIT_S),\n")])))
    assert out["log_persisted"] is True and took < HOLD, (out, took)


def test_a_retention_unlink_pass_that_does_not_return_in_time_deletes_no_row(
        logdir, monkeypatch, capsys):
    """RETENTION'S UNLINK PASS HAS A CEILING, AND PAST IT NO ROW IS DELETED.

    This is the one wait on the volume made WITH a connection checked out,
    by design: the row locks that keep two passes off one row live on the
    pass's transaction. No upload reaches it -- the opportunistic pass runs
    in a task of its own, on a session of its own -- and it is bounded by
    `AUTO_LOG_SWEEP_HOP_WAIT_S`. Past the ceiling, no removal the pass made
    can be named, so it deletes NO row: the transaction is rolled back, the
    due rows are held out of the next sweeps, and a later pass re-reads the
    volume.

    CONTROL: the ceiling lifted at the site, and the pass waits the hold out
    and deletes the row. TWIN: the same ceiling spelled `float(...)`.
    """
    HOLD = 1.0
    monkeypatch.setattr(auto_logs, "AUTO_LOG_SWEEP_HOP_WAIT_S", 0.2)
    held = _Held(auto_logs._unlink_due_blobs)
    monkeypatch.setattr(auto_logs, "_unlink_due_blobs", held)
    site = ("            _VOLUME_POOL, AUTO_LOG_SWEEP_HOP_WAIT_S, "
            "_unlink_due_blobs, base,\n")

    async def drive(prune):
        held.reset()
        auto_logs._PRUNE_HELD.clear()
        (logdir / "due.log.gz").write_bytes(b"x")
        asyncio.get_running_loop().call_later(HOLD, held.release)
        db = Scripted({DUE_KEY: [[{"id": str(R1), "log_filename": "due.log.gz"}]],
                       "DELETE FROM bug_reports": [[{"id": str(R1)}]]})
        at = time.monotonic()
        out = await prune(db)
        took = time.monotonic() - at
        await held.drained()
        return out, took, db

    out, took, db = _run(drive(auto_logs.prune_auto_logs))
    assert out == {"rows": 0, "blobs": 0, "retained": 1, "undurable": 0,
                   "due": 1, "held": 1}, out
    assert took < HOLD, took
    assert not db.sql_for("DELETE FROM bug_reports"), (
        "a row was deleted over an unlink pass that did not return")
    assert db.events[-1] == "ROLLBACK" and db.committed == 0, db.events
    assert str(R1) in auto_logs._PRUNE_HELD
    assert ("did not return within %ss" % 0.2) in capsys.readouterr().out

    out, took, db = _run(drive(_exec_mutant(
        auto_logs.prune_auto_logs, site,
        "            _VOLUME_POOL, 10 ** 6, _unlink_due_blobs, base,\n")))
    assert out["rows"] == 1 and took >= HOLD - 0.05, (out, took)

    out, took, db = _run(drive(_exec_mutant(
        auto_logs.prune_auto_logs, site,
        "            _VOLUME_POOL, float(AUTO_LOG_SWEEP_HOP_WAIT_S), "
        "_unlink_due_blobs, base,\n")))
    assert out["rows"] == 0 and out["retained"] == 1 and took < HOLD, (
        out, took)


@pytest.mark.parametrize("hop", ["walk", "resolve"])
def test_an_orphan_sweep_hop_that_does_not_return_in_time_removes_nothing(
        logdir, monkeypatch, capsys, hop):
    """THE ORPHAN SWEEP'S TWO HOPS HAVE A CEILING, AND NEITHER IS WAITED FOR
    WITH A CONNECTION CHECKED OUT.

    The walk of the directory comes before the pass's first statement, and
    the resolution of its candidates after the pass has ended its
    transaction. Past the ceiling the pass reports that it removed nothing
    it can name -- the walk's position is not advanced, and a resolution
    still running finishes in its thread -- and the next tick reads the
    volume again.

    CONTROL: the ceiling lifted at the site, and the pass waits the hold out
    and removes the orphan. TWIN: the same ceiling spelled `float(...)`.
    """
    HOLD = 1.0
    target = {"walk": "_marker_candidates",
              "resolve": "_resolve_marker_candidates"}[hop]
    site = {"walk": "        walked = await _hop(_VOLUME_POOL, "
                    "AUTO_LOG_SWEEP_HOP_WAIT_S,\n",
            "resolve": "        resolved = await _hop(_VOLUME_POOL, "
                       "AUTO_LOG_SWEEP_HOP_WAIT_S,\n"}[hop]
    line = {"walk": "the directory walk did not return within %ss",
            "resolve": "unreferenced, did not return within %ss"}[hop]
    monkeypatch.setattr(auto_logs, "AUTO_LOG_SWEEP_HOP_WAIT_S", 0.2)
    held = _Held(getattr(auto_logs, target))
    monkeypatch.setattr(auto_logs, target, held)
    name = "88888888-0000-4000-8000-0000000000b1.log.gz"

    async def drive(sweep):
        held.reset()
        auto_logs._ORPHAN_CURSOR[0] = ""
        (logdir / name).write_bytes(b"x")
        _mark(logdir, name, age_s=90_000)
        asyncio.get_running_loop().call_later(HOLD, held.release)
        db = Scripted({"COUNT(*) AS n FROM bug_reports": [[{"n": 7}]],
                       "SELECT log_filename FROM bug_reports": [[]]})
        at = time.monotonic()
        out = await sweep(db, min_age_s=3600)
        took = time.monotonic() - at
        cursor = auto_logs._ORPHAN_CURSOR[0]
        await held.drained()
        return out, took, db, cursor

    out, took, db, cursor = _run(drive(auto_logs.prune_orphan_blobs))
    assert out["unlinked"] == 0 and took < HOLD, (out, took)
    assert line % 0.2 in capsys.readouterr().out
    if hop == "walk":
        assert db.log == [], (
            "the sweep issued a statement before its walk: %r" % (db.log,))
        assert cursor == "" and out["examined"] == 0, (cursor, out)
        assert (logdir / name).exists(), "a walk that timed out removed a file"
    else:
        assert db.events[-1] == "ROLLBACK", (
            "the resolution was waited for with the transaction open: %r"
            % (db.events,))

    out, took, db, cursor = _run(drive(_exec_mutant(
        auto_logs.prune_orphan_blobs, site,
        site.replace("AUTO_LOG_SWEEP_HOP_WAIT_S", "10 ** 6"))))
    assert out["unlinked"] == 1 and took >= HOLD - 0.05, (out, took)

    out, took, db, cursor = _run(drive(_exec_mutant(
        auto_logs.prune_orphan_blobs, site,
        site.replace("AUTO_LOG_SWEEP_HOP_WAIT_S",
                     "float(AUTO_LOG_SWEEP_HOP_WAIT_S)"))))
    assert out["unlinked"] == 0 and took < HOLD, (out, took)
