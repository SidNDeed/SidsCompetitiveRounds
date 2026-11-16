"""MDPL (mail-deletion-purge-lock-order), the account deletion's lock order: two
lock circles a reading of main at 732d96b1 found reachable, run live through
test_mail_case_scrub_pg.py's harness (inv_pg's case schema, the real handlers).

1. Two deletions and a card print. delete_player_data deletes the prints its
   player OWNS before it takes the global pc_snapshot key (blocking form,
   exclusive, held to its commit), and the prints of its player's CARD,
   whoever owns them, after the key. Q owns a print of P's card, and no
   pc_events or pc_trades row names both (a pulled print older than the
   events' seven days): P holds the key and waits for Q's print; Q holds
   the print and waits for the key.
2. One deletion and the bot's relay acknowledgement. The deletion deletes
   the relay rows addressed TO its player, then the rows its player SENT.
   The ack route settles (retry) a DM P sent, then acks a DM addressed to
   P, in one transaction: it holds the first and waits for the second,
   which the deletion holds, while the deletion waits for the first.

3. A moderator's ban against a deletion, staged. The deletion deletes the
   ranked_queue rows naming its player (SKIP LOCKED, held to its commit)
   before it locks its lobbies; the ban locks its target's open lobby and
   then deletes the target's ranked_queue row, waiting. The state the
   circle needs (X's ranked row matched with P while X and P share an open
   lobby) is out of reach of the lease guard in steady state; the fixture
   seeds it directly, as a matched pair that outlived its lease would.

Each test asserts what MDPL is to make true: both sides finish, and neither
ends in 40P01. On the base each fails at its "outcomes" assertion with one
side's 40P01: that failure is the live reproduction MDPL's proof starts from.
The second test releases the deletion only after the ack's own deadlock
check has run, so that on the base the deletion is the side PostgreSQL ends:
the player's 500.
"""

import asyncio
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

from inv_pg import case  # noqa: E402

import main  # noqa: E402
from test_mail_case_scrub_pg import (  # noqa: E402
    _arm, _bad, _deadlock, _delete, _finish, _name, _parked, _parks, _relay_row, _settle)

KEY_SQL = "SELECT pg_advisory_xact_lock(hashtext('pc_snapshot'))"   # the deletion's blocking form only
TO_MARK = "WHERE relay_code IS NOT NULL AND steam_id = :sid"         # _ERASE_RELAY_DMS_TO_SQL
INTERNAL = "mdpl-internal-key"


async def _past_deadlock_check(env):
    """Sleeps past deadlock_timeout, so a backend already waiting has run its
    one deadlock check before the next wait begins."""
    ms = await env.conn.fetchval(
        "SELECT CAST(setting AS integer) FROM pg_settings WHERE name = 'deadlock_timeout'")
    await asyncio.sleep(ms / 1000.0 + 0.3)


async def _edition(env):
    await env.conn.execute(
        "INSERT INTO pc_editions (name) SELECT 'Edition 1'"
        " WHERE NOT EXISTS (SELECT 1 FROM pc_editions WHERE ended_at IS NULL)")


async def _print_of(env, owner, subject):
    """One print of `subject`'s card, owned by `owner`; no event and no trade."""
    return await env.conn.fetchval(
        "WITH card AS ("
        "  INSERT INTO pc_cards (subject_player_id, edition_id)"
        "  VALUES ($2, (SELECT id FROM pc_editions WHERE ended_at IS NULL ORDER BY id LIMIT 1))"
        "  ON CONFLICT (subject_player_id, edition_id, variant) DO UPDATE SET variant = EXCLUDED.variant"
        "  RETURNING id)"
        " INSERT INTO pc_prints (card_id, owner_player_id, snapshot_id, rarity, pool_rank, source)"
        " SELECT id, $1, 1, 'common', 1, 'pack' FROM card RETURNING id", owner.id, subject.id)


async def _sent(env, sender, to):
    ans = await env.mail(sender, to, body="An ordinary message.")
    assert ans.status == 200 and ans["accepted"] is True, ans
    return uuid.UUID(str(ans["id"]))


