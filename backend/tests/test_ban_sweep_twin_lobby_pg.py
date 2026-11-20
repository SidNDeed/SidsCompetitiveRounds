"""Bans part 2a, F2 c and BAN-R21 on PostgreSQL, through inv_pg (one cf_pg
case schema per case, the real handlers in main.py).

BAN-R21: after a ban the account holds no seat, lease, wager or invite of
its open lobby, and the remaining members' rows equal, field by field apart
from ids and times, those of a TWIN lobby whose member left by the leave
route. The lobby stays for the remaining members, the first of them becomes
host when the banned account was host, and with nobody left the lobby is
disbanded with its wagers refunded and its invites ended. Each mode with an
open lobby (2v2, 1v2, FFA) is driven; each scene is built twice from the
same steps, once ended by the ban core (_apply_ban_core, committed as
admin_ban commits it) and once by the leave route.

Mutants: the ban's open-lobby step ending nothing (the remaining members
keep a lobby whose host is gone, unlike the twin); the ban's invite step
ending nothing (the banned sender's invite stays pending).

Every account is a synthetic id of the case. No .env, key or cfg is read.
"""
import datetime
import decimal
import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

from inv_pg import LOBBY_TABLE, MODES, QUEUE_TABLE, case  # noqa: E402

import main  # noqa: E402
from ban_sweep_pg_bounds import bounded_pg  # noqa: E402,F401  (autouse: every session bounded)

# Columns that name an account or a row, or say when: they differ between the
# twins by construction and are compared by role instead (the host below).
_IDENTITY_COLS = frozenset({"id", "steam_id", "display_name", "player_name", "token_hash",
                            "series_id", "group_id", "generation", "room_name", "lobby_code",
                            "join_code", "invite_code", "password_hash", "name",
                            "target_steams"})


def _plain(row):
    """A row's fields apart from ids and times."""
    out = {}
    for k, v in dict(row).items():
        if k in _IDENTITY_COLS or k.endswith("_id") or k.endswith("_ids") or k.endswith("_at"):
            continue
        if isinstance(v, (uuid.UUID, datetime.datetime, datetime.date, datetime.timedelta)):
            continue
        if isinstance(v, decimal.Decimal):
            v = str(v)
        out[k] = v
    return out


async def _drain_now(db, pid):
    """_pc_lease_drain without its wait: no line is in flight in a case."""
    return 0.0


async def _admin(env):
    a = await env.player()
    await env.conn.execute("INSERT INTO admin_users (steam_id, granted_at) VALUES ($1, NOW())"
                           " ON CONFLICT DO NOTHING", a.sid)
    return a


async def _ban(env, admin, p):
    async def go(db):
        out = await main._apply_ban_core(db, admin_steam_id=admin.sid, target_steam_id=p.sid,
                                         reason="twin")
        await db.commit()
        return out
    ans = await env.call(go)
    assert ans.status == 200 and ans.body["status"] == "banned", ans
    return ans


async def _bet(env, mode, lid, bettor, target):
    """An open lobby-phase wager by `bettor` on `target` (the lobby_bets
    shapes migration 207 allows: 2v2 and FFA)."""
    if mode not in ("team", "ffa"):
        return None
    bid = uuid.uuid4()
    await env.conn.execute(
        "INSERT INTO lobby_bets (id, mode, lobby_id, player_id, amount, target_steams, status)"
        " VALUES ($1, $2, $3, $4, 25, $5, 'open')", bid, mode, lid, bettor.id, target.sid)
    await env.conn.execute(
        "UPDATE players SET gold_spent = COALESCE(gold_spent, 0) + 25,"
        " gold_earned = COALESCE(gold_earned, 0) + 100 WHERE id = $1", bettor.id)
    return bid


