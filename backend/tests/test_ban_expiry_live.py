"""B4 / B1 / B3 server half, driven against a real PostgreSQL: the tests
T1, T3, T4, T5 (the live answers), T6, T7 and T8 of the ban-expiry order.

One case schema is built for the module by the ladder harness's procedure
(test_title_ladder_hooks_live._build: every migration's DDL replayed, the ORM,
the widening pass), sealed, and dropped under its census at the end. T8 runs
inside the build, before the seal: migration 417 is taken back to the state
before it, then applied through psql the way the migrate verb applies it (the
file on stdin, ON_ERROR_STOP), twice, then its rollback, then once more.

    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    LADDER_TEST_PG_OPTOUT=1   waives the live cases deliberately (else they FAIL)
    BAN_TEST_PSQL / CF_PSQL   the psql client (else PATH, else C:/pg16)

Every ban is placed against synthetic ids below the first individual-account
SteamID64, so none can name a real account. Nothing sleeps: an ended ban is a
row whose expires_at is already behind the database's clock.

Run as a script (BAN_EXPIRY_MUTANT=definition) this module is T7's definition
mutant: models.player_ban_active_sql loses its expiry clause before main is
imported, and T1's same-row transition is run at every site in the parent's
case schema.
"""
import ast
import asyncio
import contextlib
import hashlib
import hmac
import inspect
import io
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
import types
import uuid
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
SQL_DIR = os.path.normpath(os.path.join(HERE, "..", "sql"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MUTANT = os.environ.get("BAN_EXPIRY_MUTANT", "")
if MUTANT == "definition":
    import models as _mutant_models

    def _definition_without_expiry(alias, at=None):
        if at is None:
            return "(%s.unbanned_at IS NULL)" % alias
        return "(%s.banned_at <= %s AND (%s.unbanned_at IS NULL OR %s.unbanned_at > %s))" % (
            alias, at, alias, alias, at)
    _mutant_models.player_ban_active_sql = _definition_without_expiry

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.encoders import jsonable_encoder  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

import database  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402
import tournaments  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402

M417 = os.path.join(SQL_DIR, "417_player_bans_expires_at.sql")
R417 = os.path.join(SQL_DIR, "rollback_417_player_bans_expires_at.sql")
INDEX = "player_bans_one_open_per_key"
INTERNAL_KEY = "ban-expiry-internal-key"
# the definition mutant's child process writes into the parent's case schema,
# so its ids start where the parent's never reach
_IDS = itertools.count(500001 if MUTANT else 1)


def _sid():
    """A fresh synthetic SteamID64-shaped key (17 digits, numeric for 319's
    CHECK, below 76561197960265728)."""
    return "76561190417%06d" % next(_IDS)


def _run(coro):
    return asyncio.run(coro)


# -- the case ---------------------------------------------------------------

def _psql_client():
    for var in ("BAN_TEST_PSQL", "CF_PSQL"):
        named = os.environ.get(var)
        if named and (os.path.isfile(named) or shutil.which(named)):
            return named
    found = shutil.which("psql")
    if found:
        return found
    fallback = "C:/pg16/pgsql/bin/psql.exe"
    return fallback if os.path.isfile(fallback) else None


def _psql_apply(schema, path):
    """The file on psql's stdin with ON_ERROR_STOP, bound to the case schema
    by the startup packet's search path. Returns (exit code, stderr tail)."""
    psql = _psql_client()
    if psql is None:
        return (None, "no psql client found (set BAN_TEST_PSQL or put psql on PATH)")
    u = urlparse(lh.DSN)
    env = dict(os.environ, PGOPTIONS="-c search_path=%s" % schema)
    if u.password:
        env["PGPASSWORD"] = u.password
    args = [psql, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-h", u.hostname or "localhost",
            "-p", str(u.port or 5432), "-d", u.path.lstrip("/")]
    if u.username:
        args += ["-U", u.username]
    with open(path, "rb") as fh:
        p = subprocess.run(args, stdin=fh, env=env, capture_output=True, timeout=120)
    return (p.returncode, p.stderr.decode("utf-8", "replace")[-400:])


async def _fingerprint(conn):
    col = await conn.fetchrow(
        "SELECT a.attnum, format_type(a.atttypid, a.atttypmod) AS t FROM pg_attribute a"
        " WHERE a.attrelid = to_regclass('player_bans') AND a.attname = 'expires_at'"
        " AND NOT a.attisdropped")
    idx = await conn.fetchrow(
        "SELECT i.indexrelid::oid::bigint AS oid, pg_get_indexdef(i.indexrelid) AS def,"
        " i.indisunique AS u, i.indisvalid AS v FROM pg_index i"
        " WHERE i.indexrelid = to_regclass($1)", INDEX)
    return (tuple(col) if col else None, tuple(idx) if idx else None)


T8 = {}


async def _t8_inside_the_build(conn, schema):
    """T8, before the seal: the state before 417, then 417, 417, its rollback
    and 417 again through psql, with the catalog fingerprint after each."""
    await conn.execute("DROP INDEX IF EXISTS " + INDEX)
    await conn.execute("ALTER TABLE player_bans DROP COLUMN IF EXISTS expires_at")
    T8["pre"] = await _fingerprint(conn)
    T8["runs"] = []
    for path in (M417, M417, R417, M417):
        rc, err = _psql_apply(schema, path)
        T8["runs"].append((os.path.basename(path), rc, err, await _fingerprint(conn)))
        if rc != 0:
            break


@pytest.fixture(scope="module")
def case():
    """The module's sealed case schema (its name); dropped under the census."""
    lh._require_live_pg()
    built = {}

    async def build():
        c = harness.CaseSchema(lh.DSN, "ban_expiry")
        await c.__aenter__()
        try:
            await lh._build(c, extra_ddl=_t8_inside_the_build)
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


def _with_sm(schema, body):
    async def go():
        engine = harness.bound_engine(lh.DSN, schema)
        try:
            return await body(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()
    return _run(go())


# -- seeding ----------------------------------------------------------------

async def _player(db, sid, **extra):
    pid = uuid.uuid4()
    values = {"id": pid, "steam_id": sid, "display_name": "bx-" + sid[-4:]}
    values.update(extra)
    await lh._insert(db, "players", values)
    return pid


async def _admin(db):
    sid = _sid()
    await lh._insert(db, "admin_users", {"steam_id": sid})
    return sid


async def _ban_row(db, sid, admin, minutes):
    """One OPEN ban row: minutes None = no end (a row as written before migration
    418, which this case schema does not carry: T8 rebuilt 417 without it),
    < 0 = an end already passed."""
    end = "NULL" if minutes is None else "NOW() + make_interval(mins => CAST(:m AS integer))"
    params = {"id": uuid.uuid4(), "s": sid, "a": admin}
    if minutes is not None:
        params["m"] = minutes
    await db.execute(text(
        "INSERT INTO player_bans (id, steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
        " VALUES (:id, :s, 'ban-test', :a, NOW() - INTERVAL '1 hour', " + end + ")"), params)
    return params["id"]


async def _rows(db, sid):
    return (await db.execute(text(
        "SELECT id, unbanned_at, unbanned_by_steam_id, expires_at,"
        " (" + models.player_ban_active_sql("player_bans") + ") AS active"
        " FROM player_bans WHERE steam_id = :s ORDER BY banned_at, id"), {"s": sid})).mappings().all()


@pytest.fixture
def admin_open(monkeypatch):
    """The admin routes' HMAC check passes (it is tested on its own elsewhere);
    the internal feed's key is a test value."""
    async def _ok(*a, **k):
        return None
    monkeypatch.setattr(main, "_require_admin", _ok)
    monkeypatch.setenv("API_SECRET_KEY", INTERNAL_KEY)
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)


async def _admin_ban(sm, admin, target, **fields):
    req = main._AdminBanReq(admin_steam_id=admin, target_steam_id=target, reason="ban-test", **fields)
    async with sm() as db:
        return await main.admin_ban(req, _slot=None, db=db)


# -- T1: one ban row whose end moves from the future to the past ------------
#
# F5 (fix 1): every site observes the SAME row twice -- active while its end
# is ahead of the database's clock, then inactive once that end is moved
# behind it -- so an answer cached per account, or a site that reads a second
# row, cannot pass. Each observer returns the site's raw verdict (True = the
# site treats the account as under an active ban) and lets every exception
# it does not name propagate: the refusal each one names is the site's ban
# answer, and its admission is named just as exactly.

class SiteAnswerUnexpected(AssertionError):
    """A site answered neither its named refusal nor its named admission."""


def _banned_409(e):
    return isinstance(e, HTTPException) and e.status_code == 409 and str(e.detail).startswith("Banned")


async def _obs_sign_in(sm, sid, pid):
    """Refusal: 409 Banned. Admission: a session token (unverified: no web
    API key in the test). Anything else propagates."""
    async with sm() as db:
        try:
            ans = await main.steam_auth(main.SteamAuthRequest(steam_id=sid, ticket_hex="00"), db=db)
        except HTTPException as e:
            if _banned_409(e):
                return True
            raise
        finally:
            await db.rollback()
    if sorted(ans) == ["expires_in", "session_token", "verified"] and ans["verified"] is False:
        return False
    raise SiteAnswerUnexpected(("sign_in", sorted(ans)))


async def _obs_queue_gate(sm, sid, pid):
    """Refusal: 409 Banned. Admission: the gate returns None."""
    async with sm() as db:
        try:
            ans = await main._enrollment_identity_gate(db, sid)
        except HTTPException as e:
            if _banned_409(e):
                return True
            raise
        finally:
            await db.rollback()
    if ans is None:
        return False
    raise SiteAnswerUnexpected(("shared_queue_gate", ans))


async def _obs_scan(sm, sid, pid):
    """The ranked candidate scan restricted to the subject: [] (left out)
    or exactly [the subject]."""
    async with sm() as db:
        try:
            await db.execute(text("UPDATE ranked_queue SET last_polled = clock_timestamp()"
                                  " WHERE player_id = :p"), {"p": pid})
            rows = (await db.execute(text(main._RANKED_CANDIDATE_SQL), {
                "pid": uuid.uuid4(), "rmin": 1400.0, "rmax": 1600.0, "my_uncapped": False,
                "my_rating": 1500.0, "service_ids": sorted(main.SPECTATE_BROADCAST_STEAM_IDS),
                "only": pid})).mappings().all()
        finally:
            await db.rollback()
    ids = [r["player_id"] for r in rows]
    if ids in ([], [pid]):
        return ids == []
    raise SiteAnswerUnexpected(("scan_ranked", len(ids)))


async def _obs_tournament(sm, sid, pid):
    async with sm() as db:
        try:
            ans = await tournaments._player_id_banned(db, pid)
        finally:
            await db.rollback()
    if isinstance(ans, bool):
        return ans
    raise SiteAnswerUnexpected(("tournament_gate", ans))


async def _obs_tournament_entrants(sm, sid, pid):
    async with sm() as db:
        try:
            n = (await db.execute(text(
                "SELECT count(*) FROM (SELECT CAST(:pid AS uuid) AS player_id,"
                " FALSE AS is_speculative) ts WHERE " + tournaments._ELIGIBLE_ENTRANT_SQL),
                {"pid": pid})).scalar()
        finally:
            await db.rollback()
    if n in (0, 1):
        return n == 0
    raise SiteAnswerUnexpected(("tournament_entrants", n))


async def _obs_card(sm, sid, pid):
    async with sm() as db:
        try:
            n = (await db.execute(text(
                "SELECT count(*) FROM players p WHERE p.steam_id = :s AND "
                + main._PC_NOT_BANNED_SQL.format(a="p")), {"s": sid})).scalar()
        finally:
            await db.rollback()
    if n in (0, 1):
        return n == 0
    raise SiteAnswerUnexpected(("card_gate", n))


async def _obs_chat(sm, sid, pid):
    """The chat helper swallows its own failure into False; its log line is
    how that failure shows, so a printed check error fails the observer."""
    import contextlib
    import io
    saved = database.async_session
    database.async_session = sm
    log = io.StringIO()
    try:
        with contextlib.redirect_stdout(log):
            ans = await main._is_banned_via_session(sid)
    finally:
        database.async_session = saved
    if "[BAN] check error" in log.getvalue():
        raise SiteAnswerUnexpected(("chat", log.getvalue()[-300:]))
    if isinstance(ans, bool):
        return ans
    raise SiteAnswerUnexpected(("chat", ans))


async def _obs_bets(sm, sid, pid):
    """Refusal: 409 Banned. Admission: the next gate after the ban check,
    404 "Series not found" (the series id is a fresh uuid). Anything else
    propagates."""
    saved = (main._check_steam_session, main.MATCH_HMAC_SECRET)

    from soft_check_standin import SoftCheckStandIn
    _session_ok = SoftCheckStandIn()   # admits every caller; records keywords (M3)
    main._check_steam_session = _session_ok
    main.MATCH_HMAC_SECRET = "ban-expiry-bets"
    series = str(uuid.uuid4())
    sig = hmac.new(b"ban-expiry-bets", ("bet:%s:%s:%s:1" % (sid, series, sid)).encode(),
                   hashlib.sha256).hexdigest()
    try:
        async with sm() as db:
            try:
                ans = await main.place_bet(steam_id=sid, series_id=series, bet_on_steam_id=sid, amount=1,
                                           sig=sig, db=db, request=None)
            except HTTPException as e:
                if _banned_409(e):
                    return True
                if e.status_code == 404 and e.detail == "Series not found":
                    return False
                raise
            finally:
                await db.rollback()
        raise SiteAnswerUnexpected(("bets", ans))
    finally:
        main._check_steam_session, main.MATCH_HMAC_SECRET = saved


async def _obs_mod_check(sm, sid, pid):
    async with sm() as db:
        try:
            ans = await main.check_player_registered(sid, db=db)
        finally:
            await db.rollback()
    if isinstance(ans.get("banned"), bool):
        return ans["banned"]
    raise SiteAnswerUnexpected(("mod_check", sorted(ans)))


async def _obs_admin_list(sm, sid, pid):
    """The banned-users list searched by the subject's id: the whole answer
    is that one row or nothing, and its total agrees."""
    saved = main._require_admin

    async def _ok(*a, **k):
        return None
    main._require_admin = _ok
    try:
        async with sm() as db:
            try:
                ans = await main.admin_list_bans(admin_steam_id="x", hmac_signature=None, search=sid,
                                                 limit=None, offset=0, db=db)
            finally:
                await db.rollback()
    finally:
        main._require_admin = saved
    ids = [b["steam_id"] for b in ans["bans"]]
    if ids in ([], [sid]) and ans["total"] == len(ids):
        return ids == [sid]
    raise SiteAnswerUnexpected(("admin_list", len(ids), ans["total"]))


async def _obs_recent_bans(sm, sid, pid):
    """The bot's feed is every active ban (it has no per-account filter):
    the subject is in the whole answer or not, and the answer holds each
    account at most once."""
    saved = os.environ.get("API_SECRET_KEY")
    os.environ["API_SECRET_KEY"] = INTERNAL_KEY
    try:
        async with sm() as db:
            try:
                ans = await main.get_recent_bans(since_id=None, limit=200, x_internal_key=INTERNAL_KEY, db=db)
            finally:
                await db.rollback()
    finally:
        if saved is None:
            os.environ.pop("API_SECRET_KEY", None)
        else:
            os.environ["API_SECRET_KEY"] = saved
    ids = [b["steam_id"] for b in ans["bans"]]
    if len(ids) == len(set(ids)) and len(ids) < 200:
        return sid in ids
    raise SiteAnswerUnexpected(("recent_bans_feed", len(ids), len(set(ids))))


async def _obs_h2h_is_banned(sm, sid, pid):
    async with sm() as db:
        try:
            ans = (await main._h2h_profile_block(db, pid)).is_banned
        finally:
            await db.rollback()
    if isinstance(ans, bool):
        return ans
    raise SiteAnswerUnexpected(("h2h_is_banned", ans))


OBSERVERS = [
    ("sign_in", _obs_sign_in), ("shared_queue_gate", _obs_queue_gate), ("scan_ranked", _obs_scan),
    ("tournament_gate", _obs_tournament), ("tournament_entrants", _obs_tournament_entrants),
    ("card_gate", _obs_card), ("chat", _obs_chat), ("bets", _obs_bets), ("mod_check", _obs_mod_check),
    ("admin_list", _obs_admin_list), ("recent_bans_feed", _obs_recent_bans),
    ("h2h_is_banned", _obs_h2h_is_banned),
]
OBSERVER = dict(OBSERVERS)


async def _t1_subject(sm):
    """One account with ONE open timed ban whose end is an hour ahead, and a
    searching queue row for the scan. Returns (steam id, player id, ban id)."""
    async with sm() as db:
        admin = await _admin(db)
        sid = _sid()
        pid = await _player(db, sid)
        ban = await _ban_row(db, sid, admin, 60)
        await lh._insert(db, "ranked_queue", {
            "player_id": pid, "steam_id": sid, "display_name": "bx-q", "rating": 1500.0,
            "status": "searching", "last_polled": None, "joined_at": None})
        await db.commit()
    return sid, pid, ban


async def _end_moves_behind(sm, ban):
    """The same row's end moves from the future to this statement's instant
    (clock_timestamp): behind the clock of every later transaction, and
    after every snapshot already taken, as a real expiry is. Nothing else
    about the row changes."""
    async with sm() as db:
        n = (await db.execute(text(
            "UPDATE player_bans SET expires_at = clock_timestamp()"
            " WHERE id = :id AND unbanned_at IS NULL AND expires_at > NOW()"), {"id": ban})).rowcount
        await db.commit()
    assert n == 1, "the ban row's end did not move"


async def _t1_observe(sm, fn):
    sid, pid, ban = await _t1_subject(sm)
    before = await fn(sm, sid, pid)
    await _end_moves_behind(sm, ban)
    after = await fn(sm, sid, pid)
    return before, after


@pytest.mark.parametrize("site", [name for name, _ in OBSERVERS])
def test_t1_one_ban_row_is_active_until_its_end_moves_behind_the_clock(case, site, monkeypatch):
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)
    got = _with_sm(case, lambda sm: _t1_observe(sm, OBSERVER[site]))
    assert got == (True, False), (site, "running ban not active" if not got[0] else "ended ban still active")


# Control for the observers (F5 d): each one reads only its named refusal and
# its named admission; an exception it does not name, a non-ban HTTP refusal
# and an answer of another shape all fail it. No database: the site is
# replaced by a plant and the session holds nothing.
class _Planted(Exception):
    """An exception no observer names."""


class _NoSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def rollback(self):
        return None

    async def execute(self, *a, **k):
        raise _Planted("execute")


# observer -> (module, attribute) of the site it calls; None: the site is a
# statement the observer executes itself (the session's execute is the plant)
OBSERVED_SITE = {
    "sign_in": (main, "steam_auth"), "shared_queue_gate": (main, "_enrollment_identity_gate"),
    "scan_ranked": None, "tournament_gate": (tournaments, "_player_id_banned"),
    "tournament_entrants": None, "card_gate": None, "chat": (main, "_is_banned_via_session"),
    "bets": (main, "place_bet"), "mod_check": (main, "check_player_registered"),
    "admin_list": (main, "admin_list_bans"), "recent_bans_feed": (main, "get_recent_bans"),
    "h2h_is_banned": (main, "_h2h_profile_block"),
}
# the observers that name an HTTP refusal, and an answer each must refuse to read
NAMED_REFUSAL = ("sign_in", "shared_queue_gate", "bets")
UNREADABLE = {
    "sign_in": {"session_token": "t"}, "shared_queue_gate": "admitted", "tournament_gate": None,
    "chat": None, "mod_check": {"registered": True},
    "admin_list": {"bans": [{"steam_id": "x"}], "total": 1},
    "recent_bans_feed": {"bans": [{"steam_id": "x"}, {"steam_id": "x"}]},
    "h2h_is_banned": types.SimpleNamespace(is_banned=None),
}


def _plant(monkeypatch, site, behaviour):
    if OBSERVED_SITE[site] is None:
        return
    mod, attr = OBSERVED_SITE[site]

    async def planted(*a, **k):
        if isinstance(behaviour, BaseException):
            raise behaviour
        return behaviour
    monkeypatch.setattr(mod, attr, planted)


@pytest.mark.parametrize("site", [name for name, _ in OBSERVERS])
def test_t1_control_an_observer_reads_only_what_it_names(site, monkeypatch):
    assert sorted(OBSERVED_SITE) == sorted(OBSERVER)
    sid = _sid()
    _plant(monkeypatch, site, _Planted(site))
    with pytest.raises(_Planted):
        _run(OBSERVER[site](_NoSession, sid, uuid.uuid4()))
    if site in NAMED_REFUSAL:
        _plant(monkeypatch, site, HTTPException(status_code=403, detail="Forbidden"))
        with pytest.raises(HTTPException):
            _run(OBSERVER[site](_NoSession, sid, uuid.uuid4()))
        _plant(monkeypatch, site, HTTPException(status_code=409, detail="Banned from the mod"))
        assert _run(OBSERVER[site](_NoSession, sid, uuid.uuid4())) is True
    if site in UNREADABLE:
        _plant(monkeypatch, site, UNREADABLE[site])
        with pytest.raises(SiteAnswerUnexpected):
            _run(OBSERVER[site](_NoSession, sid, uuid.uuid4()))


def test_t7_the_definition_without_its_expiry_clause_fails_t1_at_every_site(case):
    """The mutant (a subprocess, so every constant is built from it) runs
    T1's same-row transition at every site and still answers the row as
    active after its end moved: the positive fact that names the defect the
    expiry clause prevents."""
    env = dict(os.environ, BAN_EXPIRY_MUTANT="definition", BAN_EXPIRY_SCHEMA=case,
               PYTHONDONTWRITEBYTECODE="1")
    env.pop("STEAM_WEB_API_KEY", None)
    p = subprocess.run([sys.executable, os.path.abspath(__file__)], env=env, cwd=HERE,
                       capture_output=True, text=True, timeout=600)
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith("T1-MUTANT ")]
    assert p.returncode == 0 and len(lines) == 1, (p.returncode, p.stdout[-800:], p.stderr[-1500:])
    out = json.loads(lines[0][len("T1-MUTANT "):])
    assert out["definition"] == "(pb.unbanned_at IS NULL)" and "expires_at" not in out["marker"], out
    assert out["results"] == {name: [True, True] for name in OBSERVER}, out["results"]


