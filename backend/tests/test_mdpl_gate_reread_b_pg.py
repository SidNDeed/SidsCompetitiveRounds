"""MDPL-GATE-REREAD-1 (b): four routes read their player with no key, before a
wait the account deletion can end, and wrote after it from that read. Each now
takes the player's deletion key SHARED before the read (main's two-key class
PLAYER_DELETION_LOCK_CLASS, through main._player_deletion_key_shared_bounded;
no identity key), then reads, then reads the
row again by id (main._reread_player_or_404, which sends no flush).

  route                      the key's id            taken
  toggle_ranked              the path's steam_id     first statement
  unlock_achievement         req.steam_id            first statement
  admin_grant_achievement    req.target_steam_id     after _require_admin
  generate_link_code         the query's steam_id    after the strict session check

On PostgreSQL through inv_pg, with test_mdpl_gate_reread_pg.py's seeds and
checks (_player, _armed, _spy, _tombstone, _row, _naming). Each scene: a second
connection H takes P's identity key EXCLUSIVE and then P's deletion key
EXCLUSIVE, as delete_player_data does first (the deletion key's statement built
from main's own text, DELETION_KEY_SQL), and tombstones P's row as
delete_player_data does (_tombstone), not yet
committed; the route starts and waits on H; H commits. Then, in this order:
the route answers 404 (admin_grant_achievement with its own "Target player not
found"); the statement it waited at was the shared key; the read by id ran as
the route's path says (toggle_ranked: once, on the [Deleted User] row
get_or_create_player stored for the purged id, that row's GlickoRating
pending; the three others: not at all here, their own read found no row;
their read by id has scenes of its own, below); P's row
equals, in every column, the row H left; and no row of the case schema that
names P (player_achievements, gold_transactions, link_codes, the title item
among them) was added, changed or removed.

H tombstones BEFORE the route starts, not after the route waits: the fixed
route waits at the key either way, but the mutant, which takes no key, would
otherwise run to its commit before H wrote anything (it meets no lock of H's),
and a tombstone split around the route's writes can put the route's
foreign-key KEY SHARE on P's row ahead of H's steam_id store, the two then
waiting for each other. Tombstoned first, H holds P's row FOR UPDATE and P's
link code rows, so the mutant waits there and then writes onto the tombstone,
as the routes did before the key.

Each mutant takes the new key out (inv_pg's rewriting: the statement runs as
SELECT (CAST(...), hashtext(...)), which takes no lock) and runs its route's test, which
must fail at its FIRST assertion, the answer: a 200 for the deleted player
(lesson 1294 rule 6). The rewriting must have changed exactly one statement,
the route's key. The control runs every scene without the deletion: each
route answers as before, having waited at its key, with the read by id run
once on P's id and nothing pending; and toggle_ranked, for a Steam id never
seen, still creates the player under the key, the new row's GlickoRating
pending at the read by id and stored after it.

The read by id in unlock_achievement, admin_grant_achievement and
generate_link_code runs in scenes of its own, with no holder: a purged id's
[Deleted User] row (get_or_create_player stores it under the raw id with
deleted_at set; an earlier request committed it) stands under P's raw id
before the request (_purged makes P's row that row). The route's own read
finds it; then, in this order: the route answers 404 "Player not found"
(admin_grant_achievement too); the read by id ran once, on that row's id,
with nothing pending; the row equals, in every column, the row seeded; and no
row naming it was added, changed or removed (unlock_achievement: the
achievement, the gold on the row and its ledger row; admin_grant_achievement:
those, the title item and the moderator record; generate_link_code: the link
code seeded for the row stays and no code is added). Each of their mutants
takes the route's own call of the read by id out (_cut: the call answers
without reading when the route's body makes it, and reads for any other
caller) and must fail at its first assertion, the answer: a 200. The cut must
have taken out exactly one call, the route's; that premise is checked first
(lesson 1300 rule 4: a mutant that cut nothing is red on its premise, not on
the product).

Every route takes one key, its player's deletion key (the admin's is not
taken; no identity key), so no scene has a second key whose order could
change its outcome.
"""

