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
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

import main  # noqa: E402
import test_ban_sweep_live as L  # noqa: E402
import test_match_hold_pg as hold_test  # noqa: E402
import test_match_hold_reports_pg as R  # noqa: E402

MODES = ("team", "ovt")


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
