"""Bans part 2a, F2 c on PostgreSQL: the full live census.

Accounts are put into every live state the table census names
(ban_sweep_tables: each LIVE table), as many together as can coexist: each
account holds a session, a translation portal token, a queued
looking-for-players post, a card delivery lease and a spectator seat, and
one record of play: an active 1v1, 2v2 (with an open seat hold) or 1v2
series, an active FFA lobby, or an open 2v2, 1v2 or FFA lobby it hosts with
its pending invite and, where the mode takes them, its own open wager. Other
accounts wager on those records. Then every account is banned
(_apply_ban_core, committed as admin_ban commits it).

LIVE_CHECKS holds one query per LIVE table, named by it (the keys equal the
LIVE set, both ways). Each query counts the live rows of the banned accounts
and of their records; before the bans every count is above zero (the check
can fail), after them every count is zero. The other members of every voided
record keep no lease and no matched seat, as the void's own test states;
BAN-R21's field-by-field twin is test_ban_sweep_twin_lobby_pg.

Mutants: the spectate end doing nothing (the seat stays); the queued post's
delete matching nothing (the post stays).

Every account is a synthetic id of the case. No .env, key or cfg is read.
"""
import datetime
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.normpath(os.path.join(HERE, "..", "api")), HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import text  # noqa: E402

import main  # noqa: E402
from ban_sweep_pg_bounds import bounded_pg  # noqa: E402,F401  (autouse: every session bounded)
import test_title_ladder_hooks_live as lh  # noqa: E402
from ban_sweep_census import LIVE  # noqa: E402
from ban_sweep_tables import TABLE_CLASSES  # noqa: E402
from test_ban_sweep_live import _ban, _lease, _player, _session, _sid, _with_sm, case  # noqa: E402,F401


_SOON = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)


def _live(t):
    return main._ban_live_statuses_sql(t)


# :p the banned accounts' players.id, :s their steam ids, :r the ids of their
# records (series and lobbies).
LIVE_CHECKS = {
    "steam_sessions": "SELECT count(*) FROM steam_sessions WHERE steam_id = ANY(:s)",
    "i18n_portal_sessions": "SELECT count(*) FROM i18n_portal_sessions WHERE steam_id = ANY(:s)",
    "lfp_pings": "SELECT count(*) FROM lfp_pings WHERE steam_id = ANY(:s) AND posted_at IS NULL",
    "pc_delivery_leases": "SELECT count(*) FROM pc_delivery_leases WHERE subject_id = ANY(:p)",
    "spectate_leases": "SELECT count(*) FROM spectate_leases"
                       " WHERE spectator_steam_id = ANY(:s) AND revoked_at IS NULL",
    "queue_leases": "SELECT count(*) FROM queue_leases WHERE player_id = ANY(:p)",
    "ranked_queue": "SELECT count(*) FROM ranked_queue WHERE player_id = ANY(:p)",
    "team_queue": "SELECT count(*) FROM team_queue WHERE player_id = ANY(:p)",
    "ovt_queue": "SELECT count(*) FROM ovt_queue WHERE player_id = ANY(:p)",
    "ffa_queue": "SELECT count(*) FROM ffa_queue WHERE player_id = ANY(:p)",
    "ranked_series": "SELECT count(*) FROM ranked_series WHERE id = ANY(:r) AND status IN "
                     + _live("ranked_series"),
    "team_series": "SELECT count(*) FROM team_series WHERE id = ANY(:r) AND status IN "
                   + _live("team_series"),
    "ovt_series": "SELECT count(*) FROM ovt_series WHERE id = ANY(:r) AND status IN "
                  + _live("ovt_series"),
    "ffa_lobbies": "SELECT count(*) FROM ffa_lobbies WHERE id = ANY(:r) AND (status IN "
                   + _live("ffa_lobbies") + " OR (status = 'open' AND host_player_id = ANY(:p)))",
    "team_lobbies": "SELECT count(*) FROM team_lobbies WHERE status = 'open' AND host_player_id = ANY(:p)",
    "ovt_lobbies": "SELECT count(*) FROM ovt_lobbies WHERE status = 'open' AND host_player_id = ANY(:p)",
    "lobby_invites": "SELECT count(*) FROM lobby_invites WHERE state = 'pending'"
                     " AND (sender_player_id = ANY(:p) OR invitee_player_id = ANY(:p))",
    "lobby_bets": "SELECT count(*) FROM lobby_bets WHERE status = 'open' AND lobby_id = ANY(:r)"
                  " AND player_id = ANY(:p)",
    "bets": "SELECT count(*) FROM bets WHERE settled_at IS NULL AND series_id = ANY(:r)",
    "team_bets": "SELECT count(*) FROM team_bets WHERE settled_at IS NULL AND team_series_id = ANY(:r)",
    "ffa_bets": "SELECT count(*) FROM ffa_bets WHERE settled_at IS NULL AND lobby_id = ANY(:r)",
    "match_seat_holds": "SELECT count(*) FROM match_seat_holds WHERE closed_at IS NULL"
                        " AND (player_id = ANY(:p) OR series_id = ANY(:r))",
}


async def _drain_now(db, pid):
    """_pc_lease_drain without its wait: no line is in flight in a case."""
    return 0.0


