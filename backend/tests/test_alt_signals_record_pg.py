"""CHEAT-ALT-1 step 3: the alternate-account recording against a real
PostgreSQL (ruling R1, the notice check of R6, the storage limits of R4).

A verified sign-in commits its own transaction as before; then, with the
signal key loaded, the route runs the recording as a second transaction
inside a guard that lets no Exception out, and returns the answer it built
before. Every live case signs in through the real handler (main.steam_auth,
the Steam call stubbed) and checks the answer against the baseline's shape,
the session row from another connection, and the three tables.

The route's session is a probe (a plain AsyncSession that logs each
statement with the number of commits before it, and raises a planned fault
at the n-th statement after the sign-in's commit, at the recording's commit,
or at its rollback). The case schema carries one fault table and one fault
trigger on each of the three tables: a row (table, SQLSTATE) makes every
insert or update of that table raise that SQLSTATE; the word `sleep` makes
it sleep six seconds instead.

One case schema for the module, built by the ladder harness's procedure
(test_title_ladder_hooks_live._build, the fault objects as its extra DDL),
sealed, and dropped at the end:

    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    LADDER_TEST_PG_OPTOUT=1   waives the live cases deliberately (else they FAIL)

Ids are synthetic (below the first individual-account SteamID64); the
addresses are public resolver service addresses, or private, multicast and
reserved ones.
"""
import asyncio
import builtins
import hashlib
import itertools
import os
import re
import sys
import time
import uuid
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402
from starlette.requests import Request  # noqa: E402

import main  # noqa: E402
import alt_signals as A  # noqa: E402
import conn_ranges  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402

KEY_HEX = "0f1e2d3c4b5a69788796a5b4c3d2e1f00112233445566778899aabbccddeeff0"
HMAC_KEY = "alt-record-hmac-key"
V4 = "1.1.1.1"
ADDRESSES = ("1.1.1.1", "1.0.0.1", "1.1.1.2", "1.0.0.2", "1.1.1.3", "1.0.0.3",
             "8.8.8.8", "8.8.4.4", "9.9.9.9", "149.112.112.112")
FAQ_CHANNEL = "1159243585309384805"
TABLES = ("steam_signin_facts", "steam_family_shares", "conn_markers")
BOUNDS = {"lock_timeout": "10s", "statement_timeout": "120s"}
SQL_DIR = Path(HERE).parent / "sql"
LOST = asyncpg.exceptions.ConnectionDoesNotExistError("connection was closed in the middle of operation")
NO_REQUEST = object()
_IDS = itertools.count(1)

# What the sign-in's own transaction issues before its commit (MATCH_HMAC_SECRET
# set, a verified ticket): the early ban read, the key, the ban read under it,
# the tombstone, the arming stamp, the prune, the session row.
SIGN_IN_BEFORE = ("FROM player_bans", "pg_advisory_xact_lock(", "FROM player_bans",
                  "FROM deleted_steam_ids", "UPDATE players SET steam_auth_seen_at",
                  "DELETE FROM steam_sessions", "INSERT INTO steam_sessions")
UNVERIFIED_BEFORE = ("FROM player_bans", "pg_advisory_xact_lock(", "FROM player_bans",
                     "FROM deleted_steam_ids", "DELETE FROM steam_sessions", "INSERT INTO steam_sessions")
# What the recording issues after it, on its full path (a borrowed copy and a
# markable address): the time limits, the key, the ban read, the tombstone,
# the notice, the share, the marker, the facts; then its commit.
FULL_AFTER = ("set_config('lock_timeout'", "pg_advisory_xact_lock(", "FROM player_bans",
              "FROM deleted_steam_ids", "FROM pending_channel_posts", "INSERT INTO steam_family_shares",
              "INSERT INTO conn_markers", "INSERT INTO steam_signin_facts")
NOTICE_LINE = "[ALT-SIGNALS] notice not up: nothing recorded"
_LINE = re.compile(r"^\[ALT-SIGNALS\] ((not recorded|outcome unknown): [A-Za-z_][A-Za-z0-9_]*"
                   r"|notice not up: nothing recorded)$")
# The closed list of lines that are not the recording's own and may be
# printed on its path (finding R2-14): the ban helper's refusal line, which
# names the route template (or "-") and nothing else.
ADMITTED = (re.compile(r"^\[BAN-GATE\] refused route=(-|/[A-Za-z0-9_/{}.-]*)$"),)

_FAULTS_DDL = """
CREATE TABLE alt_test_faults (tbl text PRIMARY KEY, what text NOT NULL);
CREATE FUNCTION alt_test_fault() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE w text;
BEGIN
  SELECT f.what INTO w FROM alt_test_faults f WHERE f.tbl = TG_TABLE_NAME;
  IF w = 'sleep' THEN
    PERFORM pg_sleep(6);
  ELSIF w IS NOT NULL THEN
    RAISE EXCEPTION 'planted fault on %', TG_TABLE_NAME USING ERRCODE = w;
  END IF;
  RETURN NEW;
END $f$;
CREATE TRIGGER alt_test_fault BEFORE INSERT OR UPDATE ON steam_signin_facts
  FOR EACH ROW EXECUTE FUNCTION alt_test_fault();
CREATE TRIGGER alt_test_fault BEFORE INSERT OR UPDATE ON steam_family_shares
  FOR EACH ROW EXECUTE FUNCTION alt_test_fault();
CREATE TRIGGER alt_test_fault BEFORE INSERT OR UPDATE ON conn_markers
  FOR EACH ROW EXECUTE FUNCTION alt_test_fault();
"""


def _sid():
    """A fresh synthetic 17-digit id below 76561197960265728."""
    return "76561190427%06d" % next(_IDS)


def _run(coro):
    return asyncio.run(coro)


def _faq_text():
    return "message one\n\n" + A.DISCLOSURE


# -- the case -------------------------------------------------------------------

