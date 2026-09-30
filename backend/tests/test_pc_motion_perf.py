"""Dance cards T44 `perf_gate_motion_load` (design S4.6, S8), run as a
MEASUREMENT whose values the lane notes record against the design's
estimates (build brief: T37, T44, T50 and RR15 are the acceptance gates).

The S4.6 load: a cold print-atlas derivation of the largest dance
(dance_robot, 120 frames, both sizes) running on the ONE motion worker --
a process of its own since finding S2F14, started before the baseline so
its start-up is outside both phases -- and two maximum uploads decoding on
the ONE decode worker. Under it, the static face renders that share the
API process -- pc_portrait's two-worker render pool, the path every static
face route takes -- keep their p95 within 10 % of the idle baseline, the
event loop's lag stays under 50 ms, and the resident sets grow by less than
192 MiB while the job runs: this process's growth plus the worker's whole
resident set, its idle footprint counted as growth too.

Mutation (must fail): the job run on the event loop (`in_motion_pool`
calling fn inline) -- the loop-lag bound fails. Control: the executor run,
this test as written. The frames are the seat's real robot capture when
PC_MOTION_CORPUS_DIR names the corpus, else the synthetic dancer. The
measurements are printed as one line (keep it with pytest -s) and carried
in every assertion's message.
"""
import asyncio
import math
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(HERE, "..", "api")
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import pc_face  # noqa: E402
import pc_motion as pcm  # noqa: E402
import pc_motion_fixtures as fx  # noqa: E402
import pc_portrait  # noqa: E402

STATIC_RISE_MAX = 0.10          # static p95 under load / idle p95 - 1
LOOP_LAG_MAX_S = 0.050          # the largest overshoot of a 10 ms sleep
JOB_RSS_MAX = 192 << 20         # resident-set growth while the job runs
BASELINE_RENDERS = 40
LOAD_RENDERS_MIN = 40
LAG_TICK_S = 0.010


