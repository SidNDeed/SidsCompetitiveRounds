"""ALT-BAN-1 step 6 (A6): GET /api/v1/admin/bans/links and the four keys of
the ban list, over planted rows of the lane's tables and migration 431's.

The links route (CONTRACT-BAN-1124 point 4 with ADD2): the five words in
their order, days null for the three family words, others, links_total, the
caps, the banned account's own side without a window and the other side
with the lane's, a deleted linked account never named, no mark, key id or
code in the answer, 404 no_active_ban, 503 links_unavailable on a cancelled
read, at most 13 statements, no moderator-log row. The list (point 1):
region, region_at, regions and links by ONE more read for the page inside a
savepoint (four statements with a key loaded, none without), null when the
read fails or no key is loaded, the released client's parse over filled
rows. The costs are measured in test_alt_ban_costs_pg.py.

Every id, name, region and mark here is invented; the marks are hashes of
labels, never of an address."""
import asyncio
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for p in (API, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest  # noqa: E402
from sqlalchemy import event  # noqa: E402

import main  # noqa: E402
import alt_signals as A  # noqa: E402
import test_ban_record_pg as BR  # noqa: E402
import test_alt_signals_record_pg as R  # noqa: E402
from inv_pg import case  # noqa: E402
from test_ban_expiry_live import _parse_banned_users_1410  # noqa: E402

HOW = ["address", "block", "family_shared", "family_lender", "family_borrower"]


def _m(label):
    return hashlib.sha256(("alt-ban-links " + label).encode()).digest()


def _sig(admin, target):
    return BR._sig(admin, "ban_links", target)


async def _links(c, admin, target, sig=None):
    return await c.get("/api/v1/admin/bans/links", params={
        "admin_steam_id": admin, "target_steam_id": target,
        "hmac_signature": sig if sig is not None else _sig(admin, target)})


def _keyed(env, notice=True):
    """The signal key loaded (removed at the case's end) and FAQ message 1
    holding both sentences, posted (or not)."""
    A.install_key(R.KEY_HEX)
    env.mp.setattr(main, "_alt_notice_line_at", [None])
    return notice


async def _notice(env, posted=True):
    await env.conn.execute("DELETE FROM pending_channel_posts WHERE channel_id = $1 AND sort_order = 1",
                           main._ALT_FAQ_CHANNEL)
    await env.conn.execute(
        "INSERT INTO pending_channel_posts (channel_id, content, sort_order, revision, posted_revision)"
        " VALUES ($1, $2, 1, 4, $3)", main._ALT_FAQ_CHANNEL, "message one\n\n" + A.NOTICE_BAN, 4 if posted else 3)


async def _marker(env, sid, addr, block, days_ago, cls="none", first_days_ago=None):
    kid = A.loaded_key().key_id
    await env.conn.execute(
        "INSERT INTO conn_markers (steam_id, day, key_id, addr_mark, block_mark, family, conn_class, first_at, last_at)"
        " VALUES ($1, CAST((now() AT TIME ZONE 'UTC') AS date) - $2::int, $3, $4, $5, 4, $6,"
        " now() - make_interval(days => $7::int), now() - make_interval(days => $2::int))"
        " ON CONFLICT DO NOTHING",
        sid, days_ago, kid, _m(addr), _m(block), cls, days_ago if first_days_ago is None else first_days_ago)


async def _share(env, sid, owner_mark, days_ago=1):
    await env.conn.execute(
        "INSERT INTO steam_family_shares (steam_id, key_id, owner_mark, first_seen_at, last_seen_at)"
        " VALUES ($1, $2, $3, now() - make_interval(days => $4::int), now() - make_interval(days => $4::int))",
        sid, A.loaded_key().key_id, owner_mark, days_ago)


async def _ban_row(env, admin, sid):
    """An active ban of 30 days written as a row (the route's rate limit holds
    an admin to five bans in five minutes; a test of many bans writes rows)."""
    await env.conn.execute(
        "INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, expires_at)"
        " VALUES ($1, 'ban-record', $2, now() + interval '30 days')", sid, admin)


def _account(sid):
    return A.account_mark(A.loaded_key().secret, sid)


async def _region(env, sid, region, cls="none", hours_ago=1):
    await env.conn.execute(
        "INSERT INTO ban_regions (steam_id, region, conn_class, first_at, last_at) VALUES ($1, $2, $3,"
        " now() - make_interval(hours => $4::int + 5), now() - make_interval(hours => $4::int))",
        sid, region, cls, hours_ago)


async def _world(env, c, admin):
    """A banned account B and the accounts linked to it, one per word, with
    the numbers the answer must give."""
    b = await env.player("Links Banned")
    await BR._ban(c, admin, b.sid)
    w = {"b": b}
    for k in ("addr", "addr2", "blk", "fam", "lend", "borrow", "old", "gone", "far1", "attic"):
        w[k] = await env.player("Links " + k)
    # B's own rows: the home code on three days, a cafe code; the attic code only 200 days back: the own
    # side has no window while the ban stands, so attic's recent row on it links.
    for d in (1, 2, 200):
        await _marker(env, b.sid, "home", "blk-home", d)
    await _marker(env, b.sid, "cafe", "blk-cafe", 3)
    await _marker(env, b.sid, "attic", "blk-attic", 200)
    await _marker(env, w["attic"].sid, "attic", "blk-attic", 3)
    # addr: the home code on days 1 and 2 (two days); addr2 on one day; old only 120 days back (the
    # other side keeps the lane's window: never linked).
    for d in (1, 2):
        await _marker(env, w["addr"].sid, "home", "blk-home", d)
    await _marker(env, w["addr2"].sid, "home", "blk-home", 5)
    await _marker(env, w["old"].sid, "home", "blk-home", 120)
    # blk: another address in B's cafe block; addr is in the home block too (its block row is a copy).
    await _marker(env, w["blk"].sid, "cafe-2", "blk-cafe", 4, cls="vpn")
    # two further accounts on the home code, one of them deleted (never named, still counted in others).
    await _marker(env, w["far1"].sid, "home", "blk-home", 6)
    await _marker(env, w["gone"].sid, "home", "blk-home", 6)
    await env.conn.execute("UPDATE players SET deleted_at = now() WHERE steam_id = $1", w["gone"].sid)
    # family: fam borrows from the same lender as B; B borrows lend's copy; borrow borrows B's copy.
    lender = _account(w["lend"].sid)
    await _share(env, b.sid, lender, 2)
    await _share(env, w["fam"].sid, lender, 3)
    await _share(env, w["borrow"].sid, _account(b.sid), 4)
    return w


def test_each_word_its_numbers_and_the_order(monkeypatch):
    out = {}

    async def body(env):
        BR._open(env)
        _keyed(env)
        await _notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            w = await _world(env, c, admin)
            await _region(env, w["b"].sid, "Ardenmark, Vellshire", hours_ago=1)
            await _region(env, w["b"].sid, "Brynmoor", cls="vpn", hours_ago=30)
            r = await _links(c, admin, w["b"].sid)
            out.update(status=r.status_code, body=r.json(), w={k: p.sid for k, p in w.items()})
    try:
        case(monkeypatch, body, prefix="banlnk")
    finally:
        A.install_key(None)
    assert out["status"] == 200, out
    a, w = out["body"], out["w"]
    assert list(a) == ["steam_id", "recording", "regions", "links", "links_total"], list(a)
    assert a["steam_id"] == w["b"] and a["recording"] == "on"
    assert [(g["region"], g["conn_class"]) for g in a["regions"]] == [("Ardenmark, Vellshire", "none"), ("Brynmoor", "vpn")]
    assert all(BR.Z.match(g["first_at"]) and BR.Z.match(g["last_at"]) for g in a["regions"])
    got = [(e["how"], e["linked_steam_id"]) for e in a["links"]]
    # address (the lane's order: same-day days first), block without the copies, the three family words.
    assert [h for h, _s in got] == sorted([h for h, _s in got], key=HOW.index), got
    by = {(e["how"], e["linked_steam_id"]): e for e in a["links"]}
    assert set(got) == {("address", w["addr"]), ("address", w["addr2"]), ("address", w["far1"]),
                        ("address", w["attic"]), ("block", w["blk"]), ("family_shared", w["fam"]),
                        ("family_lender", w["lend"]), ("family_borrower", w["borrow"])}, got
    assert by[("address", w["attic"])]["others"] == 0 and by[("address", w["attic"])]["days"] == 1
    assert by[("address", w["addr"])]["days"] == 2 and by[("address", w["addr2"])]["days"] == 1
    # others on the home code: addr, addr2, far1 and the deleted account record it beside B; for one row, the
    # further accounts are the other three.
    assert by[("address", w["addr"])]["others"] == 3, by[("address", w["addr"])]
    assert by[("block", w["blk"])]["days"] == 1 and by[("block", w["blk"])]["others"] == 0
    for how in ("family_shared", "family_lender", "family_borrower"):
        e = next(e for e in a["links"] if e["how"] == how)
        assert e["days"] is None and re.fullmatch(r"\d{4}-\d\d-\d\d", e["last_day"]) and e["others"] == 0, e
    assert all(re.fullmatch(r"\d{4}-\d\d-\d\d", e["last_day"]) for e in a["links"])
    assert by[("address", w["addr"])]["linked_name"] == "Links addr"
    assert w["gone"] not in json.dumps(a) and w["old"] not in json.dumps(a)
    assert a["links_total"] == len(a["links"]) == 8


def test_no_mark_key_id_code_or_address_in_the_answer(monkeypatch):
    out = {}

    async def body(env):
        BR._open(env)
        _keyed(env)
        await _notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            w = await _world(env, c, admin)
            out["text"] = (await _links(c, admin, w["b"].sid)).text
            out["kid"] = A.loaded_key().key_id
    try:
        case(monkeypatch, body, prefix="banlnk")
    finally:
        A.install_key(None)
    t = out["text"]
    for word in [out["kid"], R.KEY_HEX] + [_m(x).hex() for x in ("home", "cafe", "blk-home", "blk-cafe")]:
        assert word not in t, word
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", t), "an address form in the answer"


@pytest.mark.parametrize("state", ["no ban", "ended", "lifted", "not an id"])
def test_no_active_ban_is_404(monkeypatch, state):
    out = {}

    async def body(env):
        BR._open(env)
        _keyed(env)
        admin = await BR._admin(env)
        p = await env.player("Links 404")
        async with BR._client(env) as c:
            target = p.sid
            if state in ("ended", "lifted"):
                ban = await BR._ban(c, admin, p.sid)
                row = await BR._row(env, p.sid)
                await BR._end(env, row["id"], lifted=state == "lifted")
            if state == "not an id":
                target = "12ab"
            r = await _links(c, admin, target)
            out.update(status=r.status_code, detail=r.json().get("detail"))
    try:
        case(monkeypatch, body, prefix="banlnk")
    finally:
        A.install_key(None)
    assert (out["status"], out["detail"]) == (404, "no_active_ban"), out


def test_a_bad_signature_is_refused_and_nothing_is_read(monkeypatch):
    out = {}

    async def body(env):
        BR._open(env)
        admin = await BR._admin(env)
        p = await env.player("Links Sig")
        async with BR._client(env) as c:
            await BR._ban(c, admin, p.sid)
            r = await _links(c, admin, p.sid, sig=BR._sig(admin, "list_bans", ""))
            out["status"] = r.status_code
    case(monkeypatch, body, prefix="banlnk")
    assert out["status"] == 403


def test_a_cancelled_read_answers_503_and_at_most_13_statements_and_no_log_row(monkeypatch):
    out = {}

    async def body(env):
        BR._open(env)
        _keyed(env)
        await _notice(env)
        admin = await BR._admin(env)
        seen = []

        def listen(conn, cursor, statement, parameters, context, executemany):
            seen.append(statement)
        async with BR._client(env) as c:
            w = await _world(env, c, admin)
            logged = await env.conn.fetchval("SELECT count(*) FROM admin_actions")
            event.listen(env.engine.sync_engine, "before_cursor_execute", listen)
            try:
                r = await _links(c, admin, w["b"].sid)
                out["n"], out["ok"] = len(seen), r.status_code
                env.mp.setattr(main, "_ALT_BAN_LINKS_STATEMENT_MS", 100)
                with env.rewriting("FROM ban_regions x", "FROM ban_regions x CROSS JOIN pg_sleep(0.5) zz"):
                    r = await _links(c, admin, w["b"].sid)
                out["cut"] = (r.status_code, r.json().get("detail"))
            finally:
                event.remove(env.engine.sync_engine, "before_cursor_execute", listen)
            out["logged"] = await env.conn.fetchval("SELECT count(*) FROM admin_actions") - logged
    try:
        case(monkeypatch, body, prefix="banlnk")
    finally:
        A.install_key(None)
    assert out["ok"] == 200 and out["n"] <= 13, out
    assert out["cut"] == (503, "links_unavailable"), out
    assert out["logged"] == 0, out


def test_recording_says_off_without_a_key_or_with_the_notice_closed(monkeypatch):
    out = {}

    async def body(env):
        BR._open(env)
        _keyed(env)
        await _notice(env, posted=False)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            w = await _world(env, c, admin)
            out["closed"] = (await _links(c, admin, w["b"].sid)).json()["recording"]
            A.install_key(None)
            r = await _links(c, admin, w["b"].sid)
            out["nokey"] = (r.status_code, r.json()["recording"], r.json()["links"] and r.json()["links"][0]["how"])
    try:
        case(monkeypatch, body, prefix="banlnk")
    finally:
        A.install_key(None)
    assert out["closed"] == "off" and out["nokey"][:2] == (200, "off"), out


# -- the list's four keys --------------------------------------------------------------------------

NASTY = 'Ardenmark, "Vell" \\shire \\n "id":"x9"'


def test_the_list_fills_its_four_keys_by_one_read_and_the_old_parse_reads_the_same(monkeypatch):
    out = {}

    async def body(env):
        BR._open(env)
        _keyed(env)
        await _notice(env)
        admin = await BR._admin(env)
        seen, after = [], [False]

        def listen(conn, cursor, statement, parameters, context, executemany):
            if after[0]:
                seen.append(statement)
        real = main._require_admin

        async def marked(*a, **k):
            got = await real(*a, **k)
            after[0] = True
            return got
        env.mp.setattr(main, "_require_admin", marked)
        async with BR._client(env) as c:
            w = await _world(env, c, admin)
            await _region(env, w["b"].sid, NASTY, hours_ago=2)
            await _region(env, w["b"].sid, "Brynmoor", cls="vpn", hours_ago=30)
            other = await env.player("Links Other Ban")
            await BR._ban(c, admin, other.sid)
            event.listen(env.engine.sync_engine, "before_cursor_execute", listen)
            try:
                after[0] = False
                wire = (await BR._list(c, admin)).text
                out["n_key"], out["s_key"] = len(seen), list(seen)
                seen.clear()
                after[0] = False
                A.install_key(None)
                out["nokey"] = json.loads((await BR._list(c, admin)).text)
                out["n_nokey"], out["s_nokey"] = len(seen), list(seen)
            finally:
                event.remove(env.engine.sync_engine, "before_cursor_execute", listen)
            out.update(wire=wire, b=w["b"].sid, other=other.sid)
    try:
        case(monkeypatch, body, prefix="banlnk")
    finally:
        A.install_key(None)
    answer = json.loads(out["wire"])
    for e in answer["bans"]:
        assert list(e) == BR.OLD_KEYS + BR.NEW_KEYS, list(e)
    by = {e["steam_id"]: e for e in answer["bans"]}
    b = by[out["b"]]
    assert (b["region"], b["regions"], b["links"]) == (NASTY, 2, 8), b
    assert BR.Z.match(b["region_at"]), b
    o = by[out["other"]]
    assert (o["region"], o["region_at"], o["regions"], o["links"]) == ("", None, 0, 0), o
    # No key: the four as before, and no statement of the fill; with the key: exactly four more.
    for e in out["nokey"]["bans"]:
        assert (e["region"], e["region_at"], e["regions"], e["links"]) == ("", None, None, None), e
    extra = [s for s in out["s_key"] if s not in out["s_nokey"]]
    assert out["n_key"] - out["n_nokey"] == 4, [s[:70] for s in out["s_key"]] + ["--"] + [s[:70] for s in out["s_nokey"]]
    assert [s.split()[0] for s in extra] == ["SAVEPOINT", "SELECT", "WITH", "ROLLBACK"], [s[:70] for s in extra]
    # The released client's parse over filled rows reads the same six values as over the stripped answer.
    stripped = dict(answer, bans=[{k: v for k, v in e.items() if k in BR.OLD_KEYS[:6]} for e in answer["bans"]])
    plain = json.dumps(stripped, separators=(",", ":"), ensure_ascii=False)
    new, old = _parse_banned_users_1410(out["wire"]), _parse_banned_users_1410(plain)
    assert len(new) == len(answer["bans"]) and new == old, (new, old)


@pytest.mark.parametrize("fault", ["cancelled", "absent table"])
def test_a_failed_fill_answers_null_and_the_list_still_comes(monkeypatch, fault):
    out = {}

    async def body(env):
        BR._open(env)
        _keyed(env)
        await _notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            w = await _world(env, c, admin)
            await _region(env, w["b"].sid, "Brynmoor")
            if fault == "cancelled":
                env.mp.setattr(main, "_ALT_BAN_LINKS_STATEMENT_MS", 100)
                old, new = "FROM ban_regions r JOIN ids", "FROM ban_regions r CROSS JOIN pg_sleep(0.5) zz JOIN ids"
            else:
                old, new = "FROM ban_regions r JOIN ids", "FROM ban_regions_absent r JOIN ids"
            with env.rewriting(old, new) as hits:
                r = await BR._list(c, admin)
            out.update(status=r.status_code, answer=r.json(), hits=len(hits), b=w["b"].sid)
    try:
        case(monkeypatch, body, prefix="banlnk")
    finally:
        A.install_key(None)
    assert out["status"] == 200 and out["hits"] >= 1, out
    for e in out["answer"]["bans"]:
        assert (e["region"], e["region_at"], e["regions"], e["links"]) == ("", None, None, None), e
        assert e["account"] == "live" and e["reason"] == "ban-record", e


def test_the_list_reads_no_row_at_a_time(monkeypatch):
    out = {}

    async def body(env):
        BR._open(env)
        _keyed(env)
        await _notice(env)
        admin = await BR._admin(env)
        seen = []

        def listen(conn, cursor, statement, parameters, context, executemany):
            seen.append(statement)
        async with BR._client(env) as c:
            for n in (1, 6):
                for i in range(n - (1 if n == 6 else 0)):
                    p = await env.player("Links Many %d %d" % (n, i))
                    await _ban_row(env, admin, p.sid)
                    await _marker(env, p.sid, "many-%d-%d" % (n, i), "blk-many", 1)
                    await _region(env, p.sid, "Brynmoor")
                event.listen(env.engine.sync_engine, "before_cursor_execute", listen)
                try:
                    seen.clear()
                    await BR._list(c, admin)
                    out[n] = len(seen)
                finally:
                    event.remove(env.engine.sync_engine, "before_cursor_execute", listen)
    try:
        case(monkeypatch, body, prefix="banlnk")
    finally:
        A.install_key(None)
    assert out[1] == out[6], out


# -- fix 1 of the item's round (H1, H2, M7, M8) ----------------------------------------------------

def _gate_mode(env, mode):
    """This process acts on the read gate's stage `mode` ("unknown": never loaded)."""
    import read_gate
    env.mp.setattr(read_gate, "_mode_cache", {"value": mode, "loaded": mode != read_gate.UNKNOWN,
                                              "at": read_gate._mono(), "gen": 0})


@pytest.mark.parametrize("mode", ["enforce", "log", "off", "unknown"])
def test_the_links_route_meets_the_read_gate_as_the_ban_list_does(monkeypatch, mode):
    """H1: in every stage of the read gate an admin's valid signature alone
    gets the links route's own answer, as it gets the ban list's; a wrong
    signature gets the route's own admin refusal."""
    out = {}

    async def body(env):
        BR._open(env)
        _keyed(env)
        await _notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            p = await env.player("Links Gate")
            await BR._ban(c, admin, p.sid)
            _gate_mode(env, mode)
            lst = await c.get("/api/v1/admin/banned-users",
                              params={"admin_steam_id": admin, "hmac_signature": BR._sig(admin, "list_bans", "")})
            lnk = await _links(c, admin, p.sid)
            bad_list = await c.get("/api/v1/admin/banned-users",
                                   params={"admin_steam_id": admin, "hmac_signature": BR._sig(admin, "ban", "")})
            bad = await _links(c, admin, p.sid, sig=BR._sig(admin, "list_bans", ""))
            out.update(lst=lst.status_code, lnk=(lnk.status_code, lnk.json().get("steam_id")),
                       bad_list=bad_list.status_code, bad=bad.status_code, sid=p.sid)
    try:
        case(monkeypatch, body, prefix="banlnk")
    finally:
        A.install_key(None)
    assert out["lst"] == 200 and out["lnk"] == (200, out["sid"]), out
    assert out["bad_list"] == out["bad"] == 403, out
