"""Ask 14 (the player report form) on PostgreSQL: the five routes of
api/player_reports.py against a case schema, the migration, and account
deletion.

The rules as pure functions and the claims about the source are in
test_player_report_rules.py. This file runs the statements: who may report whom
for which game, what the second read under the identity locks decides, what a
log that cannot be stored costs on each side of the write transaction
(condition C2), what the retention bound serves and deletes (C3), what the
admin routes require, and what the games statement reads through (C5).

A case schema is built from the migrations' DDL, so no migration's INSERT has
run in it: the switch row is absent until a test writes it. That is the state
rule 2 calls OFF. run_env writes the row ON; the first claim takes it away.

Every time a test writes is computed from the database's own clock and handed
over as a timestamp. An interval of N days is calendar arithmetic in the
session's time zone, and a bound here is an instant.
"""
import asyncio
import glob
import gzip
import hashlib
import hmac
import io
import json
import os
import re
import sys
import time
import uuid
from datetime import timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
SQL_DIR = os.path.normpath(os.path.join(HERE, "..", "sql"))
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import asyncpg  # noqa: E402
import cf_asm  # noqa: E402
import cf_pg  # noqa: E402
import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from sqlalchemy import event  # noqa: E402

import database  # noqa: E402
import main  # noqa: E402
import player_report_rules as rules  # noqa: E402
import player_reports as routes  # noqa: E402

SECRET = "plr-test-match-secret"
ADMIN_SECRET = "plr-test-admin-secret"
SUBMIT = "/api/v1/player-reports"
GAMES = "/api/v1/player-reports/games"
ADMIN = "/api/v1/admin/player-reports"
HOUR, DAY, MINUTE = timedelta(hours=1), timedelta(days=1), timedelta(minutes=1)
NL = chr(10)
TICKET = "Session Ticket: " + "AB12" * 16          # the credential rule's own shape
LOG = NL.join(["[Info   :Competitive] line %05d" % i for i in range(400)] + [TICKET, "the last line"])
TABLES = {"1v1": "matches", "2v2": "team_matches", "1v2": "ovt_matches", "ffa": "ffa_matches"}
SEATS = {"1v1": 2, "2v2": 4, "1v2": 3, "ffa": 5}
OMIT = object()
WORD = re.compile("[A-Z_]+")
WRITE_WORDS = frozenset(("INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE", "COPY", "DROP", "ALTER", "CREATE"))


def fold(sql):
    return " ".join(str(sql).split())


def writes(ran):
    """The statements of a request that change something, in the order they ran."""
    return [s for s in ran if WRITE_WORDS & set(WORD.findall(s.upper()))]


def head(statement, words=3):
    return " ".join(statement.split()[:words])


def code(r):
    """(the status, the answer's error code or its detail text)."""
    try:
        detail = r.json().get("detail")
    except (ValueError, AttributeError):
        return r.status_code, None
    return r.status_code, detail.get("error") if isinstance(detail, dict) else detail


def sig(steam, action, target):
    return hmac.new(ADMIN_SECRET.encode(), main._admin_canonical(steam, action, str(target)).encode(),
                    hashlib.sha256).hexdigest()


class P:
    """A seeded account: its players row, its Steam id, its name."""

    def __init__(self, pid, steam, name):
        self.pid, self.steam, self.name = pid, steam, name


class Env:
    """One case: the schema, a session maker bound to it, a test app with the
    lane's router, and a record of every statement the case's engine sent to
    the database (`last` holds the statements of the latest request)."""

    def __init__(self, c, sm, monkeypatch):
        self.c, self.sm, self.conn, self.mp = c, sm, c.conn, monkeypatch
        app = FastAPI()
        app.include_router(routes.plr_router)

        async def _db():
            async with sm() as s:
                yield s
        app.dependency_overrides[database.get_db] = _db
        self.app = app
        self.ran, self.last = [], []
        bind = getattr(sm, "kw", {}).get("bind")
        assert bind is not None, "the case's session maker has no engine to observe"
        self._engine = bind.sync_engine
        env = self

        def seen(conn, cursor, statement, parameters, context, executemany):
            env.ran.append(fold(statement))
        self._seen = seen
        event.listen(self._engine, "before_cursor_execute", seen)
        monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
        monkeypatch.setattr(main, "ADMIN_HMAC_SECRET", ADMIN_SECRET)
        monkeypatch.setattr(main, "IS_REPLICA", False)
        monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)

    def close(self):
        event.remove(self._engine, "before_cursor_execute", self._seen)

    # -- requests ---------------------------------------------------------------

    async def call(self, method, path, token=None, body=None, params=None, raw=None, headers=None):
        h = dict(headers or {})
        if token is not None:
            h["X-Session-Token"] = token
        del self.ran[:]
        transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as cl:
            if raw is not None:
                r = await cl.request(method, path, content=raw, params=params, headers=h)
            else:
                r = await cl.request(method, path, json=body, params=params, headers=h)
        self.last = list(self.ran)
        return r

    @staticmethod
    def body(kind, game, reported, reason="cheating", details="", log_text=None, **extra):
        out = {"game_kind": kind, "game_id": str(game), "reported_steam_id": reported,
               "reason": reason, "details": details}
        if log_text is not None:
            out["log_text"] = log_text
        out.update(extra)
        return out

    async def submit(self, token, kind, game, reported, **kw):
        return await self.call("POST", SUBMIT, token, body=self.body(kind, game, reported, **kw))

    async def games(self, token):
        return await self.call("GET", GAMES, token)

    async def listing(self, adm, signature=None, **params):
        q = {"admin_steam_id": adm.steam}
        if signature is not OMIT:
            q["hmac_signature"] = signature or sig(adm.steam, rules.ACTION_LIST, rules.TARGET_LIST)
        q.update(params)
        return await self.call("GET", ADMIN, params=q)

    async def log(self, adm, rid, signature=None):
        q = {"admin_steam_id": adm.steam}
        if signature is not OMIT:
            q["hmac_signature"] = signature or sig(adm.steam, rules.ACTION_LOG, rid)
        return await self.call("GET", "%s/%s/log" % (ADMIN, rid), params=q)

    async def shut(self, adm, rid, verdict, note=None, signature=None):
        """The close route (close() is the case's own teardown)."""
        body = {"admin_steam_id": adm.steam, "verdict": verdict}
        if signature is not OMIT:
            body["hmac_signature"] = signature or sig(
                adm.steam, rules.ACTION_CLOSE, rules.close_target(str(rid), verdict))
        if note is not None:
            body["note"] = note
        return await self.call("POST", "%s/%s/close" % (ADMIN, rid), body=body)

    # -- what the tables hold ---------------------------------------------------

    async def count(self, table="player_reports"):
        assert table in ("player_reports", "player_report_logs"), table
        return await self.conn.fetchval("SELECT count(*) FROM " + table)

    async def fingerprint(self):
        """Every column of both tables, to compare around requests that must
        change nothing."""
        reports = await self.conn.fetch("SELECT r::text AS t FROM player_reports r ORDER BY r.id")
        logs = await self.conn.fetch(
            "SELECT report_id, md5(gz) AS h, raw_chars, stored_at FROM player_report_logs ORDER BY report_id")
        return [x["t"] for x in reports], [tuple(x) for x in logs]

    async def report_of(self, reporter, reported):
        return await self.conn.fetchval(
            "SELECT id FROM player_reports WHERE reporter_id = $1 AND reported_id = $2", reporter.pid, reported.pid)

    # -- seeding ----------------------------------------------------------------

    async def switch(self, value):
        """The switch row: its value, or None for no row at all."""
        if value is None:
            await self.conn.execute("DELETE FROM runtime_settings WHERE key = $1", rules.SWITCH_KEY)
        else:
            await self.conn.execute(
                "INSERT INTO runtime_settings (key, value) VALUES ($1, $2)"
                " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", rules.SWITCH_KEY, value)

    async def players(self, n, name="plr"):
        out = []
        for i in range(n):
            steam = "7656119" + ("%010d" % (uuid.uuid4().int % 10 ** 10))
            shown = "%s %02d" % (name, i)
            pid = await self.conn.fetchval(
                "INSERT INTO players (id, steam_id, display_name) VALUES ($3, $1, $2) RETURNING id",
                steam, shown, uuid.uuid4())
            out.append(P(pid, steam, shown))
        return out

    async def admin(self, with_player=True):
        if with_player:
            p = (await self.players(1, "adm"))[0]
        else:
            p = P(None, "7656119" + ("%010d" % (uuid.uuid4().int % 10 ** 10)), "")
        await self.conn.execute("INSERT INTO admin_users (steam_id, granted_at) VALUES ($1, now())", p.steam)
        return p

    async def session(self, steam, verified=True, lifetime=HOUR):
        """A session row for that account; returns the token the client holds."""
        token = "plr-" + uuid.uuid4().hex
        now = await self.conn.fetchval("SELECT now()")
        await self.conn.execute(
            "INSERT INTO steam_sessions (steam_id, token_hash, verified, issued_at, expires_at)"
            " VALUES ($1, $2, $3, $4, $5)",
            steam, hashlib.sha256(token.encode()).hexdigest(), verified, now, now + lifetime)
        return token

    async def delete_account(self, p):
        """Account deletion as its route runs it, for that account."""
        signature = hmac.new(SECRET.encode(), ("delete:%s" % p.steam).encode(), hashlib.sha256).hexdigest()
        async with self.sm() as db:
            await main.delete_player_data(p.steam, cf_asm.FakeRequest(), sig=signature, _slot=None, db=db)


