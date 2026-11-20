"""Bans part 2a, FIX-3 2 g (class V e): the acting moderator's own ban, on both
/act routes of a moderation case.

_moderation_case_act reads the acting account's ban under its identity lock
(_ban_gate_or_raise after _mail_lock_identities). On the live harness's whole
schema, through each route:
  * an actively banned admin acting by the Discord route (internal key) is
    refused 409 "Banned: ..."; the same admin by the admin route is refused
    403 "Not an admin" first, by _require_admin, whose _is_admin reads the ban
    for a roster member (BAN-R10);
  * an actively banned chat moderator dismissing by the Discord route is
    refused 409;
  * in every refusal the case stays open and no mute row, no ban row and no
    moderator-log row is written;
  * control: the same acts by an account that is not banned land.
Mutant: the core's read removed. Then the admin route still answers 403 (the
read of _require_admin); the Discord route's admin answers 403 not_authorised
(the read of _is_admin inside _chat_moderator_scope); the Discord route's
moderator dismissal LANDS (a chat moderator's scope reads no ban), so that
cell is red.
"""
import inspect
import json
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

import main  # noqa: E402
from ban_sweep_pg_bounds import bounded_pg  # noqa: E402,F401  (autouse: every session bounded)
import test_ban_sweep_live as L  # noqa: E402
from test_ban_sweep_live import case, soft  # noqa: E402,F401  (the module's schema; HMAC keys)
import test_title_ladder_hooks_live as lh  # noqa: E402

_INTERNAL = "ban-sweep-internal-key"


async def _world(sm, role, banned):
    actor, subject = L._sid(), L._sid()
    discord = "9" + actor[-12:]
    async with sm() as db:
        await L._player(db, actor, discord_id=discord)
        sp = await L._player(db, subject)
        if role == "admin":
            await lh._insert(db, "admin_users", {"steam_id": actor})
        else:
            # a live chat_moderate grant on a served channel (_CHAT_MODERATE_LANGS)
            await lh._insert(db, "language_grants", {"steam_id": actor, "language_code": "ru",
                                                     "scope": "chat_moderate",
                                                     "granted_by_steam_id": actor})
        cid = (await db.execute(text(
            "INSERT INTO moderation_cases (kind, subject_player_id, evidence, bucket_key, status)"
            " VALUES ('mail_report', :p, CAST(:ev AS jsonb), :b, 'open') RETURNING id"),
            {"p": sp, "ev": json.dumps({"hits": 1}), "b": "bs-" + subject})).scalar()
        await db.commit()
    if banned:
        await L._ban(sm, actor)
    return actor, subject, discord, str(cid)


async def _landed(sm, subject, cid):
    async with sm() as db:
        one = lambda q, **b: db.execute(text(q), b)  # noqa: E731
        status = (await one("SELECT status FROM moderation_cases WHERE id = CAST(:c AS uuid)", c=cid)).scalar()
        mutes = (await one("SELECT count(*) FROM chat_mutes WHERE steam_id = :s", s=subject)).scalar()
        bans = (await one("SELECT count(*) FROM player_bans WHERE steam_id = :s", s=subject)).scalar()
        logs = (await one("SELECT count(*) FROM admin_actions WHERE CAST(details AS text) LIKE :c",
                          c="%" + cid + "%")).scalar()
    return status, mutes, bans, logs


def _body(route, role, action, banned):
    async def body(sm):
        actor, subject, discord, cid = await _world(sm, role, banned)
        async with sm() as db:
            try:
                if route == "admin":
                    req = main._AdminModCaseActReq(
                        admin_steam_id=actor, hmac_signature=L._admin_sig(actor, "modcase_act", cid),
                        action=action, hours=1)
                    ans = await main.admin_moderation_case_act(cid, req, _slot=None, db=db)
                else:
                    ans = await main.internal_moderation_case_act(
                        cid, {"actor_discord_id": discord, "action": action, "hours": 1},
                        x_internal_key=_INTERNAL, _slot=None, db=db)
                got = ("landed", None) if isinstance(ans, dict) else ("odd", repr(ans)[:80])
            except HTTPException as e:
                await db.rollback()
                got = (e.status_code, str(e.detail).split(":")[0])
        return got, await _landed(sm, subject, cid)
    return body


_NOTHING = ("open", 0, 0, 0)
_CELLS = [("admin", "admin", "mute"), ("internal", "admin", "mute"), ("internal", "moderator", "dismiss")]


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", _INTERNAL)


@pytest.mark.parametrize("route,role,action", _CELLS)
def test_v_e_a_banned_acting_moderator_is_refused_and_nothing_lands(case, soft, route, role, action):
    got, landed = L._with_sm(case, _body(route, role, action, banned=True))
    want = (403, "Not an admin") if route == "admin" else (409, "Banned")
    assert (got, landed) == (want, _NOTHING), (got, landed)


@pytest.mark.parametrize("route,role,action", _CELLS)
def test_v_e_control_the_same_act_by_an_account_not_banned_lands(case, soft, route, role, action):
    got, (status, mutes, bans, logs) = L._with_sm(case, _body(route, role, action, banned=False))
    assert got[0] == "landed", got
    if action == "mute":
        assert (status, mutes, bans, logs) == ("resolved", 1, 0, 1), (status, mutes, bans, logs)
    else:
        assert (status, mutes, bans) == ("dismissed", 0, 0) and logs == 1, (status, mutes, bans, logs)


_CORE_READ = ("    await _ban_gate_or_raise(db, actor_steam_id)\n    actor_w", "    actor_w")


def _core_mutant():
    src = textwrap.dedent(inspect.getsource(main._moderation_case_act))
    assert src.count(_CORE_READ[0]) == 1
    ns = dict(vars(main))
    exec(compile(src.replace(*_CORE_READ), "<mutant>", "exec"), ns)
    return ns["_moderation_case_act"]


_MUTANT_ANSWER = {("admin", "admin", "mute"): ((403, "Not an admin"), _NOTHING),
                  ("internal", "admin", "mute"): ((403, "not_authorised"), _NOTHING),
                  ("internal", "moderator", "dismiss"): (("landed", None), ("dismissed", 0, 0, 1))}


@pytest.mark.parametrize("route,role,action", _CELLS)
def test_v_e_mutant_without_the_core_read_each_route_answers_by_its_other_gates(
        case, soft, monkeypatch, route, role, action):
    monkeypatch.setattr(main, "_moderation_case_act", _core_mutant())
    got = L._with_sm(case, _body(route, role, action, banned=True))
    assert got == _MUTANT_ANSWER[(route, role, action)], got
