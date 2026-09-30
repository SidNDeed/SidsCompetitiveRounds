"""Dance cards: the motion writer (design S2.2, S2.6; section 12 M2, M3, M4,
L3) against a real PostgreSQL -- T7, T9-T15, T46 (the route half), T47, T54,
T55 (the upload half), T56 and T58.

Each test is one named assertion; the mutation that must fail it is planted
by the lane's mutation runner and recorded in its log, and the test's own
passing case is the control (#391). The HMAC key is a random test value, the
strict session check is replaced (dance_pg_harness.Sessions), and every
player is synthetic.
"""
import asyncio
import hashlib
import os
import sys
import time
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import dance_pg_harness as dp  # noqa: E402
import main  # noqa: E402
import pc_motion as pcm  # noqa: E402
import pc_motion_fixtures as fx  # noqa: E402

try:
    import asyncpg
except ImportError:                                    # pragma: no cover
    asyncpg = None

SECRET = "dance-test-" + uuid.uuid4().hex
_REAL_DECODE = pcm.decode_frames


@pytest.fixture(scope="module")
def lane():
    dp.require_live_pg()
    return dp.shared_lane()


@pytest.fixture
def env(monkeypatch, lane):
    sessions = dp.Sessions()
    dp.open_routes(monkeypatch, sessions, SECRET)
    return sessions


_FRAMES = {}


def frames(kind="smooth"):
    """Frame lists, encoded once per module."""
    if kind not in _FRAMES:
        if kind == "smooth":
            _FRAMES[kind] = fx.smooth_frames(80)
        elif kind == "smooth9":        # other bytes, the same canonical container
            _FRAMES[kind] = fx.smooth_frames(80, level=9)
        elif kind == "shifted":        # another motion
            _FRAMES[kind] = [fx.png_bytes(fx.figure(k / 80.0, dx=24)) for k in range(80)]
        elif kind == "empty0":         # refused at frame 0 (coverage): a cheap charged attempt
            _FRAMES[kind] = [fx.png_bytes(fx.blank())] + list(frames("smooth"))[1:]
        elif kind == "flash":          # refused at the pair (0, 1)
            bright = fx.png_bytes(fx.block((4, 4, 585, 355), (250, 250, 250, 255)))
            dark = fx.png_bytes(fx.block((4, 4, 585, 355), (10, 10, 10, 255)))
            _FRAMES[kind] = [bright if k % 2 == 0 else dark for k in range(80)]
        else:
            raise KeyError(kind)
    return _FRAMES[kind]


def body_for(static, kind="smooth", dance="dance_bounce"):
    return fx.container(dance, frames(kind), static=static)


def player(lane, sessions, **kw):
    steam = dp.steam_id()
    pid, still = lane.run(dp.make_player(lane, steam, **kw))
    sessions.live.add(steam)
    return steam, pid, still


def up(lane, steam, body, **kw):
    return lane.run(dp.upload(lane, steam, SECRET, body, **kw))


def state(lane, pid):
    return dict(lane.run(dp.fetch(
        lane, "SELECT pc_motion_at, pc_motion_day, pc_motion_day_count FROM players "
              "WHERE id = CAST(:pid AS uuid)", pid=pid))[0])


def motion_row(lane, pid):
    rows = lane.run(dp.fetch(
        lane, "SELECT motion_hash, source_sha256, static_hash, static_descriptor, byte_len, "
              "dance_item_id, stored_at FROM pc_motions WHERE player_id = CAST(:pid AS uuid)", pid=pid))
    return dict(rows[0]) if rows else None


def nonce_used(lane, pid, n):
    return bool(lane.run(dp.fetch(
        lane, "SELECT 1 FROM pc_portrait_nonces WHERE player_id = CAST(:pid AS uuid) "
              "AND nonce = CAST(:n AS text)", pid=pid, n=n)))


def age_pacing(lane, pid, secs=31):
    lane.run(dp.execute(
        lane, "UPDATE players SET pc_motion_at = now() - make_interval(secs => CAST(:s AS double precision)) "
              "WHERE id = CAST(:pid AS uuid)", s=secs, pid=pid))


