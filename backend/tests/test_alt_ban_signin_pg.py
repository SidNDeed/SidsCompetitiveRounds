"""ALT-BAN-1 step 4: the recording of a verified connection of an account
under an active ban (Sid's asks B7 and B8), against a real PostgreSQL.

A banned account's sign-in is refused by steam_auth's early gate before it
asks Steam. On that refusal, and before it is raised, _alt_ban_refused may
ask Steam to verify the ticket the request carries and record through
_ban_ticket_seen: the lane's three tables and migration 431's ban_regions.
The cases sign in through the real handler (main.steam_auth, the Steam call
stubbed, the region file a stand-in written by mmdb_standin) and check:

- the refusal the client receives is the same, byte for byte (status, body,
  headers, and the rendered response), over eleven cases (bar A1);
- no identity key, transaction or lock is held while Steam is asked or the
  region is read (bar A2);
- nothing is recorded without both sentences in the notice, a verified
  ticket for this id, an active ban read under the key, or an address the
  lane marks (bar A3);
- no address, city, key or mark in any stored text or printed line, and a
  region only for an account under an active ban (bar A4).

One case schema for the module, built by the ladder harness's procedure
(test_title_ladder_hooks_live._build), with the record test's fault table
and a fault trigger on each of the four tables, sealed, dropped at the end:

    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>

Ids are synthetic (below the first individual-account SteamID64); the
addresses are public resolver service addresses or private ones; the place
names are invented.
"""
import ast
import asyncio
import base64
import builtins
import inspect
import os
import re
import sys
import textwrap
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.exception_handlers import http_exception_handler  # noqa: E402
from sqlalchemy import text  # noqa: E402

import main  # noqa: E402
import alt_signals as A  # noqa: E402
import geo_region as G  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402
import mmdb_standin as S  # noqa: E402
import test_alt_signals_delete_pg as D  # noqa: E402
import test_alt_signals_record_pg as R  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402

V4 = "1.1.1.1"           # Ardenmark, Vellshire
V4_ALONE = "1.0.0.1"     # Brynmoor (no subdivision)
V4_CITY = "8.8.8.8"      # Ardenmark, Vellshire, with a city the reader never returns
V4_NONE = "9.9.9.9"      # not in the file
LAN = "10.0.0.1"
CITY = "Harrowgate"
REASON = "alt-ban"
TABLES = ("steam_signin_facts", "steam_family_shares", "conn_markers", "ban_regions")
STEAM_KEY = "alt-ban-steam-key"
_BAN_LINE = re.compile(r"^\[ALT-BAN\] (not verified|not recorded): [A-Za-z_][A-Za-z0-9_]*$")

_REGION_FAULT = """
CREATE TRIGGER alt_test_fault BEFORE INSERT OR UPDATE ON ban_regions
  FOR EACH ROW EXECUTE FUNCTION alt_test_fault();
"""


def _faq_both():
    return "message one\n\n" + A.NOTICE_BAN


# -- the case -------------------------------------------------------------------

@pytest.fixture(scope="module")
def case():
    lh._require_live_pg()
    built = {}

    async def extra(conn, schema):
        await conn.execute(R._FAULTS_DDL)
        await conn.execute(_REGION_FAULT)

    async def build():
        c = harness.CaseSchema(lh.DSN, "alt_ban")
        await c.__aenter__()
        try:
            await lh._build(c, extra)
            for t in TABLES:
                assert await c.conn.fetchval("SELECT to_regclass($1) IS NOT NULL", t), t
            await c.conn.execute(
                "INSERT INTO pending_channel_posts (channel_id, content, sort_order, revision, posted_revision)"
                " VALUES ($1, $2, 1, 4, 4)", R.FAQ_CHANNEL, _faq_both())
        except BaseException:
            await c.__aexit__(None, None, None)
            raise
        built.update(schema=c.schema, own=c.own)
        await c.conn.close()
    R._run(build())
    try:
        yield built["schema"]
    finally:
        async def drop():
            conn = await harness.connect_bound(lh.DSN, built["schema"])
            try:
                await harness.drop_case_schema(conn, built["schema"], built["own"])
            finally:
                await conn.close()
        R._run(drop())


class _Steam:
    """The Steam call's stand-in: records each call (the URL is never
    printed: it carries the key) and answers OK for `sid` unless told
    otherwise. With a gate, each call sets `entered` and waits for
    `release` (in the worker thread steam_auth's helper runs it in)."""

    def __init__(self):
        self.calls, self.params, self.fault, self.delay, self.gate = [], None, None, 0.0, None

    def __call__(self, url, timeout):
        self.calls.append((url, timeout))
        if self.gate is not None:
            self.gate[0].set()
            self.gate[1].wait(20)
        if self.delay:
            time.sleep(self.delay)
        if self.fault is not None:
            raise self.fault
        return {"response": {"params": dict(self.params or {})}}


