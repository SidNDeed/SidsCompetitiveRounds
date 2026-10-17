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


def test_h1_readmit_economics_use_only_server_absence(monkeypatch):
    """H1: unsigned absence and leave-score claims move no readmit-v1
    economy.  The one server-derived set feeds rating, gold, beaten counts,
    payout size, finishing tiers, persistence and duplicate comparison; a
    server-recorded earlier-game ghost remains excluded and flag-false keeps
    the legacy client-derived decision."""
    async def body(env):
        pool_calls = []
        finish_calls = []
        real_pool = main._ffa_pool_shape
        real_finish = main._ffa_finishing_count

        def pool(place, beaten, n_live):
            pool_calls.append((place, beaten, n_live))
            return real_pool(place, beaten, n_live)

        def finishing(*args, **kwargs):
            out = real_finish(*args, **kwargs)
            finish_calls.append(out)
            return out

        env.mp.setattr(main, "_ffa_pool_shape", pool)
        env.mp.setattr(main, "_ffa_finishing_count", finishing)

        # A present zero-tally seat is falsely marked absent and graced by the
        # reporter.  No server row says it left this game.
        lob = await _lobby(env)
        await _fresh(env, lob, 0)
        results = {lob.sids[0]: (5, 10), lob.sids[1]: (3, 7),
                   lob.sids[2]: (2, 5), lob.sids[3]: (0, 0)}
        rep = await env.report_req(lob, 1, results, reporter=lob.sids[0])
        players = [p.model_copy(update={"left_early": True, "absent": True,
                                         "game_points_at_leave": 0})
                   if p.steam_id == lob.sids[3] else p for p in rep.players]
        rep = rep.model_copy(update={"players": players})
        a = await env.submit(rep)
        row = await env.conn.fetchrow(
            "SELECT mp.absent, mp.rating_change, mp.gold_gained"
            " FROM ffa_match_players mp JOIN ffa_matches m ON m.id = mp.match_id"
            " WHERE m.lobby_id = $1 AND mp.player_id = $2", lob.lid, lob.pids[3])
        assert (a.status == 200 and row is not None and not row["absent"]
                and row["rating_change"] is not None and row["gold_gained"] > 0), \
            ("H1 present economics", a.status, None if row is None else dict(row))
        assert (1, 3, 4) in pool_calls, ("H1 beaten payout", pool_calls)
        assert finish_calls[-1] == (4, 4, 4), ("H1 finishing", finish_calls)

        # The same signed account with different raw client absence fields is
        # an idempotent echo because its persisted server decision is equal.
        echo_players = [p.model_copy(update={"left_early": False, "absent": False,
                                              "game_points_at_leave": None})
                        for p in rep.players]
        echo = await env.submit(rep.model_copy(update={"players": echo_players}))
        assert echo.status == 200, ("H1 duplicate echo", echo.status, echo.body)

        # A server-written prior-game gone row remains an exclusion.
        lob = await _lobby(env)
        await env.set_lobby(lob, games_played=1)
        await env.set_seat(lob, 3, gone_game=1, gone_path="witness")
        await _fresh(env, lob, 0)
        ghost_results = {lob.sids[0]: (5, 10), lob.sids[1]: (3, 7),
                         lob.sids[2]: (2, 5), lob.sids[3]: (0, 0)}
        a = await _file(env, lob, 0, g=2, results=ghost_results)
        ghost = await env.conn.fetchrow(
            "SELECT mp.absent, mp.rating_change, mp.gold_gained"
            " FROM ffa_match_players mp JOIN ffa_matches m ON m.id = mp.match_id"
            " WHERE m.lobby_id = $1 AND mp.player_id = $2", lob.lid, lob.pids[3])
        assert (a.status == 200 and ghost["absent"] and ghost["rating_change"] is None
                and ghost["gold_gained"] == 0), ("H1 server ghost", dict(ghost))

        # Flag-false retains the legacy raw absent/grace behavior byte for byte.
        lob = await _lobby(env, flag=False)
        raw = await env.report_req(lob, 1, {
            lob.sids[0]: (5, 10), lob.sids[1]: (3, 7),
            lob.sids[2]: (2, 5), lob.sids[3]: (0, 0)}, reporter=lob.sids[0])
        raw = raw.model_copy(update={"players": [
            p.model_copy(update={"left_early": True, "absent": True,
                                 "game_points_at_leave": 0})
            if p.steam_id == lob.sids[3] else p for p in raw.players]})
        a = await env.submit(raw)
        legacy = await env.conn.fetchrow(
            "SELECT mp.absent, mp.rating_change, mp.gold_gained"
            " FROM ffa_match_players mp JOIN ffa_matches m ON m.id = mp.match_id"
            " WHERE m.lobby_id = $1 AND mp.player_id = $2", lob.lid, lob.pids[3])
        assert (a.status == 200 and legacy["absent"] and legacy["rating_change"] is None
                and legacy["gold_gained"] == 0), ("H1 flag false", dict(legacy))
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