# -- T3: a second ban after the end; two bans at once -------------------------

def test_t3_a_second_ban_after_the_end_closes_the_first(case, admin_open):
    async def body(sm):
        async with sm() as db:
            admin = await _admin(db)
            target = _sid()
            await _player(db, target)
            await db.commit()
        first = await _admin_ban(sm, admin, target, duration_minutes=1)
        assert first["status"] == "banned" and first["seconds_left"] == 60, first
        async with sm() as db:     # the minute passes: the end moves behind the clock
            await db.execute(text(
                "UPDATE player_bans SET expires_at = NOW() - INTERVAL '1 second',"
                " banned_at = NOW() - INTERVAL '2 minutes' WHERE steam_id = :s"), {"s": target})
            await db.commit()
        async with sm() as db:
            assert await main._is_banned(db, target) is None
        second = await _admin_ban(sm, admin, target)
        async with sm() as db:
            rows = await _rows(db, target)
            audit = (await db.execute(text(
                "SELECT details FROM admin_actions WHERE target_steam_id = :s AND action = 'ban'"),
                {"s": target})).scalars().all()
        return first, second, rows, audit
    first, second, rows, audit = _with_sm(case, body)
    # the cap ruling: a ban without a length ends at its start plus the maximum
    assert second["status"] == "banned" and second["seconds_left"] == main.BAN_MAX_HOURS * 3600, second
    assert len(rows) == 2, rows
    closed, open_ = rows
    assert closed["unbanned_by_steam_id"] == main.BAN_CLOSED_BY_EXPIRY == "system:expired"
    assert closed["unbanned_at"] == closed["expires_at"] and not closed["active"]
    assert open_["unbanned_at"] is None and open_["active"]
    assert main._ban_end_iso(open_["expires_at"]) == second["expires_at"], (open_, second)
    assert [d.get("closed_ended_ban_ids") for d in map(_json, audit)] in (
        [None, [str(closed["id"])]], [[str(closed["id"])], None]), audit


