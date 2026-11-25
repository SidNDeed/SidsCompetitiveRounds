"""BAN-RECORD-1 on PostgreSQL: what a ban remembers (the account's name and
the moderators' details), what the admin list answers about it, the details
route, and the account deletion's clearing (ORDER-BAN-RECORD-1.md R2 to R5,
its bar V2 to V6; CONTRACT-BAN-1124.md points 1 and 2 with its ADD1).

Through main.app (its middlewares included, the database dependency bound to
the case schema of inv_pg), with real admin signatures (ADMIN_HMAC_SECRET set
for the case), unless a test names a handler and a session of its own.

R2  A new ban keeps the live players row's name after the display-name rule;
    a repeat and a length change write none of the three columns; an id with
    no live row keeps none; the name is read after the identity lock (a
    deletion-shaped anonymising that held the lock leaves no name to keep).
V2  The 1.41.0 client's parse of the list (its split on "id":" and its six
    reads), over a reason, details and a kept name holding quotes, the text
    "id":" and line breaks, gives the values of the same answer without the
    ten new keys, row for row, and one entry per ban.
V3  The list: a live name; the kept name after the deletion-shaped
    anonymising (account "deleted", or "none" without MATCH_HMAC_SECRET); no
    name (account "none"); a live name changed after the ban (the live one
    wins); search by the kept name, a details word, %, _ and a backslash;
    the total with and without a search; paging; the unpaged default's set
    and order; 0 bans; banned_by_name and details_by_name.
V4  The details route: save, change, clear, a name alone, both absent, too
    long, an unknown target, an ended ban, a lifted ban, a wrong signature,
    no change; the text rules; the ban of an account deleted before any name
    was kept (ADD1); two writers on one ban, and a writer against an unban,
    interleaved on two connections: one final text, one record per change,
    no record for a refused call.
V5  No answer to the banned account holds either text: the readers of the
    three columns stand in the two admin-signed routes and the writers alone
    (over the source), and every route of the ban census's lists that a
    banned account calls, with /mod/check, the deletion's refusal, a gated
    route's refusal, the sign-in and the bot's feed, answers without them.
V6  The deletion after an ended ban: the three columns NULL, in the
    deletion's own transaction (a failure after the statement leaves
    everything set).
N1  RULING-BAN-RECORD-R1 with N6: a ban_details record holds the ban's id and
    the words of which texts changed, never a text (T1 the table's rows, T2
    the log's three reads, T3 a key inside its ban's id, T4 three ban rows).

CF_TEST_PG_DSN names the lane database (cf_pg.require_live_pg).
"""

import ast
import asyncio
import contextlib
import hashlib
import hmac
import json
import os
import re
import sys
import uuid
from types import SimpleNamespace

import httpx
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from inv_pg import FLOOR, STEAM_BASE, case, waiting_on  # noqa: E402

import main  # noqa: E402
import modlog  # noqa: E402
import ban_sweep_census as BSC  # noqa: E402
import test_ban_record_tournament_rows_pg as TR  # noqa: E402
from test_ban_answers_pg import TOKEN, _account, _armed, _delete, _session  # noqa: E402
from test_ban_expiry_live import _parse_banned_users_1410  # noqa: E402
from test_mail_case_scrub_pg import BOUND  # noqa: E402
from test_mdpl_gate_reread_pg import _tombstone  # noqa: E402

ADMIN_SECRET = "ban-record-admin-secret"
INTERNAL_KEY = "ban-record-internal-key"
# The case harness stands a recorder in for main._check_steam_session that admits every caller (inv_pg.py,
# Env: "admits every caller"). N3.1's sweep and N8 put the real one back, so each route answers as deployed.
_REAL_SESSION_CHECK = main._check_steam_session
assert (_REAL_SESSION_CHECK.__module__, _REAL_SESSION_CHECK.__name__) == ("main", "_check_steam_session")
KEY_SQL = "SELECT pg_advisory_xact_lock(hashtext($1))"   # the identity key, exclusive
OLD_KEYS = ["id", "steam_id", "display_name", "reason", "banned_by_steam_id", "banned_at",
            "expires_at", "seconds_left"]
NEW_KEYS = ["account", "name_kept", "banned_by_name", "details", "details_at", "details_by_name",
            "region", "region_at", "regions", "links"]
Z = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z$")


# -- the world --------------------------------------------------------------------------------------

@contextlib.asynccontextmanager
async def _client(env):
    """A client of main.app whose database sessions are the case's."""
    async def override():
        async with env.sm() as db:
            yield db
    main.app.dependency_overrides[main.get_db] = override
    try:
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
                base_url="http://ban-record", headers={"X-Mod-Version": FLOOR}) as c:
            yield c
    finally:
        main.app.dependency_overrides.pop(main.get_db, None)


def _open(env, secret=True):
    """Real admin signatures for the case; the deletion ledger's secret set
    (or unset); the internal key for the bot's feed."""
    env.mp.setattr(main, "ADMIN_HMAC_SECRET", ADMIN_SECRET)
    env.mp.setattr(main, "MATCH_HMAC_SECRET", "ban-record-ledger-secret" if secret else "")
    env.mp.setenv("API_SECRET_KEY", INTERNAL_KEY)


def _sig(admin, action, target=""):
    return hmac.new(ADMIN_SECRET.encode(), main._admin_canonical(admin, action, target).encode(),
                    hashlib.sha256).hexdigest()


async def _admin(env, name="Rec Admin"):
    p = await env.player(name)
    await env.conn.execute("INSERT INTO admin_users (steam_id) VALUES ($1)", p.sid)
    return p.sid


def _no_row_sid(env):
    env.serial += 1
    return str(STEAM_BASE + env.serial)


async def _ban(c, admin, target, **fields):
    body = {"admin_steam_id": admin, "target_steam_id": target, "reason": "ban-record",
            "hmac_signature": _sig(admin, "ban", target)}
    body.update(fields)
    r = await c.post("/api/v1/admin/ban", json=body)
    assert r.status_code == 200, (r.status_code, r.text)
    return r.json()


async def _details(c, admin, target, *, sig=None, **fields):
    body = {"admin_steam_id": admin, "target_steam_id": target,
            "hmac_signature": sig if sig is not None else _sig(admin, "ban_details", target)}
    body.update(fields)
    return await _post_ascii(c, "/api/v1/admin/ban/details", body)


async def _post_ascii(c, path, body):
    """A POST whose JSON is ASCII (json.dumps escapes every character beyond
    ASCII): a lone surrogate travels as its \\ud800 escape, which httpx's
    json= cannot encode."""
    return await c.post(path, content=json.dumps(body).encode("ascii"),
                        headers={"Content-Type": "application/json"})


async def _list(c, admin, **params):
    q = {"admin_steam_id": admin, "hmac_signature": _sig(admin, "list_bans", "")}
    q.update(params)
    r = await c.get("/api/v1/admin/banned-users", params=q)
    assert r.status_code == 200, (r.status_code, r.text)
    return r


async def _row(env, sid):
    """The account's newest ban row, every column."""
    return dict(await env.conn.fetchrow(
        "SELECT * FROM player_bans WHERE steam_id = $1 ORDER BY banned_at DESC LIMIT 1", sid))


async def _records(env, ban_id=None):
    """The ban_details records (of one ban, or all), oldest first, details decoded."""
    rows = await env.conn.fetch(
        "SELECT admin_steam_id, target_steam_id, affected_steam_ids, reason, CAST(details AS text) AS d"
        "  FROM admin_actions WHERE action = 'ban_details'"
        "   AND ($1::text IS NULL OR details->>'ban_id' = $1::text) ORDER BY created_at, id",
        None if ban_id is None else str(ban_id))
    return [dict(r, d=json.loads(r["d"])) for r in rows]


async def _end(env, ban_id, *, lifted=False):
    """The ban ended (its end a minute ago) or lifted, its start moved back so
    the row stays inside the table's checks."""
    if lifted:
        await env.conn.execute("UPDATE player_bans SET unbanned_at = NOW(), unbanned_by_steam_id = banned_by_steam_id"
                               " WHERE id = $1", ban_id)
    else:
        await env.conn.execute("UPDATE player_bans SET banned_at = NOW() - INTERVAL '2 hours',"
                               "       expires_at = NOW() - INTERVAL '1 minute' WHERE id = $1", ban_id)


def _entries(r):
    return r.json()["bans"]


def _by_sid(r):
    return {e["steam_id"]: e for e in _entries(r)}


# -- R2: the name a new ban keeps -------------------------------------------------------------------

