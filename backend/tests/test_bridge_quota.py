"""Quota + pacing tests for the YouTube chat bridge.

Why this file exists: R4 found `CHAT_QUOTA_PT_DAY` referenced but never
defined — the FIRST `_quota_spend()` call raised NameError, the outer loop
swallowed it, and the bridge silently relayed nothing. No test drove that
path, which is exactly how it escaped.

R5 then found the first version of this file only PARTIALLY load-bearing
(it never executed `_yt_get`, and it reimplemented the date rule instead of
calling production's). This version extracts and EXECUTES the real
`_yt_get` against a fake clock + fake session, and calls production's own
`_quota_day_valid`, so reverting any of the guards fails here.

Run: python backend/tests/test_bridge_quota.py
"""
import ast
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "discord_bot.py")
SRC = os.path.abspath(os.environ.get("SCR_BOT_SRC", SRC))

tree = ast.parse(open(SRC, encoding="utf-8").read())
fn = next((n for n in ast.walk(tree)
           if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
           and n.name == "youtube_chat_bridge"), None)
assert fn is not None, "youtube_chat_bridge not found"

WANT_ASSIGN = {"CHAT_QUOTA_PT_DAY", "API_MIN_GAP", "QUOTA_LEDGER_DIR",
               "QUOTA_LEDGER_PATH", "qledger", "pace"}
WANT_FUNC = {"_pt_day", "_quota_spend", "_quota_persist", "_quota_day_valid",
             "_yt_get"}
picked, seen_assign, seen_func = [], set(), set()
for node in fn.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id in WANT_ASSIGN:
                picked.append(node)
                seen_assign.add(t.id)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in WANT_FUNC:
        picked.append(node)
        seen_func.add(node.name)

missing_a = WANT_ASSIGN - seen_assign
missing_f = WANT_FUNC - seen_func
assert not missing_a, f"quota constants missing from the bridge: {missing_a}"
assert not missing_f, f"quota helpers missing from the bridge: {missing_f}"


class _FakeClock:
    """Monotonic stand-in; asyncio.sleep is patched to advance it, so the
    test measures the PACE without ever really sleeping."""

    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t


clock = _FakeClock()
slept = []


async def _fake_sleep(seconds):
    slept.append(seconds)
    clock.t += seconds


class _FakeResp:
    status = 200

    async def json(self):
        return {"items": []}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self):
        self.gets = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.gets.append(clock.t)
        return _FakeResp()


session = _FakeSession()


class _FakeTimeout:
    def __init__(self, total=None):
        pass


ns = {
    "os": os, "json": __import__("json"), "datetime": datetime,
    "timezone": timezone, "timedelta": timedelta, "print": print,
    "_faq_time": clock,                       # production reads monotonic here
    "asyncio": type("A", (), {"sleep": staticmethod(_fake_sleep)}),
    "aiohttp": type("H", (), {"ClientTimeout": _FakeTimeout}),
    "_gsession": lambda: session,
    "_access_token": lambda force=False: _immediate("tok"),
}


def _immediate(value):
    async def _c():
        return value
    return _c()


exec(compile(ast.fix_missing_locations(ast.Module(body=picked, type_ignores=[])),
             "<bridge-quota>", "exec"), ns)

spend = ns["_quota_spend"]
ledger = ns["qledger"]
cap = ns["CHAT_QUOTA_PT_DAY"]
gap = ns["API_MIN_GAP"]
day_valid = ns["_quota_day_valid"]
# Never touch a real ledger file from a test run (R5 f3).
ledger["persist_dead"] = True

# ── 1. The exact call the live path makes first — this is what NameError'd.
assert spend(1) is True, "first videos.list charge refused"
assert ledger["units"] == 1, ledger
assert spend(5) is True
assert ledger["units"] == 6, ledger

# ── 2. The cap stops polling and stays stopped for the PT day. The bound is
#      a LITERAL ceiling, so silently widening the production cap past the
#      project's headroom fails here (R5 f2). 8,000 of a DEDICATED 10,000-unit
#      project leaves 20% for retries and estimate error.
assert cap <= 8000, f"chat quota cap {cap} leaves too little project headroom"
ledger["units"] = cap
assert spend(5) is False, "cap did not stop polling"
assert spend(5) is False, "cap is not sticky within the day"

