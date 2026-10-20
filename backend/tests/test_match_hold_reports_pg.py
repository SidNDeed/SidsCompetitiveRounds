"""NX4: the expiry outcomes and the report acceptance after a return (design
V3 S5), at the real main.app routes.

T5.1: a team hold frozen at one point, a live post during it, then a DC
report: dc_incomplete, as a report at the hold write would be; the report
closes the open hold (expiry_report) in its own commit. T5.4 at the routes,
both modes: for every non-empty set of the classes C, R and unclassed among
the filers, exactly one report settles, from the first non-empty class and
inside it the lowest Steam id; with fresh beats the lowest class C fighter
settles at once. T5.7: a game-over during a hold is journaled held, settled
at the entry, superseded at the lapse. T5.8: with the flag false the routes
answer exactly what today's path answers and write no window.

Runs on the hold suite's case schema (its Env and seeding; MATCH_HOLD_SRC as
in test_match_hold_pg.py).
"""

import hashlib
import hmac as _hmac
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))
sys.path.insert(0, HERE)

import test_match_hold_pg as hold_test  # noqa: E402
import database  # noqa: E402
import httpx  # noqa: E402
import main  # noqa: E402

VERSION = "1.41.0"


def _sig(canonical):
    return _hmac.new(hold_test.SECRET.encode(), canonical.encode(),
                     hashlib.sha256).hexdigest()


def _mount(env, monkeypatch):
    async def _db():
        async with env.sm() as sess:
            yield sess
    monkeypatch.setitem(main.app.dependency_overrides, database.get_db, _db)
    monkeypatch.setattr(database, "async_session", env.sm)
    # Each body starts with empty per-address rate buckets, as the other route
    # harnesses do: every request here comes from one test address, so the
    # buckets of earlier tests in the process would otherwise count against it.
    monkeypatch.setattr(main, "_RL_BUCKETS", main._rl_defaultdict(main._rl_deque))


async def _call(method, path, steam, body=None, params=None):
    # Every request starts with empty rate buckets: all of them come from one
    # test address, and the T5.4 matrix alone posts more reports to one
    # sensitive bucket than its limit admits per window on a fast seat, so a
    # per-body reset still answered 429 mid-matrix (G4 at 06e92cc8). No case
    # here tests the rate limit.
    main._RL_BUCKETS.clear()
    headers = {"X-Mod-Version": VERSION, "X-Session-Token": "tok:" + steam}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                 base_url="http://r", timeout=120) as cl:
        return await cl.request(method, path, json=body, params=params, headers=headers)


def _pmd(s, i):
    return {"steam_id": s.steam(i), "display_name": "p%d" % i}


def _game_fields(body, s, reporter, g):
    if g is not None:
        body["game_id"] = str(g)
        body["game_id_sig"] = _sig("game-id:%s:%s:%s" % (g, reporter, s.room))


def team_report(s, i, g=None, token="123456"):
    room = "%s_%s_r4" % (s.room, token)
    rep = s.steam(i)
    body = {"series_id": str(s.sid), "t1a": _pmd(s, 0), "t1b": _pmd(s, 1),
            "t2a": _pmd(s, 2), "t2b": _pmd(s, 3), "t1_rounds_won": 3, "t2_rounds_won": 1,
            "winner_team": 1, "photon_room_id": room, "is_ranked": True,
            "reported_by_steam_id": rep}
    body["hmac_signature"] = _sig("%s:%s:%s:%s:3:1:true:%s:%s:1:%s" % (
        s.steam(0), s.steam(1), s.steam(2), s.steam(3), rep, room, s.sid))
    _game_fields(body, s, rep, g)
    return body


def ovt_report(s, i, g=None, token="123456"):
    room = "%s_%s_r3" % (s.room, token)
    rep = s.steam(i)
    body = {"series_id": str(s.sid), "solo": _pmd(s, 0), "duo_a": _pmd(s, 1),
            "duo_b": _pmd(s, 2), "solo_rounds_won": 2, "duo_rounds_won": 1,
            "winner_side": 1, "photon_room_id": room, "is_ranked": False,
            "reported_by_steam_id": rep}
    body["hmac_signature"] = _sig("%s:%s:%s:2:1:false:%s:%s:1:%s" % (
        s.steam(0), s.steam(1), s.steam(2), rep, room, s.sid))
    _game_fields(body, s, rep, g)
    return body


def _report(mode, s, i, g=None):
    return team_report(s, i, g) if mode == "team" else ovt_report(s, i, g)


async def post_report(mode, s, i, g=None):
    return await _call("POST", "/api/v1/%s/matches" % mode, s.steam(i), _report(mode, s, i, g))


async def entered_hold(env, s, i, g):
    """Seat i has an entered hold for (room, G): its reports are class R."""
    slot, team = hold_test.seat_of(s, i)
    await env.conn.execute(
        "INSERT INTO match_seat_holds (mode, room_name, series_id, game_id, player_id, n,"
        "  slot, team, opener_player_id, held_anchor_at, held_at, held_until, seq,"
        "  entered_at, closed_at, closed_reason)"
        " VALUES ($1, $2, $3, $4::uuid, $5, 1, $6, $7, $8, clock_timestamp() - interval '60 s',"
        "  clock_timestamp() - interval '50 s', clock_timestamp() + interval '60 s', 2,"
        "  clock_timestamp(), clock_timestamp(), 'entered')",
        s.mode, s.room, s.sid, str(g), s.pid(i), slot, team, s.pid((i + 1) % len(s.seats)))


async def expire_and_janitor(env, s):
    await env.conn.execute(
        "UPDATE match_report_windows SET settle_after = clock_timestamp() - interval '1 s'"
        " WHERE room_name = $1", s.room)
    return await main._report_window_janitor()


