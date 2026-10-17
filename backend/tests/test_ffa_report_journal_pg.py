"""FFA readmission lobbies, the reporter (design V3 P3, server half): the
class of a report read from server rows only, the server-elected continuous
seat that settles at once, the journal and its 30 s window, the settlement
order c, r, l, g (g1 for a lone lagged report), idempotence, the returner
rated, and the flag-false negative control. Against a local PostgreSQL
through cf_pg; every assertion names its control in the first element of
its message for the readmit mutation runner (rdm_controls.py).
"""

import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import main  # noqa: E402
import test_ffa_assembly_pg as A  # noqa: E402
import test_ffa_readmit_pg as R  # noqa: E402


def run_env(monkeypatch, body):
    A.run_env(monkeypatch, body, prefix="rdj")


def _results(lob):
    return {lob.sids[0]: (5, 10), lob.sids[1]: (3, 7), lob.sids[2]: (2, 5),
            lob.sids[3]: (1, 2)}


async def _file(env, lob, slot, g=1, *, self_lag=0, results=None):
    rep = await env.report_req(lob, g, results or _results(lob), reporter=lob.sids[slot])
    if self_lag:
        rep = rep.model_copy(update={"self_lag": 1})
    return await env.submit(rep)


async def _fresh(env, lob, slot):
    """The seat's census received now (it is present at this receipt)."""
    await env.census_row(lob, slot, [(s, 1 + s, 1, 1) for s in range(lob.n)])


async def _entered_row(env, lob, slot, g=1):
    await env.conn.execute(
        "INSERT INTO ffa_seat_readmissions (lobby_id, player_id, n, anchor_at, held_at,"
        "  hold_until, claimed_at, bound_at, actor_nr, game, entered_at)"
        " VALUES ($1, $2, 1, now(), now(), now(), now(), now(), 9, $3, now())",
        lob.lid, lob.pids[slot], g)


async def _matches(env, lob, g=1):
    return [dict(r) for r in await env.conn.fetch(
        "SELECT m.*, p.steam_id AS rep_sid FROM ffa_matches m JOIN players p"
        "  ON p.id = m.reported_by WHERE m.lobby_id = $1 AND m.game_number = $2",
        lob.lid, g)]


async def _journal(env, lob, g=1):
    return {r["steam_id"]: (r["cls"], r["state"]) for r in await env.conn.fetch(
        "SELECT p.steam_id, j.cls, j.state FROM ffa_report_journal j JOIN players p"
        "  ON p.id = j.reporter_id WHERE j.lobby_id = $1 AND j.game = $2", lob.lid, g)}


async def _expire(env, lob, t):
    await env.at(lob, t)
    await A._janitor_tick(env)


async def _lobby(env, t_report=60.0, flag=True):
    lob = await R._rdm_lobby(env, 4, flag=flag)
    await env.at(lob, t_report)
    return lob


