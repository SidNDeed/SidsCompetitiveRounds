"""Migration 404 and the mail statements it serves, executed on a real
PostgreSQL: the migration and rollback files as they are, and every
statement as main.py holds it (the three sender-clock reads as the routes
issue them, recorded through test_mail.py's fake), never retyped.

Each test makes a throwaway schema holding players, mail_messages and
mail_recipients as 297 creates them (with 300's recipient_count and 330's
via) and stubs for the other tables a statement reads, and drops it
afterwards. Every test pairs a control with a mutant -- the statement or
the file with one predicate taken out -- and the mutant must change what the
control pins.

Runs against SCR_MIGRATION_TEST_PG_DSN and fails, not skips, without it
unless SCR_MIGRATION_TEST_PG_OPTOUT=1 (test_migration_reruns.py's polarity).
"""

import ast
import asyncio
import inspect
import os
import re
import textwrap
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import main
import mail_discord

try:
    import asyncpg
except ImportError:                                    # pragma: no cover
    asyncpg = None

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
DSN_VAR = "SCR_MIGRATION_TEST_PG_DSN"
OPTOUT_VAR = "SCR_MIGRATION_TEST_PG_OPTOUT"
DSN = (os.environ.get(DSN_VAR) or "").replace("postgresql+asyncpg://", "postgresql://")
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"

M404 = (SQL_DIR / "404_mail_send_receipts.sql").read_text(encoding="utf-8")
R404 = (SQL_DIR / "rollback_404_mail_send_receipts.sql").read_text(encoding="utf-8")
SENDER_CLOCK = "AND m.created_at > NOW() - make_interval(days => CAST(:ret_days AS integer))"
DAYS = main.MAIL_RETENTION_DAYS

A, B, C, D = ("00000000-0000-0000-0000-00000000a404", "00000000-0000-0000-0000-00000000b404",
              "00000000-0000-0000-0000-00000000c404", "00000000-0000-0000-0000-00000000d404")
_BIND = re.compile(r"(?<!:):([A-Za-z_]\w*)\b")


@pytest.fixture(autouse=True)
def _require_live_pg():
    """Fail, not skip, when the cluster is missing and nobody waived it."""
    if DSN and asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: migration 404's PostgreSQL coverage deliberately "
                    "waived for this run." % (DSN_VAR, OPTOUT_VAR))
    if asyncpg is None:
        pytest.fail("asyncpg is not installed, so migration 404's PostgreSQL coverage did not "
                    "run. Install it, or set %s=1 to waive it deliberately." % OPTOUT_VAR)
    pytest.fail("%s is unset, so migration 404 and its statements were not run on PostgreSQL. "
                "Point it at a throwaway cluster, or set %s=1 to waive the coverage deliberately."
                % (DSN_VAR, OPTOUT_VAR))


# ── helpers ───────────────────────────────────────────────────────────────

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _mutated(text, old, new):
    """A mutant: `text` with its one occurrence of `old` replaced."""
    assert text.count(old) == 1, ("mutant anchor occurs %d times" % text.count(old), old)
    return text.replace(old, new)


def _bind(sql, params):
    """SQLAlchemy ':name' binds to asyncpg '$n' for the names the statement
    uses, in `params` order; returns the statement and its arguments. A bind
    left over that `params` does not name fails here."""
    args = []
    for name, value in params.items():
        pattern = r"(?<!:):%s\b" % name
        if re.search(pattern, sql):
            args.append(value)
            sql = re.sub(pattern, "$%d" % len(args), sql)
    left = _BIND.findall(sql)
    assert not left, ("unbound", left, sql)
    return sql, args


def _from_file(name, pattern):
    found = re.search(pattern, (SQL_DIR / name).read_text(encoding="utf-8"), re.S)
    assert found, (name, pattern)
    return found.group(0)


