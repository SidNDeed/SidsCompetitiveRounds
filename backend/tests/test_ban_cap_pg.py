"""BAN-CAP-1 (the owner's ruling of 16 Nov 2026: every ban has a maximum length
of one year), server half: the bound is models.BAN_MAX_HOURS (8760 hours from
the ban row's start), every api writer of player_bans.expires_at takes its
value from main._ban_end_sql, and migration 418 holds the same bound in the
table (CHECK player_bans_max_one_year).

The tests that need no database run anywhere: the constant and 418's literal,
the census of the writers, the ban request's refusal through the route, the
bot's end line. The rest drive the real handlers against PostgreSQL in a case
schema built by the ladder harness (every migration's DDL replayed, 418's DO
included, so the case carries the CHECK), and run 418 and its rollback
through psql the way the migrate verb does (the file on stdin, ON_ERROR_STOP).

    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    LADDER_TEST_PG_OPTOUT=1   waives the live cases deliberately (else they FAIL)
    BAN_TEST_PSQL / CF_PSQL   the psql client (else PATH, else C:/pg16)

Every fix has a control (the test itself, red before the fix) and a mutant
that the test turns red for its stated reason only; each mutant is built
from the real source with one named replacement.
"""
import ast
import asyncio
import io
import itertools
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import inspect
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
SQL_DIR = os.path.normpath(os.path.join(HERE, "..", "sql"))
BOT = os.path.normpath(os.path.join(HERE, "..", "discord_bot.py"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import pydantic  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402

M418 = os.path.join(SQL_DIR, "418_player_bans_max_one_year.sql")
R418 = os.path.join(SQL_DIR, "rollback_418_player_bans_max_one_year.sql")
CONSTRAINT = "player_bans_max_one_year"
WANT_DEF = ("CHECK (((expires_at IS NOT NULL) AND (banned_at IS NOT NULL) AND "
            "(expires_at <= (banned_at + '%d:00:00'::interval))))" % models.BAN_MAX_HOURS)
CAP = timedelta(hours=models.BAN_MAX_HOURS)
INTERNAL_KEY = "ban-cap-internal-key"
_IDS = itertools.count(1)


def _sid():
    """A synthetic SteamID64-shaped key: 17 digits, numeric for 319's CHECK,
    below 76561197960265728, the first individual-account id."""
    return "765611904189%05d" % next(_IDS)


def _run(coro):
    return asyncio.run(coro)


# == no database ===============================================================

def test_the_bound_is_one_constant_written_in_hours():
    assert models.BAN_MAX_HOURS == 8760 == 365 * 24
    assert models.BAN_MAX_MINUTES == models.BAN_MAX_HOURS * 60
    assert models.BAN_MAX_DAYS == 365
    assert main.BAN_DURATION_MAX_MINUTES == models.BAN_MAX_MINUTES
    assert models.ban_cap_sql("c.t") == "(c.t + INTERVAL '8760 hours')"
    assert main._ban_end_sql(None, "c.t") == models.ban_cap_sql("c.t")
    assert main._ban_end_sql(30, "NOW()") == "(NOW() + make_interval(mins => CAST(:ban_minutes AS integer)))"


def _sql_code(path):
    """The file's SQL with its comments removed (the header names the bound
    in prose; only the statements are judged)."""
    src = io.open(path, encoding="utf-8").read()
    return "\n".join(line.split("--", 1)[0] for line in src.splitlines())


def test_418_spells_the_bound_from_the_constant_and_only_in_hours():
    """Ruling 1: the migration's literal is pinned to models.BAN_MAX_HOURS,
    and no interval of days, months or years appears in its statements."""
    code = _sql_code(M418)
    hours = re.findall(r"interval\s+'(\d+)\s+hours'", code, re.I)
    assert hours == [str(models.BAN_MAX_HOURS)] * 4, hours   # two backfills (one with its WHERE) and the CHECK
    # the post-check's expected definition, quoted inside a SQL string literal
    assert re.findall(r"''(\d+):00:00''::interval", code) == [str(models.BAN_MAX_HOURS)]
    assert not re.search(r"interval\s+'[^']*\b(day|days|mon|mons|month|months|year|years)\b", code, re.I)
    assert ("'%s'" % WANT_DEF.replace("'", "''")) in code
    for name in (M418, R418):
        assert CONSTRAINT in _sql_code(name), name


def _ban_route_client(monkeypatch):
    """admin_ban mounted alone: the route's own validation answer, with no
    database (a refusal is answered before the handler runs)."""
    app = FastAPI()
    app.add_api_route("/ban", main.admin_ban, methods=["POST"])
    reached = []

    async def no_db():
        reached.append("db")
        yield None

    async def no_slot():
        return None
    app.dependency_overrides[main.get_db] = no_db
    app.dependency_overrides[main._pc_writer_slot] = no_slot

    async def handler_reached(*a, **k):
        reached.append("handler")
        raise HTTPException(status_code=418, detail="handler reached")
    monkeypatch.setattr(main, "_require_admin", handler_reached)
    return TestClient(app, raise_server_exceptions=False), reached


def _over_maximum_check(client, reached):
    body = {"admin_steam_id": "1", "target_steam_id": "76561190418900001",
            "duration_minutes": models.BAN_MAX_MINUTES + 1}
    r = client.post("/ban", json=body)
    assert r.status_code == 422, (r.status_code, r.text)
    (err,) = r.json()["detail"]
    assert err["loc"][-1] == "duration_minutes", err
    assert "%d days" % models.BAN_MAX_DAYS in err["msg"] and str(models.BAN_MAX_MINUTES) in err["msg"], err
    assert "handler" not in reached, reached
    ok = client.post("/ban", json=dict(body, duration_minutes=models.BAN_MAX_MINUTES))
    assert ok.status_code == 418, (ok.status_code, ok.text)       # admitted: the handler ran


def test_the_route_refuses_one_minute_past_the_maximum_and_names_it_in_days(monkeypatch):
    client, reached = _ban_route_client(monkeypatch)
    _over_maximum_check(client, reached)


def test_mutant_the_request_without_its_maximum_admits_a_longer_ban(monkeypatch):
    """Mutant: _AdminBanReq whose validator never refuses. The check above
    then fails on its first assertion (the request is admitted, not 422)."""
    src = textwrap.dedent(inspect.getsource(main._AdminBanReq))
    old = "if v is not None and v > BAN_DURATION_MAX_MINUTES:"
    assert src.count(old) == 1
    ns = dict(vars(main))
    exec(compile(src.replace(old, "if False:"), "<mutant _AdminBanReq>", "exec"), ns)
    mutant_cls = ns["_AdminBanReq"]

    async def mutant_route(req: mutant_cls, _slot=None, db=None):
        await main._require_admin(db, req.admin_steam_id, "ban", req.target_steam_id, req.hmac_signature)
    app = FastAPI()
    app.add_api_route("/ban", mutant_route, methods=["POST"])
    reached = []

    async def handler_reached(*a, **k):
        reached.append("handler")
        raise HTTPException(status_code=418, detail="handler reached")
    monkeypatch.setattr(main, "_require_admin", handler_reached)
    with pytest.raises(AssertionError) as red:
        _over_maximum_check(TestClient(app, raise_server_exceptions=False), reached)
    assert "418" in str(red.value) or "status_code" in str(red.value) or "(418," in str(red.value), red.value


# -- the census of the writers ------------------------------------------------
#
# Ruling 9: every INSERT into player_bans and every UPDATE that sets
# player_bans.expires_at in backend/api names a value that comes from the one
# helper, main._ban_end_sql. Counted per function span (lesson 432): each
# statement root (the string constants and the calls they are concatenated
# with) that writes the table must hold a call of the helper, or a name whose
# every binding in the same function is a call of it. No module but models
# names the PlayerBan class, so no ORM row can carry another end.

HELPER = "_ban_end_sql"
CLIMB = (ast.BinOp, ast.JoinedStr, ast.FormattedValue, ast.Call)
INSERT_RX = re.compile(r"\bINSERT\s+INTO\s+player_bans\b", re.I)
UPDATE_RX = re.compile(r"\bUPDATE\s+player_bans\b", re.I)
SET_RX = re.compile(r"\bSET\b(.*?)(?:\bWHERE\b|\bRETURNING\b|\bFROM\b|$)", re.I | re.S)
SETS_END_RX = re.compile(r"(?<![\w.])expires_at\s*=(?!=)", re.I)
# (module, function) -> the writes it holds
WRITERS = {("main.py", "_apply_ban_core"): 1, ("main.py", "_ban_set_length_core"): 1}


def _parents(tree):
    out = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[child] = node
    return out


def _function(node, parents):
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    return None


def _root(node, parents):
    while node in parents and isinstance(parents[node], CLIMB):
        node = parents[node]
    return node


def _constants(root):
    return " ".join(n.value for n in ast.walk(root) if isinstance(n, ast.Constant) and isinstance(n.value, str))


def _is_helper_call(node):
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == HELPER


def _helper_names(fn):
    """Names every binding of which, in this function, is a call of the helper."""
    binds = {}
    for n in ast.walk(fn) if fn is not None else ():
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    binds.setdefault(t.id, []).append(_is_helper_call(n.value))
        elif isinstance(n, (ast.AugAssign, ast.AnnAssign, ast.NamedExpr)) and isinstance(n.target, ast.Name):
            binds.setdefault(n.target.id, []).append(False)
    return {k for k, v in binds.items() if v and all(v)}


def _writes_end(sql):
    if INSERT_RX.search(sql):
        return "insert"
    if UPDATE_RX.search(sql):
        m = SET_RX.search(sql)
        if m and SETS_END_RX.search(m.group(1)):
            return "update"
    return None


def census_source(module, src):
    """(writes, problems): writes maps (module, function) to the number of
    writes; problems names every write without the helper and every use of
    the PlayerBan class."""
    tree = ast.parse(src)
    parents = _parents(tree)
    writes, problems, seen = {}, [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "PlayerBan" and isinstance(node.ctx, ast.Load):
            problems.append(("PlayerBan used", module, node.lineno))
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        p = parents.get(node)
        if isinstance(p, ast.Expr):          # a docstring or a stray literal
            continue
        root = _root(node, parents)
        if id(root) in seen:
            continue
        seen.add(id(root))
        kind = _writes_end(_constants(root))
        if kind is None:
            continue
        fn = _function(node, parents)
        key = (module, fn.name if fn is not None else "<module>")
        writes[key] = writes.get(key, 0) + 1
        names = _helper_names(fn)
        ok = any(_is_helper_call(n) or (isinstance(n, ast.Name) and n.id in names) for n in ast.walk(root))
        if not ok:
            problems.append(("%s without %s" % (kind, HELPER), key, root.lineno))
    return writes, problems


def census_tree():
    writes, problems = {}, []
    for name in sorted(os.listdir(API)):
        if name.endswith(".py"):
            with open(os.path.join(API, name), encoding="utf-8") as fh:
                w, p = census_source(name, fh.read())
            writes.update(w)
            problems += [x for x in p if not (x[0] == "PlayerBan used" and name == "models.py")]
    return writes, problems


def test_every_writer_of_a_ban_end_takes_it_from_the_one_helper(capsys):
    writes, problems = census_tree()
    with capsys.disabled():
        print("\n[ban-cap census] writes %r" % sorted(writes.items()))
    assert not problems, problems
    assert writes == WRITERS, writes


PLANTED = {
    "a NULL insert": ('async def planted(db):\n'
                      '    await db.execute(text("INSERT INTO player_bans (steam_id, expires_at) VALUES (:s, NULL)"))\n'),
    "an end set by hand": ('async def planted(db):\n'
                           '    await db.execute(text("UPDATE player_bans pb SET expires_at = NOW() WHERE pb.id = :i"))\n'),
    "a name bound once to another value": (
        'async def planted(db, m):\n'
        '    end = _ban_end_sql(m, "NOW()")\n'
        '    end = "NULL"\n'
        '    await db.execute(text("UPDATE player_bans SET expires_at = " + end + " WHERE id = :i"))\n'),
    "the ORM class": ('def planted(db):\n'
                      '    db.add(PlayerBan(steam_id="1", reason="x", banned_by_steam_id="2"))\n'),
}


@pytest.mark.parametrize("shape", sorted(PLANTED))
def test_negative_control_each_planted_writer_is_reported(shape):
    _w, problems = census_source("planted.py", PLANTED[shape])
    assert problems and all(p[0] in ("insert without _ban_end_sql", "update without _ban_end_sql",
                                     "PlayerBan used") for p in problems), problems


def test_positive_control_a_covered_writer_is_silent_and_the_close_is_no_write():
    src = ('async def planted(db, m):\n'
           '    await db.execute(text("UPDATE player_bans SET unbanned_at = expires_at WHERE id = :i"))\n'
           '    await db.execute(text("INSERT INTO player_bans (id, expires_at) SELECT :i, " + _ban_end_sql(m, "c.t")))\n')
    writes, problems = census_source("planted.py", src)
    assert problems == [] and writes == {("planted.py", "planted"): 1}, (writes, problems)


# -- the bot's notice ---------------------------------------------------------

def _bot_nodes(*names):
    with open(BOT, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    out = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names:
            out.append(n)
        elif isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] in ([x] for x in names):
            out.append(n)
    return out


def _end_line_from(nodes):
    ns = {"datetime": datetime}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), BOT, "exec"), ns)
    return ns["_ban_end_line"]