async def _common(db, pid, sid):
    """The states that coexist with any record: session, portal token,
    queued post, delivery lease, spectator seat."""
    await _session(db, sid)
    await db.execute(text(
        "INSERT INTO i18n_portal_sessions (token, steam_id, bound_ip, expires_at)"
        " VALUES (:t, :s, '127.0.0.1', NOW() + INTERVAL '1 hour')"), {"t": uuid.uuid4().hex, "s": sid})
    await db.execute(text(
        "INSERT INTO lfp_pings (steam_id, expires_at) VALUES (:s, NOW() + INTERVAL '1 hour')"), {"s": sid})
    await db.execute(text(
        "INSERT INTO pc_delivery_leases (subject_id, until) VALUES (:p, NOW() + INTERVAL '1 minute')"),
        {"p": pid})
    gid = uuid.uuid4()
    await lh._insert(db, "spectate_games", {"id": gid, "mode": "ranked",
                                            "room_name": "lc-room-" + uuid.uuid4().hex[:8],
                                            "fighter_target": 2})
    await db.execute(text(
        "INSERT INTO spectate_leases (id, token_hash, game_id, spectator_steam_id,"
        " join_expires_at, heartbeat_expires_at)"
        " VALUES (:i, :th, :g, :s, NOW() + INTERVAL '1 minute', NOW() + INTERVAL '1 minute')"),
        {"i": uuid.uuid4(), "th": uuid.uuid4().hex, "g": gid, "s": sid})


async def _bettor(db, stake=10):
    return await _player(db, _sid(), gold_spent=stake, gold_earned=100)


async def _queue(db, table, pid, sid, status, series_id=None):
    row = {"player_id": pid, "status": status}
    if table != "ranked_queue":
        row.update(steam_id=sid, display_name="lc-" + sid[-4:], series_id=series_id)
    await lh._insert(db, table, row)


async def _world(sm):
    """Seven banned accounts, each in its records' live states; returns
    (banned steam ids, banned players.ids, record ids, other members)."""
    banned, others, records = {}, {}, []
    async with sm() as db:
        async def account(k):
            sid = _sid()
            pid = await _player(db, sid)
            await _common(db, pid, sid)
            banned[k] = (sid, pid)
            return sid, pid

        async def member(k):
            sid = _sid()
            pid = await _player(db, sid)
            others.setdefault(k, []).append(pid)
            return sid, pid

        # an active 1v1 series, both seats matched, both leases, a wager on it
        xs, xp = await account("ranked")
        rs_, rp = await member("ranked")
        rs = uuid.uuid4()
        await lh._insert(db, "ranked_series", {"id": rs, "player1_id": xp, "player2_id": rp,
                                               "status": "active"})
        await lh._insert(db, "ranked_queue", {"player_id": xp, "status": "matched", "matched_with": rp})
        await lh._insert(db, "ranked_queue", {"player_id": rp, "status": "matched", "matched_with": xp})
        await _lease(db, xp, "ranked", None)
        await _lease(db, rp, "ranked", None)
        await lh._insert(db, "bets", {"player_id": await _bettor(db), "series_id": rs,
                                      "bet_on_player_id": rp, "amount": 10, "odds_multiplier": 2.0})
        records.append(rs)

        # an active 2v2 series, every seat matched and leased, an open seat
        # hold of the account, a wager on it
        xs, xp = await account("team")
        mates = [await member("team") for _ in range(3)]
        ts = uuid.uuid4()
        await lh._insert(db, "team_series", {"id": ts, "t1a_id": xp, "t1b_id": mates[0][1],
                                             "t2a_id": mates[1][1], "t2b_id": mates[2][1],
                                             "status": "active"})
        for s, p in [(xs, xp), *mates]:
            await _queue(db, "team_queue", p, s, "matched", ts)
            await _lease(db, p, "team", ts)
        room = "lc-team-" + uuid.uuid4().hex[:8]
        game = uuid.uuid4()
        await lh._insert(db, "match_games", {"id": game, "mode": "team", "series_id": ts,
                                             "room_name": room, "seq": 1})
        await db.execute(text(
            "INSERT INTO match_seat_holds (mode, room_name, series_id, game_id, player_id, n, slot,"
            " team, opener_player_id, held_anchor_at, held_at, held_until)"
            " VALUES ('team', :room, :ts, :g, :p, 1, 0, 0, :o, NOW(), NOW(), NOW() + INTERVAL '2 minutes')"),
            {"room": room, "ts": ts, "g": game, "p": xp, "o": mates[0][1]})
        await lh._insert(db, "team_bets", {"player_id": await _bettor(db), "team_series_id": ts,
                                           "bet_on_team": 2, "amount": 10, "odds_multiplier": 2.0})
        records.append(ts)

        # an active 1v2 series, the account solo
        xs, xp = await account("ovt")
        duo = [await member("ovt") for _ in range(2)]
        os_ = uuid.uuid4()
        await lh._insert(db, "ovt_series", {"id": os_, "solo_id": xp, "duo_a_id": duo[0][1],
                                            "duo_b_id": duo[1][1], "status": "active"})
        records.append(os_)

        # an active FFA lobby, every seat matched and leased, a wager on it
        xs, xp = await account("ffa")
        ffa = [await member("ffa") for _ in range(2)]
        fl = uuid.uuid4()
        await lh._insert(db, "ffa_lobbies", {"id": fl, "status": "active", "games_played": 0,
                                             "member_ids": [xp] + [p for _s, p in ffa],
                                             "host_player_id": ffa[0][1]})
        for s, p in [(xs, xp), *ffa]:
            await _queue(db, "ffa_queue", p, s, "matched", fl)
            await _lease(db, p, "ffa", fl)
        await lh._insert(db, "ffa_bets", {"lobby_id": fl, "game_number": 1,
                                          "player_id": await _bettor(db),
                                          "bet_on_player_id": ffa[0][1], "amount": 10,
                                          "odds_multiplier": 2.0})
        records.append(fl)

        # an open lobby of each mode the account hosts, two seated members,
        # its pending invite, and (2v2, FFA) its own open wager on a member
        for mode, lt, qt in (("team", "team_lobbies", "team_queue"),
                             ("ovt", "ovt_lobbies", "ovt_queue"),
                             ("ffa", "ffa_lobbies", "ffa_queue")):
            xs, xp = await account("open-" + mode)
            seated = [await member("open-" + mode) for _ in range(2)]
            lid = uuid.uuid4()
            row = {"id": lid, "host_player_id": xp, "status": "open"}
            if mode == "ffa":
                row["games_played"] = 0
            await lh._insert(db, lt, row)
            for s, p in [(xs, xp), *seated]:
                await _queue(db, qt, p, s, "lobby", lid)
            outsider = await _player(db, _sid())
            await lh._insert(db, "lobby_invites", {"mode": mode, "lobby_id": lid,
                                                   "sender_player_id": xp,
                                                   "invitee_player_id": outsider,
                                                   "state": "pending", "kind": "invite",
                                                   "expires_at": _SOON})
            if mode != "ovt":
                await db.execute(text(
                    "INSERT INTO lobby_bets (id, mode, lobby_id, player_id, amount, target_steams, status)"
                    " VALUES (:i, :m, :l, :p, 25, :t, 'open')"),
                    {"i": uuid.uuid4(), "m": mode, "l": lid, "p": xp, "t": seated[0][0]})
                await db.execute(text(
                    "UPDATE players SET gold_spent = COALESCE(gold_spent, 0) + 25,"
                    " gold_earned = COALESCE(gold_earned, 0) + 100 WHERE id = :p"), {"p": xp})
            records.append(lid)
        await db.commit()
    return banned, others, records


