"""Verified reads, design 9.3 on a real PostgreSQL: the stage is one
runtime_settings row, read by each process through a TTL cache, and moves
without a restart.

"Another process" is simulated honestly: after the mode route has run (which
updates THIS process's cache), the cache is put back to the value it held
before, with a fresh timestamp -- the state of a second box that read the row
just before the flip. That box keeps its stage until the TTL passes, then
reads the row. The app object is never rebuilt and no module is reloaded.
"""
from __future__ import annotations

import pytest

import read_gate_pg_harness as PG
import read_gate_testkit as K
import main
import read_gate

FLOOR = "1.41.0"
PUBLIC_ROUTES = ("/api/v1/leaderboard", "/api/v1/cards", "/api/v1/rank-tiers",
                 "/api/v1/shop/items", "/api/v1/achievements/definitions")


@pytest.fixture(scope="module")
def lane():
    PG.require_live_pg()
    return PG.shared_lane()


@pytest.fixture
def clock(monkeypatch):
    c = K.Clock()
    monkeypatch.setattr(read_gate, "_mono", lambda: c.mono)
    monkeypatch.setattr(read_gate, "_wall", lambda: c.wall)
    return c


@pytest.fixture
def client(lane, monkeypatch, clock):
    monkeypatch.setattr(main, "ADMIN_HMAC_SECRET", K.ADMIN_SECRET)
    monkeypatch.setenv("API_SECRET_KEY", K.INTERNAL_KEY)
    lane.execute("INSERT INTO admin_users (steam_id, notes) VALUES ($1, 'read-gate test admin') "
                 "ON CONFLICT DO NOTHING", K.ADMIN_ID)
    lane.execute("DELETE FROM runtime_settings WHERE key = 'read_gate_mode'")
    K.reset_gate()
    yield lane.client(monkeypatch)
    lane.execute("DELETE FROM runtime_settings WHERE key = 'read_gate_mode'")
    K.reset_gate()


def _stored(lane):
    return [r[0] for r in lane.fetch("SELECT value FROM runtime_settings WHERE key = 'read_gate_mode'")]


def _set_mode(client, mode):
    return client.post("/api/v1/admin/read-gate/mode", json={
        "admin_steam_id": K.ADMIN_ID, "hmac_signature": K.admin_sign("read_gate_mode", mode),
        "mode": mode})


def _as_other_box(previous, clock):
    """This process's cache as a box that read `previous` just now."""
    read_gate._mode_cache.update({"value": previous, "loaded": True, "at": clock.mono})


def test_log_refuses_nothing(client, lane):
    assert _set_mode(client, "log").status_code == 200
    for path in PUBLIC_ROUTES:
        assert read_gate.route_class(path) == read_gate.C_PUBLIC
    before = {p: sum(r["count"] for r in K.census_rows(route=p)) for p in PUBLIC_ROUTES}
    answers = []
    for _ in range(10):
        for path in PUBLIC_ROUTES:
            main._RL_BUCKETS.clear()
            answers.append((path, client.get(path, headers=K.headers()).status_code))
    assert len(answers) == 50
    assert all(code == 200 for _, code in answers), answers
    for path in PUBLIC_ROUTES:
        rows = K.census_rows(route=path, method="GET", **{"class": "mod_no_session"},
                             version_header=True, refused=False)
        assert sum(r["count"] for r in rows) == 10, (path, rows)
        assert sum(r["count"] for r in K.census_rows(route=path)) - before[path] == 10
        assert not K.census_rows(route=path, refused=True)


def test_flip_without_restart(client, lane, monkeypatch, clock):
    app_id = id(main.app)
    monkeypatch.setattr(read_gate, "READ_GATE_CLIENT_MIN", FLOOR)
    monkeypatch.setattr(main, "MIN_MOD_VERSION_EFFECTIVE", FLOOR)
    monkeypatch.setattr(read_gate, "SOCKET_READ_GATE_BUILT", True)
    h = K.headers(version=FLOOR)
    path = "/api/v1/leaderboard"

    assert _set_mode(client, "log").status_code == 200
    assert client.get(path, headers=h).status_code == 200

    r = _set_mode(client, "enforce")
    assert r.status_code == 200, r.text
    assert _stored(lane) == ["enforce"]
    _as_other_box("log", clock)
    assert client.get(path, headers=h).status_code == 200          # within its TTL
    clock.advance(read_gate.MODE_TTL + 1)
    refused = client.get(path, headers=h)
    assert refused.status_code == 401 and refused.json()["detail"] == "read_credential_required"

    assert _set_mode(client, "log").status_code == 200
    _as_other_box("enforce", clock)
    assert client.get(path, headers=h).status_code == 401
    clock.advance(read_gate.MODE_TTL + 1)
    assert client.get(path, headers=h).status_code == 200
    assert id(main.app) == app_id


def test_floor_precondition(client, lane, monkeypatch):
    assert _set_mode(client, "log").status_code == 200
    monkeypatch.setattr(read_gate, "READ_GATE_CLIENT_MIN", FLOOR)
    monkeypatch.setattr(main, "MIN_MOD_VERSION_EFFECTIVE", "1.40.3")
    monkeypatch.setattr(read_gate, "SOCKET_READ_GATE_BUILT", True)
    r = _set_mode(client, "enforce")
    assert r.status_code == 409 and r.json()["detail"] == "client_floor_below_read_gate"
    assert _stored(lane) == ["log"]


def test_mode_route_refuses_an_unknown_mode(client, lane):
    assert _set_mode(client, "log").status_code == 200
    r = _set_mode(client, "enforcing")
    assert r.status_code == 422
    assert _stored(lane) == ["log"]


def test_advertised_mode(client, lane, clock):
    lane.execute("INSERT INTO runtime_settings (key, value) VALUES ('read_gate_mode', 'log') "
                 "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value")
    _as_other_box("off", clock)
    clock.advance(read_gate.MODE_TTL + 1)
    mv = client.get("/api/v1/mod-version", headers=K.headers())
    assert mv.status_code == 200 and mv.json()["read_gate"] == "log"
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["read_gate"] == "log" and health.json()["read_gate_build"] == "vr1"
