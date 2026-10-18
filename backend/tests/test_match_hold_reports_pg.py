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


async def _call(method, path, steam, body=None, params=None):
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
                await main._record_team_game_points(db, s.sid, 2, 2, game, seat)
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
                    await main._record_team_game_points(db, s.sid, 2, 2, game, seat)
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
