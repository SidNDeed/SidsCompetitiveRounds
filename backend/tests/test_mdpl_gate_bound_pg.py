"""MDPL-GATE-REREAD-1 F1 (round mdplg-r1, finding 1): the four routes of part
(b) take their player's identity key SHARED only through
main._identity_key_shared_bounded, which waits at most
main.SHARED_IDENTITY_KEY_TIMEOUT_MS and answers 503 "identity_busy" past it.

  route                      the key's id
  toggle_ranked              the path's steam_id
  unlock_achievement         req.steam_id
  admin_grant_achievement    req.target_steam_id
  generate_link_code         the query's steam_id

On PostgreSQL through inv_pg, with test_mdpl_gate_reread_b_pg.py's scenes
(SCENES: the seeds, the calls and the answer each route gives without a
deletion) and its _scene for the control.

A bound row, per route: the row sets the constant small (SMALL_MS); a second
session H holds P's identity key EXCLUSIVE in an open transaction for the
whole call. Then, in this order: the route answers (503, "identity_busy")
inside the bound plus MARGIN_S, and not before the bound; it printed ONE
"[LOCK]" line, which names neither P's raw id nor P's id; every table of the
case schema counts the same rows as before the call, and P's row is the
same in every column; and once H has ended, another session takes P's key
EXCLUSIVE at once (pg_try_advisory_xact_lock), so the refused request left
nothing holding it.

The control: H holds P's key and ends inside the bound (_scene: it commits as
soon as the route waits on it). Each route answers as it does at c697dc6d,
having waited at the shared key, and lock_timeout reads after the helper what
it read in the same session before it.

The census row (no database): each of the four function bodies holds ONE
call of the helper and NO string naming pg_advisory, and the helper holds
the key statement letter for letter.

The real session check: inv_pg puts a stand-in for main._check_steam_session
in every case. One row each for toggle_ranked and unlock_achievement, whose
key comes before that check, puts the real check back, plants a verified
steam_sessions row for P and sends its token: the route waits at the key
while H holds it, then answers as before, and the real check marked the
request verified.

The product mutants of F1 (the arming, the handler and the disarming taken
out of the helper; one route written with its inline key statement again)
were run on copies of the tree and are not part of this file.
"""

import ast
import asyncio
import hashlib
import inspect
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

from sqlalchemy import text  # noqa: E402

from inv_pg import Req, case  # noqa: E402

import main  # noqa: E402
import schemas  # noqa: E402
from test_mail_case_scrub_pg import BOUND  # noqa: E402
from test_mdpl_gate_reread_b_pg import (  # noqa: E402
    SCENES, UNLOCK_KEY, Scene, _scene, _seams, _sig)
from test_mdpl_gate_reread_pg import KEY_SQL, NOT_FOUND, _row  # noqa: E402

ROUTES = ("toggle_ranked", "unlock_achievement", "admin_grant_achievement", "generate_link_code")
HELPER = "_identity_key_shared_bounded"
KEY_STATEMENT = "SELECT pg_advisory_xact_lock_shared(hashtext(CAST(:sid AS text)))"
BUSY = (503, "identity_busy")
SMALL_MS = 300
MARGIN_S = 5.0
TOKEN = "mdpl-bound-session-token"
# Taken at import, before any case puts inv_pg's stand-in in its place.
_REAL_CHECK = main._check_steam_session


async def _counts(conn):
    """Every base table of the case schema and its row count."""
    names = await conn.fetch(
        "SELECT table_name FROM information_schema.tables"
        " WHERE table_schema = current_schema() AND table_type = 'BASE TABLE' ORDER BY table_name")
    return {r["table_name"]: await conn.fetchval('SELECT count(*) FROM "%s"' % r["table_name"]) for r in names}


def _bound_case(monkeypatch, capsys, tmp_path, route):
    """The route's bound row, the four assertions of the module docstring in
    its order."""
    async def body(env):
        _seams(env, tmp_path)
        env.mp.setattr(main, "SHARED_IDENTITY_KEY_TIMEOUT_MS", SMALL_MS, raising=False)
        s = await SCENES[route](env)
        rows = await _counts(env.conn)
        left = await _row(env.conn, s.p)
        side = await env.side()
        await side.execute("BEGIN")
        await side.execute(KEY_SQL, s.p.sid)
        capsys.readouterr()
        try:
            t0 = time.monotonic()
            ans = await asyncio.wait_for(env.call(s.call), SMALL_MS / 1000.0 + MARGIN_S)
            took = time.monotonic() - t0
        finally:
            await side.execute("ROLLBACK")
        out = capsys.readouterr().out
        assert (ans.status, ans.body) == BUSY, ("answer", route, ans)
        assert took >= 0.9 * SMALL_MS / 1000.0, ("answered before the bound", route, took)
        lines = [ln for ln in out.splitlines() if ln.startswith("[LOCK]")]
        assert len(lines) == 1 and s.p.sid not in lines[0] and str(s.p.id) not in lines[0], (
            "the line", route, lines)
        now = await _counts(env.conn)
        assert now == rows, ("row counts", route, {k: (rows.get(k), now.get(k)) for k in set(rows) | set(now)
                                                    if rows.get(k) != now.get(k)})
        assert await _row(env.conn, s.p) == left, ("P's row", route)
        free = await env.side()
        await free.execute("BEGIN")
        got = await free.fetchval("SELECT pg_try_advisory_xact_lock(hashtext($1))", s.p.sid)
        await free.execute("ROLLBACK")
        assert got is True, ("P's key after the holder ended", route)
    case(monkeypatch, body, prefix="mdplbd")