import asyncio
import contextlib
import hashlib
import hmac
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

from inv_pg import P, Req, case  # noqa: E402

import main  # noqa: E402
import schemas  # noqa: E402
from test_mail_case_scrub_pg import BOUND, SECRET, _settle  # noqa: E402
from test_mdpl_gate_reread_pg import (  # noqa: E402
    KEY_SQL, NOT_FOUND, _armed, _changed, _naming, _outcome, _player, _row, _sid, _spy, _tombstone)

ADMIN_SECRET = "mdpl-reread-b-admin-secret"
UNLOCK_KEY = "stacked_deck"      # client-detected (CLIENT_UNLOCK_KEYS), pays gold
GRANT_KEY = "rosetta"            # pays gold; its title item is ACHIEVEMENT_TITLE_SKUS["rosetta"]
# The new key's statement as it reaches the wire (its two binds as $1 and $2),
# and the mutant's spelling of it: the same arguments as a row, taking no lock.
SHARED_KEY = "pg_advisory_xact_lock_shared(CAST("
NO_KEY = "(CAST("


def deletion_key_sql(fn):
    """The deletion key's statement for a second connection, `fn` over
    main._PLAYER_DELETION_KEY_ARGS, the module's own text, never a typed key:
    its binds renamed for asyncpg, $1 the class (main.PLAYER_DELETION_LOCK_CLASS)
    and $2 the steam id."""
    args = main._PLAYER_DELETION_KEY_ARGS
    assert args.count(":cls") == 1 and args.count(":sid") == 1, args
    return "SELECT %s(%s)" % (fn, args.replace(":cls", "$1").replace(":sid", "$2"))


# The deletion key EXCLUSIVE, as delete_player_data takes it after its identity key.
DELETION_KEY_SQL = deletion_key_sql("pg_advisory_xact_lock")


def _sig(canonical, secret=SECRET):
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


class Scene:
    """One route's seeded state: the route, its subject P (and no Discord id),
    fn(db) calling it, the 404 it answers for a deleted P, whether it creates
    the player when its read finds none (toggle_ranked), and the check of its
    answer without the deletion."""
    __slots__ = ("route", "p", "did", "call", "gone", "creates", "ok")

    def __init__(self, route, p, call, gone, ok, creates=False):
        self.route, self.p, self.did, self.call = route, p, None, call
        self.gone, self.ok, self.creates = gone, ok, creates


# -- seeds -----------------------------------------------------------------------------------------

def _toggle_call(p, name):
    sig = _sig("toggle-ranked:%s:true" % p.sid)
    name_sig = _sig("toggle-ranked-name:%s:%s" % (p.sid, name))
    return lambda db: main.toggle_ranked(steam_id=p.sid, request=Req(p.sid), enabled=True, sig=sig,
                                         display_name=name, name_sig=name_sig, db=db)


async def _toggle(env):
    p = await _player(env, 110, "Reread toggle P")
    # ranked off, so the request's True is a store the flush writes
    await env.conn.execute("UPDATE players SET ranked_enabled = FALSE WHERE id = $1", p.id)
    return Scene("toggle_ranked", p, _toggle_call(p, "Reread toggle P renamed"), NOT_FOUND,
                 lambda body: body == {"steam_id": p.sid, "ranked_enabled": True}, creates=True)


async def _unlock(env):
    p = await _player(env, 120, "Reread unlock P")
    req = schemas.AchievementUnlockRequest(
        steam_id=p.sid, achievement_key=UNLOCK_KEY,
        hmac_signature=_sig("achievement:%s:%s" % (p.sid, UNLOCK_KEY)))
    gold = main._achievement_gold(UNLOCK_KEY)
    return Scene("unlock_achievement", p, lambda db: main.unlock_achievement(req=req, request=Req(p.sid), db=db),
                 NOT_FOUND, lambda body: body.get("status") == "unlocked" and body.get("gold_awarded") == gold)