def run_env(monkeypatch, body, prefix="plr"):
    cf_pg.require_live_pg()

    async def inside():
        async with cf_pg.case(prefix) as (c, sm):
            env = Env(c, sm, monkeypatch)
            try:
                await env.switch("1")
                await body(env)
            finally:
                env.close()
    asyncio.run(inside())


# -- seeding games and reports -----------------------------------------------------

async def seed_game(conn, kind, pids, ago=HOUR, invalid=False, room=None, absent=()):
    """A finished game of `kind` with those players in its seats, ended `ago`
    before the database's clock. Returns its id."""
    gid = uuid.uuid4()
    now = await conn.fetchval("SELECT now()")
    ended, void = now - ago, (now if invalid else None)
    if kind == "1v1":
        await conn.execute(
            "INSERT INTO matches (id, player1_id, player2_id, p1_rounds_won, p2_rounds_won, p1_points_total,"
            " p2_points_total, is_ranked, ended_at, created_at, photon_room_id, invalidated_at)"
            " VALUES ($1, $2, $3, 3, 1, 0, 0, FALSE, $4, $4, $5, $6)", gid, pids[0], pids[1], ended, room, void)
    elif kind == "2v2":
        await conn.execute(
            "INSERT INTO team_matches (id, t1a_id, t1b_id, t2a_id, t2b_id, t1_rounds_won, t2_rounds_won,"
            " t1_points_total, t2_points_total, winner_team, is_ranked, ended_at, created_at, invalidated_at)"
            " VALUES ($1, $2, $3, $4, $5, 3, 1, 0, 0, 1, TRUE, $6, $6, $7)", gid, *pids[:4], ended, void)
    elif kind == "1v2":
        await conn.execute(
            "INSERT INTO ovt_matches (id, solo_id, duo_a_id, duo_b_id, solo_rounds_won, duo_rounds_won,"
            " winner_side, ended_at, invalidated_at) VALUES ($1, $2, $3, $4, 3, 1, 1, $5, $6)",
            gid, *pids[:3], ended, void)
    else:
        await conn.execute(
            "INSERT INTO ffa_matches (id, photon_room_id, player_count, ended_at, invalidated_at)"
            " VALUES ($1, $2, $3, $4, $5)", gid, room or "ffa_" + gid.hex[:24], len(pids), ended, void)
        for i, pid in enumerate(pids):
            await conn.execute(
                "INSERT INTO ffa_match_players (match_id, player_id, placement, absent) VALUES ($1, $2, $3, $4)",
                gid, pid, i + 1, i in absent)
    return gid


async def seed_report(conn, reporter, reported, kind="1v1", game_id=None, filed=timedelta(0), closed=None,
                      verdict="dismissed", closed_by=None, now=None):
    """A report row written directly: filed `filed` before `now` (the
    database's clock when not given) and, when `closed` is given, closed that
    long before it. Returns its id."""
    if now is None:
        now = await conn.fetchval("SELECT now()")
    rid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO player_reports (id, created_at, reporter_id, reported_id, game_kind, game_id, game_ended_at,"
        " reason, status, closed_at, closed_by) VALUES ($1, $2, $3, $4, $5, $6, $2, 'cheating', $7, $8, $9)",
        rid, now - filed, reporter, reported, kind, game_id or uuid.uuid4(),
        "open" if closed is None else verdict, None if closed is None else now - closed, closed_by)
    return rid


async def seed_log(conn, rid, said="one log line"):
    await conn.execute("INSERT INTO player_report_logs (report_id, gz, raw_chars) VALUES ($1, $2, $3)",
                       rid, gzip.compress(said.encode("utf-8")), len(said))


async def lock_waiters(env, blocker_pid, want, bound=200):
    """The backends queued, directly or through another, behind the blocker
    (test_match_hold_pg's observer)."""
    pids = ()
    for _ in range(bound):
        pids = tuple(await env.conn.fetchval(
            "WITH RECURSIVE w(pid) AS ("
            " SELECT pid FROM pg_stat_activity WHERE datname = current_database()"
            "   AND $1 = ANY(pg_blocking_pids(pid))"
            " UNION SELECT a.pid FROM pg_stat_activity a JOIN w"
            "   ON w.pid = ANY(pg_blocking_pids(a.pid))"
            " WHERE a.datname = current_database())"
            " SELECT COALESCE(array_agg(pid ORDER BY pid), ARRAY[]::integer[]) FROM w",
            blocker_pid))
        if len(pids) >= want:
            return pids
        await asyncio.sleep(0.02)
    return pids


async def held_identity(env, steam):
    """A second connection holding that account's identity lock (the key
    main._identity_lock_many takes) in an open transaction. Returns
    (the connection, its transaction): roll the transaction back to release."""
    blocker = await cf_pg.harness.connect_bound(env.c.dsn, env.c.schema)
    held = blocker.transaction()
    await held.start()
    await blocker.execute("SELECT pg_advisory_xact_lock(hashtext($1::text))", steam)
    return blocker, held


# -- rules 1 to 3 ------------------------------------------------------------------

def test_r123_a_report_needs_a_verified_session_then_the_switch_then_a_body_within_the_ceiling(monkeypatch):
    async def body(env):
        a, b = await env.players(2)
        g = await seed_game(env.conn, "1v1", [a.pid, b.pid])
        tokens = {
            "no token": None,
            "a token no session carries": "plr-" + uuid.uuid4().hex,
            "an unverified session": await env.session(a.steam, verified=False),
            "an expired session": await env.session(a.steam, lifetime=-HOUR),
        }
        # Rule 1 whatever the switch says, and the switch is not read for it.
        for value in (None, "0", "1"):
            await env.switch(value)
            for name, token in sorted(tokens.items()):
                r = await env.submit(token, "1v1", g, b.steam)
                assert code(r) == (401, "session_required"), (value, name, r.text)
                assert not [s for s in env.last if "runtime_settings" in s], (value, name, env.last)
                r = await env.games(token)
                assert code(r) == (401, "session_required"), (value, name, r.text)
                assert not [s for s in env.last if "runtime_settings" in s], (value, name, env.last)
        # Rule 2: a built schema holds no row, and only the exact value '1' is ON.
        token = await env.session(a.steam)
        for value in (None, "0", "", "true", "01", " 1", "1 "):
            await env.switch(value)
            assert code(await env.submit(token, "1v1", g, b.steam)) == (503, "player_reports_off"), value
            assert code(await env.games(token)) == (503, "player_reports_off"), value
        assert await env.count() == 0
        await env.switch("1")
        # Rule 3, declared: over the ceiling, and a length that is no count.
        raw = json.dumps(env.body("1v1", g, b.steam)).encode()
        r = await env.call("POST", SUBMIT, token, raw=raw, headers={"Content-Length": str(rules.BODY_MAX + 1)})
        assert code(r) == (413, "body_too_large"), r.text
        for declared in ("abc", "-1", "1.5"):
            r = await env.call("POST", SUBMIT, token, raw=raw, headers={"Content-Length": declared})
            assert code(r) == (400, "bad_length"), (declared, r.text)
        # Rule 3, read: no declared length, and the body passes the ceiling on its way in.
        ceiling = rules.BODY_MAX
        monkeypatch.setattr(rules, "BODY_MAX", 100)

        async def chunks():
            for _ in range(4):
                yield b" " * 40
        r = await env.call("POST", SUBMIT, token, raw=chunks())
        monkeypatch.setattr(rules, "BODY_MAX", ceiling)
        assert code(r) == (413, "body_too_large"), r.text
        assert await env.count() == 0
        # With all three passed the report is taken, and the answer names no report.
        r = await env.submit(token, "1v1", g, b.steam)
        assert r.status_code == 200 and r.json() == {"ok": True, "log_stored": False}, r.text
        assert await env.count() == 1
    run_env(monkeypatch, body, prefix="plrgate")


