"""Verified reads, requirements 17 and 20: the seat caller and the census
ledger (tools/read_gate_tools.py).

The seat caller's request builder takes a transport; here the transport is
the real app through a TestClient, and no request carries X-Mod-Version, so
the control paths' place in the version bypass is what lets them through.
The ledger tests use synthetic pull records.
"""
from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "tools")))

import read_gate_testkit as K          # noqa: E402
import main                            # noqa: E402
import read_gate                       # noqa: E402
import read_gate_tools as T            # noqa: E402

FLOOR = "1.41.0"


class ClientTransport:
    """AdminCaller's transport over a TestClient. Records every request's
    headers so the test can assert none carried a mod version."""

    def __init__(self, client):
        self.c, self.sent = client, []

    def __call__(self, method, path, params=None, body=None, headers=None):
        self.sent.append((method, path, dict(headers or {})))
        r = self.c.request(method, path, params=params, json=body, headers=headers or {})
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, None


@pytest.fixture
def seat(monkeypatch):
    with K.gate_env(monkeypatch, mode="log") as (stub, clock):
        monkeypatch.setattr(main, "ADMIN_HMAC_SECRET", K.ADMIN_SECRET)
        rdb = K.RequestDB(stub)

        async def _db():
            yield rdb
        monkeypatch.setitem(main.app.dependency_overrides, main.get_db, _db)
        monkeypatch.setattr(main, "_RL_BUCKETS",
                            main._RL_BUCKETS.__class__(main._RL_BUCKETS.default_factory))
        client = TestClient(main.app, raise_server_exceptions=False)
        transport = ClientTransport(client)
        yield T.AdminCaller(transport, K.ADMIN_ID, K.ADMIN_SECRET), transport, client, stub, rdb


def test_seat_caller_flip_and_rollback(seat, monkeypatch):
    caller, transport, client, stub, rdb = seat
    monkeypatch.setattr(read_gate, "READ_GATE_CLIENT_MIN", FLOOR)
    monkeypatch.setattr(main, "MIN_MOD_VERSION_EFFECTIVE", FLOOR)
    monkeypatch.setattr(read_gate, "SOCKET_READ_GATE_BUILT", True)
    path = "/api/v1/scratch/seat-public"
    h = K.headers(version=FLOOR)
    with K.scratch_route(main.app, path):
        for mode, expect in (("log", 200), ("enforce", 401), ("log", 200)):
            status, body = caller.set_mode(mode)
            assert status == 200, (mode, status, body)
            assert body["mode"] == mode and stub.mode_row == mode
            r = client.get(path, headers=h)
            assert r.status_code == expect, (mode, r.status_code)
    assert transport.sent and all("X-Mod-Version" not in hd for _, _, hd in transport.sent)


def test_seat_caller_without_bypass_would_426(seat, monkeypatch):
    """Negative control: with the control path taken out of the version
    bypass, the same caller is refused before the handler."""
    caller, _, _, _, _ = seat
    monkeypatch.setattr(main, "_VERSION_GATE_BYPASS",
                        frozenset(main._VERSION_GATE_BYPASS - {"/api/v1/admin/read-gate/mode"}))
    status, _ = caller.set_mode("log")
    assert status == 426


def test_seat_caller_census(seat):
    caller, _, client, _, _ = seat
    status, body = caller.census()
    assert status == 200 and body["boot_id"] == read_gate.BOOT_ID


# -- ledger -------------------------------------------------------------------

P = read_gate.PROBE_PATH
KEY = f"{P}|GET|mod_no_session||True|True"
T0 = 1_790_000_000.0


def _rec(at, boot="b1", since=T0 - 600, n=0, node="primary", ok=True):
    if not ok:
        return {"node": None, "box": node, "at": at, "ok": False, "boot_id": None,
                "since": None, "counts": {}, "error": "status 502"}
    return {"node": node, "box": node, "at": at, "ok": True, "boot_id": boot,
            "since": since, "counts": {KEY: n} if n else {}, "error": ""}


def test_ledger_duplicate_pull_zero_delta(tmp_path):
    path = str(tmp_path / "ledger.jsonl")
    for r in (_rec(T0, n=5), _rec(T0 + 60, n=5), _rec(T0 + 120, n=8)):
        T.append(path, r)
    d = T.deltas(T.load(path))
    assert [x[3] for x in d] == [{KEY: 5}, {}, {KEY: 3}]


def test_ledger_restart_new_series_gap_recorded():
    recs = [_rec(T0, n=5), _rec(T0 + 600, n=9),
            _rec(T0 + 1500, boot="b2", since=T0 + 1200, n=2)]
    d = T.deltas(recs)
    assert [(x[1], x[3]) for x in d] == [("b1", {KEY: 5}), ("b1", {KEY: 4}), ("b2", {KEY: 2})]
    g = T.gaps(recs)
    unrecorded = [x for x in g if x.kind == "unrecorded_boot"]
    assert len(unrecorded) == 1
    assert (unrecorded[0].start, unrecorded[0].end) == (T0 + 600, T0 + 1200)
    # a failed pull is not a successful pull: it does not close a gap
    g2 = T.gaps(recs[:2] + [_rec(T0 + 900, ok=False)] + recs[2:])
    assert [(x.start, x.end) for x in g2 if x.kind == "between_pulls"] == \
        [(T0, T0 + 600), (T0 + 600, T0 + 1500)]


def _hourly(start, end, step=900, **kw):
    out, t = [], start
    while t <= end:
        out.append(_rec(t, **kw))
        t += step
    return out


def _both(start, end, step=900, **kw):
    """Steady successful pulls of BOTH boxes, each answering as itself with
    its own boot id."""
    return (_hourly(start, end, step, node="primary", boot="p1", **kw)
            + _hourly(start, end, step, node="standby", boot="s1", **kw))


