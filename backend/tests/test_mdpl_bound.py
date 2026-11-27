"""MDPL, the account deletion's bound (R6, R6a) and the bet helpers' flag
(R6b), checked without a database.

- C1: the arrival stamp is read BEFORE the wait for a writer slot, so the
  deadline counts that wait. Shown through the framework itself (the order in
  which a signature's sibling dependencies are solved is the framework's), on
  the registered route object; the negative control is the same endpoint with
  the stamp declared after the slot, which reads it after the slot is free.
- R6a: an attempt that cannot fit in the time left is not started; attempts
  ended as deadlock victims run again only while one still fits, and the
  route then refuses with 503 account_cleanup_contended.
- R6b: the four bet helpers keep their present behaviour by default; only the
  deletion passes raise_retryable=True.
- r1 HIGH: inside a deletion attempt a bet party's identity is taken
  without a wait (_deletion_lock_party_row): its players row SKIP LOCKED,
  then its identity key in the try form, exclusive; and each FFA bet row
  before its claim (_deletion_lock_ffa_bet), SKIP LOCKED. A held row or key
  ends the attempt (_DeletionRowHeld), which every helper catch hands back
  whatever its flag, and the bound runs it again after a pause while one
  still fits: at most 13 attempts when the row stays held. Outside an
  attempt neither guard runs a statement. The census: every players
  statement the deletion reaches is pinned, by function and player, as the
  deleted player's own row, the guard's own SKIP LOCKED read, or a bet
  party's row right after the guard on that same player; every ffa_bets
  claim it reaches comes right after the bet guard on that same bet; a new
  one fails until it is classed.
"""

import ast
import asyncio
import hashlib
import hmac
import inspect
import os
import re
import sys
import time

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy.exc import DBAPIError

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import mail_discord  # noqa: E402
import main  # noqa: E402

SECRET = "mdpl-bound-secret"
STEAM = "76561190000000777"
PATH = "/api/v1/players/{steam_id}/data"
HELPERS = ("_reconcile_team_series_bets", "_refund_lobby_bets",
           "_refund_ffa_lobby_bets", "_reconcile_ffa_lobby_bets")


def _sig(sid):
    return hmac.new(SECRET.encode(), ("delete:%s" % sid).encode(), hashlib.sha256).hexdigest()


def _route():
    hits = [r for r in main.app.router.routes
            if getattr(r, "path", None) == PATH and "DELETE" in (getattr(r, "methods", None) or ())]
    assert len(hits) == 1, ("the deletion route", hits)
    return hits[0]


class _Orig(Exception):
    def __init__(self, sqlstate):
        super().__init__("forced %s" % sqlstate)
        self.sqlstate = sqlstate


def _db_error(sqlstate):
    return DBAPIError("forced", None, _Orig(sqlstate))


async def _stamp_against_release(monkeypatch, route):
    """Holds every writer slot, sends the deletion through `route`, frees one
    slot 0.5 s later: (the first clock read of the request, the release time,
    the response)."""
    reads = []
    real = time.monotonic

    def clock():
        t = real()
        reads.append(t)
        return t
    monkeypatch.setattr(main, "_deletion_clock", clock)
    app = FastAPI()
    app.router.routes.append(route)
    gate = main._pc_writer_gate()
    for _ in range(main._PC_WRITER_SLOTS):
        await gate.acquire()
    held = main._PC_WRITER_SLOTS
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mdpl") as c:
            req = asyncio.create_task(c.delete(PATH.format(steam_id=STEAM), params={"sig": "0" * 64}))
            await asyncio.sleep(0.5)
            assert not req.done(), "the request did not wait for a writer slot"
            released = real()
            gate.release()
            held -= 1
            resp = await asyncio.wait_for(req, 30)
    finally:
        for _ in range(held):
            gate.release()
    return (reads[0] if reads else None), released, resp


def test_the_arrival_stamp_is_read_before_the_writer_slot_wait(monkeypatch):
    """C1. The deadline is the stamp plus the budget, so a stamp read before
    the slot's release counts the wait for the slot."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    first, released, resp = asyncio.run(_stamp_against_release(monkeypatch, _route()))
    assert resp.status_code == 403, resp.text        # the signature check: no database is touched
    assert first is not None and first < released, (
        "the stamp was not read before the slot was released", first, released)


def test_the_stamp_declared_after_the_slot_reads_it_late(monkeypatch):
    """C1's negative control: the same endpoint with _arrived declared after
    _slot (the stamp taken once the handler may run) reads it after the
    release, so the test above can fail."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    params = list(inspect.signature(main.delete_player_data).parameters.values())
    arrived = next(p for p in params if p.name == "_arrived")
    rest = [p for p in params if p.name != "_arrived"]
    rest.insert([p.name for p in rest].index("_slot") + 1, arrived)

    async def stamp_after_slot(**kw):
        return await main.delete_player_data(**kw)
    stamp_after_slot.__signature__ = inspect.Signature(rest)
    app = FastAPI()
    app.add_api_route(PATH, stamp_after_slot, methods=["DELETE"])
    route = [r for r in app.router.routes if getattr(r, "path", None) == PATH][0]
    first, released, resp = asyncio.run(_stamp_against_release(monkeypatch, route))
    assert resp.status_code == 403, resp.text
    assert first is not None and first >= released, ("the mutant read the stamp early", first, released)


class _NoDb:
    """A session that must not be used."""
    async def execute(self, *a, **k):
        raise AssertionError("a statement ran")

    async def rollback(self):
        raise AssertionError("rolled back")

    async def commit(self):
        raise AssertionError("committed")