async def _grant(env):
    a = await _player(env, 131, "Reread grant admin")
    await env.conn.execute("INSERT INTO admin_users (steam_id) VALUES ($1)", a.sid)
    p = await _player(env, 130, "Reread grant P")
    sku = main.ACHIEVEMENT_TITLE_SKUS[GRANT_KEY]
    if not await env.conn.fetchval("SELECT 1 FROM shop_items WHERE sku = $1", sku):
        await env.conn.execute(
            "INSERT INTO shop_items (sku, kind, name, description, price, rarity, catalog_ready,"
            " stock_limit, artist_steam_id, min_client_version, released_at)"
            " VALUES ($1, 'title', 'Rosetta', 'd', 0, 'rare', TRUE, NULL, NULL, NULL, now())", sku)
    req = main._AdminGrantAchReq(
        admin_steam_id=a.sid, target_steam_id=p.sid, achievement_key=GRANT_KEY,
        hmac_signature=_sig("admin:%s:grant_achievement:%s" % (a.sid, p.sid), ADMIN_SECRET))
    want = {"status": "granted", "achievement_key": GRANT_KEY, "gold_awarded": main._achievement_gold(GRANT_KEY)}
    return Scene("admin_grant_achievement", p, lambda db: main.admin_grant_achievement(req=req, db=db),
                 (404, "Target player not found"), lambda body: body == want)


async def _code(env):
    p = await _player(env, 140, "Reread code P")
    await env.conn.execute(
        "INSERT INTO link_codes (player_id, code, expires_at, created_at)"
        " VALUES ($1, $2, NOW() + interval '10 minutes', NOW())", p.id, "RRB140")
    return Scene("generate_link_code", p, lambda db: main.generate_link_code(request=Req(p.sid), steam_id=p.sid, db=db),
                 NOT_FOUND, lambda body: body.get("expires_in") == 600 and len(body.get("code") or "") == 6)


SCENES = {
    "toggle_ranked": _toggle,
    "unlock_achievement": _unlock,
    "admin_grant_achievement": _grant,
    "generate_link_code": _code,
}


# -- the scene -------------------------------------------------------------------------------------

def _seams(env, tmp_path):
    """(a)'s seams (the HMAC secret, the strict session check admitting) and
    the admin route's signing secret."""
    _armed(env, tmp_path)
    env.mp.setattr(main, "ADMIN_HMAC_SECRET", ADMIN_SECRET)


async def _end(*tasks):
    """Ends the tasks a row started, whatever the row's outcome. A row calls
    it in a finally, after it released its holders: each task is waited for
    within BOUND, and what still stands then is cancelled and waited for.
    The outcomes are gathered, so the ending raises nothing over the row's
    own error. On the path where every assertion held, the row has read
    each task's answer before, and this finds them done."""
    tasks = [t for t in tasks if t is not None]
    if not tasks:
        return
    await asyncio.wait(tasks, timeout=BOUND)
    for t in tasks:
        if not t.done():
            t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _scene(env, s, *, delete):
    """H takes P's identity key exclusive, then P's deletion key exclusive
    (DELETION_KEY_SQL), and, with `delete`, tombstones P and
    reads P's row and the rows naming P, not yet committed; the route starts
    and waits on H; H commits. Returns (the route's answer, the statement it
    waited at, P's row as H left it, the rows naming P as H left them)."""
    side = await env.side()
    holder = await side.fetchval("SELECT pg_backend_pid()")
    await side.execute("BEGIN")
    await side.execute(KEY_SQL, s.p.sid)
    await side.execute(DELETION_KEY_SQL, main.PLAYER_DELETION_LOCK_CLASS, s.p.sid)
    left = named = None
    if delete:
        await _tombstone(side, s.p)
        left = await _row(side, s.p)
        named = await _naming(side, s)
    task = asyncio.create_task(env.call(s.call))
    committed = False
    try:
        state, w = await _settle(env, task, by=holder)
        assert state == "waits", ("the route did not wait on the holder", s.route, state, _outcome(task))
        await side.execute("COMMIT")
        committed = True
        return await asyncio.wait_for(task, BOUND), (w or {}).get("query") or "", left, named
    finally:
        if not committed:                       # the holder released first, its own error kept below the row's
            with contextlib.suppress(Exception):
                await side.execute("ROLLBACK")
        await _end(task)