async def window_state(env, s, g):
    w = await env.conn.fetchrow(
        "SELECT settled_at, settled_cls, settled_reporter_id, superseded_at"
        "  FROM match_report_windows WHERE room_name = $1 AND game_id = $2::uuid",
        s.room, str(g))
    j = {r["reporter_steam"]: (r["cls"], r["state"]) for r in await env.conn.fetch(
        "SELECT reporter_steam, cls, state FROM match_report_journal"
        " WHERE room_name = $1 AND game_id = $2::uuid", s.room, str(g))}
    return w, j


async def recorded(env, mode, s):
    return [dict(r) for r in await env.conn.fetch(
        "SELECT id, fallback_cls FROM %s WHERE series_id = $1"
        % ("team_matches" if mode == "team" else "ovt_matches"), s.sid)]


# -- T5.1 --------------------------------------------------------------------

def test_t5_1_dc_report_reads_the_crossing_the_hold_froze(monkeypatch, capsys):
    """T5.1: team 2 is a game up; the hold of seat 1 is opened at one point
    (crossed_at_hold false); during it a live post is ignored and the
    per-game record is then raised to both teams at two (what a fresh read
    would see); the DC report closes the open hold as expiry_report in its
    own commit and settles dc_incomplete, as a report at the hold write
    would."""
    async def body(env):
        _mount(env, monkeypatch)
        s = await hold_test.seed_series(env.conn, "team")
        await env.conn.execute("UPDATE team_series SET t2_series_wins = 1 WHERE id = $1", s.sid)
        g = (await hold_test.game_start(env, s, 0))["game_id"]
        for i in range(4):
            await hold_test.beat(env, s, i)
        await hold_test.backdate_presence(env, s, 1, 30)
        r = await hold_test.open_hold(env, s, 1, 0, g, rid="req-t51-open")
        assert r.status_code == 200 and r.json()["status"] == "opened", ("T5.1 open", r.text)
        hid = r.json()["hold_id"]
        assert (await hold_test.hold_db(env, hid))["crossed_at_hold"] is False, ("T5.1 at hold",)
        steam = s.steam(0)
        lp = await _call("POST", "/api/v1/team/series/%s/live-points" % s.sid, steam, params={
            "t1_points": 2, "t2_points": 2, "reporter_steam_id": steam,
            "sig": _sig("team-live-points:%s:%s:2:2" % (s.sid, steam))})
        assert lp.status_code == 200 and lp.json().get("reason") == "hold_open", \
            ("T5.1 live post", lp.status_code, lp.text[:300])
        async with env.sm() as db:
            row = (await db.execute(main.text(
                "SELECT t1_series_wins, t2_series_wins, photon_room_id FROM team_series"
                " WHERE id = :sid FOR NO KEY UPDATE"), {"sid": s.sid})).mappings().first()
            game = main._team_game_identity(row["t1_series_wins"], row["t2_series_wins"],
                                            row["photon_room_id"])
            for seat in (0, 2):
                await main._record_team_game_points(db, s.sid, 2, 2, game, seat,
                                                    attested=game)
            assert await main._team_game_crossed_two(db, s.sid, row), ("T5.1 record raised",)
            await db.commit()
        rep, dc = s.steam(2), s.steam(1)
        r = await _call("POST", "/api/v1/team/series/%s/report-dc" % s.sid, rep, params={
            "reporter_steam_id": rep, "dc_player_steam_id": dc, "t1_points_total": 2,
            "t2_points_total": 2, "photon_room_id": s.room,
            "hmac_sig": _sig("%s:%s:%s:dc" % (rep, s.sid, dc))})
        assert r.status_code == 200 and r.json()["status"] == "dc_incomplete", \
            ("T5.1 frozen", r.status_code, r.text[:300])
        h = await hold_test.hold_db(env, hid)
        st = await env.conn.fetchval("SELECT status FROM team_series WHERE id = $1", s.sid)
        assert (h["closed_reason"], st) == ("expiry_report", "dc_incomplete"), \
            ("T5.1 closed with the report", h["closed_reason"], st)
        assert "[HOLD] closed by DC report" in capsys.readouterr().out, ("T5.1 log",)
    hold_test.run_env(monkeypatch, body, prefix="rjs2nx4d")


# -- T5.4 at the routes ------------------------------------------------------

_CLASS_SETS = [("c",), ("r",), ("u",), ("c", "r"), ("c", "u"), ("r", "u"), ("c", "r", "u")]


def _assign(n, classes):
    """Filer i -> a class, every class of the set used at least once."""
    return [classes[i % len(classes)] for i in range(n)]


def _matrix(mode, monkeypatch):
    async def body(env):
        _mount(env, monkeypatch)
        n = 4 if mode == "team" else 3
        for classes in _CLASS_SETS:
            s = await hold_test.seed_series(env.conn, mode)
            g = (await hold_test.game_start(env, s, 0))["game_id"]
            cls_of = _assign(n, classes)
            for i, c in enumerate(cls_of):
                if c == "r":
                    await entered_hold(env, s, i, g)
            for i, c in enumerate(cls_of):
                r = await post_report(mode, s, i, None if c == "u" else g)
                assert r.status_code == 202 and r.json()["status"] == "journaled", \
                    ("T5.4 journal", mode, classes, i, r.status_code, r.text[:300])
                assert r.json()["cls"] == c, ("T5.4 class", mode, classes, i, r.json())
            assert await recorded(env, mode, s) == [], ("T5.4 none before expiry", mode, classes)
            await expire_and_janitor(env, s)
            w, j = await window_state(env, s, g)
            first = next(c for c in ("c", "r", "u") if c in cls_of)
            want = min((s.steam(i) for i, c in enumerate(cls_of) if c == first),
                       key=lambda x: (len(x), x))
            settled = [k for k, v in j.items() if v[1] == "settled"]
            rec = await recorded(env, mode, s)
            assert (w["settled_cls"], settled, len(rec), rec[0]["fallback_cls"] if rec else None) \
                == (first, [want], 1, first), \
                ("T5.4 one settlement", mode, classes, w and dict(w), j, rec)
            again = await post_report(mode, s, 0, None if cls_of[0] == "u" else g)
            assert again.status_code == 200 and "already recorded" in again.json()["message"].lower(), \
                ("T5.4 duplicate", mode, classes, again.status_code, again.text[:300])
            assert len(await recorded(env, mode, s)) == 1, ("T5.4 still one", mode, classes)

        # With fresh beats the lowest class C fighter settles at its receipt.
        s = await hold_test.seed_series(env.conn, mode)
        g = (await hold_test.game_start(env, s, 0))["game_id"]
        for i in range(n):
            await hold_test.beat(env, s, i)
        order = sorted(range(n), key=lambda i: (len(s.steam(i)), s.steam(i)))
        low = order[0]
        r = await post_report(mode, s, order[-1], g)
        assert r.status_code == 202, ("T5.4 not lowest journaled", mode, r.status_code, r.text[:300])
        r = await post_report(mode, s, low, g)
        assert r.status_code == 200 and len(await recorded(env, mode, s)) == 1, \
            ("T5.4 at once", mode, r.status_code, r.text[:300])
    return body


