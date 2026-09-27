"""Dance cards: the motion pool, admission and the motion cache (design
S4.6, S4.7; section 12 H1, L8) -- T25, T26, T27 (with H1's extension), T53
and T62.

Each test is one named assertion; the mutation that must fail it is planted
by the lane's mutation runner and recorded in its log, and the test's own
passing case is the control (#391). Nothing here reads a database: the
route halves (the row read, the address the route keys a job to, the cache
instance main wires) are in the live route tests.
"""
import asyncio
import collections
import os
import re
import shutil
import sys
import threading
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(HERE, "..", "api")
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import pc_face  # noqa: E402
import pc_motion as pcm  # noqa: E402
import pc_motion_fixtures as fx  # noqa: E402
import pc_portrait  # noqa: E402

MIB = 1 << 20


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


async def settle(turns=20):
    """Let every ready callback run: the scheduler's pump, the jobs and the
    waiters all advance on loop turns, never on timers."""
    for _ in range(turns):
        await asyncio.sleep(0)


def gated(order, name, gate):
    """An async job that records its start and waits on `gate`."""
    async def go():
        order.append(name)
        await gate.wait()
        return name
    return go


# -- T25: the motion cache is its own ----------------------------------------------------

def test_motion_cache_separate(tmp_path):
    """T25 (S4.7): the motion cache tracks, evicts and expires `.gif` and
    `.png` under its own root and re-finds both after a restart; it is not
    the face cache's class. Control: the face cache's scan of a fixture tree
    and renderer_fp are the same before and after. Mutation: the motion
    cache as the static cache (its class)."""
    fp_before = pc_face.renderer_fingerprint()
    faces = tmp_path / "faces"
    (faces / "p" / "r" / "en").mkdir(parents=True)
    (faces / "p" / "r" / "en" / "card.png").write_bytes(b"p" * 100)
    (faces / "p" / "r" / "en" / "card.gif").write_bytes(b"g" * 100)
    static = pc_portrait.FaceCache(str(faces))
    static._scan()
    before = dict(static._sizes)
    assert before == {"p/r/en/card.png": 100}

    root = str(tmp_path / "motion")
    cache = pcm.MotionCache(root, cap_bytes=3000)
    assert not isinstance(cache, pc_portrait.FaceCache)
    cache.publish("gif/a/r/en/card.gif", b"g" * 1000)
    cache.publish("atlas/a/r/en/card.png", b"p" * 1000)
    assert cache.keys() == {"gif/a/r/en/card.gif", "atlas/a/r/en/card.png"}
    assert cache.read("gif/a/r/en/card.gif") == b"g" * 1000

    again = pcm.MotionCache(root, cap_bytes=3000)          # a restart re-finds both kinds
    assert again.keys() == {"gif/a/r/en/card.gif", "atlas/a/r/en/card.png"}
    again.read("atlas/a/r/en/card.png")                    # the png is now the newer
    again.publish("gif/b/r/en/card.gif", b"g" * 1000)
    again.publish("gif/c/r/en/card.gif", b"g" * 1000)      # over the cap: the oldest, a gif, goes
    assert "gif/a/r/en/card.gif" not in again.keys()
    assert not os.path.exists(again.path("gif/a/r/en/card.gif"))
    assert again.evicted == 1 and again.bytes_held() <= 3000
    gone = again.expire(max_age_s=-1.0)                    # everything is older than -1 s
    assert gone == 3 and again.keys() == set()

    static2 = pc_portrait.FaceCache(str(faces))
    static2._scan()
    assert static2._sizes == before
    assert pc_face.renderer_fingerprint() == fp_before