def _every_notice_carries_its_end_line(line):
    for row in ({"expires_at": "2027-01-02T03:04:05Z"}, {"expires_at": None}, {"id": "x"},
                {"expires_at": "garbage"}, None):
        got = line(row)
        assert isinstance(got, str) and got.startswith("Ends: "), (row, got)
        assert "ermanent" not in got, (row, got)


def test_the_bot_notice_always_carries_its_end_line():
    nodes = _bot_nodes("_BAN_END_LINE_UNREAD", "_ban_end_line")
    assert len(nodes) == 2, nodes
    _every_notice_carries_its_end_line(_end_line_from(nodes))


def test_mutant_the_bot_line_left_out_for_a_null_end_is_reported():
    nodes = _bot_nodes("_BAN_END_LINE_UNREAD", "_ban_end_line")
    src = ast.unparse(nodes[1])
    old = "if raw is None:\n            return _BAN_END_LINE_UNREAD"
    assert src.count(old) == 1, src
    mutant = ast.parse(src.replace(old, "if raw is None:\n            return ''")).body
    with pytest.raises(AssertionError) as red:
        _every_notice_carries_its_end_line(_end_line_from([nodes[0]] + mutant))
    assert "'expires_at': None" in str(red.value), red.value


# == PostgreSQL ================================================================

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
    by the startup packet's search path: (exit code, stderr)."""
    psql = _psql_client()
    assert psql is not None, "no psql client found (set BAN_TEST_PSQL or put psql on PATH)"
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
    return p.returncode, p.stderr.decode("utf-8", "replace")


