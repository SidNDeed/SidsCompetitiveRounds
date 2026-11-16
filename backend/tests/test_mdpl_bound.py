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
"""

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
    40001, run again; 55P03, refused at once); nothing else, and nothing
    without the flag."""
    for code, flag, want in (("40P01", True, True), ("40001", True, True),
                             ("40P01", False, False), ("23505", True, False),
                             ("55P03", True, True), ("55P03", False, False),
                             ("57014", True, False)):
        assert main._retryable_for_caller(_db_error(code), flag) is want, (code, flag)
    assert main._retryable_for_caller(ValueError("x"), True) is False