def test_an_attempt_that_cannot_fit_is_not_started(monkeypatch):
    """R6a (1) and (2): less than one attempt left at the start: no statement
    runs, and the answer is 503 account_cleanup_contended."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    left = main._DELETION_ATTEMPT_MIN_S - 0.5
    arrived = time.monotonic() - (main._DELETION_BUDGET_S - left)
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.delete_player_data(STEAM, None, sig=_sig(STEAM), _arrived=arrived,
                                            _slot=None, db=_NoDb()))
    assert (e.value.status_code, e.value.detail) == (503, "account_cleanup_contended"), e.value


class _VictimDb:
    """Every attempt ends at its first statement as a deadlock victim; each
    attempt takes `cost` seconds of the stubbed clock."""
    def __init__(self, clock, cost, sqlstate="40P01"):
        self.clock, self.cost, self.sqlstate = clock, cost, sqlstate
        self.attempts, self.rollbacks, self.left_at_start = 0, 0, []

    async def execute(self, statement, params=None, *a, **k):
        self.attempts += 1
        self.left_at_start.append(self.clock.deadline - self.clock.now)
        self.clock.now += self.cost
        raise _db_error(self.sqlstate)

    async def rollback(self):
        self.rollbacks += 1

    async def commit(self):
        raise AssertionError("committed")


class _Clock:
    def __init__(self):
        self.now = 1000.0
        self.deadline = self.now + main._DELETION_BUDGET_S

    def __call__(self):
        return self.now


@pytest.mark.parametrize("sqlstate", ["40P01", "40001"])
def test_attempts_run_again_only_while_one_still_fits(monkeypatch, sqlstate):
    """R6/R6a: a deadlock victim (or a serialization failure) runs again from
    the start while the time left covers ATTEMPT_MIN; then the refusal, with
    no commit. Every attempt that ran had at least ATTEMPT_MIN left."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    clock = _Clock()
    monkeypatch.setattr(main, "_deletion_clock", clock)
    db = _VictimDb(clock, cost=3.0, sqlstate=sqlstate)
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.delete_player_data(STEAM, None, sig=_sig(STEAM), _arrived=clock.now,
                                            _slot=None, db=db))
    assert (e.value.status_code, e.value.detail) == (503, "account_cleanup_contended"), e.value
    want = int((main._DELETION_BUDGET_S - main._DELETION_ATTEMPT_MIN_S) // 3.0) + 1
    assert db.attempts == want and db.rollbacks == want, (db.attempts, db.rollbacks, want)
    assert min(db.left_at_start) >= main._DELETION_ATTEMPT_MIN_S, db.left_at_start


def test_any_other_database_error_is_not_run_again(monkeypatch):
    """#505: only 40P01 and 40001 run again; a unique violation is the route's
    error at once."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    clock = _Clock()
    monkeypatch.setattr(main, "_deletion_clock", clock)
    db = _VictimDb(clock, cost=0.1, sqlstate="23505")
    with pytest.raises(DBAPIError):
        asyncio.run(main.delete_player_data(STEAM, None, sig=_sig(STEAM), _arrived=clock.now,
                                            _slot=None, db=db))
    assert db.attempts == 1, db.attempts


class _OnceDb(_VictimDb):
    """The first attempt ends at its first statement with `sqlstate`; the next ends there with _Stop."""
    async def execute(self, statement, params=None, *a, **k):
        self.attempts += 1
        self.clock.now += self.cost
        if self.attempts == 1:
            raise _db_error(self.sqlstate)
        raise _Stop()


def test_a_lock_wait_that_reached_the_cap_runs_the_attempt_again(monkeypatch, capsys):
    """55P03 before the deadline: one lock wait of the attempt reached
    _DELETION_WAIT_CAP_S (the option taken at the choke point). The attempt
    rolls back and the next starts after the held pause, as on a held row;
    the log line names the wait."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    clock = _Clock()
    monkeypatch.setattr(main, "_deletion_clock", clock)
    pauses = _paused(monkeypatch, clock)
    db = _OnceDb(clock, cost=0.1, sqlstate="55P03")
    with pytest.raises(_Stop):
        asyncio.run(main.delete_player_data(STEAM, None, sig=_sig(STEAM), _arrived=clock.now,
                                            _slot=None, db=db))
    assert (db.attempts, db.rollbacks, pauses) == (2, 1, [0.25]), (db.attempts, db.rollbacks, pauses)
    assert "deletion attempt 1 met a held %s;" % main._DELETION_WAIT_WHAT in capsys.readouterr().out


@pytest.mark.parametrize("sqlstate,cost", [("57014", 0.1), ("55P03", main._DELETION_BUDGET_S + 0.5)])
def test_a_timeout_at_the_deadline_is_refused_at_once(monkeypatch, sqlstate, cost):
    """57014 (statement_timeout, armed to the time left), and a 55P03 that
    ends at or after the deadline: 503 at once, after one attempt, rolled
    back, never committed, no pause."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    clock = _Clock()
    monkeypatch.setattr(main, "_deletion_clock", clock)
    pauses = _paused(monkeypatch, clock)
    db = _VictimDb(clock, cost=cost, sqlstate=sqlstate)
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.delete_player_data(STEAM, None, sig=_sig(STEAM), _arrived=clock.now,
                                            _slot=None, db=db))
    assert (e.value.status_code, e.value.detail) == (503, "account_cleanup_contended"), e.value
    assert (db.attempts, db.rollbacks, pauses) == (1, 1, []), (db.attempts, db.rollbacks, pauses)


def test_the_deadline_variable_is_unset_after_a_refusal_and_after_an_error(monkeypatch):
    """C2: the deadline is the one value the bound keeps in a context
    variable, set for each attempt and reset in that try's finally. After a
    deletion refused (57014) and after one ended by any other error (23505),
    run in the caller's own task, the variable is unset there."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    clock = _Clock()
    monkeypatch.setattr(main, "_deletion_clock", clock)

    async def go():
        seen = [main._deletion_deadline.get()]
        for code in ("57014", "23505"):
            db = _VictimDb(clock, cost=0.1, sqlstate=code)
            try:
                await main.delete_player_data(STEAM, None, sig=_sig(STEAM), _arrived=clock.now,
                                              _slot=None, db=db)
            except (HTTPException, DBAPIError) as e:
                seen.append((code, type(e).__name__, db.attempts, main._deletion_deadline.get()))
        return seen

    seen = asyncio.run(go())
    assert seen == [None, ("57014", "HTTPException", 1, None), ("23505", "DBAPIError", 1, None)], seen


def test_the_bound_and_the_helpers_read_the_retry_set_when_they_run(monkeypatch):
    """The order tests empty the retry set to see PostgreSQL's 40P01 as it is
    (test_mdpl_deletion_lock_order_pg._order_only). The bound and the
    helpers' test both follow it, as a set fixed at import would not: the
    40P01 is the route's error at once, after one attempt; 55P03 is still
    acted on."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    monkeypatch.setattr(main, "_DELETION_RETRY_SQLSTATES", frozenset())
    assert main._retryable_for_caller(_db_error("40P01"), True) is False
    assert main._retryable_for_caller(_db_error("55P03"), True) is True
    clock = _Clock()
    monkeypatch.setattr(main, "_deletion_clock", clock)
    db = _VictimDb(clock, cost=0.1, sqlstate="40P01")
    with pytest.raises(DBAPIError):
        asyncio.run(main.delete_player_data(STEAM, None, sig=_sig(STEAM), _arrived=clock.now,
                                            _slot=None, db=db))
    assert db.attempts == 1, db.attempts


def test_the_bet_helpers_keep_their_present_behaviour_by_default():
    """R6b: the flag defaults to False on all four helpers, and only the
    deletion passes True (four calls); every other caller is unchanged."""
    for name in HELPERS:
        p = inspect.signature(getattr(main, name)).parameters.get("raise_retryable")
        assert p is not None and p.default is False, (name, p)
    with open(main.__file__, encoding="utf-8") as fh:
        module = fh.read()
    handler = inspect.getsource(main.delete_player_data)
    assert handler.count("raise_retryable=True") == 4, handler.count("raise_retryable=True")
    rest = module.replace(handler, "").replace(inspect.getsource(main._retryable_for_caller), "")
    assert "raise_retryable=True" not in rest, "another caller passes the flag"


def _executed_in_order(fn, *names):
    """Each statement constant is executed exactly once in fn's source (as
    text(NAME) or text(mail_discord.NAME)), in the given order."""
    src = inspect.getsource(fn)
    at = []
    for n in names:
        hits = [m.start() for m in re.finditer(r"text\((?:mail_discord\.)?%s\)" % re.escape(n), src)]
        assert len(hits) == 1, (fn.__name__, n, len(hits))
        at.append(hits[0])
    assert at == sorted(at), (fn.__name__, list(zip(names, at)))


def test_each_pending_dms_writer_runs_its_pass_before_its_first_write():
    """R4's writers, by their source: where each one's id-ordered pass stands.
    test_mdpl_proof_pg.py proves the order live; this pins the places."""
    _executed_in_order(main.delete_player_data, "_ERASE_RELAY_DMS_LOCK_SQL",
                       "_ERASE_RELAY_DMS_TO_SQL", "_ERASE_RELAY_DMS_FROM_SQL")
    _executed_in_order(main.ack_pending_dms, "_PENDING_DM_ACK_LOCK_SQL",
                       "_PENDING_DM_SETTLE_SQL", "_PENDING_DM_ACK_SQL")
    for fn in (mail_discord.mail_relay_pref, main.mail_settings_put):
        _executed_in_order(fn, "RELAY_OFF_LOCK_SQL", "RELAY_OFF_CANCEL_SQL")
    assert main._ERASE_RELAY_DMS_LOCK_SQL.rstrip().endswith("ORDER BY id FOR UPDATE")
    assert main._PENDING_DM_ACK_LOCK_SQL.rstrip().endswith("ORDER BY id FOR NO KEY UPDATE")
    assert mail_discord.RELAY_OFF_LOCK_SQL.rstrip().endswith("ORDER BY id FOR NO KEY UPDATE")
    assert "FOR NO KEY UPDATE SKIP LOCKED" in main._PENDING_DM_RETIRE_SQL


def test_only_the_errors_the_bound_acts_on_leave_the_savepoint():
    """R6b: the helpers' test of an error, by its SQLSTATE and the caller's
    flag: with the flag, the errors the deletion's bound acts on (40P01 and
    40001, run again; 55P03, a held lock or the deadline; 57014, the
    deadline); nothing else, and nothing without the flag. A flush inside a
    helper's savepoint raises the two timeouts raw, outside the statement
    arming, so the helper must hand them back."""
    for code, flag, want in (("40P01", True, True), ("40001", True, True),
                             ("40P01", False, False), ("23505", True, False),
                             ("55P03", True, True), ("55P03", False, False),
                             ("57014", True, True), ("57014", False, False)):
        assert main._retryable_for_caller(_db_error(code), flag) is want, (code, flag)
    assert main._retryable_for_caller(ValueError("x"), True) is False


# -- r1 HIGH: a bet party's players row, taken without a wait ------------------------------------

class _Stop(Exception):
    """Ends the attempt after the held ones, so that a test counts the attempts that ran."""


class _HeldDb:
    """The first `held` attempts each meet a held bet party row at their
    first statement (each costs `cost` seconds of the stubbed clock); the
    next attempt ends there with _Stop."""
    def __init__(self, clock, held, cost=0.0):
        self.clock, self.held, self.cost = clock, held, cost
        self.attempts, self.rollbacks = 0, 0

    async def execute(self, statement, params=None, *a, **k):
        self.attempts += 1
        self.clock.now += self.cost
        if self.attempts <= self.held:
            raise main._DeletionRowHeld("bet party row")
        raise _Stop()

    async def rollback(self):
        self.rollbacks += 1

    async def commit(self):
        raise AssertionError("committed")


def _paused(monkeypatch, clock):
    """asyncio.sleep stubbed: records each pause and moves the stubbed clock by it."""
    pauses = []

    async def sleep(s, *a, **k):
        pauses.append(s)
        clock.now += s

    monkeypatch.setattr(asyncio, "sleep", sleep)
    return pauses


def test_a_held_party_row_runs_the_attempt_again_after_its_pause(monkeypatch, capsys):
    """Four attempts meet a held row: each rolls back, and the next starts
    after its pause (0.25 s, 0.5 s, then 1.0 s each); the fifth runs. Each
    held attempt prints a line of its own with its number."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    clock = _Clock()
    monkeypatch.setattr(main, "_deletion_clock", clock)
    pauses = _paused(monkeypatch, clock)
    db = _HeldDb(clock, held=4)
    with pytest.raises(_Stop):
        asyncio.run(main.delete_player_data(STEAM, None, sig=_sig(STEAM), _arrived=clock.now,
                                            _slot=None, db=db))
    assert (db.attempts, db.rollbacks) == (5, 4), (db.attempts, db.rollbacks)
    assert pauses == [0.25, 0.5, 1.0, 1.0], pauses
    out = capsys.readouterr().out
    for n in range(1, 5):
        assert "deletion attempt %d met a held bet party row" % n in out, (n, out[-2000:])


