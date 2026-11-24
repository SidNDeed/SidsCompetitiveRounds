"""BAN-RECORD-1 R7, the tournament part (ruling Q3, bar V10): the ban read of
tournaments.py, `_player_id_banned`, and its seven callers.

The helper is handed a player id that its caller read in an earlier
statement. The account deletion rewrites the players row in place (steam_id
`deleted_<hex>`, deleted_at set, one commit; _tombstone mirrors it from the
deletion's source) and leaves the account's tournament signups where they
are. The helper now reads, in ONE statement by that id, the row's deletion
mark beside the ban word of the steam id the same row carries, and answers
one of three words: "" (may go on), "banned" (an active ban) or "removed"
(the mark stands, whatever ban stands or stood under the former id). A
caller goes on only on "".

On PostgreSQL (a case schema of inv_pg, CF_TEST_PG_DSN; the data invented):
  - the helper's five cases: (a) a removed row without a ban, (b) a removed
    row with an active ban under its former steam id, (c) a live row under an
    active ban, (d) a live row without one, and an id with no row (and None);
  - each of the seven callers once with the helper's answer handed in by a
    spy that records the id it was asked about: "removed" takes the caller
    its refused or left-out way with the ruling's words (signup and
    force_vote: 404 "Player not found"; the check-in and forfeit_match: their
    closed answers; the activation, the overdue sweep and the leaving
    handler: the seat forfeited or the candidate passed over), and "banned"
    reads as at the base;
  - the three scans end to end with no spy: a signup whose account was
    removed beforehand in the deletion's own shape.
The mutant (the mark's arm dropped from the helper's statement, run on a copy
of the tree) turns (a), (b) and the three end-to-end cases red;
test_the_helper_statement_reached_the_database is its reached proof and
prints the statement as sent.
"""
import contextlib
import io
import os
import sys
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import event, select  # noqa: E402

import main  # noqa: E402,F401  (inv_pg's Env patches main's seams)
import tournaments  # noqa: E402
from models import TournamentMatch  # noqa: E402
from schemas import (TournamentForceVoteRequest, TournamentReadyRequest,  # noqa: E402
                     TournamentSignupRequest)

KEY_SQL = "SELECT pg_advisory_xact_lock(hashtext($1))"
BAN_SQL = ("INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
           " VALUES ($1, 'r7t', $2, NOW() - INTERVAL '1 hour', NOW() + INTERVAL '1 day')")
HELPER_CASES = ("a", "b", "c", "d", "none")
WORDS = ("removed", "banned")
CALLERS = ("signup", "force_vote", "handle_tournament_checkin_response", "forfeit_match",
           "_activate_ready_matches", "_resolve_overdue_match", "_handle_leaving_signup")
SCANS = ("_activate_ready_matches", "_resolve_overdue_match", "_handle_leaving_signup")


# -- seeding ---------------------------------------------------------------

async def _tournament(env, status, kind="async"):
    # one active tournament per kind (uniq_tournaments_active_per_kind): the
    # previous scenario's is closed first
    await env.conn.execute(
        "UPDATE tournaments SET status = 'completed' WHERE kind = $1"
        " AND status IN ('voting', 'locked', 'running')", kind)
    tid = uuid.uuid4()
    await env.conn.execute(
        "INSERT INTO tournaments (id, kind, status, default_start_ts, lock_at)"
        " VALUES ($1, $2, $3, NOW(), NOW())", tid, kind, status)
    return tid


async def _signup(env, tid, p, speculative=False):
    sid = uuid.uuid4()
    await env.conn.execute(
        "INSERT INTO tournament_signups (id, tournament_id, player_id, is_speculative)"
        " VALUES ($1, $2, $3, $4)", sid, tid, p.id, speculative)
    return sid


async def _match(env, tid, s1, s2, status):
    mid = uuid.uuid4()
    await env.conn.execute(
        "INSERT INTO tournament_matches (id, tournament_id, round, bracket_side, slot_idx,"
        " p1_signup_id, p2_signup_id, status, ready_deadline_at,"
        " prereq_match_ids, prereq_roles, early_ok_signup_ids, is_bye)"
        " VALUES ($1, $2, 1, 'W', 0, $3, $4, $5, NOW() - INTERVAL '1 hour',"
        " '{}', '{}', '{}', FALSE)",
        mid, tid, s1, s2, status)
    return mid


