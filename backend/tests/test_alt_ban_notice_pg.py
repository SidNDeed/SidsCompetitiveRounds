"""ALT-BAN-1 step 7 (A7): the notice to the admins, main.ban_link_notice_pass
and its loop, over planted rows of the lane's tables and migration 431's.

A pair is (an actively banned account, another account) where the other
account recorded an ADDRESS code after the ban began that the banned account
recorded too. Stored in its own transaction before any post; posted with
the fewest accounts on the code first, then the oldest; at most 20 posts a
UTC day; the other account's identity key taken by a try-lock; never for an
other account under an active ban; a block code or a family share alone is
no pair; names from the live players row or "no name", never the name kept
with a ban. With the channel setting unset or 0, pairs are stored, none is
posted, and the pass's line says "storing" (the positive signal).

Every id, name, channel and mark is invented."""
import asyncio
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for p in (API, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest  # noqa: E402

import main  # noqa: E402
import alt_signals as A  # noqa: E402
import test_ban_record_pg as BR  # noqa: E402
import test_alt_ban_links_pg as L  # noqa: E402
import test_alt_signals_record_pg as R  # noqa: E402
from inv_pg import case  # noqa: E402

CHANNEL = "4242424242"


async def _posts(env):
    return [r["content"] for r in await env.conn.fetch(
        "SELECT content FROM pending_channel_posts WHERE channel_id = $1 ORDER BY id", CHANNEL)]


async def _notices(env):
    return {(r["banned_steam_id"], r["other_steam_id"]): r["posted_at"] for r in await env.conn.fetch(
        "SELECT banned_steam_id, other_steam_id, posted_at FROM ban_link_notices")}


async def _pair_world(env, c, admin, others=1, code="home"):
    """A banned account B with one address code, then `others` accounts on it
    after the ban."""
    b = await env.player("Notice Banned")
    await L._marker(env, b.sid, code, "blk-" + code, 3, first_days_ago=5)
    await BR._ban(c, admin, b.sid)
    out = []
    for i in range(others):
        o = await env.player("Notice Other %02d" % i)
        await L._marker(env, o.sid, code, "blk-" + code, 0)
        out.append(o)
    return b, out


def _setup(env, channel):
    BR._open(env)
    L._keyed(env)
    if channel is None:
        env.mp.delenv(main._BAN_NOTICE_CHANNEL_ENV, raising=False)
    else:
        env.mp.setenv(main._BAN_NOTICE_CHANNEL_ENV, channel)


@pytest.mark.parametrize("channel", [None, "0"])
def test_unset_or_zero_stores_posts_none_and_the_line_says_storing(monkeypatch, channel):
    out = {}

    async def body(env):
        _setup(env, channel)
        await L._notice(env)
        admin = await BR._admin(env)
        said = []
        env.mp.setattr(main, "_alt_print", said.append)
        env.mp.setattr(main, "_BAN_NOTICE_FIRST_DELAY_S", 0)
        async with BR._client(env) as c:
            b, (o,) = await _pair_world(env, c, admin)
            task = asyncio.get_running_loop().create_task(main.ban_link_notice_loop(session_factory=env.sm))
            try:
                for _n in range(200):
                    if any("notice pass:" in s for s in said):
                        break
                    await asyncio.sleep(0.05)
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            again = await main.ban_link_notice_pass(env.sm)
            out.update(said=said, notices=await _notices(env), posts=await _posts(env), again=again,
                       pair=(b.sid, o.sid), any_post=await env.conn.fetchval(
                           "SELECT count(*) FROM pending_channel_posts WHERE content LIKE '%Linked to a banned%'"))
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    assert out["said"][0] == "[ALT-BAN] notice pass armed: channel unset", out["said"]
    assert "[ALT-BAN] notice pass: storing, stored 1, posted 0, busy 0" in out["said"], out["said"]
    assert out["notices"] == {out["pair"]: None}, out
    assert out["posts"] == [] and out["any_post"] == 0, out
    assert (out["again"]["stored"], out["again"]["posted"], out["again"]["channel"]) == (0, 0, False), out


def test_fewest_sharing_first_then_oldest_and_twenty_a_utc_day(monkeypatch):
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            b = await env.player("Notice Banned")
            for i in range(22):
                await L._marker(env, b.sid, "code-%d" % i, "blk-%d" % i, 3, first_days_ago=5)
            await BR._ban(c, admin, b.sid)
            others = []
            for i in range(22):
                o = await env.player("Notice Other %02d" % i)
                await L._marker(env, o.sid, "code-%d" % i, "blk-o-%d" % i, 0)
                others.append(o)
            # codes 2..21 carry one more account, itself banned after the others' rows: three on the code
            for i in range(2, 22):
                f = await env.player("Notice Filler %02d" % i)
                await L._marker(env, f.sid, "code-%d" % i, "blk-f-%d" % i, 0)
                await L._ban_row(env, admin, f.sid)
            env.mp.delenv(main._BAN_NOTICE_CHANNEL_ENV)
            first = await main.ban_link_notice_pass(env.sm)
            env.mp.setenv(main._BAN_NOTICE_CHANNEL_ENV, CHANNEL)
            # the two pairs on codes of two accounts are the newest; among the rest, the higher i the older
            for i, o in enumerate(others):
                await env.conn.execute(
                    "UPDATE ban_link_notices SET noticed_at = now() - make_interval(mins => $1::int)"
                    " WHERE other_steam_id = $2", 0 if i < 2 else i * 2, o.sid)
            second = await main.ban_link_notice_pass(env.sm)
            third = await main.ban_link_notice_pass(env.sm)
            posted_after_two = {k[1] for k, v in (await _notices(env)).items() if v is not None}
            await env.conn.execute("UPDATE ban_link_notices SET posted_at = posted_at - interval '1 day'"
                                   " WHERE posted_at IS NOT NULL")
            fourth = await main.ban_link_notice_pass(env.sm)
            out.update(first=first, second=second, third=third, fourth=fourth, posted=posted_after_two,
                       others=[o.sid for o in others], posts=await _posts(env), notices=await _notices(env))
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    o = out["others"]
    assert (out["first"]["stored"], out["first"]["posted"]) == (22, 0), out["first"]
    assert out["second"]["posted"] == 20 and out["third"]["posted"] == 0, (out["second"], out["third"])
    assert out["posted"] == set(o[:2]) | set(o[4:22]), sorted(o.index(s) for s in out["posted"])
    assert out["fourth"]["posted"] == 2 and len(out["posts"]) == 22, out["fourth"]
    assert all(v is not None for v in out["notices"].values()), out["notices"]


def test_names_are_the_live_rows_or_no_name_never_the_kept_name(monkeypatch):
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            b, (o, gone) = await _pair_world(env, c, admin, others=2)
            await env.conn.execute("UPDATE player_bans SET display_name_at_ban = 'Kept Name Qx' WHERE steam_id = $1",
                                   b.sid)
            await env.conn.execute("UPDATE players SET display_name = 'Live *Name* Bx' WHERE steam_id = $1", b.sid)
            await env.conn.execute("UPDATE players SET deleted_at = now() WHERE steam_id = $1", gone.sid)
            got = await main.ban_link_notice_pass(env.sm)
            out.update(got=got, posts=await _posts(env), b=b.sid, o=o.sid, gone=gone.sid, kid=A.loaded_key().key_id)
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    text_ = "\n".join(out["posts"])
    # A4 for the post rows: no key, key id, mark or address form in a post.
    for word in [R.KEY_HEX, out["kid"]] + [L._m(x).hex() for x in ("home", "blk-home")]:
        assert word not in text_, word
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text_) and "::" not in text_, text_
    assert out["got"]["posted"] == 2 and len(out["posts"]) == 2, out
    assert "Kept Name Qx" not in text_, text_
    assert "Live \\*Name\\* Bx" in text_ and "Notice Other 00" in text_, text_
    by_other = {p.split("`")[1]: p for p in out["posts"]}
    assert by_other[out["gone"]].startswith("Linked to a banned account: **no name**"), by_other[out["gone"]]


