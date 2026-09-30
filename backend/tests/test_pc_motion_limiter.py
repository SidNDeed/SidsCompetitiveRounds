"""Dance cards: the limiter's motion buckets (design S2.7; section 12 M6) --
T8, extended with the M6 latch, and the prune horizon the 60 s bucket needs.

The middleware is called directly, on a clock of the test's own and on bucket
and latch tables of its own; nothing else of the app runs. Each test is one
named assertion; its mutation is planted by the lane's mutation runner and
the test's own passing case is the control (#391).
"""
import asyncio
import os
import sys
import types

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import main  # noqa: E402

UPLOAD = "/api/v1/pc/portrait/motion"
READ = "/api/v1/pc-face/motion"
ATLAS = "/api/v1/pc-face/motion/0b7d2f8e-3c4a-4c2a-9b1e-2f3a4b5c6d7e/0123456789abcdef/en/card.png"
FACE = "/api/v1/pc-face/0b7d2f8e-3c4a-4c2a-9b1e-2f3a4b5c6d7e/0123456789abcdef/en/card.png"
STILL = "/api/v1/pc/portrait"
SELECT = "/api/v1/pc/dance"
FAMILY = "/api/v1/pc/me"
INTERNAL = "/api/v1/internal/pc/motion/preview/ref/en.gif"


class _Clock:
    def __init__(self):
        self.t = 5000.0

    def monotonic(self):
        return self.t


class _Req:
    def __init__(self, path, host, headers):
        self.url = types.SimpleNamespace(path=path)
        self.client = types.SimpleNamespace(host=host)
        self.headers = headers


@pytest.fixture
def gate(monkeypatch):
    """(clock, hit): hit(path, host=..., key=None) -> 200 when the request
    reached the app, else the status the limiter answered."""
    clock = _Clock()
    monkeypatch.setattr(main, "_rl_time", clock)
    monkeypatch.setattr(main, "_RL_BUCKETS", main._rl_defaultdict(main._rl_deque))
    monkeypatch.setattr(main, "_RL_MOTION_LATCH", {})
    monkeypatch.setattr(main, "_RL_LAST_PRUNE", [clock.t])
    monkeypatch.setenv("API_SECRET_KEY", "limiter-test-key")
    passed = object()

    async def call_next(request):
        return passed

    def hit(path, host="10.8.0.1", key=None):
        headers = {"X-Internal-Key": key} if key else {}
        out = asyncio.run(main.rate_limit_gate(_Req(path, host, headers), call_next))
        return 200 if out is passed else out.status_code
    return clock, hit


def test_limiter_classifies_motion_paths(gate):
    """T8: the motion upload is 2 per 60 s on its own exact path, ahead of the
    family prefix; the per-visit read and the atlas share 60 per 10 s, ahead
    of the face prefix; the selection stays in the family bucket; internal
    routes bypass. Control: the still upload keeps 20 per 10 s and the face
    route 120 per 10 s."""
    clock, hit = gate
    assert [hit(UPLOAD) for _ in range(3)] == [200, 200, 429]
    assert hit(FAMILY) == 200 and hit(STILL) == 200      # other buckets untouched
    clock.t += 30
    assert hit(UPLOAD) in (429, 503)                     # the window is 60 s, not 10
    clock.t += 31
    assert hit(UPLOAD) == 200
    reads = [hit(READ if k % 2 else ATLAS, host="10.8.0.2") for k in range(61)]
    assert reads[:60] == [200] * 60 and reads[60] == 429
    assert hit(FACE, host="10.8.0.2") == 200             # the static faces keep their allowance
    fam = [hit(SELECT, host="10.8.0.3") for _ in range(90)]
    assert fam == [200] * 90
    assert hit(FAMILY, host="10.8.0.3") == 429           # the selection spent the family bucket
    assert all(hit(INTERNAL, host="10.8.0.4", key="limiter-test-key") == 200 for _ in range(300))
    assert hit(INTERNAL, host="10.8.0.4") == 403         # and without the key it is refused
    clock.t += 100
    still = [hit(STILL, host="10.8.0.5") for _ in range(21)]
    assert still == [200] * 20 + [429]
    faces = [hit(FACE, host="10.8.0.6") for _ in range(121)]
    assert faces == [200] * 120 + [429]


def test_motion_429_is_latched_per_address_and_bucket(gate):
    """M6: per address and motion bucket, the FIRST refusal is a 429 and
    every later refusal inside the 600 s latch is a 503 with Retry-After, so
    one address adds at most one jail-counted 429 per motion bucket per
    latch period however fast it retries. Another address and the other
    motion bucket latch on their own; past the latch a refusal is a 429
    again. Control: the still upload's bucket is not latched."""
    clock, hit = gate
    seen = []
    for _ in range(599):
        seen.append(hit(UPLOAD))
        clock.t += 1.0
    assert seen.count(429) == 1 and seen.count(503) > 500 and seen.count(200) >= 20
    reads = [hit(READ) for _ in range(70)]
    assert reads.count(429) == 1 and reads.count(503) == 9     # its own bucket, its own latch
    other = [hit(UPLOAD, host="10.8.1.9") for _ in range(4)]
    assert other == [200, 200, 429, 503]                       # another address, its own latch
    clock.t += 4.0                                             # past the first latch (set at +2 s, 600 s)
    again = [hit(UPLOAD) for _ in range(4)]
    first = again.index(429)                                   # refused again: a 429 first, re-latched
    assert all(s == 200 for s in again[:first]) and all(s == 503 for s in again[first + 1:])
    still = [hit(STILL, host="10.8.2.1") for _ in range(25)]
    assert still == [200] * 20 + [429] * 5


def test_the_prune_keeps_the_longest_window(gate):
    """The idle prune must not shorten the 60 s bucket: two motion uploads,
    a prune run 35 s later by any other request, and a third upload at 36 s
    is still refused. Control: at 61 s it is admitted."""
    clock, hit = gate
    assert hit(UPLOAD) == 200
    clock.t += 1
    assert hit(UPLOAD) == 200
    clock.t += 34
    main._RL_LAST_PRUNE[0] = clock.t - 61                      # the next admitted request prunes
    assert hit("/api/v1/leaderboard") == 200
    clock.t += 1
    assert hit(UPLOAD) in (429, 503)
    clock.t += 25
    assert hit(UPLOAD) == 200
