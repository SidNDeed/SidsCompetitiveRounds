"""Dance cards: the clear paths, data deletion and the janitor's motion
cleanups (design S3.5-S3.6) against a real PostgreSQL -- T31, T32, T35, T52,
and T64-T66 (numbered after T63).

Each test is one named assertion; the mutation that must fail it is planted
by the lane's mutation runner and recorded in its log, and the test's own
passing case is the control (#391). The HMAC key is a random test value, the
admin check and the strict session check are replaced, and every player is
synthetic.

The lane is shared by every live module of a run, so the janitor sees the
other tests' players too: `sweep` runs passes until one finds nothing, and
every assertion names this test's own rows only.
"""
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

SECRET = "dance-test-" + uuid.uuid4().hex
ADMIN = "76561190000009999"


@pytest.fixture(scope="module")
def lane():
    dp.require_live_pg()
    return dp.shared_lane()


@pytest.fixture
def env(monkeypatch, lane):
    sessions = dp.Sessions()
    dp.open_routes(monkeypatch, sessions, SECRET)
    # the deletion route's strict session arm runs only with a Steam key set
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)

    async def _admin_ok(*_args, **_kwargs):
        return None
    monkeypatch.setattr(main, "_require_admin", _admin_ok)
    return sessions


def player(lane, sessions, **kw):
    steam = dp.steam_id()
    pid, still = lane.run(dp.make_player(lane, steam, **kw))
    sessions.live.add(steam)
    return steam, pid, still


def state(lane, pid):
    return dict(lane.run(dp.fetch(
        lane, "SELECT active_dance_id, pc_motion_at, pc_motion_day, pc_motion_day_count, deleted_at "
              "FROM players WHERE id = CAST(:pid AS uuid)", pid=pid))[0])


def motion(lane, pid):
    rows = lane.run(dp.fetch(lane, "SELECT motion_hash FROM pc_motions WHERE player_id = CAST(:pid AS uuid)", pid=pid))
    return rows[0]["motion_hash"] if rows else None


def sql(lane, statement, **params):
    lane.run(dp.execute(lane, statement, **params))


def age_motion(lane, pid, hours):
    sql(lane, "UPDATE pc_motions SET stored_at = now() - make_interval(hours => CAST(:h AS integer)) "
              "WHERE player_id = CAST(:pid AS uuid)", h=hours, pid=pid)


def replace_still(lane, pid, tag):
    """The owner's game still replaced by another blob (the binding breaks)."""
    h = dp.still_hash(tag)

    async def go():
        async with lane.sm() as db:
            await dp.still_blob(db, h)
            await db.execute(text("UPDATE players SET pc_game_portrait_hash = CAST(:h AS text) "
                                  "WHERE id = CAST(:pid AS uuid)"), {"h": h, "pid": pid})
            await db.commit()
    lane.run(go())


def admin_clear(lane, steam, lock_days=0):
    async def go():
        async with lane.sm() as db:
            try:
                return 200, await main.admin_pc_portrait_clear(
                    {"admin_steam_id": ADMIN, "steam_id": steam, "lock_days": lock_days,
                     "signature": "0" * 64}, db=db)
            except main.HTTPException as ex:
                return ex.status_code, ex.detail
    return lane.run(go())


def delete_data(lane, steam):
    async def go():
        async with lane.sm() as db:
            try:
                return 200, await main.delete_player_data(
                    steam, dp.Req(path="/api/v1/players/" + steam + "/data"),
                    sig=dp.sign(SECRET, "delete:" + steam), _slot=None, db=db)
            except main.HTTPException as ex:
                return ex.status_code, ex.detail
    return lane.run(go())


class _Hooked:
    """A session that runs `hook` once, just before the first statement whose
    text holds `marker` and whose binds name `pid` -- a write committed by
    another transaction between the janitor's candidate read and its lock."""

    def __init__(self, db, marker, pid, hook):
        self._db, self._marker, self._pid, self._hook = db, marker, pid, hook
        self.fired = False

    async def execute(self, statement, params=None):
        if (not self.fired and self._marker in " ".join(str(statement).split())
                and (params or {}).get("pid") == self._pid):
            self.fired = True
            await self._hook()
        return await self._db.execute(statement, params)

    async def commit(self):
        return await self._db.commit()

    async def rollback(self):
        return await self._db.rollback()


def janitor(lane, marker=None, pid=None, hook=None):
    async def go():
        async with lane.sm() as db:
            session = db if hook is None else _Hooked(db, marker, pid, hook)
            result = await main._pc_motion_janitor(session)
            if hook is not None:
                assert session.fired, "the hook never ran: its statement was not reached"
            return result
    return lane.run(go())