def test_a_row_held_through_the_whole_budget_allows_at_most_thirteen_attempts(monkeypatch, capsys):
    """The row never comes free and each attempt meets it at once (no work
    time, the most attempts the arithmetic allows): attempts start at 0,
    0.25, 0.75, 1.75 ... 10.75 s; the thirteenth's pause would leave less
    than ATTEMPT_MIN, so the bound refuses at once, without that pause."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    clock = _Clock()
    monkeypatch.setattr(main, "_deletion_clock", clock)
    pauses = _paused(monkeypatch, clock)
    db = _HeldDb(clock, held=10 ** 6)
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.delete_player_data(STEAM, None, sig=_sig(STEAM), _arrived=clock.now,
                                            _slot=None, db=db))
    assert (e.value.status_code, e.value.detail) == (503, "account_cleanup_contended"), e.value
    assert (db.attempts, db.rollbacks, len(pauses)) == (13, 13, 12), (db.attempts, db.rollbacks, pauses)
    assert clock.deadline - clock.now >= main._DELETION_ATTEMPT_MIN_S - 1.0, clock.deadline - clock.now
    assert "deletion attempt 13 met a held bet party row" in capsys.readouterr().out


def test_the_held_signal_comes_back_from_a_helper_whatever_its_flag():
    """Only a deletion attempt raises the two signals (a held row, a
    statement past the deadline), and its bound must see them: a helper
    called with raise_retryable False hands them back as well."""
    for flag in (True, False):
        assert main._retryable_for_caller(main._DeletionRowHeld("x"), flag) is True, flag
        assert main._retryable_for_caller(main._DeletionPastDeadline(), flag) is True, flag


def test_each_held_thing_is_named_in_the_bound_s_log_line(monkeypatch, capsys):
    """The log line names what the attempt met, so that its rate can be read
    per kind from the api log: a bet party's row, its identity key, an FFA
    bet row, each of the five step-4 rows, and a lock wait that reached the
    cap."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    for what in ("bet party row", "bet party's identity key", "FFA bet row", "ffa_lobbies row",
                 "team_series row", "ovt_series row", "team_lobbies row", "ovt_lobbies row",
                 main._DELETION_WAIT_WHAT):
        clock = _Clock()
        monkeypatch.setattr(main, "_deletion_clock", clock)
        _paused(monkeypatch, clock)

        class _Once(_HeldDb):
            async def execute(self, statement, params=None, *a, **k):
                self.attempts += 1
                if self.attempts == 1:
                    raise main._DeletionRowHeld(what)
                raise _Stop()
        with pytest.raises(_Stop):
            asyncio.run(main.delete_player_data(STEAM, None, sig=_sig(STEAM), _arrived=clock.now,
                                                _slot=None, db=_Once(clock, held=0)))
        assert "deletion attempt 1 met a held %s;" % what in capsys.readouterr().out, what


def test_without_no_wait_the_guards_run_no_statement():
    """Point 6: the no-wait mode is explicit and off by default. Without it
    (no keyword, or no_wait=False) neither guard runs a statement, so every
    other caller's own statement waits for the row as it always has -- also
    when the deletion's deadline variable is set, which no longer decides."""
    rid = "00000000-0000-0000-0000-000000000001"

    async def go():
        for guard in (main._deletion_lock_party_row, main._deletion_lock_ffa_bet):
            await guard(_NoDb(), rid)
            await guard(_NoDb(), rid, no_wait=False)
        token = main._deletion_deadline.set(main._deletion_clock() + 60.0)
        try:
            for guard in (main._deletion_lock_party_row, main._deletion_lock_ffa_bet):
                await guard(_NoDb(), rid)
        finally:
            main._deletion_deadline.reset(token)
    asyncio.run(go())


class _Res:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row

    def close(self):
        pass


class _ScriptDb:
    """Answers each statement with the next scripted row (None: no row) and records the statements."""
    def __init__(self, *rows):
        self.rows, self.seen = list(rows), []

    async def execute(self, statement, params=None, *a, **k):
        self.seen.append((str(statement), dict(params or {})))
        return _Res(self.rows.pop(0))


def _guard_inside(db, pid="00000000-0000-0000-0000-000000000002", guard=None):
    """The guard in the no-wait mode, as the deletion's bet path calls it; no deadline variable."""
    asyncio.run((guard or main._deletion_lock_party_row)(db, pid, no_wait=True))


def test_inside_an_attempt_the_guard_takes_the_row_skip_locked_and_reads_a_skipped_one():
    """A row the SKIP LOCKED read returns: taken, and then the party's
    identity key in its try form. None, and the plain read finds the row:
    another transaction holds it, the signal. None both times: no such row,
    nothing raised, and the caller's own statement runs as before."""
    assert main._DELETION_PARTY_LOCK_SQL.rstrip().endswith("FOR NO KEY UPDATE SKIP LOCKED")
    assert "FOR " not in main._DELETION_PARTY_SEEN_SQL.upper()
    pid = {"pid": "00000000-0000-0000-0000-000000000002"}
    got = _ScriptDb(("76561190000000888",), (True,))
    _guard_inside(got)
    assert got.seen == [(main._DELETION_PARTY_LOCK_SQL, pid),
                        (main._DELETION_PARTY_KEY_SQL, {"sid": "76561190000000888"})], got.seen
    held = _ScriptDb(None, (1,))
    with pytest.raises(main._DeletionRowHeld) as e:
        _guard_inside(held)
    assert e.value.what == "bet party row"
    assert held.seen == [(main._DELETION_PARTY_LOCK_SQL, pid), (main._DELETION_PARTY_SEEN_SQL, pid)]
    gone = _ScriptDb(None, None)
    _guard_inside(gone)
    assert gone.seen == [(main._DELETION_PARTY_LOCK_SQL, pid), (main._DELETION_PARTY_SEEN_SQL, pid)]


def test_inside_an_attempt_the_guard_takes_the_party_s_identity_key_without_a_wait():
    """The row taken, the identity key is tried, exclusive, on the text of the
    party's steam id (the form the routes' identity key hashes): refused
    (another transaction holds it, shared or exclusive), the signal; a row
    with no steam id, no key."""
    sql = main._DELETION_PARTY_KEY_SQL
    assert "pg_try_advisory_xact_lock(" in sql and "_shared" not in sql, sql
    assert "hashtext(CAST(:sid AS text))" in sql, sql
    refused = _ScriptDb(("76561190000000888",), (False,))
    with pytest.raises(main._DeletionRowHeld) as e:
        _guard_inside(refused)
    assert e.value.what == "bet party's identity key"
    assert [s for s, _ in refused.seen] == [main._DELETION_PARTY_LOCK_SQL, main._DELETION_PARTY_KEY_SQL]
    keyless = _ScriptDb((None,))
    _guard_inside(keyless)
    assert [s for s, _ in keyless.seen] == [main._DELETION_PARTY_LOCK_SQL]


def test_inside_an_attempt_the_ffa_bet_guard_takes_the_row_skip_locked_and_reads_a_skipped_one():
    """An unsettled bet row the SKIP LOCKED read returns: taken, one statement.
    None, and the plain read still finds it unsettled: another transaction
    holds it, the signal. None both times (settled meanwhile, or gone):
    nothing raised, and the claim passes over it as before."""
    assert main._DELETION_FFA_BET_LOCK_SQL.rstrip().endswith("FOR NO KEY UPDATE SKIP LOCKED")
    assert "settled_at IS NULL" in main._DELETION_FFA_BET_LOCK_SQL
    seen_sql = main._DELETION_FFA_BET_SEEN_SQL
    assert "FOR " not in seen_sql.upper() and "settled_at IS NULL" in seen_sql
    bid = {"bid": "00000000-0000-0000-0000-000000000002"}
    guard = main._deletion_lock_ffa_bet
    got = _ScriptDb((1,))
    _guard_inside(got, guard=guard)
    assert got.seen == [(main._DELETION_FFA_BET_LOCK_SQL, bid)], got.seen
    held = _ScriptDb(None, (1,))
    with pytest.raises(main._DeletionRowHeld) as e:
        _guard_inside(held, guard=guard)
    assert e.value.what == "FFA bet row"
    assert held.seen == [(main._DELETION_FFA_BET_LOCK_SQL, bid), (seen_sql, bid)]
    settled = _ScriptDb(None, None)
    _guard_inside(settled, guard=guard)
    assert settled.seen == [(main._DELETION_FFA_BET_LOCK_SQL, bid), (seen_sql, bid)]