def test_r2_a_new_ban_keeps_the_live_name_and_a_repeat_or_a_length_change_writes_none(monkeypatch):
    """R2, and N7 of RULING-BAN-RECORD-R1: the repeat and the length change run on a ban whose three
    columns all hold a value (the details and their time seeded through the details route first), and each
    leaves the three exactly as they were, the time included."""
    async def body(env):
        _open(env)
        admin = await _admin(env)
        live = await env.player(" Kept\tName\nTwo ")
        self_named = await env.player("x")
        await env.conn.execute("UPDATE players SET display_name = steam_id WHERE id = $1", self_named.id)
        raw = _no_row_sid(env)
        async with _client(env) as c:
            await _ban(c, admin, live.sid)
            await _ban(c, admin, self_named.sid)
            await _ban(c, admin, raw)
            first = await _row(env, live.sid)
            seeded = await _details(c, admin, live.sid, details="seeded before the repeat")
            assert seeded.status_code == 200, seeded.text
            seeded = await _row(env, live.sid)
            await env.conn.execute("UPDATE players SET display_name = 'Renamed Later' WHERE id = $1", live.id)
            again = await _ban(c, admin, live.sid)
            after_repeat = await _row(env, live.sid)
            longer = await _ban(c, admin, live.sid, duration_minutes=90)
        after = await _row(env, live.sid)
        n = await env.conn.fetchval("SELECT count(*) FROM player_bans WHERE steam_id = $1", live.sid)
        return (first, seeded, again, after_repeat, longer, after, n, await _row(env, self_named.sid),
                await _row(env, raw))
    out = {}

    async def run(env):
        out["v"] = await body(env)
    case(monkeypatch, run, prefix="banrec")
    first, seeded, again, after_repeat, longer, after, n, self_named, raw = out["v"]
    three = ("display_name_at_ban", "details", "details_at")
    # one line, the tab out, trimmed
    assert (first["display_name_at_ban"], first["details"], first["details_at"]) == ("KeptName Two", None, None)
    # the reach: all three hold a value before the repeat and the length change run
    assert (seeded["display_name_at_ban"], seeded["details"]) == ("KeptName Two", "seeded before the repeat")
    assert seeded["details_at"] is not None, seeded
    assert again["status"] == "already_banned" and longer["status"] == "length_changed", (again, longer)
    assert n == 1 and after["id"] == first["id"], (n, after["id"], first["id"])
    for label, row in (("the repeat", after_repeat), ("the length change", after)):
        assert [row[k] for k in three] == [seeded[k] for k in three], (label, {k: (seeded[k], row[k]) for k in three})
    assert after["expires_at"] != first["expires_at"], "the length change did not run"
    # the display-name rule: an account named by its own id keeps no name; no row keeps none
    assert self_named["display_name_at_ban"] is None and raw["display_name_at_ban"] is None


def test_r2_the_name_is_read_after_the_identity_lock(monkeypatch):
    """The ban core waits on the target's identity lock while a deletion-shaped
    anonymising holds it; the anonymising commits; the core then finds no
    live row and keeps no name. Read before the lock, it would keep the
    name of the account whose deletion committed before the ban did."""
    async def body(env):
        _open(env)
        admin = await _admin(env)
        p = await env.player("Before The Lock")
        side = await env.side()
        side_pid = await side.fetchval("SELECT pg_backend_pid()")
        await side.execute("BEGIN")
        await side.execute(KEY_SQL, p.sid)

        async def core():
            async with env.sm() as db:
                await main._apply_ban_core(db, admin_steam_id=admin, target_steam_id=p.sid, reason="lock order")
                await db.commit()
        task = asyncio.ensure_future(core())
        waiters = await waiting_on(env, side_pid)
        await _tombstone(side, p)
        await side.execute("COMMIT")
        await asyncio.wait_for(task, BOUND)
        return waiters, await _row(env, p.sid)
    out = {}

    async def run(env):
        out["v"] = await body(env)
    case(monkeypatch, run, prefix="banrec")
    waiters, row = out["v"]
    assert waiters, "the ban core did not wait on the identity lock"
    assert row["display_name_at_ban"] is None, row["display_name_at_ban"]


# -- V3: the list ---------------------------------------------------------------------------------

def test_v3_the_list_answers_names_texts_accounts_and_searches(monkeypatch):
    async def body(env):
        _open(env)
        out = {}
        admin_a = await _admin(env, "Rec Admin A")
        admin_b = await _admin(env, "Rec Admin B")
        live = await env.player("Live One")
        gone = await env.player("Gone Two")
        ren = await env.player("Old Three")
        raw = _no_row_sid(env)
        async with _client(env) as c:
            for sid in (live.sid, gone.sid, raw, ren.sid):
                await _ban(c, admin_a, sid)
            r = await _details(c, admin_b, live.sid, details="rate 100% sure")
            assert r.status_code == 200, r.text
            r = await _details(c, admin_a, raw, details="under_score here")
            assert r.status_code == 200, r.text
            r = await _details(c, admin_a, ren.sid, details="back\\slash here")
            assert r.status_code == 200, r.text
            await env.conn.execute("UPDATE players SET display_name = 'New Three' WHERE id = $1", ren.id)
            side = await env.side()
            await side.execute("BEGIN")
            await side.execute(KEY_SQL, gone.sid)
            await _tombstone(side, gone)
            await side.execute("COMMIT")
            out["all"] = (await _list(c, admin_a)).json()
            for q in ("Gone Two", "Old Three", "New Three", "sure", "100%", "%", "_", "\\", raw[-6:], "zz-nothing"):
                out["q:" + q] = (await _list(c, admin_a, search=q)).json()
            out["page"] = (await _list(c, admin_a, limit=2, offset=1)).json()
            out["order"] = [str(r["id"]) for r in await env.conn.fetch(
                "SELECT id FROM player_bans pb WHERE " + main.player_ban_active_sql("pb")
                + " ORDER BY pb.banned_at DESC, pb.id DESC")]
            env.mp.setattr(main, "MATCH_HMAC_SECRET", "")
            out["no_secret"] = (await _list(c, admin_a)).json()
        out["sids"] = {"live": live.sid, "gone": gone.sid, "ren": ren.sid, "raw": raw}
        return out
    got = {}

    async def run(env):
        got.update(await body(env))
    case(monkeypatch, run, prefix="banrec")
    s = got["sids"]
    full = got["all"]
    assert list(full) == ["bans", "total", "limit", "offset"] and full["total"] == 4, full
    for e in full["bans"]:
        assert list(e) == OLD_KEYS + NEW_KEYS, list(e)
        assert (e["region"], e["region_at"], e["regions"], e["links"]) == ("", None, None, None), e
        assert e["banned_by_name"] == "Rec Admin A", e
    by = {e["steam_id"]: e for e in full["bans"]}
    pick = ("display_name", "account", "name_kept", "details", "details_by_name")
    assert {k: by[s["live"]][k] for k in pick} == {
        "display_name": "Live One", "account": "live", "name_kept": False,
        "details": "rate 100% sure", "details_by_name": "Rec Admin B"}, by[s["live"]]
    assert {k: by[s["gone"]][k] for k in pick} == {
        "display_name": "Gone Two", "account": "deleted", "name_kept": True,
        "details": "", "details_by_name": ""}, by[s["gone"]]
    assert {k: by[s["raw"]][k] for k in pick} == {
        "display_name": None, "account": "none", "name_kept": False,
        "details": "under_score here", "details_by_name": "Rec Admin A"}, by[s["raw"]]
    assert {k: by[s["ren"]][k] for k in pick} == {
        "display_name": "New Three", "account": "live", "name_kept": False,
        "details": "back\\slash here", "details_by_name": "Rec Admin A"}, by[s["ren"]]
    assert Z.match(by[s["live"]]["details_at"]) and by[s["gone"]]["details_at"] is None, by
    # the unpaged default: every active ban, in the list's order
    assert [e["id"] for e in full["bans"]] == got["order"], (full["bans"], got["order"])

    def hits(q):
        a = got["q:" + q]
        assert a["total"] == len(a["bans"]), a
        return sorted(e["steam_id"] for e in a["bans"])
    assert hits("Gone Two") == [s["gone"]]            # the kept name
    assert hits("Old Three") == [s["ren"]]            # the kept name of a renamed account
    assert hits("New Three") == [s["ren"]]            # the live name
    assert hits("sure") == hits("100%") == hits("%") == [s["live"]]
    assert hits("_") == [s["raw"]]
    assert hits("\\") == [s["ren"]]
    assert hits(s["raw"][-6:]) == [s["raw"]]
    assert hits("zz-nothing") == []
    page = got["page"]
    assert (page["total"], page["limit"], page["offset"]) == (4, 2, 1), page
    assert [e["id"] for e in page["bans"]] == [e["id"] for e in full["bans"]][1:3], page
    # without the secret there is no hash: no account is "deleted"
    assert {e["steam_id"]: e["account"] for e in got["no_secret"]["bans"]} == {
        s["live"]: "live", s["gone"]: "none", s["raw"]: "none", s["ren"]: "live"}


def test_v3_no_bans_answers_an_empty_list_with_a_zero_total(monkeypatch):
    async def body(env):
        _open(env)
        admin = await _admin(env)
        async with _client(env) as c:
            return (await _list(c, admin)).content, (await _list(c, admin, search="x", limit=5)).json()
    out = {}

    async def run(env):
        out["v"] = await body(env)
    case(monkeypatch, run, prefix="banrec")
    plain, searched = out["v"]
    assert plain == b'{"bans":[],"total":0,"limit":null,"offset":0}', plain
    assert searched == {"bans": [], "total": 0, "limit": 5, "offset": 0}, searched