def _base_sql():
    return "\n".join([
        "CREATE TABLE shop_items (id BIGINT PRIMARY KEY, name TEXT, preview_color TEXT, sku TEXT);",
        "CREATE TABLE players (id UUID PRIMARY KEY, steam_id VARCHAR(32), display_name VARCHAR(64),"
        " active_title_id BIGINT, mail_from TEXT NOT NULL DEFAULT 'everyone', deleted_at TIMESTAMPTZ);",
        "CREATE TABLE glicko_ratings (player_id UUID PRIMARY KEY, rating INTEGER);",
        "CREATE TABLE mail_blocks (blocker_id UUID, blocked_id UUID);",
        "CREATE TABLE matches (player1_id UUID, player2_id UUID);",
        "CREATE TABLE team_matches (t1a_id UUID, t1b_id UUID, t2a_id UUID, t2b_id UUID);",
        "CREATE TABLE ffa_match_players (match_id UUID, player_id UUID);",
        "CREATE TABLE ovt_matches (solo_id UUID, duo_a_id UUID, duo_b_id UUID);",
        "CREATE TABLE pending_dms (id BIGSERIAL PRIMARY KEY, mail_id UUID, steam_id VARCHAR(32),"
        " relay_code TEXT, undeliverable BOOLEAN NOT NULL DEFAULT false);",
        _from_file("297_mail.sql", r"CREATE TABLE IF NOT EXISTS mail_messages \(.*?\n\);"),
        _from_file("297_mail.sql", r"CREATE TABLE IF NOT EXISTS mail_recipients \(.*?\n\);"),
        _from_file("300_mail_inbox_rev.sql", re.escape(
            "ALTER TABLE mail_messages ADD COLUMN IF NOT EXISTS recipient_count INTEGER NULL;")),
        "ALTER TABLE mail_messages " + _from_file("330_mail_discord_relay.sql", re.escape(
            "ADD COLUMN IF NOT EXISTS via TEXT NOT NULL DEFAULT 'game';")),
        "INSERT INTO players (id, steam_id, display_name) VALUES "
        "('%s', '1', 'A'), ('%s', '2', 'B'), ('%s', '3', 'C'), ('%s', '4', 'D');" % (A, B, C, D),
    ])


class _Schema:
    """A throwaway schema holding _base_sql(), alone on the search path."""

    async def __aenter__(self):
        self.name = "t404_%s" % uuid.uuid4().hex[:10]
        self.conn = await asyncpg.connect(DSN)
        try:
            await self.conn.execute('CREATE SCHEMA "%s"' % self.name)
            await self.conn.execute('SET search_path TO "%s"' % self.name)
            await self.conn.execute(_base_sql())
        except BaseException:
            await self.__aexit__()
            raise
        return self.conn

    async def __aexit__(self, *exc):
        try:
            if self.conn.is_in_transaction():
                await self.conn.execute("ROLLBACK")
            await self.conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % self.name)
        finally:
            await self.conn.close()
        return False


async def _message(conn, sender=A, kind="direct", key=None, count=None, at=None):
    mid = str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO mail_messages (id, sender_id, kind, thread_id, subject, body, idempotency_key,"
        " created_at, recipient_count) VALUES ($1, $2, $3, $1, 's', 'b', $4, COALESCE($5, NOW()), $6)",
        mid, sender, kind, key or str(uuid.uuid4()), at, count)
    return mid


async def _envelope(conn, mid, rid, delivery="delivered", kind="to"):
    await conn.execute("INSERT INTO mail_recipients (message_id, recipient_id, kind, delivery)"
                       " VALUES ($1, $2, $3, $4)", mid, rid, kind, delivery)


async def _receipts(conn):
    rows = await conn.fetch("SELECT message_id::text AS mid, kind, recipients, request_fp,"
                            " created_at = (SELECT m.created_at FROM mail_messages m"
                            "                WHERE m.id = message_id) AS same_at"
                            " FROM mail_send_receipts")
    return {r["mid"]: (r["kind"], r["recipients"], r["request_fp"], r["same_at"]) for r in rows}


async def _receipt(conn, sid, key):
    r = await conn.fetchrow("SELECT message_id::text AS mid, kind, recipients, request_fp"
                            " FROM mail_send_receipts WHERE sender_id = $1 AND idempotency_key = $2",
                            sid, key)
    return None if r is None else (r["mid"], r["kind"], r["recipients"], r["request_fp"])


async def _shape(conn):
    """Which of 404's objects exist, and whether 297's constraint does."""
    row = await conn.fetchrow("""
        SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = current_schema() AND c.relname = 'mail_send_receipts') AS tbl,
               EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                        WHERE n.nspname = current_schema() AND p.proname = 'mail_send_receipt_sync') AS fn,
               EXISTS (SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
                         JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = current_schema() AND t.tgname = 'trg_mail_send_receipt') AS trg,
               EXISTS (SELECT 1 FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
                         JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = current_schema()
                          AND k.conname = 'uq_mail_messages_sender_idem') AS uq""")
    return {"table": row["tbl"], "function": row["fn"], "trigger": row["trg"], "uq": row["uq"]}