@pytest.fixture(scope="module")
def case():
    lh._require_live_pg()
    built = {}

    async def extra(conn, schema):
        await conn.execute(_FAULTS_DDL)

    async def build():
        c = harness.CaseSchema(lh.DSN, "alt_record")
        await c.__aenter__()
        try:
            await lh._build(c, extra)
            cols = {r[0] for r in await c.conn.fetch(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = current_schema() AND table_name = 'pending_channel_posts'")}
            assert {"revision", "posted_revision", "sort_order"} <= cols, sorted(cols)
            for t in TABLES:
                assert await c.conn.fetchval("SELECT to_regclass($1) IS NOT NULL", t), t
            await c.conn.execute(
                "INSERT INTO pending_channel_posts (channel_id, content, sort_order, revision, posted_revision)"
                " VALUES ($1, $2, 1, 3, 3)", FAQ_CHANNEL, _faq_text())
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


class _Plan:
    """The statements the route's session issues, each with the number of
    commits before it, and the faults to raise after the sign-in's commit."""

    def __init__(self, fault_at=None, fault=None, commit_fault=None, rollback_fault=None,
                 after_commit_fault=None):
        self.log, self.commits, self.rollbacks = [], 0, 0
        self.fault_at, self.fault = fault_at, fault
        self.commit_fault, self.rollback_fault = commit_fault, rollback_fault
        # raised AFTER the recording's commit has been carried out (its
        # acknowledgement lost): the rows stand on the server
        self.after_commit_fault = after_commit_fault
        self.open_after = None

    def before(self):
        return [s for c, s in self.log if c == 0]

    def after(self):
        return [s for c, s in self.log if c >= 1]


class _ProbeSession(AsyncSession):
    """The route's session: a plain AsyncSession that logs and faults by its
    plan."""

    plan = None

    async def execute(self, statement, *args, **kw):
        p = self.plan
        if p is not None:
            p.log.append((p.commits, str(statement)))
            if p.commits >= 1 and p.fault_at is not None and len(p.after()) == p.fault_at:
                raise p.fault
        return await super().execute(statement, *args, **kw)

    async def commit(self):
        p = self.plan
        if p is not None and p.commits >= 1 and p.commit_fault is not None:
            raise p.commit_fault
        await super().commit()
        if p is not None:
            p.commits += 1
            if p.commits >= 2 and p.after_commit_fault is not None:
                raise p.after_commit_fault

    async def rollback(self):
        p = self.plan
        if p is not None and p.commits >= 1:
            p.rollbacks += 1
            if p.rollback_fault is not None:
                raise p.rollback_fault
        await super().rollback()


def _engine(schema):
    return create_async_engine(
        harness.async_dsn(lh.DSN), poolclass=NullPool,
        connect_args={"server_settings": {"search_path": harness.quoted(schema), **BOUNDS}})


def _with(schema, body):
    async def go():
        engine = _engine(schema)
        try:
            return await body(async_sessionmaker(engine, expire_on_commit=False),
                              async_sessionmaker(engine, class_=_ProbeSession, expire_on_commit=False))
        finally:
            await engine.dispose()
    return _run(go())


STEAM = {}


def _params(sid, owner=None, vac=False, pub=False, drop=()):
    p = {"result": "OK", "steamid": sid, "ownersteamid": owner or sid,
         "vacbanned": vac, "publisherbanned": pub}
    for k in drop:
        p.pop(k, None)
    return p


@pytest.fixture
def env(monkeypatch):
    """A verified sign-in (Steam key set, the call stubbed), the tombstone
    secret set, the signal key loaded, the notice line's clock reset."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", HMAC_KEY)
    monkeypatch.setenv("STEAM_WEB_API_KEY", "alt-record-steam-key")
    monkeypatch.delenv("STEAM_AUTH_ENFORCE", raising=False)
    monkeypatch.setattr(main, "_steam_http_get_json",
                        lambda url, timeout: {"response": {"params": dict(STEAM["params"])}})
    A.install_key(KEY_HEX)
    main._alt_notice_line_at[0] = None
    yield monkeypatch
    A.install_key(None)
    main._alt_notice_line_at[0] = None


def _request(host):
    client = None if host == "no client" else (host, 1)
    return Request({"type": "http", "method": "POST", "path": "/api/v1/auth/steam",
                    "headers": [], "query_string": b"", "client": client})


async def _sign_in(rsm, sid, host=V4, plan=None, **steam):
    """(status, answer, plan) of one sign-in through the real handler."""
    STEAM["params"] = _params(sid, **steam)
    plan = plan or _Plan()
    async with rsm() as db:
        db.plan = plan
        req = main.SteamAuthRequest(steam_id=sid, ticket_hex="abcd", mod_version="1.41.0")
        try:
            ans = await main.steam_auth(req=req, db=db,
                                        request=None if host is NO_REQUEST else _request(host))
            plan.open_after = db.in_transaction()
            return 200, ans, plan
        except HTTPException as e:
            return e.status_code, e.detail, plan


async def _rows(sm, sid):
    async with sm() as db:
        return [(await db.execute(text("SELECT count(*) FROM %s WHERE steam_id = :s" % t),
                                  {"s": sid})).scalar() for t in TABLES]


async def _digest(sm, sid):
    async with sm() as db:
        return [(await db.execute(text(
            "SELECT md5(COALESCE(string_agg(x::text, '|' ORDER BY x::text), '')) FROM %s x"
            " WHERE x.steam_id = :s" % t), {"s": sid})).scalar() for t in TABLES]


async def _session_committed(sm, token):
    async with sm() as db:
        return (await db.execute(text("SELECT count(*) FROM steam_sessions WHERE token_hash = :th"),
                                 {"th": hashlib.sha256(token.encode()).hexdigest()})).scalar() == 1


def _like_baseline(status, ans):
    assert status == 200, (status, ans)
    assert set(ans) == {"session_token", "expires_in", "verified"}, ans
    assert ans["verified"] is True and ans["expires_in"] == main.STEAM_SESSION_TTL_SECONDS, ans
    assert isinstance(ans["session_token"], str) and len(ans["session_token"]) >= 40, ans


async def _nothing_recorded(sm, sid, status, ans):
    _like_baseline(status, ans)
    assert await _session_committed(sm, ans["session_token"]), "the session row is not committed"
    assert await _rows(sm, sid) == [0, 0, 0], "a row of the three tables exists"


def _kinds(stmts, kinds):
    return len(stmts) == len(kinds) and all(k in s for s, k in zip(stmts, kinds))


def _lines(capsys):
    return [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("[ALT-SIGNALS]")]


async def _fault(sm, table, what):
    async with sm() as db:
        if what is None:
            await db.execute(text("DELETE FROM alt_test_faults WHERE tbl = :t"), {"t": table})
        else:
            await db.execute(text("INSERT INTO alt_test_faults (tbl, what) VALUES (:t, :w)"
                                  " ON CONFLICT (tbl) DO UPDATE SET what = EXCLUDED.what"),
                             {"t": table, "w": what})
        await db.commit()


async def _today(sm):
    async with sm() as db:
        return (await db.execute(text("SELECT CAST((now() AT TIME ZONE 'UTC') AS date)"))).scalar()


async def _facts(sm, sid):
    async with sm() as db:
        return (await db.execute(text("SELECT * FROM steam_signin_facts WHERE steam_id = :s"),
                                 {"s": sid})).mappings().one()


def _boom(*a, **kw):
    raise ValueError("planted")


# -- the notice states ----------------------------------------------------------

CLOSED = {
    "absent": "UPDATE pending_channel_posts SET channel_id = 'elsewhere' WHERE id = :id",
    "message 2 only": "UPDATE pending_channel_posts SET sort_order = 2 WHERE id = :id",
    "two rows": ("INSERT INTO pending_channel_posts (channel_id, content, sort_order, revision, posted_revision)"
                 " SELECT channel_id, content, sort_order, revision, posted_revision"
                 " FROM pending_channel_posts WHERE id = :id"),
    "never posted": "UPDATE pending_channel_posts SET posted_revision = NULL WHERE id = :id",
    "posted behind": "UPDATE pending_channel_posts SET posted_revision = revision - 1 WHERE id = :id",
    "sentence missing": "UPDATE pending_channel_posts SET content = 'message one' WHERE id = :id",
    "sentence changed": "UPDATE pending_channel_posts SET content = left(content, length(content) - 1) WHERE id = :id",
}


async def _faq_id(sm):
    async with sm() as db:
        return (await db.execute(text(
            "SELECT min(id) FROM pending_channel_posts WHERE channel_id IN (:c, 'elsewhere')"),
            {"c": FAQ_CHANNEL})).scalar()


async def _close(sm, state):
    fid = await _faq_id(sm)
    async with sm() as db:
        await db.execute(text(CLOSED[state]), {"id": fid})
        await db.commit()
    return fid


async def _reopen(sm, fid):
    async with sm() as db:
        await db.execute(text("DELETE FROM pending_channel_posts WHERE id <> :id"), {"id": fid})
        await db.execute(text(
            "UPDATE pending_channel_posts SET channel_id = :c, content = :t, sort_order = 1,"
            " revision = 3, posted_revision = 3 WHERE id = :id"),
            {"c": FAQ_CHANNEL, "t": _faq_text(), "id": fid})
        await db.commit()


# -- without a database ---------------------------------------------------------

def test_the_route_names_its_request_parameter():
    """FastAPI hands the request to the parameter annotated with the bare
    Request class; it is neither a query nor a body parameter."""
    route = next(r for r in main.app.routes if getattr(r, "path", None) == "/api/v1/auth/steam")
    assert route.dependant.request_param_name == "request"
    assert [p.name for p in route.dependant.query_params] == []
    assert [p.name for p in route.dependant.body_params] == ["req"]


def test_the_notice_channel_is_the_one_427_revises():
    t = (SQL_DIR / "427_alt_signals.sql").read_text(encoding="utf-8")
    assert set(re.findall(r"p\.channel_id = '(\d+)'", t)) == {main._ALT_FAQ_CHANNEL}


def test_the_boot_line_names_the_key_state_and_never_the_key(monkeypatch, capsys):
    try:
        for raw, want in ((None, "[ALT-SIGNALS] key absent"), ("zz", "[ALT-SIGNALS] key refused"),
                          (KEY_HEX, "[ALT-SIGNALS] key loaded id=959163f0cc32")):
            if raw is None:
                monkeypatch.delenv(A.KEY_ENV, raising=False)
            else:
                monkeypatch.setenv(A.KEY_ENV, raw)
            main._alt_boot()
            out = capsys.readouterr().out
            assert out.splitlines() == [want], out
            assert KEY_HEX not in out
    finally:
        A.install_key(None)


# -- the recorded path ----------------------------------------------------------

def test_a_verified_sign_in_records_the_facts_the_share_and_the_marker(case, env, capsys):
    sid, owner = _sid(), _sid()

    async def body(sm, rsm):
        status, ans, plan = await _sign_in(rsm, sid, owner=owner, vac=True)
        _like_baseline(status, ans)
        assert await _session_committed(sm, ans["session_token"])
        async with sm() as db:
            shares = (await db.execute(text("SELECT * FROM steam_family_shares WHERE steam_id = :s"),
                                       {"s": sid})).mappings().all()
            markers = (await db.execute(text("SELECT * FROM conn_markers WHERE steam_id = :s"),
                                        {"s": sid})).mappings().all()
        return plan, await _facts(sm, sid), shares, markers, await _today(sm)

    plan, f, shares, markers, today = _with(case, body)
    k = A.loaded_key()
    assert _kinds(plan.before(), SIGN_IN_BEFORE), plan.before()
    assert _kinds(plan.after(), FULL_AFTER), plan.after()
    assert plan.commits == 2 and plan.rollbacks == 0 and plan.open_after is False
    assert f["copy_state"] == "shared" and f["shared_first_at"] is not None
    assert f["shared_last_at"] == f["shared_first_at"] == f["first_seen_at"] == f["last_seen_at"]
    assert f["vac_banned"] is True and f["vac_banned_first_at"] == f["vac_banned_last_at"] == f["last_seen_at"]
    assert f["publisher_banned"] is False and f["publisher_banned_first_at"] is None
    assert (f["over_limit_days"], f["over_limit_day"]) == (0, None)
    assert [(r["key_id"], bytes(r["owner_mark"])) for r in shares] == [(k.key_id, A.account_mark(k.secret, owner))]
    seen = A.observe(V4, k, conn_ranges.classify_address, conn_ranges.CR_LAN_NETS)
    assert [(r["key_id"], bytes(r["addr_mark"]), bytes(r["block_mark"]), r["family"], r["conn_class"], r["day"])
            for r in markers] == [(k.key_id, seen.addr_mark, seen.block_mark, 4, seen.conn_class, today)]
    assert _lines(capsys) == []


def test_the_statements_a_verified_sign_in_adds(case, env):
    """7 to 9 with the commit while MATCH_HMAC_SECRET is set (own copy and no
    markable address: 6 and the commit; a borrowed copy and an address: 8 and
    the commit); one fewer without it (no tombstone read)."""
    async def body(sm, rsm):
        out = []
        for owner, host in ((None, NO_REQUEST), (_sid(), V4)):
            out.append((await _sign_in(rsm, _sid(), host=host, owner=owner))[2])
        env.setattr(main, "MATCH_HMAC_SECRET", "")
        out.append((await _sign_in(rsm, _sid(), host=NO_REQUEST))[2])
        return out

    own, full, no_secret = _with(case, body)
    assert _kinds(own.after(), FULL_AFTER[:5] + FULL_AFTER[7:]) and own.commits == 2, own.after()
    assert _kinds(full.after(), FULL_AFTER) and full.commits == 2, full.after()
    assert _kinds(no_secret.after(), FULL_AFTER[:3] + FULL_AFTER[4:5] + FULL_AFTER[7:]), no_secret.after()
    assert (len(own.after()) + 1, len(full.after()) + 1, len(no_secret.after()) + 1) == (7, 9, 6)


@pytest.mark.parametrize("how", ["unverified", "key absent", "key refused"])
def test_no_statement_is_added_without_a_verified_sign_in_and_a_loaded_key(case, env, how):
    sid = _sid()
    if how == "unverified":
        env.delenv("STEAM_WEB_API_KEY")
    elif how == "key absent":
        A.install_key(None)
    else:
        A.install_key("zz")

    async def body(sm, rsm):
        status, ans, plan = await _sign_in(rsm, sid, owner=_sid())
        assert status == 200 and ans["verified"] is (how != "unverified"), (status, ans)
        assert await _session_committed(sm, ans["session_token"])
        return plan, await _rows(sm, sid)

    plan, rows = _with(case, body)
    assert plan.after() == [] and plan.commits == 1 and plan.open_after is False, plan.after()
    assert _kinds(plan.before(), UNVERIFIED_BEFORE if how == "unverified" else SIGN_IN_BEFORE), plan.before()
    assert rows == [0, 0, 0]


def test_the_sign_in_transaction_is_today_statement_for_statement(case, env):
    """Before its commit the sign-in issues exactly today's statements, with
    the key loaded as with the key absent: the recording adds nothing there."""
    async def body(sm, rsm):
        loaded = (await _sign_in(rsm, _sid(), owner=_sid()))[2]
        A.install_key(None)
        absent = (await _sign_in(rsm, _sid(), owner=_sid()))[2]
        return loaded, absent

    loaded, absent = _with(case, body)
    assert _kinds(loaded.before(), SIGN_IN_BEFORE), loaded.before()
    assert _kinds(absent.before(), SIGN_IN_BEFORE), absent.before()
    assert loaded.after() and not absent.after()


# -- finding 23: every failure leaves the sign-in as it is ---------------------

@pytest.mark.parametrize("target", ["steam_fields", "observe", "address"])
def test_preparation_that_raises_records_nothing(case, env, capsys, target):
    if target == "address":
        env.setattr(main, "_rl_client_address", _boom)
    else:
        env.setattr(main._alt_signals, target, _boom)
    sid = _sid()

    async def body(sm, rsm):
        status, ans, plan = await _sign_in(rsm, sid, owner=_sid())
        await _nothing_recorded(sm, sid, status, ans)
        return plan

    plan = _with(case, body)
    assert plan.after() == [], plan.after()
    assert _lines(capsys) == ["[ALT-SIGNALS] not recorded: ValueError"]


def test_the_key_loader_that_raises_records_nothing(case, env, capsys):
    env.setattr(main._alt_signals, "loaded_key", _boom)
    sid = _sid()

    async def body(sm, rsm):
        status, ans, plan = await _sign_in(rsm, sid, owner=_sid())
        await _nothing_recorded(sm, sid, status, ans)
        return plan

    plan = _with(case, body)
    assert plan.after() == []
    assert _lines(capsys) == ["[ALT-SIGNALS] not recorded: ValueError"]


def _between_the_transactions(env, plant):
    """Run `plant` once, between the sign-in's commit and the recording's
    taking call (at the second call of the taking helper)."""
    orig = main._ban_lock_and_gate
    calls = []

    async def wrapped(db, ids, *a, **kw):
        calls.append(1)
        if len(calls) == 2:
            await plant()
        return await orig(db, ids, *a, **kw)
    env.setattr(main, "_ban_lock_and_gate", wrapped)
    return calls


def test_the_taking_call_refuses_a_ban_committed_after_the_sign_in(case, env, capsys):
    sid = _sid()

    async def body(sm, rsm):
        async def plant():
            async with sm() as db:
                admin = _sid()
                await lh._insert(db, "admin_users", {"steam_id": admin})
                await lh._insert(db, "players", {"id": uuid.uuid4(), "steam_id": sid,
                                                 "display_name": "ar-" + sid[-4:]})
                await db.execute(text(
                    "INSERT INTO player_bans (id, steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
                    " VALUES (:id, :s, 'alt-record', :a, NOW(), NOW() + INTERVAL '1 hour')"),
                    {"id": uuid.uuid4(), "s": sid, "a": admin})
                await db.commit()
        calls = _between_the_transactions(env, plant)
        status, ans, plan = await _sign_in(rsm, sid, owner=_sid())
        await _nothing_recorded(sm, sid, status, ans)
        return calls, plan

    calls, plan = _with(case, body)
    assert len(calls) == 2 and plan.rollbacks == 1
    assert _lines(capsys) == ["[ALT-SIGNALS] not recorded: refused"]


def test_the_tombstone_read_again_refuses_an_account_deleted_after_the_sign_in(case, env, capsys):
    sid = _sid()

    async def body(sm, rsm):
        async def plant():
            async with sm() as db:
                await lh._insert(db, "deleted_steam_ids", {"steam_id_hash": main._hash_steam_id(sid)})
                await db.commit()
        calls = _between_the_transactions(env, plant)
        status, ans, plan = await _sign_in(rsm, sid, owner=_sid())
        await _nothing_recorded(sm, sid, status, ans)
        return calls, plan

    calls, plan = _with(case, body)
    assert len(calls) == 2 and plan.rollbacks == 1
    assert _lines(capsys) == ["[ALT-SIGNALS] not recorded: deleted"]


@pytest.mark.parametrize("state", sorted(CLOSED))
def test_a_closed_notice_records_nothing_and_says_so_once(case, env, capsys, state):
    """Closed is every state but exactly one message 1 row of the FAQ channel,
    posted at its revision, holding the disclosure. Two closed sign-ins say
    one line. Control: reopened, the next sign-in records."""
    sid, control = _sid(), _sid()

    async def body(sm, rsm):
        fid = await _close(sm, state)
        try:
            first = await _sign_in(rsm, sid, owner=_sid())
            second = await _sign_in(rsm, sid, owner=_sid())
        finally:
            await _reopen(sm, fid)
        for status, ans, _plan in (first, second):
            await _nothing_recorded(sm, sid, status, ans)
        status, ans, _plan = await _sign_in(rsm, control, owner=_sid())
        _like_baseline(status, ans)
        return first[2], await _rows(sm, control)

    plan, control_rows = _with(case, body)
    assert "FROM pending_channel_posts" in plan.after()[-1] and plan.rollbacks == 1, plan.after()
    assert _lines(capsys) == [NOTICE_LINE]
    assert control_rows == [1, 1, 1]


def test_the_notice_line_is_said_at_most_once_an_hour(case, env, capsys):
    async def body(sm, rsm):
        fid = await _close(sm, "never posted")
        try:
            await _sign_in(rsm, _sid())
            await _sign_in(rsm, _sid())
            n = len(_lines(capsys))
            main._alt_notice_line_at[0] -= main._ALT_NOTICE_LINE_EVERY_S + 1
            await _sign_in(rsm, _sid())
        finally:
            await _reopen(sm, fid)
        return n, _lines(capsys)

    n, later = _with(case, body)
    assert (n, later) == (1, [NOTICE_LINE])


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("what", ["P0001", "40P01"])
def test_an_upsert_that_raises_records_nothing(case, env, capsys, table, what):
    """An ordinary error (P0001) and a deadlock error (40P01) at each upsert."""
    sid = _sid()

    async def body(sm, rsm):
        await _fault(sm, table, what)
        try:
            status, ans, plan = await _sign_in(rsm, sid, owner=_sid())
        finally:
            await _fault(sm, table, None)
        await _nothing_recorded(sm, sid, status, ans)
        return plan

    plan = _with(case, body)
    assert ("INSERT INTO " + table) in plan.after()[-1] and plan.rollbacks == 1, plan.after()
    lines = _lines(capsys)
    assert len(lines) == 1 and lines[0].startswith("[ALT-SIGNALS] not recorded: ") and _LINE.match(lines[0])


def _segment(env):
    """Time the recording's own segment (from _alt_record's call to its end)
    on the monotonic clock and keep the exception _alt_abandon is given."""
    seg = {}
    real_record, real_abandon = main._alt_record, main._alt_abandon

    async def record(*a, **kw):
        t0 = time.monotonic()
        try:
            return await real_record(*a, **kw)
        finally:
            seg["took"] = time.monotonic() - t0

    async def abandon(db, ex):
        seg["ex"] = ex
        return await real_abandon(db, ex)
    env.setattr(main, "_alt_record", record)
    env.setattr(main, "_alt_abandon", abandon)
    return seg


def _sqlstate(ex):
    """The first SQLSTATE on `ex` or on what it wraps (.orig, __cause__)."""
    todo, seen = [ex], set()
    while todo:
        e = todo.pop(0)
        if e is None or id(e) in seen:
            continue
        seen.add(id(e))
        for code in (getattr(e, "sqlstate", None), getattr(e, "pgcode", None)):
            if isinstance(code, str) and code:
                return code
        todo += [getattr(e, "orig", None), getattr(e, "__cause__", None)]
    return None


def test_a_statement_past_its_time_limit_is_cancelled_and_records_nothing(case, env, capsys):
    """Finding R2-9, the statement limit ALONE: no lock is held; the facts
    upsert sleeps six seconds. First discriminator: the SQLSTATE is 57014
    (query_canceled), not 55P03. Second: the recording's segment ends at
    least RECORD_STATEMENT_TIMEOUT_MS (1.5 s, less 0.05 s of clock grain)
    and under 2.5 s after it began: a doubled limit (3.0 s) cannot meet that
    bound (margin 0.5 s), and the 1.0 s above the limit covers the segment's
    six earlier statements on the test server. The clock is the server's
    own timer and cannot be given."""
    sid = _sid()
    seg = _segment(env)

    async def body(sm, rsm):
        await _fault(sm, "steam_signin_facts", "sleep")
        try:
            status, ans, plan = await _sign_in(rsm, sid, owner=_sid())
        finally:
            await _fault(sm, "steam_signin_facts", None)
        await _nothing_recorded(sm, sid, status, ans)

    _with(case, body)
    assert _sqlstate(seg.get("ex")) == "57014", repr(seg.get("ex"))
    limit = A.RECORD_STATEMENT_TIMEOUT_MS / 1000.0
    assert limit - 0.05 <= seg["took"] < 2.5, seg["took"]
    assert len(_lines(capsys)) == 1


@pytest.mark.parametrize("table", TABLES)
def test_the_lock_limit_ends_the_wait_on_a_row_another_transaction_holds(case, env, capsys, table):
    """Finding R2-9, the lock limit ALONE. The account's rows exist; another
    transaction holds the row of `table` FOR UPDATE (as the retention pass
    does) for up to six seconds; the second sign-in's upsert of that row
    stops and nothing changes. First discriminator: the SQLSTATE is 55P03
    (lock_not_available), which the statement limit never raises. Second:
    the recording's segment ends at least RECORD_LOCK_TIMEOUT_MS (0.5 s, less
    0.05 s of clock grain) and under 1.2 s after it began, a bound the
    statement limit (1.5 s) cannot explain (margin 0.3 s). The clock is the
    server's own timer and cannot be given."""
    sid, owner = _sid(), _sid()
    seg = _segment(env)

    async def body(sm, rsm):
        status, ans, _plan = await _sign_in(rsm, sid, owner=owner)
        _like_baseline(status, ans)
        before = await _digest(sm, sid)
        seg.clear()
        holder = sm()
        try:
            await holder.execute(text("SELECT 1 FROM %s WHERE steam_id = :s FOR UPDATE" % table), {"s": sid})
            task = asyncio.create_task(_sign_in(rsm, sid, owner=owner))
            for _ in range(120):
                if task.done():
                    break
                await asyncio.sleep(0.05)
            await holder.rollback()
        finally:
            await holder.close()
        status, ans, plan = await task
        _like_baseline(status, ans)
        assert await _session_committed(sm, ans["session_token"])
        return before, await _digest(sm, sid), plan

    before, after, plan = _with(case, body)
    assert after == before, "a row changed"
    assert _sqlstate(seg.get("ex")) == "55P03", repr(seg.get("ex"))
    limit = A.RECORD_LOCK_TIMEOUT_MS / 1000.0
    assert limit - 0.05 <= seg["took"] < 1.2, seg["took"]
    assert ("INSERT INTO " + table) in plan.after()[-1] and plan.rollbacks == 1, plan.after()
    lines = _lines(capsys)
    assert len(lines) == 1 and _LINE.match(lines[0]) and lines[0] != NOTICE_LINE, lines


