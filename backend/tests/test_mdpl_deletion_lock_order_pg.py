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
   seeds it directly, as a matched pair that outlived its lease would. The
   ban runs as its route does (admin_ban: its signature check, then both
   identities' players rows FOR NO KEY UPDATE, then the core; round 1 found
   that a test of the core alone leaves those rows out).
4. The complete ban route against the deletion's bet refund (MDPL round 1's
   HIGH). P alone owns an open team lobby L, the moderator A holds an open
   wager on L, and X's ranked row is matched with P. The deletion holds L
   and X's ranked row, then disbands L and refunds A's wager, writing A's
   players row; admin_ban(A, X) holds A's and X's players rows and waits to
   delete X's ranked row. At 8d920c07 the deletion waits for A's row: a
   circle. With the fix it takes that row without a wait
   (_deletion_lock_party_row): held, the attempt ends and rolls back, the ban
   finishes, and the next attempt refunds the wager.
5. The hold half, through the bettor's own route. P hosts an open team
   lobby L1 and an open FFA lobby L2 (the lease guard bypassed for the
   second, the state its two gaps allow, as in scene 3), and B holds an
   open wager on each. The deletion disbands L1 and refunds B's wager there,
   so it holds B's players row, then reaches L2's wagers; meanwhile
   cancel_lobby_bet(B, L2) takes B's identity key, claims the L2 wager and
   writes B's players row. Without the identity key in the guard the cancel
   holds the wager row and waits for B's row while the deletion waits for
   the wager row. With it the cancel waits at its first statement.
6. The hold half for FFA bet rows. P's FFA lobby L3, closed with P's queue
   row still pointing at it, holds P's own unsettled wager on a game with no
   recorded result. The janitor's stranded-bet sweep claims it, with no
   lobby row, and waits for P's players row, which the deletion holds from
   its start; the deletion then reaches L3's reconcile and its claim of the
   same wager. With _deletion_lock_ffa_bet the claim does not wait.