def _json(v):
    return v if isinstance(v, dict) else json.loads(v)


def test_t3_two_bans_at_once_leave_one_active_row(case, admin_open):
    async def body(sm):
        async with sm() as db:
            a1, a2 = await _admin(db), await _admin(db)
            target = _sid()
            await _player(db, target)
            await db.commit()
        res = await asyncio.gather(_admin_ban(sm, a1, target), _admin_ban(sm, a2, target))
        async with sm() as db:
            rows = await _rows(db, target)
        # and the database itself refuses a second OPEN row of one key, across
        # two connections, while the first is uncommitted
        other = _sid()
        async with sm() as d1, sm() as d2:
            await _ban_row(d1, other, a1, None)
            racing = asyncio.ensure_future(_ban_row(d2, other, a2, None))
            await asyncio.sleep(0.5)
            assert not racing.done(), "the second insert did not wait on the first"
            await d1.commit()
            with pytest.raises(IntegrityError) as refused:
                await racing
            await d2.rollback()
        return res, rows, str(refused.value)
    res, rows, refused = _with_sm(case, body)
    assert sorted(r["status"] for r in res) == ["already_banned", "banned"], res
    assert [r["active"] for r in rows] == [True], rows
    assert INDEX in refused, refused


def _mutated(fn, transform, extra=None):
    """fn's source with `transform` applied to its AST, decorators dropped,
    compiled into a copy of main's namespace (plus `extra`)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    node = tree.body[0]
    node.decorator_list = []
    transform(node)
    ns = dict(vars(main))
    ns.update(extra or {})
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 "<mutant %s>" % fn.__name__, "exec"), ns)
    return ns[node.name]


def _replace_source(fn, old, new, extra=None):
    src = textwrap.dedent(inspect.getsource(fn))
    assert src.count(old) == 1, (fn.__name__, old, src.count(old))
    tree = ast.parse(src.replace(old, new))
    node = tree.body[0]
    node.decorator_list = []
    ns = dict(vars(main))
    ns.update(extra or {})
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<mutant %s>" % fn.__name__, "exec"), ns)
    return ns[node.name]


def _replace_source_all(fn, pairs, extra=None):
    """_replace_source with several (old, new) pairs, each occurring once."""
    src = textwrap.dedent(inspect.getsource(fn))
    for old, new in pairs:
        assert src.count(old) == 1, (fn.__name__, old, src.count(old))
        src = src.replace(old, new)
    node = ast.parse(src).body[0]
    node.decorator_list = []
    ns = dict(vars(main))
    ns.update(extra or {})
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<mutant %s>" % fn.__name__, "exec"), ns)
    return ns[node.name]


def test_t7_the_writer_without_its_close_is_refused_by_the_index(case, admin_open):
    """Mutant: _apply_ban_core with the close of the ended row dropped. The
    next ban's insert is then refused by player_bans_one_open_per_key: the
    ended row was left open, and T3's two-row history cannot be written."""
    def drop_close(node):
        hits = [n for n in ast.walk(node) if isinstance(n, ast.Assign)
                and [ast.unparse(t) for t in n.targets] == ["_closed"]]
        assert len(hits) == 1
        hits[0].value = ast.List(elts=[], ctx=ast.Load())
    mutant = _mutated(main._apply_ban_core, drop_close)

    async def body(sm):
        async with sm() as db:
            admin = await _admin(db)
            target = _sid()
            await _player(db, target)
            await _ban_row(db, target, admin, -1)          # ended, still open
            await db.commit()
        async with sm() as db:
            with pytest.raises(IntegrityError) as refused:
                await mutant(db, admin_steam_id=admin, target_steam_id=target, reason="x")
                await db.commit()
            await db.rollback()
        async with sm() as db:
            rows = await _rows(db, target)
        return str(refused.value), rows
    refused, rows = _with_sm(case, body)
    assert INDEX in refused, refused
    assert len(rows) == 1 and rows[0]["unbanned_at"] is None and not rows[0]["active"], rows


# -- T4: a length change on an active ban ------------------------------------

