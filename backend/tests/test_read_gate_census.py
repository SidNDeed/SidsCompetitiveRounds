"""Verified reads, requirement 19: the census read route's shape.

`GET /api/v1/admin/read-census` (admin signature, action read_census, target
"") answers this process's census: node, boot_id, since, mode, build, the
counts keyed (route, method, class, key id, version header, refused),
distinct sources per (class, hour) as COUNTS, and agents per unverified
class. It never answers a client address, a token, a key or a key hash.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import read_gate_testkit as K
import main
import read_gate

SESSION = "rg-census-session-token"
OPKEY = read_gate.OPERATOR_KEY_PREFIX + "census-test-key-material"
UA = {"User-Agent": "rg-census-agent/1"}


@pytest.fixture
def env(monkeypatch):
    with K.gate_env(monkeypatch, mode="log") as (stub, clock):
        monkeypatch.setattr(main, "ADMIN_HMAC_SECRET", K.ADMIN_SECRET)
        stub.add_session(SESSION, expires_at=clock.wall.replace(year=2027))
        stub.add_operator(OPKEY, row_id=7, name="scrmod", slot=2)
        rdb = K.RequestDB(stub)

        async def _db():
            yield rdb
        monkeypatch.setitem(main.app.dependency_overrides, main.get_db, _db)
        monkeypatch.setattr(main, "_RL_BUCKETS",
                            main._RL_BUCKETS.__class__(main._RL_BUCKETS.default_factory))
        yield TestClient(main.app, raise_server_exceptions=False), stub


def _census(client):
    return client.get("/api/v1/admin/read-census", params={
        "admin_steam_id": K.ADMIN_ID, "hmac_signature": K.admin_sign("read_census", "")}, headers=UA)


def test_census_read_shape(env):
    client, stub = env
    path = "/api/v1/scratch/census-public"
    with K.scratch_route(main.app, path):
        assert client.get(path, headers=K.headers(**UA)).status_code == 200
        assert client.get(path, headers=K.headers(session=SESSION, **UA)).status_code == 200
        assert client.get(path, headers=K.headers(operator=OPKEY, **UA)).status_code == 200
        assert client.get(path, headers=K.headers(version=None, operator=OPKEY, **UA)).status_code == 200
    r = _census(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"node", "boot_id", "since", "mode", "build", "counts",
                         "distinct_sources", "agents"}
    assert body["node"] == "primary" and body["mode"] == "log" and body["build"] == "vr1"
    assert body["boot_id"] == read_gate.BOOT_ID and body["since"] == read_gate.SINCE
    rows = [c for c in body["counts"] if c["route"] == path]
    for row in rows:
        assert set(row) == {"route", "method", "class", "key_id", "version_header", "refused", "count"}
    seen = {(c["class"], c["key_id"], c["version_header"], c["refused"], c["count"]) for c in rows}
    assert seen == {("mod_no_session", "", True, False, 1), ("session", "", True, False, 1),
                    ("operator:scrmod", "7/2", True, False, 1),
                    ("operator:scrmod", "7/2", False, False, 1)}, seen
    assert all(set(d) == {"class", "hour", "count"} and isinstance(d["count"], int)
               for d in body["distinct_sources"])
    assert body["agents"].get("mod_no_session") == {"rg-census-agent/1": 1}, body["agents"]
    raw = r.text
    for secret in (SESSION, OPKEY, K.sha(SESSION), K.sha(OPKEY), "testclient"):
        assert secret not in raw


def test_census_read_requires_the_signature(env):
    client, _ = env
    assert client.get("/api/v1/admin/read-census",
                      params={"admin_steam_id": K.ADMIN_ID}).status_code == 403
    assert client.get("/api/v1/admin/read-census", params={
        "admin_steam_id": K.ADMIN_ID, "hmac_signature": K.admin_sign("read_census", "x")}).status_code == 403
