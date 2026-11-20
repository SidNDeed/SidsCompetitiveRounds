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


async def credit(env, qid, *, word="quarantine_credit", note=None, invariant=True):
    req = main._AdminQuarantineReq(admin_steam_id=ADMIN, hmac_signature=sig(word, qid), note=note)

    async def go():
        async with env.sm() as db:
            return await main.admin_credit_quarantine(qid, req, db)
    ans = await env._call(go)
    # F5: after every Credit of these tests, every credited held row has
    # its game's claim, whoever credited it. (invariant=False: M2's pairs,
    # which run two actions at once and read the invariant after both, on
    # the one test connection.)
    if invariant:
        await _f5_invariant(env)
    return ans


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

    def by_slot(rows):
        return sorted((slot[r["player_id"]], repr(sorted((k, v) for k, v in clean(r).items()
                                                          if k not in ("reference_id", "nonce"))))
                      for r in rows if r["player_id"] in slot)
    cards = by_slot(await env.conn.fetch("SELECT * FROM ffa_match_cards WHERE match_id = $1", m["id"]))
    offers = by_slot(await env.conn.fetch("SELECT * FROM ffa_card_offers WHERE match_id = $1", m["id"]))
    achievements = by_slot(await env.conn.fetch(
        "SELECT * FROM player_achievements WHERE player_id = ANY($1::uuid[])", lob.pids))
    packs = by_slot(await env.conn.fetch(
        "SELECT * FROM pc_packs WHERE source = 'earned' AND reference_id = $1", main._pc_earned_ref("ffa", m["id"])))
    ladder = by_slot(await env.conn.fetch(
        "SELECT * FROM title_ladder_progress WHERE player_id = ANY($1::uuid[])", lob.pids))
    credits = by_slot(await env.conn.fetch(
        "SELECT * FROM title_ladder_credits WHERE player_id = ANY($1::uuid[])", lob.pids))
    return {"match": clean(m), "winner": slot[m["winner_id"]], "seats": seats, "ratings": ratings,
            "players": players, "ledger": ledger, "cards": cards, "offers": offers,
            "achievements": achievements, "packs": packs, "ladder": ladder, "credits": credits,
            "ended_at": m["ended_at"], "id": m["id"]}


def test_a1_accept_writes_what_a_network_report_writes(monkeypatch):
    async def body(env):
        # The earned pack, deterministically: a secret so the grant runs, a
        # roll that always hits, and the signature check answering the
        # signed form (the fixture's reports carry no signature).
        monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "qapply-a1-pack-roll")
        monkeypatch.setattr(main, "_verify_ffa_hmac", lambda report: "v2")
        monkeypatch.setattr(main._pc, "earned_pack_kind", lambda secret, mode, ref: "win")
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
        assert b2["packs"], ("A1 the network game granted its pack", b2["packs"])
        for k in ("match", "winner", "seats", "ratings", "players", "ledger", "cards", "offers",
                  "achievements", "packs", "ladder", "credits"):
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
        print("A12 times", {k: round(v, 3) for k, v in sorted(started.items())}, "answers", c.status, a.status,
              n.status)
        # F3: each action ends within its deadline, the report within its
        # bound; a lock wait ends at the lock bound. The third session holds
        # the held row about 2.4 s after Credit asks for it, past the lock
        # bound, so Credit answers busy once its wait has reached the bound,
        # never on first contact; Accept, queued 0.8 s later, waits under
        # the bound and applies the game.
        lock_bound = main._QAPPLY_LOCK_TIMEOUT_MS / 1000.0
        assert started["credit"] < main._QAPPLY_DEADLINE_S and started["accept"] < main._QAPPLY_DEADLINE_S, (
            "A12 no action waits past its deadline", started)
        assert started["network"] < F3_REPORT_BOUND_S, ("A12 the report waits within its bound", started)
        assert c.status in (409, 503) and a.status == 200, ("A12 accept applies, credit does not", c, a)
        for name, x in (("credit", c), ("accept", a)):
            if x.status == 503:
                assert x.body == T["busy"], (name, x)
                assert started[name] >= lock_bound, ("A12 busy only at the bound", name, started)
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
        assert ans.status == 409 and ans.body == T["held_credited"], ("C3 credit twice", ans)
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
        assert ans.status == 409 and ans.body == T["held_applied"], ("C3 credit after accept", ans)
        assert await tables(env) == before
        lob, qid = await closed_held(env)
        await later_for(env, lob)
        assert (await credit(env, qid)).status == 200
        before = await tables(env)
        ans = await accept(env, qid)
        assert ans.status == 409 and ans.body == T["held_credited"], ("C3 accept after credit", ans)
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
        assert (ans.status, ans.body) == (403, T["admin"]), ("C5 credit with accept's word", ans)
        ans = await accept(env, qid, word="quarantine_credit")
        assert (ans.status, ans.body) == (403, T["admin"]), ("C5 accept with credit's word", ans)
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
        # can_credit: what Credit then does, on fresh rows, every refusal
        # outcome included (the gate, the number, the word, the clock, a
        # verification, the game's claim).
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
        lob, cases["count"] = await closed_held(env)
        await later_for(env, lob)
        await env.conn.execute("UPDATE ffa_lobbies SET player_count = 5 WHERE id = $1", lob.lid)
        lob, q_first, cases["paid"] = await siblings(env, 2)
        await later_for(env, lob)
        assert (await credit(env, q_first)).status == 200
        want = {"accept": False, "later": True, "ahead": True, "word": False, "clock": False,
                "count": False, "paid": False}
        verdicts = await listing(env)
        for name, qid in cases.items():
            v = verdicts[qid]
            assert v["can_credit"] is want[name], ("G2 can_credit", name, v)
            ans = await credit(env, qid)
            assert (ans.status == 200) is v["can_credit"], ("G2 credit", name, ans, v)
    run_env(monkeypatch, body)


# ── T1, W1, L1, H1 ─────────────────────────────────────────────────────────

def _widest(s):
    return s.format(n=999, tail=999, next=999, g=999)


def _texts_table():
    """qapply_texts.tsv beside this file: key -> sentence."""
    rows = {}
    with open(os.path.join(HERE, "qapply_texts.tsv"), encoding="utf-8") as f:
        assert f.readline() == "key\tsentence\n"
        for line in f:
            key, sentence = line.rstrip("\n").split("\t")
            rows[key] = sentence
    return rows


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
    for blocked in (T["later"], T["rating"], T["behind"]):
        assert "Credit can pay" in blocked
    assert "Credit" not in T["no_number"], "Credit does not pay a report naming no game"
    assert T["ahead"].endswith("Apply game {next} of this lobby first.")
    # The table the routes' sentences are reviewed from is what the code
    # holds, the list's eligibility sentence (outside _QAPPLY_TEXTS) included.
    table = _texts_table()
    assert table == dict(T, eligibility=main.QDIG_ELIGIBILITY_FAILED), sorted(
        set(table.items()) ^ set(dict(T, eligibility=main.QDIG_ELIGIBILITY_FAILED).items()))
    (lst,) = [n for n in ast.walk(_tree()) if isinstance(n, ast.AsyncFunctionDef)
              and n.name == "admin_list_quarantine"]
    assert "QDIG_ELIGIBILITY_FAILED" in {n.id for n in ast.walk(lst) if isinstance(n, ast.Name)}
    # Every HTTPException the four routes raise themselves carries a table
    # sentence (a _QAPPLY_TEXTS entry), never a literal.
    for route in ("admin_list_quarantine", "admin_discard_quarantine", "admin_accept_quarantine",
                  "admin_credit_quarantine"):
        (fn,) = [n for n in ast.walk(_tree()) if isinstance(n, ast.AsyncFunctionDef) and n.name == route]
        for c in ast.walk(fn):
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "HTTPException":
                detail = ast.unparse(c.args[1]) if len(c.args) > 1 else ""
                assert detail.startswith("_QAPPLY_TEXTS["), ("T1 a literal answer", route, detail)
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


# ── F1: one game is applied or paid once, whatever rows describe it ───────
# Two members' reports of one game are two held rows with the same lobby and
# the same room (so the same named game number). The claim on the game
# (migration 426, _qapply_claim) is what a second action of either kind meets.

async def siblings(env, g, *, games=1):
    """A lobby of four with `games` games recorded, closed, and two members'
    reports of game g held: two pending rows of one game, by two reporters.
    The second report names the room the first one took, so the capture keeps
    it as its own row with the room column empty; the room it names is in its
    payload, which is where the routes read the game number from."""
    lob = await played(env, games=games)
    await close(env, lob)
    for who in (lob.sids[0], lob.sids[1]):
        a = await env.report(lob, g, res(lob), reporter=who)
        assert a.status != 200, ("fixture: sibling report of game %d held" % g, a)
    rows = await env.conn.fetch(
        "SELECT id FROM match_report_quarantine WHERE group_id = $1"
        "   AND COALESCE(photon_room_id, payload->>'photon_room_id') LIKE $2"
        "   AND status = 'pending' ORDER BY created_at, id", lob.lid, "%%_r%d" % g)
    assert len(rows) == 2, ("fixture: two held rows of game %d" % g, len(rows))
    return lob, str(rows[0]["id"]), str(rows[1]["id"])


async def paid(env, lob):
    """The players' XP and gold and every ledger row of them, for comparing."""
    players = sorted(tuple(r) for r in await env.conn.fetch(
        "SELECT steam_id, total_xp, gold_earned, ffa_xp_earned, ffa_gold_earned FROM players"
        " WHERE id = ANY($1::uuid[])", lob.pids))
    ledger = sorted(tuple(r) for r in await env.conn.fetch(
        "SELECT player_id::text, reason, amount, reference_id FROM gold_transactions"
        " WHERE player_id = ANY($1::uuid[])", lob.pids))
    return players, ledger


async def claims(env, lob):
    return sorted(tuple(r) for r in await env.conn.fetch(
        "SELECT game_number, kind, quarantine_id::text FROM ffa_game_claims WHERE lobby_id = $1", lob.lid))


