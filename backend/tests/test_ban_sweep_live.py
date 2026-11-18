"""Bans part 2a, driven against a real PostgreSQL: T2 (per class, a banned
account and a control account, with session enforcement off and on), T4 (a
timed ban whose end has passed admits again), T5 (the report refusals, the
void closure and the others' release, the gift receiver, the banned admin),
T6 (the refusal line), the S2 exits, and S10 (BAN-R20: the length branch
judges the ban's end by the wall clock after the identity lock), each with
the mutant that fails it.

One case schema is built for the module by the ladder harness's procedure
(test_title_ladder_hooks_live._build), sealed, and dropped under its census
at the end.

    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    LADDER_TEST_PG_OPTOUT=1   waives the live cases deliberately (else they FAIL)

Every account is a synthetic id below the first individual-account
SteamID64. Nothing sleeps: an ended ban is a row whose end is moved behind
the database's clock.

"Changes no row" is read as a digest of every table of the case schema
(each table's rows, as text, sorted), taken before and after the refused
call.
"""
import asyncio
import contextlib
import hashlib
import hmac as _hmac
import inspect
import itertools
import os
import re
import sys
import types
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402
from starlette.requests import Request  # noqa: E402

import main  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402

_IDS = itertools.count(1)
HMAC_KEY = "ban-sweep-match-key"
ADMIN_KEY = "ban-sweep-admin-key"
ID_RUN = re.compile(r"\d{17}")


def _sid():
    """A fresh synthetic SteamID64-shaped key (17 digits, below 76561197960265728)."""
    return "76561190520%06d" % next(_IDS)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def case():
    lh._require_live_pg()
    built = {}

    async def build():
        c = harness.CaseSchema(lh.DSN, "ban_sweep")
        await c.__aenter__()
        try:
            await lh._build(c)
        except BaseException:
            await c.__aexit__(None, None, None)
            raise
        built.update(schema=c.schema, own=c.own)
        await c.conn.close()
    _run(build())
    try:
        yield built["schema"]
    finally:
        async def drop():
            conn = await harness.connect_bound(lh.DSN, built["schema"])
            try:
                await harness.drop_case_schema(conn, built["schema"], built["own"])
            finally:
                await conn.close()
        _run(drop())


