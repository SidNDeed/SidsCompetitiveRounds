"""BAN-RECORD-1 R1, bar V1: migration 429 (backend/sql/429_ban_record.sql)
and its rollback, run through psql as the migrate verb runs them (the file on
stdin, ON_ERROR_STOP), on a case schema built by the ladder harness (every
migration's DDL replayed, 429's DO among them, then the ORM), on the lane's
PostgreSQL. Each step's psql output and the catalog read after it are printed
(run with -s to keep them in the log):

  1. the rollback, on the built case: the three columns and the CHECK go;
     the rows stay; a second rollback changes nothing;
  2. 429 applied: three nullable columns (text, text, timestamptz) with no
     default, the CHECK validated and as written, every existing row NULL in
     all three; applied a second time: its notice, and not one catalog row
     written (the xmin of each column's and the constraint's catalog row is
     the same);
  3. 429 applied while another connection holds an open read of the table:
     it waits on that read (seen waiting on the lock), applies once the read
     ends, and the wait is measured; a read held past the 5 s lock bound
     refuses the run with nothing applied, and the next run applies;
  4. refused, nothing applied, when a column of one of the three names
     stands with another type (each column in turn), and when a constraint
     of the CHECK's name stands with another definition;
  5. the rollback refuses a column of one of the three names with another
     type, and drops nothing.

    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    BAN_TEST_PSQL / CF_PSQL   the psql client (else PATH, else C:/pg16)
"""
import asyncio
import io
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
SQL_DIR = os.path.normpath(os.path.join(HERE, "..", "sql"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

import models  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402
from test_ban_cap_pg import _notices, _psql_apply, _psql_args  # noqa: E402

M429 = os.path.join(SQL_DIR, "429_ban_record.sql")
R429 = os.path.join(SQL_DIR, "rollback_429_ban_record.sql")
CON = "ck_player_bans_details_len"
WANT_DEF = "CHECK (((details IS NULL) OR (char_length(details) <= %d)))" % models.BAN_DETAILS_MAX
COLS = ("details", "details_at", "display_name_at_ban")
WANT_COLS = [("details", "text", False, None), ("details_at", "timestamp with time zone", False, None),
             ("display_name_at_ban", "text", False, None)]


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def case():
    lh._require_live_pg()
    built = {}

    async def build():
        c = harness.CaseSchema(lh.DSN, "ban_rec_mig")
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


async def _cols(conn):
    """(name, type, not null, default) of the three columns that stand, by name."""
    return [tuple(r) for r in await conn.fetch(
        "SELECT a.attname::text, format_type(a.atttypid, a.atttypmod), a.attnotnull,"
        "       pg_get_expr(d.adbin, d.adrelid)"
        "  FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum"
        " WHERE a.attrelid = to_regclass('player_bans') AND a.attname = ANY($1::text[]) AND NOT a.attisdropped"
        " ORDER BY a.attname", list(COLS))]


async def _con(conn):
    row = await conn.fetchrow(
        "SELECT pg_get_constraintdef(c.oid), c.convalidated FROM pg_constraint c"
        " WHERE c.conrelid = to_regclass('player_bans') AND c.conname = $1", CON)
    return tuple(row) if row else None


async def _xmins(conn):
    """The catalog rows' xmin of the three columns and the constraint: a run
    that writes no catalog row leaves every one as it was."""
    a = await conn.fetch(
        "SELECT a.attname::text, a.xmin::text FROM pg_attribute a"
        " WHERE a.attrelid = to_regclass('player_bans') AND a.attname = ANY($1::text[]) ORDER BY 1", list(COLS))
    c = await conn.fetchval("SELECT c.xmin::text FROM pg_constraint c"
                            " WHERE c.conrelid = to_regclass('player_bans') AND c.conname = $1", CON)
    return [tuple(r) for r in a], c


async def _rows(conn):
    return [tuple(r) for r in await conn.fetch("SELECT id, steam_id, reason, expires_at FROM player_bans ORDER BY id")]


def _say(label, rc, err, extra=None):
    print("[V1] %s: psql rc %s; notices %s; errors %s%s" % (
        label, rc, _notices(err), [l for l in err.splitlines() if "ERROR" in l],
        "" if extra is None else "; " + repr(extra)))


async def _psql_async(schema, path, appname):
    """psql with the file on stdin, as a child of this loop: (rc, stderr, seconds)."""
    args, env = _psql_args(schema, appname=appname)
    t0 = time.monotonic()
    with open(path, "rb") as fh:
        p = await asyncio.create_subprocess_exec(*args, stdin=fh, env=env,
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, err = await asyncio.wait_for(p.communicate(), 120)
    return p.returncode, err.decode("utf-8", "replace"), time.monotonic() - t0


async def _waiting(conn, appname, tries=100):
    for _ in range(tries):
        if await conn.fetchval("SELECT count(*) FROM pg_stat_activity"
                               " WHERE application_name = $1 AND wait_event_type = 'Lock'", appname):
            return True
        await asyncio.sleep(0.05)
    return False


def test_v1_429_rolls_back_applies_twice_and_reruns_without_a_catalog_write(case):
    async def go():
        conn = await harness.connect_bound(lh.DSN, case)
        out = {}
        try:
            out["built"] = (await _cols(conn), await _con(conn))
            admin = "76561190042900001"
            await conn.execute("INSERT INTO admin_users (steam_id) VALUES ($1) ON CONFLICT DO NOTHING", admin)
            for i in range(3):
                await conn.execute(
                    "INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
                    " VALUES ($1, 'v1', $2, NOW() - INTERVAL '1 hour', NOW() + INTERVAL '1 day')",
                    "7656119004290%04d" % (100 + i), admin)
            await conn.execute("UPDATE player_bans SET details = 'kept by the build' WHERE reason = 'v1'"
                               " AND steam_id = '76561190042900100'")
            rows = await _rows(conn)
            out["rollback"] = _psql_apply(case, R429)
            out["after_rollback"] = (await _cols(conn), await _con(conn), await _rows(conn) == rows)
            out["rollback_again"] = _psql_apply(case, R429)
            out["first"] = _psql_apply(case, M429)
            out["after_first"] = (await _cols(conn), await _con(conn), await _rows(conn) == rows,
                                  await conn.fetchval("SELECT count(*) FROM player_bans WHERE display_name_at_ban"
                                                      " IS NOT NULL OR details IS NOT NULL OR details_at IS NOT NULL"))
            x1 = await _xmins(conn)
            out["second"] = _psql_apply(case, M429)
            out["after_second"] = (await _cols(conn), await _con(conn), await _xmins(conn) == x1)
            # the CHECK refuses one character past the bound and takes the bound
            for label, n in (("at", models.BAN_DETAILS_MAX), ("past", models.BAN_DETAILS_MAX + 1)):
                try:
                    await conn.execute("UPDATE player_bans SET details = repeat('d', $1) WHERE steam_id = $2",
                                       n, "76561190042900101")
                    out["check_" + label] = "stored"
                except Exception as e:      # asyncpg CheckViolationError
                    out["check_" + label] = type(e).__name__ + ": " + str(e).split("\n")[0]
        finally:
            await conn.close()
        return out
    out = _run(go())
    for k in ("rollback", "rollback_again", "first", "second"):
        _say(k, *out[k])
    print("[V1] built:", out["built"])
    print("[V1] after first:", out["after_first"])
    assert out["built"] == (WANT_COLS, (WANT_DEF, True)), out["built"]
    assert out["rollback"][0] == 0 and out["after_rollback"] == ([], None, True), (out["rollback"], out["after_rollback"])
    assert out["rollback_again"][0] == 0 and _notices(out["rollback_again"][1]) == [], out["rollback_again"]
    assert out["first"][0] == 0 and _notices(out["first"][1]) == [], out["first"]
    assert out["after_first"] == (WANT_COLS, (WANT_DEF, True), True, 0), out["after_first"]
    rc, err = out["second"]
    assert rc == 0 and _notices(err) == ["429: the three columns and ck_player_bans_details_len stand; nothing changed"], err
    assert out["after_second"] == (WANT_COLS, (WANT_DEF, True), True), out["after_second"]
    assert out["check_at"] == "stored" and CON in out["check_past"], (out["check_at"], out["check_past"])


@pytest.mark.parametrize("held", [1.0, 7.0])
def test_v1_429_applies_to_a_table_another_connection_is_reading(case, held):
    """A reader holds an open transaction that has read player_bans (its
    ACCESS SHARE lock). 429 waits on it, seen in pg_stat_activity. Read for
    1 s: the run applies once the read ends. Read for 7 s, past the run's
    5 s lock bound: the run is refused with nothing applied, and the next
    run, the read ended, applies."""
    async def go():
        conn = await harness.connect_bound(lh.DSN, case)
        reader = await harness.connect_bound(lh.DSN, case)
        out = {}
        app = "ban-rec-v1-%d" % int(held)
        try:
            rc, err = _psql_apply(case, R429)
            assert rc == 0 and await _cols(conn) == [], err
            await reader.execute("BEGIN")
            out["read"] = await reader.fetchval("SELECT count(*) FROM player_bans")
            run = asyncio.ensure_future(_psql_async(case, M429, app))
            out["seen_waiting"] = await _waiting(conn, app)
            await asyncio.sleep(held)
            await reader.execute("COMMIT")
            out["run"] = await run
            out["after_run"] = (await _cols(conn), await _con(conn))
            if out["run"][0] != 0:
                out["rerun"] = await _psql_async(case, M429, app + "-again")
                out["after_rerun"] = (await _cols(conn), await _con(conn))
        finally:
            await reader.close()
            await conn.close()
        return out
    out = _run(go())
    rc, err, secs = out["run"]
    _say("open read %.0f s" % held, rc, err, "waited %.2f s; seen waiting %s" % (secs, out["seen_waiting"]))
    assert out["seen_waiting"], "429 did not wait on the open read"
    if held < 5:
        assert rc == 0 and held <= secs < 5, (rc, secs, err)
        assert out["after_run"] == (WANT_COLS, (WANT_DEF, True)), out["after_run"]
    else:
        assert rc != 0 and "lock timeout" in err and 4.5 <= secs < held, (rc, secs, err)
        assert out["after_run"] == ([], None), out["after_run"]
        rc2, err2, secs2 = out["rerun"]
        _say("rerun after the read", rc2, err2, "%.2f s" % secs2)
        assert rc2 == 0 and out["after_rerun"] == (WANT_COLS, (WANT_DEF, True)), (rc2, err2, out["after_rerun"])


CLASHES = [
    ("display_name_at_ban", "ALTER TABLE player_bans ADD COLUMN display_name_at_ban integer",
     "player_bans.display_name_at_ban is integer, not text"),
    ("details", "ALTER TABLE player_bans ADD COLUMN details character varying(50)",
     "player_bans.details is character varying, not text"),
    ("details_at", "ALTER TABLE player_bans ADD COLUMN details_at timestamp without time zone",
     "player_bans.details_at is timestamp without time zone, not timestamp with time zone"),
    ("constraint", "ALTER TABLE player_bans ADD COLUMN details text;"
                   " ALTER TABLE player_bans ADD CONSTRAINT ck_player_bans_details_len CHECK (details <> '')",
     "ck_player_bans_details_len is CHECK ((details <> ''::text)), not the validated CHECK 429 adds"),
]


@pytest.mark.parametrize("name,ddl,message", CLASHES, ids=[c[0] for c in CLASHES])
def test_v1_429_refuses_a_name_that_stands_with_another_shape(case, name, ddl, message):
    async def go():
        conn = await harness.connect_bound(lh.DSN, case)
        out = {}
        try:
            rc, err = _psql_apply(case, R429)
            assert rc == 0 and await _cols(conn) == [], err
            await conn.execute(ddl)
            out["before"] = (await _cols(conn), await _con(conn))
            out["run"] = _psql_apply(case, M429)
            out["after"] = (await _cols(conn), await _con(conn))
            if name != "constraint":
                out["rollback"] = _psql_apply(case, R429)
                out["after_rollback"] = await _cols(conn)
            await conn.execute("ALTER TABLE player_bans DROP CONSTRAINT IF EXISTS ck_player_bans_details_len")
            await conn.execute("ALTER TABLE player_bans DROP COLUMN IF EXISTS %s" % (
                "details" if name == "constraint" else name))
            out["last"] = _psql_apply(case, M429)
            out["after_last"] = (await _cols(conn), await _con(conn))
        finally:
            await conn.close()
        return out
    out = _run(go())
    rc, err = out["run"]
    _say("clash " + name, rc, err)
    assert rc != 0 and message in err, err
    assert out["after"] == out["before"], (out["before"], out["after"])        # nothing applied
    if name != "constraint":
        rc_r, err_r = out["rollback"]
        _say("rollback over the clash " + name, rc_r, err_r)
        assert rc_r != 0 and "has another type; nothing dropped" in err_r, err_r
        assert out["after_rollback"] == out["before"][0], out["after_rollback"]
    assert out["last"][0] == 0 and out["after_last"] == (WANT_COLS, (WANT_DEF, True)), (out["last"], out["after_last"])


def test_v1_the_files_carry_their_order_and_their_transaction():
    """No database: each file is its own transaction with its bounds, and
    429's header names the deploy order (the file first, then the api)."""
    for path in (M429, R429):
        src = io.open(path, encoding="utf-8").read()
        for line in ("BEGIN ISOLATION LEVEL READ COMMITTED;", "SET LOCAL lock_timeout = '5s';",
                     "SET LOCAL idle_in_transaction_session_timeout = '5s';",
                     "SET LOCAL statement_timeout = '25s';", "SET LOCAL synchronous_commit = local;", "COMMIT;"):
            assert line in src, (os.path.basename(path), line)
    head = io.open(M429, encoding="utf-8").read()
    assert "DEPLOY ORDER: THIS FILE FIRST, then the api" in head
    assert "<= %d" % models.BAN_DETAILS_MAX in head
