"""NX6: account deletion clears the Stage 2 readmission tables (in the form
of the FFA S8 scrub).

After delete_player_data no table migration 383 created holds the deleted
player's id or Steam id in any column, read as the whole row's text: the
player's live hold ended and was deleted with its attempt and open-attempt
rows, the player's presence row and journal rows are gone, another
fighter's beat and another reporter's journaled payload keep their rows
with the Steam id replaced, and a window the player settled keeps its
result with settled_reporter_id NULL.

Runs on the hold suite's case schema (its Env and seeding).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))
sys.path.insert(0, HERE)

import cf_asm  # noqa: E402
import test_match_hold_pg as hold_test  # noqa: E402
import test_match_hold_reports_pg as reports_test  # noqa: E402
import main  # noqa: E402

NEW_TABLES = ("match_games", "match_seat_presence", "match_seat_holds",
              "match_hold_open_attempts", "match_hold_attempts",
              "match_report_windows", "match_report_journal")


async def _naming(env, needle):
    out = {}
    for t in NEW_TABLES:
        n = await env.conn.fetchval(
            "SELECT count(*) FROM %s x WHERE strpos(CAST(x AS text), $1) > 0" % t, needle)
        if n:
            out[t] = n
    return out


def test_nx6_deletion_leaves_no_stage2_row_naming_the_player(monkeypatch):
    async def body(env):
        reports_test._mount(env, monkeypatch)
        s, g, hid = await hold_test.held(env, "team")
        await hold_test.claim(env, s, 1, hid)
        await hold_test.beat(env, s, 0, seen=[(10, s.steam(0)), (21, s.steam(1))])
        for i in (0, 2, 3, 1):
            r = await reports_test.post_report("team", s, i, g)
            assert r.status_code == 202, ("NX6 journal", i, r.status_code, r.text[:300])
        await env.conn.execute(
            "UPDATE match_report_windows SET settled_at = clock_timestamp(), settled_cls = 'c',"
            "       settled_reporter_id = $2 WHERE room_name = $1", s.room, s.pid(1))
        pid, steam = str(s.pid(1)), s.steam(1)
        before = (await _naming(env, pid), await _naming(env, steam))
        assert set(before[0]) >= {"match_seat_holds", "match_seat_presence",
                                  "match_hold_open_attempts", "match_report_windows",
                                  "match_report_journal"} and \
            set(before[1]) >= {"match_seat_presence", "match_report_journal"}, \
            ("NX6 fixture names the player", before)
        others_before = await env.conn.fetchval(
            "SELECT count(*) FROM match_report_journal WHERE room_name = $1 AND reporter_id <> $2",
            s.room, s.pid(1))

        monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)
        sig = reports_test._sig("delete:%s" % steam)
        async with env.sm() as db:
            await main.delete_player_data(steam, cf_asm.FakeRequest(), sig=sig, _slot=None, db=db)

        after = (await _naming(env, pid), await _naming(env, steam))
        assert after == ({}, {}), ("NX6 no identity", after)
        kept = await env.conn.fetchval(
            "SELECT count(*) FROM match_report_journal WHERE room_name = $1", s.room)
        win = await env.conn.fetchrow(
            "SELECT settled_at, settled_reporter_id FROM match_report_windows WHERE room_name = $1",
            s.room)
        assert (kept, win["settled_at"] is not None, win["settled_reporter_id"]) == \
            (others_before, True, None), ("NX6 others kept", kept, dict(win))
    hold_test.run_env(monkeypatch, body, prefix="rjs2nx6")
