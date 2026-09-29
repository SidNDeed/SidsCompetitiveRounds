"""Discord fix round 3: the synchronized tournament's quorum, end to end on the
real app and the bot's own lifted code (board row 32; Codex round 2 LOW 1).

Item 3, one eligibility predicate. /tournaments/current reported eight votes
while lock_tournament excluded an entrant banned after signup and saw seven,
so Discord announced a quorum and sent availability DMs that the lock then
refused. Now the displayed tally, the agreement announcement, the bot's
eight-vote DM trigger (it reads /tournaments/current) and the lock's decision
all read tournaments._eligible_slot_tallies: with eight voters of whom one is
banned, every surface reads 7 of 8, and no availability DM goes out until an
eighth ELIGIBLE vote exists.

The app runs on the lane database (discord_collection_harness's Env); the bot
functions are lifted as test_discord_tournament_start_rule.py lifts them, over
the production routes. A missing DSN FAILS by name:
    DISCORD_COLLECTION_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    DISCORD_COLLECTION_TEST_PG_OPTOUT=1   says out loud that this run skips them
"""

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import discord_collection_harness as H
import test_discord_tournament_start_rule as R
from discord_collection_harness import SCHEMA

DSN = os.environ.get("DISCORD_COLLECTION_TEST_PG_DSN")
OPTOUT = H.optout(os.environ.get("DISCORD_COLLECTION_TEST_PG_OPTOUT"))


# tournament_notices as migration 124 creates it: the queue's INSERT ... SELECT
# names neither id nor created_at, and the harness build carries only the ORM's
# Python-side defaults for the two. Set for the case, dropped after it, so no
# other test file sees a schema it would not see alone.
NOTICE_DEFAULTS = (f"ALTER TABLE {SCHEMA}.tournament_notices ALTER COLUMN id SET DEFAULT gen_random_uuid(),"
                   " ALTER COLUMN created_at SET DEFAULT NOW()")
NOTICE_DEFAULTS_OFF = (f"ALTER TABLE {SCHEMA}.tournament_notices ALTER COLUMN id DROP DEFAULT,"
                       " ALTER COLUMN created_at DROP DEFAULT")


def e2e(monkeypatch, tmp_path, fn, **kw):
    dsn = H.require_pg(DSN, OPTOUT)

    async def go():
        async with H.Env(monkeypatch, tmp_path, dsn, **kw) as env:
            await env.ex(NOTICE_DEFAULTS)
            try:
                return await fn(env)
            finally:
                await env.ex(NOTICE_DEFAULTS_OFF)
    return H.run(go())


def test_quorum_gate_a_missing_dsn_fails_by_name():
    with pytest.raises(BaseException) as ex:
        H.require_pg(None, False)
    assert "Failed" in type(ex.value).__name__ and "DISCORD_COLLECTION_TEST_PG_DSN" in str(ex.value)


# -- the fixture: a sync tournament in voting, its entrants and their votes ----------------------

async def sync_tournament(env, entrants, voters, *, hours_to_lock=48):
    """A sync tournament in voting whose lock is `hours_to_lock` away (inside
    the availability window) and whose default start - the one offered slot
    here - is two days after the lock; `entrants` signed up (confirmed), the
    first `voters` of them voting for that slot. Returns (tournament id,
    the slot)."""
    import models
    now = datetime.now(timezone.utc).replace(microsecond=0)
    lock_at = now + timedelta(hours=hours_to_lock)
    slot = lock_at + timedelta(hours=48)
    async with AsyncSession(env.seed) as s:
        t = models.Tournament(kind="sync", status="voting", default_start_ts=slot, lock_at=lock_at,
                              voting_closes_at=lock_at, min_players=8, max_players=16)
        s.add(t)
        await s.flush()
        for i, who in enumerate(entrants):
            s.add(models.TournamentSignup(tournament_id=t.id, player_id=who.id, is_speculative=False))
        await s.flush()
        tid = str(t.id)
        for who in entrants[:voters]:
            s.add(models.TournamentTimeVote(tournament_id=t.id, player_id=who.id, slot_ts=slot))
        await s.commit()
        return tid, slot


async def vote(env, tid, who, slot, *, sign_up=True):
    import models
    async with AsyncSession(env.seed) as s:
        if sign_up:
            s.add(models.TournamentSignup(tournament_id=tid, player_id=who.id, is_speculative=False))
            await s.flush()
        s.add(models.TournamentTimeVote(tournament_id=tid, player_id=who.id, slot_ts=slot))
        await s.commit()


