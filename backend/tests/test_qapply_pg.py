"""QAPPLY-1 on live PostgreSQL: an admin's Accept of a held FFA report applies
the game by replaying the held body through submit_ffa_match under the
held-report replay (_qapply_run), and Credit pays its XP and gold without
ratings.

The cases run in cf_pg's pooled case schemas through cf_asm.Env (the report
route's own harness: unsigned reports, the steam session check a no-op).
Held rows are made by the report route itself: a report of a lobby that was
closed is captured by _ffa_record_and_refuse, as on a live server.

QAPPLY_TEST_PG_DSN names the database (postgresql+asyncpg://...), else the
harness's own CF_TEST_PG_DSN (cf_pg.DSN) does; with neither, every live case
FAILS by name. QAPPLY_TEST_PG_OPTOUT=1 waives them deliberately.
The checks without a database (T1, W1, H1, the A8 census, L1's word) run
regardless.

Each check's id leads its test's name; each has one mutant (an edit to a copy
of the file it changes), recorded with its outcome by the lane's notes.
"""

import ast
import asyncio
import contextlib
import datetime as _dt
import hashlib
import hmac
import importlib.util
import json
import os
import subprocess
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import cf_asm  # noqa: E402
import cf_pg  # noqa: E402
import main  # noqa: E402
import modlog  # noqa: E402
import schemas  # noqa: E402
from sqlalchemy import text  # noqa: E402

DSN_VAR = "QAPPLY_TEST_PG_DSN"
OPTOUT_VAR = "QAPPLY_TEST_PG_OPTOUT"
_DSN = (os.environ.get(DSN_VAR) or "").replace("postgresql+asyncpg://", "postgresql://")
if _DSN and not cf_pg.DSN:
    # cf_pg and cf_pool read cf_pg.DSN when a case is made.
    cf_pg.DSN = _DSN
# The cases run on cf_pg's pooled schemas, so the harness's own database
# serves them when this file's variable is unset (the seats export it).
_DSN = _DSN or cf_pg.DSN

# The lane's base: settlement as it stood before the awards helper (S1).
LANE_BASE_COMMIT = "a82771f82db558332392f40518c87c43fbe3d6d9"
MAIN_SRC = os.path.join(HERE, "..", "api", "main.py")

ADMIN = str(cf_asm.STEAM_BASE + 999_901)
SECRET = "qapply-admin-key-for-tests"
T = main._QAPPLY_TEXTS


def _require_live_pg():
    if _DSN and cf_pg._asyncpg is not None:
        return
    if os.environ.get(OPTOUT_VAR) == "1":
        pytest.skip("%s is unset and %s=1: the live cases are waived." % (DSN_VAR, OPTOUT_VAR))
    pytest.fail("%s is unset (or asyncpg is missing), so no QAPPLY-1 live case ran. Point it at a "
                "throwaway database, or set %s=1 to waive them deliberately." % (DSN_VAR, OPTOUT_VAR))


def run_env(monkeypatch, body):
    _require_live_pg()

    async def go():
        async with cf_pg.case("qap") as (c, sm):
            env = cf_asm.Env(c, sm, monkeypatch)
            try:
                monkeypatch.setattr(main, "ADMIN_HMAC_SECRET", SECRET)
                await env.conn.execute("INSERT INTO admin_users (steam_id) VALUES ($1)"
                                       " ON CONFLICT DO NOTHING", ADMIN)
                await body(env)
            finally:
                env.close()
    asyncio.run(go())


# ── the routes ─────────────────────────────────────────────────────────────

def sig(action, target):
    return hmac.new(SECRET.encode(), main._admin_canonical(ADMIN, action, target).encode(),
                    hashlib.sha256).hexdigest()


async def accept(env, qid, *, word="quarantine_action", note=None):
    req = main._AdminQuarantineReq(admin_steam_id=ADMIN, hmac_signature=sig(word, qid), note=note)

    async def go():
        async with env.sm() as db:
            return await main.admin_accept_quarantine(qid, req, db)
    return await env._call(go)


async def credit(env, qid, *, word="quarantine_credit", note=None):
    req = main._AdminQuarantineReq(admin_steam_id=ADMIN, hmac_signature=sig(word, qid), note=note)

    async def go():
        async with env.sm() as db:
            return await main.admin_credit_quarantine(qid, req, db)
    return await env._call(go)


async def discard(env, qid):
    req = main._AdminQuarantineReq(admin_steam_id=ADMIN, hmac_signature=sig("quarantine_action", qid))

    async def go():
        async with env.sm() as db:
            return await main.admin_discard_quarantine(qid, req, db)
    return await env._call(go)


async def listing(env):
    async def go():
        async with env.sm() as db:
            return await main.admin_list_quarantine(admin_steam_id=ADMIN,
                                                    hmac_signature=sig("quarantine", "list"), db=db)
    ans = await env._call(go)
    assert ans.status == 200, ("the list answers", ans)
    return {r["id"]: r for r in ans.body["reports"]}


# ── fixtures ───────────────────────────────────────────────────────────────

def res(lob):
    return {lob.sids[0]: (5, 10), lob.sids[1]: (3, 7), lob.sids[2]: (2, 5), lob.sids[3]: (1, 2)}


async def played(env, *, ranked=True, games=1):
    """A non-assembly lobby of four with `games` games recorded by the route."""
    lob = await env.lobby(4, gated=False, ranked=ranked)
    for g in range(1, games + 1):
        a = await env.report(lob, g, res(lob))
        assert a.status == 200, ("fixture: game %d recorded" % g, a)
    return lob


async def close(env, lob, status="completed"):
    await env.conn.execute("UPDATE ffa_lobbies SET status = $2 WHERE id = $1", lob.lid, status)


async def held(env, lob, g, *, results=None):
    """Report game g of `lob` (closed or ahead): the route holds it; its id."""
    a = await env.report(lob, g, results or res(lob))
    assert a.status != 200, ("fixture: game %d held" % g, a)
    qid = await env.conn.fetchval(
        "SELECT id FROM match_report_quarantine WHERE group_id = $1 AND photon_room_id LIKE $2"
        "   AND status = 'pending'", lob.lid, "%%_r%d" % g)
    assert qid is not None, ("fixture: game %d held row" % g, a)
    return str(qid)


async def closed_held(env, *, ranked=True, status="completed"):
    lob = await played(env, ranked=ranked)
    await close(env, lob, status)
    return lob, await held(env, lob, 2)


async def now(env):
    return await env.conn.fetchval("SELECT clock_timestamp()")


async def anchor(env, lob):
    return await env.conn.fetchval(
        "SELECT GREATEST(l.created_at, (SELECT MAX(m.ended_at) FROM ffa_matches m WHERE m.lobby_id = l.id))"
        "  FROM ffa_lobbies l WHERE l.id = $1", lob.lid)


async def set_received(env, qid, at):
    await env.conn.execute("UPDATE match_report_quarantine SET created_at = $2 WHERE id = $1",
                           uuid.UUID(qid), at)