def test_v3_the_list_reads_at_most_two_statements_and_no_statement_carries_the_secret(monkeypatch):
    """RULING-BAN-RECORD-Q1-Q3 Q2, added to the bar: the statements of a list
    call after its admin check are counted (every statement the case's engine
    runs, from the moment _require_admin returns): two at most (the list's
    one statement, then one read of the deletion ledger for the page's ids
    with no live row); one when every id of the page is live; one when the
    ledger's secret is unset. No statement text and no bind value of the
    whole call carries the ledger's secret (MATCH_HMAC_SECRET) or the admin
    signatures' secret."""
    from sqlalchemy import event
    ledger = "ban-record-ledger-secret"
    out = {}

    async def body(env):
        _open(env)
        admin = await _admin(env)
        live = await env.player("Q2 Live Account")
        raw = _no_row_sid(env)
        engine = env.sm.kw.get("bind")
        assert engine is not None, env.sm.kw
        seen, after = [], [False]

        def listen(conn, cursor, statement, parameters, context, executemany):
            seen.append((after[0], statement, repr(parameters)))
        real = main._require_admin

        async def marked(*a, **k):
            got = await real(*a, **k)
            after[0] = True
            return got
        env.mp.setattr(main, "_require_admin", marked)
        async with _client(env) as c:
            await _ban(c, admin, live.sid)
            await _ban(c, admin, raw)
            event.listen(engine.sync_engine, "before_cursor_execute", listen)
            try:
                for label, secret, params in (("a no-row id on the page", True, {}),
                                              ("every id of the page live", True, {"search": "Q2 Live"}),
                                              ("the secret unset", False, {})):
                    _open(env, secret=secret)
                    seen.clear()
                    after[0] = False
                    r = (await _list(c, admin, **params)).json()
                    out[label] = {"accounts": sorted(e["account"] for e in r["bans"]),
                                  "after": [s for a, s, _p in seen if a], "all": list(seen)}
            finally:
                event.remove(engine.sync_engine, "before_cursor_execute", listen)
    case(monkeypatch, body, prefix="banrec")
    for label, got in out.items():
        print("[Q2] %s: %d statements after the admin check: %s" % (
            label, len(got["after"]), [re.sub(r"\s+", " ", s)[:70] for s in got["after"]]))
    two = out["a no-row id on the page"]
    assert two["accounts"] == ["live", "none"] and len(two["after"]) == 2, two["after"]
    assert "player_bans" in two["after"][0] and "deleted_steam_ids" in two["after"][1], two["after"]
    one = out["every id of the page live"]
    assert one["accounts"] == ["live"] and len(one["after"]) == 1 and "player_bans" in one["after"][0], one
    unset = out["the secret unset"]
    assert unset["accounts"] == ["live", "none"] and len(unset["after"]) == 1, unset["after"]
    for label, got in out.items():
        for _a, statement, params in got["all"]:
            for secret in (ledger, ADMIN_SECRET):
                assert secret not in statement and secret not in params, (label, statement[:80])


# -- V2: the 1.41.0 parse ---------------------------------------------------------------------------

def test_v2_the_old_parse_reads_the_six_values_over_texts_shaped_like_its_keys(monkeypatch):
    nasty = 'say "hi" then "id":"x0" and\na break, "reason":"no"'
    async def body(env):
        _open(env)
        admin = await _admin(env)
        ps = [await env.player("Parse %d" % i) for i in range(3)]
        raw = _no_row_sid(env)
        async with _client(env) as c:
            for p in ps:
                await _ban(c, admin, p.sid, reason=nasty)
            await _ban(c, admin, raw, reason=nasty)
            for sid in (ps[0].sid, ps[1].sid, raw):
                r = await _details(c, admin, sid, details=nasty + '\r\n"steam_id":"1"')
                assert r.status_code == 200, r.text
            # a kept name holding the same, written past the name rules on purpose (the wire is under test)
            await env.conn.execute("UPDATE player_bans SET display_name_at_ban = $1 WHERE steam_id = $2",
                                   'Kept "id":"k1"\nline "display_name":"z"', raw)
            return (await _list(c, admin)).text
    out = {}

    async def run(env):
        out["wire"] = await body(env)
    case(monkeypatch, run, prefix="banrec")
    wire = out["wire"]
    answer = json.loads(wire)
    assert len(answer["bans"]) == 4 and '"id":"x0"' not in wire, wire
    stripped = dict(answer, bans=[{k: v for k, v in e.items() if k in OLD_KEYS[:6]} for e in answer["bans"]])
    plain = json.dumps(stripped, separators=(",", ":"), ensure_ascii=False)
    new, old = _parse_banned_users_1410(wire), _parse_banned_users_1410(plain)
    assert len(new) == len(answer["bans"]) and new == old, (new, old)
    assert [p["id"] for p in new] == [e["id"] for e in answer["bans"]]
    assert [p["steam_id"] for p in new] == [e["steam_id"] for e in answer["bans"]]
    kept = [e for e in answer["bans"] if e["name_kept"]]
    assert len(kept) == 1 and kept[0]["display_name"].startswith('Kept "id":"k1"'), kept


# -- V4: the details route --------------------------------------------------------------------------

def test_v4_save_change_clear_a_name_alone_and_no_change(monkeypatch):
    async def body(env):
        _open(env)
        out = {}
        admin = await _admin(env, "Details Admin")
        p = await env.player("Details Live")
        raw = _no_row_sid(env)
        async with _client(env) as c:
            await _ban(c, admin, p.sid)
            await _ban(c, admin, raw)
            ban_id = (await _row(env, p.sid))["id"]
            steps = [("save", dict(details="first text")),
                     ("change", dict(details="second text")),
                     ("same", dict(details="  second text \n")),
                     ("clear", dict(details="")),
                     ("name", dict(name="Typed Name")),
                     ("both", dict(details="third", name="")),
                     ("null", dict(details=None, name="Another"))]
            for label, fields in steps:
                r = await _details(c, admin, p.sid, **fields)
                out[label] = (r.status_code, r.json(), await _row(env, p.sid), len(await _records(env, ban_id)))
            r = await _details(c, admin, raw, name="Raw Typed")
            out["raw"] = (r.status_code, r.json())
            out["records"] = await _records(env, ban_id)
            out["list"] = _by_sid(await _list(c, admin))
        out["ids"] = (admin, p.sid, raw, str(ban_id))
        return out
    got = {}

    async def run(env):
        got.update(await body(env))
    case(monkeypatch, run, prefix="banrec")
    admin, sid, raw, ban_id = got["ids"]
    st, ans, row, n = got["save"]
    assert st == 200 and list(ans) == ["status", "steam_id", "details", "details_at", "display_name"], ans
    assert (ans["status"], ans["steam_id"], ans["details"], ans["display_name"]) == (
        "details_saved", sid, "first text", "Details Live"), ans
    assert Z.match(ans["details_at"]) and row["details"] == "first text" and n == 1, (ans, row)
    st, ans, row2, n = got["change"]
    assert (st, ans["details"], row2["details"], n) == (200, "second text", "second text", 2)
    assert row2["details_at"] >= row["details_at"]
    st, ans, row3, n = got["same"]                     # trimmed to the same text: nothing written
    assert (st, ans["details"], n, row3["details_at"]) == (200, "second text", 2, row2["details_at"]), ans
    st, ans, row4, n = got["clear"]
    assert (st, ans["details"], ans["details_at"], row4["details"], row4["details_at"], n) == (
        200, "", None, None, None, 3), ans
    st, ans, row5, n = got["name"]                     # a live account: the list shows the live name
    assert (st, ans["display_name"], row5["display_name_at_ban"], row5["details"], n) == (
        200, "Details Live", "Typed Name", None, 4), ans
    st, ans, row6, n = got["both"]
    assert (st, ans["details"], row6["details"], row6["display_name_at_ban"], n) == (
        200, "third", "third", None, 5), ans
    st, ans, row7, n = got["null"]                     # null details: the details stay
    assert (st, row7["details"], row7["display_name_at_ban"], n) == (200, "third", "Another", 6), ans
    st, ans = got["raw"]
    assert (st, ans["display_name"], ans["details"]) == (200, "Raw Typed", ""), ans
    recs = got["records"]
    assert [r["d"].get("details_change") for r in recs] == ["added", "changed", "cleared", None, "added", None]
    assert [r["d"].get("name_change") for r in recs] == [None, None, None, "changed", "cleared", "added"]
    # N1 (RULING-BAN-RECORD-R1 section 1 (a)): a record holds the ban's id and the words of which texts changed
    assert recs[0]["d"] == {"ban_id": ban_id, "details_change": "added"}, recs[0]
    assert recs[3]["d"] == {"ban_id": ban_id, "name_change": "changed"}, recs[3]
    for r in recs:
        assert (r["admin_steam_id"], r["target_steam_id"], r["affected_steam_ids"], r["reason"]) == (
            admin, sid, [sid], None), r
        assert set(r["d"]) <= {"ban_id", "details_change", "name_change"}, r["d"]
    assert [modlog.sentence("ban_details", r["d"]) for r in recs[:5]] == [
        "Ban details added.", "Ban details changed.", "Ban details cleared.", "Ban kept name changed.",
        "Ban details added and kept name cleared."]
    assert modlog.label("ban_details") == "Ban details changed"
    listed = got["list"]
    assert (listed[sid]["details"], listed[sid]["display_name"], listed[sid]["name_kept"]) == (
        "third", "Details Live", False)
    assert (listed[raw]["display_name"], listed[raw]["name_kept"], listed[raw]["account"]) == (
        "Raw Typed", True, "none")