def spy_decode(monkeypatch, before=None):
    """Count the decodes that actually ran; `before()` runs first, on the
    decode worker, inside the decode (phase B)."""
    calls = []
    real = _REAL_DECODE        # never an earlier spy: each spy replaces, not stacks

    def wrapped(header, frames_, deadline_s=pcm.DECODE_DEADLINE_S, clock=time.monotonic):
        calls.append(header["dance"])
        if before is not None:
            before()
        return real(header, frames_, deadline_s, clock)
    monkeypatch.setattr(pcm, "decode_frames", wrapped)
    return calls


def canonical_size(static):
    header, frames_ = pcm.parse_container(body_for(static))
    return len(pcm.decode_frames(header, frames_)[0])


# -- T7 / T54: transport, before any parse -----------------------------------

def test_motion_transport(lane, env, monkeypatch):
    """T7: 411 without a length and when chunked; 413 on a declared length
    over 12 MiB BEFORE the body is read; 400 when the received length
    differs; 413 when the CANONICAL container is over the cap. Control: a
    body of exactly 12 MiB passes the transport gate (then 422 as junk)."""
    steam, pid, still = player(lane, env)
    body = body_for(still)
    for req in (dp.motion_request(body, length=False), dp.motion_request(body, chunked=True)):
        status, detail = up(lane, steam, body, request=req)
        assert (status, detail, req.reads) == (411, "length_required", 0)
    req = dp.motion_request(body, length=pcm.MOTION_MAX_BYTES + 1)
    status, detail = up(lane, steam, body, request=req)
    assert (status, detail, req.reads) == (413, {"error": "motion_too_large"}, 0)
    req = dp.motion_request(body, length=len(body) + 1)
    status, detail = up(lane, steam, body, request=req)
    assert (status, detail) == (400, "length_mismatch")
    status, detail = up(lane, steam, b"\0" * pcm.MOTION_MAX_BYTES)
    assert (status, detail) == (422, {"error": "motion_container"})
    assert state(lane, pid)["pc_motion_at"] is None
    # 413 canonical: level-9 frames re-encode larger at the canonical level 6,
    # so a cap equal to the received length admits the body and refuses the
    # canonical container -- after the decode, charged.
    small = body_for(still, "smooth9")
    monkeypatch.setattr(pcm, "MOTION_MAX_BYTES", len(small))
    status, detail = up(lane, steam, small)
    assert (status, detail) == (413, {"error": "motion_too_large"})
    assert state(lane, pid)["pc_motion_day_count"] == 1 and motion_row(lane, pid) is None


def test_motion_content_type_is_exact(lane, env):
    """T54 (M2): the normalised Content-Type must EQUAL the motion type --
    a near miss or a parameter suffix is 415 before the body is read.
    Control: the exact type (case and outer spaces normalised) is applied."""
    steam, pid, still = player(lane, env)
    body = body_for(still)
    for ct in ("application/x-scr-motionjunk", "application/x-scr-motion; charset=binary",
               "application/x-scr-motion+x", "application/octet-stream", "image/png", ""):
        req = dp.motion_request(body, content_type=ct)
        status, _detail = up(lane, steam, body, request=req)
        assert (status, req.reads) == (415, 0), ct
    req = dp.motion_request(body, content_type=" Application/X-SCR-Motion ")
    status, answer = up(lane, steam, body, request=req)
    assert status == 200 and answer["applied"] is True


# -- T9, T10: binding and ownership ------------------------------------------