Each test asserts what MDPL is to make true: both sides finish, and neither
ends in 40P01. On the base each fails at its "outcomes" assertion with one
side's 40P01, or, in scenes 4 to 6, with a bet helper's line naming the
deadlock (under _order_only the helper keeps the error): that failure is
the live reproduction MDPL's proof starts from.
The second test releases the deletion only after the ack's own deadlock
check has run, so that on the base the deletion is the side PostgreSQL ends:
the player's 500. Each runs with the bound's new attempts switched off
(_order_only), so on MDPL's build it proves the ORDER: a 40P01 there would
reach the test as it does on the base, not be run again.
"""

import asyncio
import hashlib
import hmac
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

ADMIN_SECRET = "mdpl-admin-secret"


def _admin_armed(env):
    """The ban route keeps its own admin check: a secret for the case, which _ban_route signs with."""
    env.mp.setattr(main, "ADMIN_HMAC_SECRET", ADMIN_SECRET)


def _ban_route(mod, target, reason="mdpl staged ban"):
    """admin_ban(mod, target) as the route runs it, fn(db) for env.call: its signature check (needs
    _admin_armed), then _mail_lock_identities on both identities, whose players rows it holds FOR NO
    KEY UPDATE, then the core. Round 1 found that a test of _apply_ban_core alone leaves those rows
    out."""
    sig = hmac.new(ADMIN_SECRET.encode(), main._admin_canonical(mod.sid, "ban", target.sid).encode(),
                   hashlib.sha256).hexdigest()
    req = main._AdminBanReq(admin_steam_id=mod.sid, target_steam_id=target.sid, reason=reason,
                            hmac_signature=sig)
    return lambda db: main.admin_ban(req, _slot=None, db=db)

KEY_SQL = "SELECT pg_advisory_xact_lock(hashtext('pc_snapshot'))"   # the deletion's blocking form only
TO_MARK = "WHERE relay_code IS NOT NULL AND steam_id = :sid"         # _ERASE_RELAY_DMS_TO_SQL
INTERNAL = "mdpl-internal-key"


async def _past_deadlock_check(env):
    """Sleeps past deadlock_timeout, so a backend already waiting has run its
    one deadlock check before the next wait begins."""
    ms = await env.conn.fetchval(
        "SELECT CAST(setting AS integer) FROM pg_settings WHERE name = 'deadlock_timeout'")
    await asyncio.sleep(ms / 1000.0 + 0.3)


def _order_only(env):
    """The bound's new attempts off (main._DELETION_RETRY_SQLSTATES empty), its
    budget wide and its wait cap off (main._DELETION_WAIT_CAP_S past any
    scene), so a test of the lock ORDER sees PostgreSQL's 40P01 as it is, no
    park in it meets the attempt's lock_timeout or deadline, and the
    deletion's blocking waits last as they did before the cap. The held
    signal still yields (that is what scenes 4 to 6 and (a) prove).
    raising=False: the base (732d96b1) has none of the names, and ignores
    them."""
    env.mp.setattr(main, "_DELETION_RETRY_SQLSTATES", frozenset(), raising=False)
    env.mp.setattr(main, "_DELETION_BUDGET_S", 120.0, raising=False)
    env.mp.setattr(main, "_DELETION_WAIT_CAP_S", 120.0, raising=False)


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
    ans = await env.mail(sender, [to], body="An ordinary message.")
    assert ans.status == 200 and ans["accepted"] is True, ans
    return uuid.UUID(str(ans["id"]))


def test_two_deletions_one_owning_a_print_of_the_others_card_both_finish(monkeypatch):
    async def body(env):
        _arm(env)
        _order_only(env)
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
        _order_only(env)
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
# The moderator is a players row with an admin_users row: player_bans.banned_by_steam_id references
# admin_users(steam_id).


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
        _admin_armed(env)
        _order_only(env)
        lid, (p, x) = await env.lobby("team", 2)
        (mod,) = await env.players(1)
        await env.conn.execute("INSERT INTO admin_users (steam_id, granted_at) VALUES ($1, NOW())"
                               " ON CONFLICT DO NOTHING", mod.sid)
        await _matched(env, p, x)
        await _matched(env, x, p)
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM team_queue WHERE series_id = $1 AND status = 'lobby'"
            "   AND player_id = ANY($2::uuid[])", lid, [p.id, x.id]) == 2

        at = _parks(env)
        spot = at(RANKED_MARK, "after")
        td = asyncio.create_task(_delete(env, p))
        # Parked right after its ranked step, the deletion holds x's ranked
        # row; with MDPL's order it holds the lobby as well (locked before
        # that step), where at 732d96b1 it does not hold the lobby yet.
        await _parked(spot, td)
        tb = asyncio.create_task(env.call(_ban_route(mod, x)))
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


async def _wager_ban_scene(env, capsys, *, guard_off=False):
    """Scene 4. Returns (the deletion's answer, the ban's answer, A's
    wager's status, A's gold_spent, everything printed meanwhile).
    guard_off: the mutant, _deletion_lock_party_row made a no-op, so that
    the deletion waits for A's row as it did at 8d920c07."""
    _arm(env)
    _admin_armed(env)
    _order_only(env)
    if guard_off:
        async def _no_guard(db, player_id, *, no_wait=False):
            return None
        env.mp.setattr(main, "_deletion_lock_party_row", _no_guard)
    capsys.readouterr()
    lid, (p,) = await env.lobby("team", 1)
    x, mod = await env.players(2)
    await env.conn.execute("INSERT INTO admin_users (steam_id, granted_at) VALUES ($1, NOW())"
                           " ON CONFLICT DO NOTHING", mod.sid)
    await env.conn.execute("UPDATE players SET gold_earned = 200, gold_spent = 100 WHERE id = $1", mod.id)
    bet = await env.conn.fetchval(
        "INSERT INTO lobby_bets (mode, lobby_id, player_id, amount, target_steams)"
        " VALUES ('team', $1, $2, 10, $3) RETURNING id", lid, mod.id, p.sid)
    await _matched(env, p, x)
    await _matched(env, x, p)
    at = _parks(env)
    spot = at(RANKED_MARK, "after")
    td = asyncio.create_task(_delete(env, p))
    await _parked(spot, td)                       # the deletion holds L and x's ranked row
    tb = asyncio.create_task(env.call(_ban_route(mod, x)))
    state, w = await _settle(env, tb, by=spot.pid)
    assert state == "waits", (state, w)           # admin_ban holds A's and X's players rows here
    await _past_deadlock_check(env)
    a, b = await _finish([td, tb], [spot])
    st = await env.conn.fetchval("SELECT status FROM lobby_bets WHERE id = $1", bet)
    spent = await env.conn.fetchval("SELECT gold_spent FROM players WHERE id = $1", mod.id)
    return a, b, st, spent, capsys.readouterr().out