def test_r4_the_reporter_is_the_sessions_account_whatever_the_body_says(monkeypatch):
    async def body(env):
        me, ann, bo = await env.players(3)
        token = await env.session(me.steam)
        g = await seed_game(env.conn, "1v2", [ann.pid, me.pid, bo.pid])
        for raw in (b"", b"not json", b"[]", b"null", b"7"):
            r = await env.call("POST", SUBMIT, token, raw=raw)
            assert code(r) == (422, "bad_body"), (raw, r.text)
        r = await env.submit(token, "1v2", g, ann.steam, reporter_steam_id=bo.steam, reporter_id=str(bo.pid),
                             steam_id=bo.steam, status="actioned", id=str(uuid.uuid4()))
        assert r.status_code == 200 and sorted(r.json()) == ["log_stored", "ok"], r.text
        row = await env.conn.fetchrow("SELECT reporter_id, reported_id, status FROM player_reports")
        assert (row["reporter_id"], row["reported_id"], row["status"]) == (me.pid, ann.pid, "open")
        # Another account's session reports as that account, never as this one.
        other = await env.session(bo.steam)
        r = await env.submit(other, "1v2", g, ann.steam)
        assert r.status_code == 200, r.text
        assert await env.report_of(bo, ann) is not None and await env.count() == 2
    run_env(monkeypatch, body, prefix="plrwho")


# -- rules 5 to 7: the caller's own listed games --------------------------------------

def test_r6_r7_every_kind_lists_the_callers_game_from_every_seat_and_takes_a_report_on_its_players(monkeypatch):
    async def body(env):
        for kind, n in sorted(SEATS.items()):
            for seat in range(n):
                ps = await env.players(n, "%s seat %d" % (kind, seat))
                g = await seed_game(env.conn, kind, [p.pid for p in ps], ago=(seat + 1) * HOUR)
                me, others = ps[seat], [p for p in ps if p is not ps[seat]]
                token = await env.session(me.steam)
                r = await env.games(token)
                assert r.status_code == 200, (kind, seat, r.text)
                listed = r.json()
                assert sorted(listed) == ["games", "remaining"] and listed["remaining"] == rules.REPORTS_PER_DAY
                assert [(x["kind"], x["id"]) for x in listed["games"]] == [(kind, str(g))], (kind, seat, listed)
                game = listed["games"][0]
                assert sorted(game) == ["ended_at", "id", "kind", "others"], game
                assert [(o["steam_id"], o["name"], o["reported"]) for o in game["others"]] == [
                    (p.steam, p.name, False) for p in others], (kind, seat, game)
                ended = await env.conn.fetchval("SELECT ended_at FROM %s WHERE id = $1" % TABLES[kind], g)
                assert game["ended_at"] == rules.utc_stamp(ended)
                target = others[-1]
                r = await env.submit(token, kind, g, target.steam, reason="griefing", details="left at 2-0")
                assert r.status_code == 200 and r.json() == {"ok": True, "log_stored": False}, (kind, seat, r.text)
                row = await env.conn.fetchrow("SELECT * FROM player_reports WHERE reporter_id = $1", me.pid)
                assert (row["reported_id"], row["game_kind"], row["game_id"], row["game_ended_at"]) == (
                    target.pid, kind, g, ended), (kind, seat, dict(row))
                assert (row["reason"], row["details"], row["status"], row["closed_at"], row["closed_by"],
                        row["close_note"]) == ("griefing", "left at 2-0", "open", None, None, ""), dict(row)
        assert await env.count() == sum(SEATS.values())
    run_env(monkeypatch, body, prefix="plrseats")


def test_r5_r6_r7_what_the_form_is_not_offered_the_submit_refuses(monkeypatch):
    async def body(env):
        me, ann, bo, cy, dee = await env.players(5)
        token = await env.session(me.steam)

        async def offered():
            r = await env.games(token)
            assert r.status_code == 200, r.text
            return [(x["kind"], x["id"], [o["steam_id"] for o in x["others"]]) for x in r.json()["games"]]

        async def refused(kind, game, steam, want):
            before = await env.count()
            r = await env.submit(token, kind, game, steam)
            assert code(r) == want, (kind, want, r.text)
            assert await env.count() == before

        # The window: a minute past it is not listed, a minute inside it is.
        window = rules.GAME_WINDOW_DAYS * DAY
        old = await seed_game(env.conn, "1v1", [me.pid, ann.pid], ago=window + MINUTE)
        edge = await seed_game(env.conn, "1v1", [ann.pid, me.pid], ago=window - MINUTE)
        assert await offered() == [("1v1", str(edge), [ann.steam])]
        await refused("1v1", old, ann.steam, (404, "game_not_found"))
        # An invalidated game of each kind.
        for kind, n in sorted(SEATS.items()):
            void = await seed_game(env.conn, kind, [me.pid, ann.pid, bo.pid, cy.pid, dee.pid][:n], invalid=True)
            await refused(kind, void, ann.steam, (404, "game_not_found"))
        # A row of `matches` that carries a team, 1v2 or FFA room is no 1v1 game.
        for prefix in ("team_", "ovt_", "ffa_"):
            g = await seed_game(env.conn, "1v1", [me.pid, bo.pid], room=prefix + uuid.uuid4().hex[:12])
            await refused("1v1", g, bo.steam, (404, "game_not_found"))
        plain = await seed_game(env.conn, "1v1", [me.pid, bo.pid], room="room_" + uuid.uuid4().hex[:12], ago=2 * HOUR)
        # The same id under another kind; a game the caller took no part in.
        await refused("2v2", plain, bo.steam, (404, "game_not_found"))
        theirs = await seed_game(env.conn, "2v2", [ann.pid, bo.pid, cy.pid, dee.pid])
        await refused("2v2", theirs, ann.steam, (404, "game_not_found"))
        # Rule 7: an account that was not in that game, the caller's own, nobody's.
        for steam in (cy.steam, me.steam, "76561190000000000"):
            await refused("1v1", plain, steam, (422, "player_not_in_game"))
        # FFA: a roster ghost is not offered, and a game the caller was a ghost in is not listed.
        ffa = await seed_game(env.conn, "ffa", [me.pid, ann.pid, bo.pid, cy.pid], absent=(2,), ago=3 * HOUR)
        ghost = await seed_game(env.conn, "ffa", [me.pid, ann.pid, bo.pid], absent=(0,), ago=4 * HOUR)
        await refused("ffa", ffa, bo.steam, (422, "player_not_in_game"))
        await refused("ffa", ghost, ann.steam, (404, "game_not_found"))
        assert await offered() == [("1v1", str(plain), [bo.steam]), ("ffa", str(ffa), [ann.steam, cy.steam]),
                                   ("1v1", str(edge), [ann.steam])]
        # A deleted account is not offered, and a game with nobody left to report is not listed.
        await env.conn.execute("UPDATE players SET deleted_at = now() WHERE id = ANY($1::uuid[])", [bo.pid, cy.pid])
        assert await offered() == [("ffa", str(ffa), [ann.steam]), ("1v1", str(edge), [ann.steam])]
        await refused("1v1", plain, bo.steam, (404, "game_not_found"))
        await refused("ffa", ffa, cy.steam, (422, "player_not_in_game"))
        # Rule 5 and ruling (e): a session whose account has no players row lists nothing and reports nothing.
        nobody = await env.session("7656119" + "9" * 10)
        r = await env.games(nobody)
        assert r.status_code == 200 and r.json() == {"games": [], "remaining": rules.REPORTS_PER_DAY}, r.text
        assert code(await env.submit(nobody, "1v1", edge, ann.steam)) == (403, "no_player")
        await env.conn.execute("UPDATE players SET deleted_at = now() WHERE id = $1", me.pid)
        r = await env.games(token)
        assert r.status_code == 200 and r.json()["games"] == [], r.text
        await refused("1v1", edge, ann.steam, (403, "no_player"))
    run_env(monkeypatch, body, prefix="plrlist")


# -- rules 8 and 9 -------------------------------------------------------------------

def test_r8_r9_one_report_per_game_and_player_and_five_in_24_hours(monkeypatch):
    async def body(env):
        me, *others = await env.players(8)
        token = await env.session(me.steam)
        games = [await seed_game(env.conn, "1v1", [me.pid, o.pid], ago=(i + 1) * HOUR)
                 for i, o in enumerate(others)]

        async def form():
            listed = (await env.games(token)).json()
            return listed["remaining"], [o["reported"] for x in listed["games"] for o in x["others"]]

        assert await form() == (5, [False] * 7)
        r = await env.submit(token, "1v1", games[0], others[0].steam)
        assert r.status_code == 200, r.text
        assert await form() == (4, [True] + [False] * 6)
        # Rule 8: the same game and player again, whatever the reason or the text.
        for reason, details in (("cheating", ""), ("other", "again")):
            r = await env.submit(token, "1v1", games[0], others[0].steam, reason=reason, details=details)
            assert code(r) == (409, "already_reported"), r.text
        assert await env.count() == 1
        # Rule 9 counts the reporter's rows of the last 24 hours: a minute older is not counted.
        await seed_report(env.conn, me.pid, others[6].pid, filed=DAY + MINUTE)
        assert (await form())[0] == 4
        for i in (1, 2, 3):
            await seed_report(env.conn, me.pid, others[i].pid, game_id=games[i], filed=DAY - MINUTE)
        assert await form() == (1, [True] * 4 + [False] * 3)
        r = await env.submit(token, "1v1", games[4], others[4].steam)          # the fifth
        assert r.status_code == 200, r.text
        assert (await form())[0] == 0
        r = await env.submit(token, "1v1", games[5], others[5].steam)          # the sixth
        assert code(r) == (429, "report_limit"), r.text
        # Rule 8 is answered before rule 9.
        r = await env.submit(token, "1v1", games[4], others[4].steam)
        assert code(r) == (409, "already_reported"), r.text
        assert await env.count() == 6
        # Another reporter's rows do not count for this one.
        token2 = await env.session(others[5].steam)
        r = await env.submit(token2, "1v1", games[5], me.steam)
        assert r.status_code == 200, r.text
    run_env(monkeypatch, body, prefix="plrlimit")