def test_motion_cache_root_survives_an_api_rebuild():
    """S4.7 in the api container (sitting 2 finding S2F2): the motion cache's
    own root, beside the face cache's, must be what the container gets and
    must outlive the container. docker-compose.yml passes PC_MOTION_CACHE_DIR
    to the api with the code's own default and mounts a named volume, declared
    at the top level, at that path -- the face cache's arrangement -- so an
    api rebuild neither empties the cache nor sends every viewed print back
    through the single motion worker. Mutations: the mapping removed, the
    mount removed, the volume undeclared, the mapping pointed at the face
    cache's root. Control: the shipped file."""
    with open(os.path.join(API, "main.py"), encoding="utf-8") as fh:
        main_src = fh.read()
    with open(os.path.join(HERE, "..", "docker-compose.yml"), encoding="utf-8") as fh:
        compose = fh.read()

    def code_default(key):
        found = re.findall(r'os\.getenv\(\s*"%s"\s*,\s*"([^"]+)"\s*\)' % key, main_src)
        assert len(found) == 1, (key, found)
        return found[0]

    root, face_root = code_default("PC_MOTION_CACHE_DIR"), code_default("PC_FACE_CACHE_DIR")
    assert root != face_root
    api = compose[compose.index("  api:"):compose.index("  bot:")]
    mapped = re.findall(r"^ {6}PC_MOTION_CACHE_DIR: *\$\{PC_MOTION_CACHE_DIR:-([^}]*)\} *$", api, re.M)
    assert mapped == [root], mapped
    mounts = re.findall(r"^ {6}- *([A-Za-z0-9][A-Za-z0-9_.-]*):(/[^\s:]*) *$", api, re.M)
    at_root = [name for name, path in mounts if path == root]
    assert len(at_root) == 1, mounts
    assert (at_root[0], face_root) not in mounts and ("pc-faces", face_root) in mounts
    top = compose[compose.index("\nvolumes:"):]
    assert re.search(r"^  %s: *$" % re.escape(at_root[0]), top, re.M), (at_root, top)


# -- T26: the motion worker never holds a static render --------------------------------

def busy_renders(stop, seconds):
    """CPU work on the motion worker: real faces until `stop` or `seconds`."""
    end = time.monotonic() + seconds
    n = 0
    while not stop.is_set() and time.monotonic() < end:
        pc_face.render_face(fx.spec(), {}, None, "card")
        n += 1
    return n


def test_motion_pool_isolation():
    """T26 (S4.6): a static face renders within its budget while the motion
    worker is busy -- two derivations in flight, the second queued behind the
    first on the ONE motion worker. Control: the idle baseline. Mutation:
    motion jobs submitted to the static pool (both static workers then held)."""
    assert pcm.MOTION_POOL is not pc_portrait.POOL and pcm.MOTION_POOL._max_workers == 1

    async def scenario():
        spec = fx.spec(band="epic")
        await pc_portrait.in_pool(pc_face.render_face, spec, {}, None, "card")   # warm fonts
        t0 = time.perf_counter()
        await pc_portrait.in_pool(pc_face.render_face, spec, {}, None, "card")
        idle = time.perf_counter() - t0
        stop = threading.Event()
        busy = [asyncio.ensure_future(pcm.in_motion_pool(busy_renders, stop, 6.0)) for _ in range(2)]
        await asyncio.sleep(0.3)
        t0 = time.perf_counter()
        await pc_portrait.in_pool(pc_face.render_face, spec, {}, None, "card")
        loaded = time.perf_counter() - t0
        stop.set()
        await asyncio.gather(*busy)
        return idle, loaded

    idle, loaded = asyncio.run(scenario())
    assert loaded < 2.0 * idle + 0.5, (idle, loaded)


# -- T27: the admission bound (H1) ----------------------------------------------------------

