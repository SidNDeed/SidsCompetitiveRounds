"""Bans part 2a (BAN-R10): an actively banned admin holds no admin power, and
_is_admin (with _require_admin on it) refuses one "Not an admin". The one
admin route that told a banned admin "banned" before this lane,
admin_mail_broadcast (its sender gates read the sender's ban after the
idempotency replay), keeps that answer through the roster proof without the
ban read, twice: _require_admin_roster before the lock, and the lock helper's
re-proof under the lock, _mail_lock_admin(..., roster=True), which proves
with _is_admin_roster where every other caller of the helper keeps the whole
proof (_is_admin). This file holds that exception to its one route, both
halves of it, and its gate to its place; the answers themselves are tested in
test_mail.py (test_broadcast_obeys_the_sender_gates,
test_broadcast_replay_precedes_the_mutable_sender_gates; the helper's two
forms and the bulk grant routes' refusal under the lock beside them).

The sweep of admin routes that check both the roster and a ban, before and
after (found by the syntax tree of main.py at main and at the lane):
  * admin_mail_broadcast: "banned" at main (sender gates), "banned" now; a
    replay of a sent broadcast answers its stored 200 at main and now.
  * i18n_my_grants: the portal session check (_portal_auth) reads the ban
    before the roster at main and now: answer unchanged.
  * admin_ban: its ban reads are of the target and of the admin's rate, not
    of the acting admin's own ban: a banned admin was admitted at main and is
    refused "Not an admin" now (the lane's rule).
  * submit_bug_report, admin_resolve_team_series, admin_moderation_case_act:
    no ban read at main; the lane's gates and _is_admin refuse a banned admin.
"""
import ast
import inspect
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import main  # noqa: E402

MAIN_PY = os.path.join(HERE, "..", "api", "main.py")
ROSTER_ONLY = {"admin_mail_broadcast"}
# Who may call _is_admin_roster by name: the full proof, the roster-only
# check before the lock, and the lock helper's roster form.
ROSTER_CALLERS = {"_is_admin", "_require_admin_roster", "_mail_lock_admin"}


def _callers(src, name):
    tree = ast.parse(src)
    out = set()
    for fn in tree.body:
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name:
                    out.add(fn.name)
    return out


def _roster_handers(src):
    """(the functions that hand roster=True to _mail_lock_admin, the refusals):
    a call of _mail_lock_admin that hands roster any value but the literal
    True, or passes keywords through a starred dict (which can carry roster
    unseen), is refused by the name of the function that makes it."""
    handers, refused = set(), []
    for fn in ast.parse(src).body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for n in ast.walk(fn):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "_mail_lock_admin"):
                continue
            for kw in n.keywords:
                if kw.arg is None:
                    refused.append((fn.name, "starred keywords"))
                elif kw.arg == "roster":
                    if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        handers.add(fn.name)
                    else:
                        refused.append((fn.name, "roster=" + ast.unparse(kw.value)))
    return handers, refused


def _roster_refusals(src):
    """Every way the roster-only proof reaches a function it is not for, by
    name: roster=True handed outside ROSTER_ONLY, a non-literal or starred
    roster, a caller of _is_admin_roster outside ROSTER_CALLERS, and a
    ROSTER_ONLY route that lacks either half of its roster proof."""
    handers, out = _roster_handers(src)
    out += [(n, "hands roster=True outside ROSTER_ONLY") for n in sorted(handers - ROSTER_ONLY)]
    out += [(n, "calls _is_admin_roster outside ROSTER_CALLERS")
            for n in sorted(_callers(src, "_is_admin_roster") - ROSTER_CALLERS)]
    out += [(n, "a ROSTER_ONLY route without roster=True") for n in sorted(ROSTER_ONLY - handers)]
    return sorted(out)


def _gate_failures(src_of):
    """For each roster-only caller: the roster check comes before the lock
    helper, the lock helper before the replay, the replay before the sender
    gates, the sender gates before any write."""
    out = []
    for name, src in src_of.items():
        order = [src.find(w) for w in ("_require_admin_roster(", "_mail_lock_admin(", "_mail_prior_send(",
                                       "_mail_sender_gates(", "INSERT INTO")]
        if -1 in order or order != sorted(order):
            out.append((name, order))
    return out


def test_only_the_broadcast_takes_the_roster_check_alone():
    with open(MAIN_PY, encoding="utf-8") as fh:
        src = fh.read()
    assert _roster_refusals(src) == []          # each refusal by name, first
    assert _callers(src, "_require_admin_roster") == ROSTER_ONLY
    # Both callees of the lock helper's proof stand as plain calls by name.
    assert _callers(src, "_is_admin_roster") == ROSTER_CALLERS
    assert "_mail_lock_admin" in _callers(src, "_is_admin")
    assert _roster_handers(src) == (ROSTER_ONLY, [])
    srcs = {n: textwrap.dedent(inspect.getsource(getattr(main, n))) for n in ROSTER_ONLY}
    assert _gate_failures(srcs) == []


def test_planted_roster_caller_without_the_sender_gates_is_refused():
    planted = ("async def admin_planted(req, db):\n"
               "    await _require_admin_roster(db, req.a, 'x', 'y', req.s)\n"
               "    await db.execute(text('INSERT INTO mail_messages VALUES (1)'))\n")
    assert _callers(planted, "_require_admin_roster") == {"admin_planted"}
    assert [n for n, _ in _gate_failures({"admin_planted": planted})] == ["admin_planted"]


def test_planted_roster_forms_of_the_lock_helper_are_refused_by_name():
    """A second route that hands roster=True, with no sender gates, is refused
    by name, and so is its order; so is a helper that calls _is_admin_roster
    and is not in ROSTER_CALLERS, and a call that hands roster a value that
    is not the literal True or through a starred dict."""
    second = ("async def admin_planted_grant(req, db):\n"
              "    await _require_admin(db, req.a, 'x', 'y', req.s)\n"
              "    rows = await _mail_lock_admin(db, req.a, roster=True)\n"
              "    await db.execute(text('INSERT INTO mail_bulk_grants VALUES (1)'))\n")
    assert ("admin_planted_grant", "hands roster=True outside ROSTER_ONLY") in _roster_refusals(second)
    assert [n for n, _ in _gate_failures({"admin_planted_grant": second})] == ["admin_planted_grant"]
    helper = ("async def _planted_proof(db, sid):\n"
              "    return await _is_admin_roster(db, sid)\n")
    assert ("_planted_proof", "calls _is_admin_roster outside ROSTER_CALLERS") in _roster_refusals(helper)
    for spelling, why in (("roster=flag", "roster=flag"), ("roster=1", "roster=1"),
                          ("**{'roster': True}", "starred keywords")):
        src = ("async def admin_mail_broadcast(req, db):\n"
               "    rows = await _mail_lock_admin(db, req.a, %s)\n" % spelling)
        assert _roster_handers(src)[1] == [("admin_mail_broadcast", why)], spelling
        assert ("admin_mail_broadcast", why) in _roster_refusals(src), spelling