# -- ruling (c): the second read, under the identity locks, decides ----------------------

CHANGES = {
    "nothing changes": (200, None, 1),
    "the game is invalidated": (404, "game_not_found", 0),
    "the reported account is deleted": (422, "player_not_in_game", 0),
    "the session is gone": (401, "session_required", 0),
    "the same report is stored": (409, "already_reported", 1),
    "the day's limit is reached": (429, "report_limit", 0),
}


@pytest.mark.parametrize("change", sorted(CHANGES))
def test_ruling_c_a_row_changed_between_the_two_reads_turns_the_answer(monkeypatch, change):
    status, word, rows = CHANGES[change]

    async def body(env):
        me, ann, bo, cy = await env.players(4)
        fill = await env.players(rules.REPORTS_PER_DAY, "fill")
        token = await env.session(me.steam)
        g = await seed_game(env.conn, "2v2", [ann.pid, bo.pid, me.pid, cy.pid])
        blocker, held = await held_identity(env, me.steam)
        try:
            task = asyncio.ensure_future(env.submit(token, "2v2", g, ann.steam))
            waiting = await lock_waiters(env, blocker.get_server_pid(), 1)
            # Only a report the first read accepted asks for the locks: it is
            # queued behind the reporter's, and nothing is written yet.
            assert len(waiting) == 1, "the submit did not reach the identity lock: %r" % (waiting,)
            assert not task.done() and await env.count() == 0
            if change == "the game is invalidated":
                await env.conn.execute("UPDATE team_matches SET invalidated_at = now() WHERE id = $1", g)
            elif change == "the reported account is deleted":
                await env.conn.execute("UPDATE players SET deleted_at = now() WHERE id = $1", ann.pid)
            elif change == "the session is gone":
                await env.conn.execute("DELETE FROM steam_sessions WHERE steam_id = $1", me.steam)
            elif change == "the same report is stored":
                await seed_report(env.conn, me.pid, ann.pid, kind="2v2", game_id=g)
            elif change == "the day's limit is reached":
                for p in fill:
                    await seed_report(env.conn, me.pid, p.pid)
        finally:
            await held.rollback()
            await blocker.close()
        r = await task
        assert code(r) == (status, word), (change, r.text)
        stored = await env.conn.fetchval(
            "SELECT count(*) FROM player_reports WHERE reporter_id = $1 AND game_id = $2", me.pid, g)
        assert stored == rows, (change, stored)
    run_env(monkeypatch, body, prefix="plrtwice")


def test_a_submit_that_cannot_take_both_identity_locks_answers_503_and_writes_nothing(monkeypatch):
    async def body(env):
        me, ann = await env.players(2)
        token = await env.session(me.steam)
        g = await seed_game(env.conn, "1v1", [me.pid, ann.pid])
        monkeypatch.setattr(main, "FORMATION_LOCK_TIMEOUT_MS", 300)
        # The REPORTED account's lock is held: the submit takes that one too.
        blocker, held = await held_identity(env, ann.steam)
        try:
            r = await env.submit(token, "1v1", g, ann.steam)
        finally:
            await held.rollback()
            await blocker.close()
        assert r.status_code == 503, r.text
        assert await env.count() == 0
        r = await env.submit(token, "1v1", g, ann.steam)
        assert r.status_code == 200 and await env.count() == 1, r.text
    run_env(monkeypatch, body, prefix="plrlock")


# -- condition C2: a log that cannot be stored, on each side of the write transaction ------

def test_c2_a_log_that_cannot_be_prepared_before_the_transaction_leaves_the_report_alone(monkeypatch):
    async def body(env):
        me, *others = await env.players(5)
        token = await env.session(me.steam)
        games = [await seed_game(env.conn, "1v1", [me.pid, o.pid], ago=(i + 1) * HOUR)
                 for i, o in enumerate(others)]

        async def report(i):
            r = await env.submit(token, "1v1", games[i], others[i].steam, log_text=LOG)
            assert r.status_code == 200, (i, r.text)
            rid = await env.report_of(me, others[i])
            assert rid is not None, i
            log = await env.conn.fetchrow("SELECT gz, raw_chars FROM player_report_logs WHERE report_id = $1", rid)
            return r.json(), log

        # A log that can be stored is: the credential rule's text, gzipped, with its length.
        real = rules.prepare_log
        expected = gzip.decompress(real(LOG)[0]).decode("utf-8")
        answer, log = await report(0)
        assert answer == {"ok": True, "log_stored": True}
        stored = gzip.decompress(log["gz"]).decode("utf-8")
        assert stored == expected and log["raw_chars"] == len(expected)
        assert "AB12" * 16 not in stored and stored.endswith("the last line") and "line 00000" in stored
        # Over its stored cap once compressed.
        cap = rules.LOG_GZ_MAX
        monkeypatch.setattr(rules, "LOG_GZ_MAX", 16)
        assert await report(1) == ({"ok": True, "log_stored": False}, None)
        monkeypatch.setattr(rules, "LOG_GZ_MAX", cap)

        # The preparation raises.
        def broken(log_text):
            raise RuntimeError("no codec")
        monkeypatch.setattr(rules, "prepare_log", broken)
        assert await report(2) == ({"ok": True, "log_stored": False}, None)

        # The pool does not finish within its ceiling.
        def slow(log_text):
            time.sleep(0.6)
            return real(log_text)
        monkeypatch.setattr(rules, "prepare_log", slow)
        monkeypatch.setattr(main._auto_logs, "AUTO_LOG_CPU_WAIT_S", 0.05)
        assert await report(3) == ({"ok": True, "log_stored": False}, None)
        assert (await env.count(), await env.count("player_report_logs")) == (4, 1)
    run_env(monkeypatch, body, prefix="plrlog")


def test_c2_a_database_error_inside_the_write_transaction_fails_the_whole_request(monkeypatch):
    async def body(env):
        me, ann = await env.players(2)
        token = await env.session(me.steam)
        g = await seed_game(env.conn, "1v1", [me.pid, ann.pid])
        real = rules.prepare_log
        # A log row the table's CHECK refuses. By then the report's own INSERT
        # has run in the same transaction.
        monkeypatch.setattr(rules, "prepare_log", lambda log_text: (gzip.compress(b"x"), -1))
        r = await env.submit(token, "1v1", g, ann.steam, log_text=LOG)
        assert r.status_code == 500, r.text
        assert "log_stored" not in r.text
        ran = [head(s) for s in env.last]
        assert [s for s in ran if s.startswith("INSERT INTO player_report")] == [
            "INSERT INTO player_reports", "INSERT INTO player_report_logs"], ran
        # No SAVEPOINT stands between the report's INSERT and the failure (the
        # session reads before it use one, so the census does see them).
        at = ran.index("INSERT INTO player_reports")
        assert [s for s in ran[:at] if s.startswith("SAVEPOINT")], ran
        assert not [s for s in ran[at:] if s.startswith(("SAVEPOINT", "RELEASE"))], ran[at:]
        assert fold(routes.RETENTION_SQL) not in env.last
        # Nothing of the request is left, and nothing was tried again.
        assert (await env.count(), await env.count("player_report_logs")) == (0, 0)
        monkeypatch.setattr(rules, "prepare_log", real)
        r = await env.submit(token, "1v1", g, ann.steam, log_text=LOG)
        assert r.status_code == 200 and r.json() == {"ok": True, "log_stored": True}, r.text
        assert (await env.count(), await env.count("player_report_logs")) == (1, 1)
    run_env(monkeypatch, body, prefix="plrfail")


# -- condition C3: one retention bound for both readers and for the DELETE ------------------

