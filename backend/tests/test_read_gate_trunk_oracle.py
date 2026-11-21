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

import ast
import base64
import inspect
import io
import json
import math
import os
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timedelta, timezone

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
BUILD_SLACK_S = 60                  # a build-time stamp is one the database clock took after the
                                    # lane's open() began, minus this much clock drift
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()   # to_char(.., 'Mon') is English
PIN_AT = ANCHOR + timedelta(hours=12)    # the build-time shop stamps land here (see _pin_build_clock)


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

# Lists whose order among ADJACENT rows sharing a key the trunk never fixed:
# (method, url path, JSON path of the list, run key, tiebreak). Every side's
# list has each run of adjacent rows with an equal run key put in tiebreak
# order before anything is compared; nothing else in the answer moves.
#
# /shop/items ordered by price alone until the lane that added `, id`
# (lesson 1062's file, shop-order-1410): PostgreSQL answers equal prices in
# whatever order its sort leaves the heap's rows. The build alone lays the
# heap out the same every time; _pin_build_clock's UPDATEs then write each
# pinned row's new version wherever its page has room, which depends on what
# pruning had reclaimed, so trunk's own base and control disagreed at
# /items/1 and /items/10 (/items/12 and /13 in another run) from the day the
# pin landed. From that lane on, trunk answers each pool's ties in id order,
# so settling changes nothing on a side unless a joined run (below) is out of
# id order across the pool boundary; the current fixture has none. Only
# ADJACENT runs are settled, and EVERY adjacent run is: the owned achievement
# rows the route appends after the catalogue are settled like the catalogue's,
# and a run is not split where the catalogue ends, because no field of an
# answered row names its pool (the rows carry id, sku, kind, name, price,
# owned, ...; catalogue rows can be owned too). So appended rows whose price
# equals the last catalogue price join the catalogue's run and are sorted with
# it ([5, 9] + [7] at one price becomes [5, 7, 9]); appended rows at another
# price are sorted among themselves and keep their place between the price
# runs around them; a row moved to another price is still a difference.
TIES = [
    ("GET", "/api/v1/shop/items", "/items", "price", "id"),
]