async def _scene(env, mode, n):
    """A lobby of `mode` with `n` members (the first its host), all polled
    now; the host's pending invite to an outsider; when n > 1 the second
    member's pending invite too; an outsider's open wager on the host and,
    for the account itself, its own wager on the second member."""
    lid, ps = await env.lobby(mode, n)
    await env.fresh(mode, lid)
    out1, out2, bettor = await env.players(3)
    invites = [await env.invite(ps[0], out1, mode, lid)]
    if n > 1:
        invites.append(await env.invite(ps[1], out2, mode, lid))
    bets = [await _bet(env, mode, lid, bettor, ps[0])]
    own = await _bet(env, mode, lid, ps[0], ps[1]) if n > 1 else None
    return {"lid": lid, "ps": ps, "invites": invites, "bets": [b for b in bets if b],
            "own": own, "bettor": bettor}


async def _observe(env, mode, s):
    """What a departure of the host leaves: the lobby row (its host by role),
    every remaining member's seat and leases, the invites, the wagers, the
    bettor's gold, and what the departed account still holds anywhere."""
    lid, ps = s["lid"], s["ps"]
    rest = ps[1:]
    lobby = await env.conn.fetchrow("SELECT * FROM %s WHERE id = $1" % LOBBY_TABLE[mode], lid)
    host = lobby["host_player_id"]
    role = "departed" if host == ps[0].id else (
        "member%d" % [p.id for p in rest].index(host) if host in [p.id for p in rest] else "other")
    seats = [_plain(await env.conn.fetchrow(
        "SELECT * FROM %s WHERE player_id = $1" % QUEUE_TABLE[mode], p.id) or {}) for p in rest]
    leases = [sorted(repr(sorted(_plain(r).items())) for r in await env.conn.fetch(
        "SELECT * FROM queue_leases WHERE player_id = $1", p.id)) for p in rest]
    invites = [_plain(await env.conn.fetchrow("SELECT * FROM lobby_invites WHERE id = $1", i))
               for i in s["invites"]]
    bets = [_plain(await env.conn.fetchrow("SELECT * FROM lobby_bets WHERE id = $1", b)) for b in s["bets"]]
    gold = tuple(await env.conn.fetchrow(
        "SELECT COALESCE(gold_earned, 0), COALESCE(gold_spent, 0) FROM players WHERE id = $1",
        s["bettor"].id))
    me = ps[0]
    held = {
        "seats": await env.conn.fetchval(
            "SELECT (SELECT count(*) FROM team_queue WHERE player_id = $1)"
            " + (SELECT count(*) FROM ovt_queue WHERE player_id = $1)"
            " + (SELECT count(*) FROM ffa_queue WHERE player_id = $1)"
            " + (SELECT count(*) FROM ranked_queue WHERE player_id = $1)", me.id),
        "leases": await env.conn.fetchval("SELECT count(*) FROM queue_leases WHERE player_id = $1", me.id),
        "invites": await env.conn.fetchval(
            "SELECT count(*) FROM lobby_invites WHERE state = 'pending'"
            " AND (sender_player_id = $1 OR invitee_player_id = $1)", me.id),
        "wagers": await env.conn.fetchval(
            "SELECT count(*) FROM lobby_bets WHERE status = 'open' AND player_id = $1", me.id),
    }
    return {"lobby": _plain(lobby), "host": role, "seats": seats, "leases": leases,
            "invites": invites, "bets": bets, "gold": gold}, held


async def _twins(env, mode, n, ban_mutant=None):
    """Both scenes, the first ended by the ban (with `ban_mutant`, a
    (main attribute, stand-in) pair, in place for the ban only), the second
    by the leave route."""
    env.mp.setattr(main, "_pc_lease_drain", _drain_now)
    admin = await _admin(env)
    a = await _scene(env, mode, n)
    b = await _scene(env, mode, n)
    if ban_mutant is not None:
        name, stand_in = ban_mutant
        real = getattr(main, name)
        setattr(main, name, stand_in)
        try:
            await _ban(env, admin, a["ps"][0])
        finally:
            setattr(main, name, real)
    else:
        await _ban(env, admin, a["ps"][0])
    left = await env.leave(mode, b["ps"][0], b["lid"])
    assert left.status == 200, left
    return await _observe(env, mode, a), await _observe(env, mode, b)


_NONE_HELD = {"seats": 0, "leases": 0, "invites": 0, "wagers": 0}