def test_t4_a_length_change_sets_the_end_and_touches_nothing_else(case, admin_open):
    async def body(sm):
        async with sm() as db:
            admin = await _admin(db)
            target = _sid()
            pid = await _player(db, target)
            await db.commit()
        banned = await _admin_ban(sm, admin, target)
        async with sm() as db:   # rows written AFTER the ban, which a length change must leave
            await lh._insert(db, "steam_sessions", {"steam_id": target, "token_hash": uuid.uuid4().hex,
                                                    "verified": True, "issued_at": None, "expires_at": None})
            await lh._insert(db, "ranked_queue", {"player_id": pid, "steam_id": target, "display_name": "bx",
                                                  "rating": 1500.0, "status": "searching",
                                                  "last_polled": None, "joined_at": None})
            await db.commit()
        timed = await _admin_ban(sm, admin, target, duration_minutes=30)
        async with sm() as db:
            mid = await _rows(db, target)
            db_end = (await db.execute(text(
                "SELECT expires_at FROM player_bans WHERE steam_id = :s"), {"s": target})).scalar()
        back = await _admin_ban(sm, admin, target, duration_minutes=None)
        async with sm() as db:
            end = await _rows(db, target)
            cap = (await db.execute(text(
                "SELECT " + models.ban_cap_sql("banned_at") + " FROM player_bans WHERE steam_id = :s"),
                {"s": target})).scalar()
            audit = (await db.execute(text(
                "SELECT details FROM admin_actions WHERE target_steam_id = :s AND action = 'ban_length'"),
                {"s": target})).scalars().all()
            sessions = (await db.execute(text("SELECT count(*) FROM steam_sessions WHERE steam_id = :s"),
                                         {"s": target})).scalar()
            queued = (await db.execute(text("SELECT count(*) FROM ranked_queue WHERE player_id = :p"),
                                       {"p": pid})).scalar()
        return banned, timed, mid, db_end, back, end, audit, sessions, queued, cap
    banned, timed, mid, db_end, back, end, audit, sessions, queued, cap = _with_sm(case, body)
    # the cap ruling: no length = the start plus the maximum, on a new ban and
    # (explicit null) on a length change alike
    assert banned["status"] == "banned" and banned["expires_at"] == main._ban_end_iso(cap), (banned, cap)
    assert timed["status"] == "length_changed" and timed["reason"] == "ban-test", timed
    assert list(timed) == ["status", "steam_id", "reason", "expires_at", "seconds_left"], timed
    assert 1790 <= timed["seconds_left"] <= 1800, timed
    assert timed["expires_at"] == main._ban_end_iso(db_end), (timed, db_end)
    assert len(mid) == 1 and mid[0]["active"] and mid[0]["expires_at"] == db_end, mid
    assert back["status"] == "length_changed" and back["expires_at"] == main._ban_end_iso(cap), back
    assert main.BAN_MAX_HOURS * 3600 - 120 <= back["seconds_left"] <= main.BAN_MAX_HOURS * 3600, back
    assert len(end) == 1 and end[0]["expires_at"] == cap and end[0]["id"] == mid[0]["id"], end
    trail = sorted((_json(d) for d in audit), key=lambda d: d["new_expires_at"] == banned["expires_at"])
    assert [(d["old_expires_at"], d["new_expires_at"], d["duration_minutes"]) for d in trail] == [
        (banned["expires_at"], timed["expires_at"], 30), (timed["expires_at"], banned["expires_at"], None)], trail
    assert (sessions, queued) == (1, 1), "a length change touched the account's sessions or queue rows"


# -- T5 (live): old clients, and the key orders of every changed answer -----

def _extract_1410(chunk, key):
    """ApiClient.ExtractJsonString at v1.41.0: the quoted value after
    "key":" (or after the first :" for an empty key), escapes skipped."""
    search = ':"' if not key else '"%s":"' % key
    start = chunk.find(search)
    if start < 0:
        return ""
    i, out = start + len(search), []
    while i < len(chunk):
        c = chunk[i]
        if c == "\\" and i + 1 < len(chunk):
            out.append(chunk[i + 1])
            i += 2
            continue
        if c == '"':
            break
        out.append(c)
        i += 1
    return "".join(out)


def _parse_banned_users_1410(body):
    """ApiClient.ParseBannedUsers at v1.41.0: split on "id":", the id up to
    the next quote, six keys read by name."""
    out = []
    for chunk in body.split('"id":"')[1:]:
        q = chunk.find('"')
        if q < 0:
            continue
        entry = {"id": chunk[:q]}
        for k in ("steam_id", "display_name", "reason", "banned_by_steam_id", "banned_at"):
            entry[k] = _extract_1410(chunk, k)
        out.append(entry)
    return out


def _wire(answer):
    return json.dumps(jsonable_encoder(answer), separators=(",", ":"), ensure_ascii=False)


def test_t5_old_clients_and_the_key_order_of_every_changed_answer(case, admin_open):
    async def body(sm):
        async with sm() as db:
            admin = await _admin(db)
            capped, timed, stranger, clean = _sid(), _sid(), _sid(), _sid()
            await _player(db, capped)
            await _player(db, timed)
            await _player(db, clean)
            await db.commit()
        out = {"plain": await _admin_ban(sm, admin, capped)}         # the 1.41.0 request
        out["again"] = await _admin_ban(sm, admin, capped)
        out["timed"] = await _admin_ban(sm, admin, timed, duration_minutes=90)
        async with sm() as db:
            out["rows"] = await _rows(db, capped)
            out["check_banned"] = await main.check_player_registered(timed, db=db)
            out["check_unregistered"] = await main.check_player_registered(stranger, db=db)
            out["check_capped"] = await main.check_player_registered(capped, db=db)
            out["check_clean"] = await main.check_player_registered(clean, db=db)
            out["list"] = await main.admin_list_bans(admin_steam_id=admin, hmac_signature=None, search=timed,
                                                     limit=None, offset=0, db=db)
            out["feed"] = await main.get_recent_bans(since_id=None, limit=200, x_internal_key=INTERNAL_KEY, db=db)
        out["sids"] = (capped, timed)
        return out
    out = _with_sm(case, body)
    capped, timed = out["sids"]
    # the cap ruling: a ban request without the field (the 1.41.0 request)
    # ends at its start plus the maximum, and a repeat answers that end
    plain_end = out["plain"]["expires_at"]
    assert out["plain"] == {"status": "banned", "steam_id": capped, "reason": "ban-test",
                            "expires_at": plain_end, "seconds_left": main.BAN_MAX_HOURS * 3600}, out["plain"]
    assert isinstance(plain_end, str) and plain_end.endswith("Z"), out["plain"]
    assert out["again"]["status"] == "already_banned" and out["again"]["expires_at"] == plain_end
    assert list(out["again"]) == ["status", "reason", "expires_at", "seconds_left"], out["again"]
    assert [main._ban_end_iso(r["expires_at"]) for r in out["rows"]] == [plain_end], out["rows"]
    assert list(out["timed"]) == ["status", "steam_id", "reason", "expires_at", "seconds_left"]
    assert out["timed"]["seconds_left"] == 5400 and out["timed"]["expires_at"].endswith("Z"), out["timed"]
    # /mod/check: JsonUtility reads the five declared fields by name; they keep their order, the two new keys follow
    banned = out["check_banned"]
    assert list(banned) == ["registered", "ranked", "display_name", "banned", "ban_reason",
                            "ban_expires_at", "ban_seconds_left"], banned
    assert banned["banned"] is True and banned["ban_expires_at"] == out["timed"]["expires_at"]
    assert 5390 <= banned["ban_seconds_left"] <= 5400, banned
    unreg = out["check_unregistered"]
    assert unreg == {"registered": False, "ranked": False, "banned": False, "ban_reason": "",
                     "ban_expires_at": None, "ban_seconds_left": None}
    assert list(unreg) == ["registered", "ranked", "banned", "ban_reason", "ban_expires_at", "ban_seconds_left"]
    # banned-users: the row's whole key order, and the 1.41.0 parse is unchanged by the two keys
    listed = out["list"]
    assert list(listed) == ["bans", "total", "limit", "offset"] and len(listed["bans"]) == 1, listed
    row = listed["bans"][0]
    assert list(row) == ["id", "steam_id", "display_name", "reason", "banned_by_steam_id", "banned_at",
                         "expires_at", "seconds_left"], row
    stripped = dict(listed, bans=[{k: v for k, v in r.items() if k not in ("expires_at", "seconds_left")}
                                  for r in listed["bans"]])
    parsed = _parse_banned_users_1410(_wire(listed))
    assert parsed == _parse_banned_users_1410(_wire(stripped)) and parsed[0]["steam_id"] == timed, parsed
    # the bot's feed (every active ban in the schema, unfiltered): every row's
    # key order, expires_at last; one row per account; and this test's two
    # accounts carry their own ends
    feed = out["feed"]["bans"]
    assert feed and [list(b) for b in feed] == [["id", "steam_id", "reason", "banned_by_steam_id",
                                                 "display_name", "banned_at", "expires_at"]] * len(feed), feed
    ends = {b["steam_id"]: b["expires_at"] for b in feed}
    assert len(ends) == len(feed), feed
    assert (ends[capped], ends[timed]) == (plain_end, out["timed"]["expires_at"]), ends
    # ban_seconds_left: an integer for a banned account (a ban without a
    # length included), null for a registered account under no ban
    cap_check = out["check_capped"]
    assert cap_check["banned"] is True and cap_check["ban_expires_at"] == plain_end, cap_check
    left = cap_check["ban_seconds_left"]
    assert isinstance(left, int) and main.BAN_MAX_HOURS * 3600 - 120 <= left <= main.BAN_MAX_HOURS * 3600, cap_check
    clean_check = out["check_clean"]
    assert (clean_check["banned"], clean_check["ban_expires_at"], clean_check["ban_seconds_left"]) == \
        (False, None, None), clean_check
    assert list(clean_check) == list(banned), clean_check


# -- T6 / T7: presence -------------------------------------------------------
#
# F5 (fix 1): every answer is read WHOLE. The world is closed: no other test
# before this section writes a rating row, a 2v2/FFA rating row, a 1v2 match
# or a mod_seen_at stamp, so each list and board holds exactly the world's
# accounts and the expected answer names every row of it.