def test_coverage_fails_on_three_hour_gap():
    now = T0 + 14 * 86400
    start = now - 14 * 86400
    steady = _both(start, now)
    ok = T.coverage(steady, 14, now)
    for box in ("primary", "standby"):
        assert ok[box]["ok"] and ok[box]["longest_gap"] <= 900, ok
        assert ok[box]["covered"] == 1.0
    hole_a, hole_b = start + 5 * 86400, start + 5 * 86400 + 3 * 3600
    holed = [r for r in steady if not (r["box"] == "primary" and hole_a < r["at"] < hole_b)]
    bad = T.coverage(holed, 14, now)
    assert not bad["primary"]["ok"] and bad["standby"]["ok"]
    assert bad["primary"]["longest_gap"] >= 3 * 3600 - 900
    assert bad["primary"]["covered"] < 1.0


def test_coverage_cli_exit_code(tmp_path, capsys):
    """The CLI's verdict is its exit code."""
    sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "tools")))
    now = T0 + 86400
    path = str(tmp_path / "ledger.jsonl")
    for r in _both(now - 86400, now):
        T.append(path, r)
    assert T.coverage_cli(path, 1, now) == 0
    path2 = str(tmp_path / "ledger2.jsonl")
    for r in _both(now - 86400, now):
        if not (now - 50000 < r["at"] < now - 40000):
            T.append(path2, r)
    assert T.coverage_cli(path2, 1, now) == 1
    out = capsys.readouterr().out
    assert "primary" in out and "standby" in out and "longest gap" in out


def test_coverage_cli_primary_only_fails(tmp_path, capsys):
    """Fourteen days of successful primary pulls and only FAILED standby pulls:
    the standby has no successful pull, so the verdict is exit 1."""
    now = T0 + 14 * 86400
    path = str(tmp_path / "ledger.jsonl")
    for r in _hourly(now - 14 * 86400, now, node="primary", boot="p1"):
        T.append(path, r)
    for r in _hourly(now - 14 * 86400, now, node="standby", ok=False):
        T.append(path, r)
    v = T.coverage(T.load(path), 14, now)
    assert v["primary"]["ok"] and not v["standby"]["ok"], v
    assert "no successful pull" in v["standby"]["why"]
    assert T.coverage_cli(path, 14, now) == 1
    assert "standby: 0 pulls" in capsys.readouterr().out
    # and an empty ledger reports both boxes and fails
    empty = str(tmp_path / "empty.jsonl")
    assert T.coverage_cli(empty, 14, now) == 1


def test_coverage_cli_late_first_pull_fails(tmp_path):
    """Both boxes' first success three hours into the window: the clipped
    leading interval is the longest gap, so the verdict is exit 1; the same
    for a trailing interval (last success three hours before now)."""
    now = T0 + 14 * 86400
    start = now - 14 * 86400
    late = str(tmp_path / "late.jsonl")
    for r in _both(start + 3 * 3600, now):
        T.append(late, r)
    v = T.coverage(T.load(late), 14, now)
    for box in ("primary", "standby"):
        assert not v[box]["ok"] and v[box]["longest_gap"] == 3 * 3600, v
        assert v[box]["covered"] < 1.0
    assert T.coverage_cli(late, 14, now) == 1
    stale = str(tmp_path / "stale.jsonl")
    for r in _both(start, now - 3 * 3600):
        T.append(stale, r)
    v = T.coverage(T.load(stale), 14, now)
    assert not v["primary"]["ok"] and v["primary"]["longest_gap"] == 3 * 3600, v
    assert T.coverage_cli(stale, 14, now) == 1
    # a pull before the window anchors it: no leading interval
    anchored = _both(start - 600, now)
    assert all(x["ok"] for x in T.coverage(anchored, 14, now).values())


def test_coverage_requires_distinct_identities():
    """A pull of the standby address that answered as the primary does not
    count for the standby; one boot id answering for both boxes fails both."""
    now = T0 + 86400
    start = now - 86400
    crossed = (_hourly(start, now, node="primary", boot="p1")
               + [dict(r, box="standby") for r in _hourly(start, now, node="primary", boot="p9")])
    v = T.coverage(crossed, 1, now)
    assert v["primary"]["ok"] and not v["standby"]["ok"], v
    assert "answered as node ['primary']" in v["standby"]["why"]
    # and those pulls cover nothing for the standby: none is counted
    assert v["standby"]["pulls"] == 0 and v["standby"]["covered"] == 0.0, v["standby"]
    same = (_hourly(start, now, node="primary", boot="one")
            + _hourly(start, now, node="standby", boot="one"))
    v = T.coverage(same, 1, now)
    assert not v["primary"]["ok"] and not v["standby"]["ok"], v
    assert "one process" in v["standby"]["why"]


def test_canary_counts_exactly_n(seat):
    caller, transport, _, _, _ = seat
    verdict = T.canary(caller, transport, 20, headers=K.headers())
    assert verdict["ok"] and verdict["delta"] == 20 and verdict["statuses"] == [401], verdict
    # negative control: a transport that drops every fifth probe
    count = {"n": 0}

    def lossy(method, path, params=None, body=None, headers=None):
        count["n"] += 1
        if path == read_gate.PROBE_PATH and count["n"] % 5 == 0:
            return 599, None
        return transport(method, path, params=params, body=body, headers=headers)
    lossy_caller = T.AdminCaller(transport, K.ADMIN_ID, K.ADMIN_SECRET)
    verdict = T.canary(lossy_caller, lossy, 20, headers=K.headers())
    assert not verdict["ok"] and verdict["delta"] == 16, verdict
