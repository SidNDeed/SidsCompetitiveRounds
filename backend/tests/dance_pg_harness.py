"""Live PostgreSQL for the dance-cards tests: ONE production-shaped case
schema per test module, driven from a loop of its own.

The schema is built exactly as the ladder hook tests build theirs
(test_title_ladder_hooks_live._build: every migration's DDL replayed, the
ORM's tables, the widening pass, the replay again, 331 landed and checked).
That replay includes 358's DDL; 358 is then run WHOLE once more (its
idempotent re-run), the schema is sealed, and every test of the module works
in it with players of its own. ladder_pg_harness's census discipline governs
the create and the drop.

DANCE_CARDS_TEST_PG_DSN names a throwaway database for the case schemas.
Unset, every live test FAILS (a skipped live case reports exit 0 for coverage
that did not run) unless DANCE_CARDS_TEST_PG_OPTOUT=1 waives it deliberately.

Identities here are synthetic (7656119000xxxxxxx); the exemption account a
test needs is patched in, never read from the constant.
"""
import asyncio
import atexit
import hashlib
import hmac
import io
import os
import sys
import threading
import types
import uuid

import pytest
from PIL import Image, ImageDraw
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import main  # noqa: E402
import pc_motion as pcm  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402

DSN_VAR = "DANCE_CARDS_TEST_PG_DSN"
OPTOUT_VAR = "DANCE_CARDS_TEST_PG_OPTOUT"
DSN = (os.environ.get(DSN_VAR) or "").replace("postgresql+asyncpg://", "postgresql://")
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"
MIGRATION = os.path.join(HERE, "..", "sql", "358_player_card_dance_motion.sql")

DANCES = tuple(sorted(pcm.MOTION_TABLE[pcm.MOTION_RECIPE]))
DESC = "v1|face=1000:1002:1004:1005|off=0,0;0,0;0,0;0,0|color=:|effect=|skin=0|anim=1|g=1.2.3|r=1"


def require_live_pg():
    """Fail, not skip, unless the waiver is set (module docstring)."""
    if DSN and harness._asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: the live dance-cards coverage is deliberately "
                    "waived." % (DSN_VAR, OPTOUT_VAR))
    pytest.fail("%s is unset, so no dance-cards route ran against a real server. Point it "
                "at a throwaway database, or set %s=1 to waive the coverage deliberately."
                % (DSN_VAR, OPTOUT_VAR))


class Lane:
    """A background event loop holding one built, sealed case schema and a
    session factory bound to it. `run(coro)` executes on that loop."""

    def __init__(self, prefix):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.case = harness.CaseSchema(DSN, prefix)
        self.engine = None
        self.sm = None
        self.items = {}

    def run(self, coro, timeout=600):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    async def _open(self):
        await self.case.__aenter__()
        try:
            async def _358(conn, schema):
                await conn.execute(io.open(MIGRATION, encoding="utf-8").read())
            # _build reads its own module's DSN for the ORM pass: point it at
            # this lane's database for the build, then put it back.
            saved = lh.DSN
            lh.DSN = DSN
            try:
                await lh._build(self.case, _358)
            finally:
                lh.DSN = saved
            self.engine = harness.bound_engine(DSN, self.case.schema)
            self.sm = async_sessionmaker(self.engine, expire_on_commit=False)
            async with self.sm() as db:
                for sku in DANCES:
                    row = await lh._insert(db, "shop_items", {
                        "sku": sku, "kind": "dance", "name": sku, "price": 100,
                        "rarity": "common", "catalog_ready": True})
                    self.items[sku] = int(row["id"])
                await db.commit()
        except BaseException:
            await self.case.__aexit__(None, None, None)
            raise

    async def _close(self):
        try:
            if self.engine is not None:
                await self.engine.dispose()
        finally:
            await self.case.__aexit__(None, None, None)

    def open(self):
        self.run(self._open(), timeout=1800)
        return self

    def close(self):
        try:
            self.run(self._close(), timeout=600)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(10)

    async def connect(self):
        """A raw asyncpg connection bound to the case schema (probes, holds)."""
        return await harness.connect_bound(DSN, self.case.schema)


_SHARED = []


def shared_lane():
    """The process's one lane: built by the first module that asks, reused by
    the rest (a build replays every migration twice), dropped at exit."""
    if not _SHARED:
        lane = Lane("dance_cards").open()
        _SHARED.append(lane)
        atexit.register(lane.close)
    return _SHARED[0]


_SEQ = [0]


