"""Lobby invites on PostgreSQL (migration 405's change): the keys, the repeats
and the refusals of the five keyed invite requests (send, challenge, accept,
decline, cancel), design note section 11, against a local PostgreSQL through
inv_pg (one cf_pg case schema per case, the real handlers in main.py).

Every test pins one behaviour, runs a mutant it must fail (a statement
rewrite whose hits list is asserted non-empty, or a stand-in for one main.py
function), and a control showing the real path passes. Answers compare byte
for byte (Answer.wire).
"""

import asyncio
import contextlib
import json
import os
import sys
import types
import typing
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import inv_pg as inv  # noqa: E402
from inv_pg import BELOW, FLOOR, Answer, Req, case, key, waiting_on  # noqa: E402

import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402


ROUTES = ("send", "challenge", "accept", "decline", "cancel")
SENDS = ("send", "challenge")
PATHS = ("accept", "decline", "cancel")
# The handler each route calls, looked up on main at call time, so a stand-in
# set with monkeypatch is the one that runs.
FN = {"send": "invite_send", "challenge": "invite_send", "accept": "invite_accept",
      "decline": "invite_decline", "cancel": "invite_cancel"}
MODEL = {"send": main._InviteSendReq, "challenge": main._InviteSendReq,
         "accept": main._InviteAcceptReq, "decline": main._InviteAnswerReq,
         "cancel": main._InviteAnswerReq}
# The route a receipt and a fingerprint name: a challenge is a send.
FP_ROUTE = {"send": "send", "challenge": "send", "accept": "accept", "decline": "decline",
            "cancel": "cancel"}

REUSED = Answer(409, "idempotency_key_reused")
NOT_FOUND = Answer(404, "invite_not_found")
BAD_ID = "not-an-invite-id"

# The receipt read (_invite_prior), by a fragment only it holds.
PRIOR = "FROM invite_receipts WHERE caller_player_id"
# The invitee's row through a live copy (_INVITE_INVITEE_ROW_SQL): accept's and
# decline's read.
INVITEE_ROW = "FROM lobby_invites i WHERE i.id"
# The send's lobby read under its lock (_invite_lobby_gates).
GATES_LOBBY = "SELECT id, status, kicked_steam_ids FROM"


# -- helpers --------------------------------------------------------------------

async def _safe(aw):
    """An awaited handler call as an Answer; an exception that is not an HTTP
    answer (a constraint violation under a mutant) becomes a 500 named by its
    type."""
    try:
        return await aw
    except Exception as exc:                               # noqa: BLE001
        return Answer(500, type(exc).__name__)


def _send_body(sender, invitee, lid):
    return {"invitee_steam_id": invitee.sid, "mode": "team",
            "lobby_id": str(lid) if lid is not None else None, "display_name": sender.name}


def _path_body(route, caller):
    return {"display_name": caller.name} if route == "accept" else {}


async def _ask(env, caller, k, route, path, body, version=FLOOR):
    """`caller`'s keyed request on `route` (path: the invite id in the path, as
    given; body: the request model's fields other than the key)."""
    req = MODEL[route](idempotency_key=k, **body)
    r = Req(caller.sid, version)
    if route in SENDS:
        return await _safe(env.call(lambda db: getattr(main, FN[route])(req, r, db)))
    return await _safe(env.call(lambda db: getattr(main, FN[route])(str(path), req, r, db)))


def _canon(spec):
    """A request as its fingerprint reads it: route, path, validated body."""
    route, path, body = spec
    dump = MODEL[route](**body).model_dump(mode="json", exclude={"idempotency_key"})
    return (FP_ROUTE[route], None if route in SENDS else str(path),
            json.dumps(dump, sort_keys=True, separators=(",", ":")))


def _changed(name, info, value):
    """`value` changed to another value the field accepts. A field type this
    cannot change fails here, so a field a model gains is never skipped."""
    args = typing.get_args(info.annotation) or (info.annotation,)
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return value + "0"
    if value is None:
        if int in args:
            return 1
        if str in args:
            return "0"
        if bool in args:
            return True
    raise AssertionError("no change written for field %s (%r)" % (name, info.annotation))


def _one_field_changes(model, body):
    """{field: body with that one field changed}, for every field the model
    declares except the key -- read from model_fields, never listed here."""
    out = {}
    for name, info in model.model_fields.items():
        if name == "idempotency_key":
            continue
        cur = body.get(name, info.default)
        new = dict(body, **{name: _changed(name, info, cur)})
        a = model(**body).model_dump(mode="json", exclude={"idempotency_key"})
        b = model(**new).model_dump(mode="json", exclude={"idempotency_key"})
        assert a != b, ("the change left the canonical form as it was", name)
        out[name] = new
    assert "idempotency_key" in model.model_fields
    assert len(out) == len(model.model_fields) - 1
    return out


async def _live(env, lid, mode="team"):
    """The lobby's live members by the join's own rule (a fresh 'lobby' row)."""
    rows = await env.conn.fetch(
        "SELECT player_id FROM %s WHERE series_id = $1 AND status = 'lobby' AND %s"
        % (inv.QUEUE_TABLE[mode], main.LOBBY_MEMBER_FRESH_SQL), lid)
    return [r["player_id"] for r in rows]


async def _seats(env, p, lid, mode="team"):
    return await env.conn.fetchval(
        "SELECT COUNT(*) FROM %s WHERE player_id = $1 AND series_id = $2" % inv.QUEUE_TABLE[mode],
        p.id, lid)


async def _receipts(env, p, k=None):
    if k is None:
        return await env.conn.fetchval(
            "SELECT COUNT(*) FROM invite_receipts WHERE caller_player_id = $1", p.id)
    return await env.conn.fetchval(
        "SELECT COUNT(*) FROM invite_receipts WHERE caller_player_id = $1"
        "   AND idempotency_key = $2", p.id, uuid.UUID(str(k)))


async def _delete_copy(env, iid, p):
    """`p` deletes their mail copy of invite `iid`."""
    mid = await env.mail_of(iid)
    assert mid is not None, iid
    ans = await env.call(lambda db: main.mail_delete(str(mid), Req(p.sid), db))
    assert ans.status == 200, ans