def test_motion_queue_bound():
    """T27 (S4.6, H1): sixteen jobs pending or running are admitted; the
    seventeenth is refused at once (MotionBusy, the route's 503 motion_busy)
    and nothing is enqueued; a third job from one address is refused while
    the global bound has room; a join of a key in flight takes no permit;
    the address permit is held until the job exits -- not when it starts and
    not when a waiter stops waiting. Control: sixteen accepted. Mutations:
    no global bound; no per-address bound; the permit released at the job's
    start; a join that takes a permit."""
    async def scenario():
        sched = pcm.MotionScheduler()
        gate = asyncio.Event()
        order = []
        futs = [sched.submit("k%d" % i, "10.0.0.%d" % (i // 2), gated(order, i, gate)) for i in range(16)]
        assert sched.total() == 16
        with pytest.raises(pcm.MotionBusy):
            sched.submit("k16", "10.0.1.1", gated(order, 16, gate))
        assert sched.total() == 16 and sched.held("10.0.1.1") == 0
        gate.set()
        assert await asyncio.gather(*futs) == list(range(16))
        assert sched.total() == 0 and not sched._inflight

        # per address, with the global bound far away
        sched = pcm.MotionScheduler()
        gate = asyncio.Event()
        a1 = sched.submit("a1", "A", gated(order, "a1", gate))
        a2 = sched.submit("a2", "A", gated(order, "a2", gate))
        await settle()                                  # a1 has started
        assert order[-1] == "a1" and sched.held("A") == 2
        with pytest.raises(pcm.MotionBusy):
            sched.submit("a3", "A", gated(order, "a3", gate))   # one running, one waiting: still two
        # a join takes no permit, for its own address or the caller's
        assert sched.submit("a1", "B", gated(order, "x", gate)) is a1
        assert sched.held("B") == 0 and sched.held("A") == 2 and sched.total() == 2
        # a waiter that stops waiting releases nothing
        assert await pcm.await_job(a1, 0.05) is None
        assert not a1.cancelled() and sched.held("A") == 2
        gate.set()
        assert await pcm.await_job(a1, 5) == "a1" and await pcm.await_job(a2, 5) == "a2"
        assert sched.held("A") == 0 and sched.total() == 0
        sched.submit("a3", "A", gated(order, "a3", gate))   # the permits are back
    asyncio.run(scenario())


def test_motion_admission_fair():
    """T27 extended (H1): address queues are served round-robin -- an address
    that still has work goes behind every address already waiting -- so
    address B's job completes while address A continuously refills its two
    permits. Control: the fair order and B's completion. Mutations: one FIFO
    queue for every address (the order); no per-address bound (A takes every
    slot and B is refused)."""
    async def order_case():
        sched = pcm.MotionScheduler()
        gate = asyncio.Event()
        gate.set()
        order = []
        futs = [sched.submit(name, addr, gated(order, name, gate))
                for name, addr in (("a1", "A"), ("a2", "A"), ("c1", "C"), ("c2", "C"), ("b1", "B"))]
        await asyncio.gather(*futs)
        return order

    assert asyncio.run(order_case()) == ["a1", "c1", "b1", "a2", "c2"]

    async def refill_case():
        sched = pcm.MotionScheduler()
        started = []
        tokens = asyncio.Queue()                        # one token lets the running job finish

        def job(name):
            async def go():
                started.append(name)
                await tokens.get()
                return name
            return go

        submitted = []

        async def address_a():
            """A submits another job whenever one of its permits is free."""
            while True:
                try:
                    name = "a%d" % len(submitted)
                    sched.submit(name, "A", job(name))
                    submitted.append(name)
                except pcm.MotionBusy:
                    await asyncio.sleep(0)

        refiller = asyncio.ensure_future(address_a())
        await settle()
        assert sched.held("A") == 2 and len(submitted) == 2
        for _ in range(4):                              # A's jobs finish and A refills each time
            tokens.put_nowait(True)
            await settle()
            assert sched.held("A") == 2
        admitted_at, a_at_admission = len(started), len(submitted)
        b = sched.submit("b1", "B", job("b1"))          # never MotionBusy: B has its own permits
        for _ in range(6):
            if b.done():
                break
            tokens.put_nowait(True)
            await settle()
        assert b.done() and b.result() == "b1"
        refiller.cancel()
        return started, admitted_at, len(submitted) - a_at_admission

    started, admitted_at, a_refills = asyncio.run(refill_case())
    b_at = started.index("b1")
    assert b_at - admitted_at <= 1, (admitted_at, b_at, started)   # only A's queued job starts first
    assert a_refills >= 2, "A kept refilling while B waited"


# -- T53: the job deadline --------------------------------------------------------------------

def test_motion_job_deadline():
    """T53 (S4.6): a job whose frame renders run past the 120 s deadline ends
    at the step that noticed -- one step over at most -- and frees the
    worker; its key answers failed for 10 minutes from memory. Control: a
    fast job completes. Mutation: the deadline checked only at the job's
    end."""
    clock = Clock()
    renders = []

    def slow(spec, labels, png, size):
        renders.append(size)
        clock.t += 70.0
        return fx.fake_render(spec, labels, png, size)

    body = fx.container("dance_bounce", fx.smooth_frames(80))
    with pytest.raises(pcm.MotionDeadline):
        pcm.derive_atlases(fx.spec(), {}, body, deadline=clock.t + pcm.JOB_DEADLINE_S, clock=clock, render=slow)
    assert renders == ["card", "tile"], renders       # 70 s, then 140 s: stopped at the second step
    renders.clear()
    with pytest.raises(pcm.MotionDeadline):
        pcm.derive_preview_gif(fx.spec(), {}, fx.edge_still(), body, deadline=clock.t + pcm.JOB_DEADLINE_S,
                               clock=clock, render=slow)
    assert renders == ["card", "card"], renders       # the static face, then frame 0

    async def scenario():
        sched = pcm.MotionScheduler(clock=clock)

        async def job():
            return await pcm.in_motion_pool(
                lambda: pcm.derive_atlases(fx.spec(), {}, body, deadline=clock.t + pcm.JOB_DEADLINE_S,
                                           clock=clock, render=slow))
        out = await sched.submit("atlas/x/r/en", "A", job)
        assert out == ("failed", "MotionDeadline") and sched.held("A") == 0
        left = sched.failed_for("atlas/x/r/en")
        assert 0 < left <= pcm.FAILED_HOLD_S == 600.0
        clock.t += pcm.FAILED_HOLD_S + 1
        assert sched.failed_for("atlas/x/r/en") == 0
        # control: the worker is free and a fast job completes
        return await pcm.in_motion_pool(lambda: pcm.derive_atlases(
            fx.spec(), {}, body, deadline=clock.t + pcm.JOB_DEADLINE_S, clock=clock, render=fx.fake_render))

    card, tile = asyncio.run(scenario())
    assert card is not None and tile is not None


# -- T62: the cache churn gate (L8) -------------------------------------------------------------

def churn(cache, hot_keys, cold_per_cycle, cycles, size):
    """Request every hot key `cycles` times, round-robin, with a stream of
    one-off cold keys between them; a miss derives (publishes) the key.
    Returns {key: derivations}."""
    derived = collections.Counter()
    payload = b"m" * size

    def request(key):
        if cache.read(key) is None:
            derived[key] += 1
            cache.publish(key, payload)

    step = max(1, len(hot_keys) // max(1, cold_per_cycle))
    for cycle in range(cycles):
        for i, key in enumerate(hot_keys):
            request(key)
            if cold_per_cycle and i % step == 0:
                request("atlas/cold%d-%d/%s/en/card.png" % (cycle, i, "c" * 16))
    return derived


def atlas_keys(n, size="card"):
    return ["atlas/%08d-0000-4000-8000-000000000000/%s/en/%s.png" % (i, "a" * 16, size) for i in range(n)]


def test_motion_cache_churn(tmp_path):
    """T62 (S4.7, L8): with a working set of distinct print/locale/size keys
    ABOVE the 1 GiB cap (320 atlases of 4 MiB, 1.25 GiB), every key requested
    within the load window stays warm: a hot set of 230 keys (920 MiB)
    requested three times round-robin, with 92 MiB of one-off keys between
    them each cycle, is derived once and never again, while the cap evicts
    the cold remainder. Control: a working set under the cap evicts
    nothing. Mutation: the effective cap shrunk (768 MiB), so eviction
    reaches the hot set mid-window."""
    try:
        churn_gate(tmp_path)
    finally:
        shutil.rmtree(str(tmp_path), ignore_errors=True)     # 1 GiB of scratch goes with the test


def churn_gate(tmp_path):
    size = 4 * MIB
    control = pcm.MotionCache(str(tmp_path / "control"))
    under = atlas_keys(100)                             # 400 MiB
    derived = churn(control, under, 0, 2, size)
    assert control.evicted == 0 and all(derived[k] == 1 for k in under)
    for key in under:
        control.forget(key)

    cache = pcm.MotionCache(str(tmp_path / "churn"))
    assert cache.cap == 1 << 30
    working = atlas_keys(320)                           # 1.25 GiB of distinct keys
    fill = churn(cache, working, 0, 1, size)
    assert all(fill[k] == 1 for k in working)
    evicted_in_fill = cache.evicted
    assert evicted_in_fill >= 64 and cache.bytes_held() <= cache.cap
    hot = working[-230:]
    window = churn(cache, hot, 23, 3, size)
    rederived = {k: n for k, n in window.items() if k in set(hot)}
    assert rederived == {}, sorted(rederived.items())[:5]
    assert cache.evicted > evicted_in_fill and cache.bytes_held() <= cache.cap