# The census. Every statement in a function the deletion reaches (calls to
# bare names main.py defines, from delete_player_data) whose SQL updates
# players or locks a players row, with the player it names. A new one fails
# here until it is classed.
_PLAYERS_SQL = re.compile(r"\bUPDATE\s+players\b|\bFROM\s+players\b(?:(?!;).)*?"
                          r"\bFOR\s+(?:NO\s+KEY\s+UPDATE|UPDATE|SHARE|KEY\s+SHARE)\b", re.I | re.S)
# The deleted player's own row: delete_player_data writes it first (its
# "pc_shards = 0" statement), before any lobby, series, queue or bet row, so
# no later statement on it waits; _pc_clear_portrait_unit runs on that same
# row (called with str(pid)) after that write.
_OWN_ROW = sorted([("_pc_clear_portrait_unit", "pid"), ("_pc_clear_portrait_unit", "params['pid']"),
                   ("delete_player_data", "pid"), ("delete_player_data", "str(pid)")])
# The guard's own read, which never waits (SKIP LOCKED).
_GUARD_ROW = [("_deletion_lock_party_row", "player_id")]
# A bet party's row: each statement right after the guard on the same player.
_PARTY_ROW = sorted([("_credit_bet_fighter_tax", "fighter_id"), ("_return_stake_exactly", "player_id"),
                     ("_reconcile_team_series_bets", "winner_id"),
                     ("_reconcile_team_series_bets", "b['player_id']"),
                     ("_settle_ffa_bets_for_game", "winner_pid"),
                     ("_settle_ffa_bets_for_game", "b['player_id']")])


def _reach(source, root):
    tree = ast.parse(source)
    defs = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs.setdefault(node.name, []).append(node)
    seen, todo = set(), [root]
    while todo:
        name = todo.pop()
        if name in seen or name not in defs:
            continue
        seen.add(name)
        for fn in defs[name]:
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id in defs:
                    todo.append(sub.func.id)
    return {n: defs[n] for n in seen}


def _text_of(x, module):
    """A SQL expression's text: a string literal, the name of a module-level string of main, an
    f-string or a + of those; any part it cannot read stands as {?}."""
    if isinstance(x, ast.Constant) and isinstance(x.value, str):
        return x.value
    if isinstance(x, ast.Name) and isinstance(getattr(module, x.id, None), str):
        return getattr(module, x.id)
    if isinstance(x, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{?}" for v in x.values)
    if isinstance(x, ast.BinOp) and isinstance(x.op, ast.Add):
        return _text_of(x.left, module) + _text_of(x.right, module)
    return "{?}"


def _sql_of(call, module):
    """The SQL of `db.execute(text(X), ...)`, else None."""
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "execute"
            and call.args):
        return None
    t = call.args[0]
    if not (isinstance(t, ast.Call) and getattr(t.func, "id", None) == "text" and t.args):
        return None
    return _text_of(t.args[0], module)


def _pid_of(call, key="pid"):
    """The row a statement names: the `key` entry of its parameters, written as its source
    (`p['pid']` when the parameters are passed as a name, p)."""
    params = call.args[1] if len(call.args) > 1 else next(
        (k.value for k in call.keywords if k.arg == "params"), None)
    if isinstance(params, ast.Dict):
        for k, v in zip(params.keys, params.values):
            if isinstance(k, ast.Constant) and k.value == key:
                return ast.unparse(v)
        return "?"
    if params is not None:
        return "%s[%r]" % (ast.unparse(params), key)
    return "?"


def _players_census(source, module):
    """(guarded, bare): each players statement of the reach, (function, player), guarded when the
    statement right before it in its block is `await _deletion_lock_party_row(db, <same player>)`."""
    return _census(source, module, _PLAYERS_SQL, "_deletion_lock_party_row", "pid")