async def _set_lobby_status(env, lid, status):
    """The lobby row's status as a start ('active') or a closure ('canceled')
    leaves it (sql/193's statuses), its members' rows untouched."""
    await env.conn.execute("UPDATE team_lobbies SET status = $2 WHERE id = $1", lid, status)


async def _fill(env, lid, mode="team"):
    """Joins fresh players until the lobby holds its capacity."""
    cap = main._invite_capacity(mode)
    for _ in range(cap):
        if len(await env.members(mode, lid)) >= cap:
            break
        ans = await env.join(mode, await env.player(), lid)
        assert ans.status == 200, ans
    assert len(await env.members(mode, lid)) == cap


@contextlib.contextmanager
def _rw(env, *specs):
    """Several statement rewrites at once (old, new, where); yields their hits
    lists."""
    with contextlib.ExitStack() as st:
        yield [st.enter_context(env.rewriting(o, n, where=w)) for o, n, w in specs]


@contextlib.contextmanager
def _patch(**attrs):
    """main.<name> replaced for the block; yields no hits lists."""
    with pytest.MonkeyPatch.context() as m:
        for name, value in attrs.items():
            assert hasattr(main, name), name
            m.setattr(main, name, value)
        yield []


# -- one world per route ----------------------------------------------------------
#
# Caller A holds an invite J (team, someone else's lobby) and another invite Z
# (ovt); for send and cancel A hosts a team lobby LA, and for cancel A has sent
# invite I from it. A's first request per route: send G1 into LA; challenge G1
# (team); accept J; decline J; cancel I.

async def _world(env, route):
    w = types.SimpleNamespace(route=route)
    w.a = await env.player()
    w.g1, w.g2 = await env.players(2)
    w.lt, (w.h,) = await env.lobby("team", 1)
    w.j = await env.invite(w.h, w.a, "team", w.lt)
    w.lo, (w.ho,) = await env.lobby("ovt", 1)
    w.z = await env.invite(w.ho, w.a, "ovt", w.lo)
    w.la = await env.create("team", w.a) if route in ("send", "cancel") else None
    w.i = await env.invite(w.a, w.g1, "team", w.la) if route == "cancel" else None
    w.first = {
        "send": ("send", None, _send_body(w.a, w.g1, w.la)),
        "challenge": ("challenge", None, _send_body(w.a, w.g1, None)),
        "accept": ("accept", w.j, _path_body("accept", w.a)),
        "decline": ("decline", w.j, {}),
        "cancel": ("cancel", w.i, {}),
    }[route]
    return w


async def _run_first(env, w, k):
    """A's first request with key k; it commits. Names the invite it made or
    answered (target), that invite's invitee and its lobby."""
    ans = await _ask(env, w.a, k, *w.first)
    assert ans.status == 200, ans
    if w.route in SENDS:
        w.target, w.invitee = uuid.UUID(ans["invite_id"]), w.g1
        w.lobby = w.la if w.route == "send" else uuid.UUID(ans["lobby_id"])
    elif w.route == "cancel":
        w.target, w.invitee, w.lobby = w.i, w.g1, w.la
    else:
        w.target, w.invitee, w.lobby = w.j, w.a, w.lt
    assert await _receipts(env, w.a, k) == 1
    return ans


async def _expected_repeat(env, w, first):
    """Section 4.2's repeat answer, built from the invite row and the lobby as
    they are now: a send's {invite_id, state, expires_at}, with a challenge's
    create fields only while A is a live member; an accept's join answer while
    A is a live member, invite_answered (accepted) once not; a decline's and a
    cancel's fixed state."""
    if w.route == "decline":
        return Answer(200, {"state": "declined"})
    if w.route == "cancel":
        return Answer(200, {"state": "cancelled"})
    live = await _live(env, w.lobby)
    if w.route == "accept":
        if w.a.id not in live:
            return Answer(409, {"error": "invite_answered", "state": "accepted"})
        return Answer(200, {"status": "ok", "lobby_id": str(w.lobby), "player_count": len(live),
                            "max_players": main._invite_capacity("team")})
    row = await env.row(w.target)
    out = {"invite_id": str(w.target), "state": row["state"], "expires_at": first["expires_at"]}
    if w.route == "challenge" and w.a.id in live:
        out.update({k: v for k, v in first.body.items() if k not in out})
    return Answer(200, out)


# -- the key scope, one test per keyed invite request ------------------------------

def _probes(w):
    """Every other keyed invite request A can make with the first's key: the
    other routes, the same route on another invite (an existing one, an
    unknown id, a malformed id), and the same request with one model field
    changed. The unchanged repeat is left out (it is the control)."""
    a = w.a
    out = [("send", None, _send_body(a, w.g2, w.lobby)), ("challenge", None, _send_body(a, w.g2, None))]
    for r in PATHS:
        for path in (w.target, w.j, w.z, uuid.uuid4(), BAD_ID):
            out.append((r, path, _path_body(r, a)))
    fr, fpath, fbody = w.first
    changed = {name: (fr, fpath, body) for name, body in _one_field_changes(MODEL[fr], fbody).items()}
    out.extend(changed.values())
    first = _canon(w.first)
    seen, probes = set(), []
    for spec in out:
        c = _canon(spec)
        if c == first or c in seen:
            continue
        seen.add(c)
        probes.append(spec)
    assert any(FP_ROUTE[s[0]] != FP_ROUTE[fr] for s in probes)
    if fr in PATHS:
        assert any(s[0] == fr and str(s[1]) != str(fpath) for s in probes)
    return probes, changed


async def _key_states(env, w):
    """The first request's invite as it goes on: as committed; answered;
    its invitee's mail copy deleted; its lobby closed (cumulative)."""
    yield "as committed"
    if w.route in SENDS:
        ans = await env.decline(w.g1, w.target)
        assert ans.status == 200, ans
    assert (await env.row(w.target))["state"] != "pending"
    yield "its invite answered"
    await _delete_copy(env, w.target, w.invitee)
    yield "its copy deleted"
    await _set_lobby_status(env, w.lobby, "canceled")
    yield "its lobby closed"


