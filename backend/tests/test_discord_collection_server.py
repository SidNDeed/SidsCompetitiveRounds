"""DISCORD-COLLECTION: the server and route rows of DISCORD-COLLECTION-DESIGN.md
rev 13, section 10 - the four reveal routes, the compositor, the composite
path, pacing, the manifest and the face inputs.

Each row is one test named exactly as the table names it; its negative control
is a separate node named test_cNN_... (NN the row id). The mutation of each row
is applied, alone, by discord_collection_controls.py, which records which named
test went red. The shared fixtures are discord_collection_harness.py's.

Live PostgreSQL is required, and a missing DSN FAILS by name (the
test_ticket_redaction.py:390-396 shape):
    DISCORD_COLLECTION_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    DISCORD_COLLECTION_TEST_PG_OPTOUT=1   says out loud that this run skips them
"""

import ast
import asyncio
import hashlib
import inspect
import io
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import event, text

import discord_collection_harness as H
from discord_collection_harness import SCHEMA

DSN = os.environ.get("DISCORD_COLLECTION_TEST_PG_DSN")


def _optout(raw) -> bool:
    """Only an affirmative word opts out; "0", "false" or an unknown value do
    not, so the live rows then FAIL and name the DSN (#438)."""
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


OPTOUT = _optout(os.environ.get("DISCORD_COLLECTION_TEST_PG_OPTOUT"))


def require_pg():
    if DSN:
        return DSN
    if OPTOUT:
        pytest.skip("DISCORD_COLLECTION_TEST_PG_OPTOUT is set -- the Discord collection reveal's "
                    "live-PostgreSQL rows deliberately not run in this invocation")
    pytest.fail(
        "DISCORD_COLLECTION_TEST_PG_DSN is not set, so the Discord collection reveal's server rows "
        "were never executed. Set DISCORD_COLLECTION_TEST_PG_DSN=postgresql+asyncpg://... to run "
        "them, or DISCORD_COLLECTION_TEST_PG_OPTOUT=1 to say out loud that this run skips them.")


@pytest.mark.parametrize("raw,opts_out", [
    ("1", True), ("true", True), (" yes ", True), ("on", True),
    ("0", False), ("false", False), ("", False), (None, False), ("maybe", False),
])
def test_dc_server_gate_only_an_affirmative_opt_out_skips(raw, opts_out):
    assert _optout(raw) is opts_out


def test_dc_server_gate_a_missing_dsn_fails_by_name():
    assert "pytest.fail(" in inspect.getsource(require_pg)
    saved_dsn, saved_opt = globals()["DSN"], globals()["OPTOUT"]
    globals()["DSN"], globals()["OPTOUT"] = None, False
    try:
        with pytest.raises(BaseException) as ex:
            require_pg()
        assert "Failed" in type(ex.value).__name__
        assert "DISCORD_COLLECTION_TEST_PG_DSN" in str(ex.value)
        globals()["OPTOUT"] = True
        with pytest.raises(BaseException) as sk:
            require_pg()
        assert "Skipped" in type(sk.value).__name__
    finally:
        globals()["DSN"], globals()["OPTOUT"] = saved_dsn, saved_opt


# -- shared helpers --------------------------------------------------------------

PNG = b"\x89PNG\r\n\x1a\n"
WRITE_RE = re.compile(r'\bINSERT\s+INTO\b|\bDELETE\s+FROM\b|\bUPDATE\s+[\w."]+\s+SET\b', re.I)
NAMED_TABLES = ("rating_history", "player_items", "shop_items", "matches", "ranked_series",
                "glicko_ratings", "glicko_ratings_2v2", "glicko_ratings_1v2", "glicko_ratings_ffa")


def writes_to(statements, table):
    pat = re.compile(r'\b(?:INSERT\s+INTO|DELETE\s+FROM|UPDATE)\s+(?:"?\w+"?\.)?"?' + re.escape(table)
                     + r'"?(?=[\s(]|$)', re.I)
    return [s for s in statements if pat.search(s)]


def live(monkeypatch, tmp_path, fn, **kw):
    dsn = require_pg()

    async def go():
        async with H.Env(monkeypatch, tmp_path, dsn, **kw) as env:
            return await fn(env)
    return H.run(go())


async def five(env, *, owner=None, subjects=None, flags=None, tag="s"):
    """A snapshot and one opened pack: slot i deals subjects[i-1]."""
    subs = subjects if subjects is not None else await H.pool(env, 5, tag=tag)
    own = owner or await env.player("owner", rating=None)
    await env.snapshot()
    flags = flags or [(False, False)] * len(subs)
    pack = await env.open_pack(own, [(s, f, g) for s, (f, g) in zip(subs, flags)])
    return own, subs, pack


async def pack_prints(env, owner, pack, locale="en"):
    r = await env.packs_json(owner.discord, pack, locale=locale)
    assert r.status_code == 200, (r.status_code, r.text[:300])
    return r.json()["packs"][0]["prints"]


def manifest_of(r, header="x-strip-slots"):
    return [tuple(x.split(":")) for x in r.headers[header].split(",")]


def tile_bytes(env, print_id, rev, locale="en"):
    key = env.main._pcp.face_key(print_id, rev, locale, "tile")
    assert key is not None, (print_id, rev)
    return env.main._pc_face_cache.read(key)


def back_image(env):
    return env.main._pcstrip.strip_back_tile()


async def set_steam(env, who, value):
    await env.ex(f"UPDATE {SCHEMA}.players SET steam_id = :s WHERE id = CAST(:p AS uuid)",
                 {"s": value, "p": who.id})


def no_steam():
    return "dc_x_" + secrets.token_hex(4)


async def release_blob(env, h):
    """A released portrait blob: the players row still names it. The row's
    foreign key is bypassed for this one delete (replica role, this
    transaction only) - the state the janitor's release and a render's
    two reads can meet."""
    async with env.seed.begin() as c:
        await c.execute(text("SET LOCAL session_replication_role = replica"))
        await c.execute(text(f"DELETE FROM {SCHEMA}.pc_portraits WHERE hash = :h"), {"h": h})


async def exercise(env, owner, pack):
    """Every reveal route, cold and then warm, as the bot calls them."""
    out = [await env.packs_json(owner.discord), await env.packs_json(owner.discord, pack)]
    for _ in range(2):
        out.append(await env.strip(pack, owner.discord))
        out.append(await env.binder_json(owner.discord, owner.discord))
        out.append(await env.binder_page(owner.id, 1, owner.discord))
    for r in out:
        assert r.status_code == 200, (r.request.url.path, r.status_code, r.text[:200])
    return out


def strip_keys(env, pack):
    return env.cache_keys(f"strip/{pack}/")


# -- 1, 2: the strip route's ownership --------------------------------------------

def test_strip_refuses_a_pack_that_is_not_the_actors(monkeypatch, tmp_path):
    async def body(env):
        _owner, _subs, pack = await five(env)
        other = await env.player("other", rating=None)
        r = await env.strip(pack, other.discord)
        assert r.status_code == 404, (r.status_code, r.text[:200])
        assert not r.content.startswith(PNG)
    live(monkeypatch, tmp_path, body)


