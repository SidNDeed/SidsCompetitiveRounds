"""Verified reads, requirement 31 (bar 13): in stages off and log nothing
changes for the v1.40.3 client.

The GETs v1.40.3 sends before a session exists, from
`git show v1.40.3:plugin/ApiClient.cs` and `MailClient.cs` (the grep is in
BUILD-NOTES, and `test_replay_list_is_the_tags_own` re-checks every URL
fragment against the tag). Each is replayed with the 1.40.3 headers (no X-Locale, which the tag never
sends) and no session, in off and in log, and its status, body and EVERY header must equal
the same request with `read_gate` replaced by a no-op through
`app.dependency_overrides`.

The pair runs override-first. A route that writes (presence/ping) is first
called once so both halves of the pair start from the same state.
"""
from __future__ import annotations

import subprocess
import uuid

import pytest

import read_gate_pg_harness as PG
import read_gate_testkit as K
import main
import read_gate

ME = "76561190000004371"     # synthetic
WORKTREE = PG.HERE + "/../.."

# (URL as the 1.40.3 client builds it, the fragment the tag's source carries,
#  the source file)
REPLAY = (
    ("/api/v1/mod-version", "/api/v1/mod-version", "ApiClient.cs"),
    ("/api/v1/alerts/active", "/api/v1/alerts/active", "ApiClient.cs"),
    ("/api/v1/i18n/pack/ru", "/api/v1/i18n/pack/{loc}", "ApiClient.cs"),
    ("/api/v1/release-notes/en", "/api/v1/release-notes/{Escape(locale)}", "ApiClient.cs"),
    ("/api/v1/release-notes/full/en", "/api/v1/release-notes/full/{Escape(want)}", "ApiClient.cs"),
    ("/api/v1/releases/recent?limit=3", "/api/v1/releases/recent?limit=3", "ApiClient.cs"),
    ("/api/v1/players/" + ME, "/api/v1/players/{steamId}\"", "ApiClient.cs"),
    ("/api/v1/players/" + ME + "/matches?limit=20", "/api/v1/players/{steamId}/matches?limit=", "ApiClient.cs"),
    ("/api/v1/players/blocks/" + ME, "/api/v1/players/blocks/{steamId}", "ApiClient.cs"),
    ("/api/v1/admin/check-status?steam_id=" + ME, "/api/v1/admin/check-status?steam_id=", "ApiClient.cs"),
    ("/api/v1/shop/items", "/api/v1/shop/items", "ApiClient.cs"),
    ("/api/v1/presence/ping?steam_id=" + ME, "/api/v1/presence/ping", "ApiClient.cs"),
    ("/api/v1/mail/status", "/api/v1/mail/status", "MailClient.cs"),
)
WRITERS = {"/api/v1/presence/ping?steam_id=" + ME}
# The headers the tag's transport stamps (read_gate_1403_requests): no X-Locale.
HEADERS_1403 = {"X-Mod-Version": "1.40.3",
                "User-Agent": "UnityPlayer/2019.4.40f1 (UnityWebRequest/1.0, libcurl/7.80.0-DEV)"}


def _noop_gate():
    return None


@pytest.fixture(scope="module")
def lane():
    PG.require_live_pg()
    return PG.shared_lane()


@pytest.fixture
def client(lane, monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", K.INTERNAL_KEY)
    lane.execute("INSERT INTO players (id, steam_id, display_name) VALUES ($1, $2, 'rg-replay') "
                 "ON CONFLICT DO NOTHING", uuid.uuid4(), ME)
    K.reset_gate()
    yield lane.client(monkeypatch)
    lane.execute("DELETE FROM runtime_settings WHERE key = 'read_gate_mode'")
    K.reset_gate()


def _stage(lane, mode):
    if mode is None:
        lane.execute("DELETE FROM runtime_settings WHERE key = 'read_gate_mode'")
    else:
        lane.execute("INSERT INTO runtime_settings (key, value) VALUES ('read_gate_mode', $1) "
                     "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", mode)
    K.reset_gate()


def _once(client, url):
    main._RL_BUCKETS.clear()
    r = client.get(url, headers=HEADERS_1403)
    return r.status_code, r.content, sorted(r.headers.items())


def _pair(client, monkeypatch, url):
    if url in WRITERS:
        _once(client, url)
    with monkeypatch.context() as m:
        m.setitem(main.app.dependency_overrides, read_gate.read_gate, _noop_gate)
        baseline = _once(client, url)
    gated = _once(client, url)
    return baseline, gated


def test_replay_list_is_the_tags_own():
    for _, fragment, source in REPLAY:
        text = subprocess.run(["git", "-C", WORKTREE, "show", "v1.40.3:plugin/" + source],
                              capture_output=True, text=True, encoding="utf-8", check=True).stdout
        assert fragment in text, (fragment, source)


@pytest.mark.parametrize("mode", [None, "off", "log"], ids=["no-row", "off", "log"])
def test_1403_presession_replay(client, lane, monkeypatch, mode):
    _stage(lane, mode)
    differ, statuses = [], {}
    for url, _, _ in REPLAY:
        baseline, gated = _pair(client, monkeypatch, url)
        statuses[url] = baseline[0]
        if baseline != gated:
            differ.append((url, baseline[0], gated[0],
                           [h for h in gated[2] if h not in baseline[2]],
                           baseline[1][:120], gated[1][:120]))
    assert not differ, differ
    # the replay reached the handlers: no 426, no 5xx, and the reads that
    # need no session answered 200
    print("replay statuses", mode, statuses)
    assert all(s != 426 and s < 500 for s in statuses.values()), statuses
    assert statuses["/api/v1/mod-version"] == 200 and statuses["/api/v1/players/" + ME] == 200
    # the log stage counted them; off counted nothing
    counted = sum(r["count"] for r in K.census_rows())
    assert (counted > 0) == (mode == "log"), counted