def _state_first(route, real):
    """A mutant handler: the route's own path and state checks run BEFORE its
    receipt read (the real handler follows them)."""
    if route in SENDS:
        async def mutant(req, request, db):
            me = await main._mail_caller(request, db)
            await main._invite_invitee_or_raise(db, me, req.invitee_steam_id)
            lid, _t = main._invite_path_id(req.lobby_id)
            mode = (req.mode or "").strip().lower()
            if lid is not None and mode in main._INVITE_LOBBY_TABLES:
                st = (await db.execute(text(
                    "SELECT status FROM %s WHERE id = :lid" % main._INVITE_LOBBY_TABLES[mode]
                ), {"lid": lid})).scalar()
                if st != "open":
                    raise HTTPException(status_code=409, detail="lobby_closed")
            return await real(req, request, db)
        return mutant

    async def mutant(invite_id, req, request, db):
        me = await main._mail_caller(request, db)
        iid, _t = main._invite_path_id(invite_id)
        if iid is None:
            raise HTTPException(status_code=400, detail="invite_id_invalid")
        if route == "cancel":
            row = (await db.execute(text(
                "SELECT state, end_reason, (expires_at <= NOW()) AS past FROM lobby_invites"
                " WHERE id = :iid"), {"iid": iid})).mappings().first()
        else:
            row = (await db.execute(text(main._INVITE_INVITEE_ROW_SQL),
                                    {"iid": iid, "me": me["id"]})).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="invite_not_found")
        main._invite_refuse_ended(row, void_as_answered=(route != "accept"))
        return await real(invite_id, req, request, db)
    return mutant


@pytest.mark.parametrize("route", ROUTES)
def test_a_key_used_on_another_invite_request_is_refused_before_any_check(monkeypatch, route):
    """A key A used on one keyed invite request, sent again on another route,
    on another invite (existing, unknown or malformed) or with any one field
    of the request model changed, answers 409 idempotency_key_reused and
    writes nothing -- also once the first's invite is answered, its copy
    deleted and its lobby closed, so the receipt is read before any route,
    path or state check. Control: the unchanged repeat gets section 4.2's
    repeat answer and writes nothing. Mutants: the receipt looked up by route;
    by invite (the path routes); the route's own state and path checks run
    before the receipt read."""
    async def body(env):
        w = await _world(env, route)
        k = key()
        first = await _run_first(env, w, k)
        probes, changed = _probes(w)
        states = []
        async for state in _key_states(env, w):
            await env.fresh("team", w.lobby)
            snap = await env.snapshot()
            for spec in probes:
                got = await _ask(env, w.a, k, *spec)
                assert got.wire == REUSED.wire, (state, spec, got)
                assert await env.snapshot() == snap, (state, spec, "a reused key wrote")
            exp = await _expected_repeat(env, w, first)
            again = await _ask(env, w.a, k, *w.first)
            assert again.wire == exp.wire, (state, "the repeat", again, exp)
            assert await env.snapshot() == snap, (state, "the repeat wrote")
            states.append(state)
        assert len(states) == 4, states

        # mutant 1: the receipt looked up by route -- a request on another route
        # misses it and runs its own checks
        cross = "cancel" if FP_ROUTE[route] == "decline" else "decline"
        spec = (cross, uuid.uuid4(), {})
        assert (await _ask(env, w.a, k, *spec)).wire == REUSED.wire
        with env.rewriting(" AND idempotency_key = ",
                           " AND route = '%s' AND idempotency_key = " % cross, where=PRIOR) as hits:
            got = await _ask(env, w.a, k, *spec)
        assert hits, "the by-route mutant reached no receipt read"
        assert got.wire != REUSED.wire, ("the by-route mutant kept the refusal", got)

        # mutant 2: the receipt looked up by invite -- the same route on another
        # invite misses it
        if route in PATHS:
            other = uuid.uuid4()
            spec = (route, other, _path_body(route, w.a))
            assert (await _ask(env, w.a, k, *spec)).wire == REUSED.wire
            with env.rewriting(" AND idempotency_key = ",
                               " AND invite_id = '%s' AND idempotency_key = " % other,
                               where=PRIOR) as hits:
                got = await _ask(env, w.a, k, *spec)
            assert hits, "the by-invite mutant reached no receipt read"
            assert got.wire != REUSED.wire, ("the by-invite mutant kept the refusal", got)

        # mutant 3: the route's state and path checks before the receipt read
        if route in PATHS:
            targets = [(route, uuid.uuid4(), _path_body(route, w.a)), (route, BAD_ID, _path_body(route, w.a))]
        elif route == "send":
            targets = [("send", None, _send_body(w.a, w.g2, w.lobby))]
        else:
            targets = [changed["invitee_steam_id"]]
        for spec in targets:
            assert (await _ask(env, w.a, k, *spec)).wire == REUSED.wire, spec
        with pytest.MonkeyPatch.context() as m:
            m.setattr(main, FN[route], _state_first(route, getattr(main, FN[route])))
            for spec in targets:
                got = await _ask(env, w.a, k, *spec)
                assert got.wire != REUSED.wire, ("the state-first mutant kept the refusal", spec, got)
    case(monkeypatch, body)


# -- repeats: answered before any check that can change ------------------------------

async def _repeat_steps(env, w):
    """What a repeat must not run into, one change at a time and cumulative:
    the invite's copy deleted; its lobby filled; its host gone (the host
    leaves); the lobby started; then closed; and, while A holds a seat there,
    A's seat gone stale."""
    await _delete_copy(env, w.target, w.invitee)
    await env.fresh("team", w.lobby)
    yield "copy deleted"
    await _fill(env, w.lobby)
    await env.fresh("team", w.lobby)
    yield "lobby filled"
    host_id = await env.conn.fetchval("SELECT host_player_id FROM team_lobbies WHERE id = $1", w.lobby)
    host = w.a if host_id == w.a.id else w.h
    assert host.id == host_id, (host_id, w.a, w.h)
    ans = await env.leave("team", host, w.lobby)
    assert ans.status == 200, ans
    assert host.id not in await env.members("team", w.lobby)
    await env.fresh("team", w.lobby)
    yield "host moved"
    await _set_lobby_status(env, w.lobby, "active")
    await env.fresh("team", w.lobby)
    yield "lobby started"
    await _set_lobby_status(env, w.lobby, "canceled")
    await env.fresh("team", w.lobby)
    yield "lobby closed"
    if w.a.id in await env.members("team", w.lobby):
        await env.stale("team", w.a, w.lobby)
        yield "caller's seat stale"