async def _census(sm, banned, records):
    binds = {"p": [p for _s, p in banned.values()], "s": [s for s, _p in banned.values()],
             "r": records}
    out = {}
    async with sm() as db:
        for t, q in LIVE_CHECKS.items():
            q = (q.replace("ANY(:p)", "ANY(CAST(:p AS uuid[]))")
                  .replace("ANY(:s)", "ANY(CAST(:s AS text[]))")
                  .replace("ANY(:r)", "ANY(CAST(:r AS uuid[]))"))
            out[t] = (await db.execute(text(q), binds)).scalar()
    return out


async def _others_held(sm, others):
    """Leases and matched seats the other members of the voided records hold."""
    pids = [p for k, ps in others.items() if not k.startswith("open-") for p in ps]
    async with sm() as db:
        leases = (await db.execute(text(
            "SELECT count(*) FROM queue_leases WHERE player_id = ANY(CAST(:p AS uuid[]))"),
            {"p": pids})).scalar()
        matched = (await db.execute(text(
            "SELECT (SELECT count(*) FROM ranked_queue WHERE player_id = ANY(CAST(:p AS uuid[])))"
            " + (SELECT count(*) FROM team_queue WHERE status = 'matched' AND player_id = ANY(CAST(:p AS uuid[])))"
            " + (SELECT count(*) FROM ffa_queue WHERE status = 'matched' AND player_id = ANY(CAST(:p AS uuid[])))"),
            {"p": pids})).scalar()
    return leases, matched


async def _run_census(sm, monkeypatch):
    monkeypatch.setattr(main, "_pc_lease_drain", _drain_now)
    banned, others, records = await _world(sm)
    before = await _census(sm, banned, records)
    for sid, _pid in banned.values():
        await _ban(sm, sid)
    return before, await _census(sm, banned, records), await _others_held(sm, others)


def test_the_live_checks_are_the_live_tables_both_ways():
    live = {t for t, (c, _w) in TABLE_CLASSES.items() if c == LIVE}
    assert set(LIVE_CHECKS) == live, (sorted(live - set(LIVE_CHECKS)), sorted(set(LIVE_CHECKS) - live))


def test_f2_c_every_live_state_of_a_banned_account_ends(case, monkeypatch):
    before, after, (leases, matched) = _with_sm(case, lambda sm: _run_census(sm, monkeypatch))
    assert all(n > 0 for n in before.values()), {t: n for t, n in before.items() if not n}
    assert after == {t: 0 for t in LIVE_CHECKS}, {t: n for t, n in after.items() if n}
    assert (leases, matched) == (0, 0), (leases, matched)


def test_f2_c_mutant_without_the_spectate_end_the_seat_stays(case, monkeypatch):
    async def nothing(db, steam_id, lease_id=None):
        return None
    monkeypatch.setattr(main, "_spectate_leave_rows", nothing)
    _before, after, _held = _with_sm(case, lambda sm: _run_census(sm, monkeypatch))
    assert after["spectate_leases"] == 7, after
    assert {t: n for t, n in after.items() if n} == {"spectate_leases": 7}, after


