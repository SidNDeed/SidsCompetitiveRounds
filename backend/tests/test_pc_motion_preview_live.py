"""Dance cards: the /card motion preview GIF against a real PostgreSQL
(design S6.2, S4.5; section 12 L5, L6) -- T33, T60's GIF half and T61's
fetch half.

Each test is one named assertion; the mutation that must fail it is planted
by the lane's mutation runner and recorded in its log, and the test's own
passing case is the control (#391). The internal key and the HMAC key are
random test values, the admin check and the strict session check are
replaced, and every player is synthetic: a subject's id sits in the
individual SteamID64 range the pool word admits, above every id the other
live modules mint. The motion cache is a per-test directory and the
scheduler a fresh one per test; a job derives on the motion worker process
with the fixtures' fast stand-in for the renderer.
"""
import os
import sys
import time
import uuid

import pytest
from sqlalchemy import text

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import dance_pg_harness as dp  # noqa: E402
import main  # noqa: E402
import pc_motion as pcm  # noqa: E402
import pc_motion_fixtures as fx  # noqa: E402
from test_pc_motion_derive import gif_blocks  # noqa: E402
from test_pc_motion_routes_live import hold_scheduler, put_real_motion, wait_until  # noqa: E402

SECRET = "dance-test-" + uuid.uuid4().hex
KEY = "internal-test-" + uuid.uuid4().hex
ADMIN = "76561190000009999"
POOL_BASE = 76561202200000000      # inside the individual range; no other live module mints ids here
_SEQ = [0]
JOB_WAIT_S = 240.0                  # one derivation on a loaded seat; the job's own deadline is 120 s
HOLDER = "10.250.0.1"               # hold_scheduler's address


@pytest.fixture(scope="module")
def lane():
    dp.require_live_pg()
    return dp.shared_lane()


@pytest.fixture
def env(monkeypatch, lane, tmp_path):
    sessions = dp.Sessions()
    dp.open_routes(monkeypatch, sessions, SECRET)
    monkeypatch.setenv("API_SECRET_KEY", KEY)

    async def _admin_ok(*_args, **_kwargs):
        return None
    monkeypatch.setattr(main, "_require_admin", _admin_ok)
    monkeypatch.setattr(main, "_pc_motion_cache", pcm.MotionCache(str(tmp_path / "motion")))
    monkeypatch.setattr(main, "_pc_motion_jobs", pcm.MotionScheduler())
    monkeypatch.setattr(main, "_pc_motion_sessions", lambda: lane.sm)
    monkeypatch.setattr(main._pcm, "derive_preview_gif", fx.derive_preview_fake_render)   # on the worker process
    return sessions


def still_of(lane, pid):
    rows = lane.run(dp.fetch(lane, "SELECT pc_game_portrait_hash AS h FROM players WHERE id = CAST(:pid AS uuid)",
                             pid=pid))
    return rows[0]["h"]


async def pool_member(lane, pid):
    """A snapshot of its own naming the subject (rank 3, rare, 1500)."""
    async with lane.sm() as db:
        snap = (await db.execute(text(
            "INSERT INTO pc_pool_snapshots (member_count, rule) VALUES (1, CAST(:rule AS integer)) RETURNING id"),
            {"rule": int(main._PC_POOL_RULE)})).scalar_one()
        await db.execute(text(main._PC_MEMBER_INSERT_SQL), {
            "sid": snap, "pid": pid, "rank": 3, "rarity": "rare", "rating": 1500.0, "peak": 1500.0,
            "board": 7, "wins": 10, "losses": 4, "top": None, "title": None})
        await db.commit()
    return int(snap)


def subject(lane, sessions, *, pool=True):
    """A subject the way /card finds one: a registered player who has run the
    mod (unless `pool` is False), with a real game still stored by the still
    writer, the dance selected and owned, and a member row in a snapshot of
    its own. Returns (steam, pid, still hash, snapshot id)."""
    _SEQ[0] += 1
    steam = str(POOL_BASE + _SEQ[0])
    pid, _none = lane.run(dp.make_player(lane, steam, still=False))
    sessions.live.add(steam)
    status, answer = lane.run(dp.still_upload(lane, steam, SECRET, dp.still_png("gif-" + steam)))
    assert status == 200 and answer["applied"] is True, (status, answer)
    if pool:
        lane.run(dp.execute(lane, "UPDATE players SET mod_seen_at = now() WHERE id = CAST(:pid AS uuid)", pid=pid))
    snap = lane.run(pool_member(lane, pid))
    return steam, pid, still_of(lane, pid), snap