def test_toggle_ranked_answers_503_inside_the_bound_while_the_key_is_held(monkeypatch, capsys, tmp_path):
    _bound_case(monkeypatch, capsys, tmp_path, "toggle_ranked")


def test_unlock_achievement_answers_503_inside_the_bound_while_the_key_is_held(monkeypatch, capsys, tmp_path):
    _bound_case(monkeypatch, capsys, tmp_path, "unlock_achievement")


def test_admin_grant_achievement_answers_503_inside_the_bound_while_the_key_is_held(monkeypatch, capsys,
                                                                                    tmp_path):
    _bound_case(monkeypatch, capsys, tmp_path, "admin_grant_achievement")


def test_generate_link_code_answers_503_inside_the_bound_while_the_key_is_held(monkeypatch, capsys, tmp_path):
    _bound_case(monkeypatch, capsys, tmp_path, "generate_link_code")


def test_control_the_holder_ends_inside_the_bound_and_lock_timeout_reads_its_default(monkeypatch, tmp_path):
    """Every scene of the four, H holding P's key and committing nothing as
    soon as the route waits: each route answers as before, having waited at
    the shared key, and the helper left lock_timeout as the session had it."""
    async def body(env):
        _seams(env, tmp_path)
        seen = []
        real = main._identity_key_shared_bounded

        async def helper(db, steam_id):
            before = (await db.execute(text("SHOW lock_timeout"))).scalar()
            await real(db, steam_id)
            after = (await db.execute(text("SHOW lock_timeout"))).scalar()
            seen.append((steam_id, before, after))
        env.mp.setattr(main, HELPER, helper)
        for route, build in SCENES.items():
            s = await build(env)
            del seen[:]
            ans, waited, _left, _named = await _scene(env, s, delete=False)
            assert ans.status == 200 and s.ok(ans.body), ("control", route, ans)
            assert "pg_advisory_xact_lock_shared" in waited, ("the wait", route, waited)
            assert len(seen) == 1 and seen[0][0] == s.p.sid and seen[0][2] == seen[0][1], (
                "lock_timeout after the helper", route, seen)
    case(monkeypatch, body, prefix="mdplbd")


def test_census_the_four_routes_take_the_key_only_through_the_helper():
    """Each of the four function bodies: ONE call of the helper, NO string
    naming pg_advisory. The helper: the key statement letter for letter."""
    with open(inspect.getsourcefile(main), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    fns = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    got = {}
    for name in ROUTES:
        fn = fns[name]
        calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
                 and ((isinstance(c.func, ast.Name) and c.func.id == HELPER)
                      or (isinstance(c.func, ast.Attribute) and c.func.attr == HELPER))]
        named = [c.value for c in ast.walk(fn) if isinstance(c, ast.Constant) and isinstance(c.value, str)
                 and "pg_advisory" in c.value]
        got[name] = (len(calls), named)
    assert got == {name: (1, []) for name in ROUTES}, got
    strings = [c.value for c in ast.walk(fns[HELPER]) if isinstance(c, ast.Constant) and isinstance(c.value, str)]
    assert KEY_STATEMENT in strings, strings


class _TokenReq(Req):
    """inv_pg's Req carrying a session token, for the real session check."""

    def __init__(self, sid):
        super().__init__(sid)
        self.headers = {"X-Session-Token": TOKEN}


def _toggle_real(p, request):
    name = "Reread toggle P renamed"
    sig = _sig("toggle-ranked:%s:true" % p.sid)
    name_sig = _sig("toggle-ranked-name:%s:%s" % (p.sid, name))
    return lambda db: main.toggle_ranked(steam_id=p.sid, request=request, enabled=True, sig=sig,
                                         display_name=name, name_sig=name_sig, db=db)


def _unlock_real(p, request):
    req = schemas.AchievementUnlockRequest(
        steam_id=p.sid, achievement_key=UNLOCK_KEY,
        hmac_signature=_sig("achievement:%s:%s" % (p.sid, UNLOCK_KEY)))
    return lambda db: main.unlock_achievement(req=req, request=request, db=db)


def _real_check_case(monkeypatch, tmp_path, route, make_call):
    async def body(env):
        _seams(env, tmp_path)
        env.mp.setattr(main, "_check_steam_session", _REAL_CHECK)
        assert getattr(_REAL_CHECK, "__module__", None) == "main" and _REAL_CHECK.__name__ == "_check_steam_session"
        s = await SCENES[route](env)
        await env.conn.execute(
            "INSERT INTO steam_sessions (steam_id, token_hash, verified, issued_at, expires_at)"
            " VALUES ($1, $2, TRUE, NOW(), NOW() + interval '1 day')",
            s.p.sid, hashlib.sha256(TOKEN.encode()).hexdigest())
        request = _TokenReq(s.p.sid)
        real = Scene(route, s.p, make_call(s.p, request), NOT_FOUND, s.ok)
        ans, waited, _left, _named = await asyncio.wait_for(_scene(env, real, delete=False), BOUND)
        assert ans.status == 200 and real.ok(ans.body), ("answer", route, ans)
        assert "pg_advisory_xact_lock_shared" in waited, ("the wait", route, waited)
        assert getattr(request.state, "scr_session_verified", None) is True, ("the real session check", route)
    case(monkeypatch, body, prefix="mdplbd")


def test_toggle_ranked_with_the_real_session_check_answers_as_before(monkeypatch, tmp_path):
    _real_check_case(monkeypatch, tmp_path, "toggle_ranked", _toggle_real)


def test_unlock_achievement_with_the_real_session_check_answers_as_before(monkeypatch, tmp_path):
    _real_check_case(monkeypatch, tmp_path, "unlock_achievement", _unlock_real)