@pytest.mark.parametrize("route", ROUTES)
def test_a_repeat_gets_the_repeat_answer_whatever_changed_since(monkeypatch, route):
    """After the first request commits, its copy is deleted, its lobby filled,
    its host moved, the lobby started and closed: at each step the repeat with
    its key gets section 4.2's repeat answer built from the invite row and the
    lobby as they are now, and writes nothing; an accept's repeat never seats
    A twice. Mutant: the receipt read finds nothing, so the repeat runs the
    route's checks."""
    async def body(env):
        w = await _world(env, route)
        k = key()
        first = await _run_first(env, w, k)
        answers = []
        async for step in _repeat_steps(env, w):
            exp = await _expected_repeat(env, w, first)
            snap = await env.snapshot()
            got = await _ask(env, w.a, k, *w.first)
            assert got.wire == exp.wire, (step, got, exp)
            assert await env.snapshot() == snap, (step, "a repeat wrote")
            if route == "accept":
                assert await _seats(env, w.a, w.lobby) == 1, (step, "a repeat seated A again")
            answers.append(got.wire)
        assert len(answers) >= 5, answers
        if route in ("send", "challenge", "accept"):
            # the answer followed the row and the lobby: it changed on the way
            assert len(set(answers)) > 1, answers
        if route in SENDS:
            assert (await env.row(w.target))["state"] == "void"
        # mutant: the receipt read finds nothing
        exp = await _expected_repeat(env, w, first)
        with env.rewriting("WHERE caller_player_id = ", "WHERE FALSE AND caller_player_id = ",
                           where=PRIOR) as hits:
            got = await _ask(env, w.a, k, *w.first)
        assert hits, "the mutant reached no receipt read"
        assert got.wire != exp.wire, ("the receipt-less repeat still got the repeat answer", got)
    case(monkeypatch, body)


async def _settle(env, fut, first_pid, tries=100):
    """Until `fut` is done or a backend other than `first_pid` waits on a lock
    (bounded: `tries` polls 50 ms apart)."""
    for _ in range(tries):
        if fut.done():
            return
        n = await env.conn.fetchval(
            "SELECT COUNT(*) FROM pg_stat_activity"
            " WHERE pid <> $1 AND cardinality(pg_blocking_pids(pid)) > 0", first_pid)
        if n:
            return
        await asyncio.sleep(0.05)


# The identity locks a mutant moves to another lock space (the two-key form),
# so the repeat no longer waits on the first: the advisory identity lock every
# route takes, and for a send also the per-sender lock (same function) and the
# identity row's re-read lock.
_LOCK_MUTANT = (("pg_advisory_xact_lock(hashtext(", "pg_advisory_xact_lock(7, hashtext(", None),)
_SEND_ROW_MUTANT = ((" FOR NO KEY UPDATE", "", "SELECT id, steam_id, deleted_at FROM players"),)


async def _race(env, route, mutant):
    """A's first request held at its receipt's insert (a second session holds
    invite_receipts in SHARE mode), its repeat sent with the same key and
    bytes, the hold released. Returns (world, first, repeat, queued, hits):
    queued, the pids that waited on the first (None under a mutant)."""
    w = await _world(env, route)
    k = key()
    side = await env.side()
    await side.execute("BEGIN")
    await side.execute("LOCK TABLE invite_receipts IN SHARE MODE")
    tasks, released, queued, hits = [], False, None, []
    try:
        tasks.append(asyncio.ensure_future(_ask(env, w.a, k, *w.first)))
        held = await waiting_on(env, side.get_server_pid())
        assert len(held) == 1, ("the first did not stop at its receipt's insert", held)
        with _rw(env, *(mutant or ())) as hits:
            tasks.append(asyncio.ensure_future(_ask(env, w.a, k, *w.first)))
            if mutant:
                await _settle(env, tasks[1], held[0])
            else:
                queued = await waiting_on(env, held[0])
            await side.execute("ROLLBACK")
            released = True
            _done, pending = await asyncio.wait(tasks, timeout=30)
        assert not pending, "a request never finished"
    finally:
        if not released:
            await side.execute("ROLLBACK")
        left = [t for t in tasks if not t.done()]
        if left:
            await asyncio.wait(left, timeout=30)
    w.k = k
    return w, tasks[0].result(), tasks[1].result(), queued, hits


@pytest.mark.parametrize("route", ROUTES)
def test_a_repeat_sent_while_the_first_runs_gets_the_repeat_answer_once_it_commits(monkeypatch, route):
    """Two sessions: the first request is held inside its transaction, past
    its checks, at its receipt's insert; the repeat (same key, same bytes)
    waits on the first's identity lock, and once the first commits it reads
    the first's receipt and gets the first's answer byte for byte: one
    receipt, one invite, one seat, and a later repeat writes nothing.
    Mutant: the identity locks moved to another lock space for the repeat,
    so it runs beside the first and gets another answer."""
    async def body(env):
        w, first, again, queued, _hits = await _race(env, route, None)
        assert first.status == 200, first
        assert queued, "the repeat did not wait on the first's identity lock"
        assert again.wire == first.wire, ("the concurrent repeat", again, first)
        assert await _receipts(env, w.a, w.k) == 1
        if route in SENDS:
            n = await env.conn.fetchval(
                "SELECT COUNT(*) FROM lobby_invites WHERE sender_player_id = $1"
                "   AND invitee_player_id = $2", w.a.id, w.g1.id)
            assert n == 1, n
        if route == "accept":
            assert await _seats(env, w.a, w.lt) == 1
        snap = await env.snapshot()
        later = await _ask(env, w.a, w.k, *w.first)
        assert later.wire == first.wire, later
        assert await env.snapshot() == snap, "a later repeat wrote"
        # mutant
        specs = _LOCK_MUTANT + (_SEND_ROW_MUTANT if route in SENDS else ())
        _w2, first2, again2, _q, hits = await _race(env, route, specs)
        assert first2.status == 200, first2
        assert all(hits), ("a lock mutant reached no statement", [len(h) for h in hits])
        assert again2.wire != first2.wire, ("the unordered repeat still got the repeat answer", again2)
    case(monkeypatch, body)


