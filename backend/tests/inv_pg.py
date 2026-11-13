"""Lobby invites on PostgreSQL (migration 405's change): the case harness the
invite suites share.

One case schema per case through cf_pg: every numbered migration's DDL is
replayed (404 and 405 among them), the held-out ones run whole, and the
real handlers in main.py are called with a session bound to that schema.
Two seams are replaced, both outside what these suites test: the session
token (a Req names its player, and the stand-in for _mail_caller runs that
function's own player read), and the lobby routes' session check (cf_asm's
stand-in). Everything an invite does -- the identity and per-sender locks,
the receipts, the lobby cores, mail's row write and fan-out, the relay and
the revision bumps -- runs as written.

A mutant is a statement rewrite (Env.rewriting): every statement the case's
engine sends passes through each active rewrite, and the rewrite's hits list
proves that the mutant reached a statement. A rewrite keeps every bind
placeholder, so the statement still takes the parameters it is sent.

CF_TEST_PG_DSN names the lane database; unset and not waived
(CF_TEST_PG_OPTOUT=1), every case FAILS (cf_pg.require_live_pg).
"""

import asyncio
import contextlib
import inspect
import json
import os
import re
import sys
import types
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import event, text  # noqa: E402

import cf_pg  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402
import mail_discord  # noqa: E402
import main  # noqa: E402

FLOOR = main.INVITE_FLOOR_VERSION
BELOW = "1.41.0"
STEAM_BASE = 76561190040600000
MODES = ("team", "ovt", "ffa")
LOBBY_TABLE = {"team": "team_lobbies", "ovt": "ovt_lobbies", "ffa": "ffa_lobbies"}
QUEUE_TABLE = {"team": "team_queue", "ovt": "ovt_queue", "ffa": "ffa_queue"}

# What a case's snapshot reads: every table an invite request can write.
SNAPSHOT_TABLES = (
    "lobby_invites", "invite_receipts", "mail_messages", "mail_recipients", "mail_inbox_rev",
    "mail_send_receipts", "pending_dms", "team_lobbies", "team_queue", "ovt_lobbies", "ovt_queue",
    "ffa_lobbies", "ffa_queue", "queue_leases",
)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def key():
    """A fresh idempotency key a client may send (version digit 4)."""
    return str(uuid.uuid4())


class Answer:
    """A handler's answer: its status and body (the detail when it refused).
    `wire` is the JSON a client reads, keys sorted, so two answers compare
    byte for byte."""
    __slots__ = ("status", "body")

    def __init__(self, status, body):
        self.status = status
        self.body = body

    @property
    def wire(self):
        return json.dumps([self.status, self.body], sort_keys=True, separators=(",", ":"),
                          default=str)

    def __getitem__(self, k):
        return self.body[k]

    def get(self, k, d=None):
        return self.body.get(k, d) if isinstance(self.body, dict) else d

    def __eq__(self, other):
        return isinstance(other, Answer) and self.wire == other.wire

    __hash__ = None

    def __repr__(self):
        return "Answer(%r, %r)" % (self.status, self.body)


class Req:
    """What the handlers read off a request once the token is replaced: the
    player the session names (sid), the client version the middleware puts
    on request.state, and no headers."""

    def __init__(self, sid, version=FLOOR):
        self.sid = sid
        self.headers = {}
        self.client = None
        self.url = "http://inv.test/"
        self.state = types.SimpleNamespace(mod_version=version)


# _mail_caller's own player read, run on the player the Req names.
CALLER_SQL = ("SELECT id, steam_id, display_name, mod_seen_at, mail_from,"
              "       mail_discord_relay, discord_id"
              "  FROM players WHERE steam_id = :sid AND deleted_at IS NULL")


async def _caller(request, db):
    row = (await db.execute(text(CALLER_SQL), {"sid": request.sid})).mappings().first()
    if row is None:
        raise HTTPException(status_code=401, detail="session_required")
    return dict(row)


class P:
    """A player: id, steam id, display name."""
    __slots__ = ("id", "sid", "name")

    def __init__(self, pid, sid, name):
        self.id = pid
        self.sid = sid
        self.name = name

    def __repr__(self):
        return "P(%s)" % self.name


def placeholder_rx(column):
    """`column = <bind>` in a compiled statement, whatever the dialect's
    paramstyle ($n, %s or :name)."""
    return re.compile(r"\b%s = (\$\d+|%%s|%%\(\w+\)s|:\w+)" % re.escape(column))


