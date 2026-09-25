"""RJ-TRIAGE part 1, C7: the #scr-admin quarantine digest loop, EXECUTED.

discord_bot.py is not importable in a test process (it builds the bot at
import), so the digest's functions and state are lifted out of its AST,
stripped of their harness decorators and run here against fakes, in the
manner of test_mail_bot.py: a fake clock that time.monotonic, asyncio.sleep,
datetime.now, every D1 page and every Discord message advance; a fake D1
that answers the digest protocol over rows with a created_at and a commit
time; and a fake #scr-admin channel that can reject chosen messages. The
loop's own schedule is modelled as discord.py runs a tasks.loop(seconds=60):
iterations never overlap, and the next starts at max(this start + 60 s, this
end) (RJ-TRIAGE-DESIGN-V5 3.4 B4, the loop premise).

Every control pairs with a mutation that turns it RED and an inert twin at
the same site (rj_triage_controls.py beside this file plants both).
"""

import ast
import asyncio
import copy
import math
import os
import re
import types
from collections import Counter
from datetime import datetime, timedelta, timezone

SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "discord_bot.py"))
TEXT = open(SRC, encoding="utf-8").read()
TREE = ast.parse(TEXT)

WANT_FUNC = {"_qdigest_page", "_qdigest_pass", "_qdigest_when", "_qdigest_line", "_qdigest_messages",
             "_qdigest_channel", "_qdigest_send", "_qdigest_round", "_qdigest_totals_line",
             "_qdigest_iteration", "poll_quarantine_digest"}
WANT_ASSIGN = {"QDIGEST_PAGE_TIMEOUT_S", "QDIGEST_ROUND_EVERY_S", "QDIGEST_REMINDER_EVERY_S",
               "QDIGEST_MESSAGE_LIMIT", "_qdigest"}

BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)
URL = "http://api:8000/api/v1/internal/quarantine/digest"
KEY = "internal-key"
ADMIN_CHANNEL = 777


def run(coro):
    return asyncio.run(coro)


def iso(t: float) -> str:
    return (BASE + timedelta(seconds=t)).isoformat()


def secs(s: str) -> float:
    return (datetime.fromisoformat(s) - BASE).total_seconds()


def rid(n: int) -> str:
    return f"{n:08x}-0000-4000-8000-{n:012x}"


def gid(n: int) -> str:
    return f"{n:08x}-1111-4000-8000-{n:012x}"


ID_LINE = re.compile(r"^([0-9a-f]{8}-0000-4000-8000-[0-9a-f]{12}) (ffa|team) (\S+) (\S+) "
                     r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})$")


def ids_in(content: str) -> list:
    return [m.group(1) for m in (ID_LINE.match(ln) for ln in content.split("\n")) if m]


# ── fakes ──────────────────────────────────────────────────────────────────

class Clock:
    def __init__(self, t=0.0):
        self.t = float(t)

    def advance(self, dt):
        self.t += dt


class _AllowedMentions:
    def __init__(self, **kw):
        self.kw = kw

    @classmethod
    def none(cls):
        return cls(none=True)


class _HTTPException(Exception):
    pass


class _NotFound(Exception):
    pass


FAKE_DISCORD = types.SimpleNamespace(AllowedMentions=_AllowedMentions, HTTPException=_HTTPException,
                                     NotFound=_NotFound, Forbidden=_HTTPException)
FAKE_AIOHTTP = types.SimpleNamespace(ClientTimeout=lambda **kw: kw)


