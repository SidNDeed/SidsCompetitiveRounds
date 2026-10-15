"""Verified reads, requirement 21: the /health words `read_gate` (off, log,
enforce, unknown) and `read_gate_build` (vr1).

Both are REQUIRED fields of HealthResponse and both constructors of
health_check supply them: the connected arm reads the stage through its own
session (inside a savepoint), the degraded arm answers the cached stage with
no I/O, and `unknown` before any read succeeded. /health stays OPEN and in
the version bypass: a sessionless, versionless probe answers 200 in every
stage, `unknown` included, so the release train's probe keeps working.
"""
from __future__ import annotations

import ast
import os
import pathlib
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))
sys.path.insert(0, HERE)

from test_player_cards_server import _run                        # noqa: E402
import main                                                      # noqa: E402
import read_gate                                                 # noqa: E402
import read_gate_testkit as K                                    # noqa: E402
import schemas                                                   # noqa: E402

MAIN_PY = pathlib.Path(main.__file__).resolve()
WORDS = ("read_gate", "read_gate_build")


class _Res:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _Up:
    """A session that is up: the stage row answers `mode`; every other
    statement answers None, as the other health probes' fakes do."""

    def __init__(self, mode):
        self.mode = mode

    async def execute(self, stmt, *a, **k):
        if "runtime_settings" in str(stmt) and "read_gate_mode" in str(stmt):
            return _Res(self.mode)
        return None

    def begin_nested(self):
        class _N:
            async def __aenter__(s):
                return s

            async def __aexit__(s, *exc):
                return False
        return _N()


class _Down:
    async def execute(self, *a, **k):
        raise OSError("database unreachable")

    def begin_nested(self):
        raise OSError("database unreachable")


def _health(mode):
    up = _run(main.health_check(db=_Up(mode))).model_dump()
    down = _run(main.health_check(db=_Down())).model_dump()
    assert (up["status"], down["status"]) == ("ok", "degraded"), (up["status"], down["status"])
    return up, down


@pytest.fixture
def fresh(monkeypatch):
    K.reset_gate()
    yield
    K.reset_gate()


def test_health_words_both_constructors(fresh):
    for word in WORDS:
        assert schemas.HealthResponse.model_fields[word].is_required(), word
    # degraded before any read: unknown, never a guessed stage
    down0 = _run(main.health_check(db=_Down())).model_dump()
    assert down0["status"] == "degraded" and down0["read_gate"] == "unknown"
    assert down0["read_gate_build"] == "vr1"
    for stage in ("log", "enforce", "off"):
        K.reset_gate()
        up, down = _health(stage)
        assert up["read_gate"] == stage and up["read_gate_build"] == "vr1", up
        # the degraded arm answers the stage this process last read
        assert down["read_gate"] == stage and down["read_gate_build"] == "vr1", down
    K.reset_gate()
    up, _ = _health(None)               # no row: off
    assert up["read_gate"] == "off"


def test_health_words_passed_once_per_arm():
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    health = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    assert len(health) == 1
    tries = [n for n in ast.walk(health[0]) if isinstance(n, ast.Try)]
    assert len(tries) == 1
    ok_arm = {id(n) for s in tries[0].body for n in ast.walk(s)}
    degraded = {id(n) for h in tries[0].handlers for n in ast.walk(h)}
    for word in WORDS:
        kws = [k for k in ast.walk(health[0]) if isinstance(k, ast.keyword) and k.arg == word]
        assert len(kws) == 2, (word, len(kws))
        assert sum(id(k) in ok_arm for k in kws) == 1 and sum(id(k) in degraded for k in kws) == 1
    assert read_gate.READ_GATE_BUILD == "vr1"


@pytest.mark.parametrize("stage", ["off", "log", "enforce", "unknown"])
def test_health_sessionless_200(monkeypatch, stage):
    from fastapi.testclient import TestClient
    with K.gate_env(monkeypatch, mode=None if stage == "unknown" else stage) as (stub, clock):
        if stage == "unknown":
            stub.fail.add("mode")

        async def _db():
            yield _Down() if stage == "unknown" else _Up(stage)
        monkeypatch.setitem(main.app.dependency_overrides, main.get_db, _db)
        client = TestClient(main.app, raise_server_exceptions=False)
        r = client.get("/api/v1/health")            # no version, no session
        assert r.status_code == 200, r.text
        assert r.json()["read_gate"] == stage
        assert r.json()["read_gate_build"] == "vr1"
