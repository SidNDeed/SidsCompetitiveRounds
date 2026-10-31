"""The tournament fence on PostgreSQL, through the real app
(discord_collection_harness, DISCORD_COLLECTION_TEST_PG_DSN; a missing DSN
FAILS by name unless DISCORD_COLLECTION_TEST_PG_OPTOUT says otherwise).

1. Brackets of 9-14 players lock. Before the full-topology builder,
   lock_tournament raised IndexError for every such field, so the tournament
   could never leave voting. Here a field locks, the losers bracket is
   persisted at full topology, a locked withdrawal goes through the bot's
   path (speculative promotion when the pool has someone, bye collapse when
   it does not), the tournament starts, and the REAL resolver
   (_activate_ready_matches) drives it to a terminal grand final:
   structural vacancies become byes instead of parking the losers bracket.
   _maybe_complete_tournament then accepts the result.
2. The locked-leave gate, as the server states it: during voting a player
   may leave with their own session; once locked, an unsignup requires
   confirm_locked_leave (409 without it), the internal key (403 without it)
   and the player's CURRENT Discord link as discord_id (409 when absent or
   different); once running, every unsignup is refused (400).
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

import discord_collection_harness as H  # noqa: F401  (the harness the wrapper builds on)
import test_discord_tournament_quorum as Q
from discord_collection_harness import SCHEMA

TERMINAL = ("completed", "forfeit", "double_forfeit", "bye_auto")

MATCHES = (
    "SELECT m.id::text AS id, m.bracket_side AS side, m.round AS round, m.is_bye AS is_bye,"
    "       m.status AS status, m.prereq_roles AS roles,"
    "       cardinality(m.prereq_match_ids) AS n_prereqs,"
    "       m.p1_signup_id::text AS p1, m.p2_signup_id::text AS p2,"
    "       m.winner_signup_id::text AS w"
    f"  FROM {SCHEMA}.tournament_matches m"
    " WHERE m.tournament_id = CAST(:t AS uuid)")
SIGNUPS = (
    "SELECT ts.id::text AS sid, ts.player_id::text AS pid, ts.is_speculative AS spec,"
    "       g.rating AS rating"
    f"  FROM {SCHEMA}.tournament_signups ts"
    f"  LEFT JOIN {SCHEMA}.glicko_ratings g ON g.player_id = ts.player_id"
    " WHERE ts.tournament_id = CAST(:t AS uuid)")


async def async_tournament(env, entrants, speculative=()):
    """An async double-elimination tournament (the format the creation cron
    writes; the model's default is single elimination) in voting with
    `entrants` confirmed and `speculative` in the pool; lock_tournament is
    called directly, so its lock_at is irrelevant here."""
    import models
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with AsyncSession(env.seed) as s:
        t = models.Tournament(kind="async", status="voting", format="double_elim_bo3",
                              default_start_ts=now + timedelta(days=1),
                              lock_at=now + timedelta(days=1), voting_closes_at=now + timedelta(days=1),
                              min_players=8, max_players=16)
        s.add(t)
        await s.flush()
        # Read before the commit: the commit expires `t`, and reloading an
        # expired attribute is IO this coroutine cannot do implicitly.
        tid = str(t.id)
        for who in entrants:
            s.add(models.TournamentSignup(tournament_id=t.id, player_id=who.id, is_speculative=False))
        for who in speculative:
            s.add(models.TournamentSignup(tournament_id=t.id, player_id=who.id, is_speculative=True))
        await s.commit()
        return tid


async def lock(env, tid):
    import models

    async def go(db, T):
        t = await db.get(models.Tournament, uuid.UUID(tid))
        performed = await T.lock_tournament(db, t)
        return performed, t.status
    return await Q.in_app(env, go)


async def start(env, tid):
    import models

    async def go(db, T):
        t = await db.get(models.Tournament, uuid.UUID(tid))
        await T.start_tournament(db, t)
        return t.status
    return await Q.in_app(env, go)


async def activate(env, tid):
    await Q.in_app(env, lambda db, T: T._activate_ready_matches(db, uuid.UUID(tid)))


async def complete(env, tid):
    import models

    async def go(db, T):
        t = await db.get(models.Tournament, uuid.UUID(tid))
        await T._maybe_complete_tournament(db, t)
        return t.status
    return await Q.in_app(env, go)


def bot_leave(env, tid, who, discord_id="same"):
    """The bot's availability-check "No": internal key, confirmed, bound to
    the clicker's Discord id (discord_id=None omits it)."""
    body = {"steam_id": who.steam, "confirm_locked_leave": True}
    if discord_id == "same":
        body["discord_id"] = str(who.discord)
    elif discord_id is not None:
        body["discord_id"] = str(discord_id)
    return env.client.post(f"/api/v1/tournaments/{tid}/unsignup", json=body, headers=env.ihead())


def player_leave(env, tid, who, **extra):
    """The game client's Leave: the player's own session, no internal key."""
    body = {"steam_id": who.steam}
    body.update(extra)
    return env.client.post(f"/api/v1/tournaments/{tid}/unsignup", json=body, headers=env.mod_headers(who))


async def drive_to_the_end(env, tid, cap=60):
    """Play every live match (the higher-rated seat wins, so the top seed is
    the winners-bracket champion and the grand final needs no reset), then
    let the REAL resolver advance the bracket; until nothing is pending."""
    rating = {r["sid"]: float(r["rating"] or 0) for r in await env.rows(SIGNUPS, {"t": tid})}
    for _ in range(cap):
        rows = await env.rows(MATCHES, {"t": tid})
        if all(r["status"] in TERMINAL for r in rows):
            return rows, rating
        live = [r for r in rows if r["status"] in ("ready", "scheduled") and r["p1"] and r["p2"]]
        for r in live:
            win = r["p1"] if rating[r["p1"]] >= rating[r["p2"]] else r["p2"]
            await env.ex(f"UPDATE {SCHEMA}.tournament_matches SET status = 'completed',"
                         " winner_signup_id = CAST(:w AS uuid), ended_at = now()"
                         " WHERE id = CAST(:m AS uuid)", {"w": win, "m": r["id"]})
        before = [(r["id"], r["status"]) for r in rows]
        await activate(env, tid)
        after = [(r["id"], r["status"]) for r in await env.rows(MATCHES, {"t": tid})]
        assert live or before != after, "wedged: %r" % sorted(
            (r["side"], r["round"], r["status"]) for r in rows if r["status"] not in TERMINAL)
    raise AssertionError("did not converge")


def assert_double_elimination(rows, withdrawn=()):
    losses = {}
    for r in rows:
        if r["status"] == "completed":
            loser = r["p1"] if r["w"] == r["p2"] else r["p2"]
            losses[loser] = losses.get(loser, 0) + 1
    gf = [r for r in rows if r["side"] == "GF"]
    assert len(gf) == 1 and gf[0]["status"] in TERMINAL and gf[0]["w"], gf
    champ = gf[0]["w"]
    gf_loser = (gf[0]["p1"] if gf[0]["w"] == gf[0]["p2"] else gf[0]["p2"]) \
        if gf[0]["status"] == "completed" else None
    seated = {s for r in rows for s in (r["p1"], r["p2"], r["w"]) if s} - set(withdrawn)
    for sid in seated:
        n = losses.get(sid, 0)
        assert n <= 2, (sid, n)
        if n == 0:
            assert sid == champ, ("0-loss non-champion cut from the bracket", sid)
        if n == 1 and sid != champ:
            assert sid == gf_loser, ("live player cut after ONE loss", sid)
    return champ


async def bracket_case(env, n, speculative):
    people = await Q.entrants_of(env, n, tag="b")
    pool = [await env.player(f"s{i}", rating=1400.0 - i) for i in range(speculative)]
    tid = await async_tournament(env, people, pool)
    performed, status = await lock(env, tid)
    assert (performed, status) == (True, "locked"), (n, performed, status)

    rows = await env.rows(MATCHES, {"t": tid})
    wb1 = [r for r in rows if r["side"] == "W" and r["round"] == 1]
    lb1 = [r for r in rows if r["side"] == "L" and r["round"] == 1]
    assert len(wb1) == 8 and len(lb1) == 4, (n, len(wb1), len(lb1))
    assert all(list(r["roles"]) == ["L", "L"] and r["n_prereqs"] == 2 and not r["is_bye"]
               for r in lb1), lb1
    # A second lock call finds the row no longer in voting and does nothing.
    assert await lock(env, tid) == (False, "locked")

    # The lowest-rated entrant plays a real round-1 match at every size from
    # 9 to 15; it withdraws through the bot's path.
    victim = people[0]
    victim_sid = next(s["sid"] for s in await env.rows(SIGNUPS, {"t": tid}) if s["pid"] == victim.id)
    assert any(victim_sid in (r["p1"], r["p2"]) for r in wb1 if not r["is_bye"])
    r = await bot_leave(env, tid, victim)
    assert r.status_code == 200, (r.status_code, r.text[:300])
    after = await env.rows(SIGNUPS, {"t": tid})
    assert victim_sid not in {s["sid"] for s in after}
    rows = await env.rows(MATCHES, {"t": tid})
    assert not any(victim_sid in (r["p1"], r["p2"], r["w"]) for r in rows)
    if speculative:
        promoted = [s for s in after if s["pid"] == pool[0].id]
        assert promoted and promoted[0]["spec"] is False, promoted
        assert any(promoted[0]["sid"] in (r["p1"], r["p2"]) for r in rows), "the promotion took no seat"

    assert await start(env, tid) == "running"
    rows, _rating = await drive_to_the_end(env, tid)
    champ = assert_double_elimination(rows, withdrawn={victim_sid})
    best = max((s for s in await env.rows(SIGNUPS, {"t": tid})), key=lambda s: float(s["rating"] or 0))
    assert champ == best["sid"], "the highest-rated entrant won every series it played"
    assert await complete(env, tid) == "completed"


def test_nine_players_lock_withdraw_without_a_pool_and_resolve(monkeypatch, tmp_path):
    Q.e2e(monkeypatch, tmp_path, lambda env: bracket_case(env, 9, 0))


def test_twelve_players_lock_promote_a_speculative_and_resolve(monkeypatch, tmp_path):
    Q.e2e(monkeypatch, tmp_path, lambda env: bracket_case(env, 12, 1))


def test_fourteen_players_lock_withdraw_without_a_pool_and_resolve(monkeypatch, tmp_path):
    Q.e2e(monkeypatch, tmp_path, lambda env: bracket_case(env, 14, 0))


def test_unsignup_requirements_by_status_and_caller(monkeypatch, tmp_path):
    async def body(env):
        # Voting: the player's own session suffices; an internal caller's
        # discord_id is checked when supplied and may be absent.
        voters = await Q.entrants_of(env, 10, tag="v")
        tv = await async_tournament(env, voters)
        r = await player_leave(env, tv, voters[0])
        assert r.status_code == 200, (r.status_code, r.text[:300])
        r = await bot_leave(env, tv, voters[1], discord_id=voters[2].discord)
        assert r.status_code == 409 and "Discord link" in r.text, (r.status_code, r.text[:300])
        r = await bot_leave(env, tv, voters[1], discord_id=None)
        assert r.status_code == 200, (r.status_code, r.text[:300])
        left = {s["pid"] for s in await env.rows(SIGNUPS, {"t": tv})}
        assert voters[0].id not in left and voters[1].id not in left and voters[2].id in left
        # At most one async tournament is active (uniq_tournaments_active_per_kind),
        # so the voting one is retired before the locked case seeds its own.
        await env.ex(f"UPDATE {SCHEMA}.tournaments SET status = 'cancelled', ended_at = now()"
                     " WHERE id = CAST(:t AS uuid)", {"t": tv})

        # Locked: confirmation, internal key and the current Discord link.
        people = await Q.entrants_of(env, 9, tag="l")
        tl = await async_tournament(env, people)
        assert await lock(env, tl) == (True, "locked")
        a = people[3]
        r = await player_leave(env, tl, a)
        assert r.status_code == 409 and "Signups are locked" in r.text, (r.status_code, r.text[:300])
        r = await player_leave(env, tl, a, confirm_locked_leave=True)
        assert r.status_code == 403, (r.status_code, r.text[:300])
        r = await bot_leave(env, tl, a, discord_id=people[4].discord)
        assert r.status_code == 409 and "Discord link" in r.text, (r.status_code, r.text[:300])
        r = await bot_leave(env, tl, a, discord_id=None)
        assert r.status_code == 409 and "Discord link" in r.text, (r.status_code, r.text[:300])
        still = {s["pid"] for s in await env.rows(SIGNUPS, {"t": tl})}
        assert a.id in still, "a refused withdrawal changed the roster"
        r = await bot_leave(env, tl, a)
        assert r.status_code == 200, (r.status_code, r.text[:300])
        assert a.id not in {s["pid"] for s in await env.rows(SIGNUPS, {"t": tl})}

        # Running: no unsignup at all.
        assert await start(env, tl) == "running"
        r = await bot_leave(env, tl, people[5])
        assert r.status_code == 400, (r.status_code, r.text[:300])
        assert people[5].id in {s["pid"] for s in await env.rows(SIGNUPS, {"t": tl})}
    Q.e2e(monkeypatch, tmp_path, body)