def _route_case(monkeypatch, tmp_path, route, *, cut=False, record=None):
    """The route's scene with the deletion and the five assertions of the
    module docstring, in its order. cut: the mutant, the key taken out;
    `record` receives the statements its rewriting changed."""
    async def body(env):
        _seams(env, tmp_path)
        seen = _spy(env)
        s = await SCENES[route](env)
        with (env.rewriting(SHARED_KEY, NO_KEY) if cut else contextlib.nullcontext([])) as hits:
            ans, waited, left, named = await _scene(env, s, delete=True)
        if record is not None:
            record.append(list(hits))
        assert (ans.status, ans.body) == s.gone, ("answer", route, ans)
        assert "pg_advisory_xact_lock_shared" in waited, ("the wait", route, waited)
        if s.creates:
            assert len(seen) == 1 and seen[0][0] != str(s.p.id) and seen[0][1:] == (1, 0, 0), (
                "the read by id", route, seen)
        else:
            assert seen == [], ("the read by id", route, seen)
        row = await _row(env.conn, s.p)
        assert row == left, ("P's row", route, _changed(left, row))
        now = await _naming(env.conn, s)
        assert now == named, ("rows naming P", route, sorted(set(now) ^ set(named))[:4])
    case(monkeypatch, body, prefix="mdplrb")


def _mutant(monkeypatch, tmp_path, route):
    """The route's own test with the key taken out: red at its first
    assertion, the answer, which is a 200 for the deleted player; the
    rewriting changed one statement, the route's key."""
    record = []
    with pytest.raises(AssertionError) as e:
        _route_case(monkeypatch, tmp_path, route, cut=True, record=record)
    first = str(e.value).splitlines()[0]
    assert first.startswith("('answer', %r, Answer(200, " % route), first
    assert len(record) == 1 and len(record[0]) == 1 and SHARED_KEY in record[0][0], record
    print("MUTANT-RED %s: %s" % (route, first[:200]))


# -- the four routes -------------------------------------------------------------------------------

def test_toggle_ranked_refuses_a_player_deleted_while_it_waited_at_the_key(monkeypatch, tmp_path):
    """Its read finds no row under P's raw id; get_or_create_player stores the
    purged id's [Deleted User] row, which the read by id refuses, and nothing
    is stored. Without the key the read finds P, and the flush writes the
    name and ranked_enabled onto P's tombstone."""
    _route_case(monkeypatch, tmp_path, "toggle_ranked")


def test_unlock_achievement_refuses_a_player_deleted_while_it_waited_at_the_key(monkeypatch, tmp_path):
    """Without the key the read finds P, and the achievement, the gold and
    its ledger row are stored for P's tombstone."""
    _route_case(monkeypatch, tmp_path, "unlock_achievement")


def test_admin_grant_achievement_refuses_a_target_deleted_while_it_waited_at_the_key(monkeypatch, tmp_path):
    """Without the key the read finds P, and the achievement, the gold, its
    ledger row and the title item are stored for P's tombstone."""
    _route_case(monkeypatch, tmp_path, "admin_grant_achievement")