@pytest.fixture(scope="module")
def case():
    """A sealed case schema built by the harness (418's DO replayed with the
    rest), dropped under its census at the end."""
    lh._require_live_pg()
    built = {}

    async def build():
        c = harness.CaseSchema(lh.DSN, "ban_cap")
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


def _with_sm(schema, body):
    async def go():
        engine = harness.bound_engine(lh.DSN, schema)
        try:
            return await body(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()
    return _run(go())


@pytest.fixture
def admin_open(monkeypatch):
    """The admin routes' HMAC check passes (tested on its own elsewhere)."""
    async def _ok(*a, **k):
        return None
    monkeypatch.setattr(main, "_require_admin", _ok)
    monkeypatch.setenv("API_SECRET_KEY", INTERNAL_KEY)
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)


async def _player(db, sid):
    pid = uuid.uuid4()
    await lh._insert(db, "players", {"id": pid, "steam_id": sid, "display_name": "bc-" + sid[-4:]})
    return pid


async def _admin(db):
    sid = _sid()
    await lh._insert(db, "admin_users", {"steam_id": sid})
    return sid


async def _world(sm, n=1):
    async with sm() as db:
        admin = await _admin(db)
        targets = [_sid() for _ in range(n)]
        for t in targets:
            await _player(db, t)
        await db.commit()
    return admin, targets