def test_c01_the_owners_own_pack_still_returns_200(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        r = await env.strip(pack, owner.discord)
        assert r.status_code == 200 and r.content.startswith(PNG), (r.status_code, r.text[:200])
    live(monkeypatch, tmp_path, body)


def test_strip_404s_rather_than_403s_for_a_foreign_pack(monkeypatch, tmp_path):
    async def body(env):
        _owner, _subs, pack = await five(env)
        other = await env.player("other", rating=None)
        r = await env.strip(pack, other.discord)
        assert r.status_code != 403, "a foreign pack answered 403: the refusal says the pack exists"
        assert r.status_code == 404, (r.status_code, r.text[:200])
    live(monkeypatch, tmp_path, body)


def test_c02_a_malformed_pack_id_still_404s(monkeypatch, tmp_path):
    async def body(env):
        owner = await env.player("owner", rating=None)
        r = await env.strip("not-a-pack-id", owner.discord)
        assert r.status_code == 404, (r.status_code, r.text[:200])
    live(monkeypatch, tmp_path, body)


# -- 3, 3b, 3c, 3d, 4: binder consent -----------------------------------------------

def test_binder_JSON_of_a_private_player_is_refused(monkeypatch, tmp_path):
    async def body(env):
        owner = await env.player("owner", rating=None, public=False)
        viewer = await env.player("viewer", rating=None)
        r = await env.binder_json(owner.discord, viewer.discord)
        assert r.status_code == 403, (r.status_code, r.text[:200])
        assert r.json()["detail"]["error"] == "private"
    live(monkeypatch, tmp_path, body)


def test_c03_a_public_binder_still_answers(monkeypatch, tmp_path):
    async def body(env):
        owner = await env.player("owner", rating=None, public=True)
        viewer = await env.player("viewer", rating=None)
        r = await env.binder_json(owner.discord, viewer.discord)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        assert r.json()["owner_ref"] == owner.id
    live(monkeypatch, tmp_path, body)


def test_binder_IMAGE_of_a_private_player_is_refused(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, _pack = await five(env)
        await env.set_public(owner, False)
        viewer = await env.player("viewer", rating=None)
        r = await env.binder_page(owner.id, 1, viewer.discord)
        assert r.status_code == 403, (r.status_code, r.text[:200])
        assert r.json()["detail"]["error"] == "private"
    live(monkeypatch, tmp_path, body)


def test_c03b_a_public_binders_page_still_renders(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, _pack = await five(env)
        viewer = await env.player("viewer", rating=None)
        r = await env.binder_page(owner.id, 1, viewer.discord)
        assert r.status_code == 200 and r.content.startswith(PNG), (r.status_code, r.text[:200])
    live(monkeypatch, tmp_path, body)


def test_binder_image_serves_a_public_binder_to_a_non_owner(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, _pack = await five(env)
        viewer = await env.player("viewer", rating=None)
        r = await env.binder_page(owner.id, 1, viewer.discord)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        assert r.content.startswith(PNG)
    live(monkeypatch, tmp_path, body)


def test_c03c_the_owners_own_private_page_still_renders(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, _pack = await five(env)
        await env.set_public(owner, False)
        r = await env.binder_page(owner.id, 1, owner.discord)
        assert r.status_code == 200 and r.content.startswith(PNG), (r.status_code, r.text[:200])
    live(monkeypatch, tmp_path, body)


def test_binder_image_owner_with_no_discord_id_is_not_the_owner(monkeypatch, tmp_path):
    async def body(env):
        unlinked = await env.player("owner", rating=None, discord=False, public=False)
        await five(env, owner=unlinked)
        assert unlinked.discord is None
        # The viewer id the bot would send for an absent id, as text.
        r = await env.binder_page(unlinked.id, 1, "None")
        assert r.status_code == 403, (r.status_code, r.text[:200])
        assert r.json()["detail"]["error"] == "private"
    live(monkeypatch, tmp_path, body)


def test_c03d_a_linked_owner_still_sees_their_own_private_page(monkeypatch, tmp_path):
    async def body(env):
        owner = await env.player("owner", rating=None, public=False)
        await five(env, owner=owner)
        r = await env.binder_page(owner.id, 1, owner.discord)
        assert r.status_code == 200 and r.content.startswith(PNG), (r.status_code, r.text[:200])
    live(monkeypatch, tmp_path, body)


def test_binder_shards_reach_the_owner_only(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, _pack = await five(env)
        viewer = await env.player("viewer", rating=None)
        r = await env.binder_json(owner.discord, viewer.discord)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        assert "shards" not in r.json(), "a viewer's answer carries the owner's shard balance"
    live(monkeypatch, tmp_path, body)


def test_c04_the_owners_own_answer_still_carries_shards(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, _pack = await five(env)
        r = await env.binder_json(owner.discord, owner.discord)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        balance = await env.val(f"SELECT pc_shards FROM {SCHEMA}.players WHERE id = CAST(:p AS uuid)",
                                {"p": owner.id})
        assert r.json().get("shards") == int(balance)
    live(monkeypatch, tmp_path, body)


# -- 5, 5b: nothing written ------------------------------------------------------

def test_no_reveal_route_writes_a_row(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        start = len(env.app_sql)
        await exercise(env, owner, pack)
        seen = env.app_sql[start:]
        assert any("pc_prints" in s for s in seen), "the recorder saw none of the routes' reads"
        writes = [" ".join(s.split())[:160] for s in seen if WRITE_RE.search(s)]
        assert writes == [], writes
    live(monkeypatch, tmp_path, body, record_app_sql=True)


def test_c05_the_production_open_route_still_writes_under_the_same_harness(monkeypatch, tmp_path):
    async def body(env):
        subs = await H.pool(env, 5)
        owner = await env.player("owner", rating=None)
        await env.snapshot()
        start = len(env.app_sql)
        await env.open_pack(owner, subs)
        writes = [s for s in env.app_sql[start:] if WRITE_RE.search(s)]
        assert writes_to(writes, "pc_prints") and writes_to(writes, "pc_packs"), writes[:5]
    live(monkeypatch, tmp_path, body, record_app_sql=True)


def test_no_reveal_route_touches_a_rating_an_item_or_a_match_result(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        start = len(env.app_sql)
        await exercise(env, owner, pack)
        seen = env.app_sql[start:]
        assert seen, "the recorder saw nothing"
        touched = {t: [" ".join(s.split())[:120] for s in writes_to(seen, t)] for t in NAMED_TABLES}
        assert {t: w for t, w in touched.items() if w} == {}, touched
    live(monkeypatch, tmp_path, body, record_app_sql=True)


def test_c05b_the_production_shop_purchase_is_seen_by_the_recorder(monkeypatch, tmp_path):
    async def body(env):
        buyer = await env.player("buyer", rating=None)
        item = (await env.rows(
            f"SELECT sku, price FROM {SCHEMA}.shop_items WHERE kind <> 'music_album' AND catalog_ready"
            " AND stock_limit IS NULL AND price > 0 ORDER BY price, sku LIMIT 1"))[0]
        await env.ex(f"UPDATE {SCHEMA}.players SET gold_earned = :g, gold_spent = 0 WHERE id = CAST(:p AS uuid)",
                     {"g": int(item["price"]) + 100, "p": buyer.id})
        start = len(env.app_sql)
        r = await env.client.post("/api/v1/shop/purchase", headers=env.mod_headers(buyer), params={
            "steam_id": buyer.steam, "sku": item["sku"], "sig": H.mod_sig(f"buy:{buyer.steam}:{item['sku']}")})
        assert r.status_code == 200, (r.status_code, r.text[:300])
        assert writes_to(env.app_sql[start:], "player_items"), "the recorder did not see the purchase row"
    live(monkeypatch, tmp_path, body, record_app_sql=True)


# -- 6, 7: no prerender, no Steam prime -------------------------------------------

def test_reveal_never_schedules_a_prerender(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        env.prerender_calls.clear()
        await exercise(env, owner, pack)
        assert env.prerender_calls == [], env.prerender_calls
    live(monkeypatch, tmp_path, body)


def test_c06_the_minting_request_still_schedules_one(monkeypatch, tmp_path):
    async def body(env):
        env.prerender_calls.clear()
        await five(env)
        assert len(env.prerender_calls) == 1 and len(env.prerender_calls[0][0]) == 5, env.prerender_calls
    live(monkeypatch, tmp_path, body)


def test_reveal_never_primes_steam(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        env.prime_calls.clear()
        await exercise(env, owner, pack)
        assert env.prime_calls == [], env.prime_calls
    live(monkeypatch, tmp_path, body)


def test_c07_the_pack_result_route_still_primes(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        env.prime_calls.clear()
        canon = env.main._pc.canon_result(owner.steam, pack)
        r = await env.client.get("/api/v1/pc/packs/result", headers=env.mod_headers(owner), params={
            "steam_id": owner.steam, "sig": H.mod_sig(canon), "pack_id": pack})
        assert r.status_code == 200, (r.status_code, r.text[:300])
        assert env.prime_calls and len(env.prime_calls[0]) == 5, env.prime_calls
    live(monkeypatch, tmp_path, body)


# -- 8, 9, 10: the strip's digest ------------------------------------------------------

def test_strip_key_moves_with_any_face_rev(monkeypatch, tmp_path):
    async def body(env):
        owner, subs, pack = await five(env)
        first = await env.strip(pack, owner.discord)
        assert first.status_code == 200, first.text[:200]
        await env.rename(subs[2], "Renamed Slot Three")
        second = await env.strip(pack, owner.discord)
        assert second.status_code == 200, second.text[:200]
        assert manifest_of(first)[2][4] != manifest_of(second)[2][4], "the rename did not move slot 3's face_rev"
        assert first.headers["x-strip-rev"] != second.headers["x-strip-rev"], \
            "slot 3's face_rev moved and the strip digest did not"
    live(monkeypatch, tmp_path, body)


def test_c08_two_identical_pack_states_still_hit_the_same_key(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        a = await env.strip(pack, owner.discord)
        b = await env.strip(pack, owner.discord)
        assert a.status_code == b.status_code == 200
        assert a.headers["x-strip-rev"] == b.headers["x-strip-rev"]
        assert len(strip_keys(env, pack)) == 1, strip_keys(env, pack)
        assert a.content == b.content
    live(monkeypatch, tmp_path, body)


def _tokens(n=5):
    import pc_strip
    return [pc_strip.strip_slot_token(i, f"{i:08d}-0000-4000-8000-000000000000", "face", f"{i:016x}", "live")
            for i in range(1, n + 1)]


def test_strip_key_moves_with_slot_order():
    import pc_strip
    toks = _tokens()
    forward = pc_strip.composite_digest("en", "0123456789abcdef", 5, 1, toks)
    backward = pc_strip.composite_digest("en", "0123456789abcdef", 5, 1, list(reversed(toks)))
    assert forward != backward, "a reordered token list keyed the same digest"


def test_c09_the_same_order_still_hits_the_same_digest():
    import pc_strip
    toks = _tokens()
    assert pc_strip.composite_digest("en", "0123456789abcdef", 5, 1, toks) == \
        pc_strip.composite_digest("en", "0123456789abcdef", 5, 1, list(toks))


def test_strip_key_moves_with_locale_and_layout_version(monkeypatch):
    import pc_strip
    toks = _tokens()
    base = pc_strip.composite_digest("en", "0123456789abcdef", 5, 1, toks)
    assert pc_strip.composite_digest("es", "0123456789abcdef", 5, 1, toks) != base, \
        "the locale is not in the digest input"
    assert pc_strip.composite_digest("en", "0123456789abcdef", 5, 2, toks) != base, \
        "the grid shape is not in the digest input"
    monkeypatch.setattr(pc_strip, "STRIP_GUTTER", pc_strip.STRIP_GUTTER + 2)
    assert pc_strip.composite_digest("en", "0123456789abcdef", 5, 1, toks) != base, \
        "a layout constant is not in the digest input"


def test_c10_an_unchanged_locale_still_hits_warm(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        a = await env.strip(pack, owner.discord, locale="en")
        b = await env.strip(pack, owner.discord, locale="en")
        assert a.status_code == b.status_code == 200
        assert a.headers["x-strip-rev"] == b.headers["x-strip-rev"]
        assert len(strip_keys(env, pack)) == 1
    live(monkeypatch, tmp_path, body)


# -- 11, 12, 12b: what each slot draws -------------------------------------------------

async def _five_faces_in_order(env, owner, pack):
    prints = await pack_prints(env, owner, pack)
    r = await env.strip(pack, owner.discord)
    assert r.status_code == 200, (r.status_code, r.text[:200])
    img = H.image_of(r.content)
    assert img.size == (1947, 549), img.size
    assert [p["slot"] for p in prints] == [1, 2, 3, 4, 5]
    assert all(p["tile"] == "face" for p in prints), [p["tile"] for p in prints]
    for p in prints:
        tile = tile_bytes(env, p["print_id"], p["face_rev"])
        assert tile is not None, f"slot {p['slot']}'s tile is not in the face cache"
        assert H.same_pixels(img.crop(H.slot_rect(p["slot"])), H.image_of(tile)), \
            f"slot {p['slot']}'s rect is not its own tile"
    return prints, img


def test_strip_has_exactly_five_slots_in_order(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        await _five_faces_in_order(env, owner, pack)
    live(monkeypatch, tmp_path, body)


def test_c11_five_identical_cells_match_byte_for_byte():
    from PIL import Image
    import pc_strip
    rnd = __import__("random").Random(11)
    tile = Image.frombytes("RGBA", (375, 525), bytes(rnd.getrandbits(8) for _ in range(375 * 525 * 4)))
    buf = io.BytesIO()
    tile.save(buf, format="PNG")
    data = pc_strip.compose_composite([("face", buf.getvalue(), False)] * 5, 5, 1, 8 << 20)
    img = H.image_of(data)
    for slot in range(1, 6):
        assert H.same_pixels(img.crop(H.slot_rect(slot)), tile), slot


def test_a_slot_whose_subject_has_no_steamid64_becomes_the_back_not_a_gap(monkeypatch, tmp_path):
    async def body(env):
        owner, subs, pack = await five(env)
        await set_steam(env, subs[2], no_steam())
        prints = await pack_prints(env, owner, pack)
        assert len(prints) == 5
        assert (prints[2]["tile"], prints[2]["reason"]) == ("back", "no_steam_id"), prints[2]
        r = await env.strip(pack, owner.discord)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        m = manifest_of(r)
        assert len(m) == 5 and [int(e[0]) for e in m] == [1, 2, 3, 4, 5], m
        assert (m[2][3], m[2][4]) == ("back", "no_steam_id"), m[2]
        img = H.image_of(r.content)
        assert H.same_pixels(img.crop(H.slot_rect(3)), back_image(env)), "slot 3 is not the card back"
    live(monkeypatch, tmp_path, body)


def test_c12_five_drawable_slots_still_draw_five_faces(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        await _five_faces_in_order(env, owner, pack)
    live(monkeypatch, tmp_path, body)


def test_the_back_tile_is_375x525_and_matches_the_asset_path():
    import pc_face
    import pc_strip
    tile = pc_strip.strip_back_tile()
    ref = pc_face._asset("Back.png", "tile").convert("RGBA")
    assert tile.size == (375, 525), tile.size
    assert tile.mode == "RGBA"
    assert tile.tobytes() == ref.tobytes(), "the strip's back is not the asset path's tile-size back"


def test_c12b_the_card_size_back_is_still_750x1050():
    import pc_face
    assert H.image_of(pc_face.render_back()).size == (750, 1050)


# -- 12d, 12e, 12f, 12g: backs, discards and the digest ------------------------------

def test_a_released_portrait_blob_503s_the_composite_and_publishes_nothing(monkeypatch, tmp_path):
    async def body(env):
        subs = await H.pool(env, 5)
        h = await env.give_portrait(subs[2], 303)
        owner, _subs, pack = await five(env, subjects=subs)
        prints = await pack_prints(env, owner, pack)
        assert prints[2]["tile"] == "face"
        await release_blob(env, h)
        r = await env.strip(pack, owner.discord)
        assert r.status_code == 503, (r.status_code, r.text[:200])
        assert r.json()["detail"] == {"error": "portrait_pending", "retry_after": 2}
        assert r.headers.get("retry-after") == "2"
        assert strip_keys(env, pack) == [], strip_keys(env, pack)
    live(monkeypatch, tmp_path, body)


def test_c12d_the_no_steam_id_back_still_composes_and_publishes(monkeypatch, tmp_path):
    async def body(env):
        owner, subs, pack = await five(env)
        await set_steam(env, subs[2], no_steam())
        r = await env.strip(pack, owner.discord)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        assert len(strip_keys(env, pack)) == 1
    live(monkeypatch, tmp_path, body)


def test_the_digest_separates_a_back_slot_from_a_drawn_slot(monkeypatch, tmp_path):
    async def body(env):
        owner, subs, pack = await five(env)
        valid = subs[2].steam
        await set_steam(env, subs[2], no_steam())
        first = await env.strip(pack, owner.discord)
        assert first.status_code == 200 and manifest_of(first)[2][3] == "back"
        await set_steam(env, subs[2], valid)
        second = await env.strip(pack, owner.discord)
        assert second.status_code == 200 and manifest_of(second)[2][3] == "face"
        assert first.headers["x-strip-rev"] != second.headers["x-strip-rev"], \
            "a back slot and a drawn slot keyed one digest"
        a, b = H.image_of(first.content), H.image_of(second.content)
        assert not H.same_pixels(a.crop(H.slot_rect(3)), b.crop(H.slot_rect(3))), \
            "the drawn slot served the back's pixels"
    live(monkeypatch, tmp_path, body)


def test_c12e_flipping_nothing_still_hits_the_warm_key(monkeypatch, tmp_path):
    async def body(env):
        owner, subs, pack = await five(env)
        await set_steam(env, subs[2], no_steam())
        first = await env.strip(pack, owner.discord)
        second = await env.strip(pack, owner.discord)
        assert first.status_code == second.status_code == 200
        assert first.headers["x-strip-rev"] == second.headers["x-strip-rev"]
        assert len(strip_keys(env, pack)) == 1
    live(monkeypatch, tmp_path, body)


def test_a_discarded_print_of_a_no_steamid64_subject_draws_the_back_and_posts(monkeypatch, tmp_path):
    async def body(env):
        owner, subs, pack = await five(env)
        prints = await pack_prints(env, owner, pack)
        await env.discard(owner, prints[2]["print_id"])
        await set_steam(env, subs[2], no_steam())
        prints = await pack_prints(env, owner, pack)
        assert prints[2]["discarded"] is True
        assert (prints[2]["tile"], prints[2]["reason"]) == ("back", "no_steam_id"), prints[2]
        r = await env.strip(pack, owner.discord)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        assert manifest_of(r)[2][3:] == ("back", "no_steam_id", "discarded"), manifest_of(r)[2]
        assert H.same_pixels(H.image_of(r.content).crop(H.slot_rect(3)), back_image(env))
    live(monkeypatch, tmp_path, body)


def test_c12f_a_discarded_print_of_a_drawable_subject_still_draws_a_stamped_face(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        prints = await pack_prints(env, owner, pack)
        await env.discard(owner, prints[2]["print_id"])
        prints = await pack_prints(env, owner, pack)
        assert (prints[2]["tile"], prints[2]["discarded"]) == ("face", True), prints[2]
        r = await env.strip(pack, owner.discord)
        assert r.status_code == 200
        assert manifest_of(r)[2][3] == "face" and manifest_of(r)[2][5] == "discarded"
        from PIL import Image
        raw = Image.open(io.BytesIO(tile_bytes(env, prints[2]["print_id"], prints[2]["face_rev"]))).convert("RGBA")
        stamped = env.main._pcstrip._stamp_discarded(raw)
        assert H.same_pixels(H.image_of(r.content).crop(H.slot_rect(3)), stamped)
    live(monkeypatch, tmp_path, body)


def test_a_discard_changes_the_pixels_and_not_only_the_digest(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        prints = await pack_prints(env, owner, pack)
        first = await env.strip(pack, owner.discord)
        await env.discard(owner, prints[1]["print_id"])
        second = await env.strip(pack, owner.discord)
        assert first.status_code == second.status_code == 200
        assert first.headers["x-strip-rev"] != second.headers["x-strip-rev"], "the discard did not move the digest"
        a, b = H.image_of(first.content), H.image_of(second.content)
        assert not H.same_pixels(a.crop(H.slot_rect(2)), b.crop(H.slot_rect(2))), \
            "the discard moved the digest and left the tile's pixels as they were"
    live(monkeypatch, tmp_path, body)


def test_c12g_the_digest_half_alone_still_passes(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        prints = await pack_prints(env, owner, pack)
        first = await env.strip(pack, owner.discord)
        await env.discard(owner, prints[1]["print_id"])
        second = await env.strip(pack, owner.discord)
        assert first.headers["x-strip-rev"] != second.headers["x-strip-rev"]
    live(monkeypatch, tmp_path, body)


def test_c12g_a_live_prints_rect_stays_byte_equal_to_its_own_tile(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        prints = await pack_prints(env, owner, pack)
        await env.discard(owner, prints[1]["print_id"])
        r = await env.strip(pack, owner.discord)
        img = H.image_of(r.content)
        p = prints[0]
        assert H.same_pixels(img.crop(H.slot_rect(1)), H.image_of(tile_bytes(env, p["print_id"], p["face_rev"])))
    live(monkeypatch, tmp_path, body)


# -- 12h, 12i: erasure and the stored roster ------------------------------------------

def test_a_pack_whose_subject_deleted_their_data_still_posts_five_slots(monkeypatch, tmp_path):
    async def body(env):
        owner, subs, pack = await five(env)
        await env.delete_data(subs[2])
        prints = await pack_prints(env, owner, pack)
        assert len(prints) == 5, [p.get("slot") for p in prints]
        gone = prints[2]
        assert (gone["slot"], gone["tile"], gone["reason"], gone["gone"]) == (3, "back", "print_gone", True), gone
        r = await env.strip(pack, owner.discord)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        m = manifest_of(r)
        assert len(m) == 5, m
        assert (m[2][0], m[2][3], m[2][4], m[2][5]) == ("3", "back", "print_gone", "gone"), m[2]
    live(monkeypatch, tmp_path, body)


def test_c12h_a_pack_whose_five_prints_are_all_live_still_composes_five_faces(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        await _five_faces_in_order(env, owner, pack)
    live(monkeypatch, tmp_path, body)


def test_a_pack_whose_stored_roster_is_short_is_a_500(monkeypatch, tmp_path, capsys):
    async def body(env):
        owner, subs, pack = await five(env)
        await env.delete_data(subs[4])
        stored = await env.val(f"SELECT result::text FROM {SCHEMA}.pc_packs WHERE id = CAST(:p AS uuid)", {"p": pack})
        doc = json.loads(stored)
        doc["prints"] = [p for p in doc["prints"] if p.get("slot") != 5]
        await env.ex(f"UPDATE {SCHEMA}.pc_packs SET result = CAST(:r AS jsonb) WHERE id = CAST(:p AS uuid)",
                     {"r": json.dumps(doc), "p": pack})
        capsys.readouterr()
        j = await env.packs_json(owner.discord, pack)
        s = await env.strip(pack, owner.discord)
        out = capsys.readouterr().out
        assert j.status_code == 500 and j.json()["detail"] == {"error": "roster_invalid"}, (j.status_code, j.text[:200])
        assert s.status_code == 500 and s.json()["detail"] == {"error": "roster_invalid"}, (s.status_code, s.text[:200])
        assert out.count(f"[PC-REVEAL] roster_invalid pack={pack} live_rows=4") == 2, out[-600:]
    live(monkeypatch, tmp_path, body)


def test_c12i_the_four_live_one_deleted_pack_still_returns_200(monkeypatch, tmp_path):
    async def body(env):
        owner, subs, pack = await five(env)
        await env.delete_data(subs[2])
        assert (await env.packs_json(owner.discord, pack)).status_code == 200
        assert (await env.strip(pack, owner.discord)).status_code == 200
    live(monkeypatch, tmp_path, body)


# -- 13: a discarded print still draws ----------------------------------------------

def test_discarded_print_still_draws_in_a_strip(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        prints = await pack_prints(env, owner, pack)
        await env.discard(owner, prints[1]["print_id"])
        prints = await pack_prints(env, owner, pack)
        assert (prints[1]["tile"], prints[1]["discarded"]) == ("face", True), prints[1]
        r = await env.strip(pack, owner.discord)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        assert manifest_of(r)[1][3] == "face" and manifest_of(r)[1][5] == "discarded", manifest_of(r)[1]
    live(monkeypatch, tmp_path, body)


def test_c13_a_live_print_is_unaffected(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        r = await env.strip(pack, owner.discord)
        assert r.status_code == 200
        assert all(e[3] == "face" and e[5] == "live" for e in manifest_of(r)), manifest_of(r)
    live(monkeypatch, tmp_path, body)


# -- 14g, 14g2, 14k, 14m, 14r, 14s: the binder page ----------------------------------

async def binder_prints(env, owner, viewer=None, page=1):
    r = await env.binder_json(owner.discord, viewer if viewer is not None else owner.discord, page=page)
    assert r.status_code == 200, (r.status_code, r.text[:300])
    return r.json()


def test_a_binder_page_never_lists_a_discarded_print(monkeypatch, tmp_path):
    async def body(env):
        subs = await H.pool(env, 5)
        owner = await env.player("owner", rating=None)
        await env.snapshot()
        a = await env.open_pack(owner, subs)
        b = await env.open_pack(owner, subs)
        c = await env.open_pack(owner, [(subs[0], True, True)] + subs[1:])
        kept = [p["print_id"] for p in (await pack_prints(env, owner, a)) + (await pack_prints(env, owner, b))]
        gone = await pack_prints(env, owner, c)
        assert gone[0]["foil"] and gone[0]["signed"] and gone[0]["rarity"] == "legendary", gone[0]
        for p in gone:
            await env.discard(owner, p["print_id"])
        answer = await binder_prints(env, owner)
        listed = [p["print_id"] for p in answer["prints"]]
        assert not any(p["discarded"] for p in answer["prints"]), "a discarded print is listed"
        assert len(listed) == 10 and set(listed) == set(kept), (len(listed), set(listed) - set(kept))
    live(monkeypatch, tmp_path, body)


def test_c14g_the_strip_manifest_still_carries_its_three_valued_state_word(monkeypatch, tmp_path):
    async def body(env):
        owner, subs, pack = await five(env)
        prints = await pack_prints(env, owner, pack)
        await env.discard(owner, prints[1]["print_id"])
        await env.delete_data(subs[3])
        prints = await pack_prints(env, owner, pack)
        r = await env.strip(pack, owner.discord)
        assert r.status_code == 200
        states = [e[5] for e in manifest_of(r)]
        assert states == ["live", "discarded", "live", "gone", "live"], states
        want = ["gone" if p["gone"] else ("discarded" if p["discarded"] else "live") for p in prints]
        assert states == want
    live(monkeypatch, tmp_path, body)


def test_the_grid_manifest_numbers_grid_positions_not_pack_slots(monkeypatch, tmp_path):
    async def body(env):
        subs = await H.pool(env, 5)
        owner = await env.player("owner", rating=None)
        await env.snapshot()
        await env.open_pack(owner, subs)
        await env.open_pack(owner, subs)
        answer = await binder_prints(env, owner)
        assert len(answer["prints"]) == 10 and len({p["slot"] for p in answer["prints"]}) == 5
        r = await env.binder_page(owner.id, 1, owner.discord)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        m = manifest_of(r, "x-grid-slots")
        assert [int(e[0]) for e in m] == list(range(1, 11)), [e[0] for e in m]
        assert [e[1] for e in m] == [p["print_id"].replace("-", "") for p in answer["prints"]]
    live(monkeypatch, tmp_path, body)


def test_c14g2_the_strip_manifest_still_leads_with_the_pack_slot(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        prints = await pack_prints(env, owner, pack)
        r = await env.strip(pack, owner.discord)
        assert [int(e[0]) for e in manifest_of(r)] == [p["slot"] for p in prints] == [1, 2, 3, 4, 5]
    live(monkeypatch, tmp_path, body)


async def tied_pair(env):
    """Owner O with exactly two live prints X and Y: one pack, one subject in
    slots 1 and 2, same rarity, foil and signed, so the same pool_rank and,
    from one transaction, the same minted_at. Returns (O, LO, HI)."""
    subs = await H.pool(env, 4)
    owner = await env.player("owner", rating=None)
    await env.snapshot()
    pack = await env.open_pack(owner, [subs[0], subs[0], subs[1], subs[2], subs[3]])
    prints = await pack_prints(env, owner, pack)
    x, y = prints[0], prints[1]
    assert x["subject_player_id"] == y["subject_player_id"]
    assert (x["rarity"], x["foil"], x["signed"]) == (y["rarity"], y["foil"], y["signed"])
    for p in prints[2:]:
        await env.discard(owner, p["print_id"])
    lo, hi = sorted([x["print_id"], y["print_id"]])
    keys = await env.rows(f"SELECT pool_rank, minted_at FROM {SCHEMA}.pc_prints"
                          " WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid))", {"a": lo, "b": hi})
    assert len({(k["pool_rank"], k["minted_at"]) for k in keys}) == 1, keys
    return owner, lo, hi


async def touch(env, print_id):
    """A no-op UPDATE of a mutable column: a new tuple at the heap's tail."""
    await env.ex(f"UPDATE {SCHEMA}.pc_prints SET owner_player_id = owner_player_id WHERE id = CAST(:p AS uuid)",
                 {"p": print_id})


async def heap_order(env, owner):
    return [r["id"] for r in await env.rows(
        f"SELECT id::text AS id FROM {SCHEMA}.pc_prints WHERE owner_player_id = CAST(:o AS uuid)"
        " AND discarded_at IS NULL ORDER BY ctid", {"o": owner.id})]


def test_the_binder_page_orders_a_tie_by_print_id(monkeypatch, tmp_path):
    async def body(env):
        owner, lo, hi = await tied_pair(env)
        await touch(env, lo)
        assert await heap_order(env, owner) == [hi, lo], "the fixture did not reverse the heap order"
        ids = [p["print_id"] for p in (await binder_prints(env, owner))["prints"]]
        assert ids[0] == lo and ids[1] == hi, ids
    live(monkeypatch, tmp_path, body)


def test_c14k_the_key_order_survives_the_other_heap_order(monkeypatch, tmp_path):
    async def body(env):
        owner, lo, hi = await tied_pair(env)
        await touch(env, hi)
        assert await heap_order(env, owner) == [lo, hi]
        ids = [p["print_id"] for p in (await binder_prints(env, owner))["prints"]]
        assert ids == [lo, hi], ids
    live(monkeypatch, tmp_path, body)


async def ten_with_one_no_steam(env):
    subs = await H.pool(env, 10)
    owner = await env.player("owner", rating=None)
    await env.snapshot()
    await env.open_pack(owner, subs[:5])
    await env.open_pack(owner, subs[5:])
    await set_steam(env, subs[2], no_steam())
    return owner, subs


def test_the_binder_json_carries_a_tile_decision_for_every_entry(monkeypatch, tmp_path):
    async def body(env):
        owner, subs = await ten_with_one_no_steam(env)
        answer = await binder_prints(env, owner)
        prints = answer["prints"]
        assert len(prints) == 10
        assert all("tile" in p and p["tile"] in ("face", "back") for p in prints), prints
        rule1 = [p for p in prints if p["subject_player_id"] == subs[2].id]
        assert len(rule1) == 1 and (rule1[0]["tile"], rule1[0]["reason"]) == ("back", "no_steam_id"), rule1
        r = await env.binder_page(owner.id, 1, owner.discord)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        m = manifest_of(r, "x-grid-slots")
        assert len(m) == 10
        mismatched = [i + 1 for i, (p, e) in enumerate(zip(prints, m)) if p["tile"] != e[3]]
        assert mismatched == [], f"the JSON's face/back word differs from the manifest at {mismatched}"
    live(monkeypatch, tmp_path, body)


def test_c14m_the_binder_image_route_still_emits_back_no_steam_id(monkeypatch, tmp_path):
    async def body(env):
        owner, subs = await ten_with_one_no_steam(env)
        r = await env.binder_page(owner.id, 1, owner.discord)
        assert r.status_code == 200
        m = manifest_of(r, "x-grid-slots")
        rule1 = [e for e in m if e[2] == subs[2].id.replace("-", "")]
        assert len(rule1) == 1 and (rule1[0][3], rule1[0][4]) == ("back", "no_steam_id"), rule1
        assert sum(1 for e in m if e[3] == "face") == 9
    live(monkeypatch, tmp_path, body)


async def owner_with(env, subs, packs, discard):
    """An owner with `packs` packs dealt from `subs` (five a pack, cycling),
    then `discard` of the prints discarded from the end."""
    owner = await env.player(f"owner{secrets.token_hex(2)}", rating=None)
    prints = []
    for i in range(packs):
        deal = [subs[(i * 5 + j) % len(subs)] for j in range(5)]
        pack = await env.open_pack(owner, deal)
        prints += await pack_prints(env, owner, pack)
    for p in prints[len(prints) - discard:]:
        await env.discard(owner, p["print_id"])
    return owner, prints[:len(prints) - discard]


async def spread(env, snap):
    """Five bands over pool ranks 1-10, two ranks a band (a fixture state:
    a ten-member pool's own bands are legendary and epic only)."""
    await env.ex(f"UPDATE {SCHEMA}.pc_pool_members SET rarity = (ARRAY['legendary', 'epic', 'rare', 'uncommon',"
                 " 'common'])[LEAST(5, (pool_rank + 1) / 2)] WHERE snapshot_id = :s", {"s": snap})


async def group_by(env, owner):
    return {r["rarity"]: int(r["n"]) for r in await env.rows(
        f"SELECT rarity, count(*) AS n FROM {SCHEMA}.pc_prints WHERE owner_player_id = CAST(:o AS uuid)"
        " AND discarded_at IS NULL GROUP BY rarity", {"o": owner.id})}


def test_the_binder_metadata_survives_an_empty_page(monkeypatch, tmp_path):
    async def body(env):
        subs = await H.pool(env, 10)
        await spread(env, await env.snapshot())
        small, live_small = await owner_with(env, subs, 2, 3)
        assert len(live_small) == 7 and len({p["rarity"] for p in live_small}) >= 3, \
            [p["rarity"] for p in live_small]
        empty = await binder_prints(env, small, page=2)
        assert empty["prints"] == []
        assert empty["count"] == 7, empty
        assert sum(empty["by_rarity"].values()) == 7, empty["by_rarity"]
        grouped = await group_by(env, small)
        assert {k: v for k, v in empty["by_rarity"].items() if v} == grouped, (empty["by_rarity"], grouped)
        assert empty["pages"] == 1
        big, _live_big = await owner_with(env, subs, 5, 2)
        full = await binder_prints(env, big, page=1)
        assert (full["count"], full["pages"], len(full["prints"])) == (23, 3, 10), \
            (full["count"], full["pages"], len(full["prints"]))
    live(monkeypatch, tmp_path, body)


def test_c14r_the_23_print_owners_page_2_reads_under_both_forms(monkeypatch, tmp_path):
    async def body(env):
        subs = await H.pool(env, 10)
        await spread(env, await env.snapshot())
        big, _live = await owner_with(env, subs, 5, 2)
        page2 = await binder_prints(env, big, page=2)
        assert (page2["count"], page2["pages"], len(page2["prints"])) == (23, 3, 10)
    live(monkeypatch, tmp_path, body)


def test_the_binder_rarity_totals_sum_to_the_count(monkeypatch, tmp_path, capsys):
    async def body(env):
        subs = await H.pool(env, 10)
        await spread(env, await env.snapshot())
        owner, kept = await owner_with(env, subs, 2, 4)
        assert len(kept) == 6 and len({p["rarity"] for p in kept}) >= 2
        await env.ex(
            f"INSERT INTO {SCHEMA}.pc_prints (card_id, owner_player_id, snapshot_id, rarity, foil, signed,"
            " pool_rank, rating, peak_rating, board_rank, series_wins, series_losses, top_card, title, source)"
            " SELECT card_id, owner_player_id, snapshot_id, 'mythic', foil, signed, pool_rank, rating,"
            f" peak_rating, board_rank, series_wins, series_losses, top_card, title, source FROM {SCHEMA}.pc_prints"
            " WHERE id = CAST(:p AS uuid)", {"p": kept[0]["print_id"]})
        capsys.readouterr()
        answer = await binder_prints(env, owner)
        out = capsys.readouterr().out
        known = {k: v for k, v in answer["by_rarity"].items() if k in env.main._pc.RARITIES}
        assert answer["count"] == 7, answer
        assert sum(known.values()) == 6, known
        assert answer["by_rarity"].get("other") == 1, answer["by_rarity"]
        assert sum(answer["by_rarity"].values()) == answer["count"], answer["by_rarity"]
        assert out.count(f"[PC-BINDER] unknown_rarity owner={owner.id} count=1") == 1, out[-400:]
    live(monkeypatch, tmp_path, body)


def test_c14s_an_all_known_owner_reads_other_zero_and_logs_nothing(monkeypatch, tmp_path, capsys):
    async def body(env):
        subs = await H.pool(env, 10)
        await spread(env, await env.snapshot())
        owner, kept = await owner_with(env, subs, 2, 3)
        capsys.readouterr()
        answer = await binder_prints(env, owner)
        out = capsys.readouterr().out
        assert answer["by_rarity"].get("other", 0) == 0
        assert sum(answer["by_rarity"].values()) == answer["count"] == len(kept)
        assert "unknown_rarity" not in out
    live(monkeypatch, tmp_path, body)


# -- 16, 16b: the render pool and the composite gate ----------------------------------

async def face_get(env, print_id, size="card", locale="en"):
    return await env.client.get(f"/api/v1/internal/pc/face/print/{print_id}/{locale}", headers=env.ihead(),
                                params={"size": size})


async def packs_of(env, n, subs=None):
    subs = subs or await H.pool(env, 5)
    owner = await env.player("owner", rating=None)
    await env.snapshot()
    return owner, [await env.open_pack(owner, subs) for _ in range(n)]


def test_composite_does_not_nest_on_the_render_pool(monkeypatch, tmp_path):
    async def body(env):
        main = env.main
        assert main._pcp.POOL._max_workers == 2
        monkeypatch.setattr(main, "_PC_COMPOSITE_PER_PLAYER", 1000)
        owner, packs = await packs_of(env, 4)
        started = time.monotonic()
        answers = await asyncio.wait_for(asyncio.gather(*(env.strip(p, owner.discord) for p in packs)),
                                         timeout=60)
        assert [a.status_code for a in answers] == [200] * 4, [a.text[:120] for a in answers]
        print(f"four concurrent cold composites in {time.monotonic() - started:.2f} s")
    live(monkeypatch, tmp_path, body)


def test_c16_the_sequential_form_still_completes_under_the_pool(monkeypatch, tmp_path):
    async def body(env):
        owner, packs = await packs_of(env, 2)
        for p in packs:
            r = await asyncio.wait_for(env.strip(p, owner.discord), timeout=60)
            assert r.status_code == 200
    live(monkeypatch, tmp_path, body)


async def _warm_faces(env, owner, pack):
    prints = await pack_prints(env, owner, pack)
    for p in prints:
        r = await face_get(env, p["print_id"])
        assert r.status_code == 200, (r.status_code, r.text[:200])
    return prints


async def _timed_face_gets(env, prints, n=20):
    out = []
    for i in range(n):
        p = prints[i % len(prints)]
        t0 = time.perf_counter()
        r = await face_get(env, p["print_id"])
        out.append((r.status_code, time.perf_counter() - t0, r.text[:120] if r.status_code != 200 else ""))
    return out


def test_composites_do_not_starve_the_face_routes(monkeypatch, tmp_path):
    async def body(env):
        main = env.main
        monkeypatch.setattr(main, "_PC_COMPOSITE_PER_PLAYER", 1000)
        owner, packs = await packs_of(env, 10)
        prints = await _warm_faces(env, owner, packs[0])
        release = asyncio.Event()
        real = main._pc_render_face

        async def held(db, row, ctx, size, want=None):
            if size == "tile":
                await release.wait()
            return await real(db, row, ctx, size, want)
        monkeypatch.setattr(main, "_pc_render_face", held)
        composites = [asyncio.create_task(env.strip(p, owner.discord)) for p in packs]
        gate = main._pc_composite_gate
        for _ in range(500):
            await asyncio.sleep(0.01)
            if gate._sem.locked() and gate._waiting >= main._PC_COMPOSITE_QUEUE_DEPTH:
                break
        assert gate._sem.locked() and gate._waiting == 8, (gate._sem.locked(), gate._waiting)
        timed = await _timed_face_gets(env, prints)
        release.set()
        done = await asyncio.gather(*composites)
        assert [d.status_code for d in done] == [200] * 10
        busy = [t for t in timed if "composite_busy" in t[2]]
        assert busy == [], busy[:3]
        assert all(st == 200 and dt < 1.5 for st, dt, _ in timed), timed
    live(monkeypatch, tmp_path, body)


def test_c16b_the_same_face_gets_under_an_idle_composite_gate_still_pass(monkeypatch, tmp_path):
    async def body(env):
        owner, packs = await packs_of(env, 1)
        prints = await _warm_faces(env, owner, packs[0])
        timed = await _timed_face_gets(env, prints)
        assert all(st == 200 and dt < 1.5 for st, dt, _ in timed), timed
    live(monkeypatch, tmp_path, body)


# -- 17, 17c: the composite cap ----------------------------------------------------------

def test_composite_over_the_cap_is_refused_not_truncated(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        first = await env.strip(pack, owner.discord)
        assert first.status_code == 200
        size = len(first.content)
        monkeypatch.setattr(env.main, "_PC_COMPOSITE_MAX_BYTES", size - 1)
        warm = await env.strip(pack, owner.discord)
        assert warm.status_code == 500, (warm.status_code, len(warm.content))
        assert warm.json()["detail"] == {"error": "composite_too_large"}
        assert not warm.content.startswith(PNG)
        for key in strip_keys(env, pack):
            (env.faces_root / key).unlink()
        cold = await env.strip(pack, owner.discord)
        assert cold.status_code == 500 and cold.json()["detail"] == {"error": "composite_too_large"}
        assert strip_keys(env, pack) == [], "a refused composite was published"
    live(monkeypatch, tmp_path, body)


def test_c17_a_body_one_byte_under_the_cap_still_returns_whole(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        first = await env.strip(pack, owner.discord)
        size = len(first.content)
        monkeypatch.setattr(env.main, "_PC_COMPOSITE_MAX_BYTES", size + 1)
        again = await env.strip(pack, owner.discord)
        assert again.status_code == 200 and again.content == first.content
        assert int(again.headers["content-length"]) == size
        assert H.image_of(again.content).size == (1947, 549)
    live(monkeypatch, tmp_path, body)


async def densest(env):
    """Ten subjects with noisy portraits, every print legendary, foil and
    signed: the snapshot's member rarity is set to legendary (a fixture
    state), so the production open mints legendary prints."""
    subs = await H.pool(env, 10)
    for i, s in enumerate(subs):
        await env.give_portrait(s, 1700 + i, noisy=True, radius=300)
    owner = await env.player("owner", rating=None)
    snap = await env.snapshot()
    await env.ex(f"UPDATE {SCHEMA}.pc_pool_members SET rarity = 'legendary' WHERE snapshot_id = :s", {"s": snap})
    a = await env.open_pack(owner, [(s, True, True) for s in subs[:5]])
    b = await env.open_pack(owner, [(s, True, True) for s in subs[5:]])
    return owner, a, b


def test_the_densest_grid_is_served_whole_under_the_cap(monkeypatch, tmp_path):
    async def body(env):
        owner, _a, _b = await densest(env)
        answer = await binder_prints(env, owner)
        assert all((p["rarity"], p["foil"], p["signed"], p["tile"]) == ("legendary", True, True, "face")
                   for p in answer["prints"]) and len(answer["prints"]) == 10
        r = await env.binder_page(owner.id, 1, owner.discord)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        assert H.image_of(r.content).size == (1947, 1086)
        assert len(r.content) == int(r.headers["content-length"])
        assert len(r.content) <= env.main._PC_COMPOSITE_MAX_BYTES
        print(f"DENSEST-GRID bytes={len(r.content)} cap={env.main._PC_COMPOSITE_MAX_BYTES}")
    live(monkeypatch, tmp_path, body)


def test_c17c_the_five_slot_strip_of_the_same_tiles_is_also_served_whole(monkeypatch, tmp_path):
    async def body(env):
        owner, a, _b = await densest(env)
        r = await env.strip(a, owner.discord)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        assert H.image_of(r.content).size == (1947, 549)
        print(f"DENSEST-STRIP bytes={len(r.content)}")
    live(monkeypatch, tmp_path, body)


def test_c17c_the_densest_grid_composes_at_the_production_cap(monkeypatch, tmp_path):
    async def body(env):
        owner, _a, _b = await densest(env)
        answer = await binder_prints(env, owner)
        for p in answer["prints"]:
            assert (await face_get(env, p["print_id"], size="tile")).status_code == 200
        cells = [("face", tile_bytes(env, p["print_id"], p["face_rev"]), False) for p in answer["prints"]]
        data = env.main._pcstrip.compose_composite(cells, 5, 2, 8 << 20)
        assert H.image_of(data).size == (1947, 1086)
    live(monkeypatch, tmp_path, body)


# -- 18, 18b: pacing ----------------------------------------------------------------------

def test_per_player_composite_pacing_refuses_the_seventh_in_a_minute(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        codes = [(await env.strip(pack, owner.discord)).status_code for _ in range(6)]
        assert codes == [200] * 6, codes
        seventh = await env.strip(pack, owner.discord)
        assert seventh.status_code == 429, (seventh.status_code, seventh.text[:200])
        assert seventh.json()["detail"]["error"] == "too_many"
    live(monkeypatch, tmp_path, body)


def test_c18_six_within_the_minute_still_pass(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        codes = [(await env.strip(pack, owner.discord)).status_code for _ in range(6)]
        assert codes == [200] * 6, codes
    live(monkeypatch, tmp_path, body)


def _fake_clock(monkeypatch, main):
    now = [1000.0]
    monkeypatch.setattr(main, "_pc_reveal_clock", lambda: now[0])
    return now


def test_the_pacing_window_is_bracketed_from_both_sides(monkeypatch, tmp_path):
    async def body(env):
        main = env.main
        now = _fake_clock(monkeypatch, main)
        owner, _subs, pack = await five(env)
        codes = [(await env.strip(pack, owner.discord)).status_code for _ in range(6)]
        assert codes == [200] * 6, codes
        now[0] += 45.0
        at_45 = await env.strip(pack, owner.discord)
        assert at_45.status_code == 429, f"request 7 at t=45 s answered {at_45.status_code}"
        main._pc_reveal_windows.clear()
        now[0] = 5000.0
        codes = [(await env.strip(pack, owner.discord)).status_code for _ in range(6)]
        assert codes == [200] * 6, codes
        now[0] += 61.0
        at_61 = await env.strip(pack, owner.discord)
        assert at_61.status_code == 200, f"request 7 at t=61 s answered {at_61.status_code}"
    live(monkeypatch, tmp_path, body)


def test_c18b_requests_one_to_six_still_pass_in_both_runs(monkeypatch, tmp_path):
    async def body(env):
        main = env.main
        now = _fake_clock(monkeypatch, main)
        owner, _subs, pack = await five(env)
        for start in (1000.0, 5000.0):
            main._pc_reveal_windows.clear()
            now[0] = start
            codes = [(await env.strip(pack, owner.discord)).status_code for _ in range(6)]
            assert codes == [200] * 6, codes
    live(monkeypatch, tmp_path, body)


# -- 19, 19b, 20: the internal key and the renderer gate come first ----------------------

class _NoSession:
    def __getattr__(self, name):
        raise AssertionError(f"the handler used its database session ({name}) before refusing the key")


def _handlers(main, pack_id, owner_ref):
    return {
        "internal_pc_packs": lambda key, db: main.internal_pc_packs(
            discord_id="1", pack_id=None, before=None, limit=5, locale=None, x_internal_key=key, db=db),
        "internal_pc_pack_strip": lambda key, db: main.internal_pc_pack_strip(
            pack_id=pack_id, locale="en", discord_id="1", x_internal_key=key, db=db),
        "internal_pc_binder": lambda key, db: main.internal_pc_binder(
            discord_id="1", viewer_discord_id=None, page=1, locale=None, x_internal_key=key, db=db),
        "internal_pc_binder_page": lambda key, db: main.internal_pc_binder_page(
            owner_ref=owner_ref, page="1", locale="en", viewer_discord_id=None, x_internal_key=key, db=db),
    }


def test_internal_key_is_required_before_any_work(monkeypatch, tmp_path):
    async def body(env):
        from fastapi import HTTPException
        handlers = _handlers(env.main, "0" * 8 + "-0000-4000-8000-" + "0" * 12, "1" * 8 + "-0000-4000-8000-" + "1" * 12)
        for name, call in handlers.items():
            for key in (None, "not-the-key"):
                try:
                    await call(key, _NoSession())
                except HTTPException as ex:
                    assert ex.status_code == 403, (name, ex.status_code)
                else:
                    raise AssertionError(f"{name} answered without the internal key")
    live(monkeypatch, tmp_path, body)


def test_c19_the_same_handlers_with_the_key_still_answer(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        main = env.main
        async with env.database.async_session() as db:
            packs = await main.internal_pc_packs(discord_id=owner.discord, pack_id=None, before=None, limit=5,
                                                 locale=None, x_internal_key=H.INTERNAL_KEY, db=db)
            assert packs["total"] == 1
        async with env.database.async_session() as db:
            strip = await main.internal_pc_pack_strip(pack_id=pack, locale="en", discord_id=owner.discord,
                                                      x_internal_key=H.INTERNAL_KEY, db=db)
            assert strip.status_code == 200 and bytes(strip.body).startswith(PNG)
        async with env.database.async_session() as db:
            binder = await main.internal_pc_binder(discord_id=owner.discord, viewer_discord_id=None, page=1,
                                                   locale=None, x_internal_key=H.INTERNAL_KEY, db=db)
            assert binder["count"] == 5
        async with env.database.async_session() as db:
            page = await main.internal_pc_binder_page(owner_ref=owner.id, page="1", locale="en",
                                                      viewer_discord_id=None, x_internal_key=H.INTERNAL_KEY, db=db)
            assert page.status_code == 200
    live(monkeypatch, tmp_path, body)


def _count_key_checks(monkeypatch, main):
    entries = []
    real = main._require_internal_key

    def spy(key):
        entries.append(key)
        return real(key)
    monkeypatch.setattr(main, "_require_internal_key", spy)
    return entries


def test_the_middleware_refuses_before_the_handler_is_entered(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        entries = _count_key_checks(monkeypatch, env.main)
        paths = [("/api/v1/internal/pc/packs", {"discord_id": owner.discord}),
                 (f"/api/v1/internal/pc/packs/{pack}/strip/en.png", {"discord_id": owner.discord}),
                 ("/api/v1/internal/pc/binder", {"discord_id": owner.discord}),
                 (f"/api/v1/internal/pc/binder/{owner.id}/page/1/en.png", {})]
        for path, params in paths:
            r = await env.client.get(path, params=params)
            assert r.status_code == 403, (path, r.status_code)
        assert entries == [], f"the handler was entered {len(entries)} time(s) without the key"
    live(monkeypatch, tmp_path, body)


def test_c19b_a_correct_key_still_reaches_the_handler_exactly_once(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, _pack = await five(env)
        entries = _count_key_checks(monkeypatch, env.main)
        r = await env.packs_json(owner.discord)
        assert r.status_code == 200 and len(entries) == 1, (r.status_code, entries)
    live(monkeypatch, tmp_path, body)


def test_renderer_unavailable_503s_before_ownership_is_read(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        monkeypatch.setattr(env.main, "_pc_raqm", lambda: False)
        start = len(env.app_sql)
        for r in (await env.strip(pack, owner.discord), await env.packs_json(owner.discord, pack),
                  await env.binder_page(owner.id, 1, owner.discord)):
            assert r.status_code == 503, (r.request.url.path, r.status_code)
            assert r.json()["detail"] == "text_shaping_unavailable"
        sent = [" ".join(s.split())[:100] for s in env.app_sql[start:]]
        assert sent == [], f"the 503 path read the database first: {sent}"
    live(monkeypatch, tmp_path, body, record_app_sql=True)


def test_c20_a_healthy_box_still_200s(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        assert (await env.strip(pack, owner.discord)).status_code == 200
    live(monkeypatch, tmp_path, body)


# -- 25, 25b, 25c, 25d, 25e, 25f: every drawn input is keyed -----------------------------

import textwrap
import uuid as _uuid
from datetime import timedelta
from decimal import Decimal

_PORTRAIT_COLUMNS = ("portrait_hash", "steam_portrait_hash")
_BANDS = ("legendary", "epic", "rare", "uncommon", "common")


def _varied(name, value):
    """One changed value for a row column, or the sentinel `None` when the
    column is not varied (the portrait hashes: a hash without its blob is a
    different state, 12d's)."""
    if name in _PORTRAIT_COLUMNS:
        return None
    if name == "rarity":
        return next(b for b in _BANDS if b != value)
    if value is None:
        return {"title": "Fixture Title", "board_rank": 7, "top_card": "BombsAway", "peak_rating": 1777.0,
                "discard_shards": 150, "series_wins": 3, "series_losses": 2}.get(name)
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, (float, Decimal)):
        return float(value) + 150.0
    if isinstance(value, str):
        return value + "Q"
    if isinstance(value, _uuid.UUID):
        return _uuid.uuid4()
    if hasattr(value, "tzinfo") and hasattr(value, "year"):
        return value + timedelta(days=3)
    return None


async def _render_fresh(env, monkeypatch, db, row, ctx, n):
    """(face_rev, tile bytes + card bytes) of `row` rendered into an empty
    cache: a key the row does not move cannot hand back another state's file.
    Both sizes, because the card size draws the footer the tile leaves out
    (edition, mint date, print number) under the same face_rev."""
    main = env.main
    out = []
    for size in ("tile", "card"):
        root = env.tmp / f"fresh{n}{size}"
        root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(main, "_pc_face_cache", main._pcp.FaceCache(str(root)))
        rev, data = await main._pc_render_face(db, row, ctx, size)
        out.append((rev, data))
    assert out[0][0] == out[1][0]
    return out[0][0], out[0][1] + out[1][1]


async def _one_row(env, db, print_id):
    main = env.main
    return dict((await db.execute(text(main._pc_composite_row_sql("WHERE pr.id = CAST(:p AS uuid)")),
                                  {"p": print_id})).mappings().one())


def test_every_drawn_face_input_is_in_the_spec_dict(monkeypatch, tmp_path):
    async def body(env):
        main = env.main
        owner, _subs, pack = await five(env)
        pid = (await pack_prints(env, owner, pack))[0]["print_id"]
        async with env.database.async_session() as db:
            row = await _one_row(env, db, pid)
            ctx = await main._pc_face_ctx(db, "en")
            base_rev, base_png = await _render_fresh(env, monkeypatch, db, row, ctx, 0)
            drawn, unkeyed = [], []
            for i, (name, value) in enumerate(sorted(row.items())):
                new = _varied(name, value)
                if new is None:
                    continue
                rev, png = await _render_fresh(env, monkeypatch, db, dict(row, **{name: new}), ctx, i + 1)
                if png != base_png:
                    drawn.append(name)
                    if rev == base_rev:
                        unkeyed.append(name)
        print(f"drawn columns: {drawn}")
        assert len(drawn) >= 8, drawn
        assert unkeyed == [], f"drawn without moving face_rev: {unkeyed}"
    live(monkeypatch, tmp_path, body)


def test_c25_an_undrawn_field_still_leaves_face_rev_alone(monkeypatch, tmp_path):
    async def body(env):
        main = env.main
        owner, _subs, pack = await five(env)
        pid = (await pack_prints(env, owner, pack))[0]["print_id"]
        async with env.database.async_session() as db:
            row = await _one_row(env, db, pid)
            ctx = await main._pc_face_ctx(db, "en")
            base = main._pc_face_inputs(row, ctx)[3]
            for name in ("slot", "source", "card_id", "owner_player_id", "pack_id", "snapshot_id", "subject_id_ok"):
                assert main._pc_face_inputs(dict(row, **{name: _varied(name, row[name])}), ctx)[3] == base, name
    live(monkeypatch, tmp_path, body)


def _render_face_contract(face_src, caller_src):
    """Findings: render_face's parameters must be exactly (spec, labels,
    portrait_png, size), and the one call in the caller must pass exactly four
    positional arguments after the function and no keyword."""
    findings = []
    face = ast.parse(textwrap.dedent(face_src))
    fn = next(n for n in ast.walk(face) if isinstance(n, ast.FunctionDef) and n.name == "render_face")
    params = [a.arg for a in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs]
    if fn.args.vararg or fn.args.kwarg:
        params.append("*")
    if params != ["spec", "labels", "portrait_png", "size"]:
        findings.append(f"render_face parameters {params}")
    caller = ast.parse(textwrap.dedent(caller_src))
    calls = [n for n in ast.walk(caller) if isinstance(n, ast.Call) and n.args
             and ast.unparse(n.args[0]).endswith("render_face")]
    if len(calls) != 1:
        findings.append(f"{len(calls)} render_face calls in the caller")
    for c in calls:
        if len(c.args) - 1 != 4 or c.keywords:
            findings.append(f"render_face called with {len(c.args) - 1} positional and {len(c.keywords)} keyword")
    return findings


def test_render_face_takes_exactly_four_arguments():
    import main
    import pc_face
    assert list(inspect.signature(pc_face.render_face).parameters) == ["spec", "labels", "portrait_png", "size"]
    findings = _render_face_contract(Path(pc_face.__file__).read_text(encoding="utf-8"),
                                     inspect.getsource(main._pc_render_face))
    assert findings == [], findings


def test_c25b_the_four_argument_call_and_a_keyed_spec_field_still_pass(monkeypatch, tmp_path):
    async def body(env):
        import pc_face
        main = env.main
        assert _render_face_contract(Path(pc_face.__file__).read_text(encoding="utf-8"),
                                     inspect.getsource(main._pc_render_face)) == []
        owner, _subs, pack = await five(env)
        pid = (await pack_prints(env, owner, pack))[0]["print_id"]
        async with env.database.async_session() as db:
            row = await _one_row(env, db, pid)
            ctx = await main._pc_face_ctx(db, "en")
        spec, kind, phash, rev = main._pc_face_inputs(row, ctx)
        assert pc_face.render_face(spec, ctx["labels"], None, "tile").startswith(PNG)
        keyed = dict(spec, extra_keyed_field=1)
        assert pc_face.render_face(keyed, ctx["labels"], None, "tile").startswith(PNG)
        assert main._pcp.face_rev(ctx["renderer_fp"], ctx["cat_rev"], keyed, kind, phash) != rev
    live(monkeypatch, tmp_path, body)


def _colour_findings(src):
    """Every value _pc_face_inputs derives from ctx["colors"] must be used
    only inside the returned spec (or to derive another such value), and one
    such value must reach the spec."""
    fn = ast.parse(textwrap.dedent(src)).body[0]

    def reads_colors(node):
        return any(isinstance(n, ast.Subscript) and ast.unparse(n.value) == "ctx"
                   and ast.unparse(n.slice).strip("'\"") == "colors" for n in ast.walk(node))

    def is_spec(assign):
        return any(isinstance(t, ast.Name) and t.id == "spec" for t in assign.targets)
    assigns = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)]
    tainted, changed = set(), True
    while changed:
        changed = False
        for a in assigns:
            if is_spec(a):
                continue
            if reads_colors(a.value) or any(isinstance(x, ast.Name) and x.id in tainted for x in ast.walk(a.value)):
                for t in a.targets:
                    for x in ast.walk(t):
                        if isinstance(x, ast.Name) and x.id not in tainted:
                            tainted.add(x.id)
                            changed = True
    allowed = set()
    for a in assigns:
        if is_spec(a) or any(isinstance(x, ast.Name) and x.id in tainted for t in a.targets for x in ast.walk(t)):
            allowed.update(id(x) for x in ast.walk(a.value))
    findings = [f"line {n.lineno}: {n.id} leaves outside the spec" for n in ast.walk(fn)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in tainted and id(n) not in allowed]
    in_spec = any(isinstance(x, ast.Name) and x.id in tainted or reads_colors(x)
                  for a in assigns if is_spec(a) for x in ast.walk(a.value))
    if not in_spec:
        findings.append("no resolved colour reaches the spec")
    return findings


async def _set_colour(env, rank, hex_):
    await env.ex(f"INSERT INTO {SCHEMA}.rank_role_colors (name, color_hex, updated_at) VALUES (:n, :c, now())"
                 " ON CONFLICT (name) DO UPDATE SET color_hex = EXCLUDED.color_hex", {"n": rank, "c": hex_})
    env.main._rank_colors_cache.update({"at": 0.0, "ok": False, "map": {}})


def test_every_resolved_colour_reaches_the_renderer_inside_the_spec(monkeypatch, tmp_path):
    async def body(env):
        main = env.main
        assert _colour_findings(inspect.getsource(main._pc_face_inputs)) == []
        owner, _subs, pack = await five(env)
        pid = (await pack_prints(env, owner, pack))[0]["print_id"]
        async with env.database.async_session() as db:
            row = await _one_row(env, db, pid)
        rank = main._pc_rank_name(main._pc_num(row["rating"]))
        assert rank
        seen = []
        for hex_ in ("#FF00FF", "#00FF00"):
            await _set_colour(env, rank, hex_)
            async with env.database.async_session() as db:
                ctx = await main._pc_face_ctx(db, "en")
            seen.append(main._pc_face_inputs(row, ctx)[0].get("title_rgb"))
        assert seen == [(255, 0, 255), (0, 255, 0)], seen
    live(monkeypatch, tmp_path, body)


def test_c25c_a_colour_arriving_as_data_and_landing_in_spec_still_passes():
    today = '''
def _pc_face_inputs(row, ctx):
    rank_name = _pc_rank_name(row["rating"])
    title_hex = (ctx["colors"].get(rank_name) or _rank_fallback_color(rank_name)) if rank_name else None
    spec = {"band": row["rarity"], "title_rgb": _pc_hex_rgb(title_hex)}
    rev = _pcp.face_rev(spec)
    return spec, "none", None, rev
'''
    assert _colour_findings(today) == []


_RENDER_MODULE_RE = re.compile(r'"source/([A-Za-z0-9_]+\.py)"')


def _renderer_modules():
    """The Python modules renderer_fingerprint()'s record set covers."""
    import pc_face
    src = inspect.getsource(pc_face._renderer_fingerprint_cached)
    names = _RENDER_MODULE_RE.findall(src)
    assert names, "renderer_fingerprint records no source module"
    return [Path(pc_face.__file__).with_name(n) for n in names]


_DECLARED_ROOTS = {"_ASSETS_PATH": "_MODULE_DIR / 'assets' / 'pc'",
                   "_FONTS_PATH": "_MODULE_DIR / 'assets' / 'fonts'",
                   "ASSETS_DIR": "str(_ASSETS_PATH)", "FONTS_DIR": "str(_FONTS_PATH)"}
_MODULE_DIR_DEF = "Path(__file__).resolve().parent"
_DIR_PARAMS = {"fonts_dir", "assets_dir"}
_PATH_METHODS = {"resolve", "rglob", "iterdir", "glob", "joinpath", "with_name", "with_suffix", "absolute"}
_READ_METHODS = {"read_bytes", "read_text", "open", "iterdir", "rglob", "glob"}
_READ_CALLS = {"Image.open", "ImageFont.truetype", "ImageFont.load", "ImageFont.FreeTypeFont"}
_FORBIDDEN_IMPORTS = {"os", "sqlalchemy", "asyncpg", "database", "models", "psycopg", "psycopg2", "dotenv"}
_DB_CALLS = {"execute", "executemany", "fetch", "fetchrow", "fetchval", "scalar", "scalars", "cursor"}
# The one function the file-read rule does not cover: it walks the installed
# Pillow package to hash its bytes into the fingerprint, and hands back only
# a hex digest - no value it reads can reach a pixel. The environment and
# database rules still apply inside it.
_READ_EXEMPT = {"_package_digest"}
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _scope_walk(node):
    """Every node of one scope: nested functions and lambdas are their own."""
    todo = list(ast.iter_child_nodes(node))
    while todo:
        n = todo.pop()
        yield n
        if not isinstance(n, _SCOPES):
            todo.extend(ast.iter_child_nodes(n))


def _rooted(node, names, fns):
    """True when `node` is a path under the assets or the fonts directory."""
    if isinstance(node, ast.Name):
        return node.id in names
    if isinstance(node, ast.Attribute):
        return node.attr == "parent" and _rooted(node.value, names, fns)
    if isinstance(node, ast.BinOp):
        return isinstance(node.op, ast.Div) and _rooted(node.left, names, fns)
    if isinstance(node, (ast.List, ast.Tuple)):
        return bool(node.elts) and all(_rooted(e, names, fns) for e in node.elts)
    if isinstance(node, (ast.GeneratorExp, ast.ListComp)):
        bound = set(names)
        for g in node.generators:
            if not _rooted(g.iter, bound, fns):
                return False
            bound |= {x.id for x in ast.walk(g.target) if isinstance(x, ast.Name)}
        return _rooted(node.elt, bound, fns)
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name):
            if f.id in fns and not node.args and not node.keywords:
                return True
            if f.id in ("Path", "str", "sorted", "list", "tuple") and node.args:
                return _rooted(node.args[0], names, fns)
            return False
        if isinstance(f, ast.Attribute) and f.attr in _PATH_METHODS:
            return _rooted(f.value, names, fns)
    return False


def _scope_names(scope, base, fns):
    """`base` plus every name the scope binds ONLY from rooted paths."""
    bound = {}
    for n in _scope_walk(scope):
        pairs = []
        if isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
            pairs = [(n.target, n.iter)]
        elif isinstance(n, ast.Assign):
            pairs = [(t, n.value) for t in n.targets]
        elif isinstance(n, ast.AnnAssign) and n.value is not None:
            pairs = [(n.target, n.value)]
        elif isinstance(n, ast.withitem) and n.optional_vars is not None:
            pairs = [(n.optional_vars, None)]
        for target, value in pairs:
            if isinstance(target, ast.Name):
                bound.setdefault(target.id, []).append(value)
            else:
                for x in ast.walk(target):
                    if isinstance(x, ast.Name):
                        bound.setdefault(x.id, []).append(None)
    names, changed = set(base), True
    while changed:
        changed = False
        for name, values in bound.items():
            if name not in names and all(v is not None and _rooted(v, names, fns) for v in values):
                names.add(name)
                changed = True
    return names


def _face_source_findings(src):
    """No colour from a DB session, os.environ, or a path outside the assets
    and fonts directories: no environment read and no database import or
    call anywhere in the module, the declared roots bound once each to the
    module's own assets and fonts directories, and every file the module
    opens, reads or lists rooted at one of them (the module's own source,
    read to hash it, is the one other file)."""
    tree = ast.parse(src)
    findings = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr in ("environ", "environb", "getenv", "putenv"):
            findings.append(f"line {n.lineno}: environment read {ast.unparse(n)}")
        elif isinstance(n, ast.Name) and n.id in ("environ", "getenv"):
            findings.append(f"line {n.lineno}: environment read {n.id}")
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in n.names] + ([n.module] if isinstance(n, ast.ImportFrom) and n.module else [])
            bad = sorted({m.split(".")[0] for m in mods if m} & _FORBIDDEN_IMPORTS)
            if bad:
                findings.append(f"line {n.lineno}: imports {bad}")
        elif isinstance(n, ast.Attribute) and n.attr in _DB_CALLS:
            findings.append(f"line {n.lineno}: database call {ast.unparse(n)}")
    top = {}
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    top.setdefault(t.id, []).append(ast.unparse(n.value))
    every = [t.id for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign))
             for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)]
    for name, want in list(_DECLARED_ROOTS.items()) + [("_MODULE_DIR", _MODULE_DIR_DEF)]:
        if top.get(name) != [want] or every.count(name) != 1:
            findings.append(f"root {name} bound as {top.get(name)} ({every.count(name)} bindings), not {want}")
    module_names = _scope_names(tree, set(_DECLARED_ROOTS), set())
    fns = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not (
                n.args.args or n.args.posonlyargs or n.args.kwonlyargs or n.args.vararg or n.args.kwarg):
            rets = [r.value for r in ast.walk(n) if isinstance(r, ast.Return)]
            if rets and all(r is not None and _rooted(r, module_names, set()) for r in rets):
                fns.add(n.name)
    dir_params = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            ps = [a.arg for a in n.args.posonlyargs + n.args.args]
            hits = [(i, p) for i, p in enumerate(ps) if p in _DIR_PARAMS]
            if hits:
                dir_params[n.name] = hits
    scopes = [(tree, module_names)]
    for n in ast.walk(tree):
        if isinstance(n, _SCOPES):
            params = {a.arg for a in n.args.posonlyargs + n.args.args + n.args.kwonlyargs}
            scopes.append((n, _scope_names(n, module_names | (params & _DIR_PARAMS), fns)))
    for scope, names in scopes:
        exempt = getattr(scope, "name", None) in _READ_EXEMPT
        for n in _scope_walk(scope):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            if isinstance(f, ast.Name) and f.id in dir_params:
                for i, p in dir_params[f.id]:
                    arg = n.args[i] if i < len(n.args) else next(
                        (k.value for k in n.keywords if k.arg == p), None)
                    if arg is None or not _rooted(arg, names, fns):
                        findings.append(f"line {n.lineno}: {f.id} is handed a {p} that is not the module's own")
            if exempt:
                continue
            name = ast.unparse(f)
            if isinstance(f, ast.Name) and f.id == "open" or name in _READ_CALLS:
                target = n.args[0] if n.args else None
                if isinstance(target, ast.Call) and ast.unparse(target.func) == "io.BytesIO":
                    continue
            elif isinstance(f, ast.Attribute) and f.attr in _READ_METHODS:
                target = f.value
            else:
                continue
            if target is not None and ast.unparse(target) == "Path(__file__)":
                continue
            if target is None or not _rooted(target, names, fns):
                findings.append(f"line {n.lineno}: reads a file outside the assets and fonts: {ast.unparse(n)[:90]}")
    return findings


def test_no_face_colour_arrives_from_outside_spec_source_or_assets():
    mods = _renderer_modules()
    assert [m.name for m in mods] == ["pc_face.py"], mods
    findings = []
    for m in mods:
        findings += [f"{m.name} {f}" for f in _face_source_findings(m.read_text(encoding="utf-8"))]
    assert findings == [], findings


def test_c25d_a_colour_in_spec_or_a_source_constant_still_passes():
    src = '''
import io
from pathlib import Path
from PIL import Image
_MODULE_DIR = Path(__file__).resolve().parent
_ASSETS_PATH = _MODULE_DIR / "assets" / "pc"
_FONTS_PATH = _MODULE_DIR / "assets" / "fonts"
ASSETS_DIR = str(_ASSETS_PATH)
FONTS_DIR = str(_FONTS_PATH)
GOLD = (212, 175, 55)
def _assets_dir():
    return str(_ASSETS_PATH)
def _asset_at(assets_dir, name):
    with Image.open(Path(assets_dir) / name) as source:
        source.load()
        return source.copy()
def render(spec, portrait_png):
    colour = spec.get("title_rgb") or GOLD
    base = _asset_at(_assets_dir(), "Back.png")
    if portrait_png is not None:
        with Image.open(io.BytesIO(portrait_png)) as p:
            p.load()
    return colour, base
'''
    assert _face_source_findings(src) == []


def _poison(engine, fired, statements):
    """The first statement that reads rank_role_colors is replaced by one
    PostgreSQL rejects on that session; every statement is recorded with the
    pooled connection it ran on."""
    def rewrite(conn, cursor, statement, parameters, context, executemany):
        if "rank_role_colors" in statement and not fired:
            fired.append(id(conn.connection))
            statements.append((id(conn.connection), "SELECT 1/0"))
            return "SELECT 1/0", ()
        statements.append((id(conn.connection), statement))
        return statement, parameters
    event.listen(engine.sync_engine, "before_cursor_execute", rewrite, retval=True)
    return rewrite


async def _pack_rows(env, pack):
    main = env.main
    async with env.database.async_session() as db:
        return [dict(r) for r in (await db.execute(
            text(main._pc_composite_row_sql("WHERE pr.pack_id = CAST(:pack AS uuid)")),
            {"pack": pack})).mappings().all()]


async def _coloured_pack(env):
    main = env.main
    owner, _subs, pack = await five(env)
    rows = await _pack_rows(env, pack)
    ranks = {main._pc_rank_name(main._pc_num(r["rating"])) for r in rows}
    assert ranks and None not in ranks, ranks
    for rank in ranks:
        await _set_colour(env, rank, "#FF00FF")
    return owner, pack, rows


async def _revs(env, pack, colors):
    main = env.main
    async with env.database.async_session() as db:
        ctx = await main._pc_face_ctx(db, "en")
        if colors is not None:
            ctx = dict(ctx, colors=colors)
        rows = (await db.execute(text(main._pc_composite_row_sql("WHERE pr.pack_id = CAST(:pack AS uuid)")),
                                 {"pack": pack})).mappings().all()
    return {int(r["slot"]): main._pc_face_inputs(r, ctx)[3] for r in rows}


def test_a_colour_table_failure_does_not_abort_a_composite(monkeypatch, tmp_path, capsys):
    async def body(env):
        main = env.main
        owner, pack, _prints = await _coloured_pack(env)
        coloured = await _revs(env, pack, None)
        fallback = await _revs(env, pack, {})
        assert coloured != fallback, "the fixture's colour rows do not move a face_rev"
        main._rank_colors_cache.update({"at": 0.0, "ok": False, "map": {}})
        fired, statements = [], []
        hook = _poison(env.database.engine, fired, statements)
        try:
            capsys.readouterr()
            r = await env.strip(pack, owner.discord)
        finally:
            event.remove(env.database.engine.sync_engine, "before_cursor_execute", hook)
        out = capsys.readouterr().out
        assert fired, "the colour read was never reached"
        assert "[RANK] color cache refresh failed" in out
        assert r.status_code == 200, (r.status_code, r.text[:200])
        assert main._rank_colors_cache["ok"] is False
        words = {int(e[0]): e[4] for e in manifest_of(r)}
        assert words == fallback, (words, fallback)
        after = [s for conn, s in statements[statements.index((fired[0], "SELECT 1/0")) + 1:] if conn == fired[0]]
        assert any("subject_id_ok" in s for s in after), "the row read did not run on the same session afterwards"
    live(monkeypatch, tmp_path, body)


def test_c25e_a_healthy_colour_table_still_colours_and_stamps_on_success(monkeypatch, tmp_path):
    async def body(env):
        main = env.main
        owner, pack, _prints = await _coloured_pack(env)
        coloured = await _revs(env, pack, None)
        main._rank_colors_cache.update({"at": 0.0, "ok": False, "map": {}})
        r = await env.strip(pack, owner.discord)
        assert r.status_code == 200
        assert {int(e[0]): e[4] for e in manifest_of(r)} == coloured
        assert main._rank_colors_cache["ok"] is True and main._rank_colors_cache["at"] > 0
    live(monkeypatch, tmp_path, body)


def test_c25e_the_bare_call_leaves_the_session_aborted(monkeypatch, tmp_path):
    async def body(env):
        import models
        from sqlalchemy import select
        fired, statements = [], []
        hook = _poison(env.database.engine, fired, statements)
        try:
            async with env.database.async_session() as db:
                with pytest.raises(Exception):
                    await db.execute(select(models.RankRoleColor))
                with pytest.raises(Exception) as ex:
                    await db.execute(text("SELECT 1"))
        finally:
            event.remove(env.database.engine.sync_engine, "before_cursor_execute", hook)
        chain, e = [], ex.value
        while e is not None and len(chain) < 8:
            chain.append(f"{type(e).__name__}: {e}")
            e = e.__cause__ or e.__context__
        assert any("aborted" in c or "InFailedSQLTransaction" in c for c in chain), chain
    live(monkeypatch, tmp_path, body)


def _magenta(png):
    data = H.image_of(png).tobytes()
    return sum(1 for i in range(0, len(data), 3) if data[i] > 225 and data[i + 1] < 40 and data[i + 2] > 225)


async def _face_with(env, monkeypatch, row, n, colors=None):
    main = env.main
    async with env.database.async_session() as db:
        ctx = await main._pc_face_ctx(db, "en")
        if colors is not None:
            ctx = dict(ctx, colors=colors)
        root = env.tmp / f"face{n}"
        root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(main, "_pc_face_cache", main._pcp.FaceCache(str(root)))
        return await main._pc_render_face(db, row, ctx, "card")


def test_the_face_context_carries_the_rank_colour_map(monkeypatch, tmp_path):
    async def body(env):
        main = env.main
        owner, _subs, pack = await five(env)
        pid = (await pack_prints(env, owner, pack))[0]["print_id"]
        async with env.database.async_session() as db:
            row = await _one_row(env, db, pid)
        rank = main._pc_rank_name(main._pc_num(row["rating"]))
        env.main._rank_colors_cache.update({"at": 0.0, "ok": False, "map": {}})
        rev_absent, png_absent = await _face_with(env, monkeypatch, row, 1)
        await _set_colour(env, rank, "#FF00FF")
        rev_row, png_row = await _face_with(env, monkeypatch, row, 2)
        print(f"magenta pixels: with the row {_magenta(png_row)}, without {_magenta(png_absent)}")
        assert _magenta(png_row) > 200 and _magenta(png_absent) == 0, (_magenta(png_row), _magenta(png_absent))
        assert rev_row != rev_absent
    live(monkeypatch, tmp_path, body)


def test_c25f_a_rank_with_no_row_renders_the_fallback_under_both_forms(monkeypatch, tmp_path):
    async def body(env):
        main = env.main
        owner, _subs, pack = await five(env)
        pid = (await pack_prints(env, owner, pack))[0]["print_id"]
        async with env.database.async_session() as db:
            row = await _one_row(env, db, pid)
        await _set_colour(env, "No Such Rank", "#FF00FF")
        rev_map, png_map = await _face_with(env, monkeypatch, row, 1)
        rev_empty, _png = await _face_with(env, monkeypatch, row, 2, colors={})
        assert rev_map == rev_empty
        assert _magenta(png_map) == 0
    live(monkeypatch, tmp_path, body)


# -- 25g, 28: the pool refuses a deleted or non-SteamID64 subject -------------------------

async def _admitted(env, who):
    return bool(await env.rows(env.main._PC_LIVE_POOL_CHECK_SQL, {"pid": who.id}))


def test_the_pool_still_refuses_a_deleted_or_non_steamid_subject(monkeypatch, tmp_path):
    async def body(env):
        subject = await env.player("subject", rating=1500.0)
        assert await _admitted(env, subject), "a live valid subject is refused"
        await env.ex(f"UPDATE {SCHEMA}.players SET deleted_at = now() WHERE id = CAST(:p AS uuid)", {"p": subject.id})
        assert not await _admitted(env, subject), "a deleted subject is admitted"
        anon = await env.player("anon", rating=1500.0)
        await set_steam(env, anon, "deleted_" + secrets.token_hex(4))
        assert not await _admitted(env, anon), "an anonymised deleted_ id is admitted"
    live(monkeypatch, tmp_path, body)


def test_c25g_the_live_valid_row_is_still_admitted(monkeypatch, tmp_path):
    async def body(env):
        subject = await env.player("subject", rating=1500.0)
        assert await _admitted(env, subject)
    live(monkeypatch, tmp_path, body)


async def open_raw(env, owner):
    """The production open with the PRODUCTION roll (no deal queued)."""
    nonce = secrets.token_hex(8)
    price = int(env.main._pc.PC_ECONOMY["pack_price_shards"])
    canon = env.main._pc.canon_open_purchase(owner.steam, nonce, "shards", price)
    return await env.client.post("/api/v1/pc/packs/open", headers=env.mod_headers(owner), params={
        "steam_id": owner.steam, "sig": H.mod_sig(canon), "nonce": nonce, "pay": "shards",
        "expected_price": price})


async def minted_of(env, who):
    return int(await env.val(
        f"SELECT count(*) FROM {SCHEMA}.pc_prints pr JOIN {SCHEMA}.pc_cards c ON c.id = pr.card_id"
        " WHERE c.subject_player_id = CAST(:p AS uuid)", {"p": who.id}))


async def _pool_of_one(env, snap, who):
    """The snapshot narrowed to `who` alone, in the lowest band: every band
    roll falls back to it, so the open's roll reaches exactly this member and
    the live re-check it applies per slot decides the pack."""
    await env.ex(f"DELETE FROM {SCHEMA}.pc_pool_members WHERE snapshot_id = CAST(:s AS integer)"
                 " AND player_id <> CAST(:p AS uuid)", {"s": snap, "p": who.id})
    await env.ex(f"UPDATE {SCHEMA}.pc_pool_members SET rarity = 'common' WHERE snapshot_id = CAST(:s AS integer)",
                 {"s": snap})
    members = await env.rows(f"SELECT player_id::text AS p FROM {SCHEMA}.pc_pool_members"
                             " WHERE snapshot_id = CAST(:s AS integer)", {"s": snap})
    assert [m["p"] for m in members] == [who.id], members


def test_a_deleted_subject_cannot_be_minted(monkeypatch, tmp_path):
    async def body(env):
        purged = await env.player("purged", rating=1500.0)
        owner = await env.player("owner", rating=None)
        await _pool_of_one(env, await env.snapshot(), purged)
        await env.ex(f"UPDATE {SCHEMA}.players SET deleted_at = now() WHERE id = CAST(:p AS uuid)", {"p": purged.id})
        r = await open_raw(env, owner)
        print(f"open with a purged-only pool: HTTP {r.status_code} {r.text[:160]}")
        assert await minted_of(env, purged) == 0, "a purged subject was minted"
        assert r.status_code == 409 and r.json()["detail"]["error"] == "pool_changed", (r.status_code, r.text[:200])
    live(monkeypatch, tmp_path, body)


def test_c28_a_live_pool_member_is_still_minted(monkeypatch, tmp_path):
    async def body(env):
        member = await env.player("member", rating=1500.0)
        owner = await env.player("owner", rating=None)
        await _pool_of_one(env, await env.snapshot(), member)
        r = await open_raw(env, owner)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        assert await minted_of(env, member) == 5
    live(monkeypatch, tmp_path, body)


# -- 26, 26b, 26c, 26d: the manifest and the composite statement --------------------------

BRANCH_POINT = "bb7d716957d735ebf781e0d2c14defb5f18fe39c"
NEW_ROUTES = {"internal_pc_packs", "internal_pc_pack_strip", "internal_pc_binder", "internal_pc_binder_page"}
# The existing bindings this branch is expected to change, each named where
# it is recorded: S13's savepoint and its success-only stamp (_rank_colors and
# the cache's "ok" key; build notes FINDING 1) and B11's marker, its two
# health_check arms and its schema field (FINDING 2).
EXPECTED_CHANGED = {("main", "_rank_colors"), ("main", "_rank_colors_cache"), ("main", "health_check"),
                    ("main", "_DISCORD_COLLECTION_MARKER"), ("schemas", "HealthResponse")}


def _git(*args):
    root = Path(__file__).resolve().parents[2]
    return subprocess.run(["git", "-C", str(root)] + list(args), capture_output=True, check=True).stdout


def _branch_point_index(tmp_path, gate):
    names = [n for n in _git("ls-tree", "--name-only", BRANCH_POINT, "backend/api/").decode().split()
             if n.endswith(".py")]
    out = {}
    for rel in names:
        p = tmp_path / Path(rel).name
        p.write_bytes(_git("show", f"{BRANCH_POINT}:{rel}"))
        out[p.stem] = gate._index_module(p)
    return out


def _route_surface():
    tests = Path(__file__).resolve().parent
    if str(tests) not in sys.path:
        sys.path.insert(0, str(tests))
    import test_route_manifest_net_seat as gate
    return gate


def _live_routes(gate):
    """{(path, methods, module, qualname): route}, enumerated as the gate does."""
    from fastapi.routing import APIRoute, APIWebSocketRoute
    from starlette.routing import Mount
    out = {}

    def walk(routes, prefix=""):
        for route in routes:
            if isinstance(route, Mount):
                walk(route.routes, gate._joined_path(prefix, route.path))
                continue
            if not isinstance(route, (APIRoute, APIWebSocketRoute)):
                continue
            path = gate._joined_path(prefix, route.path)
            if path.startswith("/api/v1/"):
                out[(path, tuple(sorted(getattr(route, "methods", ()) or ())), route.endpoint.__module__,
                     route.endpoint.__qualname__)] = route
    walk(gate.main.app.routes)
    return out


def _changed_for(gate, seeds, old_index):
    """The bindings whose presence or text differs between the branch point's
    closure of `seeds` and today's: exactly what moves their fingerprint."""
    new = set(gate._reached(seeds))
    old = set(gate._walk_bindings(seeds, index=old_index))
    diff = new ^ old
    for module, name in new & old:
        if old_index[module][name][1] != gate._segment(module, name):
            diff.add((module, name))
    return diff


def test_only_the_four_new_routes_move_in_the_route_manifest(tmp_path):
    """REBUILT at binding level (build notes, row 26): on this base every
    route that reaches _PC_PRINT_FACE_SELECT also reaches _rank_colors, whose
    savepoint (S13) the branch carries, so the ROUTE moved set cannot tell a
    column added to the face select from the savepoint. The branch point's
    own index and manifest are read from git, and the assertion is that the
    set of existing bindings the branch changed is exactly the recorded one,
    that the new routes are exactly the four, and that the recorded
    fingerprints moved for exactly the routes and entry points that reach a
    changed binding."""
    gate = _route_surface()
    old_doc = json.loads(_git("show", f"{BRANCH_POINT}:backend/tests/route_manifest_net_seat.json"))
    old_ids = {(r[0], tuple(r[1]), r[2], r[3]) for g in old_doc["groups"] for r in g["routes"]}
    old_sha = {(r[0], tuple(r[1]), r[2], r[3]): r[4] for g in old_doc["groups"] for r in g["routes"] if len(r) > 4}
    routes = _live_routes(gate)
    new = {k for k in routes if k not in old_ids}
    assert {k[3] for k in new} == NEW_ROUTES and len(new) == 4, sorted(new)
    old_index = _branch_point_index(tmp_path, gate)
    changed, per_route = set(), {}
    for key, route in routes.items():
        if key in new:
            continue
        per_route[key] = _changed_for(gate, gate._route_seeds(route), old_index)
        changed |= per_route[key]
    per_entry = {}
    for section, rows_ in old_doc["entry_points"].items():
        for module, name, sha in rows_:
            per_entry[(module, name)] = (sha, _changed_for(gate, [(module, name)], old_index))
            changed |= per_entry[(module, name)][1]
    assert changed == EXPECTED_CHANGED, f"existing bindings changed on the branch: {sorted(changed)}"
    live_sha = {(e["path"], tuple(e["methods"]), e["module"], e["qualname"]): e["source_sha1"]
                for e in gate._route_identities(gate.main.app.routes)}
    moved = {k for k, sha in old_sha.items() if live_sha[k] != sha}
    expected = {k for k, c in per_route.items() if c and k in old_sha}
    assert moved == expected, (sorted(moved - expected), sorted(expected - moved))
    ep_moved = {k for k, (sha, _c) in per_entry.items() if gate._entry_point_sha(*k) != sha}
    ep_expected = {k for k, (_sha, c) in per_entry.items() if c}
    assert ep_moved == ep_expected, (sorted(ep_moved), sorted(ep_expected))
    print(f"ROW26 new routes: {sorted(k[3] for k in new)}")
    print(f"ROW26 changed existing bindings: {sorted(changed)}")
    print(f"ROW26 existing fingerprinted routes moved: {len(moved)}; entry points moved: {sorted(ep_moved)}")


def test_c26_the_new_route_set_is_still_exactly_the_four():
    gate = _route_surface()
    old_doc = json.loads(_git("show", f"{BRANCH_POINT}:backend/tests/route_manifest_net_seat.json"))
    old_ids = {(r[0], tuple(r[1]), r[2], r[3]) for g in old_doc["groups"] for r in g["routes"]}
    live_ids = {(e["path"], tuple(e["methods"]), e["module"], e["qualname"])
                for e in gate._route_identities(gate.main.app.routes)}
    assert {k[3] for k in live_ids - old_ids} == NEW_ROUTES
    assert old_ids - live_ids == set(), "a route pinned at the branch point is gone"


_BINDER_WHERE = "WHERE pr.owner_player_id = CAST(:owner AS uuid) AND pr.discarded_at IS NULL"


def test_the_composite_wrap_states_no_order_and_preserves_the_row_set(monkeypatch, tmp_path):
    async def body(env):
        main = env.main
        subs = await H.pool(env, 5)
        owner = await env.player("owner", rating=None)
        await env.snapshot()
        await env.open_pack(owner, subs)
        await env.open_pack(owner, subs)
        wrapped = main._pc_composite_row_sql(_BINDER_WHERE)
        own = wrapped.replace(main._PC_PRINT_FACE_SELECT, " ").replace(_BINDER_WHERE, " ")
        assert main._PC_PRINT_FACE_SELECT in wrapped and _BINDER_WHERE in wrapped
        assert not re.search(r"\bORDER\s+BY\b|\bLIMIT\b|\bOFFSET\b", own, re.I), own
        inner = [m.start() for m in re.finditer(r"\bORDER\s+BY\b", main._PC_PRINT_FACE_SELECT, re.I)]
        assert len(inner) == 1 and "array_agg(si.sku ORDER BY si.sku)" in main._PC_PRINT_FACE_SELECT
        assert not re.search(r"\bLIMIT\b|\bOFFSET\b", main._PC_PRINT_FACE_SELECT, re.I)
        w = await env.rows(wrapped, {"owner": owner.id})
        b = await env.rows(main._PC_PRINT_FACE_SELECT + " " + _BINDER_WHERE, {"owner": owner.id})
        assert len(w) == len(b) == 10, (len(w), len(b))
        assert list(w[0].keys()) == list(b[0].keys()) + ["subject_id_ok"], list(w[0].keys())[-3:]
        assert sorted(str(r["print_id"]) for r in w) == sorted(str(r["print_id"]) for r in b)
    live(monkeypatch, tmp_path, body)


def test_c26b_the_pack_form_still_returns_every_row_of_its_pack(monkeypatch, tmp_path):
    async def body(env):
        main = env.main
        owner, _subs, pack = await five(env)
        rows = await env.rows(main._pc_composite_row_sql("WHERE pr.pack_id = CAST(:pack AS uuid)"), {"pack": pack})
        want = {p["print_id"] for p in await pack_prints(env, owner, pack)}
        assert {str(r["print_id"]) for r in rows} == want
    live(monkeypatch, tmp_path, body)


def _record_texts(engine, out):
    def before(conn, clauseelement, multiparams, params, execution_options):
        t = getattr(clauseelement, "text", None)
        if isinstance(t, str) and "subject_id_ok" in t:
            out.append((t, dict(params or (multiparams[0] if multiparams else {}) or {})))
    event.listen(engine.sync_engine, "before_execute", before)
    return before


def test_the_composite_statement_is_assembled_and_runs(monkeypatch, tmp_path):
    async def body(env):
        owner, _subs, pack = await five(env)
        sent = []
        hook = _record_texts(env.database.engine, sent)
        try:
            forms = {}
            r = await env.strip(pack, owner.discord)
            assert r.status_code == 200, (r.status_code, r.text[:200])
            forms["strip"] = sent[-1]
            r = await env.packs_json(owner.discord, pack)
            assert r.status_code == 200, (r.status_code, r.text[:200])
            forms["pack read"] = sent[-1]
            r = await env.binder_json(owner.discord, owner.discord)
            assert r.status_code == 200, (r.status_code, r.text[:200])
            forms["binder"] = sent[-1]
        finally:
            event.remove(env.database.engine.sync_engine, "before_execute", hook)
        assert forms["binder"][0].startswith("WITH live AS MATERIALIZED"), forms["binder"][0][:60]
        for name, (sql, binds) in forms.items():
            assert "{17}" in sql, name
            assert "{where}" not in sql, name
            got = await env.rows(sql, binds)
            want = 5
            assert len(got) == want, (name, len(got))
    live(monkeypatch, tmp_path, body)


def test_c26c_a_brace_free_statement_still_formats(monkeypatch, tmp_path):
    async def body(env):
        main = env.main
        sql = (main._PC_PRINT_FACE_SELECT + " {where} ").format(where="WHERE false")
        assert await env.rows(sql) == []
    live(monkeypatch, tmp_path, body)


def _depth_at(sql, pos):
    depth, quoted = 0, False
    for ch in sql[:pos]:
        if ch == "'":
            quoted = not quoted
        elif not quoted and ch == "(":
            depth += 1
        elif not quoted and ch == ")":
            depth -= 1
    return depth


_SIX = ("CASE {q}rarity", "{q}signed DESC", "{q}foil DESC", "{q}pool_rank", "{q}minted_at", "{q}print_id")


def _terms_in_order(clause, q):
    at = 0
    for term in _SIX:
        i = clause.find(term.format(q=q), at)
        if i < 0:
            return False
        at = i + 1
    return True


async def _twelve(env):
    subs = await H.pool(env, 5)
    owner = await env.player("owner", rating=None)
    await env.snapshot()
    prints = []
    for _ in range(3):
        prints += await pack_prints(env, owner, await env.open_pack(owner, subs))
    for p in prints[-3:]:
        await env.discard(owner, p["print_id"])
    return owner


async def _two_plans(env, owner):
    main = env.main
    async with env.database.async_session() as a:
        _m, rows_a = await main._pc_binder_page(a, owner.id, 1)
    async with env.database.async_session() as b:
        await b.execute(text("SET LOCAL enable_indexscan = off"))
        await b.execute(text("SET LOCAL enable_bitmapscan = off"))
        _m, rows_b = await main._pc_binder_page(b, owner.id, 1)
    return [str(r["print_id"]) for r in rows_a], [str(r["print_id"]) for r in rows_b]


def test_the_binder_statement_restates_its_order_at_depth_zero(monkeypatch, tmp_path):
    async def body(env):
        main = env.main
        sql = main._pc_binder_page_sql()
        spots = [m.start() for m in re.finditer(r"ORDER BY", sql)]
        last = spots[-1]
        assert _depth_at(sql, last) == 0, f"the last ORDER BY sits at parenthesis depth {_depth_at(sql, last)}, not 0"
        assert _terms_in_order(sql[last:], "p."), sql[last:]
        page = sql.index("page AS (")
        page_order = next(s for s in spots if s > page)
        assert _depth_at(sql, page_order) == 1
        assert _terms_in_order(sql[page_order:sql.index("LIMIT", page_order)], ""), sql[page_order:page_order + 200]
        owner = await _twelve(env)
        seq_a, seq_b = await _two_plans(env, owner)
        assert len(seq_a) == 10 and seq_a == seq_b, (seq_a, seq_b)
        answer = await binder_prints(env, owner)
        r = await env.binder_page(owner.id, 1, owner.discord)
        assert [p["print_id"] for p in answer["prints"]] == seq_a
        assert [e[1] for e in manifest_of(r, "x-grid-slots")] == [s.replace("-", "") for s in seq_a]
    live(monkeypatch, tmp_path, body)


def test_c26d_the_intact_statement_returns_one_sequence_under_both_plans(monkeypatch, tmp_path):
    async def body(env):
        owner = await _twelve(env)
        seq_a, seq_b = await _two_plans(env, owner)
        assert len(seq_a) == 10 and seq_a == seq_b
    live(monkeypatch, tmp_path, body)


# -- 27: the layout formula ------------------------------------------------------------------

def test_composite_rects_come_from_the_layout_formula():
    import pc_strip
    for cols, rows in ((5, 1), (5, 2)):
        boxes = pc_strip.strip_paste_boxes(cols, rows)
        want = [H.slot_rect(i, cols) for i in range(1, cols * rows + 1)]
        assert boxes == want, [(i + 1, b, w) for i, (b, w) in enumerate(zip(boxes, want)) if b != w]


def test_c27_the_formula_canvases_still_match_the_rendered_sizes():
    import pc_strip
    for rows, size in ((1, (1947, 549)), (2, (1947, 1086))):
        assert pc_strip.strip_canvas_size(5, rows) == size
        data = pc_strip.compose_composite([("back", None, False)] * (5 * rows), 5, rows, 8 << 20)
        assert H.image_of(data).size == size


# -- end of part 3 --