def test_v4_refused_calls_write_nothing(monkeypatch):
    async def body(env):
        _open(env)
        out = {}
        admin = await _admin(env)
        stranger = (await env.player("Not An Admin")).sid
        p = await env.player("Refused Live")
        ended = await env.player("Ended")
        lifted = await env.player("Lifted")
        nobody = _no_row_sid(env)
        async with _client(env) as c:
            for x in (p, ended, lifted):
                await _ban(c, admin, x.sid)
            await _end(env, (await _row(env, ended.sid))["id"])
            await _end(env, (await _row(env, lifted.sid))["id"], lifted=True)
            r = await _details(c, admin, p.sid, details="x" * 2000)
            out["at_limit"] = (r.status_code, len(r.json().get("details", "")))
            before = (await _row(env, p.sid), len(await _records(env)))
            calls = {
                "both_absent": (admin, p.sid, {}, None),
                "both_null": (admin, p.sid, {"details": None, "name": None}, None),
                "too_long": (admin, p.sid, {"details": "y" * 2001}, None),
                "too_long_after_rules": (admin, p.sid, {"details": "\x01" + "z" * 2001}, None),
                "name_too_long": (admin, p.sid, {"name": "n" * 65}, None),
                "unknown": (admin, nobody, {"details": "t"}, None),
                "ended": (admin, ended.sid, {"details": "t"}, None),
                "lifted": (admin, lifted.sid, {"details": "t"}, None),
                "wrong_sig": (admin, p.sid, {"details": "t"}, "0" * 64),
                "other_action_sig": (admin, p.sid, {"details": "t"}, _sig(admin, "ban", p.sid)),
                "not_admin": (stranger, p.sid, {"details": "t"}, None),
                "not_a_string": (admin, p.sid, {"details": 5}, None),
            }
            for label, (who, target, fields, sig) in calls.items():
                r = await _details(c, who, target, sig=sig, **fields)
                out[label] = (r.status_code, r.json().get("detail"))
            out["after"] = (await _row(env, p.sid), len(await _records(env)))
        out["before"] = before
        return out
    got = {}

    async def run(env):
        got.update(await body(env))
    case(monkeypatch, run, prefix="banrec")
    assert got["at_limit"] == (200, 2000), got["at_limit"]
    want = {"both_absent": (422, "details_or_name_required"), "both_null": (422, "details_or_name_required"),
            "too_long": (422, "details_too_long"), "too_long_after_rules": (422, "details_too_long"),
            "name_too_long": (422, "name_too_long"), "unknown": (404, "no_active_ban"),
            "ended": (404, "no_active_ban"), "lifted": (404, "no_active_ban"),
            "wrong_sig": (403, "Bad admin signature"), "other_action_sig": (403, "Bad admin signature"),
            "not_admin": (403, "Not an admin")}
    for label, w in want.items():
        assert got[label] == w, (label, got[label])
    assert got["not_a_string"][0] == 422, got["not_a_string"]
    before_row, before_n = got["before"]
    after_row, after_n = got["after"]
    assert after_row == before_row and after_n == before_n, (before_row, after_row, before_n, after_n)


def test_v4_the_text_rules(monkeypatch):
    async def body(env):
        _open(env)
        out = {}
        admin = await _admin(env)
        p = await env.player("Rules Live")
        async with _client(env) as c:
            await _ban(c, admin, p.sid)
            cases = [("crlf", {"details": "  one\r\ntwo\rthree\u2028four\u2029five\x85six  "}),
                     ("controls", {"details": "a\tb\x00c\x1bd\x7fe\x9ff\u200bg"}),
                     ("blank", {"details": " \r\n\t "}),
                     ("surrogate", {"details": "s\ud800t"}),
                     ("name_lines", {"name": " Line\r\nOne\tTwo\u2028Three "}),
                     ("name_own_id", {"name": p.sid}),
                     ("name_account_id", {"name": "76561197960265729"}),
                     ("name_64", {"name": "m" * 64}),
                     ("name_surrogate", {"name": "Ab\udc00c"})]
            for label, fields in cases:
                r = await _details(c, admin, p.sid, **fields)
                row = await _row(env, p.sid)
                out[label] = (r.status_code, row["details"], row["display_name_at_ban"])
        return out
    got = {}

    async def run(env):
        got.update(await body(env))
    case(monkeypatch, run, prefix="banrec")
    # the kept name is the live row's from the ban (R2) until a name is sent
    assert got["crlf"] == (200, "one\ntwo\nthree\nfour\nfive\nsix", "Rules Live"), got["crlf"]
    assert got["controls"] == (200, "abcdef\u200bg", "Rules Live"), got["controls"]
    assert got["blank"] == (200, None, "Rules Live"), got["blank"]
    # a lone surrogate has no UTF-8 form: taken out (by the request model, before its
    # bound, and by the rules), never stored and never a 500 (recnew2 answered 500:
    # the model's bound refused it and the 422 body could not carry it)
    assert got["surrogate"] == (200, "st", "Rules Live"), got["surrogate"]
    assert (got["name_lines"][0], got["name_lines"][2]) == (200, "Line OneTwo Three"), got["name_lines"]
    assert (got["name_own_id"][0], got["name_own_id"][2]) == (200, None), got["name_own_id"]
    assert (got["name_account_id"][0], got["name_account_id"][2]) == (200, None), got["name_account_id"]
    assert (got["name_64"][0], got["name_64"][2]) == (200, "m" * 64), got["name_64"]
    assert (got["name_surrogate"][0], got["name_surrogate"][2]) == (200, "Abc"), got["name_surrogate"]


def test_v4_a_lone_surrogate_is_refused_past_the_bound_and_taken_out_inside_it(monkeypatch):
    """RULING-BAN-RECORD-Q5 point 2, the details route's two texts, both arms.
    Refused by the bound: a text past the request model's bound (eight times
    the limit) or past the rules' bound (the limit) that holds a lone
    surrogate is a 422 that answers (never a 500) and writes nothing.
    Accepted and stored without it: a text inside the bounds is stored with
    the character taken out (it never reaches the driver, which refuses one),
    and the log row counts the STORED text as changed: the same text sent
    again, character included, is no change and writes no second record."""
    lone, low = "\ud800", "\udc00"

    async def body(env):
        _open(env)
        admin = await _admin(env)
        p = await env.player("Arms Live")
        out = {}
        async with _client(env) as c:
            await _ban(c, admin, p.sid)
            ban_id = (await _row(env, p.sid))["id"]
            arms = [("details past the model's bound", {"details": lone + "x" * (8 * main.BAN_DETAILS_MAX + 1)}),
                    ("details past the rules' bound", {"details": lone + "x" * (main.BAN_DETAILS_MAX + 1)}),
                    ("name past the model's bound", {"name": low + "n" * (8 * main.BAN_NAME_MAX + 1)}),
                    ("name past the rules' bound", {"name": low + "n" * (main.BAN_NAME_MAX + 1)}),
                    ("details accepted", {"details": "s" + lone + "t"}),
                    ("details sent again", {"details": "s" + lone + "t"}),
                    ("name accepted", {"name": "Ab" + low + "c"}),
                    ("name sent again", {"name": "Ab" + low + "c"})]
            for label, fields in arms:
                r = await _details(c, admin, p.sid, **fields)
                row = await _row(env, p.sid)
                out[label] = (r.status_code, r.json(), row["details"], row["display_name_at_ban"],
                              len(await _records(env, ban_id)))
            out["records"] = await _records(env, ban_id)
        return out
    got = {}

    async def run(env):
        got.update(await body(env))
    case(monkeypatch, run, prefix="banrec")
    for label, v in got.items():
        if label != "records":
            print("[ARMS] %-32s %s %s" % (label, v[0], ascii(v[1])[:100]))
    for label in ("details past the model's bound", "name past the model's bound"):
        st, ans, details, name, recs = got[label]
        assert st == 422 and ans["detail"][0]["type"] == "string_too_long", (label, st, ascii(ans)[:200])
        assert (details, name, recs) == (None, "Arms Live", 0), (label, details, name, recs)
    assert got["details past the rules' bound"] == (422, {"detail": "details_too_long"}, None, "Arms Live", 0), \
        got["details past the rules' bound"]
    assert got["name past the rules' bound"] == (422, {"detail": "name_too_long"}, None, "Arms Live", 0), \
        got["name past the rules' bound"]
    assert got["details accepted"][0] == 200 and got["details accepted"][1]["details"] == "st", got["details accepted"]
    assert got["details accepted"][2:] == ("st", "Arms Live", 1), got["details accepted"]
    assert got["details sent again"][0] == 200 and got["details sent again"][2:] == ("st", "Arms Live", 1), \
        got["details sent again"]
    assert got["name accepted"][0] == 200 and got["name accepted"][1]["display_name"] == "Arms Live", \
        got["name accepted"]   # the live row's name is what the list shows; the kept name is the row's
    assert got["name accepted"][2:] == ("st", "Abc", 2), got["name accepted"]
    assert got["name sent again"][0] == 200 and got["name sent again"][2:] == ("st", "Abc", 2), got["name sent again"]
    first, second = got["records"]   # N1: the words alone, no text
    assert sorted(first["d"]) == ["ban_id", "details_change"] and first["d"]["details_change"] == "added", first["d"]
    assert sorted(second["d"]) == ["ban_id", "name_change"] and second["d"]["name_change"] == "changed", second["d"]


