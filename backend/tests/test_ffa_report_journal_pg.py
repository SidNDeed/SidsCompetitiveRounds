"""FFA readmission lobbies, the reporter (design V3 P3, server half): the
class of a report read from server rows only, the server-elected continuous
seat that settles at once, the journal and its 30 s window, the settlement
order c, r, l, g (g1 for a lone lagged report), idempotence, the returner
rated, and the flag-false negative control. Against a local PostgreSQL
through cf_pg; every assertion names its control in the first element of
its message for the readmit mutation runner (rdm_controls.py).
"""

import asyncio
import datetime as _dt
import importlib.util
import itertools
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import main  # noqa: E402
import test_ffa_assembly_pg as A  # noqa: E402
import test_ffa_readmit_pg as R  # noqa: E402


LANE_BASE_COMMIT = "9267b1fe86b636dd9a25306d9f0a64d02ca6a7cd"
_LANE_BASE = {}


def _lane_base_main():
    """The lane-base main.py, imported lazily without writing a temp tree."""
    if "mod" in _LANE_BASE:
        return _LANE_BASE["mod"]
    repo = os.path.normpath(os.path.join(HERE, "..", ".."))
    src = subprocess.run(
        ["git", "-C", repo, "show", LANE_BASE_COMMIT + ":backend/api/main.py"],
        capture_output=True, check=True).stdout
    name = "main_rdm_lane_base"
    spec = importlib.util.spec_from_loader(name, loader=None,
                                           origin="lane-base/backend/api/main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        exec(compile(src, spec.origin, "exec"), mod.__dict__)
    except Exception:
        sys.modules.pop(name, None)
        raise
    _LANE_BASE["mod"] = mod
    return mod


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


async def _lobby(env, t_report=60.0, flag=True, n=4):
    lob = await R._rdm_lobby(env, n, flag=flag)
    await env.at(lob, t_report)
    return lob


def _assert_t3_1_pure_matrix(n):
    """Assert every C/R/L/G/X assignment for one seat count."""
    receipt = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
    sids = [str(100 + i) for i in range(n)]
    priorities = ("c", "r", "l", "g")
    all_x_seen = False
    for assignment in itertools.product(("c", "r", "l", "g", "x"), repeat=n):
        classes = {sid: {"cls": cls, "census_at": receipt}
                   for sid, cls in zip(sids, assignment)}
        elected = min((sid for sid, cls in zip(sids, assignment) if cls == "c"),
                      default=None, key=main._ffa_sort_key)
        assert main._rdm_elected(classes, receipt) == elected, \
            ("T3.1 elected matrix", n, assignment, elected)
        for elected_files in (False, True):
            if elected_files and elected is not None:
                got = (elected, "c")
            else:
                journal = [{"steam_id": sid, "cls": cls, "tally": ("same",)}
                           for sid, cls in zip(sids, assignment)
                           if cls != "x" and sid != elected]
                got = main._rdm_choose(journal, classes)
            if elected_files and elected is not None:
                expected = (elected, "c")
            else:
                eligible = [(sid, cls) for sid, cls in zip(sids, assignment)
                            if cls != "x" and sid != elected]
                chosen_cls = next((cls for cls in priorities
                                   if any(c == cls for _sid, c in eligible)), None)
                if chosen_cls is None:
                    expected = (None, None)
                else:
                    chosen = min((sid for sid, cls in eligible if cls == chosen_cls),
                                 key=main._ffa_sort_key)
                    if chosen_cls == "g":
                        count = sum(cls == "g" for _sid, cls in eligible)
                        expected = (chosen, "g" if count >= 2 else "g1")
                    else:
                        expected = (chosen, chosen_cls)
            assert got == expected, \
                ("T3.1 pure matrix", n, assignment, elected_files, got, expected)
        if all(cls == "x" for cls in assignment):
            all_x_seen = True
            assert main._rdm_choose([], classes) == (None, None), ("T3.1 all X", n)
    assert all_x_seen, ("T3.1 all X covered", n)

    disagree = [{"steam_id": sid, "cls": "g", "tally": (sid,)} for sid in sids]
    assert main._rdm_choose(disagree, {}) == (sids[0], "g1"), \
        ("T3.1 disagreeing G", n, main._rdm_choose(disagree, {}))


@pytest.mark.parametrize("n", range(2, 9))
def test_t3_1_pure_class_election_matrix(n):
    """T3.1 pure matrix: for every 2-to-8-seat C/R/L/G/X assignment,
    exercise both whether the elected C files and whether it does not.  X is
    never a journal filer; delayed choice is C > R > L > G and then the
    UUID-order-equivalent Steam-id order, with g1 unless G has a quorum."""
    _assert_t3_1_pure_matrix(n)


def test_t3_1_the_class_matrix(monkeypatch):
    """T3.1: the elected continuous seat settles at once; otherwise the window
    settles the first non-empty class in the order c, r, l, g, lowest Steam id
    within a class; a lone lagged report settles recorded and unrated (g1),
    two agreeing lagged reports settle rated (g); a leaver stays refused;
    exactly one settlement per game."""
    # M3.1-M3.4 execute the exhaustive chooser matrix before their
    # route/economy-specific controls and named mutant assertions.
    for n in range(2, 9):
        _assert_t3_1_pure_matrix(n)

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


def test_t3_2_server_lag_without_client_publication_cannot_win_election(monkeypatch):
    """T3.2: in a two-seat flagged lobby the lowest Steam id is server-class
    G even though its report publishes no self-lag bit.  Its receipt waits;
    the other, genuinely continuous seat remains the elected C and settles."""
    async def body(env):
        lob = await _lobby(env, n=2)
        results = {lob.sids[0]: (5, 10), lob.sids[1]: (3, 7)}
        lag = await env.connect(lob, 0, "lag", game=1, k=1, why="timeout")
        assert lag.status == 200, ("T3.2 server lag route", lag.status, lag.body)
        await _fresh(env, lob, 0)
        await _fresh(env, lob, 1)
        lagged = await _file(env, lob, 0, results=results)
        assert lagged.status == 202 and await _journal(env, lob) == {
            lob.sids[0]: ("g", "held")}, \
            ("T3.2 server lag journals", lagged.status, await _journal(env, lob))
        continuous = await _file(env, lob, 1, results=results)
        matches = await _matches(env, lob)
        assert continuous.status == 200 and [m["rep_sid"] for m in matches] == [lob.sids[1]], \
            ("T3.2 class C settles", continuous.status, matches)
    run_env(monkeypatch, body)


def test_t3_3_edge_races(monkeypatch):
    """T3.3: real pre-edge and post-edge drops do not change receipt class.
    A returner's report waits and wins when C dropped first; a stored C wins
    after its later drop, alone and over R; an immediately settled C stays
    the one settlement after its own subsequent drop."""
    async def body(env):
        async def return_for_game(lob, slot, actor):
            await env.at(lob, 80.0)
            claim = await R._readmit(env, lob, slot, "claim", 1)
            assert claim["status"] == "claimed", ("T3.3 real claim", claim.body)
            await R._corroborate(env, lob, slot, actor, witness=1)
            bind = await R._readmit(env, lob, slot, "bind", 1, actor=actor)
            assert bind["status"] == "admitted_late", ("T3.3 real bind", bind.body)
            await R._corroborate(env, lob, slot, actor, witness=1, kept=True)
            entered = await R._readmit(env, lob, slot, "entered", 1, actor=actor, game=1)
            assert entered["status"] == "entered", ("T3.3 real entered", entered.body)

        async def held_returner():
            lob = await R._rdm_lobby(env)
            await R._present(env, lob, 2, 50.0)
            await R._witness_gone(env, lob, 2, 70.0, witnesses=(0, 1))
            seat = await env.seat(lob, 2)
            assert seat["hold_n"] == 1, ("T3.3 real hold", seat["hold_n"])
            return lob

        # Pre-edge: C actually drops before any report; the actual returner R
        # is the only filer and wins only after the window.
        lob = await held_returner()
        await return_for_game(lob, 2, 9)
        gone = await R._witness_gone(env, lob, 0, 82.0, witnesses=(3, 1))
        dropped = await env.seat(lob, 0)
        assert gone.status == 200 and dropped["gone_game"] == 1, \
            ("T3.3 real pre-edge drop", gone.status, gone.body, dropped["gone_game"])
        report = await _file(env, lob, 2)
        assert report.status == 202, ("T3.3 r waits", report.status, report.body)
        await _expire(env, lob, 113.0)
        m = await _matches(env, lob)
        assert [(r["rep_sid"], r["fallback_cls"]) for r in m] == [(lob.sids[2], "r")], \
            ("T3.3 real pre-edge R", m)

        # Post-edge: C and an actual R are journaled before C really drops;
        # the stored C receipt remains authoritative at expiry.
        lob = await held_returner()
        await return_for_game(lob, 2, 9)
        await env.at(lob, 81.0)
        c = await _file(env, lob, 0)
        r = await _file(env, lob, 2)
        assert c.status == r.status == 202, ("T3.3 real post-edge receipts", c.body, r.body)
        gone = await R._witness_gone(env, lob, 0, 82.0, witnesses=(3, 1))
        dropped = await env.seat(lob, 0)
        assert gone.status == 200 and dropped["gone_game"] == 1, \
            ("T3.3 real post-edge drop", gone.status, gone.body, dropped["gone_game"])
        await _expire(env, lob, 112.0)
        m = await _matches(env, lob)
        assert [(row["rep_sid"], row["fallback_cls"]) for row in m] == [
            (lob.sids[0], None)], ("T3.3 real post-edge C", m)

        # An elected C may settle immediately; its subsequent real drop never
        # creates a second settlement for the already-finished game.
        lob = await _lobby(env)
        await _fresh(env, lob, 0)
        c = await _file(env, lob, 0)
        assert c.status == 200, ("T3.3 immediate C", c.status, c.body)
        gone = await R._witness_gone(env, lob, 0, 71.0, witnesses=(1, 2))
        dropped = await env.seat(lob, 0)
        assert gone.status == 200 and dropped["gone_game"] == 2, \
            ("T3.3 immediate real drop", gone.status, gone.body, dropped["gone_game"])
        assert len(await _matches(env, lob)) == 1, ("T3.3 immediate stays one",)
    run_env(monkeypatch, body)


def test_h2_bound_but_unentered_returner_is_u(monkeypatch):
    """H2: a game-g readmission that has bound but not entered is U even
    after it publishes a fresh census.  It cannot settle ahead of C; after the
    real entered receipt the returned seat participates in the settled game."""
    async def body(env):
        lob = await R._held(env, gone=0)
        await env.at(lob, 80.0)
        claim = await R._readmit(env, lob, 0, "claim", 1)
        assert claim["status"] == "claimed", ("H2 claim", claim.body)
        await R._corroborate(env, lob, 0, 9, witness=1)
        bind = await R._readmit(env, lob, 0, "bind", 1, actor=9)
        assert bind["status"] == "admitted_late", ("H2 bind", bind.body)
        await env.census_row(lob, 0, [(0, 9, 1, 0), (1, 2, 1, 1),
                                      (2, 3, 1, 1), (3, 4, 1, 1)])
        a = await _file(env, lob, 0)
        assert a.status == 202 and await _journal(env, lob) == {
            lob.sids[0]: ("u", "held")}, ("H2 bound unentered", a.status,
                                           await _journal(env, lob))

        await R._corroborate(env, lob, 0, 9, witness=1, kept=True)
        entered = await R._readmit(env, lob, 0, "entered", 1, actor=9, game=1)
        assert entered["status"] == "entered", ("H2 entered", entered.body)
        await _fresh(env, lob, 1)
        settled = await _file(env, lob, 1)
        assert settled.status == 200, ("H2 c settles", settled.status, settled.body)
        row = await env.conn.fetchrow(
            "SELECT mp.rating_change, mp.gold_gained FROM ffa_match_players mp"
            " JOIN ffa_matches m ON m.id = mp.match_id"
            " WHERE m.lobby_id = $1 AND mp.player_id = $2", lob.lid, lob.pids[0])
        assert row["rating_change"] is not None and row["gold_gained"] > 0, \
            ("H2 entered economy", dict(row))
    run_env(monkeypatch, body)


def test_h3_delayed_choice_uses_the_stored_receipt_class(monkeypatch):
    """H3: a C receipt remains C if its reporter actually drops before the
    window expires.  The stored C wins both alone and against an R receipt;
    later mutable gone state cannot erase or demote it."""
    async def body(env):
        lob = await _lobby(env)
        a = await _file(env, lob, 0)
        assert a.status == 202, ("H3 c journaled", a.status, a.body)
        await R._witness_gone(env, lob, 0, 61.0, witnesses=(1, 2))
        await _expire(env, lob, 91.0)
        m = await _matches(env, lob)
        assert [(r["rep_sid"], r["fallback_cls"]) for r in m] == [
            (lob.sids[0], None)], ("H3 stored class", m)

        lob = await _lobby(env)
        await _entered_row(env, lob, 2)
        r = await _file(env, lob, 2)
        c = await _file(env, lob, 0)
        assert r.status == c.status == 202, ("H3 receipts", r.body, c.body)
        await R._witness_gone(env, lob, 0, 61.0, witnesses=(1, 2))
        await _expire(env, lob, 91.0)
        m = await _matches(env, lob)
        assert [(row["rep_sid"], row["fallback_cls"]) for row in m] == [
            (lob.sids[0], None)], ("H3 c over r", m)
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
    journal or window row is written.  The route-level wire bodies, including
    a successful replay, are compared as bytes rather than re-serialized."""
    import database
    import httpx
    lane_base = _lane_base_main()
    wire = {}

    async def exercise(env, app_main, label):
        async def override():
            async with env.sm() as db:
                yield db

        async def rows(lob):
            return await env.conn.fetchval(
                "SELECT (SELECT count(*) FROM ffa_report_journal WHERE lobby_id = $1)"
                "     + (SELECT count(*) FROM ffa_report_windows WHERE lobby_id = $1)", lob.lid)

        async def no_session(request, steam_id, db):
            return None

        env.mp.setattr(app_main, "_check_steam_session", no_session)
        env.mp.setattr(app_main, "MATCH_HMAC_SECRET", "")
        env.mp.setattr(app_main, "_presence_seen", {})
        env.mp.setattr(app_main, "time", main.time)
        env.mp.setattr(app_main, "_asm_clock", env._clock, raising=False)
        real_uuid4 = app_main.uuid.uuid4
        env.mp.setattr(app_main.uuid, "uuid4",
                       lambda: main.UUID("abcdabcd-abcd-4abc-8abc-abcdabcdabcd"))
        app_main.app.dependency_overrides[database.get_db] = override
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_main.app),
                                         base_url="http://rdj") as client:
                async def post(rep):
                    response = await client.post("/api/v1/ffa/matches",
                                                 json=rep.model_dump(mode="json"),
                                                 headers={"X-Mod-Version": "1.41.0"})
                    return response.status_code, bytes(response.content)

                late = await _lobby(env, flag=False)
                await env.set_seat(late, 1, late_admitted_at=20.0)
                rep = await env.report_req(late, 1, _results(late), reporter=late.sids[1])
                answer = await post(rep)
                again = await post(rep)
                want = (b'{"detail":"This seat may not report this sitting\'s games",'
                        b'"games_played":0,"expected_game":1}')
                assert answer == again == (409, want), \
                    ("T3.6 late bytes", label, answer, again)
                late_wire = (answer, again)
                assert await rows(late) == 0, ("T3.6 late no journal", await rows(late))

                lagged = await _lobby(env, flag=False)
                lag_write = await env.connect(lagged, 1, "lag", game=1, k=1,
                                              why="timeout")
                assert lag_write.status == 200, \
                    ("T3.6 lag route", label, lag_write.status, lag_write.body)
                rep = await env.report_req(lagged, 1, _results(lagged), reporter=lagged.sids[1])
                answer = await post(rep)
                again = await post(rep)
                want = (b'{"detail":"This seat may not report this game",'
                        b'"games_played":0,"expected_game":1}')
                assert answer == again == (409, want), \
                    ("T3.6 lag bytes", label, answer, again)
                lag_wire = (answer, again)
                assert await rows(lagged) == 0, ("T3.6 lag no journal", await rows(lagged))

                continuous = await _lobby(env, flag=False)
                rep = await env.report_req(continuous, 1, _results(continuous),
                                           reporter=continuous.sids[2])
                first = await post(rep)
                replay = await post(rep)
                replay_again = await post(rep)
                assert first[0] == replay[0] == replay_again[0] == 200 \
                    and replay == replay_again, \
                    ("T3.6 replay bytes", label, first, replay, replay_again)
                assert await rows(continuous) == 0, \
                    ("T3.6 success no journal", await rows(continuous))
                matches = await _matches(env, continuous)
                assert len(matches) == 1 and matches[0]["fallback_cls"] is None, \
                    ("T3.6 row", matches)
                wire[label] = (late_wire, lag_wire, first, replay, replay_again)
        finally:
            app_main.uuid.uuid4 = real_uuid4
            app_main.app.dependency_overrides.pop(database.get_db, None)

    run_env(monkeypatch, lambda env: exercise(env, main, "current"))
    run_env(monkeypatch, lambda env: exercise(env, lane_base, "lane_base"))
    assert wire["current"] == wire["lane_base"], \
        ("T3.6 flag-false wire compatibility", wire["current"], wire["lane_base"])


def test_h1_readmit_economics_use_only_server_absence(monkeypatch):
    """H1: the unsigned absent claim moves no readmit-v1 economy, and the
    leave-score claim moves it only through the early-leave grace, the same
    way whatever the absent flag says.  The re-land's Codex round (F1) found
    the claim read and then discarded: a claimed early leaver was skipped by
    the grace, rated and paid, where the unclaimed one was graced.  One
    server-derived set feeds rating, gold, XP, beaten counts, payout size,
    finishing tiers, persistence and duplicate comparison; a server-recorded
    earlier-game ghost remains excluded and flag-false keeps the legacy
    client-derived decision."""
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

        # The pair: a zero-tally seat that left at zero field points, with the
        # reporter's absent flag false and then true.  Both are graced: the
        # leaver is unrated with no game XP or gold, and every other seat's
        # rating, XP, gold and placement, the beaten payouts and the finishing
        # count are the same in both.
        arms = {}
        leavers = {}
        last = None
        for absent in (False, True):
            del pool_calls[:]
            del finish_calls[:]
            # Reported ten minutes in: the pace ceiling (twice the fitted
            # pace over the elapsed window) clears the 22 claimed battles at
            # either live count, so the pool is the claim and not the clock
            # and the two arms' XP and gold compare exactly.
            lob = await _lobby(env, t_report=600.0)
            await _fresh(env, lob, 0)
            results = {lob.sids[0]: (5, 10), lob.sids[1]: (3, 7),
                       lob.sids[2]: (2, 5), lob.sids[3]: (0, 0)}
            rep = await env.report_req(lob, 1, results, reporter=lob.sids[0])
            players = [p.model_copy(update={"left_early": True, "absent": absent,
                                             "game_points_at_leave": 0})
                       if p.steam_id == lob.sids[3] else p for p in rep.players]
            rep = rep.model_copy(update={"players": players})
            a = await env.submit(rep)
            assert a.status == 200, ("H1 graced either way", absent, a.status, a.body)
            rows = {r["player_id"]: dict(r) for r in await env.conn.fetch(
                "SELECT mp.player_id, mp.absent, mp.rating_change, mp.xp_gained,"
                "       mp.gold_gained, mp.placement, mp.exclusion_reasons"
                " FROM ffa_match_players mp JOIN ffa_matches m ON m.id = mp.match_id"
                " WHERE m.lobby_id = $1", lob.lid)}
            vec = [rows[pid] for pid in lob.pids]
            leavers[absent] = vec[3]
            arms[absent] = ([(v["absent"], v["rating_change"], v["xp_gained"],
                              v["gold_gained"], v["placement"],
                              sorted(v["exclusion_reasons"] or [])) for v in vec],
                            # the payout helper walks the roster in the
                            # lobby's own id order: a set of calls, not a list
                            sorted(pool_calls), list(finish_calls))
            last = (lob, rep)
        # The flag moved nothing: the whole vector first, then the ruling.
        assert arms[False] == arms[True], ("H1 graced either way", arms[False], arms[True])
        for absent, leaver in leavers.items():
            assert (leaver["absent"] and leaver["rating_change"] is None
                    and (leaver["xp_gained"] or 0) == 0 and (leaver["gold_gained"] or 0) == 0
                    and sorted(leaver["exclusion_reasons"] or []) == ["grace"]), \
                ("H1 grace unrated", absent, leaver)
        assert (1, 2, 3) in pool_calls, ("H1 beaten payout", pool_calls)
        assert finish_calls[-1] == (3, 3, 3), ("H1 finishing", finish_calls)

        # The same signed account with different raw client absence fields is
        # an idempotent echo because its persisted server decision is equal.
        lob, rep = last
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


def test_h4_retryable_failures_keep_the_chosen_receipt(monkeypatch):
    """H4: generic and quarantine-lock 503s keep the chosen row held for the
    next tick; a captured terminal 409 supersedes it."""
    async def body(env):
        # A non-bound 503 is retryable even though it carries no SQLSTATE.
        lob = await _journaled_r(env)
        real = main._ffa_settle_report
        calls = {"n": 0}

        async def once(rep, db, *, journal):
            calls["n"] += 1
            if calls["n"] == 1:
                raise main.FfaReportRefusal(503, "retry", main._ffa_progress(0))
            return await real(rep, db, journal=journal)

        env.mp.setattr(main, "_ffa_settle_report", once)
        await A._janitor_tick(env)
        assert await _journal(env, lob) == {lob.sids[2]: ("r", "held")}, \
            ("H4 retryable held", await _journal(env, lob))
        await A._janitor_tick(env)
        assert len(await _matches(env, lob)) == 1, ("H4 retry next tick",)
        env.mp.setattr(main, "_ffa_settle_report", real)

        # A terminal branch whose quarantine advisory lock is temporarily held
        # becomes a retryable 503 and must likewise retain its only receipt.
        lob = await _journaled_r(env)
        await env.set_lobby(lob, status="completed")
        R.bound_fast(env)
        done = await R.tick_holding(
            env, "SELECT pg_advisory_xact_lock(hashtext('mrq:' || $1::text))",
            str(lob.lid))
        assert done and await _journal(env, lob) == {
            lob.sids[2]: ("r", "held")}, ("H4 quarantine retry", done,
                                           await _journal(env, lob))
        await env.set_lobby(lob, status="active")
        await A._janitor_tick(env)
        assert len(await _matches(env, lob)) == 1, ("H4 quarantine next tick",)

        # Once the same terminal 409 is durably captured, it is terminal and
        # the chosen row is superseded rather than retried forever.
        lob = await _journaled_r(env)
        await env.set_lobby(lob, status="completed")
        await A._janitor_tick(env)
        assert await _journal(env, lob) == {lob.sids[2]: ("r", "superseded")}, \
            ("H4 terminal superseded", await _journal(env, lob))
        kept = await env.conn.fetchval(
            "SELECT count(*) FROM match_report_quarantine"
            " WHERE mode = 'ffa' AND group_id = $1", lob.lid)
        assert kept == 1, ("H4 terminal captured", kept)
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