@pytest.fixture
def env(monkeypatch, tmp_path):
    """The signal key loaded, the Steam key set and the call stubbed, the
    spacings and the notice line reset, a stand-in region file in place."""
    steam = _Steam()
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", R.HMAC_KEY)
    monkeypatch.setenv("STEAM_WEB_API_KEY", STEAM_KEY)
    monkeypatch.delenv("STEAM_AUTH_ENFORCE", raising=False)
    monkeypatch.setattr(main, "_steam_http_get_json", steam)
    monkeypatch.setattr(main, "_alt_ban_asked", {"all": None, "ids": {}})
    monkeypatch.setattr(main, "_alt_ban_reading", {"word": None, "region": None, "steam": None})
    folder = tmp_path / "geo"
    folder.mkdir()
    (folder / "region.mmdb").write_bytes(S.build([
        (V4, S.place("Ardenmark", "Vellshire")),
        (V4_ALONE, S.place("Brynmoor")),
        (V4_CITY, S.place("Ardenmark", "Vellshire", city={"names": {"en": CITY}})),
    ]).data)
    monkeypatch.setattr(G, "_rgn_DIR", str(folder))
    monkeypatch.setattr(G, "_rgn_kept", None)
    A.install_key(R.KEY_HEX)
    main._alt_notice_line_at[0] = None
    monkeypatch.steam, monkeypatch.geo = steam, folder
    yield monkeypatch
    A.install_key(None)
    main._alt_notice_line_at[0] = None


async def _ban(sm, sid, hours=1):
    async with sm() as db:
        admin = R._sid()
        await lh._insert(db, "admin_users", {"steam_id": admin})
        await lh._insert(db, "players", {"id": uuid.uuid4(), "steam_id": sid,
                                         "display_name": "ab-" + sid[-4:]})
        await db.execute(text(
            "INSERT INTO player_bans (id, steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
            " VALUES (:id, :s, :r, :a, NOW(), NOW() + make_interval(hours => CAST(:h AS integer)))"),
            {"id": uuid.uuid4(), "s": sid, "r": REASON, "a": admin, "h": hours})
        await db.commit()


async def _lift(sm, sid):
    async with sm() as db:
        await db.execute(text("UPDATE player_bans SET unbanned_at = NOW() WHERE steam_id = :s"), {"s": sid})
        await db.commit()


async def _notice(sm, content, revision=4, posted=4):
    fid = await R._faq_id(sm)
    async with sm() as db:
        await db.execute(text(
            "UPDATE pending_channel_posts SET content = :t, revision = :r, posted_revision = :p WHERE id = :id"),
            {"t": content, "r": revision, "p": posted, "id": fid})
        await db.commit()


async def _rows(sm, sid):
    async with sm() as db:
        return [(await db.execute(text("SELECT count(*) FROM %s WHERE steam_id = :s" % t),
                                  {"s": sid})).scalar() for t in TABLES]


async def _regions(sm, sid):
    async with sm() as db:
        return [tuple(r) for r in (await db.execute(text(
            "SELECT region, conn_class FROM ban_regions WHERE steam_id = :s ORDER BY region, conn_class"),
            {"s": sid})).all()]


async def _every_text(sm, sid):
    """Every stored value of the account's rows of the four tables, as text."""
    out = []
    async with sm() as db:
        for t in TABLES:
            out += [str(r[0]) for r in (await db.execute(text(
                "SELECT x::text FROM %s x WHERE x.steam_id = :s" % t), {"s": sid})).all()]
    return out


async def _sign_in(sm, sid, host=V4, owner=None, steam_sid=None):
    """The refusal steam_auth raises for a banned account (or its answer)."""
    main_steam = main._steam_http_get_json
    main_steam.params = R._params(steam_sid or sid, owner=owner)
    async with sm() as db:
        req = main.SteamAuthRequest(steam_id=sid, ticket_hex="abcd", mod_version="1.41.0")
        try:
            return await main.steam_auth(req=req, db=db, request=R._request(host))
        except HTTPException as e:
            return e


def _baseline():
    return HTTPException(status_code=409, detail=main._ban_gate_detail(REASON))


async def _same_refusal(got):
    """The refusal equals the one the gate gives with no recording at all:
    status, body, headers, and the rendered response's bytes."""
    want = _baseline()
    assert isinstance(got, HTTPException), got
    assert (got.status_code, got.detail, got.headers) == (want.status_code, want.detail, want.headers)
    a = await http_exception_handler(R._request(V4), got)
    b = await http_exception_handler(R._request(V4), want)
    assert (a.status_code, a.body, a.raw_headers) == (b.status_code, b.body, b.raw_headers)


def _caught(monkeypatch):
    """Every print() made while a case runs (the real print still runs)."""
    said, real = [], builtins.print

    def spy(*args, **kw):
        said.append(" ".join(str(a) for a in args))
        return real(*args, **kw)
    monkeypatch.setattr(builtins, "print", spy)
    return said


