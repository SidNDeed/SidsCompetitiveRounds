"""Verified reads, bar BV-A: with the stage off, every request the released
v1.40.3 client sends answers byte for byte as TRUNK answers it.

The oracle is trunk itself: the lane's merge base with `main` (override with
READ_GATE_ORACLE_BASE) is exported with `git archive` and its app is served
in a separate process beside the lane's, each on its own case schema built by
the same procedure and seeded with the same rows (read_gate_pg_harness.Lane).
The request list is the tag's own, derived and proved exhaustive by
read_gate_1403_requests. A third process runs TRUNK again on a third schema:
the control. A response the control reproduces exactly is DETERMINISTIC, and
the lane must reproduce it exactly (status, every header, every body byte).
A response the control does not reproduce varies run to run on trunk itself;
for those the lane must vary in exactly the same JSON paths and nowhere else.

No stage row exists in any schema, so the lane runs in `off`.
"""
from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys
import tarfile

import pytest

import read_gate_1403_requests as Q
import read_gate_pg_harness as PG
import read_gate_testkit as K

HERE = os.path.dirname(os.path.abspath(__file__))
WORKTREE = os.path.normpath(os.path.join(HERE, "..", ".."))
RUNNER = os.path.join(HERE, "read_gate_oracle_runner.py")
ME = "76561190000004371"           # synthetic
ME2 = "76561190000004372"          # synthetic
UUID = "00000000-0000-4000-8000-000000000001"
SESSION = "vr-oracle-session-token-0001"
CALLS_AT_TAG = 255                  # the tag never changes


# -- exhaustiveness ----------------------------------------------------------

def test_1403_request_list_is_exhaustive():
    calls, residue = Q.extract(WORKTREE)
    assert residue["unresolved_sites"] == [], residue["unresolved_sites"]
    assert residue["orphan_lines"] == [], residue["orphan_lines"]
    assert residue["unmatched_non_api"] == [], residue["unmatched_non_api"]
    assert residue["constructors"] == {"UnityWebRequest.Get(": 7, "UnityWebRequest.Delete(": 1,
                                       "newUnityWebRequest(": 3}, residue["constructors"]
    assert len(calls) == CALLS_AT_TAG, len(calls)
    for c in calls:
        assert c["method"] in ("GET", "POST", "PUT", "DELETE"), c
        for url in Q.concrete_urls(c["expr"], ME, ME2, UUID):
            assert url.startswith("/api/v1/") and "{" not in url and " " not in url, (c, url)


def test_exhaustiveness_controls():
    """(a) an /api/v1 literal no request consumes, and (b) a request whose URL
    resolves to nothing, are each reported."""
    src = Q.tag_sources(WORKTREE)
    lines = list(src["plugin/ApiClient.cs"])
    lines.append("        private static void ZzOrphan() { string zz = $\"{baseUrl}/api/v1/zz-orphan\"; }")
    lines.append("        private static void ZzUnresolved() { Plugin.Instance.StartCoroutine("
                 "GetRequest(zzNowhere, (ok, r) => { })); }")
    _, residue = Q.extract(WORKTREE, dict(src, **{"plugin/ApiClient.cs": lines}))
    assert any("zz-orphan" in o[2] for o in residue["orphan_lines"]), residue["orphan_lines"]
    assert any("zzNowhere" in u[2] for u in residue["unresolved_sites"]), residue["unresolved_sites"]


# -- the oracle --------------------------------------------------------------

def _base_sha() -> str:
    pinned = os.environ.get("READ_GATE_ORACLE_BASE", "").strip()
    if pinned:
        return pinned
    return subprocess.run(["git", "-C", WORKTREE, "merge-base", "HEAD", "main"], capture_output=True,
                          text=True, check=True).stdout.strip()