def test_t5_4_team_routes_settle_exactly_one_by_class(monkeypatch):
    hold_test.run_env(monkeypatch, _matrix("team", monkeypatch), prefix="rjs2nx4t")


def test_t5_4_ovt_routes_settle_exactly_one_by_class(monkeypatch):
    hold_test.run_env(monkeypatch, _matrix("ovt", monkeypatch), prefix="rjs2nx4o")


# -- T5.7 ----------------------------------------------------------------------

async def _held_game_over(env, mode):
    """A flagged series with seat 1 held and every present fighter's
    game-over report of G filed during the hold."""
    s, g, hid = await hold_test.held(env, mode)
    present = [i for i in range(len(s.seats)) if i != 1]
    for i in present:
        r = await post_report(mode, s, i, g)
        assert r.status_code == 202 and r.json().get("state") == "held", \
            ("T5.7 held", mode, i, r.status_code, r.text[:300])
    assert await recorded(env, mode, s) == [], ("T5.7 nothing settled during the hold", mode)
    return s, g, hid, present


def test_t5_7_held_game_over_settles_at_entry_and_is_superseded_at_lapse(monkeypatch):
    """T5.7: the held reports settle once at the entry (the lowest class C
    fighter) and, in a second series, are superseded at the lapse: kept,
    never settled, and a later report of G answers superseded."""
    async def body(env):
        _mount(env, monkeypatch)
        for mode in ("team", "ovt"):
            s, g, hid, present = await _held_game_over(env, mode)
            await hold_test.claim(env, s, 1, hid)
            others = [i for i in present]
            await hold_test.beat(env, s, others[0], seen=[(10 + others[0], s.steam(others[0])),
                                                           (21, s.steam(1))])
            await hold_test.bind(env, s, 1, hid, 21)
            await hold_test.beat(env, s, others[-1], seen=[(10 + others[-1], s.steam(others[-1])),
                                                            (21, s.steam(1))])
            en = await hold_test.entered(env, s, 1, hid, g, 21)
            assert en["status"] == "entered", ("T5.7 entry", mode, en)
            rec = await recorded(env, mode, s)
            w, j = await window_state(env, s, g)
            low = min((s.steam(i) for i in present), key=lambda x: (len(x), x))
            assert (len(rec), w["settled_cls"],
                    [k for k, v in j.items() if v[1] == "settled"]) == (1, "c", [low]), \
                ("T5.7 settled at entry", mode, rec, w and dict(w), j)

            s, g, hid, present = await _held_game_over(env, mode)
            await hold_test.shift_hold(env, hid, 300)
            async with env.sm() as db:
                await main._match_hold.hold_sweep(db)
            await main._report_window_janitor()
            w, j = await window_state(env, s, g)
            assert (w["superseded_at"] is not None, w["settled_at"],
                    sorted(v[1] for v in j.values()), await recorded(env, mode, s)) == \
                (True, None, ["superseded"] * len(present), []), \
                ("T5.7 superseded at x", mode, w and dict(w), j)
            late = await post_report(mode, s, present[0], g)
            assert late.status_code == 202 and late.json().get("state") == "superseded", \
                ("T5.7 late", mode, late.status_code, late.text[:300])
    hold_test.run_env(monkeypatch, body, prefix="rjs2nx4h")


# -- T5.8 ----------------------------------------------------------------------

def _strip(js):
    return {k: v for k, v in js.items() if k not in ("match_id", "series_id")}


def test_t5_8_unflagged_rooms_answer_as_today(monkeypatch):
    """T5.8 negative control: with the flag false, a team and a 1v2 report
    and a team DC report answer exactly what today's path answers (the same
    call with the Stage 2 arms switched off, on a twin series) and no window
    or journal row is written."""
    async def body(env):
        _mount(env, monkeypatch)
        real_rx, real_dc = main._report_window_receive, main._team_dc_hold_crossing

        async def _off_rx(db, mode, report):
            return None

        async def _off_dc(db, sid, s):
            return None

        for mode in ("team", "ovt"):
            answers = []
            for off in (False, True):
                monkeypatch.setattr(main, "_report_window_receive", _off_rx if off else real_rx)
                s = await hold_test.seed_series(env.conn, mode, flag=False)
                r = await post_report(mode, s, 0)
                assert r.status_code == 200, ("T5.8 report", mode, off, r.status_code, r.text[:300])
                answers.append(_strip(r.json()))
            assert answers[0] == answers[1], ("T5.8 report as today", mode, answers)
        answers = []
        for off in (False, True):
            monkeypatch.setattr(main, "_team_dc_hold_crossing", _off_dc if off else real_dc)
            s = await hold_test.seed_series(env.conn, "team", flag=False)
            await env.conn.execute("UPDATE team_series SET t2_series_wins = 1 WHERE id = $1", s.sid)
            async with env.sm() as db:
                row = (await db.execute(main.text(
                    "SELECT t1_series_wins, t2_series_wins, photon_room_id FROM team_series"
                    " WHERE id = :sid FOR NO KEY UPDATE"), {"sid": s.sid})).mappings().first()
                game = main._team_game_identity(row["t1_series_wins"], row["t2_series_wins"],
                                                row["photon_room_id"])
                for seat in (0, 2):
                    await main._record_team_game_points(db, s.sid, 2, 2, game, seat,
                                                        attested=game)
                await db.commit()
            rep, dc = s.steam(2), s.steam(1)
            r = await _call("POST", "/api/v1/team/series/%s/report-dc" % s.sid, rep, params={
                "reporter_steam_id": rep, "dc_player_steam_id": dc, "t1_points_total": 2,
                "t2_points_total": 2, "photon_room_id": s.room,
                "hmac_sig": _sig("%s:%s:%s:dc" % (rep, s.sid, dc))})
            assert r.status_code == 200, ("T5.8 dc", off, r.status_code, r.text[:300])
            js = r.json()
            js.pop("new_ratings", None)
            answers.append(js)
        assert answers[0] == answers[1] and answers[0]["status"] == "completed", \
            ("T5.8 dc as today", answers)
        n = await env.conn.fetchval(
            "SELECT (SELECT count(*) FROM match_report_windows)"
            "     + (SELECT count(*) FROM match_report_journal)")
        assert n == 0, ("T5.8 no window rows", n)
    hold_test.run_env(monkeypatch, body, prefix="rjs2nx4n")