async def _remove(env, p):
    """P's account removed in the deletion's own shape, under its identity
    key as the deletion holds it, committed before the caller runs."""
    from test_mdpl_gate_reread_pg import _tombstone
    side = await env.side()
    await side.execute("BEGIN")
    await side.execute(KEY_SQL, p.sid)
    await _tombstone(side, p)
    await side.execute("COMMIT")


async def _ban(env, p, admin):
    await env.conn.execute(BAN_SQL, p.sid, admin)


# -- calling ---------------------------------------------------------------

async def _call(env, fn):
    """fn(db) in its own session, committed; an HTTP refusal is its answer.
    Anything printed meanwhile is kept."""
    out = io.StringIO()
    async with env.sm() as db:
        with contextlib.redirect_stdout(out):
            try:
                got = ("ok", await fn(db))
                await db.commit()
            except HTTPException as e:
                await db.rollback()
                got = ("http", e.status_code, e.detail)
    return got, out.getvalue()


@contextlib.contextmanager
def _spy(words):
    """_player_id_banned replaced: records the id it is asked about and
    answers the word `words` holds for it ("" for any other)."""
    asked = []

    async def spy(db, player_id):
        asked.append(str(player_id))
        return words.get(str(player_id), "")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(tournaments, "_player_id_banned", spy)
        yield asked


async def _match_state(env, mid, sigs):
    m = await env.conn.fetchrow(
        "SELECT status, winner_signup_id, p1_signup_id, p2_signup_id FROM tournament_matches"
        " WHERE id = $1", mid)
    names = {v: k for k, v in sigs.items()}
    seat = (lambda s: names.get(s, "other") if s is not None else None)
    forfeited = {k: await env.conn.fetchval(
        "SELECT forfeited FROM tournament_signups WHERE id = $1", v) for k, v in sigs.items()}
    return {"status": m["status"], "winner": seat(m["winner_signup_id"]),
            "p1": seat(m["p1_signup_id"]), "p2": seat(m["p2_signup_id"]), "forfeited": forfeited}


# -- the callers, each driven to its ban read ----------------------------------

async def _route_signup(env, words_for):
    p = await env.player()
    tid = await _tournament(env, "voting")
    with _spy(words_for(p)) as asked:
        got, _ = await _call(env, lambda db: tournaments.signup(
            tid, TournamentSignupRequest(steam_id=p.sid), SimpleNamespace(headers={}), db))
    rows = await env.conn.fetchval("SELECT count(*) FROM tournament_signups WHERE tournament_id = $1", tid)
    return {"answer": got, "asked": asked == [str(p.id)], "rows": rows}


async def _route_force_vote(env, words_for):
    p = await env.player()
    tid = await _tournament(env, "voting")
    await _signup(env, tid, p)
    with _spy(words_for(p)) as asked:
        got, _ = await _call(env, lambda db: tournaments.force_vote(
            tid, TournamentForceVoteRequest(steam_id=p.sid), SimpleNamespace(headers={}), db))
    rows = await env.conn.fetchval(
        "SELECT count(*) FROM tournament_force_votes WHERE tournament_id = $1", tid)
    return {"answer": got, "asked": asked == [str(p.id)], "rows": rows}


async def _ready_match(env, kind="async"):
    p, q = await env.player(), await env.player()
    tid = await _tournament(env, "running", kind)
    s1, s2 = await _signup(env, tid, p), await _signup(env, tid, q)
    mid = await _match(env, tid, s1, s2, "ready")
    return p, q, tid, mid, {"p": s1, "q": s2}


async def _route_checkin(env, words_for):
    p, q, tid, mid, sigs = await _ready_match(env)
    with _spy(words_for(p)) as asked:
        got, _ = await _call(env, lambda db: tournaments.handle_tournament_checkin_response(
            db, mid, p.sid, "yes"))
    rows = await env.conn.fetchval("SELECT count(*) FROM tournament_match_checkins WHERE match_id = $1", mid)
    return {"answer": got, "asked": asked == [str(p.id)], "rows": rows,
            "match": await _match_state(env, mid, sigs)}