@pytest.mark.parametrize("at", list(range(1, 9)) + ["commit"])
def test_the_connection_reported_lost_records_nothing(case, env, capsys, at):
    """At each of the recording's eight statements and at its commit. The
    notice read (the fifth) is a closed notice: its line is the notice
    line."""
    sid = _sid()
    plan = _Plan(commit_fault=LOST) if at == "commit" else _Plan(fault_at=at, fault=LOST)

    async def body(sm, rsm):
        status, ans, _p = await _sign_in(rsm, sid, plan=plan, owner=_sid())
        await _nothing_recorded(sm, sid, status, ans)

    _with(case, body)
    assert len(plan.after()) == (8 if at == "commit" else at) and plan.rollbacks == 1, plan.after()
    # A failed commit is an outcome not known (finding R2-2), even here,
    # where the planted fault is raised before the COMMIT is sent.
    want = (NOTICE_LINE if at == 5 else
            "[ALT-SIGNALS] outcome unknown: ConnectionDoesNotExistError" if at == "commit" else
            "[ALT-SIGNALS] not recorded: ConnectionDoesNotExistError")
    assert _lines(capsys) == [want]


def test_a_rollback_that_raises_changes_nothing_the_caller_sees(case, env, capsys):
    """The rollback is not confirmed, so the line says the outcome is not
    known (finding R2-2)."""
    sid = _sid()
    plan = _Plan(fault_at=8, fault=LOST, rollback_fault=LOST)

    async def body(sm, rsm):
        status, ans, _p = await _sign_in(rsm, sid, plan=plan, owner=_sid())
        await _nothing_recorded(sm, sid, status, ans)

    _with(case, body)
    assert plan.rollbacks == 1 and plan.open_after is True
    assert _lines(capsys) == ["[ALT-SIGNALS] outcome unknown: ConnectionDoesNotExistError"]