def _census(source, module, pattern, guard, key):
    """(guarded, bare) over the statements of the reach whose SQL matches pattern, each as
    (function, the row its `key` parameter names); guarded when the statement right before it in
    its block is `await <guard>(db, <same row>, no_wait=no_wait)` -- the function's own mode
    handed on, the one keyword (point 6)."""
    guarded, bare = [], []
    for name, fns in _reach(source, "delete_player_data").items():
        for fn in fns:
            for blk in ast.walk(fn):
                for field in ("body", "orelse", "finalbody"):
                    stmts = getattr(blk, field, None)
                    if not isinstance(stmts, list):
                        continue
                    for i, st in enumerate(stmts):
                        if not isinstance(st, ast.stmt) or isinstance(st, (
                                ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith,
                                ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            continue
                        for sub in ast.walk(st):
                            sql = _sql_of(sub, module)
                            if sql is None or not pattern.search(sql):
                                continue
                            pid = _pid_of(sub, key)
                            prev = stmts[i - 1] if i > 0 else None
                            g = None
                            if (isinstance(prev, ast.Expr) and isinstance(prev.value, ast.Await)
                                    and isinstance(prev.value.value, ast.Call)
                                    and getattr(prev.value.value.func, "id", None) == guard
                                    and len(prev.value.value.args) == 2
                                    and [(k.arg, ast.unparse(k.value)) for k in prev.value.value.keywords]
                                    == [("no_wait", "no_wait")]):
                                g = ast.unparse(prev.value.value.args[1])
                            (guarded if g == pid else bare).append((name, pid))
    return sorted(guarded), sorted(bare)


def test_every_players_statement_the_deletion_reaches_is_classed():
    """Each players statement of the deletion's reach is the deleted
    player's own row, the guard's own read, or a bet party's row right after
    the guard on that same player. A new players statement anywhere in the
    reach, or a guard moved or removed, fails here."""
    with open(main.__file__, encoding="utf-8") as fh:
        source = fh.read()
    guarded, bare = _players_census(source, main)
    assert guarded == _PARTY_ROW, guarded
    assert bare == sorted(_OWN_ROW + _GUARD_ROW), bare


_FFA_BETS_SQL = re.compile(r"\bUPDATE\s+ffa_bets\b|\bFROM\s+ffa_bets\b(?:(?!;).)*?"
                           r"\bFOR\s+(?:NO\s+KEY\s+UPDATE|UPDATE|SHARE|KEY\s+SHARE)\b", re.I | re.S)
# The bet guard's own read, which never waits (SKIP LOCKED).
_FFA_GUARD_ROW = [("_deletion_lock_ffa_bet", "bet_id")]
# Each claim, right after the bet guard on the same bet.
_FFA_CLAIM = sorted([("_refund_ffa_lobby_bets", "b['id']"), ("_settle_ffa_bets_for_game", "b['id']")])


def test_every_ffa_bets_claim_the_deletion_reaches_comes_after_the_bet_guard():
    """Each ffa_bets statement that writes or locks a row, in the deletion's
    reach, is a claim right after _deletion_lock_ffa_bet on that same bet, or
    the guard's own SKIP LOCKED read. A new one, or a guard moved or removed,
    fails here."""
    with open(main.__file__, encoding="utf-8") as fh:
        source = fh.read()
    guarded, bare = _census(source, main, _FFA_BETS_SQL, "_deletion_lock_ffa_bet", "bid")
    assert guarded == _FFA_CLAIM, guarded
    assert bare == _FFA_GUARD_ROW, bare


# -- point 6: the no-wait mode, explicit, off by default, turned on by the deletion alone --------

_NO_WAIT_FNS = sorted([
    "_deletion_lock_party_row", "_deletion_lock_ffa_bet", "_credit_bet_fighter_tax",
    "_credit_team_bet_fighter_tax", "_return_stake_exactly", "_reconcile_team_series_bets",
    "_settle_ffa_bets_for_game", "_refund_ffa_lobby_bets", "_reconcile_ffa_lobby_bets",
    "_lobby_bet_pay_refund", "_refund_lobby_bets"])
# The deletion's calls that turn it on: (callee, how many).
_NO_WAIT_ON = [("_reconcile_ffa_lobby_bets", 1), ("_reconcile_team_series_bets", 1), ("_refund_lobby_bets", 2)]


def _defs(source):
    out = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.setdefault(node.name, []).append(node)
    return out


def _no_wait_calls(source):
    """Every call in main.py to a function that takes no_wait: (caller, callee, form), form one of
    'default' (no keyword), 'on' (no_wait=True), 'handed' (no_wait=no_wait inside a function that
    takes no_wait itself), or the call's source for any other form."""
    defs = _defs(source)
    takes = {n for n, fns in defs.items() for f in fns if any(a.arg == "no_wait" for a in f.args.kwonlyargs)}
    out = []
    for name, fns in defs.items():
        for f in fns:
            own = any(a.arg == "no_wait" for a in f.args.kwonlyargs)
            for sub in ast.walk(f):
                if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id in takes):
                    continue
                kw = [k for k in sub.keywords if k.arg == "no_wait"]
                if any(k.arg is None for k in sub.keywords) or len(kw) > 1:
                    form = ast.unparse(sub)
                elif not kw:
                    form = "default"
                elif isinstance(kw[0].value, ast.Constant) and kw[0].value.value is True:
                    form = "on"
                elif isinstance(kw[0].value, ast.Name) and kw[0].value.id == "no_wait" and own:
                    form = "handed"
                else:
                    form = ast.unparse(sub)
                out.append((name, sub.func.id, form))
    return sorted(takes), out


def test_the_no_wait_mode_is_off_by_default_turned_on_by_the_deletion_alone_and_handed_down():
    """Point 6. The functions that take no_wait are the two guards and the
    nine bet helpers on the deletion's bet path, each keyword-only and False
    by default. In all of main.py a call to one of them passes it in one of
    three forms: not at all (every caller outside the deletion, which issues
    exactly the statements it issued before), no_wait=True (delete_player_data
    alone, four calls), or no_wait=no_wait inside a function that takes it.
    A function that takes it never calls another without handing it on, and
    the hand-on edges from the deletion's four calls reach all eleven. A
    dropped hand-on, a second caller turning the mode on, or a new function
    with the parameter fails here."""
    with open(main.__file__, encoding="utf-8") as fh:
        source = fh.read()
    takes, calls = _no_wait_calls(source)
    assert takes == _NO_WAIT_FNS, takes
    for name in _NO_WAIT_FNS:
        p = inspect.signature(getattr(main, name)).parameters["no_wait"]
        assert p.kind is inspect.Parameter.KEYWORD_ONLY and p.default is False, (name, p)
    odd = [c for c in calls if c[2] not in ("default", "on", "handed")]
    assert odd == [], odd
    from collections import Counter
    on = sorted(Counter(c[1] for c in calls if c[2] == "on").items())
    assert on == sorted(_NO_WAIT_ON), on
    assert {c[0] for c in calls if c[2] == "on"} == {"delete_player_data"}, [c for c in calls if c[2] == "on"]
    dropped = [c for c in calls if c[0] in _NO_WAIT_FNS and c[2] == "default"]
    assert dropped == [], dropped
    reached, todo = set(), [callee for callee, _n in _NO_WAIT_ON]
    while todo:
        x = todo.pop()
        if x not in reached:
            reached.add(x)
            todo.extend(c[1] for c in calls if c[0] == x and c[2] == "handed")
    assert sorted(reached) == _NO_WAIT_FNS, sorted(set(_NO_WAIT_FNS) - reached)


# -- point 4: the guard's key is the routes' own key ----------------------------------------------

def test_the_party_guard_takes_the_identity_key_in_the_canonical_helper_s_own_form():
    """Point 4. _identity_lock_many's lock and the guard's key are built from
    one expression, _IDENTITY_KEY_ARG: a one-argument key over hashtext of
    the steam id as text. The helper executes that statement and spells no
    advisory key of its own; the guard's key is the same key in its try
    form. A two-argument or otherwise spelled key turns this, and scene 5's
    live mutant (test_mdpl_proof_pg), red."""
    arg = main._IDENTITY_KEY_ARG
    assert arg == "hashtext(CAST(:sid AS text))", arg
    assert main._IDENTITY_KEY_SQL == "SELECT pg_advisory_xact_lock(%s)" % arg, main._IDENTITY_KEY_SQL
    assert main._DELETION_PARTY_KEY_SQL == "SELECT pg_try_advisory_xact_lock(%s)" % arg, \
        main._DELETION_PARTY_KEY_SQL
    def code_of(fn):
        """The function's code without its docstring and comments, which may name the key in prose."""
        node = ast.parse(inspect.getsource(fn).lstrip()).body[0]
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
            node.body = node.body[1:]
        return ast.unparse(node)
    helper = code_of(main._identity_lock_many)
    assert helper.count("text(_IDENTITY_KEY_SQL)") == 1, helper.count("text(_IDENTITY_KEY_SQL)")
    assert "advisory_xact_lock(" not in helper and "hashtext(" not in helper
    guard = code_of(main._deletion_lock_party_row)
    assert guard.count("text(_DELETION_PARTY_KEY_SQL)") == 1 and "hashtext(" not in guard


# -- (a): the five step-4 locks, without a wait -------------------------------------------------

_STEP4 = [("ffa_lobbies", "lid"), ("team_series", "sid"), ("ovt_series", "sid"),
          ("team_lobbies", "lid"), ("ovt_lobbies", "lid")]


def test_a_step_4_row_is_taken_without_a_wait_and_a_held_one_is_the_signal():
    """(a): the row the SKIP LOCKED read returns is taken, one statement; none,
    and the plain read finds it: another transaction holds it, the signal
    naming it; none both times: no such row, passed over as the blocking
    lock passed over it."""
    lock = main.text("SELECT 1 FROM team_series WHERE id = :sid FOR NO KEY UPDATE SKIP LOCKED")
    seen = main.text("SELECT 1 FROM team_series WHERE id = :sid")
    p = {"sid": "00000000-0000-0000-0000-000000000003"}
    take = main._deletion_take_or_yield
    got = _ScriptDb((1,))
    asyncio.run(take(got, "team_series row", lock, seen, p))
    assert got.seen == [(str(lock), p)], got.seen
    held = _ScriptDb(None, (1,))
    with pytest.raises(main._DeletionRowHeld) as e:
        asyncio.run(take(held, "team_series row", lock, seen, p))
    assert e.value.what == "team_series row" and held.seen == [(str(lock), p), (str(seen), p)]
    gone = _ScriptDb(None, None)
    asyncio.run(take(gone, "team_series row", lock, seen, p))
    assert gone.seen == [(str(lock), p), (str(seen), p)], gone.seen


def test_the_deletion_takes_its_five_step_4_locks_without_a_wait():
    """In delete_player_data the five tables' locks are calls of
    _deletion_take_or_yield, in the canonical order (FFA lobbies, team series,
    1v2 series, team lobbies, 1v2 lobbies), each naming '<table> row', its
    lock FOR NO KEY UPDATE SKIP LOCKED on one row of that table, its read a
    plain SELECT of the same row; and no other statement of the deletion
    locks a row of those tables (its later UPDATEs fall on rows these took)."""
    with open(main.__file__, encoding="utf-8") as fh:
        source = fh.read()
    fn = _defs(source)["delete_player_data"][0]
    calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call) and getattr(c.func, "id", None) ==
             "_deletion_take_or_yield"]
    calls.sort(key=lambda c: c.lineno)
    got = []
    for c in calls:
        what = c.args[1].value
        lock, seen = (c.args[i].args[0].value for i in (2, 3))
        key = c.args[4].keys[0].value
        got.append((what.split()[0], key))
        table = what.split()[0]
        assert what == "%s row" % table, what
        assert lock == "SELECT 1 FROM %s WHERE id = :%s FOR NO KEY UPDATE SKIP LOCKED" % (table, key), lock
        assert seen == "SELECT 1 FROM %s WHERE id = :%s" % (table, key), seen
    assert got == _STEP4, got
    body = ast.get_source_segment(source, fn) or ""
    assert "_deletion_take_or_yield" in body
    for table, _k in _STEP4:
        locks = re.findall(r"FROM\s+%s\b[^\"]*?\bFOR\s+(?:NO\s+KEY\s+)?UPDATE(?!\s+SKIP)" % table, body)
        assert locks == [], (table, locks)


# -- the hold-time figure: every statement armed with the time left ------------------------------

class _RecDb:
    """Records each statement; the ones after the arming fail with `fail`, after moving the
    stubbed clock to `then` (a wait that ended there)."""
    def __init__(self, clock, fail=None, then=None):
        self.clock, self.fail, self.then, self.seen = clock, fail, then, []

    async def execute(self, statement, params=None, *a, **k):
        self.seen.append((str(statement), dict(params or {})))
        if self.fail and str(statement) != main._DELETION_ARM_SQL:
            if self.then is not None:
                self.clock.now = self.then
            raise _db_error(self.fail)
        return _Res(None)


def test_every_statement_of_an_attempt_is_armed_with_the_time_left_first(monkeypatch):
    """Before each statement, on the attempt's connection: statement_timeout
    to the time left, lock_timeout to the smaller of that and the cap. At or
    after the deadline no statement is sent (_DeletionPastDeadline). The undo
    takes the arming off the session and off its connection."""
    clock, db, undo = _armed_session(monkeypatch)
    asyncio.run(db.execute(main.text("SELECT 1")))
    clock.now = clock.deadline - 2.25
    asyncio.run(db.execute(main.text("SELECT 2"), {"x": 1}))
    clock.now = clock.deadline - 0.25
    asyncio.run(db.execute(main.text("SELECT 3")))
    assert db.sent == ["CHECKOUT", _armed("500ms", "15000ms"), ("SQL", "SELECT 1"),
                       _armed("500ms", "2250ms"), ("SQL", "SELECT 2"),
                       _armed("250ms", "250ms"), ("SQL", "SELECT 3")], db.sent
    clock.now = clock.deadline
    with pytest.raises(main._DeletionPastDeadline):
        asyncio.run(db.execute(main.text("SELECT 4")))
    assert len(db.sent) == 7, db.sent
    assert "execute" in vars(db) and db.conn.listeners
    undo()
    assert "execute" not in vars(db) and not db.conn.listeners


