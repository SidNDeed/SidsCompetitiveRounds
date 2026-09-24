"""RJ-TRIAGE part 1: the read-only quarantine triage view, EXECUTED.

The three routes (V1 summary, V2 one group, D1 the digest feed), their shared
read-transaction primitive and the post-COMMIT seal, run against a real
PostgreSQL. Every control here pairs with a mutation that turns it RED and an
inert twin at the same site that stays GREEN; the mutation runner
(rj_triage_controls.py beside this file) plants both and records the result.

Live PostgreSQL is REQUIRED, and a missing DSN FAILS, naming the variable:
    RJ_TRIAGE_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    RJ_TRIAGE_TEST_PG_OPTOUT=1   says out loud that this run skips them
(the harness shape of test_ffa_game_number_anchor.py's gate). An unrun K2c
must never read as a pass.

The routes run on database.py's OWN engines -- redirected to the lane
database through a do_connect listener -- so the seal's production listener
attachment is the thing under test (K15, K15b). K2c alone runs on its own
engine: a pool of one connection whose three timeouts are forced to 0, so no
server or role default can stand in for the route's own settings.

Optional: RJ_TRIAGE_PG_LOG names a file the K2c cases append their observer
record to; RJ_TRIAGE_PG_SERVER_LOG names the server's own log, from which
case (ii) quotes the lines of the route's backend.
"""

import ast
import asyncio
import hashlib
import hmac
import inspect
import json
import math
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import database
import main
import schemas

MAIN_SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api", "main.py"))
MODELS_SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api", "models.py"))

# ── live PostgreSQL gate ──────────────────────────────────────────────────

DSN = os.environ.get("RJ_TRIAGE_TEST_PG_DSN")


def _optout(raw) -> bool:
    """Only an affirmative word opts out; "0", "false" or an unknown value do
    not, so the live checks then FAIL and name the DSN (#438)."""
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


OPTOUT = _optout(os.environ.get("RJ_TRIAGE_TEST_PG_OPTOUT"))


def require_pg():
    if DSN:
        return DSN
    if OPTOUT:
        pytest.skip("RJ_TRIAGE_TEST_PG_OPTOUT is set -- live-PostgreSQL checks deliberately "
                    "not run in this invocation")
    pytest.fail(
        "RJ_TRIAGE_TEST_PG_DSN is not set, so the triage routes, their READ ONLY transaction, "
        "the post-COMMIT seal and the lock-holding bound were never executed. Set "
        "RJ_TRIAGE_TEST_PG_DSN=postgresql+asyncpg://... to run them, or "
        "RJ_TRIAGE_TEST_PG_OPTOUT=1 to say out loud that this run skips them.")


@pytest.mark.parametrize("raw,opts_out", [
    ("1", True), ("true", True), ("TRUE", True), (" yes ", True), ("on", True),
    ("0", False), ("false", False), ("no", False), ("off", False),
    ("", False), (None, False), ("maybe", False),
])
def test_only_an_affirmative_opt_out_turns_the_live_checks_into_skips(raw, opts_out):
    assert _optout(raw) is opts_out


def test_the_live_checks_cannot_be_skipped_by_a_missing_dsn_alone():
    src = inspect.getsource(require_pg)
    assert "pytest.fail(" in src
    mod = sys.modules[__name__]
    for name in dir(mod):
        fn = getattr(mod, name)
        if callable(fn) and name.startswith("test_pg_"):
            marks = {m.name for m in getattr(fn, "pytestmark", [])}
            assert "skipif" not in marks and "skip" not in marks, name
    saved_dsn, saved_opt = globals()["DSN"], globals()["OPTOUT"]
    globals()["DSN"], globals()["OPTOUT"] = None, False
    try:
        with pytest.raises(BaseException) as ex:
            require_pg()
        assert "Failed" in type(ex.value).__name__
        assert "RJ_TRIAGE_TEST_PG_DSN" in str(ex.value)
        globals()["OPTOUT"] = True
        with pytest.raises(BaseException) as sk:
            require_pg()
        assert "Skipped" in type(sk.value).__name__
    finally:
        globals()["DSN"], globals()["OPTOUT"] = saved_dsn, saved_opt


def run(coro):
    return asyncio.run(coro)


# ── schema: the columns the routes, the capture and the checksums touch ───
# match_report_quarantine and its three indexes are 169's DDL verbatim;
# ffa_matches carries 154's columns plus 327's game_number (NOT NULL, as 327
# leaves it), its source column and idx_ffa_matches_lobby_game. The ten
# checksum tables of K15 exist so a write to any of them is visible.
# (No colon-prefixed word appears in this DDL: text() would read it as a bind.)
SCHEMA = """
DROP TABLE IF EXISTS match_report_quarantine CASCADE;
DROP TABLE IF EXISTS ffa_match_players CASCADE;
DROP TABLE IF EXISTS ffa_matches CASCADE;
DROP TABLE IF EXISTS ffa_lobbies CASCADE;
DROP TABLE IF EXISTS ffa_bets CASCADE;
DROP TABLE IF EXISTS team_matches CASCADE;
DROP TABLE IF EXISTS team_series CASCADE;
DROP TABLE IF EXISTS glicko_ratings_ffa CASCADE;
DROP TABLE IF EXISTS rating_history CASCADE;
DROP TABLE IF EXISTS gold_transactions CASCADE;
DROP TABLE IF EXISTS pc_packs CASCADE;
DROP TABLE IF EXISTS admin_users CASCADE;
DROP TABLE IF EXISTS players CASCADE;
CREATE TABLE players (
    id UUID PRIMARY KEY,
    steam_id VARCHAR(20) NOT NULL UNIQUE,
    display_name VARCHAR(64) NOT NULL DEFAULT 'Player',
    gold_earned INTEGER NOT NULL DEFAULT 0,
    total_xp INTEGER NOT NULL DEFAULT 0,
    deleted_at TIMESTAMPTZ,
    last_seen TIMESTAMPTZ
);
CREATE TABLE admin_users (
    steam_id VARCHAR(20) PRIMARY KEY,
    granted_by_steam_id VARCHAR(20),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes VARCHAR(256)
);
CREATE TABLE ffa_lobbies (
    id UUID PRIMARY KEY,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    photon_room_id VARCHAR(64),
    region VARCHAR(8),
    player_count SMALLINT NOT NULL DEFAULT 0,
    member_ids UUID[] NOT NULL DEFAULT '{}',
    games_played INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    invalidated_at TIMESTAMPTZ,
    invalidation_reason VARCHAR(64),
    host_player_id UUID REFERENCES players(id)
);
CREATE TABLE ffa_matches (
    id UUID PRIMARY KEY,
    lobby_id UUID REFERENCES ffa_lobbies(id) ON DELETE SET NULL,
    photon_room_id VARCHAR(64) NOT NULL,
    player_count SMALLINT NOT NULL DEFAULT 3,
    winner_id UUID REFERENCES players(id) ON DELETE SET NULL,
    reported_by UUID REFERENCES players(id) ON DELETE SET NULL,
    is_ranked BOOLEAN NOT NULL DEFAULT TRUE,
    ended_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    invalidated_at TIMESTAMPTZ,
    invalidation_reason VARCHAR(64),
    game_number SMALLINT NOT NULL,
    game_number_source VARCHAR(16),
    CONSTRAINT uq_ffa_match_room UNIQUE (photon_room_id)
);
CREATE INDEX idx_ffa_matches_lobby_game ON ffa_matches (lobby_id, game_number);
CREATE TABLE ffa_match_players (
    match_id UUID NOT NULL REFERENCES ffa_matches(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    slot SMALLINT,
    rounds_won SMALLINT NOT NULL DEFAULT 0,
    points_total SMALLINT NOT NULL DEFAULT 0,
    placement SMALLINT NOT NULL DEFAULT 1,
    left_early BOOLEAN NOT NULL DEFAULT FALSE,
    kills INTEGER NOT NULL DEFAULT 0,
    absent BOOLEAN NOT NULL DEFAULT FALSE,
    game_points_at_leave SMALLINT,
    PRIMARY KEY (match_id, player_id)
);
CREATE TABLE team_series (
    id UUID PRIMARY KEY,
    t1a_id UUID, t1b_id UUID, t2a_id UUID, t2b_id UUID,
    t1_series_wins SMALLINT NOT NULL DEFAULT 0,
    t2_series_wins SMALLINT NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    winner_team SMALLINT,
    photon_room_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    invalidated_at TIMESTAMPTZ,
    invalidation_reason VARCHAR(64)
);
CREATE TABLE team_matches (
    id UUID PRIMARY KEY,
    series_id UUID,
    t1a_id UUID, t1b_id UUID, t2a_id UUID, t2b_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE glicko_ratings_ffa (
    player_id UUID PRIMARY KEY,
    rating DOUBLE PRECISION NOT NULL DEFAULT 1500,
    rd DOUBLE PRECISION NOT NULL DEFAULT 350,
    games INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE rating_history (
    id BIGSERIAL PRIMARY KEY,
    player_id UUID,
    rating DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE gold_transactions (
    id BIGSERIAL PRIMARY KEY,
    player_id UUID,
    amount INTEGER NOT NULL,
    reason VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE pc_packs (
    id UUID PRIMARY KEY,
    player_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE ffa_bets (
    id UUID PRIMARY KEY,
    lobby_id UUID,
    game_number SMALLINT,
    player_id UUID,
    amount INTEGER NOT NULL DEFAULT 0,
    settled_at TIMESTAMPTZ
);
CREATE TABLE match_report_quarantine (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mode            VARCHAR(8)  NOT NULL,
    reason          VARCHAR(64) NOT NULL,
    http_status     SMALLINT    NOT NULL,
    group_id        UUID,
    photon_room_id  VARCHAR(64),
    reporter_id     UUID REFERENCES players(id) ON DELETE SET NULL,
    player_ids      UUID[]      NOT NULL DEFAULT '{}',
    payload         JSONB       NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    reviewed_by     UUID REFERENCES players(id) ON DELETE SET NULL,
    reviewed_at     TIMESTAMPTZ,
    review_note     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_quarantine_room
    ON match_report_quarantine (mode, photon_room_id)
    WHERE photon_room_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quarantine_pending
    ON match_report_quarantine (created_at DESC) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_quarantine_group
    ON match_report_quarantine (group_id) WHERE group_id IS NOT NULL
"""

WATCHED = ("match_report_quarantine", "ffa_matches", "ffa_match_players", "ffa_lobbies", "team_series")
TEN = WATCHED[:4] + ("players", "glicko_ratings_ffa", "rating_history", "gold_transactions",
                      "pc_packs", "ffa_bets")

T0 = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
ADMIN = "900000000000000900"
ADMIN_SECRET = "rj-triage-admin-secret"
INTERNAL_KEY = "rj-triage-internal-key"


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def sig(target: str) -> str:
    return hmac.new(ADMIN_SECRET.encode(), main._admin_canonical(ADMIN, "quarantine", target).encode(),
                    hashlib.sha256).hexdigest()


def steam(n: int) -> str:
    """Synthetic 18-digit ids, outside every real account range."""
    return f"9000000000000{n:05d}"


def room(tag: str, n: int | None) -> str:
    return f"RJT{tag}_120000" + (f"_r{n}" if n is not None else "")