def test_a_commit_that_stands_while_its_answer_is_lost_says_outcome_unknown_and_doubles_nothing(
        case, env, capsys, monkeypatch):
    """Finding R2-2 (c). The route's session comes from the api's own
    dependency (database.get_db over the probe's sessions). The recording's
    COMMIT is carried out, and THEN the lost-connection fault is raised, as
    when the server committed and its answer never came. The guard returns
    the built answer; the dependency's teardown closes the session. The
    rows stand; the line is the unknown word, never "not recorded"; the
    account's next sign-in leaves one row per key, nothing doubled."""
    import database
    sid, owner = _sid(), _sid()

    async def body(sm, rsm):
        monkeypatch.setattr(database, "async_session", rsm)
        STEAM["params"] = _params(sid, owner=owner)
        plan = _Plan(after_commit_fault=LOST)
        dep = database.get_db()
        db = await dep.__anext__()
        db.plan = plan
        req = main.SteamAuthRequest(steam_id=sid, ticket_hex="abcd", mod_version="1.41.0")
        try:
            ans = await main.steam_auth(req=req, db=db, request=_request(V4))
        finally:
            await dep.aclose()
        _like_baseline(200, ans)
        assert await _session_committed(sm, ans["session_token"])
        first = await _rows(sm, sid)
        lines = _lines(capsys)
        status, ans2, _p = await _sign_in(rsm, sid, owner=owner)
        _like_baseline(status, ans2)
        return plan, first, lines, await _rows(sm, sid)

    plan, first, lines, second = _with(case, body)
    assert plan.commits == 2, plan.commits
    assert first == [1, 1, 1], first
    assert lines == ["[ALT-SIGNALS] outcome unknown: ConnectionDoesNotExistError"], lines
    assert second == [1, 1, 1], second