def _circle_closed(a, b, out):
    """PostgreSQL ended a circle: a side's 40P01, or a bet helper's line
    that kept one (under _order_only the helper does not hand it back)."""
    return (_deadlock(a) or _deadlock(b) or "deadlock detected" in out
            or "DeadlockDetectedError" in out)


def test_a_ban_by_a_moderator_with_a_wager_on_the_lobby_and_a_deletion_both_finish(monkeypatch, capsys):
    """Scene 4. At 8d920c07 this fails at "outcomes": the deletion, the side
    PostgreSQL ends, is ended inside its bet helper, which keeps the error,
    so the wager stays open with the helper's line naming the deadlock."""
    async def body(env):
        a, b, st, spent, out = await _wager_ban_scene(env, capsys)
        assert not _circle_closed(a, b, out), (
            "outcomes", _name(a), _name(b), [ln for ln in out.splitlines() if "eadlock" in ln][:3])
        assert not _bad(a, b), ("outcomes", _name(a), _name(b))
        assert a.status == 200 and a["status"] == "anonymized", a
        assert b.status == 200, b
        assert (st, spent) == ("refunded", 90), (st, spent)
        assert "deletion attempt 1 met a held bet party row" in out, out[-2000:]
    case(monkeypatch, body, prefix="mdpl")


FFA_OPEN_MARK = "SELECT id, host_player_id FROM ffa_lobbies WHERE id=:lid AND status='open'"


def _cancel_sig(sid, mode, lid):
    return hmac.new(main.MATCH_HMAC_SECRET.encode(), ("lobby-bet-cancel:%s:%s:%s" % (sid, mode, lid)).encode(),
                    hashlib.sha256).hexdigest()


async def _cancel_scene(env, capsys, *, key_off=False, key_sql=None):
    """Scene 5. Returns (the deletion's answer, the cancel's answer, both
    wagers' status, B's gold_spent, everything printed meanwhile). key_off:
    the mutant, the guard's identity key never taken. key_sql: the mutant,
    the guard's key statement replaced by this one (point 4: a key of
    another form)."""
    _arm(env)
    _order_only(env)
    if key_off:
        env.mp.setattr(main, "_DELETION_PARTY_KEY_SQL", "SELECT true")
    if key_sql is not None:
        env.mp.setattr(main, "_DELETION_PARTY_KEY_SQL", key_sql)
    capsys.readouterr()
    l1, (p,) = await env.lobby("team", 1)
    gates = ("_locked_in_other_queue", "_formation_lease_conflict", "_lease_acquire")
    real = {g: getattr(main, g) for g in gates}

    async def _no_lease(db, player_id, joining_table):
        return None

    async def _no_lease_conflict(db, pairs, *args, **kwargs):
        return None

    async def _lease_granted(*args, **kwargs):
        return True
    # P is in L1 (a team lobby, with its lease) and also opens L2 (FFA), a state
    # the lease rules refuse: the three gates that refuse a second queue stand
    # aside for this one create (L2's seat takes no lease). The scene is about
    # the guard's key, not about how P came to hold two lobbies.
    env.mp.setattr(main, "_locked_in_other_queue", _no_lease)
    env.mp.setattr(main, "_formation_lease_conflict", _no_lease_conflict)
    env.mp.setattr(main, "_lease_acquire", _lease_granted)
    l2 = await env.create("ffa", p)
    for g in gates:
        env.mp.setattr(main, g, real[g])
    (b,) = await env.players(1)
    await env.conn.execute("UPDATE players SET gold_earned = 200, gold_spent = 100 WHERE id = $1", b.id)
    bets = []
    for mode, lid in (("team", l1), ("ffa", l2)):
        bets.append(await env.conn.fetchval(
            "INSERT INTO lobby_bets (mode, lobby_id, player_id, amount, target_steams)"
            " VALUES ($1, $2, $3, 10, $4) RETURNING id", mode, lid, b.id, p.sid))
    at = _parks(env)
    spot = at(FFA_OPEN_MARK, "before")
    td = asyncio.create_task(_delete(env, p))
    await _parked(spot, td)                       # L1 disbanded, B refunded: B's players row held
    tc = asyncio.create_task(env.call(lambda db: main.cancel_lobby_bet(
        steam_id=b.sid, mode="ffa", lobby_id=str(l2), sig=_cancel_sig(b.sid, "ffa", l2), db=db,
        request=None)))
    state, w = await _settle(env, tc, by=spot.pid)
    assert state == "waits", (state, w)           # at B's key with the fix; at B's players row without it
    await _past_deadlock_check(env)
    a, c = await _finish([td, tc], [spot])
    st = [await env.conn.fetchval("SELECT status FROM lobby_bets WHERE id = $1", x) for x in bets]
    spent = await env.conn.fetchval("SELECT gold_spent FROM players WHERE id = $1", b.id)
    return a, c, st, spent, capsys.readouterr().out


