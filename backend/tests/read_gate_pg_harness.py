"""Live PostgreSQL for the verified-reads tests: ONE production-shaped case
schema per test process.

The schema is built as the ladder hook tests build theirs
(test_title_ladder_hooks_live._build: every migration's DDL replayed -- 367's
included -- the ORM's tables, the widening pass, the replay again), then 367
is run WHOLE once more (its idempotent re-run) and the schema is sealed.
ladder_pg_harness's census discipline governs the create and the drop.

READ_GATE_TEST_PG_DSN names a throwaway database for the case schemas. Unset,
every live test FAILS (a skipped live case reports exit 0 for coverage that
did not run) unless READ_GATE_TEST_PG_OPTOUT=1 waives it deliberately.

Identities are synthetic (7656119000xxxxxxx).

`Lane.client(monkeypatch)` returns a TestClient on the REAL app whose request
sessions (get_db) and whose gate lookups (database.async_session) both open
on the case schema, through a NullPool engine, so every connection is made
on the loop that uses it.
"""
from __future__ import annotations

import asyncio
import atexit
import io
import os
import sys
import threading

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import database  # noqa: E402
import main  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402

DSN_VAR = "READ_GATE_TEST_PG_DSN"
OPTOUT_VAR = "READ_GATE_TEST_PG_OPTOUT"
DSN = (os.environ.get(DSN_VAR) or "").replace("postgresql+asyncpg://", "postgresql://")
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"
MIGRATION = os.path.join(HERE, "..", "sql", "367_api_operator_keys.sql")


def require_live_pg():
    """Fail, not skip, unless the waiver is set (module docstring)."""
    if DSN and harness._asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: the live verified-reads coverage is deliberately "
                    "waived." % (DSN_VAR, OPTOUT_VAR))
    pytest.fail("%s is unset, so no verified-reads route ran against a real server. Point "
                "it at a throwaway database, or set %s=1 to waive the coverage deliberately."
                % (DSN_VAR, OPTOUT_VAR))


def migration_text() -> str:
    return io.open(MIGRATION, encoding="utf-8").read()


def _view(migration: str, name: str) -> str:
    """One CREATE OR REPLACE VIEW statement, verbatim from its migration."""
    text = io.open(os.path.join(HERE, "..", "sql", migration), encoding="utf-8").read()
    head = "CREATE OR REPLACE VIEW %s AS" % name
    start = text.index(head)
    return text[start:text.index(";", start) + 1]


VIEWS = (_view("148_cosmetic_placement_and_macro_evidence.sql", "cosmetic_release_candidates"),)


class Lane:
    """A background event loop holding one built, sealed case schema."""

    def __init__(self, prefix):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.case = harness.CaseSchema(DSN, prefix)

    def run(self, coro, timeout=600):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    async def _open(self):
        await self.case.__aenter__()
        try:
            async def _367(conn, schema):
                await conn.execute(migration_text())
                # The DDL replay builds tables, not views; one ADMIN_SIGNED
                # read (cosmetic-release-candidates) selects from a view.
                for stmt in VIEWS:
                    await conn.execute(stmt)
            saved = lh.DSN
            lh.DSN = DSN
            try:
                await lh._build(self.case, _367)
            finally:
                lh.DSN = saved
        except BaseException:
            await self.case.__aexit__(None, None, None)
            raise

    async def _close(self):
        await self.case.__aexit__(None, None, None)

    def open(self):
        self.run(self._open(), timeout=1800)
        return self

    def close(self):
        try:
            self.run(self._close(), timeout=600)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(10)

    @property
    def schema(self):
        return self.case.schema

    async def connect(self):
        """A raw asyncpg connection bound to the case schema."""
        return await harness.connect_bound(DSN, self.case.schema)

    def fetch(self, sql, *args):
        async def _f():
            conn = await self.connect()
            try:
                return await conn.fetch(sql, *args)
            finally:
                await conn.close()
        return self.run(_f())

    def execute(self, sql, *args):
        async def _f():
            conn = await self.connect()
            try:
                return await conn.execute(sql, *args)
            finally:
                await conn.close()
        return self.run(_f())

    def sessionmaker(self):
        engine = harness.bound_engine(DSN, self.case.schema)
        return async_sessionmaker(engine, expire_on_commit=False)

    def client(self, monkeypatch):
        """A TestClient on main.app whose request sessions and gate lookups
        both open on this case schema."""
        from fastapi.testclient import TestClient
        sm = self.sessionmaker()

        async def _get_db():
            async with sm() as s:
                try:
                    yield s
                finally:
                    await s.close()
        monkeypatch.setattr(database, "async_session", sm)
        monkeypatch.setitem(main.app.dependency_overrides, main.get_db, _get_db)
        monkeypatch.setattr(main, "_RL_BUCKETS",
                            main._RL_BUCKETS.__class__(main._RL_BUCKETS.default_factory))
        return TestClient(main.app, raise_server_exceptions=False)


_SHARED = []


def shared_lane():
    """The process's one lane: built by the first module that asks, reused by
    the rest, dropped at exit."""
    if not _SHARED:
        lane = Lane("read_gate").open()
        _SHARED.append(lane)
        atexit.register(lane.close)
    return _SHARED[0]
