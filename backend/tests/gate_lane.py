"""The admission-gate suite's live lane database (test_match_hold_admission_gate_pg).

The live tests run in cf_pg.DSN's database when its role may create schemas
there (a superuser, or the database's owner). Otherwise (an admin DSN whose
role is not a superuser, as the seats' scr_gate on postgres) the fixture
creates a database of its own through that DSN (CREATEDB suffices), points
cf_pg.DSN at it for the module, and drops it afterwards, together with the
pool's faithful copy when one was made. No DSN fails the test
(cf_pg.require_live_pg); nothing here skips.
"""
import asyncio
import uuid

import asyncpg
import pytest

import cf_pg


@pytest.fixture(scope="module")
def gate_lane():
    """The lane database's DSN, cf_pg.DSN while the module's live tests run."""
    cf_pg.require_live_pg()
    admin = cf_pg.DSN
    lane = asyncio.run(_open(admin))
    if lane is None:
        yield admin
        return
    mp = pytest.MonkeyPatch()
    mp.setattr(cf_pg, "DSN", lane)
    try:
        yield lane
    finally:
        mp.undo()
        asyncio.run(_drop(admin, lane))


async def _open(admin):
    """None when the admin DSN's role may CREATE in its own database; else
    the DSN of a new database that role creates."""
    conn = await asyncpg.connect(admin)
    try:
        if await conn.fetchval(
                "SELECT has_database_privilege(current_database(), 'CREATE')"):
            return None
        name = f"gate_lane_{uuid.uuid4().hex[:16]}"
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()
    base, _, tail = admin.rpartition("/")
    query = tail.partition("?")[2]
    return f"{base}/{name}" + (f"?{query}" if query else "")


async def _drop(admin, lane):
    """Drop the lane database and its faithful copy, through the admin DSN."""
    name = lane.rpartition("/")[2].partition("?")[0]
    conn = await asyncpg.connect(admin)
    try:
        for db in (name, f"{name}_faithful"):
            await conn.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
    finally:
        await conn.close()