APPLIED = {"table": True, "function": True, "trigger": True, "uq": False}
ROLLED_BACK = {"table": False, "function": False, "trigger": False, "uq": True}


# ── the migration ─────────────────────────────────────────────────────────

def test_the_backfill_gives_every_message_its_receipt_with_the_previous_answer():
    """A direct message, a broadcast with its count, and a broadcast written
    before 300 (no count; two delivered envelopes and one suppressed): the
    receipt replays what the previous build's replay answered for each."""
    async def body(migration):
        async with _Schema() as conn:
            t0 = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
            direct = await _message(conn, at=t0)
            counted = await _message(conn, kind="system_broadcast", count=3, at=t0 + timedelta(days=1))
            uncounted = await _message(conn, kind="system_broadcast", at=t0 + timedelta(days=2))
            for rid, delivery in ((B, "delivered"), (C, "delivered"), (D, "suppressed")):
                await _envelope(conn, uncounted, rid, delivery)
            await conn.execute(migration)
            return await _receipts(conn), (direct, counted, uncounted), await _shape(conn)
    got, (direct, counted, uncounted), shape = _run(body(M404))
    assert shape == APPLIED
    assert got == {direct: ("direct", None, None, True), counted: ("system_broadcast", 3, None, True),
                   uncounted: ("system_broadcast", 2, None, True)}
    # mutant: the envelope count without its delivery filter -> the receipt
    # would replay a count the previous build never answered
    got, (_d, _c, uncounted), _shape_ = _run(body(_mutated(
        M404, "WHERE r.message_id = m.id AND r.delivery = 'delivered'", "WHERE r.message_id = m.id")))
    assert got[uncounted][1] == 3


def test_the_trigger_writes_a_receipt_and_the_first_count_wins():
    """The previous build's writes on the migrated schema: the INSERT gives a
    receipt with no digest, its UPDATE of recipient_count fills the count
    once, and no other UPDATE reaches the receipt."""
    async def body(migration):
        async with _Schema() as conn:
            await conn.execute(migration)
            direct = await _message(conn)
            bcast = await _message(conn, kind="system_broadcast")
            inserted = await _receipts(conn)
            await conn.execute("UPDATE mail_messages SET recipient_count = 5 WHERE id = $1", bcast)
            await conn.execute("UPDATE mail_messages SET recipient_count = 7 WHERE id = $1", bcast)
            await conn.execute("UPDATE mail_messages SET deleted_by_sender_at = NOW() WHERE id = $1", direct)
            return inserted, await _receipts(conn), direct, bcast
    inserted, final, direct, bcast = _run(body(M404))
    assert inserted == {direct: ("direct", None, None, True), bcast: ("system_broadcast", None, None, True)}
    assert final == {direct: ("direct", None, None, True), bcast: ("system_broadcast", 5, None, True)}
    # mutant: the UPDATE arm without `recipients IS NULL` -> a later count
    # overwrites the one the send answered with
    _inserted, final, _direct, bcast = _run(body(_mutated(M404, "\n       AND recipients IS NULL;", ";")))
    assert final[bcast][1] == 7