def test_generate_link_code_refuses_a_player_deleted_while_it_waited_at_the_key(monkeypatch, tmp_path):
    """Without the key the read finds P, and a link code naming P's
    tombstone is stored after the deletion removed P's codes."""
    _route_case(monkeypatch, tmp_path, "generate_link_code")


# -- the mutants -----------------------------------------------------------------------------------

def test_mutant_toggle_ranked_without_the_key_writes_onto_the_tombstone(monkeypatch, tmp_path):
    _mutant(monkeypatch, tmp_path, "toggle_ranked")


def test_mutant_unlock_achievement_without_the_key_pays_the_tombstone(monkeypatch, tmp_path):
    _mutant(monkeypatch, tmp_path, "unlock_achievement")


def test_mutant_admin_grant_achievement_without_the_key_pays_the_tombstone(monkeypatch, tmp_path):
    _mutant(monkeypatch, tmp_path, "admin_grant_achievement")


def test_mutant_generate_link_code_without_the_key_stores_a_code(monkeypatch, tmp_path):
    _mutant(monkeypatch, tmp_path, "generate_link_code")


# -- the read by id, on a purged id's [Deleted User] row -------------------------------------------

async def _purged(env, s):
    """P's row made the [Deleted User] row get_or_create_player stores for a
    purged id, committed as an earlier request left it: under P's raw id
    still, display_name '[Deleted User]', deleted_at set. The scene's other
    seeds (the admin, the title's shop row, P's link code) stand as its
    builder left them."""
    await env.conn.execute(
        "UPDATE players SET display_name = '[Deleted User]', deleted_at = NOW() WHERE id = $1", s.p.id)


def _cut(env, route, taken):
    """The read-by-id mutant: main._reread_player_or_404, called from
    `route`'s own body, answers without reading; called from anywhere else,
    it runs as before. A plain function, so frame 1 is the caller's body.
    `taken` receives the name of each caller it cut."""
    before = main._reread_player_or_404

    async def nothing():
        return None

    def reread(db, player_id):
        caller = sys._getframe(1).f_code.co_name
        if caller == route:
            taken.append(caller)
            return nothing()
        return before(db, player_id)
    env.mp.setattr(main, "_reread_player_or_404", reread)


def _seeded_case(monkeypatch, tmp_path, route, *, taken=None):
    """The route called for a purged id's [Deleted User] row that stands
    before the request (no holder), and the four assertions of the module
    docstring's read-by-id paragraph, in its order. taken: the mutant, the
    route's own call of the read by id taken out (_cut)."""
    async def body(env):
        _seams(env, tmp_path)
        seen = _spy(env)
        if taken is not None:
            _cut(env, route, taken)
        s = await SCENES[route](env)
        await _purged(env, s)
        left = await _row(env.conn, s.p)
        named = await _naming(env.conn, s)
        ans = await asyncio.wait_for(env.call(s.call), BOUND)
        assert (ans.status, ans.body) == NOT_FOUND, ("answer", route, ans)
        assert seen == [(str(s.p.id), 0, 0, 0)], ("the read by id", route, seen)
        row = await _row(env.conn, s.p)
        assert row == left, ("P's row", route, _changed(left, row))
        now = await _naming(env.conn, s)
        assert now == named, ("rows naming P", route, sorted(set(now) ^ set(named))[:4])
    case(monkeypatch, body, prefix="mdplrb")


def _seeded_mutant(monkeypatch, tmp_path, route):
    """The route's seeded test with its own call of the read by id taken
    out: the cut took out one call, the route's (checked first); then red at
    the test's first assertion, the answer, which is a 200 for the purged
    id's row."""
    taken, first = [], None
    try:
        _seeded_case(monkeypatch, tmp_path, route, taken=taken)
    except AssertionError as e:
        first = str(e).splitlines()[0]
    assert taken == [route], ("the cut", route, taken)
    assert first is not None and first.startswith("('answer', %r, Answer(200, " % route), first
    print("MUTANT-RED %s (read by id): %s" % (route, first[:200]))