async def _last_record(env, sid):
    """The newest moderator-log record about sid: (action, reason), or None."""
    row = await env.conn.fetchrow("SELECT action, reason FROM admin_actions WHERE target_steam_id = $1"
                                  " ORDER BY created_at DESC, id DESC LIMIT 1", sid)
    return None if row is None else (row["action"], row["reason"])


def test_v4_the_ban_routes_texts_with_a_lone_surrogate(monkeypatch):
    """RULING-BAN-RECORD-Q5 point 2, the sweep: every text a ban route of this
    programme takes in a request and stores or searches by, with a lone
    surrogate inside its bound (sent as ASCII JSON, its escape), and what the
    route answers; the details route's two are the test above. The ban's
    reason is stored in the ban row: the route takes the character out before
    the writer (it answered 500 without that: the database driver refuses the
    text), and has no bound that refuses (the writer keeps 256 characters).
    The length change's reason and the unban's are kept in their records
    only, where the moderator log's own rule (_modlog_text) writes U+FFFD in
    the character's place: both answered 200 before the change. The list's
    search text travels in the query string, which cannot carry a lone
    surrogate: its bytes (ED A0 80) arrive as three U+FFFD characters."""
    lone = "\ud800"

    async def body(env):
        _open(env)
        admin = await _admin(env)
        a = await env.player("Sweep Ban")
        b = await env.player("Sweep Length")
        out = {}
        async with _client(env) as c:
            r = await _post_ascii(c, "/api/v1/admin/ban", {
                "admin_steam_id": admin, "target_steam_id": a.sid, "reason": "r" + lone + "s",
                "hmac_signature": _sig(admin, "ban", a.sid)})
            row = await env.conn.fetchrow("SELECT reason FROM player_bans WHERE steam_id = $1", a.sid)
            out["ban reason"] = (r.status_code, row and row["reason"], await _last_record(env, a.sid))
            await _ban(c, admin, b.sid)
            r = await _post_ascii(c, "/api/v1/admin/ban", {
                "admin_steam_id": admin, "target_steam_id": b.sid, "reason": "l" + lone + "c",
                "duration_minutes": 60, "hmac_signature": _sig(admin, "ban", b.sid)})
            out["length change reason"] = (r.status_code, None, await _last_record(env, b.sid))
            r = await _post_ascii(c, "/api/v1/admin/unban", {
                "admin_steam_id": admin, "target_steam_id": b.sid, "reason": "u" + lone + "n",
                "hmac_signature": _sig(admin, "unban", b.sid)})
            out["unban reason"] = (r.status_code, None, await _last_record(env, b.sid))
            r = await c.get("/api/v1/admin/banned-users?admin_steam_id=%s&hmac_signature=%s&search=%%ED%%A0%%80"
                            % (admin, _sig(admin, "list_bans", "")))
            out["list search"] = (r.status_code, r.json().get("total") if r.status_code == 200 else r.text[:80],
                                  None)
        return out
    got = {}

    async def run(env):
        got.update(await body(env))
    case(monkeypatch, run, prefix="banrec")
    for label, v in got.items():
        print("[SWEEP] %-22s %s" % (label, ascii(v)))
    assert got["ban reason"] == (200, "rs", ("ban", "rs")), got["ban reason"]
    assert got["length change reason"][0] == 200 and got["length change reason"][2][1] == "l�c", \
        got["length change reason"]
    assert got["unban reason"] == (200, None, ("unban", "u�n")), got["unban reason"]
    assert got["list search"] == (200, 0, None), got["list search"]


def test_v4_the_ban_of_an_account_deleted_before_any_name_was_kept_takes_a_name(monkeypatch):
    """ADD1: an active ban stands under the raw id of an account whose
    deletion committed (the deletion-shaped anonymising, ledger included).
    The route accepts it, keeps the name, and writes the raw id nowhere."""
    async def body(env):
        _open(env)
        admin = await _admin(env)
        p = await env.player("Deleted Under Ban")
        async with _client(env) as c:
            await _ban(c, admin, p.sid)
            ban_id = (await _row(env, p.sid))["id"]
            await env.conn.execute("UPDATE player_bans SET display_name_at_ban = NULL WHERE id = $1", ban_id)
            side = await env.side()
            await side.execute("BEGIN")
            await side.execute(KEY_SQL, p.sid)
            await _tombstone(side, p)
            await side.execute("COMMIT")
            r = await _details(c, admin, p.sid, name="Known Name", details="seen on stream")
            listed = _by_sid(await _list(c, admin))[p.sid]
        recs = await _records(env, ban_id)
        raw_named = await env.conn.fetchval(
            "SELECT count(*) FROM admin_actions WHERE action = 'ban_details'"
            "   AND (target_steam_id = $1 OR $1 = ANY(affected_steam_ids) OR CAST(details AS text) LIKE '%' || $1 || '%')",
            p.sid)
        return r.status_code, r.json(), listed, recs, raw_named
    out = {}

    async def run(env):
        out["v"] = await body(env)
    case(monkeypatch, run, prefix="banrec")
    st, ans, listed, recs, raw_named = out["v"]
    assert st == 200 and (ans["display_name"], ans["details"]) == ("Known Name", "seen on stream"), ans
    assert (listed["account"], listed["display_name"], listed["name_kept"]) == ("deleted", "Known Name", True)
    assert len(recs) == 1 and (recs[0]["target_steam_id"], recs[0]["affected_steam_ids"]) == (None, []), recs
    assert raw_named == 0, raw_named


async def _blocked_by(env, pid, tries=200):
    """Whether some backend of the case waits on `pid`'s locks (polled)."""
    return bool(await waiting_on(env, pid, tries=tries))


def test_v4_two_writers_on_one_ban_interleaved(monkeypatch):
    """Both writers wait on the target's identity lock held by a third
    connection; released, they run one after the other: one final text, one
    record per change, each record's old text the text the other left."""
    async def body(env):
        _open(env)
        admin = await _admin(env)
        p = await env.player("Two Writers")
        async with _client(env) as c:
            await _ban(c, admin, p.sid)
            ban_id = (await _row(env, p.sid))["id"]
            side = await env.side()
            side_pid = await side.fetchval("SELECT pg_backend_pid()")
            await side.execute("BEGIN")
            await side.execute(KEY_SQL, p.sid)
            first = asyncio.ensure_future(_details(c, admin, p.sid, details="from writer one"))
            assert await _blocked_by(env, side_pid)
            second = asyncio.ensure_future(_details(c, admin, p.sid, details="from writer two"))
            await asyncio.sleep(0.3)
            assert not first.done() and not second.done()
            await side.execute("COMMIT")
            r1, r2 = await asyncio.wait_for(asyncio.gather(first, second), BOUND)
        return (r1.status_code, r1.json()), (r2.status_code, r2.json()), await _row(env, p.sid), \
            await _records(env, ban_id)
    out = {}

    async def run(env):
        out["v"] = await body(env)
    case(monkeypatch, run, prefix="banrec")
    a, b, row, recs = out["v"]
    assert a[0] == b[0] == 200, (a, b)
    assert row["details"] in ("from writer one", "from writer two"), row
    assert len(recs) == 2, recs
    # N1: a record holds the words alone; one text was added, then changed by the second writer
    assert [r["d"]["details_change"] for r in recs] == ["added", "changed"], recs


@pytest.mark.parametrize("first", ["unban", "writer"])
def test_v4_a_writer_against_an_unban_interleaved(monkeypatch, first):
    """The unban and the writer queue on the same identity lock in a known
    order. Unban first: the writer finds no active ban, 404, no record.
    Writer first: its text and its one record stand, then the ban is lifted."""
    async def body(env):
        _open(env)
        admin = await _admin(env)
        p = await env.player("Writer Unban")
        async with _client(env) as c:
            await _ban(c, admin, p.sid)
            ban_id = (await _row(env, p.sid))["id"]
            side = await env.side()
            side_pid = await side.fetchval("SELECT pg_backend_pid()")
            await side.execute("BEGIN")
            await side.execute(KEY_SQL, p.sid)

            def unban():
                return c.post("/api/v1/admin/unban", json={
                    "admin_steam_id": admin, "target_steam_id": p.sid, "reason": "lifted",
                    "hmac_signature": _sig(admin, "unban", p.sid)})

            def writer():
                return _details(c, admin, p.sid, details="written in the race")
            calls = {"unban": unban, "writer": writer}
            order = [first, "writer" if first == "unban" else "unban"]
            t1 = asyncio.ensure_future(calls[order[0]]())
            assert await _blocked_by(env, side_pid)
            t2 = asyncio.ensure_future(calls[order[1]]())
            await asyncio.sleep(0.3)
            await side.execute("COMMIT")
            r1, r2 = await asyncio.wait_for(asyncio.gather(t1, t2), BOUND)
            got = dict(zip(order, (r1, r2)))
        return ((got["unban"].status_code, got["unban"].json()), (got["writer"].status_code, got["writer"].json()),
                await _row(env, p.sid), await _records(env, ban_id))
    out = {}

    async def run(env):
        out["v"] = await body(env)
    case(monkeypatch, run, prefix="banrec")
    unban, writer, row, recs = out["v"]
    assert unban[0] == 200 and unban[1]["rows"] == 1 and row["unbanned_at"] is not None, (unban, row)
    if first == "unban":
        assert writer == (404, {"detail": "no_active_ban"}) and row["details"] is None and recs == [], (writer, recs)
    else:
        assert writer[0] == 200 and row["details"] == "written in the race" and len(recs) == 1, (writer, recs)