# -- a refused request writes no receipt, and its retry runs again ---------------------

def _receipt_on_refusal(route, real, spare):
    """A mutant handler: a refused request commits a receipt for its key and
    fingerprint (naming its path's invite, or `spare` for a send), so its
    retry is answered as a repeat."""
    async def keep(db, request, req, iid, text_id):
        await db.rollback()
        me = await main._mail_caller(request, db)
        fp = main._invite_request_fp(FP_ROUTE[route], text_id, me["id"], req)
        await main._invite_write_receipt(db, me["id"], main._mail_parse_key(req.idempotency_key),
                                         FP_ROUTE[route], iid, fp)
        await db.commit()

    if route in SENDS:
        async def mutant(req, request, db):
            try:
                return await real(req, request, db)
            except HTTPException as exc:
                await keep(db, request, req, spare, None)
                raise exc
        return mutant

    async def mutant(invite_id, req, request, db):
        try:
            return await real(invite_id, req, request, db)
        except HTTPException as exc:
            iid, text_id = main._invite_path_id(invite_id)
            await keep(db, request, req, iid, text_id)
            raise exc
    return mutant


async def _refusal_world(env, route):
    """A request refused for a state that a later change lifts (decline: one
    that stays refused); returns the caller, the spec, the refusal, the
    change, a check of the retry's effect, and a spare invite id."""
    sl, (sh,) = await env.lobby("ovt", 1)
    c = types.SimpleNamespace(spare=await env.invite(sh, await env.player(), "ovt", sl))
    a = c.caller = await env.player()
    if route == "send":
        la = await env.create("team", a)
        fillers = await env.players(3)
        for p in fillers:
            assert (await env.join("team", p, la)).status == 200
        g = await env.player()
        c.spec = ("send", None, _send_body(a, g, la))
        c.refusal = Answer(409, "lobby_full")

        async def change():
            assert (await env.leave("team", fillers[-1], la)).status == 200

        async def effect(ans):
            if ans.status != 200:
                return False
            row = await env.row(uuid.UUID(ans["invite_id"]))
            return (row["invitee_player_id"], row["lobby_id"], row["state"]) == (g.id, la, "pending")
    elif route == "challenge":
        g = await env.player(version=BELOW)
        c.spec = ("challenge", None, _send_body(a, g, None))
        c.refusal = Answer(409, "invitee_needs_update")

        async def change():
            await env.conn.execute("UPDATE players SET mod_version = $2 WHERE id = $1", g.id, FLOOR)

        async def effect(ans):
            if ans.status != 200:
                return False
            row = await env.row(uuid.UUID(ans["invite_id"]))
            return (row["invitee_player_id"], row["kind"]) == (g.id, "challenge")
    elif route == "accept":
        lid, ps = await env.lobby("team", 3)
        j = await env.invite(ps[0], a, "team", lid)
        late = await env.player()
        assert (await env.join("team", late, lid)).status == 200
        c.spec = ("accept", j, _path_body("accept", a))
        c.refusal = Answer(409, "That lobby is full")

        async def change():
            assert (await env.leave("team", late, lid)).status == 200

        async def effect(ans):
            return (ans.status == 200 and a.id in await env.members("team", lid)
                    and (await env.row(j))["state"] == "accepted")
    elif route == "decline":
        lid, (h,) = await env.lobby("team", 1)
        j = await env.invite(h, a, "team", lid)
        await env.age(j, expired_s=5)
        c.spec = ("decline", j, {})
        c.refusal = Answer(410, "invite_expired")

        async def change():
            return None

        async def effect(ans):
            return ans.wire == c.refusal.wire
    else:
        lid, (h, b) = await env.lobby("team", 2)
        i = await env.invite(h, await env.player(), "team", lid)
        c.caller = b
        c.spec = ("cancel", i, {})
        c.refusal = NOT_FOUND

        async def change():
            # the host's seat goes stale: b is the lobby's effective host
            await env.stale("team", h, lid)

        async def effect(ans):
            return ans.wire == Answer(200, {"state": "cancelled"}).wire and \
                (await env.row(i))["state"] == "cancelled"
    c.change, c.effect = change, effect
    return c


async def _refuse_then_retry(env, route):
    c = await _refusal_world(env, route)
    k = key()
    snap = await env.snapshot()
    refused = await _ask(env, c.caller, k, *c.spec)
    wrote = await env.snapshot() != snap
    receipts = await _receipts(env, c.caller)
    await c.change()
    retry = await _ask(env, c.caller, k, *c.spec)
    return c, refused, wrote, receipts, retry, await c.effect(retry)


@pytest.mark.parametrize("route", ROUTES)
def test_a_refused_request_writes_no_receipt_and_its_retry_runs_again(monkeypatch, route):
    """A request refused by its own checks writes nothing, no receipt among
    it; once the state that refused it changes, its retry with the same key
    and bytes runs the checks again and commits (a decline refused as expired
    is refused again, not answered as a repeat). Mutant: the refusal commits
    a receipt for its key, so the retry is answered as a repeat."""
    async def body(env):
        c, refused, wrote, receipts, retry, done = await _refuse_then_retry(env, route)
        assert refused.wire == c.refusal.wire, refused
        assert not wrote, "the refusal wrote"
        assert receipts == 0, receipts
        assert done, ("the retry did not run again", retry)
        # mutant
        real = getattr(main, FN[route])
        c2 = await _refusal_world(env, route)
        with pytest.MonkeyPatch.context() as m:
            m.setattr(main, FN[route], _receipt_on_refusal(route, real, c2.spare))
            k = key()
            refused2 = await _ask(env, c2.caller, k, *c2.spec)
            receipts2 = await _receipts(env, c2.caller)
            await c2.change()
            retry2 = await _ask(env, c2.caller, k, *c2.spec)
            done2 = await c2.effect(retry2)
        assert refused2.wire == c2.refusal.wire, refused2
        assert receipts2 >= 1 and not done2, ("the mutant's retry ran again", receipts2, retry2)
    case(monkeypatch, body)