def test_never_for_a_banned_other_nor_a_block_or_family_link_alone(monkeypatch):
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            b, (o_banned,) = await _pair_world(env, c, admin)
            await BR._ban(c, admin, o_banned.sid)
            blk = await env.player("Notice Block Only")
            await L._marker(env, blk.sid, "elsewhere", "blk-home", 0)
            fam = await env.player("Notice Family Only")
            await L._share(env, b.sid, L._account(fam.sid), 1)
            await L._share(env, fam.sid, L._account(fam.sid), 0)
            before = await env.player("Notice Before The Ban")
            await env.conn.execute(
                "INSERT INTO conn_markers (steam_id, day, key_id, addr_mark, block_mark, family, conn_class,"
                " first_at, last_at) VALUES ($1, CAST((now() AT TIME ZONE 'UTC') AS date) - 4, $2, $3, $4, 4,"
                " 'none', now() - interval '4 days', now() - interval '4 days')",
                before.sid, A.loaded_key().key_id, L._m("home"), L._m("blk-home"))
            got = await main.ban_link_notice_pass(env.sm)
            out.update(got=got, notices=await _notices(env), posts=await _posts(env))
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    assert out["notices"] == {} and out["posts"] == [] and out["got"]["stored"] == 0, out


def test_the_other_accounts_key_held_is_busy_and_nothing_is_written(monkeypatch):
    out = {}

    async def body(env):
        _setup(env, None)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            b, (o,) = await _pair_world(env, c, admin)
            side = await env.side()
            tr = side.transaction()
            await tr.start()
            await side.execute("SELECT pg_advisory_xact_lock(hashtext(CAST($1 AS text)))", o.sid)
            held = await main.ban_link_notice_pass(env.sm)
            out["held_rows"] = await _notices(env)
            await tr.rollback()
            free = await main.ban_link_notice_pass(env.sm)
            out.update(held=held, free=free, rows=await _notices(env), pair=(b.sid, o.sid))
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    assert (out["held"]["busy"], out["held"]["stored"]) == (1, 0) and out["held_rows"] == {}, out
    assert out["free"]["stored"] == 1 and out["rows"] == {out["pair"]: None}, out