# Seats 1..3 are A, B and C of the walks. An account maps a seat to
# (rounds_won, points_total, kills, left_early, absent).
F, T = False, True
ACC_A = {1: (3, 30, 5, F, F), 2: (1, 20, 2, F, F), 3: (0, 10, 1, F, F)}     # A wins
ACC_B = {1: (1, 15, 2, F, F), 2: (3, 30, 4, F, F), 3: (0, 5, 0, F, F)}      # B wins
ACC_C = {1: (1, 15, 2, F, F), 2: (0, 10, 1, F, F), 3: (3, 30, 4, F, F)}     # C wins
ACC_D = {1: (2, 25, 3, F, F), 2: (1, 20, 2, F, F), 3: (1, 15, 1, F, F)}     # A wins, a fourth account


def vec(ids, acct):
    return {steam(n): (ids[steam(n)],) + tuple(v) for n, v in acct.items()}


def players_of(acct):
    return [(steam(n),) + tuple(v) for n, v in acct.items()]


def pid(ids, n):
    return ids[steam(n)]


def report(lobby, room_id, reporter, winner, players, timeline=None):
    """A report payload as the capture stores it (FfaMatchReport.model_dump()).
    players: [(steam, rounds, points, kills, left_early, absent)]."""
    return schemas.FfaMatchReport(
        lobby_id=str(lobby), photon_room_id=room_id, reported_by_steam_id=reporter,
        winner_steam_id=winner, timeline=timeline,
        players=[{"steam_id": s, "rounds_won": rw, "points_total": pt, "kills": k,
                  "left_early": le, "absent": ab} for (s, rw, pt, k, le, ab) in players]).model_dump()


def cap_of(view, qid):
    return next(c for c in view["captures"] if c["id"] == str(qid))


def keys_of(obj, out=None):
    out = set() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            keys_of(v, out)
    elif isinstance(obj, list):
        for v in obj:
            keys_of(v, out)
    return out


# ── the environment of one live test ──────────────────────────────────────

def _redirect_for(url):
    def redirect(dialect, conn_rec, cargs, cparams):
        cparams.update(host=url.host, port=url.port, user=url.username, database=url.database)
        if url.password:
            cparams["password"] = url.password
        else:
            cparams.pop("password", None)
    return redirect


async def _pg(url):
    import asyncpg
    return await asyncpg.connect(host=url.host, port=url.port, user=url.username,
                                 password=url.password or None, database=url.database)


async def _clean_slate(url):
    """#753: every case starts from a slate it TAKES -- every other backend
    on the lane database is terminated first, so a lock a dead case left
    behind cannot hold this one's DDL."""
    conn = await _pg(url)
    try:
        await conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                           " WHERE datname = current_database() AND pid <> pg_backend_pid()")
    finally:
        await conn.close()


def _app():
    app = FastAPI()
    app.add_api_route("/api/v1/admin/quarantine/triage", main.admin_quarantine_triage, methods=["GET"])
    app.add_api_route("/api/v1/admin/quarantine/triage/{mode}/{group_id}",
                      main.admin_quarantine_triage_group, methods=["GET"])
    app.add_api_route("/api/v1/internal/quarantine/digest", main.internal_quarantine_digest,
                      methods=["GET"])
    return app


class Env:
    """database.py's own engines redirected to the lane database, a fresh
    schema, and a seeding engine of its own."""

    def __init__(self, monkeypatch):
        self.mp = monkeypatch
        self._seats = None

    async def __aenter__(self):
        self.url = make_url(require_pg())
        await _clean_slate(self.url)
        self.mp.setattr(main, "ADMIN_HMAC_SECRET", ADMIN_SECRET)
        self.mp.setattr(main, "MATCH_HMAC_SECRET", "")
        self.mp.setenv("API_SECRET_KEY", INTERNAL_KEY)
        self._redirect = _redirect_for(self.url)
        for eng in (database.engine, database.release_engine):
            event.listen(eng.sync_engine, "do_connect", self._redirect)
        self.seed = create_async_engine(require_pg(), pool_size=2, max_overflow=8)
        async with self.seed.begin() as conn:
            await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            for stmt in [s for s in SCHEMA.split(";") if s.strip()]:
                await conn.execute(text(stmt))
            await conn.execute(text("INSERT INTO admin_users (steam_id) VALUES (:s)"), {"s": ADMIN})
        self.app = _app()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
                                        base_url="http://triage.test")
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()
        for eng in (database.engine, database.release_engine):
            await eng.dispose()
            event.remove(eng.sync_engine, "do_connect", self._redirect)
        await self.seed.dispose()
        return False

    # -- seeding (each helper commits) --
    async def ex(self, sql, params=None):
        async with self.seed.begin() as conn:
            return await conn.execute(text(sql), params or {})

    async def exmany(self, sql, rows):
        async with self.seed.begin() as conn:
            await conn.execute(text(sql), rows)

    async def scalar(self, sql, params=None):
        async with self.seed.connect() as conn:
            return (await conn.execute(text(sql), params or {})).scalar()

    async def player(self, n: int) -> uuid.UUID:
        pid_ = uuid.uuid4()
        await self.ex("INSERT INTO players (id, steam_id) VALUES (:i, :s)", {"i": pid_, "s": steam(n)})
        return pid_

    async def players(self, *ns):
        return {steam(n): await self.player(n) for n in ns}

    async def seats(self):
        if self._seats is None:
            self._seats = await self.players(1, 2, 3)
        return self._seats

    async def lobby(self, games_played=0, status="active", player_count=3, created=0.0, lid=None):
        lid = lid or uuid.uuid4()
        await self.ex("INSERT INTO ffa_lobbies (id, status, games_played, player_count, created_at)"
                      " VALUES (:i, :st, :g, :pc, :t)",
                      {"i": lid, "st": status, "g": games_played, "pc": player_count, "t": at(created)})
        return lid

    async def settle(self, lobby, number, room_id, vec_, winner, reported_by, ended, created=None,
                     invalidated=False, source="writer"):
        """vec_: {steam: (player_id, rounds, points, kills, left_early, absent)}."""
        mid = uuid.uuid4()
        await self.ex(
            "INSERT INTO ffa_matches (id, lobby_id, photon_room_id, player_count, winner_id, reported_by,"
            " ended_at, created_at, invalidated_at, game_number, game_number_source)"
            " VALUES (:i, :l, :r, :pc, :w, :rb, :e, :c, :inv, :g, :src)",
            {"i": mid, "l": lobby, "r": room_id, "pc": len(vec_), "w": winner, "rb": reported_by,
             "e": at(ended), "c": at(created if created is not None else ended),
             "inv": at(ended) if invalidated else None, "g": number, "src": source})
        await self.exmany(
            "INSERT INTO ffa_match_players (match_id, player_id, rounds_won, points_total, kills,"
            " left_early, absent) VALUES (:m, :p, :rw, :pt, :k, :le, :ab)",
            [{"m": mid, "p": p_, "rw": rw, "pt": pt, "k": k, "le": le, "ab": ab}
             for (p_, rw, pt, k, le, ab) in vec_.values()])
        return mid

    async def ffa_settle(self, lid, number, tag, acct, winner, reporter, ended, room_id=None, **kw):
        ids = await self.seats()
        return await self.settle(lid, number, room_id or room(tag, number), vec(ids, acct), pid(ids, winner),
                                 pid(ids, reporter), ended, **kw)

    async def capture(self, *, mode="ffa", reason, group, room_id, keyed=True, reporter=None,
                      player_ids=(), payload, created, status="pending", http=409, note=None):
        qid = uuid.uuid4()
        await self.ex(
            "INSERT INTO match_report_quarantine (id, mode, reason, http_status, group_id, photon_room_id,"
            " reporter_id, player_ids, payload, status, created_at, reviewed_at, review_note)"
            " VALUES (:i, :m, :r, :h, :g, :room, :rep, :pids, CAST(:pl AS JSONB), :st, :c, :rv, :note)",
            {"i": qid, "m": mode, "r": reason, "h": http, "g": group,
             "room": room_id if keyed else None, "rep": reporter, "pids": list(player_ids),
             "pl": json.dumps(payload, default=str), "st": status, "c": at(created),
             "rv": at(created + 1) if status != "pending" else None, "note": note})
        return qid

    async def ffa_capture(self, lid, room_id, acct, winner, reporter, created,
                          reason="ffa_game_contradiction", keyed=True, timeline=None, **kw):
        ids = await self.seats()
        pl = report(lid, room_id, steam(reporter), steam(winner), players_of(acct), timeline=timeline)
        return await self.capture(reason=reason, group=lid, room_id=room_id, keyed=keyed,
                                  reporter=pid(ids, reporter), player_ids=list(ids.values()),
                                  payload=pl, created=created, **kw)

    async def real_capture(self, **kw):
        """The production capture, _quarantine_report, on a session of its own."""
        async with async_sessionmaker(self.seed, expire_on_commit=False)() as s:
            return await main._quarantine_report(s, **kw)

    async def checksums(self, tables=WATCHED):
        out = {}
        async with self.seed.connect() as conn:
            for t in tables:
                out[t] = (await conn.execute(text(
                    f"SELECT md5(COALESCE(string_agg(x::text, '|' ORDER BY x::text), '')) FROM {t} x"))).scalar()
        return out

    # -- the routes --
    async def v1(self, **cursor):
        params = {"admin_steam_id": ADMIN, "hmac_signature": sig("triage"), **cursor}
        return await self.client.get("/api/v1/admin/quarantine/triage", params=params)

    async def v2(self, mode, group):
        params = {"admin_steam_id": ADMIN, "hmac_signature": sig(f"triage:{mode}:{group}")}
        return await self.client.get(f"/api/v1/admin/quarantine/triage/{mode}/{group}", params=params)

    async def d1(self, **params):
        return await self.client.get("/api/v1/internal/quarantine/digest", params=params,
                                     headers={"X-Internal-Key": INTERNAL_KEY})


def ok(resp):
    assert resp.status_code == 200, (resp.status_code, resp.text[:2000])
    return resp.json()


# ── the walks (RJ-TRIAGE-DESIGN-V5 section 5) ─────────────────────────────

async def walk_w1(env, tag="W1", q_at=50.0):
    """W1, in W18's order: @1, @2 and H@3 settled by A (account a); G@4
    settles at 40 (account b, reported by A); C's differing account c of H,
    keyed on H's room R_r3, is captured as q1 at q_at."""
    lid = await env.lobby(games_played=4)
    r1 = await env.ffa_settle(lid, 1, tag, ACC_A, 1, 1, 10)
    r2 = await env.ffa_settle(lid, 2, tag, ACC_A, 1, 1, 20)
    h3 = await env.ffa_settle(lid, 3, tag, ACC_A, 1, 1, 30)
    g4 = await env.ffa_settle(lid, 4, tag, ACC_B, 2, 1, 40)
    q1 = await env.ffa_capture(lid, room(tag, 3), ACC_C, 3, 2, q_at)
    return {"lid": lid, "r1": r1, "r2": r2, "h3": h3, "g4": g4, "q1": q1}