def test_f2_c_mutant_the_queued_post_delete_matching_nothing_leaves_the_post(case, monkeypatch):
    real = main.text

    def rewritten(sql, *a, **kw):
        if isinstance(sql, str) and sql.startswith("DELETE FROM lfp_pings WHERE steam_id"):
            sql = sql.replace("WHERE steam_id", "WHERE false AND steam_id")
        return real(sql, *a, **kw)
    monkeypatch.setattr(main, "text", rewritten)
    _before, after, _held = _with_sm(case, lambda sm: _run_census(sm, monkeypatch))
    assert {t: n for t, n in after.items() if n} == {"lfp_pings": 7}, after


# ---------------------------------------------------------------- FIX-2 class II
# Two account columns the census above did not seed: the spectator of a lease
# held by an authenticated account with NO players row, and the INVITEE of a
# pending invite. Each ends with the ban; each mutant leaves it standing.

async def _no_row_spectator(sm):
    """A session-only account (no players row) holding a spectate lease."""
    sid = _sid()
    async with sm() as db:
        await db.execute(text(
            "INSERT INTO steam_sessions (token_hash, steam_id, verified, issued_at, expires_at)"
            " VALUES (:th, :s, true, NOW(), NOW() + INTERVAL '1 day')"),
            {"th": "lc-" + uuid.uuid4().hex, "s": sid})
        gid = uuid.uuid4()
        await lh._insert(db, "spectate_games", {"id": gid, "mode": "ranked",
                                                "room_name": "lc-room-" + uuid.uuid4().hex[:8],
                                                "fighter_target": 2})
        await db.execute(text(
            "INSERT INTO spectate_leases (id, token_hash, game_id, spectator_steam_id,"
            " join_expires_at, heartbeat_expires_at)"
            " VALUES (:i, :th, :g, :s, NOW() + INTERVAL '1 minute', NOW() + INTERVAL '1 minute')"),
            {"i": uuid.uuid4(), "th": uuid.uuid4().hex, "g": gid, "s": sid})
        await db.commit()
    return sid


async def _live_spectate(sm, sid):
    async with sm() as db:
        return (await db.execute(text(
            "SELECT count(*) FROM spectate_leases WHERE spectator_steam_id = :s AND revoked_at IS NULL"),
            {"s": sid})).scalar()


def test_ii_the_spectate_lease_of_an_account_without_a_players_row_ends(case, monkeypatch):
    monkeypatch.setattr(main, "_pc_lease_drain", _drain_now)

    async def body(sm):
        sid = await _no_row_spectator(sm)
        before = await _live_spectate(sm, sid)
        await _ban(sm, sid)
        return before, await _live_spectate(sm, sid)
    assert _with_sm(case, body) == (1, 0)


async def _incoming_invite(sm):
    """X holds a pending invite from Y to Y's open 2v2 lobby."""
    xs = _sid()
    async with sm() as db:
        xp = await _player(db, xs)
        yp = await _player(db, _sid())
        lid = uuid.uuid4()
        await lh._insert(db, "team_lobbies", {"id": lid, "host_player_id": yp, "status": "open"})
        iid = uuid.uuid4()
        await lh._insert(db, "lobby_invites", {"id": iid, "mode": "team", "lobby_id": lid,
                                               "sender_player_id": yp, "invitee_player_id": xp,
                                               "state": "pending", "kind": "invite",
                                               "expires_at": _SOON})
        await db.commit()
    return xs, iid


def _invite_body(monkeypatch):
    monkeypatch.setattr(main, "_pc_lease_drain", _drain_now)

    async def body(sm):
        xs, iid = await _incoming_invite(sm)
        await _ban(sm, xs)
        async with sm() as db:
            return tuple((await db.execute(text(
                "SELECT state, end_reason FROM lobby_invites WHERE id = :i"), {"i": iid})).first())
    return body


def test_ii_a_pending_invite_to_the_banned_account_ends(case, monkeypatch):
    assert _with_sm(case, _invite_body(monkeypatch)) == ("void", "invitee_kicked")


def test_ii_mutant_without_the_incoming_invite_end_the_invite_stays_pending(case, monkeypatch):
    monkeypatch.setattr(main, "_INVITE_END_INVITEE_SQL",
                        "SELECT CAST(NULL AS uuid) WHERE CAST(:pid AS uuid) IS NULL")
    assert _with_sm(case, _invite_body(monkeypatch)) == ("pending", None)


# ---------------------------------------------------------------- FIX-3 section 1
# The typed census (ban_sweep_columns): every uuid or steam column of every
# LIVE table, read from this database's catalog, is typed an account column or
# not (both ways), and each account column's disposition is shown on seeded
# rows: END rows of the banned accounts are gone after the ban, rows of
# accounts the ban does not name stand (control), STAND rows stay.
import ban_sweep_columns as BC  # noqa: E402

_LIVE_TABLES = {t for t, (c, _w) in TABLE_CLASSES.items() if c == LIVE}

