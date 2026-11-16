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


def _psql_args(schema, settings=(), appname=None):
    """psql with ON_ERROR_STOP, bound to the case schema by the startup
    packet's search path; `settings` are further session settings given the
    same way, from OUTSIDE the file (name, value). A later setting of the
    same name wins; a space in a value is escaped as PGOPTIONS reads it."""
    psql = _psql_client()
    assert psql is not None, "no psql client found (set BAN_TEST_PSQL or put psql on PATH)"
    u = urlparse(lh.DSN)

    def esc(v):
        return v.replace("\\", "\\\\").replace(" ", "\\ ")
    opts = ["-c search_path=%s" % schema] + ["-c %s=%s" % (k, esc(v)) for k, v in settings]
    env = dict(os.environ, PGOPTIONS=" ".join(opts))
    if appname:
        env["PGAPPNAME"] = appname
    if u.password:
        env["PGPASSWORD"] = u.password
    args = [psql, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-h", u.hostname or "localhost",
            "-p", str(u.port or 5432), "-d", u.path.lstrip("/")]
    if u.username:
        args += ["-U", u.username]
    return args, env


def _psql_apply(schema, path, settings=()):
    """The file on psql's stdin: (exit code, stderr)."""
    args, env = _psql_args(schema, settings)
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
        " WHERE c.conrelid = to_regclass('player_bans')::oid AND c.conname = $1", CONSTRAINT)


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


# -- 418 under any session settings, and two first runs at once ---------------

INTERVAL_STYLES = ("postgres", "postgres_verbose", "sql_standard", "iso_8601")
PIN_LINE = "SET LOCAL IntervalStyle = 'postgres';\n"
REREAD = ("    EXECUTE 'LOCK TABLE player_bans IN ACCESS EXCLUSIVE MODE';\n"
          "    present := EXISTS (SELECT 1 FROM pg_constraint c\n"
          "                        WHERE c.conrelid = tbl::oid AND c.conname = 'player_bans_max_one_year');\n")
REREAD_CUT = "    EXECUTE 'LOCK TABLE player_bans IN ACCESS EXCLUSIVE MODE';\n"


def _m418_copy(old, new):
    """A temporary copy of 418 with `old` (present once) replaced: a mutant
    of exactly that edit. The caller unlinks it."""
    src = io.open(M418, encoding="utf-8").read()
    assert src.count(old) == 1, (old, src.count(old))
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as fh:
        fh.write(src.replace(old, new))
        return fh.name


async def _styles_run(case, path):
    """The file at `path` under each IntervalStyle, set for the session from
    OUTSIDE the file (the startup packet), as a role or database setting
    would set it: rollback, apply, apply again, rollback twice; then 418 once
    more under the default style, so the case ends with its CHECK."""
    conn = await harness.connect_bound(lh.DSN, case)
    out = {}
    try:
        for style in INTERVAL_STYLES:
            st = (("IntervalStyle", style),)
            out[(style, "rollback")] = _psql_apply(case, R418, st)
            out[(style, "absent")] = await _constraint_def(conn)
            snap0 = await _snapshot(conn)
            out[(style, "first")] = _psql_apply(case, path, st)
            out[(style, "def")] = await _constraint_def(conn)
            snap = await _snapshot(conn)
            out[(style, "unchanged_on_refusal")] = snap == snap0
            out[(style, "again")] = _psql_apply(case, path, st)
            out[(style, "same")] = (await _constraint_def(conn), await _snapshot(conn)) == (out[(style, "def")], snap)
            out[(style, "rollback2")] = _psql_apply(case, R418, st)
            out[(style, "rollback3")] = _psql_apply(case, R418, st)
            out[(style, "after_rollbacks")] = await _constraint_def(conn)
    finally:
        await conn.close()
    out["last"] = _psql_apply(case, M418)
    return out


def test_418_applies_under_every_interval_style(case):
    """H1 of bancap-r1. 418's post-check compares pg_get_constraintdef's text,
    which prints the CHECK's interval constant by IntervalStyle. Under each of
    the four styles, set from outside the file, 418 applies, applies again as
    a no-op, and the rollback (which compares no deparsed text) drops and
    drops again."""
    out = _run(_styles_run(case, M418))
    for style in INTERVAL_STYLES:
        for step in ("rollback", "rollback2", "rollback3"):
            assert out[(style, step)][0] == 0, (style, step, out[(style, step)])
        assert out[(style, "absent")] is None, style
        rc, err = out[(style, "first")]
        assert rc == 0, (style, err)
        assert out[(style, "def")] == WANT_DEF, (style, out[(style, "def")])
        rc, err = out[(style, "again")]
        assert rc == 0 and _notices(err) == ["418: player_bans_max_one_year is present; no row changed"], (style, err)
        assert out[(style, "same")] is True, style
        assert out[(style, "after_rollbacks")] is None, style
    assert out["last"][0] == 0, out["last"]


def test_mutant_418_without_its_interval_style_pin_is_refused_under_iso_8601(case):
    """Mutant: 418 without its SET LOCAL IntervalStyle line. Under iso_8601
    the post-check reads the definition as PT8760H and refuses, and the
    refusal leaves nothing behind (no CHECK, no row changed); under the
    postgres style the same copy applies, so the refusal has that one
    reason."""
    path = _m418_copy(PIN_LINE, "")
    try:
        out = _run(_styles_run(case, path))
    finally:
        os.unlink(path)
    rc, err = out[("iso_8601", "first")]
    assert rc != 0 and "PT8760H" in err and "not the validated CHECK 418 adds" in err, (rc, err)
    assert out[("iso_8601", "def")] is None and out[("iso_8601", "unchanged_on_refusal")] is True, out
    rc, err = out[("postgres", "first")]
    assert rc == 0 and out[("postgres", "def")] == WANT_DEF, (rc, err)
    assert out["last"][0] == 0, out["last"]