# Answers a landing changes ON PURPOSE, where trunk's answer is deterministic:
# (method, the URL's exact path with the query left out, JSON path, trunk's
# value, the lane's value, reason). The values are the bytes on the wire,
# written out here; the oracle never imports the product's own table. compare()
# accepts a lane answer that differs from trunk's only when the statuses are
# equal, the headers are equal but for a content-length that matches each
# side's own body, the paths that differ are exactly the paths declared here for
# that request, and each holds the row's trunk value on trunk and the row's lane
# value on the lane. intended_closing() names every row that describes nothing:
# each row is USED (trunk old, lane new: before the landing) or SETTLED (both
# hold the lane's value: trunk caught up after the landing). A SETTLED row may
# be removed.
INTENDED = [
    ("GET", "/api/v1/admin/quarantine", "/detail",
     "Not an admin",
     "This action needs an admin account and a valid admin signature; nothing was changed.",
     "The held-report apply lane answers every refusal of the quarantine surface with one of its "
     "own plain sentences: admin_list_quarantine catches _require_admin's refusal and answers the "
     "same status with the admin sentence. The lane's test that holds the list route's refusal: "
     "test_qapply_pg.py::test_m2_malformed_input_to_each_route_answers_its_table_sentence "
     "(403 with qapply_texts.tsv's admin sentence). The released client (v1.40.3 and v1.41.0, "
     "ApiClient.FetchAdminQuarantine) puts a refused answer's body into AdminQuarantineError and "
     "shows it; no client code at either tag matches the old text."),
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


def _pin_build_clock(lane, built_after):
    """Move every shop item stamp the build took from the database clock onto
    one fixed day, keeping the stamps distinct and in their build order.

    Migration 148's trigger stamps released_at = NOW() on each item a release
    migration flips catalog-ready, and created_at defaults to the same clock;
    /shop/items answers released_iso and /shop/newest answers added and
    date_iso as DATES of those stamps. Two sides built on different UTC days
    therefore answer different dates (lesson 1062: red on every run straddling
    00:00Z), and a same-day run cannot see it. One shift per lane puts the
    earliest build stamp at PIN_AT and the rest minutes after it, so every
    side answers the same dates whatever day built it, and /shop/newest keeps
    its order (it sorts by the stamp; a collapse to one instant would leave the
    order among ties to the heap). PIN_AT is noon UTC on ANCHOR's day: Python
    dates it in UTC and to_char dates it in the session's zone (Pacific on
    this seat), and noon is the same calendar day in every zone within eleven
    hours of UTC."""
    since = built_after - timedelta(seconds=BUILD_SLACK_S)
    window = "released_at >= $1 OR created_at >= $1"
    before = lane.fetch("SELECT id, released_at, created_at FROM shop_items WHERE " + window + " ORDER BY id", since)
    # The negative control: the build DOES stamp the clock. If this ever reads
    # empty the trigger or the default changed and this pin is dead code to remove.
    assert before, "no shop item carries a build-time stamp; the pin is dead"
    stamps = [v for r in before for v in (r["released_at"], r["created_at"]) if v is not None and v >= since]
    assert max(stamps) - min(stamps) < timedelta(hours=1), (min(stamps), max(stamps))   # one build, one day
    shift = PIN_AT - min(stamps)
    expect = {r["id"]: tuple(v + shift if v is not None and v >= since else v
                             for v in (r["released_at"], r["created_at"])) for r in before}
    # The target instants are computed here and written as values: `stamp + $2`
    # with an interval that carries days is calendar arithmetic in the
    # session's time zone, and the first run of this pin came back one hour off
    # across the DST change between October and January (local-refined-run3).
    for sid, (released_at, created_at) in expect.items():
        lane.execute("UPDATE shop_items SET released_at = $2, created_at = $3 WHERE id = $1",
                     sid, released_at, created_at)
    after = lane.fetch("SELECT id, released_at, created_at FROM shop_items WHERE id = ANY($1) ORDER BY id",
                       list(expect))
    assert {r["id"]: (r["released_at"], r["created_at"]) for r in after} == expect
    assert lane.fetch("SELECT count(*) FROM shop_items WHERE " + window, since)[0][0] == 0
    return len(before)


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


def _encode(doc) -> bytes:
    """The bytes the api's JSONResponse renders for doc."""
    return json.dumps(doc, ensure_ascii=False, allow_nan=False, indent=None,
                      separators=(",", ":")).encode("utf-8")


def _settle(req, r):
    """r with every TIES list's runs of adjacent equal-key rows in tiebreak
    order. An answer that does not round-trip through _encode byte for byte,
    or whose list is not rows that all carry both keys, is returned as it is:
    it is then compared raw, so a tie the settling cannot reach still counts."""
    path = req["url"].split("?")[0]
    ties = [(lst, key, tie) for method, url, lst, key, tie in TIES
            if req["method"] == method and path == url]
    if not ties:
        return r
    raw = base64.b64decode(r["body"])
    doc = _decode(r)
    if isinstance(doc, bytes) or _encode(doc) != raw:
        return r
    for lst, key, tie in ties:
        try:
            rows = _at(doc, lst)
        except (KeyError, IndexError, ValueError, TypeError):
            continue
        if not isinstance(rows, list) or not all(isinstance(x, dict) and key in x and tie in x for x in rows):
            continue
        i = 0
        while i < len(rows):
            j = i
            while j + 1 < len(rows) and rows[j + 1][key] == rows[i][key]:
                j += 1
            rows[i:j + 1] = sorted(rows[i:j + 1], key=lambda x: x[tie])
            i = j + 1
    body = _encode(doc)
    assert len(body) == len(raw)       # a permutation; the content-length still holds
    return dict(r, body=base64.b64encode(body).decode())


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


def _leaves(doc, prefix=""):
    """Every scalar in a decoded body, as (JSON path, value) in _paths' syntax."""
    if isinstance(doc, dict):
        for k, v in doc.items():
            yield from _leaves(v, prefix + "/" + str(k))
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            yield from _leaves(v, prefix + "/" + str(i))
    else:
        yield prefix or "/", doc


def _build_days(start, end):
    """Every UTC day the build window touched, first to last."""
    days, day = [], start.date()
    while day <= end.date():
        days.append(day)
        day += timedelta(days=1)
    return days


def _date_forms(day):
    """The two date-only spellings the api emits: ISO, and to_char 'Mon FMDD'."""
    return day.isoformat(), MONTHS[day.month - 1] + " " + str(day.day)


def build_day_leaks(requests, results, days):
    """Every date-only value in an answer that names a day of this run's build
    window, outside the paths NOISE declares. Every such value seen so far was
    a database-clock stamp truncated to a date, which two sides built on
    different UTC days answer differently and a same-day run cannot see vary
    (lesson 1062); a literal that happens to equal a build day is reported
    too, and either way the answer must not depend on the build day.
    Returns (site, method, url, session, path, value) per leak."""
    forms = {form for day in days for form in _date_forms(day)}
    leaks = []
    for req, r in zip(requests, results):
        declared = dict(_declared(req))
        doc = _decode(r)
        if isinstance(doc, bytes):
            continue
        for path, value in _leaves(doc):
            if isinstance(value, str) and value in forms and path not in declared:
                leaks.append((req["site"], req["method"], req["url"], req["session"], path, value))
    return leaks


def _same(value, want) -> bool:
    """value is want, of the same JSON type (1 is not True, 1 is not 1.0)."""
    return type(value) is type(want) and value == want


def _intended_rows(req):
    """The INTENDED rows of this request: its method and its URL's exact path."""
    path = req["url"].split("?")[0]
    return [row for row in INTENDED if row[0] == req["method"] and row[1] == path]


def _content_length_holds(x) -> bool:
    """Exactly one content-length, and it is the length of this side's own body."""
    lengths = [v for k, v in x["headers"] if k == "content-length"]
    return len(lengths) == 1 and lengths[0] == str(len(base64.b64decode(x["body"])))


def _intended(req, b, l) -> int:
    """The number of (request, path) pairs INTENDED accepts for a lane answer l
    that differs from trunk's deterministic answer b, or 0 when it accepts
    none: every condition must hold (see INTENDED)."""
    if b["status"] != l["status"]:
        return 0
    if (sorted((k, v) for k, v in b["headers"] if k != "content-length")
            != sorted((k, v) for k, v in l["headers"] if k != "content-length")):
        return 0
    if not (_content_length_holds(b) and _content_length_holds(l)):
        return 0
    rows = _intended_rows(req)
    declared = {row[2] for row in rows}
    db, dl = _decode(b), _decode(l)
    if not declared or isinstance(db, bytes) or isinstance(dl, bytes):
        return 0
    if _paths(db, dl) != declared:
        return 0
    for _method, _url, path, old, new, _reason in rows:
        try:
            if not (_same(_at(db, path), old) and _same(_at(dl, path), new)):
                return 0
        except (KeyError, IndexError, ValueError, TypeError):
            return 0
    return len(declared)


def intended_closing(requests, base, lane):
    """Every INTENDED row that describes nothing, by name: a row must name at
    least one request of the list, and over the requests it names it must be
    USED (trunk holds the old value and the lane the new one) or SETTLED (both
    hold the lane's value), the same state at every one of them."""
    problems = []
    for row in INTENDED:
        method, url, path, old, new, _reason = row
        states = set()
        for req, b, l in zip(requests, base, lane):
            if (req["method"], req["url"].split("?")[0]) != (method, url):
                continue
            try:
                vb, vl = _at(_decode(_settle(req, b)), path), _at(_decode(_settle(req, l)), path)
            except (KeyError, IndexError, ValueError, TypeError):
                states.add("neither")
                continue
            if _same(vb, old) and _same(vl, new):
                states.add("used")
            elif _same(vb, new) and _same(vl, new):
                states.add("settled")
            else:
                states.add("neither")
        if not states:
            problems.append(("INTENDED row names no request of the list", method, url, path))
        elif states not in ({"used"}, {"settled"}):
            problems.append(("INTENDED row is neither USED nor SETTLED", method, url, path, sorted(states)))
    return problems


def compare(requests, base, lane, ctl):
    """Every disagreement of the lane with trunk, judged against the frozen
    replay. Returns (problems, counts).

    An answer the control reproduces exactly is DETERMINISTIC: the lane must
    equal it exactly, or differ from it only as INTENDED declares for that
    request (_intended; counts["intended"] is the number of (request, path)
    pairs accepted so). Otherwise every path where any two of the three bodies
    differ must be a path NOISE declares for this request, every declared
    value present on any side must pass its validator, the statuses must be
    equal, and the headers equal except a content-length that matches its own
    body. A trunk variation NOISE does not declare is itself a problem: the
    oracle then cannot compare that answer, and says so. Every side is
    settled first (_settle: the TIES lists' equal-key runs in tiebreak order)."""
    problems, counts = [], {"deterministic": 0, "varying": 0, "validated": 0, "intended": 0}
    for req, b, l, c in zip(requests, base, lane, ctl):
        b, l, c = (_settle(req, x) for x in (b, l, c))
        where = (req["site"], req["method"], req["url"], req["session"])
        if _answer(b) == _answer(c) and not _carries_declared(req, b):
            counts["deterministic"] += 1
            if _answer(l) != _answer(b):
                accepted = _intended(req, b, l)
                if accepted:
                    counts["intended"] += accepted
                    continue
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
        built_from = datetime.now(timezone.utc)
        for prefix in ("rg_oracle_base", "rg_oracle_lane", "rg_oracle_ctl"):
            built_after = datetime.now(timezone.utc)
            lane = PG.Lane(prefix).open()
            lanes.append(lane)
            _seed(lane)
            _pin_build_clock(lane, built_after)
        yield lanes, built_from
    finally:
        for lane in lanes:
            lane.close()


def test_1403_replay_matches_trunk_oracle(three_lanes, tmp_path, capsys):
    (base_lane, lane_lane, ctl_lane), built_from = three_lanes
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
    # Every INTENDED row is USED or SETTLED over the requests it names (see INTENDED).
    problems += intended_closing(requests, base["results"], lane["results"])
    statuses = {}
    for r in base["results"]:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    with capsys.disabled():
        print(f"\n[bv-a oracle] base {sha[:8]} requests {len(requests)} "
              f"(calls {CALLS_AT_TAG}) frozen at {freeze} deterministic {counts['deterministic']} "
              f"varying {counts['varying']} validated {counts['validated']} intended {counts['intended']} "
              f"trunk statuses {sorted(statuses.items())} problems {len(problems)}")
        for q, b, c in zip(requests, base["results"], ctl["results"]):
            b, c = _settle(q, b), _settle(q, c)
            if _answer(b) != _answer(c):
                print("[bv-a varying on trunk]", q["method"], q["url"], "session" if q["session"] else "",
                      sorted(_paths(_decode(b), _decode(c)))[:6])
        for p in problems[:40]:
            print("[bv-a problem]", p)
    assert not problems
    # No answer names a day of the build window as a date-only value (see
    # build_day_leaks): _pin_build_clock is what keeps this empty, and this is
    # what notices the next build-time stamp a response starts to carry.
    # One day wider on each side: to_char renders in the session's zone, so a
    # build-time stamp can date as the day before or after the UTC build day.
    days = _build_days(built_from - timedelta(days=1), datetime.now(timezone.utc) + timedelta(days=1))
    leaks = [(side,) + leak for side, out in (("base", base), ("lane", lane), ("control", ctl))
             for leak in build_day_leaks(requests, out["results"], days)]
    with capsys.disabled():
        for leak in leaks[:40]:
            print("[bv-a build-day leak]", leak)
    assert not leaks, leaks[:10]
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


def _shop(*rows):
    """A /shop/items body in the api's own encoding: rows are (id, price)."""
    return _r(_encode({"items": [{"id": i, "sku": "s%d" % i, "price": p} for i, p in rows]}))


def test_settle_control(monkeypatch):
    """TIES settles trunk's equal-price order and nothing else: base and
    control that disagree only inside a run of adjacent equal prices compare
    equal, and so does a lane in id order; a row moved to another price, a
    changed row inside a run, a merge of two NON-adjacent equal-price runs, a
    body the settling cannot round-trip and another url are all still
    reported. With TIES empty the tie disagreement is reported again, so the
    declaration is what accepts it."""
    shop = [{"site": "s", "method": "GET", "url": "/api/v1/shop/items?steam_id=1", "session": True}]
    base = _shop((3, 100), (1, 100), (2, 100), (7, 200), (5, 300))
    ctl = _shop((2, 100), (3, 100), (1, 100), (7, 200), (5, 300))
    lane = _shop((1, 100), (2, 100), (3, 100), (7, 200), (5, 300))
    assert not compare(shop, [base], [lane], [ctl])[0]
    assert not compare(shop, [base], [base], [ctl])[0]
    counts = compare(shop, [base], [lane], [ctl])[1]
    assert counts == {"deterministic": 1, "varying": 0, "validated": 0, "intended": 0}, counts
    # a row at another price is a difference
    assert compare(shop, [base], [_shop((1, 100), (2, 100), (7, 100), (3, 200), (5, 300))], [ctl])[0]
    # a changed row inside a run is a difference
    changed = _r(_encode({"items": [{"id": 1, "sku": "x", "price": 100}, {"id": 2, "sku": "s2", "price": 100},
                                    {"id": 3, "sku": "s3", "price": 100}, {"id": 7, "sku": "s7", "price": 200},
                                    {"id": 5, "sku": "s5", "price": 300}]}))
    assert compare(shop, [base], [changed], [ctl])[0]
    # only ADJACENT equal prices form a run: an appended row at another price keeps its place
    tail = _shop((3, 100), (1, 100), (7, 200), (2, 100))
    assert compare(shop, [tail], [_shop((1, 100), (2, 100), (3, 100), (7, 200))], [tail])[0]
    assert not compare(shop, [tail], [_shop((1, 100), (3, 100), (7, 200), (2, 100))], [tail])[0]
    # the limit, stated: a run is not split at the catalogue's end, so appended rows at the
    # last catalogue price are settled into its run (no answered field names a row's pool)
    joined = _shop((5, 300), (9, 300), (7, 300))
    assert not compare(shop, [joined], [_shop((5, 300), (7, 300), (9, 300))], [joined])[0]
    # a body that does not round-trip is compared raw
    spaced = _r(b'{"items": [{"id": 3, "price": 100}, {"id": 1, "price": 100}]}')
    plain = _r(b'{"items": [{"id": 1, "price": 100}, {"id": 3, "price": 100}]}')
    assert compare(shop, [spaced], [spaced], [plain])[0]
    # another url is not settled
    other = [{"site": "s", "method": "GET", "url": "/api/v1/shop/newest", "session": False}]
    assert compare(other, [base], [lane], [ctl])[0]
    # negative control: without the declaration trunk's tie disagreement is a problem
    monkeypatch.setattr(sys.modules[__name__], "TIES", [])
    assert compare(shop, [base], [lane], [ctl])[0]


def test_build_day_sweep_control():
    """The sweep reports a date-only value naming a build day in either
    spelling, on any side; not another day, not a number, not a value at a
    path NOISE declares for the request; and the window spans the days."""
    day = datetime(2026, 10, 30, 23, 59, tzinfo=timezone.utc)
    days = _build_days(day, day + timedelta(minutes=2))
    assert [d.isoformat() for d in days] == ["2026-10-30", "2026-10-31"], days
    req = [{"site": "s", "method": "GET", "url": "/api/v1/shop/items", "session": False}]
    hit = _r(b'{"items": [{"released_iso": "2026-10-30", "added": "Oct 31", "n": 20261030}]}')
    assert [leak[4:] for leak in build_day_leaks(req, [hit], days)] == [
        ("/items/0/released_iso", "2026-10-30"), ("/items/0/added", "Oct 31")]
    miss = _r(b'{"items": [{"released_iso": "2026-10-29", "added": "Oct 29", "t": "2026-10-30T01:02:03Z"}]}')
    assert build_day_leaks(req, [miss], days) == []
    assert build_day_leaks(req, [_r(b"not json")], days) == []
    # a path NOISE declares for the request is judged by its own check, not here
    h2h = [{"site": "s", "method": "GET", "url": "/api/v1/h2h/1/2", "session": True}]
    declared = _r(b'{"profile": {"last_seen_s": "2026-10-30"}, "line": "2026-10-30"}')
    assert [leak[4] for leak in build_day_leaks(h2h, [declared], days)] == ["/line"]


def _quarantine_row():
    (row,) = [r for r in INTENDED if r[:3] == ("GET", "/api/v1/admin/quarantine", "/detail")]
    return row


def test_intended_control():
    """INTENDED accepts the declared difference with the row's exact values,
    and nothing else: the lane's value or trunk's value not the row's, a second
    differing path, a status, a header other than content-length, a
    content-length that does not match its own body, a sibling URL under the
    same prefix and the same path under another method are each a problem."""
    _m, url, _p, old, new, _reason = _quarantine_row()
    req = [{"site": "s", "method": "GET", "url": url + "?admin_steam_id=1&hmac_signature=00", "session": False}]

    def ans(detail, status=403, **more):
        return _r(_encode(dict({"detail": detail}, **more)), status=status)
    trunk, lane = ans(old), ans(new)
    problems, counts = compare(req, [trunk], [lane], [trunk])
    assert not problems, problems
    assert counts == {"deterministic": 1, "varying": 0, "validated": 0, "intended": 1}, counts
    # the lane's value is not the row's
    assert compare(req, [trunk], [ans(new + " ")], [trunk])[0]
    # trunk's value is not the row's
    other = ans("Bad admin signature")
    assert compare(req, [other], [lane], [other])[0]
    # a second path differs that the row does not declare
    two_t, two_l = ans(old, n=1), ans(new, n=2)
    assert compare(req, [two_t], [two_l], [two_t])[0]
    # the status differs
    assert compare(req, [trunk], [ans(new, status=401)], [trunk])[0]
    # a header other than content-length differs
    typed = dict(lane, headers=[h for h in lane["headers"] if h[0] != "content-type"]
                 + [["content-type", "text/plain"]])
    assert compare(req, [trunk], [typed], [trunk])[0]
    # a content-length that does not match its own body (on either side)
    bad = dict(lane, headers=[["content-length", "25"], ["content-type", "application/json"]])
    assert compare(req, [trunk], [bad], [trunk])[0]
    bad_t = dict(trunk, headers=[["content-length", "97"], ["content-type", "application/json"]])
    assert compare(req, [bad_t], [lane], [bad_t])[0]
    # the same difference on a request the row does not name
    for method, sibling in (("GET", url + "/00000000-0000-4000-8000-000000000001/discard"),
                            ("POST", url + "/00000000-0000-4000-8000-000000000001/discard"),
                            ("POST", url + "?admin_steam_id=1&hmac_signature=00")):
        q = [{"site": "s", "method": method, "url": sibling, "session": False}]
        assert compare(q, [trunk], [lane], [trunk])[0], (method, sibling)


def test_intended_closing_control():
    """The closing check: a USED row and a SETTLED row pass; a row whose request
    holds the OLD value on both sides is named; a row that names no request of
    the list is named; and the test of record calls the check."""
    _m, url, path, old, new, _reason = _quarantine_row()
    req = [{"site": "s", "method": "GET", "url": url + "?admin_steam_id=1&hmac_signature=00", "session": s}
           for s in (False, True)]
    trunk, lane = (_r(_encode({"detail": v}), status=403) for v in (old, new))
    assert intended_closing(req, [trunk, trunk], [lane, lane]) == []          # USED
    assert intended_closing(req, [lane, lane], [lane, lane]) == []            # SETTLED
    stale = intended_closing(req, [trunk, trunk], [trunk, trunk])
    assert [p[:4] for p in stale] == [("INTENDED row is neither USED nor SETTLED", "GET", url, path)], stale
    mixed = intended_closing(req, [trunk, lane], [lane, lane])
    assert [p[:4] for p in mixed] == [("INTENDED row is neither USED nor SETTLED", "GET", url, path)], mixed
    elsewhere = [dict(q, url="/api/v1/mod-version") for q in req]
    gone = intended_closing(elsewhere, [trunk, trunk], [lane, lane])
    assert gone == [("INTENDED row names no request of the list", "GET", url, path)], gone
    calls = {n.func.id for n in ast.walk(ast.parse(inspect.getsource(test_1403_replay_matches_trunk_oracle)))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "intended_closing" in calls, calls
