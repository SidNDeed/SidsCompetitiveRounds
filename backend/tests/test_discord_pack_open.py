"""Discord fix round 1 (player report 2026-09-28): opening a Player Cards pack
from Discord.

D1: /daily claims today's pack, opens it through POST /internal/pc/packs/open
and shows the cards it dealt - before this round it only claimed and told the
player to open the pack in the mod, and no internal route could open a pack.

D2 (a scope addition Sid asked for on 2026-09-28): /buypack buys one pack with
gold or shards through the same route - the api's price (the mod's), its daily
cap, its conditional delta debit and gold ledger row, keyed on a nonce the bot
draws - and shows it the same way.

Round 2, M1 (Codex round 1 MEDIUM 1): a purchase that committed is answered
with its recorded outcome - the pack and its charge - whatever fails after
the commit, on its first answer and on every replay of its key.

Server rows call the real app on the lane database (discord_collection_harness's
Env); bot rows lift discord_bot.py's own functions (the harness's BotRig) over
that same app, so every request the bot makes is answered by the production
route. Live PostgreSQL is required, and a missing DSN FAILS by name, as in the
collection suites:
    DISCORD_COLLECTION_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    DISCORD_COLLECTION_TEST_PG_OPTOUT=1   says out loud that this run skips them
"""

import asyncio
import os
import re
import secrets
import uuid
from typing import Literal

import pytest

import discord_collection_harness as H
from discord_collection_harness import SCHEMA

DSN = os.environ.get("DISCORD_COLLECTION_TEST_PG_DSN")
OPTOUT = H.optout(os.environ.get("DISCORD_COLLECTION_TEST_PG_OPTOUT"))

DAILY = "/internal/pc/daily"
OPEN = "/internal/pc/packs/open"
PACKS = "/internal/pc/packs"
UNSHOWN = "Your pack is open - it could not be shown right now; `/pack` shows it."

OPEN_FUNCS = H.REVEAL_FUNCS | {"cmd_pc_daily", "_pc_open_pack_api", "_pc_open_refusal", "_pc_open_and_show",
                               "_pc_reveal_opened", "cmd_pc_buypack"}
OPEN_ASSIGNS = H.REVEAL_ASSIGNS | {"_PC_OPEN_TIMEOUT_S", "_PC_OPENED_UNSHOWN", "_pc_buying"}


def e2e(monkeypatch, tmp_path, fn, **kw):
    dsn = H.require_pg(DSN, OPTOUT)

    async def go():
        async with H.Env(monkeypatch, tmp_path, dsn, **kw) as env:
            return await fn(env)
    return H.run(go())


def test_pack_open_gate_a_missing_dsn_fails_by_name():
    with pytest.raises(BaseException) as ex:
        H.require_pg(None, False)
    assert "Failed" in type(ex.value).__name__ and "DISCORD_COLLECTION_TEST_PG_DSN" in str(ex.value)


# -- shared helpers --------------------------------------------------------------------------

async def world(env, n=5, *, snapshot=True, plan=True):
    """n pool players, a linked owner outside the pool, a snapshot, and the
    next roll scripted to deal the pool in order."""
    subs = await H.pool(env, n, tag="s")
    own = await env.player("owner", rating=None)
    if snapshot:
        await env.snapshot()
    if plan:
        env.plan([(s, False, False) for s in subs])
    return own, subs


async def claim(env, who):
    r = await env.client.post("/api/v1" + DAILY, headers=env.ihead(), params={"discord_id": str(who.discord)})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    return r.json()["pack_id"]


async def open_internal(env, discord_id, pack_id):
    return await env.client.post("/api/v1" + OPEN, headers=env.ihead(),
                                 params={"discord_id": str(discord_id), "pack_id": pack_id})


async def pack_row(env, pack_id):
    rows = await env.rows(f"SELECT status, source, player_id::text AS owner FROM {SCHEMA}.pc_packs"
                          " WHERE id = CAST(:p AS uuid)", {"p": pack_id})
    return rows[0] if rows else None


async def minted(env, pack_id):
    return await env.val(f"SELECT COUNT(*) FROM {SCHEMA}.pc_prints WHERE pack_id = CAST(:p AS uuid)",
                         {"p": pack_id})


def _fake_wait_for(clock):
    """asyncio.wait_for on the rig's clock (the collection suite's own model):
    the awaited call runs to its end, and one that spent more than `timeout`
    of the rig's time raises as the real one would have."""
    async def wait_for(aw, timeout=None):
        t0 = clock.now
        out = await aw
        if timeout is not None and clock.now - t0 > float(timeout):
            raise asyncio.TimeoutError()
        return out
    return wait_for


def rig_over(env, stub=None):
    """The lifted bot over the real app; `stub(call)` may answer a request
    itself (a Reply) or return None to forward it."""
    base = H.asgi_handler(env)

    async def handler(call):
        reply = await stub(call) if stub is not None else None
        if reply is None:
            reply = await base(call)
        call.reply = reply
        return reply
    rig = H.BotRig(handler, funcs=OPEN_FUNCS, assigns=OPEN_ASSIGNS,
                   extra={"secrets": secrets, "Literal": Literal})
    rig.ns["asyncio"].wait_for = _fake_wait_for(rig.clock)
    rig.base = base
    return rig


async def daily(rig, who_discord):
    await rig.ns["cmd_pc_daily"](rig.ctx(who_discord))


def calls_to(rig, path, method="POST"):
    return [c for c in rig.calls if c.method == method and c.path == path]


# -- the internal opener, server side ----------------------------------------------------------