def _with_sm(schema, body, mode=None):
    async def go():
        if mode == "enforce":
            main._current_mod_version.set("99.0.0")
        engine = harness.bound_engine(lh.DSN, schema)
        try:
            return await body(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()
    return _run(go())


@pytest.fixture(params=["soft", "enforce"])
def mode(request, monkeypatch):
    """BAN-R13's two modes: session enforcement off (the soft-fail path) and
    on (key set, enforcement armed, a client version at or above the floor)."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", HMAC_KEY)
    monkeypatch.setattr(main, "ADMIN_HMAC_SECRET", ADMIN_KEY)
    if request.param == "enforce":
        monkeypatch.setenv("STEAM_AUTH_ENFORCE", "1")
        monkeypatch.setenv("STEAM_WEB_API_KEY", "ban-sweep-web-key")
    else:
        monkeypatch.delenv("STEAM_AUTH_ENFORCE", raising=False)
        monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)
    return request.param


@pytest.fixture
def soft(monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", HMAC_KEY)
    monkeypatch.setattr(main, "ADMIN_HMAC_SECRET", ADMIN_KEY)
    monkeypatch.delenv("STEAM_AUTH_ENFORCE", raising=False)
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)
    return "soft"


# -- helpers ----------------------------------------------------------------

def _req(template, token=None):
    headers = [(b"x-session-token", token.encode())] if token else []
    return Request({"type": "http", "method": "POST", "path": "/", "headers": headers,
                    "query_string": b"", "client": ("127.0.0.1", 1),
                    "route": types.SimpleNamespace(path=template)})


async def _call(fn, **kw):
    """Call a route handler directly: a parameter left out takes its
    declared default (a Query's own default; a dependency other than db is
    None)."""
    for name, p in inspect.signature(fn).parameters.items():
        if name in kw:
            continue
        d = p.default
        if d is inspect.Parameter.empty:
            continue
        inner = getattr(d, "default", d)
        if type(d).__name__ == "Depends" or inner is Ellipsis or "Undefined" in type(inner).__name__:
            kw[name] = None
        else:
            kw[name] = inner
    return await fn(**kw)


def _sig(canonical):
    return _hmac.new(HMAC_KEY.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def _admin_sig(admin, action, target):
    return _hmac.new(ADMIN_KEY.encode(), main._admin_canonical(admin, action, target).encode(),
                     hashlib.sha256).hexdigest()


async def _player(db, sid, **extra):
    pid = uuid.uuid4()
    values = {"id": pid, "steam_id": sid, "display_name": "bs-" + sid[-4:]}
    values.update(extra)
    await lh._insert(db, "players", values)
    return pid


async def _session(db, sid):
    token = "bs-token-" + uuid.uuid4().hex
    await db.execute(text(
        "INSERT INTO steam_sessions (token_hash, steam_id, verified, issued_at, expires_at)"
        " VALUES (:th, :s, true, NOW(), NOW() + INTERVAL '1 day')"),
        {"th": hashlib.sha256(token.encode()).hexdigest(), "s": sid})
    return token


async def _admin(db):
    """An admin roster row (player_bans.banned_by_steam_id references it)."""
    sid = _sid()
    await lh._insert(db, "admin_users", {"steam_id": sid})
    return sid


async def _ban(sm, target, minutes=60):
    async with sm() as db:
        admin = await _admin(db)
        ans = await main._apply_ban_core(db, admin_steam_id=admin, target_steam_id=target,
                                         reason="ban-sweep", duration_minutes=minutes)
        await db.commit()
    assert ans["status"] == "banned", ans
    return ans


async def _digest(sm):
    async with sm() as db:
        names = (await db.execute(text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p') ORDER BY 1"))).scalars().all()
        out = {}
        for t in names:
            out[t] = (await db.execute(text(
                f'SELECT md5(COALESCE(string_agg(x::text, \'|\' ORDER BY x::text), \'\')) FROM "{t}" x'
            ))).scalar()
        return out


async def _refused(coro):
    try:
        ans = await coro
    except HTTPException as e:
        return (e.status_code, str(e.detail))
    return ("admitted", ans)


async def _expect_refused_no_row(sm, coro_fn, want):
    before = await _digest(sm)
    async with sm() as db:
        got = await _refused(coro_fn(db))
        await db.rollback()
    after = await _digest(sm)
    changed = sorted(t for t in before if before[t] != after.get(t))
    assert got[0] == want[0] and str(got[1]).startswith(want[1]), got
    assert changed == [], changed
    return got


def _banned_answer(mode):
    """The answer a SOFT route gives an actively banned account: its 409 on
    the soft-fail path; with enforcement on, the 401 for the session the ban
    deleted."""
    return (409, "Banned: ") if mode == "soft" else (401, "")


# -- T2: per class, banned and control, both modes ---------------------------

async def _hide_gold_world(sm):
    async with sm() as db:
        item = (await db.execute(text("SELECT id FROM shop_items WHERE sku = 'util_hide_gold'"))).scalar()
        if item is None:
            await lh._insert(db, "shop_items", {"sku": "util_hide_gold", "name": "hide gold", "price": 0})
            item = (await db.execute(text("SELECT id FROM shop_items WHERE sku = 'util_hide_gold'"))).scalar()
        out = []
        for _ in range(2):
            sid = _sid()
            pid = await _player(db, sid)
            await lh._insert(db, "player_items", {"player_id": pid, "item_id": item})
            out.append((sid, await _session(db, sid)))
        await db.commit()
    return out


def _hide_gold(sid, token):
    return lambda db: _call(main.set_hide_gold, steam_id=sid,
                            request=_req("/api/v1/players/{steam_id}/hide-gold", token),
                            on=True, sig=_sig(f"hide_gold:{sid}:1"), db=db)


def test_t2_soft_class_refuses_the_banned_account_and_admits_the_control(case, mode):
    async def body(sm):
        (b, bt), (c, ct) = await _hide_gold_world(sm)
        await _ban(sm, b)
        await _expect_refused_no_row(sm, _hide_gold(b, bt), _banned_answer(mode))
        async with sm() as db:
            ans = await _hide_gold(c, ct)(db)
        assert ans == {"status": "set", "hide_gold": True}, ans
    _with_sm(case, body, mode)


def test_t2_strict_class_refuses_the_banned_account_and_admits_the_control(case, mode):
    async def body(sm):
        async with sm() as db:
            b, c = _sid(), _sid()
            await _player(db, b)
            await _player(db, c)
            bt, ct = await _session(db, b), await _session(db, c)
            await db.commit()
        await _ban(sm, b)

        def call(sid, token):
            return lambda db: main.set_allow_spectators(
                main.AllowSpectatorsBody(steam_id=sid, allow=False),
                _req("/api/v1/settings/allow-spectators", token), db=db)
        await _expect_refused_no_row(sm, call(b, bt), (401, "session_required"))
        async with sm() as db:
            ans = await call(c, ct)(db)
        assert ans == {"status": "ok", "allow_spectators": False}, ans
    _with_sm(case, body, mode)


def test_t2_ban_class_refuses_the_banned_account_and_admits_the_control(case, mode):
    async def body(sm):
        async with sm() as db:
            b, c = _sid(), _sid()
            await _player(db, b)
            await _player(db, c)
            await db.commit()
        await _ban(sm, b)

        def call(sid):
            return lambda db: _call(main.set_player_card_tier, steam_id=sid, card_name="Leech",
                                    filter="all", tier="S", sig=_sig(f"card-tier:{sid}:Leech:all:S"), db=db)
        await _expect_refused_no_row(sm, call(b), (409, "Banned: "))
        async with sm() as db:
            ans = await call(c)(db)
        assert ans["status"] == "ok" and ans["tier"] == "S", ans
    _with_sm(case, body, mode)


def test_t2_admin_class_refuses_a_banned_admin_and_admits_the_control(case, mode, capsys):
    """S7 (BAN-R10): _is_admin refuses an actively banned admin, so the ban
    route (and every route on _require_admin or an inline _is_admin) refuses
    it; the control admin bans."""
    async def body(sm):
        async with sm() as db:
            ba, ca, t1, t2 = _sid(), _sid(), _sid(), _sid()
            for s in (ba, ca, t1, t2):
                await _player(db, s)
            for s in (ba, ca):
                await lh._insert(db, "admin_users", {"steam_id": s})
            await db.commit()
        await _ban(sm, ba)
        capsys.readouterr()

        def call(admin, target):
            return lambda db: main.admin_ban(
                main._AdminBanReq(admin_steam_id=admin, target_steam_id=target, reason="bs",
                                  hmac_signature=_admin_sig(admin, "ban", target)),
                _slot=None, db=db)
        await _expect_refused_no_row(sm, call(ba, t1), (403, "Not an admin"))
        assert "[BAN-GATE] refused route=" in capsys.readouterr().out
        async with sm() as db:
            ans = await call(ca, t2)(db)
        assert ans["status"] == "banned", ans
    _with_sm(case, body, mode)


# -- S2: the exits, and the mutant without banned_ok ------------------------

def test_s2_an_exit_admits_a_banned_account_and_without_banned_ok_refuses_it(case, soft, monkeypatch):
    async def body(sm):
        async with sm() as db:
            b = _sid()
            await _player(db, b)
            await db.commit()
        await _ban(sm, b)

        def leave(db):
            return main.queue_leave(_req("/api/v1/queue/leave"), steam_id=b, db=db)
        async with sm() as db:
            ans = await leave(db)
        assert ans["status"] == "left", ans
        real = main._check_steam_session

        async def without_banned_ok(request, steam_id, db, *, banned_ok=False):
            return await real(request, steam_id, db)
        monkeypatch.setattr(main, "_check_steam_session", without_banned_ok)
        async with sm() as db:
            got = await _refused(leave(db))
        assert got[0] == 409 and got[1].startswith("Banned: "), got
    _with_sm(case, body, "soft")


def test_s2_mutant_the_soft_check_without_its_ban_read_admits_the_banned_account(case, soft, monkeypatch):
    """T3's SOFT mutant: the soft-fail path without the ban read admits the
    banned account, so the soft-mode T2 case fails on it."""
    async def body(sm):
        (b, bt), _ = await _hide_gold_world(sm)
        await _ban(sm, b)

        async def never(db, steam_id):
            return None
        monkeypatch.setattr(main, "_is_banned", never)
        async with sm() as db:
            got = await _refused(_hide_gold(b, bt)(db))
        assert got == ("admitted", {"status": "set", "hide_gold": True}), got
    _with_sm(case, body, "soft")


# -- T4: an ended timed ban admits again -------------------------------------

def test_t4_a_timed_ban_whose_end_has_passed_admits_again(case, mode):
    async def body(sm):
        (b, _bt), _ = await _hide_gold_world(sm)
        await _ban(sm, b)
        async with sm() as db:
            moved = (await db.execute(text(
                "UPDATE player_bans SET expires_at = NOW() - INTERVAL '1 minute',"
                " banned_at = NOW() - INTERVAL '2 hours'"
                " WHERE steam_id = :s AND unbanned_at IS NULL RETURNING id"), {"s": b})).scalars().all()
            assert len(moved) == 1, moved
            assert await main._is_banned(db, b) is None
            fresh = await _session(db, b)        # sign-in admits an account whose ban ended
            await db.commit()
        async with sm() as db:
            ans = await _hide_gold(b, fresh)(db)
        assert ans == {"status": "set", "hide_gold": True}, ans
        async with sm() as db:
            ans = await _call(main.set_player_card_tier, steam_id=b, card_name="Leech", filter="all",
                              tier="A", sig=_sig(f"card-tier:{b}:Leech:all:A"), db=db)
        assert ans["status"] == "ok", ans
    _with_sm(case, body, mode)


# -- T5: the reports ----------------------------------------------------------

def _report(p1, p2, reporter, ranked):
    return main.MatchReport(
        player1=main.PlayerMatchData(steam_id=p1, display_name="p1"),
        player2=main.PlayerMatchData(steam_id=p2, display_name="p2"),
        p1_rounds_won=3, p2_rounds_won=1, is_ranked=ranked, reported_by_steam_id=reporter,
        photon_room_id="bs_room_" + uuid.uuid4().hex[:8])


@pytest.mark.parametrize("ranked", [False, True])
def test_t5_a_1v1_report_naming_a_banned_player_is_refused(case, soft, monkeypatch, ranked):
    """BAN-R5: the report that named a banned opponent used to be recorded as
    casual; it is refused, and nothing is written (no match, rating, gold,
    XP, win or loss)."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")
    async def body(sm):
        async with sm() as db:
            rep, opp = _sid(), _sid()
            await _player(db, rep)
            await _player(db, opp)
            tok = await _session(db, rep)
            await db.commit()
        await _ban(sm, opp)
        lo, hi = sorted([rep, opp])
        await _expect_refused_no_row(
            sm, lambda db: main.submit_match(_report(lo, hi, rep, ranked), _req("/api/v1/matches", tok), db=db),
            (409, "Banned: participant"))
    _with_sm(case, body, "soft")


