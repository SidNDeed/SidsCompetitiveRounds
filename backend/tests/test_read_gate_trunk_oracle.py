"""Verified reads, bar BV-A: with the stage off, every request the released
v1.40.3 client sends answers byte for byte as TRUNK answers it.

The oracle is trunk itself: the lane's merge base with `main` (override with
READ_GATE_ORACLE_BASE) is exported with `git archive` and its app is served
in a separate process beside the lane's, each on its own case schema built by
the same procedure and seeded with the same rows (read_gate_pg_harness.Lane).
The request list is the tag's own, derived and proved exhaustive by
read_gate_1403_requests. A third process runs TRUNK again on a third schema:
the control.

What made trunk's own answers vary run to run is FROZEN identically on all
three sides (round 2 finding M1): the app module's clock (the boards'
`last_updated`) and its `secrets.choice` (the link code), by the runner, at
one instant chosen per test run; and the opponent's last-seen anchor, seeded
at a fixed instant. So every answer the control reproduces is compared
exactly: status, every header, every body byte. The one value that still
moves is computed by the DATABASE clock, which no process can freeze: the
h2h card's `profile/last_seen_s`, the whole seconds from the seeded anchor to
the database's now(). It is the only declared noisy field (NOISE), and on
every side it must be an integer inside the window the request was in flight
(the runner's t0..t1 measured from the same anchor). A response that varies in
any undeclared path, or a declared value outside its window, is a problem.

No stage row exists in any schema, so the lane runs in `off`.
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone

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
# The opponent's last_seen and presence_seen_at, seeded at this fixed instant,
# so h2h's last_seen_s = floor(database now - ANCHOR).
ANCHOR = datetime(2026, 1, 1, tzinfo=timezone.utc)
SLACK_S = 2                         # same host clock; whole-second floor


def _seconds_since_anchor(value, result) -> bool:
    """profile/last_seen_s: an int (not a bool) inside the request's own
    flight window, measured from ANCHOR."""
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    lo = math.floor(result["t0"] - ANCHOR.timestamp()) - SLACK_S
    hi = math.ceil(result["t1"] - ANCHOR.timestamp()) + SLACK_S
    return lo <= value <= hi


# The ONLY fields whose value may differ between two runs of the same tree:
# (method, url prefix, JSON path, validator).
NOISE = [
    ("GET", "/api/v1/h2h/", "/profile/last_seen_s", _seconds_since_anchor),
]


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
        lane.execute("INSERT INTO players (id, steam_id, display_name, last_seen, presence_seen_at) "
                     "VALUES (gen_random_uuid(), $1, $2, $3, $3) ON CONFLICT DO NOTHING",
                     sid, name, ANCHOR)
    lane.execute("INSERT INTO steam_sessions (steam_id, token_hash, verified, issued_at, expires_at) "
                 "VALUES ($1, $2, true, now(), now() + interval '1 day')", ME, K.sha(SESSION))


def _run(tree, lane, req_path, out_path, freeze):
    env = dict(os.environ, API_SECRET_KEY=K.INTERNAL_KEY, PYTHONDONTWRITEBYTECODE="1")
    env.pop("SCR_REPLICA_MODE", None)
    proc = subprocess.run([sys.executable, RUNNER, tree, PG.DSN, lane.schema, req_path, out_path,
                           str(freeze)], capture_output=True, text=True, env=env, timeout=3600)
    assert proc.returncode == 0, (proc.stdout[-2000:], proc.stderr[-4000:])
    return json.load(open(out_path, encoding="utf-8"))


def _decode(r):
    raw = base64.b64decode(r["body"])
    try:
        return json.loads(raw)
    except Exception:
        return raw


def _answer(r):
    """What a client receives: status, every header, every body byte."""
    return r["status"], sorted(map(tuple, r["headers"])), r["body"]


def _declared(req):
    return [(path, check) for method, prefix, path, check in NOISE
            if req["method"] == method and req["url"].startswith(prefix)]


def _carries_declared(req, result) -> bool:
    """True when this answer holds a value NOISE declares for its request: it
    is then judged field by field even if two runs happened to agree."""
    doc = _decode(result)
    for path, _check in _declared(req):
        try:
            _at(doc, path)
            return True
        except (KeyError, IndexError, ValueError, TypeError):
            pass
    return False


def _at(doc, path):
    for part in path.strip("/").split("/"):
        if isinstance(doc, list):
            doc = doc[int(part)]
        elif isinstance(doc, dict):
            doc = doc[part]
        else:
            raise KeyError(path)
    return doc


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
    """Every disagreement of the lane with trunk, judged against the frozen
    replay. Returns (problems, counts).

    An answer the control reproduces exactly is DETERMINISTIC: the lane must
    equal it exactly. Otherwise every path where any two of the three bodies
    differ must be a path NOISE declares for this request, every declared
    value present on any side must pass its validator, the statuses must be
    equal, and the headers equal except a content-length that matches its own
    body. A trunk variation NOISE does not declare is itself a problem: the
    oracle then cannot compare that answer, and says so."""
    problems, counts = [], {"deterministic": 0, "varying": 0, "validated": 0}
    for req, b, l, c in zip(requests, base, lane, ctl):
        where = (req["site"], req["method"], req["url"], req["session"])
        if _answer(b) == _answer(c) and not _carries_declared(req, b):
            counts["deterministic"] += 1
            if _answer(l) != _answer(b):
                problems.append(where + ("differs from a deterministic trunk answer",
                                         b["status"], l["status"],
                                         sorted(set(map(tuple, l["headers"])) ^ set(map(tuple, b["headers"]))),
                                         sorted(_paths(_decode(b), _decode(l)))[:10]))
            continue
        counts["varying"] += 1
        declared = dict(_declared(req))
        db, dl, dc = (_decode(x) for x in (b, l, c))
        moved = _paths(db, dc) | _paths(db, dl)
        undeclared = sorted(p for p in moved if p not in declared)
        if undeclared:
            problems.append(where + ("varies in a path NOISE does not declare", undeclared[:10]))
        if not b["status"] == c["status"] == l["status"]:
            problems.append(where + ("status varies", b["status"], c["status"], l["status"]))

        def _hdrs(x):
            return sorted((k, v) for k, v in x["headers"] if k != "content-length")
        if not _hdrs(b) == _hdrs(c) == _hdrs(l):
            problems.append(where + ("headers vary",))
        for x in (b, l, c):
            for k, v in x["headers"]:
                if k == "content-length" and int(v) != len(base64.b64decode(x["body"])):
                    problems.append(where + ("content-length does not match its body",))
        for side, x, doc in (("base", b, db), ("lane", l, dl), ("control", c, dc)):
            for path, check in declared.items():
                try:
                    value = _at(doc, path)
                except (KeyError, IndexError, ValueError, TypeError):
                    if path in moved:
                        problems.append(where + ("declared path missing on " + side, path))
                    continue
                counts["validated"] += 1
                if not check(value, x):
                    problems.append(where + ("declared value fails its check on " + side, path, value))
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
    freeze = int(time.time())          # one instant for all three sides
    base = _run(trunk, base_lane, str(req_path), str(tmp_path / "base.json"), freeze)
    lane = _run(WORKTREE, lane_lane, str(req_path), str(tmp_path / "lane.json"), freeze)
    ctl = _run(trunk, ctl_lane, str(req_path), str(tmp_path / "ctl.json"), freeze)
    assert os.path.normcase(os.path.abspath(trunk)) in base["main"], base["main"]
    assert os.path.normcase(os.path.abspath(WORKTREE)) in lane["main"], lane["main"]
    assert len(base["results"]) == len(lane["results"]) == len(ctl["results"]) == len(requests)
    problems, counts = compare(requests, base["results"], lane["results"], ctl["results"])
    statuses = {}
    for r in base["results"]:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    with capsys.disabled():
        print(f"\n[bv-a oracle] base {sha[:8]} requests {len(requests)} "
              f"(calls {CALLS_AT_TAG}) frozen at {freeze} deterministic {counts['deterministic']} "
              f"varying {counts['varying']} validated {counts['validated']} "
              f"trunk statuses {sorted(statuses.items())} problems {len(problems)}")
        for q, b, c in zip(requests, base["results"], ctl["results"]):
            if _answer(b) != _answer(c):
                print("[bv-a varying on trunk]", q["method"], q["url"], "session" if q["session"] else "",
                      sorted(_paths(_decode(b), _decode(c)))[:6])
        for p in problems[:40]:
            print("[bv-a problem]", p)
    assert not problems
    # Every declared noisy value was seen and validated on all three sides,
    # and nothing else varied: the freeze took the boards and the link code
    # out of the varying set.
    assert counts["varying"] >= 1 and counts["validated"] == 3 * counts["varying"], counts
    # The freeze reached every side: each board's last_updated IS the instant.
    boards = [i for i, q in enumerate(requests) if q["method"] == "GET"
              and q["url"].split("?")[0] in ("/api/v1/team/leaderboard", "/api/v1/ovt/leaderboard",
                                             "/api/v1/ffa/leaderboard")
              and base["results"][i]["status"] == 200]
    assert len(boards) >= 6, boards
    for i in boards:
        for side in (base, lane, ctl):
            stamp = _decode(side["results"][i])["last_updated"]
            assert datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() == freeze, stamp
    # the replay reached the app: the version check and the boot probe answered 200
    mv = [r for q, r in zip(requests, lane["results"]) if q["url"] == "/api/v1/mod-version"]
    assert mv and all(r["status"] == 200 for r in mv)
    for r in mv:
        body = _decode(r)
        assert "read_gate" not in body and "read_gate_open" not in body, body


def _r(body: bytes, t0=0.0, t1=0.0, status=200):
    return {"status": status, "headers": [["content-length", str(len(body))],
                                          ["content-type", "application/json"]],
            "body": base64.b64encode(body).decode(), "t0": t0, "t1": t1}


def test_compare_control():
    """The comparator reports a one-byte change to a deterministic answer, a
    variation in any path NOISE does not declare (on trunk's own runs too),
    and a declared value outside its check; it accepts a declared value
    inside it."""
    req = [{"site": "s", "method": "GET", "url": "/u", "session": False}]
    one, t6 = _r(b'{"a": 1, "t": 5}'), _r(b'{"a": 1, "t": 6}')
    # deterministic: base == ctl; a lane change is reported
    assert compare(req, [one], [t6], [one])[0]
    assert not compare(req, [one], [one], [one])[0]
    # trunk itself varies in an undeclared path: reported, even if the lane agrees
    assert compare(req, [one], [one], [t6])[0]
    # the declared h2h field: valid inside the request's window, invalid outside
    h2h = [{"site": "s", "method": "GET", "url": "/api/v1/h2h/1/2", "session": True}]
    at = ANCHOR.timestamp() + 1000.0

    def card(v, t=at, extra=b""):
        return _r(b'{"line": 3, "profile": {"last_seen_s": ' + str(v).encode() + b'}' + extra + b'}',
                  t0=t, t1=t + 0.5)
    base, ctl = card(1000), card(1060, t=at + 60)
    assert not compare(h2h, [base], [card(1030, t=at + 30)], [ctl])[0]
    assert compare(h2h, [base], [card(1090, t=at + 30)], [ctl])[0]          # outside its window
    assert compare(h2h, [base], [card('"1030"', t=at + 30)], [ctl])[0]      # not an int
    assert compare(h2h, [base], [card("true", t=at + 30)], [ctl])[0]        # a bool is not a count
    # the declared field equal on base and control is STILL checked
    assert compare(h2h, [card(1000)], [card(5, t=at)], [card(1000)])[0]
    # a declared field never excuses another path
    other = _r(b'{"line": 4, "profile": {"last_seen_s": 1030}}', t0=at + 30, t1=at + 30.5)
    assert compare(h2h, [base], [other], [ctl])[0]
    # and a content-length that does not match its body is reported
    bad_len = dict(card(1030, t=at + 30), headers=[["content-length", "1"],
                                                   ["content-type", "application/json"]])
    assert compare(h2h, [base], [bad_len], [ctl])[0]