def test_d1_the_internal_opener_opens_the_linked_players_held_daily_pack(monkeypatch, tmp_path, capsys):
    async def body(env):
        own, subs = await world(env)
        pack_id = await claim(env, own)
        assert (await pack_row(env, pack_id))["status"] == "unopened"
        before = await env.rows(f"SELECT COALESCE(gold_spent, 0) AS spent, pc_shards FROM {SCHEMA}.players"
                                " WHERE id = CAST(:p AS uuid)", {"p": own.id})
        r = await open_internal(env, own.discord, pack_id)
        assert r.status_code == 200, (r.status_code, r.text[:400])
        got = r.json()
        assert got["pack_id"] == pack_id and got["status"] == "done" and got["source"] == "daily"
        assert [p["subject_player_id"] for p in got["prints"]] == [s.id for s in subs]
        row = await pack_row(env, pack_id)
        assert row["status"] == "done" and row["owner"] == own.id
        assert await minted(env, pack_id) == 5
        after = await env.rows(f"SELECT COALESCE(gold_spent, 0) AS spent, pc_shards FROM {SCHEMA}.players"
                               " WHERE id = CAST(:p AS uuid)", {"p": own.id})
        assert after == before, "a held pack costs nothing to open"
    e2e(monkeypatch, tmp_path, body)
    out = capsys.readouterr().out
    assert "source=daily pay=None price=0" in out and "via=discord" in out, out[-800:]