def test_a_deletion_holding_a_bettors_row_and_that_bettors_cancel_both_finish(monkeypatch, capsys):
    """Scene 5. The guard took B's identity key with B's row, so B's cancel
    waits at its first statement, holding no wager row; the deletion refunds
    the L2 wager and commits; the cancel then finds no open wager (404)."""
    async def body(env):
        a, c, st, spent, out = await _cancel_scene(env, capsys)
        assert not _circle_closed(a, c, out), (
            "outcomes", _name(a), _name(c), [ln for ln in out.splitlines() if "eadlock" in ln][:3])
        assert not _bad(a, c), ("outcomes", _name(a), _name(c))
        assert a.status == 200 and a["status"] == "anonymized", a
        assert c.status == 404, c
        assert (st, spent) == (["refunded", "refunded"], 80), (st, spent)
    case(monkeypatch, body, prefix="mdpl")


async def _sweep_scene(env, capsys, *, guard_off=False):
    """Scene 6. Returns (the deletion's answer, the sweep's answer, the
    wager's settlement kind, P's gold_spent, everything printed meanwhile).
    guard_off: the mutant, _deletion_lock_ffa_bet made a no-op."""
    _arm(env)
    _order_only(env)
    if guard_off:
        async def _no_guard(db, bet_id, *, no_wait=False):
            return None
        env.mp.setattr(main, "_deletion_lock_ffa_bet", _no_guard)
    capsys.readouterr()
    p, q = await env.players(2)
    l3 = await env.create("ffa", p)
    await env.conn.execute("UPDATE ffa_lobbies SET status = 'completed', completed_at = NOW() WHERE id = $1", l3)
    await env.conn.execute("UPDATE players SET gold_earned = 200, gold_spent = 100 WHERE id = $1", p.id)
    bet = await env.conn.fetchval(
        "INSERT INTO ffa_bets (lobby_id, game_number, player_id, bet_on_player_id, amount, odds_multiplier)"
        " VALUES ($1, 1, $2, $3, 10, 2.0) RETURNING id", l3, p.id, q.id)
    at = _parks(env)
    spot = at(RANKED_MARK, "after")
    td = asyncio.create_task(_delete(env, p))
    await _parked(spot, td)                       # holds P's players row

    async def sweep(db):
        await main._reconcile_ffa_lobby_bets(db, l3, "stranded-bet sweep")
        await db.commit()
        return {"status": "swept"}
    ts = asyncio.create_task(env.call(sweep))
    state, w = await _settle(env, ts, by=spot.pid)
    assert state == "waits", (state, w)           # the sweep holds the claim and waits for P's row
    await _past_deadlock_check(env)
    a, s = await _finish([td, ts], [spot])
    kind = await env.conn.fetchval("SELECT settlement_kind FROM ffa_bets WHERE id = $1", bet)
    spent = await env.conn.fetchval("SELECT gold_spent FROM players WHERE id = $1", p.id)
    return a, s, kind, spent, capsys.readouterr().out