class Env:
    """One case: its connection, its sessions, the players it seeds and the
    handlers it calls."""

    def __init__(self, c, sm, mp):
        self.c = c
        self.conn = c.conn
        self.sm = sm
        self.engine = sm.kw["bind"]
        self.mp = mp
        self.serial = 0
        self._rewrites = []
        self._side = []
        # The stand-in reads the same columns as _mail_caller's player read;
        # a column the real read gains fails here, not as a silent default.
        src = inspect.getsource(main._mail_caller)
        assert '"SELECT id, steam_id, display_name, mod_seen_at, mail_from,"' in src
        assert '"       mail_discord_relay, discord_id"' in src
        mp.setattr(main, "_mail_caller", _caller)

        async def _no_session(request, steam_id, db):
            return None
        mp.setattr(main, "_check_steam_session", _no_session)
        mp.setattr(main, "_presence_seen", {})
        event.listen(self.engine.sync_engine, "before_cursor_execute", self._before, retval=True)

    def _before(self, conn, cursor, statement, parameters, context, executemany):
        for rw in list(self._rewrites):
            statement = rw(statement)
        return statement, parameters

    async def close(self):
        try:
            event.remove(self.engine.sync_engine, "before_cursor_execute", self._before)
        except Exception:                                  # pragma: no cover
            pass
        for conn in self._side:
            if not conn.is_closed():
                await conn.close()

    @contextlib.contextmanager
    def rewriting(self, old, new, where=None):
        """A mutant: every statement holding `old` (a string, or a compiled
        pattern) -- and `where`, when given -- has it replaced by `new` while
        the block runs. Yields the list of statements it changed."""
        hits = []

        def rw(sql):
            if where is not None and where not in sql:
                return sql
            if isinstance(old, str):
                if old not in sql:
                    return sql
                out = sql.replace(old, new)
            else:
                out, n = old.subn(new, sql)
                if not n:
                    return sql
            hits.append(sql)
            return out
        self._rewrites.append(rw)
        try:
            yield hits
        finally:
            self._rewrites.remove(rw)

    async def side(self):
        """A second session's connection, bound to the case schema."""
        conn = await harness.connect_bound(self.c.dsn, self.c.schema)
        self._side.append(conn)
        return conn

    async def require_schema(self):
        """What the suites need from the build, named when it is missing."""
        got = await self.conn.fetchrow(
            "SELECT to_regclass('lobby_invites') IS NOT NULL AS invites,"
            "       to_regclass('invite_receipts') IS NOT NULL AS receipts,"
            "       to_regclass('mail_send_receipts') IS NOT NULL AS mail_receipts,"
            "       EXISTS (SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid"
            "                WHERE c.relname = 'mail_messages' AND c.relnamespace ="
            "                      (SELECT oid FROM pg_namespace WHERE nspname = current_schema())"
            "                  AND NOT t.tgisinternal) AS trigger")
        assert dict(got) == {"invites": True, "receipts": True, "mail_receipts": True,
                             "trigger": True}, ("the case build lacks", dict(got))

    # -- seeding ------------------------------------------------------------

    async def player(self, name=None, *, version=FLOOR, seen=True, mail_from="everyone"):
        self.serial += 1
        sid = str(STEAM_BASE + self.serial)
        name = name or "inv%d" % self.serial
        pid = uuid.uuid4()
        await self.conn.execute(
            "INSERT INTO players (id, steam_id, display_name, mod_version, mod_seen_at, mail_from)"
            " VALUES ($1, $2, $3, $4, CASE WHEN $5 THEN NOW() END, $6)",
            pid, sid, name, version, seen, mail_from)
        return P(pid, sid, name)

    async def players(self, n, **kw):
        return [await self.player(**kw) for _ in range(n)]

    # -- calling ------------------------------------------------------------

    async def call(self, fn):
        """`fn(db)` in a session of its own: its Answer."""
        async with self.sm() as db:
            try:
                out = await fn(db)
            except HTTPException as exc:
                return Answer(exc.status_code, exc.detail)
        if hasattr(out, "status_code") and hasattr(out, "body"):
            return Answer(out.status_code, json.loads(bytes(out.body).decode("utf-8")))
        return Answer(200, out)

    async def ok(self, fn):
        ans = await self.call(fn)
        assert ans.status == 200, ans
        return ans

    # -- lobbies --------------------------------------------------------------

    async def create(self, mode, host, **kw):
        """`host` opens a lobby of `mode`; its id."""
        if mode == "ffa":
            req = main._FfaLobbyCreateReq(steam_id=host.sid, display_name=host.name, **kw)
            ans = await self.ok(lambda db: main.ffa_lobby_create(req, Req(host.sid), db))
        else:
            req = main._LobbyCreateReq(steam_id=host.sid, display_name=host.name, **kw)
            ans = await self.ok(lambda db: main._lobby_create_impl(mode, req, Req(host.sid), db))
        return uuid.UUID(ans["lobby_id"])

    async def join(self, mode, p, lid, **kw):
        if mode == "ffa":
            req = main._FfaLobbyJoinReq(steam_id=p.sid, display_name=p.name, lobby_id=str(lid), **kw)
            return await self.call(lambda db: main.ffa_lobby_join(req, Req(p.sid), db))
        req = main._LobbyJoinReq(steam_id=p.sid, display_name=p.name, lobby_id=str(lid), **kw)
        return await self.call(lambda db: main._lobby_join_impl(mode, req, Req(p.sid), db))

    async def lobby(self, mode, n=1, **kw):
        """A lobby of `mode` with `n` members, the first its host: (lid, members)."""
        ps = await self.players(n, **kw)
        lid = await self.create(mode, ps[0])
        for p in ps[1:]:
            ans = await self.join(mode, p, lid)
            assert ans.status == 200, ans
        return lid, ps

    async def leave(self, mode, p, lid=None):
        exp = str(lid) if lid is not None else None
        if mode == "ffa":
            return await self.call(lambda db: main.ffa_queue_leave(
                Req(p.sid), steam_id=p.sid, expected_lobby_id=exp, cause="", label="", db=db))
        return await self.call(lambda db: main._lobby_leave_impl(mode, p.sid, exp, Req(p.sid), db))

    async def kick(self, mode, host, target):
        req = main._LobbyKickReq(steam_id=host.sid, target_steam_id=target.sid)
        if mode == "ffa":
            return await self.call(lambda db: main.ffa_lobby_kick(req, Req(host.sid), db))
        return await self.call(lambda db: main._lobby_kick_impl(mode, req, Req(host.sid), db))

    async def fresh(self, mode, lid):
        """Every member's lobby row polled now (the live-member rule's clock)."""
        await self.conn.execute(
            "UPDATE %s SET last_polled = clock_timestamp() WHERE series_id = $1 AND status = 'lobby'"
            % QUEUE_TABLE[mode], lid)

    async def stale(self, mode, p, lid, seconds=600):
        """`p`'s lobby row not polled for `seconds`: not a live member."""
        await self.conn.execute(
            "UPDATE %s SET last_polled = clock_timestamp() - make_interval(secs => $3)"
            " WHERE player_id = $1 AND series_id = $2" % QUEUE_TABLE[mode], p.id, lid, float(seconds))

    async def members(self, mode, lid):
        rows = await self.conn.fetch(
            "SELECT player_id FROM %s WHERE series_id = $1 AND status = 'lobby' ORDER BY player_id"
            % QUEUE_TABLE[mode], lid)
        return [r["player_id"] for r in rows]

    async def lobby_status(self, mode, lid):
        return await self.conn.fetchval("SELECT status FROM %s WHERE id = $1" % LOBBY_TABLE[mode], lid)

    # -- invites --------------------------------------------------------------

    async def send(self, sender, invitee, mode, lid=None, *, k=None, version=FLOOR, **kw):
        req = main._InviteSendReq(invitee_steam_id=invitee.sid if isinstance(invitee, P) else invitee,
                                  mode=mode, lobby_id=str(lid) if lid is not None else None,
                                  display_name=sender.name, idempotency_key=k or key(), **kw)
        return await self.call(lambda db: main.invite_send(req, Req(sender.sid, version), db))

    async def invite(self, sender, invitee, mode, lid=None, **kw):
        """A send that must succeed: the invite's id."""
        ans = await self.send(sender, invitee, mode, lid, **kw)
        assert ans.status == 200, ans
        return uuid.UUID(ans["invite_id"])

    async def accept(self, p, iid, *, k=None, version=FLOOR, **kw):
        req = main._InviteAcceptReq(display_name=p.name, idempotency_key=k or key(), **kw)
        return await self.call(lambda db: main.invite_accept(str(iid), req, Req(p.sid, version), db))

    async def decline(self, p, iid, *, k=None):
        req = main._InviteAnswerReq(idempotency_key=k or key())
        return await self.call(lambda db: main.invite_decline(str(iid), req, Req(p.sid), db))

    async def cancel(self, p, iid, *, k=None):
        req = main._InviteAnswerReq(idempotency_key=k or key())
        return await self.call(lambda db: main.invite_cancel(str(iid), req, Req(p.sid), db))

    async def pending(self, p, version=FLOOR):
        return await self.call(lambda db: main.invite_pending(
            Req(p.sid, version), cursor="", limit=main.INVITE_PAGE_MAX, db=db))

    async def row(self, iid):
        r = await self.conn.fetchrow("SELECT * FROM lobby_invites WHERE id = $1", iid)
        return dict(r) if r is not None else None

    async def mail_of(self, iid):
        return await self.conn.fetchval("SELECT mail_message_id FROM lobby_invites WHERE id = $1", iid)

    async def delivery(self, mid, p):
        return await self.conn.fetchval(
            "SELECT delivery FROM mail_recipients WHERE message_id = $1 AND recipient_id = $2", mid, p.id)

    async def rev(self, p):
        return await self.conn.fetchval("SELECT rev FROM mail_inbox_rev WHERE recipient_id = $1", p.id) or 0

    async def age(self, iid, *, expired_s=None, kept_days=None, mail_days=None):
        """Move an invite back in time: its expires_at `expired_s` seconds
        ago, or `kept_days` days ago; its mail row's created_at `mail_days`
        days ago."""
        if expired_s is not None:
            await self.conn.execute(
                "UPDATE lobby_invites SET expires_at = clock_timestamp() - make_interval(secs => $2),"
                "       created_at = LEAST(created_at, clock_timestamp() - make_interval(secs => $2 + 600))"
                " WHERE id = $1", iid, float(expired_s))
        if kept_days is not None:
            await self.conn.execute(
                "UPDATE lobby_invites SET expires_at = clock_timestamp() - make_interval(days => $2),"
                "       created_at = clock_timestamp() - make_interval(days => $2, mins => 10)"
                " WHERE id = $1", iid, int(kept_days))
        if mail_days is not None:
            await self.conn.execute(
                "UPDATE mail_messages SET created_at = clock_timestamp() - make_interval(days => $2)"
                " WHERE id = (SELECT mail_message_id FROM lobby_invites WHERE id = $1)", iid, int(mail_days))

    async def sweep(self):
        """The janitor's invite arm, as queue_cleanup_loop runs it."""
        async with self.sm() as db:
            n = await main._invite_sweep(db)
            await db.commit()
        return n

    async def retention(self):
        """The invite retention and the mail retention sweeps, each committed."""
        async with self.sm() as db:
            n = await main._invite_retention_sweep(db)
            await db.commit()
        async with self.sm() as db:
            m = await main._mail_retention_sweep(db)
            await db.commit()
        return n, m

    # -- mail -----------------------------------------------------------------

    async def mail(self, sender, to, subject="Hello", body="An ordinary message.", *, k=None):
        req = main._MailSendReq(to=[p.sid for p in to], subject=subject, body=body,
                                idempotency_key=k or key())
        return await self.call(lambda db: main.mail_send(req, Req(sender.sid), db))

    async def snapshot(self):
        """Every row of every table an invite request can write, as text."""
        out = {}
        for t in SNAPSHOT_TABLES:
            if not await self.conn.fetchval("SELECT to_regclass($1) IS NOT NULL", t):
                continue
            rows = await self.conn.fetch("SELECT CAST(x AS text) AS r FROM %s x" % t)
            out[t] = sorted(r["r"] for r in rows)
        return out


def case(monkeypatch, body, prefix="inv"):
    """Build a case, run `body(env)` in it, close it."""
    cf_pg.require_live_pg()

    async def go():
        async with cf_pg.case(prefix) as (c, sm):
            env = Env(c, sm, monkeypatch)
            try:
                await env.require_schema()
                await body(env)
            finally:
                await env.close()
    run(go())


async def waiting_on(env, blocker_pid, tries=100):
    """The pids that wait on `blocker_pid`'s locks, polled until one does
    (bounded: `tries` polls 50 ms apart)."""
    for _ in range(tries):
        got = await env.conn.fetch(
            "SELECT pid FROM pg_stat_activity WHERE $1 = ANY(pg_blocking_pids(pid))", blocker_pid)
        if got:
            return [r["pid"] for r in got]
        await asyncio.sleep(0.05)
    return []


__all__ = ["Answer", "BELOW", "Env", "FLOOR", "LOBBY_TABLE", "MODES", "P", "QUEUE_TABLE", "Req",
           "case", "key", "mail_discord", "placeholder_rx", "run", "waiting_on"]
