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
imported, and every T1 observer is run against the parent's subjects.
"""
import ast
import asyncio
import hashlib
import hmac
import inspect
import itertools
import json
import os
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

    def _definition_without_expiry(alias):
        return "(%s.unbanned_at IS NULL)" % alias
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
_IDS = itertools.count(1)


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
    """One OPEN ban row: minutes None = permanent, < 0 = an end already passed."""
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


# -- T1: the gates, with an ended ban and a ban still running ---------------

async def _obs_sign_in(sm, sid, pid):
    async with sm() as db:
        try:
            await main.steam_auth(main.SteamAuthRequest(steam_id=sid, ticket_hex="00"), db=db)
        except HTTPException as e:
            return e.status_code == 409 and str(e.detail).startswith("Banned")
        finally:
            await db.rollback()
    return False


async def _obs_queue_gate(sm, sid, pid):
    async with sm() as db:
        try:
            await main._enrollment_identity_gate(db, sid)
        except HTTPException as e:
            return e.status_code == 409 and str(e.detail).startswith("Banned")
        finally:
            await db.rollback()
    return False


async def _obs_scan(sm, sid, pid):
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
    return pid not in [r["player_id"] for r in rows]


async def _obs_tournament(sm, sid, pid):
    async with sm() as db:
        try:
            return bool(await tournaments._player_id_banned(db, pid))
        finally:
            await db.rollback()


async def _obs_tournament_entrants(sm, sid, pid):
    async with sm() as db:
        try:
            n = (await db.execute(text(
                "SELECT count(*) FROM (SELECT CAST(:pid AS uuid) AS player_id,"
                " FALSE AS is_speculative) ts WHERE " + tournaments._ELIGIBLE_ENTRANT_SQL),
                {"pid": pid})).scalar()
        finally:
            await db.rollback()
    return n == 0


async def _obs_card(sm, sid, pid):
    async with sm() as db:
        try:
            n = (await db.execute(text(
                "SELECT count(*) FROM players p WHERE p.steam_id = :s AND "
                + main._PC_NOT_BANNED_SQL.format(a="p")), {"s": sid})).scalar()
        finally:
            await db.rollback()
    return n == 0


async def _obs_chat(sm, sid, pid):
    saved = database.async_session
    database.async_session = sm
    try:
        return await main._is_banned_via_session(sid)
    finally:
        database.async_session = saved


async def _obs_bets(sm, sid, pid):
    saved = (main._check_steam_session, main.MATCH_HMAC_SECRET)

    async def _session_ok(*a, **k):
        return None
    main._check_steam_session = _session_ok
    main.MATCH_HMAC_SECRET = "ban-expiry-bets"
    series = str(uuid.uuid4())
    sig = hmac.new(b"ban-expiry-bets", ("bet:%s:%s:%s:1" % (sid, series, sid)).encode(),
                   hashlib.sha256).hexdigest()
    try:
        async with sm() as db:
            try:
                await main.place_bet(steam_id=sid, series_id=series, bet_on_steam_id=sid, amount=1,
                                     sig=sig, db=db, request=None)
            except HTTPException as e:
                return e.status_code == 409 and str(e.detail).startswith("Banned")
            except Exception:
                return False        # past the ban gate, refused for another reason
            finally:
                await db.rollback()
        return False
    finally:
        main._check_steam_session, main.MATCH_HMAC_SECRET = saved


async def _obs_mod_check(sm, sid, pid):
    async with sm() as db:
        try:
            return (await main.check_player_registered(sid, db=db))["banned"]
        finally:
            await db.rollback()


async def _obs_admin_list(sm, sid, pid):
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
    return [b["steam_id"] for b in ans["bans"]] == [sid]


async def _obs_recent_bans(sm, sid, pid):
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
    return sid in [b["steam_id"] for b in ans["bans"]]


async def _obs_h2h_is_banned(sm, sid, pid):
    async with sm() as db:
        try:
            return (await main._h2h_profile_block(db, pid)).is_banned
        finally:
            await db.rollback()


OBSERVERS = [
    ("sign_in", _obs_sign_in), ("shared_queue_gate", _obs_queue_gate), ("scan_ranked", _obs_scan),
    ("tournament_gate", _obs_tournament), ("tournament_entrants", _obs_tournament_entrants),
    ("card_gate", _obs_card), ("chat", _obs_chat), ("bets", _obs_bets), ("mod_check", _obs_mod_check),
    ("admin_list", _obs_admin_list), ("recent_bans_feed", _obs_recent_bans),
    ("h2h_is_banned", _obs_h2h_is_banned),
]
OBSERVER = dict(OBSERVERS)


@pytest.fixture(scope="module")
def t1_subjects(case):
    """Two accounts, each with one open timed ban: one whose end is a minute
    behind the database's clock, one whose end is an hour ahead."""
    async def body(sm):
        out = {}
        async with sm() as db:
            admin = await _admin(db)
            for key, minutes in (("past", -1), ("future", 60)):
                sid = _sid()
                pid = await _player(db, sid)
                await _ban_row(db, sid, admin, minutes)
                await lh._insert(db, "ranked_queue", {
                    "player_id": pid, "steam_id": sid, "display_name": "bx-q", "rating": 1500.0,
                    "status": "searching", "last_polled": None, "joined_at": None})
                out[key] = (sid, str(pid))
            await db.commit()
        return out
    return _with_sm(case, body)