def test_the_stranded_bet_sweep_and_a_deletion_both_finish(monkeypatch, capsys):
    """Scene 6. The deletion takes the wager without a wait: held by the
    sweep, its attempt ends and rolls back, the sweep refunds P's stake and
    commits, and the next attempt finds the wager settled."""
    async def body(env):
        a, s, kind, spent, out = await _sweep_scene(env, capsys)
        assert not _circle_closed(a, s, out), (
            "outcomes", _name(a), _name(s), [ln for ln in out.splitlines() if "eadlock" in ln][:3])
        assert not _bad(a, s), ("outcomes", _name(a), _name(s))
        assert a.status == 200 and a["status"] == "anonymized", a
        assert s.status == 200, s
        assert (kind, spent) == ("refunded", 90), (kind, spent)
        assert "deletion attempt 1 met a held FFA bet row" in out, out[-2000:]
    case(monkeypatch, body, prefix="mdpl")


PC_SHARDS_MARK = "UPDATE players SET pc_shards = 0 WHERE id = :pid"   # the deletion's first write of P's row
SESSIONS_MARK = "DELETE FROM steam_sessions WHERE steam_id = :sid"    # a blocking delete late in the attempt


async def _side_writes_p_after(env, p, lock_sql, *args):
    """A side session H: BEGIN; `lock_sql` (it takes a row the deletion comes
    to later); then a write of P's players row, and COMMIT. Returns (H's
    connection, the task of its write)."""
    side = await env.side()
    await side.execute("BEGIN")
    assert await side.fetchval(lock_sql, *args) is not None, lock_sql

    async def write_p():
        await side.execute("UPDATE players SET gold_earned = COALESCE(gold_earned, 0) WHERE id = $1", p.id)
        await side.execute("COMMIT")
        return "committed"
    return side, write_p


async def _step4_scene(env, capsys, *, blocking=False, gone_before=False):
    """(a)'s scene. P alone in team lobby L. The deletion parks right after
    its first write of P's players row; a lobby writer H takes L FOR UPDATE
    and then writes P's row, which waits for the deletion. Released, the
    deletion comes to its step-4 lock of L. blocking: the mutant, that lock
    taken with a wait, as at 8d920c07. gone_before: the mirror, H commits
    before the deletion is released, so the first attempt finds L free.
    Returns (the deletion's answer, H's outcome, everything printed)."""
    _arm(env)
    _order_only(env)
    if blocking:
        async def _wait_for_it(db, what, lock_stmt, seen_stmt, params):
            await db.execute(main.text(str(lock_stmt).replace(" SKIP LOCKED", "")), params)
        # raising=False: 8d920c07 has no such helper (its step-4 locks wait
        # already); at the fix a mutant that did not apply fails the control.
        env.mp.setattr(main, "_deletion_take_or_yield", _wait_for_it, raising=False)
    capsys.readouterr()
    lid, (p,) = await env.lobby("team", 1)
    at = _parks(env)
    spot = at(PC_SHARDS_MARK, "after")
    td = asyncio.create_task(_delete(env, p))
    await _parked(spot, td)                       # the deletion holds P's players row
    side, write_p = await _side_writes_p_after(
        env, p, "SELECT id FROM team_lobbies WHERE id = $1 FOR UPDATE", lid)
    th = None
    if gone_before:
        await side.execute("COMMIT")
    else:
        th = asyncio.create_task(write_p())
        state, w = await _settle(env, th, by=spot.pid)
        assert state == "waits", (state, w)       # H holds L and waits for P's row
    a, h = await _finish([td, th], [spot])
    return a, h, capsys.readouterr().out


def test_a_lobby_writer_holding_the_deletion_s_lobby_and_the_deletion_both_finish(monkeypatch, capsys):
    """(a). The deletion takes L without a wait: held by H, its attempt ends
    and rolls back, H writes P's row and commits, and the next attempt takes
    L. At 8d920c07 this fails at "outcomes": the deletion waits for L while
    H waits for P's row, and PostgreSQL ends H."""
    async def body(env):
        a, h, out = await _step4_scene(env, capsys)
        assert not _circle_closed(a, h, out), (
            "outcomes", _name(a), _name(h), [ln for ln in out.splitlines() if "eadlock" in ln][:3])
        assert not _bad(a, h), ("outcomes", _name(a), _name(h))
        assert a.status == 200 and a["status"] == "anonymized", a
        assert h == "committed", h
        assert "deletion attempt 1 met a held team_lobbies row" in out, out[-2000:]
    case(monkeypatch, body, prefix="mdpl")