class FakeD1:
    """The digest feed's protocol over rows that carry a created_at and a
    commit time: a request sees the rows committed by its own start (tau); a
    first request fixes hw = tau and carries the totals; a later one must
    send hw, after_at and after_id together. Each page advances the clock."""

    def __init__(self, clock, page_size=500, page_cost=0.5, cap=40):
        self.clock, self.page_size, self.page_cost, self.cap = clock, page_size, page_cost, cap
        self.rows, self.log, self.fail, self.hooks, self.capped = {}, [], set(), [], False

    def add(self, n, created, commit=None, mode="ffa", group=1, family="F3a"):
        r = {"id": rid(n), "mode": mode, "group": gid(group) if group is not None else None, "family": family,
             "created": float(created), "commit": float(created if commit is None else commit),
             "status": "pending"}
        self.rows[r["id"]] = r
        return r["id"]

    @staticmethod
    def _key(r):
        return (secs(iso(r["created"])), r["id"])

    def get(self, url, params=None, headers=None, timeout=None):
        assert url == URL, url
        assert headers == {"X-Internal-Key": KEY}, headers
        assert timeout == {"total": 45}, timeout
        return _Resp(self, dict(params or {}))

    def totals(self, visible):
        groups = Counter((r["mode"], r["group"]) for r in visible if r["group"] is not None)
        oldest = min(visible, key=self._key) if visible else None
        return {"pending": len(visible), "by_mode": dict(Counter(r["mode"] for r in visible)),
                "groups": len(groups), "quota": 50,
                "at_quota": [{"mode": m, "group": g, "pending": n} for (m, g), n in sorted(groups.items()) if n >= 50],
                "oldest": None if oldest is None else {"id": oldest["id"], "mode": oldest["mode"],
                                                       "group": oldest["group"], "created_at": iso(oldest["created"])}}

    def serve(self, tau, params):
        n = len(self.log) + 1
        for hook in list(self.hooks):
            hook(n, tau)
        if n > self.cap:
            self.capped = True
            return 599, {}
        if n in self.fail:
            return 503, {"detail": "unavailable"}
        visible = [r for r in self.rows.values() if r["commit"] <= tau and r["status"] == "pending"]
        first = not params
        if first:
            hw = tau
        else:
            if set(params) != {"hw", "after_at", "after_id"}:
                return 422, {"detail": "a later page needs hw, after_at and after_id together"}
            hw = secs(params["hw"])
            after = (secs(params["after_at"]), params["after_id"])
        cohort = sorted((r for r in visible if secs(iso(r["created"])) <= hw), key=self._key)
        if not first:
            cohort = [r for r in cohort if self._key(r) > after]
        page = cohort[:self.page_size]
        body = {"hw": iso(hw), "page_size": self.page_size,
                "rows": [{"id": r["id"], "mode": r["mode"], "group": r["group"], "family": r["family"],
                          "created_at": iso(r["created"])} for r in page]}
        if first:
            body["totals"] = self.totals(visible)
        return 200, body


class _Resp:
    def __init__(self, d1, params):
        self.d1, self.params = d1, params

    async def __aenter__(self):
        d1 = self.d1
        tau = d1.clock.t
        self.status, self.body = d1.serve(tau, self.params)
        d1.clock.advance(d1.page_cost)
        d1.log.append({"start": tau, "end": d1.clock.t, "params": self.params, "status": self.status,
                       "ids": [r.get("id") for r in self.body.get("rows", [])]})
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self.body


class FakeChannel:
    """#scr-admin: each send costs `cost` seconds of the fake clock; the
    attempts numbered in `reject` are refused, as is any content over 2,000
    characters (Discord's limit)."""

    def __init__(self, clock, cost=0.0, reject=()):
        self.clock, self.cost, self.reject = clock, cost, set(reject)
        self.attempts, self.accepted = 0, []

    async def send(self, content, **kw):
        self.attempts += 1
        assert isinstance(kw.get("allowed_mentions"), _AllowedMentions) and kw["allowed_mentions"].kw == {"none": True}
        self.clock.advance(self.cost)
        if self.attempts in self.reject:
            raise _HTTPException(f"attempt {self.attempts} rejected")
        if len(content) > 2000:
            raise _HTTPException("content longer than 2000 characters")
        self.accepted.append((self.clock.t, content))


class FakeBot:
    def __init__(self, channel):
        self.channel = channel

    def get_channel(self, cid):
        return self.channel if cid == ADMIN_CHANNEL else None

    async def fetch_channel(self, cid):
        raise _NotFound(str(cid))


