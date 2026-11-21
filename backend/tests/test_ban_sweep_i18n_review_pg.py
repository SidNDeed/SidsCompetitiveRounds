"""Bans part 2a, FIX-3 2 f (class V d): the translation review commits before
the translator title grants, and each grant runs in a transaction of its own.

On the live harness's whole schema (test_ban_sweep_live.case), through the
route itself (i18n_review, a real portal session):
  * an approval commits the review and both contributors' grants land;
  * with one contributor's grant raising, the review stays committed, the
    other grant lands and the route answers approved;
  * a rejection grants nothing (control).
Mutants: the review's own commit removed (a raising grant then takes the review
with it); the rollback after a failed grant removed (the failed grant's write
then commits with the next grant).

The grant itself is a stand-in that writes one row of its contributor (the
players row's display name), so what lands is read directly; the real grant
is exercised by the title tests.
"""
import inspect
import os
import sys
import textwrap
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from starlette.requests import Request  # noqa: E402

import main  # noqa: E402
from ban_sweep_pg_bounds import bounded_pg  # noqa: E402,F401  (autouse: every session bounded)
import test_ban_sweep_live as L  # noqa: E402
from test_ban_sweep_live import case  # noqa: E402,F401  (the module's schema)
import test_title_ladder_hooks_live as lh  # noqa: E402

_GRANTED = "bs-granted"
_RAISES = []


async def _stand_in_grant(db, steam_id):
    """Writes the contributor's mark, then raises for a contributor in _RAISES
    (after its write, so a missing rollback would let the write commit)."""
    await db.execute(text("UPDATE players SET display_name = :g WHERE steam_id = :s"),
                     {"g": _GRANTED, "s": steam_id})
    if steam_id in _RAISES:
        raise RuntimeError("stand-in grant failure")


def _req(token):
    return Request({"type": "http", "method": "POST", "path": "/api/v1/i18n/review",
                    "headers": [(b"x-portal-token", token.encode())], "query_string": b"",
                    "client": ("127.0.0.1", 1)})


async def _world(sm):
    reviewer, proposer = L._sid(), L._sid()
    token = "bs-portal-" + uuid.uuid4().hex[:20]
    key = uuid.uuid4().hex[:16]
    async with sm() as db:
        for s in (reviewer, proposer):
            await L._player(db, s)
        await lh._insert(db, "i18n_keys", {"key_id": key, "namespace": "client",
                                           "msgctxt": "Ready", "source_hash": "a" * 40})
        await lh._insert(db, "language_grants", {"steam_id": reviewer, "language_code": "de",
                                                 "scope": "translate", "granted_by_steam_id": reviewer})
        await db.execute(text(
            "INSERT INTO i18n_portal_sessions (token, steam_id, bound_ip, created_at, expires_at, first_use_at)"
            " VALUES (:t, :s, '127.0.0.1', NOW(), NOW() + INTERVAL '1 hour', NOW())"),
            {"t": token, "s": reviewer})
        pid = (await db.execute(text(
            "INSERT INTO i18n_proposals (key_id, language_code, source_hash, proposed_target,"
            " proposer_steam_id) VALUES (:k, 'de', :h, 'Bereit', :p) RETURNING id"),
            {"k": key, "h": "a" * 40, "p": proposer})).scalar()
        await db.commit()
    return reviewer, proposer, token, pid


def _body(action, raising=None):
    async def body(sm):
        reviewer, proposer, token, pid = await _world(sm)
        order = sorted([reviewer, proposer], key=main.identity_lock_key)
        _RAISES[:] = [order[0]] if raising == "first" else []
        async with sm() as db:
            ans = await main.i18n_review({"proposal_id": pid, "action": action}, _req(token), db=db)
        async with sm() as db:
            status = (await db.execute(text(
                "SELECT status FROM i18n_proposals WHERE id = :p"), {"p": pid})).scalar()
            marks = {s: (await db.execute(text(
                "SELECT display_name = :g FROM players WHERE steam_id = :s"),
                {"g": _GRANTED, "s": s})).scalar() for s in order}
        return ans["status"], status, [marks[s] for s in order]
    return body


@pytest.fixture(autouse=True)
def _grant(monkeypatch):
    monkeypatch.setattr(main, "_grant_translator_achievements", _stand_in_grant)
    _RAISES[:] = []
    yield
    _RAISES[:] = []


def test_v_d_an_approval_commits_the_review_and_both_grants_land(case):
    assert L._with_sm(case, _body("approve")) == ("approved", "approved", [True, True])


def test_v_d_a_raising_grant_leaves_the_review_and_the_other_grant(case):
    assert L._with_sm(case, _body("approve", raising="first")) == ("approved", "approved", [False, True])


def test_v_d_control_a_rejection_grants_nothing(case):
    assert L._with_sm(case, _body("reject")) == ("rejected", "rejected", [False, False])


def _route_mutant(old, new):
    src = textwrap.dedent(inspect.getsource(main.i18n_review))
    assert src.count(old) == 1, old
    src = src[src.index("async def i18n_review"):]           # the route decorator cut
    ns = dict(vars(main))
    exec(compile(src.replace(old, new), "<mutant>", "exec"), ns)
    return ns["i18n_review"]


_FIRST_COMMIT = ("    await db.commit()\n    # Translator titles", "    # Translator titles")
_GRANT_ROLLBACK = ("                await db.rollback()\n            except Exception:",
                   "                pass\n            except Exception:")


def test_v_d_mutant_without_the_first_commit_a_raising_grant_takes_the_review(case, monkeypatch):
    monkeypatch.setattr(main, "i18n_review", _route_mutant(*_FIRST_COMMIT))
    _ans, status, _marks = L._with_sm(case, _body("approve", raising="first"))
    assert status == "pending", status


def test_v_d_mutant_without_the_rollback_the_failed_grant_commits(case, monkeypatch):
    monkeypatch.setattr(main, "i18n_review", _route_mutant(*_GRANT_ROLLBACK))
    _ans, _status, marks = L._with_sm(case, _body("approve", raising="first"))
    assert marks == [True, True], marks
