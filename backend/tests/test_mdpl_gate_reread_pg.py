"""MDPL-GATE-REREAD-1 (a): seven routes read a player before a wait the
account deletion can end, and wrote after that wait from the early read.
Each now reads the player's row again BY ID directly after its wait
(main._reread_player_or_404) and answers 404 when the row is gone or its
deleted_at is set. By id, because the deletion's tombstone rewrites
steam_id and clears discord_id.

  route                              read before the wait     the wait
  booster_grant                      P by discord_id          the gate, P's shared key
  report_casual_dc                   the reporter             the gate, the actor's shared key
  link_discord                       the code's player        the gate, P's shared key
  artist_gift                        the target               the gate, P's shared key
  user_comment_on_bug_report         the ticket's owner       the gate, P's shared key
  auto_logs.upload_auto_log          player_id, in T1a        T2's gate, P's shared key
  cancel_lobby_bet                   the bettor               its exclusive identity key

On PostgreSQL through inv_pg (a case schema per case, the real handlers;
test_mail_case_scrub_pg.py's _settle). Each scene: a second connection H
takes P's identity key exclusive, as delete_player_data does first; the
route starts, reads P and waits at its wait for that key; H tombstones P's
row as delete_player_data does (_tombstone; _MIRRORED holds the deletion's
source to it) and commits. Then, in this order: the route answers 404
"Player not found"; at the read nothing was pending in the route's session
(the spy records the session's new, dirty and deleted sets); P's row
equals, in every column, the row H left; and no row of the case schema
that names P (_naming) was added, changed or removed after H's commit.
upload_auto_log also leaves no blob and no marker, and prints its refusal
with "blob discarded".

report_casual_dc and artist_gift take two identity keys, in
identity_lock_key order, so each runs twice: P's id chosen to sort below
the other account's, then above it (lesson 1294 rule 3).

Each mutant patches the read out (main._reread_player_or_404 answers
without reading) and runs its route's test, which must fail at its FIRST
assertion, the route's answer: a 200 for a deleted player. It is read by
that first line (lesson 1294 rule 6). The control runs every scene without
the deletion: each route answers as before, with the read run once and
nothing pending. It first proves the read on its own: an ORM store pending
in the session is still pending after it, and an ORM select then flushes
it, which shows the check can see a flush.
"""

import asyncio
import hashlib
import hmac
import inspect
import json
import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

from sqlalchemy import select  # noqa: E402

from inv_pg import FLOOR, P, Req, case  # noqa: E402

import auto_logs  # noqa: E402
import main  # noqa: E402
import schemas  # noqa: E402
from identity_order import identity_lock_key  # noqa: E402
from test_mail_case_scrub_pg import BOUND, SECRET, _arm, _name, _settle  # noqa: E402

INTERNAL = "mdpl-reread-internal-key"
TOKEN = "mdpl-reread-session-token"
STEAM_BASE = 76561190040700000
DISCORD_BASE = 900000000000000000
SKU = "rr_gift_title"
NOT_FOUND = (404, "Player not found")
# The identity key, exclusive: the deletion's first statement of its kind.
KEY_SQL = "SELECT pg_advisory_xact_lock(hashtext($1))"
_REAL_REREAD = main._reread_player_or_404

# What _tombstone mirrors, as delete_player_data's source says it: the
# identity key first, the personal rows a route here reads, its first write
# of P's row, the anonymising store and the ledger row.
_MIRRORED = (
    'text("SELECT pg_advisory_xact_lock(hashtext(:sid))"), {"sid": steam_id}',
    'text("DELETE FROM link_codes WHERE player_id = :pid")',
    'text("UPDATE players SET pc_shards = 0 WHERE id = :pid")',
    'text("DELETE FROM steam_sessions WHERE steam_id = :sid")',
    'player.steam_id = f"deleted_{short}"',
    'player.display_name = "[Deleted User]"',
    "player.discord_id = None",
    "player.discord_username = player.discord_display_name = None",
    "player.ranked_enabled = False",
    "player.deleted_at = datetime.now(timezone.utc)",
    'text("INSERT INTO deleted_steam_ids (steam_id_hash, deleted_at)"',
    '" VALUES (:h, clock_timestamp()) ON CONFLICT DO NOTHING")',
)
_TEXTUAL = ("text", "character varying", "json", "jsonb", "ARRAY")