def test_stored_before_posted_and_posted_once(monkeypatch):
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            b, (o,) = await _pair_world(env, c, admin)
            with env.rewriting("INSERT INTO pending_channel_posts (channel_id, content)",
                               "INSERT INTO pending_channel_posts_absent (channel_id, content)") as hits:
                try:
                    await main.ban_link_notice_pass(env.sm)
                    out["raised"] = None
                except Exception as ex:
                    out["raised"] = type(ex).__name__
            out["hits"] = len(hits)
            out["after_fault"] = await _notices(env)
            ok = await main.ban_link_notice_pass(env.sm)
            again = await main.ban_link_notice_pass(env.sm)
            out.update(ok=ok, again=again, posts=await _posts(env), pair=(b.sid, o.sid))
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    assert out["raised"] is not None and out["hits"] == 1, out
    assert out["after_fault"] == {out["pair"]: None}, out
    assert (out["ok"]["stored"], out["ok"]["posted"], out["again"]["posted"]) == (0, 1, 0), out
    assert len(out["posts"]) == 1 and out["pair"][1] in out["posts"][0], out


def test_no_key_or_the_notice_closed_is_no_pass(monkeypatch):
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env, posted=False)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            await _pair_world(env, c, admin)
            closed = await main.ban_link_notice_pass(env.sm)
            await L._notice(env)
            A.install_key(None)
            nokey = await main.ban_link_notice_pass(env.sm)
            out.update(closed=closed, nokey=nokey, rows=await _notices(env))
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    assert out["closed"]["stored"] == 0 and out["nokey"]["stored"] == 0 and out["rows"] == {}, out


def test_the_loop_starts_beside_the_retention_pass_on_the_primary_only():
    src = open(os.path.join(API, "main.py"), encoding="utf-8").read()
    line = [ln for ln in src.splitlines() if '_supervised("ban_link_notice", ban_link_notice_loop)' in ln]
    assert len(line) == 1 and '_supervised("alt_signals_retention", alt_signals_retention_loop)' in line[0], line
    assert src.count("ban_link_notice_loop") == 2, "the loop is defined once and started from one place"


# -- fix 1 of the item's round (H3, H4, M1, M3) ----------------------------------------------------

