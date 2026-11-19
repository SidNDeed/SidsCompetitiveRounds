"""Bans part 2a, FIX-1 M3: every exit of BAN-R17 passes banned_ok=True to
the soft session check, judged by BEHAVIOUR. Each exit's handler is called
with the shared stand-in (soft_check_standin.SoftCheckStandIn) in place of
main._check_steam_session and a session that ends the call at its first use;
the stand-in's record of the call is what the test reads. The spectate leave
keeps its strict session requirement and calls no soft check (F3).

No database; made-up ids only.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import sys
import textwrap

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (HERE, API):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import main  # noqa: E402
import ban_sweep_census as B  # noqa: E402
from schemas import QueueDeclineRequest, SpectateLeaseBody  # noqa: E402
from soft_check_standin import SoftCheckStandIn  # noqa: E402

SID = "76561190000000042"
OTHER = "76561190000000043"


class _Stop(Exception):
    pass


class _StopDb:
    """A session whose first use ends the call: the check under test runs
    before any use of the session in every exit."""

    def __getattr__(self, name):
        raise _Stop(name)


def _req(path):
    from starlette.requests import Request
    return Request({"type": "http", "method": "POST", "path": path, "headers": [],
                    "query_string": b"", "client": ("127.0.0.1", 1)})


def _calls(ns):
    """(method, path) -> a call of that exit's handler in namespace ns."""
    return {
        ("POST", "/api/v1/queues/escape"): lambda r, db: ns["queues_escape"](r, steam_id=SID, db=db),
        ("POST", "/api/v1/queue/leave"): lambda r, db: ns["queue_leave"](r, steam_id=SID, db=db),
        ("POST", "/api/v1/queue/decline"): lambda r, db: ns["queue_decline"](
            QueueDeclineRequest(steam_id=SID, opponent_steam_id=OTHER), r, db=db),
        ("POST", "/api/v1/team/queue/leave"): lambda r, db: ns["team_queue_leave"](
            r, steam_id=SID, expected_series_id=None, db=db),
        ("POST", "/api/v1/ovt/queue/leave"): lambda r, db: ns["ovt_queue_leave"](
            r, steam_id=SID, cause="", expected_series_id=None, db=db),
        ("POST", "/api/v1/ffa/queue/leave"): lambda r, db: ns["ffa_queue_leave"](
            r, steam_id=SID, expected_lobby_id=None, cause="", label="", db=db),
        ("POST", "/api/v1/team/lobby/leave"): lambda r, db: ns["team_lobby_leave"](
            r, steam_id=SID, expected_lobby_id=None, db=db),
        ("POST", "/api/v1/ovt/lobby/leave"): lambda r, db: ns["ovt_lobby_leave"](
            r, steam_id=SID, expected_lobby_id=None, db=db),
        ("POST", "/api/v1/spectate/leave"): lambda r, db: ns["spectate_leave"](
            SpectateLeaseBody(steam_id=SID, lease_id="lease-1"), r, db=db),
    }


def _drive(ns, call, path, monkeypatch):
    stand = SoftCheckStandIn()
    monkeypatch.setattr(main, "_check_steam_session", stand)
    if ns is not vars(main):
        ns["_check_steam_session"] = stand   # a mutant's own globals

    async def go():
        try:
            await call(_req(path), _StopDb())
        except Exception:
            pass
    asyncio.run(go())
    return stand.keywords()


def _exit_failures(ns, monkeypatch):
    out = []
    for (method, path), call in sorted(_calls(ns).items()):
        kws = _drive(ns, call, path, monkeypatch)
        if (method, path) in B.STRICT_EXITS:
            if kws:
                out.append(f"{path}: a strict exit called the soft check {kws}")
        elif not kws or kws[0].get("banned_ok") is not True:
            out.append(f"{path}: the soft check was called with {kws}, not banned_ok=True")
    return out


def test_the_driven_exits_are_ban_r17s_list():
    assert set(_calls(vars(main))) == set(B.BAN_R17_EXITS)


def test_every_exit_passes_banned_ok_to_the_soft_check(monkeypatch):
    assert _exit_failures(vars(main), monkeypatch) == []


def _mutant_ns(fn_name):
    """main's namespace with fn_name's banned_ok=True turned to False."""
    src = textwrap.dedent(inspect.getsource(getattr(main, fn_name)))
    assert src.count("banned_ok=True") == 1, fn_name
    ns = dict(vars(main))
    exec(compile(src.replace("banned_ok=True", "banned_ok=False"), "<mutant>", "exec"), ns)
    return ns


@pytest.mark.parametrize("fn_name,path", [
    ("queue_leave", "/api/v1/queue/leave"),
    ("_lobby_leave_impl", "/api/v1/team/lobby/leave"),
])
def test_mutant_one_exit_with_banned_ok_false_fails(fn_name, path, monkeypatch):
    ns = _mutant_ns(fn_name)
    if fn_name == "_lobby_leave_impl":
        # the lobby routes call the implementation through main's globals
        monkeypatch.setattr(main, "_lobby_leave_impl", ns["_lobby_leave_impl"])
        ns = vars(main)
    bad = _exit_failures(ns, monkeypatch)
    assert any(b.startswith(path + ":") for b in bad), bad
