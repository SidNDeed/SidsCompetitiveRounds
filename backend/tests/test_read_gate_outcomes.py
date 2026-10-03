"""Verified reads: what the read gate answers, per credential and per stage.

Every case runs through the REAL app (main.app): the version gate, the
cache-control middleware and the route class all apply. The handler is a
scratch GET route added for the test whose class follows from its template
(PUBLIC by default; a test that needs PLAYER or BOT_ONLY adds the scratch
template to that list). The gate's lookups go to read_gate_testkit.StubDB,
the one seam the gate reads through, so each outcome can be pinned to the
lookup that produced it -- or to the absence of any lookup.
"""
from __future__ import annotations

import subprocess
from collections import Counter
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import read_gate_testkit as K
import main
import read_gate

PUBLIC_PATH = "/api/v1/zz-verified-reads/public"
PLAYER_PATH = "/api/v1/zz-verified-reads/player"
BOT_PATH = "/api/v1/zz-verified-reads/bot"
OP_A = "scrop1_" + "A" * 43
OP_B = "scrop1_" + "B" * 43
OP_UNISSUED = "scrop1_" + "Z" * 43
GOOD = "session-token-good-0123456789abcdefghijklmn"
EXPIRED = "session-token-expired-0123456789abcdefghij"
UNKNOWN_TOKEN = "session-token-unknown-0123456789abcdefghij"


@pytest.fixture
def env(monkeypatch):
    with K.gate_env(monkeypatch, mode="log") as (stub, clock):
        monkeypatch.setattr(main, "_RL_BUCKETS", main._RL_BUCKETS.__class__(main._RL_BUCKETS.default_factory))
        stub.add_session(GOOD, expires_at=clock.wall + timedelta(hours=12))
        stub.add_session(EXPIRED, expires_at=clock.wall - timedelta(minutes=1))
        stub.add_operator(OP_A, row_id=7, name="scrmod", slot=1)
        stub.add_operator(OP_B, row_id=8, name="scrmod", slot=2)
        monkeypatch.setattr(read_gate, "PLAYER", read_gate.PLAYER | {PLAYER_PATH})
        monkeypatch.setattr(read_gate, "BOT_ONLY", read_gate.BOT_ONLY | {BOT_PATH})
        with K.scratch_route(main.app, PUBLIC_PATH) as pub, \
                K.scratch_route(main.app, PLAYER_PATH) as ply, \
                K.scratch_route(main.app, BOT_PATH) as bot:
            client = TestClient(main.app, raise_server_exceptions=False)

            class E:
                pass
            e = E()
            e.stub, e.clock, e.client = stub, clock, client
            e.calls = {"public": pub, "player": ply, "bot": bot}

            def set_mode(mode):
                stub.mode_row = mode
                read_gate.mode_cache_set(mode) if mode in read_gate.MODES else K.reset_gate()
            e.set_mode = set_mode
            yield e


def _get(e, path, **kw):
    return e.client.get(path, headers=K.headers(**kw))


# -- M1: any valid credential wins --------------------------------------------

@pytest.mark.parametrize("mode", ["log", "enforce"])
def test_expired_session_plus_live_operator_key_passes_public(env, mode):
    env.set_mode(mode)
    r = _get(env, PUBLIC_PATH, session=EXPIRED, operator=OP_A)
    assert r.status_code == 200, r.text
    assert K.census_rows(route=PUBLIC_PATH, **{"class": "operator:scrmod"}, key_id="7/1",
                         refused=False)
    assert env.stub.calls["session"] == 1 and env.stub.calls["operator"] == 1


@pytest.mark.parametrize("mode", ["log", "enforce"])
def test_bad_operator_key_plus_valid_session_passes(env, mode):
    env.set_mode(mode)
    r = _get(env, PUBLIC_PATH, session=GOOD, operator=OP_UNISSUED)
    assert r.status_code == 200, r.text
    assert K.census_rows(route=PUBLIC_PATH, **{"class": "session"}, refused=False)


@pytest.mark.parametrize("mode", ["log", "enforce"])
def test_live_operator_key_plus_expired_session_refused_on_player_route(env, mode):
    env.set_mode(mode)
    r = _get(env, PLAYER_PATH, session=EXPIRED, operator=OP_A)
    if mode == "enforce":
        assert r.status_code == 401 and r.json()["detail"] == "session_required"
        assert env.calls["player"] == []
    else:
        assert r.status_code == 200
    # the operator is named in the census either way, and never as verified
    assert K.census_rows(route=PLAYER_PATH, **{"class": "operator:scrmod"},
                         refused=(mode == "enforce"))


@pytest.mark.parametrize("mode", ["log", "enforce"])
def test_live_operator_key_alone_refused_on_player_route(env, mode):
    """Decision point 4: an operator key does not open a PLAYER route."""
    env.set_mode(mode)
    r = _get(env, PLAYER_PATH, operator=OP_A)
    if mode == "enforce":
        assert r.status_code == 401 and r.json()["detail"] == "player_session_required"
    else:
        assert r.status_code == 200