def test_the_post_check_accepts_matching_objects_and_refuses_differing_ones():
    """A same-named table made before the file (as the api build's own table
    creation would make it, deployed out of order) is accepted when it
    matches the file's definition; one that differs -- a column's type, or a
    check's expression under its own name -- aborts the whole file. So does
    a same-named trigger whose WHEN condition differs, while one made as the
    file makes it is accepted."""
    same = ("CREATE TABLE mail_send_receipts (sender_id UUID NOT NULL, idempotency_key UUID NOT NULL,"
            " kind TEXT NOT NULL, request_fp BYTEA, message_id UUID NOT NULL, recipients INTEGER,"
            " created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY (sender_id, idempotency_key),"
            " CONSTRAINT ck_mail_send_receipts_kind CHECK (kind IN ('direct', 'system_broadcast')),"
            " CONSTRAINT ck_mail_send_receipts_fp CHECK (request_fp IS NULL OR octet_length(request_fp) = 32),"
            " CONSTRAINT ck_mail_send_receipts_recipients CHECK (recipients IS NULL OR recipients >= 0));")

    async def body(pre):
        async with _Schema() as conn:
            await conn.execute(pre)
            try:
                await conn.execute(M404)
                refused = None
            except asyncpg.PostgresError as e:
                refused = str(e)
                await conn.execute("ROLLBACK")
            return refused, await _shape(conn)
    assert _run(body(same)) == (None, APPLIED)
    refused, shape = _run(body(_mutated(same, "created_at TIMESTAMPTZ", "created_at TIMESTAMP")))
    assert refused and "404: mail_send_receipts columns differ" in refused
    assert shape == {"table": True, "function": False, "trigger": False, "uq": True}   # nothing else changed
    refused, shape = _run(body(_mutated(same, "recipients IS NULL OR recipients >= 0",
                                        "recipients IS NULL OR recipients >= 1")))
    assert refused and "404: mail_send_receipts key or checks differ" in refused
    assert "ck_mail_send_receipts_recipients CHECK" in refused and "recipients >= 1" in refused   # what it found
    assert shape == {"table": True, "function": False, "trigger": False, "uq": True}

    fn = ("CREATE FUNCTION mail_send_receipt_sync() RETURNS trigger LANGUAGE plpgsql"
          " AS $f$BEGIN RETURN NULL; END$f$;")
    trg = ("CREATE TRIGGER trg_mail_send_receipt AFTER INSERT OR UPDATE OF recipient_count"
           " ON mail_messages FOR EACH ROW WHEN (NEW.kind IN ('direct', 'system_broadcast'))"
           " EXECUTE FUNCTION mail_send_receipt_sync();")
    assert _run(body(fn + trg)) == (None, APPLIED)
    refused, shape = _run(body(fn + _mutated(trg, "NEW.kind IN ('direct', 'system_broadcast')",
                                             "NEW.kind = 'direct'")))
    assert refused and "404: trg_mail_send_receipt or its function differs" in refused
    assert "new.kind = 'direct'" in refused                                  # what it found
    assert shape == {"table": False, "function": True, "trigger": True, "uq": True}


# ── the api's statements ──────────────────────────────────────────────────

def test_the_api_upsert_completes_its_own_row_and_refuses_another_message():
    fp1, fp2 = bytes(range(32)), bytes(range(1, 33))

    async def body(sql):
        async with _Schema() as conn:
            await conn.execute(M404)
            key = str(uuid.uuid4())
            mid = await _message(conn, key=key)                      # the trigger's row: no digest
            stmt = lambda **p: _bind(sql, p)                         # noqa: E731
            own = await conn.fetchval(*_flat(stmt(sid=A, key=key, kind="direct", fp=fp1, mid=mid, n=None)))
            after_own = await _receipt(conn, A, key)
            other = await conn.fetchval(*_flat(stmt(sid=A, key=key, kind="direct", fp=fp2,
                                                    mid=str(uuid.uuid4()), n=None)))
            after_other = await _receipt(conn, A, key)
            # without the trigger, the upsert alone writes the whole row
            await conn.execute("DROP TRIGGER trg_mail_send_receipt ON mail_messages")
            key2 = str(uuid.uuid4())
            mid2 = await _message(conn, kind="system_broadcast", key=key2, count=4)
            alone = await conn.fetchval(*_flat(stmt(sid=A, key=key2, kind="system_broadcast", fp=fp1,
                                                    mid=mid2, n=4)))
            return (own, after_own, other, after_other, alone, await _receipt(conn, A, key2), mid, mid2)
    own, after_own, other, after_other, alone, row2, mid, mid2 = _run(body(main._MAIL_RECEIPT_SQL))
    assert own == 1 and after_own == (mid, "direct", None, fp1)
    assert other is None and after_other == after_own
    assert alone == 1 and row2 == (mid2, "system_broadcast", 4, fp1)
    # mutant: the upsert's WHERE taken out -> another message's request
    # replaces the digest on this message's receipt
    where = "   WHERE mail_send_receipts.message_id = EXCLUDED.message_id"
    # (each run makes its own messages: compare with this run's message id)
    _own, _after_own, other, after_other, _alone, _row2, m_mid, _m_mid2 = _run(
        body(_mutated(main._MAIL_RECEIPT_SQL, where, "")))
    assert other == 1 and after_other[0] == m_mid and after_other[3] == fp2


def _flat(bound):
    sql, args = bound
    return (sql, *args)


