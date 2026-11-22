"""CHEAT-ALT-1 step 4: account deletion removes the account's rows of the
three alternate-account signal tables (items 11 and 12), against a real
PostgreSQL.

  * The three DELETEs run right after the identity key, before the player
    read, and both early answers (not_found, already_deleted) commit them: an
    identity with no players row loses its rows too, its answer is unchanged
    and no tombstone is written for it.
  * Each DELETE runs in its own savepoint and tolerates exactly one failure,
    the table not existing (42P01). Any other failure fails the deletion and
    nothing of it is committed.
  * Deletion and the recording serialize on the account's identity key: a
    transaction that holds the key the way the recording takes it makes the
    deletion wait, and the row it commits is gone afterwards.

One case schema for the module, built by the ladder harness's procedure
(test_title_ladder_hooks_live._build) with one fault table and a BEFORE
DELETE fault trigger on each of the three tables (a row (table, SQLSTATE)
makes a delete of a row of that table raise that SQLSTATE), sealed, and
dropped at the end:

    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    LADDER_TEST_PG_OPTOUT=1   waives the live cases deliberately (else they FAIL)

Ids are synthetic (below the first individual-account SteamID64).
"""
import asyncio
import hashlib
import hmac
import itertools
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import main  # noqa: E402
import cf_asm  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402

DELETE_SECRET = "alt-delete-secret"
TABLES = ("conn_markers", "steam_family_shares", "steam_signin_facts")
BOUNDS = {"lock_timeout": "10s", "statement_timeout": "120s"}
_IDS = itertools.count(1)

_FAULTS_DDL = """
CREATE TABLE alt_test_faults (tbl text PRIMARY KEY, what text NOT NULL);
CREATE FUNCTION alt_test_fault() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE w text;
BEGIN
  SELECT f.what INTO w FROM alt_test_faults f WHERE f.tbl = TG_TABLE_NAME;
  IF w IS NOT NULL THEN
    RAISE EXCEPTION 'planted fault on %', TG_TABLE_NAME USING ERRCODE = w;
  END IF;
  RETURN OLD;
END $f$;
CREATE TRIGGER alt_test_fault BEFORE DELETE ON steam_signin_facts
  FOR EACH ROW EXECUTE FUNCTION alt_test_fault();
CREATE TRIGGER alt_test_fault BEFORE DELETE ON steam_family_shares
  FOR EACH ROW EXECUTE FUNCTION alt_test_fault();
CREATE TRIGGER alt_test_fault BEFORE DELETE ON conn_markers
  FOR EACH ROW EXECUTE FUNCTION alt_test_fault();
"""


def _sid():
    """A fresh synthetic 17-digit id below 76561197960265728."""
    return "76561190428%06d" % next(_IDS)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def case():
    lh._require_live_pg()
    built = {}

    async def extra(conn, schema):
        await conn.execute(_FAULTS_DDL)

    async def build():
        c = harness.CaseSchema(lh.DSN, "alt_delete")
        await c.__aenter__()
        try:
            await lh._build(c, extra)
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


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", DELETE_SECRET)
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)
    return DELETE_SECRET