@pytest.fixture(scope="module")
def presence_world(case):
    """B: banned (no end: a row from before 418) and pinging; C: the control, same stamps; E: an
    ENDED ban, pinging; B2 / C2: banned / control, offline but recent; L:
    banned then lifted by T6. Every one has last_seen and mod_seen_at stamped
    now and a 1v1 rating row; the three pinging ones have presence_seen_at
    re-stamped at every read (_presence_answers), the other three ten
    minutes old, so the marker's 3-minute window decides nothing by timing.
    B, C and E also hold the played-game rows the three other boards need:
    a 2v2 and an FFA rating row each and one 1v2 match between them."""
    async def body(sm):
        out = {}
        async with sm() as db:
            admin = await _admin(db)
            for key, minutes in (("B", None), ("C", False), ("E", -5), ("B2", None), ("C2", False), ("L", None)):
                sid = _sid()
                pid = await _player(db, sid, last_seen=None, presence_seen_at=None, mod_seen_at=None,
                                    appear_offline=False)
                await lh._insert(db, "glicko_ratings", {"player_id": pid, "rating": 1500.0,
                                                        "rating_deviation": 100.0, "volatility": 0.06})
                if minutes is not False:
                    await _ban_row(db, sid, admin, minutes)
                out[key] = (sid, pid)
            for key in ("B2", "C2", "L"):
                await db.execute(text("UPDATE players SET presence_seen_at = NOW() - INTERVAL '10 minutes'"
                                      " WHERE id = :p"), {"p": out[key][1]})
            for key in ("B", "C", "E"):
                await lh._insert(db, "glicko_ratings_2v2", {"player_id": out[key][1], "rating": 1500.0,
                                                            "rating_deviation": 100.0, "volatility": 0.06,
                                                            "completed_series": 1})
                await lh._insert(db, "glicko_ratings_ffa", {"player_id": out[key][1], "rating": 1500.0,
                                                            "rating_deviation": 100.0, "volatility": 0.06,
                                                            "games_played": 1})
            # ended_at takes its column default (now) and invalidated_at stays
            # NULL: lh._insert writes NOW() for a None value
            await lh._insert(db, "ovt_matches", {"solo_id": out["B"][1], "duo_a_id": out["C"][1],
                                                 "duo_b_id": out["E"][1], "winner_side": 1})
            await db.commit()
        out["admin"] = admin
        return out
    return _with_sm(case, body)


class _Map:
    """The presence map holding exactly the given ids, put back after."""

    def __init__(self, sids):
        self.sids = sids

    def __enter__(self):
        self.saved = dict(main._presence_seen)
        main._presence_seen.clear()
        now = time.monotonic()
        for s in self.sids:
            main._presence_seen[s] = now
        return self

    def __exit__(self, *exc):
        main._presence_seen.clear()
        main._presence_seen.update(self.saved)


def _ping_request():
    return types.SimpleNamespace(state=types.SimpleNamespace(), headers={})


THREE_BOARDS = ("ovt_leaderboard", "ffa_leaderboard", "team_leaderboard")


def _board(ans):
    """A board answer whole: every entry's (steam id, is_online)."""
    return sorted((e.steam_id, e.is_online) for e in ans.entries)


async def _presence_answers(sm, w, fns=None):
    f = dict(queue_count=main.queue_count, presence_ping=main.presence_ping,
             presence_online=main.presence_online, get_leaderboard=main.get_leaderboard,
             ovt_leaderboard=main.ovt_leaderboard, ffa_leaderboard=main.ffa_leaderboard,
             team_leaderboard=main.team_leaderboard, h2h=main._h2h_profile_block, marker=main._ONLINE_MARKER_SQL)
    f.update(fns or {})
    async with sm() as db:
        await db.execute(text("UPDATE players SET presence_seen_at = NOW() WHERE id = ANY(:p)"),
                         {"p": [w[k][1] for k in ("B", "C", "E")]})
        await db.commit()
    async with sm() as db:
        out = {"queue_count": (await f["queue_count"](steam_id=None, db=db))["online"]}
    async with sm() as db:
        out["ping"] = (await f["presence_ping"](request=_ping_request(), steam_id=w["C"][0],
                                                 in_match=None, db=db))["online"]
    async with sm() as db:
        po = await f["presence_online"](db=db)
        out["online_count"] = po["online_count"]
        out["online"] = sorted(e["steam_id"] for e in po["online"])
        out["recent"] = sorted(e["steam_id"] for e in po["recent"])
    async with sm() as db:
        lb = await f["get_leaderboard"](limit=500, offset=0, min_matches=0, include_inactive=True, db=db)
        out["board_1v1"] = _board(lb)
    async with sm() as db:
        out["ovt_leaderboard"] = _board(await f["ovt_leaderboard"](limit=200, role="combined",
                                                                   include_inactive=True, db=db))
    async with sm() as db:
        out["ffa_leaderboard"] = _board(await f["ffa_leaderboard"](limit=200, min_games=1, sort_by="rating",
                                                                   include_inactive=True, db=db))
    async with sm() as db:
        out["team_leaderboard"] = _board(await f["team_leaderboard"](limit=200, min_series=0, sort_by="rating",
                                                                     include_inactive=True, db=db))
    async with sm() as db:
        out["h2h"] = {}
        for k in ("B", "C", "E"):
            blk = await f["h2h"](db, w[k][1])
            out["h2h"][w[k][0]] = (blk.is_online, blk.is_banned)
        out["marker"] = dict((await db.execute(text(
            "SELECT p.steam_id, " + f["marker"] + " AS lit FROM players p WHERE p.steam_id = ANY(:s)"),
            {"s": [w[k][0] for k in ("B", "C", "E")]})).all())
    return out


async def _lifted(sm, w):
    async with sm() as db:
        return await main._is_banned(db, w["L"][0]) is None


def _expected(w, lifted):
    """Every answer whole, with B, C and E in the presence map. L is in the
    recent list once its ban is lifted (T6 lifts it)."""
    b, c, e = w["B"][0], w["C"][0], w["E"][0]
    bce = sorted([(b, False), (c, True), (e, True)])
    return {"queue_count": 2, "ping": 2, "online_count": 2, "online": sorted([c, e]),
            "recent": sorted([w["C2"][0]] + ([w["L"][0]] if lifted else [])),
            "board_1v1": sorted(bce + [(w[k][0], False) for k in ("B2", "C2", "L")]),
            "ovt_leaderboard": bce, "ffa_leaderboard": bce, "team_leaderboard": bce,
            "h2h": {b: (False, True), c: (True, False), e: (True, False)},
            "marker": {b: False, c: True, e: True}}


def test_t6_a_banned_account_is_in_no_presence_answer_and_an_ended_ban_shows_again(case, presence_world, admin_open):
    w = presence_world
    with _Map([w[k][0] for k in ("B", "C", "E")]):
        lifted = _with_sm(case, lambda sm: _lifted(sm, w))
        got = _with_sm(case, lambda sm: _presence_answers(sm, w))
    assert lifted is False and got == _expected(w, lifted=False), got

    # lifted: the account shows again by the ordinary rules, with no other step
    async def lift(sm):
        async with sm() as db:
            await main.admin_unban(main._AdminUnbanReq(admin_steam_id=w["admin"], target_steam_id=w["L"][0]),
                                   _slot=None, db=db)
        async with sm() as db:
            return [e["steam_id"] for e in (await main.presence_online(db=db))["online"]]
    with _Map([w["L"][0]]):
        assert _with_sm(case, lift) == [w["L"][0]]


def test_t7_each_presence_answer_without_its_ban_filter_shows_the_banned_account(case, presence_world, admin_open):
    """One mutant per route, each run through its route against T6's world,
    each asserting the defect itself: the banned account B counted, listed or
    marked online. The unmutated routes, read the same way first, are the
    control: they give exactly the expected answers."""
    w = presence_world
    b = w["B"][0]
    marker = main._ONLINE_MARKER_SQL
    cut = marker.index(" AND NOT EXISTS (SELECT 1 FROM player_bans pbo")
    noban = marker[:cut] + ")"
    extra = {"_ONLINE_MARKER_SQL_NOBAN": noban}
    shown = "online = len(await _presence_online_ids_shown(db))"

    def board(fn):
        return _replace_source(fn, "{_ONLINE_MARKER_SQL}", "{_ONLINE_MARKER_SQL_NOBAN}", extra)
    mutants = {
        "queue_count": dict(queue_count=_replace_source(main.queue_count, shown, "online = len(_presence_online_ids())")),
        "presence_ping": dict(presence_ping=_replace_source(main.presence_ping, shown,
                                                            "online = len(_presence_online_ids())")),
        "presence_online:online": dict(presence_online=_replace_source(
            main.presence_online, "online_ids = await _presence_online_ids_shown(db)",
            "online_ids = _presence_online_ids()")),
        "presence_online:recent": dict(presence_online=_replace_source(
            main.presence_online, 'player_ban_active_sql("pb")', '"FALSE"')),
        "board_1v1": dict(get_leaderboard=board(main.get_leaderboard)),
        "ovt_leaderboard": dict(ovt_leaderboard=board(main.ovt_leaderboard)),
        "ffa_leaderboard": dict(ffa_leaderboard=board(main.ffa_leaderboard)),
        "team_leaderboard": dict(team_leaderboard=board(main.team_leaderboard)),
        "h2h": dict(h2h=board(main._h2h_profile_block)),
        "marker": dict(marker=noban),
    }
    with _Map([w[k][0] for k in ("B", "C", "E")]):
        lifted = _with_sm(case, lambda sm: _lifted(sm, w))
        control = _with_sm(case, lambda sm: _presence_answers(sm, w))
    expected = _expected(w, lifted)
    assert control == expected, ("the unmutated routes", control)
    defects = {}
    for name, fns in mutants.items():
        with _Map([w[k][0] for k in ("B", "C", "E")]):
            got = _with_sm(case, lambda sm: _presence_answers(sm, w, fns))
        defects[name] = {
            "queue_count": got["queue_count"] == 3,
            "presence_ping": got["ping"] == 3,
            "presence_online:online": b in got["online"] and got["online_count"] == 3,
            "presence_online:recent": b in got["recent"] and w["B2"][0] in got["recent"],
            "board_1v1": (b, True) in got["board_1v1"],
            "ovt_leaderboard": (b, True) in got["ovt_leaderboard"],
            "ffa_leaderboard": (b, True) in got["ffa_leaderboard"],
            "team_leaderboard": (b, True) in got["team_leaderboard"],
            "h2h": got["h2h"][b] == (True, True),
            "marker": got["marker"][b] is True,
        }[name]
        # the mutant moved its own answer and only that answer
        moved = sorted(k for k in expected if got[k] != expected[k])
        assert moved == MOVES.get(name, [name]), (name, moved)
    assert all(defects.values()), defects


