"""Bans part 2a, FIX-2 class IV, at the real team and 1v2 report routes on the
hold suite's case schema (test_match_hold_pg, test_match_hold_reports_pg).

  * A ban that commits after the route's early (unlocked) check and before
    the receipt's transaction reads it refuses the report: the receipt reads
    the ban of every account the report names, and the series row, under the
    identity guards and before its first write. Nothing is journaled and no
    window row is written.
  * A journaled window whose settle a ban refuses is closed as refused: its
    terminal field superseded_at is set and every report of the game is kept;
    a later janitor tick settles nothing.
Each with a mutant that removes the read (or the close) and turns it red.
  * The settle's ban gate under a report window asks only for keys the
    window's guard already holds (the TYPED P2a entry of the lock census): an
    instrument reads this backend's granted advisory locks at every gate call
    made while the transaction holds any; the mutant that adds an id is seen.

The seats get numeric ids (a ban row's key is numeric, player_bans'
check), made up per case.
"""
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

import main  # noqa: E402
from ban_sweep_pg_bounds import bounded_pg  # noqa: E402,F401  (autouse: every session bounded)
import test_ban_sweep_live as L  # noqa: E402
import test_match_hold_pg as hold_test  # noqa: E402
import test_match_hold_reports_pg as R  # noqa: E402

MODES = ("team", "ovt")


async def _seed_numeric(conn, n):
    out = []
    for _ in range(n):
        steam = "7656119" + "%010d" % (uuid.uuid4().int % 10 ** 10)
        pid = await conn.fetchval(
            "INSERT INTO players (steam_id, display_name) VALUES ($1, $2) RETURNING id",
            steam, "bsw " + steam[-4:])
        out.append((pid, steam))
    return out


@pytest.fixture(autouse=True)
def _numeric_seats(monkeypatch):
    monkeypatch.setattr(hold_test, "seed_players", _seed_numeric)


async def _rows(env, s):
    j = await env.conn.fetchval("SELECT count(*) FROM match_report_journal WHERE room_name = $1", s.room)
    w = await env.conn.fetchval("SELECT count(*) FROM match_report_windows WHERE room_name = $1", s.room)
    return j, w


def _ban_between(monkeypatch, env, target):
    """Commit a ban of `target` after the route's early check, right before
    the receipt's transaction reads anything under its guards."""
    orig = main._report_window_receive

    async def wrapped(db, mode, report):
        await L._ban(env.sm, target)
        return await orig(db, mode, report)
    monkeypatch.setattr(main, "_report_window_receive", wrapped)


def _receipt_case(monkeypatch, mode, mutant=False):
    out = {}

    async def body(env):
        R._mount(env, monkeypatch)
        s = await hold_test.seed_series(env.conn, mode)
        g = (await hold_test.game_start(env, s, 0))["game_id"]
        _ban_between(monkeypatch, env, s.steam(len(s.seats) - 1))
        if mutant:
            async def none(*a, **k):
                return None
            monkeypatch.setattr(main, "_ban_gate_any_or_raise", none)
            monkeypatch.setattr(main, "_refuse_record_ended_by_ban", lambda *a, **k: None)
        r = await R.post_report(mode, s, 0, g)
        out["status"], out["body"] = r.status_code, r.text[:200]
        out["rows"] = await _rows(env, s)
    hold_test.run_env(monkeypatch, body, prefix="bsiv")
    return out


@pytest.mark.parametrize("mode", MODES)
def test_iv_a_ban_committed_before_the_receipt_reads_refuses_and_journals_nothing(monkeypatch, mode):
    out = _receipt_case(monkeypatch, mode)
    assert out["status"] == 409 and out["rows"][0] == 0, out


@pytest.mark.parametrize("mode", MODES)
def test_iv_mutant_without_the_receipts_read_the_report_is_journaled(monkeypatch, mode):
    out = _receipt_case(monkeypatch, mode, mutant=True)
    assert out["status"] == 202 and out["rows"][0] == 1, out


