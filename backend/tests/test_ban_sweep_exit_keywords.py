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
        elif not kws or any(k.get("banned_ok") is not True for k in kws):
            # FIX-1B point 5: EVERY soft-check call of an exit, not the first
            out.append(f"{path}: the soft check was called with {kws}, not banned_ok=True")
    return out


def _exit_endpoints():
    """{(method, path): endpoint function name} for the BAN-R17 exits."""
    out = {}
    for r in main.app.routes:
        for m in getattr(r, "methods", None) or ():
            if (m, getattr(r, "path", None)) in B.BAN_R17_EXITS:
                out[(m, r.path)] = r.endpoint.__name__
    return out


def _soft_calls_reached(funcs, name, seen=None):
    """Every _check_steam_session call in `name` and in every main function it
    calls by name, transitively: [(function, line, banned_ok keyword or None)]."""
    import ast
    seen = set() if seen is None else seen
    if name in seen or name not in funcs:
        return []
    seen.add(name)
    out = []
    for c in ast.walk(funcs[name]):
        if not isinstance(c, ast.Call):
            continue
        callee = B._name_of(c)
        if callee == "_check_steam_session":
            kw = [k.value for k in c.keywords if k.arg == "banned_ok"]
            out.append((name, c.lineno, ast.unparse(kw[0]) if kw else None))
        elif callee in funcs:
            out += _soft_calls_reached(funcs, callee, seen)
    return out


def _main_funcs(src=None):
    import ast
    src = inspect.getsource(main) if src is None else src
    return {n.name: n for n in ast.parse(src).body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _static_exit_failures(funcs):
    """Every soft-check call an exit can reach, after its first database use
    too (which the driven test does not pass), carries banned_ok=True."""
    out = []
    for key, ep in sorted(_exit_endpoints().items()):
        calls = _soft_calls_reached(funcs, ep)
        if key in B.STRICT_EXITS:
            if calls:
                out.append(f"{key[1]}: a strict exit reaches the soft check {calls}")
        elif not calls or any(kw != "True" for _f, _l, kw in calls):
            out.append(f"{key[1]}: soft-check calls {calls}")
    return out


def test_the_driven_exits_are_ban_r17s_list():
    assert set(_calls(vars(main))) == set(B.BAN_R17_EXITS)


def test_every_exit_passes_banned_ok_to_the_soft_check(monkeypatch):
    assert _exit_failures(vars(main), monkeypatch) == []


def test_every_soft_check_call_an_exit_can_reach_passes_banned_ok():
    assert set(_exit_endpoints()) == set(B.BAN_R17_EXITS)
    assert _static_exit_failures(_main_funcs()) == []


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


# FIX-1B point 5: an exit whose SECOND soft-check call drops banned_ok. The
# first-call check passed it; the every-call check and the static walk refuse it.
_FIRST = "await _check_steam_session(request, steam_id, db, banned_ok=True)\n"


def _second_call_mutant_src():
    src = textwrap.dedent(inspect.getsource(main.queue_leave))
    src = src[src.index("async def "):]     # no decorator: the mutant registers no route
    assert src.count(_FIRST) == 1
    return src.replace(_FIRST, _FIRST + "    await _check_steam_session(request, steam_id, db)\n")


def test_mutant_an_exit_whose_second_soft_check_drops_banned_ok_fails(monkeypatch):
    ns = dict(vars(main))
    exec(compile(_second_call_mutant_src(), "<mutant>", "exec"), ns)
    bad = _exit_failures(ns, monkeypatch)
    assert [b.split(":")[0] for b in bad] == ["/api/v1/queue/leave"], bad
    kws = _drive(ns, _calls(ns)[("POST", "/api/v1/queue/leave")], "/api/v1/queue/leave", monkeypatch)
    assert len(kws) == 2 and kws[0].get("banned_ok") is True   # the first call alone passes


def test_mutant_the_static_walk_sees_a_second_call_after_the_database():
    import ast
    funcs = _main_funcs()
    src = textwrap.dedent(inspect.getsource(main.queue_leave))
    mut = src.rstrip("\n") + "\n    await _check_steam_session(request, steam_id, db)\n"
    funcs["queue_leave"] = ast.parse(mut).body[0]
    bad = _static_exit_failures(funcs)
    assert [b.split(":")[0] for b in bad] == ["/api/v1/queue/leave"], bad
