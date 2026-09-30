"""Dance cards: the selection route (design S2.10; section 12 M3, M4, L4)
against a real PostgreSQL -- T16, T55 (the selection half), T56 (the
selection's lock) and T59.

Each test is one named assertion; the mutation that must fail it is planted
by the lane's mutation runner and recorded in its log, and the test's own
passing case is the control (#391). The HMAC key is a random test value, the
strict session check is replaced (dance_pg_harness.Sessions), and every
player is synthetic.
"""
import asyncio
import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import dance_pg_harness as dp  # noqa: E402
import main  # noqa: E402

SECRET = "dance-test-" + uuid.uuid4().hex


@pytest.fixture(scope="module")
def lane():
    dp.require_live_pg()
    return dp.shared_lane()


@pytest.fixture
def env(monkeypatch, lane):
    sessions = dp.Sessions()
    dp.open_routes(monkeypatch, sessions, SECRET)
    return sessions


def player(lane, sessions, **kw):
    steam = dp.steam_id()
    pid, still = lane.run(dp.make_player(lane, steam, **kw))
    sessions.live.add(steam)
    return steam, pid, still


def sel(lane, steam, item, **kw):
    return lane.run(dp.select_dance(lane, steam, SECRET, item, **kw))


def own(lane, pid, item):
    lane.run(dp.own(lane, pid, item))


def motion(lane, pid):
    rows = lane.run(dp.fetch(lane, "SELECT motion_hash FROM pc_motions WHERE player_id = CAST(:pid AS uuid)", pid=pid))
    return rows[0]["motion_hash"] if rows else None


def actives(lane, pid):
    """Every active_* column of the player's row, by name."""
    names = [r["column_name"] for r in lane.run(dp.fetch(
        lane, "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() "
              "AND table_name = 'players' AND column_name LIKE 'active%' ORDER BY column_name"))]
    assert "active_dance_id" in names and "active_title_id" in names, names
    row = lane.run(dp.fetch(lane, "SELECT " + ", ".join(names) + " FROM players WHERE id = CAST(:pid AS uuid)",
                            pid=pid))[0]
    return {n: row[n] for n in names}


def nonce_used(lane, pid, n):
    return bool(lane.run(dp.fetch(
        lane, "SELECT 1 FROM pc_portrait_nonces WHERE player_id = CAST(:pid AS uuid) "
              "AND nonce = CAST(:n AS text)", pid=pid, n=n)))


# -- T16: the route ---------------------------------------------------------------

def test_selection_route(lane, env, monkeypatch):
    """T16 (S2.10): an item of another kind is 422 item_invalid, as is an id
    naming nothing; an unready dance 403 dance_not_ready, even owned; an
    unowned dance 403 dance_not_owned, while the exemption owns it through
    _auto_owned; the unchanged selection answers applied false and keeps the
    stored motion; a change applies, deletes the motion and writes no other
    active_* column (the title stays on); a nonce is single-use. Control:
    selecting 0 clears, and 0 again is unchanged. Mutation: the selection
    written where _set_active_cosmetic writes a dance (active_title_id)."""
    steam, pid, still = player(lane, env)                  # dance_bounce selected and owned
    bounce, wave, robot = (lane.items[s] for s in ("dance_bounce", "dance_wave", "dance_robot"))
    title = lane.items["title_dancer"]
    lane.run(dp.execute(lane, "UPDATE players SET active_title_id = CAST(:t AS bigint) "
                              "WHERE id = CAST(:pid AS uuid)", t=title, pid=pid))
    h = lane.run(dp.put_motion(lane, pid, still))
    before = actives(lane, pid)
    assert before["active_dance_id"] == bounce and before["active_title_id"] == title
    assert sel(lane, steam, title) == (422, {"error": "item_invalid"})
    assert sel(lane, steam, 987654321) == (422, {"error": "item_invalid"})
    own(lane, pid, robot)
    lane.run(dp.execute(lane, "UPDATE shop_items SET catalog_ready = false WHERE sku = 'dance_robot'"))
    try:
        assert sel(lane, steam, robot) == (403, {"error": "dance_not_ready"})
    finally:
        lane.run(dp.execute(lane, "UPDATE shop_items SET catalog_ready = true WHERE sku = 'dance_robot'"))
    assert sel(lane, steam, wave) == (403, {"error": "dance_not_owned"})
    assert actives(lane, pid) == before and motion(lane, pid) == h
    # unchanged: applied false, the motion kept
    assert sel(lane, steam, bounce) == (200, {"applied": False, "reason": "same", "item_id": bounce})
    assert motion(lane, pid) == h
    # the exemption owns wave: the change applies, deletes the motion, and
    # writes active_dance_id alone
    monkeypatch.setattr(main, "SHOP_OWNER_STEAM_IDS", {steam})
    n = dp.nonce()
    assert sel(lane, steam, wave, nonce_value=n) == (200, {"applied": True, "item_id": wave})
    assert actives(lane, pid) == dict(before, active_dance_id=wave) and motion(lane, pid) is None
    # the nonce is single-use
    assert sel(lane, steam, bounce, nonce_value=n) == (403, {"error": "nonce_replayed"})
    assert actives(lane, pid)["active_dance_id"] == wave
    # control: 0 clears (the motion with it), and 0 again is unchanged
    lane.run(dp.put_motion(lane, pid, still, dance="dance_wave", tag="m2"))
    assert sel(lane, steam, 0) == (200, {"applied": True, "item_id": 0})
    assert actives(lane, pid) == dict(before, active_dance_id=None) and motion(lane, pid) is None
    assert sel(lane, steam, 0) == (200, {"applied": False, "reason": "same", "item_id": 0})