def _window_case(monkeypatch, mode, mutant=False):
    out = {}
    if mutant:
        def refusal(exc, in_window):
            return main._mrw_mod().PermanentReportRefusal(exc) if in_window else exc
        monkeypatch.setattr(main, "_ban_writer_refusal", refusal)

    async def body(env):
        R._mount(env, monkeypatch)
        s, g, _want = await R._two_filed(env, mode)
        await L._ban(env.sm, s.steam(len(s.seats) - 1))
        first = await main._report_window_janitor()
        second = await main._report_window_janitor()
        w, j = await R.window_state(env, s, g)
        out.update(first=first, second=second, superseded=w["superseded_at"] is not None,
                   settled=w["settled_at"] is not None, states=sorted(v[1] for v in j.values()),
                   recorded=len(await R.recorded(env, mode, s)))
    hold_test.run_env(monkeypatch, body, prefix="bsiv")
    return out


@pytest.mark.parametrize("mode", MODES)
def test_iv_a_window_a_ban_refuses_is_closed_as_refused(monkeypatch, mode):
    out = _window_case(monkeypatch, mode)
    assert (out["superseded"], out["settled"], out["states"], out["recorded"],
            out["first"].get("refused"), out["second"]) == \
        (True, False, ["kept", "kept"], 0, 1, {}), out


@pytest.mark.parametrize("mode", MODES)
def test_iv_mutant_a_refusal_that_does_not_close_leaves_the_window_open(monkeypatch, mode):
    out = _window_case(monkeypatch, mode, mutant=True)
    assert out["superseded"] is False and out["second"].get("refused") == 1, out


# The settle gate under a window (moved from test_ban_sweep_locks_pg.py: the hold
# harness builds its own case schema, which the module-wide one there refuses).
_HELD_SQL = (
    "SELECT l.mode, ((l.classid::bigint << 32) | l.objid::bigint) AS k FROM pg_locks l"
    " WHERE l.pid = pg_backend_pid() AND l.locktype = 'advisory' AND l.granted")

def _instrument(monkeypatch, book):
    orig = main._ban_lock_and_gate

    async def inst(db, steam_ids, *a, actor=None, exclusive=(), **kw):
        held = (await db.execute(text(_HELD_SQL))).all()
        if held:
            keys = {}
            for mode_, k in held:
                keys[k] = keys.get(k) == "ExclusiveLock" and "ExclusiveLock" or mode_
            want = [(s, "ShareLock") for s in [*steam_ids, actor] if s] + \
                   [(s, "ExclusiveLock") for s in (exclusive or ()) if s]
            for s, m in want:
                h = (await db.execute(text("SELECT hashtext(CAST(:s AS text))::bigint"), {"s": s})).scalar()
                ok = h in keys and (m == "ShareLock" or keys[h] == "ExclusiveLock")
                book.append((s, m, ok))
        return await orig(db, steam_ids, *a, actor=actor, exclusive=exclusive, **kw)
    monkeypatch.setattr(main, "_ban_lock_and_gate", inst)


def _window_settles(monkeypatch, extra=None):
    import test_match_hold_pg as hold_test
    import test_match_hold_reports_pg as R
    book = []
    _instrument(monkeypatch, book)
    if extra is not None:
        orig = main._settle_writer_ban_check

        async def mut(db, steam_ids, reporter, **kw):
            return await orig(db, [*steam_ids, extra], reporter, **kw)
        monkeypatch.setattr(main, "_settle_writer_ban_check", mut)

    async def body(env):
        R._mount(env, monkeypatch)
        for mode_ in ("team", "ovt"):
            s, g, _want = await R._two_filed(env, mode_)
            out = await main._report_window_janitor()
            assert out.get("settled") == 1, (mode_, out)
    hold_test.run_env(monkeypatch, body, prefix="bsv")
    return book