async def _lock_waiters(env, n):
    """Returns once n sessions of this database wait on a lock (the
    database's own record, pg_stat_activity), never by a fixed pause; fails
    after 5 s."""
    loop = asyncio.get_running_loop()
    end = loop.time() + 5.0
    while True:
        got = await env.conn.fetchval("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                                      "   AND wait_event_type = 'Lock'")
        if got >= n:
            return
        assert loop.time() < end, ("M2 sessions queued on the lobby's lock", got, n)
        await asyncio.sleep(0.02)


async def _timed(act, env, qid):
    """The action's answer and its own elapsed seconds. The test connection
    (env.conn) is never used inside: two of these run at once beside
    _lock_waiters, and asyncpg refuses a second operation on one
    connection; _pair_rows reads Credit's F5 invariant after both answer."""
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    ans = await (act(env, qid, invariant=False) if act is credit else act(env, qid))
    return ans, loop.time() - t0


async def _pair_rows(env, lob, one, two, *, release=True):
    """Hold the lobby's row in a third session; start one=(action, qid) and
    go on once the database shows it queued on that row; the same for two;
    then release (release=False: hold until both have answered). Both
    (answer, elapsed) pairs, waited for at most the unit's deadline plus 2 s."""
    async with env.sm() as s:
        await s.execute(text("SELECT 1 FROM ffa_lobbies WHERE id = CAST(:l AS uuid) FOR UPDATE"),
                        {"l": str(lob.lid)})
        t1 = asyncio.create_task(_timed(one[0], env, one[1]))
        t2 = None
        try:
            await _lock_waiters(env, 1)
            t2 = asyncio.create_task(_timed(two[0], env, two[1]))
            await _lock_waiters(env, 2)
            if release:
                await s.rollback()
            got = await asyncio.wait_for(asyncio.gather(t1, t2), main._QAPPLY_DEADLINE_S + 2.0)
            await _f5_invariant(env)
            return got
        finally:
            await s.rollback()
            for t in (t1, t2):
                if t is not None and not t.done():
                    t.cancel()


async def _m2_state(env, lob, rows):
    """Everything an action of `lob`'s rows can change, keyed by the lobby's
    seat order and the rows' positions (so two lobbies of one shape compare):
    each player's XP and gold, each ledger row, the claims, the game's rows
    and both held rows' statuses."""
    slot = {str(p): i for i, p in enumerate(lob.pids)}
    label = {q: "row%d" % i for i, q in enumerate(rows)}
    for r in await env.conn.fetch("SELECT id::text, game_number FROM ffa_matches WHERE lobby_id = $1", lob.lid):
        label[r["id"]] = "match%d" % r["game_number"]
    players = sorted((slot[str(r["id"])], r["total_xp"], r["gold_earned"], r["ffa_xp_earned"], r["ffa_gold_earned"])
                     for r in await env.conn.fetch("SELECT id, total_xp, gold_earned, ffa_xp_earned, ffa_gold_earned"
                                                   " FROM players WHERE id = ANY($1::uuid[])", lob.pids))
    ledger = sorted((slot[r["player_id"]], r["reason"], r["amount"], label.get(r["reference_id"], r["reference_id"]))
                    for r in await env.conn.fetch("SELECT player_id::text, reason, amount, reference_id"
                                                  " FROM gold_transactions WHERE player_id = ANY($1::uuid[])",
                                                  lob.pids))
    got = sorted((g, k, label.get(q, q)) for g, k, q in await claims(env, lob))
    held_rows = [await status_of(env, q) for q in rows]
    return {"players": players, "ledger": ledger, "claims": got,
            "games": await game_rows(env, lob, 2), "held": held_rows}


def _m2_delta(before, after):
    """after less before: players as per-seat differences, ledger rows as
    the rows added (a multiset), the rest as they stand after."""
    import collections
    b = {r[0]: r[1:] for r in before["players"]}
    players = sorted((s,) + tuple(x - y for x, y in zip(v, b[s])) for s, v in
                     ((r[0], r[1:]) for r in after["players"]))
    added = collections.Counter(after["ledger"]) - collections.Counter(before["ledger"])
    gone = collections.Counter(before["ledger"]) - collections.Counter(after["ledger"])
    return {"players": players, "ledger": sorted(added.elements()), "ledger_gone": sorted(gone.elements()),
            "claims": after["claims"], "games": after["games"] - before["games"], "held": after["held"]}


def test_f1_a_second_credit_of_one_game_is_refused_with_its_sentence(monkeypatch):
    async def body(env):
        lob, qa, qb = await siblings(env, 2)
        await later_for(env, lob)
        assert (await credit(env, qa)).status == 200
        before = await paid(env, lob)
        ans = await credit(env, qb)
        assert (ans.status, ans.body) == (409, T["game_paid"]), ("F1 credit of a sibling row", ans)
        assert await paid(env, lob) == before, "F1 nothing paid twice"
        assert await status_of(env, qb) == "pending"
        assert await claims(env, lob) == [(2, "credit", qa)]
        # The list says so before the admin tries.
        assert (await listing(env))[qb]["can_credit"] is False
    run_env(monkeypatch, body)


def test_f1_the_key_refuses_a_second_claim_of_one_game(monkeypatch):
    async def body(env):
        lob, qa, qb = await siblings(env, 2)
        await later_for(env, lob)
        assert (await credit(env, qa)).status == 200
        before = await paid(env, lob)
        ans = await credit(env, qb)
        assert ans.status == 409, ("F1 the second credit is refused", ans)
        assert await paid(env, lob) == before, "F1 nothing paid twice"
        assert len(await claims(env, lob)) == 1
        # The key itself, without any read: a second claim returns nothing.
        async with env.sm() as db:
            with pytest.raises(main._QapplyRefused) as ex:
                await main._qapply_claim(db, lob.lid, 2, kind="credit", qid=qb)
            await db.rollback()
        assert str(ex.value.detail) == T["claimed"]
    run_env(monkeypatch, body)


def test_f1_credit_then_accept_of_a_sibling_row_is_refused(monkeypatch):
    async def body(env):
        # Game 3 held twice while the lobby is on game 2: Credit pays one row
        # of game 3; game 2 is applied; the sibling row of game 3 then meets
        # the claim under Accept.
        lob, q3a, q3b = await siblings(env, 3)
        assert (await credit(env, q3a)).status == 200
        q2 = await held(env, lob, 2)
        assert (await accept(env, q2)).status == 200
        before = (await paid(env, lob), await game_rows(env, lob, 3))
        ans = await accept(env, q3b)
        assert (ans.status, ans.body) == (409, T["game_credited"]), ("F1 accept of a credited game", ans)
        assert (await paid(env, lob), await game_rows(env, lob, 3)) == before
        assert await status_of(env, q3b) == "pending"
    run_env(monkeypatch, body)


def test_f1_accept_then_credit_of_a_sibling_row_is_refused(monkeypatch):
    async def body(env):
        lob, qa, qb = await siblings(env, 2)
        assert (await accept(env, qa)).status == 200
        await later_for(env, lob)
        before = await paid(env, lob)
        ans = await credit(env, qb)
        assert (ans.status, ans.body) == (409, T["recorded"]), ("F1 credit of an applied game", ans)
        assert await paid(env, lob) == before
        assert await claims(env, lob) == [(2, "accept", qa)]
    run_env(monkeypatch, body)


def test_f1_a_later_action_names_the_state_the_earlier_one_made(monkeypatch):
    # The cells the tests above leave: each later action answers the state
    # the earlier action made, never a check that a write to the lobby moved.
    async def body(env):
        # Accept, then Accept of the same row and of a sibling row.
        lob, qa, qb = await siblings(env, 2)
        assert (await accept(env, qa)).status == 200
        before = (await paid(env, lob), await game_rows(env, lob, 2), await claims(env, lob))
        for qid, want in ((qa, "reviewed"), (qb, "recorded")):
            ans = await accept(env, qid)
            assert (ans.status, ans.body) == (409, T[want]), ("F1 accept after accept", want, ans)
        assert (await paid(env, lob), await game_rows(env, lob, 2), await claims(env, lob)) == before
        assert await status_of(env, qb) == "pending"
        # Credit of game 3 while the lobby is on game 2: the sibling row's
        # Accept names the credit, not the number it would also refuse.
        lob, q3a, q3b = await siblings(env, 3)
        assert (await credit(env, q3a)).status == 200
        v = (await listing(env))[q3b]
        assert (v["can_accept"], v["accept_blocked_reason"], v["can_credit"]) == (
            False, T["game_credited"], False), ("F1 the list names the credit", v)
        before = (await paid(env, lob), await game_rows(env, lob, 3))
        ans = await accept(env, q3b)
        assert (ans.status, ans.body) == (409, T["game_credited"]), ("F1 credited before the number", ans)
        assert (await paid(env, lob), await game_rows(env, lob, 3)) == before
        assert await status_of(env, q3b) == "pending"
        # The control: a row of another game of the same lobby is not refused
        # by that claim.
        q2 = await held(env, lob, 2)
        assert (await listing(env))[q2]["can_accept"] is True
        assert (await accept(env, q2)).status == 200, "F1 another game of the lobby applies"
        # Accept records the lobby's last game; Credit of the sibling row
        # names the recorded game, not the game limit that record reached.
        monkeypatch.setattr(main, "FFA_MAX_GAMES_PER_LOBBY", 2)
        lob, qa, qb = await siblings(env, 2)
        assert (await accept(env, qa)).status == 200
        await later_for(env, lob)
        before = await paid(env, lob)
        ans = await credit(env, qb)
        assert (ans.status, ans.body) == (409, T["recorded"]), ("F1 recorded before the limit", ans)
        assert await paid(env, lob) == before
    run_env(monkeypatch, body)


def test_f1_two_sibling_actions_at_once_take_effect_once(monkeypatch):
    """M2: two actions on the two held rows of one game, each in its own
    session, queued on the lobby's row (the database shows each queued
    before the next step; no fixed pause). Exactly one takes effect, and
    the COMPLETE change (each player's XP and gold, each ledger row, the
    claim, the game's rows, both held rows) equals that of the same action
    alone on a lobby of the same shape. Each action answers within the
    unit's deadline, also when the lobby's row is held past both bounds."""
    async def fixture(env, pair):
        lob, qa, qb = await siblings(env, 2)
        # Two Credits need a later game (Credit pays only where Accept
        # cannot apply); the mixed pairs leave the gate open, so the game
        # is Accept's and Credit is refused either way.
        if pair == (credit, credit):
            await later_for(env, lob)
        return lob, qa, qb

    async def body(env):
        bound = main._QAPPLY_DEADLINE_S
        for pair in ((credit, credit), (credit, accept), (accept, credit)):
            names = tuple(f.__name__ for f in pair)
            lob, qa, qb = await fixture(env, pair)
            start = await _m2_state(env, lob, (qa, qb))
            (a, ta), (b, tb) = await _pair_rows(env, lob, (pair[0], qa), (pair[1], qb))
            print("M2 pair", names, a.status, "%.3f s" % ta, b.status, "%.3f s" % tb)
            assert ta < bound and tb < bound, ("M2 each action within the deadline", names, ta, tb)
            ok = [i for i, x in enumerate((a, b)) if x.status == 200]
            assert len(ok) == 1, ("M2 exactly one takes effect", names, a, b)
            loser = (a, b)[1 - ok[0]]
            assert loser.status == 409 or (loser.status, loser.body) == (503, T["busy"]), ("M2 the other", names, loser)
            pair_delta = _m2_delta(start, await _m2_state(env, lob, (qa, qb)))
            # The same action alone, on the row in the same position of a
            # lobby of the same shape.
            lob1, q1a, q1b = await fixture(env, pair)
            start1 = await _m2_state(env, lob1, (q1a, q1b))
            alone = await pair[ok[0]](env, (q1a, q1b)[ok[0]])
            assert alone.status == 200, ("M2 the action alone", names, alone)
            alone_delta = _m2_delta(start1, await _m2_state(env, lob1, (q1a, q1b)))
            assert pair_delta == alone_delta, ("M2 the pair's change is one action's", names, pair_delta, alone_delta)
        # The lobby's row held past both bounds: each action answers busy
        # within the deadline and nothing changes.
        lob, qa, qb = await fixture(env, (credit, credit))
        start = await _m2_state(env, lob, (qa, qb))
        before = await tables(env)
        (a, ta), (b, tb) = await _pair_rows(env, lob, (credit, qa), (credit, qb), release=False)
        print("M2 held", a.status, "%.3f s" % ta, b.status, "%.3f s" % tb)
        assert ta < bound and tb < bound, ("M2 each action within the deadline while held", ta, tb)
        assert (a.status, a.body) == (b.status, b.body) == (503, T["busy"]), (a, b)
        assert _m2_delta(start, await _m2_state(env, lob, (qa, qb)))["ledger"] == []
        assert await tables(env) == before
    run_env(monkeypatch, body)


def test_f1_a_network_report_to_a_closed_lobby_settles_nothing(monkeypatch):
    # The premise of Credit's open-lobby refusal: once the lobby has closed,
    # no network report settles a game of it, so a game Credit paid is not
    # also settled by a late report.
    async def body(env):
        lob = await played(env)
        await close(env, lob)
        before = await tables(env)
        a = await env.report(lob, 2, res(lob))
        assert a.status != 200, ("F1 a closed lobby's report is not settled", a)
        assert await game_rows(env, lob, 2) == 0
        after = await tables(env)
        for k in ("matches", "seats", "ledger", "players", "ratings"):
            assert after[k] == before[k], ("F1 nothing settled", k)
        # And Credit's refusal while the lobby is open says when it works.
        lob2 = await played(env)
        q = await held(env, lob2, 3)
        ans = await credit(env, q)
        assert (ans.status, ans.body) == (409, T["lobby_open"]), ("F1 open lobby", ans)
        assert "once the lobby has closed" in T["lobby_open"]
    run_env(monkeypatch, body)


# ── F2: Credit pays only a report the body's own verifications pass ───────
# The verifications are the _ffa_check_* functions and _ffa_score_shape_error;
# the body calls each at its own place, and Credit and the list call
# _ffa_report_verify, which runs them all.

OUTSIDER = str(cf_asm.STEAM_BASE + 999_777)


def _calls_in(fn_name):
    (fn,) = [n for n in ast.walk(_tree()) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == fn_name]
    return {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}


def _checks_called(fn_name):
    return {n for n in _calls_in(fn_name) if n.startswith("_ffa_check_") or n == "_ffa_score_shape_error"}


def test_f2_census_credit_and_the_list_make_the_bodys_verifications():
    defined = {n.name for n in ast.walk(_tree()) if isinstance(n, ast.FunctionDef)
               and n.name.startswith("_ffa_check_")} | {"_ffa_score_shape_error"}
    body = _checks_called("submit_ffa_match")
    runner = _checks_called("_ffa_report_verify")
    assert body == defined, ("every check is one the body makes", sorted(defined ^ body))
    assert runner == body, ("Credit's verifications are the body's", sorted(runner ^ body))
    assert set(main._FFA_REPORT_VERIFICATIONS) == body
    for fn in ("_qapply_credit", "_qapply_verdict"):
        calls = _calls_in(fn)
        assert "_ffa_report_verify" in calls, fn
        assert not (_checks_called(fn)), ("no copy of a check", fn, _checks_called(fn))
        src = ast.get_source_segment(main_src(), [n for n in ast.walk(_tree())
                                                   if getattr(n, "name", None) == fn][0])
        for copied in ("FFA_MAX_GAMES_PER_LOBBY", "player_count"):
            assert copied not in src, ("no copy of a check's rule", fn, copied)
    # The signature and the service-account check: one function each, called
    # by the body and on Credit's path.
    for shared in ("_verify_ffa_hmac", "_assert_no_service_subject"):
        assert shared in _calls_in("submit_ffa_match"), shared
        assert shared in _calls_in("_qapply_credit"), shared


def main_src():
    return open(MAIN_SRC, encoding="utf-8").read()


async def _f2_parts(env):
    lob = await played(env)
    rep = await env.report_req(lob, 2, res(lob))
    row = dict(await env.lobby_row(lob.lid))
    ids = {r["steam_id"]: r["id"] for r in await env.conn.fetch(
        "SELECT id, steam_id FROM players WHERE id = ANY($1::uuid[])", lob.pids)}
    return lob, rep, row, ids


def _f2_variants(rep, lobby, ids):
    p = list(rep.players)

    def players(ps):
        return rep.model_copy(update={"players": ps})
    swapped = [p[1].model_copy(update={"slot": p[0].slot}), p[0].model_copy(update={"slot": p[1].slot})] + p[2:]
    zero = [x.model_copy(update={"rounds_won": 0}) for x in p]
    one_gone = dict(list(ids.items())[1:])
    stranger = list(lobby["member_ids"])
    stranger[-1] = uuid.uuid4()
    v2 = "v2"
    return {
        "players": (players([p[0], p[0]] + p[2:]), v2, lobby, ids),
        "winner": (rep.model_copy(update={"winner_steam_id": OUTSIDER}), v2, lobby, ids),
        "reporter": (rep.model_copy(update={"reported_by_steam_id": OUTSIDER}), v2, lobby, ids),
        "room": (rep.model_copy(update={"photon_room_id": "  "}), v2, lobby, ids),
        "accounts": (rep, v2, lobby, one_gone),
        "roster": (rep, v2, dict(lobby, member_ids=stranger), ids),
        "count": (rep, v2, dict(lobby, player_count=len(p) + 1), ids),
        "slots": (players(swapped), v2, lobby, ids),
        "shape": (players(zero), v2, lobby, ids),
        "limit": (rep, v2, dict(lobby, games_played=main.FFA_MAX_GAMES_PER_LOBBY), ids),
        "downgrade": (rep, "v1", dict(lobby, kills_tiebreak=True), ids),
    }


def test_f2_each_verification_refuses_its_report_in_the_runner(monkeypatch):
    async def body(env):
        lob, rep, row, ids = await _f2_parts(env)
        assert main._ffa_report_verify(rep, canonical_form="v2", lobby=dict(row, kills_tiebreak=True),
                                       id_by_steam=ids) is None, "the base report passes"
        got = {w: main._ffa_report_verify(r, canonical_form=c, lobby=lb, id_by_steam=i)
               for w, (r, c, lb, i) in _f2_variants(rep, row, ids).items()}
        assert got == {w: w for w in got}, got
        assert set(got) == set(main._QAPPLY_CHECK_TEXT), "every word has its sentence"
    run_env(monkeypatch, body)


F2_DB = ("accounts", "roster", "count", "slots", "shape", "limit", "downgrade")


@pytest.mark.parametrize("word", F2_DB)
def test_f2_credit_refuses_a_held_row_a_verification_fails_and_writes_nothing(word, monkeypatch):
    async def body(env):
        lob, qid = await closed_held(env)
        await later_for(env, lob)
        q = uuid.UUID(qid)
        if word == "accounts":
            await env.conn.execute("UPDATE players SET deleted_at = now() WHERE id = $1", lob.pids[3])
        elif word == "roster":
            await env.conn.execute("UPDATE ffa_lobbies SET member_ids[4] = $2 WHERE id = $1",
                                   lob.lid, lob.pids[0])
        elif word == "count":
            await env.conn.execute("UPDATE ffa_lobbies SET player_count = 5 WHERE id = $1", lob.lid)
        elif word == "slots":
            await env.conn.execute(
                "UPDATE match_report_quarantine SET payload = jsonb_set(jsonb_set(payload,"
                " '{players,0,slot}', '1'), '{players,1,slot}', '0') WHERE id = $1", q)
        elif word == "shape":
            await env.conn.execute(
                "UPDATE match_report_quarantine SET payload = jsonb_set(payload, '{players}',"
                " (SELECT jsonb_agg(jsonb_set(e, '{rounds_won}', '0')) FROM jsonb_array_elements(payload->'players') e))"
                " WHERE id = $1", q)
        elif word == "limit":
            await env.conn.execute("UPDATE ffa_lobbies SET games_played = $2 WHERE id = $1",
                                   lob.lid, main.FFA_MAX_GAMES_PER_LOBBY)
        elif word == "downgrade":
            await env.conn.execute("UPDATE ffa_lobbies SET kills_tiebreak = true WHERE id = $1", lob.lid)
            monkeypatch.setattr(main, "_verify_ffa_hmac", lambda report: "v1")
        before = await tables(env)
        ans = await credit(env, qid)
        assert (ans.status, ans.body) == (409, T[main._QAPPLY_CHECK_TEXT[word]]), (word, ans)
        assert await tables(env) == before, (word, "nothing written")
        assert await status_of(env, qid) == "pending"
        # The list's flag agrees (M1: the same verifications, read form).
        assert (await listing(env))[qid]["can_credit"] is False, word
    run_env(monkeypatch, body)


# ── F3: neither action waits without a bound, nor makes a report wait ─────
# A third session holds a participant's players row; the action needs it.

F3_OWN_BOUND_S = 6.0     # the lock bound (2 s) and the work around it
F3_REPORT_BOUND_S = 10.0  # what a player's report may wait at most


async def _f3_case(env, act):
    lob, qid = await closed_held(env)
    if act is credit:
        await later_for(env, lob)
    return lob, qid


@pytest.mark.parametrize("act", (accept, credit), ids=("accept", "credit"))
def test_f3_an_action_meeting_a_held_row_refuses_within_its_bound_and_writes_nothing(act, monkeypatch):
    async def body(env):
        lob, qid = await _f3_case(env, act)
        before = await tables(env)
        async with env.sm() as s:
            await s.execute(text("SELECT 1 FROM players WHERE id = CAST(:p AS uuid) FOR UPDATE"),
                            {"p": str(lob.pids[1])})
            t0 = asyncio.get_running_loop().time()
            ans = await asyncio.wait_for(act(env, qid), F3_OWN_BOUND_S + 4)
            took = asyncio.get_running_loop().time() - t0
            await s.rollback()
        assert (ans.status, ans.body) == (503, T["busy"]), (act.__name__, ans)
        assert took < F3_OWN_BOUND_S, (act.__name__, "refused in %.1f s" % took)
        assert await tables(env) == before, (act.__name__, "nothing written")
        assert await status_of(env, qid) == "pending"
        # Once the row is free the action goes through.
        assert (await act(env, qid)).status == 200
    run_env(monkeypatch, body)


@pytest.mark.parametrize("act", (accept, credit), ids=("accept", "credit"))
def test_f3_a_report_waiting_on_an_actions_rows_is_answered_within_the_bound(act, monkeypatch):
    async def body(env):
        lob, qid = await _f3_case(env, act)
        rep = await env.report_req(lob, 3, res(lob))
        async with env.sm() as s:
            # The action takes the held row and the lobby, then waits on this row.
            await s.execute(text("SELECT 1 FROM players WHERE id = CAST(:p AS uuid) FOR UPDATE"),
                            {"p": str(lob.pids[1])})
            t_act = asyncio.create_task(act(env, qid))
            await asyncio.sleep(0.8)
            t0 = asyncio.get_running_loop().time()
            # A player's report of the same lobby waits on the lobby's row.
            got = await asyncio.wait_for(env.submit(rep), F3_REPORT_BOUND_S + 2)
            took = asyncio.get_running_loop().time() - t0
            ans = await asyncio.wait_for(t_act, F3_REPORT_BOUND_S)
            await s.rollback()
        assert got.status != 500, ("the report is served or refused", got)
        assert took < F3_REPORT_BOUND_S, ("the report waited %.1f s" % took)
        assert (ans.status, ans.body) == (503, T["busy"]), (act.__name__, ans)
        assert await status_of(env, qid) == "pending"
    run_env(monkeypatch, body)


# ── F4: a replay writes no process state another request trusts ───────────
# The module-level names that the code the actions reach can write, derived
# from the source (bare-name calls, transitively): `global` rebinding, stores
# into a module name, and mutating method calls on one.

_F4_ROOTS = ("admin_accept_quarantine", "admin_credit_quarantine", "submit_ffa_match")
_F4_MUT = {"append", "add", "update", "pop", "popitem", "clear", "setdefault", "remove", "discard",
           "extend", "insert", "appendleft", "popleft", "move_to_end"}


def _f4_written_names():
    tree = _tree()
    funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    mod = set()
    for n in tree.body:
        ts = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, (ast.AnnAssign, ast.AugAssign)) else []
        mod |= {t.id for t in ts if isinstance(t, ast.Name)}
    seen, todo = set(), list(_F4_ROOTS)
    while todo:
        f = todo.pop()
        if f in seen or f not in funcs:
            continue
        seen.add(f)
        todo += [c.id for c in ast.walk(funcs[f]) if isinstance(c, ast.Name) and c.id in funcs]
    out = {}
    for f in seen:
        fn = funcs[f]
        globs = {g for c in ast.walk(fn) if isinstance(c, ast.Global) for g in c.names}
        local = ({a.arg for a in fn.args.args + fn.args.kwonlyargs}
                 | {c.id for c in ast.walk(fn) if isinstance(c, ast.Name) and isinstance(c.ctx, ast.Store)}) - globs
        hit = set(globs)
        for c in ast.walk(fn):
            base = None
            if isinstance(c, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                for t in (c.targets if isinstance(c, ast.Assign) else [c.target]):
                    if isinstance(t, (ast.Subscript, ast.Attribute)):
                        base = t.value
            elif isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr in _F4_MUT:
                base = c.func.value
            while isinstance(base, (ast.Subscript, ast.Attribute)):
                base = base.value
            if isinstance(base, ast.Name) and base.id in mod and base.id not in local:
                hit.add(base.id)
        for name in hit:
            out.setdefault(name, set()).add(f)
    return out


def _f4_snapshot(names):
    import copy
    return {n: copy.deepcopy(getattr(main, n, "<absent>")) for n in names}


_F4_CACHE = ("_service_player_uuid_cache", "_service_uuid_cache_monotonic",
             "_service_uuid_cache_filled_monotonic")
_F4_LOOKUP_SQL = "SELECT id::text FROM players WHERE steam_id = ANY(CAST(:sids AS text[]))"


def _f4_spies(monkeypatch, names, fail=None):
    """Counts the service lookup's statement by whether the action's unit
    (main._QAPPLY_UNIT, the unit's mark) is open when it runs, refuses that
    statement while fail[0] is true, and snapshots `names` as each unit
    opens and closes."""
    from sqlalchemy.ext.asyncio import AsyncSession
    seen = {"in_unit": 0, "outside": 0, "units": []}
    orig_exec, orig_unit = AsyncSession.execute, main._qapply_unit

    async def spy_exec(self, stmt, *a, **k):
        if " ".join(str(stmt).split()) == _F4_LOOKUP_SQL:
            seen["in_unit" if main._QAPPLY_UNIT.get() is not None else "outside"] += 1
            if fail and fail[0]:
                raise RuntimeError("the service lookup's read is refused by the test")
        return await orig_exec(self, stmt, *a, **k)

    @contextlib.asynccontextmanager
    async def spy_unit(kind):
        async with orig_unit(kind) as k:
            entry = _f4_snapshot(names)
            try:
                yield k
            finally:
                seen["units"].append((kind, entry, _f4_snapshot(names)))
    monkeypatch.setattr(AsyncSession, "execute", spy_exec)
    monkeypatch.setattr(main, "_qapply_unit", spy_unit)
    return seen


def _f4_cache(monkeypatch, cache, schedule_age, filled_age):
    # The clock main reads: the harness sets main.time to a proxy whose
    # monotonic() is its own frozen value (cf_asm.Env), so stamps taken from
    # the process clock would read as about a million seconds old.
    now = main.time.monotonic()
    monkeypatch.setattr(main, "_service_player_uuid_cache", cache)
    monkeypatch.setattr(main, "_service_uuid_cache_monotonic",
                        0.0 if schedule_age is None else now - schedule_age)
    monkeypatch.setattr(main, "_service_uuid_cache_filled_monotonic",
                        None if filled_age is None else now - filled_age)


async def _f4_raw(env, route, qid, word):
    """The route's own answer, headers kept (env._call drops them)."""
    req = main._AdminQuarantineReq(admin_steam_id=ADMIN, hmac_signature=sig(word, qid))
    async with env.sm() as db:
        try:
            out = await route(qid, req, db)
        except main.HTTPException as ex:
            return ex
    return out


_F4_ROUTES = (("accept", main.admin_accept_quarantine, "quarantine_action"),
              ("credit", main.admin_credit_quarantine, "quarantine_credit"))


def test_f4_a_unit_neither_reads_the_service_set_nor_writes_process_state(monkeypatch):
    names = _f4_written_names()
    assert set(_F4_CACHE) <= set(names), ("the census sees the policy cache", sorted(names))

    async def body(env):
        seen = _f4_spies(monkeypatch, names)
        lob_ok, q_ok = await closed_held(env)
        lob_no, q_no = await closed_held(env)
        await later_for(env, lob_no)
        lob_cr, q_cr = await closed_held(env)
        await later_for(env, lob_cr)
        for name, act, qid, want in (("commit", accept, q_ok, 200), ("rollback", accept, q_no, 409),
                                     ("credit", credit, q_cr, 200)):
            # An empty cache, as after a restart: the fill happens before the unit.
            _f4_cache(monkeypatch, None, None, None)
            seen.update(in_unit=0, outside=0, units=[])
            ans = await act(env, qid)
            assert ans.status == want, (name, ans)
            assert seen["outside"] == 1, (name, "the fill before the unit", seen["outside"])
            assert seen["in_unit"] == 0, (name, "a read of the service set inside the unit", seen["in_unit"])
            assert len(seen["units"]) == 1, (name, len(seen["units"]))
            kind, entry, leave = seen["units"][0]
            assert entry["_service_player_uuid_cache"] is not None, (name, "the cache was filled before the unit")
            changed = sorted(n for n in names if entry[n] != leave[n])
            assert not changed, (name, "process state written while the unit was open", changed)
    run_env(monkeypatch, body)


def test_f4_the_last_seconds_before_a_refresh_refuse_before_the_unit(monkeypatch):
    names = _f4_written_names()
    bound = main._QAPPLY_DEADLINE_S + main._QAPPLY_SERVICE_MARGIN_S

    async def body(env):
        seen = _f4_spies(monkeypatch, names)
        for name, route, word in _F4_ROUTES:
            lob, qid = await closed_held(env)
            if name == "credit":
                await later_for(env, lob)
            # The schedule leaves 5 s, inside the deadline plus the margin.
            left = 5.0
            _f4_cache(monkeypatch, {str(uuid.uuid4())}, main._SERVICE_UUID_REFRESH_SECONDS - left, 60.0)
            cache = _f4_snapshot(_F4_CACHE)
            before = await tables(env)
            seen.update(in_unit=0, outside=0, units=[])
            ans = await _f4_raw(env, route, qid, word)
            assert isinstance(ans, main.HTTPException), (name, ans)
            assert (ans.status_code, ans.detail) == (503, "service_policy_unavailable"), (name, ans)
            ra = int(ans.headers["Retry-After"])
            assert 1 <= ra <= int(bound) + 1 and ra <= int(left) + 1, (name, ra)
            assert seen["units"] == [] and seen["in_unit"] == 0, (name, "a unit started", seen)
            assert seen["outside"] == 0, (name, "the cache was not due: no read", seen["outside"])
            assert _f4_snapshot(_F4_CACHE) == cache, (name, "a cache or clock value changed")
            assert await tables(env) == before, (name, "a row changed")
            # Control: the 60 s an empty fill leaves is outside the bound, and the action runs.
            _f4_cache(monkeypatch, set(), main._SERVICE_UUID_REFRESH_SECONDS - 60.0, 0.0)
            ans = await (accept if name == "accept" else credit)(env, qid)
            assert ans.status == 200, (name, "control", ans)
            assert len(seen["units"]) == 1, (name, "control unit", seen["units"])
    run_env(monkeypatch, body)


def test_f4_a_failing_lookup_refuses_before_the_unit(monkeypatch):
    names = _f4_written_names()

    async def body(env):
        fail = [False]
        seen = _f4_spies(monkeypatch, names, fail)
        for name, route, word in _F4_ROUTES:
            for state, setup in (
                    ("no previous fill", (None, None, None)),
                    ("a previous fill past its schedule",
                     ({str(uuid.uuid4())}, main._SERVICE_UUID_REFRESH_SECONDS + 1.0,
                      main._SERVICE_UUID_REFRESH_SECONDS + 1.0))):
                lob, qid = await closed_held(env)
                if name == "credit":
                    await later_for(env, lob)
                _f4_cache(monkeypatch, *setup)
                before = await tables(env)
                seen.update(in_unit=0, outside=0, units=[])
                fail[0] = True
                try:
                    ans = await _f4_raw(env, route, qid, word)
                finally:
                    fail[0] = False
                assert isinstance(ans, main.HTTPException) and ans.status_code == 503, (name, state, ans)
                assert seen["outside"] == 1, (name, state, "the read was tried", seen["outside"])
                assert seen["units"] == [] and seen["in_unit"] == 0, (name, state, "a unit started", seen)
                assert await tables(env) == before, (name, state, "a row changed")
                if setup[0] is not None:
                    # The kept set leaves no time to the schedule: the helper's own refusal.
                    assert ans.detail == "service_policy_unavailable" and ans.headers["Retry-After"] == "1", \
                        (name, state, ans.detail, ans.headers)
    run_env(monkeypatch, body)


def test_f4_the_deadline_and_margin_fit_inside_the_shortest_schedule():
    """R4: the unit's deadline plus the margin is below the shortest
    schedule a fill leaves: the empty set's, read from the lookup's own
    source, and the normal refresh interval."""
    fn = _tree_fn("_service_player_uuids")
    shortest = None
    for c in ast.walk(fn):
        if (isinstance(c, ast.BinOp) and isinstance(c.op, ast.Sub)
                and isinstance(c.left, ast.Name) and c.left.id == "_SERVICE_UUID_REFRESH_SECONDS"
                and isinstance(c.right, ast.Constant) and isinstance(c.right.value, (int, float))):
            assert shortest is None, "one empty-fill schedule"
            shortest = float(c.right.value)
    assert shortest is not None, "the empty fill's schedule is read from the lookup"
    bound = main._QAPPLY_DEADLINE_S + main._QAPPLY_SERVICE_MARGIN_S
    assert main._QAPPLY_SERVICE_MARGIN_S >= 2.0
    assert bound < shortest, (bound, shortest)
    assert bound < main._SERVICE_UUID_REFRESH_SECONDS, (bound, main._SERVICE_UUID_REFRESH_SECONDS)


def _tree_fn(name):
    hits = [n for n in _tree().body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert len(hits) == 1, (name, len(hits))
    return hits[0]


def _is_await_of(stmt, name):
    return (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Await)
            and isinstance(stmt.value.value, ast.Call) and isinstance(stmt.value.value.func, ast.Name)
            and stmt.value.value.func.id == name)


def test_f4_every_unit_entry_follows_the_service_check_and_only_there():
    """R5, both ways, from the syntax tree: every `_qapply_unit(` entry is an
    `async with` whose preceding statement awaits _qapply_service_ready;
    every await of the helper is followed by such an entry; the helper
    awaits the lookup and nothing after it."""
    tree = _tree()
    entries, checks = [], []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            body = getattr(node, field, None)
            if not isinstance(body, list):
                continue
            for i, stmt in enumerate(body):
                is_entry = isinstance(stmt, ast.AsyncWith) and any(
                    isinstance(it.context_expr, ast.Call) and isinstance(it.context_expr.func, ast.Name)
                    and it.context_expr.func.id == "_qapply_unit" for it in stmt.items)
                if is_entry:
                    entries.append(stmt.lineno)
                    assert i > 0 and _is_await_of(body[i - 1], "_qapply_service_ready"), \
                        ("a unit entry without the service check before it", stmt.lineno)
                if _is_await_of(stmt, "_qapply_service_ready"):
                    checks.append(stmt.lineno)
                    nxt = body[i + 1] if i + 1 < len(body) else None
                    assert isinstance(nxt, ast.AsyncWith) and any(
                        isinstance(it.context_expr, ast.Call) and isinstance(it.context_expr.func, ast.Name)
                        and it.context_expr.func.id == "_qapply_unit" for it in nxt.items), \
                        ("a service check not followed by a unit entry", stmt.lineno)
    calls = [c for c in ast.walk(tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
             and c.func.id == "_qapply_unit"]
    assert len(calls) == len(entries) == len(checks) == 2, (len(calls), entries, checks)
    helper = _tree_fn("_qapply_service_ready")
    awaits = [a for a in ast.walk(helper) if isinstance(a, ast.Await)]
    assert len(awaits) == 1 and _is_await_of(helper.body[1] if isinstance(helper.body[0], ast.Expr)
                                             and isinstance(helper.body[0].value, ast.Constant)
                                             else helper.body[0], "_service_player_uuids"), \
        ("the helper awaits the lookup first and nothing after it", len(awaits))
    from grammar_shapes_a1 import A1_SPANS
    assert "_qapply_service_ready" not in {r[2] for r in A1_SPANS}, "the helper is in no frozen span"


# ── M2: every early failure of the four routes answers a table sentence ───

def test_m2_malformed_input_to_each_route_answers_its_table_sentence(monkeypatch):
    async def body(env):
        table = _texts_table()
        lob, qid = await closed_held(env)
        routes = (("accept", main.admin_accept_quarantine, "quarantine_action"),
                  ("credit", main.admin_credit_quarantine, "quarantine_credit"),
                  ("discard", main.admin_discard_quarantine, "quarantine_action"))
        before = await tables(env)
        for name, route, word in routes:
            for target, signed, note, want in (
                    ("not-a-uuid", "not-a-uuid", None, (400, "bad_id")),
                    (qid, "0" * 64, None, (403, "admin")),
                    (qid, qid, "bad\x00note", (422, "note")),
                    (str(uuid.uuid4()), None, None, (404, "not_found"))):
                req = main._AdminQuarantineReq(admin_steam_id=ADMIN, note=note,
                                               hmac_signature=signed if signed and len(signed) == 64
                                               else sig(word, signed or target))

                async def go(route=route, target=target, req=req):
                    async with env.sm() as db:
                        return await route(target, req, db)
                ans = await env._call(go)
                assert (ans.status, ans.body) == (want[0], table[want[1]]), (name, target, ans)

        async def go_list():
            async with env.sm() as db:
                return await main.admin_list_quarantine(admin_steam_id=ADMIN, hmac_signature="0" * 64, db=db)
        ans = await env._call(go_list)
        assert (ans.status, ans.body) == (403, table["admin"]), ("list", ans)
        assert await tables(env) == before, "M2 nothing changed"
    run_env(monkeypatch, body)


# ── M3: every effect a check is assigned is read by that check ────────────

def _test_reads(test_name):
    """The source of a test and of every module function it reaches."""
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    tree = ast.parse(src)
    funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    seen, todo = set(), [test_name]
    while todo:
        f = todo.pop()
        if f in seen or f not in funcs:
            continue
        seen.add(f)
        todo += [c.id for c in ast.walk(funcs[f]) if isinstance(c, ast.Name) and c.id in funcs]
    return "\n".join(ast.get_source_segment(src, funcs[f]) for f in seen)


def test_m3_each_check_reads_the_tables_its_effects_name():
    import re
    rows = []
    with open(os.path.join(HERE, "qapply_effects.tsv"), encoding="utf-8") as f:
        assert f.readline() == "id\ttables\tchecks\n"
        for line in f:
            eid, tbls, checks = line.rstrip("\n").split("\t")
            rows.append((eid, tbls.split(","), checks.split(",")))
    names = {n.name for n in ast.parse(open(os.path.abspath(__file__), encoding="utf-8").read()).body
             if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}
    for eid, tbls, checks in rows:
        for check in checks:
            (test,) = [n for n in names if n.startswith("test_%s_" % check.lower())][:1] or [None]
            assert test is not None, (eid, check, "no such check")
            src = _test_reads(test)
            for t in tbls:
                assert re.search(r"\b%s\b" % re.escape(t), src), (eid, check, test, "does not read", t)


# ── F5: 426 seeds a claim for every game already credited from a held row ──

M426 = os.path.join(HERE, "..", "sql", "426_ffa_game_claims.sql")
SEED_SELECT = os.path.join(HERE, "qapply_seed_select.sql")
# The words the read-only verb refuses, as substrings in any letter case.
_F5_REFUSED_WORDS = ("CREATE", "INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "TRUNCATE", "GRANT",
                     "REVOKE", "COPY")
# Every strict name (Addendum 3, C1): _r, ASCII digits, at most one final
# newline, 1 to 999; leading zeros and the final newline among them.
_F5_STRICT = ("ffa_58e81a62609a_040746_r2", "ffa_58e81a62609a_042203_r3", "ffa_q_r1", "ffa_q_r999",
              "ffa_q_r007", "ffa_q_r12\n", "ffa_q_r_r45", "r5_r6", "_r9")
# Each covered row outside the strict rule refuses the whole file (C2, C3).
_F5_REFUSE = (("arabic-indic digit", "ffa_q_r٣"), ("devanagari digit", "ffa_q_r३"),
              ("fullwidth digit", "ffa_q_r３"), ("no tail", "ffa_q"), ("tail 0", "ffa_q_r0"),
              ("tail 1000", "ffa_q_r1000"), ("a tail with a letter", "ffa_q_r3a"),
              ("two final newlines", "ffa_q_r3\n\n"), ("no room", None), ("no lobby", "ffa_q_r4"))
_F5_NOTE_421 = "Migration 421, option B: gold and XP credited, ratings not applied."


def _f5_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _f5_seed_block():
    src = _f5_text(M426)
    a = src.index("-- SEED SELECT BEGIN") + len("-- SEED SELECT BEGIN")
    return src[a:src.index("-- SEED SELECT END")]


def _f5_credit_writers_without_claims(sql_dir):
    """Migrations numbered above 426 that set a held row to 'credited' and
    never name ffa_game_claims (426's header states the rule)."""
    import re
    out = []
    for name in sorted(os.listdir(sql_dir)):
        m = re.match(r"^(\d{3,})_.*\.sql$", name)
        if not m or int(m.group(1)) <= 426:
            continue
        src = _f5_text(os.path.join(sql_dir, name))
        if re.search(r"status\s*=\s*'credited'", src, re.I) and "ffa_game_claims" not in src:
            out.append(name)
    return out


def test_f5_the_seed_select_file_is_the_migrations_reading_and_holds_no_refused_word():
    def norm(s):
        return " ".join(s.replace(";", " ").split())
    alone = _f5_text(SEED_SELECT)
    assert norm(alone) == norm(_f5_seed_block()), "the standalone SELECT is the seed's own text"
    assert alone.rstrip().endswith(";") and alone.count(";") == 1, "one plain statement"
    assert [w for w in _F5_REFUSED_WORDS if w in alone.upper()] == [], "a word the read-only verb refuses"
    assert alone.lstrip().upper().startswith("SELECT ")


def test_f5_every_later_file_that_credits_a_held_row_writes_its_claim(tmp_path):
    assert _f5_credit_writers_without_claims(os.path.join(HERE, "..", "sql")) == []
    # The planted red: a later file that credits without a claim is named;
    # one that writes the claim, and 421 itself, are not.
    (tmp_path / "421_old.sql").write_text("UPDATE match_report_quarantine SET status = 'credited';")
    (tmp_path / "998_with_claim.sql").write_text(
        "UPDATE match_report_quarantine SET status = 'credited';\nINSERT INTO ffa_game_claims VALUES (1);")
    (tmp_path / "999_planted.sql").write_text("UPDATE match_report_quarantine q SET status='CREDITED';")
    assert _f5_credit_writers_without_claims(str(tmp_path)) == ["999_planted.sql"]


async def _f5_row(c, room, *, lobby=None, no_lobby=False, status="credited"):
    """One covered held row (FFA, status credited) whose body names `room`.
    The room column stays empty: the seed reads the body alone, and the
    partial unique index uq_quarantine_room (mode, room) would refuse the
    second row of one game (the case of two covered rows of one game)."""
    qid = uuid.uuid4()
    body = {} if room is None else {"photon_room_id": room}
    await c.execute(
        "INSERT INTO match_report_quarantine (id, mode, reason, http_status, group_id, photon_room_id,"
        "  payload, status) VALUES ($1, 'ffa', 'lobby_completed', 409, $2, NULL, $3::jsonb, $4)",
        qid, None if no_lobby else (lobby or uuid.uuid4()), json.dumps(body), status)
    return qid


async def _f5_run_426(c):
    """426 run whole on the case's connection; None, or the error's text
    (the transaction it left is rolled back)."""
    try:
        await c.execute(_f5_text(M426))
    except Exception as ex:
        await c.execute("ROLLBACK")
        return str(ex)
    return None


async def _f5_claims(c):
    return sorted((str(r["lobby_id"]), r["game_number"], r["kind"], str(r["quarantine_id"]))
                  for r in await c.fetch("SELECT * FROM ffa_game_claims"))


async def _f5_invariant(env):
    """Every held row with status 'credited' has a claim for its game (the
    game its body names, in its lobby)."""
    missing = await env.conn.fetch(
        "SELECT q.id FROM match_report_quarantine q"
        " WHERE q.mode = 'ffa' AND q.status = 'credited' AND NOT EXISTS ("
        "   SELECT 1 FROM ffa_game_claims g WHERE g.lobby_id = q.group_id"
        "      AND g.game_number = CAST(substring(q.payload->>'photon_room_id' FROM '_r([0-9]+)\\n?$')"
        "          AS numeric))")
    assert [str(r["id"]) for r in missing] == [], "a credited held row without its game's claim"


def test_f5_the_strict_rule_reads_what_the_api_reads_and_refuses_the_rest(monkeypatch):
    async def body(env):
        c = env.conn
        # (1) every strict name: the api's number and the seed's, side by side.
        ids = {await _f5_row(c, room): room for room in _F5_STRICT}
        rows = {r["quarantine_id"]: r for r in await c.fetch(_f5_text(SEED_SELECT))}
        assert set(rows) == set(ids), "the SELECT covers exactly the covered rows"
        table = [(room, main._ffa_named_game_number(room), rows[q]["game_number"], rows[q]["decision"])
                 for q, room in ids.items()]
        print("F5 TABLE strict (room, api, seed, decision)", table)
        bad = [t for t in table if not (t[1] is not None and t[1] == t[2] and t[3] == "seed")]
        assert bad == [], ("the strict rule and the api differ on a strict name", bad)
        await c.execute("DELETE FROM match_report_quarantine WHERE id = ANY($1::uuid[])", list(ids))
        lob = uuid.uuid4()
        q2 = await _f5_row(c, "ffa_58e81a62609a_040746_r2", lobby=lob)
        q3 = await _f5_row(c, "ffa_58e81a62609a_042203_r3", lobby=lob)
        # (2) one covered row outside the strict rule refuses the whole file.
        for case, room in _F5_REFUSE:
            q = await _f5_row(c, room, no_lobby=(case == "no lobby"))
            r = {x["quarantine_id"]: x for x in await c.fetch(_f5_text(SEED_SELECT))}[q]
            before = await tables(env)
            err = await _f5_run_426(c)
            print("F5 TABLE refuse", case, repr(room), "api", main._ffa_named_game_number(room),
                  "seed", r["game_number"], r["decision"], "|", err)
            assert r["decision"] == "refuse", (case, dict(r))
            assert r["game_number"] is None or case == "no lobby", (case, dict(r))
            assert err is not None and ("426: credited FFA held report %s has" % q) in err, (case, err)
            assert await _f5_claims(c) == [] and await tables(env) == before, (case, "a change stood")
            await c.execute("DELETE FROM match_report_quarantine WHERE id = $1", q)
        # Two covered rows of one game: refused, nothing applied.
        q3b = await _f5_row(c, "ffa_58e81a62609a_042203_r3", lobby=lob)
        err = await _f5_run_426(c)
        assert err is not None and "credited from two or more held reports" in err, err
        assert await _f5_claims(c) == []
        await c.execute("DELETE FROM match_report_quarantine WHERE id = $1", q3b)
        # (4) control: the primary's two shapes seed exactly two claims.
        assert await _f5_run_426(c) is None
        want = sorted([(str(lob), 2, "credit", str(q2)), (str(lob), 3, "credit", str(q3))])
        assert await _f5_claims(c) == want
        await _f5_invariant(env)
        # A second run changes nothing.
        stamps = await c.fetch("SELECT * FROM ffa_game_claims ORDER BY game_number")
        assert await _f5_run_426(c) is None
        assert await c.fetch("SELECT * FROM ffa_game_claims ORDER BY game_number") == stamps
    run_env(monkeypatch, body)


def test_f5_the_strict_rule_reads_the_same_names_under_every_collation(monkeypatch):
    """The seed's rule reads ASCII digits alone whatever the database's
    collation: a regular expression's character class follows the collation
    of the text it reads (under an ICU collation a locale class such as
    [[:digit:]] takes the Arabic-Indic, Devanagari and fullwidth digits),
    while a code-point range such as [0-9] does not. Every pattern of the
    migration's seed block and of the SELECT file is read under "C", under
    the database's default and under an ICU collation, over every strict and
    every refused name; each answer must be the "C" answer, and no
    non-ASCII digit may be read as a game number under any of them."""
    import re as _re
    pats = sorted(set(_re.findall(r"FROM '([^']*)'", _f5_seed_block()))
                  | set(_re.findall(r"FROM '([^']*)'", _f5_text(SEED_SELECT))))
    assert pats, "the seed block names no pattern"
    rooms = [r for r in _F5_STRICT] + [room for _case, room in _F5_REFUSE if room is not None]
    non_ascii = [room for case, room in _F5_REFUSE if room is not None and "digit" in case]
    assert len(non_ascii) == 3

    async def body(env):
        c = env.conn
        icu = await c.fetchval(
            "SELECT collname FROM pg_collation WHERE collprovider = 'i' AND collisdeterministic"
            " ORDER BY (collname = 'und-x-icu') DESC, collname LIMIT 1")
        assert icu, "this database has no ICU collation; the rule's reading under one cannot be shown"
        bad = []
        for pat in pats:
            for room in rooms:
                ans = {}
                for name, expr in (("C", 'CAST($1 AS text) COLLATE "C"'), ("default", "CAST($1 AS text)"),
                                   (icu, 'CAST($1 AS text) COLLATE "%s"' % icu.replace('"', '""'))):
                    ans[name] = await c.fetchval("SELECT substring(%s FROM CAST($2 AS text))" % expr, room, pat)
                if len(set(ans.values())) != 1 or (room in non_ascii and ans["C"] is not None):
                    bad.append((pat, room, ans))
        print("F5 COLLATION", icu, len(pats), "patterns", len(rooms), "names", "bad", len(bad))
        assert bad == [], bad
    run_env(monkeypatch, body)


async def _f5_421_end_state(env):
    """421's end state on a lobby of the harness: two members' reports of game
    3 held (siblings) and one of game 2; the game 2 row and the first game 3
    row marked credited as 421 marks its two (status, reviewed_at, no
    reviewer, its note), with no claim; then 426 runs whole."""
    lob, q3, q3b = await siblings(env, 3)
    q2 = await held(env, lob, 2)
    await env.conn.execute(
        "UPDATE match_report_quarantine SET status = 'credited', reviewed_at = now(), reviewed_by = NULL,"
        "  review_note = $2 WHERE id = ANY($1::uuid[])", [uuid.UUID(q2), uuid.UUID(q3)], _F5_NOTE_421)
    assert await env.conn.fetchval("SELECT count(*) FROM ffa_game_claims WHERE lobby_id = $1", lob.lid) == 0
    err = await _f5_run_426(env.conn)
    assert err is None, ("426 on 421's end state", err)
    await _f5_invariant(env)
    return lob, q2, q3, q3b


def test_f5_a_game_421_credited_is_not_paid_again(monkeypatch):
    async def body(env):
        lob, q2, q3, q3b = await _f5_421_end_state(env)
        assert await _f5_claims(env.conn) == sorted([(str(lob.lid), 2, "credit", q2),
                                                      (str(lob.lid), 3, "credit", q3)])
        v = (await listing(env))[q3b]
        assert (v["can_accept"], v["accept_blocked_reason"], v["can_credit"]) == (
            False, T["game_credited"], False), ("the list names the credit", v)
        before = (await tables(env), await paid(env, lob), await _f5_claims(env.conn))
        ans = await credit(env, q3b)
        assert (ans.status, ans.body) == (409, T["game_paid"]), ("Credit of a sibling", ans)
        assert (await tables(env), await paid(env, lob), await _f5_claims(env.conn)) == before
        ans = await accept(env, q3b)
        assert (ans.status, ans.body) == (409, T["game_credited"]), ("Accept of a sibling", ans)
        assert (await tables(env), await paid(env, lob), await _f5_claims(env.conn)) == before
        assert await status_of(env, q3b) == "pending"
        await _f5_invariant(env)
    run_env(monkeypatch, body)


def test_f5_control_another_game_of_that_lobby_is_not_refused_by_the_seed(monkeypatch):
    async def body(env):
        lob, q2, q3, q3b = await _f5_421_end_state(env)
        q4 = await held(env, lob, 4)
        v = (await listing(env))[q4]
        assert v["accept_blocked_reason"] not in (T["game_credited"], T["recorded"]), v
        ans = await credit(env, q4)
        print("F5 control credit of game 4:", ans.status, ans.body)
        assert ans.body not in (T["game_paid"], T["game_applied"]), ("refused as a paid game", ans)
        await _f5_invariant(env)
    run_env(monkeypatch, body)


# ── M1: a repeat on the same held row answers what the earlier action did ──

def test_m1_a_repeat_on_one_held_row_names_what_the_earlier_action_did(monkeypatch):
    async def body(env):
        async def refused(name, q, act, want):
            before = await tables(env)
            ans = await act(env, q)
            assert (ans.status, ans.body) == (409, want), (name, ans)
            assert await tables(env) == before, (name, "a change stood")
        # Credit, then Credit and Accept on the same row.
        lob, q = await closed_held(env)
        await later_for(env, lob)
        assert (await credit(env, q)).status == 200
        await refused("credit then credit", q, credit, T["held_credited"])
        await refused("credit then accept", q, accept, T["held_credited"])
        # Accept, then Accept and Credit on the same row.
        lob, q = await closed_held(env)
        assert (await accept(env, q)).status == 200
        await refused("accept then accept", q, accept, T["held_applied"])
        await refused("accept then credit", q, credit, T["held_applied"])
        # Rows with no claim answer as before: a row main's Accept only marked
        # (never applied), a discarded row, a filed row (main's triage state).
        for how in ("accepted", "discarded", "filed"):
            lob, q = await closed_held(env)
            if how == "discarded":
                assert (await discard(env, q)).status == 200
            else:
                await env.conn.execute("UPDATE match_report_quarantine SET status = $2, reviewed_at = now()"
                                       " WHERE id = $1", uuid.UUID(q), how)
            assert await status_of(env, q) == how, how
            await refused("%s, accept" % how, q, accept, T["reviewed"])
            await refused("%s, credit" % how, q, credit, T["reviewed"])
        # A row migration 421 credited, after 426's seed: the credited sentence.
        lob, q2, q3, q3b = await _f5_421_end_state(env)
        for q in (q2, q3):
            await refused("421, accept", q, accept, T["held_credited"])
            await refused("421, credit", q, credit, T["held_credited"])
    run_env(monkeypatch, body)


# ── F5 (Addendum 4): a lobby made before the 168 bound is never applied ───

def test_f5_both_routes_reach_the_one_shared_bound_check():
    """D2: the bound stands in _qapply_held, which both routes call."""
    tree = _tree()
    funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def calls(fn, name):
        return sum(1 for c in ast.walk(funcs[fn]) if isinstance(c, ast.Call)
                   and isinstance(c.func, ast.Name) and c.func.id == name)
    for route in ("admin_accept_quarantine", "admin_credit_quarantine"):
        assert calls(route, "_qapply_held") == 1, route
    src = ast.unparse(funcs["_qapply_held"])
    assert "_QAPPLY_SQL_LOBBY_BEFORE_168" in src and "settled_by_hand" in src
    assert main._QAPPLY_LOBBY_SETTLED_BEFORE == _dt.datetime(2026, 7, 31, tzinfo=_dt.timezone.utc)


def test_f5_a_lobby_made_before_the_168_bound_is_refused_by_both_routes(monkeypatch):
    bound = main._QAPPLY_LOBBY_SETTLED_BEFORE

    async def body(env):
        for name, act in (("accept", accept), ("credit", credit)):
            lob, q = await closed_held(env)
            if name == "credit":
                await later_for(env, lob)
            await env.conn.execute("UPDATE ffa_lobbies SET created_at = $2 WHERE id = $1",
                                   lob.lid, bound - _dt.timedelta(seconds=1))
            before = (await tables(env), await paid(env, lob), await _f5_claims(env.conn))
            ans = await act(env, q)
            assert (ans.status, ans.body) == (410, T["settled_by_hand"]), (name, ans)
            assert (await tables(env), await paid(env, lob), await _f5_claims(env.conn)) == before, name
            assert await status_of(env, q) == "pending", name
            # Discard of such a row works as before.
            assert (await discard(env, q)).status == 200, name
            # A lobby made AT the instant passes this rule.
            lob, q = await closed_held(env)
            if name == "credit":
                await later_for(env, lob)
            await env.conn.execute("UPDATE ffa_lobbies SET created_at = $2 WHERE id = $1", lob.lid, bound)
            ans = await act(env, q)
            assert ans.status == 200, (name, "at the instant", ans)
    run_env(monkeypatch, body)


# ── F6: a database bound that fires inside the unit ends the action ───────
# The commits a unit's transaction can reach (from the roots, bare-name calls
# transitively), each with what stands directly before it. The four that are
# not the unit's are named with the reason the unit never reaches them.
_F6_COMMITS_EXEMPT = {
    # journals a readmission lobby's report; the body refuses a readmission
    # lobby under the replay first (readmit), and Credit refuses it in its own checks
    "_ffa_report_gate": "readmission lobbies are refused under the replay before the gate",
    # reached only from _ffa_settle_due_windows_for_report, which the body
    # calls only for a network report (_qapply is None)
    "_ffa_settle_window": "the due windows settle for a network report only",
    # the capture of a held report: under the replay the hold sites raise before it
    # (_ffa_hold_or_raise's _QAPPLY_REPLAY test); the team settlement is never an FFA row's
    "_quarantine_report": "under the replay no hold site captures",
}


def _f6_commits():
    tree = _tree()
    funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    seen, todo = set(), list(_F4_ROOTS)
    while todo:
        f = todo.pop()
        if f in seen or f not in funcs:
            continue
        seen.add(f)
        todo += [c.id for c in ast.walk(funcs[f]) if isinstance(c, ast.Name) and c.id in funcs]
    out = []
    for f in sorted(seen):
        for blk in ast.walk(funcs[f]):
            for field in ("body", "orelse", "finalbody"):
                stmts = getattr(blk, field, None)
                if not isinstance(stmts, list):
                    continue
                for i, s in enumerate(stmts):
                    v = s.value if isinstance(s, ast.Expr) else None
                    if (isinstance(v, ast.Await) and isinstance(v.value, ast.Call)
                            and isinstance(v.value.func, ast.Attribute) and v.value.func.attr == "commit"):
                        out.append((f, stmts[i - 1] if i else None))
    return funcs, out


def _f6_is_mark_read(stmt):
    return (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name) and stmt.value.func.id == "_qapply_check_bound")


def test_f6_every_commit_a_unit_reaches_is_directly_preceded_by_the_marks_read():
    funcs, commits = _f6_commits()
    unit = [(f, prev) for f, prev in commits if f not in _F6_COMMITS_EXEMPT]
    assert sorted({f for f, _ in commits} - set(_F6_COMMITS_EXEMPT)) == [
        "admin_credit_quarantine", "submit_ffa_match"], sorted({f for f, _ in commits})
    for f, prev in unit:
        if f == "admin_credit_quarantine":
            assert _f6_is_mark_read(prev), ("Credit's commit", ast.unparse(prev) if prev else None)
        else:
            # The body's one commit follows the If whose last statement is
            # _qapply_finish, and _qapply_finish ends with the mark's read.
            assert isinstance(prev, ast.If) and "_qapply_finish" in ast.unparse(prev.body[-1]), ast.unparse(prev)
    assert _f6_is_mark_read(funcs["_qapply_finish"].body[-1]), "_qapply_finish ends with the mark's read"
    assert len([c for c in commits if c[0] == "submit_ffa_match"]) == 1
    # The listener: registered for every Engine, and it classifies with the
    # one classifier (no second copy of the two codes).
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    assert event.contains(Engine, "handle_error", main._qapply_on_db_error)
    lsrc = ast.unparse(funcs["_qapply_on_db_error"])
    assert "_qapply_out_of_time" in lsrc and "55P03" not in lsrc and "57014" not in lsrc


async def _f6_bound_error(env):
    """One statement ended by statement_timeout (57014), its error caught here."""
    async with env.sm() as s:
        await s.execute(text("SELECT set_config('statement_timeout', '50ms', true)"))
        try:
            await s.execute(text("SELECT pg_sleep(1)"))
        except Exception:
            pass
        await s.rollback()


def test_f6_the_mark_is_the_calling_units_alone(monkeypatch):
    import contextvars

    async def body(env):
        async with main._qapply_unit("accept"):
            mark = main._QAPPLY_UNIT.get()
            # Another request: its own context, no unit of its own.
            await asyncio.get_running_loop().create_task(_f6_bound_error(env), context=contextvars.Context())
            assert mark.bound is False, "a bound error of another request marked this unit"
            # This unit's own context: marked.
            await _f6_bound_error(env)
            assert mark.bound is True, "the unit's own bound error left it unmarked"
        # No unit open: nothing to mark, nothing raised.
        await _f6_bound_error(env)
        assert main._QAPPLY_UNIT.get() is None
    run_env(monkeypatch, body)


async def _f6_held_kills(env):
    """A closed lobby's held game 2 whose body gives its first player 60
    kills. The harness runs with no signing secret, so the signature check
    answers v2 and kills count: Accept grants that player ffa_kills_50."""
    lob, q = await closed_held(env)
    await env.conn.execute("UPDATE match_report_quarantine SET payload = jsonb_set(payload,"
                           " '{players,0,kills}', '60') WHERE id = $1", uuid.UUID(q))
    sid = await env.conn.fetchval("SELECT payload->'players'->0->>'steam_id' FROM match_report_quarantine"
                                  " WHERE id = $1", uuid.UUID(q))
    return lob, q, await env.conn.fetchval("SELECT id FROM players WHERE steam_id = $1", sid)


async def _f6_state(env, lob, pid):
    return (await tables(env), await paid(env, lob), await _f5_claims(env.conn),
            await env.conn.fetchval("SELECT count(*) FROM player_achievements WHERE player_id = $1", pid))


def test_f6_a_lock_bound_inside_the_achievement_block_ends_the_accept(monkeypatch):
    async def body(env):
        lob, q, pid = await _f6_held_kills(env)
        before = await _f6_state(env, lob, pid)
        loop = asyncio.get_running_loop()
        async with env.sm() as other:
            # Another session holds the achievement row's key past the lock bound.
            other.add(main.PlayerAchievement(player_id=pid, achievement_key="ffa_kills_50"))
            await other.flush()
            t0 = loop.time()
            ans = await accept(env, q)
            took = loop.time() - t0
            await other.rollback()
        print("F6 accept under the held achievement key:", ans.status, ans.body, "%.3f s" % took)
        assert (ans.status, ans.body) == (503, T["busy"]), ans
        assert took < main._QAPPLY_DEADLINE_S, took
        assert await _f6_state(env, lob, pid) == before, "a change stood"
        assert await status_of(env, q) == "pending"
        # Released: a retry applies the game WITH the achievement and its gold.
        ans = await accept(env, q)
        assert ans.status == 200, ans
        assert await env.conn.fetchval("SELECT count(*) FROM player_achievements WHERE player_id = $1"
                                       " AND achievement_key = 'ffa_kills_50'", pid) == 1
        assert await env.conn.fetchval("SELECT count(*) FROM gold_transactions WHERE player_id = $1"
                                       " AND reason = 'achievement' AND reference_id = 'ffa_kills_50'", pid) == 1
    run_env(monkeypatch, body)


def test_f6_a_lock_bound_caught_in_credits_reach_ends_the_credit(monkeypatch):
    async def body(env):
        lob, q = await closed_held(env)
        await later_for(env, lob)
        pid = lob.pids[0]
        orig = main._modlog_steam_ids
        key = 0x5F6C12

        async def swallowed(db, *a, **k):
            # A best-effort block in Credit's reach: a lock wait past the
            # bound inside a savepoint (on a lock nothing else of Credit
            # takes), its error caught and dropped.
            try:
                async with db.begin_nested():
                    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
            except Exception:
                pass
            return await orig(db, *a, **k)
        monkeypatch.setattr(main, "_modlog_steam_ids", swallowed)
        before = await _f6_state(env, lob, pid)
        async with env.sm() as other:
            await other.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
            ans = await credit(env, q)
            await other.rollback()
        assert (ans.status, ans.body) == (503, T["busy"]), ans
        assert await _f6_state(env, lob, pid) == before, "a change stood"
        assert await status_of(env, q) == "pending"
        monkeypatch.setattr(main, "_modlog_steam_ids", orig)
        assert (await credit(env, q)).status == 200
    run_env(monkeypatch, body)


_F7_PLAYERS_WRITE = (r"\bINSERT\s+INTO\s+players\b|\bDELETE\s+FROM\s+players\b"
                     r"|\bUPDATE\s+players\s+SET\s+(?:(?!\bWHERE\b).)*?\b(?:steam_id|id)\s*=")
# A function of the reach that writes such a row, with the reason the row it
# writes cannot be a service account's. Empty: none does.
_F7_WRITERS_ALLOWED = {}


def _f7_players_writers(src):
    """Leg 2 of F4 (F7): the functions of the unit's reach that insert or
    delete a players row or write players.steam_id or players.id, by text
    statement or ORM form."""
    import re
    pat = re.compile(_F7_PLAYERS_WRITE, re.I | re.S)
    tree = ast.parse(src)
    funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    seen, todo = set(), list(_F4_ROOTS)
    while todo:
        f = todo.pop()
        if f in seen or f not in funcs:
            continue
        seen.add(f)
        todo += [c.id for c in ast.walk(funcs[f]) if isinstance(c, ast.Name) and c.id in funcs]
    out = set()
    for f in seen:
        for n in ast.walk(funcs[f]):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and pat.search(n.value):
                out.add((f, "text"))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Player":
                out.add((f, "orm Player()"))
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("insert", "delete", "update")
                    and n.args and isinstance(n.args[0], ast.Name) and n.args[0].id == "Player"):
                out.add((f, "orm %s(Player)" % n.func.id))
            if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                    if isinstance(t, ast.Attribute) and t.attr in ("steam_id", "id"):
                        out.add((f, "orm attribute %s" % t.attr))
    return out, seen