# -- the janitor bound on the settle arm (the round 1 census ruling) ----------

def _report_lines(env, needle=""):
    return [ln for ln in env.lines if ln.startswith("[FFA-REPORT]") and needle in ln]


async def _journaled_r(env):
    """A lobby whose one report (an r seat's) is journaled and whose window is
    due at lobby age 91."""
    lob = await _lobby(env)
    await _entered_row(env, lob, 2)
    a = await _file(env, lob, 2)
    assert a.status == 202, ("T3.7 precondition", a.status, a.body)
    await env.at(lob, 91.0)
    return lob


async def _bound_then_next(env, lob, tag, sql, *args):
    """The settle arm under a held row: the pass ends within the bound with one
    bound line for game 1, settles nothing and supersedes nothing; the next
    tick, the row free, settles the report."""
    R.bound_fast(env)
    done = await R.tick_holding(env, sql, *args)
    assert done, (tag + " bounded",)
    assert await _matches(env, lob) == [], (tag + " nothing settled",)
    assert await _journal(env, lob) == {lob.sids[2]: ("r", "held")}, \
        (tag + " kept", await _journal(env, lob))
    line = _report_lines(env, "journal window lobby %s game 1 bound stage="
                         % main._asm_id8(lob.lid))
    assert len(line) == 1, (tag + " bound line", _report_lines(env))
    await A._janitor_tick(env)
    m = await _matches(env, lob)
    assert [(r["rep_sid"], r["fallback_cls"]) for r in m] == [(lob.sids[2], "r")], \
        (tag + " next tick", [(r["rep_sid"], r["fallback_cls"]) for r in m])


def test_t3_7_a_held_window_bounds_settle_phase_one(monkeypatch):
    """T3.7: phase 1 of a due window (the lobby, then the window FOR UPDATE)
    waits no longer than the janitor bound on a window row another
    transaction holds: one bound line, nothing settled or superseded, and the
    next tick settles it."""
    async def body(env):
        lob = await _journaled_r(env)
        await _bound_then_next(env, lob, "T3.7",
                               "SELECT 1 FROM ffa_report_windows WHERE lobby_id = $1 FOR UPDATE",
                               lob.lid)
    run_env(monkeypatch, body)


def test_t3_8_a_bound_refusal_is_not_a_supersede(monkeypatch):
    """T3.8: phase 2 under the bound, through the body's insert branch: an
    uncommitted ffa_matches row of the same room (another transaction) makes
    the settlement's insert wait, the bound ends it as 55P03, the body answers
    its 503 retry refusal from inside the database error's except (and re-locks
    the lobby after its rollback, still bounded); the window reads that as a
    bound, not as a refusal, so the journaled report is not superseded."""
    async def body(env):
        lob = await _journaled_r(env)
        room = (await env.lobby_row(lob.lid))["photon_room_id"] + "_r1"
        await _bound_then_next(env, lob, "T3.8",
                               "INSERT INTO ffa_matches (id, photon_room_id, player_count,"
                               " game_number) VALUES (gen_random_uuid(), $1, 4, 1)", room)
    run_env(monkeypatch, body)


def test_t3_9_a_held_reporter_row_bounds_settle_phase_two(monkeypatch):
    """T3.9: phase 2 under the bound, raw: a reported player's players row
    another transaction holds FOR UPDATE makes the body's sorted players pass
    wait; the bound ends it and the window prints a bound line, not a failure;
    nothing settled or superseded; the next tick settles it."""
    async def body(env):
        lob = await _journaled_r(env)
        await _bound_then_next(env, lob, "T3.9",
                               "SELECT 1 FROM players WHERE id = $1 FOR UPDATE", lob.pids[0])
    run_env(monkeypatch, body)