def sweep(lane):
    """Janitor passes until one finds nothing; at most five."""
    for _ in range(5):
        if janitor(lane) == (0, 0):
            return
    raise AssertionError("the janitor kept finding work")


# -- T31: both clear paths remove the motion ---------------------------------------

def test_clear_unit_removes_motion(lane, env):
    """T31 (S3.5): the admin clear and data deletion both remove the stored
    motion, through the clear unit they share. Control: a player without a
    motion clears cleanly. Mutation: the delete in the admin route only."""
    steam, pid, still = player(lane, env)
    lane.run(dp.put_motion(lane, pid, still))
    assert motion(lane, pid) is not None
    status, answer = admin_clear(lane, steam)
    assert status == 200 and answer["cleared"] is True, (status, answer)
    assert motion(lane, pid) is None
    steam, pid, still = player(lane, env)
    lane.run(dp.put_motion(lane, pid, still))
    status, answer = delete_data(lane, steam)
    assert status == 200, (status, answer)
    assert state(lane, pid)["deleted_at"] is not None and motion(lane, pid) is None
    # control: nothing stored, the clear still answers
    steam, pid, _still = player(lane, env, dance=None)
    status, answer = admin_clear(lane, steam)
    assert status == 200 and answer["cleared"] is True and motion(lane, pid) is None, (status, answer)


# -- T32: deletion resets the dance columns ------------------------------------------

def test_deletion_nulls_dance_columns(lane, env):
    """T32 (S3.5): after data deletion the selection is NULL and the motion
    counters are NULL, NULL and 0 -- the row is anonymised, never deleted.
    Control: a player who never selected deletes to the same state.
    Mutation: the UPDATE omitted."""
    steam, pid, _still = player(lane, env)
    sql(lane, "UPDATE players SET pc_motion_at = now(), pc_motion_day = CURRENT_DATE, pc_motion_day_count = 3 "
              "WHERE id = CAST(:pid AS uuid)", pid=pid)
    before = state(lane, pid)
    assert before["active_dance_id"] is not None and before["pc_motion_day_count"] == 3, before
    status, answer = delete_data(lane, steam)
    assert status == 200, (status, answer)
    after = state(lane, pid)
    assert after["deleted_at"] is not None
    assert (after["active_dance_id"], after["pc_motion_at"], after["pc_motion_day"],
            after["pc_motion_day_count"]) == (None, None, None, 0), after
    # control: never selected
    steam, pid, _still = player(lane, env, dance=None)
    assert delete_data(lane, steam)[0] == 200
    after = state(lane, pid)
    assert (after["active_dance_id"], after["pc_motion_at"], after["pc_motion_day"],
            after["pc_motion_day_count"]) == (None, None, None, 0), after


# -- T35: the binding arm ---------------------------------------------------------------

def test_janitor_motion_cleanup(lane, env):
    """T35 (S3.6, S3.4): a motion whose binding to the owner's game still is
    broken and which was stored more than 24 hours ago is deleted; a broken
    one stored an hour ago is kept. Control: a bound motion stored 25 hours
    ago is kept. Mutations: the binding ignored; the age ignored."""
    _s, old_broken, still = player(lane, env)
    lane.run(dp.put_motion(lane, old_broken, still))
    age_motion(lane, old_broken, 25)
    replace_still(lane, old_broken, "t35-old-" + old_broken)
    _s, fresh_broken, still = player(lane, env)
    lane.run(dp.put_motion(lane, fresh_broken, still))
    age_motion(lane, fresh_broken, 1)
    replace_still(lane, fresh_broken, "t35-fresh-" + fresh_broken)
    _s, old_bound, still = player(lane, env)
    kept = lane.run(dp.put_motion(lane, old_bound, still))
    age_motion(lane, old_bound, 25)
    sweep(lane)
    assert motion(lane, old_broken) is None
    assert motion(lane, fresh_broken) is not None
    assert motion(lane, old_bound) == kept


# -- T52: ownership, never readiness ------------------------------------------------------