async def walk_w13(env):
    """W13: L1 (W1's lobby) holds the oldest pending capture; then 60 lobbies
    each receive 3 captures after it (180 rows), and one bet row exists."""
    w = await walk_w1(env, "W13", q_at=50.0)
    groups = [uuid.uuid4() for _ in range(60)]
    rows = []
    for i, g in enumerate(groups):
        for j in range(3):
            n = i * 3 + j
            rows.append({"i": uuid.uuid4(), "g": g, "room": f"RJTW13x{n}_120000_r1", "c": at(100 + n)})
    await env.exmany("INSERT INTO match_report_quarantine (id, mode, reason, http_status, group_id,"
                     " photon_room_id, payload, created_at) VALUES (:i, 'ffa', 'lobby_completed', 409, :g,"
                     " :room, CAST('{}' AS JSONB), :c)", rows)
    await env.ex("INSERT INTO ffa_bets (id, lobby_id, game_number, amount) VALUES (:i, :l, 5, 10)",
                 {"i": uuid.uuid4(), "l": w["lid"]})
    return dict(w, groups=groups)


async def walk_w6(env, tag="W6"):
    """W6 through the production capture: @1, @2, H@3 by A; B and C deliver
    differing accounts under R_r3. B's is kept on the room's key (q6b); C's,
    a different account of a held key, becomes the variant q6c with
    photon_room_id NULL."""
    ids = await env.seats()
    lid = await env.lobby(games_played=3)
    for n in (1, 2, 3):
        await env.ffa_settle(lid, n, tag, ACC_A, 1, 1, 10 * n)
    r3 = room(tag, 3)
    outs = []
    for seat, acct in ((2, ACC_B), (3, ACC_C)):
        outs.append(await env.real_capture(
            mode="ffa", reason="ffa_game_contradiction", status_code=409,
            payload=report(lid, r3, steam(seat), steam(seat), players_of(acct)), group_id=lid,
            photon_room_id=r3, reporter_id=pid(ids, seat), player_ids=list(ids.values())))
    assert outs == ["recorded", "variant"], outs
    q6b = await env.scalar("SELECT id FROM match_report_quarantine WHERE photon_room_id = :r", {"r": r3})
    q6c = await env.scalar("SELECT id FROM match_report_quarantine WHERE group_id = :g"
                           " AND photon_room_id IS NULL", {"g": lid})
    return {"lid": lid, "q6b": q6b, "q6c": q6c, "room": r3}


async def walk_w31(env, tag="W31"):
    """W31: @1, @2, H@3 (account a); B's account of H captured at 35; J@4;
    C's account of J captured at 45."""
    lid = await env.lobby(games_played=4)
    await env.ffa_settle(lid, 1, tag, ACC_A, 1, 1, 10)
    await env.ffa_settle(lid, 2, tag, ACC_A, 1, 1, 20)
    await env.ffa_settle(lid, 3, tag, ACC_A, 1, 1, 30)
    q1 = await env.ffa_capture(lid, room(tag, 3), ACC_B, 2, 2, 35)
    await env.ffa_settle(lid, 4, tag, ACC_A, 1, 1, 40)
    q2 = await env.ffa_capture(lid, room(tag, 4), ACC_C, 3, 3, 45)
    return lid, q1, q2


# ── K1: the view writes nothing ───────────────────────────────────────────