OPEN, CLOSED, TICK = rules.OPEN_LOG_DAYS * DAY, rules.CLOSED_LOG_DAYS * DAY, timedelta(microseconds=1)
# name: (filed before now, closed before now or None, whether its log is still served)
BOUNDS = {
    "open, filed now": (timedelta(0), None, True),
    "open, one tick inside its 90 days": (OPEN - TICK, None, True),
    "open, exactly at its 90 days": (OPEN, None, False),
    "open, one tick past": (OPEN + TICK, None, False),
    "closed in time, one tick inside its 30 days": (40 * DAY, CLOSED - TICK, True),
    "closed in time, exactly at its 30 days": (40 * DAY, CLOSED, False),
    "closed in time, one tick past": (40 * DAY, CLOSED + TICK, False),
    "closed one tick before the open bound, filed 95 days ago": (OPEN + 5 * DAY, 5 * DAY + TICK, True),
    "closed exactly at the open bound": (OPEN + 5 * DAY, 5 * DAY, False),
    "closed after the open bound": (OPEN + 5 * DAY, DAY, False),
}


@pytest.mark.parametrize("zone", ["UTC", "America/Los_Angeles", "Europe/London", "Australia/Lord_Howe"])
def test_c3_the_delete_keeps_exactly_the_logs_the_predicate_serves_at_both_edges(monkeypatch, zone):
    """One transaction, so now() is one instant for the rows and the DELETE.
    The session's time zone must not move a bound: three of the four zones
    change their clocks, one of them by half an hour."""
    async def body(env):
        a, b = await env.players(2)
        tx = env.conn.transaction()
        await tx.start()
        try:
            await env.conn.execute("SELECT set_config('TimeZone', $1, true)", zone)
            now = await env.conn.fetchval("SELECT now()")
            ids = {}
            for name, (filed, closed, _) in sorted(BOUNDS.items()):
                ids[name] = await seed_report(env.conn, a.pid, b.pid, filed=filed, closed=closed, now=now)
                await seed_log(env.conn, ids[name], name)
            await env.conn.execute(routes.RETENTION_SQL)
            rows = await env.conn.fetch(
                "SELECT r.id, r.created_at, r.closed_at, now() AS now, (l.report_id IS NOT NULL) AS kept"
                "  FROM player_reports r LEFT JOIN player_report_logs l ON l.report_id = r.id")
        finally:
            await tx.rollback()
        got = {r["id"]: r for r in rows}
        assert len(got) == len(BOUNDS)
        for name, (filed, closed, served) in sorted(BOUNDS.items()):
            r = got[ids[name]]
            assert r["now"] == now and r["created_at"] == now - filed, (zone, name)
            assert rules.log_readable(r["created_at"], r["closed_at"], r["now"]) is served, (zone, name)
            assert r["kept"] is served, (zone, name, "the DELETE and the predicate disagree")
    run_env(monkeypatch, body, prefix="plrbound")


def test_c3_a_log_past_its_day_that_is_still_stored_is_refused_and_listed_as_no_log(monkeypatch):
    async def body(env):
        adm = await env.admin()
        a, b, c, d = await env.players(4)
        stale_open = await seed_report(env.conn, a.pid, b.pid, filed=OPEN + HOUR)
        stale_closed = await seed_report(env.conn, a.pid, c.pid, filed=50 * DAY, closed=CLOSED + HOUR)
        fresh = await seed_report(env.conn, a.pid, d.pid, filed=OPEN - HOUR)
        for rid, said in ((stale_open, "an old open log"), (stale_closed, "an old closed log"), (fresh, "a log in time")):
            await seed_log(env.conn, rid, said)
        before = await env.fingerprint()
        r = await env.listing(adm)
        assert r.status_code == 200, r.text
        assert {x["id"]: x["has_log"] for x in r.json()["reports"]} == {
            str(stale_open): False, str(stale_closed): False, str(fresh): True}
        for rid in (stale_open, stale_closed):
            assert code(await env.log(adm, rid)) == (404, "no_log"), rid
        r = await env.log(adm, fresh)
        assert r.status_code == 200 and r.text == "a log in time", r.text
        # All three rows are still stored: no GET removed one.
        assert await env.fingerprint() == before and await env.count("player_report_logs") == 3
        # The next POST transaction removes what no reader serves. This one
        # closes the third report an hour before its own open bound, so its log stays.
        r = await env.shut(adm, fresh, "dismissed")
        assert r.status_code == 200, r.text
        left = await env.conn.fetch("SELECT report_id FROM player_report_logs")
        assert [x["report_id"] for x in left] == [fresh]
        r = await env.log(adm, fresh)
        assert r.status_code == 200 and r.text == "a log in time", r.text
    run_env(monkeypatch, body, prefix="plrstale")


def test_c3_the_retention_delete_runs_in_the_two_post_transactions_and_no_get_writes(monkeypatch):
    """The census: every statement the database was sent, request by request."""
    async def body(env):
        adm = await env.admin()
        me, ann, bo = await env.players(3)
        token = await env.session(me.steam)
        g = await seed_game(env.conn, "1v2", [me.pid, ann.pid, bo.pid])
        retention = fold(routes.RETENTION_SQL)
        assert head(retention) == "DELETE FROM player_report_logs"
        # The submit: the report, its log, the retention DELETE, in that order and once each.
        r = await env.submit(token, "1v2", g, ann.steam, log_text=LOG)
        assert r.status_code == 200 and r.json()["log_stored"] is True, r.text
        done = writes(env.last)
        assert [head(s) for s in done] == ["INSERT INTO player_reports", "INSERT INTO player_report_logs",
                                           "DELETE FROM player_report_logs"], done
        assert done[-1] == retention and env.last.count(retention) == 1
        rid = await env.report_of(me, ann)
        # A submit without a log still runs it.
        r = await env.submit(token, "1v2", g, bo.steam)
        assert r.status_code == 200, r.text
        done = writes(env.last)
        assert [head(s) for s in done] == ["INSERT INTO player_reports", "DELETE FROM player_report_logs"], done
        # The close: the UPDATE, then the retention DELETE.
        r = await env.shut(adm, rid, "actioned", note="seen")
        assert r.status_code == 200, r.text
        done = writes(env.last)
        assert [head(s, 2) for s in done] == ["UPDATE player_reports", "DELETE FROM"], done
        assert done[-1] == retention and env.last.count(retention) == 1
        # Every GET, answered or refused: no statement that writes, and both tables as they were.
        before = await env.fingerprint()
        gets = [
            ("the games", lambda: env.games(token), 200),
            ("the games without a session", lambda: env.games(None), 401),
            ("the list", lambda: env.listing(adm), 200),
            ("the list by status", lambda: env.listing(adm, status="actioned"), 200),
            ("the list for a player", lambda: env.listing(me), 403),
            ("a log", lambda: env.log(adm, rid), 200),
            ("a log of no report", lambda: env.log(adm, uuid.uuid4()), 404),
            ("a log for a player", lambda: env.log(me, rid), 403),
        ]
        for name, get, want in gets:
            r = await get()
            assert r.status_code == want, (name, r.text)
            assert want != 200 or env.last, (name, "the census saw no statement")
            assert writes(env.last) == [], (name, writes(env.last))
        assert await env.fingerprint() == before
        # A refused POST changes nothing and never reaches the retention DELETE.
        # A close of a closed report sends its UPDATE, which finds no open row.
        posts = [
            ("a submit again", lambda: env.submit(token, "1v2", g, ann.steam), 409, []),
            ("a submit without a session", lambda: env.submit(None, "1v2", g, ann.steam), 401, []),
            ("a close again", lambda: env.shut(adm, rid, "dismissed"), 409, ["UPDATE player_reports"]),
            ("a close by a player", lambda: env.shut(me, rid, "dismissed"), 403, []),
        ]
        for name, post, want, sent in posts:
            r = await post()
            assert r.status_code == want, (name, r.text)
            assert [head(x, 2) for x in writes(env.last)] == sent, (name, writes(env.last))
            assert retention not in env.last, name
        assert await env.fingerprint() == before
    run_env(monkeypatch, body, prefix="plrcensus")


# -- the admin routes ----------------------------------------------------------------