def _guarded(said, *names):
    """Each line is one of the closed forms and none names an id, an
    address, a key, a city or a mark."""
    for ln in said:
        assert (_BAN_LINE.match(ln) or R._LINE.match(ln)
                or any(rx.match(ln) for rx in R.ADMITTED)), ln
        for word in names + (STEAM_KEY, R.KEY_HEX, CITY, "Ardenmark", "Brynmoor", V4, V4_ALONE, V4_CITY):
            assert word not in ln, (word, ln)


# -- A1: the refusal is the same over eleven cases ---------------------------------

def _no_signal_key(env, sm, sid):
    A.install_key(None)


def _no_steam_key(env, sm, sid):
    env.delenv("STEAM_WEB_API_KEY")


async def _notice_closed(env, sm, sid):
    await _notice(sm, "message one")


async def _notice_lane_alone(env, sm, sid):
    await _notice(sm, "message one\n\n" + A.DISCLOSURE)


def _spacing_held(env, sm, sid):
    main._alt_ban_asked["ids"][sid] = time.monotonic() + 600


def _steam_ok(env, sm, sid):
    pass


def _another_id(env, sm, sid):
    env.steam_sid = R._sid()


def _steam_error(env, sm, sid):
    env.steam.fault = OSError("planted")


def _late(env, sm, sid):
    env.setattr(main, "_ALT_BAN_LATE_S", 0.2)
    env.steam.delay = 0.4


def _region_file_cut(env, sm, sid):
    f = env.geo / "region.mmdb"
    f.write_bytes(f.read_bytes()[:100])


async def _every_upsert_failing(env, sm, sid):
    for t in TABLES:
        await R._fault(sm, t, "22012")


# name -> (setup, Steam calls, rows of the four tables)
ELEVEN = {
    "no signal key": (_no_signal_key, 0, [0, 0, 0, 0]),
    "no Steam key": (_no_steam_key, 0, [0, 0, 0, 0]),
    "notice closed": (_notice_closed, 0, [0, 0, 0, 0]),
    "notice of the lane alone": (_notice_lane_alone, 0, [0, 0, 0, 0]),
    "spacing held": (_spacing_held, 0, [0, 0, 0, 0]),
    "Steam OK": (_steam_ok, 1, [1, 1, 1, 1]),
    "another id": (_another_id, 1, [0, 0, 0, 0]),
    "Steam error": (_steam_error, 1, [0, 0, 0, 0]),
    "late": (_late, 1, [0, 0, 0, 0]),
    "region file cut": (_region_file_cut, 1, [1, 1, 1, 0]),
    "every upsert failing": (_every_upsert_failing, 1, [0, 0, 0, 0]),
}


@pytest.mark.parametrize("name", list(ELEVEN))
def test_the_refusal_is_the_same_whatever_the_recording_does(case, env, name):
    setup, calls, rows = ELEVEN[name]
    sid, owner = R._sid(), R._sid()
    env.steam_sid = None
    said = _caught(env)

    async def body(sm, rsm):
        await _ban(sm, sid)
        try:
            got = setup(env, sm, sid)
            if inspect.isawaitable(got):
                await got
            refusal = await _sign_in(sm, sid, owner=owner, steam_sid=env.steam_sid)
            await _same_refusal(refusal)
            return await _rows(sm, sid)
        finally:
            await _notice(sm, _faq_both())
            for t in TABLES:
                await R._fault(sm, t, None)

    got = R._with(case, body)
    assert len(env.steam.calls) == calls, (name, env.steam.calls and "called")
    assert got == rows, (name, got)
    _guarded(said, sid, owner)


def test_the_refusal_raised_is_the_gates_own_object(case, env):
    """The route raises the very exception the gate raised (a bare raise),
    after the recording ran."""
    sid = R._sid()
    seen = []
    orig = main._ban_gate_or_raise

    async def gate(db, steam_id, *a, **kw):
        try:
            await orig(db, steam_id, *a, **kw)
        except HTTPException as e:
            seen.append(e)
            raise
    env.setattr(main, "_ban_gate_or_raise", gate)

    async def body(sm, rsm):
        await _ban(sm, sid)
        return await _sign_in(sm, sid)

    got = R._with(case, body)
    assert seen and got is seen[0]
    assert len(env.steam.calls) == 1


def test_the_ask_stands_before_the_answer(case, env):
    """Steam was asked by the time the refusal reached the caller: the
    recording is not left running after the answer."""
    sid = R._sid()

    async def body(sm, rsm):
        await _ban(sm, sid)
        got = await _sign_in(sm, sid)
        asked = len(env.steam.calls)
        rows = await _rows(sm, sid)
        return got, asked, rows

    got, asked, rows = R._with(case, body)
    assert isinstance(got, HTTPException) and asked == 1 and rows == [1, 0, 1, 1]


# -- A2: nothing held while Steam is asked or the region is read ---------------------