def steam_id():
    """A fresh synthetic SteamID64 for one test's player."""
    _SEQ[0] += 1
    return "7656119000%07d" % (_SEQ[0] + 3000)


def still_hash(tag):
    return hashlib.sha256(("still:" + str(tag)).encode()).hexdigest()


async def still_blob(db, h):
    """The pc_portraits row a still hash must name (players' FK): the bytes
    are never decoded by these tests."""
    await db.execute(text(
        "INSERT INTO pc_portraits (hash, bytes, content_type, width, height) "
        "VALUES (CAST(:h AS text), CAST(:b AS bytea), 'image/png', 1180, 1180) ON CONFLICT (hash) DO NOTHING"),
        {"h": h, "b": b"still:" + h.encode()})


async def make_player(lane, steam, *, still=True, descriptor=DESC, dance="dance_bounce",
                      owned=True, ready=None):
    """A live player made the way a first report makes one, with (by default)
    a game still, the dance selected and owned. Returns (pid, still hash)."""
    async with lane.sm() as db:
        pid = str((await main.get_or_create_player(db, steam, "Dancer " + steam[-4:])).id)
        h = still_hash(steam) if still else None
        if h:
            await still_blob(db, h)
        await db.execute(text(
            "UPDATE players SET pc_game_portrait_hash = CAST(:h AS text), "
            "pc_game_portrait_descriptor = CAST(:d AS text), pc_game_portrait_at = now() - interval '1 hour', "
            "active_dance_id = CAST(:item AS bigint) WHERE id = CAST(:pid AS uuid)"),
            {"h": h, "d": descriptor if still else None,
             "item": lane.items[dance] if dance else None, "pid": pid})
        if dance and owned:
            await db.execute(text(
                "INSERT INTO player_items (player_id, item_id, purchase_price) "
                "VALUES (CAST(:pid AS uuid), CAST(:item AS bigint), 0)"),
                {"pid": pid, "item": lane.items[dance]})
        await db.commit()
    return pid, h


async def fetch(lane, sql, **params):
    async with lane.sm() as db:
        return (await db.execute(text(sql), params)).mappings().all()


async def execute(lane, sql, **params):
    async with lane.sm() as db:
        await db.execute(text(sql), params)
        await db.commit()


async def ban(lane, steam, admin="76561190000009999"):
    """An active ban row for `steam` (by a synthetic admin)."""
    async with lane.sm() as db:
        have = (await db.execute(text("SELECT 1 FROM admin_users WHERE steam_id = :a"), {"a": admin})).first()
        if have is None:
            await lh._insert(db, "admin_users", {"steam_id": admin})
        await lh._insert(db, "player_bans", {"steam_id": steam, "reason": "test",
                                              "banned_by_steam_id": admin})
        await db.commit()


class Req:
    """What the motion and selection handlers read off a request."""

    def __init__(self, body=b"", headers=None, host="10.9.0.1", path="/api/v1/pc/portrait/motion"):
        self._body = body
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.client = types.SimpleNamespace(host=host)
        self.state = types.SimpleNamespace()
        self.url = types.SimpleNamespace(path=path)
        self.query_params = {}
        self.reads = 0

    async def body(self):
        self.reads += 1
        return self._body


def motion_request(body, content_type=pcm.MOTION_CONTENT_TYPE, length=None, host="10.9.0.1", chunked=False):
    headers = {"content-type": content_type}
    if chunked:
        headers["transfer-encoding"] = "chunked"
    elif length is not False:
        headers["content-length"] = str(len(body) if length is None else length)
    return Req(body, headers, host=host)


def sign(secret, canon):
    return hmac.new(secret.encode(), canon.encode(), hashlib.sha256).hexdigest()


def nonce():
    return "n-" + uuid.uuid4().hex[:20]


class Sessions:
    """The strict session check, replaced: a steam id holds a session while
    it is in `live`."""

    def __init__(self):
        self.live = set()

    async def check(self, request, steam_id, db):
        return steam_id in self.live