@pytest.mark.parametrize("code,past,want", [
    ("55P03", False, "held"), ("55P03", True, "past"), ("57014", False, "past"),
    ("40P01", False, "raw"), ("23505", False, "raw")])
def test_the_arming_reads_the_two_timeouts_as_the_bound_s_signals(monkeypatch, code, past, want):
    """A 55P03 before the deadline is a lock wait that reached the cap, a held
    lock; a 55P03 at the deadline, and any 57014, is the deadline; every
    other error passes through as PostgreSQL raised it."""
    clock = _Clock()
    monkeypatch.setattr(main, "_deletion_clock", clock)
    db = _RecDb(clock, fail=code, then=clock.deadline + 0.01 if past else None)
    main._deletion_arm_every_statement(db, clock.deadline)
    with pytest.raises(Exception) as e:
        asyncio.run(db.execute(main.text("SELECT 1")))
    got = {main._DeletionRowHeld: "held", main._DeletionPastDeadline: "past"}.get(type(e.value), "raw")
    assert got == want, (code, past, type(e.value).__name__)
    if want == "held":
        assert e.value.what == main._DELETION_WAIT_WHAT
    if want == "raw":
        assert isinstance(e.value, DBAPIError) and e.value.orig.sqlstate == code


def test_the_bound_arms_each_attempt_and_takes_the_arming_off_after(monkeypatch, capsys):
    """Each attempt checks out its own connection and arms its first statement
    there; after the deletion ends, however it ends, neither the session nor
    any connection it had carries the arming."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    clock = _Clock()
    monkeypatch.setattr(main, "_deletion_clock", clock)
    _paused(monkeypatch, clock)
    _fake_listen(monkeypatch)

    class _Held(_SessionRec):
        """The first attempt meets a held bet party row at its first statement;
        the next attempt ends there with _Stop."""
        def send(self, conn, statement, params=None, many=False, context=None):
            _SessionRec.send(self, conn, statement, params, many, context)
            if statement != main._DELETION_ARM_SQL:
                if len(self.conns) == 1:
                    raise main._DeletionRowHeld("bet party row")
                raise _Stop()
    db = _Held(clock)
    with pytest.raises(_Stop):
        asyncio.run(main.delete_player_data(STEAM, None, sig=_sig(STEAM), _arrived=clock.now,
                                            _slot=None, db=db))
    kinds = [s if isinstance(s, str) else s[0] for s in db.sent]
    assert kinds == ["CHECKOUT", "ARM", "SQL", "ROLLBACK", "CHECKOUT", "ARM", "SQL"], db.sent
    assert not {"execute", "flush", "commit", "begin_nested"} & set(vars(db)), sorted(vars(db))
    assert len(db.conns) == 2 and not any(c.listeners for c in db.conns), db.conns


# -- r2 HIGH 1: the arming on the attempt's connection -------------------------------------------

class _SyncConn:
    """One checked-out connection of a _SessionRec: the listeners _deletion_listen attached to it,
    and a sync execute through which the arming sends its own statement."""
    def __init__(self, rec, n):
        self.rec, self.n, self.listeners = rec, n, []

    def execute(self, statement, params=None):
        self.rec.send(self, str(statement), params)
        return _Res(None)

    def __repr__(self):
        return "<connection %d, %d listeners>" % (self.n, len(self.listeners))


class _Ctx:
    """An execution context as the arming reads it: the name of its execute style."""
    def __init__(self, style):
        self.execute_style = type("Style", (), {"name": style})()


def _fake_listen(monkeypatch):
    """SQLAlchemy's event registry takes no fake target: the fake sessions keep the listeners on
    their fake connection. The PG proof's R6c runs the real _deletion_listen."""
    monkeypatch.setattr(main, "_deletion_listen", lambda conn, fn: conn.listeners.append(fn))
    monkeypatch.setattr(main, "_deletion_unlisten", lambda conn, fn: conn.listeners.remove(fn))


class _SessionRec:
    """A session with the paths the arming covers, sending what SQLAlchemy sends. Each statement
    goes through its connection's listeners first, as before_cursor_execute runs them, and a
    listener that raises keeps it from being sent. Records "CHECKOUT" (a connection checked out:
    the first statement after a release), ("ARM", params), ("SQL", statement), "COMMIT" and
    "ROLLBACK" (both release the connection). `pending`: what the next flush sends -- an explicit
    one, the commit's, or the flushes at a savepoint's two ends -- one statement each, as a flush
    of rows of several tables does; an entry (statement, params, style) is one executemany or one
    insert of many rows. `slow`: seconds of the stubbed clock a step takes ("CHECKOUT", "ARM" or a
    statement's text); `blocked`: no connection is free, a checkout never ends; `fail`: a
    statement's text and the SQLSTATE it fails with."""
    def __init__(self, clock, slow=None, blocked=False, fail=None):
        self.clock, self.slow, self.blocked, self.fail = clock, dict(slow or {}), blocked, dict(fail or {})
        self.sent, self.conn, self.conns, self.pending = [], None, [], []

    def _took(self, step):
        self.clock.now += self.slow.get(step, 0.0)

    async def connection(self):
        if self.conn is None:
            if self.blocked:
                await asyncio.Event().wait()
            self.conn = _SyncConn(self, len(self.conns) + 1)
            self.conns.append(self.conn)
            self.sent.append("CHECKOUT")
            self._took("CHECKOUT")
        return self

    @property
    def sync_connection(self):
        return self.conn

    async def run_sync(self, fn, *a, **k):
        return fn(self.conn, *a, **k)

    def send(self, conn, statement, params=None, many=False, context=None):
        for fn in list(conn.listeners):
            fn(conn, None, statement, params, context, many)
        if statement == main._DELETION_ARM_SQL:
            self.sent.append(("ARM", dict(params or {})))
            self._took("ARM")
            return
        self.sent.append(("SQL", statement))
        self._took(statement)
        if statement in self.fail:
            raise _db_error(self.fail[statement])

    async def _on(self):
        await _SessionRec.connection(self)
        return self.conn

    async def execute(self, statement, params=None, *a, **k):
        conn = await self._on()
        many = isinstance(params, list)
        self.send(conn, str(statement), params, many, _Ctx("EXECUTEMANY") if many else None)
        return _Res(None)

    async def flush(self, *a, **k):
        while self.pending:
            conn = await self._on()
            item = self.pending.pop(0)
            if isinstance(item, tuple):
                self.send(conn, item[0], item[1], True, _Ctx(item[2]))
            else:
                self.send(conn, item)

    async def commit(self):
        await _SessionRec.flush(self)
        self.sent.append("COMMIT")
        self.conn = None

    async def rollback(self):
        self.sent.append("ROLLBACK")
        self.conn = None
        self.pending.clear()

    def begin_nested(self):
        rec = self

        class _Savepoint:
            async def __aenter__(self):
                await _SessionRec.flush(rec)
                rec.send(await rec._on(), "SAVEPOINT sa_savepoint_1")
                return self

            async def __aexit__(self, et, ev, tb):
                if et is None:
                    try:
                        await _SessionRec.flush(rec)
                    except BaseException:
                        rec.send(rec.conn, "ROLLBACK TO SAVEPOINT sa_savepoint_1")
                        raise
                    rec.send(rec.conn, "RELEASE SAVEPOINT sa_savepoint_1")
                else:
                    rec.send(rec.conn, "ROLLBACK TO SAVEPOINT sa_savepoint_1")
                return False
        return _Savepoint()


def _armed(lt, st):
    return ("ARM", {"lt": lt, "st": st})


def _armed_session(monkeypatch, **kw):
    clock = _Clock()
    monkeypatch.setattr(main, "_deletion_clock", clock)
    _fake_listen(monkeypatch)
    db = _SessionRec(clock, **kw)
    return clock, db, main._deletion_arm_every_statement(db, clock.deadline)


def test_everything_an_attempt_sends_is_armed_with_the_time_left_first(monkeypatch):
    """r2 HIGH 1. Each statement of a flush is armed on its own (a flush of
    rows of two tables sends two), and so is a statement inside a savepoint;
    the savepoint's own statements are not; the commit flushes first, each
    statement armed, then arms the COMMIT itself. The undo takes the arming
    off the session's four paths and off its connection."""
    clock, db, undo = _armed_session(monkeypatch)

    async def attempt():
        await db.execute(main.text("SELECT 1"))
        clock.now = clock.deadline - 3.0
        db.pending[:] = ["INSERT a", "UPDATE b"]
        await db.flush()
        async with db.begin_nested():
            await db.execute(main.text("SELECT 2"))
        db.pending[:] = ["INSERT c"]
        clock.now = clock.deadline - 0.2
        await db.commit()
    asyncio.run(attempt())
    full, three, last = _armed("500ms", "15000ms"), _armed("500ms", "3000ms"), _armed("200ms", "200ms")
    assert db.sent == ["CHECKOUT", full, ("SQL", "SELECT 1"),
                       three, ("SQL", "INSERT a"), three, ("SQL", "UPDATE b"),
                       ("SQL", "SAVEPOINT sa_savepoint_1"), three, ("SQL", "SELECT 2"),
                       ("SQL", "RELEASE SAVEPOINT sa_savepoint_1"),
                       last, ("SQL", "INSERT c"), last, "COMMIT"], db.sent
    assert {"execute", "flush", "commit", "begin_nested"} <= set(vars(db)), sorted(vars(db))
    undo()
    assert not {"execute", "flush", "commit", "begin_nested"} & set(vars(db)), sorted(vars(db))
    assert not db.conns[0].listeners, db.conns


