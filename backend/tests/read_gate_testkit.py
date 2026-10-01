"""Shared fixtures for the verified-reads tests (read_gate.py).

`StubDB` stands in for `database.async_session`, the ONE seam the gate's own
lookups use (sessions, operator keys, the stage row). It answers from three
dicts, can be told to raise per table, and counts what it was asked, so a
test can assert that an outcome came from a lookup -- or that none ran.

`Clock` drives both of the gate's clocks (read_gate._mono, read_gate._wall).

`scratch_route` adds a GET route to the REAL app for one test and removes it
afterwards, so the real middleware (version gate, cache-control) and the real
route class apply to a handler that needs no database. Its class is decided
by its template, exactly as for any route.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import database                 # noqa: E402
import read_gate                # noqa: E402

LIVE_VERSION = "1.40.3"
INTERNAL_KEY = "test-internal-key-for-read-gate"


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Clock:
    def __init__(self):
        self.mono = 1000.0
        self.wall = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)

    def advance(self, seconds: float) -> None:
        self.mono += seconds
        self.wall += timedelta(seconds=seconds)


class _Result:
    def __init__(self, row=None, scalar=None):
        self._row, self._scalar = row, scalar

    def mappings(self):
        return self

    def first(self):
        return self._row

    def scalar(self):
        return self._scalar


class StubDB:
    """Callable like database.async_session; each call is one session."""

    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.operators: dict[str, dict] = {}
        self.mode_row = None            # None = no row
        self.fail: set[str] = set()     # "session" | "operator" | "mode"
        self.calls = Counter()

    # -- fixtures --
    def add_session(self, token, *, expires_at, verified=True):
        self.sessions[sha(token)] = {"verified": verified, "expires_at": expires_at}

    def add_operator(self, key, *, row_id, name, slot):
        self.operators[sha(key)] = {"id": row_id, "operator_name": name, "slot": slot}

    def revoke(self, key):
        self.operators.pop(sha(key), None)

    # -- the seam --
    def __call__(self):
        return _StubSession(self)


class _StubSession:
    def __init__(self, db: StubDB):
        self.db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        params = params or {}
        if "steam_sessions" in sql:
            self.db.calls["session"] += 1
            if "session" in self.db.fail:
                raise OSError("session lookup unavailable")
            return _Result(row=self.db.sessions.get(params.get("th")))
        if "api_operator_keys" in sql:
            self.db.calls["operator"] += 1
            if "operator" in self.db.fail:
                raise OSError("operator lookup unavailable")
            return _Result(row=self.db.operators.get(params.get("kh")))
        if "runtime_settings" in sql:
            self.db.calls["mode"] += 1
            if "mode" in self.db.fail:
                raise OSError("settings read unavailable")
            return _Result(scalar=self.db.mode_row)
        raise AssertionError("unexpected statement on the gate's seam: " + sql[:80])


def reset_gate():
    read_gate._mode_cache.update({"value": read_gate.UNKNOWN, "loaded": False,
                                  "at": 0.0, "gen": 0})
    read_gate.credential_cache_clear()
    read_gate.census_reset()


@contextlib.contextmanager
def gate_env(monkeypatch, *, mode="log", replica=False):
    """Stub seam + controlled clocks + a fresh gate; `mode` is the stored row
    (None = no row). Yields (stub, clock)."""
    stub = StubDB()
    stub.mode_row = mode
    clock = Clock()
    monkeypatch.setattr(database, "async_session", stub)
    monkeypatch.setattr(read_gate, "_mono", lambda: clock.mono)
    monkeypatch.setattr(read_gate, "_wall", lambda: clock.wall)
    monkeypatch.setattr(read_gate, "REPLICA_NODE", replica)
    monkeypatch.setenv("API_SECRET_KEY", INTERNAL_KEY)
    reset_gate()
    try:
        yield stub, clock
    finally:
        reset_gate()


def census_rows(**match):
    out = []
    for (route, method, cls, key_id, vp, refused), n in read_gate._census.items():
        row = {"route": route, "method": method, "class": cls, "key_id": key_id,
               "version_header": vp, "refused": refused, "count": n}
        if all(row[k] == v for k, v in match.items()):
            out.append(row)
    return out


@contextlib.contextmanager
def scratch_route(app, path, handler=None):
    """Add GET `path` to the real app (through its route class) for the
    duration; removed afterwards so no other test sees it."""
    calls = []

    async def _default():
        calls.append(1)
        return {"ok": True}

    before = list(app.router.routes)
    app.add_api_route(path, handler or _default, methods=["GET"])
    added = [r for r in app.router.routes if r not in before]
    try:
        yield calls
    finally:
        for r in added:
            app.router.routes.remove(r)


ADMIN_ID = "76561190000004242"      # synthetic
ADMIN_SECRET = "test-admin-hmac-secret-for-read-gate"


def admin_sign(action: str, target: str = "", admin=ADMIN_ID, secret=ADMIN_SECRET) -> str:
    import hmac as _hmac
    canonical = f"admin:{admin}:{action}:{target or ''}"
    return _hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar(self):
        return self.value

    def first(self):
        return self.value


class RequestDB:
    """A request session (get_db) for the mode route: answers the admin
    lookup from `admins`, applies the runtime_settings upsert to the StubDB's
    stage row, and records every statement. `nested()` is a savepoint that
    does nothing."""

    def __init__(self, stub: StubDB, admins=(ADMIN_ID,)):
        self.stub, self.admins, self.ran, self.commits = stub, set(admins), [], 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.ran.append(sql)
        if "admin_users" in sql:
            compiled = getattr(stmt, "compile", None)
            sid = None
            if compiled is not None:
                try:
                    sid = list(stmt.compile().params.values())[0]
                except Exception:
                    sid = None
            return _Scalar(object() if sid in self.admins else None)
        if "INSERT INTO runtime_settings" in sql:
            self.stub.mode_row = (params or {}).get("v")
            return _Scalar(None)
        return _Scalar(None)

    def begin_nested(self):
        db = self

        class _N:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *exc):
                return False
        return _N()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass

    async def close(self):
        pass


def headers(*, version=LIVE_VERSION, session=None, operator=None, internal=None, **extra):
    h = {}
    if version:
        h["X-Mod-Version"] = version
    if session:
        h["X-Session-Token"] = session
    if operator:
        h["X-Operator-Key"] = operator
    if internal:
        h["X-Internal-Key"] = internal
    h.update(extra)
    return h