async def other_game(conn, pids, *, at, ranked=True, invalidated=False, before=None, after=None):
    """One FFA game of a lobby of its own that ended at `at`, for `pids`.
    `conn` is an asyncpg connection or a SQLAlchemy session."""
    lid, mid = uuid.uuid4(), uuid.uuid4()
    stmts = [
        ("INSERT INTO ffa_lobbies (id, status, photon_room_id, region, player_count, member_ids,"
         "  created_at, host_player_id, is_ranked, games_played)"
         " VALUES (CAST(:l AS uuid), 'completed', :room, 'eu', :n, CAST(:pids AS uuid[]),"
         "         CAST(:at AS timestamptz) - interval '10 minutes', CAST(:h AS uuid), :rk, 1)",
         {"l": str(lid), "room": "ffa_qx%s" % lid.hex[:10], "n": len(pids),
          "pids": [str(p) for p in pids], "at": at, "h": str(pids[0]), "rk": ranked}),
        ("INSERT INTO ffa_matches (id, lobby_id, photon_room_id, player_count, winner_id, reported_by,"
         "  ended_at, created_at, invalidated_at, game_number)"
         " VALUES (CAST(:m AS uuid), CAST(:l AS uuid), :room, :n, CAST(:w AS uuid), CAST(:w AS uuid),"
         "         CAST(:at AS timestamptz), CAST(:at AS timestamptz),"
         "         CASE WHEN :inv THEN CAST(:at AS timestamptz) + interval '1 minute' END, 1)",
         {"m": str(mid), "l": str(lid), "room": "ffa_qx%s_r1" % lid.hex[:10], "n": len(pids),
          "w": str(pids[0]), "at": at, "inv": invalidated}),
    ]
    for i, p in enumerate(pids):
        stmts.append((
            "INSERT INTO ffa_match_players (match_id, player_id, slot, placement, rounds_won, points_total,"
            "  kills, rating_before, rating_after)"
            " VALUES (CAST(:m AS uuid), CAST(:p AS uuid), :s, :pl, :r, :pt, 0, :b, :a)",
            {"m": str(mid), "p": str(p), "s": i, "pl": i + 1, "r": 5 if i == 0 else 0, "pt": 10 - i,
             "b": None if before is None else before[i], "a": None if after is None else after[i]}))
    if hasattr(conn, "fetchval"):
        for sql, args in stmts:
            await conn.execute(_asyncpg_sql(sql), *_asyncpg_args(sql, args))
    else:
        for sql, args in stmts:
            await conn.execute(text(sql), args)
    return mid


def _names(sql):
    import re
    return re.findall(r"(?<!:):([a-z]+)\b", sql)


def _asyncpg_sql(sql):
    import re
    order = []
    for n in _names(sql):
        if n not in order:
            order.append(n)
    return re.sub(r"(?<!:):([a-z]+)\b", lambda m: "$%d" % (order.index(m.group(1)) + 1), sql)


def _asyncpg_args(sql, args):
    order = []
    for n in _names(sql):
        if n not in order:
            order.append(n)
    return [args[n] for n in order]


async def tables(env):
    """Every table both actions can write, as counts and sums."""
    q = {
        "matches": "SELECT count(*)::text FROM ffa_matches",
        "seats": "SELECT count(*)::text FROM ffa_match_players",
        "ledger": "SELECT count(*)::text || ':' || COALESCE(sum(amount), 0)::text FROM gold_transactions",
        "players": "SELECT COALESCE(sum(total_xp), 0)::text || ':' || COALESCE(sum(gold_earned), 0)::text"
                   "    || ':' || COALESCE(sum(ffa_xp_earned), 0)::text FROM players",
        "ratings": "SELECT count(*)::text || ':' || COALESCE(sum(rating), 0)::text"
                   "    || ':' || COALESCE(sum(games_played), 0)::text FROM glicko_ratings_ffa",
        "records": "SELECT count(*)::text FROM admin_actions",
        "held": "SELECT COALESCE(string_agg(id::text || ':' || status || ':' || COALESCE(reviewed_at::text, '-'),"
                "  ',' ORDER BY id), '') FROM match_report_quarantine",
        "journal": "SELECT count(*)::text FROM ffa_report_journal",
        "lobbies": "SELECT COALESCE(string_agg(id::text || ':' || status || ':' || games_played::text,"
                   "  ',' ORDER BY id), '') FROM ffa_lobbies",
        "queue": "SELECT count(*)::text FROM ffa_queue",
        "leases": "SELECT count(*)::text FROM queue_leases",
        "bets": "SELECT count(*)::text FROM ffa_bets",
    }
    return {k: await env.conn.fetchval(v) for k, v in q.items()}


async def status_of(env, qid):
    return await env.conn.fetchval("SELECT status FROM match_report_quarantine WHERE id = $1",
                                   uuid.UUID(qid))


async def game_rows(env, lob, g):
    return await env.conn.fetchval("SELECT count(*) FROM ffa_matches WHERE lobby_id = $1 AND game_number = $2",
                                   lob.lid, g)


async def later_for(env, lob, slot=0, **kw):
    return await other_game(env.conn, [lob.pids[slot]], at=kw.pop("at", None) or await now(env), **kw)


# ── A1: the replay writes what a network report writes ─────────────────────

async def _game_state(env, lob, g):
    """Game g of `lob`: every row it wrote, keyed by slot, ids and stamps out."""
    slot = {p: i for i, p in enumerate(lob.pids)}
    m = dict(await env.conn.fetchrow("SELECT * FROM ffa_matches WHERE lobby_id = $1 AND game_number = $2",
                                     lob.lid, g))

    def clean(r):
        return {k: v for k, v in dict(r).items()
                if not isinstance(v, (uuid.UUID, _dt.datetime)) and k not in ("id", "photon_room_id")}
    seats = {slot[r["player_id"]]: clean(r) for r in await env.conn.fetch(
        "SELECT * FROM ffa_match_players WHERE match_id = $1", m["id"])}
    ratings = {slot[r["player_id"]]: clean(r) for r in await env.conn.fetch(
        "SELECT * FROM glicko_ratings_ffa WHERE player_id = ANY($1::uuid[])", lob.pids)}
    players = {slot[r["id"]]: tuple(r[k] for k in ("total_xp", "gold_earned", "ffa_xp_earned", "ffa_gold_earned"))
               for r in await env.conn.fetch("SELECT * FROM players WHERE id = ANY($1::uuid[])", lob.pids)}
    ledger = sorted((slot[r["player_id"]], r["reason"], r["amount"]) for r in await env.conn.fetch(
        "SELECT player_id, reason, amount FROM gold_transactions WHERE reference_id = $1", str(m["id"])))
    return {"match": clean(m), "winner": slot[m["winner_id"]], "seats": seats, "ratings": ratings,
            "players": players, "ledger": ledger, "ended_at": m["ended_at"], "id": m["id"]}