# -- refusals: every refusal in section 4.2 -------------------------------------------

async def _pin_refusal(env, label, setup, expected, mutant, ends=None):
    """setup() builds a fresh world and returns {ask, iid?, same_as?}; ask()
    is refused with `expected` byte for byte. Nothing is written -- for an
    accept the join refuses in a way that ends the invite, only that end
    (void with `ends`) and no receipt. `same_as`, when given, is the join's
    own answer to a plain join and must equal it. On a second fresh world,
    `mutant(ctx)` (a context manager yielding hits lists) turns the answer
    into another one."""
    c = await setup()
    exp = expected(c) if callable(expected) else expected
    if "same_as" in c:
        own = await c["same_as"]()
        assert own.wire == exp.wire, (label, "the join's own answer", own)
    snap = await env.snapshot()
    got = await c["ask"]()
    assert got.wire == exp.wire, (label, got, exp)
    after = await env.snapshot()
    if ends is None:
        assert after == snap, (label, "the refusal wrote")
    else:
        row = await env.row(c["iid"])
        assert (row["state"], row["end_reason"]) == ("void", ends), (label, row)
        assert after["invite_receipts"] == snap["invite_receipts"], (label, "a receipt was written")
    c2 = await setup()
    exp2 = expected(c2) if callable(expected) else expected
    with mutant(c2) as hits:
        bad = await c2["ask"]()
    assert all(hits), (label, "a mutant rewrite reached no statement")
    assert bad.wire != exp2.wire, (label, "the mutant kept the refusal", bad)


def _drop_member(pid):
    real = main._invite_live_members

    async def live(db, mode, lid):
        return [m for m in await real(db, mode, lid) if m["player_id"] != pid]
    return live


def _add_member(pid):
    real = main._invite_live_members

    async def live(db, mode, lid):
        return list(await real(db, mode, lid)) + [{"player_id": pid}]
    return live


def _refuse_as(forced):
    """A mutant state check: a void invite answered as `forced` says, whatever
    the route asks for."""
    real = main._invite_refuse_ended

    def refuse(row, *, void_as_answered):
        return real(row, void_as_answered=forced)
    return refuse


def _no_state_check(row, *, void_as_answered):
    return None


def _any_path_id(value):
    """A mutant parse: every path parses, as a fresh id."""
    return uuid.uuid4(), str(value)


def test_every_send_refusal_answers_its_own_detail_and_writes_nothing(monkeypatch):
    """invitee_needs_update, kicked_from_lobby, already_in_lobby, lobby_full,
    lobby_closed, invites_full, already_invited, and not_in_lobby (403) for a
    sender who is not a live member -- not a member at all, or a stale seat.
    Each with its own mutant (the check's input rewritten or stood in for)."""
    real_cap = main._invite_capacity

    async def body(env):
        def send(a, g, lid):
            return lambda: _safe(env.send(a, g, "team", lid))

        async def old_invitee():
            lid, (a,) = await env.lobby("team", 1)
            return {"ask": send(a, await env.player(version=BELOW), lid)}
        await _pin_refusal(env, "invitee_needs_update", old_invitee, Answer(409, "invitee_needs_update"),
                           lambda c: _patch(INVITE_FLOOR_VERSION=BELOW))

        async def kicked():
            lid, (a, x) = await env.lobby("team", 2)
            assert (await env.kick("team", a, x)).status == 200
            return {"ask": send(a, x, lid)}
        await _pin_refusal(env, "kicked_from_lobby", kicked, Answer(403, "kicked_from_lobby"),
                           lambda c: _rw(env, (GATES_LOBBY, "SELECT id, status, NULL AS kicked_steam_ids FROM",
                                               None)))

        async def member():
            lid, (a, x) = await env.lobby("team", 2)
            return {"ask": send(a, x, lid), "x": x}
        await _pin_refusal(env, "already_in_lobby", member, Answer(409, "already_in_lobby"),
                           lambda c: _patch(_invite_live_members=_drop_member(c["x"].id)))

        async def full():
            lid, (a, *_rest) = await env.lobby("team", main._invite_capacity("team"))
            return {"ask": send(a, await env.player(), lid)}
        await _pin_refusal(env, "lobby_full", full, Answer(409, "lobby_full"),
                           lambda c: _patch(_invite_capacity=lambda mode: real_cap(mode) + 1))

        async def closed():
            lid, (a,) = await env.lobby("team", 1)
            await _set_lobby_status(env, lid, "canceled")
            return {"ask": send(a, await env.player(), lid)}
        await _pin_refusal(env, "lobby_closed", closed, Answer(409, "lobby_closed"),
                           lambda c: _rw(env, (GATES_LOBBY,
                                               "SELECT id, CAST('open' AS text) AS status, kicked_steam_ids FROM",
                                               None)))

        pending_read = (" AND expires_at > NOW()", " AND expires_at > NOW() AND FALSE",
                        "SELECT id, invitee_player_id FROM lobby_invites")

        async def capped():
            lid, (a,) = await env.lobby("team", 1)
            for p in await env.players(2 * main._invite_capacity("team")):
                await env.invite(a, p, "team", lid)
            return {"ask": send(a, await env.player(), lid)}
        await _pin_refusal(env, "invites_full", capped, Answer(409, "invites_full"),
                           lambda c: _rw(env, pending_read))

        async def twice():
            lid, (a,) = await env.lobby("team", 1)
            g = await env.player()
            ig = await env.invite(a, g, "team", lid)
            return {"ask": send(a, g, lid), "ig": ig}
        await _pin_refusal(env, "already_invited", twice,
                           lambda c: Answer(409, {"error": "already_invited", "invite_id": str(c["ig"])}),
                           lambda c: _rw(env, pending_read))

        # design change (d): the sender must be a live member of the lobby
        async def outsider():
            lid, (_h,) = await env.lobby("team", 1)
            a = await env.player()
            return {"ask": send(a, await env.player(), lid), "a": a}
        await _pin_refusal(env, "not_in_lobby (not a member)", outsider, Answer(403, "not_in_lobby"),
                           lambda c: _patch(_invite_live_members=_add_member(c["a"].id)))

        async def stale_seat():
            lid, (_h, a) = await env.lobby("team", 2)
            await env.stale("team", a, lid)
            return {"ask": send(a, await env.player(), lid), "a": a}
        await _pin_refusal(env, "not_in_lobby (stale seat)", stale_seat, Answer(403, "not_in_lobby"),
                           lambda c: _patch(_invite_live_members=_add_member(c["a"].id)))
    case(monkeypatch, body)


