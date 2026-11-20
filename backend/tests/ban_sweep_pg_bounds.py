"""A lock bound and a statement bound of its own for every database test of
the ban sweep (bans part 2a).

A database test that waits on a lock with no bound of its own waits until the
test run's bound, and holds a test seat for hours (a seat run of 19 Nov 2026
did, at a test of another file whose choreography waited for itself). Every
lane test file that talks to PostgreSQL imports `bounded_pg` (autouse): while
a test runs, every engine and plain connection the shared harness opens
(ladder_pg_harness.bound_engine and connect_bound, which cf_pg, inv_pg, the
match hold harness and test_ban_sweep_live's _with_sm all call at use time)
starts with lock_timeout LOCK_TIMEOUT and statement_timeout
STATEMENT_TIMEOUT. A lock wait then ends in 55P03, a statement in 57014,
inside the test. test_ban_sweep_pg_bounds.py checks that every lane database
file imports it, and that a bounded session reports both settings.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ladder_pg_harness as harness  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

LOCK_TIMEOUT = "10s"
STATEMENT_TIMEOUT = "120s"
BOUNDS = {"lock_timeout": LOCK_TIMEOUT, "statement_timeout": STATEMENT_TIMEOUT}
# The harness's own two openers, read at import (before any test patches
# them); the live test's control puts the first back.
ORIGINAL_BOUND_ENGINE = harness.bound_engine
ORIGINAL_CONNECT_BOUND = harness.connect_bound


def bounded_engine(dsn, schema):
    """harness.bound_engine with the two bounds in every connection's
    startup settings (NullPool: each session is a new connection)."""
    return create_async_engine(
        harness.async_dsn(dsn), poolclass=NullPool,
        connect_args={"server_settings": {"search_path": harness.quoted(schema), **BOUNDS}})


async def bounded_connect(dsn, schema):
    """harness.connect_bound with the two bounds."""
    return await harness._asyncpg.connect(
        dsn.replace("postgresql+asyncpg://", "postgresql://"),
        server_settings={"search_path": harness.quoted(schema), **BOUNDS})


@pytest.fixture(autouse=True)
def bounded_pg(monkeypatch):
    monkeypatch.setattr(harness, "bound_engine", bounded_engine)
    monkeypatch.setattr(harness, "connect_bound", bounded_connect)
    yield
