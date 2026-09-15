"""Player Cards requests have rate buckets of their own (v4.13 §9, triage I3).

The gate is driven directly: `main.rate_limit_gate` with a scripted request,
a stub `call_next` and a scripted clock, so every assertion reads the answer
the middleware itself gives and the bucket a request was charged to.

Pinned here, each against the requirement it answers:
  * a Player Cards session from one address leaves the sensitive bucket's
    budget (queue join, match report, bets, sign-in) whole, in either order;
  * every /api/v1/pc/ route is charged to a Player Cards bucket -- exactly the
    upload's path to the upload bucket, every other family path (one that only
    starts with the upload's included) to the family bucket -- and no other
    route is; the upload is the only family route that takes a request body
    (a body parameter, or a read of the body in the endpoint or in a function
    of main it hands its request to);
    /api/v1/internal/ routes and calls carrying the internal key (the bot's)
    are charged to no bucket;
  * the drop client's fastest recorded discard pace, with the margin §9
    states, is never refused, and a per-frame loop is refused on the excess;
  * the upload bucket keeps the bound it had: 20 in any 10 s;
  * a refusal on either new bucket names the whole window, 10 s;
  * the two buckets hold §9's numbers as literals, 90 and 20 in any 10 s:
    the code comment, the bug thread and R-G7i's bound are stated for them;
  * for a fixed request sequence from one address, the split has refused no
    more requests than the one shared bucket had by every event, and inside
    any run of events it refuses at most 20 (the shared limit) more -- the
    edge's abuse jail counts refusals in a sliding window, so that 20 is a
    stated residual (R-G7i), not a property the split removes;
  * reading a committed pack again (an open's replay, /packs/result) schedules
    no pre-render -- only the request that minted the pack asks for one -- and
    a face already in the disk cache is answered without reading its picture.
"""
import ast
import asyncio
import inspect
import json
import random
import re
import textwrap
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.requests import Request
from starlette.responses import Response

import main

BOT_PY = Path(__file__).resolve().parents[1] / "discord_bot.py"
ADDR = "203.0.113.7"
KEY = "g7-internal-key"

# v4.12's gate for the traffic this fold moves: every /api/v1/pc/ route and
# every sensitive route shared ONE bucket per address, 20 in any 10 s.
SHARED_LIMIT, SHARED_WINDOW = 20, 10.0

DISCARD = "/api/v1/pc/prints/discard"
UPLOAD = "/api/v1/pc/portrait"


class Gate:
    """rate_limit_gate on a scripted clock and fresh buckets."""

    def __init__(self, monkeypatch):
        self.now = 0.0
        self.monkeypatch = monkeypatch
        monkeypatch.setattr(main, "_rl_time", SimpleNamespace(monotonic=lambda: self.now))
        monkeypatch.setattr(main, "_RL_BUCKETS", defaultdict(deque))
        monkeypatch.setattr(main, "_RL_LAST_PRUNE", [0.0])
        monkeypatch.setenv("API_SECRET_KEY", KEY)

    def reset(self):
        main._RL_BUCKETS.clear()
        main._RL_LAST_PRUNE[0] = 0.0

    @staticmethod
    def _request(path, method, headers):
        return Request({
            "type": "http", "method": method, "path": path, "raw_path": path.encode(),
            "root_path": "", "query_string": b"", "scheme": "http",
            "server": ("testserver", 8443), "client": (ADDR, 50000),
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        })

    def run(self, events):
        """events: (t, path[, method[, headers]]) in time order -> the responses."""
        async def reached(_request):
            return Response(status_code=200)

        async def drive():
            out = []
            for ev in events:
                t, path = ev[0], ev[1]
                method = ev[2] if len(ev) > 2 else "GET"
                headers = ev[3] if len(ev) > 3 else None
                assert t >= self.now, "events must be in time order"
                self.now = t
                out.append(await main.rate_limit_gate(self._request(path, method, headers), reached))
            return out
        return asyncio.run(drive())

    def statuses(self, events):
        return [r.status_code for r in self.run(events)]

    def bucket_of(self, path, method="GET", headers=None):
        """The bucket suffix one request is charged to, or None for no bucket."""
        self.reset()
        self.run([(self.now, path, method, headers)])
        keys = [k for k, dq in main._RL_BUCKETS.items() if dq]
        assert len(keys) <= 1, keys
        if not keys:
            return None
        address, suffix = keys[0].rsplit("|", 1)
        assert address == ADDR
        return suffix