def test_a_posted_pair_is_posted_once_over_the_whole_ban(monkeypatch):
    """H4: the other account's markers run out and the retention takes them
    between two of its connections while the ban stands: the posted pair
    stays, and it is not posted again."""
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            b, (o,) = await _pair_world(env, c, admin)
            first = await main.ban_link_notice_pass(env.sm)
            await env.conn.execute("UPDATE conn_markers SET last_at = now() - interval '100 days',"
                                   " first_at = now() - interval '100 days' WHERE steam_id = $1", o.sid)
            await main._alt_retention_pass(env.sm)
            out["markers_left"] = await env.conn.fetchval("SELECT count(*) FROM conn_markers WHERE steam_id = $1",
                                                          o.sid)
            out["kept"] = await _notices(env)
            await L._marker(env, o.sid, "home", "blk-home", 0)
            second = await main.ban_link_notice_pass(env.sm)
            out.update(first=first, second=second, posts=await _posts(env), pair=(b.sid, o.sid))
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    assert out["first"]["posted"] == 1 and out["markers_left"] == 0, out
    assert list(out["kept"]) == [out["pair"]] and out["kept"][out["pair"]] is not None, out["kept"]
    assert out["second"]["posted"] == 0 and len(out["posts"]) == 1, (out["second"], out["posts"])


async def _pairs(env, c, admin, n, label):
    """A banned account and `n` accounts that recorded its code `label` after
    the ban; returns (banned, others)."""
    banned = await env.player("Notice Day %s" % label)
    await L._marker(env, banned.sid, label, "blk-" + label, 3, first_days_ago=5)
    await BR._ban(c, admin, banned.sid)
    others = []
    for i in range(n):
        o = await env.player("Notice Day %s %02d" % (label, i))
        await L._marker(env, o.sid, label, "blk-o-" + label, 0)
        others.append(o)
    return banned, others


async def _stored(env):
    """One pass with the channel unset (pairs stored, none posted); the channel set again after it."""
    env.mp.delenv(main._BAN_NOTICE_CHANNEL_ENV)
    got = await main.ban_link_notice_pass(env.sm)
    env.mp.setenv(main._BAN_NOTICE_CHANNEL_ENV, CHANNEL)
    return got


def test_pairs_are_ranked_by_their_qualifying_codes_alone(monkeypatch):
    """M1: a code the two accounts shared only before the ban does not rank the pair."""
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            b = await env.player("Rank Banned")
            for code in ("rare", "pop", "mid"):
                await L._marker(env, b.sid, code, "blk-" + code, 3, first_days_ago=5)
            await BR._ban(c, admin, b.sid)
            o1, o2 = await env.player("Rank One"), await env.player("Rank Two")
            await L._marker(env, o1.sid, "rare", "blk-rare-o", 2)      # before the ban: not qualifying
            await L._marker(env, o1.sid, "pop", "blk-pop-o", 0)
            await L._marker(env, o2.sid, "mid", "blk-mid-o", 0)
            for i, code in enumerate(("pop", "pop", "pop", "mid")):
                f = await env.player("Rank Filler %d" % i)
                await L._marker(env, f.sid, code, "blk-f-%d" % i, 0)
                await L._ban_row(env, admin, f.sid)
            await _stored(env)
            env.mp.setattr(main, "_BAN_NOTICE_DAY_CAP", 1)
            got = await main.ban_link_notice_pass(env.sm)
            out.update(got=got, notices=await _notices(env), o1=o1.sid, o2=o2.sid, posts=await _posts(env))
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    posted = [k[1] for k, v in out["notices"].items() if v is not None]
    assert out["got"]["posted"] == 1 and posted == [out["o2"]], (posted, out["o1"], out["o2"])
    assert "Accounts seen on that connection: 3." in out["posts"][0], out["posts"]


@pytest.mark.parametrize("closed", ["no key", "notice not acknowledged"])
def test_the_line_says_storing_when_the_posting_gate_is_closed(monkeypatch, closed):
    """M3: the channel set and the posting gate closed: the pass's line says storing."""
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env, posted=closed != "notice not acknowledged")
        admin = await BR._admin(env)
        said = []
        env.mp.setattr(main, "_alt_print", said.append)
        env.mp.setattr(main, "_BAN_NOTICE_FIRST_DELAY_S", 0)
        async with BR._client(env) as c:
            await _pair_world(env, c, admin)
            if closed == "no key":
                A.install_key(None)
            task = asyncio.get_running_loop().create_task(main.ban_link_notice_loop(session_factory=env.sm))
            try:
                for _n in range(200):
                    if any("notice pass:" in s for s in said):
                        break
                    await asyncio.sleep(0.05)
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            out.update(said=said, posts=await _posts(env))
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    lines = [s for s in out["said"] if "notice pass:" in s]
    assert lines and lines[0].startswith("[ALT-BAN] notice pass: storing,"), out["said"]
    assert out["posts"] == [], out