# -- V5: nothing reaches the banned account ---------------------------------------------------------

# player_bans.details is TEXT and is set as text (the details route); the moderator log's own column of
# that name (admin_actions.details, jsonb, which _modlog_scrub_records sets as jsonb) is another column.
_COLUMN_TEXT = re.compile(r"display_name_at_ban|details_at|\bpb\.details\b|\bdetails\s*=\s*CAST\(:d AS (?i:text)\)")
_READERS = {("main", "_apply_ban_core"), ("main", "_BAN_LIST_SQL"), ("main", "admin_list_bans"),
            ("main", "admin_ban_details"), ("main", "_ban_record_forget")}


def _column_holders():
    """(module, top-level name) of every string constant in backend/api and the
    bot that names one of the three columns in SQL (docstrings left out)."""
    found = set()
    files = [(n[:-3], os.path.join(API, n)) for n in sorted(os.listdir(API)) if n.endswith(".py")]
    files.append(("discord_bot", os.path.normpath(os.path.join(HERE, "..", "discord_bot.py"))))
    for mod, path in files:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        docs = {id(n.body[0].value) for n in ast.walk(tree)
                if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body
                and isinstance(n.body[0], ast.Expr)}
        for top in tree.body:
            name = getattr(top, "name", None) or (
                top.targets[0].id if isinstance(top, ast.Assign) and isinstance(top.targets[0], ast.Name) else None)
            for n in ast.walk(top):
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs \
                        and _COLUMN_TEXT.search(n.value):
                    found.add((mod, name))
    return found