async def current(env, who):
    r = await env.client.get("/api/v1/tournaments/current", params={"kind": "sync", "steam_id": who.steam},
                             headers=env.mod_headers(who))
    assert r.status_code == 200, (r.status_code, r.text[:300])
    return r.json()


def tallies_of(answer):
    return [(int(datetime.fromisoformat(row["slot_ts"]).timestamp()), row["votes"])
            for row in answer.get("time_slot_tallies") or []]


async def in_app(env, fn):
    """fn(db, tournaments module) on the app's own session, committed."""
    import tournaments
    async with env.database.async_session() as db:
        out = await fn(db, tournaments)
        await db.commit()
        return out


async def queue_notices(env):
    await in_app(env, lambda db, T: T._queue_availability_notices(db))


async def agreement(env, tid):
    import models

    async def go(db, T):
        return await T._sync_agreement_reached(db, await db.get(models.Tournament, tid))
    return await in_app(env, go)


async def lock(env, tid):
    import models

    async def go(db, T):
        t = await db.get(models.Tournament, tid)
        await T.lock_tournament(db, t)
        return t.status, t.scheduled_start_ts
    return await in_app(env, go)


def bot_over(env):
    """The bot's tournament functions over the real app (the start-rule tests'
    fake Discord client: channels and DMs are recorded)."""
    return R.rig_for(H.asgi_handler(env))


async def tick(rig):
    await rig.ns["poll_tournament_notices"]()
    R.clean(rig)


async def entrants_of(env, n, tag="e"):
    return [await env.player(f"{tag}{i}", rating=1500.0 + i) for i in range(n)]


# -- item 3: one eligibility predicate ------------------------------------------------------------

def test_item3_eight_votes_with_one_active_ban_read_7_of_8_on_every_surface(monkeypatch, tmp_path):
    """Eight entrants vote for the one slot; one of them is banned after signing
    up (the production ban route). /tournaments/current's tally - the in-game
    tab and every Discord line built from it - reads 7; the agreement
    announcement is not reached; the bot holds every queued availability
    notice (no DM, no ack) and logs 7 of 8; and the lock pushes back with the
    best slot at 7. The decisive line is the first assertion: without the one
    predicate the tally read 8 and the DMs went out."""
    async def body(env):
        people = await entrants_of(env, 8)
        tid, slot = await sync_tournament(env, people, 8)
        await env.ban(people[3])
        await queue_notices(env)
        unix = int(slot.timestamp())
        seen = tallies_of(await current(env, people[0]))
        rig = bot_over(env)
        await tick(rig)
        assert (seen, rig.client.dms) == ([(unix, 7)], []), f"tally {seen}, DMs sent {len(rig.client.dms)}"
        assert await agreement(env, tid) is False
        assert R.held_lines(rig) == [f"[TAVAIL] availability checks for tournament {tid[:8]} held until a start"
                                     f" time has 8 votes: 7 of 8 agree on <t:{unix}:F> so far"], rig.logs
        assert not [c for c in rig.calls if c.path == "/internal/tournament-notices/ack"]
        queued = await env.val(f"SELECT COUNT(*) FROM {SCHEMA}.tournament_notices WHERE tournament_id = CAST(:t AS uuid)"
                               " AND notified_at IS NULL", {"t": tid})
        assert queued == 8
        status, start = await lock(env, tid)
        assert (status, start) == ("voting", None), (status, start)
        pushed = await env.val(f"SELECT content FROM {SCHEMA}.pending_channel_posts ORDER BY id DESC LIMIT 1")
        assert pushed and "pushed back" in pushed, pushed
    e2e(monkeypatch, tmp_path, body)


def test_item3_an_eighth_eligible_vote_reaches_the_quorum_on_every_surface(monkeypatch, tmp_path):
    """The same field, and a ninth entrant, not banned, signs up and votes for
    the slot: every surface reads 8 - the tally, the agreement, the bot's DMs
    (the queued notices go out, naming the slot) - and the lock takes it."""
    async def body(env):
        people = await entrants_of(env, 9)
        tid, slot = await sync_tournament(env, people[:8], 8)
        await env.ban(people[3])
        await queue_notices(env)
        await vote(env, tid, people[8], slot)
        unix = int(slot.timestamp())
        assert tallies_of(await current(env, people[0])) == [(unix, 8)]
        assert await agreement(env, tid) is True
        rig = bot_over(env)
        await tick(rig)
        assert len(rig.client.dms) == 8, [d.uid for d in rig.client.dms]
        assert {d.content for d in rig.client.dms} == {
            f"Are you still available to play in the **Synchronized tournament** at <t:{unix}:F>?"}
        status, start = await lock(env, tid)
        assert status == "locked" and int(start.timestamp()) == unix, (status, start)
    e2e(monkeypatch, tmp_path, body)