async def _held(sm, sid):
    """(key free, transactions open in this database other than the probe's)."""
    async with sm() as probe:
        free = (await probe.execute(text(
            "SELECT pg_try_advisory_xact_lock(hashtext(CAST(:s AS text)))"), {"s": sid})).scalar()
        open_ = (await probe.execute(text(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
            " AND pid <> pg_backend_pid() AND state LIKE 'idle in transaction%'"))).scalar()
        locks = (await probe.execute(text(
            "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid"
            " WHERE a.datname = current_database() AND l.pid <> pg_backend_pid()"
            " AND l.locktype IN ('advisory', 'relation', 'tuple', 'transactionid')"))).scalar()
        await probe.rollback()
    return free, open_, locks


async def _wait(event):
    for _ in range(200):
        if event.is_set():
            return True
        await asyncio.sleep(0.05)
    return False


def test_no_key_transaction_or_lock_is_held_while_steam_is_asked(case, env):
    sid = R._sid()
    entered, release = threading.Event(), threading.Event()
    env.steam.gate = (entered, release)

    async def body(sm, rsm):
        await _ban(sm, sid)
        task = asyncio.create_task(_sign_in(sm, sid))
        try:
            assert await _wait(entered), "Steam was never asked"
            held = await _held(sm, sid)
        finally:
            release.set()
        return held, await task, await _rows(sm, sid)

    held, got, rows = R._with(case, body)
    assert held == (True, 0, 0), held
    assert isinstance(got, HTTPException) and rows == [1, 0, 1, 1]


def test_no_key_transaction_or_lock_is_held_while_the_region_is_read(case, env):
    sid = R._sid()
    entered, release = threading.Event(), threading.Event()
    real = G.region_of

    def slow(host):
        entered.set()
        release.wait(20)
        return real(host)
    env.setattr(G, "region_of", slow)

    async def body(sm, rsm):
        await _ban(sm, sid)
        task = asyncio.create_task(_sign_in(sm, sid))
        try:
            assert await _wait(entered), "the region was never read"
            held = await _held(sm, sid)
            # Held past the reader's cut, so the read is one that answers nothing.
            await asyncio.sleep(main._ALT_BAN_REGION_WAIT_S + 0.5)
        finally:
            release.set()
        return held, await task, await _regions(sm, sid)

    held, got, regions = R._with(case, body)
    assert held == (True, 0, 0), held
    assert isinstance(got, HTTPException)
    assert regions == [], "a read past its 1 s answers nothing"


def test_a_region_read_past_its_second_records_the_rest_without_a_region(case, env):
    sid = R._sid()
    real = G.region_of

    def slow(host):
        time.sleep(1.5)
        return real(host)
    env.setattr(G, "region_of", slow)

    async def body(sm, rsm):
        await _ban(sm, sid)
        await _sign_in(sm, sid)
        return await _rows(sm, sid)

    assert R._with(case, body) == [1, 0, 1, 0]


# -- A3: what must hold before anything is recorded -----------------------------------

def test_a_ban_lifted_before_the_recording_records_nothing(case, env, capsys):
    """The active ban is read again under the key: a ban lifted between the
    refusal and the recording records nothing."""
    sid = R._sid()
    orig = main._ban_ticket_seen

    async def body(sm, rsm):
        async def lifted(db, *a, **kw):
            await _lift(sm, sid)
            return await orig(db, *a, **kw)
        env.setattr(main, "_ban_ticket_seen", lifted)
        await _ban(sm, sid)
        got = await _sign_in(sm, sid)
        return got, await _rows(sm, sid)

    got, rows = R._with(case, body)
    assert isinstance(got, HTTPException) and rows == [0, 0, 0, 0]
    assert "[ALT-SIGNALS] not recorded: not_banned" in capsys.readouterr().out.splitlines()


def test_a_ban_that_ended_by_time_records_nothing(case, env):
    sid = R._sid()
    orig = main._ban_ticket_seen

    async def body(sm, rsm):
        async def ended(db, *a, **kw):
            async with sm() as x:
                await x.execute(text(
                    "UPDATE player_bans SET expires_at = NOW() - INTERVAL '1 second',"
                    " banned_at = NOW() - INTERVAL '1 hour' WHERE steam_id = :s"), {"s": sid})
                await x.commit()
            return await orig(db, *a, **kw)
        env.setattr(main, "_ban_ticket_seen", ended)
        await _ban(sm, sid)
        await _sign_in(sm, sid)
        return await _rows(sm, sid)

    assert R._with(case, body) == [0, 0, 0, 0]


def test_a_deleted_account_under_an_active_ban_is_recorded(case, env):
    """No tombstone read: an account whose data was deleted and which is
    still banned is recorded like any other."""
    sid = R._sid()

    async def body(sm, rsm):
        await _ban(sm, sid)
        async with sm() as db:
            await lh._insert(db, "deleted_steam_ids", {"steam_id_hash": main._hash_steam_id(sid)})
            await db.commit()
        await _sign_in(sm, sid)
        return await _rows(sm, sid)

    assert R._with(case, body) == [1, 0, 1, 1]