async def _rows_with_xmin(conn):
    return [tuple(r) for r in await conn.fetch(
        "SELECT id, expires_at, xmin::text FROM player_bans ORDER BY id")]


async def _wait_for_lock_wait(obs, appname, limit_s=10.0):
    """True once the session named `appname` waits on a lock."""
    deadline = asyncio.get_running_loop().time() + limit_s
    while asyncio.get_running_loop().time() < deadline:
        if await obs.fetchval(
                "SELECT count(*) FROM pg_stat_activity WHERE application_name = $1"
                " AND wait_event_type = 'Lock'", appname):
            return True
        await asyncio.sleep(0.05)
    return False


async def _two_first_runs(case, path, release, b_settings=()):
    """Session A holds player_bans' ACCESS EXCLUSIVE lock in an open
    transaction while session B (psql, the file at `path`, under
    `b_settings`) starts 418 and waits. With `release`, A then does what
    418's first run does (the backfill and the ADD CONSTRAINT), reads the
    rows as it leaves them ON ITS OWN CONNECTION before its COMMIT (any other
    reader waits for B's lock and would see B's changes too: bancap-r2's
    MEDIUM), and commits inside B's 5 s lock timeout; without it, A holds on
    until B has ended and then rolls back."""
    a = await harness.connect_bound(lh.DSN, case)
    obs = await harness.connect_bound(lh.DSN, case)
    out = {}
    try:
        out["rollback"] = _psql_apply(case, R418)
        admin = _sid()
        await a.execute("INSERT INTO admin_users (steam_id) VALUES ($1)", admin)
        out["null_id"] = await a.fetchval(
            "INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, expires_at)"
            " VALUES ($1, 'race', $2, NULL) RETURNING id", _sid(), admin)
        out["before"] = await _rows_with_xmin(a)
        tr = a.transaction()
        await tr.start()
        await a.execute("LOCK TABLE player_bans IN ACCESS EXCLUSIVE MODE")
        appname = "bancap_b_%s" % uuid.uuid4().hex[:8]
        args, env = _psql_args(case, b_settings, appname=appname)
        with open(path, "rb") as fh:
            b = subprocess.Popen(args, stdin=fh, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out["b_waited"] = await _wait_for_lock_wait(obs, appname)
            if release:
                await a.execute("UPDATE player_bans SET expires_at = banned_at + interval '8760 hours'"
                                " WHERE expires_at IS NULL")
                await a.execute("ALTER TABLE player_bans ADD CONSTRAINT player_bans_max_one_year"
                                " CHECK (expires_at IS NOT NULL AND banned_at IS NOT NULL"
                                " AND expires_at <= banned_at + interval '8760 hours')")
                out["after_a"] = await _rows_with_xmin(a)
                await tr.commit()
                _o, e = await asyncio.get_running_loop().run_in_executor(None, lambda: b.communicate(timeout=60))
            else:
                _o, e = await asyncio.get_running_loop().run_in_executor(None, lambda: b.communicate(timeout=60))
                await tr.rollback()
                out["after_a"] = await _rows_with_xmin(obs)
        except BaseException:
            b.kill()
            raise
        out["b"] = (b.returncode, e.decode("utf-8", "replace"))
        out["after_b"] = await _rows_with_xmin(obs)
        out["def"] = await _constraint_def(obs)
    finally:
        await a.close()
        await obs.close()
    out["restore"] = _psql_apply(case, M418)
    return out


def test_two_first_runs_of_418_at_once_end_as_two_in_sequence(case):
    """H2 of bancap-r1. A first run of 418 that finds the constraint absent
    and then waits for the table's lock reads the constraint again under the
    lock: when another session added it meanwhile, this run ends with exit 0
    and changes no row (every row's xmin as session A left it)."""
    out = _run(_two_first_runs(case, M418, release=True))
    assert out["rollback"][0] == 0, out["rollback"]
    assert out["b_waited"] is True, "session B never waited on the lock"
    rc, err = out["b"]
    assert rc == 0, err
    assert _notices(err) == ["418: player_bans_max_one_year is present; no row changed"], err
    assert out["after_b"] == out["after_a"], "session B changed a row"
    assert out["after_a"] != out["before"], "session A's backfill changed nothing"
    assert out["def"] == WANT_DEF, out["def"]
    assert out["restore"][0] == 0, out["restore"]


def test_control_a_first_run_held_out_ends_at_its_lock_timeout_with_nothing_changed(case):
    """The control: session A never releases. B gives up at its 5 s lock
    timeout, and nothing is applied: no constraint, the row without an end
    still without one, every row as before."""
    out = _run(_two_first_runs(case, M418, release=False))
    assert out["b_waited"] is True, "session B never waited on the lock"
    rc, err = out["b"]
    assert rc != 0 and "lock timeout" in err, (rc, err)
    assert out["def"] is None, out["def"]
    assert out["after_b"] == out["before"], "a row changed"
    assert any(r[0] == out["null_id"] and r[1] is None for r in out["after_b"]), out["after_b"]
    assert out["restore"][0] == 0, out["restore"]


def test_mutant_418_without_its_reread_under_the_lock_fails_the_second_run(case):
    """Mutant: the re-read under the lock removed (418 as it stood at
    30caa3b4 in this respect). B acts on its first read, backfills nothing,
    and its ADD CONSTRAINT is refused because the constraint exists."""
    path = _m418_copy(REREAD, REREAD_CUT)
    try:
        out = _run(_two_first_runs(case, path, release=True))
    finally:
        os.unlink(path)
    assert out["b_waited"] is True, "session B never waited on the lock"
    rc, err = out["b"]
    assert rc != 0 and "already exists" in err and CONSTRAINT in err, (rc, err)
    assert out["after_b"] == out["after_a"] and out["def"] == WANT_DEF, out


async def _two_rollbacks(case, path):
    """The same two sessions for the rollback file: the CHECK present, A
    holds the table's lock, B (the file at `path`) reads the CHECK present
    and waits, A drops it and commits."""
    out = {"apply": _psql_apply(case, M418)}
    a = await harness.connect_bound(lh.DSN, case)
    obs = await harness.connect_bound(lh.DSN, case)
    try:
        out["before"] = await _rows_with_xmin(a)
        tr = a.transaction()
        await tr.start()
        await a.execute("LOCK TABLE player_bans IN ACCESS EXCLUSIVE MODE")
        appname = "bancap_r_%s" % uuid.uuid4().hex[:8]
        args, env = _psql_args(case, appname=appname)
        with open(path, "rb") as fh:
            b = subprocess.Popen(args, stdin=fh, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out["b_waited"] = await _wait_for_lock_wait(obs, appname)
            await a.execute("ALTER TABLE player_bans DROP CONSTRAINT " + CONSTRAINT)
            await tr.commit()
            _o, e = await asyncio.get_running_loop().run_in_executor(None, lambda: b.communicate(timeout=60))
        except BaseException:
            b.kill()
            raise
        out["b"] = (b.returncode, e.decode("utf-8", "replace"))
        out["after_b"] = await _rows_with_xmin(obs)
        out["def"] = await _constraint_def(obs)
    finally:
        await a.close()
        await obs.close()
    out["restore"] = _psql_apply(case, M418)
    return out


def test_two_rollbacks_of_418_at_once_both_end_without_an_error(case):
    """The rollback file's own precondition: it reads the CHECK present
    without a lock; its DROP asks again under the lock its ALTER takes, so a
    run that waited while another dropped the CHECK ends with exit 0."""
    out = _run(_two_rollbacks(case, R418))
    assert out["apply"][0] == 0, out["apply"]
    assert out["b_waited"] is True, "session B never waited on the lock"
    rc, err = out["b"]
    assert rc == 0, err
    assert out["def"] is None and out["after_b"] == out["before"], out
    assert out["restore"][0] == 0, out["restore"]


def test_mutant_the_rollback_dropping_without_if_exists_fails_the_second_run(case):
    """Mutant: the rollback's DROP without IF EXISTS (the file as it stood at
    30caa3b4). B acts on its unlocked read and fails on the missing CHECK."""
    src = io.open(R418, encoding="utf-8").read()
    old = "DROP CONSTRAINT IF EXISTS player_bans_max_one_year"
    assert src.count(old) == 1
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as fh:
        fh.write(src.replace(old, "DROP CONSTRAINT player_bans_max_one_year"))
        path = fh.name
    try:
        out = _run(_two_rollbacks(case, path))
    finally:
        os.unlink(path)
    assert out["b_waited"] is True, "session B never waited on the lock"
    rc, err = out["b"]
    assert rc != 0 and "does not exist" in err and CONSTRAINT in err, (rc, err)
    assert out["def"] is None, out["def"]


# -- bancap-r2: every session setting 418's result could follow ---------------
#
# One class: the post-check compares deparsed text, and the parse, the
# deparse and the two-session promise follow session settings. 418 pins its
# whole environment (BEGIN ISOLATION LEVEL READ COMMITTED; IntervalStyle and
# quote_all_identifiers in the block at the head of its transaction; the
# search path at the head of the DO, once the table is named), and ONE
# generated test runs the real file under each setting below, set from
# OUTSIDE the file (the startup packet) as a role or database setting would
# set it, and asserts the constraint's BEHAVIOUR, not only its text.
# Objects in another schema on the session's path enter as settings do, so
# the list carries them too: an operator planted in the table's own schema
# (PLANTS), which the pinned path keeps second. pg_catalog first settles an
# operator only against one with the same argument types: operator
# resolution takes an exact match of the argument types before any that
# needs a coercion, wherever it sits on the path, so every comparison in
# the files is written on types pg_catalog holds an exact operator for.
# Each entry: (id, settings, the plant (a key of PLANTS, or None), what the
# file must do, why the setting does or does not enter). "{case}" in a value
# is the case schema, which stands for public.

PRESENT = "418: player_bans_max_one_year is present; no row changed"
SESSION_SETTINGS = (
    ("intervalstyle-postgres", (("IntervalStyle", "postgres"),), None, "applies",
     "enters: the post-check's text prints the CHECK's interval by IntervalStyle; pinned"),
    ("intervalstyle-postgres_verbose", (("IntervalStyle", "postgres_verbose"),), None, "applies",
     "enters, as above"),
    ("intervalstyle-sql_standard", (("IntervalStyle", "sql_standard"),), None, "applies",
     "enters, as above"),
    ("intervalstyle-iso_8601", (("IntervalStyle", "iso_8601"),), None, "applies",
     "enters, as above"),
    ("quote_all_identifiers-on", (("quote_all_identifiers", "on"),), None, "applies",
     "enters: the deparser then quotes every column name; pinned off"),
    ("search_path-case_pg_catalog", (("search_path", "{case},pg_catalog"),), None, "applies",
     "enters: it decides which <= the CHECK is parsed with and whether the deparser "
     "prints that operator qualified; pinned in the DO once the table is named"),
    ("search_path-case_pg_catalog-operator", (("search_path", "{case},pg_catalog"),), "le_true", "applies",
     "the same path with a <= on two timestamptz values in the table's schema that answers true"),
    ("default_transaction_isolation-repeatable_read",
     (("default_transaction_isolation", "repeatable read"),), None, "applies",
     "enters: the re-read under the lock sees another run's commit only at read committed; "
     "pinned by BEGIN ISOLATION LEVEL READ COMMITTED"),
    ("default_transaction_isolation-serializable",
     (("default_transaction_isolation", "serializable"),), None, "applies",
     "enters, as above"),
    ("default_transaction_read_only-on", (("default_transaction_read_only", "on"),), None, "refused",
     "enters as a refusal: the BEGIN inherits it, the first write (the lock) fails inside "
     "the transaction, and nothing is applied"),
    ("datestyle-sql_dmy", (("DateStyle", "SQL, DMY"),), None, "applies",
     "does not enter: the file holds no date or time constant"),
    ("timezone-los_angeles", (("TimeZone", "America/Los_Angeles"),), None, "applies",
     "does not enter: the bound is in hours, which no time zone stretches"),
    ("standard_conforming_strings-off", (("standard_conforming_strings", "off"),), None, "applies",
     "does not enter: no string literal in the file holds a backslash"),
    ("extra_float_digits--15", (("extra_float_digits", "-15"),), None, "applies",
     "does not enter: the file holds no floating-point value"),
    ("extra_float_digits-3", (("extra_float_digits", "3"),), None, "applies",
     "does not enter, as above"),
    ("operator-eq_oid_regclass-true", (), "eq_oid_regclass_true", "applies",
     "an = on (oid, regclass) in the table's schema: an exact match for a comparison of "
     "a catalog oid with a regclass, which pg_catalog does not hold; the files cast to oid"),
    ("operator-eq_oid_regclass-false", (), "eq_oid_regclass_false", "applies", "as above, answering false"),
    ("operator-eq_oid_regtype-true", (), "eq_oid_regtype_true", "applies",
     "an = on (oid, regtype): the column-type checks; the files cast to oid"),
    ("operator-eq_oid_regtype-false", (), "eq_oid_regtype_false", "applies", "as above, answering false"),
    ("operator-eq_regclass_regclass-true", (), "eq_regclass_regclass_true", "applies",
     "an = on (regclass, regclass): the identity check; the files cast to oid"),
    ("operator-eq_regclass_regclass-false", (), "eq_regclass_regclass_false", "applies",
     "as above, answering false"),
    ("search_path-case_pg_catalog-eq_name_name-true", (("search_path", "{case},pg_catalog"),),
     "eq_name_name_true", "applies",
     "an = on (name, name) with the table's schema ahead of pg_catalog on the session's path: "
     "the constraint-name reads; pg_catalog holds the exact operator and the pinned path "
     "puts it first"),
    ("search_path-case_pg_catalog-eq_name_name-false", (("search_path", "{case},pg_catalog"),),
     "eq_name_name_false", "applies", "as above, answering false"),
)


def _eq_plant(left, right, answer):
    fn = "bancap_eq_%s_%s_%s" % (left, right, answer)
    return (("CREATE FUNCTION {s}.%s(%s, %s) RETURNS boolean LANGUAGE plpgsql IMMUTABLE"
             " AS $f$BEGIN RETURN %s; END$f$" % (fn, left, right, answer),
             "CREATE OPERATOR {s}.= (LEFTARG = %s, RIGHTARG = %s, FUNCTION = {s}.%s)" % (left, right, fn)),
            ("DROP OPERATOR IF EXISTS {s}.= (%s, %s)" % (left, right),
             "DROP FUNCTION IF EXISTS {s}.%s(%s, %s)" % (fn, left, right)))


# key: (CREATE statements, DROP statements); "{s}" is the quoted case schema.
# Every plant is removed before the case's own cleanup runs, but for the
# `<=`, which a CHECK built by a mutant may depend on: it goes after the
# cleanup has dropped that CHECK (PLANT_AFTER_CLEANUP).
PLANTS = {
    "le_true": (("CREATE FUNCTION {s}.bancap_always_true(timestamptz, timestamptz) RETURNS boolean"
                 " LANGUAGE plpgsql IMMUTABLE AS $f$BEGIN RETURN true; END$f$",
                 "CREATE OPERATOR {s}.<= (LEFTARG = timestamptz, RIGHTARG = timestamptz,"
                 " FUNCTION = {s}.bancap_always_true)"),
                ("DROP OPERATOR IF EXISTS {s}.<= (timestamptz, timestamptz)",
                 "DROP FUNCTION IF EXISTS {s}.bancap_always_true(timestamptz, timestamptz)")),
}
for _l, _r in (("oid", "regclass"), ("oid", "regtype"), ("regclass", "regclass"), ("name", "name")):
    for _a in ("true", "false"):
        PLANTS["eq_%s_%s_%s" % (_l, _r, _a)] = _eq_plant(_l, _r, _a)
PLANT_AFTER_CLEANUP = {"le_true"}
BEGIN_LINE = "BEGIN ISOLATION LEVEL READ COMMITTED;\n"
QAI_LINE = "SET LOCAL quote_all_identifiers = off;\n"
PATH_LINE = ("  PERFORM pg_catalog.set_config('search_path', "
             "pg_catalog.format('pg_catalog, %I, pg_temp', sch), true);\n")
PATH_LINE_NO_SCHEMA = ("  PERFORM pg_catalog.set_config('search_path', "
                       "pg_catalog.format('pg_catalog, pg_temp', sch), true);\n")
PRESENT_LINE = "    RAISE NOTICE '%s';\n" % PRESENT
NOOP_UPDATE = "    UPDATE player_bans SET expires_at = expires_at;\n"
REPEATABLE_READ = (("default_transaction_isolation", "repeatable read"),)
OPERATOR_PATH = (("search_path", "{case},pg_catalog"),)


def _settings_for(case, settings):
    return tuple((k, v.format(case=case)) for k, v in settings)


async def _plant(conn, case, key):
    """The plant PLANTS[key] in the table's schema (no-op for None)."""
    if key:
        for stmt in PLANTS[key][0]:
            await conn.execute(stmt.replace("{s}", harness.quoted(case)))


async def _unplant(conn, case, key):
    if key:
        for stmt in PLANTS[key][1]:
            await conn.execute(stmt.replace("{s}", harness.quoted(case)))


# A second table in the case schema carrying a CHECK of the same NAME and
# definition, and one row: a comparison that stops naming player_bans alone
# (an `=` on (oid, regclass) that answers true) reads this one instead.
DECOY = "bancap_decoy"
DECOY_CREATE = ("CREATE TABLE {s}.%s (banned_at timestamptz NOT NULL DEFAULT now(),"
                " expires_at timestamptz, CONSTRAINT player_bans_max_one_year CHECK"
                " (expires_at IS NOT NULL AND banned_at IS NOT NULL"
                " AND expires_at <= banned_at + interval '8760 hours'))" % DECOY)


async def _decoy_rows(conn):
    return [tuple(r) for r in await conn.fetch(
        "SELECT banned_at, expires_at, xmin::text FROM %s ORDER BY banned_at" % DECOY)]


async def _verdicts(conn, admin):
    """The CHECK's behaviour: (an end one microsecond past the cap, an end at
    the cap, a NULL end), each 'refused' or 'admitted', each in a
    transaction rolled back."""
    start = "TIMESTAMPTZ '2026-03-10 10:00:00+00'"
    cap = "%s + INTERVAL '%d hours'" % (start, models.BAN_MAX_HOURS)
    got = []
    for end in (cap + " + INTERVAL '1 microsecond'", cap, "NULL"):
        tr = conn.transaction()
        await tr.start()
        try:
            await conn.execute(
                "INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
                " VALUES ($1, 'verdict', $2, %s, %s)" % (start, end), _sid(), admin)
            got.append("admitted")
        except Exception as e:      # asyncpg CheckViolationError
            got.append("refused" if CONSTRAINT in str(e) else repr(e))
        finally:
            await tr.rollback()
    return tuple(got)


async def _apply_under(case, path, settings, plant):
    """The file at `path` under `settings`: with the CHECK absent and one
    row without an end, a first apply and a second apply, then the CHECK's
    verdicts, with the decoy table beside it and the plant in place from
    the first apply on. The plant, the decoy and the CHECK are removed again
    at the end (the case's census refuses an object the build did not
    leave), and 418 is applied once more under the default session."""
    st = _settings_for(case, settings)
    s = harness.quoted(case)
    conn = await harness.connect_bound(lh.DSN, case)
    out = {}
    planted = False
    try:
        out["rollback"] = _psql_apply(case, R418)
        admin = _sid()
        await conn.execute("INSERT INTO admin_users (steam_id) VALUES ($1)", admin)
        await conn.execute("INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, expires_at)"
                           " VALUES ($1, 'settings', $2, NULL)", _sid(), admin)
        await conn.execute(DECOY_CREATE.replace("{s}", s))
        await conn.execute("INSERT INTO %s (expires_at) VALUES (now() + interval '1 hour')" % DECOY)
        out["decoy_before"] = await _decoy_rows(conn)
        out["before"] = await _rows_with_xmin(conn)
        planted = True
        await _plant(conn, case, plant)
        out["first"] = _psql_apply(case, path, st)
        out["def"] = await _constraint_def(conn)
        out["after_first"] = await _rows_with_xmin(conn)
        out["again"] = _psql_apply(case, path, st)
        out["after_again"] = (await _constraint_def(conn), await _rows_with_xmin(conn))
        out["verdicts"] = await _verdicts(conn, admin)
        out["decoy_after"] = await _decoy_rows(conn)
    finally:
        try:
            if planted and plant not in PLANT_AFTER_CLEANUP:
                await _unplant(conn, case, plant)
            await conn.execute("DROP TABLE IF EXISTS %s.%s" % (s, DECOY))
            out["cleanup"] = _psql_apply(case, R418)
            if planted and plant in PLANT_AFTER_CLEANUP:
                await _unplant(conn, case, plant)
        finally:
            await conn.close()
    out["restore"] = _psql_apply(case, M418)
    return out


@pytest.mark.parametrize("entry", SESSION_SETTINGS, ids=[e[0] for e in SESSION_SETTINGS])
def test_418_under_each_session_setting_applies_once_and_the_check_holds(case, entry):
    """The generated test. Under each setting of SESSION_SETTINGS: the first
    apply ends rc 0 with the CHECK 418 adds; a second apply ends rc 0 with
    the "present" notice and changes no row (every row's xmin as the first
    left it); and the CHECK refuses an end one microsecond past the cap,
    admits an end at the cap and refuses a NULL end. The one exception,
    default_transaction_read_only on: the file ends with an error and
    nothing is applied (no CHECK, no row changed)."""
    name, settings, plant, want, _why = entry
    out = _run(_apply_under(case, M418, settings, plant))
    assert out["rollback"][0] == 0, out["rollback"]
    rc, err = out["first"]
    if want == "refused":
        assert rc != 0 and "read-only transaction" in err, (name, rc, err)
        assert out["def"] is None and out["after_first"] == out["before"], (name, out)
    else:
        assert rc == 0, (name, err)
        assert out["def"] == WANT_DEF, (name, out["def"])
        rc, err = out["again"]
        assert rc == 0 and _notices(err) == [PRESENT], (name, err)
        assert out["after_again"] == (WANT_DEF, out["after_first"]), (name, "the second apply changed a row")
        assert out["verdicts"] == ("refused", "admitted", "refused"), (name, out["verdicts"])
    assert out["decoy_after"] == out["decoy_before"], (name, "a row of another table changed")
    assert out["cleanup"][0] == 0 and out["restore"][0] == 0, (name, out["cleanup"], out["restore"])


async def _operator_case(case, path):
    """bancap-r2's first input: a `<=` in the table's schema that always
    answers true, and the path {case}, pg_catalog. (1) A first apply of the
    file at `path`, then the CHECK's verdicts. (2) A correct CHECK already
    standing, added in a session whose path reaches pg_catalog's operator
    first, then the file applied: its exit, its notices, whether a row
    changed."""
    st = _settings_for(case, OPERATOR_PATH)
    conn = await harness.connect_bound(lh.DSN, case)
    out = {}
    try:
        await _plant(conn, case, "le_true")
        out["rollback"] = _psql_apply(case, R418)
        admin = _sid()
        await conn.execute("INSERT INTO admin_users (steam_id) VALUES ($1)", admin)
        await conn.execute("INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, expires_at)"
                           " VALUES ($1, 'operator', $2, NULL)", _sid(), admin)
        out["first"] = _psql_apply(case, path, st)
        out["first_verdicts"] = await _verdicts(conn, admin)
        out["rollback2"] = _psql_apply(case, R418)
        await conn.execute("UPDATE player_bans SET expires_at = banned_at + interval '8760 hours'"
                           " WHERE expires_at IS NULL")
        await conn.execute("ALTER TABLE player_bans ADD CONSTRAINT player_bans_max_one_year"
                           " CHECK (expires_at IS NOT NULL AND banned_at IS NOT NULL"
                           " AND expires_at <= banned_at + interval '8760 hours')")
        out["standing_def"] = await _constraint_def(conn)
        out["before"] = await _rows_with_xmin(conn)
        out["on_standing"] = _psql_apply(case, path, st)
        out["after"] = (await _constraint_def(conn), await _rows_with_xmin(conn))
    finally:
        try:
            out["cleanup"] = _psql_apply(case, R418)
            await _unplant(conn, case, "le_true")
        finally:
            await conn.close()
    out["restore"] = _psql_apply(case, M418)
    return out


def test_r2_a_an_operator_in_the_tables_schema_does_not_decide_the_check(case):
    """bancap-r2 HIGH 1, its input as a named test. (1) After a first apply
    under that path the CHECK still refuses an end past the cap (and admits
    one at it). (2) Where a correct CHECK already stands, the file accepts
    it: rc 0, the "present" notice, no row changed."""
    out = _run(_operator_case(case, M418))
    assert out["rollback"][0] == 0 and out["rollback2"][0] == 0, out
    rc, err = out["first"]
    assert rc == 0, err
    assert out["first_verdicts"] == ("refused", "admitted", "refused"), out["first_verdicts"]
    assert out["standing_def"] == WANT_DEF, out["standing_def"]
    rc, err = out["on_standing"]
    assert rc == 0 and _notices(err) == [PRESENT], (rc, err)
    assert out["after"] == (WANT_DEF, out["before"]), "the file changed a row or the CHECK"
    assert out["cleanup"][0] == 0 and out["restore"][0] == 0, out


def test_r2_b_quote_all_identifiers_on_a_first_and_a_second_apply_end_rc_0(case):
    """bancap-r2 HIGH 2, its input as a named test: with quote_all_identifiers
    on for the session, a first apply and a second apply both end rc 0."""
    out = _run(_apply_under(case, M418, (("quote_all_identifiers", "on"),), None))
    assert out["first"][0] == 0, out["first"]
    assert out["def"] == WANT_DEF, out["def"]
    rc, err = out["again"]
    assert rc == 0 and _notices(err) == [PRESENT], (rc, err)
    assert out["cleanup"][0] == 0 and out["restore"][0] == 0, out


def test_two_first_runs_of_418_at_once_under_repeatable_read_end_as_two_in_sequence(case):
    """Point 4 of the r2 order: the two first runs once more with session B's
    default_transaction_isolation = repeatable read. B's transaction is read
    committed whatever the session brought, so its re-read under the lock
    sees A's commit: rc 0, the "present" notice, no row changed."""
    out = _run(_two_first_runs(case, M418, release=True, b_settings=REPEATABLE_READ))
    assert out["b_waited"] is True, "session B never waited on the lock"
    rc, err = out["b"]
    assert rc == 0 and _notices(err) == [PRESENT], (rc, err)
    assert out["after_b"] == out["after_a"], "session B changed a row"
    assert out["def"] == WANT_DEF and out["restore"][0] == 0, out


# -- mutants, one per pinned line, and the MEDIUM's ----------------------------

def test_mutant_418_without_its_isolation_level_fails_the_second_run_under_repeatable_read(case):
    """Mutant: a bare BEGIN. Under repeatable read B's snapshot is taken at
    its DO's first read, before A commits, so its re-read under the lock
    still finds the CHECK absent and it acts on rows A has since changed."""
    path = _m418_copy(BEGIN_LINE, "BEGIN;\n")
    try:
        out = _run(_two_first_runs(case, path, release=True, b_settings=REPEATABLE_READ))
    finally:
        os.unlink(path)
    assert out["b_waited"] is True, "session B never waited on the lock"
    rc, err = out["b"]
    assert rc != 0 and "could not serialize access due to concurrent update" in err, (rc, err)
    assert out["after_b"] == out["after_a"] and out["def"] == WANT_DEF, out


def test_mutant_418_without_its_search_path_pin_lets_the_operator_decide(case):
    """Mutant: the search-path line removed. Under {case}, pg_catalog the
    first apply parses the CHECK with the planted operator and its post-check
    reads it back bare, so the CHECK admits an end past the cap; and a
    correct standing CHECK deparses as OPERATOR(pg_catalog.<=) and is
    refused."""
    path = _m418_copy(PATH_LINE, "")
    try:
        out = _run(_operator_case(case, path))
    finally:
        os.unlink(path)
    assert out["first"][0] == 0, out["first"]
    assert out["first_verdicts"][0] == "admitted", out["first_verdicts"]
    rc, err = out["on_standing"]
    assert rc != 0 and "OPERATOR(pg_catalog.<=)" in err and "not the validated CHECK 418 adds" in err, (rc, err)
    assert out["after"] == (WANT_DEF, out["before"]), out["after"]
    assert out["cleanup"][0] == 0 and out["restore"][0] == 0, out


def test_mutant_418_pinning_a_path_without_the_tables_schema_is_refused_with_nothing_applied(case):
    """Mutant: the pinned path without the table's own schema. The bare name
    player_bans then resolves to no table, the identity check refuses, and
    nothing is applied: the case for that check's refusal."""
    path = _m418_copy(PATH_LINE, PATH_LINE_NO_SCHEMA)
    try:
        out = _run(_apply_under(case, path, (), None))
    finally:
        os.unlink(path)
    rc, err = out["first"]
    assert rc != 0 and "418: player_bans under the pinned search path is missing" in err, (rc, err)
    assert out["def"] is None and out["after_first"] == out["before"], out
    assert out["cleanup"][0] == 0 and out["restore"][0] == 0, out


def test_mutant_418_without_its_quote_all_identifiers_pin_is_refused_with_it_on(case):
    """Mutant: the quote_all_identifiers line removed. With it on, the
    post-check reads the columns quoted and refuses; nothing is applied."""
    path = _m418_copy(QAI_LINE, "")
    try:
        out = _run(_apply_under(case, path, (("quote_all_identifiers", "on"),), None))
    finally:
        os.unlink(path)
    rc, err = out["first"]
    assert rc != 0 and '"expires_at"' in err and "not the validated CHECK 418 adds" in err, (rc, err)
    assert out["def"] is None and out["after_first"] == out["before"], out
    assert out["cleanup"][0] == 0 and out["restore"][0] == 0, out


def test_mutant_418_rewriting_every_row_in_its_present_branch_fails_the_two_first_runs(case):
    """bancap-r2's MEDIUM. Mutant: a no-op UPDATE of every row before the
    "present" notice. B still ends rc 0 with the notice, but its rows' xmin
    differ from the rows as A left them, read on A's own connection before
    its COMMIT: the assertion the two-first-runs test makes turns red."""
    path = _m418_copy(PRESENT_LINE, NOOP_UPDATE + PRESENT_LINE)
    try:
        out = _run(_two_first_runs(case, path, release=True))
    finally:
        os.unlink(path)
    rc, err = out["b"]
    assert rc == 0 and _notices(err) == [PRESENT], (rc, err)
    assert out["after_b"] != out["after_a"], "B's rewrite of every row went unseen"


# -- bancap-r2, the integrator's B1 and B2: comparisons written on types --------
# -- pg_catalog holds an exact operator for, and the rollback pinned too ---------

def _copy_with(src_path, pairs):
    """A temporary copy of the file at `src_path` with each (old, new, count)
    replaced; `old` must occur exactly `count` times. The caller unlinks it."""
    src = io.open(src_path, encoding="utf-8").read()
    for old, new, count in pairs:
        assert src.count(old) == count, (old, src.count(old), count)
        src = src.replace(old, new)
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as fh:
        fh.write(src)
        return fh.name


# Per cast in 418: the mutant without it, the plant that then moves the
# file, and the refusal that names the reason.
CAST_MUTANTS = (
    ("conrelid", "c.conrelid = tbl::oid", "c.conrelid = tbl", 3, "eq_oid_regclass_false",
     "418: player_bans_max_one_year is missing or not a validated CHECK, not the validated CHECK 418 adds"),
    ("attrelid", "a.attrelid = tbl::oid", "a.attrelid = tbl", 2, "eq_oid_regclass_false",
     "418: player_bans.expires_at is missing, not timestamp with time zone"),
    ("regtype", "'pg_catalog.timestamptz'::regtype::oid", "'pg_catalog.timestamptz'::regtype", 2,
     "eq_oid_regtype_false",
     "418: player_bans.expires_at is timestamp with time zone, not timestamp with time zone"),
    ("identity", "pg_catalog.to_regclass('player_bans')::oid IS DISTINCT FROM tbl::oid",
     "pg_catalog.to_regclass('player_bans') IS DISTINCT FROM tbl", 1, "eq_regclass_regclass_false",
     "418: player_bans under the pinned search path is"),
)


def test_b1_an_oid_regclass_equality_answering_true_leaves_player_bans_with_its_check(case):
    """B1's case that matters most, as a named test: an `=` on (oid, regclass)
    in the table's schema that answers true, and a second table carrying a
    CHECK of the same name. 418 must still put ITS CHECK on player_bans: rc 0,
    the CHECK refuses an end past the cap and a NULL end and admits one at
    the cap, a second apply changes no row, the second table's rows are
    untouched. (At f2580d3a the file ended rc 0 with no CHECK on player_bans,
    its reads satisfied by the second table's.)"""
    out = _run(_apply_under(case, M418, (), "eq_oid_regclass_true"))
    assert out["first"][0] == 0, out["first"]
    assert out["verdicts"] == ("refused", "admitted", "refused"), out["verdicts"]
    assert out["def"] == WANT_DEF, out["def"]
    rc, err = out["again"]
    assert rc == 0 and _notices(err) == [PRESENT], (rc, err)
    assert out["after_again"] == (WANT_DEF, out["after_first"]), "the second apply changed a row"
    assert out["decoy_after"] == out["decoy_before"], "a row of the second table changed"
    assert out["cleanup"][0] == 0 and out["restore"][0] == 0, out


@pytest.mark.parametrize("mutant", CAST_MUTANTS, ids=[m[0] for m in CAST_MUTANTS])
def test_mutant_418_without_a_cast_is_moved_by_its_plant(case, mutant):
    """Mutant per cast: the comparison written on its own types again, and an
    `=` with exactly those types planted in the table's schema answering
    false. The plant is taken over pg_catalog's operator, which needs a
    coercion: the file refuses for that comparison's reason, nothing
    applied. The same plant against the real file is an entry of
    SESSION_SETTINGS, where the file applies."""
    _id, old, new, count, plant, reason = mutant
    path = _copy_with(M418, ((old, new, count),))
    try:
        out = _run(_apply_under(case, path, (), plant))
    finally:
        os.unlink(path)
    rc, err = out["first"]
    assert rc != 0 and reason in err, (rc, err)
    assert out["def"] is None and out["after_first"] == out["before"], out
    assert out["cleanup"][0] == 0 and out["restore"][0] == 0, out


async def _null_end_verdict(conn, admin):
    tr = conn.transaction()
    await tr.start()
    try:
        await conn.execute("INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, expires_at)"
                           " VALUES ($1, 'no end', $2, NULL)", _sid(), admin)
        return "admitted"
    except Exception as e:      # asyncpg CheckViolationError
        return "refused" if CONSTRAINT in str(e) else repr(e)
    finally:
        await tr.rollback()


async def _rollback_under(case, path, settings, plant):
    """418 applied under the default session, then the rollback file at
    `path` under `settings` with the plant in place: its exit, the CHECK
    after it, whether a ban without an end is admitted again, and a second
    run. The plant is removed and 418 applied again at the end."""
    st = _settings_for(case, settings)
    conn = await harness.connect_bound(lh.DSN, case)
    out = {}
    planted = False
    try:
        out["apply"] = _psql_apply(case, M418)
        admin = _sid()
        await conn.execute("INSERT INTO admin_users (steam_id) VALUES ($1)", admin)
        out["def_before"] = await _constraint_def(conn)
        planted = True
        await _plant(conn, case, plant)
        out["rollback"] = _psql_apply(case, path, st)
        out["def_after"] = await _constraint_def(conn)
        out["null_end"] = await _null_end_verdict(conn, admin)
        out["again"] = _psql_apply(case, path, st)
        out["def_again"] = await _constraint_def(conn)
    finally:
        try:
            if planted:
                await _unplant(conn, case, plant)
        finally:
            await conn.close()
    out["restore"] = _psql_apply(case, M418)
    return out


@pytest.mark.parametrize("entry", SESSION_SETTINGS, ids=[e[0] for e in SESSION_SETTINGS])
def test_rollback_418_under_each_session_setting_drops_the_check(case, entry):
    """B2's generated test: the REAL rollback under each entry of
    SESSION_SETTINGS, with 418 applied before it. rc 0 means the CHECK is
    gone: afterwards a ban without an end is admitted again, and a second run
    ends rc 0. Under default_transaction_read_only the drop is refused and
    the CHECK stands."""
    name, settings, plant, want, _why = entry
    out = _run(_rollback_under(case, R418, settings, plant))
    assert out["apply"][0] == 0 and out["def_before"] == WANT_DEF, (name, out["apply"], out["def_before"])
    rc, err = out["rollback"]
    if want == "refused":
        assert rc != 0 and "read-only transaction" in err, (name, rc, err)
        assert out["def_after"] == WANT_DEF, (name, out["def_after"])
    else:
        assert rc == 0, (name, err)
        assert out["def_after"] is None and out["null_end"] == "admitted", (name, out)
        assert out["again"][0] == 0 and out["def_again"] is None, (name, out["again"])
    assert out["restore"][0] == 0, (name, out["restore"])


ROLLBACK_POST_CHECK = (
    "\n  -- Post-check: rc 0 means the CHECK is gone. Written with pg_catalog's\n"
    "  -- operators named, so it holds whatever the path above it read.\n"
    "  IF EXISTS (SELECT 1 FROM pg_catalog.pg_constraint c\n"
    "              WHERE c.conrelid OPERATOR(pg_catalog.=) tbl::oid\n"
    "                AND c.conname OPERATOR(pg_catalog.=) 'player_bans_max_one_year'::name) THEN\n"
    "    RAISE EXCEPTION 'rollback 418: player_bans_max_one_year still stands after the drop';\n"
    "  END IF;\n")


def test_rollback_with_a_false_name_equality_ahead_of_pg_catalog_drops_the_check(case):
    """B2's input as a named test: an `=` on two name values in the table's
    schema that answers false, and the path {case}, pg_catalog. The
    rollback ends rc 0 and the CHECK is gone."""
    out = _run(_rollback_under(case, R418, OPERATOR_PATH, "eq_name_name_false"))
    rc, err = out["rollback"]
    assert rc == 0 and out["def_after"] is None, (rc, err, out["def_after"])
    assert out["null_end"] == "admitted", out["null_end"]


def test_mutant_rollback_without_its_pin_is_refused_by_its_post_check(case):
    """Mutant: the rollback without its search-path line. Under B2's input
    its guard reads the CHECK absent and skips the drop; the post-check
    finds it standing and refuses (rc 3): never rc 0 with the CHECK left."""
    path = _copy_with(R418, ((PATH_LINE, "", 1),))
    try:
        out = _run(_rollback_under(case, path, OPERATOR_PATH, "eq_name_name_false"))
    finally:
        os.unlink(path)
    rc, err = out["rollback"]
    assert rc != 0 and "still stands after the drop" in err, (rc, err)
    assert out["def_after"] == WANT_DEF, out["def_after"]


def test_mutant_rollback_without_its_pin_and_its_post_check_ends_rc_0_with_the_check(case):
    """Mutant: the rollback without its pin AND without its post-check (with
    the pin in place no input known here defeats the guard, so the
    post-check is measured on the file without it). Under B2's input it ends
    rc 0 with the CHECK still standing: the outcome the post-check refuses."""
    path = _copy_with(R418, ((PATH_LINE, "", 1), (ROLLBACK_POST_CHECK, "\n", 1)))
    try:
        out = _run(_rollback_under(case, path, OPERATOR_PATH, "eq_name_name_false"))
    finally:
        os.unlink(path)
    assert out["rollback"][0] == 0 and out["def_after"] == WANT_DEF, (out["rollback"], out["def_after"])