# -- T5.9 ----------------------------------------------------------------------

async def _two_filed(env, mode):
    """A flagged series whose window of G holds two class C reports, expired;
    returns it with the Steam id the pick chooses."""
    s = await hold_test.seed_series(env.conn, mode)
    g = (await hold_test.game_start(env, s, 0))["game_id"]
    for i in (0, 1):
        r = await post_report(mode, s, i, g)
        assert r.status_code == 202 and r.json()["status"] == "journaled", \
            ("T5.9 journal", mode, i, r.status_code, r.text[:300])
    await env.conn.execute(
        "UPDATE match_report_windows SET settle_after = clock_timestamp() - interval '1 s'"
        " WHERE room_name = $1", s.room)
    return s, g, min((s.steam(0), s.steam(1)), key=lambda x: (len(x), x))


async def _untouched_then_settled(env, mode, s, g, want, out, route):
    w, j = await window_state(env, s, g)
    assert (out.get("bound"), out.get("refused"), w["settled_at"],
            sorted(v[1] for v in j.values()), await recorded(env, mode, s)) == \
        (1, None, None, ["journaled", "journaled"], []), \
        ("T5.9 a bound tick changes nothing", route, mode, out, w and dict(w), j)
    out = await main._report_window_janitor()
    w, j = await window_state(env, s, g)
    assert (out.get("settled"), [k for k, v in j.items() if v[1] == "settled"],
            len(await recorded(env, mode, s))) == (1, [want], 1), \
        ("T5.9 the next tick settles the pick", route, mode, out, w and dict(w), j)


def test_t5_9_a_settle_a_bound_ends_leaves_the_window_for_the_next_tick(monkeypatch):
    """T5.9 (the janitor census ruling of 2026-10-19): a settle ended by a
    bound changes nothing. Lock route: the series row is held by another
    transaction, so the settle's series lock times out (55P03); the window
    stays unsettled, no journal row is kept, nothing is recorded, and once
    the lock is gone the next tick settles the report the pick chose.
    Deadline route: a settle ended by the match database deadline's 503
    with no SQLSTATE on its chain leaves the window the same way."""
    async def body(env):
        _mount(env, monkeypatch)
        for mode in ("team", "ovt"):
            s, g, want = await _two_filed(env, mode)
            tx = env.conn.transaction()
            await tx.start()
            try:
                await env.conn.execute(
                    "SELECT 1 FROM %s WHERE id = $1 FOR UPDATE"
                    % ("team_series" if mode == "team" else "ovt_series"), s.sid)
                out = await main._report_window_janitor()
            finally:
                await tx.rollback()
            await _untouched_then_settled(env, mode, s, g, want, out, "lock")

            s, g, want = await _two_filed(env, mode)

            def _expired(_mode):
                async def settle(db, entry):
                    try:
                        raise TimeoutError()
                    except TimeoutError as exc:
                        raise main.HTTPException(status_code=503,
                                                 detail="database_deadline") from exc
                return settle
            with monkeypatch.context() as m:
                m.setattr(main, "_report_window_settler", _expired)
                out = await main._report_window_janitor()
            await _untouched_then_settled(env, mode, s, g, want, out, "deadline")
    hold_test.run_env(monkeypatch, body, prefix="rjs2nx4b")


# -- Fix 1 H1: the physical report precedes its advisory window -----------------