async def _cap_scene(env, capsys, *, cap_off=False):
    """The option at the choke point. The deletion of P parks right before
    its blocking delete of P's sessions, holding P's players row; H holds
    P's session row and then writes P's players row, which waits for the
    deletion, so H's wait begins first. Released, the deletion waits for
    the session row: a circle. The cap is 0.5 s (_order_only sets it off);
    cap_off: the mutant, waits of the time left, as at 8d920c07. Returns
    (the deletion's answer, H's outcome, everything printed)."""
    _arm(env)
    _order_only(env)
    if not cap_off:
        env.mp.setattr(main, "_DELETION_WAIT_CAP_S", 0.5, raising=False)
    capsys.readouterr()
    (p,) = await env.players(1)
    await env.conn.execute(
        "INSERT INTO steam_sessions (steam_id, token_hash, verified, issued_at, expires_at)"
        " VALUES ($1, $2, true, NOW(), NOW() + INTERVAL '1 day')",
        p.sid, hashlib.sha256(("mdpl-cap-" + p.sid).encode()).hexdigest())
    at = _parks(env)
    spot = at(SESSIONS_MARK, "before")
    td = asyncio.create_task(_delete(env, p))
    await _parked(spot, td)                       # holds P's row and everything before; its sessions next
    side, write_p = await _side_writes_p_after(
        env, p, "SELECT steam_id FROM steam_sessions WHERE steam_id = $1 FOR UPDATE", p.sid)
    th = asyncio.create_task(write_p())
    state, w = await _settle(env, th, by=spot.pid)
    assert state == "waits", (state, w)           # H's wait begins first
    a, h = await _finish([td, th], [spot])
    return a, h, capsys.readouterr().out


def test_a_peer_that_began_to_wait_first_is_not_the_one_postgresql_ends(monkeypatch, capsys):
    """The option. The deletion leaves its wait at the cap, 0.5 s, before H's
    one deadlock check (deadlock_timeout, 1 s, after H's wait began): its
    attempt rolls back, H writes P's row and commits, and the next attempt
    answers 200. At 8d920c07 (one wait of the time left) this fails at
    "outcomes": PostgreSQL ends H."""
    async def body(env):
        a, h, out = await _cap_scene(env, capsys)
        assert not _circle_closed(a, h, out), (
            "outcomes", _name(a), _name(h), [ln for ln in out.splitlines() if "eadlock" in ln][:3])
        assert not _bad(a, h), ("outcomes", _name(a), _name(h))
        assert a.status == 200 and a["status"] == "anonymized", a
        assert h == "committed", h
        what = getattr(main, "_DELETION_WAIT_WHAT", "?")
        assert ("deletion attempt 1 met a held %s;" % what) in out, out[-2000:]
    case(monkeypatch, body, prefix="mdpl")