async def restill(lane, steam, pid, tag):
    """The subject's game still replaced through the still writer: a real
    picture, the writer's pacing aged out first."""
    await dp.execute(lane, "UPDATE players SET pc_game_portrait_at = now() - interval '1 hour' "
                           "WHERE id = CAST(:pid AS uuid)", pid=pid)
    status, answer = await dp.still_upload(lane, steam, SECRET, dp.still_png(tag))
    assert status == 200 and answer["applied"] is True, (status, answer)


async def take_lease(lane, pid):
    """The /card lease from the api's own acquire: (lease id, portrait hash)."""
    async with lane.sm() as db:
        got = await main.internal_pc_lease({"subject_ref": pid}, x_internal_key=KEY, db=db)
    return got["lease_id"], got["portrait_hash"]


async def craft_lease(lane, pid, portrait_hash, secs):
    """A lease row written directly: one naming a picture the acquire would
    not name, one already expired, or one for a subject outside the pool."""
    async with lane.sm() as db:
        lid = (await db.execute(text(
            "INSERT INTO pc_delivery_leases (subject_id, portrait_hash, until) VALUES (CAST(:pid AS uuid), "
            "CAST(:h AS text), now() + make_interval(secs => CAST(:s AS double precision))) RETURNING id"),
            {"pid": pid, "h": portrait_hash, "s": float(secs)})).scalar_one()
        await db.commit()
    return str(lid)


async def release_lease(lane, lease_id):
    async with lane.sm() as db:
        return await main.internal_pc_lease_release(lease_id, KEY, _slot=None, db=db)


async def get_gif(lane, pid, lease_id, snap, *, host="10.9.7.1", locale="en"):
    """The GIF route: (200, the response) or (status, the refusal)."""
    req = dp.Req(host=host, path="/api/v1/internal/pc/motion/preview/%s/%s.gif" % (pid, locale))
    async with lane.sm() as db:
        try:
            resp = await main.internal_pc_motion_preview(req, player_ref=pid, locale=locale, x_internal_key=KEY,
                                                         db=db, snapshot_id=snap, lease_id=lease_id)
        except main.HTTPException as ex:
            return ex.status_code, ex.detail
    return 200, resp


async def timed_gif(lane, pid, lease_id, snap, *, host, locale="en"):
    """The GIF route's answer and the seconds the route itself took: the
    session's connection is opened BEFORE the clock starts, because this
    harness opens a new connection for every session (NullPool) and the
    api's pooled sessions never pay that per request."""
    req = dp.Req(host=host, path="/api/v1/internal/pc/motion/preview/%s/%s.gif" % (pid, locale))
    async with lane.sm() as db:
        await db.execute(text("SELECT 1"))
        t0 = time.perf_counter()
        try:
            answer = 200, await main.internal_pc_motion_preview(
                req, player_ref=pid, locale=locale, x_internal_key=KEY, db=db, snapshot_id=snap, lease_id=lease_id)
        except main.HTTPException as ex:
            answer = ex.status_code, ex.detail
        return answer, time.perf_counter() - t0


async def rev_now(lane, pid, snap):
    """The key the route asks for now: the preview's motion revision."""
    async with lane.sm() as db:
        sub, ctx, _spec, _kind, _phash, preview_rev = await main._pc_preview_read(db, pid, "en", snap, motion=True)
    return pcm.motion_preview_rev(pcm.motion_fingerprint(ctx["renderer_fp"]), preview_rev, sub["m_hash"])


def published(pid):
    return sorted(k for k in main._pc_motion_cache.keys() if k.startswith("preview/" + pid + "/"))


def motion_of(data):
    """(loop count, frames, the delays' sum in ms) read from the GIF's own blocks."""
    _table, loop, frames = gif_blocks(data)
    return loop, len(frames), sum(delay for _local, delay, _disposal, _transparent in frames) * 10


def admin_clear(lane, steam):
    async def go():
        async with lane.sm() as db:
            try:
                return 200, await main.admin_pc_portrait_clear(
                    {"admin_steam_id": ADMIN, "steam_id": steam, "lock_days": 0, "signature": "0" * 64}, db=db)
            except main.HTTPException as ex:
                return ex.status_code, ex.detail
    return lane.run(go())