def test_fix1_h1_recorded_game_never_touches_the_next_window(monkeypatch):
    """Both modes and valid, missing, invalid G2 advisories on a G1 replay."""
    async def body(env):
        _mount(env, monkeypatch)
        for mode in ("team", "ovt"):
            for advisory in ("valid", "missing", "invalid"):
                s = await hold_test.seed_series(env.conn, mode)
                g1 = (await hold_test.game_start(env, s, 0))["game_id"]
                low = min(range(len(s.seats)), key=lambda i: (len(s.steam(i)), s.steam(i)))
                await hold_test.beat(env, s, low)
                build = team_report if mode == "team" else ovt_report

                def make(series, reporter, game, token):
                    # The signed series text may use a different UUID spelling.
                    # Both the resolver and the internal outcome use its UUID value.
                    from types import SimpleNamespace
                    view = SimpleNamespace(sid=str(series.sid).upper(), room=series.room,
                                           steam=series.steam)
                    return build(view, reporter, game, token=token)

                first = make(s, low, g1, token="111111")
                r = await _call("POST", "/api/v1/%s/matches" % mode, s.steam(low), first)
                assert r.status_code == 200, ("F1.H1 first", mode, r.status_code, r.text[:300])
                g2 = (await hold_test.game_start(env, s, low, prev=g1))["game_id"]
                replay = make(s, low, None if advisory == "missing" else g2, token="111111")
                if advisory == "invalid":
                    replay["game_id_sig"] = "invalid"
                r = await _call("POST", "/api/v1/%s/matches" % mode, s.steam(low), replay)
                w, j = await window_state(env, s, g2)
                assert r.status_code == 200 and w is None and j == {}, \
                    ("F1.H1 physical game", mode, advisory, r.status_code, r.text[:300], w, j)
                assert "recorded" in r.json()["message"].lower(), ("F1.H1 duplicate", r.json())
                await hold_test.beat(env, s, low)
                second = make(s, low, g2, token="222222")
                r = await _call("POST", "/api/v1/%s/matches" % mode, s.steam(low), second)
                assert r.status_code == 200, ("F1.H1 second", mode, r.status_code, r.text[:300])
                again = await _call("POST", "/api/v1/%s/matches" % mode, s.steam(low), second)
                w, j = await window_state(env, s, g2)
                tbl = "team_matches" if mode == "team" else "ovt_matches"
                n = await env.conn.fetchval(
                    "SELECT count(*) FROM %s WHERE photon_room_id = $1" % tbl,
                    second["photon_room_id"])
                stable = "team_series" if mode == "team" else "ovt_series"
                wins = "t1_series_wins + t2_series_wins" if mode == "team" else "solo_series_wins + duo_series_wins"
                total = await env.conn.fetchval("SELECT %s FROM %s WHERE id = $1" % (wins, stable), s.sid)
                assert (again.status_code, n, total, len(await recorded(env, mode, s)),
                        w["settled_at"] is not None, w["settled_reporter_id"]) == \
                    (200, 1, 2, 2, True, s.pid(low)), ("F1.H1 exactly once", mode, advisory, n, total, w)
    hold_test.run_env(monkeypatch, body, prefix="rjs2f1h1")


def test_fix1_h1_racing_duplicate_does_not_spend_next_reporter(monkeypatch):
    """A physical result appears after the first lookup; G2's slot survives."""
    async def body(env):
        _mount(env, monkeypatch)
        for mode in ("team", "ovt"):
            s = await hold_test.seed_series(env.conn, mode)
            low = min(range(len(s.seats)), key=lambda i: (len(s.steam(i)), s.steam(i)))
            g1 = (await hold_test.game_start(env, s, low))["game_id"]
            await hold_test.beat(env, s, low)
            r = await post_report(mode, s, low, g1)
            assert r.status_code == 200, ("F1.H1 race setup", r.text)
            g2 = (await hold_test.game_start(env, s, low, prev=g1))["game_id"]
            real = main._recorded_physical_report
            looked = []

            async def race(*args):
                looked.append(True)
                return None if len(looked) == 1 else await real(*args)

            with monkeypatch.context() as patch:
                patch.setattr(main, "_recorded_physical_report", race)
                r = await post_report(mode, s, low, g2)
            w, j = await window_state(env, s, g2)
            assert r.status_code == 200 and w is None and not j, \
                ("F1.H1 new settlement only", mode, r.status_code, r.text[:300], w, j)
            make = team_report if mode == "team" else ovt_report
            r = await _call("POST", "/api/v1/%s/matches" % mode, s.steam(low),
                            make(s, low, g2, token="222222"))
            w, j = await window_state(env, s, g2)
            assert r.status_code == 200 and w["settled_at"] is not None \
                and w["settled_reporter_id"] == s.pid(low) and len(await recorded(env, mode, s)) == 2, \
                ("F1.H1 reporter slot survives", mode, r.status_code, r.text[:300], w, j)
    hold_test.run_env(monkeypatch, body, prefix="rjs2f1h1race")


# -- Merged fix 1 H2 -----------------------------------------------------------

def test_merged_fix1_h2_causal_lapse_and_delayed_receipt(monkeypatch):
    """An earlier entered hold never authorizes a later lapsed hold's reports."""
    from datetime import timedelta

    async def body(env):
        _mount(env, monkeypatch)
        for mode in ("team", "ovt"):
            s, g, _ = await hold_test.opened_series(env, mode)
            await entered_hold(env, s, 0, g)
            opened = await hold_test.open_hold(env, s, 1, 0, g)
            assert opened.status_code == 200 and opened.json()["status"] == "opened"
            hid = opened.json()["hold_id"]
            for i in (0, 2):
                response = await post_report(mode, s, i, g)
                assert response.status_code == 202 and response.json().get("state") == "held"
            causes = await env.conn.fetch(
                "SELECT payload ->> '_causal_hold_id' AS cause FROM match_report_journal"
                " WHERE room_name = $1", s.room)
            assert [r["cause"] for r in causes] == [hid, hid], ("H2 causal stamp", mode, causes)
            stamp = (await hold_test.hold_db(env, hid))["held_until"] + timedelta(seconds=1)

            async def clock(db):
                return stamp

            with monkeypatch.context() as patch:
                patch.setattr(main._match_hold, "_ctx_now", clock)
                async with env.sm() as db:
                    await main._match_hold.hold_sweep(db)
                await main._report_window_janitor()
            w, j = await window_state(env, s, g)
            assert (w["superseded_at"] is not None, w["settled_at"],
                    sorted(v[1] for v in j.values()), await recorded(env, mode, s)) == \
                (True, None, ["superseded", "superseded"], []), \
                ("H2 causal lapse", mode, w and dict(w), j)

            # A closure with no earlier report is terminal both on receipt
            # and on the janitor path, which must not depend on journal rows.
            for janitor_first in (False, True):
                late, late_g, late_h = await hold_test.held(env, mode)
                stamp = (await hold_test.hold_db(env, late_h))["held_until"] + timedelta(seconds=1)
                with monkeypatch.context() as patch:
                    patch.setattr(main._match_hold, "_ctx_now", clock)
                    async with env.sm() as db:
                        await main._match_hold.hold_sweep(db)
                    if janitor_first:
                        await main._report_window_janitor()
                        prior, journal = await window_state(env, late, late_g)
                        assert prior["superseded_at"] is not None and journal == {}, \
                            ("H2 no-journal closure", mode, prior, journal)
                    response = await post_report(mode, late, 0, late_g)
                assert response.status_code == 202 and response.json().get("state") == "superseded", \
                    ("H2 delayed first", mode, janitor_first, response.status_code, response.text)
                assert await recorded(env, mode, late) == []
    hold_test.run_env(monkeypatch, body, prefix="mergedh2c")