def test_two_deletions_one_owning_a_print_of_the_others_card_both_finish(monkeypatch):
    async def body(env):
        _arm(env)
        await _edition(env)
        p, q = await env.players(2)
        pr = await _print_of(env, q, p)
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM pc_events WHERE player_id = ANY($1::uuid[])"
            "    OR subject_player_id = ANY($1::uuid[])", [p.id, q.id]) == 0
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM pc_trades WHERE pair_lo = ANY($1::uuid[]) OR pair_hi = ANY($1::uuid[])",
            [p.id, q.id]) == 0
        at = _parks(env)
        spot = at(KEY_SQL, "after")
        tp = asyncio.create_task(_delete(env, p))
        await _parked(spot, tp)                       # P holds the key
        tq = asyncio.create_task(_delete(env, q))
        state, w = await _settle(env, tq, by=spot.pid)
        assert state == "waits" and (w["query"] or "").startswith(KEY_SQL), (state, w)
        await _past_deadlock_check(env)
        a, b = await _finish([tp, tq], [spot])
        assert not _bad(a, b), ("outcomes", _name(a), _name(b), "40P01", [_deadlock(a), _deadlock(b)])
        assert a.status == 200 and a["status"] == "anonymized", a
        assert b.status == 200 and b["status"] == "anonymized", b
        assert await env.conn.fetchval("SELECT COUNT(*) FROM pc_prints WHERE id = $1", pr) == 0
    case(monkeypatch, body, prefix="mdpl")


def test_a_deletion_and_the_relay_ack_both_finish(monkeypatch):
    async def body(env):
        _arm(env)
        monkeypatch.setenv("API_SECRET_KEY", INTERNAL)
        p, t = await env.players(2)
        r_from = await _relay_row(env, t, p, await _sent(env, p, t))     # SENT by P, handed out
        r_to = await _relay_row(env, p, t, await _sent(env, t, p))       # addressed TO P
        claim = uuid.uuid4()
        await env.conn.execute(
            "UPDATE pending_dms SET claim_id = $2, claim_until = NOW() + make_interval(mins => 5)"
            " WHERE id = $1", r_from, claim)
        report = main._PendingDmAck(dm_ids=[str(r_to)], retry_ids=[str(r_from)],
                                    claims={str(r_from): str(claim)})
        at = _parks(env)
        spot = at(TO_MARK, "after")
        td = asyncio.create_task(_delete(env, p))
        await _parked(spot, td)                       # the deletion holds r_to
        tb = asyncio.create_task(env.call(
            lambda db: main.ack_pending_dms(report, x_internal_key=INTERNAL, db=db)))
        state, w = await _settle(env, tb, by=spot.pid)
        assert state == "waits", (state, w)
        await _past_deadlock_check(env)
        a, b = await _finish([td, tb], [spot])
        assert not _bad(a, b), ("outcomes", _name(a), _name(b), "40P01", [_deadlock(a), _deadlock(b)])
        assert a.status == 200 and a["status"] == "anonymized", a
        assert b.status == 200, b
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM pending_dms WHERE id = ANY($1::bigint[])", [r_from, r_to]) == 0
    case(monkeypatch, body, prefix="mdpl")


RANKED_MARK = "OR matched_with = :pid"      # the deletion's ranked_queue DELETE (its verify read comes after it)
ADMIN = "76561190000000001"                 # a synthetic moderator id; the ban core takes it as a string


async def _matched(env, a, b):
    """A ranked_queue row of `a`, matched with `b`, before any room."""
    await env.conn.execute(
        "INSERT INTO ranked_queue (player_id, steam_id, display_name, rating, rating_deviation, ranked_only,"
        "                          status, matched_with, ready, joined_at, matched_at, last_polled)"
        " VALUES ($1, $2, $3, 1500, 350, false, 'matched', $4, false, NOW(), NOW(), NOW())",
        a.id, a.sid, a.name, b.id)


def test_a_ban_and_a_deletion_sharing_a_lobby_and_a_ranked_match_both_finish(monkeypatch):
    async def body(env):
        _arm(env)
        lid, (p, x) = await env.lobby("team", 2)
        await _matched(env, p, x)
        await _matched(env, x, p)
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM team_queue WHERE series_id = $1 AND status = 'lobby'"
            "   AND player_id = ANY($2::uuid[])", lid, [p.id, x.id]) == 2

        async def ban(db):
            out = await main._apply_ban_core(db, admin_steam_id=ADMIN, target_steam_id=x.sid,
                                             reason="mdpl staged ban")
            await db.commit()
            return out

        at = _parks(env)
        spot = at(RANKED_MARK, "after")
        td = asyncio.create_task(_delete(env, p))
        await _parked(spot, td)                       # the deletion holds x's ranked row, not yet the lobby
        tb = asyncio.create_task(env.call(ban))
        state, w = await _settle(env, tb, by=spot.pid)
        assert state == "waits", (state, w)
        await _past_deadlock_check(env)
        a, b = await _finish([td, tb], [spot])
        assert not _bad(a, b), ("outcomes", _name(a), _name(b), "40P01", [_deadlock(a), _deadlock(b)])
        assert a.status == 200 and a["status"] == "anonymized", a
        assert b.status == 200, b
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM ranked_queue WHERE player_id = ANY($1::uuid[])", [p.id, x.id]) == 0
    case(monkeypatch, body, prefix="mdpl")