def test_motion_binding(lane, env):
    """T9: another still's hash, another descriptor, or no game still at all
    is 409 motion_unbound, nothing charged. Control: the bound upload is
    applied and stores the binding it was checked against."""
    steam, pid, still = player(lane, env)
    status, detail = up(lane, steam, body_for(dp.still_hash("another")))
    assert (status, detail) == (409, {"error": "motion_unbound"})
    status, detail = up(lane, steam, body_for(still), descriptor=dp.DESC.replace("anim=1", "anim=0"))
    assert (status, detail) == (409, {"error": "motion_unbound"})
    bare, bare_pid, _ = player(lane, env, still=False)
    status, detail = up(lane, bare, body_for(dp.still_hash(bare)))
    assert (status, detail) == (409, {"error": "motion_unbound"})
    assert state(lane, pid)["pc_motion_at"] is None and state(lane, bare_pid)["pc_motion_at"] is None
    status, answer = up(lane, steam, body_for(still))
    assert status == 200 and answer["applied"] is True
    row = motion_row(lane, pid)
    assert (row["static_hash"], row["static_descriptor"]) == (still, dp.DESC)
    assert row["motion_hash"] == answer["motion_hash"] and row["dance_item_id"] == lane.items["dance_bounce"]


def test_motion_ownership(lane, env, monkeypatch):
    """T10: an unowned dance is 403 dance_not_owned; the exemption account
    owns through `_auto_owned` with no player_items row; an unready item is
    refused even to its buyer. Control: an owned dance is applied."""
    steam, pid, still = player(lane, env, owned=False)
    status, detail = up(lane, steam, body_for(still))
    assert (status, detail) == (403, {"error": "dance_not_owned"})
    exempt, _epid, estill = player(lane, env, owned=False)
    monkeypatch.setattr(main, "SHOP_OWNER_STEAM_IDS", {exempt})
    status, answer = up(lane, exempt, body_for(estill))
    assert status == 200 and answer["applied"] is True
    wave, _wpid, wstill = player(lane, env, dance="dance_wave")
    lane.run(dp.execute(lane, "UPDATE shop_items SET catalog_ready = false WHERE sku = 'dance_wave'"))
    try:
        status, detail = up(lane, wave, body_for(wstill, dance="dance_wave"))
        assert (status, detail) == (403, {"error": "dance_not_owned"})
    finally:
        lane.run(dp.execute(lane, "UPDATE shop_items SET catalog_ready = true WHERE sku = 'dance_wave'"))
    owner, _opid, ostill = player(lane, env)
    status, answer = up(lane, owner, body_for(ostill))
    assert status == 200 and answer["applied"] is True


# -- T11, T12, T14: same, the day cap, the nonce ------------------------------

def test_motion_same_before_pacing(lane, env):
    """T11: an identical re-upload inside 30 s is 200 same with nothing
    charged and its nonce unused. Control: different bytes inside 30 s are
    409 retry_after."""
    steam, pid, still = player(lane, env)
    body = body_for(still)
    status, answer = up(lane, steam, body)
    assert status == 200 and answer["applied"] is True
    charged = state(lane, pid)
    n = dp.nonce()
    status, answer = up(lane, steam, body, nonce_value=n)
    assert status == 200 and answer == {"applied": False, "reason": "same",
                                        "motion_hash": motion_row(lane, pid)["motion_hash"]}
    assert state(lane, pid) == charged and not nonce_used(lane, pid, n)
    status, detail = up(lane, steam, body_for(still, "shifted"))
    assert status == 409 and detail["error"] == "retry_after" and 1 <= detail["retry_after"] <= 31