def _uid(n):
    return uuid.UUID("00000000-0000-4000-8000-%012d" % n)


def _sid(n):
    return str(STEAM_BASE + n)


def _did(n):
    return str(DISCORD_BASE + n)


class World:
    """One scene's seeded state: the route, its subject P and P's Discord
    id, fn(db) calling the route, the status its answer carries without the
    deletion, and the route's own check after the deletion (or None)."""
    __slots__ = ("route", "p", "did", "call", "want", "after")

    def __init__(self, route, p, call, want, did=None, after=None):
        self.route, self.p, self.did, self.call, self.want, self.after = route, p, did, call, want, after


# -- seeds -----------------------------------------------------------------------------------------

async def _player(env, n, name, did=None):
    """A players row with the id, raw id and Discord id this file chooses (inv_pg's columns)."""
    p = P(_uid(n), _sid(n), name)
    await env.conn.execute(
        "INSERT INTO players (id, steam_id, display_name, mod_version, mod_seen_at, mail_from, discord_id)"
        " VALUES ($1, $2, $3, $4, NOW(), 'everyone', $5)", p.id, p.sid, name, FLOOR, did)
    return p


async def _booster(env, tmp_path):
    did = _did(10)
    p = await _player(env, 10, "Reread booster P", did)
    return [World("booster_grant", p, lambda db: main.booster_grant(
        discord_id=did, month="2026-11", x_internal_key=INTERNAL, db=db), "granted", did=did)]


def _casual_call(p, lv, room):
    return lambda db: main.report_casual_dc(
        request=Req(p.sid), reporter_steam_id=p.sid, leaver_steam_id=lv.sid, room_id=room,
        leaver_display_name=None, game_room_id=None, db=db)


async def _casual(env, tmp_path):
    lv = await _player(env, 22, "Reread casual L")
    worlds = []
    for n, order in ((21, "below"), (23, "above")):
        p = await _player(env, n, "Reread casual P %s" % order)
        assert (identity_lock_key(p.sid) < identity_lock_key(lv.sid)) == (order == "below"), (p.sid, lv.sid)
        worlds.append(World("report_casual_dc", p, _casual_call(p, lv, "rr_room_%d" % n), "recorded"))
    return worlds


async def _link(env, tmp_path):
    did, code = _did(30), "RRL030"
    p = await _player(env, 30, "Reread link P")
    await env.conn.execute(
        "INSERT INTO link_codes (player_id, code, expires_at, created_at)"
        " VALUES ($1, $2, NOW() + interval '10 minutes', NOW())", p.id, code)
    return [World("link_discord", p, lambda db: main.link_discord(
        code=code, discord_id=did, discord_username="rr_link_user", discord_display_name="Reread Link",
        x_internal_key=INTERNAL, db=db), "linked", did=did)]


def _gift_call(a, p):
    sig = hmac.new(SECRET.encode(), ("artist:%s:gift:%s:%s" % (a.sid, SKU, p.sid)).encode(),
                   hashlib.sha256).hexdigest()
    return lambda db: main.artist_gift(request=Req(a.sid), steam_id=a.sid, sku=SKU,
                                       target_steam_id=p.sid, sig=sig, db=db)


async def _artist(env, tmp_path):
    a = await _player(env, 42, "Reread artist A")
    await env.conn.execute("INSERT INTO artist_users (steam_id, display_name) VALUES ($1, $2)", a.sid, a.name)
    await env.conn.execute(
        "INSERT INTO shop_items (sku, kind, name, description, price, rarity, catalog_ready,"
        " stock_limit, artist_steam_id, min_client_version, released_at)"
        " VALUES ($1, 'title', 'Reread', 'd', 10, 'common', TRUE, NULL, $2, NULL, now())", SKU, a.sid)
    worlds = []
    for n, order in ((41, "below"), (43, "above")):
        p = await _player(env, n, "Reread gift P %s" % order)
        assert (identity_lock_key(p.sid) < identity_lock_key(a.sid)) == (order == "below"), (p.sid, a.sid)
        worlds.append(World("artist_gift", p, _gift_call(a, p), "gifted"))
    return worlds