def test_a_flush_whose_first_statement_ends_at_the_deadline_sends_no_second(monkeypatch):
    """r2 HIGH 1, the case an arming once per session call leaves open: a
    flush of two rows sends two statements; the first ends at the deadline;
    the second is not sent."""
    clock, db, _undo = _armed_session(monkeypatch, slow={"INSERT a": main._DELETION_BUDGET_S})
    db.pending[:] = ["INSERT a", "INSERT b"]
    with pytest.raises(main._DeletionPastDeadline):
        asyncio.run(db.flush())
    assert db.sent == ["CHECKOUT", _armed("500ms", "15000ms"), ("SQL", "INSERT a")], db.sent


def test_an_executemany_shares_the_time_left_among_its_runs(monkeypatch):
    """PostgreSQL restarts statement_timeout for each run of an executemany:
    one arming for n runs gives each an n-th of the time left. An insert of
    many rows is one statement and keeps the whole of it."""
    clock, db, _undo = _armed_session(monkeypatch)
    asyncio.run(db.execute(main.text("UPDATE x"), [{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}]))
    db.pending[:] = [("INSERT many", [1, 2, 3, 4], "INSERTMANYVALUES")]
    asyncio.run(db.flush())
    assert db.sent == ["CHECKOUT", _armed("500ms", "3750ms"), ("SQL", "UPDATE x"),
                       _armed("500ms", "15000ms"), ("SQL", "INSERT many")], db.sent


def test_a_connection_checked_out_after_a_rollback_is_armed_too(monkeypatch):
    """A rollback releases the connection; the next statement checks out
    another, and the arming is attached to that one as well. The undo takes
    it off both."""
    clock, db, undo = _armed_session(monkeypatch)

    async def go():
        await db.execute(main.text("SELECT 1"))
        await db.rollback()
        await db.execute(main.text("SELECT 2"))
    asyncio.run(go())
    full = _armed("500ms", "15000ms")
    assert db.sent == ["CHECKOUT", full, ("SQL", "SELECT 1"), "ROLLBACK",
                       "CHECKOUT", full, ("SQL", "SELECT 2")], db.sent
    undo()
    assert len(db.conns) == 2 and not any(c.listeners for c in db.conns), db.conns


def _each_path(db):
    """One coroutine per path that holds the connection first: a statement, a
    flush with a row to send, a commit with one, a savepoint around nothing."""
    async def execute():
        await db.execute(main.text("SELECT 1"))

    async def flush():
        db.pending[:] = ["INSERT a"]
        await db.flush()

    async def commit():
        db.pending[:] = ["INSERT a"]
        await db.commit()

    async def savepoint():
        async with db.begin_nested():
            pass
    return {"execute": execute, "flush": flush, "commit": commit, "savepoint": savepoint}


def test_a_checkout_that_ends_past_the_deadline_sends_nothing(monkeypatch):
    """r2 HIGH 1, the reviewer's case at the checkout: the pool hands the
    connection over after the deadline. On each path nothing is sent after
    it, not even a savepoint's own statement."""
    for path in ("execute", "flush", "commit", "savepoint"):
        clock, db, _undo = _armed_session(monkeypatch, slow={"CHECKOUT": main._DELETION_BUDGET_S + 1.0})
        with pytest.raises(main._DeletionPastDeadline):
            asyncio.run(_each_path(db)[path]())
        assert db.sent == ["CHECKOUT"], (path, db.sent)


def test_a_checkout_still_waiting_at_the_deadline_is_cut_there(monkeypatch):
    """r2 HIGH 1: on each path a checkout waits at most the time left (50 ms
    here, on the event loop's own clock), not the pool's 30 s; then
    _DeletionPastDeadline, nothing sent. The test's own 10 s limit turns an
    uncut wait red."""
    for path in ("execute", "flush", "commit", "savepoint"):
        clock, db, _undo = _armed_session(monkeypatch, blocked=True)
        clock.now = clock.deadline - 0.05
        began = time.monotonic()
        with pytest.raises(main._DeletionPastDeadline):
            asyncio.run(asyncio.wait_for(_each_path(db)[path](), 10))
        assert time.monotonic() - began < 5, (path, "the checkout was not cut at the time left")
        assert db.sent == [], (path, db.sent)


def test_an_arming_that_ends_past_the_deadline_sends_no_statement(monkeypatch):
    """r2 HIGH 1, the reviewer's reproduction: the arming returns after the
    deadline (deadline 1015, the arming done at 1016). The statement itself is
    not sent."""
    clock, db, _undo = _armed_session(monkeypatch, slow={"ARM": main._DELETION_BUDGET_S + 1.0})
    with pytest.raises(main._DeletionPastDeadline):
        asyncio.run(db.execute(main.text("SELECT 1")))
    assert db.sent == ["CHECKOUT", _armed("500ms", "15000ms")], db.sent


def test_a_commit_arms_after_its_flush_and_is_not_sent_past_the_deadline(monkeypatch):
    """r2 HIGH 1: the commit flushes first, its statement armed, then arms the
    COMMIT itself; when the flush ends at the deadline the COMMIT is not sent.
    At the deadline from the start nothing is sent."""
    clock, db, _undo = _armed_session(monkeypatch, slow={"INSERT c": 3.0})
    db.pending[:] = ["INSERT c"]
    clock.now = clock.deadline - 3.0
    with pytest.raises(main._DeletionPastDeadline):
        asyncio.run(db.commit())
    assert db.sent == ["CHECKOUT", _armed("500ms", "3000ms"), ("SQL", "INSERT c")], db.sent
    clock, db, _undo = _armed_session(monkeypatch)
    clock.now = clock.deadline
    with pytest.raises(main._DeletionPastDeadline):
        asyncio.run(db.commit())
    assert db.sent == [], db.sent


def test_a_rollback_to_a_savepoint_is_sent_past_the_deadline(monkeypatch):
    """A savepoint's own statements are neither armed nor refused: a body
    whose statement ends at the deadline is left by the refusal of the next
    one, and the savepoint is still rolled back."""
    clock, db, _undo = _armed_session(monkeypatch, slow={"SELECT 2": main._DELETION_BUDGET_S})

    async def go():
        async with db.begin_nested():
            await db.execute(main.text("SELECT 2"))
            await db.execute(main.text("SELECT 3"))
    with pytest.raises(main._DeletionPastDeadline):
        asyncio.run(go())
    assert db.sent == ["CHECKOUT", ("SQL", "SAVEPOINT sa_savepoint_1"), _armed("500ms", "15000ms"),
                       ("SQL", "SELECT 2"), ("SQL", "ROLLBACK TO SAVEPOINT sa_savepoint_1")], db.sent


def test_a_held_row_at_a_savepoint_s_release_flush_rolls_the_savepoint_back(monkeypatch):
    """A statement of the flush before a savepoint's release meets a held row
    (55P03 before the deadline): the savepoint is rolled back, not released,
    and the held signal goes on to the caller."""
    clock, db, _undo = _armed_session(monkeypatch, fail={"INSERT d": "55P03"})

    async def go():
        async with db.begin_nested():
            db.pending[:] = ["INSERT d"]
    with pytest.raises(main._DeletionRowHeld):
        asyncio.run(go())
    assert db.sent == ["CHECKOUT", ("SQL", "SAVEPOINT sa_savepoint_1"), _armed("500ms", "15000ms"),
                       ("SQL", "INSERT d"), ("SQL", "ROLLBACK TO SAVEPOINT sa_savepoint_1")], db.sent


# What the deletion's reach may call on its session: the four methods that hold the connection
# first (a checkout bounded by the time left, the arming attached; every statement on that
# connection is then armed by its own event), and three that send nothing and check nothing out
# (rollback ends the attempt; add and expire leave work for the next flush).
_SESSION_HELD = {"execute", "flush", "commit", "begin_nested"}
_SESSION_ALLOWED = _SESSION_HELD | {"rollback", "add", "expire"}
_SESSION_METHODS = _SESSION_ALLOWED | {
    "scalar", "scalars", "get", "get_one", "refresh", "delete", "merge", "run_sync", "stream",
    "stream_scalars", "begin", "connection", "exec_driver_sql", "invalidate", "close", "add_all",
    "expire_all", "expunge", "reset"}


def _deletion_reach_of(source):
    """The deletion's reach as the session-method test reads it: the
    functions delete_player_data and _pc_lease_drain call by name, transitively."""
    reach = dict(_reach(source, "delete_player_data"))
    reach.update(_reach(source, "_pc_lease_drain"))
    return reach