async def _route_forfeit(env, words_for):
    p, q, tid, mid, sigs = await _ready_match(env)
    with _spy(words_for(p)) as asked:
        got, _ = await _call(env, lambda db: tournaments.forfeit_match(
            tid, mid, TournamentReadyRequest(steam_id=p.sid), SimpleNamespace(headers={}), db))
    rows = await env.conn.fetchval("SELECT count(*) FROM tournament_match_checkins WHERE match_id = $1", mid)
    return {"answer": got, "asked": asked == [str(p.id)], "rows": rows,
            "match": await _match_state(env, mid, sigs)}


async def _scan_activation(env, words_for=None, removed=False):
    p, q = await env.player(), await env.player()
    tid = await _tournament(env, "running")
    s1, s2 = await _signup(env, tid, p), await _signup(env, tid, q)
    mid = await _match(env, tid, s1, s2, "pending")
    if removed:
        await _remove(env, p)
    spy = _spy(words_for(p)) if words_for else contextlib.nullcontext([])
    with spy as asked:
        got, printed = await _call(env, lambda db: tournaments._activate_ready_matches(db, tid))
    lines = [ln for ln in printed.splitlines() if "activation:" in ln]
    return {"answer": got[0], "asked": asked == [str(p.id), str(q.id)] if words_for else None,
            "log": [ln.replace(str(s1), "<p>") for ln in lines],
            "match": await _match_state(env, mid, {"p": s1, "q": s2})}


async def _scan_sweep(env, words_for=None, removed=False, players=None):
    p, q = players or (await env.player(), await env.player())
    tid = await _tournament(env, "running")
    s1, s2 = await _signup(env, tid, p), await _signup(env, tid, q)
    mid = await _match(env, tid, s1, s2, "ready")
    if removed:
        await _remove(env, p)

    async def sweep(db):
        m = (await db.execute(select(TournamentMatch).where(TournamentMatch.id == mid)
                              .with_for_update())).scalar_one()
        await tournaments._resolve_overdue_match(db, m, datetime.now(timezone.utc))
    spy = _spy(words_for(p, q)) if words_for else contextlib.nullcontext([])
    with spy as asked:
        got, _ = await _call(env, sweep)
    return {"answer": got[0], "asked": asked == [str(p.id), str(q.id)] if words_for else None,
            "match": await _match_state(env, mid, {"p": s1, "q": s2})}


async def _scan_leaving(env, words_for=None, removed=False):
    leaver, opp, cand = await env.player(), await env.player(), await env.player()
    tid = await _tournament(env, "locked")
    sl, so = await _signup(env, tid, leaver), await _signup(env, tid, opp)
    sc = await _signup(env, tid, cand, speculative=True)
    mid = await _match(env, tid, sl, so, "pending")
    if removed:
        await _remove(env, cand)
    spy = _spy(words_for(cand)) if words_for else contextlib.nullcontext([])
    with spy as asked:
        got, _ = await _call(env, lambda db: tournaments._handle_leaving_signup(db, tid, sl))
    c = await env.conn.fetchrow("SELECT is_speculative, seed FROM tournament_signups WHERE id = $1", sc)
    return {"answer": got[0], "asked": asked == [str(cand.id)] if words_for else None,
            "candidate": (c["is_speculative"], c["seed"]),
            "match": await _match_state(env, mid, {"leaver": sl, "opp": so, "cand": sc})}


ROUTES = {
    "signup": _route_signup, "force_vote": _route_force_vote,
    "handle_tournament_checkin_response": _route_checkin, "forfeit_match": _route_forfeit,
    "_activate_ready_matches": lambda env, w: _scan_activation(env, w),
    "_resolve_overdue_match": lambda env, w: _scan_sweep(env, lambda p, q: w(p)),
    "_handle_leaving_signup": lambda env, w: _scan_leaving(env, w),
}
E2E = {
    "_activate_ready_matches": lambda env: _scan_activation(env, removed=True),
    "_resolve_overdue_match": lambda env: _scan_sweep(env, removed=True),
    "_handle_leaving_signup": lambda env: _scan_leaving(env, removed=True),
}