async def _comment(env, tmp_path):
    did = _did(50)
    p = await _player(env, 50, "Reread comment P", did)
    number = await env.conn.fetchval(
        "INSERT INTO bug_reports (player_id, steam_id, display_name, description, kind)"
        " VALUES ($1, $2, $3, 'reread scene', 'report') RETURNING bug_number", p.id, p.sid, p.name)
    req = schemas.BugReportUserCommentRequest(discord_id=did, comment="any news?")
    return [World("user_comment_on_bug_report", p, lambda db: main.user_comment_on_bug_report(
        bug_number=number, req=req, request=Req(p.sid), x_internal_key=INTERNAL, db=db), "ok", did=did)]


class _Headers:
    def __init__(self, d):
        self._d = {k.lower(): v for k, v in d.items()}

    def get(self, k, default=None):
        return self._d.get(k.lower(), default)


class _UploadReq:
    """Enough Request for upload_auto_log (test_auto_logs.py's _Req): its
    headers, read case-blind, and its body streamed in two chunks."""

    def __init__(self, body):
        self._body = body
        self.headers = _Headers({"Content-Type": "application/json", "X-Session-Token": TOKEN})

    async def stream(self):
        half = len(self._body) // 2
        yield self._body[:half]
        yield self._body[half:]


def _volume(path):
    """The log directory's blobs and markers."""
    names = sorted(x.name for x in path.iterdir() if x.is_file())
    mark = auto_logs._ORPHAN_MARKER_SUFFIX
    return [n for n in names if not n.endswith(mark)], [n for n in names if n.endswith(mark)]


async def _upload(env, tmp_path):
    p = await _player(env, 60, "Reread upload P")
    await env.conn.execute(
        "INSERT INTO steam_sessions (steam_id, token_hash, verified, issued_at, expires_at)"
        " VALUES ($1, $2, TRUE, NOW(), NOW() + interval '1 day')",
        p.sid, hashlib.sha256(TOKEN.encode()).hexdigest())
    body = json.dumps({"steam_id": p.sid, "display_name": p.name, "mod_version": "1.41.0",
                       "game_version": "1.0.0", "mode": "ranked_1v1", "room_name": "RR-60",
                       "log_text": "[Info   :CompetitiveRounds] reread scene\n"}).encode("utf-8")

    async def after(env, out):
        assert _volume(tmp_path) == ([], []), ("the blob or its marker was kept", _volume(tmp_path))
        assert "refused 404 for" in out and "blob discarded" in out, out[-2000:]
    return [World("upload_auto_log", p, lambda db: auto_logs.upload_auto_log(_UploadReq(body), db),
                  "received", after=after)]


async def _cancel(env, tmp_path):
    p = await _player(env, 70, "Reread cancel P")
    await env.conn.execute("UPDATE players SET gold_earned = 200, gold_spent = 100 WHERE id = $1", p.id)
    lid = _uid(79)
    await env.conn.execute(
        "INSERT INTO lobby_bets (mode, lobby_id, player_id, amount, target_steams)"
        " VALUES ('ffa', $1, $2, 10, $3)", lid, p.id, _sid(71))
    sig = hmac.new(SECRET.encode(), ("lobby-bet-cancel:%s:ffa:%s" % (p.sid, lid)).encode(),
                   hashlib.sha256).hexdigest()
    return [World("cancel_lobby_bet", p, lambda db: main.cancel_lobby_bet(
        steam_id=p.sid, mode="ffa", lobby_id=str(lid), sig=sig, db=db, request=None), "cancelled")]


WORLDS = {
    "booster_grant": _booster,
    "report_casual_dc": _casual,
    "link_discord": _link,
    "artist_gift": _artist,
    "user_comment_on_bug_report": _comment,
    "upload_auto_log": _upload,
    "cancel_lobby_bet": _cancel,
}


# -- the scene -------------------------------------------------------------------------------------