# the row predicate of a live row of each LIVE table (what the void ends)
LIVE_ROW = {
    "bets": "settled_at IS NULL", "ffa_bets": "settled_at IS NULL", "team_bets": "settled_at IS NULL",
    "lobby_bets": "status = 'open'",
    "ffa_lobbies": "(status IN " + _live("ffa_lobbies") + " OR status = 'open')",
    "team_lobbies": "status = 'open'", "ovt_lobbies": "status = 'open'",
    "ffa_queue": "true", "team_queue": "true", "ovt_queue": "true", "ranked_queue": "true",
    "ranked_series": "status IN " + _live("ranked_series"),
    "team_series": "status IN " + _live("team_series"),
    "ovt_series": "status IN " + _live("ovt_series"),
    "lobby_invites": "state = 'pending'", "match_seat_holds": "closed_at IS NULL",
    "pc_delivery_leases": "true", "queue_leases": "true", "spectate_leases": "revoked_at IS NULL",
    "steam_sessions": "true", "i18n_portal_sessions": "true", "lfp_pings": "posted_at IS NULL",
}


def _column_check(t, c):
    key = "CAST(:s AS text[])" if "steam" in c else "CAST(:p AS uuid[])"
    return f"SELECT count(*) FROM {t} WHERE {c} = ANY({key}) AND {LIVE_ROW[t]}"


async def _catalog(sm):
    async with sm() as db:
        rows = (await db.execute(text(
            "SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns"
            " WHERE table_schema = current_schema()"))).all()
    return [(t, c, ty) for t, c, ty, _n in rows], {(t, c) for t, c, _ty, n in rows if n == "NO"}


def test_s1_the_typed_census_is_the_catalog_both_ways(case):
    cols, notnull = _with_sm(case, _catalog)
    keys = BC.catalog_key_set(cols, _LIVE_TABLES)
    assert len(keys) >= 60, len(keys)
    assert BC.census_failures(keys) == []
    # every NO_ROW ruling: the table's player_id is NOT NULL
    for (t, c), states in BC.ACCOUNT_COLUMNS.items():
        if states.get("NONE", (None,))[0] == BC.NO_ROW:
            assert (t, "player_id") in notnull, (t, c)
    assert set(LIVE_ROW) == _LIVE_TABLES


def test_s1_planted_columns_fail_the_census_both_ways(case):
    cols, _nn = _with_sm(case, _catalog)
    keys = BC.catalog_key_set(cols, _LIVE_TABLES)
    assert BC.census_failures(keys | {("bets", "planted_steam_id")}) == [
        "('bets', 'planted_steam_id'): in the catalog and typed in neither table"]
    acct = dict(BC.ACCOUNT_COLUMNS)
    acct[("bets", "gone_column")] = {"HAS": (BC.END, "planted")}
    assert BC.census_failures(keys, account=acct) == [
        "('bets', 'gone_column'): typed and not in the catalog"]


_END_HAS = sorted(k for k, s in BC.ACCOUNT_COLUMNS.items() if s["HAS"][0] == BC.END)


async def _seed_typed(sm):
    """Rows the census world above does not hold, one per END column it
    misses, for three more banned accounts; the same rows for three accounts
    the ban does not name (control)."""
    out = {"banned": [], "control": []}
    async with sm() as db:
        for role in ("banned", "control"):
            acc = []
            for _ in range(3):
                s = _sid()
                acc.append((s, await _player(db, s)))
            out[role] += acc
            (_s1, p1), (_s2, p2), (s3, p3) = acc
            mate = await _player(db, _sid())
            rs = uuid.uuid4()
            await lh._insert(db, "ranked_series", {"id": rs, "player1_id": mate, "player2_id": p1,
                                                   "status": "active", "winner_id": p1})
            await lh._insert(db, "bets", {"player_id": await _bettor(db), "series_id": rs,
                                          "bet_on_player_id": p1, "amount": 10, "odds_multiplier": 2.0})
            await lh._insert(db, "ranked_queue", {"player_id": p3, "steam_id": s3, "status": "waiting"})
            ts = uuid.uuid4()
            await lh._insert(db, "team_series", {"id": ts, "t1a_id": mate, "t1b_id": p1,
                                                 "t2a_id": p2, "t2b_id": p3, "status": "active",
                                                 "dc_player_id": p1, "dc_fallback_player_id": p1})
            room = "lc-tc-" + uuid.uuid4().hex[:8]
            game = uuid.uuid4()
            await lh._insert(db, "match_games", {"id": game, "mode": "team", "series_id": ts,
                                                 "room_name": room, "seq": 1})
            await db.execute(text(
                "INSERT INTO match_seat_holds (mode, room_name, series_id, game_id, player_id, n, slot,"
                " team, opener_player_id, held_anchor_at, held_at, held_until)"
                " VALUES ('team', :room, :ts, :g, :p, 1, 0, 0, :o, NOW(), NOW(), NOW() + INTERVAL '2 minutes')"),
                {"room": room, "ts": ts, "g": game, "p": mate, "o": p1})
            await lh._insert(db, "ovt_series", {"id": uuid.uuid4(), "solo_id": mate, "duo_a_id": p1,
                                                "duo_b_id": p2, "status": "active", "dc_player_id": p1})
            fl = uuid.uuid4()
            await lh._insert(db, "ffa_lobbies", {"id": fl, "status": "active", "games_played": 0,
                                                 "member_ids": [mate, p1, p2],
                                                 "host_player_id": mate, "first_leaver": p1})
            await lh._insert(db, "ffa_bets", {"lobby_id": fl, "game_number": 1,
                                              "player_id": await _bettor(db),
                                              "bet_on_player_id": p1, "amount": 10,
                                              "odds_multiplier": 2.0})
            host = await _player(db, _sid())
            lid = uuid.uuid4()
            await lh._insert(db, "team_lobbies", {"id": lid, "host_player_id": host, "status": "open"})
            await lh._insert(db, "lobby_invites", {"mode": "team", "lobby_id": lid, "sender_player_id": host,
                                                   "invitee_player_id": p3, "state": "pending",
                                                   "kind": "invite", "expires_at": _SOON})
        await db.commit()
    return out