async def _ban(sm, admin, target, **fields):
    req = main._AdminBanReq(admin_steam_id=admin, target_steam_id=target, reason="cap-test", **fields)
    async with sm() as db:
        return await main.admin_ban(req, _slot=None, db=db)


async def _row(db, target):
    return (await db.execute(text(
        "SELECT * FROM player_bans WHERE steam_id = :s ORDER BY banned_at DESC LIMIT 1"),
        {"s": target})).mappings().first()


def _replace_source(fn, pairs):
    """fn compiled from its real source with each (old, new) pair replaced
    once, in a copy of main's namespace: a mutant of exactly that edit."""
    src = textwrap.dedent(inspect.getsource(fn))
    for old, new in pairs:
        assert src.count(old) == 1, (fn.__name__, old, src.count(old))
        src = src.replace(old, new)
    node = ast.parse(src).body[0]
    node.decorator_list = []
    ns = dict(vars(main))
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<mutant %s>" % fn.__name__, "exec"), ns)
    return ns[node.name]


def test_the_case_carries_418s_check(case):
    async def body(sm):
        async with sm() as db:
            return (await db.execute(text(
                "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c"
                " WHERE c.conrelid = to_regclass('player_bans') AND c.conname = :n AND c.convalidated"),
                {"n": CONSTRAINT})).scalar()
    assert _with_sm(case, body) == WANT_DEF


# -- ruling 2: the ban route --------------------------------------------------

def test_a_ban_without_a_length_ends_at_its_start_plus_the_maximum(case, admin_open):
    async def body(sm):
        admin, (plain, explicit_null, longest) = await _world(sm, 3)
        out = {"plain": await _ban(sm, admin, plain),
               "null": await _ban(sm, admin, explicit_null, duration_minutes=None),
               "longest": await _ban(sm, admin, longest, duration_minutes=models.BAN_MAX_MINUTES)}
        async with sm() as db:
            out["rows"] = {k: await _row(db, t) for k, t in
                           (("plain", plain), ("null", explicit_null), ("longest", longest))}
        return out
    out = _with_sm(case, body)
    for k in ("plain", "null", "longest"):
        ans, row = out[k], out["rows"][k]
        assert ans["status"] == "banned", (k, ans)
        assert row["expires_at"] - row["banned_at"] == CAP, (k, row)
        assert ans["expires_at"] == main._ban_end_iso(row["expires_at"]), (k, ans, row)
        assert ans["seconds_left"] == models.BAN_MAX_HOURS * 3600, (k, ans)


def test_mutant_the_insert_without_its_end_is_refused_by_the_table(case, admin_open, monkeypatch):
    """Mutant: the new-ban INSERT with NULL in place of the helper's end. The
    case's CHECK refuses it, naming player_bans_max_one_year."""
    mutant = _replace_source(main._apply_ban_core,
                             [('_ban_end_sql(duration_minutes, "c.t")', '"NULL"')])
    monkeypatch.setattr(main, "_apply_ban_core", mutant)

    async def body(sm):
        admin, (target,) = await _world(sm)
        with pytest.raises(IntegrityError) as refused:
            await _ban(sm, admin, target)
        return str(refused.value)
    assert CONSTRAINT in _with_sm(case, body)