def test_merged_fix1_h2_held_receipts_outlive_first_receipt(monkeypatch):
    """Move the harness clock, without sleeping, across the old 30 s cutoff."""
    from datetime import timedelta

    async def body(env):
        _mount(env, monkeypatch)
        for mode in ("team", "ovt"):
            s, g, hid = await hold_test.held(env, mode)
            stamp = await hold_test.dbclock(env)

            async def clock(db):
                return stamp

            with monkeypatch.context() as patch:
                patch.setattr(main._match_hold, "_ctx_now", clock)
                first = await post_report(mode, s, 0, g)
                stamp += timedelta(seconds=31)
                second = await post_report(mode, s, 2, g)
            assert first.status_code == second.status_code == 202
            assert first.json().get("state") == second.json().get("state") == "held", \
                ("H2 live hold keeps receipts eligible", mode, first.text, second.text)
            rows = await env.conn.fetch(
                "SELECT state, received_at FROM match_report_journal WHERE room_name = $1"
                " ORDER BY received_at", s.room)
            assert len(rows) == 2 and [r["state"] for r in rows] == ["held", "held"], \
                ("H2 both receipts journaled", mode, rows)
            assert rows[1]["received_at"] - rows[0]["received_at"] == timedelta(seconds=31)
            assert await recorded(env, mode, s) == []
    hold_test.run_env(monkeypatch, body, prefix="mergedh2e")


def test_merged_fix1_h2_receipt_open_and_end_races(monkeypatch):
    """Barrier-order receipt/open and receipt/end both ways, in both modes."""
    import asyncio

    async def body(env):
        _mount(env, monkeypatch)
        mrw = main._mrw_mod()
        mh = main._match_hold
        for mode in ("team", "ovt"):
            for first in ("receipt", "open"):
                s, g, _ = await hold_test.opened_series(env, mode)
                ready, release, competing = asyncio.Event(), asyncio.Event(), asyncio.Event()
                real_causal, real_decide = mrw._causal_hold, mh._open_decide

                async def causal(*args, **kwargs):
                    if first == "open":
                        competing.set()
                    result = await real_causal(*args, **kwargs)
                    if first == "receipt":
                        ready.set()
                        await release.wait()
                    return result

                async def decide(*args, **kwargs):
                    if first == "receipt":
                        competing.set()
                    result = await real_decide(*args, **kwargs)
                    if first == "open":
                        ready.set()
                        await release.wait()
                    return result

                with monkeypatch.context() as patch:
                    patch.setattr(mrw, "_causal_hold", causal)
                    patch.setattr(mh, "_open_decide", decide)
                    async def receipt():
                        return await post_report(mode, s, 2, g)
                    async def opening():
                        return await hold_test.open_hold(env, s, 1, 0, g)
                    actions = {"receipt": receipt, "open": opening}
                    lead = asyncio.create_task(actions[first]())
                    await asyncio.wait_for(ready.wait(), 3)
                    other = "open" if first == "receipt" else "receipt"
                    trail = asyncio.create_task(actions[other]())
                    await asyncio.wait_for(competing.wait(), 3)
                    release.set()
                    answers = await asyncio.wait_for(asyncio.gather(lead, trail), 7)
                answer = answers[0] if first == "receipt" else answers[1]
                opening_answer = answers[1] if first == "receipt" else answers[0]
                assert opening_answer.status_code == 200 and opening_answer.json()["status"] == "opened", \
                    ("H2 opening race", mode, first, opening_answer.text)
                assert answer.status_code == 202
                assert answer.json().get("state") == ("held" if first == "open" else None), \
                    ("H2 open order", mode, first, answer.text)
                assert await recorded(env, mode, s) == []

            for first in ("receipt", "end"):
                s, g, hid = await hold_test.held(env, mode)
                ready, release, competing = asyncio.Event(), asyncio.Event(), asyncio.Event()
                real_causal, real_hold = mrw._causal_hold, mh._hold_row

                async def causal(*args, **kwargs):
                    if first == "end":
                        competing.set()
                    result = await real_causal(*args, **kwargs)
                    if first == "receipt":
                        ready.set()
                        await release.wait()
                    return result

                async def holdrow(*args, **kwargs):
                    if not kwargs.get("lock"):
                        return await real_hold(*args, **kwargs)
                    if first == "receipt":
                        competing.set()
                    result = await real_hold(*args, **kwargs)
                    if first == "end":
                        ready.set()
                        await release.wait()
                    return result

                with monkeypatch.context() as patch:
                    patch.setattr(mrw, "_causal_hold", causal)
                    patch.setattr(mh, "_hold_row", holdrow)
                    async def receipt():
                        return await post_report(mode, s, 2, g)
                    async def ending():
                        return await env.post("/api/v1/match/hold/%s/end" % hid, s.steam(0),
                                              {"steam_id": s.steam(0), "reason": "refused"})
                    actions = {"receipt": receipt, "end": ending}
                    lead = asyncio.create_task(actions[first]())
                    await asyncio.wait_for(ready.wait(), 3)
                    other = "end" if first == "receipt" else "receipt"
                    trail = asyncio.create_task(actions[other]())
                    await asyncio.wait_for(competing.wait(), 3)
                    release.set()
                    answers = await asyncio.wait_for(asyncio.gather(lead, trail), 7)
                response = answers[0] if first == "receipt" else answers[1]
                ending_answer = answers[1] if first == "receipt" else answers[0]
                assert ending_answer.status_code == 200
                assert response.status_code == 202
                assert response.json().get("state") == ("held" if first == "receipt" else "superseded"), \
                    ("H2 end order", mode, first, response.text)
                await main._report_window_janitor()
                w, j = await window_state(env, s, g)
                assert w["superseded_at"] is not None and await recorded(env, mode, s) == [], \
                    ("H2 end race terminal", mode, first, w, j)
    hold_test.run_env(monkeypatch, body, prefix="mergedh2r")