# the answers each T7 mutant moves; a mutant not named moves the answer of its own name
MOVES = {"presence_ping": ["ping"], "presence_online:online": ["online", "online_count"],
         "presence_online:recent": ["recent"]}


# -- F2: the presence ping keeps no ban state of its own ---------------------

def _r1_ping():
    """The r1 build's ping, rebuilt as the control's subject: every ban read
    that works records the ids it found banned, and a failed read answers the
    map's count less that recorded set. Its ban read is whichever one main
    holds at call time, so the driver's swap reaches it too."""
    seen = {"banned": frozenset()}

    async def recording_read(db):
        ids = main._presence_online_ids()
        shown = await main._presence_online_ids_shown(db)
        seen["banned"] = frozenset(ids) - frozenset(shown)
        return shown

    def recorded_fallback():
        return sum(1 for sid in main._presence_online_ids() if sid not in seen["banned"])
    return _replace_source(main.presence_ping, "online = _presence_online_count()", "online = _r1_fallback()",
                           extra={"_r1_fallback": recorded_fallback, "_presence_online_ids_shown": recording_read})


def _f2_sequence(case, w, ping):
    """Four pings by C, the map holding B (banned, no end: a pre-418 row), C, P (one
    timed ban, running) and Q (no ban yet):
      works    the read works;
      failed   P's ONE row has ended (its end moved behind the clock) and the
               ban read fails;
      again    the read works again;
      new      Q is banned now and the read works.
    Returns the four answers whole and the failed ping's printed log."""
    failing = _replace_source(main._presence_online_ids_shown, '"SELECT pb.steam_id FROM player_bans pb"',
                              '"SELECT pb.no_such_column FROM player_bans pb"')

    async def body(sm):
        async with sm() as db:
            admin = await _admin(db)
            p_sid, q_sid = _sid(), _sid()
            await _player(db, p_sid)
            await _player(db, q_sid)
            p_ban = await _ban_row(db, p_sid, admin, 60)
            await db.commit()

        async def one():
            async with sm() as db:
                return await ping(request=_ping_request(), steam_id=w["C"][0], in_match=None, db=db)
        out = {}
        with _Map([w["B"][0], w["C"][0], p_sid, q_sid]):
            out["works"] = await one()
            await _end_moves_behind(sm, p_ban)
            saved = main._presence_online_ids_shown
            main._presence_online_ids_shown = failing
            log = io.StringIO()
            try:
                with contextlib.redirect_stdout(log):
                    out["failed"] = await one()
            finally:
                main._presence_online_ids_shown = saved
            out["log"] = log.getvalue()
            out["again"] = await one()
            async with sm() as db:
                await _ban_row(db, q_sid, admin, None)
                await db.commit()
            out["new"] = await one()
        return out
    return _with_sm(case, body)


def test_f2_the_ping_answers_200_through_a_failed_ban_read_and_filters_again_after(case, presence_world,
                                                                                    admin_open):
    """The ping is every client's heartbeat. When its ban read fails it
    answers 200 with the presence map's plain count (not ban-filtered for
    that one answer) and no exception text; the next ping whose read works is
    filtered again, with the ended ban counted at once (the same row, no
    state in between) and a ban made since excluded at once."""
    out = _f2_sequence(case, presence_world, main.presence_ping)
    rev = main._alerts_rev
    assert "no_such_column" not in json.dumps(out["failed"]), out["failed"]
    assert "[PRESENCE] online count ban read failed" in out["log"], out["log"][-400:]
    # B, C, P, Q in the map: B and P banned (2); P's row ended and the read
    # failed: the plain count (4); the read works: only B (3); Q banned (2)
    assert {k: out[k] for k in ("works", "failed", "again", "new")} == {
        "works": {"online": 2, "alerts_rev": rev}, "failed": {"online": 4, "alerts_rev": rev},
        "again": {"online": 3, "alerts_rev": rev}, "new": {"online": 2, "alerts_rev": rev}}, out


def test_f2_control_the_r1_recorded_set_fails_the_sequence(case, presence_world, admin_open):
    """Control: the same four pings through the r1 build's ping. Its failed
    read still subtracts the set the working read recorded, so the ended ban
    stays excluded: 2 where the test above requires 4, and only there."""
    out = _f2_sequence(case, presence_world, _r1_ping())
    rev = main._alerts_rev
    assert "[PRESENCE] online count ban read failed" in out["log"], out["log"][-400:]
    assert {k: out[k] for k in ("works", "failed", "again", "new")} == {
        "works": {"online": 2, "alerts_rev": rev}, "failed": {"online": 2, "alerts_rev": rev},
        "again": {"online": 3, "alerts_rev": rev}, "new": {"online": 2, "alerts_rev": rev}}, out


# -- T8: the migration, through psql, twice; the model's column -------------

def test_t8_417_applies_twice_through_psql_and_rolls_back(case):
    assert T8.get("pre") == (None, None), T8
    runs = T8["runs"]
    assert [(f, rc) for f, rc, _, _ in runs] == [
        ("417_player_bans_expires_at.sql", 0), ("417_player_bans_expires_at.sql", 0),
        ("rollback_417_player_bans_expires_at.sql", 0), ("417_player_bans_expires_at.sql", 0)], runs
    first, second, back, again = (fp for _, _, _, fp in runs)
    col, idx = first
    assert col[1] == "timestamp with time zone", first
    # pg_get_indexdef qualifies the table only when the search path cannot see it
    assert idx[2] is True and idx[3] is True, first
    assert idx[1] in ("CREATE UNIQUE INDEX %s ON %s USING btree (steam_id) WHERE (unbanned_at IS NULL)"
                      % (INDEX, table) for table in ("player_bans", case + ".player_bans")), first
    assert second == first, ("the second run changed the catalog", first, second)
    assert back == (None, None), back
    assert again[0][1] == "timestamp with time zone" and again[1][2] is True, again