def test_the_notice_is_read_again_under_the_key(case, env, capsys):
    """A notice that loses the second sentence between the refusal and the
    recording records nothing, and says the hourly line."""
    sid = R._sid()
    orig = main._ban_ticket_seen

    async def body(sm, rsm):
        async def closed(db, *a, **kw):
            await _notice(sm, "message one\n\n" + A.DISCLOSURE)
            return await orig(db, *a, **kw)
        env.setattr(main, "_ban_ticket_seen", closed)
        await _ban(sm, sid)
        try:
            await _sign_in(sm, sid)
            return await _rows(sm, sid)
        finally:
            await _notice(sm, _faq_both())

    assert R._with(case, body) == [0, 0, 0, 0]
    assert R.NOTICE_LINE in capsys.readouterr().out.splitlines()


@pytest.mark.parametrize("host,rows", [(LAN, [1, 0, 0, 0]), ("no client", [1, 0, 0, 0])])
def test_an_address_the_lane_does_not_mark_gets_no_marker_and_no_region(case, env, host, rows):
    sid = R._sid()

    async def body(sm, rsm):
        await _ban(sm, sid)
        await _sign_in(sm, sid, host=host)
        return await _rows(sm, sid)

    assert R._with(case, body) == rows


def test_a_ticket_check_never_runs_for_an_account_under_no_ban(case, env):
    """A non-banned verified sign-in asks Steam once (its own check) and
    stores no region, with the stand-in file in place."""
    sid = R._sid()

    async def body(sm, rsm):
        env.steam.params = R._params(sid)
        async with sm() as db:
            req = main.SteamAuthRequest(steam_id=sid, ticket_hex="abcd", mod_version="1.41.0")
            await main.steam_auth(req=req, db=db, request=R._request(V4))
        return await _rows(sm, sid)

    assert R._with(case, body) == [1, 0, 1, 0]
    assert len(env.steam.calls) == 1


# -- the spacings ------------------------------------------------------------------

def test_after_an_ok_the_account_is_not_asked_again_for_ten_minutes(case, env):
    sid = R._sid()
    env.setattr(main, "_ALT_BAN_SPACE_ALL_S", 0.0)

    async def body(sm, rsm):
        await _ban(sm, sid)
        await _sign_in(sm, sid)
        left = main._alt_ban_asked["ids"][sid] - time.monotonic()
        await _sign_in(sm, sid)
        return left

    left = R._with(case, body)
    assert 590 < left <= 600, left
    assert len(env.steam.calls) == 1


def test_after_anything_else_the_account_is_not_asked_again_for_a_minute(case, env):
    sid = R._sid()
    env.setattr(main, "_ALT_BAN_SPACE_ALL_S", 0.0)
    env.steam.fault = OSError("planted")

    async def body(sm, rsm):
        await _ban(sm, sid)
        await _sign_in(sm, sid)
        left = main._alt_ban_asked["ids"][sid] - time.monotonic()
        await _sign_in(sm, sid)
        return left

    left = R._with(case, body)
    assert 50 < left <= 60, left
    assert len(env.steam.calls) == 1


@pytest.mark.parametrize("spaced", [True, False])
def test_two_accounts_are_asked_at_most_once_in_two_seconds(case, env, spaced):
    """Negative control: with the overall spacing at zero both are asked."""
    one, two = R._sid(), R._sid()
    if not spaced:
        env.setattr(main, "_ALT_BAN_SPACE_ALL_S", 0.0)

    async def body(sm, rsm):
        await _ban(sm, one)
        await _ban(sm, two)
        await _sign_in(sm, one)
        await _sign_in(sm, two)

    R._with(case, body)
    assert len(env.steam.calls) == (1 if spaced else 2)


def test_two_sign_ins_at_once_ask_once(case, env):
    """The spacings are checked again and stamped with no await between:
    a second sign-in of the same account while the first waits on Steam is
    not asked."""
    sid = R._sid()
    entered, release = threading.Event(), threading.Event()
    env.steam.gate = (entered, release)
    # Fix 1, M5: the ticket check's thread holder alone would also keep Steam from a second call; the second
    # sign-in must not reach the ticket check at all (its spacing stamped before the first's ask).
    checks, real = [], main._steam_ticket_check

    async def counted(*a, **k):
        checks.append(1)
        return await real(*a, **k)
    env.setattr(main, "_steam_ticket_check", counted)

    async def body(sm, rsm):
        await _ban(sm, sid)
        first = asyncio.create_task(_sign_in(sm, sid))
        try:
            assert await _wait(entered), "Steam was never asked"
            second = await asyncio.wait_for(_sign_in(sm, sid), 10)
            reached = len(checks)
        finally:
            release.set()
        return await first, second, reached

    first, second, reached = R._with(case, body)
    assert isinstance(first, HTTPException) and isinstance(second, HTTPException)
    assert reached == 1, "the second sign-in reached the ticket check (%d)" % reached
    assert len(env.steam.calls) == 1


# -- turn 2, the FIRST thing (ADD1 H5): each read in a thread holds one thread at most --