def test_d1_a_replayed_open_answers_the_committed_pack_on_either_door_and_rolls_once(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        pack_id = await claim(env, own)
        first = await open_internal(env, own.discord, pack_id)
        assert first.status_code == 200, first.text[:300]
        again = await open_internal(env, own.discord, pack_id)
        assert again.status_code == 200, again.text[:300]
        ids = [p["print_id"] for p in first.json()["prints"]]
        assert [p["print_id"] for p in again.json()["prints"]] == ids
        # the mod's door answers the same committed row: one body, one claim
        canon = env.main._pc.canon_open_pack(own.steam, pack_id)
        mod = await env.client.post("/api/v1/pc/packs/open", headers=env.mod_headers(own),
                                    params={"steam_id": own.steam, "sig": H.mod_sig(canon), "pack_id": pack_id})
        assert mod.status_code == 200, mod.text[:300]
        assert [p["print_id"] for p in mod.json()["prints"]] == ids
        assert await minted(env, pack_id) == 5 and env._plans == []
    e2e(monkeypatch, tmp_path, body)


def test_d1_the_opener_refuses_another_players_pack_and_leaves_it_unopened(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        other = await env.player("other", rating=None)
        theirs = await claim(env, other)
        r = await open_internal(env, own.discord, theirs)
        assert r.status_code == 404, (r.status_code, r.text[:300])
        assert (await pack_row(env, theirs))["status"] == "unopened"
        assert await minted(env, theirs) == 0
    e2e(monkeypatch, tmp_path, body)


def test_d1_the_opener_refuses_an_unlinked_discord_id(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        pack_id = await claim(env, own)
        r = await open_internal(env, H.discord_of(999), pack_id)
        assert r.status_code == 404 and r.json()["detail"] == {"error": "not_linked"}, r.text[:300]
        assert (await pack_row(env, pack_id))["status"] == "unopened"
    e2e(monkeypatch, tmp_path, body)


def test_d1_the_opener_refuses_a_banned_player_and_writes_nothing(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        pack_id = await claim(env, own)
        await env.ban(own)
        r = await open_internal(env, own.discord, pack_id)
        assert r.status_code == 403 and r.json()["detail"] == {"error": "banned"}, r.text[:300]
        assert (await pack_row(env, pack_id))["status"] == "unopened"
        assert await minted(env, pack_id) == 0
        assert await env.val(f"SELECT COUNT(*) FROM {SCHEMA}.pc_open_attempts WHERE pack_id = CAST(:p AS uuid)",
                             {"p": pack_id}) == 0
    e2e(monkeypatch, tmp_path, body)


def test_d1_the_opener_refuses_a_deleted_account(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        pack_id = await claim(env, own)
        discord_id = own.discord
        await env.delete_data(own)
        r = await open_internal(env, discord_id, pack_id)
        assert r.status_code in (404, 410), (r.status_code, r.text[:300])
        assert await minted(env, pack_id) == 0
    e2e(monkeypatch, tmp_path, body)


def test_d1_a_rebind_between_the_lookup_and_the_lock_is_refused(monkeypatch, tmp_path):
    """The Discord id moves to another account after the route resolved it and
    before the identity lock: the re-read under the lock refuses, and nothing
    is opened for either account."""
    async def body(env):
        own, subs = await world(env)
        other = await env.player("other", rating=None, discord=False)
        pack_id = await claim(env, own)
        discord_id = own.discord
        real = env.main._pc_player_by_discord
        moved = []

        async def lookup_then_rebind(db, did):
            player = await real(db, did)
            if not moved:
                moved.append(True)
                await env.rebind(did, other)
            return player
        monkeypatch.setattr(env.main, "_pc_player_by_discord", lookup_then_rebind)
        r = await open_internal(env, discord_id, pack_id)
        assert moved and r.status_code == 404 and r.json()["detail"] == {"error": "not_linked"}, r.text[:300]
        assert (await pack_row(env, pack_id))["status"] == "unopened"
        assert await minted(env, pack_id) == 0
    e2e(monkeypatch, tmp_path, body)


def test_d1_the_renderer_gate_refuses_before_any_write(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        pack_id = await claim(env, own)
        monkeypatch.setattr(env.main, "_pc_renderer_unavailable", lambda: "renderer_unavailable")
        r = await open_internal(env, own.discord, pack_id)
        assert r.status_code == 503, (r.status_code, r.text[:300])
        assert (await pack_row(env, pack_id))["status"] == "unopened"
        assert await env.val(f"SELECT COUNT(*) FROM {SCHEMA}.pc_open_attempts WHERE pack_id = CAST(:p AS uuid)",
                             {"p": pack_id}) == 0
    e2e(monkeypatch, tmp_path, body)


def test_d1_the_identity_lock_is_taken_before_the_claim(monkeypatch, tmp_path):
    """The shared identity lock the mod's door takes (delete_player_data and
    the ban writer hold it exclusively across their purges) is taken by the
    bot's door before the claim, the open's first write."""
    async def body(env):
        own, subs = await world(env)
        pack_id = await claim(env, own)
        env.app_sql.clear()
        r = await open_internal(env, own.discord, pack_id)
        assert r.status_code == 200, r.text[:300]
        sql = [" ".join(s.split()) for s in env.app_sql]
        lock = [i for i, s in enumerate(sql) if "pg_advisory_xact_lock_shared(hashtext(" in s]
        claim_at = [i for i, s in enumerate(sql) if s.startswith("UPDATE pc_packs SET status = 'opening'")]
        assert lock and claim_at and lock[0] < claim_at[0], (lock, claim_at)
    e2e(monkeypatch, tmp_path, body, record_app_sql=True)


def test_d1_a_service_account_opens_nothing(monkeypatch, tmp_path):
    """The service check the mod's door makes (_assert_no_service_subject, both
    ids) is made by the bot's door too: a service account's held pack stays
    unopened, and nothing is minted or attempted."""
    async def body(env):
        own, subs = await world(env)
        pack_id = await claim(env, own)
        monkeypatch.setattr(env.main, "SPECTATE_BROADCAST_STEAM_IDS", {own.steam})
        monkeypatch.setattr(env.main, "_service_player_uuid_cache", None)
        r = await open_internal(env, own.discord, pack_id)
        assert r.status_code == 403 and r.json()["detail"] == "service_account_forbidden", r.text[:300]
        assert (await pack_row(env, pack_id))["status"] == "unopened"
        assert await minted(env, pack_id) == 0
        assert await env.val(f"SELECT COUNT(*) FROM {SCHEMA}.pc_open_attempts WHERE pack_id = CAST(:p AS uuid)",
                             {"p": pack_id}) == 0
    e2e(monkeypatch, tmp_path, body)


# -- /daily in Discord, end to end ---------------------------------------------------------------

def test_d1_daily_claims_opens_and_posts_the_pack_with_its_picture(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        rig = rig_over(env)
        await daily(rig, own.discord)
        claims, opens = calls_to(rig, DAILY), calls_to(rig, OPEN)
        assert len(claims) == 1 and len(opens) == 1, [(c.method, c.path) for c in rig.calls]
        pack_id = opens[0].params["pack_id"]
        assert H._json.loads(claims[0].reply.body)["pack_id"] == pack_id, "the pack /daily claimed is the one it opens"
        assert opens[0].params["discord_id"] == own.discord
        row = await pack_row(env, pack_id)
        assert row == {"status": "done", "source": "daily", "owner": own.id}, row
        assert len(rig.sent) == 1, [s.content for s in rig.sent]
        post = rig.sent[0]
        assert post.file is not None and post.file.filename == "pack.png"
        assert H.image_of(post.file.data).size == (1947, 549)
        assert "**Today's pack** (the next one unlocks <t:" in post.content, post.content
        assert "- daily, opened <t:" in post.content, post.content
        for i, s in enumerate(subs, start=1):
            assert f"\n{i}. " in post.content and f"**{s.name}**" in post.content, post.content
        assert await minted(env, pack_id) == 5
    e2e(monkeypatch, tmp_path, body)


def test_d1_daily_opens_a_pack_claimed_earlier_and_left_unopened(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        pack_id = await claim(env, own)
        rig = rig_over(env)
        await daily(rig, own.discord)
        opens = calls_to(rig, OPEN)
        assert len(opens) == 1 and opens[0].params["pack_id"] == pack_id
        assert (await pack_row(env, pack_id))["status"] == "done"
        assert len(rig.sent) == 1 and rig.sent[0].file is not None, [s.content for s in rig.sent]
        assert "**Today's pack**" in rig.sent[0].content
    e2e(monkeypatch, tmp_path, body)


def test_d1_a_second_daily_the_same_day_opens_nothing(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        rig = rig_over(env)
        await daily(rig, own.discord)
        await daily(rig, own.discord)
        assert len(calls_to(rig, OPEN)) == 1 and len(calls_to(rig, DAILY)) == 2
        assert len(rig.sent) == 2 and rig.sent[1].file is None
        assert "Already claimed today" in rig.sent[1].content and "`/pack` shows your latest pack" in rig.sent[1].content
    e2e(monkeypatch, tmp_path, body)


def test_d1_daily_for_an_unlinked_account_asks_for_the_link_and_opens_nothing(monkeypatch, tmp_path):
    async def body(env):
        await world(env, plan=False)
        rig = rig_over(env)
        await daily(rig, H.discord_of(999))
        assert calls_to(rig, OPEN) == []
        assert len(rig.sent) == 1 and "Not linked" in rig.sent[0].content, [s.content for s in rig.sent]
    e2e(monkeypatch, tmp_path, body)


def test_d1_an_open_the_api_refuses_keeps_the_pack_and_says_so(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env, snapshot=False, plan=False)   # no pool snapshot: pool_empty
        rig = rig_over(env)
        await daily(rig, own.discord)
        opens = calls_to(rig, OPEN)
        assert len(opens) == 1 and opens[0].status == 409
        pack_id = opens[0].params["pack_id"]
        assert (await pack_row(env, pack_id))["status"] == "unopened"
        assert len(rig.sent) == 1 and rig.sent[0].file is None
        assert "the pack stays yours, unopened" in rig.sent[0].content, rig.sent[0].content
    e2e(monkeypatch, tmp_path, body)


def test_d1_an_open_whose_answer_was_lost_is_sent_once_more_and_answers_the_committed_pack(monkeypatch, tmp_path):
    """The first open reaches the api and commits, and its answer never comes
    back (the bot's 20 s timeout): the one resend with the same pack id is
    answered with the committed row - one roll, one set of prints - and the
    pack is shown."""
    async def body(env):
        own, subs = await world(env)
        holder = {}

        async def stub(call):
            if call.method == "POST" and call.path == OPEN and call.n == 1:
                reply = await holder["rig"].base(call)
                reply.delay = 25.0
                return reply
            return None
        rig = rig_over(env, stub)
        holder["rig"] = rig
        await daily(rig, own.discord)
        opens = calls_to(rig, OPEN)
        assert [c.status for c in opens] == [0, 200], [c.status for c in opens]
        assert opens[0].params["pack_id"] == opens[1].params["pack_id"]
        assert opens[0].total == 20.0
        pack_id = opens[0].params["pack_id"]
        assert await minted(env, pack_id) == 5 and env._plans == []
        assert len(rig.sent) == 1 and rig.sent[0].file is not None, [s.content for s in rig.sent]
    e2e(monkeypatch, tmp_path, body)


def test_d1_an_opened_pack_that_cannot_be_shown_says_it_is_open(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)

        async def stub(call):
            if call.method == "GET" and call.path == PACKS:
                return H.Reply(500, json={"detail": "boom"})
            return None
        rig = rig_over(env, stub)
        await daily(rig, own.discord)
        pack_id = calls_to(rig, OPEN)[0].params["pack_id"]
        assert (await pack_row(env, pack_id))["status"] == "done"
        assert len(rig.sent) == 1 and rig.sent[0].file is None
        assert rig.sent[0].content.endswith(UNSHOWN), rig.sent[0].content
        assert any("opened, not shown: the read answered HTTP 500" in line for line in rig.logs), rig.logs
    e2e(monkeypatch, tmp_path, body)


# -- D2: buying a pack through Discord, server side ----------------------------------------------

PRICE_KEY = {"gold": "pack_price_gold", "shards": "pack_price_shards"}


def price_of(env, pay):
    return int(env.main._pc.PC_ECONOMY[PRICE_KEY[pay]])


async def set_gold(env, who, earned, spent=0):
    await env.ex(f"UPDATE {SCHEMA}.players SET gold_earned = :e, gold_spent = :s WHERE id = CAST(:p AS uuid)",
                 {"e": int(earned), "s": int(spent), "p": who.id})


async def purse(env, who):
    rows = await env.rows(f"SELECT gold_earned, gold_spent, pc_shards FROM {SCHEMA}.players"
                          " WHERE id = CAST(:p AS uuid)", {"p": who.id})
    return rows[0]


async def ledger(env, who):
    return await env.rows(f"SELECT amount, reason, reference_id FROM {SCHEMA}.gold_transactions"
                          " WHERE player_id = CAST(:p AS uuid) ORDER BY id", {"p": who.id})


async def buy_internal(env, discord_id, nonce, pay, **extra):
    params = {"discord_id": str(discord_id), "nonce": nonce, "pay": pay}
    params.update(extra)
    return await env.client.post("/api/v1" + OPEN, headers=env.ihead(), params=params)


def test_d2_a_gold_purchase_debits_the_price_as_a_delta_and_writes_the_ledger_row(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        price = price_of(env, "gold")
        await set_gold(env, own, 1000 + price, 150)
        r = await buy_internal(env, own.discord, "d2-gold-" + secrets.token_hex(8), "gold")
        assert r.status_code == 200, (r.status_code, r.text[:400])
        got = r.json()
        assert (got["source"], got["pay"], got["price"], got["status"]) == ("bought", "gold", price, "done")
        assert await purse(env, own) == {"gold_earned": 1000 + price, "gold_spent": 150 + price, "pc_shards": 10000}
        assert await ledger(env, own) == [{"amount": -price, "reason": "pc_pack", "reference_id": got["pack_id"]}]
        assert await minted(env, got["pack_id"]) == 5
    e2e(monkeypatch, tmp_path, body)


def test_d2_a_shards_purchase_debits_the_shards_and_no_gold(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        price = price_of(env, "shards")
        await set_gold(env, own, 500)
        r = await buy_internal(env, own.discord, "d2-shards-" + secrets.token_hex(8), "shards")
        assert r.status_code == 200, (r.status_code, r.text[:400])
        assert await purse(env, own) == {"gold_earned": 500, "gold_spent": 0, "pc_shards": 10000 - price}
        assert await ledger(env, own) == []
    e2e(monkeypatch, tmp_path, body)


def test_d2_a_purchase_without_enough_gold_is_refused_and_moves_nothing(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)   # the roll (reads only) comes before the debit, as on the mod's route
        price = price_of(env, "gold")
        await set_gold(env, own, price - 1)
        r = await buy_internal(env, own.discord, "d2-poor-" + secrets.token_hex(8), "gold")
        assert r.status_code == 402, (r.status_code, r.text[:400])
        d = r.json()["detail"]
        assert (d["error"], d["status"], d["price"]) == ("insufficient_gold", "rejected", price)
        assert await purse(env, own) == {"gold_earned": price - 1, "gold_spent": 0, "pc_shards": 10000}
        assert await ledger(env, own) == []
        assert (await pack_row(env, d["pack_id"]))["status"] == "rejected"
        assert await minted(env, d["pack_id"]) == 0
    e2e(monkeypatch, tmp_path, body)


def test_d2_the_daily_cap_refuses_the_purchase_past_it(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        monkeypatch.setitem(env.main._pc.PC_ECONOMY, "paid_packs_per_day", 1)
        price = price_of(env, "gold")
        await set_gold(env, own, 10 * price)
        first = await buy_internal(env, own.discord, "d2-cap-a-" + secrets.token_hex(8), "gold")
        assert first.status_code == 200, first.text[:300]
        second = await buy_internal(env, own.discord, "d2-cap-b-" + secrets.token_hex(8), "gold")
        assert second.status_code == 409, (second.status_code, second.text[:300])
        assert (second.json()["detail"]["error"], second.json()["detail"]["cap"]) == ("daily_cap", 1)
        assert (await purse(env, own))["gold_spent"] == price
        assert len(await ledger(env, own)) == 1
    e2e(monkeypatch, tmp_path, body)


def test_d2_a_replayed_nonce_answers_the_committed_purchase_and_charges_once(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        price = price_of(env, "gold")
        await set_gold(env, own, 10 * price)
        nonce = "d2-replay-" + secrets.token_hex(8)
        first = await buy_internal(env, own.discord, nonce, "gold")
        again = await buy_internal(env, own.discord, nonce, "gold")
        assert first.status_code == 200 and again.status_code == 200, (first.text[:200], again.text[:200])
        assert again.json()["pack_id"] == first.json()["pack_id"]
        assert [p["print_id"] for p in again.json()["prints"]] == [p["print_id"] for p in first.json()["prints"]]
        assert (await purse(env, own))["gold_spent"] == price
        assert len(await ledger(env, own)) == 1 and env._plans == []
    e2e(monkeypatch, tmp_path, body)


def test_d2_a_sent_price_must_be_the_apis_and_a_different_one_is_refused_before_any_debit(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        price = price_of(env, "gold")
        await set_gold(env, own, 10 * price)
        wrong = await buy_internal(env, own.discord, "d2-price-a-" + secrets.token_hex(8), "gold",
                                   expected_price=price + 1)
        assert wrong.status_code == 409, (wrong.status_code, wrong.text[:300])
        assert (wrong.json()["detail"]["error"], wrong.json()["detail"]["price"]) == ("price_changed", price)
        assert (await purse(env, own))["gold_spent"] == 0 and await ledger(env, own) == []
        right = await buy_internal(env, own.discord, "d2-price-b-" + secrets.token_hex(8), "gold",
                                   expected_price=price)
        assert right.status_code == 200, right.text[:300]
        assert (await purse(env, own))["gold_spent"] == price
    e2e(monkeypatch, tmp_path, body)


def test_d2_the_route_takes_a_held_pack_or_a_purchase_and_nothing_else(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env, plan=False)
        pack_id = await claim(env, own)
        before = await env.val(f"SELECT COUNT(*) FROM {SCHEMA}.pc_packs")
        head = env.ihead()
        cases = [
            {"discord_id": own.discord},                                               # neither form
            {"discord_id": own.discord, "nonce": "d2-form-" + secrets.token_hex(8)},   # a nonce without pay
            {"discord_id": own.discord, "nonce": "d2-form-" + secrets.token_hex(8), "pay": "rubies"},
            {"discord_id": own.discord, "pack_id": pack_id, "nonce": "d2-form-" + secrets.token_hex(8),
             "pay": "gold"},                                                           # both forms
            {"discord_id": own.discord, "pack_id": pack_id, "expected_price": 1},
        ]
        for params in cases:
            r = await env.client.post("/api/v1" + OPEN, headers=head, params=params)
            assert r.status_code == 422, (params, r.status_code, r.text[:200])
        assert await env.val(f"SELECT COUNT(*) FROM {SCHEMA}.pc_packs") == before
        assert (await pack_row(env, pack_id))["status"] == "unopened"
    e2e(monkeypatch, tmp_path, body)


def test_d2_two_purchases_racing_for_the_last_packs_worth_of_gold_charge_once(monkeypatch, tmp_path):
    """Two different nonces at once with gold for exactly one pack: the players
    row lock orders them and the conditional delta debit refuses the second,
    so the balance never goes below zero and one ledger row is written."""
    async def body(env):
        own, subs = await world(env)
        env.plan([(s, False, False) for s in subs])
        price = price_of(env, "gold")
        await set_gold(env, own, price)
        a, b = await asyncio.gather(buy_internal(env, own.discord, "d2-race-a-" + secrets.token_hex(8), "gold"),
                                    buy_internal(env, own.discord, "d2-race-b-" + secrets.token_hex(8), "gold"))
        assert sorted([a.status_code, b.status_code]) == [200, 402], (a.text[:200], b.text[:200])
        assert await purse(env, own) == {"gold_earned": price, "gold_spent": price, "pc_shards": 10000}
        assert len(await ledger(env, own)) == 1
    e2e(monkeypatch, tmp_path, body)


def test_d2_an_erasure_between_the_lookup_and_the_lock_buys_nothing(monkeypatch, tmp_path):
    """The account is erased after the route resolved its Discord id and before
    the identity lock: the re-read under the lock (_pc_bot_actor) answers the
    mod's 410, and nothing is written for the erased account - no pack row, no
    print, no debit, no ledger row. The erasure removes the held packs, so a
    purchase is the form that could still write."""
    async def body(env):
        own, subs = await world(env)
        price = price_of(env, "gold")
        await set_gold(env, own, 10 * price)
        discord_id = own.discord
        real = env.main._pc_player_by_discord
        erased = []

        async def lookup_then_erase(db, did):
            player = await real(db, did)
            if not erased:
                erased.append(True)
                await env.delete_data(own)
            return player
        monkeypatch.setattr(env.main, "_pc_player_by_discord", lookup_then_erase)
        r = await buy_internal(env, discord_id, "d2-erased-" + secrets.token_hex(8), "gold")
        assert erased and r.status_code == 410 and r.json()["detail"] == "Account deleted", (
            r.status_code, r.text[:300])
        assert await env.val(f"SELECT COUNT(*) FROM {SCHEMA}.pc_packs WHERE player_id = CAST(:p AS uuid)",
                             {"p": own.id}) == 0
        assert await env.val(f"SELECT COUNT(*) FROM {SCHEMA}.pc_prints WHERE owner_player_id = CAST(:p AS uuid)",
                             {"p": own.id}) == 0
        assert (await purse(env, own))["gold_spent"] == 0
        assert [row for row in await ledger(env, own) if row["reason"] == "pc_pack"] == []
    e2e(monkeypatch, tmp_path, body)


# -- /buypack in Discord, end to end -------------------------------------------------------------

async def buypack(rig, who_discord, pay="gold", ctx=None):
    await rig.ns["cmd_pc_buypack"](ctx or rig.ctx(who_discord), pay)


def test_d2_buypack_buys_opens_and_posts_the_pack(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        price = price_of(env, "gold")
        await set_gold(env, own, 1000 + price)
        rig = rig_over(env)
        await buypack(rig, own.discord, "gold")
        opens = calls_to(rig, OPEN)
        assert len(opens) == 1, [(c.method, c.path) for c in rig.calls]
        params = opens[0].params
        assert set(params) == {"discord_id", "locale", "nonce", "pay"}, params
        assert params["discord_id"] == own.discord and params["pay"] == "gold"
        assert re.fullmatch(r"[0-9a-f]{32}", params["nonce"]), params["nonce"]
        assert len(rig.sent) == 1, [s.content for s in rig.sent]
        post = rig.sent[0]
        assert post.file is not None and H.image_of(post.file.data).size == (1947, 549)
        assert f"**Pack bought for {price} gold** - bought, opened <t:" in post.content, post.content
        assert (await purse(env, own))["gold_spent"] == price and len(await ledger(env, own)) == 1
        assert rig.ns["_pc_buying"] == set()
    e2e(monkeypatch, tmp_path, body)


def test_d2_buypack_with_shards_pays_shards(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        price = price_of(env, "shards")
        rig = rig_over(env)
        await buypack(rig, own.discord, "shards")
        assert calls_to(rig, OPEN)[0].params["pay"] == "shards"
        assert len(rig.sent) == 1 and f"**Pack bought for {price} shards**" in rig.sent[0].content
        assert (await purse(env, own))["pc_shards"] == 10000 - price and await ledger(env, own) == []
    e2e(monkeypatch, tmp_path, body)


def test_d2_buypack_without_enough_gold_says_so_and_charges_nothing(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        price = price_of(env, "gold")
        await set_gold(env, own, 0)
        rig = rig_over(env)
        await buypack(rig, own.discord, "gold")
        assert len(rig.sent) == 1 and rig.sent[0].file is None
        assert f"Not enough gold - a pack costs {price} gold. Nothing was charged." in rig.sent[0].content
        assert await purse(env, own) == {"gold_earned": 0, "gold_spent": 0, "pc_shards": 10000}
        assert await ledger(env, own) == [] and rig.ns["_pc_buying"] == set()
    e2e(monkeypatch, tmp_path, body)


def test_d2_buypack_past_the_daily_cap_says_so(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        monkeypatch.setitem(env.main._pc.PC_ECONOMY, "paid_packs_per_day", 1)
        price = price_of(env, "gold")
        await set_gold(env, own, 10 * price)
        rig = rig_over(env)
        await buypack(rig, own.discord, "gold")
        await buypack(rig, own.discord, "gold")
        assert [c.status for c in calls_to(rig, OPEN)] == [200, 409]
        assert len(rig.sent) == 2 and rig.sent[1].file is None
        assert "Today's limit of bought packs is 1 - it resets at 00:00 UTC." in rig.sent[1].content
        assert (await purse(env, own))["gold_spent"] == price
    e2e(monkeypatch, tmp_path, body)


def test_d2_a_lost_purchase_answer_is_resent_with_the_same_nonce_and_charges_once(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        price = price_of(env, "gold")
        await set_gold(env, own, 10 * price)
        holder = {}

        async def stub(call):
            if call.method == "POST" and call.path == OPEN and call.n == 1:
                reply = await holder["rig"].base(call)
                reply.delay = 25.0
                return reply
            return None
        rig = rig_over(env, stub)
        holder["rig"] = rig
        await buypack(rig, own.discord, "gold")
        opens = calls_to(rig, OPEN)
        assert [c.status for c in opens] == [0, 200], [c.status for c in opens]
        assert opens[0].params["nonce"] == opens[1].params["nonce"]
        assert (await purse(env, own))["gold_spent"] == price and len(await ledger(env, own)) == 1
        assert env._plans == []
        assert len(rig.sent) == 1 and rig.sent[0].file is not None, [s.content for s in rig.sent]
    e2e(monkeypatch, tmp_path, body)


def test_d2_a_buypack_while_one_is_in_flight_buys_nothing_and_the_guard_always_clears(monkeypatch, tmp_path):
    async def body(env):
        own, subs = await world(env)
        price = price_of(env, "gold")
        await set_gold(env, own, 10 * price)
        rig = rig_over(env)
        rig.ns["_pc_buying"].add(own.discord)
        await buypack(rig, own.discord, "gold")
        assert calls_to(rig, OPEN) == [] and len(rig.sent) == 1
        assert "your last purchase is still going through" in rig.sent[0].content
        rig.ns["_pc_buying"].clear()
        # a send that raises still clears the guard (the finally)
        ctx = rig.ctx(own.discord)

        async def broken_send(*a, **k):
            raise RuntimeError("gateway gone")
        ctx.send = broken_send
        with pytest.raises(RuntimeError):
            await buypack(rig, own.discord, "gold", ctx=ctx)
        assert rig.ns["_pc_buying"] == set()
    e2e(monkeypatch, tmp_path, body)


# -- the refusal lines -----------------------------------------------------------------------------

REFUSALS = [
    (402, {"error": "insufficient_gold", "status": "rejected", "price": 100}, True,
     "Not enough gold - a pack costs 100 gold. Nothing was charged."),
    (402, {"error": "insufficient_shards", "status": "rejected", "price": 100}, True,
     "Not enough shards - a pack costs 100 shards. Nothing was charged."),
    (409, {"error": "daily_cap", "status": "rejected", "cap": 5}, True,
     "Today's limit of bought packs is 5 - it resets at 00:00 UTC."),
    (409, {"error": "pool_empty", "status": "rejected"}, True,
     "the pack was not bought and nothing was charged."),
    (409, {"error": "pool_empty", "status": "unopened"}, False,
     "the pack stays yours, unopened; `/daily` tries again."),
    (409, {"error": "in_progress"}, False, "That pack is being opened right now"),
    (403, {"error": "banned"}, False, "Player Cards are closed to this account."),
    (404, {"error": "not_linked"}, False, "Not linked."),
    (503, {"error": "renderer_unavailable"}, False, "so nothing was opened - try again later."),
    (0, None, True, "if the pack was bought, `/pack` shows it; look there before buying again."),
    (0, None, False, "`/daily` again opens today's pack, or `/pack` shows it if it opened."),
    (500, None, False, "Couldn't open the pack right now - try again in a moment."),
]


@pytest.mark.parametrize("status, detail, bought, line", REFUSALS)
def test_d2_each_refusal_is_one_line_that_says_what_happened_to_the_pack(status, detail, bought, line):
    """_pc_open_refusal: the line /daily and /buypack send when the api did not
    open the pack, read by status and error token. The purchase lines are the
    ones a player acts on with money: a refused purchase says nothing was
    charged, and an unanswered one points at /pack before buying again. No
    request is made."""
    async def never(call):
        raise AssertionError(f"no request expected: {call.method} {call.path}")
    rig = H.BotRig(never, funcs=OPEN_FUNCS, assigns=OPEN_ASSIGNS, extra={"secrets": secrets, "Literal": Literal})
    body = {"detail": detail} if detail is not None else None
    got = rig.ns["_pc_open_refusal"](rig.ctx(H.discord_of(1)), status, body, bought=bought)
    assert line in got, got
    assert rig.calls == []


# -- Round 2, M1 (server): the answer of a committed purchase ------------------------------------
#
# Codex round 1 MEDIUM 1: the purchase committed, then the subject query or
# the answer's construction after the commit raised, and the api answered 500
# for a purchase it had charged. The fix builds the whole answer inside the
# transaction that debits and mints, keeps only a best-effort refresh after
# the commit, and answers every replay of a committed key with the recorded
# outcome even when its face keys cannot be read.

async def nonce_status(env, nonce):
    """The purchase's status as the harness's own connection sees it: only a
    COMMITTED row is visible there, so None means not committed (yet)."""
    return await env.val(f"SELECT status FROM {SCHEMA}.pc_packs WHERE nonce = :n", {"n": nonce})


async def bought_packs(env, who):
    return await env.val(f"SELECT COUNT(*) FROM {SCHEMA}.pc_packs WHERE player_id = CAST(:p AS uuid)"
                         " AND source = 'bought'", {"p": who.id})


def fail_after_commit(env, monkeypatch, nonce, names=("_pc_pack_subjects", "_pc_face_ctx")):
    """The reviewer's failure: each named api function raises whenever the
    purchase keyed on `nonce` is already committed, and runs as normal before
    that; the Steam prime (the other post-commit step) raises every time.
    Returns the names in the order they raised."""
    main = env.main
    tripped = []

    def after_commit(name, real):
        async def wrapped(*a, **k):
            if await nonce_status(env, nonce) is not None:
                tripped.append(name)
                raise RuntimeError(f"{name} failed after the commit")
            return await real(*a, **k)
        return wrapped
    for name in names:
        monkeypatch.setattr(main, name, after_commit(name, getattr(main, name)))

    async def prime(*a, **k):
        tripped.append("_pc_steam_prime")
        raise RuntimeError("the Steam prime failed")
    monkeypatch.setattr(main, "_pc_steam_prime", prime)
    return tripped


def test_m1_a_failure_after_the_purchase_committed_still_answers_the_pack_and_the_charge(
        monkeypatch, tmp_path, capsys):
    """The purchase commits and everything after the commit fails: the first
    answer is the pack and its charge, built before the commit, and a replay
    of the same nonce answers the same recorded outcome (its face keys cannot
    be read, so its prints carry none). One debit, one ledger row, one pack."""
    async def body(env):
        own, subs = await world(env)
        price = price_of(env, "gold")
        await set_gold(env, own, 10 * price)
        nonce = "m1-after-" + secrets.token_hex(8)
        tripped = fail_after_commit(env, monkeypatch, nonce)
        first = await buy_internal(env, own.discord, nonce, "gold")
        assert first.status_code == 200, (first.status_code, first.text[:300])
        a = first.json()
        assert (a["status"], a["pay"], a["price"]) == ("done", "gold", price), a
        assert len(a["prints"]) == 5 and all(p.get("face_rev") for p in a["prints"]), a["prints"]
        assert tripped == ["_pc_steam_prime"], tripped
        again = await buy_internal(env, own.discord, nonce, "gold")
        assert again.status_code == 200, (again.status_code, again.text[:300])
        b = again.json()
        assert (b["pack_id"], b["status"], b["pay"], b["price"]) == (a["pack_id"], "done", "gold", price), b
        assert [p["print_id"] for p in b["prints"]] == [p["print_id"] for p in a["prints"]]
        assert not any(p.get("face_rev") for p in b["prints"]) and "locale" not in b, b
        assert tripped == ["_pc_steam_prime", "_pc_pack_subjects"], tripped
        assert await nonce_status(env, nonce) == "done"
        assert (await purse(env, own))["gold_spent"] == price and len(await ledger(env, own)) == 1
        assert await bought_packs(env, own) == 1 and await minted(env, a["pack_id"]) == 5
        out = capsys.readouterr().out
        assert "answered as built before the commit; the refresh after it failed" in out, out[-2000:]
        assert "answered without face keys (RuntimeError: _pc_pack_subjects failed after the commit)" in out
    e2e(monkeypatch, tmp_path, body)


def test_m1_the_answer_is_built_inside_the_purchase_so_its_failure_charges_nothing(monkeypatch, tmp_path):
    """The answer's inputs are read inside the transaction that debits: a
    failure there, before the commit, rolls the purchase back - nothing
    charged, no pack, no print - and the same nonce then buys once."""
    async def body(env):
        own, subs = await world(env)
        price = price_of(env, "gold")
        await set_gold(env, own, 10 * price)
        nonce = "m1-inside-" + secrets.token_hex(8)
        real = env.main._pc_pack_subjects
        seen = []

        async def broken(*a, **k):
            seen.append(await nonce_status(env, nonce))
            raise RuntimeError("the subject query failed")
        monkeypatch.setattr(env.main, "_pc_pack_subjects", broken)
        first = await buy_internal(env, own.discord, nonce, "gold")
        assert first.status_code == 500, (first.status_code, first.text[:300])
        assert seen == [None], seen   # it ran before the commit
        assert await nonce_status(env, nonce) is None and await bought_packs(env, own) == 0
        assert await env.val(f"SELECT COUNT(*) FROM {SCHEMA}.pc_prints WHERE owner_player_id = CAST(:p AS uuid)",
                             {"p": own.id}) == 0
        assert (await purse(env, own))["gold_spent"] == 0 and await ledger(env, own) == []
        monkeypatch.setattr(env.main, "_pc_pack_subjects", real)
        env.plan([(s, False, False) for s in subs])
        again = await buy_internal(env, own.discord, nonce, "gold")
        assert again.status_code == 200 and again.json()["price"] == price, (again.status_code, again.text[:300])
        assert (await purse(env, own))["gold_spent"] == price and len(await ledger(env, own)) == 1
        assert await bought_packs(env, own) == 1
    e2e(monkeypatch, tmp_path, body)


def test_m1_the_mods_result_route_answers_the_recorded_purchase_when_its_face_keys_fail(monkeypatch, tmp_path):
    """/pc/packs/result, the mod's recovery of a purchase whose answer it
    lost, answers the committed pack and its charge when the face context
    raises, instead of 500."""
    async def body(env):
        own, subs = await world(env)
        price = price_of(env, "gold")
        await set_gold(env, own, 10 * price)
        nonce = "m1-result-" + secrets.token_hex(8)
        first = await buy_internal(env, own.discord, nonce, "gold")
        assert first.status_code == 200, (first.status_code, first.text[:300])

        async def broken(*a, **k):
            raise RuntimeError("the face context failed")
        monkeypatch.setattr(env.main, "_pc_face_ctx", broken)
        canon = env.main._pc.canon_result(own.steam, nonce)
        r = await env.client.get("/api/v1/pc/packs/result", headers=env.mod_headers(own),
                                 params={"steam_id": own.steam, "sig": H.mod_sig(canon), "nonce": nonce})
        assert r.status_code == 200, (r.status_code, r.text[:300])
        got = r.json()
        assert (got["pack_id"], got["status"], got["pay"], got["price"]) == (
            first.json()["pack_id"], "done", "gold", price), got
        assert [p["print_id"] for p in got["prints"]] == [p["print_id"] for p in first.json()["prints"]]
        assert not any(p.get("face_rev") for p in got["prints"]), got["prints"]
        assert (await purse(env, own))["gold_spent"] == price
    e2e(monkeypatch, tmp_path, body)


def test_m1_a_replayed_held_pack_open_answers_the_recorded_pack_when_its_face_keys_fail(monkeypatch, tmp_path):
    """The same for the other key: a replay of an opened daily pack's id
    answers its recorded prints, not 500, and rolls nothing."""
    async def body(env):
        own, subs = await world(env)
        pack_id = await claim(env, own)
        first = await open_internal(env, own.discord, pack_id)
        assert first.status_code == 200, (first.status_code, first.text[:300])

        async def broken(*a, **k):
            raise RuntimeError("the face context failed")
        monkeypatch.setattr(env.main, "_pc_face_ctx", broken)
        again = await open_internal(env, own.discord, pack_id)
        assert again.status_code == 200, (again.status_code, again.text[:300])
        assert again.json()["pack_id"] == pack_id and again.json()["status"] == "done"
        assert [p["print_id"] for p in again.json()["prints"]] == [p["print_id"] for p in first.json()["prints"]]
        assert await minted(env, pack_id) == 5 and env._plans == []
    e2e(monkeypatch, tmp_path, body)


def test_m1_an_earned_pack_voided_at_open_answers_410_with_its_row_when_its_face_keys_fail(monkeypatch, tmp_path):
    """The void commits before its answer is built (the third committed
    answer in the open): with the face context raising it still answers
    410 voided with the pack's own row, not 500."""
    async def body(env):
        own = await env.player("owner", rating=None)
        pack_id = str(uuid.uuid4())
        await env.ex(f"INSERT INTO {SCHEMA}.pc_packs (id, player_id, source, mode, kind, reference_id, status)"
                     " VALUES (CAST(:id AS uuid), CAST(:p AS uuid), 'earned', '1v1', 'win', :ref, 'unopened')",
                     {"id": pack_id, "p": own.id, "ref": "1v1:" + str(uuid.uuid4())})

        async def broken(*a, **k):
            raise RuntimeError("the face context failed")
        monkeypatch.setattr(env.main, "_pc_face_ctx", broken)
        r = await open_internal(env, own.discord, pack_id)
        assert r.status_code == 410, (r.status_code, r.text[:300])
        d = r.json()["detail"]
        assert (d["error"], d["pack_id"], d["status"], d["source"]) == ("voided", pack_id, "voided", "earned"), d
        assert (await pack_row(env, pack_id))["status"] == "voided"
    e2e(monkeypatch, tmp_path, body)
