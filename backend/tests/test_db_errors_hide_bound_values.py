"""A failed statement's error text carries no bound value (the Codex
FENCE-R2 M1).

The availability-check withdrawal re-resolves the clicker through
GET /api/v1/players/by-discord/{discord_id} (main.py), whose SELECT binds the
raw Discord id. A statement that fails while it executes (a cancel, a
statement_timeout, a lost connection) raises SQLAlchemy's DBAPIError, and a
route that does not catch it ends in uvicorn's error log: "Exception in ASGI
application" with the formatted traceback, through the "uvicorn.error"
logger (uvicorn 0.30.6, protocols/http/httptools_impl.py). SQLAlchemy's
default exception text includes the bound values, so that log line carried
the id. database.py now builds every engine through one create_async_engine
that adds hide_parameters=True.

1. Every engine database.py builds carries the flag; the module calls
   SQLAlchemy's constructor in one place, with the flag; no other api module
   builds an engine. CONTROL: SQLAlchemy's constructor alone leaves it off.
2. Live, each of database.py's engines: a statement binding a synthetic
   Discord id is cancelled by its statement_timeout; the id is absent from
   str(exc), repr(exc) and the record uvicorn's logger writes, which still
   names the cancel and the statement. CONTROL: the same statement on an
   engine from SQLAlchemy's constructor alone shows the id in both.
3. Live, the route itself through the app (discord_collection_harness): the
   by-discord SELECT waits behind a lock and is cancelled; the request
   answers 500, and the record written the way uvicorn writes it names the
   cancel and the statement and carries no Discord id.
"""
import ast
import asyncio
import contextlib
import io
import logging
import os

import httpx
import pytest
import sqlalchemy.exc
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import create_async_engine as sqlalchemy_create_async_engine

import discord_collection_harness as H

DSN = os.environ.get(H.DSN_VAR)
OPTOUT = H.optout(os.environ.get(H.OPTOUT_VAR))
DID = H.discord_of(731)                 # synthetic 18-digit Discord id
HIDDEN = "[SQL parameters hidden due to hide_parameters=True]"
ENGINES = ("engine", "release_engine", "asm_engine")
STMT = "SELECT CAST(:discord_id AS varchar(20)) AS discord_id, pg_sleep(5) AS slept"
UNREACHABLE = "postgresql+asyncpg://nobody@127.0.0.1:1/nothing"


def _as_uvicorn_logs(exc) -> str:
    """The record uvicorn writes for an exception the app raised: logger
    "uvicorn.error", message "Exception in ASGI application\\n",
    exc_info=exc (uvicorn 0.30.6, httptools_impl.py and h11_impl.py)."""
    out = io.StringIO()
    handler = logging.StreamHandler(out)
    handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
    log = logging.getLogger("uvicorn.error")
    log.addHandler(handler)
    try:
        log.error("Exception in ASGI application\n", exc_info=exc)
    finally:
        log.removeHandler(handler)
    return out.getvalue()


def _logging_like_uvicorn(app, out):
    """The app as uvicorn serves it, for the one sink read here: an exception
    the app raises is written to `out` as uvicorn writes it, then re-raised."""
    async def served(scope, receive, send):
        try:
            await app(scope, receive, send)
        except Exception as exc:
            out.write(_as_uvicorn_logs(exc))
            raise
    return served


@contextlib.asynccontextmanager
async def _pointed_at(eng, dsn):
    """database.py's engine object itself, its connections opened on the lane
    database by the harness's do_connect redirect (which edits none of the
    engine's own parameters); disposed on the way out."""
    redirect = H._redirect_for(make_url(dsn))
    await eng.dispose(close=False)
    event.listen(eng.sync_engine, "do_connect", redirect)
    try:
        yield eng
    finally:
        await eng.dispose()
        event.remove(eng.sync_engine, "do_connect", redirect)


async def _cancelled(eng):
    """STMT, binding DID, on `eng`, cancelled by a 200 ms statement_timeout."""
    async with eng.connect() as conn:
        await conn.execute(text("SET LOCAL statement_timeout = '200ms'"))
        with pytest.raises(sqlalchemy.exc.DBAPIError) as caught:
            await conn.execute(text(STMT), {"discord_id": DID})
        await conn.rollback()
    return caught.value


async def _scalar(eng, sql, **params):
    async with eng.connect() as conn:
        return (await conn.execute(text(sql), params)).scalar()