# -- T55: an unconfigured key is 503 before the nonce ---------------------------------

def test_selection_hmac_unconfigured_is_503_first(lane, env, monkeypatch):
    """T55 (M3), the selection half: with the HMAC key unconfigured the
    selection is 503 before its nonce is consumed or anything is written.
    Control: configured, the same request -- the same nonce, still unused --
    applies."""
    steam, pid, still = player(lane, env)
    wave = lane.items["dance_wave"]
    own(lane, pid, wave)
    h = lane.run(dp.put_motion(lane, pid, still))
    before = actives(lane, pid)
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")
    n = dp.nonce()
    assert sel(lane, steam, wave, nonce_value=n, sig="0" * 64) == (503, "HMAC not configured")
    assert not nonce_used(lane, pid, n)
    assert actives(lane, pid) == before and motion(lane, pid) == h
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    assert sel(lane, steam, wave, nonce_value=n) == (200, {"applied": True, "item_id": wave})
    assert nonce_used(lane, pid, n)


# -- T56: the selection's row lock ------------------------------------------------------

async def _paused_at_nonce(lane, steam, pid, item):
    """Hold the request's own nonce, uncommitted, so the route stops at its
    nonce insert with its row lock held; probe; let it go."""
    n = dp.nonce()
    hold = await lane.connect()
    tr = hold.transaction()
    await tr.start()
    await hold.execute("INSERT INTO pc_portrait_nonces (player_id, nonce) VALUES ($1::uuid, $2)", pid, n)
    task = None
    try:
        task = asyncio.ensure_future(dp.select_dance(lane, steam, SECRET, item, nonce_value=n))
        assert await dp.wait_for_lock_wait(lane, "transactionid", timeout=60)
        seen = await dp.row_lock_probe(lane, pid)
    finally:
        await tr.rollback()
        await hold.close()
    return seen, await task


def test_selection_row_lock(lane, env):
    """T56 (M4), the selection's part: S2.10 holds the players row FOR NO KEY
    UPDATE, since its transaction updates the row -- a KEY SHARE reader (a
    foreign-key check) is not blocked; SHARE (the motion upload's phase C)
    and NO KEY UPDATE are. Then it completes."""
    steam, pid, _still = player(lane, env)
    wave = lane.items["dance_wave"]
    own(lane, pid, wave)
    seen, result = lane.run(_paused_at_nonce(lane, steam, pid, wave))
    assert seen == {"key share": True, "share": False, "no key update": False}, seen
    assert result == (200, {"applied": True, "item_id": wave})


# -- T59: the item id is parsed before any SQL (L4) ---------------------------------

class _NoSQL:
    """A session that fails the test if the route runs any statement."""

    async def execute(self, *args, **kwargs):
        raise AssertionError("SQL ran before the item id was parsed")

    async def rollback(self):
        return None

    async def commit(self):
        raise AssertionError("commit before the item id was parsed")


def test_selection_item_id_parsed_before_sql(lane, env):
    """T59 (L4): an item id outside [0, 2^63 - 1], or not canonical decimal,
    is 422 item_invalid before any SQL runs (a session that fails on any
    statement proves it). The largest BIGINT passes the parse and is refused
    by the item check, never by a database range error. Control: a valid id
    in range applies."""
    steam, pid, _still = player(lane, env)
    for raw in ("9223372036854775808", "18446744073709551616", "99999999999999999999", "-1", "01", "+1",
                " 1", "1 ", "1\n", "1e3", "0x10", "", "1.0", "\u0661", "\uff11"):
        status, detail = lane.run(dp.select_dance(lane, steam, SECRET, raw, db=_NoSQL()))
        assert (status, detail) == (422, {"error": "item_invalid"}), repr(raw)
    assert sel(lane, steam, "9223372036854775807") == (422, {"error": "item_invalid"})
    wave = lane.items["dance_wave"]
    own(lane, pid, wave)
    assert sel(lane, steam, str(wave)) == (200, {"applied": True, "item_id": wave})