def test_f7_nothing_in_the_unit_changes_what_the_service_lookup_reads():
    """Leg 2: inside a unit no statement inserts or deletes a players row or
    writes its steam_id or id, so a fill of the service set there reads what
    a fill on any other connection reads at that instant (the unit reads at
    READ COMMITTED). A new writer in the reach turns this red."""
    with open(MAIN_SRC, encoding="utf-8") as f:
        src = f.read()
    found, reach = _f7_players_writers(src)
    assert len(reach) > 100, len(reach)
    assert {f for f, _ in found} == set(_F7_WRITERS_ALLOWED), sorted(found)
    # The planted red: a writer reached from _qapply_finish is named.
    planted = src.replace("    ctx[\"applied\"] = match_id\n", "    ctx[\"applied\"] = match_id\n    _f7_plant()\n", 1) + (
        "\n\nasync def _f7_plant():\n    return \"INSERT INTO players (steam_id) VALUES ('1')\"\n")
    assert planted.count("_f7_plant") == 2
    assert {f for f, _ in _f7_players_writers(planted)[0]} == {"_f7_plant"}


async def _f7_fill_on(env, orig):
    """A fill of the service set on a connection of its own, from an empty
    cache: the three module values it leaves. The values that stood before
    are put back."""
    keep = _f4_snapshot(_F4_CACHE)
    main._service_player_uuid_cache = None
    main._service_uuid_cache_monotonic = 0.0
    main._service_uuid_cache_filled_monotonic = None
    try:
        async with env.sm() as db2:
            await orig(db2)
            await db2.rollback()
        return _f4_snapshot(_F4_CACHE)
    finally:
        for n, v in keep.items():
            setattr(main, n, v)