async def _typed_counts(sm, accounts, keys):
    binds = {"p": [p for _s, p in accounts], "s": [s for s, _p in accounts]}
    async with sm() as db:
        return {k: (await db.execute(text(_column_check(*k)), binds)).scalar() for k in keys}


def _typed_body(monkeypatch):
    monkeypatch.setattr(main, "_pc_lease_drain", _drain_now)

    async def body(sm):
        banned, _others, _records = await _world(sm)
        seeded = await _seed_typed(sm)
        acc = list(banned.values()) + seeded["banned"]
        before = await _typed_counts(sm, acc, _END_HAS)
        ctrl_before = await _typed_counts(sm, seeded["control"], _END_HAS)
        for sid, _pid in acc:
            await _ban(sm, sid)
        return (before, await _typed_counts(sm, acc, _END_HAS),
                ctrl_before, await _typed_counts(sm, seeded["control"], _END_HAS))
    return body


def test_s1_every_end_column_of_a_banned_account_with_a_players_row_ends(case, monkeypatch):
    before, after, ctrl_before, ctrl_after = _with_sm(case, _typed_body(monkeypatch))
    assert [k for k, n in before.items() if not n] == []
    assert after == {k: 0 for k in _END_HAS}, {k: n for k, n in after.items() if n}
    # control: the accounts the ban does not name keep every row they had
    assert ctrl_after == ctrl_before, (ctrl_before, ctrl_after)


_END_NONE = sorted(k for k, s in BC.ACCOUNT_COLUMNS.items() if s.get("NONE", (None,))[0] == BC.END)


async def _no_row_account(sm):
    """A session-only account (no players row) in every steam-keyed live
    state an account without a players row can hold."""
    sid = _sid()
    async with sm() as db:
        await _session(db, sid)
        await db.execute(text(
            "INSERT INTO i18n_portal_sessions (token, steam_id, bound_ip, expires_at)"
            " VALUES (:t, :s, '127.0.0.1', NOW() + INTERVAL '1 hour')"), {"t": uuid.uuid4().hex, "s": sid})
        await db.execute(text(
            "INSERT INTO lfp_pings (steam_id, expires_at) VALUES (:s, NOW() + INTERVAL '1 hour')"), {"s": sid})
        await db.commit()
    await _live_spectate_seed(sm, sid)
    return sid


async def _live_spectate_seed(sm, sid):
    async with sm() as db:
        gid = uuid.uuid4()
        await lh._insert(db, "spectate_games", {"id": gid, "mode": "ranked",
                                                "room_name": "lc-room-" + uuid.uuid4().hex[:8],
                                                "fighter_target": 2})
        await db.execute(text(
            "INSERT INTO spectate_leases (id, token_hash, game_id, spectator_steam_id,"
            " join_expires_at, heartbeat_expires_at)"
            " VALUES (:i, :th, :g, :s, NOW() + INTERVAL '1 minute', NOW() + INTERVAL '1 minute')"),
            {"i": uuid.uuid4(), "th": uuid.uuid4().hex, "g": gid, "s": sid})
        await db.commit()


def _none_body(monkeypatch):
    monkeypatch.setattr(main, "_pc_lease_drain", _drain_now)

    async def body(sm):
        sid = await _no_row_account(sm)
        ctrl = await _no_row_account(sm)
        acc, cacc = [(sid, None)], [(ctrl, None)]
        before = await _typed_counts(sm, acc, _END_NONE)
        await _ban(sm, sid)
        return before, await _typed_counts(sm, acc, _END_NONE), await _typed_counts(sm, cacc, _END_NONE)
    return body


def test_s1_every_end_column_of_a_banned_account_without_a_players_row_ends(case, monkeypatch):
    before, after, ctrl = _with_sm(case, _none_body(monkeypatch))
    assert all(n > 0 for n in before.values()), before
    assert after == {k: 0 for k in _END_NONE}, {k: n for k, n in after.items() if n}
    assert all(n > 0 for n in ctrl.values()), ctrl