# -- Merged fix 1 H3 -----------------------------------------------------------

def test_merged_fix1_h3_two_janitors_keep_only_their_attempt(monkeypatch):
    """Both janitors reject A; the second commits before the first rechecks."""
    import asyncio

    async def body(env):
        _mount(env, monkeypatch)
        for mode in ("team", "ovt"):
            s = await hold_test.seed_series(env.conn, mode)
            g = (await hold_test.game_start(env, s, 0))["game_id"]
            indices = sorted((0, 1), key=lambda i: (len(s.steam(i)), s.steam(i)))
            bad_i, good_i = indices
            for i in indices:
                report = _report(mode, s, i, g)
                if i == bad_i:
                    if mode == "team":
                        report["winner_team"] = 2
                        canonical = "%s:%s:%s:%s:3:1:true:%s:%s:2:%s" % (
                            s.steam(0), s.steam(1), s.steam(2), s.steam(3),
                            s.steam(i), report["photon_room_id"], s.sid)
                    else:
                        report["winner_side"] = 2
                        canonical = "%s:%s:%s:2:1:false:%s:%s:2:%s" % (
                            s.steam(0), s.steam(1), s.steam(2), s.steam(i),
                            report["photon_room_id"], s.sid)
                    report["hmac_signature"] = _sig(canonical)
                response = await _call("POST", "/api/v1/%s/matches" % mode, s.steam(i), report)
                assert response.status_code == 202, ("H3 setup receipt", mode, response.text)
            await env.conn.execute(
                "UPDATE match_report_windows SET settle_after = clock_timestamp() - interval '1 s'"
                " WHERE room_name = $1", s.room)
            first_rolled_back, release_first = asyncio.Event(), asyncio.Event()
            attempted = []
            real_settler = main._report_window_settler
            session_type = env.sm.class_
            real_rollback = session_type.rollback

            def observed_settler(the_mode):
                settle = real_settler(the_mode)
                async def observed(db, entry):
                    attempted.append((asyncio.current_task().get_name(), entry["reporter_steam"]))
                    return await settle(db, entry)
                return observed

            async def rollback(db):
                result = await real_rollback(db)
                if asyncio.current_task().get_name() == "h3-first":
                    first_rolled_back.set()
                    await release_first.wait()
                return result

            with monkeypatch.context() as patch:
                patch.setattr(main, "_report_window_settler", observed_settler)
                patch.setattr(session_type, "rollback", rollback)
                first = asyncio.create_task(main._report_window_janitor(), name="h3-first")
                try:
                    await asyncio.wait_for(first_rolled_back.wait(), 4)
                    second = asyncio.create_task(main._report_window_janitor(), name="h3-second")
                    await asyncio.wait_for(second, 7)
                finally:
                    release_first.set()
                await asyncio.wait_for(first, 7)
            assert attempted == [("h3-first", s.steam(bad_i)), ("h3-second", s.steam(bad_i))], \
                ("H3 both attempt A", mode, attempted)
            w, j = await window_state(env, s, g)
            assert (w["settled_at"], j[s.steam(bad_i)][1], j[s.steam(good_i)][1]) == \
                (None, "kept", "journaled"), ("H3 exact attempted row", mode, w, j)
            out = await main._report_window_janitor()
            w, j = await window_state(env, s, g)
            assert out.get("settled") == 1 and j[s.steam(good_i)][1] == "settled" \
                and len(await recorded(env, mode, s)) == 1, \
                ("H3 B settles next tick", mode, out, w, j)
    hold_test.run_env(monkeypatch, body, prefix="mergedh3j")


def test_merged_fix1_h3_unknown_and_transient_failures_keep_evidence(monkeypatch):
    """An unknown exception or retryable HTTP response never rejects evidence."""
    async def body(env):
        _mount(env, monkeypatch)
        for mode in ("team", "ovt"):
            for failure in (RuntimeError("transient fixture"), main.HTTPException(429, "retry")):
                s, g, want = await _two_filed(env, mode)
                def refusing(the_mode):
                    async def settle(db, entry):
                        raise failure
                    return settle
                with monkeypatch.context() as patch:
                    patch.setattr(main, "_report_window_settler", refusing)
                    out = await main._report_window_janitor()
                w, j = await window_state(env, s, g)
                assert (out.get("retry"), out.get("refused"), w["settled_at"],
                        sorted(v[1] for v in j.values())) == \
                    (1, None, None, ["journaled", "journaled"]), \
                    ("H3 unknown failure retry", mode, type(failure).__name__, out, w, j)
                await main._report_window_janitor()
                w, j = await window_state(env, s, g)
                assert j[want][1] == "settled" and len(await recorded(env, mode, s)) == 1
    hold_test.run_env(monkeypatch, body, prefix="mergedh3t")


# -- Merged fix 1 M1 -----------------------------------------------------------