def _with(schema, body):
    async def go():
        engine = create_async_engine(
            harness.async_dsn(lh.DSN), poolclass=NullPool,
            connect_args={"server_settings": {"search_path": harness.quoted(schema), **BOUNDS}})
        try:
            return await body(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()
    return _run(go())


async def _plant(sm, sid):
    """One row of each table for `sid` (marks are fixed 32-byte values)."""
    mark = hashlib.sha256(sid.encode()).digest()
    async with sm() as db:
        await db.execute(text("INSERT INTO steam_signin_facts (steam_id) VALUES (:s)"), {"s": sid})
        await db.execute(text("INSERT INTO steam_family_shares (steam_id, key_id, owner_mark)"
                              " VALUES (:s, 'aaaaaaaaaaaa', :m)"), {"s": sid, "m": mark})
        await db.execute(text("INSERT INTO conn_markers (steam_id, key_id, addr_mark, block_mark, family)"
                              " VALUES (:s, 'aaaaaaaaaaaa', :m, :m, 4)"), {"s": sid, "m": mark})
        await db.commit()


async def _player(sm, sid, deleted=False):
    async with sm() as db:
        values = {"id": uuid.uuid4(), "steam_id": sid, "display_name": "ad-" + sid[-4:]}
        await lh._insert(db, "players", values)
        if deleted:
            await db.execute(text("UPDATE players SET deleted_at = NOW() WHERE steam_id = :s"), {"s": sid})
        await db.commit()
        return values["id"]


async def _rows(sm, sid):
    async with sm() as db:
        return [(await db.execute(text("SELECT count(*) FROM %s WHERE steam_id = :s" % t),
                                  {"s": sid})).scalar() for t in TABLES]


async def _delete(sm, sid):
    sig = hmac.new(DELETE_SECRET.encode(), ("delete:%s" % sid).encode(), hashlib.sha256).hexdigest()
    async with sm() as db:
        return await main.delete_player_data(sid, cf_asm.FakeRequest(), sig=sig, _slot=None, db=db)


async def _fault(sm, table, what):
    async with sm() as db:
        if what is None:
            await db.execute(text("DELETE FROM alt_test_faults WHERE tbl = :t"), {"t": table})
        else:
            await db.execute(text("INSERT INTO alt_test_faults (tbl, what) VALUES (:t, :w)"
                                  " ON CONFLICT (tbl) DO UPDATE SET what = EXCLUDED.what"),
                             {"t": table, "w": what})
        await db.commit()


async def _rename(sm, table, to):
    async with sm() as db:
        await db.execute(text('ALTER TABLE "%s" RENAME TO "%s"' % (table, to)))
        await db.commit()


def test_an_identity_with_no_player_row_loses_its_rows_and_answers_as_before(case, secret):
    sid, other = _sid(), _sid()

    async def body(sm):
        await _plant(sm, sid)
        await _plant(sm, other)
        ans = await _delete(sm, sid)
        async with sm() as db:
            tomb = (await db.execute(text("SELECT count(*) FROM deleted_steam_ids WHERE steam_id_hash = :h"),
                                     {"h": main._hash_steam_id(sid)})).scalar()
        return ans, await _rows(sm, sid), await _rows(sm, other), tomb

    ans, rows, other_rows, tomb = _with(case, body)
    assert ans == {"status": "not_found", "steam_id": sid}
    assert rows == [0, 0, 0] and other_rows == [1, 1, 1]
    assert tomb == 0, "a tombstone was written for an identity that never enrolled"


def test_a_player_row_marked_deleted_answers_as_before_and_loses_its_rows(case, secret):
    sid = _sid()

    async def body(sm):
        await _player(sm, sid, deleted=True)
        await _plant(sm, sid)
        return await _delete(sm, sid), await _rows(sm, sid)

    ans, rows = _with(case, body)
    assert ans == {"status": "already_deleted", "steam_id": sid}
    assert rows == [0, 0, 0]


def test_a_deleted_player_loses_its_rows_and_another_account_keeps_its_own(case, secret):
    sid, other = _sid(), _sid()

    async def body(sm):
        await _player(sm, sid)
        await _plant(sm, sid)
        await _plant(sm, other)
        return await _delete(sm, sid), await _rows(sm, sid), await _rows(sm, other)

    ans, rows, other_rows = _with(case, body)
    assert ans["status"] == "anonymized", ans
    assert rows == [0, 0, 0] and other_rows == [1, 1, 1]


def test_deletion_waits_for_the_holder_of_the_identity_key_and_then_takes_its_row(case, secret):
    """A transaction that takes the account's key as the recording does
    (_ban_lock_and_gate, the key exclusive) and writes a facts row makes the
    deletion wait; once it commits, the deletion runs and the row is gone.
    The other order, deletion first, is the recording's re-read of the
    deletion stamp under the key (test_alt_signals_record_pg.py)."""
    sid = _sid()

    async def body(sm):
        await _player(sm, sid)
        async with sm() as holder:
            await main._ban_lock_and_gate(holder, [sid], exclusive=[sid])
            await holder.execute(text("INSERT INTO steam_signin_facts (steam_id) VALUES (:s)"), {"s": sid})
            deletion = asyncio.create_task(_delete(sm, sid))
            await asyncio.sleep(1.0)
            waited = not deletion.done()
            await holder.commit()
        ans = await asyncio.wait_for(deletion, 30)
        return waited, ans, await _rows(sm, sid)

    waited, ans, rows = _with(case, body)
    assert waited, "the deletion did not wait for the holder of the account's key"
    assert ans["status"] == "anonymized", ans
    assert rows == [0, 0, 0]


@pytest.mark.parametrize("absent",[(t,) for t in TABLES] + [TABLES], ids=list(TABLES) + ["all three"])
def test_an_absent_table_is_tolerated_and_the_deletion_completes(case, secret, absent):
    sid = _sid()

    async def body(sm):
        await _player(sm, sid)
        await _plant(sm, sid)
        for t in absent:
            await _rename(sm, t, t + "_away")
        try:
            ans = await _delete(sm, sid)
        finally:
            for t in absent:
                await _rename(sm, t + "_away", t)
        async with sm() as db:
            left = (await db.execute(text("SELECT count(*) FROM players WHERE steam_id = :s"), {"s": sid})).scalar()
        return ans, left, await _rows(sm, sid)

    ans, left, rows = _with(case, body)
    assert ans["status"] == "anonymized" and left == 0, (ans, left)
    assert rows == [1 if t in absent else 0 for t in TABLES], rows


@pytest.mark.parametrize("what", ["P0001", "42703", "40P01"])
@pytest.mark.parametrize("table", TABLES)
def test_any_other_failure_fails_the_deletion_and_commits_nothing(case, secret, table, what):
    """An ordinary error, an undefined column (the other half of the schema
    rule another route tolerates) and a deadlock error each fail the
    deletion: the player row stays as it was and every planted row stays."""
    sid = _sid()

    async def body(sm):
        await _player(sm, sid)
        await _plant(sm, sid)
        await _fault(sm, table, what)
        try:
            with pytest.raises(Exception) as got:
                await _delete(sm, sid)
        finally:
            await _fault(sm, table, None)
        async with sm() as db:
            row = (await db.execute(text("SELECT deleted_at FROM players WHERE steam_id = :s"),
                                    {"s": sid})).all()
        return got.value, row, await _rows(sm, sid)

    exc, row, rows = _with(case, body)
    assert len(row) == 1 and row[0][0] is None, row
    assert rows == [1, 1, 1], rows
    assert not main._alt_table_missing(exc)


def test_the_table_rule_tolerates_42p01_alone_on_the_wrapping_chain():
    """The rule reads the SQLSTATE of the error and of every error it wraps
    (.orig, and the explicit cause of `raise ... from`), and tolerates only a
    chain whose one state is 42P01. An error raised while handling another
    (__context__) does not wrap it."""
    import asyncpg

    class Wrapped(Exception):
        def __init__(self, orig):
            super().__init__("wrapped")
            self.orig = orig

    class Coded(Exception):
        def __init__(self, code, attr="sqlstate"):
            super().__init__(code)
            setattr(self, attr, code)

    def raised(outer, cause):
        try:
            raise outer from cause
        except Exception as e:
            return e

    assert main._alt_table_missing(asyncpg.exceptions.UndefinedTableError("x"))
    assert main._alt_table_missing(Coded("42P01", attr="pgcode"))
    assert main._alt_table_missing(Wrapped(Coded("42P01")))
    assert main._alt_table_missing(raised(Wrapped(Coded("42P01")),
                                          asyncpg.exceptions.UndefinedTableError("x")))
    assert main._alt_table_missing(raised(Exception("adapter"), asyncpg.exceptions.UndefinedTableError("x")))
    for exc in (asyncpg.exceptions.UndefinedColumnError("x"), Coded("42703"), Coded("40P01"),
                Coded("42703", attr="pgcode"), Wrapped(Coded("42703")), ValueError("x"),
                raised(Wrapped(Coded("P0001")), Coded("42P01")),       # another state on the chain
                raised(Wrapped(Coded("42P01")), Coded("42703"))):
        assert not main._alt_table_missing(exc), (exc, getattr(exc, "__cause__", None))
    try:
        try:
            raise Coded("42P01")
        except Coded:
            raise ValueError("raised while handling")
    except ValueError as e:
        assert not main._alt_table_missing(e)        # __context__ is not wrapping