def test_unlock_achievement_refuses_a_purged_ids_deleted_user_row(monkeypatch, tmp_path):
    """Its own read finds the row; the read by id refuses it. Without the
    read by id, the achievement, the gold on the row and its ledger row are
    stored for it."""
    _seeded_case(monkeypatch, tmp_path, "unlock_achievement")


def test_admin_grant_achievement_refuses_a_purged_ids_deleted_user_row(monkeypatch, tmp_path):
    """Its own read finds the row; the read by id refuses it ("Player not
    found"). Without the read by id, the achievement, the gold on the row,
    its ledger row, the title item and the moderator record are stored."""
    _seeded_case(monkeypatch, tmp_path, "admin_grant_achievement")


def test_generate_link_code_refuses_a_purged_ids_deleted_user_row(monkeypatch, tmp_path):
    """Its own read finds the row; the read by id refuses it, and the row's
    link code stays. Without the read by id, that code is removed and a new
    code naming the row is stored."""
    _seeded_case(monkeypatch, tmp_path, "generate_link_code")


def test_mutant_unlock_achievement_without_the_read_by_id_pays_the_deleted_user_row(monkeypatch, tmp_path):
    _seeded_mutant(monkeypatch, tmp_path, "unlock_achievement")


def test_mutant_admin_grant_achievement_without_the_read_by_id_pays_the_deleted_user_row(monkeypatch, tmp_path):
    _seeded_mutant(monkeypatch, tmp_path, "admin_grant_achievement")


def test_mutant_generate_link_code_without_the_read_by_id_stores_a_code(monkeypatch, tmp_path):
    _seeded_mutant(monkeypatch, tmp_path, "generate_link_code")


# -- the control -----------------------------------------------------------------------------------

def test_control_without_the_deletion_every_route_answers_as_before(monkeypatch, tmp_path):
    """Every scene of the four, H holding P's two keys and committing nothing: each
    route waited at its key and answers as before, the read by id run once on
    P's id with nothing pending. Then toggle_ranked for a Steam id never seen:
    it still creates the player under the key; at the read by id the new
    row's GlickoRating is pending (and no other store), and both rows are
    stored."""
    async def body(env):
        _seams(env, tmp_path)
        seen = _spy(env)
        for route, build in SCENES.items():
            s = await build(env)
            del seen[:]
            ans, waited, _left, _named = await _scene(env, s, delete=False)
            assert ans.status == 200 and s.ok(ans.body), ("control", route, ans)
            assert "pg_advisory_xact_lock_shared" in waited, ("the wait", route, waited)
            assert seen == [(str(s.p.id), 0, 0, 0)], ("the read by id", route, seen)
        new = P(None, _sid(150), "Reread toggle new")
        fresh = Scene("toggle_ranked", new, _toggle_call(new, new.name), NOT_FOUND,
                      lambda body: body == {"steam_id": new.sid, "ranked_enabled": True}, creates=True)
        del seen[:]
        ans, waited, _left, _named = await _scene(env, fresh, delete=False)
        assert ans.status == 200 and fresh.ok(ans.body), ("control", "toggle_ranked, a new id", ans)
        assert "pg_advisory_xact_lock_shared" in waited, ("the wait", "toggle_ranked, a new id", waited)
        made = await env.conn.fetchrow(
            "SELECT id, display_name, deleted_at FROM players WHERE steam_id = $1", new.sid)
        assert made is not None and made["deleted_at"] is None and made["display_name"] == new.name, made
        assert seen == [(str(made["id"]), 1, 0, 0)], ("the read by id", "toggle_ranked, a new id", seen)
        assert await env.conn.fetchval("SELECT count(*) FROM glicko_ratings WHERE player_id = $1", made["id"]) == 1
    case(monkeypatch, body, prefix="mdplrb")
