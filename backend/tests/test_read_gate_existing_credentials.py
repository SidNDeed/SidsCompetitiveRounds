"""Verified reads, requirement 7: the ADMIN_SIGNED and PORTAL classes keep
their handlers' existing checks, in every mode. The gate refuses nothing on
them; the handler does.

Per route, in enforce with no session: no credential is refused, a wrong
credential is refused, a valid one is answered. A route in either class that
answers 200 with no credential fails.

The valid admin signature is produced by the handler's OWN canonical: the
verifier (`main._verify_admin_hmac`) is wrapped by a recorder that calls the
real one; the wrong-signature request records which (action, target) the
handler asked about, and the valid request signs exactly that. A route whose
check never reaches the verifier therefore fails here.

A valid credential must answer 200 -- except the routes in NON_AUTH_ANSWER,
whose path or query names a row this schema does not hold; for those the
handler's answer after a PASSED check is its not-found (asserted exactly,
with the verifier's True recorded).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.routing import APIRoute

import read_gate_pg_harness as PG
import read_gate_testkit as K
import main
import read_gate

PLAYER_ID = "76561190000004311"       # synthetic
PORTAL_TOKEN = "rg-portal-token-" + "a" * 32

# template -> (path values, extra query) for the placeholder parameters
FILL = {
    "/api/v1/bug-reports/{report_id}": ({"report_id": "00000000-0000-4000-8000-000000000001"}, {}),
    "/api/v1/bug-reports/{report_id}/log": ({"report_id": "00000000-0000-4000-8000-000000000001"}, {}),
    "/api/v1/admin/quarantine/triage/{mode}/{group_id}": (
        {"mode": "ffa", "group_id": "00000000-0000-4000-8000-000000000002"}, {}),
    "/api/v1/admin/pc/trades": ({}, {"steam_id": PLAYER_ID}),
    "/api/v1/admin/cosmetic-frames": ({}, {"submission_id": "999999"}),
    "/api/v1/i18n/contributors": ({}, {"lang": "ru"}),
    "/api/v1/i18n/keys": ({}, {"lang": "ru"}),
    "/api/v1/i18n/history": ({}, {"lang": "ru", "key_id": "1"}),
    "/api/v1/i18n/approved": ({}, {"lang": "ru"}),
    "/api/v1/i18n/proposals": ({}, {"lang": "ru"}),
}

# Measured: the handler's answer after a passed check, for a row the schema
# does not hold. Anything else (including 200) fails.
NON_AUTH_ANSWER = {
    "/api/v1/bug-reports/{report_id}": 404,
    "/api/v1/bug-reports/{report_id}/log": 404,
    "/api/v1/i18n/history": 404,
}


def _routes(names):
    out = []
    for r in main.app.routes:
        if isinstance(r, APIRoute) and "GET" in r.methods and r.path in names:
            out.append(r)
    assert {r.path for r in out} == set(names), "class list and app disagree"
    return sorted(out, key=lambda r: r.path)


ADMIN_ROUTES = _routes(read_gate.ADMIN_SIGNED)
PORTAL_ROUTES = _routes(read_gate.PORTAL)


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
    lane.execute("INSERT INTO players (id, steam_id, display_name) VALUES ($1, $2, 'rg-test-player') "
                 "ON CONFLICT DO NOTHING", uuid.uuid4(), PLAYER_ID)
    now = datetime.now(timezone.utc)
    lane.execute("DELETE FROM i18n_portal_sessions WHERE token = $1", PORTAL_TOKEN)
    lane.execute("INSERT INTO i18n_portal_sessions (token, steam_id, bound_ip, created_at, "
                 "expires_at, first_use_at) VALUES ($1, $2, 'testclient', $3, $4, $3)",
                 PORTAL_TOKEN, PLAYER_ID, now, now + timedelta(hours=1))
    lane.execute("DELETE FROM language_grants WHERE steam_id = $1", PLAYER_ID)
    lane.execute("INSERT INTO language_grants (steam_id, language_code, scope, granted_by_steam_id) "
                 "VALUES ($1, 'ru', 'translate', $2)", PLAYER_ID, K.ADMIN_ID)
    lane.execute("INSERT INTO runtime_settings (key, value) VALUES ('read_gate_mode', 'enforce') "
                 "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value")
    K.reset_gate()
    c = lane.client(monkeypatch)
    yield c
    lane.execute("DELETE FROM runtime_settings WHERE key = 'read_gate_mode'")
    K.reset_gate()


def _url(route, path_values):
    url = route.path
    for k, v in path_values.items():
        url = url.replace("{" + k + "}", v)
    return url


def _admin_param_names(route):
    names = {p.name for p in route.dependant.query_params}
    who = "admin_steam_id" if "admin_steam_id" in names else "steam_id"
    sig = "sig" if "sig" in names else "hmac_signature"
    if who == "steam_id":
        assert "steam_id" in names, route.path
    return who, sig


@pytest.mark.parametrize("route", ADMIN_ROUTES, ids=lambda r: r.path)
def test_admin_signed_class_requires_signature(client, monkeypatch, route):
    assert read_gate.route_class(route.path) == read_gate.C_ADMIN_SIGNED
    seen = []
    real = main._verify_admin_hmac

    def recorder(admin, action, target, signature):
        ok = real(admin, action, target, signature)
        seen.append((admin, action, target, ok))
        return ok
    monkeypatch.setattr(main, "_verify_admin_hmac", recorder)
    path_values, extra = FILL.get(route.path, ({}, {}))
    url = _url(route, path_values)
    who, sig = _admin_param_names(route)
    h = K.headers()

    # no credential at all, then the identity with no signature
    none = client.get(url, params=dict(extra), headers=h)
    assert none.status_code != 200 and none.status_code in (401, 403, 422), (route.path, none.status_code)
    unsigned = client.get(url, params={**extra, who: K.ADMIN_ID}, headers=h)
    # 422 where the handler declares the signature a required parameter
    assert unsigned.status_code in (401, 403, 422), (route.path, unsigned.status_code, unsigned.text[:200])

    # wrong signature: refused by the handler, which records its canonical
    seen.clear()
    wrong = client.get(url, params={**extra, who: K.ADMIN_ID, sig: "0" * 64}, headers=h)
    assert wrong.status_code == 403, (route.path, wrong.status_code, wrong.text[:200])
    asked = [s for s in seen if s[0] == K.ADMIN_ID]
    assert asked and asked[-1][3] is False, (route.path, seen)
    _, action, target, _ = asked[-1]

    # valid: the same canonical, signed with the configured secret
    seen.clear()
    valid = client.get(url, params={**extra, who: K.ADMIN_ID,
                                    sig: K.admin_sign(action, target)}, headers=h)
    assert any(s[3] is True for s in seen), (route.path, seen)
    expected = NON_AUTH_ANSWER.get(route.path, 200)
    assert valid.status_code == expected, (route.path, valid.status_code, valid.text[:300])
    # the gate itself never refused: no refused census row for this route;
    # the signed reads were counted as such (both parameter spellings)
    assert not K.census_rows(route=route.path, refused=True)
    assert K.census_rows(route=route.path, refused=False, **{"class": "admin_signature"})


@pytest.mark.parametrize("route", PORTAL_ROUTES, ids=lambda r: r.path)
def test_portal_class_requires_token(client, route):
    assert read_gate.route_class(route.path) == read_gate.C_PORTAL
    path_values, extra = FILL.get(route.path, ({}, {}))
    url = _url(route, path_values)
    h = K.headers()
    none = client.get(url, params=extra, headers=h)
    assert none.status_code == 401, (route.path, none.status_code, none.text[:200])
    wrong = client.get(url, params=extra, headers={**h, "X-Portal-Token": "rg-portal-not-issued"})
    assert wrong.status_code == 401, (route.path, wrong.status_code)
    valid = client.get(url, params=extra, headers={**h, "X-Portal-Token": PORTAL_TOKEN})
    assert valid.status_code == NON_AUTH_ANSWER.get(route.path, 200), (
        route.path, valid.status_code, valid.text[:300])
    assert not K.census_rows(route=route.path, refused=True)


def test_every_class_member_was_exercised():
    """The parametrisation is the class list: 22 + 7, none dropped."""
    assert len(ADMIN_ROUTES) == len(read_gate.ADMIN_SIGNED) == 22
    assert len(PORTAL_ROUTES) == len(read_gate.PORTAL) == 7
    assert set(NON_AUTH_ANSWER) <= set(read_gate.ADMIN_SIGNED) | set(read_gate.PORTAL)