def test_each_admin_route_requires_an_admin_account_and_a_signature_over_its_own_action(monkeypatch):
    async def body(env):
        adm = await env.admin()
        me, ann = await env.players(2)
        rid = await seed_report(env.conn, me.pid, ann.pid)
        await seed_log(env.conn, rid)
        for_list = sig(adm.steam, rules.ACTION_LIST, rules.TARGET_LIST)
        for_log = sig(adm.steam, rules.ACTION_LOG, rid)
        to_dismiss = sig(adm.steam, rules.ACTION_CLOSE, rules.close_target(str(rid), "dismissed"))
        elsewhere = uuid.uuid4()
        refused = [
            ("list: a player's own signature", lambda: env.listing(me)),
            ("list: no signature", lambda: env.listing(adm, signature=OMIT)),
            ("list: the log's signature", lambda: env.listing(adm, signature=for_log)),
            ("list: the close's signature", lambda: env.listing(adm, signature=to_dismiss)),
            ("log: a player's own signature", lambda: env.log(me, rid)),
            ("log: no signature", lambda: env.log(adm, rid, signature=OMIT)),
            ("log: the list's signature", lambda: env.log(adm, rid, signature=for_list)),
            ("log: signed for another report", lambda: env.log(
                adm, rid, signature=sig(adm.steam, rules.ACTION_LOG, elsewhere))),
            ("close: a player's own signature", lambda: env.shut(me, rid, "dismissed")),
            ("close: no signature", lambda: env.shut(adm, rid, "dismissed", signature=OMIT)),
            ("close: the list's signature", lambda: env.shut(adm, rid, "dismissed", signature=for_list)),
            ("close: signed for the other verdict", lambda: env.shut(adm, rid, "actioned", signature=to_dismiss)),
            ("close: signed for another report", lambda: env.shut(adm, rid, "dismissed", signature=sig(
                adm.steam, rules.ACTION_CLOSE, rules.close_target(str(elsewhere), "dismissed")))),
        ]
        before = await env.fingerprint()
        for name, call in refused:
            r = await call()
            assert r.status_code == 403, (name, r.text)
            assert "reports" not in r.text and "one log line" not in r.text, (name, r.text)
        # With no admin secret configured every signature is refused.
        monkeypatch.setattr(main, "ADMIN_HMAC_SECRET", "")
        for name, call in (("list", lambda: env.listing(adm)), ("log", lambda: env.log(adm, rid)),
                           ("close", lambda: env.shut(adm, rid, "dismissed"))):
            assert (await call()).status_code == 403, name
        monkeypatch.setattr(main, "ADMIN_HMAC_SECRET", ADMIN_SECRET)
        assert await env.fingerprint() == before
        # The same three, signed for what they are.
        assert (await env.listing(adm)).status_code == 200
        assert (await env.log(adm, rid)).status_code == 200
        assert (await env.shut(adm, rid, "dismissed")).status_code == 200
    run_env(monkeypatch, body, prefix="plradmin")


def test_the_admin_list_puts_open_reports_first_and_counts_the_reporters_of_30_days(monkeypatch):
    async def body(env):
        adm = await env.admin()
        a, b, c, d, e = await env.players(5)
        g = uuid.uuid4()
        r1 = await seed_report(env.conn, a.pid, d.pid, kind="2v2", game_id=g, filed=3 * HOUR)
        r2 = await seed_report(env.conn, b.pid, d.pid, filed=2 * HOUR, closed=HOUR, verdict="actioned",
                               closed_by=adm.pid)
        r3 = await seed_report(env.conn, c.pid, d.pid, filed=HOUR)
        r4 = await seed_report(env.conn, a.pid, b.pid, filed=rules.REPORTED_COUNT_DAYS * DAY + HOUR)
        await seed_report(env.conn, c.pid, d.pid, filed=2 * DAY)                # the same reporter again
        r6 = await seed_report(env.conn, e.pid, d.pid, filed=rules.REPORTED_COUNT_DAYS * DAY + HOUR)
        await seed_log(env.conn, r1)

        async def ids(**params):
            r = await env.listing(adm, **params)
            assert r.status_code == 200, r.text
            j = r.json()
            assert sorted(j) == ["open_total", "reports", "total"] and (j["open_total"], j["total"]) == (5, 6)
            return [x["id"] for x in j["reports"]], j["reports"]

        order, rows = await ids()
        assert order[0] == str(r3) and order[1] == str(r1) and order[-1] == str(r2), order
        assert set(order[2:5]) >= {str(r4), str(r6)} and len(order) == 6
        by = {x["id"]: x for x in rows}
        row = by[str(r1)]
        created = await env.conn.fetchval("SELECT created_at FROM player_reports WHERE id = $1", r1)
        stamp = rules.utc_stamp(created)
        assert row == {
            "id": str(r1), "created_at": stamp, "status": "open", "reason": "cheating", "details": "",
            "game_kind": "2v2", "game_id": str(g), "game_ended_at": stamp,
            "reporter_steam_id": a.steam, "reporter_name": a.name,
            "reported_steam_id": d.steam, "reported_name": d.name,
            # a, b and c reported d inside 30 days (c twice); e's report is older.
            "reporters_30d": 3, "has_log": True, "closed_at": None, "closed_by": None, "close_note": "",
        }, row
        assert (by[str(r2)]["status"], by[str(r2)]["closed_by"]) == ("actioned", adm.name)
        assert by[str(r2)]["closed_at"] is not None and by[str(r4)]["reporters_30d"] == 0
        # The filter, the page, and the launcher's own read (one row, the open count).
        assert (await ids(status="actioned"))[0] == [str(r2)]
        assert (await ids(status="dismissed"))[0] == []
        assert len((await ids(status="open"))[0]) == 5
        assert (await ids(limit=1))[0] == [str(r3)]
        assert (await ids(limit=2, offset=1))[0] == order[1:3]
        assert code(await env.listing(adm, status="banana")) == (422, "bad_status")
        for bad in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
            assert (await env.listing(adm, **bad)).status_code == 422, bad
    run_env(monkeypatch, body, prefix="plrqueue")


def test_closing_takes_an_open_report_once_and_stores_the_verdict_the_closer_and_the_note(monkeypatch):
    async def body(env):
        adm = await env.admin()
        bare = await env.admin(with_player=False)          # an admin account that never played
        a, b, c, d = await env.players(4)
        r1 = await seed_report(env.conn, a.pid, b.pid)
        r2 = await seed_report(env.conn, a.pid, c.pid)
        r3 = await seed_report(env.conn, a.pid, d.pid)

        async def row(rid):
            x = await env.conn.fetchrow(
                "SELECT status, closed_by, close_note, closed_at IS NOT NULL AS closed FROM player_reports"
                " WHERE id = $1", rid)
            return tuple(x)

        r = await env.shut(adm, r1, "actioned", note="  spoke to them  ")
        assert r.status_code == 200 and r.json() == {"ok": True, "status": "actioned"}, r.text
        assert await row(r1) == ("actioned", adm.pid, "spoke to them", True)
        # Once: a second close is refused whatever its verdict, and changes nothing.
        for verdict in ("actioned", "dismissed"):
            assert code(await env.shut(adm, r1, verdict, note="again")) == (409, "already_closed"), verdict
        assert await row(r1) == ("actioned", adm.pid, "spoke to them", True)
        r = await env.shut(bare, r2, "dismissed")
        assert r.status_code == 200 and r.json() == {"ok": True, "status": "dismissed"}, r.text
        assert await row(r2) == ("dismissed", None, "", True)
        # No such report; an id that is no id; a verdict outside the list; a note over its length as sent.
        assert code(await env.shut(adm, uuid.uuid4(), "dismissed")) == (404, "report_not_found")
        assert (await env.shut(adm, "not-an-id", "dismissed")).status_code == 400
        assert code(await env.shut(adm, r3, "open")) == (422, "bad_verdict")
        assert code(await env.shut(adm, r3, "dismissed", note="n" * (4 * rules.NOTE_MAX + 1))) == (
            422, "note_too_long")
        assert await row(r3) == ("open", None, "", False)
        # A note is cut to what the column holds.
        r = await env.shut(adm, r3, "dismissed", note="n" * (rules.NOTE_MAX + 50))
        assert r.status_code == 200 and (await row(r3))[2] == "n" * rules.NOTE_MAX, r.text
    run_env(monkeypatch, body, prefix="plrclose")


def test_the_log_route_serves_a_stored_log_as_text_through_the_scrub(monkeypatch):
    async def body(env):
        adm = await env.admin()
        me, ann, bo = await env.players(3)
        token = await env.session(me.steam)
        g = await seed_game(env.conn, "1v2", [me.pid, ann.pid, bo.pid])
        assert (await env.submit(token, "1v2", g, ann.steam, log_text=LOG)).json() == {"ok": True, "log_stored": True}
        assert (await env.submit(token, "1v2", g, bo.steam)).json() == {"ok": True, "log_stored": False}
        with_log, without = await env.report_of(me, ann), await env.report_of(me, bo)
        r = await env.log(adm, with_log)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/plain")
        assert r.headers["content-disposition"] == 'attachment; filename="player-report-%s.log"' % with_log
        assert (r.headers["cache-control"], r.headers["referrer-policy"]) == ("no-store", "no-referrer")
        assert r.headers["x-scrub-version"] == main._BUG_LOG_SCRUB_VERSION
        assert "AB12" * 16 not in r.text and "line 00399" in r.text and r.text.endswith("the last line")
        assert code(await env.log(adm, without)) == (404, "no_log")
        assert code(await env.log(adm, uuid.uuid4())) == (404, "report_not_found")
        assert (await env.log(adm, "not-an-id")).status_code == 400
        # The list says the same of both.
        rows = {x["id"]: x["has_log"] for x in (await env.listing(adm)).json()["reports"]}
        assert rows == {str(with_log): True, str(without): False}
    run_env(monkeypatch, body, prefix="plrread")