def test_t5_a_reporter_under_a_ban_gets_its_own_reason_and_writes_nothing(case, soft, monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")
    async def body(sm):
        async with sm() as db:
            rep, opp = _sid(), _sid()
            await _player(db, rep)
            await _player(db, opp)
            await db.commit()
        await _ban(sm, rep)
        lo, hi = sorted([rep, opp])
        await _expect_refused_no_row(
            sm, lambda db: main.submit_match(_report(lo, hi, rep, False), _req("/api/v1/matches"), db=db),
            (409, "Banned: ban-sweep"))
    _with_sm(case, body, "soft")


def test_t5_a_casual_dc_naming_a_banned_leaver_is_refused_and_counts_nothing(case, soft):
    async def body(sm):
        async with sm() as db:
            rep, lv = _sid(), _sid()
            await _player(db, rep)
            await _player(db, lv)
            await db.commit()
        await _ban(sm, lv)
        await _expect_refused_no_row(
            sm, lambda db: _call(main.report_casual_dc, request=_req("/api/v1/casual-dc"),
                                 reporter_steam_id=rep, leaver_steam_id=lv,
                                 room_id="bs_room_" + uuid.uuid4().hex[:8], db=db),
            (409, "Banned: participant"))
    _with_sm(case, body, "soft")


def test_t5_the_any_gate_names_the_actors_own_reason_and_hides_anothers(case):
    async def body(sm):
        async with sm() as db:
            a, o = _sid(), _sid()
            await _player(db, a)
            await _player(db, o)
            await db.commit()
        await _ban(sm, o)
        async with sm() as db:
            got = await _refused(main._ban_gate_any_or_raise(db, a, [a, o]))
            assert got == (409, "Banned: participant"), got
            got = await _refused(main._ban_gate_any_or_raise(db, o, [a, o]))
            assert got == (409, "Banned: ban-sweep"), got
            got = await _refused(main._ban_gate_any_or_raise(db, a, [a]))
            assert got == ("admitted", None), got
    _with_sm(case, body)


# -- T5: the void closure and the others' release ----------------------------

async def _lease(db, pid, mode, group):
    await db.execute(text(
        "INSERT INTO queue_leases (player_id, mode, group_id, generation, expires_at)"
        " VALUES (:p, :m, :g, :gen, NOW() + INTERVAL '2 minutes')"),
        {"p": pid, "m": mode, "g": group, "gen": uuid.uuid4()})


async def _void_world(sm):
    """The account x in an active 1v1 series (partner r), a public 2v2
    series (t1, t2, t3) and an active FFA lobby (f1, f2), each other member
    holding its queue row and live seat lease."""
    async with sm() as db:
        sids = {k: _sid() for k in ("x", "r", "t1", "t2", "t3", "f1", "f2")}
        pids = {k: await _player(db, s) for k, s in sids.items()}
        rs, ts, fl = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        await lh._insert(db, "ranked_series", {"id": rs, "player1_id": pids["x"],
                                               "player2_id": pids["r"], "status": "active"})
        for a, b in (("x", "r"), ("r", "x")):
            await lh._insert(db, "ranked_queue", {"player_id": pids[a], "status": "matched",
                                                  "matched_with": pids[b]})
        await _lease(db, pids["r"], "ranked", None)
        await lh._insert(db, "team_series", {"id": ts, "t1a_id": pids["x"], "t1b_id": pids["t1"],
                                             "t2a_id": pids["t2"], "t2b_id": pids["t3"], "status": "active"})
        for k in ("t1", "t2", "t3"):
            await lh._insert(db, "team_queue", {"player_id": pids[k], "status": "matched", "series_id": ts})
            await _lease(db, pids[k], "team", ts)
        await lh._insert(db, "ffa_lobbies", {"id": fl, "status": "active", "games_played": 0,
                                             "member_ids": [pids["x"], pids["f1"], pids["f2"]],
                                             "host_player_id": pids["f1"]})
        for k in ("f1", "f2"):
            await lh._insert(db, "ffa_queue", {"player_id": pids[k], "status": "matched", "series_id": fl})
            await _lease(db, pids[k], "ffa", fl)
        await db.commit()
    return sids, pids, {"ranked": rs, "team": ts, "ffa": fl}


async def _void_observe(sm, sids, pids, ids):
    async with sm() as db:
        st = {
            "ranked": tuple((await db.execute(text(
                "SELECT status, invalidation_reason FROM ranked_series WHERE id = :i"),
                {"i": ids["ranked"]})).first()),
            "team": tuple((await db.execute(text(
                "SELECT status, invalidation_reason FROM team_series WHERE id = :i"),
                {"i": ids["team"]})).first()),
            "ffa": tuple((await db.execute(text(
                "SELECT status, invalidation_reason FROM ffa_lobbies WHERE id = :i"),
                {"i": ids["ffa"]})).first()),
        }
        others = [k for k in pids if k != "x"]
        leases = {k: await main._lease_live_mode(db, pids[k]) for k in others}
        blocked = {k: [t for t in ("ranked_queue", "team_queue", "ovt_queue", "ffa_queue")
                       if await main._locked_in_other_queue(db, pids[k], t) is not None]
                   for k in others}
        actions = (await db.execute(text(
            "SELECT action FROM admin_actions WHERE target_steam_id = :t"), {"t": sids["x"]})).scalars().all()
        return st, leases, blocked, sorted(actions)


def test_t5_a_ban_voids_every_open_record_and_frees_the_others_at_once(case):
    async def body(sm):
        sids, pids, ids = await _void_world(sm)
        await _ban(sm, sids["x"])
        st, leases, blocked, actions = await _void_observe(sm, sids, pids, ids)
        assert st == {"ranked": ("abandoned", "member_banned"),
                      "team": ("cancelled", "member_banned"),
                      "ffa": ("canceled", "member_banned")}, st
        assert leases == {k: None for k in leases}, leases
        assert blocked == {k: [] for k in blocked}, blocked
        assert actions == ["ban"], actions          # one record for the one action
        async with sm() as db:
            rows = (await db.execute(text(
                "SELECT 'team' AS q, player_id, status, series_id FROM team_queue WHERE player_id = ANY(:p)"
                " UNION ALL SELECT 'ffa', player_id, status, series_id FROM ffa_queue WHERE player_id = ANY(:p)"
                " UNION ALL SELECT 'ranked', player_id, status, NULL FROM ranked_queue WHERE player_id = ANY(:p)"),
                {"p": list(pids.values())})).all()
        kept = sorted((q, s, sid) for q, _p, s, sid in rows)
        # the public 2v2 group and the FFA members go back to searching; the
        # 1v1 partner's matched row and the account's own rows are gone
        assert kept == sorted([("team", "searching", None)] * 3 + [("ffa", "searching", None)] * 2), kept
    _with_sm(case, body)


def test_t5_mutant_without_the_void_the_others_stay_held(case, monkeypatch):
    async def body(sm):
        async def nothing(db, pid, found):
            return []
        monkeypatch.setattr(main, "_ban_void_apply", nothing)
        sids, pids, ids = await _void_world(sm)
        await _ban(sm, sids["x"])
        st, leases, blocked, _ = await _void_observe(sm, sids, pids, ids)
        assert st["ranked"][0] == "active" and st["team"][0] == "active", st
        assert any(v is not None for v in leases.values()), leases
    _with_sm(case, body)


# -- T5 / S5: the gift receiver ----------------------------------------------

def test_t5_an_artist_gift_to_a_banned_receiver_is_refused(case, soft, monkeypatch):
    async def body(sm):
        async with sm() as db:
            artist, rb, rc = _sid(), _sid(), _sid()
            for s in (artist, rb, rc):
                await _player(db, s)
            tok = await _session(db, artist)
            sku = "bs_gift_" + uuid.uuid4().hex[:8]
            await lh._insert(db, "shop_items", {"sku": sku, "name": "gift", "price": 0,
                                                "artist_steam_id": artist})
            await db.commit()
        await _ban(sm, rb)

        async def is_artist(db, steam_id):
            return steam_id == artist
        monkeypatch.setattr(main, "_is_artist", is_artist)

        def gift(target):
            return lambda db: _call(main.artist_gift, request=_req("/api/v1/artist/gift", tok),
                                    steam_id=artist, sku=sku, target_steam_id=target,
                                    sig=_sig(f"artist:{artist}:gift:{sku}:{target}"), db=db)
        await _expect_refused_no_row(sm, gift(rb), (409, "Banned: participant"))
        async with sm() as db:
            ans = await gift(rc)(db)
        assert ans["status"] == "gifted", ans
    _with_sm(case, body, "soft")


# -- T6: the refusal line -----------------------------------------------------

def test_t6_the_line_names_the_route_template_and_no_account_id(case, soft, capsys):
    async def body(sm):
        (b, bt), _ = await _hide_gold_world(sm)
        await _ban(sm, b)
        capsys.readouterr()
        async with sm() as db:
            got = await _refused(_hide_gold(b, bt)(db))
        assert got[0] == 409, got
        lines = [ln for ln in capsys.readouterr().out.splitlines() if "[BAN-GATE]" in ln]
        assert lines == ["[BAN-GATE] refused route=/api/v1/players/{steam_id}/hide-gold"], lines
        # a handler called with no request takes the template the middleware
        # stored for the request in flight
        token = main._ban_gate_scope.set({"route": types.SimpleNamespace(
            path="/api/v1/players/{steam_id}/card-tiers")})
        try:
            async with sm() as db:
                got = await _refused(_call(main.set_player_card_tier, steam_id=b, card_name="Leech",
                                           filter="all", tier="S", sig=_sig(f"card-tier:{b}:Leech:all:S"),
                                           db=db))
        finally:
            main._ban_gate_scope.reset(token)
        assert got[0] == 409, got
        lines = [ln for ln in capsys.readouterr().out.splitlines() if "[BAN-GATE]" in ln]
        assert lines == ["[BAN-GATE] refused route=/api/v1/players/{steam_id}/card-tiers"], lines
        assert not any(ID_RUN.search(ln) for ln in lines), lines
    _with_sm(case, body, "soft")


def test_t6_one_helper_writes_the_line():
    with open(main.__file__, encoding="utf-8") as fh:
        src = fh.read()
    assert src.count('"[BAN-GATE]') == 1, "one writer of the line"
    assert inspect.getsource(main._ban_gate_refused).count("[BAN-GATE] refused route=") == 1


def test_t6_mutant_a_line_with_the_account_id_is_caught():
    line = "[BAN-GATE] refused route=/api/v1/players/{steam_id}/hide-gold id=" + _sid()
    assert ID_RUN.search(line)


# -- S10 (BAN-R20): the length branch reads the end by the wall clock --------

async def _s10(sm, end_sql):
    """In ONE transaction: an open ban row whose end is `end_sql`, the wall
    clock run past it when the end is near, then a length change for the
    account. Returns (answer, the moderator log actions written)."""
    target = _sid()
    async with sm() as db:
        admin = await _admin(db)
        await _player(db, target)
        await db.execute(text(
            "INSERT INTO player_bans (id, steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
            " VALUES (:id, :s, 'bs-old', :a, NOW() - INTERVAL '1 hour', " + end_sql + ")"),
            {"id": uuid.uuid4(), "s": target, "a": admin})
        for _ in range(200000):
            if (await db.execute(text(
                    "SELECT clock_timestamp() > expires_at FROM player_bans"
                    " WHERE steam_id = :s AND unbanned_at IS NULL"), {"s": target})).scalar():
                break
            if "1 hour" in end_sql:
                break
        ans = await main._apply_ban_core(db, admin_steam_id=admin, target_steam_id=target,
                                         reason="bs-new", duration_minutes=120, length_sent=True)
        acts = (await db.execute(text(
            "SELECT action FROM admin_actions WHERE target_steam_id = :t"), {"t": target})).scalars().all()
        await db.rollback()
    return ans, sorted(acts)


PLANT_END = "NOW() + INTERVAL '2 milliseconds'"   # ahead of NOW(), behind the wall clock
CONTROL_END = "NOW() + INTERVAL '1 hour'"


def test_s10_a_ban_ended_by_the_wall_clock_takes_the_full_path(case):
    ans, acts = _with_sm(case, lambda sm: _s10(sm, PLANT_END))
    assert ans["status"] == "already_banned", ans          # the repeated ban's answer
    assert acts == ["ban_repeat"], acts                   # one record, once


def test_s10_control_an_active_ban_takes_the_length_change(case):
    ans, acts = _with_sm(case, lambda sm: _s10(sm, CONTROL_END))
    assert ans["status"] == "length_changed", ans
    assert acts == ["ban_length"], acts


def test_s10_mutant_without_the_wall_clock_comparison_the_plant_takes_the_early_return(case, monkeypatch):
    async def always_active(db, ban_id):
        return True
    monkeypatch.setattr(main, "_ban_active_by_wall_clock", always_active)
    ans, acts = _with_sm(case, lambda sm: _s10(sm, PLANT_END))
    assert ans["status"] == "length_changed" and acts == ["ban_length"], (ans, acts)