# -- item 4: a held availability notice dies with its recipient's signup ------------------------

AVAIL_UNSENT = (f"SELECT COUNT(*) FROM {SCHEMA}.tournament_notices WHERE tournament_id = CAST(:t AS uuid)"
                " AND player_id = CAST(:p AS uuid) AND notice_type = 'availability_check' AND notified_at IS NULL")


async def held_below_quorum(env):
    """Eight entrants, seven of them voting for the one slot; the eight checks
    queued and held by a bot tick (7 of 8, no DM). Returns (tid, slot, people):
    people[2] is a voter who will leave, people[8] and people[9] the
    replacements."""
    people = await entrants_of(env, 10)
    tid, slot = await sync_tournament(env, people[:8], 7)
    await queue_notices(env)
    rig = bot_over(env)
    await tick(rig)
    assert rig.client.dms == [] and len(R.held_lines(rig)) == 1, (rig.client.dms, rig.logs)
    return tid, slot, people


async def replacements_reach_quorum(env, tid, slot, people):
    for who in people[8:10]:
        await vote(env, tid, who, slot)
    await queue_notices(env)
    assert tallies_of(await current(env, people[0])) == [(int(slot.timestamp()), 8)]
    rig = bot_over(env)
    await tick(rig)
    return rig


def dm_view(rig, people, slot):
    """(recipients, contents) of the tick's DMs, each recipient named by its
    fixture tag; and the tags every entrant but the leaver should hold."""
    by_did = {str(p.discord): p.tag for p in people}
    got = sorted(by_did.get(str(d.uid), f"?{d.uid}") for d in rig.client.dms)
    want = sorted(p.tag for i, p in enumerate(people) if i != 2)
    line = f"Are you still available to play in the **Synchronized tournament** at <t:{int(slot.timestamp())}:F>?"
    return got, want, {d.content for d in rig.client.dms}, line


def test_item4_unsignup_drops_the_held_check_and_the_former_entrant_gets_no_dm(monkeypatch, tmp_path):
    """Queue, hold below quorum, the voter people[2] leaves through the
    production unsignup route, two replacements vote and the slot reaches
    eight: the leaver's unsent check is gone the moment they leave (the drop),
    no DM reaches them, and the nine current entrants' DMs are the ones they
    get without the leaver in the story - one each, naming the slot."""
    async def body(env):
        tid, slot, people = await held_below_quorum(env)
        leaver = people[2]
        r = await env.client.post(f"/api/v1/tournaments/{tid}/unsignup", json={"steam_id": leaver.steam},
                                  headers=env.mod_headers(leaver))
        assert r.status_code == 200, (r.status_code, r.text[:300])
        left = await env.val(AVAIL_UNSENT, {"t": tid, "p": leaver.id})
        assert left == 0, f"the leaver's held availability check survived the unsignup: {left} unsent row(s)"
        rig = await replacements_reach_quorum(env, tid, slot, people)
        got, want, contents, line = dm_view(rig, people, slot)
        assert (got, contents) == (want, {line}), f"DMs to {got}"
    e2e(monkeypatch, tmp_path, body)


def test_item4_a_check_that_outlived_its_signup_is_never_sent(monkeypatch, tmp_path):
    """The send path's own re-check: a held check whose signup is gone by
    another road - here the rows an unsignup before this fix left behind
    (signup and votes deleted, the notice kept) - is not in the feed the bot
    sends from, so the former entrant gets no DM when the replacements reach
    quorum, and the nine current entrants' DMs are unchanged."""
    async def body(env):
        tid, slot, people = await held_below_quorum(env)
        leaver = people[2]
        for table in ("tournament_time_votes", "tournament_signups"):
            await env.ex(f"DELETE FROM {SCHEMA}.{table} WHERE tournament_id = CAST(:t AS uuid)"
                         " AND player_id = CAST(:p AS uuid)", {"t": tid, "p": leaver.id})
        assert await env.val(AVAIL_UNSENT, {"t": tid, "p": leaver.id}) == 1
        rig = await replacements_reach_quorum(env, tid, slot, people)
        got, want, contents, line = dm_view(rig, people, slot)
        assert (got, contents) == (want, {line}), f"DMs to {got}"
    e2e(monkeypatch, tmp_path, body)