def _lift():
    picked, seen = [], set()
    for node in TREE.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in WANT_ASSIGN:
                    picked.append(node)
                    seen.add(t.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in WANT_FUNC:
            fn = copy.deepcopy(node)
            fn.decorator_list = []                     # @tasks.loop is the harness's; the schedule is modelled
            picked.append(fn)
            seen.add(node.name)
    assert seen == WANT_FUNC | WANT_ASSIGN, (WANT_FUNC | WANT_ASSIGN) - seen
    return picked


def make(clock, d1, channel, admin_channel=ADMIN_CHANNEL):
    """A fresh namespace per test: the lifted digest plus the module globals
    it reaches for. The digest state (_qdigest) is lifted fresh each time."""
    out = []

    async def sleep(s):
        clock.advance(s)

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            v = BASE + timedelta(seconds=clock.t)
            return v if tz is None else v.astimezone(tz)

    ns = {"discord": FAKE_DISCORD, "aiohttp": FAKE_AIOHTTP, "bot": FakeBot(channel), "http_session": d1,
          "API_SECRET_KEY": KEY, "API_BASE_URL": "http://api:8000", "ADMIN_CHANNEL_ID": admin_channel,
          "time": types.SimpleNamespace(monotonic=lambda: clock.t), "asyncio": types.SimpleNamespace(sleep=sleep),
          "datetime": FakeDatetime, "timezone": timezone, "timedelta": timedelta,
          "print": lambda *a, **k: out.append(" ".join(str(x) for x in a))}
    exec(compile(ast.Module(body=_lift(), type_ignores=[]), SRC, "exec"), ns)
    ns["_out"] = out
    return ns


async def run_loop(ns, clock, d1, until_t, stop=None):
    """discord.py's schedule for tasks.loop(seconds=60): one iteration at a
    time, the next starting at max(this start + 60 s, this end)."""
    recs, start = [], clock.t
    while start <= until_t:
        clock.t = max(clock.t, start)
        begin, n0 = clock.t, len(d1.log)
        await ns["poll_quarantine_digest"]()
        reqs = d1.log[n0:]
        recs.append({"start": begin, "pass_end": reqs[-1]["end"] if reqs else begin, "end": clock.t,
                     "reqs": reqs})
        if stop is not None and stop():
            break
        start = max(begin + 60.0, clock.t)
    return recs


def posted_ids(channel):
    out = []
    for _, content in channel.accepted:
        out.extend(ids_in(content))
    return out


def accepted_at(channel, qid):
    return next((t for t, content in channel.accepted if qid in ids_in(content)), None)


def settle_state(ns, clock, announced=(), quota_named=()):
    """A process that has run for a while: online line posted, no reminder
    due, the window open, and these ids and quota groups already listed."""
    st = ns["_qdigest"]
    st["announced"] |= set(announced)
    st["quota_named"] |= set(quota_named)
    st["online_posted"], st["first_pass_logged"] = True, True
    st["channel_logged"], st["first_post_logged"] = True, True
    st["round_at"], st["reminder_at"] = clock.t - 10_000.0, clock.t


def bound(t, recs):
    """3.4 B4's bound from the measured passes and posting steps:
    t + 600 s + 2(max(60 s, D + S) + D) + S."""
    d = max(r["pass_end"] - r["start"] for r in recs)
    s = max(r["end"] - r["pass_end"] for r in recs)
    return t + 600.0 + 2 * (max(60.0, d + s) + d) + s, d, s


# ── reachability: the lifted loop is the scheduled one (K13g, K17) ─────────

def test_the_digest_loop_is_a_60s_task_started_in_on_ready():
    fn = next(n for n in TREE.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "poll_quarantine_digest")
    assert [ast.unparse(d) for d in fn.decorator_list] == ["tasks.loop(seconds=60)"]
    on_ready = next(n for n in TREE.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_ready")
    starts = [s for s in on_ready.body if isinstance(s, ast.If)
              and ast.unparse(s.test) == "not poll_quarantine_digest.is_running()"]
    assert len(starts) == 1
    assert [ast.unparse(b) for b in starts[0].body] == ["poll_quarantine_digest.start()"]


# ── K17: activation (W29) ──────────────────────────────────────────────────

def test_k17_one_run_logs_the_three_health_lines_and_posts_the_online_line():
    clock = Clock(1000.0)
    d1, ch = FakeD1(clock), FakeChannel(clock)
    for n, created, group in ((1, 100.0, 1), (2, 200.0, 1), (3, 300.0, 2)):
        d1.add(n, created, group=group)
    ns = make(clock, d1, ch)
    run(ns["poll_quarantine_digest"]())
    assert [ln for ln in ns["_out"] if ln.startswith("[QDIGEST]")] == [
        "[QDIGEST] first pass complete: 3 pending in 2 groups",
        "[QDIGEST] admin channel resolved",
        "[QDIGEST] first post accepted"]
    assert ch.accepted[0][1] == "quarantine digest online: 3 pending, oldest 2026-09-01 00:01:40"
    assert sorted(posted_ids(ch)) == [rid(1), rid(2), rid(3)]


def test_the_loop_skips_when_the_admin_channel_is_zero():
    clock = Clock(1000.0)
    d1, ch = FakeD1(clock), FakeChannel(clock)
    d1.add(1, 100.0)
    ns = make(clock, d1, ch, admin_channel=0)
    run(ns["poll_quarantine_digest"]())
    assert d1.log == [] and ch.attempts == 0


def test_the_loop_body_is_guarded():
    clock = Clock(1000.0)
    d1, ch = FakeD1(clock), FakeChannel(clock)
    d1.serve = lambda tau, params: (200, {"hw": iso(tau), "page_size": 500, "rows": [{"no": "id"}], "totals": None})
    ns = make(clock, d1, ch)
    run(ns["poll_quarantine_digest"]())
    assert any(ln.startswith("[QDIGEST] iteration error: KeyError") for ln in ns["_out"])


# ── K13 (a): W19, c on page 2 ───────────────────────────────────────────────

def test_k13a_w19_c_is_announced_by_the_pass_that_reads_page_2():
    clock = Clock(10_000.0)
    d1, ch = FakeD1(clock), FakeChannel(clock)
    flood = [d1.add(n, created=float(n), group=1 + n // 50) for n in range(600)]      # 12 lobbies at 50
    c = d1.add(1000, created=9_000.0, group=13)                                         # c commits at t = 9000
    d1.hooks.append(lambda n, tau: d1.add(5000 + n, created=tau + 0.25, group=20 + n))  # arrivals during the pass
    ns = make(clock, d1, ch)
    settle_state(ns, clock, announced=flood, quota_named={("ffa", gid(g)) for g in range(1, 13)})
    run(ns["poll_quarantine_digest"]())
    assert [len(r["ids"]) for r in d1.log] == [500, 101] and c in d1.log[1]["ids"]
    assert posted_ids(ch) == [c]
    assert c in ns["_qdigest"]["announced"]


# ── K13 (b): W20, a capture committed late with an early created_at ─────────

def test_k13b_w20_a_late_commit_is_read_by_the_first_pass_after_it_and_posted_within_the_bound():
    clock = Clock(905.0)
    d1, ch = FakeD1(clock), FakeChannel(clock, cost=0.5)
    early = [d1.add(k, created=100.0 + 10.0 * k, group=1) for k in range(1, 81)]     # created 110..900
    t_commit = 1000.0
    c = d1.add(999, created=100.0, commit=t_commit, group=1)       # waited 15 min on its lock, created at t0
    ns = make(clock, d1, ch)
    recs = run(run_loop(ns, clock, d1, until_t=6000.0, stop=lambda: c in posted_ids(ch)))
    assert set(early) <= set(posted_ids(ch))
    first_after = next(r for r in recs if r["reqs"] and r["reqs"][0]["start"] >= t_commit)
    assert c in [i for q in first_after["reqs"] for i in q["ids"]]
    at_ = accepted_at(ch, c)
    b, _, _ = bound(t_commit, recs)
    assert at_ is not None and at_ <= b, (at_, b)
    assert posted_ids(ch).count(c) == 1


# ── K13 (c), K13f: W21, a failed message ─────────────────────────────────────

def _w21(reject):
    clock = Clock(5000.0)
    d1, ch = FakeD1(clock), FakeChannel(clock, reject=reject)
    ids = [d1.add(n, created=float(n), group=1) for n in range(1, 46)]    # 45 lines: three messages
    ns = make(clock, d1, ch)
    settle_state(ns, clock)
    return clock, d1, ch, ids, ns


def test_k13c_w21_message_2_rejected_leaves_its_ids_and_message_3s_unannounced():
    clock, d1, ch, ids, ns = _w21(reject={2})
    st = ns["_qdigest"]
    start = clock.t
    run(ns["poll_quarantine_digest"]())
    assert ch.attempts == 2 and len(ch.accepted) == 1
    first = ids_in(ch.accepted[0][1])
    assert first and st["announced"] == set(first)
    rest = [i for i in ids if i not in first]
    assert len(rest) > 19, "the unannounced lines fit one message: the fixture never reaches a message 3"
    assert st["round_at"] == start + d1.page_cost           # the window was used: this round's start
    recs = run(run_loop(ns, clock, d1, until_t=clock.t + 1300.0, stop=lambda: set(ids) <= st["announced"]))
    assert sorted(posted_ids(ch)) == sorted(ids)            # each id exactly once
    second = next(t for t, content in ch.accepted[1:] if ids_in(content))
    assert second - ch.accepted[0][0] >= 600.0 - 1.0


def test_k13c_w21_variant_message_1_rejected_marks_nothing_and_retries_at_the_next_pass_end():
    clock, d1, ch, ids, ns = _w21(reject={1})
    st = ns["_qdigest"]
    window_before = st["round_at"]
    run(ns["poll_quarantine_digest"]())
    assert ch.accepted == [] and st["announced"] == set()
    assert st["round_at"] == window_before                  # the window is not used
    clock.advance(60.0)
    run(ns["poll_quarantine_digest"]())
    assert sorted(posted_ids(ch)) == sorted(ids) and st["announced"] == set(ids)


def test_k13f_w19_cold_restart_every_line_whole_in_exactly_one_accepted_message():
    clock = Clock(10_000.0)
    d1, ch = FakeD1(clock), FakeChannel(clock)
    ids = [d1.add(n, created=float(n), group=1 + n // 50) for n in range(601)]
    ns = make(clock, d1, ch)
    run(ns["poll_quarantine_digest"]())
    st = ns["_qdigest"]
    assert all(len(content) <= 2000 for _, content in ch.accepted)
    listed = posted_ids(ch)
    assert sorted(listed) == sorted(ids) and len(listed) == len(set(listed))
    quota_lines = []
    for _, content in ch.accepted[1:]:
        for line in content.split("\n")[1 if content.startswith("quarantined reports") else 0:]:
            assert ID_LINE.match(line) or line.startswith("group at quota: "), line
            if line.startswith("group at quota: "):
                quota_lines.append(line)
    assert sorted(quota_lines) == sorted(
        f"group at quota: ffa {gid(g)} holds 50 pending reports; its next refused report is not kept" for g in range(1, 13))
    assert st["announced"] == set(ids)
    assert st["quota_named"] == {("ffa", gid(g)) for g in range(1, 13)}
    assert len(ch.accepted) >= 30


def test_k13f_cold_restart_marks_exactly_the_ids_of_accepted_messages():
    clock = Clock(10_000.0)
    d1, ch = FakeD1(clock), FakeChannel(clock, reject={9})     # the online line, then round messages 1-7, then 8 fails
    ids = [d1.add(n, created=float(n), group=1 + n // 50) for n in range(601)]
    ns = make(clock, d1, ch)
    run(ns["poll_quarantine_digest"]())
    st = ns["_qdigest"]
    assert ch.attempts == 9 and len(ch.accepted) == 8
    assert st["announced"] == set(posted_ids(ch)) and 0 < len(st["announced"]) < len(ids)


# ── K13 (d): pruning after a complete pass only ──────────────────────────────

def test_k13d_a_reviewed_row_leaves_the_announced_set_after_a_complete_pass():
    clock = Clock(1000.0)
    d1, ch = FakeD1(clock), FakeChannel(clock)
    a, b, c = (d1.add(n, created=float(n)) for n in (1, 2, 3))
    ns = make(clock, d1, ch)
    run(ns["poll_quarantine_digest"]())
    st = ns["_qdigest"]
    assert st["announced"] == {a, b, c}
    d1.rows[b]["status"] = "discarded"
    clock.advance(60.0)
    run(ns["poll_quarantine_digest"]())
    assert st["announced"] == {a, c}
    d1.rows[c]["status"] = "accepted"
    d1.fail.add(len(d1.log) + 1)                            # the next pass's first page fails: incomplete
    clock.advance(60.0)
    run(ns["poll_quarantine_digest"]())
    assert st["announced"] == {a, c}                        # nothing pruned by an incomplete pass


# ── K13e (bot half): the pass is finite over a moving tail (W28) ─────────────

def test_k13e_w28_the_pass_ends_within_its_page_bound():
    clock = Clock(10_000.0)
    d1, ch = FakeD1(clock, cap=20), FakeChannel(clock)
    for n in range(900):
        d1.add(n, created=float(n), group=1 + n // 40)
    hw = {}

    def tail(n, tau):
        if n == 1:
            hw["t"] = tau
            return
        for k in range(500):                                # 500 new captures commit between requests
            d1.add(100_000 * n + k, created=tau, group=900 + n)
        if n == 2:
            for k in range(30):                             # in flight at hw: begun before it, committed now
                d1.add(90_000 + k, created=hw["t"] - 1.0, commit=tau, group=800)

    d1.hooks.append(tail)
    ns = make(clock, d1, ch)
    run(ns["poll_quarantine_digest"]())
    assert not d1.capped
    assert len(d1.log) <= math.ceil((900 + 30) / 500) + 1, len(d1.log)
    assert [len(r["ids"]) for r in d1.log] == [500, 430]
    assert all(r["status"] == 200 for r in d1.log)


# ── K13g: the loop premise, and a capture during a posting round (W33) ──────

def test_k13g_i_one_iteration_lasts_exactly_its_pass_plus_its_posting_step():
    fn = next(n for n in TREE.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "poll_quarantine_digest")
    assert [ast.unparse(d) for d in fn.decorator_list] == ["tasks.loop(seconds=60)"]
    clock = Clock(0.0)
    d1, ch = FakeD1(clock, page_cost=0.5), FakeChannel(clock, cost=19.5)
    for n in range(601):
        d1.add(n, created=-1000.0 + n, group=1 + n // 50)
    ns = make(clock, d1, ch)
    run(ns["poll_quarantine_digest"]())
    d = d1.log[-1]["end"] - d1.log[0]["start"]
    s = ch.attempts * 19.5
    assert (d, len(d1.log)) == (1.0, 2)
    assert clock.t == d + s, (clock.t, d, s)


def test_k13g_ii_w33_a_capture_committed_during_a_cold_round_is_posted_within_the_bound():
    clock = Clock(0.0)
    d1, ch = FakeD1(clock, page_cost=0.5), FakeChannel(clock, cost=19.5)
    for n in range(601):
        d1.add(n, created=-1000.0 + n, group=1 + n // 50)
    t = 6.0                                                 # e_k + 5 s, while round k is posting
    c = d1.add(9999, created=t, group=99)
    ns = make(clock, d1, ch)
    recs = run(run_loop(ns, clock, d1, until_t=6000.0, stop=lambda: c in posted_ids(ch)))
    assert recs[0]["pass_end"] == 1.0 and recs[0]["end"] > t + 60.0      # c commits inside round k
    assert len(recs) >= 2 and recs[1]["start"] == recs[0]["end"]          # D + S > 60 s: next start = this end
    at_ = accepted_at(ch, c)
    b, d, s = bound(t, recs)
    assert at_ is not None and at_ <= b, (at_, b, d, s)


# ── the 24 h reminder, and a group newly at quota ─────────────────────────────

def test_the_24h_reminder_goes_out_while_anything_is_pending():
    clock = Clock(1000.0)
    d1, ch = FakeD1(clock), FakeChannel(clock)
    d1.add(1, created=100.0)
    ns = make(clock, d1, ch)
    run(ns["poll_quarantine_digest"]())
    n0 = len(ch.accepted)
    clock.advance(86_400.0 - 1.0)
    run(ns["poll_quarantine_digest"]())
    assert len(ch.accepted) == n0
    clock.advance(2.0)
    run(ns["poll_quarantine_digest"]())
    assert ch.accepted[-1][1] == ("quarantine digest reminder: 1 pending in 1 groups, oldest 2026-09-01 "
                                  "00:01:40; 0 group(s) at quota")


def test_a_group_newly_at_quota_is_named_once():
    clock = Clock(1000.0)
    d1, ch = FakeD1(clock), FakeChannel(clock)
    for n in range(50):
        d1.add(n, created=float(n), group=7)
    ns = make(clock, d1, ch)
    settle_state(ns, clock)
    run(ns["poll_quarantine_digest"]())
    named = [ln for _, content in ch.accepted for ln in content.split("\n") if ln.startswith("group at quota: ")]
    assert named == [f"group at quota: ffa {gid(7)} holds 50 pending reports; its next refused report is not kept"]
    d1.add(500, created=900.0, group=8)
    clock.advance(700.0)
    run(ns["poll_quarantine_digest"]())
    named = [ln for _, content in ch.accepted for ln in content.split("\n") if ln.startswith("group at quota: ")]
    assert len(named) == 1 and rid(500) in posted_ids(ch)