@pytest.mark.parametrize("site", [name for name, _ in OBSERVERS])
def test_t1_an_ended_ban_is_not_active_and_a_running_one_is(case, t1_subjects, site, monkeypatch):
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)
    fn = OBSERVER[site]

    async def body(sm):
        return [await fn(sm, sid, uuid.UUID(pid)) for sid, pid in (t1_subjects["past"], t1_subjects["future"])]
    past, future = _with_sm(case, body)
    assert (past, future) == (False, True), (site, "ended ban active" if past else "running ban not active")


def test_t7_the_definition_without_its_expiry_clause_fails_t1_at_every_site(case, t1_subjects):
    """The mutant (a subprocess, so every constant is built from it) answers
    the ENDED ban as active at every T1 site: the positive fact that names
    the defect the expiry clause prevents."""
    env = dict(os.environ, BAN_EXPIRY_MUTANT="definition", BAN_EXPIRY_SCHEMA=case,
               BAN_EXPIRY_SUBJECTS=json.dumps(t1_subjects), PYTHONDONTWRITEBYTECODE="1")
    env.pop("STEAM_WEB_API_KEY", None)
    p = subprocess.run([sys.executable, os.path.abspath(__file__)], env=env, cwd=HERE,
                       capture_output=True, text=True, timeout=600)
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith("T1-MUTANT ")]
    assert p.returncode == 0 and len(lines) == 1, (p.returncode, p.stdout[-800:], p.stderr[-1500:])
    out = json.loads(lines[0][len("T1-MUTANT "):])
    assert out["definition"] == "(pb.unbanned_at IS NULL)" and "expires_at" not in out["marker"], out
    still_active = sorted(name for name, (past, future) in out["results"].items() if past and future)
    assert still_active == sorted(OBSERVER), ("sites the mutant did not break", sorted(
        set(OBSERVER) - set(still_active)), out["results"])


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
    assert second["status"] == "banned" and second["expires_at"] is None, second
    assert len(rows) == 2, rows
    closed, open_ = rows
    assert closed["unbanned_by_steam_id"] == main.BAN_CLOSED_BY_EXPIRY == "system:expired"
    assert closed["unbanned_at"] == closed["expires_at"] and not closed["active"]
    assert open_["unbanned_at"] is None and open_["expires_at"] is None and open_["active"]
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
            audit = (await db.execute(text(
                "SELECT details FROM admin_actions WHERE target_steam_id = :s AND action = 'ban_length'"),
                {"s": target})).scalars().all()
            sessions = (await db.execute(text("SELECT count(*) FROM steam_sessions WHERE steam_id = :s"),
                                         {"s": target})).scalar()
            queued = (await db.execute(text("SELECT count(*) FROM ranked_queue WHERE player_id = :p"),
                                       {"p": pid})).scalar()
        return banned, timed, mid, db_end, back, end, audit, sessions, queued
    banned, timed, mid, db_end, back, end, audit, sessions, queued = _with_sm(case, body)
    assert banned["status"] == "banned" and banned["expires_at"] is None
    assert timed["status"] == "length_changed" and timed["reason"] == "ban-test", timed
    assert list(timed) == ["status", "steam_id", "reason", "expires_at", "seconds_left"], timed
    assert 1790 <= timed["seconds_left"] <= 1800, timed
    assert timed["expires_at"] == main._ban_end_iso(db_end), (timed, db_end)
    assert len(mid) == 1 and mid[0]["active"] and mid[0]["expires_at"] == db_end, mid
    assert back["status"] == "length_changed" and back["expires_at"] is None and back["seconds_left"] is None
    assert len(end) == 1 and end[0]["expires_at"] is None and end[0]["id"] == mid[0]["id"], end
    trail = sorted((_json(d) for d in audit), key=lambda d: d["old_expires_at"] is not None)
    assert [(d["old_expires_at"], d["new_expires_at"], d["duration_minutes"]) for d in trail] == [
        (None, timed["expires_at"], 30), (timed["expires_at"], None, None)], trail
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
            permanent, timed, stranger = _sid(), _sid(), _sid()
            await _player(db, permanent)
            await _player(db, timed)
            await db.commit()
        out = {"plain": await _admin_ban(sm, admin, permanent)}         # the 1.41.0 request
        out["again"] = await _admin_ban(sm, admin, permanent)
        out["timed"] = await _admin_ban(sm, admin, timed, duration_minutes=90)
        async with sm() as db:
            out["rows"] = await _rows(db, permanent)
            out["check_banned"] = await main.check_player_registered(timed, db=db)
            out["check_unregistered"] = await main.check_player_registered(stranger, db=db)
            out["list"] = await main.admin_list_bans(admin_steam_id=admin, hmac_signature=None, search=timed,
                                                     limit=None, offset=0, db=db)
            out["feed"] = await main.get_recent_bans(since_id=None, limit=200, x_internal_key=INTERNAL_KEY, db=db)
        out["sids"] = (permanent, timed)
        return out
    out = _with_sm(case, body)
    permanent, timed = out["sids"]
    # a ban request without the field is permanent, and so stays when repeated
    assert out["plain"] == {"status": "banned", "steam_id": permanent, "reason": "ban-test",
                            "expires_at": None, "seconds_left": None}, out["plain"]
    assert out["again"]["status"] == "already_banned" and out["again"]["expires_at"] is None
    assert list(out["again"]) == ["status", "reason", "expires_at", "seconds_left"], out["again"]
    assert [r["expires_at"] for r in out["rows"]] == [None], out["rows"]
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
    # the bot's feed: expires_at is each row's last key
    feed = [b for b in out["feed"]["bans"] if b["steam_id"] in (permanent, timed)]
    assert [list(b) for b in feed] == [["id", "steam_id", "reason", "banned_by_steam_id", "display_name",
                                        "banned_at", "expires_at"]] * 2, feed
    assert {b["steam_id"]: b["expires_at"] for b in feed} == {permanent: None, timed: out["timed"]["expires_at"]}