def test_f7_a_fill_inside_the_unit_caches_what_another_connection_reads(monkeypatch):
    """F7's interleaving, for Accept and Credit, committing and rolling back
    (the rollback by the unit's own F6 mark: busy, nothing kept). The service
    check before the unit passes on a fresh cache; then, inside the unit,
    the schedule is moved back as an older lookup's stamp would move it (a
    lookup that began 61 s ago and read an empty set), so the guard's next
    call fills the cache from the unit's transaction. That fill is compared
    with a fill made on a second connection at that point: the set and both
    clocks equal. In the second case of each pair another session inserts
    and commits a players row of a service Steam id AFTER the unit's first
    statement and BEFORE the fill (A3): both fills hold its id, which a unit
    reading from one snapshot (REPEATABLE READ) would not. After the action
    ends, whichever way, the cache it left equals a fill on a fresh
    connection: nothing another request trusts depends on its end."""
    orig = main._service_player_uuids
    sid = sorted(main.SPECTATE_BROADCAST_STEAM_IDS)[0]

    async def body(env):
        seen = _f4_spies(monkeypatch, _F4_CACHE)
        case = {}

        async def wrap(db):
            mark = main._QAPPLY_UNIT.get()
            if mark is None or case.get("done"):
                return await orig(db)
            case["done"] = True
            now = main.time.monotonic()
            main._service_uuid_cache_monotonic = now - 61.0 - (main._SERVICE_UUID_REFRESH_SECONDS - 60.0)
            if case["insert"]:
                case["new"] = str(await env.conn.fetchval(
                    "INSERT INTO players (id, steam_id, display_name) VALUES (gen_random_uuid(), $1,"
                    " 'qap service') RETURNING id", sid))
            reads = seen["in_unit"]
            out = await orig(db)
            case["reads"] = seen["in_unit"] - reads
            case["unit"] = _f4_snapshot(_F4_CACHE)
            case["other"] = await _f7_fill_on(env, orig)
            if case["end"] == "rollback":
                mark.bound = True
            return out
        monkeypatch.setattr(main, "_service_player_uuids", wrap)
        for name, act in (("accept", accept), ("credit", credit)):
            for end in ("commit", "rollback"):
                for insert in (False, True):
                    tag = (name, end, "insert" if insert else "no insert")
                    lob, q = await closed_held(env)
                    if name == "credit":
                        await later_for(env, lob)
                    _f4_cache(monkeypatch, set(), main._SERVICE_UUID_REFRESH_SECONDS - 60.0, 0.0)
                    case.clear()
                    case.update(insert=insert, end=end)
                    ans = await act(env, q)
                    print("F7 interleaving", tag, ans.status, case.get("unit"), case.get("other"))
                    assert case.get("done"), (tag, "the guard was not called inside the unit")
                    assert case["reads"] == 1, (tag, "the fill read inside the unit", case)
                    assert case["unit"] == case["other"], (tag, "the unit's fill and another connection's differ")
                    want = {case["new"]} if insert else set()
                    assert case["unit"]["_service_player_uuid_cache"] == want, (tag, case["unit"])
                    if end == "commit":
                        assert ans.status == 200, (tag, ans)
                    else:
                        assert (ans.status, ans.body) == (503, T["busy"]), (tag, ans)
                        assert await status_of(env, q) == "pending", tag
                    assert _f4_snapshot(_F4_CACHE) == case["unit"], (tag, "the cache moved after the fill")
                    assert await _f7_fill_on(env, orig) == case["unit"], (tag, "a fresh fill after the end differs")
                    if insert:
                        await env.conn.execute("DELETE FROM players WHERE steam_id = $1", sid)
    run_env(monkeypatch, body)


