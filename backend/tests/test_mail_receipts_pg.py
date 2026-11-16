"""Migration 415 and the mail statements it serves, executed on a real
PostgreSQL: the migration and rollback files as they are, and every
statement as main.py holds it, never retyped (the sender's reads, the
reply core and the send's tail run as the routes themselves, through
_Session, an AsyncSession stand-in over the test's connection).

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
import hashlib
import inspect
import os
import re
import textwrap
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

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

M415 = (SQL_DIR / "415_mail_send_receipts.sql").read_text(encoding="utf-8")
R415 = (SQL_DIR / "rollback_415_mail_send_receipts.sql").read_text(encoding="utf-8")
SENDER_CLOCK = "AND m.created_at > t.now_ - make_interval(days => CAST(:ret_days AS integer))"
DAYS = main.MAIL_RETENTION_DAYS
# The random draw of a reserved key's 32 hex digits (the trigger, the
# backfill and the sweep each set the 13th to 0 afterwards).
_RANDOM_HEX = "replace(CAST(gen_random_uuid() AS text), '-', '')"
NOT_FOUND = (404, "not_found")

A, B, C, D = ("00000000-0000-0000-0000-00000000a415", "00000000-0000-0000-0000-00000000b415",
              "00000000-0000-0000-0000-00000000c415", "00000000-0000-0000-0000-00000000d415")
_BIND = re.compile(r"(?<!:):([A-Za-z_]\w*)\b")


@pytest.fixture(autouse=True)
def _require_live_pg():
    """Fail, not skip, when the cluster is missing and nobody waived it."""
    if DSN and asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: migration 415's PostgreSQL coverage deliberately "
                    "waived for this run." % (DSN_VAR, OPTOUT_VAR))
    if asyncpg is None:
        pytest.fail("asyncpg is not installed, so migration 415's PostgreSQL coverage did not "
                    "run. Install it, or set %s=1 to waive it deliberately." % OPTOUT_VAR)
    pytest.fail("%s is unset, so migration 415 and its statements were not run on PostgreSQL. "
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


def _without(text, start, lines=1):
    """A mutant: `text` with `lines` lines taken out, from its one line
    that begins with `start`."""
    rows = text.split("\n")
    at = [i for i, r in enumerate(rows) if r.startswith(start)]
    assert len(at) == 1, ("mutant anchor occurs %d times" % len(at), start)
    return "\n".join(rows[:at[0]] + rows[at[0] + lines:])


def _reserved(seed):
    """The reserved key the build before migration 415's change derived from
    `seed`: its md5 with the version digit (the 13th hex digit) set to 0.
    The tests store one in advance to show that no draw depends on it."""
    h = hashlib.md5(seed.encode("ascii")).hexdigest()
    return str(uuid.UUID(h[:12] + "0" + h[13:]))


def _is_reserved(key):
    """Whether `key` is in the reserved space: its version digit is 0."""
    return uuid.UUID(str(key)).hex[12] == "0"


def _refused(key):
    """Whether every route's key parse refuses `key` (main._mail_parse_key)."""
    try:
        main._mail_parse_key(key)
    except HTTPException as e:
        return (e.status_code, e.detail) == (400, "idempotency_key_invalid")
    return False


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
        # mscl-r2: the purge (main._mail_purge_due) also reads the case and invite
        # rows that name a message; the one column it reads of each, no rows
        "CREATE TABLE moderation_cases (id BIGSERIAL PRIMARY KEY, message_id UUID);",
        "CREATE TABLE lobby_invites (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), mail_message_id UUID);",
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
        self.name = "t415_%s" % uuid.uuid4().hex[:10]
        self.others = []
        self.conn = await asyncpg.connect(DSN)
        try:
            await self.conn.execute('CREATE SCHEMA "%s"' % self.name)
            await self.conn.execute('SET search_path TO "%s"' % self.name)
            await self.conn.execute(_base_sql())
        except BaseException:
            await self.__aexit__()
            raise
        return self.conn

    async def other(self):
        """A second connection on this schema (each statement its own
        transaction), closed with the schema."""
        other = await asyncpg.connect(DSN)
        self.others.append(other)
        await other.execute('SET search_path TO "%s"' % self.name)
        return other

    async def __aexit__(self, *exc):
        try:
            for other in self.others:
                await other.close()
            if self.conn.is_in_transaction():
                await self.conn.execute("ROLLBACK")
            await self.conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % self.name)
        finally:
            await self.conn.close()
        return False