def test_pg_k1_the_three_routes_write_nothing(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            w = await walk_w13(env)
            before = await env.checksums(WATCHED)
            rs = [await env.v1(), await env.v2("ffa", w["lid"]), await env.d1()]
            return rs, before, await env.checksums(WATCHED)
    rs, before, after = run(body())
    for r in rs:
        ok(r)
    assert before == after


async def _warm_route(env, route, lid):
    """One untimed call of the route a timed test is about to hold, made
    before any timing starts and through database.py's engine (never the
    case's own); only its status and duration are kept, as a detail line.
    Measured over the control campaigns: the first route call of a pytest
    process spent 0.375-0.484 s between t0 and its first lock on a watched
    relation, where every later call, each on a new engine, spent
    0.000-0.063 s; a statement-timing probe put the gap just before the
    process's first ORM statement, the admin check's SELECT of admin_users.
    The process pays it once; inside a hold it is spent from the route's 1 s
    read budget. Case (i) holds the route 0.55 s after its second read, and
    a cold V1 answered 503 there."""
    started = time.monotonic()
    if route == "V1":
        status = (await env.v1()).status_code
    elif route == "V2":
        status = (await env.v2("ffa", lid)).status_code
    elif route == "D1":
        status = (await env.d1()).status_code
    else:
        status = await _k2c_primitive(async_sessionmaker(database.engine, expire_on_commit=False))
    return (f"warm-up (untimed, database.py's engine): {route} answered {status}"
            f" in {time.monotonic() - started:.3f} s")


# ── K2: no lock of the view delays a capture, on every route ──────────────

@pytest.mark.parametrize("route", ["V1", "V2", "D1"])
def test_pg_k2_a_capture_commits_while_the_route_is_open(route, monkeypatch):
    """The route is held open right after its first read of
    match_report_quarantine (its second read), and a capture of a pending
    group runs on a second connection meanwhile; it must COMMIT within that
    hold. The hold lasts at most 0.7 s -- the route's own 1 s idle bound
    would end a longer one -- so the commit is asked for while the route is
    still open, inside V5's 2 s. The route is first called once, untimed
    (_warm_route), so the hold is not also spent on the process's first-call
    cost."""
    async def body():
        async with Env(monkeypatch) as env:
            w = await walk_w1(env, "K2")
            ids = await env.seats()
            await _warm_route(env, route, w["lid"])
            state = {"n": 0, "held": None, "task": None}
            orig_read, orig_run = main._TriageReadHandle.read, main._TriageReadHandle.run

            async def hold():
                state["n"] += 1
                if state["n"] != 2:
                    return
                t_start = time.monotonic()
                state["task"] = asyncio.ensure_future(env.real_capture(
                    mode="ffa", reason="ffa_game_contradiction", status_code=409,
                    payload=report(w["lid"], room("K2", 9), steam(3), steam(3), players_of(ACC_C)),
                    group_id=w["lid"], photon_room_id=room("K2", 9), reporter_id=pid(ids, 3),
                    player_ids=list(ids.values())))
                try:
                    await asyncio.wait_for(asyncio.shield(state["task"]), 0.7)
                    state["held"] = ("committed", time.monotonic() - t_start)
                except asyncio.TimeoutError:
                    state["held"] = ("waiting", time.monotonic() - t_start)

            async def read(self, statement, params=None):
                out = await orig_read(self, statement, params)
                await hold()
                return out

            async def run_(self, helper, *args, savepoint=False):
                out = await orig_run(self, helper, *args, savepoint=savepoint)
                await hold()
                return out

            monkeypatch.setattr(main._TriageReadHandle, "read", read)
            monkeypatch.setattr(main._TriageReadHandle, "run", run_)
            if route == "V1":
                resp = await env.v1()
            elif route == "V2":
                resp = await env.v2("ffa", w["lid"])
            else:
                resp = await env.d1()
            outcome = await state["task"] if state["task"] is not None else None
            return resp, state["held"], outcome
    resp, held, outcome = run(body())
    assert resp.status_code == 200, (resp.status_code, resp.text[:500])
    assert held is not None, "the route never reached its first read of match_report_quarantine"
    assert held[0] == "committed", f"the capture was still waiting {held[1]:.2f}s into the hold"
    assert held[1] <= 2.0
    assert outcome == "recorded"


# ── K2c: relation-lock holding of at most 5.5 s from t0, on every route ──

K2C_TIMEOUTS = ("statement_timeout", "lock_timeout", "idle_in_transaction_session_timeout")
K2C_BOUND_S = 5.5
K2C_WATCH_S = 12.0
K2C_CASES = [("i", "V1"), ("i", "V2"), ("i", "D1"),
             ("ii", "V1"), ("ii", "V2"), ("ii", "D1"),
             ("iii", "V1"), ("iii", "V2"), ("iii", "D1"),
             ("iv", "V2"), ("iv", "primitive")]


class _Thread(threading.Thread):
    """One coroutine on its own event loop, in its own OS thread, so a stall
    of the route's loop cannot stop it."""

    def __init__(self, name, factory):
        super().__init__(name=name, daemon=True)
        self.factory, self.result, self.error, self.done_at = factory, None, None, None

    def run(self):
        try:
            self.result = asyncio.run(self.factory())
        except BaseException as e:   # recorded, never swallowed: the verdict reads it
            self.error = e
        finally:
            self.done_at = time.monotonic()


async def _observe(url, pid_box, t0_box, cap_s=45.0):
    """The lock observer: samples pg_locks every 50 ms on its own connection,
    each sample stamped with time.monotonic() -- the clock t0 is taken on --
    both when its query starts (tick) and when it returns (at). It stops
    only after a sample that STARTED at or past t0 + 12 s (or at its cap)."""
    conn = await _pg(url)
    samples = []
    try:
        oid = await conn.fetchrow("SELECT 'match_report_quarantine'::regclass::oid AS q,"
                                  " 'ffa_matches'::regclass::oid AS m, 'ffa_lobbies'::regclass::oid AS l")
        names = {oid["q"]: "match_report_quarantine", oid["m"]: "ffa_matches", oid["l"]: "ffa_lobbies"}
        start = time.monotonic()
        while True:
            tick = time.monotonic()
            p = pid_box.get("pid")
            rows = await conn.fetch("SELECT pid, relation, mode, granted FROM pg_locks"
                                    " WHERE locktype = 'relation' AND relation = ANY($1::oid[])", list(names))
            act = await conn.fetchrow("SELECT state FROM pg_stat_activity WHERE pid = $1", p) if p else None
            samples.append({
                "tick": tick, "at": time.monotonic(), "pid": p,
                "route": sorted({names[r["relation"]] for r in rows if r["pid"] == p and r["granted"]}),
                "state": act["state"] if act else None,
                "waiting": sorted({(r["pid"], names[r["relation"]], r["mode"]) for r in rows if not r["granted"]}),
            })
            t0 = t0_box.get("t0")
            if (t0 is not None and tick >= t0 + K2C_WATCH_S) or tick - start > cap_s:
                break
            await asyncio.sleep(max(0.0, 0.05 - (time.monotonic() - tick)))
    finally:
        await conn.close()
    return samples


async def _hold_staggered(url, base_box, ready, n=10, step=0.9, wait_cap=20.0):
    """Case (iv)'s holder: ten connections each hold one rj_stagger table in
    ACCESS EXCLUSIVE mode and release them 0.9 s apart from the trigger, so
    each of the route's staggered reads waits under lock_timeout and only
    their sum is over the bound (#689)."""
    conns, released = [], []
    try:
        for k in range(1, n + 1):
            c = await _pg(url)
            conns.append(c)
            await c.execute("BEGIN")
            await c.execute(f"LOCK TABLE rj_stagger_{k} IN ACCESS EXCLUSIVE MODE")
        ready.set()
        start = time.monotonic()
        while "base" not in base_box and time.monotonic() - start < wait_cap:
            await asyncio.sleep(0.005)
        base = base_box.get("base", time.monotonic())
        for k, c in enumerate(conns, 1):
            delay = base + step * k - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            await c.execute("COMMIT")
            released.append(time.monotonic())
    finally:
        for c in conns:
            try:
                await c.close()
            except Exception:
                pass
    return released


async def _alter(url):
    c = await _pg(url)
    try:
        await c.execute("ALTER TABLE match_report_quarantine ADD COLUMN k2c_probe integer")
        return time.monotonic()
    finally:
        await c.close()


async def _capture_elsewhere(dsn, kw):
    eng = create_async_engine(dsn, pool_size=1, max_overflow=0)
    try:
        async with async_sessionmaker(eng, expire_on_commit=False)() as s:
            outcome = await main._quarantine_report(s, **kw)
        return outcome, time.monotonic()
    finally:
        await eng.dispose()


async def _k2c_show(maker):
    async with maker() as s:
        vals = tuple([str((await s.execute(text(f"SHOW {n}"))).scalar()) for n in K2C_TIMEOUTS])
        await s.commit()
    return vals


async def _k2c_primitive(maker):
    """Case (iv) on the primitive itself: a caller issuing its reads through
    the handle -- two plain ones, then ten the holder staggers."""
    async def read(h):
        out = [await h.read("SELECT COUNT(*) AS n FROM match_report_quarantine WHERE status = 'pending'"),
               await h.read("SELECT COUNT(*) AS n FROM ffa_lobbies")]
        for _ in range(10):
            out.append(await h.read("SELECT COUNT(*) AS n FROM match_report_quarantine"))
        return out

    async def build(rows):
        return len(rows)

    async with maker() as s:
        try:
            await main._triage_read_txn(s, read, build)
            return 200
        except HTTPException as e:
            return e.status_code


def _k2c_verdict(case, route, box):
    t0 = box.get("t0")
    samples = box.get("samples") or []
    rel = (lambda v: None if v is None or t0 is None else round(v - t0, 3))
    lock_samples = [s for s in samples if s["route"]]
    seen_before = [s for s in lock_samples if t0 is not None and s["at"] < t0 + K2C_BOUND_S]
    held_after = [s for s in lock_samples if t0 is not None and s["tick"] > t0 + K2C_BOUND_S]
    last_lock = max((s["at"] for s in lock_samples), default=None)
    release = next((s["at"] for s in samples if last_lock is not None and s["tick"] > last_lock
                    and not s["route"]), None)
    gone = next((s["at"] for s in samples if s["pid"] and s["state"] is None and t0 is not None
                 and s["tick"] > t0), None)
    alter_waited = any(w[1] == "match_report_quarantine" and w[2] == "AccessExclusiveLock"
                       for s in samples for w in s["waiting"])
    capture_waited = any(w[1] == "match_report_quarantine" and w[2] in ("AccessShareLock", "RowExclusiveLock")
                         for s in samples for w in s["waiting"])
    alter_done = box.get("alter_done")
    cap = box.get("capture") or (None, None)
    alter_run = (max(0.0, alter_done - release) if (alter_done is not None and release is not None) else None)
    cover = samples[-1]["tick"] if samples else None
    fields = {
        "case": case, "route": route, "status": box.get("status"),
        "first_lock": rel(min((s["at"] for s in lock_samples), default=None)), "last_lock": rel(last_lock),
        "release_seen": rel(release), "held_after_bound": len(held_after), "samples": len(samples),
        "cover_to": rel(cover), "alter_waited": alter_waited, "alter_done": rel(alter_done),
        "alter_run": None if alter_run is None else round(alter_run, 3), "capture": cap[0],
        "capture_done": rel(cap[1]), "capture_waited": capture_waited, "pid_gone": rel(gone),
        "show_before": "/".join(box.get("show_before") or ()), "show_after": "/".join(box.get("show_after") or ()),
    }
    why = []
    if t0 is None:
        verdict, why = "NO_VERDICT", ["the route never started a read (no t0)"]
    elif not seen_before:
        verdict, why = "NO_VERDICT", ["no sample saw the route's backend hold a relation lock before t0+5.5"]
    elif cover is None or cover < t0 + K2C_WATCH_S:
        verdict, why = "NO_VERDICT", [f"the observer stopped at {rel(cover)}, before t0+{K2C_WATCH_S}"]
    elif not alter_waited:
        verdict, why = "NO_VERDICT", ["the ALTER was never seen queued behind the route"]
    elif case == "i" and box.get("status") != 200:
        verdict, why = "NO_VERDICT", [f"case (i) is the normal path and the route answered {box.get('status')},"
                                       " so it never reached the COMMIT after which SHOW is read"]
    else:
        if held_after:
            why.append(f"route held {held_after[0]['route']} at {rel(held_after[0]['tick'])}")
        if cap[0] != "recorded" or cap[1] is None:
            why.append(f"capture outcome {cap[0]!r}")
        elif cap[1] - t0 > K2C_BOUND_S + (alter_run or 0.0) + 0.5:
            why.append(f"capture committed at {rel(cap[1])}, past 5.5 s + the ALTER's run")
        want = ("0", "0", "0")
        if tuple(box.get("show_before") or ()) != want or tuple(box.get("show_after") or ()) != want:
            why.append(f"SHOW before {fields['show_before']} after {fields['show_after']}")
        verdict = "FAIL" if why else "PASS"
    line = "K2C-VERDICT " + " ".join(f"{k}={v}" for k, v in fields.items()) + f" verdict={verdict}"
    if why:
        line += " why=" + "; ".join(why)
    return verdict, line


def _k2c_record(line, detail, capsys):
    with capsys.disabled():
        print("\n" + line)
    path = os.environ.get("RJ_TRIAGE_PG_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            for d in detail:
                fh.write("    " + d + "\n")


async def _k2c_fixture(env):
    """W22: L1 with 50 pending captures and four settled rows; L2 holds one
    pending row, so the queued capture (into L2) is below quota and INSERTs.
    Ten rj_stagger tables exist for case (iv)'s holder."""
    ids = await env.seats()
    l1 = await env.lobby(games_played=4)
    for n in (1, 2, 3, 4):
        await env.ffa_settle(l1, n, "K2cL1", ACC_A, 1, 1, 10 * n)
    rows = []
    for n in range(50):
        r_ = room(f"K2cQ{n}", 5)
        rows.append({"i": uuid.uuid4(), "g": l1, "room": r_, "rep": pid(ids, 2), "pids": list(ids.values()),
                     "pl": json.dumps(report(l1, r_, steam(2), steam(3), players_of(ACC_C)), default=str),
                     "c": at(100 + n)})
    await env.exmany("INSERT INTO match_report_quarantine (id, mode, reason, http_status, group_id,"
                     " photon_room_id, reporter_id, player_ids, payload, created_at) VALUES (:i, 'ffa',"
                     " 'ffa_game_number_mismatch', 409, :g, :room, :rep, :pids, CAST(:pl AS JSONB), :c)", rows)
    l2 = await env.lobby(games_played=1)
    await env.ffa_capture(l2, room("K2cL2", 1), ACC_C, 3, 2, 200)
    for k in range(1, 11):
        await env.ex(f"DROP TABLE IF EXISTS rj_stagger_{k}")
        await env.ex(f"CREATE TABLE rj_stagger_{k} (x integer)")
    r_c = room("K2cC", 1)
    return {"l1": l1, "l2": l2, "capture_kw": dict(
        mode="ffa", reason="ffa_game_contradiction", status_code=409,
        payload=report(l2, r_c, steam(3), steam(3), players_of(ACC_C)), group_id=l2, photon_room_id=r_c,
        reporter_id=pid(ids, 3), player_ids=list(ids.values()))}


def _server_log_lines(pid_):
    path = os.environ.get("RJ_TRIAGE_PG_SERVER_LOG")
    if not path or not pid_:
        return ["server log: not read (RJ_TRIAGE_PG_SERVER_LOG unset)"]
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 1_048_576))
            tail = fh.read().decode("utf-8", "replace")
    except OSError as e:
        return [f"server log: unreadable ({e})"]
    # A backend pid is reused across the log's life: keep only this backend's
    # lines stamped within the last 300 s (the log's prefix is '%m [%p] ', in
    # the seat's local time).
    now, hits = datetime.now(), []
    for ln in tail.splitlines():
        if f"[{pid_}]" not in ln:
            continue
        try:
            stamp = datetime.strptime(ln[:23], "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            continue
        if abs((now - stamp).total_seconds()) <= 300:
            hits.append(ln)
    return ["server log: " + ln for ln in hits[-6:]] or [f"server log: no line for backend {pid_} in the last 300 s"]


async def _k2c_case(case, route, monkeypatch, capsys):
    dsn = require_pg()
    url = make_url(dsn)
    box = {"show_before": None, "show_after": None}
    detail = []
    ended = []
    sent = []
    async with Env(monkeypatch) as env:
        fx = await _k2c_fixture(env)
        detail.append(await _warm_route(env, route, fx["l1"]))
        capsys.readouterr()      # what the untimed call printed is not this case's
        eng = create_async_engine(dsn, pool_size=1, max_overflow=0, pool_pre_ping=True,
                                  connect_args={"server_settings": dict.fromkeys(K2C_TIMEOUTS, "0")})
        pid_box, t0_box, base_box = {}, {}, {}

        def on_checkout(dbapi_conn, rec, proxy):
            pid_box["pid"] = dbapi_conn._connection.get_server_pid()

        def on_execute(conn, cursor, statement, parameters, context, executemany):
            sent.append(statement)

        event.listen(eng.sync_engine, "checkout", on_checkout)
        event.listen(eng.sync_engine, "before_cursor_execute", on_execute)
        maker = async_sessionmaker(eng, expire_on_commit=False)
        threads = {}
        try:
            box["show_before"] = await _k2c_show(maker)
            threads["observer"] = _Thread("k2c-observer", lambda: _observe(url, pid_box, t0_box))
            threads["observer"].start()
            if case == "iv":
                ready = threading.Event()
                threads["holder"] = _Thread("k2c-holder", lambda: _hold_staggered(url, base_box, ready))
                threads["holder"].start()
                assert ready.wait(15), "the staggered holder never took its ten locks"
            threads["alter"] = _Thread("k2c-alter", lambda: _alter(url))
            threads["capture"] = _Thread("k2c-capture", lambda: _capture_elsewhere(dsn, fx["capture_kw"]))
            orig_ended = main._triage_ended_early

            def ended_early(exc):
                chain, cur, seen = [], exc, set()
                while cur is not None and id(cur) not in seen:
                    seen.add(id(cur))
                    chain.append(f"{type(cur).__module__}.{type(cur).__name__}"
                                 f"[sqlstate={getattr(cur, 'sqlstate', None)}]: {str(cur)[:140]}")
                    cur = getattr(cur, "orig", None) or cur.__cause__
                ended.append(chain)
                return orig_ended(exc)

            monkeypatch.setattr(main, "_triage_ended_early", ended_early)
            ops = {"n": 0}
            orig_read, orig_run = main._TriageReadHandle.read, main._TriageReadHandle.run

            def op_index(h):
                ops["n"] += 1
                if ops["n"] == 1:
                    t0_box["t0"] = h.t0
                return ops["n"]

            async def trigger(h):
                box["trigger"] = time.monotonic()
                box["route_pid"] = pid_box.get("pid")
                base_box["base"] = box["trigger"]
                threads["alter"].start()
                time.sleep(0.15)
                threads["capture"].start()
                time.sleep(0.10)
                if case == "i":
                    await asyncio.sleep(0.3)
                elif case == "ii":
                    time.sleep(10.0)       # the event loop itself stalls: nothing of this process runs
                elif case == "iii":
                    await orig_read(h, "SELECT pg_sleep(10)")

            async def read(self, statement, params=None):
                k = op_index(self)
                if case == "iv" and 3 <= k <= 12:
                    statement = f"WITH _stagger AS (SELECT 1 FROM rj_stagger_{k - 2} LIMIT 0) {statement}"
                out = await orig_read(self, statement, params)
                if k == 2:
                    await trigger(self)
                return out

            async def run_(self, helper, *args, savepoint=False):
                k = op_index(self)
                if case == "iv" and 3 <= k <= 12:
                    inner, tab = helper, f"rj_stagger_{k - 2}"

                    async def helper(db, *a):
                        await db.execute(text(f"SELECT 1 FROM {tab} LIMIT 0"))
                        return await inner(db, *a)
                out = await orig_run(self, helper, *args, savepoint=savepoint)
                if k == 2:
                    await trigger(self)
                return out

            monkeypatch.setattr(main._TriageReadHandle, "read", read)
            monkeypatch.setattr(main._TriageReadHandle, "run", run_)
            if route == "primitive":
                box["status"] = await _k2c_primitive(maker)
            else:
                app = _app()

                async def k2c_get_db():
                    async with maker() as s:
                        try:
                            yield s
                        finally:
                            await s.close()

                app.dependency_overrides[main.get_db] = k2c_get_db
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                             base_url="http://triage.test") as client:
                    if route == "V1":
                        resp = await client.get("/api/v1/admin/quarantine/triage",
                                                params={"admin_steam_id": ADMIN, "hmac_signature": sig("triage")})
                    elif route == "V2":
                        target = f"triage:ffa:{fx['l1']}"
                        resp = await client.get(f"/api/v1/admin/quarantine/triage/ffa/{fx['l1']}",
                                                params={"admin_steam_id": ADMIN, "hmac_signature": sig(target)})
                    else:
                        resp = await client.get("/api/v1/internal/quarantine/digest",
                                                headers={"X-Internal-Key": INTERNAL_KEY})
                box["status"] = resp.status_code
                detail.append(f"response {resp.status_code}: {resp.text[:160]}")
            box["route_end"] = time.monotonic()
            for name in ("alter", "capture", "holder", "observer"):
                th = threads.get(name)
                if th is not None and th.ident is not None:
                    th.join(45)
            box["t0"] = t0_box.get("t0")
            obs = threads["observer"]
            box["samples"] = obs.result or []
            if obs.error is not None:
                detail.append(f"observer error: {obs.error!r}")
            if threads["alter"].ident is not None:
                box["alter_done"] = threads["alter"].result
                if threads["alter"].error is not None:
                    detail.append(f"ALTER error: {threads['alter'].error!r}")
            if threads["capture"].ident is not None:
                box["capture"] = threads["capture"].result
                if threads["capture"].error is not None:
                    detail.append(f"capture error: {threads['capture'].error!r}")
            box["show_after"] = await _k2c_show(maker)
        finally:
            await eng.dispose()
    printed = capsys.readouterr().out
    detail.extend("route printed: " + ln for ln in printed.splitlines() if ln.startswith("[TRIAGE]"))
    for s in sent:
        if "SET TRANSACTION" in s or "set_config" in s:
            detail.append("sent: " + " ".join(s.split()))
            if len([d for d in detail if d.startswith("sent: ")]) >= 2:
                break
    t0 = box.get("t0")
    if t0 is not None:
        states, last = [], object()
        for s in box["samples"]:
            key = (s["state"], tuple(s["route"]), tuple((w[1], w[2]) for w in s["waiting"]))
            if key != last:
                states.append(f"+{s['at'] - t0:7.3f} state={s['state']} holds={s['route']} "
                              f"waiting={[(w[1], w[2]) for w in s['waiting']]}")
                last = key
        detail.append("observer transitions (seconds from t0):")
        detail.extend("  " + x for x in states)
    for chain in ended:
        detail.append("the failed read, as the route saw it: " + " <- ".join(chain))
    if case == "ii":
        detail.extend(_server_log_lines(box.get("route_pid")))
    verdict, line = _k2c_verdict(case, route, box)
    _k2c_record(line, detail, capsys)
    return verdict, line