def _rss_bytes(pid=None):
    """A process's resident set (Windows working set; Linux statm): this
    process's, or the one `pid` names."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class _Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        counters = _Counters()
        counters.cb = ctypes.sizeof(_Counters)
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        query = kernel32.K32GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]
        query.restype = wintypes.BOOL
        if pid is None:
            handle = kernel32.GetCurrentProcess()
        else:
            handle = kernel32.OpenProcess(0x1000 | 0x0010, False, int(pid))   # limited query, VM read
            if not handle:
                raise OSError("OpenProcess failed for %d" % pid)
        try:
            if not query(handle, ctypes.byref(counters), counters.cb):
                raise OSError("K32GetProcessMemoryInfo failed")
        finally:
            if pid is not None:
                kernel32.CloseHandle(handle)
        return int(counters.WorkingSetSize)
    with open("/proc/%s/statm" % ("self" if pid is None else int(pid))) as fh:
        return int(fh.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")


def _robot_container():
    root = os.environ.get("PC_MOTION_CORPUS_DIR")
    if root:
        for name in sorted(os.listdir(root)):
            if name.endswith(".scrmotion"):
                with open(os.path.join(root, name), "rb") as fh:
                    body = fh.read()
                if pcm.parse_container(body)[0]["dance"] == "dance_robot":
                    return body, "corpus"
    return fx.container("dance_robot", fx.smooth_frames(120)), "synthetic"


def _p95(values):
    ordered = sorted(values)
    return ordered[max(0, int(math.ceil(0.95 * len(ordered))) - 1)]


async def _render_once(still, serial):
    t0 = time.perf_counter()
    await pc_portrait.in_pool(pc_face.render_face, fx.spec(rating=1500 + serial % 400), {}, still, "card")
    return time.perf_counter() - t0


async def _lag_sampler(stop, out):
    while not stop.is_set():
        t0 = time.perf_counter()
        await asyncio.sleep(LAG_TICK_S)
        out.append(time.perf_counter() - t0 - LAG_TICK_S)


def _worker_pid():
    """The motion worker's process id, or None when no worker runs (the
    inline mutation never starts one)."""
    procs = getattr(pcm.motion_pool(), "_processes", None) or {}
    return next(iter(procs), None)


def _rss_sampler(stop, out, worker, errors):
    """This process's resident set plus the worker's, every 50 ms; a sample
    that cannot be read is counted in `errors`, never replaced by a guess."""
    while not stop.is_set():
        try:
            out.append(_rss_bytes() + (_rss_bytes(worker) if worker else 0))
        except OSError:
            errors.append(1)
        time.sleep(0.05)


async def _measure():
    body, source = _robot_container()
    header, frames = pcm.parse_container(body)
    still = fx.edge_still()
    await _render_once(still, 0)                                  # first-call costs outside both phases
    await pcm.in_motion_pool(fx.busy_renders, 0.0)                # the worker is up and has drawn once
    worker = _worker_pid()
    worker_base = _rss_bytes(worker) if worker else 0
    base = [await _render_once(still, k) for k in range(BASELINE_RENDERS)]

    lags, rss, rss_errors = [], [_rss_bytes()], []                # rss[0]: this process alone
    stop, rss_stop = asyncio.Event(), threading.Event()
    rss_thread = threading.Thread(target=_rss_sampler, args=(rss_stop, rss, worker, rss_errors), daemon=True)
    rss_thread.start()
    lag_task = asyncio.create_task(_lag_sampler(stop, lags))
    await asyncio.sleep(0.05)
    admission = pcm.DecodeAdmission()
    decodes = []
    for k in range(2):
        key = "t44-upload-%d" % k
        decodes.append(asyncio.create_task(
            pcm.decode_in_pool(admission, key, admission.try_claim(key), header, frames, 600.0)))
    t0 = time.perf_counter()
    job = asyncio.create_task(pcm.in_motion_pool(pcm.derive_atlases, fx.spec(), {}, body))
    await asyncio.sleep(0)
    load = []
    serial = 0
    while not job.done():
        serial += 1
        latency = await _render_once(still, serial)
        if not job.done():
            load.append(latency)
    card, tile = await job
    job_s = time.perf_counter() - t0
    for d in decodes:
        await d
    stop.set()
    await lag_task
    rss_stop.set()
    rss_thread.join(5)
    worker_after = _rss_bytes(worker) if worker else 0
    base_p95 = _p95(base)
    load_p95 = _p95(load) if load else float("inf")
    return {
        "source": source, "frames": len(frames), "job_s": job_s,
        "card_bytes": len(card) if card else 0, "tile_bytes": len(tile) if tile else 0,
        "base_n": len(base), "load_n": len(load),
        "base_p95_ms": base_p95 * 1000.0, "load_p95_ms": load_p95 * 1000.0,
        "rise": load_p95 / base_p95 - 1.0,
        "lag_max_ms": max(lags) * 1000.0 if lags else float("inf"), "lag_n": len(lags),
        "rss_growth_mib": (max(rss) - rss[0]) / float(1 << 20), "rss_errors": len(rss_errors),
        "worker_base_mib": worker_base / float(1 << 20), "worker_after_mib": worker_after / float(1 << 20),
    }


def test_perf_gate_motion_load():
    m = asyncio.run(_measure())
    line = ("[T44] source=%(source)s frames=%(frames)d job_s=%(job_s).1f card_bytes=%(card_bytes)d "
            "tile_bytes=%(tile_bytes)d base_n=%(base_n)d load_n=%(load_n)d base_p95_ms=%(base_p95_ms).1f "
            "load_p95_ms=%(load_p95_ms).1f rise_pct=%(rise_pct).1f lag_max_ms=%(lag_max_ms).1f "
            "lag_n=%(lag_n)d rss_growth_mib=%(rss_growth_mib).1f rss_errors=%(rss_errors)d "
            "worker_base_mib=%(worker_base_mib).1f worker_after_mib=%(worker_after_mib).1f") % dict(
                m, rise_pct=m["rise"] * 100.0)
    print(line)
    assert m["lag_max_ms"] < LOOP_LAG_MAX_S * 1000.0, line
    assert m["load_n"] >= LOAD_RENDERS_MIN, line
    assert m["rise"] < STATIC_RISE_MAX, line
    assert m["rss_errors"] == 0 and m["rss_growth_mib"] * (1 << 20) < JOB_RSS_MAX, line