def _ended(kind):
    """Wait, bounded, until the read of `kind` in flight has ended (lesson 1297)."""
    held = main._alt_ban_reading[kind]
    if held is not None:
        held.result(timeout=25)


def test_a_steam_check_in_flight_starts_no_second_and_the_refusal_is_the_same(case, env):
    """While one ticket check has not returned, another banned account's
    sign-in starts no second one: it gets the same refusal at once and records
    nothing."""
    one, two = R._sid(), R._sid()
    env.setattr(main, "_ALT_BAN_SPACE_ALL_S", 0.0)
    entered, release = threading.Event(), threading.Event()
    env.steam.gate = (entered, release)

    async def body(sm, rsm):
        await _ban(sm, one)
        await _ban(sm, two)
        first = asyncio.create_task(_sign_in(sm, one))
        try:
            assert await _wait(entered), "Steam was never asked"
            t = time.monotonic()
            second = await asyncio.wait_for(_sign_in(sm, two), 10)
            took = time.monotonic() - t
            asked = len(env.steam.calls)
        finally:
            release.set()
        got = await first
        await asyncio.to_thread(_ended, "steam")
        return second, took, asked, got, await _rows(sm, two)

    second, took, asked, got, rows = R._with(case, body)
    R._run(_same_refusal(second))
    assert isinstance(got, HTTPException)
    assert asked == 1, "a second ticket check was started while one was in flight (%d)" % asked
    assert took < 2.0, "the refusal waited %.2f s" % took
    assert rows == [0, 0, 0, 0], rows


def test_a_region_read_in_flight_starts_no_second_and_the_rest_is_recorded(case, env):
    """While one region read has not returned, another recording starts no
    second one: it records without a region."""
    one, two = R._sid(), R._sid()
    env.setattr(main, "_ALT_BAN_SPACE_ALL_S", 0.0)
    entered, release, reads = threading.Event(), threading.Event(), []
    real = G.region_of

    def slow(host):
        reads.append(1)
        entered.set()
        release.wait(20)
        return real(host)
    env.setattr(G, "region_of", slow)

    async def body(sm, rsm):
        await _ban(sm, one)
        await _ban(sm, two)
        first = asyncio.create_task(_sign_in(sm, one))
        try:
            assert await _wait(entered), "the region was never read"
            second = await asyncio.wait_for(_sign_in(sm, two), 10)
            count = len(reads)
        finally:
            release.set()
        got = await first
        await asyncio.to_thread(_ended, "region")
        return second, count, got, await _regions(sm, two), await _rows(sm, two)

    second, count, got, regions, rows = R._with(case, body)
    assert isinstance(second, HTTPException) and isinstance(got, HTTPException)
    assert count == 1, "a second region read was started while one was in flight (%d)" % count
    assert regions == [] and rows == [1, 0, 1, 0], (regions, rows)


def test_the_stamps_table_drops_what_has_run_out():
    asked = {"all": None, "ids": {"a": 5.0, "b": 15.0}}
    orig = main._alt_ban_asked
    main._alt_ban_asked = asked
    try:
        assert main._alt_ban_spacing("c", 10.0, take=True) is True
        assert set(asked["ids"]) == {"b", "c"} and asked["all"] == 10.0
        assert asked["ids"]["c"] == 10.0 + main._ALT_BAN_SPACE_OK_S
        assert main._alt_ban_spacing("d", 11.0, take=False) is False   # 2 s overall
        assert main._alt_ban_spacing("b", 12.5, take=False) is False   # its own stamp
    finally:
        main._alt_ban_asked = orig


# -- the region (F5, A4) -----------------------------------------------------------

def test_country_and_state_country_alone_and_none(case, env):
    ids = {h: R._sid() for h in (V4, V4_ALONE, V4_NONE)}
    env.setattr(main, "_ALT_BAN_SPACE_ALL_S", 0.0)

    async def body(sm, rsm):
        out = {}
        for host, sid in ids.items():
            await _ban(sm, sid)
            await _sign_in(sm, sid, host=host)
            out[host] = await _regions(sm, sid)
        return out

    got = R._with(case, body)
    assert got == {V4: [("Ardenmark, Vellshire", "unknown")], V4_ALONE: [("Brynmoor", "unknown")],
                   V4_NONE: []}, got


def test_the_class_stands_beside_the_region_as_the_marker_holds_it(case, env):
    sid = R._sid()

    async def body(sm, rsm):
        await _ban(sm, sid)
        await _sign_in(sm, sid)
        async with sm() as db:
            return (await db.execute(text(
                "SELECT (SELECT conn_class FROM conn_markers WHERE steam_id = :s),"
                " (SELECT conn_class FROM ban_regions WHERE steam_id = :s)"), {"s": sid})).one()

    m, r = R._with(case, body)
    assert m == r and r in main._alt_signals.STORED_CLASSES