async def _upgrade_scene(env, capsys, *, cap_off=False):
    """The census's UPGRADE class. The deletion of P parks right after its
    first write of P's players row (FOR NO KEY UPDATE). H inserts a ledger
    row naming P (its foreign key takes FOR KEY SHARE on P's row, which does
    not conflict) and then writes P's row, which waits for the deletion.
    Once H's one deadlock check has run, the deletion is released and comes
    to its tombstone (P's steam_id, a column with a unique index): the flush
    needs FOR UPDATE on P's row and waits for H's FOR KEY SHARE, a circle.
    The cap is 0.5 s (_order_only sets it off); cap_off: the mutant, waits
    of the time left, as at 8d920c07. Returns (the deletion's answer, H's
    outcome, everything printed)."""
    _arm(env)
    _order_only(env)
    if not cap_off:
        env.mp.setattr(main, "_DELETION_WAIT_CAP_S", 0.5, raising=False)
    capsys.readouterr()
    (p,) = await env.players(1)
    at = _parks(env)
    spot = at(PC_SHARDS_MARK, "after")
    td = asyncio.create_task(_delete(env, p))
    await _parked(spot, td)                       # holds P's players row, FOR NO KEY UPDATE
    side = await env.side()
    await side.execute("BEGIN")
    await side.execute(
        "INSERT INTO gold_transactions (player_id, amount, reason, reference_id, created_at)"
        " VALUES ($1, 1, 'mdpl_upgrade', 'mdpl-upgrade', NOW())", p.id)   # FOR KEY SHARE on P's row

    async def write_p():
        await side.execute("UPDATE players SET gold_earned = COALESCE(gold_earned, 0) WHERE id = $1", p.id)
        await side.execute("COMMIT")
        return "committed"
    th = asyncio.create_task(write_p())
    state, w = await _settle(env, th, by=spot.pid)
    assert state == "waits", (state, w)           # H holds P's row FOR KEY SHARE and waits for it
    await _past_deadlock_check(env)               # H's one check has run, with no circle yet
    a, h = await _finish([td, th], [spot])
    return a, h, capsys.readouterr().out


def test_a_route_that_named_the_player_in_an_insert_and_a_deletion_both_finish(monkeypatch, capsys):
    """The UPGRADE class. The deletion's wait at its tombstone ends at the cap,
    before its own deadlock check (1 s), so PostgreSQL ends neither side: its
    attempt rolls back, H writes P's row and commits, and the next attempt
    answers 200. At 8d920c07 this fails at "outcomes": the deletion reaches
    its own check and is ended."""
    async def body(env):
        a, h, out = await _upgrade_scene(env, capsys)
        assert not _circle_closed(a, h, out), (
            "outcomes", _name(a), _name(h), [ln for ln in out.splitlines() if "eadlock" in ln][:3])
        assert not _bad(a, h), ("outcomes", _name(a), _name(h))
        assert a.status == 200 and a["status"] == "anonymized", a
        assert h == "committed", h
        what = getattr(main, "_DELETION_WAIT_WHAT", "?")
        assert ("deletion attempt 1 met a held %s;" % what) in out, out[-2000:]
    case(monkeypatch, body, prefix="mdpl")


# The deletion's relay pass (MDPL R4): the first statement after its
# tombstone's flush that no earlier statement of the deletion contains.
# Parked before it, the deletion holds P's players row FOR UPDATE and not yet
# P's revision row, which its invite bump (_invite_bump's `drop`) locks after
# the relay pass and before it deletes the row.
RELAY_PASS_MARK = main._ERASE_RELAY_DMS_LOCK_SQL


async def _phase_b_scene(env, capsys, *, cap_off=False):
    """The census's phase B. P has mail (an inbox revision row). The deletion
    of P parks just before its relay pass, after its tombstone's flush, so it
    holds P's players row FOR UPDATE and not yet P's revision row. H locks
    P's revision row without a wait, then inserts a ledger row naming P: its
    foreign key's FOR KEY SHARE on P's row waits for the deletion. Once H's
    one deadlock check has run, the deletion is released and its invite bump
    waits for H's revision row, a circle. The cap is 0.5 s; cap_off: the
    mutant, waits of the time left. Returns (the deletion's answer, H's
    outcome, everything printed)."""
    _arm(env)
    _order_only(env)
    if not cap_off:
        env.mp.setattr(main, "_DELETION_WAIT_CAP_S", 0.5, raising=False)
    p, q = await env.players(2)
    sent = await env.mail(q, [p])
    assert sent.status == 200, sent
    assert await env.conn.fetchval(
        "SELECT count(*) FROM mail_inbox_rev WHERE recipient_id = $1", p.id) == 1
    capsys.readouterr()
    at = _parks(env)
    spot = at(RELAY_PASS_MARK, "before")
    td = asyncio.create_task(_delete(env, p))
    await _parked(spot, td)                       # past the tombstone: P's row held FOR UPDATE
    side = await env.side()
    await side.execute("BEGIN")
    # NOWAIT holds the scene's premise: were P's revision row already the
    # deletion's, this fails at once instead of waiting for a deletion that
    # this test keeps parked.
    await side.execute("SELECT rev FROM mail_inbox_rev WHERE recipient_id = $1 FOR UPDATE NOWAIT", p.id)

    async def name_p():
        await side.execute(
            "INSERT INTO gold_transactions (player_id, amount, reason, reference_id, created_at)"
            " VALUES ($1, 1, 'mdpl_phase_b', 'mdpl-phase-b', NOW())", p.id)
        await side.execute("COMMIT")
        return "committed"
    th = asyncio.create_task(name_p())
    state, w = await _settle(env, th, by=spot.pid)
    assert state == "waits", (state, w)           # H's FOR KEY SHARE waits for the deletion's FOR UPDATE
    await _past_deadlock_check(env)
    a, h = await _finish([td, th], [spot])
    return a, h, capsys.readouterr().out