@pytest.mark.parametrize("path", ["not-recorded line", "notice line"])
def test_a_print_that_raises_changes_nothing_the_caller_sees(case, env, path):
    real = builtins.print
    said = []

    def picky(*a, **kw):
        if a and isinstance(a[0], str) and a[0].startswith("[ALT-SIGNALS]"):
            said.append(a[0])
            raise OSError("stdout closed")
        return real(*a, **kw)
    env.setattr(builtins, "print", picky)
    if path == "not-recorded line":
        env.setattr(main._alt_signals, "steam_fields", _boom)
    sid = _sid()

    async def body(sm, rsm):
        fid = await _close(sm, "never posted") if path == "notice line" else None
        try:
            status, ans, _p = await _sign_in(rsm, sid, owner=_sid())
        finally:
            if fid is not None:
                await _reopen(sm, fid)
        await _nothing_recorded(sm, sid, status, ans)

    _with(case, body)
    assert said == ["[ALT-SIGNALS] not recorded: ValueError" if path == "not-recorded line" else NOTICE_LINE]


def test_the_lines_carry_no_id_address_or_mark(case, env, capsys):
    sid, owner = _sid(), _sid()

    async def body(sm, rsm):
        fid = await _close(sm, "never posted")
        try:
            await _sign_in(rsm, sid, owner=owner)
        finally:
            await _reopen(sm, fid)
        await _fault(sm, "conn_markers", "P0001")
        try:
            await _sign_in(rsm, sid, owner=owner)
        finally:
            await _fault(sm, "conn_markers", None)

    _with(case, body)
    lines = _lines(capsys)
    k = A.loaded_key()
    seen = A.observe(V4, k, conn_ranges.classify_address, conn_ranges.CR_LAN_NETS)
    assert len(lines) == 2 and all(_LINE.match(ln) for ln in lines), lines
    for secret in (sid, owner, V4, KEY_HEX, seen.addr_mark.hex(), A.account_mark(k.secret, owner).hex()):
        assert not any(secret in ln for ln in lines), secret