def test_the_replay_reads_the_receipt_after_the_message_is_purged():
    async def body(sql):
        async with _Schema() as conn:
            await conn.execute(M404)
            key = str(uuid.uuid4())
            mid = await _message(conn, kind="system_broadcast", key=key)
            await conn.execute("UPDATE mail_messages SET recipient_count = 3 WHERE id = $1", mid)
            await conn.execute("DELETE FROM mail_messages WHERE id = $1", mid)    # the janitor's purge
            row = await conn.fetchrow(*_flat(_bind(sql, {"sid": A, "key": key})))
            return None if row is None else dict(row), mid
    row, mid = _run(body(main._MAIL_PRIOR_SEND_SQL))
    assert row is not None
    assert (str(row["message_id"]), row["kind"], row["recipients"], row["request_fp"]) == \
        (mid, "system_broadcast", 3, None)
    # mutant: the previous build's replay read, of the message row -> after
    # the purge nothing answers the key
    previous = ("SELECT id, kind, recipient_count FROM mail_messages"
                " WHERE sender_id = :sid AND idempotency_key = :key")
    assert _run(body(previous))[0] is None


def test_the_sweep_deletes_receipts_older_than_retention_and_no_other():
    async def body(sql):
        async with _Schema() as conn:
            await conn.execute(M404)
            for days in (DAYS + 1, DAYS - 1):
                await conn.execute(
                    "INSERT INTO mail_send_receipts (sender_id, idempotency_key, kind, message_id, created_at)"
                    " VALUES ($1, $2, 'direct', $3, NOW() - make_interval(days => $4))",
                    A, str(uuid.uuid4()), str(uuid.uuid4()), days)
            gone = await conn.fetch(*_flat(_bind(sql, {"days": DAYS})))
            left = await conn.fetch("SELECT created_at < NOW() - make_interval(days => $1) AS old"
                                    " FROM mail_send_receipts", DAYS)
            return len(gone), [r["old"] for r in left]
    assert _run(body(main._MAIL_RECEIPT_SWEEP_SQL)) == (1, [False])
    # mutant: the comparison turned round -> the young receipt goes instead
    assert _run(body(_mutated(main._MAIL_RECEIPT_SWEEP_SQL, "created_at < NOW()", "created_at > NOW()"))) \
        == (1, [True])


def test_the_fanout_writes_a_forced_addressee_suppressed_whatever_their_settings():
    """C takes mail from everyone and has blocked nobody; passed forced, C's
    copy is suppressed all the same."""
    async def body(sql):
        async with _Schema() as conn:
            await conn.execute(M404)
            mid = await _message(conn)
            await conn.execute(*_flat(_bind(sql, {
                "mid": mid, "sid": A, "rids": [B, C, D], "kinds": ["to", "to", "cc"],
                "forced": [False, True, False]})))
            rows = await conn.fetch("SELECT recipient_id::text AS rid, kind, delivery FROM mail_recipients"
                                    " WHERE message_id = $1", mid)
            return {r["rid"]: (r["kind"], r["delivery"]) for r in rows}
    assert _run(body(main._MAIL_FANOUT_SQL)) == {
        B: ("to", "delivered"), C: ("to", "suppressed"), D: ("cc", "delivered")}
    # mutant: the forced arm taken out -> C is delivered the copy
    got = _run(body(_mutated(main._MAIL_FANOUT_SQL, "WHEN a.forced THEN 'suppressed'", "")))
    assert got[C] == ("to", "delivered")


def _sender_reads(monkeypatch):
    """Sent, the detail read and the reply's original read, as the routes
    issue them: recorded by running the routes against test_mail.py's fake,
    so the text run below is main.py's own."""
    import test_mail as tm
    monkeypatch.setattr(main, "_utc_now", lambda: tm.NOW)
    db, _ids = tm._world()
    orig = tm._send(db, [tm.B_SID])
    tm._run(main.mail_sent(tm._req("tokA"), "", 25, db))
    tm._run(main.mail_detail(orig["id"], tm._req("tokA"), db))
    tm._run(main.mail_reply(orig["id"], main._MailReplyReq(body="x", all=True, idempotency_key=str(uuid.uuid4())),
                            tm._req("tokA"), db))
    out = {}
    for name, needle in (("sent", "WHERE m.sender_id = :me AND m.deleted_by_sender_at IS NULL"),
                         ("detail", "LEFT JOIN mail_recipients r ON r.message_id = m.id AND r.recipient_id = :me"),
                         ("reply", "SELECT m.id, m.sender_id, m.kind, m.thread_id, m.subject")):
        found = {s for s in db.statements if needle in s}
        assert len(found) == 1, (name, found)
        out[name] = found.pop()
        assert SENDER_CLOCK in out[name], name
    return out