# -- T6 / T7: presence -------------------------------------------------------

@pytest.fixture(scope="module")
def presence_world(case):
    """B: banned (permanent) and pinging; C: the control, same stamps; E: an
    ENDED ban, pinging; B2 / C2: banned / control, offline but recent; L:
    banned then lifted by T6. Every one has last_seen, presence_seen_at and
    mod_seen_at stamped now and a 1v1 rating row."""
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


async def _presence_answers(sm, w, fns=None):
    f = dict(queue_count=main.queue_count, presence_ping=main.presence_ping,
             presence_online=main.presence_online, get_leaderboard=main.get_leaderboard,
             h2h=main._h2h_profile_block, marker=main._ONLINE_MARKER_SQL)
    f.update(fns or {})
    sids = [w[k][0] for k in ("B", "C", "E", "B2", "C2")]
    async with sm() as db:
        out = {"queue_count": (await f["queue_count"](steam_id=None, db=db))["online"]}
    async with sm() as db:
        out["ping"] = (await f["presence_ping"](request=_ping_request(), steam_id=w["C"][0],
                                                 in_match=None, db=db))["online"]
    async with sm() as db:
        po = await f["presence_online"](db=db)
        out["online_count"] = po["online_count"]
        out["online"] = sorted(e["steam_id"] for e in po["online"] if e["steam_id"] in sids)
        out["recent"] = sorted(e["steam_id"] for e in po["recent"] if e["steam_id"] in sids)
    async with sm() as db:
        lb = await f["get_leaderboard"](limit=500, offset=0, min_matches=0, include_inactive=True, db=db)
        out["board_1v1"] = {e.steam_id: e.is_online for e in lb.entries if e.steam_id in sids[:3]}
    async with sm() as db:
        out["h2h"] = {}
        for k in ("B", "C", "E"):
            blk = await f["h2h"](db, w[k][1])
            out["h2h"][w[k][0]] = (blk.is_online, blk.is_banned)
        out["marker"] = dict((await db.execute(text(
            "SELECT p.steam_id, " + f["marker"] + " AS lit FROM players p WHERE p.steam_id = ANY(:s)"),
            {"s": sids[:3]})).all())
    return out