# -- which address (item 18) ----------------------------------------------------

@pytest.mark.parametrize("host", [None, "unknown", "no client", NO_REQUEST, "10.0.0.1", "224.0.0.1", "192.0.2.1"],
                         ids=["None", "unknown", "no client", "no request", "private", "multicast", "documentation"])
def test_no_marker_without_a_markable_address_and_the_rest_is_recorded(case, env, host):
    sid = _sid()

    async def body(sm, rsm):
        status, ans, plan = await _sign_in(rsm, sid, host=host, owner=_sid())
        _like_baseline(status, ans)
        return plan, await _rows(sm, sid)

    plan, rows = _with(case, body)
    assert rows == [1, 1, 0], rows
    assert not any("INSERT INTO conn_markers" in s for s in plan.after())


def test_a_second_sign_in_the_same_day_from_the_same_address_adds_no_marker_row(case, env):
    sid = _sid()

    async def body(sm, rsm):
        await _sign_in(rsm, sid)
        await _sign_in(rsm, sid)
        async with sm() as db:
            m = (await db.execute(text("SELECT first_at, last_at FROM conn_markers WHERE steam_id = :s"),
                                  {"s": sid})).all()
        return m, await _facts(sm, sid)

    m, f = _with(case, body)
    assert len(m) == 1 and m[0][1] > m[0][0], m
    assert f["last_seen_at"] > f["first_seen_at"]