@pytest.mark.parametrize("own", [False, True])
def test_the_cap_of_fifty_regions(case, env, own):
    """Fifty other regions stand: this one is not stored. Forty-nine others
    and this one stand: its row's last sight moves forward."""
    sid = R._sid()

    async def body(sm, rsm):
        await _ban(sm, sid)
        async with sm() as db:
            n = 49 if own else 50
            for i in range(n):
                await db.execute(text(
                    "INSERT INTO ban_regions (steam_id, region, conn_class, first_at, last_at)"
                    " VALUES (:s, :r, 'unknown', NOW() - INTERVAL '1 day', NOW() - INTERVAL '1 day')"),
                    {"s": sid, "r": "Zone %02d" % i})
            if own:
                await db.execute(text(
                    "INSERT INTO ban_regions (steam_id, region, conn_class, first_at, last_at)"
                    " VALUES (:s, 'Ardenmark, Vellshire', 'unknown', NOW() - INTERVAL '1 day',"
                    " NOW() - INTERVAL '1 day')"), {"s": sid})
            await db.commit()
        await _sign_in(sm, sid)
        async with sm() as db:
            return (await db.execute(text(
                "SELECT count(*), count(*) FILTER (WHERE region = 'Ardenmark, Vellshire'),"
                " count(*) FILTER (WHERE last_at > NOW() - INTERVAL '1 minute')"
                " FROM ban_regions WHERE steam_id = :s"), {"s": sid})).one()

    total, this, fresh = R._with(case, body)
    assert total == 50
    assert (this, fresh) == ((1, 1) if own else (0, 0))


def test_a_replaced_file_is_read_by_its_new_records(case, env):
    """The operator renames a new file over the old one: the next reading
    answers the new file's region."""
    one, two = R._sid(), R._sid()
    env.setattr(main, "_ALT_BAN_SPACE_ALL_S", 0.0)

    async def body(sm, rsm):
        await _ban(sm, one)
        await _ban(sm, two)
        await _sign_in(sm, one)
        new = env.geo / "region.mmdb.new"
        new.write_bytes(S.build([(V4, S.place("Brynmoor", "Kestral Vale"))]).data)
        os.replace(new, env.geo / "region.mmdb")
        await _sign_in(sm, two)
        return await _regions(sm, one), await _regions(sm, two)

    a, b = R._with(case, body)
    assert a == [("Ardenmark, Vellshire", "unknown")] and b == [("Brynmoor, Kestral Vale", "unknown")]


def test_no_address_city_key_or_mark_in_any_stored_text_or_line(case, env):
    sid, owner = R._sid(), R._sid()
    said = _caught(env)

    async def body(sm, rsm):
        await _ban(sm, sid)
        await _sign_in(sm, sid, host=V4_CITY, owner=owner)
        async with sm() as db:
            region_text = [str(r[0]) for r in (await db.execute(text(
                "SELECT x::text FROM ban_regions x WHERE x.steam_id = :s"), {"s": sid})).all()]
        return await _every_text(sm, sid), await _regions(sm, sid), region_text

    stored, regions, region_text = R._with(case, body)
    assert regions == [("Ardenmark, Vellshire", "unknown")]
    for value in stored:
        for word in (CITY, V4_CITY, owner, R.KEY_HEX, STEAM_KEY):
            assert word not in value, (word, value)
    _guarded(said, sid, owner)
    # Fix 1, M6: the marks this connection computes (address, block, the account's own, the lender's), in any
    # form a line or a text could carry them, stand in no printed line and in no text of the region's row.
    key = A.loaded_key()
    seen = A.observe(V4_CITY, key, main._conn_ranges.classify_address, main._conn_ranges.CR_LAN_NETS)
    marks = [seen.addr_mark, seen.block_mark, A.account_mark(key.secret, sid), A.account_mark(key.secret, owner)]
    forms = [f for m in marks for f in (m.hex(), m.hex().upper(), base64.b64encode(m).decode(),
                                        base64.urlsafe_b64encode(m).decode().rstrip("="))]
    for f in forms:
        cut = f[:16]
        assert not any(cut in ln for ln in said), ("a mark in a printed line", cut)
        assert not any(cut in v for v in region_text), ("a mark in the region's row", cut)


# -- account deletion takes the two tables' rows ------------------------------------------

async def _plant_ban_rows(sm, sid, other, third):
    """A region of `sid` and of `other`; notices naming `sid` on each side and
    one between the two others."""
    async with sm() as db:
        for s in (sid, other):
            await db.execute(text("INSERT INTO ban_regions (steam_id, region) VALUES (:s, 'Ardenmark')"), {"s": s})
        for a, b in ((sid, other), (third, sid), (other, third)):
            await db.execute(text("INSERT INTO ban_link_notices (banned_steam_id, other_steam_id)"
                                  " VALUES (:a, :b)"), {"a": a, "b": b})
        await db.commit()


async def _ban_rows(sm, sid):
    async with sm() as db:
        regions = (await db.execute(text("SELECT count(*) FROM ban_regions WHERE steam_id = :s"),
                                    {"s": sid})).scalar()
        notices = (await db.execute(text("SELECT count(*) FROM ban_link_notices"
                                         " WHERE banned_steam_id = :s OR other_steam_id = :s"),
                                    {"s": sid})).scalar()
    return regions, notices