@pytest.mark.parametrize("mode", MODES)
def test_r21_a_banned_host_leaves_the_lobby_as_the_leave_route_does(monkeypatch, mode):
    """Host and two members: after the ban the first remaining member hosts,
    the lobby stays open, and every remaining row equals the twin's."""
    got = {}

    async def body(env):
        # a 1v2 lobby seats three: with two members it still takes the invite
        got["ban"], got["leave"] = await _twins(env, mode, 2 if mode == "ovt" else 3)
    case(monkeypatch, body)
    (ban, held), (leave, _left_held) = got["ban"], got["leave"]
    assert ban["host"] == "member0", ban["host"]
    # BAN-R21: the banned account keeps no seat, lease, wager or invite (the
    # leave route keeps a leaver's own lobby wager open; the ban refunds it)
    assert held == _NONE_HELD, held
    assert ban["lobby"].get("status") == "open", ban["lobby"]
    assert ban == leave, {k: (ban[k], leave[k]) for k in ban if ban[k] != leave[k]}


@pytest.mark.parametrize("mode", MODES)
def test_r21_a_banned_sole_member_disbands_the_lobby_with_refunds_as_the_leave_does(monkeypatch, mode):
    """Nobody remains: the lobby is disbanded, the outsider's wager on the
    host refunded and the host's invite ended, as when the host leaves."""
    got = {}

    async def body(env):
        got["ban"], got["leave"] = await _twins(env, mode, 1)
    case(monkeypatch, body)
    (ban, held), (leave, _left_held) = got["ban"], got["leave"]
    assert ban["lobby"].get("status") == "canceled", ban["lobby"]
    assert held == _NONE_HELD, held
    assert all(b.get("status") != "open" for b in ban["bets"]), ban["bets"]
    assert ban == leave, {k: (ban[k], leave[k]) for k in ban if ban[k] != leave[k]}


def test_r21_mutant_without_the_host_step_the_lobby_keeps_a_departed_host(monkeypatch):
    async def nothing(db, mode, lobby_id, pid):
        return [], False, []

    got = {}

    async def body(env):
        got["ban"], got["leave"] = await _twins(env, "team", 3, ban_mutant=("_lobby_seat_left_core", nothing))
    case(monkeypatch, body)
    assert got["ban"][0]["host"] == "departed", got["ban"][0]["host"]
    assert got["ban"][0] != got["leave"][0]


def test_r21_mutant_without_the_invite_step_the_banned_senders_invite_stays(monkeypatch):
    async def nothing(db, mode, lobby_id, player_ids):
        return []

    got = {}

    async def body(env):
        got["ban"], got["leave"] = await _twins(env, "team", 3, ban_mutant=("_invite_end_departed", nothing))
    case(monkeypatch, body)
    assert got["ban"][1]["invites"] >= 1, got["ban"][1]
    assert got["ban"][0]["invites"] != got["leave"][0]["invites"]


def test_r21_mutant_without_the_own_wager_step_the_banned_accounts_wager_stays(monkeypatch):
    real = main._refund_lobby_bets

    async def all_but_own(db, mode, lobby_id, reason, bettor=None):
        if bettor is not None:
            return 0
        return await real(db, mode, lobby_id, reason)

    got = {}

    async def body(env):
        got["ban"], got["leave"] = await _twins(env, "team", 3,
                                                ban_mutant=("_refund_lobby_bets", all_but_own))
    case(monkeypatch, body)
    assert got["ban"][1]["wagers"] == 1, got["ban"][1]


# ---------------------------------------------------------------- FIX-2 class III
# The ban leaves every open lobby through the ordinary leave's own core
# (_lobby_seat_left_core); the lobbies are found in the lobby tables.

def _core_mutant(old, new):
    """_lobby_seat_left_core with one branch changed (old occurs once)."""
    import inspect
    import textwrap
    src = textwrap.dedent(inspect.getsource(main._lobby_seat_left_core))
    assert src.count(old) == 1, old
    ns = dict(vars(main))
    exec(compile(src.replace(old, new), "<mutant>", "exec"), ns)
    return ns["_lobby_seat_left_core"]