def test_t3_1_the_class_matrix(monkeypatch):
    """T3.1: the elected continuous seat settles at once; otherwise the window
    settles the first non-empty class in the order c, r, l, g, lowest Steam id
    within a class; a lone lagged report settles recorded and unrated (g1),
    two agreeing lagged reports settle rated (g); a leaver stays refused;
    exactly one settlement per game."""
    async def body(env):
        # (a) the elected seat (fresh census, lowest Steam id among them).
        lob = await _lobby(env)
        await _fresh(env, lob, 1)
        a = await _file(env, lob, 1)
        assert a.status == 200, ("T3.1 elected", a.status, a.body)
        m = await _matches(env, lob)
        assert len(m) == 1 and m[0]["fallback_cls"] is None, ("T3.1 elected row", m)
        w = await env.conn.fetchrow("SELECT * FROM ffa_report_windows WHERE lobby_id = $1",
                                    lob.lid)
        assert w is not None and w["settled_cls"] == "c", ("T3.1 elected window", w)

        # (b) r, l and g file, no continuous report: the window settles r.
        lob = await _lobby(env)
        await _entered_row(env, lob, 2)
        await env.set_seat(lob, 1, late_admitted_at=20.0)
        await env.set_seat(lob, 3, lag_games=[1])
        for s in (3, 1, 2):
            a = await _file(env, lob, s)
            assert a.status == 202 and a["status"] == "journaled", ("T3.1 journaled", s, a.body)
        assert await _matches(env, lob) == [], ("T3.1 nothing settled early",)
        await _expire(env, lob, 91.0)
        m = await _matches(env, lob)
        assert [(r["rep_sid"], r["fallback_cls"]) for r in m] == [(lob.sids[2], "r")], \
            ("T3.1 r first", [(r["rep_sid"], r["fallback_cls"]) for r in m])
        j = await _journal(env, lob)
        assert j[lob.sids[2]][1] == "settled" and j[lob.sids[1]][1] == "superseded", \
            ("T3.1 journal states", j)

        # (c) l and g only: l.
        lob = await _lobby(env)
        await env.set_seat(lob, 1, late_admitted_at=20.0)
        await env.set_seat(lob, 3, lag_games=[1])
        await _file(env, lob, 3)
        await _file(env, lob, 1)
        await _expire(env, lob, 91.0)
        m = await _matches(env, lob)
        assert [(r["rep_sid"], r["fallback_cls"]) for r in m] == [(lob.sids[1], "l")], \
            ("T3.1 l over g", [(r["rep_sid"], r["fallback_cls"]) for r in m])

        # (d) a lone lagged report: recorded, rating and gold skipped.
        lob = await _lobby(env)
        await env.set_seat(lob, 3, lag_games=[1])
        a = await _file(env, lob, 3)
        assert a.status == 202, ("T3.1 g journaled", a.body)
        await _expire(env, lob, 91.0)
        m = await _matches(env, lob)
        assert len(m) == 1 and m[0]["fallback_cls"] == "g1" and m[0]["is_ranked"] is False, \
            ("T3.1 g1", m and (m[0]["fallback_cls"], m[0]["is_ranked"]))
        gold = await env.conn.fetchval(
            "SELECT COALESCE(SUM(gold_gained), 0) FROM ffa_match_players WHERE match_id = $1",
            m[0]["id"])
        assert gold == 0, ("T3.1 g1 gold", gold)

        # (e) two agreeing lagged reports (one lag row, one self_lag): rated g.
        lob = await _lobby(env)
        await env.set_seat(lob, 3, lag_games=[1])
        await _file(env, lob, 3)
        await _file(env, lob, 2, self_lag=1)
        await _expire(env, lob, 91.0)
        m = await _matches(env, lob)
        assert len(m) == 1 and m[0]["fallback_cls"] == "g" and m[0]["is_ranked"] is True, \
            ("T3.1 g agreed", m and (m[0]["fallback_cls"], m[0]["is_ranked"]))

        # (f) a non-elected continuous report and an r: the window settles c.
        lob = await _lobby(env)
        await _entered_row(env, lob, 1)
        await _file(env, lob, 1)
        await _file(env, lob, 2)
        await _expire(env, lob, 91.0)
        m = await _matches(env, lob)
        assert [(r["rep_sid"], r["fallback_cls"]) for r in m] == [(lob.sids[2], None)], \
            ("T3.1 c over r", [(r["rep_sid"], r["fallback_cls"]) for r in m])

        # (x) a leaver is refused as today and journals nothing.
        lob = await _lobby(env)
        await env.set_lobby(lob, games_played=1)
        await env.set_seat(lob, 3, gone_game=1, gone_path="witness")
        a = await _file(env, lob, 3, g=2)
        assert a.status not in (200, 202), ("T3.1 x refused", a.status, a.body)
        assert await _journal(env, lob, 2) == {}, ("T3.1 x journal",)
    run_env(monkeypatch, body)


def test_t3_3_edge_races(monkeypatch):
    """T3.3: a returner's report never settles at once; with the continuous
    seat's census stale at the receipt its report is journaled too and the
    window settles it; with no continuous report the window settles the
    returner."""
    async def body(env):
        lob = await _lobby(env)
        await _entered_row(env, lob, 2)
        a = await _file(env, lob, 2)
        assert a.status == 202, ("T3.3 r waits", a.status, a.body)
        a = await _file(env, lob, 0)
        assert a.status == 202, ("T3.3 stale c journaled", a.status, a.body)
        await _expire(env, lob, 91.0)
        m = await _matches(env, lob)
        assert [r["rep_sid"] for r in m] == [lob.sids[0]], ("T3.3 c settles",
                                                           [r["rep_sid"] for r in m])

        lob = await _lobby(env)
        await _entered_row(env, lob, 2)
        await _fresh(env, lob, 0)
        a = await _file(env, lob, 2)
        assert a.status == 202, ("T3.3 r waits", a.status, a.body)
        await _expire(env, lob, 91.0)
        m = await _matches(env, lob)
        assert [(r["rep_sid"], r["fallback_cls"]) for r in m] == [(lob.sids[2], "r")], \
            ("T3.3 r settles", [(r["rep_sid"], r["fallback_cls"]) for r in m])
    run_env(monkeypatch, body)