def _names_begin_nested(x, sessions):
    """Whether x names a session's begin_nested: `<session>.begin_nested` or
    `getattr(<session>, "begin_nested", ...)`."""
    attr = (isinstance(x, ast.Attribute) and x.attr == "begin_nested"
            and isinstance(x.value, ast.Name) and x.value.id in sessions)
    dyn = (isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == "getattr"
           and len(x.args) >= 2 and isinstance(x.args[0], ast.Name) and x.args[0].id in sessions
           and isinstance(x.args[1], ast.Constant) and x.args[1].value == "begin_nested")
    return attr or dyn


def _session_reading(reach):
    """What `reach` calls on a session, as the session-method test reads it:
    {method: the functions that call it} for each call `<session>.<method>(...)`
    of a method of _SESSION_METHODS, and [(function, line)] for each call of a
    session's begin_nested that is not itself the expression of an `async with`
    item. A session is db or a parameter annotated AsyncSession. A call of
    begin_nested is `<session>.begin_nested(...)`,
    `getattr(<session>, "begin_nested", ...)(...)`, or a call of a name the
    function binds to either by a plain assignment (`x = ...`). The list counts
    calls, not the name: an awaited call is in it, and so is a call held in a
    name and entered or awaited later (refused alike, though `async with` on
    the held object would be sound); an `async with` item's own call is not."""
    calls, outside = {}, []
    for name, fns in reach.items():
        for fn in fns:
            sessions = {"db"} | {a.arg for a in fn.args.args + fn.args.kwonlyargs
                                 if a.annotation is not None and "AsyncSession" in ast.unparse(a.annotation)}
            aliases = {t.id for n in ast.walk(fn)
                       if isinstance(n, ast.Assign) and _names_begin_nested(n.value, sessions)
                       for t in n.targets if isinstance(t, ast.Name)}
            in_with = {id(it.context_expr) for n in ast.walk(fn) if isinstance(n, ast.AsyncWith)
                       for it in n.items}
            for n in ast.walk(fn):
                if not isinstance(n, ast.Call):
                    continue
                if (isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                        and n.func.value.id in sessions and n.func.attr in _SESSION_METHODS):
                    calls.setdefault(n.func.attr, set()).add(name)
                if id(n) not in in_with and (_names_begin_nested(n.func, sessions)
                                             or (isinstance(n.func, ast.Name) and n.func.id in aliases)):
                    outside.append((name, n.lineno))
    return calls, sorted(outside)


def _session_problems(reach):
    """The session-method test's refusals over `reach`, each a (what, which)
    pair: methods outside the seven, held methods the reach never calls, and
    the begin_nested calls outside `async with` (_session_reading)."""
    calls, outside = _session_reading(reach)
    problems = []
    extra = {m: sorted(v) for m, v in calls.items() if m not in _SESSION_ALLOWED}
    if extra:
        problems.append(("methods outside the seven", extra))
    if not _SESSION_HELD <= set(calls):
        problems.append(("held methods never called", sorted(_SESSION_HELD - set(calls))))
    if outside:
        problems.append(("begin_nested outside async with", outside))
    return problems


def test_every_session_method_the_deletion_reaches_holds_its_connection_first_or_sends_nothing():
    """r2 HIGH 1, by class: the deletion's reach calls on a session (db, or a
    parameter annotated AsyncSession) only the four methods that hold the
    connection first and three that send nothing and check nothing out; and
    every begin_nested is used as `async with`, the one form the arming wraps:
    the begin_nested the arming puts on the attempt's session (_HeldNested, in
    _deletion_arm_every_statement) supports `async with` and not `await`.
    Another method (AsyncSession.scalar, get or refresh can check a connection
    out outside the four) or another form fails here. The begin_nested count is
    of the calls outside `async with`, not of the name, and it must be 0: an
    awaited begin_nested refuses and its `async with` twin does not (the ruling
    of 17 Nov 2026 14:10:47Z, 5; the controls below)."""
    with open(main.__file__, encoding="utf-8") as fh:
        source = fh.read()
    reach = _deletion_reach_of(source)
    assert _session_problems(reach) == [], _session_problems(reach)


def test_the_session_reading_counts_main_s_one_awaited_begin_nested_outside_the_reach():
    """The count's control in main.py itself: main's one awaited begin_nested,
    in _settle_ovt_report's OVT report path, is outside the deletion's reach,
    and the same reading counts it in that function's own reach."""
    with open(main.__file__, encoding="utf-8") as fh:
        source = fh.read()
    assert "_settle_ovt_report" not in _deletion_reach_of(source)
    _calls, found = _session_reading(_reach(source, "_settle_ovt_report"))
    lines = source.splitlines()
    assert [(fn, "= await db.begin_nested()" in lines[line - 1]) for fn, line in found] == [
        ("_settle_ovt_report", True)], found


# The count's controls: each form planted at the head of a function of the
# reach (its lines moved past main.py's end). The awaited forms are the
# mutants and must be refused at their line; each `async with` twin makes the
# same call as an `async with` item and must not be.
_NESTED_PLANTS = {
    "awaited": ("x = await db.begin_nested()", True),
    "awaited, its twin": ("async with db.begin_nested():\n    pass", False),
    "alias awaited": ("nested = getattr(db, 'begin_nested', None)\nx = await nested()", True),
    "alias, its twin": ("nested = getattr(db, 'begin_nested', None)\nasync with nested():\n    pass", False),
}


@pytest.mark.parametrize("where", ["delete_player_data", "_deletion_lock_party_row"])
@pytest.mark.parametrize("plant", sorted(_NESTED_PLANTS))
def test_the_session_method_count_refuses_an_awaited_begin_nested_and_not_its_async_with_twin(plant, where):
    form, refused = _NESTED_PLANTS[plant]
    with open(main.__file__, encoding="utf-8") as fh:
        source = fh.read()
    reach = _deletion_reach_of(source)
    assert where in reach and _session_problems(reach) == [], sorted(reach)
    body = ast.parse("async def _plant(db):\n" + "".join(
        "    %s\n" % line for line in form.split("\n"))).body[0].body
    for stmt in body:
        ast.increment_lineno(stmt, 10 ** 6)
    reach[where][0].body[0:0] = body
    calls = [n.lineno for stmt in body for n in ast.walk(stmt)
             if isinstance(n, ast.Call) and not (isinstance(n.func, ast.Name) and n.func.id == "getattr")]
    assert len(calls) == 1, calls
    got = _session_problems(reach)
    want = [("begin_nested outside async with", [(where, calls[0])])] if refused else []
    assert got == want, (plant, where, got)


def test_the_wait_cap_is_below_the_primary_s_deadlock_timeout():
    """The option taken (r1h): every wait of the deletion ends at
    _DELETION_WAIT_CAP_S, before its own deadlock check, so PostgreSQL never
    ends the deletion. That holds only while the cap is below
    deadlock_timeout, 1 s on the primary (read 17 Nov; main's comment beside
    the cap). The controls with waits of the time left (test_mdpl_proof_pg)
    show what PostgreSQL ends when a wait outlasts its check."""
    assert 0 < main._DELETION_WAIT_CAP_S < 1.0, main._DELETION_WAIT_CAP_S


def test_every_catch_in_the_deletion_s_reach_hands_its_signals_back():
    """The bound's two signals are plain exceptions, so a broad catch in the
    reach would swallow them. Every except clause of the reach that catches
    them (bare, Exception, BaseException) around a try body that awaits
    anything either follows a clause that re-raises the two, or opens with
    `if _retryable_for_caller(...): raise`. A new catch fails here until it
    hands them back."""
    with open(main.__file__, encoding="utf-8") as fh:
        source = fh.read()
    broad, kept = [], []
    for name, fns in _reach(source, "delete_player_data").items():
        for fn in fns:
            for tr in ast.walk(fn):
                if not isinstance(tr, ast.Try) or not any(isinstance(n, ast.Await) for s in tr.body
                                                          for n in ast.walk(s)):
                    continue
                handed = False
                for h in tr.handlers:
                    names = {ast.unparse(e) for e in (h.type.elts if isinstance(h.type, ast.Tuple)
                                                      else [h.type])} if h.type is not None else set()
                    if {"_DeletionRowHeld", "_DeletionPastDeadline"} <= names and \
                            isinstance(h.body[0], ast.Raise) and h.body[0].exc is None:
                        handed = True
                        continue
                    if h.type is not None and not names & {"Exception", "BaseException"}:
                        continue
                    first = h.body[0]
                    via = (isinstance(first, ast.If) and "_retryable_for_caller(" in ast.unparse(first.test)
                           and isinstance(first.body[0], ast.Raise) and first.body[0].exc is None)
                    (kept if handed or via else broad).append((name, h.lineno - fn.lineno))
    assert broad == [], broad
    # 8 since CHEAT-ALT-1's merge of main f1460a11 (24 Nov 2026): _alt_delete_one's clause that re-raises the
    # bound's two signals before its own catch of the table's absence; 7 before it.
    assert len(kept) == 8, kept