def test_f6_control_a_non_bound_error_in_a_best_effort_block_keeps_the_game(monkeypatch):
    async def body(env):
        lob, q = await closed_held(env)

        async def broken(*a, **k):
            raise RuntimeError("the earned-pack roll fails (forced by the test)")
        monkeypatch.setattr(main, "_pc_grant_earned_packs", broken)
        ans = await accept(env, q)
        assert ans.status == 200, ("a network report's meaning: the game stands", ans)
        assert await status_of(env, q) == "accepted"
    run_env(monkeypatch, body)


# F6's sweep (the design note's list, fix2/f6_sweep.py's rule): every except
# in the reach of the two routes and the report body that can catch a
# database error, in line order per function, with what it does after the
# catch. The test below is parametrised over this list; a change of the code
# that moves it is a re-pin here, with its reason.
_F6_DB_CATCHERS = {None, "Exception", "BaseException", "SQLAlchemyError", "DBAPIError", "OperationalError",
                   "_sa_exc.SQLAlchemyError", "_sa_exc.DBAPIError", "_sa_exc.OperationalError", "TimeoutError"}
# A swept handler that no statement of Accept or Credit reaches through its
# try body, with the reason (by function: every handler of that function).
_F6_NOT_REACHED = {
    "_asm_rollback": "its try body is a rollback, which issues no statement a lock can hold",
    "_check_steam_session": "the reporter's session check does not run under the replay",
    "_mark_session_verified": "called only from the session check, which does not run under the replay",
    "_ffa_settle_window": "the due windows settle for a network report only",
    "_mail_parse_uuid": "parses the id before the unit; its try body issues no statement",
    "_parse_version": "its try body issues no statement",
    "_qdig_read_body": "parses a held body; its try body issues no statement",
    "_qdig_strict_model": "parses a held body; its try body issues no statement",
    "_quarantine_report": "under the replay no hold site captures",
    "_quarantine_same_payload": "compares two bodies; its try body issues no statement",
    "_ffa_progress_relocked": ("called on the body's insert-race and insert-failure arms, each of which raises"
                               " QAPPLY's refusal first under the replay, and after a capture, which the"
                               " replay never makes"),
}


