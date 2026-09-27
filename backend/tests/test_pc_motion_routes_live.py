"""Dance cards: the motion reads against a real PostgreSQL (design S4.8-S4.10,
S5.2; section 12 H1, L5) -- T28, T29, T30 (with T19's live half), T60, T68
(H1's route half: jobs keyed to the limiter's client address), T69 (the
motion cache ages on the face cache's clock) and T25's wiring half.

Each test is one named assertion; the mutation that must fail it is planted
by the lane's mutation runner and recorded in its log, and the test's own
passing case is the control (#391). The HMAC key is a random test value, the
strict session check is replaced, and every player is synthetic. The motion
cache is a per-test directory and the scheduler a fresh one per test; the
tests that derive draw with the fixtures' fast stand-in for the renderer.
"""
import asyncio
import hashlib
import json
import os
import sys
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

SECRET = "dance-test-" + uuid.uuid4().hex


@pytest.fixture(scope="module")
def lane():
    dp.require_live_pg()
    return dp.shared_lane()


@pytest.fixture
def env(monkeypatch, lane, tmp_path):
    sessions = dp.Sessions()
    dp.open_routes(monkeypatch, sessions, SECRET)
    monkeypatch.setattr(main, "_pc_motion_cache", pcm.MotionCache(str(tmp_path / "motion")))
    monkeypatch.setattr(main, "_pc_motion_jobs", pcm.MotionScheduler())
    monkeypatch.setattr(main, "_pc_motion_sessions", lambda: lane.sm)
    return sessions


def player(lane, sessions, **kw):
    steam = dp.steam_id()
    pid, still = lane.run(dp.make_player(lane, steam, **kw))
    sessions.live.add(steam)
    return steam, pid, still


async def put_real_motion(lane, pid, still, *, dance="dance_bounce", descriptor=dp.DESC, seed=0):
    """A stored motion whose bytes are a real container of `dance` (smooth
    frames, bound to `still`), so a job can derive it. Returns its hash."""
    period, count = pcm.table_row(pcm.MOTION_RECIPE, dance)
    body = fx.container(dance, fx.smooth_frames(count), static=still)
    h = hashlib.sha256(body + b":" + str(seed).encode()).hexdigest()
    async with lane.sm() as db:
        await db.execute(text("DELETE FROM pc_motions WHERE player_id = CAST(:pid AS uuid)"), {"pid": pid})
        await db.execute(text(
            "INSERT INTO pc_motions (player_id, motion_hash, source_sha256, bytes, byte_len, dance_item_id, "
            "motion_recipe, frame_count, frame_ms, static_hash, static_descriptor) VALUES (CAST(:pid AS uuid), "
            "CAST(:h AS text), CAST(:h AS text), CAST(:b AS bytea), CAST(:n AS integer), CAST(:item AS bigint), "
            "CAST(:r AS smallint), CAST(:c AS smallint), CAST(:ms AS smallint), CAST(:sh AS text), CAST(:sd AS text))"),
            {"pid": pid, "h": h, "b": body, "n": len(body), "item": lane.items[dance], "r": pcm.MOTION_RECIPE,
             "c": count, "ms": period, "sh": still, "sd": descriptor})
        await db.commit()
    return h


async def make_print(lane, subject_pid, owner_pid, *, discarded=False, rarity="rare"):
    """One print of `subject_pid`'s card, held by `owner_pid`."""
    async with lane.sm() as db:
        edition = (await db.execute(text("SELECT min(id) FROM pc_editions"))).scalar_one()
        if edition is None:                               # the lane's schema carries no seed rows
            edition = (await db.execute(text(
                "INSERT INTO pc_editions (name) VALUES ('Edition 1') RETURNING id"))).scalar_one()
        card = (await db.execute(text(
            "INSERT INTO pc_cards (subject_player_id, edition_id) "
            "VALUES (CAST(:s AS uuid), CAST(:e AS integer)) "
            "ON CONFLICT (subject_player_id, edition_id, variant) DO UPDATE SET variant = EXCLUDED.variant "
            "RETURNING id"), {"s": subject_pid, "e": edition})).scalar_one()
        pr = (await db.execute(text(
            "INSERT INTO pc_prints (card_id, owner_player_id, snapshot_id, rarity, pool_rank, rating, board_rank, "
            "series_wins, series_losses, source, discarded_at) VALUES (CAST(:c AS uuid), CAST(:o AS uuid), 1, "
            "CAST(:r AS text), 3, 1500, 3, 10, 4, 'bought', CASE WHEN CAST(:d AS boolean) THEN now() END) "
            "RETURNING id"), {"c": str(card), "o": owner_pid, "r": rarity, "d": discarded})).scalar_one()
        await db.commit()
    return str(pr)