def test_v5_the_columns_are_read_only_by_the_two_admin_routes_and_written_by_the_writers():
    """Over the source: the SQL that names the three columns stands in the
    ban writer, the list's statement and its search, the details route (its
    row read and its write) and the deletion's helper alone; the list's
    statement is used by the list route alone; the list and the details route
    are admin-signed, each checking the admin signature (which refuses a
    banned admin) before any read."""
    assert _column_holders() == _READERS, _column_holders() ^ _READERS
    with open(os.path.join(API, "main.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    fns = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    users = {}
    for name, fn in fns.items():
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and n.id == "_BAN_LIST_SQL":
                users.setdefault(n.id, set()).add(name)
    assert users == {"_BAN_LIST_SQL": {"admin_list_bans"}}, users
    for name in ("admin_list_bans", "admin_ban_details"):
        awaited = [ast.unparse(st.value.value.func) for st in fns[name].body
                   if isinstance(st, ast.Expr) and isinstance(st.value, ast.Await)
                   and isinstance(st.value.value, ast.Call)]
        assert awaited and awaited[0] == "_require_admin", (name, awaited)
    # the ORM class is named by its definition and main.py's import alone: no ORM read loads the columns
    named = []
    for n in sorted(os.listdir(API)):
        if n.endswith(".py") and n != "models.py":
            with open(os.path.join(API, n), encoding="utf-8") as fh:
                t = ast.parse(fh.read())
            named += [(n, x.lineno) for x in ast.walk(t) if isinstance(x, ast.Name) and x.id == "PlayerBan"]
    assert named == [], named


def _routes_answering_a_banned_account():
    """The ban census's lists of the routes a banned account calls (its
    exits and the routes open to it), with the answers R4 names: the ban
    check, the sign-in, the deletion's refusal and a gated route's refusal,
    and the bot's feed (what Discord is told)."""
    routes = set(BSC.OPEN_ROUTES) | set(BSC.BAN_R17_EXITS) | set(BSC.STRICT_EXITS)
    routes |= {("GET", "/api/v1/mod/check/{steam_id}"), ("POST", "/api/v1/auth/steam"),
               ("DELETE", "/api/v1/players/{steam_id}/data"), ("POST", "/api/v1/queue/join"),
               ("GET", "/api/v1/internal/recent-bans")}
    return sorted(routes)


# N8 (RULING-BAN-RECORD-R1 section 4; FX2 of the integrator's entry of 01:24:29Z): every route of the list
# is sent its OWN request, and the answer the banned account gets is asserted FIRST: its status and the word
# its answer starts with. A request that ends before that answer (a validation refusal, the version check) is
# red there. The account holds no session (the ban deleted it); the client still sends the token it held.
N8_ANSWERS = {
    # the sign-in: the body of test_ban_expiry_live.py's _obs_sign_in (steam_id, ticket_hex "00"), over HTTP
    ("POST", "/api/v1/auth/steam"): (409, "Banned"),
    ("DELETE", "/api/v1/players/{steam_id}/data"): (409, "Banned"),
    ("POST", "/api/v1/queue/join"): (409, "Banned"),
    ("POST", "/api/v1/tournaments/{tournament_id}/unsignup"): (409, "Banned"),
    ("POST", "/api/v1/spectate/leave"): (401, "session_required"),
    ("POST", "/api/v1/queue/leave"): (200, "left"),
    ("POST", "/api/v1/queue/decline"): (409, "not_matched_with_that_player"),
    ("POST", "/api/v1/queues/escape"): (200, "ok"),
    ("POST", "/api/v1/team/queue/leave"): (200, "left"),
    ("POST", "/api/v1/ovt/queue/leave"): (200, "ok"),
    ("POST", "/api/v1/ffa/queue/leave"): (200, "ok"),
    ("POST", "/api/v1/team/lobby/leave"): (200, "ok"),
    ("POST", "/api/v1/ovt/lobby/leave"): (200, "ok"),
    ("GET", "/api/v1/presence/ping"): (200, "keys:"),
    ("GET", "/api/v1/series/active"): (200, "keys:series"),
    ("GET", "/api/v1/team/series/{series_id}/state"): (200, "canceled"),
    ("GET", "/api/v1/mod/check/{steam_id}"): (200, "banned=True"),
    ("GET", "/api/v1/internal/recent-bans"): (200, "bans"),
}


def _n8_word(r):
    try:
        j = r.json()
    except ValueError:
        return r.text[:60]
    if not isinstance(j, dict):
        return type(j).__name__
    for k in ("detail", "status", "result", "error"):
        if isinstance(j.get(k), str):
            return j[k]
    if "banned" in j:
        return "banned=%s" % j["banned"]
    if isinstance(j.get("bans"), list):
        return "bans"
    return "keys:" + ",".join(sorted(j))


def _n8_requests(p, ids):
    """(method, path) -> (url, keyword arguments) of each route's own request."""
    sid, q, held = p.sid, {"steam_id": p.sid}, {"X-Session-Token": TOKEN}
    return {
        ("POST", "/api/v1/auth/steam"): ("/api/v1/auth/steam", {"json": {"steam_id": sid, "ticket_hex": "00"}}),
        ("DELETE", "/api/v1/players/{steam_id}/data"): None,   # test_ban_answers_pg._delete, the token held
        ("POST", "/api/v1/queue/join"): ("/api/v1/queue/join", {"json": {"steam_id": sid}, "headers": held}),
        ("POST", "/api/v1/tournaments/{tournament_id}/unsignup"): (
            "/api/v1/tournaments/%s/unsignup" % ids["tournament"], {"json": {"steam_id": sid}, "headers": held}),
        ("POST", "/api/v1/spectate/leave"): (
            "/api/v1/spectate/leave", {"json": {"steam_id": sid, "lease_id": ids["lease"]}, "headers": held}),
        ("POST", "/api/v1/queue/leave"): ("/api/v1/queue/leave", {"params": q, "headers": held}),
        ("POST", "/api/v1/queue/decline"): (
            "/api/v1/queue/decline", {"json": {"steam_id": sid, "opponent_steam_id": ids["opponent"]},
                                      "headers": held}),
        ("POST", "/api/v1/queues/escape"): ("/api/v1/queues/escape", {"params": q, "headers": held}),
        ("POST", "/api/v1/team/queue/leave"): ("/api/v1/team/queue/leave", {"params": q, "headers": held}),
        ("POST", "/api/v1/ovt/queue/leave"): ("/api/v1/ovt/queue/leave", {"params": q, "headers": held}),
        ("POST", "/api/v1/ffa/queue/leave"): ("/api/v1/ffa/queue/leave", {"params": q, "headers": held}),
        ("POST", "/api/v1/team/lobby/leave"): ("/api/v1/team/lobby/leave", {"params": q, "headers": held}),
        ("POST", "/api/v1/ovt/lobby/leave"): ("/api/v1/ovt/lobby/leave", {"params": q, "headers": held}),
        ("GET", "/api/v1/presence/ping"): ("/api/v1/presence/ping", {"params": q, "headers": held}),
        ("GET", "/api/v1/series/active"): ("/api/v1/series/active", {}),
        ("GET", "/api/v1/team/series/{series_id}/state"): ("/api/v1/team/series/%s/state" % ids["series"], {}),
        ("GET", "/api/v1/mod/check/{steam_id}"): ("/api/v1/mod/check/%s" % sid, {}),
        ("GET", "/api/v1/internal/recent-bans"): (
            "/api/v1/internal/recent-bans", {"headers": {"X-Internal-Key": INTERNAL_KEY}}),
    }


def test_v5_no_answer_to_the_banned_account_holds_either_text(monkeypatch):
    """V5, and N8 of RULING-BAN-RECORD-R1 with FX2: each route's own request; its banned answer asserted
    FIRST (N8_ANSWERS); then no answer holds the details or the kept name. Mutants: the sign-in's banned
    answer holding the details; /mod/check's answer holding them."""
    marks = ("Zq7DetailsMark", "Zq7NameMark")

    async def body(env):
        _open(env)
        _armed(env)
        env.mp.setattr(main, "_check_steam_session", _REAL_SESSION_CHECK)
        admin = await _admin(env)
        p = await _account(env)
        opponent = await env.player("N8 Opponent")
        seats = [await env.player("N8 Seat %d" % i) for i in range(3)]
        tid = await TR._tournament(env, "voting")
        await TR._signup(env, tid, p)
        await env.conn.execute("UPDATE players SET display_name = $1 WHERE id = $2", marks[1], p.id)
        await _session(env, p.sid)
        answers = []
        known = {(m, r.path) for r in main.app.routes if hasattr(r, "methods") for m in r.methods}
        async with _client(env) as c:
            await _ban(c, admin, p.sid, reason="plain reason")
            r = await _details(c, admin, p.sid, details="the details " + marks[0])
            assert r.status_code == 200, r.text
            row = await _row(env, p.sid)
            assert (marks[0] in row["details"], row["display_name_at_ban"]) == (True, marks[1]), row
            left = await env.conn.fetchval("SELECT count(*) FROM steam_sessions WHERE steam_id = $1", p.sid)
            assert left == 0, "the ban deletes the account's sessions; %d left" % left
            await env.conn.execute("UPDATE players SET display_name = 'Shown Name' WHERE id = $1", p.id)
            series = uuid.uuid4()
            await env.conn.execute(
                "INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id, status, created_at)"
                " VALUES ($1, $2, $3, $4, $5, 'canceled', NOW())", series, p.id, *[s.id for s in seats])
            ids = {"tournament": str(tid), "lease": str(uuid.uuid4()), "opponent": opponent.sid,
                   "series": str(series)}
            for (method, path), req in sorted(_n8_requests(p, ids).items()):
                assert (method, path) in known, (method, path)
                if req is None:
                    r = await asyncio.wait_for(_delete(c, p, token=TOKEN), BOUND)
                else:
                    r = await c.request(method, req[0], **req[1])
                answers.append((method, path, r.status_code, _n8_word(r), r.text))
        return answers
    out = {}

    async def run(env):
        out["v"] = await body(env)
    case(monkeypatch, run, prefix="banrec")
    answers = out["v"]
    for m, p, s, w, t in answers:
        print("[N8] %-6s %-48s %s %-30s %s" % (m, p, s, w[:30], t[:140]))
    routes = _routes_answering_a_banned_account()
    assert sorted(N8_ANSWERS) == routes and sorted((m, p) for m, p, *_ in answers) == routes, routes
    # FIRST: each route's banned answer, its status and its word
    wrong = [(m, p, (s, w), N8_ANSWERS[(m, p)]) for m, p, s, w, _t in answers
             if s != N8_ANSWERS[(m, p)][0] or not w.startswith(N8_ANSWERS[(m, p)][1])]
    assert wrong == [], wrong
    held = [(m, p, s) for m, p, s, _w, t in answers if any(k in t for k in marks)]
    assert held == [], held
    by = {(m, p): t for m, p, _s, _w, t in answers}
    check = json.loads(by[("GET", "/api/v1/mod/check/{steam_id}")])
    assert check["banned"] is True and check["ban_reason"] == "plain reason", check
    feed = json.loads(by[("GET", "/api/v1/internal/recent-bans")])
    assert any(b["reason"] == "plain reason" for b in feed["bans"]), feed


# -- V6: the account deletion -----------------------------------------------------------------------

async def _texted_ended_ban(env, c, admin, p):
    """A ban of p with both texts (each holding p's id), one ban_details
    record, then ended; its id."""
    await _ban(c, admin, p.sid)
    ban_id = (await _row(env, p.sid))["id"]
    r = await _details(c, admin, p.sid, details="alt of %s, seen twice" % p.sid, name="Alias %s x" % p.sid)
    assert r.status_code == 200, r.text
    await _end(env, ban_id)
    return ban_id


def test_v6_the_deletion_after_an_ended_ban_clears_the_record(monkeypatch):
    async def body(env):
        _armed(env)
        env.mp.setattr(main, "ADMIN_HMAC_SECRET", ADMIN_SECRET)
        admin = await _admin(env)
        p = await _account(env)
        async with _client(env) as c:
            ban_id = await _texted_ended_ban(env, c, admin, p)
            await _session(env, p.sid)   # after the ban: the ban writer ends the account's sessions
            before = (await _row(env, p.sid), await _records(env, ban_id))
            r = await asyncio.wait_for(_delete(c, p, token=TOKEN), BOUND)
            listed = (await _list(c, admin)).json()
        return r.status_code, r.json(), before, await _row(env, p.sid), await _records(env, ban_id), listed
    out = {}

    async def run(env):
        out["v"] = await body(env)
    case(monkeypatch, run, prefix="banrec")
    st, ans, (row0, recs0), row, recs, listed = out["v"]
    assert st == 200 and ans["status"] == "anonymized", (st, ans)
    assert row0["details"] and row0["display_name_at_ban"] and row0["details_at"], row0
    assert (row["display_name_at_ban"], row["details"], row["details_at"]) == (None, None, None), row
    assert (row["reason"], row["banned_at"], row["expires_at"]) == (row0["reason"], row0["banned_at"],
                                                                    row0["expires_at"]), row
    assert len(recs) == 1 and recs[0]["target_steam_id"] == ans["placeholder"], recs
    # N1 with N6: the record held the words alone before the deletion and holds the same after it
    assert recs[0]["d"] == recs0[0]["d"] == {"ban_id": str(row["id"]), "details_change": "added",
                                              "name_change": "changed"}, (recs0, recs)
    assert modlog.sentence("ban_details", recs[0]["d"]) == "Ban details added and kept name changed."
    assert listed["bans"] == [], listed


def test_v6_a_failure_after_the_statement_leaves_the_texts(monkeypatch):
    """The deletion's own transaction: a statement that fails after the
    clearing (the ledger's insert, made to fail) rolls the clearing back."""
    async def body(env):
        _armed(env)
        env.mp.setattr(main, "ADMIN_HMAC_SECRET", ADMIN_SECRET)
        admin = await _admin(env)
        p = await _account(env)
        async with _client(env) as c:
            ban_id = await _texted_ended_ban(env, c, admin, p)
            await _session(env, p.sid)   # after the ban: the ban writer ends the account's sessions
            before = (await _row(env, p.sid), await _records(env, ban_id))
            with env.rewriting("INSERT INTO deleted_steam_ids", "INSERT INTO deleted_steam_ids_absent") as hits:
                r = await asyncio.wait_for(_delete(c, p, token=TOKEN), BOUND)
        return r.status_code, len(hits), before, (await _row(env, p.sid), await _records(env, ban_id))
    out = {}

    async def run(env):
        out["v"] = await body(env)
    case(monkeypatch, run, prefix="banrec")
    st, hits, before, after = out["v"]
    assert st >= 500 and hits >= 1, (st, hits)
    assert after == before, (before, after)


# -- N1 with N6 (RULING-BAN-RECORD-R1 section 1): no record of the moderator log holds a ban's text ------------

N1_MARKS = ("Zq8DetailsMark", "Zq8NameMark")
N1_DISCORD = "870000000000000001"
N1_SAVES = [   # (the save, its fields, the words its record holds); every old and new text carries a mark
    ("details added", {"details": "Zq8DetailsMark one"}, {"details_change": "added"}),
    ("details changed", {"details": "Zq8DetailsMark two"}, {"details_change": "changed"}),
    ("details cleared", {"details": ""}, {"details_change": "cleared"}),
    ("name changed", {"name": "Zq8NameMark One"}, {"name_change": "changed"}),
    ("name cleared", {"name": ""}, {"name_change": "cleared"}),
    ("name added", {"name": "Zq8NameMark Two"}, {"name_change": "added"}),
    ("both in one call", {"details": "Zq8DetailsMark three", "name": "Zq8NameMark Three"},
     {"details_change": "added", "name_change": "changed"}),
]


async def _n1_saves(env, c, admin, p):
    """p banned with its kept name holding the name's mark, then the seven saves of N1_SAVES; the ban's id."""
    await env.conn.execute("UPDATE players SET display_name = 'Zq8NameMark Live' WHERE id = $1", p.id)
    await _ban(c, admin, p.sid)
    ban_id = str((await _row(env, p.sid))["id"])
    for label, fields, _words in N1_SAVES:
        r = await _details(c, admin, p.sid, **fields)
        assert r.status_code == 200, (label, r.status_code, r.text)
    return ban_id


async def _n1_marks_held(env):
    """Each mark that stands in any row of player_bans and of admin_actions, the row cast to text."""
    return {table: [m for m in N1_MARKS if await env.conn.fetchval(
        "SELECT count(*) FROM " + table + " t WHERE strpos(CAST(t AS text), $1) > 0", m)]
        for table in ("player_bans", "admin_actions")}


def test_n1_t1_each_save_writes_a_record_of_the_words_alone(monkeypatch):
    """T1: after each kind of save (details added, changed, cleared; name added, changed, cleared; both in one
    call) the written admin_actions row is read from the table. The reach first: one record per save, in
    order. Its details hold exactly the ban's id and the words of which texts changed, and neither mark stands
    anywhere in the row cast to text. Mutants: new_details back into the record; old_name back."""
    out = {}

    async def body(env):
        _open(env)
        admin = await _admin(env)
        p = await env.player("N1 Account")
        async with _client(env) as c:
            out["ban_id"] = await _n1_saves(env, c, admin, p)
        out["rows"] = [dict(r) for r in await env.conn.fetch(
            "SELECT CAST(a.details AS text) AS d, CAST(a AS text) AS whole FROM admin_actions a"
            " WHERE a.action = 'ban_details' AND a.details->>'ban_id' = $1 ORDER BY a.created_at, a.id",
            out["ban_id"])]
    case(monkeypatch, body, prefix="banrec")
    rows = out["rows"]
    for (label, _f, _w), r in zip(N1_SAVES, rows):
        print("[T1] %-18s %s" % (label, r["d"]))
    assert len(rows) == len(N1_SAVES), [r["d"] for r in rows]
    keys = [(label, json.loads(r["d"])) for (label, _f, _w), r in zip(N1_SAVES, rows)]
    assert keys == [(label, {"ban_id": out["ban_id"], **words}) for label, _f, words in N1_SAVES], keys
    held = [(label, m) for (label, _f, _w), r in zip(N1_SAVES, rows) for m in N1_MARKS if m in r["whole"]]
    assert held == [], held


def test_n1_t2_the_logs_three_reads_hold_the_record_and_no_text(monkeypatch):
    """T2: after T1's saves, the moderator log's three reads, each with its own credentials: the admin list
    of actions and the moderator log (each with its admin signature), and the bot's twin (the internal key and
    the admin's linked Discord id). Each answers 200 and holds the ban's ban_details record, its id (asserted
    first), and no mark. Mutant: new_details back into the record (red on all three)."""
    out = {}

    async def body(env):
        _open(env)
        admin = await _admin(env)
        await env.conn.execute("UPDATE players SET discord_id = $1 WHERE steam_id = $2", N1_DISCORD, admin)
        p = await env.player("N1 Account")
        async with _client(env) as c:
            out["ban_id"] = await _n1_saves(env, c, admin, p)
            reads = {
                "/api/v1/admin/actions": ({"admin_steam_id": admin, "action": "ban_details", "target_steam_id": p.sid,
                                           "hmac_signature": _sig(admin, "admin_actions_list", "")}, {}),
                "/api/v1/admin/modlog": ({"admin_steam_id": admin, "action": "ban_details", "player": p.sid,
                                          "hmac_signature": _sig(admin, "modlog_list", "")}, {}),
                "/api/v1/internal/modlog": ({"action": "ban_details", "player": p.sid},
                                            {"X-Internal-Key": INTERNAL_KEY, "X-Actor-Discord-Id": N1_DISCORD}),
            }
            out["reads"] = {}
            for path, (params, headers) in reads.items():
                r = await c.get(path, params=params, headers=headers)
                out["reads"][path] = (r.status_code, r.text)
    case(monkeypatch, body, prefix="banrec")
    for path, (st, t) in out["reads"].items():
        print("[T2] %-26s %s %s" % (path, st, t[:160]))
    reached = {path: (st, out["ban_id"] in t) for path, (st, t) in out["reads"].items()}
    assert reached == {path: (200, True) for path in reached}, reached
    held = {path: [m for m in N1_MARKS if m in t] for path, (_st, t) in out["reads"].items()}
    assert held == {path: [] for path in held}, held


def test_n1_t3_a_key_inside_its_bans_id_leaves_no_mark_after_the_deletion(monkeypatch):
    """T3, the review's state: an account whose key stands as a whole token inside its ban's id (key 1234, ban
    id aaaaaaaa-1234-4aaa-8aaa-aaaaaaaaaaaa, a details record), the ban ended, then the account deleted. The
    reach first: both marks stood in player_bans before, and the deletion answered anonymized. After it no row
    of player_bans and none of admin_actions holds a mark."""
    key, ban_id = "1234", uuid.UUID("aaaaaaaa-1234-4aaa-8aaa-aaaaaaaaaaaa")
    out = {}

    async def body(env):
        _open(env)
        _armed(env)
        admin = await _admin(env)
        p = await env.player("N1 Key Account")
        await env.conn.execute("UPDATE players SET steam_id = $1 WHERE id = $2", key, p.id)
        await env.conn.execute(
            "INSERT INTO player_bans (id, steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
            " VALUES ($1, $2, 'n1 t3', $3, NOW() - INTERVAL '10 minutes', NOW() + INTERVAL '1 day')", ban_id, key, admin)
        async with _client(env) as c:
            r = await _details(c, admin, key, details="Zq8DetailsMark t3", name="Zq8NameMark T3")
            assert r.status_code == 200, r.text
            out["record"] = [x["d"] for x in await _records(env, ban_id)]
            out["before"] = await _n1_marks_held(env)
            await _end(env, ban_id)
            await _session(env, key)
            r = await asyncio.wait_for(_delete(c, SimpleNamespace(sid=key, id=p.id), token=TOKEN), BOUND)
            out["deleted"] = (r.status_code, r.json())
        out["after"] = await _n1_marks_held(env)
    case(monkeypatch, body, prefix="banrec")
    print("[T3]", out)
    assert out["before"]["player_bans"] == list(N1_MARKS), out["before"]
    assert out["deleted"][0] == 200 and out["deleted"][1]["status"] == "anonymized", out["deleted"]
    assert out["after"] == {"player_bans": [], "admin_actions": []}, out["after"]


def test_n1_t4_the_deletion_clears_the_three_columns_on_every_ban_row(monkeypatch):
    """T4: an account with three ban rows, the two ended ones holding details and a kept name, the newest lifted
    holding its kept name. The reach first: the rows held them, and the deletion answered anonymized. After it
    all three hold null in the three columns. Mutant: the first statement of _ban_record_forget limited to the
    newest row."""
    three = ("display_name_at_ban", "details", "details_at")
    read = "SELECT id, " + ", ".join(three) + " FROM player_bans WHERE id = ANY($1::uuid[])"
    out = {}

    async def body(env):
        _open(env)
        _armed(env)
        admin = await _admin(env)
        p = await _account(env)
        ids = []
        async with _client(env) as c:
            for n in (1, 2):
                await _ban(c, admin, p.sid)
                ids.append((await _row(env, p.sid))["id"])
                r = await _details(c, admin, p.sid, details="Zq8DetailsMark %d" % n, name="Zq8NameMark %d" % n)
                assert r.status_code == 200, r.text
                await _end(env, ids[-1])
            await _ban(c, admin, p.sid)
            ids.append((await _row(env, p.sid))["id"])
            await _end(env, ids[-1], lifted=True)
            await _session(env, p.sid)   # after the bans: the ban writer ends the account's sessions
            out["before"] = {str(r["id"]): [r[k] for k in three] for r in await env.conn.fetch(read, ids)}
            r = await asyncio.wait_for(_delete(c, p, token=TOKEN), BOUND)
            out["deleted"] = (r.status_code, r.json())
        out["after"] = {str(r["id"]): [r[k] for k in three] for r in await env.conn.fetch(read, ids)}
        out["ids"] = [str(i) for i in ids]
    case(monkeypatch, body, prefix="banrec")
    print("[T4]", out)
    first, second, newest = out["ids"]
    assert len(out["before"]) == 3 and all(all(out["before"][i]) for i in (first, second)), out["before"]
    assert out["before"][newest][0] == "Ban Answers P" and out["before"][newest][1:] == [None, None], out["before"]
    assert out["deleted"][0] == 200 and out["deleted"][1]["status"] == "anonymized", out["deleted"]
    assert out["after"] == {i: [None, None, None] for i in out["ids"]}, out["after"]