# ── 3. A PT day-roll re-arms it.
ledger["day"] = "1999-01-01"
assert spend(5) is True, "day roll did not re-arm polling"
assert ledger["units"] == 5, ledger

# ── 4. PRODUCTION's date predicate (not a copy of the rule).
for bad in ("garbage", "2026-13-01", "2026-1-1", "", None, 20260819, True):
    assert day_valid(bad) is False, f"invalid ledger date accepted: {bad!r}"
assert day_valid("2026-08-19") is True, "canonical date rejected"

# ── 5. The PRIMARY bound, executed: _yt_get must wait out API_MIN_GAP on
#      every attempt, including the FIRST of a fresh process (R5 f1 — a
#      restart loop that skips the initial wait defeats the whole bound).
assert gap > 0, "API_MIN_GAP must be positive"
started_at = clock.t
asyncio.get_event_loop().run_until_complete(
    ns["_yt_get"]("https://example/videos", {"id": "x"}))
assert slept and slept[0] >= gap - 0.001, (
    f"fresh process issued its first quota GET after only {slept[:1]}s — "
    "pace['last'] must seed from the current clock, not the distant past")
# The wait must precede the REQUEST, not merely happen somewhere in the
# call (R6 f2): _FakeSession stamps the clock at GET time, so a sleep moved
# after the request would show the GET landing at the un-advanced start.
assert session.gets[0] >= started_at + gap - 0.001, (
    f"first GET issued at t={session.gets[0]} but the pass started at "
    f"t={started_at} — the pace must be waited out BEFORE the request")
before = clock.t
asyncio.get_event_loop().run_until_complete(
    ns["_yt_get"]("https://example/liveChat", {"id": "x"}))
assert clock.t - before >= gap - 0.001, (
    f"second GET only {clock.t - before}s after the first (need {gap}s)")
assert session.gets[1] - session.gets[0] >= gap - 0.001, (
    f"consecutive GETs {session.gets[1] - session.gets[0]}s apart (need {gap}s)")
assert len(session.gets) == 2, session.gets

# ── 5b. The forced-401 retry is a SECOND quota-costing request and must be
#       paced too (R6 f2): a 401 that retried immediately would double the
#       day's worst case. One 401 then a 200.
class _Resp401(_FakeResp):
    status = 401


class _Flaky401Session(_FakeSession):
    def __init__(self):
        super().__init__()
        self.n = 0

    def get(self, url, params=None, headers=None, timeout=None):
        self.gets.append(clock.t)
        self.n += 1
        return _Resp401() if self.n == 1 else _FakeResp()


flaky = _Flaky401Session()
ns["_gsession"] = lambda: flaky
asyncio.get_event_loop().run_until_complete(
    ns["_yt_get"]("https://example/videos", {"id": "x"}))
assert len(flaky.gets) == 2, f"expected the 401 retry, got {flaky.gets}"
assert flaky.gets[1] - flaky.gets[0] >= gap - 0.001, (
    f"the 401 retry fired {flaky.gets[1] - flaky.gets[0]}s after the first "
    f"attempt (need {gap}s) — every attempt must pass the pace")

# ── 6. The two constants must stay COUPLED. Since the bridge moved to its
#      own Google project the pace is no longer a whole-day bound (at 15s a
#      24h day would allow ~28,800 units); the ledger cap is. So the
#      invariant that matters is: the day's budget, spent at this pace,
#      must still cover a realistic streaming session. Tightening the pace
#      without raising the cap — the change that would silently cut chat
#      off mid-stream — fails here.
MIN_COVERED_HOURS = 6.0
covered_hours = (cap / 5.0) * gap / 3600.0
assert covered_hours >= MIN_COVERED_HOURS, (
    f"cap={cap} at gap={gap}s covers only {covered_hours:.1f}h of chat "
    f"before the PT-day cap stops relaying (need >= {MIN_COVERED_HOURS}h) — "
    "raise CHAT_QUOTA_PT_DAY or loosen API_MIN_GAP")
# Blast radius is chat-only ONLY while the bridge has its own project; if
# these creds ever move back onto the broadcast's project, the pace must
# again bound the whole day on its own (see the QUOTA SAFETY note).
assert gap > 0, "API_MIN_GAP must be positive"

print(f"bridge quota path OK (cap={cap}, gap={gap}s, "
      f"covers ~{covered_hours:.1f}h of chat/day at 5 units/poll, "
      f"first-GET wait {slept[0]:.0f}s)")