def test_a_read_replica_refuses_both_posts_and_still_answers_the_gets(monkeypatch):
    async def body(env):
        adm = await env.admin()
        me, ann = await env.players(2)
        token = await env.session(me.steam)
        g = await seed_game(env.conn, "1v1", [me.pid, ann.pid])
        rid = await seed_report(env.conn, ann.pid, me.pid)
        before = await env.fingerprint()
        monkeypatch.setattr(main, "IS_REPLICA", True)
        r = await env.submit(token, "1v1", g, ann.steam)
        assert code(r) == (503, "read_replica") and env.last == [], (r.text, env.last)
        r = await env.shut(adm, rid, "dismissed")
        assert code(r) == (503, "read_replica") and writes(env.last) == [], (r.text, env.last)
        assert (await env.games(token)).status_code == 200
        assert (await env.listing(adm)).status_code == 200
        assert await env.fingerprint() == before
    run_env(monkeypatch, body, prefix="plrreplica")


# -- account deletion ----------------------------------------------------------------

def test_account_deletion_removes_the_reports_on_both_sides_and_clears_the_closer(monkeypatch):
    async def body(env):
        adm = await env.admin()
        a, b, c = await env.players(3)
        token_a, token_b = await env.session(a.steam), await env.session(b.steam)
        g = await seed_game(env.conn, "1v1", [a.pid, b.pid])
        assert (await env.submit(token_a, "1v1", g, b.steam, log_text=LOG)).json() == {"ok": True, "log_stored": True}
        ab = await env.report_of(a, b)                                           # filed by a route, with a log
        ba = await seed_report(env.conn, b.pid, a.pid)
        cb = await seed_report(env.conn, c.pid, b.pid, closed=HOUR, closed_by=adm.pid)
        ac = await seed_report(env.conn, a.pid, c.pid, closed=HOUR, closed_by=b.pid)       # closed BY b
        ca = await seed_report(env.conn, c.pid, a.pid)
        await seed_log(env.conn, ba)
        await seed_log(env.conn, ac)
        assert ab is not None and await env.count() == 5

        await env.delete_account(b)

        left = {x["id"]: (x["status"], x["closed_by"], x["closed"]) for x in await env.conn.fetch(
            "SELECT id, status, closed_by, closed_at IS NOT NULL AS closed FROM player_reports")}
        assert left == {ac: ("dismissed", None, True), ca: ("open", None, False)}, left
        assert not {ab, ba, cb} & set(left), "a report naming the deleted account is left"
        assert [x["report_id"] for x in await env.conn.fetch("SELECT report_id FROM player_report_logs")] == [ac]
        assert await env.conn.fetchval(
            "SELECT count(*) FROM player_reports WHERE reporter_id = $1 OR reported_id = $1"
            " OR closed_by = $1", b.pid) == 0
        # What the deleted account's session and the other side's form see afterwards.
        assert code(await env.games(token_b)) == (401, "session_required")
        r = await env.games(token_a)
        assert r.status_code == 200 and r.json()["games"] == [], r.text
        assert code(await env.submit(token_a, "1v1", g, b.steam)) == (404, "game_not_found")
    run_env(monkeypatch, body, prefix="plrdelete")


# -- condition C1 and the migration ----------------------------------------------------

def _migration_files():
    found = sorted(glob.glob(os.path.join(SQL_DIR, "[0-9][0-9][0-9]_player_reports.sql")))
    assert len(found) == 1, found
    down = os.path.join(SQL_DIR, "rollback_" + os.path.basename(found[0]))
    assert os.path.isfile(down), down
    return io.open(found[0], encoding="utf-8").read(), io.open(down, encoding="utf-8").read()


def _private_case(body, prefix):
    """A schema of the test's own, not the pool's: these two tests drop tables
    and change the planner's statistics. It is sealed last, so the drop's
    census admits whatever the test left in it."""
    cf_pg.require_live_pg()

    async def inside():
        async with cf_pg.case(prefix, with_355=False) as (c, _sm):
            try:
                await body(c.conn)
            finally:
                await c.seal()
    asyncio.run(inside())


CONSTRAINTS = sorted((
    "player_reports_pkey", "player_reports_reporter_id_fkey", "player_reports_reported_id_fkey",
    "player_reports_closed_by_fkey", "player_reports_two_players", "player_reports_kind", "player_reports_reason",
    "player_reports_details_len", "player_reports_status", "player_reports_closed", "player_reports_note_len",
    "player_reports_once", "player_report_logs_pkey", "player_report_logs_report_id_fkey", "player_report_logs_size"))
INDEXES = sorted(("player_reports_pkey", "player_reports_once", "ix_player_reports_status_time",
                  "ix_player_reports_reported_time", "player_report_logs_pkey"))
ON_DELETE = {"player_reports_reporter_id_fkey": "c", "player_reports_reported_id_fkey": "c",
             "player_reports_closed_by_fkey": "n", "player_report_logs_report_id_fkey": "c"}
OURS = "('player_reports', 'player_report_logs')"


async def _catalogue(conn):
    """(the two tables, the switch row, constraints, indexes, what each foreign
    key does on delete, the log column's storage) as the schema has them."""
    tables = sorted(r[0] for r in await conn.fetch(
        "SELECT table_name::text FROM information_schema.tables WHERE table_schema = current_schema()"
        " AND table_name IN " + OURS))
    switch = await conn.fetchval("SELECT value FROM runtime_settings WHERE key = $1", rules.SWITCH_KEY)
    if not tables:
        return tables, switch, [], [], {}, None
    cons = await conn.fetch(
        "SELECT c.conname::text AS name, c.contype::text AS kind, c.confdeltype::text AS on_delete"
        "  FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid"
        "  JOIN pg_namespace n ON n.oid = t.relnamespace"
        " WHERE n.nspname = current_schema() AND t.relname IN " + OURS + " AND c.contype::text <> 'n'")
    indexes = sorted(r[0] for r in await conn.fetch(
        "SELECT indexname::text FROM pg_indexes WHERE schemaname = current_schema() AND tablename IN " + OURS))
    storage = await conn.fetchval(
        "SELECT attstorage::text FROM pg_attribute WHERE attrelid = 'player_report_logs'::regclass"
        " AND attname = 'gz'")
    return (tables, switch, sorted(c["name"] for c in cons), indexes,
            {c["name"]: c["on_delete"] for c in cons if c["kind"] == "f"}, storage)


def test_c1_the_migration_writes_the_switch_on_runs_twice_rolls_back_and_runs_again():
    up, down = _migration_files()
    both = ["player_report_logs", "player_reports"]
    whole = (both, rules.SWITCH_ON, CONSTRAINTS, INDEXES, ON_DELETE, "e")
    gone = ([], None, [], [], {}, None)

    async def body(conn):
        # The build replayed the migration's DDL and none of its rows.
        assert await _catalogue(conn) == (both, None) + whole[2:]
        await conn.execute(down)
        assert await _catalogue(conn) == gone
        await conn.execute(down)                                # the rollback runs twice
        await conn.execute(up)
        assert await _catalogue(conn) == whole                  # C1: the switch row is written ON
        now = await conn.fetchval("SELECT now()")
        a, b = [await conn.fetchval(
            "INSERT INTO players (id, steam_id, display_name) VALUES ($2, $1, $1) RETURNING id",
            "7656119%010d" % i, uuid.uuid4())
            for i in (1, 2)]

        async def insert(**over):
            v = dict(reporter=a, reported=b, kind="1v1", game=uuid.uuid4(), reason="other", details="d",
                     status="open", closed=None, note="")
            v.update(over)
            return await conn.fetchval(
                "INSERT INTO player_reports (reporter_id, reported_id, game_kind, game_id, game_ended_at, reason,"
                " details, status, closed_at, close_note) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)"
                " RETURNING id", v["reporter"], v["reported"], v["kind"], v["game"], now, v["reason"],
                v["details"], v["status"], v["closed"], v["note"])

        # Each CHECK refuses its own row and nothing at its cap.
        refused = [
            ("player_reports_two_players", dict(reported=a)),
            ("player_reports_kind", dict(kind="3v3")),
            ("player_reports_reason", dict(reason="rude")),
            ("player_reports_details_len", dict(details="x" * (rules.DETAILS_MAX + 1))),
            ("player_reports_status", dict(status="closed", closed=now)),
            ("player_reports_closed", dict(status="open", closed=now)),
            ("player_reports_closed", dict(status="dismissed")),
            ("player_reports_note_len", dict(status="actioned", closed=now, note="x" * (rules.NOTE_MAX + 1))),
        ]
        for name, over in refused:
            with pytest.raises(asyncpg.exceptions.CheckViolationError) as caught:
                await insert(**over)
            assert caught.value.constraint_name == name, (name, over, caught.value.constraint_name)
        for kind in rules.GAME_KINDS:
            for reason in rules.REASONS:
                await insert(kind=kind, reason=reason)
        await insert(details="x" * rules.DETAILS_MAX)
        for verdict in rules.VERDICTS:
            await insert(status=verdict, closed=now, note="x" * rules.NOTE_MAX)
        # One report per reporter, game and player; another kind or the other direction is another report.
        g = uuid.uuid4()
        rid = await insert(game=g)
        with pytest.raises(asyncpg.exceptions.UniqueViolationError) as caught:
            await insert(game=g, reason="cheating")
        assert caught.value.constraint_name == "player_reports_once"
        await insert(game=g, kind="2v2")
        await insert(game=g, reporter=b, reported=a)
        # The log row: its size, its count, and it goes with its report.
        add_log = "INSERT INTO player_report_logs (report_id, gz, raw_chars) VALUES ($1, $2, $3)"
        for gz, n in ((b"x", -1), (b"x" * (rules.LOG_GZ_MAX + 1), 1)):
            with pytest.raises(asyncpg.exceptions.CheckViolationError) as caught:
                await conn.execute(add_log, rid, gz, n)
            assert caught.value.constraint_name == "player_report_logs_size"
        await conn.execute(add_log, rid, b"x" * rules.LOG_GZ_MAX, 0)
        await conn.execute("DELETE FROM player_reports WHERE id = $1", rid)
        assert await conn.fetchval("SELECT count(*) FROM player_report_logs") == 0
        # An operator turned the switch off and reports are stored: a second run keeps both.
        await conn.execute("UPDATE runtime_settings SET value = '0' WHERE key = $1", rules.SWITCH_KEY)
        stored = await conn.fetchval("SELECT count(*) FROM player_reports")
        assert stored > 20
        await conn.execute(up)
        assert await _catalogue(conn) == (both, "0") + whole[2:]
        assert await conn.fetchval("SELECT count(*) FROM player_reports") == stored
        # Rolled back and run again: the tables are new and the switch is ON.
        await conn.execute(down)
        assert await _catalogue(conn) == gone
        await conn.execute(up)
        assert await _catalogue(conn) == whole
        assert await conn.fetchval("SELECT count(*) FROM player_reports") == 0
    _private_case(body, "plrmig")