def test_v_the_settle_gate_asks_only_keys_the_window_guard_holds(monkeypatch):
    book = _window_settles(monkeypatch)
    assert book and all(ok for _s, _m, ok in book), book


def test_v_mutant_a_settle_gate_asking_a_new_key_is_seen(monkeypatch):
    book = _window_settles(monkeypatch, extra="76561190529999999")
    assert [b for b in book if b[0] == "76561190529999999" and not b[2]], book


# ---------------------------------------------------------------- FIX-3 2 e
# The close in match_report_window._release_held: held reports released at the
# hold's entry whose settle a ban refuses close the window as refused. The ban
# is the player_bans row alone, written after the reports were held and before
# the entry: a whole ban also voids the series and ends its holds, so no entry
# and no release follow it (that path closes through the janitor, the tests
# above). This proves what the release does when its settle reads a ban.
_RELEASE_CLOSE = ("                await close_refused(db, room, game_id, now)\n"
                  "                break\n")


def _release_close_mutant():
    import inspect
    import textwrap
    mrw = main._mrw_mod()
    src = textwrap.dedent(inspect.getsource(mrw._release_held))
    assert src.count(_RELEASE_CLOSE) == 1
    ns = dict(vars(mrw))
    exec(compile(src.replace(_RELEASE_CLOSE, "                break\n"), "<mutant>", "exec"), ns)
    return ns["_release_held"]


def _release_case(monkeypatch, mode, banned=True, mutant=False):
    out = {}
    if mutant:
        monkeypatch.setattr(main._mrw_mod(), "_release_held", _release_close_mutant())

    async def body(env):
        R._mount(env, monkeypatch)
        s, g, hid, present = await R._held_game_over(env, mode)
        await hold_test.claim(env, s, 1, hid)
        await hold_test.beat(env, s, present[0], seen=[(10 + present[0], s.steam(present[0])),
                                                       (21, s.steam(1))])
        await hold_test.bind(env, s, 1, hid, 21)
        await hold_test.beat(env, s, present[-1], seen=[(10 + present[-1], s.steam(present[-1])),
                                                        (21, s.steam(1))])
        if banned:
            await env.conn.execute(
                "INSERT INTO admin_users (steam_id) VALUES ('76561190000000001') ON CONFLICT DO NOTHING")
            await env.conn.execute(
                "INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
                " VALUES ($1, 'ban-sweep release', '76561190000000001', NOW(), NOW() + INTERVAL '1 hour')",
                s.steam(present[0]))
        en = await hold_test.entered(env, s, 1, hid, g, 21)
        w, j = await R.window_state(env, s, g)
        out.update(entered=en.get("status"), superseded=w["superseded_at"] is not None,
                   settled=w["settled_at"] is not None, states=sorted(v[1] for v in j.values()),
                   held=len(present), recorded=len(await R.recorded(env, mode, s)))
    hold_test.run_env(monkeypatch, body, prefix="bsive")
    return out


@pytest.mark.parametrize("mode", MODES)
def test_iv_e_a_held_report_released_after_a_ban_is_refused_and_the_window_closes(monkeypatch, mode):
    out = _release_case(monkeypatch, mode)
    assert (out["superseded"], out["settled"], out["states"], out["recorded"]) == \
        (True, False, ["kept"] * out["held"], 0), out


@pytest.mark.parametrize("mode", MODES)
def test_iv_e_mutant_without_the_release_close_the_window_stays_open(monkeypatch, mode):
    out = _release_case(monkeypatch, mode, mutant=True)
    assert out["superseded"] is False and out["settled"] is False and out["recorded"] == 0, out


@pytest.mark.parametrize("mode", MODES)
def test_iv_e_control_the_same_release_with_no_ban_settles(monkeypatch, mode):
    out = _release_case(monkeypatch, mode, banned=False)
    assert (out["entered"], out["settled"], out["recorded"]) == ("entered", True, 1), out