def _armed(env, tmp_path):
    """The case's secrets and seams: the HMAC secret (_arm), the bot key, the
    strict session check admitting (artist_gift, upload_auto_log), and
    upload_auto_log's volume in tmp_path with its process state fresh, as
    test_auto_logs.py's fixtures leave it."""
    _arm(env)
    env.mp.setenv("API_SECRET_KEY", INTERNAL)

    async def _session_ok(request, steam_id, db):
        return True
    env.mp.setattr(main, "_strict_steam_session_ok", _session_ok)
    env.mp.setattr(main, "BUG_REPORT_LOG_DIR", str(tmp_path))
    env.mp.setattr(auto_logs, "_LAST_PRUNE", [1e12])
    env.mp.setattr(auto_logs, "_PRUNE_HELD", {})
    env.mp.setattr(auto_logs, "_ORPHAN_HELD", {})
    env.mp.setattr(auto_logs, "_ORPHAN_CURSOR", [""])
    env.mp.setattr(auto_logs, "_BLOB_RESERVE_LOCK", asyncio.Lock())
    env.mp.setattr(auto_logs, "_BLOB_WRITE_STARTED", [0.0])
    env.mp.setattr(auto_logs, "_PRUNE_PASS", [None])
    env.mp.setattr(auto_logs, "_free_bytes", lambda directory: 10 ** 12)


def _spy(env, *, cut=False):
    """main._reread_player_or_404 as every route reaches it: records (the id
    it is given, the counts of the session's new, dirty and deleted sets) at
    the call, then reads; cut: the mutant, which answers without reading."""
    seen = []

    async def reread(db, player_id):
        seen.append((str(player_id), len(db.new), len(db.dirty), len(db.deleted)))
        if not cut:
            await _REAL_REREAD(db, player_id)
    env.mp.setattr(main, "_reread_player_or_404", reread)
    return seen


async def _tombstone(side, p):
    """P's players row as delete_player_data leaves it, written on H, which
    holds P's identity key exclusive as the deletion does from its start."""
    src = inspect.getsource(inspect.unwrap(main.delete_player_data))
    missing = [m for m in _MIRRORED if m not in src]
    assert not missing, ("delete_player_data no longer says what _tombstone mirrors", missing)
    await side.execute("DELETE FROM link_codes WHERE player_id = $1", p.id)
    await side.execute("UPDATE players SET pc_shards = 0 WHERE id = $1", p.id)
    await side.execute("DELETE FROM steam_sessions WHERE steam_id = $1", p.sid)
    await side.execute(
        "UPDATE players SET steam_id = $2, display_name = '[Deleted User]', discord_id = NULL,"
        "       discord_username = NULL, discord_display_name = NULL, ranked_enabled = FALSE,"
        "       deleted_at = NOW()"
        " WHERE id = $1", p.id, "deleted_%s" % uuid.uuid4().hex[:8])
    await side.execute(
        "INSERT INTO deleted_steam_ids (steam_id_hash, deleted_at) VALUES ($1, clock_timestamp())"
        " ON CONFLICT DO NOTHING", main._hash_steam_id(p.sid))


async def _row(conn, p):
    """P's players row, every column; None when there is no row."""
    got = await conn.fetchrow("SELECT * FROM players WHERE id = $1", p.id)
    return None if got is None else dict(got)