async def _guard(coro):
    try:
        return await coro
    except Exception as e:   # recorded, so each test names its own failure
        return {"error": "%s: %s" % (type(e).__name__, str(e)[:400])}


@pytest.fixture(scope="module")
def got():
    from inv_pg import case
    out = {"helper": {}, "spy": {}, "e2e": {}, "statements": []}

    def seen(conn, cursor, statement, parameters, context, executemany):
        if " AS removed" in statement and "player_bans" in statement:
            out["statements"].append(statement)

    async def body(env):
        event.listen(env.engine.sync_engine, "before_cursor_execute", seen)
        try:
            admin = (await env.player("R7T Admin")).sid
            await env.conn.execute("INSERT INTO admin_users (steam_id) VALUES ($1)", admin)
            kept = {}
            for step in "abcd":
                p = await env.player("R7T Row %s" % step.upper())
                if step in "ab":
                    await _remove(env, p)
                if step in "bc":
                    await _ban(env, p, admin)
                kept[step] = p.id
            kept["none"] = uuid.uuid4()
            out["rows"] = {s: dict(await env.conn.fetchrow(
                "SELECT steam_id, deleted_at IS NOT NULL AS removed FROM players WHERE id = $1", pid) or {})
                for s, pid in kept.items()}
            for step, pid in kept.items():
                async with env.sm() as db:
                    out["helper"][step] = await _guard(tournaments._player_id_banned(db, pid))
                    await db.rollback()
            async with env.sm() as db:
                out["helper"]["None"] = await _guard(tournaments._player_id_banned(db, None))
                await db.rollback()

            for name, fn in ROUTES.items():
                for word in WORDS:
                    out["spy"][(name, word)] = await _guard(fn(env, lambda p, w=word: {str(p.id): w}))
            # the sweep with one seat banned and the other removed: both refused
            pair = []
            for words in (("banned", "removed"), ("banned", "banned")):
                p, q = await env.player(), await env.player()
                pair.append(await _guard(_scan_sweep(
                    env, lambda a, b, w=words: {str(a.id): w[0], str(b.id): w[1]}, players=(p, q))))
            out["spy"]["sweep pair"] = pair

            for name, fn in E2E.items():
                out["e2e"][name] = await _guard(fn(env))
        finally:
            event.remove(env.engine.sync_engine, "before_cursor_execute", seen)

    with pytest.MonkeyPatch.context() as mp:
        case(mp, body, prefix="r7t")
    for k, v in out["helper"].items():
        print("[R7T] helper %-5s %r" % (k, v))
    for k, v in list(out["spy"].items()) + list(out["e2e"].items()):
        print("[R7T] %r %r" % (k, v))
    return out


def test_the_rows_are_as_the_steps_say(got):
    rows = got["rows"]
    assert rows["a"]["removed"] and rows["b"]["removed"], rows
    assert rows["a"]["steam_id"].startswith("deleted_") and rows["b"]["steam_id"].startswith("deleted_"), rows
    assert not rows["c"]["removed"] and not rows["d"]["removed"] and rows["none"] == {}, rows


HELPER_WANT = {"a": "removed", "b": "removed", "c": "banned", "d": "", "none": ""}


@pytest.mark.parametrize("step", HELPER_CASES)
def test_the_helper_answers_each_case_from_one_statement(got, step):
    # the message carries the statement as sent: a mutant's red line shows the text it changed
    assert got["helper"][step] == HELPER_WANT[step], (step, got["helper"][step], got["statements"][:1])
    if step == "none":
        assert got["helper"]["None"] == "", got["helper"]["None"]


def test_the_helper_statement_reached_the_database(got):
    """The mutant's reached proof: the helper's one statement was sent for
    each real call with an id (the five cases) and for each seat the three
    end-to-end scans ask about (2 + 2 + 1); printed as sent, so a mutant
    run shows the statement it changed."""
    sent = got["statements"]
    print("[R7T] helper statements sent: %d; the first: %s" % (len(sent), sent[0] if sent else None))
    assert len(sent) == 5 + 2 + 2 + 1, len(sent)