def test_a_route_holding_the_player_s_inbox_row_after_the_tombstone_and_a_deletion_both_finish(monkeypatch, capsys):
    """Phase B (the census's mail rows): the deletion's wait for H's revision
    row ends at the cap, before its own deadlock check, so PostgreSQL ends
    neither side: its attempt rolls back, H commits, and the next attempt
    answers 200. At 8d920c07 this fails at "outcomes": the deletion reaches
    its own check and is ended."""
    async def body(env):
        a, h, out = await _phase_b_scene(env, capsys)
        assert not _circle_closed(a, h, out), (
            "outcomes", _name(a), _name(h), [ln for ln in out.splitlines() if "eadlock" in ln][:3])
        assert not _bad(a, h), ("outcomes", _name(a), _name(h))
        assert a.status == 200 and a["status"] == "anonymized", a
        assert h == "committed", h
        what = getattr(main, "_DELETION_WAIT_WHAT", "?")
        assert ("deletion attempt 1 met a held %s;" % what) in out, out[-2000:]
    case(monkeypatch, body, prefix="mdpl")


def test_a_banned_host_s_lobby_and_the_next_member_s_deletion_after_the_tombstone_both_finish(monkeypatch, capsys):
    """_lobby_seat_left_core's host store (judged READ): when the stored host leaves, the
    earliest fresh member becomes host, an id neither caller keyed. Here P's deletion stands
    past its tombstone holding P's lobby rows, the ban of the host H waits for it at the lobby
    row, both finish, and the lobby stays open under Q, not P or H; the case-row pair stays
    under the class's scene."""
    async def body(env):
        _arm(env)
        _admin_armed(env)
        _order_only(env)
        lid, (h, p, q) = await env.lobby("team", 3)
        await env.fresh("team", lid)
        (mod,) = await env.players(1)
        await env.conn.execute(
            "INSERT INTO admin_users (steam_id, granted_at) VALUES ($1, NOW())"
            " ON CONFLICT DO NOTHING", mod.sid)
        capsys.readouterr()
        at = _parks(env)
        spot = at(RELAY_PASS_MARK, "before")
        td = asyncio.create_task(_delete(env, p))
        await _parked(spot, td)            # past the tombstone; P's lobby row held (main.py:47524-47527)
        tb = asyncio.create_task(env.call(_ban_route(mod, h)))
        state, w = await _settle(env, tb, by=spot.pid)
        assert state == "waits", (state, w)   # the ban core's FOR NO KEY UPDATE on the lobby row (main.py:51691-51693)
        await _past_deadlock_check(env)
        a, b = await _finish([td, tb], [spot])
        out = capsys.readouterr().out
        assert not _circle_closed(a, b, out), ("outcomes", _name(a), _name(b))
        assert not _bad(a, b), ("outcomes", _name(a), _name(b))
        assert a.status == 200 and a["status"] == "anonymized", a
        assert b.status == 200, b
        row = await env.conn.fetchrow(
            "SELECT status, host_player_id FROM team_lobbies WHERE id = $1", lid)
        assert (row["status"], row["host_player_id"]) == ("open", q.id), (dict(row), h.id, p.id, q.id)
        assert await env.conn.fetchval(
            "SELECT deleted_at IS NOT NULL FROM players WHERE id = $1", p.id), "P not tombstoned"
    case(monkeypatch, body, prefix="mdpl")