async def replace_still(lane, pid, h):
    async with lane.sm() as db:
        await dp.still_blob(db, h)
        await db.execute(text("UPDATE players SET pc_game_portrait_hash = CAST(:h AS text) "
                              "WHERE id = CAST(:pid AS uuid)"), {"h": h, "pid": pid})
        await db.commit()


async def read_motion(lane, ids, locale="en"):
    """The per-visit read: (status, the `m` string or the refusal)."""
    async with lane.sm() as db:
        try:
            resp = await main.pc_face_motion_read(ids=",".join(ids), locale=locale, db=db)
        except main.HTTPException as ex:
            return ex.status_code, ex.detail
    assert resp.headers["cache-control"] == "no-store"
    return 200, json.loads(resp.body)["m"]


def entries(answer):
    return [part.split(":") for part in answer.split("|")]


def rev_of(lane, print_id):
    status, answer = lane.run(read_motion(lane, [print_id]))
    assert status == 200, (status, answer)
    got = entries(answer)[0]
    assert got[0] == print_id and len(got) == 5, got
    return got[2]


async def get_atlas(lane, print_id, rev, *, size="card", host="10.9.0.1", locale="en"):
    """The atlas route: (200, the response) or (status, the refusal)."""
    req = dp.Req(host=host, path="/api/v1/pc-face/motion/%s/%s/%s/%s.png" % (print_id, rev, locale, size))
    async with lane.sm() as db:
        try:
            resp = await main.pc_face_motion_atlas(req, print_id=print_id, motion_rev=rev, locale=locale,
                                                   size=size, db=db)
        except main.HTTPException as ex:
            return ex.status_code, ex.detail
    return 200, resp


async def collection(lane, steam):
    sig = dp.sign(SECRET, main._pc.canon_read(steam, "collection", "-"))
    async with lane.sm() as db:
        return await main.pc_collection(dp.Req(path="/api/v1/pc/collection"), steam_id=steam, sig=sig,
                                        subject=None, db=db)