def test_a1_accept_writes_what_a_network_report_writes(monkeypatch):
    async def body(env):
        # Lobby B: game 2 by the network, 90 s after game 1 (the pace bound binds).
        lob_b = await played(env)
        await env.conn.execute("UPDATE ffa_matches SET ended_at = ended_at - interval '90 seconds',"
                               " created_at = created_at - interval '90 seconds' WHERE lobby_id = $1",
                               lob_b.lid)
        await env.conn.execute("UPDATE ffa_lobbies SET created_at = created_at - interval '120 seconds'"
                               " WHERE id = $1", lob_b.lid)
        anchor_b = await anchor(env, lob_b)
        a = await env.report(lob_b, 2, res(lob_b))
        assert a.status == 200, ("A1 twin recorded", a)
        b2 = await _game_state(env, lob_b, 2)
        elapsed = (b2["ended_at"] - anchor_b).total_seconds()
        assert main._ffa_paid_battles(24, elapsed, 4) < 24, ("A1 the pace bound binds", elapsed)
        # Lobby A: game 2 held after the lobby closed, received at the same distance.
        lob_a = await played(env)
        await close(env, lob_a)
        qid = await held(env, lob_a, 2)
        anchor_a = await anchor(env, lob_a)
        await set_received(env, qid, anchor_a + (b2["ended_at"] - anchor_b))
        verdict = (await listing(env))[qid]
        assert (verdict["can_accept"], verdict["can_credit"]) == (True, False), ("A1 gate passes", verdict)
        ans = await accept(env, qid)
        assert ans.status == 200 and ans.body["applied"] is True, ("A1 accept", ans)
        a2 = await _game_state(env, lob_a, 2)
        assert ans.body["match_id"] == str(a2["id"]), ("A1 match id", ans)
        assert a2["ended_at"] == anchor_a + (b2["ended_at"] - anchor_b), ("A1 replay clock", a2["ended_at"])
        for k in ("match", "winner", "seats", "ratings", "players", "ledger"):
            assert a2[k] == b2[k], ("A1 " + k, a2[k], b2[k])
        assert await status_of(env, qid) == "accepted"
    run_env(monkeypatch, body)


# ── A2: a settle that commits while Accept waits on a player ───────────────