async def _blocked_backend(eng, needle, request):
    """The pid of the backend whose statement contains `needle` and waits for
    a lock; fails with the request's own answer if it ended first."""
    async with eng.connect() as conn:
        for _ in range(200):
            if request.done():
                r = request.result()
                pytest.fail("the request ended before its SELECT waited: %s %s"
                            % (r.status_code, r.text[:200]))
            pid = (await conn.execute(text(
                "SELECT pid FROM pg_stat_activity WHERE datname = current_database()"
                " AND wait_event_type = 'Lock' AND strpos(query, :needle) > 0"),
                {"needle": needle})).scalar()
            await conn.rollback()       # the next read takes a fresh activity snapshot
            if pid is not None:
                return pid
            await asyncio.sleep(0.05)
    pytest.fail("no backend waited on the players lock within 10 s")


def test_every_engine_database_py_builds_hides_bound_values():
    import database
    built = {name: getattr(database, name) for name in ENGINES}
    built["make_asm_engine()"] = database.make_asm_engine(UNREACHABLE)
    built.update((k, v) for k, v in vars(database).items() if isinstance(v, AsyncEngine))
    for name, eng in built.items():
        assert eng.sync_engine.hide_parameters is True, name
    # control: SQLAlchemy's constructor alone leaves the flag off
    assert sqlalchemy_create_async_engine(UNREACHABLE).sync_engine.hide_parameters is False
    # one place: SQLAlchemy's constructor is imported under a private name only
    # and called once, inside database.py's own create_async_engine, with the flag
    source = (H.API_DIR / "database.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = [(a.name, a.asname) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                for a in node.names if a.name == "create_async_engine"]
    assert imported == [("create_async_engine", "_sqlalchemy_create_async_engine")]
    wrapper = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "create_async_engine"]
    assert len(wrapper) == 1
    raw = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
           and n.func.id == "_sqlalchemy_create_async_engine"]
    assert len(raw) == 1 and any(n is raw[0] for n in ast.walk(wrapper[0]))
    assert [(k.arg, getattr(k.value, "value", None)) for k in raw[0].keywords if k.arg] == \
        [("hide_parameters", True)]
    assert "create_engine" not in source
    assert database.create_async_engine.__module__ == "database"
    # no other api module builds an engine of its own
    others = sorted(str(p.relative_to(H.API_DIR)) for p in H.API_DIR.rglob("*.py")
                    if p.name != "database.py"
                    and any(w in p.read_text(encoding="utf-8")
                            for w in ("create_async_engine", "create_engine")))
    assert others == []


@pytest.mark.parametrize("name", ENGINES)
def test_a_failed_statement_on_each_engine_logs_no_bound_value(name):
    dsn = H.require_pg(DSN, OPTOUT)
    import database
    eng = getattr(database, name)

    async def go():
        async with _pointed_at(eng, dsn):
            exc = await _cancelled(eng)
        control = sqlalchemy_create_async_engine(dsn)
        try:
            ctl = await _cancelled(control)
        finally:
            await control.dispose()
        return exc, ctl
    exc, ctl = H.run(go())
    logged = _as_uvicorn_logs(exc)
    for where, rendered in (("str", str(exc)), ("repr", repr(exc)), ("uvicorn's record", logged)):
        assert DID not in rendered, where
    # the failure is the intended one, and its text is in the record
    assert "canceling statement due to statement timeout" in str(exc)
    assert "Exception in ASGI application" in logged and "CAST(" in logged and HIDDEN in logged
    # control: without the flag the same failure shows the id, in str and in the record
    assert DID in str(ctl) and "[parameters:" in str(ctl)
    assert DID in _as_uvicorn_logs(ctl)


def test_the_by_discord_lookup_logs_no_discord_id_when_its_select_is_cancelled(monkeypatch, tmp_path):
    dsn = H.require_pg(DSN, OPTOUT)

    async def go():
        async with H.Env(monkeypatch, tmp_path, dsn) as env:
            import main
            out = io.StringIO()
            transport = httpx.ASGITransport(app=_logging_like_uvicorn(main.app, out),
                                            raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url=H.BASE_URL,
                                         timeout=60.0) as client:
                async with env.seed.connect() as hold:
                    await hold.execute(text("LOCK TABLE players IN ACCESS EXCLUSIVE MODE"))
                    request = asyncio.ensure_future(
                        client.get("/api/v1/players/by-discord/%s" % DID, headers=env.ihead()))
                    try:
                        pid = await _blocked_backend(env.seed, "players.discord_id", request)
                        cancelled = await _scalar(env.seed, "SELECT pg_cancel_backend(:pid)", pid=pid)
                    finally:
                        await hold.rollback()
                answer = await request
            return cancelled, answer.status_code, out.getvalue()
    cancelled, status, logged = H.run(go())
    assert cancelled is True and status == 500, (cancelled, status)
    assert DID not in logged
    # the record is the cancelled lookup's
    assert "Exception in ASGI application" in logged
    assert "canceling statement due to user request" in logged
    assert "players.discord_id" in logged and HIDDEN in logged