async def wait_until(pred, timeout=15.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not pred():
        if loop.time() > end:
            raise AssertionError("the condition was never reached")
        await asyncio.sleep(0.02)


async def hold_scheduler(sched):
    """A job from another address that holds the one pump until released."""
    gate = asyncio.Event()

    async def hold():
        await gate.wait()
        return ("held",)
    sched.submit("hold/" + uuid.uuid4().hex, "10.250.0.1", hold)
    return gate


# -- T25 (wiring half): main's motion cache is its own ------------------------------------

def test_motion_cache_wired_apart():
    """T25 (S4.7): main wires a MotionCache under its own root, never the face
    cache, with the 1 GiB cap, and one scheduler. Control: the wiring as
    built. Mutation: the face cache instance reused for motion."""
    cache = main._pc_motion_cache
    assert isinstance(cache, pcm.MotionCache) and cache is not main._pc_face_cache
    assert os.path.abspath(cache.root) != os.path.abspath(main._pc_face_cache.root)
    assert cache.cap == 1 << 30 and isinstance(main._pc_motion_jobs, pcm.MotionScheduler)


# -- T69: the motion cache ages on the face cache's clock -----------------------------------

def test_motion_cache_expires_on_the_face_clock(monkeypatch):
    """T69 (S4.7): the hourly expiry pass that ages the face cache ages the
    motion cache too, on both roles. Control: both expire on every pass.
    Mutation: the motion cache left out of the pass."""
    class Stub:
        def __init__(self):
            self.calls = 0

        def expire(self):
            self.calls += 1
            return 0
    face, motion = Stub(), Stub()
    monkeypatch.setattr(main, "_pc_face_cache", face)
    monkeypatch.setattr(main, "_pc_motion_cache", motion)
    monkeypatch.setattr(main, "_PC_STEAM_BOOT_DELAY_S", 0)
    monkeypatch.setattr(main, "_PC_FACE_EXPIRE_EVERY_S", 0.01)

    async def go():
        task = asyncio.ensure_future(main._pc_face_cache_expire_loop())
        for _ in range(300):
            await asyncio.sleep(0.01)
            if face.calls >= 2 and motion.calls >= 2:
                break
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    asyncio.run(go())
    assert face.calls >= 2 and motion.calls >= 2, (face.calls, motion.calls)


# -- T28: the row before the cache -------------------------------------------------------------

def test_motion_row_before_cache(lane, env):
    """T28 (S4.8): a banned or deleted subject's atlas answers 404 though its
    file is in the motion cache; a malformed URL answers 404 with no read and
    no job. Control: a live subject's cached atlas is served (200, immutable,
    no job). Mutation: the cache read before the row."""
    steam, pid, still = player(lane, env)
    lane.run(put_real_motion(lane, pid, still))
    _so, owner, _ = player(lane, env, dance=None)
    pr = lane.run(make_print(lane, pid, owner))
    rev = rev_of(lane, pr)
    key = pcm.atlas_key(pr, rev, "en", "card")
    main._pc_motion_cache.publish(key, b"cached-atlas")
    status, resp = lane.run(get_atlas(lane, pr, rev))
    assert status == 200 and resp.body == b"cached-atlas", (status, resp)
    assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"
    for bad in ((pr, "0" * 15, "card"), ("not-a-print", rev, "card"), (pr, rev, "huge")):
        assert lane.run(get_atlas(lane, bad[0], bad[1], size=bad[2]))[0] == 404, bad
    assert main._pc_motion_jobs.started == [] and main._pc_motion_jobs.total() == 0
    lane.run(dp.ban(lane, steam))
    status, _detail = lane.run(get_atlas(lane, pr, rev))
    assert status == 404 and main._pc_motion_cache.read(key) == b"cached-atlas"

    steam2, pid2, still2 = player(lane, env)
    lane.run(put_real_motion(lane, pid2, still2))
    pr2 = lane.run(make_print(lane, pid2, owner))
    rev2 = rev_of(lane, pr2)
    key2 = pcm.atlas_key(pr2, rev2, "en", "tile")
    main._pc_motion_cache.publish(key2, b"cached-tile")
    assert lane.run(get_atlas(lane, pr2, rev2, size="tile"))[0] == 200
    lane.run(dp.execute(lane, "UPDATE players SET deleted_at = now() WHERE id = CAST(:pid AS uuid)", pid=pid2))
    assert lane.run(get_atlas(lane, pr2, rev2, size="tile"))[0] == 404
    assert main._pc_motion_jobs.started == []


# -- T29: the subject's motion, never the owner's ----------------------------------------------

def test_motion_joins_subject_not_owner(lane, env):
    """T29 (S4.8 step 3): a print of subject B held by A plays B's motion --
    B's dance, frame count and revision. Control: A's own card plays A's.
    Mutation: the motion joined on the print's owner."""
    _sa, a, still_a = player(lane, env)
    ha = lane.run(put_real_motion(lane, a, still_a))
    _sb, b, still_b = player(lane, env, dance="dance_robot")
    hb = lane.run(put_real_motion(lane, b, still_b, dance="dance_robot"))
    of_b = lane.run(make_print(lane, b, a))
    of_a = lane.run(make_print(lane, a, a))
    status, answer = lane.run(read_motion(lane, [of_b, of_a]))
    assert status == 200, (status, answer)
    (pb, fb, rb, nb, msb), (pa, fa, ra, na, msa) = entries(answer)
    fp = pcm.motion_fingerprint(main._pc_renderer_fp())
    assert (pb, nb, msb) == (of_b, "120", "50") and rb == pcm.motion_rev(fp, fb, hb)
    assert (pa, na, msa) == (of_a, "80", "50") and ra == pcm.motion_rev(fp, fa, ha)


# -- T30: the per-visit read ------------------------------------------------------------------------

def test_motion_read_endpoint(lane, env):
    """T30 (S5.2): more than eleven ids, a malformed id or an upper-case one:
    422. One entry per id in request order; `-` for an unknown print, a
    subject with no motion, a discarded print, lost ownership and a replaced
    still; the face_rev is the collection answer's. T19's live half: another
    player's motion does not move this print's rev. Control: a bound motion
    gives a rev. Mutations: the servable predicate skipped; a discarded
    print answered; twelve ids admitted."""
    ids = [str(uuid.uuid4()) for _ in range(12)]
    assert lane.run(read_motion(lane, ids))[0] == 422
    status, answer = lane.run(read_motion(lane, ids[:11]))
    assert status == 200 and [e[1:] for e in entries(answer)] == [["-"]] * 11
    assert lane.run(read_motion(lane, ["not-a-print"]))[0] == 422
    assert lane.run(read_motion(lane, [ids[0].upper()]))[0] == 422

    sx, x, still_x = player(lane, env)
    lane.run(put_real_motion(lane, x, still_x))
    so, owner, _ = player(lane, env, dance=None)
    _sy, y, still_y = player(lane, env)
    px = lane.run(make_print(lane, x, owner))
    py = lane.run(make_print(lane, y, owner))
    pd = lane.run(make_print(lane, x, owner, discarded=True))
    unknown = str(uuid.uuid4())
    status, answer = lane.run(read_motion(lane, [px, unknown, py, pd]))
    assert status == 200, (status, answer)
    got = entries(answer)
    assert [g[0] for g in got] == [px, unknown, py, pd]
    assert [g[1:] for g in got[1:]] == [["-"], ["-"], ["-"]], got
    face_rev, rev = got[0][1], got[0][2]
    coll = lane.run(collection(lane, so))
    assert {p["print_id"]: p["face_rev"] for p in coll["prints"]}[px] == face_rev

    lane.run(put_real_motion(lane, y, still_y, seed=1))          # T19: another player's motion
    assert rev_of(lane, px) == rev and rev_of(lane, py) != rev

    lane.run(dp.execute(lane, "DELETE FROM player_items WHERE player_id = CAST(:pid AS uuid)", pid=x))
    assert entries(lane.run(read_motion(lane, [px]))[1])[0][1:] == ["-"]
    lane.run(dp.own(lane, x, lane.items["dance_bounce"]))
    assert rev_of(lane, px) == rev
    lane.run(replace_still(lane, x, dp.still_hash("replaced:" + sx)))
    assert entries(lane.run(read_motion(lane, [px]))[1])[0][1:] == ["-"]


# -- T60: the job re-reads and re-validates when it starts (L5) -----------------------------------

def test_motion_job_rechecks_at_start(lane, env, monkeypatch):
    """T60 (S4.8, L5): a job scheduled for a revision and queued behind
    another address's job re-reads the row when it starts; a still replaced
    or a motion replaced in the meantime publishes nothing under the stale
    revision and the request answers 404. Control: nothing moved while it
    queued, and the job publishes both sizes (200). Mutation: the re-check
    at the job's start skipped."""
    monkeypatch.setattr(main._pcf, "render_face", fx.fake_render)
    monkeypatch.setattr(main, "_PC_MOTION_WAIT_S", 300.0)
    _so, owner, _ = player(lane, env, dance=None)

    def case(change, n):
        steam, pid, still = player(lane, env)
        lane.run(put_real_motion(lane, pid, still))
        pr = lane.run(make_print(lane, pid, owner))
        rev = rev_of(lane, pr)
        host = "10.9.1.%d" % n

        async def go():
            sched = main._pc_motion_jobs
            gate = await hold_scheduler(sched)
            task = asyncio.ensure_future(get_atlas(lane, pr, rev, host=host))
            await wait_until(lambda: sched.held(host) == 1)       # scheduled, queued behind the hold
            if change == "still":
                await replace_still(lane, pid, dp.still_hash("moved:" + steam))
            elif change == "motion":
                await put_real_motion(lane, pid, still, seed=7)
            gate.set()
            return await task
        status, resp = lane.run(go())
        published = sorted(k for k in main._pc_motion_cache.keys() if k.startswith("atlas/" + pr + "/"))
        return status, resp, published

    status, resp, published = case(None, 1)
    assert status == 200 and resp.body[:8] == b"\x89PNG\r\n\x1a\n", (status, resp)
    assert len(published) == 2, published
    for n, change in enumerate(("still", "motion"), start=2):
        status, detail, published = case(change, n)
        assert status == 404 and published == [], (change, status, detail, published)


# -- T68: jobs are keyed to the limiter's client address (H1) --------------------------------------

def test_motion_jobs_keyed_to_the_client_address(lane, env, monkeypatch):
    """T68 (S4.6, H1's route half): the atlas route admits its job under the
    request's client address as the rate limiter reads it: a third job from
    one address is refused at once (503 motion_busy) while another address's
    job is admitted. Control: two per address, a second address admitted.
    Mutation: every job keyed to one address."""
    gate = {}

    async def stub_job(print_id, rev, locale, expect):
        await gate["open"].wait()
        return ("stale", "test")
    monkeypatch.setattr(main, "_pc_motion_atlas_job", stub_job)
    _so, owner, _ = player(lane, env, dance=None)
    prints = []
    for _ in range(3):
        _steam, pid, still = player(lane, env)
        lane.run(put_real_motion(lane, pid, still))
        pr = lane.run(make_print(lane, pid, owner))
        prints.append((pr, rev_of(lane, pr)))
    h1, h2 = "10.9.2.1", "10.9.2.2"
    assert main._rl_client_address(dp.Req(host=h1)) == h1

    async def go():
        gate["open"] = asyncio.Event()
        sched = main._pc_motion_jobs
        t1 = asyncio.ensure_future(get_atlas(lane, *prints[0], host=h1))
        t2 = asyncio.ensure_future(get_atlas(lane, *prints[1], host=h1))
        await wait_until(lambda: sched.held(h1) == 2)
        third = await get_atlas(lane, *prints[2], host=h1)
        t3 = asyncio.ensure_future(get_atlas(lane, *prints[2], host=h2))
        await wait_until(lambda: sched.held(h2) == 1)
        total = sched.total()
        gate["open"].set()
        rest = await asyncio.gather(t1, t2, t3)
        return third, total, rest, list(sched.started)

    third, total, rest, started = lane.run(go())
    assert third[0] == 503 and third[1]["error"] == "motion_busy", third
    assert total == 3 and [r[0] for r in rest] == [404, 404, 404], (total, rest)
    assert sorted(addr for _key, addr in started) == [h1, h1, h2], started