def test_the_senders_three_reads_follow_the_clock(monkeypatch):
    """A's messages to B, one sent DAYS+1 days ago and one DAYS-1 days ago,
    both delivered and unread (so the janitor keeps both rows): A's Sent,
    detail and reply reach the young one only; B's detail reaches both."""
    reads = _sender_reads(monkeypatch)

    async def body(reads):
        async with _Schema() as conn:
            await conn.execute(M404)
            now = datetime.now(timezone.utc)
            old = await _message(conn, at=now - timedelta(days=DAYS + 1))
            young = await _message(conn, at=now - timedelta(days=DAYS - 1))
            for mid in (old, young):
                await _envelope(conn, mid, B)
            rows = await conn.fetch(*_flat(_bind(reads["sent"], {
                "me": A, "c_at": None, "c_id": None, "lim": 26, "ret_days": DAYS})))
            out = {"sent": {str(r["id"]) for r in rows}}
            for name, stmt, me in (("detail", reads["detail"], A), ("reply", reads["reply"], A),
                                   ("recipient", reads["detail"], B)):
                out[name] = set()
                for mid in (old, young):
                    if await conn.fetchrow(*_flat(_bind(stmt, {"mid": mid, "me": me, "ret_days": DAYS}))):
                        out[name].add(mid)
            return out, old, young
    out, old, young = _run(body(reads))
    assert out == {"sent": {young}, "detail": {young}, "reply": {young}, "recipient": {old, young}}
    # mutant: the clock taken out of all three -> the sender reaches the old
    # message for as long as its row exists
    out, old, young = _run(body({k: _mutated(v, SENDER_CLOCK, "") for k, v in reads.items()}))
    assert out == {"sent": {old, young}, "detail": {old, young}, "reply": {old, young},
                   "recipient": {old, young}}


def _sql_in(fn, prefix):
    """The one `text(...)` statement in `fn`'s source that starts with
    `prefix`, as production passes it."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    found = [n.args[0].value for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "text" and n.args
             and isinstance(n.args[0], ast.Constant) and str(n.args[0].value).startswith(prefix)]
    assert len(found) == 1, (fn.__name__, prefix, found)
    return found[0]


def _janitor_purge_sql():
    """The janitor's purge statement, read out of _mail_retention_sweep."""
    return _sql_in(main._mail_retention_sweep, "DELETE FROM mail_messages")


def test_the_rate_window_counts_receipts_whatever_the_purge_removed():
    """_mail_rate_or_raise's statement on PostgreSQL. A's direct sends 10,
    20 and 30 s ago and 2 h ago, one 2 days ago, and a broadcast 5 s ago:
    3 in the minute and 4 in the day. The rows of the 10 s and 20 s sends
    are then deleted as the janitor's purge deletes them (their receipts
    have no foreign key and stay): the counts do not move."""
    stmt = _sql_in(main._mail_rate_or_raise, "SELECT COUNT(*) FILTER")

    async def body(stmt):
        async with _Schema() as conn:
            await conn.execute(M404)
            now = await conn.fetchval("SELECT NOW()")
            sends = [await _message(conn, at=now - timedelta(seconds=s)) for s in (10, 20, 30)]
            await _message(conn, at=now - timedelta(hours=2))
            await _message(conn, at=now - timedelta(days=2))
            await _message(conn, kind="system_broadcast", count=1, at=now - timedelta(seconds=5))

            async def counts():
                row = await conn.fetchrow(*_flat(_bind(stmt, {"sid": A})))
                return row["per_minute"], row["per_day"], row["minute_wait"] is not None
            before = await counts()
            await conn.execute("DELETE FROM mail_messages WHERE id = ANY($1::uuid[])", sends[:2])
            return before, await counts()
    assert _run(body(stmt)) == ((3, 4, True), (3, 4, True))
    # mutant: the window counted on message rows -> the purged sends leave it
    assert _run(body(stmt.replace("FROM mail_send_receipts", "FROM mail_messages"))) == (
        (3, 4, True), (1, 2, True))


