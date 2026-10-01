"""Verified reads: operator keys on a real PostgreSQL (migration 367 and the
admin routes that issue, revoke and list them).

Live: READ_GATE_TEST_PG_DSN (read_gate_pg_harness). Every request goes
through the real app; the gate's lookups and the handlers' sessions both open
on the lane's case schema.
"""
from __future__ import annotations

import hashlib

import pytest

import read_gate_pg_harness as PG
import read_gate_testkit as K
import main
import read_gate


@pytest.fixture(scope="module")
def lane():
    PG.require_live_pg()
    return PG.shared_lane()


@pytest.fixture
def client(lane, monkeypatch):
    monkeypatch.setattr(main, "ADMIN_HMAC_SECRET", K.ADMIN_SECRET)
    monkeypatch.setenv("API_SECRET_KEY", K.INTERNAL_KEY)
    lane.execute("INSERT INTO admin_users (steam_id, notes) VALUES ($1, 'read-gate test admin') "
                 "ON CONFLICT DO NOTHING", K.ADMIN_ID)
    lane.execute("DELETE FROM api_operator_keys")
    lane.execute("DELETE FROM runtime_settings WHERE key = 'read_gate_mode'")
    K.reset_gate()
    yield lane.client(monkeypatch)
    K.reset_gate()


def _issue(client, name, contact="ops@example.invalid"):
    try:
        target = read_gate.canonical_operator_name(name)
    except ValueError:
        target = name
    return client.post("/api/v1/admin/operators/keys", json={
        "admin_steam_id": K.ADMIN_ID, "hmac_signature": K.admin_sign("operator_key_issue", target),
        "operator_name": name, "contact": contact})


def _revoke(client, key_id):
    return client.post("/api/v1/admin/operators/keys/revoke", json={
        "admin_steam_id": K.ADMIN_ID, "hmac_signature": K.admin_sign("operator_key_revoke", str(key_id)),
        "id": key_id})


def _list(client):
    return client.get("/api/v1/admin/operators", params={
        "admin_steam_id": K.ADMIN_ID, "hmac_signature": K.admin_sign("operator_key_list", "")})