@pytest.fixture
def gate(monkeypatch):
    return Gate(monkeypatch)


def test_a_card_session_leaves_the_sensitive_budget_whole(gate):
    """The v4.12 failure, both ways round: from one address, card requests
    used to spend the 20 that a queue join, a match report, a bet or a sign-in
    needs in the same 10 s."""
    cards = [(i * 0.1, DISCARD, "POST") for i in range(60)]
    sensitive = [(6.0 + i * 0.05, p, "POST") for i, p in
                 enumerate(["/api/v1/queue/join", "/api/v1/auth/steam"] + ["/api/v1/matches"] * 18)]
    answers = gate.statuses(sorted(cards + sensitive))
    assert answers == [200] * 80

    gate.reset()
    start = gate.now + 60.0
    sensitive = [(start + i * 0.05, "/api/v1/bets", "POST") for i in range(21)]
    cards = [(start + 1.5 + i * 0.05, p, "GET") for i, p in
             enumerate(["/api/v1/pc/me", "/api/v1/pc/collection", "/api/v1/pc/packs"] * 10)]
    answers = gate.statuses(sensitive + cards)
    assert answers[:20] == [200] * 20 and answers[20] == 429   # the sensitive bucket still holds
    assert answers[21:] == [200] * 30                          # and it is not the cards' bucket


def _concrete(path):
    return re.sub(r"\{[^}]+\}", "x1", path)


def _reads_the_body(fn, name):
    """A read of the request body through the parameter `name` in fn's own
    source: body(), json(), form() or stream(), or its receive channel."""
    pattern = r"\b%s\s*\.\s*(?:(?:body|json|form|stream)\s*\(|_?receive\b)" % re.escape(name)
    return re.search(pattern, inspect.getsource(fn)) is not None


def _takes_a_body(route):
    """A body parameter, or a read of the body in the endpoint or in any
    function of main the endpoint passes its request to (one call deep,
    positionally or by keyword)."""
    if route.dependant.body_params:
        return True
    name = route.dependant.request_param_name
    if name is None:
        return False
    if _reads_the_body(route.endpoint, name):
        return True
    tree = ast.parse(textwrap.dedent(inspect.getsource(route.endpoint)))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        helper = getattr(main, node.func.id, None)
        if not inspect.isfunction(helper):
            continue
        params = list(inspect.signature(helper).parameters)
        bound = [params[i] for i, a in enumerate(node.args)
                 if isinstance(a, ast.Name) and a.id == name and i < len(params)]
        bound += [k.arg for k in node.keywords if isinstance(k.value, ast.Name) and k.value.id == name and k.arg]
        if any(_reads_the_body(helper, p) for p in bound):
            return True
    return False


def test_every_route_is_charged_to_the_bucket_its_family_names(gate):
    """A class pin over the app's own routing table, not a list of names. The
    expected bucket comes from the gate's own path rule: exactly the upload's
    path goes to the upload bucket, every other family path to the family
    bucket, so a Player Cards route added later is classified by the rule and
    a route outside the family can never land in its buckets. The upload
    bucket is the bound on the decodes a request body queues in the render
    pool, so a second family route that takes a body fails here until someone
    decides which bucket it belongs in."""
    family = upload = 0
    with_body = set()
    for route in main.app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1/"):
            continue
        for method in sorted(getattr(route, "methods", None) or {"GET"}):
            bucket = gate.bucket_of(_concrete(path), method)
            if path.startswith("/api/v1/internal/"):
                assert bucket is None, path      # 403 before any bucket without the key
                assert gate.bucket_of(_concrete(path), method, {"X-Internal-Key": KEY}) is None, path
            elif path.startswith("/api/v1/pc/"):
                if _takes_a_body(route):
                    with_body.add(path)
                if path == UPLOAD:
                    assert bucket == "pcu", (path, bucket)
                    upload += 1
                else:
                    assert bucket == "pc", (path, bucket)
                    family += 1
                assert gate.bucket_of(_concrete(path), method, {"X-Internal-Key": KEY}) is None, path
            elif path in main._RATE_LIMIT_BYPASS:
                assert bucket is None, path
            else:
                assert bucket in ("g", "s", "f"), (path, bucket)
    # the recovery must see the family at all, or every assertion above is vacuous
    assert family >= 10 and upload >= 1, (family, upload)
    assert with_body == {UPLOAD}, with_body
    # a path that only starts with the upload's is family traffic, whatever it carries
    for near in (UPLOAD + "s", UPLOAD + "-status", UPLOAD + "/x1"):
        for method in ("GET", "POST"):
            assert gate.bucket_of(near, method) == "pc", (near, method)