def test_t3_4_one_settlement_under_a_race(monkeypatch):
    """T3.4: two settlements of one expired window interleaved (the second
    reads the choice before the first commits) and a report call after it:
    one match row, one settled line."""
    async def body(env):
        lob = await _lobby(env)
        await env.set_seat(lob, 1, late_admitted_at=20.0)
        await _file(env, lob, 1)
        await env.at(lob, 91.0)
        ev1, ev2 = asyncio.Event(), asyncio.Event()
        calls = {"n": 0}
        real = main._ffa_settle_report

        async def gate(rep, db, *, journal):
            calls["n"] += 1
            if calls["n"] == 1:
                await ev1.wait()
                try:
                    return await real(rep, db, journal=journal)
                finally:
                    ev2.set()
            ev1.set()
            await ev2.wait()
            return await real(rep, db, journal=journal)
        env.mp.setattr(main, "_ffa_settle_report", gate)

        async def one():
            async def go():
                async with env.sm() as db:
                    return await main._ffa_settle_window(db, lob.lid, 1)
            return await env._call(go)
        got = await asyncio.gather(one(), one())
        env.mp.setattr(main, "_ffa_settle_report", real)
        settled = [ln for ln in env.lines if "settled cls=" in ln]
        assert len(settled) == 1, ("T3.4 one settlement", settled, [g.body for g in got])
        a = await _file(env, lob, 1)
        assert len(await _matches(env, lob)) == 1, ("T3.4 one row", a.status)
    run_env(monkeypatch, body)


def test_t3_5_the_returner_is_rated_and_reports_later_games(monkeypatch):
    """T3.5: a readmitted seat is rated in the game it returned to (its gone
    record moved off the seat), and its report of the next game, as the
    elected seat, settles rather than being refused left_reporter."""
    async def body(env):
        lob = await R._held(env)
        await env.at(lob, 80.0)
        await R._claim_bind(env, lob, 1, 1, 9)
        await env.at(lob, 85.0)
        await _fresh(env, lob, 0)
        a = await _file(env, lob, 0)
        assert a.status == 200, ("T3.5 game 1", a.status, a.body)
        rc = await env.conn.fetchval(
            "SELECT mp.rating_change FROM ffa_match_players mp JOIN ffa_matches m"
            "  ON m.id = mp.match_id WHERE m.lobby_id = $1 AND mp.player_id = $2",
            lob.lid, lob.pids[1])
        assert rc is not None, ("T3.5 rated", rc)
        await env.at(lob, 120.0)
        await env.census_row(lob, 1, [(0, 1, 1, 1), (1, 9, 1, 1), (2, 3, 1, 1), (3, 4, 1, 1)])
        a = await _file(env, lob, 1, g=2)
        assert a.status == 200, ("T3.5 game 2", a.status, a.body)
    run_env(monkeypatch, body)


def test_t3_6_flag_false_keeps_today(monkeypatch):
    """T3.6 (#391 negative control): in a lobby locked without the flag a late
    reporter is refused late_reporter, a lagged reporter lag_reporter, a
    continuous report settles at once whatever its census age, and no
    journal or window row is written."""
    async def body(env):
        lob = await _lobby(env, flag=False)
        await env.set_seat(lob, 1, late_admitted_at=20.0)
        await env.set_seat(lob, 3, lag_games=[1])
        a = await _file(env, lob, 1)
        assert a.status not in (200, 202), ("T3.6 late", a.status, a.body)
        a = await _file(env, lob, 3)
        assert a.status not in (200, 202), ("T3.6 lag", a.status, a.body)
        a = await _file(env, lob, 2)
        assert a.status == 200, ("T3.6 settles at once", a.status, a.body)
        n = await env.conn.fetchval(
            "SELECT (SELECT count(*) FROM ffa_report_journal WHERE lobby_id = $1)"
            "     + (SELECT count(*) FROM ffa_report_windows WHERE lobby_id = $1)", lob.lid)
        assert n == 0, ("T3.6 no journal", n)
        m = await _matches(env, lob)
        assert len(m) == 1 and m[0]["fallback_cls"] is None, ("T3.6 row", m)
    run_env(monkeypatch, body)


def test_s3k_departure_credited_kill_places_as_a_death(monkeypatch):
    """S3k (control): the report carries kills, never how a kill was credited
    (no field of a reported player names a credit or a departure), so a
    departure-credited kill places exactly as the same kill from a death: the
    settled placements follow the reported tallies alone."""
    async def body(env):
        lob = await _lobby(env)
        await _fresh(env, lob, 0)
        rep = await env.report_req(lob, 1, {lob.sids[0]: (5, 10), lob.sids[1]: (3, 6),
                                            lob.sids[2]: (2, 4), lob.sids[3]: (0, 0)},
                                   reporter=lob.sids[0])
        fields = set(type(rep.players[0]).model_fields)
        assert not any(w in f for f in fields for w in ("credit", "depart", "cause")), \
            ("S3k fields", sorted(fields))
        a = await env.submit(rep)
        assert a.status == 200, ("S3k settle", a.status, a.body)
        rows = await env.conn.fetch(
            "SELECT p.steam_id, mp.placement FROM ffa_match_players mp"
            "  JOIN ffa_matches m ON m.id = mp.match_id JOIN players p ON p.id = mp.player_id"
            " WHERE m.lobby_id = $1", lob.lid)
        got = {r["steam_id"]: r["placement"] for r in rows}
        assert [got[s] for s in lob.sids] == [1, 2, 3, 4], ("S3k placements", got)
    run_env(monkeypatch, body)