async def _f6_skewed(env):
    """A closed ranked lobby's held game 2 played to the module's target in a
    lobby frozen at 3 (a score-target skew, _ffa_score_shape_error admits
    it), with game 1 recorded as a skew too and an unsettled wager on each
    game: Accept's replay refunds game 2's wagers strictly (the body's skew
    block) and game 1's leftover through the fail-soft lobby refund."""
    lob, q = await closed_held(env)
    await env.conn.execute("UPDATE ffa_lobbies SET score_target = 3 WHERE id = $1", lob.lid)
    await env.conn.execute("UPDATE ffa_matches SET score_target_frozen = 3, score_target_played = 5"
                           " WHERE lobby_id = $1 AND game_number = 1", lob.lid)
    bp, _sid = await env.bettor()
    for g in (1, 2):
        await env.wager(lob, bp, lob.pids[0], game=g)
    return lob, q


# The handlers each route reaches only with a fixture or a stand-in of its
# own (by (function, ordinal)): the skew fixture above; the earned-pack roll,
# which returns before its first statement where the harness signs nothing
# (MATCH_HMAC_SECRET is empty), so the stand-in issues one statement first;
# the achievement's title grant, reached when the granted achievement
# carries a title (ffa_kills_50 is given one for that case).
_F6_SKEWED = {("submit_ffa_match", 6), ("_refund_ffa_lobby_bets", 0)}
_F6_PACK_ROLL = ("submit_ffa_match", 3)
_F6_TITLE = ("_ensure_achievement_title", 0)


