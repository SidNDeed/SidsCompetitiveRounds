"""DISCORD-COLLECTION: the bot and end-to-end rows of DISCORD-COLLECTION-DESIGN.md
rev 13, section 10 - the /pack and /binder sequence (S2.3 steps 1-7), the
leases, the byte reader, the retry rules and the deadlines.

Each row is one test named exactly as the table names it; its negative control
is a separate node named test_cNN_... (NN the row id). The mutation of each row
is applied, alone, by discord_collection_controls.py, which records which named
test went red. The shared fixtures are discord_collection_harness.py's.

Two kinds of row live here. END-TO-END rows run the lifted bot (the harness's
BotRig) over the real app on the lane database: every request the bot makes is
forwarded to main.app, and a hook changes the database between two named
requests through a production writer. STUBBED rows answer the bot's requests
from a stub on the rig's fake monotonic clock, for the rows whose claim is an
arithmetic one about time (the deadlines, the retry counts, the per-call
timeouts); their bodies are the shapes the real routes send.

Live PostgreSQL is required by the end-to-end rows, and a missing DSN FAILS by
name (the test_ticket_redaction.py:390-396 shape):
    DISCORD_COLLECTION_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    DISCORD_COLLECTION_TEST_PG_OPTOUT=1   says out loud that this run skips them
"""

import ast
import asyncio
import io
import json
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import text

import discord_collection_harness as H
from discord_collection_harness import SCHEMA

DSN = os.environ.get("DISCORD_COLLECTION_TEST_PG_DSN")
OPTOUT = H.optout(os.environ.get("DISCORD_COLLECTION_TEST_PG_OPTOUT"))


def test_dc_bot_gate_a_missing_dsn_fails_by_name():
    with pytest.raises(BaseException) as ex:
        H.require_pg(None, False)
    assert "Failed" in type(ex.value).__name__
    assert "DISCORD_COLLECTION_TEST_PG_DSN" in str(ex.value)
    with pytest.raises(BaseException) as sk:
        H.require_pg(None, True)
    assert "Skipped" in type(sk.value).__name__


# -- shared helpers --------------------------------------------------------------

PACKS = "/internal/pc/packs"
BINDER = "/internal/pc/binder"
LEASE = "/internal/pc/lease"
PACK_GONE_LINE = "That pack is no longer yours to show - nothing was posted."
PAGE_MOVED_LINE = "That binder page changed while it was being read - nothing was posted. Try again."


def e2e(monkeypatch, tmp_path, fn, **kw):
    dsn = H.require_pg(DSN, OPTOUT)

    async def go():
        async with H.Env(monkeypatch, tmp_path, dsn, **kw) as env:
            return await fn(env)
    return H.run(go())


def _fake_wait_for(clock):
    """asyncio.wait_for on the rig's clock: the awaited call runs to its end
    (a real-time timer would count the app's own work, which the model does
    not), and a call that spent more than `timeout` of the rig's time raises
    as the real one would have."""
    async def wait_for(aw, timeout=None):
        t0 = clock.now
        out = await aw
        if timeout is not None and clock.now - t0 > float(timeout):
            raise asyncio.TimeoutError()
        return out
    return wait_for


def make_rig(handler, *, clock=None, funcs=H.REVEAL_FUNCS, assigns=H.REVEAL_ASSIGNS, extra=None, source=None):
    """A BotRig whose handler records each answer on its call (call.reply)."""
    async def tapped(call):
        reply = await handler(call)
        call.reply = reply
        return reply
    rig = H.BotRig(tapped, clock=clock, funcs=funcs, assigns=assigns, extra=extra, source=source)
    rig.ns["asyncio"].wait_for = _fake_wait_for(rig.clock)
    return rig


def app_rig(env, hooks=None, stub=None, **kw):
    """The rig over the real app. `stub(call)` may answer a request itself
    (a Reply) or return None to forward it; hooks run only on forwarded
    requests (the harness's asgi_handler)."""
    base = H.asgi_handler(env, hooks)

    async def handler(call):
        if stub is not None:
            reply = await stub(call)
            if reply is not None:
                return reply
        return await base(call)
    return make_rig(handler, **kw)


def is_json(call, kind):
    """A reveal's JSON read; for /pack, step 1 (`index`) or the final re-read
    (`pack_id`)."""
    return call.method == "GET" and call.path == (PACKS if kind == "pack" else BINDER) and (
        kind != "pack" or "pack_id" in call.params or "index" in call.params)


def is_bytes(call):
    return call.method == "GET" and call.path.endswith(".png")


def is_acquire(call):
    return call.method == "POST" and call.path == LEASE


def is_check(call):
    return call.method == "GET" and call.path.startswith(LEASE + "/")


def json_calls(rig, kind):
    return [c for c in rig.calls if is_json(c, kind)]


def body_of(call):
    try:
        return json.loads(call.reply.body.decode("utf-8"))
    except Exception:
        return None


def checks(rig):
    return [c for c in rig.calls if is_check(c)]


def acquired_subjects(rig):
    return sorted(str((c.payload or {}).get("subject_ref")) for c in rig.acquires())


def manifest(call, kind="pack"):
    raw = call.reply.headers.get("x-strip-slots" if kind == "pack" else "x-grid-slots")
    return [tuple(x.split(":")) for x in raw.split(",")] if raw else []


def hex32(ref):
    return str(ref).replace("-", "").lower()


def posted(rig):
    """(attachments, texts) of everything the bot sent."""
    return rig.attachments(), rig.texts()


async def pack_of(env, *, owner=None, subjects=None, flags=None, n=5, tag="s"):
    """A snapshot and one opened pack: slot i deals subjects[i-1]."""
    subs = subjects if subjects is not None else await H.pool(env, n, tag=tag)
    own = owner or await env.player("owner", rating=None)
    await env.snapshot()
    flags = flags or [(False, False)] * len(subs)
    pack = await env.open_pack(own, [(s, f, g) for s, (f, g) in zip(subs, flags)])
    return own, subs, pack


async def set_steam(env, who, value):
    await env.ex(f"UPDATE {SCHEMA}.players SET steam_id = :s WHERE id = CAST(:p AS uuid)",
                 {"s": value, "p": who.id})


def no_steam():
    return "dc_x_" + secrets.token_hex(4)


async def run_pack(rig, who, index=1, private=False, slash=False):
    await rig.pack(rig.ctx(who.discord, slash=slash), index, private)


async def run_binder(rig, viewer, owner=None, page=1):
    member = rig.member(owner.discord) if owner is not None and owner is not viewer else None
    await rig.binder(rig.ctx(viewer.discord), member, page)


def one_post_with_image(rig):
    atts, texts = posted(rig)
    assert len(rig.sent) == 1, [t[:120] for t in texts]
    assert len(atts) == 1, [t[:120] for t in texts]
    return atts[0]


def one_post_without_image(rig):
    atts, texts = posted(rig)
    assert len(rig.sent) == 1, [t[:120] for t in texts]
    assert atts == [], "an image was attached"
    return texts[0]


def logged(rig, needle):
    return [line for line in rig.logs if needle in line]


# -- 12c, 12j: backs take no lease and the picture still posts -----------------------

