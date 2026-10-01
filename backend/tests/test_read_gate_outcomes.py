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
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