def test_a2_a_settle_committed_while_accept_waits_blocks_it(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        before = await tables(env)
        async with env.sm() as s:
            await s.execute(text("SELECT 1 FROM players WHERE id = :p FOR NO KEY UPDATE"), {"p": lob.pids[0]})
            task = asyncio.create_task(accept(env, qid))
            await asyncio.sleep(1.5)
            assert not task.done(), ("A2 accept waits on the player's lock", task)
            await other_game(s, [lob.pids[0]], at=await now(env))
            await s.commit()
        ans = await asyncio.wait_for(task, 15)
        assert ans.status == 409 and ans.body == T["later"].format(n=1), ("A2 refused", ans)
        after = await tables(env)
        assert {k: v for k, v in after.items() if k not in ("matches", "seats", "lobbies")} == \
            {k: v for k, v in before.items() if k not in ("matches", "seats", "lobbies")}, ("A2 nothing written",)
        assert await game_rows(env, lob, 2) == 0 and await status_of(env, qid) == "pending"
    run_env(monkeypatch, body)


# ── A3: a rating changed outside settlement ────────────────────────────────

def test_a3_a_rating_changed_outside_settlement_blocks_accept(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        await env.conn.execute("UPDATE glicko_ratings_ffa SET rating = rating + 25 WHERE player_id = $1",
                               lob.pids[0])
        before = await tables(env)
        ans = await accept(env, qid)
        assert ans.status == 409 and ans.body == T["rating"].format(n=1), ("A3 refused", ans)
        assert await tables(env) == before, "A3 nothing written"
    run_env(monkeypatch, body)


# ── A4: later casual and invalidated games count ───────────────────────────

def test_a4_a_later_casual_game_and_a_later_invalidated_game_each_block(monkeypatch):
    async def body(env):
        for kind in ("casual", "invalidated"):
            lob, qid = await closed_held(env)
            if kind == "casual":
                await later_for(env, lob, ranked=False)
            else:
                r = await env.conn.fetchval("SELECT rating FROM glicko_ratings_ffa WHERE player_id = $1",
                                            lob.pids[0])
                await later_for(env, lob, invalidated=True, before=[r], after=[r])
            before = await tables(env)
            ans = await accept(env, qid)
            assert ans.status == 409 and ans.body == T["later"].format(n=1), ("A4 " + kind, ans)
            assert await tables(env) == before, ("A4 nothing written", kind)
    run_env(monkeypatch, body)


# ── A5: a game between the lobby's previous game and the receipt ───────────

def test_a5_a_game_after_the_lobbys_previous_game_blocks_accept(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        t = await anchor(env, lob)
        await set_received(env, qid, t + _dt.timedelta(seconds=300))
        await later_for(env, lob, at=t + _dt.timedelta(seconds=100), ranked=False)
        ans = await accept(env, qid)
        assert ans.status == 409 and ans.body == T["later"].format(n=1), ("A5 refused", ans)
        assert await game_rows(env, lob, 2) == 0
    run_env(monkeypatch, body)


# ── A6: game 3 before game 2 ───────────────────────────────────────────────

def test_a6_game_3_before_game_2_names_game_2_then_both_apply_in_order(monkeypatch):
    async def body(env):
        lob = await played(env)
        await close(env, lob)
        q2 = await held(env, lob, 2)
        q3 = await held(env, lob, 3)
        ans = await accept(env, q3)
        assert ans.status == 409 and ans.body == T["ahead"].format(tail=3, next=2), ("A6 names game 2", ans)
        assert "Apply game 2 of this lobby first." in ans.body
        assert (await accept(env, q2)).status == 200, "A6 game 2 applies"
        ans = await accept(env, q3)
        assert ans.status == 200, ("A6 game 3 applies", ans)
        rows = await env.conn.fetch("SELECT game_number, photon_room_id FROM ffa_matches WHERE lobby_id = $1"
                                    " ORDER BY game_number", lob.lid)
        assert [(r["game_number"], r["photon_room_id"][-3:]) for r in rows] == [(1, "_r1"), (2, "_r2"), (3, "_r3")]
    run_env(monkeypatch, body)


# ── A7: words outside the set, and team rows ───────────────────────────────

NEVER_WORDS = ("score_shape_mismatch", "v1_canonical_downgrade", "ffa_game_contradiction",
               "ffa_room_other_lobby", "ffa_replay_roster_mismatch", "late_reporter", "left_reporter",
               "lag_reporter", "ffa_lobby_no_roster", "lobby_game_limit", "lobby_open", "lobby_active")
TEAM_WORDS = ("series_completed", "series_abandoned")


def test_a7_every_word_outside_the_set_and_a_team_row_are_refused_by_both(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        before = await tables(env)
        for word in NEVER_WORDS:
            await env.conn.execute("UPDATE match_report_quarantine SET reason = $2 WHERE id = $1",
                                   uuid.UUID(qid), word)
            for act in (accept, credit):
                ans = await act(env, qid)
                assert ans.status == 409 and ans.body == T["word"], ("A7", word, act.__name__, ans)
            assert await tables(env) == before, ("A7 nothing written", word)
        for word in TEAM_WORDS:
            await env.conn.execute("UPDATE match_report_quarantine SET mode = 'team', reason = $2 WHERE id = $1",
                                   uuid.UUID(qid), word)
            for act in (accept, credit):
                ans = await act(env, qid)
                assert ans.status == 409 and ans.body == T["team"], ("A7 team", word, act.__name__, ans)
        assert await tables(env) == before, "A7 nothing written (team)"
    run_env(monkeypatch, body)


# ── A8: the body's refusals under the replay ───────────────────────────────
# One case per refusal of the body that a replay can reach with a served word
# and a closed lobby (derived from the body: the arms after the held row's own
# checks): (arm, how the case makes it, status, sentence).

A8_ARMS = (
    ("lobby not found", "lobby", 404, "no_lobby"),
    ("player not registered", "account", 404, "account"),
    ("roster does not bind", "roster", 403, "roster"),
    ("score shape (capture site)", "shape", 409, "shape"),
    ("lobby status not served (capture site)", "status", 409, "lobby_state"),
    # The stored-body reader refuses this one before the body runs (its 422
    # is not reached under the replay); the held check names it, with 409.
    ("leave figure missing", "leave", 409, "leave_figure"),
    ("recorded game contradicts (capture site)", "contradiction", 409, "recorded"),
)


async def _a8_make(env, lob, qid, how):
    q = uuid.UUID(qid)
    if how == "lobby":
        other = str(uuid.uuid4())
        await env.conn.execute("UPDATE match_report_quarantine SET group_id = $2::uuid,"
                               " payload = jsonb_set(payload, '{lobby_id}', to_jsonb($2::text)) WHERE id = $1",
                               q, other)
    elif how == "account":
        await env.conn.execute("UPDATE match_report_quarantine SET payload = jsonb_set(payload,"
                               " '{players,1,steam_id}', to_jsonb($2::text)) WHERE id = $1",
                               q, str(cf_asm.STEAM_BASE + 999_977))
    elif how == "roster":
        stranger = await env.conn.fetchval(
            "INSERT INTO players (id, steam_id, display_name) VALUES (gen_random_uuid(), $1, 'qap stranger')"
            " RETURNING id", str(cf_asm.STEAM_BASE + 999_978))
        await env.conn.execute("UPDATE ffa_lobbies SET member_ids[2] = $2 WHERE id = $1", lob.lid, stranger)
    elif how == "shape":
        await env.conn.execute("UPDATE match_report_quarantine SET payload = jsonb_set(payload,"
                               " '{players,0,rounds_won}', '1') WHERE id = $1", q)
    elif how == "status":
        await env.conn.execute("UPDATE ffa_lobbies SET status = 'open' WHERE id = $1", lob.lid)
    elif how == "leave":
        await env.conn.execute("UPDATE match_report_quarantine SET payload = jsonb_set(payload,"
                               " '{players,3,left_early}', 'true') WHERE id = $1", q)
    elif how == "contradiction":
        room = await env.conn.fetchval("SELECT photon_room_id FROM match_report_quarantine WHERE id = $1", q)
        mid = uuid.uuid4()
        await env.conn.execute(
            "INSERT INTO ffa_matches (id, lobby_id, photon_room_id, player_count, winner_id, reported_by,"
            "  ended_at, created_at, game_number) VALUES ($1, $2, $3, 4, $4, $4, clock_timestamp(),"
            "  clock_timestamp(), 2)", mid, lob.lid, room, lob.pids[1])
        for i, p in enumerate(lob.pids):
            await env.conn.execute(
                "INSERT INTO ffa_match_players (match_id, player_id, slot, placement, rounds_won, points_total,"
                " kills) VALUES ($1, $2, $3, $4, $5, $6, 0)", mid, p, i, 1 if i == 1 else (2 if i == 0 else i + 1),
                5 if i == 1 else 0, 9 - i)


@pytest.mark.parametrize("arm", A8_ARMS, ids=[a[1] for a in A8_ARMS])
def test_a8_each_body_refusal_answers_its_status_and_keeps_the_row_pending(arm, monkeypatch):
    name, how, status, key = arm

    async def body(env):
        lob, qid = await closed_held(env)
        await _a8_make(env, lob, qid, how)
        n_held = await env.conn.fetchval("SELECT count(*) FROM match_report_quarantine")
        row = dict(await env.conn.fetchrow("SELECT * FROM match_report_quarantine WHERE id = $1", uuid.UUID(qid)))
        before = len(env.lines)   # the setup's own network report was captured (its line stays)
        ans = await accept(env, qid)
        assert (ans.status, ans.body) == (status, T[key]), ("A8 " + name, ans)
        assert await env.conn.fetchval("SELECT count(*) FROM match_report_quarantine") == n_held, ("A8 no row made",)
        assert dict(await env.conn.fetchrow("SELECT * FROM match_report_quarantine WHERE id = $1",
                                            uuid.UUID(qid))) == row, ("A8 row unchanged", name)
        assert not [ln for ln in env.lines[before:] if ln.startswith("[QUARANTINE]")], ("A8 no capture line", name)
    run_env(monkeypatch, body)


def _tree():
    with open(MAIN_SRC, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _functions(tree):
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _calls(fn):
    return {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def test_a8_census_no_way_to_the_capture_skips_the_replay_guard():
    """R6: the ways from the report body to _quarantine_report. Its callers
    are itself, _ffa_record_and_refuse (whose replay guard stands before the
    call) and the team settle, which the FFA body never reaches."""
    fns = _functions(_tree())
    callers = sorted(name for name, fn in fns.items() if "_quarantine_report" in _calls(fn))
    assert callers == ["_ffa_record_and_refuse", "_quarantine_report", "_settle_team_report"], callers
    seen, todo = set(), ["submit_ffa_match"]
    while todo:
        f = todo.pop()
        if f in seen or f not in fns:
            continue
        seen.add(f)
        todo.extend(_calls(fns[f]))
    unguarded = sorted(c for c in callers if c in seen and c not in ("_ffa_record_and_refuse", "_quarantine_report"))
    assert unguarded == [], unguarded
    body = fns["_ffa_record_and_refuse"].body
    guard = [i for i, s in enumerate(body) if isinstance(s, ast.If) and "_QAPPLY_REPLAY.get()" in ast.unparse(s.test)
             and any(isinstance(x, ast.Raise) for x in s.body)]
    call = [i for i, s in enumerate(body) if "_quarantine_report(" in ast.unparse(s)]
    assert guard and call and guard[0] < call[0], (guard, call)


# ── A9: a held row received before T ──────────────────────────────────────

def test_a9_a_row_received_before_the_lobbys_previous_game_is_refused_by_both(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        t = await anchor(env, lob)
        await set_received(env, qid, t - _dt.timedelta(seconds=10))
        await later_for(env, lob)   # Credit would otherwise refuse: Accept could apply
        before = await tables(env)
        for act in (accept, credit):
            ans = await act(env, qid)
            assert ans.status == 409 and ans.body == T["clock"], ("A9", act.__name__, ans)
        assert await tables(env) == before, "A9 nothing written"
    run_env(monkeypatch, body)


# ── A10: a fault after the record, before the commit ───────────────────────

def test_a10_a_fault_after_the_record_leaves_nothing(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        before = await tables(env)
        real = main._modlog_write

        async def faulty(db, **kw):
            await real(db, **kw)
            if kw.get("action") == "quarantine_accept":
                raise RuntimeError("planted fault after the record")
        monkeypatch.setattr(main, "_modlog_write", faulty)
        with pytest.raises(RuntimeError, match="planted fault"):
            await accept(env, qid)
        assert await game_rows(env, lob, 2) == 0, "A10 no game row"
        assert await tables(env) == before, "A10 nothing written"
        assert await status_of(env, qid) == "pending"
    run_env(monkeypatch, body)


# ── A11: two sessions at once ──────────────────────────────────────────────

async def _pair(env, qid, first, second):
    """Hold the held row in a third session, queue `first` then `second`
    behind it, release; both answers."""
    async with env.sm() as s:
        await s.execute(text("SELECT 1 FROM match_report_quarantine WHERE id = CAST(:q AS uuid) FOR UPDATE"),
                        {"q": qid})
        t1 = asyncio.create_task(first(env, qid))
        await asyncio.sleep(0.8)
        t2 = asyncio.create_task(second(env, qid))
        await asyncio.sleep(0.8)
        await s.rollback()
    return await asyncio.wait_for(asyncio.gather(t1, t2), 30)


def test_a11_two_actions_at_once_take_effect_once(monkeypatch):
    async def body(env):
        for first, second in ((accept, accept), (discard, accept), (accept, discard), (accept, credit),
                              (credit, accept)):
            lob, qid = await closed_held(env)
            if credit in (first, second) and first is credit:
                await later_for(env, lob, slot=0, at=await anchor(env, lob) + _dt.timedelta(days=1))
            a, b = await _pair(env, qid, first, second)
            ok = [x for x in (a, b) if x.status == 200]
            assert len(ok) == 1, ("A11", first.__name__, second.__name__, a, b)
            assert a.status == 200, ("A11 the first in the queue wins", first.__name__, a, b)
            st = await status_of(env, qid)
            assert st == {"accept": "accepted", "discard": "discarded", "credit": "credited"}[first.__name__]
            n = await game_rows(env, lob, 2)
            assert n == (1 if first is accept else 0), ("A11 game rows", first.__name__, second.__name__, n)
            recs = await env.conn.fetchval("SELECT count(*) FROM admin_actions WHERE details->>'quarantine_id' = $1",
                                           qid)
            assert recs == 1, ("A11 one record", first.__name__, second.__name__, recs)
    run_env(monkeypatch, body)


# ── A12: Accept, Credit and a network report of the same body at once ──────

def test_a12_concurrent_accept_credit_and_network_report_record_once_without_long_waits(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        rep = await env.report_req(lob, 2, res(lob))
        started = {}

        async def timed(name, coro):
            t0 = asyncio.get_running_loop().time()
            try:
                return await coro
            finally:
                started[name] = asyncio.get_running_loop().time() - t0
        async with env.sm() as s:
            # The held row held by a third session: Credit, then Accept queue
            # behind it, then the network report arrives; Credit takes the
            # held row first and the lobby second, as Accept does.
            await s.execute(text("SELECT 1 FROM match_report_quarantine WHERE id = CAST(:q AS uuid) FOR UPDATE"),
                            {"q": qid})
            tasks = [asyncio.create_task(timed("credit", credit(env, qid)))]
            await asyncio.sleep(0.8)
            tasks.append(asyncio.create_task(timed("accept", accept(env, qid))))
            await asyncio.sleep(0.8)
            tasks.append(asyncio.create_task(timed("network", env.submit(rep))))
            await asyncio.sleep(0.8)
            await s.rollback()
        c, a, n = await asyncio.wait_for(asyncio.gather(*tasks), 30)
        assert max(started.values()) < 10.0, ("A12 no long wait", started)
        assert {c.status, a.status} <= {200, 409}, ("A12 answers", c, a)
        assert a.status == 200 and c.status == 409, ("A12 accept applies, credit refused", a, c)
        assert n.status != 200 or n.body, ("A12 network answered", n)
        assert await game_rows(env, lob, 2) == 1, "A12 recorded once"
        assert await env.conn.fetchval("SELECT count(*) FROM match_report_quarantine WHERE group_id = $1",
                                       lob.lid) == 1, "A12 no second held row"
        assert not [ln for ln in env.lines if "deadlock" in ln.lower()]
    run_env(monkeypatch, body)


# ── A13: readmission lobbies ───────────────────────────────────────────────

def test_a13_a_readmission_lobby_is_refused_before_its_journal(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        await env.conn.execute("UPDATE ffa_lobbies SET readmit_v1 = true WHERE id = $1", lob.lid)
        before = await tables(env)
        for act in (accept, credit):
            ans = await act(env, qid)
            assert ans.status == 409 and ans.body == T["readmit"], ("A13", act.__name__, ans)
        assert await env.conn.fetchval("SELECT count(*) FROM ffa_report_journal") == 0, "A13 nothing journaled"
        assert await tables(env) == before, "A13 nothing written"
    run_env(monkeypatch, body)


# ── A14: the LIVE and MEMORY rows of EFFECTS.tsv ───────────────────────────

def _raiser(what):
    async def f(*a, **k):
        raise RuntimeError("%s ran under the replay" % what)
    return f


def test_a14_ses_the_session_check_does_not_run_under_the_replay(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        monkeypatch.setattr(main, "_check_steam_session", _raiser("the session check"))
        ans = await accept(env, qid)
        assert ans.status == 200, ("A14-SES", ans)
    run_env(monkeypatch, body)


def test_a14_win_the_due_windows_settle_does_not_run_under_the_replay(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        monkeypatch.setattr(main, "_ffa_settle_due_windows_for_report", _raiser("the due windows settle"))
        ans = await accept(env, qid)
        assert ans.status == 200, ("A14-WIN", ans)
    run_env(monkeypatch, body)


def test_a14_exp_an_open_lobby_is_refused_and_its_live_rows_stay(monkeypatch):
    async def body(env):
        lob = await played(env)
        qid = await held(env, lob, 3)       # ahead of an active lobby: ffa_game_number_mismatch
        assert await env.conn.fetchval("SELECT reason FROM match_report_quarantine WHERE id = $1",
                                       uuid.UUID(qid)) == "ffa_game_number_mismatch"
        await env.conn.execute("UPDATE ffa_lobbies SET short_started_at = created_at, bets_disabled = true"
                               " WHERE id = $1", lob.lid)
        snap, before = await env.snapshot(), await tables(env)
        for act in (accept, credit):
            ans = await act(env, qid)
            assert ans.status == 409 and ans.body == T["lobby_open"], ("A14-EXP", act.__name__, ans)
        assert await env.snapshot() == snap and await tables(env) == before, "A14-EXP nothing written"
    run_env(monkeypatch, body)


def test_a14_mem_the_ladder_note_stays_in_accepts_own_session(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        real = main._qapply_finish
        seen = {}

        async def noting(db, ctx, **kw):
            main._note_ladder_achievement_gold(db, lob.pids[0], 5)
            seen["in"] = main._ladder_achievement_gold(db, lob.pids[0])
            return await real(db, ctx, **kw)
        monkeypatch.setattr(main, "_qapply_finish", noting)
        assert (await accept(env, qid)).status == 200
        async with env.sm() as db:
            assert (seen["in"], main._ladder_achievement_gold(db, lob.pids[0])) == (5, 0), ("A14-MEM", seen)
    run_env(monkeypatch, body)


# ── M1: the modes ──────────────────────────────────────────────────────────

def test_m1_network_and_journal_leave_the_replay_unset_and_both_set_is_refused(monkeypatch):
    async def body(env):
        seen = []
        real = main._ffa_game_awards

        def probe(**kw):
            seen.append(main._QAPPLY_REPLAY.get())
            return real(**kw)
        monkeypatch.setattr(main, "_ffa_game_awards", probe)
        lob = await played(env)
        assert seen and all(v is None for v in seen), ("M1 network: replay unset", seen)
        await close(env, lob)
        qid = await held(env, lob, 2)
        monkeypatch.setattr(main, "_check_steam_session", _raiser("the session check"))
        monkeypatch.setattr(main, "_ffa_settle_due_windows_for_report", _raiser("the due windows settle"))
        seen.clear()
        assert (await accept(env, qid)).status == 200, "M1 accept"
        assert seen and all(v is not None and v["kind"] == "accept" for v in seen), ("M1 replay set", seen)

        ran = []
        tok = main._RDM_JOURNAL_MODE.set({"journal": True})
        try:
            with pytest.raises(RuntimeError, match="already set"):
                async with main._qapply_run({"kind": "accept"}):
                    ran.append("journal")
        finally:
            main._RDM_JOURNAL_MODE.reset(tok)
        tok = main._QAPPLY_REPLAY.set({"kind": "accept"})
        try:
            with pytest.raises(RuntimeError, match="already set"):
                async with main._qapply_run({"kind": "accept"}):
                    ran.append("replay")
            with pytest.raises(RuntimeError):
                await main._ffa_settle_report(None, None, journal={})
        finally:
            main._QAPPLY_REPLAY.reset(tok)
        assert ran == [], ("M1 the setter refused before its block", ran)
        assert main._QAPPLY_REPLAY.get() is None and main._RDM_JOURNAL_MODE.get() is None
    run_env(monkeypatch, body)


# ── S1: settlement unchanged by the helper's extraction ────────────────────

_BASE = {}


def _base_main():
    if "mod" in _BASE:
        return _BASE["mod"]
    # QAPPLY_REPO: the checkout to read the base from when this file runs
    # from a copy of the tree (a mutant's run).
    repo = os.environ.get("QAPPLY_REPO") or os.path.normpath(os.path.join(HERE, "..", ".."))
    src = subprocess.run(["git", "-C", repo, "show", LANE_BASE_COMMIT + ":backend/api/main.py"],
                         capture_output=True, check=True).stdout
    name = "main_qapply_lane_base"
    spec = importlib.util.spec_from_loader(name, loader=None, origin="lane-base/backend/api/main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        exec(compile(src, spec.origin, "exec"), mod.__dict__)
    except Exception:
        sys.modules.pop(name, None)
        raise
    _BASE["mod"] = mod
    return mod


def test_s1_the_base_and_the_lane_settle_one_fixture_alike(monkeypatch):
    base = _base_main()
    assert not hasattr(base, "_ffa_game_awards"), "S1 the base predates the helper"

    async def _no_session(request, steam_id, db):
        return None
    for name, val in (("_check_steam_session", _no_session), ("MATCH_HMAC_SECRET", ""),
                      ("ADM_PRODUCTION_ENABLED", False), ("_presence_seen", {})):
        monkeypatch.setattr(base, name, val)

    async def body(env):
        lobs = []
        for _ in range(2):
            lob = await played(env)
            # Games far apart, so the pace bound does not bind and the two
            # settles do not depend on the instant each one runs.
            await env.conn.execute("UPDATE ffa_matches SET ended_at = ended_at - interval '1 hour'"
                                   " WHERE lobby_id = $1", lob.lid)
            await env.conn.execute("UPDATE ffa_lobbies SET created_at = created_at - interval '2 hours'"
                                   " WHERE id = $1", lob.lid)
            lobs.append(lob)
        a = await env.report(lobs[0], 2, res(lobs[0]))
        rep = await env.report_req(lobs[1], 2, res(lobs[1]))

        async def go():
            async with env.sm() as db:
                out = await base.submit_ffa_match(rep, cf_asm.FakeRequest(), db)
                return out.model_dump() if hasattr(out, "model_dump") else out
        b = await env._call(go)
        assert a.status == 200 and b.status == 200, ("S1 both settled", a, b)
        lane, old = await _game_state(env, lobs[0], 2), await _game_state(env, lobs[1], 2)
        for k in ("seats", "ratings", "players", "ledger"):
            assert lane[k] == old[k], ("S1 " + k, lane[k], old[k])
    run_env(monkeypatch, body)


# ── C1: Credit pays what settlement would have paid (migration 421's pairs) ─

def test_c1_credit_reproduces_migration_421s_twelve_pairs(monkeypatch):
    import test_oct3b_credit_pg as O

    async def body(env):
        c = env.conn
        start = await now(env)
        t0 = start - _dt.timedelta(hours=10)
        t1 = t0 + _dt.timedelta(seconds=745)
        pids = [uuid.uuid4() for _ in range(6)]
        for s, p in enumerate(pids):
            await c.execute("INSERT INTO players (id, steam_id, display_name, total_xp, gold_earned)"
                            " VALUES ($1, $2, $3, $4, $5)", p, O.steam(s), "seat %d" % s, 1000 * (s + 1), 7 * s)
            await c.execute("INSERT INTO glicko_ratings_ffa (player_id, rating, rating_deviation, volatility,"
                            "  peak_rating, games_played) VALUES ($1, 1000.0, 200.0, 0.06, 1000.0, 2)", p)
        lobby = uuid.UUID(O.LOBBY)
        await c.execute("INSERT INTO ffa_lobbies (id, status, photon_room_id, region, player_count, member_ids,"
                        "  created_at, host_player_id, is_ranked, games_played, kills_tiebreak)"
                        " VALUES ($1, 'completed', 'ffa_qapc1', 'eu', 6, $2, $3, $4, true, 1, true)",
                        lobby, pids, t0, pids[0])
        g1 = uuid.uuid4()
        await c.execute("INSERT INTO ffa_matches (id, lobby_id, photon_room_id, player_count, winner_id,"
                        "  reported_by, ended_at, created_at, game_number)"
                        " VALUES ($1, $2, 'ffa_qapc1_r1', 6, $3, $3, $4, $4, 1)", g1, lobby, pids[3], t1)
        for s, p in enumerate(pids):
            await c.execute("INSERT INTO ffa_match_players (match_id, player_id, slot, placement, rounds_won,"
                            "  points_total, kills, rating_before, rating_after)"
                            " VALUES ($1, $2, $3, $4, 0, 0, 0, $5, $6)",
                            g1, p, s, O.G1[s][0], O.G1[s][1], O.RATING_AFTER_G1[s])
        received = {O.Q2: t1 + _dt.timedelta(seconds=2000), O.Q3: t1 + _dt.timedelta(seconds=4000)}
        for q in (O.Q2, O.Q3):
            await c.execute(
                "INSERT INTO match_report_quarantine (id, mode, reason, http_status, group_id, photon_room_id,"
                "  reporter_id, player_ids, payload, status, created_at)"
                " VALUES ($1, 'ffa', 'lobby_completed', 409, $2, $3, $4, $5, $6::jsonb, 'pending', $7)",
                uuid.UUID(q), lobby, O.ROOMS[q], pids[0], pids, json.dumps(O.body(q)), received[q])
        # Each player's next FFA game, later than both: its rating_before is the
        # rating game 1 left (the tier input), and it moved every stored rating.
        await other_game(c, pids, at=t1 + _dt.timedelta(hours=5),
                         before=[O.RATING_AFTER_G1[s] for s in range(6)], after=[1000.0] * 6)
        paid = {}
        for q in (O.Q2, O.Q3):
            xp0 = {r["id"]: (r["total_xp"], r["gold_earned"]) for r in await c.fetch(
                "SELECT id, total_xp, gold_earned FROM players WHERE id = ANY($1::uuid[])", pids)}
            ans = await credit(env, q)
            assert ans.status == 200, ("C1 credit", q, ans)
            got = {s: next(p for p in ans.body["players"] if p["steam_id"] == O.steam(s)) for s in range(6)}
            ledger = {(r["player_id"], r["reason"]): r["amount"] for r in await c.fetch(
                "SELECT player_id, reason, amount FROM gold_transactions WHERE reference_id = $1", q)}
            assert all(v > 0 for v in ledger.values()), ("C1 only kinds above 0", ledger)
            for s, p in enumerate(pids):
                paid[(q, s)] = (got[s]["xp"], ledger[(p, "ffa_placement")])
                row = await c.fetchrow("SELECT total_xp, gold_earned FROM players WHERE id = $1", p)
                assert row["total_xp"] - xp0[p][0] == got[s]["xp"], ("C1 XP delta", q, s)
                assert row["gold_earned"] - xp0[p][1] == got[s]["gold"] == sum(
                    v for (pp, _k), v in ledger.items() if pp == p), ("C1 gold delta = ledger", q, s)
            assert await status_of(env, q) == "credited"
        assert paid == {(q, s): O.DESIGN[q][s] for q in (O.Q2, O.Q3) for s in range(6)}, ("C1 the twelve pairs", paid)
        assert await c.fetchval("SELECT count(*) FROM ffa_matches WHERE lobby_id = $1", lobby) == 1
        assert [r["rating"] for r in await c.fetch("SELECT rating FROM glicko_ratings_ffa WHERE player_id ="
                                                   " ANY($1::uuid[])", pids)] == [1000.0] * 6, "C1 no rating moved"
    run_env(monkeypatch, body)


# ── C2..C5 ─────────────────────────────────────────────────────────────────

def test_c2_credit_is_refused_while_accept_could_apply_and_allowed_once_blocked(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        before = await tables(env)
        ans = await credit(env, qid)
        assert ans.status == 409 and ans.body == T["can_accept"], ("C2 refused", ans)
        assert await tables(env) == before
        await later_for(env, lob)
        ans = await credit(env, qid)
        assert ans.status == 200 and len(ans.body["players"]) == 4, ("C2 allowed", ans)
    run_env(monkeypatch, body)


def test_c3_every_second_action_answers_409_and_changes_nothing(monkeypatch):
    async def body(env):
        # Credit, then Credit again; then the row set back to pending by hand.
        lob, qid = await closed_held(env)
        await later_for(env, lob)
        assert (await credit(env, qid)).status == 200
        before = await tables(env)
        ans = await credit(env, qid)
        assert ans.status == 409 and ans.body == T["reviewed"], ("C3 credit twice", ans)
        await env.conn.execute("UPDATE match_report_quarantine SET status = 'pending', reviewed_at = NULL"
                               " WHERE id = $1", uuid.UUID(qid))
        before = await tables(env)
        for act in (credit, accept):
            ans = await act(env, qid)
            assert ans.status == 409 and ans.body == T["credited_before"], ("C3 receipt", act.__name__, ans)
        assert await tables(env) == before, "C3 nothing changed"
        # Accept, then Credit; Credit, then Accept.
        lob, qid = await closed_held(env)
        assert (await accept(env, qid)).status == 200
        before = await tables(env)
        ans = await credit(env, qid)
        assert ans.status == 409 and ans.body == T["reviewed"], ("C3 credit after accept", ans)
        assert await tables(env) == before
        lob, qid = await closed_held(env)
        await later_for(env, lob)
        assert (await credit(env, qid)).status == 200
        before = await tables(env)
        ans = await accept(env, qid)
        assert ans.status == 409 and ans.body == T["reviewed"], ("C3 accept after credit", ans)
        assert await tables(env) == before
    run_env(monkeypatch, body)


def test_c4_a_fault_after_credits_record_leaves_nothing(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        await later_for(env, lob)
        before = await tables(env)
        real = main._modlog_write

        async def faulty(db, **kw):
            await real(db, **kw)
            if kw.get("action") == "quarantine_credit":
                raise RuntimeError("planted fault after the record")
        monkeypatch.setattr(main, "_modlog_write", faulty)
        with pytest.raises(RuntimeError, match="planted fault"):
            await credit(env, qid)
        assert await tables(env) == before, "C4 nothing written"
    run_env(monkeypatch, body)


def test_c5_each_action_word_signs_its_own_action_only(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        before = await tables(env)
        ans = await credit(env, qid, word="quarantine_action")
        assert (ans.status, ans.body) == (403, "Bad admin signature"), ("C5 credit with accept's word", ans)
        ans = await accept(env, qid, word="quarantine_credit")
        assert (ans.status, ans.body) == (403, "Bad admin signature"), ("C5 accept with credit's word", ans)
        assert await tables(env) == before
    run_env(monkeypatch, body)


# ── G1, G2: the list ───────────────────────────────────────────────────────

def test_g1_the_lists_verdict_takes_no_row_lock(monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        async with env.sm() as s:
            await s.execute(text("SELECT 1 FROM glicko_ratings_ffa WHERE player_id = :p FOR UPDATE"),
                            {"p": lob.pids[0]})
            await s.execute(text("SELECT 1 FROM players WHERE id = :p FOR UPDATE"), {"p": lob.pids[0]})
            task = asyncio.create_task(listing(env))
            try:
                rows = await asyncio.wait_for(asyncio.shield(task), 2.0)
            except asyncio.TimeoutError:
                rows = None
            await s.rollback()
        if rows is None:
            await asyncio.wait_for(task, 30)
        assert rows is not None and rows[qid]["can_accept"] is True, ("G1 answered within 2 s", rows)
    run_env(monkeypatch, body)


def test_g2_the_lists_verdict_is_what_accept_then_does(monkeypatch):
    async def body(env):
        cases = {}
        lob, cases["accept"] = await closed_held(env)
        lob, cases["later"] = await closed_held(env)
        await later_for(env, lob)
        lob = await played(env)
        await close(env, lob)
        await held(env, lob, 2)
        cases["ahead"] = await held(env, lob, 3)
        lob, cases["word"] = await closed_held(env)
        await env.conn.execute("UPDATE match_report_quarantine SET reason = 'lobby_game_limit' WHERE id = $1",
                               uuid.UUID(cases["word"]))
        lob, cases["clock"] = await closed_held(env)
        await set_received(env, cases["clock"], await anchor(env, lob) - _dt.timedelta(seconds=5))
        verdicts = await listing(env)
        want = {"accept": (True, ""), "later": (False, T["later"].format(n=1)),
                "ahead": (False, T["ahead"].format(tail=3, next=2)), "word": (False, T["word"]),
                "clock": (False, T["clock"])}
        for name, qid in cases.items():
            v = verdicts[qid]
            assert (v["can_accept"], v["accept_blocked_reason"]) == want[name], ("G2 verdict", name, v)
            ans = await accept(env, qid)
            got = (ans.status == 200, "" if ans.status == 200 else ans.body)
            assert got == (v["can_accept"], v["accept_blocked_reason"]), ("G2 accept", name, ans, v)
    run_env(monkeypatch, body)


# ── T1, W1, L1, H1 ─────────────────────────────────────────────────────────

def _widest(s):
    return s.format(n=999, tail=999, next=999)


def test_t1_every_sentence_is_within_180_characters_and_is_what_the_code_sends():
    assert set(T) >= {"later", "rating", "ahead", "behind", "no_number", "clock", "word", "team", "readmit",
                      "lobby_open", "can_accept", "credited_before", "reviewed", "recorded"}
    for key, s in T.items():
        w = _widest(s)
        assert 1 <= len(w) <= 180, ("T1", key, len(w))
        assert "_" not in w and "qid" not in w.lower(), ("T1 no internal names", key, w)
    # Every sentence a route answers comes from the table: the body table's
    # values, the word table's values and the number texts are its keys.
    assert set(main._QAPPLY_BODY_TEXT.values()) <= set(T)
    assert set(main._QAPPLY_WORD_TEXT.values()) <= set(T)
    assert main._qapply_number_text(3, 2) == T["ahead"].format(tail=3, next=2)
    assert main._qapply_number_text(1, 2) == T["behind"].format(tail=1)
    assert main._qapply_number_text(None, 2) == T["no_number"]
    for blocked in (T["later"], T["rating"], T["behind"], T["no_number"]):
        assert "Credit can pay" in blocked
    assert T["ahead"].endswith("Apply game {next} of this lobby first.")
    for word, label in modlog.ACTIONS.items():
        if word.startswith("quarantine_"):
            assert len(label) <= 180


# The hold sites' reason words, by class (WORDS.tsv). lobby_{} and series_{}
# are the two words the code forms from a status.
W_SERVED = frozenset({"lobby_completed", "lobby_canceled", "ffa_game_number_mismatch"})
W_NEVER = frozenset({"score_shape_mismatch", "v1_canonical_downgrade", "ffa_game_contradiction",
                     "ffa_room_other_lobby", "ffa_replay_roster_mismatch", "late_reporter", "left_reporter",
                     "lag_reporter", "ffa_lobby_no_roster", "lobby_game_limit"})
W_FORMED = {"lobby_{}": ("lobby_completed", "lobby_canceled", "lobby_open", "lobby_active"),
            "series_{}": ("series_",)}


def test_w1_every_reason_word_of_the_hold_sites_is_classed():
    tree = _tree()
    words, formed = set(), set()
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id in ("_ffa_record_and_refuse", "_quarantine_report")):
            continue
        for k in n.keywords:
            if k.arg != "reason":
                continue
            if isinstance(k.value, ast.Constant):
                words.add(k.value.value)
            elif isinstance(k.value, ast.JoinedStr):
                formed.add("".join(v.value if isinstance(v, ast.Constant) else "{}" for v in k.value.values))
            else:
                assert isinstance(k.value, ast.Name) and k.value.id == "reason", ast.unparse(k.value)
    assert words == (W_SERVED | W_NEVER) - {"lobby_completed", "lobby_canceled"}, sorted(words ^ (W_SERVED | W_NEVER))
    assert formed == set(W_FORMED), formed
    assert main._QAPPLY_SERVABLE_REASONS == W_SERVED


def test_l1_the_credit_word_and_the_accept_record(monkeypatch):
    assert modlog.ACTIONS["quarantine_credit"] == "Held report credited"
    s = modlog.sentence("quarantine_credit", {"players": {"1": {"xp": 10, "gold": 2}, "2": {"xp": 5, "gold": 1}}})
    assert s == "Credited a held match report: 2 players paid 15 XP and 3 gold in all, no rating moved.", s
    assert modlog.sentence("quarantine_accept", {"applied": True, "game": 2}).startswith(
        "Accepted a held match report and applied it as game 2")

    async def body(env):
        lob, qid = await closed_held(env)
        ans = await accept(env, qid, note="checked")
        assert ans.status == 200
        r = await env.conn.fetchrow("SELECT * FROM admin_actions WHERE action = 'quarantine_accept'")
        d = json.loads(r["details"]) if isinstance(r["details"], str) else r["details"]
        assert d["applied"] is True and d["match_id"] == ans.body["match_id"] == str(r["target_match_id"]), d
        assert sorted(r["affected_steam_ids"]) == sorted(lob.sids) and r["reason"] == "checked", dict(r)
        lob, qid = await closed_held(env)
        await later_for(env, lob)
        assert (await credit(env, qid)).status == 200
        r = await env.conn.fetchrow("SELECT * FROM admin_actions WHERE action = 'quarantine_credit'")
        assert sorted(r["affected_steam_ids"]) == sorted(lob.sids), dict(r)
    run_env(monkeypatch, body)


class _DownSession:
    async def execute(self, *a, **k):
        raise OSError("qapply_build: the database is down")

    async def rollback(self):
        pass


def test_h1_health_carries_qapply_build_in_both_forms():
    tree = _tree()
    (health,) = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    (tried,) = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    connected = [ast.unparse(k.value) for s in tried.body for k in ast.walk(s)
                 if isinstance(k, ast.keyword) and k.arg == "qapply_build"]
    degraded = [ast.unparse(k.value) for h in tried.handlers for k in ast.walk(h)
                if isinstance(k, ast.keyword) and k.arg == "qapply_build"]
    assert (connected, degraded) == (["_QAPPLY_BUILD"], ["_QAPPLY_BUILD"])
    assert main._QAPPLY_BUILD == 1
    field = schemas.HealthResponse.model_fields.get("qapply_build")
    assert field is not None and field.annotation is int and field.is_required(), field
    answer = asyncio.run(main.health_check(db=_DownSession())).model_dump()
    assert answer["status"] == "degraded" and answer["qapply_build"] == 1, answer