def test_a_pack_with_a_no_steamid64_subject_still_posts_an_image(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        await set_steam(env, subs[1], no_steam())
        rig = app_rig(env)
        await run_pack(rig, own)
        att = one_post_with_image(rig)
        assert H.image_of(att.file.data).size == (1947, 549)
        man = manifest([c for c in rig.calls if is_bytes(c)][0])
        assert [m[3] for m in man] == ["face", "back", "face", "face", "face"], man
        assert man[1][4] == "no_steam_id", man
        want = sorted(s.id for i, s in enumerate(subs) if i != 1)
        assert acquired_subjects(rig) == want, acquired_subjects(rig)
        assert len(rig.releases()) == 4
    e2e(monkeypatch, tmp_path, body)


def test_c12c_a_409_on_any_face_lease_still_drops_the_image(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        await set_steam(env, subs[1], no_steam())
        busy = str(sorted(s.id for i, s in enumerate(subs) if i != 1)[2])

        async def stub(call):
            if is_acquire(call) and (call.payload or {}).get("subject_ref") == busy:
                return H.Reply(409, json={"detail": {"error": "subject_busy", "retry_after": 2}})
            return None
        rig = app_rig(env, stub=stub)
        await run_pack(rig, own)
        one_post_without_image(rig)
        assert [c.status for c in rig.acquires() if (c.payload or {}).get("subject_ref") == busy] == [409]
        taken = [c for c in rig.acquires() if c.status == 200]
        assert taken and len(rig.releases()) == len(taken), "every lease taken is released"
    e2e(monkeypatch, tmp_path, body)


def test_the_print_gone_slot_needs_no_lease_and_the_pack_posts(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        await env.delete_data(subs[2])
        rig = app_rig(env)
        await run_pack(rig, own)
        one_post_with_image(rig)
        man = manifest([c for c in rig.calls if is_bytes(c)][0])
        assert man[2][3:] == ("back", "print_gone", "gone"), man
        assert len(rig.acquires()) == 4, acquired_subjects(rig)
        assert subs[2].id not in acquired_subjects(rig)
    e2e(monkeypatch, tmp_path, body)


def test_c12j_a_no_steam_id_back_still_needs_no_lease_and_still_posts(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        await set_steam(env, subs[4], no_steam())
        rig = app_rig(env)
        await run_pack(rig, own)
        one_post_with_image(rig)
        assert subs[4].id not in acquired_subjects(rig)
        assert len(rig.acquires()) == 4
    e2e(monkeypatch, tmp_path, body)


# -- 12k: a banned subject's slot is the back, and takes no lease ---------------

def byte_call(rig):
    calls = [c for c in rig.calls if is_bytes(c)]
    assert calls, "no byte GET was made"
    return calls[-1]


def lease_of(rig, subject_id):
    for c in rig.acquires():
        if (c.payload or {}).get("subject_ref") == str(subject_id) and c.status == 200:
            return body_of(c)["lease_id"]
    return None


def check_of(rig, subject_id):
    lid = lease_of(rig, subject_id)
    found = [c for c in checks(rig) if lid and c.path == f"{LEASE}/{lid}"]
    return found[0] if found else None


async def plated_tile(env, print_id):
    """The tile render_face draws for this print right now (the portrait, or
    the plate when there is none) - what rule 5 would paste."""
    main = env.main
    async with env.database.async_session() as db:
        row = await main._pc_face_row(db, print_id)
        ctx = await main._pc_face_ctx(db, "en")
        _rev, data = await main._pc_render_face(db, row, ctx, "tile")
    return H.image_of(data)


def test_a_banned_subjects_slot_draws_the_back_and_takes_no_lease(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        s = subs[2]
        prints = await env.pack_prints(pack)
        await env.ban(s)
        rig = app_rig(env)
        await run_pack(rig, own)
        strip = H.image_of(byte_call(rig).reply.body)
        cell = strip.crop(H.slot_rect(3))
        assert H.same_pixels(cell, env.main._pcstrip.strip_back_tile()), "slot 3 is not the card back"
        plated = await plated_tile(env, prints[2]["print_id"])
        assert not H.same_pixels(cell, plated), (
            "slot 3 carries the banned subject's card (name, rank, rating, title)")
        assert s.id not in acquired_subjects(rig), "a lease was taken for the banned subject"
        att = one_post_with_image(rig)
        man = manifest(byte_call(rig))
        assert [m[3] for m in man] == ["face", "face", "back", "face", "face"], man
        assert man[2][4] == "subject_banned", man
        assert att.file.data == byte_call(rig).reply.body
    e2e(monkeypatch, tmp_path, body)


def test_c12k_an_unbanned_subject_with_no_portrait_draws_the_plated_face_and_is_leased(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        s = subs[2]
        prints = await env.pack_prints(pack)
        found = await env.rows(f"SELECT pc_game_portrait_hash, pc_steam_portrait_hash FROM {SCHEMA}.players"
                               " WHERE id = CAST(:p AS uuid)", {"p": s.id})
        assert found[0]["pc_game_portrait_hash"] is None and found[0]["pc_steam_portrait_hash"] is None
        rig = app_rig(env)
        await run_pack(rig, own)
        att = one_post_with_image(rig)
        cell = H.image_of(att.file.data).crop(H.slot_rect(3))
        assert not H.same_pixels(cell, env.main._pcstrip.strip_back_tile())
        assert H.same_pixels(cell, await plated_tile(env, prints[2]["print_id"]))
        assert s.id in acquired_subjects(rig)
    e2e(monkeypatch, tmp_path, body)


# -- 12l, 12m: the revalidation's two refusals --------------------------------------

def _lease_gone(call):
    assert call is not None, "the subject's lease was never re-validated"
    assert call.status == 404, f"the revalidation answered HTTP {call.status}, not 404"
    assert body_of(call) == {"detail": {"error": "lease_gone"}}, body_of(call)


def test_a_ban_landing_after_the_row_read_drops_the_image(monkeypatch, tmp_path):
    """The ban lands after the JSON read and the byte GET (both saw S drawable)
    and before the first acquire: a ban writer drains the leases naming its
    subject first, so while this reveal holds S's lease it could not commit
    (S2.4, 14q). The acquire does not refuse a ban; the revalidation does."""
    async def body(env):
        own, subs, pack = await pack_of(env)
        s = subs[1]

        async def ban(call):
            await env.ban(s)
        rig = app_rig(env, hooks=[(is_acquire, ban)])
        await run_pack(rig, own)
        assert [m[3] for m in manifest(byte_call(rig))][1] == "face", "the byte GET did not see S drawable"
        text_ = one_post_without_image(rig)
        assert text_.startswith("**Pack 1**"), text_[:200]
        _lease_gone(check_of(rig, s.id))
    e2e(monkeypatch, tmp_path, body)


def test_c12l_with_no_ban_the_same_run_still_sends_the_image(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        rig = app_rig(env)
        await run_pack(rig, own)
        one_post_with_image(rig)
        assert check_of(rig, subs[1].id).status == 200
    e2e(monkeypatch, tmp_path, body)


def test_a_moved_portrait_hash_drops_the_image(monkeypatch, tmp_path):
    """S unbanned, not deleted, a SteamID64, the print live and the pack the
    actor's own - clauses 1-5 all pass; S is pictured, so the acquire stores
    a hash. S replaces the portrait through the production upload path after
    the acquire, inside S's own revalidation request, before it is served."""
    async def body(env):
        subs = await H.pool(env, 5)
        s = subs[3]
        before = await env.give_portrait(s, 11)
        own, subs, pack = await pack_of(env, subjects=subs)
        state = {}

        async def replace(call):
            state["after"] = await env.upload_portrait(s, 12)

        def s_check(call):
            lid = lease_of(rig, s.id)
            return is_check(call) and lid is not None and call.path == f"{LEASE}/{lid}"
        rig = app_rig(env, hooks=[(s_check, replace)])
        await run_pack(rig, own)
        assert state.get("after") and state["after"] != before, state
        acq = [c for c in rig.acquires() if (c.payload or {}).get("subject_ref") == s.id][0]
        assert body_of(acq)["portrait_hash"] == before, "the acquire did not store the picture's hash"
        text_ = one_post_without_image(rig)
        assert text_.startswith("**Pack 1**"), text_[:200]
        # Beyond the row's text (build notes, FINDING 5): the step-5 status is
        # asserted, as 12l's is - the re-read's drawn-member comparison also
        # drops this image (face_rev covers the portrait hash), so the two
        # assertions above cannot tell whether the revalidation refused.
        _lease_gone(check_of(rig, s.id))
    e2e(monkeypatch, tmp_path, body)


def test_c12m_the_same_run_with_the_portrait_left_alone_still_attaches_the_image(monkeypatch, tmp_path):
    async def body(env):
        subs = await H.pool(env, 5)
        await env.give_portrait(subs[3], 11)
        own, subs, pack = await pack_of(env, subjects=subs)
        rig = app_rig(env)
        await run_pack(rig, own)
        one_post_with_image(rig)
        assert check_of(rig, subs[3].id).status == 200
    e2e(monkeypatch, tmp_path, body)


# -- the K-inserted page (14d, and 12n's manifest clause) ------------------------

async def k_inserted_page(env, base=2000.0, tag="k"):
    """Owner O with exactly ten live prints, one per subject S1..S10 of a pool
    of fourteen, so page 1 reads S1..S10 in the binder order (A-J). Returns
    (O, subjects, hooks-maker): the hooks insert K - a SIGNED print of S1, so
    it sorts above A - with four prints of S11..S14 that sort after J, just
    before the byte GET, and discard K again just before the re-read."""
    subs = await H.pool(env, 14, base=base, tag=tag)
    own = await env.player(f"{tag}-owner", rating=None)
    await env.snapshot()
    await env.open_pack(own, subs[0:5])
    await env.open_pack(own, subs[5:10])
    state = {}

    async def insert_k(call):
        pack = await env.open_pack(own, [(subs[0], False, True)] + subs[10:14])
        rows = await env.pack_prints(pack)
        state["k"] = [r for r in rows if r["slot"] == 1][0]["print_id"]

    async def discard_k(call):
        await env.discard(own, state["k"])

    def hooks():
        return [(is_bytes, insert_k), (lambda c: is_json(c, "binder") and c.n == 2, discard_k)]
    return own, subs, hooks, state


def assert_k_inserted_outcome(rig, subs, state):
    """14d's baseline: no attachment, the list A-J rendered from the re-read,
    and the log line naming the manifest comparison."""
    calls = json_calls(rig, "binder")
    assert len(calls) == 2, f"expected the read and the re-read, got {len(calls)} binder JSON reads"
    first, again = calls
    names = [p["subject_name"] for p in body_of(first)["prints"]]
    assert names == [s.name for s in subs[:10]], names
    man = manifest(byte_call(rig), "binder")
    assert man[0][1] == hex32(state["k"]), "the manifest does not lead with K"
    assert [m[1] for m in man[1:]] == [hex32(p["print_id"]) for p in body_of(first)["prints"][:9]]
    assert [p["subject_name"] for p in body_of(again)["prints"]] == names, "the re-read does not agree"
    text_ = one_post_without_image(rig)
    lines = text_.split(chr(10))[2:12]
    assert [re.search(r"[*][*](.+?)[*][*]", ln).group(1) for ln in lines] == names, lines
    assert logged(rig, "picture dropped: manifest assertion"), rig.logs


# -- 12n: the first failing clause names the outcome ------------------------------

async def _n1_banned(env):
    own, subs, pack = await pack_of(env, subjects=await H.pool(env, 5, base=3000.0, tag="n1"))
    await env.ban(subs[2])
    rig = app_rig(env)
    await run_pack(rig, own)
    man = manifest(byte_call(rig))
    assert man[2][3:5] == ("back", "subject_banned"), f"clause 1: slot 3 is {man[2][3:5]}"
    assert subs[2].id not in acquired_subjects(rig), "clause 1: the banned subject was leased"
    assert len(rig.attachments()) == 1, "clause 1: the picture did not post"


async def _n2_ownership(env):
    own, subs, pack = await pack_of(env, subjects=await H.pool(env, 5, base=2900.0, tag="n2"))
    other = await env.player("n2-other", rating=None, discord=False)

    async def move(call):
        await env.rebind(own.discord, other)
    rig = app_rig(env, hooks=[(is_bytes, move)])
    await run_pack(rig, own)
    assert byte_call(rig).status == 404, f"clause 2: the strip answered {byte_call(rig).status}"
    assert rig.acquires() == [], "clause 2: a lease was taken"
    assert rig.attachments() == [], "clause 2: a picture was posted"


async def _n3_consent(env):
    own, subs, pack = await pack_of(env, subjects=await H.pool(env, 5, base=2800.0, tag="n3"))
    viewer = await env.player("n3-viewer", rating=None)

    async def private(call):
        await env.set_public(own, False)
    rig = app_rig(env, hooks=[(is_bytes, private)])
    await run_binder(rig, viewer, own)
    got = byte_call(rig)
    assert got.status == 403 and body_of(got) == {"detail": {"error": "private"}}, (
        f"clause 3: the grid answered {got.status} {body_of(got)}")
    assert rig.acquires() == [], "clause 3: a lease was taken"
    assert rig.attachments() == [], "clause 3: a picture was posted"


async def _n4_manifest(env):
    own, subs, hooks, state = await k_inserted_page(env, base=2700.0, tag="n4")
    rig = app_rig(env, hooks=hooks())
    await run_binder(rig, own)
    assert rig.attachments() == [], "clause 4: the picture posted"
    assert_k_inserted_outcome(rig, subs, state)


async def _n5_expired(env):
    own, subs, pack = await pack_of(env, subjects=await H.pool(env, 5, base=2600.0, tag="n5"))
    s = subs[0]

    async def expire(call):
        await env.ex(f"UPDATE {SCHEMA}.pc_delivery_leases SET until = now() - interval '1 second'"
                     " WHERE id = CAST(:l AS uuid)", {"l": lease_of(rig, s.id)})

    def s_check(call):
        lid = lease_of(rig, s.id)
        return is_check(call) and lid is not None and call.path == f"{LEASE}/{lid}"
    rig = app_rig(env, hooks=[(s_check, expire)])
    await run_pack(rig, own)
    assert rig.attachments() == [], "clause 5: the picture posted"
    assert len(rig.sent) == 1 and rig.texts()[0].startswith("**Pack 1**"), "clause 5: the list did not post"
    _lease_gone(check_of(rig, s.id))


async def _n6_portrait(env):
    subs = await H.pool(env, 5, base=2500.0, tag="n6")
    s = subs[3]
    await env.give_portrait(s, 21)
    own, subs, pack = await pack_of(env, subjects=subs)

    async def replace(call):
        await env.upload_portrait(s, 22)

    def s_check(call):
        lid = lease_of(rig, s.id)
        return is_check(call) and lid is not None and call.path == f"{LEASE}/{lid}"
    rig = app_rig(env, hooks=[(s_check, replace)])
    await run_pack(rig, own)
    assert rig.attachments() == [], "clause 6: the picture posted"
    assert len(rig.sent) == 1 and rig.texts()[0].startswith("**Pack 1**"), "clause 6: the list did not post"
    _lease_gone(check_of(rig, s.id))


async def _n7_reread(env):
    own, subs, pack = await pack_of(env, subjects=await H.pool(env, 5, base=2400.0, tag="n7"))
    other = await env.player("n7-other", rating=None, discord=False)

    async def move(call):
        await env.rebind(own.discord, other)
    rig = app_rig(env, hooks=[(lambda c: is_json(c, "pack") and c.n == 2, move)])
    await run_pack(rig, own)
    assert rig.attachments() == [], "clause 7: the picture posted"
    assert rig.texts() == [PACK_GONE_LINE], f"clause 7: posted {[t[:80] for t in rig.texts()]}"


RUNS_12N = (("1", _n1_banned), ("2", _n2_ownership), ("3", _n3_consent), ("4", _n4_manifest),
            ("5", _n5_expired), ("6", _n6_portrait), ("7", _n7_reread))


def test_the_first_failing_clause_names_the_outcome(monkeypatch, tmp_path):
    """Seven runs; run n fails clause n and satisfies clauses 1..n-1 (S5's
    ordered list). Every run executes; the failures are named together, so a
    single-clause deletion shows exactly which runs it reddened."""
    async def body(env):
        failed = {}
        for name, fn in RUNS_12N:
            try:
                await fn(env)
            except Exception as ex:
                failed[name] = (type(ex).__name__ + ": " + " ".join(str(ex).split()))[:240]
        for name in sorted(failed):
            print(f"ROW12N run {name} FAILED: {failed[name]}")
        assert not failed, f"ROW12N failed runs: {','.join(sorted(failed))}"
    e2e(monkeypatch, tmp_path, body)


def test_c12n_the_all_clean_fixture_posts_the_image(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        rig = app_rig(env)
        await run_pack(rig, own)
        one_post_with_image(rig)
        assert all(c.status == 200 for c in checks(rig)) and len(checks(rig)) == 5
    e2e(monkeypatch, tmp_path, body)


# -- 14: every lease re-validated ----------------------------------------------------

def _check_for(rig, subject_id):
    def pred(call):
        lid = lease_of(rig, subject_id)
        return is_check(call) and lid is not None and call.path == f"{LEASE}/{lid}"
    return pred


def test_send_is_dropped_when_any_lease_is_gone(monkeypatch, tmp_path):
    """The lease that is gone is the LAST one the gather asks about (the
    helper keys them in ascending subject order), so a check of the first
    alone would pass."""
    async def body(env):
        own, subs, pack = await pack_of(env)
        last = max(s.id for s in subs)

        async def drop(call):
            await env.ex(f"DELETE FROM {SCHEMA}.pc_delivery_leases WHERE id = CAST(:l AS uuid)",
                         {"l": lease_of(rig, last)})
        rig = app_rig(env, hooks=[(lambda c: _check_for(rig, last)(c), drop)])
        await run_pack(rig, own)
        assert len(checks(rig)) == 5
        assert check_of(rig, last).status == 404
        assert min(s.id for s in subs) != last and check_of(rig, min(s.id for s in subs)).status == 200
        one_post_without_image(rig)
    e2e(monkeypatch, tmp_path, body)


def test_c14_all_live_still_sends(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        rig = app_rig(env)
        await run_pack(rig, own)
        one_post_with_image(rig)
        assert [c.status for c in checks(rig)] == [200] * 5
    e2e(monkeypatch, tmp_path, body)


# -- 14c: no face, no byte GET ---------------------------------------------------------

def test_no_lease_taken_means_no_byte_get(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        for s in subs:
            await set_steam(env, s, no_steam())
        rig = app_rig(env)
        await run_pack(rig, own)
        assert rig.byte_gets() == [], [c.path for c in rig.byte_gets()]
        assert rig.acquires() == []
        text_ = one_post_without_image(rig)
        assert text_.startswith("**Pack 1**")
    e2e(monkeypatch, tmp_path, body)


def test_c14c_one_face_entry_with_its_lease_still_fetches(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        for s in subs[1:]:
            await set_steam(env, s, no_steam())
        rig = app_rig(env)
        await run_pack(rig, own)
        assert len(rig.byte_gets()) == 1
        assert acquired_subjects(rig) == [subs[0].id]
        one_post_with_image(rig)
    e2e(monkeypatch, tmp_path, body)


# -- 14d: the manifest binds the picture to the list -------------------------------------

def test_grid_is_dropped_when_the_manifest_differs_from_the_list_even_though_the_reread_agrees(monkeypatch, tmp_path):
    """JSON = A-J, manifest = K,A-I, re-read = A-J (K inserted before the byte
    GET and discarded again before the re-read). The log line names the
    comparison that failed: the id pair (build notes, FINDING 6 - face_rev,
    which covers the print's short id, fails at the same positions, so the
    attachment alone cannot tell the id comparison from the word one)."""
    async def body(env):
        own, subs, hooks, state = await k_inserted_page(env)
        rig = app_rig(env, hooks=hooks())
        await run_binder(rig, own)
        assert_k_inserted_outcome(rig, subs, state)
        assert logged(rig, "picture dropped: manifest assertion ids"), rig.logs
    e2e(monkeypatch, tmp_path, body)


def test_c14d_an_undisturbed_page_posts_the_image_and_the_text(monkeypatch, tmp_path):
    async def body(env):
        own, subs, hooks, state = await k_inserted_page(env)
        rig = app_rig(env)
        await run_binder(rig, own)
        att = one_post_with_image(rig)
        lines = att.content.split(chr(10))[2:12]
        assert [re.search(r"[*][*](.+?)[*][*]", ln).group(1) for ln in lines] == [s.name for s in subs[:10]]
    e2e(monkeypatch, tmp_path, body)


# -- 14h, 14i, 14j, 14e, 14f: the re-read is last, and unconditional ------------------------

def test_the_final_reread_runs_on_the_text_only_branch(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        other = await env.player("other", rating=None, discord=False)

        async def move(call):
            await env.rebind(own.discord, other)
        rig = app_rig(env, hooks=[(is_bytes, move)])
        await run_pack(rig, own)
        assert byte_call(rig).status == 404
        assert rig.attachments() == []
        assert rig.texts() == [PACK_GONE_LINE], [t[:80] for t in rig.texts()]
    e2e(monkeypatch, tmp_path, body)


def test_c14h_a_404_with_no_rebind_still_posts_the_text_list(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)

        async def stub(call):
            if is_bytes(call):
                return H.Reply(404, json={"detail": "Not found"})
            return None
        rig = app_rig(env, stub=stub)
        await run_pack(rig, own)
        text_ = one_post_without_image(rig)
        assert text_.startswith("**Pack 1**"), text_[:120]
    e2e(monkeypatch, tmp_path, body)


def test_the_consent_reread_is_the_last_read_before_the_post(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        viewer = await env.player("viewer", rating=None)

        async def private(call):
            await env.set_public(own, False)
        rig = app_rig(env, hooks=[(is_check, private)])
        await run_binder(rig, viewer, own)
        assert len(checks(rig)) == 5, "the withdrawal did not land inside the lease GETs"
        assert rig.attachments() == []
        assert rig.texts() == ["member's binder is private."], [t[:80] for t in rig.texts()]
    e2e(monkeypatch, tmp_path, body)


def test_c14i_a_binder_that_stays_public_through_both_still_posts(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        viewer = await env.player("viewer", rating=None)
        rig = app_rig(env)
        await run_binder(rig, viewer, own)
        one_post_with_image(rig)
    e2e(monkeypatch, tmp_path, body)


def test_a_rebind_between_the_reads_is_caught_by_owner_ref(monkeypatch, tmp_path):
    async def body(env):
        a = await env.player("a", rating=None)
        b = await env.player("b", rating=None, discord=False)
        revs = await env.rows(f"SELECT pc_settings_revision AS r FROM {SCHEMA}.players"
                              " WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid))", {"a": a.id, "b": b.id})
        assert len({r["r"] for r in revs}) == 1, revs

        async def move(call):
            await env.rebind(a.discord, b)
        rig = app_rig(env, hooks=[(lambda c: is_json(c, "binder") and c.n == 2, move)])
        await run_binder(rig, a)
        first, again = json_calls(rig, "binder")
        assert body_of(first)["prints"] == [] and body_of(again)["prints"] == []
        assert body_of(first)["owner_ref"] == a.id and body_of(again)["owner_ref"] == b.id
        assert body_of(again)["settings_rev"] == body_of(first)["settings_rev"], "the rebind moved settings_rev"
        assert rig.texts() == [PAGE_MOVED_LINE], [t[:80] for t in rig.texts()]
    e2e(monkeypatch, tmp_path, body)


def test_c14j_an_unchanged_owner_still_posts(monkeypatch, tmp_path):
    async def body(env):
        a = await env.player("a", rating=None)
        rig = app_rig(env)
        await run_binder(rig, a)
        text_ = one_post_without_image(rig)
        assert "No prints yet." in text_
    e2e(monkeypatch, tmp_path, body)


def test_grid_is_dropped_when_consent_rev_moved(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)

        async def flip(call):
            await env.set_public(own, False)
        rig = app_rig(env, hooks=[(lambda c: is_json(c, "binder") and c.n == 2, flip)])
        await run_binder(rig, own)
        first, again = json_calls(rig, "binder")
        assert body_of(again)["settings_rev"] == body_of(first)["settings_rev"] + 1
        assert rig.attachments() == []
        assert rig.texts() == [PAGE_MOVED_LINE], [t[:80] for t in rig.texts()]
    e2e(monkeypatch, tmp_path, body)


def test_c14e_an_unchanged_rev_still_sends(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        rig = app_rig(env)
        await run_binder(rig, own)
        one_post_with_image(rig)
    e2e(monkeypatch, tmp_path, body)


def test_pack_is_dropped_when_actor_ref_moved(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        other = await env.player("other", rating=None, discord=False)

        async def move(call):
            await env.rebind(own.discord, other)
        rig = app_rig(env, hooks=[(is_acquire, move)])
        await run_pack(rig, own)
        assert byte_call(rig).status == 200, "the rebind landed before the image GET"
        assert rig.attachments() == []
        assert rig.texts() == [PACK_GONE_LINE], [t[:80] for t in rig.texts()]
    e2e(monkeypatch, tmp_path, body)


def test_c14f_an_unchanged_actor_still_sends(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        rig = app_rig(env)
        await run_pack(rig, own)
        one_post_with_image(rig)
    e2e(monkeypatch, tmp_path, body)


# -- 14l: a tie flips neither the digest nor the binding ---------------------------------

async def tied_pair(env):
    """Owner O with exactly two live prints X and Y: one pack, one subject in
    slots 1 and 2, same rarity, foil and signed, so the same pool_rank and,
    from one transaction, the same minted_at. Returns (O, LO, HI)."""
    subs = await H.pool(env, 4)
    owner = await env.player("owner", rating=None)
    await env.snapshot()
    pack = await env.open_pack(owner, [subs[0], subs[0], subs[1], subs[2], subs[3]])
    prints = await env.pack_prints(pack)
    x, y = prints[0], prints[1]
    assert x["subject"] == y["subject"]
    assert (x["rarity"], x["foil"], x["signed"]) == (y["rarity"], y["foil"], y["signed"])
    for p in prints[2:]:
        await env.discard(owner, p["print_id"])
    lo, hi = sorted([x["print_id"], y["print_id"]])
    keys = await env.rows(f"SELECT pool_rank, minted_at FROM {SCHEMA}.pc_prints"
                          " WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid))", {"a": lo, "b": hi})
    assert len({(k["pool_rank"], k["minted_at"]) for k in keys}) == 1, keys
    return owner, lo, hi


async def touch(env, print_id):
    """A no-op UPDATE of a mutable column: a new version of the row, and no
    logical change. Where the version lands is the server's choice (heap_to)."""
    await env.ex(f"UPDATE {SCHEMA}.pc_prints SET owner_player_id = owner_player_id WHERE id = CAST(:p AS uuid)",
                 {"p": print_id})


async def heap_order(env, owner):
    return [r["id"] for r in await env.rows(
        f"SELECT id::text AS id FROM {SCHEMA}.pc_prints WHERE owner_player_id = CAST(:o AS uuid)"
        " AND discarded_at IS NULL ORDER BY ctid", {"o": owner.id})]


async def heap_to(env, owner, want, tries=32):
    """Bring the owner's two live prints to the physical order `want` with
    no-op UPDATEs only, so no logical state changes. The rows expect one no-op
    UPDATE of the print that should read last to land at the heap's tail, but
    PostgreSQL gives an updated tuple the lowest free line pointer when its
    page has one, and that can sit below the other print (build notes,
    FINDING 8). So the print that should read last is updated first, then the
    two alternate, until the heap reads `want` - bounded, and a failure names
    the order the heap read."""
    got = None
    for n in range(tries):
        await touch(env, want[1] if n % 2 == 0 else want[0])
        got = await heap_order(env, owner)
        if got == want:
            return n + 1
    raise AssertionError(f"the heap reads {got}, not {want}, after {tries} no-op UPDATEs")


def _drop_binder_composites(env):
    dropped = 0
    for p in sorted(env.faces_root.rglob("*")):
        if p.is_file() and p.relative_to(env.faces_root).as_posix().startswith("binder/"):
            p.unlink()
            dropped += 1
    assert dropped >= 1, "no binder composite was cached, so the second pass was not a cold read"


async def _binder_pass(env, owner):
    rig = app_rig(env)
    await run_binder(rig, owner)
    att = one_post_with_image(rig)
    assert not logged(rig, "manifest assertion"), rig.logs
    first = body_of(json_calls(rig, "binder")[0])
    seq = [p["print_id"] for p in first["prints"]]
    man = manifest(byte_call(rig), "binder")
    assert [m[1] for m in man] == [hex32(x) for x in seq], (man, seq)
    return seq, byte_call(rig).reply.headers.get("x-grid-rev"), att


def test_a_tie_does_not_flip_the_binder_digest_or_the_binding(monkeypatch, tmp_path):
    async def body(env):
        owner, lo, hi = await tied_pair(env)
        await heap_to(env, owner, [hi, lo])
        seq1, rev1, _ = await _binder_pass(env, owner)
        await heap_to(env, owner, [lo, hi])
        _drop_binder_composites(env)
        seq2, rev2, _ = await _binder_pass(env, owner)
        print(f"ROW14L pass1 {seq1} rev {rev1}; pass2 {seq2} rev {rev2}")
        assert seq2 == seq1, (seq1, seq2)
        assert rev2 == rev1, (rev1, rev2)
    e2e(monkeypatch, tmp_path, body)


def test_c14l_with_the_key_the_same_heap_flip_still_attaches_and_keeps_one_digest(monkeypatch, tmp_path):
    """Stated with the key present in both places, i.e. over the UNMUTATED
    tree (build notes, FINDING 8): the heap flip is asserted, so under the
    row's mutation this reads the flipped order by construction."""
    async def body(env):
        owner, lo, hi = await tied_pair(env)
        await heap_to(env, owner, [lo, hi])
        seq1, rev1, _ = await _binder_pass(env, owner)
        await heap_to(env, owner, [hi, lo])
        _drop_binder_composites(env)
        seq2, rev2, _ = await _binder_pass(env, owner)
        assert seq1 == seq2 == [lo, hi] and rev1 == rev2
    e2e(monkeypatch, tmp_path, body)


# -- 14n, 14o, 14p, 14q: the caption and the picture agree ----------------------------------

def test_a_subject_renamed_between_the_two_reads_drops_the_image(monkeypatch, tmp_path):
    """The rename lands between the JSON read and the byte GET, through the
    production writer. The log line attributes the drop to the tuple
    comparison (build notes: the re-read's drawn members also catch a rename,
    so the dropped image alone cannot tell which check fired)."""
    async def body(env):
        own, subs, pack = await pack_of(env)

        async def rename(call):
            await env.rename(subs[1], "Fixture renamed s2")
        rig = app_rig(env, hooks=[(is_bytes, rename)])
        await run_pack(rig, own)
        text_ = one_post_without_image(rig)
        assert "Fixture renamed s2" in text_
        assert logged(rig, "picture dropped: manifest assertion face_rev"), rig.logs
    e2e(monkeypatch, tmp_path, body)


def test_c14n_no_rename_posts_the_image_and_a_back_entry_is_unaffected(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        await set_steam(env, subs[4], no_steam())
        rig = app_rig(env)
        await run_pack(rig, own)
        one_post_with_image(rig)
        assert manifest(byte_call(rig))[4][3:5] == ("back", "no_steam_id")
    e2e(monkeypatch, tmp_path, body)


async def _neutral_label(env, locale="en"):
    async with env.database.async_session() as db:
        ctx = await env.main._pc_face_ctx(db, env.main._pcp.effective_locale(locale, env.main._pc_served_locales()))
    return env.main._pc_neutral_name(ctx)


def test_the_caption_is_rendered_from_the_final_reread(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        b = subs[2]
        old_name = b.name

        async def erase(call):
            await env.delete_data(b)
        rig = app_rig(env, hooks=[(is_bytes, erase)])
        await run_pack(rig, own)
        first = body_of(json_calls(rig, "pack")[0])
        assert first["packs"][0]["prints"][2]["subject_name"] == old_name, "step 1 did not read B's name"
        assert rig.attachments() == [], "the picture posted"
        assert manifest(byte_call(rig))[2][3:] == ("back", "print_gone", "gone")
        assert all(old_name not in t for t in rig.texts()), "B's pre-erasure name was posted"
        label = await _neutral_label(env)
        line3 = [ln for ln in rig.texts()[0].split(chr(10)) if ln.startswith("3. ")]
        assert len(line3) == 1 and line3[0].endswith(f"**{label}**"), (line3, label)
    e2e(monkeypatch, tmp_path, body)


def test_c14o_the_same_pack_with_no_erasure_posts_the_names_step_1_would_have(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        rig = app_rig(env)
        await run_pack(rig, own)
        att = one_post_with_image(rig)
        first = body_of(json_calls(rig, "pack")[0])
        assert att.content == rig.ns["_pc_reveal_pack_text"](first, 1, None)
        assert all(s.name in att.content for s in subs)
    e2e(monkeypatch, tmp_path, body)


def test_a_rename_after_the_image_still_posts_the_new_name(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        old = subs[1].name

        async def rename(call):
            await env.rename(subs[1], "Fixture renamed late")
        rig = app_rig(env, hooks=[(lambda c: is_json(c, "pack") and c.n == 2, rename)])
        await run_pack(rig, own)
        assert byte_call(rig).status == 200 and not logged(rig, "manifest assertion")
        text_ = one_post_without_image(rig)
        assert "Fixture renamed late" in text_ and old not in text_
    e2e(monkeypatch, tmp_path, body)


def test_c14p_no_rename_still_attaches_the_image_and_posts_the_same_names(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        rig = app_rig(env)
        await run_pack(rig, own)
        att = one_post_with_image(rig)
        assert all(s.name in att.content for s in subs)
    e2e(monkeypatch, tmp_path, body)


_UNMOVED_14Q = ("tile", "reason", "face_rev", "subject_name", "rarity", "foil", "signed", "gone", "slot",
                "print_id", "subject_player_id")


def test_a_discard_between_the_revalidation_and_the_reread_drops_the_image(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        prints = await env.pack_prints(pack)
        target = prints[2]["print_id"]

        async def discard(call):
            await env.discard(own, target)
        rig = app_rig(env, hooks=[(lambda c: is_json(c, "pack") and c.n == 2, discard)])
        await run_pack(rig, own)
        assert [c.status for c in checks(rig)] == [200] * 5, "step 5 did not pass"
        first, again = [body_of(c)["packs"][0]["prints"] for c in json_calls(rig, "pack")]
        for m in _UNMOVED_14Q:
            assert first[2].get(m) == again[2].get(m), (m, first[2].get(m), again[2].get(m))
        assert not first[2].get("discarded") and again[2].get("discarded") is True
        text_ = one_post_without_image(rig)
        line3 = [ln for ln in text_.split(chr(10)) if ln.startswith("3. ")]
        assert len(line3) == 1 and line3[0].endswith("(discarded)"), line3
    e2e(monkeypatch, tmp_path, body)


def test_c14q_with_no_discard_the_same_run_still_attaches(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        rig = app_rig(env)
        await run_pack(rig, own)
        one_post_with_image(rig)
    e2e(monkeypatch, tmp_path, body)


def test_c14q_a_discard_in_a_different_pack_still_attaches_this_one(monkeypatch, tmp_path):
    async def body(env):
        subs = await H.pool(env, 5)
        own = await env.player("owner", rating=None)
        await env.snapshot()
        other_pack = await env.open_pack(own, subs)
        pack = await env.open_pack(own, subs)
        elsewhere = (await env.pack_prints(other_pack))[2]["print_id"]

        async def discard(call):
            await env.discard(own, elsewhere)
        rig = app_rig(env, hooks=[(lambda c: is_json(c, "pack") and c.n == 2, discard)])
        await run_pack(rig, own)
        assert body_of(json_calls(rig, "pack")[0])["packs"][0]["pack_id"] == pack
        one_post_with_image(rig)
        found = await env.rows(f"SELECT discarded_at FROM {SCHEMA}.pc_prints WHERE id = CAST(:p AS uuid)",
                               {"p": elsewhere})
        assert found[0]["discarded_at"] is not None, "the other pack's discard did not land"
    e2e(monkeypatch, tmp_path, body)


# -- 15: every lease released on every exit path -------------------------------------------

def _released_all(rig):
    taken = sorted(body_of(c)["lease_id"] for c in rig.acquires() if c.status == 200)
    freed = sorted(c.path.rsplit("/", 1)[1] for c in rig.releases())
    assert taken, "no lease was taken"
    assert freed == taken, (taken, freed)


def test_leases_are_released_on_every_exit_path(monkeypatch, tmp_path):
    """Four exits that are not a posted picture, each after leases were
    taken: a lease gone at step 5, a manifest disagreement at step 4, a view
    that moved at step 6, and a send that raised. One DELETE per acquire in
    each."""
    async def body(env):
        subs = await H.pool(env, 5)
        await env.snapshot()
        owners = []
        for i in range(4):
            o = await env.player(f"owner{i}", rating=None)
            await env.open_pack(o, subs)
            owners.append(o)
        other = await env.player("other", rating=None, discord=False)

        rig = app_rig(env, hooks=[(lambda c: is_check(c), lambda c: env.ex(
            f"DELETE FROM {SCHEMA}.pc_delivery_leases WHERE id = CAST(:l AS uuid)",
            {"l": c.path.rsplit("/", 1)[1]}))])
        await run_pack(rig, owners[0])
        assert rig.attachments() == []
        _released_all(rig)

        async def rename(call):
            await env.rename(subs[0], "Fixture moved s1")
        rig = app_rig(env, hooks=[(is_bytes, rename)])
        await run_pack(rig, owners[1])
        assert logged(rig, "manifest assertion") and rig.attachments() == []
        _released_all(rig)

        async def move(call):
            await env.rebind(owners[2].discord, other)
        rig = app_rig(env, hooks=[(lambda c: is_json(c, "pack") and c.n == 2, move)])
        await run_pack(rig, owners[2])
        assert rig.texts() == [PACK_GONE_LINE]
        _released_all(rig)

        rig = app_rig(env)
        ctx = rig.ctx(owners[3].discord)
        plain = ctx.send

        async def raising(content=None, **kw):
            if kw.get("file") is not None:
                raise RuntimeError("the gateway dropped the connection")
            await plain(content, **kw)
        ctx.send = raising
        await rig.pack(ctx, 1, False)
        assert logged(rig, "pack failed: RuntimeError"), rig.logs
        _released_all(rig)
    e2e(monkeypatch, tmp_path, body)


def test_c15_the_success_path_still_releases(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        rig = app_rig(env)
        await run_pack(rig, own)
        one_post_with_image(rig)
        _released_all(rig)
    e2e(monkeypatch, tmp_path, body)


# -- stubbed rows: answers in the routes' shapes, on the rig's clock ---------------------

SYNTH_UID = 900000000000424242
BUSY_BODY = {"detail": {"error": "composite_busy", "retry_after": 5}}


def synth_png(pad=0):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (40, 60, 80)).save(buf, format="PNG")
    return buf.getvalue() + bytes(pad)


def ref_of(i):
    """The i-th subject ref (1-based) in ascending canonical order."""
    return str(uuid.UUID(int=i))


def synth_entries(n, kind, tiles=None):
    out = []
    for i in range(1, n + 1):
        tile = tiles[i - 1] if tiles else "face"
        e = {"print_id": str(uuid.uuid4()), "subject_player_id": ref_of(i), "subject_name": f"Card {i}",
             "edition_id": 1, "rarity": "common", "foil": False, "signed": False, "pool_rank": i,
             "tile": tile, "reason": None if tile == "face" else "no_steam_id",
             "face_rev": format(i, "040x") if tile == "face" else None}
        if kind == "pack":
            e.update({"slot": i, "gone": False, "discarded": False, "dup_at_pull": 0})
        out.append(e)
    return out


def busy(delay=0.0):
    """The composite gate's refusal as FastAPI writes it: a nested detail and
    the Retry-After header."""
    return H.Reply(503, json=BUSY_BODY, headers={"Retry-After": "5"}, delay=delay)


class Synth:
    """A stubbed reveal: step 1 and the re-read answer the same list, the
    picture route a PNG whose manifest matches it, the lease routes 200 at
    once - each overridable per request by its ordinal."""

    def __init__(self, kind="pack", n=None, tiles=None):
        self.kind = kind
        self.n = n or (5 if kind == "pack" else 10)
        self.actor = str(uuid.uuid4())
        self.pack_id = str(uuid.uuid4())
        self.entries = synth_entries(self.n, kind, tiles)
        self.png = synth_png()
        self.on_bytes = None      # fn(k, call) -> Reply | None; k is the byte GET's ordinal
        self.on_acquire = None    # fn(k, ref) -> Reply | None; k is the acquire's ordinal
        self.on_check = None      # fn(call) -> Reply | None
        self.k_bytes = 0
        self.k_acquire = 0

    def answer(self):
        prints = [dict(e) for e in self.entries]
        if self.kind == "pack":
            return {"packs": [{"pack_id": self.pack_id, "source": "daily", "opened_at": "2026-09-20T00:00:00+00:00",
                               "prints": prints}], "actor_ref": self.actor, "locale": "en", "total": 1}
        return {"owner_ref": self.actor, "owner_name": "Fixture owner", "settings_rev": 0, "page": 1, "pages": 1,
                "count": self.n, "by_rarity": {"common": self.n}, "prints": prints, "locale": "en"}

    def headers(self):
        def word(e):
            return e["face_rev"] if e["tile"] == "face" else e["reason"]
        if self.kind == "pack":
            slots = ",".join(f"{e['slot']}:{hex32(e['print_id'])}:{hex32(e['subject_player_id'])}:{e['tile']}:"
                             f"{word(e)}:live" for e in self.entries)
            return {"content-type": "image/png", "x-strip-slots": slots, "x-strip-actor": self.actor}
        slots = ",".join(f"{i}:{hex32(e['print_id'])}:{hex32(e['subject_player_id'])}:{e['tile']}:{word(e)}"
                         for i, e in enumerate(self.entries, start=1))
        return {"content-type": "image/png", "x-grid-slots": slots, "x-grid-owner": self.actor,
                "x-grid-consent-rev": "0"}

    def picture(self, delay=0.0, body=None):
        return H.Reply(200, self.png if body is None else body, self.headers(), delay=delay)

    @staticmethod
    def lease(delay=0.0):
        until = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
        return H.Reply(200, json={"lease_id": str(uuid.uuid4()), "until": until, "portrait_kind": None,
                                  "portrait_hash": None}, delay=delay)

    async def __call__(self, call):
        if call.method == "GET" and call.path in (PACKS, BINDER):
            if self.kind == "pack" and not ({"pack_id", "index"} & set(call.params)):
                return H.Reply(200, json={"packs": [{"pack_id": self.pack_id, "status": "done"}], "total": 1,
                                          "next_before": None, "actor_ref": self.actor})
            return H.Reply(200, json=self.answer())
        if is_bytes(call):
            self.k_bytes += 1
            got = self.on_bytes(self.k_bytes, call) if self.on_bytes else None
            return got if got is not None else self.picture()
        if is_acquire(call):
            self.k_acquire += 1
            ref = (call.payload or {}).get("subject_ref")
            got = self.on_acquire(self.k_acquire, ref) if self.on_acquire else None
            return got if got is not None else self.lease()
        if is_check(call):
            got = self.on_check(call) if self.on_check else None
            return got if got is not None else H.Reply(200, json={"live": True})
        if call.method == "DELETE" and call.path.startswith(LEASE + "/"):
            return H.Reply(200, json={"released": True})
        raise AssertionError(f"unexpected request {call.method} {call.path}")


async def synth_pack(rig, private=False, slash=False):
    await rig.pack(rig.ctx(SYNTH_UID, slash=slash), 1, private)


async def synth_binder(rig):
    await rig.binder(rig.ctx(SYNTH_UID), None, 1)


def phase_rig(synth, work=None):
    """A rig whose _pc_leases is observed (the clock at its entry and return,
    and its answer) and whose loop spends work[k] seconds of its own after
    the k-th acquire returns."""
    rig = make_rig(synth)
    real_lease, real_leases = rig.ns["_pc_lease"], rig.ns["_pc_leases"]
    seen = {}

    async def lease(*a, **k):
        out = await real_lease(*a, **k)
        rig.clock.advance((work or {}).get(len(rig.acquires()), 0.0))
        return out

    async def leases(refs):
        seen["t0"] = rig.clock.now
        out = await real_leases(refs)
        seen["t1"] = rig.clock.now
        seen["out"] = out
        return out
    rig.ns["_pc_lease"] = lease
    rig.ns["_pc_leases"] = leases
    return rig, seen


def acquire_phase(rig, seen):
    """From the first acquire request to _pc_leases' return."""
    first = rig.acquires()[0].t_start if rig.acquires() else seen["t1"]
    return seen["t1"] - first


def byte_phase(rig):
    got = rig.byte_gets()
    return got[-1].t_end - got[0].t_start


# -- 14b: the leased set is exactly the distinct face subjects ---------------------------

def test_the_leased_set_is_exactly_the_distinct_face_subjects():
    """Ten face entries over nine subjects, S at positions 3 and 7; every
    acquire answers 200 at once and nothing changes between the reads."""
    synth = Synth("binder", n=10)
    synth.entries[6]["subject_player_id"] = synth.entries[2]["subject_player_id"]
    rig, seen = phase_rig(synth)
    H.run(synth_binder(rig))
    faces = {e["subject_player_id"] for e in synth.entries if e["tile"] == "face"}
    assert len(faces) == 9
    leased = seen["out"][0]
    assert leased is not None and set(leased) == faces, sorted(leased or {})
    assert len(rig.acquires()) == 9, len(rig.acquires())
    one_post_with_image(rig)


def test_c14b_nine_distinct_subjects_take_nine_leases_and_attach():
    synth = Synth("binder", n=10)
    synth.entries[6]["subject_player_id"] = synth.entries[2]["subject_player_id"]
    rig, seen = phase_rig(synth)
    H.run(synth_binder(rig))
    one_post_with_image(rig)
    assert len(rig.acquires()) == 9


# -- 17b: one composite cap -------------------------------------------------------------

def _top(tree, name):
    found = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert len(found) == 1, (name, len(found))
    return found[0]


def _const(tree, name):
    found = [n for n in tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
    assert len(found) == 1, (name, len(found))
    return eval(compile(ast.Expression(found[0].value), name, "eval"), {})


def _names_in(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def test_the_composite_cap_is_one_number_on_both_sides():
    body = synth_png(pad=5 * 1024 * 1024)
    synth = Synth("pack")
    synth.on_bytes = lambda k, call: synth.picture(body=body)
    rig = make_rig(synth)
    data, meta, note = H.run(rig.ns["_pc_reveal_bytes"](f"/internal/pc/packs/{synth.pack_id}/strip/en.png",
                                                        {"discord_id": str(SYNTH_UID)}))
    assert note is None and data == body, f"the 5 MiB composite was refused (note {note})"
    bot = ast.parse(H.bot_source())
    api = ast.parse((H.BACKEND / "api" / "main.py").read_text(encoding="utf-8"))
    assert _const(bot, "_PC_COMPOSITE_MAX_BYTES") == _const(api, "_PC_COMPOSITE_MAX_BYTES") == 8 * 1024 * 1024
    fuse = [n for n in ast.walk(_top(api, "_pc_composite_bytes"))
            if isinstance(n, ast.Compare) and "_PC_COMPOSITE_MAX_BYTES" in _names_in(n)]
    assert len(fuse) == 1, "the server fuse does not compare against _PC_COMPOSITE_MAX_BYTES"
    calls = [n for n in ast.walk(_top(bot, "_pc_reveal_bytes"))
             if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_pc_api_bytes"]
    assert len(calls) == 1
    kw = {k.arg: k.value for k in calls[0].keywords}
    assert isinstance(kw.get("max_bytes"), ast.Name) and kw["max_bytes"].id == "_PC_COMPOSITE_MAX_BYTES"


def test_c17b_a_3_mib_face_through_a_default_cap_caller_still_passes():
    body = synth_png(pad=3 * 1024 * 1024)

    async def handler(call):
        return H.Reply(200, body, {"content-type": "image/png"})
    rig = make_rig(handler)
    st, data, meta = H.run(rig.ns["_pc_api_bytes"]("/internal/pc/face/print/x/en"))
    assert (st, data) == (200, body)


# -- 21: a prefix /pack cannot be private -------------------------------------------------

def test_prefix_pack_with_private_true_sends_one_line_and_nothing_else():
    synth = Synth("pack")
    rig = make_rig(synth)
    H.run(synth_pack(rig, private=True, slash=False))
    assert rig.calls == [], [c.path for c in rig.calls]
    assert len(rig.sent) == 1 and rig.attachments() == []
    assert "slash form" in rig.texts()[0], rig.texts()


def test_c21_a_slash_private_pack_still_delivers_the_image_ephemerally():
    synth = Synth("pack")
    rig = make_rig(synth)
    H.run(synth_pack(rig, private=True, slash=True))
    att = one_post_with_image(rig)
    assert att.ephemeral is True
    assert rig.defers == [{"ephemeral": True}], rig.defers


# -- 22: a composite lease names a subject, never a print ----------------------------------

def test_composite_leases_name_a_subject_and_never_a_print(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        rig = app_rig(env)
        await run_pack(rig, own)
        payloads = [c.payload for c in rig.acquires()]
        assert all(set(p) == {"subject_ref"} for p in payloads), payloads
        assert sorted(p["subject_ref"] for p in payloads) == sorted(s.id for s in subs)
        one_post_with_image(rig)
    e2e(monkeypatch, tmp_path, body)


def test_c22_a_discarded_print_in_the_pack_still_draws(monkeypatch, tmp_path):
    """Row 13's fact through the bot's own step 1: the strip the bot fetches
    draws the discarded print as a stamped face. Read at the byte call, which
    precedes every acquire, so it holds whatever an acquire sends."""
    async def body(env):
        own, subs, pack = await pack_of(env)
        prints = await env.pack_prints(pack)
        await env.discard(own, prints[1]["print_id"])
        rig = app_rig(env)
        await run_pack(rig, own)
        call = byte_call(rig)
        assert call.status == 200, call.status
        assert H.image_of(call.reply.body).size == (1947, 549)
        man = manifest(call)
        assert (man[1][3], man[1][5]) == ("face", "discarded"), man
    e2e(monkeypatch, tmp_path, body)


def test_c22_the_discarded_prints_subject_is_leased_and_the_image_attached(monkeypatch, tmp_path):
    """Stated over the UNMUTATED tree (build notes, FINDING 7): the outcome row
    22's property exists for - a subject-keyed lease admits the discarded
    print's subject, so the picture posts."""
    async def body(env):
        own, subs, pack = await pack_of(env)
        prints = await env.pack_prints(pack)
        await env.discard(own, prints[1]["print_id"])
        rig = app_rig(env)
        await run_pack(rig, own)
        one_post_with_image(rig)
        assert subs[1].id in acquired_subjects(rig)
    e2e(monkeypatch, tmp_path, body)


# -- 23, 23b, 23c: which refusals are retried ------------------------------------------------

def test_bot_falls_back_to_text_on_404_without_retrying():
    synth = Synth("pack")
    synth.on_bytes = lambda k, call: H.Reply(404, json={"detail": "Not found"})
    rig = make_rig(synth)
    H.run(synth_pack(rig))
    assert len(rig.byte_gets()) == 1, len(rig.byte_gets())
    assert rig.sleeps == [], rig.sleeps
    text_ = one_post_without_image(rig)
    assert text_.startswith("**Pack 1**"), text_[:120]


def test_c23_a_200_still_posts_the_image():
    synth = Synth("pack")
    rig = make_rig(synth)
    H.run(synth_pack(rig))
    one_post_with_image(rig)
    assert len(rig.byte_gets()) == 1


async def release_blob(env, h):
    """A released portrait blob: the players row still names it (the
    server module's fixture, test_discord_collection_server.py)."""
    async with env.seed.begin() as c:
        await c.execute(text("SET LOCAL session_replication_role = replica"))
        await c.execute(text(f"DELETE FROM {SCHEMA}.pc_portraits WHERE hash = :h"), {"h": h})


async def restore_blob(env, seed):
    """The same blob stored again, the players row untouched."""
    canonical, info = env.main._pcf.prepare_portrait(H._portrait_png(seed, noisy=False, radius=330))
    await env.ex(f"INSERT INTO {SCHEMA}.pc_portraits (hash, bytes, content_type, width, height)"
                 " VALUES (:h, :b, 'image/png', :w, :hh) ON CONFLICT (hash) DO NOTHING",
                 {"h": info["sha256"], "b": canonical, "w": int(info["width"]), "hh": int(info["height"])})
    return info["sha256"]


def test_a_portrait_pending_503_is_retried_once_and_the_image_is_attached(monkeypatch, tmp_path):
    """The first strip GET meets a released blob, so the real route raises
    _PcPortraitMissing and FastAPI writes its body; the blob is stored again
    before the second GET."""
    async def body(env):
        subs = await H.pool(env, 5)
        h = await env.give_portrait(subs[3], 31)
        own, subs, pack = await pack_of(env, subjects=subs)
        await release_blob(env, h)

        async def restore(call):
            assert await restore_blob(env, 31) == h
        rig = app_rig(env, hooks=[(lambda c: is_bytes(c) and c.n == 2, restore)])
        await run_pack(rig, own)
        one_post_with_image(rig)
        got = rig.byte_gets()
        assert len(got) == 2, [c.status for c in got]
        assert got[0].status == 503, got[0].status
        assert body_of(got[0]) == {"detail": {"error": "portrait_pending", "retry_after": 2}}, body_of(got[0])
        assert got[0].reply.headers.get("retry-after") == "2"
        assert rig.sleeps == [2.0], rig.sleeps
    e2e(monkeypatch, tmp_path, body)


def test_c23b_a_first_try_200_posts_without_a_second_get(monkeypatch, tmp_path):
    async def body(env):
        subs = await H.pool(env, 5)
        await env.give_portrait(subs[3], 31)
        own, subs, pack = await pack_of(env, subjects=subs)
        rig = app_rig(env)
        await run_pack(rig, own)
        one_post_with_image(rig)
        assert len(rig.byte_gets()) == 1 and rig.sleeps == []
    e2e(monkeypatch, tmp_path, body)


def test_c23b_a_flat_portrait_pending_body_is_also_retried(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        state = {"n": 0}

        async def stub(call):
            if is_bytes(call):
                state["n"] += 1
                if state["n"] == 1:
                    return H.Reply(503, json={"error": "portrait_pending", "retry_after": 2})
            return None
        rig = app_rig(env, stub=stub)
        await run_pack(rig, own)
        one_post_with_image(rig)
        assert len(rig.byte_gets()) == 2 and rig.sleeps == [2.0], (len(rig.byte_gets()), rig.sleeps)
    e2e(monkeypatch, tmp_path, body)


def _gate(env, closed):
    return env.main._PcCompositeGate(0, 0) if closed else env.main._PcCompositeGate(
        env.main._PC_COMPOSITE_SLOTS, env.main._PC_COMPOSITE_QUEUE_DEPTH)


def test_composite_busy_is_retried_at_most_twice_then_falls_back(monkeypatch, tmp_path):
    """A (0, 0) gate refuses every cold composite with the route's own
    composite_busy raise. The hook that opens the gate at the SIXTH GET only
    ends the mutated run (an uncapped retry); the capped bot stops at three."""
    async def body(env):
        own, subs, pack = await pack_of(env)
        env.mp.setattr(env.main, "_pc_composite_gate", _gate(env, True))

        async def reopen(call):
            env.mp.setattr(env.main, "_pc_composite_gate", _gate(env, False))
        rig = app_rig(env, hooks=[(lambda c: is_bytes(c) and c.n == 6, reopen)])
        await run_pack(rig, own)
        got = rig.byte_gets()
        assert len(got) == 3, f"{len(got)} byte GETs"
        assert all(c.status == 503 and body_of(c) == BUSY_BODY for c in got), [(c.status, body_of(c)) for c in got]
        assert rig.sleeps == [5.0, 5.0], rig.sleeps
        text_ = one_post_without_image(rig)
        assert text_.startswith("**Pack 1**"), text_[:120]
    e2e(monkeypatch, tmp_path, body)


def test_c23c_two_busy_answers_then_a_200_still_attach(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        env.mp.setattr(env.main, "_pc_composite_gate", _gate(env, True))

        async def reopen(call):
            env.mp.setattr(env.main, "_pc_composite_gate", _gate(env, False))
        rig = app_rig(env, hooks=[(lambda c: is_bytes(c) and c.n == 3, reopen)])
        await run_pack(rig, own)
        one_post_with_image(rig)
        assert [c.status for c in rig.byte_gets()] == [503, 503, 200]
        assert rig.sleeps == [5.0, 5.0]
    e2e(monkeypatch, tmp_path, body)


def test_c23c_a_retry_after_header_without_a_json_code_is_not_retried(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)

        async def stub(call):
            if is_bytes(call):
                return H.Reply(503, b"busy", {"Retry-After": "5", "content-type": "text/plain"})
            return None
        rig = app_rig(env, stub=stub)
        await run_pack(rig, own)
        assert len(rig.byte_gets()) == 1 and rig.sleeps == [], (len(rig.byte_gets()), rig.sleeps)
        one_post_without_image(rig)
    e2e(monkeypatch, tmp_path, body)


# -- 23d-23j: the budgets ------------------------------------------------------------------

def test_the_acquire_to_send_span_fits_the_lease(monkeypatch, tmp_path):
    """A cold ten-tile grid whose byte phase runs ~63 s: a 503 composite_busy
    after 30 s, the 5 s wait, then the real route's 200 arriving after 28 s."""
    async def body(env):
        subs = await H.pool(env, 10)
        own = await env.player("owner", rating=None)
        await env.snapshot()
        await env.open_pack(own, subs[:5])
        await env.open_pack(own, subs[5:])
        base = H.asgi_handler(env)
        state = {"n": 0}

        async def stub(call):
            if not is_bytes(call):
                return None
            state["n"] += 1
            if state["n"] == 1:
                return busy(delay=30.0)
            reply = await base(call)
            reply.delay = 28.0
            return reply
        rig = app_rig(env, stub=stub)
        ctx = rig.ctx(own.discord)
        plain, sent_at = ctx.send, []

        async def timed(content=None, **kw):
            sent_at.append(rig.clock.now)
            await plain(content, **kw)
        ctx.send = timed
        await rig.binder(ctx, None, 1)
        phase = byte_phase(rig)
        span = (sent_at[0] - rig.acquires()[0].t_start) if (sent_at and rig.acquires()) else None
        print(f"ROW23D byte phase {phase} s; acquire-to-send span {span} s")
        one_post_with_image(rig)
        assert phase >= 63.0, phase
        assert span is not None and span < 57.0, span
        assert len(rig.acquires()) == 10
    e2e(monkeypatch, tmp_path, body)


def test_the_acquire_phase_is_bounded_by_its_deadline():
    synth = Synth("binder", n=10)

    def acquire(k, ref):
        if ref == ref_of(10):
            return H.Reply(200, json={}, delay=1e9)        # never answers: the handed timeout cuts it short
        if ref == ref_of(5):
            return H.Reply(404, json={"detail": {"error": "subject_gone"}}, delay=1.875)
        return Synth.lease(delay=1.875)
    synth.on_acquire = acquire
    rig, seen = phase_rig(synth, work={k: 0.25 for k in range(1, 10)})
    H.run(synth_binder(rig))
    phase = acquire_phase(rig, seen)
    print(f"ROW23E measured acquire phase {phase} s over {len(rig.acquires())} requests")
    leased, undeliverable, past_deadline = seen["out"]
    assert len(rig.acquires()) == 10, len(rig.acquires())
    assert phase <= 20.0, f"the acquire phase ran {phase} s"
    assert leased is None, "the call did not fail"
    assert undeliverable == {ref_of(5)} and past_deadline == set(), (undeliverable, past_deadline)
    assert len(rig.releases()) == 8, len(rig.releases())
    text_ = one_post_without_image(rig)
    assert text_.startswith("**Fixture owner**"), text_[:120]


def test_c23e_ten_quick_acquires_measure_two_and_a_half_seconds_and_attach():
    synth = Synth("binder", n=10)
    synth.on_acquire = lambda k, ref: Synth.lease(delay=0.25)
    rig, seen = phase_rig(synth)
    H.run(synth_binder(rig))
    phase = acquire_phase(rig, seen)
    print(f"ROW23E control phase {phase} s")
    assert len(rig.acquires()) == 10 and phase == 2.5, (len(rig.acquires()), phase)
    one_post_with_image(rig)


def test_the_composite_byte_timeout_outlives_the_server_ceiling():
    synth = Synth("pack")
    synth.on_bytes = lambda k, call: synth.picture(delay=25.0)
    rig = make_rig(synth)
    H.run(synth_pack(rig))
    one_post_with_image(rig)
    assert [c.status for c in rig.byte_gets()] == [200]


def test_c23f_a_warm_composite_at_a_third_of_a_second_still_attaches():
    synth = Synth("pack")
    synth.on_bytes = lambda k, call: synth.picture(delay=0.3)
    rig = make_rig(synth)
    H.run(synth_pack(rig))
    one_post_with_image(rig)


def test_the_byte_phase_is_bounded_by_its_attempt_count():
    synth = Synth("pack")
    synth.on_bytes = lambda k, call: busy(delay=30.0)
    rig = make_rig(synth)
    H.run(synth_pack(rig))
    phase = byte_phase(rig)
    print(f"ROW23G {len(rig.byte_gets())} byte GETs over {phase} s, waits {rig.sleeps}")
    assert len(rig.byte_gets()) == 3, len(rig.byte_gets())
    assert phase <= 115.0, phase
    text_ = one_post_without_image(rig)
    assert text_.startswith("**Pack 1**"), text_[:120]


def test_c23g_two_slow_busy_answers_then_a_200_still_attach():
    synth = Synth("pack")
    synth.on_bytes = lambda k, call: busy(delay=30.0) if k <= 2 else synth.picture()
    rig = make_rig(synth)
    H.run(synth_pack(rig))
    one_post_with_image(rig)
    assert len(rig.byte_gets()) == 3 and byte_phase(rig) == 70.0, byte_phase(rig)


def test_the_acquire_phase_count_term_is_enforced_by_the_refusal():
    """25 face subjects on one page (the stubbed JSON stands for a page whose
    LIMIT is 25): the 24 that sort first answer 200 at 0.25 s, the last 404."""
    synth = Synth("binder", n=25)
    synth.on_acquire = lambda k, ref: (H.Reply(404, json={"detail": {"error": "subject_gone"}}, delay=0.25)
                                       if ref == ref_of(25) else Synth.lease(delay=0.25))
    rig, seen = phase_rig(synth)
    H.run(synth_binder(rig))
    phase = acquire_phase(rig, seen)
    print(f"ROW23I measured acquire phase {phase} s over {len(rig.acquires())} requests")
    assert len(rig.acquires()) <= 10, f"{len(rig.acquires())} acquire requests reached the stub"
    assert logged(rig, "leases refused: 25 subjects, at most 10"), rig.logs
    assert rig.releases() == []
    one_post_without_image(rig)


def test_c23i_ten_refs_are_accepted_and_all_ten_are_asked():
    synth = Synth("binder", n=10)
    synth.on_acquire = lambda k, ref: (H.Reply(404, json={"detail": {"error": "subject_gone"}}, delay=0.25)
                                       if ref == ref_of(10) else Synth.lease(delay=0.25))
    rig, seen = phase_rig(synth)
    H.run(synth_binder(rig))
    assert len(rig.acquires()) == 10, len(rig.acquires())
    assert seen["out"][1] == {ref_of(10)}
    assert len(rig.releases()) == 9
    one_post_without_image(rig)


def test_a_ref_past_the_deadline_is_never_issued():
    synth = Synth("binder", n=10)
    synth.on_acquire = lambda k, ref: (
        H.Reply(409, json={"detail": {"error": "subject_busy", "retry_after": 2}})
        if ref == ref_of(10) else Synth.lease(delay=1.875))
    rig, seen = phase_rig(synth, work={k: 0.5 for k in range(1, 9)})
    H.run(synth_binder(rig))
    leased, undeliverable, past_deadline = seen["out"]
    print(f"ROW23J {len(rig.acquires())} requests, phase {acquire_phase(rig, seen)} s")
    assert len(rig.acquires()) == 9, len(rig.acquires())
    assert past_deadline == {ref_of(10)}, past_deadline
    assert undeliverable == set() and leased is None
    assert len(rig.releases()) == 8, len(rig.releases())
    one_post_without_image(rig)
    assert logged(rig, "past_deadline=1"), rig.logs


def test_c23j_ten_answers_inside_the_deadline_attach():
    synth = Synth("binder", n=10)
    synth.on_acquire = lambda k, ref: Synth.lease(delay=1.875)
    rig, seen = phase_rig(synth)
    H.run(synth_binder(rig))
    assert len(rig.acquires()) == 10 and acquire_phase(rig, seen) == 18.75, acquire_phase(rig, seen)
    assert seen["out"][2] == set()
    one_post_with_image(rig)


# -- 23h, 24: the shipped face callers ------------------------------------------------------

SHIPPED_FUNCS = H.REVEAL_FUNCS | {"_pc_back_bytes", "_pc_best_face", "_pc_send_face", "cmd_pc_collection",
                                  "cmd_pc_card", "poll_pc_events", "_pc_event_lines"}
SHIPPED_ASSIGNS = H.REVEAL_ASSIGNS | {"_pc_back_bytes_cache", "_pc_events_sent", "_pc_face_tries",
                                      "_PC_FACE_TRIES", "_PC_RARITY_COLOR"}
EVENTS_CHANNEL = 4242


class FakeEmbed:
    def __init__(self, title=None, color=None, **kw):
        self.title, self.color, self.fields, self.image, self.footer = title, color, [], None, None

    def add_field(self, name=None, value=None, inline=True):
        self.fields.append((name, value, inline))
        return self

    def set_image(self, url=None):
        self.image = url
        return self

    def set_footer(self, text=None, **kw):
        self.footer = text
        return self


class Shipped:
    """The routes the three shipped face callers read, in their shapes: the
    binder summary, the card, the pending events and their ack, the three
    face routes (each a different body), and the lease routes."""

    def __init__(self, acquire_delay=0.0, check_delay=0.0):
        self.subject, self.print_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.back, self.face, self.preview = (synth_png() + b"back", synth_png() + b"face",
                                              synth_png() + b"preview")
        self.acquire_delay, self.check_delay = acquire_delay, check_delay

    def entry(self):
        return {"print_id": self.print_id, "subject_player_id": self.subject, "subject_name": "Fixture subject",
                "rarity": "legendary", "foil": False, "signed": False, "pool_rank": 1}

    async def __call__(self, call):
        p, m = call.path, call.method
        if m == "GET" and p == "/internal/pc/collection":
            return H.Reply(200, json={"owner_name": "Fixture owner", "count": 1, "distinct_subjects": 1,
                                      "by_rarity": {"legendary": 1}, "best": [self.entry()]})
        if m == "GET" and p == "/internal/pc/card":
            return H.Reply(200, json={"rarity": "legendary", "subject_name": "Fixture subject", "rating": 1500,
                                      "pool_rank": 1, "peak_rating": 1500, "series_wins": 1, "series_losses": 0,
                                      "board_rank": 1, "player_ref": self.subject, "snapshot_id": 1,
                                      "in_circulation": {"prints": 1, "holders": 1, "foil": 0, "signed": 0}})
        if m == "GET" and p == "/internal/pc/events/pending":
            return H.Reply(200, json={"events": [{
                "id": 7, "kind": "legendary", "puller_name": "Fixture puller", "subject_name": "Fixture subject",
                "subject_ref": self.subject, "face_ready": True,
                "print": {"print_id": self.print_id, "rarity": "legendary", "pool_rank": 1}}]})
        if m == "POST" and p == "/internal/pc/events/ack":
            return H.Reply(200, json={"acked": 1})
        if m == "GET" and p == "/internal/pc/face/back":
            return H.Reply(200, self.back, {"content-type": "image/png"})
        if m == "GET" and p.startswith("/internal/pc/face/print/"):
            return H.Reply(200, self.face, {"content-type": "image/png"})
        if m == "GET" and p.startswith("/internal/pc/face/preview/"):
            return H.Reply(200, self.preview, {"content-type": "image/png"})
        if is_acquire(call):
            return Synth.lease(delay=self.acquire_delay)
        if is_check(call):
            return H.Reply(200, json={"live": True}, delay=self.check_delay)
        if m == "DELETE" and p.startswith(LEASE + "/"):
            return H.Reply(200, json={"released": True})
        raise AssertionError(f"unexpected request {m} {p}")


def shipped_rig(handler):
    holder = {}

    async def channel_send(content=None, **kw):
        holder["rig"].sent.append(H.Sent(content=content, file=kw.get("file"), ephemeral=False,
                                         kw={k: v for k, v in kw.items() if k != "file"}))
    channel = SimpleNamespace(id=EVENTS_CHANNEL, send=channel_send)
    fake_discord = SimpleNamespace(
        Member=SimpleNamespace, File=H._File, HTTPException=H._HTTPException, Forbidden=H._HTTPException,
        NotFound=type("NotFound", (Exception,), {}), Embed=FakeEmbed, Color=SimpleNamespace(gold=lambda: 0xF1C40F),
        AllowedMentions=SimpleNamespace(none=lambda: "none"),
        utils=SimpleNamespace(escape_markdown=lambda s, **k: str(s)))
    extra = {"discord": fake_discord, "PC_EVENTS_CHANNEL_ID": EVENTS_CHANNEL,
             "bot": SimpleNamespace(get_channel=lambda cid: channel if cid == EVENTS_CHANNEL else None),
             "get_rank_name": lambda rating: "Fixture rank", "rank_emoji": lambda name: ""}
    rig = make_rig(handler, funcs=SHIPPED_FUNCS, assigns=SHIPPED_ASSIGNS, extra=extra)
    holder["rig"] = rig
    return rig


def _posted(rig, fn):
    """Run one caller and return what it posted."""
    n = len(rig.sent)
    H.run(fn())
    return rig.sent[n:]


def test_the_shipped_lease_callers_keep_their_own_timeouts():
    """Acquires answer at 4 s and lease checks at 3.5 s; the three shipped
    callers pass no timeout, so each keeps the request it always made
    (_pc_api's 8 s, _pc_lease_live's 4 s) and each posts WITH its picture."""
    ship = Shipped(acquire_delay=4.0, check_delay=3.5)
    rig = shipped_rig(ship)
    ctx = rig.ctx(SYNTH_UID)
    card = _posted(rig, lambda: rig.ns["cmd_pc_card"](ctx))
    coll = _posted(rig, lambda: rig.ns["cmd_pc_collection"](ctx))
    drain = _posted(rig, lambda: rig.ns["poll_pc_events"]())
    assert len(card) == 1 and card[0].file is not None and card[0].file.data == ship.preview, (
        [(s.content, s.file) for s in card])
    assert len(coll) == 1 and coll[0].file is not None and coll[0].file.data == ship.face, (
        [(s.content, s.file) for s in coll])
    assert len(drain) == 1 and drain[0].file is not None and drain[0].file.data == ship.face, (
        [(s.content, s.file) for s in drain])
    assert [c.status for c in rig.acquires()] == [200, 200, 200]
    assert all(c.status == 200 and c.t_end - c.t_start == 3.5 for c in checks(rig)) and len(checks(rig)) == 3


def test_c23h_the_new_path_still_abandons_each_acquire_at_2_s():
    ship = Shipped(acquire_delay=4.0, check_delay=3.5)
    rig = shipped_rig(ship)
    leased, undeliverable, past_deadline = H.run(rig.ns["_pc_leases"]({ship.subject}))
    got = rig.acquires()
    assert leased is None and len(got) == 1
    assert got[0].status == 0 and got[0].total == 2.0 and got[0].t_end - got[0].t_start == 2.0


def test_pc_api_bytes_returns_three_and_every_caller_unpacks_three():
    ship = Shipped()
    rig = shipped_rig(ship)
    got = H.run(rig.ns["_pc_api_bytes"]("/internal/pc/face/back"))
    assert isinstance(got, tuple) and len(got) == 3 and got[:2] == (200, ship.back)
    assert H.run(rig.ns["_pc_back_bytes"]()) == ship.back                                    # bot:8560
    face, lease = H.run(rig.ns["_pc_best_face"]({"best": [ship.entry()]}, "en"))             # bot:8623
    assert face == ship.face and lease[0]
    ctx = rig.ctx(SYNTH_UID)
    card = _posted(rig, lambda: rig.ns["cmd_pc_card"](ctx))                                   # bot:8890
    assert len(card) == 1 and card[0].file is not None and card[0].file.data == ship.preview
    drain = _posted(rig, lambda: rig.ns["poll_pc_events"]())                                  # bot:9507
    assert len(drain) == 1 and drain[0].file is not None and drain[0].file.data == ship.face


def test_c24_pc_api_bytes_still_answers_the_same_status_and_bytes():
    ship = Shipped()
    rig = shipped_rig(ship)
    st, data, meta = H.run(rig.ns["_pc_api_bytes"]("/internal/pc/face/print/x/en"))
    assert (st, data) == (200, ship.face)

    async def missing(call):
        return H.Reply(404, json={"detail": "Not found"})
    rig = make_rig(missing)
    st, data, meta = H.run(rig.ns["_pc_api_bytes"]("/internal/pc/face/print/x/en"))
    assert (st, data) == (404, None)


# -- 24b, 24c, 24d: the byte reader ------------------------------------------------------------

def _body_rig(reply):
    async def handler(call):
        return reply
    return make_rig(handler)


def test_pc_api_bytes_honours_max_bytes_per_call():
    body = synth_png(pad=6 * 1024 * 1024)
    rig = _body_rig(H.Reply(200, body, {"content-type": "image/png"}))
    fn = rig.ns["_pc_api_bytes"]
    st, data, meta = H.run(fn("/internal/pc/face/print/x/en"))
    assert (st, data) == (200, None), "a 6 MiB body passed the 4 MiB default"
    st, data, meta = H.run(fn("/internal/pc/packs/x/strip/en.png", max_bytes=rig.ns["_PC_COMPOSITE_MAX_BYTES"]))
    assert (st, data) == (200, body), "a 6 MiB body was refused at the composite cap"


def test_c24b_a_3_mib_face_still_passes_at_the_default():
    body = synth_png(pad=3 * 1024 * 1024)
    rig = _body_rig(H.Reply(200, body, {"content-type": "image/png"}))
    st, data, meta = H.run(rig.ns["_pc_api_bytes"]("/internal/pc/face/print/x/en"))
    assert (st, data) == (200, body)


def test_a_non_200_never_returns_bytes():
    reply = H.Reply(503, json={"detail": {"error": "composite_busy", "retry_after": 5, "pad": "x" * 1950}})
    assert 2000 <= len(reply.body) <= 4096, len(reply.body)
    rig = _body_rig(reply)
    st, data, meta = H.run(rig.ns["_pc_api_bytes"]("/internal/pc/packs/x/strip/en.png"))
    assert st == 503 and data is None, (st, type(data))
    assert meta.get("error") == "composite_busy" and meta.get("retry_after") == 5, meta


def test_c24c_a_200_returns_its_bytes_and_an_empty_503_carries_no_error():
    body = synth_png()
    rig = _body_rig(H.Reply(200, body, {"content-type": "image/png"}))
    assert H.run(rig.ns["_pc_api_bytes"]("/internal/pc/face/print/x/en"))[:2] == (200, body)
    rig = _body_rig(H.Reply(503, b"", {"content-type": "application/json"}))
    st, data, meta = H.run(rig.ns["_pc_api_bytes"]("/internal/pc/face/print/x/en"))
    assert st == 503 and data is None and "error" not in meta, meta


def _raising_route(make_exc):
    """A one-route app whose handler raises `make_exc()`, so the body is what
    FastAPI's default handler writes for it."""
    from fastapi import FastAPI
    app = FastAPI()

    @app.get("/api/v1/internal/pc/face/print/{pid}/{loc}")
    async def refuse(pid: str, loc: str):
        raise make_exc()

    async def handler(call):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mini.test") as c:
            r = await c.request(call.method, "/api/v1" + call.path, params=call.params or None)
        return H.Reply(r.status_code, r.content, dict(r.headers))
    return handler


def test_a_non_200_body_is_unwrapped_from_detail():
    import main
    rig = make_rig(_raising_route(main._PcPortraitMissing))
    st, data, meta = H.run(rig.ns["_pc_api_bytes"]("/internal/pc/face/print/x/en"))
    assert st == 503 and data is None
    assert meta.get("error") == "portrait_pending", meta
    assert meta.get("retry_after") == 2, meta


def test_c24d_a_flat_body_and_the_header_fallback_still_parse():
    rig = _body_rig(H.Reply(503, json={"error": "portrait_pending", "retry_after": 2}))
    st, data, meta = H.run(rig.ns["_pc_api_bytes"]("/internal/pc/face/print/x/en"))
    assert (meta.get("error"), meta.get("retry_after")) == ("portrait_pending", 2), meta
    rig = _body_rig(H.Reply(503, json={"detail": {"error": "composite_busy"}}, headers={"Retry-After": "4"}))
    st, data, meta = H.run(rig.ns["_pc_api_bytes"]("/internal/pc/face/print/x/en"))
    assert meta.get("retry_after") == 4, meta


# -- 24e: a composite timeout is retried -------------------------------------------------------

def spy_bytes(rig):
    """Every _pc_api_bytes answer the reveal saw, in order."""
    real, seen = rig.ns["_pc_api_bytes"], []

    async def spy(*a, **k):
        out = await real(*a, **k)
        seen.append(out)
        return out
    rig.ns["_pc_api_bytes"] = spy
    return seen


def test_a_composite_timeout_is_a_retryable_code(monkeypatch, tmp_path):
    """The route's own ceiling, shortened to 2 s, over a stub renderer that
    holds each tile render 0.3 s on the first attempt: the cold grid of ten
    runs past the ceiling, the route raises its composite_timeout refusal and
    FastAPI writes the body. The second attempt renders at full speed and
    finds the tiles the first one finished in the face cache."""
    async def body(env):
        subs = await H.pool(env, 10)
        own = await env.player("owner", rating=None)
        await env.snapshot()
        await env.open_pack(own, subs[:5])
        await env.open_pack(own, subs[5:])
        env.mp.setattr(env.main, "_PC_COMPOSITE_CEILING_S", 2.0)
        real, state = env.main._pc_render_face, {"slow": True, "warm": None}

        async def slow(db, row, ctx, size, *a, **k):
            if state["slow"] and size == "tile":
                await asyncio.sleep(0.3)
            return await real(db, row, ctx, size, *a, **k)
        env.mp.setattr(env.main, "_pc_render_face", slow)

        async def second(call):
            state["slow"] = False
            state["warm"] = len([k for k in env.cache_keys() if k.endswith("/tile.png")])
        rig = app_rig(env, hooks=[(lambda c: is_bytes(c) and c.n == 2, second)])
        seen = spy_bytes(rig)
        await run_binder(rig, own)
        print(f"ROW24E answers {[(s[0], s[2].get('error'), s[2].get('retry_after')) for s in seen]};"
              f" tiles warm at the second GET: {state['warm']}")
        one_post_with_image(rig)
        assert seen[0][0] == 503 and seen[0][2].get("error") == "composite_timeout", seen[0][2]
        assert seen[0][2].get("retry_after") == 5, seen[0][2]
        assert rig.sleeps == [5.0] and len(rig.byte_gets()) == 2, (rig.sleeps, len(rig.byte_gets()))
        assert state["warm"] and state["warm"] >= 1, state
    e2e(monkeypatch, tmp_path, body)


def test_c24e_a_renderer_unavailable_503_is_not_retried(monkeypatch, tmp_path):
    """The byte route answers _pc_require_renderer's string refusal (the
    shaping engine switched off for that one request): it is final."""
    async def body(env):
        own, subs, pack = await pack_of(env)

        async def off(call):
            env.mp.setattr(env.main, "_pc_raqm", lambda: False)

        async def on(call):
            env.mp.setattr(env.main, "_pc_raqm", lambda: True)
        rig = app_rig(env, hooks=[(is_bytes, off), (lambda c: is_json(c, "pack") and c.n == 2, on)])
        await run_pack(rig, own)
        got = rig.byte_gets()
        assert len(got) == 1 and got[0].status == 503, [c.status for c in got]
        assert body_of(got[0]) == {"detail": "text_shaping_unavailable"}, body_of(got[0])
        assert rig.sleeps == [], rig.sleeps
        text_ = one_post_without_image(rig)
        assert text_.startswith("**Pack 1**"), text_[:120]
    e2e(monkeypatch, tmp_path, body)


# -- 29: the actor is the gateway id's player -------------------------------------------------

IMPOSTOR_HANDLE = "dc-reveal-other-handle"


async def _actor_fixture(env):
    """A (linked, a PRIVATE binder, one pack) and B (linked, discord_username
    IMPOSTOR_HANDLE, one pack of its own)."""
    subs = await H.pool(env, 5)
    a = await env.player("actor", rating=None, public=False)
    b = await env.player("other", rating=None, username=IMPOSTOR_HANDLE)
    await env.snapshot()
    pack_a = await env.open_pack(a, subs)
    pack_b = await env.open_pack(b, subs)
    return a, b, pack_a, pack_b


def _never_read(rig, b, pack_b):
    for c in rig.calls:
        assert pack_b not in c.path and pack_b not in json.dumps(c.params), (c.path, c.params)
        assert b.id not in c.path, c.path
        assert str(b.discord) not in json.dumps(c.params), c.params
        found = body_of(c)
        if isinstance(found, dict):
            assert pack_b not in json.dumps(found) and b.id not in json.dumps(found), c.path


async def _resolves_to(env, a, handle, b=None, pack_b=None, pack_a=None):
    rig = app_rig(env)
    await rig.pack(rig.ctx(a.discord, name=handle), 1, False)
    one_post_with_image(rig)
    packs = [c for c in rig.calls if c.path == PACKS]
    assert packs and all(c.params.get("discord_id") == str(a.discord) for c in packs), [c.params for c in packs]
    assert all(body_of(c).get("actor_ref") == a.id for c in packs), [body_of(c).get("actor_ref") for c in packs]
    assert body_of(json_calls(rig, "pack")[0])["packs"][0]["pack_id"] == pack_a
    if b is not None:
        _never_read(rig, b, pack_b)
    rig = app_rig(env)
    await rig.binder(rig.ctx(a.discord, name=handle), None, 1)
    one_post_with_image(rig)
    first = body_of(json_calls(rig, "binder")[0])
    assert first["owner_ref"] == a.id and "shards" in first, "the viewer did not resolve as the binder's owner"
    if b is not None:
        _never_read(rig, b, pack_b)


def test_the_actor_is_resolved_from_the_gateway_id_alone(monkeypatch, tmp_path):
    """The invoker's gateway name equals B's discord_username. A's binder is
    private, so /binder shows it only to a viewer resolved as A."""
    async def body(env):
        a, b, pack_a, pack_b = await _actor_fixture(env)
        await _resolves_to(env, a, IMPOSTOR_HANDLE, b, pack_b, pack_a)
    e2e(monkeypatch, tmp_path, body)


def test_c29_a_handle_matching_nobody_still_resolves_normally(monkeypatch, tmp_path):
    async def body(env):
        a, b, pack_a, pack_b = await _actor_fixture(env)
        await _resolves_to(env, a, "dc-reveal-nobody-has-this", pack_a=pack_a)
    e2e(monkeypatch, tmp_path, body)


def test_c29_an_unlinked_account_still_gets_not_linked(monkeypatch, tmp_path):
    async def body(env):
        await _actor_fixture(env)
        rig = app_rig(env)
        ctx = rig.ctx(H.DISCORD_BASE + 777777, name=IMPOSTOR_HANDLE)
        await rig.pack(ctx, 1, False)
        assert rig.texts() == [rig.ns["_pc_not_linked"](ctx, ctx.author)], rig.texts()
        assert rig.attachments() == []
    e2e(monkeypatch, tmp_path, body)


# -- 30: no second pending_dms poller -------------------------------------------------------

class FakeLoop:
    def __init__(self, name, coro, started):
        self.name, self.coro, self.started, self.running = name, coro, started, False

    def is_running(self):
        return self.running

    def start(self, *a, **k):
        self.running = True
        self.started.append(self)


def _on_ready_names():
    """(loop names, everything else on_ready reads that is not a builtin)."""
    fn = _top(ast.parse(H.bot_source()), "on_ready")
    loops = sorted({n.func.value.id for n in ast.walk(fn) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute) and n.func.attr == "is_running"
                    and isinstance(n.func.value, ast.Name)})
    tasks = sorted({n.args[0].func.id for n in ast.walk(fn) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute) and n.func.attr == "create_task"
                    and n.args and isinstance(n.args[0], ast.Call) and isinstance(n.args[0].func, ast.Name)})
    return loops, tasks


def ready_rig(env):
    """on_ready lifted over fake loops and a task recorder, with the shipped
    poll_pending_dms, _ack_pending_dms and api_get over the real app. A fake
    DM send holds each send until every pending-DM poller that was started
    has reached its own send (released at once when there is one), so the
    interleaving a second poller races on is the one that runs."""
    loops, task_fns = _on_ready_names()
    started, created, deliveries = [], [], []
    gate = {"expected": 1, "arrived": 0, "event": None}

    async def dm_send(uid, content):
        gate["arrived"] += 1
        if gate["arrived"] >= gate["expected"]:
            gate["event"].set()
        try:
            await asyncio.wait_for(gate["event"].wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        deliveries.append((uid, content))

    def get_user(uid):
        async def send(content):
            await dm_send(uid, content)
        return SimpleNamespace(id=uid, send=send)

    async def fetch_user(uid):
        return get_user(uid)

    async def tree_sync():
        return []
    extra = {
        "bot": SimpleNamespace(tree=SimpleNamespace(sync=tree_sync), user="fixture-bot", guilds=[],
                               get_user=get_user, fetch_user=fetch_user),
        "_bridge_readers_started": False, "CHAT_CHANNEL_ID": 1, "ADMIN_CHANNEL_ID": 2, "_BOT_GEN": "fixture",
    }

    async def noop():
        return None
    for name in task_fns:
        extra[name] = noop
    rig = make_rig(H.asgi_handler(env), funcs={"on_ready", "poll_pending_dms", "_ack_pending_dms", "api_get"},
                   assigns={"_pdm_seen_ids"}, extra=extra)
    session = rig.ns["http_session"]
    rig.ns["aiohttp"].ClientSession = lambda *a, **k: session
    rig.ns["discord"].NotFound = type("NotFound", (Exception,), {})
    poller = rig.ns["poll_pending_dms"]
    for name in loops:
        rig.ns[name] = FakeLoop(name, poller if name == "poll_pending_dms" else noop, started)

    def create_task(coro):
        created.append(coro)
        return SimpleNamespace(cancel=lambda: None)
    rig.ns["asyncio"].create_task = create_task
    return rig, SimpleNamespace(started=started, created=created, deliveries=deliveries, gate=gate,
                                poller=poller)


def _dm_pollers(state):
    """Every task on_ready started that polls pending_dms: a started loop
    whose body is poll_pending_dms, or a created coroutine of it."""
    from_loops = [lp.coro for lp in state.started if lp.coro is state.poller]
    from_tasks = [c for c in state.created if getattr(getattr(c, "cr_code", None), "co_name", "") == "poll_pending_dms"]
    return from_loops, from_tasks


async def _seed_dm(env, who, content):
    """One pending row for `who`, dated first in the route's created_at order
    (the route hands out twenty at a time, and the schema carries the rows
    migrations seeded)."""
    await env.ex(f"INSERT INTO {SCHEMA}.pending_dms (steam_id, content, created_at)"
                 " VALUES (:s, :c, TIMESTAMPTZ '2000-01-01 00:00:00+00')", {"s": who.steam, "c": content})
    return await env.val(f"SELECT id FROM {SCHEMA}.pending_dms WHERE content = :c", {"c": content})


def test_the_reveal_adds_no_second_pending_dm_poller(monkeypatch, tmp_path):
    async def body(env):
        own, subs, pack = await pack_of(env)
        count = f"SELECT COUNT(*) FROM {SCHEMA}.pending_dms"
        before = await env.val(count)
        rig = app_rig(env)
        await run_pack(rig, own)
        await run_binder(rig, own)
        assert len(rig.sent) == 2
        assert await env.val(count) == before, "a reveal command enqueued a pending_dms row"
        content = "dc-reveal pending dm probe " + secrets.token_hex(4)
        dm_id = await _seed_dm(env, own, content)
        rig, state = ready_rig(env)
        await rig.ns["on_ready"]()
        from_loops, from_tasks = _dm_pollers(state)
        others = [c for c in state.created if c not in from_tasks]
        for c in others:
            c.close()
        state.gate["expected"] = len(from_loops) + len(from_tasks)
        state.gate["event"] = asyncio.Event()
        await asyncio.gather(*([fn() for fn in from_loops] + from_tasks))
        mine = [d for d in state.deliveries if d[1] == content]
        print(f"ROW30 pollers: {len(from_loops)} loop(s), {len(from_tasks)} created task(s); deliveries {len(mine)}")
        assert len(mine) == 1, f"the seeded row was delivered {len(mine)} times"
        assert mine[0][0] == int(own.discord)
        assert await env.val(f"SELECT delivered_at IS NOT NULL FROM {SCHEMA}.pending_dms WHERE id = :i",
                             {"i": dm_id}), "the seeded row was not acked"
        assert len(from_loops) + len(from_tasks) == 1, "more than one task polls pending_dms"
        assert [lp.name for lp in state.started].count("poll_pending_dms") == 1
    e2e(monkeypatch, tmp_path, body)


def test_c30_the_single_poller_still_delivers_the_seeded_row_once(monkeypatch, tmp_path):
    async def body(env):
        own = await env.player("owner", rating=None)
        content = "dc-reveal pending dm probe " + secrets.token_hex(4)
        await _seed_dm(env, own, content)
        rig, state = ready_rig(env)
        await rig.ns["on_ready"]()
        from_loops, from_tasks = _dm_pollers(state)
        for c in state.created:
            if c not in from_tasks:
                c.close()
        state.gate["event"] = asyncio.Event()
        await state.poller()
        assert [d for d in state.deliveries if d[1] == content] == [(int(own.discord), content)]
        for c in from_tasks:
            c.close()
    e2e(monkeypatch, tmp_path, body)


# -- 31: a gone slot carries the locale's neutral label ---------------------------------------

SECOND_LOCALE, SECOND_LABEL = "sv", "Namnlos spelare"


async def seed_label(env, locale, target):
    """A client-namespace catalogue entry for pc.unnamed in `locale`, under
    the composite msgctxt _pc_labels reads (english + U+0004 + identifier)."""
    eng = env.main._pcf.ENGLISH["pc.unnamed"]
    key = "dcreveal" + secrets.token_hex(4)
    await env.ex(f"INSERT INTO {SCHEMA}.i18n_keys (key_id, namespace, msgctxt, source_hash)"
                 " VALUES (:k, 'client', :m, :h)", {"k": key, "m": eng + chr(4) + "pc.unnamed", "h": "0" * 40})
    await env.ex(f"INSERT INTO {SCHEMA}.i18n_entries (key_id, language_code, target, state)"
                 " VALUES (:k, :l, :t, 'approved')", {"k": key, "l": locale, "t": target})


async def _erased_slot_lines(env):
    """For each locale: slot 3's and slot 1's lines of a pack whose slot 3
    subject erased their data, posted in that locale (slash form)."""
    await seed_label(env, SECOND_LOCALE, SECOND_LABEL)
    own, subs, pack = await pack_of(env)
    await env.delete_data(subs[2])
    out = {}
    for locale in ("en", SECOND_LOCALE):
        rig = app_rig(env)
        await rig.pack(rig.ctx(own.discord, slash=True, locale=locale), 1, False)
        assert len(rig.sent) == 1, rig.texts()
        lines = rig.texts()[0].split(chr(10))
        out[locale] = ([ln for ln in lines if ln.startswith("3. ")], [ln for ln in lines if ln.startswith("1. ")],
                       await _neutral_label(env, locale))
    return subs, out


def test_a_gone_slot_never_carries_a_stored_name(monkeypatch, tmp_path):
    async def body(env):
        subs, out = await _erased_slot_lines(env)
        wrong = []
        for locale, (line3, _line1, label) in out.items():
            print(f"ROW31 {locale}: label {label!r}; slot 3 {line3}")
            if not (len(line3) == 1 and line3[0].endswith(f"**{label}**")):
                wrong.append(locale)
        assert not wrong, f"ROW31 slot 3 is not the locale's neutral label in: {','.join(wrong)}"
        assert out[SECOND_LOCALE][2] == SECOND_LABEL != out["en"][2], (out[SECOND_LOCALE][2], out["en"][2])
    e2e(monkeypatch, tmp_path, body)


def test_c31_a_live_slot_still_carries_its_subjects_current_name(monkeypatch, tmp_path):
    async def body(env):
        subs, out = await _erased_slot_lines(env)
        for locale, (_line3, line1, _label) in out.items():
            assert len(line1) == 1 and f"**{subs[0].name}**" in line1[0], (locale, line1)
    e2e(monkeypatch, tmp_path, body)


# -- round 2, R1 MEDIUM Finding 1: /pack N reads its pack in one step ------------------------

F1_DEEP = 181


async def _f1_history(env, n):
    """`n` packs opened through the production open route by one owner, and
    their ids newest first - (opened_at, id) descending, the route's own
    order, sorted here from the rows rather than asked of the route."""
    subs = await H.pool(env, 5, tag="f1")
    price = int(env.main._pc.PC_ECONOMY["pack_price_shards"])
    own = await env.player("f1-owner", rating=None, shards=price * (n + 1))
    await env.snapshot()
    for _ in range(n):
        await env.open_pack(own, subs)
    rows = await env.rows(f"SELECT id::text AS id, opened_at FROM {SCHEMA}.pc_packs"
                          " WHERE player_id = CAST(:p AS uuid) AND status = 'done'", {"p": own.id})
    assert len(rows) == n, len(rows)
    return own, [r["id"] for r in sorted(rows, key=lambda r: (r["opened_at"], r["id"]), reverse=True)]


def test_f1_a_deep_pack_reveals_in_two_json_reads_whatever_its_index(monkeypatch, tmp_path):
    """R1 MEDIUM Finding 1. /pack N found its pack by walking the summary
    pages from the newest, ten a read, against the same 20-a-minute JSON
    pacing as step 1 and the final re-read: /pack 181 spent 19 reads before
    step 1, and its final re-read, the 21st, answered 429 and nothing
    posted. The pacing clock is frozen here, so every read of a run falls in
    one window. /pack 181 and /pack 90 each post their own pack whole,
    reading the packs route exactly twice - step 1 by `index`, the final
    re-read by `pack_id` - with no 429 on any request, in no more requests
    than S2.5's bound of 18."""
    async def body(env):
        own, newest_first = await _f1_history(env, F1_DEEP)
        env.mp.setattr(env.main, "_pc_reveal_clock", lambda: 1000.0)
        for index in (F1_DEEP, 90):
            env.mp.setattr(env.main, "_pc_reveal_windows", {})
            rig = app_rig(env)
            await run_pack(rig, own, index)
            one_post_with_image(rig)
            refused = [(c.method, c.path) for c in rig.calls if c.status == 429]
            assert not refused, (index, refused)
            reads = [c for c in rig.calls if c.path == PACKS]
            assert [c.status for c in reads] == [200, 200], [(c.params, c.status) for c in reads]
            assert reads[0].params.get("index") == index and "pack_id" not in reads[0].params, reads[0].params
            assert reads[1].params.get("pack_id") == newest_first[index - 1], (index, reads[1].params)
            assert len(rig.calls) <= 18, (index, [(c.method, c.path) for c in rig.calls])
            print(f"F1 /pack {index}: {len(reads)} JSON reads of the packs route, {len(rig.calls)} internal requests")
    e2e(monkeypatch, tmp_path, body)


def test_c_f1_the_latest_pack_posts_however_it_is_found(monkeypatch, tmp_path):
    """Control for Finding 1: /pack 1 never came near the pacing allowance -
    the walk read one summary page - so it posts whole with no 429 whichever
    way step 1 finds the pack, and the pack it reveals is the newest."""
    async def body(env):
        own, newest_first = await _f1_history(env, 3)
        env.mp.setattr(env.main, "_pc_reveal_clock", lambda: 1000.0)
        rig = app_rig(env)
        await run_pack(rig, own, 1)
        one_post_with_image(rig)
        assert not [c for c in rig.calls if c.status == 429], [(c.path, c.status) for c in rig.calls]
        assert [c for c in rig.calls if c.path == PACKS][-1].params.get("pack_id") == newest_first[0]
    e2e(monkeypatch, tmp_path, body)


def test_f1_an_index_past_the_last_pack_answers_the_count_from_one_read(monkeypatch, tmp_path):
    """The out-of-range line comes from step 1's own answer: one read, no
    image, and the count - for an index no route takes as well, which goes
    as the route's largest."""
    async def body(env):
        own, _newest_first = await _f1_history(env, 3)
        for index in (4, 10 ** 12):
            rig = app_rig(env)
            await run_pack(rig, own, index)
            assert rig.texts() == ["You have 3 opened packs: `/pack` goes from 1 (the latest) to 3."], rig.texts()
            assert rig.attachments() == []
            reads = [c for c in rig.calls if c.path == PACKS]
            assert [c.status for c in reads] == [200], [(c.params, c.status) for c in reads]
    e2e(monkeypatch, tmp_path, body)