def test_s1_mutant_the_queued_post_delete_back_inside_the_players_row_block(case, monkeypatch):
    """1.4: the post of an account without a players row is ended by the
    delete keyed on its steam id outside the players-row block; with the
    delete back inside the block (the base shape) the post stays."""
    src = textwrap.dedent(inspect.getsource(main._apply_ban_core))
    moved = src.replace(_LFP_OUTSIDE, "")
    assert moved.count(_LFP_OUTSIDE) == 0 and src.count(_LFP_OUTSIDE) == 1
    moved = moved.replace(_LFP_INSIDE_ANCHOR, _LFP_INSIDE_ANCHOR + _LFP_INSIDE)
    ns = dict(vars(main))
    exec(compile(moved, "<mutant>", "exec"), ns)
    monkeypatch.setattr(main, "_apply_ban_core", ns["_apply_ban_core"])
    _before, after, _ctrl = _with_sm(case, _none_body(monkeypatch))
    assert {k: n for k, n in after.items() if n} == {("lfp_pings", "steam_id"): 1}, after


def _stand_body(monkeypatch):
    monkeypatch.setattr(main, "_pc_lease_drain", _drain_now)

    async def body(sm):
        """X wagers on a series of two other accounts, sits on the kicked list
        of another account's open lobby of each mode, and is the target of
        another account's lobby-phase wager in a lobby X is not in."""
        xs = _sid()
        async with sm() as db:
            xp = await _player(db, xs, gold_spent=10, gold_earned=100)
            a = await _player(db, _sid())
            b = await _player(db, _sid())
            rs = uuid.uuid4()
            await lh._insert(db, "ranked_series", {"id": rs, "player1_id": a, "player2_id": b,
                                                   "status": "active"})
            await lh._insert(db, "bets", {"player_id": xp, "series_id": rs, "bet_on_player_id": a,
                                          "amount": 10, "odds_multiplier": 2.0})
            for lt in ("team_lobbies", "ovt_lobbies", "ffa_lobbies"):
                row = {"id": uuid.uuid4(), "host_player_id": a, "status": "open", "kicked_steam_ids": xs}
                if lt == "ffa_lobbies":
                    row["games_played"] = 0
                await lh._insert(db, lt, row)
            lid = uuid.uuid4()
            await lh._insert(db, "team_lobbies", {"id": lid, "host_player_id": b, "status": "open"})
            await db.execute(text(
                "INSERT INTO lobby_bets (id, mode, lobby_id, player_id, amount, target_steams, status)"
                " VALUES (:i, 'team', :l, :p, 25, :t, 'open')"),
                {"i": uuid.uuid4(), "l": lid, "p": b, "t": xs})
            await db.commit()
        q = {"bets": "SELECT count(*) FROM bets WHERE player_id = :p AND settled_at IS NULL",
             "kicked": "SELECT count(*) FROM (SELECT kicked_steam_ids FROM team_lobbies UNION ALL"
                       " SELECT kicked_steam_ids FROM ovt_lobbies UNION ALL SELECT kicked_steam_ids"
                       " FROM ffa_lobbies) k WHERE kicked_steam_ids = :s",
             "target": "SELECT count(*) FROM lobby_bets WHERE target_steams = :s AND status = 'open'"}

        async def counts():
            async with sm() as db:
                return {k: (await db.execute(text(v), {"p": xp, "s": xs})).scalar() for k, v in q.items()}
        before = await counts()
        await _ban(sm, xs)
        return before, await counts()
    return body


def test_s1_every_stand_column_stays(case, monkeypatch):
    before, after = _with_sm(case, _stand_body(monkeypatch))
    assert before == {"bets": 1, "kicked": 3, "target": 1}, before
    assert after == before, after
    stands = sorted(k for k, s in BC.ACCOUNT_COLUMNS.items() if any(d == BC.STAND for d, _w in s.values()))
    assert stands == [("bets", "player_id"), ("ffa_bets", "player_id"), ("ffa_lobbies", "kicked_steam_ids"),
                      ("lobby_bets", "target_steams"), ("ovt_lobbies", "kicked_steam_ids"),
                      ("team_bets", "player_id"), ("team_lobbies", "kicked_steam_ids")], stands


import inspect  # noqa: E402
import textwrap  # noqa: E402

# 1.4: the queued post is deleted keyed on the steam id itself, outside the
# players-row block (an account without a players row can hold one).
_LFP_OUTSIDE = ('    await db.execute(text(\n'
                '        "DELETE FROM lfp_pings WHERE steam_id = :sid AND posted_at IS NULL"\n'
                '    ), {"sid": target_steam_id})\n')
_LFP_INSIDE = ('        await db.execute(text(\n'
               '            "DELETE FROM lfp_pings WHERE steam_id = :sid AND posted_at IS NULL"\n'
               '        ), {"sid": target_steam_id})\n')
_LFP_INSIDE_ANCHOR = "        await _ban_void_apply(db, _bpid, _ban_void_found)\n"


# ---------------------------------------------------------------- FIX-3 section 2 b, c
_SPECTATE_OUTSIDE = "    await _spectate_leave_rows(db, target_steam_id)\n"
_SPECTATE_INSIDE = "        await _spectate_leave_rows(db, target_steam_id)\n"


def _spectate_body(monkeypatch):
    monkeypatch.setattr(main, "_pc_lease_drain", _drain_now)

    async def body(sm):
        sid = await _no_row_spectator(sm)
        ctrl = await _no_row_spectator(sm)
        await _ban(sm, sid)
        return await _live_spectate(sm, sid), await _live_spectate(sm, ctrl)
    return body


def test_ii_b_control_the_lease_of_an_account_the_ban_does_not_name_stays(case, monkeypatch):
    assert _with_sm(case, _spectate_body(monkeypatch)) == (0, 1)