def test_janitor_keeps_unready_selection(lane, env, monkeypatch):
    """T52 (S3.6): a selection whose ownership has gone is nulled, and the same
    pass deletes its motion; an owned selection of an unready item is kept,
    and so is a selection the exemption owns. Control: an owned, ready
    selection is kept. Mutations: null on unready; the exemption ignored."""
    bounce, robot = lane.items["dance_bounce"], lane.items["dance_robot"]
    _s, lost, still = player(lane, env)
    lane.run(dp.put_motion(lane, lost, still))
    sql(lane, "DELETE FROM player_items WHERE player_id = CAST(:pid AS uuid)", pid=lost)
    _s, unready, _still = player(lane, env, dance="dance_robot")
    exempt_steam, exempt, _still = player(lane, env, owned=False)
    _s, kept, _still = player(lane, env)
    monkeypatch.setattr(main, "SHOP_OWNER_STEAM_IDS", {exempt_steam})
    sql(lane, "UPDATE shop_items SET catalog_ready = false WHERE sku = 'dance_robot'")
    try:
        sweep(lane)
    finally:
        sql(lane, "UPDATE shop_items SET catalog_ready = true WHERE sku = 'dance_robot'")
    assert state(lane, lost)["active_dance_id"] is None and motion(lane, lost) is None
    assert state(lane, unready)["active_dance_id"] == robot
    assert state(lane, exempt)["active_dance_id"] == bounce
    assert state(lane, kept)["active_dance_id"] == bounce


# -- T64: the selection arm ----------------------------------------------------------------

def test_janitor_deletes_a_motion_for_another_selection(lane, env):
    """T64 (S3.6): a motion whose owner's selection is none, or another item,
    is deleted whatever its age. Control: a motion for the selected item is
    kept. Mutation: the selection ignored."""
    wave = lane.items["dance_wave"]
    _s, none, still = player(lane, env)
    lane.run(dp.put_motion(lane, none, still))
    sql(lane, "UPDATE players SET active_dance_id = NULL WHERE id = CAST(:pid AS uuid)", pid=none)
    _s, other, still = player(lane, env)
    lane.run(dp.put_motion(lane, other, still))
    lane.run(dp.own(lane, other, wave))
    sql(lane, "UPDATE players SET active_dance_id = CAST(:w AS bigint) WHERE id = CAST(:pid AS uuid)",
        w=wave, pid=other)
    _s, same, still = player(lane, env)
    kept = lane.run(dp.put_motion(lane, same, still))
    sweep(lane)
    assert motion(lane, none) is None
    assert motion(lane, other) is None
    assert motion(lane, same) == kept


# -- T65, T66: each arm re-checks under its lock (#208) --------------------------------------

def test_janitor_rechecks_ownership_under_its_lock(lane, env):
    """T65 (#208): the ownership the janitor read before its lock is read
    again once the lock is held -- a purchase committed in between keeps the
    selection. Control: the same state without the purchase is nulled.
    Mutation: the UPDATE without its re-check."""
    bounce = lane.items["dance_bounce"]
    _s, pid, _still = player(lane, env)
    sql(lane, "DELETE FROM player_items WHERE player_id = CAST(:pid AS uuid)", pid=pid)

    async def purchase():
        await dp.own(lane, pid, bounce)
    janitor(lane, "FOR NO KEY UPDATE SKIP LOCKED", pid, purchase)
    assert state(lane, pid)["active_dance_id"] == bounce
    # control
    _s, pid, _still = player(lane, env)
    sql(lane, "DELETE FROM player_items WHERE player_id = CAST(:pid AS uuid)", pid=pid)
    sweep(lane)
    assert state(lane, pid)["active_dance_id"] is None


def test_janitor_rechecks_a_stale_motion_under_its_lock(lane, env):
    """T66 (#208): a motion the janitor read as stale is judged again once its
    lock is held -- a selection that returned to the motion's item in between
    keeps it. Control: the same state left alone is deleted. Mutation: the
    DELETE without its re-check."""
    bounce, wave = lane.items["dance_bounce"], lane.items["dance_wave"]

    def stale_player():
        _s, pid, still = player(lane, env)
        h = lane.run(dp.put_motion(lane, pid, still))
        lane.run(dp.own(lane, pid, wave))
        sql(lane, "UPDATE players SET active_dance_id = CAST(:w AS bigint) WHERE id = CAST(:pid AS uuid)",
            w=wave, pid=pid)
        return pid, h
    pid, h = stale_player()

    async def reselect():
        await dp.execute(lane, "UPDATE players SET active_dance_id = CAST(:b AS bigint) "
                               "WHERE id = CAST(:pid AS uuid)", b=bounce, pid=pid)
    janitor(lane, "FOR UPDATE SKIP LOCKED", pid, reselect)
    assert motion(lane, pid) == h
    # control
    pid, _h = stale_player()
    sweep(lane)
    assert motion(lane, pid) is None