def _export(sha: str, dest: str) -> str:
    blob = subprocess.run(["git", "-C", WORKTREE, "archive", "--format=tar", sha, "backend/api"],
                          capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        tar.extractall(dest)
    return dest


def _seed(lane):
    for sid, name in ((ME, "vr-oracle-a"), (ME2, "vr-oracle-b")):
        lane.execute("INSERT INTO players (id, steam_id, display_name) "
                     "VALUES (gen_random_uuid(), $1, $2) ON CONFLICT DO NOTHING", sid, name)
    lane.execute("INSERT INTO steam_sessions (steam_id, token_hash, verified, issued_at, expires_at) "
                 "VALUES ($1, $2, true, now(), now() + interval '1 day')", ME, K.sha(SESSION))


def _run(tree, lane, req_path, out_path):
    env = dict(os.environ, API_SECRET_KEY=K.INTERNAL_KEY, PYTHONDONTWRITEBYTECODE="1")
    env.pop("SCR_REPLICA_MODE", None)
    proc = subprocess.run([sys.executable, RUNNER, tree, PG.DSN, lane.schema, req_path, out_path],
                          capture_output=True, text=True, env=env, timeout=3600)
    assert proc.returncode == 0, (proc.stdout[-2000:], proc.stderr[-4000:])
    return json.load(open(out_path, encoding="utf-8"))


def _decode(r):
    raw = base64.b64decode(r["body"])
    try:
        return json.loads(raw)
    except Exception:
        return raw


def _paths(a, b, prefix=""):
    """JSON paths where a and b differ."""
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        out = set()
        for k in a:
            out |= _paths(a[k], b[k], prefix + "/" + str(k))
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = set()
        for i, (x, y) in enumerate(zip(a, b)):
            out |= _paths(x, y, prefix + "/" + str(i))
        return out
    return set() if a == b else {prefix or "/"}


def compare(requests, base, lane, ctl):
    """Every disagreement of the lane with trunk that trunk's own control run
    does not show. Returns (problems, counts)."""
    problems, counts = [], {"deterministic": 0, "varying": 0}
    for req, b, l, c in zip(requests, base, lane, ctl):
        if b == c:
            counts["deterministic"] += 1
            if l != b:
                problems.append((req["site"], req["method"], req["url"], req["session"],
                                 "differs from a deterministic trunk answer",
                                 b["status"], l["status"],
                                 sorted(set(map(tuple, l["headers"])) ^ set(map(tuple, b["headers"]))),
                                 sorted(_paths(_decode(b), _decode(l)))[:10]))
            continue
        counts["varying"] += 1
        hb, hl, hc = ({tuple(h) for h in x["headers"]} for x in (b, l, c))
        same_shape = (b["status"] == c["status"] == l["status"]
                      and (hb == hl or {k for k, _ in hb ^ hl} <= {k for k, _ in hb ^ hc}))
        noise = _paths(_decode(b), _decode(c))
        lane_diff = _paths(_decode(b), _decode(l))
        if not same_shape or not lane_diff <= noise:
            problems.append((req["site"], req["method"], req["url"], req["session"],
                             "varies beyond trunk's own variation", sorted(lane_diff - noise)[:10]))
    return problems, counts


@pytest.fixture(scope="module")
def three_lanes():
    PG.require_live_pg()
    lanes = []
    try:
        for prefix in ("rg_oracle_base", "rg_oracle_lane", "rg_oracle_ctl"):
            lane = PG.Lane(prefix).open()
            lanes.append(lane)
            _seed(lane)
        yield lanes
    finally:
        for lane in lanes:
            lane.close()


def test_1403_replay_matches_trunk_oracle(three_lanes, tmp_path, capsys):
    base_lane, lane_lane, ctl_lane = three_lanes
    sha = _base_sha()
    trunk = _export(sha, str(tmp_path / "trunk"))
    requests = Q.request_list(WORKTREE, ME, ME2, UUID, SESSION)
    req_path = tmp_path / "requests.json"
    req_path.write_text(json.dumps(requests), encoding="utf-8")
    base = _run(trunk, base_lane, str(req_path), str(tmp_path / "base.json"))
    lane = _run(WORKTREE, lane_lane, str(req_path), str(tmp_path / "lane.json"))
    ctl = _run(trunk, ctl_lane, str(req_path), str(tmp_path / "ctl.json"))
    assert os.path.normcase(os.path.abspath(trunk)) in base["main"], base["main"]
    assert os.path.normcase(os.path.abspath(WORKTREE)) in lane["main"], lane["main"]
    assert len(base["results"]) == len(lane["results"]) == len(ctl["results"]) == len(requests)
    problems, counts = compare(requests, base["results"], lane["results"], ctl["results"])
    statuses = {}
    for r in base["results"]:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    with capsys.disabled():
        print(f"\n[bv-a oracle] base {sha[:8]} requests {len(requests)} "
              f"(calls {CALLS_AT_TAG}) deterministic {counts['deterministic']} "
              f"varying {counts['varying']} trunk statuses {sorted(statuses.items())} "
              f"problems {len(problems)}")
        for q, b, c in zip(requests, base["results"], ctl["results"]):
            if b != c:
                print("[bv-a varying on trunk]", q["method"], q["url"], "session" if q["session"] else "",
                      sorted(_paths(_decode(b), _decode(c)))[:6])
        for p in problems[:40]:
            print("[bv-a problem]", p)
    assert not problems
    # the replay reached the app: the version check and the boot probe answered 200
    mv = [r for q, r in zip(requests, lane["results"]) if q["url"] == "/api/v1/mod-version"]
    assert mv and all(r["status"] == 200 for r in mv)
    for r in mv:
        body = _decode(r)
        assert "read_gate" not in body and "read_gate_open" not in body, body


def test_compare_control():
    """The comparator reports a one-byte change to a deterministic answer and
    a change outside trunk's own varying paths; it accepts the varying path."""
    req = [{"site": "s", "method": "GET", "url": "/u", "session": False}] * 2
    one = {"status": 200, "headers": [["content-type", "application/json"]],
           "body": base64.b64encode(b'{"a": 1, "t": 5}').decode()}
    t6 = dict(one, body=base64.b64encode(b'{"a": 1, "t": 6}').decode())
    t7 = dict(one, body=base64.b64encode(b'{"a": 1, "t": 7}').decode())
    a2 = dict(one, body=base64.b64encode(b'{"a": 2, "t": 7}').decode())
    # deterministic: base == ctl; a lane change is reported
    assert compare(req[:1], [one], [t6], [one])[0]
    assert not compare(req[:1], [one], [one], [one])[0]
    # varying in /t on trunk: the lane may vary in /t, never in /a
    assert not compare(req[:1], [one], [t7], [t6])[0]
    assert compare(req[:1], [one], [a2], [t6])[0]