def _drop_client_discards(cycle, seconds, rtt=0.12):
    """The drop client (4db577d) discarding one card at a time at `cycle`
    seconds per card: the discard, then the collection and profile refetches
    when its answer lands; beside it the tab's profile poll (30 s) and the
    pack-recovery poll (15 s)."""
    events = []
    k = 0
    while k * cycle < seconds:
        t = k * cycle
        events += [(t, DISCARD, "POST"), (t + rtt, "/api/v1/pc/collection"), (t + rtt, "/api/v1/pc/me")]
        k += 1
    events += [(n * 30.0 + 0.01, "/api/v1/pc/me") for n in range(int(seconds // 30) + 1)]
    events += [(n * 15.0 + 0.02, "/api/v1/pc/packs/result") for n in range(int(seconds // 15) + 1)]
    return sorted(events, key=lambda e: e[0])


def test_the_drop_clients_fastest_recorded_pace_is_never_refused_and_a_frame_loop_is(gate):
    """§9's number, both edges. The closest two discards production had
    recorded by 2026-09-15 were 0.419 s apart; §9 sizes the bucket for a pace
    of 0.345 s, i.e. 29 discards in any 10 s at three requests each, plus the
    two polls -- 89 of 90."""
    answers = gate.statuses(_drop_client_discards(0.345, 120.0))
    assert answers.count(429) == 0

    # One request per frame at 10 fps (a low frame rate for any seat): 100 in
    # every 10 s. The excess is refused, and what is let through never exceeds
    # the limit in any window.
    gate.reset()
    start = gate.now + 60.0
    loop = [(start + n * 0.1, "/api/v1/pc/me") for n in range(600)]
    answers = gate.statuses(loop)
    assert answers.count(429) >= 50
    accepted = [t for (t, _), a in zip(loop, answers) if a == 200]
    limit, window = main._RL_PC
    assert max(sum(1 for u in accepted if t - window <= u <= t) for t in accepted) <= limit


def test_the_picture_upload_keeps_its_bound_in_a_bucket_of_its_own(gate):
    """v22 §1.7's bound: the upload is decoded in the shared render pool
    before the session proof and the pacing, so an address gets 20 uploads in
    any 10 s -- no more than the shared bucket gave it -- and they spend
    neither the card budget nor the sensitive one."""
    answers = gate.statuses([(i * 0.2, UPLOAD, "POST") for i in range(21)])
    assert answers == [200] * 20 + [429]
    assert gate.statuses([(4.5, DISCARD, "POST"), (4.6, "/api/v1/queue/join", "POST")]) == [200, 200]

    gate.reset()
    start = gate.now + 60.0
    cards = [(start + i * 0.05, "/api/v1/pc/me") for i in range(90)]
    assert gate.statuses(cards + [(start + 5.0, UPLOAD, "POST")]) == [200] * 91


def test_the_buckets_hold_the_numbers_section_9_states():
    """§9's numbers as literals: the family bucket takes 90 and the upload
    bucket 20 in any 10 s. The tests around this one bound behaviour (the
    pace, the loop, the upload bound, the refusal, the run excess), and a
    neighbouring pair such as 91 in 10 s passes all of them. The _RL_PC
    comment's 90 in 10 s, the bug thread's 10 s wait, the 89-of-90 sizing and
    R-G7i's bound of 20, whose proof needs a 10 s window on every bucket, are
    stated for exactly these values, so changing either pair fails here until
    that text is revisited."""
    assert main._RL_PC == (90, 10.0)
    assert main._RL_PC_UPLOAD == (20, 10.0)


def test_a_refusal_names_the_whole_window_on_both_new_buckets(gate):
    """retry_after stays the window (triage I3): slots free one at a time, so
    an exact time-to-the-next-slot would refuse every copy of a Dupes chain
    again the moment it came back. The 10 is a literal: it is the wait the
    bug thread tells a refused player."""
    for path, method, (limit, window) in ((DISCARD, "POST", main._RL_PC), (UPLOAD, "POST", main._RL_PC_UPLOAD)):
        gate.reset()
        start = gate.now + 60.0
        fill = [(start + i * 0.001, path, method) for i in range(limit)]
        responses = gate.run(fill + [(start + window - 0.5, path, method)])
        assert [r.status_code for r in responses] == [200] * limit + [429]
        refused = responses[-1]
        assert json.loads(refused.body) == {"error": "rate_limited", "retry_after": 10}
        assert refused.headers["Retry-After"] == "10"


def test_the_bot_and_the_internal_routes_never_reach_a_bucket(gate):
    """The bot calls from one address. Its Player Cards calls are internal
    routes carrying the key, and the key exempts a public route too, so no
    per-address bucket can throttle it."""
    with_key = {"X-Internal-Key": KEY}
    events = [(i * 0.001, "/api/v1/internal/pc/daily", "POST", with_key) for i in range(300)]
    events += [(0.5 + i * 0.001, "/api/v1/pc/me", "GET", with_key) for i in range(300)]
    events += [(1.0 + i * 0.001, UPLOAD, "POST", with_key) for i in range(300)]
    assert gate.statuses(events) == [200] * 900
    assert not any(main._RL_BUCKETS.values())
    assert gate.bucket_of("/api/v1/pc/me") == "pc"   # the same route without the key is charged


def test_every_bot_player_cards_call_is_an_internal_route():
    src = BOT_PY.read_text(encoding="utf-8")
    assert re.findall(r"(?<!/internal)/pc/", src) == [], "a bot call to a public Player Cards route"
    assert "/api/v1/pc" not in src
    calls = re.findall(r"_pc_api(?:_bytes)?\(\s*(?:\"(?:GET|POST|DELETE)\",\s*)?f?\"([^\"]*)\"", src)
    assert len(calls) >= 10 and all(c.startswith("/internal/pc/") for c in calls), calls
    assert 'default_headers = {"X-Internal-Key": API_SECRET_KEY} if API_SECRET_KEY else {}' in src


# ── the edge jail: what the split changes about refusals ─────────────────────

_JAIL_PATHS = [DISCARD, "/api/v1/pc/me", UPLOAD, "/api/v1/queue/join", "/api/v1/matches"]


def _shared_bucket_refusals(events):
    """Per event, 1 where v4.12's one shared bucket refused it, else 0 -- the
    gate's own rule: a slot frees once its request is more than the window old,
    and a refused request takes no slot."""
    dq, out = deque(), []
    for t, *_ in events:
        while dq and dq[0] < t - SHARED_WINDOW:
            dq.popleft()
        if len(dq) >= SHARED_LIMIT:
            out.append(1)
            continue
        dq.append(t)
        out.append(0)
    return out


def _split_refusals(gate, events):
    return [1 if s == 429 else 0 for s in gate.statuses(events)]


def _sequences(gate, seed, n):
    """Fixed request sequences from one address, dense in each class (the
    upload alone included): half spread uniformly, half in bursts on a coarse
    clock, which puts many requests on one instant and exactly one window
    apart. Each starts on fresh buckets, a minute after the last."""
    rng = random.Random(seed)
    mixes = [(1, 1, 1, 1, 1), (0, 0, 1, 0, 0), (5, 5, 0, 1, 1), (0, 0, 5, 1, 1), (1, 1, 8, 0, 0), (0, 0, 0, 1, 1)]
    for trial in range(n):
        gate.reset()
        start = gate.now + 60.0
        if trial % 2:
            t, events = start, []
            for _ in range(rng.randint(1, 8)):
                t += rng.choice([0.0, 0.5, 2.5, 5.0, 5.5, 10.0, 10.5, 15.0])
                events += [(t, rng.choice(_JAIL_PATHS), "POST")] * rng.randint(1, 25)
        else:
            span = rng.choice([1.0, 5.0, 10.0, 25.0, 60.0])
            mix = rng.choice(mixes)
            events = sorted((start + round(rng.uniform(0, span), 3), rng.choices(_JAIL_PATHS, mix)[0], "POST")
                            for _ in range(rng.randint(1, 140)))
        yield trial, events


def test_the_split_has_refused_no_more_than_the_shared_bucket_at_every_event(gate):
    """By every event of a fixed request sequence from one address, the split
    has refused no more requests than v4.12's one shared bucket had. A bucket
    that accepts whenever it has room accepts, by every moment, at least as
    many requests as any schedule that keeps within its limit (at the first
    request the two disagree on, it is the one that accepted); what the shared
    bucket accepted of each new bucket's traffic is such a schedule, because
    each new bucket carries a subset of that traffic and no new limit is below
    20. This is about cumulative refusals only -- inside a window the split
    can refuse more (next test)."""
    for trial, events in _sequences(gate, 413, 300):
        split, shared = _split_refusals(gate, events), _shared_bucket_refusals(events)
        s = o = 0
        for i, (a, b) in enumerate(zip(split, shared)):
            s, o = s + a, o + b
            assert s <= o, (trial, i, s, o)


def _worst_run_excess(split, shared):
    """The largest (split refusals - shared refusals) over any contiguous run of events."""
    worst = lowest = running = 0
    for a, b in zip(split, shared):
        running += a - b
        worst = max(worst, running - lowest)
        lowest = min(lowest, running)
    return worst


def test_inside_any_run_of_events_the_split_refuses_at_most_the_shared_limit_more(gate):
    """The edge's jail counts 429s per address in a sliding 10 min window, and
    cumulative dominance says nothing inside one: the split can move refusals
    later. The case: 20 queue joins at 0 s fill the shared bucket, so v4.12
    refused 20 uploads at 5 s and took 20 more at 10.5 s; the split takes the
    first 20 uploads into their own bucket and refuses the 20 at 10.5 s. A run
    of events starting at 10.5 s sees 20 refusals that v4.12 did not have.

    The bound: inside any run the split refuses at most 20 more. Only requests
    the new buckets accepted before the run can displace a request inside it,
    only during the run's first 10 s, and each displaced request is one the
    shared bucket accepted there -- at most 20. The first 10 s is the new
    buckets' window, so the bound holds only while every bucket's window is
    the shared 10 s (the literal pin above holds that). §9 records this as
    R-G7i.

    The random sequences send at most 25 requests per burst and never fill
    the family bucket, so the bound is also pinned on it: its whole limit 1 s
    after 20 queue joins, then 20 card reads at 10.5 s and at 20.6 s. The
    split refuses the 20 at 10.5 s and v4.12 none; a family window longer
    than 19.6 s would also refuse the 20 at 20.6 s and exceed the bound."""
    t0 = 60.0
    case = ([(t0, "/api/v1/queue/join", "POST")] * 20 + [(t0 + 5.0, UPLOAD, "POST")] * 20
            + [(t0 + 10.5, UPLOAD, "POST")] * 20)
    split, shared = _split_refusals(gate, case), _shared_bucket_refusals(case)
    assert sum(split) == sum(shared) == 20
    assert sum(split[40:]) == 20 and sum(shared[40:]) == 0
    assert _worst_run_excess(split, shared) == SHARED_LIMIT   # the bound is reached, so it is the bound

    limit, _window = main._RL_PC
    gate.reset()
    t1 = gate.now + 60.0
    family = ([(t1, "/api/v1/queue/join", "POST")] * 20 + [(t1 + 1.0, "/api/v1/pc/me", "GET")] * limit
              + [(t1 + 10.5, "/api/v1/pc/me", "GET")] * 20 + [(t1 + 20.6, "/api/v1/pc/me", "GET")] * 20)
    split, shared = _split_refusals(gate, family), _shared_bucket_refusals(family)
    assert _worst_run_excess(split, shared) == SHARED_LIMIT, _worst_run_excess(split, shared)
    assert sum(split) == 20 and sum(shared) == limit, (sum(split), sum(shared))
    for trial, events in _sequences(gate, 1409, 300):
        excess = _worst_run_excess(_split_refusals(gate, events), _shared_bucket_refusals(events))
        assert excess <= SHARED_LIMIT, (trial, excess)


# ── pre-render: reading a pack again starts no render work ───────────────────

STEAM = "76561198000000001"
PLAYER = uuid.UUID("00000000-0000-4000-8000-000000000007")


class _Rows:
    def __init__(self, rows=(), scalar=None):
        self.rows, self.scalar = list(rows), scalar

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def one(self):
        assert len(self.rows) == 1, self.rows
        return self.rows[0]

    def all(self):
        return list(self.rows)

    def scalar_one_or_none(self):
        return self.scalar


class _Db:
    """execute() answers by the first script key its normalised SQL contains."""

    def __init__(self, script):
        self.script, self.log, self.committed = script, [], 0

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.log.append(sql)
        for key, answer in self.script.items():
            if key in sql:
                return answer
        return _Rows()

    async def commit(self):
        self.committed += 1


def _run(coro):
    return asyncio.run(coro)


def _done_pack():
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    return {"id": uuid.UUID("00000000-0000-4000-8000-0000000000aa"), "status": "done", "source": "bought",
            "mode": None, "kind": None, "pay": "gold", "price": 100, "reject_reason": None,
            "created_at": now, "opened_at": now}


def _pack_fakes(monkeypatch):
    scheduled = []
    monkeypatch.setattr(main, "_pc_schedule_prerender", lambda ids, locale: scheduled.append((tuple(ids), locale)))
    monkeypatch.setattr(main, "_pc_require_renderer", lambda: None)

    async def actor(request, steam_id, sig, canon, db):
        return SimpleNamespace(id=PLAYER)
    monkeypatch.setattr(main, "_pc_verified_actor", actor)

    async def subjects(db, pack_id):
        return []
    monkeypatch.setattr(main, "_pc_pack_subjects", subjects)

    async def prime(ids, *args, **kwargs):
        return None
    monkeypatch.setattr(main, "_pc_steam_prime", prime)

    async def ctx(db, locale):
        return {"locale": locale}
    monkeypatch.setattr(main, "_pc_face_ctx", ctx)

    async def prints(db, pack_id, ctx=None):
        return [{"print_id": "%s-%d" % (pack_id, i)} for i in range(5)]
    monkeypatch.setattr(main, "_pc_prints_of_pack", prints)
    return scheduled


def test_reading_a_pack_again_schedules_no_prerender_and_only_the_mint_asks(monkeypatch):
    """v4.12 scheduled a pack's five faces x two sizes on EVERY done answer,
    and each render read the portrait blob before the cache, so 90 recovery
    reads in 10 s from one address could start 900 render calls. Now only the
    request that minted the pack asks: a recovery read or a replayed open
    answers the committed row and schedules nothing, in any locale."""
    scheduled = _pack_fakes(monkeypatch)
    row = _done_pack()
    pack = str(row["id"])
    locales = ["en", "de", "fr"]

    db = _Db({"SELECT id, status, source": _Rows([row])})
    for i in range(90):
        req = SimpleNamespace(headers={"X-Locale": locales[i % 3]})
        out = _run(main.pc_pack_result(request=req, steam_id=STEAM, sig="x", nonce=None, pack_id=pack, db=db))
        assert out["status"] == "done" and len(out["prints"]) == 5
    assert scheduled == [], "a recovery read scheduled a pre-render"

    held = _Db({"SELECT source, mode, reference_id": _Rows([]), "SET status = 'opening'": _Rows([]),
                "SELECT id, status, source": _Rows([row])})
    bought = _Db({"INSERT INTO pc_packs": _Rows(scalar=None), "SELECT id, status, source": _Rows([row])})
    for i in range(30):
        req = SimpleNamespace(headers={"X-Locale": locales[i % 3]})
        a = _run(main.pc_open_pack(request=req, steam_id=STEAM, sig="x", nonce=None, pay=None,
                                   expected_price=None, pack_id=pack, db=held))
        b = _run(main.pc_open_pack(request=req, steam_id=STEAM, sig="x", nonce="nonce-0001", pay="gold",
                                   expected_price=100, pack_id=None, db=bought))
        assert a["status"] == b["status"] == "done"
    assert held.committed == bought.committed == 0, "the replays must be answers of the committed row"
    assert scheduled == [], "a replayed open scheduled a pre-render"

    # the answer asks only when told to, once per call, in the caller's locale
    _run(main._pc_pack_answer(None, row, {"locale": "de"}))
    assert scheduled == []
    _run(main._pc_pack_answer(None, row, {"locale": "de"}, prerender=True))
    assert scheduled == [(tuple("%s-%d" % (pack, i) for i in range(5)), "de")]

    # ...and the one caller that tells it is the minting request, after its commit
    src = Path(main.__file__).read_text(encoding="utf-8")
    assert src.count("prerender=True") == 1
    mint = inspect.getsource(main.pc_open_pack)
    at = mint.index("prerender=True")
    assert mint.count("prerender=True") == 1
    assert mint.rindex("SET status = 'done'") < mint.rindex("await db.commit()") < at
    assert mint[at:].strip() == "prerender=True)", "the minting request's final answer is the caller"


def test_a_cached_face_is_answered_without_reading_its_picture(monkeypatch, tmp_path):
    """The face route, the bot's print face and the pre-render all draw through
    _pc_render_face. v4.12 read the portrait blob before it looked in the disk
    cache, so every request for a face already rendered still read the blob.
    The cache is looked in first now: the blob is read only when a render has
    to run, and a blob released between the row read and that read still
    refuses without caching anything."""
    renders, reads = [], []
    live = {"ab" * 32}

    class _Face:
        @staticmethod
        def render_face(spec, labels, portrait, size):
            renders.append((portrait, size))
            return b"\x89PNG" + size.encode()

    async def blob(db, phash):
        reads.append(phash)
        return b"picture" if phash in live else None

    monkeypatch.setattr(main, "_pcf", _Face)
    monkeypatch.setattr(main, "_pc_face_cache", main._pcp.FaceCache(str(tmp_path)))
    monkeypatch.setattr(main, "_pc_portrait_bytes", blob)
    monkeypatch.setattr(main, "_pc_face_inputs", lambda row, ctx: ({"name": ""}, "game", row["phash"], row["rev"]))
    ctx = {"locale": "en", "labels": {}}
    row = {"print_id": uuid.UUID("00000000-0000-4000-8000-0000000000b1"), "phash": "ab" * 32, "rev": "0" * 16}

    assert _run(main._pc_render_face(None, row, ctx, "card")) == ("0" * 16, b"\x89PNGcard")
    assert reads == ["ab" * 32] and renders == [(b"picture", "card")]
    for _ in range(90):
        assert _run(main._pc_render_face(None, row, ctx, "card")) == ("0" * 16, b"\x89PNGcard")
    assert reads == ["ab" * 32] and len(renders) == 1, "a cached face read its picture"
    assert _run(main._pc_render_face(None, row, ctx, "tile"))[1] == b"\x89PNGtile"
    assert len(reads) == 2 and len(renders) == 2   # a size not yet rendered is a miss: one read, one render

    gone = dict(row, print_id=uuid.UUID("00000000-0000-4000-8000-0000000000b2"), phash="cd" * 32, rev="1" * 16)
    for _ in range(2):
        with pytest.raises(main._PcPortraitMissing):
            _run(main._pc_render_face(None, gone, ctx, "card"))
    assert len(renders) == 2 and reads[-2:] == ["cd" * 32] * 2, "a released picture is refused, never cached"