# -- the storage limits (R4) ----------------------------------------------------

def test_the_marker_limit_holds_and_a_day_over_it_counts_once(case, env):
    sid = _sid()

    async def body(sm, rsm):
        for host in ADDRESSES:
            await _sign_in(rsm, sid, host=host)
        async with sm() as db:
            marks = {bytes(r[0]) for r in (await db.execute(text(
                "SELECT addr_mark FROM conn_markers WHERE steam_id = :s"), {"s": sid})).all()}
        return marks, await _facts(sm, sid), await _today(sm)

    marks, f, today = _with(case, body)
    k = A.loaded_key()
    want = {A.observe(h, k, conn_ranges.classify_address, conn_ranges.CR_LAN_NETS).addr_mark
            for h in ADDRESSES[:A.MARKERS_PER_DAY]}
    assert len(ADDRESSES) == A.MARKERS_PER_DAY + 2
    assert marks == want
    assert (f["over_limit_days"], f["over_limit_day"]) == (1, today)


def test_the_share_limit_holds(case, env):
    sid, owners = _sid(), [_sid() for _ in range(A.SHARES_PER_ACCOUNT + 1)]

    async def body(sm, rsm):
        for owner in owners:
            await _sign_in(rsm, sid, owner=owner)
        async with sm() as db:
            marks = {bytes(r[0]) for r in (await db.execute(text(
                "SELECT owner_mark FROM steam_family_shares WHERE steam_id = :s"), {"s": sid})).all()}
        return marks, await _facts(sm, sid), await _today(sm)

    marks, f, today = _with(case, body)
    k = A.loaded_key()
    assert marks == {A.account_mark(k.secret, o) for o in owners[:A.SHARES_PER_ACCOUNT]}
    assert (f["over_limit_days"], f["over_limit_day"]) == (1, today)


def test_a_day_over_the_limit_after_an_earlier_one_counts_again(case, env):
    sid = _sid()

    async def body(sm, rsm):
        for host in ADDRESSES[:A.MARKERS_PER_DAY]:
            await _sign_in(rsm, sid, host=host)
        async with sm() as db:
            await db.execute(text(
                "UPDATE steam_signin_facts SET over_limit_days = 3,"
                " over_limit_day = CAST((now() AT TIME ZONE 'UTC') AS date) - 1 WHERE steam_id = :s"), {"s": sid})
            await db.commit()
        await _sign_in(rsm, sid, host=ADDRESSES[A.MARKERS_PER_DAY])
        return await _facts(sm, sid), await _today(sm)

    f, today = _with(case, body)
    assert (f["over_limit_days"], f["over_limit_day"]) == (4, today)


# -- the account's row ----------------------------------------------------------

def test_a_sign_in_older_than_the_row_moves_no_last_sight_and_no_reported_value(case, env):
    sid, owner = _sid(), _sid()

    async def body(sm, rsm):
        await _sign_in(rsm, sid, owner=owner, vac=True)
        async with sm() as db:
            await db.execute(text(
                "UPDATE steam_signin_facts SET last_seen_at = now() + INTERVAL '1 day' WHERE steam_id = :s"),
                {"s": sid})
            await db.commit()
        planted = await _facts(sm, sid)
        await _sign_in(rsm, sid, vac=False)
        return planted, await _facts(sm, sid)

    planted, f = _with(case, body)
    assert f["last_seen_at"] == planted["last_seen_at"]
    assert (f["copy_state"], f["vac_banned"]) == ("shared", True)
    assert (f["vac_banned_first_at"], f["vac_banned_last_at"]) == (planted["vac_banned_first_at"],
                                                                 planted["vac_banned_last_at"])


def test_a_missing_report_keeps_the_stored_values_and_a_new_one_replaces_them(case, env):
    sid, owner = _sid(), _sid()

    async def body(sm, rsm):
        await _sign_in(rsm, sid, owner=owner, vac=True, pub=True)
        first = await _facts(sm, sid)
        await _sign_in(rsm, sid, drop=("ownersteamid", "vacbanned", "publisherbanned"))
        kept = await _facts(sm, sid)
        await _sign_in(rsm, sid, vac=False, pub=False)
        return first, kept, await _facts(sm, sid)

    first, kept, last = _with(case, body)
    assert (kept["copy_state"], kept["vac_banned"], kept["publisher_banned"]) == ("shared", True, True)
    assert kept["shared_last_at"] == first["shared_last_at"] and kept["vac_banned_last_at"] == first["vac_banned_last_at"]
    assert kept["last_seen_at"] > first["last_seen_at"]
    assert (last["copy_state"], last["vac_banned"], last["publisher_banned"]) == ("own", False, False)
    assert (last["shared_first_at"], last["vac_banned_first_at"]) == (first["shared_first_at"],
                                                                     first["vac_banned_first_at"])


# -- everything a recording prints (finding R2-14) -------------------------------

