"""ALT-BAN-1 step 7 (A7): the notice to the admins, main.ban_link_notice_pass
and its loop, over planted rows of the lane's tables and migration 431's.

A pair is (an actively banned account, another account) where the other
account recorded an ADDRESS code after the ban began that the banned account
recorded too. Stored in its own transaction before any post; posted with
the fewest accounts on a qualifying code (recorded after the ban began)
first, then the oldest; at most 20 posts a UTC day, counted in
ban_notice_days: each post takes a slot of the day by one statement inside
the pair's own transaction, so two passes at once, an account deletion or a
retention pass cannot raise the day past 20, a post row that fails to
commit gives its slot back, a pass on an engine of one connection still
posts, and a slot held past the lock limit makes the pair "busy" with
nothing written; a posted pair is kept while the ban stands, so it
is posted once over the ban; the other account's identity key taken by a
try-lock; never for an
other account under an active ban; a block code or a family share alone is
no pair; names from the live players row or "no name", never the name kept
with a ban. With the channel setting unset or 0, pairs are stored, none is
posted, and the pass's line says "storing"; it says "posting" only with
the channel set and the gate open (a key loaded, the notice acknowledged).
The loop is started on the primary only, shown by running lifespan's role
branch both ways.

Every id, name, channel and mark is invented."""
import asyncio
import datetime
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for p in (API, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import ladder_pg_harness as harness  # noqa: E402
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
            # the next UTC day: the day's count moved back one day (fix 1, H3: the allowance is that count)
            await env.conn.execute("UPDATE ban_notice_days SET day = day - 1")
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
    """Fix 1, M9, by behaviour: lifespan's role branch (its `if IS_REPLICA:`
    statement, the code itself) is RUN with every name it reads stood in
    for, once as the standby and once as the primary; what it hands to
    _supervised is recorded. The notice loop is started once on the primary,
    beside the retention loop, and never on the standby. A start moved
    outside the branch is started by neither run."""
    import ast as _ast
    import inspect as _inspect
    import textwrap as _textwrap

    tree = _ast.parse(_textwrap.dedent(_inspect.getsource(main.lifespan)))
    branch = [n for n in _ast.walk(tree) if isinstance(n, _ast.If) and isinstance(n.test, _ast.Name)
              and n.test.id == "IS_REPLICA"]
    assert len(branch) == 1, "lifespan has one `if IS_REPLICA:` branch"
    probe = _ast.Module(body=[_ast.AsyncFunctionDef(
        name="_probe", args=_ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
        body=[branch[0]], decorator_list=[], returns=None, type_params=[])], type_ignores=[])
    code = compile(_ast.fix_missing_locations(probe), "<lifespan role branch>", "exec")

    class Any:
        """Every other name: callable, awaitable, a context manager, each attribute itself."""
        def __call__(self, *a, **k):
            return self

        def __getattr__(self, n):
            if n.startswith("__"):
                raise AttributeError(n)
            return self

        def __await__(self):
            if False:
                yield
            return self

        def __iter__(self):
            return iter(())

    names = {n.id for n in _ast.walk(branch[0]) if isinstance(n, _ast.Name)}

    def run(replica):
        started = []
        loops = {"ban_link_notice_loop": object(), "alt_signals_retention_loop": object()}

        def supervised(name, factory):
            started.append((name, next((k for k, v in loops.items() if v is factory), None)))
            return Any()
        g = {n: Any() for n in names}
        g.update(loops, IS_REPLICA=replica, _supervised=supervised, tasks=[], print=lambda *a, **k: None,
                 __builtins__=__builtins__)
        exec(code, g)
        asyncio.run(g["_probe"]())
        return started

    primary, standby = run(False), run(True)
    assert primary.count(("ban_link_notice", "ban_link_notice_loop")) == 1, primary
    assert ("alt_signals_retention", "alt_signals_retention_loop") in primary, primary
    assert not [s for s in standby if s[1] is not None], standby
    src = open(os.path.join(API, "main.py"), encoding="utf-8").read()
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


def test_two_passes_at_once_post_at_most_twenty_in_a_utc_day(monkeypatch):
    """H3: pass B has read the day's allowance and stands before its read of
    the due pairs; pass A posts one pair; then B reads the due pairs and
    both post. Together they post at most twenty in the UTC day."""
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            await _pairs(env, c, admin, 24, "both")
            await _stored(env)
            real, b_at_due, a_posted = main._ban_notice_pair_tx, asyncio.Event(), asyncio.Event()

            async def first_post_waits(*a, **k):
                if k.get("post_to") is not None and not a_posted.is_set():
                    await asyncio.wait_for(b_at_due.wait(), 20)
                got = await real(*a, **k)
                if got == "posted":
                    a_posted.set()
                return got
            env.mp.setattr(main, "_ban_notice_pair_tx", first_post_waits)

            def sm_b():
                s = env.sm()
                ex = s.execute

                async def execute(stmt, *a, **k):
                    if "n.posted_at IS NULL" in str(stmt):
                        b_at_due.set()
                        await asyncio.wait_for(a_posted.wait(), 20)
                    return await ex(stmt, *a, **k)
                s.execute = execute
                return s
            one, two = await asyncio.gather(main.ban_link_notice_pass(env.sm), main.ban_link_notice_pass(sm_b))
            out.update(one=one, two=two, posts=await _posts(env), met=b_at_due.is_set() and a_posted.is_set())
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    assert out["met"], out
    assert len(out["posts"]) == 20 and out["one"]["posted"] + out["two"]["posted"] == 20, (
        len(out["posts"]), out["one"], out["two"])


@pytest.mark.parametrize("between", ["account deletion", "retention pass"])
def test_twenty_a_utc_day_holds_across_a_deletion_or_a_retention_pass(monkeypatch, between):
    """H3: after twenty posts, neither an account's deletion nor a retention
    pass that removes posted pairs gives the day more posts."""
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            first, others = await _pairs(env, c, admin, 20, "day1")
            await _stored(env)
            full = await main.ban_link_notice_pass(env.sm)
            await _pairs(env, c, admin, 2, "day2")
            await _stored(env)
            if between == "account deletion":
                async with env.sm() as db:
                    await main._alt_delete_account(db, others[0].sid)
                    await db.commit()
            else:
                await BR._end(env, (await BR._row(env, first.sid))["id"], lifted=True)
                await main._alt_retention_pass(env.sm)
            left = await env.conn.fetchval("SELECT count(*) FROM ban_link_notices WHERE posted_at IS NOT NULL")
            after = await main.ban_link_notice_pass(env.sm)
            out.update(full=full, after=after, left=left, posts=await _posts(env))
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    assert out["full"]["posted"] == 20 and out["left"] < 20, out
    assert out["after"]["posted"] == 0 and len(out["posts"]) == 20, (out["after"], len(out["posts"]))


async def _due_pair(env, c, admin):
    """One banned account and one other account, stored, the channel set:
    one pair due for posting."""
    b, (o,) = await _pair_world(env, c, admin)
    await _stored(env)
    return b, o


async def _day_posts(env):
    return await env.conn.fetchval(
        "SELECT posts FROM ban_notice_days WHERE day = (now() AT TIME ZONE 'UTC')::date")


async def _pass_caught(sm):
    """One pass; its counts, or the name of what it raised, and its time."""
    t0 = time.monotonic()
    try:
        got, err = await main.ban_link_notice_pass(sm), None
    except Exception as ex:
        got, err = None, type(ex).__name__
    return got, err, time.monotonic() - t0


POOL_TIMEOUT_S = 4


def test_a_pass_on_an_engine_of_one_connection_posts_a_due_pair_before_the_pool_time_out(monkeypatch):
    """Fix 2, A (finding 1): the pass opens no second session or connection
    while a pair's transaction is open. On an engine of ONE connection (no
    overflow, a pool time-out of POOL_TIMEOUT_S) a due pair is posted, no
    error leaves the pass, and the pass ends before the pool time-out."""
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            b, o = await _due_pair(env, c, admin)
        one = create_async_engine(
            harness.async_dsn(env.c.dsn), pool_size=1, max_overflow=0, pool_timeout=POOL_TIMEOUT_S,
            connect_args={"server_settings": {"search_path": harness.quoted(env.c.schema)}})
        try:
            got, err, took = await _pass_caught(async_sessionmaker(one, expire_on_commit=False))
        finally:
            await one.dispose()
        out.update(got=got, err=err, took=took, posts=await _posts(env), rows=await _notices(env),
                   pair=(b.sid, o.sid), day=await _day_posts(env))
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    assert out["err"] is None and out["got"]["posted"] == 1, (out["err"], out["got"], out["took"])
    assert out["took"] < POOL_TIMEOUT_S, out["took"]
    assert len(out["posts"]) == 1 and out["rows"][out["pair"]] is not None and out["day"] == 1, out


def test_the_slot_posted_at_and_the_post_row_are_one_transaction(monkeypatch):
    """Fix 2, A (findings 1 and 2): the slot statement, the posted_at UPDATE
    and the post row's INSERT run in ONE transaction on one connection, so
    the day the slot counts, posted_at and the post row's created_at read
    one clock. Each statement's transaction is observed by the engine's
    begin events; then the stored values: posted_at equals the post row's
    created_at, and the day counted is posted_at's UTC date."""
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            b, o = await _due_pair(env, c, admin)
        serial, open_tx, seen = [0], {}, []

        def on_begin(conn):
            serial[0] += 1
            open_tx[id(conn)] = serial[0]

        def on_statement(conn, cursor, statement, parameters, context, executemany):
            seen.append((statement, open_tx.get(id(conn))))
        sync = env.engine.sync_engine
        event.listen(sync, "begin", on_begin)
        event.listen(sync, "before_cursor_execute", on_statement)
        try:
            got = await main.ban_link_notice_pass(env.sm)
        finally:
            event.remove(sync, "before_cursor_execute", on_statement)
            event.remove(sync, "begin", on_begin)
        tx = {}
        for want in ("INSERT INTO ban_notice_days", "UPDATE ban_link_notices SET posted_at",
                     "INSERT INTO pending_channel_posts"):
            tx[want] = [t for s, t in seen if want in s]
        row = await env.conn.fetchrow(
            "SELECT n.posted_at, p.created_at FROM ban_link_notices n, pending_channel_posts p"
            " WHERE n.banned_steam_id = $1 AND n.other_steam_id = $2 AND p.channel_id = $3",
            b.sid, o.sid, CHANNEL)
        days = [tuple(r) for r in await env.conn.fetch("SELECT day, posts FROM ban_notice_days")]
        out.update(got=got, tx=tx, row=row and tuple(row), days=days, begins=serial[0])
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    assert out["got"]["posted"] == 1 and out["begins"] > 0, out
    serials = [t for ts in out["tx"].values() for t in ts]
    assert len(serials) == 3 and None not in serials and len(set(serials)) == 1, out["tx"]
    posted_at, created_at = out["row"]
    assert posted_at == created_at, out["row"]
    assert out["days"] == [(posted_at.astimezone(datetime.timezone.utc).date(), 1)], (out["days"], posted_at)


REFUSE_FN = "alt_ban_fix2_refuse_post"


def test_a_post_row_that_fails_to_commit_gives_its_slot_back_and_leaves_the_pair_unposted(monkeypatch):
    """Fix 2, A: a post row refused at COMMIT (a deferred constraint trigger
    of the case's own on pending_channel_posts) leaves the day's count where
    it was (3), the pair unposted and no post row; with the trigger gone the
    next pass posts the pair and the day counts 4."""
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            b, o = await _due_pair(env, c, admin)
        await env.conn.execute(
            "INSERT INTO ban_notice_days (day, posts) VALUES ((now() AT TIME ZONE 'UTC')::date, 3)")
        await env.conn.execute(
            "CREATE FUNCTION %s() RETURNS trigger LANGUAGE plpgsql AS"
            " $f$BEGIN RAISE EXCEPTION 'the post row is refused at commit'; END$f$" % REFUSE_FN)
        await env.conn.execute(
            "CREATE CONSTRAINT TRIGGER %s AFTER INSERT ON pending_channel_posts"
            " DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION %s()" % (REFUSE_FN, REFUSE_FN))
        try:
            refused, err, _took = await _pass_caught(env.sm)
            out.update(refused=refused, err=err, day_refused=await _day_posts(env),
                       rows_refused=await _notices(env), posts_refused=await _posts(env))
        finally:
            await env.conn.execute("DROP TRIGGER IF EXISTS %s ON pending_channel_posts" % REFUSE_FN)
            await env.conn.execute("DROP FUNCTION IF EXISTS %s()" % REFUSE_FN)
        again = await main.ban_link_notice_pass(env.sm)
        out.update(again=again, day=await _day_posts(env), rows=await _notices(env), posts=await _posts(env),
                   pair=(b.sid, o.sid))
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    assert out["day_refused"] == 3, (out["day_refused"], out["err"], out["refused"])
    assert out["rows_refused"] == {out["pair"]: None} and out["posts_refused"] == [], out
    assert out["again"]["posted"] == 1 and out["day"] == 4 and out["rows"][out["pair"]] is not None, out
    assert len(out["posts"]) == 1, out["posts"]


def test_a_slot_held_past_the_lock_limit_makes_the_pair_busy_with_nothing_written(monkeypatch):
    """Fix 2, A: while another transaction holds the day's row, the pair's
    slot statement waits no longer than the pair transaction's lock limit;
    the pair ends "busy", nothing is written, no error leaves the pass, and
    the pass ends within the statement limit. With the row free the next
    pass posts the pair."""
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            b, o = await _due_pair(env, c, admin)
        await env.conn.execute(
            "INSERT INTO ban_notice_days (day, posts) VALUES ((now() AT TIME ZONE 'UTC')::date, 2)")
        side = await env.side()
        tr = side.transaction()
        await tr.start()
        await side.execute(
            "SELECT posts FROM ban_notice_days WHERE day = (now() AT TIME ZONE 'UTC')::date FOR UPDATE")
        try:
            held, err, took = await _pass_caught(env.sm)
            out.update(held=held, err=err, took=took, day_held=await _day_posts(env),
                       rows_held=await _notices(env), posts_held=await _posts(env))
        finally:
            await tr.rollback()
        free = await main.ban_link_notice_pass(env.sm)
        out.update(free=free, day=await _day_posts(env), rows=await _notices(env), pair=(b.sid, o.sid))
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    assert out["err"] is None and (out["held"]["busy"], out["held"]["posted"]) == (1, 0), (out["err"], out["held"])
    assert out["took"] < main._BAN_NOTICE_STATEMENT_MS / 1000.0, out["took"]
    assert out["day_held"] == 2 and out["rows_held"] == {out["pair"]: None} and out["posts_held"] == [], out
    assert out["free"]["posted"] == 1 and out["day"] == 3 and out["rows"][out["pair"]] is not None, out


def test_a_slot_error_ends_that_pair_alone_and_the_next_due_pair_is_posted(monkeypatch):
    """Fix 2, ruling Q2: an error on the first pair's slot statement (the
    statement rewritten to name a table that does not stand, for that one
    statement only) ends that pair alone as "busy", with a rollback and no
    post; nothing leaves the pass, and the pass goes on to the next due pair,
    which is posted. Only "full" stops the posting."""
    out = {}

    async def body(env):
        _setup(env, CHANNEL)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            b, others = await _pair_world(env, c, admin, others=2)
            await _stored(env)
        hits = []

        def first_slot_fails(sql):
            if "INSERT INTO ban_notice_days" in sql and not hits:
                hits.append(sql)
                return sql.replace("INSERT INTO ban_notice_days", "INSERT INTO ban_notice_days_not_there", 1)
            return sql
        env._rewrites.append(first_slot_fails)
        try:
            got, err, _took = await _pass_caught(env.sm)
        finally:
            env._rewrites.remove(first_slot_fails)
        rows = await _notices(env)
        out.update(got=got, err=err, hits=len(hits), day=await _day_posts(env), posts=await _posts(env),
                   posted=sorted(k[1] for k, v in rows.items() if v is not None), n=len(rows))
    try:
        case(monkeypatch, body, prefix="bannote")
    finally:
        A.install_key(None)
    assert out["err"] is None and out["hits"] == 1, (out["err"], out["hits"])
    assert (out["got"]["busy"], out["got"]["posted"], out["got"]["full"]) == (1, 1, 0), out["got"]
    assert out["day"] == 1 and len(out["posts"]) == 1 and len(out["posted"]) == 1 and out["n"] == 2, out