def test_merged_fix1_m1_quarantine_preserves_window_transaction(monkeypatch):
    """Immediate, expiry and entry release, each at capture/quota/failure.

    Pause capture before its owner commits. A competing receipt starts then;
    NOWAIT observes the actual window lock, including the failure savepoint.
    """
    import asyncio
    import asyncpg
    import uuid

    async def body(env):
        _mount(env, monkeypatch)
        for dispatch in ("immediate", "expired", "held"):
            for variant in ("recorded", "quota", "failure"):
                if dispatch == "held":
                    s, g, hid = await hold_test.held(env, "team")
                    low = 0
                    initial = await post_report("team", s, low, g)
                    assert initial.status_code == 202 and initial.json()["state"] == "held"
                    await env.conn.execute(
                        "UPDATE match_seat_holds SET entered_at = clock_timestamp(),"
                        " closed_at = clock_timestamp(), closed_reason = 'entered'"
                        " WHERE id = $1", uuid.UUID(hid))
                else:
                    s = await hold_test.seed_series(env.conn, "team")
                    g = (await hold_test.game_start(env, s, 0))["game_id"]
                    low = min(range(4), key=lambda i: (len(s.steam(i)), s.steam(i)))
                    if dispatch == "immediate":
                        await hold_test.beat(env, s, low)
                        # Preexisting, empty window makes its row lock visible
                        # to NOWAIT while the new journal is still uncommitted.
                        async with env.sm() as db:
                            await main._mrw_mod().lock_window(
                                db, mode="team", room=s.room, game_id=g,
                                now=await hold_test.dbclock(env))
                            await db.commit()
                    else:
                        initial = await post_report("team", s, low, g)
                        assert initial.status_code == 202
                        await env.conn.execute(
                            "UPDATE match_report_windows SET settle_after ="
                            " clock_timestamp() - interval '1 second' WHERE room_name = $1", s.room)
                await env.conn.execute(
                    "UPDATE team_series SET status = 'completed' WHERE id = $1", s.sid)
                if variant == "quota":
                    await env.conn.execute(
                        "INSERT INTO match_report_quarantine"
                        " (mode,reason,http_status,group_id,payload)"
                        " SELECT 'team','quota-control',400,$1,jsonb_build_object('seed',n)"
                        " FROM generate_series(1,50) n", s.sid)
                paused, release, competitor_started = (asyncio.Event() for _ in range(3))
                captures = []
                real_capture = main._quarantine_report
                real_receive = main._report_window_receive

                async def capture(*args, **kwargs):
                    result = await real_capture(*args, **kwargs)
                    if kwargs.get("in_window"):
                        captures.append(result)
                        if len(captures) == 1:
                            paused.set()
                            await release.wait()
                    return result

                async def failure(db, **kwargs):
                    # Exercise a PostgreSQL-aborted savepoint, not only a
                    # Python exception that leaves the transaction usable.
                    await db.execute(main.text("SELECT 1 / 0"))

                async def competing_receive(*args, **kwargs):
                    competitor_started.set()
                    return await real_receive(*args, **kwargs)

                async def first_dispatch():
                    if dispatch == "immediate":
                        return await post_report("team", s, low, g)
                    if dispatch == "expired":
                        return await main._report_window_janitor()
                    async with env.sm() as db:
                        return await main._finish_held_reports(db, "team", s.room, g, hid)

                with monkeypatch.context() as patch:
                    patch.setattr(main, "_quarantine_report", capture)
                    if variant == "failure":
                        patch.setattr(main, "_quarantine_on_file", failure)
                    first = asyncio.create_task(first_dispatch())
                    other = None
                    try:
                        await asyncio.wait_for(paused.wait(), 10)
                        locked = False
                        try:
                            async with env.conn.transaction():
                                await env.conn.fetchrow(
                                    "SELECT 1 FROM match_report_windows WHERE room_name = $1"
                                    " AND game_id = $2::uuid FOR NO KEY UPDATE NOWAIT", s.room, str(g))
                        except asyncpg.LockNotAvailableError:
                            locked = True
                        assert locked, ("M1 owner transaction", dispatch, variant, locked)
                        patch.setattr(main, "_report_window_receive", competing_receive)
                        other = asyncio.create_task(post_report("team", s, low, g))
                        await asyncio.wait_for(competitor_started.wait(), 10)
                        assert not other.done(), ("M1 competing receipt waits", dispatch, variant)
                    finally:
                        release.set()
                        results = await asyncio.gather(
                            *([first, other] if other is not None else [first]),
                            return_exceptions=True)
                    assert not any(isinstance(r, BaseException) for r in results), \
                        ("M1 owner transaction", dispatch, variant, results)
                    if dispatch == "immediate":
                        assert results[0].status_code == 400 and results[0].json() == \
                            {"detail": "team_series is completed"}, \
                            ("M1 refusal response", variant, results[0].text)
                    repeat = await post_report("team", s, low, g)
                    assert repeat.status_code == 400 and repeat.json() == {"detail": "team_series is completed"} and captures == \
                        [{"recorded": "recorded", "quota": "quota", "failure": "failed"}[variant]], \
                        ("M1 refusal once", dispatch, variant, captures, repeat.text)
                w, j = await window_state(env, s, g)
                assert w is not None and w["settled_at"] is None and w["superseded_at"] is None \
                    and j == {s.steam(low): ("c", "kept")} and await recorded(env, "team", s) == [], \
                    ("M1 durable refusal", dispatch, variant, w, j)
                count = await env.conn.fetchval(
                    "SELECT count(*) FROM match_report_quarantine WHERE group_id = $1", s.sid)
                assert count == {"recorded": 1, "quota": 50, "failure": 0}[variant], \
                    ("M1 capture outcome", dispatch, variant, count)
    hold_test.run_env(monkeypatch, body, prefix="mergedm1")


def test_merged_fix1_m1_first_refusal_keeps_new_window_and_journal(monkeypatch):
    """The first immediate refusal owns both new inserts through its commit."""
    async def body(env):
        _mount(env, monkeypatch)
        s = await hold_test.seed_series(env.conn, "team")
        g = (await hold_test.game_start(env, s, 0))["game_id"]
        low = min(range(4), key=lambda i: (len(s.steam(i)), s.steam(i)))
        await hold_test.beat(env, s, low)
        await env.conn.execute("UPDATE team_series SET status = 'completed' WHERE id = $1", s.sid)
        response = await post_report("team", s, low, g)
        w, j = await window_state(env, s, g)
        assert response.status_code == 400 and response.json() == {"detail": "team_series is completed"} \
            and w is not None and w["settled_at"] is None and j == {s.steam(low): ("c", "kept")}, \
            ("M1 new inserts survive", response.status_code, response.text, w, j)
        assert await recorded(env, "team", s) == []
        assert await env.conn.fetchval(
            "SELECT count(*) FROM match_report_quarantine WHERE group_id = $1", s.sid) == 1
    hold_test.run_env(monkeypatch, body, prefix="mergedm1new")