def _shape(lane):
    cols = [tuple(r) for r in lane.fetch(
        "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'api_operator_keys' ORDER BY ordinal_position")]
    cons = sorted(tuple(r) for r in lane.fetch(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'api_operator_keys'::regclass"))
    idx = sorted(tuple(r) for r in lane.fetch(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema() "
        "AND tablename = 'api_operator_keys'"))
    return cols, cons, idx


# -- Group A: the migration ---------------------------------------------------

def test_operator_key_migration_idempotent(lane):
    before = _shape(lane)
    assert before[0], "367 did not create api_operator_keys"
    lane.execute(PG.migration_text())
    once = _shape(lane)
    lane.execute(PG.migration_text())
    twice = _shape(lane)
    assert before == once == twice
    names = {c[0] for c in before[1]}
    assert {"api_operator_keys_name_slug", "api_operator_keys_slot_check",
            "api_operator_keys_key_hash_key"} <= names
    assert any(i[0] == "ux_api_operator_keys_live_slot" and "WHERE (revoked_at IS NULL)" in i[1]
               for i in before[2])


def test_operator_name_check_rejects_mixed_case(lane):
    import asyncpg
    with pytest.raises(asyncpg.CheckViolationError):
        lane.execute("INSERT INTO api_operator_keys (operator_name, contact, slot, key_hash, "
                     "key_hint, created_by) VALUES ('SCRMOD', 'c', 1, $1, 'h', 'x')", "a" * 64)
    with pytest.raises(asyncpg.CheckViolationError):
        lane.execute("INSERT INTO api_operator_keys (operator_name, contact, slot, key_hash, "
                     "key_hint, created_by) VALUES (' scrmod', 'c', 1, $1, 'h', 'x')", "b" * 64)


# -- requirement 2: one canonical identity ------------------------------------

def test_canonical_operator_name():
    assert read_gate.canonical_operator_name("  ScrMod ") == "scrmod"
    assert read_gate.canonical_operator_name("release-train") == "release-train"
    for bad in ("", "s", "-x", "scr mod", "scr_mod", "x" * 33, "scrm\u00f6d"):
        with pytest.raises(ValueError):
            read_gate.canonical_operator_name(bad)


def test_operator_identity_case_folded(client, lane):
    a = _issue(client, "scrmod")
    b = _issue(client, "scrmod")
    assert (a.status_code, b.status_code) == (200, 200), (a.text, b.text)
    assert {a.json()["slot"], b.json()["slot"]} == {1, 2}
    c = _issue(client, "SCRMOD")
    assert c.status_code == 409 and c.json()["detail"] == "two_live_keys"
    import asyncpg
    with pytest.raises(asyncpg.UniqueViolationError):
        lane.execute("INSERT INTO api_operator_keys (operator_name, contact, slot, key_hash, "
                     "key_hint, created_by) VALUES ('scrmod', 'c', 1, $1, 'h', 'x')", "c" * 64)
    names = {r[0] for r in lane.fetch("SELECT DISTINCT operator_name FROM api_operator_keys")}
    assert names == {"scrmod"}


# -- requirement 15 / design 9.4 ----------------------------------------------

def test_issue_returns_the_key_once_and_stores_only_its_hash(client, lane):
    r = _issue(client, "scrmod")
    assert r.status_code == 200, r.text
    key = r.json()["key"]
    assert key.startswith(read_gate.OPERATOR_KEY_PREFIX)
    rows = lane.fetch("SELECT * FROM api_operator_keys")
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["key_hash"] == hashlib.sha256(key.encode()).hexdigest()
    assert all(str(v) != key for v in row.values())
    assert row["key_hint"] == r.json()["key_hint"] and len(row["key_hint"]) == 6
    listed = _list(client)
    assert listed.status_code == 200
    body = listed.text
    assert "key_hash" not in body and row["key_hash"] not in body and key not in body
    audit = lane.fetch("SELECT action FROM admin_actions WHERE admin_steam_id = $1 "
                       "AND action = 'operator_key_issue'", K.ADMIN_ID)
    assert audit


def test_third_key_refused_and_revoke_frees_the_slot(client, lane):
    one = _issue(client, "scrmod").json()
    _issue(client, "scrmod")
    assert _issue(client, "scrmod").status_code == 409
    rv = _revoke(client, one["id"])
    assert rv.status_code == 200 and rv.json()["revoked"] is True
    assert _revoke(client, one["id"]).status_code == 404
    again = _issue(client, "scrmod")
    assert again.status_code == 200 and again.json()["slot"] == one["slot"]


def test_admin_routes_require_the_signature(client):
    r = client.post("/api/v1/admin/operators/keys", json={
        "admin_steam_id": K.ADMIN_ID, "hmac_signature": "0" * 64,
        "operator_name": "scrmod", "contact": "c"})
    assert r.status_code == 403
    r = client.post("/api/v1/admin/operators/keys", json={
        "admin_steam_id": K.ADMIN_ID, "hmac_signature": K.admin_sign("operator_key_issue", "SCRMOD"),
        "operator_name": "SCRMOD", "contact": "c"})
    assert r.status_code == 403            # the signature names the canonical identity
    assert client.get("/api/v1/admin/operators", params={"admin_steam_id": K.ADMIN_ID}).status_code == 403


def test_issued_key_reads_through_the_gate_and_revocation_ends_it(client, lane):
    read_gate.mode_cache_set("enforce")
    issued = _issue(client, "scrmod").json()
    probe = client.get(read_gate.PROBE_PATH, headers={"X-Operator-Key": issued["key"]})
    assert probe.status_code == 200, probe.text
    assert probe.json()["credential_class"] == "operator:scrmod"
    assert probe.json()["key_id"] == f"{issued['id']}/{issued['slot']}"
    _revoke(client, issued["id"])
    # the revoking process drops its cached positive at once
    refused = client.get(read_gate.PROBE_PATH, headers={"X-Operator-Key": issued["key"],
                                                        "X-Mod-Version": K.LIVE_VERSION})
    assert refused.status_code == 401 and refused.json()["detail"] == "operator_key_invalid"


# -- requirement 16 on a real database: a refused flip leaves the row --------

def _mode(client, mode):
    return client.post("/api/v1/admin/read-gate/mode", json={
        "admin_steam_id": K.ADMIN_ID, "hmac_signature": K.admin_sign("read_gate_mode", mode),
        "mode": mode})


def test_mode_route_writes_the_row_and_refusals_leave_it(client, lane, monkeypatch):
    assert _mode(client, "log").status_code == 200
    stored = lambda: [r[0] for r in lane.fetch(
        "SELECT value FROM runtime_settings WHERE key = 'read_gate_mode'")]
    assert stored() == ["log"]
    r = _mode(client, "enforce")
    assert r.status_code == 409 and r.json()["detail"] == "client_floor_unnamed"
    assert stored() == ["log"]
    monkeypatch.setattr(read_gate, "READ_GATE_CLIENT_MIN", "1.41.0")
    monkeypatch.setattr(main, "MIN_MOD_VERSION_EFFECTIVE", "1.40.3")
    r = _mode(client, "enforce")
    assert r.status_code == 409 and r.json()["detail"] == "client_floor_below_read_gate"
    assert stored() == ["log"]
    monkeypatch.setattr(main, "MIN_MOD_VERSION_EFFECTIVE", "1.41.0")
    r = _mode(client, "enforce")
    assert r.status_code == 409 and r.json()["detail"] == "socket_read_gate_absent"
    assert stored() == ["log"]
    audit = lane.fetch("SELECT details FROM admin_actions WHERE action = 'read_gate_mode'")
    assert len(audit) == 1