def _expected(w):
    b, c, e = w["B"][0], w["C"][0], w["E"][0]
    return {"queue_count": 2, "ping": 2, "online_count": 2, "online": sorted([c, e]),
            "recent": [w["C2"][0]], "board_1v1": {b: False, c: True, e: True},
            "h2h": {b: (False, True), c: (True, False), e: (True, False)},
            "marker": {b: False, c: True, e: True}}


def test_t6_a_banned_account_is_in_no_presence_answer_and_an_ended_ban_shows_again(case, presence_world, admin_open):
    w = presence_world
    with _Map([w[k][0] for k in ("B", "C", "E")]):
        got = _with_sm(case, lambda sm: _presence_answers(sm, w))
    assert got == _expected(w), got
    # the three boards that need played games to list a row read the same marker, mapped as it is answered
    for name in THREE_BOARDS:
        src = inspect.getsource(getattr(main, name))
        assert src.count("{_ONLINE_MARKER_SQL} AS is_online") == 1, name
        assert 'is_online=bool(r["is_online"])' in src, name

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
    """One mutant per route, each run against T6's world, each asserting the
    defect itself: the banned account B counted, listed or marked online."""
    w = presence_world
    b = w["B"][0]
    marker = main._ONLINE_MARKER_SQL
    cut = marker.index(" AND NOT EXISTS (SELECT 1 FROM player_bans pbo")
    noban = marker[:cut] + ")"
    extra = {"_ONLINE_MARKER_SQL_NOBAN": noban}
    shown = "online = len(await _presence_online_ids_shown(db))"
    mutants = {
        "queue_count": dict(queue_count=_replace_source(main.queue_count, shown, "online = len(_presence_online_ids())")),
        "presence_ping": dict(presence_ping=_replace_source(main.presence_ping, shown,
                                                            "online = len(_presence_online_ids())")),
        "presence_online:online": dict(presence_online=_replace_source(
            main.presence_online, "online_ids = await _presence_online_ids_shown(db)",
            "online_ids = _presence_online_ids()")),
        "presence_online:recent": dict(presence_online=_replace_source(
            main.presence_online, 'player_ban_active_sql("pb")', '"FALSE"')),
        "board_1v1": dict(get_leaderboard=_replace_source(
            main.get_leaderboard, "{_ONLINE_MARKER_SQL}", "{_ONLINE_MARKER_SQL_NOBAN}", extra)),
        "h2h": dict(h2h=_replace_source(
            main._h2h_profile_block, "{_ONLINE_MARKER_SQL}", "{_ONLINE_MARKER_SQL_NOBAN}", extra)),
        "marker": dict(marker=noban),
    }
    defects = {}
    for name, fns in mutants.items():
        with _Map([w[k][0] for k in ("B", "C", "E")]):
            got = _with_sm(case, lambda sm: _presence_answers(sm, w, fns))
        defects[name] = {
            "queue_count": got["queue_count"] == 3,
            "presence_ping": got["ping"] == 3,
            "presence_online:online": b in got["online"] and got["online_count"] == 3,
            "presence_online:recent": b in got["recent"] and w["B2"][0] in got["recent"],
            "board_1v1": got["board_1v1"][b] is True,
            "h2h": got["h2h"][b] == (True, True),
            "marker": got["marker"][b] is True,
        }[name]
        assert got != _expected(w), (name, "the mutant left every presence answer as T6 requires")
    assert all(defects.values()), defects
    # the three boards: their mutant loses the shared marker T6 pins, and the
    # ban-less marker it would read marks B online (the "marker" mutant above)
    for name in THREE_BOARDS:
        src = inspect.getsource(getattr(main, name)).replace("{_ONLINE_MARKER_SQL}", "{_ONLINE_MARKER_SQL_NOBAN}")
        assert src.count("{_ONLINE_MARKER_SQL} AS is_online") == 0, name


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


# -- the definition mutant's driver ------------------------------------------

def _mutant_main():
    schema = os.environ["BAN_EXPIRY_SCHEMA"]
    subjects = json.loads(os.environ["BAN_EXPIRY_SUBJECTS"])

    async def go():
        engine = harness.bound_engine(lh.DSN, schema)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        try:
            out = {}
            for name, fn in OBSERVERS:
                out[name] = [await fn(sm, sid, uuid.UUID(pid))
                             for sid, pid in (subjects["past"], subjects["future"])]
            return out
        finally:
            await engine.dispose()
    results = _run(go())
    print("T1-MUTANT " + json.dumps({"definition": models.player_ban_active_sql("pb"),
                                     "marker": main._ONLINE_MARKER_SQL, "results": results}))


if __name__ == "__main__" and MUTANT == "definition":
    _mutant_main()