def test_the_new_row_carries_every_column_the_orm_row_carried(case, admin_open):
    """The INSERT names every column of player_bans, and its row matches,
    column by column, a row written by the ORM constructor the base used
    (with an end given, which the CHECK requires): same columns, same
    nullness, same Python types, a version-4 uuid id, the request's values."""
    async def body(sm):
        admin, (via_sql, via_orm) = await _world(sm, 2)
        await _ban(sm, admin, via_sql)
        async with sm() as db:
            db.add(models.PlayerBan(steam_id=via_orm, reason="cap-test", banned_by_steam_id=admin,
                                    expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
            await db.commit()
        async with sm() as db:
            cols = (await db.execute(text(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = current_schema() AND table_name = 'player_bans'"))).scalars().all()
            return admin, dict(await _row(db, via_sql)), dict(await _row(db, via_orm)), set(cols)
    admin, a, b, cols = _with_sm(case, body)
    src = inspect.getsource(main._apply_ban_core)
    m = re.search(r'INSERT INTO player_bans \(([^)]*)\)', src.replace('"\n        "', ""))
    named = {c.strip() for c in m.group(1).split(",")}
    assert named == cols == set(models.PlayerBan.__table__.columns.keys()), (named, cols)
    assert list(a) == list(b), (list(a), list(b))
    for col in a:
        assert (a[col] is None) == (b[col] is None), (col, a[col], b[col])
        assert type(a[col]) is type(b[col]), (col, type(a[col]), type(b[col]))
    assert a["id"].version == b["id"].version == 4
    assert (a["reason"], a["banned_by_steam_id"], a["unbanned_at"], a["unbanned_by_steam_id"]) == \
        ("cap-test", admin, None, None)
    assert a["banned_at"].tzinfo is not None and b["banned_at"].tzinfo is not None


def test_the_start_is_read_after_the_identity_lock(case, admin_open):
    """Integrator's condition 1a: the start (and so the end) is one clock read
    taken at the INSERT, after the identity lock. A ban that waited on the
    lock carries a start later than an instant read while it waited.
    Mutant: the same INSERT reading NOW() (the transaction's start)."""
    def drive(sm, target, admin):
        async def go():
            holder = await harness.connect_bound(lh.DSN, case)
            try:
                tr = holder.transaction()
                await tr.start()
                await holder.execute("SELECT pg_advisory_xact_lock(hashtext($1))", target)
                waiting = asyncio.ensure_future(_ban(sm, admin, target))
                await asyncio.sleep(0.6)
                assert not waiting.done(), "the ban did not wait on the identity lock"
                mid = await holder.fetchval("SELECT clock_timestamp()")
                await asyncio.sleep(0.05)
                await tr.commit()
                await waiting
            finally:
                await holder.close()
            async with sm() as db:
                return mid, await _row(db, target)
        return go()

    async def body(sm):
        admin, (t1, t2) = await _world(sm, 2)
        mid, row = await drive(sm, t1, admin)
        saved = main._apply_ban_core
        main._apply_ban_core = _replace_source(saved, [("SELECT clock_timestamp() AS t", "SELECT NOW() AS t")])
        try:
            mid_m, row_m = await drive(sm, t2, admin)
        finally:
            main._apply_ban_core = saved
        return mid, row, mid_m, row_m
    mid, row, mid_m, row_m = _with_sm(case, body)
    assert row["banned_at"] > mid, (row["banned_at"], mid)
    assert row["expires_at"] - row["banned_at"] == CAP
    # the mutant dates the ban before the instant read during its wait
    assert row_m["banned_at"] < mid_m, (row_m["banned_at"], mid_m)


# -- ruling 3: a length change -----------------------------------------------

def test_a_length_change_inside_the_bound_is_stored_and_past_it_is_refused(case, admin_open):
    async def body(sm):
        admin, (target,) = await _world(sm)
        await _ban(sm, admin, target)
        async with sm() as db:      # the ban began a day ago (start and end move together)
            await db.execute(text(
                "UPDATE player_bans SET banned_at = banned_at - INTERVAL '24 hours',"
                " expires_at = expires_at - INTERVAL '24 hours' WHERE steam_id = :s"), {"s": target})
            await db.commit()
            start = (await _row(db, target))["banned_at"]
        inside = await _ban(sm, admin, target, duration_minutes=models.BAN_MAX_MINUTES - 24 * 60 - 10)
        async with sm() as db:
            after_inside = await _row(db, target)
        with pytest.raises(HTTPException) as refused:
            await _ban(sm, admin, target, duration_minutes=models.BAN_MAX_MINUTES - 24 * 60 + 10)
        async with sm() as db:
            after_refusal = await _row(db, target)
            audits = (await db.execute(text(
                "SELECT count(*) FROM admin_actions WHERE target_steam_id = :s AND action = 'ban_length'"),
                {"s": target})).scalar()
        return start, inside, after_inside, refused.value, after_refusal, audits
    start, inside, after_inside, refused, after_refusal, audits = _with_sm(case, body)
    assert inside["status"] == "length_changed", inside
    assert after_inside["expires_at"] < start + CAP and inside["expires_at"] == main._ban_end_iso(after_inside["expires_at"])
    assert refused.status_code == 422, refused
    latest = main._ban_end_iso(start + CAP)
    assert latest in refused.detail and "%d days" % models.BAN_MAX_DAYS in refused.detail, refused.detail
    assert refused.detail.startswith("ban_length_past_maximum"), refused.detail
    assert dict(after_refusal) == dict(after_inside), "the refusal wrote the row"
    assert audits == 1, audits


def test_mutant_the_length_change_without_its_bound_is_refused_by_the_table(case, admin_open, monkeypatch):
    """Mutant: _ban_set_length_core without the bound in its UPDATE. The
    route no longer answers its own 422; the case's CHECK refuses the row."""
    mutant = _replace_source(main._ban_set_length_core,
                             [('"AND " + _new_end + " <= " + ban_cap_sql("pb.banned_at") + " "', '""')])
    monkeypatch.setattr(main, "_ban_set_length_core", mutant)

    async def body(sm):
        admin, (target,) = await _world(sm)
        await _ban(sm, admin, target)
        with pytest.raises(IntegrityError) as refused:
            await _ban(sm, admin, target, duration_minutes=models.BAN_MAX_MINUTES)
        return str(refused.value)
    assert CONSTRAINT in _with_sm(case, body)


# -- ruling 4: the moderation-case ban ----------------------------------------

async def _mod_case(sm):
    admin, (subject,) = await _world(sm)
    async with sm() as db:
        pid = (await db.execute(text("SELECT id FROM players WHERE steam_id = :s"), {"s": subject})).scalar()
        cid = uuid.uuid4()
        await lh._insert(db, "moderation_cases", {"id": cid, "kind": "report", "subject_player_id": pid,
                                                  "evidence": "{}", "bucket_key": "cap-" + subject})
        await db.commit()
    return admin, subject, str(cid)


async def _act_ban(sm, admin, cid):
    async with sm() as db:
        res = await main._moderation_case_act(db, case_id=cid, actor_steam_id=admin, action="ban",
                                              hours=None, reason="cap-case", via="test")
        await db.commit()
        return res


def test_the_moderation_case_ban_stores_its_start_plus_the_maximum(case, admin_open):
    async def body(sm):
        admin, subject, cid = await _mod_case(sm)
        res = await _act_ban(sm, admin, cid)
        async with sm() as db:
            return res, await _row(db, subject)
    res, row = _with_sm(case, body)
    assert res["resolution"] == "ban", res
    assert row["expires_at"] is not None and row["expires_at"] - row["banned_at"] == CAP, row


def test_mutant_a_helper_that_gives_no_end_fails_the_moderation_case_ban(case, admin_open, monkeypatch):
    """Mutant: the helper answering NULL for a ban without a length (the base's
    behaviour). The moderation-case ban is then refused by the case's CHECK."""
    real = main._ban_end_sql
    monkeypatch.setattr(main, "_ban_end_sql",
                        lambda d, start: "NULL" if d is None else real(d, start))

    async def body(sm):
        admin, _subject, cid = await _mod_case(sm)
        with pytest.raises(IntegrityError) as refused:
            await _act_ban(sm, admin, cid)
        return str(refused.value)
    assert CONSTRAINT in _with_sm(case, body)


# -- the notice feed: a row written before 418 ---------------------------------

def _feed_of_a_row_without_an_end(case, feed_fn):
    async def body(sm):
        admin, (target,) = await _world(sm)
        async with sm() as db:
            # the state before 418, in this transaction only (rolled back)
            await db.execute(text("ALTER TABLE player_bans DROP CONSTRAINT " + CONSTRAINT))
            await db.execute(text(
                "INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
                " VALUES (:s, 'pre-418', :a, NOW() - INTERVAL '3 days', NULL)"), {"s": target, "a": admin})
            start = (await _row(db, target))["banned_at"]
            feed = await feed_fn(since_id=None, limit=200, x_internal_key=INTERNAL_KEY, db=db)
            await db.rollback()
        return target, start, feed
    return _with_sm(case, body)


def test_the_feed_answers_the_end_418_gives_a_row_without_one(case, admin_open):
    target, start, feed = _feed_of_a_row_without_an_end(case, main.get_recent_bans)
    (row,) = [b for b in feed["bans"] if b["steam_id"] == target]
    assert row["expires_at"] == main._ban_end_iso(start + CAP), (row, start)


def test_mutant_the_feed_without_its_coalesce_answers_no_end(case, admin_open):
    mutant = _replace_source(main.get_recent_bans, [
        ('"       COALESCE(pb.expires_at, " + ban_cap_sql("pb.banned_at") + ") AS expires_at "',
         '"       pb.expires_at "')])
    target, _start, feed = _feed_of_a_row_without_an_end(case, mutant)
    (row,) = [b for b in feed["bans"] if b["steam_id"] == target]
    assert row["expires_at"] is None, row


# -- ruling 5: migration 418 through psql -------------------------------------

async def _snapshot(conn):
    return [tuple(r) for r in await conn.fetch(
        "SELECT id, expires_at FROM player_bans ORDER BY id")]


async def _constraint_def(conn):
    return await conn.fetchval(
        "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c"
        " WHERE c.conrelid = to_regclass('player_bans') AND c.conname = $1", CONSTRAINT)


def _notices(err):
    return [l.split("NOTICE:", 1)[1].strip() for l in err.splitlines() if "NOTICE:" in l]


def test_418_backfills_lowers_constrains_reruns_and_rolls_back(case):
    async def go():
        conn = await harness.connect_bound(lh.DSN, case)
        out = {}
        try:
            admin = _sid()
            await conn.execute("INSERT INTO admin_users (steam_id) VALUES ($1)", admin)
            rc, err = _psql_apply(case, R418)
            out["rollback_first"] = (rc, await _constraint_def(conn))
            ids = {}
            for name, began, end, lifted in (
                    ("null_open", "NOW() - INTERVAL '10 days'", "NULL", "NULL"),
                    ("null_closed", "NOW() - INTERVAL '20 days'", "NULL", "NOW() - INTERVAL '19 days'"),
                    ("long", "NOW() - INTERVAL '1 day'", "NOW() + INTERVAL '43800 hours'", "NULL"),
                    ("inside", "NOW() - INTERVAL '1 hour'", "NOW() + INTERVAL '720 hours'", "NULL")):
                ids[name] = await conn.fetchval(
                    "INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, banned_at, expires_at,"
                    " unbanned_at, unbanned_by_steam_id) VALUES ($1, 'mig', $2, %s, %s, %s, %s) RETURNING id"
                    % (began, end, lifted, "NULL" if lifted == "NULL" else "$2"), _sid(), admin)
            out["want_null"] = await conn.fetchval("SELECT count(*) FROM player_bans WHERE expires_at IS NULL")
            out["want_long"] = await conn.fetchval(
                "SELECT count(*) FROM player_bans WHERE expires_at > banned_at + INTERVAL '8760 hours'")
            inside_before = await conn.fetchval("SELECT expires_at FROM player_bans WHERE id = $1", ids["inside"])
            # the backfill is what lets the CHECK be added: a copy of 418
            # without its two UPDATEs is refused over the rows without an end
            src = io.open(M418, encoding="utf-8").read()
            cut = src[src.index("    UPDATE player_bans SET expires_at"):src.index("    RAISE NOTICE '418: % ban row(s) had no end")]
            with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as fh:
                fh.write(src.replace(cut, "    n_null := 0; n_long := 0;\n"))
                mutant_path = fh.name
            try:
                out["mutant"] = _psql_apply(case, mutant_path)
            finally:
                os.unlink(mutant_path)
            out["after_mutant"] = (await _constraint_def(conn),
                                   await conn.fetchval("SELECT count(*) FROM player_bans WHERE expires_at IS NULL"))
            out["first"] = _psql_apply(case, M418)
            out["after_first"] = (await _constraint_def(conn), await _snapshot(conn))
            out["rows"] = {k: dict(await conn.fetchrow(
                "SELECT banned_at, expires_at FROM player_bans WHERE id = $1", v)) for k, v in ids.items()}
            out["inside_before"] = inside_before
            out["again"] = _psql_apply(case, M418)
            out["after_again"] = (await _constraint_def(conn), await _snapshot(conn))
            # the constraint refuses a NULL end and an end one microsecond past the bound
            for label, end in (("null", "NULL"),
                               ("past", "TIMESTAMPTZ '2026-03-10 10:00:00+00' + INTERVAL '8760 hours'"
                                        " + INTERVAL '1 microsecond'")):
                try:
                    await conn.execute(
                        "INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
                        " VALUES ($1, 'mig', $2, TIMESTAMPTZ '2026-03-10 10:00:00+00', %s)" % end, _sid(), admin)
                    out["refused_" + label] = None
                except Exception as e:      # asyncpg CheckViolationError
                    out["refused_" + label] = (type(e).__name__, str(e))
            # a constraint of the name with another definition is refused, nothing applied
            out["rollback"] = _psql_apply(case, R418)
            out["after_rollback"] = (await _constraint_def(conn), await _snapshot(conn))
            out["rollback_again"] = _psql_apply(case, R418)
            await conn.execute("ALTER TABLE player_bans ADD CONSTRAINT %s CHECK (expires_at IS NOT NULL)" % CONSTRAINT)
            await conn.execute("UPDATE player_bans SET expires_at = expires_at + INTERVAL '10 hours'"
                               " WHERE id = $1", ids["long"])
            out["wrong"] = _psql_apply(case, M418)
            out["after_wrong"] = (await _constraint_def(conn), await conn.fetchval(
                "SELECT expires_at - banned_at FROM player_bans WHERE id = $1", ids["long"]))
            await conn.execute("ALTER TABLE player_bans DROP CONSTRAINT " + CONSTRAINT)
            out["last"] = _psql_apply(case, M418)
            out["after_last"] = await _constraint_def(conn)
        finally:
            await conn.close()
        return out
    out = _run(go())
    assert out["rollback_first"] == (0, None), out["rollback_first"]
    assert out["want_null"] >= 2 and out["want_long"] >= 1, out
    # mutant: no backfill, the ADD CONSTRAINT is refused and nothing changes
    rc, err = out["mutant"]
    assert rc != 0 and "is violated by some row" in err, (rc, err)
    assert out["after_mutant"] == (None, out["want_null"]), out["after_mutant"]
    rc, err = out["first"]
    assert rc == 0, err
    assert _notices(err) == [
        "418: %d ban row(s) had no end and now end at banned_at + 8760 hours" % out["want_null"],
        "418: %d ban row(s) ended later than banned_at + 8760 hours and were lowered to it" % out["want_long"]], err
    assert out["after_first"][0] == WANT_DEF
    rows = out["rows"]
    for k in ("null_open", "null_closed", "long"):
        assert rows[k]["expires_at"] - rows[k]["banned_at"] == CAP, (k, rows[k])
    assert rows["inside"]["expires_at"] == out["inside_before"], rows["inside"]
    rc, err = out["again"]
    assert rc == 0 and _notices(err) == ["418: player_bans_max_one_year is present; no row changed"], err
    assert out["after_again"] == out["after_first"]
    for label in ("null", "past"):
        got = out["refused_" + label]
        assert got is not None and CONSTRAINT in got[1], (label, got)
    rc, err = out["rollback"]
    assert rc == 0, err
    # the rollback drops the CHECK and does not restore a NULL end
    assert out["after_rollback"][0] is None and out["after_rollback"][1] == out["after_again"][1]
    assert out["rollback_again"][0] == 0, out["rollback_again"]
    rc, err = out["wrong"]
    assert rc != 0 and "not the validated CHECK 418 adds" in err, err
    # nothing applied: the wrong constraint stays and the long end was not lowered
    assert out["after_wrong"] == ("CHECK ((expires_at IS NOT NULL))", CAP + timedelta(hours=10)), out["after_wrong"]
    rc, err = out["last"]
    assert rc == 0 and out["after_last"] == WANT_DEF, (rc, err)


def test_the_checks_verdict_is_the_same_in_every_session_time_zone(case):
    """Ruling 1's control: the CHECK's bound is in hours, so its verdict does
    not depend on the session's time zone. A start three days after Los
    Angeles' 2026 daylight-saving change and an end 30 minutes past 8760
    hours: refused under UTC and under America/Los_Angeles alike, and the end
    exactly at the bound admitted under both. The control: the same bound
    written as 365 days gives different verdicts under the two zones (the
    2027 change comes later in March), so this test can see a day bound."""
    start = "TIMESTAMPTZ '2026-03-10 10:00:00+00'"
    ends = {"past": "TIMESTAMPTZ '2027-03-10 10:30:00+00'", "exact": "TIMESTAMPTZ '2027-03-10 10:00:00+00'"}

    async def go():
        out = {}
        for zone in ("UTC", "America/Los_Angeles"):
            conn = await harness.connect_bound(lh.DSN, case)
            try:
                await conn.execute("SET TIME ZONE '%s'" % zone)
                admin = _sid()
                await conn.execute("INSERT INTO admin_users (steam_id) VALUES ($1)", admin)
                for label, end in ends.items():
                    tr = conn.transaction()
                    await tr.start()
                    try:
                        await conn.execute(
                            "INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
                            " VALUES ($1, 'tz', $2, %s, %s)" % (start, end), _sid(), admin)
                        out[(zone, label)] = "admitted"
                    except Exception as e:
                        out[(zone, label)] = "refused" if CONSTRAINT in str(e) else repr(e)
                    finally:
                        await tr.rollback()
                out[(zone, "days")] = await conn.fetchval(
                    "SELECT %s <= %s + INTERVAL '365 days'" % (ends["past"], start))
            finally:
                await conn.close()
        return out
    out = _run(go())
    for zone in ("UTC", "America/Los_Angeles"):
        assert (out[(zone, "past")], out[(zone, "exact")]) == ("refused", "admitted"), out
    assert (out[("UTC", "days")], out[("America/Los_Angeles", "days")]) == (False, True), out