def test_a_recording_prints_only_its_guarded_lines_and_the_admitted_ones(case, env, monkeypatch):
    """Every print() made while the recording or its abandon runs is caught
    (the real print still runs): a full recording, a closed notice, an upsert
    fault and a ban committed between the two transactions (the taking
    call's refusal reaches the ban helper's own line). Each caught line is
    one of the recording's own (_LINE) or on the closed list ADMITTED, and
    none names the account, the owner, the address, the key or a mark."""
    real = builtins.print
    said, on = [], [False]

    def spy(*a, **kw):
        if on[0]:
            said.append(" ".join(str(x) for x in a))
        return real(*a, **kw)

    real_record, real_abandon = main._alt_record, main._alt_abandon

    async def record(*a, **kw):
        on[0] = True
        try:
            return await real_record(*a, **kw)
        finally:
            on[0] = False

    async def abandon(db, ex):
        on[0] = True
        try:
            return await real_abandon(db, ex)
        finally:
            on[0] = False
    monkeypatch.setattr(builtins, "print", spy)
    monkeypatch.setattr(main, "_alt_record", record)
    monkeypatch.setattr(main, "_alt_abandon", abandon)
    sid, owner, banned = _sid(), _sid(), _sid()

    async def body(sm, rsm):
        await _sign_in(rsm, sid, owner=owner)
        fid = await _close(sm, "never posted")
        try:
            await _sign_in(rsm, sid, owner=owner)
        finally:
            await _reopen(sm, fid)
        await _fault(sm, "conn_markers", "P0001")
        try:
            await _sign_in(rsm, sid, owner=owner)
        finally:
            await _fault(sm, "conn_markers", None)

        async def plant():
            async with sm() as db:
                admin = _sid()
                await lh._insert(db, "admin_users", {"steam_id": admin})
                await lh._insert(db, "players", {"id": uuid.uuid4(), "steam_id": banned,
                                                 "display_name": "ap-" + banned[-4:]})
                await db.execute(text(
                    "INSERT INTO player_bans (id, steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
                    " VALUES (:id, :s, 'alt-print', :a, NOW(), NOW() + INTERVAL '1 hour')"),
                    {"id": uuid.uuid4(), "s": banned, "a": admin})
                await db.commit()
        _between_the_transactions(env, plant)
        await _sign_in(rsm, banned, owner=owner)

    _with(case, body)
    stray = [ln for ln in said if not (_LINE.match(ln) or any(p.match(ln) for p in ADMITTED))]
    assert stray == [], stray
    assert any(ADMITTED[0].match(ln) for ln in said), said
    k = A.loaded_key()
    seen = A.observe(V4, k, conn_ranges.classify_address, conn_ranges.CR_LAN_NETS)
    for secret in (sid, owner, banned, V4, KEY_HEX, seen.addr_mark.hex(), A.account_mark(k.secret, owner).hex()):
        assert not any(secret in ln for ln in said), secret


# -- the commands the driver sends under the production pool (finding R2-12) ------

class _Wire(asyncpg.Connection):
    """An asyncpg connection that logs, while `log` is a list, every command
    the driver sends on it: simple-protocol commands (execute: BEGIN,
    COMMIT, ROLLBACK), the pool's ping (fetchrow), each preparation
    (prepare) and, through the patch below, each bound execution of a
    prepared statement (bind)."""

    log = None

    async def execute(self, query, *args, timeout=None):
        if _Wire.log is not None:
            _Wire.log.append(("execute", query))
        return await super().execute(query, *args, timeout=timeout)

    async def fetchrow(self, query, *args, timeout=None, record_class=None):
        if _Wire.log is not None:
            _Wire.log.append(("fetchrow", query))
        return await super().fetchrow(query, *args, timeout=timeout, record_class=record_class)

    async def prepare(self, query, *, name=None, timeout=None, record_class=None):
        if _Wire.log is not None:
            _Wire.log.append(("prepare", query))
        return await super().prepare(query, name=name, timeout=timeout, record_class=record_class)


def test_the_commands_the_driver_sends_for_one_recording_under_the_production_pool(case, env, monkeypatch):
    """The engine is built as the api's database module builds its engine:
    its own create_async_engine and the pool settings read from
    database.engine itself (QueuePool, pool_size 20, max_overflow 10,
    pool_timeout 30, pool_pre_ping, pool_recycle 1800); the test adds only
    the case schema's search path and the logging connection class. After
    the sign-in's COMMIT the driver sends, in order: the pool's pre-ping on
    checkout (BEGIN, the empty query, ROLLBACK), the recording's BEGIN, then
    its eight statements, the first of them its limits, and its COMMIT. Each
    statement may be preceded by its preparation. The pre-ping, the BEGIN
    and the limits statement's own preparation and execution come before
    the lane's limits are in force (a residual of claim C30)."""
    import asyncpg.prepared_stmt as ps
    import database
    from sqlalchemy.pool import QueuePool
    pool = database.engine.pool
    settings = {"pool_size": pool.size(), "max_overflow": pool._max_overflow, "pool_timeout": pool._timeout,
                "pool_pre_ping": pool._pre_ping, "pool_recycle": pool._recycle}
    assert isinstance(pool, QueuePool), type(pool)
    assert settings == {"pool_size": 20, "max_overflow": 10, "pool_timeout": 30,
                        "pool_pre_ping": True, "pool_recycle": 1800}, settings
    real_fetch = ps.PreparedStatement.fetch

    async def fetch(self, *args, timeout=None):
        if _Wire.log is not None and isinstance(self._connection, _Wire):
            _Wire.log.append(("bind", self.get_query()))
        return await real_fetch(self, *args, timeout=timeout)
    monkeypatch.setattr(ps.PreparedStatement, "fetch", fetch)
    sid = _sid()

    async def go():
        engine = database.create_async_engine(
            harness.async_dsn(lh.DSN), echo=False, **settings,
            connect_args={"connection_class": _Wire,
                          "server_settings": {"search_path": harness.quoted(case), **BOUNDS}})
        try:
            rsm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with rsm() as warm:   # one connection in the pool, as on a running box
                await warm.execute(text("SELECT 1"))
            _Wire.log = []
            status, ans, _p = await _sign_in(rsm, sid, owner=_sid())
            log, _Wire.log = _Wire.log, None
            return status, ans, log
        finally:
            _Wire.log = None
            await engine.dispose()

    status, ans, log = _run(go())
    _like_baseline(status, ans)
    commits = [i for i, (k, q) in enumerate(log) if k == "execute" and q.strip().upper().startswith("COMMIT")]
    assert len(commits) == 2, log
    after = log[commits[0] + 1:commits[1] + 1]
    sent = [(k, q) for k, q in after if k != "prepare"]
    head = [(k, q.strip().upper()) for k, q in sent[:4]]
    assert [k for k, _q in head] == ["execute", "fetchrow", "execute", "execute"], after
    assert head[0][1].startswith("BEGIN") and head[1][1] == ";" and head[2][1].startswith("ROLLBACK"), after
    assert head[3][1].startswith("BEGIN"), after
    binds = sent[4:-1]
    assert all(k == "bind" for k, _q in binds) and _kinds([q for _k, q in binds], FULL_AFTER), after
    assert sent[-1][0] == "execute" and sent[-1][1].strip().upper().startswith("COMMIT"), after
    prepared = [q for k, q in after if k == "prepare"]
    assert all(any(q == b for _k, b in binds) for q in prepared), after