def test_the_discord_read_back_follows_the_repliers_own_view():
    """mail_discord._REPLIED_TO_SQL: the thread a Discord reply names after
    its core returns, a replay included. B replies to A's message, which A
    also sent to C. `other` is the delivery of the one copy B cannot see --
    A's copy of the reply, or C's copy of the original. Fresh, the thread is
    named. Once B deleted the reply, or B's own copy of the original is gone
    (and A deleted it), it is named in neither world: not where the
    janitor's purge removed the row (`other` suppressed), and not where an
    unread delivered copy kept it."""
    stmt = mail_discord._REPLIED_TO_SQL
    rep_side = stmt[stmt.index("   AND rep.sender_id"):stmt.index("   AND (EXISTS")]
    orig_side = stmt[stmt.index("   AND (EXISTS"):]
    purge = _janitor_purge_sql()

    async def body(stmt, other):
        async with _Schema() as conn:
            await conn.execute(M404)
            out = {}
            for case in ("reply deleted", "copy deleted"):
                orig = await _message(conn, sender=A)
                await _envelope(conn, orig, B)
                await _envelope(conn, orig, C, other if case == "copy deleted" else "delivered")
                rep = await _message(conn, sender=B)
                await conn.execute("UPDATE mail_messages SET in_reply_to = $1, thread_id = $1"
                                   " WHERE id = $2", orig, rep)
                await _envelope(conn, rep, A, other if case == "reply deleted" else "delivered")

                async def named():
                    return await conn.fetchrow(*_flat(_bind(stmt, {
                        "rid": rep, "sid": "2", "pid": B, "ret_days": DAYS}))) is not None
                fresh = await named()
                if case == "reply deleted":
                    await conn.execute("UPDATE mail_messages SET deleted_by_sender_at = NOW()"
                                       " WHERE id = $1", rep)
                else:
                    await conn.execute("UPDATE mail_recipients SET deleted_at = NOW()"
                                       " WHERE message_id = $1 AND recipient_id = $2", orig, B)
                    await conn.execute("UPDATE mail_messages SET deleted_by_sender_at = NOW()"
                                       " WHERE id = $1", orig)
                await conn.execute(*_flat(_bind(purge, {"days": DAYS})))
                out[case] = (fresh, await named())
            return out
    for other in ("delivered", "suppressed"):
        assert _run(body(stmt, other)) == {"reply deleted": (True, False),
                                           "copy deleted": (True, False)}, other
    # mutant: the reply read without the replier's view -> a deleted reply is
    # named while A's delivered copy keeps its row, and not once it is purged
    assert [_run(body(stmt.replace(rep_side, ""), o))["reply deleted"]
            for o in ("delivered", "suppressed")] == [(True, True), (True, False)]
    # mutant: the original read without it -> the same split on C's copy
    assert [_run(body(stmt.replace(orig_side, ""), o))["copy deleted"]
            for o in ("delivered", "suppressed")] == [(True, True), (True, False)]


# ── the rollback ──────────────────────────────────────────────────────────

def test_the_rollback_restores_297_runs_twice_and_refuses_repeated_keys():
    async def body(rollback):
        async with _Schema() as conn:
            await conn.execute(M404)
            await conn.execute(rollback)
            first = await _shape(conn)
            try:
                await conn.execute(rollback)
                second = await _shape(conn)
            except asyncpg.PostgresError as e:
                await conn.execute("ROLLBACK")
                return first, e.sqlstate, None, None, None
            await conn.execute(M404)
            again = await _shape(conn)
            # a key sent again after its receipt was swept while the row is kept
            key = str(uuid.uuid4())
            await _message(conn, key=key)
            await conn.execute("DELETE FROM mail_send_receipts")
            await _message(conn, key=key)
            try:
                await conn.execute(rollback)
                refused = None
            except asyncpg.PostgresError as e:
                refused = e.sqlstate
                await conn.execute("ROLLBACK")
            return first, second, again, refused, await _shape(conn)
    first, second, again, refused, after = _run(body(R404))
    assert first == second == ROLLED_BACK and again == APPLIED
    assert refused == "23505" and after == APPLIED           # the refusal rolled the whole file back
    # mutant: the constraint added without its guard -> the second run fails
    bare = "ALTER TABLE mail_messages ADD CONSTRAINT uq_mail_messages_sender_idem UNIQUE (sender_id, idempotency_key);"
    unguarded, n = re.subn(r"DO \$r404uq\$.*?END \$r404uq\$;", bare, R404, flags=re.S)
    assert n == 1
    first, failed, *_rest = _run(body(unguarded))
    assert first == ROLLED_BACK and failed in ("42P07", "42710")