def _refused(status, detail):
    return ("http", status, detail)


CLOSED = {"ok": True, "result": "match_closed", "new_deadline_epoch": None}


@pytest.mark.parametrize("caller", CALLERS)
def test_each_caller_asks_about_its_row_and_goes_the_words_way(got, caller):
    removed, banned = got["spy"][(caller, "removed")], got["spy"][(caller, "banned")]
    assert "error" not in removed and "error" not in banned, (removed, banned)
    assert removed["asked"] is True and banned["asked"] is True, (removed, banned)
    if caller == "signup":
        assert removed["answer"] == _refused(404, "Player not found") and removed["rows"] == 0, removed
        assert banned["answer"] == _refused(409, "Banned players cannot sign up") and banned["rows"] == 0, banned
    elif caller == "force_vote":
        assert removed["answer"] == _refused(404, "Player not found") and removed["rows"] == 0, removed
        assert banned["answer"] == _refused(409, "Banned players cannot vote") and banned["rows"] == 0, banned
    elif caller == "handle_tournament_checkin_response":
        for r in (removed, banned):
            assert r["answer"] == ("ok", CLOSED) and r["rows"] == 0, r
            assert r["match"]["status"] == "ready", r
    elif caller == "forfeit_match":
        for r in (removed, banned):
            assert r["answer"] == _refused(409, "Tournament match is closed") and r["rows"] == 0, r
            assert r["match"]["status"] == "ready", r
    elif caller == "_activate_ready_matches":
        for word, r in (("removed", removed), ("banned", banned)):
            assert r["answer"] == "ok", r
            assert r["match"]["status"] == "forfeit" and r["match"]["winner"] == "q", r
            assert r["match"]["forfeited"] == {"p": True, "q": False}, r
            assert r["log"] == ["[TOURNAMENT] activation: %s signup <p> forfeited" % word], r
    elif caller == "_resolve_overdue_match":
        for r in (removed, banned):
            assert r["answer"] == "ok", r
            assert r["match"]["status"] == "forfeit" and r["match"]["winner"] == "q", r
            assert r["match"]["forfeited"] == {"p": True, "q": False}, r
        # one seat banned, the other removed: both refused, the both-banned branch
        # (double_forfeit), never the one-refused forfeit. The double forfeit's
        # carrier seat is a tie-break between two random signup ids, so the
        # winner is left out of the comparison.
        mixed, both = got["spy"]["sweep pair"]
        assert "error" not in mixed and "error" not in both, (mixed, both)
        assert mixed["match"]["status"] == both["match"]["status"] == "double_forfeit", (mixed, both)
        drop = (lambda m: {k: v for k, v in m.items() if k != "winner"})
        assert drop(mixed["match"]) == drop(both["match"]), (mixed, both)
    elif caller == "_handle_leaving_signup":
        for r in (removed, banned):
            assert r["answer"] == "ok", r
            assert r["candidate"] == (True, None), r
            assert r["match"]["status"] == "bye_auto" and r["match"]["winner"] == "opp", r
            assert r["match"]["p1"] is None and r["match"]["p2"] == "opp", r


@pytest.mark.parametrize("scan", SCANS)
def test_a_signup_of_a_removed_account_is_left_out_end_to_end(got, scan):
    r = got["e2e"][scan]
    assert "error" not in r and r["answer"] == "ok", r
    if scan == "_activate_ready_matches":
        assert r["match"]["status"] == "forfeit" and r["match"]["winner"] == "q", r
        assert r["match"]["forfeited"] == {"p": True, "q": False}, r
        assert r["log"] == ["[TOURNAMENT] activation: removed signup <p> forfeited"], r
    elif scan == "_resolve_overdue_match":
        assert r["match"]["status"] == "forfeit" and r["match"]["winner"] == "q", r
        assert r["match"]["forfeited"] == {"p": True, "q": False}, r
    else:
        assert r["candidate"] == (True, None), r
        assert r["match"]["status"] == "bye_auto" and r["match"]["winner"] == "opp", r