def test_refusal_details_and_classes_in_enforce(env):
    env.set_mode("enforce")
    cases = [
        ({}, 401, "read_credential_required", "mod_no_session"),
        ({"session": UNKNOWN_TOKEN}, 401, "session_required", "bad_session"),
        ({"session": EXPIRED}, 401, "session_required", "bad_session"),
        ({"operator": OP_UNISSUED}, 401, "operator_key_invalid", "bad_operator_key"),
        ({"session": GOOD}, 200, None, "session"),
        ({"operator": OP_A}, 200, None, "operator:scrmod"),
        ({"internal": K.INTERNAL_KEY}, 200, None, "internal"),
    ]
    for kw, status, detail, cls in cases:
        read_gate.census_reset()
        r = _get(env, PUBLIC_PATH, **kw)
        assert r.status_code == status, (kw, r.text)
        if detail:
            assert r.json()["detail"] == detail
        assert K.census_rows(route=PUBLIC_PATH, **{"class": cls}), (kw, read_gate._census)


def test_no_version_no_credential_is_426_before_the_gate(env):
    env.set_mode("enforce")
    r = _get(env, PUBLIC_PATH, version=None)
    assert r.status_code == 426
    assert read_gate._census == {}


def test_gated_route_with_invalid_path_parameter_refuses_before_validation(env):
    """FastAPI 0.115 solves the route's dependencies before it validates the
    path: the gate's 401 comes first in enforce, the 422 in log."""
    async def _typed(n: int):
        return {"n": n}
    with K.scratch_route(main.app, "/api/v1/zz-verified-reads/typed/{n}", _typed):
        env.set_mode("enforce")
        assert _get(env, "/api/v1/zz-verified-reads/typed/notanint").status_code == 401
        env.set_mode("log")
        assert _get(env, "/api/v1/zz-verified-reads/typed/notanint").status_code == 422


# -- H3: a lookup failure does not admit --------------------------------------

def test_lookup_error_enforce_503_handler_not_called(env):
    env.set_mode("enforce")
    env.stub.fail.add("session")
    r = _get(env, PUBLIC_PATH, session=GOOD)
    assert r.status_code == 503 and r.json()["detail"] == "read_gate_unavailable"
    assert r.headers.get("Retry-After")
    assert env.calls["public"] == []
    assert K.census_rows(route=PUBLIC_PATH, **{"class": "lookup_error"}, refused=True)


def test_lookup_error_log_passes(env):
    env.set_mode("log")
    env.stub.fail.add("session")
    r = _get(env, PUBLIC_PATH, session=GOOD)
    assert r.status_code == 200
    assert env.calls["public"] == [1]
    assert K.census_rows(route=PUBLIC_PATH, **{"class": "lookup_error"}, refused=False)


def test_off_performs_no_lookup(env):
    env.set_mode("off")
    env.stub.fail.update({"session", "operator"})
    r = _get(env, PUBLIC_PATH, session=GOOD, operator=OP_A)
    assert r.status_code == 200
    assert env.stub.calls["session"] == 0 and env.stub.calls["operator"] == 0
    assert read_gate._census == {}


def test_a_valid_credential_wins_over_a_failed_lookup(env):
    """M1 with H3: the session lookup raises, the operator key is live."""
    env.set_mode("enforce")
    env.stub.fail.add("session")
    r = _get(env, PUBLIC_PATH, session=GOOD, operator=OP_A)
    assert r.status_code == 200


# -- H2: a session the standby has not received yet ---------------------------

def test_standby_miss_503_pending(env, monkeypatch):
    monkeypatch.setattr(read_gate, "REPLICA_NODE", True)
    env.set_mode("enforce")
    r = _get(env, PUBLIC_PATH, session=UNKNOWN_TOKEN)
    assert r.status_code == 503 and r.json()["detail"] == "session_replication_pending"
    assert r.headers.get("Retry-After") == "2"
    assert env.calls["public"] == []
    assert K.census_rows(route=PUBLIC_PATH, **{"class": "replication_pending"}, refused=True)
    env.set_mode("log")
    assert _get(env, PUBLIC_PATH, session=UNKNOWN_TOKEN).status_code == 200
    assert K.census_rows(route=PUBLIC_PATH, **{"class": "replication_pending"}, refused=False)


def test_primary_miss_401(env, monkeypatch):
    monkeypatch.setattr(read_gate, "REPLICA_NODE", False)
    env.set_mode("enforce")
    r = _get(env, PUBLIC_PATH, session=UNKNOWN_TOKEN)
    assert r.status_code == 401 and r.json()["detail"] == "session_required"


def test_standby_expired_row_401(env, monkeypatch):
    monkeypatch.setattr(read_gate, "REPLICA_NODE", True)
    env.set_mode("enforce")
    r = _get(env, PUBLIC_PATH, session=EXPIRED)
    assert r.status_code == 401 and r.json()["detail"] == "session_required"
    env.stub.add_session("unverified-row-token-0123456789abcdefghi",
                         expires_at=env.clock.wall + timedelta(hours=1), verified=False)
    r = _get(env, PUBLIC_PATH, session="unverified-row-token-0123456789abcdefghi")
    assert r.status_code == 401 and r.json()["detail"] == "session_required"


BASE = "0e75199339b72dd132a2114fee90fa6116c5d2e1"


def _auth_steam_span(source: str):
    import ast
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef):
            for dec in node.decorator_list:
                if (isinstance(dec, ast.Call) and dec.args and isinstance(dec.args[0], ast.Constant)
                        and dec.args[0].value == "/api/v1/auth/steam"):
                    return min(d.lineno for d in node.decorator_list), node.end_lineno
    raise AssertionError("the /auth/steam handler was not found")