def test_t8_the_model_reads_and_writes_the_column(case):
    from datetime import datetime, timedelta, timezone
    end = datetime(2031, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    async def body(sm):
        async with sm() as db:
            admin = await _admin(db)
            sid = _sid()
            db.add(models.PlayerBan(steam_id=sid, reason="orm", banned_by_steam_id=admin, expires_at=end))
            await db.commit()
        async with sm() as db:
            got = (await db.execute(select(models.PlayerBan.expires_at)
                                    .where(models.PlayerBan.steam_id == sid))).scalars().all()
            raw = (await db.execute(text("SELECT expires_at FROM player_bans WHERE steam_id = :s"),
                                    {"s": sid})).scalar()
        return got, raw
    got, raw = _with_sm(case, body)
    assert got == [end] and raw == end and raw - end == timedelta(0), (got, raw)


# -- F3: a ban that ends frees the account in the card pool at once ---------
#
# Fix 1, ruling (b). The pool is a snapshot; _pc_snapshot_due gains the
# reason 'ban_ended' and the readers of pc_pool_members apply the definition
# at read time. Every case runs through the real janitor pass
# (_pc_snapshot_janitor_step) against this module's case schema, and every
# transition is ONE ban row whose end moves (F5's form).
#
# Pool players need a SteamID64 the pool's id rule admits. They take ids from
# the reveal harness's block (discord_collection_harness.STEAM_BASE: account
# type 0, never an individual account; test_cf_fixture_steam_ids.py proves
# the decode), admitted only while that harness's predicate is injected for
# the test. No test before this section seeds a pool player, so the pool is
# exactly this section's accounts. Ratings rise from test to test, so each
# test's subject is pool rank 1 once it is a member, and its witness is rank
# 1 while the subject is out.

import discord_collection_harness as H  # noqa: E402

_POOL_N = itertools.count(1)
_POOL_BASE = itertools.count(0)
_SNAP_LINE = re.compile(r"\[PC-SNAPSHOT\] id=\d+ members=\d+ reason=(\w+)")


@pytest.fixture
def pool_env(case, monkeypatch, admin_open):
    H.inject_pool_predicate(monkeypatch)
    return case


class _TopRng:
    """Every slot rolls legendary and takes the band's first member."""

    def random(self):
        return 0.0

    def randrange(self, n):
        return 0


async def _pool_player(db, rating):
    n = 417000 + next(_POOL_N)
    sid, did = H.steam_of(n), H.discord_of(n)
    pid = await _player(db, sid, mod_seen_at=None, discord_id=did)
    await lh._insert(db, "glicko_ratings", {"player_id": pid, "rating": float(rating),
                                            "peak_rating": float(rating), "rating_deviation": 100.0,
                                            "volatility": 0.06})
    return types.SimpleNamespace(sid=sid, pid=pid, did=did)


async def _ban_at(db, sid, admin, *, began="NOW() - INTERVAL '1 hour'", minutes=60):
    """One OPEN ban row of `sid`, begun at `began` (SQL), ending in `minutes`
    (None = no end, a row as written before migration 418; negative = already
    behind the clock)."""
    end = "NULL" if minutes is None else "NOW() + make_interval(mins => CAST(:m AS integer))"
    params = {"id": uuid.uuid4(), "s": sid, "a": admin}
    if minutes is not None:
        params["m"] = minutes
    await db.execute(text(
        "INSERT INTO player_bans (id, steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
        " VALUES (:id, :s, 'ban-test', :a, " + began + ", " + end + ")"), params)
    return params["id"]


async def _pool_world(sm, *, banned=True):
    """A subject (banned, ending in an hour, begun before the baseline when
    `banned`) above a witness, then the baseline snapshot."""
    base = 3000 + 100 * next(_POOL_BASE)
    async with sm() as db:
        admin = await _admin(db)
        subject = await _pool_player(db, base + 50)
        witness = await _pool_player(db, base + 10)
        subject.ban = await _ban_at(db, subject.sid, admin) if banned else None
        await db.commit()
    subject.admin = admin
    snap = await _take(sm, "ban-test baseline")
    return subject, witness, snap


async def _take(sm, reason):
    async with sm() as db:
        out = await main._pc_take_snapshot(db, reason=reason)
        await db.commit()
    return out["snapshot_id"]


async def _janitor_pass(sm):
    """One real janitor step on the case schema. Returns the reasons of the
    snapshots it took (printed by _pc_take_snapshot) and the whole log."""
    saved = database.async_session
    database.async_session = sm
    log = io.StringIO()
    try:
        with contextlib.redirect_stdout(log):
            await main._pc_snapshot_janitor_step()
    finally:
        database.async_session = saved
    return _SNAP_LINE.findall(log.getvalue()), log.getvalue()


async def _snapshot_mark(sm):
    """The latest snapshot id. Retention (snapshot_keep) deletes the oldest
    snapshot whenever one is taken, so the COUNT stays put; the snapshots
    taken since a mark are the ids above it."""
    async with sm() as db:
        return (await db.execute(text("SELECT COALESCE(MAX(id), 0) FROM pc_pool_snapshots"))).scalar()


async def _taken_since(sm, mark):
    async with sm() as db:
        return (await db.execute(text("SELECT count(*) FROM pc_pool_snapshots WHERE id > :m"),
                                 {"m": mark})).scalar()


async def _members(sm, snap):
    async with sm() as db:
        return [tuple(r) for r in (await db.execute(text(
            "SELECT player_id, pool_rank FROM pc_pool_members WHERE snapshot_id = :s ORDER BY pool_rank"),
            {"s": snap})).all()]


async def _pool_card(sm, who):
    """The bot's /card: the raw answer, or 'not_in_pool' for its named 404."""
    async with sm() as db:
        try:
            return await main.internal_pc_card(discord_id=who.did, x_internal_key=INTERNAL_KEY, db=db)
        except HTTPException as e:
            if e.status_code == 404 and e.detail == {"error": "not_in_pool"}:
                return "not_in_pool"
            raise
        finally:
            await db.rollback()


async def _pool_preview(sm, who, fn=None):
    """The preview routes' one membership read (_pc_preview_read): its spec,
    or 'not_in_pool' -- the face route answers 404 not_in_pool exactly when
    the read returns None."""
    async with sm() as db:
        try:
            read = await (fn or main._pc_preview_read)(db, str(who.pid), "en", None)
        finally:
            await db.rollback()
    return "not_in_pool" if read is None else read[2]


async def _pool_roll(sm, owner):
    """A pack roll from the latest snapshot: the subjects of its prints, or
    the reason it refused."""
    async with sm() as db:
        try:
            snap = (await db.execute(text(
                "SELECT id FROM pc_pool_snapshots ORDER BY id DESC LIMIT 1"))).scalar_one()
            prints, reason = await main._pc_roll_prints(db, snap, owner.pid, rng=_TopRng())
        finally:
            await db.rollback()
    return reason if prints is None else [p["player_id"] for p in prints]


async def _pool_answers(sm, subject, witness):
    return {"card": await _pool_card(sm, subject), "preview": await _pool_preview(sm, subject),
            "roll": await _pool_roll(sm, witness)}


def _out(witness):
    n = int(main._pc.PC_ECONOMY["prints_per_pack"])
    return {"card": "not_in_pool", "preview": "not_in_pool", "roll": [str(witness.pid)] * n}


def _in(answers, subject):
    """The positive fact of membership, read from the whole answers: rank 1,
    legendary, on the card and on the preview; every print of the roll."""
    card, spec, roll = answers["card"], answers["preview"], answers["roll"]
    n = int(main._pc.PC_ECONOMY["prints_per_pack"])
    return (isinstance(card, dict) and card["player_ref"] == str(subject.pid) and card["pool_rank"] == 1
            and card["rarity"] == "legendary" and isinstance(spec, dict) and spec["pool_rank"] == 1
            and spec["band"] == "legendary" and roll == [str(subject.pid)] * n)


async def _end_now(sm, subject, how):
    """The subject's ONE ban row ends: its expiry moves behind the clock, or
    the admin route lifts it."""
    if how == "expiry":
        await _end_moves_behind(sm, subject.ban)
    else:
        async with sm() as db:
            ans = await main.admin_unban(main._AdminUnbanReq(admin_steam_id=subject.admin,
                                                             target_steam_id=subject.sid), _slot=None, db=db)
        assert ans["rows"] == 1, ans


def _end_frees(case, how):
    async def body(sm):
        subject, witness, snap = await _pool_world(sm)
        members = await _members(sm, snap)
        banned = await _pool_answers(sm, subject, witness)
        await _end_now(sm, subject, how)
        waiting = await _pool_answers(sm, subject, witness)
        n0 = await _snapshot_mark(sm)
        first, log1 = await _janitor_pass(sm)
        freed = await _pool_answers(sm, subject, witness)
        second, log2 = await _janitor_pass(sm)
        return dict(subject=subject, witness=witness, members=members, banned=banned, waiting=waiting,
                    first=first, second=second, n0=n0, n=await _taken_since(sm, n0), freed=freed,
                    log=log1 + log2)
    r = _with_sm(case, body)
    # R-a: under an active ban at the baseline, the subject takes no pool rank; the ranks are 1..n
    assert r["subject"].pid not in [p for p, _ in r["members"]], r["members"]
    assert [k for _, k in r["members"]] == list(range(1, len(r["members"]) + 1)), r["members"]
    assert r["banned"] == _out(r["witness"]), r["banned"]
    # between the end and the next pass the account still answers 404 not_in_pool
    assert r["waiting"] == _out(r["witness"]), r["waiting"]
    # one pass: one ordinary snapshot, reason ban_ended; the account is a member at rank 1
    assert r["first"] == ["ban_ended"] and r["n"] == 1, (r["first"], r["n0"], r["n"])
    assert _in(r["freed"], r["subject"]), r["freed"]
    # once: the next pass takes none
    assert r["second"] == [], r["second"]
    assert "ban_ended read failed" not in r["log"], r["log"][-400:]


def test_f3_an_expiry_frees_the_account_at_the_next_pass(pool_env):
    _end_frees(pool_env, "expiry")


def test_f3_a_lift_frees_the_account_at_the_next_pass(pool_env):
    _end_frees(pool_env, "lift")


async def _not_due_case(sm, name):
    """Each case ends with one janitor pass that must take no snapshot."""
    if name == "no ban change":
        subject, witness, _ = await _pool_world(sm)
    elif name == "a ban begun and ended after the snapshot":
        subject, witness, _ = await _pool_world(sm, banned=False)
        async with sm() as db:
            subject.ban = await _ban_at(db, subject.sid, subject.admin, began="NOW()")
            await db.commit()
        await _end_moves_behind(sm, subject.ban)
    elif name == "an end while another ban on the account is active":
        subject, witness, _ = await _pool_world(sm)
        await _end_now(sm, subject, "lift")
        async with sm() as db:
            await _ban_at(db, subject.sid, subject.admin, began="NOW()", minutes=None)
            await db.commit()
    elif name == "the re-ban that closes an expired row":
        subject, witness, _ = await _pool_world(sm, banned=False)
        async with sm() as db:   # expired BEFORE the next snapshot, still open
            subject.ban = await _ban_at(db, subject.sid, subject.admin, began="NOW() - INTERVAL '2 hours'",
                                        minutes=-30)
            await db.commit()
        await _take(sm, "ban-test baseline")
        ans = await _admin_ban(sm, subject.admin, subject.sid)   # closes it (unbanned_at = expires_at), bans anew
        assert ans["status"] == "banned", ans
    elif name == "a ban that ended before the snapshot, still open":
        subject, witness, _ = await _pool_world(sm, banned=False)
        async with sm() as db:
            subject.ban = await _ban_at(db, subject.sid, subject.admin, began="NOW() - INTERVAL '2 hours'",
                                        minutes=-30)
            await db.commit()
        await _take(sm, "ban-test baseline")
    else:
        raise AssertionError(name)
    n0 = await _snapshot_mark(sm)
    reasons, log = await _janitor_pass(sm)
    return reasons, await _taken_since(sm, n0), log


NOT_DUE = ("no ban change", "a ban begun and ended after the snapshot",
           "an end while another ban on the account is active", "the re-ban that closes an expired row",
           "a ban that ended before the snapshot, still open")


@pytest.mark.parametrize("name", NOT_DUE)
def test_f3_nothing_is_due_without_an_end_of_a_ban_the_snapshot_held(pool_env, name):
    reasons, taken, log = _with_sm(pool_env, lambda sm: _not_due_case(sm, name))
    assert (reasons, taken) == ([], 0), (name, reasons, taken, log[-400:])
    assert "ban_ended read failed" not in log, log[-400:]


def test_f3_rule_outranks_ban_ended_when_both_hold(pool_env):
    """Both hold (an older rule on the latest snapshot, and an end since):
    the printed reason is the first in the documented order, 'rule'; and the
    snapshot it takes frees the account too."""
    async def body(sm):
        subject, witness, snap = await _pool_world(sm)
        await _end_now(sm, subject, "expiry")
        async with sm() as db:
            await db.execute(text("UPDATE pc_pool_snapshots SET rule = :r WHERE id = :s"),
                             {"r": int(main._PC_POOL_RULE) - 1, "s": snap})
            await db.commit()
        reasons, _ = await _janitor_pass(sm)
        return reasons, await _pool_answers(sm, subject, witness), subject
    reasons, answers, subject = _with_sm(pool_env, body)
    assert reasons == ["rule"] and _in(answers, subject), (reasons, answers)


def test_f3_a_failed_ban_read_frees_nobody_and_breaks_nothing(pool_env):
    """The ban read fails (a statement the database refuses): the pass takes
    no snapshot, raises nothing and logs the failure; once the read works
    again the next pass frees the account."""
    async def body(sm):
        subject, witness, _ = await _pool_world(sm)
        await _end_now(sm, subject, "expiry")
        good = main._PC_SNAPSHOT_BAN_ENDED_SQL
        main._PC_SNAPSHOT_BAN_ENDED_SQL = "SELECT no_such_column AS ban_ended FROM player_bans"
        try:
            failed = await _janitor_pass(sm)
            during = await _pool_answers(sm, subject, witness)
        finally:
            main._PC_SNAPSHOT_BAN_ENDED_SQL = good
        again, _ = await _janitor_pass(sm)
        return failed, during, again, await _pool_answers(sm, subject, witness), subject, witness
    (reasons, log), during, again, after, subject, witness = _with_sm(pool_env, body)
    assert reasons == [] and "[PC-SNAPSHOT] ban_ended read failed (" in log, log[-600:]
    assert during == _out(witness), during
    assert again == ["ban_ended"] and _in(after, subject), (again, after)


def test_f3_each_mutant_of_the_due_reason_shows_its_defect(pool_env, monkeypatch):
    """Each mutant judged by its positive fact, through the real pass:
      - the reason removed: an end leaves the account out after the pass;
      - the "active at the snapshot's time" half removed: a ban begun and
        ended after the snapshot makes a snapshot due;
      - the earlier-of rule removed (the instant form loses its expiry
        clause): a ban that ended before the snapshot and is still open
        makes a snapshot due -- the re-ban case cannot show this one, since
        the re-ban's close writes unbanned_at = expires_at;
      - the other-ban clause removed: an end while another ban is active
        makes a snapshot due."""
    at = models.player_ban_active_sql("b", "CAST(:last_at AS timestamptz)")
    at_no_expiry = "(b.banned_at <= CAST(:last_at AS timestamptz)" \
                   " AND (b.unbanned_at IS NULL OR b.unbanned_at > CAST(:last_at AS timestamptz)))"
    other = main._PC_SNAPSHOT_BAN_ENDED_SQL[main._PC_SNAPSHOT_BAN_ENDED_SQL.index("AND NOT EXISTS"):
                                            main._PC_SNAPSHOT_BAN_ENDED_SQL.index(") AS ban_ended")]
    assert main._PC_SNAPSHOT_BAN_ENDED_SQL.count(at) == 1 and other.count("b2") >= 2, other
    no_reason = _replace_source(main._pc_snapshot_due, 'return "ban_ended" if ended else None', "return None")
    sql_mutants = {
        "active at the snapshot's time removed": (
            main._PC_SNAPSHOT_BAN_ENDED_SQL.replace(at, "TRUE"), "a ban begun and ended after the snapshot"),
        "earlier-of rule removed": (
            main._PC_SNAPSHOT_BAN_ENDED_SQL.replace(at, at_no_expiry),
            "a ban that ended before the snapshot, still open"),
        "other-ban clause removed": (
            main._PC_SNAPSHOT_BAN_ENDED_SQL.replace(other, ""),
            "an end while another ban on the account is active"),
    }
    out = {}
    with monkeypatch.context() as mp:
        mp.setattr(main, "_pc_snapshot_due", no_reason)
        async def removed(sm):
            subject, witness, _ = await _pool_world(sm)
            await _end_now(sm, subject, "expiry")
            reasons, _ = await _janitor_pass(sm)
            return reasons, await _pool_answers(sm, subject, witness), witness
        reasons, answers, witness = _with_sm(pool_env, removed)
        out["reason removed"] = reasons == [] and answers == _out(witness)
    for name, (sql, case_name) in sql_mutants.items():
        assert sql != main._PC_SNAPSHOT_BAN_ENDED_SQL, name
        with monkeypatch.context() as mp:
            mp.setattr(main, "_PC_SNAPSHOT_BAN_ENDED_SQL", sql)
            reasons, taken, log = _with_sm(pool_env, lambda sm: _not_due_case(sm, case_name))
        out[name] = (reasons == ["ban_ended"] and taken == 1) or (reasons, taken, log[-600:])
    assert out == {k: True for k in ["reason removed"] + list(sql_mutants)}, out


def test_f3_every_read_time_reader_hides_a_member_banned_since_the_snapshot(pool_env, monkeypatch):
    """R-e at read time: a member of the latest snapshot banned after it is
    out of the card, the preview, the roll and the pool summary at once,
    before any pass. Each reader's mutant (its pool word without the ban
    clause) shows the banned account."""
    word = main._PC_POOL_MEMBER_SQL
    clause = " AND NOT EXISTS (SELECT 1 FROM player_bans b WHERE b.steam_id = p.steam_id AND " \
             + models.player_ban_active_sql("b") + ")"
    flat = " ".join(word.split())
    assert flat.count(" ".join(clause.split())) == 1, flat
    noban = re.sub(r"\s+AND NOT EXISTS \(SELECT 1 FROM player_bans b WHERE b\.steam_id = p\.steam_id AND "
                   + re.escape(models.player_ban_active_sql("b")) + r"\)", "", word)
    assert noban != word and "player_bans" not in noban, noban
    extra = {"_PC_POOL_MEMBER_SQL_NOBAN": noban}
    readers = {
        "card": _replace_source(main.internal_pc_card, 'AND """ + _PC_POOL_MEMBER_SQL + """',
                                'AND """ + _PC_POOL_MEMBER_SQL_NOBAN + """', extra),
        "summary": _replace_source(main.pc_pool_summary, 'AND """ + _PC_POOL_MEMBER_SQL + """',
                                   'AND """ + _PC_POOL_MEMBER_SQL_NOBAN + """', extra),
        # the preview is gated twice: the word on its subject read, and the
        # resolve columns' own subject_banned over the same row; its clause
        # removed is both
        "preview": _replace_source_all(main._pc_preview_read, [
            ("+ _PC_POOL_MEMBER_SQL)", "+ _PC_POOL_MEMBER_SQL_NOBAN)"),
            (' or sub["subject_banned"]', "")], extra),
    }
    live_noban = main._PC_LIVE_POOL_CHECK_SQL.replace(word, noban)
    assert live_noban != main._PC_LIVE_POOL_CHECK_SQL

    async def world(sm):
        subject, witness, _ = await _pool_world(sm, banned=False)
        members = await _members(sm, await _take(sm, "ban-test member"))
        async with sm() as db:
            await _ban_at(db, subject.sid, subject.admin, began="NOW()")
            await db.commit()
        return subject, witness, members

    async def summary(sm, fn):
        async with sm() as db:
            try:
                ans = await fn(db=db)
            finally:
                await db.rollback()
        return [t["pool_rank"] for t in ans["top"]]

    async def observe(sm, subject, witness, fns):
        card = fns.get("card", main.internal_pc_card)
        async with sm() as db:
            try:
                c = await card(discord_id=subject.did, x_internal_key=INTERNAL_KEY, db=db)
            except HTTPException as e:
                if not (e.status_code == 404 and e.detail == {"error": "not_in_pool"}):
                    raise
                c = "not_in_pool"
            finally:
                await db.rollback()
        return {"card": c, "preview": await _pool_preview(sm, subject, fns.get("preview")),
                "roll": await _pool_roll(sm, witness),
                "summary": await summary(sm, fns.get("summary", main.pc_pool_summary))}

    async def body(sm):
        subject, witness, members = await world(sm)
        got = {"control": await observe(sm, subject, witness, {})}
        for name, fn in readers.items():
            got[name] = await observe(sm, subject, witness, {name: fn})
        main_live = main._PC_LIVE_POOL_CHECK_SQL
        main._PC_LIVE_POOL_CHECK_SQL = live_noban
        try:
            got["roll"] = await observe(sm, subject, witness, {})
        finally:
            main._PC_LIVE_POOL_CHECK_SQL = main_live
        return subject, witness, members, got
    subject, witness, members, got = _with_sm(pool_env, body)
    assert members[0][0] == subject.pid, members      # a member, rank 1, when the snapshot was taken
    n = int(main._pc.PC_ECONOMY["prints_per_pack"])
    control = got["control"]
    top = int(main._pc.PC_ECONOMY["band_max_rank"]["uncommon"])
    assert control["card"] == "not_in_pool" and control["preview"] == "not_in_pool", control
    # the roll lands on rank 1 (the subject), is refused by the live check and re-rolled
    # onto the same slot until the attempts run out: the pack is refused before any debit
    assert control["roll"] == "pool_changed", control["roll"]
    # the summary's whole top list: every member of the snapshot but the subject (rank 1)
    assert control["summary"] == [k for _, k in members if k != 1 and k <= top], (control["summary"], members)
    shows = {
        "card": isinstance(got["card"]["card"], dict) and got["card"]["card"]["player_ref"] == str(subject.pid),
        "preview": isinstance(got["preview"]["preview"], dict) and got["preview"]["preview"]["pool_rank"] == 1,
        "summary": got["summary"]["summary"] == [k for _, k in members if k <= top],
        "roll": got["roll"]["roll"] == [str(subject.pid)] * n,
    }
    assert shows == {"card": True, "preview": True, "summary": True, "roll": True}, (shows, got)


# -- the definition mutant's driver ------------------------------------------
def _mutant_main():
    schema = os.environ["BAN_EXPIRY_SCHEMA"]

    async def go():
        engine = harness.bound_engine(lh.DSN, schema)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        try:
            out = {}
            for name, fn in OBSERVERS:
                out[name] = list(await _t1_observe(sm, fn))
            return out
        finally:
            await engine.dispose()
    results = _run(go())
    print("T1-MUTANT " + json.dumps({"definition": models.player_ban_active_sql("pb"),
                                     "marker": main._ONLINE_MARKER_SQL, "results": results}))


if __name__ == "__main__" and MUTANT == "definition":
    _mutant_main()