def warm(lane, pid, snap, host):
    """A cold fetch schedules the preview job; this waits for it to end and
    answers the cold answer. The lease it used is released."""
    async def go():
        lease_id, _h = await take_lease(lane, pid)
        cold = await get_gif(lane, pid, lease_id, snap, host=host)
        await wait_until(lambda: main._pc_motion_jobs.total() == 0, timeout=JOB_WAIT_S)
        await release_lease(lane, lease_id)
        return cold
    return lane.run(go())


# -- T33: the GIF route -- a cold key answers at once, the lease decides, a warm key serves the motion ----------

def test_gif_route_cold_and_lease(lane, env):
    """T33 (S6.2): a lease naming another picture, an expired lease, another
    subject's lease, an unknown or a malformed lease id, and a subject the
    pool word refuses each answer 404 with no job. With the one pump busy, a
    cold key answers 404 motion_cold within 2 s of the route being entered
    (timed_gif) -- the bot's GIF timeout (_PC_MOTION_GIF_TIMEOUT_S), and one
    tenth of the 20 s (_PC_MOTION_WAIT_S) a route that awaited its job would
    spend with the pump held -- its job scheduled and not started: the answer
    cannot have waited on the render, which has not begun. Once the job has
    run, the key answers 200 image/gif,
    private for a minute, naming the preview's motion revision and the still
    the lease authorised, and the body is the motion: more than one frame,
    loop 0, the delays summing to N x period. The refused leases still
    answer 404 over the warm file. Control: the warm path. Mutations: the
    route awaits its job; the job publishes the still instead of the motion;
    the lease's picture unchecked."""
    _steam, pid, still, snap = subject(lane, env)
    lane.run(put_real_motion(lane, pid, still))
    _s2, other, other_still, _snap2 = subject(lane, env)
    refused = {
        "another picture": lane.run(craft_lease(lane, pid, dp.still_hash("another picture"), 3600)),
        "expired": lane.run(craft_lease(lane, pid, still, -5)),
        "another subject": lane.run(craft_lease(lane, other, other_still, 3600)),
        "unknown": str(uuid.uuid4()),
        "malformed": "not-a-lease",
    }
    for why, lid in refused.items():
        assert lane.run(get_gif(lane, pid, lid, snap)) == (404, "Not found"), why
    # the pool word decides as it does for the face preview: the same subject
    # shape, never having run the mod, is refused under a lease naming its still
    _s3, outside, outside_still, outside_snap = subject(lane, env, pool=False)
    lane.run(put_real_motion(lane, outside, outside_still))
    lid = lane.run(craft_lease(lane, outside, outside_still, 3600))
    assert lane.run(get_gif(lane, outside, lid, outside_snap)) == (404, "Not found")
    sched = main._pc_motion_jobs
    assert sched.total() == 0 and sched.started == [], (sched.total(), sched.started)

    host = "10.9.7.1"

    async def cold():
        lease_id, leased = await take_lease(lane, pid)
        gate = await hold_scheduler(sched)
        answer, took = await timed_gif(lane, pid, lease_id, snap, host=host)
        state = (sched.held(host), sched.total(), [address for _key, address in sched.started])
        gate.set()
        await wait_until(lambda: sched.total() == 0, timeout=JOB_WAIT_S)
        await release_lease(lane, lease_id)
        return leased, answer, took, state
    leased, answer, took, state = lane.run(cold())
    assert leased == still
    assert answer == (404, {"error": "motion_cold"}), answer
    assert took < 2.0 and main._PC_MOTION_WAIT_S >= 10 * 2.0, (took, main._PC_MOTION_WAIT_S)
    assert state == (1, 2, [HOLDER]), state
    rev = lane.run(rev_now(lane, pid, snap))
    assert published(pid) == ["preview/%s/%s/en.gif" % (pid, rev)], published(pid)

    lease_id, _h = lane.run(take_lease(lane, pid))
    status, resp = lane.run(get_gif(lane, pid, lease_id, snap, host=host))
    assert status == 200, (status, resp)
    assert resp.headers["content-type"] == "image/gif"
    assert resp.headers["cache-control"] == "private, max-age=60"
    assert resp.headers["x-motion-rev"] == rev and resp.headers["x-motion-static-hash"] == still
    # the writer may merge identical neighbours and sum their delays (S4.5):
    # the frame count is at most N and the total is exactly N x period
    period, count = pcm.table_row(pcm.MOTION_RECIPE, "dance_bounce")
    loop, frames, total_ms = motion_of(resp.body)
    assert loop == 0 and 1 < frames <= count and total_ms == count * period, (loop, frames, total_ms)
    lane.run(release_lease(lane, lease_id))
    for why, lid in refused.items():
        assert lane.run(get_gif(lane, pid, lid, snap)) == (404, "Not found"), why
    assert sched.total() == 0 and len(sched.started) == 2, sched.started