def open_routes(monkeypatch, sessions, secret):
    """Point the handlers at a test HMAC key and the replaced session check."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", secret)
    monkeypatch.setattr(main, "_strict_steam_session_ok", sessions.check)
    # This seat's Pillow wheel carries no raqm; the renderer gate would refuse
    # every route for it. The names these tests render are Latin.
    monkeypatch.setattr(main, "_pc_raqm", lambda: True)


async def upload(lane, steam, secret, body, *, descriptor=DESC, nonce_value=None, request=None, sig=None):
    """One call of the motion writer on its own session: (status, answer)."""
    n = nonce_value or nonce()
    if sig is None:
        canon = pcm.canon_motion(steam, n, hashlib.sha256(body).hexdigest(), descriptor)
        sig = sign(secret, canon)
    req = request or motion_request(body)
    async with lane.sm() as db:
        try:
            answer = await main.pc_motion_upload(req, steam_id=steam, sig=sig, nonce=n,
                                                 descriptor=descriptor, db=db)
            return 200, answer
        except main.HTTPException as ex:
            return ex.status_code, ex.detail


def still_png(tag):
    """A 1180-square RGBA still the real writer accepts: transparent but for
    one opaque disc (about 10 % coverage) whose colour and place follow `tag`,
    so two tags give two canonical hashes."""
    seed = int(hashlib.sha256(str(tag).encode()).hexdigest()[:8], 16)
    img = Image.new("RGBA", (1180, 1180), (0, 0, 0, 0))
    cx, cy = 400 + seed % 380, 400 + (seed >> 9) % 380
    colour = (seed & 255, (seed >> 8) & 255, (seed >> 16) & 255, 255)
    ImageDraw.Draw(img).ellipse((cx - 210, cy - 210, cx + 210, cy + 210), fill=colour)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


async def still_upload(lane, steam, secret, body, descriptor=DESC, *, nonce_value=None, sig=None):
    """One call of the still writer (POST /api/v1/pc/portrait) on its own
    session: (status, answer)."""
    n = nonce_value or nonce()
    if sig is None:
        sig = sign(secret, main._pcp.canon_portrait(steam, n, hashlib.sha256(body).hexdigest(), descriptor))
    req = Req(body, {"content-type": "image/png", "content-length": str(len(body))}, path="/api/v1/pc/portrait")
    async with lane.sm() as db:
        try:
            return 200, await main.pc_portrait_upload(req, steam_id=steam, sig=sig, nonce=n,
                                                      descriptor=descriptor, db=db)
        except main.HTTPException as ex:
            return ex.status_code, ex.detail


async def pc_me(lane, steam, secret):
    """The owner's GET /api/v1/pc/me answer, from main.pc_me itself."""
    sig = sign(secret, main._pc.canon_read(steam, "me", "-"))
    async with lane.sm() as db:
        return await main.pc_me(Req(path="/api/v1/pc/me"), steam_id=steam, sig=sig, db=db)


async def put_motion(lane, pid, still, *, descriptor=DESC, dance="dance_bounce", recipe=1, tag="m"):
    """A stored motion row written directly, for tests about what READS the
    row (it is never decoded): bound to `still` and `descriptor`, for `dance`.
    Returns its motion_hash."""
    h = hashlib.sha256(("motion:" + pid + ":" + tag).encode()).hexdigest()
    period, count = pcm.table_row(recipe, dance) or (50, 80)
    blob = b"motion:" + h.encode()
    async with lane.sm() as db:
        await db.execute(text("DELETE FROM pc_motions WHERE player_id = CAST(:pid AS uuid)"), {"pid": pid})
        await db.execute(text(
            "INSERT INTO pc_motions (player_id, motion_hash, source_sha256, bytes, byte_len, dance_item_id, "
            "motion_recipe, frame_count, frame_ms, static_hash, static_descriptor) VALUES (CAST(:pid AS uuid), "
            "CAST(:h AS text), CAST(:h AS text), CAST(:b AS bytea), CAST(:n AS integer), CAST(:item AS bigint), "
            "CAST(:r AS smallint), CAST(:c AS smallint), CAST(:ms AS smallint), CAST(:sh AS text), CAST(:sd AS text))"),
            {"pid": pid, "h": h, "b": blob, "n": len(blob), "item": lane.items[dance], "r": recipe,
             "c": count, "ms": period, "sh": still, "sd": descriptor})
        await db.commit()
    return h


# Waiting locks of THIS database's backends only: the instance is shared.
WAITING_SQL = ("SELECT count(*) FROM pg_catalog.pg_locks l JOIN pg_catalog.pg_stat_activity a "
               "ON a.pid = l.pid WHERE a.datname = current_database() AND l.locktype = $1 "
               "AND NOT l.granted")


async def wait_for_lock_wait(lane, locktype, timeout=20.0):
    """Wait until some backend waits, ungranted, on a lock of `locktype`."""
    conn = await lane.connect()
    try:
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while loop.time() < end:
            n = await conn.fetchval(WAITING_SQL, locktype)
            if n:
                return True
            await asyncio.sleep(0.05)
        return False
    finally:
        await conn.close()