async def _message(conn, sender=A, kind="direct", key=None, count=None, at=None, thread=None,
                   parent=None, subject="s", body="b", mid=None):
    """A message row as a writer of mail_messages inserts it: a new thread
    (thread_id = id) unless `thread` names one, in reply to `parent`."""
    mid = mid or str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO mail_messages (id, sender_id, kind, thread_id, in_reply_to, subject, body,"
        " idempotency_key, created_at, recipient_count)"
        " VALUES (CAST($1 AS uuid), $2, $3, COALESCE(CAST($7 AS uuid), CAST($1 AS uuid)),"
        "         CAST($8 AS uuid), $9, $10, $4, COALESCE($5, NOW()), $6)",
        mid, sender, kind, key or str(uuid.uuid4()), at, count, thread, parent, subject, body)
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
    """Which of 415's objects exist, whether a foreign key covers
    mail_messages.in_reply_to (297's, which 415 drops), and whether 297's
    unique key exists (415 keeps it)."""
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
                         JOIN pg_attribute a ON a.attrelid = c.oid
                        WHERE n.nspname = current_schema() AND c.relname = 'mail_messages'
                          AND k.contype = 'f' AND a.attname = 'in_reply_to'
                          AND a.attnum = ANY (k.conkey)) AS fk,
               EXISTS (SELECT 1 FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
                         JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = current_schema()
                          AND k.conname = 'uq_mail_messages_sender_idem'
                          AND pg_get_constraintdef(k.oid) = 'UNIQUE (sender_id, idempotency_key)') AS uq""")
    return {"table": row["tbl"], "function": row["fn"], "trigger": row["trg"], "fk": row["fk"],
            "uq": row["uq"]}


APPLIED = {"table": True, "function": True, "trigger": True, "fk": False, "uq": True}
ROLLED_BACK = {"table": False, "function": False, "trigger": False, "fk": True, "uq": True}
BEFORE = ROLLED_BACK                     # 297's schema: what a refused first run leaves

# 415's objects as the file makes them, made before the file runs (as the
# api build's own table creation, or an earlier partial run, would make
# them); the function made before it does nothing, and the file replaces it.
_TABLE_AS_FILE = (
    "CREATE TABLE mail_send_receipts (sender_id UUID NOT NULL, idempotency_key UUID NOT NULL,"
    " kind TEXT NOT NULL, request_fp BYTEA, message_fp BYTEA NOT NULL, message_id UUID NOT NULL,"
    " recipients INTEGER, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), body_key BYTEA,"
    " PRIMARY KEY (sender_id, idempotency_key),"
    " CONSTRAINT ck_mail_send_receipts_kind CHECK (kind IN ('direct', 'system_broadcast')),"
    " CONSTRAINT ck_mail_send_receipts_fp CHECK (request_fp IS NULL OR octet_length(request_fp) = 32),"
    " CONSTRAINT ck_mail_send_receipts_message_fp CHECK (octet_length(message_fp) = 32),"
    " CONSTRAINT ck_mail_send_receipts_recipients CHECK (recipients IS NULL OR recipients >= 0),"
    " CONSTRAINT ck_mail_send_receipts_body_key CHECK (body_key IS NULL OR octet_length(body_key) = 32));")
_FN_NOOP = ("CREATE FUNCTION mail_send_receipt_sync() RETURNS trigger LANGUAGE plpgsql"
            " AS $f$BEGIN RETURN NULL; END$f$; ")
_TRG_AS_FILE = ("CREATE TRIGGER trg_mail_send_receipt AFTER INSERT OR UPDATE OF recipient_count"
                " ON mail_messages FOR EACH ROW WHEN (NEW.kind IN ('direct', 'system_broadcast'))"
                " EXECUTE FUNCTION mail_send_receipt_sync();")


# ── the routes on PostgreSQL ──────────────────────────────────────────────
#
# A route runs against the throwaway schema through _Session: every
# statement it issues is the text main.py passes to text(), its ':name'
# binds rebound by _bind, on the test's own connection. _route_stubs
# replaces only what reads no mail table -- the caller's identity, the
# identity and sender locks, the sender gates, the title colours, the
# censor -- and the recipient cap, whose stub ends a reply where its send
# would begin (after _mail_finish_send's empty-list refusal).

def _plain(value):
    """asyncpg's uuid as the uuid.UUID the api's driver hands it."""
    if isinstance(value, uuid.UUID) or type(value).__name__ == "UUID":
        return uuid.UUID(str(value))
    return value


class _Result:
    """The parts of a SQLAlchemy result the routes read."""

    def __init__(self, rows, rowcount):
        self._rows = [{k: _plain(v) for k, v in dict(r).items()} for r in rows]
        self.rowcount = rowcount

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    fetchall = all

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return next(iter(self._rows[0].values())) if self._rows else None


class _Session:
    """An AsyncSession stand-in over `conn`. `rewrite(sql)` may replace a
    statement's text before it runs (a mutant); `after(sql)` runs each time
    a statement has returned. `split` = (needle, prefix): a statement that
    holds `needle` runs as the two statements the routes issued before
    migration 415's change -- the message read, then `after`, then the read
    of the joined columns named `prefix`* (the addressees, or the reply
    all's envelopes) -- and the rows are put together as one statement
    returns them."""

    def __init__(self, conn, rewrite=None, after=None, split=None):
        self.conn, self.rewrite, self.after, self.split = conn, rewrite, after, split
        self.statements = []

    async def execute(self, clause, params=None):
        sql = getattr(clause, "text", None) or str(clause)
        if self.rewrite is not None:
            sql = self.rewrite(sql)
        self.statements.append(sql)
        q, args = _bind(sql, dict(params or {}))
        if self.split is not None and self.split[0] in sql:
            return _Result(await self._split(sql, q, args, self.split[1]), None)
        if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", q) and "RETURNING" not in q:
            status = await self.conn.execute(q, *args)
            result = _Result([], int(status.split()[-1]))
        else:
            result = _Result(await self.conn.fetch(q, *args), None)
        if self.after is not None:
            await self.after(sql)
        return result

    async def _split(self, sql, q, args, prefix):
        first = _Result(await self.conn.fetch(q, *args), None).all()
        if self.after is not None:
            await self.after(sql)
        second = _Result(await self.conn.fetch(q, *args), None).all()
        out, seen = [], set()
        for row in first:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            joined = [{k: v for k, v in r.items() if k.startswith(prefix)} for r in second
                      if r["id"] == row["id"]
                      and any(v is not None for k, v in r.items() if k.startswith(prefix))]
            out.extend(dict(row, **j) for j in (joined or [{k: None for k in row if k.startswith(prefix)}]))
        return out

    async def commit(self):
        if self.conn.is_in_transaction():
            await self.conn.execute("COMMIT")

    async def rollback(self):
        if self.conn.is_in_transaction():
            await self.conn.execute("ROLLBACK")


def _once(action):
    """An `after` hook that runs `action` once, right after the first
    statement that reads mail_messages; `fired` holds that statement."""
    fired = []

    async def after(sql):
        if not fired and "mail_messages" in sql:
            fired.append(sql)
            await action()
    return after, fired


def _rewriting(old, new):
    """A `rewrite` replacing `old` by `new` in each statement that holds it;
    `hits` holds the statements it changed, so a mutant that reached no
    statement is seen."""
    hits = []

    def rewrite(sql):
        if old not in sql:
            return sql
        hits.append(sql)
        return sql.replace(old, new)
    return rewrite, hits


_STEAM = {A: "1", B: "2", C: "3", D: "4"}
_NAME = {A: "A", B: "B", C: "C", D: "D"}


def _me(pid):
    """The caller as _mail_caller returns it."""
    return {"id": uuid.UUID(pid), "steam_id": _STEAM[pid], "display_name": _NAME[pid],
            "mod_seen_at": datetime(2026, 11, 1, tzinfo=timezone.utc), "mail_from": "everyone",
            "mail_discord_relay": False, "discord_id": None}


class _Reached(Exception):
    """A reply passed the reply core's read and _mail_finish_send's
    empty-list refusal; args[0] is the addressee list the core derived."""


def _route_stubs(monkeypatch):
    async def nothing(*_a, **_k):
        return None

    async def caller(request, _db):
        return request                       # the routes are called with _me(...) as the request

    async def colors(_db, _rows):
        return {}

    async def cap(_db, _sender):
        raise _Reached()
    for name, fn in (("_mail_caller", caller), ("_mail_lock_identities", nothing),
                     ("_mail_lock_sender", nothing), ("_mail_sender_gates", nothing),
                     ("_mail_sender_colors", colors), ("_mail_censor_or_raise", nothing),
                     ("_mail_recipient_cap", cap)):
        assert callable(getattr(main, name, None)), name
        monkeypatch.setattr(main, name, fn)
    real = main._mail_finish_send

    async def finish(db, sender, **kw):
        try:
            return await real(db, sender, **kw)
        except _Reached:
            raise _Reached(kw["addressees"]) from None
    monkeypatch.setattr(main, "_mail_finish_send", finish)


async def _answer(coro):
    """A route's answer: its body; (status, detail) when it refuses; or
    ('reached the send', addressees) for a reply that got past its read."""
    try:
        return await coro
    except HTTPException as e:
        return (e.status_code, e.detail)
    except _Reached as e:
        return ("reached the send", e.args[0] if e.args else None)


def _reply(sess, mid, me=A, reply_all=True):
    return _answer(main._mail_reply_core(sess, _me(me), message_id=str(mid), body="A short reply.",
                                         reply_all=reply_all, idempotency_key=str(uuid.uuid4())))


def _sent(sess, me=A):
    return _answer(main.mail_sent(_me(me), "", 25, sess))


def _detail(sess, mid, me=A):
    return _answer(main.mail_detail(str(mid), _me(me), sess))


# ── the migration ─────────────────────────────────────────────────────────

def test_the_backfill_gives_every_message_its_receipt_and_refuses_an_uncounted_broadcast():
    """A direct message and a broadcast with its count get receipts that
    replay what the previous build's replay answered. A broadcast written
    before 300 (no count; two delivered envelopes and one suppressed) aborts
    the file with nothing changed: the previous build answers its key with a
    count of its envelopes taken at that moment, which no stored count stays
    equal to."""
    async def body(migration, uncounted):
        async with _Schema() as conn:
            t0 = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
            direct = await _message(conn, at=t0)
            counted = await _message(conn, kind="system_broadcast", count=3, at=t0 + timedelta(days=1))
            late = None
            if uncounted:
                late = await _message(conn, kind="system_broadcast", at=t0 + timedelta(days=2))
                for rid, delivery in ((B, "delivered"), (C, "delivered"), (D, "suppressed")):
                    await _envelope(conn, late, rid, delivery)
            try:
                await conn.execute(migration)
                refused = None
            except asyncpg.PostgresError as e:
                refused = str(e)
                await conn.execute("ROLLBACK")
            shape = await _shape(conn)
            got = await _receipts(conn) if shape["table"] else None
            return refused, got, (direct, counted, late), shape
    refused, got, (direct, counted, _late), shape = _run(body(M415, False))
    assert refused is None and shape == APPLIED
    assert got == {direct: ("direct", None, None, True), counted: ("system_broadcast", 3, None, True)}
    refused, got, _made, shape = _run(body(M415, True))
    assert refused and "415: 1 broadcast row(s) have no recipient_count" in refused
    assert got is None and shape == BEFORE                      # the whole file rolled back
    # mutant: the refusal taken out -> the file commits and the broadcast's
    # receipt holds no count, so its replay answers 0 where the previous
    # build answered 2
    refused, got, (_d, _c, late), shape = _run(body(_mutated(M415, "IF uncounted <> 0 THEN", "IF false THEN"),
                                                  True))
    assert refused is None and shape == APPLIED and got[late][1] is None


def test_the_trigger_and_the_backfill_write_the_digest_the_api_computes():
    """message_fp, written by the backfill (rows present before the file)
    and by the trigger (rows written after), equals main._mail_message_fp of
    the stored text for a send, a reply and a broadcast, with text outside
    ASCII. A reply's subject is not in it, and a reply is told by its
    thread_id: the one here has no in_reply_to, as a reply whose parent was
    purged under 297's ON DELETE SET NULL has none."""
    async def make(conn):
        root = await _message(conn, subject="Root", body="r")
        made = {root: ("send", "Root", "r")}
        for route, kw in (("send", dict(subject="Plan ü", body="Café \U0001F600")),
                          ("reply", dict(thread=root, subject="Re: Root", body="Sí.")),
                          ("broadcast", dict(kind="system_broadcast", count=2, subject="Notice",
                                             body="Restart ✓"))):
            made[await _message(conn, **kw)] = (route, kw["subject"], kw["body"])
        return made

    async def body(migration):
        async with _Schema() as conn:
            before = await make(conn)
            await conn.execute(migration)
            after = await make(conn)
            fps = {r["mid"]: bytes(r["message_fp"]) for r in await conn.fetch(
                "SELECT message_id::text AS mid, message_fp FROM mail_send_receipts")}
            return before, after, fps

    def wrong(made, fps):
        return sorted(route for mid, (route, subject, text_) in made.items()
                      if fps[mid] != main._mail_message_fp(route, subject, text_))
    before, after, fps = _run(body(M415))
    assert len(fps) == 8 and wrong(before, fps) == [] and wrong(after, fps) == []
    # mutant, backfill: the route read off in_reply_to -> the reply with
    # none digests as a send
    before, after, fps = _run(body(_mutated(M415, "WHEN m.thread_id = m.id THEN 'send'",
                                            "WHEN m.in_reply_to IS NULL THEN 'send'")))
    assert wrong(before, fps) == ["reply"] and wrong(after, fps) == []
    # mutant, trigger: a reply's subject digested -> the trigger's reply row
    # differs from the api's digest
    before, after, fps = _run(body(_mutated(M415, "THEN '' ELSE NEW.subject END",
                                            "THEN NEW.subject ELSE NEW.subject END")))
    assert wrong(before, fps) == [] and wrong(after, fps) == ["reply"]


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
    inserted, final, direct, bcast = _run(body(M415))
    assert inserted == {direct: ("direct", None, None, True), bcast: ("system_broadcast", None, None, True)}
    assert final == {direct: ("direct", None, None, True), bcast: ("system_broadcast", 5, None, True)}
    # mutant: the UPDATE arm without `recipients IS NULL` -> a later count
    # overwrites the one the send answered with
    _inserted, final, _direct, bcast = _run(body(_mutated(M415, "\n       AND recipients IS NULL;", ";")))
    assert final[bcast][1] == 7


def test_the_post_check_accepts_matching_objects_and_refuses_differing_ones():
    """A same-named table made before the file (as the api build's own table
    creation would make it, deployed out of order) is accepted when it
    matches the file's definition; one that differs -- a column's type, or a
    check's expression under its own name, a typed table -- aborts the whole
    file. So does a same-named trigger that differs in any column of its
    pg_trigger row the file states, while one made as the file makes it is
    accepted."""
    same = _TABLE_AS_FILE
    table_only = {"table": True, "function": False, "trigger": False, "fk": True, "uq": True}

    async def body(pre, migration=M415):
        async with _Schema() as conn:
            await conn.execute(pre)
            try:
                await conn.execute(migration)
                refused = None
            except asyncpg.PostgresError as e:
                refused = str(e)
                await conn.execute("ROLLBACK")
            return refused, await _shape(conn)
    assert _run(body(same)) == (None, APPLIED)
    # Each property the file states, changed alone on a table made before the
    # file: the whole file aborts (only the table made before it is left),
    # with the refusal naming what it found.
    trig = ("CREATE FUNCTION t415_noop() RETURNS trigger LANGUAGE plpgsql AS $f$BEGIN RETURN NEW; END$f$;"
            " CREATE TRIGGER t415_extra BEFORE INSERT ON mail_send_receipts FOR EACH ROW"
            " EXECUTE FUNCTION t415_noop();")
    # the same columns, NOT NULLs, default, key and checks, on a table of a
    # composite type
    typed = ("CREATE TYPE t415_receipt AS (sender_id UUID, idempotency_key UUID, kind TEXT,"
             " request_fp BYTEA, message_fp BYTEA, message_id UUID, recipients INTEGER,"
             " created_at TIMESTAMPTZ, body_key BYTEA);"
             " CREATE TABLE mail_send_receipts OF t415_receipt (sender_id WITH OPTIONS NOT NULL,"
             " idempotency_key WITH OPTIONS NOT NULL, kind WITH OPTIONS NOT NULL,"
             " message_fp WITH OPTIONS NOT NULL, message_id WITH OPTIONS NOT NULL,"
             " created_at WITH OPTIONS NOT NULL DEFAULT NOW(), PRIMARY KEY (sender_id, idempotency_key),"
             + same[same.index(" CONSTRAINT ck_mail_send_receipts_kind"):])
    cases = {
        "type": (_mutated(same, "created_at TIMESTAMPTZ", "created_at TIMESTAMP"),
                 "415: mail_send_receipts columns differ", "created_at timestamp without time zone"),
        # (the constant prints in the session's time zone, so only its start)
        "default": (_mutated(same, "DEFAULT NOW()", "DEFAULT TIMESTAMPTZ '2000-01-01 00:00+00'"),
                    "415: mail_send_receipts columns differ",
                    "created_at timestamp with time zone NOT NULL DEFAULT '"),
        "modifier": (_mutated(same, "created_at TIMESTAMPTZ", "created_at TIMESTAMPTZ(0)"),
                     "415: mail_send_receipts columns differ", "timestamp(0) with time zone"),
        "collation": (_mutated(same, "kind TEXT NOT NULL", 'kind TEXT COLLATE "C" NOT NULL'),
                      "415: mail_send_receipts columns differ", "COLLATE C"),
        "check": (_mutated(same, "recipients IS NULL OR recipients >= 0", "recipients IS NULL OR recipients >= 1"),
                  "415: mail_send_receipts key or checks differ", "recipients >= 1"),
        "index": (same + " CREATE UNIQUE INDEX t415_extra ON mail_send_receipts (message_id);",
                  "415: mail_send_receipts indexes differ", "t415_extra"),
        "unlogged": (_mutated(same, "CREATE TABLE", "CREATE UNLOGGED TABLE"),
                     "415: mail_send_receipts is not the plain table", ""),
        "row security": (same + " ALTER TABLE mail_send_receipts ENABLE ROW LEVEL SECURITY;",
                         "415: mail_send_receipts is not the plain table", ""),
        "trigger": (same + " " + trig, "415: mail_send_receipts is not the plain table", ""),
        "typed": (typed, "415: mail_send_receipts is not the plain table", ""),
    }
    for name, (pre, message, found) in cases.items():
        refused, shape = _run(body(pre))
        assert refused and message in refused and found in refused, (name, refused)
        assert shape == table_only, name
    # mutants: each comparison taken out of the post-check -> its case is
    # accepted and the file commits over the differing table
    for name, old, new in (
            ("default", "     AND pg_get_expr(d.adbin, d.adrelid) IS NOT DISTINCT FROM w.def;", ";"),
            ("modifier", "     AND a.atttypmod = -1\n", ""),
            ("index", "IF n <> 1 OR pk <> 1 OR valid <> 2 OR total <> 2 THEN",
             "IF n <> 1 OR pk <> 1 THEN"),
            ("unlogged", "     AND c.relpersistence = 'p'\n", ""),
            ("typed", "     AND c.reloftype = 0\n", "")):
        refused, shape = _run(body(cases[name][0], _mutated(M415, old, new)))
        assert refused is None and shape == APPLIED, (name, refused)

    # The trigger: made as the file makes it, it is accepted; each column of
    # its pg_trigger row the post-check compares, changed alone on a trigger
    # made before the file, aborts the file, the refusal printing what it
    # found. A clone of a partitioned parent's trigger differs in tgparentid
    # alone.
    assert _run(body(_FN_NOOP + _TRG_AS_FILE)) == (None, APPLIED)
    clone = ("CREATE TABLE t415_parent (LIKE mail_messages) PARTITION BY LIST (kind); "
             + _mutated(_TRG_AS_FILE, " ON mail_messages ", " ON t415_parent ")
             + " ALTER TABLE t415_parent ATTACH PARTITION mail_messages"
               " FOR VALUES IN ('direct', 'system_broadcast');")
    triggers = {
        # name: (made before the file, what the refusal prints of it, and
        # the post-check's comparison a mutant takes out: first line, lines)
        "when": (_mutated(_TRG_AS_FILE, "NEW.kind IN ('direct', 'system_broadcast')", "NEW.kind = 'direct'"),
                 "new.kind = 'direct'", ("     AND substring(pg_get_triggerdef(tg.oid)", 2)),
        "timing": (_mutated(_TRG_AS_FILE, " AFTER INSERT", " BEFORE INSERT"), " BEFORE INSERT",
                   ("     AND tg.tgtype = 21 ", 1)),
        "columns": (_mutated(_TRG_AS_FILE, "UPDATE OF recipient_count", "UPDATE OF recipient_count, subject"),
                    "UPDATE OF recipient_count, subject", ("     AND CAST(tg.tgattr AS text)", 4)),
        "enabled": (_TRG_AS_FILE + " ALTER TABLE mail_messages DISABLE TRIGGER trg_mail_send_receipt;",
                    "enabled D", ("     AND tg.tgenabled = 'O'", 1)),
        "argument": (_mutated(_TRG_AS_FILE, "mail_send_receipt_sync();", "mail_send_receipt_sync('x');"),
                     "mail_send_receipt_sync('x')", ("     AND tg.tgnargs = 0", 1)),
        "constraint": (_mutated(_TRG_AS_FILE, "CREATE TRIGGER", "CREATE CONSTRAINT TRIGGER"),
                       "CREATE CONSTRAINT TRIGGER", ("     AND tg.tgconstraint = 0", 1)),
        "clone": (clone, ", parent ", ("     AND tg.tgparentid = 0 ", 1)),
    }
    found = {}
    for name, (pre, printed, _line) in triggers.items():
        refused, shape = _run(body(_FN_NOOP + pre))
        assert refused and "415: trg_mail_send_receipt or its function differs" in refused, (name, refused)
        assert printed in refused, (name, refused)
        assert shape == {"table": False, "function": True, "trigger": True, "fk": True, "uq": True}, name
        found[name] = refused
    assert re.search(r", parent [1-9]", found["clone"]) and ", parent 0," in found["when"]
    # mutants: each comparison taken out of the post-check -> its case is
    # accepted and the file commits over the differing trigger
    for name, (pre, _printed, (start, lines)) in triggers.items():
        refused, shape = _run(body(_FN_NOOP + pre, _without(M415, start, lines)))
        assert refused is None and shape == APPLIED, (name, refused)
    # The foreign key's drop is part of the check: a file that kept 297's
    # foreign key on in_reply_to is refused by its own post-check.
    refused, shape = _run(body("SELECT 1;", _mutated(
        M415, "    EXECUTE format('ALTER TABLE mail_messages DROP CONSTRAINT %I', k.conname);\n",
        "    NULL;\n")))
    assert refused and "415: a foreign key still covers mail_messages.in_reply_to" in refused
    assert shape == BEFORE


def test_the_backfill_runs_when_this_run_creates_the_table_or_the_trigger():
    """A message written before the file gets its receipt when the run
    creates the table under a trigger made before it, and when it creates
    the trigger over a table made before it: either run is the first in
    which the message could be without one."""
    cue = "    PERFORM set_config('m415.backfill', 'on', true);\n"

    async def body(pre, migration=M415):
        async with _Schema() as conn:
            mid = await _message(conn)
            await conn.execute(pre)
            await conn.execute(migration)
            return mid, set(await _receipts(conn))
    for name, pre, creates in (
            ("trigger made before", _FN_NOOP + _TRG_AS_FILE, "    );\n"),
            ("table made before", _TABLE_AS_FILE, "      EXECUTE FUNCTION mail_send_receipt_sync();\n")):
        mid, got = _run(body(pre))
        assert got == {mid}, name
        # mutant: the creation this run makes does not cue the backfill ->
        # the file commits and the message has no receipt
        _mid, got = _run(body(pre, _mutated(M415, creates + cue, creates)))
        assert got == set(), name


_BACKFILL_SUPERSEDE = re.compile(r"    UPDATE mail_send_receipts s\n.*?AND s\.message_id <> m\.id;\n", re.S)
_NAMING = re.compile(r"\n +AND s\.message_id = m\.id\);")


def _backfill_supersession():
    """The backfill's supersession UPDATE, as the file states it."""
    found = _BACKFILL_SUPERSEDE.findall(M415)
    assert len(found) == 1
    return found[0]


def test_the_backfill_gives_a_key_to_the_message_that_holds_it():
    """A partial rollback left 415's table and its rows but not the trigger.
    A's message M1 under key K has its receipt, completed by the api with its
    request digest, recipient count and body key; M1 is then deleted, and the
    previous build sends K again as M2 with the same text (no trigger, so no
    receipt). The re-run creates the trigger and backfills: K's receipt names
    M2 with M2's created_at, M1's receipt stays under a reserved key with
    its kind, time, digests, count and body key, and a replay of K
    (main._mail_prior_send) answers M2."""
    fp = bytes(range(32))
    send_fp = main._mail_message_fp("send", "s", "b")
    record = ("SELECT kind, created_at, request_fp, message_fp, recipients, body_key, message_id::text AS mid"
              " FROM mail_send_receipts WHERE message_id = $1")

    async def body(migration):
        async with _Schema() as conn:
            await conn.execute(M415)
            key = str(uuid.uuid4())
            now = await conn.fetchval("SELECT NOW()")
            first = await _message(conn, key=key, at=now - timedelta(hours=3))
            await conn.execute(*_flat(_bind(main._MAIL_RECEIPT_SQL, {
                "sid": A, "key": key, "kind": "direct", "fp": fp, "mfp": send_fp, "mid": first,
                "n": 1, "bk": main._mail_body_key("b")})))
            before = dict(await conn.fetchrow(record, first))
            await conn.execute("DROP TRIGGER trg_mail_send_receipt ON mail_messages")
            await conn.execute("DELETE FROM mail_messages WHERE id = $1", first)
            second = await _message(conn, key=key, at=now - timedelta(hours=1))
            try:
                await conn.execute(migration)
                refused = None
            except asyncpg.PostgresError as e:
                refused = str(e)
                await conn.execute("ROLLBACK")
            keys = {r["mid"]: r["k"] for r in await conn.fetch(
                "SELECT message_id::text AS mid, idempotency_key::text AS k FROM mail_send_receipts")}
            after = await conn.fetchrow(record, first)
            own = await conn.fetchval(
                "SELECT s.created_at = m.created_at FROM mail_send_receipts s"
                "  JOIN mail_messages m ON m.id = s.message_id WHERE s.message_id = $1", second)
            replay = None
            if refused is None:
                replay = await _answer(main._mail_prior_send(_Session(conn), uuid.UUID(A), uuid.UUID(key),
                                                             bytes(32), send_fp))
            return (refused, (await _shape(conn))["trigger"], keys,
                    (before, None if after is None else dict(after)), own, replay, (first, second, key))
    refused, trigger, keys, (before, after), own, replay, (first, second, key) = _run(body(M415))
    assert refused is None and trigger and set(keys) == {first, second}
    assert keys[second] == key and own
    assert keys[first] != key and _is_reserved(keys[first]) and _refused(keys[first])
    assert after == before and before["request_fp"] == fp and before["recipients"] == 1
    assert replay == {"id": second, "accepted": True}
    # mutant: the backfill without its supersession UPDATE -> the INSERT
    # skips K, and the check aborts the file naming the message
    no_update = _mutated(M415, _backfill_supersession(), "")
    refused, trigger, keys, _records, _own, _replay, (first, second, key) = _run(body(no_update))
    assert refused and "415: 1 message row(s) have no send receipt naming them after the backfill" in refused
    assert not trigger and keys == {first: key}
    # mutant: also the check of key presence alone -> the file commits and
    # K's receipt still names the deleted M1
    naming = _NAMING.findall(M415)
    assert len(naming) == 1
    refused, trigger, keys, _records, _own, _replay, (first, second, key) = _run(
        body(_mutated(no_update, naming[0], ");")))
    assert refused is None and trigger and keys == {first: key}


def test_the_backfill_draws_a_superseded_key_at_random():
    """As above, with M2's id chosen in advance and another message of A's
    already holding the key the previous derivation would give M1's receipt,
    md5('mail-receipt-superseded:' || M1 || ':' || M2) with the version digit
    0: the backfill supersedes M1's receipt under a key it draws, and K's
    receipt names M2."""
    derived = "md5('mail-receipt-superseded:' || CAST(s.message_id AS text) || ':' || CAST(m.id AS text))"
    block = _backfill_supersession()

    async def body(migration):
        async with _Schema() as conn:
            await conn.execute(M415)
            key, new_id = str(uuid.uuid4()), str(uuid.uuid4())
            first = await _message(conn, key=key)
            held = _reserved("mail-receipt-superseded:%s:%s" % (first, new_id))
            await _message(conn, key=held)                       # with its receipt, by the trigger
            await conn.execute("DROP TRIGGER trg_mail_send_receipt ON mail_messages")
            await conn.execute("DELETE FROM mail_messages WHERE id = $1", first)
            await _message(conn, key=key, mid=new_id)
            try:
                await conn.execute(migration)
            except asyncpg.PostgresError as e:
                await conn.execute("ROLLBACK")
                return e.sqlstate, (await _shape(conn))["trigger"]
            moved = await conn.fetchval("SELECT idempotency_key::text FROM mail_send_receipts"
                                        " WHERE message_id = $1", first)
            return ((await _receipt(conn, A, key))[0] == new_id,
                    moved not in (key, held) and _is_reserved(moved)), (await _shape(conn))["trigger"]
    assert _run(body(M415)) == ((True, True), True)
    # mutant: the backfill's key derived from the two message ids -> it meets
    # the stored key and the file aborts
    assert _run(body(_mutated(M415, block, _mutated(block, _RANDOM_HEX, derived)))) == ("23505", False)


# ── the api's statements ──────────────────────────────────────────────────

def test_the_api_upsert_completes_its_own_row_and_refuses_another_message():
    fp1, fp2 = bytes(range(32)), bytes(range(1, 33))
    send_fp, bcast_fp = main._mail_message_fp("send", "s", "b"), main._mail_message_fp("broadcast", "s", "b")
    bk1, bk2 = main._mail_body_key("b"), main._mail_body_key("another body")

    async def body(sql):
        async with _Schema() as conn:
            await conn.execute(M415)
            key = str(uuid.uuid4())
            mid = await _message(conn, key=key)                      # the trigger's row: no digest

            def stmt(**p):
                route = "broadcast" if p["kind"] == "system_broadcast" else "send"
                return _bind(sql, dict(p, mfp=main._mail_message_fp(route, "s", "b")))

            async def stored_fp(k):
                r = await conn.fetchrow("SELECT message_fp, body_key FROM mail_send_receipts"
                                        " WHERE sender_id = $1 AND idempotency_key = $2", A, k)
                return bytes(r["message_fp"]), None if r["body_key"] is None else bytes(r["body_key"])
            own = await conn.fetchval(*_flat(stmt(sid=A, key=key, kind="direct", fp=fp1, mid=mid, n=1, bk=bk1)))
            after_own = await _receipt(conn, A, key)
            other = await conn.fetchval(*_flat(stmt(sid=A, key=key, kind="direct", fp=fp2,
                                                    mid=str(uuid.uuid4()), n=2, bk=bk2)))
            after_other = await _receipt(conn, A, key)
            own_fp = await stored_fp(key)
            # without the trigger, the upsert alone writes the whole row
            await conn.execute("DROP TRIGGER trg_mail_send_receipt ON mail_messages")
            key2 = str(uuid.uuid4())
            mid2 = await _message(conn, kind="system_broadcast", key=key2, count=4)
            alone = await conn.fetchval(*_flat(stmt(sid=A, key=key2, kind="system_broadcast", fp=fp1,
                                                    mid=mid2, n=4, bk=None)))
            return (own, after_own, other, after_other, alone, await _receipt(conn, A, key2), mid, mid2,
                    (own_fp, await stored_fp(key2)))
    own, after_own, other, after_other, alone, row2, mid, mid2, fps = _run(body(main._MAIL_RECEIPT_SQL))
    assert own == 1 and after_own == (mid, "direct", 1, fp1)
    assert other is None and after_other == after_own
    assert alone == 1 and row2 == (mid2, "system_broadcast", 4, fp1)
    # the trigger's digest kept; the upsert's own written, with the body key
    # on the direct message and none on the broadcast
    assert fps == ((send_fp, bk1), (bcast_fp, None))
    # mutant: the upsert's WHERE taken out -> another message's request
    # replaces the digest on this message's receipt
    where = "   WHERE mail_send_receipts.message_id = EXCLUDED.message_id"
    # (each run makes its own messages: compare with this run's message id)
    _own, _after_own, other, after_other, _alone, _row2, m_mid, _m_mid2, _fps = _run(
        body(_mutated(main._MAIL_RECEIPT_SQL, where, "")))
    assert other == 1 and after_other[0] == m_mid and after_other[3] == fp2


def _flat(bound):
    sql, args = bound
    return (sql, *args)


def test_the_replay_reads_the_receipt_after_the_message_is_purged():
    async def body(sql):
        async with _Schema() as conn:
            await conn.execute(M415)
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
            await conn.execute(M415)
            for days in (DAYS + 1, DAYS - 1):
                await conn.execute(
                    "INSERT INTO mail_send_receipts (sender_id, idempotency_key, kind, message_fp, message_id,"
                    " created_at) VALUES ($1, $2, 'direct', $3, $4, NOW() - make_interval(days => $5))",
                    A, str(uuid.uuid4()), bytes(32), str(uuid.uuid4()), days)
            gone = await conn.fetch(*_flat(_bind(sql, {"days": DAYS})))
            left = await conn.fetch("SELECT created_at < NOW() - make_interval(days => $1) AS old"
                                    " FROM mail_send_receipts", DAYS)
            return len(gone), [r["old"] for r in left]
    assert _run(body(main._MAIL_RECEIPT_SWEEP_SQL)) == (1, [False])
    # mutant: the comparison turned round -> the young receipt goes instead
    assert _run(body(_mutated(main._MAIL_RECEIPT_SWEEP_SQL, "created_at < NOW()", "created_at > NOW()"))) \
        == (1, [True])


_RETIRE = re.compile(r"CAST\(overlay\(replace\(CAST\(gen_random_uuid\(\) AS text\), '-', ''\)"
                     r"\s+PLACING '0' FROM 13 FOR 1\) AS uuid\)")


def test_the_sweep_moves_a_kept_message_to_a_reserved_key_and_no_other():
    """A's message to B under key K, made DAYS+1 days ago and still unread,
    so the janitor's purge keeps its row; its receipt is past retention and
    the sweep deletes it. The message moves to a reserved key drawn at
    random, one every route refuses (main._mail_parse_key), so K sent again
    is a new message under 297's unique key, and K's receipt answers for it.
    A's young message keeps its key."""
    retire = _RETIRE.findall(main._MAIL_RECEIPT_SWEEP_SQL)
    assert len(retire) == 1
    retire = retire[0]

    async def body(sweep):
        async with _Schema() as conn:
            await conn.execute(M415)
            key, young_key = str(uuid.uuid4()), str(uuid.uuid4())
            now = await conn.fetchval("SELECT NOW()")
            old = await _message(conn, key=key, at=now - timedelta(days=DAYS + 1))
            await _envelope(conn, old, B)
            young = await _message(conn, key=young_key, at=now - timedelta(days=1))
            swept = len(await conn.fetch(*_flat(_bind(sweep, {"days": DAYS}))))
            keys = {r["id"]: r["k"] for r in await conn.fetch(
                "SELECT id::text AS id, idempotency_key::text AS k FROM mail_messages")}
            moved = (keys[old] != key and _is_reserved(keys[old]), _refused(keys[old]))
            try:
                new = await _message(conn, key=key)
            except asyncpg.PostgresError as e:
                return swept, moved, keys[young] == young_key, e.sqlstate
            return swept, moved, keys[young] == young_key, (await _receipt(conn, A, key))[0] == new
    assert _run(body(main._MAIL_RECEIPT_SWEEP_SQL)) == (1, (True, True), True, True)
    # mutant: the key left as it was -> K sent again breaks 297's unique key
    assert _run(body(_mutated(main._MAIL_RECEIPT_SWEEP_SQL, retire, "m.idempotency_key"))) == \
        (1, (False, False), True, "23505")
    # mutant: the draw without the overlay -> the moved row's key is a
    # version-4 key, one a request can name
    assert _run(body(_mutated(main._MAIL_RECEIPT_SWEEP_SQL, retire, "CAST(%s AS uuid)" % _RANDOM_HEX))) == \
        (1, (False, False), True, True)
    # mutant: the key's match taken out -> every message of the sender moves
    assert _run(body(_mutated(main._MAIL_RECEIPT_SWEEP_SQL, " AND m.idempotency_key = g.idempotency_key",
                              ""))) == (1, (True, True), False, True)


def test_the_sweep_draws_the_retired_key_at_random():
    """A's kept message M (DAYS+1 days old, B's copy unread) whose receipt the
    sweep deletes, while another message of A's already holds the key the
    previous derivation would give M, md5('mail-key-retired:' || M) with the
    version digit 0: the sweep moves M to a reserved key it draws."""
    async def body(sweep):
        async with _Schema() as conn:
            await conn.execute(M415)
            key = str(uuid.uuid4())
            now = await conn.fetchval("SELECT NOW()")
            old = await _message(conn, key=key, at=now - timedelta(days=DAYS + 1))
            await _envelope(conn, old, B)
            held = _reserved("mail-key-retired:" + old)
            await _message(conn, key=held)
            try:
                swept = len(await conn.fetch(*_flat(_bind(sweep, {"days": DAYS}))))
            except asyncpg.PostgresError as e:
                return e.sqlstate
            moved = await conn.fetchval("SELECT idempotency_key::text FROM mail_messages WHERE id = $1", old)
            return swept, moved not in (key, held) and _is_reserved(moved), await _receipt(conn, A, key)
    assert _run(body(main._MAIL_RECEIPT_SWEEP_SQL)) == (1, True, None)
    # mutant: the previous derivation from M's id -> it meets the stored key
    assert _run(body(_mutated(main._MAIL_RECEIPT_SWEEP_SQL, _RANDOM_HEX,
                              "md5('mail-key-retired:' || CAST(m.id AS text))"))) == "23505"


_SUPERSEDE = re.compile(r"    UPDATE mail_send_receipts\n       SET idempotency_key = CAST\(overlay\("
                        r"replace\(CAST\(gen_random_uuid\(\).*?AND message_id <> NEW\.id;\n", re.S)


def _superseding(pattern, new):
    """A mutant of the trigger function's supersession UPDATE: its one match
    of `pattern` replaced by `new` (None: the statement taken out)."""
    stmt = _SUPERSEDE.findall(M415)
    assert len(stmt) == 1
    if new is None:
        return _mutated(M415, stmt[0], "")
    changed, n = re.subn(pattern, lambda _m: new, stmt[0], flags=re.S)
    assert n == 1, pattern
    return _mutated(M415, stmt[0], changed)


def test_a_key_the_previous_build_sends_again_after_a_purge_supersedes_its_receipt():
    """The previous build on the migrated schema. A's direct message under
    key K, whose receipt the current build completed with its request
    digest, is deleted (any way a row goes); the previous build answers a
    retry of K from mail_messages, finds nothing and sends K again as a new
    direct message, and once that one is deleted too, as a broadcast. Each
    time the trigger keeps the superseded receipt -- its message, kind,
    digest and time -- under a reserved key drawn at random, and K's
    receipt is the new message's: a replay of K answers the message
    that exists, by its stored text, and both direct sends stay in A's rate
    window, which counts direct receipts."""
    fp = bytes(range(32))
    window = _sql_in(main._mail_rate_or_raise, "SELECT COUNT(*) FILTER")

    async def body(migration):
        async with _Schema() as conn:
            await conn.execute(migration)
            key = str(uuid.uuid4())
            mids = [await _message(conn, key=key, at=await conn.fetchval("SELECT NOW()") - timedelta(hours=2))]
            await conn.execute(*_flat(_bind(main._MAIL_RECEIPT_SQL, {
                "sid": A, "key": key, "kind": "direct", "fp": fp,
                "mfp": main._mail_message_fp("send", "s", "b"), "mid": mids[0], "n": None,
                "bk": main._mail_body_key("b")})))
            try:
                for kind, count in (("direct", None), ("system_broadcast", 1)):
                    await conn.execute("DELETE FROM mail_messages WHERE id = $1", mids[-1])
                    mids.append(await _message(conn, kind=kind, key=key, count=count))
            except asyncpg.PostgresError as e:
                return e.sqlstate, mids, key
            row = await conn.fetchrow(*_flat(_bind(window, {"sid": A})))
            keyed = {r["mid"]: r["k"] for r in await conn.fetch(
                "SELECT message_id::text AS mid, idempotency_key::text AS k FROM mail_send_receipts")}
            return (await _receipts(conn), keyed, (row["per_minute"], row["per_day"])), mids, key
    (got, keyed, counts), (first, second, third), key = _run(body(M415))
    assert got == {first: ("direct", None, fp, None), second: ("direct", None, None, None),
                   third: ("system_broadcast", 1, None, True)}
    assert set(keyed) == {first, second, third} and keyed[third] == key and keyed[first] != keyed[second]
    assert all(keyed[m] != key and _is_reserved(keyed[m]) and _refused(keyed[m]) for m in (first, second))
    assert counts == (1, 2)
    # mutant: the superseded receipt deleted instead of kept -> both direct
    # sends leave A's rate window
    (got, _keyed, counts), (_first, _second, third), _key = _run(body(_superseding(
        r"    UPDATE mail_send_receipts\n       SET .*?AS uuid\)\n", "    DELETE FROM mail_send_receipts\n")))
    assert got == {third: ("system_broadcast", 1, None, True)} and counts == (0, 0)
    # mutant: no supersession -> K still answers the deleted first message,
    # with the first request's digest and time, and the new sends have no
    # receipt
    (got, keyed, counts), (first, _second, _third), key = _run(body(_superseding(None, None)))
    assert got == {first: ("direct", None, fp, None)} and keyed == {first: key} and counts == (0, 1)
    # mutant: the reserved key derived from K alone -> the second
    # supersession of K takes the first one's key, and the send fails
    sqlstate, mids, _key = _run(body(_superseding(
        re.escape(_RANDOM_HEX), "md5('mail-receipt-superseded:' || CAST(NEW.idempotency_key AS text))")))
    assert sqlstate == "23505" and len(mids) == 2


def test_the_trigger_draws_a_superseded_key_at_random():
    """A's message M_old under key K is deleted, and M_new's id is chosen in
    advance; another message of A's already holds the key the previous
    derivation would give M_old's receipt, md5('mail-receipt-superseded:' ||
    M_old || ':' || M_new) with the version digit 0. M_new sent under K
    commits: the trigger supersedes M_old's receipt under a key it draws,
    and K's receipt names M_new."""
    derived = "md5('mail-receipt-superseded:' || CAST(message_id AS text) || ':' || CAST(NEW.id AS text))"

    async def body(migration):
        async with _Schema() as conn:
            await conn.execute(migration)
            key, new_id = str(uuid.uuid4()), str(uuid.uuid4())
            first = await _message(conn, key=key)
            await conn.execute("DELETE FROM mail_messages WHERE id = $1", first)
            held = _reserved("mail-receipt-superseded:%s:%s" % (first, new_id))
            await _message(conn, key=held)
            try:
                await _message(conn, key=key, mid=new_id)
            except asyncpg.PostgresError as e:
                return e.sqlstate
            moved = await conn.fetchval("SELECT idempotency_key::text FROM mail_send_receipts"
                                        " WHERE message_id = $1", first)
            return (await _receipt(conn, A, key))[0] == new_id, moved not in (key, held) and _is_reserved(moved)
    assert _run(body(M415)) == (True, True)
    # mutant: the trigger's key derived from the two message ids -> it meets
    # the stored key and the send fails
    assert _run(body(_superseding(re.escape(_RANDOM_HEX), derived))) == "23505"


def test_a_replys_in_reply_to_names_its_parent_whatever_the_parents_purge(monkeypatch):
    """B replies to A's message, which A also sent to C; A and B then delete
    their copies of the original. `other` is C's copy: delivered and unread,
    it keeps the original's row through the purge; suppressed, the purge
    removes it. B's detail read of the reply (the route) names the original
    in both worlds."""
    _route_stubs(monkeypatch)
    keep_fk = (("    EXECUTE format('ALTER TABLE mail_messages DROP CONSTRAINT %I', k.conname);\n", "    NULL;\n"),
               ("    RAISE EXCEPTION '415: a foreign key still covers mail_messages.in_reply_to';\n",
                "    NULL;\n"))

    async def body(migration, other):
        async with _Schema() as conn:
            await conn.execute(migration)
            orig = await _message(conn, sender=A)
            await _envelope(conn, orig, B)
            await _envelope(conn, orig, C, other)
            rep = await _message(conn, sender=B, thread=orig, parent=orig)
            await _envelope(conn, rep, A)
            await conn.execute("UPDATE mail_recipients SET deleted_at = NOW()"
                               " WHERE message_id = $1 AND recipient_id = $2", orig, B)
            await conn.execute("UPDATE mail_messages SET deleted_by_sender_at = NOW() WHERE id = $1", orig)
            await _janitor_purge(conn)
            kept = await conn.fetchval("SELECT 1 FROM mail_messages WHERE id = $1", orig) is not None
            got = await _detail(_Session(conn), rep, me=B)
            return kept, (got["in_reply_to"] == orig if got["in_reply_to"] else None)
    assert {o: _run(body(M415, o)) for o in ("delivered", "suppressed")} == {
        "delivered": (True, True), "suppressed": (False, True)}
    # mutant: 297's foreign key kept (its drop and its check taken out) ->
    # the purge empties in_reply_to in the second world only
    kept_fk = M415
    for old, new in keep_fk:
        kept_fk = _mutated(kept_fk, old, new)
    assert {o: _run(body(kept_fk, o)) for o in ("delivered", "suppressed")} == {
        "delivered": (True, True), "suppressed": (False, None)}


def test_the_fanout_writes_a_forced_addressee_suppressed_whatever_their_settings():
    """C takes mail from everyone and has blocked nobody; passed forced, C's
    copy is suppressed all the same."""
    async def body(sql):
        async with _Schema() as conn:
            await conn.execute(M415)
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


def test_the_senders_three_reads_follow_the_clock(monkeypatch):
    """A's messages to B, one sent DAYS+1 days ago and one DAYS-1 days ago,
    both delivered and unread (so the janitor keeps both rows): A's Sent,
    detail and reply all (the routes) reach the young one only; B's detail
    reaches both."""
    _route_stubs(monkeypatch)

    async def body(mutant):
        async with _Schema() as conn:
            await conn.execute(M415)
            now = datetime.now(timezone.utc)
            old = await _message(conn, at=now - timedelta(days=DAYS + 1))
            young = await _message(conn, at=now - timedelta(days=DAYS - 1))
            for mid in (old, young):
                await _envelope(conn, mid, B)
            rewrite, hits = _rewriting(SENDER_CLOCK, "") if mutant else (None, [])
            sess = _Session(conn, rewrite=rewrite)
            out = {"sent": {m["id"] for m in (await _sent(sess))["messages"]}}
            for name, read in (("detail", lambda mid: _detail(sess, mid)),
                               ("reply", lambda mid: _reply(sess, mid)),
                               ("recipient", lambda mid: _detail(sess, mid, me=B))):
                out[name] = set()
                for mid in (old, young):
                    if await read(mid) != NOT_FOUND:
                        out[name].add(mid)
            return out, old, young, len(hits)
    out, old, young, hits = _run(body(False))
    assert out == {"sent": {young}, "detail": {young}, "reply": {young}, "recipient": {old, young}}
    # mutant: the clock taken out of all three (each of the 7 reads ran
    # without it) -> the sender reaches the old message for as long as its
    # row exists
    out, old, young, hits = _run(body(True))
    assert hits == 7 and out == {"sent": {old, young}, "detail": {old, young}, "reply": {old, young},
                                 "recipient": {old, young}}


def test_the_sender_clock_is_read_inside_each_statement(monkeypatch):
    """Each read that applies the retention clock: the reply core, Sent, the
    detail read and the Discord read-back (mail_discord._REPLIED_TO_SQL).
    The reader's transaction starts (SELECT NOW()); another connection sets
    the message's created_at to that transaction's NOW() - MAIL_RETENTION_DAYS
    + 0.7 s, and 1.5 s later the route runs in the same transaction. The
    message is past the clock when the statement runs, so it is refused both
    where B's unread delivered copy keeps its row ("kept") and where the
    janitor's purge, run from the other connection after the wait, removed
    it ("purged"). For the read-back the message is B's reply to A, the
    copy A's."""
    _route_stubs(monkeypatch)

    async def refused(route, sess, mid):
        if route == "reply":
            return await _reply(sess, mid) == NOT_FOUND
        if route == "detail":
            return await _detail(sess, mid) == NOT_FOUND
        if route == "sent":
            return mid not in {m["id"] for m in (await _sent(sess))["messages"]}
        row = (await sess.execute(mail_discord._REPLIED_TO_SQL, {
            "rid": mid, "sid": _STEAM[B], "pid": uuid.UUID(B), "ret_days": DAYS})).first()
        return row is None

    async def body(route, state, mutant):
        schema = _Schema()
        async with schema as conn:
            await conn.execute(M415)
            other = await schema.other()
            copy = "delivered" if state == "kept" else "suppressed"
            if route == "replied to":
                orig = await _message(conn, sender=A)
                await _envelope(conn, orig, B)
                mid = await _message(conn, sender=B, thread=orig, parent=orig)
                await _envelope(conn, mid, A, copy)
            else:
                mid = await _message(conn, sender=A)
                await _envelope(conn, mid, B, copy)
            rewrite, hits = _rewriting("t.now_", "NOW()") if mutant else (None, [])
            sess = _Session(conn, rewrite=rewrite)
            tr = conn.transaction()
            await tr.start()
            try:
                start = await conn.fetchval("SELECT NOW()")
                await other.execute(
                    "UPDATE mail_messages SET created_at = CAST($1 AS timestamptz)"
                    " - make_interval(days => $2) + interval '0.7 seconds' WHERE id = $3",
                    start, DAYS, mid)
                await asyncio.sleep(1.5)
                purged = await _janitor_purge(other)
                out = (purged, await refused(route, sess, mid))
            finally:
                await tr.rollback()
            return out, bool(hits)
    routes = ("reply", "sent", "detail", "replied to")
    for route in routes:
        assert {s: _run(body(route, s, False)) for s in ("kept", "purged")} == {
            "kept": ((0, True), False), "purged": ((1, True), False)}, route
    # mutant: the transaction's NOW() in place of the clock read inside the
    # statement -> the kept message is admitted 0.8 s past its retention
    for route in routes:
        assert {s: _run(body(route, s, True)) for s in ("kept", "purged")} == {
            "kept": ((0, False), True), "purged": ((1, True), True)}, route


def test_the_senders_views_read_a_message_and_its_addressees_in_one_statement(monkeypatch):
    """A's message to B (To) and C (Cc), both copies delivered. Right after
    the route's first statement that reads mail_messages, another connection
    purges the message (DELETE, committed) while the route's transaction is
    open. Reply all, Sent and the detail read each answer as they answer with
    the message kept: the message and its addressees come from that one
    statement's snapshot. The purge is the only work between that statement
    and the route's answer."""
    _route_stubs(monkeypatch)
    prefix = {"reply all": "env_", "sent": "addr_", "detail": "addr_"}
    to = {"steam_id": _STEAM[B], "name": _NAME[B]}
    cc = {"steam_id": _STEAM[C], "name": _NAME[C]}
    want = {"reply all": ("reached the send", [(uuid.UUID(B), "to", False), (uuid.UUID(C), "cc", False)]),
            "sent": [[dict(to, kind="to"), dict(cc, kind="cc")]],
            "detail": ([to], [cc])}
    two_statements = {"reply all": (400, "recipients_empty"), "sent": [[]], "detail": ([], [])}

    def addressees(route, answer):
        if route == "reply all":
            return answer
        if route == "sent":
            return [m["addressees"] for m in answer["messages"]]
        return answer["to"], answer["cc"]

    async def call(route, sess, mid):
        if route == "reply all":
            return await _reply(sess, mid, reply_all=True)
        if route == "sent":
            return await _sent(sess)
        return await _detail(sess, mid)

    async def body(route, split):
        schema = _Schema()
        async with schema as conn:
            await conn.execute(M415)
            other = await schema.other()
            mid = await _message(conn, sender=A)
            await _envelope(conn, mid, B, kind="to")
            await _envelope(conn, mid, C, kind="cc")
            kept = await call(route, _Session(conn), mid)

            async def purge():
                await other.execute("DELETE FROM mail_messages WHERE id = $1", mid)
            after, fired = _once(purge)
            sess = _Session(conn, after=after, split=(main._MAIL_CLOCK_CTE, prefix[route]) if split else None)
            tr = conn.transaction()
            await tr.start()
            try:
                got = await call(route, sess, mid)
            finally:
                await tr.rollback()
            gone = await conn.fetchval("SELECT count(*) FROM mail_messages WHERE id = $1", mid) == 0
            # the hook fired once, on the route's own read (the clock CTE
            # opens it), so the purge lands after that statement
            return kept, got, [s.startswith(main._MAIL_CLOCK_CTE) for s in fired], gone
    for route in prefix:
        kept, got, fired, gone = _run(body(route, False))
        assert addressees(route, kept) == want[route] and fired == [True] and gone, route
        assert got == kept, route
    # mutant: the message and its addressees read by two statements, the
    # purge between them -> reply all finds no addressee, and Sent and the
    # detail read list none
    for route in prefix:
        kept, got, fired, gone = _run(body(route, True))
        assert addressees(route, kept) == want[route] and fired == [True] and gone, route
        assert addressees(route, got) == two_statements[route], route


def _sql_in(fn, prefix):
    """The one `text(...)` statement in `fn`'s source that starts with
    `prefix`, as production passes it."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    found = [n.args[0].value for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "text" and n.args
             and isinstance(n.args[0], ast.Constant) and str(n.args[0].value).startswith(prefix)]
    assert len(found) == 1, (fn.__name__, prefix, found)
    return found[0]


async def _janitor_purge(conn):
    """The janitor's purge as it runs (main._mail_purge_due: since mscl-r2
    its hold of the messages due, its locks of the rows their foreign keys
    write, a second read of those rows and its DELETE, each a statement of
    its own), in one transaction over `conn`: the number of messages it
    removed."""
    async with conn.transaction():
        return len(await main._mail_purge_due(_Session(conn)))


def test_the_rate_window_counts_receipts_whatever_the_purge_removed():
    """_mail_rate_or_raise's statement on PostgreSQL. A's direct sends 10,
    20 and 30 s ago and 2 h ago, one 2 days ago, and a broadcast 5 s ago:
    3 in the minute and 4 in the day. The rows of the 10 s and 20 s sends
    are then deleted (the delete stands for the janitor's purge or any other
    way a row could go -- their receipts have no foreign key and stay): the
    counts do not move."""
    stmt = _sql_in(main._mail_rate_or_raise, "SELECT COUNT(*) FILTER")

    async def body(stmt):
        async with _Schema() as conn:
            await conn.execute(M415)
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

    async def body(stmt, other):
        async with _Schema() as conn:
            await conn.execute(M415)
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
                await _janitor_purge(conn)
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


def test_the_spam_check_counts_receipts_whatever_the_purge_removed(monkeypatch):
    """_mail_spam_check, reached through _mail_finish_send, on PostgreSQL. A
    sends B four messages with one body and deletes them. "purged": B's
    copies are suppressed and the janitor's purge removes all four rows at
    once; "kept": B's unread delivered copies keep them. A fifth send of the
    body opens a mail_spam case in both states, counting 5. Four sends the
    previous build made (rows inserted directly, so only migration 415's
    trigger writes their receipts, with no body key) count in neither state:
    the fifth send opens no case."""
    _route_stubs(monkeypatch)
    cases = []

    async def nothing(*_a, **_k):
        return None

    async def case(_db, _sender, **kw):
        cases.append(kw["same_body"])
    # the rate window would refuse sends this close together; it is not under
    # test here (test_the_rate_window_counts_receipts_whatever_the_purge_removed)
    monkeypatch.setattr(main, "_mail_rate_or_raise", nothing)
    monkeypatch.setattr(mail_discord, "queue_mail_relay", nothing)
    monkeypatch.setattr(main, "_mail_spam_case", case)
    same_body = re.findall(
        r"\(SELECT COUNT\(\*\) FROM mail_send_receipts\s+WHERE sender_id = :sid AND kind = 'direct'"
        r"\s+AND body_key = CAST\(:bk AS bytea\)\s+AND created_at > NOW\(\) - make_interval\(days => 1\)\)"
        r" AS same_body", _sql_in(main._mail_spam_check, "SELECT"))
    assert len(same_body) == 1
    # the count before migration 415's change, of the sender's message rows
    # (a digest of the stored body stands for the Python comparison, which
    # agrees for a body already in its normal form)
    rows_count = ("(SELECT COUNT(*) FROM mail_messages WHERE sender_id = :sid AND kind = 'direct'"
                  " AND sha256(convert_to(body, 'UTF8')) = CAST(:bk AS bytea)"
                  " AND created_at > NOW() - make_interval(days => 1)) AS same_body")
    spam = "buy my cards now"
    assert main._mail_norm_body(spam) == spam
    ddl = [_from_file("297_mail.sql", r"CREATE TABLE IF NOT EXISTS mail_censor_hits \(.*?\n\);"),
           _from_file("300_mail_inbox_rev.sql", r"CREATE TABLE IF NOT EXISTS mail_inbox_rev \(.*?\n\);")]

    async def body(sends, state, mutant):
        del cases[:]
        async with _Schema() as conn:
            await conn.execute(M415)
            for stmt in ddl:
                await conn.execute(stmt)
            rewrite, hits = _rewriting(same_body[0], rows_count) if mutant else (None, [])
            sess = _Session(conn, rewrite=rewrite)
            suppressed = state == "purged"

            async def send():
                await main._mail_finish_send(
                    sess, _me(A), subject="Hi there", body=spam,
                    addressees=[(uuid.UUID(B), "to", suppressed)], thread_id=None, in_reply_to=None,
                    idempotency_key=uuid.uuid4(),
                    request_fp=main._mail_request_fp("send", to=[_STEAM[B]], cc=[], subject="Hi there",
                                                     body=spam),
                    cap=64)
            for _ in range(4):
                if sends == "api":
                    await send()
                else:
                    mid = await _message(conn, body=spam)
                    await _envelope(conn, mid, B, "suppressed" if suppressed else "delivered")
            await conn.execute("UPDATE mail_messages SET deleted_by_sender_at = NOW() WHERE sender_id = $1", A)
            purged = await _janitor_purge(conn)
            await send()
            # the mutant reached every spam check: one per send through the api
            reached = (len(hits) == (5 if sends == "api" else 1)) if mutant else not hits
            return purged, list(cases), reached
    worlds = [(s, st) for s in ("api", "previous build") for st in ("purged", "kept")]
    assert {w: _run(body(*w, False)) for w in worlds} == {
        ("api", "purged"): (4, [5], True), ("api", "kept"): (0, [5], True),
        ("previous build", "purged"): (4, [], True), ("previous build", "kept"): (0, [], True)}
    # mutant: the count of the sender's message rows -> it follows the
    # copies' delivery: the purged sends leave it, the kept ones (the
    # previous build's included) stay in it
    assert {w: _run(body(*w, True)) for w in worlds} == {
        ("api", "purged"): (4, [], True), ("api", "kept"): (0, [5], True),
        ("previous build", "purged"): (4, [], True), ("previous build", "kept"): (0, [5], True)}


# ── the rollback ──────────────────────────────────────────────────────────

def test_the_rollback_restores_297s_foreign_key_runs_twice_and_refuses_a_differing_one():
    """On the migrated schema, B's reply to a message that was then deleted
    names a row no longer there, and B's reply to a kept message names that
    one. The rollback drops 415's objects, sets the first reply's in_reply_to
    to NULL, keeps the second's and restores 297's foreign key; run again it
    changes nothing, and 297's unique key stays throughout. A foreign key on
    in_reply_to that differs from 297's -- the same name, ON DELETE CASCADE,
    NOT VALID -- aborts the whole file, naming what it found."""
    cascade = ("ALTER TABLE mail_messages ADD CONSTRAINT mail_messages_in_reply_to_fkey"
               " FOREIGN KEY (in_reply_to) REFERENCES mail_messages(id) ON DELETE CASCADE NOT VALID")

    async def body(rollback):
        async with _Schema() as conn:
            await conn.execute(M415)
            gone, kept = await _message(conn), await _message(conn)
            replies = [await _message(conn, sender=B, thread=p, parent=p) for p in (gone, kept)]
            await conn.execute("DELETE FROM mail_messages WHERE id = $1", gone)
            out = {}
            for run in ("first", "second"):
                try:
                    await conn.execute(rollback)
                except asyncpg.PostgresError as e:
                    await conn.execute("ROLLBACK")
                    out[run] = e.sqlstate
                    return out
                parents = [await conn.fetchval("SELECT in_reply_to::text FROM mail_messages WHERE id = $1", r)
                           for r in replies]
                out[run] = (await _shape(conn), parents == [None, kept])
            await conn.execute(M415)
            await conn.execute(cascade)
            try:
                await conn.execute(rollback)
                out["differing"] = None
            except asyncpg.PostgresError as e:
                await conn.execute("ROLLBACK")
                out["differing"] = str(e)
            out["after"] = await _shape(conn)
            return out
    out = _run(body(R415))
    assert out["first"] == out["second"] == (ROLLED_BACK, True)
    assert "rollback 415: the foreign key on mail_messages.in_reply_to differs from 297's (found:" \
        " mail_messages_in_reply_to_fkey FOREIGN KEY (in_reply_to) REFERENCES mail_messages(id)" \
        " ON DELETE CASCADE NOT VALID)" in out["differing"]
    assert out["after"] == dict(APPLIED, fk=True)            # the refusal rolled the whole file back
    # mutant: the definition's comparison taken out -> the differing key is
    # accepted and the file commits over it
    out = _run(body(_mutated(R415, "= 'FOREIGN KEY (in_reply_to) REFERENCES mail_messages(id) ON DELETE SET NULL')",
                             "IS NOT NULL)")))
    assert out["differing"] is None and out["after"] == ROLLED_BACK
    # mutant: no reply's in_reply_to set to NULL -> restoring the key fails
    # on the deleted parent
    assert _run(body(_mutated(R415, "AND NOT EXISTS (SELECT 1 FROM mail_messages p WHERE p.id = m.in_reply_to);",
                              "AND false;"))) == {"first": "23503"}
    # mutant: every reply's in_reply_to set to NULL -> the kept parent's
    # reply loses it too
    out = _run(body(_mutated(R415, "\n       AND NOT EXISTS (SELECT 1 FROM mail_messages p WHERE p.id = m.in_reply_to);",
                             ";")))
    assert out["first"] == (ROLLED_BACK, False)
    # mutant: the key added whatever is there -> the second run fails
    out = _run(body(_mutated(R415, "IF total = 0 THEN", "IF true THEN")))
    assert out == {"first": (ROLLED_BACK, True), "second": "42710"}