def test_motion_day_cap_survives_reselect(lane, env):
    """T12: eight charged decode attempts in one UTC day, then a selection
    change (the motion row goes, as S2.10 does it): the ninth is 409
    daily_cap -- the counter lives on `players`, not on the motion row.
    Control: the next UTC day is accepted and restarts the count at 1."""
    steam, pid, still = player(lane, env)
    lane.run(dp.execute(lane, "INSERT INTO player_items (player_id, item_id, purchase_price) "
                              "VALUES (CAST(:pid AS uuid), CAST(:i AS bigint), 0)",
                        pid=pid, i=lane.items["dance_wave"]))
    status, _ = up(lane, steam, body_for(still))
    assert status == 200 and motion_row(lane, pid) is not None
    for _ in range(7):
        age_pacing(lane, pid)
        status, detail = up(lane, steam, body_for(still, "empty0"))
        assert (status, detail["error"]) == (422, "motion_coverage")
    assert state(lane, pid)["pc_motion_day_count"] == 8
    lane.run(dp.execute(lane, "UPDATE players SET active_dance_id = CAST(:i AS bigint) WHERE id = CAST(:pid AS uuid)",
                        i=lane.items["dance_wave"], pid=pid))
    lane.run(dp.execute(lane, "DELETE FROM pc_motions WHERE player_id = CAST(:pid AS uuid)", pid=pid))
    age_pacing(lane, pid)
    wave = body_for(still, dance="dance_wave")
    status, detail = up(lane, steam, wave)
    assert status == 409 and detail["error"] == "daily_cap" and detail["retry_after"] >= 1
    lane.run(dp.execute(lane, "UPDATE players SET pc_motion_day = pc_motion_day - 1 WHERE id = CAST(:pid AS uuid)",
                        pid=pid))
    status, answer = up(lane, steam, wave)
    assert status == 200 and answer["applied"] is True and state(lane, pid)["pc_motion_day_count"] == 1


def test_motion_nonce_single_use(lane, env):
    """T14: a nonce already used is 403 nonce_replayed and charges nothing.
    Control: a fresh nonce is accepted."""
    steam, pid, still = player(lane, env)
    n = dp.nonce()
    status, _ = up(lane, steam, body_for(still), nonce_value=n)
    assert status == 200
    age_pacing(lane, pid)
    before = state(lane, pid)
    status, detail = up(lane, steam, body_for(still, "shifted"), nonce_value=n)
    assert (status, detail) == (403, {"error": "nonce_replayed"}) and state(lane, pid) == before
    status, answer = up(lane, steam, body_for(still, "shifted"))
    assert status == 200 and answer["applied"] is True


# -- T13: capacity -------------------------------------------------------------

def _capacity_barrier(lane, monkeypatch):
    """Hold the first phase C to finish its capacity SUM, AFTER the SUM and
    before its upsert, until the second has finished its own SUM too or is
    seen waiting on an advisory lock (the capacity lock the first holds).
    With the lock, the second's SUM runs after the first commits and counts
    its row; without it, both sums miss the other's row and both store.
    (Holding BEFORE the SUM proved nothing: READ COMMITTED gives each
    statement a fresh snapshot, so the held session's later SUM saw the
    other's committed row and the lockless mutant passed.) A release by the
    time cap, not by either event, is counted: the test refuses it."""
    state = {"arrived": [], "timeouts": 0}
    real = main._pc_motion_capacity_used

    async def barrier(db, pid):
        used = await real(db, pid)
        state["arrived"].append(pid)
        if len(state["arrived"]) == 1:
            conn = await lane.connect()
            try:
                for _ in range(600):
                    if len(state["arrived"]) >= 2 or await conn.fetchval(dp.WAITING_SQL, "advisory"):
                        break
                    await asyncio.sleep(0.05)
                else:
                    state["timeouts"] += 1
            finally:
                await conn.close()
        return used
    monkeypatch.setattr(main, "_pc_motion_capacity_used", barrier)
    return state


def _used(lane):
    return int(lane.run(dp.fetch(lane, "SELECT COALESCE(SUM(byte_len), 0) AS n FROM pc_motions"))[0]["n"])