_FRESH_BRANCH = (' AND {LOBBY_MEMBER_FRESH_SQL} ORDER BY', ' ORDER BY')
_DISBAND_BRANCH = ('await _refund_lobby_bets(db, mode, lobby_id, "lobby_disbanded")', 'pass')
_PROMOTE_BRANCH = ('if lrow["host_player_id"] == leaver_pid:', 'if False:')


async def _stale_host_twins(env, mode, mutant=None):
    """Reviewer case 1: the stored host's seat is stale and the departing
    account is the only fresh non-host. One twin's account is banned, the
    other's leaves by the route."""
    env.mp.setattr(main, "_pc_lease_drain", _drain_now)
    admin = await _admin(env)
    out = []
    for how in ("ban", "leave"):
        lid, ps = await env.lobby(mode, 2)
        await env.fresh(mode, lid)
        await env.stale(mode, ps[0], lid)
        bettor = (await env.players(1))[0]
        bet = await _bet(env, mode, lid, bettor, ps[0])
        if how == "ban":
            real = main._lobby_seat_left_core
            if mutant is not None:
                main._lobby_seat_left_core = mutant
            try:
                await _ban(env, admin, ps[1])
            finally:
                main._lobby_seat_left_core = real
        else:
            left = await env.leave(mode, ps[1], lid)
            assert left.status == 200, left
        out.append((await env.lobby_status(mode, lid),
                    await env.conn.fetchval("SELECT status FROM lobby_bets WHERE id = $1", bet)
                    if bet else None))
    return out


@pytest.mark.parametrize("mode", MODES)
def test_iii_case1_stale_host_and_the_only_fresh_member_departs_disbands_as_the_leave_does(monkeypatch, mode):
    got = {}

    async def body(env):
        got["v"] = await _stale_host_twins(env, mode)
    case(monkeypatch, body)
    ban, leave = got["v"]
    assert ban == leave and ban[0] == "canceled" and ban[1] in (None, "refunded"), got["v"]


def test_iii_mutant_the_core_without_its_freshness_filter_keeps_the_stale_lobby(monkeypatch):
    got = {}

    async def body(env):
        got["v"] = await _stale_host_twins(env, "team", _core_mutant(*_FRESH_BRANCH))
    case(monkeypatch, body)
    ban, leave = got["v"]
    assert ban[0] == "open" and ban != leave, got["v"]


def test_iii_mutant_the_core_without_its_disband_refund_leaves_the_wager_open(monkeypatch):
    got = {}

    async def body(env):
        got["v"] = await _stale_host_twins(env, "team", _core_mutant(*_DISBAND_BRANCH))
    case(monkeypatch, body)
    ban, leave = got["v"]
    assert ban[1] == "open" and ban != leave, got["v"]


def test_iii_mutant_the_core_without_its_promote_branch_keeps_a_departed_host(monkeypatch):
    got = {}

    async def body(env):
        got["ban"], got["leave"] = await _twins(
            env, "team", 3, ban_mutant=("_lobby_seat_left_core", _core_mutant(*_PROMOTE_BRANCH)))
    case(monkeypatch, body)
    assert got["ban"][0]["host"] == "departed" and got["ban"][0] != got["leave"][0], got["ban"][0]["host"]


@pytest.mark.parametrize("mode", MODES)
def test_iii_case2_a_banned_host_whose_own_seat_row_is_gone_hands_the_lobby_on(monkeypatch, mode):
    """Reviewer case 2: the account hosts an open lobby whose own expired seat
    row is already gone. The lobby is found by its host column; the earliest
    fresh member becomes host, as the core makes a stored host's successor."""
    got = {}

    async def body(env):
        env.mp.setattr(main, "_pc_lease_drain", _drain_now)
        admin = await _admin(env)
        lid, ps = await env.lobby(mode, 2)
        await env.fresh(mode, lid)
        await env.conn.execute("DELETE FROM %s WHERE player_id = $1" % QUEUE_TABLE[mode], ps[0].id)
        await _ban(env, admin, ps[0])
        got["v"] = (await env.lobby_status(mode, lid), await env.conn.fetchval(
            "SELECT host_player_id FROM %s WHERE id = $1" % LOBBY_TABLE[mode], lid) == ps[1].id)
    case(monkeypatch, body)
    assert got["v"] == ("open", True), got["v"]