async def _invited(env, n=1, invitee=None):
    """A team lobby of n members whose host invited `invitee` (a fresh player
    when None): (lid, members, invitee, invite id)."""
    lid, ps = await env.lobby("team", n)
    x = invitee or await env.player()
    return lid, ps, x, await env.invite(ps[0], x, "team", lid)


def _widen_invitee():
    """The invitee row read for any player: its invitee and copy-holder
    conditions made true for every caller."""
    return ((inv.placeholder_rx("i.invitee_player_id"), r"(i.invitee_player_id = \1 OR TRUE)", INVITEE_ROW),
            (inv.placeholder_rx("r.recipient_id"), r"(r.recipient_id = \1 OR TRUE)", INVITEE_ROW))


def test_every_accept_refusal_answers_as_section_4_2_says(monkeypatch):
    """invite_not_found (404) for another player's invite, a deleted copy and
    a suppressed one, each byte-identical to the answer for an unknown id;
    invite_expired (410); invite_void (409, with its end); invite_answered
    (409, with the final state); invite_id_invalid (400) for a malformed id;
    and the join's own refusals with the join's own status and detail (a full
    lobby, one no longer open, a kick), the last two ending the invite after
    the rollback and writing no receipt."""
    async def body(env):
        ref = await env.accept(await env.player(), uuid.uuid4())
        assert ref.wire == NOT_FOUND.wire, ref

        def accept(p, iid):
            return lambda: _safe(env.accept(p, iid))

        async def others():
            _lid, _ps, _x, j = await _invited(env)
            return {"ask": accept(await env.player(), j)}
        await _pin_refusal(env, "another player's invite", others, ref,
                           lambda c: _rw(env, *_widen_invitee()))

        async def deleted():
            _lid, _ps, x, j = await _invited(env)
            await _delete_copy(env, j, x)
            return {"ask": accept(x, j)}
        await _pin_refusal(env, "a deleted copy", deleted, ref,
                           lambda c: _rw(env, (" AND r.deleted_at IS NULL", "", INVITEE_ROW)))

        async def suppressed():
            _lid, _ps, x, j = await _invited(env, invitee=await env.player(mail_from="nobody"))
            assert await env.delivery(await env.mail_of(j), x) == "suppressed"
            return {"ask": accept(x, j)}
        await _pin_refusal(env, "a suppressed copy", suppressed, ref,
                           lambda c: _rw(env, ("r.delivery = 'delivered' AND ", "", INVITEE_ROW)))

        async def expired():
            _lid, _ps, x, j = await _invited(env)
            await env.age(j, expired_s=5)
            return {"ask": accept(x, j)}
        await _pin_refusal(env, "invite_expired", expired, Answer(410, "invite_expired"),
                           lambda c: _rw(env, ("(i.expires_at <= NOW()) AS past", "FALSE AS past", INVITEE_ROW),
                                         ("(expires_at <= NOW()) AS past", "FALSE AS past",
                                          "SELECT state, end_reason, (expires_at")))

        async def void():
            lid, ps, x, j = await _invited(env, 2)
            assert (await env.leave("team", ps[0], lid)).status == 200
            assert ((await env.row(j))["state"], (await env.row(j))["end_reason"]) == ("void", "sender_left")
            return {"ask": accept(x, j)}
        await _pin_refusal(env, "invite_void", void,
                           Answer(409, {"error": "invite_void", "end_reason": "sender_left"}),
                           lambda c: _patch(_invite_refuse_ended=_refuse_as(True)))

        async def answered():
            _lid, _ps, x, j = await _invited(env)
            assert (await env.decline(x, j)).status == 200
            return {"ask": accept(x, j)}
        await _pin_refusal(env, "invite_answered", answered,
                           Answer(409, {"error": "invite_answered", "state": "declined"}),
                           lambda c: _patch(_invite_refuse_ended=_no_state_check))

        async def malformed():
            _lid, _ps, x, _j = await _invited(env)
            return {"ask": accept(x, BAD_ID)}
        await _pin_refusal(env, "invite_id_invalid", malformed, Answer(400, "invite_id_invalid"),
                           lambda c: _patch(_invite_path_id=_any_path_id))

        # the join's own refusals, as a plain join answers them
        async def full():
            lid, _ps, x, j = await _invited(env, main._invite_capacity("team") - 1)
            late = await env.player()
            assert (await env.join("team", late, lid)).status == 200
            outsider = await env.player()
            return {"ask": accept(x, j), "iid": j, "late": late,
                    "same_as": lambda: env.join("team", outsider, lid)}
        real_members = main._lobby_live_members

        def without(pid):
            async def live(db, mode, lid):
                return [m for m in await real_members(db, mode, lid) if m["player_id"] != pid]
            return live
        await _pin_refusal(env, "the join's full lobby", full, Answer(409, "That lobby is full"),
                           lambda c: _patch(_lobby_live_members=without(c["late"].id)))

        async def gone():
            lid, _ps, x, j = await _invited(env)
            await _set_lobby_status(env, lid, "canceled")
            outsider = await env.player()
            return {"ask": accept(x, j), "iid": j, "same_as": lambda: env.join("team", outsider, lid)}
        await _pin_refusal(env, "the join's lobby no longer open", gone,
                           Answer(404, "That lobby is no longer open"),
                           lambda c: _rw(env, ("SELECT id, status, password_hash",
                                               "SELECT id, CAST('open' AS text) AS status, password_hash", None)),
                           ends="lobby_closed")

        async def kicked():
            lid, _ps, x, j = await _invited(env)
            await env.conn.execute("UPDATE team_lobbies SET kicked_steam_ids = $2 WHERE id = $1", lid, x.sid)
            return {"ask": accept(x, j), "iid": j, "same_as": lambda: env.join("team", x, lid)}
        await _pin_refusal(env, "the join's kick", kicked, Answer(403, "kicked_from_lobby"),
                           lambda c: _rw(env, ("password_hash, kicked_steam_ids,",
                                               "password_hash, NULL AS kicked_steam_ids,", None)),
                           ends="invitee_kicked")
    case(monkeypatch, body)