def test_ii_b_mutant_the_spectate_end_inside_the_players_row_block(case, monkeypatch):
    """The base shape: the spectate end inside the players-row block. The lease
    of an account without a players row then stays."""
    src = textwrap.dedent(inspect.getsource(main._apply_ban_core))
    assert src.count(_SPECTATE_OUTSIDE) == 1 and src.count(_LFP_INSIDE_ANCHOR) == 1
    moved = src.replace(_SPECTATE_OUTSIDE, "").replace(
        _LFP_INSIDE_ANCHOR, _LFP_INSIDE_ANCHOR + _SPECTATE_INSIDE)
    ns = dict(vars(main))
    exec(compile(moved, "<mutant>", "exec"), ns)
    monkeypatch.setattr(main, "_apply_ban_core", ns["_apply_ban_core"])
    assert _with_sm(case, _spectate_body(monkeypatch)) == (1, 1)


def test_ii_a_control_a_pending_invite_to_an_account_the_ban_does_not_name_stays(case, monkeypatch):
    monkeypatch.setattr(main, "_pc_lease_drain", _drain_now)

    async def body(sm):
        xs, _iid = await _incoming_invite(sm)
        _ys, other = await _incoming_invite(sm)
        await _ban(sm, xs)
        async with sm() as db:
            return tuple((await db.execute(text(
                "SELECT state, end_reason FROM lobby_invites WHERE id = :i"), {"i": other})).first())
    assert _with_sm(case, body) == ("pending", None)


# 1.2 STAND, settled by its own writer: the banned account's wagers on a 1v1
# series, a 2v2 series and an FFA game of OTHER accounts stand after the ban,
# and each record's own settle writer then pays them (the wagers are on the
# winner). Control: the record's other bettor, not banned, is paid alike.
async def _bettor_world(sm, xs):
    async with sm() as db:
        xp = await _player(db, xs)
        cp = await _player(db, _sid())
        a, b, c, d = [await _player(db, _sid()) for _ in range(4)]
        rs, ts, fl = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        await lh._insert(db, "ranked_series", {"id": rs, "player1_id": a, "player2_id": b, "status": "active"})
        await lh._insert(db, "team_series", {"id": ts, "t1a_id": a, "t1b_id": b, "t2a_id": c, "t2b_id": d,
                                             "status": "active"})
        await lh._insert(db, "ffa_lobbies", {"id": fl, "status": "active", "games_played": 0,
                                             "member_ids": [a, b, c], "host_player_id": a})
        for p in (xp, cp):
            await lh._insert(db, "bets", {"player_id": p, "series_id": rs, "bet_on_player_id": a,
                                          "amount": 10, "odds_multiplier": 2.0})
            await lh._insert(db, "team_bets", {"player_id": p, "team_series_id": ts, "bet_on_team": 1,
                                               "amount": 10, "odds_multiplier": 2.0})
            await lh._insert(db, "ffa_bets", {"lobby_id": fl, "game_number": 1, "player_id": p,
                                              "bet_on_player_id": a, "amount": 10, "odds_multiplier": 2.0})
        await db.commit()
    return xp, cp, a, rs, ts, fl


_BET_ROWS = ("SELECT 'bets', payout, settled_at IS NOT NULL FROM bets WHERE player_id = :p"
             " UNION ALL SELECT 'team_bets', payout, settled_at IS NOT NULL FROM team_bets WHERE player_id = :p"
             " UNION ALL SELECT 'ffa_bets', payout, settled_at IS NOT NULL FROM ffa_bets WHERE player_id = :p"
             " ORDER BY 1")


def _bettor_body(monkeypatch):
    monkeypatch.setattr(main, "_pc_lease_drain", _drain_now)

    async def body(sm):
        xs = _sid()
        xp, cp, a, rs, ts, fl = await _bettor_world(sm, xs)
        await _ban(sm, xs)

        async def rows(p):
            async with sm() as db:
                return [tuple(r) for r in (await db.execute(text(_BET_ROWS), {"p": p})).all()]
        stood = await rows(xp)
        async with sm() as db:
            await db.execute(text("UPDATE ranked_series SET status = 'completed', winner_id = :a WHERE id = :s"), {"a": a, "s": rs})
            await db.execute(text("UPDATE team_series SET status = 'completed', winner_team = 1 WHERE id = :s"), {"s": ts})
            await db.commit()
        async with sm() as db:
            await main._settle_series_bets(db, await db.get(main.RankedSeries, rs))
            await main._reconcile_team_series_bets(db, ts, "ban-sweep stand settle")
            await main._settle_ffa_bets_for_game(db, fl, 1, a)
            await db.commit()
        return stood, await rows(xp), await rows(cp)
    return body


def test_s1_the_bettor_stand_rows_stay_and_their_own_writers_settle_them(case, monkeypatch):
    stood, banned_after, control_after = _with_sm(case, _bettor_body(monkeypatch))
    assert [(t, s) for t, _p, s in stood] == [("bets", False), ("ffa_bets", False), ("team_bets", False)], stood
    assert all(s and p and p > 0 for _t, p, s in banned_after), banned_after
    assert [t for t, _p, _s in banned_after] == ["bets", "ffa_bets", "team_bets"]
    assert banned_after == control_after, (banned_after, control_after)