# -- condition C5: what each branch of the games statement reads through ---------------------

PLAN_ROWS = {"players": 4000, "matches": 60000, "team_matches": 20000, "ovt_matches": 6000, "ffa_matches": 12000}
PLAN_TABLES = ("matches", "team_matches", "ovt_matches", "ffa_match_players", "ffa_matches")
# The index names each table is read through at the row counts above: read
# from the plan on the seat's PostgreSQL, never typed. Empty until that run.
PLAN_INDEXES = {}
_NUMBERED = "WITH p AS (SELECT id, (row_number() OVER (ORDER BY steam_id))::bigint AS n FROM players)"
_WHEN = "now() - (g.i % 400) * INTERVAL '24 hours' - (g.i % 1440) * INTERVAL '1 minute'"
_SERIES = "(SELECT i::bigint AS i, (i::bigint * 7919) % $2::bigint AS x FROM generate_series(1, $1::int) i)"


async def _bulk(conn):
    """Games of all four kinds spread over 400 days, every player in each seat
    of each table by a fixed rule, then fresh statistics."""
    n = PLAN_ROWS["players"]
    await conn.execute(
        "INSERT INTO players (id, steam_id, display_name)"
        " SELECT gen_random_uuid(), '7656119' || lpad(i::text, 10, '0'),"
        " 'bulk ' || lpad(i::text, 5, '0') FROM generate_series(1, $1::int) i", n)
    await conn.execute(
        _NUMBERED + ", g AS " + _SERIES +
        " INSERT INTO matches (id, player1_id, player2_id, p1_rounds_won, p2_rounds_won, p1_points_total,"
        " p2_points_total, is_ranked, ended_at, created_at)"
        " SELECT gen_random_uuid(), p0.id, p1.id, 3, 1, 0, 0, FALSE, " + _WHEN + ", now() FROM g"
        " JOIN p p0 ON p0.n = 1 + g.x JOIN p p1 ON p1.n = 1 + (g.x * 31 + g.i % 97 + 1) % $2::bigint"
        " WHERE p0.id <> p1.id", PLAN_ROWS["matches"], n)
    await conn.execute(
        _NUMBERED + ", g AS " + _SERIES +
        " INSERT INTO team_matches (id, t1a_id, t1b_id, t2a_id, t2b_id, t1_rounds_won, t2_rounds_won,"
        " t1_points_total, t2_points_total, winner_team, is_ranked, ended_at, created_at)"
        " SELECT gen_random_uuid(), p0.id, p1.id, p2.id, p3.id, 3, 1, 0, 0, 1, TRUE, " + _WHEN + ", now() FROM g"
        " JOIN p p0 ON p0.n = 1 + g.x JOIN p p1 ON p1.n = 1 + (g.x + 1) % $2::bigint"
        " JOIN p p2 ON p2.n = 1 + (g.x + 2) % $2::bigint JOIN p p3 ON p3.n = 1 + (g.x + 3) % $2::bigint",
        PLAN_ROWS["team_matches"], n)
    await conn.execute(
        _NUMBERED + ", g AS " + _SERIES +
        " INSERT INTO ovt_matches (id, solo_id, duo_a_id, duo_b_id, solo_rounds_won, duo_rounds_won, winner_side,"
        " ended_at) SELECT gen_random_uuid(), p0.id, p1.id, p2.id, 3, 1, 1, " + _WHEN + " FROM g"
        " JOIN p p0 ON p0.n = 1 + g.x JOIN p p1 ON p1.n = 1 + (g.x + 1) % $2::bigint"
        " JOIN p p2 ON p2.n = 1 + (g.x + 2) % $2::bigint", PLAN_ROWS["ovt_matches"], n)
    await conn.execute(
        "INSERT INTO ffa_matches (id, photon_room_id, player_count, ended_at)"
        " SELECT gen_random_uuid(), 'ffa_bulk_' || g.i, 6, " + _WHEN +
        " FROM (SELECT i FROM generate_series(1, $1::int) i) g", PLAN_ROWS["ffa_matches"])
    await conn.execute(
        _NUMBERED + ", m AS (SELECT id, split_part(photon_room_id, '_', 3)::bigint AS i FROM ffa_matches)"
        " INSERT INTO ffa_match_players (match_id, player_id, placement, absent)"
        " SELECT m.id, p.id, k + 1, FALSE FROM m CROSS JOIN generate_series(0, 5) k"
        " JOIN p ON p.n = 1 + (m.i * 7919 + k) % $1::bigint", n)
    for table in ("players",) + PLAN_TABLES:
        await conn.execute("ANALYZE " + table)


def _scans(node, out, heap=None):
    """{relation: [(node type, index name or None)]} of a plan. The index
    nodes under a bitmap heap scan count for the heap's relation."""
    rel = node.get("Relation Name") or heap
    if node.get("Relation Name") or node.get("Index Name"):
        out.setdefault(rel, []).append((node.get("Node Type"), node.get("Index Name")))
    for child in node.get("Plans", ()):
        _scans(child, out, rel)
    return out


def test_c5_each_branch_of_the_games_statement_reads_its_table_through_an_index():
    async def body(conn):
        await _bulk(conn)
        counts = {t: await conn.fetchval("SELECT count(*) FROM " + t) for t in ("players",) + PLAN_TABLES}
        assert counts["matches"] > 0.9 * PLAN_ROWS["matches"] and counts["ffa_match_players"] == 6 * PLAN_ROWS[
            "ffa_matches"], counts
        pid = await conn.fetchval("SELECT id FROM players ORDER BY steam_id LIMIT 1")
        sql = routes.GAMES_SQL.replace(":pid", "'%s'::uuid" % pid).replace(":lim", str(rules.GAME_LIST_MAX))
        assert ":" not in sql.replace("::", ""), "a bind name is left in the statement"
        rows = await conn.fetch(sql)
        listed = rules.fold_games([tuple(r) for r in rows], pid)
        assert 0 < len(listed) <= rules.GAME_LIST_MAX and {x.kind for x in listed} <= set(TABLES), len(listed)
        raw = await conn.fetchval("EXPLAIN (FORMAT JSON) " + sql)
        plan = (json.loads(raw) if isinstance(raw, str) else raw)[0]["Plan"]
        scans = _scans(plan, {})
        for table in PLAN_TABLES:
            kinds = scans.get(table)
            assert kinds, (table, "is not in the plan", sorted(str(k) for k in scans))
            assert not [k for k, index in kinds if index is None and k != "Bitmap Heap Scan"], (
                table, "is read without an index", kinds)
        used = {t: sorted({index for _, index in scans[t] if index}) for t in PLAN_TABLES}
        assert used == PLAN_INDEXES, ("measured at %r" % (counts,), used)
    _private_case(body, "plrplan")