def test_auth_steam_untouched():
    """The session mint is not modified in any way: no line of main.py's diff
    from the lane base falls inside the /auth/steam handler's span there."""
    repo = Path(main.__file__).resolve().parents[2]
    base_src = subprocess.run(["git", "-C", str(repo), "show", f"{BASE}:backend/api/main.py"],
                              capture_output=True, text=True, encoding="utf-8", check=True).stdout
    lo, hi = _auth_steam_span(base_src)
    diff = subprocess.run(["git", "-C", str(repo), "diff", "-U0", BASE, "--", "backend/api/main.py"],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout
    import re
    touched = []
    for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+", diff, re.M):
        start, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        old = range(start, start + max(n, 1))
        if any(lo <= x <= hi for x in old) or (n == 0 and lo < start < hi):
            touched.append(m.group(0))
    assert not touched, touched
    assert diff, "the diff is empty: this test would pass on any tree"


# -- M2 / requirement 25: what the cache may keep -----------------------------

def test_session_cache_ends_at_expiry(env):
    env.set_mode("enforce")
    near = "session-token-near-expiry-0123456789abcdefg"
    env.stub.add_session(near, expires_at=env.clock.wall + timedelta(seconds=1))
    assert _get(env, PUBLIC_PATH, session=near).status_code == 200      # 1 s before expiry
    assert env.stub.calls["session"] == 1
    env.clock.advance(2)                                                  # 1 s after
    r = _get(env, PUBLIC_PATH, session=near)
    assert r.status_code == 401 and r.json()["detail"] == "session_required"
    assert env.stub.calls["session"] == 2
    # a session far from expiry is cached for the full 60 s, not re-read
    assert _get(env, PUBLIC_PATH, session=GOOD).status_code == 200
    env.clock.advance(30)
    assert _get(env, PUBLIC_PATH, session=GOOD).status_code == 200
    assert env.stub.calls["session"] == 3


def test_negative_verdicts_are_not_cached(env):
    env.set_mode("enforce")
    fresh = "session-token-minted-later-0123456789abcde"
    assert _get(env, PUBLIC_PATH, session=fresh).status_code == 401
    env.stub.add_session(fresh, expires_at=env.clock.wall + timedelta(hours=1))
    assert _get(env, PUBLIC_PATH, session=fresh).status_code == 200


def test_revocation_bound_60s(env):
    env.set_mode("enforce")
    assert _get(env, PUBLIC_PATH, operator=OP_A).status_code == 200
    assert _get(env, PUBLIC_PATH, session=GOOD).status_code == 200
    env.stub.revoke(OP_A)
    env.stub.sessions.clear()
    env.clock.advance(59)
    assert _get(env, PUBLIC_PATH, operator=OP_A).status_code == 200    # inside the bound
    assert _get(env, PUBLIC_PATH, session=GOOD).status_code == 200
    env.clock.advance(2)                                                 # 61 s after
    assert _get(env, PUBLIC_PATH, operator=OP_A).status_code == 401
    assert _get(env, PUBLIC_PATH, session=GOOD).status_code == 401


def test_rotation_counts_keys_separately(env):
    env.set_mode("enforce")
    assert _get(env, PUBLIC_PATH, operator=OP_A).status_code == 200
    assert _get(env, PUBLIC_PATH, operator=OP_B).status_code == 200
    rows = K.census_rows(route=PUBLIC_PATH, **{"class": "operator:scrmod"}, refused=False)
    assert sorted(r["key_id"] for r in rows) == ["7/1", "8/2"]
    env.stub.revoke(OP_A)
    env.clock.advance(61)
    a = _get(env, PUBLIC_PATH, operator=OP_A)
    b = _get(env, PUBLIC_PATH, operator=OP_B)
    assert a.status_code == 401 and a.json()["detail"] == "operator_key_invalid"
    assert b.status_code == 200
    assert K.census_rows(route=PUBLIC_PATH, **{"class": "bad_operator_key"}, refused=True)
    assert [r["count"] for r in K.census_rows(route=PUBLIC_PATH, key_id="8/2")] == [2]


# -- M4: the bot's poll reads follow the stage --------------------------------

def test_bot_only_follows_mode(env):
    seen = []
    for mode in ("off", "log", "enforce", "log"):
        env.set_mode(mode)
        read_gate.census_reset()
        plain = _get(env, BOT_PATH)
        op = _get(env, BOT_PATH, operator=OP_A)
        bot = _get(env, BOT_PATH, internal=K.INTERNAL_KEY)
        seen.append((mode, plain.status_code, op.status_code, bot.status_code))
        if mode == "enforce":
            assert plain.json()["detail"] == "internal_key_required"
        if mode == "log":
            assert K.census_rows(route=BOT_PATH, **{"class": "operator:scrmod"}, refused=False)
            assert K.census_rows(route=BOT_PATH, **{"class": "mod_no_session"}, refused=False)
        if mode == "off":
            assert read_gate._census == {}
    assert seen == [("off", 200, 200, 200), ("log", 200, 200, 200),
                    ("enforce", 403, 403, 200), ("log", 200, 200, 200)]


def test_the_three_bot_poll_reads_are_bot_only():
    for t in ("/api/v1/bug-reports/recent", "/api/v1/bug-reports/events/recent",
              "/api/v1/players/by-discord/{discord_id}"):
        assert read_gate.route_class(t) == read_gate.C_BOT_ONLY


# -- M12 / requirement 13: the operator version exemption ---------------------

@pytest.mark.parametrize("mode", ["off", "log", "enforce"])
def test_unissued_operator_key_without_version_426(env, mode):
    env.set_mode(mode)
    r = _get(env, PUBLIC_PATH, version=None, operator=OP_UNISSUED)
    assert r.status_code == 426
    assert r.json() == {"error": "outdated", "required": main.MIN_MOD_VERSION_EFFECTIVE,
                        "current": None}
    assert env.calls["public"] == []
    # a key with no prefix is refused without a lookup; a prefixed one is looked up
    assert env.stub.calls["operator"] == 1


@pytest.mark.parametrize("mode", ["log", "enforce"])
def test_live_operator_key_without_version_reaches_public(env, mode):
    env.set_mode(mode)
    r = _get(env, PUBLIC_PATH, version=None, operator=OP_A)
    assert r.status_code == 200, r.text
    assert env.calls["public"] == [1]
    # one lookup: the gate reused the version gate's verdict
    assert env.stub.calls["operator"] == 1
    assert K.census_rows(route=PUBLIC_PATH, **{"class": "operator:scrmod"}, version_header=False)


@pytest.mark.parametrize("mode", ["off", "log", "enforce"])
def test_live_operator_key_without_version_426_on_write_on_get(env, mode):
    env.set_mode(mode)
    assert read_gate.route_class("/api/v1/team/series/{series_id}/state") == read_gate.C_WRITE_ON_GET
    r = env.client.get("/api/v1/team/series/00000000-0000-0000-0000-000000000000/state",
                       headers={"X-Operator-Key": OP_A})
    assert r.status_code == 426
    assert env.stub.calls["operator"] == 0


def test_live_operator_key_without_version_426_on_player_and_bot_only(env):
    env.set_mode("log")
    assert _get(env, PLAYER_PATH, version=None, operator=OP_A).status_code == 426
    assert _get(env, BOT_PATH, version=None, operator=OP_A).status_code == 426
    assert env.calls["player"] == [] and env.calls["bot"] == []


def test_non_get_with_operator_key_426(env):
    env.set_mode("log")
    r = env.client.post("/api/v1/ffa/queue/leave?steam_id=0", headers={"X-Operator-Key": OP_A})
    assert r.status_code == 426
    assert env.stub.calls["operator"] == 0


# -- H4 / requirement 14: the stage as this process knows it ------------------

def test_first_load_failure_unknown_503(env):
    K.reset_gate()
    env.stub.fail.add("mode")
    r = _get(env, PUBLIC_PATH, session=GOOD)
    assert r.status_code == 503 and r.json()["detail"] == "read_gate_unavailable"
    assert env.calls["public"] == []
    assert read_gate.mode_word() == read_gate.UNKNOWN
    # OPEN and the classes whose behaviour does not depend on the stage still answer
    mv = _get(env, "/api/v1/mod-version", version=K.ADVERT_VERSION)
    assert mv.status_code == 200 and mv.json()["read_gate"] == "unknown"
    # within the TTL the failed read is not repeated per request
    calls = env.stub.calls["mode"]
    _get(env, PUBLIC_PATH)
    assert env.stub.calls["mode"] == calls
    # the read succeeds after the TTL: the process acts on the stored stage
    env.stub.fail.discard("mode")
    env.clock.advance(read_gate.MODE_TTL + 1)
    assert _get(env, PUBLIC_PATH).status_code == 200            # stored stage is log


def test_absent_row_is_off(env):
    K.reset_gate()
    env.stub.mode_row = None
    r = _get(env, PUBLIC_PATH, session=GOOD)
    assert r.status_code == 200
    assert read_gate.mode_word() == "off"
    assert env.stub.calls["session"] == 0 and read_gate._census == {}


def test_refresh_failure_keeps_last_known(env):
    K.reset_gate()
    env.stub.mode_row = "enforce"
    assert _get(env, PUBLIC_PATH).status_code == 401
    env.stub.fail.add("mode")
    env.clock.advance(read_gate.MODE_TTL + 1)
    r = _get(env, PUBLIC_PATH)
    assert r.status_code == 401 and r.json()["detail"] == "read_credential_required"
    assert read_gate.mode_word() == "enforce"


def test_an_unrecognised_stored_stage_is_not_off(env):
    K.reset_gate()
    env.stub.mode_row = "enforcing"
    assert _get(env, PUBLIC_PATH).status_code == 503


# -- requirement 19: the probe ------------------------------------------------

def test_probe_enforced_in_off_mode(env):
    env.set_mode("off")
    r = _get(env, read_gate.PROBE_PATH)
    assert r.status_code == 401 and r.json()["detail"] == "read_credential_required"
    assert r.headers["Cache-Control"] == "no-store, private"
    ok = _get(env, read_gate.PROBE_PATH, internal=K.INTERNAL_KEY)
    assert ok.status_code == 200
    assert ok.headers["Cache-Control"] == "no-store, private"
    assert K.census_rows(route=read_gate.PROBE_PATH, **{"class": "internal"})
    assert K.census_rows(route=read_gate.PROBE_PATH, **{"class": "mod_no_session"}, refused=True)


def test_probe_reports_credential_class(env):
    env.set_mode("log")
    got = {}
    for name, kw in (("internal", {"internal": K.INTERNAL_KEY}), ("session", {"session": GOOD}),
                     ("operator", {"operator": OP_A, "version": None})):
        r = _get(env, read_gate.PROBE_PATH, **kw)
        assert r.status_code == 200, r.text
        got[name] = r.json()
    assert set(got["session"]) == {"node", "boot_id", "mode", "credential_class", "key_id"}
    assert got["internal"]["credential_class"] == "internal"
    assert got["session"]["credential_class"] == "session"
    assert (got["operator"]["credential_class"], got["operator"]["key_id"]) == ("operator:scrmod", "7/1")
    assert got["session"]["node"] == "primary" and got["session"]["boot_id"] == read_gate.BOOT_ID
    assert got["session"]["mode"] == "log"


# -- requirement 22: the mode in the mod-version answer -----------------------

def test_mod_version_reports_mode(env):
    K.reset_gate()
    env.stub.mode_row = "log"
    body = _get(env, "/api/v1/mod-version", version=K.ADVERT_VERSION).json()
    assert body["read_gate"] == "log"
    assert body["read_gate_open"] == read_gate.ungated_templates(main.app.routes)
    env.stub.mode_row = "enforce"
    assert _get(env, "/api/v1/mod-version", version=K.ADVERT_VERSION).json()["read_gate"] == "log"   # TTL
    env.clock.advance(read_gate.MODE_TTL + 1)
    assert _get(env, "/api/v1/mod-version", version=K.ADVERT_VERSION).json()["read_gate"] == "enforce"


# -- M7 in-repo half / requirement 23: Cache-Control --------------------------

def test_enforce_responses_no_store(env):
    env.set_mode("enforce")
    ok = _get(env, PUBLIC_PATH, session=GOOD)
    assert ok.status_code == 200 and ok.headers["Cache-Control"] == "no-store, private"
    for kw, status in (({}, 401), ({"session": UNKNOWN_TOKEN}, 401)):
        r = _get(env, PUBLIC_PATH, **kw)
        assert r.status_code == status and r.headers["Cache-Control"] == "no-store, private"
    r = _get(env, BOT_PATH)
    assert r.status_code == 403 and r.headers["Cache-Control"] == "no-store, private"
    env.stub.fail.add("session")
    r = _get(env, PUBLIC_PATH, session=GOOD + "x")
    assert r.status_code == 503 and r.headers["Cache-Control"] == "no-store, private"
    env.stub.fail.clear()
    # OPEN is not marked
    assert "Cache-Control" not in _get(env, "/api/v1/mod-version").headers
    # log: a gated response is exactly what it was
    env.set_mode("log")
    assert "Cache-Control" not in _get(env, PUBLIC_PATH, session=GOOD).headers


# -- requirement 24 -----------------------------------------------------------

def test_rate_limit_bypass_unchanged():
    assert main._RATE_LIMIT_BYPASS == frozenset({
        "/api/v1/mod-version", "/api/v1/health", "/api/v1/healthz", "/api/v1/chat/post",
        "/api/v1/chat/recent", "/api/v1/admin/maintenance/status"})
    for p in ("/api/v1/admin/operators/keys", "/api/v1/admin/operators/keys/revoke",
              "/api/v1/admin/operators", "/api/v1/admin/read-gate/mode",
              "/api/v1/admin/read-census", read_gate.PROBE_PATH):
        assert p not in main._RATE_LIMIT_BYPASS


# -- build round 2 M8: every credential lookup is charged to the limiter first --

def _unissued(i):
    """A well-formed operator key no row holds (each one a cache miss)."""
    return "scrop1_" + "%043d" % i


def _charges():
    return sum(len(dq) for dq in main._RL_BUCKETS.values())


def test_unissued_operator_keys_without_version_reach_429(env):
    """A GET with no X-Mod-Version and a well-formed unissued operator key is
    charged to the per-address bucket BEFORE the version gate's operator
    lookup: up to the bucket limit each answers 426 after one lookup, past it
    each answers 429 and the operator table is not read again."""
    limit = main._RL_GLOBAL[0]
    statuses = [_get(env, PUBLIC_PATH, version=None, operator=_unissued(i)).status_code
                for i in range(limit + 10)]
    assert statuses[:limit] == [426] * limit, statuses
    assert statuses[limit:] == [429] * 10, statuses
    assert env.stub.calls["operator"] == limit
    assert env.calls["public"] == []


def test_operator_exemption_charged_once(env):
    """The version gate's charge is the request's ONE charge: a live key with
    no version reaches the handler with one bucket entry, exactly as a request
    with a version header does through rate_limit_gate alone."""
    assert _get(env, PUBLIC_PATH, version=None, operator=OP_A).status_code == 200
    assert _charges() == 1
    assert _get(env, PUBLIC_PATH).status_code == 200
    assert _charges() == 2


def test_internal_paths_keep_auth_before_parse(env):
    """/api/v1/internal/* without the internal key is refused by
    rate_limit_gate before anything else runs; an operator key on it is never
    looked up and charges nothing."""
    r = _get(env, "/api/v1/internal/zz-verified-reads", version=None, operator=_unissued(1))
    assert r.status_code == 403 and r.json() == {"error": "forbidden"}
    assert env.stub.calls["operator"] == 0 and _charges() == 0


def test_bypassed_route_lookups_charged_at_miss(env, monkeypatch):
    """A gated route the limiter never charges (one in _RATE_LIMIT_BYPASS):
    a session lookup that would read the database is charged first, so past
    the bucket an unknown token is not looked up (429 in enforce; counted
    lookup_limited and passed in log), while a cached valid session is not
    charged at all."""
    monkeypatch.setattr(main, "_RATE_LIMIT_BYPASS", main._RATE_LIMIT_BYPASS | {PUBLIC_PATH})
    limit = main._RL_GLOBAL[0]
    env.set_mode("enforce")
    st = [_get(env, PUBLIC_PATH, session="unknown-token-%05d" % i).status_code
          for i in range(limit + 5)]
    assert st[:limit] == [401] * limit and st[limit:] == [429] * 5, st
    assert env.stub.calls["session"] == limit
    env.set_mode("log")
    read_gate.census_reset()
    assert _get(env, PUBLIC_PATH, session="unknown-token-last").status_code == 200
    assert env.stub.calls["session"] == limit
    assert K.census_rows(route=PUBLIC_PATH, **{"class": "lookup_limited"})
    env.set_mode("enforce")
    main._RL_BUCKETS.clear()
    for _ in range(limit + 20):
        assert _get(env, PUBLIC_PATH, session=GOOD).status_code == 200
    assert _charges() == 1 and env.stub.calls["session"] == limit + 1


def test_socket_operator_lookup_charged(env):
    """The chat socket passes no http middleware: ws_chat charges its address
    at connect, before the count's operator lookup (which the connect charge
    covers: one charge per socket), so past the bucket the socket is closed
    1013 rate_limited and no lookup runs."""
    env.set_mode("log")
    limit = main._RL_GLOBAL[0]
    closes = []
    for i in range(limit + 3):
        with env.client.websocket_connect("/api/v1/ws/chat", headers={
                "X-Mod-Version": K.LIVE_VERSION, "X-Operator-Key": _unissued(i)}) as ws:
            try:
                ws.receive_text()
            except WebSocketDisconnect as ex:
                closes.append((i, ex.code, ex.reason))
    assert closes == [(i, 1013, "rate_limited") for i in range(limit, limit + 3)], closes
    assert env.stub.calls["operator"] == limit and _charges() == limit
    assert K.census_rows(route=read_gate.SOCKET_TEMPLATE, **{"class": "mod_no_session"})


def test_count_socket_charges_an_uncharged_connection(env):
    """count_socket on a connection nothing has charged (the future socket
    protocol's order: the stage, then the lookups) charges the operator
    lookup's cache miss to the serving app's limiter itself: past the bucket
    the key is not looked up."""
    import asyncio
    from types import SimpleNamespace
    from starlette.datastructures import Headers
    env.set_mode("log")
    limit = main._RL_GLOBAL[0]

    def conn(i):
        return SimpleNamespace(
            scope={"app": main.app}, state=SimpleNamespace(), url=SimpleNamespace(path="/api/v1/ws/chat"),
            client=SimpleNamespace(host="testclient"),
            headers=Headers(headers={"X-Mod-Version": K.LIVE_VERSION, "X-Operator-Key": _unissued(i)}))
    for i in range(limit + 3):
        asyncio.run(read_gate.count_socket(conn(i)))
    assert env.stub.calls["operator"] == limit and _charges() == limit


def test_bypassed_route_operator_lookups_charged_at_miss(env, monkeypatch):
    """The operator-key twin of the session case above: on a gated route the
    limiter never charges, each unissued key's lookup is charged first, so
    past the bucket no key is looked up (429 in enforce)."""
    monkeypatch.setattr(main, "_RATE_LIMIT_BYPASS", main._RATE_LIMIT_BYPASS | {PUBLIC_PATH})
    limit = main._RL_GLOBAL[0]
    env.set_mode("enforce")
    st = [_get(env, PUBLIC_PATH, operator=_unissued(i)).status_code for i in range(limit + 5)]
    assert st[:limit] == [401] * limit and st[limit:] == [429] * 5, st
    assert env.stub.calls["operator"] == limit


def test_lookup_charge_follows_the_serving_app(env, monkeypatch):
    """main.py imported a second time (the suite imports it as api.main too)
    builds a second app with its own charge and buckets. A lookup on THIS
    app's connection is charged to this app's buckets: with the second copy's
    bucket for this address already full, the first `limit` lookups here still
    run and only the ones past this app's own bucket are refused."""
    from api import main as second
    assert second is not main and second.app is not main.app
    monkeypatch.setattr(main, "_RATE_LIMIT_BYPASS", main._RATE_LIMIT_BYPASS | {PUBLIC_PATH})
    monkeypatch.setattr(second, "_RL_BUCKETS", second._RL_BUCKETS.__class__(second._RL_BUCKETS.default_factory))
    limit = main._RL_GLOBAL[0]
    second._RL_BUCKETS["testclient|g"].extend([second._rl_time.monotonic()] * (limit + 10))
    env.set_mode("enforce")
    st = [_get(env, PUBLIC_PATH, session="unknown-token-%05d" % i).status_code
          for i in range(limit + 5)]
    assert st[:limit] == [401] * limit and st[limit:] == [429] * 5, st
    assert env.stub.calls["session"] == limit


# -- build round 3 M-new-2: ws_chat's own lookups are charged first -----------
#
# ws_chat reads the database for the lockdown snapshot at connect, the session
# row of each auth frame, and per chat message the lockdown row (process cache),
# the ban and mute rows, the sender's metadata and the insert. The seam below
# wraps the gate's StubDB: ws_chat's statements are counted by kind and answered
# empty (lockdown off, no ban, no mute, no metadata); the gate's own statements
# go to the StubDB as before.

CHAT_SID = "76561190000000777"


class _ChatSeam:
    def __init__(self, stub):
        self.stub, self.calls, self.auth_rows = stub, Counter(), {}

    def __call__(self):
        return _ChatSession(self)

    def total(self):
        return sum(self.calls.values())


class _ChatSession:
    def __init__(self, seam):
        self.seam, self.inner = seam, K._StubSession(seam.stub)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def execute(self, stmt, params=None):
        sql, params = str(stmt), params or {}
        for kind, needle in (("lockdown", "'chat_lockdown'"), ("auth", "SELECT steam_id, verified"),
                             ("ban", "player_bans"), ("mute", "chat_mutes"), ("meta", "glicko_ratings"),
                             ("insert", "INSERT INTO chat_messages")):
            if needle in sql:
                self.seam.calls[kind] += 1
                if kind == "lockdown":
                    return K._Result(scalar="0")
                if kind == "auth":
                    return K._Result(row=self.seam.auth_rows.get(params.get("th")))
                return K._Result()
        return await self.inner.execute(stmt, params)


@pytest.fixture
def chat(env, monkeypatch):
    seam = _ChatSeam(env.stub)
    monkeypatch.setattr(K.database, "async_session", seam)   # what ws_chat's lookups import
    monkeypatch.setattr(main, "_chat_lockdown_cache", {"value": False, "loaded": False, "at": 0.0, "gen": 0})
    monkeypatch.setattr(main, "_chat_rate", {})
    monkeypatch.setattr(main, "_chat_last_msg", {})
    env.set_mode("log")
    env.seam = seam
    return env


def _expire_lockdown_cache():
    main._chat_lockdown_cache.update({"loaded": False, "at": 0.0})


def _fill_bucket():
    """The address's global bucket at its limit, as if other work had used it."""
    limit = main._RL_GLOBAL[0]
    dq = main._RL_BUCKETS["testclient|g"]
    dq.extend([main._rl_time.monotonic()] * (limit - len(dq)))


def _chat_frame(i):
    return '{"steam_id":"%s","display_name":"t","message":"hello %d"}' % (CHAT_SID, i)


def _auth_frame(token):
    return '{"type":"auth","steam_id":"%s","token":"%s"}' % (CHAT_SID, token)


def test_ws_anonymous_reconnect_refused_before_any_lookup(chat):
    """An anonymous socket (version header, no credential) that reconnects is
    charged at every connect, before its first database access: the first
    `limit` sockets are admitted and each reads the lockdown snapshot; every
    socket past the bucket is closed 1013 rate_limited, gets no lock frame,
    and reads nothing."""
    limit = main._RL_GLOBAL[0]
    frames, closes = [], []
    for i in range(limit + 10):
        _expire_lockdown_cache()          # so an admitted socket's snapshot is a read
        with chat.client.websocket_connect("/api/v1/ws/chat",
                                           headers={"X-Mod-Version": K.LIVE_VERSION}) as ws:
            try:
                frames.append(ws.receive_text())
            except WebSocketDisconnect as ex:
                closes.append((i, ex.code, ex.reason))
    assert frames == ['{"type":"lock","locked":0}'] * limit
    assert closes == [(i, 1013, "rate_limited") for i in range(limit, limit + 10)], closes
    assert chat.seam.calls == Counter({"lockdown": limit}), chat.seam.calls
    assert chat.stub.calls["operator"] == 0 and _charges() == limit


def test_ws_no_credential_lookup_count_stops_at_the_limit(chat):
    """No-credential sockets that each send one auth frame (an unknown token)
    and one chat message: a socket costs three charges (connect, auth frame,
    message) and six lookups (snapshot, session row, ban, mute, metadata,
    insert). Once the bucket is spent the count of lookups stops increasing:
    later sockets are closed at connect having read nothing."""
    limit = main._RL_GLOBAL[0]
    admitted = limit // 3
    closes = []
    for i in range(admitted + 10):
        _expire_lockdown_cache()
        with chat.client.websocket_connect("/api/v1/ws/chat",
                                           headers={"X-Mod-Version": K.LIVE_VERSION}) as ws:
            try:
                ws.receive_text()
            except WebSocketDisconnect as ex:
                closes.append((i, ex.code, ex.reason))
                continue
            ws.send_text(_auth_frame("unknown-token-%05d" % i))
            ws.send_text(_chat_frame(i))
        if i == admitted - 1:
            at_limit = dict(chat.seam.calls)
    assert at_limit == {"lockdown": admitted, "auth": admitted, "ban": admitted,
                        "mute": admitted, "meta": admitted, "insert": admitted}, at_limit
    assert dict(chat.seam.calls) == at_limit, chat.seam.calls
    assert closes == [(i, 1013, "rate_limited") for i in range(admitted, admitted + 10)], closes
    assert _charges() == 3 * admitted == limit


def test_ws_auth_frame_and_message_charged_before_their_lookups(chat):
    """On a socket already admitted, a spent bucket stops the next auth frame's
    session read and the next message's ban, mute, metadata and insert."""
    with chat.client.websocket_connect("/api/v1/ws/chat",
                                       headers={"X-Mod-Version": K.LIVE_VERSION}) as ws:
        assert ws.receive_text() == '{"type":"lock","locked":0}'
        _fill_bucket()
        ws.send_text(_auth_frame("unknown-token-x"))
        ws.send_text(_chat_frame(1))
    assert chat.seam.calls == Counter({"lockdown": 1}), chat.seam.calls


def test_ws_allowed_sockets_unchanged(chat):
    """Without a spent bucket a socket behaves as before: the lock frame, a
    verified auth frame, a message relayed to the other subscriber with the
    same fields; and the bot's socket (the internal key) is never charged,
    however often it reconnects."""
    chat.seam.auth_rows[K.sha(GOOD)] = {"steam_id": CHAT_SID, "verified": True,
                                        "expires_at": None}
    hdrs = {"X-Mod-Version": K.LIVE_VERSION}
    with chat.client.websocket_connect("/api/v1/ws/chat", headers=hdrs) as listener:
        assert listener.receive_text() == '{"type":"lock","locked":0}'
        with chat.client.websocket_connect("/api/v1/ws/chat", headers=hdrs) as sender:
            assert sender.receive_text() == '{"type":"lock","locked":0}'
            sender.send_text(_auth_frame(GOOD))
            sender.send_text(_chat_frame(7))
            got = listener.receive_json()
    assert {k: got[k] for k in ("source", "steam_id", "display_name", "rating", "title",
                                "title_color", "message", "channel")} == {
        "source": "ingame", "steam_id": CHAT_SID, "display_name": "t", "rating": None,
        "title": None, "title_color": None, "message": "hello 7", "channel": "global"}
    assert chat.seam.calls["auth"] == 1 and chat.seam.calls["insert"] == 1
    main._RL_BUCKETS.clear()
    limit = main._RL_GLOBAL[0]
    for _ in range(limit + 10):
        with chat.client.websocket_connect("/api/v1/ws/chat",
                                           headers={"X-Internal-Key": K.INTERNAL_KEY}) as ws:
            ws.receive_text()
            ws.send_text(_chat_frame(8))
    assert _charges() == 0


# -- M5 / requirement 26: the chat socket is counted --------------------------

def test_ws_connect_counted_by_class(env):
    env.set_mode("log")
    shapes = [
        ({"X-Internal-Key": K.INTERNAL_KEY}, "internal", ""),
        ({"X-Mod-Version": K.LIVE_VERSION, "X-Session-Token": GOOD}, "session", ""),
        ({"X-Mod-Version": K.LIVE_VERSION, "X-Operator-Key": OP_A}, "operator:scrmod", "7/1"),
        ({"X-Mod-Version": K.LIVE_VERSION}, "mod_no_session", ""),
    ]
    for hdrs, cls, key_id in shapes:
        with env.client.websocket_connect("/api/v1/ws/chat", headers=hdrs) as ws:
            ws.receive_text()                       # the lockdown snapshot: accepted
        rows = K.census_rows(route=read_gate.SOCKET_TEMPLATE, **{"class": cls})
        assert rows and rows[0]["key_id"] == key_id and rows[0]["refused"] is False, (cls, read_gate._census)
    env.set_mode("off")
    read_gate.census_reset()
    with env.client.websocket_connect("/api/v1/ws/chat", headers={"X-Mod-Version": K.LIVE_VERSION}) as ws:
        ws.receive_text()
    assert read_gate._census == {}
    assert read_gate.SOCKET_READ_GATE_BUILT is False


def test_ws_connect_counted_other(env, monkeypatch):
    """The fifth class: no valid credential and no version header. Reachable
    only while the socket admits a missing version (REQUIRE_MOD_VERSION
    False); with it True such a socket is closed `outdated` before it is
    counted at all."""
    env.set_mode("log")
    monkeypatch.setattr(main, "REQUIRE_MOD_VERSION", False)
    for hdrs in ({}, {"X-Operator-Key": OP_UNISSUED}):
        read_gate.census_reset()
        with env.client.websocket_connect("/api/v1/ws/chat", headers=hdrs) as ws:
            ws.receive_text()
        rows = K.census_rows(route=read_gate.SOCKET_TEMPLATE)
        assert [(r["class"], r["version_header"], r["refused"]) for r in rows] == \
            [("other", False, False)], (hdrs, rows)
    monkeypatch.setattr(main, "REQUIRE_MOD_VERSION", True)
    read_gate.census_reset()
    with pytest.raises(Exception):
        with env.client.websocket_connect("/api/v1/ws/chat", headers={}) as ws:
            ws.receive_text()
    assert K.census_rows(route=read_gate.SOCKET_TEMPLATE) == []


# -- bar BV-A: the advert only for a client that reads it ---------------------

TRUNK_MOD_VERSION_KEYS = {"version", "min_version", main._INVOLUNTARY_CAUSE_CAPABILITY_FIELD}


@pytest.mark.parametrize("sent", [None, "1.40.3", "1.40.99", "1.4", "0.0.0", "abc", "1.41.0-beta",
                                  " 1.41.0", "1.41.0.0.1", "-1.41.0"])
def test_mod_version_without_advert_for_older_clients(env, sent):
    """No header, an older version or an unparseable one: exactly trunk's
    three keys, so a 1.40.3 client's answer is trunk's byte for byte."""
    env.stub.mode_row = "enforce"
    body = _get(env, "/api/v1/mod-version", version=sent).json()
    assert set(body) == TRUNK_MOD_VERSION_KEYS, body


@pytest.mark.parametrize("sent", ["1.41.0", "1.41", "1.41.1", "1.42.0", "2.0.0"])
def test_mod_version_advert_for_1410_and_later(env, sent):
    env.stub.mode_row = "log"
    body = _get(env, "/api/v1/mod-version", version=sent).json()
    assert set(body) == TRUNK_MOD_VERSION_KEYS | {"read_gate", "read_gate_open"}, body
    assert body["read_gate"] == "log"
    assert body["read_gate_open"] == read_gate.ungated_templates(main.app.routes)


def test_advert_requested_is_strict():
    assert read_gate.READ_GATE_ADVERT_MIN == (1, 41, 0)
    for v in ("1.41.0", "1.41", "1.41.0.0", "10.0.0"):
        assert read_gate.advert_requested(v), v
    for v in (None, "", "1.40.9", "1.41.0 ", "v1.41.0", "1.41.x", "1..41", 1410, b"1.41.0"):
        assert not read_gate.advert_requested(v), v