# -- T60 (GIF half): the preview job re-reads the subject when it starts (L5) ------------------------------------

def test_gif_job_rechecks_at_start(lane, env):
    """T60's GIF half (S4.8, L5): a preview job scheduled for a revision and
    queued behind another address's job re-reads the subject when it starts;
    a still replaced (through the still writer, a real picture) or a motion
    replaced in the meantime publishes nothing. Control: nothing moved while
    it queued, and the job publishes its one file. Mutation: the re-check at
    the job's start skipped."""
    def case(change, n):
        steam, pid, still, snap = subject(lane, env)
        lane.run(put_real_motion(lane, pid, still))
        host = "10.9.8.%d" % n

        async def go():
            sched = main._pc_motion_jobs
            lease_id, _h = await take_lease(lane, pid)
            gate = await hold_scheduler(sched)
            answer = await get_gif(lane, pid, lease_id, snap, host=host)
            queued = sched.held(host)
            if change == "still":
                await restill(lane, steam, pid, "moved-" + steam)
            elif change == "motion":
                await put_real_motion(lane, pid, still, seed=7)
            gate.set()
            await wait_until(lambda: sched.total() == 0, timeout=JOB_WAIT_S)
            await release_lease(lane, lease_id)
            return answer, queued
        answer, queued = lane.run(go())
        assert answer == (404, {"error": "motion_cold"}) and queued == 1, (change, answer, queued)
        return published(pid)

    assert len(case(None, 1)) == 1
    for n, change in enumerate(("still", "motion"), start=2):
        assert case(change, n) == [], change


# -- T61 (fetch half): after an admin clear every later GIF fetch fails closed (L6) -----------------------------

def test_clear_fails_every_later_gif_fetch_closed(lane, env):
    """T61's fetch half (L6, S6.5): once an admin clear has run, every later
    GIF fetch fails closed -- the lease it waited out is gone, a lease taken
    after the clear names no picture, and a lease taken after the SAME still
    is uploaded again still answers 404, because the clear removed the
    stored motion; the derived file is still on disk and is never the
    authority. The send half is the bot's revalidation (T42). A GIF already
    posted is not retracted: that is the stated residual, not this test.
    Control: a fetch before any clear serves the GIF. Mutation: the clear
    leaves the stored motion."""
    steam, pid, still, snap = subject(lane, env)
    lane.run(put_real_motion(lane, pid, still))
    assert warm(lane, pid, snap, "10.9.9.1") == (404, {"error": "motion_cold"})
    keys = published(pid)
    assert len(keys) == 1, keys
    lease_id, _h = lane.run(take_lease(lane, pid))
    status, resp = lane.run(get_gif(lane, pid, lease_id, snap))
    assert status == 200 and resp.headers["x-motion-static-hash"] == still, (status, resp)
    # the clear waits out the live lease, and runs once it is released
    status, detail = admin_clear(lane, steam)
    assert status == 409 and detail["error"] == "retry_after", (status, detail)
    assert lane.run(release_lease(lane, lease_id)) == {"released": 1}
    status, answer = admin_clear(lane, steam)
    assert status == 200 and answer["cleared"] is True, (status, answer)
    assert lane.run(get_gif(lane, pid, lease_id, snap)) == (404, "Not found")
    after, leased = lane.run(take_lease(lane, pid))
    assert leased is None
    assert lane.run(get_gif(lane, pid, after, snap)) == (404, "Not found")
    lane.run(release_lease(lane, after))
    status, answer = lane.run(dp.still_upload(lane, steam, SECRET, dp.still_png("gif-" + steam)))
    assert status == 200 and still_of(lane, pid) == still, (status, answer)
    again, leased = lane.run(take_lease(lane, pid))
    assert leased == still
    assert lane.run(get_gif(lane, pid, again, snap)) == (404, "Not found")
    lane.run(release_lease(lane, again))
    assert published(pid) == keys and main._pc_motion_cache.read(keys[0]) is not None
    assert main._pc_motion_jobs.total() == 0