def test_every_decline_refusal_answers_as_section_4_2_says(monkeypatch):
    """invite_not_found (404) for another player's invite, a deleted copy and
    a suppressed one, byte-identical to the unknown id's; invite_expired
    (410); invite_answered (409, with the final state, a void one among
    them); invite_id_invalid (400)."""
    async def body(env):
        ref = await env.decline(await env.player(), uuid.uuid4())
        assert ref.wire == NOT_FOUND.wire, ref

        def decline(p, iid):
            return lambda: _safe(env.decline(p, iid))

        async def others():
            _lid, _ps, _x, j = await _invited(env)
            return {"ask": decline(await env.player(), j)}
        await _pin_refusal(env, "another player's invite", others, ref,
                           lambda c: _rw(env, *_widen_invitee()))

        async def deleted():
            _lid, _ps, x, j = await _invited(env)
            await _delete_copy(env, j, x)
            return {"ask": decline(x, j)}
        await _pin_refusal(env, "a deleted copy", deleted, ref,
                           lambda c: _rw(env, (" AND r.deleted_at IS NULL", "", INVITEE_ROW)))

        async def suppressed():
            _lid, _ps, x, j = await _invited(env, invitee=await env.player(mail_from="nobody"))
            return {"ask": decline(x, j)}
        await _pin_refusal(env, "a suppressed copy", suppressed, ref,
                           lambda c: _rw(env, ("r.delivery = 'delivered' AND ", "", INVITEE_ROW)))

        async def expired():
            _lid, _ps, x, j = await _invited(env)
            await env.age(j, expired_s=5)
            return {"ask": decline(x, j)}
        await _pin_refusal(env, "invite_expired", expired, Answer(410, "invite_expired"),
                           lambda c: _rw(env, ("(i.expires_at <= NOW()) AS past", "FALSE AS past", INVITEE_ROW)))

        async def cancelled():
            _lid, ps, x, j = await _invited(env)
            assert (await env.cancel(ps[0], j)).status == 200
            return {"ask": decline(x, j)}
        await _pin_refusal(env, "invite_answered", cancelled,
                           Answer(409, {"error": "invite_answered", "state": "cancelled"}),
                           lambda c: _patch(_invite_refuse_ended=_no_state_check))

        async def void():
            lid, ps, x, j = await _invited(env, 2)
            assert (await env.leave("team", ps[0], lid)).status == 200
            assert (await env.row(j))["state"] == "void"
            return {"ask": decline(x, j)}
        await _pin_refusal(env, "a void invite, answered", void,
                           Answer(409, {"error": "invite_answered", "state": "void"}),
                           lambda c: _patch(_invite_refuse_ended=_refuse_as(False)))

        async def malformed():
            _lid, _ps, x, _j = await _invited(env)
            return {"ask": decline(x, BAD_ID)}
        await _pin_refusal(env, "invite_id_invalid", malformed, Answer(400, "invite_id_invalid"),
                           lambda c: _patch(_invite_path_id=_any_path_id))
    case(monkeypatch, body)


def test_every_cancel_refusal_answers_as_section_4_2_says(monkeypatch):
    """invite_not_found (404) for a caller who is neither the invite's sender
    nor the lobby's host (a member, an outsider), byte-identical to the
    unknown id's; invite_expired (410); invite_answered (409, with the final
    state); invite_id_invalid (400). Control: the host cancels a member's
    invite."""
    async def body(env):
        ref = await env.cancel(await env.player(), uuid.uuid4())
        assert ref.wire == NOT_FOUND.wire, ref

        def cancel(p, iid):
            return lambda: _safe(env.cancel(p, iid))

        def host_is(pid):
            return lambda mode, host, live: pid

        async def member():
            _lid, ps, _x, i = await _invited(env, 2)
            return {"ask": cancel(ps[1], i), "who": ps[1]}
        await _pin_refusal(env, "a member who is neither", member, ref,
                           lambda c: _patch(_invite_effective_host=host_is(c["who"].id)))

        async def outsider():
            _lid, _ps, _x, i = await _invited(env, 1)
            o = await env.player()
            return {"ask": cancel(o, i), "who": o}
        await _pin_refusal(env, "an outsider", outsider, ref,
                           lambda c: _patch(_invite_effective_host=host_is(c["who"].id)))

        async def expired():
            _lid, ps, _x, i = await _invited(env)
            await env.age(i, expired_s=5)
            return {"ask": cancel(ps[0], i)}
        await _pin_refusal(env, "invite_expired", expired, Answer(410, "invite_expired"),
                           lambda c: _rw(env, ("(expires_at <= NOW()) AS past", "FALSE AS past",
                                               "SELECT id, sender_player_id, state")))

        async def declined():
            _lid, ps, x, i = await _invited(env)
            assert (await env.decline(x, i)).status == 200
            return {"ask": cancel(ps[0], i)}
        await _pin_refusal(env, "invite_answered", declined,
                           Answer(409, {"error": "invite_answered", "state": "declined"}),
                           lambda c: _patch(_invite_refuse_ended=_no_state_check))

        async def malformed():
            _lid, ps, _x, _i = await _invited(env)
            return {"ask": cancel(ps[0], BAD_ID)}
        await _pin_refusal(env, "invite_id_invalid", malformed, Answer(400, "invite_id_invalid"),
                           lambda c: _patch(_invite_path_id=_any_path_id))

        # control: the lobby's host cancels an invite a member sent
        lid, (h, b) = await env.lobby("team", 2)
        i = await env.invite(b, await env.player(), "team", lid)
        got = await env.cancel(h, i)
        assert got.wire == Answer(200, {"state": "cancelled"}).wire, got
        assert (await env.row(i))["state"] == "cancelled"
    case(monkeypatch, body)