@pytest.mark.parametrize("place", ["no player row", "already deleted", "live"])
def test_account_deletion_takes_its_regions_and_every_notice_naming_it(case, monkeypatch, place):
    """delete_player_data, at each of its three places, deletes the account's
    ban_regions rows and each ban_link_notices row naming it on either side;
    another account's region and a notice between two others stay."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", D.DELETE_SECRET)
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)
    sid, other, third = R._sid(), R._sid(), R._sid()

    async def body(sm, _rsm):
        if place != "no player row":
            await D._player(sm, sid, deleted=(place == "already deleted"))
        await _plant_ban_rows(sm, sid, other, third)
        before = await _ban_rows(sm, sid)
        ans = await D._delete(sm, sid)
        return before, ans, await _ban_rows(sm, sid), await _ban_rows(sm, other)

    before, ans, rows, other_rows = R._with(case, body)
    want = {"no player row": "not_found", "already deleted": "already_deleted", "live": "anonymized"}[place]
    assert ans["status"] == want, ans
    assert before == (1, 2) and rows == (0, 0), (before, rows)
    assert other_rows == (1, 1), other_rows


# -- the Steam helper: the same URL and predicate as steam_auth's ------------------------

def _steam_auth_parts():
    """steam_auth's URL expression and its verification test, from its own
    source."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(main.steam_auth)))
    url = cond = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == ["url"]:
            url = node.value
        if isinstance(node, ast.If) and "params.get(\"result\")" in ast.unparse(node.test).replace("'", "\""):
            cond = node.test
    assert url is not None and cond is not None
    return url, cond


@pytest.mark.parametrize("ticket", ["abcd", "00FF", "0123456789abcdef"])
def test_the_helpers_url_is_steam_auths_url(ticket):
    url, _cond = _steam_auth_parts()
    req = main.SteamAuthRequest(steam_id="76561190427000001", ticket_hex=ticket, mod_version="1.41.0")
    ns = dict(vars(main), key="k-1", req=req)
    assert eval(compile(ast.Expression(url), "<url>", "eval"), ns) == main._steam_ticket_url("k-1", ticket)


BODIES = [
    {"response": {"params": {"result": "OK", "steamid": "76561190427000001"}}},
    {"response": {"params": {"result": "OK", "steamid": "76561190427000002"}}},
    {"response": {"params": {"result": "FAIL", "steamid": "76561190427000001"}}},
    {"response": {"params": {"result": "OK"}}},
    {"response": {"params": {"result": "OK", "steamid": 76561190427000001}}},
    {"response": {"error": {"errorcode": 101}}},
    {"response": {}},
    {},
    None,
]


@pytest.mark.parametrize("i", range(len(BODIES)))
def test_the_helpers_predicate_is_steam_auths_predicate(i):
    _url, cond = _steam_auth_parts()
    body = BODIES[i]
    sid = "76561190427000001"
    params = ((body or {}).get("response") or {}).get("params") or {}
    req = main.SteamAuthRequest(steam_id=sid, ticket_hex="abcd", mod_version="1.41.0")
    theirs = bool(eval(compile(ast.Expression(cond), "<cond>", "eval"), dict(params=params, req=req, str=str)))
    ours = main._steam_ticket_params(body, sid)
    assert theirs == (ours is not None)
    if ours is not None:
        assert ours == params


def test_the_helper_refuses_without_a_key_and_a_hex_ticket(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_steam_http_get_json", lambda u, t: calls.append(1))
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)
    assert asyncio.run(main._steam_ticket_check("abcd", "1")) == (None, "no_key")
    monkeypatch.setenv("STEAM_WEB_API_KEY", "k")
    assert asyncio.run(main._steam_ticket_check("ab&appid=1", "1")) == (None, "bad_ticket")
    assert calls == []


# -- fix 1 of the item's round (M2): a cancelled ask is not an OK ---------------------------------

def test_a_sign_in_cancelled_while_steam_is_asked_leaves_the_minute(case, env):
    """The request is cancelled while its ticket check waits: the account's
    stamp is the 60 s of any outcome that is not a verified OK, never the
    600 s stamped provisionally before the ask."""
    sid = R._sid()
    env.setattr(main, "_ALT_BAN_SPACE_ALL_S", 0.0)
    entered, release = threading.Event(), threading.Event()
    env.steam.gate = (entered, release)

    async def body(sm, rsm):
        await _ban(sm, sid)
        task = asyncio.create_task(_sign_in(sm, sid))
        try:
            assert await _wait(entered), "Steam was never asked"
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            left = main._alt_ban_asked["ids"].get(sid, 0.0) - time.monotonic()
        finally:
            release.set()
        await asyncio.to_thread(_ended, "steam")
        return left, await _rows(sm, sid)

    left, rows = R._with(case, body)
    assert 50 < left <= 60, left
    assert rows == [0, 0, 0, 0], rows