def _f6_handlers():
    """(function, ordinal, after, (first, last) line of the try body) for
    each swept handler, from the syntax tree of the main.py under test."""
    tree = _tree()
    funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    seen, todo = set(), list(_F4_ROOTS)
    while todo:
        f = todo.pop()
        if f in seen or f not in funcs:
            continue
        seen.add(f)
        todo += [c.id for c in ast.walk(funcs[f]) if isinstance(c, ast.Name) and c.id in funcs]
    out = []
    for f in sorted(seen):
        rows = []
        for t in ast.walk(funcs[f]):
            for h in getattr(t, "handlers", None) or ():
                names = [None] if h.type is None else [
                    ast.unparse(x) for x in (h.type.elts if isinstance(h.type, ast.Tuple) else [h.type])]
                if not any(n in _F6_DB_CATCHERS for n in names):
                    continue
                after = "re-raises" if any(isinstance(s, ast.Raise) for s in ast.walk(h)) else (
                    "returns" if any(isinstance(s, ast.Return) for s in h.body) else "goes on")
                rows.append((h.lineno, after, (t.body[0].lineno, t.body[-1].end_lineno)))
        for i, (_, after, span) in enumerate(sorted(rows)):
            out.append((f, i, after, span))
    return out


def _f6_inject(monkeypatch, key):
    """Arms a lock wait: before the first statement issued, inside a unit,
    while the armed function's frame stands in its try body's lines, the
    same session waits on the advisory lock `key` (held by another session),
    so the lock bound (55P03) is raised there, as by that statement."""
    import sys as _sys
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
    state = {"target": None, "fired": 0}
    orig = {(c, n): getattr(c, n) for c, ns in ((AsyncSession, ("execute", "scalar", "scalars", "flush", "get")),
                                               (AsyncConnection, ("execute", "scalar"))) for n in ns}

    def armed_here():
        fname, (lo, hi) = state["target"]
        f = _sys._getframe(2)
        while f is not None:
            if f.f_code.co_qualname == fname and lo <= f.f_lineno <= hi:
                return True
            f = f.f_back
        return False

    for (cls, name), fn in orig.items():
        async def spy(self, *a, _fn=fn, _cls=cls, **k):
            if state["target"] and not state["fired"] and main._QAPPLY_UNIT.get() is not None and armed_here():
                state["fired"] += 1
                await orig[(_cls, "execute")](self, text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
            return await _fn(self, *a, **k)
        monkeypatch.setattr(cls, name, spy)
    return state


def test_f6_each_swept_handler_that_a_lock_reaches_ends_the_action(monkeypatch):
    """F6, per handler: for each swept handler and each route, a lock wait
    past the lock bound at the first statement its try body issues inside
    the unit. Wherever it is raised and whoever catches it, the action
    answers busy and nothing of it stands. A handler that neither route
    reaches is named in _F6_NOT_REACHED with the reason; a named one that a
    route reaches turns this red. The service lookup's handler is reached
    by making its refresh fall due inside the unit (F7's interleaving)."""
    handlers = _f6_handlers()
    assert len(handlers) == 35 and sum(1 for h in handlers if h[2] == "goes on") == 17, (
        "the sweep moved: re-pin with its reason", [(f, i, a) for f, i, a, _ in handlers])
    key = 0x5F6A11

    async def body(env):
        state = _f6_inject(monkeypatch, key)
        orig_unit = main._qapply_unit

        @contextlib.asynccontextmanager
        async def unit(kind):
            async with orig_unit(kind) as k:
                if state["target"] and state["target"][0] == "_service_player_uuids":
                    main._service_uuid_cache_monotonic = main.time.monotonic() - main._SERVICE_UUID_REFRESH_SECONDS - 1.0
                yield k
        monkeypatch.setattr(main, "_qapply_unit", unit)
        table, bad = [], []
        orig_pc = main._pc_grant_earned_packs

        async def pc_stand_in(db, *a, **k):
            await db.execute(text("SELECT 1"))
            return await orig_pc(db, *a, **k)
        for f, i, after, span in handlers:
            reached = []
            monkeypatch.setattr(main, "_pc_grant_earned_packs",
                                pc_stand_in if (f, i) == _F6_PACK_ROLL else orig_pc)
            if (f, i) == _F6_TITLE:
                monkeypatch.setitem(main.ACHIEVEMENT_TITLE_SKUS, "ffa_kills_50", "f6_title")
            else:
                monkeypatch.delitem(main.ACHIEVEMENT_TITLE_SKUS, "ffa_kills_50", raising=False)
            for name, act in (("accept", accept), ("credit", credit)):
                if name == "accept" and (f, i) in _F6_SKEWED:
                    lob, q = await _f6_skewed(env)
                elif name == "accept":
                    lob, q, _pid = await _f6_held_kills(env)
                else:
                    lob, q = await closed_held(env)
                    await later_for(env, lob)
                # A previous fill within its age, so the lookup's handler keeps it.
                _f4_cache(monkeypatch, {str(uuid.uuid4())}, 60.0, 60.0)
                before = (await tables(env), await _f5_claims(env.conn))
                state.update(target=(f, span), fired=0)
                async with env.sm() as other:
                    await other.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
                    try:
                        ans = await act(env, q)
                    finally:
                        state["target"] = None
                        await other.rollback()
                if not state["fired"]:
                    continue
                reached.append(name)
                after_state = (await tables(env), await _f5_claims(env.conn))
                ok = (ans.status, ans.body) == (503, T["busy"]) and after_state == before
                if not ok:
                    bad.append((f, i, after, name, ans.status, ans.body, after_state == before))
            table.append((f, i, after, reached))
            if not reached and f not in _F6_NOT_REACHED:
                bad.append((f, i, after, "reached by neither route, and no reason is named"))
            if reached and f in _F6_NOT_REACHED:
                bad.append((f, i, after, "named as not reached, reached by", reached))
        for row in table:
            print("F6 handler", row)
        for row in bad:
            print("F6 BAD", row)
        assert bad == [], bad
    run_env(monkeypatch, body)