def test_motion_capacity_serialised(lane, env, monkeypatch):
    """T13: two concurrent uploads when only one fits: exactly one is
    applied and the other is 409 motion_capacity. Control: room for both,
    both applied."""
    a, apid, astill = player(lane, env)
    b, bpid, bstill = player(lane, env)
    size = canonical_size(astill)
    assert size == canonical_size(bstill)
    monkeypatch.setattr(pcm, "MOTION_CAPACITY_BYTES", _used(lane) + size + size // 2)
    held = _capacity_barrier(lane, monkeypatch)

    async def both(x, xs, y, ys):
        return await asyncio.gather(dp.upload(lane, x, SECRET, body_for(xs)),
                                    dp.upload(lane, y, SECRET, body_for(ys)))
    results = lane.run(both(a, astill, b, bstill))
    assert held["timeouts"] == 0 and len(held["arrived"]) == 2, held
    assert sorted(r[0] for r in results) == [200, 409], results
    assert [r[1] for r in results if r[0] == 409] == [{"error": "motion_capacity"}]
    assert (motion_row(lane, apid) is None) != (motion_row(lane, bpid) is None)
    c, _cpid, cstill = player(lane, env)
    d, _dpid, dstill = player(lane, env)
    monkeypatch.setattr(pcm, "MOTION_CAPACITY_BYTES", _used(lane) + 2 * size)
    held = _capacity_barrier(lane, monkeypatch)
    results = lane.run(both(c, cstill, d, dstill))
    assert held["timeouts"] == 0 and len(held["arrived"]) == 2, held
    assert [r[0] for r in results] == [200, 200], results


# -- T15, T47: phase C re-checks -----------------------------------------------

def test_motion_requires_session(lane, env, monkeypatch):
    """T15: no session is 401 in phase A with no decode and no charge; a
    session revoked DURING the decode is refused in phase C (charged,
    nothing stored). Control: a held session is applied."""
    steam, pid, still = player(lane, env)
    env.live.discard(steam)
    calls = spy_decode(monkeypatch)
    status, detail = up(lane, steam, body_for(still))
    assert (status, detail, calls) == (401, "session_required", [])
    assert state(lane, pid)["pc_motion_at"] is None
    env.live.add(steam)
    spy_decode(monkeypatch, before=lambda: env.live.discard(steam))
    status, detail = up(lane, steam, body_for(still))
    assert (status, detail) == (401, "session_required")
    assert motion_row(lane, pid) is None and state(lane, pid)["pc_motion_day_count"] == 1
    env.live.add(steam)
    spy_decode(monkeypatch)
    age_pacing(lane, pid)
    status, answer = up(lane, steam, body_for(still))
    assert status == 200 and answer["applied"] is True


def _during_decode(lane, monkeypatch, make_change):
    """Commit a change from another session while the decode runs."""
    def change():
        asyncio.run_coroutine_threadsafe(make_change(), lane.loop).result(60)
    return spy_decode(monkeypatch, before=change)


async def _replace_still(lane, pid):
    h = dp.still_hash("replaced-" + pid)
    async with lane.sm() as db:
        await dp.still_blob(db, h)
        await db.execute(dp.text("UPDATE players SET pc_game_portrait_hash = CAST(:h AS text) "
                                 "WHERE id = CAST(:pid AS uuid)"), {"h": h, "pid": pid})
        await db.commit()


def test_motion_phase_c_rechecks(lane, env, monkeypatch):
    """T47: a selection change, a still replacement, a ban or a lock that
    commits during the decode makes phase C refuse (charged, nothing
    stored). Control: nothing changes, applied."""
    cases = [
        ("selection", lambda steam, pid: dp.execute(
            lane, "UPDATE players SET active_dance_id = CAST(:i AS bigint) WHERE id = CAST(:pid AS uuid)",
            i=lane.items["dance_wave"], pid=pid), (409, {"error": "dance_not_selected"})),
        ("still", lambda steam, pid: _replace_still(lane, pid), (409, {"error": "motion_unbound"})),
        ("ban", lambda steam, pid: dp.ban(lane, steam), (403, {"error": "portrait_refused"})),
        ("lock", lambda steam, pid: dp.execute(
            lane, "UPDATE players SET pc_game_portrait_locked_until = now() + interval '1 day' "
                  "WHERE id = CAST(:pid AS uuid)", pid=pid), (403, "portrait_locked")),
    ]
    for name, make, want in cases:
        steam, pid, still = player(lane, env)
        _during_decode(lane, monkeypatch, lambda s=steam, p=pid, m=make: m(s, p))
        status, detail = up(lane, steam, body_for(still))
        if want[1] == "portrait_locked":
            assert status == 403 and detail["error"] == "portrait_locked", (name, status, detail)
        else:
            assert (status, detail) == want, (name, status, detail)
        assert motion_row(lane, pid) is None and state(lane, pid)["pc_motion_day_count"] == 1
    steam, pid, still = player(lane, env)
    spy_decode(monkeypatch)
    status, answer = up(lane, steam, body_for(still))
    assert status == 200 and answer["applied"] is True


# -- T46, T55: the charge and the 503s ----------------------------------------

def test_motion_charge_before_decode(lane, env, monkeypatch):
    """T46 (route half): a flash-refused container charges pacing and the
    day count; a second attempt inside 30 s is 409 without entering the
    decode pool; an admission 503 charges nothing and leaves the nonce
    unused. Control: an accepted upload charges exactly once."""
    steam, pid, still = player(lane, env)
    calls = spy_decode(monkeypatch)
    status, detail = up(lane, steam, body_for(still, "flash"))
    assert status == 422 and detail["error"] == "motion_flash" and detail["pair"] == [0, 1]
    charged = state(lane, pid)
    assert charged["pc_motion_at"] is not None and charged["pc_motion_day_count"] == 1 and len(calls) == 1
    status, detail = up(lane, steam, body_for(still))
    assert (status, detail["error"], len(calls)) == (409, "retry_after", 1)
    age_pacing(lane, pid)
    before = state(lane, pid)
    held = [(k, pcm.DECODE_ADMISSION.try_claim(k)) for k in ("hold-1", "hold-2", "hold-3")]
    try:
        assert all(t is not None for _k, t in held)
        n = dp.nonce()
        status, detail = up(lane, steam, body_for(still), nonce_value=n)
        assert (status, detail["error"], detail["reason"]) == (503, "motion_busy", "admission")
        assert state(lane, pid) == before and not nonce_used(lane, pid, n) and len(calls) == 1
    finally:
        for k, t in held:
            pcm.DECODE_ADMISSION.release(k, t)
    status, answer = up(lane, steam, body_for(still))
    assert status == 200 and answer["applied"] is True
    assert state(lane, pid)["pc_motion_day_count"] == 2 and len(calls) == 2
    assert pcm.DECODE_ADMISSION.held() == 0


def test_motion_hmac_unconfigured_is_503_first(lane, env, monkeypatch):
    """T55 (M3, the upload half): with no HMAC key the writer answers 503
    before any nonce, decode slot or charge. Control: key configured, the
    normal flow applies."""
    steam, pid, still = player(lane, env)
    calls = spy_decode(monkeypatch)
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")
    n = dp.nonce()
    status, detail = up(lane, steam, body_for(still), nonce_value=n, sig="0" * 64)
    assert (status, detail) == (503, "HMAC not configured")
    assert not nonce_used(lane, pid, n) and state(lane, pid)["pc_motion_at"] is None
    assert pcm.DECODE_ADMISSION.held() == 0 and calls == []
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    status, answer = up(lane, steam, body_for(still))
    assert status == 200 and answer["applied"] is True


# -- T56: the lock each phase takes on the players row ------------------------

_PROBES = (("key share", "FOR KEY SHARE"), ("share", "FOR SHARE"), ("no key update", "FOR NO KEY UPDATE"))


async def _probe(lane, pid):
    """Which row locks another session can take NOW, without waiting."""
    conn = await lane.connect()
    seen = {}
    try:
        for name, clause in _PROBES:
            try:
                async with conn.transaction():
                    await conn.fetchval("SELECT 1 FROM players WHERE id = $1::uuid " + clause + " NOWAIT", pid)
                seen[name] = True
            except asyncpg.LockNotAvailableError:
                seen[name] = False
    finally:
        await conn.close()
    return seen


async def _paused_in_phase_c(lane, steam, pid, body):
    """Hold the capacity lock, so phase C stops right after its row lock."""
    hold = await lane.connect()
    await hold.execute("SELECT pg_advisory_lock(hashtext('pc_motion_capacity'))")
    task = None
    try:
        task = asyncio.ensure_future(dp.upload(lane, steam, SECRET, body))
        assert await dp.wait_for_lock_wait(lane, "advisory", timeout=120)
        seen = await _probe(lane, pid)
    finally:
        await hold.execute("SELECT pg_advisory_unlock(hashtext('pc_motion_capacity'))")
        await hold.close()
    return seen, await task


async def _paused_in_phase_a(lane, steam, pid, body):
    """Hold the request's own nonce, uncommitted, so phase A stops at its
    nonce insert with its row lock held."""
    n = dp.nonce()
    hold = await lane.connect()
    tr = hold.transaction()
    await tr.start()
    await hold.execute("INSERT INTO pc_portrait_nonces (player_id, nonce) VALUES ($1::uuid, $2)", pid, n)
    try:
        task = asyncio.ensure_future(dp.upload(lane, steam, SECRET, body, nonce_value=n))
        assert await dp.wait_for_lock_wait(lane, "transactionid", timeout=60)
        seen = await _probe(lane, pid)
    finally:
        await tr.rollback()
        await hold.close()
    return seen, await task


def test_motion_row_locks_by_phase(lane, env):
    """T56 (M4): phase C holds the players row FOR SHARE -- a compatible
    reader (KEY SHARE, SHARE) is not blocked and a NO KEY UPDATE writer is --
    while phase A holds FOR NO KEY UPDATE (SHARE blocked, KEY SHARE not).
    Both uploads then complete."""
    steam, pid, still = player(lane, env)
    seen, result = lane.run(_paused_in_phase_c(lane, steam, pid, body_for(still)))
    assert seen == {"key share": True, "share": True, "no key update": False}, seen
    assert result[0] == 200 and result[1]["applied"] is True
    steam, pid, still = player(lane, env)
    seen, result = lane.run(_paused_in_phase_a(lane, steam, pid, body_for(still)))
    assert seen == {"key share": True, "share": False, "no key update": False}, seen
    assert result[0] == 200 and result[1]["applied"] is True


# -- T58: the same path repairs the binding (L3) ------------------------------

def test_motion_same_repairs_the_descriptor(lane, env):
    """T58 (L3): the still's descriptor changes under the same hash; the same
    bytes re-uploaded with the new descriptor answer same AND repair the
    motion row's static_descriptor, charging nothing -- in phase A (same
    source) and in phase C (same canonical). Control: an unchanged
    descriptor short-circuits with no write."""
    steam, pid, still = player(lane, env)
    body = body_for(still)
    assert up(lane, steam, body)[0] == 200

    def restill(descriptor):
        lane.run(dp.execute(lane, "UPDATE players SET pc_game_portrait_descriptor = CAST(:d AS text) "
                                  "WHERE id = CAST(:pid AS uuid)", d=descriptor, pid=pid))
    d2 = dp.DESC.replace("g=1.2.3", "g=1.2.4")
    restill(d2)
    before = state(lane, pid)
    status, answer = up(lane, steam, body, descriptor=d2)
    assert status == 200 and answer["reason"] == "same" and answer.get("rebound") is True
    assert motion_row(lane, pid)["static_descriptor"] == d2 and state(lane, pid) == before
    d3 = dp.DESC.replace("g=1.2.3", "g=1.2.5")
    restill(d3)
    age_pacing(lane, pid)
    status, answer = up(lane, steam, body_for(still, "smooth9"), descriptor=d3)
    assert status == 200 and answer["reason"] == "same" and answer.get("rebound") is True
    assert motion_row(lane, pid)["static_descriptor"] == d3
    stored = motion_row(lane, pid)["stored_at"]
    status, answer = up(lane, steam, body, descriptor=d3)
    assert status == 200 and answer == {"applied": False, "reason": "same",
                                        "motion_hash": motion_row(lane, pid)["motion_hash"]}
    assert motion_row(lane, pid)["stored_at"] == stored