@pytest.mark.parametrize("case,route", K2C_CASES)
def test_pg_k2c_relation_locks_released_within_5_5s_of_t0(case, route, monkeypatch, capsys):
    verdict, line = run(_k2c_case(case, route, monkeypatch, capsys))
    if verdict == "NO_VERDICT":
        pytest.fail("NO VERDICT (not a pass): " + line)
    assert verdict == "PASS", line


# ── K2d: one primitive per route (static, per function span, #432) ─────────

TREE = ast.parse(open(MAIN_SRC, encoding="utf-8").read())
ROUTES = ("admin_quarantine_triage", "admin_quarantine_triage_group", "internal_quarantine_digest")
CONTROL = re.compile(r"set_config|set\s+transaction|lock\s+table|pg_advisory", re.I)
WRITE = re.compile(r"\b(insert\s+into|update\s+\w+\s+set|delete\s+from|merge\s+into)\b", re.I)


def _fn(name):
    hits = [n for n in ast.walk(TREE) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert len(hits) == 1, (name, len(hits))
    return hits[0]


def _strings(node):
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _triage_sql_constants():
    return {k: v for k, v in vars(main).items()
            if isinstance(v, str) and (k.startswith("_TRIAGE_SQL") or k.startswith("_TRIAGE_ROOM"))}


def test_k2d_each_route_enters_the_primitive_once_and_issues_no_control_statement():
    for name in ROUTES:
        fn = _fn(name)
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
        entries = [c for c in calls if isinstance(c.func, ast.Name) and c.func.id == "_triage_read_txn"]
        assert len(entries) == 1, (name, len(entries))
        own = [ast.unparse(c.func) for c in calls if isinstance(c.func, ast.Attribute) and (
            c.func.attr in ("commit", "rollback")
            or (c.func.attr == "execute" and isinstance(c.func.value, ast.Name) and c.func.value.id == "db"))]
        assert own == [], (name, own)
        bad = [s for s in _strings(fn) if CONTROL.search(s)]
        assert bad == [], (name, bad)
    prim = _strings(_fn("_triage_read_txn"))
    assert len([s for s in prim if re.search(r"set\s+transaction", s, re.I)]) == 1
    assert len([s for s in prim if "set_config" in s]) == 1
    consts = _triage_sql_constants()
    assert len(consts) >= 15, sorted(consts)
    assert [k for k, v in consts.items() if CONTROL.search(v)] == []


# ── K3: the oldest group first (B2), on the first screen and in the digest ─

def test_pg_k3_the_oldest_group_is_first_on_the_summary_and_in_the_digest(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            w = await walk_w13(env)
            return w, ok(await env.v1()), ok(await env.v2("ffa", w["lid"])), ok(await env.d1())
    w, v1, v2, d1 = run(body())
    h = v1["header"]
    assert h["pending_total"] == 181 and h["groups_with_pending"] == 61
    assert h["oldest_pending"]["id"] == str(w["q1"]) and h["oldest_pending"]["group_id"] == str(w["lid"])
    groups = v1["page"]["groups"]
    assert len(groups) == 50 and v1["page"]["next"] is not None
    assert groups[0]["group_id"] == str(w["lid"])
    assert [g["oldest"] for g in groups] == sorted(g["oldest"] for g in groups)
    assert d1["rows"][0]["id"] == str(w["q1"]) and d1["totals"]["pending"] == 181
    q = cap_of(v2, w["q1"])
    assert q["pt3"]["read"] == "4 of 4 read"
    assert q["pt3"]["label"].startswith("differs from every settled account of this lobby (4 of 4 read)")


# ── K3b: equal-time predecessors across a page boundary (W32) ─────────────

def test_pg_k3b_equal_time_groups_both_appear_across_pages_of_one(monkeypatch):
    l1 = uuid.UUID("10000000-0000-4000-8000-000000000001")
    l2 = uuid.UUID("10000000-0000-4000-8000-000000000002")

    async def body():
        async with Env(monkeypatch) as env:
            for lid, tag in ((l2, "K3bB"), (l1, "K3bA")):
                await env.lobby(lid=lid)
                await env.ffa_capture(lid, room(tag, 1), ACC_C, 3, 2, 30, reason="lobby_completed")
            monkeypatch.setattr(main, "_TRIAGE_V1_PAGE", 1)
            pages, cursor = [], {}
            for _ in range(4):
                page = ok(await env.v1(**cursor))["page"]
                pages.append([g["group_id"] for g in page["groups"]])
                if page["next"] is None:
                    break
                cursor = page["next"]
            return pages
    pages = run(body())
    union = [g for p in pages for g in p]
    assert union == [str(l1), str(l2)], pages
    assert all(len(p) <= 1 for p in pages)


# ── K4: per-group completeness at quota ───────────────────────────────────

def test_pg_k4_a_group_at_quota_shows_all_fifty(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            ids = await env.seats()
            lid = await env.lobby(games_played=2)
            rows = []
            for n in range(50):
                r_ = room(f"K4q{n}", 3)
                rows.append({"i": uuid.uuid4(), "g": lid, "room": r_, "rep": pid(ids, 2),
                             "pl": json.dumps(report(lid, r_, steam(2), steam(2), players_of(ACC_B)), default=str),
                             "c": at(10 + n)})
            await env.exmany("INSERT INTO match_report_quarantine (id, mode, reason, http_status, group_id,"
                             " photon_room_id, reporter_id, payload, created_at) VALUES (:i, 'ffa',"
                             " 'ffa_game_number_mismatch', 409, :g, :room, :rep, CAST(:pl AS JSONB), :c)", rows)
            return lid, ok(await env.v2("ffa", lid)), ok(await env.v1())
    lid, v2, v1 = run(body())
    pt2 = v2["pt2"]
    assert (pt2["pending"], pt2["quota"], pt2["at_quota"], pt2["quota_bound_exceeded"]) == (50, 50, True, False)
    assert len(v2["captures"]) == 50
    assert v1["header"]["groups_at_quota"] == [{"mode": "ffa", "group_id": str(lid), "pending": 50}]


# ── K5 / K10 / K14: W6's two seats, the variant and the claimed reporter ──

def test_pg_k5_pt1_counts_per_seat(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            w = await walk_w6(env)
            return w, await env.seats(), ok(await env.v2("ffa", w["lid"])), ok(await env.v1())
    w, ids, v2, v1 = run(body())
    want = sorted([{"reporter_id": str(pid(ids, s)), "reporter_label": "reporter as claimed by the report",
                    "pending": 1, "families": {"F3a": 1}} for s in (2, 3)], key=lambda s: s["reporter_id"])
    assert v2["pt1_seats"] == want
    assert v1["page"]["groups"][0]["pt1_seats"] == want


def test_pg_k10_a_variant_names_its_keyed_twin(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            w = await walk_w6(env)
            return w, ok(await env.v2("ffa", w["lid"]))
    w, v2 = run(body())
    assert cap_of(v2, w["q6b"])["pt4"] == {"kind": "keyed"}
    assert cap_of(v2, w["q6c"])["pt4"] == {
        "kind": "variant", "variant_of": {"id": str(w["q6b"]), "group_id": str(w["lid"]), "status": "pending"},
        "recapture_of": None}


def test_pg_k14_pt1_lists_a_capture_under_its_claimed_reporter_only(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            w = await walk_w6(env)
            return w, await env.seats(), ok(await env.v2("ffa", w["lid"]))
    w, ids, v2 = run(body())
    seats = v2["pt1_seats"]
    assert {s["reporter_id"] for s in seats} == {str(pid(ids, 2)), str(pid(ids, 3))}
    assert str(pid(ids, 1)) not in {s["reporter_id"] for s in seats}
    assert sum(s["pending"] for s in seats) == 2
    assert all(s["reporter_label"] == "reporter as claimed by the report" for s in seats)
    for c in v2["captures"]:
        assert c["reporter_label"] == "reporter as claimed by the report"


# ── K6: PT3 reads the whole lobby, nearest first ──────────────────────────

def test_pg_k6_pt3_lists_every_row_of_the_lobby_nearest_first(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            out = {}
            # W15: @1, @2, K@3; B delivers its full account of K under R_r5 (F9)
            l15 = await env.lobby(games_played=3)
            a1 = await env.ffa_settle(l15, 1, "W15", ACC_B, 2, 1, 10)
            a2 = await env.ffa_settle(l15, 2, "W15", ACC_B, 2, 1, 20)
            k3 = await env.ffa_settle(l15, 3, "W15", ACC_A, 1, 1, 30)
            q15 = await env.ffa_capture(l15, room("W15", 5), ACC_A, 1, 2, 40, reason="ffa_game_number_mismatch")
            out["W15"] = (ok(await env.v2("ffa", l15)), q15, [k3, a2, a1])
            # W16: closed after K@3; a seat one ahead delivers K under R_r4 (F5)
            l16 = await env.lobby(games_played=3, status="completed")
            b1 = await env.ffa_settle(l16, 1, "W16", ACC_B, 2, 1, 10)
            b2 = await env.ffa_settle(l16, 2, "W16", ACC_B, 2, 1, 20)
            k3b = await env.ffa_settle(l16, 3, "W16", ACC_A, 1, 1, 30)
            q16 = await env.ffa_capture(l16, room("W16", 4), ACC_A, 1, 3, 40, reason="lobby_completed")
            out["W16"] = (ok(await env.v2("ffa", l16)), q16, [k3b, b2, b1])
            # W17: @1, @2, H@3, J@4, G@5; B, two behind, delivers G under R_r3 (F3a)
            l17 = await env.lobby(games_played=5)
            c1 = await env.ffa_settle(l17, 1, "W17", ACC_A, 1, 1, 10)
            c2 = await env.ffa_settle(l17, 2, "W17", ACC_A, 1, 1, 20)
            h3 = await env.ffa_settle(l17, 3, "W17", ACC_B, 2, 1, 30)
            j4 = await env.ffa_settle(l17, 4, "W17", ACC_A, 1, 1, 40)
            g5 = await env.ffa_settle(l17, 5, "W17", ACC_C, 3, 1, 50)
            q17 = await env.ffa_capture(l17, room("W17", 3), ACC_D, 1, 2, 60)
            out["W17"] = (ok(await env.v2("ffa", l17)), q17, [h3, c2, j4, c1, g5], g5)
            # the legacy pair: two rows at one number (327:55-58)
            lp = await env.lobby(games_played=2)
            p1 = await env.ffa_settle(lp, 1, "LP", ACC_A, 1, 1, 10, source="room_tail")
            p2a = await env.ffa_settle(lp, 2, "LPa", ACC_A, 1, 1, 20, source="room_tail")
            p2b = await env.ffa_settle(lp, 2, "LPb", ACC_B, 2, 1, 21, source="room_tail")
            qp = await env.ffa_capture(lp, room("LPq", 2), ACC_C, 3, 2, 30)
            out["LP"] = (ok(await env.v2("ffa", lp)), qp, {p2a, p2b}, p1)
            return out
    out = run(body())
    v, q, want = out["W15"]
    pt3 = cap_of(v, q)["pt3"]
    assert [r["row_id"] for r in pt3["rows"]] == [str(x) for x in want]
    assert [r["distance"] for r in pt3["rows"]] == [2, 3, 4]
    assert pt3["rows"][0]["verdict"] == "AGREES" and pt3["read"] == "3 of 3 read"
    assert pt3["label"].startswith("agrees with the settled account at 3")
    v, q, want = out["W16"]
    pt3 = cap_of(v, q)["pt3"]
    assert [r["row_id"] for r in pt3["rows"]] == [str(x) for x in want]
    assert [r["distance"] for r in pt3["rows"]] == [1, 2, 3]
    v, q, want, g5 = out["W17"]
    pt3 = cap_of(v, q)["pt3"]
    assert [r["row_id"] for r in pt3["rows"]] == [str(x) for x in want]
    assert [r["distance"] for r in pt3["rows"]] == [0, 1, 1, 2, 2]
    g5_row = next(r for r in pt3["rows"] if r["row_id"] == str(g5))
    assert g5_row["verdict"] == f"winner {steam(1)} vs recorded {steam(3)}"
    assert pt3["label"].startswith("differs from every settled account of this lobby (5 of 5 read)")
    v, q, pair, p1 = out["LP"]
    rows = cap_of(v, q)["pt3"]["rows"]
    assert {r["row_id"] for r in rows if r["game_number"] == 2} == {str(x) for x in pair}
    assert len(rows) == 3 and rows[-1]["row_id"] == str(p1)


# ── K6b: the null-number rule (W23) ───────────────────────────────────────

def test_pg_k6b_a_tailless_key_leaves_d_distance_and_c2_undefined(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            lid = await env.lobby(games_played=2, status="completed")
            r1 = await env.ffa_settle(lid, 1, "W23", ACC_A, 1, 1, 10)
            r2 = await env.ffa_settle(lid, 2, "W23", ACC_A, 1, 1, 20)
            q = await env.ffa_capture(lid, room("W23", None), ACC_A, 1, 2, 30, reason="lobby_completed")
            return ok(await env.v2("ffa", lid)), q, r1, r2
    v, q, r1, r2 = run(body())
    undef = main._TRIAGE_UNDEFINED
    assert undef == "undefined: this report's key names no game"
    c = cap_of(v, q)
    assert c["family"] == "F5" and c["named_game"] == undef
    assert (c["pt1"]["r"], c["pt1"]["t"], c["pt1"]["d"]) == (2, undef, undef)
    assert c["pt1"]["line"] == (f"rows received before this capture: 2; this report's own game number: "
                                f"{undef}; r + 1 - t = {undef}")
    assert c["pt3"]["order"] == "game number, then id (the key names no game)"
    assert [r["row_id"] for r in c["pt3"]["rows"]] == [str(r1), str(r2)]
    assert all(r["distance"] == undef for r in c["pt3"]["rows"])
    assert c["pt5"]["c2"] == undef


# ── K6c: complete paging (W25) ────────────────────────────────────────────

def test_pg_k6c_a_201_row_lobby_is_read_whole_or_labelled_partial(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            ids = await env.seats()
            lid = await env.lobby(games_played=45)
            mids = [uuid.uuid4() for _ in range(201)]
            await env.exmany(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id, winner_id, reported_by, ended_at,"
                " created_at, game_number, game_number_source) VALUES (:i, :l, :r, :w, :w, :e, :e, :g, 'room_tail')",
                [{"i": m, "l": lid, "r": room("W25", n), "w": pid(ids, 1), "e": at(n), "g": n}
                 for n, m in enumerate(mids, 1)])
            await env.exmany(
                "INSERT INTO ffa_match_players (match_id, player_id, rounds_won, points_total, kills)"
                " VALUES (:m, :p, :rw, :pt, :k)",
                [{"m": m, "p": pid(ids, s), "rw": ACC_A[s][0], "pt": ACC_A[s][1], "k": ACC_A[s][2]}
                 for m in mids for s in (1, 2, 3)])
            q = await env.ffa_capture(lid, room("W25q", 202), ACC_C, 3, 2, 500, reason="lobby_game_limit")
            whole = ok(await env.v2("ffa", lid))
            orig = main._TriageReadHandle.read
            fired = {"n": 0}

            async def read(self, statement, params=None):
                out = await orig(self, statement, params)
                if statement == main._TRIAGE_SQL_V2_VECTORS and fired["n"] == 0:
                    fired["n"] = 1
                    self.t0 -= 100.0          # the read deadline is reached right after page 1
                return out

            monkeypatch.setattr(main._TriageReadHandle, "read", read)
            part = ok(await env.v2("ffa", lid))
            return q, whole, part
    q, whole, part = run(body())
    page = main._TRIAGE_PT3_PAGE
    assert page < 201
    c = cap_of(whole, q)
    assert c["family"] == "F7"
    assert whole["accounts"]["read"] == "201 of 201 read" and whole["accounts"]["complete"] is True
    assert len(c["pt3"]["rows"]) == 201 and c["pt3"]["read"] == "201 of 201 read"
    assert c["pt3"]["label"].startswith("differs from every settled account of this lobby (201 of 201 read)")
    c = cap_of(part, q)
    assert part["reads"]["budget_spent"] is True and part["accounts"]["complete"] is False
    assert len(c["pt3"]["rows"]) == page and c["pt3"]["read"] == f"{page} of 201 read"
    assert c["pt3"]["label"] == (f"{page} of 201 rows read before the read budget ran out; "
                                 "no lobby-wide statement is made; reopen the view")
    assert c["pt5"]["c2"] == main._TRIAGE_INCOMPLETE and c["pt1"]["r"] == main._TRIAGE_INCOMPLETE


# ── K6d: the expected game in the migration gap (W24) ─────────────────────

def test_pg_k6d_the_migration_gap_shows_expected_six(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            lid = await env.lobby(games_played=4)
            for n in range(1, 6):
                await env.ffa_settle(lid, n, "W24", ACC_A, 1, 1, 10 * n, source="room_tail")
            await env.ffa_capture(lid, room("W24", 7), ACC_A, 1, 2, 80, reason="ffa_game_number_mismatch")
            before = await env.scalar("SELECT games_played FROM ffa_lobbies WHERE id = :i", {"i": lid})
            v = ok(await env.v2("ffa", lid))
            after = await env.scalar("SELECT games_played FROM ffa_lobbies WHERE id = :i", {"i": lid})
            return v, before, after
    v, before, after = run(body())
    lob = v["pt2"]["lobby"]
    assert (lob["games_played"], lob["highest_held_game"], lob["expected_game"]) == (4, 5, 6)
    assert lob["migration_gap"] == ("games_played 4; highest held game 5; a report would be expected at 6 "
                                    "(the endpoint's catch-up moves the counter; this view does not)")
    assert before == after == 4


# ── K7: PT3's vector parity with the arm (W1) ─────────────────────────────

def test_pg_k7_pt3_compares_with_the_arms_vector_absent_included(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            w = await walk_w1(env, "K7")
            la = await env.lobby(games_played=1)
            absent_row = {1: (3, 30, 5, F, F), 2: (1, 20, 2, F, F), 3: (0, 0, 0, T, T)}
            present = {1: (3, 30, 5, F, F), 2: (1, 20, 2, F, F), 3: (0, 0, 0, F, F)}
            r1 = await env.ffa_settle(la, 1, "K7a", absent_row, 1, 1, 10)
            qa = await env.ffa_capture(la, room("K7a", 1), present, 1, 2, 20)
            return w, ok(await env.v2("ffa", w["lid"])), ok(await env.v2("ffa", la)), qa, r1
    w, v1, va, qa, r1 = run(body())
    rows = {r["row_id"]: r["verdict"] for r in cap_of(v1, w["q1"])["pt3"]["rows"]}
    assert rows[str(w["h3"])] == f"winner {steam(3)} vs recorded {steam(1)}"
    assert rows[str(w["g4"])] == f"winner {steam(3)} vs recorded {steam(2)}"
    row = cap_of(va, qa)["pt3"]["rows"]
    assert [r["row_id"] for r in row] == [str(r1)]
    assert row[0]["verdict"] == f"{steam(3)} did-not-play=False vs recorded True"


# ── K8: PT3b, the same claimed reporter (W10's Y; W15 with K@3 by B) ──────

def test_pg_k8_rows_reported_by_the_captures_reporter_are_flagged(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            ly = await env.lobby(games_played=4)
            for n in (1, 2, 3):
                await env.ffa_settle(ly, n, "W10", ACC_A, 1, 1, 10 * n)
            await env.ffa_settle(ly, 4, "W10", ACC_C, 3, 2, 40)          # B reports N+1, C's win
            qy = await env.ffa_capture(ly, room("W10", 3), ACC_B, 2, 2, 50)
            l15 = await env.lobby(games_played=3)
            for n in (1, 2):
                await env.ffa_settle(l15, n, "K8", ACC_B, 2, 1, 10 * n)
            await env.ffa_settle(l15, 3, "K8", ACC_A, 1, 2, 30)          # K@3 reported by B, A's win
            q15 = await env.ffa_capture(l15, room("K8", 5), ACC_A, 1, 2, 40, reason="ffa_game_number_mismatch")
            return ok(await env.v2("ffa", ly)), qy, ok(await env.v2("ffa", l15)), q15
    vy, qy, v15, q15 = run(body())
    sy = cap_of(vy, qy)["pt3"]["same_reporter"]
    assert sy["rows_at"] == [4]
    assert sy["text"].startswith("the capture's claimed reporter also reported the settled rows at 4:")
    s15 = cap_of(v15, q15)["pt3"]["same_reporter"]
    assert s15["rows_at"] == [3]


# ── K9 / K9b: PT4, a re-capture after review ──────────────────────────────

def test_pg_k9_a_redelivered_variant_is_labelled_a_recapture(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            ids = await env.seats()
            lid = await env.lobby(games_played=3)
            for n in (1, 2, 3):
                await env.ffa_settle(lid, n, "K9", ACC_A, 1, 1, 10 * n)
            r3 = room("K9", 3)
            kw = dict(mode="ffa", reason="ffa_game_contradiction", status_code=409, group_id=lid,
                      photon_room_id=r3, player_ids=list(ids.values()))
            keyed = await env.real_capture(payload=report(lid, r3, steam(2), steam(2), players_of(ACC_B)),
                                           reporter_id=pid(ids, 2), **kw)
            var_pl = report(lid, r3, steam(3), steam(3), players_of(ACC_C))
            first = await env.real_capture(payload=var_pl, reporter_id=pid(ids, 3), **kw)
            v_old = await env.scalar("SELECT id FROM match_report_quarantine WHERE photon_room_id IS NULL")
            await env.ex("UPDATE match_report_quarantine SET status = 'discarded', reviewed_at = now(),"
                         " review_note = 'k9 discard' WHERE id = :i", {"i": v_old})
            again = await env.real_capture(payload=var_pl, reporter_id=pid(ids, 3), **kw)
            v_new = await env.scalar("SELECT id FROM match_report_quarantine WHERE photon_room_id IS NULL"
                                     " AND status = 'pending'")
            q_k = await env.scalar("SELECT id FROM match_report_quarantine WHERE photon_room_id = :r", {"r": r3})
            return (keyed, first, again), v_old, v_new, q_k, ok(await env.v2("ffa", lid))
    outs, v_old, v_new, q_k, v = run(body())
    assert outs == ("recorded", "variant", "variant")
    pt4 = cap_of(v, v_new)["pt4"]
    assert pt4["kind"] == "variant" and pt4["variant_of"]["id"] == str(q_k)
    rc = pt4["recapture_of"]
    assert isinstance(rc, dict) and rc["id"] == str(v_old)
    assert rc["status"] == "discarded" and rc["review_note"] == "k9 discard"


def test_pg_k9b_a_reviewed_twin_at_position_230_is_found(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            ids = await env.seats()
            lid = await env.lobby(games_played=3)
            r3 = room("K9b", 3)
            q_k = await env.ffa_capture(lid, r3, ACC_B, 2, 2, 1)
            rows, twin_pl, twin_id = [], None, None
            for n in range(250):
                pl = report(lid, r3, steam(3), steam(3), players_of(ACC_C), timeline=f"k9b-{n}")
                qid = uuid.uuid4()
                if n == 229:
                    twin_pl, twin_id = pl, qid
                rows.append({"i": qid, "g": lid, "rep": pid(ids, 3), "pl": json.dumps(pl, default=str),
                             "c": at(10 + n), "rv": at(10 + n + 0.5)})
            await env.exmany("INSERT INTO match_report_quarantine (id, mode, reason, http_status, group_id,"
                             " photon_room_id, reporter_id, payload, status, created_at, reviewed_at, review_note)"
                             " VALUES (:i, 'ffa', 'ffa_game_contradiction', 409, :g, NULL, :rep,"
                             " CAST(:pl AS JSONB), 'discarded', :c, :rv, 'k9b')", rows)
            new = await env.capture(reason="ffa_game_contradiction", group=lid, room_id=r3, keyed=False,
                                    reporter=pid(ids, 3), payload=twin_pl, created=400)
            return q_k, twin_id, new, ok(await env.v2("ffa", lid))
    q_k, twin_id, new, v = run(body())
    assert v["reads"]["reviewed_read_complete"] is True
    pt4 = cap_of(v, new)["pt4"]
    assert pt4["variant_of"]["id"] == str(q_k)
    assert isinstance(pt4["recapture_of"], dict) and pt4["recapture_of"]["id"] == str(twin_id)


# ── K10b: a cross-group keyed twin (W26) ──────────────────────────────────

def test_pg_k10b_a_variant_finds_its_keyed_twin_in_another_group(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            ids = await env.seats()
            l1 = await env.lobby(games_played=3)
            l2 = await env.lobby(games_played=3)
            r3 = room("W26", 3)
            o1 = await env.real_capture(mode="ffa", reason="ffa_game_contradiction", status_code=409,
                                        payload=report(l1, r3, steam(2), steam(2), players_of(ACC_B)),
                                        group_id=l1, photon_room_id=r3, reporter_id=pid(ids, 2),
                                        player_ids=list(ids.values()))
            o2 = await env.real_capture(mode="ffa", reason="lobby_completed", status_code=409,
                                        payload=report(l2, r3, steam(3), steam(3), players_of(ACC_C)),
                                        group_id=l2, photon_room_id=r3, reporter_id=pid(ids, 3),
                                        player_ids=list(ids.values()))
            q1 = await env.scalar("SELECT id FROM match_report_quarantine WHERE photon_room_id = :r", {"r": r3})
            var = await env.scalar("SELECT id FROM match_report_quarantine WHERE group_id = :g", {"g": l2})
            return (o1, o2), l1, q1, var, ok(await env.v2("ffa", l2))
    outs, l1, q1, var, v = run(body())
    assert outs == ("recorded", "variant")
    assert cap_of(v, var)["pt4"]["variant_of"] == {"id": str(q1), "group_id": str(l1), "status": "pending"}


# ── K11: PT5, age and the two counts (a; W18) ─────────────────────────────

def test_pg_k11_age_and_the_counts_beside_pt3(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            w = await walk_w1(env, "W18")
            lid = await env.lobby()
            p = uuid.uuid4()
            await env.ex("INSERT INTO match_report_quarantine (id, mode, reason, http_status, group_id,"
                         " photon_room_id, payload, created_at) VALUES (:i, 'ffa', 'lobby_completed', 409, :g,"
                         " :r, CAST('{}' AS JSONB), now() - make_interval(hours => 2))",
                         {"i": p, "g": lid, "r": room("K11p", 1)})
            await env.ex("INSERT INTO match_report_quarantine (mode, reason, http_status, group_id, photon_room_id,"
                         " payload, status, created_at, reviewed_at) VALUES ('ffa', 'lobby_completed', 409, :g,"
                         " :r, CAST('{}' AS JSONB), 'discarded', now() - make_interval(hours => 3),"
                         " now() - make_interval(secs => 60))", {"g": lid, "r": room("K11r", 1)})
            return w, p, ok(await env.v2("ffa", lid)), ok(await env.v2("ffa", w["lid"]))
    w, p, va, v18 = run(body())
    age = cap_of(va, p)["pt5"]["age_s"]
    assert 7200 - 120 <= age <= 7200 + 120, age
    assert 7200 - 120 <= va["oldest_age_s"] <= 7200 + 120
    q = cap_of(v18, w["q1"])
    assert q["pt5"]["c1"] == 0
    assert q["pt5"]["c1_label"].startswith("Rated results for these players RECEIVED after this capture: 0.")
    assert "zero is not a safety signal" in q["pt5"]["c1_label"]
    assert q["pt5"]["c2"] == 1
    assert len(q["pt3"]["rows"]) == 4 and q["pt3"]["read"] == "4 of 4 read"


# ── K12: no automatic acceptance (static, per function span) ──────────────

def _enclosing(lineno):
    best = None
    for node in TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and node.lineno <= lineno <= node.end_lineno:
            best = node.name
    return best


def _writes_to(pattern):
    out = []
    for n in ast.walk(TREE):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            for _ in re.finditer(pattern, n.value, re.I):
                out.append(_enclosing(n.lineno))
    return sorted(out, key=str)


def test_k12_the_quarantine_table_is_written_only_by_the_capture_and_the_two_admin_routes():
    assert _writes_to(r"update\s+match_report_quarantine") == ["admin_accept_quarantine", "admin_discard_quarantine"]
    assert _writes_to(r"insert\s+into\s+match_report_quarantine") == ["_quarantine_report"] * 3
    assert _writes_to(r"delete\s+from\s+match_report_quarantine") == []
    assert "match_report_quarantine" not in open(MODELS_SRC, encoding="utf-8").read()
    spans = set(ROUTES) | {"_triage_read_txn", "_triage_group_view"}
    spans |= {n.name for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
              and n.name.lower().startswith("_triage")}
    for name in sorted(spans):
        node = next(n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    and n.name == name)
        assert [s for s in _strings(node) if WRITE.search(s)] == [], name
    assert [k for k, v in _triage_sql_constants().items() if WRITE.search(v)] == []


# ── K13e (server half): the D1 pass is finite over a moving tail (W28) ────

def test_pg_k13e_a_d1_pass_ends_within_its_page_bound(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            lid = await env.lobby()
            await env.exmany("INSERT INTO match_report_quarantine (mode, reason, http_status, group_id,"
                             " photon_room_id, payload, created_at) VALUES ('ffa', 'lobby_completed', 409, :g, :r,"
                             " CAST('{}' AS JSONB), :c)",
                             [{"g": lid, "r": room(f"W28c{n}", 1), "c": at(n)} for n in range(900)])
            added = {"n": 0}

            async def tail():
                base = added["n"]
                added["n"] += 500
                await env.exmany("INSERT INTO match_report_quarantine (mode, reason, http_status, group_id,"
                                 " photon_room_id, payload) VALUES ('ffa', 'lobby_completed', 409, :g, :r,"
                                 " CAST('{}' AS JSONB))",
                                 [{"g": lid, "r": room(f"W28t{base + n}", 1)} for n in range(500)])

            first = ok(await env.d1())
            hw, size, pages, seen = first["hw"], first["page_size"], 1, [r["id"] for r in first["rows"]]
            page = first["rows"]
            while len(page) >= size and pages < 20:
                await tail()                         # 500 new captures commit between page requests
                last = page[-1]
                page = ok(await env.d1(hw=hw, after_at=last["created_at"], after_id=last["id"]))["rows"]
                seen.extend(r["id"] for r in page)
                pages += 1
            cohort = await env.scalar("SELECT COUNT(*) FROM match_report_quarantine WHERE created_at <= :h",
                                      {"h": datetime.fromisoformat(hw)})
            return first, pages, seen, cohort
    first, pages, seen, cohort = run(body())
    assert first["totals"]["pending"] == 900 and first["page_size"] == 500
    assert pages <= math.ceil((900 + 30) / 500) + 1, pages     # ceil((P + 30) / 500) + 1, W28
    assert len(seen) == len(set(seen)) == cohort == 900


# ── K15 / K15b: no SQL after the COMMIT; the seal itself ──────────────────

def test_pg_k15_no_statement_runs_after_the_commit(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            w = await walk_w13(env)
            before = await env.checksums(TEN)
            database.post_commit_seal_stats["refused"] = 0
            rs = [await env.v1(), await env.v2("ffa", w["lid"]), await env.d1()]
            return rs, before, await env.checksums(TEN), database.post_commit_seal_stats["refused"]
    rs, before, after, refused = run(body())
    assert [r.status_code for r in rs] == [200, 200, 200], [r.text[:300] for r in rs]
    assert refused == 0
    assert before == after


def test_pg_k15b_the_seal_refuses_each_path_before_the_statement_is_sent(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            await walk_w1(env, "K15b")
            await env.ex("INSERT INTO ffa_bets (id, amount) VALUES (:i, 5)", {"i": uuid.uuid4()})
            for maker in (database.async_session, database.release_session):
                async with maker() as s:              # warm both pools before the seal is armed
                    await s.execute(text("SELECT 1"))
                    await s.commit()
            before = await env.checksums(TEN)
            database.post_commit_seal_stats["refused"] = 0
            seen = {}
            write = "UPDATE players SET gold_earned = gold_earned + 1"
            async with database.async_session() as db:
                async def read(h):
                    return await h.read("SELECT COUNT(*) AS n FROM players")

                async def build(rows):
                    for path in ("request session", "own async_session", "release_engine"):
                        try:
                            if path == "request session":
                                await db.execute(text(write))
                                await db.commit()
                            else:
                                maker = database.async_session if path == "own async_session" else database.release_session
                                async with maker() as s2:
                                    await s2.execute(text(write))
                                    await s2.commit()
                            seen[path] = "SENT"
                        except database.PostCommitSealed:
                            seen[path] = "refused"
                        except Exception as e:
                            seen[path] = f"other: {type(e).__name__}: {e}"
                    return rows

                await main._triage_read_txn(db, read, build)
            return seen, before, await env.checksums(TEN), database.post_commit_seal_stats["refused"]
    seen, before, after, refused = run(body())
    assert seen == {"request session": "refused", "own async_session": "refused", "release_engine": "refused"}
    assert refused >= 3
    assert before == after


# ── K16 / K16b: PT1's wording, and receipt order (W31, W34) ──────────────

def test_pg_k16_pt1_is_raw_arithmetic_with_the_fixed_statement(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            lid, q1, q2 = await walk_w31(env)
            return ok(await env.v2("ffa", lid)), q1, q2, ok(await env.v1())
    v, q1, q2, v1 = run(body())
    statement = ("Receipt order and the report's own number. The same values arise when this capture is a "
                 "distinct later game and when it is a second account of a settled game (section 0.5, "
                 "histories X and Y). Never acceptance or override permission.")
    for q, n in ((q1, 3), (q2, 4)):
        pt1 = cap_of(v, q)["pt1"]
        assert set(pt1) == {"r", "t", "d", "line", "statement"}
        assert (pt1["r"], pt1["t"], pt1["d"]) == (n, n, 1)
        assert pt1["line"] == f"rows received before this capture: {n}; this report's own game number: {n}; r + 1 - t = 1"
        assert pt1["statement"] == statement
        for value in pt1.values():
            assert not re.search(r"counter|drift|behind|ahead|one side", str(value), re.I), value
    for resp in (v, v1):
        assert [k for k in keys_of(resp) if re.search(r"accept|discard|override|action|suggest", k, re.I)] == []


def test_pg_k16b_pt1_counts_settlements_by_their_receipt_time(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            lid = await env.lobby(games_played=3)
            await env.ffa_settle(lid, 1, "W34", ACC_A, 1, 1, 10)
            await env.ffa_settle(lid, 2, "W34", ACC_A, 1, 1, 20)
            await env.ffa_settle(lid, 3, "W34", ACC_A, 1, 1, 50, created=30)   # begun at 30, received at 50
            q = await env.ffa_capture(lid, room("W34", 5), ACC_A, 1, 2, 40, reason="ffa_game_number_mismatch")
            l31, q1, q2 = await walk_w31(env)
            return ok(await env.v2("ffa", lid)), q, ok(await env.v2("ffa", l31)), q1, q2
    v, q, v31, q1, q2 = run(body())
    pt1 = cap_of(v, q)["pt1"]
    assert (pt1["r"], pt1["t"], pt1["d"]) == (2, 5, -2)
    assert pt1["line"] == "rows received before this capture: 2; this report's own game number: 5; r + 1 - t = -2"
    assert [(cap_of(v31, x)["pt1"]["r"], cap_of(v31, x)["pt1"]["d"]) for x in (q1, q2)] == [(3, 1), (4, 1)]


# ── K18: the team quota (W27) ─────────────────────────────────────────────

def test_pg_k18_a_team_group_at_quota_is_listed_and_the_51st_keeps_no_row(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            s = uuid.uuid4()
            await env.ex("INSERT INTO team_series (id, status, t1_series_wins, t2_series_wins, completed_at)"
                         " VALUES (:i, 'completed', 2, 1, now())", {"i": s})
            await env.exmany("INSERT INTO match_report_quarantine (mode, reason, http_status, group_id,"
                             " photon_room_id, payload, created_at) VALUES ('team', 'series_completed', 400, :g,"
                             " :r, CAST('{}' AS JSONB), :c)",
                             [{"g": s, "r": room(f"W27q{n}", 1), "c": at(n)} for n in range(50)])
            out = await env.real_capture(mode="team", reason="series_completed", status_code=400,
                                         payload={"photon_room_id": room("W27x", 1)}, group_id=s,
                                         photon_room_id=room("W27x", 1))
            n = await env.scalar("SELECT COUNT(*) FROM match_report_quarantine WHERE group_id = :g", {"g": s})
            return s, out, n, ok(await env.v1()), ok(await env.d1())
    s, out, n, v1, d1 = run(body())
    assert out == "quota" and n == 50
    assert v1["header"]["groups_at_quota"] == [{"mode": "team", "group_id": str(s), "pending": 50}]
    assert d1["totals"]["at_quota"] == [{"mode": "team", "group": str(s), "pending": 50}]
    g = v1["page"]["groups"][0]
    assert (g["mode"], g["pending"], g["at_quota"]) == ("team", 50, True)


def test_k18_the_team_caller_answers_400_whatever_the_capture_returns():
    raises = [n for n in ast.walk(TREE) if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)
              and re.match(r"HTTPException\(400, f['\"]team_series is ", ast.unparse(n.exc))]
    assert len(raises) == 1
    raise_node = raises[0]
    parents = [n for n in ast.walk(TREE) if isinstance(getattr(n, "body", None), list) and raise_node in n.body]
    assert len(parents) == 1
    body = parents[0].body
    before = body[:body.index(raise_node)]
    calls = [c for stmt in before for c in ast.walk(stmt)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "_quarantine_report"]
    assert len(calls) == 1
    holder = [s for stmt in before for s in ast.walk(stmt) if isinstance(s, ast.Expr)
              and isinstance(s.value, ast.Await) and s.value.value is calls[0]]
    assert len(holder) == 1, "the capture's outcome is bound to something: the 400 would no longer be unconditional"


# ── K19: team PT2 comes from team_series ──────────────────────────────────

def test_pg_k19_a_team_group_reads_its_series_and_no_lobby(monkeypatch):
    async def body():
        async with Env(monkeypatch) as env:
            s = uuid.uuid4()
            await env.ex("INSERT INTO team_series (id, status, t1_series_wins, t2_series_wins, created_at,"
                         " completed_at) VALUES (:i, 'completed', 2, 1, :c, :d)", {"i": s, "c": at(0), "d": at(900)})
            await env.capture(mode="team", reason="series_completed", group=s, room_id=room("K19", 1),
                              payload={"photon_room_id": room("K19", 1)}, created=1000, http=400)
            stmts = []

            def rec(conn, cursor, statement, parameters, context, executemany):
                stmts.append(statement)

            event.listen(database.engine.sync_engine, "before_cursor_execute", rec)
            try:
                v = ok(await env.v2("team", s))
            finally:
                event.remove(database.engine.sync_engine, "before_cursor_execute", rec)
            return v, stmts
    v, stmts = run(body())
    assert v["pt2"]["series"] == {"status": "completed", "score": "2-1", "created_at": at(0).isoformat(),
                                  "completed_at": at(900).isoformat(), "invalidated_at": None}
    assert "lobby" not in v["pt2"]
    assert stmts and not [s for s in stmts if "ffa_lobbies" in s]
    assert [s for s in stmts if "team_series" in s]


# ── pins: the quota the view reports is the capture's; the routes exist ──

def test_the_view_reports_the_captures_own_quota():
    assert main._TRIAGE_QUOTA == 50
    assert re.findall(r"int\(_pending\)\s*>=\s*(\d+)", inspect.getsource(main._quarantine_report)) == ["50"]


def test_the_three_routes_are_registered_on_the_app():
    want = {"/api/v1/admin/quarantine/triage": main.admin_quarantine_triage,
            "/api/v1/admin/quarantine/triage/{mode}/{group_id}": main.admin_quarantine_triage_group,
            "/api/v1/internal/quarantine/digest": main.internal_quarantine_digest}
    got = {r.path: r for r in main.app.routes if getattr(r, "path", None) in want}
    assert set(got) == set(want)
    for path, fn in want.items():
        assert got[path].endpoint is fn and got[path].methods == {"GET"}