def _changed(a, b):
    a, b = a or {}, b or {}
    return {k: (a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}


async def _naming(conn, world):
    """Every row of the case schema's tables that names P, read on `conn`: a
    uuid column equal to P's id, or a text, json or array column whose text
    holds P's raw id, P's id, P's Discord id or P's name. Sorted (table, row
    as JSON) pairs."""
    cols = await conn.fetch(
        "SELECT c.table_name, c.column_name, c.data_type"
        "  FROM information_schema.columns c"
        "  JOIN information_schema.tables t"
        "    ON t.table_schema = c.table_schema AND t.table_name = c.table_name"
        " WHERE c.table_schema = current_schema() AND t.table_type = 'BASE TABLE'"
        " ORDER BY c.table_name, c.ordinal_position")
    by = {}
    for r in cols:
        kind = "u" if r["data_type"] == "uuid" else ("t" if r["data_type"] in _TEXTUAL else None)
        if kind is not None:
            by.setdefault(r["table_name"], {"u": [], "t": []})[kind].append(r["column_name"])
    needles = [world.p.sid, str(world.p.id), world.did or world.p.sid, world.p.name]
    out = []
    for table in sorted(by):
        conds, args = [], []
        if by[table]["u"]:
            args.append(world.p.id)
            conds += ['x."%s" = $1' % c for c in by[table]["u"]]
        if by[table]["t"]:
            first = len(args) + 1
            args += needles
            conds += ['strpos(CAST(x."%s" AS text), $%d) > 0' % (c, first + k)
                      for c in by[table]["t"] for k in range(len(needles))]
        rows = await conn.fetch('SELECT CAST(row_to_json(x) AS text) AS r FROM "%s" x WHERE %s'
                                % (table, " OR ".join(conds)), *args)
        out += [(table, r["r"]) for r in rows]
    return sorted(out)


def _outcome(task):
    if not task.done():
        return "still running"
    if task.exception() is not None:
        return _name(task.exception())
    return task.result()


async def _scene(env, world, *, delete):
    """H takes P's identity key; the route starts and waits on H at its wait;
    with `delete`, H tombstones P and reads P's row and the rows naming P;
    H commits. Returns (the route's answer, P's row as H left it, the rows
    naming P as H left them)."""
    side = await env.side()
    holder = await side.fetchval("SELECT pg_backend_pid()")
    await side.execute("BEGIN")
    await side.execute(KEY_SQL, world.p.sid)
    task = asyncio.create_task(env.call(world.call))
    state, w = await _settle(env, task, by=holder)
    query = (w or {}).get("query") or ""
    assert state == "waits" and "pg_advisory_xact_lock" in query, (
        "the route did not wait at its wait", world.route, state, w, _outcome(task))
    left = named = None
    if delete:
        await _tombstone(side, world.p)
        left = await _row(side, world.p)
        named = await _naming(side, world)
    await side.execute("COMMIT")
    return await asyncio.wait_for(task, BOUND), left, named


def _route_case(monkeypatch, capsys, tmp_path, route, *, cut=False):
    """Every scene of `route` with the deletion, and the four assertions of
    the module docstring, in its order. cut: the mutant."""
    async def body(env):
        _armed(env, tmp_path)
        seen = _spy(env, cut=cut)
        for world in await WORLDS[route](env, tmp_path):
            del seen[:]
            capsys.readouterr()
            ans, left, named = await _scene(env, world, delete=True)
            assert (ans.status, ans.body) == NOT_FOUND, ("answer", route, ans)
            assert seen == [(str(world.p.id), 0, 0, 0)], ("the read again", route, seen)
            row = await _row(env.conn, world.p)
            assert row == left, ("P's row", route, _changed(left, row))
            now = await _naming(env.conn, world)
            assert now == named, ("rows naming P", route, sorted(set(now) ^ set(named))[:4])
            if world.after is not None:
                await world.after(env, capsys.readouterr().out)
    case(monkeypatch, body, prefix="mdplrr")


def _mutant(monkeypatch, capsys, tmp_path, route):
    """The route's own test with the read patched out: red at its first
    assertion, the answer, which is a 200 for the deleted player."""
    with pytest.raises(AssertionError) as e:
        _route_case(monkeypatch, capsys, tmp_path, route, cut=True)
    first = str(e.value).splitlines()[0]
    assert first.startswith("('answer', %r, Answer(200, " % route), first
    print("MUTANT-RED %s: %s" % (route, first[:200]))


# -- the seven routes ------------------------------------------------------------------------------

def test_booster_grant_refuses_a_player_deleted_while_it_waited(monkeypatch, capsys, tmp_path):
    """Read by discord_id before the gate. Without the read again it pays the
    month's gold into P's tombstone with a grant and a ledger row naming P."""
    _route_case(monkeypatch, capsys, tmp_path, "booster_grant")


def test_report_casual_dc_refuses_a_reporter_deleted_while_it_waited(monkeypatch, capsys, tmp_path):
    """The reporter, read before the gate, which takes the leaver's key
    exclusive and the reporter's shared; both orders of the two keys.
    Without the read again it records an event whose reporter_id is P."""
    _route_case(monkeypatch, capsys, tmp_path, "report_casual_dc")


def test_link_discord_refuses_a_player_deleted_while_it_waited(monkeypatch, capsys, tmp_path):
    """The code's player, read before the gate. Without the read again the
    deleted row is linked to the Discord account."""
    _route_case(monkeypatch, capsys, tmp_path, "link_discord")


def test_artist_gift_refuses_a_target_deleted_while_it_waited(monkeypatch, capsys, tmp_path):
    """The target, read before the gate, which takes the target's and the
    artist's shared keys; both orders of the two keys. Without the read
    again the deleted row is given the item and named in the artist's log."""
    _route_case(monkeypatch, capsys, tmp_path, "artist_gift")


def test_user_comment_refuses_an_owner_deleted_while_it_waited(monkeypatch, capsys, tmp_path):
    """The ticket's owner, read before the gate. Without the read again the
    comment is stored as the deleted player's."""
    _route_case(monkeypatch, capsys, tmp_path, "user_comment_on_bug_report")


def test_upload_auto_log_refuses_a_player_deleted_while_it_waited(monkeypatch, capsys, tmp_path):
    """player_id, read in T1a, before T2's gate. The refusal ends T2 and
    discards the stored blob first. Without the read again the upload is
    stored as a row whose player_id is P."""
    _route_case(monkeypatch, capsys, tmp_path, "upload_auto_log")


def test_cancel_lobby_bet_refuses_a_bettor_deleted_while_it_waited(monkeypatch, capsys, tmp_path):
    """The bettor, read before its exclusive identity key. Without the read
    again the stake is refunded into P's tombstone with a ledger row."""
    _route_case(monkeypatch, capsys, tmp_path, "cancel_lobby_bet")


# -- the mutants -----------------------------------------------------------------------------------

def test_mutant_booster_grant_without_the_read_again_grants(monkeypatch, capsys, tmp_path):
    _mutant(monkeypatch, capsys, tmp_path, "booster_grant")


def test_mutant_report_casual_dc_without_the_read_again_records(monkeypatch, capsys, tmp_path):
    _mutant(monkeypatch, capsys, tmp_path, "report_casual_dc")


def test_mutant_link_discord_without_the_read_again_links(monkeypatch, capsys, tmp_path):
    _mutant(monkeypatch, capsys, tmp_path, "link_discord")


def test_mutant_artist_gift_without_the_read_again_gifts(monkeypatch, capsys, tmp_path):
    _mutant(monkeypatch, capsys, tmp_path, "artist_gift")


def test_mutant_user_comment_without_the_read_again_stores_the_comment(monkeypatch, capsys, tmp_path):
    _mutant(monkeypatch, capsys, tmp_path, "user_comment_on_bug_report")


def test_mutant_upload_auto_log_without_the_read_again_stores_the_upload(monkeypatch, capsys, tmp_path):
    _mutant(monkeypatch, capsys, tmp_path, "upload_auto_log")


def test_mutant_cancel_lobby_bet_without_the_read_again_refunds(monkeypatch, capsys, tmp_path):
    _mutant(monkeypatch, capsys, tmp_path, "cancel_lobby_bet")


# -- the control -----------------------------------------------------------------------------------

async def _pending_stays_pending(env):
    """The read on its own: an ORM store pending in the session is still
    pending after it (the statement is text(), which Session.execute does not
    autoflush), and an ORM select right after flushes the store, which shows
    this check can see a flush."""
    q = await _player(env, 90, "Reread pending")
    async with env.sm() as db:
        row = (await db.execute(select(main.Player).where(main.Player.id == q.id))).scalar_one()
        row.display_name = "Reread pending store"
        assert row in db.dirty, "the store is not pending to begin with"
        await _REAL_REREAD(db, q.id)
        assert row in db.dirty, "the read again sent the pending store"
        await db.execute(select(main.Player.id).where(main.Player.id == q.id))
        assert row not in db.dirty, "an ORM select left the store pending: this check sees no flush"
        await db.rollback()


def test_control_without_the_deletion_every_route_answers_as_before(monkeypatch, capsys, tmp_path):
    """Every scene of the seven, H holding P's key and committing nothing:
    each route answers as before it read again, and the read ran once with
    nothing pending."""
    async def body(env):
        _armed(env, tmp_path)
        await _pending_stays_pending(env)
        seen = _spy(env)
        for route, build in WORLDS.items():
            for world in await build(env, tmp_path):
                del seen[:]
                ans, _left, _named = await _scene(env, world, delete=False)
                assert ans.status == 200 and ans.get("status") == world.want, ("control", route, ans)
                assert seen == [(str(world.p.id), 0, 0, 0)], ("the read again", route, seen)
    case(monkeypatch, body, prefix="mdplrr")
